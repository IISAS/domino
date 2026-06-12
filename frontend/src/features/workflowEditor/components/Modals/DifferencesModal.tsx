import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import LockIcon from "@mui/icons-material/Lock";
import {
  Button,
  CircularProgress,
  Grid,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import { Modal, type ModalRef } from "components/Modal";
import { useWorkspaces } from "context/workspaces";
import { detectSourceFromUrl } from "@utils/gitProviders";
import { useAddRepository } from "features/workspaces/api";
import { type Differences } from "features/workflowEditor/utils/importWorkflow";
import React, { forwardRef, useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "react-toastify";

interface Props {
  incompatiblesPieces: Differences[];
}

enum installStateEnum {
  notInstalled = 0,
  installing = 1,
  installed = 2,
  error = 3,
}

type RepoStatus = "pending" | "installing" | "installed" | "needToken";

// Unique key per missing repository (a repo is identified by its url + path).
const repoKey = (e: Differences): string => `${e.repository_url}#${e.source}`;

const extractErrorMessage = (e: unknown): string => {
  const err = e as
    | { response?: { data?: { detail?: string } }; message?: string }
    | undefined;
  return (
    err?.response?.data?.detail ??
    err?.message ??
    "Could not install repository."
  );
};

export const DifferencesModal = forwardRef<ModalRef, Props>(
  ({ incompatiblesPieces }, ref) => {
    const theme = useTheme();
    const { workspace } = useWorkspaces();
    const queryClient = useQueryClient();
    const [installState, setInstallState] = useState<installStateEnum>(
      installStateEnum.notInstalled,
    );
    const [statuses, setStatuses] = useState<Record<string, RepoStatus>>({});
    const [tokens, setTokens] = useState<Record<string, string>>({});
    const [errors, setErrors] = useState<Record<string, string>>({});

    // Add repositories silently: we manage success/error messaging from this
    // modal so we can detect private repositories and ask for an access token
    // instead of surfacing the raw "Repository not found" toast.
    const { mutateAsync: addRepository } = useAddRepository(
      { workspaceId: workspace?.id },
      {
        onError: () => {
          /* handled per-repository below */
        },
        onSuccess: async () => {
          await queryClient.invalidateQueries({
            queryKey: ["REPOSITORIES", workspace?.id],
          });
        },
      },
    );

    const { installedPieces, uninstalledPieces } = useMemo(() => {
      return {
        installedPieces: incompatiblesPieces.filter((p) => p.installedVersion),
        uninstalledPieces: incompatiblesPieces.filter(
          (p) => !p.installedVersion,
        ),
      };
    }, [incompatiblesPieces]);

    const tokenRequired = useMemo(
      () => uninstalledPieces.some((p) => statuses[repoKey(p)] === "needToken"),
      [uninstalledPieces, statuses],
    );

    // Attempt to install the given repositories, using any access token the
    // user has supplied. Returns the repos that still failed (likely private).
    const attemptInstall = useCallback(
      async (repos: Differences[]): Promise<Differences[]> => {
        const outcomes = await Promise.all(
          repos.map(async (e) => {
            const key = repoKey(e);
            setStatuses((s) => ({ ...s, [key]: "installing" }));
            try {
              await addRepository({
                source: detectSourceFromUrl(e.repository_url),
                path: e.source,
                version: e.requiredVersion,
                url: e.repository_url,
                git_access_token: tokens[key]?.trim() ? tokens[key].trim() : null,
              });
              setStatuses((s) => ({ ...s, [key]: "installed" }));
              setErrors((prev) => {
                const { [key]: _removed, ...rest } = prev;
                return rest;
              });
              return { repo: e, ok: true };
            } catch (err) {
              setStatuses((s) => ({ ...s, [key]: "needToken" }));
              setErrors((prev) => ({ ...prev, [key]: extractErrorMessage(err) }));
              return { repo: e, ok: false };
            }
          }),
        );
        return outcomes.filter((o) => !o.ok).map((o) => o.repo);
      },
      [addRepository, tokens],
    );

    const handleInstallMissingRepositories = useCallback(async () => {
      setInstallState(installStateEnum.installing);
      const failed = await attemptInstall(uninstalledPieces);
      if (failed.length === 0) {
        setInstallState(installStateEnum.installed);
      } else {
        // Some repositories are private (or otherwise unavailable). Reset to
        // the not-installed state so the user can provide access tokens and
        // retry just those repositories.
        setInstallState(installStateEnum.notInstalled);
      }
    }, [attemptInstall, uninstalledPieces]);

    const handleInstallWithTokens = useCallback(async () => {
      const toRetry = uninstalledPieces.filter(
        (p) => statuses[repoKey(p)] === "needToken",
      );
      const missingToken = toRetry.filter((p) => !tokens[repoKey(p)]?.trim());
      if (missingToken.length) {
        toast.warning(
          "Provide an access token for each private repository before installing.",
        );
        return;
      }
      setInstallState(installStateEnum.installing);
      const failed = await attemptInstall(toRetry);
      if (failed.length === 0) {
        setInstallState(installStateEnum.installed);
      } else {
        failed.forEach((e) => {
          toast.error(errors[repoKey(e)] ?? "Could not install repository.");
        });
        setInstallState(installStateEnum.notInstalled);
      }
    }, [attemptInstall, uninstalledPieces, statuses, tokens, errors]);

    const resetState = useCallback(() => {
      setInstallState(installStateEnum.notInstalled);
      setStatuses({});
      setTokens({});
      setErrors({});
    }, []);

    const renderUninstalledSecondaryAction = (item: Differences) => {
      const status = statuses[repoKey(item)];
      if (status === "installed") {
        return (
          <>
            <CheckCircleOutlineIcon />
            <Typography sx={{ marginLeft: 1 }}>
              Installed {item.requiredVersion}
            </Typography>
          </>
        );
      }
      if (status === "installing") {
        return (
          <>
            <CircularProgress size={16} />
            <Typography sx={{ marginLeft: 1 }}>Installing</Typography>
          </>
        );
      }
      if (status === "needToken") {
        return (
          <>
            <Tooltip
              placement="top"
              title="This repository appears to be private. Provide an access token to install it."
            >
              <LockIcon color="warning" />
            </Tooltip>
            <Typography sx={{ marginLeft: 1 }}>Access token required</Typography>
          </>
        );
      }
      return (
        <>
          <Tooltip
            placement="top"
            title="Please install this repository to use this workflow"
          >
            <ErrorOutlineIcon />
          </Tooltip>
          <Typography sx={{ marginLeft: 1 }}>
            Install {item.requiredVersion}
          </Typography>
        </>
      );
    };

    return (
      <Modal
        title="Missing or incompatibles Pieces Repositories"
        content={
          <Grid container>
            <Grid size={{ xs: 12 }}>
              <Typography style={{ textAlign: "justify" }}>
                Some of the pieces necessary to run this workflow are not
                present in this workspace or mismatch the correct version.
                {!!installedPieces.length && (
                  <>
                    Incorrect version pieces need to be manually update on
                    <Link to="/workspaces/settings"> workspace settings</Link>,
                  </>
                )}
              </Typography>
            </Grid>
            <Grid size={{ xs: 12 }}>
              <List>
                {installedPieces.map((item) => (
                  <ListItem
                    disablePadding
                    key={`${item.source}-${item.requiredVersion}`}
                    secondaryAction={
                      <ListItemIcon style={{ right: 0 }}>
                        <Tooltip
                          placement="top"
                          title="Repositories updates need to be done manually on workspace settings"
                        >
                          <ErrorOutlineIcon />
                        </Tooltip>
                        <Typography sx={{ marginLeft: 1 }}>
                          Change to {item.requiredVersion}
                        </Typography>
                      </ListItemIcon>
                    }
                  >
                    <ListItemText
                      primary={item.source}
                      secondary={item.installedVersion ?? "Not installed"}
                    />
                  </ListItem>
                ))}
                {uninstalledPieces.map((item) => {
                  const key = repoKey(item);
                  const status = statuses[key];
                  return (
                    <React.Fragment key={`${item.source}-${item.requiredVersion}`}>
                      <ListItem
                        disablePadding
                        secondaryAction={
                          <ListItemIcon style={{ right: 0 }}>
                            {renderUninstalledSecondaryAction(item)}
                          </ListItemIcon>
                        }
                      >
                        <ListItemText
                          primary={item.source}
                          secondary={
                            status === "installed"
                              ? item.requiredVersion
                              : item.installedVersion ?? "Not installed"
                          }
                        />
                      </ListItem>
                      {status === "needToken" && (
                        <ListItem disablePadding sx={{ mb: 1 }}>
                          <TextField
                            value={tokens[key] ?? ""}
                            onChange={(ev) => {
                              const value = ev.target.value;
                              setTokens((prev) => ({ ...prev, [key]: value }));
                            }}
                            fullWidth
                            size="small"
                            type="password"
                            variant="outlined"
                            label="Access token"
                            autoComplete="new-password"
                            error={!!errors[key]}
                            helperText={
                              errors[key] ??
                              "Provide an access token for this private repository."
                            }
                          />
                        </ListItem>
                      )}
                    </React.Fragment>
                  );
                })}
              </List>
            </Grid>
            {!!uninstalledPieces.length && (
              <Grid container size={{ xs: 12 }} justifyContent="center">
                <Grid size={{ xs: "auto" }}>
                  <Button
                    variant="outlined"
                    onClick={
                      tokenRequired
                        ? handleInstallWithTokens
                        : handleInstallMissingRepositories
                    }
                    disabled={
                      installState === installStateEnum.installing ||
                      installState === installStateEnum.installed
                    }
                    style={
                      installState === installStateEnum.installed
                        ? {
                            borderColor: theme.palette.success.main,
                            color: theme.palette.success.main,
                          }
                        : installState === installStateEnum.error
                          ? {
                              borderColor: theme.palette.error.main,
                              color: theme.palette.error.main,
                            }
                          : {}
                    }
                  >
                    {installState === installStateEnum.installing && (
                      <>
                        <CircularProgress size={16} sx={{ marginRight: 1 }} />
                        Installing
                      </>
                    )}
                    {installState === installStateEnum.notInstalled &&
                      (tokenRequired
                        ? "Install with access tokens"
                        : "Install missing repositories")}
                    {installState === installStateEnum.installed && (
                      <>
                        <CheckCircleOutlineIcon sx={{ marginRight: 1 }} />
                        Success
                      </>
                    )}
                    {installState === installStateEnum.error && (
                      <>
                        <ErrorOutlineIcon sx={{ marginRight: 1 }} />
                        Error
                      </>
                    )}
                  </Button>
                </Grid>
              </Grid>
            )}
          </Grid>
        }
        onClose={resetState}
        ref={ref}
      />
    );
  },
);

DifferencesModal.displayName = "DifferencesModal";

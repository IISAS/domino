import { AuthorizationComponent } from "@components/AuthorizationComponent";
import ChatIcon from "@mui/icons-material/Chat";
import ClearIcon from "@mui/icons-material/Clear";
import DownloadIcon from "@mui/icons-material/Download";
import IosShareIcon from "@mui/icons-material/IosShare";
import SaveIcon from "@mui/icons-material/Save";
import SettingsSuggestIcon from "@mui/icons-material/Settings";
import { Button, Grid, Menu, MenuItem, styled } from "@mui/material";
import { importJsonWorkflow } from "features/workflowEditor/utils";
import React, { useCallback, useRef, useState } from "react";

import {
  MyWorkflowExamplesGalleryModal,
  WorkflowExamplesGalleryModal,
} from "../Modals";

interface Props {
  handleSettings: (event: any) => void;
  handleSave: () => void;
  handleExport: () => void;
  handleImported: (json: any) => void;
  handleClear: () => void;
  handleChatOpen: () => void;
}

const VisuallyHiddenInput = styled("input")({
  clip: "rect(0 0 0 0)",
  clipPath: "inset(50%)",
  height: 1,
  overflow: "hidden",
  position: "absolute",
  bottom: 0,
  left: 0,
  whiteSpace: "nowrap",
  width: 1,
});

export const ButtonsMenu: React.FC<Props> = ({
  handleSettings,
  handleSave,
  handleExport,
  handleImported,
  handleClear,
  handleChatOpen,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const workflowsGalleryModalRef = useRef<any>(null);
  const myWorkflowsGalleryModalRef = useRef<any>(null);

  const [menuElement, setMenuElement] = useState<null | HTMLElement>(null);
  const importMenuOpen = Boolean(menuElement);

  const handleClickImportMenu = useCallback(
    (event: React.MouseEvent<HTMLButtonElement>) => {
      setMenuElement(event.currentTarget);
    },
    [],
  );

  const handleImportFromFile = useCallback(() => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
    setMenuElement(null);
  }, [fileInputRef]);

  const handleImportFromExamples = useCallback(() => {
    setMenuElement(null);
    workflowsGalleryModalRef.current?.open();
  }, [workflowsGalleryModalRef]);

  return (
    <Grid
      container
      spacing={1}
      direction="row"
      justifyContent="flex-end"
      alignItems="center"
      style={{ marginBottom: 10 }}
    >
      <Grid>
        <AuthorizationComponent allowedRoles={["admin", "owner", "write"]}>
          <Button
            variant="contained"
            startIcon={<SettingsSuggestIcon />}
            onClick={handleSettings}
          >
            Settings
          </Button>
        </AuthorizationComponent>
      </Grid>
      <Grid>
        <AuthorizationComponent allowedRoles={["admin", "owner", "write"]}>
          <Button
            variant="contained"
            startIcon={<SaveIcon />}
            onClick={handleSave}
          >
            Create
          </Button>
        </AuthorizationComponent>
      </Grid>
      <Grid>
        <AuthorizationComponent allowedRoles={["admin", "owner", "write"]}>
          <Button
            variant="contained"
            startIcon={<IosShareIcon />}
            onClick={handleExport}
          >
            Export
          </Button>
        </AuthorizationComponent>
      </Grid>
      <Grid>
        <AuthorizationComponent allowedRoles={["admin", "owner", "write"]}>
          <Button
            variant="contained"
            startIcon={<DownloadIcon />}
            id="import-button"
            aria-controls={importMenuOpen ? "import-menu" : undefined}
            aria-haspopup="true"
            aria-expanded={importMenuOpen ? "true" : undefined}
            onClick={handleClickImportMenu}
          >
            <VisuallyHiddenInput
              type="file"
              onChange={async (e) => {
                const json = await importJsonWorkflow(e);
                if (json) handleImported(json);
                if (fileInputRef.current) {
                  fileInputRef.current.value = "";
                }
              }}
              ref={fileInputRef}
            />
            Import
          </Button>
        </AuthorizationComponent>
        <Menu
          id="import-menu"
          anchorEl={menuElement}
          open={importMenuOpen}
          onClose={() => {
            setMenuElement(null);
          }}
          MenuListProps={{
            "aria-labelledby": "import-button",
          }}
        >
          <MenuItem onClick={handleImportFromFile}>from file</MenuItem>
          <MenuItem onClick={handleImportFromExamples}>
            from examples gallery
          </MenuItem>
          <MenuItem
            onClick={() => {
              myWorkflowsGalleryModalRef.current?.open();
            }}
          >
            from my workflows
          </MenuItem>
        </Menu>
        <WorkflowExamplesGalleryModal
          ref={workflowsGalleryModalRef}
          confirmFn={handleImported}
        />
        <MyWorkflowExamplesGalleryModal
          ref={myWorkflowsGalleryModalRef}
          confirmFn={handleImported}
        />
      </Grid>
      <Grid>
        <AuthorizationComponent allowedRoles={["admin", "owner", "write"]}>
          <Button
            variant="contained"
            startIcon={<ChatIcon />}
            onClick={handleChatOpen}
          >
            Chat
          </Button>
        </AuthorizationComponent>
      </Grid>
      <Grid>
        <AuthorizationComponent allowedRoles={["admin", "owner", "write"]}>
          <Button
            variant="contained"
            startIcon={<ClearIcon />}
            onClick={handleClear}
          >
            Clear
          </Button>
        </AuthorizationComponent>
      </Grid>
    </Grid>
  );
};

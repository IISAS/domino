import { GitHub as GitHubIcon, Folder as FolderIcon } from "@mui/icons-material";
import { type SvgIconProps } from "@mui/material/SvgIcon";
import { repositorySource } from "context/workspaces/types";
import { type DetectedProvider } from "features/workspaces";
import { type FC } from "react";

import { GitlabIcon } from "./GitlabIcon";

interface RepositorySourceIconProps extends SvgIconProps {
  source: string;
  detected?: DetectedProvider;
}

export const RepositorySourceIcon: FC<RepositorySourceIconProps> = ({
  source,
  detected,
  ...iconProps
}) => {
  if (source === repositorySource.github) return <GitHubIcon {...iconProps} />;
  if (source === repositorySource.gitlab) return <GitlabIcon {...iconProps} />;
  if (source === repositorySource.generic && detected === "gitlab")
    return <GitlabIcon {...iconProps} />;
  return <FolderIcon {...iconProps} />;
};

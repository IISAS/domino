import {
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
} from "@mui/material";
import Tooltip from "@mui/material/Tooltip";
import { type FC, type ReactNode } from "react";

interface IDrawerMenuItemProps {
  disabled?: boolean;
  isMenuOpen: boolean;
  selected?: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
  className?: string;
}

export const DrawerMenuItem: FC<IDrawerMenuItemProps> = ({
  disabled,
  isMenuOpen,
  selected,
  icon,
  label,
  onClick,
}) => {
  return (
    <Tooltip title={label} placement="right">
      <ListItemButton
        selected={selected}
        sx={{
          display: "flex",
          padding: 0,
          alignContent: "center",
          minHeight: 48,
          justifyContent: isMenuOpen ? "initial" : "center",
          px: 2.5,
        }}
        disabled={disabled}
        onClick={onClick}
      >
        <ListItemIcon
          sx={{
            minWidth: 0,
            mr: isMenuOpen ? 3 : "auto",
            justifyContent: "center",
          }}
        >
          {icon}
        </ListItemIcon>
        <ListItemText
          primary={label}
          sx={{ display: isMenuOpen ? "flex" : "none" }}
        />
      </ListItemButton>
    </Tooltip>
  );
};

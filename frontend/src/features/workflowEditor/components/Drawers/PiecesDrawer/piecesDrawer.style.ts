import MuiDrawer from "@mui/material/Drawer";
import { styled, type Theme, type CSSObject } from "@mui/material/styles";

export const MIN_DRAWER_WIDTH = 200;
export const MAX_DRAWER_WIDTH = 600;
export const DEFAULT_DRAWER_WIDTH = 270;
export const COLLAPSED_RAIL_WIDTH = 65;
export const STORAGE_KEY = "workflowEditor.piecesDrawerWidth";

const openedMixin = (width: number, isDragging: boolean) =>
  (theme: Theme): CSSObject => ({
    width: `${width}px`,
    transition: isDragging
      ? "none"
      : theme.transitions.create("width", {
          easing: theme.transitions.easing.sharp,
          duration: theme.transitions.duration.enteringScreen,
        }),
    overflowX: "hidden",
  });

const closedMixin = (theme: Theme): CSSObject => ({
  transition: theme.transitions.create("width", {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  overflowX: "hidden",
  width: `calc(${theme.spacing(7)} + 1px)`,
  [theme.breakpoints.up("sm")]: {
    width: `calc(${theme.spacing(8)} + 1px)`,
  },
});

interface ResizableDrawerProps {
  open: boolean;
  width: number;
  isDragging: boolean;
}

export const ResizableDrawer = styled(MuiDrawer, {
  shouldForwardProp: (prop) =>
    prop !== "open" && prop !== "width" && prop !== "isDragging",
})<ResizableDrawerProps>(({ theme, open, width, isDragging }) => ({
  flexShrink: 0,
  whiteSpace: "nowrap",
  boxSizing: "border-box",
  ...(open && {
    ...openedMixin(width, isDragging)(theme),
    "& .MuiDrawer-paper": openedMixin(width, isDragging)(theme),
  }),
  ...(!open && {
    ...closedMixin(theme),
    "& .MuiDrawer-paper": closedMixin(theme),
  }),
}));

export const ResizeHandle = styled("div")(({ theme }) => ({
  position: "absolute",
  top: 0,
  left: 0,
  bottom: 0,
  width: 6,
  cursor: "col-resize",
  zIndex: theme.zIndex.drawer + 2,
  backgroundColor: "transparent",
  transition: "background-color 120ms",
  "&:hover": {
    backgroundColor: theme.palette.primary.main,
    opacity: 0.4,
  },
  "&[data-active]": {
    backgroundColor: theme.palette.primary.main,
    opacity: 0.8,
  },
}));

import {
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
} from "@mui/icons-material";
import {
  AppBar,
  Box,
  Divider,
  IconButton,
  Typography,
  useTheme,
} from "@mui/material";
import { DrawerHeader } from "components/PrivateLayout/header/drawerMenu.style";
import { type FC, type ReactNode, useEffect } from "react";

import { ResizableDrawer, ResizeHandle } from "./piecesDrawer.style";
import SidebarAddNode from "./sidebarAddNode";
import { useDrawerResize } from "./useDrawerResize";

interface PiecesDrawerProps {
  handleClose: () => void;
  children?: ReactNode;
  sidePanel?: ReactNode;
  setOrientation: React.Dispatch<
    React.SetStateAction<"horizontal" | "vertical">
  >;
  orientation: "vertical" | "horizontal";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  width: number;
  onWidthChange: (width: number) => void;
  onWidthCommit: (width: number) => void;
}

export const PiecesDrawer: FC<PiecesDrawerProps> = ({
  setOrientation,
  orientation,
  open,
  onOpenChange,
  width,
  onWidthChange,
  onWidthCommit,
}) => {
  const theme = useTheme();
  const {
    width: liveWidth,
    isDragging,
    onHandleMouseDown,
  } = useDrawerResize(width, onWidthCommit);

  useEffect(() => {
    onWidthChange(liveWidth);
  }, [liveWidth, onWidthChange]);

  return (
    <Box sx={{ overflow: "auto" }}>
      <AppBar
        position="fixed"
        sx={{ backgroundColor: theme.palette.background.paper }}
      >
        <ResizableDrawer
          variant="permanent"
          anchor="right"
          open={open}
          width={liveWidth}
          isDragging={isDragging}
        >
          {open && (
            <ResizeHandle
              onMouseDown={onHandleMouseDown}
              data-active={isDragging || undefined}
            />
          )}
          <DrawerHeader sx={{ marginTop: "4rem" }}>
            {open && (
              <Typography variant="h1" sx={{ display: "flex", flex: 1 }}>
                Pieces
              </Typography>
            )}
            <IconButton
              onClick={() => {
                onOpenChange(!open);
              }}
              edge="start"
            >
              {open ? <ChevronRightIcon /> : <ChevronLeftIcon />}
            </IconButton>
          </DrawerHeader>
          {open && (
            <>
              <Divider />
              <Box>
                <SidebarAddNode
                  orientation={orientation}
                  setOrientation={setOrientation}
                />
              </Box>
            </>
          )}
        </ResizableDrawer>
      </AppBar>
    </Box>
  );
};

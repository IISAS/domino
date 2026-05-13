import { useCallback, useEffect, useRef, useState } from "react";

import { MAX_DRAWER_WIDTH, MIN_DRAWER_WIDTH } from "./piecesDrawer.style";

const clamp = (n: number, min: number, max: number) =>
  Math.min(Math.max(n, min), max);

interface UseDrawerResizeResult {
  width: number;
  isDragging: boolean;
  onHandleMouseDown: (e: React.MouseEvent) => void;
}

export function useDrawerResize(
  initialWidth: number,
  onCommit: (px: number) => void,
): UseDrawerResizeResult {
  const [width, setWidth] = useState<number>(initialWidth);
  const [isDragging, setIsDragging] = useState(false);

  const widthRef = useRef(width);
  widthRef.current = width;

  const cleanupRef = useRef<(() => void) | null>(null);

  const onHandleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();

      const startX = e.clientX;
      const startWidth = widthRef.current;

      const prevBodyCursor = document.body.style.cursor;
      const prevBodyUserSelect = document.body.style.userSelect;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      const onMove = (ev: MouseEvent) => {
        const delta = ev.clientX - startX;
        const next = clamp(
          startWidth - delta,
          MIN_DRAWER_WIDTH,
          MAX_DRAWER_WIDTH,
        );
        setWidth(next);
      };

      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.cursor = prevBodyCursor;
        document.body.style.userSelect = prevBodyUserSelect;
        cleanupRef.current = null;
        setIsDragging(false);
        onCommit(widthRef.current);
      };

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);

      cleanupRef.current = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.cursor = prevBodyCursor;
        document.body.style.userSelect = prevBodyUserSelect;
      };

      setIsDragging(true);
    },
    [onCommit],
  );

  useEffect(() => {
    return () => {
      cleanupRef.current?.();
    };
  }, []);

  return { width, isDragging, onHandleMouseDown };
}

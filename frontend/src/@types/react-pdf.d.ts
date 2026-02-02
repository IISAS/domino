declare module "react-pdf" {
  import { ComponentType, ReactNode } from "react";
  import type { PDFDocumentProxy } from "pdfjs-dist";

  export const pdfjs: any;

  export interface DocumentProps {
    file: string | Uint8Array;
    onLoadSuccess?: (pdf: PDFDocumentProxy) => void;
    options?: any;
    children?: ReactNode;
  }
  export const Document: ComponentType<DocumentProps>;

  export interface PageProps {
    pageNumber: number;
    width?: number;
    height?: number;
  }
  export const Page: ComponentType<PageProps>;
}


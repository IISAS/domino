import type { PDFDocumentProxy } from "pdfjs-dist";
import { useState } from "react";
import { pdfjs, Document, Page } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// Vite-friendly PDF worker import
import workerSrc from "pdfjs-dist/build/pdf.worker.min?url";

pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;

const options = {
  cMapUrl: "/cmaps/",
  standardFontDataUrl: "/standard_fonts/",
};

type Props =
  | {
      base64Content: string;
    }
  | { file: string };

export const RenderPDF: React.FC<Props> = (props) => {
  const [numPages, setNumPages] = useState<number>(0);

  const file =
    "file" in props
      ? props.file
      : `data:application/pdf;base64,${props.base64Content}`;

  const onDocumentLoadSuccess = (pdf: PDFDocumentProxy) => {
    setNumPages(pdf.numPages);
  };

  return (
    <Document
      file={file}
      onLoadSuccess={onDocumentLoadSuccess}
      options={options}
    >
      {Array.from({ length: numPages }, (_, index) => (
        <Page
          key={`page_${index + 1}`}
          pageNumber={index + 1}
          width={650}
        />
      ))}
    </Document>
  );
};


  import SignInPage from "@features/auth/pages/signIn/signInPage";
import SignUpPage from "@features/auth/pages/signUp/signUpPage";

export const publicRoutes = [
  { path: "sign-in", element: <SignInPage /> },
  { path: "sign-up", element: <SignUpPage /> },
  // { path: "recover-password", element: <RecoverPasswordPage /> },
];

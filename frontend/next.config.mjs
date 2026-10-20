/** @type {import('next').NextConfig} */
// Na Vercel (projeto com serviços), /api/* é roteado direto para o serviço Python pelo vercel.json.
// Fora dela (dev local/Docker), defina API_URL para o Next encaminhar /api ao backend.
const API_URL = process.env.API_URL || (process.env.VERCEL ? "" : "http://localhost:8000");

const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // O navegador fala apenas com o mesmo domínio; o cookie de sessão é httpOnly/same-site
  // e nenhuma chave de API chega ao frontend.
  async rewrites() {
    return API_URL ? [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }] : [];
  },
};

export default nextConfig;

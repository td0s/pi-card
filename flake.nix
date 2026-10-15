{
  description = "Fold-up card cases for Raspberry Pi boards";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs =
    { nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        packages = [
          (pkgs.python3.withPackages (ps: [
            ps.reportlab
            ps.pymupdf
            ps.jsonschema
            ps.pytest
          ]))
        ];
      };
    };
}

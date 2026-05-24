{
  description = "New flake";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
  };

  outputs = {
    self,
    nixpkgs,
  }: let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};
  in {
    devShells.${system}.default = pkgs.mkShell {
      packages = with pkgs; [
        (python313.withPackages (python-pkgs: [
          python-pkgs.requests
          python-pkgs.proxmoxer
          python-pkgs.paho-mqtt
          python-pkgs.pip
        ]))
      ];
    };
  };
}

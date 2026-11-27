# Installing Git on Windows, macOS, and Linux

Git is a distributed version control system used to record the change history of source code, work with branches, and collaborate through remote repositories. Before using commands such as `git status`, `git add`, `git commit`, `git fetch`, or `git push`, your computer needs a Git client installed and a terminal that can invoke the `git` program.

Git can be installed on Windows, macOS, and many Linux distributions. Each operating system has a different installation method, but the general process is the same: choose an appropriate installation source, install the program, open a new terminal, verify the version, and configure your commit identity.

## 1. Preparing before installation

Before installing, identify your operating system and administrative permissions on the machine:

- **Windows:** use an account with permission to install software; you can install using the Git for Windows installer or Windows Package Manager (`winget`).
- **macOS:** you can use Apple's Command Line Tools or a package manager such as Homebrew.
- **Linux:** install the `git` package from your distribution's repository using the corresponding package manager.

Git is a tool that runs locally on your machine. GitHub, GitLab, and Bitbucket are platforms for hosting repositories and supporting collaboration; creating an account on those platforms does not mean the Git client is already installed.

If the machine already has Git, check first to avoid unnecessary duplicate installations:

```bash
git --version
```

If the terminal returns a version, such as `git version 2.x.y`, Git can already be invoked from the current terminal. You should still check the executable path if the machine has multiple Git installations.

## 2. Installing Git on Windows

On Windows, the standard distribution is **Git for Windows**. This package provides the Git command line, Git Bash, and an optional Git GUI. Git Bash provides a Unix-style shell environment, while Git can also be invoked from PowerShell or Command Prompt if PATH is configured appropriately.

### Method 1: Using the Git for Windows installer

1. Open the official download page: <https://git-scm.com/download/win>.
2. Download the installer that matches your machine's architecture, usually 64-bit or ARM64.
3. Run the installer file and review the options in the setup wizard.
4. Select the required components. Git Bash and Git GUI can be installed alongside the Git command line.
5. At the PATH configuration step, the option typically suitable for developers is allowing Git to be used from the command line and also from third-party software. This option enables PowerShell, Command Prompt, and IDEs to find `git`.
6. Choose the default terminal for Git Bash and other options according to your needs. If your team does not have specific conventions yet, you can keep the default options recommended by the installer.
7. Complete the installation.

Some installer versions include options for line endings, terminal, credential helper, and default branch name. Read these options carefully. For line endings, a project may enforce rules using `.gitattributes`; you should not change configuration just to work around an unexpected diff without understanding the repository's rules.

### Method 2: Using winget

On Windows with Windows Package Manager, open PowerShell or Windows Terminal and run:

```powershell
winget install --id Git.Git -e --source winget
```

The command instructs `winget` to install the Git for Windows package with ID `Git.Git`. If Windows prompts to confirm the source or installation permissions, follow the system instructions. After completion, close and reopen the terminal to load the updated PATH.

To update Git installed via winget:

```powershell
winget upgrade --id Git.Git -e
```

If `winget` is not available on your machine or the package cannot be found, use the official installer in Method 1 or update Windows App Installer and try again.

### Verifying on Windows

Open a new PowerShell window:

```powershell
git --version
where.exe git
```

`git --version` confirms that the program runs; `where.exe git` lists the locations of `git.exe` found in PATH. If there are multiple results, the machine may have multiple Git installations. Check which installation takes precedence to avoid your IDE and terminal using different versions.

You can also open **Git Bash** from the Start Menu and run:

```bash
git --version
which git
```

Git Bash is usually included with Git for Windows. You can use PowerShell, Windows Terminal, Command Prompt, or Git Bash; what matters is that the terminal you use can locate the correct Git executable.

## 3. Installing Git on macOS

macOS has several ways to install Git. You can use the Command Line Tools provided by Apple or install a newer version of Git via Homebrew.

### Method 1: Installing Apple Command Line Tools

Open Terminal and run:

```bash
xcode-select --install
```

macOS will display the Command Line Tools installation dialog. Follow the instructions and wait for the process to finish. This toolkit includes essential development utilities, including Git.

On some machines, when running `git --version` for the first time, macOS may automatically prompt to install Command Line Tools. You can also check the status using:

```bash
xcode-select -p
```

If the command returns a toolkit path, such as `/Library/Developer/CommandLineTools`, the tools are already installed and currently selected. If the machine has full Xcode installed, the path may reside inside the Xcode application bundle.

### Method 2: Installing via Homebrew

If Homebrew is already installed, run:

```bash
brew install git
```

To update the Git package later:

```bash
brew update
brew upgrade git
```

Homebrew usually installs Git under its own prefix, such as `/opt/homebrew` on Apple Silicon or `/usr/local` on some Intel machines. If the machine also has Git from Apple Command Line Tools, check the path to know which installation the terminal is using:

```bash
command -v git
type -a git
git --version
```

If you want to use the Homebrew version, ensure Homebrew's `bin` directory is added to PATH according to the Homebrew installation instructions for your current shell. You do not need to uninstall Command Line Tools just because you also installed Git via Homebrew.

## 4. Installing Git on Linux

Most Linux distributions provide Git in their official package repositories. Use the package manager corresponding to the distribution you are running. The commands below require administrative privileges, typically via `sudo`.

### Ubuntu and Debian

```bash
sudo apt update
sudo apt install git
```

`apt update` refreshes package metadata; `apt install git` installs Git from the configured repositories.

### Fedora

```bash
sudo dnf install git
```

### RHEL, Rocky Linux, and AlmaLinux

```bash
sudo dnf install git
```

Depending on the version and enabled repositories, the package may not be the latest Git release. If a project requires a specific version, check the package sources supported by your organization before installing from external sources.

### Arch Linux and Arch-based distributions

```bash
sudo pacman -S git
```

### openSUSE

```bash
sudo zypper install git
```

### Alpine Linux

```bash
sudo apk add git
```

After installing, verify:

```bash
git --version
command -v git
```

To update Git, use your distribution's package manager, such as `sudo apt upgrade git`, `sudo dnf upgrade git`, or the equivalent update command. Prefer official package repositories or internal repositories approved by your organization to ensure trusted package sources and consistent update procedures.

## 5. Verifying that Git is installed properly

After installation, close old terminal windows and open a new terminal. Run:

```bash
git --version
```

Example:

```text
git version 2.45.0
```

The exact version number depends on the installation source and when it was updated. You do not need to have the exact version shown in the example; what you need to confirm is that the command returns a version rather than reporting that the program was not found.

Check the executable path:

```bash
# Windows PowerShell
where.exe git

# macOS / Linux / Git Bash
command -v git
type -a git
```

If `where.exe` or `command -v` returns a path, the terminal has found Git via PATH. If multiple paths are returned, review your PATH order and IDE settings to ensure all tools use the desired Git installation.

You can check the directory containing Git's helper subcommands:

```bash
git --exec-path
```

This command is useful when troubleshooting an incomplete installation or multiple coexisting Git installations; regular users do not need to modify that directory.

## 6. Configuring your identity for your first commit

After installing Git, configure the name and email recorded in commit metadata. This is the author/committer information that Git stores in history; it is not your GitHub or GitLab login account.

Set it at the current user scope:

```bash
git config --global user.name "Nguyen Van A"
git config --global user.email "nguyen.van.a@example.com"
```

Replace the illustrative values with a name and email that comply with your team's policy. If your organization requires a corporate email or a private email provided by the platform, use the designated address.

Verify both values:

```bash
git config --global --get user.name
git config --global --get user.email
```

Git supports three common configuration scopes:

| Scope | How to declare | Effect |
|---|---|---|
| System | `git config --system` | Applies to all users on the machine; usually requires administrative privileges |
| Global | `git config --global` | Applies to the current user across their repositories |
| Local | `git config --local` | Applies to the current repository and has higher priority than global |

If a project requires a different identity, enter the repository directory and set local configuration:

```bash
git config --local user.name "Team Bot"
git config --local user.email "team-bot@example.com"
```

Local values override global configuration within that repository. Do not use a bot identity or someone else's email unless approved by the team.

## 7. Useful initial configurations

### Setting the default branch name when initializing a repository

So that new repositories initialized with `git init` use the `main` branch:

```bash
git config --global init.defaultBranch main
```

This setting affects repositories initialized afterward; it does not automatically rename branches in existing repositories.

### Choosing an editor for commit messages

Git can open an editor when a commit message needs to be entered. For example, if you want to use Visual Studio Code and the `code` command is already in PATH:

```bash
git config --global core.editor "code --wait"
```

`--wait` tells Git to wait until you close the editor tab or window before continuing. You can choose a different editor based on your development environment.

### Displaying configuration and configuration sources

```bash
git config --list --show-origin
```

This command lists effective configuration settings along with their source files. Review the output before sharing because personal configurations may contain internal details or private paths. When you only need to inspect a single value, prefer `git config --get <key>`.

## 8. Connecting to a remote repository after installing Git

Installing Git does not automatically sign you in to GitHub, GitLab, or your organization's Git server. When you need to clone a repository, you must have the URL and appropriate access permissions.

Example of cloning via HTTPS:

```bash
git clone https://example.com/team/project.git
```

Or cloning via SSH:

```bash
git clone git@example.com:team/project.git
```

HTTPS typically uses a credential manager or the platform's authentication mechanism. SSH requires a suitable key pair and having the public key registered with the server. Do not embed passwords or access tokens directly in URLs that get saved into terminal history or public configuration files.

After cloning, navigate into the repository directory and check:

```bash
cd project
git status
git remote -v
```

If you do not have a repository yet, you can create a local repository to practice basic commands:

```bash
mkdir git-practice
cd git-practice
git init
git status
```

## 9. Troubleshooting common installation errors

### Terminal reports git is not recognized or command not found

The cause is usually that Git is not installed yet, the terminal has not loaded the updated PATH, or the directory containing the executable is not in PATH.

- Windows: close and reopen PowerShell/Windows Terminal; run `where.exe git`; check the PATH option in the Git for Windows installer.
- macOS: run `xcode-select --install` if Command Line Tools are missing; with Homebrew, check `brew --prefix` and PATH.
- Linux: verify the `git` package is installed via your package manager and run `command -v git`.

Do not download a standalone `git.exe` file from an unknown source to fix a PATH issue. Always use the official installer or a trusted package manager.

### Terminal and IDE use two different Git versions

A machine may have Git from multiple sources, such as Git for Windows and another Git bundled with a tool; macOS may have both Apple Command Line Tools and Homebrew installed simultaneously. Check the paths using `where.exe git` or `type -a git`, then review the Git executable configuration in your IDE if the IDE allows selecting one explicitly.

### macOS prompts to install Command Line Tools

This is typically a system prompt when a development tool is not yet available. Run `xcode-select --install` and complete the dialog. If Xcode or Command Line Tools are already installed but Git still does not run, check `xcode-select -p` and the Git path.

### Linux reports insufficient permissions to install packages

Package installation commands usually require administrative privileges. Use `sudo` according to your machine's policy. On corporate machines or managed environments, contact your administrator if your account lacks permissions or package repositories are restricted.

### Unable to authenticate when cloning or pushing

This is usually a credentials or repository permissions issue, not a Git installation error. Check the remote URL, access permissions, credential manager, or SSH key. You can verify the SSH connection according to your Git hosting provider's documentation; never share your private key or token when asking others to help troubleshoot.

## 10. Quick installation and verification workflow

Below is a general checklist you can use on a new machine:

1. Identify the operating system and choose an official installation source or supported package manager.
2. Install Git using the Git for Windows installer, Apple Command Line Tools/Homebrew, or the Linux package manager.
3. Open a new terminal to load PATH.
4. Run `git --version` to verify the installation.
5. Run `where.exe git` on PowerShell or `command -v git` on macOS/Linux to verify the executable.
6. Configure `user.name` and `user.email` at the appropriate global or local scope.
7. Set your editor and `init.defaultBranch` if needed by your team.
8. Clone a repository you have access to, or create a practice repository with `git init`.
9. Run `git status` to confirm Git works inside the repository.

## 11. Key takeaways

Git can be installed on Windows, macOS, and Linux. Windows typically uses Git for Windows; macOS can use Apple Command Line Tools or Homebrew; Linux usually installs the `git` package from the distribution's repository. After installing, open a new terminal, verify with `git --version`, and check the executable path if multiple Git installations exist.

Before your first commit, configure `user.name` and `user.email` so history records proper author metadata. The Git client, Git hosting account, and repository access permissions are separate components; successfully installing Git is only the first step toward working with source code and collaborating via remotes.

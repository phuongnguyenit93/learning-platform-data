# Initializing a Project, Excluding Generated Files, and Creating the First Commit Sequence

This lab walks you through a complete repository initialization workflow: choosing the right root directory, creating the project structure, preparing `.gitignore` and `.gitattributes`, adding source code, generating build files to verify ignore rules, and recording your work with a sequence of small, meaningful commits. The end result is a repository that can be cloned on another machine, contains no unnecessary caches or artifacts, and has a clear enough history for others to understand how the project was formed.

You will build a small Java application named inventory-cli. The example uses Java so that real `.class` files and a `build/` directory are generated, allowing you to verify that Git only tracks source code and documentation while excluding build output from history.

## 1. Goals and Expected Outcomes

Upon completion, the repository should have:

- A repository root scoped correctly to the project.
- A structure separating source code, documentation, and configuration.
- A `.gitignore` excluding build files, caches, logs, and local configs that may contain secrets.
- A `.gitattributes` specifying how text and certain binary files are handled.
- A Java application that compiles and runs.
- A `build/` directory created during compilation that is not tracked by Git.
- At least three initial commits, each representing a distinct unit of work.
- A clean working tree after the final commit, except for ignored files remaining on disk.

Expected commit sequence:

~~~text
main
  |
  o  docs: add local build instructions
  |
  o  feat: add inventory greeting entry point
  |
  o  chore: initialize inventory-cli project
~~~

The commit messages in the diagram are illustrative; Git will generate the actual hashes and timestamps on your machine.

## 2. Environment Setup

Verify that Git and the JDK are ready:

~~~bash
git --version
javac -version
java -version
~~~

`javac` and `java` need to belong to the same compatible JDK. If only a Java Runtime is installed without a compiler, the compilation step will fail.

Check your commit identity:

~~~bash
git config --get user.name
git config --get user.email
~~~

If not configured yet, you will set an identity specifically for this practice repository after initializing it in step 4. Use the real details you want recorded in commits; there is no need to change global configuration if you are only doing this lab.

The directory creation commands in this lab use Bash or Git Bash syntax. On Windows, you can open Git Bash in your working directory. The Git commands remain the same in PowerShell.

## 3. Choosing the Repository Root and Creating the Project Directory

Choose a parent directory for practice exercises, then create the project:

~~~bash
mkdir -p ~/git-practice
cd ~/git-practice
mkdir inventory-cli
cd inventory-cli
~~~

Do not run `git init` inside `~/git-practice` if that directory also holds multiple independent projects. The repository root for this lab is `inventory-cli/`, so Git history manages only the contents of this project.

Create the required directories:

~~~bash
mkdir -p src/main/java/com/example/inventory
mkdir -p docs
~~~

Expected structure:

~~~text
inventory-cli/
  src/
    main/java/com/example/inventory/
  docs/
~~~

There is no need to create `build/`, `target/`, `.gradle/`, or `node_modules/` in the source tree. These directories are generated when building or installing dependencies and will be ignored.

## 4. Initializing the Repository on the main Branch

Initialize Git:

~~~bash
git init -b main
~~~

The `-b main` option sets the initial branch name right from the start. If your Git version is too old to support this option, use:

~~~bash
git init
git branch -M main
~~~

If you do not have a global commit identity configured yet, set a local identity directly in this repository:

~~~bash
git config --local user.name "Your Name"
git config --local user.email "you@example.com"
~~~

Replace the two placeholder values with a name and email suitable for you.

Confirm the repository location and branch:

~~~bash
git rev-parse --show-toplevel
git branch --show-current
git status --short
~~~

The `--show-toplevel` path should point to the `inventory-cli` directory. The current branch should be `main`. If you run full `git status` (without `--short`), Git also reports that the repository has no commits yet.

Inspect the Git metadata directory:

~~~bash
git rev-parse --git-dir
~~~

The `.git/` directory stores the object database, refs, index, and local configuration. Do not commit the contents of `.git/`; Git manages this metadata automatically.

## 5. Creating .gitignore Before Building

Create the `.gitignore` file at the root:

~~~gitignore
# Java compiled files
*.class

# Build output
build/
target/
out/
.gradle/

# Logs and temporary files
*.log
*.tmp

# Local environment and secrets
.env
.env.*
!.env.example
application-local.yml

# IDE local state
.idea/workspace.xml
.vscode/settings.local.json

# Operating system files
.DS_Store
Thumbs.db
Desktop.ini
~~~

These rules suit a small Java example, though they should still be tailored to a real project:

- `*.class` excludes Java bytecode generated by the compiler.
- `build/`, `target/`, and `out/` exclude common output directories.
- `.gradle/` excludes the Gradle cache; wrapper files and build scripts can still be committed.
- `.env` and `.env.*` exclude local configs; `!.env.example` allows keeping a template file with no secrets.
- Only ignore personal IDE state rather than ignoring all IDE configuration by default if the team needs to share formatters or launch configurations.

`.gitignore` primarily applies to untracked paths. If a file has already been committed, adding a pattern afterward does not automatically stop tracking that file.

## 6. Creating .gitattributes for Consistent File Handling

Create the `.gitattributes` file at the root:

~~~gitattributes
# Normalize text files in the repository
* text=auto

# Keep shell scripts with LF line endings
*.sh text eol=lf

# Keep Windows batch files with CRLF line endings
*.bat text eol=crlf

# Treat common binary assets as binary
*.png binary
*.jpg binary
*.jpeg binary
*.jar binary
~~~

`text=auto` lets Git detect text content and normalize line endings in the object database. `eol` specifies the line-ending style on checkout for specific patterns. The `binary` macro disables normal text/diff/merge handling for the corresponding file types.

Check the attributes of a path:

~~~bash
git check-attr text eol diff merge -- README.md
git check-attr text eol diff merge -- assets/logo.png
~~~

In the current example, `assets/logo.png` does not exist yet; the command still displays the rules matching the pattern. There is no need to create a dummy file just to test.

## 7. Creating a README Describing the Project

Create `README.md`:

~~~markdown
# Inventory CLI

A small command-line Java application used in a Git practice lab.

## Structure

- src/main/java/: application source code.
- docs/: development guides.
- build/: bytecode and build output generated automatically, not committed.

## Requirements

- Git
- JDK with java and javac

## Getting Started

Build and run instructions will be added in the docs/ directory.
~~~

The README should explain how newcomers can understand and use the project. Never include tokens, passwords, URLs with credentials, or paths that only exist on a personal machine.

## 8. Reviewing and Creating the First Commit

Check which files currently exist:

~~~bash
git status --short --untracked-files=all
~~~

Stage only the three initial metadata/documentation files:

~~~bash
git add README.md .gitignore .gitattributes
~~~

Inspect the content staged for commit:

~~~bash
git diff --cached --stat
git diff --cached --check
git diff --cached
~~~

- `--stat` shows the file count and amount of changes.
- `--check` detects whitespace errors such as trailing whitespace.
- `git diff --cached` lets you read the exact contents currently in the index.

If everything looks right, create the first commit:

~~~bash
git commit -m "chore: initialize inventory-cli project"
~~~

This commit establishes the repository structure and rules. It does not yet contain application source code.

Inspect the commit:

~~~bash
git show --stat --oneline HEAD
git status --short
~~~

## 9. Adding Application Source Code

Create `src/main/java/com/example/inventory/Main.java`:

~~~java
package com.example.inventory;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Git";
        System.out.println("Hello, " + name + "!");
    }
}
~~~

The program accepts an optional argument. If no argument is passed, it prints `Hello, Git!`.

Check the new file:

~~~bash
git status --short
git diff -- src/main/java/com/example/inventory/Main.java
~~~

Because the new file is untracked, a plain `git diff` does not show its contents yet. You can read the file directly or stage it and inspect `git diff --cached`.

Stage only the Java file and review:

~~~bash
git add src/main/java/com/example/inventory/Main.java
git diff --cached --check
git diff --cached
~~~

Create the second commit:

~~~bash
git commit -m "feat: add inventory greeting entry point"
~~~

This commit contains only the application entry point. Splitting commits by purpose helps reviewers understand changes and makes it easier to locate or revert part of the history.

## 10. Compiling to Produce Generated Files

Create the output directory and compile the Java source:

~~~bash
mkdir -p build/classes
javac -d build/classes src/main/java/com/example/inventory/Main.java
~~~

Run the program:

~~~bash
java -cp build/classes com.example.inventory.Main
java -cp build/classes com.example.inventory.Main Warehouse
~~~

Expected output:

~~~text
Hello, Git!
Hello, Warehouse!
~~~

On PowerShell, you can run the equivalent:

~~~powershell
New-Item -ItemType Directory -Force -Path build/classes | Out-Null
javac -d build/classes src/main/java/com/example/inventory/Main.java
java -cp build/classes com.example.inventory.Main
java -cp build/classes com.example.inventory.Main Warehouse
~~~

After compilation, `build/classes/com/example/inventory/Main.class` is a generated file. It can be regenerated from `Main.java`, so it should not be committed.

## 11. Verifying That .gitignore Is Working

Check the matching rule:

~~~bash
git check-ignore -v build/classes/com/example/inventory/Main.class
~~~

Git should display the `.gitignore` file, line number, and pattern that ignored the `.class` file or the `build/` directory.

View ignored files in status as well:

~~~bash
git status --short --ignored
~~~

You should see a line starting with `!!` for the `build/` directory. This indicates the directory exists on disk but is being ignored.

Confirm that Git is not tracking the output:

~~~bash
git ls-files -- build/
~~~

The command prints no paths if no files inside `build/` are tracked. Regular `git status --short` also does not list the ignored directory.

### 11.1. Ignoring Does Not Delete Local Files

`.gitignore` does not delete `build/`; it only tells Git not to include untracked files in that scope in the untracked list. The `.class` file still exists and the program continues to run.

### 11.2. Ignoring Does Not Untrack Already-Committed Files

If a build file was committed earlier, adding `build/` to `.gitignore` does not remove it from history or stop tracking it. To remove the file from the index while keeping the local copy:

~~~bash
git rm --cached -r build/
git commit -m "chore: stop tracking generated build output"
~~~

Only use this example when `build/` is actually tracked. In this lab, `git ls-files -- build/` should be empty, so you do not need to run these commands.

## 12. Adding Build and Run Instructions

Create `docs/development.md`:

~~~~~markdown
# Developing Inventory CLI

## Compiling

From the repository root, run:

~~~~bash
mkdir -p build/classes
javac -d build/classes src/main/java/com/example/inventory/Main.java
~~~~

## Running

~~~~bash
java -cp build/classes com.example.inventory.Main
java -cp build/classes com.example.inventory.Main Warehouse
~~~~

## Output

Bytecode is placed in build/classes/. This is generated data, excluded from Git by .gitignore, and can be recreated with the compile command.
~~~~~

In `README.md`, replace the temporary note under Getting Started with a link to the newly created document:

~~~markdown
See [build and run instructions](docs/development.md).
~~~

Documentation should describe commands run from the repository root and clearly specify the output directory. This helps others reproduce the result without needing `.class` files from your machine.

Check the changes:

~~~bash
git status --short --untracked-files=all
~~~

New unstaged files do not appear in a plain `git diff`. Once staged, `git diff --cached` below will show all content prepared for commit.

Stage only the documentation and review:

~~~bash
git add docs/development.md README.md
git diff --cached --check
git diff --cached --stat
git diff --cached
~~~

Create the third commit:

~~~bash
git commit -m "docs: add local build instructions"
~~~

This commit adds development instructions without including build output in history.

## 13. Inspecting the Entire First Commit Sequence

View the history:

~~~bash
git log --oneline --decorate --graph
~~~

The output should contain three commits ordered from newest to oldest:

~~~text
* <hash-3> (HEAD -> main) docs: add local build instructions
* <hash-2> feat: add inventory greeting entry point
* <hash-1> chore: initialize inventory-cli project
~~~

Inspect each commit:

~~~bash
git show --stat HEAD
git show --stat HEAD~1
git show --stat HEAD~2
~~~

Check tracked files:

~~~bash
git ls-files
~~~

The list should include `.gitignore`, `.gitattributes`, the README, source code, and development documentation. It should not include `build/classes/Main.class`, log files, `.env`, or cache directories.

Check the working tree and index:

~~~bash
git status --short
git diff
git diff --cached
~~~

The last three commands should show no tracked changes after the commits are complete. Ignored files may still exist and can be confirmed with `git status --short --ignored`.

## 14. Verifying Reproducibility From a Clean Clone

A properly structured repository should not depend on build files or local configuration present only on the creator's machine. You can verify this by cloning into a sibling directory:

~~~bash
cd ..
git clone inventory-cli inventory-cli-clean
cd inventory-cli-clean
git status --short
mkdir -p build/classes
javac -d build/classes src/main/java/com/example/inventory/Main.java
java -cp build/classes com.example.inventory.Main CleanClone
~~~

The expected output is `Hello, CleanClone!`. The initial clean clone does not contain `build/classes/`; this directory appears only after compilation.

If a clean clone fails to build, check whether the README, dependency manifest, wrapper, sample configuration, or required files were left out of commits. Do not solve this by committing caches or personal credentials.

After testing, return to the original working directory if needed:

~~~bash
cd ../inventory-cli
~~~

You can delete the test clone once you confirm you no longer need it. Do not delete the original repository or a working directory with uncommitted changes.

## 15. Troubleshooting Common Situations During Practice

### .class Files Appearing in git status

Check the matching pattern:

~~~bash
git check-ignore -v build/classes/com/example/inventory/Main.class
~~~

If there is no output, verify that `.gitignore` is at the repository root and the pattern matches the path. If the file is already tracked, use `git ls-files --error-unmatch` to confirm and handle it with `git rm --cached` if you want to stop tracking it.

### .env.example Ignored Along With .env

Ensure there is an exception after the ignore pattern:

~~~gitignore
.env.*
!.env.example
~~~

Run `git check-ignore -v .env.example`. If the exception works, the command prints no ignore rule and returns exit code 1 because the file is not ignored. A template file should only be committed if it contains no real credentials.

### Staging the Wrong File

Inspect index contents:

~~~bash
git diff --cached
~~~

If you want to unstage a file while keeping its contents in the working tree:

~~~bash
git restore --staged -- path/to/file
~~~

### A Generated File Was Already Committed

Adding an ignore rule is not enough. Remove the file from the index while keeping the local copy:

~~~bash
git rm --cached -- path/to/generated-file
git commit -m "chore: stop tracking generated file"
~~~

If a large file or secret is already in history, a separate cleanup procedure is required; a new commit deleting the file does not erase data from older commits. For secrets, revoke or rotate the credentials first.

### Commit Reports Missing Identity

Check and set local configuration:

~~~bash
git config --local user.name "Your Name"
git config --local user.email "you@example.com"
~~~

Do not put fake identities into shared history. Use author information aligned with your team's policy.

## 16. Completion Checklist

- [ ] `git rev-parse --show-toplevel` points to the exact project directory.
- [ ] The current branch is `main`.
- [ ] `.gitignore` and `.gitattributes` are at the root and committed.
- [ ] The README describes the structure and how to get started.
- [ ] Java source code is committed and compiles successfully.
- [ ] `build/classes/` is generated but ignored.
- [ ] `git check-ignore -v` identifies the exact rule ignoring generated files.
- [ ] `git ls-files -- build/` lists no build files.
- [ ] There are at least three commits with distinct messages describing their purpose.
- [ ] `git log --oneline --graph` displays the commit sequence in the expected order.
- [ ] `git status --short` shows no uncommitted changes.
- [ ] A clean clone can compile and run without build files from the original machine.

## 17. Extension Exercises

1. Add `src/test/README.md` describing the test layout and commit it separately with the message `test: document test layout`.
2. Create a `.env.example` file with only variable names and placeholders, then confirm it can be staged while `.env` remains ignored.
3. Create a log file inside `build/` and a log file at the root; check whether both are ignored by the current rules.
4. Create a `.txt` file inside `docs/` and run `git check-attr text eol -- docs/example.txt` to observe the applied attributes.
5. Use `git add -p` to stage part of the changes in `README` and create a separate commit.
6. Create another commit updating the message in `README`, then use `git show` to compare the new commit with the previous one.

After each exercise, inspect `git status`, `git diff --cached`, and `git log`. Each commit should represent a change that can be explained independently.

## 18. Key Takeaways

A solid initial repository starts at the right root with a structure clear enough for others to understand, build, and verify the project. Create `.gitignore` before generating output to keep caches, bytecode, logs, and local configs out of history; use `.gitattributes` to standardize line endings and binary file handling. Stage deliberately in focused groups, review the index before committing, and split initialization into small commits. Finally, test a clean clone: if a project only builds on the creator's machine because of generated files or undocumented local setup, the repository is not yet ready for collaboration.

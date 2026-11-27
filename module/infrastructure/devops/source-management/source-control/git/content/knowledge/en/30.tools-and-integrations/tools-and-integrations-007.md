# Providing Identity and Credentials for Non-Interactive Scripts

Automated scripts often need to run Git commands such as fetch, pull, push, commit, or tag without a human sitting at a terminal to enter prompts. To keep the workflow from stalling mid-run, you must provide two distinct groups of information in advance: the identity recorded in commits and the credentials used to authenticate with the remote.

These two groups are not interchangeable. <code>user.name</code> and <code>user.email</code> identify the author/committer in commit metadata; they do not grant access permissions to a repository. Conversely, a token or SSH key lets you connect to a remote, yet it does not automatically determine the name and email recorded in commits.

This lesson belongs to the **Tools and Integrations** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history to branches, merges, rebases, remotes, and tags; it also builds skills in collaborating through branches, resolving conflicts, tracing changes, and recovering from mistakes while preserving important history. This lesson focuses on safely supplying identity and credentials for CI/CD, cron jobs, deployment scripts, and automated Git tasks.

## 1. Two separate questions: who creates the commit, and who is allowed to access the remote?

When a script runs:

~~~bash
git fetch origin
git commit -m "Update generated metadata"
git push origin main
~~~

Git may need to resolve two things:

1. If creating a commit, Git needs to know who the author and committer are.
2. When fetching or pushing, Git needs to authenticate with the server and verify whether the account has read or write permissions.

| Information group | What is it used for? | Examples |
|---|---|---|
| Commit identity | Records author and committer in the commit object | <code>user.name</code>, <code>user.email</code>, <code>GIT_AUTHOR_NAME</code>, <code>GIT_COMMITTER_EMAIL</code> |
| Authentication credential | Authenticates when connecting to a remote | HTTPS token, credential manager, SSH key, SSH agent |
| Authorization | Determines what the credential is allowed to do | Repository read permission, branch push permission, tag/release creation permission |
| Commit signing identity | Signs commits or tags for signature verification | GPG key or SSH signing key |

Commit identity is not proof of authentication. Someone can configure <code>user.name</code> to any string; remote access is determined by the server using credentials and permission policies.

## 2. Configuring author and committer identity

Git requires a name and email to create a commit. If the repository or environment lacks appropriate configuration, the commit command can fail or record unintended information.

### Configuring locally in the repository

For a script that creates commits in the current repository:

~~~bash
git config --local user.name "Automation Bot"
git config --local user.email "automation-bot@example.invalid"
~~~

The <code>--local</code> scope affects only the current repository. This is usually suitable for CI because it does not modify configuration for other repositories on the runner machine.

### Configuring for a single command

If you only need an identity for one commit:

~~~bash
git -c user.name="Automation Bot" \
    -c user.email="automation-bot@example.invalid" \
    commit -m "Update generated metadata"
~~~

These values apply only to that Git process and are not written to persistent configuration.

### Using environment variables

Git supports dedicated environment variables:

~~~bash
export GIT_AUTHOR_NAME="Automation Bot"
export GIT_AUTHOR_EMAIL="automation-bot@example.invalid"
export GIT_COMMITTER_NAME="Automation Bot"
export GIT_COMMITTER_EMAIL="automation-bot@example.invalid"

git commit -m "Update generated metadata"
~~~

<code>GIT_AUTHOR_*</code> specifies the person recorded as the author of the change. <code>GIT_COMMITTER_*</code> specifies the person creating the commit object. If not set separately, Git normally uses configured <code>user.name</code> and <code>user.email</code> for both roles.

Check configuration:

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

To check currently set environment variables without printing credentials:

~~~bash
printf 'Author: %s <%s>\n' "$GIT_AUTHOR_NAME" "$GIT_AUTHOR_EMAIL"
printf 'Committer: %s <%s>\n' "$GIT_COMMITTER_NAME" "$GIT_COMMITTER_EMAIL"
~~~

The name and email are recorded in commit history. Use an organization-approved bot address or noreply address if you do not want to expose personal emails.

### Configuring identity in PowerShell

~~~powershell
git config --local user.name "Automation Bot"
git config --local user.email "automation-bot@example.invalid"

$env:GIT_AUTHOR_NAME = "Automation Bot"
$env:GIT_AUTHOR_EMAIL = "automation-bot@example.invalid"
$env:GIT_COMMITTER_NAME = "Automation Bot"
$env:GIT_COMMITTER_EMAIL = "automation-bot@example.invalid"
~~~

PowerShell environment variables apply to child processes launched from that session. Clear them afterward if you do not want subsequent Git commands in the same session to keep using this identity:

~~~powershell
Remove-Item Env:GIT_AUTHOR_NAME, Env:GIT_AUTHOR_EMAIL, Env:GIT_COMMITTER_NAME, Env:GIT_COMMITTER_EMAIL -ErrorAction SilentlyContinue
~~~

## 3. Authenticating with a remote over HTTPS

For HTTPS URLs, Git may require a username and password. On many platforms, the password here is a personal access token, project token, job token, or provider-issued credential rather than a regular login password.

Example remote:

~~~text
https://git.example.com/team/payment-service.git
~~~

Do not embed tokens directly in the URL:

~~~text
https://username:token@git.example.com/team/payment-service.git
~~~

URLs can be written into <code>.git/config</code>, logs, shell history, diagnostic output, or process lists. Use a secret-free URL and let a credential helper or askpass supply credentials when Git prompts.

### Credential helpers for developer machines

A credential helper allows Git to retrieve login credentials from a dedicated store. For example, Git Credential Manager integrates with the OS's secure credential store and can perform browser-based sign-in.

On Git for Windows or a developer machine with Git Credential Manager installed, verify:

~~~bash
git credential-manager --version
git config --show-origin --get-all credential.helper
~~~

With modern GCM versions, the common configuration is:

~~~bash
git config --global credential.helper manager
~~~

The exact helper name depends on the installed Git/GCM version. GCM suits interactive developer use; non-interactive scripts only work reliably if credentials are already provisioned and the helper can run without opening a browser or prompting a user.

### Other helpers

| Helper | How it works | Notes |
|---|---|---|
| <code>manager</code> | Uses Git Credential Manager | Preferred for developer machines when installed and configured |
| <code>cache</code> | Keeps credentials temporarily in memory for a set timeout | Useful for short working sessions; not a long-term secret store |
| <code>store</code> | Saves credentials in a plain-text file | Unsuitable for sensitive credentials on shared machines or CI |
| Platform/CI helper | Retrieves tokens from the environment or platform-provided secret store | Prefer short-lived tokens and least privilege |

Avoid configuring <code>credential.helper store</code> to save real tokens in plain text. If the credentials file is read, the token can be abused until revoked.

## 4. Supplying HTTPS credentials to scripts with GIT_ASKPASS

When running in CI, a common pattern is storing the token in the CI system's secret store, injecting the token into an environment variable scoped to the job, and supplying it to Git via an askpass program.

<code>GIT_ASKPASS</code> specifies the program Git invokes when it needs an answer to an authentication prompt. The askpass script must write the answer to standard output; never print the token into logs.

### Bash example

Create an askpass script in the job's temporary directory, for example <code>ci-askpass.sh</code>:

~~~bash
#!/bin/sh
case "$1" in
  *Username*)
    test -n "$GIT_HTTP_USERNAME" || exit 1
    printf '%s\n' "$GIT_HTTP_USERNAME"
    ;;
  *Password*)
    test -n "$GIT_HTTP_TOKEN" || exit 1
    printf '%s\n' "$GIT_HTTP_TOKEN"
    ;;
  *)
    exit 1
    ;;
esac
~~~

The script itself contains no token. The token and username come from the secret store:

~~~bash
chmod 700 ci-askpass.sh

export GIT_HTTP_USERNAME="$CI_GIT_USERNAME"
export GIT_HTTP_TOKEN="$CI_GIT_TOKEN"
export GIT_ASKPASS="$PWD/ci-askpass.sh"
export GIT_TERMINAL_PROMPT=0

git -c credential.helper= fetch https://git.example.com/team/payment-service.git
~~~

In this example:

- <code>CI_GIT_USERNAME</code> and <code>CI_GIT_TOKEN</code> must be supplied to the job from a secret store or protected secret variables.
- <code>GIT_ASKPASS</code> points to the program answering prompts.
- <code>GIT_TERMINAL_PROMPT=0</code> prevents Git from waiting for terminal input.
- <code>-c credential.helper=</code> clears configured helpers for this command so the example uses askpass in a controlled way.

Depending on the platform, the username may be an account name, a special string like <code>oauth2</code>, or a provider-required value. Follow your Git server's convention. The token needs read permission for <code>fetch</code>; if the job needs to push, the token must also have the corresponding write permission.

After the job finishes, unset the environment variables:

~~~bash
unset GIT_HTTP_USERNAME GIT_HTTP_TOKEN GIT_ASKPASS GIT_TERMINAL_PROMPT
~~~

Ensure the shell does not enable tracing such as <code>set -x</code> while handling secrets. Do not run <code>env</code>, <code>printenv</code>, or debug commands that dump all environment variables.

### PowerShell example on Windows

You can use a CMD wrapper that invokes a PowerShell script to answer prompts. Create <code>git-askpass.cmd</code> in the job's temporary directory:

~~~bat
@echo off
powershell.exe -NoLogo -NoProfile -NonInteractive -File "%~dp0git-askpass.ps1" -Prompt "%~1"
~~~

Create <code>git-askpass.ps1</code> in the same directory:

~~~powershell
param([string]$Prompt)

if ($Prompt -match "Username") {
    if ([string]::IsNullOrEmpty($env:GIT_HTTP_USERNAME)) { exit 1 }
    [Console]::Out.WriteLine($env:GIT_HTTP_USERNAME)
    exit 0
}

if ($Prompt -match "Password") {
    if ([string]::IsNullOrEmpty($env:GIT_HTTP_TOKEN)) { exit 1 }
    [Console]::Out.WriteLine($env:GIT_HTTP_TOKEN)
    exit 0
}

exit 1
~~~

In the job step:

~~~powershell
$env:GIT_HTTP_USERNAME = $env:CI_GIT_USERNAME
$env:GIT_HTTP_TOKEN = $env:CI_GIT_TOKEN
$env:GIT_ASKPASS = (Join-Path $PSScriptRoot "git-askpass.cmd")
$env:GIT_TERMINAL_PROMPT = "0"

try {
    git -c credential.helper= fetch https://git.example.com/team/payment-service.git
    if ($LASTEXITCODE -ne 0) {
        throw "Git fetch failed"
    }
}
finally {
    Remove-Item Env:GIT_HTTP_USERNAME, Env:GIT_HTTP_TOKEN, Env:GIT_ASKPASS, Env:GIT_TERMINAL_PROMPT -ErrorAction SilentlyContinue
}
~~~

The askpass files contain only logic, no secret values. Create them in a protected temporary workspace and delete them according to the runner's cleanup policy. The wrapper uses the machine's current PowerShell execution policy; if the runner requires signed scripts, sign them or use an administrator-approved mechanism instead of bypassing policy. Environment variables can be read by child processes; therefore, grant tokens only to jobs that need them and never run untrusted code within the same privilege scope.

## 5. Preventing scripts from hanging when credentials are missing

A non-interactive script should never hang indefinitely waiting for a username or password. For HTTPS, set:

~~~bash
export GIT_TERMINAL_PROMPT=0
git fetch origin
~~~

In PowerShell:

~~~powershell
$env:GIT_TERMINAL_PROMPT = "0"
git fetch origin
if ($LASTEXITCODE -ne 0) {
    throw "Git fetch failed: credentials or remote access may be unavailable"
}
~~~

If valid credentials are unavailable, Git will fail instead of waiting for user input. <code>GIT_TERMINAL_PROMPT=0</code> does not supply credentials; it only disables interactive terminal prompts. An askpass program or credential helper still needs to be configured if the server requires authentication.

For Git Credential Manager, make sure the job does not depend on interactive browser sign-in. If the runner lacks credentials, supply a token via a secret store or an identity mechanism supported by the CI platform.

## 6. Authenticating over SSH with ssh-agent

With SSH, Git uses the SSH client to connect. In scripts, a convenient approach is loading the private key into an SSH agent before running Git, then configuring SSH not to prompt the user.

Example on a Linux runner environment:

~~~bash
eval "$(ssh-agent -s)"
ssh-add "$SSH_PRIVATE_KEY_FILE"

export GIT_SSH_COMMAND='ssh -o BatchMode=yes'
git fetch git@git.example.com:team/payment-service.git
~~~

In this example, <code>SSH_PRIVATE_KEY_FILE</code> is the path to a key file supplied by the CI secret store or secure-file mechanism. The private key file must never be committed to the repository. Restrict file read permissions and delete temporary files once the job completes.

<code>ssh-add</code> loads the key into the agent; Git invokes the SSH client and the agent provides the key when the server requests it. <code>BatchMode=yes</code> instructs SSH not to ask interactive questions such as passphrase prompts or host confirmation. If the agent or key is unavailable, the command fails fast.

If the private key has a passphrase, use your CI platform's SSH agent integration or a key-loading step that supports supplying the passphrase from a secret store. Do not strip passphrases just to make a pipeline easier to run. <code>BatchMode=yes</code> applies to Git's SSH connection; loading the key into the agent must be configured separately so it does not require manual entry either.

Verify the agent:

~~~bash
ssh-add -l
~~~

This lists the fingerprints of loaded keys without printing private keys. Never use <code>cat</code> or <code>type</code> to print a private key into logs.

### Specifying keys via SSH config

If the runner has multiple keys, you can configure a specific host entry in an SSH config file:

~~~sshconfig
Host git-ci
    HostName git.example.com
    User git
    IdentityFile ~/.ssh/id_ed25519_ci
    IdentitiesOnly yes
    BatchMode yes
    StrictHostKeyChecking yes
~~~

The remote can use the alias:

~~~bash
git clone git-ci:team/payment-service.git
~~~

Ensure the corresponding public key is authorized on the server. When using an alias in SSH config, the host in the URL must match the alias.

### Verifying host keys

SSH host keys let the client verify the server it is connecting to. In CI, provision <code>known_hosts</code> from a trusted source and verify fingerprints over an independent channel. Do not blindly auto-accept any new host key just to make a pipeline pass.

<code>StrictHostKeyChecking=yes</code> makes the job fail if the host key is untrusted or changed. This is the desired behavior in automated environments with explicitly managed known_hosts.

## 7. Should you use an SSH key or an HTTPS token?

| Criterion | SSH key | HTTPS token |
|---|---|---|
| Authentication method | Public/private key pair | Platform-issued token |
| Permission assignment | Bind public key to an account or deploy key | Bind token to an account, project, or job |
| Permission scope | Can use a repository-specific deploy key | Can restrict scope, repository, and expiration depending on platform |
| Supplying to CI | Secure file or SSH agent | Secret variable/secret manager and askpass/helper |
| Risks to manage | Private key exposure, unverified host keys | Token logged, leaked via URL or environment variables |
| Revocation | Remove key or disable deploy key | Revoke/expire token |

Neither option is automatically safe if permissions are too broad or secrets are stored carelessly. Choose the method that matches your platform, access provisioning workflow, and your team's credential rotation capability.

## 8. Granting least privilege to scripts

Job credentials should have only the permissions they actually need:

- Jobs that only clone or fetch: grant repository read access.
- Jobs that build artifacts or run code checks: usually only need read access.
- Jobs that push automated branches: grant write access only to the needed repository or scope.
- Jobs that publish packages or tags: grant publish permissions only where required.
- Deployment jobs: prefer a dedicated identity for the deployment environment, separate from repository administration permissions where possible.

Separate credentials by job or by environment. A token for a test pipeline should not automatically carry permission to delete branches, manage members, or change repository settings.

If the platform supports short-lived tokens, job tokens, or workload identity, prefer them over long-lived personal tokens. Set explicit expiration times, narrow scopes, and clear revocation procedures.

## 9. Checking read and write access without modifying the remote

Before running the real task, you can verify read access:

~~~bash
git ls-remote origin HEAD
~~~

This queries the remote for refs without checking out or altering local branches. If it fails, check the URL, network, credentials, and read permissions.

To check push capability, you can use a dry run:

~~~bash
git push --dry-run origin HEAD
~~~

A dry run does not update the branch on the remote, yet it can still require authentication and check permissions. It does not guarantee a real push will succeed because remote state could change afterward, or hooks and server policies may apply differently.

Check remote URLs:

~~~bash
git remote -v
~~~

If a URL contains a username/token or embedded credentials, replace it with a clean URL and use a credential helper or askpass. Never include output containing sensitive data in public logs.

## 10. Writing non-interactive Git scripts with error checking

Scripts should fail clearly when credentials are missing, rather than continuing subsequent steps after a failed fetch or push.

Bash example:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

export GIT_TERMINAL_PROMPT=0
export GIT_AUTHOR_NAME="Automation Bot"
export GIT_AUTHOR_EMAIL="automation-bot@example.invalid"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

# Credentials must already be provisioned via helper, askpass, or SSH agent.
git fetch origin

# Verification and change-generation steps go here.
git add generated/
git diff --cached --check

if git diff --cached --quiet; then
    echo "No staged changes"
else
    diff_status=$?
    if [ "$diff_status" -ne 1 ]; then
        exit "$diff_status"
    fi
    git commit -m "Update generated files"
    git push origin HEAD
fi
~~~

<code>set -euo pipefail</code> makes the script exit on command failure, unset variables, or pipeline errors. In pipelines, still pay attention to how the runner handles exit codes and logging.

PowerShell example:

~~~powershell
$ErrorActionPreference = "Stop"
$env:GIT_TERMINAL_PROMPT = "0"
$env:GIT_AUTHOR_NAME = "Automation Bot"
$env:GIT_AUTHOR_EMAIL = "automation-bot@example.invalid"
$env:GIT_COMMITTER_NAME = $env:GIT_AUTHOR_NAME
$env:GIT_COMMITTER_EMAIL = $env:GIT_AUTHOR_EMAIL

git fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }

git add generated/
if ($LASTEXITCODE -ne 0) { throw "git add failed" }

git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw "staged diff check failed" }

git diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    git commit -m "Update generated files"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed" }

    git push origin HEAD
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }
}
elseif ($LASTEXITCODE -ne 0) {
    throw "git diff check failed"
}
~~~

PowerShell does not automatically turn every non-zero exit code from a native program into an exception. Check <code>$LASTEXITCODE</code> after each critical Git command so the pipeline does not report false success.

## 11. Where do credential helpers, askpass, and ssh-agent fit?

These mechanisms are typically invoked by Git or SSH when authentication is needed:

~~~text
Script / CI job
      |
      v
    Git CLI
      |
      +---- HTTPS ----> credential helper / GIT_ASKPASS
      |                         |
      |                         v
      |                  secret store / CI secret
      |
      +---- SSH ------> SSH client
                                |
                                v
                           ssh-agent
                                |
                                v
                          loaded private key
~~~

The script should only know how to invoke Git and how to obtain credentials from a protected source. Never embed tokens or private keys directly in the script's source code.

## 12. Places where you should never store credentials

Avoid the following practices:

- Writing tokens into <code>.git/config</code> or remote URLs.
- Committing <code>.env</code> files, private keys, or credential files.
- Passing tokens directly as command-line arguments if they could appear in process lists or logs.
- Running <code>echo $TOKEN</code> or enabling shell tracing while tokens are in the environment.
- Saving tokens in <code>credential.helper store</code> on runners or shared machines.
- Including private keys in artifacts, caches, or debug output.
- Issuing long-lived personal tokens with admin permissions to every pipeline.

Some CI systems mask secret values in logs, but masking is no substitute for not printing secrets. Transforming, encoding, splitting, or printing part of a token can still expose sensitive data.

## 13. Distinguishing identity errors from authentication errors

| Message or symptom | Error category | How to check |
|---|---|---|
| <code>Author identity unknown</code> | Commit identity | Check <code>user.name</code>, <code>user.email</code>, and <code>GIT_AUTHOR_*</code> |
| <code>Please tell me who you are</code> | Commit identity | Configure identity for the repository or process |
| <code>Authentication failed</code> | Authentication | Check token, helper, askpass, and credential expiration |
| <code>Permission denied (publickey)</code> | SSH authentication | Check key, agent, host alias, and public key permissions |
| <code>Repository not found</code> | URL or authorization | Check URL and read permissions; private repositories may return a generic message |
| <code>Could not read Username</code> | No credential provider configured | Check <code>GIT_ASKPASS</code>, helper, and <code>GIT_TERMINAL_PROMPT</code> |
| <code>Permission to ... denied</code> | Authorization | Credential is valid but lacks permission for the action |
| <code>non-fast-forward</code> | Branch history | Fetch and integrate remote commits per team workflow; this is not a credential error |

Do not rotate tokens simply because a commit complains about missing <code>user.name</code>; likewise, do not change <code>user.email</code> to fix an SSH error. Identify the right error layer before changing configuration.

## 14. Debugging authentication without leaking secrets

When Git fails to connect, check layer by layer:

1. Does the remote URL specify the right host and repository?
2. Does the runner have network connectivity and DNS resolution to the host?
3. For HTTPS, is a credential helper or askpass available?
4. For SSH, does the agent hold the right key and does known_hosts contain a trusted host key?
5. Is the credential unexpired and configured with the right scope?
6. Does the account/identity have the required read or write permission?

Low-risk commands:

~~~bash
git remote -v
git config --show-origin --get-all credential.helper
git config --show-origin --get user.name
git config --show-origin --get user.email
git ls-remote origin HEAD
ssh-add -l
~~~

Do not enable <code>GIT_TRACE_CURL</code>, <code>GIT_CURL_VERBOSE</code>, <code>GIT_TRACE</code>, or verbose SSH debugging in public logs without understanding what data they can output. Some traces may contain URLs, headers, prompts, or sensitive environment details. If tracing is necessary, restrict log viewers, use a minimal-privilege test token, and inspect logs before sharing.

## 15. Credentials and commit signing are two separate mechanisms

Remote authentication tells the server whether the client has read/write permission on the repository. Commit signing identifies which key signed a commit so recipients can verify its signature.

A pipeline might:

- Authenticate with an HTTPS token without signing commits.
- Authenticate with an SSH key while using a separate GPG key to sign commits.
- Use an SSH signing key for commits and a different deploy key to fetch/push.

Do not use an SSH authentication private key as a commit signing key unless your team has explicitly designed and configured it for that purpose. Never commit a private signing key to a repository.

## 16. Checklist for running Git in CI/CD

Before deploying a script into a pipeline:

- Choose an organization-approved bot identity and email.
- Determine whether the job needs read, write, or publish access.
- Provision tokens or keys with least privilege and appropriate expiration.
- Store credentials in the CI secret store, not inside the repository.
- Expose secrets only to trusted jobs and branches that need them.
- Choose HTTPS askpass/credential helper or SSH agent.
- Disable terminal prompts so the job fails fast when credentials are missing.
- For SSH, verify host keys from a trusted source.
- Never print environment variables, tokens, private keys, or sensitive traces.
- Verify read access with <code>git ls-remote</code>; consider <code>git push --dry-run</code> for write access.
- Check exit codes and do not ignore fetch/commit/push failures.
- Have a revocation and rotation procedure ready in case a credential is exposed.

## 17. Self-check exercises

Practice in a test repository or sandbox pipeline:

1. Create a commit with locally configured <code>user.name</code> and <code>user.email</code>.
2. Set <code>GIT_AUTHOR_*</code> and <code>GIT_COMMITTER_*</code>, then inspect commit metadata.
3. Verify that configuring identity does not grant remote access.
4. Create a secret-free askpass script and supply a test token from a protected environment variable.
5. Set <code>GIT_TERMINAL_PROMPT=0</code>, run <code>git ls-remote</code>, and confirm the job does not hang waiting for manual input.
6. Configure an SSH agent with a read-only deploy key and check <code>ssh-add -l</code>.
7. Run fetch with missing credentials to observe the non-interactive failure.
8. Distinguish <code>Author identity unknown</code>, <code>Authentication failed</code>, and <code>Permission denied</code> errors.
9. Inspect pipeline logs to ensure no token, private key, or credential-bearing URL is present.
10. Write a credential revocation/rotation checklist in case a job token is exposed.

A non-interactive Git script needs an explicit identity, credentials supplied from a protected source, and a fast-fail behavior when authentication fails. Keep commit metadata separate from remote access permissions, scope bot permissions strictly to the job's task, and keep all secrets out of source history.

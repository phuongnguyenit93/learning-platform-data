# SSH Keys, ssh-agent, and Verifying Server Fingerprints

SSH allows Git to connect to a remote over an encrypted and authenticated channel. When using SSH, there are two separate verifications: the client must verify it is connecting to the **right server**, and the server must verify the **right user or client key** is requesting access. Personal SSH keys and `ssh-agent` handle client authentication; server fingerprints let you verify the server's identity before sending credentials.

Understanding both directions helps prevent confusing an account's public key with a server's host key, avoids trusting an imposter server, and lets you troubleshoot common errors when cloning, fetching, or pushing over SSH.

## 1. What types of keys does SSH use?

When connecting to a Git remote over SSH, distinguish between two sets of key information:

| Component | Where it lives | Purpose |
|---|---|---|
| User's personal key (client key) | Your machine: private key and public key | Proves you have permission to access the Git account or server |
| Server key (host key) | Git server holds the private host key; client stores trusted public host keys in `known_hosts` | Proves the server is the exact server you intend to connect to |

Personal keys typically have names like `id_ed25519` and `id_ed25519.pub`. You keep the file without the `.pub` suffix on your machine; only register the contents of the `.pub` file with the Git service or administrator. Never send your private key to anyone.

A host key is the server's key, not your account's key. The host key fingerprint is displayed on first connection or when you query it explicitly. You must compare that fingerprint against information published by the provider or administrator through a trusted channel.

Simplified connection flow:

```text
Your machine                             Git server
    |                                         |
    |---- SSH connection request ------------>|
    |<--- host key / verification prompt -----|
    |                                         |
    |  verify fingerprint against trusted src |
    |                                         |
    |---- authenticate using client key ----->|
    |<--- accept or reject -------------------|
    |                                         |
    |---- Git fetch / push over SSH --------->|
```

SSH encrypts the session after establishing the connection and authenticating per the protocol. Host key verification must happen before you trust the server and send account authentication requests.

## 2. Generating a personal SSH key

First, check your existing key directory to avoid overwriting a key currently in use:

```bash
ls -la ~/.ssh
```

In Windows PowerShell:

```powershell
Get-ChildItem $env:USERPROFILE\.ssh
```

If you do not yet have a suitable key, generate an Ed25519 key:

```bash
ssh-keygen -t ed25519 -C "dev@example.com"
```

Git/SSH will prompt for the path to save the key. The default is usually `~/.ssh/id_ed25519`; if a key already exists at that path, choose a distinct name such as `~/.ssh/id_ed25519_work` instead of overwriting it. Next, enter a passphrase to encrypt the private key on disk. Use a strong passphrase; `ssh-agent` can hold the unlocked key in memory so you do not have to re-enter it on every connection.

After generating, you will have two files:

```text
~/.ssh/id_ed25519       # private key: keep secret
~/.ssh/id_ed25519.pub   # public key: register with Git service
```

View the public key to copy it to your Git service's SSH keys management page:

```bash
cat ~/.ssh/id_ed25519.pub
```

In Windows PowerShell:

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

Copy only the public key line starting with the key type such as `ssh-ed25519`. Never copy the contents of the private key file. When adding the key to your Git account, give it a recognizable label based on the device or purpose, such as `Laptop work`.

### Protecting the private key

On Linux/macOS, the directory and private key should be accessible only by the owner:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
```

If you use a different key filename, substitute the exact path. On Windows, OpenSSH may also reject a key if ACLs allow unauthorized users to read the private key; check file permissions in Security properties and grant access only to your account.

Never commit a private key, send it via email/chat, or put a passphrase into scripts or repository configuration variables. If a device holding a private key is lost or suspected of compromise, revoke the corresponding public key from your Git account/service and generate a new key pair.

## 3. Registering the public key with a Git service

Each Git service has its own SSH keys management page. General workflow:

1. Open account settings or the repository's deploy key management section.
2. Select add SSH key.
3. Paste the entire single-line public key from the `.pub` file.
4. Set a device label and expiration if supported by the service.
5. Save and verify the key status.

An account key typically represents a user and inherits the user's account permissions. A deploy key is usually tied to a specific repository and can be granted read-only access or explicitly enabled for write access. Choose the key type according to your needs and organizational policy.

After registering, you can test the SSH connection to the Git server:

```bash
ssh -T git@git.example.com
```

Replace `git.example.com` with your service's hostname. Some services return a greeting confirming your account and state that they do not provide an interactive shell; that can still indicate successful SSH authentication. Check the message against your provider's documentation.

Successful SSH authentication does not prove you have read or write access to every repository. Verify the remote URL and repository permissions using an appropriate Git operation, such as:

```bash
git ls-remote origin
```

This command checks your ability to read refs from the configured remote. Push permission is separate and may be restricted by branch or server policy.

## 4. What is ssh-agent?

`ssh-agent` is a process that holds unlocked private keys in memory. When SSH needs to authenticate, the client can ask the agent to sign the challenge using a loaded key without prompting the user for the passphrase every time.

The agent does not replace the private key and never sends the private key to the server. The private key stays on your machine; the agent performs signing operations using the loaded key. Protect your login session and access permissions to the agent socket, because processes running under your user privileges can ask the agent to sign while it is active.

Basic commands:

```bash
ssh-add ~/.ssh/id_ed25519
ssh-add -l
ssh-add -L
```

- `ssh-add <private-key>` loads a key into the agent; the first time may prompt for the passphrase.
- `ssh-add -l` lists fingerprints of currently loaded keys.
- `ssh-add -L` displays the public keys of currently loaded keys.

Limit how long a key stays in the agent:

```bash
ssh-add -t 1h ~/.ssh/id_ed25519
```

After one hour, the agent removes that key from its held keys list. Remove a specific key:

```bash
ssh-add -d ~/.ssh/id_ed25519
```

Remove all keys from the current agent:

```bash
ssh-add -D
```

## 5. Starting and using ssh-agent on Linux and macOS

In many desktop environments, the agent is started automatically by the operating system or session manager. If no agent is running in your terminal session, with OpenSSH you can run:

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

The first command starts the agent and sets environment variables for the current shell; the second loads the private key. If you open another independent terminal that does not inherit the agent's environment, that shell may not connect to the same agent.

On macOS, Apple OpenSSH can integrate passphrases with Keychain:

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
```

In `~/.ssh/config`, you can configure:

```sshconfig
Host *
    AddKeysToAgent yes
    UseKeychain yes
```

`UseKeychain` is an Apple OpenSSH option; not all OpenSSH builds on Linux or Windows support it. If your machine reports an invalid option, remove that line and use the agent management method appropriate for your operating system.

Check the running agent and loaded keys:

```bash
ssh-add -l
```

If it reports no identities, load the key with `ssh-add`. If it reports it cannot connect to the agent, verify that the agent is running and that `SSH_AUTH_SOCK` points to the agent's socket in the current session.

## 6. Starting ssh-agent on Windows

Windows 10/11 can use the OpenSSH Authentication Agent service if the OpenSSH Client component is installed. Check the service in PowerShell:

```powershell
Get-Service ssh-agent
```

If the service exists, open PowerShell as Administrator to set its startup mode to automatic and start the service:

```powershell
Set-Service -Name ssh-agent -StartupType Automatic
Start-Service ssh-agent
```

Then open a terminal under your user account and load the private key:

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
ssh-add -l
```

If `Get-Service` does not find `ssh-agent`, check the OpenSSH Client feature in Windows Optional Features or install OpenSSH according to your Windows version's documentation. Changing the startup type may require administrator privileges.

PowerShell, Windows Terminal, Git Bash, and other applications may invoke different OpenSSH builds. If `ssh-add` loads a key into one agent but Git does not see it, check which `ssh` and `ssh-add` paths are being invoked:

```powershell
Get-Command ssh
Get-Command ssh-add
```

Consistently use the same OpenSSH installation and agent across your work environment to avoid confusion between multiple processes or sockets.

## 7. Selecting the right key with ~/.ssh/config

If you have multiple accounts or multiple keys, SSH configuration helps select the right identity for each host. Example `~/.ssh/config` file:

```sshconfig
Host git-work
    HostName git.example.com
    User git
    IdentityFile ~/.ssh/id_ed25519_work
    IdentitiesOnly yes

Host git-personal
    HostName git.example.net
    User git
    IdentityFile ~/.ssh/id_ed25519_personal
    IdentitiesOnly yes
```

`Host` is an alias you choose; `HostName` is the real hostname; `User` is usually `git` for Git hosting services; `IdentityFile` specifies the private key; `IdentitiesOnly yes` tells SSH to prioritize the identities configured for that host, avoiding trying too many keys loaded in the agent.

You can then configure the remote using the alias:

```bash
git remote set-url origin git@git-work:platform/storefront.git
```

Check the effective configuration:

```bash
ssh -G git-work
```

This command displays the configuration SSH applies to the alias. If the server uses a port other than 22, add `Port` inside the `Host` block:

```sshconfig
Host git-internal
    HostName git.example.com
    User git
    Port 2222
    IdentityFile ~/.ssh/id_ed25519_work
    IdentitiesOnly yes
```

With a non-default port, the host entry in `known_hosts` typically takes the form `[git.example.com]:2222`. Use the exact hostname and port the client actually connects to.

## 8. Host keys and server fingerprints

On a first SSH connection, the client usually does not yet have the server's host key in `known_hosts`. OpenSSH may display output like:

```text
The authenticity of host 'git.example.com' can't be established.
ED25519 key fingerprint is SHA256:...
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

This is the moment to verify the fingerprint. Obtain the official fingerprint from your provider's official security documentation or administrator via an independent channel, such as an authenticated HTTPS admin portal or a verified internal communication channel. Compare the entire `SHA256:...` string, while also verifying the hostname and algorithm.

Do not accept simply because the hostname looks familiar or because someone else on the team typed `yes`. If the fingerprint matches the trusted source, confirm the connection; OpenSSH will store the host key in `known_hosts` to compare on future connections.

### Fetching the fingerprint to compare before connecting

You can query the public host key using `ssh-keyscan`, save it to a temporary file, and compute its fingerprint:

```bash
ssh-keyscan -t ed25519 git.example.com > /tmp/git.example.com.keys
ssh-keygen -lf /tmp/git.example.com.keys -E sha256
```

Compare the computed fingerprint against the official fingerprint published by the administrator or provider. Only after verification should you append the checked key to `known_hosts`:

```bash
cat /tmp/git.example.com.keys >> ~/.ssh/known_hosts
```

`ssh-keyscan` only collects the public key the server presents at the moment of the query. By itself, it does not verify that the key belongs to the genuine server; if an attacker sits in the middle of the connection, `ssh-keyscan` could collect the attacker's key instead. Therefore, comparing against a fingerprint obtained via an independent channel is mandatory.

If the provider publishes multiple host key algorithms, query and verify the exact key type your client will use. Never treat `ssh-keyscan` output itself as the authoritative fingerprint for verification.

## 9. What does known_hosts store?

`known_hosts` stores the public host keys that the client has accepted for a hostname/port. By default, the file is usually located at:

```text
Linux/macOS: ~/.ssh/known_hosts
Windows:     %USERPROFILE%\.ssh\known_hosts
```

Look up a stored host key:

```bash
ssh-keygen -F git.example.com -f ~/.ssh/known_hosts
```

Compute fingerprints from stored host keys:

```bash
ssh-keygen -lf ~/.ssh/known_hosts -E sha256
```

OpenSSH can hash hostnames in `known_hosts` to reduce exposing the list of servers in the file. `ssh-keygen -F` can still locate a hashed host when given the exact hostname.

You can require SSH to connect only if the host key is already in the trusted list:

```sshconfig
Host git.example.com
    StrictHostKeyChecking yes
```

In this mode, add the verified host key to `known_hosts` before connecting. `StrictHostKeyChecking accept-new` can automatically accept a new host on first connection and reject changed host keys afterward; it is useful for some automation environments, though it does not replace independent fingerprint verification under strict security procedures.

## 10. Handling host key change warnings

If a server changes its host key, or you connect to the wrong server, OpenSSH may display a warning:

```text
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
```

This is a critical security warning. Causes can include an administrator rotating the host key, a server replacement, a DNS/IP address change, or a potential man-in-the-middle attack. Never clear the warning by disabling checks or automatically accepting the new key.

Resolution workflow:

1. Stop connecting and verify with the administrator/provider whether the host key was recently changed.
2. Obtain the new fingerprint via an independent channel and compare it exactly.
3. If the change is legitimate, back up `known_hosts` if needed and remove the old entry for that specific host.
4. Add the newly verified host key, then reconnect.

Remove an entry for a default-port hostname:

```bash
ssh-keygen -R git.example.com
```

For a non-default port:

```bash
ssh-keygen -R '[git.example.com]:2222'
```

Then add the verified new key or reconnect and check the fingerprint before accepting. `ssh-keygen -R` only deletes the corresponding local record; it does not verify the new key and does not fix DNS or server issues.

## 11. Testing connections and diagnosing errors

Test SSH authentication:

```bash
ssh -T git@git.example.com
```

If you need to inspect key selection and the authentication handshake:

```bash
ssh -vT git@git.example.com
```

Debug output shows which config files SSH reads, which identities it tries, whether it connects to the agent, and how the server responds. Do not share debug logs publicly if they contain internal hostnames, usernames, or sensitive details.

Common errors:

| Message | Possible cause | Resolution |
|---|---|---|
| `Permission denied (publickey)` | Public key not registered, client picked wrong private key, or agent has not loaded the key | Check account settings, `IdentityFile`, `ssh-add -l`, and run `ssh -vT` |
| `Host key verification failed` | Host key missing from `known_hosts` or does not match | Verify fingerprint from a trusted source, then add the right key |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | Host key changed or connected to a different server | Stop and verify the change before updating `known_hosts` |
| `Too many authentication failures` | SSH tried too many keys from the agent | Use `IdentitiesOnly yes` and specify the exact `IdentityFile` |
| `Could not open a connection to your authentication agent` | Agent is not running or shell lacks the right socket/environment variable | Start the agent in the current session and reload the key |
| `sign_and_send_pubkey: signing failed` | Agent cannot sign, key is locked, or key type is incompatible | Check agent, passphrase, file permissions, and key type |
| Timeout or connection refused | Wrong hostname/port, firewall, or server does not accept SSH | Check remote URL, VPN, firewall, and service port |

If `ssh -T` authenticates successfully but `git ls-remote origin` is rejected, check the repository URL and read permissions. If fetch works but push fails, check write permissions, branch protection, and remote policies.

## 12. Security notes for using agent and SSH

- Protect private keys with a passphrase and load keys into the agent only for the duration needed.
- Create separate keys for work and different purposes when policy requires; revoke keys belonging to lost or retired devices.
- Register only the public key. Never send a private key or passphrase to an administrator.
- Verify the host key on the first connection and whenever a change warning appears.
- Restrict `ForwardAgent yes`. Agent forwarding allows a remote machine to ask your local agent to sign during the forwarded session; if the remote machine is untrusted, this can be abused even though the private key never leaves your machine.
- Never enable agent forwarding globally. If genuinely needed, restrict it to specific hosts and use it only with trusted servers.
- Keep OpenSSH and Git LFS/Git updated according to OS and organizational policies.
- Never disable `StrictHostKeyChecking` to work around connection errors. Verify and fix the host key properly instead.

## 13. Workflow for setting up SSH for a repository

A typical workflow for a new development machine:

1. Check `~/.ssh` or `%USERPROFILE%\.ssh` to identify existing keys.
2. Generate a new Ed25519 key with a passphrase if needed.
3. Register the `.pub` public key with your account or an authorized deploy key.
4. Start `ssh-agent`, load the private key, and verify with `ssh-add -l`.
5. Obtain the host key fingerprint from an official source; verify it and save it to `known_hosts`.
6. Run `ssh -T git@<host>` to verify account authentication.
7. Configure the SSH remote URL and run `git ls-remote origin` to verify repository read access.

Example remote configuration:

```bash
git remote set-url origin git@git.example.com:platform/storefront.git
git remote -v
git ls-remote origin
```

If your organization uses a host alias or custom SSH port, configure `~/.ssh/config` first and then use the alias in the remote URL. Record the verified hostname, port, and fingerprint in your team's onboarding documentation so other members can verify them independently.

## 14. Hands-on exercises

Perform these exercises using a test account and test repository; do not use production private keys for practice:

1. Generate an Ed25519 key pair with a passphrase and identify the difference between the private key file and `.pub`.
2. Register the public key in a test Git account.
3. Start `ssh-agent`, load the key with `ssh-add`, and verify with `ssh-add -l`.
4. Fetch the host key with `ssh-keyscan`, compute the fingerprint of the saved file with `ssh-keygen -lf /tmp/git.example.com.keys -E sha256`, and compare it with the fingerprint published by the provider via an independent channel.
5. Save the verified host key to `known_hosts`, then test connecting with `StrictHostKeyChecking yes`.
6. Configure a host alias in `~/.ssh/config` to select a specific private key.
7. Run `ssh -vT` and `git ls-remote origin`; explain which command tests SSH authentication and which tests repository read permission.
8. In a test environment, observe how `ssh-keygen -R` removes an old entry; explain why you must verify the new host key before adding it back.

You have completed the exercise when you can distinguish client keys from host keys, use `ssh-agent`, verify fingerprints before trusting a server, and handle host key change warnings safely.

# Diagnosing URL, DNS, Proxy, Certificate, and SSH Connection Errors

When Git cannot communicate with a remote repository, error messages usually appear during `git clone`, `git fetch`, `git pull`, or `git push`. The cause may lie in the remote address, domain name resolution, TCP transport, proxy, TLS certificates, authentication, or repository access permissions. For SSH connections, errors can also stem from the SSH port, private key, `ssh-agent`, or the list of trusted host keys.

To pinpoint the exact cause, check layer by layer from the outside in: confirm the URL and hostname, check DNS and network ports, check proxy/TLS, and then check Git authentication and access permissions. Each step should use a small command to isolate which layer is failing before changing configuration.

In Git source control services, a remote is the connection endpoint through which team members exchange commits and branches. Systematic diagnosis helps restore collaboration without modifying the wrong remote or weakening connection security.

## 1. Understanding the Layers of a Git Connection

A networked Git command typically passes through the following steps:

1. Git determines the URL to use from remote configuration, URL rewrite rules, and fetch/push settings.
2. The operating system resolves the hostname to an IP address via DNS.
3. The client opens a TCP connection to the server or proxy on the appropriate port.
4. For HTTPS, both sides negotiate TLS and verify the server certificate; for SSH, both sides negotiate the protocol and verify the host key.
5. Git performs user or SSH key authentication.
6. The server checks whether the repository exists and whether the account has read or write permissions.

A failure at an earlier step can prevent later steps from running. For example, `Could not resolve host` happens before Git can authenticate; `Permission denied (publickey)` indicates that the SSH connection reached the server, but key-based authentication did not succeed.

```text
Remote URL
   |
   v
DNS resolves hostname
   |
   v
TCP to server/proxy port
   |
   +---- HTTPS: TLS + certificate check
   |
   +---- SSH: SSH handshake + host key verification
   |
   v
Account/key authentication
   |
   v
Repository and read/write permission check
```

Not every check proves the entire path works. `Resolve-DnsName` only checks DNS; `Test-NetConnection` checks TCP connectivity; `curl.exe -Iv` checks the HTTPS connection at the HTTP/TLS level; `git ls-remote` additionally checks the Git protocol, authentication, and repository read permissions.

## 2. Starting with the URL and Remote Configuration

First, identify which remote is failing and which URL is actually being used. The examples below use the `origin` remote; replace it with the remote in your project.

```bash
git remote -v
git remote get-url --all origin
git remote get-url --push --all origin
```

`git remote -v` displays fetch and push URLs. The two URLs can differ if the repository has `pushurl` configured. The two `git remote get-url` commands show the URL after Git applies URL rewrite rules; the second retrieves the push URL. Therefore, looking at only one URL can miss the fact that fetch goes to one server while push goes to another.

You can inspect configuration values along with where they are defined:

```bash
git config --show-origin --get-regexp '^remote\..*\.(url|pushurl)$'
git config --show-origin --get-regexp '^url\..*\.insteadof$'
```

`--show-origin` shows which file a setting comes from, such as `.git/config`, a user config file, or a system config file. A `url.<base>.insteadOf` rule can automatically replace a URL prefix, causing the effective address to differ from what you thought you configured.

### Recognizing URL Syntax

Three common forms:

```text
HTTPS:        https://git.example.com/team/project.git
SSH URI:      ssh://git@git.example.com:22/team/project.git
SSH SCP-like: git@git.example.com:team/project.git
```

- HTTPS typically uses port `443` and authenticates using a token, OAuth, or a credential manager depending on the provider.
- SSH URI explicitly specifies the protocol and can include a port after the hostname.
- The SCP-like form uses a colon after the hostname to separate the repository path; this is standard Git/SSH syntax, not a full SCP URL.

Some common URL mistakes:

- Misspelling the hostname, group name, or repository name.
- Using `/` instead of `:` in the SCP-like form, such as `git@git.example.com/team/project.git`.
- Missing the SSH username or using the wrong SSH port.
- The URL still pointing to an old repository after the project moved groups or changed servers.
- Whitespace, special characters, or extra slashes in the path.
- The fetch URL is correct, but `pushurl` still points to an old remote.

Whether repository names are case-sensitive depends on the server. Some services automatically redirect old URLs, but you should not rely on redirects instead of updating the remote accurately.

### Fixing the URL Once You Confirm the Correct Address

```bash
git remote set-url origin https://git.example.com/team/project.git
```

If you only need to change the URL used for pushing:

```bash
git remote set-url --push origin git@git.example.com:team/project.git
```

These commands update local configuration and do not automatically test whether the new URL is reachable. After editing, inspect the URL again and test with `git ls-remote origin`.

**Security note:** Remote URLs sometimes contain a username or token if someone embedded credentials in the URL. Before sharing `git remote -v` output, check and mask any tokens, passwords, internal details, or private hostnames. Do not store tokens directly in URLs because they can appear in configuration files, logs, or screenshots.

## 3. Checking DNS and Hostname

DNS translates a hostname, such as `git.example.com`, into an IP address. If DNS fails to resolve, Git typically reports:

```text
fatal: unable to access 'https://git.example.com/...':
Could not resolve host: git.example.com
```

First, confirm the hostname extracted from the remote URL is accurate. Then check domain name resolution.

### On Windows PowerShell

```powershell
Resolve-DnsName git.example.com
nslookup git.example.com
```

### On Linux or macOS

```bash
dig +short git.example.com
nslookup git.example.com
```

On Linux, you can also run `getent hosts git.example.com` to test resolution through the system resolver; `getent` is usually not available by default on macOS.

If the command returns an IP address, DNS resolved the hostname at the time of the check. If you receive `NXDOMAIN`, the domain name may be wrong or the record does not exist in the DNS server your machine uses. If the query times out, the DNS resolver may be unresponsive, the VPN may be disconnected, or the network may be blocking DNS queries.

In corporate networks, an internal hostname may only resolve when connected to a VPN or using internal DNS. If a service spans multiple network zones, split-horizon DNS may return different addresses depending on your location. Confirm your VPN, active network, and DNS resolver according to your administrator's instructions.

`ping` is not a sole reliable test for DNS or TCP. A server may block ICMP while still accepting HTTPS/SSH connections; a failed ping does not prove the Git server is down. Check the actual service port in the next step.

## 4. Checking TCP Connectivity and Service Ports

Once you have the hostname, check whether your machine can open a connection to the required port. HTTPS normally uses port `443`; SSH normally uses port `22`, though a server may configure a different port. If Git routes through a proxy, the TCP connection from your machine goes first to the proxy hostname and port; test the proxy instead of only testing the target server directly. For example, if the proxy is `proxy.example.com:8080`, test TCP to `proxy.example.com` on port `8080`.

### On Windows PowerShell

```powershell
Test-NetConnection git.example.com -Port 443
Test-NetConnection git.example.com -Port 22
```

Check the `TcpTestSucceeded` field. `True` means the TCP handshake to that port succeeded; it does not yet prove TLS, Git authentication, or repository permissions work. `False` can be caused by a wrong hostname/port, firewall, VPN, proxy, network route, or no service listening.

### On Linux or macOS

```bash
nc -vz git.example.com 443
nc -vz git.example.com 22
```

If `nc` is not installed, use the operating system's built-in network testing tools or ask your network administrator to check the path and port. Do not open firewall ports or modify routes on a company machine without authorization.

Distinguish between common results:

- **Connection timed out:** no response received within the timeout window; usually related to firewall, VPN, routing, proxy, or filtered port.
- **Connection refused:** the target host is reachable, but no service is listening on that port or the server actively refuses connections.
- **Connection reset:** the connection was closed abruptly; may be caused by a proxy, firewall, security appliance, or the server.
- **TCP succeeded:** move on to checking TLS/SSH and authentication.

## 5. Diagnosing HTTP/HTTPS Proxies

In corporate networks, HTTPS traffic may have to pass through a proxy. A wrong proxy address, wrong port, or missing proxy authentication can cause `git fetch` and `git push` to fail even when DNS and the internal network work.

### Checking Proxy Settings in Git Configuration

```bash
git config --show-origin --get-all http.proxy
git config --show-origin --get-regexp '^http\..*\.proxy$'
```

The first command checks the `http.proxy` setting; the second checks proxies set for specific URLs. URL-specific settings can cause one server to use a custom proxy while another server does not.

Git can also receive proxy settings via environment variables. Common names are `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` (some programs also read lowercase variables). Inspect their values locally on your machine and mask any username, password, or token before sharing. `NO_PROXY` lists hosts/domains that should be accessed directly rather than through the proxy.

### Testing a Proxy for a Single Command

If your network administrator provided a proxy address, you can test it temporarily without saving a persistent configuration:

```bash
git -c http.proxy=http://proxy.example.com:8080 ls-remote origin
```

This setting applies to remotes using HTTP/HTTPS; it does not tunnel SSH remotes through the proxy.

If the temporary command succeeds while the normal command fails, your default proxy configuration may be wrong or unset. The address, port, and authentication method must follow your organization's guidance. Avoid putting usernames/passwords directly in commands because terminal history and logs can record them.

### Reading Proxy Errors

| Message or Symptom | Possible Cause to Check |
| --- | --- |
| `407 Proxy Authentication Required` | The proxy requires authentication; check proxy account or authentication mechanism |
| `Could not resolve proxy` | Proxy hostname cannot be resolved or proxy URL is wrong |
| `Failed to connect to proxy` | Wrong port, proxy is down, or network path to the proxy is blocked |
| `502 Bad Gateway` / `504 Gateway Timeout` | Proxy or gateway did not receive a valid/timely response from the target server |
| HTTPS connection fails only on corporate network | Check TLS-inspecting proxy and corporate CA certificates |

If you need to remove a misconfigured proxy, identify the configuration source first. For example, only if the wrong value lives in global configuration:

```bash
git config --global --unset http.proxy
```

If the setting is in `.git/config`, use `--local`; if it comes from a system file or environment variable, fix it at that exact source. Do not remove the global proxy on a corporate machine just because one repository encountered an error.

Proxies for HTTPS and proxies for SSH are two separate configurations. `http.proxy` does not automatically route SSH traffic through a proxy. For SSH, an organization may require `ProxyJump`, `ProxyCommand`, or a dedicated SSH port in OpenSSH configuration.

## 6. Diagnosing TLS Certificate Errors with HTTPS

When a remote uses HTTPS, Git verifies the TLS certificate to ensure it is connecting to the legitimate server and data has not been tampered with. If the certificate chain is untrusted, the hostname mismatches, or the certificate has expired, Git may report:

```text
SSL certificate problem: unable to get local issuer certificate
SSL: certificate subject name does not match target host name
certificate has expired
```

### Identifying the Cause

1. Check whether the URL has the right hostname and points to the right service.
2. Check the machine's date, time, and time zone. An incorrect clock can cause a valid certificate to appear not yet valid or already expired.
3. Check whether the machine sits behind a TLS-inspecting proxy. Such a proxy may replace the server certificate with one signed by an internal CA.
4. Confirm that the service's root/intermediate CA chain or the corporate CA is installed in the appropriate trust store.
5. Compare Git's result with a browser or `curl.exe`; Git may use a different TLS backend or trust store than the browser.

You can test HTTPS independently of the Git protocol:

```powershell
curl.exe -Iv https://git.example.com
```

On Linux or macOS:

```bash
curl -Iv https://git.example.com
```

This command lets you observe the TLS handshake and the server's HTTP response. An HTTP code such as `200`, `301`, `401`, or `403` still indicates that TLS/HTTP responded; it does not yet prove the account has access to the Git repository. If `curl` succeeds while Git fails, inspect the TLS backend, CA path, and Git configuration.

### Checking Git's TLS Configuration

```bash
git config --show-origin --get http.sslBackend
git config --show-origin --get http.sslCAInfo
git config --show-origin --get http.sslCAPath
git config --show-origin --get http.sslVerify
```

`http.sslVerify` is enabled by default. If a custom CA setting points to a wrong path or an outdated CA file, Git may fail to verify the server. `http.sslBackend` shows the configured TLS backend if any; on Git for Windows, the backend can affect which trust store is used.

If your organization provides an internal CA in PEM format, obtain the file from a trusted administrative source and configure the path per their instructions, for example:

```bash
git config --global http.sslCAInfo /path/to/company-ca-bundle.pem
```

The path above is only an example; Windows can use a path like `C:/certs/company-ca-bundle.pem`. Only configure a CA whose source and fingerprint you have verified. If Git for Windows needs to use the Windows certificate store, ask your administrator about the appropriate backend; do not arbitrarily switch TLS backends.

**Never work around this by disabling certificate verification.** Do not set `http.sslVerify=false`, `GIT_SSL_NO_VERIFY`, or similar options to keep using an unverified connection. That opens the door to server-spoofing attacks and can expose credentials. Fix the hostname, clock, CA, or proxy configuration to restore proper verification.

## 7. Diagnosing SSH Connections

SSH is commonly used when a remote has the form `git@host:group/repository.git`. When an error occurs, split the check into three parts: TCP to the SSH port, host key verification, and user key authentication.

### Checking the SSH URL and Port

```bash
git remote get-url origin
```

Identify the hostname and port from the URL. For an SCP-like URL, the default port is usually `22` unless SSH configuration specifies another port. Check TCP on the corresponding port with `Test-NetConnection` or `nc` from the earlier section.

### Checking the SSH Handshake and Authentication

```bash
ssh -T git@git.example.com
ssh -vT git@git.example.com
```

`ssh -T` attempts authentication without opening an interactive shell. Many Git servers return a successful authentication message while still exiting with a non-zero exit code because the Git account does not grant shell access; read the response text instead of relying solely on the exit code. `-vT` enables verbose logging so you can see which configuration, keys, and authentication methods SSH is using.

Do not post raw SSH logs to public channels. Logs can contain usernames, internal hostnames, key paths, and infrastructure details; mask such data before sharing.

### Checking Keys and ssh-agent

List public keys currently loaded in the agent:

```bash
ssh-add -l
```

If no identity is loaded, you can load the private key created for your account:

```bash
ssh-add ~/.ssh/id_ed25519
```

On Windows PowerShell, the key path is usually under your user profile directory, for example:

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

The key filename may differ. Do not generate or load a new key before confirming which key is required by your organization or Git service. Compare the public key fingerprint against the key registered on your account:

```bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub
```

`Permission denied (publickey)` usually means the server did not accept the offered key. Check that the public key is registered on the right account, the agent has loaded the right key, `IdentityFile` points to the right file, and the account has access to the repository. Never send a private key file (usually without a `.pub` extension) to anyone.

On Windows, if the OpenSSH agent is not running, you can check the service status:

```powershell
Get-Service ssh-agent
```

Enabling or changing the service may require administrator privileges and machine policy approval. Follow device management guidance instead of altering service settings on a company machine on your own.

### Checking Effective SSH Configuration

OpenSSH can read configuration from `~/.ssh/config`, system configuration, command-line flags, and the agent. Use:

```bash
ssh -G git@git.example.com
```

This command prints the effective configuration, including hostname, user, port, and identity file. To configure host-specific settings, you can add an entry to `~/.ssh/config`:

```sshconfig
Host git-company
    HostName git.example.com
    User git
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

Then the remote can use the alias:

```bash
git remote set-url origin git@git-company:team/project.git
ssh -T git-company
```

`IdentitiesOnly yes` tells SSH to prioritize the declared identity instead of trying every key in the agent. Only set it once you have confirmed the exact key to use.

If the network blocks port 22, ask your service provider or network administrator whether an SSH endpoint on an alternate port or SSH over port 443 is supported. Do not assume port 443 accepts SSH; the endpoint and hostname must be documented by the service. If traffic must pass through a bastion/jump host, an administrator can provide a `ProxyJump` or `ProxyCommand` configuration.

### Verifying Host Keys and known_hosts

On the first SSH connection, OpenSSH may ask whether to trust the host key fingerprint. Accept only after comparing the fingerprint against official documentation or with an administrator via a trusted channel.

If you encounter:

```text
Host key verification failed
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
```

the server may have legitimately rotated its host key, DNS may be pointing to a different server, or there may be a risk of connection spoofing. Do not ignore the warning and do not disable `StrictHostKeyChecking` to proceed.

Check the saved record:

```bash
ssh-keygen -F git.example.com
```

Only after verifying the new fingerprint via a trusted source should you remove the old entry so OpenSSH prompts again:

```bash
ssh-keygen -R git.example.com
```

If using a non-default port, the record name may appear in the form `[git.example.com]:2222`; verify and handle the exact hostname/port. Never delete the entire `known_hosts` file just to clear a single warning.

## 8. Distinguishing Connection Errors from Authentication and Repository Permission Errors

Once DNS, TCP, and TLS/SSH are working, Git can still reject operations due to credentials or access permissions.

| Message | What to Check |
| --- | --- |
| `Authentication failed` | Expired/incorrect token, stale entry in credential manager, or authentication mechanism changed |
| `HTTP 401` | Unauthenticated or invalid credentials |
| `HTTP 403` | Possibly authenticated, but account/token lacks permissions or required scope |
| `Repository not found` | Wrong path, repository moved/deleted, or account lacks permission to see a private repository |
| `Permission denied (publickey)` | SSH did not present a key accepted by the server |
| `Could not read from remote repository` | Generic message; check URL, SSH/authentication, and read permissions |
| Push rejected even though fetch succeeds | Account may have read-only access, branch is protected, or server policy denies updates |

With HTTPS, many services no longer permit using regular account passwords directly via Git. Use a mechanism supported by the service, usually a personal access token, OAuth, or a credential manager. Tokens must have the minimum necessary permissions and remain valid. If old credentials are cached in Windows Credential Manager or a credential helper, update/remove the specific server entry according to your credential tool's instructions.

Check which helper is configured without displaying secret contents:

```bash
git config --show-origin --get-all credential.helper
```

Do not run commands that print credentials, do not paste tokens into commands, and do not include tokens, passwords, private keys, or `.env` files in bug reports.

## 9. Using git ls-remote to Verify the End-to-End Git Path

After checking the URL and network, use `git ls-remote` to verify Git can read the reference list from the remote:

```bash
git ls-remote origin
```

If the command returns lines with object IDs and ref names such as `refs/heads/main`, Git has reached the remote and read the ref list. The command does not download the working tree and does not change the current branch.

Some cases require careful interpretation:

- The command succeeding with no lines printed may indicate an empty repository or no matching refs; check the exit code and repository status.
- A successful `ls-remote` proves read capability, not push permissions.
- If the fetch URL and push URL differ, `git ls-remote origin` checks the fetch URL. Verify the push URL separately before concluding both directions work.
- If the command fails, the message usually helps pinpoint whether the failure is in DNS, TLS, SSH, authentication, or the repository path.

You can restrict the list to branches:

```bash
git ls-remote --heads origin
```

This command displays only branch refs. It is useful when you need to confirm branch names on the server without relying on stale local remote-tracking refs.

## 10. Ordered Diagnostic Workflow

When a networked Git command fails, follow this workflow and record the outcome at each layer:

### Step 1: Record the Exact Command and Error Message

Identify whether the error occurs during clone, fetch, pull, or push; identify the remote being used and when the error started. Do not infer solely from the last line if the log has more specific messages above it.

### Step 2: Confirm the Effective URL

```bash
git remote -v
git remote get-url --all origin
git remote get-url --push --all origin
```

Check the hostname, repository path, protocol, port, and any difference between fetch and push URLs. Mask sensitive details before sharing logs.

### Step 3: Check DNS and TCP

On Windows, use `Resolve-DnsName` and `Test-NetConnection`; on Linux, use `getent` or `dig`, while macOS can use `dig` or `nslookup`; check ports with `nc`. If DNS is wrong, resolve VPN or DNS first. If TCP fails to open, check ports, firewall, routes, and proxy with your network administrator.

### Step 4: Check the Security Protocol

- For HTTPS: use `curl.exe -Iv` or `curl -Iv`, and check CA certificates, the system clock, and TLS-inspecting proxies.
- For SSH: use `ssh -vT`, and check the port, effective config, agent, identity, and host key.

### Step 5: Check Authentication and Permissions

Only after HTTPS/SSH connectivity succeeds should you check tokens, credential helpers, public keys, repository permissions, and branch policies.

### Step 6: Re-verify with Git

```bash
git ls-remote origin
git fetch origin
```

If only push fails, check the push URL and write permissions separately. Do not use force push to test connectivity or bypass authentication errors.

## 11. Real-World Scenarios

### Scenario A: Fetch Reports Could Not Resolve Host

```text
fatal: unable to access 'https://git.example.com/team/project.git/':
Could not resolve host: git.example.com
```

Troubleshooting steps:

1. Re-read the URL to rule out a hostname typo.
2. Run `Resolve-DnsName git.example.com` or `dig +short git.example.com`.
3. If it is an internal host, confirm VPN and internal DNS.
4. Once DNS returns an IP, check TCP port 443 and re-run `git ls-remote origin`.

Do not replace the URL with an IP address from a random lookup; the server may use multiple IPs, a CDN, or TLS certificates bound to the hostname.

### Scenario B: HTTPS Returns 407

```text
Received HTTP code 407 from proxy after CONNECT
```

This is a response from the proxy requiring authentication. Confirm the proxy URL, port, account, and authentication method with your network administrator. Check `http.proxy`, URL-specific proxies, and environment variables. Never embed passwords in remote URLs or commit configuration files containing credentials.

### Scenario C: TLS Reports Unable to Get Local Issuer Certificate

```text
SSL certificate problem: unable to get local issuer certificate
```

Check the machine's clock, URL hostname, and whether the network performs TLS inspection. If using a corporate CA, obtain the right CA bundle from your administrator and configure the trust store or `http.sslCAInfo` per their instructions. Keep certificate verification enabled throughout.

### Scenario D: SSH Reports Permission denied (publickey)

```text
git@git.example.com: Permission denied (publickey).
fatal: Could not read from remote repository.
```

Check TCP to the SSH port, run `ssh-add -l`, verify the registered public key fingerprint, and run `ssh -vT git@git.example.com` to see which keys are offered. If you have multiple keys, declare the right `IdentityFile` and consider `IdentitiesOnly yes` in your host configuration.

### Scenario E: Server Host Key Changed

```text
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
```

Stop and verify the new fingerprint through an official change announcement or your administrator. Only after confirming it is a legitimate change should you remove the exact host/port entry with `ssh-keygen -R` and reconnect. Never disable host key checking.

### Scenario F: Fetch Succeeds but Push Is Rejected

A successful fetch only proves read permissions. Check the push URL, write permissions, token scopes, SSH key association with the right account, protected branches, and the project's pull request workflow. A server may allow clone/fetch while blocking direct pushes to `main`.

## 12. Practices to Avoid

- Do not disable TLS verification with `http.sslVerify=false` or `GIT_SSL_NO_VERIFY`.
- Do not disable host key verification with `StrictHostKeyChecking=no` to bypass SSH warnings.
- Do not delete the entire `known_hosts` file when only one host changed; verify the fingerprint and update the specific entry.
- Do not force push to work around connection, DNS, proxy, or authentication errors.
- Do not put tokens or passwords into remote URLs, scripts, logs, or shell history.
- Do not share private keys, tokens, credential files, or unmasked logs containing sensitive data.
- Do not modify DNS, firewall, proxy, or system services on corporate machines without understanding the impact and having authorization.

## 13. Quick Diagnostic Checklist

| Layer | Question | Suggested Command |
| --- | --- | --- |
| URL | Are the remote and fetch/push URLs correct? | `git remote -v` |
| Rewrite | Is an `insteadOf` rule rewriting the URL? | `git config --show-origin --get-regexp '^url\..*\.insteadof$'` |
| DNS | Does the hostname resolve? | `Resolve-DnsName host` / `dig host` |
| TCP | Is port 443 or the SSH port open? | `Test-NetConnection host -Port 443` / `nc -vz host 22` |
| Proxy | What proxy is set in Git or the environment? | `git config --show-origin --get-all http.proxy` |
| TLS | Are the certificate and CA valid? | `curl.exe -Iv https://host` |
| SSH | Are the keys and host key valid? | `ssh -vT git@host`, `ssh-add -l` |
| Git/auth | Can Git read refs from the remote? | `git ls-remote origin` |
| Permission | Do you have write access and the right push URL? | Check push URL, credentials, and repository policies |

## 14. Practice

Perform these steps in a test repository with a remote you are authorized to access:

1. Run `git remote -v`, note the fetch URL and push URL, and identify the protocol and hostname.
2. Use your operating system's DNS tool to resolve the hostname.
3. Test TCP connectivity to the appropriate HTTPS or SSH port.
4. If using HTTPS, run `curl -Iv` against the hostname and observe the TLS handshake; if using SSH, run `ssh -vT` and identify which identity is offered.
5. Run `git ls-remote origin` to check whether Git can read refs.
6. Analyze a sample error message from this lesson: does the error belong to DNS, TCP, proxy, TLS/host key, authentication, or repository permissions?
7. If you must change configuration in a test environment, change only one factor at a time, record before/after values, and verify with `git ls-remote`.

After practicing, explain why a successful `Test-NetConnection` is not enough to conclude Git works, why a successful `git ls-remote` does not prove push permissions, and why you should never disable certificate or host key checks to bypass errors.

## 15. Knowledge Self-Check

1. At which layer does a `Could not resolve host` error occur? Which causes should be checked first?
2. What does `Test-NetConnection host -Port 443` prove, and what does it not prove?
3. Why can a fetch URL and a push URL differ? Which commands inspect each URL?
4. How does an HTTP 407 response differ from HTTP 401?
5. When Git reports `unable to get local issuer certificate`, which factors should be checked?
6. What does `Permission denied (publickey)` suggest checking regarding the agent, identity, and public key?
7. Why should you verify a new host key fingerprint before removing the old entry in `known_hosts`?
8. What does a successful `git ls-remote` tell you about read permissions and push permissions?
9. Why does disabling `http.sslVerify` or `StrictHostKeyChecking` reduce connection security?

## Conclusion

Git connection errors should be diagnosed layer by layer. Verify the URL first, check DNS and TCP next, then inspect proxy settings along with TLS or SSH, and finally address credentials and repository permissions. `git remote` commands, operating system networking tools, `curl`, `ssh -vT`, and `git ls-remote` provide evidence at each step. When changing configuration, fix the exact source of the issue, re-verify the outcome, and always keep TLS certificate verification and SSH host key verification enabled.

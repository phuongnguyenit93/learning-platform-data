# Installing OCI CLI and Configuring Connection Profiles

## 1. Objectives and Scope

The OCI Command Line Interface (OCI CLI) is the command-line tool for calling Oracle Cloud Infrastructure APIs. You can use the CLI to inspect resources, gather operational metadata, and build repeatable automation steps.

This lesson belongs to the **Account and Lab Setup** chapter of the **CLOUD_PROVIDERS_ORACLE** module. A properly configured CLI connection provides the foundation for practicing tenancy, compartments, IAM, VCN, Compute, storage, and Oracle database services with proper permissions, the right environment, monitoring, and cost controls.

After this lesson, you will be able to:

- Install OCI CLI for your operating system and verify which executable is invoked.
- Distinguish API signing keys from SSH keys, Console passwords, and session tokens.
- Create a connection profile with the right user, tenancy, private key, and region.
- Explicitly select a profile and recognize when configuration is overridden by environment variables.
- Test connectivity using read-only commands, then separate installation, authentication, and authorization errors.
- Manage credentials on your practice machine and revoke them when no longer needed.

This lesson does not require creating instances, VCNs, buckets, or databases to test connectivity. The service calls below only retrieve metadata; never use deploying billable resources as your first connectivity test.

## 2. Understanding the Flow of an OCI CLI Command

A typical CLI command follows this structure:

~~~text
oci <service> <resource> <action> <options>
~~~

Example:

~~~text
oci compute instance list --compartment-id <COMPARTMENT_OCID>
~~~

In this example, `compute` selects the service, `instance` selects the resource type, and `list` selects the action. Authentication details and region come from the command's effective configuration. [Oracle: Using the CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliusing.htm)

~~~mermaid
flowchart LR
    S["Shell and command arguments"] --> C["Effective configuration"]
    P["Profile in config"] --> C
    E["Environment variables"] --> C
    C --> A["Authenticate via chosen method"]
    A --> O["OCI service endpoint"]
    O --> I["IAM permission check"]
    I --> R["Result or error"]
~~~

Installing the binary and authenticating successfully are two separate milestones. Successful authentication also does not prove the user has permission to manage every resource.

## 3. Preparing Information Before Configuring

You need an OCI account authorized for practice and must know which administrator handles access permissions. Do not use a tenancy-wide administrator account merely to avoid troubleshooting missing permissions.

| Information | Meaning and where to check |
| --- | --- |
| Tenancy OCID | Tenancy identifier; obtained from tenancy details in the Console |
| User OCID | Identifier of the user making requests; obtained from that exact user's details page |
| Active domain and user | Helps pick the right account when the tenancy has multiple Identity Domains |
| Lab region | Target region code to call; cross-check against subscribed and permitted regions |
| Compartment OCID | Resource scope permitted for inspection in subsequent steps |
| Authentication method | API key or temporary login session per environment rules |
| IAM permissions | Read or practice actions granted |

An OCID is not a display name. Do not replace `user` in the config with an email address, username, or domain name. Likewise, `tenancy` must be the tenancy OCID, not the lab compartment's OCID.

A region in config specifies the target service endpoint; it does not automatically subscribe to the region, copy resources, or grant extra access.

### 3.1. Credential Types to Distinguish

| Component | What is it used for? | Does not substitute for |
| --- | --- | --- |
| Console password and MFA | Interactive sign-in per account settings | API signing key for API key authentication |
| API signing key | Signs API requests; public key registered to user, private key kept on client | SSH key for OS login |
| SSH key | Authenticates into servers per SSH config | OCI API signing key |
| Session token | Authenticates CLI during a temporary session | Long-term credentials for indefinite use |
| Service auth token | Supports eligible integrations | Private key in an API key profile |

OCI API signing keys use a PEM-formatted RSA key pair, minimum 2048 bits; do not upload an `ssh-rsa` public key under API Keys as if they were the same format. [Oracle: Required Keys and OCIDs](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm)

## 4. Installing OCI CLI

Choose one primary installation method for your machine. Mixing multiple installations without managing `PATH` can cause your terminal to invoke a different version than the one you just upgraded.

Oracle provides installation instructions for Windows, macOS, and Linux/UNIX. Use official documentation and installers, and verify requirements for the version you are installing rather than copying hardcoded version numbers from a lesson. [Oracle: OCI CLI Quickstart](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm)

### 4.1. Windows: Using MSI

For beginners on Windows, you can use the MSI installer linked from the Quickstart page:

1. Open the Windows installation section in Oracle's documentation.
2. Follow the link to the official MSI installer and download the matching package.
3. Run the installer, confirm the installation folder, and complete the prompted steps.
4. Close and reopen PowerShell to pick up `PATH` changes.
5. Check the command and version:

~~~powershell
Get-Command oci
oci --version
oci --help
~~~

`Get-Command oci` shows where PowerShell finds the executable. If the machine already has multiple installations, view all matches:

~~~powershell
Get-Command oci -All
~~~

Choose and maintain a single installation according to your machine's workflow; do not delete system directories merely because one `PATH` entry is off.

If you choose the PowerShell script installation instead of MSI, follow the PowerShell branch in the official docs and your device policy. There is no need to apply both methods for the same exercise.

### 4.2. macOS: Using Homebrew

If the machine already uses Homebrew under an approved workflow:

~~~bash
brew update
brew install oci-cli
oci --version
command -v oci
~~~

When upgrading a Homebrew installation, continue using Homebrew to manage it rather than overwriting it via another installation method.

### 4.3. Linux/UNIX: Using the Official Installer

You can download the installer to inspect it first and then run it:

~~~bash
curl --fail --location https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh --output /tmp/oci-cli-install.sh
less /tmp/oci-cli-install.sh
bash /tmp/oci-cli-install.sh
~~~

Follow the installer prompts, noting the install directory and binary location. Open a new shell if the installer updated `PATH`, then verify:

~~~bash
command -v oci
oci --version
oci --help
~~~

If your organization already distributes OCI CLI via managed packages or images, use that method. Do not assume you need to reinstall simply because you saw another installer guide.

### 4.4. Dependency Environments and Network-Restricted Machines

OCI CLI has its own dependencies. For manual or offline installs, follow Oracle's corresponding guide; avoid installing into shared software environments where dependency conflicts may arise. Oracle recommends using the installer or an isolated environment instead of installing the CLI into the system Python. [Oracle: Manual and Offline Installations](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/climanualinst.htm)

If your terminal does not recognize `oci`, resolve the installation or `PATH` first. There is no need to create new API keys, edit policies, or create cloud resources at this step.

## 5. Choosing an Authentication Method

Two common practice options are API keys and session tokens:

| Option | Characteristics | Suitable scenarios |
| --- | --- | --- |
| API key | Client holds private key; public key registered to user | Protected practice workstation needing a reusable profile per workflow |
| Session token | Sign in for a temporary session; handle expiration when needed | Interactive operations and environments preferring browser-based login |

OCI also provides instance principals and resource principals for supported workloads. Do not copy personal credentials onto Compute instances or pipelines by default when an appropriate workload identity can be used. [Oracle: OCI SDK Authentication Methods](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdk_authentication_methods.htm)

In this lesson, the API key section creates profile `LAB_API`; the session token section uses a separate profile `LAB_SESSION`. Choose whichever method your environment permits—you do not need to set up both to prove the CLI works.

## 6. Creating an API Key Profile

### 6.1. Prepare Storage Outside Source Code

The standard configuration directory is `.oci` in your user home directory. On Windows PowerShell:

~~~powershell
$ociDirectory = Join-Path $env:USERPROFILE '.oci'
$ociConfigPath = Join-Path $ociDirectory 'config'
New-Item -ItemType Directory -Path $ociDirectory -Force
~~~

On Linux/macOS:

~~~bash
mkdir -p "$HOME/.oci"
chmod 700 "$HOME/.oci"
~~~

Never place private keys in repositories, shared folders, or application images. The config file should not contain plaintext secrets, yet still requires protection because it describes your identity and credential paths.

### 6.2. Register the Public Key for the Right User

A convenient workflow uses the Console:

1. Select the exact user in the exact Identity Domain.
2. Open that user's API Keys section.
3. Add an API key according to account permissions.
4. If letting the Console generate the key pair, download the private key and move it to your chosen protected directory.
5. If you already have a suitable key pair, upload only the **public key** to the Console.
6. Copy the provided configuration snippet to verify user, tenancy, and fingerprint.

The `key_file` path in the snippet must be updated to point to the actual private key location on your machine. Never upload a private key where a public key is requested. [Oracle: Required Keys and OCIDs](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm)

An alternative is running the interactive setup wizard:

~~~text
oci setup config
~~~

This command helps generate a local config. If generating a new key through the wizard, you must still complete registering the matching public key on the right OCI user. Having a PEM file on disk does not prove the key is registered. Review each prompt before writing into a config that already holds important profiles. [Oracle: oci setup config](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/setup/config.html)

### 6.3. Fields in a Profile

| Field | Contents |
| --- | --- |
| `user` | OCID of the user signing requests |
| `tenancy` | Tenancy OCID for the configuration |
| `fingerprint` | Fingerprint of the public key registered to the user |
| `key_file` | Path to the matching private key on disk |
| `region` | Default region when a command omits another value |

The config uses INI syntax with profile names in square brackets. The default config file is `~/.oci/config`; on Windows PowerShell, this is usually the `.oci` folder under `%USERPROFILE%`. [Oracle: SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm)

Example for Windows:

~~~ini
[LAB_API]
user=<USER_OCID>
fingerprint=<PUBLIC_KEY_FINGERPRINT>
tenancy=<TENANCY_OCID>
region=<LAB_REGION>
key_file=C:/Users/YourName/.oci/lab_api_key.pem
~~~

Equivalent example for Linux/macOS:

~~~ini
[LAB_API]
user=<USER_OCID>
fingerprint=<PUBLIC_KEY_FINGERPRINT>
tenancy=<TENANCY_OCID>
region=<LAB_REGION>
key_file=~/.oci/lab_api_key.pem
~~~

All values inside `<...>` are placeholders and must be replaced with real data. `YourName` must also be replaced with your actual user directory. Do not wrap the entire `key_file` path in quotes as if passing a shell argument; it is an INI file value.

The name `LAB_API` is a local name you choose. It does not create a user, group, or policy in OCI and does not narrow the account's permissions on its own.

### 6.4. Protect the Private Key

On Linux/macOS, after confirming the exact file locations:

~~~bash
chmod 600 "$HOME/.oci/config"
chmod 600 "$HOME/.oci/lab_api_key.pem"
~~~

On Windows, inspect permissions under Properties → Security for the folder and private key; restrict read access to your account and organization-approved administrative principals. Do not treat `chmod` commands as a mechanical substitute for Windows ACLs.

If the private key is encrypted with a passphrase, supply the passphrase via a supported runtime mechanism aligned with your machine's workflow. Never record passphrases in submissions, command history, or repositories. The `pass_phrase` field in config is marked deprecated; Oracle advises against storing secrets in the config file. [Oracle: SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm)

Console passwords and browser MFA cannot be substituted for a private key decryption passphrase. They are completely separate mechanisms.

## 7. Configuring a Session Token

On machines with a browser and an environment allowing interactive login:

~~~text
oci session authenticate
~~~

Follow the prompts to choose a region, sign into the right tenancy/domain, and name the session profile, such as `LAB_SESSION`. Keep the generated files intact as guided by the tool; do not copy an API key profile and paste an arbitrary token string.

Validate the session:

~~~text
oci session validate --profile LAB_SESSION --auth security_token
~~~

Run a read-only command using the session:

~~~text
oci os ns get --profile LAB_SESSION --auth security_token
~~~

For session tokens, you must specify `--auth security_token` or set `OCI_CLI_AUTH` accordingly. Selecting a profile named `LAB_SESSION` alone does not guarantee the CLI uses the right auth type. [Oracle: Token-based Authentication for the CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clitoken.htm)

Sessions expire. When a session is no longer valid, handle refresh or re-authentication according to session capabilities and Oracle docs. Do not manually edit token contents or treat interactive sessions as indefinite credentials for background jobs.

Headless machines without a browser require a different pre-configured authentication workflow. Do not interpret `--no-browser` as bypassing authentication requirements.

## 8. Selecting Profiles and Avoiding Environment Mix-Ups

### 8.1. Pass the Profile Explicitly

With an API key:

~~~text
oci os ns get --profile LAB_API --auth api_key
~~~

If the config sits outside the default path, specify the file explicitly. PowerShell example:

~~~powershell
$ociConfigPath = Join-Path $env:USERPROFILE '.oci/config'
oci os ns get --config-file $ociConfigPath --profile LAB_API --auth api_key
~~~

This is the connection config file. It differs from `oci_cli_rc`, a separate CLI options file for parameter defaults, aliases, and convenience settings. You normally do not need to edit `oci_cli_rc` to establish your first connection. [Oracle: Configuring the CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliconfigure.htm)

### 8.2. Multiple Profiles Do Not Mean Multiple Permission Sets

You can maintain multiple profiles for different users, tenancies, or regions. When adding extra profiles, populate all required fields explicitly so they are easy to audit and do not unexpectedly inherit default values.

| Illustrative profile name | Intended use | What must be verified |
| --- | --- | --- |
| `LAB_API` | Practice user with API key | User, tenancy, key, and lab permissions |
| `LAB_SESSION` | Temporary interactive session | Logged-in user, expiration, and auth type |
| `LAB_OTHER_REGION` | Practice in another permitted region | Target region and resources there |

Naming a profile `READONLY` does not turn a privileged user into a read-only user. Two profiles pointing to the same user still exercise that user's effective permissions, unless the authentication method and context resolve to a different principal.

### 8.3. Configuration Precedence Order

For settings with corresponding overrides, OCI CLI prioritizes:

1. Options passed directly on the command line.
2. Environment variables.
3. Values in the config file.

Common variables include `OCI_CLI_PROFILE`, `OCI_CLI_CONFIG_FILE`, `OCI_CLI_REGION`, `OCI_CLI_AUTH`, `OCI_CLI_USER`, `OCI_CLI_TENANCY`, and `OCI_CLI_KEY_FILE`. Other variables can hold private key content or passphrases. [Oracle: CLI Environment Variables](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clienvironmentvariables.htm)

For instance, if a profile specifies one region while `OCI_CLI_REGION` in your shell selects another, a command omitting `--region` can hit an unintended target.

On PowerShell, list only the **names** of active OCI environment variables during initial inspection:

~~~powershell
Get-ChildItem Env:OCI_CLI_* | Select-Object -ExpandProperty Name
~~~

Do not print all environment variable values to send to support: environment variables can contain private keys or passphrases. Inspect relevant variables privately within an environment you control.

To set defaults for the current PowerShell session:

~~~powershell
$env:OCI_CLI_PROFILE = 'LAB_API'
$env:OCI_CLI_AUTH = 'api_key'
~~~

On Bash:

~~~bash
export OCI_CLI_PROFILE=LAB_API
export OCI_CLI_AUTH=api_key
~~~

These variables shorten interactive commands, but when writing guides or running sensitive operations you should still pass profile, auth, and region explicitly. If you switch authentication methods, check old environment variables rather than only changing the profile name.

## 9. Layered Connectivity Testing

### 9.1. Layer 1: Local Executable

~~~text
oci --version
oci --help
~~~

These two commands confirm the binary runs and displays help. They do not verify that keys are valid, the user exists, or API endpoints are reachable.

### 9.2. Layer 2: A Simple Service Request

With an API key:

~~~text
oci os ns get --profile LAB_API --auth api_key
~~~

Output looks like this illustrative response:

~~~json
{
  "data": "tenancy-namespace"
}
~~~

The actual value is provided by your tenancy. Getting the namespace does not create a bucket or upload sample data to Object Storage.

When the command succeeds, cross-check the namespace or known tenancy details to avoid testing against the wrong environment. This result proves only that the specific request succeeded; it does not prove the user holds full permissions across Compute, VCN, or Database.

### 9.3. Layer 3: Permissions in the Lab Compartment and Region

Suppose the user has been granted permission to read instances in the lab compartment. PowerShell example:

~~~powershell
$labCompartmentId = '<COMPARTMENT_OCID>'
$labRegion = '<LAB_REGION>'
oci compute instance list --compartment-id $labCompartmentId --region $labRegion --profile LAB_API --auth api_key --limit 5
~~~

Replace placeholders before running. With a session token, use profile `LAB_SESSION` and `--auth security_token`.

Distinguish these outcomes:

- Instance list returned: the read call retrieved data in the selected scope.
- Empty list: that compartment/region may simply have no instances yet; an absence of resources is not a connectivity failure.
- Authentication error: check credentials and auth method.
- Authorization or not-found error: check policies, OCID, and resource scope.

`--limit 5` retrieves only a subset of items for testing; do not treat it as a complete tenancy inventory. Do not broaden tenancy-wide admin rights just to make this read test succeed.

### 9.4. Record Minimal Evidence

You may record the CLI version, profile name, auth method, region, lab compartment, timestamp, and succeeded command type. Never include private keys, passphrases, or session tokens in reports.

For failed requests, the request ID can help when coordinating with support. Share only output stripped of unnecessary data and credentials.

## 10. Troubleshooting Common Errors

| Symptom | Cause category to check | How to handle |
| --- | --- | --- |
| `oci` not found | Installation or `PATH` | Open a new terminal, check executable path and install method |
| Unexpected version | Multiple CLI installations | Check which binary the shell actually invokes |
| Requested profile missing | Wrong config file or section name | Check `--config-file`, environment variables, and profile name |
| Missing config field | Incomplete profile data | Verify user, tenancy, fingerprint, key file, and region for the auth type |
| Cannot read private key | Wrong path, format, or file permissions | Confirm valid PEM file and read access for the CLI account |
| `NotAuthenticated` or signature error | Key/user/fingerprint mismatch, revoked key, clock skew, or wrong auth | Cross-check credential set, key status, system clock, and auth type |
| Session expired | Token no longer valid | Validate session, then refresh or re-authenticate per procedure |
| `NotAuthorizedOrNotFound` | Missing permissions, wrong OCID, or wrong scope | Verify permissions and target; do not assume the resource was deleted |
| Expected resources missing | Wrong compartment, region, tenancy, or pagination | Check the entire scope of the command |
| Timeout, DNS, or proxy error | Network path from client to endpoint | Check network, DNS, proxy, and endpoint config |
| Certificate verification error | Trust store or TLS-inspecting proxy | Use an organization-approved CA bundle; never disable TLS verification |

### 10.1. Do Not Confuse Authentication with Authorization

Registering a public key does not grant extra IAM policies. If a request is already authenticated but denied permission, generating more API keys will not solve the issue.

Conversely, granting broad policies cannot fix a mismatched key pair. Check in order: binary → config → credentials → connectivity → permissions → target resource.

### 10.2. Corporate Proxies and CAs

The CLI supports proxy and certificate bundle configuration. For example, once provided a proxy address and CA file by your infrastructure team:

~~~powershell
$env:HTTPS_PROXY = 'http://proxy.example.internal:8080'
$env:OCI_CLI_CERT_BUNDLE = 'C:/Certificates/company-ca-bundle.pem'
~~~

These are illustrative values, not universal defaults for every network. Never put proxy passwords in shared documents or command history. Never point endpoints at an untrusted host to try to work around errors. [Oracle: Configuring the CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliconfigure.htm), [Oracle: CLI Environment Variables](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/clienvironmentvariables.htm)

### 10.3. Use Debug Output Controlledly

When deeper investigation is needed, check `oci --help` for the debug options of your installed version. Debug output can include metadata, request payloads, and environment details; inspect it before sharing. Never commit full debug logs to public code repositories.

## 11. Managing Profiles and Credentials After Connecting

### 11.1. Keep Lab Scope Clear

Before running resource-mutating commands in later lessons, verify four factors: **profile, auth, region, and compartment**. The right profile paired with the wrong compartment can still modify resources outside your intended scope if the user holds permissions there.

A working connection profile is also not a cost-control mechanism. You still need proper permissions and resource management procedures when deploying Compute or Databases. For this setup lesson, stopping at the read checks above is sufficient.

### 11.2. Rotating and Revoking API Keys

When rotating a key under standard procedure:

1. Generate and register a new public key for the right user.
2. Place the new private key in a protected location.
3. Update a new profile or update the matching fingerprint/key pair.
4. Verify with read-only commands and check dependent tools.
5. Revoke the old public key in OCI once cutover is complete.
6. Dispose of the old private key copy according to your organization's retention policy.

If key compromise is suspected, prioritize incident response and revocation commensurate with risk; do not keep the old key active merely for transition convenience.

Deleting the config file on your laptop does not revoke the public key registered in OCI. Conversely, revoking the key in OCI does not delete private key copies on other machines. Manage both sides.

### 11.3. Cleaning Up the Lab Environment

If a profile is no longer needed, confirm nothing still uses it before removing the config and related credentials. In a shell where defaults were exported, clear the exercise's variables from the current session:

~~~powershell
Remove-Item Env:OCI_CLI_PROFILE -ErrorAction SilentlyContinue
Remove-Item Env:OCI_CLI_AUTH -ErrorAction SilentlyContinue
~~~

On Bash:

~~~bash
unset OCI_CLI_PROFILE
unset OCI_CLI_AUTH
~~~

Remove only configurations belonging to this exercise or explicitly approved for removal. Do not delete the entire `.oci` directory if it holds profiles used for other work.

## 12. Comprehensive Practice and Completion Criteria

Follow this sequence:

1. Install the CLI using a method suited to your machine and note the executable path.
2. Verify `oci --version` and confirm help opens.
3. Select API key or session token per environment requirements.
4. Create a dedicated lab profile; cross-check the right identity and tenancy.
5. Verify credential files live outside repositories and have restricted access permissions.
6. Check environment variables that could alter effective configuration.
7. Run the Object Storage namespace lookup with explicit profile and auth flags.
8. If lab permissions are granted, list instances in the target compartment/region without creating resources.
9. Record the result of each test and the cause if any step cannot yet be verified.
10. Identify how to revoke credentials once practice ends.

| Milestone | Evidence of completion |
| --- | --- |
| CLI runs | Actual version and executable path recorded |
| Right profile selected | Command explicitly passes profile/config and matching auth method |
| Credentials match | For API key: matching user, fingerprint, and private key; for token: valid session |
| Service connectivity works | A read-only call returns valid output for the expected tenancy |
| Lab scope is accurate | Region and compartment verified; read output explained accurately |
| Credentials protected | Not present in source code or reports; read access restricted |
| Cleanup plan defined | Know how to revoke keys or end sessions and clean up lab config |

If permissions to read resources are missing, clearly note that milestone as unverified and coordinate with your administrator within lab scope. Do not treat installation success as completing every milestone, and do not work around it by borrowing someone else's admin credentials.

The goal is an OCI CLI capable of calling the right service with the **right identity, right authentication method, and right practice scope**. With this foundation, subsequent lessons can safely deploy infrastructure and automation while retaining control over permissions, costs, and audit trails.

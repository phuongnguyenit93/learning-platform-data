# API Signing Keys, Auth Tokens, and Customer Secret Keys

In the **IAM Identity and Access Management** chapter of the **CLOUD_PROVIDERS_ORACLE** module, learners need to pick the right credentials for each tool before deploying or automating infrastructure. OCI CLI calling management APIs, Docker accessing Container Registry, and a backup tool using the S3 protocol may all represent the same IAM user while using different credential types.

This lesson focuses on those three credential types and how to operate them in a least-privilege OCI environment. The same principles for protecting, rotating, and revoking credentials apply to Compute deployment pipelines, VCN, storage, and Oracle database backup workflows.

## Learning Objectives

After this lesson, you will be able to:

- Choose an API signing key, auth token, or customer secret key based on the API the client uses.
- Explain the difference between identity authentication and resource access permissions.
- Configure a read-only test for each credential type.
- Design procedures for key rotation, secret-leak revocation, and impact assessment.

## 1. Choose Credentials from the Client Protocol

Before creating a key, determine which endpoint the client calls and which authentication mechanism it supports. Never choose a credential simply because an application UI has a field labeled `API key` or `Password`.

| Credential Type | Typical Client or Protocol | Secret Component to Protect | Primary Usage |
| --- | --- | --- | --- |
| API signing key | OCI CLI, OCI SDK, OCI APIs using request signing | RSA private key | Signs requests; the matching public key is registered on the IAM user |
| Auth token | Docker accessing OCI Container Registry; compatible Swift clients | Oracle-generated token string | Supplies the token via the login mechanism supported by the service |
| Customer secret key | Tools calling Object Storage's Amazon S3 Compatibility API | Secret Key in the Access Key/Secret Key pair | Uses the key pair to compute signatures under the S3 protocol |

Oracle distinguishes these credentials from Console passwords, OAuth 2.0 client credentials, and database login credentials. An API signing key is also distinct from SSH keys used to log in to Compute machines. Therefore, credential rotation must be grounded in the target API and the actual identity in use. See [Working with User Credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/usercred/usercredentials.htm).

Example selections for an operations team:

| Need | Choice for This Scenario | Points to Clarify Before Issuing |
| --- | --- | --- |
| Engineer runs OCI CLI from an admin workstation | API signing key of an authorized user | Compartment, environment, and required operations |
| Build runner pulls a private image from OCIR | Auth token of a dedicated task identity | Repository and pull permissions |
| Backup software only supports S3 | Customer secret key | Bucket, endpoint, region, and read/write operations |

If a workload supports a platform-provided authentication mechanism suitable for the target service, evaluate that mechanism before distributing long-lived secrets. The hands-on sections below assume the integration genuinely requires one of these three user credential types.

## 2. Credentials Prove Identity; IAM Decides Permissions

A successful request requires multiple conditions to hold simultaneously:

```text
Client sends to the right endpoint and protocol
        ↓
Valid credential authenticates the identity
        ↓
IAM authorizes the operation on the target resource
        ↓
Service processes the request
```

Creating a credential does not grant access to every resource. The user still needs permissions appropriate for the service. When multiple credentials belong to the same user, evaluate the user's entire permission set rather than treating each key's description as a permission boundary. See [User Credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/usercredentials.htm).

For example, creating two API keys described as `dev` and `prod` under the same user does not separate permissions between the two environments. If the goal is limiting the blast radius of a test environment, the design should use identities and policies scoped accordingly.

In this lesson's example, the administrator prepares a bucket `iam-credentials-lab`, a non-sensitive object, and a read-only group beforehand. The illustrative policy uses OCIDs to avoid confusing same-named groups across identity domains:

```text
Allow group id ocid1.group.oc1..REPLACE_GROUP_OCID to read objects in compartment id ocid1.compartment.oc1..REPLACE_COMPARTMENT_OCID where target.bucket.name = 'iam-credentials-lab'
```

Replace both OCIDs with real values and ensure the user belongs to the right group. This policy illustrates reading objects in a known bucket; it does not grant permission to create buckets or manage Compute. If a tool also needs to list buckets, evaluate the corresponding permission separately instead of opening all of `object-family`. See [Object Storage Policy Templates](https://docs.oracle.com/en-us/iaas/Content/Identity/policiescommon/commonpolicies.htm).

## 3. API Signing Keys: Signing OCI Requests with Asymmetric Keys

### 3.1. Public Key, Private Key, and Fingerprint

For API signing, OCI requires a PEM-format RSA key pair of at least 2048 bits. The public key is added to the IAM user profile; the client retains the private key for signing. The fingerprint identifies the registered public key. API signing key pairs must be managed separately from SSH keys used to log in to VMs. See [Required Keys and OCIDs](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm).

Distinguish these values during configuration handover:

| Value | Role | How to Handle |
| --- | --- | --- |
| User OCID | Identifies the user calling the API | Verify the right user and identity domain |
| Tenancy OCID | Identifies the tenancy | Avoid accidentally copying configs across environments |
| Fingerprint | Identifies the public key | Cross-check against the key on the user profile |
| Public key | Portion registered in OCI | Can be provided to the administrator for registration |
| Private key | Generates signatures | Provide only to authorized processes or individuals |

OCIDs and fingerprints cannot replace the private key. Even so, share them only on a need-to-know basis since configs also reveal system structure and identities.

### 3.2. Signatures Bound to Request Content

OCI request signing uses RSA-SHA256. The client builds a signing string from request components, then places the signature into the `Authorization` header under the `Signature` scheme. For a `GET` with no body, minimal components include `(request-target)`, `host`, and `date` or `x-date`.

Altering the path or query order after signing, or letting the client clock drift by more than five minutes, can cause authentication to fail. Methods with bodies have additional header requirements and per-API exceptions, so standard practice is letting the OCI SDK/CLI perform signing. See [Request Signatures](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/signingrequests.htm).

### 3.3. Preparing and Configuring a Profile

Learner workflow:

1. Open the right user profile in the Console and locate API keys or Tokens and keys.
2. Generate a key pair or register the public key of an existing pair.
3. Save the private key in a location readable only by the account running the client.
4. Copy the suggested configuration and double-check user, tenancy, and fingerprint.
5. Use a dedicated profile for the lab to avoid mixing environments.

Example in the user's OCI config file:

```ini
[ORACLE_LAB]
user=ocid1.user.oc1..REPLACE_USER_OCID
fingerprint=REPLACE_PUBLIC_KEY_FINGERPRINT
tenancy=ocid1.tenancy.oc1..REPLACE_TENANCY_OCID
region=ap-singapore-1
key_file=C:/Users/REPLACE_LOCAL_USER/.oci/oracle_lab_api_key.pem
```

On Windows PowerShell, the default config file path is `$Env:UserProfile\.oci\config`; on Linux and macOS it is typically `~/.oci/config`. Update `key_file` to the actual path on the client machine. If the private key has a passphrase, supply it through a runtime mechanism supported by the client; avoid storing the passphrase next to the private key in config. Config fields and profiles are described in [SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm).

Never place private keys into source code, container images, shared sync folders, or ticket comments. On Windows, check file ACLs; on Unix-like systems, restrict file read permissions to the required account. Also check for leftover copies in your downloads directory after generating keys in a browser.

### 3.4. Testing with a Read-Only Operation

Assume OCI CLI is installed, the profile is correct, and the sample bucket resides in Singapore. The command below is for the learner's terminal; replace the namespace with your tenancy's value:

```powershell
oci os object list --profile ORACLE_LAB --namespace-name 'REPLACE_NAMESPACE' --bucket-name 'iam-credentials-lab' --limit 5
```

The expected output is an object listing response, which may be an empty list if the bucket contains no objects yet. Evidence to retain includes timestamp, profile, bucket, and request ID if available. Do not use creating a new resource as the first test for a read-only credential.

If it fails, check the user OCID, fingerprint, private key, and endpoint first. Once authentication succeeds, cross-check policies against the specific operation. Never open tenancy-wide admin permissions to mask a key file path error.

## 4. Auth Tokens: Secrets for Service-Supported Login Flows

### 4.1. Use Precise Terminology Instead of Just "Token"

An auth token is an Oracle-generated string for supported integrations such as Swift. It is managed separately from API signing keys. When documenting integrations, specify the exact credential type rather than writing "token," since operations teams might be referring to completely different mechanisms. See [Security Credentials](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/credentials.htm).

Example of sufficiently clear handover details:

```text
Task: pull an approved image version
Service: OCI Container Registry
Identity: user dedicated to pull jobs
Credential: OCI auth token
Scope: application repository in the test compartment
Runtime secret source: secret store approved by the admin team
```

Never paste the token value into this handover document. Recipients need to know how to fetch the secret through controlled channels and who is responsible for rotating it.

### 4.2. Container Registry Login Example

In the Auth Tokens section of the user profile, generate a token and immediately store it in a secret store. The token value is displayed only at creation time. With OCIR, the login username typically follows `<namespace>/<username>`; some federated configurations use `<namespace>/<domain-name>/<username>`. Verify the exact format for your tenancy and user per [Pushing Images Using the Docker CLI](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrypushingimagesusingthedockercli.htm).

Example using the Singapore region:

```powershell
docker login ocir.ap-singapore-1.oci.oraclecloud.com
```

When prompted, enter the username per the format above and paste the auth token at the password prompt. Then try pulling an existing private image you are authorized to access:

```powershell
docker pull ocir.ap-singapore-1.oci.oraclecloud.com/REPLACE_NAMESPACE/team/demo:lab
```

A successful login does not prove the user can pull from every repository. For pull-only tasks, administrators can design a `read repos` policy in the appropriate compartment. Pushing requires a different permission set, so avoid granting `manage repos` by default just to pull images. See [Policies to Control Repository Access](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registrypolicyrepoaccess.htm).

In CI, pass tokens from a secret store to the client via mechanisms that avoid exposing secrets in command-line arguments and logs; Docker supports reading passwords via standard input. Runner machines must also control where Docker persists login credentials. Do not assume masking a variable in the CI UI is enough if a script prints the entire environment.

When finishing the lab session, you can clear local Docker login state:

```powershell
docker logout ocir.ap-singapore-1.oci.oraclecloud.com
```

This command cleans client state. If a token must stop working immediately, revoke the token in OCI and verify with a fresh login attempt.

## 5. Customer Secret Keys: Key Pairs for the S3 Compatibility API

### 5.1. Access Key and Secret Key

Customer secret keys serve the Amazon S3 Compatibility API of OCI Object Storage. Both the Access Key and Secret Key must be supplied to the S3 client. The Access Key identifies the credential, while the Secret Key is the secret used to compute signatures; do not confuse them with Vault data encryption keys.

In a connection profile, label fields clearly:

| S3 Client Field | Value to Obtain from OCI |
| --- | --- |
| Access key ID | Access Key of the customer secret key |
| Secret access key | Corresponding Secret Key |
| Endpoint | Object Storage S3 compatibility endpoint |
| Region | Target bucket region |
| Bucket | Target bucket name |

The Secret Key cannot be viewed again after creation. If lost, plan to rotate the credential and update clients rather than trying to derive it from the Access Key. See [Object Storage Amazon S3 Compatibility API](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm).

### 5.2. Testing with AWS CLI Against an OCI Endpoint

This example assumes you already have AWS CLI, a sample bucket, and a customer secret key pair for the right user. AWS CLI acts as an S3 protocol client in this scenario; the target data still resides in OCI.

Create a dedicated profile via interactive input:

```powershell
aws configure --profile OCI_S3_LAB
```

When prompted, enter the newly created Access Key and Secret Key; choose region `ap-singapore-1` and output `json`. This configuration stores credentials locally, so restrict read permissions on the credentials file and never commit it to a repository.

Set path-style bucket addressing for this example:

```powershell
aws configure set s3.addressing_style path --profile OCI_S3_LAB
```

Then list up to five objects:

```powershell
aws --profile OCI_S3_LAB --region ap-singapore-1 --endpoint-url 'https://REPLACE_NAMESPACE.compat.objectstorage.ap-singapore-1.oci.customer-oci.com' s3api list-objects-v2 --bucket 'iam-credentials-lab' --max-keys 5
```

This is the public path-style endpoint pattern documented by Oracle. For other realms or endpoint configurations, use the corresponding official endpoint. Keep the signing region aligned with the target region; the Amazon S3 Compatibility API does not support Signature Version 2. See [Configuring S3 Compatibility Applications](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm).

Test only against a known bucket in the lab. Before putting the same configuration into real backup software, add functional tests for required operations: writing new objects, restore reads, multipart handling, and product-specific compatibility requirements. Never assume an entire backup workflow works from a single successful list call.

## 6. Operating the Credential Lifecycle

### 6.1. Record Owners and Usage Locations

Maintain a secret-free inventory for every credential:

| Attribute | Example Inventory Data |
| --- | --- |
| Identity | User for the test backup job |
| Credential type | Customer secret key |
| Identifier | Access Key or fingerprint depending on type |
| Owner | Backup administration team |
| Active clients | Standby runner and primary runner |
| Intended scope | Test bucket in the approved compartment |
| Operational milestones | Creation date, planned rotation date, last check |
| Revocation plan | Executor, config update locations, and post-revocation test |

The client list must include infrequently run jobs: data restores, month-end jobs, and standby machines. These clients are easily overlooked during key rotation because primary systems keep running normally.

Oracle specifies maximum concurrent limits of three API keys, two auth tokens, and two customer secret keys per user. Auth tokens and customer secret keys do not expire automatically; operations teams must proactively schedule rotation and revocation. Managing credentials for other users also requires appropriate IAM permissions, not just permissions on the data compartment. See [Managing User Credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcredentials.htm).

### 6.2. Rotating Keys with an Overlap Window

Illustrative scenario: backup software runs on two runners and needs a customer secret key rotation. The operational goal is for both runners to keep completing jobs throughout the transition.

1. **List everywhere the old key is used.** Check primary runner, standby runner, and restore test jobs.
2. **Ensure an open credential slot.** If already at the limit, determine which credential can genuinely be retired before creating another.
3. **Create the new credential.** Store the secret via a controlled channel and record its identifier in the inventory.
4. **Update one test client.** Verify read/write within the job's required scope without broadening permissions to force the test to pass.
5. **Switch remaining clients.** Monitor across an operational cycle matching job frequency and availability targets.
6. **Revoke the old credential in OCI.** Do not merely delete a variable in the CI UI.
7. **Run a fresh request with the old credential.** Expect rejection; use a fresh connection to avoid misinterpreting cached state or old sessions.
8. **Verify the new credential and clean up copies.** Check jobs, runbooks, standby runners, and temporary storage.

This is a suggested transition plan for the scenario above. Observation window length must match actual run schedules. A few minutes of monitoring is insufficient for a job that runs only once a week.

If a credential is compromised, prioritize rapid revocation to stop unauthorized access; accepting brief downtime may be necessary rather than keeping an exposed key active during a transition. Preparing an emergency rotation plan beforehand minimizes this downtime.

### 6.3. Handling Secrets Committed to Repositories or Logs

Do not wait for log deletion or commit history rewriting to consider an incident closed. Follow an appropriate operational sequence:

1. Identify the exact credential type, affected user, and current permission scope.
2. Revoke the exposed credential and deploy a replacement credential to clients that must stay online.
3. Check for anomalous activity using Audit for supported events, service logs, and related pipeline logs.
4. Reconcile potentially impacted resources or data, including unexpected charges and availability-impacting changes.
5. Remove copies from improper storage, remediate history per team process, and add preventive safeguards.

Incident evidence should contain timestamps, identity, identifying fingerprint or Access Key, target resources, and request IDs. Never attach private keys, Secret Keys, auth tokens, or full authentication headers. OCI credential protection recommendations are covered in [IAM Credentials](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_Credentials.htm).

## 7. Layered Error Diagnosis

The table below guides investigation. A single error message is insufficient to conclude a single root cause.

| Symptom | Check First | Next Step |
| --- | --- | --- |
| Cannot read private key or local passphrase error | Path, format, read permissions, and passphrase input mechanism | Fix client config before investigating IAM |
| OCI API returns `NotAuthenticated` | User OCID, fingerprint, key pair, clock, and signed request contents | Compare a fresh request against a known working config |
| Docker login fails | Registry domain, namespace, username format, and auth token | Run a clean login attempt; avoid stale cached login state |
| Docker login succeeds but image pull fails | Image/tag existence, target repository, and pull permissions | Check policies on the compartment holding the repository |
| S3 client reports `SignatureDoesNotMatch` | Whether Access Key/Secret Key pair match; endpoint, region, and signing config | Check request modification by proxies or client configuration |
| Object access denied | Right bucket, right region, user, groups, and policies | Match permissions to the API called; target resource may also be wrong |
| Only some jobs fail after key rotation | Runner, secret version, and actual schedule | Find clients still using the old key or un-reloaded config |

When providing remote support, request redacted identifying details. If detailed client debug logging must be turned on, restrict log read access and inspect contents before sharing. Never print credentials to the screen as an authentication test.

## 8. Capstone Practice Lab

### Prerequisites

The administrator prepares a test environment containing:

- Bucket `iam-credentials-lab` in a selected region with a non-sensitive sample object.
- A dedicated repository containing a test image to verify auth tokens.
- Identities and policies scoped strictly to what each test needs.
- OCI CLI, Docker, and a compatible S3 client on the learner's machine.

Commands in this lesson illustrate Singapore. If using another region, update profile, endpoint, and registry names consistently. Store each credential only in the selected secret protection store.

### Execution Sequence

1. For the API signing key, use a dedicated profile to list objects in the sample bucket.
2. For the auth token, log in to OCIR and pull the authorized image.
3. For the customer secret key, use an S3 client to list the same sample bucket via the compatibility endpoint.
4. Record outcomes per the template below while keeping secrets out of the report.
5. Perform a key rotation following the overlap workflow, then test the revoked old credential with a fresh request.
6. Clean up unnecessary local profiles and login state, and revoke credentials created solely for this lab.

| Test | Evidence to Record | Pass Criterion |
| --- | --- | --- |
| OCI API read object | Profile, bucket, timestamp, and outcome | Reads within granted scope |
| OCIR pull image | Registry, repository, tag, and outcome | Pulls sample image |
| S3 compatibility | Endpoint, region, bucket, and outcome | S3 client receives valid response |
| Revoke old credential | Identifier and fresh test timestamp | Old credential fails authentication |
| Continuity after rotation | Updated clients and verified job cycle | New credential serves the task properly |

Do not mark the lab complete merely because all three credential types were created. Outcomes must demonstrate that clients use the right credential type, access only the right resources, and can rotate or revoke credentials with clear operational visibility of impact.

## 9. Key Takeaways

- Start from the client's API and authentication mechanism before issuing credentials.
- Keep private keys, auth tokens, and Secret Keys in secret-protected channels; point identifying config at the exact target environment.
- Design identities and IAM policies around tasks to limit blast radius.
- Maintain a complete inventory of credential usage, including standby runners and infrequent restore jobs.
- Verify rotations and revocations with fresh requests while confirming ongoing tasks continue to work.

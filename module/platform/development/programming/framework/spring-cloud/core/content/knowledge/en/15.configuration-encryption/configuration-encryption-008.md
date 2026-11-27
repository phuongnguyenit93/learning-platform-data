# Key Rotation and Maintaining Readability of Encrypted Configurations

Configuration encryption is only useful when applications can still decrypt data throughout their operational lifecycle. A password encrypted in Git still has to be decrypted accurately by Config Server or Config Client at startup. When changing keys, the system must continue reading ciphertext created with the old key during a transition window while starting to create new ciphertext with the new key.

In Spring Cloud Config, Config Server supports symmetric and asymmetric keys. With a keystore holding multiple aliases, ciphertext can specify which alias to use via prefixes such as {key:config-2026}. This mechanism lets you keep both the old key and new key concurrently during migration. Only after every supported configuration and rollback revision has moved to the new key can the old alias be removed from the active keyring.

This lesson belongs to the **Configuration Encryption** chapter of the **SPRING_CLOUD_CORE** module. The content connects external configuration, Spring Cloud Config, secret management, refresh, and application recoverability. The focus is on preserving readability of old ciphertext, rolling out new keys in a controlled manner, and verifying every Config Server before concluding the cutover.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish symmetric keys, asymmetric keys, and the role of keystore aliases.
2. Explain how Config Server processes values with the {cipher} prefix.
3. Configure encryption keys via runtime-injected secrets instead of committing them to the repository.
4. Use multiple aliases to maintain decryption capability during key rotation.
5. Plan dual-key deployment before changing ciphertext in Git.
6. Distinguish encryption/decryption at Config Server from decryption at Config Client.
7. Recognize decryption errors and prevent ciphertext from being used as password values.
8. Test reading old configurations, new configurations, and rollback revisions.
9. Secure the /encrypt, /decrypt endpoints and documents containing ciphertext.
10. Establish periodic rotation procedures and incident response when a key is compromised.

## 2. Why Must Key Rotation Be Planned?

Suppose Config Server uses key K1 to encrypt a database connection password. The repository stores ciphertext C1, and clients fetch configuration through Config Server.

When the organization replaces K1 with K2, simply swapping the key on Config Server can make C1 undecryptable. Applications may receive configuration errors, dropped properties, or a fallback value from another property source. As a result, the service may fail to start, fail to connect to the database, or use an unintended value.

A key replacement therefore involves three things:

- **Active keys:** the key material or aliases Config Server can use.
- **Stored ciphertext:** encrypted values in Git, files, or configuration sources.
- **Configuration versions requiring support:** current revision, deployment branches, release tags, and revisions that might need rollback.

~~~mermaid
flowchart TD
    A[Repository containing ciphertext C1] --> B[Config Server]
    K1[Key K1] --> B
    B --> C[Decrypt configuration]
    C --> D[Config Client receives value]
    E[Immediately replace K1 with K2] --> F[C1 can no longer be decrypted]
    F --> G[Startup or refresh fails]
~~~

Replacing a key without migrating ciphertext is a breaking change. A safe procedure requires an overlap period where the system can decrypt both old and new ciphertext.

## 3. Spring Cloud Config Encryption Mechanism

### 3.1. The {cipher} Prefix

Config Server identifies encrypted values via the {cipher} prefix. Example in a YAML file:

~~~yaml
spring:
  datasource:
    username: app_user
    password: '{cipher}CIPHERTEXT_FROM_CONFIG_SERVER'
~~~

Single quotes around the YAML value make the parser preserve the string containing curly braces. In `application.properties`, write the value without quotes:

~~~properties
spring.datasource.username=app_user
spring.datasource.password={cipher}CIPHERTEXT_FROM_CONFIG_SERVER
~~~

Spring Cloud Config documentation notes that encrypted values in Properties files must not be wrapped in quotes; otherwise decryption may fail to recognize them properly.

When Config Server reads a property source from the repository, values starting with {cipher} are decrypted before being sent to clients in the default mode. This allows the repository to store ciphertext while clients receive plaintext over a TLS-protected Config Server connection.

### 3.2. Encryption at Rest and Plaintext in Use

Encrypting configuration in Git primarily protects data **at rest**. It does not mean secrets remain encrypted throughout their entire lifecycle:

1. Plaintext is sent to the encryption endpoint or a trusted encryption tool.
2. Ciphertext is stored in the repository.
3. Config Server reads the ciphertext.
4. Config Server decrypts it in memory.
5. Clients receive plaintext if server-side decryption is enabled.
6. The value can exist in the Environment, configuration objects, or client memory.

Therefore, you still need to protect TLS, Config Server, repository access permissions, logs, Actuator, memory dumps, and per-application configuration read permissions. Do not treat the {cipher} prefix as a complete secret management system.

### 3.3. Encryption and Decryption Endpoints

Config Server exposes two endpoints:

- POST /encrypt: encrypts plaintext and returns ciphertext.
- POST /decrypt: decrypts ciphertext and returns plaintext.

Example using a value supplied via a shell environment variable:

~~~bash
printf '%s' "$SECRET_VALUE" | curl -sS \
  -X POST \
  -H 'Content-Type: text/plain' \
  --data-binary @- \
  https://config.example.internal/encrypt
~~~

To decrypt, send the received ciphertext to the /decrypt endpoint:

~~~bash
printf '%s' "$CIPHERTEXT" | curl -sS \
  -X POST \
  -H 'Content-Type: text/plain' \
  --data-binary @- \
  https://config.example.internal/decrypt
~~~

These are illustrative examples. Never put real secrets directly into command history, tickets, chat, or CI logs. The /decrypt endpoint returns plaintext and requires stricter access control; do not expose this endpoint to end users or public networks.

When sending values containing special characters via curl, ensure the request body is transmitted intact. Spring Cloud Config documentation suggests using `--data-urlencode` with proper syntax or setting `Content-Type` to `text/plain`; the plus sign (`+`) is easily mishandled if the body is improperly encoded.

## 4. Key Types and Storage Locations

### 4.1. Symmetric Keys

A symmetric key uses the same secret for encryption and decryption. Config Server can accept the key via the property:

~~~properties
encrypt.key=SECRET_VALUE_INJECTED_AT_RUNTIME
~~~

Or via the environment variable:

~~~bash
ENCRYPT_KEY
~~~

Never commit the real value of `encrypt.key` into application.yml, application.properties, Docker images, or Git. Inject it from a secret manager, deployment environment, or the platform's secret management mechanism.

Advantages:

- Simple configuration.
- Only one key value to manage.
- Suitable when only Config Server holds the key and decrypts.

Limitations:

- Any component holding the key can both encrypt and decrypt.
- If the key is compromised, ciphertext protected by that key is at risk of decryption.
- Sharing a single key across multiple applications increases the blast radius during an incident.
- Key replacement requires migrating ciphertext or having a strategy to support multiple encryptors.

Do not assume the keystore multi-alias mechanism automatically applies to a single symmetric `encrypt.key` value. Spring Cloud Config documentation describes key aliases in multi-key workflows with keystores and `TextEncryptorLocator`; if multiple symmetric keys are needed, you must design a custom locator/encryptor or migrate data using a separate compatible workflow.

### 4.2. Asymmetric Keys

Asymmetric encryption uses a key pair:

- Public key is used to encrypt.
- Private key is used to decrypt.

Spring Cloud Config can read a key pair from a keystore. Common properties:

| Property | Meaning |
| --- | --- |
| encrypt.keyStore.location | Resource location containing the keystore |
| encrypt.keyStore.password | Password to open the keystore |
| encrypt.keyStore.alias | Alias identifying the key entry |
| encrypt.keyStore.type | Keystore type; default is JKS per documentation |

Configuration structure example, with secrets injected from the deployment environment:

~~~yaml
encrypt:
  keyStore:
    location: file:/run/secrets/config-server.jks
    type: JKS
    alias: config-current
    password: KEYSTORE_PASSWORD_INJECTED_AT_RUNTIME
~~~

This is only an illustrative placeholder for an injected password; do not use example strings as real passwords. The keystore path must be secured, and only Config Server or the responsible component should be permitted to read the private key.

### 4.3. Separating Encryption and Decryption Privileges

With asymmetric keys, in principle you can give only the public key to the encrypting component while keeping the private key at the decrypting site. This reduces the number of components holding decryption capability.

If Config Server decrypts before returning to clients, Config Server must hold the private key. If clients decrypt locally, the private key must be provisioned to clients. That expands private key distribution and management across many services, increasing key protection responsibilities.

### 4.4. A Keystore Is Not Automatically a KMS

A keystore is a storage format for key material and metadata. It does not inherently provide full capabilities such as:

- Workload-identity-based access approval.
- Centralized auditing for every key usage.
- Automated rotation policies.
- HSM-backed key operations.
- Revocation and environment-scoped authorization.
- Privilege separation between encryptors and decryptors.

You can integrate a secret manager, Vault, KMS, or HSM to protect keys and keystore passwords. Concrete integration must be designed around your platform; do not assume merely declaring `encrypt.keyStore.location` connects Spring Cloud Config to a KMS.

## 5. Maintaining Readability of Old Ciphertext

### 5.1. The Problem with Immediate Key Replacement

Suppose the repository contains:

~~~yaml
database:
  password: '{cipher}CIPHERTEXT_ENCRYPTED_WITH_K1'
~~~

Config Server currently has only K1. If you replace all key material with K2 before re-encrypting values in the repository, the server loses the ability to decrypt old ciphertext.

An application may exhibit the following symptoms:

- Configuration values are marked invalid.
- Properties are not supplied as expected.
- A lower-precedence property source providing a same-named fallback gets selected.
- Configuration beans fail to bind.
- The client starts up but fails to connect to dependencies.

Do not treat the fact that an application still starts up as proof of a successful migration. Verify the final resolved values and which source supplied them.

### 5.2. Keeping Both Keys During the Transition Period

With a multi-alias keystore, you can hold K1 and K2 concurrently:

~~~text
Config Server keystore
  config-legacy  -> private key K1
  config-current -> private key K2
~~~

Old ciphertext specifies alias K1:

~~~yaml
database:
  password: '{cipher}{key:config-legacy}CIPHERTEXT_OLD'
~~~

New ciphertext specifies alias K2:

~~~yaml
database:
  password: '{cipher}{key:config-current}CIPHERTEXT_NEW'
~~~

Config Server uses the alias in the prefix to locate the matching key. During the transition period, both aliases must be present and available on **every Config Server replica** that can receive client requests.

Do not add the new key to only one node. If a load balancer routes requests to a node still missing the new alias, decryption results will be inconsistent across requests.

### 5.3. Key Alias Prefix

With a keystore, Spring Cloud Config supports prefixes of the form:

~~~text
{cipher}{key:config-current}BASE64_CIPHERTEXT
~~~

The default locator uses the alias indicated in the prefix to look up the key in the keystore. The documentation also describes an optional secret prefix; if a separate secret is provided, an appropriate `SecretLocator` must be implemented to handle that secret.

Alias names should reflect purpose or version, for example:

~~~text
config-2025
config-2026
config-incident-rotation-01
~~~

Never put secrets or passwords into alias names. An alias is a non-secret identifier for selecting a key entry, not a place to store key material.

### 5.4. Default Locator and Customization

Spring Cloud Config uses `TextEncryptorLocator` to locate the appropriate encryptor for ciphertext. The default locator supports selecting keystore aliases via the key prefix. If you want to select encryptors by application, profile, tenant, or custom policy, you can provide a custom `TextEncryptorLocator`.

Current documentation notes that the default locator does not automatically create a separate key per application/profile; by default, encryptions share the same key. If keys must be separated by application or profile, you must design a custom locator and thoroughly test routing behavior.

## 6. Key Rotation Procedure with a Multi-Alias Keystore

A migration from K1 to K2 should be divided into phases. The goal is that Config Server never receives new ciphertext without the key to decrypt it, while still preserving the ability to read old revisions during the rollback window.

### 6.1. Phase 0 — Inventory

Before making changes, compile a list of:

- Applications and profiles using ciphertext.
- Repositories, branches, tags, and labels containing ciphertext.
- Aliases currently referenced.
- Config Server instances and each instance's keystore.
- Keystore backup/restore mechanisms.
- Access permissions for `/encrypt` and `/decrypt` endpoints.
- Rollback procedures and how long old revisions must be supported.

Do not discover secrets by bulk-decrypting into logs or unprotected temporary files. You only need to inventory aliases, property paths, and revisions; there is no need to expose plaintext.

### 6.2. Phase 1 — Add the New Key to the Keyring

Generate a new key pair and add the new alias to the keystore. Every Config Server instance must be able to read both old and new aliases.

~~~text
Before:
  config-legacy

Transition:
  config-legacy
  config-current
~~~

Deploy the compatible keystore to all Config Server replicas before updating ciphertext in the repository.

Verify on every node:

1. Keystore is mounted at the expected path.
2. Keystore password is injected successfully.
3. Old alias exists.
4. New alias exists.
5. Config Server can initialize an encryptor for each alias.
6. No logs contain private keys or passwords.

Do not remove the old alias at this step.

### 6.3. Phase 2 — Bidirectional Testing

Before editing the repository, use a non-sensitive test value to verify:

- Old ciphertext decrypts with the old alias.
- New ciphertext created with the new alias decrypts with the new alias.
- All Config Server replicas return the same result.
- Clients retrieve the expected configuration value.
- No replica is still using the old keystore.

If multiple Config Servers sit behind a load balancer, test each instance directly on the management network and then test through the shared endpoint.

### 6.4. Phase 3 — Generate New Ciphertext

You can send the alias prefix inside the POST body to `/encrypt` to instruct Config Server to use the corresponding key. Illustrative example:

~~~bash
printf '%s' "$SECRET_VALUE" | curl -sS \
  -X POST \
  -H 'Content-Type: text/plain' \
  --data-binary @- \
  https://config.example.internal/encrypt
~~~

When selecting an alias, send the key prefix using the syntax supported by Config Server in the plaintext request, or use an encryption tool configured with the new alias. Verify the output references the expected alias before writing it to the repository.

Do not assume the `/encrypt` endpoint automatically picks the new alias simply because the new alias was added to the keystore. Default alias and key selection depend on keystore/locator configuration. Inspect the output ciphertext or use an explicit alias selection mechanism.

### 6.5. Phase 4 — Update the Repository

Replace old ciphertext with new ciphertext:

~~~yaml
spring:
  datasource:
    password: '{cipher}{key:config-current}CIPHERTEXT_ENCRYPTED_WITH_K2'
~~~

Keep the same property names, data types, and profile scopes to minimize unintended changes. Changing property names or configuration structure at the same time makes troubleshooting harder.

For Properties files:

~~~properties
spring.datasource.password={cipher}{key:config-current}CIPHERTEXT_ENCRYPTED_WITH_K2
~~~

Do not wrap Properties values in quotes. For YAML, wrap the string in quotes so the parser does not interpret the curly braces as YAML structure.

### 6.6. Phase 5 — Client Verification and Rollout

After the repository contains the new ciphertext:

1. Fetch configuration for the right application/profile/label.
2. Confirm Config Server decrypts successfully.
3. Inspect the final property in the client's Environment within a secured environment.
4. Check configuration beans and dependency connections.
5. Refresh or restart clients according to what the change supports.
6. Monitor all client replicas, not just one instance.
7. Record the verified configuration revision.

If server-side decryption is enabled, clients receive plaintext. There is no need to distribute private key K2 to clients in this model.

### 6.7. Phase 6 — Retain the Old Key During the Rollback Window

Once the new configuration is running stably, retain the old alias for a defined period. Sources that may still hold old ciphertext include:

- Unmerged branches.
- Old release tags.
- Configuration revisions still used by another environment.
- Repository backups.
- Artifacts or snapshots containing configuration.
- Configuration copies saved for rollback.

If rolling back to an old revision, Config Server must still possess the key to decrypt old ciphertext. Deleting K1 too early can cause rollbacks to fail.

### 6.8. Phase 7 — Remove the Old Alias

Remove the old alias from the active keyring only when:

- All configurations requiring support have migrated to K2.
- No environment still uses K1 ciphertext.
- The rollback window has closed or rollback copies have a re-encryption plan.
- Backups needing restoration have been handled per retention policy.
- Testing confirms new configurations remain readable with only K2 present.

If K1 was compromised, incident response procedures may require shortening the old-key retention window. In that case, prioritize blocking unauthorized decryption, re-encrypting, and performing an emergency rollout; any rollback copies using K1 must be deemed unsafe to restore as-is.

~~~mermaid
flowchart TD
    A[Inventory old ciphertext and aliases] --> B[Add K2, keep K1 on all Config Servers]
    B --> C[Test decryption for K1 and K2]
    C --> D[Encrypt new secrets with K2]
    D --> E[Commit ciphertext with K2 alias]
    E --> F[Clients read configuration and verify]
    F --> G[Retain K1 during rollback window]
    G --> H{Any revisions still need K1?}
    H -->|Yes| G
    H -->|No| I[Remove K1 alias per procedure]
~~~

## 7. Handling Symmetric Keys Without Keystore Aliases

If Config Server uses only a single symmetric `encrypt.key`, changing the key value immediately makes old ciphertext undecryptable with the new key.

A straightforward transition process requires:

1. Inventory all ciphertext created with K1.
2. Ensure decryption with K1 works in a controlled environment.
3. Generate new ciphertext with K2 for all properties to retain.
4. Verify every new ciphertext with K2.
5. Deploy K2 alongside the migrated repository in a compatible sequence.
6. Retain necessary recovery copies per policy, without leaving a compromised key broadly accessible.
7. Once migration is complete, remove K1 from the active configuration.

The difficulty is that without a per-ciphertext key selection mechanism, a Config Server with a single symmetric key cannot by default read both K1 and K2 ciphertext simultaneously. Plan carefully to avoid any window where configuration and key are incompatible.

If dual-key support is required for symmetric encryption, implement a custom `TextEncryptorLocator` to route by a key ID/version embedded in a designed prefix or metadata. Verify compatibility, secret management, and old-data decryption via integration tests. Do not invent arbitrary prefixes assuming the default locator understands them.

## 8. Decryption at Config Server or Config Client?

### 8.1. Server-Side Decryption — Default

By default, Config Server decrypts {cipher}-prefixed values before returning property sources over HTTP.

~~~mermaid
sequenceDiagram
    participant Git as Config repository
    participant Server as Config Server
    participant Key as Keystore / key
    participant Client as Config Client
    Git->>Server: Ciphertext {cipher}
    Server->>Key: Select alias and decrypt
    Key-->>Server: Plaintext
    Server-->>Client: Decrypted property source
~~~

Advantages:

- Private keys or symmetric keys are centralized at Config Server.
- Clients do not need to hold decryption keys.
- Key rotation is more centralized.
- Clients do not need to implement crypto integration themselves.

In return, Config Server becomes a component with access to plaintext for multiple applications. Secure the service, restrict read permissions by application/profile, and control which operators can invoke decryption endpoints.

### 8.2. Client-Side Decryption

In some architectures, clients are expected to receive ciphertext and decrypt locally. Spring Cloud Config provides an option to disable outgoing property decryption:

~~~properties
spring.cloud.config.server.encrypt.enabled=false
~~~

Spring Cloud Config documentation describes placing this setting in Config Server's bootstrap configuration. Check your exact bootstrap/Config Data mode and running version before setting the property.

When clients decrypt locally:

- Config Server can hold ciphertext and does not need the private key to serve configuration.
- Clients must be provisioned with matching key material.
- Private/symmetric keys are distributed across more workloads.
- Each client needs rotation procedures and compatibility tests.
- One compromised client can expose a shared key if the key scope is too broad.

Choose client-side decryption only when there is a clear architectural reason and matching distributed key management capability.

### 8.3. Do Not Mix the Two Models Under One Assumption

If server-side decryption is enabled, clients typically receive plaintext. If server-side decryption is disabled, clients may receive ciphertext and require local decryption. Document the chosen model explicitly in architecture docs, runbooks, and tests.

Never assume that merely having the Config Client starter means a client automatically possesses the private key or will automatically decrypt every ciphertext in every setup. Verify integration, key material, and actual response behavior.

## 9. Decryption Errors and Invalid Properties

### 9.1. Default Behavior When Decryption Fails

If Config Server cannot decrypt a value, it removes that property from the property source and adds a property whose name starts with `invalid`, for example:

~~~json
{
  "propertySources": [
    {
      "name": "application-prod.yml",
      "source": {
        "invalid.database.password": "<n/a>"
      }
    }
  ]
}
~~~

This behavior prevents ciphertext from accidentally being used as a password and leaking into logs or clients.

### 9.2. Fallback from Lower-Precedence Property Sources

If another property source defines the same key at a lower precedence, the client may receive the value from that source. For instance, shared config has a default password while the production profile has an undecryptable ciphertext. Config Server may mark the key invalid in the profile source; the client can then resolve the same-named value from another source.

This can cause the application to start up with an unintended fallback. For required secrets, add validation and tests so the app never silently falls back to default credentials.

### 9.3. What Are the Consequences of Disabling the invalid Prefix?

The property:

~~~properties
spring.cloud.config.server.encrypt.prefix-invalid-properties=false
~~~

disables adding the `invalid` prefix. When set, if the server fails to decrypt, the encrypted value may be returned to the client as an ordinary string. If the client does not decrypt locally, ciphertext may be bound as a password or token and cause confusing failures.

Never disable the invalid prefix merely to hide warnings. Consider it only when a client-side decryption architecture has been thoroughly designed, tested, and secured.

### 9.4. Diagnosing Without Exposing Secrets

When an error occurs, record:

- Requested application, profile, and label.
- Property name marked invalid.
- Referenced alias/key ID.
- Config Server instance handling the request.
- Repository revision.
- Timestamp and correlation ID.

Do not log plaintext, private keys, keystore passwords, or full ciphertext unless necessary. Ciphertext is not plaintext, yet it remains sensitive data that requires control because it could be decrypted if a key is compromised.

## 10. Protecting the /encrypt and /decrypt Endpoints

### 10.1. Encryption Endpoints Are Not Public APIs

The `/encrypt` endpoint accepts plaintext and returns ciphertext. Authorized callers can encrypt data that will be stored in the repository. Enforce authentication, authorization, and auditing of who generated ciphertext.

### 10.2. The Decryption Endpoint Has Higher Sensitivity

The `/decrypt` endpoint returns plaintext. Permission to call this endpoint is nearly equivalent to permission to read the underlying secrets. Grant it only to authorized operators or pipelines and only when genuinely necessary.

Never expose `/decrypt` on a public route or an unauthenticated dashboard. You can separate encrypt and decrypt permissions so configuration authors do not implicitly gain permission to view every secret.

### 10.3. Securing Config Server

Required measures:

- TLS/HTTPS for all clients and operators.
- Per-application authentication and authorization.
- Least-privilege repository permissions.
- Separating configuration read access by application/profile.
- Network restrictions to encryption/decryption endpoints.
- Auditing configuration access and changes.
- Secret injection for keys and keystore passwords.
- Never committing key material into Git or container images.
- Not exposing Actuator `env`/`configprops` or unnecessary administrative endpoints.

According to Spring Cloud Config documentation, without per-application access control, an authenticated client could request another application's configuration simply by changing the application name in the URL. If the repository holds secrets that must be isolated per service, enforce appropriate authorization policies.

### 10.4. Encryption Does Not Replace TLS

Ciphertext in Git protects data at rest. When server-side decryption is enabled, plaintext travels from Config Server to clients. Protecting transit with TLS and restricting read permissions remain mandatory. Never use at-rest encryption as an excuse to skip HTTPS.

## 11. Integrating Secret Managers, Vault, and KMS

Spring Cloud Config provides configuration encryption mechanisms, yet organizations may need a dedicated key management system.

Responsibilities can be separated as follows:

| Component | Responsibility |
| --- | --- |
| Git repository | Store ciphertext and change history |
| Config Server | Fetch property sources, decrypt per configuration, and serve clients |
| Keystore | Store key entries and aliases |
| Secret manager/Vault | Supply keystore passwords or runtime secrets per permissions |
| KMS/HSM | Protect key operations and manage key material per platform capabilities |
| Deployment platform | Inject secrets into processes/containers and enforce workload identity |

Do not push all responsibilities onto Git. The repository may hold ciphertext, but must never hold private keys, symmetric keys, keystore passwords, or KMS access credentials.

When using Vault/KMS, design platform-appropriate adapters or secret injection. Check startup ordering: Config Server must obtain key material before serving configuration requests. If the secret manager is temporarily unavailable, enforce explicit startup/failover policies rather than running with an empty or default key.

## 12. Testing Readability of Old and New Configurations

A rotation test does not merely test the `/encrypt` endpoint. It must verify the full path from ciphertext in the repository to the values consumed by clients.

### 12.1. Test Matrix

| Case | Config Server Keyring | Ciphertext | Expected Result |
| --- | --- | --- | --- |
| Before rotation | K1 | K1 ciphertext | Decrypts successfully |
| Dual-key transition | K1 + K2 | K1 ciphertext | Decrypts successfully |
| Dual-key transition | K1 + K2 | K2 ciphertext | Decrypts successfully |
| After migration | K2 | K2 ciphertext | Decrypts successfully |
| After migration | K2 | K1 ciphertext | Fails decryption in a controlled manner |
| Non-existent alias | K1 + K2 | K3 alias ciphertext | Must not mistakenly use another key |
| Wrong private key/password | Keyring fails to open | Any ciphertext | Startup or decrypt reports clear error |
| Rollback revision | K1 + K2 | Old revision using K1 | Decrypts successfully within rollback window |

### 12.2. Testing Every Config Server Replica

If there are three Config Server nodes, test all three:

1. Node 1 decrypts old and new ciphertext.
2. Node 2 decrypts old and new ciphertext.
3. Node 3 decrypts old and new ciphertext.
4. Requests through the load balancer return consistent results.
5. No node still mounts an old keystore missing alias K2.

Do not run only a single request through the load balancer; requests in one test run might all hit the same node.

### 12.3. Testing Config Client

From a test Config Client:

- Request the exact application/profile/label.
- Confirm the property source has expected values.
- Verify no invalid keys appear.
- Confirm `@ConfigurationProperties` beans bind successfully.
- Verify datasources/clients can use the new credentials.
- Verify refresh/restart according to the application's mechanism.
- Confirm logs contain no plaintext.

### 12.4. Testing Rollback

Restore an old revision in a test environment while the keyring still holds both K1 and K2. Confirm the client still reads old ciphertext. After removing K1 in the test environment, re-run the rollback test to demonstrate that the retention policy behaves as intended.

## 13. Procedure When a Key Is Compromised

Periodic rotation and key-compromise response have different goals.

### 13.1. Assessing the Blast Radius

Determine:

- Which key was compromised.
- Which ciphertext was encrypted with that key.
- Who had access to the key material.
- Which secrets need to be rotated in target systems.
- Which Config Server replicas and clients used the key.
- Whether any backups or artifacts contain the key material.

### 13.2. Replace Target Secrets, Not Just the Encryption Key

If a database password was decrypted by an unauthorized party, merely re-encrypting the same password with K2 does not revoke access for the party who already knows the plaintext.

Consider the following steps:

1. Create new credentials in the database or target system.
2. Update ciphertext using K2.
3. Deploy the new keyring to Config Server.
4. Update configuration and refresh/restart clients.
5. Revoke old credentials.
6. Verify all clients are using the new credentials.
7. Remediate backups, logs, or repositories that may have held the old ciphertext and key.

Rotating the encryption key does not replace rotating credentials in databases, brokers, or API providers.

### 13.3. Revoking a Compromised Key

If a key is severely compromised, do not leave that key active long merely for rollback convenience. Generate new ciphertext, transition clients, and revoke the compromised key according to incident response procedures. Rollback configuration copies must be re-encrypted with a safe key before use.

Never restore a compromised private key into the production keystore just to get an old revision running again.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Old config fails to decrypt after rotation | K1 was removed before K1 ciphertext was migrated | Safely restore decryption capability or re-encrypt data |
| Some Config Servers decrypt, others fail | Keystores across replicas are inconsistent | Synchronize aliases/keyrings and verify each node |
| New ciphertext fails to decrypt | Wrong alias, alias missing, or mismatched key pair | Check key prefix and keystore |
| Config Server returns invalid property | Decryption failed | Check key alias, key password, ciphertext, and revision |
| Client uses default password | Encrypted property became invalid and lower source supplied fallback | Validate required secrets and check property sources |
| Client receives ciphertext instead of plaintext | Server-side decryption disabled or decrypt failed | Check `encrypt.enabled` and client-side decryption |
| `/decrypt` returns 401/403 | Security policy blocks caller | Check operator permissions; do not expose endpoint publicly |
| Plaintext appears in logs | Debug request/response logging or unsafe shell commands | Purge logs per policy, restrict logging, and audit |
| Rollback fails | Old alias was deleted or old revision was not re-encrypted | Maintain rollback window and test old revisions |
| Still had to change target secrets after rotation | Encryption key changed, yet old credentials were exposed | Replace credentials on target systems and revoke old ones |
| Wrong key used by an application | Default locator shares one key or custom locator routes wrongly | Check `TextEncryptorLocator` and application/profile |
| Keystore fails to open after deploy | Wrong password, path, file permissions, or type | Check secret injection and mounts on every replica |

## 15. Pre-Closure Rotation Checklist

### Key Material

- [ ] New key has been generated and stored in a protected location.
- [ ] New alias is present in the keystore of every Config Server replica.
- [ ] Old alias remains available during the transition period.
- [ ] Keystore password is injected at runtime, not committed to Git.
- [ ] Read permissions on keystores and backups are restricted.

### Ciphertext and Repository

- [ ] Ciphertext inventory by application/profile/label is complete.
- [ ] New ciphertext uses the right alias.
- [ ] YAML files use proper quoting for values containing curly braces.
- [ ] Properties files do not wrap cipher values in quotes.
- [ ] No active deployment revision still references the removed alias.

### Config Server and Clients

- [ ] All Config Server replicas decrypt both old and new ciphertext during the transition window.
- [ ] Clients receive expected plaintext values under the server-side decryption model.
- [ ] Zero invalid properties present.
- [ ] Configuration beans and dependencies operate with the new secrets.
- [ ] Logs contain no plaintext or key material.

### Rollback and Revocation

- [ ] Old revisions have been tested within the rollback window.
- [ ] A plan exists to re-encrypt backups requiring restoration.
- [ ] Old alias is removed only when old ciphertext no longer needs to be read.
- [ ] If a key was compromised, target credentials have also been replaced and revoked.
- [ ] Audit trail and designated approver sign-off exist for closing rotation.

## 16. Practice Exercises

**Exercise 1 — Server-side encryption.** Configure Config Server with a symmetric key sourced from an environment variable. Use `/encrypt` to encrypt a test value, store the ciphertext with the `{cipher}` prefix in the repository, and verify the client receives the decrypted value.

**Exercise 2 — Keystore aliases.** Create a keystore with two aliases, `test-key-old` and `test-key-new`. Create two ciphertexts using both aliases and verify Config Server decrypts both when the keyring contains both key entries.

**Exercise 3 — Dual-key migration.** Deploy a keyring containing K1 and K2 to two Config Server instances. Update the repository from K1 ciphertext to K2, then query each instance individually to verify readability.

**Exercise 4 — Rollback.** Restore an old revision containing K1 ciphertext while the keyring still holds K1 and K2. Then retry when only K2 remains and analyze why rollback is no longer compatible.

**Exercise 5 — Decryption failure.** Intentionally use a non-existent alias. Observe the `invalid` property in the response and check whether the client inadvertently uses a fallback value from another property source.

**Exercise 6 — Client-side decryption.** Disable server-side decryption according to your version's guidance. Verify the client receives ciphertext and design a secure private-key distribution approach for workloads.

**Exercise 7 — Incident response.** Assume K1 was compromised and database credentials were read. Draft a procedure to create new credentials, encrypt with K2, deploy the keyring, update clients, revoke old credentials, and verify.

**Exercise 8 — Security review.** Evaluate permissions to call `/encrypt` and `/decrypt`, TLS, per-application authorization, logs, and keystore access permissions. Demonstrate that one Config Client cannot read another service's secrets.

## 17. Key Takeaways and Reference Sources

- Config Server identifies ciphertext via the `{cipher}` prefix; in default mode, the server decrypts before sending configuration to clients.
- Symmetric keys use the same secret to encrypt and decrypt; asymmetric keys use a public key to encrypt and a private key to decrypt.
- A keystore can hold multiple aliases; the `{key:alias}` prefix selects the corresponding key during decryption.
- When rotating, deploy a keyring containing both old and new aliases to all Config Servers before changing ciphertext.
- Retain the old alias during the rollback window; remove it only after all configurations requiring support have migrated.
- The default `TextEncryptorLocator` does not automatically separate keys by application/profile; a custom locator is required for per-app/profile policies.
- On decryption failure, Config Server defaults to omitting the property and adding a property name prefixed with `invalid`.
- Server-side decryption centralizes key management; client-side decryption expands private key distribution scope.
- At-rest encryption does not replace TLS, authorization, secret managers, or protecting plaintext at runtime.
- If a key is compromised, target system credentials must also be replaced; re-encrypting the same old credentials does not revoke exposed access.

Official sources to cross-check for your project's Spring Cloud Config/Spring Boot version:

1. [Spring Cloud Config – Using Multiple Keys and Key Rotation](https://docs.spring.io/spring-cloud-config/reference/server/using-multiple-keys-and-key-rotation.html)
2. [Spring Cloud Config – Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html)
3. [Spring Cloud Config – Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html)
4. [Spring Cloud Config – Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html)
5. [Spring Cloud Config – Security](https://docs.spring.io/spring-cloud-config/reference/server/security.html)
6. [Spring Cloud Config – Client Side Usage](https://docs.spring.io/spring-cloud-config/reference/client.html)
7. [Spring Cloud – Release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)

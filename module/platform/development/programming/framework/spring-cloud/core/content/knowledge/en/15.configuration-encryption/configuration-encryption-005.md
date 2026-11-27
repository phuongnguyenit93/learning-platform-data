# Local Decryption and Decryption at the Remote Configuration Source

This lesson belongs to the **Configuration Encryption** chapter of the **SPRING_CLOUD_CORE** module. Spring Cloud Config allows storing encrypted properties in a repository and decrypting them when delivering configuration to applications. There are two common decryption locations:

- **Decryption at Config Server:** the server reads values starting with `{cipher}`, decrypts them, and returns plaintext to the Config Client.
- **Local decryption at Config Client:** the server returns ciphertext intact; the client holds the appropriate key material and decrypts it locally before the application uses the property.

Both models protect data at rest, yet differ in where keys are held, trust boundaries, and operational overhead. This lesson covers both flows, the `/encrypt` and `/decrypt` endpoints, symmetric/asymmetric keys, decryption errors, and controls needed for deployment.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the `{cipher}` prefix and why ciphertext can be stored in a configuration repository.
2. Describe the decryption flow at Config Server before returning properties to clients.
3. Configure Config Server to preserve ciphertext and Config Client to decrypt locally.
4. Distinguish a symmetric key from an asymmetric key pair.
5. Use `/encrypt` and `/decrypt` to encrypt/decrypt values in a protected environment.
6. Configure `encrypt.key` or `encrypt.keyStore.*` in the right place and at the right lifecycle stage.
7. Identify `invalid.<property>` responses when Config Server fails to decrypt.
8. Understand the impact of `{cipher}` syntax in YAML and `.properties` files.
9. Test Config Server responses and final values in the client's Environment.
10. Design key storage, access control, TLS, key rotation, and safe incident handling.

## 2. Where Does Configuration Encryption Protect Data?

Suppose an application configuration contains database connection details:

~~~yaml
spring:
  datasource:
    username: orders_app
    password: "a-secret-value"
~~~

If this file is committed to Git or stored in a shared backend, anyone with read access to the repository can see the password. Encrypting the property before saving ensures the repository holds only ciphertext:

~~~yaml
spring:
  datasource:
    username: orders_app
    password: '{cipher}ENCRYPTED_VALUE'
~~~

When Config Server processes the property source, the `{cipher}` prefix indicates that the following value is encrypted data. Either Config Server or Config Client will decrypt it depending on the configured model.

~~~mermaid
flowchart LR
    P["Plaintext secret"] --> ENC["/encrypt or encryption tool"]
    ENC --> C["{cipher}..."]
    C --> G["Git / remote configuration store"]
    G --> S["Spring Cloud Config Server"]
    S -->|Server-side decryption| PT1["Plaintext in response"]
    S -->|Preserve ciphertext| CT["Ciphertext in response"]
    CT --> CL["Config Client with key"]
    CL --> PT2["Plaintext in Environment"]
~~~

Encryption at rest does not replace TLS. When plaintext is transmitted over the network, loaded into the JVM, or used by beans, it still requires network security, access control, and secret management policies.

## 3. Two Decryption Locations

### 3.1. Decryption at Config Server

This is the default model when Config Server is configured with key material for decryption:

1. An administrator encrypts the secret using `/encrypt` or a compatible tool.
2. The ciphertext is prefixed with `{cipher}` and saved to the configuration repository.
3. Config Server reads the property source.
4. Config Server decrypts using the server's key.
5. Config Server returns the decrypted property to Config Client over HTTP(S).
6. The client receives plaintext and places it into the Environment.

Advantages:
- Decryption keys are centralized on the server.
- Clients do not need to hold the repository's decryption key.
- Key management and rotation can be coordinated more centrally.

In return, Config Server has access to the plaintext of all secrets it decrypts. You must secure the server, filesystem, process environment, logs, heap dumps, and administrative endpoints.

### 3.2. Local Decryption at Config Client

In this model, Config Server preserves ciphertext when sending property sources:

1. Secrets are encrypted before committing.
2. Config Server reads and returns `{cipher}...` as-is.
3. Config Client receives the property source containing ciphertext.
4. Client-side Spring Cloud Context uses `encrypt.*` to locate the decryption key.
5. The client decrypts the property before the application consumes the Environment.

To enable this model, Config Server must be configured with:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
~~~

Spring Cloud Config documentation requires placing this property in Config Server's `bootstrap.yml` or `bootstrap.properties`. If the server still needs the `/encrypt` and `/decrypt` endpoints, the server can continue configuring `encrypt.*` to locate keys; only outgoing property decryption is disabled.

If encryption/decryption endpoints are not needed on the server, the documentation notes you can omit configuring keys or enabled flags for that feature. Verify your application's bootstrap mode and Spring Cloud Config version.

### 3.3. Comparing the Two Models

| Criterion | Decryption at Config Server | Decryption at Config Client |
| --- | --- | --- |
| Where decryption key lives | Config Server. | Each client or a key system accessed by clients. |
| Data sent by server | Plaintext after decryption. | Ciphertext `{cipher}...`. |
| Client needs decryption key | Does not need repository key. | Needs matching key material. |
| Blast radius on key compromise | Can impact multiple applications/profiles using that key. | Depends on per-key/client or client group scoping. |
| Operations | Centralized key management. | Client-side key distribution, protection, and rotation. |
| Best suited for | Config Server is within the trust boundary and centralized key management is preferred. | Wanting the server to distribute only ciphertext so only key-bearing clients can decrypt. |

Neither model is automatically more secure in all situations. Choose based on trust boundaries, key management capabilities, and the number of clients.

## 4. {cipher} Format in Configuration Files

### 4.1. YAML

Encrypted values in YAML are usually wrapped in single quotes so the YAML parser preserves the prefix and ciphertext string intact:

~~~yaml
spring:
  datasource:
    username: orders_app
    password: '{cipher}ENCRYPTED_VALUE'
~~~

Single quotes are YAML syntax; after parsing, the property value still begins with `{cipher}`.

### 4.2. application.properties

In `.properties` files, do not wrap encrypted values in quotes:

~~~properties
spring.datasource.username=orders_app
spring.datasource.password={cipher}ENCRYPTED_VALUE
~~~

Spring Cloud Config documentation notes that encrypted values in `application.properties` must not be wrapped in quotes; if quoted, the value may fail to decrypt.

### 4.3. The Prefix Is a Processing Signal, Not an Algorithm

`{cipher}` indicates that the value needs to be decrypted. It does not specify which key was used or which exact algorithm produced the ciphertext. Encryptor selection can depend on `encrypt.*`, keystore, alias, or `TextEncryptorLocator`.

Do not fabricate a `{cipher}` string by Base64-encoding plaintext. Base64 is merely encoding, not secure encryption. Use `/encrypt`, Spring Cloud CLI, or an encryption tool compatible with the system's key configuration.

## 5. Configuring a Symmetric Key

### 5.1. A Single Shared Secret

With symmetric encryption, the same secret key is used to encrypt and decrypt. Config Server can be configured with:

~~~yaml
encrypt:
  key: ${ENCRYPT_KEY}
~~~

You can use the `ENCRYPT_KEY` environment variable to avoid writing the key directly into configuration files. If the application uses `spring-cloud-starter-bootstrap` or enables bootstrap via a system property, Spring Cloud documentation requires placing `encrypt.key` in `bootstrap.properties` so the key is available at the right phase.

In the local decryption model, clients also need the matching `encrypt.key`, supplied via a secret manager or the client's environment. The shared key is distributed to clients authorized to decrypt; access scope must be restricted and the key rotated on incident.

Do not commit `encrypt.key` to Git, do not place the key in the same repository holding ciphertext, and do not log the key in startup diagnostics.

### 5.2. Pros and Cons

Pros:
- Simple configuration.
- Only one key value is needed.
- Suitable for labs or systems with controlled secret distribution.

Cons:
- Any party possessing the shared key can decrypt the corresponding data.
- Every client must receive the same secret if clients decrypt locally.
- When the key is compromised, all ciphertext encrypted with that key must be evaluated.

### 5.3. Client-Side Configuration Example

In the client-side decryption model, the key must be available to the client before property source decryption runs. Example using an environment variable:

~~~text
ENCRYPT_KEY=<value-from-secret-manager>
~~~

If configuring the key via file, place it in a secured configuration source loaded at the bootstrap phase required by your application version. Never fetch the decryption key from the very remote property source that needs to be decrypted; that creates a circular dependency and can expose the key.

## 6. Configuring an Asymmetric Key

### 6.1. Public Key and Private Key Pair

Asymmetric encryption uses a key pair:

- **Public key:** used to encrypt data.
- **Private key:** used to decrypt data.

Spring Cloud Config can use a keystore. Main properties:

| Property | Role |
| --- | --- |
| `encrypt.keyStore.location` | Resource location of the keystore. |
| `encrypt.keyStore.password` | Password to open the keystore. |
| `encrypt.keyStore.alias` | Alias of the key/certificate to use. |
| `encrypt.keyStore.type` | Keystore type; default is `jks`. |

YAML configuration example:

~~~yaml
encrypt:
  key-store:
    location: classpath:config-encryption.jks
    password: ${CONFIG_KEYSTORE_PASSWORD}
    alias: config-encryption
    type: jks
~~~

This is an illustrative property structure. Location, alias, and keystore type must match the actual keystore.

### 6.2. Server Holds Only Public Key, Client Holds Private Key

A suitable model for local decryption:

- Config Server is configured with a keystore containing only the public key/certificate to encrypt.
- Config Client is configured with a keystore containing the matching private key to decrypt.
- The repository stores only ciphertext.
- Config Server has outgoing decryption disabled via `spring.cloud.config.server.encrypt.enabled=false`.

This avoids distributing the private key to Config Server. Only clients with the matching private key can decrypt. Each client's private keystore, password, and filesystem permissions must be protected.

Spring Cloud documentation notes that encryption uses the public key and decryption requires the private key. You can configure only the public key on the server if decryption is performed locally.

### 6.3. When to Choose Asymmetric?

| Scenario | Consideration |
| --- | --- |
| One server and a few clients in a lab environment | A shared key may be simpler. |
| Multiple clients with different trust boundaries | Public/private keys allow granting decryption capability per client or client group. |
| Config Server should not hold the private key | Provision only the public key to the server, private key to clients. |
| Centralized key management desired | Server-side decryption may be simpler if the server is within the trust boundary. |

Asymmetric encryption does not automatically solve every key management problem. You must still protect private keys, manage certificates/aliases, handle backups, rotate keys, and revoke access.

## 7. Using the /encrypt and /decrypt Endpoints

### 7.1. The /encrypt Endpoint

Config Server exposes `/encrypt` to encrypt plaintext into ciphertext using the configured key material.

Illustrative example in a lab environment:

~~~bash
curl -s \
  --request POST \
  --header "Content-Type: text/plain" \
  --data-binary "secret-value" \
  http://localhost:8888/encrypt
~~~

The response is ciphertext. Take the ciphertext and prepend `{cipher}` when saving it into YAML or `.properties`.

When using `curl` with data containing special characters such as `+`, spaces, or URL-sensitive characters, use `--data-urlencode` as guided by the documentation or explicitly send `Content-Type: text/plain`. Do not let curl progress meters or messages get concatenated onto the ciphertext.

Never pass real plaintext into shell history, tickets, terminal transcripts, or CI logs. For production secrets, use an approved secret administration workflow and avoid copy/pasting over insecure channels.

### 7.2. The /decrypt Endpoint

The `/decrypt` endpoint performs the reverse operation if the server has a matching key:

~~~bash
curl -s \
  --request POST \
  --header "Content-Type: text/plain" \
  --data-binary "ENCRYPTED_VALUE" \
  http://localhost:8888/decrypt
~~~

The response is plaintext. Use this endpoint only in a secured environment and by an authorized principal. Do not write plaintext responses to unprotected temporary files or logs.

### 7.3. Adding {cipher} Before Saving

Typical workflow:

1. Receive plaintext through a secret-handling channel.
2. Send plaintext to the secured `/encrypt` endpoint.
3. Receive ciphertext.
4. Prepend `{cipher}` to the ciphertext.
5. Place the value in the appropriate property.
6. Validate YAML/properties syntax.
7. Commit the ciphertext to the configuration repository.
8. Test that Config Server returns the expected data according to the chosen decryption model.

Never commit plaintext first and encrypt it in a follow-up commit. The secret can remain in Git history and clones; if exposed, remediate history per incident/secret rotation procedures.

### 7.4. Application- and Profile-Specific Endpoints

The encryption/decryption endpoints also support paths of the form:

~~~text
/{application}/{profiles}/encrypt
/{application}/{profiles}/decrypt
~~~

This allows specifying the application/profile when using context-aware encryption mechanisms. However, to use different keys per application/profile, you must supply a custom `TextEncryptorLocator` bean. The default locator does not automatically pick a different key for each application/profile; by default it uses the same key.

Do not assume that adding an application name to the URL automatically creates a separate key.

## 8. Decryption at Config Server

### 8.1. Server-Side Decryption Configuration

In this model, Config Server holds the decryption key. Example using a shared key:

~~~yaml
encrypt:
  key: ${ENCRYPT_KEY}

spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: true
~~~

The server's default behavior is to decrypt encrypted properties before returning to clients when matching keys/config are present. You can explicitly set `enabled: true` to express intent. If using bootstrap mode, place the required settings in bootstrap configuration per your version's guidance.

### 8.2. Flow from Git to Client

~~~mermaid
sequenceDiagram
    participant Git as Config repository
    participant Server as Config Server
    participant Key as Server key material
    participant Client as Config Client
    Git->>Server: Read application.yml containing {cipher}...
    Server->>Key: Locate encryptor/key
    Key-->>Server: Matching key
    Server->>Server: Decrypt property
    Server-->>Client: Property source with plaintext
    Client->>Client: Bind Environment / @ConfigurationProperties
~~~

The client does not need the repository decryption key in this model. However, plaintext appears in the Config Server response and in the client process. Protect TLS, Config Server access permissions, logs, actuator, heap dumps, and client diagnostics.

### 8.3. Benefits and Limitations

Benefits:
- Centralized key management on the server.
- Simpler clients without distributing private/shared keys.
- Key rotation can be coordinated centrally.

Limitations:
- Config Server has authority to decrypt every property within the key's scope.
- If the server is compromised, ciphertext can be decrypted right where it is served.
- Plaintext traverses the network; TLS and authentication remain mandatory.
- Logs or traces accidentally capturing plaintext responses can leak secrets.

## 9. Local Decryption at Config Client

### 9.1. Disabling Outgoing Decryption on the Server

On Config Server, set:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
~~~

According to Spring Cloud Config documentation, this setting is placed in the server's `bootstrap.yml` or `bootstrap.properties`. If the server still configures `encrypt.*`, the `/encrypt` and `/decrypt` endpoints can still be used; only outgoing property decryption is disabled.

### 9.2. Client Receives Ciphertext and Decrypts Locally

Config Client must have the matching key material.

**With a shared key:**

~~~yaml
encrypt:
  key: ${ENCRYPT_KEY}
~~~

**With a keystore/private key:**

~~~yaml
encrypt:
  key-store:
    location: file:/run/secrets/config-client-keystore.jks
    password: ${CONFIG_KEYSTORE_PASSWORD}
    alias: config-client
    type: jks
~~~

This is an illustrative configuration. Ensure the keystore file and password are supplied by secret management, not placed in the shared configuration repository.

The client must have the key available before Spring Cloud Context executes property source decryption. If using bootstrap mode, place `encrypt.*` in bootstrap configuration or a local/environment source loaded early enough. Do not rely on a key located inside the remote source that itself needs to be decrypted.

### 9.3. Client-Side Processing Flow

~~~mermaid
sequenceDiagram
    participant Repo as Git / remote config store
    participant Server as Config Server
    participant Client as Config Client
    participant Crypto as Client encryptor
    participant Env as Client Environment
    Repo->>Server: Read {cipher}...
    Server->>Server: Skip outgoing decryption
    Server-->>Client: Return ciphertext
    Client->>Crypto: Look up key from encrypt.*
    Crypto-->>Client: Decrypt value
    Client->>Env: Put plaintext property into Environment
    Env-->>Client: Bean binding / application usage
~~~

### 9.4. Benefits and Limitations

Benefits:
- Config Server does not need a private key or shared decryption key if it only stores/distributes ciphertext.
- Clients without the key cannot decrypt the data.
- You can restrict the group of clients provisioned with the private key.

Limitations:
- Key material must be provisioned and protected on each client.
- Rotation requires coordination between server, clients, and ciphertext in the repository.
- If multiple clients share a symmetric key, compromising one client can expose others.
- Clients must handle decryption errors before the application uses configuration.
- The client's local key must be available early enough in the startup lifecycle.

## 10. Handling Decryption Errors

### 10.1. Server Fails to Decrypt

If Config Server cannot decrypt a `{cipher}` value, by default it omits the original property from the property source response and adds a property prefixed with `invalid.`.

Example response:

~~~json
{
  "propertySources": [
    {
      "name": "application-prod.yml",
      "source": {
        "invalid.SharedPassword": "<n/a>"
      }
    },
    {
      "name": "application.yml",
      "source": {
        "SharedPassword": "fallback-value"
      }
    }
  ]
}
~~~

In the example, `SharedPassword` in the profile file failed to decrypt. The original property is removed from that source; `invalid.SharedPassword` serves as an error marker. If a lower-precedence source contains `SharedPassword`, the client may pick up the fallback value from that source.

This behavior prevents broken ciphertext from being mistakenly used as a password and avoids leaking encrypted strings into the application.

### 10.2. Disabling the invalid Prefix

You can configure:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          prefix-invalid-properties: false
~~~

When the invalid prefix is disabled, undecryptable values may be returned under the original property name as ciphertext. In the client-side decryption model, the client can proceed to process the ciphertext if it holds the matching key. However, if the client also lacks the key, it will receive the encrypted string instead of plaintext.

Do not disable the invalid prefix merely to mask a key mismatch error. First verify the key, alias, profile, ciphertext, and algorithm compatibility.

### 10.3. Common Causes

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Property has `invalid.` prefix | Server cannot find the key or decryption failed. | Check `encrypt.*`, alias, keystore, ciphertext, and server logs. |
| Client receives `{cipher}...` string | Server disabled outgoing decryption, or client decrypt did not run/lacks key. | Verify server/client-side model and `encrypt.*` on the client. |
| `/decrypt` returns error | Wrong key, missing private key, truncated ciphertext, or wrong request encoding. | Check key material, Content-Type, and intact ciphertext. |
| One profile decrypts, another fails | Profile uses a different key/alias or ciphertext was created with another key. | Check `{key:alias}`, application/profile path, and keystore alias. |
| Property picks fallback instead of profile value | Profile property was dropped due to decrypt failure; lower source supplies same key. | Check `invalid.<key>` in response and PropertySource order. |
| YAML parses but does not decrypt | Wrong quote/prefix syntax or altered ciphertext. | Cross-check `{cipher}` rules for YAML and `.properties`. |

## 11. Encrypting Plaintext Files and Remote Property Sources

### 11.1. Plain-Text File Decryption Is Off by Default

By default, Spring Cloud Config does not decrypt encrypted values in every plain-text file served as a resource. If that feature is required, the documentation guides configuring Config Server:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: true
          plain-text-encrypt: true
~~~

This feature only supports files with YAML, JSON, and `.properties` extensions. If a client requests an unsupported extension, encrypted values in that file will not be decrypted.

### 11.2. Distinguishing the Environment Endpoint and Resource Endpoint

Config Server can expose:
- The Environment resource, typically used by Config Client to load property sources.
- The Resource/plain-text file endpoint, used when a client needs to fetch a specific file.

Do not assume that the Environment endpoint's encrypted value processing rules automatically apply to all file/resource types. Check supported extensions and the `plain-text-encrypt` flag when designing flows.

## 12. Multiple Keys and Key Rotation

### 12.1. Specifying a Key Alias in Ciphertext

When using a keystore with multiple keys, Config Server supports an additional prefix before the ciphertext, for example:

~~~yaml
app:
  database:
    password: '{cipher}{key:orders-key-v2}ENCRYPTED_VALUE'
~~~

The `{key:orders-key-v2}` prefix tells the locator which alias to use. `TextEncryptorLocator` receives this metadata to locate the right encryptor. With the default locator and a keystore, the alias can be used to select the key.

Metadata prefixes sit after `{cipher}` and before the ciphertext. Do not add an alias unless that alias is already present in the keystore of the component responsible for decryption.

### 12.2. Controlled Rotation Procedure

A typical rotation workflow:

1. Create a new key/alias in the keystore or secret manager.
2. Provision the new key to the server/clients per the chosen decryption model.
3. Verify all instances that need to decrypt have the new key.
4. Re-encrypt secrets using the new key.
5. Update `{key:new-alias}` in the configuration repository if using multiple aliases.
6. Deploy/update configurations in a compatible order.
7. Verify decryption and business behavior.
8. Revoke the old key once no ciphertext or client still requires it.
9. Record audit logs and maintain a rollback plan during the transition period.

Do not delete the old key before all ciphertext has been re-encrypted and all clients have moved to the new alias. If a key is compromised, treat it as a security incident: assess ciphertext exposure, rotate the underlying real credentials, and audit Git history/logs.

## 13. Testing Both Models

### 13.1. Testing Server-Side Decryption

1. Configure the key on Config Server.
2. Encrypt a lab value using `/encrypt`.
3. Store the ciphertext with the `{cipher}` prefix in the repository.
4. Request the Environment resource from Config Server for the application/profile.
5. Verify the response contains plaintext under the original property name, with no ciphertext remaining.
6. Start Config Client and verify the Environment/beans receive plaintext.
7. Test with a wrong key in the test environment and verify `invalid.<key>`.

Never use production secrets for testing. Use dummy values and dedicated keys for test profiles.

### 13.2. Testing Client-Side Decryption

1. Configure Config Server with `spring.cloud.config.server.encrypt.enabled=false`.
2. Store a `{cipher}...` property in the repository.
3. Supply the matching key to Config Client via a local/secret source.
4. Request the Environment resource from Config Server.
5. Verify the server payload still contains ciphertext.
6. Start Config Client and verify the final Environment contains plaintext.
7. Run a test with a client missing the key or with a wrong key; verify decryption fails and ciphertext is not used as a credential.

### 13.3. Verification Matrix

| ID | Model | Scenario | Expected Verification Result |
| --- | --- | --- | --- |
| C1 | Server-side | Valid ciphertext, server has key. | Server returns plaintext to client. |
| C2 | Server-side | Server lacks matching key. | Response contains `invalid.<key>` by default. |
| C3 | Server-side | `prefix-invalid-properties` disabled. | Ciphertext may appear under original key; must not be treated as plaintext. |
| C4 | Client-side | Server disables outgoing decrypt, client has right key. | Server returns ciphertext; client Environment has plaintext. |
| C5 | Client-side | Client lacks key. | Client cannot decrypt; application must not treat ciphertext as a valid secret. |
| C6 | Client-side | Client has wrong key. | Decryption fails and is clearly observable. |
| C7 | Both | YAML uses proper quotes for `{cipher}`. | YAML parses and decrypts correctly. |
| C8 | Both | `.properties` wraps ciphertext in quotes. | Test detects value is not decrypted as expected. |
| C9 | Both | Ciphertext contains `+` or special characters. | `/encrypt` request preserves input data intact. |
| C10 | Multi-key | New alias present in keystore. | Ciphertext with `{key:alias}` decrypts using the matching alias. |
| C11 | Rotation | Ciphertext still uses old alias. | Client/server retaining old key decrypts during transition window. |
| C12 | Plain-text resource | YAML/JSON/properties with `plain-text-encrypt=true`. | Encrypted values are decrypted per extension support. |

## 14. Security and Operations

1. **Protect endpoints:** `/encrypt` and especially `/decrypt` are only for administrative principals. Restrict network access, authentication, authorization, and auditing.
2. **Use TLS:** both ciphertext and plaintext require protection in transit. Do not use unencrypted HTTP over untrusted networks.
3. **Do not store keys next to ciphertext:** the repository holds ciphertext; key material must live in a secret manager, keystore, or key management system.
4. **Restrict Config Server access:** if the server holds private/shared keys, protect the process, filesystem, container secrets, heap dumps, and logs.
5. **Restrict Config Client access:** with client-side decryption, provision private/shared keys only to clients that need those secrets.
6. **Do not log plaintext:** avoid logging `/decrypt` requests, Config Server responses, property dumps, or exceptions containing secrets.
7. **Control fallbacks:** on decryption errors, inspect `invalid.<key>` and fallback sources; never let the application silently use unintended default credentials.
8. **Plan rotation:** support multiple aliases during the transition window and revoke the old key only after completion.
9. **Do not confuse encryption with secret lifecycle:** encrypting ciphertext in Git does not automatically rotate database passwords, tokens, or certificates.
10. **Verify every replica:** client-side decryption requires the key on every instance; one replica missing the key may fail to start while others succeed.

## 15. Completion Checklist

- [ ] Can explain the meaning of the `{cipher}` prefix.
- [ ] Distinguish decryption at Config Server from local decryption at Config Client.
- [ ] Know that Config Server decrypts encrypted properties before returning to clients when configured with a key.
- [ ] Know how to disable server-side outgoing decryption via `spring.cloud.config.server.encrypt.enabled=false`.
- [ ] Know that clients need `encrypt.*` key material available early enough to decrypt.
- [ ] Distinguish `encrypt.key` from `encrypt.keyStore.*`.
- [ ] Explain that the public key encrypts and the private key decrypts.
- [ ] Can use `/encrypt` and `/decrypt` in a secured environment.
- [ ] Prepend `{cipher}` before ciphertext when storing in YAML/properties.
- [ ] Know the differing quoting rules between YAML and `.properties`.
- [ ] Recognize `invalid.<key>` when Config Server fails to decrypt.
- [ ] Understand `prefix-invalid-properties=false` and its implications for ciphertext.
- [ ] Distinguish Environment resources from plain-text resources and `plain-text-encrypt`.
- [ ] Understand `{key:alias}` and the key rotation workflow.
- [ ] Have tests covering both server-side and client-side decryption.
- [ ] Have TLS, access control, auditing, secret management, and a rotation plan in place.

**Official documentation to cross-check for your project version:**

- [Spring Cloud Config – Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html): cipher format, encrypt/decrypt endpoints, decryption errors, and the invalid prefix.
- [Spring Cloud Config – Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html): configuring clients to decrypt locally and disabling server-side outgoing decryption.
- [Spring Cloud Config – Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html): shared keys, keystores, public/private keys, and keeping key material.
- [Spring Cloud Config – Using Multiple Keys and Key Rotation](https://docs.spring.io/spring-cloud-config/reference/server/using-multiple-keys-and-key-rotation.html): aliases, TextEncryptorLocator, and rotation.

Property names, bootstrap behavior, and APIs can vary across release trains. Cross-check your project's Spring Boot/Spring Cloud Config BOM and test Config Server's actual responses before deploying.

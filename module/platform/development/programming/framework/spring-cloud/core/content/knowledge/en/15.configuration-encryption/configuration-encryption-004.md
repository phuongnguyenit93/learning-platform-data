# Keystores, Aliases, and Key Protection Passwords

Spring Cloud Config Server can encrypt sensitive configuration values before storing them in Git or a shared configuration store. With asymmetric RSA encryption, the server uses a **public key** to encrypt and needs the corresponding **private key** to decrypt. A keystore holds the key pair and certificate; the alias selects the exact entry to use, while passwords protect the keystore and the private key.

These three pieces of information serve distinct roles. If `location` is wrong, the server cannot open the key store. If the alias does not exist or points to an entry without a private key, the server may be able to encrypt but cannot decrypt. If the password is wrong, Config Server cannot open the keystore or unlock the private key. Therefore, managing keystores, aliases, and passwords is part of operating encrypted configurations, not merely a step to generate a `.jks` file.

This lesson belongs to the **Configuration Encryption** chapter of the **SPRING_CLOUD_CORE** module. We will create an RSA key pair with `keytool`, configure Config Server, distinguish the store password from the key password, test `/encrypt` and `/decrypt`, store ciphertext in the repository, and perform safe alias rotation.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the roles of a keystore, key pair, certificate, alias, and private-key password.
- Distinguish symmetric encryption from asymmetric encryption in Spring Cloud Config.
- Create a keystore with `keytool` and verify the alias, entry type, and certificate.
- Configure `encrypt.keyStore.location`, `password`, `alias`, `secret`, and `type`.
- Understand the public-key encryption and private-key decryption flow.
- Use `/encrypt` and `/decrypt` to verify keys in a secured environment.
- Store `{cipher}` values in remote configuration and understand when Config Server decrypts before returning them to clients.
- Manage multiple aliases, replace keys, and rotate ciphertext without interrupting configuration reads.
- Protect private keys, passwords, encryption endpoints, and keystore copies in production environments.

## 2. What Are a Keystore, Key Pair, and Alias?

### 2.1. Keystore

A **keystore** is a container managed by the Java KeyStore API. It can hold one or more entries, such as:

- **PrivateKeyEntry:** a private key along with its corresponding certificate chain. The certificate holds the public key and identity information.
- **TrustedCertificateEntry:** a trusted certificate without a private key.

For Spring Cloud Config using RSA, Config Server needs an entry with a public key to encrypt. To decrypt on the server, the entry must have the corresponding private key and the server must be able to unlock that entry.

A keystore can be stored in JKS or PKCS12 format. Spring Cloud Config defaults `encrypt.keyStore.type` to `jks`; if you create a file in a different format, you must configure `type` to match the file created.

### 2.2. Key Pair and Certificate

An RSA key pair consists of:

- **Public key:** used to encrypt data.
- **Private key:** used to decrypt data encrypted with the matching public key.

An X.509 certificate typically binds a public key to subject information and is signed by a CA or self-signed. In the hands-on lab, `keytool -genkeypair` generates a key pair and a self-signed certificate for testing purposes.

The private key cannot be derived from the public certificate. Therefore, you can distribute the certificate/public key to a component that only needs to encrypt, while keeping the private key where decryption takes place.

### 2.3. Alias

An **alias** is the identifier name of an entry inside a keystore. A single keystore can hold multiple key pairs; the alias selects the right entry.

Example:

| Alias | Purpose |
| --- | --- |
| `config-key-2026` | Active key used to encrypt new configurations |
| `config-key-2025` | Old key still needed to decrypt previously published ciphertext |
| `config-key-test` | Dedicated key for testing environments |

An alias is neither the keystore filename nor a password. Changing the alias in configuration does not alter the key content; it only changes which entry Config Server looks up in the keystore.

### 2.4. Two Types of Passwords

Spring Cloud Config has two password settings to distinguish:

| Property | Role |
| --- | --- |
| `encrypt.keyStore.password` | Opens the keystore container |
| `encrypt.keyStore.secret` | Unlocks the selected private-key entry; if omitted, `secret` defaults to the keystore password |

The name `secret` in Spring Cloud Config configuration is the secret value used for the key entry. With JKS, the store password and key password can differ. With PKCS12 on JDK 11 and later, `keytool` may ignore a separate key password; in practice, set the key password equal to the store password to avoid warnings and configuration mismatches.

Do not reuse example values from documentation as real passwords. Generate dedicated, strong passwords and store them in a secret manager or the platform's credential mechanism.

## 3. Symmetric and Asymmetric Encryption in Config Server

Spring Cloud Config supports two primary options:

| Mechanism | Key | Advantages | Notes |
| --- | --- | --- | --- |
| Symmetric | One secret used for encryption and decryption | Simple configuration, easy to deploy | Both encrypting and decrypting components must hold the same secret |
| Asymmetric RSA | Public key encrypts, private key decrypts | Can distribute the public key more broadly and restrict where the private key is kept | Must manage key pairs, aliases, certificates, and key lifecycle |

With a symmetric key, Config Server uses `encrypt.key` or the `ENCRYPT_KEY` environment variable. With an RSA keystore, configure `encrypt.keyStore.*`. `encrypt.key` cannot replace a keystore for asymmetric mode.

RSA flow diagram:

~~~mermaid
flowchart LR
    P[Plaintext secret] --> PUB[Public key]
    PUB --> ENC[Encrypt]
    ENC --> C[Ciphertext in Git]
    C --> DEC[Decrypt]
    PRIV[Private key in keystore] --> DEC
    DEC --> OUT[Plaintext for authorized client]
~~~

If Config Server decrypts values before returning configuration, the private key resides on the server and the client receives plaintext over a protected connection. If you want clients to decrypt locally, you must design private key distribution to authorized clients and configure the server not to decrypt outgoing properties. Do not scatter the private key to every client just to skip a server-side processing step.

RSA is suitable for encrypting short configuration values such as passwords, tokens, or secret keys. Maximum plaintext size depends on key length and padding; do not use RSA directly to encrypt large files or entire configuration documents. For large data, use an appropriate data encryption mechanism and protect the data key with a key-management service.

## 4. Creating a Keystore with keytool

`keytool` is distributed with the JDK. You can use this command to generate an RSA key pair and a self-signed certificate for testing.

### 4.1. Creating a JKS for the Lab

Create the keystore:

~~~bash
keytool -genkeypair \
  -alias config-key-2026 \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -storetype JKS \
  -keystore config-server.jks \
  -dname "CN=Config Server, OU=Platform, O=Example" \
  -validity 3650
~~~

`keytool` will prompt for:

1. The password protecting the keystore.
2. The password protecting the private key of alias `config-key-2026`.

With JKS, two different passwords can be used. In practice, do not put real passwords on the command line or in committed scripts. The command above lets `keytool` prompt interactively, avoiding storing values directly in shell history.

### 4.2. Creating a PKCS12 Keystore

PKCS12 is a common keystore exchange format. You can generate the file as follows:

~~~bash
keytool -genkeypair \
  -alias config-key-2026 \
  -keyalg RSA \
  -keysize 3072 \
  -sigalg SHA256withRSA \
  -storetype PKCS12 \
  -keystore config-server.p12 \
  -dname "CN=Config Server, OU=Platform, O=Example" \
  -validity 3650
~~~

On JDK 11 and later, PKCS12 may not support differing store passwords and key passwords; `keytool` may warn that the key password is ignored. Use the same password for both and configure `encrypt.keyStore.secret` with the same value as `encrypt.keyStore.password`, or use a format/provider with verified behavior if policy requires separate passwords.

### 4.3. Inspecting the Keystore

List entries:

~~~bash
keytool -list -v \
  -keystore config-server.jks \
  -storetype JKS
~~~

Check the following details:

- The alias is indeed `config-key-2026`.
- The entry type is `PrivateKeyEntry`.
- The certificate has an RSA public key.
- The certificate validity dates and expiration align with policy.
- The certificate fingerprint matches the verified/approved copy.

If the entry is `trustedCertEntry`, the keystore contains only a trusted certificate and no private key for decryption. That is suitable for a component that only encrypts, but insufficient for Config Server to decrypt ciphertext.

### 4.4. Viewing the Alias and Exporting the Certificate

View certificate information:

~~~bash
keytool -exportcert \
  -alias config-key-2026 \
  -keystore config-server.jks \
  -storetype JKS \
  -rfc \
  -file config-key-2026.crt
~~~

This command exports the certificate/public key, not the private key. You can use the certificate to distribute the public key to components that only need to encrypt or to verify fingerprints. Do not send a keystore file containing a `PrivateKeyEntry` through public certificate distribution channels.

## 5. Configuring the Keystore for Config Server

Place the keystore in a location accessible only to Config Server. Local examples may use the classpath for testing; production should mount the file from a secret manager or controlled volume.

### 5.1. Configuring application.yml

Example using JKS:

~~~yaml
encrypt:
  keyStore:
    location: "file:/run/secrets/config-server/config-server.jks"
    password: "${ENCRYPT_KEYSTORE_PASSWORD}"
    alias: "config-key-2026"
    secret: "${ENCRYPT_PRIVATE_KEY_PASSWORD}"
    type: "JKS"
~~~

Meaning:

| Property | Example | Meaning |
| --- | --- | --- |
| `location` | `file:/run/secrets/config-server/config-server.jks` | Resource path to the keystore |
| `password` | `ENCRYPT_KEYSTORE_PASSWORD` | Password to open the keystore |
| `alias` | `config-key-2026` | Default selected alias |
| `secret` | `ENCRYPT_PRIVATE_KEY_PASSWORD` | Password to unlock the private-key entry |
| `type` | `JKS` | Keystore format |

These property names belong to Spring Cloud Config's `encrypt.keyStore.*` namespace. For PKCS12, replace `location` with the `.p12` file and set `type: PKCS12`; align passwords with the provider/JDK behavior.

### 5.2. Using Classpath in a Local Environment

For quick practice, you can place the keystore in `src/main/resources` and configure:

~~~yaml
encrypt:
  keyStore:
    location: "classpath:/config-server.jks"
    password: "${ENCRYPT_KEYSTORE_PASSWORD}"
    alias: "config-key-2026"
    secret: "${ENCRYPT_PRIVATE_KEY_PASSWORD}"
    type: "JKS"
~~~

Do not package a private keystore and password inside a shared JAR. If the file is on the classpath, anyone who obtains the artifact can extract the file; protecting the password elsewhere does not eliminate the risk of overly broad private key distribution.

### 5.3. Supplying Passwords from the Environment

On Linux/macOS:

~~~bash
export ENCRYPT_KEYSTORE_PASSWORD='load-from-secret-manager'
export ENCRYPT_PRIVATE_KEY_PASSWORD='load-from-secret-manager'
java -jar config-server.jar
~~~

On PowerShell:

~~~powershell
$env:ENCRYPT_KEYSTORE_PASSWORD = "load-from-secret-manager"
$env:ENCRYPT_PRIVATE_KEY_PASSWORD = "load-from-secret-manager"
java -jar config-server.jar
~~~

The strings above are only placeholders to demonstrate passing variables. In production, the platform should inject secrets from Vault, encrypted Kubernetes Secrets, a cloud secret manager, or an equivalent credential mechanism. Do not write real values into `application.yml`, Git, Dockerfiles, image layers, or logs.

If the application uses legacy bootstrap (`spring-cloud-starter-bootstrap` or `spring.cloud.bootstrap.enabled=true`), encryption properties need to be loaded during the bootstrap phase per your release train's guidance. With modern Config Data imports, check the Spring Cloud Config documentation for your exact version to place properties in a source loaded early enough.

## 6. Default Alias and Multiple Aliases

### 6.1. Default Alias

`encrypt.keyStore.alias` specifies the default key entry that Config Server uses when there is no explicit alias directive in the ciphertext.

Example:

~~~yaml
encrypt:
  keyStore:
    alias: "config-key-2026"
~~~

When calling `/encrypt` without specifying an alias, the server uses this default alias. If the alias is misspelled or does not exist in the keystore, key retrieval fails.

### 6.2. Selecting an Alias per Ciphertext

Spring Cloud Config supports the `{key:alias}` prefix before the ciphertext. Example:

~~~yaml
payment:
  gateway:
    password: '{cipher}{key:config-key-2025}BASE64_CIPHERTEXT'
database:
  password: '{cipher}{key:config-key-2026}BASE64_CIPHERTEXT'
~~~

When decrypting, Config Server reads the alias in the prefix and asks the locator to fetch the corresponding key. This allows the same Config Server to hold multiple key pairs in one keystore during a key transition period.

The alias recorded in the ciphertext becomes a piece of metadata that must remain stable. Do not delete an old alias while the repository still contains `{cipher}` values referencing that alias.

### 6.3. The secret Prefix

Ciphertext can also carry `{secret:...}` to specify the key entry's secret. If there is no secret prefix, the default locator uses the keystore password as the default secret according to the Spring Cloud Config documentation. If a separate secret is used, it must be protected and a custom `SecretLocator` should be considered to manage secrets according to system policy.

Do not place a plaintext secret in the repository simply because the ciphertext is encrypted. If the secret appears in `{secret:...}`, it can undermine the benefit of keeping the private-key entry protected.

## 7. Encrypting and Decrypting with Endpoints

Config Server exposes `/encrypt` and `/decrypt` when keys are configured. These endpoints are sensitive administrative interfaces and must be protected with authentication, authorization, TLS, and network policies.

### 7.1. Encrypting a Value

Send plaintext via POST:

~~~bash
curl -sS -X POST \
  --data-binary 'change-this-example-password' \
  http://localhost:8888/encrypt
~~~

The response is ciphertext. If Config Server has the default alias `config-key-2026`, the server uses that alias.

When you need to select a specific alias, send the key prefix along with the plaintext using Config Server's supported syntax:

~~~bash
curl -sS -X POST \
  --data-binary '{key:config-key-2026}change-this-example-password' \
  http://localhost:8888/encrypt
~~~

Verify the alias syntax against your deployed release train. The `/encrypt` endpoint is not a public API for end users; grant access only to authorized pipelines or operators allowed to generate ciphertext.

### 7.2. Decrypting for Verification

~~~bash
curl -sS -X POST \
  --data-binary 'BASE64_CIPHERTEXT' \
  http://localhost:8888/decrypt
~~~

For values encrypted under a specific alias, verify the ciphertext in the full format stored by Config Server, including `{cipher}` and `{key:...}` prefixes if present. Perform decryption verification only in a secured terminal or administrative environment; never put plaintext into tickets, chat, CI logs, or long-lived outputs.

### 7.3. Checking Errors

If the server cannot decrypt a value, Config Server omits the ciphertext value from the returned property source and adds a key prefixed with `invalid` with a not-applicable indicator value (typically `<n/a>`). This handling prevents ciphertext from being mistakenly treated by the application as a valid password or secret.

When encountering an error:

- Check whether the alias exists and the entry contains a private key.
- Check the keystore type and location.
- Check the store password and key-entry secret.
- Check whether the ciphertext was produced by the matching key pair.
- Check whether the `{key:...}` prefix points to an old alias that was already deleted.

Do not fix this by removing the prefix or replacing ciphertext with plaintext directly in the production repository. First identify the correct key and data provenance.

## 8. Storing Ciphertext in the Configuration Repository

After encrypting, store the ciphertext with the `{cipher}` prefix.

In `application.yml`:

~~~yaml
spring:
  datasource:
    username: app_user
    password: '{cipher}BASE64_CIPHERTEXT'
~~~

If an explicit alias is needed:

~~~yaml
spring:
  datasource:
    username: app_user
    password: '{cipher}{key:config-key-2026}BASE64_CIPHERTEXT'
~~~

YAML requires quoting values starting with `{cipher}` to prevent the parser from interpreting them as flow mappings. For `.properties` files, `{cipher}...` values must not be quoted:

~~~properties
spring.datasource.username=app_user
spring.datasource.password={cipher}BASE64_CIPHERTEXT
~~~

Do not quote ciphertext values in `.properties` if your Config Server version expects the `{cipher}` prefix at the start of the value; quotation marks can prevent detection/decryption from working as expected.

### 8.1. Config Server Decrypts Before Returning to Clients

By default, Config Server detects values starting with `{cipher}` and decrypts them before sending the property source over HTTP. Git holds ciphertext at rest; authorized clients receive plaintext values after server decryption.

This protects secrets at rest in the repository, but does not replace:

- TLS between Config Client and Config Server.
- Authentication/authorization for Config Server.
- Repository permissions and branch protection.
- Protecting logs, heap dumps, actuator endpoints, and environment variables on clients.
- Managing private keys and passwords on the server.

If Config Server decrypts, any client permitted to fetch configuration can receive plaintext. Grant permissions per application and environment; do not treat ciphertext in Git as a reason to share configurations broadly.

### 8.2. Client-Side Decryption

Another architecture is having Config Server return ciphertext to clients so clients hold the private key and decrypt locally. When `encrypt.*` is configured for the server to serve encryption/decryption endpoints but you want ciphertext preserved in responses, set:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
~~~

Spring Cloud Config documentation requires placing `spring.cloud.config.server.encrypt.enabled=false` in `bootstrap.yml` or `bootstrap.properties` for serving encrypted properties mode. Use this model only when you have a plan to distribute private keys, aliases, and passwords to each authorized client; this increases the number of places where keys must be protected.

## 9. Alias Lifecycle Management and Key Rotation

Key rotation is not just creating a new alias and deleting the old one. Every published ciphertext must remain decryptable throughout the transition window.

### 9.1. Rollback-Safe Rotation Procedure

Suppose the current alias is `config-key-2025` and the new alias is `config-key-2026`.

1. Generate a new key pair with alias `config-key-2026`.
2. Update the keystore on all Config Server instances to contain both the old and new aliases.
3. Verify both aliases can retrieve keys and decrypt test ciphertext.
4. Switch the default alias to `config-key-2026` for new values.
5. Re-encrypt each property to be migrated and save the `{key:config-key-2026}` prefix.
6. Deploy the repository and confirm every Config Server replica returns configuration successfully.
7. Verify no ciphertext still references `config-key-2025`.
8. Only after the agreed rollback window expires, remove the old alias from the keystore.

### 9.2. Transition Diagram

~~~mermaid
flowchart TD
    A[Keystore: old alias] --> B[Add new alias]
    B --> C[Both aliases available on all servers]
    C --> D[Encrypt new values with new alias]
    D --> E[Update ciphertext references]
    E --> F[Verify every property decrypts]
    F --> G{Any old alias references?}
    G -->|Yes| E
    G -->|No| H[Keep rollback window]
    H --> I[Remove old alias]
~~~

If an issue occurs after switching over, revert to ciphertext using the old alias while both aliases remain in the keystore. Do not delete the old alias before completing verification and waiting out the rollback period.

### 9.3. When Is Rotation Needed?

Rotating on a short schedule is not strictly necessary if a key only encrypts a few configuration bytes and is well protected. However, you must rotate keys if there is any sign of private key/password compromise, loss of keystore control, cryptographic policy changes, or organizational compliance requirements.

If a private key has been compromised, assume ciphertext encrypted with that key is at risk of decryption. Merely changing the alias for new values does not make old ciphertext safe again; re-encrypt with a new key and evaluate rotating the underlying secrets themselves.

## 10. Protecting Keystores and Passwords in Production

### 10.1. File Location

- Use `file:` pointing to a protected volume or secret mount in production.
- Restrict file read permissions to the user running Config Server.
- Do not package a private keystore inside a JAR, Docker image, or source repository.
- Do not mount the keystore onto clients that do not need to decrypt.
- Back up keystores and passwords following secret backup procedures; test recovery capability.

### 10.2. Passwords

- Retrieve passwords from a secret manager or credential management platform.
- Never write passwords into Git, plaintext CI variables, Dockerfiles, or logs.
- Scope secret read permissions by workload identity/service account.
- Maintain a password rotation process and test recovery before deploying.
- With PKCS12, verify JDK/provider behavior; if the key password must match the store password, manage them as the same secret rather than creating two values that cause confusion.

### 10.3. Endpoints and Network

- Protect `/encrypt` and `/decrypt` with Spring Security.
- Allow only authorized pipelines or operators to call the endpoints.
- Expose them only on internal management/network segments.
- Use HTTPS/TLS; do not send plaintext over unsecured HTTP.
- Do not log endpoint request/response bodies to access logs or traces.
- Do not use the decrypt endpoint in health checks or public business flows.

### 10.4. Public Key and Private Key

If encryption happens in one component and decryption in another:

- Distribute the public key/certificate to the encrypting party.
- Keep the private key in the keystore at the decrypting component.
- Verify the certificate fingerprint before distribution.
- Revoke and replace the key if an incident occurs.

Config Server may only need the public key if it only performs encryption while another component holds the private key to decrypt. If Config Server must decrypt properties itself before returning them to clients, it must have access to the corresponding private key.

## 11. Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Config Server fails to start | Wrong location or cannot open keystore | Check resource path, mount, and file read permissions |
| `UnrecoverableKeyException` | Wrong store password or key-entry secret | Check `password`, `secret`, and the matching entry |
| Alias does not exist | Typo in configuration/ciphertext alias or not yet deployed | Run `keytool -list -v` and verify the alias |
| Can encrypt but cannot decrypt | Keystore only has certificate/public key or wrong private key/password | Verify the entry is `PrivateKeyEntry` and check private-key access |
| Old ciphertext fails to decrypt | Old alias was deleted or key pair changed | Restore old alias/key from backup and find referencing ciphertext |
| `/encrypt` returns error | No valid encryptor/key or malformed request | Check keystore config, alias, and secret-masked logs |
| Client receives `invalid.*` | Config Server cannot decrypt the property | Check key, alias, password, ciphertext, and server logs |
| PKCS12 warns key password is ignored | Provider/JDK does not support separate key-entry passwords | Align store/key passwords and configure `secret` accordingly |
| YAML fails to decrypt value | `{cipher}` is unquoted or syntax/prefix was altered | Check the value in YAML and ciphertext formatting |

Do not print the entire `encrypt.*` configuration or passwords to logs for diagnostics. You may log the alias name, keystore type, load status, and certificate fingerprint after confirming that level of detail is safe to disclose.

## 12. Hands-On Exercises

### Exercise 1 — Create and Inspect a Keystore

1. Use `keytool -genkeypair` to create a JKS keystore with alias `config-key-lab`.
2. Run `keytool -list -v`.
3. Confirm the entry is `PrivateKeyEntry`.
4. Record the certificate fingerprint and validity period.
5. Try opening the keystore with an incorrect password and observe the error.

### Exercise 2 — Configure Config Server

1. Configure `encrypt.keyStore.location`, `password`, `alias`, `secret`, and `type`.
2. Start Config Server.
3. Send test plaintext to `/encrypt`.
4. Send the ciphertext to `/decrypt`.
5. Confirm the plaintext matches the original input.

### Exercise 3 — Try a Second Alias

1. Add a key pair with alias `config-key-next` to the keystore.
2. Encrypt a value with the `{key:config-key-next}` prefix.
3. Store the ciphertext with the new alias in a test configuration file.
4. Verify Config Server can decrypt both the default alias and the new alias.

### Exercise 4 — Key Rotation

1. Keep old ciphertext using alias `config-key-lab`.
2. Switch the default alias to `config-key-next`.
3. Re-encrypt a property and update its alias prefix.
4. Verify all properties remain readable.
5. Delete the old alias only after confirming no references remain and the rollback window has elapsed.

**Completion criteria:** you can explain what each password protects, identify which alias a ciphertext requires, prove Config Server can encrypt/decrypt using the corresponding key pair, and rotate keys without breaking decryption of previously issued data.

## 13. Summary

A keystore is a container storing key pairs and certificates; an alias selects a specific entry; `encrypt.keyStore.password` opens the keystore and `encrypt.keyStore.secret` unlocks the private-key entry. With RSA, the public key encrypts and the private key decrypts. Config Server can use a default alias or an alias specified in the ciphertext's `{key:alias}` prefix.

A safe workflow consists of creating the keystore, verifying `PrivateKeyEntry`, mounting files and passwords from protected secret sources, testing `/encrypt`/`/decrypt`, storing ciphertext with the `{cipher}` prefix, and rotating aliases through rollback-safe phases. Never commit private keystores or passwords, never expose encryption/decryption endpoints publicly, and never delete an old alias while the repository still contains ciphertext depending on it.

## References

- [Spring Cloud Config — Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html): symmetric key, RSA keystore, location, password, alias, and type.
- [Spring Cloud Config — Creating a Key Store for Testing](https://docs.spring.io/spring-cloud-config/reference/server/creating-a-key-store-for-testing.html): creating key pairs with `keytool`, configuring keystores, and PKCS12 notes on JDK 11 and later.
- [Spring Cloud Config — Using Multiple Keys and Key Rotation](https://docs.spring.io/spring-cloud-config/reference/server/using-multiple-keys-and-key-rotation.html): `{key:alias}` prefix, secret locators, and changing aliases during key rotation.
- [Spring Cloud Config — Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html): keeping ciphertext in responses for client-side decryption.
- [Java Keytool Documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): commands for managing keystores, key pairs, certificates, and aliases.

Keystore properties and behaviors should be verified against your deployed Spring Cloud release train, JDK, and security provider. The JKS/PKCS12 examples in this lesson illustrate configuration; test unlocking key entries and decrypting on the exact production runtime before release.

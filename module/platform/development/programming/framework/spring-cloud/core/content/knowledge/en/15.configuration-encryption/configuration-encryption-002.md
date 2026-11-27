# The Role of TextEncryptor and Required Encryption Libraries

In a Spring Cloud system, configuration often contains sensitive information such as database passwords, access tokens, API keys, or credentials for external services. These values may be stored in a configuration repository, transferred through Config Server, and distributed to multiple instances. Simply restricting read permissions on the repository is not enough: if ciphertext is exposed alongside its storage, a reader would still need a separate key to decrypt it.

Spring Security Crypto provides the **`TextEncryptor`** contract for encrypting and decrypting strings. Spring Cloud Config uses this encryption mechanism to support the `/encrypt` and `/decrypt` endpoints and the `{cipher}` marker in configuration repositories. The encryption library must be on the classpath, yet choosing the library is only part of the design; keys, algorithms, access control, and key rotation lifecycles determine whether the system is secure in operation.

This lesson belongs to the **Configuration Encryption** chapter of the `SPRING_CLOUD_CORE` module. The goal is to understand the role of `TextEncryptor`, distinguish `spring-security-crypto` from RSA support in `spring-security-rsa`, know which dependencies are needed for each scenario, and grasp how Spring Cloud Config uses encryptors without exposing keys in the repository.

## 1. What Is `TextEncryptor`?

`TextEncryptor` is an interface in Spring Security Crypto, under the `org.springframework.security.crypto.encrypt` package. Its contract focuses on two operations:

- `encrypt(String text)`: transforms plaintext into ciphertext that can be stored or transmitted.
- `decrypt(String encryptedText)`: recovers plaintext from the corresponding ciphertext.

API-level usage example:

```java
import org.springframework.security.crypto.encrypt.TextEncryptor;

public class ConfigValueService {
    private final TextEncryptor encryptor;

    public ConfigValueService(TextEncryptor encryptor) {
        this.encryptor = encryptor;
    }

    public String protect(String plainValue) {
        return encryptor.encrypt(plainValue);
    }

    public String reveal(String cipherValue) {
        return encryptor.decrypt(cipherValue);
    }
}
```

The interface does not dictate where the application retrieves keys from, where keys are stored, who is authorized to call the decryption function, or how ciphertext is stored in a database or Git. Those decisions belong to the implementation and the overarching architecture.

### 1.1. TextEncryptor Is Not a Key Management System

`TextEncryptor` takes plaintext or ciphertext and performs a transformation. It does not inherently provide a secure key store, does not handle user authorization, and does not automatically rotate keys when credentials change.

An application can construct a `TextEncryptor` from a password/salt, or use an implementation based on an asymmetric key pair. However, the keys and required parameters must be supplied from a trusted source, such as a secret manager, a protected keystore, or securely provisioned environment variables.

### 1.2. Encryption Differs from Encoding and Hashing

| Concept | Can Original Value Be Recovered? | Purpose |
| --- | --- | --- |
| Encoding, e.g., Base64 | Yes, without a secret key | Representing data in another format |
| Encryption | Yes, if the appropriate key is available | Protecting data that must be decrypted later |
| Hashing | No, by design | Comparing/verifying integrity or storing verifiers |

Config Server needs to decrypt passwords or tokens for clients to use, so this is a **reversible encryption** problem, not hashing. For user passwords used for login authentication, use password hashing via `PasswordEncoder` with an appropriate algorithm; do not use `TextEncryptor` to store user passwords in a decryptable form.

## 2. Encryption Libraries in the Spring Ecosystem

Two commonly encountered artifacts serve different roles:

| Artifact | Main Components | When Needed |
| --- | --- | --- |
| `org.springframework.security:spring-security-crypto` | `TextEncryptor`, `Encryptors`, key generators, and crypto primitives supported by Spring Security | When code directly uses the `TextEncryptor` contract or Spring Security Crypto utilities |
| `org.springframework.security:spring-security-rsa` | RSA-based encryption/decryption support and asymmetric key material integration | When implementing RSA/keystore configuration encryption in Spring Cloud Config or using corresponding RSA APIs |

Spring Cloud Config Server may provide an integration layer on top of these libraries. Some dependencies may be pulled in transitively depending on the version and starter in use. Inspect the runtime dependency tree before adding dependencies manually; if RSA is needed and the artifact is not yet on the classpath, add it according to your project's compatible dependency management.

### 2.1. Maven: Dependencies for TextEncryptor

When a standalone Java module needs to use `TextEncryptor`/`Encryptors` directly, the base dependency is:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-crypto</artifactId>
</dependency>
```

If that module also needs the separately provided RSA implementation:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-rsa</artifactId>
</dependency>
```

The second snippet is only needed when using the corresponding RSA support. Do not blindly add both if the dependency graph already provides them or if the application uses a different encryption mode.

### 2.2. Gradle: Dependencies for TextEncryptor

```groovy
dependencies {
    implementation "org.springframework.security:spring-security-crypto"
    // Add only when RSA implementation is needed and not transitively provided.
    implementation "org.springframework.security:spring-security-rsa"
}
```

This is a dependency declaration example. Versions should be managed consistently with Spring Boot/Spring Cloud and the project's dependency management. Avoid pinning an arbitrary RSA/crypto version that differs from the verified library set.

### 2.3. Which Dependencies Does Config Server Need?

A Config Server application typically declares `spring-cloud-config-server` and dependencies managed by the Spring Cloud BOM. If encryption/decryption features are needed, check the release train documentation and runtime tree to confirm the appropriate crypto/RSA libraries are present.

Example of Config Server's primary dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>
```

This dependency provides the centralized configuration server; it is not another name for `TextEncryptor`. `spring-security-crypto` provides the crypto API, while `spring-security-rsa` adds RSA support when needed. Config Server's specific configuration determines the implementation and key material used.

## 3. Creating a TextEncryptor with Spring Security Crypto

Spring Security Crypto provides the `Encryptors` factory to create `TextEncryptor` implementations from a password and salt. Example:

```java
import org.springframework.security.crypto.encrypt.Encryptors;
import org.springframework.security.crypto.encrypt.TextEncryptor;
import org.springframework.security.crypto.keygen.KeyGenerators;

public class TextEncryptionExample {
    public static void main(String[] args) {
        String password = obtainPasswordFromSecretStore();
        String salt = KeyGenerators.string().generateKey();

        TextEncryptor encryptor = Encryptors.text(password, salt);

        String encrypted = encryptor.encrypt("db-password");
        String decrypted = encryptor.decrypt(encrypted);

        // API illustration only. Do not print sensitive plaintext/ciphertext in production.
    }

    private static String obtainPasswordFromSecretStore() {
        throw new UnsupportedOperationException("Provide a managed secret source");
    }
}
```

This is an API example, not a complete deployment configuration. `password` must be retrieved from a secret source; do not hard-code it or commit it to the repository. `salt` must be managed consistently with the encrypted data. If you generate a new salt on every run without storing the corresponding salt, older data may become undecryptable.

### 3.1. Password and Salt Have Different Roles

- **Password/secret** is the secret used to derive the encryption key.
- **Salt** is supplementary data for the key derivation process; it is not the password and usually does not need to be kept secret like the key.
- **Ciphertext** is the encrypted output; it can be stored in the configuration repository, though access control and integrity protection are still necessary.

Do not pick a weak fixed salt or reuse example values from documentation. Follow the requirements of the API and library in use, generate a properly formatted random salt, and store it alongside the metadata needed for decryption. Changing the salt or password without a migration plan can render old ciphertext undecryptable.

### 3.2. Choosing an Implementation Based on Requirements

`Encryptors` provides factory methods with different security properties and output formats. Do not assume that all `TextEncryptor` instances are compatible with one another merely because they implement the same interface.

When selecting an implementation, determine:

1. How the key is derived from the secret/password.
2. Which encryption algorithm and mode are used.
3. How the IV/nonce/salt is generated and stored.
4. How ciphertext integrity is verified.
5. Output format and compatibility across library upgrades.
6. How versions/key IDs are managed to decrypt previously encrypted data.

Do not invent your own algorithm, stitch primitives together, or strip ciphertext authentication tags for "compatibility." Use an implementation supported by the library and review the security documentation for that specific version.

## 4. TextEncryptor in Spring Cloud Config

Spring Cloud Config supports encrypting configuration values so repositories can store ciphertext instead of plaintext. Config Server exposes encryption/decryption endpoints and processes values marked with `{cipher}` when reading configuration.

```mermaid
flowchart TD
    A[Secret plaintext] --> B[POST /encrypt on Config Server]
    B --> C[TextEncryptor / key configuration]
    C --> D[Ciphertext]
    D --> E[Config repository with {cipher}]
    E --> F[Config Server reads property source]
    F --> G[Decrypt using matching encryptor and key]
    G --> H[Client receives configuration per server mechanism]
```

The diagram depicts the commonly used server-side decryption model. You must configure the server with access to the key to decrypt; if the architecture chooses client-side decryption, key distribution and client behavior must be designed separately. Do not infer the decryption location solely from the presence of ciphertext in the repository.

### 4.1. `/encrypt` and `/decrypt` Endpoints

Config Server provides HTTP POST endpoints to encrypt or decrypt content. Local example:

```bash
curl -X POST \
  -H "Content-Type: text/plain" \
  --data-binary "sample-secret" \
  http://localhost:8888/encrypt
```

The endpoint returns ciphertext. That value can be placed in the configuration repository with the `{cipher}` prefix:

```yaml
spring:
  datasource:
    username: app_user
    password: "{cipher}AQB...ciphertext..."
```

To test decryption in a secured test environment:

```bash
curl -X POST \
  -H "Content-Type: text/plain" \
  --data-binary "AQB...ciphertext..." \
  http://localhost:8888/decrypt
```

The values in the examples are placeholders. Do not put real secrets into shell history, terminal logs, or documentation. Do not call endpoints on a production server just for testing without authorization and an approved procedure.

### 4.2. What Does the `{cipher}` Marker Mean?

`{cipher}` is a marker telling Config Server that a property value is encrypted. Example:

```yaml
catalog:
  api-token: "{cipher}AQB..."
```

When Config Server reads a property source, it can process the marker and decrypt the value according to the encryptor configuration. The marker is not an encryption algorithm, is not a key, and does not make ciphertext any safer if the key is compromised.

If a value lacks the marker, Config Server normally treats it as a regular configuration value. Therefore, manage secret encryption consistently and audit the repository to prevent accidental plaintext commits.

### 4.3. Decryption Failures

Decryption can fail if:

- The server lacks the appropriate key or keystore.
- The ciphertext was generated by a different key/version.
- The ciphertext was truncated, re-encoded, or modified.
- The implementation/algorithm/parameters are incompatible.
- The keystore has the wrong password, alias, or cannot be read.

Production services should not keep running with an undecryptable placeholder if that property is a required credential. Fail startup explicitly or mark the instance as not ready per policy, while avoiding logging plaintext or keys in error messages.

## 5. Configuring a Symmetric Key for Config Server

With symmetric encryption, the same secret key is used to encrypt and decrypt. Spring Cloud Config can accept the key via the `encrypt.key` property.

Example:

```yaml
encrypt:
  key: ${CONFIG_ENCRYPT_KEY}
```

The `CONFIG_ENCRYPT_KEY` variable must be supplied by a secret manager or the platform's secret provisioning mechanism. Do not place the real value directly in `application.yml`, Config Server's Git repository, or container images.

### 5.1. Advantages and Limitations

Advantages:

- Relatively simple configuration.
- A single secret can be used with the corresponding symmetric implementation.
- Suitable when a group of servers is managed within a clear trust boundary.

Limitations:

- The server must hold a secret capable of decrypting.
- If multiple systems need to decrypt, secret distribution must be tightly controlled.
- If the secret is compromised, ciphertexts can be decrypted if an attacker has the data and algorithm.
- Key rotation requires a plan to decrypt data encrypted with the old key.

### 5.2. Do Not Store the Key Alongside the Ciphertext

An anti-pattern is storing both `encrypt.key` and the ciphertext in the same repository. Anyone who can read the repository would have everything needed to decrypt, defeating the purpose of separating keys from data.

Separate them as follows:

| Component | Appropriate Location |
| --- | --- |
| Ciphertext `{cipher}...` | Configuration repository with read access control |
| Symmetric key | Secret manager, secret mount, or securely injected environment variable |
| Key usage permissions | Dedicated identity/service account for Config Server |
| Audit | System recording secret access and encryption/decryption operations |

## 6. Asymmetric Encryption and RSA Keystores

Asymmetric encryption uses a public/private key pair. The public key can be distributed for encryption; the private key must be protected for decryption. In the Spring Cloud Config model, keystore configuration can supply RSA key material to the server.

Example of keystore properties in YAML format:

```yaml
encrypt:
  key-store:
    location: ${CONFIG_ENCRYPT_KEYSTORE_LOCATION}
    password: ${CONFIG_ENCRYPT_KEYSTORE_PASSWORD}
    alias: config-server-key
    secret: ${CONFIG_ENCRYPT_KEY_PASSWORD}
```

General meanings:

- `location`: keystore location.
- `password`: password to open the keystore.
- `alias`: name of the entry/key to use.
- `secret`: password protecting the private key entry if required by the keystore.

Canonical property names use kebab-case in YAML; corresponding properties are mapped via relaxed binding. Verify exact property names in the Spring Cloud Config documentation for your running release train.

### 6.1. Role of `spring-security-rsa`

`spring-security-rsa` adds RSA support to the Spring Security ecosystem. When Config Server uses RSA/keystores, this dependency must be on the runtime classpath as required by the version. It does not replace `spring-security-crypto` in all use cases and is not a storage vault for private keys.

The private key must still be protected with a keystore password, separately managed secrets, file permissions, and appropriate runtime access controls. Do not put the private key keystore in a configuration repository or shared container image if that image may be broadly distributed.

### 6.2. When to Choose Symmetric vs. Asymmetric?

| Criterion | Symmetric | Asymmetric |
| --- | --- | --- |
| Encryption/decryption key | Same secret | Distinct public key and private key |
| Distribution | Must protect the secret everywhere encryption/decryption occurs | Public key can be distributed more widely; private key stays secret |
| Management | Simpler in small environments with a clear trust boundary | Suitable when encryption and decryption roles must be separated |
| Operations | Rotating the secret requires handling old ciphertext | Managing certificates/keystores, aliases, and private keys |
| Dependency requirements | Appropriate crypto implementation | Requires RSA support and suitable keystore material |

There is no single best choice for every system. The decision depends on the configuration distribution model, how many parties are authorized to encrypt, how private keys are protected, and the key rotation policy.

## 7. TextEncryptor and Customization in Config Server

A standalone application can inject `TextEncryptor` as a regular dependency. However, in Config Server, selecting an encryptor may need to depend on environment, tenant, or key version. Spring Cloud Config provides abstractions to locate the appropriate encryptor based on the configuration environment, such as `TextEncryptorLocator` in supported versions.

A custom locator can address requirements such as:

- Selecting a key/keystore per tenant or application.
- Decrypting ciphertexts created with multiple key versions during a rotation period.
- Retrieving keys from a secret manager instead of configuring them directly in files.
- Enforcing isolation policies between staging and production environments.

Do not implement your own encryption algorithms inside a locator. A locator should only select or provide a verified implementation, while key material must come from an access-controlled secret management system.

### 7.1. Do Not Define a TextEncryptor Bean and Assume Config Server Will Use It

Declaring a `@Bean TextEncryptor` in your application does not guarantee that all Config Server encryption/decryption flows will use that bean. Config Server has its own configuration mechanism and locator. If you need to customize encryptor selection, use the extension points supported by your Spring Cloud Config version and test the `/encrypt`, `/decrypt` endpoints as well as `{cipher}` handling end-to-end.

## 8. Dependencies and Version Compatibility

Configuration encryption sits at the intersection of Spring Cloud Config, Spring Security Crypto, and sometimes Spring Security RSA. Therefore, versions should not be managed independently.

### 8.1. Use the Spring Cloud BOM

For Spring Cloud applications, import the compatible BOM to manage Cloud modules:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

The version of `spring-cloud.version` must match the Spring Boot version according to the official compatibility matrix. The Cloud BOM does not imply every Spring Security artifact shares the exact same version as the Cloud release train; check dependency management and the resolved dependency tree.

### 8.2. Inspecting the Dependency Tree

Maven:

```bash
mvn dependency:tree '-Dincludes=org.springframework.security:*'
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-crypto --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-rsa --configuration runtimeClasspath
```

Check:

1. `spring-security-crypto` is present if code uses `TextEncryptor`/`Encryptors`.
2. `spring-security-rsa` is present if RSA use cases require it.
3. There are no conflicting multiple versions of Spring Security Crypto/RSA.
4. Spring Cloud Config Server and Spring Boot belong to a supported combination.
5. The runtime artifact actually includes the required dependencies, not just the test classpath.

If a starter already brings in a dependency transitively, do not add a duplicate declaration. If you must declare it directly to use the API in code, let dependency management coordinate the version.

## 9. Workflow for Encrypting a Secret for Config Server

An illustrative workflow for a configuration repository:

1. Identify the Config Server instance and environment authorized to perform encryption.
2. Ensure the server is using the correct key/keystore.
3. Send the plaintext to the `/encrypt` endpoint over a protected connection.
4. Receive the ciphertext and verify it can be decrypted with the same key configuration.
5. Store the ciphertext in the property value with the `{cipher}` marker.
6. Commit the ciphertext through the repository review process.
7. Verify Config Server decrypts properly when serving configuration to clients.
8. Inspect logs to ensure neither plaintext nor keys are written out.

Repository example:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/catalog
    username: catalog_app
    password: "{cipher}AQB...ciphertext..."
```

URL and username may not be secrets in every organization, while the password must be protected. Do not assume the entire configuration needs encryption; selective encryption reduces complexity and avoids confusion during debugging.

### 9.1. Testing in a Non-Production Environment

Before applying to production, use a test Config Server with a dedicated test key, encrypt a dummy value, store it in a test repository, and verify the client receives the correct plaintext value. Do not reuse production keys for local or CI environments unless there is an explicit requirement and corresponding security controls.

## 10. Key Management, Access Control, and Key Rotation

Encryption is only meaningful when keys are protected independently from ciphertext.

### 10.1. Key Protection Principles

- Store keys/keystore passwords in a secret manager or equivalent secret provisioning mechanism.
- Only Config Server's identity or the encryption component should be allowed to access the required keys.
- Restrict read permissions on keystore files and access to volume mounts.
- Do not write keys, plaintext, or request bodies containing secrets to logs, traces, or audit payloads.
- Use TLS for traffic between operators, Config Server, and related components.
- Monitor secret access and key configuration changes.
- Maintain secure key backup/restore procedures and test recovery capability before changing production.

### 10.2. Why Does Key Rotation Require a Plan?

Old ciphertext was produced with old keys/parameters. If Config Server only has the new key and no way to decrypt old data, encrypted properties may become unusable after deployment.

A rotation process can include:

1. Create a new key in the key management system.
2. Configure the server to support decrypting ciphertext from the old key during the transition period, if the implementation/locator is designed to select multiple keys.
3. Re-encrypt secrets using the new key.
4. Update the repository and verify clients receive the right values.
5. Monitor for decryption errors and confirm no ciphertext still depends on the old key.
6. Revoke the old key after completing migration and the rollback window.

The ability to retain multiple keys or route by key version depends on the implementation and configuration; do not assume a simple `encrypt.key` property automatically supports zero-downtime rotation. For multi-key requirements, design locator/versioning support and test migration beforehand.

### 10.3. Do Not Reuse One Key Across All Environments

Staging, production, and local should have separate keys. If a staging key is compromised, the blast radius must not extend to production. Likewise, access to staging Config Server should not automatically allow decrypting production secrets.

## 11. Common Errors and Diagnostics

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| `TextEncryptor` not found at compile time | Missing `spring-security-crypto` on compile classpath | Check dependency declarations and dependency tree |
| RSA/keystore not working | Missing RSA support, wrong alias, or keystore config | Check runtime classpath, keystore path, password, alias, and private key entry |
| `/encrypt` or `/decrypt` returns 404 | Config Server encryption support not configured/initialized or different endpoint path | Check server dependencies, version, and startup logs |
| Endpoint returns error when encrypting | Missing matching key/keystore or misconfigured key | Check `encrypt.key`/keystore and secret read permissions |
| Config Server fails to decrypt `{cipher}` | Ciphertext created by another key, corrupted data, or server missing key | Cross-check key version, ciphertext, and server instance |
| Client receives placeholder/unusable value | Decryption failure or misconfigured server/client | Check server logs and returned property sources, without logging plaintext |
| Encrypts fine, but fails to decrypt after restart | Unstable password/salt/keystore or key was changed | Check provisioning source and persistence of key material |
| Works in one environment, fails in another | Environments use different keys/algorithms/parameters | Check key separation and ciphertext provenance |
| Old ciphertext breaks after rotation | Old key was revoked too early | Restore old key per procedure and complete migration |
| Secrets appear in logs | Excessive request/response or debug logging | Mask bodies, reduce logging, and rotate exposed secrets |

Investigation sequence:

1. Determine whether the error occurs at compile time, Config Server startup, endpoint invocation, or when the client receives configuration.
2. Verify the runtime classpath contains the required crypto/RSA dependencies.
3. Confirm the server is using the expected symmetric key or keystore/alias.
4. Check which environment/key version generated the ciphertext.
5. Inspect endpoints and security policies, including TLS/authentication.
6. Confirm `{cipher}` is preserved intact in the repository and not mishandled by YAML/templating.
7. Review decryption error logs and returned property sources without leaking plaintext.
8. During rotation, verify the old key remains supported throughout the migration phase.

## 12. Testing Encryption and Decryption

Tests should verify round-trip symmetry for the same key/configuration while also confirming that the system safely rejects corrupted data or mismatched keys.

| Goal | How to Test | What to Verify |
| --- | --- | --- |
| TextEncryptor round trip | Encrypt plaintext then decrypt ciphertext with the same encryptor | Original plaintext is recovered accurately |
| Key mismatch | Decrypt ciphertext using a different key | Does not return bogus plaintext or silently ignore error |
| Salt persistence | Restart process and reuse stored salt/key | Old ciphertext still decrypts |
| Config Server endpoints | Call `/encrypt` then `/decrypt` in a test environment | Both endpoints use compatible encryptor configuration |
| `{cipher}` integration | Put ciphertext in a test repository and request configuration | Config Server handles the marker properly |
| RSA keystore | Use test keystore, alias, and test password | Encrypts/decrypts with configured key pair |
| Missing key | Start server without required key | Startup/endpoint fails clearly as designed |
| Rotation | Encrypt with old key, transition to new key per plan | Old ciphertext decrypts during the transition window |
| Secret hygiene | Inspect logs/test output | No plaintext, keys, or keystore passwords appear |

Unit test example with the same encryptor:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.encrypt.Encryptors;
import org.springframework.security.crypto.encrypt.TextEncryptor;

class TextEncryptorTest {
    @Test
    void encryptsAndDecryptsWithSameConfiguration() {
        String password = "test-only-secret-from-fixture";
        String salt = "a1b2c3d4e5f60708";
        TextEncryptor encryptor = Encryptors.text(password, salt);

        String plain = "not-a-real-credential";
        String cipher = encryptor.encrypt(plain);

        assertThat(cipher).isNotEqualTo(plain);
        assertThat(encryptor.decrypt(cipher)).isEqualTo(plain);
    }
}
```

The example above uses a fixed test fixture so both sides share the same parameters; do not copy that password/salt to production. Integration tests must use dedicated test keys and verify that Config Server endpoints as well as the `{cipher}` marker work end-to-end.

## 13. Practice: Adding Encryption for catalog-service Configuration

Suppose Config Server serves configuration for `catalog-service` and the repository needs to store the database password as ciphertext.

**Step 1 — Choose a key model:** decide between a symmetric key via `encrypt.key` or an RSA keystore based on distribution and operational requirements. Create a separate key for the test environment.

**Step 2 — Check dependencies:** verify Config Server has the required dependencies; if code directly uses `TextEncryptor`, check `spring-security-crypto`; if using RSA, confirm `spring-security-rsa` is present according to the release train.

**Step 3 — Provision the key securely:** configure Config Server to read the key from a secret manager or secret mount. Do not store the key in Git.

**Step 4 — Encrypt a dummy value:** send a test password to `/encrypt`, obtain the ciphertext, and test `/decrypt` in a secured environment.

**Step 5 — Store the ciphertext:**

```yaml
spring:
  datasource:
    username: catalog_app
    password: "{cipher}AQB...test-ciphertext..."
```

**Step 6 — Test the client:** start `catalog-service` with the right application/profile/label, confirm the configuration is decrypted, and verify the test database connection succeeds.

**Step 7 — Verify secret hygiene:** review Config Server logs, CI output, exceptions, and Actuator to ensure plaintext/keys are not exposed.

**Step 8 — Prepare for rotation:** document the key version and procedure for decrypting old ciphertext before introducing production secrets into the system.

### Self-Check Questions

1. What two core operations does `TextEncryptor` provide?
2. Why is `TextEncryptor` not a key management system?
3. How do `spring-security-crypto` and `spring-security-rsa` differ in role?
4. Why should `TextEncryptor` not be used to store user login passwords?
5. What does the `{cipher}` marker mean in a configuration repository?
6. Which key model is the `encrypt.key` property used for?
7. In RSA keystore configuration, what roles do `location`, `password`, `alias`, and `secret` serve?
8. Why must salt/key parameters be managed consistently to decrypt old ciphertext?
9. Why should keys not be stored in the same repository containing ciphertext?
10. During which phase must key rotation preserve the ability to decrypt old data?

**Answer hints:** (1) `encrypt` and `decrypt`; (2) It does not store, distribute, authorize, or rotate keys; (3) Crypto provides TextEncryptor and crypto APIs, while RSA adds asymmetric encryption support; (4) Login passwords require one-way hashing; (5) Marks an encrypted value for Config Server processing; (6) Symmetric key; (7) Locate the keystore, open the keystore, select the entry, and unlock the private key entry; (8) If parameters differ, old ciphertext may fail to decrypt; (9) Readers could obtain both the ciphertext and the key; (10) Throughout the migration/rollback period until no ciphertext relies on the old key.

## 14. Key Principles to Remember

- `TextEncryptor` is a string encryption/decryption contract; it does not manage keys, authorization, or rotation on its own.
- `spring-security-crypto` provides `TextEncryptor` and crypto utilities; `spring-security-rsa` adds RSA support when the use case requires it.
- Spring Cloud Config uses encryptors for the `/encrypt`, `/decrypt` endpoints and to process `{cipher}`-marked properties.
- `encrypt.key` represents symmetric key configuration; an RSA keystore requires location, password, alias, and the appropriate private-key secret.
- Dependencies and versions must be verified on the runtime classpath and managed under a supported Spring Boot/Spring Cloud combination.
- Ciphertext can live in the repository; keys must be separated and protected via a secret manager/keystore with least-privilege access.
- Do not use reversible encryption instead of password hashing; do not log plaintext, keys, or credentials.
- Rotation must preserve the ability to decrypt old ciphertext during the transition window and include rollback testing.

Understanding the role of `TextEncryptor` and the encryption libraries helps establish clean boundaries between crypto APIs, Config Server, and key management systems. Once dependencies, key material, and operational workflows are clearly defined, Spring Cloud can distribute configurations containing secrets while keeping decryption capability and key-change risks under control.

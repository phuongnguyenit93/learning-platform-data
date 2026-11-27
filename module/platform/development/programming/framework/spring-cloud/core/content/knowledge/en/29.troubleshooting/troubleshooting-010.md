# Unable to Decrypt Cipher Value

When Spring Cloud Config Server reads a property prefixed with `{cipher}`, the server attempts to decrypt it before returning the configuration to the Config Client. If decryption fails, the server removes the cipher value from the property source and adds a key prefixed with `invalid.`, typically with the value `<n/a>`. The application may still start up, receiving a default value from a lower-priority configuration source or missing a required property altogether.

The issue usually stems from mismatched encryption keys, wrong keystore/alias, ciphertext altered during copying, incorrect configuration file syntax, or decryption mode configured on a different side than expected. This lesson guides you through pinpointing the exact failing layer, checking keys and ciphertext, reading Config Server responses, safely restoring configuration, and preventing recurrence.

This lesson belongs to the **Troubleshooting** chapter of the **SPRING_CLOUD_CORE** module. Its scope focuses on Spring Cloud Config encryption/decryption, including symmetric keys, RSA keystores, `{cipher}` prefixes, `/encrypt` and `/decrypt` endpoints, multiple keys/rotation, Config Server/Client configuration, testing, and secret protection.

## 1. Learning Objectives

After this lesson, you can:

- Explain where Spring Cloud Config decrypts properties and the meaning of the `{cipher}` prefix.
- Recognize decryption failures via `invalid.*` properties.
- Distinguish ciphertext errors, key errors, keystore errors, and server/client configuration errors.
- Check symmetric key `encrypt.key` and RSA keystore `encrypt.keyStore.*`.
- Check key aliases via `{key:alias}` and `TextEncryptorLocator`.
- Use `/decrypt` to verify ciphertext against the currently running key configuration.
- Fix quoting errors, special characters, truncated Base64, or URL-decoded values.
- Distinguish server-side decryption from client-side decryption.
- Design a key rotation workflow that still reads old ciphertexts during the transition period.
- Write integration tests to verify the encrypt/decrypt lifecycle.
- Protect endpoints and sensitive data across logs, CI, and repositories.

## 2. Spring Cloud Config Decryption Mechanism

Config Server can store ciphertext in Git or a configuration backend. Encrypted properties typically start with `{cipher}`. When Config Server processes an Environment response, it detects this prefix and decrypts the value before sending it to the client over HTTP.

Example `application.yml` file in the repository:

~~~yaml
spring:
  datasource:
    username: app_user
    password: '{cipher}BASE64_CIPHERTEXT'
~~~

The value `BASE64_CIPHERTEXT` is only an illustrative placeholder, not usable ciphertext. YAML requires wrapping the entire value in single quotes because a string starting with `{` can be parsed as a flow mapping.

In `.properties` files, do not put quotes around the cipher value:

~~~properties
spring.datasource.username=app_user
spring.datasource.password={cipher}BASE64_CIPHERTEXT
~~~

Spring Cloud Config specifies that encrypted values in `.properties` must not be wrapped in quotes; if quotes are present, the server may fail to recognize and decrypt the value. With YAML, quoting is necessary to preserve the `{cipher}...` string intact.

### 2.1. Default Server-Side Decryption

In typical configurations, Config Server decrypts properties before sending them to the Config Client:

~~~mermaid
flowchart LR
    A[Git / Config repository] --> B["{cipher} ciphertext"]
    B --> C[Config Server]
    K[encrypt.key or keystore] --> C
    C --> D[Decrypt property]
    D --> E[Plain value in Environment response]
    E --> F[Config Client]
~~~

The client receives decrypted values. The client does not need to hold the private key just to read configuration in this model. Decryption keys are centralized on Config Server, so the server must be strictly protected.

### 2.2. What Happens When Decryption Fails?

If Config Server cannot decrypt a property, it removes the cipher property from the source and adds a key prefixed with `invalid.`. Example:

~~~json
{
  "propertySources": [
    {
      "name": "application-production.yml",
      "source": {
        "invalid.spring.datasource.password": "<n/a>"
      }
    },
    {
      "name": "application.yml",
      "source": {
        "spring.datasource.password": "fallback-value"
      }
    }
  ]
}
~~~

In the example, Config Server does not return ciphertext as a password. The client may pick up `fallback-value` from a lower-priority source if that property exists. Consequently, the application may not crash yet still fail database connections or silently use an old value.

When you see `invalid.<property>` in an Environment response, treat it as a decryption error to resolve. Do not disable the `invalid.` prefixing mechanism just to make the response look normal; disabling it can forward ciphertext to the client as an ordinary property value.

The property controlling this behavior is:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          prefix-invalid-properties: true
~~~

Keep this default behavior enabled in most systems. Only change it after understanding the consequences and having another error-detection mechanism in place.

## 3. Distinguishing Errors on Config Server vs. Config Client

Before changing keys or regenerating ciphertext, determine where decryption is taking place.

| Model | Where Decryption Occurs | Component Needing Keys |
| --- | --- | --- |
| Server-side decryption | Config Server | Config Server |
| Client-side decryption | Config Client | Each client needing decryption |

Server-side decryption is the standard model. If the server has the matching key, the Environment response contains plain values.

If you want clients to decrypt themselves, Config Server must disable decrypting outgoing properties with:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: false
~~~

Clients must then be configured with the corresponding key/decryption support. Configuring keys on the client while the server still decrypts outgoing properties does not mean the client should decrypt a second time.

If the response from Config Server still contains `{cipher}...`, check the client-side decryption setup, `spring.cloud.config.server.encrypt.enabled`, and keys on the client. If the response contains `invalid.<property>`, the failure occurred during the decryption step performed by Config Server.

## 4. Common Causes

| Cause | Symptom | What to Check |
| --- | --- | --- |
| Mismatched symmetric key | `/decrypt` fails on old ciphertext; logs report decrypt error | Compare `encrypt.key` source on the exact Config Server instance/profile |
| Wrong RSA private key or alias | Keystore opens yet no matching key found or decrypt fails | Check `encrypt.keyStore.location`, alias, and private key entry |
| Truncated or altered ciphertext | Base64 decode error, padding/block error, or decrypt fails | Compare exact repository value with output generated by `/encrypt` |
| Wrong quotes in `.properties` | Property is not recognized as cipher | Remove quotes around `{cipher}...` in `.properties` |
| YAML does not preserve string verbatim | Parser treats `{cipher}` as YAML structure or unexpected value | Quote the entire cipher value in YAML |
| Missing `{cipher}` prefix | Value is forwarded as a plain string | Check the marker at the start of the value |
| Wrong key alias after rotation | Cipher has `{key:oldAlias}` yet server only has new key alias | Restore old alias or migrate ciphertext to new alias |
| Mismatched decryption mode | Server returns cipher to client or server decrypted yet client processes again | Verify `spring.cloud.config.server.encrypt.enabled` and key placement |
| Key not loaded in the right phase | Config Server runs legacy bootstrap yet key is in a file/source not loaded during bootstrap | Put `encrypt.key` in `bootstrap.properties` when using legacy bootstrap |
| `+`, `/`, `=` characters altered | Ciphertext sent over HTTP differs from value stored in Git | Send `text/plain` body or use `--data-urlencode` properly |
| Plain-text file endpoint not decrypted | YAML/JSON/properties resource returns raw cipher | Check `plainTextEncrypt` and file extension |
| Incompatible crypto policy/runtime | Specific error like `Illegal key size` or provider lacks transformation | Check JDK, security provider, and algorithm used |

Do not conclude from a single exception message alone. The same surface error can stem from a wrong key, corrupted ciphertext, or missing key alias. Use `/decrypt` on the exact instance with the exact configuration to narrow down the scope.

## 5. Checking Symmetric Keys

With symmetric encryption, Config Server uses the same secret key to encrypt and decrypt. Common configuration is:

~~~yaml
encrypt:
  key: ${ENCRYPT_KEY}
~~~

Or set the `ENCRYPT_KEY` environment variable in a secret manager/container environment. Never commit real keys to Git or shared configuration files.

### 5.1. Verify the Exact Value and Exact Instance

In environments with multiple Config Server replicas, every instance may need the same key to decrypt the same ciphertext. If one replica uses a new key while another still uses an old key, results become inconsistent behind a load balancer.

Check:

- Secret manager serves the right version to all replicas.
- The `ENCRYPT_KEY` environment variable is injected into the Config Server process.
- No other profile or environment variable overrides the key.
- Pods/containers were restarted after updating the secret if the runtime does not auto-reload environment variables.
- Instances serve the same key version during rollout.

Do not print keys into logs for comparison. You can compare secret versions/references or fingerprints computed in an internal key-management workflow, but never store weak fingerprints that could aid guessing a low-entropy key.

### 5.2. Legacy Bootstrap Case

If Config Server has `spring-cloud-starter-bootstrap` or `spring.cloud.bootstrap.enabled=true`, Spring Cloud Config documentation requires `encrypt.key` to be placed in `bootstrap.properties` so the key is available during the bootstrap phase.

Example:

~~~properties
encrypt.key=${ENCRYPT_KEY}
~~~

Put this in Config Server's `bootstrap.properties` when the application genuinely uses legacy bootstrap. For applications using only Config Data, configure the key in a property source loaded before the encryption subsystem initializes; verify with integration tests and do not blindly copy legacy bootstrap instructions into a modern application.

### 5.3. Verifying Without Exposing the Key

Do not use the Actuator `env` endpoint to dump `encrypt.key`. To confirm configuration is present, check secret reference status in deployment or verify bean/configuration state with tests that never return secret values.

If the key is fetched from a secret manager, verify secret read permissions, version aliases, and rotation timing. A Config Server may start up yet fail to load the key because the secret provider returned empty or lacked permissions.

## 6. Checking the RSA Keystore

With asymmetric encryption, Config Server uses the public key to encrypt and the private key to decrypt. `encrypt.key` is only for symmetric keys; do not use it to configure an RSA key pair.

Keystore configuration example:

~~~yaml
encrypt:
  keyStore:
    location: classpath:/config-server-keys.jks
    password: ${CONFIG_KEYSTORE_PASSWORD}
    alias: config-encryption
    secret: ${CONFIG_PRIVATE_KEY_PASSWORD}
    type: jks
~~~

Key properties:

| Property | Meaning | Common Errors |
| --- | --- | --- |
| `encrypt.keyStore.location` | Resource containing the keystore | Wrong path, file not packaged, insufficient read permissions |
| `encrypt.keyStore.password` | Password to open the keystore | Wrong password or secret not injected |
| `encrypt.keyStore.alias` | Alias of the key inside the keystore | Alias missing or points to a certificate-only entry |
| `encrypt.keyStore.secret` | Password of the private key entry if different from store password | Wrong password or incompatible with keystore format |
| `encrypt.keyStore.type` | Keystore type; defaults to JKS | PKCS12 file with wrong type configured |

### 6.1. Listing Aliases with keytool

Run `keytool` on a test environment keystore or an authorized inspection copy:

~~~bash
keytool -list -v \
  -keystore config-server-keys.jks \
  -storetype JKS
~~~

The command prompts for the store password. Check:

- Configured alias exists.
- Entry is `PrivateKeyEntry` if the server must decrypt with a private key.
- Corresponding certificate/public key is the one used to encrypt the ciphertext.
- Keystore type matches the actual file.

Never export private keys or attach production keystore files to tickets/logs. Share only non-sensitive metadata such as alias, entry type, validity, and certificate fingerprint when permitted.

### 6.2. JKS and PKCS12

Some PKCS12 keystores do not support a separate password for private key entries the same way JKS does. On newer JDKs, `keytool` may warn that a `keypass` different from `storepass` is ignored. If using PKCS12, check the actual password and configure `encrypt.keyStore.type: PKCS12`.

Do not change keystore type or alias just to silence errors. First verify the file, password, alias, and private key entry. If conversion is required, generate a new keystore under key-management controls, test decryption with sample ciphertext, and only then roll out.

### 6.3. Encrypt with Public Key, Decrypt with Private Key

In the RSA model:

- The encryption tool needs the public key matching the private key being held.
- Config Server needs the corresponding private key if server-side decryption is enabled.
- If Config Server only holds the public key, it can encrypt yet cannot decrypt outgoing properties due to the missing private key.

If ciphertext was produced using a public key from another pair, the current private key cannot decrypt it. An alias existing does not prove the public/private keys belong to the same pair; compare certificate/public key fingerprints via key management.

## 7. Checking Aliases and Multiple Keys

When multiple keys must coexist simultaneously, Spring Cloud Config supports metadata prefixes before ciphertext:

~~~yaml
spring:
  datasource:
    password: '{cipher}{key:config-2026}BASE64_CIPHERTEXT'
~~~

`{key:config-2026}` instructs `TextEncryptorLocator` to look up the corresponding encryptor/key alias. With a keystore, the default locator uses this alias to select the key. The alias must exist on the Config Server handling the request.

### 7.1. Default Locator and Custom Locator

The default `TextEncryptorLocator` does not automatically partition keys per application/profile; by default, encryptions use the same key. If separate keys per application or profile are needed, provide a `TextEncryptorLocator` bean with appropriate selection logic.

Organization example:

| Cipher Metadata | Selected Key |
| --- | --- |
| `{cipher}...` | Default key |
| `{cipher}{key:config-2025}...` | Alias `config-2025` |
| `{cipher}{key:config-2026}...` | Alias `config-2026` |

Do not invent alias prefixes if Config Server is not configured with a matching locator. A ciphertext containing `{key:config-2026}` while the keystore only has `config-2025` will fail to decrypt.

### 7.2. Secret in Prefix

Config Server also supports the `{secret:...}` prefix. If no separate secret is provided, the default locator uses the keystore password. If a secret is supplied, the documentation recommends using a custom `SecretLocator` to handle that secret safely.

Avoid embedding secrets directly in shared configuration files or logs. If per-tenant/application secrets are required, manage secret distribution via a secret manager and a thoroughly tested custom locator.

## 8. Step-by-Step Diagnostic Procedure

Proceed in order to isolate whether the fault lies in the encrypted data, running keys, or how Config Server serves properties.

### Step 1 — Identify Application, Profile, and Label

Record completely:

- `spring.application.name` sent by the Config Client.
- Active profiles in exact order.
- Git label/branch/commit selected by Config Server.
- Property source containing the failing key.
- Config Server replica that processed the request.

Ciphertext may be encrypted with an application/profile-specific key. If the request hits the wrong application or profile, Config Server may pick the wrong `TextEncryptor` when using a custom locator.

### Step 2 — Inspect the Environment Response

Call Config Server's Environment endpoint within the management network:

~~~bash
curl -fsS \
  "https://config.internal/orders-service/production/main" \
  -o config-response.json
~~~

The example path has the form `/{application}/{profile}/{label}`. Do not print the entire response to a terminal or CI log because it may contain many sensitive values.

If `jq` is available, list only source names and error keys:

~~~bash
jq -r '
  .propertySources[] as $source
  | ($source.source // {} | keys[])
  | select(startswith("invalid."))
  | "\($source.name): \(.)"
' config-response.json
~~~

Output such as `invalid.spring.datasource.password` indicates Config Server could not decrypt that key. Check both application-level and profile-specific property sources; a lower-priority source may be providing a fallback value.

After diagnosing, delete the response file from temporary workspaces or ensure it is protected as sensitive configuration data.

### Step 3 — Test Decryption on the Exact Config Server Instance

Take the ciphertext portion after `{cipher}` directly from the repository—not a value altered in logs. Send the ciphertext to `/decrypt` on the exact replica handling requests:

~~~bash
curl -fsS \
  -H "Content-Type: text/plain" \
  --data-binary "BASE64_CIPHERTEXT" \
  https://config.internal/decrypt
~~~

Do not send the `{cipher}` prefix in the body. If the ciphertext has key metadata such as `{key:config-2026}`, retain the required metadata when testing key selection.

If `/decrypt` returns the right plaintext, the key and ciphertext can be decrypted on that instance; move on to checking property source syntax, decryption mode, and request application/profile. If `/decrypt` fails, continue investigating key, alias, keystore, and ciphertext integrity.

The `/decrypt` endpoint can return secrets in plaintext. Call it only from a management network with proper authorization, and never save request bodies/responses to logs. Never open this endpoint publicly for debugging convenience.

### Step 4 — Check Body Transmission and Special Characters

Base64 ciphertext can contain `+`, `/`, and `=`. If sent as `application/x-www-form-urlencoded`, `+` characters can be interpreted as spaces. Use `Content-Type: text/plain` with `--data-binary`, or `--data-urlencode` per Spring Cloud Config documentation.

When encrypting plaintext via `/encrypt`:

~~~bash
curl -fsS \
  -H "Content-Type: text/plain" \
  --data-binary "VALUE_TO_ENCRYPT" \
  https://config.internal/encrypt
~~~

If using `curl --data-urlencode`, documentation instructs prefixing the content to encode with `=`. Use `-s` or `-fsS` so you do not accidentally copy curl progress stats into the ciphertext. Always capture the exact response body without copying extra whitespace, quotes, or terminal messages.

### Step 5 — Cross-Check Key Configuration

For symmetric keys, verify `ENCRYPT_KEY`/`encrypt.key` is loaded on the exact replica. For RSA, verify:

1. Keystore path exists inside the runtime container.
2. Store password opens the keystore.
3. Alias is present.
4. Alias points to a private key entry if the server must decrypt.
5. Private key password is correct.
6. Ciphertext was encrypted using the corresponding public key.

If using `{key:alias}`, verify the alias is passed accurately and the locator can find it. Do not change keys before identifying which key produced the ciphertext.

### Step 6 — Check Formatting in the Repository

Verify source files:

- YAML: quote the entire `{cipher}...` value.
- `.properties`: do not quote cipher values.
- Ciphertext has no line breaks, truncation, or leading/trailing spaces.
- `{cipher}` prefix sits right at the start of the value.
- If using key aliases, `{key:alias}` metadata sits immediately after `{cipher}`.

If files are generated by a pipeline, check whether templating/rendering steps escape or alter special characters. Do not edit manually on just one Config Server instance; fix the source of truth and redeploy.

### Step 7 — Confirm the Decryption Model

Check `spring.cloud.config.server.encrypt.enabled`:

- `true` or not disabled: Config Server decrypts outgoing properties per current configuration.
- `false`: Config Server may keep ciphertext for clients to decrypt locally; clients must have matching keys/decryption support.

When fetching configuration from the plain-text resource endpoint, decryption is disabled by default. Only enable `spring.cloud.config.server.encrypt.plainTextEncrypt=true` alongside `spring.cloud.config.server.encrypt.enabled=true` if properties inside YAML, JSON, or `.properties` files served via that endpoint need decryption.

### Step 8 — Compare All Replicas

Call `/decrypt` on every replica using the same non-sensitive test ciphertext. If results differ, compare secret versions, keystore versions, aliases, and deployment revisions. Do not treat a single successful request through a load balancer as proof that all replicas are in sync.

## 9. Proper Configuration and Formatting

### 9.1. YAML

~~~yaml
spring:
  datasource:
    password: '{cipher}BASE64_CIPHERTEXT'
~~~

Single quotes preserve `{cipher}` as a YAML scalar. Do not add nested quotes inside the ciphertext and do not insert whitespace into Base64.

### 9.2. Properties

~~~properties
spring.datasource.password={cipher}BASE64_CIPHERTEXT
~~~

Do not use:

~~~properties
spring.datasource.password="{cipher}BASE64_CIPHERTEXT"
~~~

Quotes in `.properties` become part of the value and can prevent Config Server from recognizing the marker.

### 9.3. Generating New Ciphertext

Use `/encrypt` on the exact Config Server/key that will decrypt at runtime. Example:

~~~bash
curl -fsS \
  -H "Content-Type: text/plain" \
  --data-binary "NEW_VALUE_TO_ENCRYPT" \
  https://config.internal/encrypt
~~~

Save the response body and prepend `{cipher}` when updating the repository. If a key alias is needed:

~~~yaml
spring:
  datasource:
    password: '{cipher}{key:config-2026}BASE64_CIPHERTEXT'
~~~

After updating, call the Environment endpoint and verify `invalid.<property>` is gone. Never commit plaintext returned by `/decrypt` to Git, pull requests, issues, or CI artifacts.

## 10. Key Rotation and Compatibility with Old Ciphertexts

Decryption errors frequently appear right after changing `encrypt.key`, swapping a keystore, or deploying a Config Server replica with a new key. Ciphertext encrypted with an old key does not automatically convert to a new key.

### 10.1. Rotation Procedure with a Transition Window

For systems supporting multiple key aliases, the safe procedure typically is:

1. Create the new key/alias in the key management process.
2. Install the new key on all Config Server replicas while retaining the old key.
3. Verify both old ciphertexts and new test ciphertexts decrypt successfully.
4. Re-encrypt properties with the new key and add `{key:new-alias}` in source config.
5. Roll out repository/config updates, monitoring `invalid.*` and client startups.
6. Confirm no remaining properties use the old alias.
7. Only after confirming all ciphertexts are migrated, remove the old alias per key management policy.

Do not delete the old key immediately upon deploying the new key. During the transition window, Config Server must be able to decrypt both unmigrated and new values.

### 10.2. Using Multiple Aliases in the Same Keystore

For example, source config can hold two different aliases:

~~~yaml
spring:
  datasource:
    username: '{cipher}{key:config-2025}OLD_CIPHERTEXT'
    password: '{cipher}{key:config-2026}NEW_CIPHERTEXT'
~~~

This is only an illustrative structural example. Aliases `config-2025` and `config-2026` must exist in the keystore or be supported by a custom locator. Each ciphertext must be encrypted with the exact public key/key matching its alias.

### 10.3. Rotation with a Single Symmetric Key

If only a single `encrypt.key` is configured without a custom `TextEncryptorLocator`, there are no old/new aliases to select automatically. Changing the single key makes old ciphertexts undecryptable.

With a single symmetric key, plan ciphertext migration in advance or implement a locator supporting multiple keys. Never roll out a new key to Config Server while the repository still holds ciphertexts decryptable only with the old key.

### 10.4. Compromised Keys

If a key is compromised, treat it as a security incident. Revoke access to the old key, generate a new key, re-encrypt affected properties, update Config Server/clients, and audit repository access history, `/decrypt` calls, logs, and CI artifacts. How long the old key stays active for compatibility must follow incident response policy—never extend it merely for rollout convenience.

## 11. Plain-Text Resource Endpoint and Client-Side Decryption

These two modes are often mistaken for key errors.

### 11.1. Decrypting Properties in the Plain-Text Resource Endpoint

By default, encrypted values inside plain-text resource files are not decrypted. If Config Server serves YAML, JSON, or `.properties` resources via the resource endpoint and needs to decrypt ciphers inside file contents, enable:

~~~yaml
spring:
  cloud:
    config:
      server:
        encrypt:
          enabled: true
          plainTextEncrypt: true
~~~

This feature supports only YAML, JSON, and properties extensions. If another extension is requested, encrypted values may still be returned as-is.

### 11.2. Client-Side Decryption

If intentionally letting clients decrypt themselves:

1. Config Server must keep ciphertext in Environment responses via `spring.cloud.config.server.encrypt.enabled=false`.
2. Clients must have decryption support and the appropriate keys.
3. Every client must be secured as a key holder.
4. Must be tested on the exact Config Client version and Config Data/bootstrap mode.

This model fits when Config Server holds only public keys or only select clients are permitted to hold private keys. In return, key distribution and rotation workflows become more complex because keys are distributed across many clients.

Do not mix both models for the same property without an explicit design. Check the Environment response to confirm whether ciphertext is decrypted on the server or client.

## 12. Crypto Runtime and Algorithm Errors

If logs report specific errors such as `InvalidKeyException: Illegal key size`, inspect the JDK and runtime crypto policy. This can be a policy/provider issue on an older JDK, whereas modern JDKs usually enable unlimited-strength cryptography by default. Do not blindly install legacy JCE policy packages.

Check:

- JDK vendor and version match across local, staging, and production.
- Required crypto providers are present in the runtime image.
- Minimal JDK images are not missing providers/modules.
- Ciphertext was generated using the same key type and algorithm supported by the current runtime.
- Algorithms or providers were not switched while old keys/ciphertexts remain in use.

If the error occurs only after changing the base image/JDK, test decrypting the same ciphertext in test environments running both the old and new runtimes. If only one runtime fails, compare providers, security properties, and algorithms before changing keys.

Do not attempt to decrypt manually with an arbitrary AES/RSA algorithm to "fix" data. Spring Cloud Config must use the exact `TextEncryptor` that created the ciphertext; switching algorithms arbitrarily introduces yet another incompatible cipher format.

## 13. Testing Encrypt/Decrypt

Never use production keys or real secrets in tests. Use dedicated test keys and synthetic data, and never print plaintext/ciphertext into logs.

### 13.1. Testing the Endpoint Lifecycle

With a test Config Server having encryption enabled and endpoints exposed, you can use `TestRestTemplate` to verify round-trip behavior:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "encrypt.key=test-only-key-not-for-production")
class ConfigServerEncryptionEndpointTests {

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void encryptThenDecryptReturnsOriginalTestValue() {
        String original = "synthetic-config-value";

        ResponseEntity<String> encrypted =
                restTemplate.postForEntity("/encrypt", original, String.class);

        assertThat(encrypted.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(encrypted.getBody()).isNotBlank();

        ResponseEntity<String> decrypted =
                restTemplate.postForEntity(
                        "/decrypt", encrypted.getBody(), String.class);

        assertThat(decrypted.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(decrypted.getBody()).isEqualTo(original);
    }
}
~~~

If the test application uses Spring Security, configure test authentication/authorization for endpoints per the application's security policy. Never disable security in production just to make tests pass. For asymmetric keys, use a test keystore and test alias instead of `encrypt.key`.

### 13.2. Testing Config Server Returning Decrypted Properties

Create a test Config Server using a mock repository or file fixture. Place a cipher property encrypted with a test key into the source, then call the Environment endpoint:

1. Verify the response contains the original property name.
2. Verify the response does not contain `invalid.<property>`.
3. Verify the returned value equals the test plaintext.
4. Replace the ciphertext with invalid data and verify the server detects the decryption failure.
5. Verify behavior when `prefix-invalid-properties` remains enabled by default.

Do not assert the entire JSON response because metadata may change between versions. Assert only the required property source, property name, and decryption status.

### 13.3. Testing Key Aliases and Rotation

With a keystore containing two test aliases:

- Encrypt with the old alias and verify decryption succeeds.
- Encrypt with the new alias and verify decryption succeeds.
- Test a nonexistent alias and verify appropriate warning/error handling.
- Remove the old alias in a separate test and verify old ciphertext can no longer be decrypted.

This test proves the rotation procedure works while both keys coexist and catches premature alias removal early.

## 14. Troubleshooting Table

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Response contains `invalid.db.password` | Config Server cannot decrypt property | Call `/decrypt` on the exact replica; check key/alias and ciphertext |
| `/decrypt` errors for all ciphertexts | Key not loaded, wrong key, or keystore cannot open | Check `ENCRYPT_KEY`, `encrypt.keyStore.*`, secret manager, and startup logs |
| Only one Config Server replica fails | Replicas use different key/keystore versions | Synchronize secret versions, keystores, and deployment revisions |
| `/decrypt` succeeds yet Environment still has `invalid.*` | Wrong source/profile/label, custom locator picks another key, or another source holds ciphertext | Call exact Environment path and inspect application/profile/label |
| Ciphertext works in staging yet fails in production | Different key, alias, JDK/provider, or secret version | Compare reference config and runtime metadata without printing secrets |
| Property value starts with `{cipher}` on client | Server disabled outgoing decryption or client-side decryption is used | Check `spring.cloud.config.server.encrypt.enabled` and keys on client |
| YAML parse error on password line | `{cipher}` is unquoted | Wrap the entire YAML scalar in single quotes |
| `.properties` fails to decrypt | Ciphertext is wrapped in quotes | Remove quotes around the value |
| Ciphertext fails only when sent via curl | `+` turned into space or body mis-encoded | Send `text/plain` with `--data-binary` |
| Alias not found | Wrong `{key:alias}` or alias not yet deployed | Check keystore and `TextEncryptorLocator` |
| Old ciphertext fails after rotation | Old key was deleted before migrating all properties | Temporarily restore old alias and complete migration |
| `/encrypt` and `/decrypt` return 404 | Encryption endpoints not registered or request hit wrong base path | Check Config Server dependency/version and mappings |
| `/encrypt` returns 401/403 | Security policy blocks caller | Use proper administrative credentials/role; do not open endpoints publicly |
| Resource endpoint still returns cipher | `plainTextEncrypt` not enabled or extension unsupported | Check `spring.cloud.config.server.encrypt.plainTextEncrypt` and file format |
| `Illegal key size` error | Incompatible JDK/crypto policy/provider | Check JDK and security providers; avoid blindly installing legacy JCE policies |
| Application falls back without crashing | Lower-priority source still defines the same key | Check `invalid.*` and property source precedence; do not rely solely on startup status |

### 14.1. Quick Investigation Workflow

1. Obtain application, profile, label, and Config Server replica.
2. Inspect Environment response for `invalid.<property>`.
3. Call `/decrypt` with the original ciphertext on the exact replica.
4. If decryption fails, verify key/keystore/alias and ciphertext.
5. If decryption succeeds, verify file format, property source, and server-side/client-side mode.
6. Repeat checks on every replica.
7. Run integration tests with test keys before updating the repository or rolling out.

## 15. Securing Endpoints and Decrypted Data

The `/encrypt` and `/decrypt` endpoints are sensitive endpoints. `/decrypt` can return plaintext secrets directly; `/encrypt` can be abused as an encryption oracle. Allow only authorized service identities or administrative operators to call these endpoints.

### 15.1. Securing Endpoints

- Place Config Server behind a private network, gateway, or service mesh with strict policies.
- Enable authentication and authorization for `/encrypt` and `/decrypt`.
- Grant access only to necessary operations/key-management groups.
- Use TLS when transmitting ciphertext, key metadata, and responses.
- Never expose decrypt endpoints to the Internet or public management ports.
- Audit security matchers so overly broad path matchers do not accidentally permit anonymous access.

Spring Cloud Config documentation explicitly states that encryption endpoints are provided under the assumption that they are secured and accessible only to authorized callers.

### 15.2. Never Log Plaintext or Keys

Do not log:

- Values returned from `/decrypt`.
- Request body contents sent to `/encrypt` or `/decrypt`.
- `encrypt.key`, keystore passwords, or private keys.
- Full Environment responses when responses may contain secrets.
- Ciphertext alongside metadata sufficient to identify the key alias if logs are unprotected.

Log diagnostic metadata such as request ID, application, profile, label, replica ID, alias name (if policy permits), outcome, and exception category. Never log secret values.

### 15.3. Key Management

Store symmetric keys, keystore passwords, and private key passwords in a secret manager or key management system. Restrict read permissions by service identity. Track version/rotation events and maintain rollback runbooks. Never share the same key across test, staging, and production.

## 16. Recovery Runbook

When a critical property fails to decrypt in production:

1. Identify the application/profile/label and replica returning `invalid.<property>`.
2. Check whether a fallback property is being used; assess impact on databases, message brokers, or downstream services.
3. Call `/decrypt` with a test ciphertext on an administrative replica to determine which key is currently active.
4. Check secret versions, aliases, and keystore deployment; do not modify keys before knowing which key created the ciphertext.
5. If rotation just occurred, ensure the old key remains present during the transition window.
6. If ciphertext is corrupted, retrieve the source of truth or re-encrypt from authorized plaintext per secret management procedures.
7. Deploy the fix to one replica/canary first, call the Environment endpoint, and verify `invalid.<property>` disappears.
8. Confirm the Config Client receives the expected property and bean binding/health work.
9. Deploy remaining replicas and verify consistency.
10. Revoke the old key after confirming no dependent ciphertexts remain, unless incident response requires emergency revocation.

Do not replace all ciphertexts in Git with arbitrary strings just to silence warnings. Verify correct plaintext values from authorized sources and ensure the new key/alias is deployed on every Config Server replica.

## 17. Practice Exercises

### Exercise 1 — Identifying Invalid Properties

Create a test Config Server with one valid cipher property and one undecryptable ciphertext. Call the Environment endpoint, find the `invalid.*` key, and explain why the Config Client can receive a fallback from another source.

### Exercise 2 — Checking Symmetric Keys

Create a test Config Server using a mock `encrypt.key`. Call `/encrypt`, then `/decrypt`. Change the key and verify the old ciphertext can no longer be decrypted.

### Exercise 3 — Checking an RSA Keystore

Create a test keystore using `keytool`. Inspect the alias and private key entry. Encrypt with the public key and decrypt with the corresponding private key. Try a wrong alias/password to observe the errors.

### Exercise 4 — Fixing Formatting Mistakes

Create two fixtures: YAML and `.properties`. Place ciphertext with valid and invalid quoting and verify the difference. Try sending ciphertext containing `+` using form encoding versus `text/plain`.

### Exercise 5 — Key Rotation

Create two test aliases. Keep both aliases in the keystore, migrate one property to the new alias, and verify both old and new properties decrypt. Then simulate removing the old alias in a separate test.

### Exercise 6 — Securing Endpoints

Add security tests for `/encrypt` and `/decrypt`: unauthenticated callers are rejected, authorized operators can call them, and plaintext responses never appear in logs.

**Completion criteria:** you can pinpoint why a property fails to decrypt, verify keys/ciphertext with tests, restore proper configuration, and prove endpoints/secrets are protected.

## 18. Summary

When Spring Cloud Config fails to decrypt a cipher value, start with the Environment response and search for `invalid.<property>`. This signals that Config Server removed the ciphertext from the property source because decryption failed. Verify the exact application/profile/label, call `/decrypt` on the exact replica, and check the symmetric key or RSA keystore, alias, ciphertext, and file formatting.

YAML requires quoting `{cipher}` values; `.properties` must not quote them. When sending ciphertext over HTTP, use `text/plain` or proper URL encoding so `+`, `/`, and `=` are not altered. During rotation, keep the old key until all ciphertexts have been migrated and verified. If using client-side decryption or the plain-text resource endpoint, explicitly verify the properties controlling decryption mode.

The `/decrypt` endpoint can return plaintext and must therefore be secured, request bodies/responses must never be logged, and production keys must never be used in tests. Round-trip, Environment response, and key alias test suites catch failures before deployment.

## References

- [Spring Cloud Config 5.0.6 — Encryption and Decryption](https://docs.spring.io/spring-cloud-config/reference/server/encryption-and-decryption.html): `{cipher}` prefix, `invalid.*` behavior, `/encrypt` and `/decrypt` endpoints.
- [Spring Cloud Config 5.0.6 — Key Management](https://docs.spring.io/spring-cloud-config/reference/server/key-management.html): symmetric keys, RSA key pairs, and keystore configuration.
- [Spring Cloud Config 5.0.6 — Using Multiple Keys and Key Rotation](https://docs.spring.io/spring-cloud-config/reference/server/using-multiple-keys-and-key-rotation.html): alias prefixes, `TextEncryptorLocator`, and rotation.
- [Spring Cloud Config 5.0.6 — Serving Encrypted Properties](https://docs.spring.io/spring-cloud-config/reference/server/serving-encrypted-properties.html): server-side and client-side decryption.
- [Spring Cloud Config 5.0.6 — Actuator and Security](https://docs.spring.io/spring-cloud-config/reference/server/actuator-and-security.html): Actuator configuration and securing Config Server.

Cross-check documentation for your exact Spring Cloud release train and running JDK. Key configuration, crypto providers, endpoint security, and bootstrap lifecycles can differ across version generations.

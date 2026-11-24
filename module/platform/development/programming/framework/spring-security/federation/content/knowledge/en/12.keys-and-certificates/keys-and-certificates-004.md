# Protecting private keys with secret stores and restricting read permissions

> **Module:** Spring Security – federation. **Group:** Keys and certificates. This lesson covers how to protect **SAML Service Provider (SP) private keys** used to sign messages or decrypt Assertions, from key generation, storage in a secret manager/KMS/HSM, granting workload access, loading into Spring Security, and rotation through revocation. Examples use **Java 17**, **Spring Boot 3.5.x**, **Spring Security 6.x**, and Linux/Kubernetes environments. Some infrastructure configs are illustrative excerpts and must be adapted and tested against your real platform.

## 1. Objectives and prerequisites

After this lesson, you should be able to:

1. Identify **which private keys belong to the SP** and which belong to the IdP; distinguish public signing certificates, public encryption certificates, and private signing/decryption keys.
2. Explain why private keys **must never be placed in source code, Git, Docker images, application.yml, spreadsheets, logs, tickets, CI artifacts**, or shared with partners over email.
3. Choose an appropriate key storage model among **managed secret managers**, **Vault**, **KMS/HSM**, keystores, and least-privilege mounted secret files.
4. Design **least privilege** for users, CI/CD, workload identities, service accounts, namespaces/tenants, and individual secret versions.
5. Control file permissions, startup handling, memory, backups, audits, credential lifetimes, and provisioning/revocation flows.
6. Configure private signing/decryption keys in **Spring Security SAML 2.0 Relying Party** without embedding raw keys in public config.
7. Plan **overlapping rotation** to avoid breaking SSO when IdP/SP rotate keys, and execute incident response when a key is suspected compromised.
8. Run a Java 17 program demonstrating signing/verification without printing private keys, and test secret access permissions in a real environment.

**Prerequisites:** Familiarity with IdP/SP, SAML Metadata, `KeyDescriptor use="signing"` and `use="encryption"`, Java `PrivateKey`/`PublicKey`, X.509 certificates, Spring `RelyingPartyRegistration`, and basics of Linux permissions, IAM, or Kubernetes RBAC.

**Guiding principle:** Public certificates are meant to be **distributed**; private keys must be **kept secret and restricted in usage**. A secret manager protects distribution and storage, yet does not replace protecting the process, host, accounts, and data in memory.

## 2. What do private keys do in SAML2?

In SAML Federation, keys are viewed by **role and communication direction**. The same SP may use one private key to sign `AuthnRequest` and another private key to decrypt `EncryptedAssertion`. The IdP holds its own private keys for signing assertions or decrypting messages sent to the IdP.

| Action | Who holds the **private key**? | Who uses the public key/certificate? | Must private key be sent to partner? |
| --- | --- | --- | --- |
| IdP signs `SAMLResponse` / `Assertion` | **IdP** | SP verifies with IdP's public signing cert from trusted metadata | **No** |
| SP signs `AuthnRequest` / logout message | **SP** | IdP verifies with SP's public signing cert in SP metadata/registration | **No** |
| IdP encrypts Assertion for SP | **SP** holds decryption private key | IdP encrypts for **SP's public encryption cert** | **No** |
| SP encrypts message for IdP (if profile supports) | **IdP** holds decryption private key | SP uses IdP's public encryption cert | **No** |
| SP verifies IdP signature | SP only needs **IdP's public verification certificate** | SP performs verification | IdP private key not needed |

~~~text
                   IdP                                SP
       Signing private key (IdP)                 Public cert IdP
                 |                                      |
                 +-------- signed Assertion ----------->| verify
                                                        |
       Public encryption cert SP                 Decryption private key SP
                 |                                      |
                 +------- EncryptedAssertion ---------->| decrypt

               IdP                                    SP
       Public signing cert SP                   Signing private key SP
                 |                                      |
            verify |<------ signed AuthnRequest --------+
~~~

**Common mistake:** Putting the **IdP private key** into the SP application to "verify SAML". The SP only needs the **IdP's public certificate**. If a configuration asks for a private key to verify signatures arriving from the IdP, re-examine the model—signing and verification credentials are very likely being confused.

### Should private signing and decryption keys be shared?

Technically an RSA key pair can serve multiple purposes, yet **separating keypairs by purpose is recommended**: signing and decryption have different usage histories, revocation criteria, permissions, and rotation cadences. Avoid reusing the same private key across TLS, SAML, SSH, or staging/production environments. Separating keys limits blast radius if only one purpose is compromised and helps the IdP manage `KeyDescriptor@use` cleanly.

With a signing key, exposing the private key lets an attacker sign messages impersonating the SP (insofar as the IdP trusts the signer). With a decryption key, exposure compromises confidentiality of current encrypted Assertions or previously captured ciphertexts. These are **two distinct security impacts**.

## 3. Threat model: where can a private key leak?

Treat private keys as **high-impact secrets**. Even an apparently safe storage approach has multiple leak vectors.

| Attack path / misconfiguration | Example | Required control |
| --- | --- | --- |
| Source code and Git history | Copying `-----BEGIN PRIVATE KEY-----` into a repository | Secret scanning, commit blocking, policy review, immediate rotation if exposed |
| Build/CI artifacts | Private key baked into JAR, image layer, or pipeline logs | Runtime injection, short-lived CI identity, keep keys out of build context |
| Overly broad CI/CD permissions | CI token allowed to read all production secrets | Separate deploy jobs from secret-reading jobs; IAM scoped by path/role/env |
| Local file permissions | `/opt/app/sp.key` with mode `0644` | Readable only by runtime workload; read-only volume; restrict group/others |
| Environment variables | Secret appears in process environment, crash diagnostics, or inspection tools | Prefer protected file mounts/IPC or hardware-backed operations; never echo env |
| Container/Kubernetes access | User with permission to create pods or exec into pods reads mounted secrets | Pod admission/RBAC, restrict exec/debug, privileges, and images |
| Backup/snapshot | etcd backups, disk snapshots, artifact backups holding secrets | Encryption at rest, RBAC, retention/restore drills, and copy inventory |
| Debugging/APM/logs | Stack traces, actuator env, heap dumps, or HTTP traces recording keys | Masking, restrict endpoints/dumps, controlled support policies |
| Compromised host | Root/privileged process reads files or memory | Node/host hardening, network segmentation, workload isolation, monitoring |
| Compromised secret manager credential | Long-lived Vault token stored in config | Workload identity, short token TTL, tight scope, audit/revoke |
| Environment/tenant mix-up | Staging workload reads production private key | Dedicated identity and keys per env/tenant; deny cross-scope access |
| Poor key rotation | Old key remains trusted or decryptable indefinitely | Lifecycle management, expiry, removal, and secret versioning |

**Secrets are not just strings:** Private keys in PEM/PKCS#8/PKCS#12, Java `PrivateKey` objects, memory, backup copies, keystore passwords, and service-account tokens used to fetch keys all require protection. A key encrypted in a store can still leak when the app fetches plaintext to sign/decrypt.

## 4. Choosing a secret store: Secret Manager, Vault, KMS, or HSM?

No single option fits every organization. Start from whether **the key is allowed to be exported**, latency/availability needs, Spring/OpenSAML integration capability, and compliance constraints.

| Solution | Typical role | Advantages | Risks/limitations |
| --- | --- | --- | --- |
| Managed secrets service (AWS Secrets Manager, Google Secret Manager, Azure Key Vault secrets) | Stores versioned **secret blobs** like PEM/PKCS#8/PKCS#12; IAM-gated read access | Encryption at rest, audit, versioning, managed replication | App still receives plaintext key; read permissions and runtime compromise remain critical |
| HashiCorp Vault KV / appropriate secret engine | Stores and distributes keys/secrets to workloads with identity, policy, and audit | Path/version/lease management and multi-platform support | Must secure Vault tokens, unsealing, HA, network/authn, and policies |
| Cloud KMS **symmetric envelope encryption** | Uses a protected data key to encrypt secret blobs at rest | Reduces plaintext at rest; policy-controlled decrypt API | App still decrypts to plaintext private key; does not provide non-exportable signing |
| KMS/HSM **asymmetric key operations** | Generates/holds **non-exportable** private key; signs/decrypts via API/PKCS#11/provider | Reduces ability to extract raw private key | Not drop-in for every OpenSAML/Spring API, binding, and algorithm; needs provider/adapter and testing |
| Protected PKCS#12 keystore on disk | Stores private key + certificate chain protected by passphrase | Broad Java ecosystem support; centralized in one file | Must protect both keystore **and** passphrase; co-locating password helps little |
| Read-only secret volume / tmpfs mount | Supplies temporary key to container via volume | Easy with Spring `file:` Resource | Plaintext key readable by authorized process and privileged host/pod |
| Unmanaged local filesystem | Manually copying `.key` onto VM | Easy for quick experiments | Copying risk, unaudited changes, hard backups and rotation |

**Distinguishing KMS and Secret Manager:** A secret manager can store a **PEM private key as a secret**; cloud KMS may encrypt that blob (envelope encryption). If the blob is delivered to runtime and decrypted, Java still holds a plaintext key in process memory. Asymmetric **non-exportable** HSM/KMS keeps the key in cryptographic hardware/backend and exposes only sign/decrypt operations, yet requires JCA/PKCS#11 library support or integrated APIs. Never claim "putting a PEM in KMS means the private key never leaves KMS" if the app still downloads the PEM.

### 4.1. Selection criteria

1. **Threat model:** Preventing Git/CI leaks is the baseline; do you also need protection against node root, memory dumps, insiders, or side-channels?
2. **Exportability:** If private keys must strictly never be exported, prefer asymmetric HSM/KMS with a compatible provider over storing PEM blobs.
3. **Permissions and identity:** Is there per-service-account/environment workload identity? Does IAM scope down to individual secrets/keys/versions?
4. **Audit:** Are logs recording who/which role read, signed with, or rotated a key, tamper-evident, and free of plaintext?
5. **Lifecycle:** Supports versioning, rotation, overlapping keys, revoked permissions, and break-glass?
6. **Runtime:** When the secret store/KMS is temporarily unreachable, how does the app start/continue? Are timeout/cache policies defined?
7. **Cost/latency:** Remote HSM/KMS signing has different latency, quotas, and billing than a local `PrivateKey`; benchmark under realistic SSO traffic.
8. **Compliance:** Key length/algorithm types, FIPS, data residency, retention periods, and internal standards.

### 4.2. Least-privilege key distribution architecture

~~~text
Production SP workload identity
   |  (mTLS / OIDC workload identity / IAM role / Vault auth)
   v
Secret manager or HSM/KMS
   |  policy check: right app, right env, right purpose
   |  audit: who, when, secret version, allow/deny
   v
Option A: inject PEM/PKCS#8 via protected read-only volume
          |
       Java/Spring reads key at startup
          |
       signs AuthnRequest / decrypts Assertion

Option B: HSM / KMS PKCS#11 / compatible JCA provider
          |
       Java holds key handle, never exports raw private key
          |
       crypto operation scoped to key purpose and policy
~~~

In Option A, treat the **file, runtime memory, and host** as sensitive points. In Option B, treat **permission to call signing/decryption APIs**, key handles, algorithms, and logs as sensitive too; an attacker compromising the process can abuse signing authority even without extracting the raw key.

## 5. Principle of least privilege: who is allowed to see a private key?

Required access is not simply "can read secrets" but **minimum access scoped by role, purpose, and environment**.

| Principal | Permitted actions | Should not have |
| --- | --- | --- |
| Production SP runtime | Read exact production signing/decryption keys or invoke required crypto operations | List all secrets, read staging, delete keys, grant IAM permissions to others |
| CI build/test | Build artifacts, run unit tests with **test-only keys** | Read production private keys |
| Deployment automation | Deploy approved configs, holding only release-required permissions | Read plaintext keys if runtime fetches via workload identity |
| Security admin / key custodian | Create/rotate/revoke under change control and audit | Use keys for business logins without justification |
| Developer | Read docs, public certificates, and dummy test keys | Read prod private keys via tickets, Slack, repos, secret managers |
| Partner IdP | Receive SP **public** signing/encryption certificates | SP's private keys |
| Monitoring agent | Read sanitized status/metadata metrics | Dump private keys, env, keystores, heap |
| SRE break-glass | Emergency access with approval, MFA, short TTL, audit | Permanent unrestricted access across all environments |

### 5.1. Splitting permissions by key purpose

Suppose the secret store uses logical paths:

~~~text
/org/prod/saml/portal/signing-key
/org/prod/saml/portal/decryption-key
/org/staging/saml/portal/signing-key
/org/prod/saml/payroll/signing-key
~~~

Production SP Portal only needs the first two keys (or only decryption if it does not actually sign requests). Apply **deny by default**, granting read access on the **exact secret ARN/path/key ID**, avoiding wildcards like `/org/*` or admin permissions. If an app only verifies IdP signatures, it **needs no access to any IdP private key**.

In versioned secret managers, policies can further restrict usable versions/stages and `read/describe` actions; `delete`, `update`, `grant`, and `list` are reserved for rotation pipelines and key custodians. Do not grant permission to read all secret versions merely for one release when scoping is possible.

### 5.2. Workload identity instead of static credentials

In cloud/Kubernetes, workloads should authenticate to the secret manager using platform identity mechanisms (service accounts bound to IAM roles, workload identity federation, managed identities, Vault Kubernetes auth with short TTLs), rather than embedding long-lived API tokens in YAML/env to download private keys. Yet workload identity is only secure when:

- Service accounts are not shared across apps with different trust levels.
- Tokens are restricted by **audience, subject, TTL, and scope**, preventing arbitrary role assumption.
- IAM roles allow only specific secrets and, where applicable, specific KMS keys.
- Pod/node/CI policies restrict who can attach service accounts or deploy rogue workloads.
- Identity revocation/rotation paths and auditing exist.

**Never treat a Kubernetes namespace as an absolute security boundary.** Permissions to create/exec pods, mutate admission, mount hostPath, or cluster-admin roles can bypass direct `kubectl get secret` blocks to read secrets. Always evaluate permissions to **create Pods that mount Secrets**.

## 6. Deployment pattern: safely bringing private keys into runtime

A practical architecture for Spring Security on VMs/containers:

1. **Generate the keypair** through an approved process with sufficient strength and algorithms matching the IdP and cryptographic policy. Never use production keys for exercises.
2. Protect the private key in a secret manager/HSM. If PEM export is required, use PKCS#8 or a library-supported format, transmit over TLS, never log/echo.
3. Grant read access solely to the **runtime identity** for the right key/version.
4. Mount as a file in an app-only readable directory; never bake keys into images/JARs, CLI arguments, or Git config.
5. Run the app as a **non-root** user; mount **read-only** where possible with tight file permissions.
6. Spring Security loads the private key via `Resource`/configuration or a controlled JCA provider.
7. Log **load status/version/public certificate fingerprint** as needed; never log key bytes/private keys/passwords.
8. Automatically test valid read permissions, failing closed if the key is inaccessible, the version is wrong, or the cert mismatches.
9. Handle rotation/restart/reload in ways genuinely **supported** by your Spring Security version and secret provider.
10. When retiring a workload, revoke credentials and clean up temporary files/volumes per lifecycle.

### Why are file mounts usually better than environment variables?

An environment variable can leak via process inspection, crash diagnostics, CI logs, actuator env endpoints, or accidental config printing. File mounts with tight POSIX permissions and read-only mode reduce several leak paths and fit Spring Boot's `file:` Resource. However, **file mounts are not immune** to host root, users with container exec access, memory dumps, backups/snapshots, or debugging workflows that read files.

Never assume running `rm sp-private.key` guarantees erasure across storage with snapshots/layers/SSDs. Lifecycle management in the secret manager, access controls, backup governance, and encryption at rest matter more.

## 7. Linux permissions: user, group, mode, and path

On Linux, a typical private key file (needing no group access) can use mode `0600` for the application user. If owner read-only suffices and writes are unnecessary, consider `0400`. The parent secret directory must allow traversal for the runtime while blocking other users.

~~~bash
# Operational example on a test host only, run by an authorized admin.
# File already created by secret provisioning from a trusted source.
chown saml-app:saml-app /run/secrets/sp-signing.key
chmod 0400 /run/secrets/sp-signing.key

# Inspect metadata ONLY; NEVER display contents.
stat -c '%a %U %G %n' /run/secrets/sp-signing.key
~~~

In the example, owner is `saml-app`, and mode `0400` means **owner read**, denying group/others. **`chmod`/`chown` commands only apply where the filesystem permits**; orchestrator-managed secret volumes can be read-only with their own permission mechanisms. Do not run chmod on production pods without understanding the provider/mount.

**Distinguish directory permissions:** a `0400` file provides little protection if someone else can replace files in the directory, swap symlinks, or mount over the path. Restrict write access on parent directories and prevent the app from loading keys from user-supplied paths.

**Never print private keys to a terminal:**

- Avoid `cat /run/secrets/sp-signing.key`, `head`, `kubectl get secret -o yaml`, `echo "$PRIVATE_KEY"`, `printenv`, and attaching key files to tickets.
- For diagnostics, check `stat`, inode/file mode, owner, trusted mount source, key version, and public certificate metadata.
- If you must verify a key/cert pair, run tools on a controlled host and print only match/mismatch status, never the private key.

## 8. Kubernetes: Secret objects do not guarantee full security on their own

Per Kubernetes documentation, Secrets hold sensitive data, yet **Base64 is merely encoding**, not encryption. Secret data in etcd needs **encryption at rest** configured; RBAC permissions for `get/list/watch` must be restricted. Users permitted to create Pods mounting a Secret can still read its values via a Pod under certain conditions.

Common scenario:

~~~text
External secret manager or Kubernetes Secret
             |
          CSI driver / secret volume / controller
             |
          Pod (SAML SP)
          ├─ container spring-app
          │    /run/secrets/saml/signing.key       (read-only)
          │    /run/secrets/saml/signing.crt       (public)
          │    /run/secrets/saml/decryption.key    (read-only)
          │    /run/secrets/saml/decryption.crt    (public)
          └─ other container: MUST NOT mount keys
~~~

**Threat-model preference:** When integrating an external secret manager, you may use the CSI Secrets Store driver or Vault Agent Injector per platform capability. Still, CSI driver, controller, secret sync, and mount behavior need explicit policy: configuring **sync to a Kubernetes Secret** creates an extra copy inside Kubernetes and etcd that requires separate governance. Do not claim CSI automatically eliminates all copies.

### 8.1. Pod SecurityContext and secret volume snippet

The YAML below is **part of a Pod template**, not a full Deployment. It illustrates a non-root workload mounting secrets only into the needed container. `defaultMode: 0440` permits owner/group read; `fsGroup` can help the runtime's group read the volume where supported. Always verify effective owner/group/mode of CSI/Secret volumes.

~~~yaml
spec:
  serviceAccountName: saml-portal
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: saml-app
      image: registry.example.org/app/saml-sp:1.0.0
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
      volumeMounts:
        - name: saml-keys
          mountPath: /run/secrets/saml
          readOnly: true
  volumes:
    - name: saml-keys
      secret:
        secretName: saml-portal-runtime
        defaultMode: 0440
~~~

**Do not copy this snippet verbatim and treat it as production-ready.** Namespaces, RBAC, pod admission, image signatures, network policies, resource limits, Seccomp, secret sources, controllers, and a writable `/tmp` for Java/Tomcat if needed must still be configured. `automountServiceAccountToken: false` fits when the app **does not need a service account token inside the container** to call the Kubernetes API. If a CSI/sidecar needs a token to authenticate to an external secret store, implement properly scoped workload identity and token projection rather than disabling blindly.

**Permission pitfalls:** If a mount creates files owned by `root` with mode `0400`, a UID 10001 process **cannot read the key**. Use intentional ownership/group access (`0440` + matching group on supported volumes), never `0644`. `fsGroup` does not guarantee every CSI driver adjusts ownership; verify specific driver behavior. Some Kubernetes projected volumes expose keys as **symlinks** to versioned data; dereference links properly when inspecting modes.

### 8.2. Checking permissions without printing the secret

In a test container running as the same user as the app:

~~~bash
id

# Stat after dereferencing symlinks, without printing file contents.
stat -L -c '%a %u %g %n' /run/secrets/saml/signing.key

# Verify runtime readability, printing only PASS/FAIL.
if test -r /run/secrets/saml/signing.key; then
  printf '%s\n' 'KEY_READABLE_BY_APP=PASS'
else
  printf '%s\n' 'KEY_READABLE_BY_APP=FAIL'
fi
~~~

If `KEY_READABLE_BY_APP=FAIL`, check UID/GID, fsGroup, Secret volume mode, path, and container mount. **Never fix by making it world-readable**. If an attacker has root/exec privileges on the host, file modes alone are insufficient; combine with node security and deploy/debug controls.

### 8.3. Kubernetes RBAC: read access and Pod execution rights

- **Secret `get`:** permits reading a specific Secret; restrict by namespace and resourceName where feasible.
- **Secret `list/watch`:** can expose contents of many Secrets; never grant to normal workloads unless genuinely necessary.
- **Pod create/update/exec:** can allow mounting secrets, altering commands, or reading secrets indirectly; audit these permissions during security reviews.
- **Namespace/ServiceAccount:** dedicate separate ones to the production SP; do not share broad service accounts across environments.
- **Admission policy:** restrict privileged pods, host mounts, hostPID, untrusted image sources, and service account attachment rights.
- **Audit:** audit API secret reads and pod modifications; do not assume Kubernetes logs record each time a process reads a mounted volume file. For keys fetched from external vaults, secret manager audit logs record **fetches** but not every local Java key usage.

## 9. Spring Boot 3.5/Spring Security: loading keys from secret files

Spring Boot supports SAML Relying Party properties. For a SAML login SP, distinguish:

- **SP signing credential:** **SP's private key and public certificate**, used by the SP to sign `AuthnRequest`/logout messages when required by configuration.
- **SP decryption credential:** **SP's private key and public certificate**, used to decrypt `EncryptedAssertion`/`EncryptedID` sent by the IdP.
- **IdP verification credential:** **IdP's public signing certificate only**, used to verify Response/Assertion signatures.
- IdP metadata also provides the entity ID and required endpoints, when retrieved from a trusted source.

**Example `src/main/resources/application.yml`:**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/saml/signing.key
                  certificate-location: file:/run/secrets/saml/signing.crt
            decryption:
              credentials:
                - private-key-location: file:/run/secrets/saml/decryption.key
                  certificate-location: file:/run/secrets/saml/decryption.crt
~~~

These paths assume secret provisioning has created files in the right format/trust; **never create files from real keys inside the project**. If the IdP metadata URI does not work, replace it with an approved IdP source; never fetch metadata from user-supplied input. If the IdP only requires the SP to receive signed Responses, you are not forced to add signing/decryption credentials **merely because the SAML module is enabled**.

**Format requirements:** `private-key-location` properties typically read private keys from PEM compatible with the Spring Security/SAML credential loader (usually PKCS#8). Passphrase-encrypted PEMs or legacy PKCS#1 keys may require safe conversion or a custom loader/crypto provider; never assume property loaders support every file format. **Never move secrets into an unencrypted source tree just to make the app start.**

### 9.1. `pom.xml` file for the demo application

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>saml-secret-protection</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots><enabled>false</enabled></snapshots>
    </repository>
  </repositories>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-saml2-service-provider</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Example `src/main/java/demo/SamlSecretApplication.java`:**

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SamlSecretApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSecretApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class HomeController {
        @GetMapping("/")
        String home() {
            return "SAML SP is running";
        }
    }
}
~~~

If real IdP metadata and credentials are validly mounted, run `mvn spring-boot:run` from the project directory. `GET /` returns **`SAML SP is running`**. To test SSO, register the SP entity ID/ACS/cert at the IdP, create a test user, and visit `/saml2/authenticate/corporate`. Because the example URL is not a real IdP, the example **does not complete login on its own**.

Key point: the Java code never reads private keys directly or logs secrets. Spring Boot/Spring Security configures credentials via **filesystem Resources** inside an authorized runtime, instead of hardcoding PEMs in Java. However, loading still puts plaintext key material in Java process memory in a file-based model; continue hardening the host/container and restricting heap/crash dumps.

### 9.2. Error handling should fail when keys are missing

For an IdP requiring signed AuthnRequests, if the app lacks a signing private key/cert, it must fail with a configuration or request-signing error; do not disable signing requirements at the IdP to "make it work". For EncryptedAssertions when the SP lacks a decryption key, **do not** casually ask the IdP to turn off encryption; inspect the key/cert pair, secret mount, rotation, and compatibility.

**Never log verbatim exceptions containing key material:** log the error type, registration ID, secret version, and public certificate fingerprint if needed; mask sensitive paths if policy requires.

## 10. Standalone Java 17: generating and using a private key without exporting it

The following program uses JDK 17 to generate a keypair **in memory**, sign a test message, and verify with the public key. It deliberately **does not call `getEncoded()` on the private key and never prints the key**. Signing with `SHA256withRSA` in the example is purely illustrative; production must pick algorithms/key lengths per policy and SAML IdP/SP compatibility.

**File `PrivateKeyUsageDemo.java`:**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class PrivateKeyUsageDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        byte[] message = "SAML request demo".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        boolean originalVerified = verifier.verify(signature);

        Signature modifiedVerifier = Signature.getInstance("SHA256withRSA");
        modifiedVerifier.initVerify(pair.getPublic());
        modifiedVerifier.update(
                "tampered SAML request".getBytes(StandardCharsets.UTF_8));
        boolean tamperedVerified = modifiedVerifier.verify(signature);

        System.out.println("originalVerified=" + originalVerified);
        System.out.println("tamperedVerified=" + tamperedVerified);
        System.out.println("privateKeyPrinted=false");
    }
}
~~~

Run:

~~~bash
javac PrivateKeyUsageDemo.java
java PrivateKeyUsageDemo
~~~

**Exact stdout:**

~~~text
originalVerified=true
tamperedVerified=false
privateKeyPrinted=false
~~~

**Explanation:** The private key is passed only to `Signature.initSign()`; the public key is used in `initVerify()`. Any alteration to the data invalidates the signature. The program never prints/serializes raw private keys and does not connect to SAML/IdP; **this is not a SAML Signature generator**, nor does it prove the runtime holds no key copy in memory. The Java heap, debuggers, or privileged processes can still access data in exportable-key models. With hardware-backed keys, `PrivateKey` may be a handle/provider object rather than an exportable byte array; verify the specific integration.

### 10.1. Checking a secret file without opening its contents

Inside a Linux container running with the application's UID/GID:

~~~bash
id
stat -L -c '%a %u %g %n' /run/secrets/saml/signing.key

if test -r /run/secrets/saml/signing.key; then
  printf '%s\n' 'APP_CAN_READ_SIGNING_KEY=PASS'
else
  printf '%s\n' 'APP_CAN_READ_SIGNING_KEY=FAIL'
fi
~~~

**There is no fixed stdout** for `id`/`stat` since it depends on runtime. `test -r` only proves the file is readable under the process's permissions at that moment; **it does not by itself prove owner, secret origin, or key validity**. Check file permissions, read-only mounts, trusted providers, and SAML integration tests together. Never use `cat` to debug private keys.

### 10.2. Safely verifying a private key and certificate pair

When the app reports a key/certificate mismatch, an internal tool on a controlled host can sign a temporary challenge with the private key and verify it with the **public key in the certificate**. Log only `match=true/false`, the public certificate fingerprint, and key version; never print the private key or sensitive challenge data. For non-exportable HSM/KMS private keys, use the provider's signing operation and inspect the public certificate registered at the IdP.

Avoid asking engineers to paste keys onto "certificate checker" websites. Every tool that reads a private key—even diagnostic tools—requires authorization, auditing, review, and a restricted environment.

## 11. PKCS#12, PEM, and passphrases: protecting both files and passwords

Common formats:

| Format | Content | Notes |
| --- | --- | --- |
| PEM `BEGIN PRIVATE KEY` | File-level unencrypted PKCS#8 private key | Secret manager/mount/permissions and encryption at rest are mandatory |
| PEM `BEGIN ENCRYPTED PRIVATE KEY` | Encrypted PKCS#8 private key | Requires passphrase via a **separate** secret source and a decrypt-capable loader/provider |
| PEM `BEGIN RSA PRIVATE KEY` | PKCS#1 RSA private key (legacy format) | Do not assume `private-key-location` supports it in all versions; convert in a trusted environment if needed |
| PKCS#12 `.p12/.pfx` | Keystore containing private keys/certificates, password-protected | Password must not sit in the same repo/manifest; govern access to both store and password |
| HSM/PKCS#11 handle | Reference to a non-exportable key | Requires JCA provider/algorithm support, slot/session, and policy |
| X.509 certificate `.crt/.pem` | Public key and certificate metadata | Not a private key; still requires authentic distribution/trusted metadata |

**Design flaw:** Encrypting a private key with a strong passphrase yet placing the passphrase in Git's `application.yml` right alongside the encrypted PEM. An attacker obtaining both can decrypt it. Use a secrets backend/workload identity to deliver passwords where applicable, and assess whether a single tool reading both keystore and passphrase has excessive permissions.

**Keystore backup:** If a private decryption key is lost completely, SAML data encrypted for the old public key may become permanently undecryptable. If the key is non-exportable, maintain HA, backup/replication per the HSM/KMS provider, and DR tests; never casually "back up a private key" by exporting it against policy.

### Note on certificate expiry

An X.509 certificate's expiration date and a cryptographic key's lifecycle are related yet not identical. Some SAML federation profiles use certificates in metadata as **public key containers**, without enforcing browser-TLS-style PKIX trust chains/expiry; nonetheless, organizational policy should still monitor certificate validity, algorithms, and rotation cycles. **Do not wait until expiration to prepare rotation**, and never claim every SP automatically rejects a cert past `NotAfter` without verifying the exact validator.

## 12. Private key rotation requires an overlap period

Rotation is not just swapping a file. It involves partner metadata, in-flight requests/responses, caches, and every node in the system.

### 12.1. Rotating the SP signing key

1. Generate a new signing keypair, place the private key in the secret store, and verify the new public certificate.
2. Add the new public certificate to **SP metadata**/IdP registration alongside the old key if the IdP supports overlap; confirm the IdP updated trust.
3. Grant the SP workload access to read the new signing credential; verify all nodes loaded the right key (many apps load only at startup).
4. Switch the SP to sign `AuthnRequest`/logout with the new private key.
5. Watch IdP verification failures, signing algorithms, response volume, and rollback path.
6. Only retire the old cert/key once all IdPs trust the new key and old signed requests no longer need processing; clean up secret versions per policy.

**Never switch the signer before the IdP trusts the new public certificate.** Otherwise the IdP may reject every AuthnRequest even though SP metadata was updated.

### 12.2. Rotating the SP decryption key

1. Generate a new decryption keypair, store the private key secretly, and provide the public certificate to the IdP.
2. Load **both new and old decryption private keys** during the overlap window if the framework/provider supports it.
3. Publish/register the new public encryption certificate on the IdP side; check which cert the IdP actively uses, as many IdPs pick only one.
4. Switch the IdP to encrypt with the new public cert **after the SP can genuinely decrypt with it**.
5. Test encrypted Assertions using both old and new public certificates during transition in a test environment.
6. Once guaranteed no old ciphertexts remain and senders no longer use the old cert, safely retire the old decryption private key.

**Difference from signing rotation:** For decryption, the **receiving** side must retain the old private key long enough to read ciphertexts from senders still using the old cert. You cannot simply swap the keypair on the SP and delete the old one immediately. Account for in-flight messages, metadata caches, and stored ciphertexts if any.

### 12.3. Secret versioning and rollout management

A logical version identifier:

~~~text
prod/saml/portal/signing/v3      -> active
prod/saml/portal/signing/v2      -> rollover only
prod/saml/portal/decryption/v5   -> active
prod/saml/portal/decryption/v4   -> read-old-ciphertext only
~~~

Version aliases/labels depend on the secret manager. Separate the **policy to read active** from the **permission to rotate keys**. Track deployed versions per instance; verify IdP metadata/registrations are updated. If a secret volume updates files automatically, **do not assume Spring reloaded `PrivateKey` in memory**: many registrations are built at startup; perform a controlled restart/rebuild/refresh per library version.

## 13. Auditing and monitoring without exposing private keys

**What to audit:**

- Which workload identity called the secret manager/KMS, which secret/key/version, timestamp, and allow/deny outcome.
- Who created, edited, rotated, revoked, changed policies, or accessed older versions.
- Approval workflows, deployment IDs, IdP metadata changes, and public certificate fingerprints.
- Access-denied errors, spikes in reads/fetches, requests from unexpected principals or environments.
- KMS/HSM signing/decryption operations if the backend supports metadata auditing; anomalous usage thresholds.
- Enabling debug/actuator/heap dumps or exec permissions into production pods.

**Never audit by printing secret values.** Avoid logging raw PEM/private bytes, passphrases, `SAMLResponse`, Assertions, session cookies, auth tokens, or copies of secrets. Secret managers may log **fetches** yet do not track every time the app reads a mounted file or uses an in-memory key; supplement with host/container telemetry and bounded application-level events.

**Useful metrics:** `saml_signing_key_version` (internally permitted version value), `secret_fetch_errors_total`, `saml_signature_errors_total`, `saml_decryption_errors_total`, metadata refresh timestamps, and cert validity warnings. Do not expose secret versions containing tenant-sensitive identifiers to public metrics systems if policy forbids it.

## 14. Lost or compromised private key incident: runbook

Indicators: a private key appears in Git/build artifacts, an unauthorized party reads a secret path, secret manager alerts on unusual access, a private key is copied from a pod, or forensics indicate possible host compromise.

**Priority procedure:**

1. **Containment:** revoke/restrict access to affected secrets and credentials, disable stolen identities/tokens, and isolate workloads/nodes as needed per incident policy.
2. **Determine scope:** whether the key belongs to IdP or SP, signing or decryption; which environment/tenants, exposure window, and which parties may trust this key.
3. **Rotate:** generate a new keypair **without reusing the old private key**, place into protected storage, and coordinate metadata/certificates with partners.
4. **Revocation of trust:** if a signing key was exposed, do not maintain an indefinite overlap merely to avoid downtime; promptly remove the old public key from partners' verification lists per incident response.
5. **Data protection:** if a decryption key was exposed, assess encrypted assertions/ciphertexts potentially captured or stored, retention periods, and notification duties per policy.
6. **Session assessment:** decide whether SSO sessions must be revoked, re-authentication enforced, or account links restored; execute only after impact analysis.
7. **Scrub all copies:** repo/history, container image layers, CI logs, config backups, tickets, and crash dumps. Removing a key from a new commit **does not invalidate the old key**.
8. **Audit and postmortem:** preserve controlled log evidence, fix IAM/secret scanning/CI policies, and re-test the runbook.

**Critical point:** If a private signing key is exposed, publishing a new public cert **does not invalidate the old key** while the IdP still trusts the old cert. You must coordinate removing old trust. If a decryption key is exposed, rotating the key protects future ciphertexts yet does not restore confidentiality to historical ciphertexts already captured by an attacker.

## 15. Test matrix and pre-go-live checks

| Test case | Expected result |
| --- | --- |
| Runtime granted exact secret read access | App loads required signing/decryption keys without logging bytes |
| Different service account accesses same secret | `AccessDenied`, with proper metadata audit log |
| Staging identity attempts to read production private key | Denied |
| CI builds image without secrets | Build succeeds; image layers contain no keys |
| Service account only has `get` on one Secret | No namespace-wide `list/watch` unless genuinely needed |
| Pod lacks read permission | Startup/SSO fails with clear cause; never relax to `0644` to fix |
| Projected volume file mode/group changed | Test `stat -L` and `test -r` using exact runtime UID/GID |
| Debug endpoint tries to return `application.yml` or env secrets | Blocked/redacted per policy |
| Mismatched key/cert | Startup/credential validation or cryptographic test fails |
| IdP signs Response with trusted certificate | SAML verification passes if all other conditions hold |
| Different IdP signing cert while SP still uses old cert | Verification fails; metadata rotation plan exists |
| SP signs AuthnRequest with new key not yet registered at IdP | IdP rejects; never drop signing requirement |
| IdP encrypts Assertion with old cert, SP holds only new private key | Decryption fails; overlap must be properly maintained |
| IdP encrypts with new cert, SP has new decryption key | Decryption succeeds if signature/conditions also pass |
| Unauthorized secret read in audit | Alert triggers, no plaintext recorded |
| Key version revoked | Workload cannot load revoked version; old instances handled per runbook |
| Secret manager temporarily unreachable | Defined timeout/fail-closed policy or approved bounded cache |
| Key backup/restore or HSM failover | Restored per approved procedure; never export keys against policy |
| Private key accidentally committed | Incident declared, rotated, and copies purged, not just commit amended |
| Login succeeds yet user lacks permission | Authorization 403; unrelated to private key read rights |

### Short operational checklist

- [ ] Every environment/tenant uses separate keys, roles, and secret paths.
- [ ] SP private signing/decryption keys are absent from Git, images, logs, and source properties.
- [ ] Private keys are granted only to workloads that **actually sign/decrypt**.
- [ ] IdP verification certificate is **public**, obtained via trusted metadata; IdP private key is never requested.
- [ ] Secret backend enforces least-privilege IAM/RBAC, auditing, encryption at rest/in transit, and versioned lifecycles.
- [ ] Runtime runs unprivileged; secret volumes are read-only with right file mode/UID/GID, and unnecessary sidecars cannot mount keys.
- [ ] Kubernetes RBAC, pod create/exec rights, etcd encryption, and admission policies are verified.
- [ ] Spring Security credentials have right roles, trusted metadata URLs, and debug endpoints do not expose secrets.
- [ ] Signing/decryption rotation tested with old/new keys, IdP/SP metadata, and cluster rollouts.
- [ ] Runbooks exist for revocation, key compromise, disaster recovery, owners/approvals, and monitoring.

## 16. Exercises with verification answers

**Exercise A – identifying key holders.** The IdP signs an Assertion, and the SP verifies it. Who needs the private key? **The IdP**. What does the SP need? **The trusted IdP public signing certificate**. When the IdP encrypts an Assertion for the SP, who needs the private decryption key? **The SP**.

**Exercise B – designing least privilege.** An organization runs Portal SP production, Payroll SP production, and Portal staging. Write policies so Portal prod can read only `prod/saml/portal/signing` and `prod/saml/portal/decryption`, unable to list all secrets or read Payroll/staging keys. Explain who has rotation rights and how auditing works.

**Exercise C – Java 17.** Run `PrivateKeyUsageDemo.java` and verify the three lines of stdout. Modify the verifier's message and explain why verification fails. Visually inspect the code to verify it neither calls `System.out.println(pair.getPrivate())` nor writes the private key to a file.

**Exercise D – Kubernetes.** On an authorized test cluster, simulate file mode `0400` owned by root with app UID 10001; identify why the app cannot read it. Switch to a group-read model with proper `fsGroup` and verify using `stat -L`/`test -r`. **Do not test by putting real secrets into the lab**.

**Exercise E – Spring Security.** Run the demo project with a test IdP and secret mounts. Intentionally omit mounting the SP signing key in a test environment where the IdP requires signed AuthnRequests. Record the error type, then restore the secret mount instead of disabling signing.

**Exercise F – rotation.** Diagram the steps to rotate the SP decryption key from K1 to K2 while the IdP still sends Assertions encrypted with K1. Explain why the SP must retain K1 during overlap, how to test K1/K2, and when K1 may be retired.

**Exercise G – incident.** Suppose a private signing key appeared in CI logs for 30 minutes. Distinguish containment, rotation, revoking IdP trust, scanning copies, and auditing. Explain why deleting the log line without rotating the key is insufficient.

**You pass when** you can explain: (1) private/public keys per SAML role, (2) secret manager vs. non-exportable HSM/KMS, (3) least privilege applied to both IAM and pod/file permissions, (4) Spring SAML signing/decryption config without hardcoded secrets, (5) signing vs. decryption rotation differences, and (6) you can run Java 17, test denial cases, and walk through the incident runbook.

## 17. Official references

- Spring Boot 3.5 – Spring Security SAML2 Relying Party properties: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML 2.0 Authentication Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- OASIS SAML 2.0 Metadata (KeyDescriptor signing/encryption): https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
- OASIS SAML 2.0 Core (Signature/Encryption): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- Kubernetes – Good practices for Secrets: https://kubernetes.io/docs/concepts/security/secrets-good-practices/
- Kubernetes – Secrets concepts and volume mounts: https://kubernetes.io/docs/concepts/configuration/secret/
- Kubernetes – Encrypting Secret Data at Rest: https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP – Key Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html

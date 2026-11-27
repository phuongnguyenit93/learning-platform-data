# Keeping Secrets Out of Generated Config

## 1. Why Generated Config Must Not Contain Secrets

In **Spring gRPC**, applications use Protocol Buffers to define contracts, generate Java messages/stubs, and implement gRPC clients/servers in Spring. Build and deployment pipelines routinely produce additional artifacts: configuration files, Kubernetes manifests, Helm rendered output, Docker images, packages, build reports, and metadata. These artifacts may be stored long-term, copied across systems, or shared with people who do not require credential access.

If secrets are written directly into automatically generated configuration, those values can end up in:

- Git history, pull requests, code reviews, and repository clones.
- Generated YAML/JSON, profile-specific configuration files, and rendered manifests.
- Docker image layers, build caches, and image registries.
- CI/CD logs, command lines, test reports, artifacts, and caches.
- Spring configuration diagnostics, Actuator environment/configuration endpoints, or debug logs.
- Generated Java sources, protobuf descriptors, API documentation, and code examples.

**Principle:** generated config should contain only non-sensitive configuration and references to where secrets are supplied. Secrets are delivered to the process at runtime via a secret manager, secret volume, or controlled injection mechanism. Never pass secret values into code generation, build steps, or template rendering.

## 2. Distinguishing Configuration from Secrets

Configuration describes how the application should behave. Secrets prove identity or grant access.

| Data | Classification | Example |
|---|---|---|
| gRPC host, port, default timeout | Configuration | `orders-grpc.backend.svc:9090` |
| Service name, non-sensitive feature flag | Configuration | `inventory-v1`, `enable-reflection=false` |
| Maximum message size | Configuration | `4 MiB` |
| Path to a secret volume | Secret reference | `/var/run/secrets/grpc/tls.key` |
| Protected keystore/truststore password | Secret | Password unlocking the keystore |
| TLS private key | Secret | Private key of the gRPC server |
| Bearer token/API key | Secret | Credential for calling a downstream service |
| Database password | Secret | Password for repository connection |
| Signing/encryption key | Secret | Key used to sign tokens or encrypt data |
| Public CA certificate | Usually configuration/trust material | Public certificate used for chain verification |

Public certificates are not private keys. However, altering CA trust changes which peer identities are accepted, so trust bundles still require integrity and modification controls.

Do not mechanically classify every string containing `password`, `token`, or `key` as a secret; classify by whether it grants access or decrypts data. Conversely, never treat a secret as safe merely because it sits in YAML, JSON, or a generically named variable.

## 3. Generated Config Should Contain References

An application configuration file may hold service names, ports, and paths to secret files:

~~~yaml
spring:
  application:
    name: inventory-grpc

app:
  grpc:
    downstream:
      target: dns:///orders-grpc.backend.svc.cluster.local:9090
    tls:
      certificate-chain-file: /var/run/secrets/grpc/tls.crt
      private-key-file: /var/run/secrets/grpc/tls.key
      trust-bundle-file: /var/run/secrets/grpc/ca.crt
~~~

Values in this example are configuration and file paths. The contents of `tls.key`, tokens, and private credentials are supplied outside this file. The `app.grpc.*` properties are application-defined; the exact TLS property names of a Spring gRPC starter depend on the version and configuration mechanism in use.

A generated manifest or template can reference a Secret by name:

~~~yaml
volumes:
  - name: grpc-tls
    secret:
      secretName: inventory-grpc-tls

containers:
  - name: inventory
    volumeMounts:
      - name: grpc-tls
        mountPath: /var/run/secrets/grpc
        readOnly: true
~~~

The manifest specifies which Secret object is mounted and where. The private key value does not appear in the rendered manifest. Permission to read the Secret object must be managed separately with RBAC and cluster policies.

## 4. Keeping Secrets Out of Source and Generated Source

Never put secrets into:

- Committed `application.yml`, `application-*.yml`, `bootstrap.yml`, or profile files.
- Committed `.env` files, shared `gradle.properties`, or build scripts.
- Proto options, custom annotations, comments, descriptors, or sample requests.
- Generated Java classes, source templates, code generator arguments, or constants.
- Dockerfiles or image `ENV`/`ARG` instructions used to pass credentials or build layers.
- Helm values stored in repositories if those values contain real secrets.

Protobuf contracts describe only business data and RPCs. If an RPC accepts an access token or credential in metadata, never place a live sample token in `.proto` files, generated stubs, READMEs, or test fixtures. Use expired dummy data or tokens scoped exclusively to isolated tests.

Generated Java code must produce identical content regardless of dev, staging, or production environments. If code generation needs a secret to produce output, revisit the design: generators normally need only schemas, compiler options, and versions—not runtime credentials.

## 5. Injecting Secrets at Runtime

Three common approaches exist:

1. **Secret manager API:** the application or platform identity fetches secrets from a secret management service at startup or on demand.
2. **Mounted secret file:** the platform mounts private keys, certificates, or passwords as files with restricted read permissions.
3. **Environment variable:** the runtime injects secrets into the process environment; convenient, but requires controls over process dumps, diagnostics, and container access.

Prefer the mechanism matching the secret type and deployment platform. Private keys are typically convenient when mounted as files or supplied via a dedicated provider. Short-lived tokens can be issued dynamically through workload identity or a credential provider.

For example, Spring Boot can import a config tree from a mounted secret directory:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Files in that directory can be exposed as runtime properties by filename. This configuration only declares the source location; secret values reside in files mounted by the platform. Verify property names, file permissions, and how the application binds them. Never expose endpoints or logs that dump the entire environment/configuration without strict access control.

In Spring gRPC, adapters or TLS configuration read paths/credentials at runtime via APIs supported by your starter/version. Do not assume all starters use identical properties to load certificates, private keys, or truststores.

## 6. Kubernetes Secrets and External Secret Providers

Kubernetes `Secret` objects separate sensitive data from ordinary `ConfigMap` and `Deployment` manifests. However, values inside Secret creation manifests are typically Base64-encoded; Base64 is not encryption.

When using Kubernetes Secrets:

- Restrict RBAC: only necessary service accounts and operators may read secrets.
- Enable encryption at rest for Secret data in etcd per cluster policy.
- Do not grant broad `list`/`watch` permissions on Secrets to all workloads.
- Mount secrets read-only and restrict which containers/users can read them.
- Never render secret values into Helm output, GitOps diffs, or CI logs.
- Consider an external secret operator or CSI driver to sync from a cloud secret manager/HSM.
- Monitor audit logs when secrets are read or modified.

Example `Deployment` referencing a Secret:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-grpc
spec:
  template:
    spec:
      containers:
        - name: inventory
          image: registry.example/inventory-grpc:1.0.0
          volumeMounts:
            - name: grpc-tls
              mountPath: /var/run/secrets/grpc
              readOnly: true
      volumes:
        - name: grpc-tls
          secret:
            secretName: inventory-grpc-tls
~~~

The `Deployment` only references `inventory-grpc-tls`. The Secret object is created/provisioned by a separately privileged process; never embed `tls.key` inside the `Deployment` manifest itself.

## 7. Helm and Generated Manifests

Helm templates often generate environment-specific manifests. Templates should accept **secret names or references**, not literal private keys/passwords.

Example:

~~~yaml
volumes:
  - name: grpc-tls
    secret:
      secretName: {{ .Values.grpc.tls.existingSecret | quote }}
~~~

`values.yaml` can contain the `existingSecret` name, ports, targets, and non-sensitive policies. Avoid declaring `privateKey`, `clientSecret`, or `password` with real values inside repository values files.

Inspect the rendered output as well. A safe template can still be overridden by a pipeline passing secret values via `--set`, `--set-string`, generated values files, or command-line arguments. Command lines can end up in shell history, process listings, or CI logs.

If a Secret object must be created, let a secret manager/operator or a protected deployment step create it from the secret source. Never store output containing credentials in shared artifacts. Generated manifests should hold resource names, volume references, or external secret references.

## 8. Docker Builds and CI/CD Must Not Package Secrets

Do not use Docker build arguments or environment variables during image builds to pass runtime secrets:

~~~dockerfile
# Do not do this:
ARG GRPC_PRIVATE_KEY
ENV GRPC_PRIVATE_KEY=$GRPC_PRIVATE_KEY
~~~

Values can persist in image metadata, layers, build caches, or the build system. Docker build secret mounts may be used for credentials needed only during a build step (such as pulling dependencies from a private registry), but never turn them into runtime secrets and never copy secrets into the image.

Pipelines should cleanly separate stages:

| Stage | Permitted Data |
|---|---|
| Compile/code generation | Source, proto schemas, compiler/plugin versions, non-secret dependency config |
| Unit tests | Fake credentials or short-lived, tightly scoped test secrets |
| Build image | Binaries/generated code and non-secret runtime config |
| Render deployment config | Secret names/references, never rendered secret values |
| Deploy/runtime | Workload identity or read access to secret manager/secret volumes |

Never print the environment, full commands, rendered manifests containing sensitive data, or secret objects to logs. Restrict read access to artifacts, caches, test reports, and build logs, and enforce appropriate retention periods.

## 9. Secrets in gRPC Metadata and Client Credentials

A client may send a bearer token in metadata:

~~~text
authorization: Bearer <access-token>
~~~

Tokens are runtime secrets. Never hardcode tokens in generated config, source code, or stub constructors. Clients should obtain tokens from a refresh-capable credential provider and attach them to call metadata via `CallCredentials` or an interceptor designed for credentials.

Proper flow:

1. Client establishes workload identity or principal.
2. Credential provider acquires a short-lived token from the identity/secret service.
3. Call credentials attach the authorization header per RPC.
4. Tokens are refreshed before expiry; refresh failures are handled safely.
5. Logging/interceptors strip or redact authorization metadata.

Never log the entire metadata map. Metadata can contain bearer tokens, session identifiers, tenant context, or internal data. Log only an allowlist such as method, correlation ID, and status; redact sensitive headers.

Never place tokens in `Status` descriptions, exception messages, or trace attributes. When verifying authentication in tests, use dummy tokens or short-lived test-environment tokens and never commit them to snapshots/artifacts.

## 10. Secrets for TLS and mTLS

gRPC TLS may require the following data:

| Data | Is It a Secret? | Where Provided |
|---|---|---|
| Server private key | Yes | Secret manager or read-only secret volume |
| Client private key for mTLS | Yes | Secret manager/identity provider |
| Keystore password | Yes | Secret provider |
| Client bearer token | Yes, usually short-lived | Workload identity/token provider |
| Server certificate | Usually no | Certificate store/secret volume |
| Public CA certificate | Not a private secret | Managed trust bundle |

Generated config should retain only paths, secret resource names, or references to credential providers. Private keys and passwords must be read at runtime with minimal permissions.

If using PKCS12/JKS, the keystore holds the private key and certificate chain; the truststore holds trusted peer CAs/certificates. Never put store passwords in generated YAML. If using PEM, protect the private key file and restrict read permissions. Public certificates still need timely updates during rotation to avoid TLS disruptions.

## 11. Preventing Leaks via Spring Diagnostics and Logging

Even when secrets are absent from generated files, they can still leak after injection:

- Logging `Environment`, `System.getenv()`, or `System.getProperties()`.
- Calling `toString()` on configuration objects containing passwords/tokens.
- Enabling debug logging for HTTP/gRPC metadata.
- Exposing Actuator `env`, `configprops`, heap dumps, or diagnostic endpoints to unauthorized users.
- Including secrets in exception messages or validation errors.
- Writing private keys/tokens into tracing baggage or span attributes.

Be sure to:

- Avoid logging configuration objects with secret fields.
- Use redacted `toString` methods or omit secrets from logged DTOs.
- Restrict permissions and exposure of Actuator/diagnostics.
- Redact `authorization`, cookies, API keys, and sensitive metadata.
- Keep secrets in memory only as long as necessary; avoid copying them into uncontrolled caches/logs.
- Never put secrets in metric labels, which both leaks data and creates high cardinality.

## 12. Rotating and Revoking Secrets

Secrets must not remain unchanged forever. Design rotation before an incident occurs:

1. Create a new secret version in the secret manager.
2. Update trust/credential policies so the transition period accepts required identities.
3. Deliver the new secret to workloads or mount the new version.
4. Reload credentials if supported by the application/starter; otherwise perform a safe rollout/restart.
5. Check health and run test RPCs over TLS/mTLS.
6. Revoke the old version after all clients/servers have migrated.
7. Record an audit entry noting timestamp, actor, and rotated version—never the secret value.

For certificate rotation, avoid revoking the old CA before clients trust the new CA. For bearer tokens, prefer short-lived tokens refreshed before expiry. Do not assume the Spring gRPC starter automatically reloads private keys or truststores when files change; verify reload capabilities for your active version and transport.

Generated config does not need to change when secret values rotate if references stay stable. This is a major benefit of separating references from secret material.

## 13. Scanning Generated Artifacts Before Release

Inspect outputs, not just source templates:

- Scan repositories and diffs for private key headers, token patterns, passwords, or known credentials.
- Render Helm/Kustomize/Terraform output in a controlled environment and scan before publishing.
- Inspect Docker image layers/metadata and build artifacts.
- Inspect CI logs, test reports, caches, and generated documentation.
- Check protobuf generated sources, descriptors, and source maps if present.
- Inspect `application-*.yml`, config bundles, and profiles packaged inside JARs.

Secret scanners can produce false positives or miss novel credentials. Combine pattern scanning, entropy detection, reviewed allowlists, and manual review of high-risk areas. Never put real secrets into tests merely to verify a scanner.

Example quick check for PEM private keys in a workspace:

~~~bash
grep -R -n --exclude-dir=.git \
  -E 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' .
~~~

This command is only an initial signal; it misses many tokens/passwords and may flag dummy test fixtures. Use proper secret scanning in CI and ensure scan output never prints the raw matched secret.

## 14. Responding When a Secret Leaks into Generated Config

Deleting the secret line from the current file is not enough. Credentials may remain in Git history, image layers, CI logs, artifacts, or caches.

Response workflow:

1. Identify the credential type, permission scope, and everywhere it appeared.
2. Revoke/rotate the secret immediately based on risk; do not wait to finish cleaning the repository.
3. Inspect audit logs for anomalous access.
4. Delete or replace exposed artifacts following repository/registry/CI governance.
5. If rewriting Git history is necessary, coordinate with repository owners and notify users to re-clone; rewriting history does not revoke credentials.
6. Add scanners/pre-commit/CI checks and fix the pipeline to pass only secret references.
7. Document the incident and verify the new secret does not appear in generated output.

Never paste leaked secrets into chat, tickets, or reports as an "illustration." Record only the secret type, location, timestamp, scope, and rotation/revocation status.

## 15. Checklist for Secure Generated Config

| Question | Desired Answer |
|---|---|
| Do generated files contain passwords/tokens/private keys? | No |
| Do templates/values contain literal secrets? | No |
| Does generated config use secret references/paths? | Yes |
| Are secrets supplied at runtime from a controlled source? | Yes |
| Do workloads have read access only to required secrets? | Yes |
| Do Kubernetes Secrets have encryption at rest and proper RBAC? | Yes |
| Do Docker images/build caches contain secrets? | No |
| Are CI logs/artifacts/test reports protected and scanned? | Yes |
| Are gRPC metadata and TLS key material logged? | No |
| Is there a rotation/revocation process and post-rotation verification? | Yes |
| Can Actuator/config diagnostics expose secrets? | No |

## 16. Common Mistakes

| Anti-Pattern | Consequence | Correct Approach |
|---|---|---|
| Writing tokens into `application-prod.yml` | Secret persists in source/artifacts | Use secret references and runtime injection |
| Putting private keys into Helm values | Rendered manifests or CI logs may expose keys | Reference only Secret resources/external providers |
| Treating Base64 as encryption | Anyone reading the manifest can decode values | Protect Secrets with RBAC and encryption at rest |
| Passing secrets via Docker `ARG`/`ENV` at build time | Secrets may persist in layers/caches/metadata | Use build secrets for build needs; supply runtime secrets at run time |
| Hardcoding a static bearer token in an interceptor | Hard to rotate, easy to leak, and tokens expire | Use a credential provider/`CallCredentials` |
| Logging all gRPC metadata | Authorization tokens may appear in logs | Allowlist and redact sensitive headers |
| Assuming deleting the exposed file suffices | Git history, images, and logs still retain credentials | Revoke/rotate first, then purge all copies |
| Assuming the starter auto-reloads keys | Workloads may keep using old certificates | Verify reload support or perform controlled rollouts |

**Takeaway:** Generated config is an artifact that can be stored, shared, and distributed, so it should contain only non-sensitive configuration and secret references. Keep tokens, passwords, and private keys out of source code, generated code, Helm outputs, Docker images, and CI artifacts. Supply secrets at runtime via a secret manager, mounted files, or an identity provider; restrict read permissions, redact logs, scan outputs, and prepare for rotation/revocation. In Spring gRPC, protect bearer metadata and TLS/mTLS key material separately, and verify configuration against the exact starter/version running in production.

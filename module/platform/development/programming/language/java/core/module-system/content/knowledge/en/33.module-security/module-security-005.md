# Service Providers and Trusted Implementation Code

## 1. A Service Provider Is a Trust Boundary

In the Java Platform Module System (JPMS), the Service Provider Interface (SPI) allows one module to define a contract while other modules supply implementations. Consumers typically discover implementations using `ServiceLoader` instead of depending directly on provider classes.

This mechanism makes applications extensible, yet it creates an important security decision: **the provider is code that will be loaded and executed inside the application**.

For example, an application may discover formatters, database drivers, plugins, or file processors from providers on the module path. When a provider is instantiated and its methods are called, the implementation can perform any operations permitted to the Java process, such as:

- Reading files that the account running the application has permission to access.
- Sending data over the network.
- Reading environment variables or configuration visible to the process.
- Spawning threads and consuming CPU and memory.
- Calling other libraries or initiating connections to external systems.

Therefore, a module declaring a valid `provides` directive or being discovered by `ServiceLoader` does not prove that the implementation is safe. Only load providers from evaluated and approved sources.

## 2. Module Encapsulation Is Not a Sandbox

JPMS provides module boundaries to manage readability, `exports`, `opens`, and dependencies. These mechanisms help limit the APIs other modules can access under Java rules, yet **they do not isolate a provider's execution privileges from the process**.

For example:

```java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.JsonFormatter;
}
```

The `provides` directive registers an implementation for a service type. It does not restrict the provider to reading only one directory, does not block network connections on its own, and does not prevent the provider from reading environment variables.

Similarly:

- Packages that are not `exports` are access-restricted under module rules, but the provider can still call other public APIs that the process is permitted to use.
- `opens` controls reflective access to packages, not a sandbox mechanism.
- A separate `ModuleLayer` or class loader helps organize and load classes, but by themselves they do not create a security boundary equivalent to a separate operating system process.

Do not treat placing a provider in its own module as sufficient to run untrusted code safely.

## 3. Service Flow and Where Providers Execute

Suppose we have a service contract:

```java
package com.acme.spi;

public interface Formatter {
    String format(String input);
}
```

SPI module:

```java
module com.acme.spi {
    exports com.acme.spi;
}
```

Provider implementation:

```java
package com.acme.provider.json;

import com.acme.spi.Formatter;

public final class JsonFormatter implements Formatter {
    public JsonFormatter() {
    }

    @Override
    public String format(String input) {
        return "{\"value\":\"" + input + "\"}";
    }
}
```

Provider module:

```java
module com.acme.provider.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.json.JsonFormatter;
}
```

Consumer module:

```java
module com.acme.app {
    requires com.acme.spi;

    uses com.acme.spi.Formatter;
}
```

Consumer discovers and invokes the provider:

```java
import com.acme.spi.Formatter;
import java.util.ServiceLoader;

ServiceLoader<Formatter> services =
        ServiceLoader.load(Formatter.class);

for (Formatter formatter : services) {
    String result = formatter.format("hello");
    System.out.println(result);
}
```

Calling `ServiceLoader.load` creates a service lookup mechanism. Providers are generally loaded and instantiated lazily while iterating over the results; the constructor or provider method can run at that moment. When the consumer calls `format`, the implementation executes inside the consumer's process.

Therefore, discovery, instantiation, and method invocation phases must all be considered in the threat model. Do not assume that merely calling an interface is a harmless operation.

## 4. Only Put Artifacts from Trusted Sources on the Module Path

The first line of defense is controlling the origin of JARs and dependencies brought into the application.

The following measures should be applied:

- Only obtain artifacts from approved internal or vendor repositories/registries.
- Pin specific dependency versions; avoid downloading mutable versions arbitrarily during production startup.
- Verify checksums from an independent trusted channel separate from where the artifact was downloaded.
- Verify signatures and publisher identity when the distribution system provides signatures.
- Review source changes, transitive dependencies, release history, and privileges the provider needs.
- Scan dependencies for vulnerabilities and maintain a Software Bill of Materials (SBOM) for releases.
- Use reproducible builds and controlled review/publish workflows where appropriate.

You can compute the SHA-256 of a JAR:

```bash
sha256sum provider-json.jar
```

On PowerShell:

```powershell
Get-FileHash .\provider-json.jar -Algorithm SHA256
```

Compare the result against the checksum published via a trusted channel. A hash only confirms the file matches a known build; it does not prove that build contains no malicious code.

If the artifact is signed, you can verify the JAR signature:

```bash
jarsigner -verify -verbose -certs provider-json.jar
```

Inspect the verification outcome and certificate identity according to organizational trust policy. A valid signature indicates the signed contents have not been modified since signing and correspond to the signing key; it does not prove the code inside is safe. A self-signed certificate or untrusted signer also does not become trustworthy merely because the signature is cryptographically valid.

## 5. Controlling Which Providers Are Allowed to Run

Do not automatically run every provider present on the module path if the application only expects a small set of implementations.

Design an allowlist based on approved artifacts/modules, for example:

```text
Approved providers
- module: com.acme.provider.json
  artifact: com.acme:provider-json
  version: 2.4.1
  sha256: <verified digest>
- module: com.acme.provider.xml
  artifact: com.acme:provider-xml
  version: 1.8.0
  sha256: <verified digest>
```

This is an illustrative configuration; digests must come from the actual release process, never dummy values.

Before creating a module layer or starting the application, determine the exact provider modules allowed in the deployment. Do not let end users arbitrarily drop any JAR into a plugin directory that is automatically scanned.

If providers need to be filtered at the consumer layer, you can inspect the provider type before calling `get()`:

```java
import com.acme.spi.Formatter;
import java.util.Set;
import java.util.ServiceLoader;

Set<String> approvedTypes = Set.of(
        "com.acme.provider.json.JsonFormatter"
);

ServiceLoader<Formatter> services =
        ServiceLoader.load(Formatter.class);

for (ServiceLoader.Provider<Formatter> candidate
        : services.stream().toList()) {
    String typeName = candidate.type().getName();

    if (!approvedTypes.contains(typeName)) {
        continue;
    }

    Formatter formatter = candidate.get();
    System.out.println(formatter.format("hello"));
}
```

This snippet illustrates how to instantiate only providers with accepted type names. However, a class-name allowlist **does not authenticate artifact provenance**: another JAR could provide a class with the same name. Verify artifacts, modules, and checksums before a provider enters runtime; filtering in the consumer is only an additional control layer.

Do not rely on `ServiceLoader` iteration order to choose a preferred provider. If the application needs a single implementation, select it via explicit configuration and report an error when the configured provider does not exist or is not approved.

## 6. Granting Minimal Data and Privileges to Providers

An SPI should have a small, clear contract and pass only the data necessary for the task.

For example, if a provider only needs to format a string, do not pass the entire application context, database connection, credential store, or system administration object to the implementation.

Recommendations:

- Use DTOs containing minimal data instead of passing overly privileged objects.
- Do not put passwords, access tokens, or secrets in constructors, system properties, or logs.
- Separate read-only interfaces from mutating interfaces if a provider only needs one of those capabilities.
- Validate inputs before calling the provider and validate outputs before using them.
- Set input/output size limits and workload bounds if the service processes large data.
- Avoid letting the provider retain references to mutable objects or unnecessary shared state.

Example contract that limits capabilities:

```java
public interface DocumentFormatter {
    byte[] format(ReadOnlyDocument input);
}
```

If the provider only needs to read a document, supply a read-only abstraction instead of an object with permission to edit the original file or access the entire filesystem.

However, a narrow interface only reduces the privileges the application explicitly hands over via API. It does not prevent the provider from calling system APIs the process is permitted to use.

## 7. Handling Errors and Unstable Behavior

A provider may throw exceptions, return malformed data, fail initialization, or consume excessive resources.

When using `ServiceLoader`, handle errors at the integration boundary:

```java
import com.acme.spi.Formatter;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

try {
    ServiceLoader<Formatter> services =
            ServiceLoader.load(Formatter.class);

    for (Formatter formatter : services) {
        try {
            String result = formatter.format("hello");
            validateResult(result);
        } catch (RuntimeException error) {
            reportProviderFailure(error);
        }
    }
} catch (ServiceConfigurationError error) {
    reportProviderConfigurationFailure(error);
}
```

The `validateResult`, `reportProviderFailure`, and `reportProviderConfigurationFailure` methods represent application-specific handling. This example illustrates where to place the error boundary, not a replacement for retry or recovery policies suited to each service.

Notes:

- `ServiceConfigurationError` can occur when provider configuration is invalid or when a provider cannot be loaded/instantiated.
- A provider can throw runtime exceptions while processing a request; determine which errors can be skipped and which must abort the request.
- Do not catch all `Throwable` and continue as if nothing happened; serious JVM errors must be handled per application policy.
- Log provider name, artifact version, and correlation ID for traceability, but never log sensitive payloads or secrets.
- Do not blindly retry operations with side effects; retries can duplicate transactions or resend data multiple times.

A timeout on the calling thread cannot guarantee stopping a provider running synchronous code in the same JVM. If hard limits on CPU time, memory, or the ability to terminate a provider are required, move it into a separate process.

## 8. When Should a Provider Run in a Separate Process?

If a provider comes from an insufficiently trusted third party, allows users to upload arbitrary plugins, or processes highly sensitive data, consider an out-of-process architecture.

```text
Main application
      |
      | IPC / HTTP / message protocol
      v
Provider worker process
      |
      +-- dedicated OS user
      +-- restricted filesystem
      +-- restricted network
      +-- CPU / memory limits
      +-- independent lifecycle
```

The worker process can run under a dedicated OS account, container, or deployment platform sandbox with:

- Only the required data directories mounted.
- Outbound network blocked if the provider does not need network access.
- Limits on CPU, memory, process count, and processing time.
- Data transferred via a schema-validated protocol with size limits.
- Mutual authentication of communication endpoints and validation of every message.
- Ability to restart or terminate the worker without crashing the entire application.

IPC also carries its own risks: caller authentication, protecting data in transit, controlling message replay where appropriate, and resource limits are needed. However, a separate process provides OS boundaries that modules or class loaders in the same JVM cannot offer.

## 9. Managing Provider Updates and Lifecycle

A provider trusted at release time can still change in a later update. Therefore, manage its lifecycle:

1. Pin the version and checksum of each provider in the release manifest.
2. Review dependency and privilege changes before upgrading.
3. Verify compatibility of the service contract and module descriptor.
4. Run functional, security, and performance tests with the exact artifact to be released.
5. Update providers only through an approved pipeline.
6. Record module, version, digest, and release provenance in logs/telemetry.
7. Maintain a rollback process if a new provider fails or has a vulnerability.

Do not download a new JAR from a URL supplied by a user request and load it directly into a production application. If dynamic plugin installation is supported, separate downloading, verification, review, and activation into controlled steps.

## 10. Security Checklist Before Enabling a Provider

- [ ] Artifact originates from an approved repository/registry.
- [ ] Version and checksum match a trusted release manifest.
- [ ] Signatures are verified per trust policy if the artifact is signed.
- [ ] Source, transitive dependencies, and release history have been reviewed.
- [ ] Module/provider is on the deployment's allowlist.
- [ ] Service contract grants only minimal data and capabilities.
- [ ] Inputs/outputs are validated and have appropriate resource limits.
- [ ] Initialization errors and service invocation errors are safely logged.
- [ ] Secrets or sensitive data are not written to logs.
- [ ] Insufficiently trusted providers are isolated in separate processes.
- [ ] Provider version, digest, and origin are recorded for audit/rollback.

## Takeaways

- A provider loaded by `ServiceLoader` is executable code running in the application process.
- JPMS encapsulation, `ModuleLayer`, and class loaders are not security sandboxes.
- Only place artifacts from approved sources on the module path; verify versions, checksums, and signatures per trust policy.
- Provider allowlists help control selection, yet class names do not prove JAR provenance.
- Grant minimal data/capabilities, validate inputs/outputs, and handle errors at the service boundary.
- If a provider cannot be fully trusted, run it in a separate process with restricted OS permissions and resources.
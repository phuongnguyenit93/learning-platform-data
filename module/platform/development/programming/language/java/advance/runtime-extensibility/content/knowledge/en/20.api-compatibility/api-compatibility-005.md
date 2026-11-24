# Negotiating Supported Capabilities and Rejecting Incompatible Contract Versions

## 1. Why being able to load a class does not mean it is compatible

In a Java runtime-extensibility system, plugins and hosts communicate through an **API/SPI contract**. `ServiceLoader` or a class loader can discover a provider, but instantiating a class does not prove the provider understands the semantics the host requires. A plugin may have compiled against an older contract version, lack new functionality, interpret data formats differently, or rely on removed behavior.

Three questions must be distinguished:

1. **Binary compatibility:** does plugin bytecode link against the classes/methods the host currently provides?
2. **Contract compatibility:** are the meaning, invariants, data formats, and lifecycle of the API version still honored?
3. **Capability compatibility:** does the specific plugin support the required features for the current workload?

For example, both plugin and host know `PaymentProvider`, yet the host requires idempotent refunds while the plugin handles only one-way payments. Even though the object has a valid Java type, the host must **reject the plugin for refund tasks** rather than waiting for production failures.

## 2. What components make up a negotiation contract?

| Information | Provider side | Verification method |
| --- | --- | --- |
| Contract/API identity | Shared SDK and host | Same service interface/namespace and class identity |
| Contract major/minor or protocol version | SDK/plugin metadata | Published compatibility policy |
| Supported version range | Plugin or manifest | Host version falls within supported range |
| Capability set | Provider | Contains all required capabilities |
| Capability semantics | Contract documentation | Clear definition of preconditions/outputs per capability |
| Runtime prerequisites | Plugin metadata | JDK, OS, native dependencies, permissions/quotas |
| Optional extensions | Provider | Invoked only when support is confirmed |

**Principle:** negotiation must happen **before activating a provider to receive requests**, ideally before opening heavy resources or registering callbacks. Any failure during the handshake must lead to a clear rejection, never marking the plugin as READY.

## 3. Separating compatibility policy from version string comparison

Semantic Versioning (SemVer) can be a useful **release convention**, but the JVM does not enforce SemVer on APIs, and JPMS module versions do not automatically solve all semantic compatibility. A host may define:

- `major` changes on breaking contract changes: e.g., removing methods, changing data types, changing mandatory semantics.
- `minor` increments when adding optional capabilities or specified compatible behavior.
- `patch` is used for bug fixes that do not break the contract.

However, checking `host.major == plugin.major` is not enough. You must verify required features, bounds of optional behavior, minimum minor version, and actual binary linkage. Conversely, a plugin reporting the same major version without declaring a required capability must still be rejected.

Example policy for a published contract:

```text
Host contract: 2.4
Supported provider major: 2
Provider requires host minor <= provider.maxMinorSupported
Host requires capability: BATCH
Optional host capability: AUDIT

Provider A: major=2, supportedMinor=1..5, capabilities=[BATCH] -> ACCEPT
Provider B: major=1, supportedMinor=0..9, capabilities=[BATCH] -> REJECT major
Provider C: major=2, supportedMinor=1..5, capabilities=[] -> REJECT capability
Provider D: major=2, supportedMinor=5..8, capabilities=[BATCH] -> REJECT range
```

This is an **illustrative policy**, not a mandatory rule for every plugin system. For strict contracts, host and provider may use an exact version or protocol schema hash instead of a range.

## 4. Interface design: metadata first, operations second

The host should own `ProviderDescriptor` and the validator in a stable API/host module. Providers can declare a version range and a capability set; the host must validate that data rather than blindly trusting a self-advertised string.

What to avoid:

```java
// Anti-pattern: calling a new feature only to discover the plugin does not support it.
provider.processBatch(input);
```

This snippet is not a standalone program. The right approach is **validate → select → activate → invoke**.

Negotiation is usually runtime capability discovery rather than open-ended bargaining. The host must clearly specify required criteria; the provider only declares its capabilities; the final decision belongs to the host. Sensitive capabilities (such as file or network permissions) must be verified against actual OS/runtime permissions, not solely self-declared metadata.

## 5. Complete Java 17+ example: host accepting/rejecting providers

The example uses a simple service contract. Everything is in one file so it runs standalone, though in a real plugin deployment you should separate the SPI into an API module, providers into separate JARs, and let the host perform negotiation.

Create `CapabilityNegotiationDemo.java`:

```java
import java.util.EnumSet;
import java.util.List;
import java.util.Set;

public class CapabilityNegotiationDemo {
    enum Capability { BATCH, AUDIT }

    record Contract(int major, int minor) {
        Contract {
            if (major < 0 || minor < 0) {
                throw new IllegalArgumentException("Invalid contract version");
            }
        }
    }

    record Descriptor(int major, int minMinor, int maxMinor,
                      Set<Capability> capabilities) {
        Descriptor {
            if (major < 0 || minMinor < 0 || maxMinor < minMinor) {
                throw new IllegalArgumentException("Invalid version range");
            }
            capabilities = Set.copyOf(capabilities);
        }
    }

    interface Provider {
        String name();
        Descriptor descriptor();
        String executeBatch();
    }

    record Candidate(String name, Descriptor descriptor)
            implements Provider {
        @Override
        public String executeBatch() {
            return "processed by " + name;
        }
    }

    static String rejection(Contract host,
                            Set<Capability> required, Descriptor d) {
        if (host.major() != d.major()) {
            return "unsupported contract major";
        }
        if (host.minor() < d.minMinor() || host.minor() > d.maxMinor()) {
            return "unsupported contract minor";
        }
        if (!d.capabilities().containsAll(required)) {
            return "missing required capability";
        }
        return null;
    }

    public static void main(String[] args) {
        Contract host = new Contract(2, 4);
        Set<Capability> required = EnumSet.of(Capability.BATCH);
        List<Provider> providers = List.of(
            new Candidate("A", new Descriptor(2, 1, 5,
                EnumSet.of(Capability.BATCH))),
            new Candidate("B", new Descriptor(1, 0, 9,
                EnumSet.of(Capability.BATCH))),
            new Candidate("C", new Descriptor(2, 1, 5,
                EnumSet.noneOf(Capability.class))),
            new Candidate("D", new Descriptor(2, 5, 8,
                EnumSet.of(Capability.BATCH)))
        );

        for (Provider provider : providers) {
            String reason = rejection(host, required, provider.descriptor());
            if (reason != null) {
                System.out.println(provider.name() + ": REJECT - " + reason);
                continue;
            }
            System.out.println(provider.name() + ": ACCEPT - "
                + provider.executeBatch());
        }
    }
}
```

Compile/run:

```bash
javac --release 17 CapabilityNegotiationDemo.java
java CapabilityNegotiationDemo
```

Output:

```text
A: ACCEPT - processed by A
B: REJECT - unsupported contract major
C: REJECT - missing required capability
D: REJECT - unsupported contract minor
```

The example demonstrates that **a provider being visible** does not mean **being selected**. The host evaluates the version range and capabilities first, and only then invokes `executeBatch()` on provider A. In real applications, ensure the metadata/handshake part uses a compatible shared API; if the handshake interface signature itself breaks, the plugin may fail during linkage before it can report its version.

## 6. Integrating negotiation into ServiceLoader or a plugin registry

For service providers loaded via SPI, the processing order should be:

```text
Discover candidates
   |
Check artifact descriptor / supported API
   |
Resolve/load using compatible classloader or ModuleLayer
   |
Read provider descriptor
   |
Validate version range + required capabilities
   |
Reject with reason OR activate
   |
Route requests only to accepted providers
```

Illustrative snippet (inside a method with `ServiceLoader<Provider> loader`, `Contract host`, and `Set<Capability> required`):

```java
for (Provider provider : loader) {
    Descriptor metadata = provider.descriptor();
    String reason = rejection(host, required, metadata);
    if (reason != null) {
        logRejected(provider.name(), reason);
        continue;
    }
    registerAccepted(provider);
}
```

In this snippet, `logRejected` and `registerAccepted` are application-defined methods. `ServiceLoader` may instantiate provider classes as its iterator is traversed; if constructor/provider initialization already has side effects, checking `descriptor()` alone is not safe enough. Advanced plugin frameworks should read metadata **before instantiating implementations** (signed or verified manifests/descriptors), then load the provider and re-verify.

In particular, when host and provider are loaded by different classloaders, both must see **the exact same SPI class identity**. Loading two copies of an identically named interface from child-first loaders does not automatically create a compatible contract; it can cause `ClassCastException`, `ServiceConfigurationError`, or linkage errors.

## 7. Negotiating capabilities with explicit semantics

A capability is not just a string label. For instance, `BATCH` needs to define:

- Does `BATCH` process atomically or allow partial success?
- What are the maximum batch size, ordering guarantees, and retry policy?
- Do failures carry an idempotency key?
- Which contract version introduced this capability?
- If the capability is declared yet a request exceeds limits, should the host fall back or reject?

Attach a schema/contract revision to each capability if semantics evolve independently, or use a typed descriptor such as `BatchSupport(maxSize, atomic, retrySafe)`. `Set<String>` may suffice for demos, while production needs validation to prevent typos, unknown capabilities, and silent semantic drift.

**Optional capability:** the host calls it only when the provider confirms support. **Required capability:** its absence is grounds for rejection. Do not fall back to an approach that breaks correctness (such as turning atomic payment into partial) if the business contract forbids it.

## 8. Fail-fast and actionable error reporting

Output from negotiation should not be just a boolean. It needs specific, structured reasons:

| Rejection code | Meaning | Operational action |
| --- | --- | --- |
| `API_MAJOR_MISMATCH` | Supported major does not match | Upgrade/downgrade SDK or provider |
| `API_MINOR_OUT_OF_RANGE` | Host falls outside plugin's supported range | Determine a compatible version range |
| `MISSING_CAPABILITY` | Lacks a required feature | Install a suitable provider or change requirements |
| `INVALID_DESCRIPTOR` | Metadata is empty/malformed/inconsistent | Fix the plugin artifact |
| `BINARY_INCOMPATIBLE` | Linkage/API signature mismatch | Inspect JAR, SDK version, classloader |
| `RUNTIME_UNSUPPORTED` | JDK/OS/native dependency unmet | Choose a compatible runtime |

The host should log the plugin ID, artifact version, host contract, supported range, required vs advertised capabilities, and reason code. Avoid dumping long stack traces for every known version incompatibility; keep stack traces only for unexpected errors. Do not expose paths or secrets in end-user messages.

## 9. When must renegotiation occur?

Not only at startup. Renegotiation is needed when:

1. The host upgrades its API version or changes required capabilities.
2. A plugin is hot-reloaded or its JAR/provider is replaced.
3. A new `ModuleLayer` or classloader is created for a new plugin group.
4. The workload switches to a new mode needing different features (e.g., `AUDIT`).
5. A plugin reports verifiable runtime capability degradation.

Each time a new plugin set is published, perform handshake and health checks **before the atomic switch**. In-flight requests on the old plugin must complete or be canceled per policy, never switching providers mid-transaction.

Do not cache negotiation results keyed solely by provider name: the same name can appear across multiple versions/layers. Cache keys should include artifact identity/version, contract revision, required capabilities, and execution environment where relevant.

## 10. Binary compatibility and the limits of negotiation

Negotiation works only if the host can **read metadata** or call a **stable handshake API**. If a Java class has had its signature changed incompatibly, loading/linking may fail before `descriptor()` can ever be called.

Breaking changes to watch out for:

- Removing or changing the signature of a method called by old plugin bytecode: can cause `NoSuchMethodError`.
- Changing static/instance method kind or field type: can cause `IncompatibleClassChangeError`.
- Changing interface hierarchy or duplicating an interface class across loaders: can cause a class identity mismatch.
- Adding an abstract method to an SPI interface can allow old providers to have compiled previously yet cause `AbstractMethodError` when the new host calls the new method.
- Changing the meaning of a field/enum without bumping major: Java may link it, yet semantics are wrong.

Therefore, layer your defenses: **artifact manifest metadata** stable enough for preflight before loading, a minimal and stable **SPI handshake**, and then detailed **capability validation**. Do not try to catch every `LinkageError` and force a dangerous plugin into service; isolate failures and fail closed.

## 11. Testing the compatibility matrix

| Test | Expectation |
| --- | --- |
| Same major, minor in range, all required capabilities present | Accept |
| Wrong major | Reject before activation |
| Minor below min or above max | Reject with clear reason |
| Missing one of multiple required capabilities | Reject, listing missing capability |
| Extra optional capability present | Accept, yet host uses it only when supported |
| Null descriptor, inverted range, or unknown capability | Reject/validation error |
| Provider constructor throws an error | Do not route requests; clean up partial resources |
| Binary-incompatible SDK artifact version | Linkage failure is isolated, not marked READY |
| Reload same provider name with different version | Renegotiate by artifact identity |
| Runtime loses permissions/network or JDK prerequisite | Fail health check or degrade per policy |

Tests should run against **actual published JAR artifacts** with the production module path/classloader setup. Do not rely solely on mock providers on the IDE classpath; mocks do not catch SPI descriptor issues, module resolution problems, or Java binary linkage failures.

## 12. Implementation checklist

- [ ] API contract clearly defines version semantics, breaking changes, and capability semantics.
- [ ] Separate required and optional capabilities per workload.
- [ ] Structured descriptor present, validating null/range/capability values.
- [ ] Inspect artifact metadata before instantiating providers when possible.
- [ ] Keep SPI handshake minimal and stable, with one shared API class identity.
- [ ] Fail-fast when major/range/capability is unmet; do not register rejected providers.
- [ ] Report clear reason codes and log sufficient diagnostic details.
- [ ] Do not invoke optional features before checking support.
- [ ] Renegotiate on reload, host upgrade, or workload change.
- [ ] Test the compatibility matrix using final JARs/module path.

**Conclusion:** being able to load a provider is only the discovery step. The host must **negotiate the contract and capabilities** according to explicit rules, reject plugins with incompatible API versions or capabilities early, and activate only verified providers. This is essential for dynamically extensible Java systems to maintain correctness when SDKs and plugins are released independently.

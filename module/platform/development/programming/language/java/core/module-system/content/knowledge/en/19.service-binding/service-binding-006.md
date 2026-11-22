# Reducing unnecessary modules when services are unused

## 1. Objectives

The Java Platform Module System (JPMS) supports Service Loader so that a module can use a service without depending directly on each module supplying an implementation. This mechanism is very flexible, but when packaging an application into a custom runtime image with **jlink**, automatically binding service providers can cause the image to contain more modules than the application needs.

This lesson focuses on keeping a runtime image lean when an application does not need service providers, or only needs selected providers.

Key points:

- **By default, jlink does not perform service binding** when creating an image.
- The **--bind-services** option enables service binding, bringing modules that provide services used by resolved modules into the image along with their dependencies.
- **--add-modules** specifies root modules. `jlink` still adds modules required via `requires` and their transitive dependencies.
- If only one specific provider is needed, you can add that provider module itself to the root modules instead of binding every provider found.
- You must verify `ServiceLoader` behavior after creating the image: a provider excluded from the image cannot be discovered from that image.

Do not confuse skipping service binding with removing all modules that are not directly used. Modules required via `requires` must still be present for the application to run.

## 2. How does service binding add extra modules?

A modular application can declare service usage in `module-info.java`:

~~~java
module com.acme.application {
    requires com.acme.codec.api;
    uses com.acme.codec.Codec;
}
~~~

The API module defines the service type:

~~~java
module com.acme.codec.api {
    exports com.acme.codec;
}
~~~

Another module provides an implementation:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.api;

    provides com.acme.codec.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

Another provider can supply the same service:

~~~java
module com.acme.codec.xml {
    requires com.acme.codec.api;

    provides com.acme.codec.Codec
        with com.acme.codec.xml.XmlCodec;
}
~~~

The application can discover providers with `ServiceLoader`:

~~~java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.name());
}
~~~

The application module declares **uses** to state that it uses the service type. The provider module declares **provides ... with ...** to register an implementation. This is a service-use relationship internal to the module system; it does not create a direct `requires` directive from the application to each provider.

If the application module only declares `requires com.acme.codec.api`, this normal dependency does not automatically pull all provider modules into the graph. A provider is added through one of the following ways:

1. Explicitly added to root modules, for example via `--add-modules`.
2. Added because another module requires it via `requires`.
3. Found and added during service binding.

### resolve and resolveAndBind

The Java API represents two styles of module graph resolution:

- **Configuration.resolve(...)** resolves root modules along with normal module dependencies.
- **Configuration.resolveAndBind(...)** performs resolution and adds provider modules arising from service-use dependences.

With `resolveAndBind`, the module system inspects resolved modules with service dependences and modules in parent configurations. Modules that provide implementations for used service types can be added to the graph. Newly added provider modules are also resolved; if they use other services, the process continues until no more new providers need to be added.

This is why service binding can grow the graph across multiple levels: a newly added provider module may use another service, which in turn pulls in more providers and those providers' dependencies.

## 3. Default behavior of jlink

**By default, jlink does not service-bind** when building a custom runtime image. It links the root modules and their normal dependencies. Provider modules are included only if they are explicitly added, required via `requires`, or included by a broader root selection.

Example:

~~~text
jlink
  --module-path <module-path>
  --add-modules com.acme.application
  --output image-minimal
~~~

This image contains:

- `com.acme.application` and modules declared directly or transitively via `requires`;
- provider modules added by other means;
- platform modules needed for the graph.

The image does not automatically add `com.acme.codec.json` and `com.acme.codec.xml` merely because `application` has a `uses com.acme.codec.Codec` directive.

This is the right choice when:

- The application does not call `ServiceLoader` for that service.
- The service is only an optional extension point and no provider needs to be deployed in the image.
- Providers are loaded from another source in the deployment architecture, rather than from modules linked into the image.
- You want per-provider control to reduce the runtime image size.

### What does --bind-services change?

When the option is enabled:

~~~text
jlink
  --module-path <module-path>
  --add-modules com.acme.application
  --output image-with-services
  --bind-services
~~~

`jlink` links provider modules found for services used by resolved modules, together with those providers' dependencies.

In the Codec example, if both providers are observable on the module path and provide `com.acme.codec.Codec`, service binding can put both `com.acme.codec.json` and `com.acme.codec.xml` into the image.

This is convenient when the application needs all available providers. However, if only one implementation is needed or the service is unused, this option can make the image larger than necessary.

**--bind-services is an explicit opt-in.** Do not add this option when the goal is only to link root modules and regular dependencies.

## 4. Selecting one provider instead of binding all

Suppose the application only needs `JsonCodec`. You can add that provider directly to the root modules:

~~~text
jlink
  --module-path <module-path>
  --add-modules com.acme.application,com.acme.codec.json
  --output image-json
~~~

Result:

- `com.acme.application` and its dependencies are linked.
- `com.acme.codec.json` is linked along with its dependencies.
- `com.acme.codec.xml` is not added merely because it also provides `Codec`.
- There is no automatic step binding all providers of used services.

This approach fits when a deployment selects a specific implementation per environment, such as JSON in production while XML is only used in another tool.

If the application genuinely needs multiple providers, list the needed provider modules:

~~~text
--add-modules com.acme.application,com.acme.codec.json,com.acme.codec.xml
~~~

There is no need to enable `--bind-services` if the provider list is already completely determined. If a provider's dependencies use other services and the application also needs providers for those services, add the corresponding providers or consider enabling service binding after evaluating how many modules get added.

## 5. Avoiding overly broad root modules

Even without `--bind-services`, you can still accidentally pull many modules into the image by choosing overly broad root modules.

Example:

~~~text
--add-modules ALL-MODULE-PATH
~~~

`ALL-MODULE-PATH` asks to add every observable module on the module path as a root. If the module path contains many providers, they can be linked because they have become root modules, even while service binding is off.

To create a small image:

1. Select the application module as the main root.
2. Let `requires` describe truly necessary module dependencies.
3. Add only the providers that are needed.
4. Do not add the entire module path just to avoid missing one provider.
5. Verify the result using the image's module list.

The **--limit-modules** option can restrict the observable module set for resolution. This set consists of the closure of the specified modules, the main module if any, and modules specified via `--add-modules`. This is an advanced control tool; if restricted too tightly, `jlink` may fail to resolve dependencies or providers the application needs. Only use it after understanding the module graph and testing the image after building.

## 6. Finding providers before deciding to include them in the image

`jlink` has the **--suggest-providers** option to list modules supplying implementations for a specified service type.

Example:

~~~text
jlink
  --module-path <module-path>
  --suggest-providers com.acme.codec.Codec
~~~

The output might show:

~~~text
Suggested providers:
  com.acme.codec.json provides com.acme.codec.Codec
  com.acme.codec.xml provides com.acme.codec.Codec
~~~

From this list, you can pick the needed modules to add to `--add-modules`.

This is a useful step when the module path contains many providers or when a service is provided by a JDK module. Do not guess provider names or add every provider before knowing which implementations the application actually needs.

## 7. Practical example with a JDK charset provider

One example in the JDK is the **java.nio.charset.spi.CharsetProvider** service. The `java.base` module uses this service; the `jdk.charsets` module supplies several additional charsets.

When running on a full JDK, normal module resolution can perform service binding and find the `jdk.charsets` provider. Consequently, many charsets are available in a full JDK environment.

When creating a custom runtime image with `jlink`:

~~~text
jlink
  --add-modules java.base
  --output image-base-only
~~~

`jlink` does not automatically add every provider merely because `java.base` declares using the service. If the application needs the additional charsets in `jdk.charsets`, add that module explicitly:

~~~text
jlink
  --add-modules java.base,jdk.charsets
  --output image-with-charsets
~~~

Or enable `--bind-services` if you want `jlink` to automatically add matching providers for services used by resolved modules:

~~~text
jlink
  --add-modules java.base
  --output image-bound
  --bind-services
~~~

This example illustrates the difference between a full JDK and a custom runtime image. When building an image, you are responsible for choosing the modules and providers your application needs.

## 8. What happens if a provider is not in the image?

If the application calls:

~~~java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);
~~~

but there is no matching provider in the runtime image or module layer observable by `ServiceLoader`, the lookup does not automatically load missing providers from the build-time module path. `ServiceLoader` may return an empty result.

Example:

~~~java
Optional<Codec> selected = ServiceLoader.load(Codec.class)
        .findFirst();

if (selected.isEmpty()) {
    throw new IllegalStateException(
            "No Codec provider is available in this runtime image");
}
~~~

If the service is mandatory, the application should handle the missing-provider case explicitly. If the service is only an optional feature, it can use a default implementation or disable the related feature by design.

For named modules, the module calling `ServiceLoader` must declare `uses` for the service type. The provider module must declare `provides` in its module descriptor. Check both sides when a provider is not found.

Do not exclude a provider from the image solely based on the application not referencing the provider class directly. `ServiceLoader` is designed to find implementations through the service type, so the provider class name may never appear in application code.

## 9. Distinguishing reasons a module appears in an image

When a module appears in a custom runtime image, identify the path by which it was brought in:

| Inclusion source | Example | How to control |
|---|---|---|
| Root module | `--add-modules com.acme.application` | Only select roots that are genuinely needed |
| Normal dependency | `application requires com.acme.api` | Review `requires` and the dependency graph |
| Explicitly selected provider | `--add-modules com.acme.codec.json` | Add only needed providers |
| Service binding | `--bind-services` | Omit the option if automatic provider binding is not needed |
| Overly broad root | `--add-modules ALL-MODULE-PATH` | Narrow the root list |

Turning off service binding only prevents adding modules due to service-use dependences. It does not remove modules added by `requires`, root modules, or another dependency.

A provider module can still appear even when the application does not use the service if that module is required directly or transitively via `requires`, or specified in `--add-modules`. To reduce further, you must review actual dependencies and module architecture; a dependency cannot be safely removed simply by disabling service binding.

## 10. Process for creating a lean and verifiable image

### Step 1 — Identify root modules

Select the application's entry module. With `jlink`, `--add-modules` is where root modules are specified.

~~~text
--add-modules com.acme.application
~~~

### Step 2 — Inspect service usage

Find `uses` directives in `module-info.java` and code snippets calling `ServiceLoader`. Check dependencies as well, because library modules can also declare `uses`.

If the application does not use a service, remove no-longer-needed `uses` directives and redundant `ServiceLoader` code. If a service is an optional extension point, document which providers are required in each deployment environment.

### Step 3 — Decide the provider strategy

- Not using services: keep the default, do not enable `--bind-services`.
- Using only a few providers: add the exact provider modules to `--add-modules`.
- Needing every matching provider on the module path: consider `--bind-services`.

### Step 4 — Build the image

~~~text
jlink
  --module-path <module-path>
  --add-modules com.acme.application
  --output image
~~~

Add provider modules or `--bind-services` according to the decision in the previous step.

### Step 5 — Verify actual modules

Run `java` inside the newly created image:

~~~text
image/bin/java --list-modules
~~~

On Windows:

~~~text
image\bin\java.exe --list-modules
~~~

Compare the list against the expected root modules, `requires` dependencies, and provider modules. Do not rely solely on directory size to conclude an image is optimized.

### Step 6 — Test service functionality

Run integration tests or smoke tests on the runtime image itself:

- `ServiceLoader` finds mandatory providers.
- Selected providers match the deployment configuration.
- Optional features handle the zero-provider case.
- No reliance on the development machine's full JDK.

Testing on a full JDK can mask missing-provider errors in a custom image. Run tests using the executable inside the output image.

## 11. Common misconceptions

### Thinking `uses` automatically pulls providers into a jlink image

The `uses` directive describes a service dependence. `jlink` does not perform service binding by default, so providers only appear if added via roots, dependencies, or another option.

### Thinking omitting `--bind-services` excludes all providers

Incorrect. Providers added via `--add-modules` or `requires` are still linked. Disabling service binding only prevents the step that automatically adds providers for service-use dependences.

### Thinking `--bind-services` only adds providers called by the main application

Not necessarily. Any resolved module, including dependencies, can declare service usage. Providers for those services can also be added; newly added providers can create further service dependences.

### Thinking a provider missing from the image can still be found from the module path at runtime

The module path used at runtime must actually contain the provider and the provider must be observable in the appropriate configuration. A module path existing only on the build machine does not automatically become the runtime image's module path.

### Thinking `ALL-MODULE-PATH` is equivalent to `bind-services`

They are two different mechanisms. `ALL-MODULE-PATH` adds every observable module on the module path as a root; `--bind-services` adds providers for service-use dependences of already resolved modules. Both can enlarge the image, but for different reasons.

### Thinking a module not directly imported by the application is unnecessary

A module may be needed via transitive `requires`, reflection, service providers, or other runtime features. Verify how a module is used before removing it.

## 12. Checklist for deciding whether to enable service binding

- Does the application call `ServiceLoader` or use service-based extension points?
- Which dependency modules declare `uses`?
- Which services are mandatory and which are optional?
- Which providers are genuinely needed in the image?
- Are providers already added by `requires` or `--add-modules` before considering service binding?
- Is `ALL-MODULE-PATH` being used, causing every module on the module path to become a root?
- If not using `--bind-services`, have the necessary providers been added explicitly?
- Has the built image been checked with `--list-modules`?
- Do integration tests run against the output runtime image?
- When a provider is missing, does the application report a clear error or handle fallback appropriately?

**Key takeaway:** To keep an image small when service providers are not needed, leave `jlink` in its default mode, pick exact root modules, and add only the needed providers. Enable `--bind-services` when you genuinely want the module system to automatically discover and link providers for used services. Always verify the module list and test using the generated image itself.

## References

- Oracle Java SE 21 — jlink Command, `--add-modules`, `--bind-services`, `--limit-modules`, and `--suggest-providers` options: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html
- Oracle Java SE 21 API — Configuration.resolve and Configuration.resolveAndBind: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html
- Dev.java — Creating Runtime and Application Images with JLink, Including Services section: https://dev.java/learn/jlink/
- Oracle Java SE 21 API — ServiceLoader: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html

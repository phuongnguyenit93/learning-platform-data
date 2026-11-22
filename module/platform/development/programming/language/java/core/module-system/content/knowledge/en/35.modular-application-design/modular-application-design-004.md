# Placing Service Interfaces and Provider Implementations

## 1. Objective

When designing modular Java applications, a service often has multiple different implementations: saving to a file or to a database, sending email via SMTP or an API, processing payments through multiple gateways, or reading data from multiple formats. If a consuming module depends directly on an implementation class, changing providers can force modifications to the consumer's dependencies and module descriptor.

The Java Platform Module System (JPMS) supports separating three roles:

1. **Service API module** defines the contract understood by both consumers and providers.
2. **Consumer module** uses the contract and declares service usage with `uses`.
3. **Provider module** implements the contract and registers the implementation with `provides ... with ...`.

The consumer depends on the service API. The provider also depends on the service API. The consumer does not need to declare `requires` on any specific provider. At runtime, the appropriate implementation can be discovered via `ServiceLoader` once the provider module has been included in the module layer.

This organization reduces coupling, allows providers to be swapped or added via deployment configuration, and keeps implementation details inside the provider module.

## 2. Dividing responsibilities among modules

Suppose an application needs a service to send notifications:

~~~text
com.acme.notification.api
    com.acme.notification.spi
        NotificationSender
        Notification
        DeliveryResult

com.acme.notification.consumer
    com.acme.notification.app
        ReminderService

com.acme.notification.email
    com.acme.notification.email.internal
        SmtpNotificationSender

com.acme.notification.sms
    com.acme.notification.sms.internal
        SmsNotificationSender
~~~

Dependency relationships:

~~~text
                  +-------------------------------+
                  | com.acme.notification.api    |
                  | NotificationSender            |
                  | Notification / DeliveryResult |
                  +---------------+---------------+
                                  ^
                    +-------------+-------------+
                    |                           |
          +---------+----------+      +---------+---------+
          | consumer module    |      | provider modules  |
          | uses Notification  |      | provides ...      |
          +--------------------+      +-------------------+
~~~

Both the consumer and the provider know the service contract. The consumer does not need to know which package contains the SMTP or SMS class.

### Service API module

The API module contains the types needed to invoke the service:

- Service interfaces or abstract service types.
- Request/response types and exceptions belonging to the contract.
- Enums or value types exchanged between consumer and provider.
- Annotations or capability types belonging to the contract if genuinely required.

The API module should be small and stable. Do not put SMTP implementations, JDBC, HTTP clients, frameworks, or environment configurations into the API module just so the consumer can call the interface.

### Consumer module

The consumer contains the business logic that needs to use the service. It:

- Declares `requires` on the service API module.
- Declares `uses` for the service type.
- Uses `ServiceLoader` to discover providers.
- Selects a provider according to application rules if multiple implementations exist.
- Handles cases where no provider is present or provider initialization fails.

The consumer does not need to import or directly instantiate implementation classes.

### Provider module

The provider contains a concrete implementation and its own dependencies. It:

- Declares `requires` on the service API module.
- Declares `provides` for the service type.
- Places the implementation in an internal package.
- Does not export the implementation package if other modules do not need direct access.
- Manages the provider's own configuration, connections, and resources.

A provider can depend on an SMTP library, a payment SDK, or a database driver without the consumer needing to know.

## 3. Defining the service contract in the API module

Module descriptor of the API:

~~~java
module com.acme.notification.api {
    exports com.acme.notification.spi;
}
~~~

Service interface:

~~~java
package com.acme.notification.spi;

public interface NotificationSender {
    String providerId();

    DeliveryResult send(Notification notification);
}
~~~

Types exchanged through the interface also belong to the API module:

~~~java
package com.acme.notification.spi;

public record Notification(
        String recipient,
        String subject,
        String body) {
}
~~~

~~~java
package com.acme.notification.spi;

public record DeliveryResult(
        String messageId,
        boolean accepted) {
}
~~~

Because these types reside in an exported package, consumers and providers can reference them when declaring a dependency on the API module.

### Designing a stable contract

The service interface is the boundary between both sides. Design the contract around business concepts instead of exposing details of one provider:

- Use conceptual names like `NotificationSender` or `PaymentGateway` rather than `SmtpSender` if multiple provider types exist.
- Put necessary data into meaningful request/response types.
- Do not return classes belonging to a provider's private library.
- Do not require consumers to pass internal implementation connection or configuration objects.
- Clearly define possible errors, synchronous/asynchronous behavior, and timeouts if required by the service.
- Maintain compatibility when adding fields or extending the contract.

If a consumer must import an SMTP SDK class just to invoke `NotificationSender`, the abstraction is leaking implementation details.

### Do not place implementations in the API module

The API module should not contain:

~~~java
public final class SmtpNotificationSender
        implements NotificationSender {
    // SMTP implementation
}
~~~

If this class is placed in the API module, consumers may get pulled into SMTP dependencies and the service boundary becomes blurred. Implementations belong in separate provider modules.

## 4. Consumer declares `uses`

Module descriptor of the consumer:

~~~java
module com.acme.reminder {
    requires com.acme.notification.api;

    uses com.acme.notification.spi.NotificationSender;
}
~~~

The two directives serve different purposes:

- `requires` allows the consumer to read the service API module and reference types in exported packages.
- `uses` declares that the consumer uses the service type so the module system and `ServiceLoader` are aware of the consumer's service dependency.

Consumer code:

~~~java
package com.acme.reminder.app;

import com.acme.notification.spi.Notification;
import com.acme.notification.spi.NotificationSender;
import java.util.ServiceLoader;

public final class ReminderService {

    public void sendReminder(String email, String body) {
        ServiceLoader<NotificationSender> loader =
                ServiceLoader.load(NotificationSender.class);

        NotificationSender sender = loader.findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "No NotificationSender provider is available"));

        sender.send(new Notification(
                email,
                "Reminder",
                body));
    }
}
~~~

For code running in a named module, the module containing the code that invokes `ServiceLoader` must declare `uses` for the service type. If the declaration is missing, `ServiceLoader` may throw `ServiceConfigurationError` when attempting to locate providers.

When running solely on the classpath in the unnamed module, the named-module `uses` declaration rule does not apply in the same way. However, keep the module design explicit when the application uses JPMS.

### Do not `requires` a specific provider in the consumer

The consumer should not write:

~~~java
module com.acme.reminder {
    requires com.acme.notification.api;
    requires com.acme.notification.email;
}
~~~

If the consumer declares `requires` on a specific provider, it becomes coupled to that implementation module. Switching from email to SMS would force changes to the consumer's module descriptor and dependency graph.

A service-based design typically only needs:

~~~java
module com.acme.reminder {
    requires com.acme.notification.api;
    uses com.acme.notification.spi.NotificationSender;
}
~~~

Providers are supplied in the runtime configuration or module layer according to deployment needs.

## 5. Provider module registers implementation with `provides`

The email module can implement the service:

~~~java
module com.acme.notification.email {
    requires com.acme.notification.api;

    provides com.acme.notification.spi.NotificationSender
        with com.acme.notification.email.internal.SmtpNotificationSender;
}
~~~

Implementation:

~~~java
package com.acme.notification.email.internal;

import com.acme.notification.spi.DeliveryResult;
import com.acme.notification.spi.Notification;
import com.acme.notification.spi.NotificationSender;

public final class SmtpNotificationSender
        implements NotificationSender {

    public SmtpNotificationSender() {
    }

    @Override
    public String providerId() {
        return "smtp";
    }

    @Override
    public DeliveryResult send(Notification notification) {
        // Send notification via SMTP.
        return new DeliveryResult("smtp-message-id", true);
    }
}
~~~

For a constructor-based provider class, the implementation must be `public` and have a `public` no-argument constructor so `ServiceLoader` can instantiate it.

The implementation package does not need to be exported simply because it is declared in `provides`. `ServiceLoader` can instantiate the provider based on the module descriptor. Consumers only need visibility to the service type in the API module.

This keeps the implementation package encapsulated:

~~~java
module com.acme.notification.email {
    requires com.acme.notification.api;

    provides com.acme.notification.spi.NotificationSender
        with com.acme.notification.email.internal.SmtpNotificationSender;
}
~~~

There is no need to add:

~~~java
exports com.acme.notification.email.internal;
~~~

Only export the provider package if a separate API genuinely needs direct access to that implementation.

### Provider method instead of an implementation constructor

A named module can also declare a provider class with a `public static` method named `provider` returning the service type:

~~~java
package com.acme.notification.email.internal;

import com.acme.notification.spi.NotificationSender;

public final class SmtpSenderProvider {

    private SmtpSenderProvider() {
    }

    public static NotificationSender provider() {
        return new SmtpNotificationSender(loadConfiguration());
    }

    private static SmtpConfiguration loadConfiguration() {
        return new SmtpConfiguration();
    }
}
~~~

The module descriptor then names the provider class:

~~~java
provides com.acme.notification.spi.NotificationSender
    with com.acme.notification.email.internal.SmtpSenderProvider;
~~~

A provider method is useful when the implementation requires initialization via a factory, configuration, or internal dependencies. The provider class does not need to implement the service directly if it provides a valid method matching the `ServiceLoader` provider method contract.

Whether using a constructor or a provider method, consumers still receive the service type exposed in the API module.

## 6. Multiple providers can implement the same service

An SMS module can implement the same interface:

~~~java
module com.acme.notification.sms {
    requires com.acme.notification.api;

    provides com.acme.notification.spi.NotificationSender
        with com.acme.notification.sms.internal.SmsNotificationSender;
}
~~~

When both the email and SMS providers are included in the same module layer, `ServiceLoader` can discover multiple implementations.

Consumer:

~~~java
ServiceLoader<NotificationSender> loader =
        ServiceLoader.load(NotificationSender.class);

for (NotificationSender sender : loader) {
    System.out.println(sender.providerId());
}
~~~

Do not rely on the order in which providers are returned to represent business priority. If a provider must be chosen, define an explicit rule:

- By deployment configuration.
- By notification type or recipient.
- By capabilities advertised by the provider.
- By a fallback policy when the primary provider is unavailable.
- By tenant or deployment region if required by the business domain.

Example selecting by configuration:

~~~java
String selectedProviderId = configuration.notificationProvider();

NotificationSender sender = ServiceLoader
        .load(NotificationSender.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(candidate ->
                candidate.providerId().equals(selectedProviderId))
        .findFirst()
        .orElseThrow(() -> new IllegalStateException(
                "Configured notification provider is unavailable"));
~~~

If the system requires exactly one provider, verify the provider count rather than implicitly picking the first one. If multiple providers are valid, design the API so the application explicitly decides which provider is used.

## 7. Where does `ServiceLoader` find providers?

`ServiceLoader` does not automatically load every JAR on disk. A provider must be present in the appropriate search environment and discovered by the module system or class loader.

With named modules:

- The consumer declares `uses`.
- The provider module declares `provides`.
- The provider module must be resolved into the module layer that `ServiceLoader` is searching.
- The provider module must be able to read the service API module and the service type must be compatible.

For applications running on the module path, simply placing a provider JAR on the module path does not guarantee the provider is already in the module graph. Ensure the provider module is included in the configuration/layer—for instance, by adding the provider module to the root modules or using an appropriate service binding mechanism.

Example of running the application and explicitly selecting a provider:

~~~text
java
  --module-path mods
  --add-modules com.acme.notification.email
  --module com.acme.reminder/com.acme.reminder.app.Main
~~~

In larger applications, the list of root modules and layer creation should be managed by build/deployment configuration. When building a custom runtime image with `jlink`, provider modules can be explicitly added with `--add-modules` or linked via `--bind-services` for services used by resolved modules.

### Finding providers in a specific `ModuleLayer`

If an application creates a dedicated module layer to load plugins, it can look up providers in that layer:

~~~java
ServiceLoader<NotificationSender> loader =
        ServiceLoader.load(pluginLayer, NotificationSender.class);
~~~

The overload accepting a `ModuleLayer` scopes provider lookup to the selected layer and its parent layers according to the API contract.

This is useful when an application has multiple plugin groups or multiple independent provider configurations. Ensure the service API module is shared appropriately between the consumer and the layer containing the provider.

### Providers on the classpath

In traditional classpath packaging, providers are typically registered via a file:

~~~text
META-INF/services/com.acme.notification.spi.NotificationSender
~~~

The file contains the fully qualified name of each provider class, one per line:

~~~text
com.acme.notification.email.internal.SmtpNotificationSender
~~~

This registration mechanism belongs to classpath/service configuration. For named modules, declare providers using `provides ... with ...` in `module-info.java`. Do not confuse the two registration mechanisms or assume a provider class declared one way will automatically be found in every kind of module layer.

## 8. Designing the service API and provider implementation

### Keep the service contract independent

The service API should contain the types needed by both consumers and providers. Avoid letting the interface depend on provider modules:

~~~text
notification.api
    NotificationSender
    Notification
    DeliveryResult

notification.email
    SmtpNotificationSender
    SmtpConfiguration
    SmtpClient

notification.sms
    SmsNotificationSender
    SmsConfiguration
    SmsClient
~~~

Do not let `NotificationSender` return `SmtpMessage` or accept `SmtpSession`. If the contract needs to represent a delivery result, define `DeliveryResult` in the API module.

### Keep provider dependencies on the provider side

The email provider may need an SMTP client library; the SMS provider may need its own SDK. Only the provider module declares those dependencies.

~~~java
module com.acme.notification.email {
    requires com.acme.notification.api;
    requires com.acme.smtp.client;

    provides com.acme.notification.spi.NotificationSender
        with com.acme.notification.email.internal.SmtpNotificationSender;
}
~~~

The consumer does not need to read `com.acme.smtp.client` and does not need to know which library the implementation uses.

### Do not turn the service API into a giant module

Do not lump every interface in the entire system into one shared module just because all modules might depend on it. An API module should reflect meaningful contract boundaries and an appropriate versioning lifecycle.

If services are unrelated or change at different cadences, consider splitting API modules. Avoid creating an overly broad dependency graph where a minor contract change affects the entire application.

### Managing provider lifecycle and resources

`ServiceLoader` instantiates providers when the consumer iterates or retrieves an instance. A provider may open connection pools, clients, or threads. Decide clearly:

- Is a provider instance long-lived or created per call?
- Who closes resources when the application shuts down?
- Is the provider thread-safe?
- Is configuration read at initialization time or per request?
- How are provider initialization failures reported and handled?

`ServiceLoader` is not a full dependency injection container and does not automatically manage the full lifecycle of resources opened by a provider. If a provider requires complex lifecycle management, design an explicit initialization/shutdown contract or integrate with an application container.

## 9. Common mistakes

### Consumer directly requires a provider

If the consumer declares `requires com.acme.notification.email`, the consumer becomes tied to a specific implementation. Swapping providers may force descriptor and dependency edits.

Fix: the consumer `requires` the service API and declares `uses`. The provider module `requires` the API and declares `provides`.

### Forgetting to export the service API package

Consumers and providers cannot reference the service interface if the package containing it is not properly exported.

Fix: export the contract package from the API module:

~~~java
module com.acme.notification.api {
    exports com.acme.notification.spi;
}
~~~

### Forgetting `uses` in the consumer module

A named module invokes `ServiceLoader`, but its module descriptor does not declare `uses` for the service type.

Fix: add `uses` for the corresponding service interface in the consumer's `module-info.java`.

### Forgetting `provides` in the provider module

The implementation class is present on the module path, but the module descriptor does not register the provider.

Fix: add `provides ... with ...` and verify the provider type, constructor, or provider method.

### Provider is not in the module layer

The provider module is on the module path, but it was not resolved into the layer being searched.

Fix: check root modules, module finders, configuration resolution, parent layers, and service binding options. You can add the provider module explicitly or use `resolveAndBind` when binding service providers.

### Unnecessarily exporting the implementation package

Many projects export the provider package just so `ServiceLoader` can instantiate it. This exposes the implementation package as API.

Fix: keep the implementation package unexported; register the provider in the module descriptor.

### Picking the first provider by discovery order

Provider discovery order is not a stable business priority policy.

Fix: select by `providerId`/capability/configuration, or require an exact provider count and reject ambiguous configurations.

### Service contract contains provider-specific types

Consumers end up having to depend on an implementation's library or class to use the API.

Fix: move the required exchange types into the service API module and keep private types inside the provider module.

### Assuming `ServiceLoader` isolates untrusted providers

Providers are loaded and executed in the same process as the application. `ServiceLoader` does not create a sandbox.

Fix: only load trusted providers. If untrusted plugins must be run, consider a separate process/container and a controlled IPC protocol.

## 10. Complete three-module example

### API module

`module-info.java`:

~~~java
module com.acme.codec.api {
    exports com.acme.codec;
}
~~~

Service type:

~~~java
package com.acme.codec;

public interface Codec {
    String format();
    byte[] encode(String input);
}
~~~

### Consumer module

`module-info.java`:

~~~java
module com.acme.document {
    requires com.acme.codec.api;

    uses com.acme.codec.Codec;
}
~~~

Consumer code:

~~~java
package com.acme.document;

import com.acme.codec.Codec;
import java.util.ServiceLoader;

public final class DocumentEncoder {

    public byte[] encode(String format, String content) {
        Codec codec = ServiceLoader.load(Codec.class)
                .stream()
                .map(ServiceLoader.Provider::get)
                .filter(candidate ->
                        candidate.format().equalsIgnoreCase(format))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unsupported format: " + format));

        return codec.encode(content);
    }
}
~~~

### Provider module

`module-info.java`:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.api;

    provides com.acme.codec.Codec
        with com.acme.codec.json.internal.JsonCodec;
}
~~~

Implementation:

~~~java
package com.acme.codec.json.internal;

import com.acme.codec.Codec;

public final class JsonCodec implements Codec {

    public JsonCodec() {
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public byte[] encode(String input) {
        return input.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

The consumer module does not need `requires com.acme.codec.json`. The provider module does not need to export `com.acme.codec.json.internal`. Both depend on `com.acme.codec.api`.

### Running with a selected provider

A simple deployment approach is adding the provider to the root modules:

~~~text
java
  --module-path mods
  --add-modules com.acme.codec.json
  --module com.acme.document/com.acme.document.Main
~~~

To add another provider, include that provider module in the module graph. The consumer continues using the same contract.

## 11. Testing the service API and providers

The following test categories should be covered:

### Contract tests

- The provider accepts valid request types and returns valid response types.
- The provider fulfills the interface semantics correctly.
- Error mapping, timeouts, and validation conform to the contract.
- No internal provider types leak through the API.

### Consumer tests

- The consumer works when a valid provider is present.
- The consumer handles the absence of any provider.
- The consumer selects the correct provider based on configuration/capabilities.
- The consumer does not depend on the order returned by `ServiceLoader`.
- The consumer handles `ServiceConfigurationError` or initialization failures according to an appropriate policy.

### Module integration tests

- The API module exports the right packages.
- The consumer module has `requires` and `uses`.
- The provider module has `requires` and `provides`.
- An unexported provider implementation package is still discovered by `ServiceLoader`.
- The provider module is actually present in the module layer/runtime image.
- Run tests using a module path or runtime image close to the deployment environment.

### Multi-provider tests

- When two providers are present, is selection deterministic and reproducible?
- When a configured provider does not exist, is the error clear?
- When the primary provider fails, is fallback permitted by policy?
- Are duplicate provider IDs or conflicting configurations checked?

## 12. Design checklist

- Does the service contract live in an independent API module?
- Does the API module contain only types needed by consumers and providers?
- Is the package containing the service interface exported?
- Does the consumer module `requires` the API module and declare `uses`?
- Does the provider module `requires` the API module and declare `provides`?
- Does the provider implementation have a `public` no-argument constructor or a valid provider method?
- Can the implementation package remain unexported?
- Does the consumer avoid `requires` directly on a provider module?
- Is the provider module actually resolved into the target module layer?
- If multiple providers exist, is the selection policy clear?
- Does the contract avoid types tied to a provider's private library?
- Are provider lifecycle, resources, thread safety, and initialization errors handled?
- Are missing-provider, multi-provider, and failing-provider cases tested?
- Is the provider trusted code running in the same process?

**Key takeaway:** Place the service interface in an exported API module; the consumer declares `requires` + `uses`; the provider declares `requires` + `provides`. The consumer depends on the contract, while the provider owns the implementation and its dependencies. `ServiceLoader` connects the two sides at runtime once the provider module has been included in the appropriate module layer.

## References

- Oracle Java SE 21 API — ServiceLoader: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html
- Java Language Specification, Java SE 21 — Service Providers and Module Declarations: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
- Oracle Java SE 21 — The java Command, module selection and module path: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle Java SE 21 API — Configuration.resolveAndBind: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html
- OpenJDK JEP 261 — Module System: https://openjdk.org/jeps/261

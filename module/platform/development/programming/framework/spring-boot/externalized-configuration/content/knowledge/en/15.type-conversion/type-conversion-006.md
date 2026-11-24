# Converting URI, URL, InetAddress, and Resource in Spring Boot Externalized Configuration

## 1. Lesson Objectives

Application configuration frequently contains HTTP addresses, hostnames, IP addresses, or paths to certificates and data files. In `application.properties` or `application.yml`, these values are initially represented as strings. Spring Boot can perform **type conversion during binding** so Java code receives an object with explicit semantics instead of always taking a `String`.

Common types include:

- `java.net.URI`: represents a resource identifier per URI syntax, which may be relative or absolute.
- `java.net.URL`: represents a locator with a Java-supported protocol; suitable when a legacy API or library requires `URL`.
- `java.net.InetAddress`: represents an IP network address, which may be created from a numeric address or a hostname requiring resolution.
- `org.springframework.core.io.Resource`: Spring's abstraction for resource content, such as a classpath file, a filesystem file, or a source supported by `ResourceLoader`.

Example group of properties:

~~~properties
service.api.base-uri=https://api.example.test/v1
service.api.legacy-url=https://legacy.example.test/api
service.network.bind-address=127.0.0.1
service.tls.certificate=classpath:certs/service.pem
~~~

The Java object can declare fields with matching semantics:

~~~java
import java.net.InetAddress;
import java.net.URI;
import java.net.URL;
import org.springframework.core.io.Resource;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        Api api,
        Network network,
        Tls tls
) {
    public record Api(URI baseUri, URL legacyUrl) {}
    public record Network(InetAddress bindAddress) {}
    public record Tls(Resource certificate) {}
}
~~~

Once configuration binds successfully, code can call `baseUri().getHost()`, `bindAddress().getHostAddress()`, or `certificate().getInputStream()`. Yet **successful binding does not prove the endpoint is reachable, DNS is valid, or the file is readable**. Those checks serve separate purposes.

This lesson focuses on choosing the right type, examples across properties/YAML/environment variables, the conversion flow, common mistakes, and safe startup checks.

## 2. Big Picture of the Conversion Process

Spring Boot builds an `Environment` from externalized configuration sources. `@ConfigurationProperties` uses the binder to match prioritized values and convert them to declared types.

~~~text
application.properties / application.yml
             |
     Config Data locations
    profiles / import / override
             |
             v
          Environment
       + PropertySources
             |
             v
       Spring Boot Binder
      (ConversionService)
             |
      +------+------+------+------+
      |      |      |      |      |
     URI    URL  InetAddress Resource
             |
             v
      Configuration bean
             |
             v
          Service
~~~

Example:

~~~properties
remote.endpoint=https://orders.example.test/api
remote.connect-address=192.0.2.10
remote.public-key=file:/etc/orders/public.pem
~~~

Target:

~~~java
import java.net.InetAddress;
import java.net.URI;
import org.springframework.core.io.Resource;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "remote")
public record RemoteProperties(
        URI endpoint,
        InetAddress connectAddress,
        Resource publicKey
) {}
~~~

Spring Boot converts each value individually. If a value cannot be converted to its target type, creating the configuration properties bean can fail with a binding error identifying the relevant property path.

### 2.1. Three Steps That Should Not Be Lumped Together

1. **Parsing sources**: reading YAML or properties and producing key/value pairs.
2. **Type conversion**: turning a key's value into `URI`, `URL`, `InetAddress`, or `Resource` during binding.
3. **Using the resource**: sending an HTTP request, opening a file, reading a stream, or connecting to a hostname.

A valid `URI` at step 2 can still point to a nonexistent host at step 3. A `Resource` created at step 2 may have no corresponding file when `getInputStream()` is called. Recognizing this boundary is essential for diagnosing failures.

## 3. `URI`: Resource Identifier with Clear Syntax

`java.net.URI` represents a resource identifier following URI syntax rules. It can contain:

- `scheme`, such as `https`, `file`, or `mailto`.
- `authority`, typically containing hostname and port for network URLs.
- `path`, such as `/v1/orders`.
- `query`, such as `?limit=20`.
- `fragment`, such as `#overview`.

Absolute URI example:

~~~text
https://api.example.test:8443/v1/orders?limit=20
~~~

Relative URI example:

~~~text
/v1/orders
~~~

**Both can be valid URIs.** If the application requires an absolute HTTP endpoint, declaring a `URI` field alone does not guarantee a proper scheme/host; additional validation is needed.

### 3.1. Binding URI from Properties

~~~properties
app.catalog.endpoint=https://catalog.example.test/v1/items
~~~

Java record:

~~~java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog")
public record CatalogProperties(URI endpoint) {
}
~~~

After successful binding, you can access:

~~~java
URI uri = properties.endpoint();

String scheme = uri.getScheme();   // https
String host = uri.getHost();       // catalog.example.test
String path = uri.getPath();       // /v1/items
~~~

Using it with a Java HTTP client:

~~~java
import java.net.http.HttpClient;
import java.net.http.HttpRequest;

HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(
        properties.endpoint()
).GET().build();
~~~

The snippet above only builds the request; it does not send network traffic yet because `send` or `sendAsync` has not been called.

### 3.2. Binding URI from YAML

~~~yaml
app:
  catalog:
    endpoint: "https://catalog.example.test:8443/v1/items?limit=10"
~~~

Quotes make it explicit that the value is a scalar string, especially when multiple separator characters appear. The YAML parser does not construct a `URI` directly; the binder converts the string into a `URI`.

### 3.3. Relative vs. Absolute URIs

~~~properties
app.catalog.endpoint=/v1/items
~~~

This value can bind into a relative `URI`. If code needs to call a specific HTTP host, it does not satisfy the requirement even though it parses cleanly.

You can validate:

~~~java
URI uri = properties.endpoint();

if (!uri.isAbsolute() || uri.getHost() == null) {
    throw new IllegalArgumentException(
        "app.catalog.endpoint must be an absolute network URI");
}
~~~

This check is only a starting point; verify scheme, host, port, or allowlists as needed. `URI.isAbsolute()` only checks for a scheme, so `mailto:user@example.test` is an absolute URI yet not an HTTP endpoint.

### 3.4. URI and Encoding

In a URI, literal spaces and many special characters must be properly encoded. For example:

~~~text
https://example.test/search?q=hello%20world
~~~

differs from a malformed value containing a raw space in a disallowed position. `String -> URI` conversion does not automatically fix unencoded URL strings.

If the application builds URIs from dynamic pieces such as path segments or query parameters, use an appropriate builder like `UriComponentsBuilder` instead of raw string concatenation without encoding.

~~~java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

URI uri = UriComponentsBuilder
        .fromUri(properties.endpoint())
        .pathSegment("details")
        .queryParam("page", 1)
        .build()
        .toUri();
~~~

This example requires the Spring Web module containing `UriComponentsBuilder`. For applications without Spring Web, use the `URI` API or an equivalent URL builder library.

### 3.5. Why Is URI Usually the Default Choice for Endpoints?

`URI` represents an identifier; constructing it requires no DNS lookup or network connection. Modern Java HTTP APIs such as `HttpRequest.newBuilder(URI)` also accept `URI`. Therefore, for an endpoint configuration passed across multiple service layers, `URI` is generally cleaner and more convenient than `URL`.

## 4. `URL`: Locator for Protocol-Based APIs

`java.net.URL` is a long-standing Java type, often required by APIs expecting a network locator. Example:

~~~properties
legacy.partner.url=https://legacy.example.test/api
~~~

~~~java
import java.net.URL;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "legacy.partner")
public record LegacyPartnerProperties(URL url) {
}
~~~

When the binder supports the corresponding conversion, the `url` property becomes a `URL`.

### 4.1. Differences Between URI and URL

| Criterion | `URI` | `URL` |
| --- | --- | --- |
| Primary meaning | Resource identifier | Protocol-based resource locator |
| Can be relative | Yes | Relative URL paths need a suitable context/base URL |
| Syntax validation | Follows URI syntax rules | Follows protocols/handlers known to Java |
| Does creating one send requests? | No | No |
| Use with modern Java HTTP Client | Fits directly | Often needs conversion to URI |
| When to use in config | Endpoints, identifiers, and general URIs | When a library API requires `URL` |

**Do not confuse "a `URL` object was created" with "the URL is reachable".** HTTP connectivity, TLS certificates, DNS, proxies, and response times are only tested when the software actually performs network access.

### 4.2. URL Usage Example

~~~java
import java.net.URL;

URL url = properties.url();

String protocol = url.getProtocol();
String host = url.getHost();
int port = url.getPort();
~~~

A Java API might require a `URL` input. For newer APIs accepting `URI`, consider keeping the configuration field as `URI` and converting only when necessary.

~~~java
URI endpoint = properties.endpoint();

URL url = endpoint.toURL();
~~~

`toURL()` can fail for a URI that cannot be converted to a URL. If an API requires `URL`, declaring `URL` directly in configuration properties is also valid when supported by the Spring Boot version's conversion.

### 4.3. URL Is Not the Place to Store Every Kind of Path

A path like:

~~~text
./certs/service.pem
~~~

is not a network URL with a scheme. If it is a file the application wants to read, `Resource` or `Path` is more suitable than declaring `URL` and trying to construct URLs from relative file paths.

For a `file:` URL, valid syntax must be used:

~~~text
file:/etc/myapp/service.pem
~~~

on the corresponding filesystem. In an application packaged as a JAR, files on the classpath are usually easier to access via `Resource`; do not force every classpath asset into a `URL` assuming it has an individual physical file on disk.

### 4.4. Security When Using URLs for Network Access

A configured URL may point to an external system or internal network address. If untrusted users or data sources can influence the URL loaded by the application, SSRF or data leakage risks arise.

When opening a URL:

- Only allow accepted schemes, typically `https` for external APIs.
- Restrict hosts/destinations per operational policy.
- Configure connect/read timeouts and control redirects.
- Never embed credentials or tokens directly in URL queries and log them.
- Separate **URL parsing** from **actually accessing the URL**.

## 5. `InetAddress`: Network Address, Not a URL

`java.net.InetAddress` represents a host's IP address. It fits when a Java API needs a resolved IP address, such as configuring a socket bind address or network-level communication.

~~~properties
app.network.bind-address=127.0.0.1
~~~

~~~java
import java.net.InetAddress;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.network")
public record NetworkProperties(InetAddress bindAddress) {
}
~~~

Once the binder converts the string to `InetAddress`, you can access:

~~~java
InetAddress address = properties.bindAddress();

String numeric = address.getHostAddress(); // 127.0.0.1
~~~

### 5.1. Literal IP Addresses vs. Hostnames

Two configurations have different implications:

~~~properties
app.network.bind-address=192.0.2.10
~~~

and:

~~~properties
app.network.bind-address=host.example.test
~~~

A numeric address can usually produce an `InetAddress` without querying DNS for a hostname. With a hostname, creating an `InetAddress` can involve **name resolution** via the JVM/OS mechanism. If the hostname fails to resolve, binding can fail at startup or become dependent on DNS availability.

This is especially important when:

- a container starts before internal DNS is ready;
- a hostname only resolves inside a specific VPN;
- local development and production use different DNS setups;
- the application only needs to keep the hostname string rather than an IP address at startup.

If the application only needs to construct a URL or open a socket to a hostname later, storing `String hostname` or `URI endpoint` may be better than `InetAddress` to avoid unnecessary eager DNS resolution.

### 5.2. `InetAddress` Does Not Include a Port

For example:

~~~text
192.0.2.10:8080
~~~

is a **host + port** pair, not a standalone IP address. Do not pass that whole string into an `InetAddress` field.

Instead:

~~~properties
app.network.host=192.0.2.10
app.network.port=8080
~~~

~~~java
import java.net.InetAddress;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.network")
public record NetworkProperties(
        InetAddress host,
        int port
) {}
~~~

If the application needs a socket endpoint object, construct it from those components using the appropriate API, for example:

~~~java
import java.net.InetSocketAddress;

InetSocketAddress socketAddress =
        new InetSocketAddress(properties.host(), properties.port());
~~~

Validation should still check that `port` falls within the application's valid range.

### 5.3. IPv4 and IPv6

IPv4 literal:

~~~properties
app.network.bind-address=127.0.0.1
~~~

IPv6 literal:

~~~properties
app.network.bind-address=::1
~~~

In YAML, quote IPv6 addresses to clarify the scalar:

~~~yaml
app:
  network:
    bind-address: "::1"
~~~

In a **URI with an IPv6 host**, the authority representation typically uses square brackets:

~~~properties
app.api.endpoint=http://[::1]:8080/api
~~~

Do not confuse `InetAddress` syntax `::1` with URI host syntax `[::1]`. When building HTTP endpoints, use `URI`; when needing an IP address in a network API, use `InetAddress`.

### 5.4. Concrete Subtypes `Inet4Address` and `Inet6Address`

`InetAddress` is the superclass for IPv4 and IPv6 addresses. If the application permits only one address family, check the type:

~~~java
import java.net.Inet4Address;

if (!(properties.bindAddress() instanceof Inet4Address)) {
    throw new IllegalArgumentException(
        "app.network.bind-address must be IPv4");
}
~~~

Simply declaring `InetAddress` does not guarantee whether the value is IPv4 or IPv6. A hostname can resolve to either family depending on DNS and JVM/OS preference policies.

### 5.5. "Resolves to an IP" Does Not Mean "Connectable"

Even when `InetAddress` is created, the IP may be unreachable or no process may be listening on the port. The binder does not ping hosts or open TCP connections just because a field has type `InetAddress`.

If the application needs to check endpoint health, use operational health checks or probes with appropriate timeouts; do not treat successful type conversion as proof that a service is up.

## 6. `Resource`: Abstraction for Reading Resources

`org.springframework.core.io.Resource` is a Spring Framework interface. It abstracts a data source, allowing code to read content without needing to know upfront whether the source lives inside a JAR, on the filesystem, or elsewhere.

Common locations:

| Configuration String | Common Meaning |
| --- | --- |
| `classpath:certs/public.pem` | Resource on the classpath |
| `classpath:/certs/public.pem` | Resource starting from the classpath root |
| `file:/etc/myapp/keys/public.pem` | File on the filesystem |
| `file:./config/public.pem` | File relative to the working directory |
| `https://example.test/assets/schema.json` | URL resource if supported by the resolver/handler |
| `config/public.pem` | Prefixless location; interpretation depends on `ResourceLoader`/context |

When configuration points to a file or content to be opened as a stream, `Resource` typically provides a better API than `URI` and `URL`.

Example:

~~~properties
app.security.public-key=classpath:certs/public.pem
~~~

~~~java
import org.springframework.core.io.Resource;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.security")
public record SecurityProperties(Resource publicKey) {
}
~~~

When the source and binder support the conversion, `publicKey` is a `Resource` pointing to the declared location.

### 6.1. Reading a Stream from a Resource

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;

public byte[] loadBytes(Resource resource) throws IOException {
    try (InputStream input = resource.getInputStream()) {
        return input.readAllBytes();
    }
}
~~~

Opening the stream is when code actually attempts to access the content. It can throw `IOException` if the file is missing, permissions are insufficient, or the source is unavailable.

If the file can be very large, avoid `readAllBytes()` in production; stream or bound the size as required. This example only illustrates basic usage.

### 6.2. `Resource` Is Not Necessarily a `File`

A common mistake is writing:

~~~java
File file = properties.publicKey().getFile();
~~~

and assuming the call always works. For a resource inside an executable JAR, the entry lives **inside an archive** and does not necessarily have a standalone physical path accessible as `java.io.File`.

Safer way to read content from the classpath:

~~~java
try (InputStream in = properties.publicKey().getInputStream()) {
    // Process data.
}
~~~

Only use `getFile()` when you actually know the resource resides on the filesystem and a real `File` is required.

### 6.3. `exists()` and `isReadable()`

`Resource` offers methods such as `exists()`, `isReadable()`, and `getInputStream()`. You can check before reading:

~~~java
Resource resource = properties.publicKey();

if (!resource.exists()) {
    throw new IllegalStateException(
        "Configured public key resource does not exist");
}
~~~

Even so, a race condition remains: a file present at check time might be deleted before opening the stream. Therefore, handle `IOException` at the read site itself.

Do not treat `Resource.exists()` as a security check. It only reports existence according to the resource implementation's mechanics.

### 6.4. Relative Resource Locations

~~~properties
app.security.public-key=file:./config/public.pem
~~~

The `./` path is typically resolved relative to the **Java process's working directory**, not the directory containing the JAR. Running the same JAR from two different working directories can resolve to two different files or fail with not-found errors.

In containers, check `WORKDIR`, `workingDir`, and mount paths. For stable external files, absolute paths like `file:/etc/myapp/public.pem` are usually less surprising.

### 6.5. Do Not Confuse `classpath:` with `file:`

~~~properties
app.security.public-key=classpath:certs/public.pem
~~~

means look on the classpath, fitting resources under `src/main/resources/certs/public.pem` packaged into the artifact.

~~~properties
app.security.public-key=file:/etc/myapp/public.pem
~~~

means an external file that must exist on the runtime environment's filesystem.

Using `classpath:` for files that must change independently of the JAR is inconvenient because classpath files are usually tied to the build. Using `file:` for a resource packaged inside the JAR is also wrong unless an external file actually exists.

## 7. Combined Example with All Four Types

Suppose an application needs configuration for a remote service and a trust material file:

~~~yaml
app:
  remote:
    base-uri: "https://api.example.test:8443/v1"
    legacy-url: "https://legacy.example.test/v2"
    bind-address: "127.0.0.1"
    trust-bundle: "classpath:tls/trust.pem"
~~~

Record:

~~~java
package com.example.client.config;

import java.net.InetAddress;
import java.net.URI;
import java.net.URL;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.core.io.Resource;

@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(
        URI baseUri,
        URL legacyUrl,
        InetAddress bindAddress,
        Resource trustBundle
) {}
~~~

Registration:

~~~java
package com.example.client;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` discovers annotated classes in the appropriate package. For record constructor binding in Spring Boot 3.x, this registration approach is more appropriate than adding `@Component` and expecting Spring to bind constructor parameters as properties automatically.

Consuming service:

~~~java
package com.example.client.service;

import com.example.client.config.RemoteProperties;
import java.io.IOException;
import java.io.InputStream;
import org.springframework.stereotype.Service;

@Service
public class RemoteClientSettingsReader {

    private final RemoteProperties properties;

    public RemoteClientSettingsReader(RemoteProperties properties) {
        this.properties = properties;
    }

    public String host() {
        return properties.baseUri().getHost();
    }

    public String localBindIp() {
        return properties.bindAddress().getHostAddress();
    }

    public byte[] readTrustBundle() throws IOException {
        try (InputStream input =
                     properties.trustBundle().getInputStream()) {
            return input.readAllBytes();
        }
    }
}
~~~

The example above illustrates consuming typed configuration. It does **not** build a secure HTTP client, configure TLS, verify certificates, or open network connections. Those tasks require dedicated libraries and architecture.

## 8. Equivalent Declaration in `application.properties`

The four YAML properties in the previous section can be written as:

~~~properties
app.remote.base-uri=https://api.example.test:8443/v1
app.remote.legacy-url=https://legacy.example.test/v2
app.remote.bind-address=127.0.0.1
app.remote.trust-bundle=classpath:tls/trust.pem
~~~

Spring Boot Binder uses relaxed binding: `base-uri` maps to Java `baseUri`, `bind-address` to `bindAddress`, and `trust-bundle` to `trustBundle`.

If using a mutable JavaBean:

~~~java
import java.net.InetAddress;
import java.net.URI;
import java.net.URL;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.remote")
public class RemotePropertiesBean {

    private URI baseUri;
    private URL legacyUrl;
    private InetAddress bindAddress;
    private Resource trustBundle;

    public URI getBaseUri() { return baseUri; }
    public void setBaseUri(URI value) { baseUri = value; }

    public URL getLegacyUrl() { return legacyUrl; }
    public void setLegacyUrl(URL value) { legacyUrl = value; }

    public InetAddress getBindAddress() { return bindAddress; }
    public void setBindAddress(InetAddress value) { bindAddress = value; }

    public Resource getTrustBundle() { return trustBundle; }
    public void setTrustBundle(Resource value) { trustBundle = value; }
}
~~~

`@Component` requires the class to fall within component-scanning scope. A setter-based JavaBean fits standard component-scan registration. For immutable records, use `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

## 9. Externalized Configuration Sources and Precedence Order

Spring Boot can read these keys from multiple sources. For example, inside the JAR:

~~~properties
# application.properties
app.remote.base-uri=https://api.default.example/v1
app.remote.bind-address=127.0.0.1
app.remote.trust-bundle=classpath:tls/default.pem
~~~

Outside the JAR:

~~~properties
# file:./config/application.properties
app.remote.base-uri=https://api.production.example/v1
app.remote.trust-bundle=file:/etc/app/tls/trust.pem
~~~

Under standard default Config Data search rules, external files have higher precedence than files inside the JAR. During binding, Boot selects the effective value for each key and converts it to the corresponding Java type.

`app.remote.bind-address` can still come from the base file inside the JAR, while `base-uri` and `trust-bundle` come from the external file. One `@ConfigurationProperties` object can combine fields supplied by **multiple property sources**; not all fields need to live in the same file.

### 9.1. Overriding with Command-Line Arguments

~~~bash
java -jar app.jar \
  --app.remote.base-uri=https://canary.example.test/v1 \
  --app.remote.bind-address=0.0.0.0
~~~

In common Spring Boot setups, command-line properties take higher precedence than Config Data. The binder receives the new strings and converts them to `URI` and `InetAddress`.

`0.0.0.0` is typically used as a bind address across all IPv4 interfaces when permitted by socket APIs, not as a destination hostname for outbound Internet requests. Do not treat it as an HTTP endpoint you can call.

### 9.2. Environment Variables

Common environment variable names under relaxed binding:

~~~text
APP_REMOTE_BASEURI
APP_REMOTE_LEGACYURL
APP_REMOTE_BINDADDRESS
APP_REMOTE_TRUSTBUNDLE
~~~

Shell example:

~~~bash
export APP_REMOTE_BASEURI="https://api.production.example/v1"
export APP_REMOTE_BINDADDRESS="127.0.0.1"
export APP_REMOTE_TRUSTBUNDLE="file:/etc/app/tls/trust.pem"

java -jar app.jar
~~~

The rule for turning a canonical name into an env var is typically: dots become underscores, hyphens are removed, and letters become uppercase. Thus `base-uri` generally becomes `BASEURI`; do not assume `BASE_URI` is treated identically by every mechanism.

For simple property names like `server.address`, the environment variable name is `SERVER_ADDRESS`. When names contain hyphens and collection indices, take extra care.

### 9.3. Profile-Specific Configuration

~~~properties
# application-dev.properties
app.remote.base-uri=http://localhost:8081/v1
app.remote.bind-address=127.0.0.1
app.remote.trust-bundle=classpath:tls/dev.pem
~~~

~~~properties
# application-prod.properties
app.remote.base-uri=https://api.example.test/v1
app.remote.bind-address=10.0.0.5
app.remote.trust-bundle=file:/etc/app/tls/prod.pem
~~~

Profile loading determines which string values are present and take precedence; the declared Java types remain unchanged. A `Resource` only changes its location, while code calling `getInputStream()` can stay the same.

Do not store real secrets in committed profile-specific files. Profiles are for selecting configuration, not for protecting sensitive data.

## 10. Placeholders Before and During Binding

Converted values can also contain `${...}` placeholders:

~~~properties
app.api.scheme=https
app.api.host=api.example.test
app.api.port=8443

app.remote.base-uri=${app.api.scheme}://${app.api.host}:${app.api.port}/v1
app.remote.trust-bundle=${APP_TRUST_RESOURCE:classpath:tls/default.pem}
~~~

When Spring Boot resolves properties according to its configuration rules, placeholders can be substituted with values looked up from `Environment` before converting to `URI` or `Resource`.

For example, when `APP_TRUST_RESOURCE` is supplied as `file:/etc/app/trust.pem`, `trustBundle` can point to the external file. If absent, the placeholder default is `classpath:tls/default.pem`.

### 10.1. Default Does Not Guarantee the Resource Exists

~~~properties
app.remote.trust-bundle=${APP_TRUST_RESOURCE:classpath:tls/default.pem}
~~~

If `tls/default.pem` is not actually on the artifact's classpath, constructing the `Resource` can still succeed while opening the stream fails. Placeholder syntax only supplies a default location; it does not verify the source content.

### 10.2. Watch Out for Shell Expansion

If passing literal `${APP_TRUST_RESOURCE:...}` from a Bash command, the shell may expand `${...}` before Java runs. Wrap the argument in single quotes in POSIX shells if you want Spring to receive the literal placeholder:

~~~bash
java -jar app.jar \
  '--app.remote.trust-bundle=${APP_TRUST_RESOURCE:classpath:tls/default.pem}'
~~~

In `application.properties` and YAML files loaded directly by Spring Boot, the shell does not process strings like that.

## 11. Resource Locations and How Resolvers Pick Implementations

`Resource` is an interface; the concrete implementation depends on the location and the `ResourceLoader`/conversion mechanism.

Examples:

| Location | Typical Resource Implementation | Characteristics |
| --- | --- | --- |
| `classpath:config/default.json` | `ClassPathResource` | Can work when the asset is inside a JAR |
| `file:/etc/app/config.json` | `FileSystemResource` or equivalent | Filesystem file |
| `https://example.test/config.json` | `UrlResource` or equivalent | May require a network request when opened |
| Relative location without prefix | Context- and loader-dependent | Avoid if portable behavior is needed |

Do not depend on concrete implementation class names in business code unless specifically required. It is better to program against the `Resource` interface and use `getInputStream()` when needed.

### 11.1. Classpath Resources in an Executable JAR

~~~text
src/main/resources/
└── tls/
    └── trust.pem
~~~

Configuration:

~~~properties
app.remote.trust-bundle=classpath:tls/trust.pem
~~~

After building, the resource can reside inside the JAR. This is why code reading `InputStream` is more appropriate than code requiring `File`.

If operators must modify the resource without rebuilding, you can choose `file:/etc/app/tls/trust.pem` and mount the file in the deployment environment.

### 11.2. Resource Paths May Be Passed to Other Loaders

Not every library accepting a string knows the `classpath:...` syntax. That is a convention of Spring's `ResourceLoader`. If a library requires a plain filesystem path, you may need to supply a `Path` or stream rather than passing the raw `classpath:...` string.

Conversely, if a method accepts a Spring `Resource`, passing the `Resource` object directly usually reduces coupling to source details.

### 11.3. Do Not Confuse `Resource` with Multiple Resources

A single `Resource` field represents **one resource**. Wildcard patterns like `classpath*:/**/*.xml` belong to `ResourcePatternResolver`'s multi-resource lookup mechanism and do not carry the same meaning when assigned to a single `Resource` field.

For example, if you need multiple schema files from the classpath:

~~~java
import java.io.IOException;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

PathMatchingResourcePatternResolver resolver =
        new PathMatchingResourcePatternResolver();

Resource[] schemas =
        resolver.getResources("classpath*:schemas/*.xsd");
~~~

This is pattern-based lookup, not simple conversion of one string into one `Resource`. If you want to configure a list of specific file locations, you can use `List<Resource>` in a configuration properties class when supported by the binder/converters.

## 12. Arrays and Lists of Convertible Types

Spring Boot Binder can handle collections whose elements have corresponding converters.

Example:

~~~yaml
app:
  peers:
    endpoints:
      - "https://peer-a.example.test/api"
      - "https://peer-b.example.test/api"
    addresses:
      - "192.0.2.10"
      - "192.0.2.11"
    certificates:
      - "classpath:certs/a.pem"
      - "file:/etc/app/certs/b.pem"
~~~

Java:

~~~java
import java.net.InetAddress;
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.core.io.Resource;

@ConfigurationProperties(prefix = "app.peers")
public record PeerProperties(
        List<URI> endpoints,
        List<InetAddress> addresses,
        List<Resource> certificates
) {}
~~~

Each element is converted to the matching type. If an element has invalid syntax, the error can point to an indexed key such as `app.peers.endpoints[1]`.

### 12.1. Indexed Properties

~~~properties
app.peers.endpoints[0]=https://peer-a.example.test/api
app.peers.endpoints[1]=https://peer-b.example.test/api

app.peers.addresses[0]=192.0.2.10
app.peers.addresses[1]=192.0.2.11

app.peers.certificates[0]=classpath:certs/a.pem
app.peers.certificates[1]=file:/etc/app/certs/b.pem
~~~

Indexed properties work well when elements contain commas or when clear element boundaries are needed.

### 12.2. Lists Are Not Automatically Merged Across PropertySources

When a list is declared in a base file and in a higher-precedence profile-specific file, the binder typically uses the **list from the higher-precedence source** rather than appending elements across all sources.

If you have:

~~~yaml
# application.yml
app:
  peers:
    endpoints:
      - https://dev-a.example.test
      - https://dev-b.example.test
~~~

and:

~~~yaml
# application-prod.yml
app:
  peers:
    endpoints:
      - https://prod.example.test
~~~

under the `prod` profile, in the simple case, the effective `endpoints` list contains only the single production URI. It does not automatically become three endpoints. This rule matters when lists hold URIs/Resources and operators expect per-environment appending.

## 13. Validation: Right Type Does Not Mean Right Semantics

Binding eliminates a class of syntax and conversion bugs. However, it does not replace application rules.

Example:

~~~java
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.api")
public record ApiProperties(
        @NotNull URI endpoint
) {}
~~~

`@NotNull` ensures the object is non-null; **it does not ensure the URI uses the `https` scheme, has a host, or belongs to an allowlist**.

### 13.1. Validating an Absolute HTTP(S) URI

~~~java
import java.net.URI;

public static void requireHttpEndpoint(URI endpoint) {
    if (endpoint == null) {
        throw new IllegalArgumentException("Endpoint is required");
    }

    String scheme = endpoint.getScheme();
    boolean http = "http".equalsIgnoreCase(scheme);
    boolean https = "https".equalsIgnoreCase(scheme);

    if ((!http && !https) || endpoint.getHost() == null) {
        throw new IllegalArgumentException(
            "Endpoint must be an absolute HTTP(S) URI with a host");
    }
}
~~~

If the environment allows only HTTPS, remove the HTTP branch or enforce an explicit validation rule. If the endpoint includes a port, you can require the port to be within an allowed range.

### 13.2. Validating URLs for Business Suitability

A successfully constructed `URL` may use a protocol the application does not want to support. Check `getProtocol()` and host against policy.

Do not call `openStream()` just to "validate" arbitrary URLs from untrusted sources; that causes I/O and unintended network access.

### 13.3. Validating InetAddress by Purpose

If a local bind address is required, the application may require:

- IPv4 or IPv6 depending on server capability.
- A loopback address in development environments.
- An address configured on a container network interface.
- Disallowing wildcard addresses in certain secure modes.

`InetAddress` itself does not verify whether the address is actually assigned to a current network interface. That is a separate check, sometimes needed when starting a socket server.

### 13.4. Checking Resource Availability by File Type

If a certificate is required:

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;

public static void requireReadable(Resource resource) {
    if (resource == null || !resource.exists() || !resource.isReadable()) {
        throw new IllegalStateException("Required resource is unavailable");
    }

    try (InputStream ignored = resource.getInputStream()) {
        // Stream opened; parse content in the appropriate layer.
    } catch (IOException e) {
        throw new IllegalStateException("Cannot read required resource", e);
    }
}
~~~

This checks availability, not whether the content is actually a valid certificate/key. For TLS material, use a proper parser and enforce error handling, file permissions, and security.

If the resource is a network URL, `exists()`/`isReadable()` can trigger I/O; avoid using them as arbitrary synchronous startup validation if the source is untrusted or lacks timeouts.

## 14. Jakarta Validation and Required Configuration

When using `@Validated` with a compatible Bean Validation provider (commonly via `spring-boot-starter-validation`), Boot can validate configuration early.

~~~java
import jakarta.validation.constraints.NotNull;
import java.net.InetAddress;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.core.io.Resource;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(
        @NotNull URI endpoint,
        @NotNull InetAddress bindAddress,
        @NotNull Resource certificate
) {}
~~~

These annotations check **object presence**. If an absolute URL is required, a certificate must exist, or an IP must belong to an allowed range, add custom validation or appropriate startup logic.

### 14.1. Why Not Use `@NotBlank` on URI/Resource?

`@NotBlank` is designed for `CharSequence`. If placed on `URI`, `InetAddress`, or `Resource`, Bean Validation may lack a matching validator and throw an error.

For these objects, use `@NotNull`, a custom constraint, or dedicated validation methods. Do not pick an annotation merely because its name sounds right.

### 14.2. Validating Inside a Record Constructor

If you want the object's immutable contract to always hold, you can validate part of it directly in the constructor:

~~~java
@ConfigurationProperties(prefix = "app.api")
public record ApiProperties(URI endpoint) {
    public ApiProperties {
        if (endpoint == null || endpoint.getHost() == null) {
            throw new IllegalArgumentException(
                "app.api.endpoint must contain a host");
        }
    }
}
~~~

This case still needs scheme checks and other rules if required by the application. Exceptions can be wrapped by Spring Boot in binding or configuration-properties creation errors, which is expected behavior for invalid configuration.

## 15. Custom Converters When Values Do Not Match Standard Conventions

The four standard types already have appropriate conversion paths in Spring Boot/Spring Framework. However, applications sometimes receive configuration in a custom format, such as an internal identifier string that should become a domain object.

Do not add an arbitrary converter just to patch a malformed URL or nonexistent hostname. First, make sure the source data is valid.

Example of a domain type:

~~~java
public record EndpointId(String region, String service) {
}
~~~

Configuration:

~~~properties
app.endpoint-id=ap-southeast-1/catalog
~~~

Converter:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
@ConfigurationPropertiesBinding
public class EndpointIdConverter implements Converter<String, EndpointId> {

    @Override
    public EndpointId convert(String value) {
        String[] parts = value.split("/", 2);

        if (parts.length != 2 || parts[0].isBlank() || parts[1].isBlank()) {
            throw new IllegalArgumentException(
                "Expected '<region>/<service>'");
        }

        return new EndpointId(parts[0], parts[1]);
    }
}
~~~

`@ConfigurationPropertiesBinding` marks a converter to be used for configuration properties. In modern Boot versions, ensure the converter is registered at the right stage so the binder can use it; for early-created converters, avoid injecting beans that depend on an incomplete application context.

The purpose of this example is to illustrate the extension point. There is no need to replace built-in converters for `URI`, `URL`, `InetAddress`, or `Resource` when standard formats already satisfy requirements.

### 15.1. Converters Should Have No Side Effects

A converter turning a hostname into a domain object should not create accounts, send HTTP requests, or modify files. Such side effects turn configuration binding into an uncontrollable process.

With `InetAddress`, conversion itself can trigger DNS lookups; this is one reason to choose `String` if you do not want DNS infrastructure affecting startup.

## 16. Safe Production Configuration Example

A service needs an API endpoint, a bind address, and a trust store file:

~~~yaml
app:
  integration:
    endpoint: "https://integration.example.test/v2"
    bind-address: "0.0.0.0"
    trust-resource: "file:/etc/app/tls/trust.pem"
~~~

Java:

~~~java
import java.net.InetAddress;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.core.io.Resource;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        URI endpoint,
        InetAddress bindAddress,
        Resource trustResource
) {}
~~~

If the deployment environment provides `/etc/app/tls/trust.pem`, code can read it via `Resource.getInputStream()`. Still, you must configure the HTTP/TLS library to consume that content while enforcing file permissions.

A container deployment may mount a ConfigMap/Secret or persistent volume at the specified path. Spring Boot does not mount files automatically just because `Resource` points to that location.

### 16.1. Pre-Deployment Checklist

- The `endpoint` scheme is HTTPS per policy.
- The host is not an untrusted address if the endpoint can be influenced by user input.
- DNS and network routes to the endpoint work when requests are sent.
- The bind address matches a network interface of the container.
- The trust resource file is mounted properly, readable, and has valid content.
- A restart procedure when configuration or secrets change is clearly designed.
- Credentials, private keys, or sensitive resource contents are never logged.

## 17. Handling Files Inside a JAR vs. External Files

### 17.1. Assets Packaged Inside the JAR

~~~text
src/main/resources/
└── policies/
    └── access-rules.json
~~~

Configuration:

~~~properties
app.policy.resource=classpath:policies/access-rules.json
~~~

Java:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;

public String readPolicy(Resource resource) throws IOException {
    try (var stream = resource.getInputStream()) {
        return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Even when running an executable JAR, reading via `getInputStream()` works as expected as long as the resource actually exists on the classpath.

### 17.2. Externally Mounted Files

~~~properties
app.policy.resource=file:/etc/app/policies/access-rules.json
~~~

The exact same stream-reading code above works without changing any Java class. That is the benefit of `Resource`: swapping the location via externalized configuration.

### 17.3. Do Not Assume Live Reload

If a mounted file is edited after the application starts, the `Resource` object may still point to the same location and opening a new stream may see updated content depending on the source. However, **if a service read the file once and cached its contents in memory**, modifying the file does not refresh parsed data automatically.

Likewise, editing the `app.policy.resource` property on disk after startup does not rebind fields in the bean. The system needs an explicit reload or restart mechanism, especially for security policies.

## 18. Unit and Integration Testing for Type Conversion

For typed configuration, test the conversion path in a real Spring Boot environment rather than only invoking the Java constructor manually.

Suppose:

~~~java
import java.net.InetAddress;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.test")
public record TestProperties(
        URI endpoint,
        InetAddress address
) {}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    classes = ConversionBindingTest.TestConfig.class,
    properties = {
        "app.test.endpoint=https://test.example.test/v1",
        "app.test.address=127.0.0.1"
    }
)
class ConversionBindingTest {

    @org.springframework.boot.SpringBootConfiguration
    @EnableConfigurationProperties(TestProperties.class)
    static class TestConfig {}

    @Autowired
    TestProperties properties;

    @Test
    void bindsUriAndIpAddress() {
        assertEquals("https", properties.endpoint().getScheme());
        assertEquals("test.example.test",
                     properties.endpoint().getHost());
        assertEquals("127.0.0.1",
                     properties.address().getHostAddress());
    }
}
~~~

The test avoids hostnames requiring DNS lookup so results remain environment-independent. `example.test` in the URI tests parsing without making network calls.

### 18.1. Testing with Resource

You can place a test file:

~~~text
src/test/resources/
└── samples/
    └── test-config.txt
~~~

Test property:

~~~properties
app.test.resource=classpath:samples/test-config.txt
~~~

Assertion:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

assertTrue(properties.resource().exists());
~~~

To check content, open `getInputStream()` in the test with `IOException` handling. A classpath `Resource` does not have to map to a `File`, so tests should not rely on `getFile()` either.

### 18.2. Testing Failure Cases

Cases to include:

- URI missing a scheme when an absolute HTTP endpoint is required.
- URI containing invalid characters.
- URL with a protocol disallowed by the application.
- `InetAddress` receiving an unresolvable hostname in a test environment, if that needs controlled testing.
- `Resource` pointing to a missing file when required.
- A property overridden by a higher-precedence source with an invalid location.
- IPv6 configuration properly formatted for `InetAddress` and URI.
- Tests never making requests to external systems just to prove binding.

If intentionally testing DNS failures, ensure timeouts and a suitable test environment; most CI tests should not depend on real DNS.

## 19. Troubleshooting Common Errors

### 19.1. `Failed to bind properties`

An error like:

~~~text
Failed to bind properties under 'app.remote.base-uri'
~~~

can stem from conversion, a mismatched target type, or source configuration. Always check the inner cause, such as `IllegalArgumentException`, `URISyntaxException`, or network resolution errors.

Steps:

1. Check the `prefix` in `@ConfigurationProperties`.
2. Check that the Java field has the right type and relaxed-binding name.
3. Determine which property source supplies the final value.
4. Check YAML/properties syntax.
5. Inspect whether the converter cannot handle the value.
6. Distinguish conversion failures from errors when code actually uses the object.

Do not fix binding errors by turning every field into `String` and skipping validation. Using `String` makes sense only if the application genuinely needs raw text or intentionally defers conversion.

### 19.2. URI Containing Spaces

~~~properties
app.remote.base-uri=https://api.example.test/my path
~~~

A string with raw spaces in a URI can be invalid. Encode properly or use a builder when assembling from dynamic parts:

~~~properties
app.remote.base-uri=https://api.example.test/my%20path
~~~

Do not assume the binder automatically encodes invalid characters.

### 19.3. URL Missing a Protocol

~~~properties
app.remote.legacy-url=api.example.test/v1
~~~

A `URL` typically requires a valid protocol. If the intent is a relative path, choose a relative `URI`, `Resource`, or `Path` depending on semantics rather than forcing a `URL`.

### 19.4. InetAddress Including a Port

~~~properties
app.network.bind-address=127.0.0.1:8080
~~~

This string is not a pure IP literal. Split host and port into two properties:

~~~properties
app.network.bind-address=127.0.0.1
app.network.bind-port=8080
~~~

### 19.5. InetAddress Depending on DNS

~~~properties
app.network.bind-address=internal-host
~~~

If the environment cannot resolve `internal-host`, binding can fail. If the application does not truly need a resolved IP at startup, choose `String hostname` and resolve later in the connection layer.

### 19.6. Resource Does Not Exist

~~~properties
app.security.public-key=classpath:certs/missing.pem
~~~

The bound `Resource` handle itself can exist, while `getInputStream()` fails when the actual file is absent. Verify JAR packaging, exact path, and letter casing; on Linux filesystems, case sensitivity can produce different outcomes than on a development machine.

### 19.7. `getFile()` on a Classpath Resource Inside a JAR

Code:

~~~java
properties.publicKey().getFile();
~~~

can fail if the file resides inside an archive. Use `getInputStream()`, or intentionally extract to a temporary file if a library strictly requires `File`. When extracting, manage permissions, cleanup, and sensitive data.

### 19.8. Loading URLs/Resources from Untrusted Sources

If a property is set from arbitrary input, the application could be directed to local files or internal endpoints. Never use `Resource` to read arbitrary files supplied by user requests. Restrict allowed schemes, path roots, and hosts per policy.

### 19.9. YAML Parse Errors Before Binding

~~~yaml
app:
  remote:
    bind-address: ::1
~~~

YAML syntax can interpret special characters contextually. For IPv6, quote the value:

~~~yaml
app:
  remote:
    bind-address: "::1"
~~~

### 19.10. Configuration Changed but Application Still Reads Old Value

`@ConfigurationProperties` typically binds at startup. Editing `application.yml` or an environment variable in another shell does not recreate running beans. Only a restart or an explicitly designed refresh mechanism applies changes in a controlled manner.

## 20. Comparison with `String` and `Path`

Using a complex type is not always better. Choose the type based on **intended use**.

| Need | Type to Consider | Why |
| --- | --- | --- |
| HTTP endpoint with known scheme and host | `URI` | Represents a network identifier with clear structure |
| Integrating a library requiring `URL` | `URL` | Avoids converting at many call sites |
| Need an IP address to bind a socket | `InetAddress` | Network APIs operate directly on IPs |
| Want to keep hostname and resolve DNS on connect | `String` | Avoids forcing DNS resolution during binding |
| Need to read files in JAR or external filesystem | `Resource` | One unified stream API for multiple sources |
| Need a pure filesystem path for NIO operations | `Path` | Fits `Files`, `Path.resolve`, and file permissions |
| Need a URL built from dynamic parts | `URI` and builder | Prevents bad string concatenation/encoding |
| Need a list of endpoints | `List<URI>` | Binder converts each element |

**Do not use `InetAddress` in place of `URI`** just because a URL contains a host. `InetAddress` holds no scheme, port, path, or query. **Do not use `Resource` in place of a URL endpoint** if the application actually needs to send protocol-specific HTTP requests and handle responses, status codes, and authentication.

### 20.1. When to Keep String?

A URL with placeholders or a hostname that only has meaning in a specialized subsystem which parses it differently from Java `URI`. In that case, keeping `String` may fit. Still, add validation at the right boundary. Do not keep everything as `String` and let each service parse it inconsistently.

### 20.2. When to Choose Path?

`java.nio.file.Path` targets file locations on a filesystem. It is useful when the program uses `Files.readString`, `Files.newInputStream`, or `Files.move`. However, `Path` does not understand Spring's `classpath:` syntax; do not turn a classpath path inside a JAR into a `Path` expecting a filesystem entry.

`Resource` is the more natural choice when the source might reside either on the classpath or on an external filesystem.

## 21. Notes on Conversion Timing and Infrastructure Dependencies

These types do not share identical initialization costs:

- Constructing `URI` typically only processes string syntax, requiring no network access.
- Constructing `URL` typically validates protocol/handler without sending HTTP requests.
- Constructing `InetAddress` from a hostname may trigger DNS resolution and depend on the environment.
- Constructing `Resource` typically creates a location handle; checking existence or opening a stream may perform I/O depending on implementation.

If you want startup to depend as little as possible on external services, avoid conversions or validation steps that unnecessarily trigger DNS/HTTP calls. Conversely, if a resource such as a certificate or policy file is **mandatory**, checking early at startup can help catch deployment mistakes.

Good design separates:

1. **Typed configuration resolution** to ensure structural validity.
2. **Application contract checks** to enforce business/technical requirements.
3. **Actual connectivity or resource checks** at the right time, with timeouts and error handling.

## 22. Operational Scenario: Same JAR Configured for Local and Kubernetes

Suppose an application uses a packaged certificate locally while reading a mounted certificate in production.

Base configuration:

~~~yaml
app:
  remote:
    base-uri: "http://localhost:8081/api"
    bind-address: "127.0.0.1"
    trust-bundle: "classpath:tls/dev-trust.pem"
~~~

Document activated by the production profile:

~~~yaml
---
spring:
  config:
    activate:
      on-profile: prod

app:
  remote:
    base-uri: "https://api.production.example/v1"
    bind-address: "0.0.0.0"
    trust-bundle: "file:/etc/app/tls/production-trust.pem"
~~~

Running locally:

~~~bash
java -jar app.jar
~~~

Running in production:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

When Boot loads documents according to activation conditions and precedence, the identically named fields bind to `URI`, `InetAddress`, and `Resource` from the effective values.

Crucially, `file:/etc/app/tls/production-trust.pem` does not create the file by itself. Infrastructure must mount the file at that exact location and grant read permissions. Using the `prod` profile does not replace infrastructure security controls.

### 22.1. Bind Address Differs from Access Address

In a container, `bind-address=0.0.0.0` can make the server listen on all suitable IPv4 interfaces. However, clients cannot use `0.0.0.0` as a routable service endpoint. Listening addresses and outbound service endpoint addresses must be kept clearly separate.

### 22.2. Certificate Files Can Come from a Secret

A mounted Secret can be mapped as a file, with `Resource` pointing to the corresponding path. Even so, secret protection depends on permissions, RBAC, lifecycle, volumes, and policies. Never print certificate/private key contents to debug logs.

## 23. Quick Troubleshooting Reference Table

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| URI fails to bind | Syntax error or bad encoding | Check scheme, path, percent-encoding |
| URI binds yet cannot send HTTP | Relative URI or unsupported scheme | Check absolute HTTP(S), host, and client |
| URL fails to bind | Missing or unsupported protocol | Use full URL or switch to `URI`/`Resource` |
| URL holds a value yet request fails | DNS, TLS, proxy, timeout | Distinguish parsing from network access |
| `InetAddress` breaks startup | Hostname fails to resolve | Check DNS/hosts or use `String` for late resolution |
| `InetAddress` rejects port | Entered `host:port` in one field | Separate host and port |
| IPv6 fails in URI | Missing `[ ]` around host | Use `http://[::1]:8080` |
| `Resource` read fails | Missing file, wrong path, lack of permissions | Check classpath/file mount and read stream safely |
| `Resource.getFile()` fails in JAR | Asset resides inside archive | Use `getInputStream()` |
| Value differs from the file being read | Overridden by a higher-precedence source | Check profiles, env vars, command line |
| Config changed yet bean keeps old value | Binding happened at startup | Restart or use a dedicated refresh mechanism |
| `@NotBlank` on `URI` throws validation error | Constraint applied to wrong type | Use `@NotNull`/custom validator |

## 24. Project Implementation Checklist

- Clarify property semantics before picking `URI`, `URL`, `InetAddress`, `Resource`, or `String`.
- Declare typed fields in `@ConfigurationProperties` and register the bean properly.
- Write canonical kebab-case key names, such as `base-uri`, `bind-address`, and `trust-bundle`.
- For HTTP endpoints, prefer `URI` and check scheme/host/absoluteness as required.
- Pick `URL` only when an API or design genuinely requires it; do not equate URL parsing with network readiness.
- For `InetAddress`, consider DNS lookup at binding time; use `String` if keeping an unresolved hostname.
- Never place host and port in the same `InetAddress` field.
- For IPv6, distinguish literal IP syntax from IPv6 host syntax in URIs.
- For resources inside a JAR, use `classpath:` and read via `Resource.getInputStream()`.
- For files mounted outside the JAR, use `file:` and ensure the right working directory or absolute path.
- Never assume a bound `Resource` guarantees the file exists or is readable.
- Do not call `Resource.getFile()` on arbitrary classpath resources.
- Separate parsing, validation, and file/network access into clearly accountable steps.
- Check Config Data precedence if the effective value differs from the base config.
- Avoid logging secrets or loading arbitrary URLs from untrusted sources.
- Test conversion with stable URIs and literal IPs, and test `Resource` with classpath samples or test files.
- Design restart/reload workflows for Config Data changes after startup.

## 25. Conclusion

Spring Boot can convert strings in **externalized configuration** into meaningful Java types, reducing manual parsing and catching many errors early. The four types in this lesson serve distinct purposes:

- `URI` represents a resource identifier and is usually the most convenient choice for HTTP endpoints.
- `URL` serves APIs requiring a protocol-based locator.
- `InetAddress` represents an IP address and can trigger DNS lookups when given hostnames.
- `Resource` is Spring's abstraction for reading content from the classpath, filesystem, or supported sources.

Even when the binder constructs objects successfully, the application still needs **business validation**, I/O and network error handling, authorization, and sound operational rules. Above all, do not confuse URI/URL parsing with network connectivity, do not confuse `Resource` with a physical `File`, and do not confuse an IP address with a complete endpoint carrying scheme, port, and path.

### References

- [Spring Boot Reference — Externalized Configuration and Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework Reference — Resources](https://docs.spring.io/spring-framework/reference/core/resources.html)
- [Spring Framework API — Resource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/Resource.html)
- [Java API — URI](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html)
- [Java API — URL](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URL.html)
- [Java API — InetAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html)
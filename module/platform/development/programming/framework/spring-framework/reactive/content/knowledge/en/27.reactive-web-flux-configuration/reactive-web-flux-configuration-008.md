# Configuring Static Resources and the Resource Processing Chain in Spring WebFlux

## 1. Static Resources in a WebFlux Application

A WebFlux application does not only return JSON from controllers. Applications often need to serve static files such as:

- Frontend HTML, CSS, and JavaScript.
- Images, icons, fonts, and SVG files.
- PDF documents or publicly downloadable files.
- Assets packaged inside a JAR or placed in a dedicated directory on the server.
- Frontend libraries packaged as WebJars.

**Static resources** are pre-stored content served at a URL. When a client requests that URL, the server locates the resource in the configured locations and writes its content to the HTTP response. The resource does not need to be regenerated from business logic on each request.

Spring WebFlux provides static resource serving through:

- **ResourceHandlerRegistry**: registers URL patterns and locations containing resources.
- **ResourceWebHandler**: handles requests matching a pattern, locates the Resource, and writes the response.
- **ResourceResolver**: maps a request path to an actual Resource.
- **ResourceTransformer**: transforms a Resource before writing the response.
- **ResourceUrlProvider**: builds public URLs after applying the resolver chain, such as inserting a content hash into file names.
- **CacheControl** and conditional requests: allow browsers/proxies to reuse downloaded content.

Distinguish two types of caching: HTTP caching used by browsers or proxies according to response headers, and the resource chain's internal cache used to avoid repeating resolve/transform work on the server. These two mechanisms serve different purposes and have different lifecycles.

## 2. Spring Boot WebFlux Defaults

Spring Boot automatically configures a static resource handler when WebFlux is present.

Default classpath directories include:

~~~text
src/main/resources/
├── static/
├── public/
├── resources/
└── META-INF/
    └── resources/
~~~

The directories above are separate locations; you do not need to create all four. A file on the classpath can be accessed via URL under the default mapping:

~~~text
GET /
GET /index.html
GET /css/site.css
GET /images/logo.svg
~~~

By default, static resources are mapped under the pattern /**. Spring Boot uses Spring WebFlux's **ResourceWebHandler** to serve them.

### 2.1. Changing the URL Pattern via application.properties

You can move static resources under a dedicated prefix:

~~~properties
spring.webflux.static-path-pattern=/resources/**
~~~

Then the file:

~~~text
src/main/resources/static/css/site.css
~~~

is served at:

~~~text
GET /resources/css/site.css
~~~

This pattern only changes the URL mapping. It does not move files on the classpath.

### 2.2. Changing Locations via application.properties

You can specify custom locations:

~~~properties
spring.web.resources.static-locations=classpath:/public-assets/,file:/srv/www/
~~~

Spring Boot will use this location list instead of the default locations. If you want to keep the default locations, you must re-declare them in the list.

Example:

~~~properties
spring.web.resources.static-locations=classpath:/static/,classpath:/public/,classpath:/resources/,classpath:/META-INF/resources/
~~~

Each location must be a valid directory. For the filesystem, use a file URI and end with a trailing slash to indicate a directory:

~~~properties
spring.web.resources.static-locations=file:/srv/www/
~~~

Locations are searched in configured order. If multiple locations contain the same relative path, the first location found determines which Resource is served.

### 2.3. WebFlux Does Not Use src/main/webapp

WebFlux does not depend on the Servlet API in the traditional Spring MVC way, so do not rely on src/main/webapp to serve static resources. For Spring Boot WebFlux applications, place content on the classpath or configure an appropriate Resource location.

### 2.4. WebJars

WebJars package frontend libraries inside JARs. Spring Boot supports URLs of the form:

~~~text
/webjars/library-name/version/file
~~~

For example, a library can be served from:

~~~text
/webjars/jquery/3.7.1/jquery.min.js
~~~

Versioned URLs are recommended because they explicitly identify the library version and work well with caching. Versionless URLs can be supported by WebJarsResourceResolver when the org.webjars:webjars-locator-core dependency is on the classpath; this mechanism scans the classpath and can increase startup time.

You can change the WebJars pattern with:

~~~properties
spring.webflux.webjars-path-pattern=/vendor/**
~~~

## 3. Registering Resource Handlers via WebFluxConfigurer

When you need control over URL patterns, locations, cache headers, or the resource chain, implement **WebFluxConfigurer** and override **addResourceHandlers**.

Example:

~~~java
@Configuration
public class StaticResourceConfiguration
        implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(
            ResourceHandlerRegistry registry) {

        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/assets/")
            .setCacheControl(
                CacheControl.maxAge(365, TimeUnit.DAYS)
                    .cachePublic()
            );
    }
}
~~~

Components:

- **addResourceHandler("/assets/**")**: every request matching the /assets/ prefix is routed to this handler.
- **addResourceLocations(...)**: declares the root directories used to locate resources.
- **setCacheControl(...)**: sets Cache-Control for static resource responses.

If the file resides at:

~~~text
src/main/resources/static/assets/css/site.css
~~~

The corresponding URL is:

~~~text
/assets/css/site.css
~~~

The /assets/ prefix of the URL is stripped when resolving relatively inside classpath:/static/assets/.

### 3.1. One Handler with Multiple Locations

Multiple locations can be declared:

~~~java
registry.addResourceHandler("/shared/**")
    .addResourceLocations(
        "classpath:/static/shared/",
        "file:/srv/www/shared/"
    );
~~~

Spring looks up the Resource in location order. This is useful when an application packages default assets inside the JAR and allows supplementing public assets from the filesystem.

Do not add directories containing secrets, configuration, private uploads, or user data to public location lists.

### 3.2. Multiple Handlers with Separate Policies

Different patterns can be registered:

~~~java
@Override
public void addResourceHandlers(
        ResourceHandlerRegistry registry) {

    registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .setCacheControl(
            CacheControl.maxAge(365, TimeUnit.DAYS).cachePublic()
        );

    registry.addResourceHandler("/downloads/**")
        .addResourceLocations("classpath:/static/downloads/")
        .setCacheControl(CacheControl.noCache());
}
~~~

This example shows each handler can use different locations and Cache-Control settings. For data requiring authentication, add proper authorization and scope caching by user identity. A public static URL is not a protection mechanism for private files.

### 3.3. HandlerMapping Order

Resource handlers are registered through ResourceHandlerRegistry and have lower default precedence than regular handler mappings. Specific controller mappings usually take priority over static resource mappings. When patterns overlap, design clear prefixes and avoid overly broad patterns that make business routes ambiguous.

## 4. How Does ResourceWebHandler Process a Request?

**ResourceWebHandler** is the specialized WebHandler for serving static Resources. High-level processing flow:

~~~text
HTTP request
     |
     v
HandlerMapping finds matching pattern
     |
     v
ResourceWebHandler
     |
     v
Extract relative path from handler mapping
     |
     v
Normalize and validate path
     |
     v
ResourceResolver chain
     |
     v
Locate Resource in allowed locations
     |
     v
ResourceTransformer chain
     |
     v
Determine media type and HTTP metadata
     |
     v
ResourceHttpMessageWriter writes response
~~~

The handler uses the path inside the URL pattern to locate the Resource. For example, pattern /assets/** and request /assets/css/site.css produce the relative path css/site.css.

### 4.1. Path Normalization and Resource Checking

ResourceWebHandler normalizes the input path and rejects invalid paths before resolving. Then the resolver looks up the Resource in the configured locations.

The resolved path must remain within the permitted scope. **PathResourceResolver** verifies whether the Resource belongs to the corresponding location or one of the allowed locations. By default, ResourceWebHandler initializes allowed locations to match the handler's location list.

This is an important defense against path traversal. Still, applications must restrict locations to public directories only, keep Spring Framework updated, and avoid writing custom resolvers that bypass safety checks.

### 4.2. ResourceWebHandler and HTTP Responses

After the Resource is resolved and transformed, the handler determines the media type from the file name or media type configuration, then writes the Resource using a message writer.

Static resource handlers support HTTP features such as:

- Content-Type matching the file extension.
- Content-Length when determinable.
- Last-Modified and conditional requests.
- Cache-Control.
- Byte Ranges when the Resource and response meet requirements.
- Content-Encoding when a compressed Resource variant is selected by a resolver.

There is no need to create individual controllers for each CSS file, image, or JavaScript file. ResourceWebHandler handles this job.

## 5. How Do ResourceResolver and ResourceTransformer Differ?

These are the two primary extension points of the resource chain.

| Extension point | Question It Answers | Example |
| --- | --- | --- |
| **ResourceResolver** | Which Resource corresponds to this request path? | PathResourceResolver, VersionResourceResolver, EncodedResourceResolver |
| **ResourceTransformer** | How should the located Resource be transformed before sending? | CssLinkResourceTransformer, custom transformers |

Resolvers handle path mapping and Resource selection. Transformers take an already-resolved Resource and produce the output content/Resource before writing the response.

### 5.1. ResourceResolver

The ResourceResolver interface allows:

- Locating a Resource from a request path.
- Translating internal URLs into public URLs.
- Delegating to the next resolver in the chain.
- Applying versioning, content encoding, or WebJars rules.

A resolver can return Mono<Resource> or Mono<String> in its respective resolve APIs because WebFlux processes asynchronously.

Commonly used built-in resolvers:

| Resolver | Function |
| --- | --- |
| **PathResourceResolver** | Locates relative files in registered locations and enforces boundary checks |
| **VersionResourceResolver** | Resolves versioned URLs and validates content versions |
| **EncodedResourceResolver** | Selects compressed variants matching Accept-Encoding |
| **WebJarsResourceResolver** | Resolves versionless WebJars URLs when locator is present |
| **CachingResourceResolver** | Caches resolution results to avoid repeated Resource lookups |

### 5.2. PathResourceResolver

PathResourceResolver is the foundational resolver, typically placed at the end of the chain because it performs the actual Resource lookup in locations.

It checks:

- The Resource exists.
- The Resource is readable.
- The Resource resides within a valid location or allowed locations.
- The normalized path does not escape the configured scope.

If no custom resolvers are configured, ResourceWebHandler uses PathResourceResolver to find files by relative path.

Do not set overly broad allowed locations. For instance, allowing the entire filesystem root defeats boundary checks.

### 5.3. VersionResourceResolver

VersionResourceResolver adds versions to URLs so browsers can cache content long-term while still receiving new versions when files change.

Two common strategies:

- **ContentVersionStrategy**: computes a content hash, typically MD5, and appends the hash to the file name.
- **FixedVersionStrategy**: prepends an application-supplied fixed version, such as a release version or build identifier.

Example URL with content hash:

~~~text
/assets/css/site-<hash>.css
~~~

If site.css content changes, the hash changes and the public URL changes as well. Browsers treat the new URL as a distinct resource and do not reuse stale cached copies.

Configuration:

~~~java
VersionResourceResolver versionResolver =
    new VersionResourceResolver()
        .addContentVersionStrategy("/**");
~~~

For JavaScript using module loaders, ContentVersionStrategy may be unsuitable because import paths inside modules must stay consistent. In that case, FixedVersionStrategy is often a better fit:

~~~java
VersionResourceResolver versionResolver =
    new VersionResourceResolver()
        .addFixedVersionStrategy(
            "v2026.11",
            "/**/*.js"
        )
        .addContentVersionStrategy(
            "/**/*.css",
            "/**/*.png",
            "/**/*.svg"
        );
~~~

Fixed versions should come from build metadata or release configuration so all assets in the same build use a consistent version.

### 5.4. EncodedResourceResolver

EncodedResourceResolver looks up pre-compressed content variants, such as gzip or Brotli, based on the request's **Accept-Encoding** header.

For example, a directory contains:

~~~text
site.css
site.css.gz
site.css.br
~~~

If the browser sends a compatible Accept-Encoding, the resolver can select the compressed variant instead of the original file. The server must return the appropriate Content-Encoding so the client decompresses it properly.

This resolver is useful when the build pipeline pre-generates compressed assets. It does not compress arbitrary files on the fly if no corresponding variant exists.

### 5.5. WebJarsResourceResolver

WebJarsResourceResolver supports versionless URLs when libraries are packaged as WebJars. It requires the org.webjars:webjars-locator-core dependency to look up versions on the classpath.

Direct versioned URLs are usually more efficient because they avoid classpath scanning at startup. Enable the versionless resolver only when the application genuinely requires that URL style.

## 6. ResourceTransformer and Content Optimization

ResourceTransformer transforms a Resource before the response is written.

Common scenarios:

- Rewriting image/font URLs inside CSS.
- Inserting content hashes into asset links.
- Minifying or normalizing text content.
- Transforming a resource based on build/runtime configuration.

### 6.1. CssLinkResourceTransformer

CSS can reference images, fonts, or other CSS files:

~~~css
@import url("./theme.css");

.logo {
    background-image: url("../images/logo.svg");
}
~~~

When assets are versioned, URLs inside CSS must also point to the corresponding versioned paths. If CSS is renamed while internal links still point to unversioned URLs, browsers may fail to load the right asset or bypass versioned caching.

**CssLinkResourceTransformer** parses links in CSS and uses resource URL resolution to rewrite them to public URLs. This keeps links inside CSS compatible with VersionResourceResolver.

Configuring the transformer:

~~~java
CssLinkResourceTransformer cssTransformer =
    new CssLinkResourceTransformer();
~~~

### 6.2. Custom Transformers

You can implement ResourceTransformer for specific requirements. A transformer receives ServerWebExchange, Resource, and ResourceTransformerChain and returns Mono<Resource>.

When writing a transformer:

- Preserve necessary Resource content and metadata.
- Do not block the event loop with heavy synchronous I/O.
- Do not load entire large files into memory unnecessarily.
- Delegate to the next transformer when no changes are needed.
- Ensure deterministic output if the resource chain has caching enabled.
- Validate source data before writing into the response.

If minified content is needed, it is best generated in the build pipeline when static assets can be prebuilt. Runtime transformers should be used only when serving-time transformation is genuinely required.

## 7. Ordering of the Resolver and Transformer Chain

Resolver order directly determines which Resource is selected.

A common chain when using pre-compressed content and content-based versioning:

~~~text
Request
  |
  v
EncodedResourceResolver
  |
  v
VersionResourceResolver
  |
  v
PathResourceResolver
  |
  v
ResourceTransformer chain
  |
  v
Response writer
~~~

When using both **EncodedResourceResolver** and **VersionResourceResolver** with content-based versioning, register EncodedResourceResolver before VersionResourceResolver. That way, the version hash is computed from the original content rather than being affected by compressed variants.

PathResourceResolver is the final resolver in the chain to perform Resource lookup in locations. When ResourceChainRegistration auto-configures the resolver chain, Spring appends PathResourceResolver as the last resolver if needed.

Example:

~~~java
registry.addResourceHandler("/assets/**")
    .addResourceLocations("classpath:/static/assets/")
    .resourceChain(true)
    .addResolver(new EncodedResourceResolver())
    .addResolver(new VersionResourceResolver().addContentVersionStrategy("/**"))
    .addTransformer(new CssLinkResourceTransformer());
~~~

Do not reverse the order of those two resolvers when versions are computed from content and compressed files exist.

### 7.1. Resolvers and Transformers Can Delegate

A resolver can invoke the next resolver via ResourceResolverChain. A transformer can invoke the next transformer via ResourceTransformerChain.

Delegation allows composing multiple independent strategies. For example, a versioning resolver can handle the version segment first and let PathResourceResolver locate the actual file. A CSS transformer can resolve referenced links through the configured resolver chain.

Do not write a resolver that terminates the chain prematurely when it has not found a Resource if a subsequent resolver might still handle the request. Follow the chain contract.

## 8. Configuring the Resource Chain in ResourceHandlerRegistry

To enable the resource chain, use **resourceChain(boolean cacheResources)** on ResourceHandlerRegistration.

Example:

~~~java
registry.addResourceHandler("/assets/**")
    .addResourceLocations("classpath:/static/assets/")
    .resourceChain(true)
    .addResolver(
        new VersionResourceResolver()
            .addContentVersionStrategy("/**")
    )
    .addTransformer(new CssLinkResourceTransformer());
~~~

Passing true enables internal caching for resolution/transformation results. This is useful in production because the same static assets are requested repeatedly.

In development, you can use:

~~~java
.resourceChain(false)
~~~

to avoid holding stale resolve/transform results while file contents are changing continuously.

### 8.1. Default Resource Chain Cache

When caching is enabled without passing a custom cache, Spring uses an in-memory cache for resolvers/transformers. Resources are typically tied to the local process's filesystem or classpath, so Resource objects should not by default be placed into a distributed cache.

If the application passes a custom Cache into resourceChain(true, cache), carefully manage keys, namespaces, eviction, and sharing scope.

### 8.2. Cache-Control Is Not the Resource-Chain Cache

The following two settings do two different things:

~~~java
.setCacheControl(
    CacheControl.maxAge(365, TimeUnit.DAYS).cachePublic()
)
~~~

Sets the HTTP response header so browsers or proxies know how long the response may be reused.

~~~java
.resourceChain(true)
~~~

Enables the server's internal cache for the resolve and transform steps.

You can enable HTTP caching while disabling the resource-chain cache, or vice versa. Do not infer from one setting that the other is also enabled.

### 8.3. Use Separate Caches per Security Boundary

If an application has a public resource handler and a resource handler requiring authentication, do not share a custom cache between those two handlers.

Example:
- Handler /assets/** serves public content.
- Handler /private-assets/** serves user- or tenant-specific content.

A shared cache can cause a Resource resolved for one scope to be reused in another scope if cache keys and isolation policies are inadequate. Isolate caches per handler/security boundary and prefer controllers/services with explicit authorization for private files.

## 9. HTTP Caching for Static Resources

HTTP caching helps browsers and proxies avoid re-downloading unchanged content. Common headers:

| Header | Role |
| --- | --- |
| **Cache-Control** | Specifies how long a cache may store and reuse a response |
| **Last-Modified** | Timestamp when the Resource was last modified |
| **ETag** | Validator representing a content version |
| **If-Modified-Since** | Client asks whether the Resource changed after a timestamp |
| **If-None-Match** | Client asks whether the current ETag still matches |

### 9.1. Cache-Control

Example caching for one hour:

~~~java
CacheControl.maxAge(1, TimeUnit.HOURS)
~~~

Example disallowing cache storage:

~~~java
CacheControl.noStore()
~~~

Example allowing public caching for one year:

~~~java
CacheControl.maxAge(365, TimeUnit.DAYS)
    .cachePublic()
~~~

Choose policies based on content characteristics:

| Content | Suggested Policy |
| --- | --- |
| Asset with content hash in URL | Long max-age, public, optionally immutable |
| File without version in URL | Short max-age or no-cache to revalidate |
| Private file requiring authorization | private or no-store depending on security requirements |
| Frequently changing document | Short max-age and appropriate validator |

Do not set public on private resources or access-controlled content just to make it faster.

### 9.2. Last-Modified and 304 Not Modified

ResourceWebHandler evaluates Last-Modified when possible. When a client sends If-Modified-Since and the content has not changed, the server can return:

~~~http
HTTP/1.1 304 Not Modified
~~~

A 304 response does not resend the body. The browser uses its existing cached copy.

This saves bandwidth for files that remain unchanged at the same URL.

### 9.3. ETag

An ETag is a validator representing a version of content. Clients send If-None-Match to check whether content has changed.

ResourceHandlerRegistration can configure an ETag generator in Spring versions supporting that API. The generator should produce stable values for a given representation without overly expensive per-request computation.

Do not generate ETags from metadata that changes independently of content if the goal is detecting file changes. For assets with content hashes in URLs, the versioned URL already serves as a strong version identifier; ETags can supplement conditional requests.

### 9.4. Coordinating Cache-Control and Content-Hash URLs

An asset has URL:

~~~text
/assets/site-a1b2c3....css
~~~

If content changes, the URL is generated from the new hash. Because the URL changes, browsers can cache the old URL for a long time without risking stale content at the same address.

This is why versioned assets can use a long max-age. With unversioned URLs, caches need to revalidate more frequently because content can change while the address stays the same.

## 10. ResourceUrlProvider in WebFlux

WebFlux provides **ResourceUrlProvider** to build public URLs through the resolver chain. This lets you obtain versioned URLs without computing hashes or concatenating file names manually.

Key reactive API:

~~~java
Mono<String> getForUriString(
    String uriString,
    ServerWebExchange exchange
)
~~~

Controller example:

~~~java
@RestController
public class AssetUrlController {

    private final ResourceUrlProvider resourceUrlProvider;

    public AssetUrlController(
            ResourceUrlProvider resourceUrlProvider) {
        this.resourceUrlProvider = resourceUrlProvider;
    }

    @GetMapping(
        value = "/asset-url",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> assetUrl(ServerWebExchange exchange) {
        return resourceUrlProvider.getForUriString(
            "/assets/site.css",
            exchange
        );
    }
}
~~~

If site.css has content versioning, the Mono can return a URL like:

~~~text
/assets/site-<content-hash>.css
~~~

This URL is produced by the resolver chain. The actual hash depends on file content, so do not hardcode it in HTML or tests.

### 10.1. WebFlux Does Not Automatically Rewrite URLs in Every View

Unlike some capabilities in Spring MVC, WebFlux does not have transparent URL rewriting across all view technologies through a non-blocking resolver chain.

Therefore, when versioned URLs are needed in HTML or JSON responses, the application can call ResourceUrlProvider directly and compose the Mono into the active pipeline.

Do not call block() in a WebFlux controller or on the event loop just to obtain a URL. Return the Mono and continue processing reactively.

### 10.2. CssLinkResourceTransformer and ResourceUrlProvider

CssLinkResourceTransformer can use ResourceUrlProvider to rewrite links in CSS. For example, site.css references theme.css or logo.svg; the transformer can generate public URLs matching the version strategy.

As a result, versioning does not stop at the main CSS file, but also applies to resources referenced by CSS.

## 11. Complete Example: Spring Boot 4.1.2, Java 17, and the Resource Chain

This example configures a Spring WebFlux application to:

- Serve assets from classpath:/static/assets/.
- Generate versioned URLs based on content hashes.
- Use CssLinkResourceTransformer for links inside CSS.
- Use ResourceUrlProvider to return public URLs.
- Enable internal caching for the resource chain.
- Set a long Cache-Control for versioned assets.

The example uses **Spring Boot 4.1.2**, **Spring Framework 7.0.10**, and **Java 17+**. Spring Boot 4.1.2 manages Spring Framework 7.0.10, which is beyond the static-resource fix milestones mentioned in the security section.

### 11.1. Project Structure

~~~text
webflux-static-chain-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/staticchain/
    │   │       ├── StaticResourcesApplication.java
    │   │       ├── StaticResourceConfiguration.java
    │   │       └── AssetUrlController.java
    │   └── resources/
    │       ├── application.properties
    │       └── static/
    │           └── assets/
    │               ├── site.css
    │               ├── theme.css
    │               └── logo.svg
    └── test/
        └── java/
            └── com/example/staticchain/
                └── StaticResourceIntegrationTest.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-static-chain-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

No need to declare a separate Spring Framework version because Spring Boot dependency management supplies a compatible version.

### 11.3. StaticResourcesApplication.java

~~~java
package com.example.staticchain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StaticResourcesApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            StaticResourcesApplication.class,
            args
        );
    }
}
~~~

### 11.4. StaticResourceConfiguration.java

~~~java
package com.example.staticchain;

import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.resource.CssLinkResourceTransformer;
import org.springframework.web.reactive.resource.VersionResourceResolver;

@Configuration
public class StaticResourceConfiguration
        implements WebFluxConfigurer {

    @Override
    public void addResourceHandlers(
            ResourceHandlerRegistry registry) {

        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/assets/")
            .setCacheControl(
                CacheControl.maxAge(365, TimeUnit.DAYS)
                    .cachePublic()
            )
            .resourceChain(true)
            .addResolver(
                new VersionResourceResolver()
                    .addContentVersionStrategy("/**")
            )
            .addTransformer(
                new CssLinkResourceTransformer()
            );
    }
}
~~~

Explanation:

1. Requests starting with /assets/ are routed to the resource handler.
2. Files are located in classpath:/static/assets/.
3. VersionResourceResolver computes a content hash and inserts it into the public URL name.
4. CssLinkResourceTransformer rewrites asset links inside CSS when needed.
5. resourceChain(true) enables internal caching of resolver/transformer results.
6. Cache-Control lets browsers and proxies cache public assets for a long duration.

This example does not enable EncodedResourceResolver because the project does not supply .gz or .br files. If your build pipeline produces compressed variants, you can add EncodedResourceResolver before VersionResourceResolver.

### 11.5. AssetUrlController.java

~~~java
package com.example.staticchain;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.resource.ResourceUrlProvider;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class AssetUrlController {

    private final ResourceUrlProvider resourceUrlProvider;

    public AssetUrlController(
            ResourceUrlProvider resourceUrlProvider) {
        this.resourceUrlProvider = resourceUrlProvider;
    }

    @GetMapping(
        value = "/asset-url",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> assetUrl(ServerWebExchange exchange) {
        return resourceUrlProvider.getForUriString(
                "/assets/site.css",
                exchange
            )
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "Static asset not found"
                )
            ));
    }
}
~~~

The controller returns Mono<String>. ResourceUrlProvider runs through the resolver chain and produces the versioned URL. If the Resource does not exist or cannot be resolved, the endpoint returns a 404 error.

### 11.6. application.properties

~~~properties
spring.application.name=webflux-static-chain-demo
server.port=8080
~~~

No need to configure static-path-pattern manually because the example registers the /assets/** mapping via WebFluxConfigurer.

### 11.7. site.css

Create the file src/main/resources/static/assets/site.css:

~~~css
@import url("./theme.css");

body {
    font-family: Arial, sans-serif;
    background: #f5f7fa;
}

.logo {
    width: 96px;
    height: 96px;
    background-image: url("./logo.svg");
}
~~~

### 11.8. theme.css

Create the file src/main/resources/static/assets/theme.css:

~~~css
:root {
    --brand-color: #1769aa;
}

h1 {
    color: var(--brand-color);
}
~~~

### 11.9. logo.svg

Create the file src/main/resources/static/assets/logo.svg:

~~~xml
<svg xmlns="http://www.w3.org/2000/svg"
     width="96"
     height="96"
     viewBox="0 0 96 96">
    <circle cx="48" cy="48" r="44" fill="#1769aa"/>
    <path d="M25 50 L42 67 L73 31"
          fill="none"
          stroke="#ffffff"
          stroke-width="8"
          stroke-linecap="round"
          stroke-linejoin="round"/>
</svg>
~~~

The CSS transformer can process CSS links referencing theme.css and logo.svg to produce URLs matching the resolver chain.

### 11.10. Testing with WebTestClient

File StaticResourceIntegrationTest.java:

~~~java
package com.example.staticchain;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class StaticResourceIntegrationTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();
    }

    @Test
    void resolvesVersionedUrlAndServesCss() {
        String assetPath = client.get()
            .uri("/asset-url")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
            .expectBody(String.class)
            .returnResult()
            .getResponseBody();

        assertNotNull(assetPath);
        assertTrue(
            assetPath.matches(
                "/assets/site-[0-9a-f]{32}\\.css"
            )
        );

        client.get()
            .uri(assetPath)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.valueOf("text/css"))
            .expectHeader()
                .exists("Cache-Control")
            .expectBody(String.class)
            .value(body ->
                assertTrue(body.contains("font-family"))
            );
    }
}
~~~

The test performs two steps:

1. Calls /asset-url to obtain the content-hashed URL generated by ResourceUrlProvider.
2. Uses that URL to fetch the CSS and verifies status 200, CSS media type, Cache-Control, and expected content.

Because the hash is computed from file content, the test asserts the pattern rather than hardcoding a fixed hash.

### 11.11. Running the Application

Requires JDK 17+ and Maven compatible with Spring Boot 4.1.2:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Get the versioned URL:

~~~bash
curl -i http://localhost:8080/asset-url
~~~

The returned body has the form:

~~~text
/assets/site-<content-hash>.css
~~~

This is an illustrative format; the actual hash is computed from site.css content.

You can fetch the path from the endpoint and use it in the next request:

~~~bash
ASSET_PATH=$(curl -fsS http://localhost:8080/asset-url)
curl -i "http://localhost:8080$ASSET_PATH"
~~~

The expected response has status 200, Content-Type text/css, and the appropriate Cache-Control. When site.css content changes, the URL returned by /asset-url changes according to the content hash.

Stop the application with Ctrl+C.

## 12. Example Configuring Versioning and Encoded Resources

If the build system pre-generates compressed assets, you can extend the resource chain:

~~~java
registry.addResourceHandler("/assets/**")
    .addResourceLocations("classpath:/static/assets/")
    .setCacheControl(
        CacheControl.maxAge(365, TimeUnit.DAYS).cachePublic()
    )
    .resourceChain(true)
    .addResolver(new EncodedResourceResolver())
    .addResolver(
        new VersionResourceResolver()
            .addContentVersionStrategy("/**/*.css", "/**/*.svg")
            .addFixedVersionStrategy(
                "v2026.11",
                "/**/*.js"
            )
    )
    .addTransformer(new CssLinkResourceTransformer());
~~~

In this chain:

- EncodedResourceResolver is placed first to select the appropriate encoding variant.
- VersionResourceResolver handles URL versions.
- Content-based versioning is applied to CSS/SVG.
- Fixed version is applied to JavaScript in the example.
- CssLinkResourceTransformer rewrites CSS links.

Only configure the encoded resolver when corresponding compressed files exist and you have verified response Content-Encoding, Vary, and actual content with a browser/client.

## 13. Caching and Operating in Production

### 13.1. Separate Policies by Resource Type

Do not apply a very long max-age to all static URLs if URLs are unversioned. Choose policies based on how the application updates content.

For versioned URLs, a long max-age is reasonable because new content creates new URLs. For fixed URLs, use short cache durations or revalidation so clients detect changes.

### 13.2. Use Internal Caching Deliberately

The resource chain cache reduces resolve and transform work. However, if files change while the application is running, the cache can retain stale results until evicted or the application restarts.

In production, static assets are usually packaged immutably with the build, so internal caching is appropriate. In development, disable the chain cache or restart when assets change.

### 13.3. Do Not Share Caches Between Public and Private

Spring Framework has previously issued advisories regarding sharing caches across multiple resource handlers with different locations and authentication policies. If a public resource is resolved first and the cache is shared with a protected handler, protected content could be exposed in certain configurations.

Do the following:

- Use separate caches for each security boundary.
- Do not share resolver caches between public handlers and handlers requiring authentication.
- Enforce authorization before serving private content.
- Avoid exposing private documents as public static URLs.
- Use Cache-Control appropriate for sensitive content.

### 13.4. Monitoring

Useful metrics:

- Static resource request counts by URL pattern.
- Rates of 200, 304, and 404 responses.
- Resource resolution latency.
- Resource chain cache hit/miss ratios if instrumented.
- File read errors and filesystem permission errors.
- Rate of requests with Accept-Encoding and selected content encodings.
- Frequency of clients requesting nonexistent versioned URLs.

Do not log full file contents or private data when debugging static resources.

## 14. Security: Path Traversal and Related Advisories

Static resource handlers are a security boundary. If locations are overly broad or resolvers are misconfigured, request paths can be abused to access files outside the intended scope.

### 14.1. Serve Only Public Directories

Appropriate location example:

~~~java
.addResourceLocations("file:/srv/www/public/")
~~~

Do not use:

~~~java
.addResourceLocations("file:/")
~~~

or directories containing all application data, secrets, config files, or private uploads.

The application process should only have read permissions on the exact directory to be served. Restricting filesystem permissions limits blast radius if an application-layer bug occurs.

### 14.2. Do Not Concatenate Request Paths into Filesystem Paths Yourself

Avoid writing controllers like:

~~~java
Path path = Paths.get("/srv/www/" + requestPath);
Resource resource = new FileSystemResource(path);
~~~

This carries risks of path traversal, symlink escapes, and discrepancies across path normalization styles.

If you must serve dynamic files by ID, look up metadata in a service, verify authorization, constrain the root path, and construct the Resource from a validated path. Never let clients supply arbitrary filesystem paths.

### 14.3. CVE-2024-38816: Functional Static Resources

Spring published CVE-2024-38816 affecting WebFlux.fn and WebMvc.fn when using RouterFunctions to serve static resources alongside FileSystemResource locations in affected versions.

Spring Framework versions 6.1.0 through 6.1.12 are affected; the fix in the 6.1 branch is 6.1.13. When using functional endpoints to serve filesystem resources, use a patched version and review security configuration.

### 14.4. CVE-2026-22741: Encoded Resource Cache Poisoning

This advisory concerns resource chain configurations with caching enabled alongside EncodedResourceResolver in affected versions. When the cache is cold, a request can cause the cache to store an incorrect encoding variant, affecting assets served to other clients.

Published OSS fixes include Spring Framework 7.0.7 and 6.2.18. Newer patch releases already include this fix.

### 14.5. CVE-2026-41841: Protected Resource Disclosure via Shared Cache

This advisory describes a scenario with multiple resource handlers using different locations where at least one handler requires authentication, yet handlers share a cache. A public Resource with the same name can be resolved first and cached, enabling disclosure of protected content in affected configurations.

Published OSS fixes include Spring Framework 7.0.8 and 6.2.19. The design defense remains isolating caches per security boundary and never sharing caches between public and private handlers.

### 14.6. CVE-2026-41843: Path Traversal via Versioned Filesystem Resources

This advisory concerns static resources served from the filesystem together with versioned resource support. In affected versions, crafted requests can resolve files outside configured locations when an attacker knows or guesses required metadata.

Published OSS fixes include Spring Framework 7.0.8 and 6.2.19. Version 6.1.28 is available only in Enterprise Support. Upgrade to the latest patch of a supported branch.

### 14.7. Versions Used in the Example

The example uses Spring Boot **4.1.2**, which manages Spring Framework **7.0.10** and requires Java 17+. This Framework version is newer than the 7.0.8 fix milestones noted above.

If an application is on Spring Framework 6.2.x, at minimum version 6.2.19 is needed for the 2026 advisories above; prefer upgrading along supported Spring branches. The 6.1 branch has reached end of OSS support and 6.1.28 is Enterprise Support.

Do not treat upgrading versions as an excuse to skip path validation, location boundaries, or cache isolation. Always inspect the application's actual dependency tree because BOMs, overrides, or transitive dependencies can pull in a different Framework version than expected.

## 15. RouterFunctions.resources and ResourceHandlerRegistry

WebFlux can serve static resources using functional routing via RouterFunctions.resources(...). However, for standard static resources, **ResourceHandlerRegistry** is usually easier to configure and integrate.

Comparison:

| Approach | Appropriate When |
| --- | --- |
| **ResourceHandlerRegistry** | Serving static assets by URL pattern and location, needing resolver/transformer/cache chains |
| **RouterFunctions.resources** | Application uses functional routing and needs resource routes attached to RouterFunction |
| **Controller returning Resource** | Resources are determined by business logic or per-request authorization |

If using RouterFunctions.resources with FileSystemResource, pay particular attention to CVE-2024-38816 and patched Framework versions. Do not build a custom functional resource handler to replace built-in boundary checks without reason.

## 16. Common Pitfalls and Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Request /assets/site.css returns 404 | URL pattern or location mismatch | Check addResourceHandler, addResourceLocations, and classpath file location |
| Changed static-path-pattern but old URL stops working | Mapping moved to the new prefix | Use URLs matching the new pattern |
| Set static-locations and lost files in /static | Property replaces the default location list | Re-declare every needed location |
| Filesystem file not found | Location missing file URI or not pointing to a directory | Use file:/directory-path/ and verify read permissions |
| Same-named file returned from another location | Multiple locations searched in order | Order locations and avoid unintended filename collisions |
| Versioned URL fails to resolve | Hash in URL does not match current content | Generate URLs with ResourceUrlProvider; do not hardcode hashes |
| CSS still uses old asset URLs | CssLinkResourceTransformer not configured | Add transformer and check relative links in CSS |
| Version hash changes per compressed file | EncodedResourceResolver placed in wrong position | Place EncodedResourceResolver before VersionResourceResolver |
| Browser still displays stale CSS | Unversioned URL and overly long Cache-Control | Use content hashes or lower max-age/revalidate |
| File changed but resource chain still returns old copy | Internal cache holds resolve/transform result | Disable cache in development or restart/evict per policy |
| Static handler serves private file | Public location contains protected data or authorization missing | Restrict locations and use an authorized endpoint |
| CSS links are not versioned | Missing CssLinkResourceTransformer or resolver mapping mismatch | Check transformer and path patterns |
| Versionless WebJars URL returns 404 | Missing webjars-locator-core | Use versioned URLs or add locator if truly needed |
| Versioned URL names incompatible with JS module loader | Content hash used for module imports | Use FixedVersionStrategy or build-time manifest |
| Public cache retains personal content | Inappropriate cache policy | Use private/no-store and enforce authentication |
| Path traversal via filesystem resource | Overly broad location, unsafe custom resolver, or old Framework | Restrict root, use standard resolvers, and apply security patches |
| Protected resource leaked via cache | Cache shared between public/private handlers | Isolate caches per security boundary |
| Static response lacks 304 | Missing validator or conditional request setup | Check Last-Modified, ETag, If-Modified-Since, and If-None-Match |
| Wrong compressed asset selected | Inconsistent resolver, cache, or file variants | Check Accept-Encoding, Content-Encoding, and resolver order |
| /assets/** URL collides with API route | Overly broad pattern or ambiguous route | Use separate prefixes for API and static resources |

## 17. Pre-Deployment Checklist

- Are static resources placed inside intentionally public locations?
- Are URL patterns clear and free of overlap with business routes?
- Are locations ordered appropriately?
- Are filesystem root or directories containing secrets not exposed?
- Is ResourceHandlerRegistry used appropriately for the requirements?
- Does PathResourceResolver preserve location boundaries?
- Is the ResourceResolver chain in the proper order?
- Is EncodedResourceResolver placed before VersionResourceResolver when using content-based versioning?
- Is CssLinkResourceTransformer added if CSS contains links needing versioning?
- Is ResourceUrlProvider used to generate versioned URLs?
- Does ContentVersionStrategy fit the asset types?
- Do JavaScript module loaders need FixedVersionStrategy?
- Does Cache-Control match public/private visibility and content mutability?
- Is the resource-chain cache appropriate for the environment?
- Are caches isolated across security boundaries?
- Have Last-Modified/ETag/conditional requests been tested?
- Are versioned WebJars URLs preferred?
- Is Spring Framework updated with security patches?
- Are there integration tests for URL resolution and Resource content?
- Are path traversal and cache isolation tested in apps with filesystem/private resources?
- Are 404, 304, cache hit/miss, and file read errors monitored?

## 18. Practice Exercises

**Exercise 1 — Default static resources:** Place index.html and css/site.css in classpath:/static. Run the application and access them directly via browser/curl.

**Exercise 2 — Custom pattern:** Use spring.webflux.static-path-pattern to move URLs from /** to /resources/**. Verify the new URL.

**Exercise 3 — Custom locations:** Configure classpath:/public-assets/ and file:/srv/www/. Check search order when both locations contain a file with the same name.

**Exercise 4 — ResourceHandlerRegistry:** Create a WebFluxConfigurer and register /assets/**. Verify files are served from the expected classpath location.

**Exercise 5 — PathResourceResolver:** Send a request with a path traversal pattern. Verify Resources outside allowed locations are not returned.

**Exercise 6 — Content versioning:** Configure VersionResourceResolver with ContentVersionStrategy. Use ResourceUrlProvider to get the hashed URL and fetch the file.

**Exercise 7 — Fixed versioning:** Configure FixedVersionStrategy for JavaScript modules. Verify URLs have the release version prefix.

**Exercise 8 — CSS transformer:** Create CSS referencing theme.css and logo.svg. Add CssLinkResourceTransformer and observe rewritten links.

**Exercise 9 — Encoded resources:** Create site.css.gz and configure EncodedResourceResolver before VersionResourceResolver. Send Accept-Encoding: gzip and inspect Content-Encoding.

**Exercise 10 — Cache-Control:** Configure short max-age for unversioned URLs and long max-age for content-hashed URLs. Compare response headers.

**Exercise 11 — Last-Modified:** Send an initial request to obtain Last-Modified, then send If-Modified-Since. Verify a 304 response when the file is unchanged.

**Exercise 12 — Resource-chain cache:** Run with resourceChain(true), modify a file in development, and observe caching. Try resourceChain(false).

**Exercise 13 — ResourceUrlProvider:** Create an endpoint returning Mono<String> from getForUriString and use the resulting URL in HTML or JSON responses.

**Exercise 14 — WebJars:** Add a WebJar, access its versioned URL, and compare with a versionless URL when webjars-locator-core is present.

**Exercise 15 — Cache isolation:** Create two public/private resource handlers in a test application. Verify caches are not shared and protected resources cannot be retrieved via the public mapping.

**Exercise 16 — Security upgrade:** Inspect the dependency tree to verify the Spring Framework version in use is on or above the patched releases for the static-resource advisories.

## 19. Key Takeaways

Spring WebFlux serves static resources using **ResourceWebHandler**. **ResourceHandlerRegistry** registers URL patterns and locations; **ResourceResolver** locates Resources; **ResourceTransformer** transforms Resources before responses are written.

**PathResourceResolver** is the foundational resolver, verifying that Resources reside in permitted locations. **VersionResourceResolver** generates URLs with content hashes or fixed versions. **EncodedResourceResolver** selects compressed variants by Accept-Encoding. **CssLinkResourceTransformer** rewrites links inside CSS. **ResourceUrlProvider** builds public URLs using the resolver chain.

**Cache-Control** governs browser/proxy caching; **resourceChain(true)** enables internal resolve/transform caching. With content versioning, assets can be cached long-term because changing content produces a new URL. When combining encoded resources and versioning, place EncodedResourceResolver before VersionResourceResolver. Never share caches between public and protected resource handlers.

Restrict locations, enforce path boundaries, keep Spring Framework updated, and check advisories CVE-2024-38816, CVE-2026-22741, CVE-2026-41841, and CVE-2026-41843 before deploying a static-resource chain.

## 20. References

- Spring Framework Reference — WebFlux Configuration, Static Resources: https://docs.spring.io/spring/reference/6.2/web/webflux/config.html
- Spring Framework API — ResourceHandlerRegistry: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/config/ResourceHandlerRegistry.html
- Spring Framework API — ResourceHandlerRegistration: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/config/ResourceHandlerRegistration.html
- Spring Framework API — ResourceWebHandler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/ResourceWebHandler.html
- Spring Framework API — ResourceResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/ResourceResolver.html
- Spring Framework API — PathResourceResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/PathResourceResolver.html
- Spring Framework API — VersionResourceResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/VersionResourceResolver.html
- Spring Framework API — EncodedResourceResolver: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/EncodedResourceResolver.html
- Spring Framework API — CssLinkResourceTransformer: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/CssLinkResourceTransformer.html
- Spring Framework API — ResourceUrlProvider: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/resource/ResourceUrlProvider.html
- Spring Framework Reference — WebFlux HTTP Caching: https://docs.spring.io/spring/reference/6.2/web/webflux/caching.html
- Spring Boot Reference — Reactive Web Applications / Static Content: https://docs.spring.io/spring-boot/4.1/reference/web/reactive.html
- Spring Security Advisory — CVE-2024-38816: https://spring.io/security/cve-2024-38816/
- Spring Security Advisory — CVE-2026-22741: https://spring.io/security/cve-2026-22741/
- Spring Security Advisory — CVE-2026-41841: https://spring.io/security/cve-2026-41841/
- Spring Security Advisory — CVE-2026-41843: https://spring.io/security/cve-2026-41843/
- Spring Boot 4.1.2 Release: https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/
- RFC 9111 — HTTP Caching: https://www.rfc-editor.org/rfc/rfc9111.html

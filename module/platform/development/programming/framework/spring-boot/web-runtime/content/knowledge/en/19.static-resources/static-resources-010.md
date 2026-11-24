# Preventing path traversal and exposing only approved directories in Spring Boot

## 1. Objectives and security model

A Spring Boot application can serve CSS, JavaScript, images, fonts, public documents, and many other static resources. A security vulnerability arises when an application lets a URL or user input determine the file read path without strictly confining it to an allowed scope. An attacker can attempt **path traversal (directory traversal)** to request files outside the public directory, such as configuration files, secret keys, or internal data.

After this lesson, you will be able to:

1. Distinguish a **public URL** from an **actual file path** and understand how traversal moves across URL decoding, path normalization, and resource resolution layers.
2. Use standard Spring MVC configuration to publish only resources inside **one approved directory**, rather than manually joining paths from HTTP parameters.
3. Recognize risk surfaces: default classpath locations, overly broad mappings, file-system resources, symbolic links, reverse proxies, manual file-reading controllers, and unpatched Spring Framework versions.
4. Write a Java 17+ Spring Boot application and test that **permitted files are readable while files outside the permitted directory are denied**.
5. Distinguish path confinement from **authentication, authorization, and operating system file permissions**.

**Principle:** define the set of public resources on the server side; map a specific URL prefix to a specific public directory; never accept arbitrary absolute/relative paths from clients to construct returned resources.

## 2. What is path traversal?

Suppose the application should only serve files inside `public-assets/`:

```text
application
├─ public-assets/
│  ├─ logo.svg
│  └─ css/site.css
└─ internal/
   ├─ config-private.txt
   └─ customer-data.csv
```

Valid request: `GET /assets/logo.svg` → resource `public-assets/logo.svg`.

Dangerous request, if an endpoint joins strings without validation: `GET /assets/../internal/config-private.txt`. The `..` segment denotes the **parent directory** when interpreted against a filesystem. If an application concatenates URL strings into a filesystem path without proper checks, normalization can point the path at `internal/config-private.txt`.

Here is an example of a bug that can occur in a hand-written controller:

```java
// INSECURE EXAMPLE: do not use to serve files.
Path file = Path.of("/srv/app/public-assets")
    .resolve(userSuppliedPath);
return Files.readAllBytes(file);
```

This snippet illustrates only the root cause, not a standalone program. `userSuppliedPath` is controlled by the request; `resolve` **does not inherently guarantee** the resulting file remains inside the root. Likewise, an absolute path string can cause `resolve` to discard the root entirely depending on OS and path format.

Variants to include in your threat model:

- Parent segments: `../`, `../../`; on Windows also account for backslashes `\`.
- URL encoding of dots or separators, e.g., `%2e%2e%2f`; these may be interpreted differently across proxies, servlet containers, and applications.
- **Multiple decoding passes**: data decoded once by a proxy and decoded again in custom code will be interpreted differently.
- Absolute paths, Windows drive letters, UNC paths, or paths with alternative separator characters.
- **Symbolic links** inside the public folder pointing to files outside the folder.
- Misconfigured handlers/resource resolvers, or framework dependencies containing disclosed vulnerabilities.

No single `replace("../", "")`, simple regex, or “starts with root string” check is an adequate defense.

## 3. Understanding Spring Boot's default static resource mechanism

In **Spring Boot MVC** with `spring-boot-starter-web`, Boot typically serves static assets from the following classpath directories:

- `classpath:/static/`
- `classpath:/public/`
- `classpath:/resources/`
- `classpath:/META-INF/resources/`

In Servlet applications, there is also the **`ServletContext` root** resource source. The default static resource mapping is usually `/**`. Spring MVC uses `ResourceHttpRequestHandler`; Spring WebFlux uses `ResourceWebHandler`. These handlers rely on the framework's resource resolver mechanism, which checks that resolved resources stay within configured locations.

For instance, `src/main/resources/static/css/app.css` typically maps to `/css/app.css`. You do not need to write a controller like `@GetMapping("/{path}")` to read files by request parameter.

However, **“Spring Boot serves them out of the box” does not mean every file in the project is public**; only resources under sources configured for the static handler should be treated as public. Conversely, any sensitive file mistakenly placed inside `static/`, `public/`, or a publicly mapped folder can be fetched without any traversal at all.

Two useful properties in Spring MVC:

```properties
# Change the URL pattern of the default static resource configuration:
spring.mvc.static-path-pattern=/assets/**

# Replace the default locations with a chosen location:
spring.web.resources.static-locations=classpath:/public-assets/
```

This is a simple configuration when you want to change the URL prefix and asset source. However, in Servlet apps, Spring Boot applies rules adding **`ServletContext` root** resources; because this lesson aims for a **strictly controlled** public area, the main example below disables automatic static mappings and registers a single explicit resource handler.

**Do not confuse:**

- `spring.mvc.static-path-pattern` changes the mapped URLs, **not** disk file protections.
- `spring.web.resources.static-locations` selects file/classpath sources; never point it at the project root, a home directory, paths containing configs, or an unvetted upload folder.
- `spring.web.resources.add-mappings=false` disables Spring Boot's auto-added static resource mappings; it does not automatically make arbitrary custom handlers safe.

## 4. Recommended approach: a single URL prefix for a public classpath directory

For assets shipped with a release, an easily auditable choice is placing them in a **dedicated directory containing only public content**, such as `src/main/resources/public-assets/`, and registering **one** explicit mapping `/assets/**` to `classpath:/public-assets/`.

Diagram:

```text
HTTP GET /assets/logo.svg
             |
             v
Spring MVC ResourceHttpRequestHandler
             |
             v
classpath:/public-assets/logo.svg  ---> 200 (if file exists)

HTTP GET /assets/../internal/example.txt
             |
             v
URL normalization / security checks / ResourceHandler
             |
             v
Must not return content outside the public area ---> 4xx
```

Internal resources must sit **outside** locations the handler is allowed to serve; the public directory must contain no sensitive data.

### 4.1. Sample project structure

Create a Java **17+**-compatible Spring Boot project with the **Spring Web** (`spring-boot-starter-web`) dependency. Use a supported Spring Boot version incorporating recent Spring Framework security patches.

```text
src/
├─ main/
│  ├─ java/com/example/demo/
│  │  ├─ StaticAssetsApplication.java
│  │  └─ StaticAssetsConfiguration.java
│  └─ resources/
│     ├─ application.properties
│     ├─ public-assets/
│     │  └─ hello.txt
│     └─ internal-demo/
│        └─ marker.txt
└─ test/
   └─ java/com/example/demo/
      └─ StaticAssetsApplicationTest.java
```

**`internal-demo/marker.txt` is only a dummy fixture** illustrating a file outside the public area; it holds no real secrets. In real applications, never bundle secrets or sensitive data on the classpath and in repositories merely assuming they “look private”.

### 4.2. Configuration and code files

**`src/main/resources/application.properties`**

```properties
server.port=8080

# Disable static resource handlers added automatically by Boot.
spring.web.resources.add-mappings=false
```

**`src/main/java/com/example/demo/StaticAssetsApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StaticAssetsApplication {
    public static void main(String[] args) {
        SpringApplication.run(StaticAssetsApplication.class, args);
    }
}
```

**`src/main/java/com/example/demo/StaticAssetsConfiguration.java`**

```java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class StaticAssetsConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/public-assets/");
    }
}
```

**`src/main/resources/public-assets/hello.txt`**

```text
PUBLIC_ASSET
```

**`src/main/resources/internal-demo/marker.txt`**

```text
NOT_FOR_HTTP
```

Key points to understand:

1. `spring.web.resources.add-mappings=false` prevents Boot from adding overly broad default static mappings; handlers defined via `WebMvcConfigurer` remain active in Spring MVC.
2. `addResourceHandler("/assets/**")` applies only to URLs beginning with `/assets/` under Spring MVC's path matching rules.
3. `addResourceLocations("classpath:/public-assets/")` confines the asset source to a dedicated classpath folder; **the trailing `/` on the location** makes clear it is a directory.
4. `ResourceHttpRequestHandler` uses Spring's standard resource resolution; by default `PathResourceResolver` verifies located resources stay beneath valid locations. Do not swap in a custom resolver to “optimize” before fully understanding its security checks.
5. There is no mapping for `/internal-demo/marker.txt` or `internal-demo/` resources. A file on the classpath **does not become public merely because it sits beside another resource**.
6. Do not add `/**`, `classpath:/`, `file:/`, custom servlet default handlers, or manual file-reading endpoints if your goal is exposing only `public-assets/`.

This is the complete Spring MVC setup for the sample scenario. Larger systems may have other controllers and handlers; in that case audit **all routes** capable of returning resources, including upstream gateways, CDNs, and proxies.

### 4.3. Running and testing over HTTP

Inside the project directory with the Maven Wrapper:

```bash
./mvnw spring-boot:run
```

On Windows, run `mvnw.cmd spring-boot:run`. Use `curl.exe` if PowerShell aliases `curl` to a cmdlet.

**Permitted resource:**

```bash
curl -i http://localhost:8080/assets/hello.txt
```

Expected output: HTTP **200**, response body `PUBLIC_ASSET` (plus trailing newline); exact headers such as `Content-Type` depend on the server and configuration.

**Do not expose other directories:**

```bash
curl -i http://localhost:8080/internal-demo/marker.txt
curl -i http://localhost:8080/assets/internal-demo/marker.txt
curl -i http://localhost:8080/hello.txt
```

In the sample application, these URLs must **not return the file's contents**, typically returning HTTP **404**. The last URL also confirms the public resource is exposed only at `/assets/hello.txt`, not automatically at `/hello.txt`.

**Testing traversal and encoded traversal:** use `--path-as-is` so `curl` does not normalize `..` segments before sending the HTTP request.

```bash
curl --path-as-is -i "http://localhost:8080/assets/../internal-demo/marker.txt"
curl --path-as-is -i "http://localhost:8080/assets/%2e%2e/internal-demo/marker.txt"
curl --path-as-is -i "http://localhost:8080/assets/%252e%252e%252finternal-demo%252fmarker.txt"
```

Security expectation: **no request returns `NOT_FOR_HTTP`**. Depending on the servlet container, reverse proxy, firewall rules, and decoding behavior, the status may be **400**, **404**, or another rejection response. Do not enforce one rigid HTTP status for every malformed URL without knowing the exact layer rejecting it.

**Note:** testing that an endpoint returns 404 for a nonexistent filename is a weak test. This example creates an **actual** marker file outside the public directory, then tests both direct URLs and traversal payloads. When running security tests in real environments, use harmless canaries/fixtures rather than placing or requesting real secrets.

## 5. Automated tests: the “only public-assets is served” contract

Use `spring-boot-starter-test` in the Spring Boot project and test Spring MVC with `MockMvc`. If creating from Spring Initializr, include **Spring Boot Starter Test**.

Create **`src/test/java/com/example/demo/StaticAssetsApplicationTest.java`**:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StaticAssetsApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void servesOnlyThePublishedAsset() throws Exception {
        mvc.perform(get("/assets/hello.txt"))
                .andExpect(status().isOk())
                .andExpect(content().string("PUBLIC_ASSET\n"));
    }

    @Test
    void doesNotServePrivateClasspathFolder() throws Exception {
        mvc.perform(get("/internal-demo/marker.txt"))
                .andExpect(status().isNotFound());

        mvc.perform(get("/assets/internal-demo/marker.txt"))
                .andExpect(status().isNotFound());
    }

    @Test
    void doesNotServeAssetAtUnapprovedUrl() throws Exception {
        mvc.perform(get("/hello.txt"))
                .andExpect(status().isNotFound());
    }
}
```

Run:

```bash
./mvnw test
```

Expected outcome: all three tests pass in the sample Spring Boot MVC project. This is the **expected result for you to run and verify**, not a claim of execution on a specific repository.

`MockMvc` is good for checking Spring MVC mappings, yet **does not fully simulate URL decoding and normalization in real web servers and reverse proxies**. Therefore, CI or staging also needs HTTP integration/security tests hitting the actual Tomcat/Jetty, gateway, and HTTP clients used in deployment. Test raw, percent-encoded, double-encoded, slash/backslash, and symlink variants on the target OS. The test criterion is **zero leakage outside the approved scope**; which exact 4xx status is returned can depend on the network layer.

## 6. Reading files on demand in a controller: a different problem from static resource handlers

When users download files by document identifier, **never use a file path from the URL as direct filesystem input**, for example:

```java
// INSECURE: path taken directly from the client.
@GetMapping("/download")
public byte[] download(@RequestParam String path) throws IOException {
    return Files.readAllBytes(
        Path.of("/srv/app/public-assets").resolve(path)
    );
}
```

This snippet illustrates the risk, requires corresponding annotations/imports, and is **not complete code to use**. Even stripping `"../"` or checking `path.startsWith("/srv/app/public-assets")` is insufficient because paths can use alternate encodings, `..`, different separators, or symlinks.

If you genuinely need an API serving private documents, a safer design is:

1. The client sends a **logical ID** of the document, not a filesystem path: `GET /documents/12345`.
2. The server verifies **authentication + authorization for that document and tenant**.
3. The server looks up the ID in an internal database/map to retrieve a server-stored path, disallowing arbitrary client substitution.
4. The storage root comes from trusted configuration, and **OS permissions allow the process to read only the intended files**.
5. Resolve and canonicalize the path; verify the target lies inside the root with `Path.startsWith(Path)` on normalized/`toRealPath()` `Path` objects, **not `String.startsWith`**. Verify the file exists, is a regular file, and does not follow a symlink outside the root.
6. Consider **TOCTOU/symlink races**: if another actor can swap files/links between validation and opening, checking `toRealPath` alone is insufficient against races. Choose storage areas where untrusted actors cannot alter layout, and use platform-safe file-opening APIs when needed.

The illustration below shows the containment check **once the file exists**:

```java
// Illustration inside a service; NOT a complete HTTP endpoint.
Path publicRoot = Path.of("/srv/app/published").toRealPath();
Path candidate = publicRoot.resolve(serverControlledRelativeName)
        .toRealPath();

if (!candidate.startsWith(publicRoot)
        || !Files.isRegularFile(candidate)) {
    throw new SecurityException("Requested file is not allowed");
}
```

`serverControlledRelativeName` must be **resolved by the server from an authorized ID**, not a raw path string from the request. `toRealPath()` requires the path to exist, follows symlinks, and returns the canonical real path. `startsWith(Path)` compares **path components**, distinguishing `/srv/app/published` from `/srv/app/published-backup`. In a real app, add error handling for missing files, streaming, HTTP responses, authorization, and resource lifecycles.

**Do not try to reinvent a complex static file server** when `ResourceHttpRequestHandler` / `ResourceWebHandler` already meets your needs. Every custom layer of decoding, caching, normalization, or symlink handling you write adds another potential vulnerability surface.

## 7. Risks that remain even when using standard resource handlers

### 7.1. Accidentally publishing files inside the public area

Handlers reject reads **outside** the root, yet still serve **every file inside the root**. If someone copies `application-prod.yml`, backups, `.env` files, key files, logs, private documents, or sensitive source maps into `public-assets/`, normal requests can download them.

Mitigations:

- Enforce by convention that `public-assets/` holds only assets approved for publication.
- Review changes to public folders; use CI/scripts to inventory packaged artifacts and block disallowed extensions or filenames.
- Never copy an entire repository, config folder, or mounted secret into a document root.
- Disable directory listings in static web servers/proxies; when auto-index files exist, explicitly verify what gets exposed.
- Enforce MIME types and protect user-uploaded HTML/SVG/JS; uploaded files must not execute as active content on a trusted same-origin domain.

### 7.2. Adding overly broad resource locations

Examples of configurations that require **careful review**:

```java
// Dangerous examples if these roots contain non-public data.
registry.addResourceHandler("/**")
        .addResourceLocations("file:/srv/app/");

registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/");
```

These snippets illustrate anti-patterns and must not be copied into apps. Overly broad mappings or locations expand the set of servable files. Even though the framework enforces path containment against the root, a broad root still exposes many files within that root.

Never add locations such as `file:/`, home directories, directories containing config files, unreviewed uploads, or drive roots. Be careful with multi-element location lists because the **public file set is the union of all sources**.

### 7.3. Symbolic links and operating system permissions

On a filesystem, a symlink **inside** the public directory can point outside it. Check framework symlink handling for your version and ensure no untrusted symlinks exist inside the public tree; when serving dynamic files, use canonical containment and race-resistant design as in section 6.

Even with proper mappings, the OS must still enforce **least privilege**: the application user should only read assets meant to be served, never secrets or other services' directories. Container mounts and volumes require the same restrictions.

### 7.4. URL decoding and differences across proxies, containers, and frameworks

A request may traverse:

```text
Client
  -> CDN / WAF
  -> reverse proxy / API gateway
  -> Tomcat/Jetty/Netty
  -> Spring MVC/WebFlux resource handler
  -> Resource/Filesystem
```

Each layer can handle separators, URL encoding, encoded slashes, backslashes, and dot segments differently. If one layer checks paths before decoding while a downstream layer decodes again, policies can be bypassed.

Therefore:

- Keep framework, servlet container, and proxy versions patched.
- Do not arbitrarily call `URLDecoder.decode(...)` again on paths already parsed by the framework.
- Do not treat proxy/WAF rules as a substitute for narrowing resource sources inside the app.
- Run tests across the **actual production path**; test payloads only in authorized environments.
- Check accessibility over both HTTP 80 and HTTPS 443, across alternate hosts/path prefixes, or via CDN; policies must remain consistent.

### 7.5. Authentication/authorization differs from directory confinement

`permitAll("/assets/**")` (when using Spring Security) only controls **who may reach the URL**, not ensuring the handler opens files only inside the right folder. Conversely, mapping the right directory does not determine which files are private per user.

**Public static resources** belong in a public folder with no private data. **Documents with per-account/tenant permissions** require a download endpoint enforcing authorization before reading, never sitting in a `permitAll` static directory.

When using Spring Security, prefer letting `/assets/**` pass through the security filter chain with `permitAll` where appropriate. Do not disable security filters via `ignoring()` for everything just because they are static assets; security headers and controls remain valuable. Matchers must correspond exactly to the public URLs you declared.

## 8. Important Spring Framework patches for path traversal

Never assume “using the standard resource handler guarantees safety across all versions.” Real advisories exist:

**CVE-2024-38816** (published 2024-09-12): certain Spring MVC.fn/WebFlux.fn applications configuring `RouterFunctions` to serve resources from `FileSystemResource` were vulnerable to path traversal; Spring Framework 6.1.13 patched the 6.1 branch. Official advisory: https://spring.io/security/cve-2024-38816/

**CVE-2026-41843** (published 2026-06-08): path traversal when resolving **versioned static resources** in Spring MVC/WebFlux under combined conditions, particularly file-system resources and versioning support. Public patches include Spring Framework **6.2.19** and **7.0.8**; enterprise branches have dedicated patches per the advisory. Official advisory: https://spring.io/security/cve-2026-41843/

Key takeaways:

1. **Upgrade Spring Boot/Spring Framework per security advisories** using managed compatible dependency BOMs; do not swap a single Spring Framework JAR in isolation while ignoring compatibility. Verify the dependency tree and framework version **actually packaged and running**.
2. If you use resource versioning, file-system resources, or functional resource routes, determine whether you meet the advisory conditions and upgrade to a patched release on your branch.
3. This lesson's example avoids file-system static roots and disables resource versioning; that **reduces attack surface**, without replacing your obligation to apply patches.
4. Because vulnerabilities can arise inside the framework, **never treat passing self-written tests as absolute proof**; continue tracking advisories and testing libraries alongside containers/proxies in deployment.

## 9. Notes for Spring WebFlux and other web runtimes

The main example uses **Spring MVC/Servlet**. If a project runs **Spring WebFlux**, the corresponding static handler is `ResourceWebHandler`; custom configuration goes through `WebFluxConfigurer`, not `WebMvcConfigurer`:

```java
// Dedicated example for a Spring WebFlux application.
@Configuration
public class ReactiveStaticConfig implements WebFluxConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/public-assets/");
    }
}
```

This is a **snippet**, requiring imports from `org.springframework.context.annotation.Configuration` and `org.springframework.web.reactive.config`. Do not place both `WebMvcConfigurer` and `WebFluxConfigurer` classes in the sample MVC project; select the configuration matching your actual web stack.

Spring Boot WebFlux has `spring.webflux.static-path-pattern`, which **differs** from `spring.mvc.static-path-pattern`. `spring.web.resources.static-locations` can also be used in Boot static resource configuration. Whether MVC or WebFlux, the policy is identical: map only necessary public locations, keep the framework patched, test URL decoding, and verify files outside the root cannot be leaked.

If Nginx or a CDN serves assets directly, Spring Boot configuration **does not control Nginx/CDN file roots**. You must audit `root`/`alias`, redirects, rewrites, and file permissions on that web server under its own rules.

## 10. Pre-deployment review checklist

| Question | Expectation |
| --- | --- |
| What is the public URL? | A clear prefix like `/assets/**`, never accidentally covering the entire app |
| What is the public directory? | `classpath:/public-assets/` or another root containing only approved files |
| Are unintended default static handlers active? | Disabled or tightly configured; check `ServletContext` root and proxies too |
| Any endpoint joining client paths to the filesystem? | Removed or replaced with logical ID + authorization + canonical containment |
| Are symlinks/mounts/uploads inside the public area? | No escape paths out of root; write permissions and content types controlled |
| Any secrets, backups, or sensitive source maps in public artifacts? | None; packaging audit step in place |
| Are URL decoding layers consistent? | Tested through production-like proxy and container |
| Are relevant Spring/servlet container patches applied? | Advisories and actual runtime versions verified |
| Are personal resources using static `permitAll`? | No; served via an authorized endpoint |
| Do tests verify boundaries? | Public files -> 200; real files outside root -> unreachable across multiple URL variants |

## 11. Common misconceptions

**“Filtering `../` with `replace` is enough.”** False. Encodings, backslashes, absolute paths, symlinks, and discrepancies between URL processing layers bypass simple replacements.

**“`Path.normalize()` blocks traversal by itself.”** False. It normalizes path segments, **without checking** whether the path escaped the allowed directory. You must check containment on trusted `Path` objects and consider symlinks/TOCTOU.

**“Using `String.startsWith(root)` is sufficient.”** False. `/srv/app/public-bak` still begins with the string `/srv/app/public`. Use `Path.startsWith(Path)` on properly resolved paths.

**“URL `/assets/**` is safe even if the location is a root directory.”** False. A narrow URL pattern cannot compensate for a location exposing too many files.

**“Files on the classpath are always public.”** False. Files are only public when a mapping or handler exposes them. Still, never rely on that assumption to bundle secrets in a JAR.

**“Adding Spring Security `permitAll`/`authenticated` stops path traversal.”** False. URL-level authorization and file resource containment are **two independent security controls**.

**“A single test with `../` returning 404 proves traversal is impossible.”** False. You need a real canary file outside the public area, multiple encoded variants, and testing across the real HTTP stack/proxy.

## 12. Self-check

1. The app maps only `/assets/**` to `classpath:/public-assets/`. Should `src/main/resources/internal-demo/marker.txt` automatically be served at `/assets/../internal-demo/marker.txt`? **No**; if it were, that would be a security vulnerability.
2. Why shouldn't users pass `/download?path=../../...` even with Spring Security enabled? **Because authentication does not guarantee the requested path lies within files the user is authorized to read.**
3. Why set `spring.web.resources.add-mappings=false` in the strict-mapping example? **To disable Boot's auto-configured default static mappings and use only the declared custom handler**, alongside auditing other routes.
4. Can `/srv/app/public` and `/srv/app/public-bak` be safely distinguished with `String.startsWith`? **No**; compare `Path` components and handle symlinks.
5. When a file sits inside the public root yet contains a real token, does `PathResourceResolver` automatically block sensitive contents? **No**; every file inside the public area must be assumed publicly readable.
6. Why must Spring Framework still be upgraded even though standard handlers check locations? **Because path traversal CVEs have occurred in certain static resource configurations**, such as CVE-2024-38816 and CVE-2026-41843.
7. When a request through a CDN and reverse proxy returns 400 instead of 404 for an odd encoded URL, is that necessarily a bug? **No**; the security goal is never returning resources outside the root, while the exact status depends on the rejecting layer.

## 13. Official references for verification

- Spring Boot, *Servlet Web Applications – Static Content*: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Framework, *Spring MVC Static Resources*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- Spring Boot, *Reactive Web Applications – Static Content*: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework, *WebFlux Config – Static Resources*: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Security, *Authorization*: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OWASP, *Path Traversal*: https://owasp.org/www-community/attacks/Path_Traversal
- Spring Security Advisory *CVE-2024-38816*: https://spring.io/security/cve-2024-38816/
- Spring Security Advisory *CVE-2026-41843*: https://spring.io/security/cve-2026-41843/

**Conclusion:** Always **publish from a server-controlled list of locations**, use Spring's standard resource handlers instead of concatenating paths from requests, keep public assets in a dedicated directory, disable unneeded default mappings, and test that real files outside the public area can never be retrieved. Stay current on security patches, restrict OS file permissions, and handle authorized documents through dedicated endpoints.

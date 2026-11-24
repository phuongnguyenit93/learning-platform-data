# Query Parameters, Form Data, JSON, and Multipart in Spring Boot

**Context:** Spring Boot web-runtime → HTTP Foundation. This lesson uses **Spring MVC on the Servlet stack**, Java 17+, and Spring Boot 3.5.x; most mechanisms also apply to recent Spring MVC versions. Distinguish this from WebFlux on certain details of reading form data.

## 1. Four Ways to Send Data in HTTP

An HTTP request consists of a request line (method, path, and query string), headers, and an optional body. **`Content-Type` describes the format of the uploaded body**; it does not describe the query string. Four common ways to send data:

| Data type | Location and format | Typical Spring MVC usage | Appropriate use case |
| --- | --- | --- | --- |
| **Query parameter** | After `?` in the URL, e.g. `?q=java&page=2` | `@RequestParam` | Search, filtering, pagination, read options |
| **Form URL-encoded** | Body with `application/x-www-form-urlencoded`, e.g. `name=Lan&email=...` | `@RequestParam` or `@ModelAttribute` | Simple HTML forms, text field inputs |
| **JSON** | Body with `application/json`, e.g. `{"productId":"P-7","quantity":3}` | `@RequestBody` | APIs sending objects, arrays, structured data |
| **Multipart** | Body with `multipart/form-data`, consisting of multiple **parts** and a `boundary` | `@RequestParam MultipartFile`, `@RequestPart` | File uploads, sending files alongside text/JSON |

For example, the same user information can be transmitted in three different ways, yet **how the data is placed on the wire determines how the controller reads it**:

~~~http
GET /api/products?q=spring&page=2 HTTP/1.1
Host: localhost:8080
~~~

~~~http
POST /api/contacts HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=Lan&email=lan%40example.com
~~~

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"productId":"P-7","quantity":3}
~~~

In the multipart example, one part can be text and another part a binary file. The `boundary` delimiter is declared in the header and wraps each part. **Do not manually write a multipart header with a fake boundary when using clients like `curl -F` or `FormData`**; the client generates a boundary that matches the body.

> `@PathVariable` reads a segment inside the path, e.g. `/products/42`; `@RequestHeader` reads a header. These two data sources differ from query parameters, form data, and JSON bodies.

## 2. Query Parameters — Parameters in the URL

**Syntax:** the part after `?` consists of `key=value` pairs separated by `&`. For example, `/api/products?q=java%20web&page=2&tag=spring&tag=http` carries a keyword, a page number, and two `tag` values.

In **Spring MVC Servlet**, `@RequestParam` reads Servlet request parameters: primarily the query string and parsed form fields. With `GET`, the query string is normally the source to read. Query parameters are not exclusive to `GET`: a `POST` request can still carry query parameters in the URL.

~~~java
@GetMapping("/products")
public SearchResponse search(
        @RequestParam(defaultValue = "") String q,
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(name = "tag", required = false) List<String> tags) {
    if (page < 1) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "page must be positive");
    }
    return new SearchResponse(q, page, tags == null ? List.of() : tags);
}
~~~

Explanation:
- `@RequestParam("q")` or `@RequestParam(name = "q")` explicitly names the request key, independent of the Java parameter name. Missing a **required** parameter causes an HTTP 400 error by default; `required = false` or `Optional<T>` allows omission.
- `defaultValue` supplies a fallback when the parameter is absent or empty and implicitly makes the parameter optional. The incoming string is type-converted—for example, `page` from text to `int`.
- For repeated keys such as `tag=spring&tag=http`, use `List<String>`, an array, or `MultiValueMap<String,String>` if you need to preserve all values.
- Input data is always untrusted: validate bounds for `page` and `size`, and validate sort fields against an allowlist; avoid letting clients directly control SQL column names.

**URL encoding:** special characters require percent-encoding (a space usually becomes `%20`, and `&` inside a value becomes `%26`). Form-URL-encoding rules may encode a space as `+`; a literal `+` must be encoded as `%2B`. The fragment `#...` in a URL **is not sent by the browser to the server**. To avoid mistakes, use `URLSearchParams` or an HTTP client that encodes automatically.

**API design:** query parameters suit filtering, sorting, and pagination because URLs can be linked or bookmarked. Do not put passwords, access tokens, or sensitive data in the URL: URLs can appear in browser history, access logs, or monitoring systems. Do not use query parameters to carry large payloads.

## 3. Form Data — `application/x-www-form-urlencoded`

A default HTML form (without setting another `enctype`) sends fields as key/value pairs in the body using the same character encoding style as URL-encoding. For example, body `name=Lan&email=lan%40example.com`. Browsers use this format for many standard forms.

There are two ways to receive it in Spring MVC:

~~~java
@PostMapping(path = "/quick-contact",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public String quickContact(
        @RequestParam("name") String name,
        @RequestParam("email") String email) {
    return name + " <" + email + ">";
}
~~~

With multiple fields, **`@ModelAttribute` + a form DTO** is commonly used so Spring binds field names to Java properties, followed by Bean Validation:

~~~java
@PostMapping(path = "/contacts",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ContactResponse createContact(@Valid @ModelAttribute ContactForm form) {
    return new ContactResponse(form.getName(), form.getEmail());
}
~~~

`ContactForm` needs a structure that the data binder can instantiate and populate (for instance, a JavaBean with a no-arg constructor and getters/setters). `@NotBlank` and `@Email` validate the data after binding. The full example in section 6 defines this DTO.

**Common pitfall:** `@RequestParam` in Spring MVC Servlet sees both query parameters and URL-encoded form fields because the Servlet API unifies them as `request parameter`. If the same key appears in both the URL and the body, do not rely on implicit ordering or precedence; design the API contract to avoid ambiguous duplicate names. In **Spring WebFlux**, `@RequestParam` only reads query parameters; form and multipart data have separate access paths.

**Do not use `@RequestBody` instead of `@RequestParam` for URL-encoded form data** in Servlet MVC. Parameter parsing by the Servlet container may consume the body, making direct body reads unreliable. Nor is `@ModelAttribute` a JSON parser: it is a mechanism for binding request parameters to an object.

A simple HTML form:

~~~html
<form method="post" action="/api/contacts">
  <input name="name" required>
  <input name="email" type="email" required>
  <button type="submit">Submit</button>
</form>
~~~

This example sends a default URL-encoded form; the API side returns JSON, so for a complete browser experience, frontends typically submit via `fetch` and handle the returned JSON themselves. If the application uses cookie/session authentication, state-changing form POSTs must consider **CSRF** protection according to Spring Security configuration.

## 4. JSON — `application/json` and `@RequestBody`

In REST APIs, JSON fits structured data with nested objects, lists, booleans, or numbers. The client sends `Content-Type: application/json` and a valid JSON body. Spring MVC uses `HttpMessageConverter` to deserialize the body into a Java object; in typical Spring Boot MVC apps, Jackson handles JSON.

~~~java
public record OrderInput(
        @NotBlank String productId,
        @Min(1) int quantity) {}

@PostMapping(path = "/orders", consumes = MediaType.APPLICATION_JSON_VALUE)
public OrderResponse createOrder(@Valid @RequestBody OrderInput input) {
    return new OrderResponse(
            input.productId(), input.quantity(), input.quantity() * 1000L);
}
~~~

`@RequestBody` reads the **request body** once in a format supported by a converter; `@Valid` triggers validation when the project includes a Bean Validation provider. Invalid JSON syntax, unconvertible types, or a missing required body typically returns **400 Bad Request**. Sending `text/plain` when the endpoint requires `application/json` typically returns **415 Unsupported Media Type**. A DTO with syntactically valid fields that violate rules (such as `quantity=0`) can also return 400 due to validation.

Distinguish these headers and attributes:
- `Content-Type`: what format the client **is sending** in the body.
- `Accept`: what representation the client **wants to receive**; does not replace `Content-Type`.
- `consumes` on `@PostMapping`: which media type the endpoint **accepts**.
- `produces`: which representation the endpoint **produces**.
- `@RestController`: return values are serialized into the response body; with a plain `@Controller`, returning a `String` may be interpreted as a view name.

JSON numbers, strings, booleans, and `null` are distinct. `{"quantity":"3"}` is a string, whereas `{"quantity":3}` is a number; do not rely on overly permissive coercion. Use dedicated DTOs for requests and avoid binding directly to domain entities containing sensitive fields (internal IDs, roles, payment status, etc.). When input needs to distinguish **omitting a field** from **passing null**, consider appropriate wrapper types/validation instead of primitive `int`.

## 5. Multipart — Files Alongside Text and JSON Fields

`multipart/form-data` splits the body into multiple parts. Each part has its own headers, typically including `Content-Disposition: form-data; name="..."`; file parts may include `filename` and `Content-Type`. For file uploads, Spring MVC supports:
- `@RequestParam("file") MultipartFile file` to obtain a file part, or `List<MultipartFile>` for multiple files under one name.
- `@RequestParam("description") String description` to read an adjacent text field.
- `@RequestPart("metadata") DocumentMeta metadata` to deserialize a **JSON part** via a converter, similar to `@RequestBody` scoped to a single part; send `Content-Type: application/json` on that part.
- `jakarta.servlet.http.Part` if you need the standard Servlet API at the part level.

~~~java
@PostMapping(path = "/uploads", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public UploadResponse upload(
        @RequestParam("description") String description,
        @RequestParam("file") MultipartFile file) {
    if (file.isEmpty()) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "file is empty");
    }
    return new UploadResponse(
            description, file.getOriginalFilename(), file.getSize());
}

@PostMapping(path = "/documents", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public DocumentResponse document(
        @Valid @RequestPart("metadata") DocumentMeta metadata,
        @RequestPart("file") MultipartFile file) {
    if (file.isEmpty()) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "file is empty");
    }
    return new DocumentResponse(metadata.title(), file.getSize());
}
~~~

Both methods above only **return metadata to demonstrate binding** without persisting the file. When persisting for real, copy the stream to your chosen storage system, generate a safe storage ID/name, and handle I/O errors. `MultipartFile` is temporary request-scoped data; do not retain that object for processing after the request finishes.

Simplified raw multipart example (boundary and file bytes are illustrative only, **not a complete request to copy verbatim**):

~~~http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=abc123

--abc123
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Invoice"}
--abc123
Content-Disposition: form-data; name="file"; filename="sample.txt"
Content-Type: text/plain

hello
--abc123--
~~~

**Upload limits and security:**
- Spring Boot servlet enables multipart by default with limits of **1MB/file** and **10MB/request**; limits may also exist at a reverse proxy/gateway. Set limits suited to your business needs, for example:

~~~properties
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=20MB
~~~

- Check `file.isEmpty()`, size, allowed file types, and actual content; `file.getContentType()` and `getOriginalFilename()` are client-supplied and **untrusted**. Never use the original filename directly as a storage path; protect against path traversal, malicious executables, and file overwrites.
- Enforce upload/download permissions, limit file counts, scan for malware when required by the business, and avoid loading large files entirely into RAM with `getBytes()` unnecessarily.
- Oversized upload errors may be surfaced by the app/container as **413 Payload Too Large**, or as a multipart exception that an application handler maps. Do not promise a single status code without verifying your specific stack/gateway.
- With browser `fetch` and `FormData`, **do not manually set `Content-Type: multipart/form-data`**: the browser must append the actual boundary.

## 6. Runnable Example: One Application, Four Input Types

This example pins **Spring Boot 3.5.0, Java 17** for a reproducible Maven project. It uses Spring MVC (Servlet) with no database. File tree:

~~~text
http-inputs/
├─ pom.xml
└─ src/main/java/com/example/httpinputs/
   ├─ DemoApplication.java
   └─ HttpInputsController.java
~~~

**`pom.xml`**

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
  <groupId>com.example</groupId>
  <artifactId>http-inputs</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
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

**`src/main/java/com/example/httpinputs/DemoApplication.java`**

~~~java
package com.example.httpinputs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/httpinputs/HttpInputsController.java`**

~~~java
package com.example.httpinputs;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class HttpInputsController {

    @GetMapping("/products")
    public SearchResponse search(
            @RequestParam(defaultValue = "") String q,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(name = "tag", required = false) List<String> tags) {
        if (page < 1) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "page must be positive");
        }
        return new SearchResponse(q, page, tags == null ? List.of() : tags);
    }

    @PostMapping(
            path = "/contacts",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ContactResponse createContact(
            @Valid @ModelAttribute ContactForm form) {
        return new ContactResponse(form.getName(), form.getEmail());
    }

    @PostMapping(
            path = "/orders",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public OrderResponse createOrder(@Valid @RequestBody OrderInput input) {
        return new OrderResponse(
                input.productId(), input.quantity(),
                input.quantity() * 1000L);
    }

    @PostMapping(
            path = "/uploads",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public UploadResponse upload(
            @RequestParam("description") String description,
            @RequestParam("file") MultipartFile file) {
        requireNonEmpty(file);
        return new UploadResponse(
                description, file.getOriginalFilename(), file.getSize());
    }

    @PostMapping(
            path = "/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public DocumentResponse document(
            @Valid @RequestPart("metadata") DocumentMeta metadata,
            @RequestPart("file") MultipartFile file) {
        requireNonEmpty(file);
        return new DocumentResponse(metadata.title(), file.getSize());
    }

    private static void requireNonEmpty(MultipartFile file) {
        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "file is empty");
        }
    }

    public record SearchResponse(String q, int page, List<String> tags) {}
    public record ContactResponse(String name, String email) {}
    public record OrderInput(
            @NotBlank String productId,
            @Min(1) int quantity) {}
    public record OrderResponse(
            String productId, int quantity, long totalCents) {}
    public record UploadResponse(
            String description, String originalFilename, long size) {}
    public record DocumentMeta(@NotBlank String title) {}
    public record DocumentResponse(String title, long size) {}

    public static class ContactForm {
        @NotBlank
        private String name;

        @NotBlank
        @Email
        private String email;

        public ContactForm() {}

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }
    }
}
~~~

Run from the directory containing `pom.xml` (requires JDK 17+ and Maven):

~~~bash
java -version
mvn spring-boot:run
~~~

Open a second terminal to send requests. The commands below use **bash/curl**; on Windows you can use `curl.exe` and adjust quoting for PowerShell/CMD. Example responses show only the JSON body; server headers and dynamic metadata are omitted.

**A. Query parameter**

~~~bash
curl -s "http://localhost:8080/api/products?q=java%20web&page=2&tag=spring&tag=http"
~~~

~~~json
{"q":"java web","page":2,"tags":["spring","http"]}
~~~

Omitting `page` falls back to default 1. Passing `page=abc` fails conversion to `int` and the server returns 400. Passing `page=0` triggers the controller's check and returns 400.

**B. Form URL-encoded**

~~~bash
curl -s -X POST http://localhost:8080/api/contacts \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "email=lan@example.com"
~~~

~~~json
{"name":"Lan","email":"lan@example.com"}
~~~

`--data-urlencode` properly encodes user input. A malformed `email` or whitespace-only `name` will fail `@Valid` and return 400.

**C. JSON**

~~~bash
curl -s -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"productId":"P-7","quantity":3}'
~~~

~~~json
{"productId":"P-7","quantity":3,"totalCents":3000}
~~~

`totalCents` here is only an **illustrative fixed formula of 1000 cents per unit**, not real pricing logic. Sending `quantity=0` violates `@Min(1)`. Sending JSON to `/api/contacts` does not match `consumes`; conversely, sending URL-encoded data to `/api/orders` is also a media type mismatch.

**D. Multipart text + file**

~~~bash
printf hello > sample.txt
curl -s -X POST http://localhost:8080/api/uploads \
  -F "description=Invoice" \
  -F "file=@sample.txt;type=text/plain"
~~~

~~~json
{"description":"Invoice","originalFilename":"sample.txt","size":5}
~~~

`printf hello` creates exactly **5 bytes** in the file. The filename and size in the response come from the actual uploaded file; if you create the file differently, `size` may differ.

**E. Multipart JSON part + file part**

~~~bash
curl -s -X POST http://localhost:8080/api/documents \
  -F 'metadata={"title":"Invoice"};type=application/json' \
  -F 'file=@sample.txt;type=text/plain'
~~~

~~~json
{"title":"Invoice","size":5}
~~~

`;type=application/json` on the `metadata` part is the key detail: Spring uses a converter to deserialize the JSON part into `DocumentMeta`. Sending that part as plain text may make the part's media type incompatible and return 415.

## 7. Browser Clients: Choosing the Right Way to Send

**JSON with `fetch`:**

~~~javascript
const response = await fetch("/api/orders", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ productId: "P-7", quantity: 3 })
});
if (!response.ok) throw new Error("Request failed: " + response.status);
const order = await response.json();
~~~

**Multipart with `FormData`:**

~~~javascript
const data = new FormData();
data.append("description", "Invoice");
data.append("file", fileInput.files[0]); // fileInput is <input type="file">
const response = await fetch("/api/uploads", { method: "POST", body: data });
// Do not add Content-Type manually: the browser generates the boundary.
~~~

When a JSON part is needed in the browser, use a `Blob` with an explicit media type:

~~~javascript
const form = new FormData();
form.append(
  "metadata",
  new Blob([JSON.stringify({ title: "Invoice" })],
           { type: "application/json" }));
form.append("file", fileInput.files[0]);
await fetch("/api/documents", { method: "POST", body: form });
~~~

## 8. Common Errors and How to Diagnose Them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| HTTP **400** and missing `@RequestParam` | Key name differs from annotation or required parameter is absent | Compare names in URL/form; set `required=false` or `defaultValue` when appropriate |
| HTTP **400** with `page=abc` | Cannot convert text to `int` | Validate data before sending; return clear input error messages |
| HTTP **400** with `@Valid` | DTO violates `@NotBlank`, `@Min`, `@Email`, etc. | Fix payload; apps can standardize errors via `@RestControllerAdvice` |
| HTTP **400** due to malformed JSON | Missing JSON delimiter, empty body, type mismatch | Validate JSON syntax and verify `Content-Type` |
| HTTP **415** | `consumes` mismatches `Content-Type`, or JSON multipart part lacks media type | Send the proper media type on both the request and individual parts |
| HTTP **413** or multipart size error | File/request exceeds app, container, or proxy limit | Configure appropriate limits consistently across layers |
| `@RequestBody` fails on form data | URL-encoded form does not match JSON conversion | Use `@RequestParam`/`@ModelAttribute` for forms |
| `@RequestPart` fails to bind JSON | `metadata` part is `text/plain` instead of `application/json` | Send the part with `Content-Type: application/json` |
| Corrupted accented characters / `+` signs | Wrong encoding or double manual decoding | Use UTF-8 and URL-encoding-aware clients; decode only once |
| Upload succeeds yet file does not exist | Controller only read `MultipartFile` without persisting it | Write stream to storage during the request and save metadata separately |
| File has malicious content / path traversal | Trusting client-supplied filename/type | Validate content and permissions; use server-generated storage names in a safe directory |

**Validation and error handling:** `@Valid` with `@RequestBody`/`@RequestPart`/`@ModelAttribute` can raise `MethodArgumentNotValidException`. For constraints placed directly on method parameters, Spring MVC may use `HandlerMethodValidationException`. Production APIs should standardize error responses via `@RestControllerAdvice` or `ResponseEntityExceptionHandler`, though you do not need custom exception handlers to learn these four binding mechanisms.

## 9. Selection Principles and Self-Check Exercises

Choose based on **data source and purpose**: search/filter criteria → **query**; simple text form fields → **URL-encoded form**; structured objects/lists for REST APIs → **JSON**; binary files with accompanying metadata → **multipart**. `@RequestParam` in Servlet MVC handles both query and form parameters; `@RequestBody` reads JSON bodies; `@RequestPart` converts individual multipart parts.

Self-check with the sample application:
1. Send `GET /api/products?tag=A&tag=B`; predict `tags` and `page`; test `page=0` or `page=xyz`.
2. Submit the form with `name=   ` and `email=not-email`; observe HTTP 400 from Bean Validation.
3. Send `POST /api/orders` with a JSON body but omit the `Content-Type` header; compare with the exact header.
4. Send multipart `metadata` as plain text, then add `;type=application/json` and compare outcomes.
5. Create a file larger than `spring.servlet.multipart.max-file-size` and identify which layer rejects the request in your environment.

**Official documentation for reference:**
- Spring MVC `@RequestParam`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring MVC `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring MVC multipart and `@RequestPart`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Spring MVC validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot multipart configuration: https://docs.spring.io/spring-boot/appendix/application-properties/

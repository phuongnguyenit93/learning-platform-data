# Headers, Content-Type, Accept, and Content Negotiation in HTTP and Spring Web

An HTTP request or response consists of a **start-line/status-line, a set of headers, and a body (if present)**. Headers provide metadata so both sides understand how to exchange data: body format, desired response type, language, transfer encoding, authentication, caching, and many other conditions.

In Spring MVC or Spring WebFlux, the two most frequently confused headers are **Content-Type** and **Accept**:

- **Content-Type** describes **what format the body currently being sent has**. In a request, the client declares the body sent to the server. In a response, the server declares the body returned to the client.
- **Accept** in an HTTP request describes **which media types the client accepts for the response**. It does not declare the format of the body the client sent.
- **Content negotiation** is the process of selecting an appropriate **representation** for the same resource based on the server's capabilities and the client's preferences expressed via headers such as Accept, Accept-Language, and Accept-Encoding.

Example:

~~~http
POST /api/messages HTTP/1.1
Host: example.test
Content-Type: application/json
Accept: text/plain

{"text":"Hello"}
~~~

The client sends **JSON** and wants to receive **plain text**. Sending JSON does not force the server to return JSON. If the endpoint can indeed read JSON and return text/plain, this exchange is valid; if the endpoint does not support that combination, the server can return an appropriate error.

## 1. Message Structure and the Role of Headers

An illustrative HTTP/1.1 request:

~~~http
GET /api/books/7 HTTP/1.1
Host: example.test
Accept: application/json
Accept-Language: vi
Authorization: Bearer TOKEN_EXAMPLE
~~~

The GET request above has no body. The server might return a response like:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Language: vi
Cache-Control: private, max-age=60

{"id":7,"title":"HTTP Basics"}
~~~

These lines are a **protocol example**, not a guaranteed automatic output from every Spring application. Real responses may include Content-Length, Date, Transfer-Encoding, Vary, proxy-added headers, and a different ordering.

**Distinguish three positions:**

1. **Start-line/status-line:** method, target path, and HTTP version (request); or status code (response), in HTTP/1.x representation.
2. **Header field:** a name–value pair with a standardized role, such as **Content-Type: application/json**.
3. **Body/content:** bytes of the representation—JSON, text, images, multipart... or empty.

In HTTP/2 and HTTP/3, wire encoding is not verbatim HTTP/1.1 text lines: there are pseudo-headers and binary framing, yet the **semantic meaning** of most fields like Content-Type and Accept is preserved.

### Practical rules for headers

- Field names are semantically **case-insensitive**: Content-Type and content-type denote the same field name. When working through a framework, use its header API instead of writing custom string parsers.
- Some fields allow **comma-separated lists of values**, but you **must not automatically merge every header** with commas. Notably, Set-Cookie has its own rules.
- The order of most headers does not matter, though the order among repeated values of certain fields can be significant; do not treat all headers as unordered sets.
- Headers describe metadata, **not security proof** of the body's validity. The server must validate data, enforce size limits, check permissions, and never blindly trust client-supplied values.
- Proxies/gateways/load balancers can add or alter headers. When debugging, determine whether you are observing the request from the client, behind a reverse proxy, or inside the application.

## 2. Common Headers and Categorization

| Header | Common Direction | Meaning / When Used |
|---|---|---|
| Content-Type | Request and response with body | Media type of the current representation |
| Accept | Request | Media types the client accepts in the response |
| Accept-Language | Request | Preferred languages, e.g., vi, en |
| Content-Language | Response | Language of the returned representation |
| Accept-Encoding | Request | Content codings such as gzip, br understood by the client |
| Content-Encoding | Response or encoded request | Which content coding was applied to the body |
| Vary | Response | Request headers that affect the representation, helping caches select the right version |
| Authorization | Request | Authentication credentials per scheme, e.g., Bearer |
| WWW-Authenticate | Response | Challenge for authentication scheme, commonly paired with 401 |
| Cookie / Set-Cookie | Request / response | Sends cookies to server / sets cookies on client |
| Cache-Control | Both | Caching directives, depending on request/response context |
| ETag / If-None-Match | Response / request | Validator and conditional request supporting caching |
| Origin | Request | Browser origin, important for CORS |
| Access-Control-Allow-Origin | Response | Policy allowing browsers to share cross-origin responses |
| Location | Response | Target URI for redirects or newly created resources |
| Content-Disposition | Mainly response; also used in multipart parts | Display/download behavior or description of each multipart part |
| Content-Length | Applicable request/response | Content size in bytes when determined, not Unicode character count |

**Do not infer all application behavior merely from header presence.** Authorization does not guarantee access is permitted; Accept-Language does not guarantee the server has a translation; Accept-Encoding does not guarantee compression is enabled; Content-Type does not prove the body is parseable.

### Content-Type is not Content-Encoding

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

The logical content is **JSON**, while the bytes are **gzip-compressed** in transit. The client decodes gzip before parsing JSON. Content-Type specifies the representation type after removing content codings; Content-Encoding specifies how to decode the applied content coding bytes. A MIME type **does not replace** a compression algorithm.

## 3. Content-Type: Declaring the Format Being Sent

A media type has the form **type/subtype**, sometimes with parameters:

~~~http
Content-Type: application/json
Content-Type: text/plain; charset=UTF-8
Content-Type: text/html; charset=utf-8
Content-Type: application/problem+json
Content-Type: application/octet-stream
Content-Type: application/x-www-form-urlencoded
Content-Type: multipart/form-data; boundary=BOUNDARY_123
~~~

**type/subtype** identifies how to interpret the body—for example, JSON differs from XML even when representing the same book object. For media types with a **+json** suffix, such as application/problem+json, the suffix indicates JSON structure yet it remains a **distinct media type**; client and server must agree on supporting that media type, rather than assuming every endpoint supporting application/json accepts all +json variants under all conditions.

**charset** indicates character encoding when applicable to the media type, typically text. In modern applications, JSON exchanged across systems normally uses UTF-8; you should not rely on attaching arbitrary charsets in Content-Type to solve every encoding issue.

**multipart boundary** separates individual parts in the body. Parts may carry their own Content-Disposition and Content-Type. When using browser FormData or HTTP client tools that build multipart automatically, **let the client attach Content-Type with the boundary**; manually setting **multipart/form-data** without a boundary usually prevents the server from parsing it.

### Content-Type in requests

~~~http
POST /api/books HTTP/1.1
Host: example.test
Content-Type: application/json
Accept: application/json

{"title":"HTTP Basics"}
~~~

Here the server must **decode the request body as JSON** if the endpoint accepts JSON. When a client sends raw plain text in the request body while claiming Content-Type: application/json, JSON parsing can fail (typically 400 for invalid data). Never treat Content-Type as a tool that automatically converts content.

### Content-Type in responses

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8

OK
~~~

The server declares the current body is plain text. If it returns JSON while labeling it text/plain, clients or browsers may misinterpret it; browser MIME sniffing policies can also interfere. For web content, configure Content-Type accurately and consider **X-Content-Type-Options: nosniff** to prevent browsers from guessing types where relevant.

**When GET sends no body**, a **request Content-Type is normally unnecessary**; if you want JSON back, send **Accept: application/json**. The Content-Type header is neither "the API type being called" nor synonymous with the desired output.

## 4. Accept: Describing Which Responses the Client Can Receive

Typical syntax:

~~~http
Accept: application/json
Accept: text/plain
Accept: text/html, application/json
Accept: application/json, text/plain;q=0.5
Accept: application/*;q=0.8, text/plain;q=0.6
Accept: */*
~~~

**Meaning:**

- **application/json:** accepts JSON.
- **text/plain:** accepts plain text.
- **application/\***: accepts subtypes under the application type.
- **\*/\***: accepts any media type.
- **q:** relative preference/quality weight, defaulting to **1** when omitted, ranging from **0** to **1**. **q=0** means the corresponding media range is not acceptable.
- **Specificity:** more specific media ranges and parameters can influence candidate matching; it is not simply picking "the first item in the header".

Example request:

~~~http
Accept: application/json;q=0.9, text/plain;q=0.5
~~~

The client prefers JSON over plain text. If the server can produce both, negotiation logic may pick JSON by preference after considering available media types and matching rules. If the server **only supports text/plain**, returning plain text is still valid because the client permits q=0.5.

**The server is not forced to return the first media type in the list.** Accept states the client's constraints and preferences; the server must also be capable of producing the representation. Detailed ranking algorithms can vary across frameworks/servers, so do not assert one universal sorting formula for every case.

### When Accept is absent

Omitting Accept usually means the client **does not specify response format constraints**; the server may pick a default type. The command-line tool **curl** normally sends **Accept: */*** by default (observable with curl -v).

For instance, a browser navigating to an HTML page typically advertises text/html alongside several other media types, whereas an API call from code may explicitly set Accept: application/json. Therefore, **do not rely on default browser headers to prove which formats an API supports**.

### Accept does not change the request body

~~~http
POST /api/books HTTP/1.1
Content-Type: text/plain
Accept: application/json

book 1
~~~

The client asks for a JSON response while sending **plain text**. If the endpoint only reads JSON, it may return **415 Unsupported Media Type**; setting Accept=application/json does not turn a text/plain body into JSON. This is a very common HTTP client configuration mistake.

## 5. Content Negotiation: One Resource, Multiple Representations

A single resource can have multiple representations:

~~~text
GET /api/status
           |
           | request Accept?
           +--> application/json --> {"status":"ok"}
           +--> text/plain       --> status=ok
           +--> text/html        --> <p>status=ok</p>
           +--> no match         --> 406 (if server provides no fallback)
~~~

This is a **conceptual model**. For it to work, the server must actually implement each representation; Spring does not automatically know how to convert every object into JSON, XML, HTML, and plain text simply because a client asks for them.

**Server-side resolution steps:**

1. Locate the resource by URL, method, and other routing conditions.
2. Check whether a request body is present, whether the request Content-Type is supported by the endpoint, and whether a converter/decoder can read it.
3. Read Accept (and other configured strategies) to determine the client's desired response media types.
4. Intersect **what the client accepts** with **what the endpoint and message converters/encoders can produce**.
5. Select the matching handler/representation, serialize the body, and return the corresponding response Content-Type.
6. If none can be selected, it may return **406**; if the request body cannot be consumed due to an unsupported media type, it may return **415**. Other errors can arise before or after negotiation.

### Proactive vs. reactive content negotiation

**Server-driven / proactive negotiation:** the client sends Accept, Accept-Language, and Accept-Encoding; the server chooses the representation. This is the common pattern in Spring REST controllers.

**Agent-driven / reactive negotiation in HTTP terminology:** the server provides choices or a response like 300/406 so the client selects for itself. The word **reactive** here is an HTTP content negotiation term and **is not directly related** to Spring WebFlux/Reactive Streams.

### Content-Type, Accept, and illustrative outcomes

| Request Sent | Server Supports | Outcome |
|---|---|---|
| Content-Type JSON, Accept JSON | POST reads JSON and returns JSON | Succeeds if body is valid |
| Content-Type JSON, Accept text/plain | POST reads JSON, can return text/plain | Succeeds if a text/plain branch exists |
| Content-Type text/plain, Accept JSON | POST only reads JSON | Typically **415** |
| Content-Type JSON, Accept XML | POST reads JSON but only returns JSON | Typically **406** |
| Content-Type JSON, Accept JSON | POST reads JSON, but JSON body is malformed | Typically **400**, not 415 |
| GET with no body, Accept JSON | GET returns JSON | Succeeds; no request Content-Type needed |
| GET with no body, Accept XML | GET only has JSON | Typically **406** |
| GET Accept */* | GET has multiple representations | Server picks one representation per configuration; do not guess which without checking |

The table assumes URL, method, access permissions, handlers, and remaining configuration are all valid. HTTP allows fallbacks, custom error handling, or different media type matching; **do not treat the status codes in the table as an absolute guarantee for every web server**.

## 6. Spring MVC: consumes, produces, and HttpMessageConverter

In **Spring MVC**, controllers route requests using @RequestMapping and shortcuts like @GetMapping and @PostMapping. Two key attributes:

- **consumes:** mapping condition based on the **request Content-Type**. For example, consumes = application/json means the handler only matches requests whose representation matches application/json.
- **produces:** mapping condition based on the **request Accept** and response generation capability. For example, produces = application/json indicates the handler targets clients accepting JSON.
- **headers:** other header matching conditions, such as headers = "X-Client-Version=1", though **you should use consumes and produces for Content-Type/Accept** rather than manual header conditions.
- **@RequestBody:** instructs Spring to read/deserialize the body into a Java parameter, depending on converters and media type.
- **@ResponseBody** or **@RestController**: instructs Spring to write the Java return value into the response body.
- **ResponseEntity:** controls status code, headers, and body; Content-Type can be specified explicitly on the response when needed.

**Simplified Spring MVC flow:**

~~~text
Client
  -> Servlet container
  -> DispatcherServlet
  -> HandlerMapping filters path/method/consumes/produces
  -> HandlerAdapter + HttpMessageConverter reads @RequestBody
  -> Controller calls business service
  -> ReturnValueHandler + HttpMessageConverter writes response
  -> Content-Type + HTTP response
~~~

Familiar converters: **StringHttpMessageConverter** handles String/text, **MappingJackson2HttpMessageConverter** handles JSON when Jackson/matching config is present (exact class/converter names may evolve across Spring generations). XML requires appropriate dependencies and converters; do not merely add produces="application/xml" and expect objects to produce valid XML automatically.

Modern Spring MVC defaults to prioritizing the **Accept header** to determine requested representations. A query parameter strategy can also be configured if needed; **relying on .json/.xml path extensions to drive media type selection is no longer the default and is generally discouraged** due to routing ambiguity and security risks.

## 7. Hands-on Spring Boot + Spring MVC: Runnable Example

Create a Spring Boot application from **https://start.spring.io/**, choosing **Java**, **Maven**, **Spring Web**, and a JDK compatible with your Boot version (Java 17+ is a good baseline for Boot 3.x/4.x). Choose package name **example.media** or update the package consistently in both files below. The MVC starter chosen by Spring Initializr depends on the Boot generation (e.g., Boot 3.x uses spring-boot-starter-web, while Boot 4.x uses spring-boot-starter-webmvc).

**File src/main/java/example/media/MediaDemoApplication.java:**

~~~java
package example.media;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MediaDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MediaDemoApplication.class, args);
    }
}
~~~

**File src/main/java/example/media/MediaController.java:**

~~~java
package example.media;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class MediaController {

    // Same URI, but JSON representation for clients accepting JSON.
    @GetMapping(path = "/greeting",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Message greetingJson() {
        return new Message("Hello Lan");
    }

    // Same URI, plain text representation for clients accepting text/plain.
    @GetMapping(path = "/greeting",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String greetingText() {
        return "Hello Lan";
    }

    // Reads JSON request body and writes JSON response body.
    @PostMapping(path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Message echo(@RequestBody Message input) {
        return new Message(input.text());
    }

    public record Message(String text) {
    }
}
~~~

**Code explanation:**

- The two GET handlers share the **same path and method** but have different produces conditions, allowing representation selection based on Accept.
- For JSON GET, Spring and Jackson serialize **Message** into JSON; for plain text GET, Spring writes the String as text.
- POST /echo uses consumes to accept JSON and produces to return JSON; @RequestBody converts JSON into the Message record.
- No database, network client, or dependencies outside Spring Web; the example focuses strictly on headers and media types.
- The controller is in package **example.media**, matching the @SpringBootApplication class's package/subpackage so component scanning finds it.

### Starting the app

Inside the extracted Maven project directory:

~~~bash
# macOS / Linux
./mvnw spring-boot:run
~~~

On Windows PowerShell or Command Prompt, run the equivalent command:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Run the following curl commands from **a second terminal**. Each example assumes the application is listening on http://localhost:8080 and no other process occupies the port.

### Case A — GET requesting JSON

~~~bash
curl -i -H "Accept: application/json" "http://localhost:8080/api/greeting"
~~~

Expected status and response media type:

~~~http
HTTP/1.1 200
Content-Type: application/json
~~~

Expected JSON body:

~~~json
{"text":"Hello Lan"}
~~~

Additional headers, charset, and exact status-line formatting depend on version/server; the JSON payload above is what to verify.

### Case B — GET requesting plain text

~~~bash
curl -i -H "Accept: text/plain" "http://localhost:8080/api/greeting"
~~~

Expected response body:

~~~text
Hello Lan
~~~

The response Content-Type is **text/plain** (possibly with a charset parameter). Same URI yet two distinct representations; this is the clearest illustration of **media-type content negotiation**.

### Case C — GET requesting unsupported XML

~~~bash
curl -i -H "Accept: application/xml" "http://localhost:8080/api/greeting"
~~~

Expected status:

~~~http
HTTP/1.1 406
~~~

The sample app has no GET handler matching produces=application/xml, so Spring MVC returns **406 Not Acceptable** by default. Error body and error response headers may vary by Boot/Spring version; **do not assert a fixed error JSON or message**.

### Case D — POST sending JSON, expecting JSON

~~~bash
curl -i -X POST "http://localhost:8080/api/echo" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"text":"Hello Spring"}'
~~~

Expected JSON body:

~~~json
{"text":"Hello Spring"}
~~~

Notice the two headers have separate duties: **Content-Type** helps select/read the request body; **Accept** helps select/write the response body.

**Windows PowerShell:** you can run the same syntax with **curl.exe** on a single line to avoid line-continuation differences or the curl alias in Windows PowerShell 5.1:

~~~powershell
curl.exe -i -X POST "http://localhost:8080/api/echo" -H "Content-Type: application/json" -H "Accept: application/json" --data '{"text":"Hello Spring"}'
~~~

If older PowerShell environments alter quoting when calling native commands, use a JSON body file or shell-appropriate escaping; what matters is that the **transmitted bytes are valid JSON**. Postman or HTTPie also works.

### Case E — POST sending the wrong Content-Type

~~~bash
curl -i -X POST "http://localhost:8080/api/echo" \
  -H "Content-Type: text/plain" \
  -H "Accept: application/json" \
  --data '{"text":"Hello Spring"}'
~~~

Expected status:

~~~http
HTTP/1.1 415
~~~

Even though the body looks like JSON, the client declared text/plain while the mapping only consumes application/json. Spring MVC stops at the media type condition and returns **415 Unsupported Media Type**; it does not inspect the string content to pick a handler.

### Case F — POST sending valid JSON, requesting an XML response

~~~bash
curl -i -X POST "http://localhost:8080/api/echo" \
  -H "Content-Type: application/json" \
  -H "Accept: application/xml" \
  --data '{"text":"Hello Spring"}'
~~~

Expected status:

~~~http
HTTP/1.1 406
~~~

The client sends a valid JSON body that the mapping can read, yet there is no XML representation matching produces. **406** concerns the requested response, whereas **415** concerns the request content's media type.

### Case G — Valid headers but malformed JSON

~~~bash
curl -i -X POST "http://localhost:8080/api/echo" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"text":'
~~~

Expected status:

~~~http
HTTP/1.1 400
~~~

The declared format is **correct**, but the JSON payload is **syntactically invalid**. HttpMessageConverter fails to parse it and typically returns **400 Bad Request**. Thus, not every body failure is 415.

### Case H — Missing Accept or Accept: */*

~~~bash
curl -i "http://localhost:8080/api/greeting"
~~~

With **two distinct produces mappings**, the client does not specify a preferred format. The framework may choose according to actual mapping/converter rules; **do not hard-predict JSON or text/plain** in this open-ended case. When a client requires a specific representation, always set Accept explicitly for deterministic testing.

## 8. How Spring Processes @RequestBody, @ResponseBody, and Converters

Four collaborating yet independent concepts are involved:

**(1) Handler mapping:** determines which controller method qualifies for the path, HTTP method, consumes, produces, and other constraints.

**(2) Request decoding:** @RequestBody delegates to a reader/converter compatible with the media type and target Java type. If headers are valid but the payload is malformed (broken JSON), the error happens **during reading**, not necessarily during mapping.

**(3) Return value / response encoding:** @RestController writes the return value to the body. The framework locates a converter supporting the Java type and selected media type—for example, Jackson for JSON, String converter for text/plain.

**(4) Exception resolution:** routing, media type, deserialization, and business errors can be mapped to HTTP statuses. @RestControllerAdvice/@ExceptionHandler can **customize error status/body**, while preserving protocol semantics.

**Do not assume JSON just because you return a Java object.** If no compatible converter exists or a dependency is excluded, the endpoint may fail to produce the expected representation. Additionally, **ResponseEntity.ok(...).contentType(...)** sets an explicit response Content-Type; ensure the **actual body matches the declared type** and does not conflict with produces conditions.

### consumes and produces vs. @RequestHeader

~~~java
@GetMapping(path = "/example",
        headers = "X-Channel=mobile",
        produces = MediaType.APPLICATION_JSON_VALUE)
public Message example() {
    return new Message("Hello");
}
~~~

This is an **illustrative method snippet inside MediaController**, not a standalone Java file. The method matches only when the client sends **X-Channel: mobile** and a JSON-compatible Accept. When a custom header is missing, mapping failure is not necessarily 406/415; inspect which condition failed to match. Use **@RequestHeader("X-Channel")** to bind the header value as a parameter when needed, with explicit required/defaultValue handling.

## 9. WebFlux Also Negotiates Content Using Reactive Codecs

Spring WebFlux uses similar annotations in **annotated controllers**:

~~~java
@PostMapping(path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<Message> echo(@RequestBody Mono<Message> input) {
    return input.map(message -> new Message(message.text()));
}
~~~

**Illustrative method only**; this snippet must live inside a WebFlux @RestController importing Reactor Mono, MediaType, PostMapping, RequestBody, and an appropriate Message record. In WebFlux, **HttpMessageReader/HttpMessageWriter (codecs)** read/write content reactively instead of MVC's synchronous converter chain.

Key points to remember:

- **Content-Type/Accept, consumes/produces, HTTP 406/415** retain the same protocol semantics in both MVC and WebFlux.
- WebFlux can respond with **Mono/Flux**, streaming, and non-blocking I/O; that does not change the roles of the two headers.
- **Content-Type: text/event-stream** is typically tied to Server-Sent Events (SSE); clients usually send **Accept: text/event-stream** when requesting a stream. Streaming also requires proper flushing, serialization, timeout, and proxy configuration.
- A multi-element **Flux** is not automatically a single valid JSON document if fragments are emitted arbitrarily. Choose an appropriate serialization media type: application/json (e.g., a JSON array when supported by the writer), application/x-ndjson for newline-delimited JSON records, or text/event-stream for SSE, per your API contract.

**Note:** content negotiation does not make a blocking API reactive. If a service runs blocking JDBC/JPA calls directly on the event loop, using WebFlux can stall regardless of how cleanly headers are configured.

## 10. Accept-Language, Accept-Encoding, and Vary

Content negotiation is not limited to JSON/XML. A single resource can have multiple language versions or content codings:

~~~http
GET /guide HTTP/1.1
Accept: text/html
Accept-Language: vi, en;q=0.7
Accept-Encoding: br, gzip;q=0.8
~~~

The server might select Vietnamese HTML, compress it with Brotli if supported, and return:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Language: vi
Content-Encoding: br
Vary: Accept-Language, Accept-Encoding

[compressed body, cannot be read directly as text]
~~~

This is a **design example**, not headers Spring Boot adds automatically out of the box. Serving localized content and HTTP compression require proper configuration at the application or proxy level.

### Vary is needed to cache the right version

Suppose **GET /guide** returns Vietnamese for Accept-Language: vi and English for Accept-Language: en. If a shared cache keys strictly by URL, it risks serving the **Vietnamese version to a client wanting English**. The **Vary: Accept-Language** header instructs caches to factor that header into version selection. If the body also varies by Accept, **Vary: Accept** may be needed. If compression changes the wire representation, **Vary: Accept-Encoding** may be needed.

**Vary is a cache-key declaration**; it does not generate translations, perform compression, or route controllers. Only declare headers that genuinely influence the representation; inaccurate declarations lower cache hit rates or cause wrong responses to be served. For user-specific data, pair with an appropriate caching policy (Cache-Control: private/no-store, etc.) rather than relying on Vary alone.

### Accept-Language is a preference, not an absolute command

A browser's language preferences may not reflect the user's actual choice. If a user explicitly selected a language in the UI/profile, that selection usually takes precedence; when falling back to Accept-Language, provide a sensible default. In Spring, locale resolution and translating messages via MessageSource require configuration or integration; **simply sending Accept-Language does not automatically translate every String**.

### Accept-Encoding differs from Transfer-Encoding

Content-Encoding gzip/br describes **compressed/encoded content**. **Transfer-Encoding: chunked** in HTTP/1.1 describes message framing over the connection; it is neither a media type nor a data compression algorithm. HTTP/2 and HTTP/3 have their own framing. When debugging, distinguish **byte content length**, content compression, and transport framing.

## 11. Forms, File Uploads, JSON, and Client Configuration

**JSON API:**

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"productId":5,"quantity":2}
~~~

In Spring, use @RequestBody DTO to read JSON; **@RequestParam** suits query/form parameters and does not deserialize a full JSON object.

**HTML form passing key/value pairs:**

~~~http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan&remember=true
~~~

This is a URL-encoded form body, **not JSON**, even though both carry structured information. Spring MVC provides parameter binding suited to form parameters.

**File upload:**

~~~http
POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=ExampleBoundary

--ExampleBoundary
Content-Disposition: form-data; name="title"

Sample
--ExampleBoundary
Content-Disposition: form-data; name="file"; filename="note.txt"
Content-Type: text/plain

Example file content
--ExampleBoundary--
~~~

This is an **illustrative protocol** multipart body. In real applications, use **MultipartFile/@RequestPart** with Spring MVC multipart configuration, enforce upload size limits, and validate media types/content and filenames. Never trust a client-supplied content type as proof that a file is safe.

### Browser Fetch API

When sending JSON:

~~~javascript
const response = await fetch("/api/echo", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json"
  },
  body: JSON.stringify({ text: "Hello Spring" })
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}

const data = await response.json();
console.log(data.text);
~~~

The JavaScript snippet assumes the same origin and the sample JSON endpoint running; console output on a successful request is:

~~~text
Hello Spring
~~~

**Common mistake:** calling response.json() when the server returns HTML/text or 204 No Content; sending Accept: application/json **does not guarantee the server always returns JSON**, especially on error or proxy responses. Before parsing, check status and response Content-Type per the API contract.

When sending **FormData** with a file, normally **do not set Content-Type manually**:

~~~javascript
const form = new FormData();
form.append("title", "Sample");
form.append("file", selectedFile);

await fetch("/upload", {
  method: "POST",
  body: form
});
~~~

This illustrative JavaScript assumes a valid **selectedFile** File variable and a server upload endpoint; the browser generates the multipart boundary automatically.

### Postman, curl, and Spring WebClient

In Postman, selecting **Body → raw → JSON** usually syncs the body type with an appropriate Content-Type, though you should still verify the Headers tab.

With curl:

- **-H "Content-Type: application/json"** declares the request body type.
- **-H "Accept: application/json"** requests a JSON response.
- **--data** sends payload data; verify the actual Content-Type because curl defaults toward application/x-www-form-urlencoded when using --data unless overridden.
- **-i** prints response headers with the body; **-v** inspects both request and response, though avoid leaking Authorization/cookies publicly when sharing logs.
- **--compressed** requests/decompresses compression as supported by curl when observing Accept-Encoding.

With Spring WebClient, you can use **contentType(MediaType.APPLICATION_JSON)** to declare the outgoing body and **accept(MediaType.APPLICATION_JSON)** to request the response type. Both methods remain independent just like in HTTP. Individual clients may populate headers differently depending on request/body inserters; inspect the actual request if results differ from expectations.

## 12. Common Errors: 400, 404, 405, 406, 415, 500

| Status | Typical Scenario | First Thing to Check |
|---|---|---|
| **400 Bad Request** | Malformed JSON body, missing required parameter, binding failure | Body syntax, DTO fields, required parameters |
| **404 Not Found** | No matching route or resource | URL, context path, controller registration |
| **405 Method Not Allowed** | URL matches a route, but method is not allowed | GET/POST/PUT and @GetMapping/@PostMapping |
| **406 Not Acceptable** | Cannot produce a representation matching Accept | Accept, produces, message converters, available response types |
| **415 Unsupported Media Type** | Cannot accept/read request content for the given media type | Request Content-Type, consumes, converters/decoders |
| **500 Internal Server Error** | Server failure during processing/serialization or unhandled exception | Logs, stack trace, serialization, code bugs |

These are **common causes**, not an exhaustive list. @ControllerAdvice configuration, security layers, proxies, middleware, and server-specific behavior can return other statuses; do not blindly tweak headers before identifying which layer raised the error.

### Debugging 406 example

Suppose:

~~~java
@GetMapping(path = "/report",
        produces = MediaType.APPLICATION_JSON_VALUE)
public Report report() {
    return new Report(1);
}
~~~

This is an **illustrative method** depending on a valid **Report** type and enclosing controller. The client calls:

~~~http
GET /report HTTP/1.1
Accept: application/xml
~~~

If the server only has a JSON representation, no fallback, and maps by produces, it fails with **406**. Fix: update the client's **Accept** if the caller actually wants JSON; or provide an XML representation with an appropriate message writer/converter and API contract if XML is required. **Do not change Content-Type on the GET request** to fix this error.

### Debugging 415 example

~~~java
@PostMapping(path = "/report",
        consumes = MediaType.APPLICATION_JSON_VALUE)
public void submit(@RequestBody Report report) {
    // process report
}
~~~

This is also an **illustrative method**, not standalone. The client sends **Content-Type: text/plain**. If you intend to send JSON, replace the body with valid JSON and declare **Content-Type: application/json**. If the business requirement truly demands text/plain, design a handler/reader for that type. **Do not change Accept** to fix 415.

### Checklist when using Spring Boot

1. **What was actually sent?** Use curl -v/Postman console/browser DevTools Network to inspect **path, method, Content-Type, Accept, and body bytes**.
2. **How does the controller map?** Check @GetMapping/@PostMapping, consumes/produces, headers, param conditions, and class-level @RequestMapping prefixes.
3. **Are dependencies/converters sufficient?** For JSON check Jackson/relevant config; for XML verify the right version of XML converter.
4. **Is the body actually valid?** Content-Type: application/json does not turn an arbitrary string into JSON.
5. **Where did the error originate?** Controller, Spring framework, security filter, gateway, or reverse proxy? Trace request/correlation IDs if available and read reliable logs.
6. **Error responses may also participate in negotiation:** if @ExceptionHandler returns only one fixed representation, clients might see unexpected formats. Design a consistent error format, such as application/problem+json if adopting Problem Details.
7. **Have you tested with explicit Accept values?** Test application/json, text/plain, application/xml, and */* against your contract; testing only from a browser is insufficient.
8. **Could caching serve the wrong variant?** If multiple representations share a URI, verify Vary and Cache-Control in both the app and CDN/proxy.

## 13. Designing APIs with Good Content Negotiation

**Declare the contract clearly:** which media types each endpoint accepts (request Content-Type) and returns (response Content-Type/Accept). In OpenAPI specs, media types live in requestBody.content and responses.<status>.content; this keeps design and testing aligned.

**Use produces/consumes where meaningful:** if an endpoint only accepts JSON, declare consumes=application/json on POST/PUT/PATCH with bodies; if it only returns JSON, declare produces=application/json. This enables early error classification, documents the contract, and guides handler selection. Do not attach consumes to a bodyless GET just to signal "this is a JSON API".

**Decouple DTOs from wire formats:** business services operate on domain objects; controllers/serializers handle reading and writing representations. When adding XML or text formats, avoid duplicating business logic.

**Do not force every URL to support every format:** multiple representations per URI is an HTTP capability, yet when unneeded, a JSON-only API is completely reasonable. Adding gratuitous XML/HTML increases test burden, maintenance cost, and attack surface.

**Document real status codes:** clients must handle 406/415/400 and error responses. Never promise JSON on every possible error if proxies or security layers might return HTML or plain text.

**Configure caching properly:** if Accept or Accept-Language selects cacheable content, plan Vary and cache rules from the design stage, especially behind CDNs.

**Mind security headers and CORS:** Content-Type and Accept are not authorization mechanisms; CORS is enforced by browsers via Origin and Access-Control-* response headers and does not replace authentication/authorization. Use accurate Content-Type with nosniff where appropriate for browser-rendered resources.

## 14. Self-Check Questions

**1. A client POSTs Content-Type: application/json and Accept: text/plain—what does this mean?** The client sends JSON and wants a text/plain response; the server must support reading JSON and producing plain text for the call to succeed.

**2. GET /api/books has no body, and the client wants JSON—which header should it set?** **Accept: application/json**. Do not add a request Content-Type to signal the desired response format.

**3. Why can a valid JSON body still receive 415?** Because the request may declare a Content-Type that does not match consumes, lack a suitable reader, or send a media type unsupported by the endpoint.

**4. Why can Accept: application/xml return 406?** The client asked for XML, but the server cannot produce an XML representation for that route and chooses no fallback.

**5. What does q=0.5 in Accept mean?** It is a relative preference/quality weight for that media range, not a 50% probability that the server returns that type.

**6. Does a Spring endpoint returning a Java record always produce XML when Accept: application/xml is sent?** **No**. A matching handler and converter/encoder are required; having a Java object alone is not enough.

**7. What is Vary: Accept-Language for?** It helps caches distinguish responses that vary by requested language; it does not create translations.

**8. Does returning JSON and plain text from the same URL violate HTTP?** **No**. Those are multiple representations of one resource, selectable via content negotiation when implemented by the API.

**9. Does Content-Encoding: gzip mean the body's type is gzip instead of JSON?** **No**. Content-Type can still be application/json; gzip describes how the bytes are compressed.

**10. Do Spring MVC and WebFlux interpret Accept/Content-Type differently?** **No**. Both follow the same HTTP standard; internal reading/writing mechanics differ (converters vs. reactive codecs).

## 15. Standard References

- [MDN — HTTP headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers): header classification and meanings.
- [MDN — Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type): media type, charset, multipart boundary.
- [MDN — Accept](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Accept): media ranges, wildcards, and q weighting.
- [MDN — HTTP content negotiation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Content_negotiation): representations, language/encoding negotiation, Vary.
- [MDN — 406 Not Acceptable](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/406) and [415 Unsupported Media Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/415).
- [Spring Framework — Spring MVC Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): consumes, produces, header conditions.
- [Spring Framework — Spring MVC Content Types](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html): how Spring MVC resolves requested media types.
- [Spring Framework — WebFlux Request Mapping](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): corresponding semantics in the reactive web stack.

**Key takeaway:** **Content-Type = what this body is**; **Accept = what response formats I can accept**; **consumes = which request body types the server accepts**; **produces = which response media types the server can return**; **406 = cannot satisfy the requested response format**; **415 = unsupported media type for the request content**.

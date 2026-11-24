# Character Encoding, URIs, and Unicode Handling in Spring Boot Web Runtime

## 1. Learning Objectives

In a Spring Boot application serving HTTP, Vietnamese diacritical text, Japanese usernames, Arabic script, or emojis can pass through many different stages: browser, URL, reverse proxy, HTTP connector, Servlet API, Spring MVC, JSON converter, and database. If one stage uses the wrong decoding rule, users see garbled characters, broken URLs, HTTP 400/404 responses, or strings that look identical yet fail equality checks.

This lesson belongs to the **Server Configuration** group and focuses on:

1. Distinguishing **Unicode**, **UTF-8**, **UTF-16**, **URI percent-encoding**, and **HTML form encoding**.
2. Understanding three independent data paths: **URI path/query**, **HTTP request body**, and **HTTP response body**.
3. Configuring **server.servlet.encoding.\*** and **server.tomcat.uri-encoding** for Spring Boot running on Servlet/Tomcat.
4. Receiving, processing, and returning Unicode in Spring MVC without double-encoding or double-decoding.
5. Testing end-to-end and troubleshooting Vietnamese characters, emojis, special characters, rejected paths, and Unicode normalization.
6. Recognizing the boundaries of Servlet configuration when an application uses **Spring WebFlux / Reactor Netty**.

Configuration examples and the sample application use **Spring Boot 3.5.x, Java 17+, Spring MVC, and embedded Tomcat**. For other Boot versions, check the documentation for that exact release line because property names and server behavior may differ.

## 2. Unicode Is Not Synonymous with UTF-8

**Unicode** defines characters and code points. **Encoding** specifies how those code points are represented as bytes or code units.

- **UTF-8** represents Unicode as byte sequences and is standard across HTTP, JSON, configuration files, and web infrastructure; each Unicode scalar value uses one to four bytes.
- **UTF-16** represents text using 16-bit code units. Java Strings use UTF-16 code units; characters outside the Basic Multilingual Plane, such as many emojis, require a **surrogate pair** of two code units.
- **Charset** is the name of the encoding used when converting bytes to Strings and back, such as **UTF-8** or **ISO-8859-1**.
- **Percent-encoding** in URIs represents bytes as **%HH** sequences so data is safe inside a URL. It is not an independent charset: you must choose a charset (usually UTF-8) **before** turning bytes into %HH.

For example, the letter **é** has Unicode code point U+00E9; its UTF-8 bytes are **C3 A9**, and when placed in a URI component needing percent-encoding it becomes **%C3%A9**.

The Vietnamese string **Việt** can be used in JSON or a Java String as literal characters. In a URL, browsers or HTTP clients typically represent non-ASCII portions as %HH sequences after UTF-8 encoding.

**Mojibake** occurs when the same bytes are decoded with the wrong charset. For example, a string written as UTF-8 but read under another charset can appear as **Tiáº¿ng Viá»‡t** instead of **Tiếng Việt**. Changing fonts cannot fix this root cause.

## 3. Distinguishing Each Layer When a Request Enters the Server

~~~text
User types "Tiếng Việt 😀"
          |
          +-- URL path / query --> URI percent-encoding --> reverse proxy
          |                                             --> Tomcat URI decoding
          |                                             --> @PathVariable / @RequestParam
          |
          +-- Request body --> Content-Type + bytes --> HTTP message converter
                                                    --> @RequestBody / form parameter
          |
          +-- Controller and Service (Java String / Unicode)
                                                    --> DB, logs, files, APIs
          |
          +-- Response --> HTTP message converter --> UTF-8 bytes --> Client
~~~

There are **three separate encoding decisions**:

| Data Channel | Decoding Mechanism | Example | Configuration to Watch |
|---|---|---|---|
| **URI Path** | Server parses URL and percent-decodes per connector policy | **/users/Nguy%E1%BB%85n** | **server.tomcat.uri-encoding**, reverse proxy, path rules |
| **Query parameter** | URL decoding and parameter parsing | **?name=C%C3%A0+ph%C3%AA** | URI encoding, query/form rules |
| **JSON body** | **HttpMessageConverter** and JSON parser | **{"name":"Hà Nội"}** | Content-Type, UTF-8 per JSON standard |
| **Form body** | Servlet parameter parsing | **application/x-www-form-urlencoded** | Request character encoding and Content-Type |
| **text/plain body** | Text converter according to charset | UTF-8 text | **Content-Type: text/plain;charset=UTF-8** |
| **Response** | Converter or response writer | JSON, HTML, text, files | Response Content-Type/charset and converter |

**Core point:** configuring the charset of the **request body** is not the same as configuring **URI decoding**. An endpoint can receive Unicode bodies correctly yet misread paths or query parameters if the server, proxy, or client disagree on URL encoding rules.

## 4. Configuring UTF-8 for Spring Boot Servlet/Tomcat

Spring Boot 3.5 documents the relevant properties in **Common Application Properties** and the **Character Encoding** section of Servlet web applications.

Create or update **src/main/resources/application.yml**:

~~~yaml
server:
  servlet:
    encoding:
      enabled: true
      charset: UTF-8
      force-request: true
      force-response: false
  tomcat:
    uri-encoding: UTF-8
~~~

Exact explanation:

- **server.servlet.encoding.enabled=true**: enables character encoding configuration support at the Servlet layer.
- **server.servlet.encoding.charset=UTF-8**: the charset configured for HTTP requests/responses; the default in Boot 3.5 is UTF-8.
- **server.servlet.encoding.force-request=true**: forces requests to use the configured charset within the Servlet encoding mechanism. When **force** is not declared, this option defaults to true in Boot 3.5.
- **server.servlet.encoding.force-response=false**: does not force every response to use the same charset. This is appropriate when an application returns multiple media types and lets converters set suitable charsets. Default behavior depends on the force setting; check your version's documentation.
- **server.tomcat.uri-encoding=UTF-8**: sets the encoding **Tomcat** uses to decode URI bytes after percent-decoding; the default in Boot 3.5 is UTF-8.

If the entire application needs to force the charset on both requests and responses at the Servlet layer, you can use:

~~~yaml
server:
  servlet:
    encoding:
      charset: UTF-8
      force: true
~~~

Evaluate the effect of **force: true** on text responses or specialized formats before enabling it. This property does not repair bytes already mis-decoded by a proxy, database, or HTTP client; nor does it convert binary data into UTF-8.

### 4.1. Role of CharacterEncodingFilter

In the Servlet stack, Spring Boot typically registers a **CharacterEncodingFilter** to apply request/response encoding settings. Setting the request charset must happen **before** any Servlet or Filter reads the request body or form parameters. If a custom Filter accesses parameters too early before the encoding filter runs, the charset may already be locked in and the data cannot be recovered merely by changing properties.

Avoid registering multiple encoding filters with conflicting orders when Boot already configures one; prefer properties and inspect the actual filter chain.

### 4.2. Non-Interchangeable Properties

**server.tomcat.uri-encoding** only takes effect when the running server is **Tomcat**. If switching to Jetty or Undertow on a supported Boot version, check the corresponding connector settings; Tomcat properties do not control other servers.

**server.servlet.encoding.\*** belongs to the **Servlet stack**. In Spring WebFlux running on **Reactor Netty**, body reading/writing lives in HTTP codecs and the reactive server, without Servlet CharacterEncodingFilter. In WebFlux, rely on proper Content-Type headers, URI building, and reactive server configuration.

**server.servlet.encoding.mapping.\*** can map **locale → charset** for responses in Servlet applications. This is a specialized setting, such as mapping by Accept-Language for JSP/Servlet responses; it does not translate languages and is rarely needed in UTF-8 JSON APIs. Do not configure locale mappings without an actual requirement.

## 5. URIs, URLs, and Percent-Encoding

A URI typically has the structure:

~~~text
https://example.com/search/C%C3%A0-ph%C3%AA?q=Vi%E1%BB%87t+Nam&sort=name#section
|----- origin -----|---- path ----------------|---- query --------------------| fragment
~~~

Parts follow distinct rules:

- **Path** separates segments with **/**. Since **/** is structural, do not blindly encode every character with a form-encoding algorithm.
- **Query** contains name/value pairs. Characters **&** and **=** have structural meaning when parsing parameters; they must be encoded when part of literal data.
- **Fragment** starts with **#** and is normally used only client-side by browsers; it is **not sent** in the HTTP request-target to the server.
- The **%** sign introduces a percent-encoding sequence. Literal percent characters in data must be properly encoded as **%25** when building URLs.

### 5.1. Encoding Components Properly

| Input String | Common URL Representation | Note |
|---|---|---|
| **é** | **%C3%A9** | UTF-8 bytes are C3 A9 |
| **Việt** | **Vi%E1%BB%87t** | Non-ASCII is percent-encoded |
| **Cà phê** | **C%C3%A0%20ph%C3%AA** in path | Space becomes %20 |
| **Cà phê** | **C%C3%A0+ph%C3%AA** in form/query form-style | Plus sign represents a space |
| **A+B** | **A%2BB** as a form value | Literal plus must be encoded |
| **a&b** | **a%26b** as a query/form value | Prevents splitting into two parameters |
| **a/b** | Must be handled as segment data, not a path separator | %2F may be rejected by proxies/servers |

Never concatenate raw user input directly into URLs if it can contain **?**, **&**, **=**, **#**, **%**, spaces, or Vietnamese diacritics. Use a **URI builder** that distinguishes path from query components.

### 5.2. java.net.URLEncoder Suits Forms, Not Entire URIs

Java's **URLEncoder** implements **application/x-www-form-urlencoded** rules: spaces become plus signs (**+**). It is well suited for encoding form fields, but can cause confusion when used to build an entire path segment or full URL.

Standalone Java 17 example:

**UnicodeCheck.java**

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public class UnicodeCheck {
    public static void main(String[] args) {
        String value = "Cà phê & trà";
        System.out.println(URLEncoder.encode(value, StandardCharsets.UTF_8));

        String composed = "\u00E9";     // é in NFC form
        String decomposed = "e\u0301";  // e + combining acute accent
        System.out.println(composed.equals(decomposed));
        System.out.println(composed.equals(
                Normalizer.normalize(decomposed, Normalizer.Form.NFC)));

        String emoji = "😀";
        System.out.println(emoji.length());
        System.out.println(emoji.codePointCount(0, emoji.length()));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 UnicodeCheck.java
java UnicodeCheck
~~~

Exact stdout:

~~~text
C%C3%A0+ph%C3%AA+%26+tr%C3%A0
false
true
2
1
~~~

The first line is **form-style encoding**; plus signs replace spaces. The two Unicode values **é** and **e + combining acute accent** look nearly identical yet are unequal before normalization. The emoji lies outside the BMP, so the Java String has two UTF-16 code units even though it is a single code point.

### 5.3. Using UriComponentsBuilder When Constructing URIs in Spring

The snippet below is an **illustrative code fragment** that requires a project with **spring-web**, unlike the standalone Java program above:

~~~java
import org.springframework.web.util.UriComponentsBuilder;

String uri = UriComponentsBuilder
        .fromPath("/api/items/{name}")
        .encode()
        .buildAndExpand("Cà phê & trà")
        .toUriString();

System.out.println(uri);
~~~

Output:

~~~text
/api/items/C%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0
~~~

Calling **UriComponentsBuilder#encode()** before expanding variables encodes variable values as data, including reserved characters that could carry structural meaning. Do not pre-percent-encode values and then pass them into an encoding builder if you want to avoid **double encoding**, where **%C3%A0** turns into **%25C3%25A0**.

If user input is itself a multi-segment path, decide explicitly whether it is **one data segment** or **multiple structural segments**; the two are not equivalent.

### 5.4. Watch Out for Plus Signs, Slashes, and Server Rules

- In **application/x-www-form-urlencoded**, **+** represents a space. To send a literal plus sign, use **%2B**.
- In a URL path, **+** is normally a valid literal character and is not automatically treated like a form-query space.
- **%2F** is a percent-encoded slash. Reverse proxies and Tomcat may reject or apply special rules to encoded slashes to prevent path traversal and routing ambiguities.
- **Do not** enable relaxed URI server options just to make a malformed URL work. If an identifier contains slashes or special characters, place it in a query/body or encode it using a safe API design.
- Never arbitrarily decode a URL twice. **%252F** after one decode becomes **%2F**, and after two decodes becomes **/**, causing routing errors and security vulnerabilities.
- Proxies, WAFs, ingress controllers, and backends must agree on decode/normalize rules. Never test only on Tomcat while ignoring the reverse proxy.

## 6. JSON, Form, and Plain Text Bodies

### 6.1. JSON as UTF-8

Per **RFC 8259**, JSON exchanged between systems outside a closed ecosystem must be encoded in **UTF-8**. The standard media type is **application/json**; its media type registration defines no required charset parameter. Therefore, the following header suffices for modern JSON:

~~~http
Content-Type: application/json
~~~

Valid JSON body example:

~~~json
{
  "name": "Nguyễn Hà",
  "city": "Hà Nội",
  "emoji": "😀"
}
~~~

When a Spring MVC controller receives a record or DTO via **@RequestBody** from JSON, Jackson and the message converter build Java Strings from the body. When returning a record, the converter serializes it to JSON using a compatible encoding.

**Note:** JSON can represent a character directly or via Unicode escapes such as **\u00E9**. Both forms can produce the exact same **String value** after parsing even though the raw HTTP bytes differ. Do not compare two JSON responses by raw bytes and conclude Unicode is broken when the only difference is escaping.

Do not include a UTF-8 BOM in JSON sent over the network. If a body contains bytes encoded in another charset while claiming or assuming UTF-8, the server may fail parsing or produce corrupted characters.

### 6.2. HTML Forms

With **application/x-www-form-urlencoded**, clients encode **field names / field values** and send them as a form-style string; spaces typically become **+**. Java Servlet parameter parsing is affected by the request character encoding and container decoding behavior.

The following form body represents the value **Cà phê & trà**:

~~~text
name=C%C3%A0+ph%C3%AA+%26+tr%C3%A0
~~~

Appropriate header:

~~~http
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
~~~

Setting **force-request: true** enforces UTF-8 consistently at the Servlet layer, though it cannot fix a client that sends malformed bytes. Always test with real browsers or integrated clients.

### 6.3. Plain Text

When sending a plain text body, declare the charset explicitly, for example:

~~~http
Content-Type: text/plain; charset=UTF-8
~~~

When returning plain text with **ResponseEntity<String>**, you can specify Content-Type with a charset; when returning JSON, use the JSON converter and JSON media type. Never call parameterless **String.getBytes()** at I/O boundaries where a protocol requires a fixed charset; pass **StandardCharsets.UTF_8**.

### 6.4. Multipart Uploads

With **multipart/form-data**, each part can have its own headers. The filename in **Content-Disposition** and text part payloads follow different rules from JSON request bodies. Do not apply a single blanket URL-decoding trick to filenames, form fields, and file contents.

When uploading files with Unicode filenames, test across client/proxy/container, sanitize filenames, and never concatenate user-supplied filenames directly into storage paths. Binary file bytes must be preserved untouched; never decode every part as UTF-8 text.

## 7. Runnable Spring Boot MVC Example: Unicode via Query, Path, and JSON

The example below demonstrates the three data paths. It uses **Java 17+**, **Maven**, and **Spring Boot 3.5.16** (a patch release in the Boot 3.5 line). The server is embedded Tomcat from **spring-boot-starter-web**.

### Project Structure

~~~text
unicode-web-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/unicodeweb/
    │   ├── UnicodeWebApplication.java
    │   └── UnicodeController.java
    └── resources/
        └── application.yml
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>unicode-web-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### UnicodeWebApplication.java

~~~java
package com.example.unicodeweb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UnicodeWebApplication {
    public static void main(String[] args) {
        SpringApplication.run(UnicodeWebApplication.class, args);
    }
}
~~~

### UnicodeController.java

~~~java
package com.example.unicodeweb;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/text")
public class UnicodeController {

    @GetMapping("/query")
    public Echo fromQuery(@RequestParam String value) {
        return new Echo(value);
    }

    @GetMapping("/path/{value}")
    public Echo fromPath(@PathVariable String value) {
        return new Echo(value);
    }

    @PostMapping(
        value = "/json",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Echo fromJson(@RequestBody Echo request) {
        return request;
    }

    public record Echo(String value) {
    }
}
~~~

The code uses the **Echo** record as a JSON DTO, convenient for inspecting the String value Spring MVC received. In real applications, validate user input and avoid echoing sensitive data directly.

### application.yml

~~~yaml
server:
  port: 8080
  servlet:
    encoding:
      enabled: true
      charset: UTF-8
      force-request: true
      force-response: false
  tomcat:
    uri-encoding: UTF-8
~~~

### Running

In the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Or package:

~~~bash
mvn clean package
java -jar target/unicode-web-demo-1.0.0.jar
~~~

### Test 1: Query Parameter with Unicode and Reserved Characters

~~~bash
curl -i --get \
  --data-urlencode "value=Cà phê & trà" \
  "http://localhost:8080/api/text/query"
~~~

Expected response body **value**:

~~~json
{"value":"Cà phê & trà"}
~~~

The **curl --data-urlencode** flag properly encodes the query parameter value; **&** becomes data instead of being interpreted as a parameter separator.

### Test 2: Percent-Encoded Path Variable

~~~bash
curl -i "http://localhost:8080/api/text/path/Vi%E1%BB%87t"
~~~

Expected response body:

~~~json
{"value":"Việt"}
~~~

Tomcat percent-decodes the URL using UTF-8 and Spring MVC binds the decoded path variable. If **%2F** is used inside a segment, the result depends on connector/proxy policies; do not use it as a routine Unicode test.

### Test 3: JSON Body with Vietnamese Text and Emoji

Create **payload.json**, genuinely saved in **UTF-8**:

~~~json
{"value":"Tiếng Việt 😀"}
~~~

Send request:

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  --data-binary @payload.json \
  "http://localhost:8080/api/text/json"
~~~

Response body representing the same value:

~~~json
{"value":"Tiếng Việt 😀"}
~~~

A differently configured JSON serializer may escape Unicode as **\uXXXX** sequences; if the client parses it back into the exact String, the data is still valid. To inspect exact bytes and Content-Type, use **curl -v**, hex-dump the response, or write tests that parse the JSON and compare parsed values.

**Shell note:** the multiline curl examples above use Bash syntax. On Windows PowerShell you can use **curl.exe** on one line, or appropriate line continuations; for JSON bodies, a UTF-8 file avoids shell differences in quoting and Unicode handling.

## 8. Unicode Normalization, Comparison, and Storage

Two visually identical strings do not necessarily share the same code point sequence. For example, **é** can be:

- One code point **U+00E9** (composed form).
- Two code points **U+0065 U+0301** (letter e + combining acute accent).

The Java program in Section 5 demonstrates **String.equals** returning false before normalization and true after **Normalizer.Form.NFC**. In Vietnamese, tone marks and diacritics can also exist in multiple combining forms.

**Practical application:**

- For display names, generally **preserve** the original string if display fidelity matters; normalize only when business rules require it.
- For identifiers, lookup keys, or uniqueness-enforced values, establish a normalization policy (usually **NFC**) at **one consistent boundary** before storage and comparison. Apply it consistently across create, lookup, and update.
- **NFC** is not the same as **case folding**, accent stripping, or case conversion; do not mix these operations unless the business logic calls for it.
- **NFKC** merges compatibility characters and can lose meaningful distinctions; do not apply it by default to all user input.
- Visually similar strings can be completely different Unicode characters (homoglyphs/confusables); NFC alone does not solve phishing or identifier security issues.

### 8.1. Counting Characters in Java

**String.length()** counts **UTF-16 code units**, not Unicode code points, composed letters, or UTF-8 bytes. A single emoji can consist of multiple code points (emoji + skin tone, zero-width joiner) and many UTF-16 code units.

If you need length limits for UI or database columns, explicitly define whether the limit measures **bytes**, **code points**, or **grapheme clusters** (user-perceived characters). Do not apply the same limit across all three without testing.

### 8.2. Files, Databases, Logs, and Downstream APIs

Unicode can still be corrupted **after** passing through the controller cleanly:

- **Text files**: read/write with an explicit charset, e.g., **Files.readString(path, StandardCharsets.UTF_8)** and **Files.writeString(path, text, StandardCharsets.UTF_8)**.
- **Databases**: use a database/driver/column supporting full Unicode and appropriate collation. For instance, with MySQL pay attention to **utf8mb4** and collation; do not assume every charset named **utf8** can store every emoji.
- **Logs**: check encoding of appenders, terminals, container runtimes, and log collectors. Strings valid in the JVM can still render incorrectly on a console.
- **HTTP clients**: use proper message converters and URI builders for RestClient, WebClient, or SDKs; check request body charsets and URL encoding.
- **HTML/JSP**: ensure matching HTTP Content-Type charsets, HTML metadata, and template file encodings; avoid mixing JSP defaults with JSON rules.

If corruption happens at only one layer, inspect the **raw bytes**, **Content-Type header**, **parsed String**, and **stored output** at that point before changing global settings.

## 9. Evaluating Reverse Proxies, API Gateways, and CDNs

A production system can have multiple layers:

~~~text
Browser / Mobile App
        |
        v
CDN / WAF / API Gateway
        |
        v
Reverse Proxy / Ingress
        |
        v
Embedded Tomcat
        |
        v
Spring MVC Controller
~~~

A request URI can be rejected or altered **before reaching Tomcat**. Points to align:

1. Does the reverse proxy **pass through** or **decode/re-encode** the URI?
2. Does it reject encoded slashes (**%2F**), encoded backslashes, NUL bytes, or invalid percent escapes?
3. Does the gateway normalize paths or case?
4. Do all layers treat plus signs (**+**) the same way in query/form data?
5. Are headers such as **Content-Type** and body bytes forwarded intact?
6. Do redirects and link generation use a URI builder to encode user-provided data?

**Security:** do not blindly turn on **server.tomcat.relaxed-path-chars**, **server.tomcat.relaxed-query-chars**, or encoded-slash allowances just to bypass 400/404 errors. Ensure URLs are generated properly and verify consistency between proxy and application, because mismatched decoding across layers can cause path traversal, cache inconsistency, or access-control bypasses.

## 10. Test Matrix to Include

A single successful Vietnamese request is not enough to prove the entire web runtime handles Unicode properly. Run a minimal matrix:

| Input | Query | Path | JSON body | Form body |
|---|---|---|---|---|
| **Hà Nội** | Test | Test | Test | Test |
| **Cà phê & trà** | Test & encoding | Test segment encoding | Test | Test +/& encoding |
| **A+B** | Test %2B | Test plus | Test | Test %2B |
| **日本語** | Test | Test | Test | Test |
| **😀** | Test | Test | Test | Test |
| **e + combining mark** | Test NFC/NFD | Test NFC/NFD | Test NFC/NFD | Test NFC/NFD |
| **a/b, a?b, a#b, a%b** | Test reserved chars | Evaluate path policy | Test | Test reserved chars |

Each test should verify:

- Correct HTTP **status**; no unexpected 400/404/415/500 responses.
- Correct **Content-Type** media type, and charset when required by the media type.
- Unicode value **after parsing** matches expected data.
- Spaces, **+**, **&**, **=**, **#**, **%** are treated as data when encoded in the right component.
- Combining Unicode sequences are compared according to application policy; diacritics are not silently dropped.
- If a bug comes from a proxy, reproduce the difference between calling the backend directly versus through the gateway.

For JSON APIs, writing integration tests with **MockMvc** or **WebTestClient** is more reliable than comparing raw JSON bytes. For example, use a JSON parser to verify the **value** field rather than comparing response escape formatting.

## 11. Diagnosing Common Encoding Errors

| Symptom | Possible Cause | How to Check and Fix |
|---|---|---|
| **Tiáº¿ng Viá»‡t** instead of **Tiếng Việt** | UTF-8 read as another charset | Inspect raw bytes, Content-Type, and charset at the parse point |
| Vietnamese query fails, JSON body works | URI decoding or client URL encoding mismatch | Check percent-encoded URI, Tomcat URIEncoding, and proxy |
| Character **+** turns into a space | Form/query value used unencoded plus sign | Send **%2B** if a literal plus sign is intended |
| **&** truncates part of a parameter | Client concatenated query string without encoding | Use a URI builder or --data-urlencode |
| URL path returns **400** on **%2F** | Encoded slash blocked by connector/proxy policy | Design identifiers without slashes in paths; inspect proxy |
| URL returns **404** despite controller existing | Path decoded into different segments or wrong context path | Inspect actual request-target and route mapping |
| JSON characters escaped as **\uXXXX** | JSON serializer chose escaped representation | Parse JSON and compare Unicode Strings; do not assume corruption |
| Emoji becomes **?** when saved to DB | DB charset/collation/column or connector lacks support | Inspect schema, driver, and encoding; run a round-trip test |
| Visually identical strings return **equals** false | Different Unicode normalization forms | Apply NFC/NFD policy at the right boundary |
| API works, console/logs look wrong | Terminal or log appender uses a different encoding | Check log file, stdout, and log collector encodings |
| Form body broken despite UTF-8 config | A filter parsed parameters before charset was set | Check Servlet Filter order; avoid reading parameters too early |
| Changed charset yet old data remains garbled | Bytes were already mis-decoded and stored as mojibake | Locate the source bug and plan a separate data remediation |

**Do not try to fix bugs by** encoding every String to UTF-8 and decoding as UTF-8 at every layer. Only convert **bytes ↔ String** at necessary I/O boundaries, and only percent-encode when constructing **URI components**.

## 12. Safe Implementation Checklist

- [ ] Identify Spring Boot version, Servlet vs. WebFlux, and actual embedded server.
- [ ] Default to UTF-8 for text bodies; declare Content-Type accurately.
- [ ] For Spring MVC, check **server.servlet.encoding.charset**, **force-request**, and **force-response**.
- [ ] For Tomcat, check **server.tomcat.uri-encoding**; do not confuse it with request-body charset.
- [ ] Use a URI builder for paths/queries; do not use **URLEncoder** for whole URLs.
- [ ] Do not double-encode or double-decode user-supplied URL parts.
- [ ] Keep decoding behavior consistent between reverse proxies and the backend.
- [ ] JSON uses UTF-8 per RFC 8259; do not rely on adding a charset parameter to application/json.
- [ ] Read/write text files, connect to databases, and write logs using the chosen charset.
- [ ] Explicitly define when Unicode normalization and string comparison are needed.
- [ ] Run round-trip tests with Vietnamese, CJK, emojis, plus signs, ampersands, and combining Unicode.
- [ ] Handle invalid URIs/encoded slashes per security policy; do not relax rules indiscriminately.

## 13. References

1. Spring Boot 3.5 – Common Application Properties (Servlet encoding and Tomcat URI encoding): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
2. Spring Boot 3.5 – Servlet Web Applications, Character Encoding section: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
3. Apache Tomcat 10.1 – HTTP Connector, URIEncoding and useBodyEncodingForURI attributes: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
4. Spring Framework – URI Links, UriComponentsBuilder encoding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html
5. RFC 3986 – Uniform Resource Identifier: https://www.rfc-editor.org/rfc/rfc3986
6. RFC 8259 – JSON UTF-8 encoding and media type: https://www.rfc-editor.org/rfc/rfc8259
7. Java 17 – Normalizer API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html
8. Java 17 – URLEncoder API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html

**Conclusion:** Unicode data traverses multiple independent layers. Setting **UTF-8** for requests/responses is necessary but not sufficient: **URI percent-encoding**, **Tomcat/proxy decoding policies**, HTTP message converters, Java Strings, and persistence layers must all align. Understanding each boundary lets you handle Vietnamese and Unicode reliably without manual encoding workarounds everywhere.
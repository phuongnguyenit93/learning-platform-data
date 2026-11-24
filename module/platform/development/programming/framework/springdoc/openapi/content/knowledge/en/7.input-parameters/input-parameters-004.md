# Describing `@RequestHeader` and `@CookieValue`

REST APIs often receive data beyond path and query parameters. Clients can also send information in HTTP headers or cookies. In Spring MVC, `@RequestHeader` reads a request header and `@CookieValue` reads a cookie by name. Springdoc recognizes both annotations to generate the corresponding parameters in the OpenAPI specification; `@Parameter` helps add descriptions, examples, and details that Java types cannot convey.

These two data types serve different roles. Headers typically carry request metadata such as client version, language, or correlation IDs. Cookies are typically stored and sent automatically by browsers according to domain, path, and cookie policies. When documenting an API, clearly state the name, purpose, requiredness, and format of each value so integrators know how to send requests.

## 1. HTTP Headers and Cookies in a Request

An HTTP request can contain a method, URL, headers, cookies, and a body. Example:

```http
GET /api/preferences HTTP/1.1
Host: api.example.com
X-Client-Version: 2.4.0
Accept-Language: vi
Cookie: theme=dark; locale=vi
Accept: application/json
```

In the example:

- `X-Client-Version` is a custom header defined by the application.
- `Accept-Language` is a standard header indicating the client's preferred language.
- `theme` and `locale` are cookies sent in the `Cookie` header of the HTTP request.
- `Accept` describes the response format the client can accept.

Header field names are case-insensitive in HTTP. Thus `X-Client-Version` and `x-client-version` refer to the same header name. However, the development team should standardize the casing in documentation so readers can recognize it easily.

A cookie is not a regular header parameter in an OpenAPI contract. When represented in OpenAPI 3, a cookie parameter has location `in: cookie`; Springdoc can infer this location from `@CookieValue`.

## 2. Reading Headers with `@RequestHeader`

Spring MVC's `@RequestHeader` binds a method parameter to a header value in the HTTP request. You can specify the header name using the `name` or `value` attribute:

```java
@GetMapping("/client-info")
public String getClientInfo(
        @RequestHeader(name = "X-Client-Version") String clientVersion) {
    return "Client version: " + clientVersion;
}
```

If `required` is not specified, Spring treats the header as mandatory by default. When a request omits the header, Spring MVC typically returns `400 Bad Request` because it cannot bind the required parameter.

### Optional Headers

To make a header optional, set `required = false` and handle the missing-value case:

```java
@GetMapping("/client-info")
public String getClientInfo(
        @RequestHeader(name = "X-Client-Version", required = false)
        String clientVersion) {

    String effectiveVersion = clientVersion == null
        ? "unknown"
        : clientVersion;

    return "Client version: " + effectiveVersion;
}
```

When the header is not sent, the parameter value may be `null`. If default logic applies, express it clearly in both code and API documentation so clients understand the behavior when omitting the header.

### Headers with a Default Value

Spring allows declaring `defaultValue`:

```java
@GetMapping("/client-info")
public String getClientInfo(
        @RequestHeader(
            name = "X-Client-Version",
            defaultValue = "unknown"
        ) String clientVersion) {
    return "Client version: " + clientVersion;
}
```

When `defaultValue` is set, Spring automatically treats the parameter as optional. If the header is absent or empty, Spring uses the default value. When documentation is generated, inspect both `required` and `schema.default` in the OpenAPI JSON since representation details may depend on the Springdoc version.

## 3. Describing Headers with `@Parameter`

Springdoc typically infers the name, location, and required status from `@RequestHeader`. Use `@Parameter` to supplement information for documentation readers:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;

@GetMapping("/api/client-settings")
@Operation(summary = "Get client settings")
public String getClientSettings(
        @Parameter(
            description = "Client application version in use",
            example = "2.4.0"
        )
        @RequestHeader(name = "X-Client-Version", required = false)
        String clientVersion) {
    return clientVersion == null ? "default settings" : clientVersion;
}
```

`description` explains the header's meaning; `example` shows a valid value. For headers with specific formats, document additional rules such as SemVer versioning, tenant codes, BCP 47 language tags, or internal trace ID conventions.

For deeper customization, `@Parameter` supports attributes such as `name`, `required`, `deprecated`, `allowEmptyValue`, `schema`, `example`, and `examples`. Do not declare `required` in conflict with `@RequestHeader(required = ...)`; the Spring annotation still governs how Spring MVC binds the request, while OpenAPI metadata must reflect that same behavior.

### Multi-Value Headers

Some headers can carry multiple values or appear multiple times. You can use an appropriate collection type to receive those values, depending on how Spring MVC converts the header:

```java
@GetMapping("/api/search")
public String search(
        @RequestHeader(name = "X-Feature", required = false)
        List<String> features) {
    return String.valueOf(features);
}
```

If the contract permits multiple values, inspect the schema and parameter serialization generated by Springdoc. Agree on whether clients send multiple values by repeating the header or using comma-separated syntax, as representation depends on each header's definition.

## 4. Reading Cookies with `@CookieValue`

`@CookieValue` binds a method parameter to a cookie with a specific name. Example reading the `theme` cookie:

```java
@GetMapping("/api/preferences/theme")
public String getTheme(
        @CookieValue(name = "theme") String theme) {
    return "Current theme: " + theme;
}
```

If the `theme` cookie is absent from the request, Spring treats the cookie as required by default and binding may fail with `400 Bad Request`.

### Optional Cookies

Cookies are often created after a user's first visit, so the API may need to accept cases where the cookie does not exist yet:

```java
@GetMapping("/api/preferences/theme")
public String getTheme(
        @CookieValue(name = "theme", required = false) String theme) {

    String effectiveTheme = theme == null ? "light" : theme;
    return "Current theme: " + effectiveTheme;
}
```

In this case, `theme` is an optional cookie and the application uses `light` when the client has no cookie yet. Document the default value so integrators understand the outcome.

### Cookies with a Default Value

`defaultValue` can be used similarly to `@RequestHeader`:

```java
@GetMapping("/api/preferences/locale")
public String getLocale(
        @CookieValue(name = "locale", defaultValue = "vi") String locale) {
    return locale;
}
```

When the cookie is absent or empty, Spring uses `vi`. Setting `defaultValue` also makes the cookie optional during binding.

## 5. Describing Cookies with `@Parameter`

Springdoc recognizes `@CookieValue` to generate a cookie parameter. You can add descriptions and examples as follows:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/preferences")
@Operation(summary = "Read UI preferences")
public String getPreferences(
        @Parameter(
            description = "Cookie storing user UI theme",
            example = "dark"
        )
        @CookieValue(name = "theme", required = false)
        String theme) {
    return theme == null ? "light" : theme;
}
```

In the OpenAPI 3 document, the corresponding parameter generally looks like:

```yaml
parameters:
  - name: theme
    in: cookie
    required: false
    description: Cookie storing user UI theme
    schema:
      type: string
    example: dark
```

`in: cookie` distinguishes a cookie from a header parameter with `in: header`. Do not manually declare a header named `Cookie` instead of `@CookieValue`; Spring MVC already provides an abstraction to read cookies by name.

## 6. Example Combining Headers and Cookies in One Controller

The following example describes an endpoint returning client display preferences. Client version and language are sent via headers; UI theme is stored in a cookie:

```java
package com.example.preferences;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/preferences")
@Tag(name = "Preferences", description = "Client display preferences")
public class PreferenceController {

    @GetMapping
    @Operation(summary = "Get display preferences")
    public PreferenceResponse getPreferences(
            @Parameter(
                description = "Client application version",
                example = "2.4.0"
            )
            @RequestHeader(name = "X-Client-Version", required = false)
            String clientVersion,

            @Parameter(
                description = "Client preferred language",
                example = "vi"
            )
            @RequestHeader(name = "Accept-Language", required = false)
            String acceptLanguage,

            @Parameter(
                description = "Cookie storing UI theme",
                example = "dark"
            )
            @CookieValue(name = "theme", required = false)
            String theme) {

        return new PreferenceResponse(
            clientVersion == null ? "unknown" : clientVersion,
            acceptLanguage == null ? "vi" : acceptLanguage,
            theme == null ? "light" : theme
        );
    }

    public record PreferenceResponse(
        String clientVersion,
        String language,
        String theme
    ) {}
}
```

Sample request with curl:

```bash
curl -i http://localhost:8080/api/preferences \
  -H "X-Client-Version: 2.4.0" \
  -H "Accept-Language: vi" \
  --cookie "theme=dark"
```

The response may look like:

```json
{
  "clientVersion": "2.4.0",
  "language": "vi",
  "theme": "dark"
}
```

When optional headers or cookies are omitted, the controller uses the fallback values written in code. OpenAPI documentation should accurately reflect this optionality and explain the fallback behavior.

## 7. Headers That Should Not Be Documented as Regular Parameters

Not every header should be declared with `@RequestHeader` for Springdoc to include in the parameter list.

- **`Authorization`:** if the header is used for Bearer tokens, OAuth2, or API keys, describe it with `@SecurityScheme` and `@SecurityRequirement`. This produces the proper security model in OpenAPI and enables Swagger UI's Authorize button.
- **`Accept`:** typically represented via response media types (`responses.content`) and content negotiation mechanisms.
- **`Content-Type`:** typically represented via request body media types (`requestBody.content`).
- **`Cookie`:** is a composite header containing request cookies; to document a specific cookie by name, use `@CookieValue` to represent `in: cookie`.
- **`Set-Cookie`:** is a response header used to send cookies back to the browser; it is not an input parameter and is not read with `@CookieValue`.

OpenAPI defines special handling for certain headers such as `Accept`, `Content-Type`, and `Authorization` when declared as header parameters. Therefore, use the OpenAPI structure that fits each header's semantics rather than documenting everything as an arbitrary string.

## 8. Distinguishing Request Cookies from Creating Response Cookies

`@CookieValue` only reads cookies that the client has already sent. If the server needs to create or update a cookie, the server must send a `Set-Cookie` response header. Example:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/api/preferences/theme")
public ResponseEntity<Void> saveTheme() {
    ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(60 * 60 * 24 * 30)
        .build();

    return ResponseEntity.noContent()
        .header(HttpHeaders.SET_COOKIE, cookie.toString())
        .build();
}
```

`HttpOnly`, `Secure`, `SameSite`, `Path`, `Domain`, and cookie max-age are attributes that affect how browsers store and send cookies. Choose values suited to your security requirements and usage scope. The example above illustrates how to send a cookie; actual values and policies must be determined by the application.

For session cookies, never place real session values or tokens in OpenAPI examples. If a cookie serves authentication, describe it using an API key security scheme with location `cookie` when appropriate for the contract, while implementing real security on the server.

## 9. Notes on Browser Cookies and CORS

Browsers manage cookies automatically based on domain, path, expiration, `Secure`, `SameSite`, and privacy policies. JavaScript cannot manually set the `Cookie` header in `fetch`; the browser decides which cookies are sent.

When calling APIs across origins, pay attention to:

- Browser requests must enable sending credentials, such as `credentials: "include"` with Fetch when appropriate.
- The server must configure CORS to allow credentials and declare explicit origins; do not use wildcard `*` together with `Access-Control-Allow-Credentials: true`.
- Cross-site cookies typically require `SameSite=None; Secure`; browser policies may continue to restrict third-party cookies.
- `HttpOnly` cookies are still sent automatically by the browser when conditions are met, though JavaScript cannot read their values.

Swagger UI can display cookie parameters in documentation, but the ability to enter and send cookies when clicking **Try it out** also depends on the Swagger UI version, origin, and browser policies. For browser-managed cookies, inspect the actual request in the Network tab instead of assuming the UI can override the `Cookie` header.

## 10. How to Inspect OpenAPI Generated by Springdoc

After starting the application, open `/v3/api-docs` and find the corresponding operation. Headers and cookies are typically represented as follows:

```json
{
  "parameters": [
    {
      "name": "X-Client-Version",
      "in": "header",
      "required": false,
      "schema": {
        "type": "string"
      },
      "example": "2.4.0"
    },
    {
      "name": "theme",
      "in": "cookie",
      "required": false,
      "schema": {
        "type": "string"
      },
      "example": "dark"
    }
  ]
}
```

This is an illustrative excerpt, not a complete application document. When verifying, confirm:

1. Parameter names match `name` in `@RequestHeader` or `@CookieValue` exactly.
2. Headers have `in: header`; cookies have `in: cookie`.
3. `required` reflects `required` and `defaultValue` of the Spring annotation.
4. Descriptions, examples, and schemas express the right value format.
5. Operations still have accurate responses and schemas.

Swagger UI can present these parameters in the Parameters section. Test requests with valid values and requests missing optional parameters to verify server behavior. For cookies, inspect the Network tab to see which cookies the browser actually sends.

## 11. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Request missing header returns `400` | `@RequestHeader` has `required = true` | Set `required = false` or send the required header |
| Request missing cookie returns `400` | `@CookieValue` has `required = true` | Set `required = false` or configure `defaultValue` |
| Parameter does not appear in OpenAPI | Controller not scanned by Spring, invalid mapping, or annotation not recognized by Springdoc | Check controller and `/v3/api-docs` |
| Cookie appears as header instead of cookie | Incorrectly declared `@RequestHeader("Cookie")` | Use `@CookieValue(name = "...")` |
| Incorrect description or example | Missing `@Parameter` or conflicting metadata | Check annotations and generated OpenAPI JSON |
| Browser does not send cookie | Incompatible domain, path, SameSite, Secure, credentials, or CORS | Check cookie attributes and request in Network |
| Cookie not created after calling API | Using `@CookieValue` expecting server to write a cookie | Return a `Set-Cookie` response header |
| Token does not show Authorize button | Token documented as a regular header parameter | Declare security scheme and security requirement |

## 12. Header and Cookie Documentation Checklist

- [ ] Every header is declared with `@RequestHeader` using an explicit name.
- [ ] Every input cookie is read with `@CookieValue` using the exact cookie name.
- [ ] `required` accurately reflects behavior when values are missing.
- [ ] `defaultValue` and fallback logic are clearly documented.
- [ ] `@Parameter` includes helpful descriptions and examples.
- [ ] `Authorization`, `Accept`, or `Content-Type` are not documented as arbitrary parameters when OpenAPI has dedicated structures.
- [ ] Authentication cookies are documented with an appropriate security scheme without placing secrets in examples.
- [ ] Response cookies are sent via `Set-Cookie` with appropriate attributes.
- [ ] Verified `in: header` and `in: cookie` in `/v3/api-docs`.
- [ ] Tested real requests, including missing optional headers/cookies and CORS cases if called from a browser.

`@RequestHeader` and `@CookieValue` enable controllers to receive client metadata and state following standard HTTP mechanics. Springdoc translates those declarations into header/cookie parameters in OpenAPI, while `@Parameter` clarifies usage. When documentation accurately reflects requiredness, examples, and cookie policies, clients can integrate APIs easily and avoid confusion among headers, input cookies, response cookies, and authentication credentials.

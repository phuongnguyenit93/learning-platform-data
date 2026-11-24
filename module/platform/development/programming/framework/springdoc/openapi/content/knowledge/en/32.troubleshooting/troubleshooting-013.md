# Message Converter Errors When Replacing Spring Defaults

When changing Spring MVC's default `HttpMessageConverter` list, the application may still start and simple controllers may still run, while the OpenAPI endpoint or Swagger UI fails. Typical symptoms include Swagger UI reporting it is unable to render definition, `/v3/api-docs` returning HTTP 500, or logs reporting no converter found to write the response.

The cause usually lies in the converter list having been replaced or ordered improperly. springdoc requires appropriate converters to return the OpenAPI document and Swagger UI configuration. The springdoc FAQ explicitly states that when overriding Spring's default registered converters, both `ByteArrayHttpMessageConverter` and the corresponding JSON converter must be present; registration order also matters.

With Spring Boot 3 and Spring Framework 6, the JSON converter is typically `MappingJackson2HttpMessageConverter`. With Spring Boot 4 and Spring Framework 7, the default stack moves to Jackson 3 and `JacksonJsonHttpMessageConverter`. Use the exact classes matching your application's dependency versions.

## 1. What Does `HttpMessageConverter` Do?

In Spring MVC, `HttpMessageConverter` reads request bodies into Java objects and writes Java objects to HTTP response bodies. Spring selects a converter based on data type, media type, and the registered converter list.

Examples:

| HTTP exchange | Typical participating converter |
| --- | --- |
| JSON request to DTO | Jackson JSON converter |
| DTO to JSON response | Jackson JSON converter |
| Byte array to response | `ByteArrayHttpMessageConverter` |
| String to text response | `StringHttpMessageConverter` |
| Form URL encoded | `FormHttpMessageConverter` |
| Multipart upload | `AllEncompassingFormHttpMessageConverter` and per-part converters |
| Resource or file response | `ResourceHttpMessageConverter` |

Spring Boot auto-configures a converter list matching dependencies on the classpath. If the application has Jackson, objects are typically read/written as JSON. If an appropriate XML module is present, the application can support XML. Strings are written as UTF-8 by default.

This converter is not `Converter<S,T>` used to convert values in `@PathVariable` or `@RequestParam`. `HttpMessageConverter` handles HTTP bodies; `Converter`, `Formatter`, and `ConversionService` handle binding value conversion.

## 2. Spring Selects Converters by `Content-Type` and `Accept`

Two headers to distinguish:

- `Content-Type`: format of the request body sent by the client. Spring uses it to pick a converter to read the request.
- `Accept`: response format accepted by the client. Spring uses it together with `produces` to pick a converter to write the response.

Example client sending JSON and expecting JSON:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":"C-100"}
~~~

Controller receiving a DTO and returning a DTO:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Spring needs a converter capable of reading `CreateOrderRequest` from `application/json` and a converter capable of writing `OrderResponse` as `application/json`. Without a matching converter, the request or response fails even when the controller method is invoked properly.

`/v3/api-docs` is also an HTTP endpoint. springdoc builds an OpenAPI model and Spring MVC must write that model to the response body. Consequently, the application's converter configuration directly affects whether Swagger UI can load the specification.

## 3. Signs of Converter Errors Breaking springdoc

Common symptoms:

| Symptom | What to inspect |
| --- | --- |
| Swagger UI shows "Unable to render definition" | Network requests to `/v3/api-docs` and `/v3/api-docs/swagger-config` |
| `/v3/api-docs` returns 500 | Logs for `HttpMessageNotWritableException`, `No converter for ...`, or serialization errors |
| `/v3/api-docs` returns JSON yet Swagger UI fails to load | Check `swagger-config`, `Content-Type`, response body, and configured URLs |
| API accepting JSON returns 415 | No converter reads the request `Content-Type` or `consumes` mismatches |
| API returns 406 | No converter writes response matching `Accept`/`produces` |
| Error appears only after adding a custom converter | New converter may accept overly broad media types or sit in the wrong order |
| File/byte response breaks after replacing converters | Check `ByteArrayHttpMessageConverter` and `ResourceHttpMessageConverter` |

A typical error in logs:

~~~text
HttpMessageNotWritableException:
No converter for [class ...] with preset Content-Type 'application/json'
~~~

This message means Spring found no converter able to write the returned data type with the selected content type. Do not edit controllers or OpenAPI annotations before inspecting the converter list.

## 4. Why Replacing Default Converters Can Break Swagger UI

In Spring MVC, `configureMessageConverters` is the hook to configure the converter list. When an application manually populates this list, default behavior can change. If the new list only contains a JSON converter, other converters such as byte array, string, resource, or form may no longer be registered as before.

The springdoc FAQ highlights a specific case: Swagger UI fails to render definitions when an application overrides Spring's default registered `HttpMessageConverter`s. springdoc's guidance requires registering both:

- `ByteArrayHttpMessageConverter`
- `MappingJackson2HttpMessageConverter` with an appropriate `ObjectMapper`

Example per springdoc's guidance for the Jackson 2 stack:

~~~java
converters.add(new ByteArrayHttpMessageConverter());
converters.add(new MappingJackson2HttpMessageConverter(jacksonBuilder.build()));
~~~

The two converters serve different body types. `ByteArrayHttpMessageConverter` reads/writes `byte[]`; the Jackson converter reads/writes JSON objects. Replacing the converter list while omitting either one can cause some springdoc responses not to be written properly.

Order also matters. Spring tries converters in registration order and picks the first matching converter. A custom converter supporting `*/*` or broad media types can claim responses ahead of specialized converters. When adding a converter, check `canRead`, `canWrite`, `supportedMediaTypes`, and its position in the list.

## 5. Distinguishing `configureMessageConverters` and `extendMessageConverters`

These two methods have different purposes:

| Method | Meaning | When to use |
| --- | --- | --- |
| `configureMessageConverters` | Configure the converter list yourself | When intentionally replacing the entire list and taking responsibility for registering all required converters |
| `extendMessageConverters` | Modify or append after the list has been created | When only adding a converter or adjusting default converters |

In Spring Framework, `configureMessageConverters` receives an initially empty list. Adding converters here can disable Spring Framework's default converter registration. `extendMessageConverters` is called after the list has been configured and is the more suitable point for adding converters while keeping defaults intact.

In Spring Boot, auto-configuration also contributes converter beans and default converters. However, do not rely on internal differences between versions to accidentally wipe the whole list. For standard needs, prefer Spring Boot's additive mechanisms or `extendMessageConverters`.

## 6. Preferred Fix: Keep Default MVC Configuration and Extend Converters

If you only need to add a converter for a custom format, use `extendMessageConverters`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new VendorDocumentHttpMessageConverter());
    }
}
~~~

`VendorDocumentHttpMessageConverter` is an application-specific converter. Place it at index zero only if it has a narrow media type and will not hijack content types handled by other converters. If a converter supports `*/*`, do not place it ahead of JSON or byte-array converters without verifying impact.

When you only want to customize the `ObjectMapper` of the existing JSON converter, locate the already-registered Jackson converter and configure it instead of building a brand-new list:

~~~java
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class JacksonMvcConfiguration implements WebMvcConfigurer {

    private final ObjectMapper objectMapper;

    JacksonMvcConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        for (HttpMessageConverter<?> converter : converters) {
            if (converter instanceof MappingJackson2HttpMessageConverter jackson) {
                jackson.setObjectMapper(objectMapper);
            }
        }
    }
}
~~~

This example targets Spring Boot 3 / Spring Framework 6 with Jackson 2. The default converter list is still created beforehand by Spring Boot; the code only updates the `ObjectMapper` on the existing Jackson converter.

If the application has multiple Jackson converters for different media types, replace only the converters that genuinely need the shared mapper. Do not assume there is only one converter when the application supports JSON, XML, or vendor media types.

## 7. Ensuring `ByteArrayHttpMessageConverter` Is Present

When managing the converter list manually, verify the presence of the byte-array converter. The example below targets Spring MVC with Jackson 2:

~~~java
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.ByteArrayHttpMessageConverter;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class OpenApiConverterConfiguration implements WebMvcConfigurer {

    private final ObjectMapper objectMapper;

    OpenApiConverterConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        boolean hasByteArray = false;
        boolean hasJacksonJson = false;

        for (HttpMessageConverter<?> converter : converters) {
            if (converter instanceof ByteArrayHttpMessageConverter) {
                hasByteArray = true;
            }
            if (converter instanceof MappingJackson2HttpMessageConverter jackson) {
                jackson.setObjectMapper(objectMapper);
                hasJacksonJson = true;
            }
        }

        if (!hasByteArray) {
            converters.add(0, new ByteArrayHttpMessageConverter());
        }

        if (!hasJacksonJson) {
            converters.add(new MappingJackson2HttpMessageConverter(objectMapper));
        }
    }
}
~~~

This checks and supplements the list already configured by Spring MVC. It does not replace other converters. If the initial list is empty because the application intentionally disabled auto-configuration, adding only those two converters may not suffice for all controllers; restore proper MVC configuration or register all needed converters.

Do not mechanically add duplicate converters. Check the current list first and append only what is missing. Duplicate converters create order-dependent selection and complicate debugging.

## 8. When Using `configureMessageConverters` to Replace the Entire List

Use this only when the application intentionally owns the full converter list. Minimal example for a Spring MVC application with very specific requirements:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.ByteArrayHttpMessageConverter;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.ResourceHttpMessageConverter;
import org.springframework.http.converter.StringHttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class CompleteMvcConverterConfiguration implements WebMvcConfigurer {

    private final ObjectMapper objectMapper;

    CompleteMvcConverterConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void configureMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(new ByteArrayHttpMessageConverter());
        converters.add(new StringHttpMessageConverter(StandardCharsets.UTF_8));
        converters.add(new ResourceHttpMessageConverter());
        converters.add(new MappingJackson2HttpMessageConverter(objectMapper));
    }
}
~~~

This is only an abbreviated example, not a complete list for every application. Depending on needs, form, multipart, XML, source, feed, or custom format converters may also be required. Replacing the list makes you responsible for every request/response the application must support, including springdoc and Swagger UI endpoints.

If the goal is merely adding one converter, do not use `configureMessageConverters` this way. Use `extendMessageConverters` or the `HttpMessageConverters` mechanism for your Spring Boot version.

## 9. Using `HttpMessageConverters` in Spring Boot 3

Spring Boot 3.x has `org.springframework.boot.autoconfigure.http.HttpMessageConverters`. This mechanism lets you contribute extra converters while retaining defaults:

~~~java
import org.springframework.boot.autoconfigure.http.HttpMessageConverters;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;

@Configuration(proxyBeanMethods = false)
class BootHttpConvertersConfiguration {

    @Bean
    HttpMessageConverters customConverters() {
        HttpMessageConverter<?> custom =
            new VendorDocumentHttpMessageConverter();
        return new HttpMessageConverters(custom);
    }
}
~~~

In Spring Boot 3.5, the constructor accepting additional converters places custom converters alongside matching default converters or at the front of the list if no matching type exists. You can subclass `HttpMessageConverters` and override `postProcessConverters` to fine-tune order or remove default converters.

Do not create an `HttpMessageConverters` bean with `addDefaultConverters=false` without a clear reason and manually registering all needed converters. Doing so can reproduce the exact error preventing OpenAPI endpoints from writing responses.

## 10. Customizing Jackson Without Replacing All Converters

If you only need date formatting, inclusion rules, or Jackson modules, configure the builder/mapper via Spring Boot mechanisms rather than building a new converter list.

Example with Spring Boot 3 and Jackson 2:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> builder.serializationInclusion(
            JsonInclude.Include.NON_NULL
        );
    }
}
~~~

`Jackson2ObjectMapperBuilderCustomizer` tunes the builder Spring Boot uses to construct the mapper. JSON converters continue using the Boot-configured mapper. After changing serialization rules, still test API responses and the OpenAPI document because the shared mapper can affect multiple endpoints.

Do not instantiate a new `ObjectMapper` missing modules just to solve a converter error. A custom mapper can drop Java Time, Kotlin, Optional, parameter names, or serializers the application relies on.

## 11. Notes on Spring Boot 4 and Jackson 3

Spring Boot 4 moves to Jackson 3 as the default JSON stack. Therefore, examples using `MappingJackson2HttpMessageConverter` and `Jackson2ObjectMapperBuilderCustomizer` belong to the Jackson 2 generation; do not copy them verbatim into a Boot 4 application.

In Spring Boot 4, the default JSON converter is `JacksonJsonHttpMessageConverter`, using `tools.jackson.databind.json.JsonMapper`. Spring Boot provides `ServerHttpMessageConvertersCustomizer` to customize server-side converters.

Example replacing the JSON converter in Boot 4:

~~~java
import org.springframework.boot.http.converter.autoconfigure.ServerHttpMessageConvertersCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.json.JacksonJsonHttpMessageConverter;
import tools.jackson.databind.json.JsonMapper;

@Configuration(proxyBeanMethods = false)
class Boot4JsonConverterConfiguration {

    @Bean
    ServerHttpMessageConvertersCustomizer serverJsonCustomizer() {
        JsonMapper jsonMapper = JsonMapper.builder().build();
        return builder -> builder.withJsonConverter(
            new JacksonJsonHttpMessageConverter(jsonMapper)
        );
    }
}
~~~

If you need to add a byte-array converter in Boot 4, use the same builder:

~~~java
return builder
    .addCustomConverter(new ByteArrayHttpMessageConverter())
    .withJsonConverter(new JacksonJsonHttpMessageConverter(jsonMapper));
~~~

Builder APIs and packages may change across minor versions; check the Spring Boot reference for your exact version. The springdoc FAQ currently shows a `MappingJackson2HttpMessageConverter` example for Jackson 2, yet Jackson 2 classes should not be applied to Boot 4 if the application moved to Jackson 3.

Dependency selection guide:

| Spring Boot | Spring Framework | springdoc-openapi | Typical default JSON converter |
| --- | --- | --- | --- |
| 2.x | 5.x | springdoc 1.x | `MappingJackson2HttpMessageConverter` |
| 3.x | 6.x | springdoc 2.x | `MappingJackson2HttpMessageConverter` |
| 4.x | 7.x | springdoc 3.x | `JacksonJsonHttpMessageConverter` |

This is a major-version guide. Check the official compatibility matrix before upgrading or choosing a specific version.

## 12. Do Not Add `@EnableWebMvc` Just to Fix Converters

In Spring Boot, `@EnableWebMvc` signals that the application wants full control over Spring MVC configuration. Adding this annotation can disable Boot auto-configurations such as static resources, WebJars, and default MVC integrations.

If you only want to add interceptors, formatters, resource handlers, or converters, implement `WebMvcConfigurer` without adding `@EnableWebMvc`:

~~~java
@Configuration
class WebConfiguration implements WebMvcConfigurer {
    // Override only the required hooks.
}
~~~

Only use `@EnableWebMvc` when intentionally taking over MVC configuration and manually configuring every needed component. Adding it to fix Swagger UI can create new problems with static resources, welcome pages, or other endpoints.

## 13. Checking Converter Order and Media Types

Spring iterates through the converter list in order. An earlier converter can be chosen first if it supports the response's Java type and media type. When clients send `Accept: */*`, multiple converters may match, making order even more critical.

A custom converter should declare narrow media types:

~~~java
public VendorDocumentHttpMessageConverter() {
    setSupportedMediaTypes(
        List.of(MediaType.valueOf("application/vnd.example.document+json"))
    );
}
~~~

Do not declare `MediaType.ALL` if the converter only handles one specific format. If a converter must support multiple media types, clearly restrict which Java types it reads/writes and inspect its order relative to Jackson, byte-array, string, and resource converters.

After changing order, test both normal JSON requests and OpenAPI endpoints. Do not test only a controller returning a simple DTO because it may not follow the same path as byte arrays or `swagger-config`.

## 14. Distinguishing Converter Errors from Content Negotiation Errors

HTTP statuses suggest investigation directions:

| Status/error | Common meaning | Check |
| --- | --- | --- |
| 400 / `HttpMessageNotReadableException` | Converter read request yet body is invalid or un-deserializable | JSON syntax, DTO types, Jackson modules |
| 406 / `HttpMediaTypeNotAcceptableException` | Cannot write response matching `Accept` or `produces` | Supported media types, converter `canWrite` |
| 415 / `HttpMediaTypeNotSupportedException` | Cannot read request `Content-Type` | Converter `canRead`, `consumes`, request header |
| 500 / `HttpMessageNotWritableException` | Cannot serialize/write response | Converter for return type, mapper, and content type |
| Swagger UI does not render | Spec or `swagger-config` failed to load or is invalid OpenAPI JSON | Network response, HTTP status, `Content-Type`, and body |

Not every Swagger UI failure is caused by converters. If `/v3/api-docs` returns 401/403, check Spring Security. If it returns 404, check `springdoc.api-docs.path`, context path, or whether springdoc is enabled. If it returns 200 with an HTML login page body, the issue lies in security redirects or a proxy rather than the JSON converter.

## 15. Testing OpenAPI Endpoints with `curl`

First test the JSON endpoint directly:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/v3/api-docs
~~~

A successful response must have status 200 and a JSON body containing `openapi`, `info`, and `paths` per the generated document.

Check `swagger-config`:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/v3/api-docs/swagger-config
~~~

If Swagger UI loads the HTML page yet fails to render APIs, inspect these two requests in the browser Network tab. Separate static JavaScript/CSS files from the dynamic config and OpenAPI endpoints.

Test YAML if the application enables the YAML endpoint:

~~~bash
curl -i \
  -H "Accept: application/yaml" \
  http://localhost:8080/v3/api-docs.yaml
~~~

If JSON works while YAML fails, check YAML-specific configuration and support; do not conclude all JSON converters are broken.

## 16. Inspecting the Converter List in the Application

You can log converter classes, order, and supported media types in `extendMessageConverters`:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    for (int index = 0; index < converters.size(); index++) {
        HttpMessageConverter<?> converter = converters.get(index);
        log.info(
            "HTTP converter [{}]: {} supports {}",
            index,
            converter.getClass().getName(),
            converter.getSupportedMediaTypes()
        );
    }
}
~~~

The snippet above requires an application logger. Use logging in development or during incident investigation; avoid excessive logging in production when the list never changes.

Review the list against these goals:

- A converter exists that writes JSON for the OpenAPI document.
- `ByteArrayHttpMessageConverter` is present as required by the springdoc FAQ for override setups.
- Converters exist for the response types the API actually returns.
- Media types and ordering do not let a broad converter intercept responses meant for specialized converters.
- No custom converter alters `Content-Type` unexpectedly.

## 17. Testing the OpenAPI Endpoint with MockMvc

After fixing converters, add integration tests to catch regressions. Test the OpenAPI endpoint directly:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiMessageConverterTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void writesOpenApiDocumentAsJson() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.paths").isMap());
    }

    @Test
    void writesSwaggerConfigurationAsJson() throws Exception {
        mockMvc.perform(get("/v3/api-docs/swagger-config")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }
}
~~~

If the application has a custom API docs path or context path, update test URLs to match actual configuration. If Spring Security protects docs, add authentication or appropriate test security config; never disable production security just to pass tests.

This test checks both JSON content and `swagger-config`. Testing only business controllers can miss converter failures in springdoc.

## 18. Testing Converters for Byte Arrays and Standard APIs

Beyond the OpenAPI endpoint, test a file/byte-array endpoint if the application has that response type:

~~~java
@GetMapping(
    path = "/api/reports/{id}/download",
    produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
)
public ResponseEntity<byte[]> download(@PathVariable UUID id) {
    byte[] content = reportService.load(id);
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(content);
}
~~~

Test:

~~~java
mockMvc.perform(get("/api/reports/{id}/download", reportId)
        .accept(MediaType.APPLICATION_OCTET_STREAM))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_OCTET_STREAM
    ));
~~~

If the application has no file endpoint, do not create a dummy endpoint just to test. You can check for `ByteArrayHttpMessageConverter` in the converter list and test `swagger-config`/OpenAPI endpoints.

## 19. When Using Spring WebFlux

`HttpMessageConverter` belongs to the Spring MVC/Servlet stack. Spring WebFlux uses a codec system with `HttpMessageReader` and `HttpMessageWriter`, configured via `WebFluxConfigurer#configureHttpMessageCodecs` or `CodecConfigurer`.

Therefore, do not directly apply `WebMvcConfigurer`, `extendMessageConverters`, or `MappingJackson2HttpMessageConverter` to a WebFlux application. Check the starter stack:

| Stack | Conversion mechanism |
| --- | --- |
| Spring MVC | `HttpMessageConverter` |
| Spring WebFlux | `HttpMessageReader` / `HttpMessageWriter`, codecs |

If the project uses `springdoc-openapi-starter-webflux-*`, diagnose JSON codecs and WebFlux configuration accordingly. Do not add `@EnableWebMvc` or MVC converters into a WebFlux application to fix errors.

## 20. Step-by-Step Diagnostic Procedure

1. Call `/v3/api-docs` directly with `Accept: application/json` and record status, `Content-Type`, and body.
2. Call `/v3/api-docs/swagger-config` to determine whether the error lies in the document or Swagger UI config.
3. Read server logs for `HttpMessageNotWritableException`, `No converter for`, `HttpMediaTypeNotAcceptableException`, or Jackson errors.
4. Confirm whether the stack is Spring MVC or WebFlux.
5. Check Spring Boot, Spring Framework, springdoc, and Jackson major versions.
6. Search for `configureMessageConverters`, `@EnableWebMvc`, `HttpMessageConverters` beans, and custom converter beans.
7. Log converter order, classes, and supported media types.
8. Ensure JSON converter and `ByteArrayHttpMessageConverter` are present if using MVC and overriding the list as described in the springdoc FAQ.
9. Move converter additions to `extendMessageConverters` or the appropriate Spring Boot customizer mechanism.
10. Re-test Swagger UI, JSON/YAML endpoints, and APIs returning DTOs, Strings, Resources, or byte arrays.

## 21. Error-Prone Configurations

**Adding only a Jackson converter in `configureMessageConverters`.** A manually populated list can drop default converters. Add byte-array and other required converters, or switch to `extendMessageConverters`.

**Missing `ByteArrayHttpMessageConverter`.** The springdoc FAQ requires this converter when overriding default converters. Check and register it in the MVC stack.

**Using `MappingJackson2HttpMessageConverter` in Spring Boot 4.** That is a Jackson 2 converter. Boot 4 uses Jackson 3; choose `JacksonJsonHttpMessageConverter` and Boot 4's customizer API.

**Placing a custom converter supporting `*/*` at the head of the list.** That converter can intercept responses intended for specialized converters. Narrow supported media types and check ordering.

**Creating a new `ObjectMapper` missing modules.** Java Time, Optional, or Kotlin DTOs may fail to serialize properly. Customize the Boot-managed mapper or register all required modules.

**Adding `@EnableWebMvc` just to fix converters.** This takes over MVC configuration and can drop other auto-configurations. Use `WebMvcConfigurer` without `@EnableWebMvc` when only extending behavior.

**Checking only Swagger UI HTML.** The HTML page may load while `/v3/api-docs` or `swagger-config` fails. Test API docs requests directly.

**Confusing 401/403 errors with converter errors.** Security may block endpoints before converters write responses. Check status codes and filter chains.

**Confusing 404 with serialization errors.** Verify `springdoc.api-docs.path`, context path, and `springdoc.api-docs.enabled`.

**Testing only business JSON endpoints.** Add tests for `/v3/api-docs` and `/v3/api-docs/swagger-config` to catch springdoc-specific failures.

## 22. Checklist for Restoring Message Converters

- [ ] Confirmed whether the application uses Spring MVC or WebFlux.
- [ ] Recorded exact Spring Boot, Spring Framework, springdoc, and Jackson versions.
- [ ] Tested `/v3/api-docs` directly.
- [ ] Tested `/v3/api-docs/swagger-config`.
- [ ] Read logs to distinguish request-reading vs response-writing errors.
- [ ] Checked whether `configureMessageConverters` replaces the default list.
- [ ] Preferred `extendMessageConverters` when only adding/adjusting converters.
- [ ] Ensured JSON converter matches the major version.
- [ ] Ensured `ByteArrayHttpMessageConverter` is present in MVC override scenarios per springdoc guidance.
- [ ] Checked converter order and `supportedMediaTypes`.
- [ ] Avoided `@EnableWebMvc` unless intentionally taking over all of MVC.
- [ ] Customized `ObjectMapper`/`JsonMapper` through Spring Boot's mechanism.
- [ ] Tested JSON, YAML, `swagger-config`, and APIs returning files/strings/resources.
- [ ] Added MockMvc integration tests to prevent regressions.

## 23. Conclusion

Message converter errors after changing defaults usually occur because the converter list was replaced, the byte-array converter is missing, or the JSON converter mismatches the Spring/Jackson version. In Spring MVC, prefer keeping default converters and using `extendMessageConverters` to add or adjust converters. When genuinely overriding the list, ensure `ByteArrayHttpMessageConverter` and the required JSON converter remain present and properly ordered. Use Jackson 2 converters for Boot 3, and Jackson 3 converters with the corresponding customizer mechanism for Boot 4. Finally, test `/v3/api-docs` and `/v3/api-docs/swagger-config` directly to confirm springdoc works after every MVC change.

## 24. References

- [springdoc-openapi FAQ — Swagger UI unable to render definition when overriding HttpMessageConverter](https://springdoc.org/faq.html): requirement for `ByteArrayHttpMessageConverter`, Jackson converter, and ordering notes when overriding default converters.
- [Spring Framework 6.2 — Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html): differences between `configureMessageConverters` and `extendMessageConverters`, converter selection, and Jackson 2 examples.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): MVC auto-configuration, `HttpMessageConverters`, and adding converters in Boot 3.
- [Spring Boot 3.5 — HttpMessageConverters API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/http/HttpMessageConverters.html): constructors, default converters, and `postProcessConverters`.
- [Spring Boot 4 — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): Jackson 3, `JacksonJsonHttpMessageConverter`, and `ServerHttpMessageConvertersCustomizer`.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): media-type converters such as String, byte array, form, resource, and Jackson.
- [springdoc-openapi FAQ — Spring Boot compatibility matrix](https://springdoc.org/faq.html): mapping springdoc major versions to Spring Boot.

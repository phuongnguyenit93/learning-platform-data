# Localizing Descriptions and Placeholder Resolution

An API may be used by development teams across different countries or markets. When that happens, operation names, descriptions, schema details, and messages in the OpenAPI document need to appear in the appropriate language. Springdoc-openapi integrates with Spring's configuration mechanism and MessageSource to resolve placeholders in specific Swagger annotation fields, while generating OpenAPI documents according to the request locale.

There are two related needs to distinguish:

- **Placeholder resolution:** replacing expressions like ${api.operation.summary} with the corresponding configuration value. Configuration can come from application.yml, environment variables, command-line arguments, or other property sources.
- **Localization (i18n):** the same message key can have different values per Locale, such as Vietnamese, English, or French. Spring's MessageSource selects the translation matching the request's locale.

Springdoc combines both mechanisms in supported annotation fields. Using placeholders does not automatically translate every string in OpenAPI. You must define message keys in resource bundles, enable property resolvers for schemas/extensions when needed, and verify the generated document with each Accept-Language header.

## 1. When Is OpenAPI Documentation Localization Needed?

Treat API documentation as part of the interface for integrators. One development team may prefer reading descriptions in Vietnamese, while partners or operations teams in another environment need English. If the same API serves multiple locales, a single OpenAPI document with hardcoded descriptions will not serve those audiences well.

Parts commonly needing localization:

| OpenAPI Component | Example Content |
|---|---|
| Info | Title, description, terms of service, contact information |
| Operation | Endpoint summary and description |
| Parameter | Display name and description of path/query/header parameters |
| Response | Description of the meaning of an HTTP response |
| Schema | Name, title, and description of a model or field |
| OAuth flow | Authorization, token, refresh, or OpenID Connect URLs when varying by environment |
| Extension | Values of custom extensions if they must vary by locale |

Not every attribute of every Swagger annotation supports placeholder resolution by springdoc. Use only the fields listed in springdoc's documentation; other strings must stay static or be handled with an appropriate OpenApiCustomizer.

## 2. Distinguishing Locale from Spring Profile

Spring profiles and Locales solve two different problems:

| Mechanism | What Does It Determine? | Example |
|---|---|---|
| Spring profile | Which configuration is loaded for a deployment | dev, staging, prod |
| Locale | Which language is used to render content for the current request | vi, en, fr-CA |

Profiles are suited for values that vary by environment, such as server URLs, OAuth client IDs, or API versions. Locales are suited when the same application must return descriptions in multiple languages depending on the reader's request.

If you use application-prod.yml to switch all descriptions to English, every request to the production instance receives English. That does not allow two users calling the same instance to receive two different languages. To support multiple languages simultaneously, use MessageSource and Accept-Language.

## 3. Placeholders in Swagger Annotations

Springdoc supports Spring property resolution for a specific set of fields. You can declare placeholders using ${key} syntax in annotations:

~~~java
@OpenAPIDefinition(
    info = @Info(
        title = "${api.info.title}",
        description = "${api.info.description}",
        version = "${api.info.version}",
        termsOfService = "${api.info.terms-of-service}"
    )
)
@Configuration
class OpenApiConfiguration {}
~~~

For an operation:

~~~java
@Operation(
    summary = "${api.products.get.summary}",
    description = "${api.products.get.description}"
)
@GetMapping("/api/products/{id}")
ProductResponse getProduct(@PathVariable UUID id) {
    return productService.getById(id);
}
~~~

Springdoc resolves the key's value through Spring property resolution and MessageSource according to the active locale. When backed by per-locale message bundles, the same key can return different content without editing annotations or recompiling controllers.

### Fields Supported by springdoc

According to the official FAQ, fields supporting Spring property resolution include:

| Annotation | Supported Fields |
|---|---|
| @Info | title, description, version, termsOfService |
| @Info.license | name, url |
| @Info.contact | name, email, url |
| @Operation | summary, description |
| @Parameter | name, description |
| @ApiResponse | description |
| @OAuthFlow | openIdConnectUrl, authorizationUrl, refreshUrl, tokenUrl |
| @Schema | name, title, description; requires enabling resolve-schema-properties |
| @ExtensionProperty | value; requires enabling resolve-extensions-properties |

The list above represents the scope of documented fields. Do not assume every string attribute in Swagger annotations is automatically resolved. For example, never assume tag names, operationIds, enum values, examples, or arbitrary custom fields are translated simply because summary is translated.

## 4. Declaring Locale Message Bundles

Spring Boot uses MessageSource to read message bundles. With the default basename `messages`, place the following files in src/main/resources:

~~~text
src/main/resources/
  messages.properties
  messages_vi.properties
  messages_en.properties
  messages_fr_CA.properties
~~~

messages.properties is the default/fallback bundle. Files with locale suffixes provide the corresponding translations. Locale names follow Java ResourceBundle rules; for example, fr_CA represents French in Canada.

Example messages.properties:

~~~properties
api.info.title=Store API
api.info.description=API for product catalog and order management.
api.info.version=1.0.0
api.info.terms-of-service=https://example.com/terms
api.products.get.summary=Get a product
api.products.get.description=Returns one product by its identifier.
api.products.id.name=Product identifier
api.products.id.description=Unique identifier assigned to the product.
api.products.response.ok=Product was found.
api.schema.product.name=Product
api.schema.product.description=Product information exposed by the catalog API.
api.products.name.description=Display name of the product.
~~~

Example messages_vi.properties:

~~~properties
api.info.title=API Cửa hàng
api.info.description=API quản lý danh mục sản phẩm và đơn hàng.
api.info.version=1.0.0
api.info.terms-of-service=https://example.com/dieu-khoan
api.products.get.summary=Lấy thông tin sản phẩm
api.products.get.description=Trả về một sản phẩm theo mã định danh.
api.products.id.name=Mã sản phẩm
api.products.id.description=Mã định danh duy nhất được cấp cho sản phẩm.
api.products.response.ok=Đã tìm thấy sản phẩm.
api.schema.product.name=Sản phẩm
api.schema.product.description=Thông tin sản phẩm được công bố bởi API danh mục.
api.products.name.description=Tên hiển thị của sản phẩm.
~~~

Example messages_en.properties:

~~~properties
api.info.title=Store API
api.info.description=API for product catalog and order management.
api.info.version=1.0.0
api.info.terms-of-service=https://example.com/terms
api.products.get.summary=Get a product
api.products.get.description=Returns one product by its identifier.
api.products.id.name=Product identifier
api.products.id.description=Unique identifier assigned to the product.
api.products.response.ok=Product was found.
api.schema.product.name=Product
api.schema.product.description=Product information exposed by the catalog API.
api.products.name.description=Display name of the product.
~~~

For a message key, springdoc uses the request's locale to look up the translation. If a locale file lacks a key, MessageSource applies Spring/Java fallback rules to search the default bundle. Therefore, maintain a complete messages.properties as the default language and avoid unintentionally missing keys.

### Configuring Basename and Encoding

You can explicitly declare the bundle and encoding:

~~~yaml
spring:
  messages:
    basename: messages
    encoding: UTF-8
    fallback-to-system-locale: false
~~~

If bundles are placed in a dedicated directory, such as src/main/resources/i18n/api-docs.properties, configure basename accordingly:

~~~yaml
spring:
  messages:
    basename: i18n/api-docs
    encoding: UTF-8
    fallback-to-system-locale: false
~~~

Then create api-docs.properties, api-docs_vi.properties, and api-docs_en.properties in the same directory. Do not include the .properties suffix in basename. When specifying multiple basenames, separate them using the syntax supported by Spring Boot.

If the project declares a custom MessageSource bean, ensure that bean still reads all required bundles. A custom MessageSource can replace Spring Boot's auto-configuration; forgetting basename or encoding can prevent keys in Swagger annotations from resolving.

## 5. Applying Placeholders to Info, Operation, Parameter, and Response

Once message bundles exist, annotations can hold keys instead of fixed text:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    @Operation(
        operationId = "getProductById",
        summary = "${api.products.get.summary}",
        description = "${api.products.get.description}",
        responses = {
            @ApiResponse(
                responseCode = "200",
                description = "${api.products.response.ok}"
            )
        }
    )
    ProductResponse getProduct(
        @Parameter(
            name = "id",
            description = "${api.products.id.description}"
        )
        @PathVariable UUID id
    ) {
        return productService.getById(id);
    }
}
~~~

In this example, operationId stays stable because it is the technical identifier of the operation. Summary, description, parameter name/description, and response description can be translated. Do not translate operationId by locale because client generators, OpenAPI links, and integrating systems may depend on this identifier.

If an annotation has multiple responses, each @ApiResponse can use its own message key. Name keys by path and response code to avoid reusing a generic key with conflicting meanings.

## 6. Resolving Placeholders in @Schema

Schemas are easily overlooked during localization. Springdoc has a dedicated property to enable resolution for @Schema's name, title, and description fields:

~~~yaml
springdoc:
  api-docs:
    resolve-schema-properties: true
~~~

DTO example:

~~~java
@Schema(
    name = "Product",
    title = "${api.schema.product.name}",
    description = "${api.schema.product.description}"
)
public record ProductResponse(
    @Schema(
        description = "${api.products.id.description}",
        example = "8f1f3f3a-72c2-4e1c-a1c7-3c4f57a10f21"
    )
    UUID id,

    @Schema(
        description = "${api.products.name.description}",
        example = "Ballpoint pen"
    )
    String name
) {}
~~~

When resolve-schema-properties is enabled, springdoc resolves name, title, and description inside schemas. The example above reuses keys for illustration; in a real API, maintain separate keys for the model name, model description, and each field description.

This property defaults to false according to the springdoc configuration table. If you forget to enable it, placeholders in @Schema may appear verbatim inside components.schemas. Enabling the resolver does not alter schema data types, required flags, enums, or validation constraints.

### Avoid Translating JSON Property Names

JSON property names are part of the data contract. You should normally never vary JSON names by locale:

~~~java
public record ProductResponse(
    @JsonProperty("productId")
    UUID id,

    @JsonProperty("displayName")
    String name
) {}
~~~

Field descriptions can change by locale, whereas Product, productId, and displayName must remain stable so Vietnamese and English clients exchange the exact same JSON structure. Never translate component schema names, @JsonProperty names, path segments, query keys, or technical headers if doing so alters the wire contract.

## 7. Resolving ExtensionProperty

OpenAPI extensions allow adding metadata beyond standard fields. If @ExtensionProperty values must come from Spring property resolution or message bundles, enable:

~~~yaml
springdoc:
  api-docs:
    resolve-extensions-properties: true
~~~

Example:

~~~java
@Operation(
    summary = "${api.products.get.summary}",
    extensions = {
        @Extension(
            name = "x-display-label",
            properties = {
                @ExtensionProperty(
                    name = "label",
                    value = "${api.products.extension.label}"
                )
            }
        )
    }
)
~~~

This property defaults to false according to the configuration table. Enable it only when the application actually uses placeholders in extension values. Keep extension names and property names stable; translate only display values if the extension's consumers expect values to vary by locale.

## 8. Selecting Locale from Accept-Language

When a client calls the OpenAPI endpoint, it can send the Accept-Language header to request a locale:

~~~http
GET /v3/api-docs HTTP/1.1
Host: api.example.com
Accept: application/json
Accept-Language: vi
~~~

Requesting English:

~~~http
GET /v3/api-docs HTTP/1.1
Host: api.example.com
Accept: application/json
Accept-Language: en
~~~

Spring resolves the request's locale and springdoc uses that locale when resolving messages. A client can call the same /v3/api-docs endpoint repeatedly with different Accept-Language headers to receive different descriptions while paths, HTTP methods, schema types, and operationIds remain identical.

Verification example using curl:

~~~bash
curl -H "Accept: application/json" \
     -H "Accept-Language: vi" \
     http://localhost:8080/v3/api-docs

curl -H "Accept: application/json" \
     -H "Accept-Language: en" \
     http://localhost:8080/v3/api-docs
~~~

If Accept-Language is omitted, the framework uses the default locale configured by the application and its locale resolver. Do not rely on the host machine's system locale to select the language for public APIs; configure an explicit fallback and provide a default bundle.

### Whitelisting Allowed Locales

Springdoc provides the allowed-locales property to restrict supported locales for OpenAPI:

~~~yaml
springdoc:
  allowed-locales:
    - vi
    - en
    - fr-CA
~~~

This list explicitly defines which locales the application is allowed to serve. Values must match the locale format used by your system; verify behavior against your installed springdoc version, especially when regions like fr-CA are involved. When a request sends a locale outside the list, verify the actual fallback with tests rather than assuming every server handles it identically.

Do not allow hundreds of arbitrary locales if the API officially supports only a few languages. Each additional locale increases the number of bundles to maintain and OpenAPI variants that may be generated/cached.

## 9. Configuring i18n, Preloading, and Schema Resolvers

You can group related settings in application.yml:

~~~yaml
spring:
  messages:
    basename: messages
    encoding: UTF-8
    fallback-to-system-locale: false

springdoc:
  disable-i18n: false
  allowed-locales:
    - vi
    - en
  pre-loading-enabled: true
  pre-loading-locales:
    - vi
    - en
  api-docs:
    resolve-schema-properties: true
    resolve-extensions-properties: true
~~~

Meaning of each property:

| Property | Documented Default | Effect |
|---|---|---|
| springdoc.disable-i18n | false | false allows automatic i18n translation; true disables automatic translation |
| springdoc.allowed-locales | No default list | Restricts locales allowed for OpenAPI |
| springdoc.pre-loading-enabled | false | Pre-generates OpenAPI when the application starts |
| springdoc.pre-loading-locales | No default list | Locales to preload; if unspecified, preloads the default locale |
| springdoc.api-docs.resolve-schema-properties | false | Resolves name, title, and description in @Schema |
| springdoc.api-docs.resolve-extensions-properties | false | Resolves @ExtensionProperty values |

Preloading helps when documents are large or the first request takes time to build schemas. When pre-loading-enabled is on and pre-loading-locales is specified, springdoc can prepare documents for those locales at startup. Preloading does not emit separate static JSON/YAML files and does not replace checking request locales.

### When to Disable i18n?

springdoc.disable-i18n=true can be used when the application does not want springdoc to look up locale-based messages or wants fixed documentation content. Do not enable this property while still expecting Accept-Language to switch description languages. If the application needs property placeholders for environment configuration, test placeholder behavior separately after toggling i18n on your exact springdoc version; do not assume both forms of resolution always turn on/off together.

## 10. Caching OpenAPI per Locale

Generating an OpenAPI document can be expensive because springdoc scans controllers, processes annotations, and builds schemas. According to the current FAQ, springdoc caches one description per locale requested via Accept-Language. As a result:

- Vietnamese requests can reuse the cached document for the Vietnamese locale.
- English requests can reuse the cached document for the English locale.
- The same locale does not need to rebuild the document on every request while caching is enabled.
- The number of supported locales should be controlled to avoid generating excessive variants.

By default, springdoc caches the OpenAPI description. If message contents change dynamically at runtime and must reflect immediately on every request, you can consider:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Disabling the cache can force the document to be recomputed on every request, increasing CPU usage and latency. When bundles live on the classpath and change only upon deployment, it is usually better to keep caching enabled and restart the application when releasing updated translations.

Do not confuse springdoc's cache with HTTP/CDN/reverse proxy caches. If a proxy caches /v3/api-docs without including Accept-Language in the cache key, it may serve the Vietnamese version to an English client or vice versa. When publishing multilingual documentation through a proxy, ensure the cache key respects Accept-Language; if the proxy uses HTTP Vary, verify the response contains Vary: Accept-Language or configure an equivalent cache key.

## 11. Testing OpenAPI Across Locales

Tests should confirm that content is translated and placeholders no longer appear verbatim. You can use MockMvc to send Accept-Language:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiLocalizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsVietnameseDescriptions() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .header(HttpHeaders.ACCEPT_LANGUAGE, "vi"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("API Cửa hàng"))
            .andExpect(jsonPath(
                "$.paths['/api/products/{id}'].get.summary"
            ).value("Lấy thông tin sản phẩm"))
            .andExpect(jsonPath(
                "$.paths['/api/products/{id}'].get.parameters[0].description"
            ).value("Mã định danh duy nhất được cấp cho sản phẩm."));
    }

    @Test
    void returnsEnglishDescriptions() throws Exception {
        mockMvc.perform(get("/v3/api-docs")
                .header(HttpHeaders.ACCEPT_LANGUAGE, "en"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("Store API"))
            .andExpect(jsonPath(
                "$.paths['/api/products/{id}'].get.summary"
            ).value("Get a product"));
    }
}
~~~

This example assumes the controller and bundles use the exact keys from earlier sections. If an operation has multiple parameters, do not rely on index [0]; parse the JSON document and locate the parameter by its stable in/path/name properties.

With WebFlux, use WebTestClient and send the same header:

~~~java
webTestClient.get()
    .uri("/v3/api-docs")
    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.info.title").isEqualTo("API Cửa hàng");
~~~

Beyond translated content, verify these conditions:

1. Requests without Accept-Language receive the expected default language.
2. Whitelisted locales return the right translations.
3. Non-whitelisted locales follow the intended fallback behavior.
4. Missing keys do not cause OpenAPI to emit raw placeholder strings or unexpected text.
5. @Schema descriptions are resolved when resolve-schema-properties is enabled.
6. Extension values are resolved when resolve-extensions-properties is enabled.
7. JSON and YAML return identical content for the same locale.
8. Requests with different locales do not receive the wrong document due to caching or reverse proxies.

## 12. When Annotations Are Not Enough: Using MessageSource in Customizers

Springdoc supports placeholders directly for many annotation fields. For metadata outside the supported list or requiring custom translation rules, use MessageSource inside an OperationCustomizer or OpenApiCustomizer.

Example using OperationCustomizer to replace a description by locale:

~~~java
@Configuration
class LocalizedOperationConfiguration {

    @Bean
    OperationCustomizer localizedProductDescription(MessageSource messageSource) {
        return (operation, handlerMethod) -> {
            if ("getProductById".equals(operation.getOperationId())) {
                Locale locale = LocaleContextHolder.getLocale();
                String description = messageSource.getMessage(
                    "api.products.get.description",
                    null,
                    "Returns a product by its identifier.",
                    locale
                );
                operation.setDescription(description);
            }
            return operation;
        };
    }
}
~~~

MessageSource#getMessage accepts a key, arguments, a default message, and a Locale. Passing a default message ensures the application can still build the document if a bundle lacks a key. LocaleContextHolder supplies the locale bound to the current request during synchronous Spring processing.

Use customizers only when necessary. If a field is already resolved directly from annotations by springdoc, do not overwrite the same field again in a customizer, as that creates two competing sources of truth. With GroupedOpenApi, ensure the customizer is applied to the right group; when applying across both default documents and groups, use the global customizer mechanism appropriate for your springdoc version.

## 13. Values That Should Remain Stable Across Languages

Not all content should be translated. A multilingual OpenAPI document must still describe the exact same HTTP contract:

| Should Localize | Should Keep Stable |
|---|---|
| Info title and description | Paths such as /api/products/{id} |
| Operation summary and description | HTTP methods such as GET, POST |
| Parameter description | Actual parameter names such as id, page, sort |
| ApiResponse description | operationId |
| Schema title and description | JSON property names and enum values |
| Human-facing extension descriptions | Security scheme keys and OAuth scopes |
| Business descriptions and input guidance | Media types and technical headers |

In particular, even though @Parameter.name supports property resolution, do not translate path/query/header parameter names when they are part of the request contract. For example, clients always send the query parameter `page`; do not rename it in Vietnamese documentation. Keep `name` as `page` and translate `description` to explain what `page` means. Similarly, @Schema.name is the referenced component name in OpenAPI; keep it stable and translate `title`/`description`.

Likewise, operationId is not a display label. Client generators typically derive method names from operationId; varying it by locale can cause Vietnamese and English client SDKs to expose two different API surfaces even though they call the exact same endpoint.

## 14. Common Issues and Fixes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Summary still shows raw ${api.products.get.summary} | Message key does not exist or bundle was not loaded | Check basename, locale filenames, and exact keys |
| Info is translated but schemas are unchanged | resolve-schema-properties is not enabled | Set springdoc.api-docs.resolve-schema-properties=true |
| ExtensionProperty is not replaced | resolve-extensions-properties is not enabled | Enable the property and inspect extension values |
| Accept-Language: vi request still returns English | Locale resolver, allowed-locales, or vi bundle is misconfigured | Check header, whitelist, filenames, and default locale |
| Some fields translate while others do not | Field is not on the supported list | Consult the FAQ; use a customizer for remaining metadata |
| Vietnamese diacritics look garbled | Bundle encoding is not UTF-8 or resource filtering corrupted it | Set spring.messages.encoding=UTF-8 and inspect packaged files |
| Missing key causes document generation failure | MessageSource lacks default or fallback configuration is unsuitable | Add key to default bundle; pass default message in customizer |
| Updated bundle yet API docs show stale text | OpenAPI cache or proxy cache | Restart, configure caching appropriately, and check cache keys |
| English client receives Vietnamese docs | CDN/proxy cache ignores Accept-Language | Add Accept-Language to cache key or bypass cache for multilingual responses |
| Changing schema name breaks client SDK parity | Component identifier was localized | Keep schema names stable; translate only title/description |
| Swagger UI does not switch doc language when UI locale changes | Swagger UI locale and OpenAPI document locale are separate mechanisms | Send Accept-Language when fetching the document or configure UI/requests separately |
| Arbitrary locales bloat cache or yield unreviewed text | Input locales are unrestricted | Configure allowed-locales and enforce default fallback |

## 15. Localization Rollout Workflow

When adding a language to API documentation, follow this sequence:

1. List human-readable fields to translate: Info, operation, parameter descriptions, response descriptions, and schema descriptions.
2. Keep paths, HTTP methods, operationIds, JSON property names, enums, and security identifiers stable.
3. Extract translatable content into clearly namespaced message keys.
4. Place the default bundle and per-locale bundles in src/main/resources.
5. Configure spring.messages.basename, encoding, and fallback.
6. Use ${key} in annotation fields supported by springdoc.
7. Enable resolve-schema-properties if placeholders appear in @Schema.
8. Enable resolve-extensions-properties if placeholders appear in @ExtensionProperty.
9. Configure allowed-locales and pre-loading-locales when needed.
10. Test /v3/api-docs and /v3/api-docs.yaml with each Accept-Language value.
11. Verify springdoc caching and reverse proxy/CDN caching.
12. Add checks for missing keys and unresolved placeholders to CI.

A well-designed setup lets the same API contract be explained in multiple languages. MessageSource manages translations, placeholders let annotations reference content external to code, and OpenAPI keeps technical identifiers stable so clients across all locales share identical endpoints and data structures.

## 16. References

- [Springdoc OpenAPI v2 FAQ – Spring properties in Swagger annotations](https://springdoc.org/v2/faq.html): supported fields on @Info, @Operation, @Parameter, @ApiResponse, @Schema, and @ExtensionProperty.
- [Springdoc OpenAPI v2 – Core properties](https://springdoc.org/v2/core-properties.html): disable-i18n, allowed-locales, pre-loading-enabled, pre-loading-locales, and schema/extension resolvers.
- [Springdoc OpenAPI – Current configuration properties](https://springdoc.org/properties.html): current configuration and version-specific changes.
- [Spring Boot – MessageSource](https://docs.spring.io/spring-boot/reference/features/internationalization.html): resource bundles, basename, and encoding for message sources.
- [Spring Framework – MessageSource](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-messagesource): Locale-based message lookup mechanism.
- [Java ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): bundle naming rules and locale fallback.
- [HTTP Semantics – Accept-Language](https://www.rfc-editor.org/rfc/rfc9110.html#name-accept-language): header clients use to indicate preferred representation languages.

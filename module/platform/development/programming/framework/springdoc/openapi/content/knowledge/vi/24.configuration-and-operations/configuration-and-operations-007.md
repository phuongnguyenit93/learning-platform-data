# Bản địa hóa mô tả và khả năng phân giải placeholder

Một API có thể được sử dụng bởi nhiều nhóm phát triển ở các quốc gia hoặc thị trường khác nhau. Khi đó, tên operation, phần mô tả, thông tin schema và thông báo trong tài liệu OpenAPI cần xuất hiện bằng ngôn ngữ phù hợp. Springdoc-openapi tích hợp với cơ chế cấu hình và MessageSource của Spring để phân giải placeholder trong một số trường của Swagger annotations, đồng thời tạo OpenAPI document theo locale của request.

Có hai nhu cầu gần nhau nhưng cần phân biệt:

- **Phân giải placeholder:** thay giá trị dạng ${api.operation.summary} bằng giá trị cấu hình tương ứng. Cấu hình có thể đến từ application.yml, biến môi trường, command line hoặc property source khác.
- **Bản địa hóa (i18n):** cùng một khóa thông điệp có thể có giá trị khác nhau theo Locale, chẳng hạn tiếng Việt, tiếng Anh hoặc tiếng Pháp. Spring MessageSource chọn bản dịch phù hợp với locale của request.

Springdoc kết hợp hai cơ chế này trong các trường annotation được hỗ trợ. Việc dùng placeholder không tự động dịch mọi chuỗi trong OpenAPI. Cần đặt khóa thông điệp trong resource bundle, bật các property resolver dành cho schema/extension khi cần, và kiểm tra tài liệu được tạo với từng header Accept-Language.

## 1. Khi nào cần bản địa hóa tài liệu OpenAPI?

Hãy xem tài liệu API như một phần giao diện dành cho người tích hợp. Một nhóm developer có thể muốn đọc mô tả bằng tiếng Việt, trong khi đối tác hoặc đội vận hành ở môi trường khác cần tiếng Anh. Nếu cùng một API phục vụ nhiều locale, một bản OpenAPI duy nhất với các mô tả hard-code sẽ không đáp ứng tốt nhu cầu đó.

Các phần thường cần bản địa hóa:

| Thành phần OpenAPI | Ví dụ nội dung |
|---|---|
| Info | Tiêu đề, mô tả, terms of service, thông tin liên hệ |
| Operation | Summary và description của endpoint |
| Parameter | Tên hiển thị và mô tả path/query/header parameter |
| Response | Mô tả ý nghĩa của HTTP response |
| Schema | Tên, title và description của model hoặc field |
| OAuth flow | URL authorization, token, refresh hoặc OpenID Connect khi khác nhau theo môi trường |
| Extension | Giá trị của extension tùy chỉnh nếu cần thay theo locale |

Không phải mọi thuộc tính của mọi Swagger annotation đều được springdoc phân giải placeholder. Chỉ dùng các trường được tài liệu springdoc liệt kê; các chuỗi khác cần được giữ tĩnh hoặc xử lý bằng OpenApiCustomizer phù hợp.

## 2. Phân biệt locale với Spring profile

Spring profile và Locale giải quyết hai vấn đề khác nhau:

| Cơ chế | Quyết định điều gì? | Ví dụ |
|---|---|---|
| Spring profile | Cấu hình nào được nạp cho một lần triển khai | dev, staging, prod |
| Locale | Ngôn ngữ dùng để tạo nội dung cho request hiện tại | vi, en, fr-CA |

Profile phù hợp khi giá trị thay đổi theo môi trường, như server URL, OAuth client ID hoặc phiên bản API. Locale phù hợp khi cùng một ứng dụng cần trả mô tả bằng nhiều ngôn ngữ theo yêu cầu của người đọc.

Nếu dùng application-prod.yml để thay toàn bộ mô tả thành tiếng Anh, mọi request tới instance production đều nhận tiếng Anh. Cách đó không hỗ trợ hai người dùng cùng gọi một instance nhưng nhận hai ngôn ngữ khác nhau. Để hỗ trợ nhiều ngôn ngữ đồng thời, dùng MessageSource và Accept-Language.

## 3. Placeholder trong Swagger annotations

Springdoc hỗ trợ Spring property resolver cho một tập trường cụ thể. Có thể khai báo placeholder theo cú pháp ${key} trong annotation:

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

Với operation:

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

Springdoc lấy giá trị của key từ Spring property resolution và MessageSource theo locale được xử lý. Nếu dùng message bundle theo locale, cùng một key có thể trả về nội dung khác nhau mà không phải sửa annotation hoặc biên dịch lại controller.

### Các trường được springdoc hỗ trợ

Theo FAQ chính thức, các trường có hỗ trợ Spring property resolver gồm:

| Annotation | Trường được hỗ trợ |
|---|---|
| @Info | title, description, version, termsOfService |
| @Info.license | name, url |
| @Info.contact | name, email, url |
| @Operation | summary, description |
| @Parameter | name, description |
| @ApiResponse | description |
| @OAuthFlow | openIdConnectUrl, authorizationUrl, refreshUrl, tokenUrl |
| @Schema | name, title, description; cần bật resolve-schema-properties |
| @ExtensionProperty | value; cần bật resolve-extensions-properties |

Danh sách trên là phạm vi các trường được tài liệu công bố. Không suy luận rằng mọi trường string trong Swagger annotations đều tự động được phân giải. Ví dụ, không nên tự giả định tên tag, operationId, enum value, example hoặc mọi trường tùy chỉnh đều được dịch chỉ vì summary đã được dịch.

## 4. Khai báo message bundle theo locale

Spring Boot dùng MessageSource để đọc message bundle. Với basename mặc định là messages, đặt các file sau trong src/main/resources:

~~~text
src/main/resources/
  messages.properties
  messages_vi.properties
  messages_en.properties
  messages_fr_CA.properties
~~~

messages.properties là bundle mặc định/fallback. Các file có hậu tố locale cung cấp bản dịch tương ứng. Tên locale tuân theo quy tắc ResourceBundle của Java; ví dụ fr_CA biểu diễn tiếng Pháp tại Canada.

Ví dụ messages.properties:

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

Ví dụ messages_vi.properties:

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

Ví dụ messages_en.properties:

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

Với một message key, springdoc dùng locale của request để tra cứu bản dịch. Nếu file locale không có key, MessageSource áp dụng quy tắc fallback của Spring/Java để tìm bundle mặc định. Vì vậy, nên giữ một messages.properties đầy đủ làm ngôn ngữ mặc định và không để các key bị thiếu ngoài ý muốn.

### Cấu hình basename và encoding

Có thể khai báo rõ bundle và encoding:

~~~yaml
spring:
  messages:
    basename: messages
    encoding: UTF-8
    fallback-to-system-locale: false
~~~

Nếu bundle đặt trong thư mục riêng, ví dụ src/main/resources/i18n/api-docs.properties, cấu hình basename tương ứng:

~~~yaml
spring:
  messages:
    basename: i18n/api-docs
    encoding: UTF-8
    fallback-to-system-locale: false
~~~

Khi đó tạo api-docs.properties, api-docs_vi.properties và api-docs_en.properties cùng thư mục. Không thêm đuôi .properties vào basename. Khi khai báo nhiều basename, phân tách theo cú pháp Spring Boot hỗ trợ.

Nếu dự án tự khai báo bean MessageSource, hãy đảm bảo bean đó vẫn đọc đủ các bundle cần thiết. Một MessageSource tùy chỉnh có thể thay thế cấu hình tự động của Spring Boot; nếu quên basename hoặc encoding, các key trong Swagger annotations có thể không được phân giải.

## 5. Áp dụng placeholder cho Info, Operation, Parameter và Response

Khi đã có message bundle, annotation có thể giữ nguyên khóa thay vì chứa câu văn cố định:

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

Trong ví dụ, operationId giữ ổn định vì đây là định danh kỹ thuật của operation. Summary, description, parameter name/description và response description có thể được dịch. Không dịch operationId theo locale vì client generator, link OpenAPI và các hệ thống tích hợp có thể dựa vào định danh này.

Nếu annotation có nhiều response, mỗi @ApiResponse có thể dùng một message key riêng. Nên đặt tên key theo path và response code để tránh một khóa chung bị dùng với ý nghĩa khác nhau.

## 6. Phân giải placeholder trong @Schema

Schema là phần dễ bị bỏ sót khi bản địa hóa. Springdoc có property riêng để bật resolver cho các trường name, title và description của @Schema:

~~~yaml
springdoc:
  api-docs:
    resolve-schema-properties: true
~~~

Ví dụ DTO:

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
        example = "Bút bi"
    )
    String name
) {}
~~~

Khi bật resolve-schema-properties, springdoc phân giải name, title và description trong schema. Ví dụ trên dùng cùng một key để minh họa; trong API thực tế, nên có key riêng cho tên model, mô tả model và mô tả từng field.

Property này mặc định là false theo bảng cấu hình springdoc. Nếu quên bật, placeholder trong @Schema có thể xuất hiện nguyên dạng trong components.schemas. Việc bật resolver không làm thay đổi kiểu dữ liệu, required, enum hoặc validation constraint của schema.

### Tránh dịch tên thuộc tính JSON

Tên property trong JSON là một phần của contract dữ liệu. Thông thường không nên thay đổi tên JSON theo locale:

~~~java
public record ProductResponse(
    @JsonProperty("productId")
    UUID id,

    @JsonProperty("displayName")
    String name
) {}
~~~

Mô tả field có thể thay đổi theo locale, nhưng Product, productId và displayName cần giữ ổn định để client tiếng Việt và tiếng Anh trao đổi cùng một cấu trúc JSON. Không dùng bản dịch cho tên component schema, @JsonProperty, tên path, query key hoặc header kỹ thuật nếu điều đó làm thay đổi wire contract.

## 7. Phân giải ExtensionProperty

OpenAPI extension cho phép bổ sung metadata ngoài các field chuẩn. Nếu giá trị của @ExtensionProperty cần lấy từ Spring property resolver hoặc message bundle, bật:

~~~yaml
springdoc:
  api-docs:
    resolve-extensions-properties: true
~~~

Ví dụ:

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

Property này mặc định là false theo bảng cấu hình. Chỉ bật khi ứng dụng thực sự dùng placeholder trong extension value. Tên extension và tên property nên giữ ổn định; chỉ dịch giá trị hiển thị nếu consumer của extension hiểu được rằng giá trị có thể thay đổi theo locale.

## 8. Locale được chọn từ Accept-Language

Khi client gọi endpoint OpenAPI, có thể gửi header Accept-Language để yêu cầu locale:

~~~http
GET /v3/api-docs HTTP/1.1
Host: api.example.com
Accept: application/json
Accept-Language: vi
~~~

Yêu cầu tiếng Anh:

~~~http
GET /v3/api-docs HTTP/1.1
Host: api.example.com
Accept: application/json
Accept-Language: en
~~~

Spring xử lý locale của request và springdoc dùng locale đó khi phân giải message. Một client có thể tải cùng một endpoint /v3/api-docs nhiều lần với Accept-Language khác nhau để nhận mô tả khác nhau, trong khi path, HTTP method, schema type và operationId vẫn giống nhau.

Ví dụ kiểm tra bằng curl:

~~~bash
curl -H "Accept: application/json" \
     -H "Accept-Language: vi" \
     http://localhost:8080/v3/api-docs

curl -H "Accept: application/json" \
     -H "Accept-Language: en" \
     http://localhost:8080/v3/api-docs
~~~

Nếu không gửi Accept-Language, framework dùng locale mặc định theo cấu hình và locale resolver của ứng dụng. Không nên dựa vào system locale của máy chủ để chọn ngôn ngữ cho API public; hãy cấu hình fallback rõ ràng và cung cấp bundle mặc định.

### Whitelist locale được phép

Springdoc có property allowed-locales để giới hạn các locale được hỗ trợ cho OpenAPI:

~~~yaml
springdoc:
  allowed-locales:
    - vi
    - en
    - fr-CA
~~~

Danh sách này giúp ứng dụng xác định rõ những locale được phép phục vụ. Giá trị cần khớp với định dạng locale mà hệ thống sử dụng; kiểm tra hành vi với version springdoc đang cài, nhất là khi có region như fr-CA. Khi request gửi một locale ngoài danh sách, hãy xác minh fallback thực tế bằng test thay vì giả định mọi server đều xử lý giống nhau.

Không nên tạo hàng trăm locale tùy ý nếu API chỉ cần vài ngôn ngữ được hỗ trợ chính thức. Mỗi locale bổ sung làm tăng số bundle cần duy trì và số biến thể OpenAPI có thể được tạo/cache.

## 9. Cấu hình i18n, preloading và schema resolver

Có thể gom các cấu hình liên quan vào application.yml:

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

Ý nghĩa các property:

| Property | Giá trị mặc định theo tài liệu | Tác dụng |
|---|---|---|
| springdoc.disable-i18n | false | false cho phép tự động dịch qua i18n; true tắt cơ chế dịch tự động |
| springdoc.allowed-locales | Không có danh sách mặc định | Giới hạn locale được phép dùng cho OpenAPI |
| springdoc.pre-loading-enabled | false | Tạo trước OpenAPI khi ứng dụng khởi động |
| springdoc.pre-loading-locales | Không có danh sách mặc định | Các locale cần preload; nếu không chỉ định, preload locale mặc định |
| springdoc.api-docs.resolve-schema-properties | false | Phân giải name, title, description trong @Schema |
| springdoc.api-docs.resolve-extensions-properties | false | Phân giải giá trị @ExtensionProperty |

Preloading hữu ích khi tài liệu lớn hoặc lần gọi đầu tiên cần thời gian dựng schema. Khi bật pre-loading-enabled và chỉ định pre-loading-locales, springdoc có thể chuẩn bị document cho các locale đó ngay lúc khởi động. Preloading không tạo các file JSON/YAML tĩnh riêng và không thay thế việc kiểm tra locale của request.

### Khi nào tắt i18n?

springdoc.disable-i18n=true có thể dùng khi ứng dụng không muốn springdoc tra cứu message theo locale hoặc muốn giữ nội dung tài liệu cố định. Không bật property này trong khi vẫn kỳ vọng Accept-Language đổi nội dung mô tả. Nếu ứng dụng cần property placeholder cho cấu hình môi trường, hãy kiểm tra riêng hành vi placeholder sau khi bật/tắt i18n trên đúng version springdoc; đừng giả định hai loại resolution luôn bật/tắt cùng nhau.

## 10. Cache OpenAPI theo locale

Việc tạo OpenAPI document có thể tốn chi phí vì springdoc quét controller, xử lý annotation và tạo schema. Theo FAQ hiện hành, springdoc cache một bản mô tả cho mỗi locale được request qua Accept-Language. Vì vậy:

- Request tiếng Việt có thể dùng document cache của locale tiếng Việt.
- Request tiếng Anh có thể dùng document cache của locale tiếng Anh.
- Cùng một locale không cần dựng lại document ở mỗi request khi cache đang bật.
- Số locale được dùng cần được kiểm soát để tránh tạo quá nhiều biến thể.

Mặc định springdoc cache OpenAPI description. Nếu nội dung message được thay đổi động trong runtime và cần phản ánh ngay ở mọi request, có thể cân nhắc:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Tắt cache có thể khiến document phải được tính lại trên mỗi request, làm tăng CPU và độ trễ. Với bundle nằm trong classpath và chỉ thay đổi khi deploy, thường nên giữ cache và khởi động lại ứng dụng khi phát hành bản dịch mới.

Không nhầm cache của springdoc với cache HTTP/CDN/reverse proxy. Nếu proxy cache /v3/api-docs nhưng không đưa Accept-Language vào cache key, proxy có thể trả bản tiếng Việt cho client tiếng Anh hoặc ngược lại. Khi publish tài liệu đa ngôn ngữ qua proxy, cần bảo đảm cache key tôn trọng Accept-Language; nếu proxy dùng HTTP Vary, kiểm tra response có Vary: Accept-Language hoặc cấu hình cache key tương đương.

## 11. Kiểm thử OpenAPI với từng locale

Kiểm thử phải xác nhận nội dung đã được dịch và placeholder không còn xuất hiện nguyên dạng. Có thể dùng MockMvc để gửi Accept-Language:

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

Ví dụ giả định controller và bundle đã dùng đúng các key ở phần trước. Nếu operation có nhiều parameter, không nên phụ thuộc index [0]; có thể đọc JSON document rồi tìm parameter theo in/path/name ổn định.

Với WebFlux, có thể dùng WebTestClient và gửi header tương tự:

~~~java
webTestClient.get()
    .uri("/v3/api-docs")
    .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.info.title").isEqualTo("API Cửa hàng");
~~~

Ngoài nội dung đã dịch, nên kiểm tra các điều kiện:

1. Request không gửi Accept-Language nhận đúng ngôn ngữ mặc định.
2. Locale được whitelist trả đúng bản dịch.
3. Locale ngoài whitelist được xử lý theo fallback mong muốn.
4. Key bị thiếu không làm OpenAPI trả chuỗi placeholder hoặc nội dung không mong muốn.
5. @Schema description được phân giải khi resolve-schema-properties bật.
6. Extension value được phân giải khi resolve-extensions-properties bật.
7. JSON và YAML trả cùng nội dung cho cùng locale.
8. Hai request locale khác nhau không nhận nhầm document do cache hoặc reverse proxy.

## 12. Khi annotation không đủ: dùng MessageSource trong customizer

Springdoc hỗ trợ placeholder trực tiếp cho nhiều trường annotation. Với metadata không nằm trong danh sách hỗ trợ hoặc cần quy tắc dịch đặc biệt, có thể dùng MessageSource trong OperationCustomizer hoặc OpenApiCustomizer.

Ví dụ dùng OperationCustomizer để thay description theo locale:

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

MessageSource#getMessage nhận key, arguments, nội dung mặc định và Locale. Truyền default message giúp ứng dụng vẫn tạo document khi một bundle thiếu key. LocaleContextHolder cung cấp locale gắn với request hiện tại trong quá trình xử lý đồng bộ của Spring.

Chỉ dùng customizer khi cần thiết. Nếu một field đã được springdoc phân giải trực tiếp từ annotation, đừng thay cùng field lần nữa trong customizer vì có thể tạo hai nguồn dữ liệu khó bảo trì. Với GroupedOpenApi, hãy kiểm tra customizer được áp dụng cho đúng group; khi cần áp dụng cho cả document mặc định và các group, dùng loại global customizer phù hợp với phiên bản springdoc.

## 13. Những giá trị nên giữ ổn định giữa các ngôn ngữ

Không phải mọi nội dung đều nên dịch. Một OpenAPI document đa ngôn ngữ vẫn phải mô tả cùng một HTTP contract:

| Nên bản địa hóa | Nên giữ ổn định |
|---|---|
| Info title và description | Path như /api/products/{id} |
| Operation summary và description | HTTP method như GET, POST |
| Parameter description | Tên parameter thực tế như id, page, sort |
| ApiResponse description | operationId |
| Schema title và description | JSON property name và enum value |
| Mô tả extension dành cho con người | Security scheme key và OAuth scope |
| Mô tả nghiệp vụ, hướng dẫn nhập liệu | Media type và header kỹ thuật |

Đặc biệt, dù @Parameter.name có hỗ trợ property resolver, không nên dịch tên path/query/header parameter nếu tên đó là một phần của request contract. Ví dụ, client luôn gửi query parameter page; không đổi tên thành trang trong tài liệu tiếng Việt. Hãy giữ name là page và dịch description để giải thích page có ý nghĩa gì. Tương tự, @Schema.name là tên component được tham chiếu trong OpenAPI; giữ tên này ổn định và dịch title/description.

Tương tự, operationId không phải nhãn hiển thị. Client generator thường dùng operationId để tạo tên method; thay đổi theo locale có thể làm client SDK tiếng Việt và tiếng Anh sinh ra hai API surface khác nhau dù cùng gọi một endpoint.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Summary vẫn hiện nguyên ${api.products.get.summary} | Message key không tồn tại hoặc bundle không được nạp | Kiểm tra basename, tên file locale và key chính xác |
| Info được dịch nhưng schema không đổi | Chưa bật resolve-schema-properties | Đặt springdoc.api-docs.resolve-schema-properties=true |
| ExtensionProperty không được thay | Chưa bật resolve-extensions-properties | Bật property và kiểm tra value của extension |
| Request Accept-Language: vi vẫn trả tiếng Anh | Locale resolver, allowed-locales hoặc bundle vi chưa đúng | Kiểm tra header, whitelist, tên file và default locale |
| Một số field dịch, một số field không dịch | Field không nằm trong danh sách hỗ trợ | Kiểm tra FAQ; dùng customizer cho metadata còn thiếu |
| Tiếng Việt bị lỗi dấu | Encoding bundle không phải UTF-8 hoặc build resource sai | Đặt spring.messages.encoding=UTF-8 và kiểm tra file được đóng gói |
| Thiếu key làm lỗi tạo document | MessageSource không có default hoặc cấu hình fallback không phù hợp | Bổ sung key vào bundle mặc định; dùng default message trong customizer |
| Đổi bundle nhưng API docs vẫn dùng nội dung cũ | OpenAPI cache hoặc cache proxy | Khởi động lại, cấu hình cache phù hợp và kiểm tra cache key |
| Client tiếng Anh nhận tài liệu tiếng Việt | CDN/proxy cache không phân biệt Accept-Language | Thêm Accept-Language vào cache key hoặc không cache response đa ngôn ngữ |
| Schema name thay đổi làm client SDK khác nhau | Đã bản địa hóa định danh component | Giữ schema name ổn định; chỉ dịch title/description |
| Swagger UI không tự đổi ngôn ngữ khi đổi giao diện | Locale của Swagger UI và locale của OpenAPI document là hai cơ chế | Gửi Accept-Language khi tải document hoặc cấu hình UI/request riêng |
| Locale lạ làm tăng cache hoặc tạo bản dịch không kiểm soát | Không giới hạn locale đầu vào | Cấu hình allowed-locales và dùng fallback mặc định |

## 15. Quy trình triển khai bản địa hóa

Khi thêm một ngôn ngữ cho tài liệu API, thực hiện theo trình tự:

1. Liệt kê các trường con người đọc cần dịch: Info, operation, parameter description, response description và schema description.
2. Giữ ổn định path, HTTP method, operationId, tên JSON property, enum và security identifiers.
3. Chuyển nội dung cần dịch thành message key có namespace rõ ràng.
4. Đặt bundle mặc định và các bundle locale trong src/main/resources.
5. Cấu hình spring.messages.basename, encoding và fallback.
6. Dùng ${key} trong những annotation fields springdoc hỗ trợ.
7. Bật resolve-schema-properties nếu placeholder nằm trong @Schema.
8. Bật resolve-extensions-properties nếu placeholder nằm trong @ExtensionProperty.
9. Cấu hình allowed-locales và pre-loading-locales khi cần.
10. Kiểm thử /v3/api-docs và /v3/api-docs.yaml với từng Accept-Language.
11. Kiểm tra cache của springdoc và cache ở reverse proxy/CDN.
12. Đưa việc kiểm tra key thiếu và placeholder chưa phân giải vào CI.

Một cấu hình tốt giúp cùng một API contract được giải thích bằng nhiều ngôn ngữ. MessageSource quản lý bản dịch, placeholder giúp annotation tham chiếu nội dung bên ngoài mã nguồn, còn OpenAPI vẫn giữ định danh kỹ thuật ổn định để client ở mọi locale dùng chung endpoint và cấu trúc dữ liệu.

## 16. Tài liệu tham khảo

- [Springdoc OpenAPI v2 FAQ – Spring properties in Swagger annotations](https://springdoc.org/v2/faq.html): các trường @Info, @Operation, @Parameter, @ApiResponse, @Schema và @ExtensionProperty được hỗ trợ.
- [Springdoc OpenAPI v2 – Core properties](https://springdoc.org/v2/core-properties.html): disable-i18n, allowed-locales, pre-loading-enabled, pre-loading-locales và schema/extension resolver.
- [Springdoc OpenAPI – Current configuration properties](https://springdoc.org/properties.html): cấu hình hiện hành và các thay đổi theo version.
- [Spring Boot – MessageSource](https://docs.spring.io/spring-boot/reference/features/internationalization.html): resource bundle, basename và encoding cho message source.
- [Spring Framework – MessageSource](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-messagesource): cơ chế tra cứu thông điệp theo Locale.
- [Java ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): quy tắc đặt tên bundle và fallback theo locale.
- [HTTP Semantics – Accept-Language](https://www.rfc-editor.org/rfc/rfc9110.html#name-accept-language): header client dùng để chỉ định ngôn ngữ ưu tiên cho representation.

# OpenAPI bean và mô hình đối tượng của Swagger Core

## 1. Khi nào cần tùy biến OpenAPI bằng Java?

Springdoc OpenAPI có thể đọc controller Spring Boot, kiểu dữ liệu và annotation để tạo tài liệu OpenAPI. Với ứng dụng đơn giản, nhóm phát triển thường chỉ cần khai báo metadata cơ bản rồi để thư viện suy luận path, operation, parameter, request body, response và schema.

Một số tình huống cần can thiệp bằng code:

- Khai báo thông tin API, server, tag hoặc security scheme tập trung.
- Bổ sung metadata lấy từ cấu hình ứng dụng.
- Thêm vendor extension như x-api-owner hoặc x-internal.
- Điều chỉnh mô tả từng operation dựa trên annotation nghiệp vụ.
- Tùy biến tài liệu riêng cho một document group.
- Thêm schema hoặc response dùng chung mà annotation trên controller không diễn đạt thuận tiện.
- Chuẩn hóa document trước khi xuất JSON/YAML hoặc phân phối qua developer portal.

Springdoc tích hợp với **Swagger Core** thông qua mô hình đối tượng OpenAPI. Ứng dụng có thể tạo bean OpenAPI, sau đó Springdoc bổ sung operation được suy luận từ controller. Các customizer cho phép chỉnh mô hình trước khi tài liệu được trả về.

Cần phân biệt ba thành phần:

1. **OpenAPI model** là các lớp Java biểu diễn cấu trúc tài liệu.
2. **Springdoc customizer** là điểm mở rộng để thay đổi document hoặc operation.
3. **OpenAPI annotations** là metadata đặt trên controller, method và DTO để Springdoc đọc.

## 2. Swagger Core Object Model là gì?

Swagger Core cung cấp các lớp Java tương ứng với object trong OpenAPI Specification. Các lớp này nằm chủ yếu trong package io.swagger.v3.oas.models.

| Lớp Java | Object OpenAPI tương ứng | Mục đích |
|---|---|---|
| OpenAPI | OpenAPI Object | Tài liệu gốc |
| Info | Info Object | Title, description, version, contact, license |
| Server | Server Object | Địa chỉ server và biến server |
| Paths | Paths Object | Tập hợp đường dẫn |
| PathItem | Path Item Object | Các method tại một path |
| Operation | Operation Object | Mô tả một thao tác HTTP |
| Parameter | Parameter Object | Path, query, header hoặc cookie parameter |
| RequestBody | Request Body Object | Body mà client gửi |
| ApiResponses | Responses Object | Các response theo status code |
| ApiResponse | Response Object | Mô tả một kết quả HTTP |
| Content | Content Object | Media type và schema |
| Schema | Schema Object | Kiểu dữ liệu và ràng buộc |
| Components | Components Object | Các định nghĩa có thể tái sử dụng |
| SecurityScheme | Security Scheme Object | Cơ chế xác thực |
| Tag | Tag Object | Nhóm operation |

Các model này là đối tượng Java có thể được tạo bằng constructor và thay đổi qua setter hoặc fluent method. Springdoc sử dụng chúng để tạo tài liệu JSON/YAML.

Ví dụ:

~~~java
OpenAPI openAPI = new OpenAPI()
    .info(new Info()
        .title("Shop API")
        .description("API quản lý sản phẩm và đơn hàng")
        .version("1.0.0"));
~~~

Model trên biểu diễn phần metadata tương ứng:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  description: API quản lý sản phẩm và đơn hàng
  version: "1.0.0"
~~~

Giá trị openapi ở cấp tài liệu cho biết phiên bản đặc tả. Info.version mô tả phiên bản API được công bố; hai giá trị này có mục đích khác nhau.

## 3. Phân biệt model classes với annotation classes

Swagger Core có hai nhóm package dễ nhầm:

| Nhóm | Package tiêu biểu | Cách sử dụng |
|---|---|---|
| Annotation | io.swagger.v3.oas.annotations | Đặt metadata lên class, method, field hoặc parameter |
| Model | io.swagger.v3.oas.models | Tạo và thay đổi object OpenAPI bằng Java |

Ví dụ annotation:

~~~java
@Operation(
    summary = "Lấy thông tin sản phẩm",
    description = "Tra cứu sản phẩm theo mã định danh"
)
@GetMapping("/api/products/{id}")
public ProductResponse findById(@PathVariable Long id) {
    return productService.findById(id);
}
~~~

Annotation được đặt trên method để Springdoc đọc khi quét controller.

Ví dụ model:

~~~java
Operation operation = new Operation()
    .summary("Lấy thông tin sản phẩm")
    .description("Tra cứu sản phẩm theo mã định danh");
~~~

Model được tạo và chỉnh bằng code. Nó không tự gắn vào controller; cần đưa vào OpenAPI document thông qua customizer hoặc cấu hình phù hợp.

Không nhầm io.swagger.v3.oas.annotations.Operation với io.swagger.v3.oas.models.Operation. Tên lớp giống nhau nhưng một lớp là annotation, lớp kia là model.

## 4. Khai báo OpenAPI bean trong Spring Boot

Một cách phổ biến để cung cấp metadata toàn cục là khai báo bean OpenAPI:

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI shopOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .description("API quản lý sản phẩm, danh mục và đơn hàng.")
                .version("1.0.0"))
            .servers(List.of(
                new Server()
                    .url("https://api.example.com")
                    .description("Production server")
            ));
    }
}
~~~

Các import model trong ví dụ thuộc package io.swagger.v3.oas.models; @Configuration và @Bean thuộc Spring Framework.

Springdoc sử dụng bean này làm nền tảng cho OpenAPI document và tiếp tục phát hiện operation từ controller. Không cần tự tạo toàn bộ Paths nếu ứng dụng đã có controller được Springdoc quét.

Nên giữ bean tập trung vào metadata hoặc cấu phần chung như server, components và security. Những nội dung gắn với từng method thường phù hợp hơn với annotation hoặc OperationCustomizer.

Nếu ứng dụng đã khai báo metadata bằng @OpenAPIDefinition, tránh khai báo một nguồn khác có giá trị mâu thuẫn. Có thể dùng annotation cho metadata tĩnh hoặc bean OpenAPI cho cấu hình cần xây dựng bằng code; chọn một nguồn chính và kiểm tra kết quả cuối cùng.

## 5. Khai báo Info, Server và Tag bằng model

OpenAPI bean có thể chứa nhiều metadata:

~~~java
@Bean
public OpenAPI shopOpenAPI() {
    return new OpenAPI()
        .info(new Info()
            .title("Shop API")
            .description("API dành cho ứng dụng bán hàng và hệ thống tích hợp.")
            .version("1.4.0")
            .contact(new Contact()
                .name("API Support")
                .email("api-support@example.com")
                .url("https://example.com/support"))
            .license(new License()
                .name("Apache 2.0")
                .url("https://www.apache.org/licenses/LICENSE-2.0.html")))
        .servers(List.of(
            new Server()
                .url("https://api.example.com")
                .description("Production"),
            new Server()
                .url("https://staging-api.example.com")
                .description("Staging")
        ))
        .tags(List.of(
            new Tag()
                .name("Products")
                .description("Quản lý sản phẩm"),
            new Tag()
                .name("Orders")
                .description("Quản lý đơn hàng")
        ));
}
~~~

Server Object mô tả URL mà client có thể gọi. Không nên đặt một URL production cố định nếu tài liệu cần thay đổi theo môi trường. Có thể lấy giá trị từ application properties hoặc profile, nhưng cần bảo đảm document không vô tình công bố hostname nội bộ.

Tag ở cấp tài liệu giúp định nghĩa tên và mô tả nhóm. Operation vẫn cần tham chiếu tag bằng tên tương ứng để Swagger UI nhóm đúng endpoint. Chỉ tạo Tag Object mà không gắn tag vào operation có thể khiến tag không có operation hiển thị.

Info.summary chỉ dùng khi phiên bản OpenAPI model và tài liệu được xuất hỗ trợ trường này, tức OpenAPI 3.1.0 trở lên. Nếu dự án xuất OpenAPI 3.0 hoặc swagger-models chưa có thuộc tính tương ứng, hãy đưa phần giới thiệu ngắn vào description.

## 6. Tái sử dụng schema thông qua Components

Components là nơi lưu các định nghĩa dùng lại, chẳng hạn schema, response, parameter, request body và security scheme.

Ví dụ thêm schema bằng model:

~~~java
@Bean
public OpenAPI shopOpenAPI() {
    Schema<?> productSchema = new Schema<>()
        .type("object")
        .addProperty("id", new Schema<>().type("integer").format("int64"))
        .addProperty("name", new Schema<>().type("string"))
        .addProperty("price", new Schema<>().type("number"));

    Components components = new Components()
        .addSchemas("ProductSummary", productSchema);

    return new OpenAPI()
        .info(new Info()
            .title("Shop API")
            .version("1.0.0"))
        .components(components);
}
~~~

Schema ProductSummary có thể được tham chiếu từ response:

~~~java
Schema<?> productReference = new Schema<>()
    .$ref("#/components/schemas/ProductSummary");
~~~

Trong nhiều trường hợp, Springdoc tự tạo component schema từ DTO được dùng trong controller. Chỉ thêm schema bằng model khi cần một định nghĩa dùng chung đặc biệt hoặc cần bổ sung cấu trúc mà quá trình suy luận tự động chưa thể hiện đúng.

Không nên tạo component trùng tên với schema do Springdoc đã sinh. Tên component phải duy nhất trong document và các tham chiếu $ref phải trỏ đúng vị trí.

## 7. Khai báo Security Scheme bằng OpenAPI model

Có thể mô tả cơ chế Bearer JWT trong Components:

~~~java
@Bean
public OpenAPI shopOpenAPI() {
    SecurityScheme bearerScheme = new SecurityScheme()
        .type(SecurityScheme.Type.HTTP)
        .scheme("bearer")
        .bearerFormat("JWT")
        .description("Nhập access token JWT");

    Components components = new Components()
        .addSecuritySchemes("bearerAuth", bearerScheme);

    return new OpenAPI()
        .info(new Info()
            .title("Shop API")
            .version("1.0.0"))
        .components(components)
        .addSecurityItem(new SecurityRequirement()
            .addList("bearerAuth"));
}
~~~

Security Scheme định nghĩa cơ chế xác thực có tên bearerAuth. Security Requirement ở cấp document áp dụng yêu cầu đó cho các operation theo quy tắc OpenAPI. Nếu một số endpoint public, có thể override security ở operation tương ứng bằng security requirement rỗng hoặc cấu hình thích hợp.

Khai báo scheme chỉ mô tả hợp đồng cho công cụ OpenAPI. Nó không bật Spring Security, không xác thực JWT và không cấp token. Ứng dụng vẫn phải cấu hình filter chain, token decoder và authorization rule ở runtime.

Không đưa token thật hoặc secret vào OpenAPI model. Tài liệu chỉ mô tả cách client gửi thông tin xác thực.

## 8. OpenApiCustomizer thay đổi toàn bộ document

OpenApiCustomizer là điểm mở rộng của Springdoc cho phép chỉnh OpenAPI model sau khi document được tạo. Nó phù hợp với thay đổi ở cấp tài liệu, chẳng hạn thêm extension, tag, server hoặc metadata chung.

Ví dụ thêm extension và tag:

~~~java
@Configuration
public class OpenApiCustomizationConfiguration {

    @Bean
    public OpenApiCustomizer documentMetadataCustomizer() {
        return openApi -> {
            openApi.addExtension("x-api-owner", "platform-team");

            openApi.addTagsItem(new Tag()
                .name("Internal")
                .description("Các operation phục vụ tích hợp nội bộ"));
        };
    }
}
~~~

Trong Springdoc 2.x, OpenApiCustomizer thường nằm trong package org.springdoc.core.customizers. Hãy dùng package và API phù hợp với dòng Springdoc của dự án; package có thể khác ở major version cũ.

Customizer nhận OpenAPI model đã được xây dựng và có thể sửa các thuộc tính hiện có. Nếu cần giữ metadata từ bean hoặc annotation, hãy bổ sung có điều kiện thay vì thay toàn bộ object:

~~~java
if (openApi.getInfo() != null) {
    openApi.getInfo().setDescription(
        "Tài liệu API được tạo từ các controller Spring Boot."
    );
}
~~~

Nếu gọi openApi.info(new Info()) trong customizer, toàn bộ Info trước đó có thể bị thay thế. Chỉ làm vậy khi chủ đích là thay thế và đã giữ lại những trường cần thiết.

## 9. OperationCustomizer thay đổi từng operation

OperationCustomizer làm việc ở cấp một operation và nhận thêm thông tin HandlerMethod tương ứng. Nó phù hợp khi cần dựa vào method hoặc controller để bổ sung metadata.

Ví dụ thêm extension chứa tên method:

~~~java
@Configuration
public class OperationCustomizationConfiguration {

    @Bean
    public OperationCustomizer operationMetadataCustomizer() {
        return (operation, handlerMethod) -> {
            operation.addExtension(
                "x-handler-method",
                handlerMethod.getMethod().getName()
            );

            return operation;
        };
    }
}
~~~

Customizer này được gọi cho operation được Springdoc tạo từ handler method. Có thể dùng HandlerMethod để đọc annotation tùy chỉnh của ứng dụng, package controller hoặc thông tin method.

Ví dụ, nếu dự án có annotation @ApiOwner("catalog-team"), OperationCustomizer có thể đọc annotation trên method và thêm extension x-api-owner tương ứng. Cách này tránh lặp metadata ở nhiều annotation OpenAPI.

OperationCustomizer không thay thế Spring MVC mapping và không thay đổi cách request được xử lý. Nó chỉ chỉnh mô hình tài liệu. Nếu thêm extension hoặc thay summary, hãy bảo đảm giá trị đó phản ánh đúng hành vi thực tế.

## 10. So sánh OpenApiCustomizer và OperationCustomizer

Hai customizer có phạm vi khác nhau:

| Tiêu chí | OpenApiCustomizer | OperationCustomizer |
|---|---|---|
| Đối tượng nhận | OpenAPI document | Operation và HandlerMethod |
| Phạm vi | Toàn bộ document | Từng endpoint operation |
| Có biết controller method cụ thể? | Không trực tiếp qua callback cơ bản | Có |
| Ví dụ | Thêm server, tag, extension toàn tài liệu | Gắn owner, mã nghiệp vụ hoặc mô tả theo method |
| Khi nào dùng | Metadata chung hoặc cấu trúc cấp document | Metadata phụ thuộc controller/method |

Không nên dùng OperationCustomizer để thêm metadata toàn tài liệu nếu có thể dùng OpenApiCustomizer. Ngược lại, không nên duyệt thủ công toàn bộ Paths chỉ để tìm HandlerMethod nếu OperationCustomizer đã cung cấp ngữ cảnh method.

Nếu cần customizer áp dụng cho tất cả document groups, Springdoc có cơ chế global customizer ở các phiên bản hỗ trợ. Nếu chỉ muốn thay đổi một group, có thể gắn customizer vào cấu hình GroupedOpenApi tương ứng. Hãy xác minh đúng loại customizer và phạm vi áp dụng trong phiên bản dependency của dự án.

## 11. Gắn customizer vào một document group

Một ứng dụng có thể có nhiều document group. Mỗi group có thể cần metadata hoặc extension riêng.

Ví dụ:

~~~java
@Bean
public GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(openApi -> {
            openApi.info(new Info()
                .title("Partner API")
                .description("API dành cho đối tác")
                .version("1.0.0"));

            openApi.addExtension("x-audience", "partners");
        })
        .build();
}
~~~

Customizer được gắn trên builder của group để điều chỉnh document nhóm đó. Cách này hữu ích khi public, admin và partner có title, server hoặc metadata khác nhau.

Cần kiểm tra liệu metadata đã được cấu hình trong OpenAPI bean toàn cục có bị customizer nhóm ghi đè hay không. Nếu chỉ muốn thay đổi một trường, hãy cập nhật trường đó và giữ các giá trị khác.

Với các phiên bản cung cấp GlobalOpenApiCustomizer, có thể dùng khi thay đổi phải xuất hiện trong cả tài liệu mặc định và các group. Đừng dùng customizer group-specific cho một quy tắc cần áp dụng toàn hệ thống mà không kiểm tra tài liệu mặc định.

## 12. Thêm Operation và PathItem bằng Swagger Core model

Springdoc thường tự tạo PathItem và Operation từ controller. Tuy nhiên, Swagger Core model cũng cho phép tạo operation bằng code khi cần mô tả endpoint không được sinh trực tiếp từ controller, hoặc bổ sung một path đặc biệt.

Ví dụ tạo operation health:

~~~java
@Bean
public OpenApiCustomizer healthOperationCustomizer() {
    return openApi -> {
        Operation healthOperation = new Operation()
            .operationId("healthCheck")
            .summary("Kiểm tra trạng thái dịch vụ")
            .description("Trả về trạng thái hoạt động của API")
            .responses(new ApiResponses()
                .addApiResponse("200", new ApiResponse()
                    .description("Dịch vụ đang hoạt động")));

        openApi.path(
            "/internal/health-doc",
            new PathItem().get(healthOperation)
        );
    };
}
~~~

Đây là ví dụ tạo PathItem và Operation trực tiếp trong model. Nó chỉ bổ sung tài liệu OpenAPI; endpoint HTTP tương ứng phải thực sự tồn tại ở runtime nếu client được kỳ vọng gọi nó.

Không nên tạo operation trùng với path/method đã được Springdoc sinh từ controller. Nếu cùng một path và HTTP method được thêm hai lần, một cấu hình có thể ghi đè hoặc làm tài liệu trở nên khó đoán.

Đối với endpoint thực sự được triển khai bằng controller, ưu tiên khai báo controller và annotation để tài liệu được liên kết với code runtime. Dùng model thủ công cho những trường hợp có lý do rõ ràng.

## 13. Thêm response và schema bằng model

Swagger Core model có thể mô tả response với status, description, media type và schema:

~~~java
ApiResponse successResponse = new ApiResponse()
    .description("Trả về sản phẩm")
    .content(new Content()
        .addMediaType(
            "application/json",
            new MediaType().schema(
                new Schema<>().$ref("#/components/schemas/ProductSummary")
            )
        ));

Operation operation = new Operation()
    .responses(new ApiResponses()
        .addApiResponse("200", successResponse));
~~~

Có thể thêm schema component dùng chung:

~~~java
Schema<?> productSchema = new Schema<>()
    .type("object")
    .addProperty("id", new Schema<>().type("integer").format("int64"))
    .addProperty("name", new Schema<>().type("string"));

openApi.getComponents()
    .addSchemas("ProductSummary", productSchema);
~~~

Khi tham chiếu schema, tên component phải khớp chính xác với key trong components.schemas. Nếu component được thêm sau khi response đã tham chiếu, kết quả cuối cùng vẫn cần có cả định nghĩa và reference.

Trong ứng dụng Springdoc, controller và DTO thường là nguồn chính để tạo response/schema. Chỉ can thiệp bằng model khi cần điều chỉnh cấu trúc hoặc bổ sung một định nghĩa dùng chung mà quá trình suy luận tự động chưa đáp ứng.

## 14. Thứ tự và phạm vi tùy biến

Một OpenAPI document có thể được tạo từ nhiều nguồn:

- Metadata trong @OpenAPIDefinition.
- OpenAPI bean.
- Annotation trên controller và DTO.
- Model được Springdoc suy luận từ kiểu Java.
- OpenApiCustomizer.
- OperationCustomizer.
- Customizer riêng của document group.

Khi nhiều nguồn cùng chỉnh một trường, kết quả phụ thuộc quá trình tạo document và cách customizer được áp dụng trong phiên bản Springdoc. Không nên dựa vào thứ tự ngầm định nếu ứng dụng có nhiều customizer cùng ghi đè một thuộc tính.

Để cấu hình dễ hiểu:

1. Chọn một nguồn chính cho metadata toàn cục.
2. Dùng annotation cho thông tin gắn trực tiếp với controller hoặc DTO.
3. Dùng OperationCustomizer cho metadata phụ thuộc HandlerMethod.
4. Dùng OpenApiCustomizer cho thay đổi cấp document.
5. Dùng customizer theo group cho metadata riêng của group.
6. Tránh nhiều customizer cùng thay thế toàn bộ Info, Paths hoặc Components.
7. Kiểm tra tài liệu cuối cùng sau khi tất cả customizer đã chạy.

Không nên thay toàn bộ Paths bằng một object mới trong customizer nếu muốn giữ các operation do Springdoc phát hiện. Nếu cần thêm một path, hãy bổ sung path cụ thể thay vì thay thế collection hiện có.

## 15. Lấy giá trị cấu hình từ application properties

Một số metadata thay đổi theo môi trường, chẳng hạn server URL hoặc contact. Có thể inject cấu hình Spring vào bean:

~~~yaml
app:
  api:
    title: Shop API
    version: 1.4.0
    server-url: https://api.example.com
~~~

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI shopOpenAPI(
        @Value("${app.api.title}") String title,
        @Value("${app.api.version}") String version,
        @Value("${app.api.server-url}") String serverUrl
    ) {
        return new OpenAPI()
            .info(new Info()
                .title(title)
                .version(version))
            .servers(List.of(
                new Server().url(serverUrl)
            ));
    }
}
~~~

Cách này giúp metadata theo môi trường được quản lý bằng cấu hình Spring Boot. Với nhiều giá trị liên quan, có thể dùng một class @ConfigurationProperties thay vì nhiều tham số @Value.

Cần phân biệt server URL dùng trong OpenAPI với địa chỉ thực tế mà gateway hoặc reverse proxy expose. Nếu ứng dụng chạy sau proxy, cấu hình forwarded headers và server URL cần nhất quán để Swagger UI gửi request đến đúng host và path.

Không đưa secret, mật khẩu, access token hoặc thông tin kết nối nội bộ vào OpenAPI bean.

## 16. Kiểm tra model sau khi tùy biến

Sau khi ứng dụng khởi động, tải OpenAPI document:

~~~http
GET /v3/api-docs
~~~

Nếu dùng group, kiểm tra thêm endpoint tài liệu của từng group, ví dụ:

~~~http
GET /v3/api-docs/partner
~~~

Cần xác minh:

- Info có đúng title, description và version.
- Server URL có đúng môi trường và base path.
- Tag có tên và mô tả nhất quán.
- Components chứa schema, response và security scheme được tham chiếu.
- Security requirement áp dụng đúng operation.
- OperationCustomizer chỉ tác động operation dự kiến.
- OpenApiCustomizer không làm mất Paths hoặc Components đã được Springdoc tạo.
- Extension có tên bắt đầu bằng x- và giá trị đúng kiểu.
- Document group có metadata riêng đúng phạm vi.
- JSON/YAML vẫn hợp lệ sau khi chỉnh model.

Có thể dùng validator OpenAPI trong CI để kiểm tra cấu trúc. Validator không xác minh rằng endpoint runtime thực sự tồn tại hoặc security rule đã được bật; cần integration test riêng cho các điều đó.

## 17. Các lỗi thường gặp khi tùy biến bằng model

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Import nhầm Operation | Dùng annotation class thay cho model class hoặc ngược lại |
| Metadata bean không xuất hiện | Bean chưa được Spring scan, cấu hình bị nguồn khác ghi đè hoặc sai document group |
| Controller paths biến mất | Customizer thay toàn bộ Paths thay vì bổ sung path cần thiết |
| Schema reference không resolve | Component chưa được khai báo hoặc tên $ref sai |
| Security scheme có nhưng UI không yêu cầu token | Thiếu Security Requirement hoặc requirement không áp dụng cho operation |
| Mọi operation bị thêm cùng một extension | Logic OperationCustomizer chưa lọc theo controller/method |
| Group thiếu metadata tùy biến | Dùng sai phạm vi customizer hoặc customizer chỉ áp dụng document mặc định |
| Summary không xuất hiện | Đặc tả đang dùng OpenAPI 3.0 hoặc model version chưa hỗ trợ Info.summary |
| Swagger UI gọi sai server | Server URL, context path hoặc reverse proxy chưa khớp |
| Operation bị lặp hoặc ghi đè | Tạo thủ công path/method trùng với operation được quét từ controller |

Khi điều tra, hãy xem OpenAPI JSON trước để biết model cuối cùng đang chứa gì. Sau đó kiểm tra bean, annotation và customizer nào đã tạo hoặc thay đổi trường đó.

## 18. Nguyên tắc thiết kế OpenAPI customization

Khi dùng OpenAPI bean và Swagger Core model trong Springdoc, nên áp dụng các nguyên tắc:

1. Dùng OpenAPI bean cho metadata và cấu phần dùng chung.
2. Dùng Swagger Core model classes khi cần tạo hoặc thay đổi document bằng Java.
3. Phân biệt model package với annotation package.
4. Dùng OpenApiCustomizer cho thay đổi cấp document.
5. Dùng OperationCustomizer cho thay đổi phụ thuộc HandlerMethod.
6. Dùng customizer riêng của group khi metadata chỉ thuộc một tài liệu nhóm.
7. Không thay toàn bộ Paths hoặc Components nếu chỉ cần thêm một phần tử.
8. Không khai báo operation thủ công trùng với controller đã được Springdoc quét.
9. Giữ server, schema, security và extension nhất quán với runtime.
10. Kiểm tra OpenAPI JSON/YAML và chạy contract/integration test sau thay đổi.

OpenAPI bean cung cấp điểm bắt đầu có kiểm soát cho tài liệu; Swagger Core model biểu diễn cấu trúc OpenAPI bằng Java; customizer cho phép thay đổi document hoặc operation ở đúng phạm vi. Khi mỗi nguồn được dùng đúng vai trò và kết quả cuối cùng được kiểm tra, ứng dụng có thể mở rộng tài liệu mà vẫn giữ hợp đồng nhất quán với controller Spring Boot.


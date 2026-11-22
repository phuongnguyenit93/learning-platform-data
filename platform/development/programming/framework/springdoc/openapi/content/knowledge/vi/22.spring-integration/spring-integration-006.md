# Spring Cloud Function Web và siêu dữ liệu cho hàm

Spring Cloud Function cho phép viết nghiệp vụ dưới dạng các hàm Java độc lập với cách triển khai. Một hàm có thể được gọi qua HTTP, messaging hoặc adapter serverless mà không phải viết lại phần xử lý nghiệp vụ. Module Spring Cloud Function Web tự động đưa các function bean thành HTTP endpoint. Springdoc-openapi có thể mô tả những endpoint đó trong OpenAPI, nhưng cần cung cấp metadata phù hợp để tài liệu thể hiện đúng tên operation, HTTP method, request, response và schema.

Trong chủ đề này có hai lớp metadata cần phân biệt:

- **Metadata của function runtime:** tên hàm, kiểu input/output, loại Supplier/Function/Consumer và thông tin cần để Spring Cloud Function chuyển đổi dữ liệu.
- **Metadata của API:** path, HTTP method, operationId, tag, tham số, request body, response status và schema mà springdoc đưa vào OpenAPI.

Metadata runtime giúp framework gọi hàm đúng kiểu. Metadata API giúp client hiểu và sử dụng HTTP contract. Có generic type rõ ràng không tự động tạo ra mô tả nghiệp vụ đầy đủ cho OpenAPI; ngược lại, annotation OpenAPI không thay đổi cách hàm thực thi.

## 1. Spring Cloud Function giải quyết vấn đề gì?

Trong ứng dụng Spring Boot truyền thống, nghiệp vụ thường nằm trong controller hoặc service. Nếu muốn chạy cùng nghiệp vụ qua HTTP, message broker và nền tảng serverless, nhóm phát triển có thể phải viết nhiều adapter và lặp lại phần chuyển đổi dữ liệu.

Spring Cloud Function tách phần xử lý thành một functional bean. Framework cung cấp adapter để gọi cùng hàm trong nhiều môi trường:

~~~text
                    +----------------------+
HTTP request ------>|                      |
Message broker ---->|   FunctionCatalog    |----> Function / Consumer / Supplier
Serverless event -->|                      |
                    +----------------------+
~~~

Các interface Java cốt lõi:

| Interface | Chức năng | Ví dụ |
|---|---|---|
| Supplier<O> | Tạo dữ liệu đầu ra, không nhận input | Tạo báo cáo hoặc danh sách |
| Function<I, O> | Nhận input và trả output | Chuẩn hóa dữ liệu sản phẩm |
| Consumer<I> | Nhận input và thực hiện side effect | Ghi nhận sự kiện, gửi thông báo |

Spring Cloud Function chuẩn hóa các function bean trong FunctionCatalog. Khi được gọi qua catalog, function có thể được bọc thêm các khả năng như chuyển đổi kiểu, composition và xử lý Message.

Spring Cloud Function Web là adapter HTTP cho mô hình này. Nó phù hợp với các hàm stateless, đơn giản cần được công bố qua HTTP. Nó không thay thế toàn bộ khả năng của Spring MVC hoặc WebFlux như controller routing phức tạp, model binding, validation và mọi quy tắc REST.

## 2. Khai báo function bean trong Spring Boot

Với cấu hình Spring thông thường, khai báo một bean có kiểu Supplier, Function hoặc Consumer:

~~~java
@SpringBootApplication
public class FunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(FunctionApplication.class, args);
    }

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

Tên method bean, trong ví dụ là uppercase, trở thành tên function mà Spring Cloud Function đăng ký. Nếu dùng Spring Cloud Function Web, function có thể được gọi qua HTTP theo tên đó.

Với nghiệp vụ có DTO, nên khai báo kiểu input và output cụ thể:

~~~java
public record NormalizeProductRequest(
    String sku,
    String displayName
) {}

public record NormalizeProductResponse(
    String sku,
    String displayName
) {}

@Configuration
class ProductFunctions {

    @Bean
    Function<NormalizeProductRequest, NormalizeProductResponse> normalizeProduct() {
        return request -> new NormalizeProductResponse(
            request.sku().trim().toUpperCase(Locale.ROOT),
            request.displayName().trim()
        );
    }
}
~~~

Kiểu generic cho Spring Cloud Function biết input là NormalizeProductRequest và output là NormalizeProductResponse. Nó cũng là nguồn thông tin hữu ích cho công cụ introspection và schema generation.

### Đặt tên function ổn định

Tên bean function trở thành một phần của URL. Đổi tên method bean từ normalizeProduct thành normalizeCatalogItem có thể làm thay đổi path được công bố. Vì vậy, hãy xem tên function đã được expose là một phần của API contract. Nếu muốn đổi tên nội bộ, có thể dùng tên bean tường minh hoặc lên kế hoạch migration endpoint.

Không dùng tên bean quá chung như process, handle hoặc execute khi ứng dụng có nhiều function. Tên như normalizeProduct, calculateShippingFee hoặc publishOrderEvent dễ đọc hơn trong URL, log và OpenAPI.

## 3. Thêm Spring Cloud Function Web

Để tự động expose function bean qua HTTP, thêm module Web hoặc starter tổng hợp của Spring Cloud Function:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Starter này tập hợp các dependency cần thiết cho trải nghiệm bắt đầu nhanh. Dự án quản lý version bằng Spring Cloud BOM tương thích với Spring Boot đang dùng; không tự ghim một version Spring Cloud Function độc lập nếu dependency management đã quản lý phiên bản.

Nếu muốn quản lý dependency ở mức thấp hơn, có thể sử dụng module spring-cloud-function-web theo hướng dẫn của phiên bản Spring Cloud Function đang chạy.

Tài liệu Spring Cloud Function hiện hành mô tả web auto-configuration cho ứng dụng Spring Boot web với MVC support. Khi dùng một web stack khác, cần xác nhận adapter và version Spring Cloud Function hỗ trợ stack đó. Việc thêm springdoc WebFlux không tự biến một adapter Servlet thành WebFlux.

### Chọn springdoc theo web stack và nhu cầu

Springdoc có starter chỉ tạo OpenAPI document và starter kèm Swagger UI:

| Web stack | Chỉ cần OpenAPI JSON/YAML | Cần cả Swagger UI |
|---|---|---|
| Spring MVC / spring-web | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webmvc-ui |
| Spring WebFlux / spring-webflux | springdoc-openapi-starter-webflux-api | springdoc-openapi-starter-webflux-ui |

Ví dụ dependency khi ứng dụng dùng Spring MVC và chỉ cần OpenAPI:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
</dependency>
~~~

Nếu cần Swagger UI, thay bằng springdoc-openapi-starter-webmvc-ui. Với Spring Boot 3, dùng dòng springdoc 2.x tương thích; với Spring Boot 4, dùng dòng springdoc 3.x. Các dự án Spring Boot 2 dùng dòng springdoc 1.x với artifact cũ. Hãy đối chiếu compatibility matrix và dependency management của dự án trước khi chọn version.

## 4. Spring Cloud Function Web ánh xạ function thành HTTP endpoint

Khi web adapter được bật, function name trở thành một phần của path. Method HTTP và loại function quyết định cách request được xử lý.

Các mapping phổ biến:

| Loại function | HTTP method | Path | Hành vi thường gặp |
|---|---|---|---|
| Supplier | GET | /{supplier} | Gọi supplier và trả dữ liệu do supplier phát ra |
| Consumer | POST hoặc PUT | /{consumer} | Gửi request body vào consumer, thường trả 202 Accepted |
| Consumer | DELETE | /{consumer} | Gọi consumer theo mapping DELETE, thường trả 204 No Content |
| Function | POST hoặc PUT | /{function} | Chuyển request body thành input, gọi function và trả output |
| Function | GET | /{function}/{item} | Chuyển path item thành input rồi gọi function |

Ví dụ với function normalizeProduct:

~~~http
POST /normalizeProduct
Content-Type: application/json
Accept: application/json

{
  "sku": " p-001 ",
  "displayName": " Bút bi "
}
~~~

Response:

~~~json
{
  "sku": "P-001",
  "displayName": "Bút bi"
}
~~~

Với Supplier tên dailyReport, HTTP adapter có thể expose GET /dailyReport. Với Consumer tên orderEvents, POST /orderEvents gửi payload tới consumer và không có response nghiệp vụ giống một Function trả kết quả.

Nếu catalog chỉ có một function, tên function trong path có thể là tùy chọn. Khi có nhiều function, tên function thường được đưa vào path để chọn đúng bean.

### Đổi prefix của các endpoint function

Có thể đặt prefix bằng property spring.cloud.function.web.path:

~~~yaml
spring:
  cloud:
    function:
      web:
        path: /functions
~~~

Khi đó function normalizeProduct có thể được gọi tại /functions/normalizeProduct. Prefix cần được dùng nhất quán trong OpenAPI, security matcher, reverse proxy và client.

## 5. Chọn function được expose và composition

Spring Cloud Function hỗ trợ composition bằng tên function. Có thể ghép nhiều function bằng ký tự pipe hoặc dấu phẩy theo quy tắc của adapter.

Ví dụ hai function:

~~~java
@Bean
Function<String, String> uppercase() {
    return value -> value.toUpperCase(Locale.ROOT);
}

@Bean
Function<String, String> reverse() {
    return value -> new StringBuilder(value).reverse().toString();
}
~~~

Có thể gọi composition theo path:

~~~text
/uppercase,reverse
~~~

Hoặc định nghĩa composition ở cấu hình:

~~~properties
spring.cloud.function.definition=uppercase|reverse
~~~

Khi dùng definition để chọn một function hoặc composition mặc định, adapter có thể map nó vào root path. Khi catalog có nhiều function, có thể giới hạn các function được export bằng danh sách phân tách dấu chấm phẩy:

~~~properties
spring.cloud.function.definition=normalizeProduct;calculateShippingFee
~~~

Khi dùng danh sách filter, chỉ những function hoặc composition được liệt kê mới được expose; không có function mặc định ở root. Hãy kiểm tra đúng cú pháp và hành vi của version Spring Cloud Function đang dùng.

Spring Cloud Function còn cho phép map function theo HTTP method bằng property spring.cloud.function.http.<method>. Ví dụ:

~~~properties
spring.cloud.function.http.GET=uppercase;reverse
spring.cloud.function.http.POST=normalizeProduct
~~~

Các mapping này tác động tới runtime HTTP routing. Chúng không tự cung cấp đầy đủ OpenAPI summary, request schema, response schema hoặc mã lỗi. Phần mô tả contract vẫn cần được khai báo trong springdoc.

## 6. Content-Type và chuyển đổi dữ liệu vào function

Spring Cloud Function chuyển dữ liệu thô của request thành kiểu input được khai báo trong function. Quá trình này dựa vào generic type, Content-Type và các MessageConverter/ConversionService phù hợp.

Ví dụ:

| Content-Type | Input function thường dùng |
|---|---|
| application/json | DTO hoặc Map |
| text/plain | String |
| application/octet-stream | byte[] hoặc InputStream tùy cách khai báo |

Với function:

~~~java
Function<NormalizeProductRequest, NormalizeProductResponse> normalizeProduct()
~~~

client nên gửi Content-Type: application/json và JSON có cấu trúc tương thích với NormalizeProductRequest. Nếu thiếu Content-Type, Spring Cloud Function có thể dùng application/json làm mặc định trong các trường hợp được tài liệu hỗ trợ; API client vẫn nên gửi header tường minh.

Ví dụ gọi bằng curl:

~~~bash
curl -i \
  -X POST http://localhost:8080/functions/normalizeProduct \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"sku":" p-001 ","displayName":" Bút bi "}'
~~~

Không nhầm Content-Type với Accept:

- Content-Type mô tả định dạng body client gửi lên.
- Accept mô tả định dạng response client muốn nhận.

Nếu không có converter phù hợp với input type và Content-Type, function có thể không được gọi và request thất bại khi chuyển đổi dữ liệu. Với kiểu dữ liệu đặc biệt, có thể cần đăng ký custom MessageConverter.

## 7. Truyền header và query parameter bằng Message

Function có thể nhận Message<T> thay vì chỉ nhận payload T. Message chứa payload và headers, cho phép nghiệp vụ sử dụng correlation ID, tenant, request metadata hoặc thông tin do adapter truyền vào.

~~~java
@Bean
Function<Message<NormalizeProductRequest>, Message<NormalizeProductResponse>>
normalizeProductWithMetadata() {
    return message -> {
        NormalizeProductRequest request = message.getPayload();
        NormalizeProductResponse response = new NormalizeProductResponse(
            request.sku().trim().toUpperCase(Locale.ROOT),
            request.displayName().trim()
        );

        return MessageBuilder.withPayload(response)
            .copyHeaders(message.getHeaders())
            .build();
    };
}
~~~

Khi function nhận Message, các HTTP request header có thể được chuyển thành message header. Với function trả Message, output headers có thể được chuyển thành HTTP response headers. Payload vẫn là phần dữ liệu chính cần mô tả trong OpenAPI.

HTTP query parameter được adapter đưa vào message header với key http_request_param, giá trị là một Map. Vì vậy, nếu function cần đọc query parameter, có thể khai báo input là Message<T> và đọc header tương ứng. Không nên coi query parameter tự động trở thành property của DTO input nếu không có cơ chế binding riêng.

Ví dụ ý tưởng đọc query parameter:

~~~java
@Bean
Function<Message<String>, String> greet() {
    return message -> {
        Object params = message.getHeaders().get("http_request_param");
        return "Hello " + message.getPayload() + " (" + params + ")";
    };
}
~~~

Không đưa các header nội bộ, token hoặc dữ liệu nhạy cảm vào response header. Nếu OpenAPI cần công bố một header request/response, hãy khai báo bằng @Parameter hoặc @ApiResponse header metadata và xác minh giá trị thực tế.

## 8. Siêu dữ liệu kiểu của FunctionCatalog

FunctionCatalog là nơi Spring Cloud Function đăng ký và tra cứu các function. Các bean có kiểu Supplier, Function hoặc Consumer được phát hiện và chuẩn hóa thành function invocation có metadata phù hợp.

Trong khai báo @Bean thông thường, framework thường có thể suy luận input/output type từ generic signature. Ví dụ Function<NormalizeProductRequest, NormalizeProductResponse> cung cấp thông tin kiểu rõ ràng.

Một số cách khai báo function có thể làm mất generic type ở runtime, chẳng hạn đăng ký function bằng functional bean definition hoặc dùng raw Function/Object. Khi đó, có thể dùng FunctionRegistration để cung cấp thông tin kiểu:

~~~java
Function<NormalizeProductRequest, NormalizeProductResponse> function =
    request -> new NormalizeProductResponse(
        request.sku().trim().toUpperCase(Locale.ROOT),
        request.displayName().trim()
    );

FunctionRegistration<Function<NormalizeProductRequest, NormalizeProductResponse>>
    registration = new FunctionRegistration<>(function)
        .type(FunctionType.from(NormalizeProductRequest.class)
            .to(NormalizeProductResponse.class));
~~~

FunctionRegistration đóng gói function cùng type metadata. FunctionType mô tả kiểu input và output. Metadata này phục vụ việc gọi hàm và chuyển đổi dữ liệu; nó không thay thế OpenAPI schema annotation.

### Tra cứu function trong FunctionCatalog

Có thể inject FunctionCatalog để tra cứu hoặc liệt kê function:

~~~java
@Component
class FunctionInspector {

    private final FunctionCatalog catalog;

    FunctionInspector(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    Set<String> functionNames() {
        return catalog.getNames(null);
    }

    Function<?, ?> findNormalizeProduct() {
        return catalog.lookup("normalizeProduct");
    }
}
~~~

FunctionCatalog lookup trả về function đã được framework instrument với các khả năng như type conversion và composition. Không nên lấy bean function trực tiếp rồi giả định nó có đủ các lớp hỗ trợ giống function lấy qua catalog.

### Xem metadata bằng Actuator

Spring Cloud Function có thể công bố danh sách function trong Actuator endpoint functions nếu ứng dụng thêm Spring Boot Actuator và expose endpoint tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,functions
~~~

Endpoint /actuator/functions có thể hiển thị tên function, loại FUNCTION/CONSUMER/SUPPLIER và input/output type. Đây là endpoint vận hành để kiểm tra catalog, không phải OpenAPI document. Chỉ expose khi có nhu cầu và bảo vệ bằng Spring Security hoặc management network policy; không công khai danh sách function nội bộ một cách mặc định.

## 9. Siêu dữ liệu OpenAPI khác với metadata runtime

FunctionCatalog có thể biết kiểu input và output nhưng không biết đầy đủ ý nghĩa nghiệp vụ của HTTP operation. Ví dụ, từ Function<OrderRequest, OrderResponse>, công cụ có thể suy luận schema nhưng không thể tự biết:

- Endpoint dùng POST hay PUT.
- Operation có tên công khai và mục đích gì.
- Request body có bắt buộc hay không.
- Những status code như 400, 404 hoặc 409 có thể xảy ra trong nghiệp vụ.
- Field nào deprecated, nhạy cảm hoặc chỉ đọc.
- Endpoint yêu cầu OAuth scope nào.
- Những header hoặc query parameter nào là một phần của contract.

Springdoc cung cấp metadata annotation để mô tả các thông tin đó:

| Annotation | Vai trò |
|---|---|
| @RouterOperation | Mô tả một operation được tạo từ function hoặc functional endpoint |
| @RouterOperations | Mô tả nhiều operation được expose từ cùng một bean/function |
| @Operation | Summary, description, operationId, tag, security và request body |
| @ApiResponse | HTTP response status và nội dung trả về |
| @Content | Media type và schema của request/response |
| @Schema | Tên, kiểu, mô tả, ví dụ và constraint của model |
| @Parameter | Path, query, header hoặc cookie parameter |
| OpenApiCustomizer | Chỉnh OpenAPI model sau khi springdoc tổng hợp document |

Springdoc hỗ trợ mô tả Spring Cloud Function Web từ phiên bản 1.6.3. Với các version hiện hành, có thể dùng @RouterOperation, @RouterOperations hoặc OpenApiCustomizer để bổ sung metadata.

Với springdoc 2.x và 3.x, các annotation RouterOperation/RouterOperations thuộc package org.springdoc.core.annotations. Dự án springdoc 1.x dùng package cũ org.springdoc.api.annotations. Hãy dùng import theo major version đang cài; không trộn annotation từ hai major version.

## 10. Mô tả một function bằng @RouterOperation

Với một function bean tương ứng một HTTP operation, có thể gắn @RouterOperation trực tiếp lên method @Bean. Nên khai báo path và method tường minh nếu muốn tránh nhập nhằng giữa mapping runtime và tài liệu.

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.web.bind.annotation.RequestMethod;

@Configuration
class ProductFunctionConfiguration {

    @Bean
    @RouterOperation(
        path = "/normalizeProduct",
        method = RequestMethod.POST,
        operation = @Operation(
            operationId = "products_normalize",
            summary = "Chuẩn hóa thông tin sản phẩm",
            description = "Chuẩn hóa SKU và tên hiển thị của sản phẩm.",
            tags = {"Products"},
            requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
                required = true,
                content = @Content(
                    mediaType = "application/json",
                    schema = @Schema(implementation = NormalizeProductRequest.class)
                )
            ),
            responses = {
                @ApiResponse(
                    responseCode = "200",
                    description = "Thông tin sản phẩm đã chuẩn hóa",
                    content = @Content(
                        mediaType = "application/json",
                        schema = @Schema(implementation = NormalizeProductResponse.class)
                    )
                ),
                @ApiResponse(
                    responseCode = "400",
                    description = "Request body không hợp lệ"
                )
            }
        )
    )
    Function<NormalizeProductRequest, NormalizeProductResponse> normalizeProduct() {
        return request -> new NormalizeProductResponse(
            request.sku().trim().toUpperCase(Locale.ROOT),
            request.displayName().trim()
        );
    }
}
~~~

Trong ví dụ:

- Tên bean normalizeProduct được Spring Cloud Function dùng để định danh function.
- Path /normalizeProduct và method POST mô tả route HTTP tương ứng.
- operationId products_normalize là định danh ổn định của operation trong OpenAPI.
- requestBody mô tả NormalizeProductRequest.
- response 200 mô tả NormalizeProductResponse.
- response 400 cung cấp thông tin lỗi mà client cần biết.

Nếu ứng dụng cấu hình prefix /functions, path public sẽ là /functions/normalizeProduct. Hãy xác nhận path cuối cùng trong /v3/api-docs thay vì chỉ nhìn annotation.

operationId phải duy nhất trong OpenAPI document. Không dùng operationId trùng nhau cho nhiều function hoặc nhiều HTTP method.

@RouterOperation chỉ bổ sung metadata cho springdoc, không tự đăng ký HTTP route và không thay đổi mapping của Spring Cloud Function Web. Nếu annotation mô tả PUT nhưng runtime chỉ nhận POST, OpenAPI sẽ công bố một operation không thể gọi. Luôn kiểm tra cả mapping runtime và OpenAPI document.

## 11. Mô tả nhiều HTTP operation bằng @RouterOperations

Một function có thể được gọi bằng nhiều HTTP method. Khi cần mô tả nhiều operation gắn với cùng bean, dùng @RouterOperations. Mỗi @RouterOperation cần có method; nên khai báo path rõ ràng để springdoc nhận diện đúng route.

~~~java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/normalizeProduct",
        method = RequestMethod.POST,
        operation = @Operation(
            operationId = "products_normalizePost",
            summary = "Chuẩn hóa sản phẩm bằng POST",
            tags = {"Products"},
            responses = @ApiResponse(
                responseCode = "200",
                description = "Sản phẩm đã chuẩn hóa",
                content = @Content(
                    mediaType = "application/json",
                    schema = @Schema(implementation = NormalizeProductResponse.class)
                )
            )
        )
    ),
    @RouterOperation(
        path = "/normalizeProduct",
        method = RequestMethod.PUT,
        operation = @Operation(
            operationId = "products_normalizePut",
            summary = "Chuẩn hóa sản phẩm bằng PUT",
            tags = {"Products"},
            responses = @ApiResponse(
                responseCode = "200",
                description = "Sản phẩm đã chuẩn hóa",
                content = @Content(
                    mediaType = "application/json",
                    schema = @Schema(implementation = NormalizeProductResponse.class)
                )
            )
        )
    )
})
Function<NormalizeProductRequest, NormalizeProductResponse> normalizeProduct() {
    return request -> new NormalizeProductResponse(
        request.sku().trim().toUpperCase(Locale.ROOT),
        request.displayName().trim()
    );
}
~~~

Đây là ví dụ mô tả hai method mà Spring Cloud Function Web có thể dùng để gọi một Function. Chỉ công bố các method thực sự được adapter và cấu hình ứng dụng hỗ trợ. Nếu runtime chỉ cho phép POST, không đưa PUT vào OpenAPI chỉ vì annotation có thể khai báo nó.

Với một bean có nhiều function route hoặc nhiều path, hãy cung cấp đủ path, method, consumes/produces hoặc các điều kiện cần thiết để nhận diện duy nhất route. Nếu annotation trùng hoặc không khớp mapping runtime, tài liệu có thể thiếu operation hoặc mô tả nhầm operation.

## 12. Liên kết metadata với bean method

Khi function được khai báo ở một bean nhưng metadata nằm trên method khác, @RouterOperation có thể dùng beanClass và beanMethod để springdoc tìm method cần introspect. Cách này hữu ích khi method xử lý có Swagger annotations riêng hoặc function bean chỉ là adapter mỏng.

~~~java
@RouterOperation(
    path = "/employees",
    method = RequestMethod.GET,
    beanClass = EmployeeQueryService.class,
    beanMethod = "findAll",
    operation = @Operation(
        operationId = "employees_findAll",
        summary = "Liệt kê nhân viên",
        tags = {"Employees"}
    )
)
@Bean
Supplier<List<EmployeeResponse>> employees() {
    return employeeQueryService::findAll;
}
~~~

Ví dụ trên minh họa việc tham chiếu method cung cấp metadata nghiệp vụ. Tên class và method phải tồn tại, method phải có kiểu và annotation phù hợp với operation. Nếu method beanMethod được khai báo, @Operation cũng có thể được đặt trên method đó theo cách springdoc hỗ trợ.

Không nên khai báo beanClass/beanMethod chỉ để lặp lại thông tin không cần thiết. Dùng chúng khi thực sự cần springdoc đọc metadata từ một method khác.

## 13. Mô tả Supplier và Consumer

Supplier không nhận request body; nó tạo dữ liệu khi được gọi. OpenAPI nên mô tả operation GET, response schema và điều kiện response.

~~~java
@Bean
@RouterOperation(
    path = "/dailyReport",
    method = RequestMethod.GET,
    operation = @Operation(
        operationId = "reports_getDaily",
        summary = "Lấy báo cáo trong ngày",
        tags = {"Reports"},
        responses = @ApiResponse(
            responseCode = "200",
            description = "Báo cáo hiện tại",
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = DailyReport.class)
            )
        )
    )
)
Supplier<DailyReport> dailyReport() {
    return reportService::createCurrentReport;
}
~~~

Consumer nhận dữ liệu và thực hiện side effect, chẳng hạn ghi nhận event. Vì Consumer không trả dữ liệu nghiệp vụ, response thường là 202 Accepted hoặc 204 No Content tùy HTTP mapping. Hãy mô tả chính xác status code và body runtime thực tế.

~~~java
@Bean
@RouterOperation(
    path = "/orderEvents",
    method = RequestMethod.POST,
    operation = @Operation(
        operationId = "orders_publishEvent",
        summary = "Gửi sự kiện đơn hàng",
        tags = {"Orders"},
        requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
            required = true,
            content = @Content(
                mediaType = "application/json",
                schema = @Schema(implementation = OrderEvent.class)
            )
        ),
        responses = @ApiResponse(
            responseCode = "202",
            description = "Sự kiện đã được tiếp nhận"
        )
    )
)
Consumer<OrderEvent> orderEvents() {
    return event -> eventPublisher.publish(event);
}
~~~

Không mô tả Consumer như một Function có response object nếu runtime chỉ chấp nhận và xử lý input. Nếu HTTP adapter mirror lại payload trong response, hãy kiểm tra response thực tế và mô tả đúng representation đó.

## 14. Schema input/output và annotation trên DTO

Generic type của Function cung cấp cơ sở để springdoc suy luận schema, nhưng DTO vẫn cần mô tả rõ các field có ý nghĩa nghiệp vụ:

~~~java
@Schema(name = "NormalizeProductRequest", description = "Dữ liệu đầu vào để chuẩn hóa sản phẩm")
public record NormalizeProductRequest(
    @Schema(description = "Mã SKU", example = "p-001", minLength = 1, maxLength = 40)
    String sku,

    @Schema(description = "Tên hiển thị", example = "Bút bi", minLength = 1, maxLength = 160)
    String displayName
) {}

@Schema(name = "NormalizeProductResponse", description = "Sản phẩm sau khi chuẩn hóa")
public record NormalizeProductResponse(
    @Schema(description = "SKU viết hoa và đã loại khoảng trắng thừa", example = "P-001")
    String sku,

    @Schema(description = "Tên hiển thị đã loại khoảng trắng thừa", example = "Bút bi")
    String displayName
) {}
~~~

@Schema mô tả schema trong OpenAPI. Nếu cần validation ở runtime, dùng Bean Validation như @NotBlank, @Size hoặc custom validator trên DTO. Chỉ ghi minLength/maxLength trong OpenAPI không tự làm server từ chối dữ liệu sai.

Với function nhận Message<NormalizeProductRequest>, schema request body nên mô tả payload NormalizeProductRequest, không nên tạo model Message wrapper như thể đó là JSON body client phải gửi. Header của Message cần được mô tả riêng bằng OpenAPI Parameter nếu nó là một phần contract công khai.

## 15. OpenApiCustomizer cho metadata cần tính toán

Annotation phù hợp khi metadata tĩnh và gắn với một function cụ thể. Nếu cần chuẩn hóa operationId, thêm response dùng chung, chỉnh server URL hoặc cập nhật metadata dựa trên profile/group, có thể dùng OpenApiCustomizer.

Ví dụ bổ sung mô tả cho operation đã được springdoc tạo:

~~~java
@Configuration
class FunctionOpenApiConfiguration {

    @Bean
    OpenApiCustomizer functionOperationCustomizer() {
        return openApi -> {
            PathItem pathItem = openApi.getPaths().get("/functions/normalizeProduct");
            if (pathItem != null && pathItem.getPost() != null) {
                pathItem.getPost()
                    .setDescription("Chuẩn hóa SKU và tên hiển thị của sản phẩm.");
            }
        };
    }
}
~~~

Đoạn code này giả định application đã cấu hình prefix /functions và path operation tương ứng. Nếu prefix hoặc function name thay đổi, cần cập nhật path. Với nhiều OpenAPI group, đăng ký customizer vào đúng group hoặc dùng cơ chế global tương ứng.

OpenApiCustomizer chỉ sửa OpenAPI model được sinh ra. Nó không đăng ký function mới, không đổi HTTP mapping, không thêm validation runtime và không thay đổi security filter chain.

## 16. Function composition và OpenAPI contract

Composition cho phép nối nhiều function thành một pipeline:

~~~java
@Bean
Function<String, String> trim() {
    return String::trim;
}

@Bean
Function<String, String> uppercase() {
    return value -> value.toUpperCase(Locale.ROOT);
}

@Bean
Function<String, String> normalizeSku() {
    return value -> value.replace(" ", "");
}
~~~

Một composition có thể được định nghĩa bằng:

~~~properties
spring.cloud.function.definition=trim|uppercase|normalizeSku
~~~

Từ góc nhìn OpenAPI, composition thường là một operation có input type của function đầu tiên và output type của function cuối cùng. Không nhất thiết tạo operation riêng cho từng bước nội bộ. Nếu composition được expose qua một path, hãy mô tả contract của pipeline đó bằng một operationId và schema đầu vào/đầu ra ổn định.

Khi các function có kiểu trung gian không tương thích trực tiếp, Spring Cloud Function có thể dùng content-type conversion và MessageConverter để chuyển đổi trong composition. Đừng mô tả kiểu trung gian nội bộ thành request/response công khai nếu client không trực tiếp trao đổi kiểu đó.

## 17. Sinh OpenAPI và kiểm tra document

Với springdoc API starter, document mặc định thường có tại:

~~~text
/v3/api-docs
/v3/api-docs.yaml
~~~

Nếu dùng UI starter, Swagger UI cũng có thể hiển thị document. Khi chạy ứng dụng, kiểm tra:

1. Operation function có xuất hiện trong paths không.
2. Path có bao gồm spring.cloud.function.web.path hoặc context path đúng không.
3. HTTP method có khớp mapping thực tế không.
4. operationId có duy nhất và ổn định không.
5. Request body có đúng media type và schema input không.
6. Response status, media type và schema output có khớp runtime không.
7. Consumer có response phù hợp với hành vi chấp nhận dữ liệu không.
8. Security requirement có phản ánh chính sách bảo vệ endpoint không.
9. Function không được expose có xuất hiện trong document hay không.

Ví dụ OpenAPI YAML rút gọn:

~~~yaml
paths:
  /functions/normalizeProduct:
    post:
      operationId: products_normalize
      summary: Chuẩn hóa thông tin sản phẩm
      tags:
        - Products
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/NormalizeProductRequest'
      responses:
        '200':
          description: Sản phẩm đã chuẩn hóa
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NormalizeProductResponse'
        '400':
          description: Request body không hợp lệ
components:
  schemas:
    NormalizeProductRequest:
      type: object
      required:
        - sku
        - displayName
      properties:
        sku:
          type: string
        displayName:
          type: string
    NormalizeProductResponse:
      type: object
      properties:
        sku:
          type: string
        displayName:
          type: string
~~~

Đây là ví dụ contract mong muốn. Tài liệu sinh ra thực tế có thể thêm metadata như servers, tags, security, schema format và response khác tùy cấu hình. Luôn kiểm tra JSON/YAML thực tế thay vì giả định annotation đã được xử lý đúng.

## 18. Kiểm thử HTTP function và OpenAPI

Nên kiểm thử cả hai lớp: function được gọi đúng qua HTTP và OpenAPI document mô tả đúng endpoint.

### Kiểm thử function bằng MockMvc

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductFunctionHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void normalizesProduct() throws Exception {
        mockMvc.perform(post("/functions/normalizeProduct")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "sku": " p-001 ",
                      "displayName": " Bút bi "
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sku").value("P-001"))
            .andExpect(jsonPath("$.displayName").value("Bút bi"));
    }
}
~~~

Test giả định application đã đặt function web path là /functions. Nếu dùng path mặc định, gọi /normalizeProduct.

### Kiểm thử OpenAPI operation

~~~java
@Test
void exposesNormalizeProductOperation() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.paths['/functions/normalizeProduct'].post.operationId"
        ).value("products_normalize"))
        .andExpect(jsonPath(
            "$.paths['/functions/normalizeProduct'].post.requestBody.content['application/json'].schema"
        ).exists());
}
~~~

Nếu JSONPath implementation không hỗ trợ biểu thức chứa key có dấu gạch hoặc dấu chấm, hãy đọc object OpenAPI rồi assert trực tiếp trong test. Test cần xác minh operationId, method, path, request schema và response schema.

### Kiểm thử consumer và supplier

Với Consumer, xác nhận status code và side effect (ví dụ event được publish hoặc record được lưu). Với Supplier, xác nhận GET trả dữ liệu đúng media type. Không chỉ kiểm tra status 202/200 mà bỏ qua kết quả nghiệp vụ.

## 19. Function reactive và response nhiều phần tử

Spring Cloud Function hỗ trợ function dùng Mono và Flux. Khi function trả nhiều phần tử, HTTP adapter có thể trả dữ liệu nhiều giá trị. Client có thể yêu cầu server-sent event stream bằng Accept: text/event-stream.

Ví dụ function reactive:

~~~java
@Bean
Function<Flux<String>, Flux<String>> lowercase() {
    return values -> values.map(value -> value.toLowerCase(Locale.ROOT));
}
~~~

Client gửi nhiều dòng text:

~~~http
POST /lowercase
Content-Type: text/plain
Accept: text/event-stream

HELLO
WORLD
~~~

Với output nhiều phần tử, Accept: text/event-stream yêu cầu representation SSE nếu endpoint và codec hỗ trợ. Nếu client muốn một JSON document thông thường, phải chọn media type và kiểu output phù hợp; đừng suy luận cách đóng khung response chỉ từ Flux.

Trong OpenAPI, mô tả đúng media type mà endpoint trả. Với SSE, response content dùng text/event-stream và description giải thích event framing. Nếu output là JSON array, schema cần là array với items trỏ tới schema phần tử. Nếu là stream event, không mô tả nó như một JSON array hoàn chỉnh.

~~~yaml
responses:
  '200':
    description: Luồng sự kiện được gửi qua Server-Sent Events
    content:
      text/event-stream:
        schema:
          type: string
~~~

Springdoc có thể cần metadata response tường minh khi generic reactive type không đủ để suy luận representation. Hãy kiểm tra Content-Type và body thực tế bằng test, curl hoặc WebTestClient trước khi chốt OpenAPI contract.

## 20. Bảo mật khi expose function qua HTTP

Khi dùng Spring Cloud Function Web, các function trong catalog có thể trở thành endpoint. Vì vậy, cần kiểm soát function nào được expose và ai được gọi.

Các nguyên tắc:

- Chỉ export function cần thiết; dùng spring.cloud.function.definition để giới hạn function hoặc composition.
- Bảo vệ endpoint function bằng Spring Security, OAuth2 Resource Server hoặc cơ chế authentication phù hợp.
- Áp dụng authorization theo function hoặc nhóm API; không mặc định mọi function trong catalog đều công khai.
- Bảo vệ /actuator/functions và các endpoint Actuator khác bằng management security policy.
- Không để lộ bean nội bộ chỉ vì bean đó có kiểu Function, Supplier hoặc Consumer.
- Kiểm tra request body, kích thước payload, rate limit, timeout và giới hạn concurrency.

### Cẩn trọng với routing-expression

Spring Cloud Function hỗ trợ routing bằng header spring.cloud.function.definition hoặc spring.cloud.function.routing-expression trong một số trường hợp. routing-expression sử dụng SpEL và tài liệu cảnh báo rằng nếu người dùng không tin cậy có thể gửi expression qua HTTP header, họ có thể tạo rủi ro thực thi biểu thức ngoài ý muốn.

Không cho client Internet tự do truyền routing-expression. Ưu tiên route cố định bằng function name, allowlist function được export hoặc tự xây dựng một bộ định tuyến kiểm tra tên function trong danh sách cho phép. Với reactive function, routing instruction qua message header không có cùng khả năng route per-message như imperative function; hãy kiểm tra quy tắc của version đang dùng.

### OpenAPI security metadata phải khớp runtime

Nếu endpoint yêu cầu Bearer token, khai báo security scheme và security requirement trong OpenAPI. Nhưng annotation chỉ mô tả tài liệu; Spring Security mới thực thi xác thực và phân quyền. Nếu Swagger UI hiển thị endpoint không cần xác thực trong khi runtime trả 401/403, cần đồng bộ security metadata.

Ví dụ khai báo security scheme:

~~~java
@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class FunctionApiSecurityConfiguration {}
~~~

Gắn security requirement vào operation bằng @Operation(security = ...), hoặc cấu hình ở cấp OpenAPI document nếu mọi function đều dùng cùng cơ chế. Nếu chỉ một số function cần quyền khác nhau, đặt security requirement theo từng operation và kiểm tra lại với Spring Security matcher.

## 21. Giới hạn và lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Function không xuất hiện qua HTTP | Thiếu Spring Cloud Function Web hoặc bean không được đăng ký | Kiểm tra dependency, ApplicationContext và FunctionCatalog |
| Path function trả 404 | Tên path không khớp tên function hoặc web path prefix | Kiểm tra tên @Bean và spring.cloud.function.web.path |
| Request JSON không chuyển thành DTO | Thiếu Content-Type hoặc converter không hỗ trợ kiểu input | Gửi application/json và kiểm tra generic type/converter |
| Function nhận Map thay vì DTO | Input type bị mất hoặc khai báo raw Function/Object | Khai báo generic rõ ràng hoặc đăng ký FunctionRegistration |
| OpenAPI thiếu operation function | Chưa có metadata hoặc springdoc không nhận diện mapping | Dùng @RouterOperation/@RouterOperations và kiểm tra web stack |
| Operation có path hoặc method sai | Metadata không khớp mapping của adapter | Khai báo path/method tường minh và kiểm tra document runtime |
| operationId bị trùng | Nhiều function dùng tên operationId giống nhau | Đặt operationId duy nhất trong document |
| Request/response schema là Object chung | Generic type bị mất hoặc function dùng Message/raw type | Cung cấp FunctionRegistration type và @Schema implementation |
| Consumer được mô tả như response object | Nhầm Consumer với Function | Mô tả 202/204 và side effect thực tế |
| Function nội bộ bị expose | Không lọc function catalog hoặc thiếu security | Dùng definition allowlist và Spring Security |
| Header routing cho phép chọn function tùy ý | Tin cậy function name/routing-expression từ client | Kiểm tra allowlist, không nhận SpEL tùy ý |
| Actuator functions lộ metadata nội bộ | Endpoint functions được expose công khai | Giới hạn management port và yêu cầu role phù hợp |
| Swagger UI gọi endpoint nhưng trả 401/403 | OpenAPI security metadata hoặc security matcher chưa đồng bộ | Kiểm tra scheme, scope và Spring Security chain |

## 22. Quy trình tích hợp Spring Cloud Function Web với springdoc

Khi thêm tài liệu OpenAPI cho function endpoint, thực hiện theo thứ tự:

1. Khai báo function bean với Supplier, Function hoặc Consumer và generic input/output cụ thể.
2. Thêm Spring Cloud Function Web và quản lý version theo Spring Cloud BOM tương thích.
3. Xác định web stack thực tế; chọn springdoc webmvc hoặc webflux starter phù hợp.
4. Chọn API-only starter hay UI starter theo cách phân phối tài liệu.
5. Xác định function name, HTTP path, method và prefix.
6. Dùng @RouterOperation cho một operation hoặc @RouterOperations cho nhiều operation.
7. Đặt operationId duy nhất; khai báo request body, response status, media type, tags và schema.
8. Dùng FunctionRegistration nếu runtime không suy luận được generic input/output type.
9. Dùng OpenApiCustomizer cho metadata cần chuẩn hóa hoặc tính toán.
10. Giới hạn function được export và bảo vệ endpoint bằng Spring Security.
11. Kiểm thử function HTTP, content negotiation và OpenAPI JSON/YAML.
12. So sánh contract sinh ra với request/response thực tế trước khi phát hành.

Spring Cloud Function Web cung cấp adapter để đưa function bean thành HTTP endpoint. FunctionCatalog và FunctionRegistration quản lý function cùng type metadata; springdoc sử dụng metadata OpenAPI để mô tả operation cho client. Khi hai lớp được khai báo nhất quán, nhóm phát triển có thể tái sử dụng nghiệp vụ dạng function mà vẫn cung cấp API contract rõ ràng, có thể kiểm thử và sinh client.

## 23. Tài liệu tham khảo

- [Spring Cloud Function 5.0.5 – Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html): expose Supplier, Function và Consumer qua HTTP; path, method, content type, function mapping và filtering.
- [Spring Cloud Function – Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): FunctionCatalog, Function/Consumer/Supplier, Message, headers và function composition.
- [Spring Cloud Function – Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/docs/current/reference/html/functional.html): FunctionRegistration và metadata input/output type.
- [Spring Cloud Function – Reference Documentation](https://docs.spring.io/spring-cloud-function/reference/index.html): version, module và hướng dẫn tích hợp.
- [Springdoc OpenAPI – Spring Cloud Function Web support](https://springdoc.org/modules.html#spring-cloud-function-web-support): springdoc starter, @RouterOperation, @RouterOperations và OpenApiCustomizer.
- [Springdoc OpenAPI – Features](https://springdoc.org/features.html#spring-webfluxwebmvc-fn-with-functional-endpoints): metadata cho functional endpoints và cách ánh xạ operation.
- [OpenAPI Specification – Operation Object](https://spec.openapis.org/oas/latest.html#operation-object): operationId, summary, parameters, requestBody và responses.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): schema cho request và response.

# Kiểm tra thứ tự ưu tiên khi cấu hình và annotation cùng tác động

Trong Spring Boot dùng `springdoc-openapi`, một operation có thể nhận thông tin từ nhiều nguồn: mapping của Spring MVC, kiểu dữ liệu và annotation trên DTO, Swagger/OpenAPI annotations, bean `OpenAPI`, customizer và các thuộc tính `springdoc.*`. Khi nhiều nguồn cùng mô tả một nội dung, chẳng hạn response, schema, server hoặc summary, tài liệu sinh ra có thể khác với điều người phát triển dự đoán.

Không có một quy tắc “annotation luôn thắng cấu hình” hoặc “cấu hình luôn thắng annotation” áp dụng cho tất cả trường hợp. Mỗi nguồn có phạm vi riêng. Spring quyết định request thực tế được định tuyến và serialize như thế nào; Springdoc thu thập các thông tin đó để tạo tài liệu; Swagger annotations bổ sung metadata; customizer có thể sửa mô hình OpenAPI đã tạo; còn thuộc tính cấu hình điều khiển cách Springdoc hoạt động. Muốn xử lý xung đột chính xác, trước hết phải xác định trường nào đang bị tác động và nguồn nào có quyền quyết định trường đó.

## 1. Phân biệt các lớp thông tin

Một tài liệu OpenAPI được tạo từ nhiều lớp dữ liệu. Có thể nhìn chúng theo vai trò sau:

| Nguồn | Phạm vi quyết định | Ví dụ | Tác động trực tiếp đến API runtime? |
|---|---|---|---|
| Spring MVC/WebFlux mapping | HTTP method, path, params, headers, consumes, produces và handler được gọi | `@GetMapping`, `@RequestMapping` | Có |
| Kiểu Java và cấu hình serialize | Dữ liệu thực tế được đọc, ghi và chuyển thành JSON/XML | DTO, Jackson, `@JsonProperty`, `@JsonIgnore` | Có |
| Swagger/OpenAPI annotations | Metadata mô tả operation, parameter, schema, request, response và security | `@Operation`, `@Schema`, `@ApiResponse` | Không |
| Bean `OpenAPI` hoặc `@OpenAPIDefinition` | Metadata cấp tài liệu như title, version, contact, license, server | `new OpenAPI().info(...)` | Không |
| Springdoc properties | Bật/tắt endpoint, đường dẫn, phạm vi quét, media type mặc định, UI và hành vi tích hợp | `springdoc.api-docs.path` | Thường không; chủ yếu ảnh hưởng việc sinh/phục vụ tài liệu |
| Customizer | Sửa mô hình OpenAPI hoặc operation trong quá trình tạo tài liệu | `OperationCustomizer`, `OpenApiCustomizer` | Không |
| Swagger UI properties | Cách giao diện tải và hiển thị tài liệu | `springdoc.swagger-ui.path`, `doc-expansion` | Không |

Điểm cần nhớ là metadata trong tài liệu không thay thế cấu hình runtime. Ví dụ, `@Operation(summary = "... ")` có thể thay đổi nội dung mô tả operation, nhưng không thay đổi URL mà Spring MVC đăng ký. Tương tự, `@SecurityRequirement` mô tả yêu cầu bảo mật trong OpenAPI, còn Spring Security mới thực thi quyền truy cập.

## 2. Mapping của Spring quyết định request thật

Springdoc lấy endpoint từ các handler mà Spring đăng ký. Những annotation như `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestParam` và các thuộc tính `headers`, `consumes`, `produces` quyết định request nào được định tuyến đến method nào.

Ví dụ:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping(value = "/{id}", produces = "application/json")
    @Operation(
        summary = "Tra cứu sản phẩm",
        description = "Lấy thông tin một sản phẩm theo mã định danh."
    )
    ProductResponse getById(@PathVariable Long id) {
        return productService.getById(id);
    }
}
```

Trong trường hợp này:

- Spring mapping tạo route `GET /api/products/{id}` và giới hạn kiểu nội dung response theo cấu hình `produces`.
- `@PathVariable` xác định tham số `id` lấy từ path.
- `@Operation` cung cấp summary và description cho operation trong tài liệu.

Nếu summary hoặc description trong `@Operation` nói endpoint dùng POST trong khi mapping là GET, request thực tế vẫn không biến thành POST. `@Operation` không khai báo route hay HTTP method; annotation Swagger không thay đổi mapping đã đăng ký với Spring. Khi nội dung mô tả và mapping mâu thuẫn, hãy sửa phần mô tả hoặc mapping theo hợp đồng mong muốn rồi kiểm tra lại cả API thật và tài liệu được sinh.

Các thuộc tính `springdoc.paths-to-match`, `springdoc.packages-to-scan` hoặc cấu hình tương ứng trong `GroupedOpenApi` giới hạn endpoint được đưa vào tài liệu. Chúng không tạo thêm route và cũng không thay đổi mapping. Một endpoint có thể hoạt động bình thường nhưng không xuất hiện trong tài liệu nếu nằm ngoài phạm vi quét của tài liệu hoặc group đang xem.

## 3. Swagger annotations bổ sung metadata cho thông tin Spring suy luận

Springdoc có thể suy luận method, path, parameter và nhiều schema từ Spring handler cùng kiểu Java. Swagger annotations giúp mô tả những thông tin không thể hiện đầy đủ qua chữ ký method.

| Annotation | Nội dung thường bổ sung |
|---|---|
| `@Tag` | Tên và mô tả nhóm operation |
| `@Operation` | Summary, description, operationId, tag và metadata operation |
| `@Parameter` | Mô tả, ví dụ, required và schema của tham số |
| `@ApiResponse` | Mô tả response theo status code, media type và schema |
| `@RequestBody` của Swagger | Mô tả request body, content và ví dụ |
| `@Schema` | Mô tả schema, property, ví dụ, format và ràng buộc |
| `@SecurityScheme` | Khai báo cơ chế xác thực trong tài liệu |
| `@SecurityRequirement` | Gắn yêu cầu sử dụng security scheme cho operation hoặc controller |
| `@Hidden` | Loại phần tử được hỗ trợ khỏi tài liệu |

Khi annotation mô tả một trường mà Springdoc có thể suy luận, annotation thường được dùng để làm rõ hoặc điều chỉnh metadata được sinh. Tuy nhiên, cách hợp nhất các thuộc tính phức tạp như response content, schema composition hoặc tham chiếu có thể phụ thuộc phiên bản Springdoc và Swagger Core. Không nên giả định rằng toàn bộ object sẽ được thay thế nguyên khối hoặc mọi thuộc tính đều được merge theo cùng một cách.

Ví dụ mô tả response:

```java
@GetMapping("/{id}")
@Operation(summary = "Lấy sản phẩm theo mã")
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Tìm thấy sản phẩm"),
    @ApiResponse(responseCode = "404", description = "Không tìm thấy sản phẩm")
})
ProductResponse getById(@PathVariable Long id) {
    return productService.getById(id);
}
```

Springdoc có thể suy luận response thành công từ kiểu trả về `ProductResponse`. Annotation bổ sung ý nghĩa cho mã trạng thái và mô tả. Nếu cần khai báo chính xác media type hoặc schema của từng response, hãy dùng `@Content` và `@Schema` để thể hiện đầy đủ hợp đồng.

## 4. DTO, Jackson và `@Schema` có vai trò khác nhau

Đây là một nguồn xung đột thường gặp. Jackson và các cấu hình serialize quyết định JSON mà ứng dụng thực sự gửi hoặc nhận. `@Schema` mô tả schema trong tài liệu OpenAPI. Springdoc có thể đọc metadata từ cả hai nguồn, nhưng annotation tài liệu không thay đổi kết quả serialize của Jackson.

Ví dụ:

```java
public record ProductResponse(
    @JsonProperty("product_name")
    @Schema(description = "Tên sản phẩm", example = "Keyboard")
    String name,

    @JsonIgnore
    @Schema(description = "Ghi chú nội bộ")
    String internalNote
) {
}
```

`@JsonProperty("product_name")` tham gia quyết định tên thuộc tính trong JSON. `@JsonIgnore` yêu cầu Jackson bỏ qua thuộc tính theo cấu hình áp dụng. `@Schema` bổ sung mô tả cho tài liệu; nó không làm cho `internalNote` xuất hiện trở lại trong JSON nếu Jackson đã loại bỏ trường đó. Tương tự, `@Parameter(required = true)` hoặc `@Schema(requiredMode = ...)` mô tả yêu cầu trong hợp đồng; validation và binding của Spring mới quyết định request thực tế có bị từ chối hay không.

Nếu tài liệu và payload thật khác nhau, hãy kiểm tra lần lượt:

1. DTO hoặc record thực tế được controller sử dụng.
2. Annotation Jackson như `@JsonProperty`, `@JsonIgnore`, `@JsonView`, `@JsonUnwrapped` và naming strategy.
3. Cấu hình `ObjectMapper`, module Jackson và serializer/deserializer tùy chỉnh.
4. Annotation `@Schema` hoặc `@ArraySchema` có thể bổ sung hoặc điều chỉnh metadata.
5. JSON thực tế trong response/request và schema tương ứng trong `/v3/api-docs`.

Không dùng `@Schema` để che giấu một khác biệt của JSON runtime. Nếu muốn thay đổi payload, sửa DTO hoặc cấu hình serialization. Nếu payload đúng nhưng mô tả chưa rõ, sửa annotation hoặc customizer tài liệu.

## 5. Bean `OpenAPI` và `@OpenAPIDefinition`

Thông tin cấp tài liệu có thể được khai báo bằng `@OpenAPIDefinition` hoặc bean `OpenAPI`. Ví dụ:

```java
@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Product API",
        version = "1.0.0",
        description = "API quản lý sản phẩm"
    )
)
class OpenApiDefinitionConfiguration {
}
```

Hoặc:

```java
@Configuration
class OpenApiBeanConfiguration {

    @Bean
    OpenAPI productApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Product API")
                .version("1.0.0")
                .description("API quản lý sản phẩm"));
    }
}
```

Hai cơ chế này đều cung cấp metadata cấp tài liệu. Nếu khai báo cùng một trường ở nhiều nguồn, đừng dựa vào một giả định chung rằng annotation hay bean luôn thắng. Cách Springdoc kết hợp metadata phụ thuộc cơ chế xử lý và phiên bản thư viện. Cách dễ bảo trì nhất là chọn một nguồn làm nơi sở hữu chính cho `Info`, `Servers`, `Security` hoặc metadata dùng chung, sau đó dùng customizer cho những thay đổi có điều kiện.

Nếu dự án cần giá trị title hoặc version khác nhau theo group, hãy cấu hình rõ theo group bằng customizer thích hợp. Không nên dựa vào việc khai báo nhiều bean `OpenAPI` với kỳ vọng Springdoc tự chọn đúng bean theo tên group.

## 6. Spring Boot property precedence áp dụng cho `springdoc.*`

Khi cùng một thuộc tính Springdoc được khai báo ở nhiều nguồn cấu hình, việc chọn giá trị hiệu lực tuân theo cơ chế property source của Spring Boot. Ví dụ, `springdoc.api-docs.path` có thể xuất hiện trong file cấu hình chung, file profile, biến môi trường, system property hoặc command-line argument.

Ở các ứng dụng Spring Boot thông thường, command-line arguments có độ ưu tiên cao hơn system properties, environment variables và cấu hình trong file. Cấu hình profile-specific có thể ghi đè giá trị tương ứng trong file cấu hình chung. Thứ tự chi tiết có thể có thêm nguồn như test properties, `@DynamicPropertySource` hoặc cấu hình do framework bổ sung; hãy tham khảo đúng phiên bản Spring Boot khi điều tra trường hợp đặc biệt.

Ví dụ file chung:

```yaml
springdoc:
  api-docs:
    path: /v3/api-docs
```

File `application-prod.yml`:

```yaml
springdoc:
  api-docs:
    path: /internal/openapi
```

Nếu profile `prod` đang hoạt động, giá trị profile-specific được chọn cho thuộc tính này, trừ khi một property source có độ ưu tiên cao hơn tiếp tục ghi đè. Có thể truyền command-line argument:

```bash
java -jar app.jar --springdoc.api-docs.path=/ops/openapi
```

Khi đó, cần kiểm tra giá trị hiệu lực thay vì chỉ đọc một file YAML. Nếu ứng dụng bật Spring Boot Actuator, endpoint `/actuator/env` hoặc `/actuator/configprops` có thể hỗ trợ chẩn đoán, nhưng chỉ nên expose chúng theo chính sách bảo mật của hệ thống.

Lưu ý: property precedence của Spring Boot chỉ giải quyết xung đột giữa các nguồn cấu hình có cùng key. Nó không có nghĩa thuộc tính `springdoc.*` sẽ tự động ghi đè `@Operation`, `@Schema` hoặc mapping của Spring. Đó là các lớp thông tin khác nhau.

## 7. Thuộc tính Springdoc điều khiển phạm vi và cách tạo tài liệu

Các thuộc tính `springdoc.*` có thể ảnh hưởng đến việc endpoint nào được đưa vào tài liệu, đường dẫn tài liệu và cách Springdoc xử lý response. Một số ví dụ:

```yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  packages-to-scan:
    - com.example.api
  paths-to-match:
    - /api/**
  default-consumes-media-type: application/json
  default-produces-media-type: application/json
  override-with-generic-response: true
```

Ý nghĩa:

| Thuộc tính | Ảnh hưởng |
|---|---|
| `api-docs.enabled` | Bật hoặc tắt endpoint tài liệu |
| `api-docs.path` | Thay đổi đường dẫn endpoint tài liệu |
| `packages-to-scan` | Giới hạn package được xem xét khi sinh tài liệu |
| `paths-to-match` | Lọc endpoint theo path |
| `default-consumes-media-type` | Đặt media type mặc định cho request body khi cần suy luận |
| `default-produces-media-type` | Đặt media type mặc định cho response khi cần suy luận |
| `override-with-generic-response` | Điều khiển việc áp dụng response tổng quát từ `@ControllerAdvice` vào operation theo cơ chế Springdoc |

Những thuộc tính này không có cùng phạm vi. `paths-to-match` lọc operation; `default-produces-media-type` bổ sung thông tin media type khi thiếu; `override-with-generic-response` tác động cách response tổng quát được đưa vào tài liệu. Không nên dùng một thuộc tính để sửa một khác biệt thuộc mapping hoặc payload runtime.

### Response từ `@ControllerAdvice`

Một ứng dụng có thể định nghĩa lỗi dùng chung bằng `@RestControllerAdvice` và `@ExceptionHandler`. Springdoc có thể đưa response tổng quát này vào tài liệu của nhiều operation. Nếu operation cũng khai báo `@ApiResponse` cho cùng mã trạng thái, kết quả cuối cùng cần được kiểm tra trực tiếp trong tài liệu sinh ra vì việc kết hợp response phụ thuộc phiên bản và cấu trúc content.

Ví dụ cấu hình điều khiển việc áp dụng response tổng quát:

```yaml
springdoc:
  override-with-generic-response: false
```

Đặt `false` khi không muốn Springdoc tự áp dụng response tổng quát theo cơ chế đó và nhóm muốn mô tả response ở từng operation. Trước khi thay đổi, hãy kiểm tra tài liệu của phiên bản Springdoc đang dùng và xác minh ảnh hưởng lên tất cả group.

## 8. Customizer có thể sửa mô hình sau khi được tạo

Khi annotation và cấu hình tiêu chuẩn chưa đủ, Springdoc cung cấp các điểm mở rộng để tùy chỉnh tài liệu. Cần phân biệt phạm vi của từng loại:

| Loại customizer | Phạm vi |
|---|---|
| `OperationCustomizer` | Sửa một operation trong quá trình Springdoc xử lý handler method |
| `OpenApiCustomizer` | Sửa mô hình OpenAPI của tài liệu mặc định |
| `GlobalOpenApiCustomizer` | Sửa mô hình áp dụng cho tài liệu mặc định và các group theo cơ chế Springdoc hỗ trợ |

Ví dụ dùng `OperationCustomizer` để bổ sung mô tả dựa trên handler:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.context.annotation.Bean;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface InternalApi {
}

@Bean
OperationCustomizer operationDescriptionCustomizer() {
    return (operation, handlerMethod) -> {
        if (handlerMethod.getMethod().isAnnotationPresent(InternalApi.class)) {
            operation.addTagsItem("Internal");
        }
        return operation;
    };
}
```

Ví dụ dùng `OpenApiCustomizer` để chỉnh metadata chung:

```java
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
OpenApiCustomizer openApiDescriptionCustomizer() {
    return openApi -> {
        if (openApi.getInfo() != null) {
            openApi.getInfo().setDescription("Tài liệu API được chuẩn hóa bởi nhóm nền tảng.");
        }
    };
}
```

Customizer là mã Java thực thi trong quá trình tạo tài liệu. Nếu một customizer đặt `description` sau khi Springdoc đã đọc `@Operation(description = ...)`, giá trị cuối cùng có thể là giá trị do customizer ghi. Nếu nhiều customizer cùng sửa một field, thứ tự thực thi có ý nghĩa. Dùng cơ chế ordering của Spring khi phiên bản tích hợp hỗ trợ, giữ logic thay đổi cùng một field ở một nơi và kiểm tra tài liệu sau khi thay đổi.

Không nên dùng customizer để che giấu lỗi mapping, thay đổi response runtime hoặc đưa dữ liệu nhạy cảm vào tài liệu. Customizer chỉ sửa mô hình OpenAPI, không sửa controller hoặc kết quả serialize của API.

## 9. Swagger UI là lớp trình bày riêng

Các thuộc tính `springdoc.swagger-ui.*` điều khiển giao diện như đường dẫn UI, bộ lọc, cách mở rộng operation, danh sách tài liệu hoặc việc hiển thị thời gian request. Chúng không thay thế các metadata trong OpenAPI document.

Ví dụ:

```yaml
springdoc:
  swagger-ui:
    path: /docs
    filter: true
    doc-expansion: none
    display-request-duration: true
```

Nếu Swagger UI hiển thị một tài liệu cũ, cần kiểm tra URL mà UI tải, cache của trình duyệt hoặc proxy và endpoint OpenAPI thực tế. Việc đổi `doc-expansion` không sửa operation; việc đổi `swagger-ui.path` không đổi `/v3/api-docs`.

## 10. Ma trận xử lý khi nhiều nguồn cùng tác động

| Trường hợp | Nguồn cần kiểm tra trước | Hướng xử lý |
|---|---|---|
| URL hoặc HTTP method trong tài liệu sai | Spring mapping và handler thực tế | Sửa mapping hoặc phạm vi lọc; không cố sửa route bằng `@Operation` |
| Summary/description không như mong đợi | `@Operation`, metadata ứng dụng và customizer | Chọn một nguồn sở hữu nội dung; kiểm tra customizer có ghi đè không |
| Tên field JSON khác schema | Jackson, DTO và `@Schema` | Xác nhận payload thực tế; đồng bộ schema với serialization |
| Response lỗi bị lặp hoặc thay đổi | `@ControllerAdvice`, `@ApiResponse`, `override-with-generic-response` | Kiểm tra JSON của operation và điều chỉnh cách áp dụng response tổng quát |
| Endpoint không xuất hiện | `packages-to-scan`, `paths-to-match`, group và `@Hidden` | Kiểm tra từng điều kiện lọc và tài liệu group đang xem |
| Title/version khác giá trị mong đợi | `@OpenAPIDefinition`, bean `OpenAPI`, customizer | Chọn nguồn metadata chính; kiểm tra giá trị cuối cùng |
| Path API Docs khác cấu hình trong file | Profile, environment variable, system property, command line | Kiểm tra property source hiệu lực của Spring Boot |
| Swagger UI hiển thị sai hoặc không tải được tài liệu | `swagger-ui.url`, group URL, browser/proxy cache | Mở trực tiếp endpoint JSON/YAML và kiểm tra request trong Network |

Ma trận này chỉ ra nơi bắt đầu điều tra. Với một số cấu trúc, nhiều nguồn có thể cùng được merge; cần xác minh giá trị cuối cùng thay vì suy luận chỉ từ một annotation hoặc một file cấu hình.

## 11. Quy trình kiểm tra xung đột một cách có hệ thống

Khi tài liệu không phản ánh điều mong muốn, thực hiện theo thứ tự:

1. **Xác nhận hành vi runtime.** Gọi endpoint thật, ghi nhận URL, method, status code, header và JSON request/response.
2. **Lấy tài liệu trực tiếp.** Gọi `/v3/api-docs` hoặc URL group thay vì chỉ quan sát Swagger UI.
3. **Xác định trường bị sai.** Phân loại đó là path/method, parameter, schema, response, metadata cấp tài liệu hay cách trình bày UI.
4. **Tìm nguồn sở hữu trường đó.** Ví dụ mapping thuộc Spring; tên JSON thuộc Jackson; summary thuộc metadata operation; đường dẫn API Docs thuộc cấu hình Springdoc.
5. **Kiểm tra các nguồn bổ sung.** Tìm annotation, bean `OpenAPI`, `@ControllerAdvice`, customizer và profile cấu hình có thể cùng tác động.
6. **Thay đổi một nguồn tại một thời điểm.** Việc cô lập thay đổi giúp xác định chính xác nguồn gây ra kết quả.
7. **Đọc lại JSON/YAML sinh ra.** Kiểm tra trường cuối cùng, schema reference, response code, media type và URL.
8. **Kiểm tra lại API runtime và Swagger UI.** Bảo đảm tài liệu khớp hành vi thật và giao diện đang tải đúng tài liệu.

Ví dụ dùng `curl` để lấy tài liệu:

```bash
curl -s http://localhost:8080/v3/api-docs
```

Có thể lưu kết quả vào file tạm trong môi trường phát triển để so sánh trước và sau thay đổi. Khi so sánh, tập trung vào operation liên quan thay vì chỉ nhìn kích thước toàn bộ JSON.

## 12. Ví dụ kiểm tra response bị tác động bởi nhiều nguồn

Giả sử controller khai báo:

```java
@GetMapping("/{id}")
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Thành công"),
    @ApiResponse(responseCode = "404", description = "Không tìm thấy sản phẩm")
})
ProductResponse getById(@PathVariable Long id) {
    return productService.getById(id);
}
```

Ứng dụng đồng thời có `@RestControllerAdvice` xử lý `ProductNotFoundException`. Nếu Springdoc tự áp dụng response tổng quát, operation có thể nhận response được suy ra từ advice. Khi tài liệu có hai mô tả cạnh tranh cho status `404`, không nên đoán mô tả nào chắc chắn thắng trong mọi phiên bản.

Hãy kiểm tra operation trong JSON được sinh. Sau đó chọn một quy ước:

- Để response dùng chung đến từ advice và giảm khai báo trùng ở từng controller.
- Hoặc tắt việc áp dụng response tổng quát theo cấu hình Springdoc và mô tả response ở từng operation.
- Hoặc dùng customizer có chủ đích để chuẩn hóa response sau khi Springdoc đã tạo operation.

Trong cả ba trường hợp, response runtime do exception handler và HTTP status thực tế vẫn là điều cần kiểm thử riêng. Mô tả OpenAPI chỉ cho client biết server dự kiến phản hồi như thế nào.

## 13. Nguyên tắc giữ cấu hình dễ bảo trì

- Mỗi trường metadata nên có một nguồn sở hữu chính, nhất là title, version, server và security scheme.
- Để Spring mapping và DTO phản ánh hành vi runtime; dùng Swagger annotations để làm rõ hợp đồng.
- Giữ `@Operation`, `@ApiResponse` và `@Schema` gần controller/DTO mà chúng mô tả.
- Dùng customizer cho quy tắc thực sự dùng chung hoặc phụ thuộc metadata mà annotation khó biểu đạt.
- Không dùng `springdoc.*` property để cố sửa một nội dung thuộc routing hoặc serialization.
- Tách cấu hình theo profile có chủ đích và kiểm tra property source cuối cùng.
- Khi nhiều customizer cùng sửa một trường, xác định thứ tự và viết kiểm tra cho giá trị cuối.
- Kiểm tra trực tiếp tài liệu JSON/YAML trong CI để phát hiện thay đổi ngoài dự kiến.
- Đảm bảo tài liệu OpenAPI và endpoint thực tế nhất quán trước khi phân phối cho client.

## 14. Checklist trước khi kết luận về precedence

- [ ] Đã xác định trường nào đang bị xung đột.
- [ ] Đã xác nhận route, method và payload thực tế của Spring.
- [ ] Đã kiểm tra mapping, DTO, Jackson và validation nếu liên quan.
- [ ] Đã kiểm tra Swagger annotations trên controller và DTO.
- [ ] Đã kiểm tra `@OpenAPIDefinition` và bean `OpenAPI` có khai báo trùng metadata không.
- [ ] Đã kiểm tra customizer và thứ tự sửa mô hình OpenAPI.
- [ ] Đã kiểm tra các thuộc tính `springdoc.*` cùng profile và property source hiệu lực.
- [ ] Đã phân biệt cấu hình API Docs với cấu hình Swagger UI.
- [ ] Đã mở trực tiếp tài liệu JSON/YAML để xác nhận giá trị cuối.
- [ ] Đã kiểm thử API runtime sau khi chỉnh sửa tài liệu.

Khi nhiều nguồn cùng tác động, cách xác định precedence đáng tin cậy là hiểu đúng phạm vi của từng lớp và kiểm tra kết quả cuối mà Springdoc tạo ra. Spring quyết định hành vi HTTP, Jackson quyết định biểu diễn dữ liệu, Swagger annotations và metadata mô tả hợp đồng, cấu hình Springdoc điều khiển quá trình tạo tài liệu, còn customizer có thể chuẩn hóa mô hình trước khi trả về. Giữ mỗi trường có một nguồn sở hữu rõ ràng sẽ giúp tài liệu nhất quán và tránh những xung đột khó chẩn đoán.

# Quy trình thu hẹp lỗi bằng đặc tả JSON, mapping và log liên quan

Khi Swagger UI thiếu endpoint, OpenAPI JSON có schema sai hoặc một operation không hoạt động như tài liệu mô tả, cần tìm đúng lớp gây ra sai lệch trước khi sửa code. springdoc-openapi lấy thông tin từ Spring application context, handler mapping, annotation, kiểu request/response và cấu hình serialization. Vì vậy, lỗi có thể xuất phát từ route chưa được Spring đăng ký, filter của springdoc, metadata trên controller, Jackson, validation, customizer hoặc dependency không tương thích.

Quy trình hiệu quả bắt đầu bằng việc ghi lại triệu chứng và request thực tế, sau đó so sánh ba nguồn bằng chứng: OpenAPI JSON được sinh, handler mapping mà Spring đang chạy và log tại thời điểm tái hiện. Nếu ba nguồn không khớp, mỗi khác biệt giúp thu hẹp vùng cần kiểm tra. Không nên thêm annotation hoặc mở rộng component scan theo phỏng đoán khi chưa biết operation biến mất ở bước nào.

Bài này hướng dẫn chẩn đoán theo từng lớp: xác nhận endpoint tài liệu, đọc OpenAPI JSON, kiểm tra Spring mappings, kiểm tra package/path filters, phân tích parameter và schema, đối chiếu Jackson/validation, đọc log, kiểm tra dependency và tái hiện bằng test. Các ví dụ giả định Spring Boot với springdoc-openapi; tên property và API có thể khác giữa major version, nên đối chiếu tài liệu đúng phiên bản đang dùng.

## 1. Xác định chính xác triệu chứng trước khi sửa

Một báo cáo như “Swagger bị lỗi” chưa đủ để tìm nguyên nhân. Hãy phân loại biểu hiện quan sát được:

| Triệu chứng | Câu hỏi đầu tiên |
|---|---|
| Không mở được Swagger UI | Trang UI trả status nào? Có lỗi tải JavaScript hoặc document không? |
| /v3/api-docs trả 404 | Endpoint docs có đổi path, context path hoặc bị security chặn không? |
| /v3/api-docs trả 500 | Exception đầu tiên trong server log là gì? |
| Thiếu một operation | Spring có đăng ký handler đó không? Filter hoặc annotation có loại nó không? |
| Operation có nhưng thiếu parameter | Mapping method và annotation parameter có được đọc đúng không? |
| Schema thiếu field | Jackson có serialize field đó không? Schema annotation hoặc mixin có ảnh hưởng không? |
| Required/format sai | Bean Validation annotation và OpenAPI version có khớp không? |
| Tài liệu đúng nhưng API chạy sai | Runtime request/response có khác contract không? |
| Chỉ một group bị lỗi | Customizer hoặc filter của group đó có khác document mặc định không? |

Thu thập tối thiểu:
- HTTP method và URL đầy đủ đã gọi.
- Status code, response headers và phần body lỗi đã loại dữ liệu nhạy cảm.
- Tên document: default hay group cụ thể.
- Spring profile, port, context path và môi trường đang chạy.
- Thời điểm tái hiện và correlation/request ID nếu có.
- Phiên bản Java, Spring Boot và springdoc đang được dùng.
- Một operation cụ thể làm ví dụ, gồm path, method và DTO liên quan.

Ghi lại một lần tái hiện có thể lặp lại. Nếu lỗi chỉ xuất hiện ở production hoặc sau proxy, giữ lại URL public và URL backend tương ứng để kiểm tra context path, forwarded headers và routing.

## 2. Hiểu luồng tạo OpenAPI để khoanh vùng

springdoc không tự phát hiện mọi class trong source code. Nó làm việc với các handler mà Spring đã đăng ký, rồi phân tích metadata và model liên quan để tạo document.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Spring Boot starts] --> B[Component scanning and bean creation]
    B --> C[Spring MVC or WebFlux handler mappings]
    C --> D[springdoc selects eligible handlers]
    D --> E[Operation and parameter analysis]
    E --> F[Request and response schema resolution]
    F --> G[OpenAPI customizers and extensions]
    G --> H[OpenAPI JSON or YAML]
    H --> I[Swagger UI loads the document]
~~~

Có thể chia nguyên nhân thành các lớp:

1. **Application context:** controller có được tạo thành bean không?
2. **Handler mapping:** Spring có đăng ký route và HTTP method không?
3. **springdoc selection:** package/path filter hoặc annotation có loại operation không?
4. **Metadata:** operation, parameter, response và security có được mô tả đầy đủ không?
5. **Schema resolution:** Jackson, validation và kiểu dữ liệu tạo schema thế nào?
6. **Customization:** customizer có thay đổi hoặc làm hỏng document không?
7. **Delivery:** endpoint JSON/YAML và Swagger UI có được phục vụ qua đúng URL không?

Khi biết operation biến mất ở lớp nào, phạm vi điều tra sẽ nhỏ hơn nhiều. Ví dụ, nếu handler mapping đã không có route thì chỉnh @Operation sẽ không thể làm route xuất hiện.

## 3. Xác nhận đúng endpoint tài liệu và đúng môi trường

Mặc định springdoc thường cung cấp OpenAPI JSON tại `/v3/api-docs` và YAML tại `/v3/api-docs.yaml`. Swagger UI thường có thể truy cập qua `/swagger-ui.html` hoặc đường dẫn UI tương ứng với cấu hình/version đang dùng.

Gọi trực tiếp endpoint JSON trước khi điều tra UI:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Lưu response để phân tích:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Nếu ứng dụng có context path, ví dụ `/catalog`, URL có thể là:

~~~text
http://localhost:8080/catalog/v3/api-docs
~~~

Nếu property `springdoc.api-docs.path` đã được đổi, hãy dùng path thực tế đó. Không kết luận springdoc không hoạt động chỉ vì gọi endpoint mặc định trong khi dự án đã tùy chỉnh đường dẫn.

Kiểm tra các điểm sau:
- Đang gọi đúng host, port và application instance.
- Profile hiện tại có bật dependency/configuration tạo docs không.
- Context path hoặc servlet path có được thêm vào URL không.
- Reverse proxy có rewrite prefix không.
- Security filter có yêu cầu authentication cho endpoint docs không.
- Có nhiều service cùng chạy và đang gọi nhầm instance không.

Nếu JSON endpoint hoạt động nhưng UI không tải được, chuyển sang kiểm tra cấu hình Swagger UI và proxy. Nếu cả JSON lẫn YAML đều lỗi, ưu tiên kiểm tra server log và quá trình tạo document.

## 4. Đọc OpenAPI JSON bằng jq

OpenAPI JSON là bằng chứng trực tiếp về nội dung springdoc đã sinh. Trước tiên, xác nhận document có cấu trúc cơ bản:

~~~bash
jq '{openapi, info, serverCount: (.servers // [] | length), pathCount: (.paths // {} | length)}' openapi.json
~~~

Liệt kê các path:

~~~bash
jq -r '.paths | keys[]' openapi.json
~~~

Liệt kê path và HTTP method:

~~~bash
jq -r '
  .paths
  | to_entries[]
  | .key as $path
  | .value
  | to_entries[]
  | select(
      .key == "get" or .key == "post" or .key == "put" or
      .key == "patch" or .key == "delete" or .key == "options" or
      .key == "head" or .key == "trace"
    )
  | "\(.key | ascii_upcase) \($path)"
' openapi.json
~~~

Xem một operation cụ thể:

~~~bash
jq '.paths["/api/orders/{id}"].get' openapi.json
~~~

Xem schema component:

~~~bash
jq '.components.schemas.OrderResponse' openapi.json
~~~

Xem security scheme:

~~~bash
jq '.components.securitySchemes' openapi.json
~~~

Nếu jq báo parse error, response tải về có thể là HTML error page, trang đăng nhập hoặc nội dung không phải JSON. Kiểm tra status/header và vài dòng đầu của file trước khi kết luận document hỏng.

Không dùng riêng số path để xác nhận tài liệu đầy đủ. Một path có thể có nhiều operation, và một operation có thể tham chiếu nhiều schema. Cần kiểm tra path, method, parameters, requestBody, responses và components của endpoint đang điều tra.

## 5. So sánh OpenAPI JSON với Spring handler mapping

Đây là bước phân biệt lỗi ở Spring với lỗi ở springdoc.

Nếu Spring Boot Actuator đã được thêm và endpoint `mappings` được expose trong môi trường chẩn đoán, có thể kiểm tra:

~~~bash
curl -fsS http://localhost:8080/actuator/mappings -o mappings.json
~~~

Tìm path hoặc tên controller trong kết quả:

~~~bash
jq '.. | objects | select(tostring | contains("/api/orders"))' mappings.json
~~~

Cấu trúc output của Actuator có thể thay đổi theo phiên bản Spring Boot. Nếu lệnh jq không khớp, mở file JSON và tìm chuỗi path hoặc tên handler trực tiếp.

Đọc kết quả theo bảng:

| Actuator mappings | OpenAPI JSON | Hướng điều tra |
|---|---|---|
| Không có route | Không có operation | Spring chưa đăng ký handler; kiểm tra bean, profile, condition và mapping |
| Có route | Không có operation | Kiểm tra springdoc filters, @Hidden, group và customizer |
| Có route | Có operation nhưng metadata sai | Kiểm tra annotation, parameter và schema resolution |
| Có route và operation | Runtime trả lỗi | Kiểm tra security, validation, service và business logic |
| Không có Actuator | Không có bằng chứng mapping | Dùng startup log, integration test hoặc debugger để xác nhận handler |

Actuator mappings là dữ liệu runtime hữu ích, nhưng endpoint này có thể tiết lộ cấu trúc nội bộ của ứng dụng. Chỉ expose trong môi trường local/test hoặc bảo vệ bằng security policy chặt chẽ. Không mở rộng public actuator access để tiện chẩn đoán.

## 6. Nếu route không có trong Spring mappings

Khi route không xuất hiện trong /actuator/mappings, hãy kiểm tra từ application context.

### 6.1. Controller có được tạo thành bean không?

Kiểm tra:
- Class có @RestController hoặc @Controller phù hợp không?
- Package của controller có nằm trong vùng component scan không?
- Class có bị loại bởi profile, conditional property hoặc cấu hình test không?
- Có lỗi khởi tạo dependency khiến bean không được tạo không?
- Controller có bị giới hạn bằng @Profile hoặc @ConditionalOnProperty không?

Ví dụ controller chỉ tồn tại trong profile dev:

~~~java
@Profile("dev")
@RestController
@RequestMapping("/api/orders")
class OrderController {
    // ...
}
~~~

Khi chạy profile production, controller sẽ không được đăng ký. Đây là khác biệt application configuration, không phải lỗi tạo OpenAPI.

### 6.2. Kiểm tra request mapping

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse getById(@PathVariable String id) {
        return service.findById(id);
    }
}
~~~

Path cuối cùng là `/api/orders/{id}`. Khi kiểm tra mapping, tính cả:
- Class-level @RequestMapping.
- Method-level @GetMapping, @PostMapping hoặc @RequestMapping.
- HTTP method.
- consumes và produces.
- Servlet context path hoặc WebFlux base path.
- Các điều kiện mapping khác như params/headers.

Một controller có thể được đăng ký nhưng method mapping không khớp request mà bạn đang gọi. Đừng chỉ tìm tên class trong log.

### 6.3. Kiểm tra functional routes

Với WebFlux functional endpoint hoặc router function, route không được khai báo theo kiểu controller annotation thông thường. Hãy xác nhận springdoc version và cơ chế hỗ trợ functional route của stack đang dùng, đồng thời kiểm tra route function thực sự được tạo trong application context.

## 7. Nếu Spring có route nhưng OpenAPI không có operation

Khi route đã có trong Spring mappings nhưng JSON thiếu operation, tập trung vào bộ lọc và metadata loại trừ.

### 7.1. Package và path filters

Kiểm tra các property:
- `springdoc.packages-to-scan`
- `springdoc.packages-to-exclude`
- `springdoc.paths-to-match`
- `springdoc.paths-to-exclude`

Ví dụ:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.catalog.api
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
~~~

Nếu controller nằm ngoài package include hoặc path không khớp pattern, springdoc có thể bỏ qua operation dù endpoint vẫn chạy.

Đối chiếu package khai báo thực tế của controller với package filter. Đối chiếu path sau khi kết hợp class-level và method-level mapping với pattern. Sau mỗi thay đổi, tải lại OpenAPI JSON và tìm operation cụ thể.

### 7.2. Annotation ẩn

Kiểm tra:
- @Hidden trên controller hoặc method.
- @Operation(hidden = true) trên operation.
- Annotation/meta-annotation được dùng chung trong project.
- Customizer xóa operation hoặc path khỏi document.

Ẩn operation chỉ ảnh hưởng tài liệu. Endpoint vẫn có thể hoạt động và cần được bảo vệ bằng Spring Security hoặc policy runtime.

### 7.3. GroupedOpenApi

Một operation có thể xuất hiện trong document mặc định nhưng không xuất hiện trong group đang xem, hoặc ngược lại, tùy filter của từng group.

Ví dụ:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .packagesToScan("com.example.catalog.partner")
        .pathsToMatch("/partner/**")
        .build();
}
~~~

Tải đúng endpoint group, thường có dạng `/v3/api-docs/partner`, hoặc path đã được tùy chỉnh. Đừng so sánh document mặc định với group partner rồi kết luận endpoint bị mất.

### 7.4. Customizer

Tìm các bean như:
- OpenApiCustomizer.
- GlobalOpenApiCustomizer.
- Bean OpenAPI tùy chỉnh.
- Logic xóa path, operation, tag hoặc schema.

Tạm thời cô lập customizer trong một nhánh/test profile để xác định có phải customization gây ra khác biệt hay không. Không xóa customizer production chỉ để “thử” nếu chưa hiểu chức năng của nó.

## 8. Nếu operation có nhưng parameter bị thiếu hoặc sai vị trí

Đối chiếu signature của controller với OpenAPI operation:

| Spring annotation | Vị trí HTTP thường tương ứng |
|---|---|
| @PathVariable | path |
| @RequestParam | query |
| @RequestHeader | header |
| @CookieValue | cookie |
| @RequestBody | requestBody |
| @ModelAttribute | Các field bind từ request parameter theo cách Spring MVC xử lý |

Ví dụ:

~~~java
@GetMapping("/api/orders")
List<OrderResponse> search(
    @RequestParam(required = false) String status,
    @RequestHeader(name = "X-Tenant-Id") String tenantId
) {
    return service.search(status, tenantId);
}
~~~

OpenAPI nên mô tả status là query parameter và X-Tenant-Id là header parameter. Nếu vị trí hoặc required sai, kiểm tra:
- Annotation có được đặt đúng tham số không?
- Có annotation parameter từ thư viện khác gây nhầm lẫn không?
- Có tên parameter được compile với metadata phù hợp không?
- Có @Parameter hoặc @Parameters override metadata không?
- Method có overload hoặc mapping phức tạp không?

Có thể khai báo tường minh:

~~~java
@Parameter(
    name = "status",
    in = ParameterIn.QUERY,
    required = false,
    description = "Lọc theo trạng thái"
)
@RequestParam(required = false) String status
~~~

Sau khi sửa, kiểm tra parameters trong JSON. Không dùng annotation để che giấu một signature runtime sai; parameter phải phản ánh request mà Spring thực sự bind.

## 9. Nếu requestBody hoặc response schema không đúng

Khi operation tồn tại nhưng model sai, xác định kiểu dữ liệu được dùng ở method signature trước:

~~~java
@PostMapping("/api/orders")
ResponseEntity<OrderResponse> create(
    @Valid @RequestBody CreateOrderRequest request
) {
    // ...
}
~~~

Kiểm tra các yếu tố:
- Kiểu tham số request body.
- Kiểu trả về thực tế.
- Generic wrapper như ResponseEntity<T>, Page<T> hoặc envelope riêng.
- DTO, record, inheritance và generic type.
- Jackson annotations và mixins.
- Schema annotations.
- Serialization module được đăng ký trong application context.

Ví dụ Jackson:

~~~java
public record OrderResponse(
    String id,
    @JsonProperty("order_status") String status,
    @JsonIgnore String internalNote
) {
}
~~~

OpenAPI schema thường phản ánh tên JSON property và quy tắc serialization mà springdoc/Jackson nhận diện. Vì vậy, status có thể xuất hiện dưới tên order_status, còn internalNote có thể bị bỏ khỏi schema serialization.

Nếu field bị thiếu:
1. Xác nhận field có thực sự xuất hiện trong JSON response runtime.
2. Kiểm tra @JsonIgnore, @JsonProperty, visibility và naming strategy.
3. Kiểm tra getter/record component và Jackson mixin.
4. Kiểm tra @Schema(hidden = true) hoặc schema customizer.
5. Xem schema component trong JSON và tìm nơi $ref được dùng.

Nếu field có trong runtime JSON nhưng không có trong schema, vấn đề có thể nằm ở introspection/annotation. Nếu field cũng không có trong runtime JSON, kiểm tra DTO và serializer trước khi chỉnh springdoc.

## 10. Phân tích required, nullable và validation

Các annotation Bean Validation có thể cung cấp constraint cho schema, nhưng kết quả phụ thuộc phiên bản, vị trí annotation và kiểu dữ liệu.

Ví dụ:

~~~java
public record CreateOrderRequest(
    @NotBlank
    String customerId,

    @NotEmpty
    List<@Valid OrderLineRequest> items
) {
}
~~~

Kiểm tra:
- Dependency validation có mặt không?
- Import annotation thuộc jakarta.validation hay javax.validation có khớp Spring Boot line không?
- Annotation nằm trên field, getter, record component hay type-use?
- Controller có @Valid hoặc @Validated tại vị trí cần thiết không?
- Constraint có được runtime validator thực thi không?
- Schema được tạo có required, minLength, minItems hoặc format phù hợp không?

Spring Boot 3 sử dụng Jakarta namespace cho nhiều API. Nếu nâng từ Boot 2 lên Boot 3 mà source vẫn dùng annotation javax.validation, dependency có thể không hoạt động như mong đợi hoặc không tương thích với stack mới. Kiểm tra import và dependency thực tế.

Phân biệt:
- required trong OpenAPI mô tả field phải có mặt trong payload.
- nullable mô tả field có thể nhận null theo dialect.
- @NotNull/@NotBlank/@NotEmpty là constraint validation runtime.
- Default value trong schema không tự động đảm bảo server gán giá trị đó.

Nếu schema và runtime validation không thống nhất, sửa cả contract lẫn validation implementation rồi thêm test để ngăn tái diễn.

## 11. Kiểm tra response code và error schema

Một operation có thể có response mặc định được springdoc suy ra từ return type, nhưng các status code thực tế có thể do exception handler hoặc response logic tạo ra.

Kiểm tra:
- @ApiResponse và @ApiResponses.
- @ControllerAdvice và @ExceptionHandler.
- ResponseEntity với status động.
- Error response thực tế.
- Media type và response header.
- Response code mặc định và response code đặc thù.

Ví dụ mô tả response:

~~~java
@Operation(summary = "Lấy thông tin đơn hàng")
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Tìm thấy đơn hàng"),
    @ApiResponse(responseCode = "404", description = "Không tìm thấy"),
    @ApiResponse(responseCode = "500", description = "Lỗi hệ thống")
})
@GetMapping("/api/orders/{id}")
OrderResponse getById(@PathVariable String id) {
    return service.findById(id);
}
~~~

Annotation chỉ mô tả tài liệu. Nó không tự làm endpoint trả 404 hoặc 500 theo nội dung đó. Dùng integration test để xác nhận status và body runtime khớp OpenAPI.

Nếu mọi operation đều bị thêm cùng một error response, kiểm tra global response configuration hoặc customizer trước khi sửa từng controller.

## 12. Đọc log có mục tiêu

Log cần trả lời câu hỏi cụ thể. Bật DEBUG cho toàn bộ ứng dụng thường tạo nhiều dữ liệu và che mất exception quan trọng.

Bắt đầu bằng log startup và exception đầu tiên:
- Controller bean nào được tạo?
- Có lỗi classpath hoặc NoClassDefFoundError không?
- Có mapping conflict hoặc ambiguous mapping không?
- Có exception khi resolve schema hoặc serialize OpenAPI không?
- Customizer nào chạy trước khi lỗi xảy ra?
- Request đến /v3/api-docs có đi qua security filter không?

Có thể bật log package springdoc trong profile chẩn đoán:

~~~yaml
logging:
  level:
    org.springdoc: DEBUG
~~~

Nếu cần kiểm tra Spring MVC mappings, có thể bật log package liên quan trong thời gian ngắn:

~~~yaml
logging:
  level:
    org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping: DEBUG
~~~

Với WebFlux, package logger và chi tiết mapping khác MVC; dùng logger phù hợp với stack thực tế.

Sau khi thu thập log, tắt mức DEBUG nếu không còn cần. Không để cấu hình verbose logging vô thời hạn trong production nếu nó tạo nhiều log hoặc ghi metadata nhạy cảm.

## 13. Dùng Actuator để xem conditions và logger

Nếu ứng dụng đã có Spring Boot Actuator, các endpoint sau có thể hỗ trợ điều tra:
- /actuator/mappings: handler mapping.
- /actuator/conditions: điều kiện auto-configuration và bean condition.
- /actuator/beans: danh sách bean.
- /actuator/loggers: trạng thái logger và điều chỉnh level trong phạm vi được phép.

Ví dụ kiểm tra conditions:

~~~bash
curl -fsS http://localhost:8080/actuator/conditions -o conditions.json
~~~

Tìm cấu hình liên quan springdoc hoặc web auto-configuration trong output. Cấu trúc condition report có thể lớn; lọc theo từ khóa và kiểm tra cả positive/negative matches.

Nếu actuator endpoint chưa được expose, không cần mở nó trên production chỉ để chẩn đoán. Có thể dùng profile local/test, log startup hoặc test context để thu thập bằng chứng.

Không expose env, configprops, beans, mappings hoặc loggers công khai nếu chưa có kiểm soát truy cập. Những endpoint này có thể tiết lộ cấu hình, bean nội bộ, route hoặc cho phép thay đổi logger level.

## 14. Kiểm tra dependency và lỗi tương thích

Lỗi tạo OpenAPI đôi khi đến từ dependency tree chứ không phải controller. Đặc biệt cần kiểm tra khi:
- Vừa nâng Spring Boot hoặc springdoc.
- Có nhiều swagger-core/swagger-annotations version.
- Jackson được override thủ công.
- Dự án giữ cả starter mới và artifact springdoc cũ.
- MVC và WebFlux starter cùng được kéo vào ngoài chủ đích.
- Có lỗi NoSuchMethodError, ClassNotFoundException hoặc NoClassDefFoundError.

Với Maven:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springdoc,io.swagger.core.v3,com.fasterxml.jackson.core
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Kiểm tra:
- Spring Boot BOM đang quản lý version nào.
- Starter springdoc đúng MVC hay WebFlux.
- Không có artifact cũ trùng chức năng.
- Dependency transitive có bị exclude hoặc override không.
- Compile classpath và runtime classpath có khác biệt bất thường không.

Không thêm một version swagger-core/Jackson tùy ý để dập lỗi compile. Hãy xác định version compatibility của springdoc và Spring Boot trước, rồi chỉnh dependency management ở một nơi có chủ đích.

## 15. Kiểm tra Swagger UI khi JSON đã đúng

Nếu /v3/api-docs trả JSON hợp lệ và chứa operation mong đợi nhưng UI trắng hoặc báo lỗi, hãy điều tra delivery layer:

- Swagger UI URL có đúng sau context path không?
- UI có tải được JavaScript/CSS không?
- Network request tải OpenAPI document trả status nào?
- UI có trỏ tới URL document cũ trong springdoc.swagger-ui.url hoặc config URL không?
- Proxy có rewrite path hoặc scheme không?
- Có HTTPS termination nhưng server URL được sinh thành HTTP không?
- CSP hoặc security policy có chặn tài nguyên UI không?
- CORS có ảnh hưởng khi UI và API docs ở origin khác nhau không?

Mở Developer Tools của browser và kiểm tra Network:
1. Request trang Swagger UI.
2. Tài nguyên JS/CSS.
3. Request tới OpenAPI JSON.
4. Response status và content type.
5. Console error đầu tiên.

Nếu UI dùng document URL cấu hình riêng, kiểm tra nó có trỏ tới đúng group và context path. Đừng sửa controller nếu OpenAPI JSON đã đúng.

## 16. Kiểm tra proxy, forwarded headers và server URL

Khi chạy sau reverse proxy hoặc ingress, server URL trong document có thể khác public URL. Hãy so sánh:
- Request URL public mà browser/client truy cập.
- URL backend mà proxy chuyển tới.
- Host, X-Forwarded-Host, X-Forwarded-Proto và forwarded prefix.
- Context path của ứng dụng.
- Property springdoc liên quan server URL hoặc proxy.

Nếu server URL sai, kiểm tra cấu hình forwarded headers của Spring Boot và proxy. Chỉ tin forwarded header từ proxy đáng tin cậy; không cho client tùy ý đặt header để thay đổi host URL được sinh.

Để xác định đây là lỗi proxy hay ứng dụng, gọi OpenAPI JSON trực tiếp tới backend trong môi trường an toàn rồi so sánh với document qua public ingress. Nếu backend đúng và ingress sai, điều tra rewrite/forwarded headers ở tầng proxy.

## 17. Khi document trả 500: đọc exception gốc

Lỗi 500 ở /v3/api-docs thường cho thấy quá trình tạo document gặp exception. Tìm stack trace cùng timestamp/request ID và bắt đầu từ exception đầu tiên, không chỉ dòng cuối cùng.

Một số dấu hiệu:

| Dấu hiệu trong log | Vùng cần kiểm tra |
|---|---|
| NoSuchMethodError | Version dependency không tương thích |
| ClassNotFoundException | Thiếu artifact hoặc classpath sai |
| NullPointerException trong customizer | Code tùy biến giả định object/path luôn tồn tại |
| Jackson mapping/serialization exception | Serializer, mixin, module hoặc kiểu dữ liệu |
| Schema resolution exception | Generic, recursive model hoặc annotation |
| Ambiguous mapping | Spring đăng ký nhiều handler không phân biệt được |
| Security 401/403 | Docs endpoint bị security policy chặn |
| 404 | Sai path, context path hoặc docs endpoint chưa được đăng ký |

Nếu lỗi xuất hiện ngay khi gọi document và stack trace trỏ tới customizer, thử cô lập customizer trong integration test. Thêm null guard có chủ đích, kiểm tra path/method có tồn tại và xác nhận extension được gắn đúng operation.

Nếu exception liên quan schema, xác định DTO cụ thể đang được phân tích. Tạm thay response type bằng DTO đơn giản trong test để xem lỗi có biến mất không; sau đó thêm lại field/generic từng bước để tìm model gây lỗi. Không thay DTO production chỉ để né exception mà chưa hiểu nguyên nhân.

## 18. Kiểm tra cache và khác biệt giữa lần đầu với các lần gọi sau

Nếu OpenAPI JSON chỉ thay đổi sau khi restart, hoặc customizer thay đổi dữ liệu nhưng response vẫn cũ, kiểm tra cache và cách khởi tạo document.

springdoc có cache OpenAPI document trong các cấu hình thông thường. Property `springdoc.cache.disabled` có thể được dùng để tắt cache ở những version hỗ trợ. Chỉ dùng như bước chẩn đoán hoặc khi thực sự cần document thay đổi theo request; tắt cache có thể làm tăng chi phí tạo document lặp lại.

So sánh:
1. Document ngay sau khi ứng dụng khởi động.
2. Document sau khi customizer/configuration đã chạy.
3. Document sau lần request lặp lại.
4. Document của từng group.

Nếu nội dung OpenAPI phụ thuộc user, tenant hoặc header request, cần thiết kế cache và bảo mật riêng. Không giả định cache mặc định phân biệt mọi biến thể. Một document API thường nên ổn định theo build và group; không nên đưa dữ liệu riêng tư của người dùng vào OpenAPI metadata.

## 19. Quy trình thu hẹp lỗi theo thứ tự

Dùng thứ tự dưới đây để không bỏ qua bằng chứng quan trọng:

~~~mermaid
flowchart TD
    A[Record exact symptom and request] --> B[Fetch OpenAPI JSON]
    B --> C{JSON endpoint works?}
    C -- No --> D[Check status, security, path and server exception]
    C -- Yes --> E{Operation exists in JSON?}
    E -- Yes --> F[Inspect parameters, schemas, responses and security]
    E -- No --> G[Check Spring handler mappings]
    G --> H{Handler registered?}
    H -- No --> I[Check bean, profile, condition and mapping]
    H -- Yes --> J[Check springdoc filters, Hidden and groups]
    F --> K[Compare runtime request/response]
    I --> K
    J --> K
    D --> L[Inspect dependencies and customizers]
    K --> M[Create focused regression test]
    L --> M
~~~

Diễn giải:
- JSON endpoint không chạy: kiểm tra URL, security, server log và dependency.
- JSON chạy nhưng thiếu operation: so sánh với Spring handler mapping.
- Handler không tồn tại: điều tra application context và route.
- Handler có nhưng operation mất: kiểm tra filters, hidden annotation, group và customizer.
- Operation có nhưng schema sai: kiểm tra signature, Jackson, validation và annotation.
- JSON đúng nhưng UI lỗi: kiểm tra tài nguyên UI, URL document và proxy.
- Tài liệu đúng nhưng API sai: kiểm tra runtime behavior và contract test.

Chỉ thay một yếu tố mỗi lần tái hiện nếu có thể. Nếu đồng thời sửa package scan, DTO, Jackson và customizer, sẽ khó biết thay đổi nào thực sự giải quyết lỗi.

## 20. Ví dụ thực tế: endpoint có trong ứng dụng nhưng mất khỏi OpenAPI

Giả sử controller:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse getById(@PathVariable String id) {
        return service.findById(id);
    }
}
~~~

Triệu chứng: gọi GET /api/orders/1001 thành công nhưng /v3/api-docs không có path /api/orders/{id}.

Thực hiện theo thứ tự:

1. Tải /actuator/mappings trong môi trường chẩn đoán và tìm /api/orders/{id}.
2. Nếu không có mapping, kiểm tra controller bean, profile, component scan và startup log.
3. Nếu mapping có, kiểm tra package controller có nằm trong springdoc.packages-to-scan không.
4. Kiểm tra springdoc.paths-to-match và springdoc.paths-to-exclude.
5. Tìm @Hidden hoặc @Operation(hidden = true).
6. Xác nhận đang tải đúng default document hoặc group.
7. Kiểm tra customizer có xóa path/operation không.
8. Tải lại JSON và xác nhận path cùng method đã xuất hiện.

Không thêm @Operation vào method trước khi xác nhận Spring đã đăng ký handler. Annotation mô tả operation đã tồn tại; nó không tự đăng ký route.

## 21. Ví dụ thực tế: schema thiếu field sau khi đổi DTO

Giả sử DTO:

~~~java
public record OrderResponse(
    String id,
    @JsonProperty("order_status") String status,
    @JsonIgnore String internalNote
) {
}
~~~

OpenAPI có schema:

~~~yaml
OrderResponse:
  type: object
  properties:
    id:
      type: string
    order_status:
      type: string
~~~

Consumer phản ánh field status và cho rằng springdoc làm mất field. Nhưng JSON serialization thực tế dùng tên order_status, còn internalNote được Jackson bỏ qua.

Cách kiểm tra:
1. Gọi endpoint thật và lưu JSON response.
2. So sánh JSON response với components.schemas.OrderResponse.
3. Xác nhận tên property theo @JsonProperty.
4. Xác nhận field bị ẩn theo @JsonIgnore.
5. Nếu schema không khớp runtime, kiểm tra Jackson module/mixin và customizer.
6. Cập nhật client hoặc contract theo đúng tên JSON đã thống nhất.

Không dùng tên field Java làm chuẩn nếu wire JSON đã được cấu hình khác. Hợp đồng phải mô tả representation thực tế mà consumer nhận.

## 22. Tạo regression test sau khi tìm được nguyên nhân

Khi đã xác định lỗi, thêm test ở đúng lớp:

- @WebMvcTest hoặc MockMvc cho controller mapping và HTTP behavior.
- @SpringBootTest khi cần xác nhận springdoc document được tạo từ application context thật.
- Test trực tiếp JSON OpenAPI để xác nhận path, operationId, parameter, schema và response.
- Test adapter/customizer nếu extension hoặc group là nguyên nhân.
- Contract test để xác nhận request/response thực tế phù hợp tài liệu.

Ví dụ kiểm tra OpenAPI JSON qua MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocumentTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesOrderLookupOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/orders/{id}'].get").exists())
            .andExpect(jsonPath(
                "$.paths['/api/orders/{id}'].get.operationId"
            ).value("getOrderById"));
    }
}
~~~

Ví dụ cần dependency test phù hợp và import static cho get, status và jsonPath. Nếu API docs endpoint được bảo vệ, test cần thiết lập authentication tương ứng. Nếu application đổi docs path, cập nhật URL test theo cấu hình đã công bố.

Không chỉ assert path tồn tại. Với lỗi schema, thêm assertion vào field/required/type quan trọng. Với lỗi security, xác nhận scheme và operation requirement. Với lỗi group, gọi đúng endpoint document group.

## 23. Các lỗi chẩn đoán thường gặp và cách tránh

| Cách làm thiếu căn cứ | Vì sao gây khó khăn | Cách làm tốt hơn |
|---|---|---|
| Thêm @Operation để làm route xuất hiện | Annotation không đăng ký Spring handler | Kiểm tra handler mapping trước |
| Mở rộng component scan toàn module | Có thể thay đổi application context ngoài ý muốn | Kiểm tra package controller và filter springdoc riêng |
| Bỏ @Hidden mà không xác định nguồn | Có thể làm lộ operation nội bộ | Xác minh policy công bố trước khi thay |
| Xóa customizer toàn bộ | Có thể làm mất security/schema metadata khác | Cô lập từng customizer trong test |
| Override Jackson/swagger-core tùy tiện | Tạo xung đột dependency mới | Đọc dependency tree và compatibility matrix |
| Chỉ xem Swagger UI | Không biết JSON document có lỗi hay không | Gọi OpenAPI endpoint trực tiếp |
| Bật DEBUG toàn ứng dụng vô thời hạn | Log quá nhiều và có thể lộ dữ liệu | Bật logger package hẹp trong thời gian ngắn |
| Expose toàn bộ Actuator | Tiết lộ cấu trúc và cấu hình nội bộ | Dùng local/test hoặc security policy chặt |
| Tắt cache ngay khi thấy dữ liệu cũ | Có thể che giấu nguyên nhân thật | So sánh cold/warm document và kiểm tra version |
| Chỉ test document | Không xác nhận runtime API | Kết hợp document test với endpoint contract test |

## 24. Checklist điều tra một lỗi springdoc

- [ ] Ghi lại HTTP method, URL, status, response và thời điểm tái hiện.
- [ ] Xác nhận đúng host, port, profile, context path và document group.
- [ ] Gọi trực tiếp OpenAPI JSON trước khi điều tra Swagger UI.
- [ ] Kiểm tra JSON có hợp lệ và có path/operation cần tìm.
- [ ] Nếu thiếu operation, kiểm tra Spring handler mappings.
- [ ] Nếu handler không có, kiểm tra bean, profile, condition và mapping.
- [ ] Nếu handler có, kiểm tra package/path filters và annotation ẩn.
- [ ] Kiểm tra GroupedOpenApi và customizer.
- [ ] Đối chiếu controller signature với parameter/requestBody/response.
- [ ] So sánh schema với Jackson serialization thực tế.
- [ ] Kiểm tra Jakarta/Javax validation namespace và constraint.
- [ ] Kiểm tra response code, exception handler và error schema.
- [ ] Đọc exception gốc trong server log và correlation ID.
- [ ] Kiểm tra dependency tree nếu có lỗi classpath hoặc version.
- [ ] Nếu JSON đúng nhưng UI lỗi, kiểm tra Network, proxy, CSP và URL document.
- [ ] Bảo vệ Actuator và log khỏi truy cập không được phép.
- [ ] Tạo regression test ở đúng lớp gây lỗi.
- [ ] Tải lại document và gọi endpoint thật để xác nhận đã khắc phục.

## Tài liệu tham khảo

- [springdoc-openapi](https://springdoc.org/): cấu hình endpoint OpenAPI, filter, group, Swagger UI và customizer.
- [Spring Boot Actuator – Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): mappings, conditions, beans, loggers và cách expose endpoint.
- [Spring MVC – Handler Methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods.html): controller, request mapping và method arguments.
- [Spring WebFlux – Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann.html): mapping và binding trong WebFlux.
- [Jackson Annotations](https://github.com/FasterXML/jackson-annotations): property name, ignore và serialization metadata.
- [Jakarta Bean Validation](https://beanvalidation.org/): constraint và validation metadata.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): paths, operations, parameters, request bodies, responses và schemas.

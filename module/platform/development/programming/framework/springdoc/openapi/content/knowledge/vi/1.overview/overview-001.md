# Springdoc OpenAPI là gì và giải quyết vấn đề tài liệu API như thế nào

## 1. Vấn đề: API có thể chạy đúng nhưng tài liệu vẫn sai

Trong một ứng dụng Spring Boot, controller, DTO và cấu hình bảo mật tạo nên hợp đồng mà client phải tuân theo. Hợp đồng này trả lời những câu hỏi cụ thể:

- Có những endpoint nào, dùng HTTP method nào và nhận tham số gì?
- Request body có cấu trúc ra sao? Trường nào bắt buộc, trường nào có giới hạn?
- Response thành công và các lỗi có định dạng như thế nào?
- Endpoint yêu cầu xác thực hay quyền nào?
- API thuộc nhóm chức năng hoặc phiên bản nào?

Nếu nhóm phát triển viết tài liệu thủ công trong wiki hoặc một tệp riêng, tài liệu dễ lệch khỏi mã nguồn. Một endpoint được đổi tên nhưng tài liệu chưa cập nhật, một trường DTO mới xuất hiện mà ví dụ request vẫn cũ, hoặc một response lỗi thay đổi nhưng client không được thông báo. Người tích hợp phải đọc mã nguồn, hỏi lại nhóm backend hoặc thử từng request để hiểu cách API hoạt động.

Tài liệu API vì thế cần được tạo và duy trì gần với nơi định nghĩa API. Với Spring Boot, **springdoc-openapi** giúp thực hiện việc này bằng cách thu thập thông tin từ ứng dụng, tạo đặc tả OpenAPI và cung cấp giao diện Swagger UI để con người khám phá, thử gọi endpoint.

## 2. Springdoc OpenAPI là gì?

**Springdoc OpenAPI** là thư viện tích hợp với hệ sinh thái Spring để tự động tạo tài liệu theo chuẩn **OpenAPI** từ các API được khai báo trong ứng dụng Spring Boot. Thư viện đọc thông tin mapping của Spring MVC hoặc Spring WebFlux, kiểu dữ liệu của tham số và kết quả, cùng các annotation mô tả bổ sung để xây dựng đặc tả API.

Có thể nhìn giải pháp qua ba thành phần:

1. **Ứng dụng Spring Boot** là nguồn thông tin về endpoint, tham số, DTO, validation và cấu hình bảo mật.
2. **OpenAPI document** là bản mô tả API có cấu trúc, thường được xuất dưới dạng JSON hoặc YAML. Máy móc có thể đọc tài liệu này để sinh client, kiểm tra hợp đồng hoặc tích hợp vào quy trình phát triển.
3. **Swagger UI** là giao diện web trình bày OpenAPI document. Người dùng có thể xem endpoint, schema, tham số và gửi request thử nghiệm ngay trên trình duyệt nếu môi trường cho phép.

OpenAPI là đặc tả trung lập với ngôn ngữ và framework. Swagger là tên của một hệ sinh thái công cụ làm việc với đặc tả đó; Swagger UI là một giao diện phổ biến để hiển thị tài liệu. Springdoc đóng vai trò cầu nối giữa ứng dụng Spring và đặc tả OpenAPI.

Springdoc không thay thế controller, DTO hay logic nghiệp vụ. Nó mô tả những gì ứng dụng công bố. Nếu mã nguồn thiếu mô tả về ý nghĩa nghiệp vụ, quy tắc phân quyền hoặc trường hợp lỗi, tài liệu sinh tự động cũng có thể chưa đủ rõ. Khi đó, lập trình viên cần bổ sung annotation hoặc cấu hình mô tả.

## 3. Springdoc giải quyết vấn đề bằng cách nào?

### 3.1. Tự phát hiện endpoint từ Spring

Spring MVC và Spring WebFlux đã có metadata về các route được khai báo bằng những annotation như:

- **@RestController** và **@Controller**;
- **@RequestMapping**, **@GetMapping**, **@PostMapping**, **@PutMapping**, **@DeleteMapping**;
- **@PathVariable**, **@RequestParam**, **@RequestHeader** và **@RequestBody**.

Springdoc sử dụng metadata của ứng dụng để xác định đường dẫn, HTTP method, tham số và kiểu dữ liệu đầu vào/đầu ra. Vì vậy, khi endpoint được thêm hoặc thay đổi trong controller, tài liệu có thể phản ánh thay đổi đó sau khi ứng dụng được khởi động lại hoặc cập nhật.

Ví dụ, từ khai báo:

~~~java
@GetMapping("/{id}")
public ProductResponse findById(@PathVariable Long id) {
    // Tìm sản phẩm và trả về kết quả
    return null; // Thay bằng kết quả từ service trong ứng dụng thực tế
}
~~~

Springdoc có thể nhận diện endpoint GET với đường dẫn chứa biến **id**, đồng thời suy luận kiểu của tham số và kiểu response từ chữ ký phương thức.

### 3.2. Suy luận schema từ kiểu dữ liệu

Các lớp request và response thường được chuyển thành schema trong phần **components.schemas** của OpenAPI document. Springdoc dựa trên kiểu Java, cấu trúc thuộc tính và các annotation có liên quan để mô tả schema.

Ví dụ:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Schema(description = "Tên sản phẩm", example = "Bàn phím cơ")
    String name,

    @Positive
    @Schema(description = "Giá sản phẩm", example = "1290000")
    BigDecimal price
) {}
~~~

Từ kiểu dữ liệu và annotation, tài liệu có thể thể hiện tên trường, kiểu dữ liệu, ví dụ và một số ràng buộc validation. Điều này giúp client hiểu request cần gửi mà không phải mở mã nguồn DTO.

Tuy nhiên, schema được suy luận không tự giải thích đầy đủ ý nghĩa nghiệp vụ. Chẳng hạn, kiểu **String** không cho biết giá trị phải là mã quốc gia, trạng thái đơn hàng hay một chuỗi tùy ý. Hãy dùng mô tả, ví dụ và ràng buộc phù hợp để làm rõ những trường hợp đó.

### 3.3. Bổ sung mô tả có chủ đích bằng annotation

Các annotation trong gói **io.swagger.v3.oas.annotations** cho phép mô tả thông tin mà Spring không thể suy ra từ chữ ký phương thức:

| Annotation | Mục đích |
|---|---|
| **@Tag** | Nhóm controller hoặc endpoint theo chủ đề |
| **@Operation** | Mô tả ý nghĩa, tóm tắt và hành vi của operation |
| **@Parameter** | Mô tả query, path, header hoặc cookie parameter |
| **@ApiResponse** | Khai báo response code và nội dung trả về |
| **@Schema** | Mô tả model, thuộc tính, ví dụ và ràng buộc |
| **@SecurityRequirement** | Gắn yêu cầu bảo mật vào operation hoặc nhóm operation |
| **@Hidden** | Ẩn một thành phần khỏi tài liệu được sinh |

Ví dụ một endpoint có mô tả rõ ràng:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "API quản lý sản phẩm")
public class ProductController {

    @GetMapping("/{id}")
    @Operation(
        summary = "Lấy sản phẩm theo mã",
        description = "Trả về thông tin chi tiết của một sản phẩm."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Tìm thấy sản phẩm",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Không tìm thấy sản phẩm",
            content = @Content
        )
    })
    public ProductResponse findById(
        @Parameter(description = "Mã sản phẩm", example = "42")
        @PathVariable Long id
    ) {
        // Phần xử lý nghiệp vụ được lược bỏ
        return null;
    }
}

@Schema(description = "Thông tin sản phẩm")
public record ProductResponse(
    @Schema(description = "Mã sản phẩm", example = "42")
    Long id,

    @Schema(description = "Tên sản phẩm", example = "Bàn phím cơ")
    String name,

    @Schema(description = "Giá sản phẩm", example = "1290000")
    BigDecimal price
) {}
~~~

Đoạn mã tập trung vào cách mô tả tài liệu; phần triển khai truy vấn dữ liệu được lược bỏ. Trong ứng dụng thật, response **404** cần khớp với cách ứng dụng xử lý ngoại lệ và định dạng lỗi thực tế.

## 4. Tích hợp Springdoc vào ứng dụng Spring Boot

### 4.1. Chọn starter phù hợp

Với ứng dụng Spring MVC sử dụng Swagger UI, dependency Maven thường dùng là:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Trong đó, **springdoc.version** là phiên bản được quản lý trong cấu hình build của dự án. Nếu dùng Gradle:

~~~kotlin
implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion")
~~~

Hãy chọn phiên bản Springdoc tương thích với phiên bản Spring Boot và Java của dự án theo bảng tương thích của Springdoc. Không ghép tùy ý các major version hoặc đưa đồng thời nhiều starter UI cho cùng một ứng dụng.

Một số lựa chọn phổ biến:

- **springdoc-openapi-starter-webmvc-ui**: ứng dụng Spring MVC cần cả OpenAPI document và Swagger UI.
- **springdoc-openapi-starter-webmvc-api**: ứng dụng Spring MVC chỉ cần endpoint cung cấp OpenAPI document.
- **springdoc-openapi-starter-webflux-ui**: ứng dụng Spring WebFlux cần OpenAPI document và Swagger UI.
- **springdoc-openapi-starter-webflux-api**: ứng dụng Spring WebFlux chỉ cần OpenAPI document.

Tên artifact và cách tích hợp có thể khác giữa các thế hệ Springdoc. Khi nâng cấp dự án cũ, cần đối chiếu hướng dẫn migration của phiên bản đang dùng thay vì chỉ thay số phiên bản dependency.

### 4.2. Chạy ứng dụng và kiểm tra endpoint tài liệu

Sau khi thêm starter và khởi động ứng dụng, các đường dẫn mặc định thường dùng là:

| Đường dẫn | Nội dung |
|---|---|
| **/v3/api-docs** | OpenAPI document dạng JSON |
| **/v3/api-docs.yaml** | OpenAPI document dạng YAML |
| **/swagger-ui.html** | Điểm truy cập Swagger UI, thường chuyển hướng đến giao diện |

Nếu ứng dụng có context path, chạy sau reverse proxy hoặc thay đổi cấu hình mặc định, đường dẫn thực tế có thể khác. Hãy kiểm tra cấu hình triển khai và log khởi động khi không truy cập được các URL trên.

Có thể kiểm tra nhanh JSON bằng trình duyệt hoặc lệnh HTTP:

~~~bash
curl http://localhost:8080/v3/api-docs
~~~

Nếu nhận được JSON có các phần như **openapi**, **info**, **paths** và **components**, ứng dụng đã cung cấp được tài liệu OpenAPI. Nếu có Swagger UI, mở **/swagger-ui.html** để xem endpoint được nhóm theo tag và thử gọi API.

### 4.3. Cấu hình đường dẫn và giao diện

Có thể tùy biến một số thiết lập bằng **application.yml**:

~~~yaml
springdoc:
  api-docs:
    path: /api-docs
  swagger-ui:
    path: /docs
    operationsSorter: method
    tagsSorter: alpha
    displayRequestDuration: true
~~~

Với cấu hình này, OpenAPI JSON nằm tại **/api-docs**; Swagger UI được truy cập qua **/docs**. Tên thuộc tính cấu hình cần đúng với phiên bản Springdoc mà ứng dụng đang sử dụng.

Không nên bật tài liệu hoặc Swagger UI một cách vô thức ở mọi môi trường. Ở môi trường production, nhóm phát triển cần quyết định tài liệu có được công khai hay phải bảo vệ bằng xác thực, mạng nội bộ hoặc gateway.

## 5. Tùy biến thông tin chung của tài liệu

Thông tin như tên API, phiên bản hợp đồng và mô tả tổng quan có thể được khai báo bằng một bean **OpenAPI**:

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI shopOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .version("v1")
                .description("API phục vụ quản lý sản phẩm và đơn hàng."));
    }
}
~~~

Thông tin này xuất hiện trong phần **info** của OpenAPI document và được Swagger UI hiển thị. Giá trị **version** ở đây là phiên bản của hợp đồng API được công bố; nó không nhất thiết trùng với phiên bản release của ứng dụng.

Có thể bổ sung thông tin liên hệ, giấy phép, server URL hoặc external documentation khi cần. Với nhiều môi trường, cần bảo đảm server URL phản ánh đúng địa chỉ mà client có thể truy cập. Tránh ghi cố định địa chỉ localhost vào tài liệu phát hành.

## 6. Mô tả bảo mật để client hiểu cách gọi API

Nếu API dùng JWT Bearer token, có thể khai báo security scheme bằng annotation:

~~~java
@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiSecurityConfiguration {
}
~~~

Sau đó gắn yêu cầu bảo mật vào controller hoặc operation:

~~~java
@RestController
@RequestMapping("/api/orders")
@SecurityRequirement(name = "bearerAuth")
@Tag(name = "Orders", description = "API quản lý đơn hàng")
public class OrderController {
    // Các endpoint của đơn hàng
}
~~~

Khi scheme được khai báo và liên kết đúng, OpenAPI document thể hiện cơ chế Bearer authentication; Swagger UI có thể cung cấp nút Authorize để người dùng nhập token khi thử gọi API.

Khai báo security scheme chỉ mô tả hợp đồng. Nó không tự bật xác thực trong Spring Security, không tạo JWT và không thay thế cấu hình phân quyền. Ứng dụng vẫn phải thực thi bảo mật ở tầng phù hợp.

Cũng cần phân biệt bảo mật của API với bảo mật của chính trang tài liệu. Nếu Spring Security chặn **/v3/api-docs/** hoặc **/swagger-ui/**, Swagger UI có thể không tải được tài liệu. Nhóm phát triển cần cấu hình quyền truy cập cho các đường dẫn này theo chính sách của môi trường: cho phép công khai, yêu cầu đăng nhập hoặc chỉ cho phép mạng nội bộ.

## 7. Chia tài liệu thành nhiều nhóm API

Một ứng dụng lớn có thể chứa API cho quản trị, khách hàng, sản phẩm và tích hợp nội bộ. Đưa tất cả endpoint vào một tài liệu duy nhất khiến người đọc khó tìm đúng phần mình cần.

Springdoc hỗ trợ tạo các nhóm bằng **GroupedOpenApi**. Ví dụ:

~~~java
@Configuration
public class OpenApiGroupsConfiguration {

    @Bean
    public GroupedOpenApi catalogApi() {
        return GroupedOpenApi.builder()
            .group("catalog")
            .pathsToMatch("/api/products/**", "/api/categories/**")
            .build();
    }

    @Bean
    public GroupedOpenApi orderApi() {
        return GroupedOpenApi.builder()
            .group("orders")
            .pathsToMatch("/api/orders/**")
            .build();
    }
}
~~~

Mỗi nhóm có thể được truy cập qua endpoint tài liệu tương ứng, chẳng hạn **/v3/api-docs/catalog** và **/v3/api-docs/orders** với đường dẫn mặc định. Swagger UI có thể hiển thị danh sách nhóm để người dùng chọn tài liệu cần xem.

Nhóm API hữu ích khi:

- Một ứng dụng phục vụ nhiều đối tượng client có phạm vi truy cập khác nhau.
- Tài liệu public cần tách khỏi endpoint nội bộ.
- Nhóm phát triển muốn công bố tài liệu theo bounded context hoặc phiên bản API.
- Quy trình phát hành cần kiểm tra từng hợp đồng riêng.

Việc chia nhóm tài liệu không tự tạo ranh giới bảo mật. Nếu endpoint nội bộ vẫn được triển khai và có thể truy cập, cần kiểm soát quyền ở tầng ứng dụng hoặc hạ tầng.

## 8. Những nội dung tài liệu cần được chăm chút

Tự động sinh OpenAPI giúp giảm công việc lặp lại, nhưng chất lượng tài liệu vẫn phụ thuộc vào cách thiết kế và mô tả API.

**Request và parameter:** Làm rõ tham số nằm trong path, query, header hay body; ghi kiểu dữ liệu, định dạng, giá trị ví dụ và trường hợp bắt buộc. Với DTO, dùng Bean Validation để thể hiện các giới hạn có thể kiểm tra được và dùng **@Schema** để bổ sung ý nghĩa.

**Response:** Mô tả response thành công, response rỗng nếu có, và các lỗi có ý nghĩa với client như 400, 401, 403, 404 hoặc 409. Đừng giả định Springdoc luôn suy ra đầy đủ mọi response lỗi từ **@ControllerAdvice**; hãy khai báo rõ các response quan trọng và schema lỗi dùng chung.

**Enum và giá trị mẫu:** Cung cấp mô tả hoặc ví dụ cho trạng thái, loại phương thức thanh toán và các trường có tập giá trị giới hạn. Client cần biết ý nghĩa của từng giá trị, không chỉ biết trường có kiểu chuỗi.

**Pagination và sorting:** Giải thích quy ước page, size, sort, thứ tự mặc định và cấu trúc metadata của kết quả. Các tham số được framework suy luận vẫn có thể cần mô tả nghiệp vụ.

**Operation và tag:** Đặt tên tóm tắt dễ hiểu, gom endpoint theo chức năng và tránh để người đọc phải suy đoán từ tên phương thức Java.

**Endpoint không công bố:** Dùng **@Hidden** hoặc cấu hình lọc phù hợp khi một endpoint không thuộc phạm vi tài liệu. Việc ẩn endpoint khỏi OpenAPI không thay thế kiểm soát truy cập.

## 9. Từ OpenAPI document đến kiểm thử hợp đồng

OpenAPI document không chỉ phục vụ người đọc. Vì đây là dữ liệu có cấu trúc, nó có thể tham gia vào quy trình phát triển:

1. **Sinh client SDK:** Công cụ tương thích OpenAPI có thể tạo mã client cho Java, TypeScript hoặc các ngôn ngữ khác.
2. **Kiểm thử hợp đồng:** Pipeline có thể kiểm tra tài liệu có hợp lệ, endpoint có response schema cần thiết và request mẫu có tuân theo hợp đồng.
3. **Phát hiện thay đổi phá vỡ tương thích:** So sánh OpenAPI document của nhánh hiện tại với phiên bản đã phát hành để phát hiện việc xóa endpoint, đổi kiểu trường hoặc thay đổi response.
4. **Phân phối tài liệu:** Lưu JSON/YAML như một artifact của bản build, đưa lên cổng developer portal hoặc cung cấp cho nhóm tích hợp.
5. **Quản lý phiên bản:** Dùng version trong **info**, URL version hoặc các nhóm tài liệu để làm rõ hợp đồng nào đang được hỗ trợ.

Một quy trình thực tế có thể lấy **/v3/api-docs** từ ứng dụng đã khởi động trong môi trường kiểm thử, xác thực document bằng công cụ OpenAPI, rồi so sánh với tài liệu của bản phát hành gần nhất. Cần chọn rõ nguồn chuẩn: tài liệu được sinh từ đúng cấu hình và đúng phiên bản ứng dụng mà nhóm định phát hành.

Springdoc không tự bảo đảm API tuân thủ tài liệu. Một endpoint có thể được mô tả là trả về 200 nhưng logic thực tế vẫn trả về 500; một schema có thể đúng về kiểu nhưng sai về ý nghĩa nghiệp vụ. Vì vậy, cần kết hợp tài liệu sinh tự động với integration test, contract test và review thay đổi API.

## 10. Các lỗi thường gặp khi tích hợp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Không thấy endpoint trong Swagger UI | Controller chưa nằm trong phạm vi component scan; endpoint bị lọc bởi cấu hình path/package; endpoint bị ẩn; ứng dụng chưa nạp đúng mapping |
| **/v3/api-docs** trả về 404 | Starter không phù hợp; API docs bị tắt hoặc đổi path; cấu hình context path hoặc reverse proxy chưa đúng |
| Swagger UI không tải được JSON | Đường dẫn UI hoặc API docs không khớp; Spring Security chặn request; proxy chưa chuyển tiếp đúng prefix |
| Schema thiếu trường hoặc sai kiểu | DTO dùng kiểu tùy biến, generic hoặc serializer đặc biệt; cần kiểm tra cách Jackson và Springdoc diễn giải model, bổ sung **@Schema** khi cần |
| Tài liệu hiển thị sai server URL | Ứng dụng chạy sau proxy hoặc có nhiều môi trường nhưng thông tin forwarded header/server chưa được cấu hình đúng |
| Thiếu response lỗi | Chưa khai báo rõ **@ApiResponse**; exception handler thực tế chưa được mô tả trong OpenAPI |
| Không tương thích sau khi nâng cấp | Phiên bản Spring Boot, Java và Springdoc không khớp; cần đối chiếu ma trận tương thích và hướng dẫn migration |

Khi xử lý sự cố, nên kiểm tra lần lượt dependency và phiên bản, log khởi động, endpoint OpenAPI JSON, cấu hình lọc, Spring Security và reverse proxy. JSON là nguồn kiểm tra hữu ích: nếu endpoint đã có trong JSON nhưng không hiển thị như mong muốn trên UI, vấn đề có thể nằm ở giao diện hoặc cấu hình hiển thị.

## 11. Quy trình áp dụng trong một dự án

Một cách triển khai có thể bắt đầu từ phạm vi nhỏ:

1. Chọn starter tương thích với Spring Boot và mô hình web đang dùng.
2. Khởi động ứng dụng, kiểm tra OpenAPI JSON và Swagger UI.
3. Bổ sung **@Tag**, **@Operation**, **@Schema** và response cho các endpoint quan trọng.
4. Khai báo thông tin chung, security scheme và nhóm tài liệu nếu dự án cần.
5. Kiểm tra tài liệu ở cấu hình gần với môi trường triển khai, bao gồm context path, proxy và Spring Security.
6. Đưa bước kiểm tra OpenAPI document vào CI; xem thay đổi tài liệu như một phần của review hợp đồng API.
7. Phân phối đúng phiên bản tài liệu cùng bản phát hành và thông báo các thay đổi ảnh hưởng client.

Không cần mô tả mọi dòng mã bằng annotation. Hãy ưu tiên thông tin giúp người sử dụng API đưa ra request đúng, hiểu response và xử lý lỗi. Mục tiêu là tài liệu đủ rõ để một nhóm khác có thể tích hợp mà không phải đọc sâu vào implementation.

## 12. Kết luận

Springdoc OpenAPI giúp ứng dụng Spring Boot công bố hợp đồng API theo chuẩn OpenAPI và hiển thị hợp đồng đó qua Swagger UI. Thư viện tận dụng mapping, kiểu dữ liệu và annotation trong ứng dụng để giảm chênh lệch giữa mã nguồn và tài liệu. Khi được bổ sung mô tả về request, response, bảo mật, nhóm API và phiên bản, tài liệu có thể phục vụ cả lập trình viên, client tích hợp lẫn pipeline kiểm thử.

Giá trị của Springdoc không nằm ở việc tạo ra một trang Swagger UI đơn thuần. Giá trị lớn hơn là đưa tài liệu API vào cùng vòng đời phát triển phần mềm: thay đổi endpoint kéo theo thay đổi hợp đồng, hợp đồng được kiểm tra trước khi phát hành, và các nhóm tích hợp có một nguồn thông tin nhất quán để làm việc.


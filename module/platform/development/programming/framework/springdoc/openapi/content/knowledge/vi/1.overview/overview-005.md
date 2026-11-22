# Hướng tiếp cận code-first, design-first và phạm vi của Springdoc

Khi xây dựng API bằng Spring Boot, nhóm phát triển cần thống nhất một hợp đồng mô tả API: endpoint nào tồn tại, client gửi dữ liệu gì, server trả về dữ liệu nào, lỗi được biểu diễn ra sao và cơ chế bảo mật hoạt động thế nào. OpenAPI là một định dạng đặc tả phổ biến để biểu diễn hợp đồng đó. Từ đặc tả OpenAPI, nhóm có thể tạo tài liệu cho lập trình viên, cấu hình công cụ kiểm thử hoặc sinh mã client.

`springdoc-openapi` kết nối ứng dụng Spring Boot với OpenAPI. Thư viện đọc các thông tin mà ứng dụng công bố qua controller, kiểu dữ liệu, annotation và cấu hình để tạo tài liệu OpenAPI; nó cũng tích hợp Swagger UI để con người xem và thử gọi API. Vì vậy, khi chọn cách tiếp cận code-first hay design-first, điều quan trọng là xác định **nguồn sự thật của hợp đồng API** nằm ở đâu và Springdoc đảm nhiệm phần nào trong quy trình.

## 1. Hợp đồng OpenAPI và vị trí của Springdoc

Một tài liệu OpenAPI mô tả API theo cấu trúc máy có thể đọc được. Các thành phần thường gặp gồm:

- `info`: tên, phiên bản và mô tả của API.
- `servers`: các địa chỉ gốc mà client có thể sử dụng.
- `paths` và `operations`: đường dẫn, HTTP method, tham số, request body và các response.
- `components.schemas`: cấu trúc dữ liệu được tái sử dụng.
- `components.securitySchemes` và `security`: cơ chế xác thực, ủy quyền được công bố cho client.
- `tags`: nhóm các operation theo chức năng hoặc miền nghiệp vụ.

Trong ứng dụng Spring Boot, Springdoc thu thập thông tin từ các ánh xạ Spring MVC hoặc WebFlux được hỗ trợ, kiểu tham số và kiểu trả về, cùng các annotation OpenAPI như `@Operation`, `@Parameter`, `@Schema`, `@ApiResponse` và `@SecurityScheme`. Từ dữ liệu đó, thư viện tạo tài liệu OpenAPI tại thời điểm ứng dụng chạy.

Với cấu hình mặc định thường dùng, các địa chỉ quan trọng là:

| Địa chỉ | Mục đích |
| --- | --- |
| `/v3/api-docs` | Tài liệu OpenAPI ở dạng JSON |
| `/v3/api-docs.yaml` | Tài liệu OpenAPI ở dạng YAML |
| `/swagger-ui/index.html` | Giao diện Swagger UI để xem và thử API |

Đường dẫn có thể được thay đổi bằng cấu hình. Nếu ứng dụng có nhiều nhóm tài liệu, Springdoc còn cung cấp tài liệu theo từng group, thường có dạng `/v3/api-docs/{group}`. Các endpoint này là đầu ra tài liệu; chúng không thay thế endpoint nghiệp vụ của ứng dụng.

## 2. Code-first: bắt đầu từ mã nguồn Spring Boot

Code-first xem mã nguồn ứng dụng là nơi mô tả API trước tiên. Lập trình viên khai báo controller, request DTO, response DTO và các quy tắc xử lý bằng Spring. Springdoc đọc những khai báo đó để tạo đặc tả OpenAPI. Khi cần bổ sung ý nghĩa mà kiểu Java hoặc annotation Spring không thể hiện đầy đủ, lập trình viên thêm annotation OpenAPI hoặc cấu hình tập trung.

Quy trình thường có dạng:

1. Thiết kế hoặc triển khai controller và các DTO trong ứng dụng.
2. Dùng annotation OpenAPI để bổ sung mô tả, ví dụ, response và thông tin bảo mật cần thiết.
3. Khởi chạy ứng dụng, mở `/v3/api-docs` để kiểm tra đặc tả được sinh ra.
4. Mở Swagger UI để rà soát tài liệu và thử gọi các endpoint phù hợp.
5. Đưa việc kiểm tra cấu trúc đặc tả và kiểm thử hợp đồng vào quy trình CI khi dự án cần.

Ví dụ sau minh họa một endpoint đọc thông tin sách. Phần xử lý nghiệp vụ được lược bỏ để tập trung vào cách mô tả hợp đồng:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
@Tag(name = "Books", description = "API quản lý sách")
class BookController {

    @GetMapping("/{id}")
    @Operation(summary = "Lấy thông tin sách theo ID")
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Tìm thấy sách"),
        @ApiResponse(responseCode = "404", description = "Không tìm thấy sách")
    })
    BookResponse getById(
            @Parameter(description = "ID của sách", example = "42")
            @PathVariable long id) {
        // Gọi service và trả về dữ liệu thực tế của ứng dụng.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }
}

@Schema(description = "Thông tin sách được trả về cho client")
record BookResponse(
    @Schema(description = "Mã sách", example = "42")
    long id,

    @Schema(description = "Tên sách", example = "Spring in Action")
    String title
) {}
```

Springdoc có thể suy ra nhiều thông tin từ chữ ký method, annotation Spring và kiểu dữ liệu. `@Operation` bổ sung ý nghĩa cho operation; `@ApiResponses` công bố các mã phản hồi quan trọng; `@Parameter` giải thích tham số; `@Schema` mô tả cấu trúc và ví dụ của dữ liệu. Với endpoint đơn giản, không cần lặp lại mọi thông tin mà Springdoc đã suy ra chính xác. Chỉ nên thêm annotation khi cần làm rõ ngữ nghĩa, ví dụ, trường hợp lỗi hoặc quy tắc mà mã nguồn chưa biểu đạt rõ.

### Bổ sung metadata ở cấp API

Thông tin chung như tiêu đề, mô tả và phiên bản tài liệu có thể được cấu hình bằng một bean `OpenAPI`:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfig {

    @Bean
    OpenAPI serviceApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Book Service API")
                .description("API tra cứu và quản lý sách")
                .version("1.0.0"));
    }
}
```

Ví dụ này mô tả phiên bản của tài liệu API. Nó không tự động quyết định chiến lược tương thích ngược hay cách triển khai versioning cho endpoint; nhóm phát triển vẫn phải quy định các chính sách đó.

### Mô tả bảo mật

Nếu API sử dụng Bearer token, có thể khai báo security scheme để OpenAPI và Swagger UI hiểu cách client cung cấp thông tin xác thực:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class ApiSecurityDocumentationConfig {}
```

Operation cần thể hiện yêu cầu xác thực có thể gắn `@SecurityRequirement(name = "bearerAuth")`. Khai báo này giúp tài liệu mô tả cơ chế bảo mật và hỗ trợ thao tác nhập token trong Swagger UI. Nó **không cấu hình Spring Security**, không cấp token và cũng không bảo vệ endpoint. Quyền truy cập thực tế vẫn do cơ chế bảo mật của ứng dụng quyết định.

### Chia tài liệu thành nhiều group

Một ứng dụng có thể phục vụ nhiều nhóm người dùng, chẳng hạn API nội bộ, API đối tác và API công khai. `GroupedOpenApi` cho phép tạo các tập tài liệu riêng dựa trên package hoặc đường dẫn:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ApiGroupsConfig {

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner")
            .pathsToMatch("/api/partners/**")
            .build();
    }
}
```

Với cấu hình minh họa trên, tài liệu của group `partner` có thể được truy cập tại `/v3/api-docs/partner`. API và đường dẫn cụ thể trong dự án cần được điều chỉnh theo cấu trúc thực tế. Ví dụ import ở trên phù hợp với dòng Springdoc 2.x; package hoặc cách cấu hình có thể khác giữa các phiên bản chính, vì vậy cần đối chiếu tài liệu của phiên bản thư viện đang dùng.

## 3. Design-first: bắt đầu từ hợp đồng OpenAPI

Design-first xem tài liệu OpenAPI là nguồn sự thật của hợp đồng. Nhóm thống nhất endpoint, request, response, mã lỗi, schema và bảo mật trước khi hoàn thiện phần triển khai. Sau đó, backend và frontend cùng làm theo hợp đồng đã duyệt.

Quy trình thường gồm:

1. Phân tích nhu cầu và thống nhất hành vi API với các bên liên quan.
2. Viết đặc tả OpenAPI bằng YAML hoặc JSON, có thể dùng công cụ thiết kế chuyên dụng.
3. Review và quản lý thay đổi của đặc tả trong hệ thống quản lý phiên bản.
4. Dùng đặc tả làm căn cứ triển khai server, tạo mock hoặc sinh client nếu quy trình dự án có sử dụng các công cụ đó.
5. Kiểm tra implementation có đáp ứng hợp đồng đã thống nhất hay không.
6. Phân phối cùng một phiên bản hợp đồng cho backend, frontend, QA và đối tác.

Ví dụ rút gọn về một hợp đồng đọc sách:

```yaml
openapi: 3.0.3
info:
  title: Book Service API
  version: 1.0.0
  description: API tra cứu thông tin sách
paths:
  /api/books/{id}:
    get:
      tags:
        - Books
      summary: Lấy thông tin sách theo ID
      parameters:
        - name: id
          in: path
          required: true
          description: ID của sách
          schema:
            type: integer
            format: int64
          example: 42
      responses:
        '200':
          description: Tìm thấy sách
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BookResponse'
        '404':
          description: Không tìm thấy sách
components:
  schemas:
    BookResponse:
      type: object
      required:
        - id
        - title
      properties:
        id:
          type: integer
          format: int64
          example: 42
        title:
          type: string
          example: Spring in Action
```

Trong design-first, Springdoc không phải công cụ thiết kế hợp đồng hay công cụ sinh mã từ OpenAPI. Vai trò chính của Springdoc là sinh tài liệu từ ứng dụng Spring và tích hợp Swagger UI. Tuy nhiên, Swagger UI có thể hiển thị một tài liệu OpenAPI tĩnh đã được chuẩn bị trước. Ví dụ, đặt file tại `src/main/resources/static/contracts/openapi.yaml`, để Spring Boot phục vụ file ở đường dẫn `/contracts/openapi.yaml`, rồi cấu hình:

```properties
springdoc.swagger-ui.url=/contracts/openapi.yaml
```

Swagger UI sẽ tải đặc tả tại URL được cấu hình. Cần kiểm tra URL có thể truy cập từ trình duyệt và cấu hình tài nguyên tĩnh phù hợp với cách đóng gói ứng dụng. Nếu đồng thời bật endpoint OpenAPI được Springdoc sinh từ controller, hãy làm rõ tài liệu nào là hợp đồng chuẩn để tránh người dùng chọn nhầm giữa bản thiết kế và bản phản ánh implementation.

Trong quy trình design-first, nhóm thường cần thêm công cụ hoặc bước CI riêng để kiểm tra cú pháp, quy tắc lint, tương thích phiên bản, sinh mã và đối chiếu implementation với hợp đồng. Swagger UI chỉ trình bày đặc tả; việc hiển thị thành công không chứng minh server đã triển khai đúng mọi quy tắc trong YAML.

## 4. So sánh code-first và design-first

| Tiêu chí | Code-first | Design-first |
| --- | --- | --- |
| Nguồn sự thật | Mã nguồn controller, DTO và cấu hình | File OpenAPI đã được review |
| Thời điểm có hợp đồng | Được hình thành cùng hoặc sau khi triển khai | Được thống nhất trước khi triển khai |
| Cách tạo tài liệu | Springdoc suy ra từ ứng dụng, sau đó được bổ sung metadata | Đặc tả được viết và quản lý độc lập; Swagger UI có thể hiển thị file đó |
| Điểm mạnh | Gần với implementation, thuận tiện cho dịch vụ đã có code | Các bên thống nhất giao diện sớm, thuận tiện phát triển song song |
| Rủi ro thường gặp | Tài liệu phản ánh sai sót trong code hoặc thiếu mô tả nghiệp vụ | Đặc tả và implementation có thể lệch nhau nếu không kiểm tra |
| Phù hợp khi | Dịch vụ đã tồn tại, nhóm backend làm chủ thiết kế và triển khai | Nhiều nhóm cùng tiêu thụ API hoặc hợp đồng cần được duyệt trước |

Không có cách tiếp cận nào phù hợp với mọi dự án. Một dịch vụ nội bộ nhỏ có thể ưu tiên code-first để giảm công việc duy trì tài liệu. Một API công khai được nhiều đối tác tích hợp thường cần design-first để các bên thống nhất thay đổi trước khi phát hành. Tiêu chí quyết định nên là chi phí phối hợp, mức độ ổn định của hợp đồng và khả năng kiểm soát sai lệch, thay vì chỉ dựa trên sở thích công cụ.

## 5. Kết hợp hai cách tiếp cận

Nhiều nhóm sử dụng mô hình kết hợp. Họ thiết kế hợp đồng ở mức đủ rõ để các bên thống nhất, sau đó triển khai bằng Spring Boot và dùng Springdoc tạo ra tài liệu phản ánh ứng dụng thực tế. Một quy trình kết hợp có thể như sau:

1. Tạo bản OpenAPI ban đầu để thống nhất endpoint, schema, response và quy tắc bảo mật.
2. Triển khai controller và DTO theo hợp đồng.
3. Dùng Springdoc sinh tài liệu từ ứng dụng đang chạy.
4. So sánh tài liệu sinh ra với hợp đồng chuẩn bằng bước kiểm tra tự động hoặc review có kiểm soát.
5. Khi hợp đồng thay đổi, cập nhật đặc tả, implementation và ví dụ client trong cùng một quy trình phát hành.

Trong mô hình này cần quy định rõ ai được phép sửa hợp đồng và khi nào thay đổi được chấp nhận. Nếu nhóm chọn file YAML làm nguồn chuẩn, không nên âm thầm coi tài liệu sinh từ code là bản thay thế. Nếu nhóm chọn code làm nguồn chuẩn, cần review thay đổi annotation và DTO như một phần của thay đổi API.

## 6. Phạm vi Springdoc: làm được gì và cần công cụ nào khác?

Springdoc tập trung vào việc tạo và phục vụ tài liệu OpenAPI trong hệ sinh thái Spring Boot. Có thể nhìn phạm vi của nó qua các nhóm trách nhiệm sau:

| Nhu cầu | Vai trò của Springdoc |
| --- | --- |
| Phát hiện endpoint và HTTP method | Đọc các ánh xạ controller được hỗ trợ trong ứng dụng Spring |
| Mô tả request và response | Suy ra từ tham số, kiểu dữ liệu và annotation; cho phép bổ sung metadata |
| Mô tả schema | Tạo schema từ kiểu dữ liệu và hỗ trợ tùy biến bằng annotation OpenAPI |
| Mô tả bảo mật | Đưa security scheme và security requirement vào đặc tả |
| Nhóm tài liệu | Tạo nhiều OpenAPI group theo cấu hình |
| Xem và thử API | Tích hợp Swagger UI để đọc đặc tả và gửi request thử khi môi trường cho phép |
| Xuất tài liệu | Cung cấp tài liệu OpenAPI dạng JSON hoặc YAML qua endpoint |

Springdoc không thay thế các trách nhiệm sau:

- **Thiết kế nghiệp vụ:** nhóm vẫn phải quyết định tài nguyên, quy tắc, luồng xử lý, mã lỗi và ý nghĩa của từng trường dữ liệu.
- **Bảo mật thực tế:** annotation mô tả bảo mật trong tài liệu không thay thế Spring Security, xác thực, phân quyền hay cấu hình mạng.
- **Kiểm thử hợp đồng:** tài liệu sinh ra không tự chứng minh response thực tế khớp schema, mã trạng thái đúng hoặc mọi trường hợp lỗi đã được xử lý. Cần kiểm thử API và kiểm thử hợp đồng riêng.
- **Quản lý vòng đời API:** Springdoc không tự quyết định chính sách tương thích ngược, thời điểm ngừng hỗ trợ, quy tắc tăng phiên bản hay quy trình thông báo cho client.
- **Sinh mã và quản trị API:** việc sinh SDK, tạo mock server, lint quy chuẩn, so sánh breaking change, xuất bản portal hoặc quản lý quyền truy cập tài liệu có thể cần công cụ và quy trình khác.
- **Chất lượng nội dung nghiệp vụ:** thư viện có thể suy ra kiểu Java nhưng không thể tự biết đầy đủ ý nghĩa như đơn vị đo, quy tắc ràng buộc, điều kiện chuyển trạng thái hoặc lý do một lỗi có thể xảy ra.

Ví dụ, nếu một method trả về `ResponseEntity<BookResponse>`, Springdoc có thể dùng kiểu trả về để xây dựng schema response. Nhưng nó không thực thi method để xác minh rằng mọi nhánh đều trả về đúng schema, cũng không biết một mã `404` có được phát ra đúng trong mọi trường hợp hay không. Những điều đó cần được bảo đảm ở tầng triển khai và kiểm thử.

## 7. Nhóm tài liệu, phiên bản API và phiên bản đặc tả

Ba khái niệm sau cần được phân biệt:

- **Phiên bản API:** phiên bản hợp đồng mà client sử dụng, thường thể hiện qua đường dẫn như `/api/v1/...`, header hoặc một quy ước khác của hệ thống.
- **Phiên bản tài liệu:** giá trị `info.version` trong OpenAPI, do nhóm quy định để nhận diện phiên bản hợp đồng được công bố.
- **Group của Springdoc:** một tập endpoint được gom thành một tài liệu riêng, chẳng hạn `public`, `internal` hoặc `partner`.

Group chỉ chia phạm vi tài liệu theo cấu hình; nó không tự tạo phiên bản API, không bảo đảm tương thích và không phân quyền truy cập. Nếu tài liệu nội bộ chứa thông tin nhạy cảm, cần bảo vệ endpoint tài liệu bằng cấu hình bảo mật phù hợp hoặc không công bố nó ra môi trường công khai.

Khi thay đổi API, nhóm cần đánh giá tác động với client hiện có. Thêm một trường response tùy chọn thường có mức độ ảnh hưởng khác với việc đổi tên trường bắt buộc, đổi kiểu dữ liệu, xóa endpoint hoặc thay đổi ý nghĩa mã lỗi. Springdoc giúp thể hiện kết quả thay đổi trong đặc tả; việc phân loại breaking change và quyết định phát hành vẫn thuộc quy trình quản lý API của nhóm.

## 8. Chọn hướng tiếp cận cho một dự án Spring Boot

Có thể dùng các câu hỏi sau để lựa chọn:

1. **Ai cần duyệt hợp đồng?** Nếu frontend, QA, đối tác hoặc nhiều nhóm cần thống nhất trước khi backend hoàn thành, design-first thường phù hợp hơn.
2. **Nguồn sự thật hiện tại nằm ở đâu?** Nếu dịch vụ đã có controller và DTO ổn định, code-first với Springdoc có thể là điểm bắt đầu thực tế.
3. **Mức độ ảnh hưởng của thay đổi ra sao?** API công khai hoặc API có nhiều client cần quản lý hợp đồng, versioning và kiểm tra breaking change chặt chẽ hơn.
4. **Nhóm có kiểm tra sai lệch không?** Dù chọn cách nào, cần có bước xác minh tài liệu với implementation và kiểm thử hành vi thực tế.
5. **Tài liệu được phân phối thế nào?** Xác định endpoint tài liệu có được truy cập ở production hay không, ai được xem và phiên bản nào được công bố cho client.

Với một Spring Boot service mới, cách khởi đầu hợp lý là xác định các operation và schema quan trọng trước, sau đó quyết định chúng được quản lý trực tiếp trong code hay trong file OpenAPI. Nếu chọn code-first, hãy dùng Springdoc để sinh tài liệu và bổ sung annotation có chọn lọc. Nếu chọn design-first, hãy quản lý YAML/JSON như một phần của hợp đồng, dùng Swagger UI để hiển thị khi phù hợp và bổ sung bước kiểm tra implementation. Nếu kết hợp, phải ghi rõ nguồn chuẩn và cơ chế đồng bộ.

## 9. Checklist khi đưa Springdoc vào dự án

- Chọn phiên bản Springdoc tương thích với dòng Spring Boot và các dependency của dự án.
- Xác định rõ code hay file OpenAPI là nguồn sự thật của hợp đồng.
- Kiểm tra `/v3/api-docs` và `/v3/api-docs.yaml` trong môi trường phát triển.
- Bổ sung mô tả cho operation, tham số, schema, response lỗi và bảo mật ở những nơi cần thiết.
- Kiểm tra ví dụ và kiểu dữ liệu có phản ánh đúng hợp đồng client cần dùng.
- Nếu có nhiều nhóm API, cấu hình group và xác định endpoint tài liệu tương ứng.
- Quyết định Swagger UI và endpoint tài liệu có được bật ở từng môi trường hay không; bảo vệ tài liệu nội bộ khi cần.
- Đưa kiểm tra đặc tả và kiểm thử hợp đồng vào CI theo mức độ quan trọng của API.
- Quản lý thay đổi hợp đồng, versioning và thông báo cho client trong quy trình phát hành.

Springdoc phát huy hiệu quả nhất khi nhóm đã có quy ước rõ về hợp đồng API. Nó tự động hóa phần chuyển thông tin từ ứng dụng Spring Boot thành OpenAPI và cung cấp giao diện đọc tài liệu, giúp giảm thao tác cập nhật thủ công. Chất lượng hợp đồng vẫn phụ thuộc vào quyết định thiết kế, metadata được khai báo, kiểm thử và quy trình quản lý thay đổi của nhóm.

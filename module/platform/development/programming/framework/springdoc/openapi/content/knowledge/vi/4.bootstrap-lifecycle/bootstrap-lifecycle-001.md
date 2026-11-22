# Tạo tài liệu cho một REST Controller tối thiểu

Springdoc giúp ứng dụng Spring Boot tạo đặc tả OpenAPI từ các REST Controller và hiển thị đặc tả đó bằng Swagger UI. Với một controller đơn giản, bạn chỉ cần thêm đúng starter Springdoc, khai báo endpoint bằng Spring MVC và chạy ứng dụng. Springdoc tự đọc các ánh xạ HTTP, tham số và kiểu dữ liệu để tạo tài liệu; annotation OpenAPI được dùng khi cần bổ sung mô tả rõ ràng hơn.

Bài học xây dựng một API quản lý sách nhỏ với hai thao tác: đọc sách theo ID và tạo sách mới. Sau khi chạy ứng dụng, bạn sẽ kiểm tra endpoint REST, tài liệu JSON/YAML và giao diện Swagger UI.

## 1. Chuẩn bị ứng dụng Spring Boot

Ví dụ sử dụng Spring Boot 3, Java 17 trở lên và Spring MVC. Nếu dự án đã có `spring-boot-starter-web`, chỉ cần bổ sung starter Springdoc tương thích với phiên bản Spring Boot đang dùng.

Trong `pom.xml`, khai báo các dependency chính:

```xml
<properties>
    <java.version>17</java.version>
    <springdoc.version>2.x.y</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

`2.x.y` là ký hiệu giữ chỗ. Hãy thay bằng một phiên bản Springdoc 2.x cụ thể tương thích với phiên bản Spring Boot 3 của dự án. Starter `springdoc-openapi-starter-webmvc-ui` tích hợp phần tạo đặc tả OpenAPI cho Spring MVC và Swagger UI. Với Spring WebFlux, cần chọn starter WebFlux tương ứng. Ứng dụng Spring Boot 2 sử dụng dòng Springdoc 1.x và artifact khác; không trộn dependency của hai thế hệ.

Một cấu trúc package đơn giản có thể như sau:

```text
src/main/java/com/example/books/
├── BooksApplication.java
├── BookController.java
└── dto/
    ├── BookResponse.java
    └── CreateBookRequest.java
```

Đặt lớp ứng dụng ở package gốc để Spring Boot quét được controller và DTO trong các package con.

## 2. Tạo lớp khởi động ứng dụng

Tạo file `BooksApplication.java`:

```java
package com.example.books;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BooksApplication {

    public static void main(String[] args) {
        SpringApplication.run(BooksApplication.class, args);
    }
}
```

`@SpringBootApplication` kích hoạt cấu hình tự động và component scanning từ package `com.example.books`. Springdoc dựa trên các bean và ánh xạ endpoint trong ứng dụng, vì vậy controller phải được Spring phát hiện và đăng ký.

## 3. Khai báo DTO cho request và response

DTO mô tả dữ liệu đi qua API. Springdoc có thể suy ra schema từ kiểu Java, tên thuộc tính và một số annotation. Annotation `@Schema` bổ sung mô tả hoặc ví dụ để người đọc tài liệu hiểu ý nghĩa của từng trường.

Tạo `dto/CreateBookRequest.java`:

```java
package com.example.books.dto;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Dữ liệu client gửi để tạo sách mới")
public record CreateBookRequest(
    @Schema(description = "Tên sách", example = "Spring Boot căn bản")
    String title
) {}
```

Tạo `dto/BookResponse.java`:

```java
package com.example.books.dto;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Thông tin sách trả về cho client")
public record BookResponse(
    @Schema(description = "Mã định danh sách", example = "1")
    long id,

    @Schema(description = "Tên sách", example = "Spring Boot căn bản")
    String title
) {}
```

Hai record trên dùng cú pháp Java record, phù hợp với Java 17. Nếu dự án dùng Java cũ hơn, có thể thay record bằng class có constructor, getter và các field tương ứng. Kiểu dữ liệu trong DTO sẽ trở thành cơ sở để Springdoc tạo schema trong đặc tả.

## 4. Tạo REST Controller và mô tả operation

Tạo file `BookController.java`:

```java
package com.example.books;

import com.example.books.dto.BookResponse;
import com.example.books.dto.CreateBookRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
@Tag(name = "Books", description = "Các thao tác với sách")
public class BookController {

    @GetMapping("/{id}")
    @Operation(
        summary = "Lấy thông tin sách theo ID",
        description = "Trả về thông tin sách nếu ID tồn tại"
    )
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Tìm thấy sách"),
        @ApiResponse(responseCode = "404", description = "Không tìm thấy sách")
    })
    public ResponseEntity<BookResponse> getById(
            @Parameter(description = "Mã định danh của sách", example = "1")
            @PathVariable long id) {

        if (id != 1L) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(
            new BookResponse(1L, "Spring Boot căn bản")
        );
    }

    @PostMapping
    @Operation(
        summary = "Tạo sách mới",
        description = "Nhận dữ liệu sách và trả về thông tin vừa tạo"
    )
    @ApiResponses({
        @ApiResponse(responseCode = "201", description = "Tạo sách thành công"),
        @ApiResponse(responseCode = "400", description = "Dữ liệu request không hợp lệ")
    })
    public ResponseEntity<BookResponse> create(
            @RequestBody CreateBookRequest request) {

        BookResponse created = new BookResponse(2L, request.title());
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

Đây là controller minh họa tài liệu API. Endpoint GET trả về một bản ghi cố định khi `id` bằng `1`; endpoint POST trả về dữ liệu mô phỏng với ID `2`, chưa lưu vào cơ sở dữ liệu. Trong ứng dụng thực tế, controller thường gọi service để thực hiện nghiệp vụ và lưu dữ liệu.

Các annotation quan trọng trong ví dụ:

| Annotation | Vai trò trong tài liệu |
| --- | --- |
| `@RestController` | Khai báo controller REST để Spring MVC đăng ký các endpoint |
| `@RequestMapping` | Xác định tiền tố đường dẫn cho controller |
| `@GetMapping`, `@PostMapping` | Khai báo HTTP method và đường dẫn operation |
| `@Tag` | Gom operation vào nhóm Books trong tài liệu |
| `@Operation` | Bổ sung tên ngắn và mô tả cho operation |
| `@Parameter` | Mô tả tham số đường dẫn `id` |
| `@ApiResponses`, `@ApiResponse` | Mô tả các mã HTTP response quan trọng |
| `@Schema` | Mô tả cấu trúc và ví dụ cho DTO |

Springdoc có thể tự suy ra nhiều thông tin từ `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestBody`, kiểu trả về và DTO. Không cần thêm annotation cho mọi chi tiết nếu dữ liệu suy ra đã chính xác. Hãy dùng annotation OpenAPI để bổ sung ý nghĩa mà mã nguồn chưa thể hiện đầy đủ.

## 5. Khởi chạy và kiểm tra REST API

Chạy ứng dụng từ thư mục dự án:

```bash
./mvnw spring-boot:run
```

Trên Windows có thể dùng:

```powershell
.\mvnw.cmd spring-boot:run
```

Khi ứng dụng khởi động thành công trên cổng mặc định `8080`, thử gọi endpoint GET:

```bash
curl -i http://localhost:8080/api/books/1
```

Response thành công có mã `200` và nội dung JSON tương tự:

```json
{
  "id": 1,
  "title": "Spring Boot căn bản"
}
```

Gọi một ID khác để kiểm tra trường hợp không tìm thấy:

```bash
curl -i http://localhost:8080/api/books/99
```

Response có mã `404`. Tiếp theo, gửi request tạo sách:

```bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Spring Boot căn bản"}'
```

Response mô phỏng có mã `201 Created` và một đối tượng `BookResponse`. Những lần gọi này kiểm tra hành vi của controller; tài liệu OpenAPI được tạo riêng từ metadata của ứng dụng.

## 6. Mở tài liệu OpenAPI do Springdoc tạo

Với cấu hình mặc định thường dùng, Springdoc cung cấp các endpoint sau:

| URL | Nội dung |
| --- | --- |
| `http://localhost:8080/v3/api-docs` | Đặc tả OpenAPI dạng JSON |
| `http://localhost:8080/v3/api-docs.yaml` | Đặc tả OpenAPI dạng YAML |
| `http://localhost:8080/swagger-ui/index.html` | Swagger UI để xem và thử API |

Mở `/v3/api-docs` để kiểm tra tài liệu máy có thể đọc được. Trong JSON, tìm `paths` để thấy `/api/books/{id}` và `/api/books`, sau đó kiểm tra `components.schemas` để thấy các schema `BookResponse` và `CreateBookRequest`. Thông tin mô tả từ `@Operation`, `@ApiResponse`, `@Parameter` và `@Schema` sẽ được phản ánh trong đặc tả tương ứng.

Mở Swagger UI để xem API theo nhóm Books. Chọn operation GET hoặc POST, nhấn **Try it out**, nhập tham số hoặc request body rồi thực thi. Swagger UI gửi request đến server theo địa chỉ được khai báo trong tài liệu; vì vậy ứng dụng phải đang chạy và trình duyệt phải truy cập được server.

Swagger UI chỉ là giao diện đọc và thử gọi API. Nó không thay thế controller, không tự lưu dữ liệu và không bảo đảm rằng mọi hành vi nghiệp vụ đều đúng với mô tả.

## 7. Tùy chỉnh metadata chung của API

Khi muốn tài liệu có tiêu đề, mô tả và phiên bản rõ ràng, khai báo bean `OpenAPI`:

```java
package com.example.books;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI booksApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Books API")
                .description("API minh họa tra cứu và tạo sách")
                .version("1.0.0"));
    }
}
```

Sau khi thêm bean, tải lại `/v3/api-docs` để kiểm tra `info.title`, `info.description` và `info.version`. Giá trị `info.version` là phiên bản tài liệu/hợp đồng được công bố; nó không tự động tạo version cho URL endpoint hoặc quyết định chính sách tương thích ngược.

## 8. Một số cấu hình thường dùng

Có thể tùy chỉnh đường dẫn endpoint tài liệu và Swagger UI trong `application.properties`:

```properties
# Đổi đường dẫn phục vụ đặc tả OpenAPI
springdoc.api-docs.path=/openapi

# Đổi đường dẫn truy cập giao diện Swagger UI
springdoc.swagger-ui.path=/docs
```

Với cấu hình này, tài liệu JSON được phục vụ tại `/openapi`; đường dẫn giao diện UI được cấu hình tại `/docs`. Hãy kiểm tra URL thực tế sau khi khởi động và tính đến `server.servlet.context-path` nếu ứng dụng có context path riêng. Khi đổi đường dẫn, các URL mặc định trong bảng ở phần trước không còn là địa chỉ truy cập tương ứng.

Trong một số môi trường, nhóm có thể tắt tài liệu hoặc Swagger UI bằng cấu hình:

```properties
springdoc.api-docs.enabled=false
springdoc.swagger-ui.enabled=false
```

Chỉ sử dụng các thuộc tính này khi có chủ đích theo môi trường. Nếu endpoint tài liệu trả về `404`, hãy kiểm tra xem tài liệu có bị tắt hoặc đổi path hay không trước khi kết luận starter chưa hoạt động.

## 9. Lỗi thường gặp khi tạo tài liệu lần đầu

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `/v3/api-docs` trả về `404` | Thiếu starter Springdoc, dùng sai starter MVC/WebFlux, endpoint đã đổi path hoặc bị tắt | Kiểm tra dependency và `springdoc.api-docs.*` |
| Controller không xuất hiện trong `paths` | Controller chưa được component scanning phát hiện hoặc không có mapping Spring hợp lệ | Kiểm tra package của lớp `@SpringBootApplication` và mapping controller |
| Schema DTO thiếu trường hoặc sai kiểu | Kiểu Java, getter/record component hoặc cấu hình serialization chưa như mong muốn | Kiểm tra DTO và JSON thực tế mà endpoint trả về |
| Swagger UI mở nhưng không tải được đặc tả | UI đang trỏ đến URL sai, context path hoặc proxy chưa đúng | Kiểm tra request lấy OpenAPI trong Network của trình duyệt |
| Swagger UI gửi request nhưng nhận `401`/`403` | API được bảo vệ bởi Spring Security hoặc gateway | Kiểm tra cấu hình xác thực và quyền truy cập môi trường thử nghiệm |
| Không thấy mô tả annotation | Import nhầm annotation Swagger v1 hoặc annotation chưa đặt đúng vị trí | Dùng package `io.swagger.v3.oas.annotations` và kiểm tra lại operation/schema |

Nếu dự án có Spring Security, endpoint `/v3/api-docs` và Swagger UI có thể cần được cấp quyền truy cập phù hợp trong môi trường phát triển. Không nên mở công khai tài liệu nội bộ chỉ để khắc phục lỗi truy cập; hãy áp dụng chính sách bảo mật đúng với môi trường triển khai.

## 10. Checklist hoàn thành bài thực hành

- [ ] Ứng dụng Spring Boot khởi động thành công với đúng starter Springdoc.
- [ ] Controller được Spring phát hiện và endpoint GET/POST hoạt động.
- [ ] DTO request và response được mô tả thành schema.
- [ ] `@Tag`, `@Operation`, `@Parameter` và response metadata xuất hiện trong tài liệu.
- [ ] `/v3/api-docs` trả về JSON OpenAPI hợp lệ.
- [ ] `/v3/api-docs.yaml` trả về đặc tả YAML.
- [ ] Swagger UI hiển thị các operation và có thể thử gọi API.
- [ ] Nhóm hiểu rằng tài liệu được sinh từ controller/DTO, còn kiểm thử API vẫn cần xác minh hành vi thực tế.

Sau bài thực hành, bạn đã có một REST Controller Spring Boot tối thiểu được Springdoc mô tả thành OpenAPI và hiển thị qua Swagger UI. Đây là nền tảng để tiếp tục mô tả request/response phức tạp, bảo mật, nhóm tài liệu và kiểm thử hợp đồng API.

# Tìm kiếm, lọc và hiển thị mô hình schema

Swagger UI giúp người tích hợp tìm operation, đọc request/response và xem cấu trúc dữ liệu do OpenAPI mô tả. Khi API có nhiều tag, nhiều operation hoặc nhiều schema dùng chung, việc tổ chức bộ lọc và cách mở rộng mô hình sẽ ảnh hưởng trực tiếp đến khả năng tra cứu tài liệu.

Springdoc cung cấp cấu hình Swagger UI qua các thuộc tính `springdoc.swagger-ui.*`. Có thể bật bộ lọc tag, sắp xếp nhóm operation, chọn cách mở rộng danh sách endpoint và điều khiển cách hiển thị schema/example. Những thiết lập này chỉ thay đổi giao diện tài liệu; schema thực tế vẫn được tạo từ controller, DTO, annotation OpenAPI và metadata Springdoc.

## 1. Bộ lọc tích hợp trong Swagger UI

Swagger UI có tùy chọn `filter` để bật ô lọc ở đầu giao diện. Người đọc nhập tên tag để thu hẹp danh sách nhóm operation. Việc lọc phân biệt chữ hoa/chữ thường.

Trong `application.yml`:

```yaml
springdoc:
  swagger-ui:
    filter: true
```

Hoặc trong `application.properties`:

```properties
springdoc.swagger-ui.filter=true
```

Khi bật, Swagger UI hiển thị ô lọc tag. Ví dụ API có các tag `Books`, `Orders`, `Payments`; nhập `Books` sẽ giúp người đọc tập trung vào nhóm tài liệu có tag tương ứng.

Có thể cung cấp chuỗi mặc định thay cho boolean:

```yaml
springdoc:
  swagger-ui:
    filter: Books
```

Chuỗi này được dùng làm giá trị lọc ban đầu. Nếu chỉ muốn bật ô nhập và để người dùng tự tìm, dùng `true`.

Lưu ý rằng filter tích hợp tập trung vào tag và nhóm operation. Nó không phải công cụ tìm kiếm toàn văn trên mọi nội dung của OpenAPI như summary, description, schema property hoặc example. Để tìm nhanh một từ trong nội dung trang đang mở, người đọc có thể dùng chức năng tìm kiếm của trình duyệt; nếu sản phẩm cần tìm kiếm toàn văn chuyên biệt, cần xây dựng giao diện hoặc plugin phù hợp.

## 2. Tag tốt giúp lọc operation hiệu quả

Filter chỉ hữu ích khi operation được gắn tag rõ ràng và nhất quán. Có thể gắn tag ở cấp controller bằng `@Tag`:

```java
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
@Tag(name = "Books", description = "Tra cứu và quản lý sách")
public class BookController {
    // Các operation của Books API.
}
```

Hoặc gắn tag cho operation riêng bằng `@Operation`:

```java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/reports/sales")
@Operation(
    summary = "Báo cáo doanh thu",
    tags = {"Reports", "Sales"}
)
public String getSalesReport() {
    return "sales report";
}
```

Trong dự án lớn, nên dùng tên tag ổn định, dễ hiểu và có quy ước chung. Tránh các biến thể như `Book`, `Books`, `book-api` nếu chúng cùng chỉ một nhóm chức năng; các tên khác nhau sẽ tạo nhiều nhóm riêng và làm bộ lọc khó dùng.

Có thể khai báo mô tả tag tập trung trong `@OpenAPIDefinition`:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.tags.Tag;

@OpenAPIDefinition(
    tags = {
        @Tag(name = "Books", description = "Tra cứu và quản lý sách"),
        @Tag(name = "Orders", description = "Quản lý đơn hàng"),
        @Tag(name = "Payments", description = "Tạo và tra cứu thanh toán")
    }
)
```

Tag mô tả cách nhóm operation trong tài liệu. Nó không thay đổi URL, controller mapping hoặc quyền truy cập API.

## 3. Sắp xếp tag và operation để dễ tìm

Khi số lượng tag và operation tăng, có thể sắp xếp chúng theo thứ tự chữ cái hoặc thứ tự HTTP method. Swagger UI hỗ trợ `tagsSorter` và `operationsSorter`.

Ví dụ cấu hình:

```yaml
springdoc:
  swagger-ui:
    filter: true
    tags-sorter: alpha
    operations-sorter: alpha
```

Các giá trị thường dùng:

| Thuộc tính | Giá trị | Kết quả |
| --- | --- | --- |
| `tags-sorter` | `alpha` | Sắp xếp tag theo thứ tự chữ cái |
| `operations-sorter` | `alpha` | Sắp xếp operation theo thứ tự chữ cái |
| `operations-sorter` | `method` | Sắp xếp operation theo HTTP method |

Nếu muốn giữ thứ tự do đặc tả hoặc plugin quyết định, không cần cấu hình sorter. Khi tùy chỉnh sorter bằng JavaScript function, cần kiểm tra cách truyền cấu hình của phiên bản Swagger UI/Springdoc đang dùng; các giá trị chuỗi là lựa chọn đơn giản cho `application.yml`.

## 4. Điều khiển cách mở rộng danh sách operation

Thuộc tính `doc-expansion` quyết định các nhóm operation được mở ở mức nào khi trang tải:

```yaml
springdoc:
  swagger-ui:
    doc-expansion: none
```

Các giá trị thường dùng:

| Giá trị | Cách hiển thị |
| --- | --- |
| `list` | Mở danh sách tag, giữ nội dung operation thu gọn |
| `full` | Mở tag và operation |
| `none` | Thu gọn các nhóm operation ban đầu |

Với API có nhiều endpoint, `none` giúp trang tải gọn và người đọc mở đúng nhóm cần xem. Với API nhỏ hoặc trang demo, `list` có thể giúp người đọc thấy nhanh các endpoint sẵn có.

`doc-expansion` điều khiển trạng thái mở của danh sách operation. Nó không quyết định schema model bên dưới được mở rộng sâu đến đâu; phần đó do các tùy chọn model/schema riêng điều khiển.

## 5. Hiển thị model thay cho example

Trong request body, Swagger UI có thể hiển thị payload ví dụ hoặc cấu trúc model. Thuộc tính `default-model-rendering` điều khiển chế độ hiển thị mặc định:

```yaml
springdoc:
  swagger-ui:
    default-model-rendering: model
```

Hai giá trị chính:

- `example`: ưu tiên hiển thị ví dụ dữ liệu.
- `model`: ưu tiên hiển thị cấu trúc schema/model.

Ví dụ DTO:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Schema(description = "Thông tin sách cần tạo")
public record CreateBookRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(description = "Tên sách", example = "Spring Boot căn bản")
    String title,

    @Schema(description = "Năm xuất bản", example = "2025")
    Integer publicationYear
) {}
```

Khi hiển thị model, người đọc tập trung vào property, kiểu dữ liệu, mô tả và ràng buộc. Khi hiển thị example, họ thấy một payload cụ thể có thể dùng làm điểm bắt đầu cho request. Hai chế độ phục vụ mục đích khác nhau; người đọc vẫn có thể chuyển đổi chế độ trong giao diện nếu phiên bản Swagger UI hỗ trợ điều khiển đó.

`default-model-rendering` là tùy chọn trình bày. Nó không tạo example và không thay đổi schema OpenAPI. Muốn có payload mẫu, hãy khai báo `@Schema(example = ...)`, `@ExampleObject` hoặc metadata tương ứng.

## 6. Điều khiển độ sâu mở rộng của schema

Swagger UI có hai tùy chọn thường được dùng để kiểm soát độ sâu phần model:

- `default-models-expand-depth`: độ sâu mở rộng của danh sách model/schema.
- `default-model-expand-depth`: độ sâu mở rộng bên trong một model.

Ví dụ:

```yaml
springdoc:
  swagger-ui:
    default-models-expand-depth: 1
    default-model-expand-depth: 2
```

`default-models-expand-depth: -1` có thể dùng để ẩn hoàn toàn khu vực danh sách model/schema trong giao diện. Giá trị `1` thường giữ phần model ở mức mở rộng cơ bản. `default-model-expand-depth` kiểm soát mức hiển thị các thuộc tính lồng nhau khi mở một model.

Ví dụ schema lồng nhau:

```java
import java.util.List;

public record OrderResponse(
    Long id,
    CustomerSummary customer,
    List<OrderItemResponse> items
) {}

public record CustomerSummary(
    Long id,
    String displayName,
    AddressResponse address
) {}

public record AddressResponse(
    String city,
    String country
) {}

public record OrderItemResponse(
    Long productId,
    Integer quantity
) {}
```

Nếu model có nhiều cấp lồng nhau, mở sâu toàn bộ có thể làm trang dài và khó đọc. Đặt độ sâu vừa phải giúp người dùng xem cấu trúc chính trước, sau đó mở những object con cần thiết.

Các giá trị này điều khiển giao diện Swagger UI. Chúng không làm thay đổi số cấp schema trong OpenAPI, không cắt bỏ property và không thay đổi serialization của Jackson.

## 7. Hiển thị extension và constraint của schema

Swagger UI có các tùy chọn để hiển thị extension và một số thuộc tính schema:

```yaml
springdoc:
  swagger-ui:
    show-extensions: true
    show-common-extensions: true
```

- `show-extensions` bật hiển thị specification extension, ví dụ `x-audience` hoặc `x-internal`.
- `show-common-extensions` bật hiển thị một số extension phổ biến được Swagger UI nhận diện, chẳng hạn các thuộc tính bổ sung trong schema tùy phiên bản.

Các ràng buộc OpenAPI như `minLength`, `maxLength`, `minimum`, `maximum`, `minItems`, `maxItems`, `pattern`, `enum`, `format` và `required` được lấy từ schema. Swagger UI trình bày chúng để người đọc hiểu giới hạn dữ liệu. Nguồn dữ liệu vẫn là đặc tả OpenAPI do Springdoc sinh ra.

Ví dụ:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import io.swagger.v3.oas.annotations.media.Schema;

public record CreateProductRequest(
    @NotBlank
    @Size(min = 3, max = 80)
    @Schema(example = "Mechanical Keyboard")
    String name,

    @Min(1)
    @Max(100)
    Integer quantity
) {}
```

Schema có thể chứa `minLength`, `maxLength`, `minimum` và `maximum` nếu Springdoc nhận diện được constraint tương ứng. Nếu UI không hiển thị ràng buộc như mong muốn, hãy kiểm tra `/v3/api-docs` trước để xác định metadata có được sinh ra hay chưa.

## 8. Cấu hình Swagger UI tổng hợp

Một cấu hình cân bằng cho API có nhiều tag và schema có thể như sau:

```yaml
springdoc:
  swagger-ui:
    path: /swagger-ui.html
    filter: true
    tags-sorter: alpha
    operations-sorter: alpha
    doc-expansion: none
    default-model-rendering: model
    default-models-expand-depth: 1
    default-model-expand-depth: 2
    show-extensions: true
    show-common-extensions: true
```

Ý nghĩa của cấu hình:

1. Mở ô lọc tag để tìm nhóm API.
2. Sắp xếp tag và operation theo chữ cái.
3. Thu gọn operation khi tải trang để giảm độ dài ban đầu.
4. Ưu tiên xem schema model khi đọc request body.
5. Mở model ở độ sâu vừa phải.
6. Hiển thị extension và constraint mở rộng nếu đặc tả có chúng.

Không phải API nào cũng cần bật tất cả tùy chọn. Với API nhỏ, cấu hình mặc định có thể đã đủ. Hãy thử trên tài liệu thực tế và chọn thiết lập giúp người tích hợp tìm endpoint, hiểu schema và gửi request thuận tiện.

## 9. Kiểm tra tag, filter và schema trong Swagger UI

Sau khi ứng dụng khởi động, mở đường dẫn Swagger UI, thường là `/swagger-ui/index.html` hoặc đường dẫn được cấu hình qua `springdoc.swagger-ui.path`.

Quy trình kiểm tra:

1. Xác nhận danh sách tag xuất hiện với tên và mô tả mong muốn.
2. Nhập một phần tên tag vào ô Filter và quan sát các nhóm được thu hẹp.
3. Thử khác biệt chữ hoa/chữ thường để hiểu hành vi filter.
4. Xóa nội dung filter và xác nhận toàn bộ nhóm được hiển thị lại.
5. Mở một operation có request body và chuyển giữa example/model nếu giao diện hỗ trợ.
6. Mở phần Schemas và kiểm tra property, kiểu dữ liệu, mô tả, required, enum, format và constraint.
7. Mở schema lồng nhau để xác nhận độ sâu hiển thị phù hợp.
8. Nếu bật extension, kiểm tra các thuộc tính `x-...` xuất hiện như mong muốn.

Đồng thời mở `/v3/api-docs` hoặc `/v3/api-docs.yaml`. Nếu tag hoặc schema không có trong OpenAPI, thay đổi cấu hình giao diện không thể tự tạo ra chúng. Hãy sửa annotation/controller/DTO hoặc customizer sinh đặc tả trước.

## 10. Khi có nhiều tài liệu group

Springdoc có thể tạo nhiều tài liệu OpenAPI qua `GroupedOpenApi`. Swagger UI có thể hiển thị danh sách tài liệu để người đọc chọn group cần xem.

Ví dụ:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}

@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .build();
}
```

Khi người dùng chọn tài liệu `partner`, bộ lọc tag và phần hiển thị schema áp dụng trên tài liệu đang được mở. Người dùng cần chọn đúng group trước khi tìm operation.

Tên group và tên tag là hai khái niệm khác nhau:

- Group chọn một tài liệu OpenAPI riêng, ví dụ `public` hoặc `partner`.
- Tag phân loại operation bên trong tài liệu, ví dụ `Books`, `Orders` hoặc `Payments`.

Không dùng filter tag để thay thế việc chọn group. Nếu một operation không nằm trong tài liệu group đang mở, lọc tag sẽ không làm nó xuất hiện.

## 11. Bảo vệ tài liệu và nút Try it out

Swagger UI là giao diện đọc và thử API. Việc bật filter, ẩn schema hoặc thu gọn operation không phải biện pháp bảo mật. Nếu tài liệu chứa endpoint nội bộ, schema nhạy cảm hoặc thông tin kiến trúc, hãy kiểm soát quyền truy cập vào cả Swagger UI lẫn endpoint OpenAPI JSON/YAML.

Các hướng triển khai thường gặp:

- Dùng Spring Security để yêu cầu xác thực khi truy cập `/swagger-ui/**`, `/swagger-ui.html` và `/v3/api-docs/**`.
- Tắt Swagger UI hoặc endpoint tài liệu trong môi trường không cần công bố.
- Tạo group tài liệu phù hợp với từng đối tượng và bảo vệ endpoint group bằng chính sách truy cập.
- Không đưa token, password, private key hoặc dữ liệu production vào example/schema description.

Nếu muốn tắt khả năng gửi request từ giao diện, Swagger UI có tùy chọn `supported-submit-methods`. Có thể cấu hình danh sách rỗng:

```yaml
springdoc:
  swagger-ui:
    supported-submit-methods: []
```

Thiết lập này tắt nút gửi request (`Try it out`) trong giao diện theo cấu hình Swagger UI. Nó không chặn HTTP request đến API; quyền truy cập và chính sách runtime vẫn phải được bảo vệ ở server hoặc gateway.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thấy ô Filter | `springdoc.swagger-ui.filter` chưa bật hoặc cấu hình chưa được nạp | Đặt `filter: true`, kiểm tra profile và tải lại UI |
| Filter không tìm thấy summary/description | Filter tích hợp tập trung vào tag | Dùng tên tag nhất quán; dùng browser find hoặc công cụ tìm kiếm riêng cho nội dung toàn văn |
| Filter phân biệt chữ hoa/chữ thường | Hành vi filter mặc định là case-sensitive | Nhập đúng tên tag hoặc chuẩn hóa quy ước đặt tag |
| Tag bị chia thành nhiều nhóm gần giống nhau | Tên tag không nhất quán | Chuẩn hóa tên tag và dùng `@Tag` tập trung |
| Schema không hiển thị property mong muốn | DTO hoặc OpenAPI schema không chứa property đó | Kiểm tra `/v3/api-docs`, Jackson visibility và `@Schema` |
| Schema bị thu gọn quá sâu | `default-models-expand-depth` hoặc `default-model-expand-depth` thấp | Tăng độ sâu phù hợp hoặc để người đọc mở thủ công |
| Không thấy khu vực Schemas | `default-models-expand-depth` đặt `-1` | Đặt lại giá trị lớn hơn hoặc bằng `0` |
| Chỉ thấy example, không thấy cấu trúc model | `default-model-rendering` đang là `example` | Đặt `default-model-rendering: model` |
| Extension không xuất hiện | Chưa bật `show-extensions` hoặc OpenAPI không chứa extension | Bật tùy chọn và kiểm tra JSON/YAML |
| Cấu hình YAML không có tác dụng | Sai tên property, profile hoặc phiên bản thư viện | Kiểm tra cấu hình Spring Boot đã bind và phiên bản Springdoc |
| Tài liệu bị lộ dù đã ẩn tag/schema | Nhầm tùy chọn giao diện với bảo mật | Bảo vệ endpoint tài liệu bằng Spring Security hoặc cấu hình môi trường |

## 13. Checklist cho tìm kiếm, lọc và hiển thị schema

- [ ] Đã bật `springdoc.swagger-ui.filter` nếu cần ô lọc tag.
- [ ] Tên tag ngắn gọn, nhất quán và mô tả đúng nhóm operation.
- [ ] Đã chọn `tags-sorter` và `operations-sorter` nếu cần sắp xếp.
- [ ] `doc-expansion` phù hợp với số lượng operation.
- [ ] `default-model-rendering` phù hợp với nhu cầu xem example hoặc schema.
- [ ] `default-models-expand-depth` và `default-model-expand-depth` không làm ẩn nội dung cần đọc.
- [ ] Đã bật `show-extensions` nếu tài liệu dùng extension `x-...`.
- [ ] Đã kiểm tra schema, property, required, format, enum và constraint trong `/v3/api-docs`.
- [ ] Đã thử filter tag và mở model trên Swagger UI thực tế.
- [ ] Đã chọn đúng group trước khi tìm operation.
- [ ] Tài liệu được bảo vệ bằng chính sách truy cập phù hợp; không dựa vào việc ẩn UI.
- [ ] Đã tắt `Try it out` nếu môi trường chỉ cho phép đọc tài liệu.

Filter của Swagger UI giúp người đọc thu hẹp operation theo tag; các tùy chọn model/schema điều khiển cách hiển thị cấu trúc và ví dụ. Khi tag được tổ chức nhất quán, schema có mô tả đầy đủ và giao diện được cấu hình hợp lý, người tích hợp có thể tìm endpoint nhanh hơn và hiểu rõ dữ liệu cần gửi hoặc nhận.

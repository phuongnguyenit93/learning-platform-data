# externalDocs và liên kết đến tài liệu bổ sung

Một đặc tả OpenAPI mô tả cách gọi API, cấu trúc request/response và các phản hồi có thể nhận. Tuy nhiên, một số thông tin cần thiết cho người tích hợp nằm ngoài hợp đồng HTTP: hướng dẫn nghiệp vụ, quy trình onboarding, quy ước phân trang, từ điển dữ liệu, ví dụ end-to-end hoặc tài liệu vận hành. OpenAPI cung cấp đối tượng `externalDocs` để gắn liên kết tới những nguồn tham khảo đó ngay tại vị trí phù hợp trong tài liệu.

Với `springdoc-openapi`, có thể khai báo `externalDocs` bằng annotation của swagger-core hoặc cấu hình mô hình OpenAPI bằng Java. Springdoc đưa thông tin này vào JSON/YAML được sinh để người đọc và công cụ hiển thị có thể theo liên kết tới tài liệu chi tiết.

## 1. External Documentation Object là gì?

`externalDocs` là một đối tượng tài liệu tham khảo có cấu trúc đơn giản:

| Trường | Bắt buộc | Ý nghĩa |
| --- | --- | --- |
| `url` | Có | URL của tài liệu bổ sung. |
| `description` | Không | Mô tả ngắn về nội dung hoặc mục đích của liên kết. |

Ví dụ:

```yaml
externalDocs:
  description: Hướng dẫn tích hợp Order API
  url: https://docs.example.com/order-api/guide
```

`externalDocs` chỉ công bố một liên kết và mô tả của liên kết đó. Nó không nhúng nội dung trang web vào đặc tả, không kiểm tra người đọc có quyền truy cập URL hay không và không bảo đảm tài liệu đích còn tồn tại. Việc mở liên kết phụ thuộc trình xem OpenAPI, trình duyệt và chính sách truy cập của hệ thống đích.

Trường `description` có thể dùng văn bản Markdown/CommonMark theo hỗ trợ của OpenAPI và công cụ hiển thị. Hãy viết mô tả ngắn, nêu rõ người đọc sẽ tìm thấy gì ở liên kết. URL phải là giá trị tuyệt đối hợp lệ theo hợp đồng, thường nên dùng HTTPS.

## 2. Chọn đúng vị trí gắn externalDocs

OpenAPI cho phép đặt `externalDocs` ở một số cấp khác nhau. Chọn cấp theo phạm vi áp dụng của tài liệu:

| Vị trí | Phạm vi | Ví dụ tài liệu nên liên kết |
| --- | --- | --- |
| OpenAPI Object (gốc tài liệu) | Toàn bộ API | Cẩm nang tích hợp, chính sách chung, trang developer portal |
| Tag Object | Một nhóm operation | Hướng dẫn nghiệp vụ đơn hàng, khách hàng hoặc thanh toán |
| Operation Object | Một operation cụ thể | Hướng dẫn xử lý webhook, quy trình hoàn tiền, ví dụ gọi endpoint |
| Schema Object | Một kiểu dữ liệu | Từ điển dữ liệu, quy ước mã trạng thái, mô tả cấu trúc phức tạp |

Ví dụ, tài liệu chung của dịch vụ nên được đặt ở cấp gốc; hướng dẫn riêng cho nhóm `Orders` nên gắn với tag; hướng dẫn gửi idempotency key cho thao tác tạo đơn nên gắn với operation; quy ước chi tiết của `Money` nên gắn với schema.

Không nên đặt mọi liên kết ở cấp gốc nếu chúng chỉ liên quan đến một endpoint hoặc một kiểu dữ liệu. Gắn liên kết gần nơi người đọc cần nó giúp tài liệu dễ tìm và giảm sự mơ hồ.

## 3. Khai báo externalDocs ở cấp toàn bộ API

Đối với liên kết chung của dịch vụ, dùng thuộc tính `externalDocs` trong `@OpenAPIDefinition`:

```java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "v1",
        description = "API quản lý đơn hàng"
    ),
    externalDocs = @ExternalDocumentation(
        description = "Cẩm nang tích hợp, xác thực và quy ước chung",
        url = "https://docs.example.com/order-api/guide"
    )
)
class OpenApiDocumentationConfig {
}
```

Khi springdoc tạo tài liệu, liên kết chung xuất hiện ở cấp gốc của OpenAPI document:

```yaml
openapi: 3.1.0
info:
  title: Order API
  version: v1
  description: API quản lý đơn hàng
externalDocs:
  description: Cẩm nang tích hợp, xác thực và quy ước chung
  url: https://docs.example.com/order-api/guide
```

Phiên bản `openapi` trong ví dụ chỉ minh họa phần đầu tài liệu; phiên bản đặc tả thực tế được springdoc cấu hình và sinh ra theo phiên bản tương thích của dự án.

## 4. Gắn liên kết vào tag để hướng dẫn theo nhóm API

Tag gom các operation có cùng chủ đề. Có thể mô tả tài liệu bổ sung ngay trên tag trong `@OpenAPIDefinition`:

```java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.tags.Tag;

@OpenAPIDefinition(
    tags = {
        @Tag(
            name = "Orders",
            description = "Các thao tác quản lý đơn hàng",
            externalDocs = @ExternalDocumentation(
                description = "Quy trình và trạng thái vòng đời đơn hàng",
                url = "https://docs.example.com/order-api/orders/lifecycle"
            )
        )
    }
)
class OrderApiTagsConfig {
}
```

Controller có thể sử dụng cùng tên tag để gắn operation vào nhóm:

```java
import io.swagger.v3.oas.annotations.tags.Tag;

@RestController
@RequestMapping("/api/orders")
@Tag(name = "Orders")
class OrderController {
    // Các endpoint của nhóm Orders
}
```

Trong YAML sinh ra, đối tượng tag có thể chứa `externalDocs`:

```yaml
tags:
  - name: Orders
    description: Các thao tác quản lý đơn hàng
    externalDocs:
      description: Quy trình và trạng thái vòng đời đơn hàng
      url: https://docs.example.com/order-api/orders/lifecycle
```

Tên tag phải nhất quán giữa metadata khai báo và operation. Nếu tên tag khác nhau do sai chính tả hoặc cách viết, giao diện có thể tạo thành các nhóm riêng và liên kết không xuất hiện ở nhóm mong muốn.

## 5. Gắn liên kết vào operation cụ thể

Khi tài liệu chỉ áp dụng cho một thao tác, dùng `externalDocs` trong `@Operation`:

```java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@Operation(
    summary = "Tạo đơn hàng",
    description = "Tạo một đơn hàng mới từ giỏ hàng đã xác nhận.",
    externalDocs = @ExternalDocumentation(
        description = "Ví dụ tạo đơn, quy tắc idempotency và xử lý lỗi",
        url = "https://docs.example.com/order-api/orders/create"
    )
)
@PostMapping
OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
```

Đặc tả sinh ra đặt liên kết trong operation tương ứng:

```yaml
paths:
  /api/orders:
    post:
      summary: Tạo đơn hàng
      description: Tạo một đơn hàng mới từ giỏ hàng đã xác nhận.
      externalDocs:
        description: Ví dụ tạo đơn, quy tắc idempotency và xử lý lỗi
        url: https://docs.example.com/order-api/orders/create
```

Liên kết ở operation hữu ích khi người đọc cần thêm quy trình hoặc ví dụ vượt ra ngoài phần mô tả ngắn của endpoint. Các thông tin bắt buộc để gọi API như parameter, request body, response và security vẫn phải được mô tả trực tiếp trong OpenAPI; không nên buộc client mở một trang ngoài mới biết tên field hoặc mã HTTP cơ bản.

## 6. Gắn liên kết vào schema

Một số kiểu dữ liệu cần giải thích sâu hơn mức có thể trình bày trong `description`. Dùng `externalDocs` trong `@Schema` để dẫn tới từ điển dữ liệu hoặc quy ước miền:

```java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;

@Schema(
    name = "Money",
    description = "Giá trị tiền tệ với số tiền và mã tiền tệ",
    externalDocs = @ExternalDocumentation(
        description = "Quy ước số thập phân, làm tròn và mã tiền tệ",
        url = "https://docs.example.com/data-models/money"
    )
)
public record Money(
    @Schema(description = "Giá trị tiền", example = "125000.00")
    BigDecimal amount,

    @Schema(description = "Mã tiền tệ", example = "VND")
    String currency
) {
}
```

Phần schema tương ứng có thể được biểu diễn như sau:

```yaml
components:
  schemas:
    Money:
      type: object
      description: Giá trị tiền tệ với số tiền và mã tiền tệ
      externalDocs:
        description: Quy ước số thập phân, làm tròn và mã tiền tệ
        url: https://docs.example.com/data-models/money
      properties:
        amount:
          type: number
          example: 125000.00
        currency:
          type: string
          example: VND
```

Nếu một schema được tái sử dụng ở nhiều operation, liên kết gắn ở schema sẽ đi cùng kiểu dữ liệu đó trong các vị trí tham chiếu. Điều này phù hợp với tài liệu giải thích ý nghĩa và quy ước chung của model.

## 7. Cấu hình bằng OpenAPI bean

Trong dự án cần tạo tài liệu theo điều kiện hoặc tập trung cấu hình bằng Java, có thể thiết lập `ExternalDocumentation` trên model `OpenAPI`:

```java
import io.swagger.v3.oas.models.ExternalDocumentation;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiModelConfig {

    @Bean
    OpenAPI orderOpenAPI() {
        ExternalDocumentation docs = new ExternalDocumentation()
            .description("Cẩm nang tích hợp Order API")
            .url("https://docs.example.com/order-api/guide");

        return new OpenAPI()
            .info(new Info().title("Order API").version("v1"))
            .externalDocs(docs);
    }
}
```

Model `ExternalDocumentation` thuộc package `io.swagger.v3.oas.models`; annotation `@ExternalDocumentation` thuộc package `io.swagger.v3.oas.annotations`. Hai kiểu này có mục đích tương tự nhưng được dùng ở hai cách cấu hình khác nhau. Không nhầm import giữa chúng.

Có thể kết hợp bean OpenAPI với annotation ở controller/model, nhưng nên tổ chức cấu hình có chủ đích và kiểm tra tài liệu cuối cùng để tránh metadata bị khai báo trùng hoặc bị ghi đè ngoài dự kiến. Chọn một nguồn cấu hình chính cho liên kết cấp gốc; giữ annotation gần controller hoặc DTO cho liên kết đặc thù của operation/schema.

## 8. Dùng nhiều liên kết và tổ chức tài liệu đích

External Documentation Object có một trường `url`. Nếu một operation cần trỏ tới nhiều trang, có thể chọn một trang tổng hợp làm liên kết chính; trang đó chứa các liên kết con tới ví dụ, quy trình và FAQ. Phần `description` cũng có thể ghi Markdown link khi trình xem hỗ trợ CommonMark.

Ví dụ:

```yaml
externalDocs:
  description: |
    Xem [hướng dẫn tích hợp](https://docs.example.com/order-api/guide),
    [ví dụ mã nguồn](https://github.com/example/order-api-samples)
    và [FAQ](https://docs.example.com/order-api/faq).
  url: https://docs.example.com/order-api/guide
```

Để liên kết hữu ích và bền vững:

- Ưu tiên URL HTTPS công khai hoặc URL nội bộ có quy trình truy cập rõ ràng.
- Dùng URL ổn định, tránh liên kết tới trang preview, URL có token, session id hoặc thông tin nhạy cảm.
- Nếu tài liệu thay đổi theo phiên bản API, đặt phiên bản trong đường dẫn hoặc dùng trang điều hướng có hỗ trợ phiên bản.
- Mô tả đích đến cụ thể, ví dụ “Quy tắc retry và idempotency”, thay vì “Xem thêm”.
- Bảo đảm người dùng Swagger UI và công cụ đọc OpenAPI có thể truy cập tài liệu đích theo chính sách của tổ chức.
- Kiểm tra liên kết định kỳ trong quy trình tài liệu hoặc CI để phát hiện URL hỏng.

Không đưa bí mật hoặc thông tin xác thực vào URL. OpenAPI có thể được chia sẻ rộng hơn tài liệu nội bộ, nên cần xem xét quyền truy cập và phân loại dữ liệu trước khi công bố liên kết.

## 9. Kiểm tra externalDocs trong tài liệu được sinh

Sau khi cấu hình, kiểm tra JSON hoặc YAML thực tế do springdoc xuất ra. Mặc định, endpoint thường là `/v3/api-docs` và `/v3/api-docs.yaml`; đường dẫn có thể đã được tùy chỉnh trong cấu hình ứng dụng.

Ví dụ dùng `curl` để lấy tài liệu:

```bash
curl -sS http://localhost:8080/v3/api-docs
curl -sS http://localhost:8080/v3/api-docs.yaml
```

Trong kết quả, kiểm tra từng vị trí đã cấu hình:

- Trường `externalDocs` ở cấp gốc có đúng URL cẩm nang chung không.
- Phần tử trong `tags` có đúng tên tag, mô tả và URL không.
- Operation dưới `paths` có liên kết đúng với endpoint không.
- Schema dưới `components.schemas` có liên kết đúng với model không.
- Các URL có đầy đủ `https://`, không bị cắt, escape sai hoặc trỏ nhầm môi trường không.

Nếu annotation không xuất hiện trong đặc tả, hãy kiểm tra import annotation, vị trí đặt annotation, class/method có được springdoc quét hay không và phiên bản swagger-core đi cùng springdoc. Nếu YAML có URL nhưng giao diện không mở được, thử URL trực tiếp trên trình duyệt và kiểm tra DNS, chứng chỉ TLS, quyền truy cập hoặc redirect của hệ thống tài liệu.

## 10. Phân biệt externalDocs với các cơ chế liên kết khác

| Cơ chế | Vai trò | Khi nào dùng |
| --- | --- | --- |
| `description` | Giải thích trực tiếp API hoặc schema | Thông tin ngắn người đọc cần ngay trong hợp đồng |
| `externalDocs` | Liên kết tới một tài liệu tham khảo bên ngoài | Hướng dẫn chi tiết, quy trình, từ điển dữ liệu |
| `$ref` | Tái sử dụng một thành phần OpenAPI/schema trong đặc tả | Chia sẻ model, parameter hoặc response giữa nhiều nơi |
| `servers` | Khai báo URL máy chủ API để client gửi request | Phân biệt môi trường hoặc base URL |
| `tags` | Nhóm các operation theo chủ đề | Tổ chức giao diện và danh mục API |

`externalDocs` không thay thế `$ref`: một liên kết tới trang giải thích model không tạo ra schema mà client có thể dùng để sinh mã. Tương tự, `externalDocs.url` không phải URL máy chủ để gửi request; URL máy chủ được khai báo trong `servers`.

## 11. Quy trình áp dụng

Khi bổ sung liên kết tài liệu cho một API, thực hiện theo các bước:

1. Xác định người đọc cần tài liệu bổ sung ở cấp nào: toàn API, tag, operation hay schema.
2. Chọn trang đích ổn định, có phiên bản và quyền truy cập phù hợp.
3. Viết `description` nêu cụ thể nội dung người đọc sẽ tìm thấy.
4. Khai báo bằng `@OpenAPIDefinition`, `@Tag`, `@Operation`, `@Schema` hoặc OpenAPI bean tương ứng.
5. Lấy `/v3/api-docs` hoặc file YAML để xác minh `externalDocs` nằm đúng vị trí.
6. Mở từng URL từ môi trường người dùng tài liệu và kiểm tra quyền truy cập.

Ví dụ, tài liệu tổng quan của Order API đặt ở cấp gốc; hướng dẫn vòng đời đơn hàng gắn với tag `Orders`; quy tắc idempotency gắn với operation tạo đơn; từ điển dữ liệu tiền tệ gắn với schema `Money`. Mỗi liên kết giúp người đọc đi sâu đúng chủ đề mà không làm hợp đồng HTTP trở nên khó đọc.

## Tài liệu tham khảo

- [OpenAPI Specification – External Documentation Object](https://spec.openapis.org/oas/latest.html#external-documentation-object)
- [OpenAPI Specification – OpenAPI Object](https://spec.openapis.org/oas/latest.html#openapi-object)
- [Swagger Core Annotations – GitHub](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
- [springdoc-openapi – Documentation](https://springdoc.org/)

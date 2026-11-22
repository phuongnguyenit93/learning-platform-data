# Đường dẫn tài liệu bổ sung và quy ước giữ ví dụ không chứa bí mật

Tài liệu OpenAPI nên giúp người tích hợp hiểu cách gọi API và biết nơi tìm hướng dẫn sâu hơn. Springdoc cho phép gắn liên kết tài liệu bên ngoài vào đặc tả bằng `@ExternalDocumentation`; đồng thời, `@ExampleObject`, `@Schema` và `@Parameter` giúp minh họa request, response và giá trị tham số. Các liên kết cần ổn định, có ngữ cảnh và trỏ đến đúng phiên bản tài liệu. Các ví dụ phải dùng dữ liệu giả lập, không chứa token, mật khẩu, khóa API hoặc dữ liệu cá nhân thật.

Một liên kết tài liệu tốt giúp người đọc tìm được quy trình tích hợp, chính sách lỗi, quy tắc phân trang hoặc hướng dẫn xác thực. Một ví dụ tốt giúp họ gửi đúng định dạng dữ liệu. Cả hai đều là một phần của trải nghiệm hợp đồng API và cần được duy trì như nội dung kỹ thuật có phiên bản.

## 1. Khi nào cần liên kết tài liệu bổ sung?

OpenAPI mô tả cấu trúc và hành vi HTTP của API. Tuy nhiên, một số nội dung có thể cần giải thích dài hơn hoặc thay đổi độc lập với schema:

- Hướng dẫn bắt đầu tích hợp và các bước cấu hình client.
- Quy trình cấp, gia hạn và thu hồi thông tin xác thực.
- Quy tắc nghiệp vụ, trạng thái đơn hàng hoặc vòng đời tài nguyên.
- Quy ước phân trang, lọc, sắp xếp và giới hạn tốc độ.
- Quy tắc retry, idempotency và xử lý lỗi.
- Hướng dẫn migration giữa các phiên bản API.
- Tài liệu webhook, callback hoặc sự kiện bất đồng bộ.

Không nên chép toàn bộ hướng dẫn dài vào `description` của operation. Hãy giữ mô tả OpenAPI ngắn, tập trung vào hợp đồng và gắn liên kết đến trang giải thích chi tiết khi người đọc cần thêm bối cảnh.

## 2. `@ExternalDocumentation` ở cấp toàn bộ tài liệu

`@ExternalDocumentation` thuộc package `io.swagger.v3.oas.annotations`. Có thể khai báo nó trong `@OpenAPIDefinition` để gắn một đường dẫn tham khảo chung cho toàn bộ API:

```java
package com.example.books.config;

import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Books API",
        version = "1.0.0",
        description = "API tra cứu và quản lý sách"
    ),
    externalDocs = @ExternalDocumentation(
        description = "Hướng dẫn tích hợp và quy tắc sử dụng Books API",
        url = "https://docs.example.com/books-api/1.0/guide"
    )
)
public class OpenApiDocumentationConfig {}
```

Trong ví dụ:

- `description` giải thích trang đích chứa nội dung gì.
- `url` là địa chỉ đầy đủ của tài liệu bên ngoài.
- `@OpenAPIDefinition` đặt liên kết ở cấp tài liệu, nên nó áp dụng cho API nói chung.

Địa chỉ `example.com` chỉ là tên miền minh họa. Khi triển khai, thay bằng URL HTTPS đã được tổ chức phê duyệt và có người chịu trách nhiệm duy trì.

Trong đặc tả OpenAPI, liên kết này xuất hiện ở thuộc tính `externalDocs` cấp gốc:

```yaml
openapi: 3.0.3
info:
  title: Books API
  version: 1.0.0
externalDocs:
  description: Hướng dẫn tích hợp và quy tắc sử dụng Books API
  url: https://docs.example.com/books-api/1.0/guide
```

`externalDocs` chỉ tạo metadata liên kết. Springdoc không tạo trang tài liệu đó, không kiểm tra quyền truy cập và không bảo đảm URL luôn hoạt động.

## 3. Liên kết tài liệu tại operation hoặc tag

Không phải mọi hướng dẫn đều áp dụng cho toàn bộ API. Có thể gắn liên kết ở phạm vi cụ thể để người đọc tìm được tài liệu liên quan ngay tại operation hoặc nhóm chức năng.

### Liên kết tại operation bằng `@Operation`

```java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PaymentController {

    @PostMapping("/api/payments")
    @Operation(
        summary = "Tạo yêu cầu thanh toán",
        description = "Khởi tạo một giao dịch thanh toán cho đơn hàng",
        externalDocs = @ExternalDocumentation(
            description = "Quy trình thanh toán, idempotency và xử lý trạng thái",
            url = "https://docs.example.com/payments/1.0/create-payment"
        )
    )
    public PaymentResponse create(@RequestBody PaymentRequest request) {
        // Xử lý nghiệp vụ thanh toán.
        return new PaymentResponse("pending");
    }
}
```

Liên kết operation phù hợp khi tài liệu chỉ giải thích một thao tác, ví dụ quy trình xác nhận thanh toán hoặc cách xử lý một trạng thái đặc biệt.

### Liên kết tại tag bằng `@Tag`

```java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
@Tag(
    name = "Orders",
    description = "Tra cứu và quản lý đơn hàng",
    externalDocs = @ExternalDocumentation(
        description = "Vòng đời và các trạng thái đơn hàng",
        url = "https://docs.example.com/orders/1.0/lifecycle"
    )
)
public class OrderController {}
```

Liên kết ở tag phù hợp khi nhiều operation cùng chia sẻ một quy trình hoặc quy tắc nghiệp vụ. Tên tag nên ổn định và mô tả của liên kết cần nói rõ nội dung trang đích.

### Chọn đúng phạm vi

| Phạm vi | Vị trí khai báo | Dùng khi |
| --- | --- | --- |
| Toàn API | `@OpenAPIDefinition(externalDocs = ...)` | Có một cổng tài liệu hoặc hướng dẫn chung |
| Một nhóm operation | `@Tag(externalDocs = ...)` | Các endpoint trong cùng miền có chung quy trình |
| Một operation | `@Operation(externalDocs = ...)` | Một thao tác cần hướng dẫn riêng |

Tránh gắn cùng một URL lặp lại ở mọi operation nếu một liên kết cấp tài liệu hoặc tag đã đủ. Đặt liên kết tại nơi người đọc có thể dự đoán và tìm thấy nó.

## 4. Phân biệt `externalDocs` với các loại liên kết khác

OpenAPI có nhiều cấu trúc chứa URL nhưng chúng phục vụ mục đích khác nhau:

| Thành phần | Ý nghĩa |
| --- | --- |
| `externalDocs` | Liên kết đến tài liệu giải thích thêm về API, tag hoặc operation |
| `servers` | Địa chỉ gốc để client gửi HTTP request |
| `info.termsOfService` | URL điều khoản sử dụng dịch vụ |
| `info.contact` | Thông tin liên hệ hỗ trợ |
| `@Link` / Link Object | Mô tả liên kết từ một response đến operation khác hoặc giá trị đầu vào của operation đó |
| `@ExampleObject.externalValue` | URL đến nội dung ví dụ được lưu bên ngoài |

Ví dụ, URL `https://api.example.com` là server để gọi API; URL `https://docs.example.com/books/guide` là tài liệu bổ sung. Không dùng `externalDocs` để thay thế `servers`, và không dùng `servers` làm nơi trỏ đến trang hướng dẫn.

`@Link` cũng không giống `@ExternalDocumentation`. Link Object mô tả mối liên hệ điều hướng giữa các operation theo response, chẳng hạn từ kết quả tạo đơn hàng đến thao tác xem đơn hàng. Nó không đơn thuần là một URL đến trang hướng dẫn.

## 5. Dùng `@ExampleObject` cho ví dụ inline

Ví dụ inline phù hợp với payload ngắn, ổn định và hữu ích ngay trong Swagger UI. Có thể khai báo ví dụ trong `@Content` của request hoặc response:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.RequestBody;

@Operation(
    summary = "Tạo sách",
    requestBody = @RequestBody(
        required = true,
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = CreateBookRequest.class),
            examples = {
                @ExampleObject(
                    name = "BasicBook",
                    summary = "Sách cơ bản",
                    description = "Payload tối thiểu để tạo sách",
                    value = "{\"title\":\"Spring Boot căn bản\",\"publicationYear\":2025}"
                ),
                @ExampleObject(
                    name = "BookWithoutYear",
                    summary = "Sách chưa có năm xuất bản",
                    value = "{\"title\":\"REST API thực hành\"}"
                )
            }
        )
    )
)
```

`name` là định danh ví dụ; `summary` và `description` giải thích tình huống; `value` chứa payload mẫu. Ví dụ cần hợp lệ với schema và phản ánh dữ liệu mà API thực sự chấp nhận.

Với parameter, có thể dùng `@Parameter(example = ...)` hoặc `@Parameter(examples = ...)` tùy nhu cầu. Với một giá trị field trong DTO, dùng `@Schema(example = ...)`. Hãy chọn đúng vị trí để ví dụ hiển thị gắn với phần dữ liệu mà người đọc đang xem.

## 6. Dùng `externalValue` khi ví dụ được lưu ở tệp riêng

Nếu ví dụ lớn, có nhiều dòng hoặc được dùng chung ở nhiều nơi, có thể lưu nội dung ở một URL công khai ổn định rồi tham chiếu bằng `@ExampleObject(externalValue = ...)`:

```java
@Content(
    mediaType = "application/json",
    schema = @Schema(implementation = BulkImportRequest.class),
    examples = @ExampleObject(
        name = "BulkImport",
        summary = "Ví dụ nhập nhiều bản ghi",
        externalValue = "https://docs.example.com/examples/books/bulk-import-v1.json"
    )
)
```

Trong OpenAPI, Example Object có thể dùng `value` hoặc `externalValue`. Hai thuộc tính này là hai cách cung cấp nội dung ví dụ; không nên khai báo đồng thời cho cùng một ví dụ. `externalValue` trỏ đến nội dung ví dụ ở bên ngoài, còn `value` nhúng payload trực tiếp trong tài liệu.

Khi dùng `externalValue`, hãy lưu ý:

- URL phải truy cập được bởi công cụ hoặc người đọc tài liệu cần tải ví dụ.
- Tệp phải có định dạng và nội dung phù hợp với media type đã khai báo.
- Nên dùng HTTPS và URL có version hoặc đường dẫn bất biến.
- Một số công cụ hiển thị OpenAPI có thể không tải hoặc không hiển thị external example giống nhau; hãy kiểm tra Swagger UI và công cụ client mục tiêu.
- Nếu ví dụ nhỏ, quan trọng hoặc cần hiển thị ổn định offline, inline `value` thường dễ kiểm soát hơn.

Không đặt `externalValue` trỏ đến URL cần token truy cập, URL có chữ ký tạm thời hoặc địa chỉ chứa thông tin bí mật trong query string. Đường dẫn công khai không nên trở thành một cách phát tán thông tin xác thực.

## 7. Quy ước tạo dữ liệu ví dụ an toàn

Mọi ví dụ trong OpenAPI có thể được sao chép vào ticket, tài liệu, log, mã nguồn client hoặc môi trường thử nghiệm. Hãy giả định nội dung ví dụ có thể được chia sẻ rộng rãi.

Không đưa các loại dữ liệu sau vào ví dụ:

- Mật khẩu, mã PIN, câu trả lời bảo mật hoặc thông tin đăng nhập.
- Access token, refresh token, JWT thật, API key, client secret hoặc private key.
- Cookie phiên, session ID, mã reset mật khẩu hoặc mã xác minh còn hiệu lực.
- Thông tin cá nhân thật như họ tên gắn với email/số điện thoại, địa chỉ, ngày sinh hoặc mã định danh.
- Dữ liệu thanh toán thật, số thẻ, CVV, tài khoản ngân hàng hoặc thông tin giao dịch có thể truy ngược người dùng.
- Tên miền nội bộ, IP riêng, hostname môi trường, đường dẫn hệ thống, tên bucket hoặc mã tài nguyên nhạy cảm.
- Dữ liệu log hoặc payload được sao chép từ production mà chưa được làm sạch.

Thay bằng dữ liệu giả lập có thể nhận biết là ví dụ:

| Trường hợp | Giá trị nên dùng trong tài liệu |
| --- | --- |
| Email | `lan.nguyen@example.com` |
| Tên miền minh họa | `api.example.com` hoặc `docs.example.com` |
| Số điện thoại | Dùng chuỗi placeholder rõ ràng như `+84-000-000-000` nếu schema chỉ cần minh họa định dạng |
| Token | `tok_test_example_only` hoặc `<your-access-token>` trong phần hướng dẫn văn bản |
| API key | `YOUR_API_KEY` hoặc `REPLACE_WITH_TEST_KEY` |
| Mã người dùng | `user_demo_001` |
| Địa chỉ | Địa chỉ hư cấu được ghi rõ là dữ liệu mẫu |
| Thẻ thanh toán | Token giả lập do sandbox của nhà cung cấp công bố; không dùng số thẻ thật ngoài bộ dữ liệu thử nghiệm chính thức |

Nếu cần ví dụ có hình dạng giống token hoặc định danh, hãy dùng giá trị vô hiệu và ghi rõ đó là placeholder. Không tạo một chuỗi trông như credential hợp lệ rồi để người đọc nhầm là có thể dùng để xác thực.

## 8. Ví dụ an toàn cho header xác thực

Không đặt token thật trong `@ExampleObject`, `@Parameter(example = ...)` hoặc `@Schema(example = ...)`. Với Bearer authentication, nên mô tả cách xác thực bằng security scheme:

```java
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;

@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
```

Ở operation cần xác thực, dùng `@SecurityRequirement(name = "bearerAuth")`. Người dùng nhập token của môi trường họ đang sử dụng qua nút **Authorize** của Swagger UI. Tài liệu không cần chứa một token mẫu có thể bị dùng lại.

Nếu muốn minh họa cú pháp HTTP trong phần hướng dẫn, dùng placeholder:

```http
Authorization: Bearer <your-access-token>
```

Đây là văn bản hướng dẫn, không phải credential có thể sử dụng. Trong schema hoặc ví dụ JSON, có thể dùng chuỗi `YOUR_TEST_TOKEN` nếu field chỉ cần minh họa định dạng, đồng thời ghi rõ client phải thay bằng token do hệ thống cấp.

Không đặt token vào query parameter hoặc URL để minh họa. URL thường xuất hiện trong browser history, proxy log, analytics và log máy chủ; credential trong URL dễ bị lưu hoặc chia sẻ ngoài ý muốn.

## 9. Ví dụ an toàn cho dữ liệu cá nhân và thanh toán

Ví dụ request tạo hồ sơ có thể dùng dữ liệu hư cấu:

```json
{
  "displayName": "Lan Nguyen",
  "email": "lan.nguyen@example.com",
  "phone": "+84-000-000-000"
}
```

Địa chỉ email dùng miền `example.com` dành cho minh họa. Số điện thoại là placeholder, không đại diện một thuê bao thật. Nếu tài liệu cần dữ liệu có định dạng chính xác cho một quốc gia, hãy chọn dải số dành riêng cho thử nghiệm theo quy định hoặc hướng dẫn chính thức của hệ thống.

Ví dụ thanh toán nên dùng token sandbox giả lập:

```json
{
  "paymentMethod": {
    "kind": "card",
    "token": "tok_test_example_only",
    "last4": "4242"
  }
}
```

Chỉ dùng số thẻ thử nghiệm do cổng thanh toán cung cấp trong tài liệu sandbox chính thức. Không tự sao chép thông tin thẻ từ giao dịch thật vào ví dụ, kể cả khi đã che một vài chữ số.

## 10. Quản lý đường dẫn tài liệu theo phiên bản

API có thể có nhiều phiên bản cùng tồn tại. Liên kết tài liệu nên giúp người dùng biết họ đang đọc hợp đồng nào:

```text
https://docs.example.com/books-api/1.0/guide
https://docs.example.com/books-api/2.0/guide
```

Một số quy tắc hữu ích:

1. **Đưa phiên bản vào đường dẫn khi nội dung phụ thuộc phiên bản API.** Điều này giúp client cũ tiếp tục dùng đúng tài liệu.
2. **Giữ URL cũ hoạt động trong thời gian hỗ trợ.** Nếu chuyển trang, dùng redirect ổn định và cập nhật liên kết trong OpenAPI.
3. **Tránh liên kết đến trang “latest” cho quy tắc có thể thay đổi.** Trang latest phù hợp với hướng dẫn chung, nhưng tài liệu hợp đồng nên gắn với phiên bản cụ thể.
4. **Dùng URL HTTPS và tên miền chính thức.** Không trỏ tài liệu public đến hostname nội bộ hoặc môi trường cá nhân.
5. **Đặt chủ sở hữu cho mỗi liên kết.** Nhóm phát triển hoặc nhóm tài liệu cần biết ai cập nhật trang khi API đổi.
6. **Kiểm tra trang đích khi phát hành.** URL đúng cú pháp nhưng trả 404, yêu cầu quyền nội bộ hoặc hiển thị nội dung cũ vẫn là liên kết lỗi.

Nếu API có tài liệu cho từng nhóm chức năng, có thể dùng đường dẫn riêng như `/orders/1.0/lifecycle` hoặc `/payments/1.0/retries`. Đường dẫn nên thể hiện chủ đề và phiên bản, không chứa tên người dùng, token, mã phiên hoặc tham số bí mật.

## 11. Đưa ví dụ và liên kết vào OpenAPI YAML

Khi Springdoc sinh đặc tả, liên kết và ví dụ được thể hiện trong các vị trí tương ứng. Ví dụ rút gọn:

```yaml
externalDocs:
  description: Hướng dẫn tích hợp Books API
  url: https://docs.example.com/books-api/1.0/guide
paths:
  /api/books:
    post:
      summary: Tạo sách
      externalDocs:
        description: Quy tắc tạo và kiểm tra dữ liệu sách
        url: https://docs.example.com/books-api/1.0/create
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateBookRequest'
            examples:
              BasicBook:
                summary: Sách cơ bản
                value:
                  title: Spring Boot căn bản
                  publicationYear: 2025
```

Với external example, OpenAPI có thể biểu diễn:

```yaml
examples:
  BulkImport:
    summary: Ví dụ nhập nhiều bản ghi
    externalValue: https://docs.example.com/examples/books/bulk-import-v1.json
```

Đây là cấu trúc minh họa. Đặc tả thực tế có thể chứa thêm schema, response, tag, security và metadata khác. Sau khi thay annotation, hãy kiểm tra `/v3/api-docs` hoặc `/v3/api-docs.yaml` để xác nhận URL và example xuất hiện đúng vị trí.

## 12. Kiểm tra liên kết và ví dụ trước khi công bố

Một liên kết hợp lệ về cú pháp vẫn có thể không dùng được. Trước khi công bố tài liệu, kiểm tra:

- URL dùng HTTPS và trỏ đến đúng tên miền chính thức.
- Trang đích trả về nội dung phù hợp, không phải trang đăng nhập hoặc trang lỗi.
- Người tiêu thụ API mục tiêu có quyền truy cập trang đó.
- Trang đích nói về đúng API, operation và phiên bản.
- Redirect không dẫn đến URL chứa thông tin nhạy cảm hoặc nội dung không còn liên quan.
- External example có định dạng hợp lệ, đúng media type và không yêu cầu credential bí mật để tải.
- Các ví dụ inline hợp lệ với schema, có thể sao chép để thử trong môi trường sandbox.

Với một tập tài liệu lớn, có thể thêm kiểm tra liên kết tự động trong pipeline tài liệu. Kiểm tra cần xử lý redirect, lỗi tạm thời và trang yêu cầu xác thực một cách phù hợp; không coi mọi phản hồi 403 từ tài liệu nội bộ là liên kết public hợp lệ.

## 13. Quy trình rà soát bí mật trong ví dụ

Trước khi merge hoặc phát hành thay đổi tài liệu, thực hiện các bước sau:

1. Tìm các trường nhạy cảm thường gặp như `password`, `secret`, `token`, `apiKey`, `authorization`, `cookie`, `privateKey` và `clientSecret`.
2. Xem giá trị thực tế trong từng ví dụ, không chỉ dựa vào tên field. Một trường `reference` hoặc `id` cũng có thể chứa mã nội bộ nhạy cảm.
3. Thay dữ liệu production bằng dữ liệu giả lập hoặc placeholder vô hiệu.
4. Kiểm tra URL, header, cookie và query string để bảo đảm không chứa credential.
5. Kiểm tra tệp `externalValue` và các trang được liên kết; bí mật có thể nằm trong ví dụ lưu bên ngoài.
6. Chạy secret scanner nếu repository hoặc pipeline có công cụ phù hợp.
7. Nhờ người sở hữu API xác nhận ví dụ phản ánh đúng hợp đồng và không tiết lộ thông tin nội bộ.

Secret scanner hỗ trợ phát hiện chuỗi có hình dạng giống khóa hoặc token nhưng không thay thế việc đọc nội dung. Một giá trị giả lập có thể trông giống secret; ngược lại, một mã nội bộ thật có thể không khớp mẫu scanner. Cần kết hợp công cụ với rà soát thủ công.

Nếu phát hiện credential thật đã được commit hoặc công bố, xóa chuỗi khỏi tài liệu là chưa đủ. Cần báo cho người sở hữu credential để thu hồi hoặc rotate theo quy trình bảo mật, đồng thời đánh giá nơi nội dung đã được phân phối. Không tiếp tục sao chép credential vào một ví dụ khác để “giữ tính nhất quán”.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thấy liên kết trong Swagger UI | `externalDocs` chưa xuất hiện trong OpenAPI hoặc giao diện không hiển thị ở vị trí mong đợi | Kiểm tra JSON/YAML; mở trực tiếp URL trong `externalDocs` |
| URL tài liệu trả về 404 | Trang bị di chuyển hoặc sai version path | Cập nhật URL và giữ redirect nếu cần |
| Người dùng API không truy cập được tài liệu | Trang chỉ dành cho mạng nội bộ hoặc yêu cầu quyền không được cấp | Cung cấp trang phù hợp với đối tượng sử dụng hoặc mô tả rõ quyền truy cập |
| External example không hiển thị | Công cụ không hỗ trợ tải `externalValue`, URL bị chặn hoặc nội dung không hợp lệ | Thử với công cụ mục tiêu; dùng inline `value` nếu cần hiển thị ổn định |
| Ví dụ không khớp schema | Payload cũ hoặc được sao chép từ phiên bản khác | Cập nhật ví dụ và kiểm tra bằng schema hiện tại |
| Token xuất hiện trong Swagger UI | Credential bị ghi vào `value`, `example`, header hoặc URL | Thay bằng placeholder; nếu là credential thật, thu hồi/rotate |
| Ví dụ chứa dữ liệu cá nhân | Payload production được sao chép mà chưa làm sạch | Thay bằng dữ liệu tổng hợp, không thể liên kết với người thật |
| Tài liệu trỏ đến hostname nội bộ | Dùng URL môi trường phát triển hoặc staging trong metadata public | Thay bằng domain chính thức dành cho người tiêu thụ |
| Trang latest không khớp API cũ | Liên kết không khóa phiên bản | Dùng URL tài liệu versioned và duy trì trong thời gian hỗ trợ |

## 15. Checklist cho liên kết và ví dụ an toàn

- [ ] `@ExternalDocumentation` được đặt ở phạm vi phù hợp: tài liệu, tag hoặc operation.
- [ ] Mỗi liên kết có mô tả ngắn, nói rõ người đọc sẽ tìm thấy gì.
- [ ] URL dùng HTTPS, tên miền chính thức và đường dẫn ổn định.
- [ ] Tài liệu gắn với phiên bản API phù hợp và có người sở hữu.
- [ ] `@ExampleObject.value` hoặc `externalValue` phản ánh payload hợp lệ.
- [ ] Không khai báo đồng thời `value` và `externalValue` cho cùng một ví dụ.
- [ ] Ví dụ không chứa password, token, API key, cookie phiên hoặc private key thật.
- [ ] Dữ liệu cá nhân, thanh toán và định danh đều là dữ liệu giả lập.
- [ ] Header, cookie, query string và URL không chứa credential.
- [ ] Tệp external example cũng đã được rà soát bí mật.
- [ ] Đã kiểm tra URL và ví dụ trong OpenAPI JSON/YAML cùng Swagger UI.
- [ ] Đã rà soát nội dung trước khi công bố hoặc phát hành.

`@ExternalDocumentation` giúp nối hợp đồng OpenAPI với hướng dẫn chi tiết; `@ExampleObject` và `@Schema` giúp minh họa cách sử dụng API. Hãy giữ các liên kết ổn định theo phiên bản và chỉ dùng dữ liệu giả lập trong ví dụ. Nhờ đó, tài liệu vừa hữu ích cho người tích hợp vừa tránh trở thành nơi lưu trữ hoặc phát tán thông tin xác thực và dữ liệu nhạy cảm.

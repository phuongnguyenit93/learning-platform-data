# Đọc bản YAML tại `/v3/api-docs.yaml`

Springdoc-openapi có thể xuất hợp đồng API thành JSON hoặc YAML từ metadata của ứng dụng Spring Boot. Khi ứng dụng chạy với cấu hình mặc định, endpoint `/v3/api-docs` cung cấp tài liệu JSON và `/v3/api-docs.yaml` cung cấp cùng tài liệu đó ở định dạng YAML. Bản YAML thuận tiện cho việc đọc, review thay đổi trong Git, lưu thành artifact và đưa vào quy trình kiểm thử hoặc sinh client.

Đối với module `SPRINGDOC_OPENAPI`, cần hiểu YAML là biểu diễn của mô hình OpenAPI được springdoc tạo từ controller, DTO, annotation và cấu hình. Đọc được tài liệu này giúp kiểm tra hợp đồng mà người tiêu dùng API thực sự nhận được, thay vì chỉ dựa vào ý định thể hiện trong mã nguồn.

## 1. Endpoint `/v3/api-docs.yaml` hoạt động như thế nào?

Trong lúc ứng dụng Spring Boot khởi động, Spring đăng ký các handler mapping và khởi tạo các bean cấu hình. Springdoc tích hợp với môi trường này để thu thập thông tin về endpoint, tham số, kiểu request/response và metadata OpenAPI. Khi có request đến endpoint tài liệu, springdoc trả về mô hình OpenAPI đã được xây dựng dưới dạng JSON hoặc YAML.

Với cấu hình mặc định:

| Endpoint | Nội dung |
|---|---|
| `/v3/api-docs` | Tài liệu OpenAPI dạng JSON |
| `/v3/api-docs.yaml` | Tài liệu OpenAPI dạng YAML |
| `/swagger-ui.html` | Điểm truy cập giao diện Swagger UI; có thể chuyển hướng đến trang giao diện thực tế |

Hai endpoint tài liệu biểu diễn cùng một hợp đồng. Khác biệt nằm ở định dạng tuần tự hóa, không phải một endpoint chứa nhiều API hơn endpoint còn lại. Swagger UI thường tải tài liệu JSON theo cấu hình mặc định, nhưng các công cụ khác có thể đọc trực tiếp YAML.

Nếu ứng dụng có context path, reverse proxy prefix hoặc cấu hình đường dẫn tài liệu riêng, URL thực tế sẽ có thêm tiền tố tương ứng. Ví dụ, với context path `/orders`, URL mặc định trở thành `/orders/v3/api-docs.yaml`.

## 2. Truy cập và lưu tài liệu YAML

Khởi động ứng dụng Spring Boot theo cách thông thường, sau đó mở URL dưới đây trong trình duyệt:

```text
http://localhost:8080/v3/api-docs.yaml
```

Nếu endpoint được bảo vệ, gửi request kèm thông tin xác thực mà ứng dụng yêu cầu. Có thể dùng `curl.exe` để tải tài liệu về file:

```bash
curl.exe -fS http://localhost:8080/v3/api-docs.yaml -o openapi.yaml
```

Khi API yêu cầu bearer token, thêm header `Authorization`:

```bash
curl.exe -fS \
  -H "Authorization: Bearer <access-token>" \
  http://localhost:8080/v3/api-docs.yaml \
  -o openapi.yaml
```

Trong PowerShell, có thể chạy lệnh trên dưới dạng nhiều dòng với dấu backtick làm ký tự nối dòng, hoặc viết thành một dòng. Dùng `curl.exe` giúp gọi chương trình curl trên Windows thay vì alias `curl` có thể trỏ đến `Invoke-WebRequest` trong một số phiên bản PowerShell.

Sau khi tải, kiểm tra file có nội dung YAML và bắt đầu bằng trường `openapi`. Nếu nhận HTML, trang đăng nhập hoặc JSON lỗi thay vì YAML, hãy kiểm tra status HTTP, redirect, quyền truy cập và URL. Không nên đưa file HTML lỗi vào công cụ xử lý OpenAPI vì thông báo lỗi khi phân tích sẽ gây nhầm lẫn.

## 3. Thay đổi đường dẫn tài liệu

Đường dẫn mặc định có thể được thay đổi bằng cấu hình `springdoc.api-docs.path`. Ví dụ:

```yaml
springdoc:
  api-docs:
    path: /internal/openapi
```

Với cấu hình này, endpoint JSON sử dụng `/internal/openapi`; endpoint YAML tương ứng sử dụng hậu tố `.yaml`, tức `/internal/openapi.yaml`. Nếu có context path hoặc proxy prefix, ghép thêm tiền tố đó khi gọi từ bên ngoài.

Có thể bật hoặc tắt endpoint tài liệu bằng cấu hình:

```yaml
springdoc:
  api-docs:
    enabled: true
```

Giá trị `false` sẽ tắt việc cung cấp API docs qua endpoint springdoc. Cấu hình có thể được đặt theo profile để môi trường phát triển cho phép truy cập, còn môi trường triển khai thực tế áp dụng chính sách công bố và bảo vệ tài liệu phù hợp.

Khi URL không hoạt động, kiểm tra lần lượt:

1. Ứng dụng đã khởi động thành công và web server đang lắng nghe đúng port.
2. Đường dẫn có bao gồm context path và prefix do proxy thêm hay chưa.
3. `springdoc.api-docs.path` có được đặt trong profile đang chạy hay không.
4. `springdoc.api-docs.enabled` có đang bị đặt thành `false` hay không.
5. Security filter, gateway hoặc reverse proxy có chặn request trước khi đến endpoint tài liệu hay không.

## 4. Đọc cấu trúc cấp cao của OpenAPI YAML

Một tài liệu OpenAPI thường bắt đầu với các trường `openapi`, `info`, `servers`, `paths` và có thể có `components` cùng `security`. Ví dụ rút gọn:

```yaml
openapi: 3.0.1
info:
  title: Order API
  version: v1
  description: API quản lý đơn hàng
servers:
  - url: https://api.example.com
paths:
  /api/orders/{id}:
    get:
      tags:
        - Orders
      summary: Lấy thông tin đơn hàng
      operationId: getOrderById
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Tìm thấy đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '404':
          description: Không tìm thấy đơn hàng
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
```

Đây là ví dụ minh họa cấu trúc, không phải output cố định của mọi phiên bản springdoc. Trường `openapi` cho biết phiên bản đặc tả; giá trị thực tế phụ thuộc phiên bản thư viện và cấu hình. `info` chứa metadata của tài liệu, `servers` mô tả địa chỉ máy chủ, còn `paths` chứa các đường dẫn và thao tác HTTP.

Khi review YAML, nên đọc từ ngoài vào trong:

- **`openapi`:** phiên bản đặc tả OpenAPI mà tài liệu tuân theo. Không nhầm trường này với phiên bản ứng dụng trong `info.version`.
- **`info`:** tiêu đề, phiên bản API được công bố, mô tả và thông tin liên hệ hoặc giấy phép nếu có.
- **`servers`:** URL cơ sở để client gọi API. Cần kiểm tra URL có phù hợp với môi trường và cách triển khai hay không.
- **`paths`:** tập endpoint được đưa vào tài liệu. Mỗi path có thể chứa các thao tác `get`, `post`, `put`, `patch`, `delete`, `options` hoặc `head`.
- **`components`:** nơi định nghĩa schema, response, parameter, request body, header và security scheme có thể tái sử dụng.
- **`security`:** yêu cầu bảo mật áp dụng ở cấp tài liệu; một operation có thể khai báo yêu cầu riêng hoặc ghi đè chính sách chung theo quy tắc OpenAPI.

## 5. Đọc một operation trong `paths`

Mỗi cặp path và HTTP method mô tả một operation. Ví dụ, `/api/orders/{id}` cùng `get` tương ứng với thao tác lấy một đơn hàng. Các trường thường cần kiểm tra gồm:

| Trường | Ý nghĩa khi đọc hợp đồng |
|---|---|
| `tags` | Nhóm thao tác trong tài liệu và Swagger UI |
| `summary` | Mô tả ngắn gọn chức năng |
| `description` | Giải thích chi tiết cách sử dụng hoặc quy tắc nghiệp vụ |
| `operationId` | Định danh thao tác, thường được dùng khi sinh client |
| `parameters` | Path, query, header hoặc cookie parameter |
| `requestBody` | Nội dung request, media type và schema |
| `responses` | Các mã trạng thái, mô tả và nội dung phản hồi |
| `deprecated` | Cho biết thao tác đã được đánh dấu ngừng khuyến nghị |
| `security` | Yêu cầu xác thực riêng của operation nếu được khai báo |

Ví dụ request body và nhiều response:

```yaml
paths:
  /api/orders:
    post:
      summary: Tạo đơn hàng
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Đã tạo đơn hàng
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '400':
          description: Dữ liệu không hợp lệ
        '409':
          description: Đơn hàng xung đột với trạng thái hiện tại
```

Đọc phần này để xác nhận endpoint có đúng HTTP method, tham số có đúng vị trí, request body có bắt buộc hay không, media type có chính xác và response có bao phủ các kết quả API thực sự trả về. Một response chỉ có `description` vẫn có thể hợp lệ nếu thao tác không có nội dung phản hồi; với response có body, cần kiểm tra `content` và schema tương ứng.

## 6. Hiểu schema và tham chiếu `$ref`

Các DTO Java thường được biểu diễn thành schema trong `components.schemas`. Thay vì lặp lại định nghĩa một kiểu ở nhiều operation, OpenAPI có thể tham chiếu đến schema chung bằng `$ref`:

```yaml
components:
  schemas:
    CreateOrderRequest:
      type: object
      required:
        - customerName
        - amount
      properties:
        customerName:
          type: string
          maxLength: 80
          example: Nguyen Van A
        amount:
          type: number
          format: double
          description: Tổng tiền tính bằng VND
          example: 250000
    OrderResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
```

`$ref: '#/components/schemas/CreateOrderRequest'` có nghĩa là nội dung schema được lấy từ vị trí tương ứng trong cùng tài liệu. Khi đọc một operation, hãy theo `$ref` để xem đầy đủ kiểu dữ liệu, trường bắt buộc, giới hạn, enum, định dạng và ví dụ.

Một số điểm cần lưu ý:

- `required` ở cấp object liệt kê các thuộc tính bắt buộc; `required: true` ở parameter hoặc request body mang ý nghĩa bắt buộc của thành phần đó.
- `type` và `format` mô tả kiểu dữ liệu và định dạng bổ sung, ví dụ `string` với `uuid` hoặc `date-time`.
- `enum`, `minimum`, `maximum`, `minLength`, `maxLength`, `minItems` và `maxItems` thể hiện giới hạn có thể được suy ra từ kiểu hoặc validation metadata.
- `readOnly` và `writeOnly` giúp mô tả trường chỉ đọc hoặc chỉ ghi trong hợp đồng.
- Tên JSON, kiểu nullable, thuộc tính kế thừa và cấu trúc lồng nhau phụ thuộc vào DTO, Jackson, validation và cấu hình springdoc.

Không nên giả định schema luôn trùng từng chữ với khai báo Java. Điều quan trọng là YAML phải mô tả đúng JSON mà ứng dụng nhận và trả ở runtime.

## 7. Đọc thông tin bảo mật trong YAML

Khi API dùng bearer token, API key hoặc OAuth2, tài liệu có thể định nghĩa cơ chế đó trong `components.securitySchemes` và tham chiếu trong `security`. Ví dụ minh họa bearer JWT:

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
security:
  - bearerAuth: []
```

Khai báo này mô tả cách client gửi bearer token. Nó không tự cấu hình Spring Security và cũng không bật xác thực cho endpoint. Chính sách thực thi vẫn do cấu hình bảo mật của ứng dụng quyết định; metadata OpenAPI cần được khai báo hoặc tùy biến để phản ánh chính sách đó.

Nếu chỉ một số endpoint cần đăng nhập, kiểm tra `security` ở từng operation. Một operation có thể công khai trong khi tài liệu cấp cao khai báo yêu cầu bảo mật chung; OpenAPI cho phép operation ghi đè yêu cầu chung, kể cả biểu diễn operation không yêu cầu security. Vì vậy, hãy kiểm tra kết quả được sinh có khớp với quyền truy cập thực tế.

## 8. YAML, JSON và nhóm tài liệu

JSON và YAML là hai cách biểu diễn cùng mô hình OpenAPI. JSON phù hợp với nhiều API và công cụ tự động; YAML dễ đọc, dễ review và thường được dùng làm file đặc tả trong repository. Việc đổi định dạng không làm thay đổi hợp đồng nếu hai bản được sinh từ cùng một cấu hình.

Springdoc cũng hỗ trợ chia tài liệu theo nhóm bằng cấu hình `GroupedOpenApi`. Mỗi nhóm có thể chọn các package hoặc path riêng để tạo một tập endpoint phù hợp với một phạm vi API. Điều này hữu ích khi ứng dụng có nhiều miền chức năng hoặc cần phân phối tài liệu cho các nhóm client khác nhau.

Ví dụ khai báo nhóm:

```java
@Bean
GroupedOpenApi orderApi() {
    return GroupedOpenApi.builder()
            .group("orders")
            .pathsToMatch("/api/orders/**")
            .build();
}
```

Với nhóm này, springdoc tạo tài liệu riêng cho phạm vi `orders`. Endpoint JSON của nhóm thường có dạng `/v3/api-docs/orders`. Để tải YAML của một nhóm, dùng route YAML tương ứng được expose bởi phiên bản springdoc đang dùng; kiểm tra cấu hình nhóm và URL mà Swagger UI sử dụng thay vì tự đoán đường dẫn khi ứng dụng đã tùy biến `springdoc.api-docs.path`.

Khi đọc tài liệu theo nhóm, hãy kiểm tra cả tên nhóm lẫn bộ lọc `pathsToMatch`, `packagesToScan`, `pathsToExclude` hoặc `packagesToExclude` nếu có. Endpoint không xuất hiện có thể do bị loại khỏi nhóm, không nhất thiết do springdoc không nhận diện controller.

## 9. Bảo vệ endpoint tài liệu

OpenAPI YAML có thể tiết lộ đường dẫn nội bộ, mô hình dữ liệu, cách xác thực và các thao tác được hỗ trợ. Vì vậy, quyền truy cập tài liệu cần phù hợp với chính sách công bố API của hệ thống.

Một số cách kiểm soát thường dùng:

- Dùng Spring Security để yêu cầu xác thực hoặc phân quyền trước khi truy cập endpoint tài liệu.
- Dùng profile hoặc cấu hình triển khai để bật/tắt API docs theo môi trường.
- Giới hạn truy cập qua gateway, mạng nội bộ hoặc reverse proxy nếu tài liệu chỉ dành cho đội phát triển.
- Không đặt token, mật khẩu, khóa bí mật hoặc dữ liệu cá nhân thật trong `example`, `description` hay metadata OpenAPI.
- Kiểm tra quyền truy cập cả endpoint JSON, YAML và Swagger UI; bảo vệ giao diện nhưng bỏ quên endpoint dữ liệu vẫn có thể để lộ hợp đồng.

Không nên coi việc ẩn Swagger UI là biện pháp bảo vệ tài liệu. Client vẫn có thể gọi trực tiếp `/v3/api-docs` hoặc `/v3/api-docs.yaml` nếu endpoint đó còn mở.

## 10. Kiểm tra chất lượng bản YAML

Sau khi tải tài liệu, hãy xác minh cả cú pháp YAML lẫn ý nghĩa OpenAPI:

1. **Kiểm tra HTTP response:** request thành công, trả nội dung YAML và không bị redirect sang trang đăng nhập ngoài dự kiến.
2. **Kiểm tra cấu trúc:** có `openapi`, `info` và `paths`; phiên bản đặc tả là giá trị hợp lệ mà hệ sinh thái công cụ đang dùng hỗ trợ.
3. **Kiểm tra đường dẫn:** các path và HTTP method có đầy đủ, đúng prefix và đúng phạm vi nhóm.
4. **Kiểm tra request:** parameter nằm đúng vị trí, request body và media type chính xác, schema có đủ trường bắt buộc và giới hạn.
5. **Kiểm tra response:** mã trạng thái, schema, header và ví dụ khớp với kết quả thực tế.
6. **Kiểm tra bảo mật:** security scheme, scope và yêu cầu ở cấp operation phản ánh chính sách Spring Security.
7. **Kiểm tra tham chiếu:** mọi `$ref` đều trỏ đến thành phần tồn tại và không tạo tham chiếu sai.
8. **Kiểm tra bằng công cụ:** dùng OpenAPI parser hoặc validator trong IDE/CI để phát hiện YAML sai cú pháp và cấu trúc OpenAPI không hợp lệ.
9. **Đối chiếu runtime:** gọi các endpoint đại diện và so sánh payload thực tế với schema trong tài liệu.

Một file YAML có thể parse được nhưng vẫn mô tả sai API. Ví dụ, `200` có schema `OrderResponse` trong khi ứng dụng trả `204` không có body là sai lệch hợp đồng dù cú pháp hoàn toàn hợp lệ. Do đó, cần cả kiểm tra cấu trúc và kiểm tra hành vi.

## 11. Lỗi thường gặp khi đọc `/v3/api-docs.yaml`

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `404 Not Found` | Sai path, context path hoặc `springdoc.api-docs.path`; API docs bị tắt | Kiểm tra cấu hình đang chạy và URL thực tế |
| `401` hoặc `403` | Security yêu cầu xác thực hoặc quyền cao hơn | Gửi credential phù hợp hoặc kiểm tra chính sách truy cập |
| Nhận HTML thay vì YAML | Request bị redirect, proxy trả trang lỗi hoặc URL trỏ nhầm Swagger UI | Kiểm tra status, header `Location` và URL endpoint |
| YAML không có endpoint mong đợi | Controller không được component scan, endpoint bị lọc hoặc thuộc nhóm khác | Kiểm tra package scan, mapping và cấu hình `GroupedOpenApi` |
| Schema thiếu thuộc tính | Jackson, visibility, annotation ẩn hoặc cấu hình schema ảnh hưởng kết quả | Kiểm tra DTO, serializer và OpenAPI annotation |
| `servers` chứa URL không đúng | Cấu hình server, context path hoặc reverse proxy chưa được phản ánh | Kiểm tra cấu hình OpenAPI và forwarded headers |
| Tài liệu bị từ chối khi phân tích | YAML sai cú pháp, `$ref` không hợp lệ hoặc cấu trúc OpenAPI không đúng | Dùng parser/validator và sửa metadata nguồn |

Nếu lỗi chỉ xảy ra ở môi trường sau reverse proxy, so sánh URL và header được proxy chuyển tiếp với cấu hình ứng dụng. Nếu endpoint trả tài liệu nhưng thiếu một operation, kiểm tra log khởi tạo và các bộ lọc nhóm trước khi thay đổi controller.

## 12. Đưa YAML vào quy trình phát triển

YAML có thể được lưu làm artifact để review và so sánh hợp đồng giữa các lần phát hành. Một quy trình đơn giản gồm:

1. Khởi động ứng dụng với cấu hình đại diện cho phiên bản cần phát hành.
2. Tải `/v3/api-docs.yaml` hoặc endpoint nhóm tương ứng.
3. Chạy parser/validator OpenAPI và kiểm tra các quy tắc nội bộ.
4. So sánh với bản đặc tả của phiên bản trước để phát hiện thay đổi có thể phá vỡ client, như xóa path, đổi kiểu trường, thay response hoặc siết điều kiện bắt buộc.
5. Lưu artifact gắn với phiên bản ứng dụng và phân phối cho nhóm tiêu dùng API.

Không nên chỉnh sửa trực tiếp file YAML được sinh rồi kỳ vọng ứng dụng tự nhận thay đổi đó. Khi phát hiện tài liệu thiếu mô tả hoặc sai schema, hãy cập nhật controller metadata, DTO, annotation OpenAPI hoặc customizer là nguồn tạo ra tài liệu, sau đó sinh lại và kiểm tra.

Đọc bản YAML tại `/v3/api-docs.yaml` giúp nhìn thấy hợp đồng OpenAPI ở dạng dễ kiểm tra và có thể tự động hóa. Khi hiểu `paths`, `components`, `$ref`, `responses` và `security`, người phát triển có thể đối chiếu chính xác tài liệu với controller Spring Boot, phát hiện sai lệch trước khi phát hành và cung cấp một đặc tả ổn định cho công cụ cũng như người tiêu dùng API.

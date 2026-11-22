# Method, path, query, header và body

Một HTTP API nhận request qua mạng và diễn giải request đó thành một hành động trên tài nguyên. Để hiểu một API hoạt động thế nào, cần đọc được năm thành phần cơ bản: **HTTP method**, **path**, **query parameter**, **header** và **body**. Mỗi thành phần mang một loại thông tin khác nhau; nếu đặt dữ liệu sai chỗ hoặc hiểu sai ý nghĩa của chúng, ứng dụng có thể xử lý request không nhất quán, làm lộ dữ liệu hoặc cho phép thao tác vượt quyền.

Trong API Security, hiểu cấu trúc HTTP là bước đầu để thiết kế kiểm soát theo từng endpoint và luồng nghiệp vụ. Method thể hiện hành động, path xác định tài nguyên, query bổ sung điều kiện truy vấn, header mang metadata của request, còn body thường chứa dữ liệu cần xử lý. Tất cả dữ liệu đến từ client đều phải được xem là không đáng tin cậy cho đến khi được kiểm tra và áp dụng chính sách phù hợp.

## 1. Cấu trúc một HTTP request

Một request HTTP/1.1 điển hình có dạng:

```http
PATCH /api/v1/orders/8f12?notify=false HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json
Content-Type: application/json
X-Request-Id: 7f4d2c

{
  "shippingAddress": {
    "city": "Da Nang",
    "street": "12 Nguyen Van Linh"
  }
}
```

Có thể đọc request này như sau:

| Thành phần | Giá trị ví dụ | Vai trò |
|---|---|---|
| Method | `PATCH` | Yêu cầu cập nhật một phần tài nguyên |
| Path | `/api/v1/orders/8f12` | Chỉ ra đơn hàng được nhắm tới |
| Query | `notify=false` | Bổ sung một tùy chọn cho request |
| Header | `Authorization`, `Accept`, `Content-Type` | Mang thông tin xác thực, định dạng mong muốn và định dạng gửi lên |
| Body | JSON địa chỉ giao hàng | Mang dữ liệu cần xử lý |

Server phân tích request, áp dụng các quy tắc định tuyến, xác thực, phân quyền, validation và nghiệp vụ, sau đó trả về một HTTP response. Response cũng có status code, header và có thể có body.

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "8f12",
  "status": "PENDING_PAYMENT",
  "shippingAddress": {
    "city": "Da Nang",
    "street": "12 Nguyen Van Linh"
  }
}
```

Đây là ví dụ minh họa. Tên header, status code và nội dung response thực tế phụ thuộc hợp đồng API của hệ thống.

## 2. HTTP method: request muốn thực hiện hành động nào?

HTTP method cho biết ý định của client đối với tài nguyên. Method không tự cấp quyền cho người gọi; nó chỉ mô tả hành động mà server được yêu cầu thực hiện. Server phải quyết định method đó có được hỗ trợ tại endpoint hay không và danh tính hiện tại có quyền thực hiện hành động tương ứng không.

| Method | Ý nghĩa thường gặp | Tính chất HTTP quan trọng |
|---|---|---|
| `GET` | Đọc biểu diễn tài nguyên hoặc danh sách | Safe, idempotent, thường cacheable |
| `HEAD` | Như `GET` nhưng không trả response body | Safe, idempotent |
| `POST` | Tạo tài nguyên hoặc thực hiện hành động | Không mặc định idempotent |
| `PUT` | Tạo hoặc thay thế biểu diễn tại URI đích | Idempotent theo ngữ nghĩa HTTP |
| `PATCH` | Áp dụng thay đổi một phần | Không mặc định idempotent |
| `DELETE` | Yêu cầu xóa tài nguyên | Idempotent theo ngữ nghĩa HTTP |
| `OPTIONS` | Hỏi các tùy chọn giao tiếp được hỗ trợ | Safe; thường dùng cho capability và CORS preflight |

### Safe và idempotent có nghĩa gì?

Một method **safe** được định nghĩa là method mà client không yêu cầu thay đổi trạng thái tài nguyên. `GET` là ví dụ điển hình. Server vẫn có thể ghi access log, tăng bộ đếm vận hành hoặc cập nhật dữ liệu kỹ thuật, nhưng không nên dùng `GET` để thực hiện hành động nghiệp vụ như thanh toán, xóa tài khoản hoặc xác nhận đơn hàng.

Một method **idempotent** có nghĩa là gửi cùng một request nhiều lần có cùng hiệu quả dự kiến trên trạng thái tài nguyên như gửi một lần. Ví dụ, đặt trạng thái địa chỉ giao hàng thành một giá trị cố định qua `PUT` có thể idempotent. Gửi `DELETE` nhiều lần vẫn có hiệu quả cuối cùng là tài nguyên đã bị xóa, dù response của lần sau có thể khác lần đầu.

`POST` thường tạo một tài nguyên mới hoặc thực hiện một lệnh, nên gửi lại có thể tạo nhiều kết quả. `PATCH` cũng không mặc định idempotent: phép gán một giá trị cố định có thể idempotent, nhưng phép tăng số lượng thêm một đơn vị thì không. Nếu client cần retry một thao tác tạo đơn hàng hoặc thanh toán, API có thể hỗ trợ idempotency key và quy tắc lưu kết quả của lần xử lý đầu tiên.

Idempotency theo HTTP không tự động chống mọi kiểu lạm dụng. Server vẫn cần xác thực, phân quyền, giới hạn tần suất, kiểm soát đồng thời và kiểm tra trạng thái nghiệp vụ. Một request `PUT` idempotent vẫn có thể bị lạm dụng để ghi dữ liệu vào object mà người gọi không sở hữu.

### Chọn method theo ý nghĩa nghiệp vụ

Ví dụ với tài nguyên đơn hàng:

```http
GET    /api/v1/orders/8f12
POST   /api/v1/orders
PUT    /api/v1/orders/8f12/shipping-address
PATCH  /api/v1/orders/8f12
DELETE /api/v1/orders/8f12
```

Không nên dùng `GET` cho thao tác có side effect chỉ vì nó dễ gọi từ trình duyệt. Crawler, proxy, cache hoặc trình duyệt có thể tự động gửi lại request đọc. Không nên dùng một endpoint `POST /orders/action` cho nhiều hành động không liên quan nếu điều đó khiến hợp đồng quyền và validation trở nên khó hiểu. Method và endpoint nên thể hiện rõ chức năng mà server thực hiện.

Server cần từ chối method không được hỗ trợ. HTTP thường dùng `405 Method Not Allowed` và có thể gửi header `Allow` liệt kê các method được hỗ trợ cho tài nguyên đó. Việc frontend không hiển thị nút hoặc tài liệu không công bố method không phải biện pháp phân quyền.

## 3. Path: xác định tài nguyên hoặc vùng chức năng

Path là phần đường dẫn trong URI, thường được dùng để xác định tài nguyên. Ví dụ:

```text
/api/v1/customers
/api/v1/customers/42
/api/v1/customers/42/orders
/api/v1/orders/8f12/items/3
```

Các đoạn như `42`, `8f12` hoặc `3` thường là path parameter. Chúng giúp server biết client đang tham chiếu tới object nào.

Trong REST, URI thường được thiết kế xoay quanh danh từ biểu diễn tài nguyên. Collection thường dùng dạng số nhiều như `/orders`, còn một tài nguyên cụ thể dùng `/orders/{orderId}`. Tài nguyên con có thể được biểu diễn bằng đường dẫn lồng nhau như `/orders/{orderId}/items`. Đây là quy ước thiết kế dễ đọc, không phải quy tắc cú pháp bắt buộc của HTTP.

Path parameter cần được parse và validation theo kiểu dữ liệu mong đợi. Nếu `orderId` phải là UUID, server nên từ chối giá trị sai định dạng với lỗi phù hợp. Tuy nhiên, ID hợp lệ không chứng minh người gọi có quyền truy cập object đó. Server vẫn phải kiểm tra quan hệ sở hữu, tenant, vai trò và ngữ cảnh nghiệp vụ trước khi trả dữ liệu hoặc thay đổi trạng thái.

Không dùng ID khó đoán làm biện pháp bảo mật duy nhất. Số thứ tự tăng dần, UUID hay mã ngẫu nhiên đều có thể bị lộ qua response, log phía client, liên kết hoặc endpoint khác. Quyết định truy cập phải dựa trên authorization ở phía server.

Path cũng không phải nơi thích hợp để truyền bí mật như mật khẩu, access token hoặc dữ liệu cá nhân nhạy cảm. URL có thể xuất hiện trong browser history, access log, proxy log, hệ thống phân tích và header `Referer` trong một số ngữ cảnh. Hãy đặt thông tin xác thực trong cơ chế header hoặc cookie được thiết kế phù hợp, và hạn chế dữ liệu nhạy cảm trong URL.

## 4. Query parameter: lọc, phân trang và tùy chọn truy vấn

Query là phần nằm sau dấu `?` trong URI. Các cặp tên–giá trị thường được nối với nhau bằng `&`:

```http
GET /api/v1/orders?status=SHIPPED&page=0&size=20&sort=createdAt,desc
```

Ví dụ này yêu cầu danh sách đơn hàng có trạng thái `SHIPPED`, trang số 0, tối đa 20 phần tử và sắp xếp theo thời gian tạo giảm dần.

Query parameter phù hợp với dữ liệu bổ sung cách truy vấn collection: bộ lọc, phân trang, sắp xếp, tìm kiếm hoặc lựa chọn biểu diễn. Nó thường không xác định danh tính hay quyền truy cập. Nếu client gửi `?userId=42` hoặc `?tenantId=9`, server không được mặc định rằng người gọi có quyền xem dữ liệu của user hoặc tenant đó. Phạm vi truy cập phải được xác định từ danh tính và chính sách phía server.

### Kiểm soát query để tránh truy vấn nguy hiểm

Query parameter là đầu vào không đáng tin cậy. Hãy quy định rõ:

- Danh sách tên filter được hỗ trợ và kiểu dữ liệu của từng filter.
- Số lượng giá trị tối đa, độ dài chuỗi và cách xử lý tham số lặp.
- Giá trị mặc định và giới hạn `page`, `size`, `limit`, `offset`.
- Các trường được phép sort và chiều sắp xếp hợp lệ.
- Thời gian tối đa, độ sâu hoặc độ phức tạp của truy vấn tìm kiếm.

Không ghép trực tiếp giá trị query vào câu SQL hoặc tên cột. Dùng parameterized query cho giá trị và allowlist cho tên trường hoặc hướng sort, vì tên cột thường không thể bind như một giá trị thông thường. Giới hạn kích thước trang ở phía server; không tin `size=1000000` chỉ vì client gửi lên.

Tham số lặp như `?role=USER&role=ADMIN` có thể được framework diễn giải thành danh sách, lấy giá trị đầu tiên hoặc lấy giá trị cuối cùng. Nếu nhiều lớp proxy, gateway và ứng dụng diễn giải khác nhau, request có thể tạo ra hành vi không nhất quán. Hợp đồng API cần quy định rõ cách xử lý tham số trùng và từ chối trường hợp mơ hồ nếu không có ý nghĩa nghiệp vụ.

Query string thường được ghi vào access log và có thể được lưu trong lịch sử trình duyệt. Vì vậy, không truyền password, token, mã xác thực dùng một lần hoặc dữ liệu nhạy cảm qua query. Dùng HTTPS vẫn cần thiết nhưng không làm URL trở thành nơi lưu bí mật an toàn.

## 5. Header: metadata và thông tin điều khiển request

Header là các trường metadata đi kèm request hoặc response. Header giúp hai phía hiểu cách xử lý nội dung, xác thực, cache, nguồn request và các thuộc tính giao tiếp.

Một số request header thường gặp:

| Header | Mục đích | Lưu ý bảo mật |
|---|---|---|
| `Authorization` | Mang thông tin xác thực, ví dụ Bearer token | Không ghi token vào log; kiểm tra chữ ký, issuer, audience, thời hạn và quyền cần thiết |
| `Content-Type` | Cho biết định dạng body gửi lên | Không tin khai báo này thay cho việc kiểm tra và parse nội dung thực tế |
| `Accept` | Cho biết định dạng response client chấp nhận | Xử lý rõ trường hợp không hỗ trợ định dạng, có thể trả `406` |
| `Host` hoặc `:authority` | Xác định authority của request | Cấu hình host hợp lệ; tránh tin host tùy ý khi tạo absolute URL hoặc kiểm tra tenant |
| `Origin` | Chỉ ra origin khởi tạo request trong ngữ cảnh trình duyệt | Dùng cho CORS; không phải bằng chứng xác thực hoặc phân quyền |
| `Cookie` | Gửi cookie đã lưu cho domain/path phù hợp | Với xác thực bằng cookie, cần cấu hình thuộc tính cookie và phòng chống CSRF |
| `If-Match` | Gửi điều kiện phiên bản/ETag khi cập nhật | Có thể giúp ngăn ghi đè dữ liệu đã thay đổi; server cần kiểm tra điều kiện |
| `X-Request-Id` | Hỗ trợ truy vết request nếu hệ thống quy định | Không dùng làm danh tính hoặc quyền; cần giới hạn và chuẩn hóa giá trị |

Một số response header quan trọng:

| Header | Mục đích |
|---|---|
| `Content-Type` | Định dạng response body |
| `Cache-Control` | Quy định cache được phép lưu và trong bao lâu |
| `ETag` | Định danh phiên bản biểu diễn để cache hoặc kiểm tra cập nhật có điều kiện |
| `Location` | Chỉ ra URI tài nguyên mới hoặc đích chuyển hướng theo status code |
| `Allow` | Liệt kê method được hỗ trợ, thường đi cùng `405` |
| `Retry-After` | Gợi ý thời điểm thử lại, thường dùng với `429` hoặc một số lỗi tạm thời |

### Không mặc định tin header do client gửi

Client có thể tự đặt các header như `X-User-Id`, `X-Role`, `X-Tenant-Id`, `X-Forwarded-For` hoặc `X-Forwarded-Host`. Nếu ứng dụng lấy các giá trị này làm nguồn quyền mà không có một proxy đáng tin cậy xác thực và ghi đè chúng, người gọi có thể giả mạo danh tính hoặc địa chỉ nguồn.

Các header `Forwarded` và `X-Forwarded-*` chỉ nên được tin khi request đi qua proxy/load balancer đã được cấu hình trong danh sách tin cậy. Ứng dụng cần biết proxy nào được phép thêm hoặc sửa header, và phải loại bỏ giá trị do client tự đưa vào ở ranh giới tin cậy. Không dùng `X-Request-Id` hay một header tùy chỉnh làm cơ chế xác thực.

### CORS không phải là authorization

CORS (Cross-Origin Resource Sharing) là cơ chế trình duyệt kiểm soát việc JavaScript từ một origin có được phép đọc response từ origin khác hay không. CORS không ngăn mọi client gửi HTTP request và không thay thế authentication hoặc authorization. Một lệnh gọi bằng curl, ứng dụng di động hoặc máy chủ khác không chịu cùng giới hạn đọc response của trình duyệt.

Với API dùng cookie, cần cân nhắc CSRF vì trình duyệt có thể tự động gửi cookie theo quy tắc domain, path và SameSite. Cấu hình CORS chặt chẽ, cookie `Secure`, `HttpOnly`, `SameSite` phù hợp và CSRF token khi cần là các biện pháp phối hợp. Không bật `Access-Control-Allow-Origin: *` cùng credential một cách tùy tiện; cũng không phản chiếu mọi giá trị `Origin` mà không kiểm tra allowlist.

## 6. Body: dữ liệu gửi để server xử lý

Body thường mang dữ liệu tạo mới hoặc cập nhật tài nguyên. Body có thể là JSON, form URL-encoded, multipart, văn bản thuần hoặc dữ liệu nhị phân. Định dạng cần được mô tả qua `Content-Type`.

Ví dụ JSON:

```http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "items": [
    { "productId": "P-100", "quantity": 2 }
  ],
  "shippingAddressId": "ADDR-12"
}
```

Ví dụ form URL-encoded:

```http
POST /api/v1/login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=an&password=example
```

Ví dụ multipart dùng cho upload tệp:

```http
POST /api/v1/files HTTP/1.1
Content-Type: multipart/form-data; boundary=----form-boundary

------form-boundary
Content-Disposition: form-data; name="description"

Invoice scan
------form-boundary
Content-Disposition: form-data; name="file"; filename="invoice.pdf"
Content-Type: application/pdf

...binary file content...
------form-boundary--
```

Không phải method nào cũng thường có body. `GET` thường truyền điều kiện truy vấn qua query; ngữ nghĩa của GET body không được định nghĩa chung theo cách có thể dựa vào giữa các hệ thống, nên API không nên thiết kế phụ thuộc vào nó. `POST`, `PUT` và `PATCH` thường mang body. Server phải quy định rõ body nào được chấp nhận cho từng endpoint và method.

### Validation body

Server cần kiểm tra ít nhất:

- Body có đúng định dạng được endpoint hỗ trợ không?
- JSON có parse được không, trường bắt buộc có đủ không, kiểu dữ liệu và miền giá trị có hợp lệ không?
- Chuỗi có giới hạn độ dài, danh sách có giới hạn số phần tử và số lồng nhau không?
- Các ID tham chiếu trong body có tồn tại và thuộc phạm vi mà người gọi được phép sử dụng không?
- Các trường nhạy cảm như `ownerId`, `tenantId`, `role`, `price`, `balance` hoặc `status` có được phép do client thiết lập không?
- Kích thước body, số phần multipart, kích thước tệp và thời gian parse có nằm trong giới hạn không?

Không bind trực tiếp request JSON vào entity có nhiều trường nội bộ. Dùng request DTO chỉ chứa thuộc tính được phép nhận, sau đó service áp dụng quy tắc nghiệp vụ. Khi trả response, dùng response DTO để giới hạn thuộc tính được phép đọc. Việc một object được phép truy cập không đồng nghĩa mọi trường trong object đều được phép xem hoặc sửa.

Đối với upload, không chỉ tin tên tệp hoặc MIME type do client khai báo. Cần giới hạn kích thước, kiểm tra định dạng thực tế, đổi tên lưu trữ an toàn, ngăn path traversal và lưu tệp ở vùng không thể thực thi trực tiếp. Nếu nội dung tệp được xử lý hoặc giải nén, cần giới hạn kích thước sau giải nén và thời gian xử lý.

### Content-Type và Accept

`Content-Type` mô tả định dạng body được gửi. Nếu endpoint chỉ hỗ trợ JSON nhưng nhận một định dạng khác, server có thể trả `415 Unsupported Media Type`. `Accept` mô tả định dạng response client muốn nhận. Nếu server không thể tạo định dạng phù hợp, có thể trả `406 Not Acceptable`.

Không nên tự động parse mọi định dạng hoặc bật polymorphic deserialization rộng mà không có nhu cầu và chính sách rõ ràng. Parser và thư viện xử lý tệp là một phần của bề mặt tấn công; cần cập nhật phiên bản, cấu hình an toàn và giới hạn tài nguyên.

## 7. REST và cách tổ chức tài nguyên

REST (Representational State Transfer) là một phong cách kiến trúc cho hệ thống phân tán. Một API thường được gọi là RESTful khi tổ chức giao tiếp quanh tài nguyên, biểu diễn tài nguyên và các quy tắc HTTP nhất quán. Một số nguyên tắc thường được nhắc đến gồm:

1. **Client–server:** giao diện client và nơi lưu trữ/xử lý dữ liệu có ranh giới trách nhiệm rõ ràng.
2. **Stateless:** mỗi request mang đủ ngữ cảnh cần thiết để server xử lý; server không phụ thuộc vào trạng thái phiên giao tiếp ngầm giữa hai request.
3. **Cacheable:** response chỉ rõ có được cache hay không và theo điều kiện nào.
4. **Uniform interface:** tài nguyên được định danh bằng URI, thao tác dùng ngữ nghĩa HTTP và dữ liệu được trao đổi dưới dạng biểu diễn.
5. **Layered system:** client có thể giao tiếp qua gateway, proxy hoặc lớp trung gian mà không cần biết toàn bộ kiến trúc bên trong.
6. **Code on demand:** là ràng buộc tùy chọn, cho phép server cung cấp mã thực thi cho client trong một số hệ thống.

Stateless không có nghĩa server không lưu dữ liệu người dùng hoặc không có database session. Nó có nghĩa server không dựa vào trạng thái hội thoại ngầm để hiểu request tiếp theo. Với Bearer token, mỗi request thường gửi token để server xác định danh tính và quyền. Token phải được bảo vệ, có thời hạn và được kiểm tra đúng ngữ cảnh.

REST cũng không có nghĩa mọi endpoint phải là CRUD thuần túy. Một số nghiệp vụ dạng lệnh như xác nhận thanh toán hoặc phát hành hóa đơn có thể được biểu diễn bằng tài nguyên/action endpoint có hợp đồng rõ ràng. Điều quan trọng là method, path, status code và quyền phải phản ánh chính xác tác động của request.

## 8. HTTP response và status code

Status code cho biết kết quả xử lý ở mức giao thức. Các nhóm mã thường gặp:

| Nhóm | Ý nghĩa |
|---|---|
| `1xx` | Thông tin trung gian |
| `2xx` | Request được xử lý thành công |
| `3xx` | Chuyển hướng hoặc dùng response đã cache |
| `4xx` | Request có vấn đề hoặc không được phép trong ngữ cảnh hiện tại |
| `5xx` | Server hoặc upstream gặp lỗi khi xử lý |

Một số status code API nên dùng nhất quán:

| Code | Ý nghĩa thường gặp | Ví dụ |
|---|---|---|
| `200 OK` | Request thành công và có response phù hợp | Đọc hoặc cập nhật thành công, có body |
| `201 Created` | Tạo tài nguyên thành công | Tạo đơn hàng; thường kèm `Location` |
| `202 Accepted` | Đã nhận request để xử lý bất đồng bộ | Tạo tác vụ xuất báo cáo |
| `204 No Content` | Thành công nhưng không có body | Xóa thành công hoặc cập nhật không cần trả nội dung |
| `400 Bad Request` | Request sai cú pháp hoặc không hợp lệ | JSON lỗi, query sai định dạng |
| `401 Unauthorized` | Thiếu hoặc không có thông tin xác thực hợp lệ | Token thiếu, hết hạn hoặc không hợp lệ |
| `403 Forbidden` | Đã xác thực nhưng không được phép thực hiện | Thiếu quyền chức năng |
| `404 Not Found` | Không tìm thấy tài nguyên hoặc cố ý không tiết lộ sự tồn tại | ID không tồn tại; object ngoài phạm vi theo chính sách |
| `405 Method Not Allowed` | Method không được hỗ trợ cho tài nguyên | Gửi `DELETE` tới endpoint chỉ đọc |
| `409 Conflict` | Xung đột với trạng thái hiện tại | Cập nhật đơn hàng đã khóa |
| `412 Precondition Failed` | Điều kiện request như `If-Match` không đạt | ETag đã thay đổi |
| `413 Content Too Large` | Body vượt giới hạn | Upload tệp quá lớn |
| `415 Unsupported Media Type` | Định dạng body không được hỗ trợ | Gửi XML vào endpoint chỉ nhận JSON |
| `422 Unprocessable Content` | Cú pháp hợp lệ nhưng nội dung không thể xử lý theo quy tắc | Trường dữ liệu không thỏa điều kiện nghiệp vụ |
| `429 Too Many Requests` | Vượt giới hạn tần suất | Gọi API quá nhiều lần |
| `500 Internal Server Error` | Lỗi không dự kiến ở server | Exception chưa được xử lý |
| `503 Service Unavailable` | Dịch vụ tạm thời không sẵn sàng | Bảo trì hoặc quá tải tạm thời |

`401` và `403` có ý nghĩa khác nhau. `401` nói rằng request chưa có thông tin xác thực hợp lệ; `403` nói rằng server hiểu danh tính nhưng từ chối hành động theo chính sách. Trong một số trường hợp, API có thể trả `404` thay cho `403` để tránh tiết lộ object có tồn tại hay không. Hãy chọn theo mô hình đe dọa và áp dụng nhất quán.

Không trả stack trace, câu SQL, token hoặc thông tin nội bộ trong response lỗi. Nên có cấu trúc lỗi thống nhất, mã lỗi ổn định và request ID để hỗ trợ tra cứu log. Client cần dựa vào status code và mã lỗi đã công bố, không phân tích chuỗi thông báo nội bộ.

## 9. Ví dụ triển khai với Spring Boot

Các annotation Spring MVC ánh xạ từng thành phần HTTP vào tham số Java:

| Annotation | Thành phần |
|---|---|
| `@GetMapping`, `@PostMapping`, `@PatchMapping`... | Method và path |
| `@PathVariable` | Path parameter |
| `@RequestParam` | Query parameter |
| `@RequestHeader` | Header |
| `@RequestBody` | Body |
| `@Valid` | Kích hoạt validation cho object request |

Ví dụ endpoint đọc danh sách đơn hàng:

```java
@RestController
@Validated
@RequestMapping("/api/v1/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping
    public Page<OrderSummaryResponse> searchOrders(
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {

        return orderService.searchVisibleOrders(status, page, size);
    }
}
```

Đây là ví dụ rút gọn để minh họa cách ánh xạ. Trong ứng dụng thực tế, cần cấu hình method validation phù hợp với phiên bản Spring đang dùng, xử lý `Accept` theo cơ chế content negotiation của framework và lấy danh tính từ security context. Service `searchVisibleOrders` phải tự áp dụng phạm vi người dùng/tenant; không được trả mọi đơn hàng chỉ vì request có query hợp lệ.

Ví dụ endpoint cập nhật địa chỉ giao hàng:

```java
public record UpdateShippingAddressRequest(
    @NotBlank @Size(max = 120) String street,
    @NotBlank @Size(max = 80) String city
) {}
```

```java
@PatchMapping("/{orderId}/shipping-address")
public OrderResponse updateShippingAddress(
        @PathVariable UUID orderId,
        @Valid @RequestBody UpdateShippingAddressRequest request,
        @RequestHeader(name = "If-Match", required = false) String ifMatch,
        @AuthenticationPrincipal Jwt jwt) {

    UUID customerId = UUID.fromString(jwt.getSubject());
    return orderService.updateShippingAddress(
        customerId, orderId, request, ifMatch);
}
```

Service cần kiểm tra người dùng có quyền trên `orderId`, đơn hàng có đang ở trạng thái cho phép sửa hay không, và `If-Match` có khớp phiên bản hiện tại nếu API yêu cầu optimistic concurrency không. DTO giới hạn các trường được cập nhật; client không thể gửi `ownerId`, `totalAmount` hoặc `paymentStatus` qua request này.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Path có UUID nên object an toàn | ID không thay thế authorization; phải kiểm tra quyền trên object |
| `GET` không thay đổi dữ liệu nên không có rủi ro | GET vẫn có thể lộ dữ liệu, tạo tải lớn hoặc bị lạm dụng để dò object |
| CORS chặn người lạ gọi API | CORS chủ yếu giới hạn JavaScript trong trình duyệt đọc response cross-origin; không phải cơ chế xác thực |
| Đã dùng HTTPS nên có thể gửi token qua query | URL có thể bị ghi log hoặc lưu lịch sử; hãy dùng header/cookie phù hợp và bảo vệ bí mật |
| Client gửi `role=ADMIN` thì server có thể dùng để phân quyền | Quyền phải đến từ danh tính và chính sách đáng tin cậy phía server |
| `PUT`, `DELETE` gửi lặp sẽ luôn an toàn | Idempotency chỉ nói về hiệu quả trạng thái dự kiến; vẫn cần authorization, validation và chống lạm dụng |
| `Content-Type: application/json` chứng minh body an toàn | Header chỉ khai báo định dạng; nội dung vẫn cần parse, validate và giới hạn tài nguyên |
| Ẩn nút trong frontend là đã bảo vệ method | Request có thể được gửi trực tiếp; server phải kiểm tra mọi method |

## 11. Kiểm thử request và hợp đồng HTTP

Với mỗi endpoint, hãy kiểm tra cả request hợp lệ lẫn các biến thể sai hoặc vượt quyền:

1. Gửi đúng method, path, query, header và body; xác nhận status code, response schema và side effect.
2. Gửi method không hỗ trợ; xác nhận server từ chối đúng cách và không thực hiện tác động nghiệp vụ.
3. Thay path ID bằng ID của người dùng hoặc tenant khác; xác nhận không đọc hoặc sửa được object ngoài phạm vi.
4. Thay query filter, sort, page và size bằng giá trị sai, lặp hoặc vượt giới hạn; xác nhận server xử lý rõ ràng và không tạo truy vấn tốn kém.
5. Bỏ, làm sai hoặc giả mạo header xác thực; xác nhận request bị từ chối và header tùy chỉnh không thể giả danh người dùng.
6. Gửi body thiếu trường, sai kiểu, thêm thuộc tính nhạy cảm, JSON quá lớn hoặc Content-Type không hỗ trợ; xác nhận validation và giới hạn được thực thi.
7. Kiểm tra response có lộ trường nội bộ, token, thông tin cá nhân hoặc chi tiết exception không.
8. Gửi request lặp hoặc đồng thời cho thao tác tạo, cập nhật, thanh toán và xóa; xác nhận idempotency và trạng thái nghiệp vụ đúng theo hợp đồng.

Có thể dùng curl để quan sát request và response:

```bash
curl -i \
  -X GET \
  'https://api.example.com/api/v1/orders?status=SHIPPED&page=0&size=20' \
  -H 'Authorization: Bearer <access-token>' \
  -H 'Accept: application/json'
```

```bash
curl -i \
  -X PATCH \
  'https://api.example.com/api/v1/orders/8f12/shipping-address' \
  -H 'Authorization: Bearer <access-token>' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"street":"12 Nguyen Van Linh","city":"Da Nang"}'
```

Không đưa token thật vào shell history, script chia sẻ hoặc log CI. Dùng credential test có phạm vi và thời hạn phù hợp.

## 12. Checklist đọc và thiết kế một HTTP API

- [ ] Method thể hiện đúng ý nghĩa đọc, tạo, thay thế, cập nhật một phần hoặc xóa.
- [ ] Path định danh tài nguyên rõ ràng; path parameter được parse và validation.
- [ ] Query chỉ nhận filter, phân trang, sort và tùy chọn đã được công bố; có giới hạn kích thước và độ phức tạp.
- [ ] Header được phân loại theo mục đích; danh tính và quyền không lấy từ header tùy ý do client gửi.
- [ ] Body có Content-Type được hỗ trợ, schema rõ ràng, DTO allowlist và giới hạn kích thước.
- [ ] Response có status code, Content-Type, cache policy và trường dữ liệu phù hợp.
- [ ] Mọi request đều được xác thực và phân quyền theo endpoint, method, object và thuộc tính.
- [ ] CORS, cookie và CSRF được cấu hình theo mô hình client thực tế; không coi CORS là authorization.
- [ ] Request lỗi không làm lộ bí mật, stack trace hoặc dữ liệu nội bộ.
- [ ] Test bao gồm method sai, ID ngoài phạm vi, query bất thường, header giả mạo, body không hợp lệ và request lặp.

## Kết luận

Method, path, query, header và body tạo nên hợp đồng HTTP mà client và server cùng tuân theo. Đọc đúng từng thành phần giúp thiết kế endpoint rõ ràng, validation nhất quán và xử lý lỗi dễ dự đoán. Trong một API an toàn, server không chỉ parse request thành công mà còn xác minh danh tính, quyền trên chức năng và object, thuộc tính được phép, trạng thái nghiệp vụ và giới hạn tài nguyên trước khi thực hiện hành động hoặc trả dữ liệu.

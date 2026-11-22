# Đọc trao đổi HTTP thực tế bằng curl hoặc công cụ phát triển

Một màn hình hiển thị “Không tải được đơn hàng” chưa cho biết vấn đề nằm ở đâu. Trình duyệt có gửi request không? API có trả về `401` vì thiếu thông tin xác thực, `404` vì sai URI, hay `200` với dữ liệu mà giao diện không hiểu? Muốn trả lời, cần đọc được trao đổi HTTP giữa client và server.

Trong module `INTEGRATION_API_REST`, kỹ năng này nối kiến thức nền tảng HTTP với việc thiết kế resource, URI, phương thức, mã trạng thái và hợp đồng dữ liệu. Bạn sẽ dùng `curl` để tạo request có kiểm soát, dùng công cụ phát triển của trình duyệt để quan sát hành vi của ứng dụng, rồi đối chiếu hai nguồn bằng chứng. Các bước áp dụng được cho REST API viết bằng Java/Spring hoặc công nghệ tương đương.

Sau bài học, bạn có thể:

- Tách một trao đổi thành phương thức, URL, request headers, request body, mã trạng thái, response headers và response body.
- Chọn đúng tùy chọn `curl` để xem dữ liệu cần thiết mà vẫn hiểu request thực sự được gửi đi.
- Đọc một lần tải dữ liệu trong Network panel, kể cả redirect, cache và CORS preflight.
- Phân biệt lỗi kết nối, lỗi HTTP, lỗi hợp đồng dữ liệu và lỗi do trình duyệt áp dụng chính sách.
- Ghi lại bằng chứng đủ để tái hiện vấn đề mà không làm lộ token, cookie hoặc dữ liệu cá nhân.

## 1. Chuẩn bị tình huống quan sát

Giả sử một dịch vụ bán hàng cung cấp các endpoint:

| Request | Ý nghĩa trong ví dụ |
| --- | --- |
| `GET /api/products/42` | Đọc sản phẩm có mã `42` |
| `GET /api/products?limit=2&sort=id` | Đọc một trang danh sách sản phẩm |
| `POST /api/orders` | Tạo đơn hàng |
| `GET /api/orders/ord-107` | Đọc đơn hàng vừa tạo |

Các địa chỉ, mã tài nguyên, token và kết quả trong bài là dữ liệu minh họa. Những endpoint này không được bài học tự khởi tạo. Để thực hành, dùng API local hoặc môi trường thử nghiệm mà bạn được phép truy cập, rồi thay URL và dữ liệu cho đúng hợp đồng của API đó. Không giả định một API bất kỳ sẽ trả chính xác các header trong ví dụ.

Các lệnh trong khối `bash` dùng cú pháp Bash, phù hợp với Git Bash, WSL hoặc terminal tương đương. Kiểm tra công cụ bằng:

```bash
curl --version
```

Trên Windows PowerShell, dùng tên `curl.exe` để gọi đúng chương trình curl, vì một số môi trường có alias `curl` trỏ đến lệnh khác:

```powershell
curl.exe --version
curl.exe -sS -v "http://localhost:8080/api/products/42"
```

Lệnh nhiều dòng và cách truyền dấu nháy trong JSON phụ thuộc shell. Không sao chép nguyên cú pháp xuống dòng `\` của Bash sang PowerShell. Khi dùng URL có `&`, luôn đặt toàn bộ URL trong dấu nháy để shell không tách nó thành thao tác khác.

## 2. Nhìn cấu trúc trước khi đọc chi tiết

### 2.1. Request gồm những gì?

Một request được biểu diễn theo dạng văn bản HTTP/1.1 có thể như sau:

```http
GET /api/products/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
X-Request-ID: demo-read-001

```

Đọc lần lượt:

1. `GET` là phương thức: client muốn đọc biểu diễn của resource.
2. `/api/products/42` là request target trong dạng kết nối trực tiếp thông thường. Scheme `http` và authority `localhost:8080` nằm trong URL dùng để tạo kết nối; header `Host` thể hiện authority ở HTTP/1.1.
3. `HTTP/1.1` là phiên bản giao thức trong cách biểu diễn này.
4. `Accept: application/json` thể hiện loại biểu diễn client mong muốn nhận.
5. `X-Request-ID` là header quy ước của ứng dụng trong ví dụ, dùng để liên hệ request với log.
6. Dòng trống kết thúc phần header. Request GET này không gửi body.

Với URL `http://localhost:8080/api/products?limit=2&sort=id`, phần `?limit=2&sort=id` là query string. Nó không phải JSON body. Khi chẩn đoán phân trang, phải kiểm tra cả tên tham số, giá trị và thứ tự sắp xếp mà server hiểu.

### 2.2. Response gồm những gì?

Server có thể trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=60
ETag: "product-42-v7"
X-Request-ID: demo-read-001

{"id":42,"name":"Bàn phím","price":{"amount":450000,"currency":"VND"}}
```

Ở đây:

- `200` cho biết kết quả xử lý request theo ngữ nghĩa HTTP.
- `Content-Type` mô tả kiểu dữ liệu của body đang được gửi về.
- `Cache-Control` đưa ra chỉ dẫn cache; trong ví dụ, private cache có thể dùng response khi còn fresh trong thời gian cho phép, còn shared cache không được lưu response này.
- `ETag` là validator của biểu diễn, hữu ích khi kiểm tra dữ liệu trong cache còn phù hợp hay không.
- `X-Request-ID` hỗ trợ tìm đúng log nếu các thành phần trong hệ thống truyền và ghi lại giá trị này.
- Dòng trống tách header khỏi body JSON.

`Accept` của request và `Content-Type` của response có vai trò khác nhau. Khi client gửi JSON trong request, request cũng cần `Content-Type` mô tả JSON đó. Không suy ra kiểu của request body từ `Accept`.

### 2.3. Đây là cách trình bày để con người đọc

HTTP/2 và HTTP/3 không truyền nguyên các dòng văn bản trên theo định dạng HTTP/1.1. Công cụ có thể trình bày lại thông tin thành dạng dễ đọc, chẳng hạn `HTTP/2 200` hoặc các pseudo-header `:method`, `:path`, `:authority`, `:scheme`, `:status`.

Vì vậy, không coi dấu nháy, chữ hoa/thường, thứ tự header hoặc reason phrase như `OK` trong cửa sổ công cụ là toàn bộ byte thật trên đường truyền. Tên field HTTP không phân biệt hoa thường; giá trị của từng field có quy tắc riêng. Khi đọc REST API, trước hết xác định đúng phương thức, đích, trạng thái, các header có ý nghĩa và body đã được công cụ giải mã.

## 3. Chọn chế độ quan sát của curl

Chạy lệnh sau thường chỉ cho thấy response body:

```bash
curl 'http://localhost:8080/api/products/42'
```

Để đọc được toàn bộ trao đổi, cần chủ động chọn thông tin hiển thị.

| Tùy chọn | Thông tin hoặc hành vi | Điểm cần nhớ |
| --- | --- | --- |
| `-i`, `--include` | Thêm response headers vào đầu output của body | Không hiển thị request headers |
| `-v`, `--verbose` | Hiện chi tiết kết nối cùng request/response headers | Thông tin verbose đi ra stderr; body mặc định đi ra stdout |
| `-sS` | Ẩn progress meter nhưng vẫn hiện thông báo lỗi của curl | Không tự biến HTTP `4xx` hoặc `5xx` thành lỗi exit code |
| `-H`, `--header` | Thêm hoặc đặt header cho request | Header có thể chứa thông tin nhạy cảm |
| `-I`, `--head` | Gửi request HEAD | Có thể nhận hành vi khác GET; không phải GET rồi giấu body |
| `-D -` | Ghi response headers ra stdout | Kết hợp với `-o` nếu cần tách phần body |
| `-o <đích>` | Ghi response body vào đích đã chọn | Đích có thể là thiết bị loại bỏ output |
| `-L`, `--location` | Theo các HTTP redirect được hỗ trợ | Có thể tạo nhiều request, cần đọc từng chặng |
| `-w`, `--write-out` | In thêm trường đo lường sau khi chuyển dữ liệu | Chọn các trường cần quan sát, tránh trộn lẫn với body |
| `--data-binary` | Gửi dữ liệu body theo cách của tùy chọn này | Thông thường khiến curl chọn POST nếu không có tùy chọn khác thay đổi phương thức |

### 3.1. Đọc cả request và response

```bash
curl -sS -v \
  -H 'Accept: application/json' \
  -H 'X-Request-ID: demo-read-001' \
  'http://localhost:8080/api/products/42'
```

Output minh họa, đã rút gọn:

```text
* Connected to localhost (...) port 8080
> GET /api/products/42 HTTP/1.1
> Host: localhost:8080
> User-Agent: curl/...
> Accept: application/json
> X-Request-ID: demo-read-001
>
< HTTP/1.1 200 OK
< Content-Type: application/json
< Cache-Control: private, max-age=60
< ETag: "product-42-v7"
< X-Request-ID: demo-read-001
<
{"id":42,"name":"Bàn phím","price":{"amount":450000,"currency":"VND"}}
```

Cách đọc các tiền tố:

- `*`: thông tin curl cung cấp về kết nối, TLS hoặc quá trình truyền; không phải header HTTP.
- `>`: thông tin request được công cụ trình bày.
- `<`: thông tin response được công cụ trình bày.
- JSON không có tiền tố trên là response body trong ví dụ.

Terminal thường hiển thị stdout và stderr cùng nhau nên bạn thấy chúng trong một vùng. Nếu chuyển hướng chỉ stdout sang một công cụ khác, phần verbose có thể vẫn xuất hiện trên terminal. Với HTTP/2, kiểu hiển thị có thể khác ví dụ; hãy đọc theo ý nghĩa thay vì dựa tuyệt đối vào định dạng dòng.

### 3.2. Chỉ xem response headers và body

```bash
curl -sS -i \
  -H 'Accept: application/json' \
  'http://localhost:8080/api/products/42'
```

Dùng `-i` khi câu hỏi là “server trả mã nào, media type gì, có header nào?”. Dùng `-v` khi cần biết thêm “client đã gửi phương thức, đường dẫn và header nào?”. Bật cả hai mà không chủ đích có thể làm phần header xuất hiện ở hai luồng output và khó đọc hơn.

### 3.3. Muốn kiểm tra GET nhưng không cần xem body

Trên Bash:

```bash
curl -sS -D - -o /dev/null \
  'http://localhost:8080/api/products/42'
```

Trên Windows PowerShell:

```powershell
curl.exe -sS -D - -o NUL "http://localhost:8080/api/products/42"
```

Hai lệnh vẫn gửi GET rồi loại bỏ body ở phía client. Ngược lại, `curl -I URL` gửi HEAD. Server, gateway hoặc cấu hình bảo mật có thể xử lý HEAD khác GET; quan sát bằng HEAD không đủ để kết luận một GET có body hoạt động đúng. HEAD cũng không làm giảm chi phí xử lý theo cùng một cách ở mọi triển khai.

## 4. Đọc một GET như kiểm tra hợp đồng dữ liệu

Với một request đọc sản phẩm, hãy đi qua sáu câu hỏi theo thứ tự:

1. **Có kết nối được không?** Có lỗi DNS, từ chối kết nối hoặc TLS trước khi nhận HTTP response không?
2. **Đích có đúng không?** Scheme, host, port, path, query có khớp môi trường và resource cần đọc không?
3. **Phương thức có đúng không?** Request thật là GET, hay công cụ hoặc redirect đã làm thay đổi điều bạn tưởng đang gửi?
4. **Trạng thái nói gì?** Ví dụ `200`, `304`, `401`, `404`, `503` cần các cách giải thích khác nhau.
5. **Header mô tả điều gì?** Kiểm tra `Content-Type`, cache, xác thực, redirect và thông tin truy vết.
6. **Body có khớp hợp đồng không?** Kiểu dữ liệu, trường bắt buộc, đơn vị tiền, cấu trúc lỗi hoặc cấu trúc phân trang có đúng không?

Ví dụ, cả hai response sau đều có thể mang `200`, nhưng ý nghĩa đối với ứng dụng khác nhau:

```json
{"id":42,"price":{"amount":450000,"currency":"VND"}}
```

```json
{"id":"42","price":"450.000 đ"}
```

Nếu hợp đồng yêu cầu `id` là số và `price` là object, response thứ hai gây lỗi tích hợp dù HTTP request đã nhận `200`. Một trang HTML đăng nhập được trả với `200` cũng không trở thành dữ liệu sản phẩm chỉ vì mã trạng thái là thành công. Đọc `Content-Type`, URL cuối cùng và body trước khi kết luận.

Với danh sách phân trang, thử:

```bash
curl -sS -i \
  -H 'Accept: application/json' \
  'http://localhost:8080/api/products?limit=2&sort=id'
```

Nếu API công bố response có `items` và `nextCursor`, hãy kiểm tra cả hai. Hai phần tử trong `items` không chứng minh đây là toàn bộ danh sách. Đọc cách API biểu diễn trang kế tiếp; không tự giả định mọi dịch vụ đều dùng `page`, `size` hay `totalElements` của một kiểu triển khai Spring cụ thể.

## 5. Quan sát request có body và kết quả tạo resource

Ví dụ Bash sau tạo một đơn hàng trong môi trường thử nghiệm:

```bash
curl -sS -v \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: demo-create-001' \
  --data-binary '{"productId":42,"quantity":2}' \
  'http://localhost:8080/api/orders'
```

Trong cấu hình này, `--data-binary` khiến curl chọn POST nên không cần thêm `-X POST`. Header `Content-Type: application/json` là phần chủ động khai báo kiểu dữ liệu; curl không tự hiểu JSON chỉ vì chuỗi có dấu `{}`. Các tùy chọn gửi dữ liệu có thể có mặc định media type khác, vì vậy phải đọc request thật trong verbose output.

Trao đổi minh họa:

```http
POST /api/orders HTTP/1.1
Host: localhost:8080
Accept: application/json
Content-Type: application/json
X-Request-ID: demo-create-001

{"productId":42,"quantity":2}
```

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/ord-107
X-Request-ID: demo-create-001

{"id":"ord-107","productId":42,"quantity":2,"status":"PENDING"}
```

Cần liên hệ ba mảnh thông tin:

- Request gửi đến collection `/api/orders` với dữ liệu tạo đơn hàng.
- `201` báo resource đã được tạo trong tình huống này.
- `Location` chỉ ra URI resource mới. Giá trị ở ví dụ là URI tương đối và được giải theo URI request; curl không tự GET địa chỉ đó chỉ vì nhận `201` cùng header `Location`.

Có thể chủ động đọc tiếp resource:

```bash
curl -sS -i 'http://localhost:8080/api/orders/ord-107'
```

Nếu client hết thời gian chờ sau khi gửi POST, chưa thể kết luận server không tạo đơn hàng. Request có thể đã được xử lý nhưng response không đến được client. Ghi nhận thời điểm, request ID và kết quả phía server; chỉ thử lại thao tác tạo theo hợp đồng idempotency của API hoặc bằng dữ liệu thử nghiệm có kiểm soát.

## 6. Đọc lỗi theo từng lớp thông tin

Giả sử gửi `quantity` bằng `0`, API có thể trả:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
X-Request-ID: demo-create-002

{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "quantity phải lớn hơn 0",
  "instance": "/api/orders",
  "errors": [
    {"field": "quantity", "message": "phải lớn hơn 0"}
  ]
}
```

Đây là một hợp đồng lỗi minh họa theo dạng Problem Details. Trường `errors` là phần mở rộng do ứng dụng quy định, không phải trường mà mọi API đều phải có. HTTP status thực tế là `400` trên response; một trường JSON tên `status` không thay thế được status của giao thức.

Hãy đọc lần lượt mã trạng thái, media type, chi tiết lỗi và request ID. Lỗi body JSON sai cú pháp, dữ liệu không qua validation và xung đột nghiệp vụ có thể được API phân loại khác nhau; đối chiếu với hợp đồng đã công bố thay vì suy ra chỉ từ một câu thông báo.

| Quan sát | Điều cần kiểm tra tiếp |
| --- | --- |
| `400 Bad Request` | Request target, tham số, JSON, kiểu dữ liệu và quy tắc validation được công bố |
| `401 Unauthorized` | Thông tin xác thực có thiếu, hết hạn hoặc không hợp lệ không; đọc `WWW-Authenticate` nếu có |
| `403 Forbidden` | Chính sách quyền, phạm vi truy cập hoặc CSRF; không tự kết luận chỉ cần đổi token |
| `404 Not Found` | Đúng host, base path, resource ID và môi trường chưa; một số API còn dùng `404` để che giấu resource |
| `405 Method Not Allowed` | Phương thức nào được hỗ trợ tại resource; response loại này phải có `Allow` theo ngữ nghĩa HTTP |
| `415 Unsupported Media Type` | Request `Content-Type` và định dạng dữ liệu có được endpoint chấp nhận không |
| `429 Too Many Requests` | Chính sách giới hạn, phạm vi áp dụng và `Retry-After` nếu được trả về |
| `500`, `502`, `503`, `504` | Thành phần phát sinh lỗi, gateway, upstream, thời điểm và correlation ID |

Trong Java/Spring, bảng quan sát này có thể dẫn tới các lớp khác nhau: mapping của controller, binding và validation, Spring Security, exception handler hoặc gateway trước ứng dụng. Chưa có log và cấu hình thì đây mới là hướng điều tra, không phải kết luận nguyên nhân. Một lỗi HTML mang `502` có thể đến từ proxy; đừng mặc định mọi response đều được controller tạo ra.

### Mã thoát của curl và HTTP status là hai thông tin khác nhau

Với cách gọi thông thường, curl có thể kết thúc với exit code `0` khi đã nhận đầy đủ một response HTTP `404` hoặc `500`. Nghĩa là thao tác truyền dữ liệu hoàn thành theo đánh giá của công cụ, còn server đã trả một HTTP status báo lỗi.

Ngược lại, lỗi DNS, kết nối hoặc TLS có thể làm curl kết thúc với mã thoát khác `0` mà chưa có HTTP response từ API. Một lần truyền cũng có thể lỗi sau khi đã nhận headers, chẳng hạn body bị ngắt giữa chừng. Vì vậy, phải đọc cả exit code, status và mức độ hoàn chỉnh của body.

Nếu dùng `--fail` để thay đổi cách curl báo lỗi HTTP, cần hiểu tùy chọn đó có thể làm mất body lỗi cần xem. Khi chẩn đoán tương tác, trước hết giữ lại response để quan sát đầy đủ thay vì chỉ nhìn kết quả thành công/thất bại của lệnh.

## 7. Redirect: một thao tác có thể tạo nhiều request

Quan sát redirect trước khi tự động theo nó:

```bash
curl -sS -i 'http://localhost:8080/old-products/42'
```

Response giả định:

```http
HTTP/1.1 302 Found
Location: /api/products/42
Content-Length: 0

```

Ở đây bạn mới quan sát request đầu và response redirect. Để xem chuỗi chuyển hướng:

```bash
curl -sS -v -L 'http://localhost:8080/old-products/42'
```

Ghi lại từng chặng:

```text
GET /old-products/42  -> 302, Location: /api/products/42
GET /api/products/42  -> 200, Content-Type: application/json
```

Những điểm dễ đọc sai:

- Chỉ nhìn `200` cuối cùng sẽ bỏ qua redirect tới nơi khác, chẳng hạn trang đăng nhập.
- Với POST, curl có thể chuyển sang GET khi theo `301`, `302` hoặc `303` tùy trường hợp và tùy chọn. `307` và `308` dùng để giữ phương thức khi chuyển hướng.
- Dùng `-X` để ép phương thức trong một chuỗi redirect có thể tạo hành vi khác điều bạn mong muốn. Hãy đọc phương thức thực tế của từng chặng.
- Chuyển host, scheme hoặc port có thể làm thay đổi đích tin cậy và cách công cụ xử lý credential. Không bật tùy chọn chuyển credential sang đích khác chỉ để làm lỗi biến mất.

Khi cần so sánh hai client, phải so sánh cả chuỗi redirect và URL cuối cùng, không chỉ URL ban đầu.

## 8. Đọc cache và conditional request qua bằng chứng

Hai lần mở cùng một trang chưa chắc tạo hai lần truy vấn giống nhau đến API. Client có thể dùng bản lưu trong cache, kiểm tra lại bản lưu hoặc nhận body mới.

### 8.1. Lấy validator từ response đầu

```bash
curl -sS -i 'http://localhost:8080/api/products/42'
```

Giả sử response là `200` kèm:

```http
Cache-Control: private, max-age=60
ETag: "product-42-v7"
```

Giá trị ETag phải được lấy nguyên vẹn từ response thực tế, gồm dấu nháy và tiền tố `W/` nếu có. Không tự tính ETag bằng cách nhìn các trường JSON.

### 8.2. Gửi điều kiện kiểm tra lại

Ví dụ Bash:

```bash
curl -sS -i \
  -H 'If-None-Match: "product-42-v7"' \
  'http://localhost:8080/api/products/42'
```

Nếu điều kiện dẫn tới kết luận biểu diễn chưa thay đổi đối với GET, server có thể trả:

```http
HTTP/1.1 304 Not Modified
ETag: "product-42-v7"
Cache-Control: private, max-age=60

```

`304` không có response body. Client có bản lưu phù hợp sẽ cập nhật metadata cần thiết và dùng lại body đã lưu. Lệnh curl đơn lẻ ở trên không tự có body sản phẩm từ lần chạy trước chỉ vì bạn đã gọi URL đó; ví dụ đang gửi validator một cách thủ công.

Nếu resource thay đổi và validator không còn khớp, server có thể trả `200` với body và ETag mới. Vì vậy:

- `200` kèm body: server đang gửi biểu diễn trong response này.
- `304`: request kiểm tra điều kiện đã nhận response từ server hoặc một thành phần xử lý tương ứng, nhưng response đó không mang lại body sản phẩm.
- Nhãn như “from memory cache” hoặc “from disk cache” trong trình duyệt: dữ liệu được phục vụ từ cache theo cách công cụ ghi nhận; không đồng nghĩa vừa nhận `304` qua mạng.

Curl thông thường không hoạt động như HTTP cache của trình duyệt. Hai lần gọi GET giống nhau bằng curl không tự mô phỏng đầy đủ hành vi cache của một trang web đang chạy.

## 9. Quan sát cùng thao tác trong Network panel

Phần này dùng Network panel của Chrome hoặc Edge làm ví dụ. Tên nhãn và cách bố trí có thể khác giữa phiên bản hoặc trình duyệt, nhưng các câu hỏi cần trả lời vẫn giống nhau.

### 9.1. Thu một lần thao tác rõ ràng

1. Mở công cụ phát triển bằng phím tắt phù hợp, thường là `F12`, rồi chọn **Network**.
2. Đảm bảo chế độ ghi request đang bật. Xóa danh sách cũ để dễ liên hệ với thao tác sắp làm.
3. Bắt đầu với bộ lọc **All**. Chỉ chuyển sang **Fetch/XHR** khi đã xác định request API cần tìm; bộ lọc hẹp có thể che mất document, redirect hoặc tài nguyên liên quan.
4. Thực hiện đúng một thao tác, ví dụ mở chi tiết sản phẩm `42`.
5. Chọn request theo host, path và thời điểm; không chỉ dựa vào một tên file ngắn.
6. Nếu thao tác làm điều hướng sang trang khác, bật **Preserve log** trước khi tái hiện để giữ lịch sử cần thiết.

Có thể bật **Disable cache** để thử một lần tải khi cơ chế cache thông thường bị vô hiệu hóa theo công cụ. Trong Chrome/Edge, tùy chọn này thường có hiệu lực khi DevTools đang mở. Khi nghiên cứu hành vi cache thực tế, hãy tắt nó và ghi rõ điều kiện quan sát. Service worker có thể tạo thêm một lớp xử lý riêng nên không dùng riêng checkbox đó để kết luận mọi cache đều bị bỏ qua.

### 9.2. Đọc từng vùng thông tin

| Vùng quan sát | Câu hỏi cần trả lời |
| --- | --- |
| Danh sách request | Có bao nhiêu request? Request nào xảy ra trước? Có OPTIONS, redirect hoặc retry không? |
| General / thông tin chung | URL, phương thức, status và nguồn dữ liệu được ghi nhận là gì? |
| Request Headers | Client gửi `Accept`, `Content-Type`, `Origin`, cookie hoặc thông tin xác thực nào? |
| Payload / Request | Query, form data hay JSON body? Giá trị thực tế có đúng không? |
| Response Headers | Media type, cache, CORS, redirect và request ID có giá trị gì? |
| Preview / Response | Dữ liệu đọc được là JSON, HTML, văn bản hay không có body? |
| Initiator | Đoạn mã hoặc tài nguyên nào khởi tạo request? |
| Timing | Thời gian nằm ở chờ gửi, kết nối, đợi byte đầu hay tải body? |

Request headers được hiển thị có thể là thông tin tạm thời, chẳng hạn công cụ ghi “Provisional headers”. Khi đó chưa đủ bằng chứng rằng toàn bộ những header ấy đã tới server. Muốn kết luận phía server nhận gì, cần đối chiếu với log hoặc dấu vết phía server được phép xem.

### 9.3. Phân biệt dữ liệu ứng dụng với kích thước truyền

Một JSON lớn sau giải nén có thể có kích thước khác số byte truyền qua mạng. Header nén, cache, phiên bản giao thức và cách công cụ thống kê đều ảnh hưởng cách hiển thị. Đọc cả tên cột và chú giải trước khi so sánh “Size” giữa curl và trình duyệt.

Tương tự, thời gian đợi byte đầu không chỉ là thời gian chạy controller. Nó có thể gồm độ trễ mạng, hàng đợi, gateway và xử lý upstream. DNS, kết nối TCP hoặc TLS có thể không xuất hiện như ở lần đầu khi trình duyệt tái sử dụng kết nối. HTTP/2 còn cho phép nhiều luồng chia sẻ một kết nối.

### 9.4. Thấy OPTIONS trước POST không có nghĩa ứng dụng gửi trùng đơn

Một ứng dụng web khác origin gọi API bằng POST có `Content-Type: application/json` hoặc header xác thực có thể kích hoạt CORS preflight. Ví dụ:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://shop.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type, authorization

```

Nếu preflight được chấp nhận và các điều kiện khác thỏa mãn, trình duyệt mới gửi request thực tế. Một OPTIONS và một POST là hai request phục vụ hai mục đích khác nhau; không phải bằng chứng của hai lần tạo đơn hàng. Ngược lại, nhiều POST thật cần được điều tra bằng Initiator, thời điểm, body và cơ chế thử lại.

Nếu preflight bị từ chối, request thực tế có thể chưa được gửi. Nếu request thực tế đã gửi nhưng response không vượt qua kiểm tra CORS, server có thể đã xử lý thao tác trong khi JavaScript không được đọc response. Hai trường hợp có hệ quả khác nhau và cần bằng chứng từ Network hoặc log để phân biệt.

## 10. So sánh request trình duyệt với curl

Một quy trình hữu ích là chọn request trong Network, dùng chức năng **Copy as cURL** phù hợp với shell rồi tái hiện trong môi trường được phép. Lệnh được sao chép có thể chứa token, cookie, dữ liệu người dùng và header của phiên đăng nhập. Kiểm tra nội dung trước khi lưu, chia sẻ hoặc dán vào công cụ khác.

Sau khi có bản tái hiện, thay từng yếu tố một để tìm khác biệt. Không xóa hàng loạt header rồi coi kết quả còn lại là cùng một request.

| Thuộc tính | Khi so sánh cần chú ý |
| --- | --- |
| Scheme, host, port | `localhost`, domain qua proxy, HTTP và HTTPS có thể đi đến các thành phần khác nhau |
| Path và query | Dấu `/` cuối, URL encoding, tên tham số, cursor và bộ lọc |
| Phương thức | GET, POST hay phương thức đã thay đổi khi theo redirect |
| Body | Cấu trúc JSON, số so với chuỗi, `null`, trường bị thiếu và dữ liệu thực tế |
| Headers mô tả dữ liệu | `Accept`, `Content-Type`, encoding và lựa chọn biểu diễn |
| Phiên và danh tính | Token, cookie, CSRF, credential mode và quyền của tài khoản |
| Cache và điều kiện | `If-None-Match`, bản cache đang có, service worker và cấu hình DevTools |
| Chính sách trình duyệt | CORS, mixed content hoặc chính sách khác ảnh hưởng việc gửi/đọc response |

Curl không thực thi CORS như JavaScript chạy trong trình duyệt. Một lệnh curl nhận `200` chỉ chứng minh request đó nhận response trong điều kiện của lệnh, không chứng minh trình duyệt được phép đọc response cho một origin cụ thể. Ngược lại, tự thêm header `Origin` vào curl chỉ giúp quan sát phản hồi của server đối với giá trị đó; nó không biến curl thành một trình duyệt có đầy đủ chính sách CORS.

Cookie và token cũng không tự được chia sẻ giữa trình duyệt và một lần chạy curl. Nếu một bên đã đăng nhập còn bên kia chưa, hai kết quả khác nhau là điều có thể giải thích được.

## 11. Dùng số đo đúng mục đích

Để xem HTTP status và tổng thời gian mà không in body, có thể dùng Bash:

```bash
curl -sS -o /dev/null \
  -w 'http_code=%{http_code}\ntime_total=%{time_total}s\n' \
  'http://localhost:8080/api/products/42'
```

Output minh họa:

```text
http_code=200
time_total=0.084123s
```

`time_total` là thời gian curl đo cho thao tác truyền; không phải riêng thời gian truy vấn database hay xử lý nghiệp vụ. Nếu dùng `-L`, tổng thời gian còn bao gồm các chặng redirect được thực hiện. Muốn so sánh với trình duyệt, phải ghi rõ cache, kết nối mới hay tái sử dụng, đích đến, vị trí chạy và chuỗi redirect.

Giá trị `http_code=000` do curl in ra không phải HTTP status hợp lệ mà server gửi. Nó thường cho biết curl chưa có HTTP response code trong kết quả quan sát. Cần xem thông báo lỗi và mã thoát, đồng thời chú ý trường hợp có proxy hoặc nhiều chặng kết nối.

Một mẫu duy nhất chưa đủ để kết luận hiệu năng. Trong phạm vi bài này, số đo giúp xác định phần cần điều tra tiếp; việc đánh giá tải, percentile và sức chịu tải cần quy trình kiểm thử riêng.

## 12. Quy trình điều tra ngắn có thể lặp lại

Khi gặp một lỗi tích hợp REST, làm theo chuỗi sau:

```text
Tái hiện đúng một thao tác
    -> Xác định request thật và các chặng liên quan
    -> Kiểm tra kết nối, URL, phương thức và dữ liệu gửi
    -> Đọc status, headers và body nhận được
    -> Đối chiếu hợp đồng API và điều kiện của client
    -> Ghi bằng chứng, rồi thay một yếu tố để kiểm tra giả thuyết
```

Những kết luận vội thường gặp:

| Kết luận vội | Cách đọc lại bằng chứng |
| --- | --- |
| “Curl chạy xong nên API thành công” | Kiểm tra HTTP status, body và exit code riêng biệt |
| “Có `200` nên frontend phải xử lý được” | Kiểm tra media type, cấu trúc dữ liệu và URL cuối |
| “Không thấy JSON nên response lỗi” | Xem request có phải HEAD hoặc status có phải `204`/`304` không |
| “Curl được, trình duyệt lỗi nên backend đúng hết” | So sánh danh tính, request, cache và chính sách trình duyệt |
| “Không thấy request trong Network nên mã không gửi” | Kiểm tra thời điểm bắt đầu ghi, bộ lọc, điều hướng và service worker |
| “TTFB cao chứng tỏ controller chậm” | Tách ảnh hưởng của mạng, proxy, hàng đợi và upstream bằng bằng chứng bổ sung |
| “Client timeout nên thử lại POST ngay” | Xác minh khả năng thao tác trước đã được xử lý và hợp đồng chống tạo trùng |

## 13. Bài thực hành quan sát

Dùng một API thử nghiệm có hợp đồng rõ ràng. Mục tiêu là thu được bằng chứng, không chỉnh server chỉ để bắt nó giống hệt các response minh họa.

### Thực hành A: đọc một resource

1. Gọi GET bằng curl với `-v` và `Accept` phù hợp.
2. Ghi lại URL, phương thức, status, `Content-Type` và cấu trúc body.
3. Thực hiện thao tác tương ứng trên ứng dụng web nếu có, rồi tìm đúng request trong Network.
4. So sánh danh tính, query và headers quan trọng giữa hai client.

Kết quả cần có: một bản mô tả chính xác trao đổi HTTP và các khác biệt đã quan sát. Nếu không có ứng dụng web, hoàn thành phần curl và ghi rõ phần trình duyệt chưa thực hiện.

### Thực hành B: đọc lỗi có chủ đích

1. Trong môi trường thử nghiệm, dùng một ID mà bạn biết không tồn tại hoặc một payload vi phạm hợp đồng đã công bố.
2. Ghi HTTP status thực tế, media type, body lỗi và request ID nếu có.
3. Nêu phần thông tin nào là bằng chứng, phần nào mới là giả thuyết nguyên nhân.

Kết quả cần có: phân biệt được lỗi kết nối với response HTTP báo lỗi; không chỉ chụp riêng một câu thông báo trong giao diện.

### Thực hành C: quan sát cache hoặc redirect nếu API hỗ trợ

1. Nếu response có ETag, lấy nguyên giá trị rồi gửi GET có `If-None-Match`.
2. Nếu endpoint có redirect, quan sát response đầu trước, sau đó dùng `-L -v` để xem cả chuỗi.
3. Trong trình duyệt, ghi rõ trạng thái Disable cache và cách công cụ báo nguồn dữ liệu.

Kết quả cần có: giải thích được body đến từ response mới, bản lưu được dùng lại sau xác thực hay cache cục bộ theo bằng chứng hiện có. Nếu API không hỗ trợ tình huống, ghi “không áp dụng” thay vì tự tạo kết quả.

## 14. Ghi báo cáo trao đổi HTTP để người khác tái hiện

Một bản ghi gọn nên chứa các trường sau:

```text
Môi trường: local / test, phiên bản ứng dụng nếu biết
Thời điểm: kèm múi giờ
Client: curl hoặc trình duyệt, phiên bản nếu liên quan
Thao tác: mở chi tiết sản phẩm 42
Request: GET http://localhost:8080/api/products/42
Query/body: không có trong ví dụ GET này
Danh tính: tài khoản thử nghiệm thuộc vai trò nào; không ghi token
Response: HTTP status, Content-Type, các header liên quan
Body quan trọng: trường hoặc đoạn lỗi đã lược bỏ dữ liệu nhạy cảm
Redirect/cache: các chặng và trạng thái công cụ đã quan sát
Request ID: giá trị nếu hệ thống cung cấp
Kỳ vọng: dựa trên hợp đồng API nào
Thực tế: điều đã quan sát được
Cách tái hiện: lệnh đã làm sạch hoặc các bước giao diện
Chưa xác minh: thông tin chưa có, chẳng hạn log của upstream
```

Trước khi chia sẻ verbose output, lệnh Copy as cURL, ảnh chụp hoặc HAR, loại bỏ `Authorization`, cookie, khóa API, tham số nhạy cảm và dữ liệu cá nhân trong cả request lẫn response. HAR có thể chứa nhiều request ngoài request đang điều tra. Chỉ giữ thông tin cần thiết để tái hiện; không thay bằng dữ liệu thật của người dùng khác.

Kỹ năng cốt lõi của bài là liên kết một hành động của ứng dụng với request thực tế và response tương ứng. Khi đọc đủ phương thức, URI, headers, status và body trong đúng điều kiện client, bạn có cơ sở để kiểm tra hợp đồng REST và chọn bước điều tra tiếp theo.
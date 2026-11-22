# Cấu trúc request, response, header và nội dung

## Mục tiêu và phạm vi

Trong chương **Nền tảng HTTP** của module **INTEGRATION_API_REST**, bài học này hướng dẫn đọc một request và một response: phần nào xác định đích, phần nào diễn đạt thao tác, phần nào là metadata và phần nào là nội dung trao đổi.

Module tập trung vào thiết kế REST API dựa trên resource, URI, phương thức và mã trạng thái HTTP, cùng hợp đồng dữ liệu rõ ràng. Hiểu cấu trúc thông điệp là nền tảng để học tiếp phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử API bằng Java/Spring hoặc công nghệ tương đương.

Sau bài học, bạn có thể:

- Tách request line hoặc status line, header section và body trong ví dụ HTTP/1.1.
- Phân biệt URI đích, query parameter, header và field trong JSON.
- Giải thích `Content-Type`, `Accept`, `Content-Length` và mã trạng thái.
- Nhận biết trường hợp không có response body, cũng như khác biệt giữa cấu trúc minh họa và cách truyền của HTTP/2 hoặc HTTP/3.
- Ánh xạ một hợp đồng HTTP sang request Java và controller Spring mà không nhầm dữ liệu nghiệp vụ với metadata giao thức.

## 1. HTTP là trao đổi thông điệp theo yêu cầu và phản hồi

Trong một tương tác HTTP thông thường, client gửi **request** để yêu cầu server xử lý, rồi nhận một **response cuối cùng** thể hiện kết quả. Có thể có response thông tin `1xx` trước response cuối cùng; vì vậy không nên coi mọi response đều là kết quả kết thúc request.

Client có thể là ứng dụng Java, trình duyệt, ứng dụng di động hoặc một service khác. Server mà client kết nối có thể là origin server, reverse proxy hoặc gateway; các lớp trung gian có thể chuyển tiếp request và response.

```text
Client  -- request -->  Gateway/proxy  -- request -->  Origin
Client  <-- response -- Gateway/proxy  <-- response -- Origin
```

Cấu trúc thông điệp và ngữ nghĩa HTTP không phụ thuộc vào việc phía server có dùng Java hay không. Một API trả JSON cũng không tự trở thành RESTful chỉ vì nó đi qua HTTP.

HTTPS dùng HTTP qua một kênh được bảo vệ bằng TLS. Các khái niệm phương thức, URI, header, status và nội dung vẫn được sử dụng; HTTPS không biến JSON thành một loại thông điệp HTTP khác.

## 2. Nhìn toàn bộ một request và response

Các ví dụ dạng văn bản trong bài dùng cú pháp **HTTP/1.1** để dễ đọc. Với các ví dụ có `Content-Length`, body JSON là đúng chuỗi một dòng hiển thị, không có ký tự xuống dòng ở cuối body.

### 2.1. Request tạo đơn hàng

```http
POST /orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json
Content-Length: 47

{"items":[{"productId":"prd-10","quantity":2}]}
```

Request được chia thành các phần:

| Phần | Giá trị trong ví dụ | Vai trò |
| --- | --- | --- |
| Request line | `POST /orders HTTP/1.1` | Phương thức, đích request và phiên bản HTTP |
| Header `Host` | `api.example.test` | Authority đích trong request HTTP/1.1 |
| Header `Content-Type` | `application/json` | Mô tả định dạng nội dung request |
| Header `Accept` | `application/json` | Nêu media type client mong nhận trong response |
| Header `Content-Length` | `47` | Số byte của nội dung request trong ví dụ |
| Dòng trống | Giữa header cuối và JSON | Kết thúc header section |
| Body | JSON chứa `items` | Dữ liệu đầu vào theo hợp đồng tạo đơn |

Tên `items`, `productId` và `quantity` do hợp đồng API định nghĩa. HTTP không biết `quantity` phải dương hoặc `productId` có tồn tại trong kho hay không.

### 2.2. Response khi tài nguyên đã được tạo

```http
HTTP/1.1 201 Created
Location: /orders/ord-123
Content-Type: application/json
Content-Length: 35

{"id":"ord-123","status":"PENDING"}
```

| Phần | Giá trị trong ví dụ | Vai trò |
| --- | --- | --- |
| Status line | `HTTP/1.1 201 Created` | Phiên bản HTTP, status code và reason phrase |
| Header `Location` | `/orders/ord-123` | Tham chiếu tới tài nguyên mới trong ví dụ |
| Header `Content-Type` | `application/json` | Mô tả định dạng nội dung response |
| Header `Content-Length` | `35` | Số byte của nội dung response |
| Body | JSON chứa `id`, `status` | Biểu diễn đơn hàng vừa tạo |

`201` nói tài nguyên đã được tạo. `PENDING` là trạng thái nghiệp vụ của đơn hàng. Hai giá trị nằm ở hai tầng ý nghĩa khác nhau: tạo đơn thành công không có nghĩa mọi bước thanh toán hoặc giao hàng đã hoàn tất.

`Location` có thể là một URI reference tương đối như ví dụ. Client phân giải nó theo URI liên quan của response; không nên mặc định mọi `Location` đều là URL tuyệt đối hoặc đều có cùng mục đích trong mọi mã trạng thái.

## 3. Request line: phương thức, request target và phiên bản

### 3.1. Cú pháp dễ gặp của HTTP/1.1

```text
METHOD SP request-target SP HTTP-version CRLF
```

`SP` là dấu cách. `CRLF` là cặp ký tự kết thúc dòng `\r\n` trong cú pháp HTTP/1.1; các code block chỉ hiển thị dòng để thuận tiện quan sát.

Ví dụ:

```http
GET /orders/ord-123?include=items HTTP/1.1
Host: api.example.test
```

- `GET`: phương thức.
- `/orders/ord-123?include=items`: request target.
- `HTTP/1.1`: phiên bản được dùng trong thông điệp minh họa.

Không nên parse thủ công bằng cách cắt chuỗi sơ sài trong ứng dụng nghiệp vụ. HTTP server và framework chịu trách nhiệm đọc cú pháp giao thức; ứng dụng nhận các thành phần đã được xử lý qua API tương ứng.

### 3.2. Phương thức không phải tên hàm Java

| Phương thức | Ngữ nghĩa khái quát |
| --- | --- |
| `GET` | Yêu cầu một biểu diễn của tài nguyên đích |
| `HEAD` | Yêu cầu metadata như khi đọc bằng `GET`, nhưng response không chứa nội dung |
| `POST` | Yêu cầu tài nguyên đích xử lý nội dung theo ngữ nghĩa của nó; thường dùng cho tạo mới hoặc gửi một thao tác |
| `PUT` | Tạo hoặc thay thế trạng thái của tài nguyên tại URI đích theo hợp đồng |
| `PATCH` | Áp dụng một tập thay đổi theo định dạng patch được quy định |
| `DELETE` | Yêu cầu loại bỏ mối liên hệ của URI đích với chức năng hiện tại của tài nguyên |

Bảng chỉ định hướng cách đọc request. Chi tiết an toàn, idempotency và lựa chọn phương thức cần được xem cùng hợp đồng nghiệp vụ.

Một method Java tên `getOrder` không tự khiến endpoint dùng `GET`. Ngược lại, `@PostMapping` sẽ ánh xạ request `POST` dù method Java mang tên khác.

### 3.3. URL ở client và request target trên đường truyền

Giả sử client sử dụng URL:

```text
https://api.example.test:8443/orders/ord-123?include=items#debug
```

| Thành phần | Giá trị | Vai trò |
| --- | --- | --- |
| Scheme | `https` | Cách truy cập gắn với HTTP qua TLS |
| Host và port | `api.example.test:8443` | Authority đích |
| Path | `/orders/ord-123` | Đường dẫn tài nguyên |
| Query | `include=items` | Phần query của URI |
| Fragment | `debug` | Thông tin fragment; không được gửi trong request target HTTP |

Khi client gửi trực tiếp theo dạng request target thông thường của HTTP/1.1:

```http
GET /orders/ord-123?include=items HTTP/1.1
Host: api.example.test:8443
```

Scheme không xuất hiện trong request line này, còn fragment không được gửi đi. Một số tình huống như gửi qua forward proxy hoặc dùng `CONNECT` có dạng request target khác; không nên coi dạng path và query là dạng duy nhất của mọi request HTTP/1.1.

HTTP/1.1 yêu cầu thông tin `Host` hợp lệ. Một server có thể phục vụ nhiều tên miền trên cùng hạ tầng, nên chỉ biết địa chỉ kết nối chưa đủ phân biệt mọi đích ứng dụng.

### 3.4. Path parameter và query parameter

Trong tài liệu API, mẫu `/orders/{orderId}` diễn đạt một vị trí biến. Request thực tế dùng `/orders/ord-123`, không gửi nguyên `{orderId}` như một placeholder.

Một query thường gặp:

```text
/orders?status=PENDING&page=1&size=20
```

Theo quy ước của hợp đồng này:

- `status` là bộ lọc.
- `page` và `size` là tham số phân trang.
- Giá trị đến qua URI dưới dạng văn bản; việc chuyển thành số và kiểm tra miền giá trị thuộc server.

HTTP không quy định mọi API phải có `page`, đánh số trang từ 0 hay từ 1, hoặc luôn dùng `&` và `=` theo cùng một mô hình dữ liệu. Hợp đồng và thư viện mã hóa query phải thống nhất cách diễn giải.

Không tự nối dữ liệu người dùng vào URI mà bỏ qua encoding. Các ký tự như dấu cách, `&` hoặc `/` có thể cần mã hóa tùy vị trí và mục đích; thư viện URI builder giúp giữ đúng ranh giới thành phần. Dấu `+` cũng không có nghĩa “dấu cách” trong mọi thành phần URI và mọi cách mã hóa.

## 4. Header: metadata có quy tắc riêng

### 4.1. Cấu trúc một field trong HTTP/1.1

```text
Field-Name: field-value
```

Ví dụ:

```http
Content-Type: application/json
Accept: application/json
Authorization: Bearer <access-token>
```

Tên header không phân biệt hoa thường: `Content-Type` và `content-type` là cùng một tên field. Tuy nhiên, không được vì thế mà tùy tiện chuyển mọi giá trị thành chữ thường. Token, định danh và các giá trị khác có quy tắc so sánh riêng; access token chẳng hạn không phải một chuỗi được phép tự biến đổi.

Dấu hai chấm phân cách tên và giá trị; sender không thêm khoảng trắng trước dấu hai chấm. Framework chịu trách nhiệm tạo cú pháp hợp lệ. Header không phải một JSON object và không có quy tắc escape giống chuỗi JSON.

### 4.2. Header request, response và header xuất hiện ở cả hai

| Header | Nơi thường dùng | Ý nghĩa |
| --- | --- | --- |
| `Host` | Request HTTP/1.1 | Authority đích |
| `Accept` | Request | Media type client có thể chấp nhận cho response |
| `Authorization` | Request | Thông tin xác thực theo một cơ chế đã định nghĩa |
| `If-None-Match` | Request | Điều kiện so sánh validator, thường dùng khi xác minh cache |
| `Location` | Response | URI reference có ý nghĩa theo status và hợp đồng |
| `ETag` | Response | Validator của biểu diễn |
| `WWW-Authenticate` | Response | Thông tin challenge của cơ chế xác thực |
| `Set-Cookie` | Response | Yêu cầu user agent lưu cookie theo các thuộc tính quy định |
| `Content-Type` | Cả hai | Media type của nội dung đang gửi |
| `Content-Length` | Cả hai, khi được phép | Độ dài nội dung tính bằng byte |
| `Cache-Control` | Cả hai | Chỉ thị cache; ý nghĩa cụ thể phụ thuộc request hay response |

Đây là bảng để đọc thông điệp, không phải danh sách đầy đủ. Cùng một tên header ở request và response không có nghĩa hai phía luôn dùng nó với cùng vai trò.

### 4.3. Content-Type và Accept trả lời hai câu hỏi khác nhau

```http
Content-Type: application/json
Accept: application/json
```

Trong một request tạo đơn:

- `Content-Type` trả lời: **body tôi đang gửi có định dạng gì?**
- `Accept` trả lời: **tôi có thể nhận những định dạng response nào?**

Client gửi JSON nhưng muốn nhận một định dạng khác là điều có thể, nếu server hỗ trợ hợp đồng đó. Đặt `Accept: application/json` không làm một body XML hoặc văn bản tự trở thành JSON.

Nếu media type của request không được hỗ trợ, server có thể trả `415 Unsupported Media Type`. Nếu không thể cung cấp biểu diễn đáp ứng yêu cầu negotiation theo chính sách của endpoint, server có thể trả `406 Not Acceptable`. Cần phân biệt hai lỗi này với JSON sai cú pháp hoặc dữ liệu nghiệp vụ không hợp lệ.

Nếu không có `Accept`, không thể suy ra client chỉ chấp nhận JSON. Hợp đồng và quy tắc negotiation của server xác định biểu diễn được trả.

### 4.4. Một header có thể có nhiều giá trị nhưng không ghép tùy ý

Một số header có cú pháp danh sách, chẳng hạn:

```http
Accept: application/json, application/problem+json
```

Một số field có thể xuất hiện nhiều lần và được xử lý theo quy tắc riêng. Đặc biệt, không gộp các dòng `Set-Cookie` thành một chuỗi phân cách bằng dấu phẩy như thể đó là một danh sách thông thường.

Ứng dụng nên dùng API đọc header của thư viện thay vì giả định mỗi tên luôn ánh xạ đúng một chuỗi đơn. Khi triển khai gateway, cũng cần giữ đúng quy tắc chuyển tiếp và không làm mất metadata của các lớp khác.

## 5. Body: nội dung không tự mô tả hết hợp đồng

### 5.1. Body có thể là nhiều loại dữ liệu

Body có thể là JSON, XML, văn bản, tệp nhị phân, dữ liệu form hoặc các phần của một nội dung multipart. HTTP không bắt buộc body phải là JSON.

Ví dụ các media type:

| Content-Type | Nội dung thường gặp |
| --- | --- |
| `application/json` | Dữ liệu JSON |
| `application/problem+json` | Một biểu diễn problem details bằng JSON |
| `text/plain; charset=utf-8` | Văn bản theo mã hóa đã nêu |
| `application/pdf` | Tài liệu PDF |
| `application/octet-stream` | Dữ liệu nhị phân tổng quát |
| `multipart/form-data; boundary=example-boundary` | Nhiều phần dữ liệu, thường dùng cho form hoặc upload |

Với multipart, `boundary` là thông tin quan trọng để tách các phần; không chỉ đặt `Content-Type: multipart/form-data` rồi gửi một body tùy ý. Thư viện tạo multipart thường chịu trách nhiệm sinh boundary và body tương ứng.

### 5.2. Cú pháp JSON và quy tắc nghiệp vụ là hai lớp

```json
{
  "items": [
    { "productId": "prd-10", "quantity": 2 }
  ]
}
```

JSON hợp lệ chỉ cho biết cấu trúc có thể được phân tích theo cú pháp JSON. Hợp đồng còn phải định nghĩa:

- `items` bắt buộc hay tùy chọn, có được rỗng không.
- `productId` là một chuỗi định danh theo quy tắc nào.
- `quantity` là số nguyên và nằm trong phạm vi nào.
- Field không được khai báo bị bỏ qua hay bị từ chối.
- `null`, thiếu field và chuỗi rỗng có ý nghĩa gì.

`{"quantity":2}` và `{"quantity":"2"}` khác kiểu dữ liệu. Không nên dựa vào khả năng tự chuyển kiểu của một thư viện để thay cho hợp đồng được công bố.

### 5.3. Request không bắt buộc phải có body

Một request đọc thường chỉ cần URI và header:

```http
GET /orders/ord-123 HTTP/1.1
Host: api.example.test
Accept: application/json
```

Không cần thêm `{}` chỉ để request “đủ cấu trúc”. Trong HTTP/1.1, request không có `Content-Length` hoặc `Transfer-Encoding` được xác định là không có message body theo quy tắc framing.

Nội dung trong request `GET` không có ngữ nghĩa được định nghĩa chung và có thể bị các thành phần từ chối hoặc xử lý khác nhau. Với API thông thường, hãy diễn đạt điều kiện đọc qua URI hoặc thiết kế một operation tìm kiếm riêng có hợp đồng phù hợp, thay vì mặc định mọi client và proxy sẽ hiểu body của `GET`.

Tương tự, sự có mặt của body không tự quyết định phương thức. Một `POST` không có body hoặc một `PUT` có body phải được đánh giá theo ngữ nghĩa và hợp đồng, không chỉ theo hình dạng thông điệp.

## 6. Phân định nội dung và độ dài theo byte

### 6.1. Dòng trống phân tách header và body

Với thông điệp HTTP/1.1 dạng văn bản:

```text
start-line CRLF
header-field CRLF
header-field CRLF
CRLF
[message-body]
```

Dòng trống kết thúc header section. Không thể tiếp tục gửi một dòng `Authorization: ...` sau dòng trống rồi mong server hiểu đó vẫn là header ban đầu; lúc đó các byte đã thuộc phần tiếp theo của thông điệp theo quy tắc framing.

Trong một kết nối có thể truyền nhiều thông điệp liên tiếp. Bên nhận cần biết nội dung kết thúc ở đâu để không nhầm byte của thông điệp sau thành body của thông điệp trước.

### 6.2. Content-Length đếm byte

```http
Content-Length: 11
```

có thể mô tả body ASCII:

```json
{"ok":true}
```

Số `11` không gồm request line, status line, header hoặc dòng trống phân cách. Nó cũng không phải số field hay số ký tự theo cách đếm của ngôn ngữ lập trình.

Trong Java:

```java
String json = "{\"name\":\"Bàn phím\"}";
int utf16Units = json.length();
int utf8Bytes = json.getBytes(StandardCharsets.UTF_8).length;
```

`String.length()` đếm đơn vị mã UTF-16; đó không phải số byte của chuỗi khi gửi bằng UTF-8. Các ký tự có dấu trong ví dụ làm hai kết quả khác nhau. `StandardCharsets` thuộc `java.nio.charset`.

Nếu nội dung được nén bằng một content coding, `Content-Length` khi được gửi phải mô tả độ dài nội dung đã mã hóa đó, không phải độ dài JSON trước nén. Framing của giao thức không được tính vào giá trị này.

Trong ứng dụng thông thường, hãy để HTTP client hoặc server tính và phát header độ dài phù hợp với các byte thực sự gửi, thay vì tự đếm chuỗi rồi đặt header bằng tay.

### 6.3. Transfer-Encoding và Content-Encoding khác nhau

| Header | Ví dụ | Mô tả điều gì? |
| --- | --- | --- |
| `Content-Type` | `application/json` | Cách diễn giải kiểu nội dung sau các bước giải mã liên quan |
| `Content-Encoding` | `gzip` | Content coding áp dụng lên nội dung biểu diễn |
| `Transfer-Encoding` trong HTTP/1.1 | `chunked` | Cách mã hóa truyền thông điệp trên chặng kết nối đó |

Một response HTTP/1.1 có thể truyền body theo chunk khi không công bố độ dài trước:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Transfer-Encoding: chunked

B
{"ok":true}
0

```

Trong cách hiển thị này, các ranh giới dòng của cú pháp chunk dùng CRLF. `B` là số 11 ở hệ thập lục phân, cho biết chunk có 11 byte dữ liệu; chunk kích thước `0` kết thúc chuỗi chunk, tiếp theo là phần kết thúc theo cú pháp. Ví dụ không có trailer.

Ứng dụng nhận JSON đã được HTTP stack bỏ framing; `B` và `0` không phải field của JSON. Một lớp trung gian có thể thay đổi cách framing trên chặng tiếp theo mà vẫn giữ nguyên ý nghĩa nội dung.

Sender không gửi đồng thời `Content-Length` và `Transfer-Encoding` trong cùng thông điệp HTTP/1.1. HTTP stack phải tạo framing nhất quán; không sao chép mù quáng các header này khi tự xây proxy.

Một số response HTTP/1.1 cũng có thể được phân định bằng việc đóng kết nối theo quy tắc áp dụng. Vì vậy, không có `Content-Length` chưa đủ để kết luận mọi response đều không có body. Cần xét loại thông điệp, status và framing.

### 6.4. Có metadata nhưng không có nội dung

Các trường hợp sau không mang response body:

- Response cho `HEAD`.
- Response thông tin `1xx`.
- `204 No Content`.
- `304 Not Modified`.

Ví dụ:

```http
HTTP/1.1 204 No Content
```

Không thêm JSON `{}` sau `204`. Cũng không gửi `Content-Length` trong response `204` hoặc `1xx`.

Một số header ở response `HEAD` mô tả nội dung mà một request `GET` tương ứng sẽ nhận, dù `HEAD` không truyền nội dung đó. `Content-Length` trên `HEAD` hoặc `304`, khi được gửi đúng điều kiện của chuẩn, không có nghĩa các response đó thực sự chứa body dài như vậy.

`304` phục vụ request có điều kiện và thường dẫn đến dùng lại biểu diễn đã lưu. Nó không phải một response `200` bị cắt mất JSON, và cũng không phải thông báo chung rằng bất kỳ nghiệp vụ nào đều “không có thay đổi”.

## 7. Status line và ý nghĩa của kết quả HTTP

### 7.1. Đọc status line

```http
HTTP/1.1 404 Not Found
```

- `HTTP/1.1`: phiên bản trong cách biểu diễn này.
- `404`: mã trạng thái có ý nghĩa theo HTTP.
- `Not Found`: reason phrase để người đọc dễ hiểu.

Client dựa vào status code và hợp đồng, không parse chuỗi tiếng Anh để quyết định thành công hay thất bại. Reason phrase không xuất hiện theo cách này trong HTTP/2 hoặc HTTP/3.

### 7.2. Các nhóm status

| Nhóm | Ý nghĩa khái quát | Ví dụ |
| --- | --- | --- |
| `1xx` | Thông tin trong quá trình trao đổi | `100 Continue` |
| `2xx` | Request đã được tiếp nhận và xử lý theo ý nghĩa của status cụ thể | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` |
| `3xx` | Nhóm redirection và cơ chế liên quan | `301 Moved Permanently`, `304 Not Modified` |
| `4xx` | Request không thể được đáp ứng vì vấn đề thuộc request hoặc điều kiện phía client theo ngữ nghĩa mã | `400 Bad Request`, `401 Unauthorized`, `404 Not Found` |
| `5xx` | Server hoặc thành phần phục vụ gặp vấn đề khi xử lý | `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable` |

Không phải mọi `3xx` đều có nghĩa trình duyệt cần điều hướng sang trang khác; `304` là ví dụ rõ. `202` chỉ xác nhận đã chấp nhận xử lý, chưa bảo đảm công việc cuối cùng thành công.

### 7.3. Body lỗi và status phải thống nhất

Một response lỗi có thể dùng problem details:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Content-Length: 120

{"type":"about:blank","title":"Bad Request","status":400,"detail":"quantity must be positive","code":"INVALID_QUANTITY"}
```

Trong ví dụ:

- Mã HTTP `400` giúp client và hạ tầng nhận biết loại kết quả.
- `Content-Type` chỉ cách diễn giải body.
- Các field problem details mô tả vấn đề.
- `code` là field mở rộng theo hợp đồng ví dụ, không phải field bắt buộc của mọi response HTTP.

Nếu hợp đồng xác định request bị từ chối mà server vẫn trả `200` chỉ với một field `error`, các thành phần chỉ quan sát status có thể hiểu sai kết quả. Ngược lại, body có field tên `status` cũng không tự thay thế mã trạng thái ở lớp HTTP.

Không được mặc định body của mọi lỗi luôn là JSON theo schema của origin. Một proxy có thể trả lỗi do chính nó tạo ra; client cần kiểm tra status, header và khả năng phân tích nội dung một cách phù hợp.

### 7.4. Có response lỗi khác với không nhận được response

Nhận `503 Service Unavailable` nghĩa là client đã nhận được một response HTTP. Timeout, lỗi kết nối hoặc lỗi TLS có thể khiến client không nhận được response cuối cùng.

Không nhận được response không chứng minh server chưa thực hiện thao tác. Sau một `POST` tạo đơn, server có thể đã tạo đơn nhưng kết nối bị mất trước khi client nhận kết quả. Đây là một lý do hợp đồng retry và idempotency phải được thiết kế rõ, không thể suy ra chỉ từ cấu trúc JSON.

## 8. HTTP/2 và HTTP/3 giữ ngữ nghĩa nhưng đổi cách đóng gói

Không nên hiểu rằng mọi request trên mạng đều là một chuỗi văn bản bắt đầu bằng `GET ... HTTP/1.1`.

HTTP/2 và HTTP/3 trao đổi thông tin qua framing và cơ chế mã hóa header của từng phiên bản. Ví dụ dưới là cách biểu diễn để người đọc hiểu một tập pseudo-header và header, không phải bản chép byte thực trên đường truyền:

```text
:method: POST
:scheme: https
:authority: api.example.test
:path: /orders
content-type: application/json
accept: application/json
```

Response có pseudo-header tương ứng:

```text
:status: 201
content-type: application/json
location: /orders/ord-123
```

Các khác biệt cần nhớ:

- Không có request line hoặc status line dạng văn bản giống HTTP/1.1 trên wire.
- Tên field trong HTTP/2 và HTTP/3 dùng chữ thường theo quy tắc của giao thức.
- Không dùng `Transfer-Encoding: chunked` để phân định nội dung như HTTP/1.1; nội dung đi trong cơ chế framing của phiên bản tương ứng.
- HTTP/2 hỗ trợ nhiều stream trên một kết nối; HTTP/3 sử dụng QUIC. Không được suy ra mỗi request đều cần mở rồi đóng một kết nối riêng.

URI, phương thức, status, media type và hợp đồng dữ liệu vẫn là những yếu tố mà người thiết kế REST API cần hiểu. HTTP client và server chuyển chúng sang cách truyền phù hợp.

Một công cụ có thể hiển thị dòng như `HTTP/2 200` để tiện đọc. Đây là giao diện chẩn đoán của công cụ, không phải bằng chứng HTTP/2 có một status line văn bản giống HTTP/1.1.

## 9. Đọc cùng hợp đồng trong Java và Spring

### 9.1. Gửi request bằng Java HttpClient

Ví dụ dùng `java.net.http.HttpClient`, có từ JDK 11. Tên miền `.test` là địa chỉ minh họa; khi thực hành cần URI của server phù hợp.

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public class CreateOrderClient {
    public static void main(String[] args)
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newHttpClient();

        String json = "{\"items\":[{\"productId\":\"prd-10\",\"quantity\":2}]}";

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.test/orders"))
                .header("Content-Type", "application/json")
                .header("Accept",
                        "application/json, application/problem+json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        json, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        System.out.println(response.statusCode());
        System.out.println(response.headers()
                .firstValue("Content-Type")
                .orElse(""));
        System.out.println(response.body());
    }
}
```

Các thành phần tương ứng với thông điệp HTTP:

| Mã Java | Thành phần hợp đồng |
| --- | --- |
| `uri(...)` | Đích request |
| `.POST(...)` | Phương thức và nguồn cung cấp body |
| `.header("Content-Type", ...)` | Định dạng body gửi đi |
| `.header("Accept", ...)` | Các định dạng response client chấp nhận |
| `response.statusCode()` | Mã trạng thái HTTP nhận được |
| `response.headers()` | Metadata của response |
| `response.body()` | Nội dung đã được body handler đọc thành chuỗi |

HTTP client chịu trách nhiệm đóng gói request theo phiên bản được sử dụng; code trên không buộc thông điệp phải được truyền dưới dạng HTTP/1.1. Không tự thêm `Host` hoặc `Content-Length` chỉ để làm mã giống ví dụ văn bản.

`client.send(...)` không tự biến mọi status `4xx` hoặc `5xx` thành lỗi I/O. Ứng dụng phải đọc status và xử lý hợp đồng response. Ngược lại, lỗi kết nối hoặc timeout có thể được phản ánh bằng exception mà không có response cuối cùng để đọc.

Ví dụ đọc body thành chuỗi, chưa chuyển JSON thành DTO và chưa triển khai xác thực hay retry. Với API có yêu cầu xác thực, client cần gửi thông tin theo cơ chế đã được công bố.

### 9.2. Nhận request và tạo response trong Spring MVC

Giả sử ứng dụng đã có controller, service `orders`, DTO `CreateOrderRequest` và `OrderView`, cùng bộ chuyển đổi JSON phù hợp. Method minh họa:

```java
@PostMapping(
    value = "/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<OrderView> createOrder(
        @RequestBody CreateOrderRequest input) {
    OrderView created = orders.create(input);

    return ResponseEntity
            .created(URI.create("/orders/" + created.getId()))
            .body(created);
}
```

Import và triển khai service, DTO được lược bỏ. `URI` thuộc `java.net`; các kiểu HTTP và annotation còn lại thuộc Spring.

| Thành phần Spring | Vai trò |
| --- | --- |
| `@PostMapping` | Ánh xạ phương thức và đích request theo cấu hình |
| `consumes` | Ràng buộc media type nội dung request mà method nhận |
| `produces` | Tham gia chọn media type response theo negotiation |
| `@RequestBody` | Chuyển body request thành đối tượng bằng converter phù hợp |
| `ResponseEntity.created(...)` | Tạo response status `201` và header `Location` |
| `.body(created)` | Cung cấp dữ liệu để converter ghi nội dung response |

Các annotation khác giúp đọc những phần khác nhau:

- `@PathVariable` lấy một biến đã khớp trong path.
- `@RequestParam` đọc request parameter theo cơ chế của Spring, thường dùng cho query hoặc form theo ngữ cảnh.
- `@RequestHeader` đọc một header request.

Không nên coi ba nguồn đó là hoán đổi tùy ý. Một `orderId` trong JSON không tự đi vào `@PathVariable`, và một field `contentType` trong DTO không tự đặt `Content-Type` của response.

Chuyển JSON thành DTO không tự chứng minh đơn hàng hợp lệ. Validation số lượng, kiểm tra sản phẩm, xác thực, phân quyền và ánh xạ lỗi vẫn cần được triển khai phù hợp. Ví dụ chỉ tập trung vào ranh giới request–response.

## 10. Từ cấu trúc thông điệp đến hợp đồng REST API

Một hợp đồng API cần mô tả nhiều hơn schema JSON:

| Câu hỏi | Phần thông điệp hoặc quy ước cần công bố |
| --- | --- |
| Gọi tài nguyên nào? | URI, path variable và query parameter |
| Yêu cầu làm gì? | Phương thức HTTP |
| Gửi dữ liệu gì? | Request body, media type, schema và validation |
| Cần danh tính hoặc điều kiện nào? | Header hoặc cơ chế xác thực, điều kiện theo hợp đồng |
| Thành công được biểu đạt thế nào? | Status, header liên quan và schema response |
| Thất bại được biểu đạt thế nào? | Status, media type lỗi, schema lỗi và mã nghiệp vụ |
| Có dùng lại kết quả được không? | Metadata cache và validator |
| Có gửi lại thao tác được không? | Ngữ nghĩa phương thức và cơ chế idempotency nếu có |

Một số liên hệ quan trọng:

- **Phân trang:** query điều khiển tập dữ liệu; body hoặc liên kết trong header có thể mô tả phần tiếp theo theo hợp đồng.
- **Cache:** `Cache-Control`, `ETag` và request có điều kiện điều khiển việc dùng lại; một field JSON tên `cached` không thay thế chúng.
- **Idempotency:** nếu API định nghĩa khóa chống xử lý lặp trong header, server phải thực thi ý nghĩa đó. Chỉ có tên header không tự tạo cơ chế chống trùng.
- **OpenAPI:** cần mô tả cả parameter, request body, response, header và security scheme liên quan; chỉ liệt kê các model JSON là chưa đủ.
- **Kiểm thử:** cần xác minh status, header và body phối hợp đúng, không chỉ kiểm tra một field trong JSON.

HTTP thường được mô tả là stateless, nhưng điều đó không có nghĩa mỗi request phải mở một kết nối mới hoặc server không được lưu tài nguyên. Cấu trúc request cần mang đủ ngữ cảnh theo hợp đồng, còn kết nối có thể được tái sử dụng và dữ liệu nghiệp vụ vẫn được lưu ở server.

## 11. Các nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng hơn |
| --- | --- |
| URL và body là hai cách ghi cùng một thứ | URI xác định đích và query; body mang nội dung theo ngữ nghĩa request. Chúng có vai trò được hợp đồng quy định. |
| Có `Accept: application/json` thì body gửi đi là JSON | `Accept` nói về response mong muốn; `Content-Type` mô tả nội dung đang gửi. |
| Tên header không phân biệt hoa thường nên giá trị cũng vậy | Giá trị có quy tắc riêng; không biến đổi token hoặc định danh tùy ý. |
| `Content-Length` bằng `String.length()` | Header đếm byte nội dung thực sự gửi, không đếm đơn vị mã UTF-16. |
| Mọi response có body và body luôn là JSON | Có response không có nội dung, và có nhiều media type khác JSON. |
| `204` vẫn nên gửi `{}` cho nhất quán | `204` không mang body; schema client phải phản ánh điều đó. |
| `200` và `PENDING` mâu thuẫn nhau | Status HTTP và trạng thái nghiệp vụ là hai lớp ý nghĩa; phải đọc theo đúng hợp đồng. |
| `304` là body mới bị thiếu | Đây là kết quả cho request có điều kiện, không mang body và thường dùng cùng bản đã lưu. |
| Chunk size là một phần của JSON | Chunk là framing HTTP/1.1; HTTP stack loại bỏ framing trước khi ứng dụng diễn giải nội dung. |
| Gửi JSON qua HTTP là đã tuân thủ REST | Còn phải xem mô hình tài nguyên, ngữ nghĩa và các ràng buộc kiến trúc. |
| Không nhận response nghĩa là request chưa thực thi | Server có thể đã thực hiện side effect trước khi kết nối mất; cần hợp đồng retry rõ. |

Cũng cần phân biệt ba giá trị sau khi thiết kế schema:

```text
Không có nội dung
JSON null
JSON object rỗng {}
```

Chúng không phải ba cách viết tương đương. Client đọc JSON có thể xử lý `null` và `{}` khác nhau, còn response không có nội dung thì không có một JSON value để parse.

## 12. Cách đọc một tương tác HTTP có hệ thống

Khi xem log, tài liệu hoặc một response từ công cụ kiểm tra, hãy đi theo thứ tự:

1. **Đích và phương thức:** request gửi đến đâu, thao tác gì, parameter nằm ở phần nào?
2. **Phiên bản và cách hiển thị:** đang xem văn bản HTTP/1.1 hay giao diện chẩn đoán của HTTP/2 hoặc HTTP/3?
3. **Header request:** định dạng đầu vào, định dạng chấp nhận, xác thực và điều kiện liên quan là gì?
4. **Body request:** có nội dung không; có khớp media type và schema đã công bố không?
5. **Status response:** request đã hoàn tất theo nghĩa nào; đó là kết quả cuối cùng hay response thông tin?
6. **Header response:** có `Location`, validator, cache policy hoặc thông tin khác mà client phải dùng không?
7. **Body response:** có được phép có nội dung không; media type và schema có phù hợp với status không?
8. **Trường hợp không nhận kết quả:** đó là lỗi HTTP đã có response hay lỗi trao đổi khiến chưa biết kết quả thực thi?

Ví dụ, với `POST /orders` nhận `201`, `Location: /orders/ord-123` và JSON có `status: PENDING`, kết luận phù hợp là tài nguyên đơn đã được tạo và đang ở trạng thái chờ. Muốn biết thanh toán hoặc giao hàng đã hoàn tất hay chưa phải đọc tiếp hợp đồng nghiệp vụ, không thể suy ra từ việc request có JSON hoặc kết nối dùng HTTPS.

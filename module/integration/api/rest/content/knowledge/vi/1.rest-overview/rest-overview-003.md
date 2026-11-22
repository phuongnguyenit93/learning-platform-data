# Phân biệt phong cách REST với giao thức HTTP và định dạng JSON

## Mục tiêu bài học

Trong chương **Tổng quan** của module **INTEGRATION_API_REST**, bài học này giúp bạn phân biệt ba khái niệm thường xuất hiện cùng nhau nhưng đảm nhiệm ba vai trò khác nhau:

- **REST** đặt ra các ràng buộc kiến trúc cho cách các thành phần của một hệ thống phân tán tương tác.
- **HTTP** cung cấp ngữ nghĩa giao tiếp: phương thức, mã trạng thái, header và các quy tắc xử lý thông điệp.
- **JSON** cung cấp cú pháp biểu diễn dữ liệu mà các bên có thể trao đổi.

Sau bài học, bạn cần giải thích được vì sao một API dùng HTTP và trả JSON chưa đủ để được xem là tuân thủ REST; đồng thời đọc được một trao đổi API và nhận ra quyết định nào thuộc kiến trúc, giao thức hay định dạng dữ liệu.

Sự phân biệt này là nền tảng cho các phần tiếp theo của module: thiết kế resource và URI, phương thức và mã trạng thái HTTP, hợp đồng dữ liệu, phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử API với Java/Spring hoặc công nghệ tương đương.

## 1. Ba câu hỏi, ba vai trò

Giả sử ứng dụng bán hàng cần lấy thông tin một đơn hàng.

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
Accept: application/json
~~~

Máy chủ trả về:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=30

{
  "id": 42,
  "status": "CONFIRMED",
  "totalAmount": 250000,
  "currency": "VND"
}
~~~

Đây là cách trình bày thông điệp theo HTTP/1.1 để dễ đọc. Không cần hiểu rằng mọi phiên bản HTTP đều truyền thông điệp dưới đúng dạng văn bản này.

| Câu hỏi | Khái niệm liên quan | Thể hiện trong ví dụ |
|---|---|---|
| Hệ thống tổ chức tương tác quanh điều gì? | REST | Đơn hàng là resource; client truy cập một biểu diễn thông qua URI của resource |
| Client yêu cầu thao tác nào và máy chủ thông báo kết quả thế nào? | HTTP | Phương thức `GET`, mã `200`, header và các quy tắc cache |
| Dữ liệu trong body được mã hóa theo cú pháp nào? | JSON | Object chứa các trường `id`, `status`, `totalAmount`, `currency` |

Các khía cạnh này liên quan với nhau. REST có thể khai thác ngữ nghĩa HTTP để triển khai một giao diện thống nhất; HTTP có thể mang một biểu diễn JSON. Tuy nhiên, sự xuất hiện của từng thành phần không tự chứng minh rằng các thành phần còn lại đã được thiết kế đúng.

Một cách diễn đạt chính xác hơn câu “API này là JSON REST” là:

> API này được thiết kế theo hướng resource trên HTTP và sử dụng JSON làm một định dạng biểu diễn dữ liệu.

Nếu muốn khẳng định hệ thống tuân thủ REST đầy đủ, cần đánh giá thêm các ràng buộc kiến trúc, không chỉ kiểm tra ví dụ request và response.

## 2. REST là phong cách kiến trúc

**REST** là viết tắt của **Representational State Transfer**. REST mô tả một tập ràng buộc kiến trúc cho các hệ thống phân tán. Nó không phải một giao thức truyền tin, một thư viện Java hay một định dạng file.

### 2.1. Resource khác với representation

**Resource** là khái niệm mà API nhận diện và cung cấp khả năng tương tác, chẳng hạn một đơn hàng, một khách hàng hoặc một danh sách sản phẩm.

**Representation** là dữ liệu mô tả trạng thái của resource ở một thời điểm, được trao đổi giữa client và server.

Với đơn hàng có URI `/orders/42`:

- Resource là đơn hàng số 42.
- JSON trong response là một representation của đơn hàng.
- Một biểu diễn XML hoặc HTML cũng có thể mô tả cùng resource đó.
- Bản ghi trong cơ sở dữ liệu là chi tiết lưu trữ; API không bắt buộc phải lộ nguyên cấu trúc bảng ra ngoài.

Ví dụ, cơ sở dữ liệu có thể lưu `customer_id`, `internal_version` và nhiều thông tin xử lý nội bộ. Representation công khai chỉ cần chứa những trường phù hợp với hợp đồng và quyền truy cập của client.

Đây là lý do thiết kế REST không chỉ là chuyển từng bảng thành một endpoint CRUD.

### 2.2. Các ràng buộc chính của REST

| Ràng buộc | Ý nghĩa thực hành |
|---|---|
| Client–server | Tách trách nhiệm của giao diện sử dụng và phía cung cấp tài nguyên, để các bên có thể phát triển độc lập theo hợp đồng |
| Stateless | Mỗi request chứa đủ ngữ cảnh cần thiết để xử lý; server không phải dựa vào trạng thái hội thoại ngầm được giữ riêng cho client từ request trước |
| Cache | Khả năng và điều kiện tái sử dụng response phải được xác định phù hợp; một số response có thể cache, một số cần bị hạn chế hoặc cấm lưu |
| Uniform interface | Các thành phần tương tác qua một giao diện thống nhất thay vì mỗi thao tác tự có quy ước hoàn toàn riêng |
| Layered system | Tương tác cho phép các lớp trung gian như proxy hoặc gateway tham gia mà client không cần biết toàn bộ cấu trúc phía sau |
| Code on demand, tùy chọn | Server có thể gửi mã để mở rộng khả năng client; ràng buộc này không bắt buộc và thường không xuất hiện trong API dữ liệu thông thường |

**Uniform interface** bao gồm bốn khía cạnh đáng chú ý:

1. Nhận diện resource.
2. Thao tác với resource thông qua representation.
3. Thông điệp tự mô tả để bên nhận hiểu cách xử lý.
4. Hypermedia định hướng các chuyển trạng thái của ứng dụng.

Vì vậy, chỉ đặt URI bằng danh từ rồi dùng `GET`, `POST`, `PUT`, `DELETE` chưa đủ để chứng minh toàn bộ kiến trúc tuân thủ REST.

Trong thực tế, thuật ngữ “REST API” thường được dùng rộng cho các API HTTP hướng resource. Khi đánh giá một hệ thống, nên nêu rõ nó đáp ứng những đặc điểm nào. Đặc biệt, nhiều API kiểu này chưa triển khai hypermedia như một cơ chế điều hướng ứng dụng.

### 2.3. Stateless không có nghĩa là server không lưu dữ liệu

Một máy chủ vẫn có thể lưu đơn hàng, giỏ hàng, quyền truy cập hoặc bản nháp trong cơ sở dữ liệu. Đó là trạng thái của các resource hoặc dữ liệu nghiệp vụ.

Điểm cần tránh là buộc request mới phụ thuộc vào ngữ cảnh hội thoại ngầm, chẳng hạn:

~~~text
Request 1: chọn cửa hàng A và ghi vào phiên làm việc của client.
Request 2: lấy danh sách sản phẩm, nhưng không chỉ ra cửa hàng nào.
Server phải nhớ request 1 mới biết ý nghĩa request 2.
~~~

Một thiết kế rõ ngữ cảnh hơn có thể là:

~~~http
GET /stores/A/products HTTP/1.1
Host: api.example.com
Accept: application/json
~~~

Đường dẫn đã xác định phạm vi resource. Nếu cần xác thực, request còn phải mang thông tin xác thực thích hợp.

Sự có mặt của cookie hay token tự nó không quyết định hệ thống có stateless hay không. Cần xem server có bắt buộc nhớ trạng thái hội thoại của client để diễn giải request hay không. Tương tự, sử dụng JWT không tự động làm toàn bộ API tuân thủ REST.

## 3. HTTP là giao thức ứng dụng

HTTP xác định cách client và server thể hiện yêu cầu, kết quả và các metadata liên quan. HTTP không chỉ là đường truyền cho một chuỗi JSON.

Một request HTTP có những thành phần quan trọng như:

- **Method**: loại yêu cầu, chẳng hạn `GET` hoặc `POST`.
- **Request target/URI**: đích mà yêu cầu hướng đến.
- **Headers**: metadata, điều kiện, thông tin xác thực, khả năng chấp nhận nội dung…
- **Body nếu có**: dữ liệu gửi kèm yêu cầu.

Response có mã trạng thái, header và có thể có body. Body không bắt buộc luôn là JSON, thậm chí có thể không tồn tại.

### 3.1. Phương thức có ngữ nghĩa, không chỉ là tên thao tác

| Phương thức | Ngữ nghĩa khái quát | Safe | Idempotent theo ngữ nghĩa HTTP |
|---|---|---|---|
| `GET` | Lấy một representation của resource đích | Có | Có |
| `POST` | Yêu cầu resource đích xử lý nội dung gửi lên theo ngữ nghĩa riêng của nó | Không | Không được bảo đảm |
| `PUT` | Tạo hoặc thay thế trạng thái resource đích bằng nội dung được gửi | Không | Có |
| `PATCH` | Áp dụng một tập thay đổi lên resource đích | Không | Không được bảo đảm |
| `DELETE` | Gỡ liên kết giữa URI đích và chức năng/resource hiện tại của nó | Không | Có |

**Safe** nghĩa là ngữ nghĩa được yêu cầu chủ yếu là đọc, không yêu cầu thay đổi trạng thái nghiệp vụ. Máy chủ vẫn có thể ghi log hoặc thống kê khi xử lý một `GET`.

**Idempotent** nghĩa là hiệu ứng dự kiến lên server của nhiều request giống nhau tương đương với một request. Điều này không đòi hỏi mọi lần gọi phải trả cùng body hoặc mã trạng thái. Ví dụ, xóa lần đầu có thể trả `204`, còn gọi xóa lại có thể trả `404`, nhưng resource không bị “xóa thêm một lần” theo một hiệu ứng nghiệp vụ mới.

Một thao tác `PATCH` cụ thể có thể được thiết kế idempotent. Ví dụ, “đặt trạng thái thành CONFIRMED” khác với “tăng số lượng thêm 1”. Bản thân tên phương thức không bảo đảm mọi cách triển khai `PATCH` đều idempotent.

Trong bảng, `POST` không chỉ có nghĩa “tạo bản ghi”; tạo resource là một cách sử dụng rất phổ biến của nó. Khi cần chống tạo trùng do retry, API phải có thêm thiết kế phù hợp, chẳng hạn cơ chế khóa idempotency và chính sách xử lý lặp.

Ví dụ sau dùng HTTP hợp lệ về mặt hình thức nhưng đặt sai kỳ vọng của phương thức:

~~~http
GET /orders/42/delete HTTP/1.1
Host: api.example.com
~~~

Nếu request này thực sự xóa đơn hàng, nó vi phạm ngữ nghĩa safe của `GET`. Trình duyệt, crawler, bộ nạp trước hoặc thành phần trung gian có thể xử lý một liên kết `GET` với kỳ vọng rằng thao tác đó chỉ đọc. Trả JSON không sửa được vấn đề này.

### 3.2. Mã trạng thái nói về kết quả ở lớp HTTP

Một số ví dụ thường gặp:

| Mã | Ý nghĩa cần phân biệt |
|---|---|
| `200 OK` | Request thành công, thường có body biểu diễn kết quả |
| `201 Created` | Request thành công và tạo một hoặc nhiều resource |
| `204 No Content` | Request thành công và response không có nội dung body |
| `400 Bad Request` | Server không thể hoặc không muốn xử lý do lỗi được quy cho request |
| `401 Unauthorized` | Request thiếu thông tin xác thực hợp lệ cho resource đích |
| `403 Forbidden` | Server hiểu request nhưng từ chối thực hiện |
| `404 Not Found` | Không tìm thấy representation hiện tại của resource đích, hoặc server không muốn tiết lộ sự tồn tại của nó |
| `500 Internal Server Error` | Server gặp tình huống ngoài dự kiến khiến không thể hoàn thành request |

Không nên suy rằng mọi lỗi nghiệp vụ đều bắt buộc dùng cùng một mã. Cần chọn mã theo ngữ nghĩa cụ thể, sau đó mô tả lỗi trong body theo hợp đồng nhất quán.

Nếu client gọi lấy một đơn hàng không tồn tại, cách biểu đạt rõ ràng có thể là:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "ORDER_NOT_FOUND",
  "message": "Không tìm thấy đơn hàng được yêu cầu."
}
~~~

Mã `404` là thông tin HTTP; cấu trúc `code` và `message` là hợp đồng dữ liệu của API; các dấu ngoặc và chuỗi là cú pháp JSON.

Ngược lại, nếu API luôn trả `200` rồi đặt mọi kết quả thật vào trường `success` trong body, các công cụ chỉ quan sát mã HTTP sẽ khó phân biệt thành công và lỗi. Đây có thể là quy ước riêng của một hệ thống, nhưng không nên coi là cách sử dụng ngữ nghĩa HTTP đầy đủ.

### 3.3. Header có ý nghĩa độc lập với JSON

Trong ví dụ đầu bài:

~~~http
Content-Type: application/json
Cache-Control: private, max-age=30
~~~

- `Content-Type` mô tả media type của representation trong body.
- `Cache-Control` điều khiển cách cache được phép xử lý response.
- `private` giới hạn việc lưu response ở cache riêng; cache dùng chung không được lưu response đó.
- `max-age=30` cho biết khoảng thời gian freshness theo giây trong chính sách cache này.

JSON chứa một trường `"cache": true` không thay thế được header cache của HTTP. Thành phần trung gian không có nghĩa vụ hiểu quy ước riêng đó.

Tương tự, trường `"status": 404` trong JSON không tự biến một response `200 OK` thành response HTTP `404 Not Found`.

Với dữ liệu nhạy cảm hoặc yêu cầu cập nhật tức thời, chính sách cache cần được thiết kế riêng; không sao chép `max-age=30` cho mọi endpoint.

## 4. JSON là định dạng dữ liệu

JSON mô tả dữ liệu bằng object, array, string, number, boolean và `null`. Định dạng này không định nghĩa resource, phương thức HTTP, phân quyền hay quy tắc chuyển trạng thái nghiệp vụ.

Ví dụ dưới đây là một tài liệu JSON:

~~~json
{
  "id": 42,
  "createdAt": "2026-11-17T09:30:00Z",
  "totalAmount": 250000,
  "currency": "VND",
  "items": [
    {
      "productId": 7,
      "quantity": 2
    }
  ],
  "paid": false,
  "note": null
}
~~~

Chỉ nhìn tài liệu này, bạn chưa thể biết:

- Nó là request tạo đơn hay response đọc đơn.
- Nó được trao đổi qua HTTP, một hàng đợi thông điệp hay được lưu trong file.
- Client có được phép thay đổi `paid` hay không.
- Trường `totalAmount` dùng đơn vị nào và có cho phép phần thập phân hay không.
- `note: null` khác gì với việc không gửi trường `note`.
- Khi nào một đơn được phép chuyển từ trạng thái này sang trạng thái khác.

Đây là những phần cần được xác định trong hợp đồng và thiết kế nghiệp vụ.

### 4.1. JSON hợp lệ chưa chắc là dữ liệu hợp lệ

~~~json
{
  "quantity": -3,
  "currency": "UNKNOWN",
  "createdAt": "ngày mai"
}
~~~

Đoạn trên hợp lệ về cú pháp JSON. Nó vẫn có thể không hợp lệ theo hợp đồng của API:

- `quantity` phải là số nguyên dương.
- `currency` phải thuộc tập giá trị cho phép.
- `createdAt` phải có định dạng ngày giờ đã thống nhất.

JSON không có kiểu ngày giờ riêng; chuỗi ngày giờ cần một quy ước trong hợp đồng. JSON cũng không xác định cách tính tiền, cách làm tròn hay mức chính xác của thư viện đọc số.

Do đó, cần phân biệt ít nhất ba mức:

1. **Cú pháp**: body có phân tích được thành JSON hay không.
2. **Schema/hợp đồng**: trường, kiểu, giá trị bắt buộc và ràng buộc có đúng không.
3. **Nghiệp vụ**: thao tác với dữ liệu này có hợp lệ trong tình huống hiện tại và với người gọi hiện tại không.

OpenAPI có thể mô tả nhiều khía cạnh của hợp đồng HTTP và schema dữ liệu. Việc có file OpenAPI không tự chứng minh toàn bộ kiến trúc tuân thủ REST hoặc mọi quy tắc nghiệp vụ đã được triển khai.

### 4.2. Một số lưu ý cú pháp

Trong JSON chuẩn:

- Tên thuộc tính và giá trị string dùng dấu nháy kép.
- Không viết comment.
- Không đặt dấu phẩy thừa sau phần tử cuối.
- Giá trị không giới hạn ở object; array và các giá trị JSON khác cũng có thể là một tài liệu JSON.

Ví dụ JavaScript dưới đây không phải JSON chuẩn:

~~~javascript
{
  id: 42, // mã đơn hàng
}
~~~

Việc giao diện kiểm thử hiển thị được một object không có nghĩa body thực tế đã đúng cú pháp JSON hoặc header `Content-Type` đã đúng.

## 5. Quan hệ giữa REST, HTTP và JSON

### 5.1. Dùng HTTP và JSON chưa đủ để là REST

Xét một endpoint tập trung mọi lệnh:

~~~http
POST /rpc HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "action": "getOrder",
  "arguments": {
    "orderId": 42
  }
}
~~~

Thiết kế này dùng HTTP và JSON. Giao diện được tổ chức quanh việc gọi tên lệnh trong body, gần với RPC hơn một giao diện resource dùng ngữ nghĩa thống nhất của HTTP.

RPC là một lựa chọn thiết kế có mục đích sử dụng riêng. Vấn đề ở đây là không thể kết luận “REST” chỉ từ việc có `POST` và JSON. Tương tự, riêng sự xuất hiện của `POST` cũng không đủ để kết luận một API không theo REST.

Một thiết kế hướng resource cho việc đọc cùng đơn hàng có thể là:

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
Accept: application/json
~~~

Đổi URI và phương thức giúp thể hiện ý định đọc qua giao diện HTTP, nhưng đánh giá REST đầy đủ vẫn phải xét những ràng buộc đã nêu ở phần 2.

### 5.2. REST không bắt buộc JSON

Một resource có thể có nhiều representation:

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
Accept: application/xml
~~~

Nếu server hỗ trợ XML cho resource này, nó có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/xml

<order>
  <id>42</id>
  <status>CONFIRMED</status>
</order>
~~~

Định dạng XML không làm hệ thống mất các đặc điểm REST. Ngược lại, đổi XML thành JSON không tự cải thiện kiến trúc.

Hai header thường bị nhầm:

| Header | Câu hỏi nó trả lời |
|---|---|
| `Content-Type` | Nội dung mà thông điệp này đang mang thuộc media type nào? |
| `Accept` | Bên gửi request chấp nhận những media type nào cho response? |

Trong request có JSON body, client có thể gửi cả `Content-Type: application/json` và `Accept: application/json`: một header nói về dữ liệu gửi đi, header còn lại nói về dữ liệu muốn nhận.

Server chỉ có thể chọn representation mà nó thực sự hỗ trợ. Nếu không thể cung cấp representation phù hợp và không chọn bỏ qua yêu cầu thương lượng đó, server có thể trả `406 Not Acceptable`. Gửi request body bằng media type mà endpoint không hỗ trợ thường dẫn đến `415 Unsupported Media Type`. Header không tự chuyển đổi dữ liệu.

Khi response được chọn theo `Accept`, cấu hình cache thường cần `Vary: Accept` để cache phân biệt các representation theo header này.

### 5.3. HTTP không chỉ dùng cho REST

HTTP còn có thể phục vụ:

- Trang HTML và tài nguyên tĩnh.
- API RPC.
- GraphQL.
- Tải lên hoặc tải xuống file.
- Các giao diện khác có hợp đồng riêng.

Do đó, “HTTP API” là mô tả về giao tiếp, còn “REST API” là một khẳng định thêm về cách thiết kế hệ thống.

REST được mô tả ở mức phong cách kiến trúc, không đồng nhất với một phiên bản HTTP. Trong phạm vi module này, các ví dụ triển khai REST trên HTTP; cần áp dụng ngữ nghĩa của HTTP một cách nhất quán.

### 5.4. JSON không chỉ dùng trong HTTP

Một thông điệp trong hàng đợi, một file cấu hình hoặc một bản ghi xuất dữ liệu đều có thể chứa JSON. Chúng không trở thành REST vì dùng cùng định dạng với một API web.

Quan hệ cần nhớ là:

~~~text
REST: tổ chức tương tác bằng các ràng buộc kiến trúc.
  ↓ Có thể triển khai bằng cách khai thác giao diện HTTP.
HTTP: mang yêu cầu, kết quả, header và có thể có body.
  ↓ Body có thể dùng một media type JSON.
JSON: biểu diễn cấu trúc dữ liệu theo một cú pháp xác định.
~~~

Các mũi tên mô tả một cách kết hợp thường gặp, không phải quan hệ tương đương hay điều kiện đủ.

## 6. Ví dụ đọc một luồng tạo và lấy đơn hàng

Client tạo đơn hàng:

~~~http
POST /orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "customerId": 15,
  "items": [
    {
      "productId": 7,
      "quantity": 2
    }
  ]
}
~~~

Server phản hồi:

~~~http
HTTP/1.1 201 Created
Location: /orders/42
Content-Type: application/json

{
  "id": 42,
  "status": "PENDING",
  "totalAmount": 250000,
  "currency": "VND",
  "links": [
    {
      "rel": "self",
      "href": "/orders/42"
    }
  ]
}
~~~

Sau đó client có thể đọc resource mới:

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
Accept: application/json
~~~

Phân tích từng lớp:

| Quyết định | Lớp cần hiểu |
|---|---|
| Xem tập đơn hàng và từng đơn hàng là các resource | Thiết kế hướng resource trong REST |
| Dùng `POST` lên tập đơn hàng để yêu cầu tạo mới | Ánh xạ thao tác lên ngữ nghĩa HTTP |
| Dùng `201` để báo đã tạo resource | HTTP |
| Dùng `Location` để chỉ URI của resource vừa tạo | HTTP |
| Biểu diễn đơn hàng bằng object và danh sách item bằng array | JSON |
| Xác định `quantity` phải dương và server tính tổng tiền | Hợp đồng dữ liệu và nghiệp vụ |
| Cung cấp liên kết có quan hệ `self` | Một yếu tố hypermedia trong representation |

Cấu trúc `links` trên là quy ước minh họa của API, không phải trường đặc biệt do JSON tự định nghĩa. Client muốn sử dụng phải hiểu hợp đồng về quan hệ liên kết.

Một liên kết `self` chỉ giúp minh họa khả năng dẫn tới resource. Nó chưa đủ để chứng minh toàn bộ cơ chế hypermedia định hướng các chuyển trạng thái ứng dụng. Ví dụ, nếu API cung cấp các liên kết cho những hành động hiện được phép, client còn cần hiểu ý nghĩa quan hệ, cách gửi yêu cầu và dữ liệu cần thiết.

Body của request cũng không nhất thiết giống body của response. Client gửi ý định tạo đơn; server trả trạng thái đã được xác lập sau khi kiểm tra quyền, kiểm tra dữ liệu và xử lý nghiệp vụ.

## 7. Liên hệ với Java/Spring

Ví dụ tối giản sau tập trung vào một endpoint đọc đơn hàng:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<OrderView> getById(@PathVariable("id") long id) {
        OrderView order = new OrderView(id, "CONFIRMED", 250000L, "VND");
        return ResponseEntity.ok(order);
    }

    public record OrderView(
        long id,
        String status,
        long totalAmount,
        String currency
    ) {
    }
}
~~~

Đoạn mã dùng Java có hỗ trợ `record`, trong một ứng dụng Spring MVC đã cấu hình bộ chuyển đổi JSON phù hợp. Dữ liệu được tạo trực tiếp để làm rõ các khái niệm; một ứng dụng thực tế cần lấy dữ liệu qua tầng nghiệp vụ và xử lý trường hợp không tồn tại.

Các vai trò trong ví dụ:

- `@RequestMapping` và `@GetMapping` khai báo ánh xạ URI/phương thức HTTP.
- `ResponseEntity.ok(...)` tạo response với mã `200`.
- `produces` khai báo media type endpoint có thể tạo.
- Bộ chuyển đổi thông điệp HTTP của Spring, thường kết hợp Jackson, chuyển object Java thành JSON.
- `OrderView` mô tả dữ liệu trao đổi ở phía Java.

Tên annotation `@RestController` không kiểm chứng các ràng buộc REST. Một controller vẫn có thể thiết kế URI theo lệnh, lạm dụng `GET` để thay đổi dữ liệu hoặc trả mã trạng thái không phù hợp.

Tương tự, thay `produces` thành XML không đủ để hỗ trợ XML nếu ứng dụng chưa có bộ chuyển đổi và mô hình dữ liệu phù hợp.

Khi kiểm thử, cần kiểm tra từng khía cạnh: phương thức và URI, mã HTTP, header, body và quy tắc nghiệp vụ. Chỉ kiểm tra JSON có trường `id` sẽ bỏ sót nhiều lỗi quan trọng.

## 8. Những nhầm lẫn cần tránh

| Nhận định | Cách hiểu chính xác hơn |
|---|---|
| “Trả JSON là REST.” | JSON chỉ mô tả định dạng dữ liệu; cần đánh giá kiến trúc và cách tương tác |
| “Dùng HTTP là REST.” | Nhiều loại giao diện khác cũng dùng HTTP |
| “REST bắt buộc dùng JSON.” | Resource có thể được biểu diễn bằng nhiều media type |
| “REST chỉ là CRUD.” | Resource và tương tác nghiệp vụ rộng hơn thao tác trực tiếp trên bảng dữ liệu |
| “URI có danh từ là đủ.” | URI chỉ là một phần; còn ngữ nghĩa thông điệp, cache, stateless, hypermedia và các ràng buộc khác |
| “HTTP chỉ có nhiệm vụ chuyển body.” | Method, status và header đều có ngữ nghĩa mà client và thành phần trung gian dựa vào |
| “JSON hợp lệ thì request đúng.” | Còn phải đúng schema, quyền truy cập và nghiệp vụ |
| “Stateless nghĩa là không có cơ sở dữ liệu.” | Server vẫn lưu resource; điểm cần xét là sự phụ thuộc vào trạng thái hội thoại ngầm |
| “Có OpenAPI hoặc `@RestController` là đạt REST.” | Công cụ và annotation không thay cho thiết kế kiến trúc |
| “JSON hoặc REST tự bảo đảm an toàn.” | HTTPS, xác thực và phân quyền cần được thiết kế và triển khai riêng |

## 9. Tự kiểm tra

### Câu hỏi

1. API dùng `POST /rpc` và JSON chứa `action: "findProduct"`. Từ thông tin đó có kết luận được API tuân thủ REST không?
2. `GET /products/7` trả XML. XML có khiến thiết kế không thể theo REST không?
3. Response có dòng `200 OK` và body `{"status": 404}`. Mã trạng thái HTTP thực tế là gì?
4. Request JSON có `{"quantity": -1}`. Nếu phân tích JSON thành công, request đã hợp lệ hoàn toàn chưa?
5. Hai lần `DELETE /orders/42` lần lượt trả `204` và `404`. Chênh lệch mã này có tự chứng minh thao tác không idempotent không?
6. Một ứng dụng dùng `@RestController`, JWT và JSON. Cần kiểm tra gì thêm trước khi gọi nó là một triển khai REST đầy đủ?

### Gợi ý trả lời

1. Chưa. Ví dụ mới cho thấy HTTP và JSON, với giao diện gọi lệnh gần RPC. Cần đánh giá các ràng buộc kiến trúc; không suy REST từ định dạng body.
2. Không. XML là một lựa chọn representation; kiến trúc không được quyết định bởi việc chọn XML hay JSON.
3. Mã HTTP là `200`. Trường trong body là dữ liệu theo hợp đồng riêng.
4. Chưa. Giá trị còn phải đáp ứng schema và quy tắc nghiệp vụ; nếu số lượng phải dương thì request này không đạt.
5. Không. Idempotency xét hiệu ứng dự kiến trên server, không yêu cầu hai response giống nhau.
6. Cần xem cách nhận diện và tương tác với resource, ngữ nghĩa HTTP, thông điệp tự mô tả, stateless, chính sách cache, các lớp trung gian và hypermedia. Đồng thời, xác thực và phân quyền cần được kiểm tra độc lập.

Khi đọc hoặc thiết kế một API, hãy diễn đạt riêng ba điều: **hệ thống tổ chức tương tác ra sao, giao thức biểu đạt yêu cầu/kết quả thế nào, và dữ liệu được biểu diễn bằng định dạng gì**. Sự rõ ràng này giúp bạn chọn đúng công cụ để giải quyết đúng vấn đề trong các bài tiếp theo.

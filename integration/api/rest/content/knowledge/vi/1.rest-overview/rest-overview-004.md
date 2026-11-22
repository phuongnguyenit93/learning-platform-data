# RESTful API, HTTP API và API theo kiểu RPC

## Mục tiêu bài học

Trong chương **Tổng quan** của module **INTEGRATION_API_REST**, bài học này giúp bạn phân biệt ba cách gọi thường bị dùng lẫn lộn: HTTP API, RESTful API và API theo kiểu RPC. Sau bài học, bạn có thể đọc một hợp đồng API, nhận ra cách API mô hình hóa nghiệp vụ và giải thích vì sao việc dùng HTTP hoặc JSON chưa đủ để kết luận API đó tuân theo REST.

Phạm vi của module là thiết kế REST API dựa trên resource, URI, phương thức và mã trạng thái HTTP, với hợp đồng dữ liệu rõ ràng. Bài này xây dựng nền tảng để học tiếp phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử bằng Java/Spring hoặc công nghệ tương đương. Các chủ đề đó chỉ xuất hiện ở mức cần thiết để so sánh ba khái niệm.

## 1. Ba khái niệm trả lời những câu hỏi khác nhau

**HTTP API** là API mà client và server giao tiếp thông qua HTTP. Khái niệm này cho biết giao thức trao đổi; nó chưa quy định nghiệp vụ phải được biểu diễn bằng tài nguyên hay bằng lời gọi thao tác.

**REST** — Representational State Transfer — là một phong cách kiến trúc cho hệ thống phân tán, với một tập các ràng buộc. Khi áp dụng REST trên HTTP, thiết kế thường đặt tài nguyên ở trung tâm và tận dụng ngữ nghĩa chung của HTTP. **RESTful API** là cách gọi API được thiết kế theo các ràng buộc đó. Trong thực tế, mức độ tuân thủ của các API mang nhãn RESTful có thể khác nhau.

**RPC** — Remote Procedure Call — là mô hình tương tác trong đó client yêu cầu phía xa thực hiện một thủ tục hoặc phương thức. Hợp đồng thường tập trung vào tên thao tác, tham số đầu vào và kết quả trả về. RPC có thể chạy trên HTTP hoặc trên cơ chế truyền thông khác.

| Khái niệm | Câu hỏi chính | Điều khái niệm đó chưa bảo đảm |
| --- | --- | --- |
| HTTP API | Hai phía trao đổi bằng giao thức nào? | Chưa bảo đảm thiết kế theo REST, chưa quy định định dạng body |
| RESTful API | Hệ thống tổ chức tài nguyên và tương tác theo những ràng buộc nào? | Chưa thể kết luận chỉ từ một đường dẫn có danh từ |
| API kiểu RPC | Client yêu cầu thực hiện thao tác phía xa nào? | Chưa cho biết có dùng HTTP, JSON hay một giao thức RPC cụ thể |

Ví dụ, cả hai request sau đều thuộc HTTP API:

```http
GET /orders/ord-123 HTTP/1.1
Host: api.example.test
Accept: application/json
```

```http
POST /rpc HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"method":"getOrder","params":{"orderId":"ord-123"}}
```

Request thứ nhất thể hiện cách tiếp cận tài nguyên: lấy biểu diễn của đơn hàng có định danh `ord-123`. Request thứ hai thể hiện lời gọi thao tác: thực thi `getOrder` với tham số tương ứng. Ví dụ thứ hai là một hợp đồng RPC tự định nghĩa, chưa phải thông điệp JSON-RPC 2.0 hoàn chỉnh.

Hai request đủ để minh họa sự khác nhau về mô hình tương tác, nhưng chưa đủ để chứng minh toàn bộ API thứ nhất tuân thủ REST.

## 2. HTTP API: giao thức chung, nhiều cách thiết kế

HTTP cung cấp các thành phần dùng chung giữa client, server và hạ tầng trung gian:

- URI xác định đích của request.
- Phương thức như `GET`, `POST`, `PUT`, `PATCH`, `DELETE` diễn đạt ngữ nghĩa của request.
- Header mang metadata như định dạng mong muốn, điều kiện truy cập cache hoặc thông tin xác thực.
- Mã trạng thái cho biết kết quả xử lý ở lớp HTTP.
- Body có thể mang biểu diễn tài nguyên, dữ liệu đầu vào hoặc kết quả của một thao tác.

Body của HTTP API có thể là JSON, XML, văn bản, dữ liệu nhị phân hoặc định dạng khác. Một response thành công cũng có thể không có body, chẳng hạn `204 No Content`.

### 2.1. HTTP API không đồng nghĩa với JSON API

```http
GET /documents/doc-123/content HTTP/1.1
Host: api.example.test
Accept: application/pdf
```

Một API tải tài liệu có thể trả về `Content-Type: application/pdf`. Nó vẫn là HTTP API dù payload không phải JSON.

Ngược lại, JSON có thể được truyền qua một kênh không phải HTTP. Vì vậy, định dạng dữ liệu và giao thức truyền thông là hai quyết định riêng.

### 2.2. Dùng HTTP không tự động đồng nghĩa với dùng đúng ngữ nghĩa HTTP

Một hệ thống có thể công bố các endpoint như:

```http
POST /getOrder
POST /createOrder
POST /cancelOrder
```

Đây là HTTP API theo kiểu RPC qua các endpoint riêng. Nó không trở thành REST chỉ vì request và response dùng JSON.

Dùng `POST` để gửi lời gọi RPC không tự thân là sai. Tuy nhiên, các tên thao tác nằm trong URI hoặc body, nên client phải hiểu hợp đồng thao tác để biết lời gọi nào đọc dữ liệu, lời gọi nào thay đổi dữ liệu và lời gọi nào có thể gửi lại.

Ngược lại, dùng `GET /deleteOrder?id=ord-123` để xóa đơn hàng vi phạm ngữ nghĩa an toàn của `GET`. Trình duyệt, bộ thu thập dữ liệu hoặc hạ tầng có thể chủ động lấy một URI mà không mong đợi thay đổi nghiệp vụ. Sai lầm ở đây là chọn phương thức không phù hợp, không đơn thuần là đặt tên URI có động từ.

## 3. RESTful API: tài nguyên, biểu diễn và giao diện thống nhất

### 3.1. Resource không đồng nghĩa với bảng cơ sở dữ liệu

**Resource**, hay tài nguyên, là một khái niệm mà API định danh và cho phép tương tác. Nó có thể là:

- Một đơn hàng: `/orders/ord-123`.
- Một tập đơn hàng: `/orders`.
- Một lần hủy đơn hàng: `/orders/ord-123/cancellations/can-456`.
- Một tác vụ xuất báo cáo: `/report-jobs/job-789`.

Resource không bắt buộc ánh xạ trực tiếp tới một bảng hoặc một entity trong Java. Một tác vụ tính toán, một kết quả tổng hợp hoặc một quy trình nghiệp vụ cũng có thể được mô hình hóa thành tài nguyên nếu có định danh, trạng thái và vòng đời có ý nghĩa.

**Representation**, hay biểu diễn, là dữ liệu mô tả trạng thái của tài nguyên tại thời điểm trao đổi. JSON sau là một biểu diễn của đơn hàng, không phải chính đối tượng Java hoặc bản ghi database:

```json
{
  "id": "ord-123",
  "status": "PENDING",
  "items": [
    { "productId": "prd-10", "quantity": 2 }
  ]
}
```

Hợp đồng cần làm rõ ý nghĩa của `status`, các field bắt buộc, các giá trị hợp lệ và những điều client được phép thực hiện. Tên field đẹp chưa đủ tạo nên một hợp đồng rõ ràng.

### 3.2. Các ràng buộc kiến trúc của REST

| Ràng buộc | Ý nghĩa trong thiết kế API |
| --- | --- |
| Client–server | Tách trách nhiệm giao diện sử dụng và trách nhiệm cung cấp dữ liệu, dịch vụ |
| Stateless | Mỗi request mang đủ ngữ cảnh cần thiết để server hiểu yêu cầu, không phụ thuộc trạng thái phiên hội thoại đã giữ lại từ các request trước |
| Cache | Response cho biết khả năng được lưu và tái sử dụng theo ngữ nghĩa cache áp dụng |
| Uniform interface | Các bên tương tác qua một giao diện thống nhất, thay vì mỗi tài nguyên có một bộ quy tắc hoàn toàn riêng |
| Layered system | Client không cần biết nó đang kết nối trực tiếp đến server cuối hay đi qua các lớp trung gian |
| Code on demand, tùy chọn | Server có thể cung cấp mã thực thi để mở rộng khả năng của client; không phải yêu cầu bắt buộc |

Stateless không có nghĩa server không được lưu dữ liệu. Server vẫn lưu đơn hàng, tài khoản, trạng thái xử lý tác vụ hoặc dữ liệu phân quyền. Điều cần tránh là phụ thuộc vào một trạng thái hội thoại ngầm, chẳng hạn bắt buộc client đã gọi `selectCurrentOrder` trước thì một request `confirmCurrentOrder` thiếu định danh mới được hiểu đúng.

REST cũng không bắt buộc mọi response đều được cache công khai. Một response có thể không cho lưu cache; một response khác có thể chỉ được lưu trong cache riêng của client. Điểm cốt lõi là khả năng tái sử dụng phải được xác định phù hợp với dữ liệu và giao thức.

Uniform interface thường được giải thích qua bốn khía cạnh:

1. Định danh tài nguyên.
2. Thao tác tài nguyên thông qua các biểu diễn.
3. Thông điệp có đủ thông tin mô tả cách diễn giải, kết hợp với chuẩn giao thức và media type.
4. Hypermedia dẫn dắt các bước tương tác tiếp theo của ứng dụng.

Trên HTTP, URI, phương thức, mã trạng thái, header và media type cùng góp phần tạo giao diện thống nhất. Chỉ đổi `/getOrder` thành `/orders/ord-123` mới giải quyết một phần nhỏ.

### 3.3. Hypermedia và cách dùng từ RESTful trong thực tế

Một response có thể cung cấp liên kết đến chính tài nguyên và những bước tương tác có liên quan. Ví dụ minh họa sau dùng cấu trúc `_links` do API tự quy định:

```json
{
  "id": "ord-123",
  "status": "PENDING",
  "_links": {
    "self": { "href": "/orders/ord-123" },
    "cancellations": { "href": "/orders/ord-123/cancellations" }
  }
}
```

Client vẫn cần hiểu quan hệ liên kết, media type và quy tắc sử dụng do hợp đồng quy định. Chỉ thêm `_links` hoặc một URL ngẫu nhiên chưa đủ đáp ứng toàn bộ yêu cầu hypermedia. Tên `_links` ở đây cũng không có nghĩa response tự động tuân thủ một chuẩn hypermedia cụ thể.

Nhiều API trong thực tế được gọi là RESTful vì chúng thiết kế theo tài nguyên và tận dụng HTTP, dù chưa áp dụng đầy đủ hypermedia. Khi đánh giá, hãy nói cụ thể: API đã có định danh tài nguyên và ngữ nghĩa HTTP rõ ràng, còn mức độ áp dụng các ràng buộc REST khác cần xem xét thêm. Nhãn RESTful không phải chứng chỉ chất lượng.

## 4. RPC: thao tác nghiệp vụ là trung tâm của hợp đồng

Với RPC, client thường nghĩ theo dạng:

```text
getOrder(orderId)
createOrder(items)
cancelOrder(orderId, reason)
calculateShipping(orderId, destination)
```

Hợp đồng định nghĩa tên thao tác, tham số, kiểu kết quả và mô hình lỗi. Một client SDK có thể trình bày các lời gọi này như phương thức cục bộ, nhưng việc thực thi vẫn qua mạng và có thể gặp timeout, mất kết nối hoặc lỗi từ server.

### 4.1. RPC qua một endpoint HTTP

JSON-RPC 2.0 là một ví dụ về giao thức RPC dùng JSON. HTTP có thể được chọn làm cơ chế vận chuyển, nhưng bản thân JSON-RPC không chỉ dành riêng cho HTTP.

Request JSON-RPC 2.0 có định danh lời gọi:

```http
POST /rpc HTTP/1.1
Host: api.example.test
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "method": "orders.get",
  "params": { "orderId": "ord-123" },
  "id": 42
}
```

Response thành công tương ứng:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "result": {
    "id": "ord-123",
    "status": "PENDING"
  },
  "id": 42
}
```

`id` giúp ghép response với request; nó không phải khóa idempotency. Lặp lại một request tạo đơn hàng với cùng `id` không tự động bảo đảm server chỉ tạo một đơn.

Một JSON-RPC response lỗi dùng `error` thay cho `result`. Cách ánh xạ lỗi RPC sang mã trạng thái HTTP phụ thuộc hợp đồng vận chuyển; không thể suy ra tất cả API kiểu RPC đều trả `200` cho mọi tình huống.

### 4.2. RPC qua nhiều endpoint và RPC có kiểu dữ liệu

RPC không bắt buộc có một URL `/rpc`. API như `POST /orders/cancel` nhận `{ "orderId": "ord-123" }` cũng có thể mang mô hình RPC vì hợp đồng xoay quanh lời gọi thao tác.

gRPC là một ví dụ khác: hợp đồng mô tả service và các phương thức, thường dùng Protocol Buffers và HTTP/2. Từ ví dụ đó không nên suy ra mọi RPC đều dùng Protocol Buffers, mọi HTTP/2 API đều là gRPC hoặc mọi RPC đều có hiệu năng giống nhau.

RPC có thể phù hợp khi nghiệp vụ được diễn đạt tự nhiên bằng các lệnh như tính giá, tối ưu lịch giao hoặc chạy một thuật toán. Nó vẫn cần hợp đồng dữ liệu, kiểm soát lỗi, xác thực, phân quyền và chiến lược xử lý retry.

## 5. Cùng một nghiệp vụ, hai cách xây dựng hợp đồng

Xét một hệ thống đặt hàng cần tạo đơn, đọc đơn, tìm đơn và hủy đơn. Các endpoint sau là ví dụ thiết kế, không phải quy tắc bắt buộc cho mọi hệ thống.

| Nghiệp vụ | Cách tiếp cận tài nguyên trên HTTP | Cách tiếp cận RPC trên HTTP |
| --- | --- | --- |
| Đọc đơn | `GET /orders/ord-123` | `POST /rpc` gọi `orders.get` |
| Tạo đơn | `POST /orders` | `POST /rpc` gọi `orders.create` |
| Tìm đơn chờ xử lý | `GET /orders?status=PENDING` | `POST /rpc` gọi `orders.search` |
| Ghi nhận yêu cầu hủy | `POST /orders/ord-123/cancellations` | `POST /rpc` gọi `orders.cancel` |

Bảng chỉ so sánh cách biểu đạt. Hệ thống có thể triển khai bất đồng bộ, phân quyền hoặc lưu trữ rất khác nhau dù có endpoint giống nhau.

### 5.1. Tạo đơn theo cách tiếp cận tài nguyên

```http
POST /orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json

{
  "items": [
    { "productId": "prd-10", "quantity": 2 }
  ]
}
```

Nếu đơn hàng đã được tạo thành công, server có thể trả:

```http
HTTP/1.1 201 Created
Location: /orders/ord-123
Content-Type: application/json

{
  "id": "ord-123",
  "status": "PENDING",
  "items": [
    { "productId": "prd-10", "quantity": 2 }
  ]
}
```

Ở đây, `POST /orders` yêu cầu collection xử lý việc tạo thành viên mới; `Location` chỉ tới tài nguyên đã tạo. Trạng thái `PENDING` là trạng thái nghiệp vụ của đơn hàng. Nó không mâu thuẫn với `201`: đơn hàng đã tồn tại dù quy trình giao hàng chưa hoàn tất.

### 5.2. Tạo đơn theo kiểu RPC

```http
POST /rpc HTTP/1.1
Host: api.example.test
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "method": "orders.create",
  "params": {
    "items": [
      { "productId": "prd-10", "quantity": 2 }
    ]
  },
  "id": 43
}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "jsonrpc": "2.0",
  "result": {
    "orderId": "ord-123",
    "status": "PENDING"
  },
  "id": 43
}
```

Client gọi `orders.create` và đọc kết quả của thao tác. Việc endpoint HTTP trả `200` trong ví dụ này không có nghĩa API không tạo dữ liệu; kết quả nghiệp vụ nằm trong hợp đồng RPC. Nếu cần khả năng khám phá tài nguyên qua HTTP, hợp đồng vẫn có thể bổ sung URI của đơn hàng trong kết quả.

### 5.3. Hủy đơn: hiểu nghiệp vụ trước khi chọn phương thức

Có ít nhất ba cách biểu đạt một yêu cầu hủy:

- `POST /orders/ord-123/cancellations`: tạo một bản ghi hoặc yêu cầu hủy, có thể có lý do, người yêu cầu và trạng thái xử lý riêng.
- `PATCH /orders/ord-123`: thay đổi trạng thái đơn hàng bằng một định dạng patch đã được định nghĩa, nếu quy tắc nghiệp vụ cho phép.
- Lời gọi RPC `orders.cancel`: yêu cầu thực hiện một thao tác hủy được mô tả rõ bằng tham số và kết quả.

Không nên chọn `DELETE /orders/ord-123` chỉ vì muốn đơn hàng “biến mất khỏi màn hình”. `DELETE` diễn đạt việc loại bỏ mối liên hệ giữa URI đích và chức năng hiện có của tài nguyên; nó không bắt buộc phải xóa vật lý mọi dữ liệu. Trong nhiều miền nghiệp vụ, một đơn bị hủy vẫn phải tra cứu được, nên thao tác hủy và thao tác xóa là hai khái niệm khác nhau.

Việc tạo tài nguyên `cancellation` chỉ có ý nghĩa khi nó phản ánh một khái niệm trong hợp đồng. Bọc mọi động từ bằng một danh từ mới mà không xác định định danh, trạng thái và vòng đời sẽ không tự làm API tốt hơn.

## 6. Những khác biệt ảnh hưởng tới client và hạ tầng

### 6.1. An toàn và idempotency

**Safe**, hay an toàn theo ngữ nghĩa HTTP, nghĩa là client không yêu cầu thay đổi trạng thái ứng dụng khi thực hiện phương thức đó. **Idempotent**, hay lũy đẳng, nghĩa là gửi lặp lại cùng một request có cùng tác động dự định lên server như gửi một lần.

| Phương thức | Safe theo ngữ nghĩa HTTP | Idempotent theo ngữ nghĩa HTTP | Lưu ý |
| --- | --- | --- | --- |
| `GET` | Có | Có | Dùng để đọc; không dùng để đặt hàng hoặc hủy đơn |
| `PUT` | Không | Có | Tạo hoặc thay thế trạng thái tại URI đã biết theo hợp đồng |
| `DELETE` | Không | Có | Các lần gọi có thể trả mã khác nhau nhưng tác động dự định vẫn lũy đẳng |
| `POST` | Không | Không được bảo đảm | API có thể bổ sung cơ chế để một thao tác cụ thể có thể gửi lại an toàn |
| `PATCH` | Không | Không được bảo đảm | Tùy thao tác patch: gán giá trị và tăng bộ đếm có tính chất khác nhau |

Idempotency không yêu cầu mọi response giống hệt nhau. Lần `DELETE` đầu có thể trả `204`, lần sau trả `404`, trong khi trạng thái cuối cùng vẫn là không còn tài nguyên đích.

Với RPC qua `POST /rpc`, khả năng retry không thể suy ra chỉ từ tên endpoint hoặc request ID. Hợp đồng phải xác định thao tác nào có tác động phụ và cơ chế chống thực thi lặp nếu cần.

Ngay cả với API theo tài nguyên, timeout sau `POST /orders` vẫn tạo ra sự không chắc chắn: server có thể đã tạo đơn nhưng response bị mất. Phong cách REST không tự giải quyết vấn đề này; cần một hợp đồng idempotency riêng cho thao tác tạo đơn nếu muốn retry mà không tạo trùng.

### 6.2. Cache và quan sát hệ thống

`GET /orders/ord-123` có URI và phương thức giúp client, gateway và công cụ giám sát nhận biết đây là request đọc một tài nguyên. Việc thực sự cache response còn phụ thuộc header, quyền truy cập và chính sách của dữ liệu.

Một endpoint RPC chung có thể đưa mọi thao tác vào `POST /rpc`; khi đó log chỉ chứa phương thức và đường dẫn sẽ khó phân biệt `orders.get` với `orders.cancel`. Hệ thống có thể bổ sung metadata về tên thao tác vào tracing và metrics theo hợp đồng.

Không nên kết luận RPC không thể cache. Client RPC vẫn có thể cache ở cấp ứng dụng hoặc dùng cơ chế chuyên biệt. Khác biệt là mức độ có thể tận dụng ngữ nghĩa và hạ tầng HTTP sẵn có; bản thân `POST` cũng không đồng nghĩa tuyệt đối với cấm cache.

### 6.3. Mã trạng thái và lỗi

Trong API hướng tài nguyên dùng HTTP, các mã thường gặp gồm:

| Mã | Ý nghĩa phù hợp trong ví dụ |
| --- | --- |
| `200 OK` | Đọc đơn thành công hoặc trả kết quả xử lý đồng bộ |
| `201 Created` | Đã tạo tài nguyên; cung cấp `Location` khi cần chỉ URI tài nguyên mới |
| `202 Accepted` | Đã chấp nhận xử lý nhưng chưa hoàn tất; hợp đồng cần mô tả cách theo dõi kết quả |
| `204 No Content` | Thành công và không có response body |
| `400 Bad Request` | Request không hợp lệ theo cú pháp hoặc quy tắc đầu vào mà API đã công bố |
| `404 Not Found` | Không tìm thấy tài nguyên đích theo ngữ nghĩa API |
| `409 Conflict` | Yêu cầu xung đột với trạng thái hiện tại, chẳng hạn đơn đã giao không thể hủy |

Đây là tập ví dụ, không phải danh mục đầy đủ hoặc ánh xạ duy nhất cho mọi lỗi validation. Điểm quan trọng là mã HTTP và body lỗi phải nhất quán với hợp đồng.

RPC có thể có thêm mã lỗi nghiệp vụ trong payload hoặc cơ chế trạng thái riêng. Không được đồng nhất “HTTP trao đổi thành công” với “thao tác nghiệp vụ thành công”. Ngược lại, cũng không nên bỏ qua mã HTTP chỉ vì body có field `error`.

## 7. Minh họa ranh giới trong Java/Spring

Spring có thể triển khai cả API theo tài nguyên lẫn RPC qua HTTP. Annotation `@RestController` cho biết controller trả dữ liệu trực tiếp qua response theo cơ chế của Spring; nó không kiểm chứng các ràng buộc REST cho bạn.

Các đoạn dưới chỉ minh họa cách ánh xạ endpoint, không phải ứng dụng hoàn chỉnh. Import, cấu hình bean, triển khai service, validation và xử lý lỗi được lược bỏ. `OrderService` đại diện cho cùng một năng lực nghiệp vụ; `getRequired` phải được triển khai để lỗi không tìm thấy được ánh xạ phù hợp.

```java
public record OrderView(String id, String status) {}

public record GetOrderRequest(String orderId) {}

public interface OrderService {
    OrderView getRequired(String orderId);
}
```

Controller theo tài nguyên:

```java
@RestController
@RequestMapping("/orders")
public class OrderResourceController {
    private final OrderService orders;

    public OrderResourceController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    public OrderView get(@PathVariable("orderId") String orderId) {
        return orders.getRequired(orderId);
    }
}
```

Controller kiểu RPC qua một endpoint thao tác:

```java
@RestController
@RequestMapping("/rpc/orders")
public class OrderRpcController {
    private final OrderService orders;

    public OrderRpcController(OrderService orders) {
        this.orders = orders;
    }

    @PostMapping("/get")
    public OrderView get(@RequestBody GetOrderRequest request) {
        return orders.getRequired(request.orderId());
    }
}
```

Các kiểu `public` trong ví dụ cần nằm trong các file Java tương ứng; cú pháp `record` yêu cầu Java 16 trở lên. Controller RPC này dùng hợp đồng JSON tự định nghĩa, không triển khai envelope JSON-RPC 2.0 ở phần trước.

Cả hai controller có thể gọi cùng service và cùng trả JSON. Sự khác biệt nằm ở hợp đồng HTTP mà client nhìn thấy: một bên dùng định danh tài nguyên kết hợp `GET`, bên kia gửi tham số cho thao tác `get` bằng `POST`.

Việc truy xuất một đơn hàng phải kiểm tra quyền của người gọi đối với đơn đó trong cả hai thiết kế. Đặt dữ liệu trong path hay body không thay thế kiểm soát truy cập.

## 8. Chọn cách tiếp cận dựa trên nhu cầu sử dụng

| Bối cảnh | Cách tiếp cận đáng cân nhắc | Câu hỏi cần làm rõ |
| --- | --- | --- |
| API cho nhiều bên tích hợp, có các thực thể và vòng đời rõ ràng | Tài nguyên trên HTTP | Có tận dụng được phương thức, mã trạng thái, liên kết và cache nhất quán không? |
| Nghiệp vụ chủ yếu là các thao tác tính toán hoặc lệnh chuyên biệt | RPC | Tham số, kiểu kết quả, lỗi và hành vi khi retry đã rõ chưa? |
| Giao tiếp nội bộ cần code generation và hợp đồng có kiểu | RPC có schema, chẳng hạn gRPC | Công cụ, môi trường triển khai và nhu cầu streaming có phù hợp không? |
| Tác vụ dài cần theo dõi tiến độ | Tài nguyên tác vụ, hoặc RPC kèm cơ chế theo dõi | Client lấy trạng thái, kết quả và lỗi cuối cùng bằng cách nào? |

Đây là các gợi ý suy luận từ đặc điểm hợp đồng, không phải quy tắc “API bên ngoài luôn REST, API nội bộ luôn RPC”. Quyết định còn phụ thuộc người dùng API, hệ sinh thái client, yêu cầu vận hành và chi phí duy trì.

Với một thao tác như xuất báo cáo, thiết kế theo tài nguyên có thể tạo `POST /report-jobs`, sau đó đọc `GET /report-jobs/job-789`. Khi tạo tài nguyên tác vụ đã hoàn tất, server có thể trả `201` dù báo cáo đang chạy; khi chỉ chấp nhận yêu cầu để xử lý sau, `202` có thể phù hợp. Hợp đồng phải nói rõ điều gì đã hoàn thành và cách theo dõi kết quả.

Một API có thể kết hợp nhiều cách tiếp cận. Ví dụ, tài nguyên đơn hàng dùng HTTP theo hướng REST, còn một service tính toán nội bộ dùng RPC. Nếu kết hợp trong cùng API công khai, cần quy ước nhất quán để client hiểu sự khác nhau; không thể dựa vào một nhãn chung để giải thích mọi endpoint.

OpenAPI mô tả được nhiều hợp đồng HTTP, bao gồm API hướng tài nguyên và API HTTP mang kiểu RPC. Có tài liệu OpenAPI hoặc giao diện Swagger không phải bằng chứng API đã tuân thủ REST.

## 9. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu chính xác hơn |
| --- | --- |
| “Trả JSON là REST.” | JSON là định dạng biểu diễn; REST là phong cách kiến trúc. |
| “HTTP API và RESTful API là hai loại loại trừ nhau.” | Trong phạm vi bài học, RESTful API trên HTTP cũng là HTTP API. |
| “Đường dẫn có danh từ thì chắc chắn RESTful.” | Còn phải xem ngữ nghĩa phương thức, stateless, cache, giao diện thống nhất và các ràng buộc khác. |
| “RPC chỉ là dùng POST.” | RPC tập trung vào lời gọi thao tác; `POST` cũng được dùng hợp lệ trong API theo tài nguyên. |
| “REST chỉ làm CRUD.” | Resource có thể biểu diễn tác vụ, quy trình và kết quả tính toán, không chỉ bản ghi dữ liệu. |
| “Stateless nghĩa là server không được có trạng thái.” | Server có thể giữ trạng thái tài nguyên; request không được phụ thuộc ngữ cảnh hội thoại ngầm đã giữ từ request trước. |
| “REST luôn chậm hơn RPC.” | Độ trễ còn phụ thuộc payload, số lượt trao đổi, cache, xử lý nghiệp vụ và triển khai; nhãn kiến trúc chưa đủ để kết luận. |
| “RPC làm client không cần hiểu lỗi mạng.” | Lời gọi từ xa vẫn có timeout, lỗi vận chuyển và kết quả không chắc chắn sau mất kết nối. |
| “Đổi tên endpoint là hoàn tất chuyển RPC sang REST.” | Cần xem lại mô hình tài nguyên, hợp đồng, ngữ nghĩa HTTP và cách client đi qua các trạng thái nghiệp vụ. |

## 10. Tự phân loại một hợp đồng API

Khi gặp một API mới, hãy đọc theo thứ tự:

1. **Giao thức:** API có trao đổi bằng HTTP không? Nếu có, có thể gọi nó là HTTP API.
2. **Đơn vị tương tác:** Client làm việc với tài nguyên được định danh, hay gửi tên thao tác và tham số?
3. **Ngữ nghĩa HTTP:** Phương thức, mã trạng thái và header có diễn đạt đúng kết quả không?
4. **Hợp đồng:** Field, lỗi, tác động phụ và điều kiện gửi lại request có rõ không?
5. **Ràng buộc kiến trúc:** Có bằng chứng về stateless, cache, giao diện thống nhất, hypermedia và khả năng đi qua các lớp trung gian không?

Thử xét ba mô tả:

- `GET /products/prd-10` chỉ đọc sản phẩm, có response và header cache rõ ràng: biểu hiện thiết kế tài nguyên tốt, nhưng vẫn cần xem toàn bộ API trước khi kết luận tuân thủ REST đầy đủ.
- `POST /rpc` với `method: "products.get"`: HTTP API theo kiểu RPC, dù kết quả cũng là một sản phẩm.
- `GET /orders/ord-123?cancel=true` làm hủy đơn: URI có danh từ nhưng dùng sai ngữ nghĩa `GET`.

Kết quả phân loại hữu ích phải giải thích được API đang tổ chức tương tác như thế nào và hệ quả đối với client. Một kết luận như “HTTP API hướng tài nguyên, dùng đúng phương thức nhưng chưa có bằng chứng về hypermedia” có giá trị hơn việc gắn nhãn RESTful chỉ từ hình thức URL.

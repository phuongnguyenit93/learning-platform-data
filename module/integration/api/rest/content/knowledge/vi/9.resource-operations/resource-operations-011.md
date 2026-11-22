# Ngăn mô hình dữ liệu nội bộ quyết định toàn bộ thiết kế API

> **Phạm vi:** Bài học thuộc **INTEGRATION_API_REST**, chương **Thao tác tài nguyên**. Người học thiết kế REST API theo resource, URI, HTTP method, status code và hợp đồng dữ liệu có chủ đích; giữ cho cấu trúc công khai phục vụ nhu cầu của client thay vì sao chép bảng cơ sở dữ liệu hoặc JPA Entity. Ví dụ sử dụng Java/Spring, DTO, lớp ánh xạ, OpenAPI, phân trang, idempotency, xác thực, phân quyền và kiểm thử hợp đồng; nguyên tắc tương tự áp dụng cho công nghệ khác.

## 1. Vấn đề: một bảng cơ sở dữ liệu không phải mặc nhiên là một resource API

Trong một dự án mới, cách nhanh nhất để dựng endpoint thường là tạo một JPA Entity, repository và controller trả thẳng entity qua JSON. Ví dụ có bảng `orders`, lập tức tạo `GET /orders`, `POST /orders`, `PUT /orders/{id}` và `DELETE /orders/{id}` với toàn bộ cột bảng được mở cho client. Ban đầu rất tiện, nhưng về lâu dài mọi thay đổi nội bộ có thể trở thành thay đổi đối với client:

- Đổi tên cột `customer_id` thành `buyer_account_id` làm JSON đổi tên ngoài ý muốn.
- Tách bảng `orders` và `order_items` khiến JSON thay đổi dù nghiệp vụ đặt hàng không đổi.
- Thêm cột `fraud_score`, `internal_note` hay `cost_price` vô tình xuất hiện trong phản hồi.
- Cho phép client gửi `status: "PAID"` hoặc `discountPercent: 100` vì các field của entity có setter.
- Lazy relationship có thể gây N+1 query, vòng tham chiếu khi serialize hoặc lỗi `LazyInitializationException`.
- Một thao tác nghiệp vụ như hủy đơn phải đi qua quy tắc bù hoàn tiền và trả hàng, nhưng `DELETE /orders/{id}` lại xóa row không theo workflow.

**Phản mẫu cốt lõi:** lấy schema lưu trữ làm hợp đồng API mặc định, khiến client phụ thuộc vào các quyết định tối ưu database, persistence framework và cấu trúc mã nội bộ. API tồn tại để trao đổi **khả năng và thông tin có ý nghĩa với người dùng**, không phải để công bố toàn bộ bộ nhớ của server.

Điều này không có nghĩa mọi DTO bắt buộc phải khác từng trường so với bảng. Với chức năng CRUD đơn giản, resource công khai có thể rất gần với dữ liệu lưu trữ. Điều quan trọng là sự tương đồng được **chọn có chủ ý, có kiểm soát**, không phải hệ quả ngầm của serializer.

### 1.1. Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt **resource API**, **biểu diễn JSON**, **domain model**, **persistence entity** và **schema cơ sở dữ liệu**.
- Nhận diện khi API bị ràng buộc quá mức vào DB schema/JPA Entity và giải thích tác động lên bảo mật, hiệu năng, versioning, trải nghiệm client.
- Thiết kế URI và thao tác từ hành trình nghiệp vụ, vòng đời resource và ranh giới aggregate.
- Thiết kế request/response DTO có trường công khai ổn định, quy tắc validation, quyền cập nhật và hợp đồng lỗi rõ ràng.
- Triển khai lớp controller, application service, mapper và repository bằng Java/Spring mà không lộ persistence model.
- Áp dụng idempotency, ETag/`If-Match`, pagination, cache và OpenAPI phù hợp để bảo vệ hợp đồng qua các lần refactor nội bộ.
- Viết phép kiểm hợp đồng nhằm cho phép thay đổi cấu trúc dữ liệu nội bộ mà client vẫn hoạt động bình thường.

## 2. Năm khái niệm cần phân biệt

| Khái niệm | Nó trả lời câu hỏi gì? | Ví dụ hệ thống đặt hàng | Có nhất thiết công khai cho client? |
|---|---|---|---|
| **Resource API** | Client đang thao tác đối tượng hoặc khái niệm nghiệp vụ nào? | Một đơn hàng có định danh `ord_916` | URI và hành vi có, cách lưu không |
| **Representation** | Dữ liệu nào được công bố tại thời điểm đọc hoặc ghi? | JSON gồm mã đơn, trạng thái, dòng hàng, tổng tiền | Có, theo quyền và hợp đồng |
| **Domain model** | Quy tắc và bất biến nghiệp vụ là gì? | Đơn không thể xác nhận nếu hàng chưa giữ chỗ; hủy đơn có quy tắc | Không nhất thiết; có thể dùng nội bộ |
| **Persistence entity / ORM mapping** | Ứng dụng làm việc với dữ liệu lưu trữ ra sao? | `OrderEntity`, `OrderLineEntity`, version column | Không |
| **Database schema** | Dữ liệu được tổ chức vật lý và chuẩn hóa như thế nào? | Bảng `orders`, `order_lines`, `payment_attempts` | Không |

Một **resource** có thể được tổng hợp từ nhiều bảng hoặc nhiều dịch vụ. Ngược lại, một bảng nội bộ có thể không nên có endpoint riêng vì nó chỉ phục vụ triển khai. Resource thường có một danh tính URI ổn định, các phương thức được hỗ trợ và representation tùy theo trạng thái/ủy quyền.

~~~mermaid
flowchart LR
    C["Client web / mobile / partner"] -->|"HTTP: URI, method, JSON, status"| A["REST API contract"]
    A -->|"DTO + validation + authorization"| UC["Application use case"]
    UC -->|"Đối tượng và quy tắc nghiệp vụ"| D["Domain model"]
    D -->|"Repository abstraction"| R["Persistence adapter / JPA"]
    R --> DB[("Tables / indexes / storage")]
    UC --> M["Response projection / mapper"]
    M --> A
    note1["Có thể thay entity/schema mà vẫn giữ DTO công khai"] -.-> R
~~~

Sơ đồ cho thấy các lớp chịu trách nhiệm khác nhau. Có ứng dụng nhỏ không cần tách thành nhiều module vật lý, nhưng vẫn nên giữ **ranh giới dữ liệu vào/ra và hành vi** độc lập với persistence framework.

## 3. Bắt đầu từ hành trình nghiệp vụ, không bắt đầu từ bảng

Giả sử nội bộ một hệ thống thương mại điện tử có các bảng:

~~~text
customer_accounts
orders
order_lines
payment_attempts
inventory_reservations
shipment_events
fraud_reviews
audit_entries
~~~

Sơ đồ quan hệ này hữu ích cho thiết kế dữ liệu nhưng không cho biết trực tiếp client cần làm gì. Hãy hỏi người dùng và đối tác:

1. Khách cần **đặt hàng**, xem đơn, xem tình trạng giao hàng và yêu cầu hủy.
2. Nhân viên hỗ trợ cần **tra cứu** nhưng không được xem thông tin điều tra gian lận nội bộ.
3. Dịch vụ thanh toán cần gửi kết quả giao dịch theo hợp đồng riêng, có xác thực webhook.
4. Đội vận hành cần điều tra lỗi và xem audit nội bộ, không thông qua cùng JSON công khai cho khách.

Từ đó có thể thiết kế các resource và thao tác:

| Nhu cầu | URI và phương thức khả dĩ | Ý nghĩa với client |
|---|---|---|
| Tạo đơn | `POST /v1/orders` | Yêu cầu tạo đơn mới; server tính giá và kiểm tra ràng buộc |
| Đọc đơn | `GET /v1/orders/{orderId}` | Lấy biểu diễn đơn mà caller được phép xem |
| Danh sách đơn của người dùng | `GET /v1/orders?limit=20&cursor=...` | Duyệt tập đơn có kiểm soát phân trang |
| Yêu cầu hủy đơn | `POST /v1/orders/{orderId}/cancellations` | Tạo **yêu cầu hủy** theo workflow, có thể thành công hoặc bị từ chối |
| Đọc trạng thái yêu cầu hủy | `GET /v1/orders/{orderId}/cancellations/{id}` | Xem kết quả nghiệp vụ của một yêu cầu hủy |
| Lấy trạng thái vận chuyển | `GET /v1/orders/{orderId}/tracking` | View tổng hợp từ shipment events, không buộc lộ từng row |

URI là ví dụ, không phải một tiêu chuẩn duy nhất. Đối với một tác vụ hủy đơn đơn giản và luôn đồng bộ, một hành vi cập nhật phù hợp trên resource đơn hoặc một resource hủy có thể đều được cân nhắc. Khi hủy có thể cần hoàn tiền, giải phóng tồn kho và chờ dịch vụ ngoài, **resource yêu cầu hủy** thể hiện vòng đời tốt hơn việc xóa trực tiếp bản ghi `orders`.

### 3.1. Câu hỏi chọn resource

Với một khái niệm đang được đề xuất là resource, hãy kiểm tra:

- **Danh tính:** client có cần tham chiếu nó giữa nhiều lần gọi hoặc nhiều phiên không?
- **Vòng đời:** nó được tạo, chuyển trạng thái và kết thúc bằng quy tắc nào?
- **Quyền sở hữu:** ai được đọc, tạo, sửa, hủy, và ở trạng thái nào?
- **Bất biến:** có trường nào server phải tính hoặc quyết định thay vì tin giá trị client gửi?
- **Ranh giới:** nó là một đối tượng nghiệp vụ, một hành động có kết quả theo dõi được, hay chỉ là chi tiết DB?
- **Độ ổn định:** tên và cấu trúc có ý nghĩa lâu dài với người dùng/đối tác không, hay chỉ mô tả thuật toán lưu trữ hiện tại?

**Không phải mọi bảng phải có CRUD và không phải mọi resource phải có đủ GET/POST/PUT/PATCH/DELETE.** Chọn phương thức theo hành vi thực tế và ngữ nghĩa HTTP.

### 3.2. Thiết kế representation từ góc nhìn client

**Request tạo đơn** chỉ cần thông tin client có quyền đề xuất:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <token>
Idempotency-Key: 475990a5-887f-4fb2-9acd-0fb3a1b79ed1
Content-Type: application/json

{
  "shippingAddressId": "addr_84",
  "items": [
    {"sku": "BOOK-123", "quantity": 2}
  ]
}
~~~

Server tự xác định tài khoản từ danh tính đã xác thực, kiểm tra địa chỉ thuộc quyền của khách, tìm giá và khuyến mãi hợp lệ, tính tiền bằng số thập phân chính xác, kiểm tra tồn kho và xác định trạng thái khởi đầu. Không để client đặt `ownerId`, `totalAmount`, `paymentStatus`, `fraudScore` hay `createdAt` nếu đó là dữ liệu do hệ thống kiểm soát.

**Phản hồi tạo đơn** có thể là:

~~~http
HTTP/1.1 201 Created
Location: https://api.example.test/v1/orders/ord_916
Content-Type: application/json
ETag: "ord_916-v1"

{
  "id": "ord_916",
  "status": "PENDING_PAYMENT",
  "currency": "VND",
  "totalAmount": "250000",
  "items": [
    {
      "sku": "BOOK-123",
      "displayName": "Sách Java cơ bản",
      "quantity": 2,
      "unitPrice": "125000"
    }
  ],
  "createdAt": "2026-11-18T09:00:00Z",
  "links": {"self": "/v1/orders/ord_916"}
}
~~~

Trong ví dụ, tiền được truyền bằng **chuỗi thập phân** để tránh cách biểu diễn dấu phẩy động không mong muốn trên một số client. Đây là quyết định hợp đồng; một API khác có thể dùng số nguyên đơn vị nhỏ nhất kèm currency hoặc JSON number có quy định độ chính xác. Điều bắt buộc là quy tắc đơn vị, làm tròn, tiền tệ và giới hạn giá trị được công bố rõ.

### 3.3. Một JSON có thể gom dữ liệu từ nhiều nơi

Resource đơn hàng có thể cần `orders` cho header, `order_lines` cho mặt hàng, dịch vụ catalog để lấy tên hiển thị và dịch vụ payment để biểu diễn tình trạng thanh toán. API không buộc phải có URI tương ứng cho từng khóa ngoại. Tuy nhiên, aggregation phải được thiết kế về **độ trễ, cache, fallback và consistency**. Nếu dịch vụ catalog không phản hồi, API trả giá trị snapshot tên sản phẩm hay báo thiếu trường? Quyết định này thuộc hợp đồng.

## 4. Những phản mẫu do database dẫn dắt API

| Phản mẫu | Dấu hiệu | Hệ quả | Cách thiết kế |
|---|---|---|---|
| **Database-as-API** | URI và JSON dùng nguyên tên bảng/cột | Client phụ thuộc vào schema | Định nghĩa resource và field theo nhu cầu người dùng |
| **Expose JPA Entity** | Controller trả `OrderEntity` trực tiếp | Lộ dữ liệu, lazy load, cycle, N+1, serializer quyết định contract | Dùng request/response DTO hoặc projection có kiểm soát |
| **Generic CRUD cho mọi bảng** | Mọi table đều có GET/POST/PUT/DELETE | Cho phép thao tác trái quy tắc nghiệp vụ | Chọn endpoint theo vòng đời và invariants |
| **Mass assignment** | `save(requestBody)` gán toàn bộ field entity | Client cập nhật status/price/owner trái phép | Allowlist field được sửa, tách input DTO theo use case |
| **Deep ORM graph** | JSON chứa toàn bộ quan hệ lazy/eager | Payload lớn, vòng tham chiếu, N+1, lộ thông tin | Flat DTO, liên kết resource và query có mục tiêu |
| **Leaky internal IDs** | Client nhận khóa nối bảng, ID transaction kỹ thuật | Coupling và nguy cơ dò dữ liệu | ID công khai ổn định; mapping sang PK riêng nếu cần |
| **Data access quyết định authorization** | Có row trong DB là trả cho client | BOLA/IDOR, lộ dữ liệu liên tenant | Phân quyền theo chủ thể và tài nguyên trước khi trả |
| **Trạng thái từ cột tùy ý** | `PATCH {"status":"PAID"}` | Bỏ qua kiểm chứng thanh toán | Chuyển trạng thái qua nghiệp vụ có quy tắc |
| **Filter theo tên cột SQL** | Client gửi `sort=cost_price,table_id` | Lộ schema, query không ổn định hoặc tốn tài nguyên | Danh sách filter/sort công khai được phép |
| **Chuyển lỗi DB thẳng ra API** | Trả tên constraint, SQL exception | Lộ chi tiết nội bộ, khó sinh SDK | Ánh xạ sang status và Problem Details ổn định |

### 4.1. Ví dụ controller dễ gây hại

~~~java
// PHẢN MẪU: chỉ minh họa vấn đề, không dùng làm API sản xuất.
@RestController
@RequestMapping("/v1/order_table")
class UnsafeOrderController {
    private final JpaRepository<OrderEntity, Long> repository;

    @PostMapping
    OrderEntity create(@RequestBody OrderEntity entity) {
        return repository.save(entity);
    }

    @GetMapping("/{id}")
    OrderEntity get(@PathVariable Long id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

Vấn đề không chỉ là tên URI xấu. Đưa `OrderEntity` vào request cho phép serializer gán các field mà client không nên kiểm soát. Trả entity trong response khiến các association, annotation Jackson, kiểu dữ liệu Java, tên cột/field và cơ chế lazy loading trở thành một phần hợp đồng ngoài ý muốn. Ngay cả khi dùng `@JsonIgnore`, vẫn phải xét xem phần bị bỏ qua có thay đổi theo use case và quyền người dùng không.

## 5. Thiết kế contract-first: từ nhu cầu đến request/response

**Contract-first** ở đây nghĩa là chốt ngữ nghĩa tài nguyên, field, mã lỗi, quyền và ví dụ trước khi chốt cách persistence thể hiện chúng. Không bắt buộc phải viết OpenAPI trước mọi dòng code; quan trọng là contract có thể review và test độc lập với DB schema.

Một quy trình có thể lặp lại:

1. **Chọn hành trình:** “Khách đặt hàng”, “Khách xem đơn”, “Khách yêu cầu hủy”.
2. **Liệt kê bất biến nghiệp vụ:** giá do server tính, không vượt tồn kho đã xác nhận, chỉ chủ đơn được hủy trong điều kiện cho phép.
3. **Định nghĩa resource:** tên, URI, định danh, lifecycle, các liên kết và quyền.
4. **Định nghĩa representation:** trường nào nhận từ client, trường nào do server trả, trường nào ẩn vì bảo mật.
5. **Định nghĩa HTTP contract:** method, status, `Location`, `ETag`, `If-Match`, lỗi, pagination, caching và idempotency.
6. **Định nghĩa lớp chuyển đổi:** DTO → command → domain → persistence, và domain/read projection → response DTO.
7. **Định nghĩa phép thử:** happy path, đầu vào xấu, quyền sai, trạng thái xung đột, retry và thay schema DB.

### 5.1. Tách DTO theo từng hành vi

Đừng tạo một `OrderDto` duy nhất vừa làm POST input, PATCH input, GET output, response admin và dữ liệu ghi DB. Các use case có yêu cầu khác nhau:

| DTO | Trường được phép | Trường chủ động không xuất hiện |
|---|---|---|
| `CreateOrderRequest` | `shippingAddressId`, `items[].sku`, `items[].quantity` | `id`, `ownerId`, `price`, `paymentStatus`, `createdAt` |
| `OrderResponse` | ID, trạng thái công khai, snapshot mặt hàng, tiền, thời gian, links | Fraud score, internal notes, raw tokens, hash, dữ liệu điều tra |
| `CancelOrderRequest` | Lý do từ danh sách được cho phép, ghi chú ngắn nếu cần | Quyền ép hoàn tiền, sửa payment provider ID |
| `SupportOrderView` | Các trường nhân viên hỗ trợ được phép xem | Dữ liệu nội bộ của đội an ninh, khóa bí mật |

DTO được chọn theo **lý do sử dụng và quyền**, không chỉ theo cấu trúc bảng. Một field có thể tồn tại trong domain nhưng không thuộc bất kỳ representation công khai nào.

### 5.2. Không để field không biết bị “bỏ qua âm thầm” trong các lệnh nhạy cảm

Ví dụ client gửi `{"status":"PAID"}` trong request tạo đơn. Nếu server âm thầm bỏ qua, client có thể tưởng đã cập nhật trạng thái. Nếu server tự gán vào entity, đây là lỗi bảo mật. Nên quyết định rõ:

- Request schema chỉ bao gồm field được phép.
- Kiểm tra field không biết/không hỗ trợ theo chính sách đã công bố (ví dụ từ chối `400` hoặc bỏ qua có tài liệu hóa khi tương thích ngược).
- Với lệnh thay đổi nghiệp vụ nhạy cảm, ưu tiên **từ chối field vượt phạm vi**, giúp phát hiện client hiểu sai contract.

Không dùng generic object mapper để sao chép toàn bộ JSON vào entity theo tên field mà không có allowlist.

## 6. HTTP method phải thể hiện hành vi, không phải thao tác SQL

Một REST resource có lifecycle riêng; SQL `INSERT/UPDATE/DELETE` là cách nội bộ hiện thực hóa, không quyết định tự động method HTTP.

| HTTP method | Ngữ nghĩa | Tình huống đặt hàng | Lưu ý |
|---|---|---|---|
| `GET` | Đọc representation, safe theo giao thức | Đọc đơn, danh sách đơn | Không dùng GET để hủy hoặc thanh toán |
| `POST` | Gửi yêu cầu xử lý theo ngữ nghĩa tài nguyên đích | Tạo đơn, yêu cầu hủy, bắt đầu xuất báo cáo | Không mặc định idempotent; cần chiến lược chống trùng nếu retry có tác động |
| `PUT` | Tạo/thay thế trạng thái resource đích theo representation được định nghĩa | Thay toàn bộ cấu hình một resource có quyền điều khiển rõ | PUT có tính idempotent theo ngữ nghĩa; không ép thành “update mọi cột” |
| `PATCH` | Áp dụng một tập thay đổi lên resource đích | Cập nhật các trường người dùng được phép sửa | Cần quy ước patch document, validation và xung đột |
| `DELETE` | Yêu cầu loại bỏ liên kết/khả năng phục vụ của resource đích theo hợp đồng | Xóa draft nếu nghiệp vụ cho phép | Không mặc nhiên dùng để hủy đơn đã thanh toán hoặc xóa dữ liệu vật lý |

Ví dụ `POST /orders/{id}/cancellations` tạo một yêu cầu hủy có danh tính và trạng thái. Hệ thống có thể ghi nhiều bảng, gọi payment gateway và kho tồn, nhưng client không cần biết từng bước SQL đó. Nếu yêu cầu hoàn tất đồng bộ và resource yêu cầu hủy được tạo, có thể dùng `201 Created` với `Location` trỏ tới cancellation; nếu công việc được tiếp nhận để thực thi sau, `202 Accepted` với URI operation/monitor là một lựa chọn theo contract.

Đừng biến mọi hành động thành `POST /cancelOrder`, `POST /updateOrder` theo tên hàm nội bộ; nhưng cũng không gò ép mọi nghiệp vụ phức tạp thành CRUD vô nghĩa. Một **resource biểu diễn yêu cầu hoặc quá trình nghiệp vụ** thường cung cấp URI và trạng thái dễ theo dõi hơn.

### 6.1. PUT và PATCH không phải là “cho phép sửa toàn bộ entity”

Khi một resource là địa chỉ giao hàng có thể chỉnh sửa, API có thể dùng:

~~~http
PATCH /v1/orders/ord_916/shipping-address HTTP/1.1
Host: api.example.test
Authorization: Bearer <token>
Content-Type: application/merge-patch+json
If-Match: "shipping-ord_916-v2"

{"recipientName":"Nguyễn An"}
~~~

Đây là một **representation độc lập về địa chỉ giao hàng** nếu API đã định nghĩa resource đó và điều kiện cho sửa. JSON Merge Patch có quy tắc riêng: đối tượng chỉ chứa field muốn đổi; giá trị `null` thường mang nghĩa xóa trường; mảng thường được thay thế như một giá trị, không tự merge từng phần tử. Nếu API dùng `application/json-patch+json`, cú pháp và ngữ nghĩa hoàn toàn khác. Tài liệu phải nêu đúng loại patch, field được phép và cách xử lý `null`.

Không cho phép tùy ý PATCH `status` từ `PENDING_PAYMENT` thành `PAID`. Đây là chuyển trạng thái phụ thuộc vào bằng chứng thanh toán, thường phải đi qua use case riêng được bảo vệ.

### 6.2. Đồng thời: `ETag` và `If-Match`

Giả sử hai client cùng đọc một địa chỉ giao hàng ở version 2. Client A sửa thành version 3; client B gửi bản sửa dựa trên version 2. Nếu server ghi đè vô điều kiện, mất cập nhật của A.

Một thiết kế có thể trả:

~~~http
HTTP/1.1 200 OK
ETag: "shipping-ord_916-v2"
Content-Type: application/json

{"recipientName":"Nguyễn An","city":"Hà Nội"}
~~~

Sau đó yêu cầu sửa gửi `If-Match: "shipping-ord_916-v2"`. Nếu version hiện tại đã đổi, server trả:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/stale-resource",
  "title": "Resource was modified",
  "status": 412,
  "detail": "Phiên bản tài nguyên đã thay đổi. Hãy đọc lại trước khi sửa."
}
~~~

Nếu endpoint yêu cầu client luôn gửi điều kiện và header bị thiếu, `428 Precondition Required` có thể phù hợp. `409 Conflict` thích hợp cho xung đột **quy tắc nghiệp vụ hoặc trạng thái** khi không phải lỗi HTTP precondition. Không lấy tên cột `version` ra làm field public chỉ vì JPA dùng `@Version`; ETag có thể được tạo từ version nội bộ và chính sách representation nhưng phải duy trì ngữ nghĩa validator đúng. Nếu dùng ETag mạnh, giá trị cần phản ánh thay đổi của representation tương ứng; không gán một cách tùy tiện một version DB không theo dõi các field được tổng hợp từ dịch vụ khác.

## 7. Thiết kế Java/Spring theo ranh giới rõ ràng

### 7.1. Request/response DTO

Ví dụ rút gọn với Java 17+ và Spring MVC, Jakarta Validation:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

public record OrderLineInput(
    @NotBlank String sku,
    @Min(1) int quantity
) {}

public record CreateOrderRequest(
    @NotBlank String shippingAddressId,
    @NotEmpty List<@Valid OrderLineInput> items
) {}

public record OrderLineResponse(
    String sku,
    String displayName,
    int quantity,
    BigDecimal unitPrice
) {}

public record OrderResponse(
    String id,
    String status,
    String currency,
    BigDecimal totalAmount,
    List<OrderLineResponse> items,
    Instant createdAt
) {}
~~~

Các DTO **không có `OrderEntity`, `paymentToken` hay `internalNote`**. Nên bổ sung giới hạn kích thước danh sách, độ dài chuỗi, validation theo định dạng ID và quy tắc tổng số lượng để tránh request quá lớn. Các annotation kiểm tra cấu trúc; use case vẫn phải kiểm tra tồn kho, giá, địa chỉ thuộc quyền và quy tắc nghiệp vụ.

`BigDecimal` phù hợp với phép tính tiền chính xác ở Java, nhưng format JSON (number hay string), độ chính xác và đơn vị tiền phải thống nhất qua Jackson/OpenAPI và client. DTO ở đây là **bản minh họa shape**; không mặc định JSON serialization của BigDecimal là chuỗi như ví dụ HTTP mục 3.2 nếu chưa cấu hình và kiểm thử.

### 7.2. Application layer nhận command, trả projection

~~~java
import java.util.List;

public record PlaceOrderCommand(
    String authenticatedCustomerId,
    String shippingAddressId,
    List<OrderLineInput> items
) {}

public record CreatedOrder(
    String id,
    OrderView view
) {}

public record OrderView(
    String id,
    String status,
    String currency,
    java.math.BigDecimal totalAmount,
    List<OrderLineView> items,
    java.time.Instant createdAt
) {}

public record OrderLineView(
    String sku,
    String name,
    int quantity,
    java.math.BigDecimal price
) {}

public interface OrderApplicationService {
    CreatedOrder placeOrder(PlaceOrderCommand command);
    OrderView findVisibleOrder(String id, String authenticatedCustomerId);
}
~~~

Service dùng command đã ràng buộc danh tính thực tế, không tin `customerId` từ request. `OrderView` là projection nội bộ phục vụ API, không phải JPA Entity. Domain có thể là aggregate `Order` với các phương thức kiểm tra bất biến; repository/persistence adapter chuyển đổi giữa domain và bảng thật.

### 7.3. Controller chỉ điều phối HTTP

~~~java
import java.net.URI;
import java.security.Principal;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/v1/orders")
public class OrderController {
    private final OrderApplicationService application;
    private final OrderApiMapper mapper;

    public OrderController(
            OrderApplicationService application,
            OrderApiMapper mapper) {
        this.application = application;
        this.mapper = mapper;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request,
            Principal principal) {
        var command = new PlaceOrderCommand(
            principal.getName(),
            request.shippingAddressId(),
            request.items());
        CreatedOrder created = application.placeOrder(command);

        URI location = ServletUriComponentsBuilder.fromCurrentRequest()
            .path("/{id}")
            .buildAndExpand(created.id())
            .toUri();

        return ResponseEntity.created(location)
            .body(mapper.toResponse(created.view()));
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderResponse> get(
            @PathVariable String id,
            Principal principal) {
        OrderView visible = application.findVisibleOrder(
            id, principal.getName());
        return ResponseEntity.ok(mapper.toResponse(visible));
    }
}
~~~

`Principal` ở ví dụ biểu thị danh tính đã được xác thực. Ứng dụng thật phải cấu hình Spring Security, xác thực, phân quyền và hành vi khi Principal không có; không coi chỉ nhận parameter là đã an toàn. `findVisibleOrder` phải kiểm tra owner/tenant, kể cả khi ID khó đoán. Đặt `@Transactional` và kiểm soát giao dịch ở lớp service/repository phù hợp; không phải controller tự thao tác `JpaRepository.save(requestBody)`.

`ServletUriComponentsBuilder` giúp tạo URI từ request nhưng khi chạy sau proxy cần cấu hình xử lý header chuyển tiếp từ **proxy tin cậy** và quy tắc public origin; nếu không `Location` có thể là internal hostname hoặc bị thao túng bởi header không đáng tin. Có thể ưu tiên cấu hình public base URL cố định. Ví dụ chưa xử lý trường hợp Idempotency-Key để giữ trọng tâm vào phân tầng; bổ sung middleware/service lưu idempotency đúng contract trước khi đưa vào production.

### 7.4. Mapper chọn trường công khai

~~~java
import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class OrderApiMapper {
    public OrderResponse toResponse(OrderView view) {
        List<OrderLineResponse> lines = view.items().stream()
            .map(line -> new OrderLineResponse(
                line.sku(),
                line.name(),
                line.quantity(),
                line.price()))
            .toList();

        return new OrderResponse(
            view.id(),
            view.status(),
            view.currency(),
            view.totalAmount(),
            lines,
            view.createdAt());
    }
}
~~~

Mapper không được tự phát sinh truy vấn DB hoặc gọi dịch vụ ngoài ngầm cho mỗi dòng. Application/query service nên lấy dữ liệu theo projection phù hợp, batch lookup hoặc join có chủ đích để tránh N+1. Với quan hệ lớn, thay vì trả mọi chi tiết lồng sâu, công bố link hoặc endpoint riêng có phân trang.

### 7.5. Persistence entity có thể thay đổi độc lập

Ví dụ `OrderEntity` ban đầu có `customerId`, `createdAt` và danh sách `OrderLineEntity`. Sau này nhóm database tách bảng vì nhu cầu lưu trữ, đổi cột `customer_id` thành `buyer_account_id` hoặc chuyển thông tin giá sang snapshot bảng khác. Nếu persistence adapter vẫn trả đúng domain/read projection, **hợp đồng `OrderResponse` có thể không đổi**.

Điều này là tính **ổn định có điều kiện**: nếu nghiệp vụ thật thay đổi, ví dụ bỏ hỗ trợ một trạng thái đơn hoặc đổi cách tính thuế, API có thể cần phiên bản mới hoặc quá trình chuyển đổi có quản lý. Mục tiêu không phải ngăn API tiến hóa, mà là **không buộc client đổi chỉ vì refactor lưu trữ**.

## 8. Bảo vệ dữ liệu, tránh mass assignment và lộ thông tin

### 8.1. Allowlist trường được ghi

Giả sử client gửi:

~~~json
{
  "shippingAddressId": "addr_84",
  "items": [{"sku":"BOOK-123","quantity":2}],
  "ownerId": "user_other",
  "status": "PAID",
  "totalAmount": "0",
  "internalNote": "approve"
}
~~~

Nếu API bind trực tiếp vào entity, những field thêm có thể bị gán mà server không dự tính. Với DTO riêng, request chỉ mô tả ý định được phép, còn status/total/owner do hệ thống quyết định. Nên kiểm thử trường ngoài hợp đồng sẽ bị từ chối hoặc xử lý theo chính sách tài liệu hóa; với các lệnh nhạy cảm, **từ chối field lạ** giúp phát hiện client sai contract thay vì bỏ qua im lặng.

### 8.2. Kiểm tra object-level authorization

Ví dụ `GET /v1/orders/ord_916`:

1. Xác thực caller từ bearer token/session.
2. Tìm đơn theo ID trong đúng tenant (hoặc truy vấn có ràng buộc owner).
3. Kiểm tra quyền đọc theo vai trò và trạng thái; ví dụ nhân viên hỗ trợ có thể xem subset cụ thể.
4. Chọn response projection tương ứng; không trả field nội bộ rồi mong frontend ẩn đi.
5. Trả `403 Forbidden` hoặc `404 Not Found` theo chính sách không tiết lộ sự tồn tại của đơn.

Việc có `orderId` hợp lệ trong DB không chứng minh người gọi được phép đọc. Đây là lớp lỗi API thường gọi là **Broken Object Level Authorization (BOLA)** hoặc IDOR.

### 8.3. Dữ liệu cá nhân, bí mật và cache

Không serialize tự động quan hệ `CustomerEntity` hoặc `PaymentEntity` vào response vì chúng có thể chứa email, điện thoại, token và lịch sử giao dịch. Thiết kế representation theo nhu cầu tối thiểu của caller, áp dụng quy tắc che thông tin nếu cần. Với response nhạy cảm, cân nhắc `Cache-Control: private` hoặc `no-store` theo yêu cầu; không để cache chia sẻ trả đơn của user này cho user khác. ETag và conditional GET vẫn có thể dùng khi cache policy và phạm vi người dùng được thiết kế đúng.

## 9. Phân trang, filter, sort: không biến query string thành SQL công khai

Một API nội bộ dùng ORM có thể cho repository nhận trực tiếp `sortBy=internalColumn` hoặc danh sách predicate tùy ý. Điều này làm client phụ thuộc tên cột, mở đường tới truy vấn tốn tài nguyên hoặc dữ liệu không được phép; một số trường hợp ghép SQL động còn làm tăng rủi ro injection.

Định nghĩa tập filter/sort **theo ngôn ngữ nghiệp vụ**:

~~~http
GET /v1/orders?status=SHIPPED&limit=20&sort=createdAt_desc HTTP/1.1
Host: api.example.test
Authorization: Bearer <token>
~~~

Phản hồi mẫu:

~~~json
{
  "data": [
    {"id":"ord_916","status":"SHIPPED","totalAmount":"250000","currency":"VND"}
  ],
  "page": {
    "limit": 20,
    "nextCursor": "opaque_cursor_example",
    "hasMore": true
  }
}
~~~

`sort=createdAt_desc` là **tên công khai được phép**. Adapter có thể ánh xạ sang cột khác hoặc nhiều cột khi schema thay đổi. `limit` có tối đa rõ ràng và đầu vào không hợp lệ phải bị từ chối; không cho client tự chọn các trường nội bộ ngoài allowlist.

### 9.1. Offset và cursor

| Cách phân trang | Ưu điểm | Hạn chế |
|---|---|---|
| `offset/limit` | Dễ giải thích; thích hợp dữ liệu nhỏ/ít biến động | Trang sâu có thể tốn chi phí; thêm/xóa row giữa hai request có thể làm lặp/bỏ sót |
| `cursor/limit` | Phù hợp luồng dữ liệu lớn, thường ổn định hơn nếu sắp xếp đúng | Cursor phải được quản lý, có liên quan sort/filter và thời hạn |

Cursor nên **opaque với client**, có thể bao gồm thứ tự sắp xếp, khóa ràng buộc, bộ lọc và phạm vi quyền, được mã hóa/ký hay xác thực chống sửa nếu cần. Đảm bảo sort có thứ tự xác định, chẳng hạn `createdAt DESC, id DESC` để tránh bằng nhau ở timestamp gây thiếu/lặp. Đừng công khai trực tiếp primary key nội bộ làm cursor nếu nó chỉ là chi tiết implementation; có thể dùng nội bộ trong token opaque nhưng hợp đồng không dựa vào ý nghĩa của nó.

**Tính ổn định của phân trang không tự bảo đảm snapshot nhất quán** khi dữ liệu đang đổi. Nếu yêu cầu xuất dữ liệu chính xác một thời điểm, cần snapshot/export job hoặc cơ chế snapshot isolation phù hợp, không chỉ thêm cursor.

## 10. Lỗi API phải phản ánh ý nghĩa nghiệp vụ

Không trả nguyên exception của SQL/JPA như `ConstraintViolationException: uq_orders_customer_id` cho client. Bên trong có thể dùng unique constraint để bảo vệ tính duy nhất; API cần ánh xạ lỗi đó thành **mã HTTP và Problem Details** ổn định.

| Lỗi | Status phù hợp trong nhiều API | Ghi chú |
|---|---|---|
| JSON sai cú pháp / thiếu field bắt buộc | `400 Bad Request` | Validation theo schema |
| Không được xác thực | `401 Unauthorized` | Có cơ chế auth/`WWW-Authenticate` phù hợp |
| Không có quyền trên đơn | `403 Forbidden` hoặc `404 Not Found` | Theo chính sách tiết lộ tài nguyên |
| Đơn không tồn tại | `404 Not Found` | Không lộ chi tiết DB |
| Không thể hủy vì đã giao hàng | `409 Conflict` | Xung đột trạng thái nghiệp vụ |
| Đầu vào hợp cú pháp nhưng không hợp quy tắc xử lý | `422 Unprocessable Content` | Ví dụ phạm vi ngày xuất dữ liệu không được phép |
| `If-Match` cũ khi PATCH | `412 Precondition Failed` | Xung đột với điều kiện request |
| Thiếu điều kiện bắt buộc | `428 Precondition Required` | Khi API yêu cầu precondition |
| Retry POST vượt rate limit | `429 Too Many Requests` | Có thể kèm `Retry-After` |
| Hệ phụ thuộc tạm thời không sẵn sàng | `503 Service Unavailable` khi thích hợp | Cần định nghĩa retry/backoff |

Ví dụ lỗi nghiệp vụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/order-not-cancellable",
  "title": "Order cannot be cancelled",
  "status": 409,
  "detail": "Đơn đã chuyển sang giao hàng nên không thể hủy trực tiếp.",
  "code": "ORDER_NOT_CANCELLABLE",
  "orderId": "ord_916"
}
~~~

Loại lỗi, `code`, field lỗi và status cần được tài liệu hóa; URL `type` chỉ là giá trị minh họa. Không bao gồm stack trace, tên bảng, path nội bộ hoặc dữ liệu của người khác trong response. Một `@RestControllerAdvice` có thể ánh xạ domain exception thành `ProblemDetail` của Spring, nhưng đừng để controller biết từng SQLException riêng.

## 11. Idempotency: thiết kế theo tác động nghiệp vụ

`POST /orders` có thể bị retry nếu client mất kết nối sau khi server đã ghi đơn nhưng trước khi nhận `201`. Nếu không kiểm soát, hệ thống tạo hai đơn. Một mẫu là `Idempotency-Key` có phạm vi theo caller/tenant, thao tác và fingerprint payload.

Hợp đồng cần quy định:

1. Khi **cùng key và cùng nội dung**, trả cùng đơn/response tương thích, không tạo thêm đơn.
2. Khi **cùng key nhưng payload khác**, trả lỗi xung đột được tài liệu hóa, chẳng hạn `409`.
3. Đặt chỗ khóa và ghi tác động nghiệp vụ cần **nguyên tử/bền vững** để chống hai request chạy đồng thời.
4. Có thời hạn lưu khóa; khi hết hạn, việc retry không còn được bảo đảm chống trùng theo key đó.
5. Phân quyền không thể bị bypass chỉ vì đoán được key của user khác.

Idempotency ở HTTP không tự bảo vệ tác động từ queue/worker gửi lại message. Nếu nghiệp vụ thanh toán hoặc gửi email có side effect, cần thêm khóa hoặc ràng buộc chống trùng ở tầng xử lý tương ứng.

Thiết kế này dựa vào yêu cầu **“một hành động nghiệp vụ chỉ gây một tác động logic”**, không phụ thuộc vào việc dữ liệu cuối cùng nằm trong một hay nhiều bảng.

## 12. OpenAPI: hợp đồng là tài sản độc lập với schema nội bộ

Mô tả API nên công bố URI, method, request body, response DTO, status, header, lỗi, security scheme và quy tắc idempotency. Ví dụ OpenAPI 3.1 rút gọn:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths:
  /v1/orders:
    post:
      summary: Tạo đơn từ thông tin được phép của khách
      security:
        - bearerAuth: []
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema: {type: string}
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Đơn được tạo
          headers:
            Location:
              required: true
              schema: {type: string, format: uri}
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '400': {description: Request không hợp lệ}
        '401': {description: Cần xác thực}
        '409': {description: Xung đột nghiệp vụ hoặc idempotency}
        '422': {description: Dữ liệu không thể xử lý theo quy tắc}
  /v1/orders/{orderId}:
    get:
      summary: Đọc đơn mà caller được phép xem
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: orderId
          required: true
          schema: {type: string}
      responses:
        '200':
          description: Đơn tồn tại và được phép đọc
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        '403': {description: Không có quyền}
        '404': {description: Không tìm thấy hoặc không công bố tài nguyên}
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    CreateOrderRequest:
      type: object
      required: [shippingAddressId, items]
      additionalProperties: false
      properties:
        shippingAddressId: {type: string}
        items:
          type: array
          minItems: 1
          items:
            type: object
            required: [sku, quantity]
            additionalProperties: false
            properties:
              sku: {type: string}
              quantity: {type: integer, minimum: 1}
    OrderResponse:
      type: object
      required: [id, status, currency, totalAmount, items, createdAt]
      properties:
        id: {type: string}
        status:
          type: string
          enum: [PENDING_PAYMENT, CONFIRMED, SHIPPED, CANCELLED]
        currency: {type: string}
        totalAmount:
          type: string
          description: Số thập phân không có ký hiệu tiền; đơn vị theo currency
        items:
          type: array
          items:
            type: object
            properties:
              sku: {type: string}
              displayName: {type: string}
              quantity: {type: integer}
              unitPrice: {type: string}
        createdAt: {type: string, format: date-time}
~~~

Đây là mô tả **rút gọn** để minh họa contract, chưa phải API hoàn chỉnh. Cần thêm operationId, ví dụ response, Problem Details schema, pagination, header `ETag` khi dùng optimistic concurrency và toàn bộ endpoint nghiệp vụ còn lại. `bearerFormat: JWT` mang tính gợi ý tài liệu; việc token thật thuộc định dạng nào và quyền gì vẫn phải được xác thực ở runtime.

Chọn `additionalProperties: false` trong request schema thể hiện mong muốn từ chối field lạ. OpenAPI có thể dùng để kiểm thử contract nhưng **không khiến Jackson tự động từ chối field không xác định**; runtime cần cấu hình/validation phù hợp và test thực tế.

## 13. Thay đổi nội bộ mà giữ nguyên hợp đồng ngoài

### 13.1. Ví dụ refactor database

Phiên bản A lưu:

~~~text
orders(id, customer_id, status, total, created_at)
order_lines(id, order_id, sku, qty, unit_price)
~~~

Phiên bản B vì tối ưu:

~~~text
purchase_orders(pk, buyer_account_id, lifecycle_code, created_on)
order_amount_snapshots(order_pk, currency_code, amount_decimal)
purchase_items(pk, order_pk, product_code, units, price_at_order)
~~~

Client **vẫn** dùng `GET /v1/orders/ord_916` và nhận các field `id`, `status`, `currency`, `totalAmount`, `items`, `createdAt`. Persistence adapter chuyển đổi dữ liệu B sang projection công khai, đồng thời giữ nguyên semantics. Trong migration thực tế cần xử lý backfill, consistency, thay query, chỉ số và rollback; không nên giả định đổi tên cột là không có rủi ro.

### 13.2. Kế hoạch expand–migrate–contract

1. **Expand:** thêm bảng/cột/cơ chế ghi mới và khả năng đọc tương thích với dữ liệu cũ.
2. **Migrate:** backfill, kiểm chứng đối soát, cập nhật repository/read projection; nếu cần dual-write, phải có cách tránh lệch dữ liệu và đối soát lỗi.
3. **Switch:** chuyển ứng dụng sang nguồn dữ liệu mới theo rollout có giám sát; chạy kiểm thử hợp đồng và hiệu năng.
4. **Contract:** khi không còn phụ thuộc, loại bỏ cấu trúc cũ theo kế hoạch, sau khi đã kiểm chứng rollback và retention.

Trong toàn quá trình, tầng API không nhất thiết đổi. Ngược lại, nếu semantics thay đổi — ví dụ một đơn có nhiều lần giao hàng và `status` cũ không đủ biểu đạt — cần thiết kế tiến hóa API có chủ đích: thêm field, resource con hoặc version, truyền thông đến client và giữ thời gian chuyển đổi.

### 13.3. Versioning dựa trên thay đổi hợp đồng

Không phải mọi migration DB cần `/v2`. Chỉ cân nhắc version mới hoặc cơ chế tương thích khi có thay đổi **breaking** về public contract, ví dụ:

- Loại bỏ/đổi nghĩa một field client đang dùng.
- Đổi format tiền hoặc enum làm client không còn hiểu đúng.
- Thay đổi rule của endpoint từ tạo đồng bộ sang workflow bất đồng bộ không có cơ chế tương thích.
- Thay đổi authorization hoặc query semantics khiến client cũ không còn làm được hành trình đã cam kết.

Thêm field tùy chọn thường dễ tương thích hơn nhưng phải xem client cũ có xử lý unknown field/unknown enum hay không. Nên có consumer contract tests hoặc telemetry để hiểu client thật sự dùng những field nào trước khi thay đổi.

## 14. Kiểm thử chứng minh API độc lập với persistence

### 14.1. Ma trận kiểm thử

| Nhóm | Kịch bản | Kỳ vọng |
|---|---|---|
| Tạo đơn | Gửi chỉ field hợp đồng | `201 Created`, Location hợp lệ, tính tiền server-side |
| Mass assignment | Gửi thêm `status`/`totalAmount`/`ownerId` | Không thể thao túng nội bộ; lỗi/behavior theo contract |
| Đọc đơn | Đọc đơn thuộc user | `200`, chỉ field công khai, đúng schema |
| BOLA | User B đọc `orderId` của A | `403`/`404`, không lộ dữ liệu |
| Validation | Quantity ≤ 0 hoặc address không thuộc quyền | `400`/`422`/`403` phù hợp, không tạo đơn sai |
| Workflow | Hủy đơn ở trạng thái không cho phép | `409` và mã lỗi nghiệp vụ ổn định |
| Optimistic concurrency | PATCH với ETag đã cũ | `412`, không ghi đè cập nhật mới |
| Idempotency | POST cùng key/payload hai lần hoặc đồng thời | Một đơn logic, response/Location nhất quán |
| Pagination | Limit vượt max, cursor sửa hoặc sort lạ | Lỗi hợp đồng rõ ràng, không lộ query nội bộ |
| Serialization | Entity có quan hệ lazy/cyclic | Response DTO có cấu trúc và chi phí dự kiến, không vòng lặp |
| Internal migration | Đổi tên/tách bảng DB, giữ hành vi | Contract test công khai vẫn qua |
| Error mapping | Vi phạm unique constraint DB | Problem Details ổn định, không lộ SQL |
| Security/cache | Đọc cache hoặc log từ tenant khác | Không lộ PII, secret hay response chéo tenant |

### 14.2. Các tầng test có mục đích

- **Schema/contract tests:** xác nhận status, header `Location`, tên field, kiểu dữ liệu, enum, lỗi và OpenAPI khớp response thực.
- **Controller tests (MockMvc):** input validation, mapping status, security/filter và serialization của DTO; mock use case có mục đích.
- **Application/domain tests:** ràng buộc business, chuyển trạng thái và quyết định giá/stock/ủy quyền.
- **Repository integration tests:** ánh xạ projection với schema thật, transaction, eager/batch fetch, N+1 và query index.
- **Consumer-driven tests:** nếu có client/đối tác độc lập, xác minh những giả định mà họ đã dựa vào và đánh giá breaking change trước rollout.
- **Migration tests:** chạy với dữ liệu mẫu đại diện, đối soát trước/sau và giữ response công khai giống về ngữ nghĩa.

Không viết những test chỉ khẳng định mapper trả đúng các field vừa copy bằng cùng một logic mà không bảo vệ hành vi quan trọng. Test nên phát hiện lỗi có thể gây hại: mass assignment, lộ dữ liệu, mất đơn, mất cập nhật, sai tổng tiền hoặc đổi JSON do refactor DB.

### 14.3. Một phép thử có ý nghĩa với MockMvc

~~~java
// Ví dụ assertion minh họa sau khi đã cấu hình @WebMvcTest,
// mock application service và Spring Security cho user hợp lệ.
mockMvc.perform(post("/v1/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "shippingAddressId": "addr_84",
              "items": [{"sku":"BOOK-123","quantity":2}]
            }
            """))
    .andExpect(status().isCreated())
    .andExpect(header().exists("Location"))
    .andExpect(jsonPath("$.id").value("ord_916"))
    .andExpect(jsonPath("$.status").value("PENDING_PAYMENT"))
    .andExpect(jsonPath("$.internalNote").doesNotExist());
~~~

Đây là **đoạn assertion minh họa**, chưa phải test class chạy độc lập: phải cấu hình principal, dependency mock, response từ use case và import. Đặc biệt cần thêm test gửi field không hợp đồng, user khác đọc đơn và công việc tạo đơn đồng thời; chỉ kiểm tra status/field vắng mặt không đủ chứng minh bảo mật.

## 15. Bài thực hành: sửa API bị phụ thuộc database

**Tình huống:** Một nhóm đang dùng mô hình:

~~~text
Table customers(id, email, phone, vip_flag)
Table order_table(id, customer_id, status_code, cost_total, private_note)
Table order_item(id, order_id, sku, qty, price_snapshot)

POST /api/order_table
GET  /api/order_table/{id}
PUT  /api/order_table/{id}
DELETE /api/order_table/{id}

Request/response trực tiếp là JSON của OrderEntity,
bao gồm customer object và danh sách OrderItemEntity.
~~~

Nhóm chuẩn bị chuyển cơ sở dữ liệu từ một schema cũ sang schema mới; đồng thời ứng dụng mobile cần tạo đơn, xem đơn và yêu cầu hủy, nhưng không được xem `private_note`, thông tin nội bộ của customer khác hoặc tự sửa `status_code`.

### 15.1. Yêu cầu của người học

1. **Nêu ít nhất năm vấn đề** của thiết kế hiện tại và hậu quả của từng vấn đề: coupling, mass assignment, quyền dữ liệu, lazy loading, semantics của DELETE/PUT.
2. **Vẽ resource map** gồm URI tạo đơn, đọc đơn, xem danh sách có phân trang và yêu cầu hủy. Giải thích tại sao hủy đơn đã thanh toán không đơn giản là DELETE row.
3. **Thiết kế CreateOrderRequest** không chứa giá, trạng thái, owner hoặc note; định nghĩa ít nhất bốn validation rules.
4. **Thiết kế OrderResponse** phục vụ mobile: ID, status công khai, dòng hàng, tổng tiền và tiền tệ, thời gian, link. Chỉ rõ một số field nội bộ sẽ không bao giờ serialize.
5. **Chọn status code** cho tạo thành công, không có quyền, đơn không tồn tại, hủy sai trạng thái, cập nhật dựa trên version cũ và retry cùng idempotency key.
6. **Vẽ sơ đồ phân tầng** controller → application → domain/repository → DB và chiều trả projection/DTO; nêu vị trí của validation, authorization, mapping, transaction và xử lý lỗi.
7. **Viết OpenAPI rút gọn** cho POST tạo đơn và GET theo ID, kèm ít nhất hai response lỗi.
8. **Đề xuất kế hoạch migration** khi `order_table.customer_id` đổi thành `purchase_orders.buyer_account_id` nhưng API vẫn giữ `id`/`status`/`totalAmount`.
9. **Lập bảng test** gồm happy path, mass assignment, IDOR/BOLA, concurrency, idempotency, pagination và thay đổi schema DB.

### 15.2. Gợi ý lời giải

**Resource map mẫu:**

~~~text
POST /v1/orders
  -> 201 Created
     Location: /v1/orders/{id}

GET /v1/orders/{id}
  -> 200 OrderResponse (nếu có quyền)

GET /v1/orders?limit=20&cursor=...
  -> 200 danh sách + nextCursor

POST /v1/orders/{id}/cancellations
  -> 201 nếu tạo resource yêu cầu hủy đồng bộ
  -> hoặc 202 nếu đã nhận công việc hủy bất đồng bộ theo hợp đồng
~~~

Đối với request tạo đơn, thông tin caller lấy từ danh tính đã xác thực, không lấy `ownerId` từ JSON. Application service kiểm tra địa chỉ thuộc về caller, tồn kho/giá và sự hợp lệ của trạng thái. Mapper chỉ chọn các field public. Nếu có xử lý giá có thuế hoặc khuyến mãi, tổng tiền phải được định nghĩa theo quy tắc, không tin client gửi `cost_total`.

Khi thay DB, có thể thay `OrderRepositoryAdapter` và query projection mà giữ nguyên controller/OpenAPI. Chạy kiểm thử hợp đồng trước/sau, kiểm tra performance khi số lượng dòng hàng tăng và xác minh không lộ `private_note` hoặc account data sau refactor. Nếu semantics công khai thay đổi thật, tạo phương án version/compatibility có chủ đích.

### 15.3. Câu hỏi phản biện

**Nếu API chỉ có CRUD đơn giản, có cần DTO không?** DTO riêng vẫn là một ranh giới hữu ích khi entity có field nội bộ, authorization khác nhau hoặc DB dự kiến thay. Với ứng dụng rất nhỏ, có thể dùng projection đơn giản; điều quan trọng là chủ động quyết định các field và giữ contract tests, không serialize entity ngoài ý muốn.

**Nếu DTO có trường giống hệt entity, như vậy là thất bại?** Không. Sự giống nhau có thể đúng với yêu cầu hiện tại. Điểm cần kiểm soát là thay đổi entity không tự thay JSON và request không thể gán field trái quyền.

**Nếu bảng có status_code, có phải expose nguyên enum DB?** Không. Có thể ánh xạ trạng thái kỹ thuật sang trạng thái nghiệp vụ công khai và quản lý sự tiến hóa enum theo hợp đồng. Client không cần biết mã vận hành nội bộ hoặc trạng thái gian lận.

**Có phải mọi giao dịch cần microservice riêng?** Không. Một monolith có phân tầng rõ và API contract ổn định có thể phù hợp. Tách dịch vụ khi có ranh giới nghiệp vụ, nhu cầu scale, trách nhiệm vận hành và đánh đổi đủ rõ.

## 16. Checklist thiết kế trước khi phát hành

### Resource và hành vi

- [ ] URI và method thể hiện nghiệp vụ, không chỉ phản ánh tên bảng/ORM method.
- [ ] Mỗi resource có identity, quyền sở hữu và lifecycle rõ.
- [ ] Chỉ công bố thao tác HTTP phù hợp; không ép mọi bảng có đầy đủ CRUD.
- [ ] Các quy tắc chuyển trạng thái quan trọng chạy qua use case được kiểm soát.

### Representation và bảo mật

- [ ] Request DTO chỉ có field caller được phép cung cấp.
- [ ] Response DTO/projection chỉ có field caller được phép xem; không trả trực tiếp JPA Entity.
- [ ] Có validation cấu trúc và kiểm tra nghiệp vụ; field lạ có chính sách cụ thể.
- [ ] Phân quyền theo từng object/tenant khi đọc, ghi, hủy và xem danh sách.
- [ ] Không để các cột nội bộ, dữ liệu cá nhân, mật khẩu, token hoặc stack trace lộ qua serialization.

### Hợp đồng HTTP và tích hợp

- [ ] Status, `Location`, `ETag`/`If-Match` khi cần, schema lỗi và hành vi concurrency đã được thống nhất.
- [ ] Có idempotency cho POST có thể bị retry và tác động nghiệp vụ cần duy nhất.
- [ ] Pagination/filter/sort công khai có allowlist, giới hạn và semantics ổn định.
- [ ] Cache, retention và quyền truy cập phản ánh dữ liệu nhạy cảm của resource.
- [ ] OpenAPI và ví dụ phản hồi được kiểm thử với API runtime.

### Khả năng thay đổi nội bộ

- [ ] Controller không phụ thuộc trực tiếp entity/repository persistence.
- [ ] Lớp ánh xạ và query projection có mục đích, tránh N+1 và payload vô hạn.
- [ ] Migration schema không buộc thay đổi JSON ngoài ý muốn; có test hợp đồng trước/sau.
- [ ] Breaking change được quản lý bằng kế hoạch tương thích hoặc version, có đo ảnh hưởng client.

## 17. Ghi nhớ

**Thiết kế REST API bắt đầu từ resource và hành trình của người dùng, không bắt đầu từ bảng hoặc class của ORM.** Database schema tối ưu cách lưu dữ liệu; domain model bảo vệ quy tắc nghiệp vụ; API contract định nghĩa những khả năng và representation client được phép sử dụng. Ba mối quan tâm này có thể phối hợp mà vẫn giữ ranh giới rõ.

DTO, lớp ánh xạ và use case không phải thủ tục hình thức: chúng giúp server quyết định dữ liệu nào được nhận, dữ liệu nào được công bố và hành động nào hợp lệ. Kết hợp HTTP semantics, OpenAPI, idempotency, phân quyền, pagination, concurrency và kiểm thử hợp đồng sẽ giúp API phát triển theo nhu cầu sản phẩm trong khi schema DB, JPA entity và các tối ưu lưu trữ có thể thay đổi độc lập.

# Thiết kế tài nguyên và ngữ nghĩa HTTP trong REST API

## 1. Vì sao REST API cần ngữ nghĩa HTTP rõ ràng trong Microservices?

Trong kiến trúc Microservices, lời gọi HTTP đồng bộ thường là một trong các cách để hai dịch vụ phối hợp. Ví dụ, Order Service gọi Inventory Service để yêu cầu giữ hàng; ứng dụng web gọi Order Service để xem đơn; Shipping Service cung cấp trạng thái lô giao hàng. Một REST API tốt giúp các bên hiểu **tài nguyên nào được thao tác, hành động có ý nghĩa gì, trạng thái kết quả là gì và khi có lỗi phải xử lý thế nào**.

REST (Representational State Transfer) là phong cách kiến trúc nhấn mạnh tài nguyên, giao diện thống nhất, tính phi trạng thái của mỗi yêu cầu, khả năng cache khi phù hợp và các ràng buộc khác. Một API dùng HTTP/JSON chưa tự động là REST đúng nghĩa; điều quan trọng là cách sử dụng mô hình tài nguyên và ngữ nghĩa giao thức nhất quán.

Khi API chỉ là “RPC đặt trong HTTP”, như **POST /doSomething** cho mọi thao tác, client có thể phải tự suy đoán request có được gửi lại hay không, điều gì xảy ra khi timeout, thay đổi nào có thể cache, khi nào kết quả đã tồn tại và khi nào phải cập nhật trạng thái. Vấn đề trở nên lớn hơn khi các microservice được phát hành riêng, kết nối mạng có thể trễ hoặc thất bại, và các bản client khác nhau cùng tồn tại.

Một thiết kế REST API nên trả lời rõ:

1. **Tài nguyên là gì?** Đối tượng nghiệp vụ nào có định danh và trạng thái có thể quan sát?
2. **URI biểu diễn gì?** Client có thể truy cập tài nguyên hoặc tập tài nguyên ở đâu?
3. **Phương thức HTTP có nghĩa gì?** Đọc, tạo, thay thế, cập nhật một phần hay xóa?
4. **Response thể hiện kết quả gì?** Trạng thái HTTP, representation, header và lỗi có thống nhất không?
5. **Request có thể thử lại an toàn không?** Có idempotency, điều kiện cập nhật và cách xử lý timeout?
6. **Dữ liệu có thể cache và thay đổi tương thích không?** Client cũ có tiếp tục hoạt động được không?
7. **Ranh giới dịch vụ được bảo vệ thế nào?** API có che giấu dữ liệu nội bộ và phản ánh ownership nghiệp vụ không?

Mục tiêu của bài là biết thiết kế API theo **ngữ nghĩa tài nguyên và HTTP**, rồi áp dụng vào giao tiếp đồng bộ giữa các dịch vụ mà không làm rò rỉ quy tắc và dữ liệu nội bộ.

## 2. Tài nguyên, representation và trạng thái nghiệp vụ

**Tài nguyên (resource)** là một khái niệm được nhận diện và quản lý qua API, ví dụ đơn hàng, giỏ hàng, yêu cầu giữ hàng hoặc một giao dịch thanh toán. Tài nguyên không đồng nghĩa với hàng dữ liệu trong một bảng, một class Java hay một endpoint controller.

Ví dụ trong miền bán hàng:

- **Order**: yêu cầu mua có vòng đời, định danh và các quy tắc xác nhận/hủy.
- **Inventory Reservation**: cam kết giữ một số lượng hàng cho một đơn trong một thời hạn.
- **Payment Attempt**: một lần thực hiện hoặc theo dõi yêu cầu thanh toán.
- **Shipment**: lệnh giao hàng và trạng thái vận chuyển.
- **Refund Request**: yêu cầu hoàn tiền với trạng thái kiểm tra/phê duyệt/thực hiện.

Một tài nguyên có thể được lưu qua nhiều bảng. Ngược lại, có các bảng kỹ thuật như outbox, audit và migration history không cần công khai thành REST resource.

**Representation** là biểu diễn một trạng thái của tài nguyên tại thời điểm trả về, thường là JSON. Representation không phải toàn bộ cấu trúc lưu trữ:

~~~http
GET /orders/ORD-1001 HTTP/1.1
Accept: application/json
Authorization: Bearer <token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-1001-v7"
Cache-Control: private, no-cache

{
  "id": "ORD-1001",
  "status": "CONFIRMED",
  "total": {
    "amount": 350000,
    "currency": "VND"
  },
  "createdAt": "2026-11-11T08:00:00Z",
  "version": 7
}
~~~

Client biết được danh tính, trạng thái và giá trị cần dùng của đơn. Nó không cần biết tên bảng, quan hệ khóa ngoại, transaction nội bộ hay dữ liệu bí mật như token thanh toán của nhà cung cấp.

### 2.1. Resource không phải chỉ là CRUD

CRUD là một phần của API, nhưng nhiều miền nghiệp vụ có **chuyển trạng thái bị ràng buộc**. Chẳng hạn, Order có thể được hủy trước khi giao, nhưng không nhất thiết được hủy sau khi lô hàng đã bàn giao cho nhà vận chuyển. Vì vậy thao tác cập nhật chung **PATCH /orders/{id} {"status":"CANCELLED"}** có thể không thể hiện đủ yêu cầu xác thực quyền, lý do hủy, thời điểm và xử lý bù.

Trong trường hợp một hành động có vòng đời riêng, có thể mô hình hóa thành tài nguyên phụ hoặc một yêu cầu nghiệp vụ:

~~~http
POST /orders/ORD-1001/cancellation-requests
Content-Type: application/json

{
  "reasonCode": "CUSTOMER_CHANGED_MIND"
}
~~~

Server xác minh điều kiện và trả về trạng thái yêu cầu hủy. Cách biểu diễn này phù hợp khi cần lưu hồ sơ, phê duyệt hoặc xử lý bất đồng bộ. Nếu nghiệp vụ chỉ cần xóa một tài nguyên hợp lệ, HTTP DELETE có thể đủ. Chọn mô hình xuất phát từ ngữ nghĩa nghiệp vụ, không cố biến tất cả lệnh thành một danh từ giả tạo.

### 2.2. Ranh giới REST API và bounded context

Order Service nên công bố hợp đồng về đơn hàng; Inventory Service công bố hợp đồng về giữ hàng và số tồn khả dụng; Payment Service công bố hợp đồng về giao dịch thanh toán. Một service không nên công bố API cho phép consumer trực tiếp sửa trạng thái nội bộ của service khác.

Ví dụ, Order có thể gọi **POST /inventory-reservations** do Inventory Service cung cấp, nhưng không được trực tiếp đặt **available_quantity = 0** trong database kho. API là một ranh giới điều khiển quy tắc: Inventory tự kiểm tra bất biến và quyết định chấp nhận hay từ chối yêu cầu.

Sự nhất quán giữa các API giúp tương tác dễ hiểu, nhưng **không nên dùng chung một domain model toàn hệ thống** để ép mọi bounded context có cùng dữ liệu và trạng thái.

## 3. Thiết kế URI: định danh tài nguyên, không rò rỉ thao tác

Một URI tốt phản ánh **danh tính và quan hệ tài nguyên**, ổn định đủ lâu để consumer không phải thay đổi theo cấu trúc code.

### 3.1. Dùng danh từ và tên tập tài nguyên rõ

Một phong cách thường dùng:

| Mục đích | URI minh họa | Ý nghĩa |
| --- | --- | --- |
| Liệt kê đơn | GET /orders | Tập đơn hàng mà caller được phép xem |
| Xem một đơn | GET /orders/ORD-1001 | Một Order theo ID |
| Tạo đơn | POST /orders | Yêu cầu tạo một Order mới |
| Thay thế biểu diễn | PUT /orders/ORD-1001 | Thay thế trạng thái biểu diễn có thể cập nhật, nếu API cho phép |
| Cập nhật một phần | PATCH /orders/ORD-1001 | Chỉ cập nhật các trường cho phép |
| Xóa tài nguyên | DELETE /drafts/DR-001 | Xóa hoặc làm tài nguyên dự thảo không còn truy cập được |
| Danh sách mục đơn | GET /orders/ORD-1001/items | Tập line item nằm trong phạm vi đơn |
| Một mục đơn | GET /orders/ORD-1001/items/ITEM-1 | Một phần tử có định danh ổn định |

Nhất quán dùng **/orders**, **/payments** và **/inventory-reservations** thường dễ dự đoán hơn hỗn hợp **/order**, **/getOrders**, **/createNewOrder**. Tuy nhiên không có một tiêu chuẩn bắt buộc tên số ít/số nhiều cho mọi hệ thống; cần áp dụng quy ước đã công bố và tránh đổi URL vô lý.

Tránh URI phụ thuộc framework và code như **/orderController/findById**, **/orderService/save** hoặc **/db/table_order**. Những tên đó làm rò rỉ cách cài đặt thay vì khái niệm nghiệp vụ.

### 3.2. Path, query parameter và request body

- **Path** xác định tài nguyên hoặc tập tài nguyên được truy cập, ví dụ **/orders/ORD-1001**.
- **Query parameter** mô tả phép chọn, lọc, sắp xếp, phân trang hoặc biểu diễn của tập tài nguyên, ví dụ **/orders?status=CONFIRMED&limit=20**.
- **Request body** mang representation hoặc dữ liệu yêu cầu hành động, ví dụ số lượng hàng và địa chỉ nhận.
- **Header** mang thông tin giao thức hoặc điều kiện, chẳng hạn **Authorization**, **If-Match**, **If-None-Match**, **Idempotency-Key**, **Accept** và **Content-Type**.

Đừng truyền dữ liệu bí mật như access token, mật khẩu, khóa API hay thông tin thẻ qua query string. URI thường xuất hiện trong log, lịch sử trình duyệt, proxy và hệ thống giám sát.

### 3.3. Quan hệ lồng nhau và độ sâu URI

Một tài nguyên con có thể được định danh theo cha khi quan hệ sở hữu là thiết yếu:

~~~text
GET /orders/ORD-1001/items/ITEM-1
~~~

Nếu tài nguyên có danh tính và vòng đời độc lập, URI cấp cao có thể tự nhiên hơn:

~~~text
GET /shipments/SHP-9001
GET /payments/PAY-2001
~~~

Không cần tạo đường dẫn dài như **/customers/C1/orders/O1/payments/P1/refunds/R1** chỉ để mô phỏng mối quan hệ dữ liệu. Quan hệ có thể biểu diễn bằng các ID hoặc liên kết trong payload, trong khi quyền truy cập được kiểm tra ở phía server.

### 3.4. ID là định danh, không phải cơ chế bảo mật

ID có thể là UUID, ULID, ID sinh theo hệ thống hoặc mã nghiệp vụ ổn định. Dù ID khó đoán, server vẫn phải kiểm tra caller có quyền đọc/sửa đối tượng đó hay không. Không dùng việc “không thể đoán URL” làm điều kiện bảo vệ dữ liệu.

Nếu phải phân vùng theo tenant, xác định tenant từ thông tin xác thực và chính sách quyền; không tin tuyệt đối tham số **tenantId** do caller gửi.

## 4. Ngữ nghĩa các phương thức HTTP

HTTP method xác định ý định tổng quát và ảnh hưởng cách proxy, cache, client, retry library xử lý request.

| Method | Ngữ nghĩa chuẩn | Safe? | Idempotent? | Ví dụ |
| --- | --- | --- | --- | --- |
| GET | Lấy biểu diễn tài nguyên | Có | Có | GET /orders/ORD-1001 |
| HEAD | Như GET nhưng không trả body | Có | Có | HEAD /orders/ORD-1001 |
| OPTIONS | Tra cứu phương thức/khả năng giao tiếp | Có | Có | OPTIONS /orders |
| POST | Gửi representation để tài nguyên đích xử lý | Không | Không mặc định | POST /orders |
| PUT | Tạo/thay thế trạng thái tài nguyên tại URI cụ thể theo hợp đồng | Không | Có | PUT /profiles/me/preferences |
| PATCH | Áp dụng tập thay đổi cho tài nguyên | Không | Không mặc định | PATCH /orders/ORD-1001 |
| DELETE | Yêu cầu gỡ mối liên hệ URI với tài nguyên | Không | Có | DELETE /drafts/DR-001 |

**Safe** nghĩa là phương thức có ngữ nghĩa chỉ đọc từ góc nhìn kết quả được client yêu cầu. Server vẫn có thể ghi access log hoặc metric khi xử lý GET, nhưng không được khiến một yêu cầu đọc vô tình thay đổi trạng thái nghiệp vụ.

**Idempotent** nghĩa là thực hiện cùng một request một lần hoặc nhiều lần có **hiệu ứng dự kiến giống nhau lên trạng thái server**, không nhất thiết response của mọi lần đều giống nhau. Ví dụ:

- PUT đặt cấu hình **notificationsEnabled=true** nhiều lần vẫn có trạng thái cuối là true.
- DELETE một draft lần đầu trả **204**, lần sau có thể trả **404** nhưng tài nguyên vẫn không tồn tại.
- GET không làm thay đổi nghiệp vụ nên thường có thể thử lại.
- POST tạo đơn mới mỗi lần có thể sinh các đơn khác nhau nếu không có cơ chế deduplication.
- PATCH tăng số lượng lên một đơn vị mỗi lần sẽ không idempotent; PATCH đặt giá trị tuyệt đối có thể idempotent tùy hợp đồng.

**Không dùng GET để hủy đơn, ghi nhận thanh toán hay trừ tồn kho**, dù chỉ là “đường dẫn để dễ gọi”. Bot, prefetcher, cache và công cụ quan sát có thể gọi GET ngoài ý muốn.

### 4.1. GET và HEAD: đọc tài nguyên

GET lấy representation của tài nguyên hoặc tập tài nguyên. Những phản hồi thường gặp là **200 OK**, **304 Not Modified** nếu request có điều kiện và representation chưa đổi, **404 Not Found**, **403 Forbidden** hoặc lỗi máy chủ phù hợp.

~~~http
GET /orders/ORD-1001 HTTP/1.1
Accept: application/json
If-None-Match: "order-1001-v7"
~~~

Nếu tài nguyên chưa đổi:

~~~http
HTTP/1.1 304 Not Modified
ETag: "order-1001-v7"
Cache-Control: private, no-cache
~~~

Response **304** không chứa body của representation; client dùng bản đã cache và metadata phù hợp. HEAD hữu ích khi caller cần header như ETag hoặc Content-Length mà không cần body. Server cần bảo đảm ngữ nghĩa metadata của HEAD tương thích với GET theo quy định HTTP.

### 4.2. POST: tạo hoặc yêu cầu xử lý

POST thường được dùng để tạo tài nguyên trong một collection:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/json
Idempotency-Key: checkout-abc-123

{
  "customerId": "CUS-001",
  "items": [
    { "sku": "SKU-100", "quantity": 2 }
  ],
  "shippingAddressId": "ADDR-22"
}
~~~

Khi server tạo thành công Order:

~~~http
HTTP/1.1 201 Created
Location: /orders/ORD-1001
Content-Type: application/json

{
  "id": "ORD-1001",
  "status": "PENDING_STOCK",
  "items": [
    { "sku": "SKU-100", "quantity": 2 }
  ]
}
~~~

**201 Created** cho biết tài nguyên mới được tạo; **Location** chỉ URI của tài nguyên chính được tạo. Không nên dùng **200 OK** cho tất cả mọi trường hợp chỉ vì client dễ đọc JSON.

POST cũng phù hợp cho tài nguyên yêu cầu xử lý như **/cancellation-requests** hoặc **/refund-requests**. Nếu một thao tác nghiệp vụ cần thời gian, có thể tạo operation resource và trả **202 Accepted**.

### 4.3. PUT: tạo hoặc thay thế trạng thái tại URI đích

PUT nhắm tới một URI được xác định trước và biểu diễn trạng thái mong muốn. Ví dụ cập nhật toàn bộ tập cài đặt thông báo mà client được phép kiểm soát:

~~~http
PUT /users/me/notification-preferences HTTP/1.1
Content-Type: application/json
If-Match: "prefs-v3"

{
  "emailEnabled": true,
  "smsEnabled": false,
  "pushEnabled": true
}
~~~

Khi cập nhật thành công server có thể trả **200 OK** với representation mới hoặc **204 No Content** nếu không trả body. Nếu PUT tạo một tài nguyên trước đó chưa tồn tại và hợp đồng cho phép, thường trả **201 Created**.

**PUT không nên được diễn giải là “chỉ cập nhật các trường xuất hiện trong body”** trừ khi hợp đồng xác định rõ một mô hình thay thế khác. Với PUT thay thế toàn bộ representation có thể ghi, bỏ một trường có thể có ý nghĩa xóa hoặc đặt giá trị mặc định. Nếu client chỉ muốn thay một phần, PATCH thường diễn đạt rõ hơn.

Một request PUT có cùng body có thể cho hiệu ứng cuối giống nhau ngay cả khi gọi lại. Nhưng nếu PUT chứa các side effect khác như gửi email nhiều lần cho cùng giá trị hoặc tự cộng một counter, service đã làm mất tính idempotent mà method này hứa hẹn.

### 4.4. PATCH: thay đổi một phần theo tài liệu rõ

PATCH dùng khi client chỉ cập nhật một số trường. Cần công bố **định dạng patch và cách xử lý null, trường thiếu, điều kiện xung đột**.

Ví dụ dùng JSON Merge Patch:

~~~http
PATCH /profiles/CUS-001 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "profile-v4"

{
  "displayName": "Nguyen Van A",
  "phoneNumber": null
}
~~~

Với JSON Merge Patch, trường null có ý nghĩa **xóa thành phần** theo định dạng đó, không mặc định là gán giá trị null cho mọi mô hình. Nếu cần phân biệt “gán null” và “xóa”, cân nhắc JSON Patch hoặc định dạng patch khác được mô tả chính xác.

Ví dụ JSON Patch:

~~~http
PATCH /profiles/CUS-001 HTTP/1.1
Content-Type: application/json-patch+json
If-Match: "profile-v4"

[
  { "op": "replace", "path": "/displayName", "value": "Nguyen Van A" }
]
~~~

PATCH **không tự idempotent**. Một patch “replace” giá trị tuyệt đối có thể idempotent; một patch tăng counter theo giá trị hiện tại hoặc thêm phần tử vào danh sách có thể không. Client và server phải hiểu ngữ nghĩa cụ thể trước khi triển khai retry.

### 4.5. DELETE: yêu cầu loại bỏ tài nguyên

DELETE có nghĩa yêu cầu gỡ liên hệ URI với tài nguyên; không nhất thiết phải xóa vật lý mọi bản ghi. API có thể dùng soft delete hoặc quy trình lưu trữ theo chính sách nghiệp vụ.

~~~http
DELETE /draft-orders/DR-9001 HTTP/1.1
If-Match: "draft-v5"
~~~

Nếu xóa hoàn tất và không trả body:

~~~http
HTTP/1.1 204 No Content
~~~

Một yêu cầu DELETE thứ hai có thể trả **204** hoặc **404**, tùy hợp đồng; cả hai vẫn phù hợp với idempotency về hiệu ứng. Nếu thao tác xóa thực tế cần xử lý lâu và chưa hoàn tất, server có thể trả **202 Accepted** với nơi theo dõi công việc.

Không dùng DELETE khi cần diễn đạt một quy trình phức tạp như “hủy giao dịch tài chính”, nếu thao tác cần phê duyệt, xử lý bù, đối soát và trạng thái riêng. Khi đó, tài nguyên **cancellation request** hoặc **refund request** có thể thể hiện domain tốt hơn.

## 5. Chọn phương thức theo hành vi nghiệp vụ

Một bảng quyết định thực tế:

| Nhu cầu | Thiết kế thường phù hợp | Lưu ý |
| --- | --- | --- |
| Xem trạng thái Order | GET /orders/{id} | Không thay đổi trạng thái nghiệp vụ |
| Lọc các Order | GET /orders?status=... | Phân trang và áp quyền |
| Tạo Order | POST /orders | 201 + Location; idempotency key nếu sợ gửi trùng |
| Ghi cài đặt có URI ổn định | PUT /users/me/preferences | Nhất quán việc thay thế và cập nhật có điều kiện |
| Sửa một vài trường hồ sơ | PATCH /profiles/{id} | Công bố patch media type, trường được sửa |
| Xóa bản nháp | DELETE /draft-orders/{id} | Có thể yêu cầu If-Match |
| Yêu cầu giữ hàng | POST /inventory-reservations | Tạo reservation có vòng đời |
| Yêu cầu hoàn tiền | POST /refund-requests | Có thể đợi duyệt hoặc xử lý bất đồng bộ |
| Lấy tiến độ của job | GET /operations/{id} | 200 với trạng thái trung gian/hoàn thành |
| Huỷ một yêu cầu đang chờ | POST /operations/{id}/cancellation-requests | Tài nguyên yêu cầu hủy nếu domain cần lưu kết quả |

**Lựa chọn URI/phương thức phải phục vụ ngữ nghĩa thực tế**. Không cần thay đổi mọi API hiện có chỉ để trông “giống REST”. Cần có tính nhất quán và hợp đồng rõ, nhất là khi một API đã có client phụ thuộc.

## 6. HTTP status code: kết quả là một phần của hợp đồng

HTTP status code cho client biết ý nghĩa kết quả ở cấp giao thức. Body bổ sung chi tiết chứ không thay status.

### 6.1. Nhóm 2xx: thành công

| Code | Ý nghĩa | Tình huống REST |
| --- | --- | --- |
| 200 OK | Request thành công, có representation hoặc kết quả | GET tài nguyên; PATCH trả representation mới |
| 201 Created | Tài nguyên được tạo | POST /orders thành công, có Location |
| 202 Accepted | Đã nhận để xử lý, chưa cam kết hoàn thành | Yêu cầu xuất báo cáo hoặc thực hiện nghiệp vụ chậm |
| 204 No Content | Thành công, không trả body | DELETE xong; PUT/PATCH không cần body |

**202 Accepted không đồng nghĩa nghiệp vụ cuối cùng đã thành công**. Ví dụ, một lệnh hoàn tiền có thể được chấp nhận vào hàng đợi nhưng sau đó bị từ chối bởi nhà cung cấp. Cần cung cấp tài nguyên operation/request để client kiểm tra kết quả.

### 6.2. Nhóm 3xx: điều kiện/cache và chuyển hướng

**304 Not Modified** thường dùng cho conditional GET/HEAD: representation client đã cache còn hợp lệ. Nó không phải lỗi; client dùng cache tương ứng. Các redirect khác có thể phù hợp trong API nhưng cần cân nhắc việc client tự theo chuyển hướng, các header xác thực và thay đổi method. Không tạo redirect tùy tiện giữa hai service khiến client bị phụ thuộc vào địa chỉ nội bộ.

### 6.3. Nhóm 4xx: yêu cầu không thể được thực hiện như gửi

| Code | Ý nghĩa chính | Ví dụ |
| --- | --- | --- |
| 400 Bad Request | Request sai cú pháp, tham số hoặc dạng yêu cầu không hợp lệ | JSON malformed, query parameter sai định dạng |
| 401 Unauthorized | Chưa có thông tin xác thực hợp lệ | Thiếu/không hợp lệ access token; thường có WWW-Authenticate phù hợp |
| 403 Forbidden | Đã xác định caller nhưng không được phép thực hiện | Nhân viên không có quyền duyệt refund |
| 404 Not Found | Không tìm thấy representation tài nguyên trong ngữ cảnh yêu cầu | Order ID không tồn tại hoặc không được tiết lộ |
| 405 Method Not Allowed | URI không hỗ trợ method này | PUT với resource chỉ đọc; kèm Allow header |
| 406 Not Acceptable | Không thể tạo representation đáp ứng Accept | Client đòi format không được hỗ trợ |
| 409 Conflict | Xung đột với trạng thái tài nguyên hiện tại | Hủy Order đã giao; trạng thái không cho chuyển |
| 410 Gone | Resource đã bị loại bỏ vĩnh viễn theo thông tin server biết | Tài nguyên đã ngừng cung cấp |
| 412 Precondition Failed | Điều kiện như If-Match không còn đúng | ETag cũ khi cập nhật Order |
| 415 Unsupported Media Type | Content-Type hoặc định dạng body không được hỗ trợ | Gửi XML khi endpoint chỉ nhận JSON |
| 422 Unprocessable Content | Cú pháp hiểu được nhưng nội dung không xử lý theo quy tắc | Dữ liệu hợp lệ về JSON nhưng không thỏa validation/semantics |
| 428 Precondition Required | Server yêu cầu request phải có precondition | Bắt buộc If-Match khi sửa tài nguyên |
| 429 Too Many Requests | Quá giới hạn tần suất | Quota/rate limit; có thể kèm Retry-After |

Cách dùng **400** và **422** có thể tùy quy ước API nhưng phải thống nhất. Tránh trả **200 OK** với body **{"success":false}** cho mọi trường hợp lỗi: client, metrics, retry và proxy sẽ mất tín hiệu chính xác.

**401** là vấn đề xác thực, còn **403** là từ chối quyền truy cập. Server có thể dùng **404** để không tiết lộ sự tồn tại của tài nguyên nhạy cảm nếu phù hợp chính sách bảo mật.

### 6.4. Nhóm 5xx: server hoặc phụ thuộc không thể xử lý

| Code | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| 500 Internal Server Error | Lỗi không mong đợi trong server | Ghi log, trace, trả lỗi an toàn |
| 502 Bad Gateway | Gateway nhận phản hồi không hợp lệ từ upstream | Điều tra upstream và proxy |
| 503 Service Unavailable | Server tạm không sẵn sàng | Có thể kèm Retry-After nếu có căn cứ |
| 504 Gateway Timeout | Gateway/proxy không nhận phản hồi kịp | Client cần chính sách timeout/retry và idempotency |

Không biến mọi lỗi của Inventory thành **400** ở Order. Lỗi nghiệp vụ “hết hàng” có thể là conflict hoặc phản hồi nghiệp vụ đã định nghĩa; lỗi do Inventory không kết nối được là lỗi phụ thuộc thời gian chạy. Hai trường hợp cần hành vi retry, phản hồi khách hàng và cảnh báo khác nhau.

### 6.5. Một số trường hợp dễ nhầm

**404 hay 409?** Nếu tài nguyên không tồn tại, 404 thường phù hợp. Nếu tài nguyên tồn tại nhưng trạng thái hiện tại khiến thao tác không hợp lệ, 409 thường diễn đạt tốt hơn.

**409 hay 412?** Nếu client gửi **If-Match** với ETag cũ, 412 diễn đạt precondition không thỏa. Nếu chính trạng thái nghiệp vụ không cho phép thao tác, chẳng hạn đã đóng sổ kế toán, 409 có thể phù hợp.

**202 hay 201?** Nếu đã tạo một request/operation resource nhưng nghiệp vụ xử lý sau, có thể trả 201 để nói rằng request resource đã được tạo, hoặc 202 để nhấn mạnh thao tác đang chờ xử lý. Điều cần ghi rõ là **đối tượng nào đã tồn tại và điều gì chưa hoàn tất**.

**204 có body không?** Không. Nếu muốn trả representation mới, dùng 200 với body.

## 7. Thiết kế lỗi theo Problem Details

Các client cần lỗi **đọc được bằng máy, ổn định và dễ truy nguyên**. Một cách phổ biến là định dạng Problem Details for HTTP APIs, media type **application/problem+json**.

Ví dụ client yêu cầu hủy đơn đã giao:

~~~http
POST /orders/ORD-1001/cancellation-requests HTTP/1.1
Content-Type: application/json

{
  "reasonCode": "CUSTOMER_CHANGED_MIND"
}
~~~

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-cannot-be-cancelled",
  "title": "Order cannot be cancelled",
  "status": 409,
  "detail": "Order ORD-1001 has already been handed over for shipment.",
  "instance": "/orders/ORD-1001/cancellation-requests",
  "code": "ORDER_ALREADY_SHIPPED",
  "traceId": "5eaf0aa3b7d14b80"
}
~~~

Các trường cơ bản:

- **type:** định danh loại lỗi, có thể là URI tài liệu lỗi ổn định.
- **title:** mô tả ngắn gọn, không thay đổi nghĩa giữa các lần gặp cùng loại lỗi.
- **status:** mã HTTP của lần phản hồi.
- **detail:** giải thích cụ thể, phù hợp để hiển thị hoặc hỗ trợ xử lý.
- **instance:** định danh lần xảy ra/vị trí liên quan.
- **code**, **traceId:** ví dụ extension phục vụ ứng dụng và vận hành.

Không trả stack trace, SQL, secret, token, thông tin hạ tầng nội bộ hoặc dữ liệu người dùng không cần thiết ra API. Với validation, có thể thêm danh sách lỗi trường theo schema đã công bố. Client nên dựa vào **HTTP status và code ổn định**, thay vì parse câu tiếng Việt/tiếng Anh tự do trong detail.

### 7.1. Mẫu lỗi kiểm tra dữ liệu

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/validation",
  "title": "Validation failed",
  "status": 422,
  "code": "ORDER_VALIDATION_FAILED",
  "errors": [
    {
      "field": "items[0].quantity",
      "reason": "MUST_BE_POSITIVE"
    }
  ]
}
~~~

Ngữ nghĩa **errors** là extension do API định nghĩa. Phải thống nhất giữa các endpoint để consumer có thể xử lý có hệ thống.

## 8. Idempotency: xử lý request lặp khi mạng không đáng tin tuyệt đối

Trong giao tiếp đồng bộ, timeout không chứng minh request chưa được server xử lý. Client có thể gửi POST tạo đơn, server đã ghi đơn nhưng phản hồi bị mất trên mạng. Nếu client tự gửi lại, rất dễ tạo hai đơn hoặc thu tiền hai lần.

**Idempotency ở cấp nghiệp vụ** giúp server nhận ra nhiều request thực hiện cùng một ý định logic và trả về kết quả tương ứng mà không lặp side effect nguy hiểm.

### 8.1. GET/PUT/DELETE và POST khác nhau thế nào?

HTTP coi GET/HEAD/OPTIONS là safe; GET, PUT và DELETE có ngữ nghĩa idempotent. Điều đó không làm POST tự idempotent. Với POST quan trọng như checkout hoặc payment, API thường cần cơ chế **Idempotency-Key** hoặc client-generated request ID nếu muốn hỗ trợ retry an toàn.

Ví dụ:

~~~http
POST /payments HTTP/1.1
Idempotency-Key: checkout-ORD-1001-attempt-1
Content-Type: application/json

{
  "orderId": "ORD-1001",
  "amount": 350000,
  "currency": "VND",
  "paymentMethodId": "PM-001"
}
~~~

Khi lần gọi đầu đã thực hiện thành công, lần gửi lại **cùng khóa và cùng payload trong phạm vi hiệu lực** phải được xử lý theo hợp đồng idempotency: không tạo lần thu tiền thứ hai. Có thể trả lại cùng kết quả đã lưu hoặc trạng thái request hiện tại; phải công bố hành vi.

### 8.2. Điều kiện thiết kế idempotency key

1. **Phạm vi khóa:** khóa được so sánh trong ngữ cảnh nào, ví dụ tenant + client + endpoint + key.
2. **Fingerprint request:** nếu một khóa cũ đi cùng payload khác, server cần từ chối bằng lỗi xác định, không âm thầm coi như giao dịch giống nhau.
3. **Atomicity:** việc ghi nhận khóa và bắt đầu/tạo hiệu ứng nghiệp vụ phải có cơ chế nhất quán, tránh hai request đồng thời đều vượt qua kiểm tra.
4. **TTL/retention:** bao lâu khóa còn có hiệu lực; client phải biết phạm vi thử lại.
5. **Response replay:** server trả status/representation thế nào khi gặp lại request đã xử lý hoặc đang xử lý.
6. **Downstream idempotency:** nếu service gọi payment provider, cần truyền một danh tính giao dịch ổn định và dùng cơ chế chống xử lý trùng ở bước downstream.
7. **Quan sát:** metric cho request trùng, xung đột key, timeout và kết quả đang chờ.

Một Idempotency-Key không tự giải quyết các bất biến khác như “tổng tiền hoàn không vượt tiền đã thu”. Chính service sở hữu nghiệp vụ vẫn phải thực thi quy tắc ở tầng dữ liệu/transaction phù hợp.

### 8.3. Retry cần dựa vào loại lỗi

Không retry mọi **4xx** vì chúng thường đòi sửa dữ liệu hoặc quyền. Với lỗi tạm thời như **429**, **503** hoặc timeout, có thể retry có giới hạn, backoff và jitter, nhưng chỉ khi thao tác có thể lặp an toàn. Cần có **deadline tổng**, tránh nhiều tầng microservice cùng retry khiến lưu lượng tăng vọt.

Nếu đã nhận **202 Accepted** cùng URI theo dõi operation, client thường nên **kiểm tra operation**, thay vì POST lại một ý định mới không có idempotency.

## 9. Đồng thời và chống ghi đè: ETag, If-Match và version

Hai client có thể cùng đọc một đơn, rồi mỗi bên cập nhật trên phiên bản cũ. Nếu server ghi đè bản cập nhật trước mà không phát hiện, xảy ra **lost update**.

### 9.1. Cập nhật có điều kiện với ETag

Lần đọc ban đầu:

~~~http
GET /draft-orders/DR-9001 HTTP/1.1
~~~

~~~http
HTTP/1.1 200 OK
ETag: "draft-9001-v3"
Content-Type: application/json

{
  "id": "DR-9001",
  "notes": "Giao giờ hành chính",
  "version": 3
}
~~~

Client sửa trên phiên bản v3:

~~~http
PATCH /draft-orders/DR-9001 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "draft-9001-v3"

{
  "notes": "Giao sau 17:00"
}
~~~

Server chỉ thực hiện nếu phiên bản hiện tại thỏa **If-Match**. Nếu một client khác đã cập nhật lên v4, server trả:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/stale-resource",
  "title": "Resource version changed",
  "status": 412,
  "code": "STALE_RESOURCE_VERSION"
}
~~~

Client cần đọc lại và quyết định áp dụng thay đổi trên dữ liệu mới. Không tự gửi lại patch mù khi nó có thể ghi đè thay đổi của người khác.

### 9.2. Phân biệt If-None-Match và If-Match

- **If-None-Match** thường dùng khi đọc có điều kiện để tránh tải representation chưa thay đổi, hoặc yêu cầu chỉ tạo khi URI chưa tồn tại với giá trị **\***.
- **If-Match** yêu cầu phiên bản hiện tại khớp trước khi sửa/xóa, giúp chống cập nhật dựa trên dữ liệu cũ.
- **ETag** là validator của representation. API cần tạo và kiểm tra đúng theo quy tắc của nó; không dùng một timestamp làm giả ETag nếu độ phân giải không thể phân biệt những lần thay đổi.

Không trộn lẫn ETag cho response đã biến đổi theo quyền/locale với phiên bản đối tượng nếu sự khác nhau đó làm điều kiện cập nhật sai. Với endpoint cần optimistic concurrency, hãy thiết kế rõ representation nào được so sánh và điều kiện cập nhật nào thực sự được DB bảo vệ.

### 9.3. Business invariant vẫn là bắt buộc

Ngay cả khi If-Match đúng, request vẫn có thể vi phạm chính sách: không thể hủy đơn đã giao, không được xuất tồn âm hoặc không được hoàn tiền quá hạn mức. ETag chỉ giải quyết **một loại điều kiện đồng thời**, không thay thế validation và transaction bảo vệ quy tắc nghiệp vụ.

## 10. Cache HTTP: giảm tải nhưng phải bảo vệ tính đúng đắn

Cache là một phần của mô hình HTTP, rất hữu ích với dữ liệu nhiều người đọc và ít thay đổi như catalog công khai. Trong Microservices, cache có thể giảm số lượng lời gọi đồng bộ và độ trễ, nhưng nếu cache sai tài nguyên hoặc không phân biệt quyền truy cập sẽ gây lỗi nghiêm trọng.

### 10.1. Các header quan trọng

- **Cache-Control: public, max-age=...** cho representation thực sự có thể chia sẻ, ví dụ thông tin catalog công khai.
- **Cache-Control: private** dành cho dữ liệu chỉ phù hợp cache theo từng client, không chia sẻ trong shared cache.
- **Cache-Control: no-store** yêu cầu không lưu trữ representation trong cache; phù hợp với nội dung nhạy cảm khi cần.
- **Cache-Control: no-cache** cho phép lưu trữ nhưng phải xác minh lại trước khi tái sử dụng trong điều kiện thông thường.
- **ETag** giúp kiểm tra representation đã thay đổi hay chưa.
- **Last-Modified** có thể dùng cho kiểm tra điều kiện dựa trên thời gian khi phù hợp.
- **Vary** thông báo những request header ảnh hưởng đến representation để cache phân biệt đúng phiên bản.

Ví dụ:

~~~http
GET /catalog/products/SKU-100 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60
ETag: "sku-100-catalog-v11"

{
  "sku": "SKU-100",
  "name": "Sổ tay",
  "displayPrice": {
    "amount": 45000,
    "currency": "VND"
  }
}
~~~

Nếu giá thay đổi theo khách hàng, hợp đồng hoặc thị trường, representation trên **không được đánh dấu public cache một cách đơn giản**. Cần thiết kế khóa cache, chính sách riêng tư và mức chấp nhận dữ liệu cũ dựa trên đặc tính nghiệp vụ.

### 10.2. Khi nào không nên cache tùy tiện?

- Kết quả xác thực hoặc thông tin tài khoản nhạy cảm.
- Số dư, hạn mức, trạng thái giao dịch cần độ mới rất cao.
- Tồn kho khả dụng dùng để ra quyết định giữ hàng mà không kiểm tra lại tại owner.
- Nội dung phụ thuộc quyền nhưng response header không tách được các quyền/tenant.

Một GET tồn kho có cache không được biến thành quyền quyết định chắc chắn rằng khách hàng sẽ giữ được sản phẩm. **Việc giữ hàng phải được xác nhận bởi Inventory Service** tại thời điểm yêu cầu.

## 11. Phân trang, lọc, sắp xếp và tìm kiếm collection

REST API thường bị quá tải khi danh sách không có giới hạn. Một endpoint **GET /orders** cần có chiến lược phân trang và quyền truy cập rõ.

### 11.1. Truy vấn danh sách

~~~http
GET /orders?status=CONFIRMED&limit=20&sort=-createdAt HTTP/1.1
Accept: application/json
~~~

Ví dụ response:

~~~json
{
  "items": [
    {
      "id": "ORD-1001",
      "status": "CONFIRMED",
      "createdAt": "2026-11-11T08:00:00Z"
    },
    {
      "id": "ORD-1000",
      "status": "CONFIRMED",
      "createdAt": "2026-11-10T17:00:00Z"
    }
  ],
  "nextCursor": "opaque-cursor-token",
  "hasMore": true
}
~~~

Các query parameter cần định nghĩa:

- **status:** giá trị trạng thái hợp lệ; unknown value được xử lý thế nào.
- **limit:** mặc định, lớn nhất, lỗi nếu vượt giới hạn.
- **sort:** các trường được hỗ trợ và chiều tăng/giảm.
- **cursor/page:** cơ chế phân trang; cursor nên opaque, không yêu cầu client giải mã.
- **filter:** điều kiện có thể kết hợp và cách escape đặc biệt.

### 11.2. Offset và cursor

**Offset pagination** như **?limit=20&offset=40** dễ hiểu nhưng có thể bỏ qua hoặc lặp item khi dữ liệu thay đổi giữa các request, và truy vấn offset lớn có thể tốn tài nguyên.

**Cursor pagination** phù hợp hơn với tập dữ liệu liên tục có insert/update nếu được thiết kế với thứ tự ổn định (ví dụ timestamp + ID), quy tắc snapshot hoặc cách xử lý thay đổi. Cursor không tự đảm bảo không lặp/thiếu item trong mọi điều kiện; hợp đồng cần mô tả kỳ vọng.

Client không nên giả định một trang dưới limit có nghĩa đã hết dữ liệu nếu API có trường **hasMore** hoặc **nextCursor**. Server cần áp phân quyền trước khi xây danh sách trả về và không tiết lộ bản ghi khác tenant.

### 11.3. Trường tìm kiếm và quyền dữ liệu

Không cho phép truy vấn tùy ý tới cột, biểu thức SQL hoặc field nội bộ chỉ vì client gửi **filter**. API công bố các tiêu chí tìm kiếm được hỗ trợ, kiểm tra đầu vào, limit tài nguyên và chỉ trả những trường mà caller được phép xem.

## 12. Content negotiation và định dạng dữ liệu

Client dùng **Accept** để thể hiện dạng response mong muốn; server dùng **Content-Type** để khai báo định dạng body được gửi. Khi request có body, client dùng **Content-Type** để cho biết cách giải mã body.

Ví dụ:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/json
~~~

Nếu server chỉ hỗ trợ JSON mà caller gửi **Content-Type: application/xml**, server có thể trả **415 Unsupported Media Type**. Nếu client yêu cầu representation không được hỗ trợ trong **Accept**, có thể dùng **406 Not Acceptable**.

### 12.1. Ngày giờ và tiền

- Thời gian nên có quy ước rõ, thường là ISO 8601/RFC 3339 với offset hoặc UTC, như **2026-11-11T08:00:00Z**.
- Không gửi thời gian kiểu **11/11/26 15:00** nếu thiếu timezone và định dạng.
- Tiền phải có currency và quy ước chính xác: ví dụ số nguyên đơn vị nhỏ nhất khi phù hợp hoặc decimal với scale rõ, không tính tiền bằng float thiếu kiểm soát.
- Những ID như số tài khoản, mã đơn, SKU nên biểu diễn là string khi không phải lượng số học; tránh mất số 0 đầu và độ chính xác khi client JavaScript đọc số lớn.
- Phân biệt null, trường thiếu và chuỗi rỗng; mỗi trường có ý nghĩa nghiệp vụ nào phải được công bố.

### 12.2. Định dạng response thống nhất

Không cần bọc tất cả response trong cấu trúc **{"data":..., "error":..., "success":...}** nếu điều đó che khuất status HTTP. Điều quan trọng là nhất quán giữa các API về dữ liệu, lỗi, phân trang, trace, timezone và version.

Hợp đồng nên có ví dụ cho ca thành công, dữ liệu không hợp lệ, không có quyền, xung đột trạng thái, phiên bản cũ và lỗi tạm thời.

## 13. Tính phi trạng thái và session

Trong REST, mỗi request cần mang đủ ngữ cảnh để server xử lý theo hợp đồng mà không phụ thuộc vào một chuỗi hội thoại ẩn trong bộ nhớ của một instance. Ví dụ request được xác thực bằng access token hoặc một cơ chế phiên được khai báo phù hợp; nếu các instance sau phải nhớ những bước trước đó theo cách không chia sẻ/không ổn định, load balancing và failover khó hơn.

**Stateless không có nghĩa server không lưu dữ liệu nghiệp vụ.** Server vẫn lưu Order, Payment, Reservation và trạng thái operation. Khác biệt là trạng thái đó được biểu diễn thành tài nguyên/quy trình có định danh rõ thay vì giữ trong một session không được công bố.

Ví dụ khi cần xử lý export báo cáo nhiều phút, nên tạo một **operation resource** để client kiểm tra tiến độ, thay vì giữ một kết nối HTTP mở vô hạn hoặc yêu cầu client gọi đúng cùng instance.

## 14. Yêu cầu xử lý dài: 202 Accepted và operation resource

Một số nghiệp vụ như xuất báo cáo, nhập dữ liệu lớn hoặc đối soát thanh toán không thể hoàn tất trong thời gian chờ của một request đồng bộ. REST API có thể dùng mô hình **request–operation**:

~~~http
POST /reports/export-requests HTTP/1.1
Content-Type: application/json
Idempotency-Key: report-customer-7-20261111

{
  "reportType": "ORDER_SUMMARY",
  "from": "2026-11-01",
  "to": "2026-11-10"
}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: /operations/OP-9001
Retry-After: 5
Content-Type: application/json

{
  "operationId": "OP-9001",
  "status": "PENDING"
}
~~~

Client theo dõi:

~~~http
GET /operations/OP-9001 HTTP/1.1
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "operationId": "OP-9001",
  "status": "COMPLETED",
  "result": {
    "downloadUrl": "/reports/REP-901"
  }
}
~~~

Ở trường hợp lỗi, operation resource có thể mang trạng thái **FAILED** và thông tin lỗi nghiệp vụ thích hợp. **200** của GET operation chỉ cho biết việc đọc trạng thái operation thành công; bản thân operation có thể thất bại. Client phải phân biệt hai tầng kết quả.

Server cần quy định retention của operation và file kết quả, quyền truy cập, frequency poll và cách hết hạn. Nếu sử dụng **Retry-After**, nó chỉ là gợi ý thời gian trong ngữ cảnh response; client vẫn phải tuân thủ deadline và giới hạn tổng.

## 15. REST API ở ranh giới giữa các microservice

Một API được thiết kế tốt phải vừa đúng ngữ nghĩa HTTP vừa thể hiện **ownership của miền**. Xét quá trình đặt hàng:

~~~text
Web / Mobile Client
       |
       v
API Gateway / BFF (neu can)
       |
       v
Order Service
       |
       +---- POST /inventory-reservations ---> Inventory Service
       |
       +---- POST /payment-requests --------> Payment Service
       |
       +---- POST /shipments ---------------> Shipping Service
~~~

Đây là sơ đồ minh họa; tên endpoint và việc gọi đồng bộ hay bất đồng bộ tùy thiết kế nghiệp vụ. Mỗi service tự kiểm tra điều kiện trong ranh giới của mình. Order không tự sửa bảng tồn hoặc thay đổi giao dịch thanh toán trực tiếp.

### 15.1. Phân biệt kết quả giao thức và kết quả nghiệp vụ

Giả sử Order gọi Inventory để giữ hàng:

~~~http
POST /inventory-reservations HTTP/1.1
Content-Type: application/json
Idempotency-Key: reserve-ORD-1001-v1

{
  "orderId": "ORD-1001",
  "lines": [
    { "sku": "SKU-100", "quantity": 2 }
  ]
}
~~~

Có thể có ba loại kết quả:

1. **201 Created:** một reservation mới đã được tạo, trả **Location** và trạng thái của reservation.
2. **409 Conflict** hoặc response nghiệp vụ tương ứng: quy tắc tồn kho không cho giữ số lượng yêu cầu; client phải hiểu kết quả từ chối đã được xác định.
3. **503/504 hoặc timeout:** chưa xác định được kết quả nghiệp vụ; không được mặc định là “không có reservation”. Cần dùng idempotency key để retry hoặc tra cứu theo request identity.

Cần chọn và công bố status code nhất quán với mô hình. Nếu service chọn tạo một request resource ngay cả khi giữ hàng chưa hoàn tất, **202** cùng URI theo dõi có thể phù hợp hơn **201** cho reservation đã xác nhận.

### 15.2. Tránh chuỗi lời gọi đồng bộ quá dài

Nếu Gateway gọi Order, Order gọi Payment, Payment gọi Fraud, Fraud lại gọi Customer, thời gian chờ và điểm lỗi sẽ tăng theo chuỗi. Một API có ngữ nghĩa HTTP tốt vẫn có thể làm hệ thống kém ổn định nếu phụ thuộc thời gian chạy quá nhiều.

Các nguyên tắc vận hành:

- Đặt timeout và **deadline** rõ cho từng lời gọi và toàn luồng.
- Giới hạn retry, dùng backoff và jitter; tránh mọi tầng cùng retry.
- Có bảo vệ tài nguyên, circuit breaker/bulkhead khi phù hợp với tải và loại lỗi.
- Dùng correlation ID và distributed tracing để theo dõi đường đi.
- Chỉ chuyển sang bất đồng bộ khi nghiệp vụ cho phép trạng thái trung gian, eventual consistency và xử lý lỗi theo sau.
- Không giữ transaction database mở trong lúc đợi nhiều dịch vụ chậm hoặc nhà cung cấp bên ngoài nếu có thể tránh.

### 15.3. API Gateway không thay quyền sở hữu nghiệp vụ

Gateway có thể thực hiện routing, xác thực ở biên, rate limiting, ghi log và chuyển đổi một số representation. Nhưng các bất biến như “không hoàn tiền quá số tiền đã thu” phải nằm ở service sở hữu nghiệp vụ, không được phụ thuộc riêng vào Gateway. Nội bộ có thể gọi service mà không đi qua giao diện biên; nghiệp vụ vẫn phải được bảo vệ.

## 16. API versioning và thay đổi tương thích

Microservices phát hành độc lập thường có nhiều phiên bản producer/consumer tồn tại đồng thời. Vì vậy API design phải cân nhắc thay đổi dài hạn, không chỉ khớp với client vừa được build hôm nay.

### 16.1. Những thay đổi thường ít phá vỡ hơn

- Thêm trường response tùy chọn khi client được thiết kế bỏ qua field không biết.
- Thêm endpoint/tài nguyên mới.
- Mở rộng khả năng lọc hoặc sắp xếp mà không đổi nghĩa các tùy chọn cũ.
- Thêm giá trị mới cho enum **chỉ khi consumer được thiết kế chấp nhận giá trị chưa biết**; không giả định enum mới luôn tương thích.

### 16.2. Những thay đổi dễ phá vỡ hợp đồng

- Đổi tên/xóa trường đang được consumer sử dụng.
- Đổi kiểu dữ liệu, đơn vị tiền, timezone hoặc ý nghĩa của một trạng thái.
- Đổi mã status của các trường hợp client đang phân biệt nếu không thông báo.
- Biến trường tùy chọn thành bắt buộc.
- Thay đổi yêu cầu quyền mà consumer hợp lệ hiện chưa đáp ứng.
- Thay đổi mặc định sắp xếp hoặc pagination khiến client hiển thị dữ liệu khác.
- Đổi cách xử lý idempotency key hoặc thời hạn tồn tại của khóa.
- Chuyển resource tới URI mới mà không có kế hoạch chuyển đổi.

Một thay đổi **giữ nguyên JSON schema nhưng đổi nghĩa “CONFIRMED”** có thể nguy hiểm hơn việc thêm một field. Hợp đồng bao gồm cả semantics, không chỉ hình dạng dữ liệu.

### 16.3. Chiến lược versioning

Có nhiều cách:

- **Đường dẫn:** /v1/orders và /v2/orders.
- **Media type/Accept:** khách yêu cầu một representation đã phiên bản hóa.
- **Tương thích tiến hóa:** giữ URL ổn định, mở rộng có kiểm soát và chỉ tạo version mới khi cần thay đổi phá vỡ.

Không có một chiến lược tốt nhất. Quyết định dựa trên số consumer, công cụ hỗ trợ, vòng đời khách hàng, tài liệu và chính sách deprecation. Quan trọng là có **consumer inventory**, thời gian hỗ trợ, thông báo và chỉ số sử dụng trước khi bỏ hợp đồng cũ.

### 16.4. Expand–migrate–contract

Ví dụ muốn đổi **customerName** thành **customerDisplayName**:

1. **Expand:** service cung cấp cả hai trường hoặc trường mới với hành vi tương thích, định nghĩa rõ mối liên hệ.
2. **Migrate:** chuyển consumer dần sang trường mới, đo mức dùng trường cũ và chạy contract tests.
3. **Contract:** xóa trường cũ trong một phiên bản phá vỡ hợp đồng đã được công bố hoặc khi toàn bộ consumer phù hợp đã chuyển.

Với thay đổi yêu cầu trường input mới, có thể server chấp nhận cả hai trong một giai đoạn, thay vì yêu cầu toàn bộ consumer phải deploy đồng thời.

## 17. Bảo mật, phân quyền và kiểm soát thông tin

HTTP status và URI rõ ràng không thay thế được bảo mật. Mỗi endpoint cần xác thực, phân quyền và kiểm soát dữ liệu theo tài nguyên.

### 17.1. Phân biệt authentication và authorization

**Authentication** trả lời “ai đang gọi?”. **Authorization** trả lời “caller được phép làm gì trên tài nguyên cụ thể này?”. Một token hợp lệ không cho phép người dùng đọc Order của người khác.

Ví dụ **GET /orders/ORD-1001** phải kiểm tra chủ sở hữu, tenant và quyền cần thiết trước khi trả dữ liệu. Với truy vấn collection, bộ lọc phân quyền phải được áp dụng cho cả tập, không chỉ xóa field nhạy cảm khỏi những record đã bị truy vấn sai.

### 17.2. Quyền giữa các service

Service-to-service authentication có thể dùng cơ chế token phù hợp, mTLS hoặc nền tảng nhận dạng dịch vụ theo kiến trúc được chọn. Không coi lời gọi “trong mạng nội bộ” mặc nhiên đáng tin. Inventory cần biết caller nào được tạo reservation; Payment phải bảo vệ các lệnh có side effect và chứng thực nguồn callback từ đối tác.

### 17.3. Validation và giới hạn tài nguyên

- Kiểm tra input length, số lượng phần tử, định dạng ID, JSON nesting và giá trị hợp lệ.
- Giới hạn body size, pagination size, timeout và concurrency để giảm rủi ro cạn tài nguyên.
- Không đưa tham số vào SQL/query một cách thiếu kiểm soát.
- Không hiển thị stack trace, thông tin connection string, access token hoặc dữ liệu cá nhân trong lỗi.
- Thực hiện rate limiting theo identity hoặc phạm vi phù hợp, trả status và hướng dẫn retry rõ.
- Cân nhắc CORS ở lớp browser nếu API được gọi xuyên origin; CORS không thay thế authorization.

### 17.4. Audit và quyền riêng tư

Các thao tác như hủy đơn, hoàn tiền, đổi địa chỉ giao hàng có thể cần audit với ai thực hiện, lúc nào, căn cứ nào và kết quả gì. Log vận hành nên chứa ID giao dịch, trạng thái, thời gian và trace, nhưng phải tránh ghi toàn bộ payload nhạy cảm hoặc thông tin thẻ.

## 18. Khả năng quan sát và hợp đồng vận hành

Một API được dùng bởi các microservice cần làm rõ cách phát hiện lỗi và đo ảnh hưởng.

### 18.1. Những chỉ số hữu ích

| Nhóm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tính sẵn sàng | Tỉ lệ request thành công theo endpoint | API có đáp ứng hợp đồng trong thời gian đã hứa? |
| Độ trễ | p50, p95, p99 cho từng route/method | Có lỗi đuôi dài hoặc chờ downstream không? |
| Kết quả nghiệp vụ | Số reservation được tạo/từ chối | Phân biệt lỗi hệ thống và từ chối hợp lệ |
| Retry | Số 429/503, retry count, deadline exceeded | Chính sách retry có gây bão request không? |
| Idempotency | Request trùng, key conflict, kết quả replay | Có phòng chống thực thi lặp hiệu quả không? |
| Concurrency | Số 412, 409, tình huống lost update | Client có áp dụng If-Match phù hợp? |
| Cache | Hit/miss, 304, stale data incidents | Cache có giảm tải và không làm sai nghiệp vụ? |
| Consumer | API version usage, deprecated endpoint usage | Khi nào có thể gỡ đường cũ? |

Một tỷ lệ 409 cao có thể là lỗi nếu do concurrency bất thường, nhưng cũng có thể phản ánh khách cố giữ hàng đã hết. Cần gắn metric với ngữ nghĩa nghiệp vụ thay vì coi mọi 4xx là lỗi hệ thống.

### 18.2. Correlation và tracing

Mỗi request qua nhiều service nên có trace/correlation context xuyên suốt, sử dụng chuẩn tracing và hệ thống quan sát phù hợp. Có thể trả **traceId** trong error response để hỗ trợ tra cứu sự cố, nhưng không để client điều khiển tùy tiện các trường định danh hoặc làm lộ thông tin nhạy cảm.

Log cần cho phép trả lời: request nào, service nào, thời gian bao lâu, gọi downstream nào, lỗi giao thức hay lỗi nghiệp vụ, đã retry bao nhiêu lần và kết quả cuối cùng là gì.

## 19. Ví dụ thiết kế hoàn chỉnh: Order API

Giả sử Order Service sở hữu vòng đời đơn hàng, còn Inventory, Payment và Shipping sở hữu phần dữ liệu của mình. Các endpoint công khai của Order có thể gồm:

| Method | URI | Mục đích | Kết quả thường gặp |
| --- | --- | --- | --- |
| POST | /orders | Tạo yêu cầu đơn mới | 201 + Location, 422 nếu input không hợp lệ |
| GET | /orders/{id} | Lấy trạng thái đơn | 200, 304 hoặc 404 |
| GET | /orders | Tìm/lọc đơn được phép xem | 200 với pagination |
| PATCH | /draft-orders/{id} | Sửa trường cho phép của bản nháp | 200/204, 412 hoặc 409 |
| POST | /orders/{id}/cancellation-requests | Yêu cầu hủy đơn | 201 hoặc 202, 409 nếu trạng thái không cho phép |
| GET | /orders/{id}/cancellation-requests/{requestId} | Xem kết quả xử lý yêu cầu | 200 hoặc 404 |
| GET | /operations/{id} | Theo dõi công việc chưa hoàn tất | 200 với trạng thái operation |

### 19.1. Luồng tạo Order thành công

**Bước 1 — Client gửi POST với idempotency key:**

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/json
Idempotency-Key: checkout-CUS-001-cart-1001

{
  "customerId": "CUS-001",
  "items": [
    {
      "sku": "SKU-100",
      "quantity": 2
    }
  ],
  "shippingAddressId": "ADDR-22"
}
~~~

**Bước 2 — Order tạo nguồn sự thật của mình:**

~~~http
HTTP/1.1 201 Created
Location: /orders/ORD-1001
ETag: "order-1001-v1"
Content-Type: application/json

{
  "id": "ORD-1001",
  "status": "PENDING_STOCK",
  "createdAt": "2026-11-11T08:00:00Z"
}
~~~

Order chưa nên trả **CONFIRMED** nếu chưa có bằng chứng hoàn tất những điều kiện doanh nghiệp quy định. Khi đã khởi tạo một quy trình liên miền, trạng thái trung gian là thông tin có giá trị.

**Bước 3 — Client theo dõi bằng GET:**

~~~http
GET /orders/ORD-1001 HTTP/1.1
Accept: application/json
If-None-Match: "order-1001-v1"
~~~

Nếu Order cập nhật sau khi giữ hàng, server có thể trả 200 cùng ETag mới và trạng thái **PENDING_PAYMENT**. Nếu chưa thay đổi, có thể trả **304**.

### 19.2. Luồng thất bại nghiệp vụ

Giả sử Inventory từ chối vì không đủ hàng. Order cập nhật trạng thái phù hợp như **REJECTED_OUT_OF_STOCK** và GET Order vẫn trả **200 OK**, vì việc **đọc Order** thành công, dù **nghiệp vụ đặt hàng** đã thất bại. Client phải đọc trường trạng thái của Order, không hiểu 200 là mọi nghiệp vụ đã hoàn thành.

Nếu client gọi một endpoint yêu cầu xác nhận đơn khi chưa đủ điều kiện, endpoint có thể trả **409 Conflict** với Problem Details, vì request thao tác bị từ chối do trạng thái hiện tại.

### 19.3. Luồng lỗi hạ tầng

Nếu Order gửi yêu cầu giữ hàng nhưng Inventory timeout, Order không thể giả định reservation không tồn tại. Có thể ghi trạng thái **PENDING_STOCK_CHECK**, sử dụng request identity ổn định để retry hoặc tra cứu kết quả và có quy trình xử lý hết hạn. Chỉ trả **503/504** cho client nếu giao diện đồng bộ thực sự không thể đáp ứng và hợp đồng không hỗ trợ operation/resource trung gian.

### 19.4. Không đồng nhất hợp đồng public và internal

Public Order API có thể cần bảo vệ trải nghiệm client bằng representation ổn định. Internal Inventory API có thể tối ưu theo nghiệp vụ reserve/release và contract giữa đội. Cả hai vẫn nên tôn trọng HTTP method, status, idempotency và lỗi; không nhất thiết có cùng mô hình hoặc cùng đường dẫn.

## 20. Đặc tả REST API bằng OpenAPI

Tài liệu OpenAPI giúp producer và consumer thống nhất đường dẫn, method, tham số, schema, security, responses và ví dụ. Một đoạn minh họa đơn giản:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths:
  /orders/{orderId}:
    get:
      summary: Lay mot don hang
      parameters:
        - in: path
          name: orderId
          required: true
          schema:
            type: string
        - in: header
          name: If-None-Match
          required: false
          schema:
            type: string
      responses:
        '200':
          description: Order representation
          content:
            application/json:
              schema:
                type: object
                required: [id, status]
                properties:
                  id:
                    type: string
                  status:
                    type: string
        '304':
          description: Khong thay doi so voi ETag client
        '404':
          description: Khong tim thay don
~~~

Đây là fragment hướng dẫn cấu trúc, chưa phải đặc tả production đầy đủ. Khi triển khai thực tế cần bổ sung security scheme, status code cho từng trường hợp, schema validation, content type, error representation, caching, concurrency và policy tương thích.

### 20.1. Contract test và integration test

Kiểm thử có giá trị khi xác minh **ngữ nghĩa**, không chỉ rằng controller trả HTTP 200.

Ví dụ cần có:

1. GET không gây side effect nghiệp vụ.
2. POST tạo Order mới trả 201 và Location có thể GET.
3. Hai POST cùng idempotency key/cùng body không tạo hai Order.
4. Cùng key nhưng body khác bị xử lý theo quy tắc xung đột đã công bố.
5. PUT/PATCH với If-Match cũ trả 412 và dữ liệu mới không bị ghi đè.
6. DELETE lặp không tạo side effect thêm.
7. 204 và 304 không có representation body.
8. JSON không hợp lệ và media type không hỗ trợ trả status đúng quy ước.
9. 401/403/404 phân biệt và không tiết lộ dữ liệu xuyên tenant.
10. Consumer cũ vẫn đọc được các trường cần thiết sau một thay đổi tương thích.
11. Khi downstream timeout, retry không tạo thao tác nghiệp vụ trùng.
12. GET collection thực hiện pagination, filtering và authorization như đã công bố.

Với service-to-service API, contract tests kiểm tra producer/consumer và integration tests kiểm tra luồng thực giữa những thành phần cần thiết. Một bản OpenAPI được sinh ra từ code chưa chắc phát hiện sai lệch ý nghĩa khi một status chuyển từ “yêu cầu đã gửi” sang “giao dịch hoàn tất”, nên cần ví dụ nghiệp vụ và test các trạng thái quan trọng.

## 21. Các phản mẫu thường gặp

### 21.1. Dùng POST cho mọi endpoint

~~~text
POST /getOrders
POST /deleteOrder
POST /updateOrderStatus
~~~

Cách này đánh mất lợi ích ngữ nghĩa của GET, PUT, DELETE, cache và chuẩn retry. Nên dùng method/tài nguyên thích hợp, hoặc nếu là command có quy tắc phức tạp thì mô hình hóa request resource rõ ràng.

### 21.2. GET thực hiện thay đổi

~~~text
GET /orders/ORD-1001/cancel
GET /inventory/decrease?sku=SKU-100&quantity=2
~~~

Các endpoint như vậy không safe. Dùng POST/DELETE/PATCH tùy nghiệp vụ và bảo vệ idempotency, authorization.

### 21.3. Luôn trả 200, lỗi nằm trong body

~~~json
{
  "success": false,
  "errorCode": "UNAUTHORIZED"
}
~~~

HTTP 200 khiến client, gateway và observability nhận tín hiệu thành công. Nên trả **401/403** hoặc status phù hợp cùng Problem Details.

### 21.4. Mở API CRUD trực tiếp lên database

Công bố trường **paid = true** và cho consumer PATCH trực tiếp có thể vượt qua xác minh của Payment. API phải thực thi quy tắc nghiệp vụ, không cho consumer sửa tùy ý những field phản ánh sự thật quan trọng.

### 21.5. Dùng PUT như PATCH mà không công bố hợp đồng

Client gửi một vài field, server hiểu là cập nhật từng phần ở endpoint PUT; client khác gửi toàn bộ rồi xóa mất trường mới. Cần tách rõ semantics và định dạng để hỗ trợ tương thích.

### 21.6. Sửa tài nguyên không có điều kiện cập nhật

Hai request cạnh tranh có thể ghi đè nhau. Với tài nguyên có nguy cơ lost update, dùng ETag/If-Match hoặc cơ chế version phù hợp và bảo vệ trong transaction.

### 21.7. Retry POST thanh toán vô hạn

Timeout có thể xảy ra **sau khi tiền đã được thu**. Retry không khóa idempotency có thể thu hai lần. Cần có định danh attempt, idempotency, trạng thái tra cứu và reconciliation.

### 21.8. Expose entity nội bộ nguyên vẹn

Trả về toàn bộ object persistence làm API phụ thuộc cột DB, lộ dữ liệu nhạy cảm và khiến migration schema thành thay đổi contract. Nên dùng representation được thiết kế riêng cho consumer và nghiệp vụ.

### 21.9. Cache dữ liệu sai quyền hoặc sai độ mới

Giá riêng cho khách/tenant nhưng trả **Cache-Control: public** có nguy cơ rò rỉ. Kiểm tra phân quyền và độ mới yêu cầu trước khi chọn cache.

### 21.10. Không xác định vòng đời resource

Một request được tạo nhưng không có URI để theo dõi, không có trạng thái hoàn thành hay cơ chế hết hạn khiến client không thể phân biệt “đang chạy”, “đã thất bại” và “không tồn tại”. Nên đưa operation hoặc request resource vào hợp đồng nếu xử lý mất thời gian.

## 22. Quy trình thiết kế một REST API mới

Một quy trình có thể thực hiện theo thứ tự sau:

**Bước 1 — Chọn năng lực và chủ sở hữu.** Xác định bounded context nào chịu trách nhiệm cho trạng thái và quy tắc. API cần bảo vệ nguồn sự thật của context.

**Bước 2 — Xác định resource.** Liệt kê những đối tượng có danh tính, vòng đời và giá trị quan sát từ bên ngoài. Tách các tài nguyên nghiệp vụ khỏi bảng dữ liệu kỹ thuật.

**Bước 3 — Mô tả trạng thái và invariant.** Viết điều kiện cho mỗi chuyển trạng thái, ai có quyền thực hiện, cách xử lý thất bại và tình huống đồng thời.

**Bước 4 — Thiết kế URI và method.** Dùng collection/item URI nhất quán; chọn GET, POST, PUT, PATCH, DELETE theo ý định và ngữ nghĩa chuẩn.

**Bước 5 — Định nghĩa response.** Chọn 200/201/202/204 và Location phù hợp; mô tả JSON, header và điều kiện không có body.

**Bước 6 — Định nghĩa lỗi.** Ghi rõ 400/401/403/404/409/412/422/429/5xx khi thích hợp, payload Problem Details và mã lỗi ứng dụng.

**Bước 7 — Xử lý mạng và đồng thời.** Xác định timeout, retry, idempotency key, ETag, If-Match, concurrency và operation resource cho luồng dài.

**Bước 8 — Thiết kế collection và cache.** Phân trang, lọc, sort, giới hạn kích thước, quyền truy cập, ETag/Cache-Control khi an toàn.

**Bước 9 — Đặc tả và kiểm thử hợp đồng.** Cung cấp OpenAPI, ví dụ thành công/thất bại và contract/integration tests dựa trên nghĩa nghiệp vụ.

**Bước 10 — Quản lý phiên bản.** Xác định khả năng tương thích, thời gian deprecation, consumer inventory và cách quan sát các endpoint cũ.

Việc thiết kế API nên diễn ra với cả **người hiểu nghiệp vụ và người sẽ tiêu thụ API**. Tính rõ ràng của hợp đồng quan trọng hơn sở thích đặt tên của một nhóm riêng lẻ.

## 23. Bài tập thực hành

Giả sử cần thiết kế API cho một **Inventory Reservation Service** trong hệ thống bán hàng. Service có trách nhiệm giữ một lượng hàng trong thời hạn hữu hạn. Order Service là consumer. Một reservation có ID, mã đơn, danh sách SKU/số lượng, thời hạn và trạng thái **PENDING**, **RESERVED**, **REJECTED**, **EXPIRED** hoặc **RELEASED** tùy mô hình đã xác minh.

### Yêu cầu A — Tài nguyên và URI

Thiết kế endpoint để tạo reservation, xem reservation, liệt kê reservation theo orderId và yêu cầu giải phóng reservation. Giải thích khi nào DELETE hợp lý và khi nào cần một resource **release request** có trạng thái riêng.

### Yêu cầu B — HTTP method và status

Với từng endpoint, chọn method, success status, lỗi validation, hết hàng, không có quyền, không tìm thấy và lỗi phụ thuộc. Giải thích tại sao **409** có thể khác **412**, và tại sao timeout không đồng nghĩa reservation chưa được tạo.

### Yêu cầu C — Idempotency và concurrency

Mô tả cách hai request tạo reservation cùng ID nghiệp vụ được xử lý; cách bảo vệ không giữ quá tồn kho; cách ngăn hai request đồng thời làm sai invariant; và điều gì xảy ra khi cùng idempotency key gửi payload khác.

### Yêu cầu D — Contract

Viết một request/response JSON và một Problem Details cho tình huống từ chối giữ hàng. Ghi ETag hoặc version nếu có cập nhật phù hợp. Nêu trường nào thuộc source of truth Inventory và trường nào chỉ là tham chiếu từ Order.

### Yêu cầu E — Vận hành

Đề xuất timeout, giới hạn retry, cách tra cứu request bị timeout, tracing và ba metric để biết hệ thống xử lý đúng. Bổ sung tình huống release request đến lặp sau khi reservation đã hết hạn.

Một phương án đạt yêu cầu khi consumer có thể **dự đoán hành vi HTTP, hiểu trạng thái nghiệp vụ, xử lý retry an toàn và không cần truy cập database nội bộ của Inventory**.

## 24. Ghi nhớ

- **URI định danh tài nguyên; HTTP method diễn đạt ý định thao tác.** Không dùng route như tên hàm RPC một cách tùy tiện khi ngữ nghĩa tài nguyên có thể diễn đạt rõ.
- **GET/HEAD/OPTIONS là safe; GET, PUT, DELETE có ngữ nghĩa idempotent; POST/PATCH không mặc định idempotent.** Một API nghiệp vụ có thể bổ sung idempotency key để bảo vệ thao tác quan trọng trước retry.
- **Status HTTP là một phần của contract.** 201 cho tài nguyên mới, 202 cho xử lý đang chờ, 204 cho thành công không body, 409 cho xung đột trạng thái, 412 cho precondition thất bại.
- **ETag/If-Match** giúp tránh lost update; cache validator giúp tránh truyền representation không đổi, nhưng không thay quy tắc nghiệp vụ.
- **Problem Details** giúp client phân biệt lỗi có cấu trúc, còn trace/correlation hỗ trợ truy nguyên lỗi qua nhiều service.
- **Phân trang, cache, versioning và bảo mật** phải được thiết kế từ đầu theo mức độ cần thiết; tránh để các chi tiết này trở thành hành vi bất ngờ.
- Trong Microservices, **REST API phải bảo vệ quyền sở hữu nghiệp vụ và dữ liệu**: service tiêu thụ sử dụng hợp đồng công bố, không sửa trực tiếp trạng thái nội bộ của service khác.
- Một hợp đồng tốt cho phép các phiên bản producer/consumer phối hợp an toàn trước mạng không đáng tin tuyệt đối, đặc biệt ở các thao tác gây side effect như đặt hàng, giữ hàng và thanh toán.

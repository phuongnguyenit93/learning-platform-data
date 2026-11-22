# HATEOAS và vai trò của liên kết trong luồng sử dụng API

Hãy hình dung một ứng dụng khách vừa tạo đơn hàng thành công. Đơn ở trạng thái **AWAITING_PAYMENT** (chờ thanh toán), nên người dùng có thể thanh toán hoặc hủy. Sau khi thanh toán, hành động thanh toán không còn phù hợp; thay vào đó, người dùng có thể xem vận chuyển, hóa đơn hoặc yêu cầu hỗ trợ. Nếu client tự ghép tất cả URL từ một danh sách endpoint cố định rồi đoán hành động dựa trên chuỗi trạng thái, mỗi thay đổi quy trình ở server có thể buộc nhiều phiên bản web/mobile phải sửa theo.

**HATEOAS** (*Hypermedia as the Engine of Application State*) đề xuất hướng tiếp cận khác: **response hiện tại mang những liên kết và/hoặc điều khiển hypermedia giúp client tìm bước tiếp theo**. Client biết mình đang ở đâu, có thể đi đến đâu và tìm cách thực hiện hành động phù hợp dựa trên thông tin máy đọc được trong biểu diễn. Server giữ quyền quyết định chuyển trạng thái nghiệp vụ, còn client tuân thủ hợp đồng về **link relation, media type, phương thức và dữ liệu đầu vào**.

Bài học này thuộc chương **Hypermedia** của module **INTEGRATION_API_REST**. Trọng tâm là thiết kế REST API theo tài nguyên, URI, phương thức và trạng thái HTTP, với ví dụ Java/Spring, hợp đồng dữ liệu, phân trang, cache, phân quyền, OpenAPI và kiểm thử luồng API. Ta sẽ phân biệt **có URL trong JSON** với **thực sự dùng hypermedia để điều hướng trạng thái**, sau đó thiết kế và kiểm chứng một luồng đặt hàng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **hypermedia**, **HATEOAS**, **application state**, **resource state**, **link relation** và **affordance** bằng ví dụ REST.
2. Phân biệt link chỉ để tham chiếu với link/hành động giúp client chuyển giữa các trạng thái ứng dụng.
3. Đọc và thiết kế biểu diễn có **self**, **collection**, **next**, **prev** và các relation nghiệp vụ riêng.
4. Phân biệt khả năng **khám phá liên kết** với khả năng **khám phá method, content type và mẫu payload**.
5. Tạo response hypermedia trong Spring với **Spring HATEOAS**, giữ đúng HTTP status, ETag và kiểm soát quyền.
6. Thiết kế client đi theo relation thay vì tự xây URI; kiểm thử biến thể trạng thái, bảo mật, caching và tương thích.

## 2. HATEOAS là gì trong mô hình REST?

Trong kiến trúc REST, **hypermedia** là một ràng buộc: các tương tác của client có thể được dẫn dắt bởi **biểu diễn tài nguyên mang các điều khiển chuyển trạng thái**, cùng với những quy tắc chung của media type và HTTP. Nói ngắn gọn, khi client nhận một tài nguyên, biểu diễn đó có thể cung cấp **các lựa chọn tiếp theo** để người dùng/ứng dụng thực hiện.

Một trình duyệt web là ví dụ quen thuộc: người dùng mở trang chủ, theo liên kết đến danh mục, đi tiếp tới chi tiết sản phẩm, rồi gửi form. Họ không cần biết toàn bộ đường dẫn nội bộ của website trước khi bắt đầu. API hypermedia áp dụng cùng nguyên tắc cho client phần mềm.

### 2.1. Bốn khái niệm thường bị trộn lẫn

| Khái niệm | Ý nghĩa | Ví dụ đơn hàng |
|---|---|---|
| **Resource** | Một khái niệm có định danh được truy cập qua HTTP | Đơn hàng o-918 |
| **Resource state** | Trạng thái được biểu diễn tại một thời điểm | status = AWAITING_PAYMENT |
| **Application state** | Vị trí/bước hiện tại trong tương tác của client với ứng dụng | Client đang xem đơn, muốn thanh toán |
| **Hypermedia control** | Thông tin máy đọc được giúp client xác định lựa chọn tiếp theo | Relation dẫn tới endpoint tạo payment intent |

**Resource state** không đồng nghĩa **application state**. Resource có thể chuyển từ chờ thanh toán sang đã thanh toán; client cũng có thể đang ở màn hình giỏ hàng, chi tiết đơn hoặc theo dõi vận chuyển. HATEOAS tập trung vào cách client **đi qua luồng tương tác**, không chỉ cách lưu trạng thái trong database.

### 2.2. Không phải cứ có URL là HATEOAS

Một payload đơn giản:

~~~json
{
  "id": "o-918",
  "status": "AWAITING_PAYMENT",
  "paymentUrl": "/v1/orders/o-918/payment-intents"
}
~~~

Payload có URL, nhưng client còn phải đoán **paymentUrl nghĩa là gì**, dùng GET hay POST, có được gọi khi đã thanh toán không, và schema dữ liệu đầu vào ở đâu. Tài liệu trường có thể làm rõ những điều đó; tuy nhiên, một thuộc tính URL tùy ý chưa tạo thành **hợp đồng hypermedia có relation và ngữ nghĩa điều hướng được thống nhất**.

Biểu diễn có quan hệ tường minh hơn:

~~~json
{
  "id": "o-918",
  "status": "AWAITING_PAYMENT",
  "_links": {
    "self": {
      "href": "/v1/orders/o-918"
    },
    "collection": {
      "href": "/v1/orders"
    },
    "https://api.example.test/rels/create-payment": {
      "href": "/v1/orders/o-918/payment-intents"
    }
  }
}
~~~

Đây là cách biểu diễn kiểu **HAL**. Tên relation được đặt trong **_links**; các relation như **self**, **collection** có ý nghĩa được công nhận trong hệ sinh thái liên kết, còn URI **https://api.example.test/rels/create-payment** định danh một **relation nghiệp vụ do API định nghĩa**. Trong ví dụ, tài liệu của relation đó quy định client dùng **POST** để tạo payment intent; HAL link **tự nó chỉ cho biết relation và href**, chưa mô tả toàn bộ method/payload.

**Bài học cốt lõi:** HATEOAS không yêu cầu server bỏ hết tài liệu API hoặc client không hiểu bất kỳ quy tắc nào. Nó yêu cầu client dựa vào **điều khiển được cung cấp ở trạng thái hiện tại** thay vì mã hóa cứng mọi đường đi và chuyển trạng thái thành những URI phỏng đoán.

## 3. Các thành phần của một hypermedia control

### 3.1. Target URI: đi tới đâu?

**Target URI** xác định đích của một link. Client nên coi giá trị này là **opaque**: dùng URI server đã công bố, không tách chuỗi để suy ra cấu trúc hoặc tự thay đoạn path.

~~~json
{
  "_links": {
    "self": {"href": "/v1/orders/o-918"},
    "next": {"href": "/v1/orders?cursor=eyJvZmZzZXQiOjIwfQ"}
  }
}
~~~

Server có thể chuyển từ path **/v1/orders/o-918** sang **/v2/purchases/918**, thay host hoặc thay kiểu pagination mà client đi theo link vẫn ít phụ thuộc vào quy ước đường dẫn hơn. Điều này **không miễn trừ trách nhiệm giữ tương thích của toàn contract**: method, representation, quyền và ý nghĩa relation vẫn phải được quản lý.

### 3.2. Link relation: vì sao đi theo link?

**Link relation (rel)** mô tả quan hệ giữa ngữ cảnh hiện tại và tài nguyên đích. Client nên tìm theo relation, không theo vị trí phần tử trong mảng hay chuỗi cố định ở cuối URI.

| Relation | Ý nghĩa thường gặp | Cách dùng |
|---|---|---|
| **self** | Định danh biểu diễn/ngữ cảnh tài nguyên hiện tại | Làm mới hoặc tham chiếu lại tài nguyên |
| **collection** | Tập hợp mà tài nguyên thuộc về | Quay về danh sách |
| **item** | Một mục thuộc collection | Đi từ danh sách đến chi tiết |
| **next** | Trang hoặc phần tiếp theo của một chuỗi | Phân trang |
| **prev** | Trang/phần trước đó | Phân trang ngược |
| **describedby** | Tài nguyên mô tả ngữ nghĩa/đặc tả liên quan | Tìm tài liệu bổ sung |
| **Relation nghiệp vụ** | Hành động/chuyển trạng thái cụ thể | Thanh toán, yêu cầu hủy, tải hóa đơn |

Một số relation phổ biến được đăng ký trong **IANA Link Relations registry** và được chuẩn hóa qua **RFC 8288 (Web Linking)**. Các relation riêng nên có **định danh và tài liệu ổn định**. Trong HAL có thể dùng **extension relation URI** hoặc **CURIE** để đặt tên gọn, thay vì coi mọi chuỗi tùy ý là relation chuẩn.

Ví dụ hai relation riêng:

~~~text
https://api.example.test/rels/create-payment
https://api.example.test/rels/request-cancellation
~~~

Hợp đồng cần nêu rõ: relation xuất hiện trong hoàn cảnh nào, resource đích là gì, phương thức nào được dùng, media type, schema đầu vào, điều kiện, idempotency và các response hợp lệ.

### 3.3. Affordance: có thể làm gì và bằng cách nào?

Một **affordance** mô tả khả năng tương tác, có thể gồm method, input fields, content type hoặc các ràng buộc. Trong một tài liệu HTML, **form** có action, method và các trường. Trong API, mức độ affordance phụ thuộc **media type** và phần mở rộng được chọn.

**HAL** chủ yếu biểu diễn link và resource embedding; nó **không chuẩn hóa đầy đủ** một cách diễn tả form action/payload cho mọi thao tác ghi. **Siren** có khái niệm actions cho method, href, type và fields; **JSON:API** chuẩn hóa hệ thống links/relationships nhưng không tự giải quyết mọi form/action nghiệp vụ. Các định dạng khác cũng có thể có khả năng biểu đạt khác nhau.

Vì thế, hai câu khẳng định sau **khác nhau**:

- “Response có link relation dẫn tới nơi có thể tạo payment intent.”
- “Response mô tả đầy đủ POST, Content-Type, các trường hợp lệ và điều kiện thực thi để client tự gửi action.”

Đối với HAL, câu thứ hai thường cần **OpenAPI/tài liệu relation** hoặc một cơ chế affordance bổ sung. Không nên dạy client cứ thấy link thì tự động GET, nhất là relation liên quan đến xóa, thanh toán hoặc tác động bên ngoài.

### 3.4. Entry point và discoverability

Client cần có một **điểm khởi đầu** được công bố (entry point) cùng hiểu biết về media type, authentication và relation đã biết. Ví dụ:

~~~http
GET /v1 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Cache-Control: private, no-store

{
  "_links": {
    "self": {"href": "/v1"},
    "https://api.example.test/rels/orders": {"href": "/v1/orders"},
    "https://api.example.test/rels/catalog": {"href": "/v1/products"}
  }
}
~~~

Client bắt đầu ở **/v1**, tìm relation cần thiết rồi **theo href trả về**. Trong hệ thống thực tế, entry point, authorization policy và những relation quan trọng vẫn cần được tài liệu hóa để client biết nơi bắt đầu và ý nghĩa của từng lựa chọn.

## 4. Luồng sử dụng API: từ đơn hàng tới bước tiếp theo

Xét nghiệp vụ:

1. Người dùng đặt hàng.
2. Đơn được chấp nhận, đang chờ thanh toán.
3. Sau khi thanh toán, đơn có thể chuyển sang xử lý/giao hàng.
4. Khi đủ điều kiện, người dùng có thể yêu cầu hủy hoặc tải hóa đơn.
5. Sau khi hoàn tất, những hành động không hợp lệ sẽ không còn được công bố như affordance ở trạng thái hiện tại.

### 4.1. Sơ đồ trạng thái minh họa

~~~mermaid
stateDiagram-v2
    [*] --> AWAITING_PAYMENT: POST /orders
    AWAITING_PAYMENT --> PAYMENT_PROCESSING: Tạo payment intent
    AWAITING_PAYMENT --> CANCELLED: Yêu cầu hủy được chấp thuận
    PAYMENT_PROCESSING --> PAID: PSP xác nhận thanh toán
    PAYMENT_PROCESSING --> PAYMENT_FAILED: PSP xác nhận thất bại
    PAYMENT_FAILED --> AWAITING_PAYMENT: Tạo lần thanh toán mới hợp lệ
    PAID --> FULFILLING: Bắt đầu xử lý
    PAID --> CANCELLED: Hủy/hoàn tiền theo quy tắc
    FULFILLING --> COMPLETED: Đã giao/nhận
    COMPLETED --> [*]
    CANCELLED --> [*]
~~~

Sơ đồ này chỉ minh họa **một** quy trình, chưa thể hiện tất cả chi tiết như reservation tồn kho, thu/hoàn tiền và trạng thái phân tán. Một thao tác “yêu cầu hủy” có thể tạo tài nguyên **cancellation request** trước khi đơn thật sự **CANCELLED**; không được đồng nhất việc gửi request với việc đã hoàn tất hủy.

### 4.2. Sau khi tạo đơn

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/hal+json
Idempotency-Key: checkout-71

{
  "cartId": "cart-71",
  "deliveryMethod": "pickup"
}
~~~

~~~http
HTTP/1.1 201 Created
Location: /v1/orders/o-918
Content-Type: application/hal+json
ETag: "order-v1"
Cache-Control: private, no-store

{
  "id": "o-918",
  "status": "AWAITING_PAYMENT",
  "total": {"amount": 359000, "currency": "VND"},
  "_links": {
    "self": {"href": "/v1/orders/o-918"},
    "collection": {"href": "/v1/orders"},
    "https://api.example.test/rels/create-payment": {
      "href": "/v1/orders/o-918/payment-intents"
    },
    "https://api.example.test/rels/request-cancellation": {
      "href": "/v1/orders/o-918/cancellation-requests"
    }
  }
}
~~~

**Location** xác định URI của đơn vừa tạo, còn **self** làm rõ định danh đó bên trong biểu diễn. Các relation khác cho client biết **những hướng tiếp tục phù hợp tại thời điểm trả response**. Phương thức để tạo payment intent và cancellation request ở ví dụ này đều là **POST**, được quy định trong hợp đồng relation/API; không suy ra từ phần đuôi URI.

**Idempotency-Key** là hợp đồng cấp ứng dụng giúp xử lý retry POST; việc gửi header này **không tự biến** mọi POST thành idempotent. Server phải quy định phạm vi key, TTL, payload fingerprint và phản hồi khi dùng lại key khác dữ liệu.

### 4.3. Client theo relation để tạo payment intent

Client đọc relation **https://api.example.test/rels/create-payment** từ **_links**, sau đó gửi POST theo schema được công bố:

~~~http
POST /v1/orders/o-918/payment-intents HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json
Idempotency-Key: pay-918-attempt-1

{"provider":"supported-psp"}
~~~

Server có thể trả:

~~~http
HTTP/1.1 201 Created
Location: /v1/payment-intents/pi-501
Content-Type: application/json

{
  "id": "pi-501",
  "status": "PENDING",
  "orderId": "o-918"
}
~~~

Trong một triển khai hoàn chỉnh, payment intent có thể trả URL checkout của đối tác, expiration và trạng thái cần thiết. Client **không xem việc tạo payment intent là bằng chứng đã thanh toán**; phải dựa trên trạng thái đáng tin cậy của hệ thống và PSP.

### 4.4. Response sau khi trạng thái đổi

Sau khi hệ thống đã xác nhận đơn **PAID**, GET cùng URI có thể trả:

~~~http
GET /v1/orders/o-918 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "order-v3"
Cache-Control: private, no-store

{
  "id": "o-918",
  "status": "PAID",
  "total": {"amount": 359000, "currency": "VND"},
  "_links": {
    "self": {"href": "/v1/orders/o-918"},
    "collection": {"href": "/v1/orders"},
    "https://api.example.test/rels/receipt": {
      "href": "/v1/orders/o-918/receipts/r-100"
    },
    "https://api.example.test/rels/shipment": {
      "href": "/v1/orders/o-918/shipment"
    }
  }
}
~~~

Relation **create-payment** biến mất vì không còn phù hợp; relation **receipt/shipment** xuất hiện theo trạng thái và quyền hiện tại. Client có thể **khám phá bước tiếp theo từ response**, thay vì viết quy tắc cố định dạng “nếu status là PAID thì tự tạo URI shipment”.

**Lưu ý bảo mật:** link vắng mặt **không thay thế kiểm tra quyền và validation phía server**. Người dùng có thể giữ URI cũ, sửa request, chạy nhiều client đồng thời hoặc nhận link trước khi trạng thái đổi. Mọi POST/DELETE vẫn phải kiểm tra xác thực, phân quyền, trạng thái thực tế và điều kiện cạnh tranh khi thực thi.

### 4.5. Quy trình nhìn từ client

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Client
    participant A as Orders API
    participant P as Payment Adapter
    U->>C: Đặt hàng
    C->>A: POST /orders
    A-->>C: 201 + Location + self/create-payment/cancel links
    C->>A: GET self link
    A-->>C: AWAITING_PAYMENT + create-payment rel
    U->>C: Chọn thanh toán
    C->>A: POST vào href của create-payment rel
    A->>P: Tạo payment intent
    P-->>A: Payment reference
    A-->>C: 201 payment intent
    Note over A,P: Xác nhận thanh toán qua luồng tin cậy riêng
    C->>A: GET self để làm mới
    A-->>C: PAID + receipt/shipment links
    C-->>U: Hiển thị bước tiếp theo
~~~

Điểm đáng chú ý là client đi theo **rel và href đã nhận**, chứ không tự ghép URL. Tuy vậy, client vẫn cần hiểu **cách thực thi action** từ hợp đồng relation, media type và API. Nếu muốn method/form được truyền trực tiếp trong response, hãy chọn hoặc mở rộng media type có khả năng biểu đạt affordance phù hợp.

## 5. Khi nào link được hiển thị, khi nào phải ẩn?

**Link availability** là cách server phát tín hiệu về các lựa chọn hiện có. Trong ứng dụng thực tế, nó thường phụ thuộc vào:

| Điều kiện | Ví dụ | Ảnh hưởng đến response |
|---|---|---|
| **Trạng thái tài nguyên** | AWAITING_PAYMENT, PAID, CANCELLED | Chỉ công bố action tương ứng |
| **Quyền của người gọi** | Chủ đơn, nhân viên cửa hàng, tài khoản khách | Người gọi khác nhau nhìn thấy link khác nhau |
| **Quy tắc nghiệp vụ** | Đã quá hạn hủy, hàng đang vận chuyển | Có thể không có relation request-cancellation |
| **Tình trạng hệ thống** | Đối tác thanh toán đang bảo trì | Có thể tạm ẩn affordance hoặc trả lỗi phù hợp |
| **Tính năng và phiên bản** | Feature flag/đối tác chưa hỗ trợ | Không công bố affordance không thực hiện được |

Hai biểu diễn cùng một resource có thể khác bộ liên kết khi người dùng khác quyền hoặc trạng thái khác nhau. Do vậy, response có link theo quyền truy cập cần áp dụng **authorization**, **cache policy** và **Vary** nếu những header cụ thể ảnh hưởng nội dung. Không để shared cache vô tình trả bộ affordance của quản trị viên cho một người dùng khác.

### 5.1. Có link không có nghĩa chắc chắn thao tác thành công

Giữa lúc client nhận link và lúc gửi action, trạng thái có thể đổi:

~~~text
10:00:00  GET /orders/o-918 -> có request-cancellation
10:00:02  Nhân viên chuyển đơn sang FULFILLING
10:00:03  Client POST cancellation request theo link cũ
10:00:03  Server kiểm tra lại -> từ chối theo chính sách hiện tại
~~~

Đây là một tình huống **time-of-check/time-of-use** thông thường. Server phải xác minh trạng thái khi thực thi, có thể trả **409 Conflict**, **412 Precondition Failed** nếu đang dùng HTTP conditional request, hoặc phản hồi nghiệp vụ phù hợp. Client cần làm mới **self** và render lại affordance.

Nếu server cấp **ETag**, client có thể dùng **If-Match** trong một hành động điều kiện khi hợp đồng quy định:

~~~http
POST /v1/orders/o-918/cancellation-requests HTTP/1.1
Host: api.example.test
Content-Type: application/json
If-Match: "order-v1"
Idempotency-Key: cancel-o-918-01

{"reason":"CUSTOMER_CHANGED_MIND"}
~~~

Nếu API dùng If-Match để so phiên bản đơn, thao tác kiểm tra điều kiện và tạo yêu cầu hủy phải được thực hiện **nguyên tử hoặc có cơ chế chống race tương đương**; gửi If-Match tự nó không bảo đảm consistency. Với một endpoint tạo subresource, cần công bố rõ validator trong If-Match là **phiên bản của resource nào** và cách server áp dụng; không mặc định mọi client/server hiểu cùng một precondition cho resource đích khác URI.

### 5.2. Vắng link không phải bằng chứng bị từ chối tuyệt đối

Không xuất hiện relation có thể do:

- Người dùng không có quyền.
- Trạng thái không cho phép.
- Server không hỗ trợ tính năng.
- Phiên bản biểu diễn không công bố relation đó.
- Lỗi tạm thời hoặc ứng dụng chưa có dữ liệu để quyết định.

Client nên **không hiển thị hành động** khi không có affordance cần thiết, nhưng server vẫn phải kiểm tra quyền mỗi lần request. Đừng thiết kế bảo mật dựa vào việc “client không biết URI”.

### 5.3. Client nên phản ứng thế nào với relation chưa biết?

Theo hướng phát triển mở rộng, client cần **bỏ qua relation không nhận diện được** và tiếp tục xử lý những relation đã hiểu. Không nên crash vì server thêm link **https://api.example.test/rels/return-policy**. Ngược lại, nếu một affordance là bắt buộc cho hành trình nghiệp vụ và bị thiếu, client cần thông báo trạng thái không thể tiếp tục hoặc dẫn người dùng đến con đường xử lý hợp lệ đã được thiết kế.

## 6. Các cách biểu diễn hypermedia phổ biến

Không tồn tại một JSON key tên **links** hoặc **_links** có ý nghĩa HTTP phổ quát cho mọi API. Muốn client biết cách đọc hypermedia, server phải chọn hoặc công bố **media type và quy tắc biểu diễn**.

### 6.1. HAL: liên kết và tài nguyên nhúng

**HAL (Hypertext Application Language)**, thường đi với media type **application/hal+json**, sử dụng hai thành phần quan trọng:

- **_links:** map từ relation đến một link hoặc danh sách link. Link thường có **href**, có thể có **templated**, title, type, profile… tùy đặc tả.
- **_embedded:** các tài nguyên liên quan được nhúng trong biểu diễn, thuận tiện khi client cần đọc danh sách mà không phải gửi thêm request cho từng item.

Ví dụ collection:

~~~json
{
  "count": 2,
  "_links": {
    "self": {"href": "/v1/orders?limit=2"},
    "next": {"href": "/v1/orders?limit=2&cursor=eyJpZCI6Im8tOTE4In0"}
  },
  "_embedded": {
    "orders": [
      {
        "id": "o-917",
        "status": "PAID",
        "_links": {
          "self": {"href": "/v1/orders/o-917"}
        }
      },
      {
        "id": "o-918",
        "status": "AWAITING_PAYMENT",
        "_links": {
          "self": {"href": "/v1/orders/o-918"}
        }
      }
    ]
  }
}
~~~

Khóa **orders** bên trong _embedded ở ví dụ này là quy ước của API và cần được tài liệu hóa; không phải một tên bắt buộc trong mọi tài liệu HAL. HAL giúp client khám phá **tài nguyên và liên kết**; nếu cần form/action ghi dữ liệu có đầy đủ method và field, cần thêm hợp đồng khác.

### 6.2. JSON:API

**JSON:API** có mô hình **data, attributes, relationships, links, included** và media type **application/vnd.api+json**. Nó giúp biểu diễn mối quan hệ giữa resource, phân trang và tài nguyên liên quan một cách nhất quán.

~~~json
{
  "data": {
    "type": "orders",
    "id": "o-918",
    "attributes": {
      "status": "AWAITING_PAYMENT"
    },
    "links": {
      "self": "/v1/orders/o-918"
    },
    "relationships": {
      "customer": {
        "links": {
          "related": "/v1/orders/o-918/customer"
        }
      }
    }
  }
}
~~~

Đây là biểu diễn rút gọn theo phong cách JSON:API. Tài liệu thực tế phải tuân thủ phiên bản spec đã chọn, bao gồm quy tắc media type, thành phần resource và error format. **Không trộn tùy ý** _links của HAL vào payload JSON:API rồi vẫn gọi đó là JSON:API chuẩn.

### 6.3. Siren và action metadata

**Siren** sử dụng các thành phần như entities, links và **actions**. Ví dụ đơn giản cho hành động thanh toán:

~~~json
{
  "class": ["order"],
  "properties": {
    "id": "o-918",
    "status": "AWAITING_PAYMENT"
  },
  "links": [
    {"rel": ["self"], "href": "/v1/orders/o-918"}
  ],
  "actions": [
    {
      "name": "create-payment",
      "title": "Create payment intent",
      "method": "POST",
      "href": "/v1/orders/o-918/payment-intents",
      "type": "application/json",
      "fields": [
        {"name": "provider", "type": "text", "value": "supported-psp"}
      ]
    }
  ]
}
~~~

Điểm khác biệt đáng chú ý: action có thể chỉ ra **POST, href, kiểu nội dung và các field** ngay trong representation. Dù vậy, client vẫn cần hiểu ngữ nghĩa của action, điều kiện bảo mật và kết quả có thể xảy ra. Không được tự động thực hiện hành động gây thay đổi trạng thái chỉ vì server gửi về một action.

### 6.4. HTTP Link header

Hypermedia không nhất thiết nằm trong JSON body. HTTP có **Link header** theo **RFC 8288**, ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Link: </v1/orders/o-918>; rel="self"
Link: </v1/orders>; rel="collection"

{"id":"o-918","status":"AWAITING_PAYMENT"}
~~~

Một HTTP response có thể có nhiều giá trị Link. Link header đặc biệt hữu ích khi response body không phải JSON hypermedia, ví dụ một tài liệu PDF hoặc tải file, và muốn dẫn tới metadata/hướng dẫn. Tuy nhiên, **Link header vẫn không tự mô tả payload của POST**.

Trong thiết kế thật, cần quyết định link được thể hiện ở header, body hay cả hai; tránh phát sinh hai bộ quan hệ không nhất quán. Kiểm tra proxy/CDN có giữ và chuyển tiếp Link header theo contract không.

### 6.5. So sánh khi lựa chọn

| Biểu diễn | Thế mạnh | Giới hạn/điểm cần cân nhắc |
|---|---|---|
| **HAL** | Nhẹ, phổ biến trong ví dụ Spring HATEOAS; links và embedded rõ | Link không tự định nghĩa đầy đủ action method/schema |
| **JSON:API** | Quy ước rõ cho resource, relationships, included và pagination | Cần tuân thủ spec; action nghiệp vụ tùy biến cần giải pháp phù hợp |
| **Siren** | Mô tả action có method, type và fields | Client/tooling cần hiểu Siren; cân nhắc độ phức tạp |
| **HTTP Link header** | Dùng được với nhiều kiểu response, không cần thay body | Khó mô tả state/action phức tạp chỉ bằng link |
| **JSON tự định nghĩa** | Tùy biến được theo sản phẩm | Phải tự chuẩn hóa relation, URI/template, hành vi và client tooling |

**Chọn media type theo use case và khả năng client**, không theo số lượng trường có vẻ hấp dẫn. Nếu một API đã có khách hàng dùng JSON thuần, việc đổi sang HAL/JSON:API có thể là breaking change và cần hỗ trợ content negotiation/versioning có kiểm soát.

## 7. Hypermedia trong phân trang và truy vấn tài nguyên

Phân trang là tình huống HATEOAS phát huy lợi ích rõ ràng: **client không cần hiểu cách server tính trang tiếp theo**.

### 7.1. Theo next/prev thay vì tự tăng offset

Một endpoint:

~~~http
GET /v1/orders?status=PAID&limit=2 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
~~~

Có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Cache-Control: private, no-store

{
  "_links": {
    "self": {
      "href": "/v1/orders?status=PAID&limit=2"
    },
    "next": {
      "href": "/v1/orders?status=PAID&limit=2&cursor=c-991"
    }
  },
  "_embedded": {
    "orders": [
      {"id":"o-915","_links":{"self":{"href":"/v1/orders/o-915"}}},
      {"id":"o-916","_links":{"self":{"href":"/v1/orders/o-916"}}}
    ]
  }
}
~~~

Client lấy **next.href** làm URI tiếp theo và dừng khi không còn relation next, theo hợp đồng pagination. Nó không tự tính **page + 1**, không giả định cursor có thể giải mã, và không bỏ bộ lọc **status=PAID** khi theo link mới.

Cursor có thể mã hóa **thứ tự ổn định, điểm tiếp tục hoặc trạng thái truy vấn**. Dù dùng hypermedia, server vẫn phải định nghĩa tính nhất quán của pagination khi dữ liệu thay đổi (ví dụ keyset pagination), tránh trùng/bỏ sót và bảo vệ cursor khỏi chỉnh sửa trái phép nếu nó mang thông tin nhạy cảm.

### 7.2. URI template và placeholder

Một số hypermedia format hỗ trợ **URI template**, ví dụ:

~~~json
{
  "_links": {
    "https://api.example.test/rels/find-orders": {
      "href": "/v1/orders{?status,limit,cursor}",
      "templated": true
    }
  }
}
~~~

Client dùng bộ xử lý URI template phù hợp chuẩn **RFC 6570** để chèn tham số hợp lệ; **không ghép chuỗi tùy tiện** khi giá trị có khoảng trắng, ký tự đặc biệt hoặc dấu &. Server cần công bố các tham số, kiểu, giới hạn và hành vi mặc định. Nếu client chưa hỗ trợ URI template thì không thể giả định nó sẽ đi theo template như một URL thông thường.

### 7.3. Phân biệt next link với số trang

Trong một hệ thống dữ liệu liên tục có bản ghi mới, **trang số 3** không nhất thiết có cùng nội dung qua thời gian. Link next cho server quyền duy trì một cơ chế tiếp tục thích hợp như cursor, nhưng **không tự giải quyết tính nhất quán dữ liệu**. Các yêu cầu như snapshot, thứ tự total count, hoặc hiển thị thông báo có bản ghi mới vẫn cần được thiết kế và kiểm thử.

## 8. Triển khai HAL bằng Java/Spring HATEOAS

**Spring HATEOAS** cung cấp các abstraction như **Link**, **EntityModel**, **CollectionModel**, **PagedModel**, **RepresentationModelAssembler** và các API xây link dựa trên Spring MVC mapping. Chúng giúp thêm relation vào representation, giảm việc tự ghép URI và hỗ trợ serialize các biểu diễn hypermedia.

Ví dụ dưới đây dùng **Spring Boot 3, Spring MVC và Spring HATEOAS**. Để tập trung vào hypermedia, mã giả định ứng dụng đã có xác thực, lớp dữ liệu, xử lý exception và dịch vụ tạo payment intent. Phần cần lưu ý là cách **xác định action khả dụng** và **đặt link vào response**.

### 8.1. Thêm dependency

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-hateoas</artifactId>
</dependency>
~~~

Chọn phiên bản Spring Boot phù hợp với dự án để dependency management chọn Spring HATEOAS tương thích; không tự trộn nhiều phiên bản thư viện tùy ý.

### 8.2. Một REST controller sinh link theo trạng thái

~~~java
import java.net.URI;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.*;

record OrderView(String id, String status, long version) {}
record PaymentRequest(String provider) {}
record PaymentCreated(String id) {}

interface OrdersService {
    OrderView getVisibleOrder(String id);
    boolean canCreatePayment(String id);
    PaymentCreated createPayment(String id, PaymentRequest request, String key);
}

@RestController
@RequestMapping("/v1/orders")
class OrderController {
    private static final String CREATE_PAYMENT_REL =
            "https://api.example.test/rels/create-payment";

    private final OrdersService service;

    OrderController(OrdersService service) {
        this.service = service;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    ResponseEntity<EntityModel<OrderView>> get(@PathVariable String id) {
        OrderView order = service.getVisibleOrder(id);

        EntityModel<OrderView> model = EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                        .get(order.id())).withSelfRel()
        );

        if ("AWAITING_PAYMENT".equals(order.status())
                && service.canCreatePayment(order.id())) {

            model.add(
                linkTo(methodOn(OrderController.class)
                        .createPayment(
                                order.id(), null, null))
                    .withRel(LinkRelation.of(CREATE_PAYMENT_REL))
            );
        }

        return ResponseEntity.ok()
                .contentType(MediaTypes.HAL_JSON)
                .cacheControl(CacheControl.noStore())
                .eTag("\"order-v" + order.version() + "\"")
                .body(model);
    }

    @PostMapping(
            value = "/{id}/payment-intents",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<Void> createPayment(
            @PathVariable String id,
            @RequestBody PaymentRequest request,
            @RequestHeader("Idempotency-Key") String key) {

        PaymentCreated payment = service.createPayment(id, request, key);
        return ResponseEntity.created(
                URI.create("/v1/payment-intents/" + payment.id())
        ).build();
    }
}
~~~

**Giải thích các điểm quan trọng:**

- **linkTo(methodOn(...))** dựa trên mapping Spring MVC để xây URI của method đích; hạn chế sự phụ thuộc vào các chuỗi path được viết thủ công ở nhiều nơi.
- **withSelfRel()** đánh dấu liên kết tới chính đơn hàng.
- **withRel(LinkRelation.of(...))** đặt relation nghiệp vụ ổn định, tách khỏi URI của action.
- Server **chỉ đưa link create-payment** khi trạng thái và quyền cho phép ở thời điểm tạo representation.
- **GET** trả ETag theo phiên bản trạng thái và **Cache-Control: no-store** cho dữ liệu đơn nhạy cảm; **POST** tạo payment intent trả **201 Created** cùng Location.
- **OrdersService.createPayment** vẫn phải kiểm tra quyền, trạng thái, idempotency và xử lý transaction khi thực thi; không dùng điều kiện trong GET làm bảo đảm an toàn cho POST.

Mã trên là **minh họa kiến trúc**, chưa cung cấp triển khai OrdersService, entity/database, validation, security filter, error handler hoặc transactional workflow nên **không tự chạy như ứng dụng hoàn chỉnh**. Đặc biệt, việc trả đúng HAL JSON đòi hỏi cấu hình Spring HATEOAS/Jackson phù hợp trong dự án.

Với một controller public thật, phương thức **canCreatePayment** phải tính theo **người dùng đã xác thực và resource thực**, tránh tạo link dựa trên ID đoán được. Hành động POST phải từ chối thao tác không hợp lệ ngay cả khi người dùng gửi trực tiếp URI mà không theo link.

### 8.3. Có cần thêm mọi link vào mỗi response?

Không. Một biểu diễn nên cung cấp **những relation hữu ích cho use case hiện tại**, tránh biến response thành danh mục hàng trăm endpoint. Một số lựa chọn phổ biến:

- **Self:** để client làm mới tài nguyên và giữ định danh.
- **Collection/parent:** để quay lại tập hợp.
- **Navigational links:** customer, items, shipment, invoice, next/prev khi liên quan.
- **State transition links:** thanh toán, yêu cầu hủy, xác nhận giao hàng khi hợp lệ.
- **Documentation/profile:** khi client cần hiểu schema hoặc relation đặc biệt.

Tránh trả một action khi nó chỉ dẫn tới lỗi nghiệp vụ chắc chắn trong trạng thái hiện tại. Ngược lại, đừng bỏ **self** một cách tùy tiện nếu client cần làm mới tài nguyên sau một thao tác bất đồng bộ.

### 8.4. CollectionModel và PagedModel

Đối với API trả danh sách, Spring HATEOAS có **CollectionModel** cho một nhóm entity model và **PagedModel** để biểu diễn metadata phân trang cùng các relation next/prev. Spring Data Web có thể kết hợp với **PagedResourcesAssembler** trong những trường hợp phù hợp.

Khi sử dụng, hãy phân biệt:

1. **Cách trả representation**: collection, embedded item, metadata và relation.
2. **Cách truy vấn dữ liệu**: offset/limit, keyset/cursor, thứ tự và điều kiện lọc.
3. **Điều kiện truy cập**: chỉ tài nguyên thuộc phạm vi người dùng đã được phân quyền.

Framework hỗ trợ **xây link**, nhưng không tự bảo đảm consistency của cursor, hiệu năng query, tính đúng của total count hay quyền truy cập vào item được nhúng.

## 9. Client hypermedia nên viết như thế nào?

Client hypermedia cần biết **các relation nó sử dụng** và cách thực hiện action tương ứng, nhưng có thể tránh hardcode URI cụ thể.

### 9.1. Client đi theo link đã trả

Ví dụ TypeScript đơn giản:

~~~typescript
type Link = { href: string };

type OrderResource = {
  id: string;
  status: string;
  _links?: Record<string, Link | Link[]>;
};

const CREATE_PAYMENT_REL =
  "https://api.example.test/rels/create-payment";

function getHref(order: OrderResource, rel: string): string | undefined {
  const value = order._links?.[rel];
  if (!value) return undefined;
  return Array.isArray(value) ? value[0]?.href : value.href;
}

async function createPaymentIntent(
  order: OrderResource,
  responseUrl: string,
  provider: string,
  idempotencyKey: string
) {
  const href = getHref(order, CREATE_PAYMENT_REL);
  if (!href) {
    return { available: false as const };
  }

  // Resolve relative URI; validate trusted origin / HTTPS policy in real clients.
  const target = new URL(href, responseUrl);

  // POST được biết từ hợp đồng relation, không suy ra từ HAL href.
  const response = await fetch(target, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json",
      "Idempotency-Key": idempotencyKey
    },
    body: JSON.stringify({ provider })
  });

  if (!response.ok) {
    // Parse API error contract; refresh order on 409/412 when appropriate.
    throw new Error("Payment intent request failed");
  }

  return { available: true as const, payment: await response.json() };
}
~~~

Đây là ví dụ tập trung vào **duyệt relation**, chưa bao gồm auth, CSRF protection, timeout, policy URL tin cậy, Problem Details hay logic đối soát thanh toán. Nếu server được phép trả href tuyệt đối, client cần quy tắc **trusted origin/allowlist** và không tự gửi access token tới một host tùy ý xuất hiện trong response. Với trình duyệt, hành vi CORS và credential cũng phải được thiết kế, kiểm thử.

Điểm chính: client **không ghép** URI theo công thức /orders/{id}/payment-intents. Khi server chuyển payment intent endpoint sang một URI khác nhưng giữ relation và contract, client đi theo liên kết hiện tại vẫn hoạt động.

### 9.2. Kiểu client phụ thuộc endpoint so với client hypermedia

| Tình huống | Client ghép URI cố định | Client theo hypermedia |
|---|---|---|
| Server đổi URI của shipment | Phải sửa code hoặc redirect | Có thể theo shipment href mới |
| Trạng thái không cho phép hủy | Client phải biết toàn bộ business rules | Client không thấy affordance hủy, vẫn xử lý lỗi race |
| Server dùng cursor thay offset | Client tự tính trang có thể lỗi | Client đi theo next |
| Có tính năng mới không liên quan | Client thường chưa biết | Có thể bỏ qua relation chưa hiểu |
| Relation đổi ý nghĩa hoặc schema action đổi breaking | Cần cập nhật | **Vẫn cần cập nhật** |
| Mất authorization | Request có thể bị từ chối | **Vẫn bị từ chối**; link không cấp quyền |

HATEOAS **giảm coupling vào URI và luồng điều hướng**, chứ không xóa bỏ mọi coupling. Client vẫn cần hiểu **media type, relation, schema, business semantics, authentication và error contract**.

### 9.3. Không nên thực hiện action chỉ vì relation có mặt

Client có thể hiển thị nút “Thanh toán” khi nhận link, nhưng chỉ gửi POST khi người dùng chủ động xác nhận và dữ liệu đầu vào hợp lệ. Không tự động nhấn mọi action trong response, đặc biệt với thanh toán, hủy, chuyển tiền, xóa hoặc gửi email. **GET/HEAD phải giữ tính safe**; nếu client hoặc crawler có thể làm thay đổi trạng thái chỉ bằng cách theo link GET thì API đã vi phạm ý nghĩa HTTP và có rủi ro vận hành.

### 9.4. Khi không có relation cần thiết

Client có thể:

- Làm mới self vì trạng thái có thể đã thay đổi.
- Hiển thị một thông báo phù hợp (“Chưa thể thanh toán lúc này”).
- Hiển thị hành động thay thế có relation khác (ví dụ liên hệ hỗ trợ).
- Ghi telemetry cấp ứng dụng rằng hành trình hiện không có affordance cần thiết.

Không nên tự đoán URI ẩn rồi thử gọi chỉ để “vượt qua” việc thiếu link. Nếu sản phẩm yêu cầu một action luôn khả dụng mà response không có, đó là **vấn đề contract/logic** cần được kiểm tra với server.

## 10. Thiết kế hợp đồng hypermedia: HTTP, tài liệu và tương thích

Một hệ API hypermedia vẫn cần hợp đồng rõ ràng. **URI có thể được khám phá**, nhưng **ngữ nghĩa của relation, method, data schema và quy tắc chuyển trạng thái** phải được xác định để các client có thể lập trình và kiểm thử.

### 10.1. Mẫu tài liệu cho một relation nghiệp vụ

| Trường hợp đồng | Giá trị minh họa |
|---|---|
| **Relation URI** | https://api.example.test/rels/create-payment |
| **Ý nghĩa** | Tạo một payment intent cho đơn tại trạng thái được phép |
| **Khi xuất hiện** | Người gọi được quyền, đơn đang AWAITING_PAYMENT |
| **Target href** | Trả động trong _links; client dùng nguyên giá trị được cấp |
| **HTTP method** | POST |
| **Content-Type gửi lên** | application/json |
| **Payload mẫu** | { "provider": "supported-psp" } |
| **Idempotency** | Header Idempotency-Key bắt buộc, phạm vi một lần thanh toán |
| **Thành công** | 201 Created + Location tới payment-intent resource |
| **Lỗi thường gặp** | 400, 401, 403, 409, 422, 429, 503 theo contract |
| **Tình huống cạnh tranh** | Nếu trạng thái đã thay đổi, server từ chối; client GET self mới |
| **Bảo mật** | Kiểm tra quyền trên đơn và idempotency ở điểm thực thi |

Một relation có **định danh ổn định** nên tồn tại qua nhiều phiên bản URI đích. Nếu phương thức hoặc ý nghĩa nghiệp vụ thay đổi theo cách không tương thích, cần xem xét **relation mới hoặc phiên bản contract rõ ràng**, thay vì lặng lẽ đổi nghĩa relation cũ.

### 10.2. OpenAPI vẫn hữu ích

OpenAPI giúp mô tả **operation, request/response schema, security, error status và ví dụ**. Tuy nhiên, một mô tả OpenAPI truyền thống chủ yếu liệt kê endpoint và method; nó không tự động bảo đảm client **theo các link có sẵn trong từng response**.

Có thể kết hợp:

1. **OpenAPI** để mô tả POST create-payment, GET order, GET shipment, DELETE/hủy khi thích hợp và các lỗi.
2. **Media type + relation documentation** để client hiểu ý nghĩa của self, next, create-payment…
3. **Contract test** để bảo đảm server chỉ xuất hiện relation hợp lệ trong từng trạng thái/quyền.
4. **Client test** để chứng minh client đi theo href trả về, không tự ghép URI.

Trong một số phiên bản OpenAPI có **links object**, cho phép mô tả mối quan hệ giữa một response operation với operation khác. Nhưng OpenAPI links **không thay thế** những hypermedia control thực sự có trong response runtime; client phải được xây để sử dụng các link mà server trả.

### 10.3. Thêm relation mới thường dễ hơn đổi relation cũ

Ví dụ server thêm **https://api.example.test/rels/request-return** sau khi đơn hoàn tất. Client cũ có thể bỏ qua relation mới; client mới có thể hiển thị chức năng trả hàng. Nhưng nếu server đổi **create-payment** để chỉ vào một endpoint nhận nội dung XML thay vì JSON mà không thay tài liệu/hợp đồng, client cũ vẫn có link nhưng có thể gửi sai yêu cầu.

Để thay đổi an toàn, cần đánh giá:

- Relation có giữ nguyên ý nghĩa?
- HTTP method và content type có tương thích?
- Response schema có còn các trường client đã dùng?
- Có thể thêm link mà không xóa link cũ trong giai đoạn chuyển tiếp?
- Các client offline/mobile cũ có thể xử lý relation chưa biết và fallback không?

### 10.4. Thay đường dẫn không có nghĩa được phá chính sách bảo mật

Client có thể theo link từ **/v1/orders/o-918** tới một URL trên host khác. Cần có quy tắc đối với **authority/origin** của href: sử dụng HTTPS, định nghĩa các host tin cậy, xử lý redirect an toàn, không tự gửi Authorization hoặc cookie tới host ngoài danh sách cho phép.

Nếu relation dẫn tới hệ thống bên ngoài (ví dụ trang thanh toán do PSP lưu trữ), cần **hợp đồng riêng cho URL chuyển hướng**, tính hết hạn, chữ ký/nonce, chính sách mở tab và cách xác nhận kết quả đáng tin cậy. Việc một URL được đưa vào response không có nghĩa đích đến tự động được client tin tưởng tuyệt đối.

## 11. Caching, ETag, lỗi và hypermedia

Link không đứng ngoài cơ chế HTTP; nó là **một phần của representation** và chịu tác động của cache, trạng thái tài nguyên và phân quyền.

### 11.1. Khi link thay đổi theo trạng thái

Giả sử GET đơn ở trạng thái AWAITING_PAYMENT có link create-payment. Sau khi PSP xác nhận thanh toán, GET mới trả PAID và link create-payment biến mất. Nếu cache trả representation cũ, UI có thể tiếp tục hiển thị nút thanh toán không còn hợp lệ.

Giải pháp gồm:

- **Cache-Control: no-store** hoặc private với chính sách làm mới phù hợp cho tài nguyên riêng và trạng thái đổi nhanh.
- **ETag** gắn với phiên bản representation bao gồm những thay đổi có ý nghĩa, kể cả tập link.
- Client có thể dùng **If-None-Match** để xác minh representation khi cache được phép.
- Mọi action ghi vẫn **kiểm tra lại trạng thái và quyền**, ngay cả khi client có representation còn hạn cache.

Ví dụ:

~~~http
GET /v1/orders/o-918 HTTP/1.1
Host: api.example.test
If-None-Match: "order-v3"
Accept: application/hal+json
~~~

Khi server cho phép revalidation và representation chưa đổi, có thể trả **304 Not Modified** theo điều kiện và hợp đồng cache. Trong ví dụ trước sử dụng **no-store** cho đơn nhạy cảm; **không nên kết hợp một cache client của response no-store với giả định nó được giữ để revalidate**. Vì vậy, ví dụ 304 ở đây chỉ mô tả **một API được cấu hình cache private/revalidation phù hợp**, không phải diễn biến mặc định của mẫu no-store.

### 11.2. Cần cân nhắc Vary khi representation phụ thuộc quyền

Một representation có thể khác nhau theo **Accept** (JSON thường hay HAL), ngôn ngữ hoặc các header khác. Khi response được phép cache, sử dụng **Vary** đúng theo trường làm thay đổi representation.

**Vary: Authorization** không tự giải quyết bảo vệ dữ liệu qua mọi cache, đặc biệt với cookie và cơ chế auth khác nhau. Với đơn hàng cá nhân, chọn **private/no-store** và kiểm soát cache ở CDN/gateway rõ ràng thường dễ kiểm chứng hơn. Không dựa vào Vary như cơ chế phân quyền.

### 11.3. Link không thay thế HTTP status

| Tình huống | Cách phản hồi phù hợp |
|---|---|
| Tạo đơn thành công | 201 Created + Location và có thể body hypermedia |
| Chấp nhận tác vụ nhưng chưa hoàn tất | 202 Accepted + link tới job/status |
| GET tài nguyên thành công | 200 OK + representation/self link |
| Resource không tồn tại hoặc không được tiết lộ | 404 Not Found theo contract |
| Người dùng chưa xác thực hoặc không được phép | 401/403 theo ngữ nghĩa |
| Trạng thái thay đổi sau khi nhận link | 409 Conflict hoặc 412 khi precondition sai, theo contract |
| Thao tác gây quá tải/hạn mức | 429 hoặc 503 theo nguyên nhân và policy |
| Resource đã xóa | 404 hoặc 410 theo policy, dù client còn href cũ |

Một client đúng phải vừa đọc **status/error contract** vừa theo **hypermedia controls** khi có response thành công. Không nên biến mọi response thành HTTP 200 rồi chỉ dùng trường links hoặc status bên trong JSON để báo lỗi.

### 11.4. Tác vụ bất đồng bộ cũng có thể có hypermedia

Khi client gửi POST tạo một tác vụ chạy lâu:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/jobs/j-900
Content-Type: application/hal+json

{
  "id": "j-900",
  "status": "RUNNING",
  "_links": {
    "self": {"href": "/v1/jobs/j-900"},
    "https://api.example.test/rels/cancel-job": {
      "href": "/v1/jobs/j-900/cancellation-requests"
    }
  }
}
~~~

Khi job hoàn tất, representation có thể thêm relation **result** và không còn cancel-job. Client theo **self** để làm mới và tiếp tục đến kết quả. Tuy nhiên, **202 không đảm bảo công việc chắc chắn hoàn thành**; server cần công bố TTL của job, hành vi khi lỗi/timeout và cách tra cứu/đối soát nếu mạng bị gián đoạn.

## 12. Bảo mật và phân quyền trong API dùng HATEOAS

### 12.1. Kiểm tra quyền ở cả hai thời điểm

Kiểm tra quyền khi **tạo link** cải thiện trải nghiệm: chỉ hiển thị hành động phù hợp. Kiểm tra quyền khi **xử lý request** bảo vệ tài nguyên. Hai lần kiểm tra có vai trò khác nhau.

~~~mermaid
flowchart TB
    A["GET đơn hàng"] --> B["Xác thực + kiểm tra quyền xem"]
    B --> C["Đọc trạng thái hiện tại"]
    C --> D["Tạo self + affordance hợp lệ"]
    D --> E["Client thấy link tạo thanh toán"]
    E --> F["POST theo link"]
    F --> G["Xác thực + kiểm tra quyền thực thi"]
    G --> H["Kiểm tra lại trạng thái/idempotency"]
    H --> I{"Hợp lệ?"}
    I -->|Có| J["Commit giao dịch / tạo intent"]
    I -->|Không| K["409/403/412 theo contract"]
~~~

**Không cho rằng URI khó đoán là bảo mật**. Client có thể nhận một link trước đó, đoán ID hoặc nhận URL từ người khác. Server phải kiểm tra quyền theo **resource, tenant, người dùng và trạng thái**, đặc biệt với API đa tenant.

### 12.2. Không để lộ các hành động nhạy cảm

Một tài nguyên trong response có thể hiển thị link hủy, hoàn tiền hoặc xem hóa đơn. Khi tạo response cho vai trò không có quyền:

- Không đưa affordance admin/hoàn tiền vào payload nếu không thuộc phạm vi người gọi.
- Kiểm tra quyền đọc cả tài nguyên **embedded** và đường link liên quan.
- Không để shared cache phát lại link/tài liệu của tài khoản khác.
- Không gắn token bí mật dài hạn vào URL vì URL dễ bị ghi lại trong history, log hoặc referer.
- Giới hạn redirect và các URL do dữ liệu không đáng tin cậy sinh ra.

### 12.3. Link relation không phải authorization scope

Một relation như **request-cancellation** nói về **ý nghĩa hành động**. Scope như **orders:cancel** chỉ thể hiện quyền có thể cần, không nói resource cụ thể có đang ở trạng thái được phép hủy không. Hai khía cạnh phải được kiểm tra cùng nhau. Đừng dùng việc có/không có link làm bằng chứng duy nhất khi audit an ninh.

### 12.4. Hypermedia với dữ liệu có tính riêng tư

Một server có thể trả **_embedded.customer** hoặc link tới customer. Kể cả khi client chỉ nhận URI, liên kết vẫn có thể tiết lộ ID hoặc cấu trúc dữ liệu nếu không kiểm soát. Trước khi xuất link/embedded, xác định rõ **data classification, ownership và policy**; nội dung được nhúng có thể cần authorization riêng với dữ liệu của tài nguyên cha.

## 13. Kiểm thử HATEOAS như một luồng nghiệp vụ

Một unit test chỉ xác minh có trường **_links** trong JSON chưa đủ. Cần kiểm tra **khả năng client đi theo quan hệ thực**, sự thay đổi của relation theo trạng thái, authorization và hiệu ứng của action.

### 13.1. Ma trận kiểm thử chính

| Kịch bản | Hành động | Kết quả cần chứng minh |
|---|---|---|
| **Entry point** | GET /v1 với user đã xác thực | Có relation vào tài nguyên được phép |
| **Tạo đơn** | POST /v1/orders | 201 + Location + self đúng resource mới |
| **Chờ thanh toán** | GET đơn AWAITING_PAYMENT | Có create-payment khi user có quyền |
| **Sau thanh toán** | GET đơn PAID | Không có create-payment; có link receipt/shipment theo quy tắc |
| **Khác quyền** | GET cùng đơn bằng hai vai trò | Bộ relation theo quyền, không lộ action trái phép |
| **Replay link cũ** | Gửi POST qua URI từ trạng thái cũ | Server kiểm tra lại, trả lỗi hợp đồng nếu đã đổi trạng thái |
| **URI thay đổi** | Server đổi href, giữ rel/contract | Client vẫn đi theo relation và hoàn tất luồng |
| **Pagination** | Theo next cho tới khi vắng | Không cần tự tính page/offset, giữ filter |
| **Cursor hỏng** | Dùng cursor hết hạn/sai | Lỗi rõ nghĩa, không lộ nội dung cursor nhạy cảm |
| **Affordance lạ** | Thêm relation mới vào response | Client cũ không crash hoặc gửi nhầm action |
| **External URL** | Href dẫn tới origin ngoài policy | Client không chuyển token bí mật hoặc tự thực hiện lệnh |
| **Cache** | GET trước/sau đổi trạng thái | Không giữ action cũ để tạo nhầm hiệu ứng; revalidation đúng |
| **Race** | Đổi trạng thái giữa GET và POST | Không thực hiện action trái điều kiện hiện tại |
| **Timeout** | Tạo payment intent nhưng mất response | Idempotency/đối soát giữ đúng hiệu ứng |
| **Format** | Accept HAL hoặc JSON thường | Content-Type và schema đúng theo negotiation |

### 13.2. Ví dụ kiểm tra JSON HAL bằng MockMvc

Giả sử controller từ mục 8 đã được gắn với một stub OrdersService, có một đơn **o-918** ở trạng thái AWAITING_PAYMENT và chủ đơn có quyền tạo payment intent.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderHypermediaTest {
    @Autowired
    MockMvc mvc;

    @Test
    void pendingOrderHasPaymentAffordance() throws Exception {
        mvc.perform(get("/v1/orders/o-918")
                .accept("application/hal+json"))
           .andExpect(status().isOk())
           .andExpect(content().contentTypeCompatibleWith(
                "application/hal+json"))
           .andExpect(jsonPath("$._links.self.href").exists())
           .andExpect(jsonPath(
                "$._links['https://api.example.test/rels/create-payment'].href"
           ).exists());
    }
}
~~~

Đây là **test minh họa**, không tự chạy độc lập vì thiếu cấu hình stub/auth và dữ liệu test. Khi dùng Spring Security, bài test phải cấp **principal và quyền thực tế** hoặc test authentication tương ứng. Để kiểm tra relation biến mất khi PAID, chuẩn bị một test fixture PAID và assert JSONPath của relation create-payment **không tồn tại**.

### 13.3. Kiểm thử điều hướng thay vì chỉ kiểm tra chuỗi href

Một phép thử tích hợp mạnh hơn có thể thực hiện:

1. Gọi entry point, lấy relation **orders**.
2. Tạo một đơn trong môi trường test theo hợp đồng.
3. Dùng **Location/self** để lấy đơn vừa tạo.
4. Lấy **create-payment href** từ response, gửi POST với idempotency key.
5. Làm mới **self**, mô phỏng xác nhận PSP qua luồng kiểm thử hợp lệ.
6. Xác nhận relation create-payment biến mất và receipt xuất hiện khi đủ điều kiện.
7. Kiểm tra mọi truy cập đã qua authorization và trạng thái đơn đúng bất biến.

Trong bài test này, **không viết lại URI từ order ID** ngoài điểm khởi đầu/hợp đồng cần thiết. Nếu test vẫn hardcode toàn bộ href, nó không chứng minh ưu điểm khám phá liên kết của HATEOAS.

### 13.4. Phép thử thay đổi URI mà client không biết

Thay cấu hình route trong môi trường test:

~~~text
Trước: /v1/orders/o-918/payment-intents
Sau:   /v1/payment-requests?orderRef=o-918
Rel:   https://api.example.test/rels/create-payment (giữ nguyên)
~~~

Nếu client đã được lập trình **theo rel/href** và hợp đồng POST không đổi, hành trình thanh toán vẫn có thể chạy. Nếu client tự ghép URI cũ, test phát hiện ngay sự phụ thuộc. Cần xem xét kỹ khả năng tương thích, idempotency và semantics; chỉ thay đường dẫn không phải là lý do để tự đổi relation.

### 13.5. Kiểm thử bảo mật link

- Một user không có quyền xem đơn phải nhận response theo policy (403/404), **không chỉ một JSON rỗng links**.
- Một user xem được đơn nhưng không có quyền thanh toán có thể không thấy action create-payment; gửi POST trực tiếp vẫn bị từ chối.
- Gửi request dựa trên link cũ sau khi chuyển trạng thái phải bị kiểm tra lại.
- Href tuyệt đối ngoài danh sách origin tin cậy không được khiến client rò Authorization/token.
- Không để cache/gateway phát bộ relation theo quyền của user A cho user B.

## 14. Bài tập thiết kế: API quản lý yêu cầu hoàn trả

Một sàn bán hàng có các trạng thái đơn:

**AWAITING_PAYMENT → PAID → FULFILLING → COMPLETED**; có thể chuyển sang **CANCELLED** khi đủ điều kiện. Khách có thể **yêu cầu hoàn trả (return request)** trong 7 ngày sau khi đơn COMPLETED; nhân viên hỗ trợ có quyền xem lịch sử, duyệt hoặc từ chối yêu cầu hoàn trả. Yêu cầu trả hàng là **tài nguyên riêng**, trạng thái **REQUESTED → APPROVED/REJECTED → REFUNDED** theo quy trình.

Mục tiêu: một web client và một mobile client có thể đi theo các relation trả về mà không phải tự đoán URL của bước tiếp theo. Người dùng không được thấy hoặc thực hiện action ngoài quyền của họ.

### 14.1. Các nhiệm vụ

1. Thiết kế **entry point** dẫn tới collection orders của người dùng.
2. Cho một đơn ở trạng thái AWAITING_PAYMENT, đề xuất các relation cần trả về và giải thích method của từng action.
3. Cho một đơn ở trạng thái COMPLETED và **còn trong 7 ngày**, thêm relation thích hợp để tạo return request. Sau khi quá hạn, relation phải thay đổi thế nào?
4. Với đơn COMPLETED có return request, hãy thiết kế resource cho return request và bộ relation theo trạng thái **REQUESTED**, **APPROVED** và **REFUNDED**.
5. Viết hai response HAL tối thiểu: một cho đơn có thể trả hàng, một cho đơn quá hạn hoặc user thiếu quyền.
6. Nêu phương án xử lý khi user giữ link tạo return request trước khi hết hạn nhưng gửi POST **sau** hạn.
7. Đề xuất kiểm thử về status, authorization, cache, race và idempotency.

### 14.2. Gợi ý lời giải

Một đơn còn hạn hoàn trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Cache-Control: private, no-store

{
  "id": "o-300",
  "status": "COMPLETED",
  "completedAt": "2026-11-15T10:00:00Z",
  "_links": {
    "self": {"href": "/v1/orders/o-300"},
    "collection": {"href": "/v1/orders"},
    "https://api.example.test/rels/request-return": {
      "href": "/v1/orders/o-300/return-requests"
    }
  }
}
~~~

Một đơn đã quá thời hạn trả hàng:

~~~json
{
  "id": "o-200",
  "status": "COMPLETED",
  "completedAt": "2026-10-01T10:00:00Z",
  "_links": {
    "self": {"href": "/v1/orders/o-200"},
    "collection": {"href": "/v1/orders"}
  }
}
~~~

Client nhận thấy relation **request-return** không có ở biểu diễn thứ hai và **không hiển thị action trả hàng**. Server vẫn phải kiểm tra hạn 7 ngày, quyền và trạng thái đơn khi xử lý POST. Trường hợp user POST sau hạn có thể trả **409 Conflict** hoặc một mã lỗi nghiệp vụ khác theo hợp đồng; không tự chấp nhận vì URI từng được phát trong một response trước đó.

Một resource return request:

~~~json
{
  "id": "rr-70",
  "orderId": "o-300",
  "status": "REQUESTED",
  "_links": {
    "self": {"href": "/v1/return-requests/rr-70"},
    "https://api.example.test/rels/order": {
      "href": "/v1/orders/o-300"
    },
    "https://api.example.test/rels/approve-return": {
      "href": "/v1/return-requests/rr-70/approval-decisions"
    }
  }
}
~~~

**Chú ý:** relation approve-return trong ví dụ trên **chỉ xuất hiện cho người có quyền duyệt**, chẳng hạn nhân viên được phân quyền. Với khách hàng, response có thể chỉ có self/order và các lựa chọn theo đúng vai trò. Việc phê duyệt có thể tạo một decision resource bằng POST; khi đã APPROVED, relation approve-return biến mất và có thể xuất hiện link theo dõi hoàn tiền. Khi REFUNDED, resource vẫn có self và lịch sử liên quan nhưng không còn action phê duyệt/hoàn tiền trùng.

### 14.3. Một đáp án tốt phải giải thích được các đánh đổi

- **URI ổn định, relation rõ nghĩa** giúp thay route mà client vẫn điều hướng được.
- **Action theo trạng thái** giúp giao diện hiển thị lựa chọn phù hợp, nhưng không thay server authorization.
- **Tài nguyên return request** có trạng thái riêng, tránh gộp “đã yêu cầu” và “đã hoàn tiền”.
- **Idempotency key/transaction** giúp không tạo hai yêu cầu trả hàng cho một thao tác retry.
- **GET self và cache policy** cho phép cập nhật affordance khi tình trạng thay đổi.
- **Hợp đồng media type/method** cho client biết POST và schema của return request; HAL link không đủ để tự suy ra mẫu form.

## 15. Những anti-pattern và hiểu nhầm thường gặp

### 15.1. “JSON nào có URL cũng là HATEOAS”

**Vấn đề:** một số response chỉ có các trường paymentUrl, cancelEndpoint hoặc nextPage nhưng không có relation được tài liệu hóa. Client phải học ý nghĩa của từng thuộc tính riêng lẻ, tự đoán method và điều kiện sử dụng.

**Cải thiện:** dùng một **media type/hợp đồng nhất quán** và xác định relation rõ ràng. Nếu vẫn dùng JSON tự thiết kế, cần quy chuẩn cách client phân biệt **link, action, method, type và input**; không nhất thiết phải đổi sang HAL nếu hệ sinh thái đã có format tự định nghĩa đủ tốt và được kiểm thử.

### 15.2. “Có HAL là tự động đạt RESTful”

**Vấn đề:** API trả _links nhưng mọi thao tác thực vẫn dựa vào một endpoint POST /execute với tên hành động tùy ý và không dùng ngữ nghĩa HTTP đúng. Hoặc backend cho phép GET tạo thanh toán vì action dễ gọi.

**Cải thiện:** hypermedia cần đi cùng **resource modeling, HTTP method semantics, stateless interaction, cache khi phù hợp và status code chính xác**. HATEOAS không thay thế các ràng buộc REST khác.

### 15.3. “Một link tự nói rõ HTTP method”

**Vấn đề:** client thấy href dẫn tới /cancellation-requests rồi gọi GET vì cho rằng mọi link đều dùng GET, hoặc gửi DELETE dựa vào tên “cancel”.

**Cải thiện:** với HAL, method và schema của action phải được công bố qua **relation contract/OpenAPI** hoặc một cơ chế affordance thích hợp. Với Siren, có thể dùng actions để cung cấp thêm metadata. Đừng suy method chỉ từ tên path.

### 15.4. “Link đang hiện thì không cần kiểm tra quyền”

**Vấn đề:** frontend ẩn nút “Hủy đơn” nếu không có relation, nhưng server vẫn chấp nhận POST vào URI cũ của user không có quyền hoặc đơn đã hết hạn.

**Cải thiện:** luôn kiểm tra xác thực, authorization, trạng thái tài nguyên và điều kiện cạnh tranh **tại thời điểm thực thi**. Việc phát link chỉ là một phần trải nghiệm và hợp đồng khám phá.

### 15.5. “Càng nhiều link càng tốt”

**Vấn đề:** response gồm hàng trăm relation không dùng đến, embedded dữ liệu thừa, tính toán quyền cho mọi action khiến latency tăng và có nguy cơ lộ thông tin.

**Cải thiện:** chọn link theo **use case, resource boundary và quyền**. Đo payload size, N+1 query, công sức xác minh permissions và khả năng cache. Để client truy cập sâu hơn qua relation cần thiết thay vì nhúng tất cả dữ liệu.

### 15.6. “Client đã biết URI thì không cần đọc response”

**Vấn đề:** server đã trả next link và create-payment href, nhưng client bỏ qua rồi tự xây URI từ ID. Đổi route hoặc cursor khiến client lỗi.

**Cải thiện:** kiểm thử một hành trình thực sự **lấy href từ representation và theo relation**. Giữ URI như dữ liệu được khám phá; tránh thao tác chuỗi thủ công trên đường dẫn.

### 15.7. “Thêm relation mới luôn an toàn”

**Vấn đề:** client giả định _links có đúng một số khóa cố định, parse vào object quá chặt hoặc vỡ khi nhận relation lạ.

**Cải thiện:** client cần bỏ qua relation chưa biết. Server thêm relation cùng ngữ nghĩa chuẩn thường là thay đổi mở rộng; nhưng không được đổi **ý nghĩa, method hoặc schema** của relation cũ một cách âm thầm.

### 15.8. “Hypermedia khiến API không cần versioning”

**Vấn đề:** đội phát triển đổi schema, xóa thuộc tính quan trọng hoặc thay quy trình thanh toán nhưng cho rằng client cứ theo link là tự thích nghi.

**Cải thiện:** HATEOAS giảm phụ thuộc vào URI và thứ tự điều hướng, **không loại bỏ phụ thuộc ngữ nghĩa**. Vẫn cần policy tương thích, migration và kiểm thử ứng dụng khách cũ.

### 15.9. “Không có action tức là thao tác chắc chắn không được phép”

**Vấn đề:** client biến sự thiếu relation thành thông điệp “Bạn không có quyền”, trong khi nguyên nhân thật là đơn đã thay đổi trạng thái, đối tác tạm bảo trì hoặc representation không có đủ dữ liệu.

**Cải thiện:** dùng thông điệp trung tính hoặc hướng dẫn tải lại; nếu cần lý do chi tiết, thiết kế **machine-readable reason/code** thích hợp và không làm lộ thông tin nhạy cảm.

### 15.10. “HATEOAS yêu cầu bỏ hết tài liệu endpoint”

**Vấn đề:** client không biết ý nghĩa của một relation nghiệp vụ hoặc schema cho POST nhưng API chỉ nói “hãy theo link”.

**Cải thiện:** công bố **entry point, media type, relation semantics, affordance/action contract, auth, error handling và ví dụ**. Hypermedia làm giảm số URI client cần biết trước, nhưng không thay nhu cầu hợp đồng cho những thao tác máy có ý nghĩa.

## 16. Checklist review một API có hypermedia

- [ ] Tài nguyên và các trạng thái nghiệp vụ được mô hình hóa rõ ràng.
- [ ] API công bố entry point; client biết media type và relation cần thiết để bắt đầu.
- [ ] Các relation có ý nghĩa ổn định, dùng tên chuẩn hoặc extension relation URI được tài liệu hóa.
- [ ] Client theo **href được trả** thay vì tự ghép path/đoán cursor.
- [ ] Các link phục vụ hành trình nghiệp vụ, không chỉ liệt kê endpoint thiếu ngữ nghĩa.
- [ ] Với action ghi, hợp đồng mô tả **HTTP method, content type, schema, idempotency, response và điều kiện**.
- [ ] Link/action chỉ xuất hiện khi trạng thái và quyền tại thời điểm tạo response phù hợp.
- [ ] Server **vẫn kiểm tra quyền, trạng thái và điều kiện cạnh tranh** ở thời điểm thực thi.
- [ ] GET/HEAD không tạo side effect do client/crawler tự động theo link.
- [ ] Các thao tác tạo resource trả **201 + Location**, tác vụ chưa xong có **202 + link trạng thái** khi phù hợp.
- [ ] Link self, collection, next/prev, related resource và action được dùng nhất quán.
- [ ] Phân trang theo link next/prev, cursor là opaque và giữ đúng filter, order, authorization.
- [ ] Cache/ETag/Vary/no-store phản ánh việc representation và bộ link có thể thay đổi theo người dùng/trạng thái.
- [ ] Không đưa token vào href hoặc theo external link cùng thông tin xác thực ngoài policy.
- [ ] Content negotiation giữ đúng media type; không trộn HAL và JSON:API tùy tiện.
- [ ] Client bỏ qua relation không biết và có fallback khi thiếu relation cần thiết.
- [ ] OpenAPI/tài liệu relation và contract test được cập nhật cùng với code server.
- [ ] Test được toàn bộ hành trình, đổi URI, đổi trạng thái, thiếu quyền, race, retry và cache.

## 17. Tài liệu tham khảo

- **Roy T. Fielding — Architectural Styles and the Design of Network-based Software Architectures**, chương REST: nguồn gốc các ràng buộc REST và khái niệm hypermedia; https://ics.uci.edu/~fielding/pubs/dissertation/top.htm
- **RFC 8288 — Web Linking**: link relation, Link header và định danh relation; https://www.rfc-editor.org/rfc/rfc8288.html
- **IANA Link Relation Types registry**: các relation phổ biến được đăng ký; https://www.iana.org/assignments/link-relations/link-relations.xhtml
- **RFC 6570 — URI Template**: cú pháp và cách mở rộng URI template; https://www.rfc-editor.org/rfc/rfc6570.html
- **RFC 9110 — HTTP Semantics**: method, status, header, representation và conditional requests; https://www.rfc-editor.org/rfc/rfc9110.html
- **HAL specification**: mô hình _links và _embedded, media type application/hal+json; https://stateless.group/hal_specification.html
- **JSON:API specification**: tài nguyên, relationships và links; https://jsonapi.org/format/
- **Siren specification**: links, actions và fields; https://github.com/kevinswiber/siren
- **Spring HATEOAS Reference**: EntityModel, CollectionModel, PagedModel, link builders và media types; https://docs.spring.io/spring-hateoas/docs/current/reference/html/
- **OpenAPI Specification**: hợp đồng operation, schema, responses và links object; https://spec.openapis.org/oas/latest.html

**Điều cần nhớ:** HATEOAS đặt **liên kết và điều khiển hypermedia** vào trung tâm luồng tương tác. Một API tốt cho client biết **tài nguyên hiện tại liên quan đến đâu và hành động nào đáng cân nhắc tiếp theo**, trong khi HTTP method, schema, quyền và luật nghiệp vụ vẫn được xác định chặt chẽ. Client đi theo **relation/href hiện có**, server kiểm soát **trạng thái và authorization ở thời điểm thực thi**; đó là cách giảm phụ thuộc vào URI cố định mà không đánh đổi tính đúng và an toàn của REST API.

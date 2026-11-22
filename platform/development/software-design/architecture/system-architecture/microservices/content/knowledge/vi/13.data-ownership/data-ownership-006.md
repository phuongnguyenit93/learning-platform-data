# Định danh và tham chiếu đối tượng xuyên dịch vụ

## 1. Vấn đề: các service biết đối tượng của nhau bằng cách nào?

Trong kiến trúc microservices, mỗi service có thể sở hữu mô hình dữ liệu, transaction và cơ sở dữ liệu riêng. Order cần biết đơn hàng thuộc khách nào; Payment cần liên hệ khoản thu với đơn; Inventory cần biết một reservation dành cho order nào; Shipping cần địa chỉ giao và mã đơn để tạo vận đơn.

Điều này không có nghĩa các service được phép đọc và ghi trực tiếp bảng của nhau. Khi tách quyền sở hữu dữ liệu, chúng ta cần một cách **định danh đối tượng ổn định** và **tham chiếu xuyên ranh giới** mà không phụ thuộc vào cấu trúc lưu trữ nội bộ của service khác.

Ví dụ:

    Customer Service
      owns: Customer(customerId)
               |
               | customerId + hợp đồng đọc/sự kiện
               v
    Order Service
      owns: Order(orderId, customerId, shippingSnapshot)
               |
               | orderId + amount + command
               v
    Payment Service
      owns: PaymentAttempt(paymentAttemptId, orderId)

Order lưu customerId để chỉ ra **khách hàng liên quan**, không vì vậy trở thành chủ sở hữu hồ sơ Customer. Payment lưu orderId để liên hệ khoản thu với một đơn, nhưng không được tự sửa trạng thái đơn bằng truy cập database của Order.

**Nguyên tắc cốt lõi:** Mỗi ID cần một chủ thể cấp phát và một phạm vi duy nhất rõ ràng; mỗi tham chiếu cần có nguồn thẩm quyền, ngữ nghĩa vòng đời và một cách xử lý khi dữ liệu liên quan thay đổi hoặc không còn truy cập được.

### Mục tiêu học tập

Sau bài này, bạn có thể:
1. Phân biệt identity, reference, foreign key, business key, external ID, correlation ID và idempotency key.
2. Chọn chiến lược ID phù hợp với khả năng tạo dữ liệu độc lập, khả năng bảo mật và yêu cầu vận hành.
3. Thiết kế tham chiếu xuyên dịch vụ mà không áp đặt transaction hoặc JOIN xuyên database.
4. Phân tích cách kiểm tra sự tồn tại, khả năng hợp lệ và quyền truy cập của đối tượng từ service khác.
5. Xử lý xóa, hợp nhất, đổi mã, dữ liệu cũ, sự kiện trễ và tham chiếu mồ côi.
6. Thiết kế API/event contract có ID, version, tenant scope và snapshot hợp lệ.
7. Triển khai ví dụ Java/Spring và xây các bài kiểm thử về vòng đời, concurrency và bảo mật.
8. Ghi nhận quyết định kiến trúc bằng ADR và bài tập thực hành.

**Phạm vi:** “Quyền sở hữu dữ liệu” ở đây nói tới thẩm quyền quản lý trạng thái nghiệp vụ. Nó không tự động bao gồm quyền sở hữu pháp lý hay mọi nghĩa vụ bảo vệ dữ liệu, nhưng những yêu cầu bảo mật, riêng tư và xóa dữ liệu phải được đưa vào thiết kế tham chiếu khi có liên quan.

---

## 2. Những khái niệm nền tảng

### 2.1. Identity: đối tượng này là ai?

**Identity (định danh)** là dấu hiệu ổn định dùng để phân biệt một đối tượng nghiệp vụ với những đối tượng khác theo một phạm vi.

Ví dụ:
- customerId = cus_01HZY... xác định một hồ sơ khách hàng.
- orderId = ord_01HZZ... xác định một đơn hàng.
- paymentAttemptId = payatt_... xác định một lần thử thanh toán.
- reservationId = res_... xác định quyền giữ chỗ được cấp.
- tenantId = ten_... xác định phạm vi tổ chức trong hệ đa tenant.

ID có thể là chuỗi, số, UUID hoặc dạng khác. Điều quan trọng hơn định dạng là **ngữ nghĩa duy nhất, độ ổn định và hợp đồng cấp phát**.

### 2.2. Reference: mối liên hệ có ý nghĩa

**Reference (tham chiếu)** là quan hệ từ một đối tượng hoặc thông điệp tới đối tượng khác. Ví dụ Order.customerId có nghĩa “đơn hàng này có liên hệ với hồ sơ khách hàng mang ID đó” theo chính sách.

Reference không nhất thiết là một **database foreign key**. Trong cùng cơ sở dữ liệu và ranh giới sở hữu, foreign key vật lý có thể phù hợp. Xuyên service, tham chiếu thường được giữ dưới dạng scalar ID cùng hợp đồng dùng để xác nhận, truy vấn và phản ứng khi đối tượng thay đổi.

### 2.3. Database primary key không luôn là public ID

Một bảng có thể có cột id tăng dần để tối ưu lưu trữ. Nhưng public API có thể cần ID không thay đổi khi:
- Di chuyển dữ liệu sang database khác.
- Gộp hoặc tách schema.
- Nhân bản dữ liệu giữa các vùng.
- Import hồ sơ từ hệ legacy.
- Chuyển sang partition/shard mới.
- Đổi cơ chế ORM/persistence.

Nếu để mọi consumer phụ thuộc vào primary key nội bộ, quyết định thay đổi lưu trữ sẽ kéo theo thay đổi hợp đồng. Có thể dùng **public ID ổn định**, còn internal key được chọn theo nhu cầu datastore.

Ví dụ:

    internal_pk BIGINT  = 87234   (nội bộ Customer)
    customer_id VARCHAR = cus_8GK... (hợp đồng công bố)

Không phải hệ thống nào cũng bắt buộc có hai trường. Nếu khóa hiện tại đã ổn định và đáp ứng yêu cầu, có thể dùng một ID. Chỉ tách khi có lý do rõ ràng.

### 2.4. Natural key và surrogate key

**Natural key** là thuộc tính có ý nghĩa nghiệp vụ như email, số điện thoại, mã số thuế hoặc mã sản phẩm. **Surrogate key** là ID được cấp chỉ để nhận diện.

Natural key thường thay đổi hoặc có ngoại lệ:
- Khách có thể đổi email/số điện thoại.
- Email có thể chưa được xác minh hoặc dùng chung theo ngữ cảnh.
- Mã sản phẩm từ nhà cung cấp có thể được sửa.
- Một số mã doanh nghiệp có phạm vi quốc gia/loại tổ chức khác nhau.
- Một mã có thể được tái sử dụng sau một thời gian.

Vì vậy đừng mặc định email là customerId, hoặc SKU là định danh duy nhất toàn hệ thống. Có thể dùng business key để tìm kiếm, kiểm tra duy nhất theo chính sách, nhưng tham chiếu bền vững thường nên dùng một ID ổn định độc lập với thuộc tính có thể đổi.

### 2.5. Correlation ID và idempotency key là khái niệm khác

- **Business object ID:** Chỉ ra đối tượng cụ thể, như orderId.
- **Correlation ID:** Kết nối log/trace của một quy trình qua nhiều service.
- **Request ID:** Phân biệt một lần request hoặc giao dịch truyền thông.
- **Idempotency key:** Nhận diện **cùng một ý định có tác động** để chống ghi trùng qua retry.
- **Event ID:** Phân biệt một sự kiện được phát, hỗ trợ nhận diện redelivery.
- **Aggregate version:** Diễn đạt phiên bản trạng thái trong một phạm vi aggregate.

Không nên dùng traceId mới của mỗi retry làm idempotency key, hoặc dùng eventId như orderId. Các ID phục vụ những quyết định khác nhau.

---

## 3. Ai có quyền cấp phát ID?

Một thiết kế rõ cần trả lời:
- Đối tượng thuộc năng lực nào?
- Service nào có quyền tạo và tuyên bố đối tượng tồn tại?
- ID được cấp trước hay sau khi dữ liệu được ghi?
- Caller có được chọn ID không, hay chỉ gửi một key chống trùng?
- ID có duy nhất trong toàn hệ, mỗi tenant hay mỗi loại đối tượng?
- Có thể thay đổi ID sau khi tạo không?
- Khi đối tượng bị xóa, ID có được cấp lại cho đối tượng mới không?

### 3.1. Mô hình provider cấp ID

Ví dụ Order nhận lệnh tạo đơn và trả orderId:

~~~http
POST /orders
Idempotency-Key: checkout-session-88
Content-Type: application/json

{
  "customerId": "cus_123",
  "items": [
    {"productId": "prod_77", "quantity": 2}
  ]
}
~~~

~~~http
HTTP/1.1 201 Created
Location: /orders/ord_456
Content-Type: application/json

{
  "orderId": "ord_456",
  "status": "PENDING"
}
~~~

Order là chủ thể cấp và quản lý orderId; consumer dùng ID đó để gọi API hoặc liên hệ sự kiện. Nếu request bị timeout, client không tự động tạo một đơn khác, mà retry với idempotency key ổn định hoặc truy vấn theo hợp đồng.

### 3.2. Client-generated ID khi thực sự cần

Trong một số hệ thống offline-first hoặc phân tán, client có thể cần tạo ID trước để liên kết dữ liệu chưa đồng bộ. Có thể dùng UUID hoặc dạng ID đủ rộng với quy tắc cấp phát rõ.

Nhưng caller cấp ID không có nghĩa caller được tự tuyên bố đối tượng hợp lệ:
- Service sở hữu vẫn xác thực dữ liệu, quyền và trạng thái.
- Một client không thể ghi đè object của tenant khác bằng ID đoán được.
- Cùng ID nhưng nội dung khác cần xử lý conflict.
- Nếu ID có thể được tạo trước khi object tồn tại, tham chiếu phải chịu được trạng thái pending/unresolved.

### 3.3. ID có duy nhất theo phạm vi nào?

Một string "123" có thể là:
- customerId nội bộ của Tenant A.
- customerId nội bộ của Tenant B.
- orderId của một hệ khác.

Không thể đưa "123" vào một event rồi mặc định toàn hệ biết nó là đối tượng nào. Hợp đồng phải nói rõ **namespace, loại đối tượng và tenant scope** khi cần.

Một khoá logic có thể là:

    (tenantId, objectType, objectId)

Hoặc provider cấp ID duy nhất toàn cục rồi vẫn yêu cầu tenant authorization khi truy cập.

**Độ duy nhất không thay thế phân quyền.** ID toàn cục có thể phân biệt object, nhưng không chứng minh người cầm ID có quyền truy cập object.

---

## 4. Chọn kiểu ID: lợi ích và đánh đổi

| Kiểu ID | Ưu điểm | Rủi ro/cần chú ý |
|---|---|---|
| Số tăng tự động trong DB | Ngắn, dễ index, thuận tiện nội bộ | Khó cấp phát offline/đa nguồn, có thể lộ thứ tự và số lượng |
| UUID ngẫu nhiên | Dễ tạo ở nhiều nơi, xác suất va chạm rất thấp khi tạo đúng | Dài hơn số; ảnh hưởng index và hiển thị |
| UUID dựa vào thời gian/tuần tự | Có thể thuận lợi hơn cho locality và sắp xếp | Không nên suy ra bảo mật/độ đúng chỉ từ timestamp |
| ULID hoặc dạng lexicographic | Dễ đọc, thường có thành phần thời gian, sắp xếp tiện | Cần chuẩn hóa encoding và chính sách tạo cùng thời điểm |
| Snowflake-like ID | Gọn, có thể cấp phân tán bằng worker/time bits | Phụ thuộc cấu hình node/clock, rủi ro trùng nếu quản trị sai |
| Business key (email, SKU) | Dễ hiểu với người dùng | Có thể thay đổi, không luôn duy nhất, có thể là dữ liệu nhạy cảm |
| Prefixed opaque ID | Phân biệt loại đối tượng, dễ hỗ trợ/debug | Prefix không tự bảo đảm uniqueness, auth hoặc khả năng kiểm tra |

Không có một định dạng đúng cho mọi hệ thống. Tiêu chí chọn gồm:
- Có cần tạo ID độc lập khi offline hoặc nhiều vùng không?
- Ưu tiên hiệu suất index và lưu trữ tới mức nào?
- ID có lộ ra public URL không?
- Có cần thứ tự gần thời gian tạo không?
- Cấu hình generator và clock có đáng tin không?
- Kế hoạch import/merge dữ liệu có thể xảy ra không?
- Consumer có thể giữ ID lâu dài không?
- Định dạng ID có trở thành hợp đồng công khai không?

### 4.1. UUID không phải cơ chế phân quyền

Một ID ngẫu nhiên khó đoán **không thay thế** authorization. Nếu endpoint GET /orders/{orderId} không xác minh quyền theo tenant/user, người có được ID qua log, email hoặc URL vẫn có thể truy cập trái phép.

Ngược lại, ID tăng dần không phải tự nó làm hệ thống không an toàn, nhưng có thể tạo rủi ro enumeration dễ hơn nếu ứng dụng thiếu kiểm soát quyền và rate limit. Hãy bảo vệ truy cập tại service có thẩm quyền.

### 4.2. Không dùng thứ tự ID thay cho business sequence

UUID có thành phần thời gian hoặc Snowflake-like ID có thể tương quan với thời điểm tạo. Nhưng không nên dùng phép so sánh ID để quyết định:
- Event nào có hiệu lực mới nhất.
- Đơn nào được xác nhận trước theo transaction.
- Chuyển trạng thái nào được phép.
- Khoản thu nào phải được xử lý tiếp.

Thứ tự ID không thay thế aggregate version, transaction order hoặc timestamp nghiệp vụ được định nghĩa rõ. Nếu cần sequence pháp lý cho hóa đơn hoặc chứng từ, hãy quản lý sequence đó như một quy tắc riêng với phạm vi và ràng buộc thích hợp.

---

## 5. Public ID nên ổn định, opaque và có ngữ nghĩa giới hạn

Một public ID là một phần hợp đồng vì consumer có thể lưu nó lâu dài. Những cam kết cần cân nhắc:
- **Ổn định:** Không thay ID chỉ vì đổi DB hoặc chuyển shard.
- **Không tái sử dụng:** ID đã đại diện cho một object không được cấp lại cho object khác nếu consumer có thể lưu tham chiếu cũ.
- **Phạm vi duy nhất rõ:** Globally unique hay unique trong tenant/namespace.
- **Không yêu cầu parse nội dung:** Consumer không cần cắt chuỗi để suy ra region, thời gian, business state hoặc ownership.
- **Định dạng có quy tắc:** Kiểu, độ dài tối đa, ký tự hợp lệ, trường hợp chữ hoa/thường và cách encode URL.
- **Tham chiếu qua hợp đồng:** Dùng API/event được công bố, không lấy ID để query bảng nội bộ service khác.

Ví dụ prefixed ID:

    cus_01J8...
    ord_01J9...
    pay_01JA...

Prefix có thể giúp phát hiện nhầm kiểu, nhưng business logic vẫn cần xác thực đúng loại, quyền và quan hệ. Đừng dùng prefix để thay thế object type hoặc tenant trong các ngữ cảnh yêu cầu định danh đầy đủ.

### 5.1. Tránh hợp đồng dựa vào cấu trúc bên trong ID

Sai lầm:

    if (orderId.startsWith("EU-")) {
        routeToEurope();
    }

Nếu sau này provider thay chiến lược ID hoặc chuyển vùng, consumer sẽ sai.

Tốt hơn là một hợp đồng tra route hoặc metadata có ngữ nghĩa rõ, do service sở hữu hoặc routing layer quản lý. Nếu một hệ thống thực sự thiết kế region-aware ID, nó phải công bố rõ tính chất và kế hoạch tiến hóa; không để consumer tự suy từ ví dụ.

### 5.2. Chuẩn hóa biểu diễn

Tất cả các bên cần thống nhất:
- ID là string hay number?
- Có phân biệt chữ hoa và chữ thường không?
- Có dấu gạch nối được chuẩn hóa không?
- Có cho phép leading zero không?
- ID có encode/escape khi đưa vào URL/path không?
- Có được trim whitespace hay normalizing Unicode không?
- Khi serialize JSON, có nguy cơ mất độ chính xác với số nguyên lớn trong JavaScript không?

Đặc biệt với ID số 64-bit, một số môi trường JavaScript không biểu diễn chính xác mọi số nguyên lớn dưới dạng Number. Dùng string trong JSON có thể an toàn hơn nếu phạm vi số vượt giới hạn chính xác của consumer.

---

## 6. Tham chiếu xuyên dịch vụ không phải foreign key xuyên DB

Giả sử Order sở hữu database riêng, Customer sở hữu database riêng:

    Customer DB
      customer(customer_id, name, status)
            |
            | contract/customerId
            v
    Order DB
      orders(order_id, customer_id, address_snapshot)

Order.customer_id là **logical reference**, không phải foreign key có thể được database Order bảo đảm bằng constraint tới Customer DB.

Lợi ích:
- Customer có thể thay schema nội bộ mà Order không phải migrate theo.
- Hai service không cần transaction chung cho một lần ghi cục bộ.
- Có thể triển khai theo nhịp riêng khi giữ hợp đồng.
- Không ép consumer phụ thuộc trực tiếp vào trạng thái tồn tại vật lý của dữ liệu nguồn.

Đánh đổi:
- Không có FK vật lý xuyên hai database để tự ngăn mọi tham chiếu sai.
- Kiểm tra và thời điểm cập nhật cần được thiết kế ở mức ứng dụng.
- Một đối tượng nguồn có thể bị khóa, xóa hoặc hợp nhất sau khi consumer đã lưu ID.
- Dữ liệu projection và event có thể trễ.
- Phải có cách phát hiện/đối soát logical references bất thường.

### 6.1. Không dùng JOIN xuyên database cho luồng nghiệp vụ chính

Một truy vấn như:

~~~sql
SELECT *
FROM order_db.orders o
JOIN customer_db.customers c
  ON o.customer_id = c.id;
~~~

có thể chạy được trên một số hạ tầng, nhưng nếu service Order sở hữu query này như một phần công việc thường xuyên, nó đã phụ thuộc vào schema và quyền truy cập Customer.

Hướng thay thế:
- Order lưu dữ liệu snapshot cần cho nghiệp vụ đơn hàng.
- Gọi Customer API khi cần thông tin cập nhật có thẩm quyền.
- Tạo read model từ event để ghép dữ liệu phục vụ hiển thị.
- Dùng API composition trong BFF/query service cho một số màn hình.
- Dùng kho dữ liệu/báo cáo riêng cho phân tích liên miền.

Không phải mọi JOIN trong cùng một cơ sở dữ liệu đều xấu. Vấn đề là **vượt ranh giới ownership** bằng chi tiết triển khai riêng của nhóm khác.

### 6.2. Có thể dùng chung hạ tầng DB mà vẫn tách ownership

Hai service có thể dùng cùng một cụm database vật lý vì chi phí vận hành, nhưng vẫn cần schema/credential/migration và quyền ghi riêng. Nếu Order có quyền UPDATE trực tiếp bảng Customer, ranh giới logic bị phá vỡ dù sơ đồ cho thấy hai service khác nhau.

---

## 7. Kiểm tra sự tồn tại của tham chiếu: lúc nào và ở đâu?

Khi Order nhận customerId hoặc productId, có ít nhất ba câu hỏi:
1. ID có đúng **định dạng và phạm vi** không?
2. Đối tượng có **tồn tại** tại một thời điểm được xác định không?
3. Đối tượng có **đủ điều kiện nghiệp vụ** cho hành động hiện tại không?

Một GET 200 từ Customer có thể chứng minh object đang được tìm thấy và có quyền đọc theo hợp đồng, nhưng chưa chắc chứng minh khách được phép mua hàng hoặc trạng thái sẽ không đổi ngay sau đó.

### 7.1. Kiểm tra đồng bộ tại điểm ra quyết định

Khi nghiệp vụ cần câu trả lời tức thời, Order có thể gọi Customer để xác minh khách hợp lệ, hoặc Catalog để xác minh productId và chính sách mua.

Ví dụ:

    Client ---> Order.CreateOrder
                 |
                 +-- Customer.ValidatePurchasingEligibility
                 |
                 +-- Catalog.QuoteItems
                 |
                 +-- Inventory.ReserveStock
                 |
                 +-- Order ghi trạng thái và snapshot

Nhưng kiểm tra đồng bộ có TOCTOU: giữa lúc Validate và lúc Order commit, Customer có thể bị khóa, mặt hàng có thể ngừng bán hoặc reservation hết hạn. Nếu bất biến cứng đòi hiệu lực kéo dài, cần token/quyền đã cấp hoặc cơ chế reservation có phiên bản và thời hạn.

### 7.2. Xác thực sơ bộ khác quyết định có hiệu lực

Catalog có thể cung cấp ProductExists để giao diện phản hồi sớm. Nhưng Inventory mới quyết định có thể giữ hàng khi thực hiện ReserveStock. Dữ liệu danh mục đọc từ cache không được xem là bảo đảm tồn kho.

Tương tự, Customer được phép đọc thông tin profile không có nghĩa Order được tự động tạo giao dịch thanh toán thay cho Customer. Mỗi quyết định thuộc năng lực khác nhau.

### 7.3. Kiểm tra bất đồng bộ và trạng thái pending

Trong một số hệ, object có thể được tạo ở service A rồi event được gửi sang B. B có thể nhận một tham chiếu trước khi read model thấy object do event lag. Hợp đồng có thể chấp nhận trạng thái:

    REFERENCE_PENDING
       |
       +-- Resolved --> ACTIVE
       |
       +-- Timed out / invalid --> REJECTED or REVIEW_REQUIRED

Cần giới hạn chờ, retry, đối soát và owner của trạng thái. Không tự coi “chưa tìm thấy trong projection” là “object chưa từng tồn tại”.

### 7.4. Tham chiếu mồ côi (orphan reference)

Orphan reference là liên kết tới object không còn tồn tại, không còn hợp lệ hoặc không thể tìm thấy theo chính sách. Không phải mọi orphan đều là lỗi dữ liệu: một snapshot lịch sử có thể giữ ID của khách đã bị xóa, nếu được phép và có chính sách bảo vệ.

Cần phân loại:
- **Orphan không mong đợi:** Order trỏ tới customerId chưa bao giờ tồn tại; cần khôi phục/điều tra.
- **Logical deletion:** Customer đã bị vô hiệu hóa, nhưng đơn cũ cần giữ lịch sử.
- **Out-of-order propagation:** Dữ liệu nguồn đã có, projection chưa bắt kịp.
- **Merge/alias:** ID cũ được chuyển về canonical ID mới.
- **Ẩn vì authorization:** Object tồn tại nhưng caller không có quyền nhìn thấy.
- **Temporary unavailable:** Source service lỗi, không thể xác định tồn tại.

Không gom các trường hợp thành một boolean exists.

---

## 8. Các chiến lược tham chiếu và dữ liệu sao chép

### 8.1. Chỉ lưu ID

Order lưu customerId, khi cần hiển thị tên mới nhất thì gọi Customer.

Ưu điểm:
- Ít dữ liệu trùng.
- Nguồn có thẩm quyền rõ.
- Dễ thay đổi thông tin hiện tại.

Nhược điểm:
- Gọi mạng trong luồng đọc.
- Dependency unavailable làm giảm khả dụng.
- Thông tin lịch sử có thể thay đổi so với lúc giao dịch.

Phù hợp khi cần trạng thái hiện tại và latency/availability cho phép.

### 8.2. Lưu ID + snapshot nghiệp vụ

Order lưu customerId cùng shippingAddressSnapshot, productNameSnapshot, unitPriceSnapshot tại thời điểm chốt.

Ưu điểm:
- Phục vụ hóa đơn/đơn hàng lịch sử.
- Không bị thay đổi theo Customer/Catalog hiện tại.
- Đọc nhanh hơn và ít gọi liên service.

Nhược điểm:
- Phải định nghĩa thời điểm và nguồn snapshot.
- Dữ liệu nhạy cảm cần chính sách lưu giữ/xóa.
- Consumer có thể nhầm snapshot với giá trị hiện tại.

**Quan trọng:** Snapshot là một sự thật riêng, có ngữ nghĩa theo thời điểm. Khi khách đổi địa chỉ hiện tại, địa chỉ giao hàng đã chốt cho đơn cũ không mặc nhiên thay đổi nếu nghiệp vụ yêu cầu giữ nguyên lịch sử.

### 8.3. Read model hoặc materialized view

Một dịch vụ query xây projection từ CustomerUpdated, OrderCreated và các event khác:

    Customer ------ CustomerUpdated -----+
                                        |
    Order --------- OrderCreated -------+--> OrderSummary projection
                                        |
    Shipping ------ ShipmentStatus -----+

Projection là dữ liệu phục vụ đọc, thường cập nhật bất đồng bộ.

Cần công bố:
- Độ trễ có thể có.
- sourceVersion hoặc updatedAt khi hữu ích.
- Cơ chế replay/backfill.
- Duplicate và ordering.
- Trường hợp thiếu event.
- Khi nào không được dùng projection để ra quyết định có bất biến.

### 8.4. API composition

Một BFF gọi Order, Customer và Shipping rồi ghép kết quả ngay khi request đến. Cách này phù hợp một số trang cần dữ liệu mới, nhưng tăng độ trễ và phụ thuộc availability của nhiều service.

Không nên để BFF trở thành nơi tự quyết định quy tắc Payment hay quyền giữ hàng chỉ vì nó đã có dữ liệu ghép.

### 8.5. Cache

Một cache của Customer có thể chứa tên hoặc trạng thái mới nhất được quan sát. Nhưng cached state không tự bảo đảm tính mới tại thời điểm chấp nhận command. TTL, invalidation, version và nguồn chuẩn cần được định nghĩa.

---

## 9. Vòng đời đối tượng: ID có nghĩa gì sau khi xóa?

Đây là phần dễ bị bỏ sót. Một ID đã được consumer lưu có thể tồn tại lâu hơn bản ghi nguồn. Chính sách xóa cần phân biệt:
- **Deactivate / disable:** Object vẫn tồn tại nhưng không thể thực hiện một số hành vi.
- **Soft delete:** Object không còn xuất hiện trong truy vấn thông thường, vẫn có thể còn dữ liệu nội bộ.
- **Hard delete:** Dữ liệu nguồn bị loại khỏi lưu trữ theo chính sách.
- **Archive:** Chuyển dữ liệu sang vùng lưu khác; đường truy cập có thể thay đổi.
- **Merge:** Hai object được hợp nhất và một ID trở thành alias hoặc retired ID.
- **Redaction:** Một số thuộc tính nhạy cảm được xóa/ẩn nhưng identity lịch sử còn cần cho audit.
- **Pseudonymization:** Thay thông tin nhận dạng bằng biểu diễn giảm khả năng liên kết theo chính sách.

### 9.1. Không tái sử dụng ID một cách tùy tiện

Giả sử customerId=123 từng thuộc khách A, sau khi xóa được cấp lại cho khách B. Order cũ vẫn trỏ 123 và có thể bị gắn nhầm với B. Đây là lỗi toàn vẹn nghiêm trọng.

Với public ID đã công bố, chính sách thường là **không tái sử dụng** trong phạm vi mà tham chiếu cũ có thể còn tồn tại. Nếu storage cần tái sử dụng numeric internal key, hãy tách public ID hoặc có cơ chế đảm bảo không nhầm identity.

### 9.2. Tombstone

Một **tombstone** là dấu hiệu đối tượng đã bị xóa/không còn hiệu lực, có thể giữ ID và metadata tối thiểu để consumer nhận biết.

Ví dụ event:

~~~json
{
  "eventId": "evt-cus-789",
  "eventType": "CustomerDeactivated",
  "schemaVersion": 1,
  "aggregateId": "cus_123",
  "aggregateVersion": 14,
  "occurredAt": "2026-11-12T10:00:00Z",
  "data": {
    "customerId": "cus_123",
    "reasonCode": "ACCOUNT_CLOSED"
  }
}
~~~

Consumer có thể dùng event để ngừng những hành vi không được phép, đánh dấu reference stale hoặc cập nhật projection.

Tombstone không nhất thiết giữ mọi dữ liệu cá nhân. Cần thiết kế nội dung tối thiểu, thời gian lưu và quyền truy cập theo yêu cầu áp dụng.

### 9.3. Sự kiện xóa có thể đến trễ

Một projection nhận:
1. CustomerUpdated(version=13).
2. CustomerDeactivated(version=14).
3. CustomerUpdated(version=12) đến trễ.

Nếu áp dụng mù theo thứ tự đến, record có thể bị “hồi sinh”. Với event snapshot, consumer cần version guard và quy tắc tombstone; với delta, cần đảm bảo sequence hoặc replay phù hợp.

### 9.4. Quyền riêng tư và lịch sử

Một hệ thống có thể cần giữ bằng chứng đơn hàng đã bán nhưng cũng phải thực hiện yêu cầu xóa thông tin cá nhân theo nghĩa vụ áp dụng. Khi đó:
- Xác định dữ liệu nào bắt buộc giữ theo hồ sơ giao dịch và dữ liệu nào cần xóa.
- Tránh nhúng dữ liệu nhạy cảm không cần thiết trong mọi event.
- Kiểm soát snapshot, cache, search index, analytics và backup theo chính sách.
- Thiết kế sự kiện xóa/redaction và quy trình đối soát.
- Không mặc định việc xóa Customer DB là đã loại mọi bản sao ở service khác.

Đây là vấn đề phối hợp giữa kiến trúc dữ liệu, bảo mật, quyền riêng tư và quản trị vòng đời.

---

## 10. Khi hai hồ sơ được hợp nhất: canonical ID và alias

Ví dụ khách có hai hồ sơ:
- cus_A: được tạo từ website.
- cus_B: được import từ cửa hàng.
Sau khi xác minh là cùng một người, Customer muốn hợp nhất vào cus_A.

Nếu Order, Support và Loyalty đều đang tham chiếu cus_B, đổi ngay mọi ID trong mọi database là một giao dịch phân tán khó kiểm soát.

Một chiến lược:
1. Customer quyết định canonical ID = cus_A.
2. Duy trì alias/tombstone chuyển cus_B → cus_A trong một thời hạn được công bố.
3. Công bố sự kiện CustomerMerged với sourceId, targetId, version và ngữ nghĩa.
4. Consumer xử lý migration hoặc giữ historical reference theo mục đích.
5. API tra cứu ID cũ trả kết quả phù hợp (alias/redirect/retired) theo hợp đồng.
6. Theo dõi consumer chưa cập nhật và lên kế hoạch loại alias.
7. Không để ID cũ được cấp lại cho người khác.

### 10.1. Tránh vòng alias

Nếu hệ thống cho cus_A → cus_B và cus_B → cus_A, phép phân giải có thể lặp vô hạn. Owner cần ngăn vòng, kiểm soát độ dài chuỗi alias, version và transaction khi merge.

### 10.2. Lịch sử không luôn phải rewrite

Một hóa đơn đã phát hành cho thông tin tại thời điểm giao dịch có thể cần giữ nguyên snapshot. CustomerMerged không tự động cho phép sửa toàn bộ chứng từ lịch sử. Consumer nên xác định:
- Dữ liệu hiện tại cần trỏ canonical ID.
- Dữ liệu lịch sử giữ identifier cũ hay gắn mapping hỗ trợ tra cứu.
- Chính sách audit, pháp lý và quyền riêng tư áp dụng.

### 10.3. ID có thể mang nghĩa theo tổ chức

Một người có thể có nhiều customerId trong các tenant khác nhau theo ranh giới quản lý. Hợp nhất xuyên tenant có thể không hợp lệ hoặc bị cấm. Không suy rằng hai email trùng nhau là cùng một identity được phép merge. Quyết định hợp nhất phải nằm tại owner có thẩm quyền và tuân thủ chính sách.

---

## 11. Cross-service reference và tính nhất quán cuối cùng

Một số liên kết chỉ có thể hội tụ dần vì hệ thống phân tán.

Ví dụ:
1. Customer tạo hồ sơ cus_123 và commit.
2. Event CustomerCreated được ghi vào outbox.
3. Broker truyền event đến Order projection sau vài giây.
4. Trong lúc đó, người dùng gọi CreateOrder với customerId=cus_123.

Order projection chưa có cus_123 không đồng nghĩa Customer chưa tạo hồ sơ. Có các lựa chọn:
- Gọi Customer API có thẩm quyền để kiểm tra.
- Chấp nhận order=PENDING_CUSTOMER_VALIDATION theo chính sách.
- Dùng token/receipt tạo hồ sơ có giá trị xác minh.
- Từ chối tạm thời và cho caller retry an toàn, nếu hợp đồng cho phép.
- Chọn read-your-writes/stronger consistency cho đường cụ thể khi cần.

### 11.1. Version và nguồn sự thật

Nếu Consumer giữ CustomerSnapshot với version=7 rồi nhận CustomerUpdated(version=6), nó không nên ghi lùi state.

~~~sql
UPDATE customer_projection
SET display_name = :name,
    source_version = :version
WHERE customer_id = :customerId
  AND source_version < :version;
~~~

Ví dụ này phù hợp với snapshot event. Khi event mang delta (thêm điểm, trừ số lượng), bỏ qua một version có thể làm mất phép biến đổi. Contract phải nêu cách xử lý đúng loại event.

### 11.2. Transactional outbox và referential events

Nếu Customer commit một object rồi phát CustomerCreated bằng hai thao tác độc lập, ứng dụng có thể crash sau commit nhưng trước publish. Order projection sẽ không bao giờ thấy object nếu không có cơ chế khôi phục.

Outbox trong transaction cục bộ của Customer:
- Ghi Customer.
- Ghi Outbox event CustomerCreated cùng transaction.
- Commit.
- Publisher gửi message từ outbox.
- Consumer xử lý duplicate bằng eventId/unique constraint.

Outbox không làm Order thấy Customer ngay lập tức, nhưng giúp tránh đánh mất ý định công bố sự kiện sau commit.

### 11.3. Anti-entropy và reconciliation

Khi có projection/reference, nên có cơ chế định kỳ:
- Đối chiếu version/checkpoint.
- Phát hiện event thiếu, DLQ hoặc consumer lag.
- Quét logical references cần xác minh.
- Replay/backfill theo nguồn có thẩm quyền.
- Ghi nhận trạng thái unresolved và owner xử lý.
- Không tự xóa dữ liệu lịch sử chỉ vì một lần lookup trả 404 tạm thời.

Reconciliation là lớp phục hồi; với bất biến cứng như không bán vượt tồn kho, nó không thay thế quyết định nguyên tử tại service sở hữu.

---

## 12. Bảo mật: ID không phải giấy phép truy cập

Một ID có thể lộ qua URL, sự kiện, email, log hoặc client. Mọi endpoint dùng ID để truy vấn hay sửa tài nguyên phải kiểm tra quyền trong **ngữ cảnh caller và tenant**.

### 12.1. IDOR và Broken Object Level Authorization

Ví dụ:

~~~http
GET /orders/ord_123
Authorization: Bearer <user-token>
~~~

Nếu service chỉ kiểm tra token hợp lệ rồi trả mọi đơn theo orderId, người dùng có thể đọc đơn của người khác khi biết ID. Đây là lỗi cấp quyền theo đối tượng.

Service Order cần kiểm tra:
- Caller là ai?
- Caller thuộc tenant nào?
- Order có thuộc tenant hoặc phạm vi được phép không?
- Caller có quyền xem loại dữ liệu và trạng thái này không?
- Có quy tắc đặc biệt cho nhân viên hỗ trợ hoặc delegated access không?

**Không dùng ID khó đoán để thay thế những kiểm tra này.**

### 12.2. Tenant-scoped lookup

Một truy vấn ví dụ:

~~~sql
SELECT order_id, status, customer_id
FROM orders
WHERE order_id = :orderId
  AND tenant_id = :authenticatedTenantId;
~~~

Các thao tác cập nhật cũng nên giới hạn theo tenant/resource. Tenant ID trong request body không được mặc định là đáng tin nếu danh tính người gọi chỉ được xác minh theo ngữ cảnh khác.

Khi tham chiếu Customer từ Order, cần đảm bảo customerId thuộc phạm vi tenant được phép theo hợp đồng Customer; nếu không, có thể tạo liên kết xuyên tenant trái quyền.

### 12.3. Không suy quyền theo chuỗi ID

Sai:

    if (customerId.startsWith("vip_")) grantDiscount();

Prefix không chứng minh khách là VIP. Quyền lợi phải được xác nhận từ chính sách/năng lực sở hữu với phiên bản và thời điểm hiệu lực phù hợp.

Tương tự, một role hoặc tenant có thể thay đổi sau khi ID được lưu. Authorization phải được thực thi ở thời điểm hành động, không dựa duy nhất trên quyền đã đọc từ lâu.

### 12.4. Không rò PII qua ID

Email, số điện thoại, số căn cước hoặc ngày sinh có thể là định danh tự nhiên nhưng đồng thời là dữ liệu nhạy cảm. Dùng chúng trực tiếp làm object ID trong URL/log/event làm tăng phạm vi lộ dữ liệu. Có thể cấp opaque ID và giữ business key ở owner với chính sách truy cập hạn chế.

### 12.5. Confused deputy trong service-to-service

Order gọi Customer để lấy dữ liệu thay mặt người dùng. Customer không được tin rằng “Order là service nội bộ nên mọi customerId đều được phép”. Cần xác thực service identity và phân quyền theo use case, có thể có end-user context hoặc delegated authorization được công bố.

---

## 13. Đối tượng nào thật sự cần được tham chiếu?

Không phải mọi bảng và mọi entity đều cần global public ID.

Các câu hỏi:
- Bên ngoài có cần giữ liên kết ổn định tới object này không?
- Object có vòng đời nghiệp vụ độc lập không?
- Có cần API truy vấn theo ID không?
- Một object khác có quyền sở hữu dữ liệu của nó không?
- Nếu service chuyển storage, external reference có cần giữ nguyên không?

Ví dụ:
- Customer, Order, PaymentAttempt, Reservation thường có identity để tích hợp.
- Một dòng order line có thể có ID nội bộ hoặc identity trong phạm vi Order; chỉ cần global ID khi có use case bên ngoài truy cập riêng.
- Một bảng join thuần túy không nhất thiết cần public ID.
- Một snapshot địa chỉ trong đơn có thể là value object, không phải reference tới hồ sơ địa chỉ hiện tại.
- Một cấu hình tạm thời hoặc cache entry có thể không có identity nghiệp vụ bền vững.

**Đừng phát minh global ID cho mọi row chỉ để “microservice hóa”**. Chọn identity theo bounded context và vòng đời.

### 13.1. Value object và entity

Một địa chỉ giao hàng đã chốt có thể là value object nằm trong Order, được xác định bằng các trường nội dung và thời điểm chốt. Một Customer là entity có identity ổn định dù đổi tên.

Nhầm hai khái niệm dẫn tới tham chiếu không cần thiết: Order cứ trỏ tới Customer.currentAddressId rồi khi khách đổi địa chỉ, hóa đơn cũ cũng đổi theo. Nếu cần giữ lịch sử, hãy chụp địa chỉ có hiệu lực cho đơn.

### 13.2. Composite ID

Một enrollment có thể được định danh theo (tenantId, studentId, courseId, cohortId). Nếu tổ chức coi một lần ghi danh là entity có vòng đời riêng, một enrollmentId ổn định có thể đơn giản hóa tham chiếu khi hủy/đăng ký lại. Dù chọn gì, uniqueness phải được cưỡng chế theo **phạm vi nghiệp vụ**, không chỉ theo khả năng tạo random ID.

---

## 14. API contract cho tham chiếu xuyên service

Hợp đồng không chỉ công bố trường id là string. Nó cần nêu:
- ID được cấp khi nào và thuộc nguồn nào.
- Phạm vi uniqueness.
- Định dạng và chính sách thay đổi định dạng.
- Trạng thái object có thể truy vấn và ý nghĩa 404/403/410.
- Kết quả khi object bị merge/deactivate.
- Thời hạn tồn tại của alias.
- Các hành động được phép khi một reference đang pending.
- Idempotency và request identity.
- Quy tắc tenant authorization.
- Khả năng trả dữ liệu stale hoặc snapshot và cách nhận biết.

### 14.1. Không mặc định 404 là không từng tồn tại

Một API có thể trả 404 khi:
- Object thực sự không có.
- Object đã bị xóa mềm.
- Caller không được biết object tồn tại.
- Dữ liệu chưa hội tụ ở một read model.
- URL sai namespace/version.
- Instance hiện không có dữ liệu do phân vùng/routing.

Hợp đồng cần xác định cách client xử lý và khi nào có thể tra trạng thái có thẩm quyền. Nếu vì bảo mật cần 404 thay cho 403 để không tiết lộ sự tồn tại, không nên yêu cầu consumer suy ra dữ liệu nguồn đã bị xóa.

### 14.2. 410 Gone và alias

Một API có thể chọn 410 Gone cho tài nguyên đã bị retired và không còn khả dụng, hoặc cung cấp canonicalId/redirect khi merge. Nhưng ý nghĩa status code phải nhất quán với chính sách bảo mật và API; không phải mọi service đều phải dùng 410.

Ví dụ response minh họa (khi caller được quyền biết alias):

~~~json
{
  "requestedCustomerId": "cus_old",
  "canonicalCustomerId": "cus_new",
  "resolution": "MERGED"
}
~~~

Consumer nên cập nhật tham chiếu theo chính sách, tránh chuỗi redirect vô hạn và không tự suy rằng hai object khác tenant có thể được hợp nhất.

### 14.3. Tránh tạo chatty reference validation

Nếu một lệnh tạo đơn có 100 order lines, mỗi line gọi Catalog một request riêng để xác minh productId, latency và tải sẽ tăng. Khi phù hợp, contract có thể hỗ trợ **batch validation/quote** theo danh sách ID với ngữ nghĩa kết quả từng item, version và chính sách partial failure.

Bảo đảm của batch phải được công bố: kết quả là snapshot tại một thời điểm hay các item có thể được kiểm tra ở các thời điểm khác nhau? Nếu cần một báo giá có tính nguyên tử theo giỏ hàng, nên có command QuoteCart/ReserveItems phù hợp thay vì tự ghép 100 lần đọc.

---

## 15. Event contract và identity

Một integration event tốt cung cấp định danh đủ để consumer hiểu sự thật:

~~~json
{
  "eventId": "evt-ord-001",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "aggregateId": "ord_456",
  "aggregateVersion": 8,
  "occurredAt": "2026-11-12T09:55:00Z",
  "correlationId": "checkout_456",
  "data": {
    "orderId": "ord_456",
    "customerId": "cus_123",
    "paymentAttemptId": "payatt_789"
  }
}
~~~

Những ID có nghĩa:
- eventId: nhận biết message trùng.
- aggregateId/version: theo dõi trạng thái Order và thứ tự hợp lệ theo aggregate.
- orderId/customerId/paymentAttemptId: tham chiếu nghiệp vụ.
- correlationId: hỗ trợ tracing workflow.
- schemaVersion: khả năng giải mã hợp đồng, không thay thế aggregateVersion.

### 15.1. Quy tắc delivery

Với at-least-once delivery, consumer có thể nhận một event nhiều lần. Consumer cần:
- Dedupe bằng eventId trong phạm vi phù hợp.
- Xử lý version hoặc thứ tự.
- Không tạo hai shipping requests cho cùng order nếu nghiệp vụ không cho phép.
- Commit trạng thái consumer và marker đã xử lý trong transaction cục bộ khi khả thi.
- Có DLQ, replay hoặc đối soát với source of truth.

Nếu có hai event cùng aggregateId nhưng khác version, đừng dùng eventId để kết luận event nào mới hơn. Mỗi ID có vai trò riêng.

### 15.2. Định danh qua nhiều lần chuyển tiếp

Một message do adapter hoặc integration layer chuyển đổi có thể mang originalEventId và newEventId. Hợp đồng phải quy định dedupe dựa trên ID nào, và liệu một lần chuyển đổi có tạo event nghiệp vụ mới hay chỉ là representation của sự kiện nguồn.

Không tùy tiện tái sử dụng eventId của event hoàn toàn mới nếu nó biểu diễn sự thật khác.

### 15.3. Event payload tối thiểu

Không phải event nào cũng cần full Customer. Việc nhúng toàn bộ profile làm lan rộng PII, tạo nhiều consumer phụ thuộc schema và tăng chi phí. Chỉ đưa các trường đúng use case đã được chấp thuận; consumer cần thêm có thể gọi API hay đăng ký một projection phù hợp.

---

## 16. Idempotency và create-with-reference

Một tình huống khó:

    Client POST CreateOrder(customerId=cus_123)
    Order tạo ord_456 và commit
    Response bị mất do timeout
    Client retry POST CreateOrder(customerId=cus_123)

Nếu Order tạo một orderId mới cho lần retry, có thể có hai đơn độc lập. Do đó CreateOrder cần nhận diện cùng một **ý định** bằng idempotency key hoặc business key phù hợp.

### 16.1. Sự khác biệt giữa orderId và idempotency key

- orderId nhận diện đối tượng đơn hàng sau khi được tạo.
- idempotency key nhận diện yêu cầu CreateOrder có thể được gửi nhiều lần vì mạng lỗi.

Cùng idempotency key/cùng payload nên trả lại orderId hoặc trạng thái đã lưu theo hợp đồng. Cùng key với payload khác cần bị từ chối hoặc xử lý conflict, không tự coi là cùng intent.

Một transaction có thể:
1. Ghi idempotency request record với uniqueness.
2. Tạo Order và lấy orderId.
3. Ghi kết quả cùng transaction.
4. Commit.
5. Trả phản hồi.

Hai request cạnh tranh phải được bảo vệ bởi uniqueness/locking phù hợp; một phép SELECT rồi INSERT thông thường chưa đủ.

### 16.2. Caller-generated orderId cũng cần validation

Nếu client gửi orderId tự tạo, vẫn phải có constraint duy nhất và xác minh tenant/ownership. Một ID đã dùng không được ghi đè record khác chỉ vì request có cùng ID.

### 16.3. External provider reference

Payment có thể có:
- paymentAttemptId của Payment.
- providerPaymentId do cổng thanh toán cấp.
- orderId liên hệ đơn.
- idempotency key của command.

Không nên dùng providerPaymentId làm public business ID chính của Payment nếu mục tiêu là thay provider mà không ảnh hưởng consumer. Có thể lưu mapping providerPaymentId ↔ paymentAttemptId trong Payment; các service khác phụ thuộc paymentAttemptId và hợp đồng trạng thái nghiệp vụ.

---

## 17. Transaction và tính đúng đắn khi tạo reference

Giả sử Order cần tạo đơn trỏ tới Customer và InventoryReservation.

**Không có transaction ACID tự động xuyên mọi service**. Một transaction trong Order chỉ bảo vệ dữ liệu Order; nó không khóa trạng thái Customer hoặc reservation ở service khác.

Các lựa chọn:
- Kiểm tra eligibility đồng bộ rồi tạo Order nếu rủi ro thay đổi chấp nhận được.
- Lấy token/quote/reservation có hiệu lực đủ lâu và xác minh ở thời điểm sử dụng.
- Tạo Order ở trạng thái PENDING rồi chạy saga/tiến trình xác nhận.
- Gom những bất biến bắt buộc nguyên tử vào cùng ranh giới nghiệp vụ nếu thực sự cần.
- Thiết kế bù trừ và reconciliation khi một bước thành công, bước sau thất bại.

### 17.1. Một saga đặt hàng

    Order: CREATE PENDING
       |
       +-- Inventory.Reserve(orderId)
       |      -> reservationId
       |
       +-- Payment.Charge(orderId)
       |      -> paymentAttemptId
       |
       +-- Order.CONFIRMED / REJECTED / PENDING_RECONCILIATION

Mỗi service có thẩm quyền đối với dữ liệu của mình:
- Inventory quyết định reservationId có hiệu lực hay không.
- Payment quyết định paymentAttemptId đã thu tiền chưa.
- Order quyết định trạng thái Order từ các kết quả có thẩm quyền.

Nếu Payment timeout, Order không thể suy ra “không tồn tại paymentAttempt”. Nó cần tra theo operation ID hoặc idempotency key trước khi thử một lệnh mới.

### 17.2. Release không phải xóa reference tùy ý

Khi Order bị hủy, nó gửi ReleaseReservation với reservationId/idempotency key. Inventory kiểm tra trạng thái và thực hiện release tối đa một lần theo policy; Order không sửa trực tiếp bảng stock hoặc đặt reservationId null rồi xem như hàng đã được trả.

### 17.3. Race khi đối tượng nguồn bị vô hiệu hóa

Customer được đánh dấu SUSPENDED ngay sau khi Order xác minh. Có thể có:
- Order đã được chấp nhận hợp lệ trước mốc khóa và vẫn tiếp tục theo chính sách.
- Order phải dừng nếu khóa xảy ra trước bước xác nhận cuối.
- Một yêu cầu cancel/compensate được kích hoạt bởi CustomerSuspended event.

Hợp đồng phải định nghĩa **mốc thời gian quyết định và nguồn chứng cứ**. Không thể chỉ nói “Customer phải active” mà không nêu active tại thời điểm nào, trong suốt bao lâu và ai chịu trách nhiệm khi trạng thái thay đổi.

---

## 18. Java/Spring: typed IDs và boundary mapping

Dùng mọi ID như String có thể gây nhầm:

    repository.findCustomerById(orderId);
    paymentService.refund(reservationId);

Hai dòng trên có thể vẫn compile dù định danh sai loại. Có thể giới thiệu value objects hoặc wrapper types để tăng độ an toàn.

Ví dụ Java record:

~~~java
public record CustomerId(String value) {
    public CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("CustomerId required");
        }
    }
}

public record OrderId(String value) {
    public OrderId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("OrderId required");
        }
    }
}
~~~

Đây là minh họa typed IDs, chưa có kiểm tra định dạng và namespace đầy đủ. Validation cụ thể thuộc hợp đồng của từng ID.

### 18.1. Domain model chỉ lưu tham chiếu hợp lệ

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final ShippingAddressSnapshot shippingAddress;
    private OrderStatus status;

    public Order(
            OrderId id,
            CustomerId customerId,
            ShippingAddressSnapshot address) {
        this.id = id;
        this.customerId = customerId;
        this.shippingAddress = address;
        this.status = OrderStatus.PENDING;
    }
}
~~~

Order không cần import JPA entity Customer từ repository của Customer. Nếu Order muốn xác minh eligibility, application service dùng client adapter theo contract:

~~~java
public interface CustomerEligibilityPort {
    EligibilityResult checkCanPurchase(
        TenantId tenantId,
        CustomerId customerId,
        PurchaseContext context
    );
}
~~~

Như vậy domain model không phụ thuộc persistence schema của service ngoài.

### 18.2. Không tự động dùng @ManyToOne xuyên service

Trong cùng service có một database, JPA @ManyToOne có thể mô tả quan hệ cục bộ. Nhưng nếu Customer là service độc lập, Order entity không nên dùng @ManyToOne để tự động JOIN bảng Customer.

Một cách đơn giản hơn:

~~~java
@Entity
@Table(name = "orders")
public class OrderJpaEntity {
    @Id
    private String orderId;

    @Column(nullable = false)
    private String customerId;

    @Column(nullable = false)
    private String tenantId;
}
~~~

Application adapter chuyển String sang typed IDs khi bước vào domain. Đường đọc thông tin Customer dùng API/contract rõ thay vì JPA lazy loading qua database khác.

### 18.3. REST controller và quyền truy cập

Ví dụ giả mã:

~~~java
@GetMapping("/orders/{orderId}")
public OrderResponse getOrder(
        @PathVariable String orderId,
        Authentication authentication) {

    TenantId tenant = tenantFromAuthenticatedContext(authentication);
    OrderId id = new OrderId(orderId);

    Order order = orderApplication.getAuthorizedOrder(tenant, id, authentication);
    return OrderResponse.from(order);
}
~~~

Tên hàm là ví dụ, không phải API Spring có sẵn toàn bộ. Điểm cốt lõi là service phải kiểm tra tenant/resource authorization ở đường xử lý có thẩm quyền, không chỉ parse một ID hợp lệ.

### 18.4. Data access tenant-scoped

~~~sql
SELECT *
FROM orders
WHERE tenant_id = :authenticatedTenantId
  AND order_id = :orderId;
~~~

Ngay cả với ID ngẫu nhiên không đoán được, vẫn cần kiểm tra quyền. Những lệnh UPDATE cũng phải giới hạn phạm vi tenant và trạng thái hợp lệ ở điểm ghi.

---

## 19. Event version và trạng thái xóa trong Java consumer

Một consumer projection có thể nhận CustomerUpdated hoặc CustomerDeactivated. Cần tách:
- Event ID để nhận diện gửi trùng.
- Aggregate ID để chọn đúng bản ghi.
- Aggregate version để tránh dữ liệu cũ ghi đè.
- Event type/schema version để giải mã hành vi.

Mã giả transaction:

~~~java
@Transactional
public void consume(CustomerEvent event) {
    if (processedEventRepository.exists(event.eventId())) {
        return;
    }

    CustomerProjection current =
        projectionRepository.find(event.customerId());

    if (current == null || event.aggregateVersion() > current.version()) {
        projectionRepository.apply(event);
    }

    processedEventRepository.insert(event.eventId());
}
~~~

Mã này chỉ minh họa trường hợp **event mang trạng thái đầy đủ** và kiểm tra uniqueness ở database được thực hiện đúng. Nếu chỉ SELECT exists rồi INSERT mà không có unique constraint, hai consumer cạnh tranh có thể cùng áp dụng effect. Với delta event, một version lớn hơn không nhất thiết cho phép bỏ qua các version thiếu.

Nếu có tombstone và event cũ đến sau, phải giữ version/tombstone logic phù hợp để không hồi sinh object đã bị loại.

---

## 20. Thay đổi ID và hợp đồng phiên bản

Định dạng ID là một phần của hợp đồng. Ví dụ public API v1 dùng ID numeric, v2 muốn dùng opaque string. Một sự thay đổi trực tiếp từ:

~~~json
{"orderId": 123456789}
~~~

sang:

~~~json
{"orderId": "ord_01J9..."}
~~~

có thể phá vỡ consumer vì kiểu, parser, database mapping, sorting và giả định unique scope khác nhau.

Một kế hoạch chuyển đổi:
1. **Expand:** Provider có thể công bố ID mới song song ID cũ hoặc hỗ trợ lookup cả hai, với ngữ nghĩa rõ.
2. **Migrate:** Consumer cập nhật lưu/đọc ID mới, kiểm thử cùng dữ liệu cũ và mới.
3. **Reconcile:** Đối chiếu mapping oldId ↔ newId, xử lý alias, duplicate và dữ liệu lịch sử.
4. **Contract:** Loại đường cũ sau thời hạn hỗ trợ và bằng chứng consumer đã chuyển.
5. **Prevent reuse:** Không cấp lại ID cũ nếu reference lịch sử còn tồn tại.

Không tự diễn giải ID mới bằng cách cắt chuỗi nếu provider chưa cam kết định dạng nội bộ. Có thể cung cấp một API ResolveIdentifier khi việc ánh xạ cần tồn tại dài hạn.

### 20.1. Mã hiển thị cho người dùng

Một order có thể có:
- orderId opaque: định danh tích hợp ổn định.
- orderNumber: mã hiển thị ngắn, dễ đọc/tra cứu ở tổng đài.

Hai giá trị có thể khác:
- orderNumber có thể chứa tiền tố theo năm, điểm bán hoặc tenant.
- Có thể cần phát lại/định dạng lại số hiển thị nhưng không đổi orderId.
- orderNumber có thể không duy nhất toàn hệ, chỉ duy nhất trong một tenant/năm.

Hãy công bố phạm vi và mục đích. Không dùng orderNumber để tham chiếu xuyên service nếu nó có thể thay đổi hoặc bị tái sử dụng theo chính sách.

### 20.2. Hợp nhất hệ thống legacy

Khi import hai hệ đều có customerId=42, cần namespace:

    (sourceSystem=A, legacyId=42) -> cus_A
    (sourceSystem=B, legacyId=42) -> cus_B

Không được dùng trực tiếp giá trị 42 để hợp nhất bản ghi. Một bảng external identifier mapping có owner và uniqueness rõ có thể giữ liên kết:

    external_system
    external_id
    canonical_customer_id
    valid_from
    valid_to

Mapping cần bảo vệ quyền, audit và chính sách thay đổi; không biến thành nơi mọi service tự ý sửa canonical IDs.

---

## 21. Observability và đối soát tham chiếu

Một kiến trúc có nhiều logical references cần theo dõi không chỉ latency HTTP mà cả **chất lượng liên kết dữ liệu**.

Các metric gợi ý:

| Metric/sự kiện | Ý nghĩa |
|---|---|
| Unknown reference count | Số ID không phân giải được theo nguồn chuẩn |
| Reference validation failures | Định dạng/phạm vi/trạng thái không hợp lệ |
| Pending reference age | Một tham chiếu chờ xác minh bao lâu |
| Orphan references by reason | Phân biệt deleted, missing, unauthorized, stale projection |
| Alias resolution count | Số lần phải chuyển ID cũ sang canonical ID |
| ID conflict/collision errors | Các trường hợp trùng ID hoặc scope sai |
| Cross-tenant reference rejections | Phát hiện liên kết vượt tenant |
| Projection lag và source version gap | Độ trễ/thiếu sự kiện |
| Event duplicate/out-of-order counts | Chất lượng luồng thông điệp |
| Reconciliation backlog | Số record chờ đối soát |
| Event/tombstone processing failures | Nguy cơ hồi sinh dữ liệu đã xóa |
| API lookup p95/p99 và timeout | Tác động của reference validation lên latency |
| Idempotency hit/conflict | Phát hiện retry và request key sai |
| Privacy deletion propagation lag | Độ trễ xử lý bản sao cần xóa/redact |

### 21.1. Không ghi PII vào log chỉ để dễ tìm

Một log như:

    Failed to resolve customer email abc@example.com

có thể làm lan thông tin nhạy cảm sang hệ logs. Dùng opaque ID/correlationId và lý do mã hóa, với phân quyền log phù hợp. Khi thực sự cần dữ liệu nhạy cảm để điều tra, phải theo quy trình được phép.

### 21.2. Runbook cho reference không phân giải được

1. Xác định owner của object ID và tenant scope.
2. Kiểm tra ID có đúng namespace/định dạng không.
3. Tra source-of-truth qua API/đường quản trị có thẩm quyền.
4. Phân biệt not found, deleted, merged, unauthorized và temporary unavailable.
5. Kiểm tra version, event lag, DLQ hoặc outbox backlog.
6. Nếu có alias, phân giải canonical ID theo chính sách.
7. Replay/backfill projection nếu thiếu sự kiện.
8. Nếu lỗi do client hoặc dữ liệu nhập, trả kết quả theo hợp đồng và audit.
9. Không UPDATE trực tiếp database owner khác để “sửa tạm” thiếu reference.

---

## 22. Các lỗi thiết kế thường gặp

**Lỗi 1 — Dùng primary key database nội bộ làm giao diện ổn định vô điều kiện.** Khi migrate dữ liệu hoặc merge hệ thống, consumer có thể mất tham chiếu. Cân nhắc public ID độc lập nếu vòng đời đòi hỏi.

**Lỗi 2 — Dùng email hoặc số điện thoại làm identity bất biến.** Người dùng đổi số hoặc email, dẫn đến liên kết sai hoặc lộ PII. Dùng opaque ID với business key riêng khi phù hợp.

**Lỗi 3 — Đưa foreign key xuyên service vào database.** Tạo quyền truy cập chéo và coupling schema/transaction. Dùng logical reference và hợp đồng có thẩm quyền.

**Lỗi 4 — Không có tenant scope.** Hai tenant cùng local ID hoặc một request tham chiếu khách tenant khác. Kiểm tra tenant cùng ID trong cả query và command.

**Lỗi 5 — UUID được xem là bảo mật.** ID khó đoán không thay thế object-level authorization, scope và rate limit.

**Lỗi 6 — Lưu bản GET cũ rồi coi là quyết định mới nhất.** Cache/projection có thể trễ; cần kiểm tra với owner ở điểm có bất biến hoặc dùng reservation/quote hợp lệ.

**Lỗi 7 — Xóa nguồn mà không thiết kế consumer.** Reference mồ côi, projection không xóa, PII tồn tại ở bản sao. Cần lifecycle contract và propagation.

**Lỗi 8 — Tái sử dụng ID cũ.** Một Order lịch sử bị liên kết với người mới. Tránh tái cấp ID công khai trong phạm vi tham chiếu còn tồn tại.

**Lỗi 9 — Merge bằng cách đổi toàn bộ ID không có mapping.** Có thể mất lịch sử và phá vỡ consumers. Cần canonical ID, alias, migration và audit.

**Lỗi 10 — Để consumer parse ID đoán region hoặc business state.** Vi phạm opacity; thay generator hoặc shard sẽ phá vỡ logic.

**Lỗi 11 — Tự join bảng xuyên schema của các nhóm.** Provider không thể đổi lưu trữ độc lập. Dùng API/read model hoặc kho phân tích.

**Lỗi 12 — Dùng traceId hoặc eventId làm idempotency key mới cho mỗi retry.** Có thể tạo side effect trùng. ID phải theo đúng mục đích.

**Lỗi 13 — Bỏ qua event ordering.** Một CustomerUpdated cũ đến sau CustomerDeactivated làm projection sống lại. Dùng version và tombstone semantics.

**Lỗi 14 — Mọi service cùng “sở hữu” Customer.** Không có nguồn sự thật cho trạng thái hiện tại. Tách snapshot/hồ sơ hiện tại và quyền ghi rõ ràng.

**Lỗi 15 — Mỗi object nhỏ đều có global ID.** Tăng complexity, contract và chi phí vận hành mà không có use case. Chỉ cấp public ID khi cần vòng đời độc lập.

**Lỗi 16 — 404 được hiểu là đối tượng chắc chắn không tồn tại.** Có thể là thiếu quyền, xóa mềm, projection trễ hoặc lỗi tầng dữ liệu. Đọc đúng hợp đồng.

**Lỗi 17 — Reference validation gọi tuần tự hàng trăm API.** Tạo chatty network và kéo dài latency. Dùng batch/quote/reservation hoặc read model theo tính đúng đắn.

**Lỗi 18 — Hợp đồng schema có ID nhưng không có lifecycle.** Không biết khi merge/delete/disable sẽ phát event nào và consumer phải phản ứng ra sao.

---

## 23. Quy trình thiết kế tham chiếu mới

### Bước 1 — Xác định object và ownership

Viết một câu: “Customer Service là nguồn sự thật của hồ sơ khách hiện tại; Order Service sở hữu đơn và lưu customerId để liên hệ”.

### Bước 2 — Xác định identity contract

ID có kiểu gì, duy nhất trong phạm vi nào, được cấp bởi ai, có được client tạo không, có ổn định qua migration không và có bao giờ được tái sử dụng không?

### Bước 3 — Xác định loại dữ liệu ở consumer

Consumer chỉ giữ ID, snapshot lịch sử, projection hay kết hợp? Những trường nào là hiện tại, những trường nào cố định tại thời điểm giao dịch?

### Bước 4 — Xác định điều kiện sử dụng reference

Tồn tại có đủ không? Cần active, eligible, paid, not-deleted hay một quyền có thời hạn? Ai kiểm tra cuối cùng, tại thời điểm nào?

### Bước 5 — Thiết kế khi source thay đổi

Object bị disable/delete/merge thì consumer làm gì? Có event, tombstone, alias hoặc status lookup không? Có thời hạn hội tụ và đối soát không?

### Bước 6 — Thiết kế authorization

Dùng tenant/user/service identity, không dựa vào ID khó đoán. Ngăn cross-tenant reference và truy cập object không thuộc quyền.

### Bước 7 — Thiết kế retry/idempotency

Khi tạo object hoặc gọi command có reference mà timeout, caller có thể tra cứu kết quả không? Có key ổn định và unique constraint không?

### Bước 8 — Chọn mức nhất quán

Bất biến cứng cần owner quyết định hoặc reservation/quote. Màn hình hiển thị có thể dùng projection trễ nếu UX/contract chấp nhận.

### Bước 9 — Định nghĩa sự kiện và phiên bản

Ghi eventId, aggregateId, version, schema version, delivery, replay, ordering và xử lý duplicate. Không gửi PII không cần thiết.

### Bước 10 — Kiểm thử và vận hành

Thử ID mồ côi, xóa, merge, cross-tenant, replay cũ, provider timeout, retry đồng thời, migration và đối soát. Theo dõi metric liên quan.

---

## 24. Bài tập thực hành: hệ thống đặt vé sự kiện

Một nền tảng có bốn năng lực:
- **Account:** Sở hữu hồ sơ người dùng và trạng thái tài khoản.
- **EventCatalog:** Sở hữu sự kiện, suất diễn và thông tin mô tả hiện tại.
- **Reservation:** Sở hữu việc giữ chỗ và số ghế có thể cấp.
- **Ticketing:** Sở hữu vé đã phát hành và trạng thái hiệu lực của vé.

Bài toán:
- User có thể đổi email.
- Một khách có thể có tài khoản từ hai hệ legacy cần hợp nhất sau.
- Một suất diễn có ID nội bộ tăng dần trong mỗi tenant.
- Một số vé phát hành trước khi cập nhật projection Account tới Ticketing.
- Một event UserDeactivated có thể đến sau event UserUpdated.
- Account có thể bị xóa theo yêu cầu riêng tư, nhưng lịch sử vé cần tuân thủ chính sách lưu giữ.
- Client có thể retry CreateReservation vì timeout.
- Đội EventCatalog muốn chuyển database và đổi cách sinh numeric primary key.

### Yêu cầu

1. Xác định service owner của Account, Event, Reservation và Ticket. Phân biệt current profile với snapshot tại thời điểm phát vé.
2. Đề xuất public IDs, uniqueness scope, prefix/format nếu cần và chính sách không tái sử dụng.
3. Giải thích vì sao email không nên là userId ổn định và vì sao không dùng database ID của EventCatalog trực tiếp nếu muốn thay storage độc lập.
4. Thiết kế CreateReservation command với eventId, userId, seatId, tenantId và idempotency key theo đúng ngữ nghĩa; lưu ý eventId ở đây có thể nghĩa ID suất diễn, vì vậy nên đặt tên rõ eventOccurrenceId để tránh nhầm message eventId.
5. Viết sự kiện ReservationCreated/ReservationConfirmed có messageEventId, aggregateId/version, timestamp và tham chiếu phù hợp.
6. Nêu cách Reservation xác minh seat đủ điều kiện **tại điểm cấp chỗ** thay vì chỉ dựa vào EventCatalog projection.
7. Nếu Account bị merge từ user_old sang user_new, Ticketing cần giữ lịch sử thế nào và khi nào cập nhật canonical ID?
8. Nếu Account bị xóa, cách xử lý dữ liệu cá nhân nằm ở Ticketing và projection theo chính sách?
9. Khi một message UserUpdated version 8 đến sau UserDeactivated version 10, consumer phải làm gì?
10. Thiết kế kiểm tra authorization ngăn một tenant tự tạo reservation cho userId thuộc tenant khác.
11. Mô tả cách tránh hai reservation khi Client retry CreateReservation sau timeout.
12. Viết hai phép thử integration cho migration ID và hai phép thử cho merge/delete.
13. Đề xuất metric cho orphan references, alias resolution, replay lag và idempotency conflict.

### Hướng giải tham khảo

Account sở hữu hồ sơ hiện tại; Reservation sở hữu quyền giữ chỗ, Ticketing sở hữu vé đã phát hành. Ticketing có thể lưu snapshot tên hiển thị hoặc thông tin cần cho vé tại thời điểm phát hành theo chính sách, nhưng không tự cập nhật email nguồn của Account.

Public ID ổn định không nên phụ thuộc primary key storage mà EventCatalog muốn thay. Một phép merge account cần alias/canonical mapping có owner; các tham chiếu lịch sử không nên bị rewrite mù. Khi một Account bị xóa, phải xử lý PII trong projection và snapshot theo nghĩa vụ áp dụng, chứ không mặc định hard delete toàn bộ vé có ý nghĩa lịch sử.

Khi hai create command có cùng idempotency key, hệ thống phải đảm bảo một intent chỉ tạo một reservation. Reservation kiểm tra seat availability nguyên tử; EventCatalog chỉ cung cấp mô tả suất diễn. Read model trễ không phải nguồn quyết định cấp vé.

---

## 25. Mẫu ADR cho định danh và tham chiếu xuyên service

~~~text
ADR: Identity và Cross-service References cho <entity>

Bối cảnh nghiệp vụ:
Bounded context / service owner:
Đối tượng và vòng đời:
Public ID:
  Format/type và namespace:
  Phạm vi uniqueness:
  Ai cấp phát:
  Có cho client tạo trước không:
  Có ổn định qua DB migration không:
  Có bao giờ được tái sử dụng không:
Internal PK và mapping (nếu có):
Business keys có thể thay đổi:
Tenant scope và authorization:
Consumer references:
  Consumer nào lưu ID:
  Chỉ ID, snapshot hay projection:
  Hợp đồng query/command/event:
  Consistency và staleness chấp nhận:
Validation:
  Định dạng, tồn tại, eligibility:
  Điểm quyết định nghiệp vụ:
  Quote/reservation/version/expiry:
Lifecycle:
  Deactivate, delete, archive, merge:
  Alias và canonical ID:
  Tombstone/event/replay:
  Xử lý reference mồ côi:
Security và privacy:
  PII exposure, audit và retention:
  Cross-tenant checks:
Resilience:
  Timeout, retry, idempotency:
  Event ordering, duplicate và DLQ:
  Reconciliation/backfill:
Compatibility:
  Khi đổi ID format/storage/provider:
  Expand-migrate-contract và deprecation:
Test:
  Collision, race, tenant, delete, merge, stale:
Metric, alert và runbook:
Owner và rủi ro còn lại:
~~~

## 26. Những nguyên tắc cần nhớ

1. **Identity là hợp đồng có vòng đời**, không đơn thuần là khóa chính database.
2. **Logical reference xuyên service** liên kết các đối tượng qua ID và ngữ nghĩa, không bắt buộc foreign key vật lý xuyên DB.
3. **Service owner cấp phát và giải thích ID có thẩm quyền**; consumer không được dùng ID để tự sửa dữ liệu nguồn.
4. **Phạm vi uniqueness, tenant và object type phải rõ**; ID giống nhau có thể thuộc namespace khác nhau.
5. **Opaque, stable ID giúp giảm coupling**, nhưng không tự thay thế authentication, authorization và kiểm tra quyền theo tài nguyên.
6. **Business key như email/SKU có thể đổi**; cân nhắc surrogate/public ID khi cần tham chiếu bền.
7. **Reference có thể cũ, bị xóa hoặc được hợp nhất**; cần chính sách tombstone, alias, canonical ID và reconciliation.
8. **Snapshot lịch sử khác trạng thái hiện tại**; hai bản sao có thể cùng đúng theo thời điểm và ý nghĩa.
9. **Mất FK xuyên service là một đánh đổi có chủ đích**: cần bảo vệ những bất biến thực sự ở nơi có quyền quyết định.
10. **Idempotency, event version và source authority** giúp tham chiếu không bị nhân đôi, lùi trạng thái hoặc hồi sinh khi retry/replay.
11. **Migrating database không nên buộc consumer đổi public ID**, trừ khi có kế hoạch chuyển đổi hợp đồng rõ.
12. **Thiết kế reference phải tính cả bảo mật và dữ liệu riêng tư**: không lộ PII trong ID/event, không cho truy cập xuyên tenant và xử lý xóa bản sao đúng chính sách.

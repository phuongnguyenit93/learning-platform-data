# Các khái niệm nền tảng: dịch vụ, thể hiện chạy, hợp đồng và ranh giới

> Chủ đề: **Software Architecture → System Architecture → Microservices**  
> Phần: **Tổng quan**

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt **dịch vụ (service)** là đơn vị chức năng logic với **thể hiện chạy (instance)** là một tiến trình/container thực thi dịch vụ đó.
- Nhận diện **hợp đồng (contract)** mà dịch vụ cam kết với bên sử dụng, gồm giao diện, ý nghĩa nghiệp vụ và quy tắc tương thích.
- Xác định **ranh giới (boundary)** về trách nhiệm, dữ liệu và quyền quyết định của mỗi dịch vụ.
- Đọc sơ đồ Microservices mà không nhầm số lượng dịch vụ với số lượng bản sao đang chạy; giải thích tác động của các ranh giới đến triển khai, mở rộng và giao tiếp.

## 1. Bốn khái niệm nhìn trên cùng một hệ thống

Giả sử một ứng dụng bán hàng cần quản lý đơn đặt hàng, tồn kho và thanh toán:

~~~text
                        HTTP / JSON
Ứng dụng khách ────────> API Gateway
                              |
                              v
                   [Order Service: logic]
                     |       |       |
                 instance 1  |   instance 3
                         instance 2
                              |
                       dữ liệu đơn hàng

                [Inventory Service]   [Payment Service]
                   dữ liệu kho         dữ liệu thanh toán
~~~

Sơ đồ trên có **ba dịch vụ logic**: Order, Inventory và Payment. Order Service có **ba thể hiện chạy** phục vụ cùng một khả năng nghiệp vụ. Các bên gọi Order Service thông qua một **hợp đồng giao tiếp**. Mỗi dịch vụ có một **ranh giới trách nhiệm và dữ liệu** riêng.

| Khái niệm | Câu hỏi cốt lõi | Ví dụ |
| --- | --- | --- |
| **Service – dịch vụ** | Hệ thống cung cấp khả năng nghiệp vụ nào? | Order Service tiếp nhận và theo dõi đơn hàng. |
| **Instance – thể hiện chạy** | Có bao nhiêu bản thực thi đang phục vụ? | Ba container chạy Order Service. |
| **Contract – hợp đồng** | Bên ngoài được phép gọi/gửi/nhận gì và phải hiểu kết quả ra sao? | POST /v1/orders nhận yêu cầu tạo đơn; sự kiện OrderPlaced thông báo đơn được ghi nhận. |
| **Boundary – ranh giới** | Ai sở hữu quy tắc, dữ liệu và quyết định nghiệp vụ nào? | Order sở hữu trạng thái đơn; Inventory sở hữu số lượng tồn và quyết định giữ hàng. |

Quan hệ cần ghi nhớ: **một service có thể có nhiều instance; các instance cùng cung cấp contract của service; contract là cửa giao tiếp qua boundary**. Mỗi khái niệm trả lời một câu hỏi khác nhau, nên không được dùng thay nhau.

## 2. Service: đơn vị chức năng và vòng đời triển khai

### 2.1. Dịch vụ là gì?

Trong kiến trúc Microservices, **service** là một thành phần phần mềm có trách nhiệm tương đối rõ ràng, hiện thực một khả năng hoặc quy trình nghiệp vụ và cung cấp cách giao tiếp được xác định cho thành phần khác. Tùy hệ thống, dịch vụ có thể chứa mã nguồn, quy tắc nghiệp vụ, lưu trữ dữ liệu, API và các tác vụ nền.

Ví dụ:

- **Catalog Service**: quản lý thông tin mô tả sản phẩm, tên, hình ảnh và phân loại.
- **Inventory Service**: quản lý tồn kho, giữ hàng, giải phóng hàng và quy tắc không bán vượt số lượng khả dụng.
- **Order Service**: quản lý vòng đời đơn hàng như Draft, Pending, Confirmed, Cancelled.
- **Payment Service**: quản lý yêu cầu thanh toán, kết quả thanh toán và đối soát.

Một dịch vụ có thể được xây dựng, triển khai, giám sát và phát triển theo vòng đời tương đối độc lập. **Khả năng triển khai độc lập** là mục tiêu kiến trúc quan trọng; nó không có nghĩa dịch vụ tuyệt đối không phụ thuộc vào hệ thống khác. Thay đổi contract hoặc quy trình liên dịch vụ vẫn cần phối hợp.

### 2.2. Kích thước không định nghĩa một microservice

Không có quy tắc “mỗi service phải có dưới N dòng code”, “mỗi bảng là một service” hay “mỗi endpoint là một service”. Cách phân tách tốt ưu tiên **các quy tắc nghiệp vụ liên quan được giữ gần nhau** và giảm nhu cầu thay đổi đồng thời nhiều dịch vụ.

Chẳng hạn, tách CreateOrderService, UpdateOrderService và CancelOrderService thành ba service chỉ vì chúng có ba endpoint có thể làm quy tắc nhất quán của đơn hàng bị phân tán. Giữ các thao tác trong một Order Service thường rõ hơn, khi chúng cùng quản lý một vòng đời đơn hàng.

Ngược lại, nếu quản lý tồn kho có quy tắc, tốc độ thay đổi và nhu cầu mở rộng riêng, Inventory Service có thể là một ranh giới hợp lý.

### 2.3. Phân biệt với các khái niệm cùng tên

- Một **class Java gắn @Service** là thành phần trong ứng dụng Spring, chưa tự động trở thành một microservice.
- Một **Kubernetes Service** là đối tượng mạng cung cấp điểm truy cập và cân bằng kết nối đến các Pod; nó không đồng nghĩa với dịch vụ nghiệp vụ.
- **Module, package, library** là cách tổ chức mã. Chúng có thể hiện thực một phần dịch vụ, nhưng riêng sự tồn tại của chúng không tạo ra một đơn vị triển khai độc lập.
- **Microservice** không bắt buộc có một repository Git riêng. Một monorepo vẫn có thể chứa nhiều service được build và deploy độc lập.

## 3. Instance: một lần chạy cụ thể của service

### 3.1. Service logic khác instance vật lý

Một **instance** là một bản thực thi đang chạy của service: ví dụ một tiến trình JVM, một container hoặc một Pod chứa tiến trình ứng dụng. Một service có thể chạy 0, 1 hoặc nhiều instance ở cùng thời điểm.

~~~text
Định danh logic: order-service
  ├── instance A: JVM/container trên node-1
  ├── instance B: JVM/container trên node-2
  └── instance C: JVM/container trên node-3
~~~

Cả A, B, C đều chạy mã thực hiện chức năng Order Service và về nguyên tắc phục vụ cùng contract. Tuy nhiên, mỗi instance có bộ nhớ, kết nối mạng, log và vòng đời riêng. Instance có thể được tạo mới, khởi động lại, cập nhật phiên bản hoặc loại khỏi lưu lượng mà định danh service vẫn giữ nguyên.

**Một instance bị lỗi không nhất thiết làm service ngừng hoạt động** nếu các instance còn lại vẫn khỏe, tuyến truy cập được cập nhật và các phụ thuộc như cơ sở dữ liệu còn sẵn sàng. Nhiều instance cũng không tự động bảo đảm tính sẵn sàng cao: chúng có thể cùng phụ thuộc vào một điểm lỗi chung.

### 3.2. Vì sao chạy nhiều instance?

- **Mở rộng ngang (horizontal scaling):** thêm instance để phân tán tải khi ứng dụng và các phụ thuộc hỗ trợ.
- **Chịu lỗi:** điều hướng yêu cầu khỏi instance lỗi.
- **Triển khai cuốn chiếu (rolling deployment):** thay từng nhóm instance để giảm thời gian gián đoạn.
- **Phân bố tài nguyên:** đặt instance trên nhiều máy hoặc vùng lỗi khác nhau.

Ví dụ Order Service nhận 600 yêu cầu/giây. Thêm từ một lên ba instance có thể giúp tăng năng lực xử lý, nhưng không suy ra chắc chắn mỗi instance xử lý đúng 200 yêu cầu/giây: phân bố tải, độ trễ, khóa dữ liệu và giới hạn cơ sở dữ liệu đều ảnh hưởng kết quả.

### 3.3. Những hệ quả khi nhân bản instance

1. **Không lấy bộ nhớ của một instance làm nguồn dữ liệu chung.** Nếu instance A giữ giỏ hàng trong RAM, lần gọi sau vào B có thể không nhìn thấy. Trạng thái cần bền vững hoặc chia sẻ phải được lưu ở nơi có thiết kế phù hợp, chẳng hạn database/cache/session store.
2. **Không hard-code địa chỉ từng instance vào logic nghiệp vụ.** Client thường gọi tên service hoặc gateway; discovery/load balancer chọn instance khả dụng.
3. **Cẩn thận xử lý đồng thời.** Hai instance cùng nhận yêu cầu cập nhật một đơn hàng cần cơ chế kiểm soát nhất quán ở tầng lưu trữ hoặc nghiệp vụ, chẳng hạn optimistic locking, điều kiện cập nhật hoặc idempotency.
4. **Dự tính instance bị dừng bất kỳ lúc nào.** Health check, readiness, graceful shutdown và retry có giới hạn giúp hệ thống thích nghi khi triển khai hay có sự cố.
5. **Dự tính chồng phiên bản trong lúc rollout.** Trong một thời gian ngắn, các instance phiên bản cũ và mới có thể cùng phục vụ. Contract và dữ liệu phải tương thích với trạng thái đó nếu muốn rollout an toàn.

**Stateless ở tầng xử lý yêu cầu** không có nghĩa dịch vụ không sở hữu dữ liệu; nó nghĩa là tính đúng đắn của một yêu cầu không phụ thuộc vào bộ nhớ riêng của một instance cụ thể.

## 4. Contract: lời cam kết tại điểm giao tiếp

### 4.1. Contract gồm những gì?

**Contract** là tập quy tắc có thể quan sát từ bên ngoài mà provider cam kết cho consumer. Contract không chỉ là URL hay chữ ký hàm; nó còn bao gồm **ý nghĩa nghiệp vụ**.

Với HTTP API, contract thường mô tả:

- **Điểm truy cập và phương thức:** chẳng hạn POST /v1/orders, GET /v1/orders/{id}.
- **Dữ liệu đầu vào:** schema, kiểu dữ liệu, trường bắt buộc/tùy chọn, ràng buộc hợp lệ.
- **Đầu ra:** schema, status code, header, lỗi có cấu trúc.
- **Ngữ nghĩa:** khi nào đơn được coi là tạo, thanh toán có được thực hiện ngay không, yêu cầu lặp được xử lý thế nào.
- **Yêu cầu sử dụng:** xác thực, phân quyền, giới hạn tốc độ, timeout, chính sách retry và khả năng tương thích phiên bản khi được công bố.

Ví dụ một phần contract tạo đơn:

~~~http
POST /v1/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: checkout-42

{
  "customerId": "cus-42",
  "items": [
    { "sku": "book-01", "quantity": 2 }
  ]
}
~~~

Một kết quả có thể được định nghĩa như sau:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /v1/orders/ord-1001

{
  "orderId": "ord-1001",
  "status": "PENDING",
  "totalAmount": 340000,
  "currency": "VND"
}
~~~

Trong **ví dụ contract giả định** này, 201 nghĩa là tài nguyên đơn đã được tạo. Trạng thái PENDING chỉ cho biết quy trình hoàn tất đơn có thể đang diễn ra, **không khẳng định thanh toán và giữ hàng đều đã thành công**. Nếu hệ thống chỉ tiếp nhận công việc và chưa tạo tài nguyên, contract có thể chọn 202 Accepted thay vì 201. Ý nghĩa cụ thể phải được viết rõ và giữ nhất quán.

Header Idempotency-Key là một cách thiết kế để hỗ trợ yêu cầu lặp, nhưng **chỉ đặt header không tự tạo ra tính idempotent**. Provider phải lưu và áp dụng chính sách nhận diện yêu cầu trùng, thời hạn hiệu lực, phạm vi khóa và cách trả kết quả.

### 4.2. Contract của giao tiếp bất đồng bộ

Microservices còn giao tiếp qua sự kiện hoặc hàng đợi. Khi Order Service công bố sự kiện, contract có thể là:

~~~json
{
  "eventId": "evt-9001",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T10:00:00Z",
  "orderId": "ord-1001",
  "customerId": "cus-42"
}
~~~

Contract sự kiện cần giải thích **OrderPlaced nghĩa là điều gì đã xảy ra**: đơn đã được lưu, đã xác nhận, hay đã hoàn thành thanh toán? Nếu tên sự kiện không phản ánh đúng thời điểm nghiệp vụ, các consumer dễ hiểu sai.

Ngoài schema, hợp đồng bất đồng bộ cần mô tả khi có liên quan:

- Định danh sự kiện, quy tắc chống xử lý trùng, correlation ID và cách truy vết.
- Có bảo đảm thứ tự hay không, theo khóa nào, và điều gì xảy ra khi sự kiện đến muộn.
- Chính sách gửi lại, dead-letter, lưu giữ và khả năng phát lại, tùy broker và cấu hình thực tế.
- Cách thay đổi schema khi producer và consumer triển khai khác thời điểm.

Không mặc định hệ thống message bảo đảm **exactly-once** xuyên suốt mọi side effect. Trong nhiều triển khai, consumer phải có khả năng xử lý lặp an toàn vì thông điệp có thể được giao lại.

### 4.3. Contract và implementation

Consumer nên phụ thuộc vào **hợp đồng công khai**, không phụ thuộc vào cấu trúc bảng, class nội bộ, tên Pod hay thuật toán của provider. Order Service có thể đổi từ một bảng sang nhiều bảng, hoặc tối ưu truy vấn, mà consumer không cần đổi nếu contract vẫn được giữ.

Ngược lại, đổi tên trường JSON đang được sử dụng, đổi cách diễn giải trạng thái, biến lỗi nghiệp vụ thành HTTP 200 thành công hoặc thay quy tắc retry có thể phá contract dù mã vẫn biên dịch.

Contract nên được mô tả bằng tài liệu/schema phù hợp, ví dụ OpenAPI cho HTTP hoặc AsyncAPI/schema cho sự kiện. **Consumer-driven contract test** và integration test giúp phát hiện một số thay đổi gây đổ vỡ, nhưng test không thay thế việc thỏa thuận ngữ nghĩa nghiệp vụ.

### 4.4. Tiến hóa contract

Một số hướng duy trì tương thích:

1. Thêm trường tùy chọn có giá trị mặc định/hành vi rõ ràng, khi consumer cũ được thiết kế để bỏ qua trường lạ.
2. Không xóa, đổi tên hoặc đổi nghĩa trường mà consumer còn dựa vào khi chưa có kế hoạch chuyển đổi.
3. Thay đổi dần theo chu kỳ **expand → migrate → contract**: mở rộng API/schema, chuyển consumer, rồi mới loại bỏ giao diện cũ.
4. Dùng versioning khi thật sự cần thay đổi không tương thích; version mới không tự giải quyết việc chuyển consumer.
5. Thử nghiệm với phiên bản producer/consumer cùng tồn tại trong quá trình rollout.

## 5. Boundary: giới hạn quyền sở hữu và trách nhiệm

### 5.1. Ranh giới nghiệp vụ

**Boundary** cho biết dịch vụ chịu trách nhiệm về điều gì và điều gì thuộc bên ngoài. Nó giúp giữ các quy tắc có liên quan chặt ở cùng nơi, đồng thời giảm tình trạng nhiều thành phần phải biết chi tiết của nhau.

Ví dụ trong hệ thống bán hàng:

| Dịch vụ | Quyết định và dữ liệu thuộc quyền sở hữu | Điều không nên tự quyết thay dịch vụ khác |
| --- | --- | --- |
| Order | Tạo đơn, trạng thái và lịch sử đơn, điều kiện hủy đơn | Tự sửa số lượng tồn trong bảng của Inventory |
| Inventory | Số lượng khả dụng, giữ/nhả hàng, chống bán vượt tồn | Tự đổi trạng thái thanh toán của Order |
| Payment | Giao dịch thanh toán, kết quả từ cổng thanh toán, đối soát | Tự sửa tổng tiền và các dòng hàng của đơn |

Chủ sở hữu dữ liệu là dịch vụ **có quyền áp dụng quy tắc và ghi thay đổi**. Điều này không nhất thiết đòi mỗi dịch vụ có một máy database vật lý riêng. Tuy nhiên, để giữ ranh giới, dịch vụ khác không nên truy cập ghi trực tiếp bảng/sơ đồ nội bộ của chủ sở hữu; dữ liệu cần được chia sẻ qua contract hoặc bản sao đọc có cơ chế đồng bộ rõ ràng.

### 5.2. Ranh giới có nhiều chiều

- **Ranh giới nghiệp vụ:** những quy tắc và quyết định nào thay đổi cùng nhau?
- **Ranh giới dữ liệu:** dịch vụ nào là nguồn sự thật cho từng thực thể/trạng thái? Ai được quyền ghi?
- **Ranh giới giao tiếp:** thông tin nào được công bố ra ngoài? Điều gì phải giấu bên trong?
- **Ranh giới triển khai:** thành phần nào có thể được release, rollback, scale độc lập?
- **Ranh giới sở hữu vận hành:** nhóm nào chịu trách nhiệm chỉ số, cảnh báo, điều tra lỗi và khắc phục?

Các chiều này liên quan nhưng không hoàn toàn trùng nhau. Ví dụ, hai dịch vụ cùng chạy trên một cluster vẫn có ranh giới nghiệp vụ riêng. Việc dùng hai container không chứng minh rằng chúng có ranh giới nghiệp vụ tốt.

Trong Domain-Driven Design, **bounded context** là phạm vi mà mô hình và thuật ngữ nghiệp vụ có ý nghĩa nhất quán. Nó là công cụ hữu ích để nhận diện ranh giới microservice, nhưng không có quy tắc bắt buộc “một bounded context luôn bằng đúng một service”. Sự lựa chọn còn phụ thuộc đội ngũ, tải, vòng đời và chi phí vận hành.

### 5.3. Ranh giới quyết định kiểu giao tiếp

Một thao tác nằm **trong** boundary có thể dùng lời gọi hàm và một transaction cục bộ. Một thao tác **đi qua** boundary thường cần API hoặc sự kiện, xử lý mạng chậm/lỗi, kiểm soát quyền và cơ chế nhất quán giữa các chủ sở hữu.

Ví dụ Order muốn giữ hàng:

~~~text
Order Service                           Inventory Service
     |                                          |
     |---- ReserveStock(orderId, items) ------> |
     |                                          | kiểm tra tồn,
     |                                          | ghi reservation
     | <--- Reserved / Rejected ----------------|
     |                                          |
   cập nhật trạng thái đơn tại dữ liệu Order
~~~

Inventory Service tự quyết liệu còn đủ hàng. Order Service không nên dùng một câu SQL để tự trừ tồn kho. Nếu Order đã ghi đơn nhưng Inventory từ chối giữ hàng, hệ thống cần trạng thái và quy trình xử lý thất bại đã thiết kế trước; không thể giả định transaction database của Order tự động bao trùm Inventory.

### 5.4. Tín hiệu ranh giới chưa hợp lý

- Một thay đổi nghiệp vụ nhỏ luôn buộc triển khai đồng thời nhiều dịch vụ.
- Hai dịch vụ cùng ghi cùng bảng, tạo phụ thuộc ngầm vào schema.
- Service A phải hiểu chi tiết class, trạng thái tạm hoặc thuật toán bên trong Service B mới làm được việc.
- Các service liên tục gọi đồng bộ thành chuỗi dài, biến một yêu cầu thành nhiều điểm lỗi.
- Quy tắc nhất quán của một thực thể bị phân tán đến mức không ai có quyền quyết định cuối cùng.
- Cắt service theo lớp kỹ thuật thuần túy như “controller service”, “repository service” dù chức năng nghiệp vụ không có ranh giới tương ứng.

Không phải mọi lời gọi liên dịch vụ đều là dấu hiệu thiết kế sai. Vấn đề nằm ở **mức phụ thuộc, tính rõ ràng của sở hữu và khả năng tiến hóa**.

## 6. Ghép cả bốn khái niệm vào luồng đặt hàng

Giả sử người dùng nhấn **Đặt hàng**:

1. Ứng dụng gửi POST /v1/orders theo **contract** do Order Service công bố.
2. Gateway hoặc cơ chế discovery chọn một **instance** Order đang khỏe. Instance nhận yêu cầu không phải một service mới.
3. **Order Service** kiểm tra dữ liệu đơn và lưu trạng thái ban đầu vào vùng dữ liệu do nó sở hữu.
4. Để giữ hàng, Order gọi **contract** của Inventory Service. Inventory kiểm tra và cập nhật tồn theo **boundary** của mình.
5. Nếu cần thanh toán, Order bắt đầu quy trình qua contract của Payment Service. Payment sở hữu kết quả giao dịch và phản hồi/sự kiện liên quan.
6. Order chuyển trạng thái đơn dựa trên kết quả nhận được và quy tắc của Order. Các bước có thể diễn ra bất đồng bộ; trạng thái trung gian phải được mô tả rõ với người dùng.
7. Sau này khi tải tăng, Order có thể tăng từ 2 lên 5 **instance** mà không vì thế thành 5 service và không làm đổi contract nếu thiết kế đúng.

Một quy trình đi qua nhiều boundary **không có transaction ACID chung theo mặc định**. Kiến trúc có thể dùng trạng thái tiến trình, sự kiện, timeout, retry có kiểm soát và hành động bù trừ (compensation/saga) khi cần. Chẳng hạn, đã giữ hàng nhưng thanh toán thất bại thì có thể phát lệnh giải phóng reservation; phải xác định điều kiện và xử lý cả trường hợp lệnh bù trừ cũng lỗi.

Bảng kiểm tra nhanh cho ví dụ:

| Thành phần | Câu trả lời |
| --- | --- |
| Service là gì? | Order, Inventory, Payment: ba năng lực nghiệp vụ. |
| Instance là gì? | Những tiến trình/container đang chạy từng service; số lượng thay đổi theo tải. |
| Contract ở đâu? | API tạo đơn, API giữ hàng, API thanh toán và các event/schema được công bố. |
| Boundary nằm ở đâu? | Ở quyền sở hữu quyết định và dữ liệu đơn, kho, thanh toán; lời gọi qua API/event vượt qua boundary. |

## 7. Tác động đến thiết kế và vận hành

### 7.1. Độ tin cậy và lỗi từng phần

Trong một tiến trình đơn, lời gọi hàm có thể lỗi nhưng không có chặng mạng. Khi tách qua service, mỗi lời gọi có thêm khả năng timeout, mất kết nối, trả lời muộn hoặc bên kia chưa sẵn sàng.

Các cơ chế như **timeout, retry có giới hạn, backoff, circuit breaker và bulkhead** có thể hữu ích tùy luồng. Retry chỉ an toàn khi hiểu ngữ nghĩa và tính idempotent; retry lệnh tạo thanh toán một cách mù quáng có thể gây tác dụng phụ lặp.

Nên định nghĩa trạng thái thất bại từ góc nhìn nghiệp vụ: “đơn chờ thanh toán”, “giữ hàng hết hạn”, “hủy yêu cầu” rõ hơn việc che tất cả dưới một lỗi 500.

### 7.2. Quan sát và truy vết

Một yêu cầu có thể đi qua nhiều service và nhiều instance. Vì vậy nên có:

- **Correlation/trace ID** truyền qua các lời gọi và message khi có thể.
- Log chứa tên service, instance, phiên bản, request ID và ngữ cảnh phù hợp mà không lộ dữ liệu nhạy cảm.
- Metrics cho tỉ lệ lỗi, độ trễ, lưu lượng và trạng thái tài nguyên từng service.
- Distributed tracing để thấy thời gian của từng chặng, đặc biệt khi quy trình bị chậm hoặc timeout.

Service-level metrics giúp đánh giá trách nhiệm logic; instance-level metrics giúp tìm đúng bản chạy lỗi. Chúng phục vụ hai mục đích khác nhau.

### 7.3. Bảo mật và quyền truy cập

Ranh giới service cũng là điểm phải quyết định **ai được gọi thao tác nào**. Gateway xác thực đầu vào không có nghĩa các lời gọi nội bộ luôn đáng tin. Tùy môi trường, cần xác thực/ủy quyền giữa service, giới hạn quyền truy cập dữ liệu và lưu dấu thao tác.

Contract nên mô tả các yêu cầu quyền có ý nghĩa với consumer, còn chi tiết bí mật như khóa, mật khẩu, token nội bộ không được công bố trong ví dụ hoặc tài liệu chung.

### 7.4. Chi phí của phân tán

Microservices có thể giúp các nhóm phát triển và triển khai độc lập, nhưng đổi lại là network latency, giám sát phân tán, quản lý phiên bản contract, dữ liệu eventual consistency và hạ tầng vận hành phức tạp hơn.

Một **modular monolith** với module/boundary nghiệp vụ rõ ràng có thể là điểm khởi đầu phù hợp. Khi có lý do cụ thể như nhu cầu triển khai hoặc mở rộng độc lập, từng boundary mới được tách thành service. Việc có nhiều container tự nó không làm hệ thống tốt hơn.

## 8. Các nhầm lẫn phổ biến

**Nhầm lẫn 1 — “Ba Pod Order nghĩa là ba microservice.”**  
Sai. Đó là ba instance của một Order Service logic. Tăng replica chỉ thay đổi số bản chạy, trừ khi thiết kế thực sự thay đổi năng lực và contract.

**Nhầm lẫn 2 — “Contract chỉ là địa chỉ endpoint.”**  
Thiếu. Consumer cần hiểu định dạng, status code, lỗi, ý nghĩa thành công, điều kiện retry và tương thích. Cùng URL nhưng đổi nghĩa trường vẫn có thể phá contract.

**Nhầm lẫn 3 — “Mỗi microservice phải có database server riêng.”**  
Không bắt buộc ở mức máy chủ vật lý. Điều cần làm rõ là **quyền sở hữu dữ liệu và đường ghi có kiểm soát**. Dùng chung schema với quyền ghi chéo thường khiến các service phụ thuộc chặt.

**Nhầm lẫn 4 — “Đã tách boundary thì không cần nhất quán.”**  
Sai. Các bất biến nghiệp vụ vẫn phải được bảo vệ; chỉ có cơ chế duy trì nhất quán thay đổi. Bên trong service có thể dùng transaction cục bộ; xuyên service cần quy trình và chính sách lỗi rõ ràng.

**Nhầm lẫn 5 — “Có thể thay đổi mọi thứ trong service mà consumer không biết.”**  
Chỉ đúng với chi tiết nội bộ không làm thay đổi contract được quan sát. Thay đổi schema, hành vi hoặc mức bảo đảm có thể ảnh hưởng consumer.

**Nhầm lẫn 6 — “Chạy nhiều instance sẽ tự động xử lý được mọi vấn đề tải.”**  
Không. Database, message broker, downstream service, khóa ghi và dữ liệu nóng vẫn có thể là nút thắt; cần đo lường từng tầng.

**Nhầm lẫn 7 — “Service A gọi service B nên cả hai phải dùng chung model và bảng.”**  
Không. A nên dùng contract được công bố. Mỗi bên duy trì model nội bộ phù hợp với trách nhiệm; mapping là một phần của tích hợp.

## 9. Bài tập suy luận

**Tình huống A.** Một ứng dụng có 4 Pod chạy cùng artifact order-service, cùng cung cấp POST /v1/orders; riêng Order và Inventory có dữ liệu riêng.  
**Xác định:** Có bao nhiêu service trong phần mô tả, bao nhiêu Order instance, đâu là contract và đâu là boundary?

**Gợi ý trả lời:** Có ít nhất hai service logic được nêu (Order, Inventory). Order có bốn instance. POST /v1/orders là một điểm trong contract của Order, nhưng cần thêm schema và ngữ nghĩa để thành contract đầy đủ. Boundary nằm ở quyền sở hữu đơn hàng so với tồn kho.

**Tình huống B.** Đội phát triển thêm trường tùy chọn deliveryNote vào response tạo đơn; consumer cũ bỏ qua trường lạ.  
**Câu hỏi:** Thay đổi này có thể tương thích không? Khi nào không?

**Gợi ý trả lời:** Có thể tương thích nếu contract cho phép trường mở rộng và các consumer thực sự bỏ qua trường lạ. Vẫn có thể không tương thích nếu consumer kiểm tra schema đóng, ý nghĩa trường cũ bị đổi hoặc quy trình liên quan thay đổi. Cần kiểm chứng bằng contract/integration test phù hợp.

**Tình huống C.** Order Service muốn trừ trực tiếp cột available_quantity trong database của Inventory để giảm một lời gọi API.  
**Câu hỏi:** Cách này tiết kiệm điều gì, và gây rủi ro gì?

**Gợi ý trả lời:** Nó có thể giảm một chặng giao tiếp trước mắt, nhưng làm Order phụ thuộc schema và vượt quyền quyết định giữ hàng của Inventory. Kiểm tra tồn, chống tranh chấp và audit dễ bị bỏ qua; hai service phải phối hợp thay đổi dữ liệu, đánh mất một phần lợi ích của boundary.

## 10. Ghi nhớ

- **Service** trả lời: *Năng lực nghiệp vụ nào đang được cung cấp và ai chịu trách nhiệm?*
- **Instance** trả lời: *Năng lực đó hiện được thực thi bởi những tiến trình/container nào?*
- **Contract** trả lời: *Bên ngoài có thể tương tác bằng cách nào và có thể dựa vào hành vi gì?*
- **Boundary** trả lời: *Dữ liệu, quy tắc và quyết định nào thuộc bên trong, điểm giao tiếp nào đi ra bên ngoài?*

Khi phân tích một sơ đồ Microservices, hãy bắt đầu bằng cách **đếm service theo trách nhiệm nghiệp vụ**, sau đó xác định **số instance của mỗi service**, đọc **contract nối các service** và cuối cùng kiểm tra **quyền sở hữu dữ liệu/quy tắc ở từng boundary**. Bốn câu hỏi này là nền tảng để hiểu các chủ đề tiếp theo như service discovery, API Gateway, giao tiếp đồng bộ/bất đồng bộ, consistency, scaling và resilience.

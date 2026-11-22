# Quyền sở hữu dữ liệu và hợp đồng giữa các dịch vụ

Trong kiến trúc cloud có nhiều dịch vụ, việc chia ứng dụng thành các API nhỏ chưa đủ để tạo ra các thành phần độc lập. Câu hỏi khó hơn là: **dịch vụ nào có quyền quyết định sự thật nghiệp vụ, dịch vụ nào được thay đổi dữ liệu, và những dịch vụ khác được phép dựa vào cam kết nào?**

Ví dụ, một nền tảng đặt chỗ có dịch vụ Đặt chỗ, Tình trạng phòng và Thanh toán. Nếu cả ba cùng sửa trạng thái đặt phòng trong một bảng dùng chung, thay đổi của một nhóm dễ làm hỏng nhóm còn lại. Nếu mỗi dịch vụ tự duy trì một bản dữ liệu phòng nhưng không quy định nguồn đáng tin cậy, hệ thống có thể xác nhận hai lượt đặt cho cùng một phòng. **Quyền sở hữu dữ liệu** giải quyết ranh giới quyết định và cập nhật; **hợp đồng giữa các dịch vụ** xác định cách các bên giao tiếp, hiểu dữ liệu và ứng xử khi có thay đổi hoặc sự cố.

Bài học thuộc chương **Mô hình ứng dụng** của **CLOUD_ARCHITECTURE**. Khi thiết kế ứng dụng trên đám mây, các quyết định về ranh giới dịch vụ ảnh hưởng trực tiếp đến lựa chọn compute, mạng, cơ sở dữ liệu, mô hình triển khai, độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Nội dung dưới đây dùng tư duy Well-Architected để đánh giá các đánh đổi ấy.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **chủ sở hữu dữ liệu nghiệp vụ**, **nguồn dữ liệu có thẩm quyền**, **bản sao phục vụ đọc** và **người quản trị hạ tầng lưu trữ**.
2. Phân chia ranh giới dịch vụ theo năng lực nghiệp vụ và xác định ai được tạo, cập nhật, hủy, công bố hoặc sử dụng từng loại dữ liệu.
3. Thiết kế hợp đồng REST/gRPC hoặc sự kiện bất đồng bộ, bao gồm cấu trúc, ngữ nghĩa, lỗi, phiên bản, an ninh và cam kết vận hành.
4. Giải thích các cơ chế **eventual consistency**, **idempotency**, **transactional outbox** và **saga** khi nghiệp vụ trải qua nhiều dịch vụ.
5. Lựa chọn chiến lược thay đổi schema an toàn, kiểm thử tính tương thích và quan sát hệ thống.
6. Đánh giá giải pháp theo Well-Architected: độ tin cậy, bảo mật, vận hành, hiệu năng, chi phí và tính bền vững.

## 2. Hiểu đúng quyền sở hữu dữ liệu

### 2.1. Ai sở hữu dữ liệu trong kiến trúc phần mềm?

Trong bài này, **data ownership về mặt kiến trúc** là sự phân công quyền **định nghĩa quy tắc**, **quyết định trạng thái hợp lệ**, **thực hiện thay đổi** và **công bố thông tin** cho một nhóm dữ liệu nghiệp vụ. Nó khác với quyền sở hữu hợp pháp đối với dữ liệu, quyền riêng tư của chủ thể dữ liệu hoặc bên chịu trách nhiệm xử lý dữ liệu theo luật.

Ví dụ, nhóm phụ trách Đặt chỗ có quyền quản lý vòng đời một booking (tạo, xác nhận, hủy) theo quy tắc nghiệp vụ. Điều đó **không có nghĩa** nhóm được tự quyết thời hạn lưu giữ dữ liệu cá nhân, quyền truy cập của khách hàng hoặc yêu cầu pháp lý. Các quy tắc về quyền riêng tư và tuân thủ vẫn phải được thực thi xuyên suốt.

Một hệ thống thường có nhiều vai trò khác nhau:

| Vai trò | Trách nhiệm | Minh họa |
|---|---|---|
| **Chủ sở hữu nghiệp vụ / nhóm sản phẩm** | Định nghĩa ý nghĩa và vòng đời dữ liệu, chấp thuận thay đổi quy tắc | Quy định khi nào booking được xem là xác nhận |
| **Dịch vụ có thẩm quyền (system of record)** | Thực thi kiểm tra và thao tác ghi hợp lệ cho dữ liệu thuộc phạm vi mình | Booking Service quyết định trạng thái booking |
| **Nhóm vận hành / nền tảng** | Vận hành database, backup, monitoring, IAM và hạ tầng theo trách nhiệm được giao | Nhóm cloud vận hành cluster DB cho nhiều dịch vụ |
| **Dịch vụ tiêu thụ (consumer)** | Đọc dữ liệu qua hợp đồng, xử lý dữ liệu trễ và tình huống thiếu dữ liệu | Notification Service nghe sự kiện BookingConfirmed |
| **Chủ quản dữ liệu / bộ phận pháp chế** | Chính sách phân loại, lưu giữ, bảo mật và tuân thủ | Quy định thời hạn lưu thông tin định danh |

**Quy tắc chủ chốt:** một sự thật nghiệp vụ quan trọng cần có **một nơi chịu trách nhiệm quyết định trạng thái chuẩn**, dù có thể tồn tại nhiều bản sao để đọc. Quy tắc này không đòi hỏi mỗi dịch vụ luôn phải có một máy chủ database riêng; điều cốt lõi là quyền thay đổi được phân định và có cơ chế thực thi.

### 2.2. Bounded context là điểm khởi đầu thực tế

Theo tư duy *Domain-Driven Design (DDD)*, một **bounded context** là phạm vi mà các khái niệm và quy tắc nghiệp vụ có ý nghĩa nhất quán. Ranh giới này thường là cơ sở tốt để định hình dịch vụ, nhưng không bắt buộc cứ một bounded context phải trở thành một tiến trình triển khai độc lập ngay lập tức.

Ví dụ với một hệ thống đặt chỗ:

| Ngữ cảnh | Nguồn dữ liệu có thẩm quyền | Dữ liệu có thể được nơi khác sao chép để đọc |
|---|---|---|
| **Listing / Catalog** | Thông tin chỗ ở, mô tả, trạng thái công bố | Tên và hình đại diện chỗ ở trong lịch sử booking |
| **Availability** | Khoảng thời gian còn trống, quyền giữ chỗ, giới hạn số lượng | Kết quả tìm kiếm khả dụng tại thời điểm truy vấn |
| **Booking** | Mã đặt chỗ, người đặt, trạng thái và quy tắc hủy | Danh sách booking hiển thị trong trang hồ sơ |
| **Payment** | Giao dịch thanh toán, trạng thái ủy quyền/hoàn tiền, đối soát | Trạng thái thanh toán tổng quát trong màn hình booking |
| **Customer Profile** | Thông tin hồ sơ và sở thích được phép lưu | Tên hiển thị cần thiết trong lịch sử giao dịch |

Không nên tách dịch vụ chỉ vì các danh từ khác nhau. Hãy xét ai thay đổi quy tắc, mức độ gắn kết dữ liệu và transaction, nhu cầu mở rộng riêng, khả năng vận hành của đội ngũ và chi phí giao tiếp qua mạng.

### 2.3. Tách quyền ghi khỏi nhu cầu đọc

Để Booking Service hiển thị tên chỗ ở, không nhất thiết phải cho Booking Service quyền sửa bảng listing. Có thể:

- Truy vấn Catalog qua API khi cần thông tin mới nhất.
- Lưu **snapshot** một số thuộc tính tại thời điểm tạo booking (chẳng hạn tên cơ sở và giá được chấp thuận), nếu lịch sử cần giữ nguyên theo giao dịch.
- Duy trì bản sao đọc (*read model/projection*) bằng sự kiện, kèm thời điểm cập nhật và quy trình tái tạo.

Mỗi cách có đánh đổi: gọi API trực tiếp có thể tạo phụ thuộc độ trễ/sẵn sàng; snapshot phù hợp lịch sử nhưng không phản ánh thay đổi hiện tại; projection giảm tải truy vấn liên dịch vụ nhưng có độ trễ đồng bộ và chi phí vận hành.

**Nguồn chuẩn cho thuộc tính nào phải ghi rõ đến thuộc tính đó.** Ví dụ, giá đã chấp nhận trong hợp đồng đặt chỗ là sự thật của Booking, còn giá niêm yết hiện tại là sự thật của Catalog/Pricing. Nếu coi hai giá trị là một và đồng bộ vô điều kiện, giao dịch lịch sử có thể bị thay đổi sai.

## 3. Cách tổ chức dữ liệu theo ranh giới dịch vụ

### 3.1. Database per service là ranh giới truy cập, không chỉ là tên database

Nguyên tắc *database per service* yêu cầu mỗi dịch vụ có quyền kiểm soát độc lập trên schema hoặc vùng dữ liệu của mình; các dịch vụ khác sử dụng **hợp đồng đã công bố** để truy cập, thay vì tự truy vấn và ghi bảng nội bộ.

Những mức cách ly có thể lựa chọn:

| Cách triển khai | Khi nào có thể phù hợp | Rủi ro phải quản lý |
|---|---|---|
| Chung DB server, mỗi dịch vụ có **schema và tài khoản riêng** | Hệ thống nhỏ, tối ưu chi phí ban đầu | Tài nguyên chung và quyền quản trị có thể gây ảnh hưởng lẫn nhau; phải hạn chế quyền cross-schema |
| Mỗi dịch vụ có **database logic riêng** trên cùng cụm | Muốn cách ly schema, cấu hình kết nối và quyền rõ hơn | Cluster vẫn là failure domain và giới hạn hiệu năng chung |
| Mỗi dịch vụ có **database hoặc cluster riêng** | Cần scale, backup, restore và cấu hình độc lập | Chi phí hạ tầng, giám sát, kết nối và DR tăng |

Mọi phương án đều cần quy định ai thực hiện migration, ai quản lý role/secret, lịch backup và cách phục hồi. Việc chia database vật lý không tự bảo đảm dịch vụ độc lập nếu API vẫn gọi đồng bộ lẫn nhau theo một chuỗi dài.

### 3.2. Chống truy cập trực tiếp sang dữ liệu thuộc dịch vụ khác

Mẫu cần tránh:

~~~text
Booking Service ---SQL UPDATE---> payment.transactions
Booking Service ---SQL SELECT---> availability.holds
Payment Service ---SQL UPDATE---> booking.bookings
~~~

Vấn đề:

1. Một dịch vụ có thể phá vỡ quy tắc nghiệp vụ và invariant của dịch vụ khác.
2. Nhóm sở hữu bảng khó thay schema vì không biết hết consumer.
3. Một transaction trải nhiều bảng tạo phụ thuộc triển khai và quyền database rộng.
4. Quan sát, phân quyền, audit và điều tra nguyên nhân trở nên khó.

Cách làm phù hợp hơn là yêu cầu consumer gọi API hoặc gửi command mà **owner có quyền từ chối** khi điều kiện nghiệp vụ không thỏa, hoặc đăng ký các sự kiện được owner phát hành. Chỉ dùng shared database có chủ đích trong một ứng dụng/đơn vị triển khai chung nếu ranh giới module và trách nhiệm thay đổi được kiểm soát rõ.

### 3.3. Ai kiểm soát các thay đổi cấu trúc?

Service owner sở hữu schema và migration của phần dữ liệu mình quản lý. Khi cần thêm cột, chia bảng hoặc thay cấu trúc lưu trữ, thay đổi nội bộ có thể triển khai độc lập **nếu hợp đồng bên ngoài vẫn tương thích**. Ngược lại, dùng chung database và truy vấn liên schema khiến việc sửa một cột thành thay đổi liên đội, có nguy cơ cần triển khai đồng thời.

## 4. Hợp đồng giữa các dịch vụ là gì?

**Service contract** là tập cam kết mà nhà cung cấp dịch vụ (*provider*) công bố cho bên sử dụng (*consumer*). Hợp đồng đầy đủ phải bao quát nhiều hơn tên endpoint hoặc schema JSON:

| Thành phần hợp đồng | Nội dung phải làm rõ | Ví dụ |
|---|---|---|
| **Cấu trúc** | Endpoint/topic, request/response/event, kiểu, trường bắt buộc, định danh | bookingId là chuỗi định danh bất biến |
| **Ngữ nghĩa** | Ý nghĩa trường, trạng thái, quy tắc chuyển trạng thái, tính bất biến | CONFIRMED chỉ khi điều kiện giữ chỗ và thanh toán đáp ứng |
| **Hành vi lỗi** | Mã lỗi, timeout, retry, giới hạn, khi nào trả kết quả chưa xác định | Hết thời gian chờ không chứng minh thanh toán thất bại |
| **Tính nhất quán** | Trạng thái nào đọc được ngay, trạng thái nào chỉ đồng bộ sau một thời gian | Search index có thể chậm cập nhật so với nguồn |
| **Bảo mật và dữ liệu** | Xác thực, ủy quyền, trường nhạy cảm, tenant, retention | Chỉ khách hàng sở hữu booking hoặc vai trò được phép mới được đọc |
| **Phiên bản và thay đổi** | Quy tắc tương thích, deprecation, thời hạn hỗ trợ | Không xóa trường khi consumer cũ còn phụ thuộc |
| **Cam kết vận hành** | SLO, giới hạn tải, throughput, event retention, cảnh báo | Tỷ lệ thành công và độ trễ p95 của API trong điều kiện đo xác định |
| **Owner và hỗ trợ** | Nhóm chịu trách nhiệm, tài liệu, đầu mối sự cố, cách báo thay đổi | Nhóm Booking duyệt yêu cầu thay đổi hợp đồng |

Một schema có thể hợp lệ về cú pháp nhưng sai về nghiệp vụ. Nếu provider đổi ý nghĩa của trường amount từ đơn vị tiền nhỏ nhất sang đơn vị tiền chính mà không đổi tên hay phiên bản, consumer vẫn parse thành công nhưng có thể tính tiền sai nghiêm trọng.

## 5. Thiết kế hợp đồng API đồng bộ

### 5.1. Giao tiếp đồng bộ phù hợp khi nào?

REST/HTTP hoặc gRPC thường phù hợp khi caller cần kết quả ngay để tiếp tục xử lý: kiểm tra quyền, lấy thông tin sản phẩm mới nhất, yêu cầu giữ chỗ hoặc hỏi trạng thái một giao dịch. Đổi lại, caller phụ thuộc vào độ trễ và tình trạng hoạt động của callee trong thời gian thực.

Khi thiết kế, đừng chỉ ghi “Booking gọi Availability”. Hãy xác định:

- Caller cần câu trả lời nào để đưa ra quyết định?
- Nếu kết nối timeout, làm sao biết thao tác có được thực thi hay chưa?
- Hành động có **idempotent** không khi yêu cầu lặp?
- Thông tin nào được trả về và ai được phép xem?
- Có yêu cầu bảo đảm phiên bản đồng thời, tránh cập nhật đè không?

### 5.2. Ví dụ hợp đồng tạo booking

Một lựa chọn là tạo booking theo tiến trình bất đồng bộ và cho client truy vấn trạng thái. Request HTTP mẫu:

~~~http
POST /v1/bookings HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 937e47cf-9886-44fd-9a39-26bdc8072c67

{
  "listingId": "listing_42",
  "checkIn": "2026-12-10",
  "checkOut": "2026-12-12",
  "guestCount": 2
}
~~~

Một phản hồi khi yêu cầu đã được chấp nhận để xử lý, nhưng giao dịch chưa hoàn tất:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /v1/bookings/booking_913

{
  "bookingId": "booking_913",
  "status": "PENDING",
  "statusUrl": "/v1/bookings/booking_913"
}
~~~

Trong ví dụ này, hệ thống phải quy định rõ:

1. Token được xác thực và quyền tạo booking được kiểm tra ở phía server; không tin hoàn toàn vào mã khách hàng do client tự gửi.
2. Ngày check-out phải sau check-in; guestCount phải phù hợp chính sách listing.
3. Cùng một **Idempotency-Key** trong đúng phạm vi tenant/người gọi và thời hạn lưu khóa, với cùng nội dung yêu cầu, trả về cùng kết quả logic thay vì tạo booking khác. Nếu dùng lại khóa nhưng payload khác, cần phản hồi lỗi xung đột có quy định rõ.
4. 202 Accepted nghĩa là **đã nhận để xử lý**, không có nghĩa booking được xác nhận. Client phải đọc trạng thái tiếp theo hoặc nhận thông báo hợp lệ.
5. Định danh, số tiền, múi giờ, giới hạn số khách và quy tắc hủy cần được định nghĩa bằng chính sách/schema; không suy ra từ kiểu dữ liệu đơn thuần.

Mã lỗi cần được định nghĩa nhất quán, chẳng hạn:

| Trường hợp | Hành vi hợp đồng có thể lựa chọn |
|---|---|
| Thiếu hoặc sai token | HTTP 401; không đưa thông tin nhạy cảm vào lỗi |
| Có danh tính nhưng thiếu quyền | HTTP 403; không tiết lộ thông tin booking của người khác |
| Dữ liệu đầu vào không hợp lệ | HTTP 400 hoặc 422 theo quy ước nhất quán, có mã lỗi nghiệp vụ |
| Giữ chỗ xung đột với lượt đặt khác | HTTP 409 nếu phát hiện đồng bộ, hoặc trạng thái FAILED với reason code nếu xử lý bất đồng bộ |
| Quá tải tạm thời | HTTP 429 hoặc 503, có quy tắc Retry-After/backoff |
| Caller timeout | Kết quả **chưa biết**; truy vấn theo idempotency key hoặc bookingId trước khi thử lại |

Không nên để consumer suy ra “giao dịch chắc chắn thất bại” từ HTTP timeout. Request có thể đã được commit nhưng response thất lạc.

### 5.3. Hợp đồng về concurrency

Với tài nguyên có thể được nhiều bên cập nhật, cân nhắc optimistic locking: bản ghi có version hoặc ETag; cập nhật chỉ hợp lệ khi version vẫn như khi đọc. Ví dụ, Availability Service kiểm tra và giảm số chỗ còn lại trong transaction của chính nó. Cơ chế này bảo vệ invariant tại nơi sở hữu dữ liệu; một bước kiểm tra availability trước đó ở UI chỉ cung cấp thông tin tạm thời.

## 6. Hợp đồng sự kiện bất đồng bộ

### 6.1. Event là sự thật đã xảy ra, command là yêu cầu

- **Command**: yêu cầu một owner thực hiện hành động (ví dụ, ReserveAvailability). Owner có thể chấp nhận hoặc từ chối sau khi kiểm tra chính sách.
- **Domain/integration event**: thông báo sự thật đã xảy ra và được công bố (ví dụ, BookingConfirmed). Consumer có thể phản ứng mà không thay đổi kết quả đã xảy ra.
- **Query**: hỏi thông tin mà không yêu cầu đổi trạng thái.

Đặt tên sự kiện theo **sự thật đã hoàn tất** thường giúp tránh hiểu nhầm. Một thông báo BookingConfirmationRequested không được consumer đối xử như BookingConfirmed.

### 6.2. Envelope sự kiện cần đủ ngữ cảnh

Ví dụ một sự kiện tích hợp sau khi booking đã xác nhận:

~~~json
{
  "eventId": "evt_01JXY99",
  "eventType": "BookingConfirmed",
  "eventVersion": 1,
  "occurredAt": "2026-12-01T09:16:22Z",
  "producer": "booking-service",
  "correlationId": "req_548",
  "tenantId": "tenant_7",
  "data": {
    "bookingId": "booking_913",
    "listingId": "listing_42",
    "checkIn": "2026-12-10",
    "checkOut": "2026-12-12"
  }
}
~~~

Hợp đồng sự kiện cần mô tả rõ:

- **eventId** dùng để nhận diện sự kiện và chống xử lý lặp theo phạm vi lưu dấu đã định nghĩa.
- **eventType + eventVersion** giúp consumer chọn đúng schema và quy tắc tương thích.
- **occurredAt** là thời điểm sự kiện nghiệp vụ xảy ra, không đồng nghĩa thời điểm consumer nhận; nên dùng ISO 8601 có múi giờ rõ ràng.
- **correlationId** phục vụ truy vết luồng xử lý qua nhiều dịch vụ, không dùng làm khóa chống trùng mặc định.
- **tenantId** định danh phạm vi dữ liệu; phía consumer phải xác thực/ủy quyền theo môi trường và nguồn tin cậy.
- **data** chỉ chứa thuộc tính consumer thực sự cần; tránh mang thông tin thẻ thanh toán, giấy tờ hoặc dữ liệu cá nhân không cần thiết.

Contract còn phải nêu **thứ tự**, **số lần giao hàng**, **retention**, khả năng **replay**, **DLQ** (*dead-letter queue*), quy tắc schema registry và thời gian tối đa mà consumer dự kiến nhận cập nhật. Nhiều hệ thống message broker có thể giao sự kiện ít nhất một lần (*at-least-once*); consumer cần chịu được trùng lặp.

### 6.3. Chống phụ thuộc ẩn trong sự kiện

Sự kiện nên mang đủ ngữ cảnh để consumer hoàn thành tác vụ được thiết kế mà không phải gọi ngược nhiều API trong cùng một chuỗi bắt buộc. Tuy nhiên, không nên biến event thành bản sao toàn bộ bảng nội bộ; điều đó tạo coupling và tăng rủi ro lộ dữ liệu. Hãy thiết kế **integration event** riêng với domain event nội bộ khi cần bảo vệ quyền thay đổi và giữ ổn định hợp đồng.

## 7. Tính nhất quán và giao dịch qua nhiều dịch vụ

### 7.1. Một transaction cơ sở dữ liệu không tự trải trên các dịch vụ

Với một service duy nhất, thao tác ghi liên quan có thể dùng transaction ACID để bảo đảm tính nhất quán. Nhưng trong kiến trúc tách Booking, Availability và Payment thành các owner độc lập, việc cập nhật tất cả qua một transaction ACID thông thường không còn đơn giản. Giao thức giao dịch phân tán có thể tồn tại trong một số nền tảng, song thường tạo chi phí phối hợp, rủi ro giảm availability và coupling vận hành.

Thay vào đó, cần thiết kế **quy trình nghiệp vụ gồm nhiều trạng thái trung gian**. Đó là nơi saga, idempotency, sự kiện và tác vụ đối soát đóng vai trò quan trọng.

### 7.2. Ví dụ saga đặt phòng

Một workflow khả thi:

1. Booking tạo bản ghi **PENDING**, gắn idempotency key với request.
2. Booking yêu cầu Availability **giữ chỗ có thời hạn**. Availability thực hiện kiểm tra và ghi trạng thái hold trong transaction của mình.
3. Nếu giữ chỗ thành công, Booking yêu cầu Payment **ủy quyền thanh toán** theo transaction reference duy nhất.
4. Nếu thanh toán thành công, Booking điều phối việc xác nhận hold. Sau khi các điều kiện cần thiết được xác minh, Booking chuyển sang **CONFIRMED** và phát BookingConfirmed.
5. Nếu payment thất bại được xác nhận, Booking hủy workflow và yêu cầu giải phóng hold. Nếu một bước không xác định kết quả vì timeout, workflow chuyển sang trạng thái cần **truy vấn/đối soát**, tránh tự ý coi đó là thất bại.
6. Hệ thống xử lý hold hết hạn, hoàn tác hoặc hoàn tiền theo trạng thái thực tế và quy tắc nghiệp vụ, đồng thời có cảnh báo cho trường hợp không thể tự phục hồi.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant B as Booking
    participant A as Availability
    participant P as Payment
    participant E as Event Bus
    C->>B: Tạo booking (Idempotency-Key)
    B->>B: Ghi PENDING
    B->>A: Hold listing trong khoảng ngày
    A-->>B: holdId / declined
    alt Hold thành công
        B->>P: Authorize payment (reference cố định)
        P-->>B: Authorized / Declined / Unknown
        alt Payment đã được xác nhận hợp lệ
            B->>A: Confirm hold
            A-->>B: Confirmed
            B->>B: Ghi CONFIRMED + Outbox
            B->>E: Publish BookingConfirmed
        else Declined hoặc cần đối soát
            B->>B: FAILED hoặc RECONCILING
            B->>A: Release hold khi an toàn
        end
    else Hold bị từ chối
        B->>B: FAILED
    end
    C->>B: Kiểm tra bookingId
    B-->>C: Trạng thái hiện tại
~~~

Đây là sơ đồ logic minh họa. Trong thực tế, trạng thái Payment và Availability có thể thay đổi giữa các bước; phải có chính sách hết hạn hold, đối soát giao dịch, xử lý sự kiện tới muộn và thao tác bù cho trường hợp đã thu tiền nhưng xác nhận booking không thành công. Không được mặc định rằng các bước bù luôn thành công ngay.

### 7.3. Transactional outbox giải quyết khoảng trống nào?

Nếu Booking Service commit trạng thái CONFIRMED vào database rồi gặp sự cố **trước khi** gửi BookingConfirmed lên broker, hệ thống đã đổi dữ liệu nhưng các consumer không biết. Ngược lại, nếu gửi event trước khi commit database, consumer có thể nhận một thông báo về trạng thái chưa từng được ghi thành công.

**Transactional outbox** ghi cả thay đổi trạng thái và bản ghi sự kiện chờ phát hành **trong cùng một transaction của database thuộc Booking**:

~~~text
BEGIN TRANSACTION
  UPDATE bookings
    SET status = 'CONFIRMED'
    WHERE id = 'booking_913' AND status = 'PENDING';
  INSERT INTO outbox(event_id, type, payload, created_at)
    VALUES ('evt_01JXY99', 'BookingConfirmed', '{...}', NOW());
COMMIT

Outbox publisher / CDC:
  đọc outbox -> gửi broker -> đánh dấu đã phát theo cơ chế phù hợp
~~~

Publisher có thể gửi lại sau khi crash. Vì vậy, **outbox không tự bảo đảm xử lý đúng một lần từ đầu đến cuối**; consumer vẫn cần deduplication hoặc xử lý idempotent. Ví dụ, Notification Service lưu eventId đã xử lý trước khi gửi thư hoặc dùng khóa idempotency của dịch vụ email; lựa chọn cụ thể tùy khả năng phối hợp ghi và side effect.

### 7.4. Eventual consistency phải là một phần của hợp đồng

Nếu trang hồ sơ đọc projection do event cập nhật, ngay sau khi thanh toán thành công dữ liệu có thể chưa phản ánh trạng thái mới. UX và consumer phải biết sự khác nhau giữa **PENDING**, **CONFIRMED**, **FAILED** và **RECONCILING**, có đường lấy nguồn tin cậy cho thao tác nhạy cảm, và không coi “không thấy bản ghi trong read model” là “booking chắc chắn chưa tồn tại”.

Các điểm cần đặc tả:

- Thời gian trễ đồng bộ dự kiến và cách phát hiện khi vượt ngưỡng.
- Cách xử lý sự kiện trùng, tới sai thứ tự hoặc tới muộn.
- Quy tắc rebuild projection từ nguồn đáng tin cậy khi thiếu sự kiện.
- Ảnh hưởng tới nghiệp vụ khi consumer tạm thời không cập nhật kịp.

## 8. Tiến hóa hợp đồng mà không phá consumer

### 8.1. Tương thích không chỉ là “JSON vẫn parse được”

Thay đổi thường **có thể** tương thích:

- Thêm trường tùy chọn với ý nghĩa rõ ràng; consumer cũ được thiết kế để bỏ qua trường không biết.
- Thêm endpoint mới mà không thay hành vi endpoint cũ.
- Thêm loại event mới độc lập, không thay ngữ nghĩa loại event cũ.

Thay đổi thường **phá vỡ** hợp đồng:

- Xóa hoặc đổi tên trường mà consumer đang dùng; đổi type hoặc đơn vị tiền.
- Biến trường tùy chọn thành bắt buộc, thay ngữ nghĩa null/default.
- Đổi ý nghĩa trạng thái, bổ sung enum value khi consumer đang xử lý danh sách enum đóng.
- Thay thứ tự/bảo đảm giao sự kiện, xóa retention hoặc siết giới hạn tải vượt giả định hiện tại.
- Chuyển một thao tác từ thành công đồng bộ thành 202 bất đồng bộ mà không cung cấp giao thức chuyển tiếp.

Một thay đổi “thêm trường” cũng có thể gây lỗi nếu consumer cấu hình parser từ chối unknown properties. Tính tương thích phụ thuộc vào **hành vi thực tế của producer và consumer**, không phải một quy tắc chung áp đặt.

### 8.2. Expand–migrate–contract

Một quy trình an toàn khi cần chuyển từ trường totalAmount sang amountMinor là:

1. **Expand:** provider công bố trường mới, giữ trường cũ và tài liệu hóa chính xác đơn vị cùng quy tắc làm tròn.
2. **Migrate:** consumer chuyển dần sang trường mới; triển khai song song và đối chiếu kết quả bằng test.
3. **Observe:** đo lượng sử dụng trường cũ, theo dõi lỗi và xác minh consumer liên quan đã cập nhật.
4. **Contract:** thông báo hạn cuối, ngừng hỗ trợ trường cũ theo chính sách deprecation đã thống nhất, rồi mới loại bỏ.

Với event đã nằm trên broker hoặc trong kho replay, cần quyết định consumer sẽ đọc được bao nhiêu phiên bản và schema được lưu giữ bao lâu. Đôi khi cần event type/version mới thay vì cố giữ cùng sự kiện với ý nghĩa đã đổi.

### 8.3. Kiểm thử hợp đồng

Các lớp kiểm thử bổ trợ nhau:

| Kiểm thử | Xác nhận điều gì | Trách nhiệm |
|---|---|---|
| Schema / OpenAPI / AsyncAPI validation | Trường, type, định dạng, version phù hợp đặc tả | Provider công bố và CI xác minh |
| **Consumer-driven contract test** | Provider vẫn đáp ứng những kỳ vọng cụ thể đã khai báo của consumer | Consumer công bố kỳ vọng; provider chạy kiểm tra |
| Integration test với dependency thật hoặc môi trường tương đương | Timeout, auth, lỗi broker, mapping trạng thái | Nhóm tích hợp, platform và service owner |
| End-to-end nghiệp vụ | Trải nghiệm tạo/hủy booking qua nhiều dịch vụ đúng | Nhóm sản phẩm sở hữu luồng |
| Chaos / failover / replay test | Hệ thống phục hồi khi mất thông điệp, lặp, lỗi mạng, chậm replication | Nhóm vận hành phối hợp owner |

Contract test giúp phát hiện sai khác giao diện, nhưng **không thay thế kiểm thử nghiệp vụ, độ tin cậy và bảo mật**.

### 8.4. Quản lý vòng đời hợp đồng

Nên có registry hoặc kho tài liệu theo phiên bản, owner rõ ràng, quy trình review, thời gian thông báo deprecation và cơ chế quan sát consumer hiện hữu. Với API công khai hoặc nhiều nhóm phụ thuộc, cần ghi rõ compatibility policy và support window, tránh yêu cầu mọi đội triển khai cùng giờ.

## 9. Bảo mật, quyền riêng tư và trách nhiệm dữ liệu xuyên dịch vụ

### 9.1. Mỗi điểm giao tiếp là một ranh giới tin cậy

Ngay cả khi dịch vụ cùng chạy trong một VPC/cluster, chúng không nên mặc nhiên tin tưởng mọi request. Cần:

- Xác thực danh tính gọi dịch vụ, chẳng hạn workload identity, mTLS hoặc token có issuer, audience và thời hạn phù hợp.
- Kiểm tra **authorization tại nơi thực thi nghiệp vụ**, kể cả quyền theo tài nguyên và tenant.
- Áp dụng least privilege cho database role, topic publish/subscribe, secret và service account.
- Mã hóa đường truyền; không ghi token, dữ liệu thẻ hoặc thông tin cá nhân nhạy cảm vào log.
- Giới hạn quyền đọc event theo nhu cầu và phân loại payload trước khi phát tán lên broker.
- Theo dõi audit cho truy cập dữ liệu quan trọng, bao gồm hoạt động quản trị và yêu cầu xóa dữ liệu.

Ví dụ: Booking Service có thể gọi Customer Profile để lấy thông tin phục vụ xác nhận, nhưng không nên nhận toàn bộ hồ sơ và giấy tờ tùy thân chỉ vì cần tên hiển thị. Một event gửi tới nhiều consumer càng cần giảm dữ liệu nhạy cảm trong payload.

### 9.2. Data ownership không thay thế data governance

Trong kiến trúc nhiều dịch vụ, dữ liệu có thể xuất hiện trong source DB, projection, cache, backup, stream, log, kho phân tích và hệ thống đối tác. Chủ sở hữu dữ liệu cần thống nhất chính sách vòng đời và xóa/ẩn danh; từng dịch vụ giữ bản sao phải biết nghĩa vụ liên quan.

Nếu có yêu cầu về **nơi lưu/xử lý dữ liệu hoặc chủ quyền dữ liệu**, cần rà cả replica, event broker, DLQ, log, backup, đội hỗ trợ và dịch vụ thứ ba. Khả năng cấu hình region của database chính không tự bảo đảm toàn bộ pipeline tuân thủ. Quy định pháp lý phải được đối chiếu theo loại dữ liệu, phạm vi và thời điểm áp dụng.

## 10. Đánh đổi kiến trúc cloud và năng lực vận hành

### 10.1. Dịch vụ nhỏ hơn chưa chắc tốt hơn

Một **modular monolith** với các module có quyền sở hữu dữ liệu rõ ràng có thể là bước đầu phù hợp nếu đội ngũ nhỏ, quy trình nghiệp vụ gắn kết chặt và chưa có nhu cầu scale/deploy độc lập. Cùng một transaction trong một tiến trình có thể đơn giản hơn, dễ quan sát hơn và ít điểm lỗi mạng hơn.

Tách thành microservices thường có lợi khi các bounded context cần nhịp phát triển khác nhau, quy mô tải khác nhau hoặc quyền vận hành riêng; đổi lại phải giải quyết truyền thông, phân tán trạng thái, tính nhất quán, bảo mật giữa dịch vụ, tracing và chi phí hạ tầng.

### 10.2. Chọn giao tiếp theo nhu cầu thực tế

| Cách giao tiếp | Lợi thế | Cái giá / rủi ro |
|---|---|---|
| API đồng bộ | Trả kết quả ngay; dễ hiểu cho truy vấn/kiểm tra cần phản hồi tức thì | Coupling về độ trễ, khả năng sẵn sàng; timeout dây chuyền |
| Event bất đồng bộ | Producer ít phụ thuộc consumer tức thời; tốt cho fan-out và xử lý nền | Eventual consistency, duplicate, ordering, DLQ, versioning |
| Read model do event cập nhật | Truy vấn nhanh, giảm tải service owner | Dữ liệu trễ, logic projection và khả năng rebuild |
| Shared database có ranh giới module | Đơn giản trong hệ thống còn gắn kết; transaction cục bộ | Khó thay đổi riêng, dễ rò quyền và gắn chặt schema nếu kiểm soát lỏng |

**Đừng chuyển toàn bộ API thành event** chỉ để “giảm coupling”. Chọn đồng bộ khi cần kết quả trực tiếp và có thể xử lý lỗi rõ ràng; chọn bất đồng bộ khi nghiệp vụ chấp nhận tiến trình nhiều bước và cần giảm phụ thuộc thời gian thực.

### 10.3. Khung Well-Architected

| Trụ cột | Câu hỏi thiết kế | Biện pháp / đánh đổi |
|---|---|---|
| **Operational Excellence – Vận hành** | Ai sở hữu hợp đồng, sự cố và migration? | Service catalog, owner, tracing, log, dashboard; nhiều service tăng công giám sát |
| **Security – Bảo mật** | Ai được xem/sửa dữ liệu và nhận event? | IAM theo workload, authz theo tenant, mã hóa, tối thiểu hóa payload |
| **Reliability – Độ tin cậy** | Một service hoặc broker lỗi sẽ ảnh hưởng luồng nghiệp vụ thế nào? | Timeout, retry có giới hạn, idempotency, outbox, DLQ, saga, khôi phục |
| **Performance Efficiency – Hiệu năng** | Luồng nào cần đọc gần, luồng nào cần nhất quán mạnh? | Cache/projection giúp tốc độ nhưng làm phức tạp đồng bộ; tránh fan-out đồng bộ |
| **Cost Optimization – Chi phí** | Mỗi DB, event, API call và bản sao gây chi phí gì? | Tách dịch vụ khi có giá trị; quản lý retention, traffic, replica và tài nguyên |
| **Sustainability – Bền vững** | Có tạo dữ liệu, truyền tin và compute không cần thiết không? | Giảm event payload, bản sao vô ích và polling quá dày |

### 10.4. Điểm lỗi và đường cong chi phí

Mỗi lần gọi thêm dịch vụ trong đường xử lý đồng bộ bổ sung độ trễ và một nơi có thể lỗi. Nếu Booking gọi lần lượt nhiều dependency trước khi trả response, độ trễ đuôi (*tail latency*) có thể tăng và khả năng phục vụ đầu cuối chịu ảnh hưởng từ tất cả dependency. Các cách giảm rủi ro gồm deadline xuyên chuỗi, retry có backoff/jitter, giới hạn số lần thử, bulkhead, circuit breaker khi phù hợp và giải pháp giảm chức năng (*graceful degradation*).

Trên cloud, chi phí không chỉ là CPU: API gateway, load balancer, kết nối liên zone/region, managed database, broker, egress, log, trace và sao lưu đều cần ngân sách. Theo dõi tải và số bản sao trước khi quyết định mỗi dịch vụ một cluster hoặc event lưu giữ dài hạn.

## 11. Quy trình thiết kế một ranh giới dịch vụ từ đầu

**Bước 1 — Ghi yêu cầu nghiệp vụ.** Liệt kê lệnh, truy vấn, quy tắc bất biến (invariant), mức độ bảo mật, độ trễ, RTO/RPO, mức tải và thay đổi dự kiến.

**Bước 2 — Xác định bounded context và owner.** Với mỗi nhóm dữ liệu, ghi ai ra quyết định, ai có quyền ghi, ai chỉ đọc và bộ phận nào chịu trách nhiệm tuân thủ.

**Bước 3 — Vẽ luồng dữ liệu và giao dịch.** Đánh dấu dữ liệu nguồn, bản sao, event, log, backup và đường dữ liệu ra đối tác. Chọn chỗ cần transaction cục bộ và chỗ chấp nhận eventual consistency.

**Bước 4 — Thiết kế hợp đồng.** Viết request/response hoặc event schema, ngữ nghĩa trạng thái, mã lỗi, idempotency key, SLA/SLO, authn/authz, version và chính sách deprecation.

**Bước 5 — Chọn hạ tầng.** Quyết định database/schema riêng, managed compute, API gateway, broker, mạng riêng, secret manager, observability, backup và DR theo yêu cầu.

**Bước 6 — Kiểm tra lúc lỗi.** Diễn tập timeout sau commit, event trùng, event tới muộn, consumer dừng, database lỗi, thiếu quyền, dữ liệu trễ và schema mới khi consumer chưa nâng cấp.

**Bước 7 — Vận hành vòng đời.** Có dashboard và SLO, owner cảnh báo, runbook, cách replay/khôi phục, lịch rà soát quyền, quy trình thay đổi API/event và kế hoạch retire phiên bản cũ.

### 11.1. Mẫu quyết định kiến trúc (ADR) ngắn

~~~text
Quyết định: Booking là owner của trạng thái booking.
Nguồn dữ liệu chuẩn: bookings và outbox thuộc Booking Service.
Consumer: Notification, Search projection, Reporting.
Đường đọc: GET /v1/bookings/{id} cho trạng thái chuẩn;
          projection chỉ dùng cho danh sách/tìm kiếm chấp nhận trễ.
Đường ghi: chỉ Booking Service; hệ thống khác gửi command qua API.
Hợp đồng: BookingConfirmed v1; eventId, bookingId, occurredAt,
          tenantId, correlationId; không chứa thông tin thẻ.
Nhất quán: outbox + at-least-once delivery + consumer idempotent.
Lỗi: timeout chưa rõ kết quả -> truy vấn trạng thái hoặc đối soát.
Chuyển phiên bản: expand-migrate-contract, có consumer contract tests.
Owner: nhóm Booking; điều phối với Platform/Security.
Bằng chứng: kết quả test replay, failover, khôi phục và audit quyền.
~~~

ADR cần gắn với yêu cầu thực tế và được cập nhật khi thay đổi topology hoặc hợp đồng. Không nên sao chép các mục tiêu SLO, thời hạn retention hay vùng lưu trữ từ ví dụ mà không có chủ sở hữu nghiệp vụ phê duyệt.

## 12. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Nhiều dịch vụ cùng sửa một bảng nghiệp vụ | Không rõ nguồn chuẩn, dễ phá invariant | Chỉ định owner, giới hạn quyền ghi, truy cập qua hợp đồng |
| Public toàn bộ schema nội bộ như API/event | Không thể thay cấu trúc bên trong; lộ dữ liệu | Thiết kế DTO/integration event ổn định theo nhu cầu consumer |
| Dùng timestamp để đoán “bản ghi mới nhất” cho mọi trường | Mất cập nhật hoặc xung đột nghiệp vụ | Định nghĩa version, conflict policy và nơi quyết định trạng thái |
| Timeout được coi là giao dịch thất bại | Thử lại có thể tạo nhiều booking/thanh toán | Idempotency key, correlation, trạng thái UNKNOWN/RECONCILING |
| Gửi event sau khi commit mà không có outbox | Trạng thái đổi nhưng không phát event khi crash | Outbox/CDC hoặc cơ chế công bố tin cậy tương đương |
| Giả định broker không giao tin trùng hoặc sai thứ tự | Gửi nhiều thông báo, tính tiền/lệnh sai | Consumer idempotent, kiểm tra version/order theo entity |
| Đổi enum hoặc ý nghĩa trường mà không thông báo | Consumer vẫn parse nhưng hành vi sai | Versioning, compatibility test, deprecation |
| Đồng bộ mọi thông tin giữa mọi dịch vụ | Bản sao khó kiểm soát, tăng egress và vấn đề riêng tư | Chỉ sao chép dữ liệu cần thiết, có retention và owner |
| Mỗi thao tác qua chuỗi API dài | Độ trễ và lỗi dây chuyền | Thiết kế giới hạn sync path, tối ưu cache/projection/async |
| Chia microservices trước khi hiểu miền nghiệp vụ | Quá nhiều đường mạng, data ownership mơ hồ | Bắt đầu với ranh giới module rõ và tách khi có nhu cầu |

## 13. Bài tập áp dụng

### Bài tập A — Ai là nguồn chuẩn?

Catalog lưu giá hiện tại của phòng là 1.500.000 đồng/đêm. Một booking đã hoàn tất trước đó chốt giá 1.200.000 đồng/đêm. Nhóm phát triển muốn đồng bộ mọi booking khi Catalog đổi giá.

**Câu hỏi:** Nên đồng bộ không?

**Gợi ý:** Không đồng bộ giá giao dịch đã chấp nhận theo giá niêm yết hiện tại. Pricing/Catalog sở hữu bảng giá công bố; Booking giữ snapshot giá đã được chốt, đơn vị tiền, chính sách khuyến mại và căn cứ tính tiền phù hợp, để lịch sử giao dịch không thay đổi sai.

### Bài tập B — API timeout sau khi đã thanh toán

Booking gọi Payment để ủy quyền tiền, request timeout. Client thử lại ngay bằng một mã giao dịch mới; kết quả phát sinh hai khoản ủy quyền.

**Câu hỏi:** Thiết kế lại cách xử lý?

**Gợi ý:** Dùng transaction reference/idempotency key ổn định cho cùng intent, truy vấn hoặc đối soát với Payment khi timeout, giới hạn retry, tránh tự tạo payment attempt khác khi kết quả lần đầu chưa xác định. Payment là owner trạng thái thanh toán, Booking cập nhật trạng thái từ kết quả đã được xác minh.

### Bài tập C — Event đến lặp và sai thứ tự

Một consumer nhận BookingCancelled rồi lại nhận một thông báo BookingConfirmed cũ do retry. Nếu chỉ ghi đè trạng thái theo event cuối cùng đã nhận, bản sao đọc sẽ chuyển sai về CONFIRMED.

**Câu hỏi:** Consumer cần thêm điều kiện gì?

**Gợi ý:** Sử dụng eventId cho dedup, version/sequence theo booking hoặc kiểm tra state transition có thể xác minh từ nguồn; thiết kế cách xử lý event out-of-order, replay và rebuild projection. Không dùng thời điểm nhận message làm thứ tự nghiệp vụ đáng tin cậy.

### Bài tập D — Thay đổi hợp đồng

Provider muốn bỏ trường totalAmount và trả amountMinor, đồng thời đưa thêm trạng thái REFUND_PENDING. Consumer mobile cũ chỉ chấp nhận ba giá trị enum hiện tại.

**Câu hỏi:** Những phần nào có nguy cơ breaking change?

**Gợi ý:** Xóa totalAmount là breaking; thêm REFUND_PENDING cũng có thể breaking với consumer parse enum đóng. Dùng expand-migrate-contract, trường mới không bắt buộc với consumer cũ, version mới hoặc cơ chế backward compatibility, contract tests và chiến lược nâng cấp ứng dụng mobile có lịch hỗ trợ rõ.

## 14. Checklist trước khi chốt thiết kế

- [ ] Mỗi thực thể và quy tắc nghiệp vụ quan trọng có owner và nguồn chuẩn được định danh.
- [ ] Chỉ owner có quyền thay đổi trực tiếp dữ liệu thuộc phạm vi của mình; cross-service write được kiểm soát.
- [ ] Phân biệt snapshot lịch sử, cache, projection và dữ liệu nguồn; mỗi bản sao có cơ chế cập nhật và xóa rõ ràng.
- [ ] API/event contract mô tả schema, ngữ nghĩa, timeout, lỗi, retry, idempotency, bảo mật, phiên bản và owner.
- [ ] Các invariant và transaction cục bộ được chỉ rõ; giao dịch nhiều dịch vụ có trạng thái trung gian, bù trừ và đối soát.
- [ ] Event quan trọng có cơ chế publish đáng tin cậy, consumer xử lý được duplicate/out-of-order/replay.
- [ ] Có chiến lược schema migration, compatibility tests, policy deprecation và phương án rollback.
- [ ] Token, quyền theo tenant, IAM, secret, network và event permissions được rà soát theo least privilege.
- [ ] Có SLI/SLO, dashboard, tracing, audit, DLQ/replay runbook và chủ sở hữu cảnh báo.
- [ ] Backup, restore, RTO/RPO, vùng lưu dữ liệu, log và bản sao được đánh giá theo yêu cầu nghiệp vụ và tuân thủ.
- [ ] Đã tính toán chi phí DB, broker, dữ liệu nhân bản, request liên dịch vụ và chi phí vận hành.
- [ ] Việc tách microservices có lý do rõ ràng so với phương án modular monolith.

**Ghi nhớ:** quyền sở hữu dữ liệu trả lời **ai có thẩm quyền quyết định và thay đổi sự thật nghiệp vụ**; hợp đồng dịch vụ trả lời **các bên trao đổi điều gì, có thể tin vào cam kết nào và điều gì xảy ra khi hệ thống thay đổi hoặc lỗi**. Hai yếu tố phải được thiết kế cùng nhau để dịch vụ có thể tiến hóa độc lập mà vẫn giữ đúng dữ liệu, bảo mật và trải nghiệm đầu cuối.

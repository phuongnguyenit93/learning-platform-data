# Tiến hóa trường dữ liệu, enum và ngữ nghĩa thao tác

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Hợp đồng và phiên bản  
> **Trọng tâm:** Tiến hóa API và message contract an toàn khi client, provider và các dịch vụ không nâng cấp cùng thời điểm.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích tại sao **contract** không chỉ là tên endpoint và JSON schema mà còn bao gồm ý nghĩa của trường dữ liệu, giá trị enum, quy tắc kiểm tra, mã lỗi và hiệu ứng của thao tác.
- Phân biệt **backward compatibility**, **forward compatibility**, **wire/schema compatibility** và **behavioral/semantic compatibility** trong hệ thống Microservices.
- Đánh giá rủi ro khi thêm, xóa, đổi tên, đổi kiểu, đổi ý nghĩa hoặc đổi tính bắt buộc của một trường trong request, response hay event.
- Xử lý enum có giá trị mới mà không âm thầm biến một trạng thái chưa biết thành trạng thái nghiệp vụ nguy hiểm.
- Thiết kế tiến hóa ngữ nghĩa thao tác HTTP hoặc message command, bao gồm idempotency, lỗi, điều kiện tiền đề, transition và tác dụng phụ.
- Thực hiện lộ trình **expand → migrate → contract**, có quan sát, kiểm thử hợp đồng, mixed-version testing và phương án rollback.
- Viết ví dụ đơn giản với JSON/OpenAPI, Java/Spring Boot và trường hợp cần trao đổi dữ liệu giữa nhiều phiên bản.

## 2. Bài toán: service thay đổi trước khi mọi consumer kịp cập nhật

Giả sử Order Service công bố API:

~~~http
GET /v1/orders/ord-1001 HTTP/1.1
Accept: application/json
~~~

~~~json
{
  "id": "ord-1001",
  "status": "PENDING",
  "totalAmount": 340000
}
~~~

Có ít nhất ba consumer:

- Web frontend dùng dữ liệu để hiển thị đơn.
- Mobile app có thể ở phiên bản cũ trong nhiều tuần vì người dùng chưa nâng cấp.
- Fulfillment Service đọc trạng thái đơn để quyết định có tạo công việc đóng gói hay không.

Đội Order muốn thay đổi:

1. Thêm trường **currency**.
2. Tách **totalAmount** thành **amountMinorUnits**.
3. Thêm trạng thái đơn **AWAITING_PAYMENT_REVIEW**.
4. Thay ý nghĩa của **CONFIRMED** từ “đã thanh toán” thành “đã nhận yêu cầu đặt hàng”.
5. Đổi endpoint đặt hàng để trả về **202 Accepted** thay vì trả **201 Created** cùng đơn đã xác nhận.

Những thay đổi này **không tương đương nhau**. Thêm trường thường dễ tương thích hơn nếu consumer bỏ qua trường lạ. Đổi tên hoặc kiểu dữ liệu có thể làm consumer không giải mã được. Thêm enum có thể làm một client Java crash nếu switch không xử lý giá trị mới. Đổi ý nghĩa CONFIRMED nguy hiểm hơn nữa: JSON schema không đổi nhưng Fulfillment có thể giao hàng khi chưa đủ điều kiện.

**Nguyên tắc nền tảng:** tính tương thích được xác định bởi **hành vi của provider mới với consumer cũ và provider cũ với consumer mới**, không chỉ bởi file OpenAPI có còn biên dịch hay không.

### 2.1. Vì sao vấn đề nổi bật trong Microservices?

Các nhóm có thể deploy service độc lập, nhưng tại một thời điểm:

~~~text
                Các phiên bản đang cùng tồn tại

Web v5  -------+
Mobile v2 -----+---> Order API v3
Mobile v4 -----+
Fulfillment v7-+

Order v2 event ------> Consumer v5 đang chờ backlog cũ
Order v3 event ------> Consumer v6 trong một partition khác
~~~

Một provider được nâng cấp không bảo đảm mọi consumer, worker và event còn tồn trong broker đã nâng cấp. Thực tế có thể tồn tại:

- Rolling deployment: nhiều phiên bản cùng chạy trong vài phút hoặc lâu hơn.
- Mobile app và client đối tác nâng cấp ngoài quyền kiểm soát trực tiếp.
- Consumer đọc event được lưu từ nhiều ngày trước.
- Cache/CDN giữ response cũ.
- Blue–green hoặc canary tạo traffic đi tới các phiên bản khác nhau.
- Các service nhận thay đổi theo thời điểm release riêng biệt.

Vì thế thiết kế contract phải chịu được **cửa sổ mixed-version** và công bố rõ khi nào một thay đổi thật sự breaking.

## 3. Contract gồm nhiều lớp

Một contract API/event có thể được chia thành các lớp:

| Lớp | Ví dụ | Điều phải giữ ổn định hoặc công bố thay đổi |
| --- | --- | --- |
| **Transport** | HTTP, HTTPS, Kafka, gRPC | Kiểu kết nối, content type, timeout, message delivery |
| **Shape/schema** | Tên trường, kiểu dữ liệu, required, enum | Payload nào được phép và consumer giải mã ra sao |
| **Validation** | Quantity > 0, amount có giới hạn, chuỗi ngày hợp lệ | Điều kiện request được chấp nhận |
| **Semantics** | CONFIRMED có nghĩa gì; giá trị totalAmount theo đơn vị nào | Ý nghĩa nghiệp vụ, không chỉ cú pháp |
| **Operation** | POST đặt hàng tạo đơn hay chỉ xếp hàng xử lý | Preconditions, side effects, idempotency, kết quả |
| **Error** | 400, 409, 422, 429; business error code | Caller phân loại và khôi phục như thế nào |
| **Temporal** | Thời điểm event xuất hiện, tính cuối cùng của kết quả | Thứ tự, độ trễ, timeout, eventual consistency |
| **Security** | Scope, quyền tài nguyên, thông tin nhạy cảm | Ai được truy cập; thay đổi có tăng/giảm quyền không |
| **Operational** | Rate limits, pagination, field size, retention | Consumer có cần đổi lưu lượng hoặc cách truy vấn không |

**Schema-compatible** nghĩa là định dạng có thể chấp nhận/đọc theo một bộ quy tắc nhất định; **semantically compatible** đòi ý nghĩa và hành vi mà consumer dựa vào không bị phá vỡ. Một thay đổi có thể qua schema check nhưng vẫn sai nghiệp vụ.

### 3.1. Hai chiều tương thích

- **Backward compatibility:** consumer cũ có thể làm việc đúng với dữ liệu/hành vi provider mới trong phạm vi contract được hứa hỗ trợ.
- **Forward compatibility:** consumer mới có thể tiếp tục làm việc đúng khi gặp dữ liệu/hành vi provider cũ, ví dụ trong lúc rollout hoặc đọc backlog.

Các thuật ngữ đôi khi được định nghĩa theo chiều schema reader/writer trong từng nền tảng serialization. Vì vậy trong thảo luận thực tế nên ghi rõ **ai là writer/provider, ai là reader/consumer, phiên bản nào đang tương tác** để tránh hiểu nhầm.

~~~text
                  Provider v1     Provider v2
Consumer v1       Baseline         Backward-compat concern
Consumer v2       Forward concern  New baseline
~~~

Không phải hệ thống nào cũng cần cả bốn tổ hợp vận hành. Nhưng tổ hợp nào có thể xuất hiện do lịch deploy thì phải kiểm thử theo contract.

### 3.2. Tolerant reader có giới hạn

Nhiều JSON consumer được thiết kế để **bỏ qua trường chưa biết**. Điều này giúp thêm field vào response ít phá vỡ hơn. Tuy nhiên không nên biến “tolerant reader” thành việc nuốt mọi lỗi:

- Bỏ qua trường bổ sung vô hại thường chấp nhận được.
- Bỏ qua một trường mà tác vụ cần để đảm bảo an toàn có thể làm sai nghiệp vụ.
- Trả UNKNOWN cho một enum chưa biết phải có xử lý phù hợp, không mặc định xem là SUCCEEDED.
- Không tự chuyển giá trị sai kiểu hoặc sai tiền tệ thành một mặc định tùy tiện.

Một consumer an toàn phải **chấp nhận có chọn lọc** và thất bại rõ khi không thể bảo toàn ngữ nghĩa.

## 4. Phân loại thay đổi trường dữ liệu

### 4.1. Thêm trường vào response

Provider v1:

~~~json
{
  "id": "ord-1001",
  "totalAmount": 340000
}
~~~

Provider v2:

~~~json
{
  "id": "ord-1001",
  "totalAmount": 340000,
  "currency": "VND"
}
~~~

Thay đổi này **có thể** tương thích với consumer cũ nếu:

- Consumer có khả năng bỏ qua trường lạ.
- Không có logic kiểm strict schema từ chối thuộc tính ngoài danh sách.
- Trường bổ sung không làm thay đổi ý nghĩa các trường cũ.
- Kích thước payload hoặc yêu cầu bảo mật không tạo tác động ngoài dự kiến.

Không được tuyên bố “thêm field luôn backward-compatible” vì consumer có thể dùng strict DTO/deserializer, schema validator hoặc signature/canonicalization phụ thuộc toàn bộ payload.

### 4.2. Thêm trường vào request

Giả sử v1 tạo đơn bằng:

~~~json
{
  "productId": "book-01",
  "quantity": 2
}
~~~

V2 thêm:

~~~json
{
  "productId": "book-01",
  "quantity": 2,
  "couponCode": "FALLSALE"
}
~~~

Trường mới nên là **tùy chọn khi có consumer cũ**. Nếu v2 yêu cầu couponCode trong mọi request, client v1 sẽ bị từ chối dù trước đây hợp lệ. Nếu muốn đưa một trường mới thành bắt buộc, phải có lộ trình nâng cấp, default an toàn hoặc API version mới với contract rõ.

Trường nullable/optional không nhất thiết có cùng ý nghĩa trên mọi hệ thống. Ví dụ couponCode vắng mặt có thể nghĩa là không áp dụng coupon; còn couponCode = null có thể được hiểu là yêu cầu xóa coupon. Cần công bố rõ.

### 4.3. Missing, null, giá trị rỗng và mặc định

Xét bốn request:

~~~json
{}
~~~

~~~json
{"nickname": null}
~~~

~~~json
{"nickname": ""}
~~~

~~~json
{"nickname": "Lan"}
~~~

Chúng có thể mang bốn ý nghĩa khác nhau:

| Hình thức | Một cách hiểu có thể có | Rủi ro khi đổi |
| --- | --- | --- |
| Không có field | Không cập nhật hoặc dùng default theo contract | Provider mới đổi default làm client cũ thay đổi hành vi |
| Field = null | Xóa giá trị hoặc báo “chưa biết”, tùy contract | Bị giải mã thành missing, mất ý định |
| Field = chuỗi rỗng | Giá trị rỗng hợp lệ hoặc bị validation từ chối | Provider siết ràng buộc làm request cũ lỗi |
| Field có giá trị | Cập nhật theo giá trị | Đổi format/range làm consumer không tương thích |

Trong **PATCH**, khác biệt missing và null đặc biệt quan trọng: tùy patch format, missing nghĩa là giữ nguyên, còn null có thể xóa field. Tuy nhiên JSON Patch và JSON Merge Patch có semantics khác nhau; không áp dụng một quy tắc cho mọi PATCH. Contract phải mô tả định dạng và phép biến đổi.

### 4.4. Đổi tên field: không xóa ngay

Đổi totalAmount thành amountMinorUnits không nên triển khai bằng cách xóa field cũ ở provider trước khi consumer nâng cấp.

Lộ trình minh họa:

~~~text
v1:
  totalAmount

Giai đoạn mở rộng:
  totalAmount
  amountMinorUnits

Giai đoạn chuyển:
  client mới đọc amountMinorUnits;
  client cũ vẫn đọc totalAmount

Giai đoạn thu hẹp:
  sau khi xác nhận không còn consumer cần totalAmount,
  loại bỏ field này theo chính sách deprecation/version.
~~~

Trong giai đoạn cả hai field tồn tại:

- Phải xác định **một nguồn sự thật** để tính hai representation, không để chúng trôi khác nhau.
- Nếu cả hai field được client gửi, cần quy tắc precedence hoặc từ chối trường hợp mâu thuẫn.
- Cần monitor usage để biết khi nào có thể ngừng hỗ trợ.
- Không giả định “tất cả client đã sửa” chỉ vì repository chính đã nâng version.

Nếu field mới thay đổi cả đơn vị hoặc ý nghĩa, cần mô tả đầy đủ chứ không chỉ nêu đổi tên.

### 4.5. Đổi kiểu dữ liệu

| Thay đổi | Nguy cơ |
| --- | --- |
| number → string | Consumer dùng DTO kiểu số có thể giải mã thất bại |
| integer → decimal | Mất chính xác, sai phép tính hoặc serialization khác |
| scalar → array | Consumer giả định một giá trị sẽ lỗi |
| string → object | Client cũ không hiểu cấu trúc mới |
| date string → timestamp number | Đổi đơn vị, timezone, precision |
| enum string → integer | Sai mapping, gây chuyển trạng thái nguy hiểm |
| int32 → int64 | Client JS/DB/serializer có thể có giới hạn và khác biệt precision |

Ví dụ tổng tiền:

~~~json
{"totalAmount": 340000}
~~~

Nếu giá trị cũ ngầm hiểu “VND nguyên đơn vị”, provider mới không thể đổi ngầm sang “số đơn vị nhỏ nhất của mọi loại tiền” mà không công bố quy tắc. Với các đồng tiền có số chữ số thập phân khác nhau, người dùng có thể thấy giá sai dù JSON vẫn là number.

Một hướng an toàn:

~~~json
{
  "price": {
    "amountMinorUnits": "340000",
    "currency": "VND"
  }
}
~~~

Dùng string cho số nguyên lớn có thể giúp bảo toàn độ chính xác xuyên ngôn ngữ, nhưng **đây là contract minh họa**; hệ thống có thể dùng integer hoặc decimal tùy giới hạn và chuẩn đã chọn. Phải định nghĩa đơn vị, rounding, currency và range bằng văn bản.

### 4.6. Thêm ràng buộc validation cũng có thể phá compatibility

Một field vốn cho phép quantity = 0 nhưng v2 cấm giá trị đó sẽ làm request của client cũ bị từ chối, dù schema vẫn ghi integer. Thay đổi regex, min/max length, đơn vị tiền, timezone, default hoặc uniqueness rule cũng là thay đổi hợp đồng.

**Hướng xử lý:** phân tích cách consumer hiện dùng, thông báo deprecation, quan sát tỷ lệ request theo pattern cũ, sau đó thay đổi theo lộ trình. Nếu rule mới là yêu cầu an toàn bắt buộc, cần phối hợp và thông báo rõ vì có thể phải chấp nhận breaking change.

## 5. Enum là giao diện trạng thái nghiệp vụ, không chỉ danh sách hằng số

Giả sử Payment API công bố:

~~~json
{
  "paymentId": "pay-91",
  "status": "PENDING"
}
~~~

Các giá trị ban đầu: PENDING, SUCCEEDED, FAILED.

Sau đó Payment bổ sung **REQUIRES_ACTION** để mô tả trường hợp người dùng phải thực hiện 3-D Secure hoặc thao tác xác nhận bổ sung.

Một client cũ có logic:

~~~java
switch (status) {
    case PENDING -> showWaiting();
    case SUCCEEDED -> showSuccess();
    case FAILED -> showFailure();
}
~~~

Nếu kiểu status được giải mã trực tiếp thành enum Java không cho giá trị chưa biết, deserialization có thể ném exception ngay trước khi đến switch. Nếu client có default mà mặc định coi unknown là FAILED, người dùng có thể bị hiển thị thất bại dù giao dịch thực tế còn khả năng hoàn tất.

### 5.1. Enum mở và enum đóng

**Enum đóng (closed):** contract cam kết danh sách có giới hạn và thay đổi giá trị cần phát hành version/điều phối rõ. Dùng khi các giá trị hoàn toàn quyết định logic nhạy cảm và không có cách xử lý unknown an toàn.

**Enum mở (open/extensible):** consumer được yêu cầu chấp nhận giá trị mới trong tương lai, có nhánh unknown và xử lý theo quy tắc bảo toàn nghiệp vụ.

Không thể vừa thêm enum tùy ý vừa yêu cầu tất cả client cũ hành động đúng nếu giá trị mới thay đổi quyết định nghiệp vụ mà client không thể dự đoán.

### 5.2. Hành vi an toàn khi gặp enum lạ

| Tình huống | Chiến lược an toàn hơn |
| --- | --- |
| Trạng thái payment chưa nhận diện | Hiển thị “Đang xác minh” hoặc báo unsupported; không kết luận đã thu/không thu tiền |
| Trạng thái fulfillment mới | Không phát hành hàng nếu chưa có bằng chứng đủ điều kiện |
| Loại thông báo không quan trọng | Có thể bỏ qua theo contract và ghi telemetry |
| Giá trị quyền truy cập mới | Deny by default khi không hiểu scope/permission |
| Loại phí mới ảnh hưởng tổng tiền | Không tự coi như phí bằng 0; từ chối hoặc yêu cầu nâng cấp |
| Trạng thái UI ít nhạy cảm | Hiển thị nhãn fallback nếu không làm sai business rule |

**Unknown không đồng nghĩa Failed, Pending, Allowed hoặc Success.** Ý nghĩa fallback phải được định nghĩa theo miền. Thường nên lưu **giá trị raw** để quan sát và hỗ trợ xử lý về sau.

### 5.3. Java/Jackson: xử lý enum mới

Một cách dùng fallback explicit:

~~~java
public enum PaymentStatus {
    PENDING,
    REQUIRES_ACTION,
    SUCCEEDED,
    FAILED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Cần cấu hình Jackson được sử dụng bởi ứng dụng để hỗ trợ tính năng đọc unknown enum về giá trị mặc định:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE)
    .build();
~~~

**Chú ý:** ví dụ chỉ cho biết cơ chế có thể chọn, không đồng nghĩa thêm UNKNOWN là giải quyết hết. Nếu UNKNOWN được dùng để phán quyết giao hàng hoặc hoàn tiền thì vẫn phải kiểm soát branch nghiệp vụ. Tùy cấu hình framework và ObjectMapper thực tế, cần kiểm chứng bằng test request cho giá trị mới.

Một hướng khác là giữ status raw dạng String và ánh xạ sang mô hình domain có nhánh Unknown(rawValue), giúp bảo toàn giá trị gốc. Cách này thích hợp khi consumer cần log/tự động phân loại enum ngoài danh sách.

### 5.4. Không đổi ngầm ý nghĩa một enum cũ

Giả sử CONFIRMED trước đây có nghĩa “đơn được xác nhận sau khi đã thanh toán”. Nếu đổi thành “đơn vừa được tiếp nhận”, một consumer Fulfillment cũ vẫn coi CONFIRMED là đủ điều kiện giao hàng.

Đây là **breaking semantic change** dù chữ CONFIRMED và schema không thay đổi. Cách xử lý thường an toàn hơn là:

- Giữ nguyên ngữ nghĩa giá trị cũ.
- Công bố một trạng thái mới như ACCEPTED hoặc PAYMENT_PENDING.
- Tạo chuyển tiếp rõ ràng sang CONFIRMED chỉ khi đạt điều kiện nghiệp vụ cũ, hoặc
- Phát hành contract/version mới nếu không thể giữ ngữ nghĩa cũ.

Không nên dùng cùng một event/status name để báo hai sự kiện nghiệp vụ khác nhau.

### 5.5. Không tái sử dụng giá trị enum đã bị bỏ

Một enum cũ như REFUNDED không nên được tái sử dụng với nghĩa hoàn toàn mới chỉ vì “tiết kiệm tên”. Consumer có thể giữ dữ liệu cũ trong database, cache hoặc backlog và giải mã nó theo nghĩa trước đây. Nguyên tắc tương tự áp dụng với numeric enum: **không tái sử dụng số định danh cũ cho ý nghĩa mới**.

## 6. Tiến hóa ngữ nghĩa thao tác: thay đổi nguy hiểm nhất thường không nằm trong JSON

### 6.1. Thao tác create trả kết quả tức thì hay tạo job bất đồng bộ?

Contract v1:

~~~http
POST /v1/orders
Content-Type: application/json

{"cartId": "cart-88"}
~~~

~~~http
HTTP/1.1 201 Created
Location: /v1/orders/ord-1001
Content-Type: application/json

{"orderId": "ord-1001", "status": "CONFIRMED"}
~~~

Nếu contract v1 hứa **CONFIRMED** nghĩa là đơn hoàn tất các điều kiện đã định, client có thể ngay lập tức yêu cầu in nhãn hoặc xác nhận cho khách. Thay provider để trả:

~~~http
HTTP/1.1 202 Accepted
Location: /v2/order-operations/op-99

{"operationId": "op-99", "status": "PROCESSING"}
~~~

đã thay đổi **thời điểm hoàn tất và ngữ nghĩa phản hồi**. Dù client parse được JSON mới, hành vi có thể không tương thích.

Một migration đúng cần cung cấp contract mới hoặc lớp compatibility cho client cũ; định nghĩa rõ đã chấp nhận request, trạng thái đang xử lý, endpoint kiểm tra, các kết quả cuối và thời hạn nghiệp vụ.

### 6.2. GET, POST, PUT, PATCH và idempotency

| Thao tác | Ý nghĩa thường kỳ vọng | Một thay đổi cần thận trọng |
| --- | --- | --- |
| GET | Truy xuất biểu diễn tài nguyên, không gây side effect nghiệp vụ theo semantics an toàn của HTTP | Đưa lệnh thu tiền hoặc xác nhận đơn vào GET |
| POST | Xử lý thao tác/tạo tài nguyên theo contract; không mặc nhiên idempotent | Bắt đầu tự động retry mà không có khóa thao tác |
| PUT | Thay thế hoặc thiết lập trạng thái tài nguyên theo representation được công bố; có semantics idempotent | Đổi từ “đặt quantity = 2” sang “cộng quantity thêm 2” |
| PATCH | Áp dụng thay đổi từng phần theo media type/contract; có thể idempotent hoặc không | Đổi format JSON Patch sang JSON Merge Patch mà không thông báo |
| DELETE | Yêu cầu xóa/hủy tài nguyên theo contract, thường có semantics idempotent ở mức kết quả mong muốn | Đổi từ hủy bản nháp sang hoàn tiền/hủy giao dịch mà không định nghĩa riêng |

HTTP method cho biết một phần semantics, nhưng **business rules, trạng thái cuối và side effects** vẫn phải được contract định nghĩa. Một PUT có thể được triển khai sai, và một POST có thể idempotent khi có cơ chế idempotency đúng.

### 6.3. Ví dụ đổi ngầm cách cộng số lượng

V1:

~~~http
PUT /v1/carts/cart-7/items/book-01

{"quantity": 2}
~~~

Nghĩa là **đặt số lượng của dòng hàng về 2**.

Nếu v2 ngầm đổi cùng endpoint thành **thêm 2 cuốn**, request lặp sau timeout gây tăng số lượng ngoài ý định. JSON không đổi, route không đổi nhưng ngữ nghĩa thao tác đã bị phá. Hãy tạo operation khác như AddItemQuantity hoặc giữ contract cũ và giới thiệu phiên bản mới.

### 6.4. Preconditions và tính hợp lệ của chuyển trạng thái

Giả sử CancelOrder ban đầu chỉ chấp nhận khi đơn đang PENDING. Nếu provider mở rộng để tự động hoàn tiền khi đơn đã PAID, hành vi có thể ảnh hưởng tiền thật, SLA, audit và UX. Dù nhiều client thích tính năng mới, đây vẫn là thay đổi side effect cần nêu rõ.

Một contract command nên mô tả:

- Trạng thái nào được phép gọi.
- Quyền của caller và business owner.
- Điều gì được ghi bền và thời điểm commit.
- Side effect chính và phụ: reservation, payment, email, event.
- Kết quả khi request bị lặp hoặc đến muộn.
- Chính sách timeout/retry và cách tra cứu kết quả chưa biết.
- Mã lỗi nghiệp vụ có thể xảy ra.
- Tính cuối cùng của trạng thái và các chuyển tiếp hợp lệ.

### 6.5. Idempotency là một phần ngữ nghĩa, không phải chỉ header

~~~http
POST /v1/payments
Idempotency-Key: order-1001-payment-v1
Content-Type: application/json

{
  "orderId": "ord-1001",
  "amountMinorUnits": "340000",
  "currency": "VND"
}
~~~

Provider phải định nghĩa phạm vi khóa, TTL, xử lý hai request trùng đồng thời, payload khác nhau với cùng khóa và hành vi khi lần đầu vẫn PROCESSING.

Nếu trước đây retry cùng key trả cùng giao dịch, thay đổi implementation để mỗi lần gọi lại tạo một payment attempt mới là breaking semantic change nghiêm trọng dù route và schema không đổi.

Khi client nhận timeout, nó **không biết chắc provider chưa thực hiện side effect**. Không tự gửi POST mới với khóa mới trừ khi đã xác minh điều kiện nghiệp vụ.

## 7. Thay đổi error contract và HTTP status

Mã lỗi không chỉ để hiển thị toast; nhiều consumer dựa vào nó để quyết định retry, sửa input hay kết thúc workflow.

Ví dụ một response:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/stock-conflict",
  "title": "Cannot reserve stock",
  "status": 409,
  "code": "INSUFFICIENT_STOCK",
  "detail": "Requested quantity is unavailable"
}
~~~

Đây là cấu trúc minh họa có trường mở rộng code, dựa theo ý tưởng problem details; không phải tất cả API đều dùng cùng format. Contract cần định nghĩa rõ:

- **Machine-readable code** có ổn định không?
- HTTP status có ý nghĩa gì; có cần retry không?
- Lỗi nào do input, quyền, xung đột, giới hạn tốc độ hoặc dependency?
- Consumer cần xử lý những code chưa biết thế nào?
- Thông tin lỗi có thể bị che vì bảo mật hay không?

### 7.1. Những thay đổi dễ làm vỡ consumer

- Đổi code INSUFFICIENT_STOCK thành OUT_OF_STOCK mà không giữ alias hoặc version.
- Biến validation error 400 thành 500; client cũ sẽ retry không phù hợp.
- Thêm 429 nhưng client không biết Retry-After và tiếp tục tạo tải.
- Trả 200 với payload error cho thao tác trước đây trả 4xx; monitoring và retry logic bị sai.
- Thay lỗi “không đủ quyền” bằng “không tìm thấy tài nguyên” có thể hợp lý vì chính sách bảo mật, nhưng phải đánh giá consumer và hợp đồng quan sát.

Không nên hứa tất cả status/code cố định vĩnh viễn; thay vào đó cần **quy ước nhóm lỗi**, thông báo deprecation, handling unknown và chiến lược phiên bản.

### 7.2. Thêm giá trị lỗi mới giống thêm enum

Nếu error code được coi là enum đóng trong SDK, việc thêm code mới có thể làm lỗi giải mã. SDK nên có nhánh unknown, giữ raw code và chọn hành vi an toàn. Nhưng với thao tác nhạy cảm, unknown code không nên bị coi là lỗi tạm thời có thể retry vô hạn.

## 8. Tương thích response, request và event không giống nhau

### 8.1. Thêm field vào response

Thường chỉ cần consumer cũ bỏ qua field lạ, **nếu** contract cho phép field bổ sung. Nhưng việc thêm trường lớn chứa ảnh/file hoặc dữ liệu nhạy cảm có thể ảnh hưởng hiệu năng/bảo mật.

### 8.2. Thêm field vào request

Provider mới phải tiếp tục chấp nhận request cũ nếu muốn backward compatibility. Field mới không thể trở thành required ngay mà không có default hoặc migration hợp lệ.

Ngược lại, nếu client mới gửi field mà provider cũ chưa hiểu, cần biết provider cũ **bỏ qua field** hay **từ chối request**. Đừng mặc định hai hành vi tương đương: bỏ qua field quan trọng như discountPolicy có thể làm sai số tiền.

### 8.3. Thêm field vào event

Ví dụ event OrderPlaced v1:

~~~json
{
  "eventId": "evt-1",
  "eventType": "OrderPlaced",
  "orderId": "ord-1001",
  "occurredAt": "2026-01-01T10:00:00Z"
}
~~~

V2 bổ sung:

~~~json
{
  "eventId": "evt-1",
  "eventType": "OrderPlaced",
  "orderId": "ord-1001",
  "occurredAt": "2026-01-01T10:00:00Z",
  "orderTotal": {
    "amountMinorUnits": "340000",
    "currency": "VND"
  }
}
~~~

Consumer cũ có thể bỏ qua trường orderTotal, nhưng nếu sau này producer ngừng gửi orderId, consumer cũ lỗi. Event tồn tại trong broker hoặc archive lâu hơn thời gian deploy; **replay** có thể khiến consumer mới gặp payload từ nhiều version khác nhau.

### 8.4. Không thay sự kiện đã xảy ra bằng định nghĩa mới

Nếu OrderPlaced ban đầu nghĩa là “Order đã được persist” nhưng bây giờ muốn dùng cho “đơn đã thanh toán”, hãy tạo sự kiện khác như OrderConfirmed/PaymentCompleted phù hợp với chủ sở hữu nghiệp vụ. Không đổi ngữ nghĩa của event cũ và kỳ vọng tất cả consumer tự hiểu.

### 8.5. Event version và event schema

Một số hệ thống version tên event (OrderPlacedV2), một số đặt schemaVersion trong envelope, một số dùng schema registry. Chọn cách nào cần trả lời:

- Consumer cũ có còn cần xử lý được dữ liệu mới không?
- Consumer mới phải replay được dữ liệu cũ bao lâu?
- Có bao nhiêu producer/consumer và ai sở hữu lộ trình?
- Khi replay, business semantics của event đã thay đổi không?
- Thứ tự, partition key, idempotency và định danh event có giữ nguyên không?

Version schema giúp phân loại biểu diễn; nó **không tự động dịch đúng ý nghĩa nghiệp vụ** nếu domain semantics thay đổi.

## 9. JSON, OpenAPI và Protobuf: khác biệt cần hiểu

### 9.1. JSON/OpenAPI

Với JSON schema/OpenAPI, ta có thể mô tả tên field, type, required, nullable, enum, format và ràng buộc. Nhưng:

- Tùy parser, trường lạ có thể bị bỏ qua hoặc bị từ chối.
- Khai báo required trong response khác với required trong request.
- JSON null và field vắng mặt có thể khác nhau.
- Format như date-time không thay thế quy tắc timezone/precision.
- Một enum đóng trong schema có thể làm consumer tự sinh code không chịu giá trị mới.

Ví dụ OpenAPI minh họa:

~~~yaml
components:
  schemas:
    OrderView:
      type: object
      required: [id, status]
      properties:
        id:
          type: string
        status:
          type: string
          description: >
            Consumer phải xử lý trường hợp giá trị status chưa nhận diện.
            Không được mặc định coi là CONFIRMED.
        currency:
          type: string
          description: Mã tiền tệ theo contract áp dụng.
        totalAmount:
          type: integer
          format: int64
          deprecated: true
        amountMinorUnits:
          type: string
          description: Số đơn vị nhỏ nhất, biểu diễn số nguyên thập phân.
~~~

Nếu dùng thuộc tính enum khép kín, OpenAPI generator có thể tạo enum Java đóng; cần xét cách client chịu được trạng thái mới, tùy công cụ và chính sách version.

### 9.2. Protobuf/gRPC

Trong Protobuf, field có **số hiệu (field number)** và wire type. Những nguyên tắc cơ bản khi tiến hóa schema:

- Không đổi hoặc tái sử dụng field number của field đã được phát hành cho một ý nghĩa khác.
- Không tái sử dụng giá trị số của enum cũ với nghĩa mới.
- Khi xóa field, nên **reserve** number và tên để giảm nguy cơ tái sử dụng vô tình.
- Thêm field mới với number chưa dùng thường là hướng mở rộng, nhưng vẫn phải xét ngữ nghĩa và code generated client.
- Sự hiện diện field, default value, enum unknown và quy tắc optional có thể khác theo version/syntax/runtime Protobuf.
- Đổi type chỉ an toàn nếu quy tắc compatibility của Protobuf và mọi reader/writer liên quan cho phép; không suy từ tên type.

Ví dụ minh họa:

~~~proto
syntax = "proto3";

message OrderView {
  string id = 1;
  string status = 2;
  int64 total_amount_legacy = 3 [deprecated = true];
  string currency = 4;
  string amount_minor_units = 5;

  reserved 6, 7;
  reserved "removed_old_field";
}
~~~

Đây là ví dụ về nguyên tắc tổ chức field number, không phải một lời khuyên rằng mọi hệ thống phải dùng Protobuf. Nếu trạng thái status được biểu diễn bằng enum numeric, phải kiểm tra cụ thể khả năng consumer cũ bảo toàn unknown value và nhánh xử lý của code.

### 9.3. Không đánh đồng codegen compatibility với business compatibility

Một thay đổi compile được trên Java, TypeScript và Go chưa chắc đảm bảo:

- Không phát sinh charge trùng.
- Không thay đổi thời điểm đơn được giao.
- Không mất phí/chiết khấu trong tính tổng tiền.
- Không mở quyền truy cập.
- Không xóa dữ liệu khi gặp field null.
- Không sai trạng thái do message cũ đến muộn.

Schema checker là một lớp bảo vệ cần thiết, không phải kiểm chứng cuối của contract.

## 10. Lộ trình an toàn: expand → migrate → contract

Đây là mô hình thường dùng khi chuyển representation hoặc endpoint mà nhiều consumer đang sử dụng.

### 10.1. Expand: thêm khả năng mới nhưng giữ cách cũ

Giả sử muốn đổi tên totalAmount thành amountMinorUnits.

1. Provider thêm field mới vào response, giữ field cũ.
2. Hai field được tính từ **cùng một giá trị nguồn**.
3. API documentation nêu đơn vị, currency, rounding và quan hệ giữa chúng.
4. Contract tests xác nhận consumer cũ vẫn đọc được response.
5. Instrumentation ghi tỷ lệ consumer cũ và lỗi parsing (nếu có thể quan sát).

~~~json
{
  "id": "ord-1001",
  "totalAmount": 340000,
  "amountMinorUnits": "340000",
  "currency": "VND"
}
~~~

### 10.2. Migrate: cập nhật consumer theo từng đợt

1. Consumer mới bắt đầu đọc amountMinorUnits; vẫn có fallback có kiểm soát nếu provider cũ còn chạy.
2. Triển khai thử nghiệm với mixed versions.
3. Kiểm tra behavior về rounding, null, currency và số lớn.
4. Xác minh consumer bên ngoài, mobile và worker đọc backlog đã được xử lý.
5. Theo dõi contract usage, error rate, support cases và rollback.

Nếu một consumer chưa thể cập nhật, có thể duy trì **compatibility adapter** hoặc version endpoint trong khoảng thời gian cam kết.

### 10.3. Contract: loại bỏ hình thức cũ khi đủ bằng chứng

Chỉ loại bỏ field cũ khi:

- Đã công bố deprecation và thời hạn hỗ trợ.
- Đã có bằng chứng không còn consumer yêu cầu field đó, hoặc có một version cũ tiếp tục được hỗ trợ.
- Rollback của các bản phát hành liên quan vẫn có đường hợp lệ.
- Lịch sử event/snapshot cũ vẫn được consumer mới đọc/replay nếu cần.
- Các dashboard và test cảnh báo breaking change đã sẵn sàng.

**Không xóa field chỉ vì các codebase nội bộ hiện tại đã merge.** Client cài trên thiết bị hoặc tích hợp bên thứ ba có thể vẫn dùng contract cũ.

### 10.4. Timeline ví dụ

~~~text
T0  Provider v1: chỉ có totalAmount
T1  Provider v2: totalAmount + amountMinorUnits
T2  Client v2: ưu tiên amountMinorUnits, fallback có quy tắc
T3  Mobile/partners nâng cấp theo khả năng
T4  Giám sát usage và thông báo dừng hỗ trợ field cũ
T5  Provider v3 hoặc API version mới: bỏ totalAmount
~~~

Khoảng cách T1–T5 không có con số cố định; phụ thuộc chính sách tương thích, loại consumer và bằng chứng thực tế.

## 11. Khi nào cần một version API mới?

Không phải thay đổi nào cũng cần /v2, nhưng có những thay đổi không thể giữ contract cũ an toàn.

Có thể cần version mới khi:

- Đổi ý nghĩa trường cũ mà consumer cũ không thể suy ra.
- Thay invariant hoặc precondition ảnh hưởng quyết định nghiệp vụ.
- Đổi từ tạo tài nguyên đồng bộ sang quy trình bất đồng bộ mà consumer cũ không có khả năng theo dõi.
- Đổi model thanh toán, làm tròn, tính tiền hoặc điều kiện giao hàng.
- Bắt buộc yêu cầu thêm dữ liệu mà consumer cũ không thể cung cấp.
- Bỏ các endpoint/field đang được consumer cam kết hỗ trợ.
- Đổi phân quyền hoặc mô hình lỗi đến mức thay đổi workflow.

Các cách version có thể gồm:

| Cách | Ví dụ | Đánh đổi |
| --- | --- | --- |
| URI path | /v1/orders, /v2/orders | Dễ thấy và định tuyến; nhiều route tồn tại |
| Media type | Accept: application/vnd.example.order-v2+json | Version theo representation; cần hỗ trợ client/proxy/tool |
| Header riêng | API-Version: 2026-01 | Tách đường dẫn và version; cần chính sách rõ cho cache/log |
| Contract/event type mới | OrderPlacedV2 hoặc PaymentAuthorized | Dễ phân biệt sự kiện; tăng số topic/schema hoặc handler |
| Capability/feature negotiation | Client khai báo khả năng hỗ trợ | Linh hoạt nhưng phức tạp và cần kiểm tra thực |

Không có chuẩn chung bắt buộc mọi API phải version theo đường dẫn. Quan trọng là **vòng đời hỗ trợ, khả năng định tuyến, contract/documentation, kiểm thử và deprecation** được công bố và vận hành.

### 11.1. Version khác feature flag

Feature flag có thể giúp bật dần hành vi mới với một nhóm caller. Nhưng nếu flag làm thay đổi ý nghĩa cùng endpoint tùy ngẫu nhiên, consumer khó dự đoán. Flag nên đi với contract/capability rõ, phân nhóm có thể quan sát và rollback, không thay thế versioning khi semantics đã không tương thích.

## 12. Ví dụ Java/Spring Boot: đọc trường lạ và bảo toàn ngữ nghĩa

### 12.1. DTO với field bổ sung

Một DTO minh họa:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderView(
    String id,
    String status,
    Long totalAmount,
    String amountMinorUnits,
    String currency
) {}
~~~

Cấu hình bỏ qua trường lạ phù hợp khi **contract cho phép response được mở rộng**. DTO này không chứng minh business correctness; controller/service vẫn phải kiểm tra trường cần thiết và trạng thái thực sự hợp lệ trước khi thực hiện side effect.

Ví dụ nếu status là một String raw:

~~~java
public boolean canRequestFulfillment(OrderView order) {
    return "CONFIRMED".equals(order.status());
}
~~~

Điều kiện này chỉ an toàn nếu contract giữ nguyên ý nghĩa CONFIRMED và Order sở hữu quyết định confirmed. Nếu enum mới biểu thị một trạng thái tương đương hoặc đã thay đổi ngữ nghĩa, consumer phải được nâng cấp theo contract mới.

### 12.2. Giữ null khác missing trong PATCH

Với những API yêu cầu phân biệt hai trường hợp, record Java với String nullable đơn thuần có thể không đủ. Có thể xử lý JSON tree hoặc dùng kiểu dữ liệu biểu diễn sự hiện diện rõ:

~~~java
JsonNode root = objectMapper.readTree(body);

if (!root.has("displayName")) {
    // Theo contract: không cập nhật displayName.
} else if (root.get("displayName").isNull()) {
    // Theo contract: xóa displayName, nếu cho phép.
} else if (root.get("displayName").isTextual()) {
    // Theo contract: cập nhật displayName.
} else {
    // Trả validation error.
}
~~~

Đây là logic minh họa cho một **custom PATCH contract**, không áp đặt lên JSON Patch hoặc JSON Merge Patch. Phải ghi nhận format được API sử dụng.

### 12.3. Enum unknown và branch an toàn

~~~java
public enum ExternalPaymentStatus {
    PENDING,
    SUCCEEDED,
    FAILED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Nếu consumer dùng Jackson feature tương ứng, status mới được map sang UNKNOWN. Nhánh domain có thể:

~~~java
public PaymentDecision decide(ExternalPaymentStatus status) {
    return switch (status) {
        case SUCCEEDED -> PaymentDecision.CONTINUE;
        case FAILED -> PaymentDecision.STOP;
        case PENDING, UNKNOWN -> PaymentDecision.VERIFY;
    };
}
~~~

Không được coi UNKNOWN là đã thanh toán để tiếp tục giao hàng. Nếu VERIFICATION không khả thi, cần dừng an toàn và hiển thị lỗi tương thích, không tự đoán kết quả.

### 12.4. Lưu ý với SDK generated code

OpenAPI/Protobuf code generation có thể thay đổi kiểu, enum và serialization khác nhau theo version thư viện. Vì vậy:

- Dùng **contract test trên artifact SDK thực tế** mà client đang dùng.
- Thử dữ liệu có field lạ, field null, enum lạ và giá trị số biên.
- Không chỉ chạy unit test trên DTO server hiện tại.
- Giữ test mixed-version và test replay event cũ.

## 13. Kiểm thử contract: schema cần đi cùng hành vi

### 13.1. Các lớp kiểm thử

| Lớp | Kiểm chứng điều gì | Ví dụ |
| --- | --- | --- |
| Schema compatibility | Writer/reader chấp nhận fields và types theo rule | Thêm currency không phá JSON client cũ |
| Consumer contract | Provider giữ những trường/hành vi consumer sử dụng | Mobile v1 vẫn nhận totalAmount và status cũ |
| Provider behavior | Validation, precondition, side effects có giữ nghĩa | CancelOrder không hoàn tiền ngoài contract |
| Mixed-version integration | v1/v2 cùng chạy trong rollout | Order v2 phục vụ Fulfillment v1 |
| Negative tests | Request sai và enum lạ được xử lý an toàn | UNKNOWN payment không giao hàng |
| Idempotency/retry | Duplicate request không tạo side effect lặp | Retry POST /payments không double charge |
| Event replay | Consumer mới đọc được payload cũ | Replay OrderPlaced v1 sau khi v2 deploy |
| E2E business | Tính đúng nghiệp vụ qua nhiều service | Đơn chỉ CONFIRMED theo invariant được công bố |

Consumer-driven contract tests (CDC, ví dụ Pact) có thể giúp provider biết consumer nào dùng phần nào của API. Nhưng contract test phản ánh chỉ những kỳ vọng đã được khai báo/test; nó không thay thế việc quản lý consumer ngoài hệ thống hoặc kiểm thử bất biến nghiệp vụ.

### 13.2. Bộ dữ liệu thử cần có

Với một field mới:

- Request/response thiếu field.
- Có field = null.
- Có field với giá trị hợp lệ và biên.
- Có field lạ không được consumer biết.
- Field chứa chuỗi quá dài/số rất lớn.
- Field có sai kiểu hoặc format.
- Consumer cũ nhận payload mới.
- Consumer mới nhận payload cũ.

Với enum:

- Mọi giá trị đã công bố.
- Một giá trị chưa biết.
- Giá trị null hoặc thiếu field nếu contract cho phép.
- Giá trị tương tự nhưng khác chữ hoa/thường nếu API quy định case-sensitive.
- Giá trị đã deprecated nhưng còn trong dữ liệu lịch sử.

Với operation:

- Request hợp lệ và lỗi nghiệp vụ.
- Timeout sau khi provider đã commit.
- Retry cùng idempotency key.
- Hai request cùng key đến đồng thời.
- Event đến trùng hoặc đảo thứ tự.
- Provider và consumer có version lệch nhau.
- Một request có side effect quan trọng nhưng response trả mất.

### 13.3. Một kịch bản Given–When–Then

~~~text
Given:
  Mobile v1 chỉ biết status PENDING, SUCCEEDED, FAILED.
  Payment v2 có thể trả REQUIRES_ACTION.

When:
  Mobile v1 gọi GET /payments/pay-91.
  Provider trả status REQUIRES_ACTION.

Then:
  Mobile v1 không crash do deserialization nếu contract/SDK có hỗ trợ unknown.
  Mobile v1 không hiển thị SUCCEEDED hoặc FAILED sai.
  Mobile v1 cho người dùng trạng thái chưa hỗ trợ/đang xác minh theo policy.
  Có telemetry để biết user cần nâng cấp hoặc hỗ trợ.
~~~

Nếu mobile v1 không có khả năng xử lý unknown, phải coi REQUIRES_ACTION là breaking change đối với client đó và dùng version/adapter hoặc rollout có phân loại năng lực client.

## 14. Quy trình thay đổi contract trong một đội Microservices

### Bước 1 — Mô tả yêu cầu nghiệp vụ

Ví dụ cần thêm trạng thái REQUIRES_ACTION vì cổng thanh toán áp dụng một bước xác thực mới. Không bắt đầu bằng “sửa enum Java”.

### Bước 2 — Liệt kê consumer và phiên bản

Ghi web, mobile, partner, batch job, service, message consumer và dữ liệu tồn trong broker. Phân biệt bên đội kiểm soát rollout với bên ngoài không thể ép nâng cấp ngay.

### Bước 3 — Phân loại thay đổi

Đặt nhãn:

- additive schema change;
- breaking shape/type;
- validation change;
- enum extension;
- semantic operation change;
- authorization/security change;
- historical event compatibility.

Một thay đổi có thể nằm nhiều nhóm.

### Bước 4 — Chọn chiến lược

- Mở rộng field và duy trì field cũ?
- Thêm enum với fallback an toàn có thực sự khả thi?
- Cần version endpoint/event mới?
- Có cần compatibility adapter cho client cũ?
- Có cần dual-read/dual-write với một nguồn sự thật?
- Có cần trạng thái trung gian trong workflow và cơ chế đối soát?

### Bước 5 — Viết contract và bằng chứng

Cập nhật OpenAPI/AsyncAPI/Protobuf, mô tả ngữ nghĩa field, status/error, idempotency, example và migration plan. Ghi ADR nếu thay đổi quan trọng.

### Bước 6 — Kiểm thử trước khi deploy

Chạy schema checks, consumer contracts, business tests, replay và mixed-version tests. Có thể dùng golden payload từ dữ liệu hợp lệ từng version, đã xử lý bảo mật/ẩn danh.

### Bước 7 — Rollout theo thứ tự tương thích

Thường triển khai provider **hỗ trợ cả cũ và mới trước**, sau đó nâng consumer, nhưng không áp dụng máy móc cho mọi thay đổi: một số consumer cần nâng cấp để có hành vi an toàn trước khi producer bắt đầu phát giá trị enum mới.

### Bước 8 — Quan sát và xác nhận

Theo dõi lỗi parsing, enum unknown, tỷ lệ 4xx/5xx, consumer version, request format, deprecation usage, retry và side effect thực tế. Canary/feature flag cần có điều kiện dừng rõ.

### Bước 9 — Thu hẹp/loại bỏ

Chỉ gỡ hỗ trợ cũ sau khi hết thời gian cam kết và có bằng chứng phù hợp, kể cả backlog và bản ghi lịch sử. Công bố lịch dừng hỗ trợ và khả năng khôi phục.

## 15. Một bản kế hoạch migration minh họa

Bối cảnh: Order Service cần đổi totalAmount thành amountMinorUnits, bổ sung currency và trạng thái AWAITING_PAYMENT_REVIEW.

| Giai đoạn | Provider | Consumer | Rủi ro cần theo dõi |
| --- | --- | --- | --- |
| 0. Hiện trạng | Chỉ totalAmount; status=PENDING/CONFIRMED/CANCELLED | Web/mobile/fulfillment cũ | Tài liệu hóa ngữ nghĩa hiện tại |
| 1. Expand fields | Trả cả hai amount fields và currency | Cũ vẫn chạy; mới có fallback | Hai biểu diễn lệch nhau; missing/null |
| 2. Prepare enum | Có hỗ trợ schema/adapter cho status mới nhưng chưa phát cho consumer chưa tương thích | SDK mới hỗ trợ UNKNOWN/REVIEW | Client cũ crash hoặc hiểu nhầm |
| 3. Migrate clients | Giữ cách cũ và cách mới | Web/mobile/fulfillment chuyển dần | Phân quyền/UX và rounding |
| 4. Activate status | Phát trạng thái mới cho nhóm consumer có khả năng xử lý; hoặc API v2 | Consumer mới có branch chính xác | Giao hàng nhầm khi chưa thanh toán |
| 5. Deprecate | Gắn notice và metrics field cũ | Các client còn lại được hỗ trợ theo cam kết | Mobile/partner chậm nâng cấp |
| 6. Contract | Gỡ trường cũ ở version mới khi đủ điều kiện | Không còn consumer cũ trên contract mới | Replay/cached payload/rollback |

### 15.1. Câu hỏi không được bỏ qua

- Cần lưu bao lâu các event cũ để replay?
- Client mobile cũ nhất còn được hỗ trợ là version nào?
- Ai là source of truth cho amount và currency?
- Có sử dụng số nguyên nhỏ hơn 64-bit trong một ngôn ngữ nào không?
- Trạng thái mới có thể khiến consumer cũ thực hiện hành vi không an toàn không?
- Nếu rollback provider, consumer mới vẫn chạy được với response cũ không?
- Có quy trình xử lý đơn/transaction được tạo trong lúc hai version cùng tồn tại không?

## 16. Quan sát thay đổi bằng metrics và log

Không đủ để dashboard báo tỷ lệ request 200 cao. Một thay đổi contract có thể gây sai nghiệp vụ mà không tăng 5xx.

Các tín hiệu nên cân nhắc:

| Tín hiệu | Mục đích |
| --- | --- |
| Client/consumer version distribution | Biết còn consumer cũ nào |
| Deserialize/validation error | Phát hiện lỗi schema hoặc kiểu dữ liệu |
| Unknown enum encounters | Biết có giá trị mới vượt khả năng consumer |
| Deprecated field usage | Đo thời điểm có thể loại bỏ trường cũ |
| Unexpected 4xx/409/422 | Phát hiện validation/semantic change |
| Idempotency conflicts và duplicate attempts | Phát hiện thao tác bị retry không đúng |
| Event parse failure, DLQ và lag | Theo dõi consumer event cũ/mới |
| Business invariants | Phát hiện giao hàng sai, amount sai, charge trùng |
| Rollback/canary metrics | Chứng minh khả năng trở lại version trước |
| Support incidents theo contract version | Phát hiện lỗi không lộ ra qua HTTP metrics |

Không đưa paymentId/orderId của từng request làm label metrics cardinality vô hạn. Những định danh chi tiết phù hợp hơn trong trace/log với chính sách bảo mật thích hợp. Tránh ghi dữ liệu cá nhân hoặc raw token vào telemetry.

### 16.1. Đo usage không phải lúc nào cũng dễ

Server thường biết endpoint nào được gọi, nhưng không biết client dùng field response nào. Để gỡ một trường cũ, có thể cần client telemetry, contract registry, SDK release tracking, deprecation header hoặc xác nhận từ partner. Nếu không có bằng chứng, không tự kết luận field không còn được sử dụng chỉ vì server log không nhắc đến tên nó.

## 17. Những phản mẫu thường gặp

**“Thêm field luôn không breaking.”**  
Sai nếu consumer dùng parser strict, JSON canonicalization, DTO codegen hoặc field mới làm tăng dữ liệu/tác động bảo mật ngoài contract.

**“Field optional nghĩa là consumer có thể dùng tùy ý mà không cần xét null.”**  
Sai. Missing và null có thể khác ngữ nghĩa. Default chỉ an toàn khi đã được công bố và không thay đổi bất ngờ.

**“Đổi field cùng nghĩa chỉ là rename.”**  
Chưa chắc. Nếu đổi đơn vị, kiểu, rounding hoặc thời điểm tính giá, có thể là thay đổi nghiệp vụ quan trọng.

**“Thêm enum mới thì client cũ chỉ việc bỏ qua.”**  
Không luôn. Client có thể crash hoặc đưa ra quyết định sai; cần fallback an toàn hoặc version mới.

**“Đổi định nghĩa CONFIRMED không breaking vì schema không đổi.”**  
Sai. Thay đổi ngữ nghĩa có thể làm consumer thực hiện side effect sai.

**“Mọi POST đều có thể retry sau timeout.”**  
Không. Provider có thể đã commit. Chỉ retry theo idempotency/operation contract phù hợp.

**“Có /v2 là tự động tương thích.”**  
Sai. Version phải đi cùng routing, policy, tài liệu, thử nghiệm và vòng đời hỗ trợ. Nó cũng không tự khắc phục event replay hoặc nguồn dữ liệu chồng chéo.

**“OpenAPI schema check PASS là đủ.”**  
Không. Schema test không phát hiện nhiều lỗi về invariant, quyền, trạng thái cuối và hành vi thu tiền.

**“Xóa field sau khi frontend chính đã cập nhật.”**  
Rủi ro nếu mobile, partner, batch worker hoặc event lịch sử vẫn cần nó.

**“Unknown enum nên map thành một giá trị cũ.”**  
Có thể sai nghiêm trọng. Unknown cần được xử lý theo tính an toàn của nghiệp vụ, thường là chờ xác minh/từ chối hoặc version adaptation.

**“Đổi default không phá contract vì field không thay đổi.”**  
Sai. Client cũ bỏ qua field có thể nhận một kết quả mới mà không hề đổi payload.

## 18. Bài tập thực hành

### Bài 1 — Phân loại thay đổi

Một Product API đang trả price=120000, currency="VND", status="ACTIVE". Đội phát triển dự kiến:

1. Thêm field description.
2. Đổi price từ integer sang string.
3. Thêm status="PREORDER".
4. Đổi status ACTIVE từ “được phép bán” thành “đang hiển thị trên catalog”.
5. Biến currency từ tùy chọn thành bắt buộc.

**Yêu cầu:** xác định thay đổi nào có thể additive, thay đổi nào breaking và bằng chứng/consumer handling cần kiểm tra.

**Gợi ý:** (1) thường là additive nếu reader chịu field lạ; (2), (4), (5) có rủi ro rõ rệt; (3) phụ thuộc enum là open hay closed và PREORDER ảnh hưởng hành vi mua như thế nào.

### Bài 2 — Missing và null trong PATCH

API cho sửa profile. PATCH body là custom JSON, contract định nghĩa missing = không thay đổi, null = xóa, string = cập nhật.

**Yêu cầu:** viết ba testcase cho displayName; xác định cách Java đọc đủ sự khác biệt.

**Gợi ý:** dùng JsonNode.has() để biết field có tồn tại, kiểm null trước khi đọc string; không giải mã tất cả vào String nullable rồi coi missing và null giống nhau.

### Bài 3 — Payment enum mới

Payment API thêm REQUIRES_ACTION. Client cũ chỉ biết PENDING, SUCCEEDED, FAILED và đang map mọi enum không biết thành SUCCEEDED.

**Yêu cầu:** chỉ ra rủi ro và đề xuất migration.

**Gợi ý:** mapping đó có thể dẫn đến giao hàng/ghi nhận thanh toán sai. Đổi client sang handling unknown an toàn trước khi provider phát giá trị mới, hoặc dùng contract version/adapter riêng cho client chưa hỗ trợ.

### Bài 4 — Đổi ngữ nghĩa PUT

V1: PUT /cart/items/{sku} với quantity=2 nghĩa là đặt số lượng về 2. V2 dự định giữ route nhưng hiểu là tăng thêm 2.

**Yêu cầu:** vì sao đây là breaking change ngay cả khi JSON không đổi? Đề xuất hai cách triển khai mới an toàn.

**Gợi ý:** giữ PUT semantics cũ và thêm command POST /cart/items/{sku}/add với idempotency; hoặc version API riêng với contract rõ và kế hoạch chuyển consumer.

### Bài 5 — Protobuf field number

Một message đã phát hành có field number 5 cho customer_id. Đội muốn xóa customer_id và tái dùng number 5 cho coupon_code.

**Yêu cầu:** phân tích rủi ro khi đọc dữ liệu lịch sử và nêu cách sửa.

**Gợi ý:** không tái dùng field number cho nghĩa khác; reserve number và tên cũ nếu phù hợp, cấp number mới và lên kế hoạch migration.

### Bài 6 — Sửa hợp đồng đặt hàng đồng bộ

API cũ POST /orders trả 201 với status=CONFIRMED; đội muốn trả 202 cùng operationId vì cần thanh toán bất đồng bộ.

**Yêu cầu:** xây dựng plan cho web, mobile và partner cũ; nêu trường hợp nào phải version thay vì âm thầm đổi response.

**Gợi ý:** vì ngữ nghĩa hoàn tất thay đổi, cần endpoint/version mới hoặc lớp compatibility giữ kỳ vọng cũ, kèm khả năng tra operation, trạng thái cuối, idempotency và thông báo deprecation.

### Bài 7 — Bảng thử mixed-version

Provider Order v1/v2 và Consumer Fulfillment v1/v2 có thể cùng tồn tại.

**Yêu cầu:** lập ma trận bốn tổ hợp version; chọn ít nhất sáu payload/status để test, bao gồm field mới, enum lạ, timeout, event cũ và lỗi validation.

**Gợi ý:** không chỉ đo parse success; khẳng định Fulfillment chỉ giao hàng khi đủ điều kiện nghiệp vụ.

## 19. Mẫu đánh giá thay đổi contract (ADR nhẹ)

~~~markdown
# Contract Change Proposal

## Phạm vi
- Provider:
- Endpoint / event:
- Current contract version:
- Proposed contract version:

## Động cơ nghiệp vụ
- Vì sao phải thay đổi?
- Bất biến nghiệp vụ nào bị ảnh hưởng?

## Thay đổi dự kiến
- Field thêm / xóa / đổi tên / đổi kiểu:
- Enum thêm / đổi / deprecated:
- Operation semantics thay đổi:
- Error/authorization/timeout thay đổi:

## Consumer bị ảnh hưởng
- Web:
- Mobile:
- Service nội bộ:
- Partner:
- Batch/replay:

## Phân loại tương thích
- Provider mới với consumer cũ:
- Consumer mới với provider cũ:
- Event lịch sử với consumer mới:
- Schema compatibility:
- Semantic compatibility:

## Chiến lược migration
- Expand:
- Migrate:
- Contract/deprecation:
- Version/adapter nếu cần:
- Rollback:

## Kiểm thử và tín hiệu
- Schema/CDC:
- Mixed-version:
- Business invariants:
- Retry/idempotency:
- Metrics/unknown enum/errors:

## Quyết định
- Accepted / Rejected / Needs evidence:
- Lý do:
- Người sở hữu và thời điểm xem lại:
~~~

Mẫu giúp làm rõ **hợp đồng đang được consumer nào sử dụng** và **điều gì bị thay đổi về nghĩa**, thay vì chỉ chấp thuận pull request sửa JSON class.

## 20. Tổng kết

| Thành phần | Nguyên tắc trọng tâm |
| --- | --- |
| **Field** | Thêm trường có thể tương thích nếu consumer cho phép; đổi tên/kiểu/required/default cần kế hoạch migration. |
| **Null và missing** | Không đánh đồng; quyết định theo contract, đặc biệt với PATCH. |
| **Enum** | Giá trị mới có thể làm client cũ crash hoặc quyết định sai; xử lý unknown an toàn hoặc version riêng. |
| **Operation** | Ý nghĩa, side effects, preconditions, idempotency và tính cuối cùng là một phần contract. |
| **Errors** | HTTP status và business error code ảnh hưởng retry/UX; thay đổi cần công bố và test. |
| **Events** | Consumer có thể đọc backlog cũ; không đổi nghĩa sự kiện đã phát. |
| **Schema/codegen** | Là lớp kiểm tra định dạng, không thay thế kiểm thử đúng nghiệp vụ. |
| **Versioning** | Chọn cơ chế theo vòng đời consumer, không chỉ thêm số phiên bản vào URI. |
| **Migration** | Expand → migrate → contract, giữ owner rõ, quan sát adoption và có rollback. |

**Câu hỏi quan trọng nhất trước khi sửa contract:** “Một consumer chưa nâng cấp sẽ **hiểu** dữ liệu mới như thế nào và sẽ **làm gì** với nó?” Nếu đáp án là crash, mất dữ liệu, retry sai, lộ quyền hoặc thực hiện side effect nguy hiểm, thay đổi đó chưa thể coi là tương thích—ngay cả khi payload JSON vẫn hợp lệ.

Một hợp đồng tiến hóa tốt giúp các thành phần triển khai độc lập **mà không đổi ngầm ý nghĩa**. Trong Microservices, bảo toàn ngữ nghĩa và invariant qua nhiều phiên bản quan trọng hơn việc giữ nguyên hình dạng của schema.

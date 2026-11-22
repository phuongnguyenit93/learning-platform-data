# Kiểm tra ma trận tương thích giữa các phiên bản dịch vụ trong Microservices

Trong kiến trúc Microservices, mỗi dịch vụ có thể được triển khai độc lập. Ở một thời điểm, **Order Service** có thể đã chạy phiên bản mới trong khi **Payment Service**, **Inventory Service**, một consumer Kafka hoặc một ứng dụng di động vẫn chạy phiên bản cũ. Do vậy, “build thành công” hoặc “tất cả dịch vụ chạy ổn khi đều ở bản mới nhất” chưa đủ để khẳng định một bản phát hành an toàn.

**Ma trận tương thích phiên bản** (*version compatibility matrix*) là cách mô tả và kiểm chứng có hệ thống các tổ hợp phiên bản có thể giao tiếp đúng với nhau. Ma trận giúp nhóm trả lời: bản dịch vụ mới có còn làm việc với consumer đang hoạt động không, một service cũ có hiểu event từ service mới không, có được triển khai producer trước consumer không, và rollback có làm hỏng dữ liệu hoặc hợp đồng đã phát hành không?

Bài viết thuộc chủ đề **Tích hợp và phát hành** của kiến trúc hệ thống Microservices.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu vì sao triển khai độc lập dẫn tới tình trạng nhiều phiên bản cùng tồn tại.
- Xác định các hướng tương thích: backward, forward, full compatibility và trường hợp breaking change.
- Lập ma trận tổ hợp phiên bản cho HTTP/REST, gRPC, sự kiện bất đồng bộ, schema và cấu hình liên quan.
- Phân biệt **đã kiểm thử**, **được hỗ trợ**, **chưa kiểm thử** và **không tương thích**.
- Dùng contract test, integration test và end-to-end test phù hợp để kiểm chứng từng ô của ma trận.
- Chọn các tổ hợp kiểm thử có trọng tâm thay vì thử tích Descartes của mọi phiên bản trong hệ thống.
- Liên kết kết quả kiểm thử với quy tắc triển khai, canary, rollback và loại bỏ phiên bản cũ.
- Theo dõi phiên bản thật đang chạy để ma trận không bị lỗi thời.

## 2. Bài toán nhiều phiên bản cùng tồn tại

Giả sử hệ thống thương mại điện tử có bốn thành phần:

~~~text
Web / Mobile Client
        |
        v
   Order Service ------HTTP------> Payment Service
        |
        +-------------HTTP------> Inventory Service
        |
        +-------------EVENT-----> Notification Service
~~~

Nhóm Payment phát hành phiên bản 2.5, thêm trường phản hồi "fraudDecision", trong khi Order 2.3 vẫn chờ phản hồi từ Payment 2.4. Nhóm Order cùng lúc chuẩn bị phát hành 2.4 và đổi định dạng request. Kafka có event "OrderPlaced" được các consumer ở những nhịp phát hành khác nhau sử dụng.

Các tình huống thường gặp:

1. **Rolling deployment:** các pod v2.4 và v2.5 cùng nhận lưu lượng trong thời gian ngắn.
2. **Canary:** 5% lưu lượng đến v2.5, phần còn lại đến v2.4.
3. **Nhóm phát hành độc lập:** Order v2.3 tiếp tục dùng Payment v2.5 vì hai đội có lịch triển khai khác nhau.
4. **Consumer chậm cập nhật:** Notification v1.8 vẫn đọc event mới do Order v2.4 phát ra.
5. **Mobile/web client cũ:** ứng dụng trên thiết bị người dùng không thể được nâng cấp đồng loạt.
6. **Rollback:** một dịch vụ quay về binary cũ nhưng database hoặc event đã được cập nhật.

Mỗi tình huống đều có khả năng tạo tổ hợp phiên bản mới. Nếu chỉ kiểm thử bộ “tất cả bản mới nhất”, nhóm có thể bỏ lỡ lỗi tương thích xảy ra ngay trong quá trình triển khai.

## 3. “Tương thích” phải được định nghĩa theo hợp đồng và hành vi

Hai phiên bản tương thích khi những tương tác mà hệ thống **cam kết hỗ trợ** vẫn hoạt động đúng trong tổ hợp đó, kể cả cấu trúc dữ liệu, quy tắc nghiệp vụ và cách xử lý lỗi. Việc một request trả HTTP 200 chưa đủ để kết luận tương thích.

Một tổ hợp cần được xem xét theo các lớp:

| Lớp | Cần kiểm chứng | Ví dụ lỗi |
|---|---|---|
| Giao diện API | Method, path, query, header, status, request/response body | Đổi tên trường "amount" thành "totalAmount" |
| Hợp đồng dữ liệu | Required/optional, kiểu, enum, nullability, giới hạn và validation | Giá trị enum mới làm consumer cũ crash |
| Ngữ nghĩa | Ý nghĩa trường, đơn vị, quy tắc nghiệp vụ, idempotency | Trường "amount" đổi từ VND sang đơn vị nhỏ nhất |
| Giao thức | HTTP, gRPC, TLS, authentication, serialization | Service mới yêu cầu header cũ không gửi |
| Sự kiện | Topic, event name, schema, key, ordering, retention | Consumer cũ không giải mã payload mới |
| Persistence | Migration, thay đổi column, index, data shape | Binary cũ không đọc được row mới |
| Vận hành | Timeout, retry, rate limit, cấu hình và feature flags | Retry mới khiến side effect bị lặp |
| Triển khai | Rolling, canary, rollback, mixed versions | Hai pod khác version ghi dữ liệu không tương thích |

**Tương thích theo cú pháp** là parse được payload. **Tương thích theo ngữ nghĩa** là vẫn hiểu và xử lý đúng payload đó. Cần kiểm tra cả hai.

### 3.1. Ai là producer, ai là consumer?

Trong một API call, **provider** cung cấp endpoint và **consumer** gọi endpoint. Với event, **producer** xuất bản sự kiện và **consumer** nhận sự kiện. Một Microservice có thể đồng thời giữ cả hai vai trò trong các mối quan hệ khác nhau.

Ví dụ:

~~~text
Order Service (consumer HTTP) ---> Payment Service (provider HTTP)
Order Service (event producer) --> Kafka --> Notification Service (event consumer)
~~~

Ma trận phải ghi rõ chiều tương tác. Kết quả “Payment v2.5 tương thích Order v2.3” có nghĩa cụ thể là Order v2.3 gọi Payment v2.5 theo hợp đồng đang sử dụng được; nó **không mặc nhiên** chứng minh Payment v2.3 có thể gọi Order v2.5, hoặc hai dịch vụ tương thích theo mọi giao diện.

## 4. Backward, forward và full compatibility

Các thuật ngữ chỉ có ý nghĩa khi chỉ rõ dữ liệu của bên nào được đọc bởi bên nào:

- **Backward compatibility (đối với schema mới):** bộ đọc mới xử lý được dữ liệu do phiên bản cũ tạo ra.
- **Forward compatibility (đối với schema cũ):** bộ đọc cũ xử lý được dữ liệu do phiên bản mới tạo ra.
- **Full compatibility:** đáp ứng cả hai hướng theo quy ước và phạm vi schema đã công bố.
- **Breaking change:** làm mất một hành vi đã được consumer đang hỗ trợ phụ thuộc vào; có thể xảy ra ngay cả khi payload vẫn parse được.

Trong REST API, cách diễn đạt thực dụng là: **provider mới còn phục vụ consumer cũ không?** và **consumer mới có sử dụng provider cũ được không?** Hai câu hỏi khác nhau, cần hai hướng test khác nhau.

Ví dụ thêm trường tùy chọn:

~~~json
// Response cũ
{
  "paymentId": "p-100",
  "status": "PAID"
}
~~~

~~~json
// Response mới
{
  "paymentId": "p-100",
  "status": "PAID",
  "fraudDecision": "APPROVED"
}
~~~

Nếu Order v2.3 bỏ qua trường response mà nó không biết, Payment v2.5 có thể còn tương thích với Order v2.3. Nhưng nếu parser của Order từ chối mọi trường lạ, tổ hợp này có thể thất bại. **Không thể suy từ loại thay đổi mà bỏ qua hành vi parser, validation và contract thực tế.**

Ví dụ breaking change:

~~~json
// Consumer cũ chờ
{"amount": 150000, "currency": "VND"}
~~~

~~~json
// Producer mới chỉ trả
{"minorUnits": 150000, "currency": "VND"}
~~~

Nếu producer bỏ "amount" khi consumer cũ vẫn yêu cầu trường này, việc triển khai producer trước có thể phá vỡ dịch vụ. Thậm chí nếu giữ tên trường nhưng đổi ý nghĩa từ “đồng” thành “xu”, đó vẫn là breaking change về ngữ nghĩa.

### 4.1. Semantic Versioning là tín hiệu, không phải bằng chứng

Phiên bản dạng MAJOR.MINOR.PATCH hỗ trợ truyền đạt ý định thay đổi nhưng không tự chứng minh tương thích. Một bản minor có thể vô tình đổi schema; một bản major có thể vẫn phục vụ các consumer cũ qua endpoint versioned. Quyết định phát hành cần dựa trên hợp đồng, bằng chứng kiểm thử và chính sách hỗ trợ được công bố.

## 5. Định nghĩa phạm vi ma trận

Không nên bắt đầu bằng toàn bộ tổ hợp của mọi version trong hệ thống. Trước tiên, xác định:

1. **Đồ thị phụ thuộc:** service nào gọi service nào, dùng endpoint/event nào.
2. **Phiên bản đang chạy:** version/digest hiện tại trên production, staging, canary và nhóm khách hàng còn được hỗ trợ.
3. **Phiên bản ứng viên:** binary mới dự kiến phát hành, cùng các phiên bản có thể rollback.
4. **Chính sách hỗ trợ:** current, previous active, LTS hoặc phiên bản consumer cũ còn lưu hành.
5. **Kiểu thay đổi:** breaking/non-breaking dự kiến, schema migration, event mới, auth, config hay timeout.
6. **Mức bằng chứng:** contract test, integration test hoặc workflow E2E cần có cho từng ô.
7. **Thời hạn:** mốc ngừng hỗ trợ phiên bản cũ sau khi consumer thực tế đã được nâng cấp.

Một ma trận có thể gắn nhãn:

| Trạng thái | Ý nghĩa |
|---|---|
| **PASS** | Tổ hợp đã chạy bộ test được định nghĩa và đạt |
| **FAIL** | Tổ hợp đã kiểm thử và có lỗi cần phân tích |
| **NOT_TESTED** | Chưa có bằng chứng kiểm thử; không suy thành PASS |
| **UNSUPPORTED** | Nằm ngoài chính sách hỗ trợ đã công bố |
| **BLOCKED** | Không thể kiểm thử vì thiếu dependency, môi trường hoặc điều kiện cần |
| **DEPRECATED** | Vẫn có thể chạy nhưng sẽ bị ngừng hỗ trợ theo lịch |

Trạng thái kỹ thuật và trạng thái hỗ trợ nên là hai thuộc tính độc lập: một tổ hợp có thể PASS nhưng UNSUPPORTED vì đã ngoài thời hạn cam kết.

## 6. Ví dụ ma trận giữa Order và Payment

Giả sử hệ thống hiện có Order 2.3, Order 2.4 và Payment 2.4, Payment 2.5. Những giá trị dưới đây **chỉ là dữ liệu minh họa**, không phải kết quả từ một hệ thống thực.

<escape><table></escape>

| Order (consumer) \ Payment (provider) | Payment 2.4 | Payment 2.5 |
|---|---|---|
| Order 2.3 | PASS | PASS |
| Order 2.4 | FAIL | PASS |

Giải thích dựa trên giả định cụ thể:

- Order 2.3 dùng các trường cũ và Payment 2.5 vẫn giữ chúng, nên hai tổ hợp đều vượt qua test.
- Order 2.4 bắt buộc gửi/nhận một khả năng mới mà Payment 2.4 chưa hỗ trợ, nên tổ hợp Order 2.4 + Payment 2.4 thất bại.
- Order 2.4 + Payment 2.5 là trạng thái mục tiêu mới.

Từ ma trận này, nếu Order 2.4 sẽ được triển khai, **Payment 2.5 cần có mặt trước** hoặc Order 2.4 phải có cơ chế tương thích ngược với Payment 2.4. Trong rolling deployment, phải xét xem request có thể đến cả hai phiên bản Payment hay không.

Dạng record dễ lưu vào hệ thống CI hơn:

~~~yaml
compatibility:
  consumer:
    service: order-service
    version: "2.4"
  provider:
    service: payment-service
    version: "2.5"
  interface: "POST /payments"
  contract_revision: "payments-v3"
  test_suite: "payment-consumer-contract"
  support_policy: "active"
  result: "PASS"
  checked_commit: "example-commit-sha"
  checked_at: "example-timestamp"
~~~

Đây là cấu trúc minh họa cho catalog tương thích nội bộ. Các thuộc tính như "checked_commit" và "checked_at" cần được hệ thống CI điền từ lần chạy thật, không nhập giá trị giả vào báo cáo phát hành.

### 6.1. Khi nào bảng hai chiều chưa đủ?

Nếu hành vi còn phụ thuộc vào broker, database schema, feature flag hoặc version của một dịch vụ thứ ba, một ô “Order 2.4 × Payment 2.5” chưa mô tả hết điều kiện. Có thể coi ma trận hai chiều là **một lát cắt của không gian phiên bản**, đi kèm metadata:

~~~text
Order:       2.4
Payment:     2.5
Inventory:   1.9
DB schema:   31
Event schema: OrderPlaced v2
Flag:        new-payment-flow = OFF
Environment: staging
~~~

Không thêm vô hạn chiều vào bảng để rồi khó đọc. Thay vào đó, giữ các phép kiểm tra theo từng **dependency edge**, và bổ sung các kịch bản workflow cho một vài tổ hợp quan trọng nhiều service.

## 7. Hợp đồng REST/HTTP: kiểm tra đúng điều consumer dùng

Một contract test hiệu quả tập trung vào các tương tác consumer đang sử dụng, ví dụ:

~~~http
POST /payments HTTP/1.1
Content-Type: application/json
Idempotency-Key: order-100

{
  "orderId": "order-100",
  "amount": 150000,
  "currency": "VND"
}
~~~

Kỳ vọng:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "paymentId": "payment-100",
  "status": "PAID"
}
~~~

Các phép kiểm tra nên bao gồm:

- Request/response schema, required field, optional field và nullability.
- Field mà consumer thực sự dùng; trường mới producer thêm vào có bị từ chối không.
- HTTP status, lỗi validation, auth, rate limit và mã lỗi ứng dụng.
- Header cần thiết, version header, content type và idempotency key.
- Quy tắc về đơn vị tiền tệ, timestamp, enum và độ chính xác số.
- Timeout, retry, duplicate request và side effect lặp.
- Các phiên bản API đang được quảng bá hoặc cam kết hỗ trợ.

**Consumer-driven contract testing** (ví dụ với Pact) cho phép consumer công bố hợp đồng tương tác của mình và provider xác minh rằng phiên bản provider ứng viên đáp ứng được hợp đồng đó. Thử nghiệm này hữu ích khi producer và consumer phát hành độc lập.

Tuy nhiên, việc provider verifier báo PASS chỉ xác nhận các trường hợp đã khai báo trong contract; nó không chứng minh workflow nhiều service sẽ thành công, không thay thế bảo mật vận hành và không đảm bảo tương thích với các hành vi mà consumer chưa mô tả.

### 7.1. Consumer tolerance và giới hạn

Parser có thể cho phép trường response bổ sung mà nó không dùng. Ngược lại, việc silently bỏ qua tất cả trường request không biết đến có thể che lỗi đánh máy hoặc lỗi cấu hình. Chính sách nên rõ ràng theo hướng dữ liệu: mở rộng được ở response/event nơi phù hợp, nhưng validation của request vẫn phải bảo vệ quy tắc nghiệp vụ và kiểm soát dữ liệu đầu vào.

### 7.2. Không chỉ kiểm tra HTTP 2xx

Ví dụ Payment 2.5 thay đổi HTTP 409 thành HTTP 422 cho trường hợp trùng thanh toán. JSON vẫn giống nhau nhưng Order 2.3 có thể chỉ retry khi gặp 409. Như vậy behavior thay đổi làm sai luồng nghiệp vụ. Cần test cả nhánh thành công, lỗi, timeout, retry và mapping error code.

## 8. Hợp đồng gRPC và Protocol Buffers

Với gRPC, compatibility không chỉ là message còn parse được; cần xét service/method name, field number, type, oneof, enum, streaming semantics và error status.

Ví dụ protobuf:

~~~proto
syntax = "proto3";

message PaymentRequest {
  string order_id = 1;
  int64 amount_minor_units = 2;
  string currency = 3;
}
~~~

Khi thêm field:

~~~proto
message PaymentRequest {
  string order_id = 1;
  int64 amount_minor_units = 2;
  string currency = 3;
  string idempotency_key = 4;
}
~~~

Field mới cần được thiết kế sao cho consumer/provider cũ không bị buộc cung cấp giá trị mà trước đó chưa biết. Đặc biệt:

- Không tái sử dụng field number đã xóa; dùng "reserved" khi loại bỏ.
- Tránh đổi meaning hoặc wire type theo cách parser cũ hiểu sai.
- Kiểm tra default value của proto3: “không có giá trị” và “giá trị mặc định” có thể không được phân biệt nếu không thiết kế presence.
- Khi thêm enum value, client cũ cần xử lý giá trị không biết phù hợp.
- Nếu thay RPC method hoặc chuyển unary sang streaming, cần hợp đồng mới và kế hoạch chuyển tiếp.

Code generation chạy được là một kiểm tra cần thiết, nhưng service phải được gọi với đúng version để xác minh behavior thực tế.

## 9. Tương thích schema sự kiện bất đồng bộ

Khác với HTTP request/response, event đã phát hành có thể tiếp tục nằm trong topic, queue hoặc được replay sau khi producer đã nâng cấp. Một consumer mới có thể đọc event cũ; consumer cũ có thể nhận event mới trong rolling deployment.

Ví dụ event:

~~~json
{
  "eventId": "evt-100",
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "orderId": "order-100",
  "totalAmount": 150000
}
~~~

Producer muốn thêm "currency" và "discountAmount". Cần xác định rõ liệu consumer cũ có bỏ qua được field mới, consumer mới có xử lý event cũ thiếu field hay không, và hai bên diễn giải đơn vị tiền giống nhau hay không.

### 9.1. Những hướng kiểm thử quan trọng

| Cặp | Câu hỏi |
|---|---|
| Consumer cũ + Event mới | Consumer cũ có deserialize và xử lý được payload mới không? |
| Consumer mới + Event cũ | Khi replay, consumer mới có hiểu schema lịch sử không? |
| Producer mới + Schema Registry | Schema mới có vượt qua chế độ tương thích đã cấu hình không? |
| Producer cũ + Consumer mới | Consumer mới có còn chấp nhận event của producer chưa nâng cấp không? |
| Event trùng / lệch thứ tự | Business outcome có giữ tính idempotent và hợp lệ không? |

Các công nghệ Avro, JSON Schema hoặc Protobuf có quy tắc kiểm tra khả năng tương thích riêng. Schema Registry có thể giúp phát hiện thay đổi cấu trúc vi phạm chính sách; nhưng nó không tự kiểm tra tất cả thay đổi ngữ nghĩa như đổi đơn vị tiền hoặc đổi ý nghĩa enum.

### 9.2. Schema evolution và event version

Đối với event được nhiều bên sử dụng:

1. Định nghĩa schema rõ ràng, có version/revision và ownership.
2. Bổ sung field có default hoặc quy tắc xử lý thiếu field khi cần.
3. Duy trì reader support cho các event lịch sử còn được replay.
4. Nếu thay đổi ngữ nghĩa đáng kể, cân nhắc một event type/version mới hoặc cơ chế dual publish có thời hạn.
5. Tránh rename trực tiếp field được consumer cũ dùng.
6. Theo dõi consumer nào còn đọc format cũ trước khi gỡ bỏ đường tương thích.

Một topic mới không tự bảo đảm compatibility; cần kiểm tra routing, quyền, offset, retention, replay và business semantics. Bổ sung event version cũng không giải quyết vấn đề nếu consumer không có logic đọc các version liên quan.

## 10. Cơ sở dữ liệu và chiến lược Expand–Migrate–Contract

Mỗi dịch vụ thường sở hữu dữ liệu riêng, nhưng khi rolling deployment, **hai phiên bản của cùng dịch vụ** có thể tạm thời truy cập chung một database schema. Vì vậy, migration database là một chiều của ma trận tương thích.

Ví dụ muốn đổi trường "customer_name" thành "display_name":

**Giai đoạn 1 — Expand:** thêm cột "display_name" trong khi vẫn giữ "customer_name", triển khai code có thể đọc dữ liệu hiện tại. Không xóa cột cũ.

~~~sql
ALTER TABLE customers
ADD COLUMN display_name text;
~~~

**Giai đoạn 2 — Migrate:** backfill dữ liệu cũ; phiên bản ứng dụng chuyển dần sang đọc trường mới, có logic fallback khi dữ liệu chưa được chuyển hết. Trong giai đoạn song song, có chiến lược đồng bộ ghi được kiểm soát và test cho cả hai binary nếu cần.

~~~sql
UPDATE customers
SET display_name = customer_name
WHERE display_name IS NULL;
~~~

**Giai đoạn 3 — Contract:** sau khi chắc chắn không còn instance, job, report hoặc consumer được hỗ trợ nào phụ thuộc cột cũ, mới xóa "customer_name" trong một đợt phát hành sau.

~~~sql
ALTER TABLE customers
DROP COLUMN customer_name;
~~~

Những lệnh SQL trên minh họa tiến trình; thao tác thực tế cần có migration được version hóa, chiến lược backfill có thể chạy lại và giới hạn khóa/hiệu năng theo quy mô dữ liệu.

Ma trận ví dụ:

| Application version | Schema 30 | Schema 31 (cũ + mới) | Schema 32 (đã xóa cũ) |
|---|---|---|---|
| App 2.3 đọc "customer_name" | PASS | PASS | FAIL |
| App 2.4 đọc "display_name", có fallback | Phụ thuộc code/migration | PASS | PASS |
| App 2.5 chỉ đọc "display_name" | FAIL | PASS | PASS |

Đây cũng chỉ là kết quả giả định dùng để giải thích. **Rollback binary** phải được đối chiếu với trạng thái schema: rollback về App 2.3 sau khi xóa cột cũ có thể thất bại dù image cũ từng chạy tốt.

## 11. Lập ma trận bằng đồ thị phụ thuộc

Một hệ thống 20 dịch vụ, mỗi dịch vụ có ba version, sẽ có số tổ hợp toàn hệ thống là 3 mũ 20 nếu thử tất cả. Cách đó không thực tế và thường không cần thiết.

Thay vì thế:

1. Biểu diễn mỗi service là một đỉnh, mỗi API/event dependency là một cạnh có hướng.
2. Với mỗi cạnh, liệt kê **provider/producer candidate versions** và **consumer versions thực sự còn cần hỗ trợ**.
3. Chạy contract test cho các cặp có ý nghĩa trên mỗi cạnh.
4. Chỉ dựng các kịch bản xuyên nhiều cạnh cho luồng nghiệp vụ quan trọng hoặc thay đổi rủi ro cao.
5. Bổ sung tổ hợp biên: version cũ nhất còn hỗ trợ, version mới nhất, canary và trường hợp rollback.
6. Lưu cả điều kiện môi trường (feature flag, schema, broker configuration) khi chúng thay đổi kết quả.

~~~text
           +--------------------+
           | Order v2.3 / v2.4  |
           +----------+---------+
                      |
        +-------------+-------------+
        |                           |
        v                           v
 Payment v2.4 / v2.5      Inventory v1.8 / v1.9
        |
        v
 Event consumers v1.7 / v1.8
~~~

Thử hai cặp trực tiếp của từng dependency cho biết phần lớn hợp đồng đã định nghĩa được giữ vững. Sau đó, chọn một tập E2E nhỏ theo workflow (đặt hàng, hủy đơn, hoàn tiền) để phát hiện lỗi phối hợp giữa các cạnh.

### 11.1. Rủi ro để ưu tiên tổ hợp

Ưu tiên cao hơn nếu tổ hợp có một hoặc nhiều yếu tố sau:

- Liên quan thanh toán, số dư, dữ liệu người dùng hoặc hành động khó đảo ngược.
- Thay đổi required field, enum, auth, idempotency, retry hoặc semantics.
- Thay đổi event schema có nhiều consumer; consumer di động không thể nâng cấp đồng thời.
- Có migration database, backfill hoặc rollback rủi ro.
- Có phiên bản production vẫn hoạt động với lưu lượng đáng kể.
- Có rollout canary hoặc mixed-version deployment trong thời gian dài.

Nếu phạm vi còn lớn, áp dụng **pairwise/combinatorial testing** có trọng số, nhưng vẫn giữ kiểm thử bắt buộc cho các đường phụ thuộc và workflow trọng yếu. Pairwise không bảo đảm phát hiện lỗi chỉ xuất hiện khi ba hoặc nhiều phiên bản tương tác đồng thời.

## 12. Thiết kế bộ test cho một ô ma trận

Giả sử cần kiểm chứng “Order 2.3 là consumer của Payment 2.5”:

**Đầu vào kiểm thử:**
- Artifact của Order đúng version 2.3; artifact Payment đúng version 2.5.
- Hợp đồng API/event tương ứng và bộ fixture có version.
- Database schema, feature flags, auth và dependency cần thiết được ghi lại.
- Môi trường riêng hoặc dữ liệu được cô lập để không bị test khác ảnh hưởng.

**Thực hiện:**
1. Triển khai các image theo version/digest được chọn.
2. Chờ readiness, chạy migration được cho phép rồi seed dữ liệu.
3. Gọi các tương tác Order 2.3 thực sự sử dụng qua Payment 2.5.
4. Chạy nhánh thành công, validation lỗi, timeout/retry và duplicate request nếu nằm trong hợp đồng.
5. Xác minh outcome nghiệp vụ và side effects, không chỉ response structure.
6. Thu log/trace, kết quả verifier và metadata của artifact.
7. Dọn dữ liệu/môi trường và xuất kết quả dưới trạng thái PASS, FAIL hoặc BLOCKED.

**Điều kiện PASS:** mọi assertion bắt buộc của suite đã được chạy và đạt trong đúng tổ hợp khai báo. Nếu không dựng được environment hoặc không chạy đủ suite, kết quả là BLOCKED/NOT_TESTED, không tự tính PASS.

### 12.1. Ví dụ khai báo test case

~~~yaml
case_id: order-2_3__payment-2_5
edge: "order-service -> payment-service"
consumer:
  service: order-service
  version: "2.3"
provider:
  service: payment-service
  version: "2.5"
interfaces:
  - "POST /payments"
  - "GET /payments/{paymentId}"
checks:
  - consumer-contract
  - http-negative-cases
  - payment-idempotency
environment:
  database_schema: "payment-31"
  new_payment_flag: false
required_for_release: true
~~~

Đây là manifest minh họa. Pipeline thực tế phải ánh xạ trường "checks" sang các suite test có thật và lưu image digest/commit đã triển khai.

## 13. Tự động hóa kiểm tra trong CI/CD

Ma trận tương thích hữu ích nhất khi được sinh ra và kiểm tra thường xuyên từ version đang chạy và thay đổi trong Pull Request.

Một pipeline có thể hoạt động theo trình tự:

~~~text
Pull Request của một service
        |
        v
Phân tích endpoint/event/schema bị ảnh hưởng
        |
        v
Tra danh sách consumer/provider version đang được hỗ trợ
        |
        v
Sinh các ô cần kiểm tra cho các dependency liên quan
        |
        +--> Static/OpenAPI/Protobuf/Schema diff
        |
        +--> Consumer-driven contract verification
        |
        +--> Integration test với artifact/version thật
        |
        +--> E2E workflow trọng yếu khi cần
        |
        v
Ghi ma trận PASS / FAIL / NOT_TESTED / BLOCKED
        |
        v
Kiểm tra release policy và duyệt phát hành
        |
        v
Canary / rolling deploy + telemetry + rollback guard
~~~

### 13.1. PR gate

Khi một service thay đổi contract, CI nên:

1. Kiểm tra breaking change ở OpenAPI/Protobuf/schema theo quy tắc phù hợp.
2. Lấy danh sách contract của consumer còn được hỗ trợ.
3. Chạy provider verification trên artifact ứng viên.
4. Test các tổ hợp có rủi ro cao với version thực tế và dữ liệu riêng.
5. Chặn merge/phát hành nếu một ô **bắt buộc** chuyển FAIL hoặc BLOCKED theo chính sách.

Không nên coi mọi NOT_TESTED là PASS, và cũng không nhất thiết chặn mọi thay đổi vì một tổ hợp UNSUPPORTED. Chính sách release phải ghi rõ ranh giới hỗ trợ và tiêu chí chặn.

### 13.2. Pre-production gate

Trong staging hoặc môi trường tạm thời của PR, dựng các mixed-version combinations gần thực tế:

- Producer mới + consumer cũ đang production.
- Producer cũ + consumer mới nếu dự kiến triển khai consumer trước.
- Hai bản ứng dụng cũ/mới cùng dùng database đã expand.
- Feature flag ON/OFF nếu ảnh hưởng đến hợp đồng giao tiếp.
- Trường hợp rollback khi schema hoặc event đã được ghi ở phiên bản mới.

Dùng image digest thay vì chỉ dựa vào mutable tag để tái hiện chính xác artifact từng được kiểm thử.

### 13.3. Release gate và runtime

Trước production rollout, xác nhận service cần triển khai có compatible path với các version còn hoạt động. Khi canary, theo dõi các chỉ số của **tương tác thực tế**: lỗi 4xx/5xx theo endpoint, gRPC status, deserialize failure, consumer lag, business rejection, retry volume, event dead-letter và latency. Số lần gọi thành công không đủ nếu có side effect nghiệp vụ bị sai.

Canary có thể đi qua nhiều provider version; nếu traffic routing không bảo đảm chỉ đến phiên bản cụ thể, test và rollout phải xem xét toàn bộ tập provider có thể nhận request.

## 14. Ví dụ chiến lược triển khai theo ma trận

Trở lại ma trận minh họa:

| | Payment 2.4 | Payment 2.5 |
|---|---|---|
| Order 2.3 | PASS | PASS |
| Order 2.4 | FAIL | PASS |

**Trình tự được phép theo giả định:**

1. Payment 2.4 + Order 2.3 đang chạy.
2. Triển khai Payment 2.5 canary, Order 2.3 tương thích cả hai bản Payment.
3. Hoàn tất rollout Payment 2.5, xác nhận không còn Payment 2.4 nhận lưu lượng.
4. Triển khai Order 2.4 canary rồi rollout.
5. Duy trì quyền rollback Order 2.4 → 2.3 vì Order 2.3 tương thích Payment 2.5.

**Trình tự có nguy cơ:** triển khai Order 2.4 trong khi Payment 2.4 vẫn nhận request, vì có ô FAIL. Nếu buộc triển khai Order trước, phải sửa Order 2.4 để có fallback và kiểm thử lại tổ hợp.

### 14.1. Rollback là một hàng trong ma trận

Rollback không chỉ là chạy image cũ. Cần hỏi:

- Binary cũ có đọc được schema đã migration không?
- Binary cũ có hiểu event payload do bản mới phát ra không?
- Feature flag đã bật có làm dữ liệu được ghi theo định dạng mới không?
- Hợp đồng giữa service rollback và các service khác còn PASS không?
- Có side effect nào không thể đảo ngược (thanh toán, email, lệnh kho) không?

Khi migration đã làm mất dữ liệu hoặc loại bỏ schema cũ, rollback binary có thể không khả thi. Khi đó cần chiến lược roll forward hoặc một quy trình khôi phục dữ liệu đã được kiểm chứng.

## 15. Quản lý thay đổi breaking bằng phiên bản chuyển tiếp

Nếu API cần đổi "amount" thành "minorUnits", có thể dùng chiến lược chuyển tiếp:

**Giai đoạn A — Expand contract:** provider nhận và/hoặc xuất cả định dạng cũ lẫn mới theo quy tắc chuyển đổi rõ ràng. Consumer mới có thể đọc hai dạng khi cần. Không nên tự động chọn một trong hai trường nếu chúng mâu thuẫn; phải có precedence/validation được đặc tả.

**Giai đoạn B — Migrate consumers:** từng consumer chuyển sang hợp đồng mới, các ô ma trận được kiểm chứng sau mỗi thay đổi. Đo việc sử dụng contract cũ bằng telemetry.

**Giai đoạn C — Contract old path:** chỉ ngừng field/endpoint cũ khi danh sách consumer hỗ trợ không còn phụ thuộc, lịch deprecation đã đến và bài test xác nhận đường mới hoạt động.

Ví dụ sự thay đổi liên quan nhiều team:

~~~text
Provider v2.5: accept old + new formats
       |
       +--> Consumer A v1.8: dùng old, PASS
       +--> Consumer B v2.0: dùng new, PASS
       +--> Consumer C v1.2: còn old, cần migrate
       |
Provider v3.0: remove old only after policy allows
~~~

Giai đoạn này thường kéo dài qua nhiều lần phát hành. Vì vậy, việc chọn thời điểm xóa compatibility code dựa trên số liệu consumer thực tế và cam kết hỗ trợ, không chỉ dựa trên việc “đã có bản mới”.

## 16. Cách lưu kết quả và bằng chứng

Một ma trận chỉ đáng tin cậy khi mỗi ô có nguồn gốc:

| Trường | Ý nghĩa |
|---|---|
| Consumer / provider ID | Tên service, interface và chiều gọi |
| Consumer version/digest | Artifact đã kiểm thử |
| Provider version/digest | Artifact đã kiểm thử |
| Contract/schema revision | Revision của OpenAPI, event schema hoặc proto |
| Test suite và revision | Bộ test đã chạy, commit của tests |
| Environment fingerprint | DB schema, flags và dependency version liên quan |
| Result | PASS / FAIL / BLOCKED / NOT_TESTED |
| Support status | SUPPORTED / DEPRECATED / UNSUPPORTED |
| Evidence | Link CI run, log, trace, contract verification |
| Checked at | Thời điểm chạy; xác định mức độ còn mới |
| Owner | Đội sở hữu hợp đồng và xử lý lỗi |

Lưu thêm thông tin runtime đang triển khai (deployment manifest, image digest, service discovery version) để so sánh **phiên bản đang chạy** với **phiên bản đã test**. Kết quả PASS của image khác digest không tự động áp dụng cho image mới dù tag giống nhau.

Ma trận có thể được lưu trong kho hợp đồng, báo cáo CI hoặc một registry nội bộ. Để tránh xung đột, cần có một nguồn sự thật cho version đang hoạt động và quy tắc ai được thay đổi support status.

## 17. Đánh giá độ bao phủ của ma trận

Thay vì chỉ đếm số ô PASS, đo đúng phần hệ thống cần đảm bảo:

- **Coverage trên active edges:** bao nhiêu dependency giữa phiên bản active/candidate đã được kiểm chứng.
- **Coverage trên required combinations:** bao nhiêu tổ hợp bắt buộc theo release policy đã PASS.
- **Contract coverage:** endpoint, message type và error path nào có consumer test.
- **Rollout coverage:** các giai đoạn rolling, canary, mixed version và rollback nào có bằng chứng.
- **Schema transition coverage:** các tổ hợp app/schema nào còn cần hỗ trợ.
- **Độ mới bằng chứng:** test chạy trên artifact/contract gần nhất hay đã lỗi thời.
- **Lỗi tương thích production:** sự cố thực tế để bổ sung case cho pipeline.

Ví dụ nếu có 8 tổ hợp bắt buộc và 7 PASS, 1 NOT_TESTED, có thể báo 7/8 required combinations verified; không được gọi đó là “100% compatible” chỉ vì tất cả test đã chạy đều PASS.

## 18. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Điều chỉnh |
|---|---|---|
| Chỉ test latest + latest | Bỏ lỡ consumer cũ, rolling và rollback | Test active version + candidate |
| Chỉ dựa SemVer | Nhãn phiên bản không kiểm chứng behavior | Dùng contract và test có bằng chứng |
| Coi schema diff PASS là đủ | Không kiểm tra semantics, retry và side effects | Thêm integration test cho behavior |
| Coi NOT_TESTED là PASS | Quyết định release thiếu dữ liệu | Trạng thái riêng và policy rõ |
| Kiểm thử mọi tổ hợp toàn hệ thống | CI quá chậm, nhiều tổ hợp không tồn tại thực tế | Dependency graph + risk-based selection |
| Chỉ kiểm thử response thành công | Lỗi mapping status, auth, idempotency vẫn lọt | Kiểm tra error/timeout/duplicate |
| Gỡ field cũ ngay khi phát hành mới | Consumer chưa nâng cấp có thể hỏng | Expand–Migrate–Contract |
| Không gắn image digest | Không tái hiện chính xác artifact | Lưu version/digest, schema và test revision |
| Bỏ qua event cũ trong broker | Consumer mới không replay được | Test new reader + historical events |
| Quên phiên bản database | Rollback binary không khôi phục hợp đồng lưu trữ | Ma trận app × schema |
| Không cập nhật inventory | Matrix không phản ánh production | Đồng bộ từ deployment telemetry |
| Dùng chung dữ liệu E2E không cô lập | Kết quả flaky và khó quy lỗi | RUN_ID, fixture riêng, cleanup |

## 19. Bài thực hành: lập ma trận cho thay đổi API

**Bối cảnh giả định:** Shipping Service v1.4 trả về:

~~~json
{
  "shipmentId": "s-100",
  "status": "DELIVERED"
}
~~~

Nhóm chuẩn bị Shipping v1.5 có thêm enum status "RETURNED" và trường optional "deliveredAt". Có ba consumer: Order v2.1, Order v2.2 và Customer Portal v1.0.

Thực hiện:

1. Liệt kê consumer nào đọc "status" và consumer nào parse enum chặt.
2. Ghi các version thực tế đang được hỗ trợ; xác định hợp đồng từng consumer.
3. Lập ma trận consumer version × Shipping v1.4/v1.5.
4. Tạo payload test cho trạng thái cũ, trạng thái RETURNED và response thiếu deliveredAt.
5. Chạy consumer contract verification trên Shipping v1.5.
6. Nếu consumer cũ không hiểu RETURNED, xác định chiến lược rollout: nâng cấp consumer, mapping tương thích có chủ đích hoặc versioned API.
7. Chạy mixed-version test cho thời gian rolling/canary và đánh giá rollback.
8. Ghi PASS/FAIL/NOT_TESTED kèm commit, digest, schema revision và link evidence.

**Câu hỏi suy luận:** Việc thêm một enum value là “additive” về mặt schema, nhưng vì sao vẫn có thể breaking đối với consumer? Vì code consumer có thể switch exhaustive hoặc parser không chấp nhận giá trị enum mới; dù JSON parse được, hành vi nghiệp vụ vẫn có thể sai.

## 20. Checklist trước khi phát hành thay đổi liên dịch vụ

- [ ] Có danh sách dependency edge và chiều giao tiếp liên quan.
- [ ] Có inventory các version production/canary/rollback còn trong chính sách hỗ trợ.
- [ ] Có contract/schema revision, chủ sở hữu và mô tả thay đổi.
- [ ] Đã phân loại field, enum, route, status code, semantics, auth, timeout và retry bị tác động.
- [ ] Đã chạy provider verification với hợp đồng consumer đang hỗ trợ.
- [ ] Đã kiểm tra event mới với consumer cũ và event lịch sử với consumer mới nếu có messaging.
- [ ] Đã kiểm tra app cũ/mới với schema database trong mọi giai đoạn rollout liên quan.
- [ ] Đã kiểm chứng các ô required; không có FAIL/BLOCKED bị bỏ qua tùy tiện.
- [ ] Đã chọn thứ tự triển khai dựa trên kết quả ma trận.
- [ ] Đã xác nhận khả năng rollback và kế hoạch xử lý khi rollback không thể thực hiện.
- [ ] Đã lưu artifact digest, test evidence, thời điểm và điều kiện môi trường.
- [ ] Đã cấu hình theo dõi lỗi trong canary và ngưỡng dừng/khôi phục phù hợp.
- [ ] Đã thống nhất ngày loại bỏ hỗ trợ cũ dựa trên deprecation policy và tình trạng consumer thực tế.

## 21. Kết luận

Trong Microservices, tương thích phiên bản là tính chất của **một tương tác cụ thể giữa các artifact và điều kiện vận hành cụ thể**, không phải đặc tính tuyệt đối của một dịch vụ. Ma trận tương thích đưa các giả định phát hành thành những tổ hợp có thể kiểm thử: consumer nào, provider nào, contract nào, database/event schema nào, và bằng chứng PASS ở đâu.

Thực hành bền vững là kiểm tra theo đồ thị phụ thuộc, giữ các contract test nhanh cho từng cạnh, bổ sung integration/E2E cho các workflow quan trọng, liên kết ma trận với chiến lược Expand–Migrate–Contract và thứ tự rollout, rồi cập nhật kết quả theo version thực tế đang chạy. Khi đó, nhóm có cơ sở kỹ thuật để phát hành độc lập mà vẫn kiểm soát rủi ro của giai đoạn nhiều phiên bản cùng tồn tại.
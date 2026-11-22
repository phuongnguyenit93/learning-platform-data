# Poison message, retry storm và dead-letter queue

Trong chương **Async và message API** của module `SECURITY_API_SECURITY`, message broker giúp API xử lý công việc bất đồng bộ và tách producer khỏi consumer. Tuy nhiên, message lỗi có thể được giao đi giao lại, một dependency chậm có thể làm hàng loạt consumer retry đồng thời, và một message độc hại có thể giữ tài nguyên hoặc làm kẹt cả luồng xử lý. Nếu không có giới hạn retry và cơ chế cách ly, một lỗi đơn lẻ có thể lan thành sự cố toàn hệ thống.

Ba khái niệm cần được thiết kế cùng nhau:

- **Poison message** là message liên tục thất bại do nội dung, schema, trạng thái hoặc logic xử lý; retry thông thường không làm nó tự hết lỗi.
- **Retry storm** là hiện tượng nhiều request/message được thử lại quá nhanh hoặc đồng thời, làm tăng tải lên broker, consumer và dependency đang gặp sự cố.
- **Dead-letter queue (DLQ)** là nơi cách ly message không thể xử lý sau chính sách retry hoặc bị xác định là không hợp lệ, để điều tra và xử lý có kiểm soát.

DLQ không tự sửa message và retry không tự bảo đảm xử lý thành công. Một thiết kế an toàn cần phân loại lỗi, giới hạn số lần thử và thời gian, dùng backoff có jitter, bảo đảm idempotency, chỉ acknowledge sau khi kết quả được lưu bền vững, bảo vệ dữ liệu trong DLQ và kiểm soát chặt việc redrive.

## 1. Vì sao lỗi message có thể trở thành sự cố bảo mật?

Một consumer thường xử lý message bằng cách parse payload, xác minh nguồn, kiểm tra quyền, truy vấn dữ liệu và gọi service khác. Nếu một bước thất bại, broker có thể giao lại message. Điều này là bình thường trong hệ thống at-least-once, nhưng trở thành rủi ro khi ứng dụng không kiểm soát được số lần giao, chi phí xử lý hoặc side effect.

Ví dụ một message yêu cầu gửi SMS:

```json
{
  "messageId": "msg-8f2a",
  "tenantId": "tenant-a",
  "type": "SendOtp",
  "phoneNumber": "+84901234567",
  "challengeId": "challenge-91"
}
```

Nếu provider SMS timeout sau khi đã nhận request, consumer có thể không biết tin nhắn đã được gửi hay chưa. Retry không có idempotency có thể gửi SMS lần nữa và tính phí trùng. Nếu provider đang lỗi trên diện rộng, hàng nghìn message cùng retry ngay lập tức có thể làm tình hình nặng hơn.

Một message khác có thể chứa JSON sai schema hoặc tham chiếu tới resource đã bị xóa. Nếu consumer liên tục requeue message ngay lập tức, nó có thể chiếm slot xử lý và khiến các message hợp lệ bị trì hoãn.

### 1.1. Các tác động cần tính đến

| Rủi ro | Ví dụ | Tác động |
|---|---|---|
| Poison message | Payload sai schema, enum không hỗ trợ, dữ liệu không thể deserialize | Lặp lỗi, kẹt partition/queue, tốn CPU |
| Retry storm | Provider trả `503`, consumer retry đồng loạt | Tăng tải, timeout dây chuyền, cạn connection/thread |
| Duplicate delivery | Consumer xử lý xong nhưng ack thất bại | Gửi email/SMS hoặc trừ tiền hai lần |
| Message tampering | Producer không được phép gửi command quản trị | Gọi hành động trái quyền |
| Tenant confusion | Tin `tenantId` trong payload | Đọc/ghi dữ liệu tenant khác |
| DLQ data exposure | DLQ lưu payload chứa PII hoặc token | Rò dữ liệu qua công cụ vận hành |
| Unsafe redrive | Replay message cũ sau khi quyền hoặc trạng thái đã đổi | Side effect sai thời điểm hoặc lặp lại |
| Queue exhaustion | Message lớn hoặc xử lý cực chậm | Cạn storage, worker và ngân sách |

### 1.2. DLQ là vùng dữ liệu nhạy cảm

DLQ thường chứa những message đã đi qua luồng nghiệp vụ nhưng thất bại. Payload có thể có email, số điện thoại, địa chỉ, dữ liệu thanh toán, nội dung tài liệu, tenant ID hoặc thông tin debug. Vì vậy DLQ cần authentication, authorization, mã hóa, retention và audit giống một kho dữ liệu production.

Không cho mọi developer hoặc operator quyền đọc toàn bộ DLQ chỉ để tiện debug. Cần giới hạn quyền theo queue, tenant, loại dữ liệu và thao tác; ưu tiên hiển thị metadata đã mask trước khi mở payload đầy đủ.

## 2. Phân biệt poison message, lỗi tạm thời và lỗi không chắc kết quả

Không phải mọi exception đều nên retry. Phân loại lỗi là bước quyết định để tránh retry vô hạn và tránh bỏ qua lỗi có thể khắc phục.

### 2.1. Lỗi vĩnh viễn (permanent failure)

Lỗi vĩnh viễn không thể được khắc phục bằng cách gửi lại cùng message trong cùng điều kiện. Ví dụ:

- Payload không phải JSON hợp lệ hoặc không đúng schema.
- Message type không được hỗ trợ và không có handler tương thích.
- Field bắt buộc thiếu, sai kiểu hoặc vượt giới hạn bảo mật.
- Chữ ký message sai, producer không được phép hoặc tenant mapping không hợp lệ.
- Command yêu cầu một trạng thái nghiệp vụ không thể xảy ra.
- Message chứa resource reference không tồn tại và contract xác định đây là lỗi cuối cùng.

Những message này nên bị từ chối hoặc đưa vào quarantine/DLQ theo chính sách, không retry liên tục. Với lỗi chữ ký hoặc producer identity, cần tạo security event và điều tra nguồn gửi; không tự động redrive chỉ vì operator thấy message trong DLQ.

### 2.2. Lỗi tạm thời (transient failure)

Lỗi tạm thời có thể tự hết khi dependency hoặc hạ tầng phục hồi:

- Database connection tạm thời không sẵn sàng.
- Provider trả `429` hoặc `503` và có hướng dẫn retry.
- Network timeout ngắn hoặc connection reset.
- Broker/consumer gặp lỗi hạ tầng có thể phục hồi.
- Một lock hoặc tài nguyên dùng chung đang bận trong thời gian ngắn.

Những lỗi này có thể retry nhưng cần backoff, jitter, giới hạn số lần và tổng thời gian. Với `429`, tôn trọng `Retry-After` nếu có và vẫn áp dụng retry budget của hệ thống.

### 2.3. Lỗi không chắc kết quả (ambiguous outcome)

Timeout không luôn có nghĩa thao tác thất bại. Ví dụ provider đã gửi SMS nhưng response bị mất; database đã commit nhưng consumer chưa kịp ack; một payment request đã được nhận nhưng client bị timeout.

Không được xử lý trường hợp này như “chắc chắn chưa làm gì” rồi gửi lại một side effect mới. Cần:

- Dùng idempotency key ổn định cho thao tác nghiệp vụ.
- Tra cứu trạng thái bằng provider request ID hoặc business reference nếu có.
- Ghi trạng thái trung gian như `UNKNOWN` hoặc `PENDING_RECONCILIATION`.
- Chỉ retry side effect sau khi xác định lần trước chưa thành công hoặc provider bảo đảm idempotency.

### 2.4. Ma trận phân loại lỗi

| Nhóm lỗi | Ví dụ | Hành động |
|---|---|---|
| Permanent | Invalid schema, chữ ký sai, command không hợp lệ | Quarantine/DLQ, không retry tự động |
| Transient | `429`, `503`, connection reset | Retry có giới hạn và backoff |
| Ambiguous | Timeout sau khi gửi payment/SMS | Kiểm tra idempotency/trạng thái, reconciliation |
| Unknown | Exception chưa được phân loại | Giới hạn thử lại rất chặt, cảnh báo và quarantine sau ngưỡng |

Không phân loại chỉ dựa trên tên exception chung như `RuntimeException`. Hãy tạo nhóm exception rõ ở adapter của database, broker và provider; mapping phải được review khi dependency thay đổi.

## 3. Nhận diện poison message

Poison message có thể là lỗi dữ liệu, schema, nghiệp vụ hoặc tương tác với một phiên bản consumer. Cần lưu đủ metadata để phân biệt nguyên nhân mà không log payload nhạy cảm.

### 3.1. Dấu hiệu nhận diện

- Cùng `messageId` thất bại nhiều lần với cùng error code.
- Một partition/queue có message đứng đầu không tiến triển trong thời gian dài.
- Tỷ lệ deserialize hoặc validation failure tăng đột biến sau một lần deploy.
- Một message làm consumer restart hoặc crash lặp lại.
- Cùng một payload luôn tạo exception deterministic ở cùng bước.
- Message vượt giới hạn kích thước, depth, số phần tử hoặc thời gian xử lý.

Không phải mọi message có nhiều lần giao đều là poison. Consumer có thể bị restart, lease hết hạn hoặc ack bị mất sau khi xử lý thành công. Cần đối chiếu delivery count, processing state và idempotency record trước khi kết luận.

### 3.2. Phân biệt poison data với lỗi code

Một payload hợp lệ có thể trở thành “poison” khi consumer deploy lỗi hoặc schema compatibility bị phá vỡ. Nếu toàn bộ message của một event type bắt đầu thất bại sau release, nguyên nhân có thể là regression trong code chứ không phải producer gửi dữ liệu độc hại.

Phân tích theo nhóm:

- **Một message duy nhất lỗi:** có thể là dữ liệu sai hoặc trạng thái bất thường.
- **Một schema version lỗi hàng loạt:** có thể là consumer không tương thích schema.
- **Một consumer group lỗi nhưng group khác bình thường:** có thể là code/config riêng của consumer.
- **Nhiều dependency cùng timeout:** có thể là sự cố hạ tầng hoặc retry storm.

Không redrive hàng loạt trước khi xác định nguyên nhân. Nếu bug nằm ở consumer, sửa code và test schema trước; nếu message thực sự không hợp lệ, giữ cách ly và xử lý theo quy trình dữ liệu.

### 3.3. Giới hạn payload trước khi parse sâu

Consumer phải giới hạn kích thước message, độ sâu JSON, số field, số phần tử array và độ dài string trước khi tạo object graph lớn. Không để message độc hại làm parser tiêu thụ memory hoặc CPU vô hạn. Broker maximum message size là lớp đầu; consumer vẫn cần validation riêng vì message có thể đến từ internal producer hoặc đường nhập dữ liệu khác.

## 4. Thiết kế retry có giới hạn

Retry policy cần định nghĩa rõ số lần thử, thời gian chờ, tổng deadline và điều kiện dừng. Không để code tự `catch` rồi `nack(requeue=true)` mà không có giới hạn.

### 4.1. Exponential backoff và jitter

Một công thức backoff có thể dùng:

\[
delay_n = random(0, \min(maxDelay, initialDelay \times 2^{n-1}))
\]

Đây là full jitter: mỗi lần retry chọn thời gian ngẫu nhiên từ 0 đến mức trần tăng theo cấp số nhân. Jitter giúp các consumer không đồng loạt retry đúng cùng một thời điểm.

Ví dụ policy minh họa:

| Lần thử lại | Khoảng chờ tối đa |
|---:|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 16 giây |
| Sau lần 5 | Chuyển DLQ hoặc quarantine theo phân loại |

Các giá trị phải dựa trên latency, retry-after của provider, thời gian phục hồi và SLA. Không copy một lịch cố định cho mọi dependency. Có thể thêm minimum delay để tránh retry ngay lập tức.

### 4.2. Giới hạn số lần và tổng thời gian

Đặt cả:

- Maximum delivery attempts hoặc retry attempts.
- Maximum elapsed time từ lần nhận đầu.
- Maximum retry delay.
- Maximum processing time cho mỗi lần.
- Message TTL/expiry theo nghiệp vụ.
- Retry budget theo queue, tenant hoặc dependency.

Phải định nghĩa rõ “max attempts” có tính lần giao đầu hay chỉ tính lần retry. Ví dụ `maxAttempts = 5` có thể nghĩa tổng cộng năm lần xử lý (một lần đầu và bốn lần retry); ghi rõ semantics trong cấu hình và metric.

Không chỉ dùng delivery count của broker nếu nó có thể reset khi chuyển queue hoặc republish. Nếu cần retry xuyên nhiều queue, lưu attempt metadata được quản lý và xác minh; không tin giá trị `attempt` do producer tùy ý đặt trong payload.

### 4.3. Retry budget

Retry budget giới hạn tổng lượng công việc retry trong một khoảng thời gian hoặc tỷ lệ so với message mới. Khi dependency đang lỗi, hệ thống nên giảm retry thay vì nhân số request lên nhiều lần.

Có thể áp dụng budget theo:

- Dependency/provider, ví dụ tổng retry tới payment gateway.
- Queue hoặc consumer group.
- Tenant để một tenant lỗi không chiếm toàn bộ retry capacity.
- Operation family/cost unit cho email, SMS, export hoặc AI API.
- Toàn hệ thống để bảo vệ database và broker.

Khi budget cạn, đưa message vào delayed queue hoặc tạm dừng consumer theo policy; không chuyển tất cả message hợp lệ sang DLQ ngay lập tức nếu nguyên nhân là sự cố dependency diện rộng. Cần một trạng thái chờ phục hồi riêng hoặc retry schedule có giới hạn.

### 4.4. Không retry lỗi vĩnh viễn

Không retry lỗi như schema invalid, permission denied, unsupported event type hoặc validation failure nếu không có thay đổi điều kiện. Với lỗi `401/403` từ downstream, xác minh credential/config; retry liên tục thường chỉ làm tăng tải và che khuất lỗi cấu hình.

Nếu một lỗi hiện được xem là permanent nhưng có thể được khắc phục bằng deploy consumer mới, đưa message vào DLQ hoặc quarantine để giữ lại và redrive sau khi đã xác minh compatibility. Không requeue nóng trong lúc chờ release.

### 4.5. Không retry ngay trong vòng lặp consumer

Tránh pattern:

```java
while (true) {
    try {
        process(message);
        break;
    } catch (Exception ex) {
        // Retry ngay, không giới hạn
    }
}
```

Vòng lặp này giữ worker, thread và connection trong lúc dependency lỗi. Dùng broker/delayed retry scheduler để lên lịch lần thử sau, giải phóng worker hiện tại và áp dụng giới hạn concurrency.

## 5. Ngăn retry storm và failure cascade

Retry storm xảy ra khi nhiều thành phần cùng cố khôi phục bằng cách gửi thêm tải vào dependency đang suy yếu. Retry cần làm tăng khả năng thành công sau phục hồi, không được làm tăng mức độ sự cố.

### 5.1. Backoff phải đi cùng concurrency limit

Backoff giảm tần suất retry của từng message nhưng không tự giới hạn tổng số message đồng thời. Dùng bulkhead hoặc concurrency limit theo dependency/queue, giới hạn connection pool và giới hạn số request mỗi tenant.

Khi provider chậm, consumer không nên mở thêm vô hạn request mới. Có thể giảm consumer concurrency, tạm dừng intake hoặc xếp hàng có giới hạn. Theo dõi queue age và backlog để tránh queue tăng không kiểm soát.

### 5.2. Circuit breaker

Circuit breaker có thể mở khi tỷ lệ lỗi hoặc latency của dependency vượt ngưỡng, ngăn consumer tiếp tục gọi một dịch vụ đang không khỏe. Khi circuit mở:

- Không gọi dependency cho từng message như bình thường.
- Đưa message vào delayed retry có giới hạn hoặc giữ ở queue theo policy.
- Không ack message nếu chưa có kết quả xử lý bền vững.
- Cho phép half-open probe số lượng nhỏ để xác minh phục hồi.
- Tránh để mỗi consumer instance tự probe quá dày.

Circuit breaker không thay thế retry limit hoặc DLQ. Nó điều tiết việc gọi dependency; message vẫn cần được lưu, trì hoãn hoặc cách ly theo semantics.

### 5.3. Tôn trọng Retry-After và provider quota

Khi provider trả `429` hoặc `503` kèm `Retry-After`, dùng giá trị này làm cơ sở delay nhưng vẫn áp dụng maximum delay và retry budget. Không để một giá trị header bất thường tạo thời gian chờ vô hạn hoặc vượt quá expiry nghiệp vụ.

Nếu provider quota theo tenant/API key, tách budget và concurrency theo credential/tenant để một khách hàng không làm cạn quota của các khách hàng khác.

### 5.4. Backpressure và giới hạn queue

Queue không phải kho lưu trữ vô hạn. Cần đặt:

- Maximum queue depth hoặc storage quota.
- Message size limit.
- Message TTL/retention.
- Consumer concurrency và prefetch/batch size.
- Giới hạn số retry đang chờ.
- Chính sách khi broker gần đầy.

Khi queue vượt ngưỡng, có thể từ chối enqueue mới, áp dụng backpressure cho producer hoặc giảm tốc độ intake. Không xóa message cũ tùy tiện nếu chúng đại diện cho giao dịch nghiệp vụ; cần dead-letter/quarantine hoặc quy trình xử lý backlog được phê duyệt.

### 5.5. Tránh retry đồng loạt sau khi hệ thống phục hồi

Sau một outage, hàng nghìn message có thể cùng đến thời điểm retry. Jitter, retry tier, rate limit và gradual ramp-up giúp dàn tải. Có thể dùng delayed queues nhiều mức (ví dụ 1s, 5s, 30s, 2m) hoặc scheduler có phân tán thời gian; vẫn cần maximum attempts và expiry.

## 6. Dead-letter queue: cách ly, không phải thùng rác

DLQ lưu message không thể xử lý theo policy. Một thiết kế DLQ cần trả lời: message nào được đưa vào, metadata nào được lưu, ai được đọc, bao lâu thì xóa, ai có thể redrive và làm sao tránh side effect trùng.

### 6.1. Khi nào đưa message vào DLQ?

Các trường hợp điển hình:

- Permanent validation/schema/authorization failure cần điều tra.
- Message vượt maximum attempts.
- Message hết hạn trước khi xử lý.
- Consumer không tương thích schema và cần chờ bản sửa.
- Lỗi không phân loại sau số lần thử an toàn.
- Message có dấu hiệu giả mạo hoặc vi phạm security policy cần quarantine riêng.

Không nhất thiết dùng cùng một DLQ cho mọi loại dữ liệu. Có thể tách theo domain, sensitivity hoặc mức độ rủi ro để quyền truy cập và retention phù hợp. Security quarantine cho message chữ ký sai hoặc producer không hợp lệ nên có quy trình điều tra riêng, không được trộn với lỗi nghiệp vụ thông thường.

### 6.2. Metadata tối thiểu trong dead letter

Giữ metadata đủ để điều tra:

| Metadata | Mục đích |
|---|---|
| Original message ID | Deduplication và truy vết |
| Original topic/queue và partition/key | Biết nguồn và thứ tự |
| Message type/schema version | Chọn consumer/schema tương thích |
| Producer identity | Xác minh nguồn gửi |
| Tenant/context reference | Phân vùng và kiểm tra quyền |
| First/last received time | Tính tuổi message |
| Delivery/retry count | Xác định số lần thử |
| Error category/code | Phân loại nguyên nhân |
| Consumer version | Xác định bản code xử lý |
| Correlation/trace ID | Nối log giữa service |
| Redrive history | Biết ai đã phát lại và khi nào |

Không lưu access token, password, private key hoặc secret provider trong header DLQ. Không đưa toàn bộ exception stack trace vào message metadata nếu có thể chứa query, credential hoặc dữ liệu cá nhân.

### 6.3. Lưu payload an toàn

Payload DLQ có thể cần để tái xử lý, nhưng cần bảo vệ:

- Mã hóa khi truyền và khi lưu bằng key do hệ thống quản lý.
- Broker ACL chỉ cấp quyền consumer/producer cần thiết.
- Quyền đọc payload đầy đủ hẹp hơn quyền xem metadata.
- Mask hoặc tokenization field nhạy cảm nếu có thể tái tạo từ nguồn an toàn.
- Retention và deletion theo loại dữ liệu, hợp đồng và nghĩa vụ pháp lý.
- Audit mọi thao tác đọc, export, xóa và redrive.
- Giới hạn message size và storage quota của DLQ.

Nếu cần lưu payload gốc bất biến để điều tra, đặt quyền truy cập riêng và thời hạn lưu rõ. Không sao chép DLQ sang bucket hoặc log chung có quyền rộng hơn broker.

### 6.4. Không để DLQ tạo thành một queue vô hạn

Theo dõi số message, dung lượng, tuổi message cũ nhất và tốc độ tăng. Đặt retention, quota và cảnh báo. Khi DLQ đầy, hành vi phải được định nghĩa: chặn producer, dừng consumer nguồn, chuyển sang secure quarantine storage hoặc phát cảnh báo khẩn cấp. Không âm thầm drop message quan trọng.

## 7. Redrive message từ DLQ một cách có kiểm soát

Redrive là thao tác đưa message đã dead-letter trở lại luồng xử lý. Đây là thao tác có thể tạo side effect thật, do đó cần permission, audit, validation và giới hạn tốc độ.

### 7.1. Quy trình redrive

Một quy trình phù hợp:

1. Operator xem metadata đã mask và error category.
2. Xác định nguyên nhân đã được khắc phục (consumer bug, provider recovery hoặc dữ liệu được sửa).
3. Kiểm tra schema version, tenant, message expiry và policy hiện hành.
4. Xác định redrive theo một message, một nhóm có điều kiện hay toàn bộ DLQ.
5. Yêu cầu permission riêng; thao tác hàng loạt hoặc nhạy cảm có thể cần approval hai người.
6. Tạo redrive job có tốc độ, concurrency và retry budget giới hạn.
7. Giữ original message ID để idempotency; thêm redrive ID và actor vào audit metadata.
8. Theo dõi kết quả và dừng tự động nếu tỷ lệ lỗi tăng trở lại.

Không sửa payload trực tiếp trong DLQ mà không lưu bản gốc và audit. Nếu cần sửa dữ liệu, tạo một corrected message có liên kết tới original message, lý do, actor và nguồn sửa được xác minh.

### 7.2. Kiểm tra message hết hạn và trạng thái nghiệp vụ

Một command có thể không còn hợp lệ khi được redrive nhiều giờ hoặc nhiều ngày sau. Ví dụ yêu cầu xác nhận OTP, gửi thông báo tức thời hoặc thay đổi trạng thái đơn hàng. Kiểm tra `expiresAt`, business state và authorization theo semantics của operation.

Với event đã ghi nhận một sự kiện trong quá khứ, consumer có thể cần xử lý theo event time và version. Với command yêu cầu hành động hiện tại, nên xác minh quyền và điều kiện nghiệp vụ tại thời điểm thực thi. Không mặc định mọi message cũ đều còn hợp lệ.

### 7.3. Bảo toàn idempotency khi redrive

Nếu tạo message ID mới khi redrive mà không giữ original ID, consumer có thể coi đó là thao tác mới và lặp side effect. Duy trì original business message ID hoặc idempotency key; lưu redrive attempt riêng.

Một message đã xử lý thành công nhưng bị dead-letter do ack/commit lỗi có thể xuất hiện trong DLQ hoặc được giao lại. Inbox/deduplication record cần ngăn thực thi nghiệp vụ lần hai. Tuy nhiên, không dùng deduplication vô thời hạn nếu ID có thể được tái sử dụng; cần phạm vi và retention phù hợp.

### 7.4. Redrive không được bỏ qua authorization

Operator có quyền quản lý queue không tự động có quyền thực hiện nghiệp vụ mà message đại diện. Consumer phải xác minh producer identity, tenant và command authorization theo policy. Redrive tool không được biến payload thành một cách cấp quyền mới.

Nếu cần replay sự kiện đã được producer tin cậy phát hành, giữ nguyên bằng chứng nguồn gốc và kiểm tra signature/integrity theo thiết kế. Không cho operator sửa `tenantId`, actor hoặc permission trong message để “làm cho chạy được”.

## 8. Delivery semantics, acknowledgment và idempotency

Broker thường cung cấp một trong các semantics at-most-once, at-least-once hoặc hỗ trợ exactly-once trong phạm vi nhất định. Không nên hiểu exactly-once của broker là side effect bên ngoài cũng chỉ xảy ra một lần.

### 8.1. At-least-once và duplicate delivery

At-least-once ưu tiên không mất message nhưng có thể giao trùng. Consumer phải idempotent: xử lý cùng một message nhiều lần không tạo thêm side effect nghiệp vụ.

Một mô hình inbox đơn giản:

```sql
CREATE TABLE processed_messages (
    consumer_name   VARCHAR(100) NOT NULL,
    message_id      VARCHAR(200) NOT NULL,
    processed_at    TIMESTAMP NOT NULL,
    result_ref      VARCHAR(200),
    PRIMARY KEY (consumer_name, message_id)
);
```

Trong cùng transaction với cập nhật dữ liệu nghiệp vụ, consumer insert `(consumer_name, message_id)`. Nếu unique constraint báo đã tồn tại, message đã được xử lý và có thể acknowledge theo policy. Việc ghi inbox và business update cần nằm trong cùng transaction database để tránh đánh dấu processed nhưng chưa commit nghiệp vụ hoặc ngược lại.

### 8.2. Acknowledge sau khi kết quả đã bền vững

Không ack trước khi side effect quan trọng đã được lưu bền vững. Nếu ack trước rồi process thất bại, message có thể mất. Nếu process xong nhưng ack thất bại, message có thể giao lại; idempotency xử lý trường hợp này.

Với thao tác gọi provider ngoài database, transaction local không thể bao trùm broker và provider. Dùng outbox/inbox, idempotency key provider, trạng thái workflow và reconciliation. Không giả định một transaction database có thể rollback email hoặc payment đã được provider thực hiện.

### 8.3. Chuyển sang DLQ phải tránh mất message

Khi chuyển message sang DLQ, chỉ ack/commit offset nguồn sau khi DLQ publish đã được broker xác nhận bền vững. Nếu có thể, dùng transaction hoặc cơ chế atomic dead-letter của broker. Nếu publish DLQ thành công nhưng ack nguồn thất bại, có thể tạo bản DLQ trùng; DLQ consumer/tool cần deduplicate theo original message ID.

Nếu ack nguồn trước rồi publish DLQ thất bại, message có thể mất hoàn toàn. Không làm theo thứ tự đó trừ khi broker cung cấp một thao tác atomic được bảo đảm.

### 8.4. Retry topic và thứ tự message

Một số broker không hỗ trợ delay từng message thuận tiện. Có thể dùng retry queue/topic theo các mức delay. Cần cân nhắc ordering: chuyển một message sang retry topic có thể cho phép message sau vượt lên trước. Với nghiệp vụ yêu cầu thứ tự, dùng partition/key strategy, sequence number hoặc pause partition theo policy.

Không để một poison message chặn vô thời hạn cả partition nếu có thể cách ly an toàn. Ngược lại, không bỏ qua message đầu nếu thứ tự là invariant nghiệp vụ. Đây là quyết định domain, không chỉ là cấu hình broker.

## 9. Xác thực và phân quyền message ở consumer

Message broker là một kênh truyền dữ liệu, không phải bằng chứng rằng payload đáng tin. Consumer cần xác minh nguồn gửi và quyền của message giống như một API boundary.

### 9.1. Xác minh producer identity

- Bật authentication cho producer và consumer tới broker.
- Dùng ACL theo topic/queue/exchange; chỉ producer được cấp quyền mới publish loại message tương ứng.
- Dùng workload identity hoặc mTLS nếu hạ tầng hỗ trợ.
- Với trust boundary đặc biệt, cân nhắc chữ ký message và timestamp/nonce để phát hiện tampering/replay.
- Không tin `producerName` hoặc `serviceName` chỉ vì chúng nằm trong JSON payload.

Broker ACL chứng minh workload nào được publish vào destination; nó không nhất thiết chứng minh từng field trong payload đúng. Consumer vẫn cần schema validation và business validation.

### 9.2. Không tin tenant ID hoặc actor trong payload

Payload có thể chứa `tenantId`, `userId`, `requestedBy` hoặc `role`. Các field này là dữ liệu đầu vào. Consumer cần xác minh producer có quyền phát message cho tenant đó và resource có thuộc tenant đó không. Với command đại diện cho hành động của user, lưu actor/delegation context đã được xác minh và kiểm tra permission theo policy.

Không dùng `tenantId` từ payload để mở rộng phạm vi query. Tenant context phải được xác minh qua producer grant, message signature hoặc mapping server-side; sau đó repository vẫn cần tenant predicate.

### 9.3. Quyết định authorization tại thời điểm nào?

Với event, producer có thể phát một fact đã xảy ra sau khi authorization được kiểm tra tại thời điểm ghi nhận. Consumer xác minh producer và tính toàn vẹn event, rồi xử lý theo contract event. Với command trì hoãn hoặc có side effect nhạy cảm, consumer thường cần kiểm tra lại quyền và trạng thái resource tại thời điểm thực thi.

Thiết kế phải nói rõ quyền được chốt ở thời điểm enqueue hay execution. Nếu membership bị thu hồi trong lúc message nằm trong queue, behavior cần được định nghĩa và kiểm thử. Không để worker chạy một command cũ với quyền rộng chỉ vì lúc enqueue user từng là admin.

### 9.4. Chống replay và message giả mạo

Dùng message ID duy nhất, timestamp/expiry, idempotency store và chữ ký hoặc transport identity phù hợp. Với command nhạy cảm, có thể ràng buộc chữ ký với message type, tenant, audience, payload hash và issued-at. Consumer từ chối message quá hạn hoặc đã được xử lý theo policy.

Không dùng timestamp đơn lẻ làm chống replay; attacker có thể gửi lại message trong cửa sổ thời gian hợp lệ. Cần deduplication hoặc nonce store.

## 10. Ví dụ Java: consumer phân loại lỗi và chuyển DLQ

Ví dụ sau minh họa flow broker-agnostic. Các interface `Delivery`, `RetryScheduler`, `DeadLetterPublisher` và `Inbox` là abstraction của ứng dụng; API ack/commit thực tế khác nhau giữa RabbitMQ, Kafka, SQS và các broker khác.

```java
public final class MessageConsumer {
    private final MessageValidator validator;
    private final MessageAuthorization authorization;
    private final BusinessHandler handler;
    private final FailureClassifier classifier;
    private final RetryPolicy retryPolicy;
    private final RetryScheduler retryScheduler;
    private final DeadLetterPublisher deadLetters;
    private final Inbox inbox;

    public void onDelivery(Delivery delivery) {
        MessageEnvelope message;
        try {
            message = validator.validateAndDecode(delivery.body());
            authorization.requireAllowedProducerAndTenant(
                    delivery.authenticatedProducer(), message);
        } catch (PermanentMessageException | SecurityMessageException ex) {
            deadLetterThenAcknowledge(delivery, null, ex);
            return;
        }

        try {
            inbox.executeOnce(message.messageId(), () ->
                    handler.process(message));
        } catch (Exception ex) {
            FailureKind kind = classifier.classify(ex);
            int attempt = delivery.trustedDeliveryCount();

            if (kind == FailureKind.PERMANENT
                    || kind == FailureKind.SECURITY
                    || retryPolicy.exhausted(attempt, message)) {
                deadLetterThenAcknowledge(delivery, message, ex);
                return;
            }

            if (kind == FailureKind.AMBIGUOUS) {
                inbox.markOutcomeUnknown(message.messageId(), ex);
                retryScheduler.scheduleReconciliation(message, ex);
                delivery.acknowledgeAfterDurableSchedule();
                return;
            }

            Duration delay = retryPolicy.nextDelay(attempt, ex);
            retryScheduler.scheduleDurably(message, attempt + 1, delay);
            delivery.acknowledgeAfterDurableSchedule();
            return;
        }

        // Ack nằm ngoài catch nghiệp vụ: ack failure không được phân loại
        // nhầm thành lỗi xử lý và tạo thêm retry/DLQ. Broker có thể giao lại;
        // Inbox sẽ ngăn side effect nghiệp vụ lặp.
        delivery.acknowledge();
    }

    private void deadLetterThenAcknowledge(
            Delivery delivery, MessageEnvelope message, Exception error) {
        DeadLetterRecord record = DeadLetterRecord.from(
                delivery, message, SafeErrors.code(error));
        deadLetters.publishAndConfirm(record);
        delivery.acknowledge();
    }
}
```

Đây là pseudocode để thể hiện thứ tự và ranh giới, không phải implementation có thể copy nguyên trạng. Một số điểm cần giữ:

- `authenticatedProducer()` phải đến từ broker connection/session đã xác minh, không lấy từ payload.
- Parser/schema/authorization adapter phải chuẩn hóa lỗi dữ liệu không hợp lệ thành `PermanentMessageException` và lỗi trust boundary thành `SecurityMessageException`.
- `trustedDeliveryCount()` là metadata do broker hoặc retry subsystem quản lý; không tin `attempt` tùy ý trong JSON.
- `Inbox.executeOnce` cần bảo đảm inbox record và business update nằm trong transaction phù hợp.
- `publishAndConfirm` chỉ trả thành công sau khi DLQ message được lưu bền vững.
- `scheduleDurably` phải xác nhận retry đã được lưu trước khi ack message nguồn.
- Nếu ack sau khi publish/schedule thất bại, có thể có bản trùng; original message ID và deduplication phải xử lý được.
- Ack thất bại sau business commit là tình huống giao lại, không phải lý do để chạy thêm business handler; inbox/deduplication xử lý lần giao sau.
- Với ambiguous outcome, không gọi lại side effect ngay; reconciliation phải xác định trạng thái trước.

Trong triển khai thật, tránh giữ transaction database mở trong lúc gọi provider hoặc chờ broker. Dùng các transaction ngắn, outbox/inbox hoặc workflow state machine để nối các bước.

## 11. Khác biệt cần biết giữa các broker

Khái niệm chung giống nhau nhưng cơ chế retry, ack và DLQ của từng broker khác nhau. Không chuyển cấu hình giữa các broker mà không xem lại semantics.

| Broker | Cơ chế thường dùng | Điểm cần kiểm tra |
|---|---|---|
| RabbitMQ | `ack`, `nack/reject`, requeue, dead-letter exchange/queue, TTL/delay pattern | `requeue=true` có thể tạo hot loop; kiểm tra DLX routing và publisher confirm |
| Apache Kafka | Retry topic, dead-letter topic, offset commit, consumer group | Commit offset chỉ sau khi xử lý hoặc publish DLT bền vững; cân nhắc ordering theo partition |
| Amazon SQS | Visibility timeout, receive count, redrive policy, DLQ | Visibility timeout phải phù hợp processing time; `maxReceiveCount`, retention và redrive allow policy cần được cấu hình |
| Azure Service Bus | Delivery count, abandon/defer/dead-letter, lock duration | Lock renewal, max delivery count, DLQ access và scheduled delivery |

### 11.1. RabbitMQ

Nếu consumer `nack` với `requeue=true` ngay khi lỗi, message có thể quay lại queue lập tức và được giao cho cùng consumer liên tục. Dùng retry queue/delay pattern hoặc cơ chế retry được quản lý; khi lỗi permanent hoặc hết số lần thử, dead-letter sang queue riêng. Kiểm tra cấu hình dead-letter exchange, routing key, publisher confirms và quyền đọc DLQ.

### 11.2. Kafka

Kafka lưu message theo partition và consumer quản lý offset. Một message lỗi lặp có thể khiến consumer không commit offset và partition không tiến triển. Có thể publish message lỗi sang dead-letter topic rồi commit offset nguồn, nhưng phải bảo đảm publish DLT đã được xác nhận; transaction của Kafka có thể giúp kết hợp produce và offset commit trong phạm vi broker. Không để consumer commit offset trước khi message được xử lý hoặc DLT lưu thành công.

Khi dùng retry topic, thứ tự message có thể thay đổi vì message lỗi được xử lý sau các message đến tiếp theo. Nếu nghiệp vụ cần ordering, thiết kế partition/key và retry flow phải giữ invariant đó.

### 11.3. Amazon SQS

SQS dùng visibility timeout để tạm ẩn message trong lúc consumer xử lý. Nếu processing lâu hơn visibility timeout, message có thể xuất hiện lại và bị xử lý đồng thời. Đặt timeout phù hợp, gia hạn visibility khi cần và dùng idempotency. Redrive policy với `maxReceiveCount` đưa message sang DLQ sau số lần nhận quy định; kiểm tra retention của source và DLQ, quyền redrive và giới hạn tốc độ khi đưa message trở lại.

### 11.4. Azure Service Bus

Service Bus có delivery count, lock duration và dead-letter reason. Consumer cần gia hạn lock khi xử lý dài, nhưng không gia hạn vô hạn. Dùng dead-letter reason/code ổn định, hạn chế payload nhạy cảm trong description và kiểm soát quyền peek/receive/dead-letter/redrive.

## 12. Kiểm thử poison message và retry behavior

Test cần chứng minh lỗi được phân loại đúng, retry không vượt budget và DLQ không làm mất message hoặc tạo side effect trùng.

### 12.1. Ma trận test theo loại lỗi

| Trường hợp | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Invalid JSON | Body không parse được | Không retry nóng; quarantine/DLQ |
| Schema không hỗ trợ | Event version lạ | Từ chối có mã lỗi, giữ metadata |
| Signature sai | Producer/message không xác minh được | Security quarantine và alert |
| Tenant mismatch | Payload tenant không khớp producer grant/resource | Từ chối, không truy vấn ngoài scope |
| Permanent business error | Transition không hợp lệ | Không retry vô ích |
| Transient `503` | Dependency phục hồi sau vài lần | Retry theo backoff và thành công trong budget |
| `429 Retry-After` | Provider yêu cầu chờ | Delay tôn trọng header và maximum policy |
| Retry exhaustion | Luôn trả lỗi transient đến hết ngưỡng | DLQ một lần theo original message ID |
| Ambiguous timeout | Provider đã nhận nhưng response mất | Reconciliation/idempotency, không gửi trùng |
| Duplicate delivery | Cùng message ID được giao hai lần | Business side effect chỉ xảy ra một lần |
| DLQ publish failure | Broker không xác nhận publish | Không ack message nguồn |
| Ack failure sau xử lý | Business transaction đã commit | Delivery trùng không tạo side effect mới |
| Redrive hết hạn | Message quá `expiresAt` | Không thực hiện command cũ |
| Redrive không quyền | Operator thiếu permission | Từ chối và audit |

### 12.2. Test retry storm

Mô phỏng dependency trả `503` cho nhiều message đồng thời. Xác minh:

- Số request downstream không vượt concurrency limit.
- Backoff có jitter và không tập trung tất cả retry vào cùng một thời điểm.
- Circuit breaker mở khi ngưỡng lỗi đạt điều kiện.
- Retry budget được áp dụng theo dependency/tenant.
- Queue depth, oldest message age và retry backlog không tăng vô hạn.
- Khi dependency phục hồi, consumer tăng tốc có kiểm soát.

### 12.3. Test DLQ và redrive

- DLQ record có original message ID, source, error code và timestamp.
- Payload được mã hóa và chỉ principal được cấp quyền mới đọc được.
- Operator không thể sửa tenant/actor hoặc phát lại message ngoài phạm vi.
- Redrive job có rate limit, approval và audit.
- Message duplicate không lặp side effect.
- Message hết hạn hoặc schema không tương thích không được redrive mù quáng.
- DLQ storage quota/retention hoạt động đúng và phát cảnh báo trước khi đầy.

### 12.4. Test crash ở các điểm ranh giới

Mô phỏng consumer crash:

1. Trước khi bắt đầu xử lý.
2. Sau khi ghi inbox nhưng trước business commit.
3. Sau business commit nhưng trước ack.
4. Sau provider call nhưng trước khi ghi kết quả.
5. Sau khi publish DLQ/retry nhưng trước ack nguồn.

Sau mỗi tình huống, kiểm tra message có được giao lại đúng, side effect có bị lặp không và không có message bị mất. Đây là các test quan trọng hơn việc chỉ assert một exception được ném ra.

## 13. Monitoring, alert và incident response

Không chỉ theo dõi số lượng message trong queue. Cần quan sát tuổi message, số lần giao, tốc độ retry và tình trạng dependency.

Metric hữu ích:

- `messages_received_total`, `messages_processed_total`, `messages_failed_total`.
- Retry count và retry delay theo queue, consumer, error category.
- DLQ depth, DLQ ingress rate, oldest message age và storage bytes.
- Delivery count/attempt distribution.
- Consumer processing latency, timeout, crash/restart và concurrency.
- Queue backlog, oldest unprocessed age, partition lag hoặc visibility timeout expiry.
- Dependency error rate, latency, `429/5xx` và circuit breaker state.
- Idempotency duplicate count và ambiguous outcome count.
- Redrive count, actor, success/failure và rate.

Không dùng `messageId`, email, phone hoặc tenant ID làm metric label không giới hạn cardinality. Có thể dùng log/trace có kiểm soát để điều tra theo ID. Metric nên aggregate theo queue, message type, consumer version và error category.

### 13.1. Alert theo xu hướng

Tạo cảnh báo khi:

- DLQ depth hoặc oldest message age vượt ngưỡng.
- Tỷ lệ poison message tăng sau deployment.
- Retry rate tăng nhanh hơn message ingress.
- Circuit breaker mở kéo dài.
- Consumer lag tăng trong khi throughput giảm.
- Một tenant hoặc producer tạo lượng message bất thường.
- DLQ storage gần quota hoặc retention job thất bại.
- Redrive job chạy vượt rate hoặc có nhiều lỗi lặp.

Ngưỡng cần dựa trên baseline và SLA. Một DLQ tăng từ 0 lên 20 message có thể đáng chú ý với payment command nhưng bình thường với telemetry có thể bỏ qua; phân loại theo loại message và tác động.

### 13.2. Xử lý sự cố retry storm

1. Xác định dependency và queue/consumer bị ảnh hưởng.
2. Giảm consumer concurrency hoặc tạm dừng retry tới dependency đang lỗi.
3. Mở circuit breaker và giữ message trong delayed retry theo policy.
4. Bảo vệ luồng nghiệp vụ thiết yếu bằng quota/bulkhead riêng.
5. Xác định message có side effect đã xảy ra nhưng response không rõ.
6. Chỉ resume tăng tải từ từ khi dependency phục hồi.
7. Đối soát idempotency, retry và provider usage để tìm thao tác trùng.

### 13.3. Xử lý poison message hàng loạt

Nếu nhiều message cùng schema/type thất bại sau deploy, cân nhắc rollback hoặc hotfix consumer. Giữ message trong DLQ/retry buffer có giới hạn và bảo toàn ordering khi cần. Sau khi sửa, chạy test trên bản sao dữ liệu đã mask, xác minh schema compatibility rồi redrive theo batch nhỏ.

Nếu phát hiện message giả mạo hoặc có tenant mismatch, không redrive. Cách ly producer/credential liên quan, kiểm tra broker ACL, audit và các consumer đã nhận message. DLQ security quarantine cần được bảo vệ khỏi thao tác sửa payload không có kiểm soát.

## 14. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| `nack(requeue=true)` ngay lập tức | Hot loop, consumer bận với cùng message | Delayed retry, backoff và max attempts |
| Retry mọi exception | Retry lỗi vĩnh viễn, tăng tải | Failure classifier rõ ràng |
| Không có jitter | Nhiều consumer retry đồng thời | Exponential backoff + jitter |
| Không giới hạn tổng thời gian | Message cũ được thực hiện sau khi hết ý nghĩa | Deadline, TTL và expiry |
| Ack trước business commit | Mất message khi xử lý thất bại | Ack sau durable outcome |
| Không idempotency | Duplicate delivery tạo side effect trùng | Inbox, provider idempotency và reconciliation |
| Publish DLQ rồi không confirm | Ack nguồn có thể làm mất message | Confirm DLQ trước ack hoặc dùng atomic broker transaction |
| Commit Kafka offset trước DLT publish | Message lỗi bị mất | Publish DLT bền vững rồi commit/transaction |
| DLQ không có ACL | Payload nhạy cảm bị đọc rộng | Least privilege, encryption và audit |
| Redrive toàn bộ DLQ một lần | Tạo retry storm mới | Batch, rate limit, canary và stop condition |
| Tin tenant/actor trong payload | Cross-tenant action | Producer identity, grant mapping và consumer authorization |
| Không kiểm tra message expiry | Command cũ gây side effect | Validate expiry và business state khi thực thi |
| Log toàn bộ payload/exception | Rò secret và PII | Safe error code, redaction và payload access control |

## 15. Checklist review trước khi phát hành

- [ ] Message có ID duy nhất, type, schema version và metadata cần thiết.
- [ ] Producer/consumer xác thực với broker; ACL giới hạn publish/consume theo queue/topic.
- [ ] Consumer xác minh producer identity, tenant mapping và command authorization.
- [ ] Payload có giới hạn size, depth, field, array và schema trước xử lý sâu.
- [ ] Lỗi được phân loại permanent, transient, ambiguous và unknown.
- [ ] Retry có max attempts, max elapsed time, TTL và maximum delay.
- [ ] Backoff có jitter; `Retry-After` được tôn trọng trong giới hạn policy.
- [ ] Có retry budget, concurrency limit, circuit breaker và backpressure.
- [ ] Poison message được cách ly; không requeue nóng vô hạn.
- [ ] DLQ có ACL, encryption, retention, quota, audit và metadata an toàn.
- [ ] Payload DLQ không lưu secret không cần thiết; quyền đọc nội dung được giới hạn.
- [ ] DLQ publish được xác nhận bền vững trước khi ack/commit message nguồn.
- [ ] Consumer idempotent; inbox/business update có transaction phù hợp.
- [ ] Side effect ngoài database dùng idempotency và reconciliation.
- [ ] Redrive có permission, approval theo rủi ro, rate limit, expiry check và audit.
- [ ] Redrive giữ original message ID và ghi redrive history riêng.
- [ ] Message command kiểm tra quyền/trạng thái tại thời điểm thực thi theo semantics đã định nghĩa.
- [ ] Có test duplicate, crash boundary, DLQ publish failure, retry storm và poison payload.
- [ ] Dashboard/alert theo dõi backlog, oldest age, retry, DLQ và dependency health.
- [ ] Có runbook xử lý retry storm, poison message và redrive hàng loạt.

## Kết luận

Poison message cần được nhận diện và cách ly; retry phải có phân loại lỗi, backoff, jitter, budget và giới hạn thời gian; DLQ phải được bảo vệ như một kho dữ liệu nhạy cảm. Consumer cần idempotency và chỉ acknowledge sau khi kết quả đã bền vững. Redrive phải xác minh nguyên nhân, expiry, tenant, quyền và tốc độ để không tái tạo sự cố. Khi kết hợp các cơ chế này với monitoring và kiểm thử crash/retry thực tế, hệ thống async có thể phục hồi lỗi mà không khuếch đại tải hoặc biến message broker thành đường vòng bảo mật.

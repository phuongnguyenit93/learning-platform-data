# Duplicate event failure test

## 1. Vì sao event trùng là một ca lỗi bảo mật?

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, event có thể kích hoạt xác minh bằng chứng, hoàn tất recovery, thu hồi session hoặc gửi thông báo khi người dùng mất mật khẩu, MFA, passkey hay thiết bị xác thực. Một event được xử lý nhiều lần có thể gây nhiều hơn việc ghi log lặp: nó có thể tạo thêm recovery grant, đặt lại credential lần nữa hoặc làm sống lại một request đã đóng.

Ví dụ điển hình: consumer hoàn tất đổi mật khẩu trong database, sau đó chết trước khi xác nhận bản tin với broker. Broker giao lại event; consumer chạy lại phần đổi mật khẩu và tạo một session mới. Lần giao lại là điều có thể dự kiến, nhưng tác động cấp quyền lặp là lỗi của hợp đồng xử lý.

Tài liệu Amazon SQS nêu rằng bản sao của message có thể được nhận lại và ứng dụng cần xử lý theo cách idempotent. Không nên coi việc message được giao đúng một lần là tiền đề mặc định của test. [Amazon SQS — At-least-once delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues-at-least-once-delivery.html).

Mục tiêu của bài là thiết kế phép thử chứng minh một tác động nhạy cảm chỉ được áp dụng theo số lần mà nghiệp vụ cho phép, kể cả khi có giao lại, crash và xử lý đồng thời. Tên event, bảng và interface dưới đây là minh họa; chúng không xác nhận dự án đang có những thành phần đó.

### 1.1. Idempotent không có nghĩa mọi thứ đều bất biến

Gọi `P(s)` là phần trạng thái nhạy cảm cần bảo vệ và `handle(s, e)` là xử lý event e. Với một event đã được áp dụng hợp lệ, mong muốn thường là:

```text
P(handle(handle(s, e), e)) = P(handle(s, e))
```

Phần trạng thái này có thể gồm credential version, generation của recovery grant, tập session được cấp và trạng thái token đã tiêu thụ. Log số lần giao, metric duplicate và journal thử xử lý vẫn có thể tăng.

Do đó, “chỉ một lần xử lý” cần được diễn đạt chính xác. Có thể có hai lần gọi handler nhưng chỉ một lần commit tác động nghiệp vụ. Đếm số dòng log không đủ để kết luận.

## 2. Phân loại event trùng trước khi đặt oracle

| Trường hợp | Đặc điểm | Kiểm soát cần kiểm tra |
| --- | --- | --- |
| Broker giao lại cùng event | Cùng event ID và nội dung nghiệp vụ | Khử trùng lặp theo danh tính event trong đúng scope |
| Producer phát lại cùng lệnh với ID mới | Event ID khác nhưng cùng operation logic | Idempotency nghiệp vụ hoặc state transition có điều kiện |
| Cùng event ID, nội dung khác | Xung đột về danh tính hoặc toàn vẹn dữ liệu | Phát hiện conflict, không âm thầm áp dụng payload thứ hai |
| Event cũ đến lại sau thời gian dài | Có thể không còn inbox record | Hiệu lực hiện tại, version và trạng thái kết thúc vẫn bảo vệ |
| Hai event hợp lệ khác nhau | Cùng account nhưng khác thao tác/generation | Không loại nhầm chỉ vì trùng subject |
| Event từ nguồn không được phép | ID có thể giống event hợp lệ | Xác thực nguồn và phân quyền trước khi tin dữ liệu |

Một test chỉ publish cùng JSON hai lần chưa bao phủ producer sinh event ID mới cho cùng thao tác. Ngược lại, một test dùng cùng account ID cho hai thao tác khác nhau có thể vô tình kiểm tra việc loại bỏ công việc hợp lệ.

### 2.1. Transport ID và event ID

Một broker có thể cấp message ID hoặc delivery tag riêng cho từng lần publish hay từng lần giao. Nếu dùng delivery tag làm khóa deduplication, bản giao lại có thể trông như một event mới.

Cần chỉ rõ ID nào ổn định theo hợp đồng producer, ID nào chỉ dùng để xác nhận một lần giao, và ID nào định danh thao tác nghiệp vụ. Test nên lưu cả ba trong probe để đối chiếu, nhưng không xem chúng là những giá trị thay thế cho nhau.

### 2.2. Một event có nhiều consumer hợp lệ

Một event recovery hoàn tất có thể được consumer session xử lý và consumer thông báo xử lý. Đó là hai tác động khác nhau. Nếu dùng một bảng “event đã xử lý” toàn hệ thống mà không có scope consumer/action, consumer thứ hai có thể bị bỏ qua nhầm.

Bài test cần gửi cùng một event tới các consumer được phép và chứng minh mỗi tác động của chúng xảy ra đúng policy. “Đã được một consumer xử lý” không đồng nghĩa mọi consumer khác đều phải bỏ qua.

## 3. Mô hình event và ranh giới tin cậy

Một envelope minh họa cho yêu cầu hoàn tất recovery:

```json
{
  "eventId": "evt-test-001",
  "producer": "recovery-orchestrator",
  "eventType": "FinalizeRecoveryRequested",
  "schemaVersion": 1,
  "tenantId": "tenant-test-a",
  "recoveryId": "recovery-test-001",
  "operationId": "finalize-test-001",
  "expectedGeneration": 3,
  "proofRef": "proof-test-001",
  "occurredAt": "2026-11-24T00:00:00Z"
}
```

Envelope không chứa OTP, raw recovery token, mật khẩu hay cookie. Nếu thao tác cần tham chiếu tới dữ liệu credential đã được chuẩn bị, việc lưu và tham chiếu đó phải có bảo vệ phù hợp; không đưa bí mật vào một event để mọi consumer đều đọc được.

Trường `producer` trong JSON không tự chứng minh nguồn phát. Consumer phải xác thực qua cơ chế của transport, webhook hoặc chữ ký theo thiết kế, rồi kiểm tra nguồn đó có quyền yêu cầu loại thao tác tương ứng trên tenant hay không.

Tương tự, một field `proofRef` không tự là bằng chứng hợp lệ. Consumer cần ràng buộc proof với recovery, subject, purpose, generation và điều kiện hiệu lực tại điểm mà policy yêu cầu. Không cho payload tự khai `verified=true` thay thế trạng thái đáng tin.

### 3.1. Thời điểm xảy ra không quyết định quyền hiện tại

`occurredAt` phục vụ lịch sử và đối chiếu. Không dùng timestamp từ payload như một cách bỏ qua việc proof đã bị thu hồi hoặc request đã hủy trước khi event thực sự được áp dụng.

Một số thiết kế đã cấp một authorization có hiệu lực riêng ở thời điểm trước; thiết kế khác yêu cầu kiểm tra lại tại bước commit. Test phải nêu hợp đồng cụ thể, bao gồm cách xử lý việc thu hồi giữa hai thời điểm. Đừng tự biến event thành một quyền có hiệu lực vô hạn.

### 3.2. Xác thực trước khi ghi dấu event

Nếu caller không đáng tin có thể ghi một event ID vào inbox trước, event hợp lệ về sau có thể bị xem là duplicate và bị mất tác động. Đây là một dạng đầu độc deduplication.

Tạo một bản tin giả dùng cùng ID với bản tin hợp lệ, nhưng không có quyền nguồn hoặc sai tenant. Sau khi xử lý bản giả theo policy, gửi bản thật và chứng minh bản giả không chiếm mất quyền xử lý hợp lệ.

Không mở một endpoint test cho client tùy ý publish vào luồng recovery production. Fault injection và event emitter cần nằm trong môi trường kiểm thử được định vị rõ.

## 4. Danh tính event và danh tính thao tác nghiệp vụ

Một khóa event khái niệm có thể là:

```text
eventKey =
    environment
  | consumerAction
  | trustedProducerNamespace
  | trustedTenantScope
  | stableEventId
```

Scope thực tế phụ thuộc cách producer bảo đảm tính duy nhất. Nếu event ID đã duy nhất toàn cục thì vẫn cần xem cách nhiều consumer dùng cùng ID. Nếu chỉ duy nhất trong một provider account hoặc tenant, không bỏ mất namespace đó.

Một khóa thao tác nghiệp vụ có thể khác:

```text
businessOperationKey =
    tenant
  | recoveryId
  | generation
  | operationType
  | operationId
```

Không phải tất cả field trên đều bắt buộc trong mọi hệ thống. Điều cần kiểm tra là hai envelope biểu diễn cùng thao tác không được tạo hai tác động nhạy cảm; hai thao tác hợp lệ khác nhau không bị hợp nhất ngoài ý muốn.

### 4.1. Cùng ID nhưng payload khác

Sau khi xác thực và phân quyền, so sánh những field nghiệp vụ bất biến theo hợp đồng. Ví dụ cùng event ID nhưng đổi recovery ID, tenant hoặc operation type là conflict cần được xử lý rõ.

Một fingerprint có thể hỗ trợ đối chiếu, nhưng phải định nghĩa dữ liệu canonical. Header retry, delivery tag hoặc thứ tự field JSON không nên làm một event logic trở thành xung đột. Ngược lại, việc bỏ qua quá nhiều field có thể che thay đổi có ý nghĩa.

Fingerprint không thay thế chữ ký hay phân quyền. Nếu payload chứa dữ liệu nhạy cảm, không đưa nó nguyên vẹn vào log khi conflict. Quyết định quarantine, báo lỗi hoặc dừng xử lý cần tuân hợp đồng vận hành, không âm thầm chọn payload tới sau.

### 4.2. Hai ID cho cùng thao tác

Producer có thể bị timeout sau khi publish rồi phát lại với ID mới. Inbox theo event ID có thể ghi cả hai event là hợp lệ; việc ngăn tác động thứ hai phải dựa vào operation identity hoặc state transition.

Test tạo `E1` và `E2` có event ID khác nhau nhưng cùng `operationId`, recovery và generation. Kỳ vọng có thể là hai event được ghi nhận, nhưng chỉ một lần tiêu thụ authorization và một lần chuyển trạng thái.

Một operation ID mới cũng không đương nhiên cho phép hoàn tất lại một recovery đã COMPLETED. Điều kiện nghiệp vụ phải được bảo vệ độc lập với việc caller hoặc producer đổi khóa.

## 5. Bất biến cần chứng minh trong account recovery

| Bất biến | Oracle cụ thể |
| --- | --- |
| Một authorization không bị tiêu thụ nhiều lần | Số transition tiêu thụ và liên kết tới operation |
| Recovery không hoàn tất lại ngoài policy | Trạng thái, generation và completion record |
| Không tạo nhiều lần đổi credential | Credential version và journal của thao tác |
| Không cấp thêm quyền do giao lại | Số grant/session được tạo cho cùng operation |
| Request đóng không bị mở lại | CANCELLED, EXPIRED, COMPLETED giữ đúng vòng đời |
| Proof cũ không vượt proof mới | Binding và generation được kiểm tra |
| Thu hồi session không lan sang phiên ngoài phạm vi | Tập session theo cutoff/epoch hoặc tiêu chí policy |
| Thông báo không phát lặp ngoài hợp đồng | Intent theo operation và submit thực tế |
| Không mất công việc sau crash trước commit | Event được xử lý lại khi chưa có tác động đã commit |
| Không đổi tenant hoặc purpose do collision | Dữ liệu subject, tenant, source và thao tác |
| Event độc hại không đầu độc inbox | Bản hợp lệ vẫn có đường được xử lý |
| Log duplicate không lộ bí mật | Report/trace không chứa raw token hoặc credential |

Một policy có thể cố ý tạo nhiều thông báo, ví dụ thông báo riêng tới kênh cũ và kênh mới. Khi đó oracle là mỗi notification purpose/recipient hợp lệ có đúng intent cần thiết, không ép toàn bộ recovery chỉ có một thông báo.

Số version cũng cần được diễn giải theo implementation. Nếu version tăng vì một tác động audit hợp lệ, không dùng nó để khẳng định password đã đổi. Nên có credential version hoặc operation journal phân biệt được tác động nhạy cảm.

## 6. Ranh giới transaction, inbox và outbox

Một mô hình thường dùng là commit dấu xử lý event, thay đổi trạng thái nghiệp vụ và ý định gửi tiếp trong cùng database transaction.

```text
Nhận bản tin và xác thực nguồn
        |
        v
BEGIN
  Giành quyền xử lý event trong inbox
  Kiểm tra fingerprint hoặc kết quả đã có nếu bị conflict
  Kiểm tra binding, generation, hiệu lực và trạng thái nghiệp vụ
  Áp dụng đúng một chuyển trạng thái được phép
  Ghi ý định tác động ngoài database vào outbox nếu cần
  Ghi kết quả xử lý event
COMMIT
        |
        v
ACK hoặc commit vị trí đọc theo hợp đồng broker
```

Nếu transaction rollback, dấu “đã xử lý xong” không được tồn tại độc lập rồi khiến bản giao lại bị bỏ qua. Nếu transaction đã commit nhưng ACK bị mất, bản giao lại cần tìm thấy kết quả bền vững và không áp dụng tác động lần nữa.

ACK và database commit thường không nằm trong cùng một transaction. Chính khoảng trống đó là mục tiêu chèn lỗi, không phải điều có thể bỏ qua bằng cách đặt tên hàm `processExactlyOnce`.

Kafka mô tả các bảo đảm xử lý trong phạm vi của Kafka và việc phối hợp với hệ thống đích bên ngoài. Không suy từ một cấu hình transaction của broker rằng database credential hay provider SMS cũng tự có cùng bảo đảm. [Apache Kafka — Message Delivery Semantics](https://kafka.apache.org/41/design/design/#message-delivery-semantics).

### 6.1. Ví dụ giành quyền xử lý bằng unique constraint

Với PostgreSQL, một schema minh họa có thể có khóa duy nhất theo scope event:

```sql
CREATE TABLE recovery_event_inbox (
    consumer_action TEXT NOT NULL,
    producer_scope TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    payload_fingerprint TEXT NOT NULL,
    outcome TEXT NOT NULL,
    PRIMARY KEY (consumer_action, producer_scope, tenant_id, event_id)
);
```

Một câu lệnh giành quyền xử lý trong transaction:

```sql
INSERT INTO recovery_event_inbox (
    consumer_action, producer_scope, tenant_id,
    event_id, payload_fingerprint, outcome
)
VALUES (
    :consumer_action, :producer_scope, :tenant_id,
    :event_id, :payload_fingerprint, 'IN_TRANSACTION'
)
ON CONFLICT (
    consumer_action, producer_scope, tenant_id, event_id
)
DO NOTHING
RETURNING event_id;
```

Nếu insert trả về một hàng, transaction này có thể tiếp tục theo nhánh mới. Nếu không trả hàng, cần đọc và xử lý kết quả đã có theo isolation và retry policy của transaction. Không được tiếp tục tác động nghiệp vụ như thể insert đã thành công.

PostgreSQL quy định `RETURNING` trả dữ liệu từ các hàng thực sự được insert hoặc update; `DO NOTHING` không tự tạo một hàng kết quả thay thế. Đây là chi tiết quan trọng để kiểm tra adapter đọc kết quả SQL. [PostgreSQL 18 — INSERT](https://www.postgresql.org/docs/18/sql-insert.html).

Trong mô hình này, `IN_TRANSACTION` là giá trị tạm chưa được commit. Trước khi commit phải đổi thành kết quả cuối hoặc rollback toàn bộ. Nếu hệ thống chủ ý commit trạng thái PROCESSING rồi thực hiện sau, cần thêm lease, phục hồi và fencing; đó là một hợp đồng khác cần các test riêng.

Không dùng `ON CONFLICT DO UPDATE` chỉ để ghi đè fingerprint/payload cũ bằng payload tới sau. Việc đó có thể biến xung đột danh tính thành thay đổi dữ liệu không được xem xét.

### 6.2. Không mặc định mọi lỗi unique đều là duplicate an toàn

Một unique violation ở bảng credential, grant hoặc outbox có thể là lỗi khác với event đã xử lý. Consumer cần phân biệt đúng constraint và kết quả nghiệp vụ, không bắt mọi exception rồi ACK như duplicate.

Nếu dùng câu lệnh insert thường và database làm transaction chuyển sang trạng thái lỗi, cần rollback hoặc xử lý bằng cơ chế transaction đúng trước khi tiếp tục query. Test với database thật sẽ phát hiện những giả định mà repository mock thường bỏ qua.

### 6.3. Outbox không bao trùm tác động ngoài hệ thống

Outbox giúp ghi bền vững ý định trong transaction nghiệp vụ. Worker phát outbox vẫn có thể chết sau khi provider nhận request nhưng trước khi ghi kết quả.

Vì vậy test cần phân biệt “một notification intent” với “một submit tới provider” và “một tin thực sự đến”. Nếu provider không có hợp đồng idempotency tương ứng, không hứa exactly once cho delivery vật lý. Tác động cấp quyền vẫn cần được bảo vệ độc lập.

## 7. Thiết lập fixture và probe

Chuẩn bị một recovery đang ở đúng trạng thái cho thao tác cần kiểm tra. Nếu test event hoàn tất, proof và authorization phải được tạo qua fixture đáng tin, còn hiệu lực và đúng purpose. Đừng gửi một event sai hết điều kiện rồi lấy việc bị từ chối làm bằng chứng deduplication.

Fixture nên cung cấp:

- Namespace dữ liệu biệt lập cùng tenant/account tổng hợp.
- Event hợp lệ có ID ổn định và operation ID xác định.
- Producer test có quyền đúng loại event; một nguồn không có quyền cho ca âm.
- Fault hook quanh inbox insert, business write, COMMIT và ACK.
- Broker hoặc transport test cho phép giao lại có kiểm soát.
- Probe đọc trạng thái đã commit, outbox, grant và session.
- Provider sink để đo tác động ngoài database.
- Cơ chế dừng consumer/fault và cleanup đúng namespace.

Probe không được sửa trạng thái mà nó đang kiểm tra. Ví dụ `awaitCommitted` phải đợi commit thật hoặc journal thật, không tự ghi trạng thái COMPLETED để test tiếp tục.

Dùng correlation ID cho từng lần giao để phân tích lịch thực thi, nhưng giữ event ID và operation ID đúng ý nghĩa. Nếu mỗi lần “giao lại” lại đổi mọi ID, bạn đang kiểm tra producer duplicate, không kiểm tra transport redelivery.

## 8. Ca cơ sở: cùng event được giao tuần tự

Thực hiện lần lượt:

1. Snapshot credential, recovery, grant và session trước xử lý.
2. Giao event E hợp lệ và chờ tác động đã commit.
3. Snapshot trạng thái sau E lần đầu.
4. Giao lại E với cùng các field nghiệp vụ.
5. Chờ consumer xử lý xong bản giao lại.
6. Đối chiếu trạng thái nhạy cảm với snapshot ở bước 3.
7. Đối chiếu inbox/outbox với số operation được phép.

Bản thứ hai có thể được ACK với kết quả duplicate hoặc kết quả đã xử lý trước đó tùy transport. HTTP 200, ACK thành công hay log “duplicate” chỉ là tín hiệu; cần đọc trạng thái để chứng minh không có password version, grant hoặc session mới.

Đếm attempt có thể là hai; đếm tác động hoàn tất phải đúng một trong fixture này. Một inbox row không đủ để chứng minh tác động chỉ xảy ra một lần nếu code đã đổi credential trước khi insert inbox.

### 8.1. Kiểm tra cả trường hợp lần đầu thất bại

Tạo lỗi có thể retry trước commit. Sau đó giao lại event hợp lệ khi lỗi đã được gỡ. Kỳ vọng tác động được áp dụng một lần, thay vì event bị bỏ qua vì dấu đã xử lý được commit quá sớm.

Ca này bảo vệ khả năng tiến triển. Một consumer bỏ qua mọi event sau lần nhìn thấy đầu tiên có thể tránh tác động lặp nhưng cũng làm mất toàn bộ công việc chưa hoàn thành.

## 9. Tạo cạnh tranh giữa nhiều consumer

Một implementation kiểu “SELECT xem đã có chưa, nếu chưa thì xử lý rồi INSERT” có thể vượt test tuần tự nhưng thất bại khi hai consumer cùng thấy chưa có inbox record.

Thiết kế lịch thực thi để tạo va chạm:

```text
Consumer A nhận E                    Consumer B nhận bản sao E
       |                                     |
       v                                     v
  Sẵn sàng trước điểm giành quyền      Sẵn sàng trước điểm giành quyền
       |                                     |
       +------------- mở barrier ------------+
                             |
                  Cùng tranh xử lý event
                             |
                Quan sát commit và kết quả
```

Dùng hai instance hoặc process với cùng database nếu cần kiểm tra phạm vi phân tán. Một lock `synchronized` trong một JVM có thể bảo vệ object cục bộ nhưng không bảo vệ consumer ở JVM khác.

Không chỉ tăng số thread rồi hy vọng chúng va chạm. Fault hook hoặc barrier tại điểm trước giành quyền giúp chứng minh lịch thử thực sự đi qua vùng có rủi ro. Thu thập mọi exception và timeout; không lọc bỏ những tác vụ lỗi trước khi đếm thành công.

Kết quả đạt trong fixture một lần hoàn tất có thể là:

```text
Số lần nhận E:                         N
Số transition hoàn tất đã commit:      1
Số authorization được tiêu thụ:        1
Số grant của operation:                theo policy, không tăng do duplicate
Số notification intent từng purpose:   theo policy
Số event bị conflict payload:          0 trong ca cùng nội dung
```

Một consumer có thể đợi lock, nhận kết quả đã xử lý hoặc retry transaction sau lỗi tạm thời. Không ép mọi consumer phải trả cùng một internal status ngay lập tức; điều cần chứng minh là an toàn và kết thúc được trong giới hạn môi trường test.

### 9.1. Bản khác ID cùng cạnh tranh

Lặp lại lịch trên với E1 và E2 khác event ID nhưng cùng operation. Nếu chỉ inbox event ID được bảo vệ, cả hai có thể giành quyền thành công. Test lúc này phải chứng minh ràng buộc nghiệp vụ, operation key hoặc cập nhật có điều kiện ngăn tác động thứ hai.

Tiếp theo dùng hai operation hợp lệ khác nhau để làm ca đối chứng. Nếu cả hai bị gộp vì cùng account ID, cơ chế chống trùng đang quá rộng và làm mất công việc hợp lệ.

## 10. Ma trận crash quanh commit và ACK

| Điểm chèn crash | Trạng thái bền vững mong đợi trong mô hình transaction chung | Khi giao lại |
| --- | --- | --- |
| Trước inbox insert | Chưa có dấu hoàn tất và chưa có tác động | Có thể xử lý lần đầu |
| Sau insert, trước business write | Transaction chưa commit nên phải rollback khi connection kết thúc | Không bị dấu tạm chặn vĩnh viễn |
| Sau business write, trước COMMIT | Toàn bộ transaction rollback | Có thể áp dụng đúng một lần về sau |
| Sau COMMIT, trước ACK | Inbox, business state và outbox đã bền vững | Không lặp tác động |
| Trong lúc client không biết COMMIT đã thành công chưa | Kết quả chưa rõ đối với client | Tra cứu/retry không tạo tác động thêm |
| Sau ACK bị broker nhận nhưng client thấy lỗi | Tùy kết quả broker, có thể không giao lại | Không phát lại thủ công một thao tác mới ngoài policy |
| Sau lease hết hạn, worker cũ trở lại | Phụ thuộc cơ chế claim nhiều bước | Fencing/version ngăn worker cũ ghi đè sai |

Cần tạo crash ngoài cùng transaction đang đánh giá. Nếu test method và consumer dùng chung một transaction được test framework rollback ở cuối, không thể dùng kết quả đó để khẳng định database đã commit rồi ACK bị mất.

Đối với crash process, xác nhận process hoặc connection thực sự kết thúc và database đã xử lý transaction đang mở. Một exception bị bắt bên trong handler có thể không tương đương process chết; journal phải cho biết điểm lỗi thực tế.

### 10.1. Mất phản hồi COMMIT

Client có thể không biết transaction đã commit hay chưa nếu connection mất ở thời điểm nhạy cảm. Khi đó không được kết luận “exception đồng nghĩa rollback”.

Tạo hai ca riêng với fault controller biết kết quả ở database: một ca commit chưa xảy ra và một ca commit đã xảy ra nhưng phản hồi bị mất. Sau khi consumer khởi động lại, dùng inbox, operation record và trạng thái nguồn chuẩn để xác định kết quả, không tự chạy lại tác động nhạy cảm vô điều kiện.

Nếu muốn trả kết quả đã có cho một request đồng bộ, không tạo một raw recovery token hoặc refresh token mới chỉ vì caller retry. Hợp đồng trả lại dữ liệu nhạy cảm cần được thiết kế riêng; một event consumer có thể chỉ cần ghi nhận outcome và ACK.

### 10.2. Không ACK sớm để làm mất bản tin

Tạo lỗi sau khi handler ACK nhưng trước khi database có tác động bền vững, nếu implementation có điểm như vậy. Nếu không còn một bản tin hoặc journal hợp lệ để tiếp tục, hệ thống đã làm mất công việc.

Test không nên chỉ bảo vệ at-most-once effect mà bỏ qua liveness. Cần chứng minh công việc hợp lệ chưa commit vẫn có đường hoàn thành sau khi lỗi tạm thời kết thúc.

## 11. Duplicate của những tác động ngoài transaction

### 11.1. Thông báo recovery

Một notification intent có thể duy nhất theo operation, purpose và recipient đã được policy chọn. Tuy vậy dispatcher có thể submit lặp sau khi provider nhận tin nhưng phản hồi bị mất.

Oracle cần ghi rõ ba số: số intent, số submit attempt và số message provider test tạo. Với provider hỗ trợ idempotency đúng phạm vi, có thể yêu cầu một message logic. Với provider không có bảo đảm đó, tiêu chí cần nêu giới hạn retry và khả năng duplicate delivery được chấp nhận; không suy từ một outbox row thành một SMS vật lý.

Duplicate notification không được phát mã mới, thay generation, reset số lượt thử hoặc tạo quyền recovery mới ngoài policy. Nếu một bản tin cũ mang mã đã bị thay thế tới muộn, validator vẫn phải kiểm tra hiệu lực hiện tại.

### 11.2. Thu hồi session có phạm vi

Một event `RevokeRecoverySessions` có thể nhắm tới các session trước một auth epoch hoặc cutoff đã định. Lần đầu thực hiện đúng, nhưng bản duplicate tới muộn có thể làm hỏng session hợp lệ tạo sau recovery nếu handler thực hiện lại lệnh “revoke tất cả hiện tại” không có phạm vi.

Ca thử minh họa:

1. Chuẩn bị session cũ thuộc epoch E0.
2. Xử lý event thu hồi nhắm đúng phạm vi E0.
3. Hoàn tất recovery và tạo session mới ở epoch E1 theo policy.
4. Giao lại cùng event thu hồi cũ.
5. Xác minh session E0 vẫn bị từ chối; session E1 được xử lý đúng policy đã chốt.

Không mặc định mọi hệ thống đều cho session E1 sống sau event đó. Điều cần có là phạm vi thu hồi rõ ràng; nếu policy chủ ý thu hồi rộng hơn thì test phản ánh phạm vi ấy. Event cũ không được tự mở rộng quyền chỉ vì được giao lại muộn.

### 11.3. Cấp quyền ở hệ thống khác

Nếu consumer gọi identity provider hoặc session service bên ngoài để đổi factor hay thu hồi quyền, transaction local không tự bảo đảm tác động đó chỉ xảy ra một lần.

Tạo lỗi sau khi downstream áp dụng nhưng trước khi consumer lưu kết quả. Kiểm tra idempotency key, operation reference, reconcile và khả năng xác định kết quả chưa rõ theo hợp đồng downstream. Không hoàn tác bằng một thao tác có ý nghĩa khác nếu chưa chứng minh nó tương đương an toàn.

Một compensating action cũng có thể được giao lại. Nếu có cơ chế này, cần thêm test cho danh tính thao tác và phạm vi của chính compensation.

## 12. Event cũ, trạng thái kết thúc và thời hạn deduplication

Bản ghi inbox có thể được dọn sau một thời gian. Khi đó cùng event ID xuất hiện lại có thể không còn bị chặn bằng dấu đã xử lý. Recovery vẫn phải được bảo vệ bằng trạng thái và authorization nguồn chuẩn.

Tạo test với quy trình dọn hợp lệ của môi trường test:

```text
Áp dụng event E cho recovery R, generation G
        |
        v
Đóng R và thu hồi/tiêu thụ quyền liên quan
        |
        v
Cho inbox record hết thời gian giữ theo policy
        |
        v
Giao lại E bằng cơ chế replay hợp lệ của test
        |
        v
Không mở R, không cấp grant/session mới, không đổi credential lại
```

Không xóa thủ công dấu deduplication trong production để “thử”. Với test tích hợp, dùng namespace biệt lập và cơ chế retention/clock được kiểm soát. Clock của ứng dụng không tự điều khiển lịch cleanup ở một kho khác.

### 12.1. Chọn thời gian giữ theo các đường phát lại

Cần xem xét retry broker, lưu message, dead-letter queue, replay vận hành, backup/restore và producer phát lại. Thời hạn inbox không nên được chọn chỉ vì “cache một ngày có vẻ đủ”.

Nếu có đường replay không giới hạn theo thời gian, một inbox có TTL hữu hạn không thể một mình bảo vệ mãi. Cần state transition, operation record, tombstone hoặc ràng buộc phù hợp giữ được an toàn sau khi dấu transport đã dọn.

Không giữ raw proof hoặc token để kéo dài khả năng deduplication. Có thể giữ định danh operation và outcome tối thiểu theo chính sách lưu dữ liệu, với kiểm soát truy cập và vòng đời riêng.

### 12.2. CANCELLED và EXPIRED không bị hồi sinh

Chuẩn bị event hợp lệ ở thời điểm tạo nhưng trì hoãn xử lý. Trong lúc đó hủy request, thu hồi proof hoặc cho authorization hết hiệu lực theo policy. Sau đó giao nhiều bản sao.

Kỳ vọng không phải mọi event trễ đều bị xử lý theo cùng một lý do. Điều cần chứng minh là chúng không được tự chuyển request đã đóng về trạng thái có quyền, và lý do bỏ qua/từ chối được ghi nhận đúng hợp đồng.

Đối với recovery đã COMPLETED, một duplicate đã được áp dụng trước đó có thể được ACK như outcome cũ. Điều đó khác với việc áp dụng lại event theo trạng thái mới của tài khoản.

### 12.3. Restore và replay vận hành

Nếu khôi phục database từ backup cũ nhưng broker còn message mới hơn, inbox, credential state và operation record có thể không ở cùng một mốc. Test restore cần mô tả mốc dữ liệu và điều kiện cho phép consumer chạy lại.

Không tự xem reset offset hoặc replay dead-letter queue là thao tác an toàn chỉ vì handler có một hàm tên `isDuplicate`. Kiểm tra cả thời điểm ledger bị mất, phiên bản schema thay đổi và trạng thái quyền hiện tại.

## 13. Duplicate kết hợp đảo thứ tự và thay đổi schema

Một luồng có thể nhận `RecoveryCancelled`, sau đó nhận lại `ProofVerified` cũ. Nếu handler chỉ ghi đè state bằng state trong payload, request có thể quay lại đường hoàn tất.

Thiết kế ca thử theo các transition được phép. Nếu event tới khi thiếu điều kiện tiên quyết, hệ thống có thể trì hoãn, reconcile từ nguồn chuẩn hoặc từ chối theo hợp đồng; không tự cấp trạng thái tương lai chỉ để tiếp tục xử lý.

Không dùng sequence number làm phép “nếu lớn hơn thì tin mọi nội dung”. Sequence phải được gắn đúng aggregate và nguồn; event có số cao nhưng sai tenant, sai proof hay không có quyền vẫn không hợp lệ.

Cũng không bỏ mọi số nhỏ mà chưa xem đó có phải một consumer khác hoặc một tác động độc lập cần thực hiện. Tính thứ tự và deduplication là hai điều kiện liên quan nhưng không thay thế nhau.

### 13.1. Event cùng ý nghĩa qua hai schema

Nếu producer hoặc replay tool chuyển event cũ sang schema mới, hãy xác định ID và operation identity được giữ hay thay đổi. Hai envelope khác byte không nhất thiết là hai nghiệp vụ mới.

Tạo ca schemaVersion cũ còn hỗ trợ, schema mới và version chưa được hỗ trợ. Bản không hiểu được không được ACK như “đã xử lý thành công” nếu điều đó làm mất tác động cần thiết; cũng không được retry nóng vô hạn.

Kiểm tra fingerprint theo hợp đồng canonical của từng schema hoặc phép chuyển đổi được phê duyệt. Không đổi cách so sánh mà không xem những inbox record đã lưu trước đó.

## 14. Mẫu hợp đồng kiểm thử Java

Đoạn sau minh họa JUnit 5 cho consumer hoàn tất recovery. Fixture chuẩn bị một recovery hợp lệ, có đúng một transition hoàn tất và một authorization tiêu thụ theo policy của ví dụ. Đây là interface test harness cần adapter, chưa phải test chạy độc lập.

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

abstract class DuplicateRecoveryEventContract {
    record EventRef(String stableEventId) {}
    record DeliveryRef(String value) {}
    record OperationRef(String value) {}

    record SensitiveSnapshot(long credentialVersion,
                             long recoveryGeneration,
                             int grantsForOperation,
                             int sessionsForOperation,
                             boolean completed) {}

    interface Harness extends AutoCloseable {
        OperationRef prepareEligibleRecovery();
        EventRef trustedFinalizeEvent(OperationRef operation);
        DeliveryRef publish(EventRef event);
        void awaitHandled(DeliveryRef delivery, Duration deadline);

        SensitiveSnapshot snapshot(OperationRef operation);
        int committedFinalizations(OperationRef operation);
        int authorizationConsumptions(OperationRef operation);

        // Hook chặn ACK sau khi transaction thật đã commit.
        void crashAfterCommitBeforeAckOnce();
        void awaitConsumerStoppedAfterCommit(Duration deadline);
        void restartConsumer();

        // Chờ broker giao lại event và consumer xử lý xong bản giao lại.
        void awaitBrokerRedeliveryHandled(EventRef event, Duration deadline);

        @Override
        void close();
    }

    protected abstract Harness newHarness();

    @Test
    void sequentialDuplicateDoesNotCreateAnotherSensitiveEffect() {
        try (Harness h = newHarness()) {
            OperationRef operation = h.prepareEligibleRecovery();
            EventRef event = h.trustedFinalizeEvent(operation);

            h.awaitHandled(h.publish(event), Duration.ofSeconds(5));
            SensitiveSnapshot once = h.snapshot(operation);
            assertTrue(once.completed());
            assertEquals(1, h.committedFinalizations(operation));

            h.awaitHandled(h.publish(event), Duration.ofSeconds(5));

            assertEquals(once, h.snapshot(operation));
            assertEquals(1, h.committedFinalizations(operation));
            assertEquals(1, h.authorizationConsumptions(operation));
        }
    }

    @Test
    void committedWorkSurvivesCrashAndRedeliveryWithoutReapplying() {
        try (Harness h = newHarness()) {
            OperationRef operation = h.prepareEligibleRecovery();
            EventRef event = h.trustedFinalizeEvent(operation);

            h.crashAfterCommitBeforeAckOnce();
            h.publish(event);
            h.awaitConsumerStoppedAfterCommit(Duration.ofSeconds(5));

            SensitiveSnapshot committed = h.snapshot(operation);
            assertTrue(committed.completed());
            assertEquals(1, h.committedFinalizations(operation));
            assertEquals(1, h.authorizationConsumptions(operation));

            h.restartConsumer();
            h.awaitBrokerRedeliveryHandled(event, Duration.ofSeconds(10));

            assertEquals(committed, h.snapshot(operation));
            assertEquals(1, h.committedFinalizations(operation));
            assertEquals(1, h.authorizationConsumptions(operation));
        }
    }
}
```

Lần publish thứ hai ở test đầu cần giữ event ID và payload nghiệp vụ. Nó có thể có transport ID mới; đó là điều test muốn bao phủ.

Ở test thứ hai, hook phải cho transaction commit thật rồi làm consumer dừng trước ACK. Nếu hook ném exception trước commit, test đang kiểm tra rollback, không kiểm tra cửa sổ mất ACK. Nếu harness tự publish một event mới thay vì quan sát broker giao lại, cần báo đúng phạm vi đó.

Các hàm đếm phải đọc tác động bền vững của operation, không đếm số lần gọi mock repository. Snapshot giúp phát hiện việc tạo grant/session mới dù trạng thái recovery cuối vẫn là COMPLETED.

Để kiểm tra nhiều process, thêm ca riêng phát các bản sao đồng thời qua những consumer instance được xác nhận bằng trace. Không suy từ hai test trên rằng race condition phân tán đã được kiểm tra.

## 15. Ma trận kiểm thử tổng hợp

| ID | Tình huống | Điều kiện đạt |
| --- | --- | --- |
| DUP-01 | Cùng event giao hai lần tuần tự | Không lặp tác động nhạy cảm |
| DUP-02 | Cùng event đồng thời qua nhiều consumer | Một transition nghiệp vụ trong fixture |
| DUP-03 | Hai event ID, cùng operation | Không tạo hai tác động của cùng operation |
| DUP-04 | Cùng ID, payload nghiệp vụ khác | Phát hiện conflict, không ghi đè outcome cũ |
| DUP-05 | Cùng local ID ở hai tenant/source scope | Không loại nhầm hoặc xử lý nhầm tenant |
| DUP-06 | Event giả tới trước bản thật | Không đầu độc quyền xử lý event hợp lệ |
| DUP-07 | Crash sau inbox insert, trước commit | Không có dấu hoàn tất độc lập làm mất việc |
| DUP-08 | Crash sau business write, trước commit | Rollback đúng phạm vi transaction |
| DUP-09 | Commit xong, ACK bị mất | Giao lại không áp dụng lại tác động |
| DUP-10 | COMMIT response không rõ | Reconcile theo trạng thái bền vững |
| DUP-11 | Thông báo đã được provider nhận rồi timeout | Đo intent/submit/delivery theo hợp đồng riêng |
| DUP-12 | Duplicate thu hồi session đến sau session mới | Giữ phạm vi cutoff/epoch theo policy |
| DUP-13 | Event trễ sau CANCELLED/EXPIRED | Không hồi sinh request hoặc authorization |
| DUP-14 | Replay sau khi inbox đã dọn | Ràng buộc nghiệp vụ vẫn ngăn tác động sai |
| DUP-15 | Duplicate kết hợp đảo thứ tự | State machine không lùi hoặc vượt điều kiện |
| DUP-16 | Hai consumer hợp lệ cùng xử lý event | Mỗi action được thực hiện đúng, không loại nhầm |
| DUP-17 | Schema cũ/mới của cùng thao tác | Giữ identity và điều kiện xử lý theo hợp đồng |
| DUP-18 | Hai operation hợp lệ khác nhau cùng account | Không bị gộp bởi khóa quá rộng |
| DUP-19 | Replay từ dead-letter/restore | Không bỏ qua hiệu lực hiện tại hoặc cấp lại quyền |
| DUP-20 | Dedupe store lỗi hoặc không truy cập được | Không tự chạy tác động nhạy cảm vô điều kiện |

Ở DUP-20, một cơ chế thay thế dựa trên unique operation key hoặc conditional transition có thể vẫn bảo vệ được nghiệp vụ nếu đã được thiết kế. Test phải đánh giá cơ chế thật, không tự coi mọi cache dedupe lỗi đều là lý do được tiếp tục.

## 16. Báo cáo, quan sát và bài tập

### 16.1. Báo cáo đủ điều kiện tái hiện

Một report nên có event identity, operation identity, consumer action, tenant test, schema/policy version, điểm chèn lỗi, topology, số lần giao và số tác động đã commit.

```text
CASE: DUP-09
FAULT: database commit succeeds, consumer stops before broker ACK
SCOPE: isolated recovery operation; one allowed finalization
TOPOLOGY: record actual broker, database and consumer instances
OBSERVATIONS:
  first delivery committed the operation
  broker redelivered the same stable event
  second handling did not change the sensitive snapshot
  completion and authorization-consumption counts stayed at one
EXTERNAL_EFFECTS: report notification/session-service checks separately
RESULT: fill PASS/FAIL from actual observations, not from this example
```

Không ghi raw token, OTP, mật khẩu hoặc session cookie vào report. Event payload cũng có thể chứa reference nhạy cảm; lưu dữ liệu tối thiểu cần tái hiện và giới hạn truy cập tương ứng.

Metric duplicate hữu ích để phát hiện tăng bất thường nhưng không phải oracle duy nhất. Metric có thể bị trễ, mất hoặc gộp nhiều test. Đọc dữ liệu thuộc namespace và operation cụ thể để kết luận tác động.

Sau khi thử, dừng consumer/fault test, gỡ barrier và dọn đúng namespace. Không reset offset, xóa inbox toàn hệ thống hoặc purge queue dùng chung để làm số đếm trở về không.

### 16.2. Diễn giải lỗi theo tác động

Một phát hiện cụ thể có thể là: “Hai bản giao cùng event chạy qua hai instance trước inbox insert; database ghi hai grant khác ID cho cùng operation, dù chỉ có một inbox row cuối cùng.”

Một phát hiện khác: “Sau khi inbox record hết thời gian giữ, replay event cũ tạo thêm session trên recovery đã COMPLETED; kiểm tra trạng thái nghiệp vụ không được áp dụng ở nhánh replay.”

Cũng cần ghi nhận mất công việc: “Consumer commit dấu DONE trước khi thay credential, chết ở giữa; bản giao lại được ACK như duplicate nhưng credential chưa từng thay.” Đây là lỗi khác với tác động bị lặp, dù đều liên quan cách đặt ranh giới xử lý.

### 16.3. Bài tập thiết kế

**Bài tập A — Hai danh tính khác nhau.** Tạo hai event ID cho cùng operation hoàn tất recovery. Nêu vì sao unique inbox theo event ID chưa đủ và chọn oracle chứng minh chỉ có một tác động nhạy cảm.

**Bài tập B — Dấu đã xử lý quá sớm.** Thiết kế fault sau khi commit dấu dedupe nhưng trước business write trong một implementation cố ý sai. Mô tả cách test phát hiện công việc bị mất, thay vì chỉ thấy không có tác động lặp.

**Bài tập C — Session mới sau recovery.** Xác định policy cutoff/epoch, xử lý thu hồi session cũ rồi tạo session mới. Giao lại event cũ và chứng minh phạm vi thu hồi không tự mở rộng.

**Bài tập D — Replay sau retention.** Cho inbox hết thời gian giữ trong namespace test, sau đó replay event đã hoàn tất. Liệt kê những ràng buộc ngoài inbox cần quan sát để chứng minh request không được mở lại.

**Bài tập E — Event giả chiếm ID.** Gửi bản không có quyền nguồn trước bản hợp lệ dùng cùng ID. Đề xuất quan sát để chứng minh bản giả không chặn công việc thật và không làm lộ thông tin outcome của event thật.

Một duplicate event failure test đạt mục tiêu khi vừa ngăn tác động nhạy cảm bị áp dụng thêm, vừa bảo đảm công việc hợp lệ chưa hoàn thành vẫn có thể tiếp tục sau lỗi, trong đúng phạm vi quyền và vòng đời của recovery.

# Thiết kế tác vụ idempotent khi thực thi lại

Compute có thể bị thu hồi (interruptible compute) như Spot VM, preemptible VM hoặc worker dùng capacity có thể thu hồi thường có chi phí thấp hơn hoặc tận dụng năng lực dư thừa của cloud. Đổi lại, nhà cung cấp có thể dừng instance khi cần capacity, khi chính sách cung cấp thay đổi hoặc theo điều kiện của dịch vụ. Một tác vụ đang chạy vì vậy có thể bị ngắt trước khi hoàn tất.

Để tận dụng compute loại này an toàn, ứng dụng phải giả định một tác vụ có thể chạy lại trên cùng máy, máy khác hoặc ở thời điểm khác. **Idempotency** giúp nhiều lần thực thi cùng một thao tác logic tạo ra kết quả nghiệp vụ tương đương một lần thực thi. Khi kết hợp với checkpoint bền vững, deduplication, transaction và retry có kiểm soát, hệ thống có thể tiếp tục công việc sau khi instance bị thu hồi mà không tạo thanh toán trùng, ghi dữ liệu lặp hoặc làm sai trạng thái.

Trong module CLOUD_CORE_SERVICES_COMPUTE, bài học đặt thiết kế idempotent trong bối cảnh workload chạy trên VM, container và worker có thể bị thay thế. Trọng tâm là xác định ranh giới công việc, lưu tiến độ bên ngoài vòng đời instance, xử lý side effect an toàn và kiểm chứng khả năng chạy lại sau interruption.

Sau bài học, bạn có thể:

- Giải thích vì sao interruptible compute cần thiết kế theo giả định tác vụ có thể bị chạy lại.
- Phân biệt idempotency, retry, deduplication, checkpoint và exactly-once processing.
- Thiết kế idempotency key ổn định cho request, job và từng bước xử lý.
- Dùng unique constraint, transaction, outbox và fencing để ngăn side effect trùng.
- Lưu checkpoint bền vững và khôi phục tiến độ sau khi worker bị thu hồi.
- Xử lý interruption notice, graceful stop, queue visibility/lease và retry.
- Kiểm thử tác vụ khi bị dừng ở các thời điểm khác nhau mà vẫn bảo toàn dữ liệu.

## 1. Vì sao interruptible compute cần idempotency?

Interruptible compute là năng lực tính toán mà instance có thể bị thu hồi trước khi người dùng chủ động kết thúc. Các tên thường gặp gồm Spot Instance, Spot VM, preemptible VM hoặc capacity có thể thu hồi. Cơ chế và thời gian cảnh báo khác nhau theo nhà cung cấp, loại dịch vụ, region và nguyên nhân thu hồi.

Các tình huống có thể làm tác vụ bị gián đoạn:

- Nhà cung cấp cần lấy lại capacity để phục vụ nhu cầu ưu tiên cao hơn.
- Instance không còn đáp ứng điều kiện cung cấp hoặc capacity pool thay đổi.
- Người vận hành scale-in, thay image hoặc bảo trì hạ tầng.
- VM/container bị lỗi host, mất kết nối hoặc bị terminate đột ngột.
- Worker bị restart trong lúc deploy hoặc cập nhật cấu hình.
- Lease của message hết hạn và queue giao lại công việc cho worker khác.

Một tác vụ có thể đã thực hiện một phần side effect trước khi bị dừng. Ví dụ:

1. Worker đọc job tạo hóa đơn.
2. Worker ghi file PDF vào object storage.
3. Worker ghi record hóa đơn vào database.
4. Instance bị thu hồi trước khi xác nhận message hoàn tất.
5. Queue giao lại message cho worker khác.
6. Worker mới chạy lại từ đầu và có thể tạo thêm file hoặc record trùng.

Nếu tác vụ không được thiết kế để chạy lại, interruption có thể dẫn đến dữ liệu trùng, thiếu dữ liệu, trạng thái nửa chừng hoặc chi phí xử lý lặp. Idempotency làm cho lần thực thi tiếp theo có thể nhận biết phần việc đã hoàn tất và tiếp tục an toàn.

### Nguyên tắc thiết kế

Hãy giả định:

- Instance có thể biến mất mà không chạy được shutdown hook.
- Interruption notice, nếu có, chỉ là cơ hội lưu tiến độ, không phải bảo đảm luôn nhận được.
- Request hoặc message có thể được gửi lại sau timeout.
- Worker có thể hoàn tất side effect nhưng chết trước khi gửi acknowledgement.
- Hai worker có thể cùng xử lý một job nếu lease hết hạn hoặc retry chồng lấn.
- Local RAM và ephemeral disk không phải nơi lưu tiến độ duy nhất.
- Một job có thể chạy trên instance hoặc phiên bản ứng dụng khác với lần trước.

## 2. Phân biệt các khái niệm cốt lõi

Các cơ chế thường được dùng cùng nhau nhưng giải quyết những vấn đề khác nhau.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Retry | Thử lại thao tác khi lỗi tạm thời | Gửi lại message sau timeout |
| Idempotency | Lặp lại cùng thao tác logic không tạo thêm tác động nghiệp vụ | Cùng key thanh toán chỉ tạo một khoản thu |
| Deduplication | Nhận biết và bỏ qua sự kiện/job đã xử lý | Lưu message ID đã commit |
| Checkpoint | Lưu tiến độ để tiếp tục từ điểm đã hoàn thành | Đã xử lý đến partition 42 |
| Transaction | Nhóm nhiều thay đổi dữ liệu thành một đơn vị commit/rollback | Ghi kết quả và đánh dấu job hoàn tất cùng transaction |
| Lease/lock | Quy định worker nào đang được phép xử lý trong một khoảng thời gian | Worker giữ lease của job trong 30 giây |
| Fencing token | Ngăn worker cũ ghi dữ liệu sau khi quyền sở hữu đã chuyển | Mỗi lease mới có generation tăng dần |
| Outbox | Ghi thay đổi nghiệp vụ và event cần phát trong cùng transaction | Commit order và outbox event cùng lúc |
| Compensation/Saga | Hoàn tác hoặc bù trừ side effect không thể nằm trong transaction chung | Hoàn tiền khi bước sau thất bại |

### Idempotency không đồng nghĩa với chạy nhanh hoặc không có lỗi

Một thao tác idempotent vẫn có thể chạy lâu, timeout hoặc thất bại. Điểm quan trọng là khi được thực hiện lại, nó không tạo thêm kết quả ngoài ý muốn.

Ví dụ, đặt trạng thái đơn hàng thành PAID nhiều lần có thể idempotent nếu thao tác luôn đặt cùng giá trị. Nhưng cộng số dư tài khoản thêm 100 mỗi lần không idempotent nếu không có khóa giao dịch để chống ghi trùng.

## 3. At-least-once và giới hạn của exactly-once

Trong hệ thống phân tán, worker có thể hoàn thành công việc nhưng mất kết nối trước khi queue nhận acknowledgement. Queue không biết công việc đã xong nên có thể giao lại message. Vì vậy, nhiều hệ thống queue sử dụng semantics **at-least-once**: message được giao một hoặc nhiều lần cho đến khi được xác nhận hoặc hết chính sách retry.

Không nên giả định một message chỉ được xử lý đúng một lần. Thay vào đó, thiết kế consumer idempotent.

### Cửa sổ lỗi giữa commit và acknowledgement

~~~mermaid
sequenceDiagram
    participant Q as Queue
    participant W as Worker
    participant DB as Database
    Q->>W: Giao message M
    W->>DB: Ghi kết quả nghiệp vụ
    DB-->>W: Commit thành công
    Note over W: Instance bị thu hồi trước acknowledgement
    Q->>W: Lease hết hạn, giao lại message M
    W->>DB: Kiểm tra idempotency key M
    DB-->>W: Đã xử lý trước đó
    W-->>Q: Acknowledge message
~~~

Nếu consumer ghi kết quả trước rồi mới ack, message có thể được giao lại. Idempotency/deduplication giúp lần sau nhận biết kết quả đã commit và không lặp side effect.

Nếu ack trước khi ghi kết quả bền vững, worker có thể bị dừng sau ack và message không được giao lại, dẫn đến mất công việc. Vì vậy, thứ tự phổ biến là commit kết quả và trạng thái xử lý trước, sau đó mới acknowledge.

### Exactly-once cần được hiểu theo phạm vi

Một số hệ thống cung cấp exactly-once semantics trong phạm vi transaction hoặc nền tảng nhất định. Nhưng khi một tác vụ tương tác với nhiều hệ thống độc lập như queue, database, object storage và API bên thứ ba, rất khó bảo đảm một transaction toàn cục duy nhất.

Trong thực tế, thường xây dựng **effectively-once business outcome** bằng cách kết hợp:

- Idempotency key ổn định.
- Unique constraint hoặc deduplication record.
- Transaction trong phạm vi database.
- Outbox/inbox cho event.
- Idempotency API của dịch vụ ngoài nếu có.
- Reconciliation hoặc compensation khi side effect không thể giao dịch cùng nhau.

## 4. Xác định ranh giới tác vụ và đơn vị idempotent

Trước khi chọn key hoặc viết retry, cần xác định một thao tác logic là gì.

Ví dụ một job xử lý video có các bước:

1. Tải source object.
2. Kiểm tra định dạng và metadata.
3. Tạo thumbnail.
4. Transcode video.
5. Lưu output.
6. Ghi metadata vào database.
7. Phát event hoàn tất.

Có thể chia job thành các step độc lập có đầu vào/đầu ra xác định. Mỗi step cần biết:

- Job ID và step ID.
- Input object/version/checksum.
- Phiên bản thuật toán hoặc image thực thi.
- Idempotency key.
- Trạng thái pending/running/completed/failed.
- Output location và checksum.
- Checkpoint hoặc cursor cần để tiếp tục.

Nếu toàn bộ job được xem là một thao tác duy nhất, retry có thể phải chạy lại mọi bước. Nếu chia nhỏ hợp lý, worker mới có thể bỏ qua step đã commit và tiếp tục từ step chưa hoàn tất.

### Chọn kích thước đơn vị công việc

Đơn vị quá lớn làm mất nhiều tiến độ khi bị thu hồi. Đơn vị quá nhỏ tạo nhiều checkpoint, transaction và metadata overhead.

Ví dụ:

- Xử lý 10 triệu record: chia thành partition hoặc batch có ID ổn định.
- Render video: chia theo segment hoặc stage.
- ETL: checkpoint theo partition và watermark.
- ML training: checkpoint theo epoch hoặc số bước optimizer.
- Crawl dữ liệu: checkpoint theo cursor/page token.
- Batch image: một object hoặc nhóm object có manifest riêng.

Hãy chọn ranh giới dựa trên thời gian xử lý, chi phí làm lại, khả năng song song và yêu cầu nhất quán.

## 5. Thiết kế idempotency key ổn định

Idempotency key là định danh duy nhất cho một thao tác logic. Key phải giữ nguyên qua các lần retry của cùng thao tác.

### Key nên dựa trên dữ liệu nghiệp vụ ổn định

Ví dụ:

- Payment: payment intent ID hoặc order ID + loại giao dịch.
- Invoice: order ID + invoice version.
- File processing: object key + object version + transformation version.
- Batch: dataset ID + partition ID + pipeline version.
- Message consumer: producer event ID.
- Scheduled job: job definition ID + scheduled execution timestamp.

Không tạo UUID ngẫu nhiên mới cho mỗi lần retry. Nếu mỗi attempt có key khác nhau, hệ thống không nhận ra đó là cùng một thao tác.

Ví dụ công thức key:

~~~text
idempotency_key =
  tenant_id + ":" +
  job_id + ":" +
  step_name + ":" +
  input_version
~~~

Cần canonicalize các thành phần trước khi ghép hoặc hash để tránh cùng dữ liệu tạo ra key khác nhau do thứ tự field, encoding hoặc khoảng trắng.

### Phạm vi và thời hạn key

Cần xác định:

- Key duy nhất trong toàn hệ thống hay theo tenant.
- Key áp dụng cho một API call, một job hay một step.
- Khi nào key hết hạn.
- Kết quả được lưu bao lâu để bao phủ thời gian retry tối đa.
- Cùng key nhưng payload khác nhau sẽ bị xử lý thế nào.
- Có cần lưu trạng thái IN_PROGRESS để ngăn hai worker cùng chạy không.

Nếu key hết hạn quá sớm, một message cũ được giao lại có thể tạo side effect lần nữa. Nếu giữ mãi, bảng dedup có thể tăng không giới hạn. Chọn retention dựa trên queue retention, retry horizon, business audit và quy định dữ liệu.

### Payload hash

Có thể lưu hash của payload chuẩn hóa cùng key. Nếu cùng key xuất hiện với payload khác, trả lỗi conflict thay vì âm thầm dùng kết quả cũ hoặc thực thi một thao tác khác.

## 6. Lưu idempotency record bằng database

Một bảng idempotency record có thể chứa:

- Key và tenant/scope.
- Loại operation.
- Payload hash.
- Trạng thái: IN_PROGRESS, COMPLETED hoặc FAILED_RETRYABLE.
- Kết quả hoặc reference đến kết quả.
- Thời gian tạo/cập nhật và thời điểm hết hạn.
- Lease owner hoặc fencing generation nếu cần.

Ví dụ schema SQL minh họa:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id       VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    operation_type  VARCHAR(80)  NOT NULL,
    payload_hash    VARCHAR(128) NOT NULL,
    status          VARCHAR(30)  NOT NULL,
    result_ref      VARCHAR(500),
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP,
    PRIMARY KEY (tenant_id, idempotency_key)
);
~~~

Khóa chính bảo đảm hai worker không thể cùng tạo hai record cho cùng tenant/key. Nhưng chỉ có unique constraint chưa đủ; logic xử lý conflict và transaction cũng cần đúng.

### Luồng xử lý khái niệm

1. Nhận job và xác định key.
2. Bắt đầu transaction.
3. Tạo idempotency record nếu chưa tồn tại.
4. Nếu key đã COMPLETED, trả kết quả đã lưu.
5. Nếu key đang IN_PROGRESS và lease còn hiệu lực, không chạy song song.
6. Nếu lease hết hạn, worker mới có thể tiếp quản theo fencing/version.
7. Thực hiện thay đổi nghiệp vụ trong transaction phù hợp.
8. Ghi kết quả và chuyển record sang COMPLETED cùng transaction.
9. Commit.
10. Ack message sau commit.

Cần xử lý trường hợp hai worker đến đồng thời bằng unique constraint, row lock, compare-and-swap hoặc cơ chế tương đương của database.

### Không giữ transaction mở trong suốt một job dài

Một job có thể chạy nhiều phút hoặc hàng giờ. Giữ transaction database mở trong toàn bộ thời gian có thể gây lock dài, giữ connection và làm tăng contention. Thay vào đó, chia job thành các bước ngắn, mỗi bước commit kết quả và checkpoint bền vững.

## 7. Idempotency cho side effect bên ngoài database

Không phải mọi side effect đều có thể nằm trong transaction database. Ví dụ:

- Gửi email.
- Gọi cổng thanh toán.
- Gửi SMS.
- Tạo resource ở cloud API.
- Ghi object vào storage.
- Phát message sang broker khác.

Nếu worker gọi API bên ngoài thành công nhưng bị dừng trước khi lưu kết quả, retry có thể gọi lại và tạo tác động trùng.

### Dùng idempotency key của dịch vụ đích

Nếu API bên ngoài hỗ trợ idempotency key, gửi cùng key cho mọi lần retry của cùng thao tác. Dịch vụ đích có thể trả lại kết quả đã ghi nhận thay vì thực hiện lại.

Key cần ổn định xuyên qua mọi attempt và có phạm vi/retention tương thích với dịch vụ đích.

### Dùng trạng thái pending và reconciliation

Nếu dịch vụ ngoài không hỗ trợ idempotency:

1. Ghi một operation record trước khi gọi dịch vụ.
2. Gửi request với một reference nghiệp vụ có thể truy vấn.
3. Nếu timeout, không kết luận thao tác thất bại.
4. Truy vấn trạng thái từ dịch vụ đích bằng reference.
5. Chỉ retry khi xác định thao tác chưa xảy ra hoặc retry là an toàn.
6. Nếu không thể xác định, đưa vào reconciliation/manual review theo chính sách.

Timeout không đồng nghĩa request chưa được thực hiện. Đây là nguyên nhân phổ biến tạo giao dịch trùng.

### Saga và compensation

Một quy trình nhiều hệ thống có thể cần compensation. Ví dụ, đặt hàng gồm reserve inventory, charge payment và tạo shipment. Nếu charge thành công nhưng shipment thất bại, quy trình có thể cần hoàn tiền hoặc release inventory.

Compensation là một thao tác nghiệp vụ mới để đưa hệ thống về trạng thái chấp nhận được; nó không phải rollback vật lý của transaction đã commit. Compensation cũng cần idempotency vì chính nó có thể bị retry.

## 8. Outbox và inbox pattern

### Transactional outbox

Giả sử API ghi đơn hàng vào database rồi phát event OrderCreated lên queue. Nếu database commit thành công nhưng publish thất bại, worker khác không biết đơn hàng mới. Nếu publish thành công nhưng database rollback, event lại mô tả một đơn hàng không tồn tại.

Outbox ghi thay đổi nghiệp vụ và event cần phát trong cùng transaction:

~~~sql
BEGIN;

INSERT INTO orders (order_id, customer_id, status)
VALUES ('ord-1042', 'cust-81', 'CREATED');

INSERT INTO outbox_events (event_id, aggregate_id, event_type, payload)
VALUES ('evt-1042', 'ord-1042', 'OrderCreated', '{...}');

COMMIT;
~~~

Một publisher riêng đọc outbox, gửi event và đánh dấu đã publish. Publisher có thể bị dừng sau khi gửi nhưng trước khi cập nhật trạng thái, vì vậy có thể gửi event lại. Consumer cần inbox/dedup theo event ID.

### Inbox/dedup ở consumer

Consumer lưu event ID đã xử lý trong cùng transaction với thay đổi nghiệp vụ:

~~~sql
BEGIN;

INSERT INTO inbox_events (consumer_name, event_id, processed_at)
VALUES ('invoice-worker', 'evt-1042', CURRENT_TIMESTAMP)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Chỉ thực hiện thay đổi nghiệp vụ nếu event vừa được ghi mới.
-- Triển khai thực tế cần kiểm tra số dòng được insert trong transaction.

COMMIT;
~~~

Nếu event đã có trong inbox, consumer bỏ qua side effect đã hoàn tất. Inbox retention phải dài đủ để bao phủ retry/replay; nếu cần replay có chủ đích, phải có namespace/version hoặc cơ chế reprocessing riêng.

## 9. Checkpoint để tiếp tục thay vì chạy lại từ đầu

Checkpoint là bản ghi tiến độ bền vững của job. Worker mới đọc checkpoint để biết phần nào đã hoàn tất.

### Checkpoint nên lưu gì?

Tùy workload, có thể lưu:

- Job ID, step ID và input version.
- Partition, offset, cursor hoặc số record đã commit.
- Output object/key và checksum.
- Phiên bản code/model/algorithm.
- Trạng thái bước và timestamp.
- Fencing generation hoặc worker lease.
- Thống kê số record thành công/thất bại.
- Thông tin cần để xác minh output trước khi tiếp tục.

Không lưu secret, access token hoặc dữ liệu cá nhân không cần thiết trong checkpoint.

### Commit output và checkpoint theo thứ tự an toàn

Một lỗi phổ biến là cập nhật checkpoint trước khi output được ghi bền vững. Nếu instance bị dừng sau checkpoint, lần sau worker có thể bỏ qua phần output chưa tồn tại.

Ngược lại, nếu output đã ghi nhưng checkpoint chưa cập nhật, worker có thể tạo output lần nữa. Cần dùng một trong các cách:

- Ghi output theo key deterministic và thao tác overwrite an toàn.
- Ghi object bất biến theo attempt/step rồi commit manifest trỏ đến output đã xác minh.
- Ghi output và checkpoint trong cùng transaction nếu cùng một database.
- Dùng trạng thái PREPARED/COMMITTED để hoàn tất hoặc dọn output chưa commit.
- Dùng checksum và version để xác minh output trước khi tiếp tục.

### Ví dụ manifest cho batch

~~~json
{
  "job_id": "etl-2026-11-22",
  "input_version": "dataset-v17",
  "pipeline_version": "3.2.1",
  "completed_partitions": [0, 1, 2, 3],
  "outputs": {
    "0": "s3://result/etl-2026-11-22/part-000",
    "1": "s3://result/etl-2026-11-22/part-001"
  },
  "status": "RUNNING"
}
~~~

Đây là manifest minh họa. Trong production, cập nhật manifest cần có conditional write/version check để hai worker không ghi đè tiến độ của nhau. Chỉ đánh dấu partition hoàn tất sau khi output đã được ghi và kiểm tra thành công.

## 10. Thiết kế job có thể chia nhỏ và tiếp tục

Interruptible compute phù hợp với workload có thể chia thành đơn vị độc lập hoặc checkpoint thường xuyên.

### Batch processing

Chia dataset thành partition có ID ổn định. Mỗi partition được xử lý độc lập, output có key deterministic. Worker bị dừng thì partition chưa commit có thể được giao lại.

### MapReduce và fan-out/fan-in

Các map task xử lý từng phần dữ liệu và ghi output độc lập. Reduce chỉ đọc các output đã commit trong manifest. Không dùng tên file ngẫu nhiên làm bằng chứng hoàn tất; dùng manifest, checksum và trạng thái task.

### Render/transcode

Chia media thành segment hoặc stage. Mỗi segment có input version và output key. Nếu một segment đã hoàn tất, worker khác có thể xác minh checksum và bỏ qua.

### Machine learning

Lưu checkpoint model, optimizer state, learning rate scheduler, random seed và dataset position theo phiên bản. Khi tiếp tục, phải biết checkpoint tương thích với code, framework và hardware hiện tại hay không. Không chỉ lưu trọng số model nếu optimizer state cần thiết để tiếp tục đúng quy trình.

### Crawl hoặc pagination

Lưu cursor hoặc page token sau khi toàn bộ dữ liệu của trang đã được ghi bền vững. Nếu cursor cập nhật trước khi ghi record, dữ liệu có thể bị bỏ qua. Nếu record ghi trước nhưng cursor chưa cập nhật, trang có thể chạy lại; consumer cần dedup theo record/business key.

## 11. Xử lý interruption notice

Một số dịch vụ phát tín hiệu hoặc sự kiện trước khi thu hồi instance. Cơ chế có thể là metadata/event endpoint, notification, lifecycle hook, signal hệ điều hành hoặc event từ orchestrator. Thời gian cảnh báo và điều kiện phát khác nhau; không được giả định mọi lần thu hồi đều có cảnh báo đủ dài.

### Mục tiêu của interruption handler

Khi nhận tín hiệu:

1. Đánh dấu worker đang draining.
2. Ngừng nhận job mới.
3. Ngừng lấy message hoặc ngừng gia hạn lease nếu không thể hoàn tất.
4. Hoàn tất phần công việc nhỏ có thể commit an toàn.
5. Ghi checkpoint bền vững.
6. Flush output và metadata cần thiết.
7. Trả lại hoặc cho hết hạn lease của công việc chưa hoàn tất.
8. Đóng kết nối và thoát trước deadline nếu còn thời gian.

Interruption handler phải chạy nhanh và có giới hạn thời gian. Không thực hiện backup toàn bộ volume, upload dữ liệu lớn hoặc transaction dài trong một cửa sổ cảnh báo ngắn.

### Graceful shutdown không phải bảo đảm

Instance có thể bị terminate đột ngột, kernel panic hoặc mất network trước khi handler hoàn tất. Do đó:

- Checkpoint định kỳ trong lúc job chạy.
- Commit từng batch nhỏ.
- Lưu tiến độ ra storage độc lập.
- Giữ operation idempotent.
- Dùng lease/visibility timeout để job có thể được giao lại.
- Kiểm thử cả trường hợp không có interruption notice.

### Pseudocode interruption handler

~~~python
def on_interruption():
    worker_state.mark_draining()
    queue.stop_receiving_new_messages()

    for task in active_tasks():
        if task.can_finish_within_shutdown_budget():
            task.finish_current_atomic_step()
        else:
            task.persist_checkpoint()
            task.release_or_allow_lease_expiry()

    flush_telemetry_with_timeout()
    close_connections()
~~~

Đây là pseudocode mô tả thứ tự xử lý. Hàm checkpoint phải ghi dữ liệu bền vững và có conditional update/fencing phù hợp; không được chỉ ghi biến trong RAM hoặc file ephemeral rồi coi là đã lưu.

## 12. Queue lease, visibility timeout và worker ownership

Queue thường giao message cho worker trong một khoảng thời gian. Cơ chế có thể được gọi là visibility timeout, message lock hoặc lease tùy nền tảng.

### Lease quá ngắn

Nếu thời gian xử lý bình thường dài hơn lease và worker không gia hạn, queue có thể giao cùng message cho worker thứ hai trong khi worker đầu vẫn chạy. Hai worker có thể tạo side effect đồng thời.

### Lease quá dài

Nếu worker chết, message phải chờ lâu mới được giao lại. RTO của job tăng và queue bị giữ message không cần thiết.

### Cách thiết kế

- Chọn lease ban đầu dựa trên thời gian xử lý thực tế và giới hạn dịch vụ.
- Gia hạn lease khi worker vẫn tiến triển và còn quyền sở hữu.
- Dừng xử lý nếu không gia hạn được lease hoặc quyền đã hết.
- Ack chỉ sau khi kết quả và checkpoint đã commit.
- Dùng idempotency để xử lý redelivery.
- Dùng fencing token/generation nếu worker cũ có thể tiếp tục chạy sau khi lease đã chuyển.

### Fencing token

Mỗi lần một worker nhận quyền xử lý job, hệ thống cấp generation tăng dần. Storage chỉ chấp nhận ghi từ generation mới nhất. Nếu worker cũ thức dậy sau khi lease hết hạn, token cũ bị từ chối.

Ví dụ:

- Worker A nhận lease generation 7.
- A bị pause lâu hơn lease.
- Worker B nhận lease mới generation 8.
- B ghi checkpoint với generation 8.
- A tiếp tục chạy và cố ghi generation 7.
- Storage từ chối ghi của A vì generation đã là 8.

Fencing cần được thực thi ở nơi lưu trạng thái hoặc hệ thống nhận side effect. Chỉ kiểm tra lease ở worker không đủ nếu worker cũ vẫn có thể gửi request sau khi mất quyền.

## 13. Retry có kiểm soát và phân loại lỗi

Không phải mọi lỗi đều nên retry. Retry lỗi vĩnh viễn có thể lãng phí capacity và gây tải lên dependency.

### Phân loại lỗi

| Loại lỗi | Ví dụ | Hành động |
|---|---|---|
| Transient | Timeout mạng, throttling tạm thời, service unavailable | Retry với backoff và jitter |
| Interruption/preemption | Instance nhận tín hiệu thu hồi | Checkpoint, nhả lease hoặc để queue giao lại |
| Permanent input | File sai định dạng, schema không hợp lệ | Đánh dấu failed/quarantine, không retry vô hạn |
| Business rejection | Đơn hàng không đủ điều kiện | Ghi kết quả nghiệp vụ và kết thúc |
| Dependency configuration | Sai credential, endpoint hoặc permission | Dừng retry nhanh, cảnh báo và sửa cấu hình |
| Unknown outcome | Request bên ngoài timeout nhưng chưa biết đã thực hiện chưa | Tra cứu bằng reference/idempotency key trước khi retry |

### Exponential backoff và jitter

Retry theo cấp số nhân giúp giảm áp lực khi dependency đang lỗi. Jitter ngẫu nhiên tránh nhiều worker retry đồng loạt.

Ví dụ công thức:

~~~text
delay = random(0, min(max_delay, base_delay * 2^attempt))
~~~

Cần có:

- Số lần retry tối đa hoặc deadline tổng.
- Timeout cho từng attempt.
- Backoff có jitter.
- Giới hạn concurrency retry.
- Dead-letter queue hoặc trạng thái cần điều tra.
- Metric retry count và tuổi job.
- Idempotency ở consumer và side effect.

Không đặt retry vô hạn cho payment, email hoặc API ngoài mà không có reconciliation. Nếu không biết request đã thành công hay chưa, tra cứu trạng thái trước khi gửi lại.

## 14. Ví dụ triển khai worker idempotent

Một worker xử lý job tạo thumbnail cho object. Job chứa object key, object version và transformation version. Output được ghi vào key xác định từ các thành phần đó.

### Tạo idempotency key

~~~python
def make_key(tenant_id, job_id, input_version, transform_version):
    return (
        f"{tenant_id}:{job_id}:thumbnail:"
        f"{input_version}:{transform_version}"
    )
~~~

Mọi retry của cùng job và cùng input/transform version phải dùng cùng key. Nếu thuật toán thay đổi, version mới tạo một thao tác logic mới.

### Luồng xử lý khái niệm

~~~python
def process_thumbnail(job):
    key = make_key(
        job.tenant_id,
        job.job_id,
        job.input_version,
        job.transform_version,
    )

    record = idempotency_store.claim_or_read(key, job.payload_hash)

    if record.status == "COMPLETED":
        return record.result_ref

    if not record.lease_is_owned_by_current_worker:
        raise RetryLater()

    source = object_store.get(
        job.input_key,
        version=job.input_version,
    )

    thumbnail = transform(source, job.transform_version)

    output_key = f"thumbnails/{key}.webp"
    checksum = object_store.put_if_absent_or_verify(
        output_key,
        thumbnail,
    )

    result = {
        "output_key": output_key,
        "checksum": checksum,
    }

    idempotency_store.commit_completed(
        key=key,
        result=result,
        fencing_token=record.fencing_token,
    )

    return result
~~~

Đây là pseudocode. Trong triển khai thực tế, claim phải atomic; commit phải kiểm tra fencing token; object write cần conditional semantics hoặc verify checksum; record COMPLETED phải chỉ được ghi sau khi output bền vững.

### Tại sao output key deterministic?

Nếu mỗi attempt tạo một tên file ngẫu nhiên, retry có thể tạo nhiều thumbnail cho cùng input. Key deterministic giúp worker biết output thuộc thao tác logic nào. Nếu object store không hỗ trợ create-if-absent hoặc conditional write như mong muốn, cần dùng version/manifest và quy trình commit riêng.

## 15. Ví dụ SQL: claim và hoàn tất job an toàn

Một bảng job có thể lưu trạng thái, lease và generation:

~~~sql
CREATE TABLE job_steps (
    job_id          VARCHAR(120) NOT NULL,
    step_name       VARCHAR(100) NOT NULL,
    input_version   VARCHAR(120) NOT NULL,
    status          VARCHAR(30) NOT NULL,
    lease_owner     VARCHAR(120),
    lease_until     TIMESTAMP,
    fencing_token   BIGINT NOT NULL DEFAULT 0,
    checkpoint_ref  VARCHAR(500),
    result_ref      VARCHAR(500),
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (job_id, step_name, input_version)
);
~~~

Worker cần claim job bằng thao tác atomic, ví dụ transaction với row lock hoặc update có điều kiện:

~~~sql
UPDATE job_steps
SET lease_owner = :worker_id,
    lease_until = :new_lease_until,
    fencing_token = fencing_token + 1,
    status = 'RUNNING',
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = :job_id
  AND step_name = :step_name
  AND input_version = :input_version
  AND (
      status IN ('PENDING', 'RETRYABLE')
      OR lease_until < CURRENT_TIMESTAMP
  );
~~~

Trong thực tế, worker phải kiểm tra số dòng được cập nhật. Nếu không có dòng nào, worker chưa claim được. Sau khi claim, cần đọc generation mới và sử dụng nó cho mọi checkpoint/commit.

Cập nhật checkpoint phải kiểm tra đúng owner/generation:

~~~sql
UPDATE job_steps
SET checkpoint_ref = :checkpoint_ref,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = :job_id
  AND step_name = :step_name
  AND input_version = :input_version
  AND lease_owner = :worker_id
  AND fencing_token = :fencing_token
  AND status = 'RUNNING';
~~~

Nếu số dòng cập nhật bằng 0, worker đã mất quyền hoặc trạng thái thay đổi; nó phải dừng side effect tiếp theo và không ghi đè tiến độ mới.

Cú pháp SQL locking, timestamp và transaction isolation có thể khác giữa các hệ quản trị. Cần triển khai theo database thực tế và kiểm tra race condition bằng test đồng thời.

## 16. Tính toán chu kỳ checkpoint

Checkpoint quá thưa làm tăng công việc phải chạy lại; checkpoint quá dày tạo overhead ghi và tải lên storage/database.

Giả sử:

- Thời gian giữa hai checkpoint là C.
- Chi phí tạo checkpoint là S.
- Tỷ lệ interruption trên một đơn vị thời gian là λ.
- Công việc chạy liên tục với tốc độ ổn định.

Một mô hình gần đúng cho overhead là:

- Overhead checkpoint tỷ lệ với S/C.
- Công việc kỳ vọng mất do interruption tỷ lệ với λ × C/2.

Có thể dùng mô hình đơn giản để tìm điểm bắt đầu cho thử nghiệm; không xem đây là công thức tối ưu chính xác cho mọi workload. Thời gian interruption thực tế có thể không phân bố đều, checkpoint có thể có chi phí biến thiên và job có thể có nhiều giai đoạn.

Quy tắc thực tế:

- Với job dài, checkpoint tại ranh giới batch/partition có thể tái tạo.
- Với ML training, cân nhắc checkpoint theo số step hoặc thời gian.
- Với xử lý file, checkpoint sau mỗi object hoặc segment đã commit.
- Với transaction ngắn, commit từng transaction thay vì tạo checkpoint riêng quá dày.
- Đo thời gian checkpoint, thời gian restore và lượng công việc phải chạy lại.
- Kiểm tra checkpoint không làm tăng latency của workload quan trọng khác.

## 17. Chọn workload phù hợp với compute có thể bị thu hồi

Không phải workload nào cũng nên chạy trên interruptible compute.

### Phù hợp

- Batch analytics có thể chia partition.
- Rendering, transcoding và xử lý ảnh theo job.
- CI build/test có artifact và cache tái tạo được.
- Simulation hoặc Monte Carlo có thể chạy nhiều task độc lập.
- Training ML có checkpoint đầy đủ.
- Worker queue xử lý message idempotent.
- Data processing có cursor/checkpoint và output commit rõ.

### Cần cân nhắc hoặc tránh nếu chưa có thiết kế bổ sung

- Database primary hoặc hệ thống giữ state duy nhất trên local disk.
- Job có side effect không thể kiểm tra hoặc bù trừ.
- Tác vụ đồng bộ có deadline rất ngắn và không có capacity thay thế.
- License hoặc phần mềm không cho phép instance bị thay đổi thường xuyên.
- Workload giữ kết nối dài hạn mà không có reconnect/resume.
- Tác vụ không thể checkpoint và chi phí chạy lại quá cao.
- Dịch vụ cần capacity ổn định nhưng không có fallback sang compute on-demand.

### Kiến trúc kết hợp

Một pattern phổ biến là giữ control plane và stateful dependency trên capacity ổn định, còn worker thực thi các job độc lập trên interruptible capacity. Queue và database điều phối công việc; worker có thể bị thu hồi mà không làm mất source of truth.

## 18. Kiểm thử idempotency và interruption

Không thể xác nhận thiết kế idempotent chỉ bằng việc chạy job thành công một lần. Cần cố ý tạo interruption ở các điểm dễ phát sinh side effect trùng.

### Fault injection points

- Trước khi tạo idempotency record.
- Sau khi claim lease nhưng trước khi xử lý.
- Sau khi đọc input nhưng trước output.
- Sau khi ghi output nhưng trước checkpoint.
- Sau khi ghi checkpoint nhưng trước khi ack.
- Sau khi database commit nhưng trước response.
- Sau khi gọi API bên ngoài nhưng trước khi lưu kết quả.
- Khi lease hết hạn nhưng worker cũ vẫn chạy.
- Khi hai worker nhận cùng job gần như đồng thời.

### Ma trận kiểm thử

| Kịch bản | Cách thử | Tiêu chí đạt |
|---|---|---|
| Retry cùng key | Gửi lại cùng operation nhiều lần | Chỉ có một kết quả nghiệp vụ |
| Cùng key, payload khác | Thay payload nhưng giữ key | Bị từ chối hoặc đưa vào conflict, không âm thầm dùng sai |
| Worker chết trước commit | Kill process trước transaction commit | Job được giao lại và xử lý bình thường |
| Worker chết sau commit trước ack | Dừng process sau commit | Redelivery nhận ra COMPLETED và không lặp side effect |
| Hai worker đồng thời | Giao cùng job cho hai worker | Chỉ một worker có lease hợp lệ hoặc commit được |
| Lease hết hạn | Làm worker A pause rồi cho B tiếp quản | Fencing từ chối ghi của A |
| Output đã ghi, checkpoint thiếu | Dừng giữa hai thao tác | Retry xác minh output và hoàn tất manifest an toàn |
| Checkpoint cũ | Khôi phục từ checkpoint trước | Chỉ chạy lại phần chưa commit, không bỏ dữ liệu |
| Interruption notice | Gửi tín hiệu dừng trong lúc job chạy | Worker drain, checkpoint và nhả lease trong budget |
| Không có notice | Terminate đột ngột | Queue/checkpoint phục hồi mà không cần shutdown hook |
| Dependency timeout | Làm API ngoài timeout sau khi nhận request | Tra cứu trạng thái hoặc retry bằng cùng idempotency key |
| DLQ | Tạo lỗi permanent | Message được cách ly, có thể điều tra/replay có kiểm soát |

### Tiêu chí nghiệm thu

- Một logical operation chỉ tạo một business effect trong phạm vi cam kết.
- Job có thể chạy lại sau interruption ở bất kỳ điểm test nào.
- Không có checkpoint trỏ đến output chưa commit.
- Worker mất lease không thể ghi đè trạng thái mới.
- Retry có giới hạn và không tạo retry storm.
- Message poison không chặn queue vô hạn.
- RPO của checkpoint và thời gian khôi phục đáp ứng mục tiêu.
- Chi phí làm lại sau interruption nằm trong mức chấp nhận.

## 19. Quan sát và vận hành

Để biết interruptible workload có an toàn và hiệu quả, cần quan sát cả vòng đời job lẫn interruption.

Metric hữu ích:

- Số interruption theo instance type, capacity pool và region.
- Thời gian cảnh báo trước khi thu hồi nếu nền tảng cung cấp.
- Số job bị retry, redelivery và số attempt trung bình.
- Tỷ lệ job hoàn tất ở attempt đầu và sau retry.
- Checkpoint frequency, duration, size và failure rate.
- Thời gian resume từ checkpoint.
- Công việc phải chạy lại sau mỗi interruption.
- Idempotency hit, duplicate suppressed và payload conflict.
- Lease expiry, fencing rejection và worker overlap.
- Queue depth, oldest message age và DLQ count.
- Tỷ lệ side effect conflict hoặc reconciliation cần xử lý thủ công.
- Cost per successful job và wasted compute time.

Log nên ghi job ID, step ID, attempt, input version, idempotency key đã hash hoặc mã tham chiếu an toàn, checkpoint version và worker ID. Không ghi token, session cookie, secret hoặc dữ liệu nhạy cảm vào log.

Dashboard nên phân biệt:
- Job thất bại vĩnh viễn.
- Job đang retry.
- Job bị interruption nhưng sẽ tiếp tục.
- Job đã hoàn tất nhưng message chưa ack.
- Job bị chặn do lease hoặc fencing.
- Job cần reconciliation vì outcome bên ngoài chưa xác định.

### Runbook khi interruption rate tăng

1. Xác định capacity pool, region và loại instance bị ảnh hưởng.
2. Kiểm tra tỷ lệ interruption và thời gian notice quan sát được.
3. Xem queue age, retry rate, checkpoint restore time và DLQ.
4. Xác minh worker mới có capacity thay thế.
5. Kiểm tra side effect duplicate, idempotency conflict và lease expiry.
6. Nếu cần, chuyển phần tải deadline-sensitive sang capacity ổn định.
7. Điều chỉnh batch size/checkpoint interval dựa trên dữ liệu đo.
8. Ghi lại chi phí làm lại và cập nhật lựa chọn capacity.

## 20. Những sai lầm thường gặp

**Tạo idempotency key mới cho mỗi lần retry.** Hệ thống không nhận ra các lần thử thuộc cùng thao tác. Key phải được tạo từ định danh nghiệp vụ ổn định và được lưu cùng job.

**Ack message trước khi ghi kết quả bền vững.** Worker bị dừng sau ack có thể làm mất job. Commit kết quả/checkpoint trước rồi ack.

**Ghi checkpoint trước khi output tồn tại.** Worker mới có thể bỏ qua phần output chưa được ghi. Commit output trước hoặc dùng manifest/transaction để phối hợp.

**Cho rằng queue at-least-once sẽ tự chống duplicate.** Queue có thể giao lại; consumer phải dedup và idempotent.

**Chỉ dùng distributed lock mà không có fencing.** Worker cũ có thể tiếp tục sau khi lease hết hạn. Hệ thống lưu state phải từ chối generation cũ.

**Retry mọi timeout của API thanh toán.** Request có thể đã được xử lý nhưng response bị mất. Tra cứu trạng thái hoặc dùng idempotency key của dịch vụ đích.

**Checkpoint quá thường xuyên.** Storage và database có thể trở thành bottleneck. Đo chi phí checkpoint và chọn ranh giới batch phù hợp.

**Chỉ xử lý interruption qua shutdown hook.** Instance có thể biến mất mà hook không chạy. Checkpoint định kỳ và idempotency là lớp bảo vệ chính.

**Dùng local ephemeral disk làm nơi giữ checkpoint duy nhất.** Khi instance bị thu hồi, checkpoint cũng mất. Lưu ở database/object storage hoặc dịch vụ bền vững.

**Không test hai worker chạy đồng thời.** Lease hết hạn hoặc redelivery có thể tạo overlap. Test claim atomic, fencing và commit conflict.

**Cho rằng exactly-once có thể đạt trên mọi hệ thống chỉ bằng queue.** Side effect qua nhiều dịch vụ cần idempotency, transaction/outbox và reconciliation theo từng ranh giới.

## 21. Checklist thiết kế tác vụ idempotent

### Định nghĩa công việc

- [ ] Job và từng step có ID ổn định.
- [ ] Input version và phiên bản thuật toán được xác định.
- [ ] Ranh giới batch/partition/checkpoint phù hợp.
- [ ] Source of truth nằm ngoài vòng đời instance.
- [ ] Local disk chỉ giữ dữ liệu có thể tái tạo hoặc tạm thời.

### Idempotency và side effect

- [ ] Idempotency key không thay đổi qua các lần retry.
- [ ] Key có scope, retention và payload hash rõ ràng.
- [ ] Database có unique constraint hoặc cơ chế atomic claim.
- [ ] Result và trạng thái COMPLETED được commit cùng transaction khi có thể.
- [ ] External API dùng idempotency key hoặc reconciliation.
- [ ] Event publish dùng outbox; consumer có inbox/dedup.
- [ ] Compensation cũng idempotent.

### Checkpoint và worker lifecycle

- [ ] Checkpoint được ghi ở storage bền vững.
- [ ] Output được ghi/verify trước khi đánh dấu checkpoint hoàn tất.
- [ ] Lease có timeout và renewal phù hợp.
- [ ] Fencing token ngăn worker cũ ghi sau khi mất quyền.
- [ ] Interruption handler ngừng nhận job mới và checkpoint trong budget.
- [ ] Không phụ thuộc shutdown hook để bảo vệ dữ liệu.
- [ ] Ack chỉ sau commit.

### Retry và kiểm thử

- [ ] Lỗi transient/permanent/unknown outcome được phân loại.
- [ ] Retry có exponential backoff, jitter, timeout và giới hạn.
- [ ] Có DLQ và quy trình replay.
- [ ] Đã test retry cùng key, payload conflict và worker concurrency.
- [ ] Đã test interruption trước/sau output, checkpoint, commit và ack.
- [ ] Đã test trường hợp không có interruption notice.
- [ ] Có metric interruption, retry, checkpoint, duplicate và cost per successful job.

## 22. Tự kiểm tra

1. Vì sao worker chạy trên interruptible compute phải giả định một job có thể được giao nhiều lần?
2. Idempotency khác deduplication và checkpoint như thế nào?
3. Vì sao tạo UUID mới cho mỗi attempt làm mất tác dụng của idempotency?
4. Worker commit database thành công nhưng bị thu hồi trước acknowledgement. Lần giao lại cần làm gì?
5. Vì sao at-least-once delivery không tự bảo đảm exactly-once business effect?
6. Khi output đã ghi nhưng checkpoint chưa cập nhật, retry nên xác minh điều gì?
7. Lease và fencing token giải quyết hai vấn đề nào khác nhau?
8. Vì sao timeout khi gọi payment API không đủ để kết luận giao dịch thất bại?
9. Interruption handler nên làm gì trong thời gian cảnh báo ngắn, và những việc nào cần được thực hiện định kỳ trước đó?
10. Làm thế nào chọn checkpoint interval cân bằng giữa chi phí lưu tiến độ và lượng công việc phải chạy lại?
11. Những điểm nào cần fault injection để kiểm tra tác vụ idempotent?
12. Hãy thiết kế một worker xử lý batch có thể bị terminate đột ngột mà không tạo record trùng hoặc bỏ sót partition.

Thiết kế idempotent biến interruption từ một tình huống đặc biệt thành một điều kiện bình thường của vòng đời compute. Khi job có định danh ổn định, side effect được bảo vệ bằng transaction hoặc idempotency key, tiến độ được checkpoint bền vững, worker có lease/fencing và retry được giới hạn, instance có thể bị thu hồi rồi thay thế mà công việc vẫn tiếp tục an toàn.

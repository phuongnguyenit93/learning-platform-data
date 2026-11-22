# Theo dõi độ trễ đồng bộ và khả năng khôi phục

Trong nhiều hệ thống, Elasticsearch là nơi phục vụ tìm kiếm còn dữ liệu gốc nằm trong một hệ thống khác như PostgreSQL, MySQL hoặc một dịch vụ nghiệp vụ. Sau khi dữ liệu nguồn thay đổi, document trong Elasticsearch cần được cập nhật theo. Khoảng thời gian từ lúc thay đổi ở nguồn đến lúc người dùng tìm thấy phiên bản mới chính là **độ trễ đồng bộ** (synchronization lag).

Đồng bộ dữ liệu có thể bị chậm vì hàng đợi tăng, consumer ngừng hoạt động, Elasticsearch quá tải, bulk request có item thất bại, mapping không tương thích hoặc một lần deploy làm gián đoạn pipeline. Hệ thống vận hành tốt cần trả lời được ba câu hỏi: dữ liệu đang chậm bao lâu, đang mất hoặc mắc ở bước nào, và có thể tiếp tục từ đâu mà không bỏ sót hay ghi sai thứ tự.

Bài này đặt trong ngữ cảnh Spring Data Elasticsearch, với nguồn dữ liệu chính (source of truth) và Elasticsearch là một read model/projection phục vụ tìm kiếm. Nội dung đi từ kiến trúc đồng bộ, cách đo lag, checkpoint, xử lý Bulk API, retry và Dead Letter Queue (DLQ), đến replay, backfill, reconciliation và diễn tập khôi phục.

## 1. Xác định nguồn dữ liệu chuẩn và mục tiêu đồng bộ

Trước khi đo độ trễ, cần xác định hệ thống nào là nơi có thẩm quyền cuối cùng đối với dữ liệu.

Một kiến trúc phổ biến:

~~~text
Client
  |
  v
Application service
  |
  +----> Primary database (source of truth)
  |          |
  |          +----> Outbox / CDC log
  |                     |
  |                     v
  |                Sync worker
  |                     |
  |                     v
  +----------------> Elasticsearch
                         |
                         v
                    Search API
~~~

Trong mô hình này:

- Database lưu trạng thái nghiệp vụ chuẩn.
- Outbox hoặc CDC ghi nhận thay đổi cần đồng bộ.
- Worker đọc sự kiện theo thứ tự hoặc theo partition.
- Spring Data Elasticsearch hoặc Elasticsearch Java API Client ghi document.
- Search API đọc projection từ Elasticsearch.

Nếu Elasticsearch bị mất dữ liệu hoặc index cần xây dựng lại, ứng dụng có thể tái tạo projection từ nguồn chuẩn và lịch sử thay đổi còn được lưu.

Không nên coi một lần ghi Elasticsearch thành công là bằng chứng dữ liệu nghiệp vụ đã được commit ở nguồn. Nếu database và Elasticsearch cùng là nơi ghi chính mà không có cơ chế phối hợp, hệ thống có thể rơi vào trạng thái một nơi thành công, nơi còn lại thất bại.

## 2. Các kiểu đồng bộ thường gặp

### Ghi đồng bộ hai nơi

Ứng dụng ghi database rồi ghi Elasticsearch ngay trong cùng request:

~~~text
Request
  |
  +--> Database commit
  |
  +--> Elasticsearch index
  |
  +--> Response
~~~

Cách này dễ triển khai nhưng tạo dual-write problem. Database có thể commit thành công rồi Elasticsearch timeout; hoặc Elasticsearch ghi thành công nhưng database rollback. Một transaction thông thường không tự bao trùm cả hai hệ thống.

Nếu vẫn dùng cách này, cần có cơ chế sửa sai rõ ràng và không được báo thành công khi trạng thái hai nơi chưa đáp ứng hợp đồng nghiệp vụ.

### Transactional outbox

Ứng dụng ghi business data và một outbox event trong cùng transaction database:

~~~text
Database transaction
  |
  +--> Update business row
  |
  +--> Insert outbox event
  |
  +--> Commit
          |
          v
      Outbox relay
          |
          v
      Elasticsearch
~~~

Khi transaction commit, thay đổi nghiệp vụ và sự kiện đồng bộ cùng tồn tại. Worker có thể retry event nếu Elasticsearch tạm thời không sẵn sàng.

Outbox thường là lựa chọn dễ kiểm soát cho ứng dụng cần đồng bộ đáng tin cậy mà không muốn phụ thuộc trực tiếp vào log replication của database.

### Change Data Capture (CDC)

CDC đọc transaction log của database, ví dụ WAL hoặc binlog, rồi chuyển thay đổi tới pipeline đồng bộ. CDC phù hợp khi cần bắt thay đổi từ nhiều bảng hoặc giảm việc thêm logic publish event vào từng service.

Cần hiểu cách connector biểu diễn insert, update, delete, schema change, transaction boundary và offset. Không phải mọi event CDC đều tương đương một domain event hoàn chỉnh.

### Batch polling

Một worker định kỳ tìm bản ghi thay đổi sau watermark hoặc theo updatedAt rồi cập nhật Elasticsearch. Cách này đơn giản nhưng cần xử lý cẩn thận các bản ghi có cùng timestamp, thay đổi trong lúc batch chạy và khoảng trống do pagination.

Không dùng timestamp đơn lẻ làm checkpoint nếu độ phân giải thấp hoặc có nhiều bản ghi cùng thời điểm. Nên có khóa tie-breaker hoặc sequence tăng đơn điệu.

## 3. Phân biệt write latency và searchable latency

Một document có thể đã được Elasticsearch chấp nhận nhưng chưa xuất hiện trong search ngay lập tức do refresh.

Cần phân biệt:

- **Source-to-consumer lag:** thời gian từ lúc nguồn commit thay đổi đến khi worker nhận event.
- **Processing lag:** thời gian worker xử lý, transform và gửi request.
- **Index acknowledgement latency:** thời gian Elasticsearch trả lời thao tác ghi.
- **Search visibility lag:** thời gian từ source commit đến khi document thực sự nhìn thấy qua search.
- **End-to-end synchronization lag:** tổng thời gian từ thay đổi nguồn đến khi projection có thể được đọc theo hợp đồng sản phẩm.

Luồng thời gian:

~~~text
t0: Database commit
 |
 |  Queue / CDC delay
 v
t1: Worker receives event
 |
 |  Transform + bulk request
 v
t2: Elasticsearch acknowledges write
 |
 |  Wait for refresh
 v
t3: Document becomes searchable

End-to-end lag = t3 - t0
~~~

Nếu chỉ đo thời gian Bulk API trả về, dashboard có thể báo đồng bộ tốt trong khi người dùng vẫn chưa tìm thấy document mới.

Đối với một số use case, acknowledgement là đủ. Ví dụ ứng dụng cần xác nhận dữ liệu đã được lưu vào index nhưng không yêu cầu search ngay. Với use case read-after-write, cần đo searchable latency hoặc dùng chiến lược refresh phù hợp.

## 4. Định nghĩa lag bằng timestamp có ý nghĩa

Mỗi event nên mang timestamp nguồn, ví dụ:

- sourceCreatedAt: thời điểm event được tạo.
- sourceCommittedAt: thời điểm transaction nguồn commit, nếu có thể lấy chính xác.
- consumedAt: thời điểm worker nhận event.
- processingStartedAt: thời điểm bắt đầu xử lý.
- indexedAt: thời điểm Elasticsearch xác nhận thao tác.
- searchableAt: thời điểm document đã được quan sát trong search, nếu use case cần đo.

Các timestamp phải có timezone rõ ràng; nên lưu Instant/UTC. Đồng hồ giữa các máy cần được đồng bộ để phép trừ timestamp có ý nghĩa. Nếu clock skew lớn, lag có thể âm hoặc bị phóng đại.

Không dùng thời điểm worker xử lý làm nguồn thay cho thời điểm thay đổi gốc. Nếu event nằm trong queue 20 phút rồi mới được xử lý, timestamp worker không thể phản ánh 20 phút chờ đó.

Một event envelope có thể có cấu trúc:

~~~json
{
  "eventId": "evt-01JABC",
  "aggregateType": "Product",
  "aggregateId": "p-1001",
  "tenantId": "tenant-a",
  "eventType": "ProductUpdated",
  "sourceVersion": 42,
  "sourceOccurredAt": "2026-11-13T09:20:00Z",
  "partition": "product-07",
  "sequence": 918273,
  "payload": {
    "name": "Mechanical Keyboard",
    "status": "ACTIVE"
  }
}
~~~

Envelope nên giữ event ID ổn định qua các lần retry. Không tạo eventId mới mỗi lần worker gửi lại cùng một thay đổi, nếu không việc deduplicate sẽ khó hơn.

## 5. Đo end-to-end synchronization lag

Với event đã được index, lag cơ bản:

\[
lag = indexedAt - sourceOccurredAt
\]

Nếu yêu cầu là dữ liệu đã searchable:

\[
searchableLag = searchableAt - sourceOccurredAt
\]

Nên theo dõi phân vị thay vì chỉ nhìn average:

- p50: độ trễ điển hình.
- p95: độ trễ của phần lớn event.
- p99: phần đuôi chậm.
- max: event chậm nhất trong cửa sổ.
- oldest pending age: tuổi của event chưa xử lý lâu nhất.

Average có thể che giấu một nhóm nhỏ event bị mắc nhiều giờ. p95/p99 và oldest pending age thường hữu ích hơn để phát hiện backlog hoặc poison message.

Đo lag theo event hoặc theo partition. Nếu chỉ lấy timestamp event mới nhất đã xử lý, một partition đang mắc có thể bị che bởi partition khác vẫn chạy tốt.

## 6. Watermark và checkpoint

**Watermark** mô tả tiến độ đồng bộ đến một mốc nào đó. **Checkpoint** là vị trí có thể dùng để tiếp tục sau khi worker restart.

Tùy nguồn, checkpoint có thể là:

- Kafka partition offset.
- CDC log sequence number (LSN), binlog position hoặc connector offset.
- Outbox event ID/sequence.
- Database cursor theo cặp updatedAt và primary key.
- Một sequence tăng đơn điệu theo aggregate hoặc partition.

Checkpoint không nên chỉ là timestamp gần nhất nếu nhiều event có thể có cùng timestamp. Với polling theo thời gian, dùng cặp khóa:

~~~sql
WHERE
    updated_at > :lastUpdatedAt
    OR (
        updated_at = :lastUpdatedAt
        AND id > :lastId
    )
ORDER BY updated_at, id
LIMIT :batchSize
~~~

Sau mỗi batch, lưu lại cặp cuối cùng đã xử lý thành công. Khi restart, worker bắt đầu sau checkpoint này.

### Checkpoint phải phản ánh công việc đã hoàn tất

Không cập nhật checkpoint lên event mới nhất chỉ vì worker đã đọc được nó. Nếu event thứ 100 thất bại nhưng checkpoint đã nhảy lên 120, restart có thể bỏ qua event 100.

Với xử lý song song, các event có thể hoàn tất không theo thứ tự nhận. Checkpoint an toàn thường là **contiguous completed offset**: vị trí lớn nhất mà mọi event trước đó trong partition đã hoàn tất hoặc được đưa vào một trạng thái xử lý bền vững theo chính sách.

Nếu hệ thống cho phép bỏ qua event sau khi chuyển vào DLQ, cần lưu trạng thái và vị trí DLQ bền vững để replay sau. Không coi một lỗi chưa được ghi nhận là đã hoàn tất.

## 7. Phân biệt received, processed, indexed và searchable

Một dashboard đồng bộ nên có các trạng thái tiến độ riêng:

| Trạng thái | Ý nghĩa |
|---|---|
| Received | Worker đã nhận event |
| Validated | Payload và schema đã qua kiểm tra |
| Transformed | Đã tạo document/query |
| Submitted | Request đã được gửi |
| Indexed | Item được Elasticsearch xác nhận thành công |
| Searchable | Document đã xuất hiện trong search theo yêu cầu |
| Dead-lettered | Event được lưu vào DLQ để điều tra/replay |
| Reconciled | Đã xác nhận projection khớp nguồn |

Một event có thể được received nhưng chưa processed do queue; submitted nhưng item-level error; indexed nhưng chưa searchable; hoặc dead-lettered và đang chờ xử lý.

Tách trạng thái giúp xác định chính xác bottleneck. Ví dụ queue lag thấp nhưng searchable lag cao có thể liên quan refresh, trong khi consumer lag cao thường chỉ ra worker throughput hoặc downstream capacity.

## 8. Đếm chính xác kết quả của Bulk API

Bulk API xử lý nhiều index/create/update/delete action trong một request. HTTP request có thể thành công ở mức tổng thể nhưng một số item vẫn thất bại.

Do đó, không được coi một bulk request không ném exception là toàn bộ item đã được ghi thành công.

Một response có thể có:

- errors: cho biết có item lỗi hay không.
- items: kết quả riêng cho từng action.
- status: HTTP status của từng item.
- error: loại lỗi và lý do.
- _id, _index và version metadata.

Ví dụ response rút gọn:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_id": "p-1001",
        "status": 201
      }
    },
    {
      "index": {
        "_id": "p-1002",
        "status": 429,
        "error": {
          "type": "es_rejected_execution_exception",
          "reason": "rejected execution"
        }
      }
    },
    {
      "index": {
        "_id": "p-1003",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field"
        }
      }
    }
  ]
}
~~~

Trong ví dụ, p-1001 thành công, p-1002 có thể retry sau backoff, còn p-1003 cần sửa payload hoặc mapping. Nếu đánh dấu cả batch thành công, hai event lỗi sẽ bị mất khỏi luồng khôi phục.

## 9. Xử lý kết quả từng item

Worker cần ánh xạ mỗi bulk item về event nguồn tương ứng. Có thể giữ danh sách theo đúng thứ tự request:

~~~text
events[0] <-> bulkItems[0]
events[1] <-> bulkItems[1]
events[2] <-> bulkItems[2]
~~~

Sau khi nhận response:

1. Kiểm tra số lượng item response khớp số action gửi đi.
2. Đối chiếu từng item với event ID/aggregate ID.
3. Xác định success, retryable failure hoặc permanent failure.
4. Ghi trạng thái bền vững cho từng item.
5. Chỉ tiến checkpoint theo quy tắc an toàn.
6. Ghi metric theo loại kết quả.

Không chỉ dùng cờ errors ở cấp response. Nó cho biết có lỗi trong batch nhưng không nói item nào cần retry. Cũng không giả định thứ tự response có thể thay đổi tùy ý; API Bulk trả item theo thứ tự action, nhưng worker vẫn nên giữ correlation ID rõ ràng để tránh ghép nhầm khi transform hoặc phân nhóm.

## 10. Phân loại lỗi có thể phục hồi và lỗi cần sửa dữ liệu

Một chính sách retry hữu ích phân biệt lỗi tạm thời với lỗi không tự hết.

| Loại lỗi | Hướng xử lý thường gặp |
|---|---|
| 429 / rejected execution | Backoff, giảm batch/concurrency |
| 502, 503, 504 | Retry có giới hạn |
| Network timeout/reset | Retry idempotent, kiểm tra trạng thái nếu cần |
| Cluster unavailable | Giữ backlog, retry có backoff |
| 400 mapping/parsing | DLQ, sửa schema/payload |
| 401/403 | Dừng hoặc cảnh báo cấu hình credential |
| Index not found | Kiểm tra provisioning/alias; không retry vô hạn |
| 409 version conflict | Áp dụng chính sách ordering/version cụ thể |
| Document validation failure | DLQ hoặc reject theo nghiệp vụ |
| Payload quá lớn | Chia nhỏ hoặc xử lý riêng |

Một số status có nhiều nguyên nhân. Ví dụ 409 có thể là conflict do concurrency, duplicate create hoặc optimistic concurrency. Không retry tất cả 409 theo cùng một cách.

## 11. Exponential backoff và jitter

Retry liên tục ngay sau lỗi có thể làm cluster đang quá tải càng khó hồi phục. Dùng exponential backoff:

\[
delay_n = min(maxDelay,\ baseDelay \times 2^n)
\]

Thêm jitter để các worker không đồng loạt retry cùng thời điểm:

\[
actualDelay = random(0,\ delay_n)
\]

Ví dụ cấu hình khái niệm:

- Lần 1: tối đa 200 ms.
- Lần 2: tối đa 400 ms.
- Lần 3: tối đa 800 ms.
- Lần 4: tối đa 1.6 s.
- Giới hạn tối đa: 30 s.
- Sau số lần retry nhất định: DLQ hoặc chuyển sang trạng thái chờ điều tra.

Giá trị cụ thể phụ thuộc throughput, SLA và khả năng cluster. Không dùng retry vô hạn mà không có giới hạn, metric và cảnh báo.

Nếu Elasticsearch trả Retry-After hoặc hệ thống downstream có tín hiệu throttling, cân nhắc tôn trọng chính sách đó thay vì chỉ dùng lịch retry cố định.

## 12. Giảm batch size khi Elasticsearch bị quá tải

Khi bulk thường xuyên có 429 hoặc latency tăng, có thể giảm:

- Số document trong mỗi bulk.
- Tổng byte của mỗi bulk.
- Số bulk request đồng thời.
- Số worker/consumer song song.
- Tốc độ đọc event từ queue.

Batch nên được giới hạn theo cả số item và kích thước byte. Một batch 500 document nhỏ khác đáng kể với 500 document có payload nhiều megabyte.

Một chiến lược adaptive đơn giản:

~~~text
Nếu bulk thành công và latency ổn định:
    tăng batch nhẹ đến giới hạn cấu hình
Nếu có nhiều 429 hoặc timeout:
    giảm batch và concurrency
Nếu mapping error:
    không giảm batch; chuyển item lỗi sang DLQ
~~~

Không tăng batch vô hạn chỉ để giảm số request. Batch lớn làm tăng memory footprint, thời gian xử lý và phạm vi ảnh hưởng khi request timeout.

## 13. Idempotency: nền tảng của retry an toàn

Một event có thể được gửi nhiều lần vì worker crash sau khi Elasticsearch đã ghi nhưng trước khi checkpoint được lưu. Do đó, pipeline nên giả định có thể nhận at-least-once delivery.

**Idempotency** nghĩa là xử lý lại cùng một event không tạo ra trạng thái sai hoặc side effect lặp ngoài ý muốn.

Một cách phổ biến là dùng ID document ổn định:

~~~java
IndexQuery query = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build();
~~~

Nếu cùng một product được index lại với cùng ID, request index sẽ thay thế document theo semantics index operation thay vì tạo bản ghi mới có ID ngẫu nhiên.

Điều này không tự giải quyết ordering. Một event cũ được retry sau event mới vẫn có thể ghi đè dữ liệu mới nếu không kiểm tra version.

## 14. Bảo vệ thứ tự bằng source version

Mỗi aggregate có thể có version tăng đơn điệu:

~~~json
{
  "aggregateId": "p-1001",
  "sourceVersion": 42,
  "eventType": "ProductUpdated"
}
~~~

Khi event version 42 đã được index, event version 41 đến muộn không được phép ghi đè projection.

Các lựa chọn:

- External versioning trong Elasticsearch.
- Lưu sourceVersion trong document và kiểm tra trước khi update.
- Serialize event theo aggregate key.
- Dùng optimistic concurrency với sequence number/primary term khi phù hợp.
- Dùng script cập nhật có điều kiện version.

External versioning cho phép Elasticsearch từ chối một phiên bản cũ hơn phiên bản hiện có. Cần chọn đúng version_type theo semantics của pipeline và hiểu hành vi khi cùng một version được gửi lại.

Không dùng timestamp làm version nếu timestamp có thể trùng hoặc đồng hồ không đồng bộ. Một integer version từ nguồn thường rõ ràng hơn.

## 15. Xử lý version conflict có chủ đích

Khi dùng external versioning, một request cũ có thể nhận conflict vì document đã có version mới hơn. Đây có thể là kết quả đúng: event cũ đã lỗi thời và không cần retry như một lỗi transient.

Worker cần phân biệt:

- Event cũ hơn document: đánh dấu stale/superseded theo chính sách.
- Cùng version và cùng payload: có thể là duplicate đã xử lý.
- Cùng version nhưng payload khác: dấu hiệu dữ liệu nguồn hoặc event producer có vấn đề.
- Version mới hơn: cần index nếu không có conflict khác.

Nếu dùng optimistic concurrency với if_seq_no và if_primary_term, conflict thường có nghĩa document thay đổi kể từ lần đọc. Có thể cần đọc lại và tính toán lại update; không retry nguyên request cũ một cách mù quáng.

## 16. Delete cũng cần version và tombstone

Đồng bộ delete dễ bị bỏ quên. Một document bị xóa ở nguồn nhưng vẫn tồn tại trong Elasticsearch sẽ tiếp tục xuất hiện trong search.

Một event delete có thể mang:

~~~json
{
  "eventId": "evt-delete-1001",
  "aggregateId": "p-1001",
  "sourceVersion": 43,
  "eventType": "ProductDeleted",
  "sourceOccurredAt": "2026-11-13T10:00:00Z"
}
~~~

Nếu event delete bị xử lý trước một event update cũ đến muộn, document có thể bị tạo lại. Versioning hoặc tombstone giúp ngăn tình trạng này.

Một số hệ thống lưu tombstone (trạng thái đã xóa) trong projection hoặc một store riêng đủ lâu để chặn event cũ. Nếu chỉ xóa document ngay, cần hiểu cách pipeline bảo đảm event cũ không tái tạo nó.

Test phải bao gồm update đến trễ sau delete và xác nhận trạng thái cuối vẫn là deleted.

## 17. Outbox pattern và trạng thái event

Một outbox table có thể lưu:

~~~sql
CREATE TABLE outbox_event (
    event_id        VARCHAR(64) PRIMARY KEY,
    aggregate_type  VARCHAR(80) NOT NULL,
    aggregate_id    VARCHAR(128) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type      VARCHAR(120) NOT NULL,
    payload         JSON NOT NULL,
    occurred_at     TIMESTAMP NOT NULL,
    published_at    TIMESTAMP NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NULL,
    last_error      TEXT NULL
);
~~~

Schema thực tế phụ thuộc database. Với PostgreSQL, JSONB và timestamp with time zone có thể phù hợp hơn; worker cũng cần cơ chế claim/lock hoặc CDC để nhiều instance không xử lý trùng ngoài ý muốn.

Các trạng thái vận hành có thể được lưu ở bảng riêng hoặc suy ra từ published/attempt fields. Tránh cập nhật outbox row và Elasticsearch trong một transaction giả định có thể rollback cả hai.

Outbox nên được giữ đủ lâu để phục vụ replay và điều tra. Xóa event ngay sau khi publish có thể làm mất khả năng khôi phục khi phát hiện mapping bug vài giờ sau đó.

## 18. Dead Letter Queue (DLQ)

DLQ lưu event không thể xử lý tự động sau khi retry hoặc gặp lỗi vĩnh viễn.

Một DLQ record nên giữ:

- eventId và aggregateId.
- sourceVersion/sequence.
- payload gốc hoặc tham chiếu an toàn tới payload.
- thời điểm phát sinh.
- loại lỗi và error message đã được làm sạch.
- số lần thử.
- worker/build version.
- index/alias đích.
- trạng thái replay và người/phê duyệt nếu cần.

Ví dụ record:

~~~json
{
  "eventId": "evt-1003",
  "aggregateId": "p-1003",
  "sourceVersion": 8,
  "attempts": 5,
  "failureType": "mapper_parsing_exception",
  "target": "products-write",
  "status": "PENDING_REPAIR"
}
~~~

DLQ không phải thùng rác để quên. Cần dashboard, alert, owner, thời hạn xử lý và quy trình replay. Nếu DLQ tăng nhưng không có người chịu trách nhiệm, hệ thống có thể âm thầm tích lũy dữ liệu lệch.

Không lưu secret, access token hoặc thông tin cá nhân không cần thiết trong error payload. Bảo vệ DLQ như dữ liệu nghiệp vụ.

## 19. Replay event từ DLQ

Sau khi sửa mapping hoặc payload, có thể replay event:

1. Chọn một tập DLQ event theo loại lỗi hoặc khoảng thời gian.
2. Kiểm tra schema và source version.
3. Xác định event còn cần thiết hay đã bị event mới hơn thay thế.
4. Tạo lại document/query từ payload nguồn hoặc đọc lại trạng thái mới nhất.
5. Gửi tới index đích.
6. Kiểm tra kết quả từng item.
7. Chỉ đánh dấu DLQ record đã xử lý khi kết quả được xác nhận.
8. Ghi audit trail cho lần replay.

Có hai chiến lược:

- **Replay event nguyên bản:** hữu ích khi cần tái hiện lịch sử và event vẫn có đầy đủ dữ liệu.
- **Rebuild từ trạng thái mới nhất:** phù hợp khi event cũ đã lỗi thời hoặc projection có thể dựng lại từ source of truth.

Không replay hàng loạt toàn bộ DLQ ngay sau khi cluster vừa hồi phục. Bắt đầu với batch nhỏ, đo latency và lỗi, sau đó tăng dần.

## 20. Retry queue và DLQ khác nhau

Retry queue giữ các event có khả năng thành công sau một khoảng chờ. DLQ giữ event cần điều tra hoặc sửa trước khi thử lại.

| Retry queue | DLQ |
|---|---|
| Lỗi tạm thời | Lỗi vĩnh viễn hoặc đã hết retry |
| Có nextAttemptAt | Có failure classification |
| Tự động thử lại theo lịch | Thường cần quyết định replay |
| Backoff và jitter | Theo dõi owner và remediation |
| Thời gian lưu thường ngắn | Cần retention đủ để điều tra |

Không chuyển mọi lỗi vào retry queue. Mapping error sẽ không tự biến mất sau 30 giây. Ngược lại, không đưa mọi timeout vào DLQ ngay lập tức nếu request có thể retry an toàn.

## 21. Khôi phục sau khi Elasticsearch ngừng hoạt động

Khi Elasticsearch không sẵn sàng:

- Không xóa hoặc bỏ qua event nguồn.
- Giữ event trong outbox/broker.
- Giảm hoặc dừng consumer theo backpressure.
- Retry có backoff, không tạo retry storm.
- Theo dõi oldest pending age và queue depth.
- Bảo đảm nguồn event đủ retention cho thời gian outage.
- Khi cluster hồi phục, tăng throughput từ từ.
- Kiểm tra item-level failures trong bulk.
- Xác nhận lag giảm và searchable latency trở lại bình thường.

Nếu consumer tiếp tục đọc nhanh hơn khả năng ghi, queue có thể tràn hoặc memory tăng. Cần có giới hạn queue và chính sách pause/resume.

Khi outage kéo dài vượt retention của broker hoặc CDC log, có thể phải thực hiện backfill từ database hoặc snapshot. Vì vậy, recovery plan phải tính tới giới hạn lưu event, không chỉ cách restart worker.

## 22. Khôi phục sau lỗi mapping hoặc schema

Một mapping error thường không tự hết khi retry. Ví dụ nguồn bắt đầu gửi chuỗi vào field đã mapping numeric.

Quy trình:

1. Dừng hoặc cô lập loại event gây lỗi nếu nó làm DLQ tăng nhanh.
2. Xác định field và schema version thay đổi.
3. Kiểm tra mapping hiện tại.
4. Chọn cách sửa: sửa payload, thêm field mới, tạo index version mới hoặc dùng ingest transform.
5. Replay các event bị ảnh hưởng.
6. Kiểm tra document và query sau khi replay.
7. Tiếp tục consumer khi lỗi đã được xử lý.

Elasticsearch không cho phép thay đổi tùy ý một số field mapping đã tạo. Nếu cần đổi kiểu dữ liệu, thường phải tạo index mới với mapping đúng, reindex dữ liệu và chuyển alias sau khi xác minh.

Không đổi mapping production trực tiếp chỉ để làm hết lỗi mà chưa đánh giá tác động tới query, sort, aggregation và dữ liệu hiện có.

## 23. Snapshot + change stream để xây dựng lại index

Khi cần tạo index mới hoặc phục hồi projection từ đầu, có thể kết hợp snapshot dữ liệu nguồn với change stream.

Luồng khái quát:

~~~text
1. Capture database log position L0
             |
             v
2. Read consistent source snapshot
             |
             v
3. Bulk index snapshot into new index
             |
             v
4. Replay changes after L0
             |
             v
5. Catch up to current position
             |
             v
6. Validate counts / samples / hashes
             |
             v
7. Switch read alias to new index
~~~

Điểm quan trọng là snapshot và log position phải nhất quán. Nếu lấy snapshot trước rồi mới bắt đầu đọc CDC mà không có điểm nối chính xác, các thay đổi xảy ra giữa hai bước có thể bị bỏ sót.

Với database có cơ chế consistent snapshot gắn với log position, lưu position đó làm mốc replay. Tùy công nghệ CDC, cần làm theo đúng quy trình connector để tránh gap hoặc duplicate; duplicate thường có thể xử lý bằng idempotency, nhưng gap thì không thể tự sửa nếu không có reconciliation.

## 24. Rebuild index bằng alias

Một cách an toàn để xây index mới là dùng versioned index và alias:

~~~text
products-v1  <- alias products-read
products-v2  <- build + validate
                  |
                  v
            atomic alias switch
                  |
                  v
products-read -> products-v2
~~~

Quy trình:

1. Tạo products-v2 với mapping/settings mới.
2. Đọc snapshot nguồn và bulk index vào v2.
3. Replay các event phát sinh trong lúc snapshot.
4. Catch up đến một watermark đủ mới.
5. Chạy reconciliation.
6. Chuyển alias read/write theo kế hoạch.
7. Giữ index cũ trong thời gian rollback đã định.
8. Xóa index cũ sau khi xác nhận ổn định và hết retention.

Alias switch có thể thực hiện bằng một update aliases request nguyên tử trong Elasticsearch. Phải xác định rõ write alias và read alias; không để producer ghi nhầm vào index cũ sau khi chuyển.

Nếu dùng external versioning, có thể replay snapshot và events theo version để event cũ không ghi đè bản mới. Cần xác nhận version semantics phù hợp với bulk operation và mapping.

## 25. Reconciliation: so sánh nguồn với projection

Replay không thay thế reconciliation. Một pipeline có thể báo mọi event thành công nhưng vẫn có dữ liệu sai do bug transform, event bị thiếu trước khi monitoring bắt đầu hoặc thao tác ghi bypass outbox.

Reconciliation so sánh dữ liệu nguồn với Elasticsearch theo một phạm vi có kiểm soát.

Các mức kiểm tra:

- **Count:** số document theo tenant, trạng thái hoặc partition.
- **Existence:** ID có ở cả nguồn và projection hay không.
- **Version:** sourceVersion có khớp phiên bản nguồn không.
- **Field sample:** so sánh một số field quan trọng.
- **Hash/checksum:** tạo fingerprint ổn định từ field nghiệp vụ.
- **Delete consistency:** tài liệu đã xóa không còn xuất hiện.
- **Aggregate comparison:** so sánh tổng hoặc phân bố theo nhóm.

Không chỉ so tổng số document toàn index. Tenant A thiếu 100 document và tenant B thừa 100 document có thể làm tổng count vẫn bằng nhau.

## 26. Reconciliation theo partition hoặc thời gian

Với dữ liệu lớn, không nên tải toàn bộ source và Elasticsearch về application để so sánh trong một lần. Chia phạm vi theo:

- Tenant.
- ID range.
- Ngày tạo/cập nhật.
- Partition key.
- Loại entity.
- Source version window.

Ví dụ reconciliation theo ngày và tenant:

~~~text
tenant-a / 2026-11-12
tenant-a / 2026-11-13
tenant-b / 2026-11-12
tenant-b / 2026-11-13
~~~

Mỗi partition có thể lưu:

- Source count.
- Elasticsearch count.
- Mismatch count.
- Oldest mismatch age.
- Last checked time.
- Status: MATCH, MISMATCH, FAILED hoặc IN_PROGRESS.

Nếu phát hiện mismatch, tạo repair task có phạm vi nhỏ thay vì chạy lại toàn bộ index ngay lập tức.

## 27. Sửa dữ liệu lệch mà không tạo thêm lỗi

Khi reconciliation phát hiện document thiếu hoặc cũ:

1. Đọc trạng thái mới nhất từ source of truth.
2. Xác định source version.
3. Tạo document projection bằng cùng transformation code với luồng bình thường.
4. Index bằng ID ổn định và version guard.
5. Xác nhận document trong Elasticsearch.
6. Ghi repair result và source version đã áp dụng.

Nếu dùng event cũ để sửa document mà nguồn đã thay đổi thêm, có thể đưa projection lùi về trạng thái cũ. Với repair, thường an toàn hơn khi dựng lại từ trạng thái mới nhất của nguồn thay vì replay một payload cũ mà không kiểm tra version.

Với document đã bị xóa, cần xử lý tombstone/delete semantics để event cũ không tái tạo nó sau repair.

## 28. Theo dõi throughput và backlog

Lag là một chỉ số, nhưng cần thêm các metric để giải thích nguyên nhân:

- events produced per second.
- events consumed per second.
- events indexed per second.
- queue depth hoặc consumer lag.
- oldest pending event age.
- bulk requests per second.
- bulk items per request.
- bulk byte size.
- item success/failure count.
- retry count và retry delay.
- DLQ size và oldest DLQ age.
- Elasticsearch request latency.
- 429, 5xx, timeout và connection error rate.
- worker concurrency và processing duration.
- refresh/search visibility delay.

Nếu producer tạo 1.000 event/giây nhưng worker chỉ xử lý 700 event/giây, backlog tăng khoảng 300 event/giây. Một lag dashboard không có throughput sẽ khó dự đoán khi nào backlog được xử lý xong.

Backlog drain time có thể ước lượng:

\[
drainTime \approx \frac{pendingEvents}{processingRate - incomingRate}
\]

Công thức chỉ có ý nghĩa khi processingRate lớn hơn incomingRate và tốc độ tương đối ổn định. Nếu worker không có capacity dư, backlog sẽ không tự giảm.

## 29. Metric và dashboard với Spring Boot

Spring Boot Actuator và Micrometer có thể cung cấp metric cho worker. Ví dụ:

~~~java
@Component
public class SyncMetrics {

    private final MeterRegistry registry;

    public SyncMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordIndexed(String eventType) {
        registry.counter(
                "search.sync.items",
                "result", "success",
                "event_type", eventType
        ).increment();
    }

    public void recordFailure(String category) {
        registry.counter(
                "search.sync.items",
                "result", "failure",
                "failure_type", category
        ).increment();
    }

    public void recordLag(Duration lag) {
        registry.timer("search.sync.lag")
                .record(lag);
    }

    public void recordProcessingTime(Duration duration) {
        registry.timer("search.sync.processing")
                .record(duration);
    }
}
~~~

Đây là ví dụ đơn giản về cách ghi counter và timer. Trong production, không thêm eventId, documentId hoặc tenantId có cardinality rất cao làm metric tag mặc định. Những giá trị đó phù hợp hơn với log/trace có kiểm soát.

Gauge có thể theo dõi queue depth hoặc oldest pending age. Với metric gauge, nguồn dữ liệu phải được cập nhật an toàn và không thực hiện query database nặng mỗi lần scrape.

## 30. Theo dõi searchable lag

Nếu yêu cầu là “người dùng tìm thấy dữ liệu ngay sau khi cập nhật”, đo thời điểm Elasticsearch nhận write là chưa đủ.

Có thể đo searchable lag bằng một trong các cách:

- Sampling event đã index rồi truy vấn lại theo ID sau một khoảng ngắn.
- Dùng một canary document được cập nhật định kỳ và đo thời gian xuất hiện trong search.
- Dùng refresh policy phù hợp cho các thao tác cần read-after-write.
- Đo khoảng thời gian giữa write acknowledgement và lần search đầu tiên thấy document.

Không nên gửi một search request riêng cho từng event trong production chỉ để đo lag; cách đó có thể tạo thêm tải lớn hơn chính pipeline. Sampling hoặc canary thường phù hợp hơn.

Refresh là cơ chế làm các thay đổi đã index trở nên searchable. Đặt refresh=wait_for có thể hữu ích cho một số request cần chờ refresh, nhưng dùng trên mọi bulk có thể giảm throughput. Cần cân bằng yêu cầu read-after-write với hiệu năng.

## 31. Định nghĩa SLI, SLO và alert

Một số SLI có thể dùng:

- p95 end-to-end sync lag.
- p99 end-to-end sync lag.
- oldest pending event age.
- tỷ lệ event thành công trong cửa sổ thời gian.
- DLQ growth rate.
- tỷ lệ bulk item failure.
- tỷ lệ document version mismatch.
- searchable lag của canary.

Ví dụ SLO minh họa:

| Chỉ số | Mục tiêu ví dụ |
|---|---|
| p95 source-to-searchable lag | dưới 30 giây |
| p99 source-to-searchable lag | dưới 2 phút |
| oldest pending event age | dưới 5 phút |
| tỷ lệ event được index thành công | 99.9% trong cửa sổ ngày |
| DLQ item chưa xử lý | không tăng liên tục |

Các con số này không phải mặc định cho mọi hệ thống. Chọn mục tiêu theo yêu cầu sản phẩm, tải, refresh interval và chi phí vận hành.

Alert nên dựa trên mức độ ảnh hưởng:

- Warning khi p95 lag vượt SLO trong một khoảng thời gian.
- Critical khi oldest pending age tăng nhanh hoặc consumer không tiến offset.
- Critical khi DLQ có lỗi mapping hàng loạt.
- Warning khi retry rate tăng hoặc có nhiều 429.
- Critical khi nguồn event sắp hết retention trước khi backlog được xử lý.

Tránh alert trên một spike ngắn không có ảnh hưởng thực tế. Dùng cửa sổ thời gian và điều kiện kéo dài phù hợp.

## 32. Phân biệt lag với dữ liệu mất

Lag nghĩa là dữ liệu chưa đến đích hoặc chưa searchable trong thời gian mong muốn. Data loss nghĩa là event hoặc thay đổi không còn khả năng được tái tạo qua pipeline hiện tại.

Ví dụ:

- Queue còn 100.000 event chưa xử lý: backlog/lag, chưa chắc mất dữ liệu.
- Consumer offset đã nhảy qua event lỗi nhưng event không được lưu DLQ: có nguy cơ mất dữ liệu.
- Outbox row bị xóa trước khi publish: có thể mất event.
- CDC log retention hết trước khi consumer bắt kịp: có thể không replay được từ log.
- Document bị ghi sai nhưng event vẫn còn: projection lệch, có thể repair.

Dashboard cần hiển thị checkpoint, retention head/tail, DLQ và reconciliation status để phân biệt hai trạng thái.

## 33. RPO và RTO cho projection Elasticsearch

**RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa có thể chấp nhận khi xảy ra sự cố. **RTO (Recovery Time Objective)** là thời gian tối đa để khôi phục dịch vụ.

Với Elasticsearch là projection có thể rebuild:

- RPO phụ thuộc khả năng giữ source data, outbox/CDC log và checkpoint.
- RTO phụ thuộc tốc độ snapshot, bulk indexing, replay backlog và alias switch.
- Nếu source event chỉ được giữ 24 giờ nhưng outage kéo dài 48 giờ, có thể không replay được từ log.
- Nếu index rebuild mất 6 giờ mà SLO chỉ cho phép gián đoạn 30 phút, cần chiến lược index song song hoặc snapshot gần đây.

Hãy tính RTO bằng dữ liệu thực tế: số document, kích thước trung bình, throughput bulk ổn định, thời gian replay và reconciliation. Không ước lượng chỉ từ tốc độ trên máy local.

## 34. Runbook khi lag vượt ngưỡng

Một runbook có thể theo trình tự:

1. Xác nhận lag ở source-to-consumer hay write-to-searchable.
2. Kiểm tra queue depth, oldest pending age và consumer offset.
3. Kiểm tra worker health, restart count và deployment gần nhất.
4. Kiểm tra Elasticsearch cluster health, thread pool, 429, 5xx và latency.
5. Kiểm tra bulk item failures, retry queue và DLQ.
6. Xác định lỗi là transient, mapping/schema hay credential/config.
7. Nếu downstream quá tải, giảm concurrency/batch hoặc pause consumer.
8. Nếu lỗi mapping, cô lập loại event và sửa schema/payload.
9. Khi cluster ổn định, resume theo batch nhỏ và theo dõi backlog drain rate.
10. Chạy reconciliation trên partition bị ảnh hưởng.
11. Xác nhận searchable lag trở lại SLO.
12. Ghi lại nguyên nhân, thời gian ảnh hưởng và biện pháp phòng ngừa.

Không chỉ restart worker khi chưa hiểu nguyên nhân. Restart có thể làm mất trạng thái trong memory, tạo duplicate hoặc khiến nhiều instance cùng retry.

## 35. Diễn tập khôi phục

Recovery plan cần được kiểm tra định kỳ. Một số kịch bản diễn tập:

- Dừng Elasticsearch trong vài phút rồi bật lại.
- Tạo bulk 429 bằng cách tăng tải trong môi trường test.
- Gửi payload sai mapping để tạo DLQ.
- Kill worker sau khi Elasticsearch đã ghi nhưng trước khi checkpoint được commit.
- Gửi event version cũ sau event version mới.
- Tạo delete event rồi replay update cũ.
- Tạm dừng consumer đến gần retention limit.
- Rebuild index mới và chuyển alias.
- Tạo mismatch có chủ đích rồi chạy reconciliation/repair.

Mỗi bài diễn tập cần ghi lại: thời gian phát hiện, thời gian khôi phục, số event retry, số item DLQ, dữ liệu lệch trước/sau, và liệu SLO/RPO/RTO có được đáp ứng.

Không chỉ kiểm tra worker khởi động lại được. Cần xác nhận không mất event, không ghi lùi version và search trả trạng thái cuối đúng.

## 36. Kiểm thử checkpoint và crash recovery

Một integration test quan trọng là mô phỏng crash giữa các bước:

~~~text
1. Worker đọc event E42
2. Elasticsearch ghi E42 thành công
3. Worker crash trước khi commit checkpoint
4. Worker restart
5. E42 được đọc lại
6. Index lại với cùng document ID/version
7. Worker commit checkpoint
~~~

Kết quả phải là một document đúng, không tạo bản sao và không ghi đè một version mới hơn.

Một kịch bản khác:

~~~text
1. Worker đọc E42, E43, E44
2. E42 và E44 thành công
3. E43 thất bại
4. Worker restart
5. Checkpoint không được bỏ qua E43
~~~

Nếu xử lý song song, cần kiểm tra contiguous checkpoint hoặc cơ chế ack theo partition của broker. Không cập nhật offset cao nhất đã hoàn thành khi vẫn còn gap phía trước.

## 37. Kiểm thử Bulk API partial failure

Tạo một batch gồm:

- Một document hợp lệ.
- Một document có lỗi mapping.
- Một item có thể bị conflict.
- Một item có thể bị throttling trong test có kiểm soát.

Xác nhận:

- Worker đọc item response riêng.
- Item thành công không bị gửi lại không cần thiết nếu trạng thái đã được ghi nhận.
- Item retryable được lên lịch retry.
- Item permanent được đưa vào DLQ.
- Checkpoint tuân theo chính sách không bỏ qua gap.
- Metric phản ánh đúng số success/failure.
- Replay sau khi sửa lỗi không làm hỏng document mới hơn.

Không nên dùng mock response duy nhất để kết luận Bulk API behavior. Nên có integration test với Elasticsearch và unit test cho classifier/worker state machine.

## 38. Kiểm thử lag bằng clock có thể điều khiển

Không dùng Thread.sleep trong unit test để chờ lag. Inject Clock để tạo thời gian xác định:

~~~java
public class SyncLagCalculator {

    private final Clock clock;

    public SyncLagCalculator(Clock clock) {
        this.clock = clock;
    }

    public Duration lag(Instant sourceOccurredAt) {
        return Duration.between(
                sourceOccurredAt,
                clock.instant()
        );
    }
}
~~~

Test:

~~~java
@Test
void calculatesLagFromSourceTimestamp() {
    Clock clock = Clock.fixed(
            Instant.parse("2026-11-13T10:00:30Z"),
            ZoneOffset.UTC
    );

    SyncLagCalculator calculator =
            new SyncLagCalculator(clock);

    Duration lag = calculator.lag(
            Instant.parse("2026-11-13T10:00:00Z")
    );

    assertEquals(Duration.ofSeconds(30), lag);
}
~~~

Cách này kiểm tra phép tính mà không phụ thuộc thời gian chạy test. Với integration test, có thể dùng event fixture timestamp cố định và xác nhận metric/record tương ứng.

## 39. Những lỗi thường gặp khi theo dõi và khôi phục đồng bộ

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Dashboard báo lag thấp nhưng người dùng chưa thấy document | Chỉ đo write acknowledgement, bỏ qua refresh | Đo searchable lag hoặc canary |
| Bulk request thành công nhưng thiếu document | Bỏ qua item-level errors | Đọc từng item response |
| Checkpoint nhảy qua event lỗi | Commit offset trước khi xử lý bền vững | Ack sau success/DLQ và giữ contiguous progress |
| Retry làm document cũ ghi đè mới | Không có source version guard | External version hoặc kiểm tra version |
| Delete rồi document xuất hiện lại | Event update cũ đến trễ | Tombstone/version ordering |
| DLQ tăng nhưng không ai xử lý | Thiếu owner, alert và replay workflow | Runbook, dashboard và SLA xử lý DLQ |
| Backlog không giảm sau recovery | Throughput chỉ bằng hoặc thấp hơn incoming rate | Tăng capacity có kiểm soát, giảm producer load |
| Replay tạo dữ liệu trùng | ID không ổn định hoặc side effect không idempotent | Deterministic ID và idempotency key |
| Rebuild index bỏ sót thay đổi | Snapshot không nối đúng CDC position | Snapshot + log position nhất quán |
| Count hai hệ thống bằng nhau nhưng dữ liệu lệch | Thiếu đối chiếu theo partition/ID | Version/hash reconciliation |
| Retry storm sau outage | Nhiều worker retry cùng lúc | Exponential backoff và jitter |
| Mapping error retry mãi | Không phân loại permanent failure | DLQ và sửa schema |
| Lag âm hoặc bất thường | Clock skew hoặc timestamp sai nguồn | UTC, đồng bộ clock và kiểm tra event time |

## 40. Checklist thiết kế đồng bộ có thể khôi phục

**Nguồn và sự kiện**

- Xác định source of truth.
- Có outbox hoặc CDC bền vững.
- Event có ID ổn định.
- Có aggregate version/sequence khi cần ordering.
- Payload có timestamp nguồn và schema version.
- Retention đủ dài cho outage và replay.

**Xử lý và checkpoint**

- Tách received, processed, indexed và searchable.
- Kiểm tra từng bulk item.
- Checkpoint chỉ tiến khi trạng thái đã bền vững.
- Xử lý gap khi có parallelism.
- Idempotent khi event được gửi lại.
- Version guard chống ghi lùi.
- Delete/tombstone có ordering rõ.

**Retry và DLQ**

- Phân loại transient/permanent.
- Exponential backoff và jitter.
- Giới hạn attempts và tổng retry time.
- Điều chỉnh batch/concurrency khi có 429.
- DLQ có payload/reference, error, owner và retention.
- Có quy trình replay và audit trail.

**Quan sát và khôi phục**

- Đo source-to-consumer và source-to-searchable lag.
- Theo dõi p95/p99 và oldest pending age.
- Theo dõi throughput, queue depth, retry, DLQ và bulk errors.
- Có SLO, alert và runbook.
- Có snapshot + CDC catch-up cho rebuild.
- Có reconciliation theo tenant/partition/version.
- Có RPO/RTO được đo.
- Diễn tập crash, outage, mapping error và replay định kỳ.

Theo dõi độ trễ đồng bộ không chỉ là đo thời gian Bulk API trả về. Cần biết thay đổi đã đi từ source of truth qua queue, worker và Elasticsearch đến thời điểm searchable; đồng thời giữ checkpoint, version và event history đủ bền vững để khôi phục sau lỗi. Bulk item failure phải được xử lý riêng, retry cần idempotency và backoff, lỗi không tự hết phải vào DLQ, còn replay/backfill cần có version guard và reconciliation. Khi có metric theo từng giai đoạn, runbook và recovery drill, Elasticsearch có thể được xây dựng lại hoặc bắt kịp backlog mà không âm thầm bỏ sót thay đổi hay ghi lùi trạng thái dữ liệu.

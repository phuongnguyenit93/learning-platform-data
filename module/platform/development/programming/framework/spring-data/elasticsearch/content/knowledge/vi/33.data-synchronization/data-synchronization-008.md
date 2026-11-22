# Retry, hàng đợi lỗi và đối soát dữ liệu bị thiếu

Elasticsearch thường được dùng như một search projection của dữ liệu đến từ database, message broker hoặc một hệ thống nghiệp vụ khác. Khi nguồn dữ liệu thay đổi, ứng dụng cần đồng bộ thay đổi đó vào index để tìm kiếm phản ánh trạng thái mới nhất. Trong thực tế, quá trình đồng bộ có thể thất bại vì network timeout, cluster quá tải, shard chưa sẵn sàng, mapping không phù hợp, dữ liệu lỗi hoặc consumer dừng giữa chừng.

Một hệ thống đồng bộ đáng tin cậy cần giải quyết ba việc:

- **Retry:** thử lại những thao tác thất bại tạm thời với giới hạn và backoff phù hợp.
- **Hàng đợi lỗi (Dead Letter Queue - DLQ):** lưu bền vững những event không thể xử lý sau chính sách retry để điều tra và replay.
- **Đối soát (reconciliation):** so sánh dữ liệu nguồn với search index để phát hiện và sửa những document bị thiếu, cũ hoặc sai lệch.

Retry giúp xử lý lỗi tạm thời. DLQ giữ lại những trường hợp chưa thể xử lý. Reconciliation phát hiện những sai lệch mà retry/event delivery không thể tự bảo đảm đã khắc phục, ví dụ event bị mất trước khi vào queue, consumer chết sau khi ghi một phần, hoặc lỗi mapping kéo dài.

Không nên xem Elasticsearch là nguồn dữ liệu nghiệp vụ duy nhất nếu hệ thống cần transaction và lịch sử thay đổi đáng tin cậy. Một thiết kế phổ biến là giữ database hoặc hệ thống nghiệp vụ làm source of truth, rồi đồng bộ sang Elasticsearch theo mô hình eventual consistency.

## 1. Vì sao đồng bộ dữ liệu có thể bị thiếu?

Giả sử một dịch vụ quản lý sản phẩm có database làm nguồn chính và Elasticsearch phục vụ tìm kiếm:

    Database
       |
       v
    Outbox / Change Event
       |
       v
    Message Broker
       |
       v
    Sync Consumer
       |
       v
    Elasticsearch Index

Một sản phẩm được cập nhật trong database nhưng không xuất hiện trong search có thể do nhiều nguyên nhân:

- Transaction database commit nhưng event không được publish.
- Event được publish nhưng broker hoặc consumer gặp sự cố.
- Consumer nhận event nhưng không ghi được document.
- Bulk request trả thành công ở cấp HTTP nhưng một item thất bại.
- Consumer ghi document thành công nhưng chết trước khi acknowledge message.
- Message bị xử lý lặp hoặc sai thứ tự, khiến dữ liệu mới bị ghi đè bởi dữ liệu cũ.
- Mapping hoặc ingest pipeline thay đổi làm event cũ không còn hợp lệ.
- Retry hết số lần nhưng không có DLQ.
- Document bị xóa nhầm, bị ghi vào index khác hoặc dùng sai routing.
- Một đợt reindex hoặc deploy chuyển alias không hoàn tất.

Vì vậy, một luồng đồng bộ chỉ dựa vào việc gọi save và log exception là chưa đủ. Cần có trạng thái xử lý, khả năng retry, lưu lỗi bền vững và cơ chế phát hiện sai lệch độc lập.

## 2. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng nên retry. Retry một lỗi dữ liệu không hợp lệ thường chỉ làm tăng tải và trì hoãn việc phát hiện nguyên nhân.

Có thể chia lỗi thành hai nhóm:

- **Transient failure:** lỗi có khả năng tự hết nếu thử lại sau một khoảng thời gian.
- **Permanent failure:** lỗi cần thay đổi dữ liệu, mapping, cấu hình hoặc logic trước khi thử lại.

Ví dụ:

| Lỗi | Phân loại thường gặp | Hành động |
|---|---|---|
| HTTP 429 / rejected execution | Tạm thời | Giảm tốc, backoff, retry item lỗi |
| Connection reset / temporary network failure | Tạm thời | Retry có giới hạn |
| Timeout với kết quả không rõ | Có thể tạm thời nhưng trạng thái mơ hồ | Retry an toàn hoặc đối soát trước |
| Shard unavailable trong thời gian ngắn | Tạm thời | Backoff, kiểm tra cluster health |
| HTTP 502/503/504 từ gateway hoặc cluster | Thường tạm thời | Retry có giới hạn |
| Mapper parsing exception | Thường lâu dài | Đưa vào DLQ, sửa dữ liệu hoặc mapping |
| Mapping conflict / field type sai | Lâu dài cho đến khi sửa schema | Không retry liên tục |
| Pipeline không tồn tại | Lỗi cấu hình | Dừng hoặc DLQ có phân loại |
| Unauthorized / forbidden | Lỗi quyền/cấu hình | Dừng retry tự động, cảnh báo |
| Version conflict 409 | Xung đột logic hoặc thứ tự | Đọc lại, so version, xử lý theo nghiệp vụ |
| Document không tồn tại khi update | Tùy use case | Upsert, bỏ qua hoặc DLQ theo hợp đồng |

Phân loại cần dựa trên exception type, HTTP status, Elasticsearch error type và ngữ cảnh thao tác. Không nên chỉ dựa vào status code tổng của bulk request.

## 3. Bulk API có partial failure

Bulk API xử lý nhiều thao tác trong một request. Một bulk request có thể hoàn tất ở cấp HTTP nhưng một số item bên trong thất bại.

Ví dụ response:

    {
      "took": 32,
      "errors": true,
      "items": [
        {
          "index": {
            "_id": "p-100",
            "status": 201
          }
        },
        {
          "index": {
            "_id": "p-101",
            "status": 429,
            "error": {
              "type": "es_rejected_execution_exception",
              "reason": "rejected execution"
            }
          }
        },
        {
          "index": {
            "_id": "p-102",
            "status": 400,
            "error": {
              "type": "mapper_parsing_exception",
              "reason": "failed to parse field"
            }
          }
        }
      ]
    }

Trong ví dụ:

- p-100 đã được index thành công.
- p-101 bị từ chối tạm thời và có thể được retry sau backoff.
- p-102 có dữ liệu không phù hợp mapping; cần sửa dữ liệu hoặc schema trước khi replay.

Nếu chỉ kiểm tra HTTP status, ứng dụng có thể kết luận sai rằng toàn bộ batch đã thành công. Với bulk, luôn kiểm tra trường errors và kết quả của từng item.

## 4. Retry đúng phần thất bại

Giả sử một batch có 500 item, trong đó 490 item thành công và 10 item bị 429. Retry cả 500 item là lãng phí và có thể gây ghi lặp. Nên tách 10 item thất bại thành một tập riêng để retry.

Luồng xử lý:

    Tạo batch
       |
       v
    Gửi Bulk request
       |
       v
    Đọc kết quả từng item
       |
       +---- Thành công ----> Đánh dấu hoàn tất
       |
       +---- Lỗi tạm thời --> Retry queue / backoff
       |
       +---- Lỗi lâu dài ---> DLQ
       |
       v
    Cập nhật checkpoint khi đã xử lý xong

Nếu API Spring Data trả về metadata theo từng thao tác, hãy đối chiếu kết quả với item đầu vào bằng ID hoặc correlation key. Không dựa vào thứ tự nếu tầng adapter của ứng dụng có thể sắp xếp hoặc lọc lại item.

Với bulk request bị timeout ở cấp HTTP, ứng dụng có thể không biết Elasticsearch đã xử lý được bao nhiêu item. Trạng thái khi đó là ambiguous. Nếu thao tác có tính idempotent, có thể retry cả batch theo chiến lược an toàn; nếu thao tác không idempotent, cần đọc lại trạng thái hoặc thiết kế idempotency key trước khi retry.

## 5. Exponential backoff và jitter

Retry liên tục ngay lập tức có thể làm cluster đang quá tải càng quá tải hơn. Khi nhiều consumer cùng retry, chúng có thể tạo retry storm.

Exponential backoff tăng thời gian chờ theo số lần thử:

    delay = min(maxDelay, baseDelay * 2^attempt)

Jitter thêm yếu tố ngẫu nhiên để các worker không retry cùng một thời điểm:

    actualDelay = random(0, delay)

Ví dụ với base delay 200 ms và max delay 10 giây:

| Lần thử lại | Delay tối đa trước jitter |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.6 s |
| 5 | 3.2 s |
| 6 trở đi | Tối đa 10 s |

Giá trị này chỉ là ví dụ. Cần chọn theo latency mục tiêu, thời gian tồn tại của event, broker visibility timeout và khả năng phục hồi của cluster.

Nguyên tắc:

- Có số lần retry tối đa.
- Có thời gian chờ tối đa.
- Dùng jitter.
- Tôn trọng Retry-After nếu gateway hoặc dịch vụ cung cấp.
- Giảm concurrency khi nhận nhiều 429.
- Không retry lỗi dữ liệu hoặc lỗi quyền vô hạn.
- Ghi nhận số lần retry và thời gian event nằm trong hệ thống.

## 6. Retry ở tầng nào?

Retry có thể xuất hiện ở nhiều tầng:

- HTTP client retry request.
- Elasticsearch client retry một số lỗi transport.
- Service retry thao tác.
- Message broker redelivery message.
- Consumer retry queue.
- Job reconciliation chạy lại dữ liệu thiếu.

Nhiều tầng retry có thể nhân số lần thử. Ví dụ HTTP client retry 3 lần, service retry 3 lần và broker redelivery 5 lần có thể tạo ra nhiều lần gọi Elasticsearch hơn dự kiến.

Hãy chọn một tầng chịu trách nhiệm chính cho retry nghiệp vụ và ghi rõ giới hạn ở các tầng thấp hơn. Retry ở HTTP client chỉ nên xử lý lỗi transport phù hợp; retry ở consumer cần biết item nào thành công, item nào thất bại và khi nào message được acknowledge.

## 7. Idempotency là điều kiện quan trọng để retry an toàn

At-least-once delivery có nghĩa một event có thể được giao nhiều lần. Consumer phải chịu được việc nhận lại cùng một event.

Ví dụ index document theo ID ổn định:

    PUT products/_doc/p-100
    {
      "id": "p-100",
      "name": "Keyboard K8",
      "price": 120
    }

Gửi lại cùng ID và cùng source thường tạo cùng trạng thái cuối. Đây là một thao tác tương đối idempotent.

Ngược lại, update kiểu tăng giá trị:

    POST products/_update/p-100
    {
      "script": {
        "source": "ctx._source.viewCount += params.count",
        "params": {
          "count": 1
        }
      }
    }

Nếu event bị xử lý hai lần, viewCount có thể tăng hai lần. Đây không phải thao tác idempotent.

Một số cách tăng độ an toàn:

- Dùng document ID xác định từ khóa nghiệp vụ hoặc event.
- Lưu source version hoặc event sequence.
- Bỏ qua event cũ hơn version đã xử lý.
- Dùng update có điều kiện.
- Lưu event ID đã xử lý nếu cần deduplication.
- Thiết kế update theo trạng thái mong muốn thay vì cộng dồn mù quáng.

## 8. Bảo vệ khỏi event đến sai thứ tự

Idempotency không tự giải quyết thứ tự event. Giả sử sản phẩm có hai phiên bản:

    Event A: version 10, price = 100
    Event B: version 11, price = 120

Nếu B được xử lý trước rồi A đến muộn, index có thể bị ghi lùi về version 10 nếu consumer không kiểm tra version.

Có thể dùng external version hoặc lưu source version trong document để từ chối event cũ. Ví dụ khái niệm:

    if (event.version <= indexed.version) {
        ignore(event);
    } else {
        index(event);
    }

Khi dùng Elasticsearch external versioning, cần hiểu semantics của version_type và cách API client truyền version. Không dùng version tăng tự phát ở consumer nếu source có version đáng tin cậy.

Nếu nhiều event cùng một aggregate cần giữ thứ tự, broker partition key theo aggregate ID có thể giúp giữ thứ tự trong partition. Tuy nhiên, retry và nhiều consumer vẫn cần xử lý duplicate/version.

## 9. Dead Letter Queue là gì?

Dead Letter Queue (DLQ) là nơi lưu những message hoặc item không thể xử lý thành công theo chính sách retry. DLQ giúp giữ lại dữ liệu lỗi để điều tra, sửa và replay sau này.

DLQ không phải một tính năng tự động của Elasticsearch Bulk API. Ứng dụng hoặc message infrastructure phải triển khai nơi lưu bền vững, ví dụ:

- Dead-letter topic của Kafka.
- Dead-letter queue của RabbitMQ.
- Queue lỗi riêng của hệ thống.
- Database table lưu payload lỗi.
- Object storage cho payload lớn kèm metadata trong database.

Elasticsearch có ingest pipeline và error response, nhưng không tự tạo một DLQ nghiệp vụ hoàn chỉnh cho event đồng bộ.

Một bản ghi DLQ nên chứa đủ thông tin để hiểu và replay:

| Trường | Mục đích |
|---|---|
| eventId | Định danh duy nhất để deduplicate |
| aggregateId/documentId | Document nghiệp vụ liên quan |
| eventType | Loại thay đổi |
| sourceVersion | Phiên bản dữ liệu nguồn |
| payload hoặc payload reference | Nội dung cần xử lý lại |
| targetIndex | Index đích tại thời điểm lỗi |
| routing | Routing nếu có |
| errorType/errorReason | Nguyên nhân thất bại |
| firstFailedAt/lastFailedAt | Thời điểm lỗi |
| attempts | Số lần đã thử |
| correlationId/traceId | Truy vết luồng xử lý |
| schemaVersion | Phiên bản schema của payload |
| status | NEW, INVESTIGATING, READY_TO_REPLAY, RESOLVED hoặc trạng thái tương đương |

Không lưu bí mật, token hoặc dữ liệu cá nhân không cần thiết vào DLQ. Cần có quyền truy cập, mã hóa, thời hạn lưu và quy trình xóa phù hợp.

## 10. Khi nào đưa message vào DLQ?

Không nên đưa mọi lỗi vào DLQ ngay lần đầu. Một chính sách thường dùng:

1. Lỗi transient: retry theo backoff.
2. Hết số lần retry: đưa vào DLQ hoặc retry topic có delay.
3. Lỗi permanent: đưa vào DLQ ngay, kèm error classification.
4. Lỗi cấu hình diện rộng: có thể pause consumer và cảnh báo thay vì đẩy hàng triệu message vào DLQ.

Ví dụ:

| Trường hợp | Hành động |
|---|---|
| 429 trong vài giây | Retry có backoff |
| Cluster mất kết nối ngắn hạn | Retry có giới hạn |
| Field price chứa chuỗi không parse được | DLQ để sửa payload |
| Mapping đổi nhưng consumer vẫn gửi schema cũ | Pause/alert hoặc DLQ có phân loại |
| Index đích bị xóa ngoài kế hoạch | Dừng hoặc pause luồng và cảnh báo |
| Event vượt schema version chưa hỗ trợ | DLQ hoặc giữ ở retry topic đến khi consumer được nâng cấp |

DLQ không nên trở thành nơi chứa mọi lỗi mà không có người theo dõi. Nếu không có alert, owner và quy trình replay, dữ liệu sẽ nằm đó vô thời hạn.

## 11. DLQ và retry topic khác nhau

Một retry topic có thể giữ message để thử lại sau một khoảng thời gian. DLQ thường chứa message đã hết chính sách retry hoặc không thể xử lý tự động.

| Thành phần | Mục tiêu |
|---|---|
| Main topic/queue | Giao event lần đầu |
| Retry topic/queue | Chờ rồi thử lại lỗi tạm thời |
| DLQ | Lưu message cần điều tra hoặc can thiệp |
| Replay worker | Đọc item đã sửa/được phê duyệt và gửi lại |

Một số hệ thống dùng nhiều retry topic với delay tăng dần. Một số hệ thống dùng scheduler và database retry table. Hãy chọn cơ chế phù hợp với broker, throughput và yêu cầu vận hành.

Không nên retry bằng cách giữ một thread consumer ngủ lâu. Việc đó có thể chiếm consumer slot, giảm throughput và làm ảnh hưởng các partition khác.

## 12. Thiết kế retry queue có delay

Một luồng có thể gồm:

    Main topic
        |
        v
    Consumer
        |
        +---- Success ----> Acknowledge
        |
        +---- Transient --> Retry topic (delay)
        |                       |
        |                       v
        |                    Consumer
        |
        +---- Permanent --> DLQ
        |
        +---- Retry limit --> DLQ

Retry message nên giữ event ID, source version, payload reference và số lần thử. Khi chuyển qua retry topic, không tạo event ID mới cho cùng một event nghiệp vụ.

Nếu dùng Kafka, có thể triển khai retry topic theo số lần thử hoặc dùng cơ chế retry/DLT của framework. Nếu dùng RabbitMQ, có thể dùng dead-letter exchange và TTL/delay pattern tùy broker/plugin. Các cấu hình cụ thể phụ thuộc hạ tầng; nguyên tắc chung là retry phải có delay, giới hạn và observability.

## 13. Acknowledge message khi nào?

Với message broker, thời điểm acknowledge ảnh hưởng đến khả năng mất hoặc lặp message.

Một nguyên tắc phổ biến là chỉ acknowledge sau khi:

- Elasticsearch ghi thành công tất cả item cần xử lý; hoặc
- Item lỗi đã được lưu bền vững vào retry queue/DLQ theo chính sách.

Nếu acknowledge trước khi ghi Elasticsearch và consumer chết sau đó, event có thể mất khỏi queue trong khi index chưa cập nhật.

Nếu ghi Elasticsearch thành công nhưng consumer chết trước khi acknowledge, broker có thể giao lại event. Vì vậy, consumer vẫn phải idempotent.

Nếu bulk có partial failure, không acknowledge toàn bộ message batch như thể mọi item đã thành công. Hãy tách item thành công và thất bại, hoặc đưa item lỗi vào nơi lưu bền vững trước khi xác nhận message nguồn.

## 14. Outbox pattern để tránh mất event

Một lỗi khó phát hiện xảy ra khi database commit thành công nhưng publish event thất bại:

    UPDATE products SET price = 120 WHERE id = 'p-100';
    COMMIT;
    publish(ProductUpdated);  // lỗi hoặc process dừng

Database đã có giá mới nhưng không có event để cập nhật Elasticsearch.

Outbox pattern giải quyết bằng cách ghi thay đổi nghiệp vụ và event vào cùng một transaction database:

    BEGIN;
      UPDATE products
      SET price = 120
      WHERE id = 'p-100';

      INSERT INTO outbox(
        event_id,
        aggregate_id,
        event_type,
        payload,
        created_at
      ) VALUES (...);
    COMMIT;

Một publisher đọc outbox và gửi event đến broker. Khi publish thành công, publisher đánh dấu record đã gửi hoặc lưu trạng thái tương ứng.

Outbox không loại bỏ duplicate: publisher có thể gửi event thành công rồi chết trước khi đánh dấu sent. Consumer vẫn cần idempotency.

Outbox giúp bảo đảm thay đổi nguồn và ý định phát event được lưu cùng transaction, giảm nguy cơ database đã đổi nhưng event bị mất.

## 15. Change Data Capture và đồng bộ

Ngoài outbox, hệ thống có thể dùng Change Data Capture (CDC) để đọc transaction log của database và phát thay đổi đến broker.

Luồng:

    Database transaction log
             |
             v
            CDC
             |
             v
        Message broker
             |
             v
      Elasticsearch consumer

CDC giúp giảm việc phải viết publisher riêng cho từng nghiệp vụ, nhưng vẫn cần:

- Xử lý schema evolution.
- Quản lý offset/checkpoint.
- Xử lý duplicate và thứ tự.
- Retry/DLQ.
- Reconciliation.
- Theo dõi độ trễ giữa source và index.

CDC không tự bảo đảm Elasticsearch luôn đồng bộ. Nó chỉ cung cấp một luồng thay đổi có thể được consumer xử lý.

## 16. Reconciliation là gì?

Reconciliation là quá trình đối chiếu dữ liệu trong Elasticsearch với nguồn dữ liệu có thẩm quyền để tìm sai lệch.

Các loại sai lệch thường gặp:

- Document tồn tại ở nguồn nhưng bị thiếu trong Elasticsearch.
- Document trong Elasticsearch có source cũ hơn.
- Document có field sai hoặc thiếu.
- Document đã bị xóa ở nguồn nhưng vẫn còn trong index.
- Document nằm sai index hoặc routing.
- Mapping/transform thay đổi khiến projection không còn đúng.

Retry xử lý những thao tác lỗi đã biết. Reconciliation tìm ra những sai lệch mà hệ thống có thể không biết đã xảy ra.

Nếu database là source of truth, reconciliation nên so sánh Elasticsearch với database hoặc một snapshot/stream đáng tin cậy. Không nên lấy chính index cần kiểm tra làm nguồn xác thực duy nhất.

## 17. Đối soát bằng ID và version

Một cách đơn giản là lưu source version trong mỗi document Elasticsearch:

    {
      "id": "p-100",
      "name": "Keyboard K8",
      "price": 120,
      "sourceVersion": 42,
      "updatedAt": "2026-11-13T10:00:00Z"
    }

Trong reconciliation:

1. Đọc ID và version từ nguồn.
2. Đọc document tương ứng trong Elasticsearch.
3. So sánh sourceVersion.
4. Nếu index thiếu hoặc version thấp hơn, phát sinh thao tác repair.
5. Nếu version index cao hơn nguồn, kiểm tra dữ liệu nguồn, sai thứ tự event hoặc ghi nhầm môi trường.

Không chỉ so timestamp nếu hệ thống có thể ghi timestamp lệch, độ chính xác thấp hoặc event đến không theo thứ tự. Version tăng đơn điệu theo aggregate thường dễ so sánh hơn.

Version phải được cập nhật cùng transaction nghiệp vụ ở source. Nếu version chỉ được tạo trong consumer, nó không thể cho biết event nào mới hơn ở nguồn.

## 18. Đối soát bằng checksum hoặc hash

Nếu chỉ so ID và version chưa đủ, có thể tính hash trên tập field quan trọng:

    sourceHash = hash(canonicalize(sourceProjection))
    indexHash  = hash(canonicalize(indexProjection))

Nếu hai hash khác nhau, document có thể bị thiếu field hoặc dữ liệu không khớp.

Canonicalization cần ổn định:

- Sắp xếp key object trước khi serialize.
- Chuẩn hóa kiểu số và ngày giờ.
- Loại field không ổn định như thời điểm ingest hoặc metadata kỹ thuật.
- Quy định rõ null, missing và default.
- Dùng cùng phiên bản projection logic.

Hash không thay thế kiểm tra version. Hash giúp phát hiện khác biệt payload, còn version giúp xác định thứ tự và trạng thái cập nhật.

Với tập dữ liệu lớn, không nhất thiết tải toàn bộ source và index về ứng dụng để so hash. Có thể dùng partition, batch, checksum theo nhóm hoặc lưu projection hash ở nguồn.

## 19. Đối soát document bị thiếu

Một quy trình đơn giản:

    Đọc batch ID từ nguồn
             |
             v
    Multi-get ID từ Elasticsearch
             |
             v
    So sánh tập ID
             |
             +---- Có đủ ----> So version/hash
             |
             +---- Thiếu ----> Tạo repair event
             |
             v
    Ghi repair result/checkpoint

Không nên gọi GET từng ID riêng lẻ nếu có hàng nghìn document. Dùng multi-get hoặc bulk read phù hợp để giảm request overhead.

Khi Elasticsearch trả document không tồn tại, cần phân biệt:

- ID thực sự bị thiếu.
- Routing sai khiến request đọc nhầm shard.
- Index/alias sai.
- Document đang được chuyển giữa index trong quá trình reindex.
- Quyền truy cập hoặc filter làm kết quả bị giới hạn.

Repair chỉ nên ghi lại document từ source of truth. Không tự tạo source mới bằng cách suy đoán từ dữ liệu search không đầy đủ.

## 20. Đối soát document đã bị xóa ở nguồn

Document bị xóa là trường hợp khó hơn vì khi đọc nguồn hiện tại, ID đã biến mất. Nếu không có tombstone hoặc change log, reconciliation không biết ID nào cần xóa khỏi Elasticsearch.

Các chiến lược:

- Lưu tombstone/event xóa trong outbox hoặc CDC.
- Giữ danh sách ID đã xóa theo thời gian.
- So sánh toàn bộ tập ID theo partition nếu quy mô cho phép.
- Dùng generation/snapshot và xây lại index từ nguồn.

Tombstone có thể chứa:

    {
      "eventId": "evt-900",
      "aggregateId": "p-100",
      "eventType": "ProductDeleted",
      "sourceVersion": 43,
      "deletedAt": "2026-11-13T10:05:00Z"
    }

Consumer dùng tombstone để xóa document hoặc ghi trạng thái deleted tùy chiến lược. Giữ version của tombstone giúp ngăn event cập nhật cũ đến muộn tạo lại document đã xóa.

## 21. Checkpoint cho reconciliation job

Reconciliation thường xử lý dữ liệu theo batch. Nếu job dừng giữa chừng, cần biết đã xử lý đến đâu.

Checkpoint có thể lưu:

- Partition hoặc tenant.
- ID cuối cùng đã đọc.
- Source watermark hoặc sequence.
- Thời điểm bắt đầu snapshot.
- Số record đã quét.
- Số document thiếu/cũ/sai.
- Trạng thái job.

Không nên chỉ lưu số trang nếu nguồn dữ liệu thay đổi liên tục và thứ tự phân trang không ổn định. Dùng cursor theo khóa tăng dần hoặc snapshot/watermark phù hợp.

Ví dụ:

    {
      "jobId": "reconcile-products-2026-11-13",
      "partition": "tenant-12",
      "lastProcessedId": "p-90000",
      "sourceWatermark": 8839201,
      "status": "RUNNING"
    }

Khi resume, đọc tiếp sau cursor đã commit. Chỉ cập nhật checkpoint sau khi mọi repair của batch đã được xử lý hoặc được ghi bền vững vào repair queue.

## 22. Reconciliation theo snapshot và theo delta

Có hai kiểu đối soát phổ biến:

### Full reconciliation

Quét toàn bộ dữ liệu nguồn và so sánh với index.

Ưu điểm:

- Có thể phát hiện sai lệch cũ không còn event.
- Hữu ích sau migration hoặc incident.

Nhược điểm:

- Tốn tài nguyên.
- Có thể kéo dài.
- Khó xác định document thừa trong index nếu không có tập ID nguồn đầy đủ.
- Dữ liệu thay đổi trong khi quét cần được xử lý bằng snapshot/watermark.

### Incremental reconciliation

Chỉ quét các record thay đổi sau một watermark hoặc trong một khoảng thời gian:

    updated_at > last_successful_watermark

Ưu điểm:

- Ít tốn tài nguyên.
- Có thể chạy thường xuyên.

Nhược điểm:

- Có thể bỏ sót nếu watermark, timestamp hoặc CDC offset sai.
- Cần overlap window để xử lý độ trễ và đồng hồ lệch.
- Không phát hiện được mọi sai lệch lịch sử nếu record không được đánh dấu thay đổi.

Thực tế thường kết hợp incremental reconciliation thường xuyên với full audit định kỳ hoặc sau sự cố lớn.

## 23. Watermark và overlap window

Nếu dùng updatedAt làm watermark, một job có thể lưu thời điểm hoàn tất gần nhất rồi truy vấn:

    updatedAt >= previousWatermark
    AND updatedAt < currentCutoff

Overlap window đọc lặp lại một khoảng thời gian trước watermark:

    updatedAt >= previousWatermark - overlap

Điều này giúp giảm nguy cơ bỏ sót do:

- Timestamp có độ chính xác thấp.
- Transaction commit muộn.
- Event đến trễ.
- Clock skew giữa các hệ thống.
- Job trước cập nhật checkpoint trước khi mọi event được xử lý.

Overlap tạo duplicate, vì vậy repair và consumer phải idempotent. Dùng source version để bỏ qua dữ liệu cũ hoặc đã được index.

Không dùng timestamp đơn lẻ làm thứ tự tuyệt đối nếu nhiều update có thể cùng timestamp. Có thể kết hợp timestamp với ID hoặc source sequence.

## 24. Đối soát dữ liệu lớn với PIT và search_after

Khi cần quét index Elasticsearch lớn, tránh deep pagination bằng from/size. PIT kết hợp search_after giúp đọc một snapshot ổn định theo cursor.

Luồng khái quát:

1. Mở PIT trên index cần kiểm tra.
2. Chạy search với sort ổn định và page size giới hạn.
3. Đọc hit stream và lấy sort values của hit cuối.
4. Gửi trang tiếp theo bằng search_after và PIT ID mới nhất.
5. Lặp đến khi hết hit.
6. Đóng PIT trong finally/cleanup path.

Ví dụ request:

    POST products/_search
    {
      "size": 500,
      "pit": {
        "id": "PIT_ID",
        "keep_alive": "2m"
      },
      "sort": [
        {
          "_shard_doc": "asc"
        }
      ]
    }

Trang kế tiếp thêm sort values của hit cuối:

    POST _search
    {
      "size": 500,
      "pit": {
        "id": "LATEST_PIT_ID",
        "keep_alive": "2m"
      },
      "sort": [
        {
          "_shard_doc": "asc"
        }
      ],
      "search_after": [
        12345
      ]
    }

Đây là ví dụ minh họa; sort values thực tế phải lấy nguyên vẹn từ hit cuối. PIT ID có thể được làm mới trong response, cần dùng ID mới nhất.

PIT snapshot chỉ giữ trạng thái index tại thời điểm snapshot. Nếu nguồn thay đổi trong lúc đối soát, hãy kết hợp source watermark và một lượt incremental repair sau snapshot.

## 25. Đối soát bằng composite aggregation

Nếu cần duyệt các bucket theo key thay vì document, composite aggregation hỗ trợ phân trang bucket qua after_key.

Ví dụ nhóm theo tenant:

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "by_tenant": {
          "composite": {
            "size": 500,
            "sources": [
              {
                "tenant": {
                  "terms": {
                    "field": "tenantId"
                  }
                }
              }
            ]
          }
        }
      }
    }

Response có after_key để request tiếp theo tiếp tục duyệt bucket. Composite phù hợp khi cần duyệt nhiều bucket theo key; nó không thay thế PIT/search_after cho việc đọc từng document.

Nếu reconciliation cần so sánh từng ID, hãy chọn cách duyệt document phù hợp. Nếu cần tổng hợp số lượng hoặc checksum theo tenant/category, composite aggregation có thể hữu ích.

## 26. Repair job phải idempotent

Reconciliation có thể phát hiện cùng một document thiếu ở nhiều lần chạy, hoặc repair request có thể timeout sau khi Elasticsearch đã ghi thành công. Vì vậy, repair operation cần idempotent.

Ví dụ repair bằng index theo ID ổn định:

    IndexRequest request = IndexRequest.of(i -> i
        .index("products")
        .id(sourceProduct.id())
        .document(sourceProduct)
    );

Gửi lại cùng source version và ID có thể tạo cùng trạng thái cuối nếu không có event mới hơn. Tuy nhiên, cần kiểm tra version để repair snapshot cũ không ghi đè dữ liệu mới vừa được consumer index.

Một cách an toàn:

- Đọc source version.
- So với version trong Elasticsearch.
- Chỉ ghi nếu source version mới hơn hoặc document đang thiếu.
- Dùng external version/conditional update nếu phù hợp.
- Ghi kết quả repair và checkpoint.

## 27. Spring Data Elasticsearch: xử lý bulk item failures

Spring Data Elasticsearch cung cấp ElasticsearchOperations để gửi bulk. API cụ thể và kiểu trả về thay đổi theo phiên bản. Một ví dụ imperative thường gặp:

    List<IndexQuery> queries = batch.stream()
        .map(product -> IndexQuery.builder()
            .withId(product.getId())
            .withObject(product)
            .build())
        .toList();

    List<IndexedObjectInformation> indexed =
        operations.bulkIndex(
            queries,
            BulkOptions.builder()
                .withRefreshPolicy(RefreshPolicy.NONE)
                .build(),
            IndexCoordinates.of("products")
        );

Kết quả trả về có thể cung cấp metadata cho các thao tác được index thành công. Với lỗi item, cách Spring Data biểu diễn exception/result phụ thuộc client integration và phiên bản. Nếu cần phân loại chi tiết từng lỗi, có thể dùng Elasticsearch Java API Client trực tiếp hoặc một adapter ở tầng persistence để giữ BulkResponse item details.

Không giả định bulkIndex luôn trả một result list chứa cả success và failure. Hãy đọc contract của method đang dùng và kiểm tra cách exception được ném khi bulk có item lỗi.

### Gửi bulk bằng Java API Client

Với Elasticsearch Java API Client, có thể nhận BulkResponse và duyệt items:

    BulkResponse response = client.bulk(request);

    for (BulkResponseItem item : response.items()) {
        if (item.error() == null) {
            markSucceeded(item.id());
        } else {
            classifyFailure(
                item.id(),
                item.status(),
                item.error().type(),
                item.error().reason()
            );
        }
    }

Đây là ví dụ khái quát. Request builder, kiểu item và cách truyền source phụ thuộc version client. Mục tiêu là giữ quan hệ giữa từng request item và response item để phân loại lỗi chính xác.

## 28. Retry trong service Spring

Có thể triển khai retry ở service bằng vòng lặp có backoff:

    public void indexWithRetry(Product product) {
        int maxAttempts = 5;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                operations.save(product);
                return;
            } catch (TransientDataAccessException ex) {
                if (attempt == maxAttempts) {
                    throw ex;
                }

                sleepWithBackoff(attempt);
            }
        }
    }

Đây là mã minh họa, không phải bộ phân loại exception đầy đủ. Không bắt mọi RuntimeException rồi retry. Hãy map lỗi Elasticsearch/client sang nhóm transient/permanent cụ thể.

Trong ứng dụng production, tránh tự viết sleep trong request thread nếu có thể. Với background worker, scheduler hoặc queue, hãy dùng delayed retry để giải phóng worker trong thời gian chờ.

## 29. Dùng Spring Retry hoặc Resilience4j

Spring Retry hoặc Resilience4j có thể cung cấp cơ chế retry/backoff/circuit breaker. Chúng là thư viện ở tầng ứng dụng, không thay thế việc phân tích item-level bulk errors.

Ví dụ minh họa annotation với Spring Retry:

    @Retryable(
        retryFor = TransientDataAccessException.class,
        maxAttempts = 4,
        backoff = @Backoff(
            delay = 200,
            multiplier = 2,
            maxDelay = 5000,
            random = true
        )
    )
    public Product save(Product product) {
        return operations.save(product);
    }

Chữ ký annotation và thuộc tính retryFor/value phụ thuộc phiên bản Spring Retry. Cần bật cấu hình retry theo thư viện đang dùng.

Lưu ý:

- Annotation retry chỉ có hiệu lực khi method đi qua proxy phù hợp.
- Self-invocation trong cùng bean có thể bỏ qua proxy.
- Retry method save không tự phân tích partial failures của bulk.
- Chỉ retry exception đã xác định là transient.
- Không retry thao tác không idempotent nếu không có deduplication.

## 30. Retry trong reactive pipeline

Với Reactor, có thể dùng retryWhen để retry lỗi tạm thời:

    Mono<Product> saved =
        reactiveOperations.save(product)
            .retryWhen(
                Retry.backoff(4, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(5))
                    .jitter(0.5)
                    .filter(this::isTransientFailure)
            );

isTransientFailure cần phân loại lỗi dựa trên exception thực tế. Không dùng retry() vô hạn cho mọi lỗi.

Với bulk reactive, nếu response chứa partial item failures nhưng Mono vẫn thành công, retryWhen không tự phát hiện item lỗi. Ứng dụng phải inspect response, tạo publisher chỉ cho item cần retry và chuyển item permanent sang DLQ.

Không dùng block trong reactive retry path. Không gọi subscribe riêng bên trong retry callback; compose toàn bộ publisher.

## 31. DLQ record trong ứng dụng

Một DTO có thể biểu diễn bản ghi lỗi:

    public record DeadLetterRecord(
        String eventId,
        String aggregateId,
        String eventType,
        long sourceVersion,
        String targetIndex,
        String errorType,
        String errorReason,
        int attempts,
        Instant firstFailedAt,
        Instant lastFailedAt,
        String payloadReference
    ) {}

Payload lớn hoặc có dữ liệu nhạy cảm có thể được lưu trong object storage/database riêng; DLQ chỉ giữ reference. Cần bảo đảm payload reference vẫn truy cập được trong suốt retention period.

Lưu DLQ phải bền vững trước khi acknowledge message nguồn. Nếu ghi DLQ thất bại, không được đánh dấu message đã xử lý xong theo chính sách at-least-once.

## 32. Replay DLQ an toàn

Replay là việc đưa message từ DLQ trở lại luồng xử lý sau khi nguyên nhân lỗi được khắc phục.

Quy trình:

1. Chọn một nhóm DLQ record theo error type, target index hoặc khoảng thời gian.
2. Xác định nguyên nhân và thay đổi cần thiết.
3. Kiểm tra payload/schema version.
4. Xác nhận source version vẫn còn hợp lệ.
5. Replay vào consumer hoặc repair worker.
6. Ghi lại replay attempt, người/tiến trình thực hiện và kết quả.
7. Đánh dấu RESOLVED chỉ sau khi Elasticsearch đã nhận trạng thái đúng.

Không replay hàng loạt trước khi sửa nguyên nhân gốc. Nếu mapping vẫn sai, replay sẽ tiếp tục thất bại và tạo tải lớn.

Replay cần idempotent. Nếu event cũ hơn document hiện tại, không được ghi đè trạng thái mới. Dùng source version hoặc đọc lại source of truth trước khi index.

## 33. Tránh DLQ replay gây duplicate hoặc đảo thứ tự

Giả sử DLQ chứa event version 10, trong khi Elasticsearch đã có version 12. Replay version 10 có thể làm dữ liệu lùi nếu consumer không kiểm tra version.

Trước replay:

- Đọc source of truth hiện tại hoặc kiểm tra source version.
- Bỏ qua event đã cũ nếu document index đã ở version mới hơn.
- Nếu cần rebuild trạng thái, tạo projection từ source hiện tại thay vì phát lại từng event lịch sử.
- Giữ event ID để deduplicate.

Với event mang side effect như cộng số lượng, gửi thông báo hoặc phát thanh toán, không được replay tùy tiện. Cần phân biệt đồng bộ search projection với side effect nghiệp vụ.

## 34. Reconciliation theo source of truth

Một job reconciliation đáng tin cậy cần biết nguồn nào là authoritative. Ví dụ:

- Database là nguồn chính cho product.
- Elasticsearch là projection để tìm kiếm.
- Cache là lớp tăng tốc có thể được rebuild.

Khi có sai lệch:

    Database product version 42
    Elasticsearch product version 40

Job nên lấy dữ liệu hiện tại từ database và cập nhật Elasticsearch lên version 42. Không nên lấy version 40 trong Elasticsearch rồi cố suy ra hai event đã bị thiếu.

Nếu source of truth không còn lưu record đã xóa, cần tombstone/change log hoặc snapshot ID để phát hiện document thừa trong index.

## 35. Reconciliation với Spring Data và multi-get

Có thể đọc dữ liệu nguồn theo batch, rồi dùng ElasticsearchOperations hoặc Java API Client để lấy document theo ID.

Ví dụ ý tưởng:

    List<Product> sourceBatch = sourceRepository
        .findNextBatch(checkpoint, 500);

    List<String> ids = sourceBatch.stream()
        .map(Product::getId)
        .toList();

    // Dùng multi-get hoặc query theo IDs để đọc projection.
    // So sánh version/hash rồi tạo repair IndexQuery cho document thiếu/cũ.

Không dùng repository.findById trong vòng lặp nếu batch có hàng trăm hoặc hàng nghìn ID; đó là N+1 request.

Với Spring Data, có thể dùng multiGet hoặc NativeQuery với terms theo ID tùy phiên bản và yêu cầu mapping. Với lượng ID lớn, chia thành batch nhỏ để tránh terms query quá lớn.

## 36. Repair document bị thiếu bằng bulk

Sau khi xác định document thiếu hoặc cũ, tạo repair batch:

    List<IndexQuery> repairs = outdatedProducts.stream()
        .map(product -> IndexQuery.builder()
            .withId(product.getId())
            .withObject(product)
            .build())
        .toList();

    operations.bulkIndex(
        repairs,
        BulkOptions.builder()
            .withRefreshPolicy(RefreshPolicy.NONE)
            .build(),
        IndexCoordinates.of("products")
    );

Sau repair, kiểm tra kết quả từng item và chỉ cập nhật checkpoint khi batch đã được xử lý hoặc lỗi đã được ghi bền vững vào DLQ/repair queue.

Nếu cần search thấy dữ liệu ngay sau reconciliation, refresh một lần sau khi batch/job hoàn tất. Không refresh sau từng document.

## 37. Đối soát dữ liệu xóa bằng tombstone

Khi nguồn phát tombstone, consumer có thể xóa document trong Elasticsearch:

    DeleteQuery delete = DeleteQuery.builder(productId)
        .build();

    operations.delete(delete, IndexCoordinates.of("products"));

API builder cụ thể phụ thuộc Spring Data version. Với custom routing, cần đưa routing vào delete request.

Nếu delete event version 43 đến trước update event version 42, consumer phải ngăn event cũ tạo lại document. Có thể giữ tombstone version trong một store hoặc dùng versioning/conditional operation phù hợp.

Nếu xóa document hoàn toàn, metadata version của tombstone có thể mất cùng document. Với event đến trễ, cần một nơi lưu version xóa hoặc cơ chế source-of-truth check để không resurrect dữ liệu đã xóa.

## 38. Đo lường sức khỏe đồng bộ

Một pipeline sync nên có các metric và alert:

| Metric | Điều cần phát hiện |
|---|---|
| Consumer lag | Event đang chờ xử lý lâu |
| Retry count/rate | Lỗi tạm thời tăng |
| DLQ size | Số item không xử lý được |
| Oldest DLQ age | Lỗi tồn đọng lâu chưa được xử lý |
| Bulk item failure rate | Mapping, overload hoặc dữ liệu lỗi |
| 429/rejected count | Cluster chịu áp lực |
| Indexing latency | Ghi Elasticsearch chậm |
| Source-to-index lag | Search projection chậm hơn nguồn |
| Reconciliation mismatch count | Số document thiếu/cũ/sai |
| Repair success/failure rate | Khả năng khắc phục sai lệch |
| Last successful checkpoint | Job đối soát có tiến triển không |

Không chỉ theo dõi số lượng DLQ. Một DLQ nhỏ nhưng record cũ nhiều tháng vẫn là vấn đề. Theo dõi tuổi của record lỗi và có owner xử lý.

## 39. Cảnh báo và vận hành DLQ

Quy trình vận hành cần trả lời:

- Ai chịu trách nhiệm cho từng loại lỗi?
- Bao lâu phải xử lý record mới trong DLQ?
- Khi nào pause consumer?
- Khi nào sửa payload và replay?
- Khi nào phải rebuild index thay vì replay từng event?
- Ai được quyền truy cập payload lỗi?
- Payload được giữ bao lâu?
- Làm sao xác nhận replay đã sửa đúng dữ liệu?

Có thể phân loại DLQ theo error type và schema version để nhóm lỗi cùng nguyên nhân. Dashboard nên hiển thị số lượng, tuổi, top error reason và trạng thái replay.

Nếu một lỗi mapping ảnh hưởng toàn bộ consumer, pause hoặc giảm tốc có thể tốt hơn việc tiếp tục đẩy mọi event vào DLQ. Cần có circuit breaker hoặc health gate cho lỗi cấu hình diện rộng.

## 40. Reconciliation không thay thế event-driven sync

Chạy reconciliation toàn bộ sau mỗi thay đổi là tốn kém. Event-driven sync giúp cập nhật nhanh; reconciliation là lớp kiểm tra và sửa sai lệch.

Một thiết kế cân bằng:

- Outbox/CDC phát thay đổi gần real-time.
- Consumer ghi Elasticsearch và retry lỗi transient.
- DLQ lưu item không xử lý được.
- Incremental reconciliation chạy định kỳ để kiểm tra watermark/version.
- Full reconciliation hoặc rebuild chạy sau incident, migration hoặc thay đổi projection lớn.

Nếu reconciliation phát hiện quá nhiều mismatch, cần điều tra pipeline sync thay vì chỉ tăng tần suất repair. Sai lệch hàng loạt thường là dấu hiệu của bug, mapping drift hoặc event loss.

## 41. Khi nào nên rebuild toàn bộ index?

Một số tình huống sửa từng document không còn hiệu quả:

- Mapping hoặc analyzer thay đổi lớn.
- Projection logic cũ đã tạo dữ liệu sai trên diện rộng.
- Event history bị thiếu và không thể khôi phục từng thay đổi.
- Index bị hỏng về cấu trúc hoặc không còn tin cậy.

Quy trình rebuild thường:

1. Tạo index mới với mapping/settings đúng.
2. Đọc snapshot dữ liệu từ source of truth.
3. Bulk index theo batch có kiểm soát.
4. Đồng bộ các thay đổi phát sinh trong khi snapshot chạy bằng outbox/CDC hoặc watermark.
5. Đối soát số lượng, version và mẫu dữ liệu.
6. Chuyển alias sang index mới.
7. Giữ index cũ trong khoảng rollback theo chính sách.

Không xóa index cũ trước khi index mới được xác minh và alias chuyển thành công.

## 42. Xử lý schema evolution

Event cũ có thể được tạo bởi schema version trước. Khi consumer mới nhận event cũ, field có thể thiếu hoặc có kiểu khác.

Payload nên mang schemaVersion hoặc eventVersion. Consumer có thể:

- Hỗ trợ nhiều phiên bản schema.
- Chuyển payload cũ sang model nội bộ hiện tại.
- Đưa version không hỗ trợ vào DLQ.
- Giữ raw payload để replay sau khi triển khai converter.

Không sửa raw event trong DLQ mà không lưu lại bản gốc hoặc audit trail. Nếu cần transform, ghi nhận phiên bản converter và replay attempt.

Mapping Elasticsearch cũng cần tiến hóa có kiểm soát. Thay đổi field type thường cần index mới và reindex, không thể chỉ retry event cũ để sửa mapping.

## 43. Bulk retry và giới hạn tài nguyên

Retry có thể làm tăng tải nếu batch quá lớn hoặc quá nhiều worker chạy đồng thời. Khi cluster trả 429:

- Giảm concurrency.
- Giảm batch size nếu payload lớn.
- Tăng backoff.
- Tạm dừng producer nếu queue tăng nhanh.
- Theo dõi indexing pressure và write thread pool.

Không tăng số lần retry để che giấu cluster quá tải. Retry phải giúp hệ thống phục hồi, không kéo dài tình trạng overload.

Nếu một batch có item lỗi, tạo retry batch nhỏ chỉ gồm item transient. Điều này giúp giảm chi phí và tránh gửi lại item permanent.

## 44. Exactly-once và thực tế của đồng bộ

Trong một hệ thống gồm database, broker và Elasticsearch, rất khó có một transaction atomic bao trùm tất cả thành phần. Vì vậy, nhiều kiến trúc chọn at-least-once delivery cùng idempotent consumer.

At-least-once có thể giao lặp event, nhưng không chủ ý bỏ mất event đã được commit vào outbox/broker. Consumer xử lý lặp an toàn bằng event ID, source version và thao tác idempotent.

Không nên tuyên bố pipeline là exactly-once chỉ vì broker hỗ trợ transaction trong phạm vi riêng của nó. Transaction broker không tự tạo transaction chung với database và Elasticsearch.

Một mục tiêu thực tế hơn:

- Không mất thay đổi đã commit ở source.
- Event có thể giao lại.
- Consumer có thể xử lý duplicate.
- Lỗi được lưu bền vững.
- Reconciliation phát hiện sai lệch còn sót.
- Có thể replay hoặc rebuild để khôi phục projection.

## 45. Ví dụ kiến trúc đồng bộ hoàn chỉnh

    [Application Service]
             |
             v
    [Database Transaction]
       |             |
       |             +--> [Outbox Event]
       |                       |
       v                       v
    [Source Tables]        [Publisher]
                               |
                               v
                         [Message Broker]
                               |
                               v
                         [Sync Consumer]
                               |
                       +-------+-------+
                       |               |
                       v               v
                [Bulk Index]     [Failure Classifier]
                       |               |
                       v          +----+----+
                [Elasticsearch]   |         |
                                  v         v
                             [Retry]      [DLQ]
                                  |
                                  v
                             [Replay]

    [Reconciliation Job]
             |
             +---- Read source snapshot/watermark
             |
             +---- Compare IDs, versions, hashes
             |
             +---- Create repair events
             |
             +---- Update checkpoint

Kiến trúc này có nhiều thành phần, nhưng mỗi thành phần có trách nhiệm rõ:

- Database/outbox giữ thay đổi nguồn và ý định phát event.
- Broker vận chuyển event.
- Consumer chuyển event thành thao tác index.
- Retry xử lý lỗi tạm thời.
- DLQ lưu lỗi cần điều tra.
- Replay khôi phục những item đã sửa.
- Reconciliation phát hiện sai lệch còn sót.

## 46. Những lỗi thường gặp

### Retry mọi exception

Lỗi mapping, quyền hoặc cấu hình không tự hết. Phân loại transient và permanent trước khi retry.

### Retry vô hạn

Retry vô hạn tạo backlog và retry storm. Đặt max attempts, max delay, jitter và DLQ.

### Retry cả bulk khi chỉ một item lỗi

Gây ghi lặp và tăng tải. Tách item thất bại nếu response có đủ chi tiết.

### Không kiểm tra partial failure

HTTP 200 không đồng nghĩa mọi bulk item thành công. Đọc errors và item response.

### Không có idempotency

Message có thể được giao lại. Dùng ID ổn định, event ID, source version hoặc conditional update.

### Event đến sai thứ tự ghi đè dữ liệu mới

So source version hoặc giữ thứ tự theo aggregate. Không để event cũ ghi lùi projection.

### Acknowledge trước khi lưu bền vững kết quả

Consumer chết sau acknowledge có thể làm event mất. Chỉ acknowledge sau success hoặc sau khi lỗi đã được ghi vào retry/DLQ.

### DLQ không có người theo dõi

DLQ tăng mà không có alert và replay workflow sẽ trở thành nơi chôn dữ liệu. Theo dõi age, owner và trạng thái.

### Replay khi nguyên nhân gốc chưa được sửa

Replay sẽ tiếp tục thất bại và gây tải. Sửa mapping/config/payload trước.

### Replay event cũ hơn dữ liệu hiện tại

Có thể ghi lùi source. Kiểm tra source version và trạng thái hiện tại trước replay.

### Không có tombstone cho delete

Document đã xóa khỏi nguồn có thể tồn tại mãi trong index. Lưu event xóa hoặc cơ chế phát hiện ID thừa.

### Reconciliation không có checkpoint

Job dừng giữa chừng phải quét lại từ đầu hoặc có thể bỏ sót. Lưu cursor/watermark sau khi batch được xử lý an toàn.

### Chỉ đối soát theo timestamp

Clock skew và timestamp trùng có thể làm bỏ sót. Dùng version/sequence, overlap window và idempotent repair.

### Chỉ kiểm tra số lượng document

Số lượng bằng nhau không có nghĩa nội dung đúng. So ID, version và hash trên field quan trọng.

### Dùng Elasticsearch làm nguồn xác thực của chính nó

Reconciliation cần so với source of truth hoặc snapshot độc lập. Không thể xác nhận dữ liệu bị thiếu chỉ bằng index đang kiểm tra.

### Ghi log payload nhạy cảm vào DLQ

DLQ cần retention, access control và bảo vệ dữ liệu. Lưu reference nếu payload lớn hoặc nhạy cảm.

## 47. Quy trình thiết kế retry, DLQ và reconciliation

Khi xây dựng pipeline đồng bộ, có thể thực hiện theo thứ tự:

1. Xác định source of truth và document projection trong Elasticsearch.
2. Xác định event ID, aggregate ID và source version.
3. Dùng outbox hoặc CDC để tránh mất thay đổi giữa database và broker.
4. Thiết kế consumer idempotent và có kiểm tra thứ tự/version.
5. Gửi bulk theo batch phù hợp và kiểm tra kết quả từng item.
6. Phân loại transient/permanent dựa trên status và error type.
7. Retry transient với exponential backoff, jitter và giới hạn.
8. Đưa lỗi permanent hoặc hết retry vào DLQ có metadata đầy đủ.
9. Chỉ acknowledge sau success hoặc sau khi lỗi được lưu bền vững.
10. Xây dựng replay có kiểm tra version và idempotency.
11. Chạy incremental reconciliation theo watermark/overlap.
12. Chạy full reconciliation hoặc rebuild khi cần.
13. Dùng PIT/search_after hoặc cursor ổn định khi quét index lớn.
14. Lưu checkpoint sau khi batch đã được xử lý hoặc repair đã được ghi bền vững.
15. Theo dõi consumer lag, retry, DLQ age, mismatch và repair rate.

## Kết luận

Retry, DLQ và reconciliation giải quyết ba phần bổ sung của một pipeline đồng bộ. Retry xử lý lỗi tạm thời bằng backoff, jitter và giới hạn; DLQ giữ các item không thể xử lý để điều tra và replay; reconciliation đối chiếu Elasticsearch với source of truth để tìm document thiếu, cũ, sai hoặc còn tồn tại sau khi nguồn đã xóa.

Bulk API có partial failure nên phải kiểm tra từng item và chỉ retry phần thất bại khi có đủ thông tin. Retry an toàn đòi hỏi idempotency và kiểm soát thứ tự bằng event ID/source version. Outbox hoặc CDC giúp giảm nguy cơ mất event, nhưng consumer vẫn cần chịu duplicate và DLQ phải có quy trình vận hành. Reconciliation nên có checkpoint, watermark/overlap, so sánh ID/version/hash và repair idempotent. Với dữ liệu lớn, dùng PIT/search_after hoặc composite aggregation theo loại dữ liệu cần duyệt. Thiết kế theo hướng at-least-once cùng khả năng phát hiện và sửa sai lệch thường thực tế hơn việc giả định một transaction exactly-once xuyên qua database, broker và Elasticsearch.

# Xử lý sự kiện trùng, đến muộn và sai thứ tự

Trong một hệ thống đồng bộ dữ liệu, event có thể được gửi nhiều lần, đến sau một event mới hơn hoặc đến không theo thứ tự mà nguồn đã tạo ra. Đây là hành vi bình thường của các pipeline dùng message broker, CDC, transactional outbox hoặc consumer có retry. Nếu projector ghi mọi event vào Elasticsearch theo thứ tự nhận được, document có thể bị lùi về trạng thái cũ, một lần tăng số lượng có thể bị áp dụng hai lần hoặc document đã xóa có thể xuất hiện trở lại.

Một pipeline đáng tin cậy cần xác định trạng thái nào mới hơn bằng metadata do nguồn dữ liệu cấp, thiết kế thao tác ghi idempotent và có chính sách riêng cho event trùng, event đến muộn, event sai thứ tự, event thiếu và event lỗi không thể phục hồi.

Các nguyên tắc chính:

- Dùng event ID để nhận diện một lần phát sinh nghiệp vụ.
- Dùng aggregate version hoặc sequence đơn điệu để xác định thứ tự thay đổi của cùng một đối tượng.
- Giữ thứ tự event theo aggregate khi event mang delta phụ thuộc nhau.
- Dùng full-state event hoặc source version guard để chống event cũ ghi đè event mới.
- Biểu diễn delete bằng tombstone có version khi cần chống document sống lại.
- Chỉ xác nhận offset/checkpoint sau khi Elasticsearch đã xử lý event hoặc event đã được chuyển sang trạng thái lỗi bền vững.
- Retry có giới hạn, phân loại lỗi và giữ nguyên metadata gốc khi replay.

## 1. Vì sao event có thể trùng, đến muộn hoặc sai thứ tự?

Một luồng đồng bộ thường có nhiều thành phần:

~~~text
Application / Database
          |
          v
    Outbox hoặc CDC
          |
          v
    Message broker
          |
          v
       Consumer
          |
          v
    Elasticsearch
~~~

Mỗi chặng đều có thể phát sinh tình huống khiến event bị giao lại hoặc đến khác thứ tự.

### 1.1. Event trùng

Event trùng xảy ra khi cùng một sự kiện được xử lý nhiều lần. Ví dụ:

1. Consumer nhận event E-100.
2. Consumer ghi document vào Elasticsearch thành công.
3. Process dừng trước khi commit offset.
4. Broker giao lại E-100.
5. Consumer ghi E-100 lần nữa.

Đây là hệ quả thường gặp của at-least-once delivery. Broker bảo đảm event được giao lại khi chưa xác nhận, nhưng không tự bảo đảm side effect ở Elasticsearch chỉ xảy ra đúng một lần.

Event trùng cũng có thể xuất hiện khi:

- Publisher retry vì timeout nhưng lần publish trước đã thành công.
- Outbox relay đọc lại một hàng chưa được đánh dấu published.
- CDC connector phục hồi từ offset cũ.
- Consumer xử lý thành công nhưng commit offset thất bại.
- Hệ thống replay một khoảng event để khôi phục index.

### 1.2. Event đến muộn

Event đến muộn là event được tạo trước một event khác nhưng đến consumer sau event mới hơn.

Ví dụ:

~~~text
Nguồn tạo:
  E-10: đổi giá thành 100
  E-11: đổi giá thành 120

Consumer nhận:
  E-11 trước
  E-10 sau
~~~

Nếu consumer ghi theo thứ tự nhận, giá có thể quay từ 120 về 100. Thời điểm nhận event không thể được dùng làm căn cứ duy nhất để xác định trạng thái mới nhất.

### 1.3. Event sai thứ tự

Sai thứ tự thường xuất hiện khi:

- Một aggregate được xử lý bởi nhiều consumer song song.
- Các event của cùng aggregate được gửi vào nhiều partition.
- Consumer xử lý bất đồng bộ và hoàn tất request Elasticsearch không theo thứ tự nhận.
- Retry event cũ diễn ra trong khi event mới đã được xử lý.
- Nhiều publisher phát event cho cùng aggregate.
- Một event bị retry lâu hơn các event phía sau.

Sai thứ tự đặc biệt nguy hiểm với delta event, vì mỗi event chỉ chứa phần thay đổi và phụ thuộc trạng thái do event trước tạo ra.

## 2. Phân biệt event ID, aggregate ID và version

Ba trường này giải quyết ba vấn đề khác nhau.

| Trường | Vai trò | Ví dụ |
| --- | --- | --- |
| eventId | Nhận diện một sự kiện cụ thể để deduplicate | evt-90001 |
| aggregateId | Xác định đối tượng nghiệp vụ bị thay đổi | P-100 |
| aggregateVersion | Xác định thứ tự trạng thái của đối tượng | 42 |

Ví dụ event:

~~~json
{
  "eventId": "evt-90001",
  "eventType": "ProductPriceChanged",
  "aggregateType": "Product",
  "aggregateId": "P-100",
  "aggregateVersion": 42,
  "occurredAt": "2026-11-13T10:15:00Z",
  "payload": {
    "productId": "P-100",
    "price": 120
  }
}
~~~

Ý nghĩa:

- eventId giúp nhận ra cùng một event được giao lại.
- aggregateId cho biết document nào trong Elasticsearch cần cập nhật.
- aggregateVersion cho biết trạng thái nào mới hơn trong lịch sử của Product P-100.
- occurredAt hữu ích cho audit và quan sát, nhưng không thay thế version nếu cần thứ tự chính xác.

Không dùng eventId thay cho aggregateVersion. Một UUID có thể phân biệt hai event nhưng không cho biết event nào mới hơn.

Không dùng aggregateId thay cho eventId. Một aggregate có thể phát sinh hàng nghìn event trong vòng đời.

## 3. At-least-once delivery và idempotency

Nhiều hệ thống message broker và CDC ưu tiên at-least-once delivery. Consumer có thể nhận một event nhiều lần, nhưng nếu được cấu hình đúng thì event chưa xác nhận sẽ được giao lại sau lỗi.

Điều này phù hợp với đồng bộ dữ liệu nếu thao tác projection idempotent.

### 3.1. Idempotent nghĩa là gì?

Một thao tác idempotent có thể được thực hiện nhiều lần mà trạng thái cuối cùng vẫn giống như thực hiện một lần.

Ví dụ phép gán:

~~~text
set product.price = 120
~~~

Ghi cùng giá 120 nhiều lần không làm giá tăng thêm.

Ngược lại, phép cộng:

~~~text
product.viewCount = product.viewCount + 1
~~~

không idempotent. Nếu event bị giao hai lần, viewCount tăng hai lần.

### 3.2. Ưu tiên full-state projection

Event mang toàn bộ trạng thái document sau thay đổi thường dễ xử lý lặp hơn event chỉ mang delta.

Full-state event:

~~~json
{
  "eventId": "evt-90011",
  "aggregateId": "P-100",
  "aggregateVersion": 43,
  "operation": "UPSERT",
  "payload": {
    "id": "P-100",
    "name": "Mechanical Keyboard",
    "price": 120,
    "available": true
  }
}
~~~

Consumer có thể index lại cùng document ID với trạng thái đó. Nếu event được giao lại, thao tác ghi vẫn hướng đến cùng document và cùng dữ liệu.

Delta event:

~~~json
{
  "eventId": "evt-90012",
  "aggregateId": "P-100",
  "aggregateVersion": 44,
  "operation": "INCREMENT_STOCK",
  "payload": {
    "amount": 5
  }
}
~~~

Nếu consumer áp dụng phép cộng nhiều lần, tồn kho bị tăng sai. Delta event cần deduplication bền vững và thứ tự xử lý nghiêm ngặt, hoặc phải tính lại trạng thái từ nguồn chuẩn.

### 3.3. Dùng document ID ổn định

Khi projection một aggregate, dùng aggregate ID làm Elasticsearch document ID:

~~~text
_index = products
_id    = P-100
~~~

Không tạo ID ngẫu nhiên mỗi lần nhận event. Nếu ID thay đổi, một event giao lặp có thể tạo thêm document trùng thay vì ghi lại cùng document.

## 4. Deduplication bằng event ID

Event ID là khóa nhận diện sự kiện. Consumer có thể lưu event ID đã xử lý trong một bảng hoặc kho deduplication.

Ví dụ bảng:

| event_id | aggregate_id | processed_at | result |
| --- | --- | --- | --- |
| evt-90001 | P-100 | 10:15:01 | APPLIED |
| evt-90002 | P-100 | 10:15:03 | APPLIED |

Khi nhận event:

1. Kiểm tra eventId đã được xử lý chưa.
2. Nếu đã xử lý, bỏ qua side effect và xác nhận event.
3. Nếu chưa, thực hiện projection.
4. Chỉ đánh dấu processed sau khi projection đã thành công hoặc đã được xử lý theo chính sách bền vững.

### 4.1. Pseudocode deduplication

~~~java
public void handle(ProductEvent event) {
    if (processedEventStore.exists(event.eventId())) {
        acknowledge(event);
        return;
    }

    projector.apply(event);
    processedEventStore.markProcessed(event.eventId());
    acknowledge(event);
}
~~~

Đây là mô hình khái niệm. Nó vẫn có một khoảng lỗi quan trọng: Elasticsearch có thể ghi thành công nhưng process crash trước khi markProcessed. Event sẽ được giao lại. Vì vậy, deduplication ledger không thay thế idempotency ở thao tác ghi đích.

### 4.2. Vì sao không đánh dấu processed trước khi ghi Elasticsearch?

Nếu đánh dấu processed trước:

1. Consumer lưu eventId vào dedup store.
2. Process crash trước khi ghi Elasticsearch.
3. Broker giao lại event.
4. Consumer thấy eventId đã processed và bỏ qua.
5. Document không bao giờ được cập nhật.

Đây là mất dữ liệu.

### 4.3. Vì sao ghi Elasticsearch trước rồi mới đánh dấu processed?

Nếu ghi Elasticsearch trước:

1. Consumer ghi document thành công.
2. Process crash trước khi markProcessed.
3. Event được giao lại.
4. Consumer ghi document lần nữa.

Với full-state upsert có ID ổn định và version guard, lần ghi lại có thể an toàn. Với delta operation không idempotent, side effect có thể bị lặp.

Không có transaction ACID chung giữa database dedup store, message broker và Elasticsearch trong mô hình thông thường. Thiết kế nên dựa vào at-least-once delivery cùng projection idempotent thay vì giả định có exactly-once end-to-end.

### 4.4. Dedup store cần retention

Không thể giữ mọi event ID vô hạn trong một bảng mà không có chính sách dọn dẹp.

Retention phải dài hơn:

- Thời gian broker có thể replay event.
- Thời gian consumer có thể retry.
- Cửa sổ phục hồi sau sự cố.
- Thời gian bootstrap hoặc rebuild projection.
- Thời gian vận hành cho phép replay thủ công.

Nếu dùng aggregateVersion và full-state projection để chặn event cũ, có thể giảm phụ thuộc vào event ID ledger cho trạng thái cuối của document. Event ID vẫn hữu ích cho audit, phát hiện duplicate và side effect không idempotent.

## 5. Dùng aggregate version để chống event cũ

Aggregate version là số tăng theo mỗi thay đổi trạng thái của một aggregate.

Ví dụ:

~~~text
Product P-100:
  version 40: tạo sản phẩm
  version 41: đổi tên
  version 42: đổi giá
  version 43: đổi trạng thái tồn kho
~~~

Consumer có thể lưu version mới nhất trong document:

~~~json
{
  "id": "P-100",
  "name": "Mechanical Keyboard",
  "price": 120,
  "available": true,
  "sourceVersion": 43
}
~~~

Quy tắc:

- Incoming version lớn hơn stored version: có thể áp dụng.
- Incoming version nhỏ hơn stored version: event đã cũ, bỏ qua.
- Incoming version bằng stored version: có thể là duplicate; kiểm tra semantics của event và payload.

### 5.1. So sánh version

~~~text
Stored version = 43

Incoming version 42 -> STALE, không ghi
Incoming version 43 -> DUPLICATE hoặc CONFLICT
Incoming version 44 -> APPLY
~~~

Version phải do nguồn dữ liệu chuẩn cấp và tăng theo aggregate. Không tự tăng version trong Elasticsearch consumer vì nhiều consumer có thể xử lý cùng lúc và tạo thứ tự không nhất quán.

### 5.2. Version nghiệp vụ khác Elasticsearch _version

Elasticsearch có metadata nội bộ như _version, _seq_no và _primary_term để quản lý concurrency trong index.

Các giá trị đó không tự động là version của nguồn dữ liệu:

- _version do Elasticsearch quản lý cho document tại index đó.
- _seq_no và _primary_term hỗ trợ optimistic concurrency trong shard.
- aggregateVersion/sourceVersion do hệ thống nguồn quản lý thứ tự thay đổi nghiệp vụ.

Khi rebuild index mới, Elasticsearch _version có thể bắt đầu lại. Vì vậy, nếu cần chống event cũ xuyên suốt các lần rebuild, hãy lưu sourceVersion hoặc truyền nó qua external versioning.

## 6. External versioning của Elasticsearch

Elasticsearch hỗ trợ versioning do client cung cấp cho Index API và bulk index operation.

Hai chế độ thường cần phân biệt:

| Version type | Điều kiện chấp nhận |
| --- | --- |
| external | Incoming version phải lớn hơn version đang lưu |
| external_gte | Incoming version phải lớn hơn hoặc bằng version đang lưu |

### 6.1. Ví dụ bulk request

Giả sử sourceVersion của Product P-100 là 42:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{ "index": { "_index": "products", "_id": "P-100", "version": 42, "version_type": "external" } }
{ "id": "P-100", "name": "Mechanical Keyboard", "price": 120, "sourceVersion": 42 }
~~~

Nếu document hiện tại có external version 43, operation version 42 sẽ bị từ chối thay vì ghi đè trạng thái mới.

### 6.2. external hay external_gte?

Với external:

- Version 43 được chấp nhận khi stored version là 42.
- Version 43 bị từ chối nếu stored version đã là 43.
- Duplicate cùng version thường nhận version conflict.

Với external_gte:

- Version 43 được chấp nhận nếu stored version là 42.
- Version 43 cũng được chấp nhận nếu stored version đã là 43.
- Duplicate cùng version có thể ghi lại cùng trạng thái.

Chỉ dùng external_gte nếu bảo đảm cùng một aggregate version luôn đại diện cho cùng một payload trạng thái. Nếu hai event khác nội dung nhưng dùng cùng version, event đến sau có thể ghi đè event trước.

### 6.3. Xử lý 409 do stale event

Khi dùng external versioning, một event cũ có thể nhận 409 version conflict. Đây có thể là kết quả mong đợi khi document đã có version mới hơn.

Không retry vô hạn cùng event cũ. Hãy phân loại:

- Stored version lớn hơn incoming version: stale event, ghi nhận đã bỏ qua.
- Stored version bằng incoming version: duplicate hoặc xung đột dữ liệu; cần xác định payload có giống nhau không.
- Stored version nhỏ hơn incoming version nhưng vẫn có conflict: kiểm tra race giữa writer, version type và index state.

Một lỗi 409 khác có thể do optimistic concurrency hoặc create conflict. Cần đọc error type và context thay vì coi mọi 409 là duplicate.

## 7. Dùng optimistic concurrency khi nhiều writer cùng cập nhật

Elasticsearch hỗ trợ optimistic concurrency control bằng cặp _seq_no và _primary_term.

Ví dụ:

1. Consumer đọc document với seq_no 10 và primary_term 3.
2. Consumer tính trạng thái mới.
3. Consumer ghi update yêu cầu if_seq_no=10 và if_primary_term=3.
4. Nếu writer khác đã thay đổi document, request bị từ chối.
5. Consumer đọc lại và quyết định tính toán lại.

Đây là cơ chế bảo vệ ghi đồng thời trong Elasticsearch.

### 7.1. Optimistic concurrency khác ordering của nguồn

_seq_no và _primary_term ngăn ghi đè do hai writer cùng đọc một phiên bản document, nhưng không tự biết event nào mới hơn theo nghiệp vụ.

Ví dụ event version 10 đến sau event version 11. Nếu consumer đọc document hiện tại rồi dùng optimistic concurrency đúng, nó vẫn có thể cố tình ghi trạng thái version 10 lên version 11 vì thao tác đó hợp lệ theo seq_no hiện tại.

Do đó:

- Source version giải quyết thứ tự nghiệp vụ.
- Elasticsearch seq_no/primary_term giải quyết race giữa các lần ghi dựa trên trạng thái đã đọc.
- Hai cơ chế có thể kết hợp nếu hệ thống cần cả hai.

## 8. Xử lý event sai thứ tự

Cách xử lý phụ thuộc event chứa full state hay delta.

### 8.1. Full-state event

Full-state event chứa trạng thái đầy đủ sau một version. Nếu event version 12 đến trước version 11, consumer có thể áp dụng version 12 rồi bỏ qua version 11 khi nó đến muộn.

~~~text
Receive v12 -> apply state v12
Receive v11 -> stale, ignore
~~~

Đây là lợi thế lớn của full-state projection. Tuy nhiên, event version 12 phải thực sự chứa trạng thái đầy đủ, không phải chỉ chứa một field thay đổi.

### 8.2. Delta event

Delta event chỉ chứa phần thay đổi:

~~~text
v10: stock = 10
v11: decrement stock by 2
v12: increment stock by 5
~~~

Nếu v12 được áp dụng trước v11, trạng thái có thể sai vì delta phụ thuộc thứ tự.

Với delta event:

- Giữ thứ tự theo aggregate.
- Phát hiện sequence gap.
- Buffer event đến sớm nếu có thể chờ event còn thiếu.
- Không xác nhận offset vượt qua event chưa xử lý nếu broker semantics yêu cầu thứ tự.
- Nếu không thể khôi phục chuỗi event, đọc lại trạng thái aggregate từ nguồn chuẩn và rebuild projection.

### 8.3. Phát hiện sequence gap

Giả sử document đang ở version 20, consumer nhận event version 22:

~~~text
storedVersion = 20
incomingVersion = 22
expectedVersion = 21
~~~

Có thể version 21 đang đến muộn hoặc đã bị mất. Nếu event 22 là full state, có thể áp dụng version 22 và đánh dấu bỏ qua version 21 theo chính sách. Nếu event 22 là delta, không nên áp dụng khi thiếu version 21.

Một policy:

| Điều kiện | Full-state event | Delta event |
| --- | --- | --- |
| Incoming = stored + 1 | Áp dụng | Áp dụng |
| Incoming <= stored | Bỏ qua stale/duplicate | Bỏ qua nếu đã xử lý, kiểm tra duplicate |
| Incoming > stored + 1 | Có thể áp dụng trạng thái mới nhất | Buffer, retry hoặc rebuild |

### 8.4. Không dùng occurredAt để sắp xếp duy nhất

Timestamp có thể hữu ích để hiển thị lịch sử, nhưng có các hạn chế:

- Đồng hồ application instance có thể lệch.
- Hai event có cùng timestamp.
- Transaction bắt đầu trước nhưng commit sau.
- Event được tạo từ nhiều service.
- Timestamp không biểu diễn thứ tự commit một cách tổng quát.

Nếu cần ordering chính xác, dùng aggregate version, database log sequence hoặc broker offset có semantics rõ ràng.

## 9. Ordering trong message broker

Message broker có thể bảo đảm thứ tự trong một phạm vi, nhưng không phải lúc nào cũng bảo đảm thứ tự toàn hệ thống.

### 9.1. Partition key theo aggregate ID

Với Kafka, các event có cùng key thường được đưa vào cùng partition. Dùng aggregateId làm message key giúp các event của cùng aggregate được đọc theo thứ tự trong partition.

~~~text
key = Product:P-100

Partition 2:
  offset 100 -> version 10
  offset 101 -> version 11
  offset 102 -> version 12
~~~

Các aggregate khác có thể nằm ở partition khác và được xử lý song song.

### 9.2. Ordering chỉ trong partition

Kafka không cung cấp thứ tự tổng thể giữa nhiều partition. Nếu Product P-100 và Product P-200 ở hai partition khác nhau, không nên giả định event của hai product có một thứ tự toàn cục.

Thông thường, projection Elasticsearch theo document ID chỉ cần ordering theo aggregate. Nếu nghiệp vụ có invariant liên quan nhiều aggregate, cần một cơ chế transaction/event coordination ở nguồn.

### 9.3. Không xử lý song song cùng một aggregate

Ngay cả khi broker giao event đúng thứ tự, consumer có thể phá thứ tự nếu dispatch nhiều event cùng key sang các worker song song:

~~~text
Consumer receives:
  v10
  v11

Worker A handles v10 (slow)
Worker B handles v11 (fast)

Elasticsearch receives:
  v11
  v10
~~~

Có thể xử lý bằng:

- Serial processing trong từng partition.
- Key-based executor bảo đảm cùng aggregate vào cùng lane.
- Source version guard ở Elasticsearch.
- Kết hợp ordering và version guard để có lớp bảo vệ kép.

## 10. Delete, tombstone và event đến muộn

Delete thường khó xử lý hơn upsert vì sau khi xóa vật lý, document không còn chứa version để so sánh với event cũ.

Timeline:

~~~text
v10: Product P-100 tồn tại
v11: Product P-100 được xóa
v10 event retry đến muộn
~~~

Nếu v11 xóa document vật lý rồi v10 được index lại, sản phẩm sống lại.

### 10.1. Tombstone document

Thay vì xóa vật lý ngay, ghi một tombstone:

~~~json
{
  "id": "P-100",
  "sourceVersion": 11,
  "deleted": true,
  "deletedAt": "2026-11-13T10:16:00Z"
}
~~~

Query đọc sản phẩm lọc deleted=false. Tombstone giữ sourceVersion 11 để event upsert version 10 đến sau bị từ chối.

### 10.2. Giữ tombstone đủ lâu

Tombstone phải được giữ lâu hơn thời gian event cũ có thể xuất hiện:

- Broker retention.
- Consumer retry window.
- DLQ replay window.
- Backup restore window.
- Bootstrap/rebuild duration.
- Thời gian phục hồi sau outage.

Nếu xóa tombstone trước khi event cũ không còn khả năng replay, document có thể sống lại.

### 10.3. Khi nào có thể xóa tombstone vật lý?

Chỉ xóa tombstone sau khi:

1. Tất cả consumer đã qua watermark bảo đảm không còn event cũ.
2. DLQ không còn event có version thấp hơn.
3. Backup/replay process không thể phát lại event cũ.
4. Có cơ chế ngăn upsert cũ nếu nó vẫn xuất hiện.

Có thể giữ version ledger riêng nếu không muốn tombstone nằm trong index search.

### 10.4. Delete event cần version

Event delete phải mang aggregateVersion mới hơn trạng thái trước đó. Không gửi delete không version nếu hệ thống có thể nhận event cũ đến sau.

Nếu dùng Elasticsearch external versioning, có thể ghi tombstone như một document với external version, hoặc duy trì version ledger riêng. Physical delete với version có retention giới hạn không thay thế tombstone bền vững trong replay window dài.

## 11. Dùng event store hoặc outbox để giữ thứ tự

Nếu ứng dụng kiểm soát transaction nghiệp vụ, transactional outbox giúp event được lưu bền vững cùng thay đổi nguồn.

Trong một transaction:

1. Cập nhật Product.
2. Tăng aggregateVersion.
3. Ghi event vào outbox với eventId, aggregateId và version.
4. Commit một lần.

Ví dụ bảng outbox:

| event_id | aggregate_id | aggregate_version | event_type | payload |
| --- | --- | ---: | --- | --- |
| evt-100 | P-100 | 10 | ProductCreated | ... |
| evt-101 | P-100 | 11 | ProductPriceChanged | ... |
| evt-102 | P-100 | 12 | ProductStockChanged | ... |

Outbox relay có thể publish lại event nếu không chắc lần publish trước đã thành công. Consumer vẫn phải idempotent.

### 11.1. Unique constraint cho event identity

Nên đặt unique constraint cho event_id để publisher không tạo cùng một event record nhiều lần do retry transaction hoặc lỗi ứng dụng.

Có thể có unique constraint trên (aggregate_id, aggregate_version) nếu mỗi aggregate version chỉ tương ứng một event trong mô hình dữ liệu. Nếu một transaction phát nhiều event cùng version, cần thêm event sequence hoặc thiết kế khóa phù hợp.

### 11.2. Aggregate version phải được cấp trong transaction

Không tăng version ở publisher sau khi đọc dữ liệu. Hai request đồng thời có thể cùng đọc version 10 rồi cả hai phát version 11.

Version cần được cập nhật nguyên tử trong database, ví dụ optimistic locking hoặc update có điều kiện:

~~~sql
UPDATE product
SET price = :price,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
~~~

Nếu số hàng được cập nhật bằng 0, transaction phải xử lý optimistic lock conflict thay vì phát event version trùng.

## 12. Consumer checkpoint và acknowledgement

Consumer cần ghi nhận event nào đã được xử lý. Với broker có offset, checkpoint thường là offset đã commit. Với CDC connector, checkpoint là log position hoặc connector offset.

Quy tắc:

~~~text
Receive event
     |
     v
Validate event
     |
     v
Apply projection to Elasticsearch
     |
     +---- success / stale event safely ignored
     |             |
     |             v
     |        Commit offset
     |
     +---- transient failure
     |             |
     |             v
     |        Retry without advancing
     |
     +---- permanent failure
                   |
                   v
          Persist to DLQ / error store
                   |
                   v
          Commit according to policy
~~~

Không commit offset trước khi projection hoàn tất. Nếu commit trước, consumer crash có thể làm event bị mất.

### 12.1. Commit sau khi ghi thành công

Nếu Elasticsearch đã ghi nhưng commit offset thất bại, event có thể được giao lại. Vì vậy, projection cần idempotent.

Đây là trade-off phổ biến của at-least-once processing: có thể xử lý trùng nhưng không bỏ sót event đã được xác nhận sai thời điểm.

### 12.2. Nhiều event trong một batch

Nếu consumer xử lý batch, chỉ commit đến offset liên tục đã hoàn tất. Không commit vượt qua một event trước đó còn pending nếu broker yêu cầu thứ tự offset.

Ví dụ:

~~~text
offset 100 -> success
offset 101 -> pending
offset 102 -> success

Safe committed offset = 100
~~~

Nếu commit 102 khi 101 chưa được xử lý bền vững, restart có thể bỏ qua event 101.

### 12.3. Partition concurrency

Với Kafka, offset commit là theo partition. Nếu xử lý song song trong partition, cần theo dõi highest contiguous completed offset, không chỉ offset lớn nhất đã xong.

Nếu yêu cầu ordering theo aggregate, cách đơn giản nhất thường là giữ thứ tự xử lý trong partition hoặc dùng key-based serial executor.

## 13. Retry event và backoff

Không phải mọi lỗi đều có thể retry.

| Lỗi | Cách xử lý thường gặp |
| --- | --- |
| HTTP 429 / rejected execution | Retry có backoff, giảm concurrency |
| Lỗi mạng hoặc timeout | Retry an toàn sau khi xem xét kết quả chưa xác định |
| HTTP 5xx tạm thời | Retry có giới hạn |
| Mapping/parsing exception | Sửa payload hoặc mapping; không retry nguyên trạng |
| Authentication/authorization | Sửa cấu hình credential/quyền |
| Version conflict do stale event | Bỏ qua nếu đã xác nhận version mới hơn |
| Version gap của delta event | Buffer, retry event thiếu hoặc rebuild |
| Index missing | Kiểm tra lifecycle/bootstrap và cấu hình target |

### 13.1. Exponential backoff

Ví dụ delay cơ sở:

| Lần retry | Delay |
| --- | ---: |
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 3.200 ms |

Thêm jitter để nhiều consumer không retry cùng lúc. Giới hạn delay tối đa và tổng thời gian retry.

### 13.2. Giữ ordering khi retry

Với delta event, nếu version 11 thất bại mà version 12 được xử lý tiếp, trạng thái có thể sai. Cần chặn các event sau của cùng aggregate cho đến khi version 11 được xử lý hoặc aggregate được rebuild.

Với full-state event, có thể cho phép version 12 được áp dụng trước và sau đó bỏ qua version 11 bằng version guard.

Không áp dụng cùng một retry policy cho full-state và delta event mà không xét semantics.

## 14. Dead-letter queue và poison event

Poison event là event liên tục thất bại do dữ liệu hoặc schema không hợp lệ. Nếu consumer retry vô hạn, một event có thể chặn toàn bộ partition hoặc làm backlog tăng liên tục.

Sau số lần retry cho phép, lưu event vào dead-letter queue (DLQ).

Một DLQ record nên có:

~~~json
{
  "eventId": "evt-90021",
  "aggregateId": "P-100",
  "aggregateVersion": 45,
  "sourceTopic": "product-events",
  "sourcePartition": 2,
  "sourceOffset": 1024,
  "attempts": 5,
  "errorType": "mapper_parsing_exception",
  "errorReason": "failed to parse field price",
  "failedAt": "2026-11-13T10:20:00Z",
  "payload": {
    "id": "P-100",
    "price": "unknown"
  }
}
~~~

### 14.1. DLQ không phải nơi bỏ quên event

Mỗi DLQ cần có:

- Metric số event trong DLQ.
- Alert theo số lượng và tuổi event.
- Công cụ tra cứu event theo ID/aggregate.
- Quy trình sửa schema hoặc dữ liệu.
- Quy trình replay có kiểm soát.
- Owner chịu trách nhiệm xử lý.

### 14.2. Replay DLQ

Khi replay:

1. Xác nhận nguyên nhân đã được sửa.
2. Giữ nguyên eventId và aggregateVersion gốc.
3. Xác định event có còn mới hơn trạng thái đích không.
4. Nếu event đã stale, đánh dấu bỏ qua theo policy.
5. Nếu event còn cần thiết, gửi lại theo ordering phù hợp.
6. Ghi lại kết quả replay.

Không tự tăng aggregateVersion chỉ để replay qua version conflict. Version phản ánh lịch sử nguồn, không phải số lần consumer thử.

## 15. Full-state event và delta event: chọn theo nhu cầu

| Tiêu chí | Full-state event | Delta event |
| --- | --- | --- |
| Payload | Trạng thái đầy đủ | Phần thay đổi |
| Dễ xử lý duplicate | Cao nếu dùng ID/version | Thấp hơn nếu có phép cộng/side effect |
| Dễ xử lý out-of-order | Có thể bỏ qua version cũ | Thường cần thứ tự liên tục |
| Dung lượng event | Lớn hơn | Nhỏ hơn |
| Replay | Có thể index lại trạng thái | Cần lịch sử đầy đủ và đúng thứ tự |
| Rebuild index | Thuận lợi | Có thể cần snapshot + toàn bộ event |

Với Elasticsearch là read model/search projection, full-state event thường là lựa chọn dễ vận hành hơn nếu payload không quá lớn. Có thể tạo full-state event từ aggregate hoặc để consumer đọc lại trạng thái mới nhất từ source of truth.

### 15.1. Khi chỉ có delta event

Nếu domain chỉ phát delta:

- Dùng aggregateVersion.
- Bảo đảm event cùng aggregate được phân vùng và xử lý tuần tự.
- Phát hiện gap.
- Giữ event bền vững để replay.
- Nếu thiếu event không thể khôi phục, đọc lại aggregate từ nguồn chuẩn và ghi full document mới.

Không nên dùng script update cộng/trừ trên Elasticsearch như nguồn duy nhất của trạng thái nghiệp vụ nếu event có thể giao trùng hoặc sai thứ tự.

## 16. Event đến muộn sau khi index được rebuild

Khi tạo index mới, consumer có thể replay event trong lúc snapshot đang ghi. Nếu không có version guard, event cũ có thể ghi đè snapshot mới hoặc ngược lại.

Một mô hình an toàn:

1. Snapshot row mang sourceVersion tại thời điểm snapshot.
2. Event mang aggregateVersion của thay đổi.
3. Snapshot writer và event projector dùng chung document ID.
4. Mọi ghi đều dùng external version hoặc conditional update theo sourceVersion.
5. Target chỉ giữ trạng thái có version lớn nhất.

Ví dụ:

~~~text
Snapshot P-100 version 20
Event P-100 version 21
Event P-100 version 22

Arrival order:
  event 22
  snapshot 20
  event 21

Target:
  version 22
  snapshot 20 rejected as stale
  event 21 rejected as stale
~~~

Nếu version guard không được triển khai, hãy buộc snapshot hoàn tất trước khi replay bắt đầu và bảo đảm change log giữ đủ event từ snapshot boundary.

## 17. Ghi log và quan sát event processing

Log cần cho biết event nào được nhận, đã xử lý ra sao và vì sao bị bỏ qua hoặc retry.

Ví dụ log thành công:

~~~text
eventId=evt-90001
aggregateType=Product
aggregateId=P-100
aggregateVersion=42
operation=UPSERT
result=APPLIED
targetIndex=products-v2
sourcePartition=2
sourceOffset=1024
~~~

Ví dụ event stale:

~~~text
eventId=evt-89990
aggregateId=P-100
incomingVersion=40
storedVersion=42
result=IGNORED_STALE
~~~

Ví dụ DLQ:

~~~text
eventId=evt-90021
aggregateId=P-100
aggregateVersion=45
result=DEAD_LETTERED
attempts=5
errorType=mapper_parsing_exception
~~~

### 17.1. Metric cần theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| events_received_total | Tổng event consumer nhận |
| events_applied_total | Tổng event được áp dụng |
| events_duplicate_total | Event trùng |
| events_stale_total | Event cũ bị bỏ qua |
| events_out_of_order_total | Event sai thứ tự |
| events_gap_total | Phát hiện thiếu version/sequence |
| events_retried_total | Tổng lần retry |
| events_dead_letter_total | Tổng event vào DLQ |
| consumer_lag | Khoảng cách consumer với nguồn |
| event_processing_duration | Thời gian xử lý event |
| projection_version_lag | Chênh lệch source version và target version |

Metric stale event tăng có thể là dấu hiệu retry bình thường, nhưng nếu tăng đột biến có thể cho thấy consumer xử lý song song không đúng hoặc publisher phát lại nhiều event.

### 17.2. Tránh log payload nhạy cảm

Log eventId, aggregateId, version, offset và error metadata thường đủ để điều tra. Không log toàn bộ payload nếu chứa thông tin cá nhân, bí mật hoặc dữ liệu lớn. Có thể log hash payload để hỗ trợ nhận diện hai event cùng version nhưng khác nội dung.

## 18. Ví dụ projector với version guard

Ví dụ dưới đây mô tả cách phân loại event theo version trước khi ghi. Phần kiểm tra và ghi phải được thực hiện nguyên tử ở Elasticsearch nếu có nhiều writer cạnh tranh.

~~~java
public enum ProjectionDecision {
    APPLY,
    IGNORE_DUPLICATE,
    IGNORE_STALE,
    VERSION_GAP
}

public ProjectionDecision decide(
        long storedVersion,
        long incomingVersion,
        boolean fullStateEvent) {

    if (incomingVersion < storedVersion) {
        return ProjectionDecision.IGNORE_STALE;
    }

    if (incomingVersion == storedVersion) {
        return ProjectionDecision.IGNORE_DUPLICATE;
    }

    if (!fullStateEvent && incomingVersion > storedVersion + 1) {
        return ProjectionDecision.VERSION_GAP;
    }

    return ProjectionDecision.APPLY;
}
~~~

Đây là logic minh họa cho một consumer tuần tự. Nếu nhiều consumer có thể ghi cùng document, không nên chỉ đọc storedVersion rồi quyết định ở Java, sau đó ghi bằng một request không điều kiện. Một writer khác có thể thay đổi document giữa bước đọc và bước ghi.

Hãy dùng external versioning hoặc update script/optimistic concurrency để thực hiện version guard một cách nguyên tử.

### 18.1. External versioning với Java API Client

Ví dụ bulk index operation có external version:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.VersionType;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;

public BulkResponse writeVersionedBatch(
        ElasticsearchClient client,
        String index,
        List<ProductIndexDocument> documents) throws IOException {

    BulkRequest.Builder request = new BulkRequest.Builder();

    for (ProductIndexDocument document : documents) {
        request.operations(operation -> operation
            .index(indexOperation -> indexOperation
                .index(index)
                .id(document.id())
                .version(document.sourceVersion())
                .versionType(VersionType.External)
                .document(document)
            )
        );
    }

    return client.bulk(request.build());
}
~~~

Tên enum và builder method cần đối chiếu với phiên bản Elasticsearch Java API Client đang dùng. Với external strict versioning, duplicate cùng version có thể trả conflict; consumer có thể phân loại conflict là stale/duplicate sau khi xác nhận trạng thái đích.

### 18.2. Kiểm tra từng item

Bulk response có thể trả HTTP 200 dù một số item lỗi. Cần duyệt từng item:

~~~java
BulkResponse response = writeVersionedBatch(
    client,
    "products-v2",
    documents
);

for (var item : response.items()) {
    if (item.error() == null) {
        recordApplied(item.id(), item.status());
        continue;
    }

    if (item.status() == 409) {
        recordVersionConflict(item.id(), item.error().type());
        continue;
    }

    recordFailure(
        item.id(),
        item.status(),
        item.error().type(),
        item.error().reason()
    );
}
~~~

Không coi mọi 409 là stale event. Phân tích error type, version policy và stored state để phân biệt duplicate, stale version, create conflict hoặc optimistic concurrency conflict.

## 19. Update script có điều kiện theo sourceVersion

Trong một số trường hợp cần cập nhật một phần document, có thể dùng update script để so sánh version rồi chỉ áp dụng khi incoming version mới hơn.

Pseudocode Painless:

~~~text
if (ctx._source.sourceVersion == null ||
    params.sourceVersion > ctx._source.sourceVersion) {
    ctx._source.name = params.name;
    ctx._source.price = params.price;
    ctx._source.sourceVersion = params.sourceVersion;
} else {
    ctx.op = 'noop';
}
~~~

Script chạy trong Elasticsearch, vì vậy việc đọc version và cập nhật document được thực hiện trong một operation. Đây là cách tránh race giữa bước read-then-write ở client.

Nếu event là delta, script cũng cần kiểm tra version liên tiếp hoặc previousVersion:

~~~text
if (params.previousVersion == ctx._source.sourceVersion) {
    // Apply delta and set new sourceVersion.
} else {
    // Reject or noop; caller must classify the gap/stale event.
}
~~~

Không dùng script update để âm thầm bỏ qua mọi event sai thứ tự. Consumer vẫn cần biết event bị bỏ qua vì stale hay bị từ chối vì thiếu version.

## 20. Reconciliation và rebuild khi event chain bị hỏng

Nếu phát hiện version gap không thể phục hồi, có thể đọc lại trạng thái aggregate từ nguồn chuẩn rồi ghi lại document đầy đủ.

Quy trình:

1. Đánh dấu aggregate cần reconcile.
2. Tạm dừng hoặc serialize các event mới của aggregate nếu cần.
3. Đọc trạng thái hiện tại và version từ source of truth.
4. Tạo full-state document.
5. Ghi bằng source version guard.
6. Xác nhận target đã đạt version nguồn.
7. Tiếp tục xử lý event mới.

Nếu event mới hơn đến trong lúc reconciliation, version guard bảo đảm snapshot reconciliation cũ không ghi đè trạng thái mới hơn.

### 20.1. Reconciliation theo batch

Có thể định kỳ so sánh:

- Aggregate version trong nguồn.
- sourceVersion trong Elasticsearch.
- Deleted state.
- Số aggregate không có document.
- Số document không còn trong nguồn.

Không cần đọc toàn bộ source cho mỗi event. Có thể dùng audit job, change log hoặc sampling để phát hiện drift.

### 20.2. Không sửa version nguồn trong quá trình sửa index

Khi rebuild document do lỗi projection, giữ sourceVersion gốc của trạng thái được đọc. Không tăng version để vượt qua conflict, vì việc đó làm sai lịch sử nghiệp vụ và có thể khiến event hợp lệ sau đó bị coi là stale.

## 21. Kiểm thử event trùng, đến muộn và sai thứ tự

Test nên kiểm tra trạng thái cuối của Elasticsearch thay vì chỉ xác nhận consumer không ném exception.

### 21.1. Duplicate event

Kịch bản:

1. Gửi event version 10.
2. Gửi lại đúng event đó.
3. Refresh index.
4. Assert document chỉ có một trạng thái version 10.
5. Nếu có counter hoặc side effect, xác nhận nó không bị áp dụng hai lần.

### 21.2. Event đến muộn

Kịch bản:

1. Gửi event version 12 với giá 120.
2. Gửi event version 11 với giá 100.
3. Assert document vẫn có giá 120 và sourceVersion 12.

### 21.3. Event sai thứ tự

Với full-state event:

~~~text
Send v12
Send v10
Send v11
Expected stored version = 12
~~~

Với delta event:

~~~text
Stored v10
Receive v12 (expects v11 first)
Expected: buffer/retry/reconcile, not apply delta
Receive v11
Apply v11 then v12
~~~

### 21.4. Delete rồi nhận upsert cũ

Kịch bản:

1. Ghi Product P-100 version 10.
2. Ghi tombstone version 11.
3. Gửi lại upsert version 10.
4. Assert document vẫn deleted hoặc tombstone version 11.
5. Query sản phẩm phải không trả về P-100.

### 21.5. Crash giữa Elasticsearch write và offset commit

Kịch bản:

1. Consumer ghi event thành công.
2. Giả lập crash trước commit offset.
3. Giao lại event.
4. Assert projection idempotent và sourceVersion không đổi sai.

### 21.6. Version gap

Kịch bản:

1. Target đang version 20.
2. Gửi delta event version 22.
3. Assert consumer không áp dụng delta khi thiếu version 21.
4. Gửi version 21.
5. Assert version 21 rồi 22 được áp dụng đúng thứ tự.

## 22. Các lỗi thường gặp

**Dùng timestamp nhận event làm thứ tự.** Event cũ có thể đến sau event mới. Dùng aggregateVersion hoặc sequence từ nguồn.

**Cho rằng broker không giao event trùng.** At-least-once delivery có thể giao lại. Thiết kế consumer idempotent.

**Chỉ deduplicate bằng eventId rồi bỏ qua version.** Event ID không cho biết event nào mới hơn. Dùng cả event identity và aggregate version.

**Đánh dấu event processed trước khi ghi Elasticsearch.** Crash sau khi đánh dấu có thể làm mất projection. Ghi đích trước, sau đó commit checkpoint; dùng version guard để chịu duplicate.

**Dùng phép cộng/trừ cho event có thể giao lặp.** Delta có thể bị áp dụng nhiều lần. Dùng event dedup bền vững, ordering hoặc full-state projection.

**Dùng _version của Elasticsearch như version nguồn.** Elasticsearch internal version không mang semantics lịch sử nghiệp vụ. Lưu sourceVersion riêng hoặc dùng external versioning.

**Đọc version rồi ghi không điều kiện ở client.** Hai consumer có thể race. Dùng external versioning, script condition hoặc optimistic concurrency.

**Dùng external_gte khi cùng version có payload khác nhau.** Event đến sau có thể ghi đè trạng thái cùng version. Bảo đảm version duy nhất cho một trạng thái hoặc dùng external strict.

**Coi mọi HTTP 409 là duplicate.** Có thể là version conflict, create conflict hoặc optimistic concurrency. Phân tích error type và stored version.

**Bỏ qua version gap của delta event.** Thiếu event trước có thể làm trạng thái sai. Buffer, retry hoặc rebuild từ nguồn.

**Xử lý event cùng aggregate song song.** Event mới có thể ghi trước event cũ. Partition theo aggregate key và/hoặc dùng version guard.

**Xóa document vật lý rồi bỏ quên tombstone.** Event upsert cũ có thể tạo lại document. Giữ tombstone/version ledger đủ lâu.

**Retry poison event vô hạn.** Một event có thể chặn partition. Dùng retry giới hạn và DLQ.

**Commit offset trước khi projection xong.** Consumer crash có thể làm event bị bỏ qua. Commit sau khi ghi hoặc lưu lỗi bền vững theo policy.

**Commit offset cao nhất dù offset trước chưa hoàn tất.** Có thể bỏ qua event chưa xử lý. Commit highest contiguous completed offset.

**Replay DLQ với version mới giả tạo.** Điều đó phá lịch sử nguồn và làm event khác bị stale. Giữ version gốc.

**Không có reconciliation.** Event chain có thể bị thiếu hoặc projection drift mà không được phát hiện. So sánh sourceVersion và trạng thái nguồn định kỳ.

## 23. Quy trình xử lý event đề xuất

Với mỗi event nhận được:

1. Validate schema, eventId, aggregateId, aggregateVersion và operation.
2. Xác định event là full-state hay delta.
3. Kiểm tra eventId nếu cần deduplication ledger.
4. Đọc hoặc kiểm tra sourceVersion hiện tại theo cơ chế nguyên tử ở Elasticsearch.
5. Nếu incoming version cũ hơn, ghi nhận stale và không áp dụng.
6. Nếu version bằng, phân loại duplicate hoặc payload conflict.
7. Nếu version lớn hơn nhưng có gap và event là delta, buffer/retry hoặc reconcile.
8. Nếu event hợp lệ, apply upsert/delete/tombstone với version guard.
9. Kiểm tra từng item result nếu dùng bulk.
10. Chỉ sau khi kết quả được xử lý bền vững, commit offset/checkpoint.
11. Với lỗi tạm thời, retry có backoff và giữ ordering cần thiết.
12. Với lỗi permanent, lưu event vào DLQ và phát cảnh báo.
13. Theo dõi sourceVersion, lag, stale count, gap count và DLQ.

~~~text
Receive event
     |
     v
Validate schema and identity
     |
     v
Classify event type
     |
     v
Compare source version
     |
     +-- stale/duplicate ------> record ignored -> ack
     |
     +-- delta version gap ----> buffer/retry/reconcile
     |
     +-- newer valid event ----> atomic versioned write
                                    |
                                    +-- success/noop stale -> ack
                                    |
                                    +-- transient failure -> retry
                                    |
                                    +-- permanent failure -> DLQ
~~~

## 24. Tài liệu tham khảo

- [Elasticsearch - Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index): document indexing và version parameters.
- [Elasticsearch - Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk): bulk operations, item response và external versioning.
- [Elasticsearch - Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control): _seq_no, _primary_term và conditional writes.
- [Elasticsearch - Update API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update): update scripts và noop operations.
- [Elasticsearch - Delete API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete): delete behavior và version constraints.
- [Apache Kafka - Message delivery semantics](https://kafka.apache.org/documentation/#semantics): at-least-once, idempotent producer và processing semantics.
- [Apache Kafka - Message ordering](https://kafka.apache.org/documentation/#intro_concepts_and_terms): partition ordering và message keys.
- [Debezium - Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): transactional outbox event routing.
- [Spring Data Elasticsearch - Bulk operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): sử dụng ElasticsearchOperations và bulk APIs.

Tên class, enum và builder method của Elasticsearch Java API Client có thể thay đổi theo phiên bản. Hãy kiểm tra Javadoc đúng dependency của dự án. Quy tắc cốt lõi là event identity giúp nhận diện duplicate, source version xác định trạng thái mới hơn, ordering bảo vệ delta event, còn idempotency và tombstone giúp pipeline phục hồi an toàn khi retry hoặc replay.

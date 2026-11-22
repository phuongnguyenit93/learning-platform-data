# Truyền thay đổi xóa, tombstone và ngăn hồi sinh tài liệu cũ

## 1. Vấn đề khi đồng bộ thao tác xóa

Một hệ thống thường có cơ sở dữ liệu nguồn và Elasticsearch làm read model phục vụ tìm kiếm. Ứng dụng ghi dữ liệu vào database, sau đó một luồng đồng bộ chuyển các thay đổi sang Elasticsearch qua message broker, CDC hoặc transactional outbox.

Với thao tác tạo và cập nhật, luồng đồng bộ thường gửi một document mới hoặc một bản cập nhật. Với thao tác xóa, database có thể xóa hẳn row. Nếu luồng đồng bộ chỉ đọc những row còn tồn tại, nó sẽ không còn dữ liệu để biết rằng một document cần bị xóa khỏi Elasticsearch.

Ví dụ:

1. Đơn hàng `order-42` tồn tại trong database và Elasticsearch.
2. Người dùng xóa đơn hàng trong database.
3. Một sự kiện xóa được phát ra nhưng consumer đang tạm dừng.
4. Một worker khác hoặc một lần retry cũ vẫn gửi sự kiện cập nhật trước đó.
5. Elasticsearch nhận lại payload cũ và tạo document `order-42`.

Document đã bị xóa có thể xuất hiện trở lại. Hiện tượng này thường được gọi là **resurrection** hoặc hồi sinh dữ liệu.

Nguyên nhân thường không nằm ở thao tác Delete API. Vấn đề nằm ở việc hệ thống không giữ đủ thông tin để phân biệt một thay đổi mới với một sự kiện cũ đến trễ.

Muốn đồng bộ xóa an toàn, cần có cơ chế truyền dấu vết của thao tác xóa, xác định thứ tự phiên bản cho từng entity và từ chối mọi bản ghi cũ hơn trạng thái đã áp dụng.

## 2. Tombstone là gì?

**Tombstone** là một dấu mốc cho biết một entity đã bị xóa tại một phiên bản hoặc thời điểm cụ thể. Tombstone có thể là một sự kiện trong event stream, một document đánh dấu đã xóa trong Elasticsearch, hoặc một bản ghi metadata được lưu riêng.

Ví dụ tombstone cho đơn hàng:

~~~json
{
  "id": "order-42",
  "operation": "DELETE",
  "sourceRevision": 18,
  "deletedAt": "2026-11-13T10:15:30Z",
  "eventId": "evt-9f8a"
}
~~~

Tombstone mang thông tin quan trọng:

- Entity nào đã bị xóa.
- Phiên bản nguồn tại thời điểm xóa.
- Thời điểm hoặc vị trí của thay đổi.
- ID sự kiện để hỗ trợ deduplication và tracing.
- Routing hoặc partition key nếu cần xác định đúng shard.

Một tombstone cho biết rằng trạng thái mới nhất của entity là đã xóa. Khi một sự kiện cũ hơn xuất hiện, consumer có thể so sánh revision của sự kiện với revision tombstone và từ chối sự kiện cũ.

### Tombstone khác gì soft delete?

Soft delete thường là cách biểu diễn trạng thái xóa trong dữ liệu nghiệp vụ, ví dụ:

~~~json
{
  "id": "order-42",
  "deleted": true,
  "deletedAt": "2026-11-13T10:15:30Z"
}
~~~

Soft delete có thể đóng vai trò tombstone nếu nó giữ đủ revision và được dùng làm mốc chống sự kiện cũ.

Tuy nhiên, một cờ `deleted=true` không tự động bảo vệ khỏi hồi sinh. Nếu ứng dụng xóa document này sau một thời gian rồi nhận lại một upsert cũ, Elasticsearch không còn dấu mốc để từ chối upsert đó.

### Tombstone không nhất thiết giữ toàn bộ document

Trong nhiều hệ thống, tombstone chỉ cần giữ ID, source revision, thời điểm xóa và một số metadata cần thiết. Nếu cần xóa dữ liệu cá nhân hoặc payload nhạy cảm, có thể thay nội dung document bằng một tombstone tối giản.

Tombstone nên lưu đủ thông tin để chống hồi sinh nhưng không giữ lại dữ liệu nghiệp vụ đã cần xóa.

## 3. Ba khái niệm xóa cần phân biệt trong Elasticsearch

Trong Elasticsearch, có nhiều cơ chế mang ý nghĩa “xóa”, nhưng chúng phục vụ các mục đích khác nhau.

| Cơ chế | Ý nghĩa | Có phải tombstone nghiệp vụ bền vững? |
|---|---|---|
| Delete API | Xóa document khỏi khả năng truy vấn | Không |
| Soft delete nội bộ của Elasticsearch | Giữ lịch sử thao tác phục vụ replication/recovery | Không |
| Application tombstone | Document hoặc event đánh dấu entity đã xóa kèm revision nguồn | Có, nếu được giữ và kiểm tra đúng cách |

### Delete API

Ví dụ:

~~~http
DELETE /orders/_doc/order-42
~~~

Document không còn xuất hiện trong kết quả tìm kiếm sau khi thay đổi trở nên searchable. Elasticsearch giữ metadata phiên bản của document đã xóa trong một khoảng thời gian ngắn để xử lý các thao tác cạnh tranh.

Khoảng thời gian đó được điều khiển bởi `index.gc_deletes`, mặc định hiện hành là 60 giây. Sau khi metadata xóa được thu gom, Elasticsearch không còn giữ mốc phiên bản xóa đó cho các thao tác versioned tiếp theo.

Vì vậy, Delete API không cung cấp một tombstone ứng dụng tồn tại vô thời hạn.

### Soft deletes nội bộ

Elasticsearch sử dụng soft deletes ở tầng lưu trữ để giữ lịch sử thao tác cần thiết cho các cơ chế như peer recovery và cross-cluster replication. Đây là chi tiết nội bộ của engine.

Soft deletes nội bộ không phải một document `deleted=true` mà ứng dụng có thể dựa vào để quyết định một sự kiện CDC có cũ hay không. Thời gian giữ lịch sử của shard và retention lease cũng không phải chính sách lưu tombstone nghiệp vụ.

### Application tombstone

Application tombstone là dữ liệu do ứng dụng chủ động tạo và duy trì. Ví dụ, thay vì gọi Delete API, consumer index một document tối giản với cùng ID và revision mới hơn:

~~~json
{
  "id": "order-42",
  "sourceRevision": 18,
  "deleted": true,
  "deletedAt": "2026-11-13T10:15:30Z",
  "lastEventId": "evt-9f8a"
}
~~~

Document này vẫn tồn tại trong index và giữ revision 18. Một upsert cũ có revision 17 sẽ bị từ chối khi dùng external versioning.

## 4. Vì sao document cũ có thể hồi sinh?

Giả sử database phát hai sự kiện cho cùng một đơn hàng:

| Revision | Sự kiện | Nội dung |
|---:|---|---|
| 17 | UPDATE | Đơn hàng ở trạng thái `PAID` |
| 18 | DELETE | Đơn hàng bị xóa |

Do consumer chạy song song, sự kiện DELETE revision 18 có thể đến Elasticsearch trước. Consumer gọi Delete API và document biến mất.

Sau đó, một worker retry sự kiện UPDATE revision 17. Nếu worker gọi Index API theo cách ghi thông thường, Elasticsearch có thể tạo lại document vì ID hiện không còn tồn tại.

Timeline:

~~~text
Database source
   |
   +-- revision 17: UPDATE order-42
   |
   +-- revision 18: DELETE order-42
             |
             v
        Event broker
             |
       +-----+------+
       |            |
       v            v
   Consumer B   Consumer A
       |            |
       |            +-- DELETE order-42
       |                     |
       |                     v
       |              Document bị xóa
       |
       +-- UPDATE revision 17 đến trễ
                    |
                    v
              Index order-42
                    |
                    v
             Document hồi sinh
~~~

Nếu hệ thống chỉ dựa vào thứ tự message đến nơi, nó rất dễ gặp vấn đề khi có retry, partition song song, consumer restart hoặc reprocessing.

Cần một revision có thể so sánh được giữa mọi sự kiện của cùng entity. Consumer sẽ dùng revision đó để bảo vệ trạng thái mới nhất.

## 5. Quy tắc nền tảng: revision nguồn phải tăng đơn điệu

Mỗi thay đổi của một entity cần có revision tăng đơn điệu. Revision này được tạo tại nguồn dữ liệu và được giữ trong event.

Ví dụ:

| Thay đổi | Source revision |
|---|---:|
| Tạo đơn hàng | 1 |
| Đổi địa chỉ giao hàng | 2 |
| Xác nhận thanh toán | 3 |
| Đổi trạng thái giao hàng | 4 |
| Xóa đơn hàng | 5 |

Revision của thao tác xóa phải lớn hơn mọi revision của các thay đổi trước đó.

Nếu một entity được tạo lại theo nghiệp vụ, revision mới cũng phải lớn hơn tombstone trước đó. Ví dụ, tombstone ở revision 5, lần tạo lại hợp lệ có revision 6.

Không nên dùng riêng timestamp `updated_at` làm version nếu có thể tránh:

- Hai thay đổi có thể cùng timestamp do độ phân giải clock.
- Nhiều service có clock lệch nhau.
- Một message được retry có thể giữ timestamp cũ.
- Thời gian không nhất thiết phản ánh thứ tự commit của nguồn dữ liệu.

Có thể dùng cột revision tăng dần trong database, sequence theo entity, hoặc một source change position có semantics rõ ràng. Nếu dùng LSN/offset của CDC, cần bảo đảm giá trị đó có thể so sánh đúng trong phạm vi entity và không bị mất ý nghĩa khi đổi partition hoặc nguồn.

Một event nên mang revision nguồn tường minh:

~~~json
{
  "eventId": "evt-9f8a",
  "aggregateId": "order-42",
  "revision": 18,
  "type": "ORDER_DELETED",
  "occurredAt": "2026-11-13T10:15:30Z",
  "routing": "customer-7"
}
~~~

Consumer không tự tạo revision mới theo thời điểm nhận message. Nó phải dùng revision đã được nguồn gán.

## 6. Định dạng sự kiện đồng bộ

Một event đồng bộ nên chứa đủ dữ liệu để consumer có thể áp dụng thay đổi mà không phải suy đoán từ trạng thái hiện tại.

Ví dụ Java record:

~~~java
import java.time.Instant;

public record OrderSyncEvent(
    String eventId,
    String orderId,
    long revision,
    Operation operation,
    OrderPayload payload,
    String routing,
    Instant occurredAt
) {
    public enum Operation {
        UPSERT,
        DELETE
    }
}
~~~

Một số nguyên tắc:

- `eventId` duy nhất để tracing và deduplication.
- `orderId` ổn định trong toàn bộ vòng đời entity.
- `revision` tăng đơn điệu theo entity.
- `operation` phân biệt upsert và delete.
- `payload` có thể null đối với sự kiện xóa.
- `routing` giữ đúng giá trị dùng khi index document.
- `occurredAt` phục vụ quan sát và điều tra, không thay thế revision.

Nếu consumer phải lấy lại dữ liệu từ database khi nhận event, cần cẩn thận: một sự kiện UPDATE cũ có thể đọc được trạng thái mới nhất của database và vô tình ghi nội dung mới với revision cũ. Payload hoặc source revision phải được giữ nhất quán với nhau.

Với CDC, delete event thường chỉ còn thông tin trước khi xóa (before image) hoặc metadata của thao tác. Hãy bảo đảm connector và cấu hình CDC không loại bỏ delete event, ID, revision hoặc routing cần thiết.

## 7. Truyền delete event khi database xóa vật lý

Khi database xóa row vật lý, một job polling đơn giản như:

~~~sql
SELECT * FROM orders WHERE updated_at > :last_seen;
~~~

không thể phát hiện row đã biến mất. Sau khi xóa, row không còn trong kết quả truy vấn.

Có hai cách thường dùng để giữ thông tin xóa.

### CDC đọc log thay đổi

CDC đọc transaction log của database. Một thao tác DELETE có thể được chuyển thành event chứa khóa chính và metadata của thay đổi.

Consumer nhận event xóa và ghi tombstone vào Elasticsearch.

Cần kiểm tra cấu hình connector:

- Delete event có được phát ra không?
- Primary key có còn trong payload không?
- Revision hoặc source position nào có thể dùng để so sánh?
- Before image có được bật nếu cần dữ liệu cũ không?
- Tombstone Kafka có bị connector hoặc SMT loại bỏ không?
- Thời gian lưu log có đủ để consumer phục hồi không?

Một số connector phát một tombstone Kafka record có value null sau delete event để hỗ trợ log compaction. Tombstone Kafka này có semantics khác với application tombstone trong Elasticsearch. Nó giúp broker biểu thị key đã bị xóa khi compact log; consumer vẫn cần xử lý delete event và ghi dấu xóa/version phù hợp vào search index.

### Transactional outbox

Ứng dụng có thể ghi một event vào outbox trong cùng transaction với thao tác xóa.

Luồng khái quát:

~~~text
BEGIN TRANSACTION
    |
    +-- Tăng revision của entity
    |
    +-- Ghi ORDER_DELETED vào outbox
    |
    +-- Xóa row nghiệp vụ
    |
COMMIT
    |
    v
Outbox relay đọc event
    |
    v
Message broker
    |
    v
Elasticsearch consumer
~~~

Ví dụ SQL dạng minh họa:

~~~sql
BEGIN;

UPDATE orders
SET revision = revision + 1
WHERE id = :order_id
RETURNING revision;

-- Ứng dụng lấy revision vừa trả về để ghi outbox.
INSERT INTO outbox_events (
    event_id,
    aggregate_id,
    aggregate_revision,
    event_type,
    created_at
)
VALUES (
    :event_id,
    :order_id,
    :new_revision,
    'ORDER_DELETED',
    CURRENT_TIMESTAMP
);

DELETE FROM orders
WHERE id = :order_id;

COMMIT;
~~~

Câu lệnh trên mô tả các bước trong một transaction; phần lấy revision từ kết quả UPDATE cần được triển khai bằng CTE hoặc câu lệnh phù hợp với database cụ thể.

Điểm quan trọng là event xóa và thao tác xóa row được commit cùng nhau. Nếu transaction rollback, cả hai cùng rollback. Nếu transaction commit, relay vẫn có thể phát event sau khi ứng dụng hoặc broker phục hồi.

Không nên chỉ phát message sau khi xóa database bằng một lời gọi độc lập mà không có outbox hoặc CDC. Nếu ứng dụng chết giữa commit và publish, thông tin xóa có thể bị mất.

## 8. Cách 1: hard delete trong Elasticsearch

Cách đơn giản nhất là nhận delete event rồi gọi Delete API:

~~~http
DELETE /orders/_doc/order-42
~~~

Nếu cần kiểm soát bằng source revision:

~~~http
DELETE /orders/_doc/order-42?version=18&version_type=external
~~~

`version_type=external` yêu cầu version được gửi cao hơn version đang lưu. Nếu document đang ở revision 17, delete revision 18 có thể thành công. Nếu document đã được cập nhật lên revision 19, delete revision 18 bị từ chối vì cũ hơn.

### Giới hạn của hard delete

Sau khi xóa, Elasticsearch chỉ giữ version của document đã xóa trong khoảng thời gian do `index.gc_deletes` điều khiển. Mặc định hiện hành là 60 giây.

Ví dụ:

1. Document đang có external version 17.
2. Delete event revision 18 đến và xóa document.
3. Trong thời gian tombstone nội bộ còn được giữ, một upsert revision 17 bị từ chối.
4. Sau khi delete metadata được garbage collect, upsert revision 17 có thể không còn gặp version marker để so sánh.
5. Nếu ID không còn tồn tại, thao tác index cũ có thể tạo lại document.

Vì vậy, `index.gc_deletes` không phải cơ chế chống hồi sinh lâu dài cho CDC. Tăng giá trị này có thể kéo dài khoảng bảo vệ nhưng không giải quyết được replay sau nhiều giờ, nhiều ngày hoặc sau khi khôi phục backup.

Hard delete phù hợp khi nguồn sự kiện và consumer có giới hạn replay rõ ràng, hoặc khi hệ thống có một kho version/tombstone bền vững khác để kiểm tra trước khi ghi.

## 9. Cách 2: giữ application tombstone trong cùng index

Một mẫu phổ biến là thay document nghiệp vụ bằng một tombstone document có cùng `_id`.

Giả sử document đang hoạt động:

~~~json
{
  "id": "order-42",
  "customerId": "customer-7",
  "status": "PAID",
  "sourceRevision": 17,
  "deleted": false
}
~~~

Khi nhận delete event revision 18, consumer index một document mới:

~~~json
{
  "id": "order-42",
  "sourceRevision": 18,
  "deleted": true,
  "deletedAt": "2026-11-13T10:15:30Z",
  "lastEventId": "evt-9f8a"
}
~~~

Tombstone thay thế payload cũ và giữ version 18. Consumer có thể dùng external versioning để từ chối mọi event có revision thấp hơn.

Ưu điểm:

- Tombstone tồn tại như một document thông thường.
- Revision xóa được giữ sau khi `index.gc_deletes` hết hạn.
- Không cần truy vấn một kho tombstone riêng trước mỗi lần upsert.
- Một lần tạo lại hợp lệ có revision cao hơn có thể ghi đè tombstone.
- Payload nghiệp vụ cũ có thể được loại khỏi `_source` khi tombstone được index.

Đây thường là thiết kế dễ hiểu cho một read model cần chống sự kiện đến sai thứ tự.

### Mapping cho document có tombstone

Ví dụ mapping:

~~~http
PUT /orders-v1
{
  "mappings": {
    "properties": {
      "id": {
        "type": "keyword"
      },
      "customerId": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "sourceRevision": {
        "type": "long"
      },
      "deleted": {
        "type": "boolean"
      },
      "deletedAt": {
        "type": "date"
      },
      "lastEventId": {
        "type": "keyword"
      }
    }
  }
}
~~~

Document đang hoạt động cần có `deleted: false`. Tombstone có `deleted: true`.

Có thể tạo alias chỉ đọc các document đang hoạt động:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "orders-v1",
        "alias": "orders-active",
        "filter": {
          "bool": {
            "must_not": [
              {
                "term": {
                  "deleted": true
                }
              }
            ]
          }
        }
      }
    }
  ]
}
~~~

Ứng dụng tìm kiếm qua alias:

~~~http
GET /orders-active/_search
{
  "query": {
    "term": {
      "customerId": "customer-7"
    }
  }
}
~~~

Alias filter loại tombstone khỏi kết quả tìm kiếm. Tombstone vẫn tồn tại trong index để giữ revision.

Nếu dữ liệu cũ có document chưa có field `deleted`, điều kiện `must_not deleted=true` vẫn cho phép các document đó xuất hiện. Khi muốn chuẩn hóa, có thể bổ sung field `deleted=false` trong quá trình migration.

## 10. External versioning ngăn sự kiện cũ ghi đè tombstone

External versioning cho phép ứng dụng gửi version do nguồn dữ liệu quản lý. Elasticsearch chỉ chấp nhận thao tác nếu version được gửi lớn hơn version hiện tại.

Ví dụ document hiện có revision 17:

~~~http
PUT /orders-v1/_doc/order-42?version=17&version_type=external
{
  "id": "order-42",
  "customerId": "customer-7",
  "status": "PAID",
  "sourceRevision": 17,
  "deleted": false
}
~~~

Delete event revision 18 được biểu diễn bằng một tombstone document:

~~~http
PUT /orders-v1/_doc/order-42?version=18&version_type=external
{
  "id": "order-42",
  "sourceRevision": 18,
  "deleted": true,
  "deletedAt": "2026-11-13T10:15:30Z",
  "lastEventId": "evt-9f8a"
}
~~~

Một sự kiện cũ revision 17 đến sau đó:

~~~http
PUT /orders-v1/_doc/order-42?version=17&version_type=external
{
  "id": "order-42",
  "customerId": "customer-7",
  "status": "PAID",
  "sourceRevision": 17,
  "deleted": false
}
~~~

Elasticsearch trả version conflict vì 17 không lớn hơn 18. Tombstone vẫn giữ trạng thái mới nhất.

Nếu có một lần tái tạo đơn hàng hợp lệ với revision 19, thao tác đó được chấp nhận:

~~~http
PUT /orders-v1/_doc/order-42?version=19&version_type=external
{
  "id": "order-42",
  "customerId": "customer-7",
  "status": "NEW",
  "sourceRevision": 19,
  "deleted": false
}
~~~

Tính chất quan trọng là revision phải do nguồn dữ liệu cấp và phải tăng qua cả thao tác xóa lẫn tạo lại.

### EXTERNAL và EXTERNAL_GTE

| Version type | Điều kiện chấp nhận |
|---|---|
| `internal` | Elasticsearch quản lý version nội bộ |
| `external` | Version gửi vào phải lớn hơn version đang lưu |
| `external_gte` | Version gửi vào có thể bằng hoặc lớn hơn version đang lưu |

Với event stream có thể phát lại, `external` thường an toàn hơn vì một event trùng revision không thể ghi đè một payload khác cùng revision.

`external_gte` có thể hữu ích trong một số thiết kế idempotent đặc biệt, nhưng nếu hai payload khác nhau dùng chung revision thì payload đến sau có thể ghi đè payload trước. Tài liệu Elasticsearch cảnh báo sử dụng sai `external_gte` có thể gây mất dữ liệu.

Không dùng timestamp hoặc giá trị tự tạo ngẫu nhiên làm external version. Cần một thứ tự có ý nghĩa và ổn định ở nguồn.

## 11. Spring Data Elasticsearch và version metadata

Spring Data Elasticsearch hỗ trợ versioning thông qua annotation `@Version` và cấu hình `@Document.versionType`.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(
    indexName = "orders",
    versionType = Document.VersionType.EXTERNAL
)
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String status;

    // Getters và setters
}
~~~

`@Version` đánh dấu property được dùng làm version metadata của document. Spring Data sử dụng version để hỗ trợ kiểm soát các lần ghi cạnh tranh. Khi version không khớp, thao tác có thể thất bại với optimistic locking exception.

`@Document.versionType` xác định cách Elasticsearch quản lý version. Spring Data Elasticsearch 6.1.2 đặt mặc định là `EXTERNAL`; các giá trị được hỗ trợ gồm `INTERNAL`, `EXTERNAL` và `EXTERNAL_GTE`.

Cần phân biệt version metadata với field nghiệp vụ `sourceRevision`:

- `@Version` là metadata version của Elasticsearch được Spring Data quản lý.
- `sourceRevision` là revision do database hoặc event source cấp.
- Nếu dùng external versioning cho CDC, request index thực tế phải nhận đúng source revision làm version metadata.
- Không giả định chỉ thêm một property `sourceRevision` vào entity là Elasticsearch tự dùng nó làm version.

Nếu ứng dụng dùng repository `save()` cho entity thông thường, hãy dùng `@Version` để bảo vệ các lần đọc-sửa-ghi theo mô hình Spring Data. Với consumer CDC cần áp dụng chính xác revision nguồn, hãy xác nhận version được truyền vào request ở tầng Elasticsearch và kiểm thử việc xử lý event đến sai thứ tự.

### SeqNoPrimaryTerm trong Spring Data

Spring Data Elasticsearch còn cung cấp `SeqNoPrimaryTerm` để hỗ trợ optimistic concurrency control bằng `_seq_no` và `_primary_term`.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.query.SeqNoPrimaryTerm;

@Document(indexName = "orders")
public class OrderDocument {

    @Id
    private String id;

    private String status;

    private SeqNoPrimaryTerm seqNoPrimaryTerm;

    // Getters và setters
}
~~~

Khi entity được đọc từ Elasticsearch, Spring Data tự điền cặp sequence number và primary term nếu property này tồn tại. Khi entity được index lại với cặp metadata còn hợp lệ, Spring Data gửi điều kiện tương ứng để Elasticsearch từ chối update nếu document đã bị thay đổi sau lần đọc.

Cơ chế này phù hợp cho luồng:

1. Đọc document.
2. Thay đổi entity trong ứng dụng.
3. Ghi lại entity.
4. Phát hiện nếu một writer khác đã cập nhật document trong lúc đó.

`SeqNoPrimaryTerm` không phải source revision của database và cũng không phải tombstone. Nó bảo vệ một thao tác dựa trên trạng thái Elasticsearch đã đọc trước đó.

## 12. Spring Data Java API Client cho event có source revision

Với Spring Data Elasticsearch 5+ sử dụng Elasticsearch Java API Client, ứng dụng có thể inject client đã được cấu hình và gửi external version trực tiếp.

Ví dụ document index:

~~~java
import co.elastic.clients.elasticsearch._types.VersionType;
import co.elastic.clients.elasticsearch.core.IndexResponse;

OrderIndexDocument document = new OrderIndexDocument(
    event.orderId(),
    event.revision(),
    false,
    null,
    event.eventId()
);

IndexResponse response = elasticsearchClient.index(i -> i
    .index("orders-v1")
    .id(event.orderId())
    .version(event.revision())
    .versionType(VersionType.External)
    .document(document)
);
~~~

Ví dụ tombstone:

~~~java
OrderIndexDocument tombstone = new OrderIndexDocument(
    event.orderId(),
    event.revision(),
    true,
    event.occurredAt(),
    event.eventId()
);

IndexResponse response = elasticsearchClient.index(i -> i
    .index("orders-v1")
    .id(event.orderId())
    .version(event.revision())
    .versionType(VersionType.External)
    .document(tombstone)
);
~~~

Đây là thao tác index một document tombstone với cùng ID. Nó giữ version trong Elasticsearch metadata và lưu source revision trong `_source` để ứng dụng có thể quan sát, debug và đối chiếu.

Ví dụ record document:

~~~java
import java.time.Instant;

public record OrderIndexDocument(
    String id,
    long sourceRevision,
    boolean deleted,
    Instant deletedAt,
    String lastEventId
) {
}
~~~

Trong ứng dụng thực tế, document active có thể có thêm các field tìm kiếm như customer, status và nội dung đơn hàng. Tombstone chỉ cần giữ những field tối thiểu cần thiết.

### Gọi qua ElasticsearchOperations

Nếu ứng dụng đang dùng template, có thể dùng `ElasticsearchOperations.execute(...)` để truy cập client cấp thấp:

~~~java
IndexResponse response = operations.execute(client ->
    client.index(i -> i
        .index("orders-v1")
        .id(event.orderId())
        .version(event.revision())
        .versionType(VersionType.External)
        .document(tombstone)
    )
);
~~~

Đường gọi này dùng Elasticsearch Java API Client trực tiếp. Nó cho phép kiểm soát version type và source revision rõ ràng. Các callback entity của Spring Data không tự chạy chỉ vì request được gọi bên trong `operations.execute`; ứng dụng phải tự chuẩn bị dữ liệu cần gửi.

## 13. Xử lý version conflict đúng cách

Khi dùng external versioning, event trùng hoặc cũ hơn có thể trả về HTTP 409 version conflict.

Không nên xem mọi HTTP 409 là thành công. Có thể có nhiều loại xung đột hoặc lỗi khác cần xử lý.

Một quy trình hợp lý:

1. Nhận event với ID và revision.
2. Gửi index hoặc tombstone bằng external version.
3. Nếu thành công, ghi nhận event đã áp dụng.
4. Nếu nhận version conflict, đọc document hiện tại theo ID.
5. So sánh `sourceRevision` hiện tại với revision của event.
6. Nếu revision hiện tại lớn hơn, event đến trễ và có thể được bỏ qua.
7. Nếu revision bằng nhau và event ID/trạng thái tương ứng, đây có thể là lần phát lại cùng event.
8. Nếu cùng revision nhưng payload hoặc loại event khác nhau, coi là vi phạm hợp đồng version và đưa vào luồng điều tra.

Pseudo-code:

~~~java
try {
    applyWithExternalVersion(event);
    acknowledge(event);
} catch (VersionConflictException conflict) {

    OrderIndexDocument current = loadCurrentDocument(event.orderId());

    if (current.sourceRevision() > event.revision()) {
        // Event cũ hơn trạng thái đã áp dụng.
        acknowledgeAsStale(event);
        return;
    }

    if (current.sourceRevision() == event.revision()
            && current.lastEventId().equals(event.eventId())) {
        // Cùng một event đã được áp dụng trước đó.
        acknowledgeAsDuplicate(event);
        return;
    }

    // Cùng revision nhưng khác event hoặc trạng thái.
    sendToDeadLetterQueue(event, conflict);
}
~~~

Đây là pseudo-code mô tả quy tắc xử lý; tên exception cụ thể phụ thuộc cách client hoặc Spring Data bọc lỗi Elasticsearch.

Khi đọc document hiện tại, hãy xử lý trường hợp document không tồn tại hoặc lỗi mạng. Không biến một lỗi đọc thành kết luận rằng event đã được áp dụng.

### Vì sao không dùng external_gte để né 409?

Nếu dùng `external_gte`, một event cùng revision có thể được chấp nhận và ghi đè tombstone bằng payload cũ nếu producer phát ra hai nội dung khác nhau với cùng version.

Dùng external strict và xử lý duplicate ở consumer thường giúp phát hiện vi phạm version rõ hơn.

## 14. Hard delete có thể dùng versioning và seq_no/primary_term

Nếu nghiệp vụ yêu cầu xóa vật lý khỏi Elasticsearch, Delete API hỗ trợ hai kiểu kiểm soát.

### External versioning

~~~http
DELETE /orders/_doc/order-42?version=18&version_type=external
~~~

Version nguồn được so sánh với version document. Cách này hữu ích khi source revision được dùng làm version của document.

Tuy nhiên, version tombstone của hard delete chỉ được giữ theo `index.gc_deletes`. Nó không thay thế application tombstone bền vững.

### Optimistic concurrency bằng seq_no và primary_term

Khi ứng dụng đọc một document, Elasticsearch trả `_seq_no` và `_primary_term`. Có thể dùng chúng để chỉ xóa nếu document chưa bị thay đổi sau lần đọc:

~~~http
DELETE /orders/_doc/order-42?if_seq_no=362&if_primary_term=2
~~~

Nếu document đã thay đổi, Elasticsearch trả version conflict và không xóa document mới hơn.

Cơ chế này phù hợp với thao tác người dùng đọc rồi xóa theo snapshot. Nó không thay thế source revision trong event stream: revision của database và sequence number của Elasticsearch thuộc hai miền khác nhau.

## 15. Routing phải nhất quán khi xóa và ghi tombstone

Nếu document được index bằng custom routing, thao tác Delete API phải dùng đúng routing để đến cùng shard.

Ví dụ index:

~~~http
PUT /orders/_doc/order-42?routing=customer-7
{
  "customerId": "customer-7",
  "status": "PAID"
}
~~~

Delete cũng phải dùng routing:

~~~http
DELETE /orders/_doc/order-42?routing=customer-7
~~~

Nếu mapping yêu cầu routing và request thiếu routing, Elasticsearch từ chối thao tác. Nếu request dùng sai routing, nó có thể tìm ở shard khác và không xóa được document cần xóa.

Với application tombstone, phải dùng cùng ID và routing đã dùng khi index document active. Nếu routing key thay đổi theo thời gian, cần biết routing cũ để xóa hoặc thay thế document cũ đúng shard.

Routing nên là một phần của event contract hoặc có thể được xác định ổn định từ ID.

## 16. Delete by query không thay thế delete event theo từng entity

Elasticsearch cung cấp Delete by Query API:

~~~http
POST /orders/_delete_by_query
{
  "query": {
    "term": {
      "status": "CANCELLED"
    }
  }
}
~~~

API này phù hợp cho tác vụ bảo trì hoặc xóa một tập document theo điều kiện.

Tuy nhiên, nó không phải lựa chọn mặc định để truyền từng delete event từ database:

- Elasticsearch lấy snapshot dữ liệu tại thời điểm request bắt đầu.
- Các document phù hợp được xóa bằng internal versioning.
- Nếu document thay đổi sau khi snapshot được lấy nhưng trước khi thao tác xóa chạy, có thể phát sinh version conflict.
- Tác vụ lớn có thể chạy lâu hoặc chạy bất đồng bộ.
- Request không tự mang source revision riêng của từng entity.

Nếu đồng bộ CDC, consumer nên xử lý event theo ID và source revision. Delete by query nên dành cho tác vụ quản trị có phạm vi rõ ràng.

## 17. Tái tạo entity sau khi đã xóa

Có hai loại yêu cầu khác nhau:

1. Entity bị xóa vĩnh viễn, không được phép xuất hiện lại.
2. Entity có thể được tạo lại theo nghiệp vụ.

Nếu entity được tạo lại, revision mới phải lớn hơn tombstone revision.

Ví dụ:

| Revision | Operation | Kết quả |
|---:|---|---|
| 20 | UPSERT | Document active |
| 21 | DELETE | Tombstone |
| 22 | UPSERT | Document active trở lại |
| 20 | UPSERT đến trễ | Bị từ chối |
| 21 | DELETE duplicate | Được nhận diện là duplicate/stale |

Nếu nghiệp vụ cấm tạo lại sau khi xóa, consumer cần một trạng thái hoặc registry cho biết ID đó đã bị retire. Một sự kiện upsert có revision lớn hơn vẫn không nên tự động kích hoạt lại entity nếu source policy không cho phép.

Tombstone chỉ giải quyết thứ tự và version. Quyết định một entity có thể được tạo lại hay không vẫn là quy tắc nghiệp vụ của nguồn dữ liệu.

## 18. Khi nào có thể thu gom tombstone?

Giữ tombstone vĩnh viễn có thể làm index tăng dần. Tuy nhiên, xóa tombstone quá sớm sẽ mở lại khả năng hồi sinh.

Chỉ nên thu gom tombstone khi hệ thống chứng minh được rằng không còn sự kiện cũ nào có thể đến.

Các yếu tố cần tính:

- Thời gian lưu event trong broker.
- Thời gian consumer có thể offline.
- Thời gian retry và dead-letter replay.
- Khả năng khôi phục từ backup hoặc snapshot cũ.
- Quy trình reindex/rebuild read model.
- Thời gian lưu CDC log ở database.
- Các nguồn ghi khác có thể phát lại dữ liệu cũ.

Nếu không có giới hạn replay đáng tin cậy, hãy giữ tombstone hoặc giữ một high-watermark version bền vững cho ID đó.

Một chiến lược có thể là:

1. Giữ tombstone trong index trong một khoảng thời gian.
2. Sau khi mọi consumer đã vượt qua checkpoint liên quan, chuyển ID và revision sang một registry nhỏ hơn.
3. Khi nhận upsert, kiểm tra high-watermark trước khi ghi.
4. Chỉ loại bỏ registry khi nguồn dữ liệu và mọi đường replay đã bảo đảm không thể phát lại revision cũ.

Nếu registry nằm ở index khác, cần giải quyết race giữa kiểm tra registry và ghi document. Hai thao tác trên hai index không có transaction nguyên tử. Có thể dùng một service ghi duy nhất, partition theo entity, hoặc đặt tombstone cùng document để tránh cửa sổ cạnh tranh này.

## 19. Xây dựng transactional outbox cho delete

Ví dụ một service xóa đơn hàng trong database:

~~~java
@Transactional
public void deleteOrder(String orderId) {

    Order order = orderRepository.findById(orderId)
        .orElseThrow();

    long nextRevision = order.getRevision() + 1;

    outboxRepository.save(
        new OutboxEvent(
            UUID.randomUUID().toString(),
            orderId,
            nextRevision,
            "ORDER_DELETED",
            Instant.now()
        )
    );

    orderRepository.delete(order);
}
~~~

Ví dụ này mô tả ý tưởng; phần cập nhật revision và xóa row phải được triển khai sao cho revision cuối cùng được giữ trong outbox trong cùng transaction.

Relay đọc outbox và publish event. Consumer áp dụng tombstone vào Elasticsearch.

Outbox cần có:

- `event_id` duy nhất.
- `aggregate_id`.
- `aggregate_revision`.
- `event_type`.
- Payload hoặc metadata cần thiết.
- Trạng thái publish/checkpoint.
- Thời điểm tạo.

Không xóa outbox event ngay khi gửi message nếu cơ chế relay cần retry hoặc audit. Chính sách cleanup phải dựa trên checkpoint và retention của broker.

Nếu dùng CDC, có thể bỏ relay riêng nhưng vẫn cần bảo đảm log retention và delete event được phát đầy đủ.

## 20. Bulk synchronization và delete tombstone

Khi có nhiều event, có thể gom các thao tác thành Bulk API. Mỗi action cần mang version của chính entity đó.

Ví dụ bulk index hai tombstone:

~~~http
POST /orders-v1/_bulk
{"index":{"_id":"order-42","version":18,"version_type":"external"}}
{"id":"order-42","sourceRevision":18,"deleted":true,"deletedAt":"2026-11-13T10:15:30Z","lastEventId":"evt-9f8a"}
{"index":{"_id":"order-43","version":31,"version_type":"external"}}
{"id":"order-43","sourceRevision":31,"deleted":true,"deletedAt":"2026-11-13T10:16:00Z","lastEventId":"evt-9f8b"}
~~~

Bulk API trả kết quả cho từng item. Một request có thể có một số item thành công và một số item thất bại.

Consumer cần:

- Đọc trạng thái từng item.
- Retry lỗi tạm thời như timeout hoặc unavailable.
- Nhận diện version conflict do event cũ.
- Đưa lỗi mapping hoặc dữ liệu sai vào dead-letter queue.
- Chỉ commit/ack checkpoint phù hợp sau khi xử lý từng item.
- Không coi toàn bộ bulk request thành công chỉ vì HTTP response trả 200.

Với message broker partitioned, hãy bảo đảm checkpoint không nhảy qua một event chưa được xử lý thành công nếu consumer yêu cầu bảo toàn thứ tự trong partition.

## 21. Alias và rollover khi đồng bộ xóa

Nếu ứng dụng ghi qua alias trỏ đến nhiều index hoặc có rollover, cần xác định document có thể tồn tại ở những index nào.

Ví dụ:

- `orders-000001` chứa document trước rollover.
- Alias `orders-write` chuyển sang `orders-000002`.
- Một event xóa đến sau rollover.

Nếu consumer chỉ ghi tombstone vào write index mới, document cũ ở `orders-000001` có thể vẫn xuất hiện khi search qua alias đọc gồm cả hai index.

Một số nguyên tắc:

- Dùng một chiến lược index ổn định cho mỗi entity nếu cần update/delete theo ID.
- Nếu rollover làm cùng ID có thể xuất hiện ở nhiều backing index, delete phải xác định các index có thể chứa document.
- Với data stream, không thể gửi delete trực tiếp vào tên data stream; cần target backing index cụ thể.
- Giữ cùng routing key cho upsert và delete.
- Đảm bảo alias đọc không trả document cũ từ index trước.

Nếu cần entity mutable theo ID, một regular index hoặc write alias có quy tắc routing rõ ràng thường dễ quản lý hơn data stream append-only.

## 22. Rebuild index mà không làm hồi sinh document đã xóa

Một lần reindex hoặc rebuild read model có thể đọc snapshot cũ trong khi CDC tiếp tục phát sự kiện mới.

Ví dụ:

1. Bắt đầu snapshot database tại checkpoint C100.
2. Trong lúc snapshot chạy, đơn hàng bị xóa ở checkpoint C120.
3. Snapshot vẫn chứa đơn hàng vì nó được chụp trước khi xóa.
4. Consumer nạp snapshot vào index mới.
5. CDC event DELETE C120 được phát lại.

Nếu bỏ qua delete event hoặc checkpoint sai, document từ snapshot có thể tồn tại trong index mới dù nguồn đã xóa.

Một quy trình rebuild an toàn:

1. Chọn checkpoint nguồn C100.
2. Tạo index đích mới.
3. Nạp snapshot nhất quán tại C100.
4. Thu thập mọi thay đổi sau C100, bao gồm delete events.
5. Áp dụng các thay đổi theo source revision hoặc change position.
6. Đợi consumer đạt checkpoint mục tiêu.
7. Đối soát trạng thái với nguồn.
8. Chuyển read alias sang index mới.
9. Giữ index cũ đủ lâu để rollback theo quy trình.

Nếu snapshot và CDC không có một ranh giới nhất quán, có thể bỏ sót update hoặc delete giữa hai bước. Tombstone không thể sửa một checkpoint sai hoặc một event xóa đã bị mất.

## 23. Phân biệt source revision, Elasticsearch version và sequence number

Ba loại số thường bị dùng lẫn nhau:

| Giá trị | Ai tạo? | Dùng để làm gì? |
|---|---|---|
| Source revision | Database hoặc event source | Sắp thứ tự thay đổi nghiệp vụ của một entity |
| Elasticsearch `_version` | Elasticsearch hoặc external version do request gửi | Kiểm soát version của document trong index |
| `_seq_no` + `_primary_term` | Primary shard Elasticsearch | Optimistic concurrency cho thao tác dựa trên trạng thái đã đọc |

Ví dụ:

- Database order revision 18 bị xóa.
- Elasticsearch document đang có `_version` 17.
- Thao tác tombstone gửi external version 18.
- Elasticsearch chấp nhận tombstone và lưu version 18.
- `_seq_no` có thể là 900 và `_primary_term` là 3.

Các số này không nhất thiết bằng nhau. Source revision 18 không phải `_seq_no` 18.

Nếu ứng dụng lấy `_seq_no` từ một SearchHit rồi dùng nó làm source revision trong message broker, hệ thống sẽ trộn hai miền version và dễ phát sinh lỗi khi rebuild index hoặc chuyển sang index khác.

## 24. Đối soát và quan sát luồng xóa

Không nên chỉ kiểm tra rằng consumer không báo lỗi. Một hệ thống đồng bộ cần các số liệu giúp phát hiện delete event bị mất hoặc stale event bị chấp nhận.

Một số metric nên theo dõi:

- Số lượng delete event nhận được.
- Số lượng tombstone được ghi thành công.
- Số lượng external version conflict.
- Số lượng stale event bị bỏ qua.
- Số lượng duplicate event.
- Số lượng lỗi mapping hoặc serialization.
- Tuổi của event cũ nhất chưa được xử lý.
- Consumer lag và checkpoint.
- Số tombstone theo index và theo thời gian.
- Số document active trong Elasticsearch so với nguồn.
- Số ID vẫn tồn tại trong Elasticsearch nhưng đã bị xóa ở database.

Khi phát hiện chênh lệch, cần có quy trình reconciliation:

1. Xác định ID và revision nguồn mới nhất.
2. Đọc trạng thái document hoặc tombstone trong Elasticsearch.
3. So sánh source revision.
4. Nếu Elasticsearch thấp hơn, phát lại event mới nhất hoặc ghi lại trạng thái nguồn bằng external version.
5. Nếu Elasticsearch cao hơn, điều tra event đến sai thứ tự hoặc nguồn revision bị reset.
6. Ghi lại kết quả reconciliation để tránh lặp vô hạn.

Đối soát nên chạy định kỳ và có thể chạy theo từng partition hoặc từng khoảng ID để kiểm soát tải.

## 25. Những lỗi thường gặp

**Chỉ gọi Delete API rồi cho rằng đã chống hồi sinh.** Delete metadata chỉ được giữ theo `index.gc_deletes`, mặc định 60 giây. Nó không phải tombstone ứng dụng bền vững.

**Phát delete event sau khi xóa database mà không có outbox hoặc CDC.** Nếu tiến trình chết sau commit nhưng trước publish, event có thể bị mất.

**Không gắn revision vào delete event.** Consumer không thể xác định delete event đến trước hay sau một update khác của cùng entity.

**Dùng timestamp làm version.** Timestamp có thể trùng hoặc lệch clock. Hãy dùng revision có thứ tự được đảm bảo tại nguồn.

**Dùng external version nhưng quên version của tombstone.** Nếu tombstone được index mà không có version nguồn, một upsert cũ vẫn có thể ghi đè nó theo quy tắc version hiện hành.

**Dùng `external_gte` tùy tiện.** Event khác nội dung nhưng cùng revision có thể ghi đè nhau. Dùng strict external và xử lý duplicate rõ ràng.

**Coi mọi 409 là duplicate hợp lệ.** Hãy xác định đó là version conflict do stale event hay một lỗi khác. Cùng revision nhưng khác event cần được điều tra.

**Xóa tombstone ngay sau khi broker ack.** Broker ack không chứng minh mọi consumer, backup, replay hoặc rebuild đã vượt qua event đó.

**Dùng kho tombstone riêng mà không kiểm soát race.** Kiểm tra tombstone rồi index ở một index khác có thể có cửa sổ mà delete và upsert chạy đồng thời.

**Không giữ routing khi xóa.** Delete hoặc tombstone có thể đi đến shard khác với document cũ.

**Dùng delete_by_query cho CDC từng entity.** API này dùng snapshot và internal versioning, không mang source revision riêng cho từng entity.

**Chỉ dùng `@Version` rồi cho rằng đã có tombstone.** `@Version` giúp kiểm soát version của document khi ghi. Nó không giữ một document đã xóa sau khi Delete API hoàn tất.

**Nhầm SeqNoPrimaryTerm với revision nguồn.** Đây là metadata optimistic concurrency của Elasticsearch, không phải sequence của database.

**Để snapshot rebuild chạy sau CDC mà không có checkpoint chung.** Snapshot cũ có thể nạp lại dữ liệu đã bị xóa nếu delete event bị bỏ qua.

**Để một alias đọc nhiều backing index giữ bản cũ.** Tombstone trong write index mới không tự xóa document trùng ID trong backing index cũ.

**Giữ toàn bộ payload nhạy cảm trong tombstone.** Tombstone nên tối giản và tuân thủ yêu cầu xóa dữ liệu của nghiệp vụ.

## 26. Quy trình thiết kế truyền thay đổi xóa an toàn

Có thể triển khai theo các bước:

1. Xác định nguồn dữ liệu có thể phát delete event bằng CDC hay transactional outbox.
2. Thiết kế event contract có ID, operation, source revision, event ID và routing.
3. Bảo đảm revision tăng đơn điệu cho mọi thay đổi, bao gồm cả delete và recreate.
4. Chọn hard delete hoặc application tombstone theo yêu cầu replay và retention.
5. Nếu cần chống hồi sinh lâu dài, giữ tombstone document hoặc high-watermark bền vững.
6. Dùng external versioning để từ chối sự kiện cũ.
7. Dùng strict `external` nếu cần phát hiện event trùng revision; chỉ dùng `external_gte` khi semantics được thiết kế rõ.
8. Với Spring Data, phân biệt `@Version`, `@Document.versionType` và `SeqNoPrimaryTerm`.
9. Với CDC event, truyền chính xác source revision vào version metadata của request.
10. Xử lý 409 theo trạng thái hiện tại, không bỏ qua tất cả conflict.
11. Bảo đảm routing và index target nhất quán.
12. Xử lý Bulk API theo từng item và quản lý checkpoint.
13. Thiết kế retention tombstone dựa trên replay, backup và rebuild horizon.
14. Xây dựng quy trình snapshot + CDC catch-up khi rebuild index.
15. Theo dõi stale event, duplicate, consumer lag và reconciliation.
16. Kiểm thử tình huống update cũ đến sau delete, delete đến sau update mới, duplicate delete, recreate và replay sau nhiều ngày.

## 27. Kịch bản kiểm thử quan trọng

Một bộ kiểm thử đồng bộ xóa nên bao gồm các tình huống:

| Kịch bản | Event đến Elasticsearch | Kết quả mong đợi |
|---|---|---|
| Tạo mới | UPSERT revision 1 | Document active |
| Cập nhật | UPSERT revision 2 | Document cập nhật |
| Xóa | DELETE revision 3 | Tombstone revision 3 |
| Update cũ đến trễ | UPSERT revision 2 | Bị từ chối |
| Delete lặp lại | DELETE revision 3 | Nhận diện duplicate |
| Update mới hợp lệ | UPSERT revision 4 | Chỉ được áp dụng nếu nghiệp vụ cho phép recreate |
| Event cùng revision nhưng khác payload | UPSERT revision 3 khác event | Báo lỗi hợp đồng version |
| Replay sau thời gian dài | UPSERT revision 2 sau nhiều ngày | Vẫn bị tombstone revision 3 từ chối |
| Routing sai | DELETE với routing khác | Test phải phát hiện document cũ còn tồn tại |
| Rebuild từ snapshot cũ | Snapshot có revision 2, sau đó replay DELETE revision 3 | Index mới giữ tombstone revision 3 |

Đặc biệt, hãy chạy test replay stale upsert sau khi `index.gc_deletes` đã hết hạn. Nếu test chỉ chạy trong vòng vài giây, nó có thể không phát hiện lỗ hổng của hard delete.

## Kết luận

Truyền thay đổi xóa trong hệ thống đồng bộ đòi hỏi giữ được dấu vết của thao tác xóa và revision của entity. Delete API của Elasticsearch chỉ giữ version của document đã xóa trong khoảng thời gian do `index.gc_deletes` điều khiển, mặc định 60 giây. Khoảng thời gian này hữu ích cho kiểm soát cạnh tranh ngắn hạn nhưng không đủ để bảo vệ trước replay hoặc event đến trễ sau nhiều giờ, nhiều ngày.

Application tombstone giải quyết vấn đề bằng cách giữ một document tối giản có cùng ID, source revision và trạng thái đã xóa. Kết hợp external versioning, Elasticsearch chỉ chấp nhận thay đổi có revision mới hơn. Một upsert cũ không thể ghi đè tombstone còn tồn tại; một lần tạo lại hợp lệ phải có revision lớn hơn và được nghiệp vụ cho phép.

Trong Spring Data Elasticsearch, `@Version` và `@Document.versionType` hỗ trợ version metadata cho thao tác entity; `SeqNoPrimaryTerm` hỗ trợ optimistic concurrency dựa trên trạng thái Elasticsearch đã đọc. Các cơ chế này khác với source revision và application tombstone. Với event CDC cần mang chính xác revision nguồn, hãy bảo đảm version đó được gửi trong request Elasticsearch, xử lý version conflict có kiểm tra và duy trì tombstone qua mọi khoảng thời gian replay hoặc rebuild có thể xảy ra.

Một luồng đồng bộ đáng tin cậy cần kết hợp delete event bền vững từ CDC hoặc transactional outbox, revision tăng đơn điệu, tombstone đủ lâu, idempotent consumer, routing nhất quán và quy trình reconciliation. Khi các thành phần này cùng được thiết kế, thao tác xóa có thể được truyền qua các consumer bất đồng bộ mà không làm dữ liệu cũ hồi sinh.

## Tài liệu tham khảo

- [Elasticsearch — Delete a document](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete)
- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Elasticsearch — General index settings (index.gc_deletes)](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index-modules)
- [Elasticsearch — Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch — Delete by query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query)
- [Elasticsearch — Soft deletes and retention leases](https://www.elastic.co/docs/deploy-manage/tools/cross-cluster-replication)
- [Spring Data Elasticsearch — Core concepts and entity state detection](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/core-concepts.html)
- [Spring Data Elasticsearch — @Document API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/Document.html)
- [Spring Data Elasticsearch — Document.VersionType API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/Document.VersionType.html)
- [Spring Data Elasticsearch — SeqNoPrimaryTerm API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/SeqNoPrimaryTerm.html)
- [Spring Data Elasticsearch — IndexQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/IndexQueryBuilder.html)

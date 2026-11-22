# Thiết kế thông điệp thay đổi và id tài liệu ổn định

Khi đồng bộ dữ liệu từ database hoặc message broker sang Elasticsearch, thiết kế message và document ID quyết định việc consumer có thể xử lý lặp, khôi phục sau lỗi và cập nhật đúng document hay không. Nếu mỗi lần nhận message đều tạo document với ID ngẫu nhiên, một event được gửi lại có thể tạo bản ghi trùng. Nếu dùng ID ổn định nhưng message đến sai thứ tự, event cũ vẫn có thể ghi đè trạng thái mới.

Một thiết kế tốt cần tách rõ ba định danh: event ID nhận diện một thông điệp; aggregate ID nhận diện thực thể nghiệp vụ ở nguồn; Elasticsearch document ID nhận diện document đích. Message nên có schema rõ ràng, version nguồn, loại thay đổi và payload đủ để consumer áp dụng. Consumer cần xử lý được giao nhận ít nhất một lần (at-least-once), retry, replay, delete và thay đổi schema.

Bài học này trình bày cách thiết kế event envelope, cách chọn document ID xác định từ khóa nguồn, cách phân biệt snapshot event với delta event, cách dùng outbox/CDC, cách xử lý duplicate và out-of-order delivery, cách đồng bộ xóa, tenant/routing, bulk failure, schema evolution và kiểm thử tính idempotent.

## 1. Bài toán đồng bộ dữ liệu

Giả sử hệ thống bán hàng lưu Product trong database quan hệ và dùng Elasticsearch làm read model cho tìm kiếm. Khi Product thay đổi, một message được gửi tới consumer để cập nhật index products.

Luồng đơn giản:

~~~text
Source database
      |
      | Product changed
      v
Change event / Outbox / CDC
      |
      v
Message broker
      |
      v
Elasticsearch consumer
      |
      | index / update / delete
      v
Elasticsearch document
~~~

Trong hệ thống phân tán, message có thể được giao lại vì consumer crash, timeout, broker redelivery hoặc retry. Event có thể đến trùng, đến trễ hoặc sai thứ tự. Nếu thiết kế ID và message không phù hợp, các tình huống đó gây:

- Một thực thể nguồn tạo nhiều document trùng lặp.
- Event cũ ghi đè dữ liệu mới.
- Một delete bị event cũ làm sống lại document.
- Một delta event bị áp dụng hai lần.
- Consumer không thể replay sau khi sửa bug.
- Không xác định được message nào đã gây ra trạng thái hiện tại.

Elasticsearch thường đóng vai trò projection/read model. Database hoặc domain service là nguồn sự thật (source of truth); message mang thông tin để xây dựng lại projection. Thiết kế cần cho phép projection hội tụ về trạng thái nguồn.

## 2. Phân biệt event ID, aggregate ID và document ID

Ba loại ID có mục đích khác nhau:

| Định danh | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| eventId | Đây là message cụ thể nào? | evt-8d31... |
| aggregateId | Thực thể nghiệp vụ nào đã thay đổi? | product-100 |
| Elasticsearch _id | Document đích nào đại diện cho thực thể/projection này? | tenant-7:product-100 |

Một Product có thể phát sinh nhiều event:

~~~text
Product product-100
    |
    +-- ProductCreated       eventId = evt-001
    +-- ProductPriceChanged  eventId = evt-002
    +-- ProductRenamed       eventId = evt-003
    +-- ProductDeleted       eventId = evt-004
~~~

Các event có eventId khác nhau nhưng cùng aggregateId. Nếu mỗi event đại diện cho trạng thái mới nhất của cùng một Product document, chúng phải cập nhật cùng một Elasticsearch _id.

Không dùng eventId làm document ID cho materialized view một-document-per-product. Làm vậy sẽ tạo một document mới cho mỗi thay đổi, thay vì cập nhật projection hiện tại.

Ngược lại, nếu index được thiết kế như event history, mỗi event là một document riêng thì eventId có thể là _id phù hợp. Hãy chọn ID theo mô hình dữ liệu đích, không chọn theo tên message.

## 3. Thiết kế event envelope

Một event nên có envelope thống nhất, chứa metadata độc lập với payload nghiệp vụ:

~~~json
{
  "eventId": "evt-01J8Z7K4Y3",
  "eventType": "ProductSnapshotUpdated",
  "schemaVersion": 2,
  "aggregateType": "Product",
  "aggregateId": "product-100",
  "aggregateVersion": 18,
  "tenantId": "tenant-7",
  "occurredAt": "2026-11-13T09:15:30Z",
  "producer": "catalog-service",
  "correlationId": "req-42",
  "payload": {
    "sku": "KB-100",
    "name": "Wireless Keyboard",
    "category": "accessories",
    "price": 1299000,
    "active": true
  }
}
~~~

Ý nghĩa các field:

| Field | Mục đích |
|---|---|
| eventId | ID duy nhất của lần phát event; dùng tracing hoặc deduplication |
| eventType | Loại thay đổi để consumer chọn cách xử lý |
| schemaVersion | Version schema của payload |
| aggregateType | Loại thực thể nguồn |
| aggregateId | Khóa ổn định của thực thể nguồn |
| aggregateVersion | Version tăng đơn điệu của aggregate tại nguồn |
| tenantId | Phạm vi tenant nếu dữ liệu đa tenant |
| occurredAt | Thời điểm thay đổi xảy ra ở nguồn |
| producer | Service phát event |
| correlationId | Liên kết event với request/workflow |
| payload | Dữ liệu nghiệp vụ cần đồng bộ |

Không phải hệ thống nào cũng cần mọi field. Tuy nhiên, eventId, loại event, aggregate identity, version và schema version thường rất hữu ích khi xử lý duplicate, ordering và replay.

### 3.1. occurredAt không thay thế aggregateVersion

Timestamp không phải cách an toàn để quyết định event nào mới hơn:

- Đồng hồ giữa các service có thể lệch.
- Hai event có thể có cùng timestamp.
- Độ chính xác timestamp có thể thấp hơn tốc độ thay đổi.
- Event có thể được publish trễ dù xảy ra trước.

Nếu nguồn có version hoặc sequence tăng đơn điệu theo aggregate, hãy dùng giá trị đó để so sánh thứ tự. occurredAt phục vụ audit và quan sát; aggregateVersion phục vụ kiểm soát thứ tự.

### 3.2. eventId cần ổn định khi retry

Khi publisher retry cùng một event, giữ nguyên eventId. Không tạo UUID mới mỗi lần gửi lại, vì consumer sẽ coi mỗi lần retry là event khác nhau.

Nếu event được ghi vào outbox, tạo eventId trong transaction nguồn và lưu cùng outbox record. Dispatcher có thể gửi lại record đó nhiều lần mà không đổi ID.

### 3.3. Message key và eventId không giống nhau

Với broker hỗ trợ partition key như Kafka:

- Message key thường là aggregateId để các event của cùng aggregate đi vào cùng partition và có thứ tự trong partition.
- eventId là định danh duy nhất của từng message.

Ví dụ:

~~~text
Kafka key: product-100
eventId:   evt-001
eventType: ProductPriceChanged
~~~

Dùng aggregateId làm key giúp duy trì ordering theo key trong phạm vi partition, nhưng consumer vẫn nên kiểm tra aggregateVersion. Retry, nhiều luồng xử lý hoặc các nguồn phát khác nhau có thể làm thứ tự nghiệp vụ phức tạp hơn.

## 4. Chọn snapshot event hay delta event

Payload event có thể mô tả trạng thái đầy đủ sau thay đổi (snapshot) hoặc chỉ mô tả phần thay đổi (delta).

### 4.1. Snapshot event

Snapshot chứa toàn bộ trạng thái cần để dựng document:

~~~json
{
  "eventType": "ProductSnapshotUpdated",
  "aggregateId": "product-100",
  "aggregateVersion": 18,
  "payload": {
    "sku": "KB-100",
    "name": "Wireless Keyboard",
    "price": 1299000,
    "active": true
  }
}
~~~

Consumer có thể index toàn bộ payload vào document với ID ổn định. Nếu cùng snapshot được xử lý lại, document vẫn có cùng trạng thái cuối.

Snapshot thường dễ làm idempotent hơn vì thao tác có semantics “đặt document thành trạng thái này”.

### 4.2. Delta event

Delta chỉ chứa thay đổi:

~~~json
{
  "eventType": "ProductPriceIncreased",
  "aggregateId": "product-100",
  "aggregateVersion": 18,
  "payload": {
    "priceDelta": 50000
  }
}
~~~

Consumer có thể cộng delta vào giá hiện tại. Nhưng nếu message được giao hai lần, phép cộng có thể chạy hai lần:

~~~text
Giá ban đầu:       1.000.000
Event delta:       +50.000
Sau lần đầu:       1.050.000
Sau lần retry:     1.100.000  <- sai
~~~

Delta event cần deduplication bền vững, kiểm tra version hoặc một cơ chế áp dụng event đúng một lần về mặt nghiệp vụ. Chỉ dùng stable document ID không đủ để ngăn một phép cộng bị lặp.

### 4.3. Chọn loại event theo khả năng dựng projection

| Tình huống | Thiết kế thường phù hợp |
|---|---|
| Đồng bộ một document đại diện trạng thái hiện tại | Snapshot |
| Event stream cần ghi nhận mọi thay đổi nghiệp vụ | Delta/domain event |
| Consumer cần replay độc lập và xây lại index | Snapshot hoặc event đủ dữ liệu để tái dựng |
| Chỉ có delta nhưng cần projection hiện tại | Delta + version/deduplication và quy tắc fold rõ ràng |
| Dữ liệu lớn, event nhỏ | Delta có thể tiết kiệm băng thông nhưng tăng độ phức tạp consumer |

Không có lựa chọn chung cho mọi hệ thống. Nếu ưu tiên consumer đơn giản và replay an toàn, snapshot event thường là lựa chọn dễ vận hành.

## 5. Thiết kế Elasticsearch document ID ổn định

Đối với một document đại diện cho một thực thể nguồn, ID nên được tạo xác định từ khóa nguồn:

~~~text
Elasticsearch _id = source aggregate ID
~~~

Ví dụ Product có ID product-100:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String sku;
    private String name;
    private Long price;
}
~~~

Khi map event:

~~~java
ProductDocument document = new ProductDocument();
document.setId(event.aggregateId());
document.setSku(event.payload().sku());
document.setName(event.payload().name());
document.setPrice(event.payload().price());

operations.save(document);
~~~

Lần đầu Elasticsearch tạo document với ID product-100. Lần sau cùng aggregateId, thao tác save index lại cùng document thay vì sinh một document khác.

### 5.1. Vì sao không dùng ID ngẫu nhiên?

Ví dụ không phù hợp cho projection một-document-per-product:

~~~java
document.setId(UUID.randomUUID().toString());
operations.save(document);
~~~

Nếu broker redelivery event, UUID mới tạo document mới. Sau nhiều lần retry, index chứa nhiều bản sao của cùng Product.

ID ngẫu nhiên chỉ phù hợp khi mỗi lần ghi thực sự là một record độc lập, ví dụ event history hoặc audit log. Với projection trạng thái hiện tại, dùng khóa nguồn xác định.

### 5.2. Dùng repository save

Repository cũng sử dụng ID của entity:

~~~java
ProductDocument document = mapper.toDocument(event);
repository.save(document);
~~~

Nếu document có @Id được gán cùng một giá trị cho mọi lần xử lý của cùng aggregate, save sẽ index vào cùng _id.

Không để ID null nếu mục tiêu là upsert idempotent. Khi ID null, Elasticsearch có thể tự sinh ID và mỗi lần retry trở thành một document khác.

### 5.3. Dùng IndexQuery trong bulk

Với bulk indexing, đặt ID rõ ràng cho từng operation:

~~~java
IndexQuery query = new IndexQueryBuilder()
        .withId(document.getId())
        .withObject(document)
        .build();

operations.bulkIndex(
        List.of(query),
        BulkOptions.defaultOptions(),
        IndexCoordinates.of("products"));
~~~

ID do ứng dụng gán bảo đảm cùng source entity luôn nhắm tới cùng document đích. Kiểm tra bulk response từng item; không giả định toàn bộ batch thành công chỉ vì request HTTP thành công.

## 6. Tạo ID cho dữ liệu đa tenant

Nếu hai tenant có thể cùng dùng một khóa cục bộ như product-100, ID chỉ dựa trên productId sẽ gây collision giữa tenant.

Dùng composite identity:

~~~text
_id = tenantId + ":" + productId
~~~

Ví dụ:

~~~text
tenant-7:product-100
tenant-9:product-100
~~~

Hai document có ID khác nhau dù productId ở từng tenant giống nhau.

### 6.1. Tránh composite key mơ hồ

Ghép chuỗi bằng dấu phân cách chỉ an toàn nếu các thành phần không chứa delimiter hoặc có quy tắc escaping:

~~~text
tenant:a + ":" + product:b
tenant:a:product:b
~~~

Nếu không có quy tắc encoding, hai bộ thành phần khác nhau có thể tạo cùng chuỗi. Có thể dùng length-prefix, canonical JSON hoặc encode từng thành phần trước khi ghép.

Ví dụ length-prefix:

~~~text
7:tenant-7|11:product-100
~~~

Trong nhiều hệ thống, UUID nguồn đã đủ duy nhất toàn cục. Khi đó có thể dùng UUID làm document ID và lưu tenantId như field để filter/authorization.

### 6.2. Hash composite key

Nếu composite key dài hoặc chứa dữ liệu không nên xuất hiện trong URL/log, có thể hash canonical key:

~~~java
String canonicalKey = tenantId + "\u0000" + productId;
String documentId = sha256Hex(canonicalKey);
~~~

Hash cho ID cố định, độ dài đều và không để lộ trực tiếp thành phần gốc. Tuy nhiên:

- Cùng canonical input phải luôn tạo cùng hash.
- Quy tắc canonicalization phải ổn định.
- Chọn hash đủ mạnh để xác suất collision không đáng kể.
- Nếu cần ngăn đoán ID từ dữ liệu ít entropy, hash thường có thể bị dò; cân nhắc keyed HMAC và quản lý khóa.
- Không thay thuật toán/secret HMAC mà không có kế hoạch migration ID.

Nếu khóa nguồn đã là opaque UUID, hash thường không đem lại lợi ích đáng kể.

## 7. Một aggregate có thể tạo nhiều document

Một thực thể nguồn có thể được chiếu thành nhiều loại document:

- Product detail document.
- Product suggestion document.
- Product inventory projection.
- Product per-locale document.

Không dùng cùng _id nếu các projection ở cùng index và cần tồn tại độc lập. Hãy đưa loại projection hoặc locale vào identity:

~~~text
tenant-7:product-100:detail
tenant-7:product-100:suggestion
tenant-7:product-100:inventory
tenant-7:product-100:locale-en
tenant-7:product-100:locale-vi
~~~

Nếu mỗi projection ở index riêng, source ID có thể dùng lại trong từng index. Document identity là duy nhất trong phạm vi index/shard, không phải định danh toàn hệ thống cho mọi loại projection.

## 8. ID ổn định giúp idempotent như thế nào?

Một thao tác idempotent có thể được thực hiện nhiều lần mà trạng thái cuối vẫn giống một lần thực hiện.

Với snapshot event và stable ID:

~~~text
Event evt-001:
  aggregateId = product-100
  payload = { name: "Keyboard", price: 1000 }

Lần 1 -> index _id=product-100
Lần 2 -> index _id=product-100
Lần 3 -> index _id=product-100

Kết quả: vẫn một document product-100 với cùng source state
~~~

Index API với cùng _id thay thế source document trước đó. Đây là nền tảng của idempotent projection cho snapshot.

### 8.1. Stable ID không bảo đảm mọi update đều idempotent

Update dạng gán giá trị:

~~~json
{
  "doc": {
    "price": 1299000
  }
}
~~~

Gửi lại thường giữ cùng giá trị cuối.

Update dạng tăng:

~~~json
{
  "script": {
    "source": "ctx._source.stock += params.delta",
    "params": {
      "delta": 2
    }
  }
}
~~~

Gửi lại sẽ tăng thêm lần nữa. ID ổn định chỉ bảo đảm ghi vào cùng document, không bảo đảm phép biến đổi không bị lặp.

Đối với delta, cần event deduplication, version guard hoặc chuyển đổi thành snapshot trước khi ghi.

## 9. Consumer xử lý at-least-once

Nhiều message broker và consumer framework dùng delivery semantics ít nhất một lần. Điều đó có nghĩa message có thể được giao lại khi consumer không ack, process chết hoặc kết quả xử lý không được xác nhận.

Một tình huống điển hình:

~~~text
1. Consumer nhận event evt-001
2. Consumer index document thành công
3. Process crash trước khi ack broker
4. Broker giao lại evt-001
5. Consumer xử lý lại
~~~

Nếu consumer dùng snapshot và stable _id, lần thứ hai index cùng document sẽ không tạo bản sao. Nếu consumer dùng random ID hoặc delta không có deduplication, dữ liệu có thể sai.

### 9.1. Ack sau khi ghi thành công

Với message broker, chỉ ack/commit offset sau khi Elasticsearch đã xác nhận thao tác tương ứng thành công theo chính sách xử lý.

Không ack trước rồi mới ghi Elasticsearch:

~~~text
ACK broker -> crash -> document chưa được ghi -> mất projection update
~~~

Với bulk, cần xử lý từng item. Nếu một số item thành công và một số thất bại, không retry mù toàn bộ batch nếu thao tác không idempotent. Ack/commit và retry cần tuân thủ semantics của broker, partition và batch.

### 9.2. Exactly-once không tự xuất hiện khi dùng broker

Exactly-once end-to-end giữa database, broker và Elasticsearch là bài toán khác nhau. Broker transaction không tự tạo transaction phân tán với Elasticsearch.

Thiết kế thực tế thường dùng:

- At-least-once delivery.
- Stable document ID.
- Snapshot hoặc delta có version/deduplication.
- Retry có kiểm soát.
- Outbox/CDC.
- Reconciliation và replay.

Mục tiêu là hiệu ứng cập nhật projection đúng một lần về mặt trạng thái, dù message có thể được giao nhiều lần.

## 10. Deduplication bằng eventId

Nếu cần biết một event đã được xử lý hay chưa, eventId có thể dùng làm idempotency key. Consumer cần lưu dấu vết bền vững trong một nơi phù hợp:

~~~text
processed_event
----------------
event_id       primary key
processed_at
consumer_name
result
~~~

Quy trình khái quát:

1. Nhận event.
2. Kiểm tra eventId đã được xử lý chưa.
3. Nếu đã có, bỏ qua theo semantics retry.
4. Nếu chưa có, áp dụng projection.
5. Ghi nhận eventId đã xử lý.
6. Ack message.

### 10.1. Cẩn thận với dual write

Nếu deduplication ledger nằm trong database riêng và document nằm trong Elasticsearch, hai thao tác không nằm trong cùng transaction:

~~~text
Write Elasticsearch succeeds
       |
       | process crashes
       v
Dedup ledger not written
       |
       v
Event redelivered and applied again
~~~

Nếu ghi ledger trước:

~~~text
Write dedup ledger succeeds
       |
       | process crashes
       v
Elasticsearch not updated
       |
       v
Redelivery is skipped incorrectly
~~~

Vì vậy, chỉ lưu eventId trong một database khác không tự tạo exactly-once. Với snapshot event và stable ID, có thể dùng tính idempotent của thao tác index để đơn giản hóa. Với delta event, cần thiết kế lưu version/dedup và khả năng khôi phục nhất quán, hoặc chuyển sang snapshot.

### 10.2. Ghi event marker cùng document?

Có thể lưu lastAppliedEventId hoặc lastAppliedVersion trong Elasticsearch document để kiểm soát xử lý. Nhưng cập nhật marker và dữ liệu phải diễn ra trong cùng một update/script có điều kiện; nếu thực hiện hai request riêng, vẫn có cửa sổ crash.

Với một aggregate, version tăng đơn điệu thường hữu ích hơn chỉ giữ eventId cuối cùng, vì version giúp phát hiện cả event cũ đến sai thứ tự.

## 11. Xử lý event đến sai thứ tự

Giả sử Product có version tăng:

~~~text
Version 16: price = 1000
Version 17: price = 1200
Version 18: price = 1500
~~~

Do retry hoặc partitioning, consumer nhận theo thứ tự:

~~~text
18 -> 16 -> 17
~~~

Nếu mỗi event chỉ index theo stable ID mà không kiểm tra version, trạng thái cuối có thể quay về price = 1200, dù nguồn đã ở version 18.

Stable ID ngăn duplicate document; nó không tự ngăn stale event ghi đè dữ liệu mới.

### 11.1. Dùng aggregateVersion

Mỗi aggregate có version tăng đơn điệu tại nguồn:

~~~json
{
  "aggregateId": "product-100",
  "aggregateVersion": 18,
  "payload": {
    "price": 1500
  }
}
~~~

Consumer chỉ áp dụng event nếu version của nó mới hơn version đang lưu. Nếu event version 16 đến sau document version 18, bỏ qua event cũ.

### 11.2. External versioning

Với snapshot event, Elasticsearch hỗ trợ external versioning cho index operation. Ứng dụng gửi version do nguồn cung cấp:

~~~http
PUT products/_doc/product-100?version=18&version_type=external
{
  "id": "product-100",
  "sourceVersion": 18,
  "name": "Keyboard",
  "price": 1500
}
~~~

Với version_type=external, Elasticsearch chỉ chấp nhận version gửi lên lớn hơn version đang lưu. Event cũ hơn bị từ chối bằng version conflict.

Nếu version bằng nhau và muốn cho phép replay cùng version, Elasticsearch có version_type=external_gte. Chỉ dùng khi cùng một aggregateVersion luôn đại diện cho đúng một payload trạng thái. Nếu hai payload khác nhau cùng version, external_gte có thể cho payload đến sau ghi đè payload trước.

### 11.3. Version nguồn khác với Elasticsearch _version

Elasticsearch có internal _version và sequence number riêng. Chúng không tự đồng bộ với aggregateVersion trong database.

Nếu dùng external versioning, version được gửi phải đến từ nguồn có thứ tự ổn định. Không lấy timestamp hoặc Elasticsearch _version của lần index trước làm thay thế cho version nghiệp vụ nếu không có quy tắc rõ ràng.

### 11.4. Dùng update script để so sánh sourceVersion

Nếu cần partial update thay vì index toàn snapshot, có thể lưu sourceVersion trong document và so sánh trong một update script:

~~~json
{
  "script": {
    "source": "if (ctx._source.sourceVersion == null || params.version > ctx._source.sourceVersion) { ctx._source.price = params.price; ctx._source.sourceVersion = params.version; } else { ctx.op = 'noop'; }",
    "params": {
      "version": 18,
      "price": 1500
    }
  },
  "upsert": {
    "price": 1500,
    "sourceVersion": 18
  }
}
~~~

Script là một thao tác nguyên tử trên document. Cần xác định hành vi khi version bằng nhau, thiếu version và document chưa tồn tại. Với snapshot đầy đủ, external versioning của index action thường đơn giản hơn.

## 12. Thiết kế event delete

Delete event cần mang cùng identity với document được tạo:

~~~json
{
  "eventId": "evt-099",
  "eventType": "ProductDeleted",
  "aggregateType": "Product",
  "aggregateId": "product-100",
  "aggregateVersion": 19,
  "tenantId": "tenant-7",
  "occurredAt": "2026-11-13T10:00:00Z"
}
~~~

Consumer tính đúng document ID rồi xóa:

~~~java
operations.delete(
        event.aggregateId(),
        IndexCoordinates.of("products"));
~~~

Nếu document ID được tạo từ tenantId và aggregateId, delete phải dùng đúng cùng hàm tạo ID:

~~~java
String documentId = documentIdFactory.productId(
        event.tenantId(),
        event.aggregateId());

operations.delete(
        documentId,
        IndexCoordinates.of("products"));
~~~

Không xây ID cho delete bằng một quy tắc khác với ID khi index. Sai khác một ký tự cũng khiến document cũ còn lại.

### 12.1. Event cũ có thể làm sống lại document đã xóa

Một tình huống:

1. Version 19 xóa Product.
2. Consumer xóa document trong Elasticsearch.
3. Event version 18 bị redelivery sau đó.
4. Consumer index snapshot version 18 với cùng _id.

Document đã bị xóa lại xuất hiện. Stable ID không ngăn resurrection này.

### 12.2. Tombstone hoặc versioned delete

Có thể giữ một tombstone document:

~~~json
{
  "_id": "tenant-7:product-100",
  "sourceVersion": 19,
  "deleted": true,
  "deletedAt": "2026-11-13T10:00:00Z"
}
~~~

Consumer chỉ thay đổi document nếu event có version mới hơn tombstone. Search query lọc deleted = false. Một job cleanup có thể xóa tombstone sau khoảng retention đã định, khi hệ thống bảo đảm không còn event cũ có thể được replay.

Một lựa chọn khác là dùng versioned delete/conditional delete theo cơ chế Elasticsearch phù hợp. Tuy nhiên, delete tombstone nội bộ của Elasticsearch có retention hữu hạn; không nên dựa vào nó như một ledger nghiệp vụ lâu dài cho event replay không giới hạn.

### 12.3. Hard delete hay soft delete?

| Cách | Ưu điểm | Hạn chế |
|---|---|---|
| Hard delete ngay | Index chỉ chứa document đang hoạt động | Cần bảo vệ khỏi event cũ làm sống lại |
| Soft delete/tombstone | Giữ version để bỏ qua stale event và replay | Query phải lọc deleted; cần cleanup |
| Delete có version condition | Ngăn một số thao tác cũ theo concurrency token | Cần truyền đúng version và hiểu retention semantics |

Chọn theo thời gian replay tối đa, yêu cầu audit và cách hệ thống phát event. Với đồng bộ có thể replay từ broker/outbox lâu ngày, tombstone hoặc version ledger bền vững thường dễ kiểm soát hơn.

## 13. Transactional Outbox

Một vấn đề phổ biến là dual write giữa database và broker:

~~~text
1. Update Product trong database
2. Publish event lên broker
~~~

Nếu database commit thành công nhưng publish thất bại, Elasticsearch không được cập nhật. Nếu publish thành công nhưng database rollback, consumer nhận event không tương ứng với trạng thái nguồn.

Transactional Outbox ghi thay đổi nghiệp vụ và outbox record trong cùng một transaction database:

~~~text
Database transaction
   |
   +-- UPDATE product
   |
   +-- INSERT outbox_event
   |
   +-- COMMIT
          |
          v
Outbox relay / CDC
          |
          v
Message broker
          |
          v
Elasticsearch consumer
~~~

Ví dụ bảng outbox:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(200) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSON NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Trong cùng transaction:

~~~sql
BEGIN;

UPDATE product
SET price = 1500,
    version = 18
WHERE id = 'product-100';

INSERT INTO outbox_event (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    schema_version,
    payload,
    occurred_at
) VALUES (
    'evt-018',
    'Product',
    'product-100',
    18,
    'ProductSnapshotUpdated',
    2,
    '{"name":"Keyboard","price":1500}',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Relay đọc outbox và publish. Nếu relay crash sau khi publish nhưng trước khi đánh dấu published, event có thể được gửi lại. Consumer vẫn cần idempotency và stable document ID.

## 14. CDC và chuẩn hóa message

Change Data Capture (CDC) đọc transaction log hoặc thay đổi database để phát sự kiện. Một CDC record có thể chứa:

- operation type (insert/update/delete).
- before và after image.
- source metadata như database, table, log position.
- timestamp và transaction metadata.

Không nên để mọi Elasticsearch consumer phụ thuộc trực tiếp vào cấu trúc CDC cụ thể của database nếu có thể tránh. Tạo một bước adapter chuyển CDC record thành domain/projection event ổn định:

~~~text
Database CDC format
       |
       v
CDC adapter
       |
       | normalize fields, IDs and versions
       v
ProductSnapshotUpdated v2
       |
       v
Elasticsearch projection consumer
~~~

Điều này giúp đổi database connector hoặc schema CDC mà không buộc tất cả consumer thay đổi cùng lúc.

### 14.1. Delete trong CDC

Một số CDC connector phát tombstone record sau delete, đặc biệt trong log-compacted topic. Phân biệt:

- Delete event nghiệp vụ có aggregate ID và version.
- Tombstone message của broker dùng để biểu thị xóa key khỏi compacted log.
- Before/after image của CDC.

Adapter cần chuyển chúng thành contract mà consumer hiểu. Không mặc định mọi record có payload null đều có cùng ý nghĩa ở mọi connector.

## 15. Schema evolution của message

Message sống lâu hơn một lần deploy. Producer và consumer có thể được nâng cấp ở thời điểm khác nhau; event cũ có thể được replay sau nhiều tháng.

Đưa schemaVersion vào envelope:

~~~json
{
  "eventType": "ProductSnapshotUpdated",
  "schemaVersion": 2,
  "aggregateId": "product-100",
  "aggregateVersion": 18,
  "payload": {
    "name": "Keyboard",
    "price": 1500,
    "active": true
  }
}
~~~

Khi thêm field:

- Ưu tiên thay đổi additive.
- Consumer cũ nên bỏ qua field không biết nếu format hỗ trợ.
- Field mới có thể optional hoặc có default an toàn.
- Không đổi ý nghĩa field cũ mà vẫn giữ schemaVersion cũ.

Khi đổi kiểu dữ liệu hoặc semantics:

- Tăng schemaVersion.
- Viết mapper/upcaster từ version cũ.
- Kiểm thử replay message cũ.
- Có thể publish event mới hoặc rebuild projection nếu cách chuyển đổi không thể làm tại consumer.

### 15.1. Event type và schema version là hai khái niệm

eventType mô tả ý nghĩa nghiệp vụ, ví dụ ProductDeleted. schemaVersion mô tả cấu trúc payload của loại event đó. Không dùng schemaVersion để thay eventType hoặc ngược lại.

### 15.2. Không dùng Java class name làm contract

Không nên gửi tên package/class Java làm event type nếu producer và consumer cần độc lập ngôn ngữ hoặc package có thể refactor. Dùng tên event ổn định trong schema, ví dụ ProductSnapshotUpdated.

### 15.3. Giữ lại dữ liệu đủ để replay

Nếu event chỉ chứa productId và consumer phải gọi lại database nguồn để lấy trạng thái, replay có thể nhận trạng thái hiện tại chứ không phải trạng thái tại thời điểm event. Điều đó có thể đúng nếu mục tiêu là eventual projection mới nhất, nhưng không phù hợp nếu cần tái tạo từng bước lịch sử.

Chọn payload dựa trên semantics:

- Snapshot event lưu trạng thái tại version đó.
- Reference event chỉ lưu ID và yêu cầu source read có kiểm soát.
- Delta event lưu thay đổi cùng version và quy tắc áp dụng.

Không để consumer vô tình trộn semantics của ba loại này.

## 16. Ánh xạ message sang document

Tạo một mapper riêng để chuyển event thành document:

~~~java
public class ProductDocumentMapper {

    public ProductDocument toDocument(ProductSnapshotUpdated event) {
        ProductDocument document = new ProductDocument();
        document.setId(documentId(event.tenantId(), event.aggregateId()));
        document.setTenantId(event.tenantId());
        document.setSourceVersion(event.aggregateVersion());
        document.setSku(event.payload().sku());
        document.setName(event.payload().name());
        document.setPrice(event.payload().price());
        document.setActive(event.payload().active());
        document.setUpdatedAt(event.occurredAt());
        document.setDeleted(false);
        return document;
    }

    private String documentId(String tenantId, String aggregateId) {
        return tenantId + ":" + aggregateId;
    }
}
~~~

Mapper có trách nhiệm:

- Tạo ID theo một quy tắc duy nhất.
- Chuyển field từ event schema sang Elasticsearch document.
- Lưu sourceVersion để quan sát/đối soát.
- Áp dụng default và normalization có chủ đích.
- Không phụ thuộc transport metadata không liên quan.

Không tạo document ID rải rác ở nhiều consumer/service. Dùng một DocumentIdFactory hoặc mapper dùng chung để index, update, get và delete thống nhất.

### 16.1. Lưu source metadata cần thiết

Document có thể lưu:

~~~json
{
  "tenantId": "tenant-7",
  "sourceId": "product-100",
  "sourceVersion": 18,
  "sourceUpdatedAt": "2026-11-13T09:15:30Z",
  "projectionVersion": 2,
  "name": "Wireless Keyboard",
  "price": 1299000
}
~~~

Metadata giúp:

- So sánh projection với source.
- Phát hiện document stale.
- Tìm lỗi mapping hoặc event bị bỏ sót.
- Rebuild index theo version.
- Xác định projection schema đã được tạo bằng mapper nào.

Không nhất thiết expose mọi metadata này cho API người dùng; có thể giữ trong document để vận hành.

## 17. Consumer xử lý snapshot event

Consumer đơn giản có thể:

~~~java
public void onProductSnapshot(ProductSnapshotUpdated event) {
    ProductDocument document = mapper.toDocument(event);
    repository.save(document);
}
~~~

Vì ID ổn định và payload là snapshot, xử lý lại cùng event sẽ ghi cùng document. Tuy nhiên, cần thêm kiểm soát version nếu event có thể đến sai thứ tự.

Nếu dùng external versioning, consumer gửi aggregateVersion vào index request. Khi version conflict xảy ra do event cũ, có thể xem đó là stale event đã bị từ chối sau khi xác minh error type. Không bỏ qua mọi lỗi conflict giống nhau; create conflict, external version conflict và OCC conflict có semantics khác nhau.

### 17.1. Nếu consumer nhận cùng version hai lần

Với external version strict, lần thứ hai cùng version có thể bị từ chối vì version không lớn hơn version đã lưu. Consumer có thể coi đây là duplicate/stale event sau khi xác minh document hiện tại có version tương ứng.

Với external_gte, cùng version được chấp nhận. Chỉ dùng khi payload của cùng version luôn giống nhau; nếu không, retry có thể ghi một payload khác có cùng version.

### 17.2. Không ghi đè sourceVersion bằng event thiếu version

Nếu event không có aggregateVersion, không tự gán 0 hoặc timestamp để giả lập thứ tự. Hãy xác định semantics của nguồn:

- Thêm version ở producer.
- Dùng log sequence/CDC position có quy tắc rõ.
- Serialize theo aggregate key.
- Hoặc chấp nhận eventual overwrite và có reconciliation phù hợp.

## 18. Consumer xử lý delta event

Với delta event, consumer cần biết document hiện tại và áp dụng thay đổi:

~~~java
public void onStockChanged(StockChanged event) {
    UpdateQuery update = UpdateQuery.builder(
                    documentIdFactory.productId(
                            event.tenantId(),
                            event.aggregateId()))
            .withScript("""
                ctx._source.stock = params.stock;
                ctx._source.sourceVersion = params.version;
                """)
            .withParams(Map.of(
                    "stock", event.payload().newStock(),
                    "version", event.aggregateVersion()))
            .build();

    operations.update(
            update,
            IndexCoordinates.of("products"));
}
~~~

Ví dụ này gán giá trị stock mới (snapshot của field), không cộng delta. Gán trạng thái tuyệt đối thường dễ retry hơn thao tác cộng/trừ.

Nếu thật sự cần cộng delta, script phải kiểm tra event/version đã áp dụng hay chưa và cập nhật version trong cùng thao tác nguyên tử. Cần xác định cách xử lý khi document chưa tồn tại và khi event bị bỏ qua do version cũ.

### 18.1. Partial update có thể mất dữ liệu nếu event không đủ

Nếu một event snapshot chỉ có một vài field nhưng consumer dùng index toàn document, các field khác có thể bị xóa khỏi source. Nếu dùng partial update, field không có trong payload được giữ nguyên nhưng có thể khiến projection chứa dữ liệu từ nhiều version khác nhau.

Xác định rõ event là:

- Full snapshot: có thể thay toàn document.
- Partial patch: chỉ cập nhật field có mặt.
- Delta: áp dụng phép biến đổi.

Đừng coi ba payload này là tương đương.

## 19. Bulk processing và partial failure

Consumer có thể gom nhiều event thành bulk để tăng throughput:

~~~java
List<IndexQuery> queries = events.stream()
        .map(event -> {
            ProductDocument document = mapper.toDocument(event);
            return new IndexQueryBuilder()
                    .withId(document.getId())
                    .withObject(document)
                    .build();
        })
        .toList();

operations.bulkIndex(
        queries,
        BulkOptions.defaultOptions(),
        IndexCoordinates.of("products"));
~~~

Bulk API xử lý từng item độc lập. Một số item có thể thành công trong khi item khác thất bại. Consumer cần:

- Kiểm tra từng item/failed documents.
- Retry lỗi transient như 429 hoặc một số lỗi 5xx theo policy.
- Xử lý version conflict như stale/duplicate theo semantics.
- Đưa lỗi mapping/schema lâu dài sang DLQ.
- Không ack message chưa được xử lý thành công theo chính sách.
- Giữ correlation giữa bulk item và event gốc.

Nếu retry cả batch, thao tác index snapshot với stable ID thường idempotent; delta event không có deduplication có thể bị áp dụng lặp.

### 19.1. Bulk không phải transaction

Bulk request không rollback các item đã thành công khi một item khác thất bại. Không đánh dấu cả batch thành công chỉ dựa trên HTTP response. Cũng không xóa toàn bộ document thành công để cố giả lập rollback.

### 19.2. Batch có thể chứa nhiều version của cùng aggregate

Nếu một batch có version 17 và 18 cho cùng product, hãy:

- Giữ thứ tự theo aggregate nếu xử lý delta.
- Hoặc chỉ giữ snapshot mới nhất nếu semantics và audit cho phép.
- Dùng external versioning/version guard để event cũ không ghi đè event mới.

Không phụ thuộc thứ tự array trong bulk như một bảo đảm ordering giữa nhiều request hoặc nhiều consumer.

## 20. Routing và stable document identity

Elasticsearch cho phép custom routing để chọn shard. Nếu index document với routing tùy chỉnh, các thao tác get/update/delete/search theo ID cần dùng routing phù hợp.

Ví dụ dùng tenantId làm routing:

~~~text
_id     = tenant-7:product-100
routing = tenant-7
~~~

Khi index:

~~~http
PUT products/_doc/tenant-7:product-100?routing=tenant-7
{
  "tenantId": "tenant-7",
  "sourceId": "product-100",
  "name": "Keyboard"
}
~~~

Khi delete phải dùng cùng routing:

~~~http
DELETE products/_doc/tenant-7:product-100?routing=tenant-7
~~~

Nếu index dùng routing nhưng delete/get không gửi routing, thao tác có thể tìm sai shard hoặc không tìm thấy document.

### 20.1. _id không thay thế routing

ID ổn định xác định document trong shard. Custom routing quyết định shard đích. Với custom routing, cùng một _id nhưng routing khác có thể được định tuyến sang shard khác; không thay đổi routing tùy tiện giữa các event.

### 20.2. Chọn routing key

Routing theo tenant có thể gom dữ liệu tenant vào cùng shard và làm tenant-filtered search hiệu quả hơn. Tuy nhiên, tenant rất lớn có thể tạo hot shard. Cân nhắc phân bố tải, tenant size và query pattern trước khi chọn routing.

Nếu không cần custom routing, để Elasticsearch chọn shard mặc định theo _id đơn giản hơn và giảm nguy cơ quên routing khi update/delete.

## 21. Multi-index, alias và thay đổi projection

Document ID nên ổn định theo aggregate qua các lần cập nhật cùng projection. Khi reindex sang index version mới, giữ nguyên ID:

~~~text
products-v1/_doc/tenant-7:product-100
products-v2/_doc/tenant-7:product-100
~~~

Alias products có thể chuyển từ v1 sang v2 sau khi index mới được dựng và kiểm tra. Nếu ID algorithm thay đổi giữa hai version, cần migration/rebuild có kế hoạch; nếu không, một aggregate có thể có ID khác nhau và tạo document trùng trong index mới.

### 21.1. Projection version khác aggregateVersion

- aggregateVersion cho biết thứ tự thay đổi ở nguồn.
- projectionVersion cho biết schema/logic mapping của document đích.

Ví dụ mapper v2 bổ sung normalizedName. Cùng một aggregateVersion có thể được tái chiếu bởi projectionVersion mới khi rebuild index. Không dùng projectionVersion thay cho source version để bỏ qua event cũ.

### 21.2. Rebuild từ source of truth

Một index có thể được xây lại từ database snapshot hoặc event history. Dùng cùng document ID factory và mapper contract để dữ liệu sau rebuild có cùng identity với dữ liệu đồng bộ incremental.

Nếu rebuild từ snapshot trong khi event mới tiếp tục đến, cần một chiến lược catch-up:

1. Chụp snapshot tại source position/version xác định.
2. Rebuild index mới từ snapshot.
3. Phát lại event sau snapshot position.
4. Kiểm tra projection version/lag.
5. Chuyển alias khi index mới đã hội tụ.

Không chỉ copy document sang index mới rồi chuyển alias nếu còn event chưa áp dụng.

## 22. Xử lý event poison và Dead Letter Queue

Một message có thể không xử lý được vì:

- Payload sai schema.
- Thiếu aggregateId hoặc eventId.
- Field mapping không tương thích.
- Document ID factory lỗi.
- Quyền Elasticsearch không đủ.
- Index hoặc alias không tồn tại.

Phân loại lỗi:

| Lỗi | Cách xử lý |
|---|---|
| Network timeout/429/temporary 5xx | Retry có backoff |
| Version conflict do event cũ | Xác minh version rồi bỏ qua |
| Mapping/parsing error | DLQ và sửa schema/mapper |
| Missing required identity | DLQ hoặc reject producer contract |
| Authentication/authorization | Dừng/retry có giới hạn và cảnh báo cấu hình |
| Unknown index | Retry sau khi xác minh deployment order hoặc DLQ |

DLQ nên giữ event gốc, eventId, aggregateId, version, lỗi, số lần thử và thời điểm cuối. Không log payload nhạy cảm không cần thiết.

Khi replay DLQ, dùng cùng eventId và document ID rule. Nếu event đã stale so với sourceVersion hiện tại, consumer nên bỏ qua theo version guard thay vì ghi ngược projection.

## 23. Observability và đối soát

Một consumer đồng bộ dữ liệu cần đo lường:

- Số event nhận được.
- Số event thành công, duplicate và stale.
- Số version conflict.
- Bulk item failure theo status/error type.
- Retry count và DLQ count.
- Consumer lag và tuổi event.
- Chênh lệch sourceVersion với document sourceVersion.
- Thời gian từ occurredAt đến khi projection được cập nhật.

Log có thể ghi metadata:

~~~text
eventId=evt-018
aggregateType=Product
aggregateId=product-100
aggregateVersion=18
documentId=tenant-7:product-100
result=INDEXED
~~~

Không cần ghi toàn bộ payload nếu chứa dữ liệu nhạy cảm.

### 23.1. Reconciliation

Retry không đảm bảo projection luôn đúng. Có thể cần job đối soát:

1. Đọc source IDs và source versions theo batch.
2. Đọc document IDs/sourceVersion tương ứng từ Elasticsearch.
3. Phát hiện document thiếu, stale hoặc có version cao bất thường.
4. Rebuild snapshot cho các aggregate bị lệch.
5. Ghi metrics và kết quả đối soát.

Reconciliation là cơ chế phát hiện và sửa sai lệch dài hạn, đặc biệt hữu ích khi message bị DLQ hoặc lỗi mapping từng xảy ra.

## 24. Kiểm thử thiết kế message và document ID

Các test nên chứng minh những invariant chính:

### 24.1. Cùng aggregate luôn có cùng document ID

~~~java
@Test
void documentIdIsStableForSameAggregate() {
    String first = documentIdFactory.productId("tenant-7", "product-100");
    String second = documentIdFactory.productId("tenant-7", "product-100");

    assertThat(first).isEqualTo(second);
}
~~~

### 24.2. Hai tenant không collision

~~~java
@Test
void documentIdIncludesTenantIdentity() {
    String tenantA = documentIdFactory.productId("tenant-a", "product-100");
    String tenantB = documentIdFactory.productId("tenant-b", "product-100");

    assertThat(tenantA).isNotEqualTo(tenantB);
}
~~~

### 24.3. Replay cùng snapshot không tạo document trùng

Integration test:

1. Xử lý cùng một snapshot event hai lần.
2. Refresh index nếu test cần search visibility.
3. Search theo aggregateId/tenantId.
4. Xác nhận chỉ có một document và source giống nhau.

### 24.4. Event cũ không ghi đè event mới

1. Xử lý version 18.
2. Xử lý lại version 16.
3. Đọc document.
4. Xác nhận sourceVersion vẫn là 18 và field giữ giá trị của version 18.

### 24.5. Delete không bị stale event làm sống lại

1. Xử lý snapshot version 18.
2. Xử lý delete/tombstone version 19.
3. Gửi lại snapshot version 18.
4. Xác nhận document vẫn deleted hoặc không searchable theo semantics đã chọn.

### 24.6. Delta không bị áp dụng hai lần

Gửi cùng event delta hai lần và xác nhận counter/stock chỉ thay đổi một lần. Nếu test thất bại, cần bổ sung event deduplication hoặc version guard.

### 24.7. Schema compatibility

Test message cũ và message schema version mới qua mapper/upcaster. Xác nhận default, optional field và unknown field có semantics rõ ràng.

### 24.8. Bulk partial failure

Tạo batch gồm item hợp lệ, stale event và item mapping error. Xác nhận consumer phân loại từng item, retry đúng phần cần retry và gửi lỗi lâu dài vào DLQ.

## 25. Các lỗi thiết kế thường gặp

### Dùng UUID mới cho mỗi lần xử lý event

Mỗi retry tạo document khác. Dùng document ID xác định từ aggregate identity.

### Dùng eventId làm document ID cho projection trạng thái

Mỗi thay đổi tạo một document mới. Dùng aggregateId hoặc composite projection key; giữ eventId cho message identity.

### Nghĩ stable ID tự ngăn duplicate delta

Stable ID chỉ chọn document đích. Phép cộng/trừ vẫn có thể chạy hai lần. Dùng snapshot, deduplication hoặc version guard.

### Không có aggregateVersion

Event cũ có thể ghi đè event mới. Thêm version tăng đơn điệu từ source hoặc xác định ordering strategy rõ.

### Dùng timestamp để quyết định event mới nhất

Clock skew và độ chính xác thời gian làm ordering không đáng tin. Dùng source version/sequence.

### Hard delete nhưng vẫn replay event cũ

Event cũ có thể tạo lại document. Dùng versioned delete, tombstone hoặc version ledger bền vững.

### Dùng tenantId trong field nhưng không trong identity

Hai tenant có cùng local ID có thể ghi đè nhau. Dùng UUID toàn cục hoặc composite tenant identity.

### Composite key ghép chuỗi không escaping

Delimiter có thể tạo collision. Dùng canonical encoding hoặc length-prefix.

### Thay đổi ID algorithm khi reindex

Projection mới có thể có document identity khác. Giữ cùng ID factory hoặc thực hiện migration rõ ràng.

### Quên routing khi update/delete

Document được index vào shard theo routing nhưng thao tác sau tìm shard khác. Dùng routing key ổn định và truyền nhất quán.

### Ack message trước khi Elasticsearch ghi thành công

Crash sau ack làm mất projection update. Ack sau khi thao tác đã được xác nhận theo delivery policy.

### Coi bulk là transaction

Một số item có thể thành công, item khác thất bại. Kiểm tra từng item và xử lý selective retry.

### Coi outbox/CDC loại bỏ nhu cầu idempotency

Relay có thể publish lặp. Consumer vẫn phải xử lý redelivery an toàn.

### Ghi dedup ledger và Elasticsearch như hai bước độc lập

Crash giữa hai bước gây mất hoặc lặp thao tác. Thiết kế snapshot idempotent hoặc một quy trình recovery nhất quán.

### Không version hóa event schema

Consumer cũ có thể parse sai payload replay. Thêm schemaVersion và kiểm thử compatibility.

## 26. Quy trình thiết kế đồng bộ dữ liệu

Khi xây consumer cập nhật Elasticsearch:

1. Xác định source of truth và projection/document đích.
2. Xác định một aggregate tạo một hay nhiều document.
3. Tách eventId, aggregateId, aggregateVersion và document ID.
4. Thiết kế event envelope có eventType, schemaVersion, tenant, occurredAt và correlation metadata cần thiết.
5. Chọn snapshot hay delta và ghi rõ semantics payload.
6. Tạo document ID xác định từ source identity; dùng composite key nếu cần tenant/projection scope.
7. Dùng một ID factory thống nhất cho index, get, update và delete.
8. Dùng outbox/CDC để không mất thay đổi giữa database commit và publish.
9. Thiết kế consumer theo at-least-once và idempotent behavior.
10. Dùng aggregateVersion/external versioning hoặc version guard để chặn event cũ.
11. Thiết kế delete/tombstone để stale event không làm sống lại document.
12. Chọn routing ổn định nếu dùng custom routing.
13. Kiểm tra từng bulk item, retry transient errors và đưa poison event vào DLQ.
14. Version hóa message schema và hỗ trợ replay/upcasting.
15. Đo consumer lag, stale event, conflict, DLQ và projection version lag.
16. Có reconciliation/rebuild plan để khôi phục projection.
17. Kiểm thử duplicate, out-of-order, delete, tenant collision, replay và partial bulk failure.

## 27. Tổng kết

Thiết kế message đồng bộ dữ liệu cần tách eventId, aggregateId, aggregateVersion và Elasticsearch document ID. eventId nhận diện một lần thay đổi; aggregateId nhận diện thực thể nguồn; document ID xác định projection đích. Với mô hình một document cho một aggregate, hãy tạo _id xác định từ khóa nguồn thay vì UUID mới mỗi lần xử lý. Với dữ liệu đa tenant hoặc nhiều projection, dùng composite identity có encoding rõ ràng.

Snapshot event chứa trạng thái đầy đủ và thường dễ làm idempotent: xử lý lại cùng snapshot sẽ index cùng document với cùng nội dung. Delta event chỉ mô tả thay đổi nên có thể bị áp dụng hai lần; cần deduplication hoặc version guard. Stable ID cũng không tự giải quyết event đến sai thứ tự. Dùng aggregateVersion hoặc source sequence để ngăn stale event ghi đè dữ liệu mới.

Outbox/CDC giúp truyền thay đổi từ nguồn đáng tin cậy hơn nhưng relay vẫn có thể publish lặp. Consumer cần at-least-once handling, selective retry, kiểm tra bulk item và DLQ. Delete cần cùng document ID/routing với index và phải chống stale event làm sống lại document bằng versioned delete, tombstone hoặc version ledger. Schema version, reconciliation và replay plan giúp projection có thể tiến hóa và khôi phục khi xảy ra lỗi.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – IndexQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/IndexQuery.html)
- [Elasticsearch – Index API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html)
- [Elasticsearch – Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Elasticsearch – Document APIs and routing](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-get.html)
- [Debezium – Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [Debezium – Change Data Capture](https://debezium.io/documentation/reference/stable/)

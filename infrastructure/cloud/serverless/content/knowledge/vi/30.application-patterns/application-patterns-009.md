# Xây dựng bộ lập chỉ mục tìm kiếm từ sự kiện thay đổi dữ liệu

Một ứng dụng thường lưu dữ liệu giao dịch trong database quan hệ nhưng cần tìm kiếm toàn văn, lọc theo nhiều thuộc tính, xếp hạng kết quả hoặc autocomplete. Search engine có thể đáp ứng các truy vấn này tốt hơn database giao dịch, nhưng dữ liệu trong search index phải được cập nhật khi nguồn thay đổi.

Một cách triển khai phù hợp với serverless là tạo **search index projection** từ các sự kiện thay đổi dữ liệu. Khi một bản ghi được tạo, cập nhật hoặc xóa, hệ thống phát sự kiện vào broker. Java function tiêu thụ sự kiện, biến đổi dữ liệu nguồn thành search document rồi cập nhật index.

Mô hình này tách workload tìm kiếm khỏi workload giao dịch. Database nguồn tiếp tục là nơi giữ trạng thái chuẩn; search index là một bản chiếu có thể tái tạo. Vì xử lý sự kiện thường có retry, duplicate và độ trễ, consumer phải xử lý idempotent, kiểm soát thứ tự cập nhật và có quy trình rebuild/reconciliation.

Bài học này trình bày kiến trúc từ transactional outbox hoặc CDC đến Java indexer, cách bootstrap dữ liệu ban đầu, xử lý upsert/delete, kiểm soát bulk/retry/backpressure và xây dựng lại index an toàn.

## 1. Vì sao xây dựng search index từ sự kiện?

Database giao dịch được tối ưu cho tính đúng đắn của transaction và truy cập theo key/relationship. Search engine được tối ưu cho các thao tác như:

- Full-text search và relevance scoring.
- Fuzzy matching, stemming và autocomplete.
- Faceted search và aggregation.
- Lọc theo nhiều field và tổ hợp điều kiện.
- Tìm kiếm trên dữ liệu đã denormalize.
- Truy vấn đọc lớn mà không làm tăng tải lên database giao dịch.

Không nên mặc định chuyển toàn bộ truy vấn nghiệp vụ sang search engine. Những thao tác cần transaction, kiểm tra tồn kho cuối cùng hoặc quyết định quyền truy cập phải xác minh với nguồn dữ liệu chuẩn khi cần.

### 1.1. Search index là dữ liệu dẫn xuất

Database nguồn có thể chứa nhiều bảng liên quan:

~~~text
products
  id, name, description, brand_id, category_id, status

brands
  id, name

categories
  id, name

search document
  product_id
  product_name
  description
  brand_name
  category_name
  searchable_attributes
  source_version
~~~

Search index lưu một projection thuận tiện cho truy vấn. Nếu index bị xóa hoặc mapping thay đổi, hệ thống có thể xây dựng lại từ database/event history.

Vì vậy:

- Database/domain service là nguồn dữ liệu chuẩn.
- Event báo rằng một thay đổi đã xảy ra hoặc mô tả thay đổi.
- Indexer biến đổi sự kiện thành document.
- Search engine lưu projection để phục vụ truy vấn.
- Reconciliation phát hiện và sửa sai lệch.

Không để business logic quan trọng chỉ tồn tại trong search index. Nếu index mất dữ liệu, cần có cách tái tạo.

## 2. Kiến trúc tổng thể

Một kiến trúc phổ biến gồm producer, nguồn sự kiện, broker và consumer:

~~~mermaid
flowchart LR
    A["HTTP command / domain service"] --> B["Source database"]
    B --> O["Outbox row / CDC log"]
    O --> Q["Event broker"]
    Q --> F["Java serverless indexer"]
    F --> T["Transform / enrich"]
    T --> S["Search engine index"]
    C["Search API"] --> S
    C --> A
    R["Reconciliation / reindex job"] --> B
    R --> S
~~~

| Thành phần | Trách nhiệm |
|---|---|
| Command/domain service | Kiểm tra nghiệp vụ và cập nhật dữ liệu nguồn |
| Source database | Lưu trạng thái chuẩn và transaction |
| Outbox hoặc CDC connector | Chuyển thay đổi thành event bền vững |
| Broker | Buffer, delivery, retry và phân phối |
| Java indexer | Validate, transform, enrich và ghi search document |
| Search engine | Phục vụ truy vấn tìm kiếm |
| Reconciliation job | Phát hiện chênh lệch và phục hồi |
| Search API | Kiểm soát quyền truy cập và định dạng kết quả |

Indexer có thể chạy dưới dạng Lambda, Cloud Functions, Azure Functions hoặc consumer serverless/container khác. Thiết kế cốt lõi vẫn giống nhau: event bền vững, xử lý lặp an toàn và index có thể rebuild.

## 3. Chọn Domain Event hay CDC

Có hai nguồn sự kiện phổ biến.

**Domain event** mô tả một điều có ý nghĩa trong nghiệp vụ, ví dụ ProductPublished, ProductPriceChanged hoặc ProductDeleted. Event được phát từ domain/application service sau khi quy tắc nghiệp vụ được áp dụng.

**Change Data Capture (CDC)** ghi nhận thay đổi ở database, ví dụ một row trong products được insert/update/delete. CDC thường đọc transaction log hoặc cơ chế change stream của database.

| Tiêu chí | Domain event | CDC |
|---|---|---|
| Ý nghĩa | Mang ngữ nghĩa nghiệp vụ | Mô tả thay đổi ở storage |
| Coupling | Gắn với domain contract | Gắn với schema/table |
| Nguồn dữ liệu | Application/domain service | Database log/connector |
| Dữ liệu | Có thể chỉ chứa field cần cho consumer | Có thể chứa before/after row |
| Multi-table change | Có thể phát một event nghiệp vụ tổng hợp | Consumer cần join/enrich hoặc xử lý nhiều record |
| Use case | Nhiều consumer nghiệp vụ | Đồng bộ read model, search, warehouse |

Domain event giúp consumer ít phụ thuộc schema database. CDC hữu ích khi cần capture mọi thay đổi từ hệ thống cũ hoặc không thể sửa producer. Có thể kết hợp CDC với outbox table để phát domain event đã được chuẩn hóa.

Không nên phát trực tiếp một event sau khi update database mà không có cơ chế đảm bảo ghi event và transaction dữ liệu nhất quán. Nếu process chết giữa hai bước, database có thể đã commit nhưng event không được publish.

## 4. Transactional outbox ngăn mất event

Transactional outbox ghi thay đổi nghiệp vụ và event cần publish trong cùng một database transaction.

Ví dụ khi publish sản phẩm:

~~~sql
BEGIN;

WITH updated_product AS (
    UPDATE products
    SET status = 'PUBLISHED',
        version = version + 1,
        updated_at = NOW()
    WHERE id = :product_id
    RETURNING id, version, name, description, brand_id, category_id, status
)
INSERT INTO outbox_event (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    schema_version,
    payload,
    created_at
) SELECT
    :event_id,
    'Product',
    updated_product.id,
    updated_product.version,
    'ProductPublished',
    1,
    jsonb_build_object(
        'productId', updated_product.id,
        'aggregateVersion', updated_product.version,
        'name', updated_product.name,
        'description', updated_product.description,
        'brandId', updated_product.brand_id,
        'categoryId', updated_product.category_id,
        'status', updated_product.status
    ),
    NOW()
FROM updated_product;

COMMIT;
~~~

Nếu transaction rollback, cả business update và outbox row đều rollback. Nếu commit thành công, publisher có thể đọc outbox và gửi event sau đó.

Schema minh họa:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(200) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);

CREATE INDEX outbox_unpublished_idx
    ON outbox_event (created_at)
    WHERE published_at IS NULL;
~~~

Publisher đọc các row chưa publish, gửi event đến broker và chỉ đánh dấu published sau khi broker xác nhận theo semantics của client.

Có một khoảng trống: broker nhận event thành công nhưng publisher chết trước khi ghi published_at. Publisher sẽ gửi lại event khi chạy tiếp. Đây là hành vi at-least-once; consumer cần idempotency. Outbox ngăn mất event, nhưng không làm broker delivery thành exactly-once.

### 4.1. Tránh nhiều publisher claim cùng một row

Nếu chạy nhiều publisher, cần cơ chế claim an toàn để tránh cùng gửi một row đồng thời. Có thể dùng row locking/claim lease, cơ chế skip-locked của database hỗ trợ, hoặc CDC connector quản lý offset.

Không giữ transaction mở trong khi chờ network broker lâu. Có thể claim một batch ngắn, commit lease/ownership rồi publish; sau publish cập nhật trạng thái có điều kiện. Thiết kế lease phải có timeout và recovery nếu publisher chết.

Với CDC, connector đọc transaction log và checkpoint offset. Cần theo dõi connector lag, log retention và khả năng resume sau outage để tránh mất khoảng thay đổi.

## 5. Event contract cho search indexer

Event cần có identity, version và thông tin đủ để consumer xử lý. Một envelope minh họa:

~~~json
{
  "id": "evt-7c91",
  "source": "catalog-service",
  "type": "com.example.catalog.product-updated",
  "subject": "products/sku-1042",
  "time": "2026-11-17T10:15:30Z",
  "schemaVersion": 2,
  "aggregateId": "sku-1042",
  "aggregateVersion": 18,
  "operation": "UPSERT",
  "data": {
    "productId": "sku-1042",
    "name": "Java Serverless Handbook",
    "description": "A practical guide",
    "brandId": "publisher-7",
    "categoryId": "books",
    "status": "PUBLISHED"
  }
}
~~~

Các trường quan trọng:

- **id:** identity ổn định của event qua mọi redelivery.
- **source:** hệ thống phát event.
- **type:** loại thay đổi.
- **subject/aggregateId:** entity bị thay đổi.
- **time:** thời điểm event được tạo.
- **schemaVersion:** phiên bản payload contract.
- **aggregateVersion:** version tăng đơn điệu của entity.
- **operation:** UPSERT hoặc DELETE.
- **data:** dữ liệu cần cho projection.

Có thể dùng CloudEvents hoặc envelope nội bộ. Nếu dùng CloudEvents, source + id là identity phù hợp cho cùng một event. Business version vẫn cần riêng để phát hiện event cũ hoặc đến sai thứ tự.

### 5.1. Chọn payload đầy đủ hay payload mỏng

**Full-state event** chứa trạng thái entity cần index tại version mới. Consumer có thể ghi document mà không cần đọc lại source database.

Ưu điểm:

- Giảm read load lên database.
- Consumer ít phụ thuộc vào schema nguồn.
- Dễ replay event nếu payload được lưu bền vững.

Nhược điểm:

- Payload lớn.
- Có thể chứa dữ liệu nhạy cảm.
- Event phải được cập nhật khi projection cần thêm field.
- Event cũ có thể thiếu field mới.

**Thin event** chỉ chứa entity ID, version và loại thay đổi. Consumer đọc trạng thái mới nhất từ source database để xây document.

Ưu điểm:

- Payload nhỏ.
- Indexer lấy dữ liệu chuẩn tại thời điểm đọc.
- Ít phải đưa nhiều dữ liệu vào broker.

Nhược điểm:

- Tăng query load lên database.
- Nếu đọc latest state thay vì state tại event version, event cũ có thể index nhầm trạng thái mới rồi event ordering trở nên khó giải thích.
- Cần kiểm soát xóa record và race condition.

Có thể chọn hybrid: event mang ID/version; consumer đọc một projection query được thiết kế riêng, đồng thời kiểm tra version và chỉ ghi nếu dữ liệu đọc tương ứng với version cần áp dụng.

## 6. Bootstrap: tạo index lần đầu

Event chỉ cập nhật những thay đổi xảy ra sau khi subscription hoạt động. Một index rỗng cần được nạp dữ liệu hiện tại trước khi có thể phục vụ đầy đủ.

Bootstrap thường có hai phần:

1. Snapshot dữ liệu nguồn tại một điểm nhất quán.
2. Replay/catch-up các thay đổi phát sinh sau điểm snapshot đó.

~~~mermaid
sequenceDiagram
    participant DB as Source database
    participant CDC as Outbox / CDC
    participant Q as Broker
    participant I as Indexer
    participant S as Search index

    Note over DB,CDC: Chọn snapshot và change-stream checkpoint nhất quán
    DB->>S: Bulk index snapshot
    CDC->>Q: Publish changes sau checkpoint
    Q->>I: Deliver change events
    I->>S: Apply version-aware upsert/delete
    Note over I,S: Index bắt kịp source rồi mới bật read traffic
~~~

Cách lấy checkpoint phụ thuộc database và CDC connector. Ưu tiên cơ chế consistent snapshot/snapshot offset được connector hỗ trợ. Không tự ghép một timestamp ở application server với một database scan rồi giả định không có khoảng trống.

### 6.1. Vì sao scan database rồi mới subscribe có thể mất dữ liệu?

Một tình huống lỗi:

1. Job bắt đầu scan bảng products.
2. Một sản phẩm thay đổi trong lúc scan.
3. Event được phát trước khi consumer bắt đầu đọc.
4. Scan có thể đọc version cũ hoặc mới tùy thời điểm.
5. Consumer không nhận được event cần để sửa document.

Kết quả là index có thể thiếu thay đổi vĩnh viễn.

Giải pháp là thiết lập một change-stream checkpoint có quan hệ nhất quán với snapshot. Snapshot nạp trạng thái tại checkpoint; sau đó replay mọi event sau checkpoint. Dùng connector có hỗ trợ consistent snapshot hoặc quy trình database-specific đã được kiểm chứng.

### 6.2. Chạy snapshot và consumer đồng thời

Một cách thực tế là ghi snapshot vào index mới, đồng thời buffer hoặc consume change events sau checkpoint. Khi snapshot hoàn tất, apply các event đã tích lũy theo version guard để event cũ không ghi đè trạng thái mới hơn.

Nếu event consumer xử lý song song với snapshot, mọi write cần có source version và thao tác conditional. Không để một snapshot row cũ overwrite event mới đã được áp dụng.

## 7. Thiết kế search document

Search document nên tối ưu cho truy vấn cần phục vụ. Ví dụ:

~~~json
{
  "productId": "sku-1042",
  "name": "Java Serverless Handbook",
  "description": "A practical guide",
  "brand": {
    "id": "publisher-7",
    "name": "Tech Press"
  },
  "category": {
    "id": "books",
    "name": "Books"
  },
  "status": "PUBLISHED",
  "searchableText": "Java Serverless Handbook A practical guide Tech Press Books",
  "sourceVersion": 18,
  "sourceUpdatedAt": "2026-11-17T10:15:30Z"
}
~~~

Các nguyên tắc:

- Chọn document ID ổn định, thường là entity ID.
- Denormalize những field cần cho filter/sort/facet.
- Giữ source version để kiểm soát thứ tự.
- Không index field không cần cho truy vấn.
- Phân biệt field exact-match, full-text, numeric, date và nested.
- Định nghĩa analyzer/tokenizer phù hợp ngôn ngữ.
- Giữ tenant/resource ownership nếu search API cần enforce authorization.
- Tránh đưa secret hoặc dữ liệu nhạy cảm không cần thiết vào index.

Search mapping là contract giữa indexer và search API. Thay đổi mapping có thể cần tạo index mới và reindex, không phải mọi field đều đổi kiểu tại chỗ được.

## 8. Xử lý UPSERT và DELETE

Indexer thường có hai thao tác chính:

- UPSERT: tạo hoặc thay thế projection của entity.
- DELETE: xóa entity khỏi search index.

UPSERT phải ghi toàn bộ document theo projection contract hoặc cập nhật partial document theo quy tắc rõ ràng. Nếu dùng partial update, cần xử lý field bị xóa/null để tránh dữ liệu cũ còn sót.

DELETE phải được xem là một thay đổi có version, không chỉ là lệnh xóa không điều kiện.

### 8.1. Tombstone ngăn document bị hồi sinh

Giả sử event version 20 là DELETE nhưng đến trước event UPSERT version 19. Nếu indexer xóa document rồi sau đó áp dụng UPSERT cũ, document sẽ xuất hiện lại dù nguồn đã xóa.

Cần lưu delete version/tombstone hoặc dùng cơ chế versioning/conditional write của search engine:

- Chỉ áp dụng event có version lớn hơn version đã ghi.
- Ghi tombstone với entity ID và delete version.
- Bỏ qua event cũ hơn tombstone.
- Giữ tombstone đủ lâu để bao phủ retry, replay và snapshot overlap.
- Khi rebuild index, bảo đảm snapshot/checkpoint không hồi sinh record đã xóa.

Một số search engine hỗ trợ external versioning hoặc optimistic concurrency. Nếu dùng tính năng đó, xác minh semantics cụ thể của engine. Nếu không, có thể lưu version/tombstone trong document metadata hoặc một state store bền vững.

Không xóa hết metadata version ngay sau khi xóa document nếu event cũ vẫn có thể được replay.

## 9. Ordering và version của entity

Broker thường đảm bảo ordering trong một partition/group nhất định, không nhất thiết trên toàn bộ topic. Nhiều event cho cùng entity có thể đến từ các partition hoặc worker khác nhau.

Ví dụ:

~~~text
Product sku-1042:
  version 17 -> name = "Old title"
  version 18 -> name = "New title"
~~~

Nếu version 18 được index trước version 17, một consumer không có version guard có thể ghi đè title mới bằng title cũ.

Các biện pháp:

- Partition key theo aggregate/entity ID để event cùng entity đi cùng partition khi broker hỗ trợ.
- Gắn aggregateVersion tăng đơn điệu trong source transaction.
- Dùng conditional update để chỉ ghi version mới hơn.
- Không dùng event timestamp làm version duy nhất vì clock có thể lệch và timestamp có thể trùng.
- Xử lý duplicate và out-of-order event riêng biệt.

Version phải được tạo ở nguồn dữ liệu chuẩn, không tạo ngẫu nhiên trong consumer.

Contract cần quy định một aggregate version tương ứng với một trạng thái projection có thể áp dụng. Nếu một transaction phát nhiều event cho cùng entity và cùng version nhưng mỗi event chỉ chứa một phần thay đổi, hãy thêm sequence/sub-version để tạo thứ tự toàn phần, hoặc phát một full-state projection event. Chỉ dùng aggregateVersion sẽ không phân biệt được hai event khác nhau có cùng version.

### 9.1. Không phải mọi sequence đều là aggregate version

Database log sequence/offset có thể xác định thứ tự thay đổi toàn cục hoặc trong log, nhưng không luôn là business version của entity. Nếu dùng CDC, connector offset giúp resume stream; entity version hoặc source transaction metadata vẫn cần được diễn giải theo database semantics.

Nếu một transaction cập nhật nhiều bảng liên quan, consumer cần biết projection nào bị ảnh hưởng và đảm bảo dữ liệu join không trộn trạng thái từ hai transaction khác nhau.

## 10. Idempotency cho event consumer

Event broker có thể giao lại message nếu consumer xử lý xong nhưng chưa ack, hoặc publisher gửi lại do không biết lần trước đã thành công hay chưa.

Indexer cần chịu được việc cùng event được xử lý nhiều lần.

Một event dedup store có thể dùng key:

~~~text
source + event_id
~~~

Một idempotency record lưu:

- Event identity.
- Entity ID và aggregate version.
- Processing status.
- Thời điểm nhận/hoàn tất.
- Error metadata cần thiết.

Tuy nhiên, dedup theo event ID chưa đủ. Hai event ID khác nhau có thể mô tả cùng một trạng thái entity; version guard giúp ngăn state cũ ghi đè state mới.

Nếu dùng dedup store để loại duplicate đồng thời, claim phải là thao tác atomic có lease/owner token. Một cặp thao tác đọc isCompleted rồi ghi markCompleted riêng rẽ không khóa được hai worker cùng xử lý. Trong thiết kế bên dưới, atomic version guard tại search writer mới là ranh giới bảo vệ correctness; dedup store giúp giảm công việc lặp và hỗ trợ theo dõi trạng thái.

### 10.1. Thứ tự ghi index và đánh dấu event hoàn tất

Nếu đánh dấu event completed trước khi search engine xác nhận write, process có thể chết sau đó và event bị bỏ qua khi redelivery. Document sẽ không được cập nhật.

Luồng an toàn hơn:

1. Validate event và kiểm tra identity/version.
2. Ghi upsert/delete có điều kiện vào search engine.
3. Chờ xác nhận kết quả write.
4. Đánh dấu event completed trong dedup store nếu có.
5. Ack message.

Nếu search engine đã ghi thành công nhưng process chết trước bước 4 hoặc ack, event có thể chạy lại. Version-aware upsert/delete làm lần chạy lại không tạo tác động sai. Đây là effectively-once projection effect, không phải exactly-once delivery xuyên nhiều hệ thống.

## 11. Java event model

Ví dụ Java record cho event:

~~~java
import java.time.Instant;
import java.util.Map;

public record ProductChangeEvent(
        String id,
        String source,
        String type,
        int schemaVersion,
        String aggregateId,
        long aggregateVersion,
        Operation operation,
        Instant occurredAt,
        Map<String, Object> data) {

    public enum Operation {
        UPSERT,
        DELETE
    }
}
~~~

Trong production, nên dùng DTO có kiểu rõ cho các field domain quan trọng thay vì Map tùy ý. Validate schema version và required field trước khi xử lý.

Các ví dụ record bên dưới yêu cầu Java hỗ trợ record (Java 16 trở lên); khi dùng Java 17/21 trên nền tảng serverless, có thể giữ nguyên cấu trúc này.

Ví dụ document:

~~~java
import java.time.Instant;

public record ProductSearchDocument(
        String productId,
        String name,
        String description,
        String brandName,
        String categoryName,
        String status,
        long sourceVersion,
        Instant sourceUpdatedAt) {
}
~~~

Tách mapper khỏi consumer để có thể test độc lập:

~~~java
public interface ProductDocumentMapper {
    ProductSearchDocument map(ProductChangeEvent event);
}
~~~

Mapper có thể enrich dữ liệu từ source read model nếu event không chứa đủ field. Enrichment phải có policy về version consistency, timeout và fallback.

## 12. Java index writer với version guard

Search engine adapter nên cung cấp thao tác có điều kiện:

~~~java
public interface SearchIndexWriter {

    WriteResult upsertIfNewer(
            String documentId,
            long sourceVersion,
            ProductSearchDocument document);

    WriteResult deleteIfNewer(
            String documentId,
            long sourceVersion);
}
~~~

upsertIfNewer và deleteIfNewer là abstraction của ứng dụng. Adapter cụ thể cần dùng atomic conditional update, external version hoặc optimistic concurrency phù hợp search engine. Không triển khai bằng cách đọc version rồi ghi riêng rẽ nếu giữa hai bước có thể xảy ra race condition.

Ví dụ kết quả:

~~~java
public enum WriteResult {
    APPLIED,
    ALREADY_CURRENT,
    STALE_EVENT
}
~~~

Nếu event có version thấp hơn document hiện tại, writer trả STALE_EVENT và consumer có thể xem event đó đã được superseded. Nếu version bằng nhau, cùng một event/state được retry có thể trả ALREADY_CURRENT.

Không coi mọi conflict là lỗi retryable. Phân biệt version conflict do event cũ với lỗi transient của search cluster.

## 13. Java consumer orchestration

Một handler có thể điều phối validate, dedup, mapping và write:

~~~java
public final class ProductIndexer {

    private final EventDedupStore dedupStore;
    private final ProductDocumentMapper mapper;
    private final SearchIndexWriter indexWriter;

    public ProductIndexer(
            EventDedupStore dedupStore,
            ProductDocumentMapper mapper,
            SearchIndexWriter indexWriter) {
        this.dedupStore = dedupStore;
        this.mapper = mapper;
        this.indexWriter = indexWriter;
    }

    public void handle(ProductChangeEvent event) {
        validate(event);

        String eventKey = event.source() + ":" + event.id();

        if (dedupStore.isCompleted(eventKey)) {
            return;
        }

        if (event.operation() == ProductChangeEvent.Operation.DELETE) {
            indexWriter.deleteIfNewer(
                    event.aggregateId(),
                    event.aggregateVersion());
        } else {
            ProductSearchDocument document = mapper.map(event);

            indexWriter.upsertIfNewer(
                    event.aggregateId(),
                    event.aggregateVersion(),
                    document);
        }

        dedupStore.markCompleted(eventKey);
    }

    private void validate(ProductChangeEvent event) {
        if (event == null) {
            throw new InvalidEventException("Missing event");
        }
        if (event.id() == null || event.id().isBlank()) {
            throw new InvalidEventException("Missing event id");
        }
        if (event.source() == null || event.source().isBlank()) {
            throw new InvalidEventException("Missing event source");
        }
        if (event.schemaVersion() < 1 || event.schemaVersion() > 2) {
            throw new UnsupportedEventSchemaException(event.schemaVersion());
        }
        if (event.aggregateId() == null || event.aggregateId().isBlank()) {
            throw new InvalidEventException("Missing aggregate id");
        }
        if (event.aggregateVersion() < 1) {
            throw new InvalidEventException("Invalid aggregate version");
        }
        if (event.operation() == null) {
            throw new InvalidEventException("Missing operation");
        }
    }
}
~~~

Đây là skeleton minh họa. isCompleted và markCompleted phải dùng durable store, không phải static map. Có thể thay bằng atomic claim/complete record. Nếu markCompleted thất bại sau khi index write thành công, retry sẽ gọi lại writer; version guard bảo đảm thao tác an toàn.

Với event không hợp lệ vĩnh viễn, đưa vào quarantine/DLQ cùng thông tin chẩn đoán cần thiết. Không retry vô hạn một payload thiếu entity ID hoặc schema version không được hỗ trợ.

## 14. Batch indexing để tăng throughput

Gọi search engine một lần cho mỗi event có thể tạo nhiều network round trip. Bulk indexing gom nhiều thao tác trong một request.

Lợi ích:

- Giảm request overhead.
- Tăng throughput.
- Tận dụng network tốt hơn.
- Có thể kiểm soát số document mỗi batch.

Rủi ro:

- Batch quá lớn gây memory pressure hoặc request timeout.
- Một số item trong batch có thể thành công, số khác thất bại.
- Retry toàn bộ batch có thể gửi lại document đã thành công.
- Payload vượt giới hạn request của search engine.

Cần xử lý kết quả theo từng item, không chỉ xem HTTP response tổng thể. Chỉ retry item transient; giữ lại item permanent failure cho DLQ/quarantine.

### 14.1. Chọn batch size

Bắt đầu với batch size và giới hạn byte vừa phải, sau đó benchmark:

- Số document mỗi batch.
- Tổng byte mỗi batch.
- Thời gian tạo document.
- Bulk request latency.
- Item success/failure rate.
- Memory peak.
- Search cluster indexing pressure.
- Queue age và consumer throughput.

Không chọn batch size chỉ theo số document. Một document có description lớn hoặc nhiều nested fields có thể nặng hơn nhiều document nhỏ.

### 14.2. Partial batch failure

Nếu trigger hỗ trợ partial batch response, báo lại đúng những message chưa xử lý thành công để nền tảng chỉ retry phần đó. Nếu không, một lỗi trong batch có thể khiến toàn bộ batch redelivery.

Consumer vẫn phải idempotent vì message thành công có thể được giao lại cùng các message lỗi. Với bulk API, xử lý từng item result để không đánh dấu toàn batch completed khi còn item lỗi.

## 15. Retry, DLQ và poison event

Lỗi khi index có thể chia thành hai nhóm:

| Loại lỗi | Ví dụ | Hành vi |
|---|---|---|
| Transient | Timeout, connection reset, search cluster tạm unavailable, throttling | Retry với backoff và jitter |
| Permanent | Event schema sai, thiếu entity ID, operation không hỗ trợ | Quarantine/DLQ và điều tra |
| Conflict có thể bỏ qua | Event version cũ hơn index | Mark superseded/completed |
| Dependency/configuration | Credential sai, endpoint sai, mapping incompatible | Alert và dừng/giảm consumer theo policy |

Retry cần có giới hạn và DLQ. Poison event không được phép chặn partition hoặc batch vô thời hạn.

Khi replay DLQ:

- Giữ nguyên event ID và aggregate version.
- Kiểm tra event còn hợp lệ với schema/mapping hiện tại.
- Xác định index hiện tại đã có version mới hơn chưa.
- Không replay side effect ngoài phạm vi index nếu event được dùng chung.
- Theo dõi replay rate và lỗi lặp lại.

DLQ là nơi cô lập lỗi cần xử lý, không phải nơi lưu trữ vĩnh viễn mà không có owner.

## 16. Backpressure và bảo vệ search cluster

Nếu producer phát 5.000 event/giây nhưng search cluster chỉ index ổn định 1.000 document/giây, backlog sẽ tăng. Tăng số Lambda invocation vô hạn có thể làm search cluster quá tải, tăng rejection và retry.

Các lớp điều tiết:

- Maximum consumer concurrency.
- Batch size và batch bytes.
- Rate limit theo index/tenant.
- Bounded worker pool.
- Search cluster write capacity.
- Pause/slow polling khi downstream bão hòa.
- Retry backoff khi trả 429 hoặc overload.
- Bulkhead cho các index hoặc tenant quan trọng.

Theo dõi queue age và search indexing pressure cùng nhau. Nếu cluster bão hòa, tăng consumer concurrency thường làm tình hình tệ hơn.

### 16.1. Giới hạn theo index hoặc tenant

Một tenant có thể phát burst lớn và chiếm toàn bộ indexing capacity. Nếu có multi-tenant workload, cân nhắc:

- Partition key và queue riêng theo workload class.
- Rate limit theo tenant.
- Fair scheduling.
- Giới hạn document size.
- Quota cho bulk operations.
- Tách index hoặc cluster theo yêu cầu isolation.

Không đưa tenant ID không được xác thực từ payload vào quyết định security boundary. Tenant identity cần được xác minh từ nguồn tin cậy.

## 17. Mapping và schema evolution

Search mapping có thể thay đổi theo yêu cầu tìm kiếm. Ví dụ field name chuyển từ text sang keyword, analyzer thay đổi hoặc bổ sung nested object.

Cần quản lý schema version cho event và index mapping:

- Consumer biết những schemaVersion nào được hỗ trợ.
- Mapper có thể chuyển đổi event cũ sang document hiện tại.
- Field mới nên có default hoặc nullable behavior phù hợp.
- Thay đổi kiểu field thường cần index mới.
- Không xóa field cũ trước khi mọi producer/consumer đã chuyển.
- Reindex khi analyzer hoặc mapping thay đổi không tương thích.

Không giả định event schema và search index mapping là một. Producer có thể phát domain event ổn định, còn indexer biến đổi sang nhiều version index khác nhau.

### 17.1. Schema registry hoặc contract validation

Với hệ thống nhiều producer/consumer, dùng schema registry hoặc contract test để kiểm soát compatibility. Quy tắc có thể là backward compatible, forward compatible hoặc full compatible tùy cách deploy.

Một event consumer nên có hành vi rõ khi nhận schema version chưa hỗ trợ: quarantine/DLQ và alert, không âm thầm bỏ field quan trọng rồi ghi document sai.

## 18. Rebuild index bằng blue-green và alias

Có lúc cần rebuild toàn bộ index:

- Mapping/analyzer thay đổi.
- Document projection thay đổi.
- Index bị hỏng hoặc thiếu dữ liệu.
- Thay đổi cách tính field/searchable text.
- Chuyển sang search cluster mới.

Không nên xóa index đang phục vụ người dùng rồi mới bắt đầu build lại. Tạo index mới, nạp snapshot, replay event và chuyển alias khi đã bắt kịp.

~~~mermaid
flowchart TD
    A["Index hiện tại: products-v1"] --> U["Alias: products"]
    S["Source snapshot + CDC checkpoint"] --> B["Build products-v2"]
    Q["Events sau checkpoint"] --> C["Catch-up consumer"]
    C --> B
    B --> D["Validate count, versions, sample queries"]
    D --> E{"Lag đủ thấp và dữ liệu đúng?"}
    E -->|Có| F["Atomically switch alias products -> v2"]
    F --> G["Search API đọc v2"]
    E -->|Không| C
    F --> H["Giữ v1 trong thời gian rollback"]
~~~

Các bước:

1. Tạo index mới với mapping/version mới.
2. Chọn snapshot/checkpoint nhất quán.
3. Bulk index snapshot vào index mới.
4. Replay event sau checkpoint.
5. Theo dõi consumer lag và source version.
6. So sánh document count, version distribution và query samples.
7. Switch alias atomically nếu search engine hỗ trợ.
8. Theo dõi error/latency sau cutover.
9. Giữ index cũ theo rollback window.
10. Xóa index cũ sau khi hết thời hạn rollback.

Nếu search engine không có alias, cần cơ chế routing/config switch tương đương và phải kiểm tra atomicity.

### 18.1. Tránh dual-write không kiểm soát

Trong giai đoạn rebuild, có thể cần ghi event vào cả index cũ và mới. Dùng một consumer/router có version-aware write để hai index nhận cùng stream, hoặc chạy hai consumer độc lập với checkpoint được quản lý.

Không để application command ghi trực tiếp vào cả database và search engine như một transaction giả định nguyên tử. Nếu một write thành công và write còn lại thất bại, dữ liệu lệch nhau.

## 19. Search consistency và trải nghiệm người dùng

Event-driven indexing tạo eventual consistency: database commit trước, search index cập nhật sau.

Một user vừa tạo sản phẩm có thể chưa tìm thấy ngay trong search. API cần xác định contract:

- Trả về resource từ write API ngay sau database commit.
- Trả operation/event status nếu index readiness quan trọng.
- Cho client retry search trong một khoảng ngắn.
- Có thể đọc trực tiếp resource theo ID khi search chưa thấy.
- Không dùng search result làm xác nhận cuối cùng cho transaction.

Với một số use case, có thể cần read-your-writes. Có thể chờ index acknowledgment trong một luồng có giới hạn, hoặc trả indexing status để client poll. Tránh giữ HTTP request mở quá lâu để chờ backlog lớn.

Search API cần chấp nhận độ trễ nhất định và hiển thị trạng thái phù hợp thay vì giả định database và index cập nhật đồng thời.

## 20. Reconciliation: phát hiện index lệch nguồn

Ngay cả khi event pipeline hoạt động tốt, lỗi vận hành, bug mapper, DLQ hoặc retention có thể khiến index lệch source.

Một reconciliation job định kỳ có thể:

- So sánh số lượng entity theo trạng thái/tenant.
- So sánh source version với indexed version.
- Lấy mẫu document và so sánh normalized fields/hash.
- Tìm entity active ở source nhưng thiếu trong index.
- Tìm document trong index không còn ở source.
- Kiểm tra tombstone/delete propagation.
- Tạo repair event hoặc reindex một nhóm entity.

Không nhất thiết scan toàn bộ bảng liên tục. Có thể chia partition theo thời gian/ID, dùng updated_at/version watermark hoặc chạy full reconciliation theo lịch thưa hơn.

Khi sửa sai lệch, dùng cùng version-aware writer. Không ghi document cũ đè lên version mới đang được consumer xử lý.

## 21. Bảo mật và dữ liệu nhạy cảm trong search index

Search index thường dễ truy vấn hơn database chuẩn, vì vậy việc denormalize có thể mở rộng phạm vi dữ liệu được tiếp cận.

Cần kiểm soát:

- Chỉ index field cần thiết cho search.
- Loại bỏ secret, token và dữ liệu payment.
- Phân loại PII và áp dụng masking/minimization.
- Enforce tenant/resource filter ở server side.
- Không tin filter do client tự gửi để bảo vệ tenant.
- Mã hóa transport và storage.
- Giới hạn quyền write index cho indexer.
- Giới hạn quyền read/query cho Search API.
- Log access và administrative operations.
- Xóa hoặc cập nhật dữ liệu nhạy cảm theo retention/deletion policy.

Nếu một người dùng bị thu hồi quyền xem resource, search API phải enforce quyền hiện tại. Việc document còn trong index không có nghĩa caller được phép xem.

### 21.1. Xóa dữ liệu và quyền riêng tư

Khi nhận yêu cầu xóa dữ liệu, cần xác định:

- Source record đã xóa hoặc anonymize chưa?
- Event delete đã được publish chưa?
- Search index đã áp dụng tombstone chưa?
- Cache hoặc replica có giữ dữ liệu không?
- Snapshot/backup còn chứa dữ liệu trong thời hạn nào?
- Rebuild index có vô tình nạp lại dữ liệu đã xóa không?

Tombstone và deletion ledger có thể cần giữ đủ lâu để ngăn event cũ hoặc snapshot cũ hồi sinh dữ liệu. Việc xóa khỏi search index không tự động xóa dữ liệu trong backup hoặc event archive.

## 22. Observability cho indexing pipeline

Cần theo dõi từ source đến search index, không chỉ invocation duration của function.

| Metric | Ý nghĩa |
|---|---|
| Outbox pending count | Event chưa publish |
| CDC connector lag | Khoảng trễ đọc transaction log |
| Broker backlog | Event đang chờ consumer |
| Oldest event age | Tuổi event cũ nhất chưa xử lý |
| Consumer throughput | Event được xử lý mỗi giây |
| Indexing latency | Từ source commit đến document searchable |
| Bulk request latency | Thời gian ghi batch |
| Item failure rate | Tỷ lệ item lỗi trong bulk |
| Version conflict/stale count | Event cũ bị bỏ qua |
| Duplicate event count | Event identity được giao lại |
| DLQ depth | Event cần điều tra |
| Reconciliation mismatch | Sai lệch source và index |
| Search cluster rejection | Áp lực hoặc thiếu capacity |

Gắn trace/correlation ID và event ID trong log để truy vết một thay đổi. Tránh đưa entity ID, tenant ID hoặc event ID làm metric label có cardinality cao; dùng log/trace cho định danh chi tiết.

Một SLO hữu ích là tỷ lệ thay đổi được index trong thời hạn, ví dụ phần trăm event được searchable trong một khoảng thời gian mục tiêu. Chọn ngưỡng theo nhu cầu sản phẩm và khả năng hệ thống.

## 23. Kiểm thử indexing pipeline

Các tình huống cần kiểm thử:

1. Product được tạo và xuất hiện trong search.
2. Product thay đổi tên/description và document được cập nhật.
3. Product bị xóa và biến mất khỏi kết quả.
4. Event giống nhau được giao lại nhiều lần.
5. Event version cũ đến sau version mới.
6. DELETE đến trước UPSERT cũ.
7. Consumer chết sau index write nhưng trước ack.
8. Search cluster timeout hoặc trả throttling.
9. Một item trong bulk thất bại.
10. Event schema version mới chưa được hỗ trợ.
11. Snapshot chạy đồng thời với event stream.
12. Rebuild index trong khi production vẫn nhận thay đổi.
13. Alias switch và rollback.
14. DLQ replay sau khi index đã có version mới hơn.
15. Tenant burst không làm tenant khác bị starvation.
16. Delete/PII request được phản ánh trong index và cache.
17. Reconciliation phát hiện và sửa một document bị thiếu.

Test concurrency và crash với broker/database/search engine test environment thực tế khi có thể. Mock chỉ xác minh logic mapper; nó không chứng minh atomic version guard hoặc delivery behavior của hệ thống thật.

## 24. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Update database rồi publish event riêng | Có thể mất event sau DB commit | Transactional outbox hoặc CDC |
| Subscribe sau khi scan snapshot | Mất thay đổi trong khoảng trống | Consistent snapshot + checkpoint/catch-up |
| Không có aggregate version | Event cũ ghi đè state mới | Version-aware conditional write |
| Dedup chỉ trong memory | Duplicate sau restart/scale-out | Durable dedup và version guard |
| Delete không có tombstone/version | Event cũ hồi sinh document | Versioned tombstone |
| Retry toàn bộ bulk | Tăng tải và ghi lại item đã thành công | Retry theo từng item |
| Không có DLQ/quarantine | Poison event chặn pipeline | Phân loại lỗi và DLQ |
| Tăng concurrency khi cluster quá tải | Rejection/retry tăng | Backpressure và rate limit |
| Dùng search index làm source of truth | Khó phục hồi khi index sai/mất | Rebuild từ nguồn chuẩn |
| Rebuild trên index đang phục vụ | Search gián đoạn hoặc thiếu dữ liệu | Index mới + catch-up + alias switch |
| Không reconciliation | Sai lệch tồn tại lâu | Đối soát version/count/hash định kỳ |
| Index dư PII | Mở rộng phạm vi lộ dữ liệu | Data minimization và access control |

## 25. Quy trình xây dựng bộ lập chỉ mục từ sự kiện

1. **Chọn nguồn sự kiện.** Domain event, transactional outbox hay CDC phù hợp với quyền kiểm soát producer và database.
2. **Thiết kế event contract.** Có event ID, source, schema version, entity ID, operation và aggregate version.
3. **Đảm bảo event bền vững.** Dùng outbox/CDC checkpoint để không mất thay đổi.
4. **Bootstrap index.** Dùng consistent snapshot và change-stream checkpoint.
5. **Thiết kế document/mapping.** Chỉ index field cần cho truy vấn, giữ source version và ownership metadata.
6. **Triển khai Java consumer.** Validate, transform, enrich và ghi conditional.
7. **Xử lý idempotency/order.** Durable dedup, version guard và tombstone cho delete.
8. **Batch có giới hạn.** Theo dõi byte, duration, partial item failure và memory.
9. **Retry/DLQ.** Retry transient, quarantine permanent và replay có kiểm soát.
10. **Điều tiết tải.** Giới hạn concurrency/rate để bảo vệ search cluster.
11. **Bảo vệ dữ liệu.** Enforce tenant access, data minimization và deletion policy.
12. **Quan sát end-to-end.** Theo dõi outbox/CDC lag, queue age, indexing latency và mismatch.
13. **Rebuild an toàn.** Dùng index mới, snapshot, catch-up, validation và alias switch.
14. **Đối soát định kỳ.** Sửa document thiếu, stale hoặc không còn tồn tại.
15. **Kiểm thử failure.** Mô phỏng duplicate, out-of-order, crash, timeout, DLQ replay và rollback.

## 26. Câu hỏi tự kiểm tra

- Vì sao search index nên là projection có thể tái tạo?
- Domain event khác CDC ở điểm nào?
- Transactional outbox ngăn mất event như thế nào?
- Vì sao outbox publisher vẫn có thể gửi duplicate?
- Event envelope cần những trường nào để hỗ trợ idempotency và ordering?
- Khi nào nên dùng full-state event và khi nào nên dùng thin event?
- Snapshot bootstrap cần phối hợp checkpoint ra sao để không mất thay đổi?
- Aggregate version ngăn event cũ ghi đè document mới như thế nào?
- Vì sao delete cần tombstone?
- Dedup theo event ID khác version guard ra sao?
- Vì sao cần xử lý từng item trong bulk response?
- Khi nào nên đưa event vào DLQ?
- Backpressure bảo vệ search cluster như thế nào?
- Rebuild bằng index mới và alias switch có lợi ích gì?
- Reconciliation cần so sánh những dữ liệu nào?
- Làm sao bảo vệ tenant isolation và xử lý yêu cầu xóa PII?
- Những metric nào thể hiện độ trễ từ source commit đến searchable document?



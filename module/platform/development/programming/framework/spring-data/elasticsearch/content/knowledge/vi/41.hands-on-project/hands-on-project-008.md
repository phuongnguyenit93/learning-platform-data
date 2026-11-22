# Đồng bộ thay đổi từ cơ sở dữ liệu qua outbox

Khi một ứng dụng lưu dữ liệu nghiệp vụ vào cơ sở dữ liệu và đồng thời cập nhật Elasticsearch để phục vụ tìm kiếm, hai thao tác ghi này tạo ra một bài toán nhất quán. Database có thể commit thành công nhưng Elasticsearch tạm thời không sẵn sàng; hoặc ứng dụng có thể dừng sau khi database commit nhưng trước khi gửi thay đổi sang search index. Nếu chỉ gọi hai thao tác ghi liên tiếp trong cùng một service method, hệ thống vẫn có nguy cơ để dữ liệu ở hai nơi lệch nhau.

**Transactional outbox** giải quyết khoảng trống này bằng cách ghi thay đổi nghiệp vụ và một sự kiện cần đồng bộ vào cùng transaction của database. Một tiến trình relay đọc sự kiện đã commit rồi chuyển chúng tới Elasticsearch. Nếu relay lỗi, sự kiện vẫn còn trong outbox để retry hoặc khôi phục. Cách làm này thường cung cấp delivery theo kiểu at-least-once; vì vậy consumer phải idempotent và có cơ chế bảo vệ thứ tự phiên bản.

Trong ngữ cảnh Spring Data Elasticsearch, database là source of truth còn Elasticsearch là read model/projection. Bài này trình bày kiến trúc outbox, transaction boundary, schema event, polling relay, CDC, xử lý Bulk API, idempotency, ordering, delete, retry/DLQ, rebuild index và cách kiểm thử toàn bộ luồng.

## 1. Vì sao ghi database rồi ghi Elasticsearch trực tiếp có thể lỗi?

Một service đơn giản có thể làm như sau:

~~~java
@Transactional
public Product updateProduct(UpdateProductRequest request) {
    Product product = productRepository.findById(request.id())
            .orElseThrow();

    product.setName(request.name());
    productRepository.save(product);

    elasticsearchOperations.save(toDocument(product));

    return product;
}
~~~

Nhìn qua, method có transaction database nên có vẻ hai thay đổi được bảo vệ cùng nhau. Nhưng transaction đó thường chỉ quản lý database connection. Elasticsearch không tự tham gia transaction của JPA/JDBC.

Các tình huống lỗi:

1. Database commit thành công, Elasticsearch timeout.
2. Elasticsearch ghi thành công, database transaction rollback.
3. Process bị kill sau database commit nhưng trước lệnh Elasticsearch.
4. Process bị kill sau Elasticsearch write nhưng trước khi trả response.
5. Elasticsearch trả HTTP success nhưng một item trong bulk bị lỗi.
6. Network timeout khiến ứng dụng không biết server đã nhận write hay chưa.

Đây là dual-write problem. Không có transaction phân tán được cấu hình rõ ràng thì không thể giả định hai hệ thống commit hoặc rollback như một đơn vị.

Với kiến trúc search projection, outbox thường đơn giản và dễ vận hành hơn: transaction nghiệp vụ chỉ commit ở source database, còn projection được cập nhật bất đồng bộ và có thể tái tạo.

## 2. Kiến trúc transactional outbox

Outbox lưu event trong cùng database với dữ liệu nghiệp vụ. Khi transaction commit, cả business change và event cùng tồn tại.

~~~text
HTTP request
     |
     v
Application service
     |
     | one database transaction
     v
+-----------------------------+
| Relational database         |
|                             |
|  business table             |
|  outbox_event table         |
+-----------------------------+
               |
               | committed rows
               v
        Outbox relay
               |
               | retry / backoff
               v
        Elasticsearch
               |
               v
         Search API
~~~

Các thành phần:

- **Business table:** lưu trạng thái nghiệp vụ chuẩn.
- **Outbox table:** lưu event cần chuyển tiếp.
- **Application service:** ghi business data và outbox event trong cùng transaction.
- **Relay/consumer:** đọc event đã commit.
- **Projector:** chuyển event thành document Elasticsearch.
- **Elasticsearch:** lưu projection để search, filter và aggregation.

Outbox không làm database và Elasticsearch trở thành một transaction duy nhất. Nó bảo đảm rằng nếu business transaction commit thì ý định đồng bộ cũng được lưu bền vững trong cùng transaction.

## 3. Luồng xử lý khi cập nhật một sản phẩm

Ví dụ người dùng đổi tên sản phẩm:

~~~text
1. Request UpdateProduct
          |
          v
2. Begin DB transaction
          |
          v
3. Update products row
          |
          v
4. Insert ProductUpdated event into outbox
          |
          v
5. Commit DB transaction
          |
          v
6. Outbox relay reads committed event
          |
          v
7. Build ProductDocument
          |
          v
8. Index document into Elasticsearch
          |
          v
9. Mark outbox event delivered
~~~

Nếu bước 5 rollback, cả product update và outbox event đều không tồn tại. Nếu bước 7 hoặc 8 thất bại, outbox event vẫn còn để retry. Nếu bước 8 thành công nhưng relay crash trước bước 9, event có thể được gửi lại; projector phải xử lý idempotently.

Đây là điểm quan trọng: outbox loại bỏ nguy cơ mất ý định đồng bộ giữa hai lệnh ghi, nhưng không tự tạo exactly-once delivery giữa database và Elasticsearch.

## 4. Thiết kế bảng outbox

Một schema cơ bản có thể dùng PostgreSQL:

~~~sql
CREATE TABLE outbox_event (
    event_id           UUID PRIMARY KEY,
    aggregate_type     VARCHAR(100) NOT NULL,
    aggregate_id       VARCHAR(200) NOT NULL,
    aggregate_version  BIGINT NOT NULL,
    event_type         VARCHAR(150) NOT NULL,
    schema_version     INTEGER NOT NULL,
    payload            JSONB NOT NULL,
    occurred_at        TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    status             VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts           INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMPTZ,
    locked_by          VARCHAR(150),
    lease_until        TIMESTAMPTZ,
    delivered_at       TIMESTAMPTZ,
    last_error         TEXT
);

CREATE INDEX idx_outbox_pending
    ON outbox_event (status, next_attempt_at, created_at);

CREATE INDEX idx_outbox_aggregate
    ON outbox_event (aggregate_type, aggregate_id, aggregate_version);
~~~

Các field:

- event_id: định danh event ổn định.
- aggregate_type: loại entity/domain aggregate.
- aggregate_id: ID nghiệp vụ.
- aggregate_version: version tăng theo aggregate.
- event_type: tên sự kiện.
- schema_version: version của payload.
- payload: dữ liệu cần projector xử lý.
- occurred_at: thời điểm nghiệp vụ phát sinh.
- status: trạng thái xử lý.
- attempts: số lần thử.
- next_attempt_at: thời điểm sớm nhất được retry.
- locked_by và lease_until: claim/lease cho relay.
- delivered_at: thời điểm xác nhận hoàn tất.
- last_error: lỗi gần nhất đã được làm sạch.

Schema thực tế cần điều chỉnh theo database, lượng event, retention và mô hình concurrency. Có thể tách trạng thái xử lý ra bảng khác để giữ event bất biến; với throughput lớn, partitioning theo thời gian hoặc archive policy có thể cần thiết.

## 5. Event cần chứa gì?

Một event nên mang đủ thông tin để consumer xác định loại thay đổi và dựng projection. Ví dụ:

~~~json
{
  "eventId": "6d76f9d0-6f2d-4e56-ae58-1e1f2e3a1001",
  "eventType": "ProductUpdated",
  "schemaVersion": 1,
  "aggregateType": "Product",
  "aggregateId": "p-1001",
  "aggregateVersion": 42,
  "occurredAt": "2026-11-13T10:15:30Z",
  "tenantId": "tenant-a",
  "payload": {
    "name": "Mechanical Keyboard",
    "description": "Compact wireless keyboard",
    "category": "keyboard",
    "status": "ACTIVE"
  }
}
~~~

Envelope nên có event ID duy nhất và ổn định qua retry, aggregate ID, aggregate version hoặc sequence, event type, schema version, thời điểm nguồn phát sinh, tenant/partition key nếu có, và payload hoặc dữ liệu tham chiếu để đọc trạng thái mới nhất.

Không đưa access token, secret hoặc dữ liệu cá nhân không cần thiết vào event. Outbox thường có quyền đọc rộng trong pipeline và có thể được giữ lâu để replay, nên phải bảo vệ như dữ liệu nghiệp vụ.

## 6. Event payload hay đọc lại trạng thái mới nhất?

Có hai chiến lược phổ biến.

**Event mang snapshot cần thiết:** payload chứa các field để dựng document tại thời điểm event phát sinh. Consumer không cần truy vấn lại database. Cách này thuận lợi cho replay lịch sử, nhưng payload có thể lớn và cần quản lý schema evolution.

**Event chỉ mang ID/version:** consumer đọc lại aggregate hiện tại từ database rồi dựng document mới nhất. Cách này giảm payload, nhưng khi event cũ được xử lý muộn, consumer có thể đọc trạng thái mới hơn event đang xử lý. Đây có thể là hành vi mong muốn nếu projection chỉ cần trạng thái hiện tại, nhưng không phù hợp nếu cần tái hiện từng chuyển đổi lịch sử.

Một hệ thống cũng có thể dùng domain event nhỏ kèm metadata rồi project từ event, hoặc dùng notification event chỉ báo rằng aggregate cần được làm mới.

Hãy quyết định semantics trước:

- Nếu mục tiêu là phản ánh trạng thái mới nhất, đọc lại source có thể đơn giản hơn.
- Nếu mục tiêu là áp dụng từng thay đổi theo thứ tự, event cần đủ dữ liệu và version.
- Nếu cần audit/history, giữ event bất biến và không thay payload bằng trạng thái mới nhất.

## 7. Ghi business data và outbox trong cùng transaction Spring

Ví dụ dùng Spring Data JPA cho database và một repository outbox:

~~~java
@Service
public class ProductCommandService {

    private final ProductJpaRepository products;
    private final OutboxEventRepository outbox;
    private final ObjectMapper objectMapper;

    public ProductCommandService(
            ProductJpaRepository products,
            OutboxEventRepository outbox,
            ObjectMapper objectMapper) {
        this.products = products;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Product update(UpdateProductRequest request) {
        Product product = products.findById(request.id())
                .orElseThrow(ProductNotFoundException::new);

        product.setName(request.name());
        product.setDescription(request.description());
        product.setVersion(product.getVersion() + 1);

        Product saved = products.save(product);

        ProductUpdatedPayload payload =
                new ProductUpdatedPayload(
                        saved.getId(),
                        saved.getName(),
                        saved.getDescription(),
                        saved.getVersion()
                );

        OutboxEvent event = OutboxEvent.create(
                UUID.randomUUID(),
                "Product",
                saved.getId(),
                saved.getVersion(),
                "ProductUpdated",
                1,
                objectMapper.writeValueAsString(payload),
                Instant.now()
        );

        outbox.save(event);
        return saved;
    }
}
~~~

Ví dụ giả định ProductJpaRepository và OutboxEventRepository cùng sử dụng một transaction manager và cùng database. Các constructor, exception và serialization cần điều chỉnh theo ứng dụng.

Điểm cốt lõi là không gọi Elasticsearch trong method transaction này. Khi transaction commit, business row và outbox row cùng được commit hoặc cùng rollback.

Nếu ghi outbox qua một datasource hoặc transaction manager khác, bảo đảm atomicity không còn tự động. Khi đó cần một thiết kế khác đã được đánh giá, không nên chỉ thêm một repository rồi giả định cùng transaction.

## 8. Entity và repository cho outbox

Một entity JPA tối giản:

~~~java
@Entity
@Table(name = "outbox_event")
public class OutboxEvent {

    @Id
    private UUID eventId;

    private String aggregateType;
    private String aggregateId;
    private long aggregateVersion;
    private String eventType;
    private int schemaVersion;

    @Column(columnDefinition = "jsonb")
    private String payload;

    private Instant occurredAt;
    private String status;
    private int attempts;
    private Instant nextAttemptAt;
    private String lockedBy;
    private Instant leaseUntil;
    private Instant deliveredAt;

    @Column(length = 4000)
    private String lastError;

    protected OutboxEvent() {
    }

    // Constructor/factory and accessors omitted for clarity.
}
~~~

Repository:

~~~java
public interface OutboxEventRepository
        extends JpaRepository<OutboxEvent, UUID> {
}
~~~

Ví dụ dùng JSONB phụ thuộc PostgreSQL và mapping strategy của Hibernate. Có thể dùng converter hoặc JSON type phù hợp phiên bản ORM. Không nên giả định khai báo columnDefinition tự chuyển Java object thành JSONB nếu converter chưa được cấu hình.

Trong production, cân nhắc tách immutable event content khỏi delivery state. Event payload không nên bị thay đổi mỗi lần retry; chỉ các field trạng thái xử lý mới được cập nhật.

## 9. Vì sao relay không nên giữ transaction database trong lúc gọi Elasticsearch?

Một cách đơn giản là mở transaction, đọc outbox row, gọi Elasticsearch, rồi đánh dấu delivered trước khi commit. Cách này giữ database lock/transaction trong thời gian network request và tạo ra các vấn đề:

- Elasticsearch chậm khiến transaction database kéo dài.
- Lock giữ lâu làm các relay khác chờ.
- Connection pool bị chiếm trong lúc chờ network.
- Nếu transaction rollback sau khi Elasticsearch đã ghi, event sẽ được gửi lại.
- Nếu cluster timeout, transaction database có thể kéo dài đến timeout khác.

Thiết kế phổ biến là **claim event trong transaction ngắn**, commit lease, sau đó gọi Elasticsearch ngoài transaction. Khi xử lý xong, mở transaction khác để cập nhật trạng thái.

~~~text
Transaction A:
  claim rows + set lease + commit
             |
             v
Outside DB transaction:
  project and write to Elasticsearch
             |
             v
Transaction B:
  mark delivered / schedule retry + commit
~~~

Crash sau khi claim sẽ để event ở trạng thái leased đến khi lease hết hạn. Worker khác có thể claim lại. Crash sau Elasticsearch success nhưng trước mark delivered cũng tạo duplicate; idempotency xử lý trường hợp này.

## 10. Polling relay với FOR UPDATE SKIP LOCKED

PostgreSQL hỗ trợ SELECT ... FOR UPDATE SKIP LOCKED để nhiều worker claim các hàng khác nhau mà không chờ nhau.

Ví dụ transaction claim batch:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_event
    WHERE status = 'PENDING'
      AND (next_attempt_at IS NULL OR next_attempt_at <= now())
      AND (lease_until IS NULL OR lease_until < now())
    ORDER BY created_at, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE outbox_event e
SET status = 'IN_PROGRESS',
    locked_by = :worker_id,
    lease_until = now() + interval '60 seconds',
    attempts = attempts + 1
FROM candidates c
WHERE e.event_id = c.event_id
RETURNING e.*;
~~~

Query cần chạy trong transaction ngắn. Sau khi trả về các row đã claim, commit trước khi gọi Elasticsearch.

Cú pháp interval, RETURNING và locking khác nhau giữa database. MySQL, SQL Server hoặc Oracle cần query tương ứng. Không copy nguyên SQL PostgreSQL sang database khác.

## 11. Lease và xử lý worker chết

Lease là quyền xử lý tạm thời có thời hạn. Nếu worker chết, lease hết hạn để worker khác có thể claim event.

Các điều cần xác định:

- Lease dài hơn thời gian xử lý batch bình thường.
- Nếu xử lý lâu, worker có thể gia hạn lease.
- Chỉ worker đang sở hữu lease mới được cập nhật trạng thái.
- Khi lease hết hạn, worker cũ có thể vẫn đang chạy; do đó duplicate vẫn có thể xảy ra.
- Update trạng thái cần kiểm tra locked_by/lease token để tránh worker cũ đánh dấu nhầm event đã được worker mới claim.

Ví dụ update có điều kiện:

~~~sql
UPDATE outbox_event
SET status = 'DELIVERED',
    delivered_at = now(),
    locked_by = NULL,
    lease_until = NULL
WHERE event_id = :event_id
  AND status = 'IN_PROGRESS'
  AND locked_by = :worker_id
  AND lease_until > now();
~~~

Nếu update không ảnh hưởng row nào, worker không còn sở hữu lease. Không được tự ý đánh dấu delivered bằng một update không điều kiện.

## 12. Không để claim làm mất thứ tự aggregate

Nhiều worker có thể xử lý song song. Điều này tăng throughput nhưng có thể khiến event version 43 tới Elasticsearch trước version 42.

~~~text
Product p-1001:
  E41 -> worker A (chậm)
  E42 -> worker B (nhanh)

Elasticsearch nhận E42 trước E41
Sau đó E41 ghi đè projection mới
~~~

Có các lựa chọn:

- Partition theo aggregate ID và giữ thứ tự trong partition.
- Chỉ claim event kế tiếp của mỗi aggregate.
- Dùng source version và external versioning để từ chối event cũ.
- Dùng một event consumer tuần tự cho từng partition.
- Nếu projection đọc lại trạng thái mới nhất, kiểm tra version trước khi index.

Không phải lúc nào cũng cần xử lý toàn hệ thống tuần tự. Có thể song song giữa các aggregate nhưng giữ thứ tự trong cùng một aggregate key.

## 13. Polling relay trong Spring

Có thể tạo scheduled component gọi service claim batch:

~~~java
@Component
public class OutboxPollingJob {

    private final OutboxRelayService relayService;

    public OutboxPollingJob(OutboxRelayService relayService) {
        this.relayService = relayService;
    }

    @Scheduled(fixedDelay = 500L)
    public void poll() {
        relayService.processNextBatch();
    }
}
~~~

Service orchestration có thể:

~~~java
public void processNextBatch() {
    List<ClaimedOutboxEvent> events = claimService.claim(batchSize);

    if (events.isEmpty()) {
        return;
    }

    processOutsideTransaction(events);
}
~~~

Phương thức claim nên nằm trong bean/service transaction riêng để transaction kết thúc trước khi xử lý Elasticsearch. Tránh gọi self-invocation trong cùng bean rồi kỳ vọng proxy @Transactional mở transaction mới; Spring proxy thường không intercept self-invocation theo cách đó.

Nếu nhiều application instance chạy scheduler, claim phải được điều phối bằng database lock/lease hoặc broker. Không chỉ dùng một biến boolean trong memory để bảo đảm chỉ một worker toàn hệ thống.

## 14. Tách transaction boundary trong Spring

Một cấu trúc dễ hiểu:

~~~java
@Service
public class OutboxClaimService {

    @Transactional
    public List<ClaimedOutboxEvent> claim(int limit) {
        // Select eligible rows with lock/lease.
        // Mark them IN_PROGRESS and return immutable event data.
    }
}

@Service
public class OutboxDeliveryService {

    @Transactional
    public void markDelivered(UUID eventId, String workerId) {
        // Update only if this worker still owns the lease.
    }

    @Transactional
    public void scheduleRetry(
            UUID eventId,
            String workerId,
            Instant nextAttempt,
            String safeError) {
        // Persist retry state.
    }
}
~~~

Relay gọi hai service qua proxy bean:

~~~java
public void processNextBatch() {
    List<ClaimedOutboxEvent> events = claimService.claim(100);

    for (ClaimedOutboxEvent event : events) {
        try {
            projector.project(event);
            deliveryService.markDelivered(
                    event.eventId(),
                    workerId
            );
        } catch (RetryableProjectionException ex) {
            deliveryService.scheduleRetry(
                    event.eventId(),
                    workerId,
                    retryPolicy.nextAttempt(event.attempts()),
                    sanitize(ex)
            );
        } catch (PermanentProjectionException ex) {
            deliveryService.moveToDeadLetter(
                    event.eventId(),
                    workerId,
                    sanitize(ex)
            );
        }
    }
}
~~~

Ví dụ minh họa; cần thiết kế claim DTO, exception và retry policy phù hợp. Không giữ transaction claim mở xuyên suốt vòng lặp gọi Elasticsearch.

## 15. Ghi document vào Elasticsearch bằng Spring Data

Tạo document riêng cho search projection:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String name;
    private String description;
    private String category;
    private String status;
    private String tenantId;
    private long sourceVersion;
}
~~~

Projector chuyển event thành document:

~~~java
@Component
public class ProductProjector {

    private final ElasticsearchOperations operations;
    private final ObjectMapper objectMapper;

    public ProductProjector(
            ElasticsearchOperations operations,
            ObjectMapper objectMapper) {
        this.operations = operations;
        this.objectMapper = objectMapper;
    }

    public void project(OutboxEvent event) {
        ProductUpdatedPayload payload =
                readPayload(event.getPayload());

        ProductDocument document = new ProductDocument();
        document.setId(event.getAggregateId());
        document.setName(payload.name());
        document.setDescription(payload.description());
        document.setCategory(payload.category());
        document.setStatus(payload.status());
        document.setTenantId(payload.tenantId());
        document.setSourceVersion(event.getAggregateVersion());

        operations.save(
                document,
                IndexCoordinates.of("products")
        );
    }
}
~~~

Đây là ví dụ minh họa cho thao tác save qua Spring Data Elasticsearch. Trong production, index name nên lấy từ cấu hình/alias, tenant scope phải được áp dụng ở query, và version semantics cần được bảo vệ ở tầng Elasticsearch hoặc projector.

Dùng document projection riêng giúp database entity không bị gắn trực tiếp với mapping search. Có thể bổ sung analyzer, multi-field, denormalized data hoặc field chỉ phục vụ search mà không làm thay đổi schema nghiệp vụ.

## 16. Idempotency khi relay gửi lại event

Relay có thể gửi lại cùng event nếu Elasticsearch index thành công nhưng worker bị crash trước khi đánh dấu outbox event delivered. Lease hết hạn cũng có thể khiến worker khác claim lại event.

Vì vậy, projector phải xử lý duplicate an toàn:

- Dùng document ID ổn định từ aggregate ID.
- Không tạo ID ngẫu nhiên mới mỗi lần retry.
- Tránh side effect không idempotent trong projector.
- Lưu sourceVersion.
- Từ chối event cũ hơn version đã áp dụng.
- Nếu cùng event được gửi lại, kết quả cuối vẫn giống nhau.

Với thao tác index document đầy đủ cùng ID, gửi lại cùng payload thường tạo cùng trạng thái document. Tuy nhiên, nếu projection có logic cộng dồn hoặc append vào array, cần thiết kế idempotency riêng.

Idempotency không đồng nghĩa chỉ dùng cùng ID. Nếu event cũ ghi sau event mới, document vẫn có thể bị lùi trạng thái. Cần thêm version ordering.

## 17. Bảo vệ version bằng external versioning

Elasticsearch hỗ trợ version control cho index operation. Khi source có aggregate version tăng đơn điệu, có thể dùng external versioning để chỉ chấp nhận phiên bản mới hơn theo semantics được chọn.

~~~text
Database aggregate version 41 -> Elasticsearch document version 41
Database aggregate version 42 -> Elasticsearch document version 42

Nếu event version 41 đến sau version 42:
    Elasticsearch từ chối stale write
~~~

Ở tầng REST, một index request có thể dùng version và version_type phù hợp. Với Spring Data abstraction, khả năng cấu hình external version phụ thuộc API và phiên bản; nếu cần kiểm soát chính xác, có thể dùng Elasticsearch Java API Client tại adapter.

Cần phân biệt external versioning và optimistic concurrency bằng sequence number/primary term. Chúng giải quyết những vấn đề liên quan nhưng không giống nhau.

Khi nhận version conflict:

- Nếu event cũ hơn document hiện tại, có thể đánh dấu stale/superseded.
- Nếu cùng version và cùng event, duplicate có thể đã được áp dụng.
- Nếu cùng version nhưng payload khác, cần điều tra.
- Nếu version mới hơn bị conflict do race, đọc trạng thái/version và xử lý theo policy.

Không retry mọi conflict vô hạn.

## 18. Xử lý delete event

Delete phải được đồng bộ như một thay đổi dữ liệu bình thường. Nếu chỉ xử lý create/update, sản phẩm đã xóa trong database vẫn có thể xuất hiện trong search.

Một event:

~~~json
{
  "eventId": "evt-delete-1001",
  "eventType": "ProductDeleted",
  "aggregateId": "p-1001",
  "aggregateVersion": 43,
  "occurredAt": "2026-11-13T11:00:00Z",
  "payload": {
    "reason": "REMOVED"
  }
}
~~~

Projector có thể xóa document theo ID. Nhưng cần chú ý event cũ đến muộn có thể index lại document sau delete.

Các cách bảo vệ:

- External versioning cho delete nếu semantics phù hợp.
- Lưu tombstone với version trong projection.
- Lưu version đã xóa trong một store riêng.
- Tuần tự hóa event theo aggregate.
- Khi project từ source mới nhất, kiểm tra aggregate còn tồn tại hay đã bị xóa.

Nếu Elasticsearch document bị xóa hoàn toàn và không còn version/tombstone, event cũ có thể tạo lại nó. Test phải bao gồm delete version 43 đến trước update version 42 và xác nhận document không bị hồi sinh.

## 19. Bulk indexing từ outbox

Khi backlog lớn, gửi từng document một có thể tạo quá nhiều HTTP request. Có thể gom event thành bulk request.

~~~text
Claim batch of outbox events
          |
          v
Transform to IndexQuery items
          |
          v
Bulk index request
          |
          v
Inspect every item response
       /      |       \
      v       v        v
  Success   Retry    Permanent
      |       |        |
      v       v        v
 Delivered  Pending    DLQ
~~~

Spring Data Elasticsearch có Bulk API qua ElasticsearchOperations. Ví dụ khái niệm:

~~~java
List<IndexQuery> queries = events.stream()
        .map(this::toIndexQuery)
        .toList();

List<IndexedObjectInformation> results =
        operations.bulkIndex(
                queries,
                BulkOptions.defaultOptions(),
                IndexCoordinates.of("products")
        );
~~~

Tên class, overload và metadata response thay đổi theo phiên bản Spring Data. Cần dùng đúng API dependency dự án và xác định cách correlate từng result với event nguồn. Nếu API trả exception tổng thể, vẫn phải hiểu liệu server đã xử lý một phần request hay chưa; không mặc định mọi item thất bại hoặc mọi item thành công.

## 20. Bulk HTTP success không có nghĩa mọi item thành công

Bulk response có thể chứa item-level errors dù HTTP request thành công. Worker phải đọc kết quả từng action:

- Thành công: mark event delivered.
- Lỗi tạm thời như 429: retry với backoff.
- Lỗi mapping/parsing: chuyển DLQ hoặc chờ sửa.
- Conflict do stale version: đánh dấu superseded theo policy.
- Authentication/authorization: cảnh báo cấu hình, thường dừng pipeline thay vì retry từng item vô hạn.

Không đánh dấu cả batch delivered chỉ vì bulk method không ném exception. Không retry toàn bộ batch nếu chỉ một số item thất bại mà việc gửi lại thành công có thể gây side effect hoặc ghi đè version.

Mỗi bulk item cần giữ correlation tới eventId. Nếu thứ tự list là cách duy nhất để ghép, phải bảo đảm transform không reorder list và response API giữ thứ tự action. Một correlation ID rõ ràng trong worker state giúp điều tra dễ hơn.

## 21. Retry có backoff và jitter

Lỗi tạm thời cần retry có giới hạn. Exponential backoff:

\[
delay_n = min(maxDelay,\ baseDelay \times 2^n)
\]

Có thể thêm jitter:

\[
actualDelay = random(0,\ delay_n)
\]

Ví dụ lần 1 tối đa 250 ms, lần 2 tối đa 500 ms, lần 3 tối đa 1 giây, lần 4 tối đa 2 giây, delay tối đa 30 giây; hết số lần thử thì DLQ hoặc trạng thái chờ xử lý.

Các con số chỉ là ví dụ. Hãy chọn dựa trên throughput, latency, cluster capacity và yêu cầu freshness.

Khi nhận nhiều 429, giảm batch size hoặc concurrency thay vì chỉ tăng retry. Nếu cluster đang quá tải, retry storm sẽ làm backlog và latency tăng thêm.

## 22. Phân loại lỗi retryable và permanent

| Lỗi | Hướng xử lý thường gặp |
|---|---|
| 429 / rejected execution | Backoff, giảm batch/concurrency |
| Network timeout/reset | Retry idempotent; kiểm tra write có thể đã thành công |
| 502/503/504 | Retry có giới hạn |
| Cluster unavailable | Giữ backlog, backoff |
| 400 mapping/parsing | DLQ, sửa payload/mapping |
| 401/403 | Cảnh báo credential/role, dừng hoặc pause |
| Index/alias không tồn tại | Kiểm tra provisioning, không retry vô hạn |
| Version conflict do stale event | Đánh dấu superseded theo policy |
| Version conflict không rõ nguyên nhân | Đọc lại version và điều tra |
| Payload vượt giới hạn | Chia nhỏ hoặc xử lý riêng |

Không phân loại chỉ dựa vào exception class tổng quát. Hãy đọc status, error type và context của từng bulk item. Error message lưu vào outbox/DLQ cần được sanitize và giới hạn độ dài.

## 23. Dead Letter Queue cho event không thể xử lý

DLQ giữ event đã hết retry hoặc lỗi cần sửa thủ công.

Record DLQ nên có event ID, aggregate ID/version, event type và schema version, payload gốc hoặc reference an toàn, index/alias đích, attempts và thời điểm thử cuối, error type/message đã làm sạch, worker/build version, trạng thái remediation/replay, người hoặc job thực hiện replay nếu cần audit.

Không coi DLQ là nơi bỏ quên event. Cần dashboard, owner, alert, retention và quy trình replay. Một lỗi mapping hàng loạt có thể làm DLQ tăng rất nhanh mà không tạo exception ở API người dùng.

## 24. Replay event từ DLQ

Khi đã sửa lỗi:

1. Chọn event theo error type hoặc khoảng thời gian.
2. Kiểm tra event schema và aggregate version.
3. Xác định event còn cần áp dụng hay đã bị version mới hơn thay thế.
4. Dựng lại projection.
5. Gửi tới index đích.
6. Kiểm tra item-level result.
7. Chỉ đánh dấu replay thành công sau khi xác nhận.
8. Ghi audit trail.

Có hai hướng: replay payload nguyên bản để tái hiện sự kiện, hoặc đọc trạng thái mới nhất từ database và rebuild projection cho aggregate.

Nếu mục tiêu là search phản ánh trạng thái hiện tại, rebuild từ source mới nhất thường tránh việc áp dụng event lịch sử đã lỗi thời. Nếu cần audit hoặc event-sourced projection, replay theo thứ tự và version là cần thiết.

Không replay toàn bộ DLQ ngay sau outage. Bắt đầu bằng batch nhỏ, theo dõi latency/429 và tăng dần.

## 25. Outbox retention và dọn dữ liệu

Outbox table tăng liên tục nếu event delivered không được archive hoặc xóa theo retention. Cần quyết định:

- Giữ event đã delivered bao lâu.
- Có archive sang object storage/data warehouse không.
- DLQ retention khác delivered retention thế nào.
- Có cần giữ event để rebuild index không.
- Có yêu cầu audit hoặc điều tra lịch sử không.
- Cách partition và vacuum/cleanup database.

Không xóa event ngay khi Elasticsearch ack nếu tổ chức cần replay sau khi phát hiện bug projector. Một chiến lược có thể giữ event đã delivered một khoảng thời gian, sau đó archive và xóa theo batch.

Cleanup không nên khóa toàn bảng hoặc tạo transaction khổng lồ. Xóa theo partition/time range hoặc batch nhỏ.

## 26. CDC thay cho polling relay

Thay vì polling outbox table, có thể dùng Change Data Capture (CDC) đọc transaction log của database.

~~~text
Application transaction
      |
      v
Business tables + outbox_event
      |
      v
Database transaction log
      |
      v
Debezium connector
      |
      v
Kafka topic
      |
      v
Outbox event consumer
      |
      v
Elasticsearch projector
~~~

Debezium Outbox Event Router có thể biến outbox row thành message theo convention/configuration. Kafka giữ event và consumer offset, giúp scale consumer và replay theo retention.

CDC giảm polling query lên database và có thể cung cấp luồng event gần thời gian thực. Nhưng nó thêm hạ tầng và vận hành: connector, schema registry nếu dùng, Kafka, partitioning, offset, retention và monitoring.

Chọn polling nếu throughput vừa phải và muốn ít thành phần. Chọn CDC khi cần scale, throughput lớn, nhiều consumer hoặc đã có event streaming platform.

## 27. Polling và CDC có cùng nguyên tắc delivery

Dù relay đọc bằng polling hay CDC, vẫn cần xử lý:

- At-least-once delivery.
- Duplicate event.
- Event ordering.
- Schema evolution.
- Retry và DLQ.
- Idempotent projection.
- Source version.
- Delete.
- Rebuild/replay.
- Monitoring lag.

CDC không tự bảo đảm Elasticsearch index exactly once. Consumer có thể index thành công rồi crash trước khi commit Kafka offset; event sẽ được gửi lại.

Do đó, cùng một projector idempotent có thể được dùng cho polling relay và CDC consumer. Chỉ phần nguồn event/ack/checkpoint khác nhau.

## 28. Schema evolution của outbox event

Event có thể sống lâu hơn một phiên bản ứng dụng. Một worker mới có thể đọc event được tạo từ payload schema cũ.

Cần có schema_version và chính sách tương thích:

- Thêm field optional với default phù hợp.
- Không đổi nghĩa field hiện tại mà không version.
- Không xóa field đang được consumer cũ dùng.
- Xử lý enum value mới.
- Có adapter/migration cho event schema cũ.
- Giữ test fixture cho các schema version được hỗ trợ.

Consumer có thể có deserializer/mapper theo schema version. Không để một event cũ làm worker crash liên tục mà không vào DLQ.

## 29. Rebuild Elasticsearch index từ database và outbox

Một ưu điểm của việc coi Elasticsearch là projection là có thể tạo index mới.

~~~text
1. Capture consistent source/log position L0
2. Create products-v2 with target mapping
3. Read source snapshot
4. Bulk index snapshot into products-v2
5. Replay outbox/CDC events after L0
6. Catch up to a current watermark
7. Reconcile source and target
8. Switch read/write alias
9. Keep old index for rollback window
~~~

Điểm quan trọng là snapshot phải gắn với log position nhất quán. Nếu chỉ đọc snapshot rồi bắt đầu đọc event ở một thời điểm không chính xác, các thay đổi trong khoảng giữa có thể bị bỏ sót.

Dùng version guard để event cũ không ghi đè document mới trong index mới. Sau khi catch up, chạy reconciliation theo tenant/partition và kiểm tra search result trước khi chuyển alias.

## 30. Reconciliation sau đồng bộ

Một relay có thể báo mọi event delivered nhưng projection vẫn sai do bug transform, event thiếu, delete bị bỏ qua hoặc một luồng ghi bypass outbox.

Reconciliation so sánh source of truth với Elasticsearch:

- Document count theo tenant/type/status.
- ID tồn tại ở source nhưng thiếu trong index.
- Document trong index không còn ở source.
- Source version và projection version.
- Field quan trọng.
- Hash/checksum trên dữ liệu đã chuẩn hóa.
- Delete/tombstone consistency.

Không chỉ so tổng count toàn index. Hai tenant có thể lệch ngược chiều nhưng tổng vẫn bằng nhau.

Với dữ liệu lớn, chia theo tenant, ID range hoặc thời gian. Khi mismatch, tạo repair task có phạm vi nhỏ; đọc trạng thái mới nhất từ source và index lại với version guard.

## 31. Monitoring outbox và độ trễ đồng bộ

Các metric nên có:

- Pending outbox event count.
- Oldest pending event age.
- Events created per second.
- Events claimed/processed per second.
- Events delivered per second.
- Bulk request count và item count.
- Bulk item success/failure.
- Retry count và retry delay.
- DLQ size và oldest DLQ age.
- Lease expiry/reclaim count.
- Elasticsearch latency, 429, 5xx và timeout.
- Source-to-index lag.
- Searchable lag nếu yêu cầu read-after-write.

Đo lag từ timestamp nguồn, không chỉ từ lúc worker nhận event. Nếu event chờ 10 phút trong outbox rồi xử lý trong 100 ms, processing time thấp nhưng end-to-end lag vẫn là 10 phút.

Theo dõi p50, p95, p99 và oldest pending age. Average có thể che giấu một số event mắc lâu.

## 32. Micrometer metric trong Spring Boot

Có thể dùng Micrometer để ghi counter và timer:

~~~java
@Component
public class OutboxMetrics {

    private final MeterRegistry registry;

    public OutboxMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void delivered(String eventType) {
        registry.counter(
                "outbox.events",
                "result", "delivered",
                "event_type", eventType
        ).increment();
    }

    public void failed(String failureType) {
        registry.counter(
                "outbox.events",
                "result", "failed",
                "failure_type", failureType
        ).increment();
    }

    public void recordEndToEndLag(Duration lag) {
        registry.timer("outbox.end_to_end_lag")
                .record(lag);
    }

    public void recordProcessingTime(Duration duration) {
        registry.timer("outbox.processing_time")
                .record(duration);
    }
}
~~~

Đây là ví dụ cơ bản. Có thể thêm gauge cho pending count/oldest age, nhưng tránh query database nặng mỗi lần scrape.

Không đưa eventId, aggregateId, documentId hoặc tenant ID có cardinality cao vào metric tag. Dùng structured log/trace đã masking cho điều tra một event cụ thể.

## 33. Định nghĩa SLO và cảnh báo

Một số SLI có thể dùng:

- p95 source-to-index lag.
- p99 source-to-searchable lag.
- Oldest pending event age.
- Tỷ lệ event được delivery trong cửa sổ thời gian.
- Bulk item failure rate.
- DLQ growth rate.
- Reconciliation mismatch count.
- Consumer/checkpoint progress.

Ví dụ mục tiêu minh họa:

| Chỉ số | Mục tiêu ví dụ |
|---|---|
| p95 source-to-index lag | dưới 30 giây |
| p99 source-to-searchable lag | dưới 2 phút |
| Oldest pending age | dưới 5 phút |
| Event delivery success | 99.9% theo cửa sổ ngày |
| DLQ chưa xử lý | Không tăng liên tục |

Các con số cần được chọn theo yêu cầu sản phẩm, refresh interval, throughput và năng lực cluster.

Cảnh báo khi backlog tăng liên tục, lease hết hạn nhiều, 429 tăng, mapping error hàng loạt hoặc DLQ không được xử lý. Alert cần có owner và runbook.

## 34. Bảo mật dữ liệu outbox

Outbox có thể chứa snapshot của dữ liệu nghiệp vụ. Vì vậy:

- Chỉ cấp quyền đọc bảng cho relay cần thiết.
- Không ghi token/secret vào payload.
- Mã hóa dữ liệu nhạy cảm theo policy.
- Giới hạn retention và archive access.
- Sanitize error trước khi lưu.
- Không log toàn bộ payload nếu không cần.
- Bảo vệ DLQ và replay tool bằng role riêng.
- Audit ai replay hoặc sửa trạng thái event.
- Đảm bảo tenant ID lấy từ dữ liệu nghiệp vụ đáng tin cậy, không từ field client chưa authorize.

Nếu event chứa dữ liệu nhạy cảm, cần xem xét cả backup, snapshot, CDC topic và log vì chúng có thể giữ bản sao payload lâu hơn bảng nghiệp vụ.

## 35. Kiểm thử atomicity của business change và outbox

Một integration test nên chứng minh hai thao tác cùng commit hoặc cùng rollback.

Kịch bản commit:

1. Gọi service update product.
2. Đọc lại business row.
3. Đọc outbox row.
4. Xác nhận cả hai tồn tại và cùng aggregate version.

Kịch bản rollback:

1. Gọi service trong transaction rồi cố ý ném exception trước commit.
2. Xác nhận business row không thay đổi.
3. Xác nhận outbox event không được tạo.

Test cần chạy với database thật hoặc Testcontainers nếu cần xác minh transaction semantics. Mock repository không chứng minh hai bảng cùng transaction manager.

## 36. Kiểm thử crash sau Elasticsearch write

Đây là test quan trọng cho at-least-once delivery:

~~~text
1. Claim event E42
2. Project E42 to Elasticsearch successfully
3. Simulate worker crash before markDelivered
4. Lease expires
5. Another worker claims E42
6. Project E42 again
7. Mark delivered
~~~

Xác nhận:

- Document ID không bị nhân đôi.
- Projection vẫn đúng.
- Source version không lùi.
- Outbox cuối cùng được đánh dấu delivered.
- Duplicate không tạo side effect khác.

Nếu projector thực hiện thêm side effect ngoài Elasticsearch, những side effect đó cũng phải idempotent hoặc được quản lý riêng.

## 37. Kiểm thử ordering và stale event

Tạo hai event cùng aggregate:

- Version 41: tên cũ.
- Version 42: tên mới.

Cố ý xử lý version 42 trước version 41. Xác nhận document cuối cùng vẫn có version 42 và tên mới.

Test delete:

- Version 43 là ProductDeleted.
- Version 42 update đến muộn.
- Xác nhận document không được tạo lại.

Nếu dùng external versioning, integration test cần xác nhận semantics conflict của đúng server/client version. Nếu dùng application-side version check, test race condition khi hai worker cập nhật cùng aggregate.

## 38. Kiểm thử bulk partial failure và retry

Tạo batch có item hợp lệ, item lỗi mapping, item nhận 429 trong môi trường test có kiểm soát, và item conflict do version.

Xác nhận:

- Success được mark delivered.
- Retryable failure có next_attempt_at.
- Permanent failure vào DLQ.
- Stale event được đánh dấu superseded nếu policy cho phép.
- Checkpoint/claim không bỏ qua event chưa được lưu trạng thái bền vững.
- Replay sau sửa lỗi không ghi lùi version.

Không chỉ mock một exception tổng thể. Cần test classifier theo từng item response và có ít nhất một integration test với Elasticsearch thật.

## 39. Kiểm thử relay nhiều instance

Khi có nhiều worker:

1. Khởi chạy hai relay instance.
2. Tạo một tập outbox event.
3. Cho cả hai claim đồng thời.
4. Xác nhận một event không bị hai worker cùng sở hữu lease hợp lệ.
5. Dừng một worker sau claim.
6. Chờ lease hết hạn.
7. Xác nhận worker còn lại reclaim được event.
8. Kiểm tra duplicate handling và trạng thái cuối.

Có thể có duplicate do lease expiry hoặc network delay, nhưng không được có event bị bỏ qua. Cần xác nhận claim query thực sự dùng locking/lease đúng trên database production.

## 40. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Database đã đổi nhưng Elasticsearch chưa đổi | Dual write hoặc relay backlog | Outbox bền vững, theo dõi lag |
| Outbox event không có dù business row commit | Khác transaction manager/database | Cùng transaction resource |
| Bulk request thành công nhưng thiếu document | Bỏ qua item-level errors | Xử lý từng item |
| Event bị xử lý nhiều lần | Crash trước khi ack hoặc lease hết hạn | Idempotent projector |
| Document bị ghi lùi dữ liệu | Event cũ đến sau event mới | Aggregate version/external version |
| Delete rồi document xuất hiện lại | Update cũ đến muộn | Tombstone/version ordering |
| Worker giữ DB lock lâu | Gọi Elasticsearch trong transaction claim | Claim ngắn, network ngoài transaction |
| Hai worker xử lý cùng event | Claim không atomic hoặc lease race | SKIP LOCKED/lease token |
| Checkpoint bỏ qua event lỗi | Ack vị trí cao nhất thay vì contiguous progress | Theo dõi gap và trạng thái bền vững |
| Retry storm | Retry ngay và đồng loạt | Backoff, jitter, giảm concurrency |
| DLQ tăng mãi | Không có owner/replay process | Dashboard, alert và runbook |
| Rebuild index thiếu thay đổi | Snapshot không nối đúng CDC position | Snapshot + log position nhất quán |
| Mapping error lặp vô hạn | Không phân loại permanent error | DLQ và schema repair |

## 41. Checklist triển khai transactional outbox

**Transaction và schema**

- Business change và outbox event cùng database transaction.
- Event ID ổn định.
- Có aggregate ID/version và schema version.
- Payload có timestamp nguồn.
- Event immutable sau khi commit.
- Retention/archive rõ ràng.

**Relay**

- Claim batch bằng transaction ngắn.
- Lease có expiry và ownership token.
- Không giữ DB transaction khi gọi Elasticsearch.
- Nhiều worker không claim cùng event hợp lệ.
- Crash/reclaim không làm mất event.
- Checkpoint không bỏ qua gap.

**Projector**

- Document ID ổn định.
- Idempotent khi duplicate.
- Version guard chống stale write.
- Delete/tombstone được xử lý.
- Bulk item response được kiểm tra riêng.
- Mapping/schema error được phân loại.

**Retry và recovery**

- Backoff và jitter.
- Giới hạn retry.
- DLQ có owner và replay.
- Rebuild index từ source + change stream.
- Reconciliation theo tenant/partition/version.
- Có runbook và recovery drill.

**Observability và security**

- Theo dõi end-to-end lag, backlog và throughput.
- Theo dõi 429, timeout, item errors và DLQ.
- Có SLO/alert.
- Bảo vệ outbox, CDC topic và DLQ.
- Không log payload nhạy cảm.
- Audit replay và repair.

Transactional outbox tạo ra một đường chuyển tiếp bền vững giữa database và Elasticsearch: business change và event được commit cùng nhau, còn relay có thể retry khi downstream gặp lỗi. Vì delivery có thể lặp, projector phải idempotent và dùng version để chống event cũ ghi đè trạng thái mới. Relay cần claim bằng transaction ngắn, xử lý network ngoài transaction, kiểm tra từng bulk item và giữ event lỗi trong retry/DLQ. Khi kết hợp outbox với monitoring lag, replay, reconciliation và quy trình rebuild index, Elasticsearch có thể bắt kịp source of truth sau outage hoặc deploy lỗi mà không âm thầm bỏ mất thay đổi nghiệp vụ.

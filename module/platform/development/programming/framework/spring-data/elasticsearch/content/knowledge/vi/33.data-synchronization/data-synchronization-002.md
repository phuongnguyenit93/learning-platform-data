# Phân biệt ghi kép trực tiếp, outbox và CDC

Một ứng dụng thường lưu dữ liệu nghiệp vụ trong cơ sở dữ liệu quan hệ và đồng thời đưa dữ liệu sang Elasticsearch để tìm kiếm. Câu hỏi quan trọng là: làm sao bảo đảm hai nơi được cập nhật nhất quán khi mạng lỗi, process dừng giữa chừng hoặc một message được giao lại?

Có ba cách thường gặp:

- **Ghi kép trực tiếp (dual write)**: service gọi ghi vào database và Elasticsearch trong cùng luồng xử lý.
- **Transactional outbox**: service ghi dữ liệu nghiệp vụ và một bản ghi sự kiện vào cùng transaction database; một tiến trình khác chuyển sự kiện sang Elasticsearch.
- **Change Data Capture (CDC)**: hệ thống đọc transaction log của database để phát hiện thay đổi và chuyển chúng thành sự kiện hoặc bản ghi index.

Ba cách này có độ phức tạp, độ trễ và bảo đảm nhất quán khác nhau. Spring Data Elasticsearch thường là lớp ghi projection vào Elasticsearch; nó không tự tạo transaction phân tán giữa Elasticsearch và database nghiệp vụ.

## 1. Vì sao cần đồng bộ database với Elasticsearch?

Giả sử ứng dụng quản lý sản phẩm. Database quan hệ là nơi lưu trạng thái chính thức, còn Elasticsearch phục vụ tìm kiếm theo tên, mô tả, danh mục và bộ lọc.

Một bản ghi trong database:

~~~json
{
  "id": 1001,
  "name": "Wireless Keyboard",
  "price": 1299000,
  "status": "PUBLISHED",
  "version": 42
}
~~~

Document Elasticsearch có thể được thiết kế phục vụ truy vấn:

~~~json
{
  "productId": "1001",
  "name": "Wireless Keyboard",
  "price": 1299000,
  "status": "PUBLISHED",
  "category": "ACCESSORIES",
  "aggregateVersion": 42
}
~~~

Hai cấu trúc không nhất thiết giống nhau:

- Database tối ưu cho transaction và ràng buộc dữ liệu nghiệp vụ.
- Elasticsearch tối ưu cho full-text search, filter, sort và aggregation.
- Elasticsearch document có thể kết hợp dữ liệu từ nhiều bảng.
- Mapping và analyzer của Elasticsearch có thể khác cấu trúc database.

Vì vậy, Elasticsearch thường đóng vai trò **read model hoặc search projection** được xây dựng từ dữ liệu nguồn. Khi database thay đổi, projection cần được cập nhật theo.

## 2. Vấn đề atomicity khi ghi hai nơi

Giả sử service thực hiện:

~~~java
@Transactional
public void publishProduct(Product product) {
    productRepository.save(product);
    elasticsearchOperations.save(toDocument(product));
}
~~~

Nhìn qua, cả hai lệnh nằm trong một phương thức có `@Transactional`. Nhưng transaction của Spring Data JPA không tự bao trùm thao tác ghi Elasticsearch thành một transaction phân tán có khả năng commit hoặc rollback nguyên tử cùng database.

Một số tình huống có thể xảy ra:

| Trình tự | Sự cố | Trạng thái có thể còn lại |
|---|---|---|
| Database ghi trước | Elasticsearch lỗi | Database đã commit, search index chưa cập nhật |
| Elasticsearch ghi trước | Database rollback | Search index có dữ liệu chưa được database chấp nhận |
| Cả hai ghi thành công | Response về client bị mất | Client có thể retry và gửi lại thao tác |
| Process dừng giữa hai lệnh | Lệnh thứ hai chưa chạy | Hai nơi lệch nhau |
| Elasticsearch timeout | Không rõ server đã ghi hay chưa | Retry có thể ghi lặp hoặc ghi đè dữ liệu mới |

Đây là **khoảng trống atomicity**: hai hệ thống có cơ chế lưu trữ và commit độc lập. Một annotation transaction trên service không làm cho chúng tự động trở thành một transaction duy nhất.

Có thể dùng distributed transaction trong một số kiến trúc, nhưng Elasticsearch và database không mặc nhiên tham gia cùng một transaction manager theo cách JPA transaction thường dùng. Với search projection, outbox hoặc CDC thường dễ vận hành hơn.

## 3. Ghi kép trực tiếp (dual write)

Ghi kép trực tiếp là service chủ động ghi vào database và Elasticsearch trong cùng luồng xử lý.

Ví dụ:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;
    private final ElasticsearchOperations elasticsearchOperations;

    public ProductService(
            ProductRepository productRepository,
            ElasticsearchOperations elasticsearchOperations
    ) {
        this.productRepository = productRepository;
        this.elasticsearchOperations = elasticsearchOperations;
    }

    @Transactional
    public Product publish(Product product) {
        product.setStatus("PUBLISHED");

        Product saved = productRepository.save(product);

        ProductDocument document = toDocument(saved);
        elasticsearchOperations.save(document);

        return saved;
    }
}
~~~

Service có thể trả kết quả sau khi cả hai lệnh hoàn tất. Cách này dễ hiểu và có thể phù hợp khi hệ thống nhỏ, độ trễ thấp quan trọng và ứng dụng có cơ chế xử lý sai lệch rõ ràng.

Tuy nhiên, nếu Elasticsearch lỗi sau khi database đã commit, transaction database không tự rollback phần commit đó. Nếu Elasticsearch ghi thành công trước khi database commit rồi database rollback, search index có thể chứa trạng thái chưa được chấp nhận.

### Ưu điểm

- Ít thành phần hạ tầng.
- Luồng code dễ theo dõi.
- Có thể phản hồi cho người dùng sau khi đã thử cập nhật cả hai nơi.
- Phù hợp với hệ thống nhỏ hoặc trường hợp Elasticsearch chỉ là projection có thể tái tạo.

### Hạn chế

- Không có atomic commit giữa hai hệ thống.
- Request nghiệp vụ phụ thuộc độ sẵn sàng của Elasticsearch nếu chờ ghi đồng bộ.
- Retry và timeout có thể tạo duplicate hoặc ghi đè dữ liệu mới.
- Logic phục hồi thường bị rải rác trong service.
- Khi nhiều service cùng ghi, việc giữ thứ tự cập nhật khó hơn.

Không nên coi dual write là nhất quán chỉ vì hai lệnh được viết cạnh nhau trong cùng một method.

## 4. Các biến thể của dual write

### Ghi database rồi ghi Elasticsearch

~~~text
Client
  |
  v
Application
  |
  +----> Database commit
  |
  +----> Elasticsearch index
  |
  v
Response
~~~

Nếu database commit thành công nhưng Elasticsearch thất bại, ứng dụng phải lưu lại trạng thái cần đồng bộ và retry sau đó. Nếu không có retry hoặc reconciliation, document có thể lệch vô thời hạn.

### Ghi Elasticsearch rồi ghi database

~~~text
Client
  |
  v
Application
  |
  +----> Elasticsearch index
  |
  +----> Database commit
  |
  v
Response
~~~

Nếu Elasticsearch ghi thành công nhưng database rollback, search projection có thể hiển thị dữ liệu không tồn tại trong nguồn chính thức.

### Ghi song song

~~~java
Mono.zip(
        saveDatabaseReactive(product),
        saveElasticsearchReactive(toDocument(product))
);
~~~

Ghi song song giảm thời gian chờ tuần tự, nhưng không giải quyết atomicity. Một publisher có thể thành công trong khi publisher kia lỗi. Khi `zip` phát lỗi, side effect đã hoàn tất ở nhánh kia không tự được rollback.

Không chọn ghi song song chỉ để giảm latency nếu chưa có chính sách xử lý partial success.

## 5. Khi nào dual write có thể chấp nhận?

Dual write có thể là lựa chọn hợp lý nếu:

- Dữ liệu Elasticsearch có thể tái tạo từ nguồn chính.
- Sai lệch ngắn hạn được chấp nhận.
- Có retry queue hoặc cơ chế đối soát.
- Tải và số writer còn nhỏ.
- Có thể chấp nhận request nghiệp vụ thất bại hoặc báo trạng thái đồng bộ đang chờ.

Nếu cần cập nhật search index trước khi trả response, service có thể ghi database trước, sau đó ghi Elasticsearch và trả lỗi hoặc trạng thái pending khi đồng bộ thất bại. Nhưng cần hiểu rằng database đã commit và request trả lỗi có thể khiến client retry. ID ổn định và idempotency vẫn cần thiết.

Không nên dùng dual write cho dữ liệu có yêu cầu nhất quán chặt mà không có cơ chế phục hồi, chẳng hạn số dư hoặc trạng thái thanh toán. Elasticsearch thường không nên là nơi quyết định transaction tài chính nếu database nghiệp vụ là nguồn sự thật.

## 6. Transactional outbox là gì?

Transactional outbox giải quyết vấn đề ứng dụng cần cập nhật database và phát một sự kiện nhưng không thể commit hai hệ thống độc lập trong một transaction.

Thay vì service ghi trực tiếp database rồi gọi Elasticsearch, service thực hiện hai thao tác trong **cùng transaction của database**:

1. Cập nhật bảng nghiệp vụ.
2. Thêm một bản ghi vào bảng outbox mô tả thay đổi cần phát.

Nếu transaction commit, cả thay đổi nghiệp vụ và outbox record cùng được lưu. Nếu rollback, cả hai cùng rollback.

Một tiến trình relay đọc outbox và chuyển sự kiện sang message broker hoặc trực tiếp sang Elasticsearch.

~~~mermaid
flowchart LR
    A["Application service"] --> B["Database transaction"]
    B --> C["Business table"]
    B --> D["Outbox table"]
    D --> E["Outbox relay / CDC"]
    E --> F["Message broker"]
    F --> G["Elasticsearch consumer"]
    G --> H["Search projection"]
~~~

Điểm quan trọng là database chỉ cần bảo đảm tính nguyên tử giữa hai ghi trong chính database. Việc phát sự kiện ra ngoài được thực hiện bất đồng bộ và có thể retry.

## 7. Thiết kế bảng outbox

Một bảng outbox có thể chứa:

~~~sql
CREATE TABLE outbox_event (
    event_id          VARCHAR(100) PRIMARY KEY,
    aggregate_type    VARCHAR(100) NOT NULL,
    aggregate_id      VARCHAR(150) NOT NULL,
    aggregate_version BIGINT,
    event_type        VARCHAR(150) NOT NULL,
    schema_version    INTEGER NOT NULL,
    payload           TEXT NOT NULL,
    occurred_at       TIMESTAMP NOT NULL,
    published_at      TIMESTAMP NULL
);
~~~

Ý nghĩa:

| Field | Mục đích |
|---|---|
| `event_id` | Định danh duy nhất của event, dùng cho deduplication |
| `aggregate_type` | Loại thực thể, ví dụ Product |
| `aggregate_id` | ID thực thể nghiệp vụ |
| `aggregate_version` | Phiên bản thay đổi của aggregate |
| `event_type` | Tên sự kiện, ví dụ ProductPublished |
| `schema_version` | Phiên bản cấu trúc payload |
| `payload` | Nội dung event hoặc dữ liệu cần dựng projection |
| `occurred_at` | Thời điểm nghiệp vụ xảy ra |
| `published_at` | Thời điểm relay xác nhận đã phát, nếu dùng polling |

Một số triển khai còn có `headers`, `tenant_id`, `trace_id`, `correlation_id`, số lần thử và trạng thái xử lý.

Không cần mọi outbox phải có cùng schema. Điều quan trọng là có event ID ổn định, aggregate identity, event type, payload và version/schema phù hợp với cách consumer xử lý.

## 8. Ghi business data và outbox trong cùng transaction

Ví dụ entity outbox bằng JPA:

~~~java
@Entity
@Table(name = "outbox_event")
public class OutboxEventEntity {

    @Id
    private String eventId;

    private String aggregateType;
    private String aggregateId;
    private Long aggregateVersion;
    private String eventType;
    private Integer schemaVersion;

    @Lob
    private String payload;

    private Instant occurredAt;

    // Constructors, getters and setters
}
~~~

Service:

~~~java
@Service
public class ProductApplicationService {

    private final ProductRepository productRepository;
    private final OutboxEventRepository outboxRepository;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    public ProductApplicationService(
            ProductRepository productRepository,
            OutboxEventRepository outboxRepository,
            ObjectMapper objectMapper,
            Clock clock
    ) {
        this.productRepository = productRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Transactional
    public Product publish(long productId) {
        Product product = productRepository.findById(productId)
                .orElseThrow();

        product.publish();
        product.increaseVersion();

        Product saved = productRepository.save(product);

        ProductPublished event = new ProductPublished(
                saved.getId(),
                saved.getVersion(),
                saved.getName(),
                saved.getPrice(),
                clock.instant()
        );

        outboxRepository.save(
                OutboxEventEntity.from(
                        event.eventId(),
                        "Product",
                        String.valueOf(saved.getId()),
                        saved.getVersion(),
                        "ProductPublished",
                        1,
                        serialize(event),
                        clock.instant()
                )
        );

        return saved;
    }

    private String serialize(Object event) {
        try {
            return objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize outbox event",
                    ex
            );
        }
    }
}
~~~

Đây là ví dụ minh họa. `ProductRepository` và `OutboxEventRepository` phải cùng tham gia một transaction manager và cùng database. Nếu hai repository dùng hai datasource hoặc hai transaction manager độc lập, tính nguyên tử không còn được bảo đảm chỉ bằng `@Transactional`.

Nếu serialize event thất bại, transaction cần rollback để không lưu trạng thái nghiệp vụ mà thiếu outbox event tương ứng.

## 9. Outbox relay bằng polling

Một cách triển khai relay là định kỳ đọc các event chưa phát:

~~~sql
SELECT *
FROM outbox_event
WHERE published_at IS NULL
ORDER BY occurred_at
LIMIT 100;
~~~

Relay gửi event tới Kafka hoặc một message broker khác, sau đó đánh dấu `published_at`.

Luồng:

~~~text
Outbox table
    |
    v
Poll unpublished events
    |
    v
Publish to broker
    |
    v
Mark published
~~~

Trong môi trường nhiều relay instance, cần cơ chế claim/lock để hai worker không cùng xử lý một batch không cần thiết. Có thể dùng row locking, lease hoặc cột trạng thái xử lý tùy database.

Không giữ một transaction database dài trong lúc chờ network broker nếu có thể tránh. Một thiết kế phổ biến là claim một batch ngắn trong transaction, publish bên ngoài transaction, rồi đánh dấu hoàn tất trong transaction khác. Cách này cần xử lý lease hết hạn và event được phát lại.

### Khoảng trống giữa publish và đánh dấu

Một tình huống quan trọng:

1. Relay publish event thành công.
2. Process dừng trước khi cập nhật `published_at`.
3. Relay khởi động lại.
4. Event vẫn được xem là chưa phát và được publish lần nữa.

Do đó, polling outbox thường cung cấp delivery at-least-once. Consumer phải chấp nhận duplicate và xử lý idempotent.

Nếu đánh dấu published trước khi publish, process có thể dừng sau khi đánh dấu nhưng trước khi gửi; event sẽ bị mất. Vì vậy, ưu tiên không mất event và thiết kế consumer chống duplicate.

## 10. Outbox kết hợp CDC

Outbox không bắt buộc phải dùng polling. Có thể dùng CDC để đọc transaction log và phát các dòng mới được insert vào outbox.

Ví dụ với Debezium:

~~~text
Application transaction
       |
       v
Business table + Outbox table
       |
       v
Database transaction log
       |
       v
Debezium connector
       |
       v
Outbox event router
       |
       v
Kafka topic
       |
       v
Elasticsearch projection consumer
~~~

Ở đây:

- Ứng dụng vẫn ghi business table và outbox table trong cùng transaction.
- Database ghi transaction log khi commit.
- Debezium đọc log và phát thay đổi outbox.
- Outbox Event Router có thể chuyển row outbox thành message có key, topic và payload phù hợp.
- Consumer nhận message rồi cập nhật Elasticsearch.

CDC không thay thế ý nghĩa của outbox. Outbox xác định **sự kiện nghiệp vụ nào cần phát**; CDC là một cách **vận chuyển sự kiện ra khỏi database**.

Đây là mô hình thường dùng khi cần độ tin cậy cao, throughput lớn và muốn tránh polling liên tục.

## 11. CDC là gì?

Change Data Capture là kỹ thuật thu nhận thay đổi dữ liệu từ database. Với log-based CDC, connector đọc transaction log của database thay vì liên tục chạy câu SELECT để so sánh trạng thái.

Nguồn log tùy database:

- PostgreSQL: Write-Ahead Log (WAL).
- MySQL: binary log (binlog).
- SQL Server: transaction log hoặc cơ chế CDC phù hợp.
- Oracle: redo log qua connector được hỗ trợ.

CDC có thể phát các thao tác:

- Insert.
- Update.
- Delete.
- Snapshot ban đầu.
- Một số metadata về transaction, timestamp, log position hoặc source offset tùy connector.

CDC thường chuyển row change thành event trong Kafka hoặc hệ thống streaming khác. Một sink connector hoặc consumer sẽ đưa event đó vào Elasticsearch.

## 12. CDC trực tiếp từ bảng nghiệp vụ khác outbox thế nào?

Có hai cách dùng CDC thường gặp:

1. **Raw table CDC**: đọc thay đổi trực tiếp từ bảng nghiệp vụ.
2. **Outbox CDC**: đọc các event đã được ứng dụng ghi vào bảng outbox.

| Tiêu chí | Raw table CDC | Outbox CDC |
|---|---|---|
| Dữ liệu phát | Row-level change | Domain event do ứng dụng định nghĩa |
| Ngữ nghĩa | Phản ánh thay đổi cấu trúc bảng | Phản ánh sự kiện nghiệp vụ |
| Ghép nhiều bảng | Consumer phải tự dựng lại trạng thái | Event có thể chứa dữ liệu đã tổng hợp |
| Phụ thuộc schema DB | Cao hơn | Thấp hơn ở consumer |
| Phù hợp | Đồng bộ bản sao, data pipeline | Tích hợp service và projection nghiệp vụ |
| Logic phát event | Suy ra từ row changes | Ứng dụng quyết định rõ event type |

Ví dụ raw CDC có thể phát rằng cột `status` trong bảng product đổi từ DRAFT sang PUBLISHED. Nhưng nó không nhất thiết biết nghiệp vụ đó tương ứng với `ProductPublished`, có cần phát thông báo hay phải kết hợp thêm bảng nào.

Outbox có thể phát event:

~~~json
{
  "eventId": "evt-184",
  "eventType": "ProductPublished",
  "aggregateId": "1001",
  "aggregateVersion": 42,
  "occurredAt": "2026-11-13T10:00:00Z",
  "payload": {
    "name": "Wireless Keyboard",
    "price": 1299000,
    "status": "PUBLISHED"
  }
}
~~~

Event này mang ngữ nghĩa nghiệp vụ rõ hơn. Consumer không phải suy đoán event type từ tên bảng và cột thay đổi.

## 13. Khi nào nên dùng raw CDC?

Raw CDC phù hợp khi mục tiêu là đồng bộ dữ liệu ở mức bảng hoặc xây data pipeline:

- Sao chép thay đổi sang data warehouse.
- Đồng bộ một số bảng sang hệ thống tìm kiếm.
- Xây read replica hoặc cache projection.
- Thu thập lịch sử row changes.
- Tích hợp với nền tảng streaming.

Nếu dùng raw CDC để cập nhật Elasticsearch, cần thiết kế consumer để:

1. Hiểu schema của từng bảng.
2. Xử lý insert/update/delete.
3. Ghép dữ liệu từ nhiều bảng khi document cần nhiều nguồn.
4. Xử lý thứ tự thay đổi.
5. Xử lý snapshot ban đầu và chuyển sang streaming.
6. Theo dõi schema evolution.
7. Tạo document ID ổn định.

Một thay đổi row đơn lẻ có thể không đủ thông tin để tạo document hoàn chỉnh. Ví dụ sản phẩm cần cả category name, inventory summary và dữ liệu thương hiệu. Consumer có thể phải đọc thêm bảng hoặc duy trì state riêng.

## 14. Khi nào nên dùng outbox thay vì raw CDC?

Outbox phù hợp khi ứng dụng muốn phát sự kiện theo ngữ nghĩa nghiệp vụ và kiểm soát hợp đồng event.

Ví dụ:

- `ProductCreated`.
- `ProductPriceChanged`.
- `ProductPublished`.
- `ProductDeleted`.

Ứng dụng biết rõ khi nào một hành động nghiệp vụ xảy ra và có thể ghi event cùng transaction với dữ liệu chính.

Outbox đặc biệt hữu ích khi:

- Một thay đổi cần thông báo cho nhiều consumer.
- Payload cần chứa dữ liệu đã chuẩn hóa hoặc snapshot.
- Schema database có thể thay đổi nhưng contract event cần ổn định.
- Nhiều service cần dùng cùng một event.
- Cần audit và replay theo event identity.

Không nên tạo một event chung chung như `ProductRowUpdated` cho mọi thay đổi nếu consumer cần hiểu nghiệp vụ cụ thể. Ngược lại, không cần tạo quá nhiều event nhỏ nếu consumer chỉ cần một projection snapshot.

## 15. Consumer cập nhật Elasticsearch bằng Spring Data

Sau khi nhận event từ broker, consumer chuyển event thành document và ghi bằng Spring Data Elasticsearch.

Ví dụ:

~~~java
@Component
public class ProductProjectionConsumer {

    private final ElasticsearchOperations operations;

    public ProductProjectionConsumer(
            ElasticsearchOperations operations
    ) {
        this.operations = operations;
    }

    public void handle(ProductPublished event) {
        ProductDocument document = new ProductDocument();

        document.setId(String.valueOf(event.productId()));
        document.setProductId(String.valueOf(event.productId()));
        document.setName(event.name());
        document.setPrice(event.price());
        document.setStatus("PUBLISHED");
        document.setAggregateVersion(event.aggregateVersion());

        operations.save(
                document,
                IndexCoordinates.of("products")
        );
    }
}
~~~

`operations.save(...)` ghi document theo ID. Khi cùng event được giao lại và payload vẫn là cùng một snapshot, việc ghi lại cùng ID thường đưa source về cùng trạng thái.

Nhưng nếu event cũ đến sau event mới, `save` có thể ghi đè projection mới hơn bằng dữ liệu cũ. ID ổn định chống tạo nhiều document cho cùng sản phẩm; nó không tự bảo đảm thứ tự event.

Consumer cần version guard hoặc một chiến lược ordering phù hợp.

## 16. Idempotency và event ordering trong projection

Giả sử hai event của cùng sản phẩm:

~~~text
Event version 42: price = 1,299,000
Event version 43: price = 1,499,000
~~~

Nếu version 43 được xử lý trước rồi version 42 đến muộn, một lệnh save đơn giản có thể ghi giá cũ trở lại.

Có thể lưu `aggregateVersion` trong document và chỉ áp dụng event có version lớn hơn:

~~~painless
if (ctx._source.aggregateVersion == null
        || params.aggregateVersion > ctx._source.aggregateVersion) {
    ctx._source.name = params.name;
    ctx._source.price = params.price;
    ctx._source.status = params.status;
    ctx._source.aggregateVersion = params.aggregateVersion;
} else {
    ctx.op = 'noop';
}
~~~

Script được gọi với params từ event. Nó giúp event cũ trở thành no-op nếu projection đã có version mới hơn.

Một số lựa chọn khác:

- Partition message theo aggregate ID để giữ thứ tự trong cùng aggregate.
- Dùng external versioning khi ghi document nếu API và mô hình version phù hợp.
- Dùng sequence number do nguồn nghiệp vụ cấp.
- Dùng consumer state/checkpoint nếu cần kiểm soát thứ tự phức tạp.

Không dùng timestamp nhận message làm version. Đồng hồ của producer và consumer có thể lệch, và thời điểm nhận không nhất thiết phản ánh thứ tự nghiệp vụ.

## 17. Xử lý delete event

Đồng bộ không chỉ có create/update. Khi sản phẩm bị xóa trong database, projection Elasticsearch cũng cần được xóa hoặc đánh dấu tombstone.

Event:

~~~json
{
  "eventId": "evt-delete-1001",
  "eventType": "ProductDeleted",
  "aggregateId": "1001",
  "aggregateVersion": 44
}
~~~

Consumer có thể gọi:

~~~java
public void handle(ProductDeleted event) {
    operations.delete(
            event.productId().toString(),
            ProductDocument.class,
            IndexCoordinates.of("products")
    );
}
~~~

Nếu cần chống event cũ làm sản phẩm xuất hiện trở lại, xóa vật lý có thể chưa đủ vì sau khi document biến mất, version guard cũng biến mất. Có thể lưu tombstone/version riêng, dùng soft-delete field hoặc duy trì event sequence ở một nơi khác.

Tombstone có thể là:

~~~json
{
  "productId": "1001",
  "aggregateVersion": 44,
  "deleted": true
}
~~~

Search query lọc `deleted = false`. Cách này giữ version để event cũ đến muộn không tái tạo document đã xóa. Cần có chính sách retention và dọn tombstone sau khi không còn khả năng nhận event cũ.

## 18. Xác nhận message sau khi Elasticsearch ghi thành công

Với message consumer, không nên acknowledge event trước khi Elasticsearch đã xác nhận ghi thành công nếu mục tiêu là không mất projection update.

Luồng phổ biến:

~~~text
Broker delivers event
        |
        v
Consumer maps event
        |
        v
Elasticsearch write
        |
        +---- failure -> retry / DLQ
        |
        v
Acknowledge message
~~~

Ví dụ ý tưởng với Spring Kafka:

~~~java
@KafkaListener(topics = "product-events")
public void onProductPublished(
        ProductPublished event,
        Acknowledgment acknowledgment
) {
    productProjectionConsumer.handle(event);

    // Chỉ acknowledge sau khi thao tác ghi ES thành công.
    acknowledgment.acknowledge();
}
~~~

Đây là ví dụ cho listener dùng manual acknowledgment. Cấu hình acknowledgment mode, transaction và error handler phải phù hợp với ứng dụng.

Nếu Elasticsearch ghi thành công nhưng process dừng trước acknowledgment, broker có thể giao lại event. Consumer phải idempotent.

Nếu acknowledge trước khi ghi Elasticsearch và sau đó process dừng, broker có thể không giao lại event; projection sẽ bị thiếu dữ liệu.

## 19. Xử lý bulk và partial failure ở consumer

Consumer có thể gom nhiều event thành một bulk request để tăng throughput. Bulk API có thể thành công một phần, nên không được acknowledge cả batch chỉ dựa vào việc request tổng thể trả response.

Cần phân loại từng item:

| Kết quả | Hướng xử lý |
|---|---|
| Index/create thành công | Đánh dấu item đã xử lý |
| Version conflict do event cũ | Xác định no-op hợp lệ hay lỗi cần xử lý |
| Mapping error | Đưa vào DLQ hoặc sửa schema/payload |
| 429 hoặc lỗi tạm thời | Retry có backoff |
| Timeout không rõ kết quả | Retry cùng ID/version theo chính sách idempotent |
| Document missing khi update | Xác định có cần upsert hay event đến sai thứ tự |

Nếu broker offset bao phủ nhiều event trong batch, chỉ commit offset khi tất cả event trước offset đó đã được xử lý theo chính sách. Với partial failure, có thể retry item lỗi, tách batch hoặc chuyển item vĩnh viễn lỗi sang DLQ rồi mới tiến offset.

Không retry cả batch mù quáng nếu một số script hoặc update operation không idempotent.

## 20. So sánh ba cách tiếp cận

| Tiêu chí | Dual write trực tiếp | Transactional outbox | Raw CDC |
|---|---|---|---|
| Nguồn thay đổi | Service ghi hai nơi | Service ghi business + outbox | Transaction log database |
| Atomicity | Không có giữa hai hệ thống | Business row và outbox row cùng transaction DB | CDC quan sát commit đã ghi trong DB |
| Ngữ nghĩa event | Do service tự điều phối | Domain event rõ ràng | Row-level change |
| Độ phức tạp | Thấp ban đầu | Trung bình | Trung bình đến cao |
| Độ trễ | Có thể đồng bộ ngay | Thường bất đồng bộ | Thường bất đồng bộ |
| Retry | Tự thiết kế trong service | Relay và consumer retry | Connector/consumer retry |
| Duplicate | Có thể do client retry | Có thể do publish lại | Có thể do offset/replay |
| Replay | Thường khó nếu không lưu event | Có thể phát lại outbox/event log | Có thể snapshot/replay từ log nếu còn retention |
| Phụ thuộc schema DB | Thấp ở code ghi, cao ở logic mapping | Thấp hơn ở consumer | Cao hơn |
| Phù hợp | Hệ thống nhỏ, yêu cầu đơn giản | Đồng bộ nghiệp vụ đáng tin cậy | Data pipeline và đồng bộ thay đổi ở mức dữ liệu |

Outbox + CDC là sự kết hợp phổ biến: outbox xác định domain event, còn CDC vận chuyển row outbox ra broker.

## 21. CDC snapshot ban đầu và streaming

Khi một CDC connector mới được triển khai, Elasticsearch có thể chưa có document nào. Chỉ đọc các thay đổi mới từ transaction log sẽ không tự tạo lại toàn bộ dữ liệu lịch sử.

Một quy trình CDC thường cần:

1. Chụp snapshot ban đầu của các bảng hoặc outbox cần theo dõi.
2. Ghi nhận vị trí log tương ứng.
3. Phát các bản ghi snapshot.
4. Tiếp tục đọc thay đổi mới từ transaction log.
5. Duy trì offset/checkpoint để tiếp tục sau restart.

Cách chuyển từ snapshot sang streaming phụ thuộc connector và database. Cần kiểm tra chế độ snapshot, offset và semantics của connector đang dùng.

Nếu dùng outbox CDC, snapshot toàn bộ outbox lịch sử có thể không cần thiết hoặc không mong muốn. Projection ban đầu có thể được dựng từ snapshot business data, sau đó CDC chỉ phát các event mới từ một vị trí log nhất quán. Cần thiết kế điểm bắt đầu để không bỏ sót thay đổi giữa snapshot và streaming.

## 22. Schema evolution và version của event

Database schema và event schema có thể thay đổi theo thời gian. Consumer cần xử lý event cũ còn nằm trong broker hoặc DLQ.

Ví dụ event version 1:

~~~json
{
  "eventType": "ProductPublished",
  "schemaVersion": 1,
  "payload": {
    "productId": "1001",
    "name": "Keyboard"
  }
}
~~~

Event version 2 bổ sung category:

~~~json
{
  "eventType": "ProductPublished",
  "schemaVersion": 2,
  "payload": {
    "productId": "1001",
    "name": "Keyboard",
    "category": "ACCESSORIES"
  }
}
~~~

Consumer nên:

- Có schema version rõ ràng.
- Thêm field theo hướng tương thích khi có thể.
- Đặt default cho field mới nếu nghiệp vụ cho phép.
- Không đổi ý nghĩa một field cũ mà không đổi version.
- Giữ khả năng xử lý event cũ trong thời gian retention/replay.
- Version hóa mapping và index khi cần thay đổi kiểu field Elasticsearch.

Không để consumer phụ thuộc trực tiếp vào cấu trúc bảng nội bộ nếu contract cần tồn tại lâu dài.

## 23. Quản lý lag và quan sát đồng bộ

Đồng bộ bất đồng bộ tạo ra khoảng trễ giữa database và Elasticsearch. Ứng dụng cần đo và hiển thị được trạng thái đó.

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| Outbox backlog | Số event chưa được relay |
| Oldest unpublished age | Tuổi của event cũ nhất chưa phát |
| CDC source lag | Độ trễ đọc transaction log |
| Consumer lag | Số message chưa xử lý |
| Projection latency | Thời gian từ event đến khi ES ghi xong |
| Retry count | Số lần retry |
| DLQ count | Số event không thể xử lý tự động |
| Bulk item failures | Số item lỗi trong mỗi bulk |
| Version no-op/conflict | Số event bị bỏ qua do version cũ |

Có thể thêm timestamp `occurredAt` trong event và ghi `indexedAt` trong projection để đo độ trễ.

Không chỉ log lỗi. Cần cảnh báo khi backlog tăng liên tục, oldest event quá cũ hoặc DLQ xuất hiện lỗi schema/mapping hàng loạt.

## 24. Reconciliation và khả năng rebuild projection

Outbox hoặc CDC giảm nguy cơ mất event nhưng không loại bỏ mọi lỗi vận hành. Consumer có thể bug, mapping có thể sai, event có thể bị đưa vào DLQ hoặc một index có thể bị xóa.

Nên có quy trình reconciliation:

1. Đọc tập ID/version từ nguồn chính.
2. Đối chiếu với Elasticsearch projection.
3. Phát hiện document thiếu, thừa hoặc version cũ.
4. Tạo lại projection từ nguồn chính hoặc event log.
5. Ghi nhận số lượng và kết quả sửa chữa.

Nếu Elasticsearch chỉ là read model, có thể xóa index cũ, tạo index mới và rebuild từ database hoặc event history. Sau khi rebuild, chuyển alias sang index mới.

Một quy trình reindex an toàn thường cần:

- Snapshot dữ liệu nguồn tại một mốc.
- Tiếp tục thu nhận thay đổi phát sinh trong lúc rebuild.
- Áp dụng thay đổi theo version để không ghi event cũ đè snapshot mới.
- Kiểm tra số lượng và dữ liệu mẫu.
- Chuyển alias khi index mới sẵn sàng.

Không dùng Elasticsearch làm nguồn sự thật duy nhất nếu kiến trúc nghiệp vụ đã xác định database hoặc event store là nguồn chính.

## 25. Chọn direct dual write, outbox hay CDC?

Có thể chọn theo câu hỏi:

### Cần code đơn giản và dữ liệu search có thể tái tạo?

Dual write có retry/reconciliation có thể đủ cho hệ thống nhỏ. Tuy nhiên, phải ghi nhận trường hợp DB thành công nhưng ES thất bại và có cách sửa projection.

### Cần bảo đảm thay đổi nghiệp vụ không bị mất khi process dừng?

Transactional outbox phù hợp vì business update và event record cùng commit trong database. Relay có thể tiếp tục sau restart.

### Cần đồng bộ nhiều bảng hoặc xây pipeline dữ liệu ở mức row change?

Raw CDC phù hợp nếu consumer hiểu schema và có logic dựng projection.

### Cần domain event đáng tin cậy qua streaming platform?

Outbox + CDC thường là lựa chọn tốt: service ghi domain event vào outbox, connector phát event vào broker, consumer xây Elasticsearch projection.

### Elasticsearch có phải nguồn dữ liệu chính?

Nếu không có một database nguồn khác cần đồng bộ, có thể ghi trực tiếp vào Elasticsearch. Khi đó bài toán dual write không tồn tại theo cùng nghĩa; cần tập trung vào durability, replication, backup, versioning và recovery của Elasticsearch.

## 26. Một kiến trúc tham khảo với Spring Boot, outbox và Elasticsearch

~~~mermaid
flowchart TD
    A["REST / Command"] --> B["Spring Application Service"]
    B --> C["@Transactional"]
    C --> D["JPA ProductRepository"]
    C --> E["JPA OutboxRepository"]
    E --> F["Outbox CDC / Debezium"]
    F --> G["Kafka: product-events"]
    G --> H["Spring Kafka Consumer"]
    H --> I["Projection Mapper"]
    I --> J["ElasticsearchOperations"]
    J --> K["products-v2 index"]
    K --> L["products alias"]
    L --> M["Search API"]
~~~

Vai trò từng phần:

- Application service điều phối nghiệp vụ.
- JPA transaction ghi dữ liệu và outbox event.
- CDC connector đọc outbox insert.
- Kafka giữ event và phân phối tới consumer.
- Consumer kiểm tra version, map event thành document.
- Spring Data Elasticsearch ghi projection.
- Search API chỉ đọc alias/index phù hợp.

Kiến trúc này tách luồng ghi nghiệp vụ khỏi luồng cập nhật search. Khi Elasticsearch tạm thời không khả dụng, event có thể chờ trong broker và được consumer xử lý lại sau khi cluster phục hồi, trong giới hạn retention và chính sách retry.

## 27. Những lỗi thường gặp

### Nghĩ @Transactional bao trùm cả database và Elasticsearch

Transaction JPA không tự rollback thao tác Elasticsearch. Hai hệ thống cần cơ chế phối hợp riêng.

### Ghi database thành công rồi bỏ qua lỗi Elasticsearch

Projection có thể lệch mãi nếu không retry, lưu trạng thái pending hoặc reconciliation.

### Publish event trước khi database commit

Consumer có thể đọc event và truy vấn database khi transaction nguồn chưa commit hoặc sau đó rollback. Ghi outbox trong cùng transaction rồi phát sau commit.

### Đánh dấu outbox published trước khi gửi

Nếu process dừng trước publish, event bị mất. Ưu tiên publish rồi mark, chấp nhận duplicate và làm consumer idempotent.

### Coi CDC là domain event tự động

Raw CDC phát row changes. Muốn domain event có ngữ nghĩa, dùng outbox hoặc transformation có chủ đích.

### Acknowledge message trước khi ghi Elasticsearch

Process có thể dừng sau ack và trước ES write, làm mất projection update. Ack sau khi xử lý thành công theo chính sách.

### Dùng document ID ngẫu nhiên trong consumer

Một event giao lại có thể tạo document mới. Dùng ID ổn định theo aggregate hoặc event tùy loại projection.

### Event cũ ghi đè projection mới

Dùng aggregate version, ordering theo key hoặc version guard trong update/index.

### Coi bulk là transaction

Bulk có partial success. Kiểm tra từng item và retry chọn lọc.

### Không xử lý delete

Projection giữ document đã bị xóa trong nguồn hoặc event cũ có thể tạo lại document. Thiết kế tombstone/version hoặc delete semantics.

### Không có snapshot ban đầu cho CDC

Connector chỉ đọc log mới có thể không tạo dữ liệu lịch sử trong Elasticsearch. Thiết kế snapshot và chuyển tiếp sang streaming.

### Không có reconciliation

Outbox/CDC vẫn có thể gặp lỗi consumer, schema hoặc thao tác quản trị. Cần khả năng đối chiếu và rebuild.

## 28. Quy trình triển khai đồng bộ

Khi thiết kế luồng đồng bộ database và Elasticsearch:

1. Xác định nguồn dữ liệu chính và vai trò của Elasticsearch.
2. Xác định yêu cầu nhất quán: đồng bộ ngay, eventual consistency hay snapshot.
3. Nếu dùng dual write, ghi nhận rõ partial success và có retry/reconciliation.
4. Nếu cần phát event tin cậy, tạo outbox table trong cùng database transaction.
5. Định nghĩa event ID, aggregate ID, aggregate version, event type và schema version.
6. Chọn relay polling hoặc CDC connector.
7. Nếu dùng raw CDC, thiết kế logic chuyển row changes thành document projection.
8. Chọn topic/partition key theo aggregate để giữ thứ tự trong phạm vi cần thiết.
9. Xây consumer idempotent và chỉ acknowledge sau khi ghi Elasticsearch thành công.
10. Dùng document ID ổn định và version guard để chống duplicate/out-of-order event.
11. Xử lý delete, mapping error, bulk partial failure, retry và DLQ.
12. Theo dõi outbox backlog, CDC lag, consumer lag và projection latency.
13. Xây reconciliation và quy trình rebuild index.
14. Kiểm thử process crash ở từng ranh giới: trước commit, sau commit, sau publish, sau ES write và trước ack.
15. Kiểm thử replay, duplicate event, event cũ và schema version cũ.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Reference Documentation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html)
- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [Debezium — Architecture](https://debezium.io/documentation/reference/stable/architecture.html)
- [Debezium — PostgreSQL connector](https://debezium.io/documentation/reference/stable/connectors/postgresql.html)
- [Debezium — MySQL connector](https://debezium.io/documentation/reference/stable/connectors/mysql.html)
- [Kafka — Delivery semantics](https://kafka.apache.org/documentation/#semantics)
- [Elasticsearch — Index API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html)
- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)

## Kết luận

Ghi kép trực tiếp đơn giản nhưng không có atomic commit giữa database và Elasticsearch. Transactional outbox ghi business data và event trong cùng transaction database, sau đó relay hoặc CDC chuyển event ra ngoài. Raw CDC đọc transaction log và phù hợp với pipeline row-level, còn outbox CDC giữ được ngữ nghĩa domain event do ứng dụng định nghĩa. Với Spring Data Elasticsearch, consumer chuyển event thành projection và ghi bằng `ElasticsearchOperations`; cần ID ổn định, version guard, xử lý duplicate, ack sau khi ghi thành công, retry/DLQ và reconciliation. Chọn kiến trúc dựa trên yêu cầu nhất quán, khả năng phục hồi và mức độ phức tạp mà hệ thống có thể vận hành.

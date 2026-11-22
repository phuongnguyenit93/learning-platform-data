# Vì sao `@Transactional` không tạo giao dịch chung giữa JPA và Elasticsearch

Một method Spring có thể vừa lưu dữ liệu bằng Spring Data JPA vừa ghi document bằng Spring Data Elasticsearch. Dù cả hai lời gọi nằm trong cùng một method có `@Transactional`, chúng không tự động trở thành một giao dịch nguyên tử.

Nguyên nhân nằm ở ranh giới của transaction manager. `@Transactional` yêu cầu transaction manager được cấu hình cho method quản lý tài nguyên của nó. `JpaTransactionManager` quản lý transaction JPA và có thể phối hợp với JDBC connection thuộc cùng `DataSource`; nó không tự đưa request HTTP của Elasticsearch vào transaction đó. Elasticsearch client gửi request độc lập tới cluster, và Elasticsearch không tham gia XA transaction với cơ sở dữ liệu quan hệ.

Vì vậy, nếu một thao tác cần cập nhật cả database và Elasticsearch, ứng dụng phải thiết kế cách xử lý trạng thái một bên thành công, bên kia thất bại. Với hệ thống coi database là nguồn dữ liệu chính, transactional outbox thường là lựa chọn phù hợp: lưu thay đổi nghiệp vụ và sự kiện cần đồng bộ trong cùng transaction JPA, sau đó một tiến trình riêng chuyển sự kiện sang Elasticsearch theo cơ chế retry có thể phục hồi.

## 1. `@Transactional` thực sự quản lý điều gì?

Trong Spring, `@Transactional` là metadata để transaction infrastructure mở, commit hoặc rollback transaction thông qua một transaction manager.

Với ứng dụng imperative, các transaction manager thường gặp:

- `JpaTransactionManager`: quản lý transaction của JPA `EntityManagerFactory`, và có thể phối hợp với JDBC access trên cùng `DataSource`.
- `DataSourceTransactionManager`: quản lý JDBC transaction cho một `DataSource`.
- `JtaTransactionManager`: tích hợp với một transaction coordinator JTA nếu các resource tham gia hỗ trợ giao thức đó.
- Các transaction manager chuyên biệt khác: quản lý resource và semantics của chính chúng.

Khi method được gọi qua Spring proxy, transaction interceptor xác định transaction manager cần dùng, bắt đầu hoặc tham gia transaction, gọi method, rồi commit hoặc rollback theo kết quả và rollback rules.

Ví dụ:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional
    public Product create(CreateProductCommand command) {
        Product product = new Product(
                command.name(),
                command.price()
        );

        return productRepository.save(product);
    }
}
~~~

Trong ví dụ này, nếu repository dùng JPA và method được gọi qua Spring proxy, transaction manager JPA quản lý việc ghi database. Nếu method ném runtime exception trước khi commit, transaction có thể rollback theo mặc định.

Điều quan trọng là transaction manager không tự phát hiện mọi resource được sử dụng trong method rồi đưa chúng vào một transaction chung. Nó chỉ quản lý resource mà nó được thiết kế và cấu hình để quản lý.

## 2. Vì sao JPA và Elasticsearch là hai resource độc lập?

JPA thường giao tiếp với database thông qua JDBC connection và persistence context của `EntityManager`. Database hỗ trợ transaction ACID cho các thao tác trong transaction đó.

Spring Data Elasticsearch giao tiếp với Elasticsearch qua Elasticsearch Java API Client và HTTP transport. Một request index/update được gửi tới cluster và được Elasticsearch xử lý theo semantics của API tương ứng.

Sơ đồ hai đường ghi:

~~~text
                  Spring service
                       |
                 @Transactional
                       |
             JpaTransactionManager
                       |
                 EntityManager
                       |
                    JDBC
                       |
                Relational DB

                  Spring service
                       |
             ElasticsearchOperations
                       |
             Elasticsearch Java Client
                       |
                      HTTP
                       |
               Elasticsearch cluster
~~~

Hai nhánh không tự chia sẻ transaction context. `JpaTransactionManager` không thể rollback một request Elasticsearch đã được cluster chấp nhận. Ngược lại, Elasticsearch cũng không thể rollback commit của database.

Ngay cả khi cả hai client đều là Spring bean, được inject trong cùng service và được gọi trong cùng method, điều đó không làm chúng trở thành cùng một transactional resource.

### 2.1. Cùng một method không có nghĩa là cùng một transaction

Ví dụ:

~~~java
@Transactional("jpaTransactionManager")
public Product create(CreateProductCommand command) {
    Product product = productRepository.save(
            new Product(command.name(), command.price())
    );

    elasticsearchOperations.save(
            ProductDocument.from(product)
    );

    return product;
}
~~~

Method có một ranh giới transaction được chọn bởi `jpaTransactionManager`. Lời gọi `productRepository.save(...)` tham gia transaction JPA. Lời gọi `elasticsearchOperations.save(...)` gửi một request riêng tới Elasticsearch.

Nếu cả hai lời gọi trả về bình thường, database vẫn chỉ commit khi transaction interceptor kết thúc method và thực hiện commit. Elasticsearch có thể đã xử lý xong request trước thời điểm đó.

### 2.2. Chỉ định transaction manager không mở rộng phạm vi resource

Nếu ứng dụng có nhiều transaction manager, có thể chỉ định rõ:

~~~java
@Transactional(transactionManager = "jpaTransactionManager")
public void updateProduct(...) {
    // Các thao tác JPA tham gia transaction manager này.
}
~~~

Tên bean `jpaTransactionManager` là ví dụ; dùng đúng tên bean trong ứng dụng.

Việc chỉ định manager làm rõ transaction nào được áp dụng cho method. Nó không đăng ký Elasticsearch client như một participant của transaction JPA.

Nếu ứng dụng cấu hình nhiều transaction manager và không chỉ định rõ, Spring cần chọn manager theo cấu hình/qualifier hoặc có thể báo lỗi khi không xác định được. Dù chọn manager nào, lời gọi tới Elasticsearch vẫn cần cơ chế đồng bộ riêng.

## 3. Hai thứ tự lỗi khi ghi cả database và Elasticsearch

Một thao tác dual-write thường có hai bước: ghi database và ghi Elasticsearch. Dù thứ tự nào, vẫn tồn tại cửa sổ mà một bên đã thành công còn bên kia chưa hoàn tất.

### 3.1. Elasticsearch ghi thành công, database commit thất bại

Giả sử method ghi database trước rồi Elasticsearch:

~~~text
1. Mở JPA transaction
2. JPA save Product (chưa commit)
3. Elasticsearch index ProductDocument -> thành công
4. JPA commit -> thất bại
5. JPA rollback
~~~

Kết quả:

| Resource | Trạng thái |
| --- | --- |
| Database | Không có thay đổi đã commit. |
| Elasticsearch | Document đã được ghi. |

Search có thể trả về sản phẩm không tồn tại trong database. Đây là dữ liệu mồ côi ở read model.

Lưu ý: JPA `save()` có thể chưa gửi SQL ngay. SQL có thể được flush ở cuối transaction. Gọi `EntityManager.flush()` chỉ đẩy SQL tới database trong transaction hiện tại; nó chưa commit và không làm Elasticsearch chờ transaction đó.

### 3.2. Database đã commit, Elasticsearch ghi thất bại

Một biến thể khác là ứng dụng commit database trước rồi gọi Elasticsearch, hoặc bắt lỗi Elasticsearch và không rollback transaction database:

~~~text
1. JPA transaction commit -> thành công
2. Gửi request index tới Elasticsearch
3. Elasticsearch timeout hoặc từ chối request
4. Database đã có dữ liệu, Elasticsearch chưa cập nhật
~~~

Kết quả:

| Resource | Trạng thái |
| --- | --- |
| Database | Dữ liệu nghiệp vụ đã commit. |
| Elasticsearch | Projection/search document chưa được cập nhật. |

Nếu service trả lỗi cho caller, caller có thể thử lại toàn bộ request. Nếu không có idempotency, thao tác nghiệp vụ có thể bị thực hiện hai lần.

### 3.3. Bảng tổng hợp

| Thời điểm lỗi | Database | Elasticsearch | Vấn đề |
| --- | --- | --- | --- |
| DB commit thất bại sau khi ES đã ghi | Rollback | Đã ghi | Document mồ côi trong ES. |
| ES thất bại sau khi DB commit | Đã commit | Chưa ghi | Search index bị trễ hoặc thiếu document. |
| ES request timeout, kết quả không rõ | Có thể commit | Có thể đã ghi hoặc chưa | Retry có nguy cơ lặp thao tác. |
| Bulk có một số item lỗi | Có thể commit | Một phần document đã ghi | Cần xử lý theo từng item. |
| Process chết giữa hai bước | Một bên có thể đã hoàn tất | Trạng thái không đồng bộ | Không có transaction chung để tự phục hồi. |

Đây không phải lỗi riêng của annotation. Nó là hệ quả của việc ghi vào hai hệ thống có transaction boundary khác nhau.

## 4. Vì sao rollback JPA không xóa được document Elasticsearch?

Rollback chỉ đảo ngược các thay đổi nằm trong transaction mà transaction manager quản lý.

Ví dụ:

~~~java
@Transactional("jpaTransactionManager")
public void createProduct() {
    productRepository.save(new Product("Keyboard", 49.99));

    elasticsearchOperations.save(
            new ProductDocument("P-100", "Keyboard", 49.99)
    );

    throw new IllegalStateException("Simulated failure");
}
~~~

Runtime exception khiến JPA transaction rollback theo mặc định nếu nó thoát khỏi method và transaction interceptor xử lý. Nhưng request `save()` đã gửi tới Elasticsearch không nằm trong transaction JPA. Document không tự bị xóa.

Nếu muốn bù lại thao tác Elasticsearch, ứng dụng phải tự gửi một request khác, ví dụ delete document. Đó là một compensating action, không phải rollback của transaction ban đầu. Compensating action cũng có thể thất bại hoặc chạy sau khi một consumer khác đã đọc document.

### 4.1. Rollback rules cũng cần được hiểu đúng

Theo mặc định của Spring, runtime exception và error thường kích hoạt rollback; checked exception không tự động làm transaction rollback nếu không khai báo rollback rule phù hợp.

Ví dụ:

~~~java
@Transactional(
        transactionManager = "jpaTransactionManager",
        rollbackFor = IOException.class
)
public void update(...) throws IOException {
    // ...
}
~~~

`rollbackFor` chỉ thay đổi quyết định commit/rollback của transaction JPA. Nó vẫn không làm Elasticsearch tham gia transaction.

Nếu exception từ Elasticsearch bị bắt và không được ném lại, JPA method có thể kết thúc bình thường và transaction commit. Vì vậy, catch block cần thể hiện rõ chính sách nghiệp vụ, không được vô tình biến lỗi đồng bộ thành thành công giả.

## 5. Elasticsearch không cung cấp transaction ACID chung với database

Elasticsearch hỗ trợ các thao tác ghi document và một số semantics atomic ở phạm vi document. Ví dụ một lần update document được áp dụng như một thao tác ghi trên document đó; optimistic concurrency có thể ngăn ghi dựa trên phiên bản cũ.

Nhưng những khả năng đó không tương đương một transaction ACID bao trùm:

- Một document Elasticsearch.
- Nhiều document Elasticsearch.
- Một database quan hệ.
- Một message broker.
- Một dịch vụ HTTP khác.

Bulk API cũng không phải transaction. Mỗi item có kết quả riêng; một số item có thể thành công trong khi item khác thất bại.

Elasticsearch không tham gia XA transaction như một XA-capable relational database resource. Không thể chỉ bật JTA rồi giả định request HTTP tới Elasticsearch được enlist, prepare và rollback cùng database.

### 5.1. Refresh không phải commit chung

Refresh làm document đã được index trở nên visible cho search. Nó không:

- Chờ transaction JPA commit.
- Kiểm tra database đã commit hay chưa.
- Rollback document khi database rollback.
- Tạo transaction giữa hai hệ thống.

`refresh=wait_for` hoặc `refresh=true` chỉ ảnh hưởng thời điểm search nhìn thấy thay đổi Elasticsearch. Nó không sửa được vấn đề dual-write.

## 6. Vì sao `@TransactionalEventListener(AFTER_COMMIT)` vẫn chưa đủ?

Một cách thường dùng là phát application event sau khi database commit:

~~~java
@Transactional
public Product create(CreateProductCommand command) {
    Product product = productRepository.save(
            new Product(command.name(), command.price())
    );

    eventPublisher.publishEvent(
            new ProductCreatedEvent(product.getId())
    );

    return product;
}
~~~

Listener:

~~~java
@Component
public class ProductCreatedListener {

    private final ElasticsearchOperations operations;

    public ProductCreatedListener(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onProductCreated(ProductCreatedEvent event) {
        // Đọc product từ database và index document.
    }
}
~~~

`AFTER_COMMIT` bảo đảm listener được gọi sau khi transaction đã commit thành công. Điều này tránh index dữ liệu trước khi database commit.

Tuy nhiên, event trong application context thường chỉ tồn tại trong bộ nhớ process. Có một khoảng trống:

~~~text
1. Database commit thành công
2. Process bị dừng đột ngột
3. Listener chưa chạy hoặc chưa gửi request Elasticsearch
4. Không còn event bền vững để phát lại
~~~

Database đã commit nhưng không có document Elasticsearch và cũng không có message durable để retry.

Nếu listener chạy bất đồng bộ, lỗi trong listener càng không thể rollback transaction database đã commit. `@Async` thay đổi thread thực thi, không biến event thành dữ liệu durable.

### 6.1. Khi nào AFTER_COMMIT hữu ích?

`@TransactionalEventListener(AFTER_COMMIT)` vẫn hữu ích để:

- Kích hoạt một tác vụ sau khi dữ liệu đã commit.
- Gửi tín hiệu đánh thức outbox poller.
- Cập nhật cache best-effort.
- Chạy công việc không cần bảo đảm giao nhận bền vững.

Nếu việc mất event là không chấp nhận được, đừng dùng in-memory event làm cơ chế duy nhất. Hãy lưu sự kiện trong cùng database transaction, rồi dùng listener như một tín hiệu tối ưu để giảm độ trễ xử lý.

## 7. Transactional outbox giải quyết khoảng trống dual-write như thế nào?

Transactional outbox lưu thay đổi nghiệp vụ và một bản ghi mô tả việc cần đồng bộ trong cùng một transaction database.

Khi transaction commit:

- Bản ghi nghiệp vụ đã tồn tại.
- Bản ghi outbox cũng đã tồn tại.
- Cả hai cùng commit hoặc cùng rollback vì chúng thuộc cùng database transaction.

Một tiến trình relay đọc outbox sau đó gửi event tới Elasticsearch hoặc message broker.

~~~text
                 JPA service
                      |
              JPA transaction
                      |
            +---------+---------+
            |                   |
            v                   v
       Product table       Outbox table
            |                   |
            +------ COMMIT -----+
                                |
                                v
                         Outbox relay
                                |
                     retry / delivery tracking
                                |
                                v
                        Elasticsearch index
~~~

Nếu process chết sau khi commit nhưng trước khi relay chạy, bản ghi outbox vẫn còn trong database. Relay có thể tiếp tục sau khi service khởi động lại.

Outbox không tạo transaction chung giữa DB và Elasticsearch. Nó bảo đảm ý định đồng bộ được ghi bền vững cùng thay đổi database, sau đó cho phép delivery theo kiểu eventual consistency.

## 8. Thiết kế bảng outbox

Một bảng outbox thường lưu:

| Cột | Ý nghĩa |
| --- | --- |
| id | Event ID duy nhất, dùng để deduplicate và audit. |
| aggregate_type | Loại aggregate, ví dụ Product. |
| aggregate_id | ID của entity nghiệp vụ. |
| aggregate_version | Version tăng dần của aggregate. |
| event_type | Loại event, ví dụ ProductCreated hoặc ProductUpdated. |
| payload | Nội dung cần chuyển sang projection. |
| created_at | Thời điểm tạo event. |
| published_at | Thời điểm relay xác nhận đã gửi thành công. |
| attempts | Số lần thử. |
| next_attempt_at | Thời điểm được phép retry tiếp. |
| last_error | Thông tin lỗi đã được lọc dữ liệu nhạy cảm. |
| lock_owner / locked_until | Thông tin lease để nhiều relay không xử lý trùng đồng thời. |

Schema SQL minh họa:

~~~sql
CREATE TABLE outbox_event (
    id                UUID PRIMARY KEY,
    aggregate_type    VARCHAR(100) NOT NULL,
    aggregate_id      VARCHAR(200) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type        VARCHAR(150) NOT NULL,
    payload           TEXT NOT NULL,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at      TIMESTAMP WITH TIME ZONE NULL,
    attempts          INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMP WITH TIME ZONE NULL,
    last_error        TEXT NULL,
    lock_owner        VARCHAR(100) NULL,
    locked_until      TIMESTAMP WITH TIME ZONE NULL
);
~~~

Kiểu UUID, timestamp và cú pháp SQL cần điều chỉnh theo database đang dùng. Có thể thêm index cho các cột dùng để tìm event pending, ví dụ `published_at`, `next_attempt_at` và `created_at`.

Không lưu một payload tùy ý chứa secret hoặc dữ liệu không cần thiết. Outbox nên chứa snapshot/event data đủ để cập nhật projection, có version schema và quy tắc tương thích.

## 9. Ghi domain data và outbox trong cùng JPA transaction

Ví dụ entity đơn giản:

~~~java
@Entity
@Table(name = "outbox_event")
public class OutboxEvent {

    @Id
    private UUID id;

    private String aggregateType;
    private String aggregateId;
    private long aggregateVersion;
    private String eventType;

    @Lob
    private String payload;

    private Instant createdAt;
    private Instant publishedAt;

    protected OutboxEvent() {
    }

    public static OutboxEvent pending(
            String aggregateId,
            long version,
            String eventType,
            String payload) {

        OutboxEvent event = new OutboxEvent();
        event.id = UUID.randomUUID();
        event.aggregateType = "Product";
        event.aggregateId = aggregateId;
        event.aggregateVersion = version;
        event.eventType = eventType;
        event.payload = payload;
        event.createdAt = Instant.now();
        return event;
    }
}
~~~

Service:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;
    private final OutboxEventRepository outboxRepository;
    private final ObjectMapper objectMapper;

    public ProductService(
            ProductRepository productRepository,
            OutboxEventRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.productRepository = productRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional(transactionManager = "jpaTransactionManager")
    public Product create(CreateProductCommand command) {
        Product product = productRepository.save(
                new Product(command.name(), command.price())
        );

        String payload = serialize(
                ProductProjection.from(product)
        );

        outboxRepository.save(
                OutboxEvent.pending(
                        product.getId(),
                        product.getVersion(),
                        "ProductProjectionChanged",
                        payload
                )
        );

        return product;
    }

    private String serialize(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize outbox event", ex
            );
        }
    }
}
~~~

Tên bean transaction manager và kiểu version là ví dụ; entity/version strategy cần được định nghĩa trong ứng dụng. Điều quan trọng là `ProductRepository` và `OutboxEventRepository` dùng cùng database và cùng transaction manager.

Nếu serialize payload thất bại trước commit, runtime exception có thể làm transaction rollback. Nếu commit thành công, cả product và outbox row đều bền vững.

Không gọi Elasticsearch trực tiếp trong method này. Method chỉ ghi hai loại dữ liệu thuộc cùng database transaction.

### 9.1. Payload snapshot hay event nhỏ?

Có hai cách thiết kế payload:

- **Snapshot/projection payload:** chứa dữ liệu đủ để relay ghi thẳng document Elasticsearch.
- **Domain event nhỏ:** chứa aggregate ID và event metadata; consumer đọc trạng thái mới nhất từ database.

Snapshot giúp relay không cần query database lần nữa và giữ được trạng thái tại thời điểm event được tạo. Event nhỏ giảm kích thước outbox nhưng có thể yêu cầu đọc lại entity và cần xử lý khi entity đã thay đổi thêm.

Nếu relay đọc trạng thái mới nhất từ database, event cũ có thể tạo projection của version mới hơn. Điều này có thể chấp nhận nếu mục tiêu là eventual current-state projection, nhưng không phù hợp nếu cần tái tạo chính xác từng event lịch sử.

## 10. Outbox relay: gửi event và đánh dấu đã xử lý

Relay có thể chạy bằng scheduler, worker riêng hoặc CDC platform. Với polling relay, luồng khái quát:

1. Lấy một batch event chưa publish và đã đến `next_attempt_at`.
2. Claim event bằng lease/locking để tránh nhiều worker xử lý cùng lúc.
3. Commit trạng thái claim ngắn hạn.
4. Gửi payload tới Elasticsearch.
5. Nếu thành công, đánh dấu `published_at`.
6. Nếu lỗi tạm thời, tăng attempts và lên lịch retry.
7. Nếu lỗi không thể tự phục hồi, đưa vào trạng thái cần can thiệp hoặc dead-letter workflow.

Không nên giữ một database transaction/row lock mở trong toàn bộ thời gian gọi mạng tới Elasticsearch. Một request chậm có thể giữ lock lâu và làm tắc relay hoặc các transaction nghiệp vụ.

Pseudocode:

~~~java
public void processBatch() {
    List<ClaimedOutboxEvent> events = claimPendingBatch();

    for (ClaimedOutboxEvent event : events) {
        try {
            elasticsearchProjectionWriter.apply(event);
            markPublished(event.id());
        } catch (TransientElasticsearchException ex) {
            scheduleRetry(event.id(), ex);
        } catch (PermanentProjectionException ex) {
            markForManualReview(event.id(), ex);
        }
    }
}
~~~

Các method claim, markPublished và scheduleRetry cần transaction riêng trên database. `claimPendingBatch()` cần cơ chế locking hoặc lease phù hợp với database để nhiều relay instance không giành cùng event.

### 10.1. Crash sau khi Elasticsearch đã ghi

Có một cửa sổ khác:

~~~text
1. Relay gửi event tới Elasticsearch
2. Elasticsearch ghi thành công
3. Relay process chết trước khi cập nhật published_at
4. Relay khởi động lại và gửi lại event
~~~

Đây là hành vi at-least-once delivery. Outbox bảo đảm event không bị mất âm thầm, nhưng có thể giao lặp. Consumer phải idempotent hoặc có cơ chế deduplication/version guard.

Không có cách đánh dấu DB row và ghi Elasticsearch thành một thao tác atomic chỉ bằng cách đặt hai lời gọi cạnh nhau.

## 11. Idempotency khi ghi projection vào Elasticsearch

Một consumer idempotent có thể xử lý lại cùng event mà không tạo hiệu ứng nghiệp vụ mới.

Với projection phản ánh trạng thái hiện tại của entity, cách phổ biến là dùng document ID ổn định:

~~~http
PUT /products/_doc/P-100
Content-Type: application/json

{
  "id": "P-100",
  "name": "Keyboard",
  "price": 49.99,
  "sourceVersion": 12
}
~~~

Nếu cùng một snapshot được gửi lại, thao tác index theo ID xác định sẽ thay thế cùng document bằng cùng nội dung. Điều này thường phù hợp cho projection dạng current-state.

Tuy nhiên, ID xác định không giải quyết sự kiện đến sai thứ tự. Ví dụ version 13 đã được index rồi, sau đó event version 12 đến muộn và ghi đè dữ liệu mới hơn.

### 11.1. Giữ thứ tự bằng aggregate version

Tăng aggregate version trong cùng transaction database và đưa version vào outbox payload.

Khi ghi Elasticsearch, có thể dùng external versioning:

~~~http
PUT /products/_doc/P-100?version=13&version_type=external
Content-Type: application/json

{
  "id": "P-100",
  "name": "Keyboard",
  "price": 52.00,
  "sourceVersion": 13
}
~~~

Với `version_type=external`, Elasticsearch chỉ chấp nhận version mới lớn hơn version hiện có. Event cũ đến sau sẽ bị từ chối bằng version conflict, nhờ đó không ghi đè projection mới hơn.

Consumer cần phân biệt conflict do event cũ/trùng với conflict do một writer khác. Có thể đọc version hiện tại hoặc dùng metadata đã biết để quyết định event đã được áp dụng hay cần điều tra.

Không dùng external version nếu version nguồn không đơn điệu hoặc nhiều aggregate cùng ghi vào một document mà không có quy tắc tổng hợp.

### 11.2. Event ID và deduplication

Ngoài aggregate version, lưu event ID duy nhất để audit và hỗ trợ deduplicate. Có thể có bảng processed-event ở consumer nếu nghiệp vụ cần xác định event đã xử lý.

Với projection current-state, deterministic document ID cùng external version thường đủ cho phần lớn trường hợp. Với thao tác có side effect hoặc tăng/giảm giá trị, cần idempotency key hoặc event processing ledger.

## 12. CDC và Debezium

Thay vì polling outbox table, có thể dùng Change Data Capture (CDC) để đọc transaction log của database.

Một mô hình phổ biến:

~~~text
JPA transaction
      |
      v
Domain table + Outbox table
      |
      v
Database transaction log
      |
      v
CDC connector (ví dụ Debezium)
      |
      v
Message broker
      |
      v
Projection consumer
      |
      v
Elasticsearch
~~~

CDC connector đọc các row outbox đã commit từ transaction log và phát chúng tới broker. Consumer cập nhật Elasticsearch.

Ưu điểm:

- Không cần polling liên tục bảng outbox.
- Có thể tận dụng log position và connector offset.
- Tách relay khỏi ứng dụng nghiệp vụ.
- Dễ mở rộng nhiều consumer/projection.

Đổi lại, vận hành CDC và broker phức tạp hơn: connector health, schema registry, offset, topic retention, partition ordering, dead-letter và replay đều cần quản lý.

CDC vẫn thường là at-least-once ở các ranh giới giao nhận. Consumer Elasticsearch vẫn cần idempotency và version ordering. CDC không tạo transaction XA giữa database và Elasticsearch.

## 13. Saga và compensating action

Transactional outbox phù hợp với đồng bộ một chiều từ database sang search projection. Nếu một workflow cần nhiều bước nghiệp vụ trên nhiều hệ thống, có thể dùng Saga.

Saga biểu diễn quy trình thành các bước có trạng thái và hành động bù:

~~~text
Create order in DB
       |
       v
Reserve inventory
       |
       v
Update search/projection
       |
       v
Complete workflow

Nếu bước sau thất bại:
       |
       v
Run compensating action
       |
       v
Restore business state where possible
~~~

Compensating action là một thao tác nghiệp vụ mới nhằm đưa hệ thống về trạng thái chấp nhận được. Nó không xóa lịch sử đã xảy ra và không bảo đảm thành công tuyệt đối.

Ví dụ, nếu một document đã được index nhưng order bị hủy, workflow có thể phát event cập nhật trạng thái hoặc xóa projection. Nếu consumer tạm thời lỗi, hành động bù cũng cần retry.

Không nên dùng Saga chỉ để đồng bộ một bản search document đơn giản nếu outbox là đủ. Saga hữu ích khi có nhiều bước và quy tắc bù rõ ràng.

## 14. Vì sao không nên dựa vào ChainedTransactionManager hoặc JTA để giải quyết?

Một số hệ thống cũ từng dùng nhiều transaction manager nối tiếp hoặc cấu hình transaction coordinator để cố phối hợp nhiều resource.

Cần phân biệt:

- Một transaction manager có thể quản lý nhiều resource nếu chúng được hỗ trợ và enlist đúng giao thức.
- Gọi tuần tự hai transaction manager không tự tạo atomic commit.
- Một transaction coordinator JTA chỉ có thể điều phối resource tham gia giao thức tương ứng.
- Elasticsearch HTTP client không trở thành XA resource chỉ vì được gọi bên trong method có `@Transactional`.

Cơ chế chained commit thường có thể gặp tình huống manager thứ nhất đã commit nhưng manager tiếp theo thất bại. Khi đó hệ thống vẫn ở trạng thái partial commit và cần bù/khôi phục.

Không coi việc bọc nhiều manager trong một annotation là bằng chứng có transaction ACID chung. Với DB + Elasticsearch, hãy thiết kế theo outbox/eventual consistency hoặc một workflow có compensation.

## 15. `@Transactional(propagation = ...)` không giải quyết cross-resource atomicity

Propagation quyết định cách một method tham gia transaction hiện tại hoặc tạo transaction mới trong phạm vi transaction manager được chọn.

Ví dụ:

- `REQUIRED`: tham gia transaction hiện tại hoặc tạo mới.
- `REQUIRES_NEW`: tạm treo transaction hiện tại và mở transaction mới.
- `NESTED`: transaction lồng nhau nếu manager/resource hỗ trợ savepoint.
- `NOT_SUPPORTED`: chạy không có transaction trong phạm vi manager tương ứng.

Các propagation mode không tự thêm Elasticsearch vào transaction JPA.

Ví dụ:

~~~java
@Transactional(
        transactionManager = "jpaTransactionManager",
        propagation = Propagation.REQUIRES_NEW
)
public void saveAuditRecord(...) {
    // Một transaction database mới.
}
~~~

`REQUIRES_NEW` có thể hữu ích để ghi audit vào database trong một transaction riêng, nhưng không làm request Elasticsearch trở thành một phần của transaction đó.

## 16. Xử lý khi Elasticsearch chỉ là read model

Một kiến trúc thường gặp là database quan hệ giữ dữ liệu chuẩn (source of truth), còn Elasticsearch là read model phục vụ tìm kiếm, lọc và aggregation.

Trong kiến trúc này:

- JPA transaction bảo đảm thay đổi nghiệp vụ và outbox event được commit cùng nhau.
- Outbox relay/consumer cập nhật Elasticsearch sau commit.
- Search có thể trễ hơn database một khoảng thời gian.
- Nếu Elasticsearch tạm ngừng, database vẫn có thể nhận thay đổi và outbox tích lũy event.
- Khi Elasticsearch phục hồi, consumer xử lý event tồn đọng để hội tụ projection.

Đây là eventual consistency. Ứng dụng cần định nghĩa độ trễ chấp nhận được và hành vi khi người dùng vừa cập nhật dữ liệu rồi lập tức search.

Ví dụ API có thể trả entity từ database ngay sau khi commit, đồng thời cung cấp trạng thái đồng bộ projection nếu UI cần biết search index đã bắt kịp hay chưa.

Không dùng kết quả Elasticsearch làm bằng chứng duy nhất rằng database transaction đã commit.

## 17. Read-after-write và đồng bộ trải nghiệm người dùng

Nếu người dùng tạo sản phẩm rồi ngay lập tức tìm kiếm sản phẩm đó, outbox có thể khiến search index chưa cập nhật tại thời điểm query.

Một số cách xử lý:

1. Trả dữ liệu vừa tạo từ database response thay vì tìm lại qua Elasticsearch.
2. Hiển thị trạng thái “đang đồng bộ tìm kiếm” nếu nghiệp vụ cần.
3. Sau khi relay xác nhận event đã index, cho phép query search.
4. Với một số luồng quan trọng, chờ consumer acknowledgment có timeout, nhưng không giữ JPA transaction mở trong lúc chờ.
5. Dùng một endpoint đọc trực tiếp từ database cho thao tác cần read-your-writes.

Refresh `wait_for` chỉ bảo đảm document đã ghi vào Elasticsearch được search-visible sau refresh. Nó không bảo đảm event đã được tạo, relay đã chạy hoặc database và Elasticsearch commit cùng nhau.

## 18. Retry, dead-letter và reconciliation

Một outbox workflow cần có chính sách lỗi rõ ràng.

### 18.1. Phân loại lỗi

| Lỗi | Cách xử lý |
| --- | --- |
| Timeout hoặc network interruption | Retry với backoff; kết quả lần trước có thể chưa rõ nên cần idempotency. |
| Elasticsearch 429 | Backoff, giảm concurrency và retry. |
| Mapping/parsing error | Không retry nguyên trạng; sửa payload hoặc mapping. |
| 401/403 | Sửa credential/privilege; đưa event vào trạng thái lỗi có thể can thiệp. |
| Version conflict do event cũ | Đánh dấu stale/already superseded nếu đã xác minh version hiện tại mới hơn. |
| Index không tồn tại | Kiểm tra provisioning/alias; retry sau khi điều kiện được khắc phục. |

### 18.2. Dead-letter hoặc manual review

Sau số lần retry giới hạn, event lỗi vĩnh viễn cần chuyển sang trạng thái dễ quan sát:

- Lưu error type và thông tin chẩn đoán.
- Giữ payload hoặc reference an toàn để replay.
- Cảnh báo theo tuổi event và số lần thất bại.
- Cung cấp công cụ replay có kiểm soát.
- Không xóa row chỉ vì đã vượt số lần retry.

### 18.3. Reconciliation

Outbox xử lý event chưa giao, nhưng hệ thống vẫn cần kiểm tra projection có lệch dữ liệu hay không. Một reconciliation job có thể so sánh:

- Số lượng entity theo partition hoặc thời gian.
- Aggregate version trong DB và projection.
- Các ID gần đây đã cập nhật.
- Document thiếu hoặc stale.
- Các outbox event bị treo quá lâu.

Reconciliation giúp phát hiện lỗi vận hành, bug consumer hoặc dữ liệu đã bị sửa ngoài luồng event.

## 19. Kiểm thử ranh giới transaction

Không chỉ kiểm thử trường hợp thành công. Cần mô phỏng các điểm process có thể thất bại.

### 19.1. Kiểm thử JPA rollback

1. Bắt đầu JPA transaction.
2. Ghi Product.
3. Buộc method ném runtime exception.
4. Xác nhận Product không được commit trong database.

Nếu cùng method đã ghi Elasticsearch trực tiếp, kiểm tra document có còn tồn tại không. Đây là cách chứng minh rollback JPA không đảo ngược request ES.

### 19.2. Kiểm thử outbox atomicity

1. Ghi Product và OutboxEvent trong cùng transaction.
2. Buộc transaction rollback.
3. Xác nhận cả hai row đều không tồn tại.
4. Chạy transaction thành công.
5. Xác nhận cả Product và OutboxEvent cùng tồn tại.

### 19.3. Kiểm thử relay crash

1. Tạo outbox event.
2. Relay gửi thành công tới Elasticsearch.
3. Mô phỏng process chết trước khi mark published.
4. Chạy relay lại.
5. Xác nhận event được giao lặp nhưng projection không bị nhân đôi hoặc lùi version.

### 19.4. Kiểm thử event đến sai thứ tự

1. Gửi event version 12.
2. Gửi event version 13.
3. Gửi lại event version 12.
4. Xác nhận projection vẫn ở version 13.

### 19.5. Kiểm thử lỗi Elasticsearch

- Tạm dừng cluster hoặc chặn network.
- Trả 429 để kiểm tra backoff.
- Gửi payload sai mapping để kiểm tra dead-letter.
- Khởi động lại relay và xác nhận event pending được xử lý.
- Xác nhận alert khi outbox backlog tăng.

## 20. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Nghĩ cùng method `@Transactional` nghĩa là DB và ES cùng commit | Một bên có thể thành công, bên kia thất bại. | Xác định transaction boundary của từng resource. |
| Ghi ES trước khi JPA commit | ES có thể chứa document không có trong DB. | Ghi outbox cùng DB transaction rồi xử lý sau commit. |
| Dùng AFTER_COMMIT listener làm durable queue | Process chết có thể làm mất event. | Lưu outbox row hoặc dùng CDC. |
| Bắt lỗi ES rồi trả thành công mà không lưu trạng thái | Projection có thể lệch mà không thể retry. | Lưu event bền vững và theo dõi trạng thái. |
| Retry toàn bộ thao tác nghiệp vụ | Có thể tạo duplicate hoặc thực hiện nghiệp vụ hai lần. | Tách command và projection event; dùng idempotency key. |
| Retry cùng event không có version guard | Event cũ có thể ghi đè projection mới. | Aggregate version/external versioning. |
| Giữ JPA transaction mở khi gọi ES chậm | Giữ connection/lock lâu, tăng contention. | Outbox relay gọi ES ngoài transaction domain. |
| Dùng `REQUIRES_NEW` nghĩ rằng đã có distributed transaction | Chỉ tạo transaction mới trong manager được chọn. | Dùng outbox hoặc Saga theo yêu cầu. |
| Coi Bulk API là transaction | Item có thể thành công/thất bại độc lập. | Xử lý từng item response. |
| Bật refresh ngay để sửa dual-write | Chỉ thay đổi search visibility, không tạo atomicity. | Tách freshness khỏi transaction consistency. |
| Xóa outbox event ngay sau khi gửi mà không có audit | Khó replay và điều tra lỗi. | Retention/archive theo chính sách. |

## 21. Quy trình chọn giải pháp

Khi một use case cần ghi cả JPA và Elasticsearch, hãy xác định:

1. Hệ thống nào là source of truth?
2. Elasticsearch là read model hay nơi lưu dữ liệu nghiệp vụ chính?
3. Có chấp nhận độ trễ eventual consistency không?
4. Điều gì xảy ra nếu DB commit nhưng Elasticsearch không cập nhật?
5. Điều gì xảy ra nếu Elasticsearch ghi xong nhưng DB rollback?
6. Có thể lưu event trong cùng DB transaction không?
7. Consumer có thể ghi idempotent theo document ID không?
8. Có cần aggregate version để ngăn event cũ ghi đè không?
9. Retry, dead-letter và reconciliation được vận hành thế nào?
10. Người dùng cần read-after-write ở mức nào?

Với phần lớn hệ thống dùng JPA làm nguồn dữ liệu chính và Elasticsearch phục vụ search, lựa chọn thực tế là:

- Ghi entity và outbox event trong cùng `JpaTransactionManager`.
- Commit database.
- Relay/CDC phát event theo at-least-once.
- Consumer index document bằng ID ổn định và version guard.
- Retry lỗi tạm thời, cách ly lỗi vĩnh viễn.
- Chạy reconciliation để phát hiện projection lệch.

Nếu nghiệp vụ đòi hỏi nhiều hệ thống cùng hoàn thành một quy trình, hãy mô hình hóa trạng thái workflow và compensating actions theo Saga. Không cố biến một method Java thành distributed transaction chỉ bằng annotation.

## 22. Tài liệu tham khảo

- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Data Elasticsearch — Elasticsearch Clients and Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)

`@Transactional` tạo ranh giới transaction cho resource do transaction manager được chọn quản lý. `JpaTransactionManager` bảo vệ database transaction, còn Elasticsearch client gửi request HTTP độc lập nên không được rollback cùng JPA. `@TransactionalEventListener(AFTER_COMMIT)` bảo đảm thứ tự sau commit nhưng không lưu event bền vững. Khi cần đồng bộ đáng tin cậy, hãy ghi outbox row cùng entity trong một transaction JPA, sau đó relay event theo at-least-once với idempotency, version ordering, retry và reconciliation.


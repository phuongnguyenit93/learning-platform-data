# Cache phía ứng dụng và chiến lược vô hiệu hóa sau commit

Cache phía ứng dụng giúp giảm số lần đọc MySQL, giảm độ trễ và bảo vệ database trước các đợt tăng tải. Tuy nhiên, cache tạo thêm một bản sao dữ liệu bên cạnh database. Khi một transaction cập nhật dữ liệu, cache phải được xử lý đúng thời điểm; nếu xóa cache quá sớm, request khác có thể nạp lại dữ liệu cũ. Nếu chỉ cập nhật database mà quên vô hiệu hóa cache, người dùng có thể tiếp tục thấy giá trị cũ cho đến khi TTL hết hạn.

Chiến lược phổ biến là cache-aside: ứng dụng đọc cache trước, cache miss thì đọc MySQL và đưa kết quả vào cache; khi ghi, ứng dụng commit transaction MySQL trước rồi mới vô hiệu hóa các cache key liên quan. Với hệ thống cần độ tin cậy cao, có thể ghi sự kiện invalidation vào transactional outbox trong cùng transaction với dữ liệu, sau đó một worker phát sự kiện và xóa cache theo cơ chế retry.

Bài học này nằm trong phạm vi làm chủ MySQL từ thiết kế bảng, truy vấn, transaction và kiểm soát đồng thời đến mở rộng hệ thống. Trọng tâm là hiểu ranh giới nhất quán giữa MySQL và cache, chọn thời điểm invalidation, xử lý race condition và kiểm thử để dữ liệu cache không đi lệch khỏi dữ liệu đã commit.

## 1. Cache phía ứng dụng giải quyết vấn đề gì?

Một ứng dụng có thể nhận hàng nghìn lượt đọc cùng một sản phẩm, cấu hình hoặc danh mục. Nếu mỗi lượt đọc đều truy vấn MySQL, database phải lặp lại công việc lấy cùng dữ liệu, parse SQL, thực hiện kế hoạch truy vấn và truyền kết quả qua mạng.

Cache giữ kết quả đọc thường xuyên ở một tầng truy cập nhanh hơn. Cache có thể nằm trong bộ nhớ của một tiến trình (local/in-process cache) hoặc ở dịch vụ dùng chung cho nhiều instance (distributed cache). Ví dụ thường gặp là cache cấu hình, danh mục sản phẩm, thông tin hồ sơ ít thay đổi, kết quả truy vấn tổng hợp và metadata.

Cache phù hợp khi:

- Dữ liệu được đọc nhiều hơn ghi.
- Chấp nhận được một mức stale data được xác định rõ.
- Chi phí truy vấn MySQL cao hơn chi phí lưu và lấy cache.
- Có cách xác định key và vô hiệu hóa khi dữ liệu thay đổi.
- Có thể đặt TTL để giới hạn thời gian tồn tại của dữ liệu cũ.

Cache không phù hợp để làm nguồn dữ liệu duy nhất cho nghiệp vụ cần tính đúng đắn tuyệt đối. Tồn kho, số dư, trạng thái thanh toán hoặc quyền truy cập nhạy cảm cần được xác minh bằng transaction và dữ liệu có thẩm quyền trong MySQL hoặc một hệ thống nguồn khác.

## 2. Mô hình cache-aside

Cache-aside (lazy loading) là mô hình ứng dụng chủ động đọc và ghi cache. Cache không tự theo dõi MySQL; ứng dụng chịu trách nhiệm nạp và vô hiệu hóa.

### 2.1. Luồng đọc

~~~mermaid
flowchart TD
    A["Request đọc dữ liệu"] --> B["Tạo cache key"]
    B --> C{"Cache hit?"}
    C -->|Có| D["Trả dữ liệu từ cache"]
    C -->|Không| E["Đọc MySQL"]
    E --> F["Đưa kết quả vào cache với TTL"]
    F --> G["Trả dữ liệu cho request"]
~~~

Ví dụ logic:

~~~java
public Product getProduct(long productId) {
    String key = "product:" + productId;

    Product cached = cache.get(key, Product.class);
    if (cached != null) {
        return cached;
    }

    Product loaded = repository.findById(productId)
        .orElseThrow(ProductNotFoundException::new);

    cache.put(key, loaded, Duration.ofMinutes(5));
    return loaded;
}
~~~

Đây là mã minh họa, trong ứng dụng thật cần xử lý cache miss đồng thời, serialization, lỗi cache và trường hợp dữ liệu không tồn tại. Cache nên được xem là một dependency có thể lỗi; nếu cache tạm thời không truy cập được, ứng dụng có thể fallback về MySQL trong giới hạn tải cho phép.

### 2.2. Luồng ghi và invalidation

Với cache-aside, cách an toàn thông dụng là cập nhật database trong transaction, đợi commit thành công rồi mới xóa cache key:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant DB as MySQL
    participant Cache as Cache
    App->>DB: BEGIN
    App->>DB: UPDATE dữ liệu
    App->>DB: COMMIT
    DB-->>App: Commit thành công
    App->>Cache: DELETE key liên quan
    Cache-->>App: Đã xóa hoặc key không tồn tại
~~~

Nếu transaction rollback, cache không bị xóa theo một thay đổi chưa tồn tại trong database. Sau commit, request đọc tiếp theo sẽ cache miss và nạp dữ liệu mới từ MySQL.

Vô hiệu hóa key thường đơn giản và ít rủi ro hơn việc tự xây dựng một bản cache mới từ dữ liệu đầu vào của lệnh ghi. Một nghiệp vụ có thể cập nhật nhiều cột, trigger, generated value hoặc dữ liệu liên quan; nếu ứng dụng tự ghi cache từ object trước khi database hoàn tất, cache có thể không phản ánh đúng trạng thái cuối cùng.

## 3. Vì sao phải invalidation sau commit?

Thứ tự thao tác quyết định liệu một reader khác có thể đưa dữ liệu cũ trở lại cache hay không.

### 3.1. Xóa cache trước commit tạo race condition

Giả sử cache đang chứa sản phẩm có giá 100. Một transaction thay giá thành 120:

~~~text
Writer A                         Reader B
DELETE cache key
                                 Cache miss
                                 SELECT MySQL -> giá 100
                                 PUT cache giá 100
UPDATE MySQL giá = 120
COMMIT
~~~

Kết quả: MySQL đã có giá 120 nhưng cache lại chứa giá 100. Cache chỉ hết sai khi key bị xóa lần nữa hoặc TTL hết hạn. Lỗi này có thể khó tái hiện vì phụ thuộc thời điểm hai request xen kẽ.

### 3.2. Commit trước, xóa sau

~~~text
Writer A                         Reader B
UPDATE MySQL giá = 120
COMMIT
                                 Cache hit giá 100 (cửa sổ ngắn)
DELETE cache key
                                 Cache miss ở lần đọc sau
                                 SELECT MySQL -> giá 120
                                 PUT cache giá 120
~~~

Invalidating sau commit loại bỏ race condition “reader nạp lại dữ liệu cũ trước khi writer commit”. Tuy vậy, giữa thời điểm commit và thời điểm xóa cache vẫn tồn tại một cửa sổ ngắn mà reader có thể nhận giá trị cũ. Với nghiệp vụ chấp nhận eventual consistency, cửa sổ này thường được quản lý bằng event sau commit, TTL và retry. Với nghiệp vụ cần read-after-write nghiêm ngặt, cần cơ chế mạnh hơn như bỏ qua cache trong request ghi, version/generation token hoặc đọc trực tiếp MySQL.

### 3.3. Không cập nhật cache từ dữ liệu chưa commit

Nếu ứng dụng ghi giá trị mới vào cache trước khi transaction commit, request khác có thể đọc dữ liệu chưa commit. Nếu transaction sau đó rollback, cache giữ một giá trị không tồn tại trong MySQL.

Vì vậy, mọi thao tác cache đại diện cho trạng thái đã lưu phải diễn ra sau commit. Nếu cache được dùng như một phần của workflow có trạng thái riêng, phải thiết kế semantics đó rõ ràng, không nhầm với cache của dữ liệu MySQL.

## 4. Spring transaction và thao tác cache sau commit

Trong Spring, @Transactional quản lý ranh giới transaction. Một phương thức service có thể phát application event trong transaction; listener chỉ xử lý khi transaction đã commit.

### 4.1. Dùng TransactionalEventListener

Ví dụ service:

~~~java
public record ProductChangedEvent(long productId) {}

@Service
public class ProductService {

    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductService(
            ProductRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void changePrice(long productId, BigDecimal newPrice) {
        Product product = repository.findById(productId)
            .orElseThrow(ProductNotFoundException::new);

        product.setPrice(newPrice);
        repository.save(product);

        events.publishEvent(new ProductChangedEvent(productId));
    }
}
~~~

Listener:

~~~java
@Component
public class ProductCacheInvalidator {

    private final CacheManager cacheManager;

    public ProductCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onProductChanged(ProductChangedEvent event) {
        Cache cache = cacheManager.getCache("products");
        if (cache != null) {
            cache.evict("product:" + event.productId());
        }
    }
}
~~~

TransactionalEventListener mặc định gắn listener với transaction hiện tại; AFTER_COMMIT chỉ chạy khi transaction commit. Nếu không có transaction, listener mặc định không chạy trừ khi bật fallbackExecution, và bật tùy chọn đó có thể làm thay đổi semantics. Chỉ dùng fallback khi thực sự muốn xử lý event ngoài transaction.

Ví dụ trên giả định cache key được xây dựng bằng product ID. Nếu cache có thêm key theo SKU, category, danh sách sản phẩm hoặc kết quả tìm kiếm, phải vô hiệu hóa các entry phụ thuộc tương ứng hoặc dùng cơ chế version/tag để quản lý nhóm key.

### 4.2. TransactionSynchronization

Với trường hợp không cần event domain riêng, có thể đăng ký callback sau commit:

~~~java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                cache.evict(cacheKey);
            }
        }
    );
} else {
    // Không có transaction bao quanh: xử lý theo chính sách riêng.
}
~~~

Đăng ký callback phải xảy ra trong đúng transaction mà thay đổi dữ liệu tham gia. Không đăng ký callback sau khi transaction đã hoàn tất hoặc ở một luồng khác không gắn với transaction.

### 4.3. Giới hạn của callback sau commit

Callback afterCommit giải quyết thứ tự, nhưng không tự cung cấp đảm bảo giao nhận bền vững. Tiến trình có thể dừng sau khi MySQL commit nhưng trước khi callback xóa cache. Cache cũng có thể tạm thời không truy cập được.

Nếu listener chạy đồng bộ và ném exception, transaction MySQL đã commit không thể rollback lại. Caller có thể nhận lỗi dù dữ liệu đã được ghi; client retry khi đó có thể tạo thao tác lặp nếu API không idempotent. Cần ghi log, metric, retry có kiểm soát và thiết kế idempotency.

@Async có thể chuyển listener sang executor khác, nhưng nếu process dừng trước khi tác vụ được thực thi hoặc queue không bền vững, sự kiện có thể mất. Async giúp tách thời gian xử lý khỏi request, không tự biến event thành durable message.

## 5. Transactional outbox cho invalidation đáng tin cậy

Khi không thể chấp nhận mất sự kiện invalidation sau commit, dùng transactional outbox. Ứng dụng ghi thay đổi nghiệp vụ và một bản ghi outbox trong cùng transaction MySQL. Một worker đọc outbox sau commit, phát sự kiện hoặc xóa cache, rồi đánh dấu đã xử lý.

### 5.1. Vì sao outbox giải quyết được khoảng trống dual-write?

Nếu ứng dụng thực hiện hai thao tác độc lập:

1. Commit dữ liệu vào MySQL.
2. Gửi event đến broker hoặc cache.

Process có thể dừng giữa hai bước. Nếu gửi event trước commit, event có thể được phát dù transaction rollback. Nếu gửi sau commit, process có thể dừng trước khi gửi.

Outbox ghi dữ liệu nghiệp vụ và event trong cùng transaction. Hoặc cả hai cùng commit, hoặc cả hai cùng rollback:

~~~mermaid
flowchart TD
    A["BEGIN MySQL transaction"] --> B["UPDATE business row"]
    B --> C["INSERT outbox event"]
    C --> D{"COMMIT?"}
    D -->|Rollback| E["Không có thay đổi hoặc event"]
    D -->|Commit| F["Worker đọc outbox"]
    F --> G["Phát event / invalidate cache"]
    G --> H["Đánh dấu event đã xử lý"]
    H --> I["Retry nếu phát hiện lỗi"]
~~~

### 5.2. Bảng outbox minh họa

~~~sql
CREATE TABLE outbox_event (
  event_id BIGINT NOT NULL AUTO_INCREMENT,
  aggregate_type VARCHAR(100) NOT NULL,
  aggregate_id VARCHAR(128) NOT NULL,
  event_type VARCHAR(100) NOT NULL,
  payload JSON NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  published_at TIMESTAMP(6) NULL,
  attempts INT NOT NULL DEFAULT 0,
  PRIMARY KEY (event_id),
  KEY ix_outbox_pending (published_at, event_id)
) ENGINE = InnoDB;
~~~

Trong cùng transaction cập nhật sản phẩm:

~~~sql
START TRANSACTION;

UPDATE product
SET price = 120.00,
    version = version + 1
WHERE product_id = 101;

INSERT INTO outbox_event (
  aggregate_type,
  aggregate_id,
  event_type,
  payload
)
VALUES (
  'Product',
  '101',
  'ProductChanged',
  JSON_OBJECT('productId', 101)
);

COMMIT;
~~~

Ví dụ giả định bảng product có cột version. Trong ứng dụng thật, chỉ phát event khi UPDATE thực sự thay đổi dữ liệu theo quy tắc nghiệp vụ; kiểm tra affected rows trước khi insert outbox event hoặc phát event domain. Có thể dùng event ID dạng UUID nếu nhiều writer cần tạo ID độc lập hoặc cần tránh phụ thuộc một sequence trung tâm.

Worker lấy các event chưa xử lý, phát invalidation và cập nhật trạng thái. MySQL 8 hỗ trợ FOR UPDATE SKIP LOCKED, hữu ích khi nhiều worker cùng lấy việc:

~~~sql
START TRANSACTION;

SELECT event_id, aggregate_type, aggregate_id, event_type, payload
FROM outbox_event
WHERE published_at IS NULL
ORDER BY event_id
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- Ứng dụng xử lý các event đã lấy và cập nhật trạng thái.
COMMIT;
~~~

Đoạn SQL chỉ minh họa cách claim hàng; worker phải giữ transaction ngắn và thiết kế việc phát event cẩn thận. Không giữ row lock trong lúc gọi một dịch vụ mạng chậm. Có thể dùng trạng thái claim/lease, worker ID và thời hạn lease để lấy việc trong transaction ngắn, sau đó phát event bên ngoài transaction.

### 5.3. At-least-once và idempotency

Worker có thể phát event thành công rồi process dừng trước khi đánh dấu published_at. Sau khi khởi động lại, event được phát lần nữa. Vì vậy, outbox thường cung cấp semantics at-least-once, không phải exactly-once end-to-end.

Với cache invalidation, thao tác xóa cùng key nhiều lần thường idempotent: key đã bị xóa thì xóa lần nữa vẫn giữ trạng thái không tồn tại. Với các side effect khác, consumer phải lưu event ID đã xử lý hoặc dùng version để tránh áp dụng lặp.

Ghi nhận số lần retry, tuổi event cũ nhất, số event pending và lỗi phát. Cần có chính sách dead-letter hoặc cảnh báo khi event vượt ngưỡng retry; không xóa event lỗi chỉ để backlog biến mất.

## 6. Cache invalidation cho nhiều loại key

Một bản ghi MySQL có thể xuất hiện trong nhiều cache entry:

- Cache chi tiết theo ID: product:{id}.
- Cache theo SKU: product:sku:{sku}.
- Cache danh sách theo category: products:category:{categoryId}.
- Cache kết quả tìm kiếm: products:search:{queryHash}.
- Cache trang chủ hoặc số liệu tổng hợp.

Khi cập nhật một sản phẩm, xóa mỗi product:{id} có thể chưa đủ nếu các danh sách hoặc kết quả tìm kiếm vẫn giữ bản cũ.

### 6.1. Thiết kế key theo dependency

Tạo tài liệu hoặc code registry cho biết dữ liệu nào phụ thuộc vào bảng/cột nào và key nào phải bị invalidated khi mutation xảy ra. Ví dụ:

| Thay đổi MySQL | Cache key có thể cần invalidation |
|---|---|
| Đổi tên/giá sản phẩm | product:{id}, product:sku:{sku}, danh sách category và search result |
| Chuyển category | Cache chi tiết, danh sách category cũ và mới |
| Xóa sản phẩm | Cache chi tiết, lookup theo SKU, danh sách và kết quả tìm kiếm |
| Đổi trạng thái đơn hàng | order:{id}, danh sách đơn theo user và số liệu trạng thái |
| Đổi quyền user | Cache profile/quyền và mọi cache được phân vùng theo quyền |

Không đưa dữ liệu của tenant hoặc user khác nhau vào cùng một cache key nếu nội dung phụ thuộc quyền hoặc phạm vi dữ liệu. Key cần chứa tenant ID, locale, currency, role/scope hoặc tham số lọc cần thiết.

### 6.2. Invalidate nhóm key

Nếu một thay đổi ảnh hưởng hàng nghìn key, xóa từng key có thể tốn thời gian và tạo tải lớn. Có thể dùng namespace version:

- Key thực tế gồm catalog:v42:category:12.
- Khi catalog thay đổi, tăng version namespace lên v43.
- Các key cũ tự trở thành không còn được tham chiếu và hết hạn theo TTL.

Version namespace giúp invalidation một nhóm dữ liệu nhanh, nhưng phải đảm bảo cập nhật version được quan sát nhất quán trên mọi instance. Nếu mỗi tiến trình giữ version local riêng, các node có thể tiếp tục đọc namespace cũ. Dùng một nguồn version dùng chung hoặc event fan-out có xác nhận.

Tránh xóa toàn bộ cache khi một bản ghi thay đổi. Flush cache có thể tạo cache stampede, làm nhiều request đồng thời quay về MySQL và gây quá tải đúng lúc hệ thống đang xử lý mutation.

### 6.3. Không dùng key scan làm chiến lược mặc định

Quét toàn bộ key để tìm prefix liên quan có thể tốn tài nguyên và có hành vi khác nhau theo loại cache. Thiết kế key, tag, set thành viên hoặc namespace version ngay từ đầu. Nếu phải dùng SCAN trong Redis hoặc cơ chế tương đương, giới hạn tốc độ, xử lý kết quả theo batch và kiểm thử trên kích thước dữ liệu thực tế; không dùng thao tác quét đồng bộ trong request ghi.

## 7. Race condition khi cache miss và stale refill

Ngay cả khi writer invalidates sau commit, vẫn có một race khác:

~~~text
Reader A                         Writer B
GET cache -> miss
SELECT MySQL -> giá 100
                                 UPDATE MySQL giá 120
                                 COMMIT
                                 DELETE cache key
PUT cache giá 100
~~~

Reader A bắt đầu đọc trước khi writer commit nhưng ghi cache sau khi writer đã xóa key. Cache lại chứa giá cũ. Đây là stale refill race.

Các cách xử lý tùy mức nhất quán:

1. **TTL ngắn và chấp nhận eventual consistency:** đơn giản, phù hợp dữ liệu ít nhạy cảm; cần giới hạn stale window.
2. **Single-flight hoặc lock theo key:** chỉ một reader nạp cache cho key tại một thời điểm; writer cần phối hợp cùng cơ chế lock nếu yêu cầu chặt.
3. **Version/generation token:** reader ghi nhận generation trước khi đọc MySQL, sau đó chỉ được populate cache nếu generation vẫn chưa đổi.
4. **Version-aware cache write:** entry mang version tăng đơn điệu; thao tác atomic chỉ cho phép version mới hơn ghi đè version cũ.
5. **Bypass cache sau write:** request vừa ghi đọc trực tiếp từ MySQL hoặc dùng dữ liệu trả về từ transaction đã commit.

Ví dụ generation token:

~~~text
Reader:
  generation_before = GET generation:product:101
  value = SELECT product FROM MySQL
  atomic_if_equal(generation_before):
      SET product:101 = value

Writer after commit:
  INCREMENT generation:product:101
  DELETE product:101
~~~

Việc kiểm tra generation và ghi cache phải là một thao tác atomic ở cache; nếu tách thành hai lệnh, writer vẫn có thể tăng generation giữa bước kiểm tra và bước ghi. Cần dùng script/transaction atomic phù hợp với cache backend. Generation key không nên bị xóa hoặc hết hạn sớm hơn các entry mà nó bảo vệ, nếu không token cũ có thể được tái sử dụng. Reader phải lấy generation trước khi mở snapshot đọc dữ liệu hoặc bảo đảm generation và payload được xác minh trên cùng một snapshot nhất quán; nếu reader dùng một transaction REPEATABLE READ đã mở từ trước rồi mới lấy generation mới, nó vẫn có thể ghi payload từ snapshot cũ.

Một phương án khác là lưu version trong row MySQL và trong cache. Writer tăng version cùng transaction dữ liệu. Reader chỉ được publish kết quả nếu version đọc được vẫn khớp generation hiện tại. Cần thiết kế nơi lưu generation sao cho writer và reader kiểm tra được tính atomic; chỉ thêm cột version vào row nhưng không có bước compare-and-set vẫn chưa giải quyết hết race.

Không có một mẫu invalidation đơn giản nào đảm bảo cache và MySQL nhất quán tuyệt đối qua mọi lỗi mạng và process crash. Hãy chọn semantics nhất quán theo nghiệp vụ, đo stale window và ghi rõ điều kiện chấp nhận.

## 8. Cache stampede, TTL và lỗi cache

### 8.1. Cache stampede

Khi một key phổ biến hết hạn, hàng trăm request có thể cùng cache miss và đồng thời truy vấn MySQL. Kết quả là database chịu tải đột biến.

Biện pháp:

- Single-flight/request coalescing để nhiều request dùng chung một lần nạp.
- Lock có thời hạn theo key để một worker nạp, các worker khác chờ hoặc dùng dữ liệu cũ nếu được phép.
- TTL jitter để nhiều key không hết hạn cùng thời điểm.
- Refresh trước khi hết hạn với giới hạn concurrency.
- Stale-while-revalidate cho dữ liệu có thể tạm thời cũ.
- Giới hạn tải fallback về MySQL khi cache lỗi.

Lock cần có lease/timeout và cách xử lý khi chủ lock chết. Không dùng lock không thời hạn có thể làm key bị treo vô hạn.

### 8.2. TTL là lớp bảo vệ, không thay thế invalidation

TTL giới hạn thời gian một entry tồn tại, nhưng nếu TTL là 30 phút thì dữ liệu có thể cũ gần 30 phút. Đối với dữ liệu thay đổi thường xuyên, invalidation sau commit giúp rút ngắn stale window; TTL đóng vai trò dự phòng khi event bị mất hoặc một node bỏ lỡ invalidation.

Thêm jitter ngẫu nhiên vào TTL để tránh nhiều key cùng hết hạn. TTL cần phù hợp với mức thay đổi dữ liệu, độ nhạy của nghiệp vụ và khả năng chịu tải của MySQL khi cache miss tăng.

### 8.3. Cache unavailable

Nếu cache không truy cập được:

- Có thể fallback về MySQL cho key ít tải.
- Dùng circuit breaker hoặc giới hạn concurrency để tránh dồn toàn bộ traffic vào database.
- Không ghi cache thất bại vào một vòng retry vô hạn trong request.
- Ghi metric cache error, hit/miss, fallback và latency.
- Khi cache phục hồi, tránh nạp lại toàn bộ dữ liệu đồng thời.

Cache là lớp tăng tốc. Nếu cache là dependency bắt buộc của nghiệp vụ, cần xác định rõ đây là datastore hay state store và thiết kế độ bền/HA tương ứng, không còn xem nó đơn thuần là cache.

## 9. Negative caching và dữ liệu không tồn tại

Cache-aside thường chỉ lưu dữ liệu tìm thấy. Với một ID không tồn tại, mỗi request lặp lại có thể truy vấn MySQL và tạo tải không cần thiết. Negative caching lưu một marker “không tìm thấy” với TTL ngắn.

Ví dụ:

~~~text
product:999 -> NOT_FOUND (TTL 20 giây)
~~~

Khi sản phẩm 999 được tạo, event sau commit phải xóa negative cache key. Nếu không, người dùng có thể không thấy sản phẩm mới cho đến khi marker hết hạn.

Phân biệt ba trạng thái:

- Cache miss: key chưa có trong cache.
- Cached not found: đã truy vấn MySQL và xác nhận không tồn tại.
- Cached value: có dữ liệu.

Không dùng null làm tín hiệu duy nhất nếu cache API cũng trả null khi key không tồn tại. Dùng sentinel hoặc kiểu kết quả có trạng thái rõ ràng. Negative cache cần TTL ngắn và phải tính đến tenant, quyền truy cập và soft delete.

## 10. Các lựa chọn write-through và write-behind

Cache-aside không phải mô hình duy nhất:

| Mô hình | Luồng ghi | Đặc điểm |
|---|---|---|
| Cache-aside | Ghi MySQL, sau commit xóa cache | Đơn giản, ứng dụng kiểm soát cache miss và invalidation |
| Write-through | Ghi đi qua cache layer, cache cập nhật đồng bộ với datastore | Có thể giữ cache nóng nhưng cần định nghĩa thứ tự và xử lý lỗi giữa hai hệ thống |
| Write-behind/write-back | Ghi cache trước, hệ thống ghi MySQL sau theo batch/async | Độ trễ ghi thấp nhưng rủi ro mất dữ liệu và phức tạp phục hồi cao |

Với dữ liệu MySQL là nguồn có thẩm quyền, cache-aside cộng invalidation sau commit thường là điểm bắt đầu dễ vận hành. Write-behind không phù hợp nếu ứng dụng coi commit MySQL là xác nhận nghiệp vụ; nếu dùng, cache trở thành một phần của hệ thống ghi và cần durability, replay, idempotency, backup và recovery plan riêng.

## 11. Kiểm thử tính nhất quán giữa MySQL và cache

Không chỉ test rằng cache hit trả đúng dữ liệu. Cần kiểm tra cả commit, rollback, race condition, nhiều instance và lỗi giao nhận event.

### 11.1. Test commit và rollback

- Khi transaction commit, cache key liên quan được invalidated.
- Khi transaction rollback, cache cũ vẫn hợp lệ và không bị thay bằng dữ liệu chưa commit.
- Khi transaction không có thay đổi thực tế, không phát invalidation thừa nếu có thể tránh.
- Nếu callback invalidation lỗi sau commit, dữ liệu MySQL vẫn được xác nhận đã commit và hệ thống ghi nhận lỗi để retry.

### 11.2. Test concurrent reader/writer

Tạo hai luồng có barrier:

1. Reader cache miss và bắt đầu đọc MySQL.
2. Writer cập nhật row, commit và invalidates key.
3. Reader hoàn tất truy vấn và thử populate cache.
4. Đọc lại cache và xác minh không thể giữ giá trị cũ ngoài stale window đã chấp nhận.

Test này phát hiện stale refill race. Dùng synchronization primitive như CountDownLatch/CyclicBarrier thay vì dựa vào Thread.sleep để tạo timing ngẫu nhiên.

### 11.3. Test outbox

- Event được ghi cùng transaction nghiệp vụ.
- Rollback không để lại outbox event.
- Worker retry khi cache hoặc broker tạm lỗi.
- Process dừng sau khi invalidate nhưng trước khi đánh dấu published không gây sai lệch khi event được xử lý lại.
- Nhiều worker không làm mất event.
- Event cũ được cảnh báo và có quy trình xử lý.

### 11.4. Test nhiều instance

Nếu dùng local cache, mỗi instance có bản sao riêng. Event invalidation phải được phát đến tất cả instance hoặc cache phải có TTL/namespace giúp giới hạn stale. Test trên ít nhất hai application instance: ghi qua instance A, đọc qua instance B và xác minh cache B được cập nhật hoặc invalidated theo chính sách.

Với distributed cache dùng chung, kiểm tra key namespace, tenant isolation, serialization version và hành vi khi cache cluster failover.

## 12. Quan sát và vận hành cache

Các metric nên theo dõi:

| Metric | Ý nghĩa |
|---|---|
| Hit ratio | Tỷ lệ request lấy được dữ liệu từ cache |
| Miss rate | Tỷ lệ phải đọc MySQL hoặc nguồn khác |
| Eviction count | Số entry bị xóa do TTL hoặc áp lực bộ nhớ |
| Invalidation lag | Thời gian từ DB commit đến cache invalidation |
| Outbox oldest age | Tuổi event chưa được xử lý lâu nhất |
| Retry/dead-letter count | Số event invalidation lỗi và retry |
| Cache operation latency | Thời gian GET/SET/DELETE |
| Fallback rate | Tỷ lệ request phải bỏ cache và đọc MySQL |
| Stale-read indicator | Số lần phát hiện cache version cũ hoặc đọc vượt stale SLO |

Hit ratio cao không tự chứng minh cache tốt. Cache có thể trả dữ liệu cũ rất hiệu quả. Cần theo dõi cả invalidation lag, stale read, độ chính xác dữ liệu và tải MySQL.

Đặt cảnh báo khi outbox backlog tăng, invalidation lag vượt SLO, cache error tăng hoặc MySQL fallback traffic vượt ngưỡng. Với local cache, cần đo riêng từng instance để phát hiện một node không nhận event.

## 13. Tình huống thực hành

Một ứng dụng bán hàng lưu cache thông tin sản phẩm trong 10 phút. Người quản trị thay đổi giá sản phẩm trong MySQL; API ghi trả thành công nhưng một số người dùng vẫn thấy giá cũ. Hệ thống có bốn replica ứng dụng và mỗi replica có local cache.

Hãy xây dựng chiến lược:

1. Xác định cache key cho trang chi tiết, SKU lookup và danh sách category.
2. Bọc thay đổi giá trong transaction MySQL.
3. Phát ProductChangedEvent trong transaction và xử lý bằng listener AFTER_COMMIT, hoặc ghi outbox cùng transaction nếu cần bảo đảm event không mất khi process dừng.
4. Phát invalidation đến cả bốn replica hoặc chuyển sang distributed cache dùng chung.
5. Đặt TTL làm lớp dự phòng và thêm metric invalidation lag.
6. Kiểm thử rollback để cache không bị xóa bởi thay đổi chưa commit.
7. Kiểm thử stale refill race khi reader đã cache miss trước thời điểm writer commit.
8. Xác minh một lần ghi qua replica A khiến đọc qua replica B tuân theo consistency policy.

Nếu giá bán phải chính xác ngay trong bước thanh toán, không dùng giá từ cache làm giá cuối cùng. Đọc/khóa và xác minh giá trong transaction nghiệp vụ trên MySQL, đồng thời lưu giá đã chốt vào đơn hàng. Cache chỉ phục vụ hiển thị; nguồn dữ liệu dùng để tính tiền phải theo hợp đồng nghiệp vụ đã xác định.

## 14. Checklist thiết kế cache invalidation

### Trước khi bật cache

- [ ] Xác định MySQL hay hệ thống nào là nguồn dữ liệu có thẩm quyền.
- [ ] Ghi rõ dữ liệu nào được cache và mức stale được chấp nhận.
- [ ] Thiết kế key chứa đủ tenant, locale, filter và quyền truy cập.
- [ ] Liệt kê mọi cache entry phụ thuộc vào một thay đổi dữ liệu.
- [ ] Chọn TTL, negative caching và cách xử lý cache unavailable.
- [ ] Quy định read-after-write cho từng luồng nghiệp vụ.

### Khi ghi dữ liệu

- [ ] Commit transaction MySQL trước khi invalidation.
- [ ] Không publish cache value từ dữ liệu chưa commit.
- [ ] Dùng after-commit callback/event hoặc transactional outbox.
- [ ] Xử lý lỗi invalidation bằng retry, metric và cảnh báo.
- [ ] Đảm bảo event consumer idempotent.
- [ ] Xem xét stale refill race và version/generation token nếu cần.

### Khi vận hành

- [ ] Theo dõi hit/miss, invalidation lag và stale read.
- [ ] Theo dõi outbox backlog và event lỗi.
- [ ] Kiểm thử nhiều instance, restart và cache failover.
- [ ] Có cách flush/namespace rollover được kiểm soát.
- [ ] Không flush toàn bộ cache cho một thay đổi nhỏ.
- [ ] Kiểm tra dữ liệu nhạy cảm không bị chia sẻ qua cache key sai phạm vi.

## 15. Câu hỏi tự kiểm tra

1. Cache-aside khác write-through và write-behind như thế nào?
2. Vì sao xóa cache trước commit có thể làm reader nạp lại dữ liệu cũ?
3. AFTER_COMMIT trong Spring bảo đảm điều gì và không bảo đảm điều gì?
4. Vì sao process crash sau commit nhưng trước invalidation vẫn có thể làm cache stale?
5. Transactional outbox giải quyết khoảng trống dual-write như thế nào?
6. Vì sao consumer outbox cần idempotency dù event chỉ đại diện cho một lần thay đổi?
7. Stale refill race xảy ra trong lịch xen kẽ nào?
8. Generation token cần thao tác atomic nào để ngăn reader ghi đè cache mới bằng dữ liệu cũ?
9. Vì sao TTL không thay thế được invalidation?
10. Khi nào cần bypass cache và đọc trực tiếp MySQL?

Cache giúp MySQL phục vụ tải đọc hiệu quả hơn, nhưng chỉ an toàn khi ứng dụng quản lý rõ nguồn dữ liệu, thời điểm invalidation và mức nhất quán. Với cache-aside, hãy commit MySQL trước rồi invalidates; dùng after-commit event cho luồng đơn giản và transactional outbox khi cần giao nhận bền vững. Kiểm thử cả rollback, concurrent refill, nhiều instance và lỗi worker để cache luôn tuân theo consistency policy của nghiệp vụ.

# Phân trang, bộ nhớ đệm và giảm số lần gọi dịch vụ

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot kết nối với database, object storage, messaging và các dịch vụ managed của AWS, Azure, Google Cloud. Mỗi lần gọi database hoặc dịch vụ từ xa đều có chi phí: độ trễ mạng, serialization, connection, compute, quota và khả năng phát sinh lỗi.

Bài học tập trung vào ba kỹ thuật giúp giảm chi phí đó mà vẫn giữ đúng semantics dữ liệu:

1. Chọn offset pagination, cursor pagination hoặc keyset scrolling theo đặc điểm datastore và cách người dùng duyệt dữ liệu.
2. Dùng Spring Data Page, Slice, Window và API continuation token để đọc tập dữ liệu lớn theo từng phần.
3. Dùng Spring Cache abstraction, Caffeine và Redis-compatible managed cache theo mô hình cache-aside, TTL và invalidation.
4. Tránh N+1 bằng projection, batch query, bulk API và request aggregation.
5. Giảm các lần gọi trùng nhau bằng request coalescing, cache và deduplication.
6. Tái sử dụng HTTP/Redis client và connection pool; đặt timeout, concurrency limit và retry có kiểm soát.
7. Đo cache hit ratio, query count, latency, payload size, service call count và chi phí trước/sau tối ưu.
8. Giữ an toàn tenant boundary, quyền truy cập, dữ liệu nhạy cảm và freshness khi cache hoặc phân trang.

## 1. Vì sao pagination, cache và call reduction quan trọng?

### 1.1. Một request có thể tạo nhiều lần gọi phía sau

Một API lấy danh sách đơn hàng có thể tạo chuỗi công việc:

~~~mermaid
flowchart TD
    USER["Client request"] --> API["Spring Boot controller"]
    API --> AUTH["Resolve tenant and permissions"]
    AUTH --> DB["Query orders"]
    DB --> CUSTOMER["Load customer for each order"]
    DB --> ASSET["Load asset for each order"]
    API --> CACHE["Read/write cache"]
    API --> CLOUD["Call managed service"]
    CUSTOMER --> RESP["Build response"]
    ASSET --> RESP
    CACHE --> RESP
    CLOUD --> RESP
    RESP --> USER
~~~

Nếu trang có 30 đơn hàng và service gọi thêm customer cùng asset riêng cho từng đơn, một request có thể phát sinh hàng chục hoặc hàng trăm truy vấn. Nếu người dùng chuyển qua trang 20 bằng offset lớn, database có thể phải bỏ qua rất nhiều bản ghi. Nếu cùng một danh mục được đọc liên tục, ứng dụng vẫn gọi database dù dữ liệu gần như không đổi.

Ba kỹ thuật giải quyết ba nguyên nhân khác nhau:

- **Pagination:** giới hạn lượng dữ liệu đọc và truyền trong một lần.
- **Caching:** tránh đọc lại dữ liệu đã có thể tái sử dụng.
- **Batching/aggregation:** thay nhiều lần gọi nhỏ bằng ít lần gọi lớn hơn.

### 1.2. Mục tiêu tối ưu phải đo được

Không tối ưu chỉ vì muốn giảm số dòng code hoặc số query nhìn thấy trong log. Trước khi thay đổi, hãy đo:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Request latency p50/p95/p99 | Thời gian người dùng thực sự chờ |
| Database query count/request | Số query trung bình cho một API |
| Rows scanned / rows returned | Mức độ đọc thừa |
| Cache hit ratio | Tỷ lệ request được đáp ứng từ cache |
| Cache miss latency | Chi phí khi phải đọc nguồn |
| Remote calls/request | Số lần gọi service khác |
| Payload bytes | Dữ liệu truyền qua mạng |
| Connection pool wait | Thời gian chờ connection |
| Error/retry rate | Mức độ phụ thuộc và lỗi của dịch vụ |
| Cost per request | Chi phí database, cache, network và compute quy đổi |

Một kỹ thuật có thể giảm query count nhưng tăng memory, stale data hoặc chi phí cache. Cần đánh giá cả latency, correctness và tổng chi phí.

## 2. Phân trang dữ liệu

### 2.1. Offset pagination

Offset pagination dùng số trang và kích thước trang. Ví dụ:

~~~sql
SELECT id, customer_id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
~~~

Với page size 20:

- Trang đầu: LIMIT 20 OFFSET 0.
- Trang thứ hai: LIMIT 20 OFFSET 20.
- Trang thứ ba: LIMIT 20 OFFSET 40.

Ưu điểm:
- Dễ triển khai và dễ hiểu.
- Người dùng có thể nhảy đến một trang bất kỳ.
- Phù hợp với bảng quản trị nhỏ hoặc tập dữ liệu có giới hạn.

Nhược điểm:
- Offset càng lớn, database thường phải xử lý hoặc bỏ qua nhiều kết quả trước khi trả trang cần thiết.
- Insert/delete giữa hai lần request có thể làm bản ghi dịch chuyển, dẫn đến trùng hoặc bỏ sót khi người dùng đi qua các trang.
- Tổng số trang có thể yêu cầu thêm count query.
- API cho phép page size quá lớn có thể tạo response nặng và tiêu tốn memory.

Offset phù hợp khi người dùng cần số trang và dữ liệu không quá lớn. Không nên mặc định dùng nó cho infinite scroll hoặc export hàng triệu bản ghi.

### 2.2. Page, Slice và List trong Spring Data

Spring Data hỗ trợ các kiểu kết quả khác nhau:

| Kiểu | Metadata | Chi phí thường gặp | Khi nên dùng |
| --- | --- | --- | --- |
| Page<T> | Nội dung, page number, total elements, total pages | Có thể cần thêm count query | UI cần hiển thị tổng số trang |
| Slice<T> | Nội dung và hasNext | Thường đọc thêm một phần tử để biết còn trang | Next/Previous hoặc infinite scroll |
| List<T> | Chỉ danh sách kết quả | Không tạo metadata Page; vẫn cần giới hạn query | API tự xây response đơn giản |
| Window<T> | Một cửa sổ kết quả và scroll position | Hỗ trợ offset/keyset scrolling tùy store | Duyệt dữ liệu lớn theo từng cửa sổ |

Page hữu ích khi tổng số bản ghi thực sự cần thiết cho giao diện. Count query có thể đắt trên bảng lớn hoặc query có join/filter phức tạp. Nếu chỉ cần nút “Tiếp theo”, Slice thường đủ.

Ví dụ repository:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    Page<Order> findPageByTenantIdAndStatus(
            String tenantId,
            OrderStatus status,
            Pageable pageable);

    Slice<Order> findSliceByTenantIdAndStatus(
            String tenantId,
            OrderStatus status,
            Pageable pageable);
}
~~~

### 2.3. Tạo Pageable với sort ổn định

Ví dụ service nhận page và size từ API:

~~~java
public Page<OrderSummary> listOrders(
        String tenantId,
        OrderStatus status,
        int requestedPage,
        int requestedSize) {

    int page = Math.max(requestedPage, 0);
    int size = Math.max(1, Math.min(requestedSize, 100));

    Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.desc("id")));

    return orderRepository
            .findPageByTenantIdAndStatus(tenantId, status, pageable)
            .map(orderMapper::toSummary);
}
~~~

Các điểm cần chú ý:

- PageRequest dùng page index bắt đầu từ 0.
- Luôn giới hạn page size ở server; không tin giá trị client gửi lên.
- Có thể đặt giới hạn page index hoặc yêu cầu cursor khi client muốn đi quá sâu; một page number rất lớn vẫn có thể tạo offset rất lớn.
- Sort phải ổn định. Nếu createdAt có thể trùng, thêm khóa duy nhất như id làm tie-breaker.
- Không đưa trực tiếp tên cột do client truyền vào Sort nếu chưa kiểm tra allowlist.
- Filter tenant phải lấy từ security context hoặc principal đã xác thực, không dựa vào tenant ID tùy ý trong query string.
- Dùng projection/DTO để tránh serialize toàn bộ entity và lazy relation.

### 2.4. Khi nào count query trở thành nút thắt?

Một Page<T> cần biết tổng số phần tử. Spring Data có thể phát sinh query dạng:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status;
~~~

Nếu điều kiện có nhiều join, distinct hoặc filter phức tạp, count có thể tốn thời gian đáng kể dù query lấy 20 row khá nhanh.

Có ba lựa chọn:

1. Dùng Slice<T> nếu chỉ cần biết có trang kế tiếp.
2. Dùng List<T> với Pageable nếu service chỉ cần dữ liệu trong giới hạn và tự quản lý metadata.
3. Duy trì aggregate/count riêng nếu tổng số cần hiển thị thường xuyên và có thể chấp nhận cập nhật bất đồng bộ.

Không cache total count quá lâu nếu nghiệp vụ yêu cầu số liệu chính xác ngay sau mỗi thay đổi. Nếu chấp nhận eventual consistency, hãy ghi rõ thời điểm cập nhật.

### 2.5. Keyset pagination (seek pagination)

Keyset pagination dùng giá trị của bản ghi cuối cùng ở trang trước để tìm phần tiếp theo. Thay vì bỏ qua OFFSET bản ghi, query dùng điều kiện trên sort key.

Giả sử sort giảm dần theo created_at, sau đó theo id:

~~~sql
SELECT id, customer_id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
       created_at < :lastCreatedAt
       OR (
           created_at = :lastCreatedAt
           AND id < :lastId
       )
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSizePlusOne;
~~~

Trang đầu không có cursor nên bỏ điều kiện keyset và lấy pageSize + 1 bản ghi. Trang sau dùng created_at và id của bản ghi cuối cùng trang trước.

Lấy thêm một bản ghi giúp biết còn trang tiếp theo:
- Nếu query trả nhiều hơn page size, cắt phần tử dư và trả hasNext = true.
- Nếu không có phần tử dư, đây là trang cuối.

Keyset phù hợp với tập dữ liệu lớn, infinite scroll và export tuần tự. Nó không hỗ trợ nhảy tùy ý đến trang số 500 như offset.

### 2.6. Điều kiện để keyset hoạt động đúng

- Sort phải có thứ tự xác định, tốt nhất kết thúc bằng primary key.
- Các trường dùng làm cursor nên không null.
- Có index phù hợp với filter và sort, ví dụ (tenant_id, status, created_at DESC, id DESC).
- Cursor phải giữ tất cả sort key cần thiết.
- Không thay đổi filter/sort giữa hai trang nếu vẫn dùng cursor cũ.
- Nếu sort key có thể thay đổi trong lúc duyệt, bản ghi có thể dịch chuyển qua cursor; hãy chọn trường bất biến hoặc dùng snapshot/version boundary phù hợp.

Keyset không tự tạo snapshot nhất quán cho toàn bộ quá trình. Nếu nghiệp vụ cần một snapshot cố định, cần transaction/snapshot hoặc watermark/version boundary được datastore hỗ trợ.

### 2.7. Keyset scrolling với Spring Data

Spring Data Commons cung cấp Window<T> và ScrollPosition. Các module datastore hỗ trợ scrolling có thể triển khai offset hoặc keyset filtering.

Ví dụ với Spring Data JPA:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    Window<Order>
    findFirst50ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
            String tenantId,
            OrderStatus status,
            ScrollPosition position);
}
~~~

Đọc cửa sổ đầu và lấy vị trí tiếp theo:

~~~java
ScrollPosition position = ScrollPosition.keyset();

Window<Order> window =
        orderRepository
                .findFirst50ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
                        tenantId,
                        OrderStatus.PAID,
                        position);

if (!window.isEmpty() && !window.isLast()) {
    ScrollPosition nextPosition =
            window.positionAt(window.size() - 1);

    Window<Order> nextWindow =
            orderRepository
                    .findFirst50ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
                            tenantId,
                            OrderStatus.PAID,
                            nextPosition);
}
~~~

Trong ví dụ, createdAt và id tạo thứ tự ổn định. Các trường keyset cần được map và trả về trong kết quả; nếu dùng projection, hãy giữ các trường sort cần thiết. Kiểm tra datastore module và phiên bản Spring Data đang dùng vì không phải mọi query/store đều hỗ trợ Window và keyset.

### 2.8. Cursor pagination ở API

Với API public, không nên bắt client gửi trực tiếp toàn bộ sort key hoặc SQL condition. Trả một cursor opaque:

~~~json
{
  "items": [
    {
      "id": "ord-1001",
      "status": "PAID"
    }
  ],
  "nextCursor": "eyJ2IjoxLCJrZXkiOi4uLn0.signature",
  "hasMore": true
}
~~~

Cursor có thể chứa:
- Version của cursor format.
- Các sort key của phần tử cuối.
- Fingerprint của filter và sort.
- Tenant/partition scope đã xác thực.
- Thời hạn sử dụng nếu cần.

Nên ký cursor bằng HMAC hoặc cơ chế tương đương để client không thể sửa khóa hoặc filter. Base64URL chỉ là encoding, không phải mã hóa. Nếu cursor chứa thông tin nhạy cảm, hãy mã hóa hoặc lưu state phía server và chỉ trả token ngẫu nhiên.

Khi nhận cursor:
1. Xác minh chữ ký và version.
2. Xác minh cursor thuộc đúng tenant/principal.
3. Kiểm tra filter/sort hiện tại khớp fingerprint.
4. Áp dụng page size giới hạn.
5. Dùng keyset/cursor native của datastore.
6. Trả cursor mới nếu còn dữ liệu.

### 2.9. Pagination native ở các managed datastore

Không phải dịch vụ nào cũng dùng OFFSET:

| Dịch vụ | Cơ chế tiếp tục | Lưu ý |
| --- | --- | --- |
| SQL database / Cloud SQL | LIMIT/OFFSET hoặc keyset predicate | Offset sâu có thể tốn I/O; dùng index |
| Firestore Native | orderBy, limit, startAfter/document snapshot | Cursor phải theo cùng query và thứ tự |
| Amazon DynamoDB | LastEvaluatedKey → ExclusiveStartKey | Tiếp tục cho đến khi không còn key; filter có thể tạo trang rỗng nhưng vẫn có key |
| Azure Cosmos DB | Continuation token | Số item mỗi trang có thể thay đổi; tiếp tục đến khi hết token |
| BigQuery REST API | pageToken và maxResults | Token gắn với kết quả query/list tương ứng |

Ví dụ Firestore Java:

~~~java
Query firstPage = firestore.collection("orders")
        .whereEqualTo("tenantId", tenantId)
        .orderBy("createdAt", Query.Direction.DESCENDING)
        .orderBy(FieldPath.documentId(), Query.Direction.DESCENDING)
        .limit(50);

ApiFuture<QuerySnapshot> firstFuture = firstPage.get();
QuerySnapshot firstSnapshot = firstFuture.get();

if (!firstSnapshot.isEmpty()) {
    DocumentSnapshot lastDocument =
            firstSnapshot.getDocuments()
                    .get(firstSnapshot.size() - 1);

    Query nextPage = firestore.collection("orders")
            .whereEqualTo("tenantId", tenantId)
            .orderBy("createdAt", Query.Direction.DESCENDING)
            .orderBy(FieldPath.documentId(), Query.Direction.DESCENDING)
            .startAfter(lastDocument)
            .limit(50);
}
~~~

Ví dụ này minh họa native cursor. Trong ứng dụng WebFlux, không gọi get() đồng bộ trên event-loop; dùng API async/reactive phù hợp hoặc chuyển thao tác blocking sang scheduler. Query có thể cần composite index cho tenantId, createdAt và document ID; kiểm tra index error và triển khai index trước khi phát hành.

Với DynamoDB, một trang có thể trả ít item hoặc rỗng do FilterExpression được áp dụng sau khi đọc; vẫn phải tiếp tục nếu LastEvaluatedKey còn tồn tại. Với Cosmos DB, tiếp tục theo continuation token đến khi token rỗng. Không tự giải mã hoặc tự tạo token của provider.

### 2.10. Pagination cho export và batch processing

Export toàn bộ dữ liệu khác với API hiển thị một trang. Không nên tạo một List chứa hàng triệu entity trong heap.

Các lựa chọn:
- Dùng cursor/keyset để đọc từng batch và ghi dần ra file/object storage.
- Dùng Stream<T> nếu store hỗ trợ cursor; luôn đóng stream bằng try-with-resources.
- Dùng batch job hoặc Dataflow/ETL khi dữ liệu rất lớn.
- Ghi checkpoint/cursor sau mỗi batch để job có thể resume.
- Đặt giới hạn số worker và batch size để tránh làm quá tải database.

Nếu batch job phải chạy lại, dùng khóa idempotency hoặc output path theo batch/version để tránh ghi trùng.

## 3. Bộ nhớ đệm (caching)

### 3.1. Cache là bản sao có thời hạn

Cache lưu bản sao của dữ liệu ở nơi truy cập nhanh hơn source of truth. Cache phù hợp nhất khi dữ liệu:
- Được đọc lặp lại.
- Ít thay đổi hơn tần suất đọc.
- Có chi phí truy vấn hoặc network đáng kể.
- Có thể chấp nhận một khoảng freshness được xác định rõ.

Không nên cache chỉ vì một query chậm. Trước hết hãy kiểm tra index, query plan, projection và số lần gọi. Cache một query sai hoặc không có giới hạn có thể chỉ che vấn đề và làm tăng độ phức tạp invalidation.

### 3.2. Các tầng cache

~~~mermaid
flowchart TD
    APP["Spring Boot instance"] --> L1["L1 local cache<br/>Caffeine"]
    L1 -->|"miss"| L2["L2 shared cache<br/>Redis-compatible"]
    L2 -->|"miss"| SOURCE["Database / remote service"]
    SOURCE --> L2
    L2 --> L1
    L1 --> APP
    OTHER["Other application instances"] --> L2
~~~

- **L1 local cache:** nằm trong JVM, độ trễ rất thấp, không cần network. Mỗi instance có bản sao riêng và có thể lệch nhau.
- **L2 shared cache:** cache phân tán như Redis-compatible managed service. Nhiều instance cùng đọc một keyspace; có thêm network hop và cần quản lý connection.
- **Source of truth:** database hoặc service gốc. Cache có thể bị xóa, hết hạn hoặc mất dữ liệu mà ứng dụng vẫn phải khôi phục được từ nguồn.

Có thể dùng cả L1 và L2. Khi đó L1 nên có TTL ngắn hơn và cần cơ chế invalidation/broadcast hoặc chấp nhận stale window rõ ràng.

### 3.3. Cache-aside (lazy loading)

Cache-aside là pattern thường dùng:

1. Ứng dụng đọc cache theo key.
2. Nếu hit, trả dữ liệu.
3. Nếu miss, đọc source of truth.
4. Ghi kết quả vào cache với TTL.
5. Khi dữ liệu nguồn thay đổi, evict hoặc cập nhật key liên quan.

Ưu điểm:
- Chỉ cache dữ liệu thực sự được yêu cầu.
- Cache trống sau restart vẫn không làm mất dữ liệu gốc.
- Dễ áp dụng với database hoặc remote service hiện có.

Nhược điểm:
- Cache miss cần thêm một lần đọc source và một lần ghi cache.
- Cache có thể stale nếu source thay đổi mà không invalidation.
- Nhiều request cùng miss một key có thể đồng thời gọi source, tạo cache stampede.

### 3.4. Spring Cache abstraction

Spring Framework cung cấp abstraction để service không phụ thuộc trực tiếp vào Redis, Caffeine hoặc provider cụ thể. Spring Boot có thể auto-configure CacheManager khi thêm provider tương ứng.

Dependency cơ bản:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
~~~

Bật caching trong configuration:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
~~~

Không cần đặt EnableCaching trực tiếp trên main application class nếu muốn giữ cache optional trong test hoặc profile. Có thể bật trong configuration riêng.

Các annotation chính:

| Annotation | Tác dụng |
| --- | --- |
| Cacheable | Đọc cache trước; cache miss thì chạy method và lưu kết quả |
| CacheEvict | Xóa entry sau thao tác |
| CachePut | Luôn chạy method rồi cập nhật cache với kết quả |
| Caching | Kết hợp nhiều thao tác cache |
| CacheConfig | Chia sẻ cấu hình cache ở cấp class |

### 3.5. Ví dụ cache-aside với @Cacheable

~~~java
@Service
public class ProductReadService {

    private final ProductRepository products;

    public ProductReadService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(
            cacheNames = "productById",
            key = "'tenant:' + #tenantId + ':product:' + #productId")
    public ProductView getProduct(
            String tenantId, UUID productId) {

        return products
                .findByTenantIdAndId(tenantId, productId)
                .map(ProductView::from)
                .orElseThrow(ProductNotFoundException::new);
    }
}
~~~

Key bao gồm tenant ID và product ID. Nếu chỉ dùng product ID, một tenant có thể vô tình nhận dữ liệu cache của tenant khác khi ID không được bảo đảm duy nhất toàn hệ thống.

Nếu kết quả còn phụ thuộc locale, currency, quyền hoặc feature flag, những giá trị đó cũng phải nằm trong cache key hoặc cache phải được tách theo scope phù hợp.

Annotation caching hoạt động qua Spring proxy. Nếu một method trong cùng class gọi trực tiếp method có @Cacheable, lời gọi nội bộ thường không đi qua proxy nên cache advice không được áp dụng. Hãy đặt cached method trong bean riêng hoặc gọi qua bean proxy.

### 3.6. Evict hoặc update cache khi ghi dữ liệu

Ví dụ service cập nhật nguồn dữ liệu:

~~~java
@Service
public class ProductCommandService {

    private final ProductRepository products;

    public ProductCommandService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public Product updateProduct(
            String tenantId, UUID productId, ProductUpdate update) {

        Product product = products
                .findByTenantIdAndId(tenantId, productId)
                .orElseThrow(ProductNotFoundException::new);

        product.apply(update);
        return products.save(product);
    }
}
~~~

Có thể dùng CacheEvict ở boundary thích hợp, nhưng cần chú ý transaction: eviction xảy ra trước khi transaction database commit có thể khiến request khác đọc dữ liệu cũ và cache lại. Với dữ liệu cần đảm bảo thứ tự, phát event sau commit:

~~~java
public record ProductChanged(String tenantId, UUID productId) {
}

@Service
public class ProductCommandService {

    private final ProductRepository products;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductRepository products,
            ApplicationEventPublisher events) {
        this.products = products;
        this.events = events;
    }

    @Transactional
    public void updateProduct(
            String tenantId, UUID productId, ProductUpdate update) {

        Product product = products
                .findByTenantIdAndId(tenantId, productId)
                .orElseThrow(ProductNotFoundException::new);

        product.apply(update);
        products.save(product);

        events.publishEvent(new ProductChanged(tenantId, productId));
    }
}
~~~

Listener evict cache sau khi transaction commit:

~~~java
@Component
public class ProductCacheInvalidator {

    private final CacheManager cacheManager;

    public ProductCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void invalidate(ProductChanged event) {
        Cache cache = cacheManager.getCache("productById");

        if (cache != null) {
            cache.evict(
                    "tenant:" + event.tenantId()
                            + ":product:" + event.productId());
        }
    }
}
~~~

Event listener trong ví dụ chạy trong cùng application process. Nếu dùng L1 local cache trên nhiều instance, cần broadcast invalidation hoặc dựa vào TTL ngắn; event nội bộ một instance không tự xóa cache của các instance khác. Với yêu cầu invalidation bền vững, có thể ghi outbox trong transaction rồi phát message đến các instance sau commit.

### 3.7. TTL và cấu hình cache

TTL (time to live) xác định thời gian một entry được giữ trong cache. TTL phải dựa trên freshness SLA và tần suất thay đổi dữ liệu.

Ví dụ dùng Redis cache provider trong Spring Boot:

~~~yaml
spring:
  cache:
    type: redis
    cache-names:
      - productById
      - productList
      - referenceData
    redis:
      time-to-live: 5m
      use-key-prefix: true
~~~

Key prefix giúp phân biệt cùng một key giữa các cache region. Không tắt prefix nếu tự tạo nhiều cache có thể trùng key.

Nếu cần TTL riêng cho từng cache, cấu hình RedisCacheManagerBuilderCustomizer:

~~~java
import java.time.Duration;

import org.springframework.boot.cache.autoconfigure.RedisCacheManagerBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration
public class RedisCacheTtlConfiguration {

    @Bean
    RedisCacheManagerBuilderCustomizer cacheTtlCustomizer() {
        return builder -> builder
                .withCacheConfiguration(
                        "productById",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofMinutes(5)))
                .withCacheConfiguration(
                        "referenceData",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofHours(1)));
    }
}
~~~

Ví dụ trên giả định Spring Boot đã auto-configure Redis cache provider và Redis connection factory. Nếu dùng Caffeine local cache, có thể cấu hình provider và giới hạn kích thước/TTL:

~~~yaml
spring:
  cache:
    type: caffeine
    caffeine:
      spec: maximumSize=10000,expireAfterWrite=60s
~~~

Cache provider đơn giản dựa trên concurrent map phù hợp để thử nghiệm, nhưng không phải cache production có TTL/eviction/shared state đầy đủ.

### 3.8. Chọn managed cache theo cloud provider

Spring Cache abstraction giúp giữ phần business code độc lập với provider. Hạ tầng cache có thể là:

| Cloud | Managed cache thường gặp | Ghi chú |
| --- | --- | --- |
| AWS | Amazon ElastiCache for Valkey/Redis OSS | Chọn engine, topology, failover và client tương thích |
| Azure | Azure Managed Redis | Dùng dịch vụ hiện được Microsoft khuyến nghị cho workload mới; kiểm tra lộ trình Azure Cache for Redis hiện hữu |
| Google Cloud | Memorystore for Redis hoặc Valkey | Chọn tier, networking, failover và khả năng kết nối từ runtime |

Dù dùng dịch vụ nào, cache vẫn là bản sao có thể bị evict hoặc mất khi failover. Database hoặc service nguồn phải giữ dữ liệu chuẩn.

### 3.9. TTL, cache stampede và thundering herd

Giả sử một key phổ biến hết hạn đúng lúc có 500 request. Nếu mọi request đều cache miss, chúng có thể cùng gọi database và ghi lại cache. Hiện tượng này gọi là cache stampede.

Các cách giảm rủi ro:

- Cacheable với sync = true có thể đồng bộ việc tính cùng một key nếu cache provider hỗ trợ. Kiểm tra giới hạn của provider và annotation khi kết hợp sync.
- Thêm jitter ngẫu nhiên vào TTL để nhiều key không hết hạn cùng lúc.
- Pre-warm key phổ biến trước giờ cao điểm.
- Dùng stale-while-revalidate: trả bản cũ trong một khoảng cho phép trong khi refresh nền.
- Giới hạn số request đồng thời tới source bằng semaphore/bulkhead.
- Với cross-instance stampede lớn, dùng distributed lock có lease và fencing/version nếu thật sự cần; tránh biến cache thành một lock service phức tạp.

Không dùng lock không có timeout. Nếu worker giữ lock bị chết, các request khác có thể bị treo hoặc chờ quá lâu.

### 3.10. Negative caching

Một số key thường xuyên không tồn tại có thể gây nhiều truy vấn lặp lại. Có thể cache kết quả “không tìm thấy” trong thời gian ngắn nếu semantics cho phép.

Cần phân biệt:
- Không tìm thấy thật sự.
- Request không có quyền truy cập.
- Timeout hoặc lỗi database.
- Cache miss.

Không cache lỗi tạm thời như thể dữ liệu không tồn tại. Nếu cache negative result quá lâu, bản ghi mới tạo có thể vẫn bị trả 404 cho đến khi TTL hết hạn.

### 3.11. Cache list và cache trang

Có thể cache một trang kết quả, nhưng key cần bao gồm mọi tham số ảnh hưởng nội dung:

- Tenant/principal scope.
- Filter và search query.
- Sort field/direction.
- Page size.
- Offset hoặc cursor.
- Locale/currency nếu response phụ thuộc.
- API/schema version nếu format thay đổi.

Ví dụ key khái niệm:

~~~text
orders:list:v2:tenant-42:status-PAID:sort-created-desc:size-20:cursor-abc
~~~

Cache page đầu có thể có hit ratio cao; các trang sâu thường ít được truy cập. Không cache mọi page vô hạn. Đặt TTL, giới hạn số entry và theo dõi memory.

Cursor có thể chứa trạng thái dữ liệu. Không dùng cache key có cursor chưa xác minh hoặc cursor thuộc tenant khác. Với cursor token ký số, vẫn cần kiểm tra quyền của request hiện tại.

### 3.12. Khi cache lỗi

Ứng dụng nên quyết định cache có phải dependency bắt buộc hay không:

- Nếu cache chỉ tăng tốc, cache timeout có thể được coi là miss và đọc source theo concurrency limit.
- Nếu cache đang giữ dữ liệu phục vụ session/coordination quan trọng, hành vi fallback phải được thiết kế riêng.
- Không để cache outage tạo một đợt traffic không giới hạn vào database.
- Đặt timeout ngắn, circuit breaker và rate limit cho cache/source.
- Ghi metric cache error riêng với cache miss.

Cache failure không nên âm thầm trả dữ liệu sai hoặc khiến database bị quá tải dây chuyền.

### 3.13. Cache với reactive return type

Spring Cache có thể thích nghi với CompletableFuture, Mono và Flux. Với Mono, giá trị được phát ra sẽ được cache khi hoàn tất. Với Flux, Spring gom toàn bộ phần tử thành một List trước khi lưu cache. Vì vậy, annotation caching trên Flux không phù hợp với stream rất lớn, stream vô hạn hoặc pipeline cần backpressure; hãy cache từng page/batch hoặc dùng một cache strategy reactive được thiết kế riêng.

## 4. Giảm số lần gọi database và dịch vụ khác

### 4.1. Loại bỏ N+1 query

N+1 xảy ra khi lấy danh sách N bản ghi rồi thực hiện thêm một query cho mỗi bản ghi để lấy quan hệ.

Ví dụ không tốt:

~~~java
List<Order> orders = orderRepository.findByTenantId(tenantId);

for (Order order : orders) {
    Customer customer = customerRepository
            .findById(order.getCustomerId())
            .orElseThrow();
    // Build response.
}
~~~

Nếu có 100 order, code có thể tạo 1 query lấy order và 100 query lấy customer.

Các cách xử lý:
- Dùng JOIN FETCH hoặc EntityGraph khi quan hệ phù hợp.
- Dùng projection/DTO để chỉ lấy field cần thiết.
- Lấy danh sách ID rồi dùng một query WHERE id IN (...).
- Dùng batch fetching nếu ORM hỗ trợ.
- Đặt batch size phù hợp và chia batch khi vượt giới hạn database/API.

Ví dụ bulk lookup:

~~~java
List<UUID> customerIds = orders.stream()
        .map(Order::getCustomerId)
        .distinct()
        .toList();

Map<UUID, CustomerSummary> customers =
        customerRepository.findAllById(customerIds)
                .stream()
                .collect(Collectors.toMap(
                        Customer::getId,
                        CustomerSummary::from));
~~~

Sau đó map order với customer trong memory. Cách này giảm số query, nhưng vẫn phải giới hạn kích thước IN list và chỉ lấy các cột cần thiết.

### 4.2. Cẩn thận khi fetch join cùng pagination

Fetch join collection cùng Pageable có thể tạo nhiều row cho một entity gốc và làm database/ORM khó áp dụng limit đúng. Một số trường hợp Hibernate phải đọc nhiều row rồi phân trang trong memory.

Một chiến lược an toàn hơn:

1. Query page ID của entity gốc theo sort ổn định.
2. Query batch toàn bộ entity/relations cần cho các ID đó.
3. Khôi phục thứ tự theo danh sách ID ban đầu.
4. Map sang DTO.

Với collection lớn, cân nhắc query riêng hoặc projection thay vì tải toàn bộ graph.

### 4.3. Bulk API thay cho gọi từng phần tử

Nếu service đích hỗ trợ batch, dùng một request cho nhiều key thay vì một request cho mỗi key.

Ví dụ API nội bộ:

~~~http
POST /customers:batchGet
Content-Type: application/json

{
  "ids": [
    "cus-1001",
    "cus-1002",
    "cus-1003"
  ]
}
~~~

Service trả một map hoặc danh sách customer tương ứng. Bên gọi cần:
- Loại ID trùng trước khi gửi.
- Chia batch theo giới hạn provider.
- Xử lý phần tử không tồn tại.
- Theo dõi partial failure nếu batch API có thể trả kết quả thành công một phần.
- Giữ idempotency cho batch write.

Các dịch vụ cloud có API bulk riêng như DynamoDB BatchGet/BatchWrite, Firestore getAll hoặc các thao tác batch write, và API batch/stream cho data service khác. Đọc giới hạn số item, payload và retry của từng API.

### 4.4. API aggregation và BFF

Một màn hình có thể cần order, customer, asset và pricing. Nếu client gọi bốn service tuần tự, latency tổng gần bằng tổng latency của bốn call.

Có thể tạo API aggregation/BFF:
- Nhận một request từ client.
- Gọi các service cần thiết.
- Batch các key trùng.
- Chỉ trả field cần cho màn hình.
- Áp dụng timeout và giới hạn concurrency.

Aggregation giảm round-trip từ client nhưng không tự giảm số call backend nếu vẫn gọi từng service riêng. Để giảm call thật sự, cần batch API, cache hoặc thay đổi data ownership/read model.

### 4.5. Request coalescing và deduplication

Trong một request, nhiều component có thể cùng yêu cầu một customer hoặc configuration. Hãy gom các key trùng và chỉ gọi source một lần.

Trong nhiều request đồng thời, nhiều caller có thể cùng cache miss một key. Cacheable với sync = true có thể giúp single-flight ở provider hỗ trợ. Với logic phức tạp, có thể dùng một in-flight future map theo key và xóa entry sau khi future hoàn tất.

Nguyên tắc:
- Coalesce theo key đầy đủ, gồm tenant/security scope.
- Không chia sẻ kết quả giữa người dùng có quyền khác nhau.
- Không giữ future lỗi vĩnh viễn trong map.
- Đặt timeout và cleanup.
- Không dùng một global lock cho mọi key.

### 4.6. Tái sử dụng HTTP client và connection pool

Không tạo một RestClient, WebClient hoặc SDK client mới cho từng request. Tạo bean dùng chung và tái sử dụng connection pool.

Ví dụ cấu hình WebClient qua builder được Spring quản lý:

~~~java
@Configuration
public class RemoteClientConfiguration {

    @Bean
    WebClient catalogWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.internal")
                .build();
    }
}
~~~

Service inject client:

~~~java
@Service
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient catalogWebClient) {
        this.webClient = catalogWebClient;
    }

    public Mono<ProductView> getProduct(UUID id) {
        return webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(ProductView.class);
    }
}
~~~

Trong production, cấu hình connection pool và timeout qua HTTP connector phù hợp. Theo dõi:
- Max connections và pending acquire.
- Connect timeout.
- Response/read timeout.
- Keep-alive.
- DNS resolution.
- TLS handshake.
- Connection reuse và pool saturation.

Đặt ứng dụng và managed service trong region/network path phù hợp để tránh latency liên vùng. Đừng mở connection rồi đóng lại sau mỗi lần gọi.

### 4.7. HTTP caching và conditional request

Nếu service đích hỗ trợ ETag, client có thể gửi If-None-Match. Khi dữ liệu chưa đổi, server trả 304 Not Modified và không gửi lại response body.

Conditional request giảm bandwidth và serialization; nó vẫn là một network round-trip. Muốn giảm số lần gọi, kết hợp với local/shared cache và TTL.

Không dùng ETag thay cho authorization hoặc version control nghiệp vụ. Cache HTTP response phải tôn trọng Cache-Control, Vary, user scope và thông tin nhạy cảm.

### 4.8. Song song hóa có giới hạn

Nếu các service call độc lập, gọi song song có thể giảm latency so với gọi tuần tự. Nhưng số call không giảm và tải downstream có thể tăng.

Dùng bounded concurrency, timeout tổng và bulkhead. Không tạo hàng nghìn future cùng lúc cho một request. Khi một dependency chậm, không để toàn bộ thread/connection pool bị giữ.

Với reactive pipeline, có thể dùng Mono.zip cho một số call độc lập; đặt timeout và fallback phù hợp. Đừng dùng parallel chỉ để che một API chatty mà chưa batch được.

### 4.9. Retry không phải cách giảm call

Retry giúp vượt lỗi tạm thời nhưng làm tăng số lần gọi. Nếu 1.000 request đồng thời đều retry ba lần khi dependency đang lỗi, hệ thống có thể tự khuếch đại sự cố.

Nguyên tắc:
- Chỉ retry lỗi tạm thời như timeout, connection reset hoặc một số HTTP 5xx.
- Không retry lỗi validation, permission denied hoặc business rejection.
- Chỉ retry write khi operation idempotent hoặc có idempotency key.
- Dùng exponential backoff và jitter.
- Giới hạn số lần retry và tổng deadline.
- Dùng circuit breaker để ngừng gọi dependency đang lỗi.
- Dùng bulkhead để cô lập tài nguyên cho từng dependency.

Spring Cloud CircuitBreaker có thể tích hợp Resilience4j và các implementation khác. Chọn đúng implementation theo blocking/reactive stack của ứng dụng.

## 5. Kết hợp pagination và cache

### 5.1. Cache trang đầu, keyset cho phần tiếp theo

Một danh sách có thể có pattern:
- Phần lớn người dùng chỉ xem trang đầu.
- Một nhóm nhỏ đi sâu hơn.
- Dữ liệu mới thường xuất hiện ở đầu danh sách.

Chiến lược có thể là:
1. Cache trang đầu với TTL ngắn.
2. Dùng keyset cursor cho các trang tiếp theo.
3. Evict trang đầu khi có bản ghi mới.
4. Không cache mọi cursor vô hạn.
5. Giới hạn page size và số trang có thể lưu.

Cách này thường phù hợp hơn cache toàn bộ danh sách hoặc cache tất cả page offset.

### 5.2. Cache query result theo fingerprint

Một query page có thể được định danh bằng fingerprint của:
- Tenant.
- Filter.
- Sort.
- Page size.
- Cursor/offset.
- Version schema/response.

Khi filter hoặc sort thay đổi, cache key phải thay đổi. Nếu không, người dùng có thể nhận dữ liệu từ query khác.

### 5.3. Freshness và invalidation

Định nghĩa freshness theo loại dữ liệu:

| Dữ liệu | Chiến lược gợi ý |
| --- | --- |
| Danh mục ít đổi | TTL dài hơn, refresh nền |
| Product detail | TTL ngắn/vừa và evict khi update |
| Giá và tồn kho | TTL ngắn hoặc đọc source theo yêu cầu |
| Permission/role | TTL ngắn, invalidation chặt |
| Dashboard aggregate | TTL theo lịch refresh, hiển thị thời điểm dữ liệu |
| Reservation/payment status | Không dựa vào cache stale để quyết định giao dịch |

Đối với dữ liệu giao dịch quan trọng, cache chỉ phục vụ read optimization khi nghiệp vụ cho phép stale read. Các quyết định ghi/checkout phải được xác minh lại ở source of truth.

## 6. Bảo mật và tính đúng đắn

### 6.1. Cache key không được làm rò dữ liệu tenant

Cache key phải phản ánh scope dữ liệu. Nếu response phụ thuộc:
- Tenant.
- User hoặc role.
- Locale/currency.
- Feature entitlement.
- Data residency region.

thì key hoặc cache region phải tách theo các yếu tố đó.

Không cache response cá nhân hóa trong một key dùng chung cho mọi user. Không đưa access token, secret hoặc PII vào key có thể xuất hiện trong monitoring/log.

### 6.2. Serialization và schema version

Với distributed cache:
- Dùng DTO ổn định thay vì serialize entity ORM có lazy proxy.
- Chọn serializer có format/version rõ ràng.
- Tránh deserialize Java native object từ nguồn không tin cậy.
- Có kế hoạch xử lý cache entry cũ khi deploy schema mới.
- Có thể thêm version vào cache name/key để rollout an toàn.

Cache là dữ liệu tạm; deploy mới phải có thể bỏ cache cũ và nạp lại từ source.

### 6.3. Quyền truy cập và network

Managed cache thường nằm trong private network. Cấu hình:
- Private endpoint/VPC/VNet hoặc private service access.
- TLS/in-transit encryption khi được hỗ trợ và yêu cầu.
- Authentication/ACL hoặc identity integration của provider.
- Secret được lưu trong secret manager.
- Least privilege và network allowlist.
- Không mở cache trực tiếp ra Internet nếu không có yêu cầu được kiểm soát.

### 6.4. Cache không phải database bền vững

Không dùng cache làm nơi lưu duy nhất cho:
- Payment ledger.
- Reservation state.
- Inventory source of truth.
- Audit record bắt buộc.
- Event chưa được persist.

Failover, eviction, flush, restart hoặc scale operation có thể làm mất cache entry. Ứng dụng phải phục hồi được từ database hoặc hệ thống nguồn.

## 7. Đo lường và kiểm thử hiệu năng

### 7.1. Metrics cần theo dõi

**Pagination**
- Page size trung bình và tối đa.
- Offset depth.
- Query latency theo page/cursor.
- Count query latency.
- Rows scanned/returned.
- Cursor invalid/expired rate.

**Cache**
- Hit/miss ratio theo cache name.
- Eviction và expiration count.
- Cache operation latency/error.
- Memory usage và key cardinality.
- Invalidation lag.
- Origin request khi cache miss.

**Service calls**
- Calls/request theo dependency.
- Retry count và timeout rate.
- Connection pool wait/pending acquire.
- Batch size và partial failure.
- Circuit breaker open duration.
- Payload size và serialization time.

Không chỉ xem hit ratio tổng. Cache hit ratio cao nhưng cache miss quá chậm hoặc key cardinality tăng vô hạn vẫn có thể gây vấn đề.

### 7.2. Distributed tracing

Gắn trace/span cho:
- HTTP request vào Spring Boot.
- Database query.
- Cache get/set/evict.
- HTTP/gRPC client call.
- Messaging publish/consume.
- Batch job hoặc export.

Trace giúp tìm đoạn nào tạo nhiều call và xác định latency nằm ở ứng dụng, network, database hay provider.

### 7.3. Load test với cache cold và hot

Một bài test nên có các trạng thái:
1. Cold cache sau deploy/restart.
2. Warm cache với traffic bình thường.
3. Hot key có nhiều request đồng thời.
4. Cache provider tạm thời không khả dụng.
5. Source database tăng latency.
6. Cache eviction hoặc failover.
7. Dữ liệu thay đổi liên tục trong khi client đang phân trang.

Dùng dữ liệu có phân bố thực tế, gồm key phổ biến và key hiếm. Test một cache toàn hit không phản ánh hành vi production.

### 7.4. Đánh giá cost

Cache thêm chi phí:
- Instance/cluster và memory.
- Network traffic.
- Serialization/deserialization.
- Vận hành, monitoring và invalidation.
- Stale data và xử lý lỗi.

Batching cũng có trade-off: request lớn hơn có thể tăng memory và thời gian xử lý một batch; partial failure có thể cần retry từng phần. Chọn batch size theo giới hạn provider và benchmark.

So sánh tổng chi phí trước/sau:
- Database read giảm bao nhiêu?
- Remote call giảm bao nhiêu?
- Cache cost tăng bao nhiêu?
- Latency p95/p99 thay đổi thế nào?
- Tỷ lệ stale/error có tăng không?

## 8. Quy trình tối ưu một API thực tế

Giả sử endpoint GET /orders p95 cao và database có nhiều query:

1. **Đo baseline:** trace request, đếm query, xem execution plan và remote calls.
2. **Giới hạn kết quả:** đặt page size tối đa và sort ổn định.
3. **Chọn pagination:** Page nếu cần total count; Slice nếu chỉ cần next; keyset nếu dữ liệu lớn và duyệt tuần tự.
4. **Loại N+1:** projection, batch lookup hoặc entity graph phù hợp.
5. **Cache dữ liệu đọc lặp:** cache danh mục/customer summary theo tenant và TTL.
6. **Giảm call trùng:** deduplicate IDs và batch service API.
7. **Tái sử dụng client:** connection pool, timeout và region.
8. **Bảo vệ dependency:** concurrency limit, circuit breaker và retry có giới hạn.
9. **Kiểm tra freshness:** invalidation sau commit và test nhiều instance.
10. **Load test lại:** so sánh latency, calls/request, cache hit, DB load và cost.

Không bật cache trước khi hiểu semantics của dữ liệu. Không đổi offset sang cursor mà không có sort ổn định và index.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Trang sâu rất chậm | Offset lớn | Keyset/cursor và index theo sort |
| Bản ghi lặp giữa các trang | Sort không duy nhất hoặc dữ liệu thay đổi | Thêm tie-breaker ID, dùng cursor ổn định |
| Page endpoint chậm dù chỉ trả 20 row | Count query đắt | Dùng Slice/List hoặc tối ưu count |
| Trang bị thiếu item | Cursor sai hoặc filter thay đổi | Bind cursor với filter/sort fingerprint |
| Memory tăng khi export | Materialize toàn bộ List | Stream/Window/batch và checkpoint |
| Database query tăng theo số row | N+1 | Batch query, projection, entity graph |
| Cache hit nhưng trả sai tenant | Cache key thiếu tenant/scope | Bổ sung tenant/user/role vào key |
| Dữ liệu stale sau update | Thiếu invalidation hoặc TTL quá dài | Evict sau commit, outbox/broadcast |
| Database quá tải khi cache restart | Cache stampede | Single-flight, jitter, pre-warm, concurrency limit |
| Redis connection tăng liên tục | Tạo client/connection mỗi request hoặc idle connection | Tái sử dụng client, pool và idle timeout |
| Cache memory đầy | TTL thiếu, key cardinality lớn, value quá lớn | TTL, eviction policy, giới hạn kích thước |
| Retry làm tăng tải khi dependency lỗi | Retry không giới hạn hoặc không có jitter | Retry budget, backoff, circuit breaker |
| Batch API trả partial failure | Batch quá lớn hoặc provider giới hạn item | Chia batch, retry phần lỗi, idempotency |
| Parallel fan-out làm downstream quá tải | Không giới hạn concurrency | Bulkhead, semaphore và timeout |
| Cache page trả response khác filter | Cache key thiếu query parameters | Key theo filter/sort/cursor/version |

## 10. Bài tập thực hành

### Bài A — Offset và Slice

Tạo endpoint liệt kê reservation bằng Pageable. Đo query count và latency khi trả Page so với Slice. Giải thích chi phí count query.

### Bài B — Keyset pagination

Tạo query theo createdAt DESC, id DESC. Viết keyset cursor, tạo index tương ứng và duyệt ít nhất 100.000 bản ghi. So sánh latency ở đầu và cuối dataset với offset pagination.

### Bài C — Cursor API

Thiết kế response có items, nextCursor, hasMore. Ký cursor và xác minh cursor không thể dùng cho tenant hoặc filter khác.

### Bài D — Native continuation token

Thực hành một dịch vụ có cursor native như Firestore, DynamoDB hoặc Cosmos DB. Xử lý trang rỗng có token và chỉ dừng khi token báo hết dữ liệu.

### Bài E — Spring Cache

Bật EnableCaching, cache product detail bằng Cacheable, cập nhật bằng transaction và evict sau commit. Kiểm tra nhiều lần đọc cùng key chỉ gọi repository một lần khi cache hit.

### Bài F — L1 và L2 cache

Dùng Caffeine cho L1 và Redis-compatible cache cho L2. Chạy hai application instance, cập nhật một product và kiểm tra invalidation giữa các instance.

### Bài G — Cache stampede

Tạo nhiều request đồng thời cùng đọc một key chưa có cache. So sánh không coalesce, sync=true và TTL jitter. Đo số query xuống database.

### Bài H — N+1 và batch

Viết một endpoint tải 50 order và customer. Đo query count trước/sau khi dùng findAllById hoặc projection/batch query.

### Bài I — HTTP client reuse

Tạo WebClient bean dùng chung, cấu hình connection pool/timeout. So sánh với cách tạo client mới cho từng request; quan sát connection reuse và pending acquire.

### Bài J — Resilience và cost

Giả lập dependency chậm hoặc lỗi. Cấu hình timeout, retry có giới hạn, circuit breaker và bulkhead. Đo calls/request, p95 và số lỗi khi tải tăng.

### Câu hỏi tự kiểm tra

1. Offset pagination hoạt động như thế nào?
2. Vì sao offset sâu có thể tốn kém?
3. Vì sao sort cần một tie-breaker duy nhất?
4. Page khác Slice ở metadata và query cost nào?
5. Khi nào nên dùng Window<T>?
6. Keyset pagination cần những sort key nào?
7. Vì sao keyset sort field nên không null?
8. Cursor token cần gắn với filter và tenant như thế nào?
9. DynamoDB dùng LastEvaluatedKey ra sao?
10. Vì sao DynamoDB có thể trả trang rỗng nhưng vẫn có key tiếp tục?
11. Firestore dùng startAfter để làm gì?
12. Cosmos DB continuation token có vai trò gì?
13. Cache-aside gồm các bước nào?
14. Spring Cacheable, CacheEvict và CachePut khác nhau ra sao?
15. Vì sao cache key cần tenant ID và authorization scope?
16. TTL quá dài có rủi ro gì?
17. Cache stampede là gì và cách giảm?
18. Vì sao eviction nên diễn ra sau database commit?
19. Local cache khác shared cache ở consistency như thế nào?
20. N+1 query là gì và cách loại bỏ?
21. Khi nào nên dùng batch API?
22. Vì sao không tạo HTTP client mới cho mỗi request?
23. Parallel call có làm giảm số lần gọi không?
24. Vì sao retry có thể khuếch đại sự cố?
25. Metrics nào chứng minh tối ưu pagination/cache/call reduction có hiệu quả?

**Kết quả mong đợi:** người học thiết kế được pagination phù hợp cho SQL và managed datastore, dùng Spring Data Page/Slice/Window, triển khai cache-aside và invalidation với Spring Cache, chọn local/shared cache theo workload, loại N+1 bằng batching, tái sử dụng client/connection pool, giảm request trùng và đo được hiệu quả về latency, số lần gọi, tài nguyên và chi phí.

## Tài liệu tham khảo

- [Spring Data Commons — Scrolling and keyset filtering](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [Spring Data JPA — Paging, sorting and query methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Framework — Annotation-based caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Cloud CircuitBreaker](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Amazon DynamoDB — Paginating query results](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html)
- [Firestore — Paginate data with query cursors](https://docs.cloud.google.com/firestore/native/docs/query-data/query-cursors)
- [Azure Cosmos DB — Pagination and continuation tokens](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/query/pagination)
- [BigQuery — Paging query results](https://docs.cloud.google.com/bigquery/docs/paging-results)
- [Amazon ElastiCache — Caching strategies](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/Strategies.html)
- [Azure Architecture Center — Caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- [Google Cloud Memorystore — Redis best practices](https://docs.cloud.google.com/memorystore/docs/redis/general-best-practices)


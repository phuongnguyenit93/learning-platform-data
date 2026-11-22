# Điều kiện dùng bộ nhớ đệm cấp hai và chọn bộ cung cấp tương thích trong Hibernate ORM

## 1. Bài toán: cùng một dữ liệu tham chiếu được đọc hàng nghìn lần

Giả sử một ứng dụng bán hàng dùng Hibernate ORM. Mỗi request hiển thị đơn hàng đều cần tên quốc gia giao hàng, nhóm sản phẩm hoặc thông tin một loại thuế suất tham chiếu. Những dữ liệu đó được đọc thường xuyên nhưng hiếm khi thay đổi.

Mã nghiệp vụ có thể gọi:

~~~java
Country country = entityManager.find(Country.class, countryId);
~~~

Khi mỗi HTTP request mở một persistence context mới, Hibernate thường phải tìm Country lại. Nếu Country có trong cache của **Session hiện tại** thì không cần SQL; nhưng object ở Session trước không đương nhiên tồn tại trong Session mới.

Hibernate có cơ chế **bộ nhớ đệm cấp hai (second-level cache, L2 cache)** để một phần dữ liệu persistent được chia sẻ giữa nhiều Session/EntityManager thuộc cùng SessionFactory. Với provider phù hợp, yêu cầu đọc lặp lại có thể được phục vụ từ cache thay vì luôn đi tới cơ sở dữ liệu.

Tuy nhiên câu hỏi quan trọng không phải “bật cache thế nào?” mà là:

> Dữ liệu nào nên được cache, yêu cầu nhất quán đến mức nào, và provider nào thật sự tương thích với phiên bản Hibernate, transaction và kiến trúc triển khai?

Nếu chọn sai, L2 cache có thể làm ứng dụng **đọc dữ liệu cũ**, tốn heap, khó debug, giảm hiệu năng hoặc gây vấn đề khi chạy nhiều instance. Với tồn kho hay số dư tiền, trả dữ liệu cũ có thể gây hậu quả nghiêm trọng hơn chi phí thêm một query.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt first-level cache, second-level cache, query cache và cache ở tầng ứng dụng.
2. Nhận biết điều kiện để L2 cache mang lại lợi ích thực tế.
3. Quyết định entity, collection và dữ liệu nào **không nên** cache.
4. Phân biệt các chiến lược READ_ONLY, NONSTRICT_READ_WRITE, READ_WRITE và TRANSACTIONAL.
5. Hiểu vai trò của @Cacheable, @Cache và SharedCacheMode.
6. Chọn provider theo Hibernate version, Java/Jakarta/JCache, cấu trúc multi-node và transaction.
7. Cấu hình minh họa Hibernate JCache cùng provider Ehcache 3.
8. Kiểm soát cache region, TTL, dung lượng, eviction, dữ liệu thay đổi ngoài ORM và query cache.
9. Đo hit/miss/put, SQL và latency trong các Session độc lập.
10. Thiết kế integration test và phương án rollback khi triển khai cache vào production.

Bài viết dùng Java 17+, Jakarta Persistence và Hibernate ORM 6.x làm ngữ cảnh minh họa. Tên artifact, property, API SPI và khả năng hỗ trợ của từng cache provider có thể thay đổi theo phiên bản. Khi áp dụng, phải kiểm tra **ma trận tương thích của các phiên bản cụ thể**; không chỉ dựa vào việc một thư viện có chữ “cache” trong tên.

## 2. Bốn phạm vi cache rất dễ bị nhầm

Trước khi chọn provider, cần xác định dữ liệu được giữ ở tầng nào.

| Tầng | Phạm vi | Vai trò | Có tự động chia sẻ giữa các request không? |
|---|---|---|---|
| Persistence context / first-level cache (L1) | Một Session/EntityManager | Identity map, theo dõi entity managed và dirty checking | Không, nếu request có Session khác |
| Second-level cache (L2) | SessionFactory và cơ chế vùng của provider | Giữ cached entity/collection/natural-id data giữa các Session | Có trong phạm vi provider hỗ trợ |
| Hibernate query result cache | Các query đủ điều kiện, phối hợp với Hibernate cache regions | Tái sử dụng kết quả truy vấn đã cache khi còn hợp lệ | Có khi bật và query opt-in |
| Spring Cache/Redis/application cache | Tầng service/application | Cache DTO, response hoặc giá trị tự định nghĩa | Tùy cấu hình ứng dụng |

L1 **luôn là thành phần cốt lõi của persistence context**. Khi một entity đã được tải và đang managed trong cùng Session, Hibernate thường trả lại cùng instance theo khóa định danh. L2 không thay thế L1.

### 2.1. Đường đọc dữ liệu theo ID

~~~mermaid
flowchart TD
    A[Session.find Country theo ID] --> B{Có entity trong L1?}
    B -->|Có| C[Trả managed instance]
    B -->|Không| D{Entity đủ điều kiện dùng L2?}
    D -->|Không| G[SELECT từ database]
    D -->|Có| E{L2 có entry hợp lệ?}
    E -->|Hit| F[Dựng/hydrate managed entity trong Session]
    E -->|Miss| G
    G --> H[Hydrate entity, cân nhắc đưa entry vào L2]
    H --> F
~~~

Sơ đồ là mô hình khái quát. Thực tế còn phụ thuộc cache mode, access strategy, inheritance, fetch plan, locking, provider và thời điểm transaction hoàn tất.

Một **L2 hit không có nghĩa ứng dụng nhận lại cùng object Java** đã được một Session khác dùng trước đó. Hibernate tái tạo hoặc đồng bộ trạng thái entity cho persistence context hiện tại; identity của managed object gắn với Session đó. L2 không phải một kho chứa object entity đang managed để nhiều thread cùng sửa trực tiếp.

### 2.2. L2 và query cache khác nhau

Nếu gọi:

~~~java
entityManager.find(Country.class, 42L);
~~~

Hibernate có thể tra entity L2 cache theo ID nếu Country được cache.

Nhưng truy vấn:

~~~hql
select c
from Country c
where c.isoCode = :code
~~~

không mặc nhiên được cache kết quả chỉ vì Country được cache ở L2. Hibernate vẫn có thể phải chạy query để xác định những ID nào khớp điều kiện. **Query cache là cơ chế riêng**, cần bật và đánh dấu các query phù hợp.

### 2.3. L2 không thay thế transaction hoặc database constraints

Cache có thể tránh một số SELECT, nhưng không phải nguồn sự thật cho:

- Kiểm tra unique key.
- Khóa hàng để ngăn ghi đồng thời.
- Bảo đảm số dư và tồn kho không âm.
- Atomic compare-and-swap/version check.
- Referential integrity và transaction durability.

Các quy tắc này vẫn cần được thực thi bằng transaction và ràng buộc database phù hợp.

## 3. Khi nào cache cấp hai thực sự có lợi?

Trước hết, cần một giả thuyết có thể đo được:

> Cùng một entity/collection được đọc nhiều lần ở những Session khác nhau; dữ liệu ít thay đổi; giảm round-trip tới database đáng giá hơn chi phí quản lý cache.

### 3.1. Tỷ lệ đọc so với ghi cao

Các ứng viên thường tốt:

- Danh mục quốc gia, tỉnh/thành, mã đơn vị đo.
- Bảng phân loại sản phẩm ít thay đổi.
- Nhóm cấu hình tham chiếu tương đối ổn định.
- Quy tắc nghiệp vụ có phiên bản rõ, ít cập nhật.
- Metadata dùng lặp lại trên nhiều request và có kích thước vừa phải.

Những dữ liệu này thường có **read-many/write-rarely**. Nếu 10.000 request cùng đọc một Country ID, một cache hit có thể giúp giảm nhiều SELECT lặp lại sau giai đoạn warm-up.

Ngược lại, nếu mỗi lần đọc theo một ID chưa từng thấy, cache có tỷ lệ miss cao và tốn bộ nhớ mà không giảm được nhiều query.

### 3.2. Dữ liệu đủ ổn định

Không có một ngưỡng “ít hơn X lần update/giờ là an toàn” áp dụng cho mọi hệ thống. Cần quan tâm:

- Dữ liệu có thay đổi trong giờ cao điểm không?
- Nếu đổi, cần các node nhìn thấy thay đổi ngay hay có thể trễ?
- Có cập nhật bằng JDBC, native SQL, ETL, stored procedure hoặc ứng dụng khác ngoài Hibernate không?
- Một cached value cũ gây lỗi giao diện hay vi phạm nghiệp vụ?
- Có cơ chế eviction/invalidation đáng tin cậy không?

Đặc biệt, “ít thay đổi” không đồng nghĩa “chấp nhận đọc cũ”. Một cấu hình thay đổi mỗi năm nhưng liên quan đến quyền truy cập hoặc nghĩa vụ pháp lý có thể vẫn không phù hợp với cache lỏng lẻo.

### 3.3. Tập dữ liệu nóng vừa với bộ nhớ

Nếu một bảng có 50 triệu entity nhưng mỗi ngày chỉ đọc lặp lại vài trăm khóa, cache có thể hữu ích khi giới hạn dung lượng đúng. Nếu mọi ID đều được đọc đúng một lần, L2 thường không mang lại hit đáng kể.

Đo:

- Số key duy nhất được truy cập trong một khoảng thời gian.
- Phân bố nóng/lạnh (top 1%, 10% keys).
- Kích thước trung bình của một cache entry.
- Tần suất miss và eviction.
- Thời gian sống thực sự của dữ liệu trong cache.

Đừng đặt cache capacity theo số rows trong cả bảng khi chỉ một working set nhỏ có ý nghĩa.

### 3.4. L2 giúp giảm chi phí thật, không chỉ số SQL trên giấy

Chi phí cache lookup gồm hash/key creation, locking, serialization/deserialization, network (nếu distributed), GC, invalidation và observability. L2 hiệu quả khi chi phí đọc từ cache **thấp hơn đáng kể** chi phí đọc từ DB với tần suất hit đủ cao.

Ví dụ **giả định**, không phải benchmark:

~~~text
DB SELECT cho một entity:                 8 ms
Cache hit + hydrate:                      0,5 ms
Cache miss rồi đọc database:              8,5 ms
Hit rate giả định:                        90%

Trung bình gần đúng = 0,9 × 0,5 + 0,1 × 8,5
                   = 1,3 ms
~~~

Tính toán đơn giản này chưa bao gồm write invalidation, warm-up, cache cluster, memory pressure và tải hỗn hợp. Nó chỉ minh họa lý do **tỷ lệ hit** và **chi phí trên mỗi hit** đều quan trọng.

## 4. Khi nào không nên bật L2 cache?

Không coi bộ nhớ đệm là tối ưu mặc định cho toàn bộ entity.

| Loại dữ liệu | Rủi ro | Hướng phù hợp hơn |
|---|---|---|
| Inventory/available stock cập nhật liên tục | Đọc tồn kho cũ dẫn đến quyết định sai | Transaction/locking hoặc read model có semantics rõ |
| Số dư ví, tài khoản, hạn mức tức thời | Sai lệch tiền và concurrency | Query/transaction nhất quán, version, constraint |
| Entity update rất thường xuyên | Invalidation liên tục, tỷ lệ hit thấp | Không cache hoặc đánh giá read model khác |
| Entity chỉ được đọc một lần | Cache miss nhiều, lãng phí memory | Đọc trực tiếp DB |
| BLOB/CLOB/JSON rất lớn | Entry chiếm bộ nhớ, serialization đắt | Projection và cache chuyên biệt khi cần |
| Dữ liệu theo user nhạy cảm/quyền thay đổi nhanh | Khó bảo đảm authorization và revoke | Áp dụng quyền ở mỗi access; cân nhắc không cache |
| Collection lớn, biến động liên tục | Entry nặng, bị invalidation nhiều | Truy vấn child phân trang |
| Bảng thường xuyên update bằng hệ thống khác | Không có eviction đáng tin cậy | Không cache hoặc có đồng bộ cache bắt buộc |

### 4.1. Cẩn thận với trạng thái tài chính

Một cached PaymentStatus dùng để hiển thị “Đã thanh toán” không nên tự trở thành căn cứ duy nhất để chuyển hàng hoặc chốt thanh toán. Dù READ_WRITE strategy được sử dụng, hệ thống vẫn cần xác minh transaction/version và điều kiện trạng thái ở database theo nghiệp vụ.

### 4.2. Không cache chỉ để che N+1

Nếu code chạy 100 lần:

~~~java
for (Order order : orders) {
    order.getCustomer().getName();
}
~~~

thì 100 lazy lookups có thể được L2 cache trả lại sau warm-up, khiến số SQL giảm. Nhưng fetch plan vẫn chưa được thiết kế tốt. Khi cache lạnh, áp lực SQL có thể quay lại. Nên sửa N+1 bằng to-one fetch join, DTO projection, batch fetching hoặc fetch plan phù hợp trước, rồi đo xem L2 có giá trị bổ sung không.

### 4.3. Cache không sửa thiếu index

Một query chậm vì điều kiện WHERE không có index vẫn có thể chậm mỗi khi miss. Query cache chỉ che một phần triệu chứng nếu request lặp cùng tham số và dữ liệu không thay đổi. Cần xem SQL plan và index trước khi quyết định cache.

## 5. Các điều kiện tiên quyết trước khi chọn provider

Trước khi thêm thư viện cache, trả lời:

1. **Hibernate phiên bản nào?** 5.x, 6.x và các minor version có SPI/adapter và dependency khác.
2. **Java/Jakarta version nào?** Có những package javax.* vẫn tồn tại ở JCache dù JPA đã chuyển sang jakarta.*.
3. **Ứng dụng có bao nhiêu node?** Một JVM, nhiều replica, auto-scaling, blue-green deployment?
4. **Consistency cần gì?** Immutable, best-effort, invalidation sau update, transaction-aware?
5. **Cập nhật dữ liệu qua những đường nào?** Hibernate managed entity, HQL bulk DML, native SQL, job, service khác?
6. **Cache lưu ở đâu?** Heap trong JVM, off-heap, disk, cluster/distributed store?
7. **Dung lượng và TTL ra sao?** Có giới hạn memory, eviction policy, khu vực dữ liệu nóng?
8. **Cách đo/giám sát?** Hit/miss/put/evict, memory, latency, cache unavailable?
9. **Khả năng vận hành?** Khởi động lạnh, schema migration, rolling deployment, sự cố provider?
10. **Kiểm thử tương thích?** Module integration thực sự chạy với Hibernate và provider sẽ triển khai?

Nếu chưa trả lời được hai câu về **consistency** và **đường cập nhật ngoài ORM**, chưa nên bật L2 cho entity nhạy cảm.

## 6. SharedCacheMode của JPA và phạm vi entity được cache

Jakarta Persistence có chính sách chia sẻ cache được biểu diễn bằng SharedCacheMode. Các chế độ có ý nghĩa chung:

| SharedCacheMode | Ý nghĩa khái quát |
|---|---|
| ALL | Tất cả entity đủ điều kiện được cache theo policy/provider |
| NONE | Không cache entity bằng shared cache theo policy JPA |
| ENABLE_SELECTIVE | Chỉ cache entity được opt-in, ví dụ @Cacheable(true) |
| DISABLE_SELECTIVE | Mặc định cache, trừ entity opt-out bằng @Cacheable(false) |
| UNSPECIFIED | Để provider xác định hành vi mặc định |

Với hệ thống muốn triển khai thận trọng, **ENABLE_SELECTIVE** là một lựa chọn tốt: chỉ những entity đã được đánh giá và khai báo mới đủ điều kiện.

Ví dụ property JPA thường dùng qua Hibernate:

~~~properties
jakarta.persistence.sharedCache.mode=ENABLE_SELECTIVE
~~~

Khi dùng Spring Boot, cấu hình persistence unit có thể được quản lý qua các property hoặc cách thiết lập EntityManagerFactory. Cần kiểm tra xem framework thật sự truyền SharedCacheMode vào persistence unit như mong muốn; không chỉ đặt một property rồi mặc định mọi provider hiểu như nhau.

### 6.1. @Cacheable

~~~java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
@Cacheable(true)
public class Country {
    @Id
    private Long id;
}
~~~

@Cacheable là annotation của Jakarta Persistence, xác định tính đủ điều kiện sử dụng shared cache theo SharedCacheMode. Nó không tự chọn cache provider hay bảo đảm một vùng cache có TTL/dung lượng phù hợp.

### 6.2. Hibernate @Cache

Hibernate cung cấp annotation để chọn access strategy và region:

~~~java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;
import org.hibernate.annotations.Immutable;

@Entity
@Immutable
@Cacheable(true)
@Cache(
    usage = CacheConcurrencyStrategy.READ_ONLY,
    region = "reference.countries"
)
public class Country {
    @Id
    private Long id;

    private String isoCode;
    private String displayName;
}
~~~

Trong ví dụ:

- @Cacheable(true): entity đủ điều kiện trong chính sách JPA chọn lọc.
- @Cache(usage = READ_ONLY): Hibernate dùng chiến lược vùng cache cho dữ liệu bất biến.
- region: tên vùng cache cần khớp cấu hình provider.
- @Immutable: mô tả entity được Hibernate coi là không được update theo dirty checking thông thường.

**@Immutable không thay thế giới hạn nghiệp vụ ở mọi write path**: database, native SQL hoặc ứng dụng khác vẫn có thể đổi bảng nếu được phép. Dữ liệu bên ngoài thay đổi sẽ cần eviction/reload hoặc chiến lược deployment riêng.

### 6.3. Không bật ALL khi chưa định cỡ

Bật cache mọi entity có thể đưa nhiều dữ liệu ít được tái sử dụng vào heap, gây churn và invalidate liên tục. Một số association hoặc lazy attributes còn có hành vi cache khác dự kiến. Bắt đầu từ vài region dễ đo và ít rủi ro, sau đó mở rộng dựa trên số liệu.

## 7. Các cache concurrency strategy

Hibernate không chỉ cần một chỗ lưu key-value; nó cần **access strategy** xác định cách dữ liệu cache tương tác với transaction và update.

| Strategy | Ngữ cảnh phù hợp | Khả năng nhất quán và lưu ý |
|---|---|---|
| READ_ONLY | Dữ liệu bất biến sau khi tạo | Thường đơn giản, hiệu quả; không dành cho update entity thường xuyên |
| NONSTRICT_READ_WRITE | Read-mostly, chấp nhận một khoảng đọc cũ | Eviction/invalidation không có bảo đảm strict read-after-write trong mọi tình huống |
| READ_WRITE | Entity thay đổi và muốn cơ chế đồng bộ cache với ORM update | Có protocol nhất quán mạnh hơn nonstrict, nhưng không thay transaction DB |
| TRANSACTIONAL | Cần phối hợp transaction cấp cache và database | Chỉ dùng với provider và transaction manager có hỗ trợ tương ứng |

Không chọn strategy chỉ vì tên có vẻ “an toàn”. Provider phải thật sự hỗ trợ chiến lược đó trên Hibernate version đang chạy.

### 7.1. READ_ONLY

Phù hợp với Country hoặc nhóm mã tham chiếu được quản lý theo phiên bản và coi là immutable.

~~~java
@Entity
@Immutable
@Cacheable(true)
@Cache(
    usage = CacheConcurrencyStrategy.READ_ONLY,
    region = "reference.countries"
)
class Country {
    @Id Long id;
    String isoCode;
}
~~~

Khi entity đã được cache dạng read-only, các thay đổi thông thường qua Hibernate không phải use case được hỗ trợ cho vùng đó. Đừng thử “cập nhật hiếm nên vẫn READ_ONLY” nếu update là nghiệp vụ hợp lệ; hãy chọn chiến lược khác hoặc chỉ evict/rebuild theo quy trình quản trị có kiểm soát.

### 7.2. NONSTRICT_READ_WRITE

Một bảng danh mục dùng để hiển thị có thể cập nhật vài lần/ngày và chấp nhận thời gian rất ngắn nhìn thấy dữ liệu cũ. NONSTRICT_READ_WRITE có thể phù hợp, với điều kiện:

- Business chấp nhận stale reads.
- Không dùng cached value để quyết định transaction quan trọng.
- Có test hành vi khi hai thread/node đọc và ghi xen kẽ.
- Có kế hoạch khi dữ liệu được cập nhật từ ngoài Hibernate.

Không nên mô tả NONSTRICT_READ_WRITE như một guarantee “mọi reader thấy dữ liệu mới ngay sau commit”. Nó được thiết kế cho use case có yêu cầu consistency thấp hơn READ_WRITE.

### 7.3. READ_WRITE

~~~java
@Entity
@Cacheable(true)
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "catalog.product-categories"
)
public class ProductCategory {
    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    @Version
    private long version;
}
~~~

READ_WRITE áp dụng access protocol của Hibernate/provider để xử lý các lượt đọc/ghi qua ORM. Một số implementation dùng cơ chế soft lock hoặc invalidation quanh transaction. **Nó không tương đương SERIALIZABLE transaction**, không thay @Version và không bảo đảm những writer bypass Hibernate tự kích hoạt invalidation.

@Version trong ví dụ phục vụ optimistic locking của entity; đây là cơ chế khác với L2 cache concurrency strategy. Không thêm version chỉ để “làm cache an toàn” mà chưa hiểu quy tắc update của domain.

### 7.4. TRANSACTIONAL

TRANSACTIONAL dành cho tình huống provider cache và transaction coordination (chẳng hạn JTA/XA theo khả năng provider) đáp ứng hợp đồng transaction-aware. Một Spring @Transactional chạy bằng local JDBC transaction **không mặc định** có nghĩa cache provider hỗ trợ TRANSACTIONAL.

Chỉ chọn khi đã xác minh:

- Hibernate adapter hỗ trợ strategy.
- Provider cung cấp transactional cache phù hợp.
- Transaction manager được cấu hình chính xác.
- Rollback/commit/concurrent writes qua nhiều node có integration tests.

Nếu không cần semantics đó, không chọn TRANSACTIONAL chỉ vì nghe “mạnh nhất”.

### 7.5. Không có strategy nào biến cache thành nguồn dữ liệu tối hậu

Ngay cả READ_WRITE, dữ liệu giao dịch vẫn phải dựa vào database lock/version/constraint khi cần bảo đảm correctness. Cache là lớp tăng tốc, không phải nơi ra quyết định tồn kho/số dư theo giả định trạng thái luôn mới nhất.

## 8. Chọn provider: tương thích nghĩa là tương thích ở nhiều tầng

Một cache provider chỉ phù hợp với Hibernate nếu có **integration hợp lệ với Hibernate L2 cache SPI**, không chỉ có một API get(key)/put(key).

Các tầng cần đối chiếu:

~~~mermaid
flowchart TD
    A[Phiên bản Hibernate ORM] --> B[RegionFactory / Hibernate integration module]
    B --> C[Cache API, ví dụ JCache JSR-107]
    C --> D[Provider implementation và version]
    D --> E[Java runtime, serialization và classloader]
    E --> F[Transactions, cluster, invalidation, metrics]
    F --> G[Integration test với deployment thực tế]
~~~

Chỉ khi các tầng này khớp, mới có thể coi provider là ứng viên triển khai.

### 8.1. Một vài hướng integration thường gặp

| Hướng | Mô tả | Cần xác minh |
|---|---|---|
| Hibernate JCache adapter + Ehcache 3 JSR-107 | Hibernate nói chuyện qua JCache và Ehcache cung cấp implementation | Hibernate 6 module, JCache API, Ehcache version, XML, region strategy |
| Hibernate integration dành cho Infinispan | Cache integration có thể cung cấp clustering/distributed behavior chuyên biệt | Module được phát hành tương ứng Hibernate version, transaction và topology |
| JCache adapter + provider JCache khác | Sử dụng một JCache implementation được hỗ trợ | Access semantics, cluster behavior, expiry/invalidation, region creation |
| Provider custom RegionFactory | Integration đặc thù do vendor/team duy trì | SPI binary compatibility, correctness khi update/rollback, bảo trì lâu dài |

Bảng này **không khẳng định mọi phiên bản** của một tên provider luôn tương thích. Ví dụ một module Infinispan dành cho Hibernate phiên bản khác có thể không nạp được hoặc lỗi runtime dù package tên gần giống.

### 8.2. Ehcache 2 và Ehcache 3 không phải một dependency

Nhiều hướng dẫn cũ cho Hibernate 4/5 dùng integration và tên RegionFactory của Ehcache 2. Không sao chép dependency hoặc class name đó sang Hibernate 6 rồi mong chạy.

Với Hibernate 6, hướng phổ biến là **hibernate-jcache** cộng với một JCache provider như Ehcache 3. Cần kiểm tra classpath, phiên bản JCache implementation và cấu hình vùng cache trong project thực tế.

### 8.3. JCache vẫn có package javax.cache

Một điểm dễ nhầm:

- Entity/JPA Hibernate 6 dùng **jakarta.persistence**.
- JCache (JSR-107) thường vẫn có API **javax.cache**.

Vì vậy property Hibernate JCache có tên dạng:

~~~properties
hibernate.javax.cache.provider=...
hibernate.javax.cache.uri=...
~~~

Điều này không có nghĩa Hibernate 6 đang dùng javax.persistence. Hai tiêu chuẩn có lịch sử package riêng. Không tự đổi tên property thành hibernate.jakarta.cache.provider nếu version Hibernate không định nghĩa property đó.

### 8.4. Spring Cache và Redis không tự trở thành Hibernate L2 provider

Nếu một ứng dụng đã dùng:

~~~java
@Cacheable("products")
public ProductDto getProduct(...) { ... }
~~~

đó thường là annotation của Spring Cache trên service method, **không phải** jakarta.persistence.Cacheable của entity và không đồng nghĩa Hibernate L2 đã dùng cache này.

Tương tự, việc có Redis connection hoặc Caffeine cache trong Spring Boot **không tự cung cấp Hibernate RegionFactory**. Muốn dùng Redis/Caffeine như L2 cần integration Hibernate được hỗ trợ và xác minh semantics; không thể trỏ Hibernate vào một bean Spring Cache bất kỳ.

### 8.5. Khả năng multi-node không đến từ một cái tên provider

Một Ehcache/JCache cache trong heap của từng JVM có thể là **node-local**. Nếu app chạy 4 replica, mỗi replica có cache riêng. Một node cập nhật DB không có nghĩa 3 node còn lại tự biết phải evict entry.

Provider có khả năng distributed/clustered chỉ có ích nếu **đã cấu hình topology, messaging, invalidation và consistency** đúng. Không coi “đã dùng cache provider X” là bằng chứng dữ liệu L2 đồng bộ đa node.

## 9. Quy trình chọn provider theo từng bước

Một cách chọn có hệ thống:

### Bước 1 — cố định phiên bản ứng dụng

Ghi nhận:

~~~text
Java runtime
Spring Boot version (nếu có)
Hibernate ORM version
Transaction manager và chế độ JTA/local
Database dialect
Số app instances và scaling model
~~~

Không chọn cache dependency trước khi biết Hibernate version. Cache adapter thường có phụ thuộc chặt với Hibernate SPI.

### Bước 2 — xác định mục tiêu nhất quán

Với từng entity candidate, phân loại:

~~~text
Immutable thực tế?
Read-mostly và stale được bao lâu?
Update qua ORM hay nhiều writer?
Có tiền/tồn kho/quyền truy cập không?
Một cache miss hay mất cache có làm hệ thống lỗi không?
~~~

Kết quả dẫn đến access strategy và phạm vi cache, không ngược lại.

### Bước 3 — chọn adapter được hỗ trợ

Nếu muốn JCache, dùng module Hibernate JCache đúng version và một JCache provider có tài liệu tương thích. Nếu muốn provider-specific như Infinispan integration, dùng đúng module dành cho Hibernate version.

Không chọn RegionFactory class từ một bài blog của Hibernate phiên bản cũ mà chưa xác nhận class còn tồn tại trong runtime.

### Bước 4 — kiểm tra các khả năng của provider

Một danh sách đánh giá:

- READ_ONLY/READ_WRITE/NONSTRICT_READ_WRITE/TRANSACTIONAL mà ứng dụng định sử dụng.
- Local vs distributed region và đồng bộ eviction giữa các node.
- TTL/TTI, heap/off-heap/disk capacity, eviction policy.
- Transaction synchronization và xử lý rollback.
- Serialization của cache keys/values trong cluster.
- Region naming, implicit creation, startup fail-fast.
- Metrics, logging, cache health, failover.
- Behavior khi provider restart hoặc network partition.

### Bước 5 — chạy thử một entity trước

Chọn một Country/reference entity READ_ONLY, bật statistics và chứng minh:

1. Session thứ nhất cache miss rồi đọc database.
2. Session khác thuộc cùng SessionFactory cache hit mà không đọc lại entity row.
3. Thao tác eviction buộc lượt đọc sau trở về database.
4. Khi update dữ liệu, vùng cache có xử lý phù hợp theo strategy.

### Bước 6 — thử triển khai thực tế

Một provider chạy đúng trong single-JVM test chưa chứng minh chạy đúng trên 3 pods. Với clustered deployment, test cross-node writes, rolling restart, cache unavailable và schema upgrade.

## 10. Ví dụ cấu hình Hibernate 6 + JCache + Ehcache 3

Đây là ví dụ **minh họa cách ghép các thành phần**, không phải phiên bản dependency được pin sẵn cho mọi Spring Boot.

### 10.1. Các dependency cần thiết

Với Gradle dùng Spring Boot dependency management:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.hibernate.orm:hibernate-jcache")
    implementation("org.ehcache:ehcache")
}
~~~

Các artifact không ghi version ở đây vì ví dụ giả định BOM/dependency management đã quản lý. **Phải kiểm tra** Hibernate core và hibernate-jcache cùng dòng/version tương thích, Ehcache 3 là implementation JCache phù hợp và JCache API được resolve trong dependency graph.

Tùy version Ehcache/Java packaging, có thể có yêu cầu thêm về JAXB, classifier hoặc exclusion. Không sao chép máy móc một cặp artifact từ ứng dụng Hibernate 5 sang Hibernate 6. Nếu dependency management không quản lý version, pin những phiên bản đã được thử cùng nhau và kiểm tra dependency tree.

### 10.2. Cấu hình application.properties

~~~properties
# Kích hoạt L2; nếu không có provider và cacheable entity,
# property này một mình không tạo giá trị cache.
spring.jpa.properties.hibernate.cache.use_second_level_cache=true

# Hibernate 6 JCache RegionFactory:
spring.jpa.properties.hibernate.cache.region.factory_class=org.hibernate.cache.jcache.internal.JCacheRegionFactory

# JCache implementation:
spring.jpa.properties.hibernate.javax.cache.provider=org.ehcache.jsr107.EhcacheCachingProvider

# Tài nguyên cấu hình phải được provider phân giải đúng.
spring.jpa.properties.hibernate.javax.cache.uri=ehcache.xml

# Query cache là tính năng riêng; mặc định chưa sử dụng ở ví dụ.
spring.jpa.properties.hibernate.cache.use_query_cache=false

# Chỉ bật thống kê khi cần quan sát/test.
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Đường dẫn ehcache.xml và khả năng tìm resource qua URI tùy JCache provider. Nếu ứng dụng không tìm thấy XML, cần kiểm tra classpath URI/provider API cụ thể thay vì tự đổi tên file hoặc class mà không xem log. Tên class RegionFactory trong ví dụ dành cho mô hình Hibernate 6 JCache; phiên bản khác có thể thay đổi.

### 10.3. Cấu hình region dung lượng có giới hạn

Một XML Ehcache 3 minh họa:

~~~xml
<config xmlns="http://www.ehcache.org/v3">
    <cache alias="reference.countries">
        <key-type>java.lang.Object</key-type>
        <value-type>java.lang.Object</value-type>
        <expiry>
            <ttl unit="hours">12</ttl>
        </expiry>
        <resources>
            <heap unit="entries">2000</heap>
        </resources>
    </cache>
</config>
~~~

Region alias phải tương ứng với region="reference.countries" trong Hibernate @Cache. Đây là sơ đồ cấu hình minh họa; cần xác nhận namespace/schema, cách JCache provider ánh xạ key/value type và URI của XML với phiên bản Ehcache thực tế. Hibernate có thể lưu các cache entry types nội bộ, nên không tự giới hạn key-type thành Long hoặc value-type thành Country mà chưa hiểu representation.

### 10.4. Không để region tự tạo không kiểm soát

Một số integration/provider có thể tạo cache còn thiếu với cấu hình mặc định. Nếu region chưa được định nghĩa, cache có thể nhận TTL/capacity không phù hợp hoặc thậm chí không có giới hạn như dự kiến.

Quy trình tốt:

1. Định danh các region được phép.
2. Cấu hình giới hạn dung lượng, eviction/expiry rõ.
3. Tìm hiểu policy tạo region còn thiếu và ưu tiên fail fast khi thích hợp.
4. Kiểm tra startup log xác nhận tên region/provider.
5. Quan sát memory và hit rate sau warm-up.

Đừng đoán rằng cấu hình XML đã được đọc chỉ vì ứng dụng khởi động thành công.

### 10.5. Cấu hình một entity đầu tiên

~~~java
import jakarta.persistence.*;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;
import org.hibernate.annotations.Immutable;

@Entity
@Table(name = "countries")
@Immutable
@Cacheable(true)
@Cache(
    usage = CacheConcurrencyStrategy.READ_ONLY,
    region = "reference.countries"
)
public class Country {
    @Id
    private Long id;

    @Column(name = "iso_code", nullable = false, unique = true)
    private String isoCode;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Country() {}

    public Long getId() { return id; }
    public String getIsoCode() { return isoCode; }
    public String getDisplayName() { return displayName; }
}
~~~

Trong dự án thật, dữ liệu Country phải được vận hành đúng như immutable và có quy trình rõ nếu danh mục được thay qua migration/admin. Lúc đó cần evict/clear hoặc thay version cache để tránh entry cũ.

## 11. L2 cache chứa những dữ liệu nào?

Một sai lầm là hình dung cache entity dưới dạng một object graph Java hoàn chỉnh:

~~~text
Country { id, name, provinces: [Province, Province, ...] }
~~~

Hibernate L2 thường quản lý cached state theo region và entity/collection keys. **Cache một entity không mặc định cache mọi association hoặc cả graph**.

### 11.1. Entity region

Entity ProductCategory được cache theo identifier và các thành phần khóa liên quan do Hibernate/provider xác định. Entry thường chứa trạng thái cần để hydrate entity, không phải một managed entity dùng chung cho mọi Session.

Ví dụ:

~~~java
ProductCategory category = em.find(ProductCategory.class, 7L);
~~~

Nếu region có entry hợp lệ, Hibernate có thể tránh SELECT của entity ProductCategory. Nhưng việc truy cập category.getProducts() có thể vẫn cần SQL vì collection chưa được cache hoặc chưa được khởi tạo.

### 11.2. Collection region là riêng

Nếu cần cache membership của một collection:

~~~java
@Entity
public class ProductCategory {
    @Id
    private Long id;

    @OneToMany(mappedBy = "category", fetch = FetchType.LAZY)
    @Cache(
        usage = CacheConcurrencyStrategy.READ_WRITE,
        region = "catalog.category-products"
    )
    private Set<Product> products = new HashSet<>();
}
~~~

Cache collection có thể lưu thông tin các phần tử/identifiers của collection, tùy loại mapping. **Nó không có nghĩa Product entities tự động được cached ở entity region**. Khi collection chứa entity IDs, Hibernate vẫn có thể đọc Product từ database nếu Product không có cache entry và chưa nằm trong L1.

Vì vậy khi muốn cache collection, đo cả:

- Cache hit của collection region.
- Cache hit/miss của entity target region.
- Số SQL phát sinh để load target entities.
- Chi phí invalidation khi thêm/xóa/reorder collection.

### 11.3. Vì sao collection lớn thường không nên cache

Một category có 100.000 Products có thể tạo cached collection entry rất lớn. Nếu Product được thêm/xóa thường xuyên, entry bị invalidation liên tục. Nếu UI chỉ cần 20 products đầu, cache cả membership không giải quyết thiết kế phân trang.

Trong trường hợp này, thường phù hợp hơn:

~~~hql
select p
from Product p
where p.category.id = :categoryId
order by p.id
~~~

rồi paginate/DTO projection theo nhu cầu.

### 11.4. Natural-ID cache

Hibernate có cơ chế riêng cho lookup bằng business key ổn định:

~~~java
@Entity
@NaturalIdCache
@Cacheable(true)
@Cache(
    usage = CacheConcurrencyStrategy.READ_ONLY,
    region = "reference.countries"
)
public class Country {
    @Id
    private Long id;

    @NaturalId(mutable = false)
    private String isoCode;
}
~~~

Natural-id caching giúp tối ưu việc ánh xạ business key như isoCode tới entity identity trong những trường hợp được Hibernate hỗ trợ; entity data region và natural-id cache có vai trò riêng. Nếu natural ID có thể thay đổi, phải hiểu semantics của mutable natural id và invalidation. Không xem @NaturalIdCache là một cách thay thế UNIQUE constraint ở DB.

## 12. Query result cache: chỉ bật khi thật sự có lý do

Hibernate query cache không đồng nghĩa L2 entity cache. Bật query cache toàn ứng dụng mà không đánh dấu query phù hợp cũng không mang lại lợi ích tự động cho mọi SELECT.

Ví dụ Hibernate-specific:

~~~properties
hibernate.cache.use_query_cache=true
~~~

~~~java
List<Country> countries = entityManager
    .createQuery("""
        select c
        from Country c
        order by c.displayName
        """, Country.class)
    .unwrap(org.hibernate.query.Query.class)
    .setCacheable(true)
    .getResultList();
~~~

Với query cache, Hibernate lưu thông tin kết quả và phối hợp cơ chế invalidation/timestamps cho các query spaces. Chi tiết representation (identifiers, scalar values, row representations) có thể khác giữa các phiên bản Hibernate; không giả định nó chỉ chứa ID hoặc luôn chứa toàn bộ entity objects.

### 12.1. Điều kiện để query cache hữu ích

- Cùng HQL/query shape và parameters được lặp nhiều.
- Tập dữ liệu dưới query không bị update thường xuyên.
- Kết quả vừa phải, không tạo quá nhiều key combinations.
- Có cấu hình region/expiry và invalidation phù hợp.
- Đã đo cache hit và SQL thực tế.

Nếu mỗi request có một bộ filter/timestamp khác nhau, query cache có thể tạo hàng nghìn entry không được tái sử dụng.

### 12.2. Query cache invalidation và timestamps

Hibernate cần biết khi nào dữ liệu của các bảng liên quan thay đổi để kết quả query đã cache không còn hợp lệ. Các region phục vụ update timestamps/invalidation có yêu cầu sống lâu phù hợp với query results, tùy provider/version.

Nếu cấu hình timestamps region hết hạn quá sớm hoặc bị evict không đúng cách trong khi query results còn tồn tại, khả năng kiểm chứng dữ liệu mới có thể bị ảnh hưởng. **Không đặt TTL thấp cho vùng update-timestamps theo thói quen**; tham khảo yêu cầu của Hibernate version/provider và kiểm thử hành vi cập nhật.

### 12.3. Query cache không thay thế sửa query chậm

Nếu query chạy 2 giây khi miss, lần warm-up/restart hoặc invalidation vẫn gây tải 2 giây. Index, projection, JOIN strategy và giới hạn số rows cần được tối ưu độc lập.

## 13. Hạn dùng TTL và chính sách eviction không phải bảo đảm correctness

Một entry có TTL 12 giờ có nghĩa provider có thể xem nó hết hạn sau khoảng thời gian đó (theo semantics được cấu hình), **không có nghĩa mọi giá trị thay đổi được đồng bộ ngay trong 12 giờ**.

### 13.1. TTL chỉ là cơ chế làm mới theo thời gian

Giả sử Country.displayName được sửa trực tiếp bằng SQL từ một hệ thống khác:

~~~sql
UPDATE countries
SET display_name = 'Tên mới'
WHERE id = 42;
~~~

Hibernate ở một JVM khác không nhất thiết nhận thông báo này. Entry L2 có thể tiếp tục trả tên cũ cho tới khi bị evict/expire hoặc cache bị xóa.

Nếu business cần cập nhật thấy ngay, TTL 12 giờ **không phải giải pháp**. Cần write-through/invalidation có kiểm soát, event/cross-node synchronization hoặc tránh cache.

### 13.2. Dung lượng và eviction policy

Giới hạn region:

~~~text
reference.countries: 2.000 entries
catalog.categories: 20.000 entries
~~~

Nên được chọn bằng working set và kích thước entry, không chỉ số entity ở DB. Khi capacity quá nhỏ, hot keys có thể bị đẩy ra liên tục, hit rate thấp và CPU/GC tăng. Khi capacity quá lớn, memory pressure làm JVM và cache provider chậm.

### 13.3. Cache stampede và khởi động lạnh

Sau restart/eviction đồng loạt, hàng nghìn request có thể cùng miss và dồn xuống database. Một số provider có cơ chế loading/locking khác nhau; không mặc định Hibernate L2 tự ngăn mọi thundering herd.

Giải pháp vận hành có thể gồm:

- Capacity planning cho DB trong giai đoạn warm-up.
- Rollout từng node thay vì xóa tất cả cache cùng lúc.
- Preload một tập dữ liệu tham chiếu nhỏ nếu lợi ích rõ và được kiểm thử.
- Rate-limit hoặc coalescing ở tầng service khi cần.
- Theo dõi hit rate/DB QPS ngay sau deploy.

Prewarming hàng triệu entity một cách vô tội vạ có thể làm startup chậm và lấp vùng cache bằng dữ liệu không nóng.

## 14. Dữ liệu được cập nhật qua Hibernate hay qua đường khác?

Đây là yếu tố quyết định khi dùng L2.

### 14.1. Update entity managed qua Hibernate

~~~java
@Transactional
public void renameCategory(Long id, String newName) {
    ProductCategory category =
        entityManager.find(ProductCategory.class, id);
    category.rename(newName);
}
~~~

Với entity cacheable và strategy phù hợp, Hibernate biết một entity đã được thay đổi theo lifecycle ORM và phối hợp cache action theo transaction/access strategy.

### 14.2. Bulk HQL hoặc native SQL

~~~java
entityManager.createNativeQuery("""
    UPDATE product_categories
    SET name = :name
    WHERE id = :id
    """)
    .setParameter("name", newName)
    .setParameter("id", id)
    .executeUpdate();
~~~

Native/bulk DML có thể bypass callback, dirty checking và một phần đường cập nhật entity thông thường. Hibernate có cơ chế invalidation cho một số bulk operations, nhưng cách phối hợp với native SQL, query spaces và cache regions phụ thuộc API/version. **Không mặc định mọi native update tự động làm đúng mọi cached entity/collection/query result ở mọi node**.

Khi dùng native/bulk DML:

1. Xác định những entity/collection/query region chịu ảnh hưởng.
2. Kiểm tra Hibernate có nhận diện được affected query spaces không.
3. Chọn đúng cơ chế eviction/synchronization sau commit nếu cần.
4. Test cả Session khác và node khác.
5. Không xóa cache trước commit rồi để request khác nạp lại dữ liệu cũ vào cache.

### 14.3. External writers

ETL, admin console, stored procedure, một service khác hoặc DBA update trực tiếp database có thể không đi qua Hibernate cache integration. Với dữ liệu như vậy, cần lựa chọn:

- Tất cả writes đi qua một lớp có phối hợp invalidation.
- Publish cache-invalidation event tin cậy sau commit.
- Không dùng L2 cho thực thể đó.
- Chấp nhận stale data có giới hạn được business xác nhận và dùng TTL.

Việc thay đổi ngoài ORM là một **điều kiện kiến trúc**, không chỉ là chi tiết hiệu năng.

## 15. Evict cache theo entity hoặc toàn bộ vùng

JPA Cache API cung cấp các thao tác eviction:

~~~java
import jakarta.persistence.Cache;
import jakarta.persistence.EntityManagerFactory;

Cache cache = entityManagerFactory.getCache();

// Loại entry của một Country.
cache.evict(Country.class, 42L);

// Loại toàn bộ Country entity region.
cache.evict(Country.class);

// Loại dữ liệu shared cache do provider quản lý theo API JPA.
cache.evictAll();
~~~

Hibernate SessionFactory Cache API cung cấp thêm thao tác provider-specific cho entity, collection và các region khác.

### 15.1. Eviction có nghĩa gì với L1?

Evict L2 **không tự xóa object đang managed trong mọi EntityManager hiện hữu**. Nếu Session A đã load Country và giữ entity trong L1, sau khi L2 eviction, Session A vẫn có thể trả instance đó cho một lần find tiếp theo. Cần hiểu scope riêng của L1 và L2.

### 15.2. Thời điểm eviction

Nếu một transaction sửa DB nhưng chưa commit, rồi evict L2 quá sớm:

~~~text
T1: cập nhật nhưng chưa commit
T2: evict cache
T3: request khác miss và đọc bản ghi cũ đã commit
T4: request khác put giá trị cũ lại vào cache
T5: transaction đầu mới commit
~~~

Nếu không có protocol đồng bộ phù hợp, stale entry có thể tồn tại. Không tự viết eviction thủ công quanh transaction mà không xem lifecycle/caching strategy. Với external writers, nên phát invalidation **sau commit thành công** và thiết kế retry/idempotency cho event.

### 15.3. EvictAll không phải cách vận hành thường xuyên

Xóa toàn bộ L2 sau mỗi lần sửa một ProductCategory làm mất lợi ích của các vùng khác và tạo cold cache spike. Dùng region/entry invalidation có phạm vi phù hợp và giám sát. EvictAll có thể hữu ích trong deploy/migration có kiểm soát hoặc test, nhưng không phải cơ chế update mặc định.

## 16. Cache cấp hai trong môi trường nhiều node

Một hệ thống có ba ứng dụng:

~~~mermaid
flowchart LR
    A[App instance A] --> D[(Database)]
    B[App instance B] --> D
    C[App instance C] --> D
    A --> E[Local L2 A]
    B --> F[Local L2 B]
    C --> G[Local L2 C]
~~~

Nếu từng node có L2 local:

1. A nạp Country #42 vào cache A.
2. B nạp cùng Country vào cache B.
3. A update entity và đồng bộ cache A.
4. B có thể vẫn giữ giá trị cũ nếu không có cơ chế invalidation cross-node.

Vì vậy trước khi triển khai nhiều replica, phải biết provider đang hoạt động ở chế độ nào:

| Kiến trúc | Lợi ích | Rủi ro cần kiểm tra |
|---|---|---|
| Local per-JVM | Hit rất nhanh, vận hành đơn giản | Invalidation giữa node không tự động |
| Cluster replicated | Nhiều node chia sẻ hoặc đồng bộ entries | Network, replication overhead, split-brain |
| Distributed partitioned | Dung lượng chung lớn hơn, dữ liệu được phân phối | Remote latency, ownership/rebalance, failover |
| Near-cache local + remote | Đọc nóng nhanh và chia sẻ remote store | Local invalidation, stale near-cache |

### 16.1. Chọn theo correctness trước

Một product category cũ vài giây có thể chấp nhận trong giao diện, nhưng quyền truy cập/giá trị quyết định tính tiền có thể không. Đừng chọn local provider chỉ vì benchmark trên một node đẹp nếu production có nhiều instance và cần read-after-write toàn cụm.

### 16.2. Network partition và cache provider failure

Hãy xác định:

- Khi cache remote timeout, Hibernate fallback database hay query thất bại?
- Provider có retry/backoff khiến request vượt SLA không?
- Dữ liệu cache có bị mất khi node restart không?
- Khi cluster phân mảnh, có thể đọc entry stale không?
- Khi rolling upgrade, key/value serialization giữa version mới/cũ có tương thích không?

Các hành vi này là đặc tính implementation và configuration, cần thử thực tế. Không thể suy ra từ annotation @Cache trên entity.

## 17. Multi-tenancy, quyền truy cập và dữ liệu nhạy cảm

L2 cache thường keyed theo entity identifier và metadata cần thiết. Trong kiến trúc multi-tenant, thiết kế Hibernate chuẩn có thể bao gồm tenant identifier trong khóa cache khi cấu hình multi-tenancy đúng. Nhưng điều đó **không thay thế xác minh tenant isolation trong integration test**.

### 17.1. Không coi L2 cache là bộ lọc quyền

L2 entity cache là cơ chế tối ưu dữ liệu, không phải nơi tự thực thi mọi chính sách authorization của HTTP request. Nếu một user có thể yêu cầu entity ID thuộc user khác, service vẫn phải kiểm tra quyền ở mỗi đường truy cập.

### 17.2. Bảo mật dựa trên database RLS

Nếu ứng dụng dựa vào row-level security ở database, một cached entity có thể được trả từ L2 mà không phát sinh SELECT xuống DB cho lượt đọc đó. Không giả định DB RLS sẽ được đánh giá lại trên mọi cache hit.

Hệ thống phải xác định:

- Có cache những entity chịu RLS không?
- Tenant/principal có tham gia key/scope không?
- Authorization có được kiểm tra ở application layer không?
- Revocation của quyền có làm invalidation/recheck phù hợp không?

Nếu không chứng minh được, tránh L2 trên dữ liệu mà việc đọc cache bypass kiểm tra quyền.

### 17.3. Tách cache của tài nguyên nhạy cảm

Một provider có thể ghi entry xuống disk/off-heap, replicate qua mạng hoặc serialize. Cần xem encryption, ACL của cache cluster, retention/TTL, backup/logging và phạm vi dữ liệu cá nhân. Không mặc định “cache nằm trong RAM” nghĩa là không có rủi ro dữ liệu.

## 18. Đo hit, miss và put thật

Không thể kết luận L2 đã hoạt động chỉ vì có @Cacheable hoặc log “CacheManager initialized”.

Hibernate Statistics:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics stats = sessionFactory.getStatistics();

long hits = stats.getSecondLevelCacheHitCount();
long misses = stats.getSecondLevelCacheMissCount();
long puts = stats.getSecondLevelCachePutCount();

double hitRate = hits + misses == 0
    ? 0.0
    : (double) hits / (hits + misses);
~~~

Các bộ đếm này thuộc SessionFactory và có thể cộng dồn từ nhiều thread/request. Chỉ lấy delta trước/sau trong test cô lập khi muốn gắn số liệu với một use case.

### 18.1. Đừng nhầm L1 hit và L2 hit

Sai cách đo:

~~~java
Country first = em.find(Country.class, 42L);
Country second = em.find(Country.class, 42L);
~~~

Nếu cả hai trong cùng EntityManager, lần thứ hai thường được L1 phục vụ. Điều này **không chứng minh L2 hoạt động**.

Đúng cách thử L2 là đọc entity qua **hai Session độc lập** cùng SessionFactory, đảm bảo cache entry được put và transaction/Session đầu đã hoàn tất.

### 18.2. Integration test hai Session

~~~java
SessionFactory sf =
    entityManagerFactory.unwrap(SessionFactory.class);
Statistics stats = sf.getStatistics();

// Chỉ nên clear/evict trong test cô lập.
sf.getCache().evictEntityData(Country.class);
stats.clear();

try (Session first = sf.openSession()) {
    Transaction tx = first.beginTransaction();
    Country country = first.find(Country.class, countryId);
    assertNotNull(country);
    tx.commit();
}

long firstHits = stats.getSecondLevelCacheHitCount();
long firstPuts = stats.getSecondLevelCachePutCount();

try (Session second = sf.openSession()) {
    Transaction tx = second.beginTransaction();
    Country country = second.find(Country.class, countryId);
    assertNotNull(country);
    tx.commit();
}

long secondHits = stats.getSecondLevelCacheHitCount();

assertTrue(firstPuts > 0);
assertTrue(secondHits > firstHits);
~~~

Đây là skeleton: cần import Session, Transaction, EntityManagerFactory và assertion của JUnit; fixture countryId phải tồn tại. Một số cache implementations/strategies có thời điểm put khác hoặc không cache kết quả theo điều kiện đặc biệt, vì vậy test phải chạy trên provider/dialect thực tế và kiểm tra SQL.

### 18.3. Chỉ số cần theo dõi

| Metric | Ý nghĩa |
|---|---|
| L2 hit count/hit ratio | Số lần tìm thấy entry hợp lệ và tỷ lệ hit |
| L2 miss count | Số lần phải lấy dữ liệu từ nguồn khác |
| L2 put count | Số entry được đưa vào cache theo semantics Hibernate |
| Provider eviction count | Dữ liệu bị đẩy ra vì TTL/capacity/policy |
| Region entry count/heap bytes | Dung lượng chiếm dụng |
| DB SELECT/QPS | Tải database trước/sau triển khai |
| p50/p95/p99 latency | Trải nghiệm dưới tải thực tế |
| GC pause, heap pressure | Chi phí Java memory |
| Cache/network errors | Mức ổn định của provider |
| Invalidation lag | Thời gian dữ liệu mới được nhìn thấy ở các node |

Không chỉ nhìn hit rate. Một cache 99% hit nhưng mỗi hit phải gọi cache cluster qua mạng 20 ms có thể kém hơn một index lookup DB 2 ms, hoặc gây tail latency lớn khi network chập chờn.

### 18.4. Thống kê region cụ thể

Hibernate Statistics thường cung cấp cách xem số liệu theo cache region, API có thể thay đổi qua version. Khi đánh giá, phân tách:

~~~text
reference.countries
catalog.product-categories
catalog.category-products
query result regions
~~~

Một region rất tốt có thể che đi một region khác có miss/eviction dày đặc nếu chỉ xem số liệu tổng toàn SessionFactory.

## 19. Cách benchmark trước khi quyết định bật cache

Một phép đo hợp lý gồm:

1. **Baseline không L2:** cùng database/data, cùng tải, fetch plan và pool.
2. **Cold cache:** sau startup/eviction, đo SQL và latency khi cache mới rỗng.
3. **Warm cache:** chạy workload đủ lâu để working set được nạp.
4. **Update workload:** mô phỏng ghi entity/cập nhật ngoài ORM theo thực tế.
5. **Multi-node:** nếu production nhiều node, chạy đúng topology.
6. **Failure:** cache node restart, timeout, network partition (khi có khả năng mô phỏng).
7. **Comparative metrics:** DB QPS, p95/p99, heap, GC, provider network.

### 19.1. Workload phải giống production

Nếu chỉ benchmark lặp lại cùng Country ID 100.000 lần, hit rate sẽ rất đẹp nhưng không đại diện cho dịch vụ thực sự đọc hàng nghìn IDs khác nhau và update mỗi phút.

Tạo phân phối khóa nóng/lạnh và tỷ lệ read/write tương ứng workload dự kiến. Đo dưới số lượng concurrent requests gần thực tế.

### 19.2. Cảnh giác với cache warm-up sau deploy

Một hệ thống có thể rất nhanh sau 30 phút, nhưng cứ mỗi lần autoscaling lại dồn SQL xuống database và làm p99 tăng mạnh. Kết quả benchmark cần có cả cold-start/warm-up, không chỉ steady-state.

### 19.3. Có nên bật query cache cùng lúc?

Không nên thay hai biến cùng lúc nếu muốn hiểu lợi ích thực của L2 entity region. Đầu tiên thử L2 cho một entity; sau đó nếu có lặp query result rõ ràng, thử query cache ở một nhóm query đã chọn. Đo delta độc lập.

## 20. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| @Cacheable có nhưng mỗi Session vẫn SELECT | Chưa có RegionFactory/provider, SharedCacheMode không cho phép, region không thực sự hoạt động | Kiểm tra startup config, provider và Statistics |
| Lần find thứ hai không chạy SQL trong cùng EntityManager | Đó có thể là L1 hit, chưa chứng minh L2 | Test bằng hai Session khác nhau |
| ClassNotFoundException cho RegionFactory | Dùng class cũ hoặc thiếu hibernate-jcache module | Căn version/module và class được phát hành |
| No caching provider / CacheManager lỗi | Thiếu JCache implementation, classpath hoặc URI sai | Kiểm tra dependency tree và provider config |
| Lỗi javax.cache khi dùng Jakarta Persistence | Nhầm JCache package với javax.persistence | Dùng đúng JCache API và Hibernate adapter |
| Hibernate startup được nhưng cache không có limit | Region bị auto-create với default | Cấu hình từng region/limit và test thực tế |
| READ_ONLY entity vẫn bị update | Cache strategy mâu thuẫn domain | Chọn READ_WRITE hoặc mô hình immutable thật |
| Dữ liệu cũ sau native SQL | Thay đổi bypass invalidation dự kiến | Đồng bộ/evict sau commit và test |
| Dữ liệu khác nhau giữa các app nodes | Cache local không có cross-node invalidation | Chọn cluster strategy hoặc bỏ L2 cho vùng đó |
| L2 hit cao nhưng query vẫn nhiều | Query lookup, collection/associations hoặc count chưa cached | Phân biệt entity/query/collection cache |
| Cache hit thấp | Working set quá lớn, TTL thấp, truy cập chỉ một lần | Bỏ region hoặc điều chỉnh capacity/TTL |
| Heap/GC tăng | Region quá lớn hoặc nhiều entries | Giới hạn dung lượng, xem sizes và eviction |
| Query cache trả kết quả không như mong đợi | Update timestamps/query spaces/expiry không phù hợp | Kiểm tra cache regions và update paths |
| Security regression khi cache hit | Authorization dựa quá nhiều vào DB filter/RLS | Kiểm tra quyền ở app, test multi-tenant |
| Transaction rollback gây dữ liệu sai | Strategy/provider không phối hợp transaction đúng | Chọn provider/strategy tương thích, test rollback |
| Migrate Hibernate rồi cache ngừng chạy | SPI/dependency/version mismatch | Kiểm tra BOM, adapter và provider cùng lúc |

## 21. Các bài kiểm thử về tính đúng đắn

Kiểm thử phải đi xa hơn việc assert cache hit.

### 21.1. READ_ONLY với dữ liệu immutable

1. Tạo Country fixture trong database.
2. Clear Session, evict entry L2 và reset Statistics.
3. Session A đọc Country theo ID.
4. Session B đọc cùng ID.
5. Kiểm tra B có L2 hit và giảm SELECT.
6. Cố gắng thay đổi Country qua một write path có kiểm soát để xác nhận domain không cho phép update.
7. Evict entry rồi xác nhận lượt đọc sau lấy dữ liệu mới nếu đã thay đổi ở DB ngoài ORM.

Không tạo test làm DB thay đổi nhưng cố tình không invalidation rồi coi kết quả stale là “cache hoạt động tốt”; bài test đó chỉ chứng minh rủi ro freshness.

### 21.2. READ_WRITE và rollback

1. Tạo ProductCategory cacheable với @Version.
2. Đọc để warm L2.
3. Trong transaction A, update name nhưng rollback.
4. Session khác đọc lại, phải thấy giá trị đã commit cũ.
5. Trong transaction B, update rồi commit.
6. Session khác đọc lại, phải thấy dữ liệu đã commit mới theo consistency contract/provider.
7. Nếu chạy cluster, lặp lại giữa các node.

Những bước này cần chạy với cache provider và transaction manager thực tế. Đừng suy diễn từ annotation rằng mọi provider đều đáp ứng cùng một mức nhất quán.

### 21.3. Native SQL và external writer

1. Warm cache entity.
2. Chạy native UPDATE trong transaction riêng.
3. Commit.
4. Đọc từ Session/node khác trước eviction.
5. Quan sát có stale read không.
6. Thực hiện cơ chế invalidation mà hệ thống đã thiết kế.
7. Đọc lại, xác nhận giá trị đúng.

Mục tiêu là định nghĩa **đường cập nhật thực tế** chứ không chỉ test Hibernate managed update.

### 21.4. Multi-node integration test

Với hai app instances:

~~~text
Node A: read Country #42 -> warm cache A
Node B: read Country #42 -> warm cache B
Node A: update nếu domain cho phép -> commit
Node B: read Country #42 -> kiểm tra freshness
Restart node A/B -> kiểm tra warm-up
Disconnect cache cluster -> kiểm tra failure behavior
~~~

Nếu provider được cấu hình local-only và business chấp nhận stale đến TTL, test phải khẳng định đúng contract đó. Nếu business yêu cầu mọi node thấy update sau commit, local-only mà không invalidation cross-node là thiết kế không phù hợp.

### 21.5. Không dùng cùng EntityManager cho cả test

L1 có thể che đi L2 behavior. Sau fixture, flush/commit và dùng persistence context mới. Trong benchmark, không reuse entity đã managed giữa các lượt muốn đo cache hit.

## 22. Kịch bản triển khai có kiểm soát

Một rollout an toàn cho L2 cache:

1. **Chọn một entity nhỏ** có read-many/write-rarely và rủi ro stale thấp.
2. **Chọn SharedCacheMode chọn lọc**, tránh cache toàn hệ thống.
3. **Cấu hình provider/region rõ ràng**, giới hạn heap và TTL.
4. **Chọn access strategy có chủ đích**, thường READ_ONLY cho immutable reference.
5. **Viết test với hai Session**, thêm test update/eviction.
6. **Bật metrics**, ghi baseline SQL và p95 latency.
7. **Canary ở một phần traffic** nếu kiến trúc cho phép.
8. **Quan sát warm-up, miss spikes và DB load** sau deploy.
9. **Kiểm tra multi-node invalidation** trước khi mở rộng.
10. **Có công tắc tắt cache/rollback** và quy trình clear cache an toàn nếu phát hiện stale data.

### 22.1. Lộ trình từ dễ đến khó

~~~text
Country (immutable, đọc theo ID)
    ↓
ProductCategory (read-mostly, update qua ORM)
    ↓
Collection nhỏ, ít thay đổi
    ↓
Một query result cache cụ thể nếu thật sự lặp
    ↓
Các use case multi-node/concurrency phức tạp
~~~

Không bật entity, collection và query cache hàng loạt trong một lần rồi cố truy ngược nguyên nhân khi hiệu năng xấu đi.

### 22.2. Khi nào nên tắt cache sau thử nghiệm?

Đôi khi kết luận tốt nhất là **không dùng L2** cho entity đã chọn:

- Hit rate thấp sau khi warm đủ.
- Heap/GC tăng, p95 không cải thiện.
- Mỗi update gây invalidate nhiều region.
- Cross-node consistency không đáp ứng.
- External writer không thể phát invalidation tin cậy.
- Vấn đề N+1 hoặc missing index mới là nguyên nhân chính.

Tắt một cache region không phải thất bại: đó là một quyết định dựa trên dữ liệu và yêu cầu correctness.

## 23. Bài thực hành tổng hợp

### Bài A — Phân biệt L1 và L2

1. Tạo entity Country có dữ liệu ổn định.
2. Đọc hai lần trong cùng EntityManager, quan sát không có SELECT lần hai.
3. Đọc trong hai EntityManager riêng khi chưa có L2, quan sát SQL.
4. Bật provider và region READ_ONLY.
5. Đọc qua hai Session mới, kiểm tra Statistics hit/miss.
6. Giải thích tại sao hai entity objects thuộc hai Session không phải một managed instance duy nhất.

### Bài B — Chọn entity candidate

Với bốn loại dữ liệu:

~~~text
Country: hiếm update
ProductCategory: update vài lần/ngày
InventoryBalance: update liên tục
PaymentTransaction: ghi nhiều, yêu cầu chính xác cao
~~~

Hãy chọn:

- Entity nên/không nên cache.
- Access strategy nếu cache.
- Mức stale được phép.
- Cách invalidation khi update ngoài ORM.
- Metrics chứng minh lợi ích.

Không dùng một access strategy cho tất cả chỉ để cấu hình gọn hơn.

### Bài C — Provider compatibility

1. Ghi Hibernate ORM version từ dependency management.
2. Chọn hibernate-jcache version tương ứng.
3. Chọn Ehcache 3 JCache implementation có version được hỗ trợ.
4. Kiểm tra dependency tree và runtime classpath.
5. Cấu hình RegionFactory, provider URI và region XML.
6. Xác nhận application start và metrics từ đúng provider.
7. Thử thiếu region config để quan sát behavior; chọn fail-fast/auto-create policy có chủ đích.

### Bài D — Consistency

1. Warm ProductCategory READ_WRITE trong Session A.
2. Cập nhật qua ORM và commit.
3. Session B đọc lại, kiểm tra giá trị mới.
4. Lặp lại với rollback.
5. Update trực tiếp qua JDBC/native SQL, quan sát behavior và bổ sung invalidation.
6. Thử thêm node thứ hai nếu production multi-node.

### Bài E — Collection và query cache

1. Tạo Category có nhiều Products.
2. Cache entity Category rồi truy cập collection trong Session mới; quan sát SQL.
3. Chỉ khi có lý do, cache collection và đo số entity lookups còn lại.
4. Dùng một HQL query lặp lại tham số cố định, bật query cache chọn lọc.
5. Update bảng liên quan, kiểm tra query result invalidation.
6. So sánh hit rate và heap/DB load trước/sau.

### Bài F — Benchmark và rollout

1. Tạo workload đọc nhiều key nóng và một số key lạnh.
2. Đo khi không cache, cold cache, warm cache.
3. Bổ sung update workload.
4. Ghi hit/miss/put, evictions, p95, DB QPS, heap/GC.
5. Giảm region capacity để tái hiện eviction churn.
6. Đưa ra kết luận bật/tắt cache dựa trên số liệu và yêu cầu consistency.

## 24. Checklist chọn bộ cung cấp L2 cache

Trước khi đưa một provider vào production, kiểm tra:

1. **Đã xác định entity/region đủ điều kiện cache chưa?**
2. **Có chứng cứ reads lặp lại giữa các Session không?**
3. **Có baseline và mục tiêu đo được cho DB QPS/latency không?**
4. **Business cho phép dữ liệu stale tới mức nào?**
5. **Hibernate ORM, adapter hibernate-jcache/provider module có tương thích đúng version không?**
6. **JCache javax.cache và Jakarta Persistence có được phân biệt rõ không?**
7. **Provider có hỗ trợ access strategy được chọn không?**
8. **Region names, capacity, expiry và auto-create policy có rõ không?**
9. **Cache local hay clustered? Multi-node invalidation đã được thử chưa?**
10. **Transaction commit, rollback và optimistic locking đã được kiểm thử chưa?**
11. **Native SQL, ETL và external writers có cơ chế invalidation đáng tin cậy không?**
12. **Entity cache, collection cache và query cache có được phân biệt không?**
13. **Dữ liệu nhạy cảm/tenant/RLS có được bảo vệ ở mọi cache hit không?**
14. **Có metrics theo region cho hit/miss/put/eviction, heap và latency không?**
15. **Đã test bằng hai Session riêng, không bị L1 che hành vi L2 chưa?**
16. **Có kiểm thử provider failure, cold start, rolling deploy và network partition nếu cần không?**
17. **Có cách eviction/disable/rollback khi dữ liệu sai hoặc cache gây quá tải không?**

## 25. Nguyên tắc ghi nhớ

**Second-level cache là một tối ưu có điều kiện, không phải thứ nên bật đồng loạt cho mọi entity.**

- **L1 cache** thuộc từng Session/EntityManager; **L2** chia sẻ dữ liệu qua các Session theo phạm vi SessionFactory/provider.
- **Query cache** là cơ chế khác; cache entity theo ID không tự cache mọi SELECT/WHERE.
- Dữ liệu read-many/write-rarely, nhỏ và ổn định là ứng viên tốt; tiền, tồn kho, quyền truy cập thay đổi nhanh là ứng viên nhiều rủi ro.
- Cần **định nghĩa correctness và stale tolerance trước** khi chọn cache access strategy.
- @Cacheable, @Cache, SharedCacheMode và RegionFactory là các thành phần khác nhau; thiếu một tầng integration thì cache có thể không hoạt động như mong muốn.
- READ_ONLY dành cho immutable; NONSTRICT_READ_WRITE chấp nhận tính nhất quán lỏng; READ_WRITE có protocol update; TRANSACTIONAL chỉ dành cho provider/transaction infrastructure phù hợp.
- Hibernate 6 JCache sử dụng adapter riêng và JCache API có package **javax.cache**, dù entity dùng **jakarta.persistence**.
- Ehcache, Infinispan, provider JCache khác và Redis/Spring Cache **không hoán đổi trực tiếp** nếu thiếu đúng integration Hibernate và các bảo đảm vận hành.
- TTL/eviction không bảo đảm mọi cập nhật ngoài ORM được nhìn thấy ngay; multi-node consistency phải được xác minh.
- Cached entity, cached collection và query result cache có phạm vi và chi phí khác nhau.
- Đo qua **hai Session độc lập**; một L1 hit trong cùng Session không chứng minh L2 hit.
- Quyết định triển khai dựa trên hit/miss/put, SQL thực, p95/p99 latency, heap, invalidation và correctness tests.

Lộ trình thực tế tốt nhất là **bắt đầu nhỏ, chọn dữ liệu ít biến động, cấu hình provider đúng phiên bản, kiểm thử tính đúng đắn ở nhiều Session/node và đo lợi ích trước khi mở rộng**. Khi có các điều kiện đó, Hibernate second-level cache có thể giảm đáng kể những lượt đọc lặp lại; khi thiếu chúng, một hệ thống không dùng L2 nhưng có SQL/index/fetch plan tốt thường an toàn và dễ vận hành hơn.

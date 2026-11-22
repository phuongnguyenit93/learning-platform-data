# Kiểm chứng tính nhất quán thay vì giả định cache luôn có dữ liệu mới nhất

Khi dùng **Spring Data Redis** và **Spring Cache**, ứng dụng thường lưu bản sao dữ liệu trong Redis để giảm độ trễ và giảm số truy vấn tới database. Cache hit nhanh, Redis trả kết quả thành công và TTL vẫn còn là những tín hiệu vận hành hữu ích. Nhưng **chúng không chứng minh dữ liệu là phiên bản mới nhất**.

Giả sử database đã commit giá sản phẩm mới, còn Redis vẫn giữ giá trước đó. Người dùng đọc từ cache sẽ nhận dữ liệu cũ mà không có exception. Ngay cả khi ứng dụng đã có `@CacheEvict`, cơ chế đồng bộ sau commit hoặc TTL ngắn, vẫn có cửa sổ lỗi và race condition khiến bản cũ được giữ lại hoặc nạp trở lại.

Vì thế, chiến lược cache cần được **kiểm chứng**: nguồn sự thật là gì, mức độ stale được chấp nhận đến đâu, mỗi entry thuộc version nào, sai lệch tồn tại bao lâu, và hệ thống có tự hội tụ khi Redis hoặc tiến trình ứng dụng gặp lỗi không?

Bài học đi từ việc xác định hợp đồng tính nhất quán đến các phương pháp đo, thử nghiệm cạnh tranh, phát hiện cache stale và sửa sai có kiểm soát.

## 1. Cache nhất quán nghĩa là gì?

Giả sử hệ thống có dữ liệu:

```text
Database (nguồn chuẩn):
  productId = 42
  price     = 950000
  version   = 12

Redis cache:
  key       = productsById::42
  price     = 900000
  version   = 11
  ttl       = 180 giây
```

Redis có khóa và thời gian sống còn lại, nhưng cache đang ở **version 11**, trong khi nguồn đã ở **version 12**.

Cần phân biệt:

- **Source of truth:** hệ thống có thẩm quyền xác định trạng thái nghiệp vụ, thường là database hoặc một service nguồn.
- **Cache entry:** bản sao dùng để tối ưu việc đọc; vòng đời của nó có thể khác nguồn.
- **Freshness:** mức độ cache phản ánh trạng thái nguồn tại thời điểm quan sát.
- **Stale read:** lần đọc trả bản cũ hơn trạng thái được công nhận.
- **Convergence:** quá trình cache hội tụ về trạng thái phù hợp khi việc ghi và đồng bộ ổn định.
- **Consistency contract:** bảo đảm mà ứng dụng cam kết đối với người đọc.

Mỗi tính năng có thể cần một hợp đồng khác nhau:

| Yêu cầu | Ý nghĩa | Cách kiểm chứng |
|---|---|---|
| **Eventual consistency** | Khi nguồn ngừng thay đổi và đồng bộ hoạt động, cache cuối cùng hội tụ | Quan sát version đến khi trùng và phát hiện key không hội tụ |
| **Bounded staleness** | Cache không cũ quá ngưỡng được định nghĩa, ví dụ vài giây | Đo từ commit nguồn đến lúc đường đọc phản ánh bản mới |
| **Read-your-writes** | Người vừa ghi nhìn thấy thay đổi của chính mình ở lần đọc sau | Cập nhật rồi GET ngay qua đường API thật |
| **Monotonic reads** | Một phiên đã thấy v12 không bị trả về v11 sau đó | Theo dõi version trong chuỗi request cùng phiên |
| **Độ đúng nghiêm ngặt cho quyết định quan trọng** | Không quyết định dựa duy nhất trên cache có thể stale | Thử khi cache cũ, Redis lỗi, quyền/số dư vừa thay đổi |

Không nên tuyên bố “cache luôn đúng” khi chưa xác định được mức nhất quán nào cần bảo đảm.

## 2. Redis không tự biết database vừa commit

Trong mô hình **cache-aside**, ứng dụng điều phối việc đọc và ghi:

```text
READ:
Client -> Redis GET
           |
           +-- HIT --> Trả cache
           |
           +-- MISS --> Đọc database
                          |
                          +--> Ghi Redis với TTL
                          |
                          +--> Trả dữ liệu

WRITE:
Client -> UPDATE database -> COMMIT
                                |
                                +--> UPDATE / EVICT Redis
```

Redis không tự lắng nghe SQL transaction. Sau khi database commit, ứng dụng phải chủ động invalidation hoặc cập nhật cache. Hai hệ thống có kết nối và giao dịch riêng; một bước có thể thành công trong khi bước kia thất bại.

Ví dụ:

```java
@Transactional
public void updatePrice(long id, BigDecimal price) {
    Product product = repository.findById(id).orElseThrow();
    product.setPrice(price);
    cacheManager.getCache("productsById").evict(id);
}
```

Chỉ nhìn method này chưa thể biết eviction được thực thi trước hay sau commit, vì nó còn phụ thuộc cache manager, transaction synchronization và thời điểm gọi thực tế.

## 3. Điều gì không phải bằng chứng cache mới?

| Quan sát | Điều đã biết | Điều chưa chứng minh |
|---|---|---|
| `GET` Redis trả kết quả | Key đọc được | Giá trị khớp nguồn mới nhất |
| `EXISTS key = 1` | Key tồn tại | Key không stale |
| `TTL key = 180` | Redis còn giữ key | Database không thay đổi trong 180 giây đó |
| Hit ratio 98% | Phần lớn request tránh đọc database | 98% request có dữ liệu đúng |
| `@CacheEvict` được gọi | Ứng dụng yêu cầu xóa | Xóa thành công sau commit và không bị ghi lại bản cũ |
| Event đã publish | Producer đã phát thông điệp | Consumer đã áp dụng vào Redis đúng thứ tự |
| HTTP 200 | API hoạt động theo giao thức | Payload là snapshot đúng theo hợp đồng |

Một hệ thống có thể đạt độ trễ rất thấp nhưng vẫn trả bản cũ trong thời gian dài nếu đường invalidation hỏng.

## 4. Nguồn chuẩn phải được đọc đúng

Giả sử có database primary và read replica:

```text
DB primary:       product 42 version 12
DB read replica:  product 42 version 11
Redis cache:      product 42 version 12
```

Nếu lấy read replica đang trễ làm “đáp án chuẩn”, công cụ đối soát có thể kết luận sai rằng Redis chứa version không hợp lệ.

Để kiểm chứng, cần xác định điểm đọc phù hợp với hợp đồng nguồn, thường là primary sau khi transaction đã commit. Đồng thời phân biệt ba trạng thái:

1. **Source state:** dữ liệu đã commit tại nguồn chuẩn.
2. **Redis state:** dữ liệu đang nằm trong cache.
3. **Response state:** dữ liệu người dùng thực nhận qua controller, có thể đi qua cache local, CDN hoặc service instance khác.

Hai lần đọc Redis và database liên tiếp **không tạo snapshot nguyên tử xuyên hệ thống**. Nếu có ghi đồng thời giữa hai lần đọc, sự khác biệt có thể là trạng thái tạm trong hợp đồng eventual consistency. Vì vậy cần ghi version, thời điểm quan sát và lịch sử event.

## 5. Gắn version nguồn vào DTO cache

Có thể dùng `@Version` của JPA cho entity khi các writer đều tuân theo optimistic locking và quy tắc tăng version.

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
public class Product {
    @Id
    private Long id;

    private String name;
    private BigDecimal price;

    @Version
    private Long version;

    protected Product() {}

    // Constructor, getter/setter thuộc ứng dụng.
}
```

DTO lưu trong cache:

```java
import java.math.BigDecimal;

public record ProductView(
        Long id,
        String name,
        BigDecimal price,
        Long version
) {
    public static ProductView from(Product product) {
        return new ProductView(
                product.getId(),
                product.getName(),
                product.getPrice(),
                product.getVersion());
    }
}
```

Đọc qua Spring Cache:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {
    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productsById", key = "#productId")
    @Transactional(readOnly = true)
    public ProductView getById(long productId) {
        Product product = repository.findById(productId)
                .orElseThrow();
        return ProductView.from(product);
    }
}
```

Khi cache hit, Spring có thể trả DTO từ Redis mà **không gọi method đọc database**. Version trong DTO chính là version của bản được cache, không tự thay đổi khi database commit version khác.

`@Version` chỉ là nguồn version đáng tin cậy nếu mọi đường ghi có thẩm quyền cập nhật version nhất quán. Một câu SQL thủ công hoặc writer khác có thể bỏ qua cơ chế đó. Version cũng chỉ có ý nghĩa trong phạm vi một entity, không phải thứ tự toàn hệ thống.

### Cấu hình RedisCacheManager

```java
import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class CacheConfiguration {
    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory factory) {

        RedisCacheConfiguration productCache =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(5))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(factory)
                .withCacheConfiguration("productsById", productCache)
                .transactionAware()
                .build();
    }
}
```

`transactionAware()` cho phép những cache mutation được hỗ trợ được hoãn đến sau khi Spring transaction commit, **nếu** operation được yêu cầu trong một ngữ cảnh transaction synchronization phù hợp. Nó không tạo giao dịch nguyên tử giữa database và Redis.

Serializer phải tương thích với DTO và môi trường triển khai. Nếu dùng JSON, cần khai báo định dạng và schema rõ ràng; tránh coi lỗi deserialize là cache miss bình thường mà không quan sát nguyên nhân.

## 6. Invalidation sau commit vẫn có thể bị bỏ lỡ

Một service cập nhật:

```java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {
    private final ProductRepository repository;

    public ProductCommandService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "transactionManager")
    @CacheEvict(cacheNames = "productsById", key = "#productId")
    public void changePrice(long productId, BigDecimal newPrice) {
        Product product = repository.findById(productId)
                .orElseThrow();
        product.setPrice(newPrice);
    }
}
```

Ví dụ giả định `transactionManager` là manager database đúng của ứng dụng. Việc đặt `@CacheEvict` cùng `@Transactional` không tự chứng minh thứ tự cache advice so với transaction advice. Phải biết cache operation được gọi ở lúc nào và cache manager nào thực sự tham gia.

Nếu eviction chạy sau commit, vẫn có các tình huống:

```text
DB COMMIT thành công
       |
       +--> App crash trước callback evict
       |
       +--> Redis timeout/mất kết nối
       |
       +--> Event invalidation bị mất
       |
       +--> Request khác ghi lại payload cũ
       |
       v
Redis có thể còn version cũ
```

Database đã commit không tự rollback chỉ vì thao tác Redis sau commit thất bại.

## 7. Race: bản cũ quay lại sau khi eviction thành công

Đây là tình huống quan trọng khi kiểm chứng cache-aside:

```text
Thời điểm    Request A (đọc)             Request B (ghi)
----------------------------------------------------------------
T0           Redis MISS
T1           SQL SELECT -> v11
T2                                        UPDATE -> v12
T3                                        DB COMMIT
T4                                        Redis EVICT key
T5           Redis PUT v11
T6           API trả v11
T7           Request C cache HIT v11
```

A đọc dữ liệu cũ **trước** khi B commit, nhưng cache put **sau** khi B evict. Cả hai đường thao tác riêng lẻ có thể thành công, song Redis cuối cùng chứa v11 khi database đã v12.

**TTL không ngăn race này**: nó chỉ bắt đầu thời gian sống của v11 từ lúc T5. Nếu stale refill tiếp tục diễn ra, cửa sổ dữ liệu cũ có thể kéo dài.

Kiểm chứng cần tái hiện lịch trình T1 → T3 → T4 → T5 có kiểm soát, thay vì chỉ tăng số request và hy vọng lỗi xuất hiện.

## 8. Race: sự kiện cập nhật chạy sai thứ tự

Giả sử hệ thống dùng event:

```text
DB commit v12 -> E12
DB commit v13 -> E13

Consumer xử lý:
  E13 -> cache v13
  E12 -> cache v12  (event cũ được retry muộn)
```

Redis bị **lùi version** dù mọi event đều hợp lệ. Một chính sách phòng vệ:

```text
incomingVersion < cachedVersion -> bỏ qua
incomingVersion = cachedVersion -> xử lý idempotent
incomingVersion > cachedVersion -> chấp nhận
```

Nếu hai consumer thực hiện check version bằng `GET` rồi ghi bằng `SET` thành hai lệnh khác nhau, chúng vẫn có thể xen kẽ. Bước so sánh và ghi cần nguyên tử trong phạm vi key/slot hợp lệ, hoặc chỉ một writer chịu trách nhiệm thứ tự của từng entity.

Khi key đã bị xóa và không còn cachedVersion, event cũ vẫn có thể tạo lại entry stale. Một watermark/tombstone version hoặc một giao thức đồng bộ chặt hơn có thể cần thiết.

## 9. Đo version lag và convergence latency

Có hai câu hỏi khác nhau:

- **Lệch bao nhiêu bản cập nhật?** So sánh `sourceVersion` và `cacheVersion` của cùng entity.
- **Lệch trong bao lâu?** Đo thời gian từ DB commit đến lúc đường đọc được định nghĩa trả version mới.

Một cache envelope có thể chứa:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record VersionedProductCache(
        long productId,
        BigDecimal price,
        long sourceVersion,
        Instant cachedAt
) {}
```

`sourceVersion` là thứ tự nguồn, `cachedAt` là thời điểm ghi cache. Chúng có ý nghĩa khác nhau. Đồng hồ của nhiều server có thể lệch, nên timestamp không thay thế version trong việc xác định thứ tự cập nhật.

Ví dụ bản ghi quan sát:

```text
productId           = 42
sourceVersion       = 13
cacheVersion        = 12
cacheObservedAt     = 2026-11-13T03:00:04Z
lastCommittedEvent  = product-42-v13
eventStatus         = waiting-retry
```

Timestamp và ID chỉ minh họa định dạng. Khi đo thật, cần gắn số đo với thời điểm commit do hệ thống nguồn cung cấp hoặc một cơ chế theo dõi thời gian đủ tin cậy.

## 10. So sánh cache với dữ liệu nguồn độc lập

Không nên gọi lại `getById()` có `@Cacheable` để làm “nguồn đối chiếu”, vì có thể đọc cùng một entry Redis hai lần rồi kết luận nó trùng khớp.

Tạo một đường đọc nguồn:

```java
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductSourceReader {
    private final ProductRepository repository;

    public ProductSourceReader(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Optional<ProductView> readFromSource(long productId) {
        return repository.findById(productId)
                .map(ProductView::from);
    }
}
```

Service này cần được cấu hình đọc đúng datasource nguồn, chẳng hạn primary khi read replica có độ trễ.

Đọc cùng Spring Cache abstraction đang phục vụ ứng dụng:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

Cache cache = cacheManager.getCache("productsById");
if (cache == null) {
    throw new IllegalStateException("Cache missing");
}
ProductView cached = cache.get(42L, ProductView.class);
```

Cách này tránh đoán Redis key prefix hoặc serializer. Khi cần biết bytes và TTL thực tế, có thể bổ sung kiểm tra Redis CLI hoặc RedisTemplate với serializer phù hợp.

| Nguồn chuẩn | Cache | Đánh giá ban đầu |
|---|---|---|
| v13 | v13, field khớp | Match ở thời điểm quan sát |
| v13 | v12 | Stale |
| v13 | Không có entry | Cache miss có thể hợp lệ |
| Không còn entity | Còn entry | Stale orphan, cần xác minh |
| v13 | v14 | Kiểm tra replica lag hoặc nguồn/writer sai |
| v13 | v13, field khác | Version/mapping/serializer có vấn đề |
| Nguồn đọc được | Cache không giải mã được | Cache schema/serialization error |

Một lần so sánh đọc tuần tự không cung cấp snapshot nguyên tử xuyên Redis và database. Nếu có ghi đồng thời, phải xem transaction/commit diễn ra giữa hai lần đọc hay không và tiêu chí eventual consistency đã thỏa chưa.

## 11. Kiểm chứng trên đường API thật

Một entry Redis có thể đã đúng nhưng người dùng vẫn nhận dữ liệu cũ nếu hệ thống có cache ở các tầng khác:

```text
Browser / CDN
      |
      v
Controller
      |
      v
Service / local cache
      |
      v
Spring Redis Cache
      |
      v
Database primary / read replica
```

Nếu yêu cầu **read-your-writes**, phép thử nên thực hiện theo đúng đường người dùng:

1. Client cập nhật product 42 và nhận kết quả xác nhận giao dịch đã commit.
2. Client lập tức gọi GET product 42 qua HTTP API.
3. Kiểm tra response có version hoặc field tương ứng với bản vừa cập nhật.
4. Lặp lại qua nhiều application instance và khi Redis hoặc read replica có độ trễ.
5. Quan sát đường đọc nào trả bản cũ nếu một phép thử thất bại.

Khi Redis đã v13 nhưng HTTP vẫn v12, cần xem local in-memory cache, CDN, serializer, response mapper hoặc instance khác đang chạy code cũ. Không nên sửa Redis ngay nếu nguyên nhân nằm ở tầng trên nó.

## 12. Lấy mẫu kiểm chứng để không phá lợi ích cache

Nếu mỗi cache hit đều truy vấn database để biết cache có đúng không, ứng dụng sẽ gần như mất lợi ích giảm tải của cache.

Những cách kiểm chứng có kiểm soát:

- **Sampling:** lấy một tỷ lệ nhỏ request cache hit, đối chiếu không ảnh hưởng response chính.
- **Đối soát theo lô:** duyệt một tập entity/key trong khoảng thời gian, có phân trang hoặc `SCAN`.
- **Kiểm chứng theo thay đổi:** sau commit, kiểm tra các key vừa thay đổi trong một thời hạn đã chọn.
- **Kiểm chứng theo cảnh báo:** tăng tỷ lệ đo khi consumer lag, lỗi Redis hoặc event retry tăng.
- **Theo phiên người dùng:** ghi nhận các trường hợp read-your-writes violation hoặc version đi lùi.

Ví dụ 20.000 cache hit/giây, sample 0,5% tương đương khoảng 100 lần đọc nguồn bổ sung mỗi giây. Cần đo database có chịu được tải kiểm chứng này không.

Sampling cũng có thể lệch về nhóm khóa hiếm khi thay đổi, trong khi những key nhiều writer dễ stale hơn. Nếu cần đo tỷ lệ sai lệch đáng tin cậy, phân tầng mẫu theo namespace, tần suất cập nhật, instance và mức quan trọng nghiệp vụ.

Một job kiểm chứng nên ưu tiên **đọc và phát hiện sai lệch**, còn job sửa dữ liệu có cơ chế riêng. Nếu nhiều instance tự phát hiện rồi ghi đè cache đồng thời, cơ chế giám sát có thể tạo thêm race hoặc che dấu lỗi gốc.

## 13. Các chỉ số cho thấy cache đúng tới đâu

| Chỉ số | Cách diễn giải | Hạn chế |
|---|---|---|
| Cache hit ratio | Hit / (hit + miss) | Chỉ đo hiệu năng, không đo độ đúng |
| Sample stale rate | Số mẫu có cacheVersion thấp hơn nguồn / số mẫu hợp lệ | Phụ thuộc cách chọn mẫu |
| Version lag | `sourceVersion - cacheVersion` | Chỉ hợp lệ trong cùng domain/version contract |
| Convergence latency | Thời gian từ commit đến khi cache/đường đọc đạt version mới | Cần xác định đúng mốc đo |
| Invalidation failure | Số lần `evict`/update thất bại | Không đếm được những callback hoàn toàn bị mất nếu thiếu event bền vững |
| Outbox/event lag | Thời gian chờ xử lý cập nhật | Cho biết nguy cơ cache stale kéo dài |
| Orphan cache entries | Cache còn entity đã bị xóa ở nguồn | Có thể gây hậu quả nghiệp vụ |
| Serialization errors | Số entry không giải mã được | Cần phân biệt lỗi schema với cache miss |
| Redis timeout/latency | Tình trạng hạ tầng Redis | Không chứng minh mọi key sai |
| Source replica lag | Độ trễ dữ liệu ở read replica | Tránh chẩn đoán nhầm nguồn |
| TTL remaining | Thời gian sống còn lại của các entry | Không phải tuổi dữ liệu tính từ commit |

Ví dụ hợp đồng có thể đo (chỉ để minh họa):

> Trong điều kiện hệ thống hoạt động bình thường, 99,9% các thay đổi sản phẩm đã commit sẽ được phản ánh trên đường GET sản phẩm trong tối đa 5 giây.

Để kiểm tra yêu cầu này phải nói rõ:

- Mốc bắt đầu là database commit, không phải lúc application bắt đầu update.
- Mốc kết thúc là **đường đọc đã trả bản đúng**, hay chỉ Redis bị evict.
- Cách xử lý khi một entity được cập nhật liên tiếp nhiều version.
- Điều kiện đo khi Redis/DB outage; có đưa khoảng lỗi vào SLO không.
- Phạm vi tenant, instance, read replica và thời gian lấy mẫu.

Số event đã publish hoặc số lệnh Redis đã gửi không thay thế được việc đo **dữ liệu người dùng thực sự nhận được**.

## 14. Test race condition có kiểm soát thay vì chờ ngẫu nhiên

Các race hiếm khó xuất hiện trong test tuần tự. Thay vì tạo thật nhiều thread rồi hy vọng có lỗi, nên cố định lịch trình các bước quan trọng.

### Kịch bản A — Stale refill sau eviction

```text
1. Xóa entry cache product 42.
2. Đặt DB tại version 11.
3. Request A cache MISS rồi SELECT version 11.
4. Tạm dừng A trước bước cache PUT.
5. Request B UPDATE version 12 và COMMIT.
6. Request B EVICT cache key; xác nhận evict thành công.
7. Cho A tiếp tục PUT version 11.
8. Kiểm tra cache và HTTP GET đang trả version nào.
9. Quan sát cơ chế phòng vệ có sửa được stale v11 không.
```

Test tích hợp có thể dùng `CountDownLatch` hoặc gateway test đặt điểm dừng đúng sau SQL read/trước cache put. Nếu khó can thiệp vào interceptor của Spring Cache, có thể tạo một harness cache-aside riêng chỉ để tái hiện lịch trình này.

### Kịch bản B — Redis thất bại sau DB commit

```text
1. Cache có version 11.
2. Transaction cập nhật nguồn lên version 12.
3. SQL COMMIT thành công.
4. Giả lập Redis timeout đúng khi invalidation/update.
5. Xác nhận DB vẫn version 12.
6. Quan sát Redis còn v11 hay không.
7. Khôi phục Redis.
8. Theo dõi retry, TTL, event/outbox hoặc reconciliation.
9. Đo đến khi GET trả version 12.
```

Thực hiện fault injection trên môi trường thử nghiệm. Nếu callback sau commit thất bại, database đã commit **không tự rollback**.

### Kịch bản C — Event đảo thứ tự

```text
1. Commit DB v12 và phát event E12.
2. Commit DB v13 và phát event E13.
3. Cho consumer nhận E13 trước.
4. Cho E12 retry đến muộn.
5. Assert Redis không lùi về v12 nếu hệ thống hứa monotonic update.
```

Nếu không có version gating, test này có thể cho thấy cache bị ghi lùi. Nếu chỉ dùng eviction, test cần tập trung vào khả năng stale refill và đường đọc sau khi các event chạy xong.

### Kịch bản D — SQL rollback

```text
1. Bắt đầu transaction.
2. Cập nhật entity và yêu cầu cache mutation.
3. Ném RuntimeException trước commit.
4. Xác nhận database rollback.
5. Kiểm tra Redis không chứa dữ liệu chưa từng commit.
```

Cần xác định cache operation được gọi bên trong transaction synchronization, Spring AOP advisor được áp dụng đúng và RedisCacheManager thực sự `transactionAware()`.

### Kịch bản E — Đọc từ database replica trễ

```text
1. Primary DB đã version 12.
2. Read replica vẫn version 11.
3. Redis bị evict.
4. Cache miss đọc từ replica v11.
5. Ứng dụng đưa v11 vào Redis.
6. So sánh Redis với primary và kiểm tra khả năng hội tụ.
```

Test này giúp phân biệt vấn đề cache stale và độ trễ nguồn nạp.

## 15. Version gating có thể chặn cập nhật lùi

Khi ứng dụng **tự quản lý** cache entry (khác với RedisCacheManager mặc định), có thể lưu version và payload chung trong một Redis Hash:

```text
product-cache:42 (HASH)
  version = 13
  payload = {"id":42,"price":950000}
```

Script Lua kiểm tra và ghi nguyên tử trong cùng một key:

```lua
-- KEYS[1] = cache key
-- ARGV[1] = incoming version
-- ARGV[2] = payload đã serialize
-- ARGV[3] = TTL giây, số nguyên dương

local incoming = tonumber(ARGV[1])
local ttl = tonumber(ARGV[3])

if not incoming or not ttl or ttl <= 0 then
    return -1
end

local oldRaw = redis.call('HGET', KEYS[1], 'version')
local oldVersion = tonumber(oldRaw)

if oldRaw and not oldVersion then
    return -2
end

if oldVersion and incoming < oldVersion then
    return 0
end

redis.call('HSET', KEYS[1],
           'version', ARGV[1],
           'payload', ARGV[2])
redis.call('EXPIRE', KEYS[1], ttl)
return 1
```

Giao ước kết quả: `1` là chấp nhận ghi, `0` là từ chối version cũ, `-1` là input không hợp lệ, `-2` là version hiện có sai định dạng. Spring Data Redis có thể dùng `DefaultRedisScript<Long>` và `StringRedisTemplate.execute(...)` cho script một key này.

Cần hiểu rõ giới hạn:

- Đây là **Hash cache tự quản**, không tự tương thích với entry mà RedisCacheManager mặc định serialize theo định dạng khác.
- Nếu key đã bị xóa, không còn version để chặn một event cũ tái tạo cache. Có thể cần watermark/tombstone hoặc cơ chế kiểm tra nguồn khác.
- Nếu hai event cùng version nhưng payload khác, ứng dụng phải xác định quy tắc đúng thay vì cho ghi đè tùy ý.
- Version cần được cấp tăng nhất quán bởi nguồn; các writer SQL thủ công không được bỏ qua nó.
- Lua có giới hạn số nguyên và Redis Cluster có quy tắc hash slot riêng.
- Atomicity trên Redis key không tạo atomic commit giữa SQL và Redis.

Version gating là một biện pháp phòng stale overwrite, **không thay thế kiểm chứng hệ thống và chiến lược phục hồi**.

## 16. TTL không tự giới hạn được staleness tính từ commit

Giả sử cache entry có TTL 300 giây:

```text
T0  Database COMMIT version 12
T1  Request cũ PUT version 11, TTL 300s
T2  Worker khác PUT lại version 11, TTL được làm mới
T3  Redis vẫn trả version 11
```

TTL giới hạn thời gian sống của **mỗi lần ghi entry**, không nhất thiết giới hạn thời gian kể từ lúc source commit. Nếu một nguồn đọc chậm hoặc event cũ tiếp tục ghi lại dữ liệu, TTL có thể bị reset liên tục.

Vì vậy muốn đặt bounded staleness phải kiểm soát:

- Nguồn dùng để refill cache là primary hay read replica?
- Có writer nào có thể ghi lùi version?
- Cơ chế invalidation có retry khi thất bại không?
- Có job đối soát xử lý entry tồn đọng không?
- Việc refresh cache có làm TTL bắt đầu lại không?
- SLO đo từ commit của source hay từ lần ghi cache?

Giảm TTL có thể tăng miss rate và tải database mà chưa giải quyết race.

## 17. Evict hay cập nhật cache trực tiếp?

Hai chiến lược thường gặp:

**Invalidate on write:** sau DB commit, xóa cache entry để lần đọc tiếp theo lấy lại từ nguồn.

```text
DB COMMIT v13
     |
     v
EVICT cache
     |
     v
Next GET MISS -> SELECT v13 -> cache v13
```

**Update on write:** sau DB commit, ghi payload mới trực tiếp vào Redis.

```text
DB COMMIT v13
     |
     v
PUT cache payload v13
     |
     v
Next GET HIT v13
```

| Tiêu chí | Evict | Update |
|---|---|---|
| Dữ liệu gửi Redis | Key cần xóa | Payload và version |
| Đường đọc tiếp theo | Thường miss | Thường hit |
| Rủi ro chính | Evict thất bại, stale refill | Event đảo thứ tự, stale overwrite |
| Phòng vệ | TTL, retry, reconciliation | Version gating, ordering, idempotency |
| Nguyên tử với DB | Không | Không |

Evict thường dễ sử dụng khi database là nguồn sự thật; update phù hợp khi muốn giữ cache nóng. Cả hai cần được kiểm chứng với lỗi hạ tầng và cập nhật đồng thời.

## 18. Transactional outbox giúp không mất yêu cầu đồng bộ

Nếu chỉ dựa vào một callback `@TransactionalEventListener(AFTER_COMMIT)` trong bộ nhớ, process có thể dừng sau DB commit nhưng trước khi callback gửi yêu cầu cache update. Event đó không tự được lưu lại để replay.

**Transactional outbox** lưu thay đổi nghiệp vụ và yêu cầu đồng bộ trong **cùng một transaction database**:

```text
Request
   |
   v
DB transaction
  /           \
 v             v
UPDATE entity  INSERT outbox event
  \           /
     COMMIT
        |
        v
Durable pending event
        |
        v
Worker -> Redis update/evict
       /      \
    Success   Failure
      |         |
   Mark done   Retry
```

Quy trình:

1. Ghi thay đổi dữ liệu và bản ghi outbox trong cùng giao dịch SQL.
2. Commit thành công để event trở thành bền vững.
3. Consumer lấy event chưa xử lý và cập nhật Redis.
4. Nếu lỗi, retry; nếu thành công, đánh dấu đã xử lý.
5. Dùng event ID/version để chống áp dụng trùng hoặc sai thứ tự.
6. Theo dõi độ trễ từ DB commit đến Redis được đồng bộ.

Ví dụ ý tưởng:

```java
@Transactional
public void changePrice(long productId, BigDecimal price) {
    Product product = repository.findById(productId).orElseThrow();
    product.setPrice(price);

    outboxRepository.save(
            OutboxEvent.productChanged(productId));
}
```

Nếu event phải chứa version sau cập nhật, cần xác định thời điểm JPA cập nhật `@Version` (flush/commit) và cách đọc version đáng tin cậy. Không tự cho rằng version trong bộ nhớ đã tăng đúng trước mọi lần flush.

Outbox cung cấp cơ chế **khôi phục sau crash**, nhưng cache thường vẫn đạt eventual consistency và consumer có thể xử lý event lặp. Cần idempotency, retry và xử lý thứ tự.

## 19. Xử lý một entry stale có kiểm soát

Một quy trình có thể dùng khi phát hiện cache không khớp:

1. **Xác nhận nguồn:** đọc bản đã commit ở primary hoặc nguồn đúng thẩm quyền.
2. **Chụp bằng chứng:** ID, sourceVersion, cacheVersion, TTL, thời điểm, event ID/offset; tránh log dữ liệu nhạy cảm.
3. **Xác định nguyên nhân:** event mất/trễ, stale refill, writer ngoài luồng, serializer, local cache, database replica lag.
4. **Dừng lỗi đang lặp:** điều chỉnh writer hoặc consumer sai thứ tự trước khi sửa nhiều key.
5. **Repair đúng phạm vi:** evict hoặc refresh theo version, replay outbox, đối soát key theo lô có giới hạn.
6. **Xác nhận lại đường đọc thật:** HTTP GET và cache state có hội tụ không; bản cũ có xuất hiện lại không?
7. **Theo dõi sau sửa:** metric mismatch, event lag, Redis errors và thời gian hội tụ.

Không dùng `FLUSHDB` hay `KEYS *` trên production chỉ để sửa một entry stale. Khi kiểm kê nhiều key, dùng `SCAN` theo từng node/primary phù hợp và giới hạn tốc độ. Redis Cluster không có một cursor toàn cluster, và quét trong lúc dữ liệu thay đổi không cho snapshot nhất quán.

## 20. Nhiều lớp cache và Redis Cluster

```text
Client
  |
  v
Browser / CDN cache
  |
  v
Spring application local cache (nếu có)
  |
  v
Redis Cluster / Redis replica
  |
  v
Database primary / read replicas
```

Redis có thể đã v13 trong khi HTTP vẫn trả v12 từ CDN hoặc một app instance giữ local cache cũ. Ngược lại, Redis reader có thể đọc từ replica Redis chưa kịp nhận thay đổi, hoặc cache miss nạp v11 từ database read replica trong khi primary đã v12.

Trong Redis Cluster, một key thuộc một hash slot; truy vấn một node không đại diện toàn bộ cluster. Khi đối soát cần xác định node đang phục vụ key, tình trạng failover/resharding và cách client chọn primary/replica.

Khi ghi nhận lỗi, nên lưu route đọc, tên cache, key/version, instance và nguồn dữ liệu đã quan sát. Nếu không biết entry đến từ tầng nào, rất dễ sửa nhầm Redis trong khi lỗi nằm ở nơi khác.

## 21. Bài thực hành tự đánh giá

**1.** Redis trả `TTL=200`, có thể kết luận cache mới nhất không?  
**Không.** TTL chỉ nói key còn sống, không cho biết version nguồn.

**2.** `@CacheEvict` chạy sau commit thành công thì không còn race nào?  
**Không.** Request đọc dữ liệu cũ trước commit có thể PUT lại bản đó sau khi eviction đã chạy.

**3.** Vì sao `@Version` hữu ích hơn chỉ dùng `cachedAt` để so sánh?  
**Version** phản ánh thứ tự cập nhật nguồn nếu các writer tuân thủ quy ước, còn cachedAt phản ánh thời điểm cache được tạo và có thể chịu lệch đồng hồ.

**4.** Event v13 chạy trước v12 thì giải pháp nào giúp không bị lùi?  
**Version-aware conditional update**, thực hiện kiểm tra và ghi nguyên tử trong phạm vi key hợp lệ, kết hợp idempotency/ordering.

**5.** Nếu DB commit thành công nhưng Redis timeout khi evict, `@Transactional` có rollback database lại không?  
**Không.** Đó là khoảng lỗi xuyên hai tài nguyên; cần retry, outbox hoặc đối soát.

**6.** Tại sao đọc nguồn bằng method `@Cacheable` không phù hợp khi đối soát?  
Nó có thể trả chính cache entry cần kiểm tra, khiến phép so sánh không độc lập.

**7.** Vì sao cache version 14 và database read replica version 13 chưa đủ chứng minh cache sai?  
Replica có thể trễ; phải kiểm tra primary hoặc nguồn phù hợp.

**8.** Có thể bảo đảm stale dưới 5 phút chỉ bằng TTL 5 phút không?  
Không nếu có cơ chế refill/refresh tiếp tục ghi lại dữ liệu cũ và reset TTL.

**9.** Vì sao outbox hữu ích hơn callback after-commit in-memory khi Redis bị lỗi?  
Event đã được lưu bền vững cùng DB transaction và có thể replay sau khi worker khôi phục.

**10.** Kiểm chứng xong Redis key đúng đã đủ khẳng định người dùng nhận đúng chưa?  
Chưa. Cần thử qua HTTP/service thật vì có thể còn cache local, CDN hoặc nguồn đọc khác.

## 22. Ghi nhớ khi triển khai

- Xác định **nguồn sự thật** và mức nhất quán mỗi nghiệp vụ thực sự cần.
- Gắn **source version** vào payload hoặc metadata cache khi phù hợp.
- Đo **độ đúng** bên cạnh hit ratio và latency: stale rate, version lag, convergence latency và lỗi invalidation.
- Kiểm chứng bằng **đường đọc nguồn độc lập**, không gọi lại cùng method có `@Cacheable`.
- Tái hiện race theo lịch trình cố định: stale refill, event đảo thứ tự, rollback và Redis lỗi sau commit.
- Dùng TTL như một lớp bảo vệ, **không coi TTL là bằng chứng về độ mới**.
- Dùng `transactionAware()` và các callback after-commit để giảm cập nhật trước commit, nhưng hiểu rằng chúng không tạo atomicity SQL + Redis.
- Khi cần phục hồi đáng tin cậy, dùng outbox/retry/idempotency cùng kiểm chứng đường đọc.
- Khi sửa stale cache, giới hạn phạm vi và xác nhận lại **dữ liệu HTTP người dùng thực nhận**.

Câu hỏi quan trọng cần trả lời là: **“Sau khi nguồn commit một version mới, bằng chứng nào cho thấy người dùng sẽ đọc được version đúng trong khoảng thời gian mà nghiệp vụ cho phép?”** Một chiến lược cache tốt phải có cách đo và thử nghiệm câu trả lời đó.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): RedisCacheManager, RedisCacheConfiguration, TTL và cách tổ chức cache.
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CachePut`, `@CacheEvict` và cache interceptor.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxy và rollback.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và `AFTER_COMMIT`.
- [Spring Framework — Transaction-aware Cache Decorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): thao tác cache được hoãn sau commit.
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): RedisTemplate và Spring transaction synchronization.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/): semantics của TTL.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): duyệt keyspace theo cursor để kiểm chứng có giới hạn.

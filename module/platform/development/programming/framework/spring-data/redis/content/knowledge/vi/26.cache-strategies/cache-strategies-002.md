# Phân biệt cập nhật cache, vô hiệu hóa cache và nguồn dữ liệu chuẩn trong Spring Data Redis

## 1. Bài toán: dữ liệu đã thay đổi nhưng người dùng vẫn nhìn thấy giá trị cũ

Một ứng dụng Spring Boot lưu thông tin sản phẩm trong PostgreSQL, đồng thời dùng Spring Data Redis làm cache để giảm số lần đọc database. Khi người dùng mở trang sản phẩm, ứng dụng đọc dữ liệu từ Redis nếu đã có. Khi quản trị viên đổi giá, bản ghi database được cập nhật. Tuy nhiên, nếu Redis vẫn giữ giá cũ, người dùng khác có thể nhìn thấy thông tin sai.

Ví dụ:

~~~text
09:00  Database: product#42.price = 100
       Redis:    productById::42 = price 100

09:05  Quản trị viên đổi giá thành 120
       Database: product#42.price = 120

09:06  Người dùng gọi GET /products/42
       Redis:    productById::42 = price 100
       API trả:  price 100  <-- dữ liệu cũ
~~~

Để xử lý chính xác, cần phân biệt ba khái niệm:

1. **Nguồn dữ liệu chuẩn (source of truth):** nơi có thẩm quyền quyết định trạng thái nghiệp vụ đúng.
2. **Cập nhật cache (cache update):** ghi ngay giá trị mới vào bản sao cache khi dữ liệu thay đổi.
3. **Vô hiệu hóa cache (cache invalidation):** xóa hoặc đánh dấu bản sao đã lỗi thời, để lần đọc sau tạo lại cache từ nguồn chuẩn.

Ba khái niệm có quan hệ nhưng không đồng nhất. **Cập nhật cache** và **vô hiệu hóa cache** là hai cách đồng bộ bản sao; còn **nguồn dữ liệu chuẩn** quyết định bản sao phải phản ánh điều gì.

> Một cache trả lời nhanh chỉ có giá trị khi hệ thống biết dữ liệu đó được phép cũ đến đâu, khi nào phải làm mới và làm sao phục hồi khi Redis hoặc ứng dụng gặp sự cố.

## 2. Nguồn dữ liệu chuẩn là gì?

**Source of truth** là thành phần được thiết kế để giữ trạng thái có thẩm quyền, phục vụ việc kiểm tra, quyết định và phục hồi dữ liệu. Với một hệ thống đặt hàng thông thường, database giao dịch có thể là nguồn chuẩn cho:

- Giá sản phẩm chính thức.
- Trạng thái đơn hàng.
- Số dư tài khoản.
- Tồn kho khả dụng.
- Quyền truy cập của người dùng.
- Lịch sử thay đổi cần kiểm toán.

Redis Cache trong kiến trúc đó chỉ là **bản sao có thể tái tạo** từ nguồn chuẩn. Nếu Redis mất dữ liệu, ứng dụng có thể đọc database rồi tạo cache mới. Nếu Redis và database bất đồng, dữ liệu có thẩm quyền là trạng thái database theo quy tắc nghiệp vụ.

~~~text
                           +-----------------------------+
                           | Database                    |
                           | Source of truth             |
                           | product#42.price = 120      |
                           +--------------+--------------+
                                          |
                         đọc dữ liệu / tạo lại bản sao
                                          |
                                          v
                           +-----------------------------+
                           | Redis Cache                 |
                           | productById::42 = price 120 |
                           +--------------+--------------+
                                          |
                                          v
                                     Spring API
~~~

### Redis có thể là nguồn dữ liệu chuẩn không?

**Có**, nếu hệ thống chủ động thiết kế Redis giữ trạng thái nghiệp vụ có thẩm quyền. Ví dụ một bộ đếm hoặc trạng thái giới hạn tốc độ có thể được quản lý trực tiếp trong Redis. Khi đó cần đánh giá persistence, replication, durability, failover, tính nguyên tử và cách phục hồi.

Không nên mặc định “Redis luôn chỉ là cache” hoặc “Redis nhanh nên cứ lưu dữ liệu chuẩn ở đó”. **Vai trò của Redis do kiến trúc và bảo đảm của dữ liệu quyết định**, không do tên công nghệ.

Trong bài này, để minh họa Spring Cache và Spring Data Redis, chúng ta giả định:

~~~text
PostgreSQL = nguồn dữ liệu chuẩn
Redis      = cache của dữ liệu đọc
Spring     = điều phối truy vấn, ghi và invalidation
~~~

Quy tắc nhất quán cần thống nhất: cập nhật nghiệp vụ phải thành công ở nguồn chuẩn trước khi hệ thống coi thay đổi đã hoàn tất.

## 3. Phân biệt cập nhật cache và vô hiệu hóa cache

Hai chiến lược xử lý bản sao sau khi nguồn chuẩn thay đổi:

### Cập nhật cache

Sau khi ghi dữ liệu mới thành công, ứng dụng đặt trực tiếp giá trị mới vào Redis:

~~~text
Ghi product.price = 120 vào database
           |
           v
Ghi productById::42 = price 120 vào Redis
           |
           v
Lần đọc tiếp theo có thể lấy giá mới từ Redis
~~~

**Ưu điểm:** những lần đọc sau không nhất thiết truy vấn database để tái tạo dữ liệu. Phù hợp khi ứng dụng đã có đủ giá trị mới, key được xác định rõ và chi phí tạo bản sao đáng kể.

**Rủi ro:** ghi database thành công nhưng ghi cache lỗi, hoặc bản sao bị ghi theo thứ tự sai trong cạnh tranh đồng thời. Nếu một bản ghi có nhiều cache view khác nhau, phải cập nhật chính xác mọi bản sao liên quan.

### Vô hiệu hóa cache

Sau khi dữ liệu ở nguồn chuẩn được cập nhật, ứng dụng xóa cache key có thể đã lỗi thời:

~~~text
Ghi product.price = 120 vào database
           |
           v
Xóa productById::42 khỏi Redis
           |
           v
Lần đọc tiếp theo: cache miss
           |
           v
Đọc database -> tạo cache với price 120
~~~

**Ưu điểm:** không cần tính toán ngay nội dung của tất cả bản sao; lần đọc sau lấy lại từ nguồn chuẩn. Thường dễ bảo trì khi dữ liệu có nhiều biểu diễn khác nhau.

**Rủi ro:** lần đọc đầu sau invalidation chậm hơn vì phải truy vấn nguồn chuẩn. Việc xóa cache vẫn có thể lỗi, tới muộn hoặc cạnh tranh với luồng đang nạp giá trị cũ.

### Bảng so sánh

| Tiêu chí | Cập nhật cache | Vô hiệu hóa cache |
| --- | --- | --- |
| Hành động | Ghi giá trị mới vào Redis | Xóa/đánh dấu bản sao cũ |
| Cần biết giá trị mới | Có | Không nhất thiết |
| Lần đọc kế tiếp | Thường cache hit | Thường cache miss rồi tái tạo |
| Chi phí lúc ghi | Có thể cần serialize và ghi nhiều cache entry | Thường chỉ cần xóa các key liên quan |
| Chi phí lúc đọc | Thấp nếu cập nhật thành công | Có lần đọc từ nguồn chuẩn sau khi xóa |
| Nguy cơ | Ghi giá trị cũ đè giá trị mới, bỏ sót derived views | Invalidation bị mất hoặc có race nạp cache |
| Trường hợp phù hợp | Giá trị mới rõ ràng, đọc rất nhiều, key đơn giản | Read model phức tạp, nhiều bản sao, có thể nạp lại |

Hai chiến lược đều cần một **quy tắc thời điểm**: khi nào được phép sửa Redis so với thời điểm transaction nguồn chuẩn commit.

## 4. Cache-aside: mô hình thông dụng với Spring Data Redis

**Cache-aside** (lazy loading) là mô hình:

- Khi đọc, thử lấy từ cache.
- Nếu cache miss, đọc nguồn chuẩn rồi ghi kết quả vào cache.
- Khi thay đổi dữ liệu, ứng dụng cập nhật hoặc xóa cache theo quy tắc đã chọn.

Sơ đồ đường đọc:

~~~text
GET /products/42
        |
        v
Redis GET productById::42
        |
        +------ HIT ------> Trả ProductView
        |
        +------ MISS
               |
               v
        Database SELECT product#42
               |
               v
        Redis SET productById::42 + TTL
               |
               v
        Trả ProductView
~~~

Spring Cache abstraction có thể triển khai phần lớn đường đọc bằng `@Cacheable`. Spring Data Redis cung cấp `RedisCacheManager` và `RedisCache` để dữ liệu thực tế nằm ở Redis.

Điểm quan trọng: **`@Cacheable` không có nghĩa Redis trở thành nguồn chuẩn.** Annotation mô tả cách tái sử dụng kết quả phương thức. Nguồn chuẩn vẫn là repository/database mà phương thức truy vấn.

## 5. Ví dụ Spring Boot: database chuẩn, Redis là cache

Giả sử một entity `Product` được quản lý bằng Spring Data JPA:

~~~java
import java.math.BigDecimal;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Product {

    @Id
    private Long id;

    private String name;

    private BigDecimal price;

    @Version
    private Long version;

    protected Product() {
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public Long getVersion() { return version; }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        this.price = newPrice;
    }
}
~~~

DTO chỉ chứa những gì API cần trả về:

~~~java
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
            product.getVersion()
        );
    }
}
~~~

Repository cơ sở dữ liệu:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductJpaRepository
        extends JpaRepository<Product, Long> {
}
~~~

Trong mô hình này:

- `ProductJpaRepository` thao tác với database chuẩn.
- `ProductView` là snapshot dùng để trả về API và lưu cache.
- `Product.version` giúp nhận diện phiên bản dữ liệu, hữu ích khi chẩn đoán hoặc xây cơ chế chống ghi cache ngược thứ tự.

Không nên mặc định cache trực tiếp một JPA entity chứa lazy relationship, Hibernate proxy hoặc trạng thái persistence context. DTO thường là lựa chọn dễ tuần tự hóa, có contract ổn định và ít kéo dữ liệu thừa.

## 6. Cấu hình RedisCacheManager và TTL

Với các dependency tương ứng như Spring Cache, Spring Data Redis và Spring Data JPA, có thể bật caching và cấu hình Redis:

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        var json = new GenericJackson2JsonRedisSerializer();

        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .serializeValuesWith(
                    RedisSerializationContext.SerializationPair
                        .fromSerializer(json)
                )
                .entryTtl(Duration.ofMinutes(5))
                .disableCachingNullValues();

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaults)
            .withInitialCacheConfigurations(
                Map.of(
                    "productById",
                    defaults.entryTtl(Duration.ofMinutes(5)),
                    "productList",
                    defaults.entryTtl(Duration.ofMinutes(1))
                )
            )
            .build();
    }
}
~~~

Với cách cấu hình này:

- Cache `productById` có TTL 5 phút.
- Cache `productList` có TTL 1 phút.
- Giá trị được tuần tự hóa theo JSON serializer đã chọn.
- Không cache kết quả `null`.
- Spring Cache quản lý key trong namespace cache name, thường có dạng `productById::42` với cấu hình mặc định.

**Lưu ý phiên bản:** tên API cấu hình và lựa chọn JSON serializer có thể khác giữa các thế hệ Spring Data Redis/Spring Boot. Khi sử dụng, chọn phiên bản dependency nhất quán với ứng dụng. Serializer có type metadata cần được cấu hình và kiểm soát tương thích với DTO đáng tin cậy, đặc biệt khi có nhiều phiên bản dịch vụ cùng đọc cache.

### TTL giải quyết vấn đề gì?

TTL giới hạn thời gian Redis giữ một entry chưa được làm mới. Nếu bước invalidation không xảy ra, một TTL ngắn có thể giúp bản sao cũ tự biến mất sau khoảng thời gian nhất định.

Tuy nhiên, TTL **không bảo đảm dữ liệu luôn mới ngay khi database cập nhật**. Ví dụ TTL 5 phút có thể khiến người dùng thấy giá cũ trong phần còn lại của thời gian sống nếu ứng dụng không xóa/ghi lại cache.

Ngoài ra, khi cache hết TTL, lần đọc tiếp theo phải có cơ chế nạp lại từ nguồn chuẩn. TTL chỉ điều khiển vòng đời entry, không quyết định nghiệp vụ có được phép đọc giá cũ hay không.

## 7. Đọc dữ liệu bằng @Cacheable

Tạo service truy vấn:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {

    private final ProductJpaRepository products;

    public ProductQueryService(ProductJpaRepository products) {
        this.products = products;
    }

    @Transactional(readOnly = true)
    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductView getById(Long id) {
        Product product = products.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Product not found: " + id)
            );

        return ProductView.from(product);
    }
}
~~~

Luồng:

~~~text
getById(42)
    |
    +-- Có productById::42 -> lấy ProductView từ Redis
    |
    +-- Không có -> chạy method, query DB,
                    serialize ProductView và cache
~~~

`@Cacheable` thường được triển khai bằng Spring AOP proxy. Khi cache hit, thân method có thể không chạy; khi miss, method chạy và kết quả được cache nếu thao tác thành công.

**Không dùng `@Cacheable` để bảo vệ điều kiện luôn cần kiểm tra theo thời gian thực**, chẳng hạn xác thực quyền truy cập nhạy cảm hoặc chặn thanh toán sau hạn, trừ khi hệ thống đã định nghĩa rõ độ cũ được chấp nhận và cách kiểm tra lại nguồn chuẩn.

### Self-invocation

Nếu một method trong cùng bean gọi `this.getById(id)`, lời gọi nội bộ có thể đi thẳng vào object thay vì đi qua Spring proxy, nên cache annotation không được áp dụng như kỳ vọng trong chế độ proxy mặc định.

Cách tổ chức an toàn là để controller hoặc service khác gọi public method qua bean Spring, hoặc tách query cache thành một bean riêng.

## 8. Cập nhật cache với @CachePut

`@CachePut` yêu cầu Spring **thực thi method** và sau đó đưa kết quả của method vào cache theo key đã chọn.

Ví dụ về ý tưởng:

~~~java
import java.math.BigDecimal;

import org.springframework.cache.annotation.CachePut;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductUpdateWithCachePutService {

    private final ProductJpaRepository products;

    public ProductUpdateWithCachePutService(
            ProductJpaRepository products) {
        this.products = products;
    }

    @Transactional
    @CachePut(cacheNames = "productById", key = "#result.id")
    public ProductView changePrice(Long id, BigDecimal newPrice) {
        Product product = products.findById(id)
            .orElseThrow();

        product.changePrice(newPrice);
        Product saved = products.saveAndFlush(product);

        return ProductView.from(saved);
    }
}
~~~

Sau khi method trả về, `@CachePut` cố ghi `ProductView` mới vào entry `productById::42`. Khác `@Cacheable`, nó **không bỏ qua method chỉ vì cache đã có dữ liệu**.

Lợi ích của `@CachePut` là caller có ngay dữ liệu mới và cache có cơ hội được cập nhật cho request đọc tiếp theo.

### Cảnh báo về giao dịch

Ví dụ trên dùng để minh họa API. `saveAndFlush` **không tương đương database transaction đã commit**. Tùy cấu hình advisor, transaction manager và thứ tự AOP interceptor, thao tác cache và việc commit có thể không xảy ra theo thứ tự mà người viết mong muốn.

Nếu cập nhật cache trước khi transaction thực sự commit và database sau đó rollback, cache có thể chứa giá trị **chưa bao giờ trở thành dữ liệu chuẩn**.

Đối với nghiệp vụ yêu cầu tính nhất quán sau commit, nên tách bước cache update/invalidation khỏi thời điểm method ghi dữ liệu và thực hiện sau khi transaction commit thành công. Phần tiếp theo minh họa cơ chế đó.

## 9. Vô hiệu hóa cache với @CacheEvict

`@CacheEvict` dùng để xóa entry tương ứng với key:

~~~java
import java.math.BigDecimal;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductUpdateWithEvictService {

    private final ProductJpaRepository products;

    public ProductUpdateWithEvictService(
            ProductJpaRepository products) {
        this.products = products;
    }

    @Transactional
    @CacheEvict(cacheNames = "productById", key = "#id")
    public void changePrice(Long id, BigDecimal newPrice) {
        Product product = products.findById(id)
            .orElseThrow();

        product.changePrice(newPrice);
        products.save(product);
    }
}
~~~

Với mặc định `beforeInvocation = false`, cache được evict khi lời gọi method hoàn tất thành công theo cơ chế interceptor. Nếu method ném exception trước khi hoàn tất, evict thường không được thực hiện.

Tuy vậy, **method hoàn tất không luôn đồng nghĩa transaction đã commit**, nên nếu tính đúng phụ thuộc vào việc commit thật sự, hãy dùng một cơ chế sau commit rõ ràng.

### Có nên dùng beforeInvocation = true?

~~~java
@CacheEvict(
    cacheNames = "productById",
    key = "#id",
    beforeInvocation = true
)
~~~

Tùy chọn này xóa cache **trước khi chạy method**, kể cả nếu method sau đó thất bại. Nó có thể hữu ích trong những tình huống đặc biệt, nhưng với cập nhật database thường gây rủi ro:

~~~text
Cache bị xóa
    |
    v
Request đọc mới nạp dữ liệu cũ từ DB
    |
    v
Transaction ghi vẫn chưa commit
    |
    v
Cache vừa được tái tạo từ dữ liệu cũ
~~~

Do đó không nên chọn `beforeInvocation = true` như một cách chung để “bảo đảm dữ liệu mới”.

## 10. Vô hiệu hóa sau khi transaction commit

Một thiết kế dễ lập luận hơn là:

1. Transaction ghi dữ liệu vào nguồn chuẩn.
2. Trong transaction phát một domain event mô tả ID đã thay đổi.
3. Sau khi commit thành công, listener xóa cache key tương ứng.
4. Lần đọc sau cache miss và nạp dữ liệu mới.

Tạo event nội bộ:

~~~java
public record ProductChanged(Long productId) {
}
~~~

Service ghi:

~~~java
import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {

    private final ProductJpaRepository products;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductJpaRepository products,
            ApplicationEventPublisher events) {
        this.products = products;
        this.events = events;
    }

    @Transactional
    public void changePrice(Long id, BigDecimal newPrice) {
        Product product = products.findById(id)
            .orElseThrow();

        product.changePrice(newPrice);
        products.save(product);

        events.publishEvent(new ProductChanged(id));
    }
}
~~~

Listener chạy sau commit:

~~~java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCacheInvalidationListener {

    private final CacheManager caches;

    public ProductCacheInvalidationListener(CacheManager caches) {
        this.caches = caches;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterProductChanged(ProductChanged event) {
        Cache cache = caches.getCache("productById");

        if (cache != null) {
            cache.evict(event.productId());
        }
    }
}
~~~

Với đường gọi đã có một transaction Spring được quản lý:

~~~text
changePrice()
  |
  v
Database UPDATE trong transaction
  |
  v
publish ProductChanged(id)
  |
  v
Database COMMIT thành công
  |
  v
AFTER_COMMIT listener
  |
  v
Redis Cache.evict(id)
~~~

Nếu transaction rollback, `AFTER_COMMIT` listener không thực hiện bước evict của transaction đó.

### Giới hạn của AFTER_COMMIT

Đây là cách tốt để xếp thứ tự thao tác **trong tiến trình ứng dụng còn hoạt động**, nhưng vẫn không làm database và Redis trở thành một transaction nguyên tử.

Ví dụ:

~~~text
DB commit thành công
    |
    +---- JVM crash trước khi AFTER_COMMIT evict
          |
          +---- Redis có thể tiếp tục giữ giá trị cũ
~~~

Nếu Redis đang lỗi, callback có thể không xóa được cache. Với một hệ thống chịu được độ cũ trong TTL, có thể dựa vào TTL như cơ chế phục hồi cuối cùng. Với yêu cầu phải xóa cache chắc chắn, cần **transactional outbox**, retry và/hoặc quản lý phiên bản dữ liệu. Các cách này được giải thích ở phần sau.

### Sự kiện nội bộ không phải message queue bền vững

`ApplicationEventPublisher` và `@TransactionalEventListener` không tự lưu message vào database. Nếu process chết đúng khoảng giữa commit và invalidation, sự kiện trong bộ nhớ có thể mất. Không gọi cơ chế này là “đảm bảo giao hàng”.

## 11. Cập nhật cache sau commit khác gì vô hiệu hóa sau commit?

Khi đã đặt đúng thời điểm sau commit, vẫn phải chọn hành động:

~~~text
Sau DB commit:
  Option A: cache.put(id, newProductView)
  Option B: cache.evict(id)
~~~

**Cập nhật trực tiếp** hợp lý khi:

- Payload mới đã được xác định đáng tin cậy.
- Một ID tương ứng với một entry hoặc ít cache view.
- Chi phí tạo lại từ database cao.
- Có cơ chế xử lý thứ tự các lần ghi khi nhiều request chạy đồng thời.

**Vô hiệu hóa** hợp lý khi:

- Một thay đổi ảnh hưởng nhiều dạng dữ liệu tổng hợp.
- Cache chứa kết quả join, giá theo ưu đãi hoặc read model phức tạp.
- Giá trị mới không dễ tính ở luồng ghi.
- Chấp nhận một cache miss sau khi thay đổi.

Có thể tạo listener sau commit để `cache.put(...)` bằng cách event mang dữ liệu mới. Tuy nhiên, event snapshot trước commit có thể không phản ánh các trường được database tự sinh, trigger thay đổi hoặc quy tắc xử lý khác. Nếu cần snapshot chính xác, cân nhắc đọc dữ liệu đã commit rồi cache, đồng thời bảo vệ race với update mới hơn.

## 12. Một giá trị bị cache ở nhiều nơi: invalidation không chỉ là xóa một key

Giả sử hệ thống có:

~~~text
productById::42
productList::category-books::page-0
featuredProducts::today
productSearch::keyword-spring::sort-price
sellerSummary::17
~~~

Khi giá của sản phẩm 42 thay đổi, những bản sao liên quan có thể cùng lỗi thời. Chỉ xóa `productById::42` sẽ không khiến danh sách sản phẩm, kết quả tìm kiếm hay thống kê người bán tự cập nhật.

Có ba hướng phổ biến:

1. **Xóa những cache key phụ thuộc đã biết.** Cần định nghĩa rõ dependency và quy tắc key.
2. **Xóa cả cache region hoặc tăng phiên bản namespace** khi không dễ tìm tất cả key liên quan.
3. **Chấp nhận độ cũ có giới hạn**, dùng TTL ngắn cho danh sách tổng hợp ít quan trọng.

Ví dụ, dữ liệu chi tiết có thể invalidation theo ID chính xác; danh sách giới thiệu có TTL 30 giây và được nạp lại định kỳ. Chiến lược cần phù hợp với yêu cầu sản phẩm.

### @Caching cho nhiều entry xác định

Khi biết rõ cache và key liên quan, có thể kết hợp:

~~~java
import org.springframework.cache.annotation.Caching;
import org.springframework.cache.annotation.CacheEvict;

@Caching(evict = {
    @CacheEvict(cacheNames = "productById", key = "#id"),
    @CacheEvict(
        cacheNames = "productSummaryById",
        key = "#id"
    )
})
public void refreshProductCaches(Long id) {
    // Method chịu trách nhiệm thao tác nghiệp vụ thích hợp.
}
~~~

Đoạn trên minh họa cú pháp nhiều invalidation. Nó không tự bảo đảm xóa sau commit hay xóa những cache key mà ứng dụng chưa liệt kê. Với dữ liệu bắt buộc đồng bộ theo transaction, vẫn nên gắn thao tác vào luồng sau commit/outbox.

### Cẩn trọng với allEntries

~~~java
@CacheEvict(cacheNames = "productList", allEntries = true)
~~~

`allEntries = true` yêu cầu xóa toàn bộ entry trong cache region. Với Redis, chi phí và cơ chế clear phụ thuộc cache writer/cấu hình, số lượng key và cách quét key. Khi region rất lớn hoặc nhiều ứng dụng cùng dùng Redis, xóa hàng loạt có thể tạo tải đáng kể.

Nên ưu tiên key cụ thể hoặc thiết kế namespace/version hợp lý nếu có thể.

## 13. Phân biệt cache update, invalidate và write-through/write-behind

Các thuật ngữ thường bị dùng lẫn:

| Mô hình | Đọc | Ghi | Điểm cần lưu ý |
| --- | --- | --- | --- |
| Cache-aside | Ứng dụng đọc cache, miss thì DB và cache | Ứng dụng chủ động evict/put | Phổ biến với Spring Cache |
| Read-through | Thành phần cache tự tải từ nguồn khi miss | Tùy thiết kế | Khả năng này tùy hệ cache |
| Write-through | Đường ghi cập nhật nguồn chuẩn và cache theo cơ chế đã định | Ghi đồng bộ qua tầng chịu trách nhiệm | Không tự bảo đảm transaction DB + Redis |
| Write-behind/write-back | Cache nhận ghi rồi đẩy xuống nguồn khác sau | Bất đồng bộ | Có nguy cơ mất dữ liệu nếu cơ chế queue/durability không đủ |
| Invalidate-on-write | Đọc qua cache | Ghi DB rồi xóa bản sao cũ | Lần đọc sau tạo lại cache |

**`@CachePut` không tự động biến mọi ứng dụng thành hệ thống write-through có transaction xuyên database và Redis.** Nó chỉ là một cơ chế đưa kết quả method vào cache theo proxy của Spring.

Tương tự, dùng Redis làm write-behind không tự giải quyết độ bền dữ liệu. Nếu cần ghi bắt buộc, phải định nghĩa nguồn chuẩn và cơ chế đảm bảo giao hàng, retry, thứ tự sự kiện và khả năng phục hồi.

## 14. Trình tự ghi sai có thể tạo dữ liệu cũ trong cache

### Trường hợp A: cập nhật Redis trước database

~~~text
T0  Redis PUT price=120
T1  Client đọc Redis -> 120
T2  Database transaction rollback -> giá chuẩn vẫn 100
T3  Redis vẫn giữ 120
~~~

Giá trong cache có thể chưa từng tồn tại ở nguồn chuẩn. Vì vậy, nếu database là nguồn chuẩn, tránh coi thao tác cache trước commit là bằng chứng thay đổi nghiệp vụ đã thành công.

### Trường hợp B: commit xong nhưng evict thất bại

~~~text
T0  Database commit price=120
T1  Redis connection lỗi, evict thất bại
T2  Client đọc Redis price=100
T3  TTL hết, Redis loại entry cũ
T4  Client nạp lại price=120
~~~

Đây là lý do phải xác định **mức chấp nhận stale data**. Nếu chấp nhận giá cũ tối đa vài phút, TTL có thể là biện pháp giới hạn. Nếu tuyệt đối không chấp nhận, chỉ TTL chưa đủ.

### Trường hợp C: hai cập nhật đồng thời viết cache sai thứ tự

~~~text
Writer A: DB commit version 7, price=110
Writer B: DB commit version 8, price=120

Writer B: cache.put(price=120, version=8)
Writer A: cache.put(price=110, version=7)  <-- chạy muộn

Redis cuối cùng: version 7, dù DB đã là version 8.
~~~

Chỉ vì mỗi thao tác PUT là nguyên tử ở Redis không có nghĩa **trình tự write cache khớp trình tự commit database**. Một value có thể được ghi lại bởi một event cũ.

Có thể cân nhắc:

- Invalidate thay vì ghi snapshot từ callback cũ.
- Ghi cache với so sánh version atomically, chỉ cho phép version mới hơn.
- Key theo version khi ứng dụng có cách lấy version có thẩm quyền.
- Dùng một luồng xử lý được điều phối thứ tự theo entity.
- Cho dữ liệu cần nhất quán mạnh đọc trực tiếp nguồn chuẩn.

Mỗi biện pháp cần một contract và kiểm thử race condition cụ thể. Không thể chỉ thêm trường `version` vào DTO rồi mặc nhiên giải quyết được vấn đề.

## 15. Race ngay cả khi chỉ vô hiệu hóa sau commit

Một tình huống tinh vi:

~~~text
Reader A                      Writer B                 Redis/DB
--------                      --------                 --------
Cache MISS ------------------------------------------> Redis không có key
Đọc DB version 7 ------------------------------------> DB trả version 7
                              Ghi version 8
                              COMMIT
                              EVICT key -------------> Redis xóa key
Reader A PUT version 7 ------------------------------> Redis chứa version 7
~~~

Dù Writer B đã evict **sau commit**, Reader A vẫn có thể nạp giá trị cũ vào cache **sau khi evict**. Điều này xảy ra khi quá trình cache fill của Reader A bị kéo dài qua lúc Writer B cập nhật.

Vì vậy, invalidation sau commit là một chiến lược rất hữu ích nhưng **không phải lời chứng minh tính nhất quán tuyến tính** cho mọi thao tác đọc/ghi cạnh tranh.

Những lựa chọn khi race quan trọng:

- Giới hạn TTL và chấp nhận cửa sổ stale có biên độ đã biết.
- Dùng version làm phần của key, với phiên bản nguồn được xác định đáng tin cậy.
- Chỉ cache snapshot nếu version không cũ hơn trạng thái cache/nguồn được kiểm tra bằng thao tác nguyên tử phù hợp.
- Sắp xếp truy cập theo khóa với cơ chế đồng bộ đã thiết kế, chú ý tính phân tán.
- Đọc nguồn chuẩn cho quyết định nhạy cảm.

Một thiết kế có bảo đảm chặt cần xem toàn bộ vòng đời **cache miss -> read DB -> populate Redis**, không chỉ đường update.

## 16. TTL, eviction và invalidation khác nhau

Ba thuật ngữ này có thể xuất hiện cùng lúc nhưng ý nghĩa khác nhau.

| Khái niệm | Kích hoạt | Mục tiêu |
| --- | --- | --- |
| TTL expiration | Thời hạn của cache entry đã qua | Giới hạn thời gian sống |
| Cache invalidation | Ứng dụng biết dữ liệu gốc đã đổi | Loại bỏ bản sao lỗi thời |
| Redis memory eviction | Redis cần giải phóng bộ nhớ theo `maxmemory-policy` | Quản lý giới hạn bộ nhớ |

Ví dụ Redis tự xóa entry vì TTL 5 phút không chứng minh database vừa thay đổi. Và khi Redis loại key vì áp lực bộ nhớ, đó cũng không phải sự kiện nghiệp vụ “sản phẩm đã được cập nhật”.

Đừng thiết kế quy trình cập nhật nghiệp vụ dựa duy nhất vào Redis `expired` hoặc `evicted`. Keyspace notification qua Pub/Sub có thể đến muộn hoặc bị bỏ lỡ khi listener offline; cache miss phải có đường đọc nguồn chuẩn.

### TTL là cơ chế bảo vệ cuối cùng, không phải invalidation ngay lập tức

Nếu yêu cầu “giá sau khi đổi phải nhìn thấy trong vòng 1 giây”, TTL 5 phút không đáp ứng. Nếu yêu cầu “bài viết gợi ý có thể cũ khoảng 1 phút”, TTL 60 giây có thể phù hợp.

TTL nên phản ánh **mức độ chấp nhận dữ liệu cũ**, tần suất thay đổi, chi phí đọc nguồn và lưu lượng. Không chọn TTL chỉ vì một giá trị cấu hình trông có vẻ phổ biến.

## 17. Đánh giá độ nhất quán theo từng loại dữ liệu

Không phải mọi dữ liệu cần cùng một chiến lược.

| Loại dữ liệu | Tính đúng quan trọng | Hướng triển khai |
| --- | --- | --- |
| Danh mục sản phẩm | Chấp nhận cập nhật chậm ngắn hạn | Cache-aside + invalidation + TTL |
| Danh sách bài viết gợi ý | Có thể cũ vài phút | TTL và tái tạo lazy |
| Giá hiển thị | Cần xác định mức stale chấp nhận | Evict/put sau commit; xác minh khi checkout |
| Tồn kho | Không được oversell | Quyết định giữ hàng ở nguồn chuẩn/atomic operation, cache chỉ hỗ trợ hiển thị |
| Số dư tài khoản | Cần tính đúng cao | Không dựa vào cache cho quyết định chuyển tiền |
| Quyền truy cập nhạy cảm | Thường cần có hiệu lực nhanh | Kiểm tra nguồn có thẩm quyền, version/revocation |
| Báo cáo dashboard | Có thể eventual consistency | Cache tổng hợp TTL, refresh theo batch |
| Trạng thái giao hàng | Chấp nhận một độ trễ xác định | Event-driven invalidation + TTL dự phòng |

Một API có thể dùng cache để hiển thị tồn kho ước lượng, nhưng thao tác `POST /reserve` phải kiểm tra và giảm tồn kho tại nơi có thẩm quyền theo cơ chế nguyên tử. Người dùng nhìn thấy “còn 2” trên trang không có nghĩa hệ thống được phép bán 2 sản phẩm mà không kiểm tra lại.

## 18. Khi nào nên vô hiệu hóa, khi nào nên ghi đè cache?

### Ưu tiên invalidation nếu dữ liệu có nhiều biểu diễn

Ví dụ đổi giá sản phẩm có thể ảnh hưởng đến:

~~~text
Chi tiết sản phẩm
Danh sách sản phẩm theo danh mục
Kết quả lọc theo khoảng giá
Sản phẩm khuyến nghị
Tổng giá trị giỏ hàng
Thống kê doanh thu dự kiến
~~~

Việc tính lại tất cả view ngay trong request cập nhật có thể phức tạp và dễ thiếu. Invalidate view trực tiếp biết được, đặt TTL cho các view còn lại, hoặc chuyển việc tái tạo sang worker theo dependency đã thiết kế.

### Ưu tiên update nếu payload mới rõ ràng và đọc lại rất đắt

Ví dụ cache chi tiết của một cấu hình nhỏ do chính service ghi. Sau commit, có thể đặt trực tiếp snapshot đã xác nhận vào cache, tránh cache miss.

Tuy nhiên, khi có nhiều writer cùng cập nhật, hãy cân nhắc version và thứ tự cập nhật cache. `cache.put` đơn thuần có thể khiến bản ghi cũ ghi đè bản ghi mới nếu callback chạy sai thứ tự.

### Trộn chiến lược một cách có chủ đích

Một hệ thống thực tế có thể:

~~~text
Sau khi cập nhật Product#42:
  - productById::42      -> evict
  - featuredProducts     -> evict
  - productList::*       -> TTL ngắn, làm mới theo nhu cầu
  - productSearch        -> đồng bộ qua index pipeline riêng
~~~

Không bắt buộc toàn bộ cache trong ứng dụng phải có cùng một cách cập nhật. Quan trọng là có một **bảng phụ thuộc dữ liệu** hoặc quy ước rõ ràng cho mỗi cache region.

## 19. Redis và Spring Cache không cùng một lớp trừu tượng

Spring Data Redis có cả API thao tác Redis trực tiếp và tích hợp Spring Cache.

| Lớp API | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| Spring Cache abstraction | `@Cacheable`, `@CachePut`, `@CacheEvict` | Quy tắc cache theo method |
| Spring Cache manager | `CacheManager`, `Cache` | Cách truy cập cache theo tên/key |
| Spring Data Redis cache | `RedisCacheManager`, `RedisCache` | Triển khai cache bằng Redis |
| Spring Data Redis data operations | `StringRedisTemplate`, `RedisTemplate` | Thao tác key, hash, set, sorted set ... |
| Nguồn dữ liệu chuẩn | `JpaRepository`/database hoặc hệ có thẩm quyền khác | Xác định trạng thái nghiệp vụ |

Nếu ứng dụng cache thông qua `@Cacheable(cacheNames="productById")`, cách an toàn để xóa entry là dùng cùng abstraction:

~~~java
Cache cache = cacheManager.getCache("productById");
if (cache != null) {
    cache.evict(42L);
}
~~~

Không tự suy đoán Redis key rồi gọi:

~~~java
stringRedisTemplate.delete("productById::42");
~~~

trừ khi đã kiểm soát rõ RedisCacheConfiguration, key prefix và key conversion. Cache manager có thể thay đổi prefix, serialization hoặc namespace khiến key thực tế khác điều người viết đoán.

### Cache key là một phần của contract

Nếu một nơi cache với `key="#id"` nhưng nơi khác evict với `key="#product.id"`, hãy đảm bảo giá trị thực tế tương đương. Trường hợp key có tenant, locale, currency hoặc version còn phức tạp hơn:

~~~java
@Cacheable(
    cacheNames = "productByTenant",
    key = "#tenantId + ':' + #productId"
)
public ProductView getProduct(String tenantId, Long productId) {
    // ...
}
~~~

Khi invalidation, phải dùng chính contract `tenantId:productId`. Không xóa riêng `productId` rồi tưởng đã vô hiệu hóa các entry theo tenant.

Nếu lược tenant khỏi cache key trong hệ thống nhiều tenant, dữ liệu có thể bị trả nhầm giữa tenant. Đây là lỗi phân vùng dữ liệu, không chỉ lỗi hiệu năng.

## 20. Cấu hình serializer và thay đổi schema cache

Redis lưu bytes; giá trị DTO phải được tuần tự hóa và giải mã. Khi dùng RedisCacheManager, cần thống nhất:

- Key format, cache prefix và namespace.
- Serializer của value.
- Kiểu DTO và field được cache.
- TTL, null caching và kích thước dữ liệu.
- Cách xử lý khi một phiên bản ứng dụng không đọc được value của bản khác.

Ví dụ:

~~~text
App v1 cache:
  productById::42 -> { "id": 42, "price": 100 }

App v2 mong đợi:
  productById::42 -> { "id": 42, "price": 120, "currency": "VND" }
~~~

Nếu v2 bắt buộc có `currency` mà bản cache cũ thiếu, cần một trong những cách:

1. Thiết kế DTO tương thích ngược hoặc giá trị mặc định an toàn.
2. Tăng namespace/cache name: `productByIdV2`.
3. Vô hiệu hóa cache cũ trong rollout có kiểm soát.
4. Dùng TTL và lộ trình migration thích hợp.

Cập nhật serializer không tự chuyển bytes cũ. Khi gặp lỗi deserialize, ứng dụng cần chính sách fail-open về cache (đọc database) hoặc fail-closed tùy rủi ro; không nên làm hỏng toàn bộ nghiệp vụ chỉ vì một cache entry không còn tương thích nếu cache chỉ là bản sao tùy chọn.

### Lưu dữ liệu nhạy cảm trong cache

Dù Redis là cache, dữ liệu vẫn được lưu ở mạng/bộ nhớ hệ thống. Tránh cache trực tiếp credential, token bí mật hoặc thông tin cá nhân không cần thiết. Khi cần cache thông tin nhạy cảm, áp dụng quyền truy cập, mã hóa nếu phù hợp, TTL và quy tắc tenant isolation.

## 21. Khi có nhiều instance ứng dụng

Với ba instance Spring Boot cùng dùng một Redis Cache:

~~~text
App A ----+
          |
App B ----+------ Redis Cache ------ Database
          |
App C ----+
~~~

Một invalidation thực hiện trên Redis chung có thể khiến cả ba instance đều miss ở request tiếp theo nếu chúng chỉ dùng Redis cache.

Nhưng hệ thống có thể có thêm **L1 local cache** (ví dụ Caffeine) ở mỗi JVM:

~~~text
App A: L1 local cache
App B: L1 local cache
App C: L1 local cache
              |
              v
          Redis L2
              |
              v
          Database
~~~

Nếu chỉ xóa Redis L2, các L1 local vẫn có thể giữ dữ liệu cũ. Cần quy tắc invalidation cho **tất cả tầng cache**. Redis Pub/Sub có thể được dùng như tín hiệu thông báo tới các instance, nhưng Pub/Sub không lưu message để phát lại khi instance offline.

Nếu yêu cầu mạnh, cần TTL/version cho L1 hoặc cơ chế durable invalidation và đối soát, thay vì tin rằng mọi notification đều được nhận.

## 22. Event-driven invalidation và transactional outbox

Khi thay đổi Product, service có thể phát event như `ProductChanged(productId=42, version=8)`. Một consumer nhận event rồi xóa Redis cache hoặc xây lại read model.

~~~text
Transaction ghi dữ liệu chuẩn
         |
         +--> UPDATE product
         |
         +--> INSERT outbox_event
         |
         v
       COMMIT
         |
         v
Worker đọc outbox có retry
         |
         v
Redis EVICT / UPDATE
         |
         v
Đánh dấu event đã xử lý
~~~

**Transactional outbox** giải quyết cửa sổ “database commit thành công nhưng ứng dụng chết trước khi gửi event” bằng cách lưu thông tin cần xử lý trong **cùng database transaction**.

Cần chú ý:

- Worker có thể nhận và xử lý cùng event nhiều lần; invalidation theo key thường là idempotent, còn put cần kiểm soát version.
- Outbox cần retry, theo dõi backlog và không xóa bản ghi công việc trước khi xác nhận xử lý.
- Nếu một entity có nhiều lần thay đổi, event có thể tới consumer không theo thứ tự mong muốn; phải xét ordering/version.
- Dữ liệu đọc ở replica hoặc read model có độ trễ có thể chưa phản ánh commit mới nhất tại thời điểm invalidation.
- Một hệ thống đang offline không thể làm mới cache đúng hạn; kiến trúc phải định nghĩa mức độ stale được phép và đường fallback.

Outbox giúp làm việc **có thể phục hồi**, nhưng không tự biến database và Redis thành cùng một transaction phân tán. Đối với thao tác cần độ đúng tuyệt đối, vẫn kiểm tra nguồn chuẩn hoặc dùng giao thức nhất quán phù hợp.

## 23. Cache stampede sau invalidation

Khi một cache key nóng bị xóa, nhiều request cùng đến có thể đều nhìn thấy cache miss:

~~~text
Evict productById::42
         |
         +--> Request A: MISS -> query DB
         +--> Request B: MISS -> query DB
         +--> Request C: MISS -> query DB
         +--> Request D: MISS -> query DB
         +--> Request E: MISS -> query DB
~~~

Hiện tượng này thường gọi là **cache stampede/thundering herd**.

Các cách giảm:

- Chọn TTL hợp lý và có jitter để tránh nhiều key hết hạn đồng thời.
- Làm nóng các key cực nóng sau invalidation có kiểm soát.
- Giới hạn số request đồng thời được phép nạp cùng key.
- Dùng single-flight/coalescing ở tầng thích hợp.
- Dùng Redis lock có thời hạn khi thực sự cần, đồng thời thiết kế fallback và giải phóng lock an toàn.
- Tối ưu truy vấn nguồn chuẩn, batching và connection pool.

### @Cacheable(sync = true) có giải quyết toàn bộ không?

~~~java
@Cacheable(
    cacheNames = "productById",
    key = "#id",
    sync = true
)
~~~

`sync = true` yêu cầu tầng cache hỗ trợ đồng bộ việc tạo giá trị cho cùng key. Hiệu lực cụ thể phụ thuộc cache provider và cấu hình. **Không nên mặc định nó là một distributed lock hoàn chỉnh qua nhiều JVM hoặc bảo đảm mọi instance chỉ query DB một lần.**

Cần kiểm tra hành vi của RedisCacheManager và cache writer trong phiên bản ứng dụng trước khi dựa vào cơ chế này để chống stampede ở quy mô phân tán.

## 24. Negative caching và khi dữ liệu được tạo mới

Một API tìm sản phẩm theo ID có thể trả “không tồn tại”. Để giảm truy vấn database lặp lại cho ID không tồn tại, có thể cache kết quả âm (negative caching) trong thời gian ngắn.

Nhưng nếu cache kết quả “không tồn tại” quá lâu:

~~~text
T0  GET product#99 -> không tồn tại -> cache NOT_FOUND
T1  CREATE product#99 trong DB
T2  GET product#99 -> cache NOT_FOUND cũ
~~~

Khóa mới đã tồn tại ở nguồn chuẩn nhưng cache làm người dùng không nhìn thấy.

Giải pháp:

- Đặt TTL ngắn hơn cho kết quả âm so với kết quả tồn tại.
- Khi tạo mới entity, invalidation đúng key.
- Phân biệt “không tồn tại” với “database đang lỗi”; không cache lỗi hệ thống thành NOT_FOUND.
- Không cache kết quả từ nguồn có độ trễ replica theo cách gây stale quá lâu.

`disableCachingNullValues()` trong RedisCacheConfiguration giúp tránh một lớp lỗi khi trả `null`; tuy vậy, nếu ứng dụng trả wrapper hoặc đối tượng `NotFoundResult`, nó vẫn có thể được cache theo thiết kế. Cần định nghĩa contract âm rõ ràng.

## 25. Cache update có thể gây lỗi khi nguồn chuẩn đã commit

Ví dụ:

~~~text
1. Database COMMIT thành công.
2. Ứng dụng gọi cache.put(newValue).
3. Redis timeout.
4. API trả lỗi cho client.
~~~

Client có thể hiểu rằng cập nhật không thành công và gửi lại, dù dữ liệu chuẩn đã đổi. Đây là dạng **partial failure** giữa hệ thống lưu trữ chính và cache.

Với cache là tối ưu hóa tùy chọn, một số hệ thống chọn:

- Ghi nguồn chuẩn là kết quả nghiệp vụ chính.
- Invalidation/update cache chạy best effort, có retry/metric.
- Cache lỗi thì đọc database.
- TTL giới hạn thời gian entry cũ còn tồn tại.

Với dữ liệu không được phép stale, phải nâng mức bảo đảm bằng cơ chế durable invalidation, read validation/versioning hoặc bỏ cache khỏi đường quyết định. Không dùng cách “bỏ qua mọi exception Redis” một cách mù quáng nếu ứng dụng đang dùng Redis để giữ trạng thái nghiệp vụ chuẩn khác với cache.

### CacheErrorHandler

Spring Cache có cơ chế `CacheErrorHandler` tùy chỉnh để quyết định xử lý lỗi cache ở mức `get`, `put`, `evict` và `clear`. Có thể chọn phản hồi thích hợp tùy loại lỗi và vai trò của cache.

Dù cho phép request tiếp tục khi cache lỗi, vẫn phải log/metric để phát hiện Redis không còn đáp ứng kỳ vọng, đặc biệt khi invalidation không thành công sẽ làm tăng stale reads.

## 26. Kiểm thử các bất biến của chiến lược cache

Bài toán cache có thể “chạy đúng” trong test đơn luồng mà vẫn lỗi khi nhiều request đồng thời. Nên kiểm thử bằng dữ liệu và Redis thực cho những đường quan trọng, đồng thời tách kiểm thử logic nghiệp vụ và kiểm thử tính nhất quán.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Cache miss lần đầu | Đọc database và lưu snapshot có TTL |
| Cache hit | Trả snapshot cache phù hợp |
| Cập nhật database rồi evict | Lần đọc kế tiếp nạp giá trị mới |
| Database transaction rollback | Không xuất hiện dữ liệu chưa commit trong cache |
| Redis lỗi lúc evict | Có cảnh báo/metric và cơ chế fallback phù hợp |
| Hai writer cập nhật cùng ID | Không coi giá trị cache cũ là nguồn quyết định |
| Reader miss cạnh tranh với writer | Chiến lược xử lý được cửa sổ stale theo yêu cầu |
| Cache entry hết TTL | API nạp lại từ nguồn chuẩn |
| Schema cache thay đổi | Có migration hoặc namespace version tương thích |
| Entity mới được tạo sau negative cache | Key âm được invalidation hoặc tự hết hạn đúng mức |
| Nhiều instance | Invalidation có tác dụng tới các tầng cache liên quan |
| Tenant khác nhau cùng product ID | Không đọc nhầm cache giữa tenant |

### Ví dụ kiểm thử luồng cơ bản

Pseudocode:

~~~java
// Arrange
database.save(new Product(42L, "Book", price("100")));
cache.evict(42L);

// Act: lần đọc đầu tạo cache
ProductView first = queryService.getById(42L);

// Update dữ liệu chuẩn và invalidation sau commit
commandService.changePrice(42L, price("120"));

// Assert: lần đọc sau nhận dữ liệu mới
ProductView latest = queryService.getById(42L);
assertThat(latest.price()).isEqualByComparingTo("120");
~~~

Đây là **pseudocode kiểm thử luồng**, không phải một test class có thể copy chạy nguyên vẹn: constructor entity, helper `price` và ranh giới transaction cần triển khai theo ứng dụng thật.

Nếu cần chứng minh độ nhất quán sau commit, dùng integration test có database và Redis test riêng, tạo hai transaction/luồng có điều phối để tái hiện race. Mock chỉ kiểm tra số lần gọi `cache.evict` không chứng minh giá trị có đúng sau một lần commit hay không.

## 27. Chẩn đoán khi dữ liệu cache cũ không biến mất

Có thể dùng một trình tự điều tra:

**Bước 1 — Xác định nguồn chuẩn.** Kiểm tra database có thật sự commit giá trị mới hay transaction đã rollback. Xác định có đọc replica chậm hơn primary hay không.

**Bước 2 — Xác định cache key.** Kiểm tra `cacheNames`, biểu thức `key`, prefix, tenant, version và serializer. Không giả định key Redis là key Java nguyên văn.

**Bước 3 — Kiểm tra đường invalidation.** Method có đi qua Spring AOP proxy không? Có self-invocation không? Event `AFTER_COMMIT` đã chạy chưa? Có lỗi kết nối Redis hoặc listener không?

**Bước 4 — Kiểm tra cạnh tranh.** Có request cache miss nào đọc DB cũ rồi ghi cache sau invalidation không? Có event/callback cũ nào `cache.put` đè snapshot mới không?

**Bước 5 — Kiểm tra tầng khác.** Có Caffeine L1, CDN, reverse proxy, browser cache hoặc HTTP caching ngoài Redis không?

**Bước 6 — Kiểm tra TTL và schema.** Entry có TTL đúng không, liệu việc truy cập đang gia hạn TTL theo chính sách nào, hay dữ liệu không còn tương thích serializer?

**Bước 7 — Xác định yêu cầu business.** Dữ liệu có bắt buộc mạnh nhất quán hay được chấp nhận stale trong thời gian ngắn?

Một số lệnh quan sát trên Redis trong môi trường phù hợp:

~~~bash
redis-cli TTL 'productById::42'
redis-cli PTTL 'productById::42'
redis-cli EXISTS 'productById::42'
redis-cli INFO stats
redis-cli INFO memory
~~~

Các lệnh này chỉ hữu ích nếu biết **đúng key vật lý** do RedisCacheManager tạo ra; cấu hình prefix hoặc serializer có thể thay đổi tên thực tế. Đừng dùng `KEYS *` như công cụ thường xuyên trong production có nhiều key; nếu cần duyệt, cân nhắc `SCAN` theo batch.

## 28. Metrics cho cache strategy

Để biết chiến lược có thật sự hữu ích, không chỉ quan sát “Redis vẫn chạy”.

Những chỉ số có ý nghĩa:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Cache hit ratio | Bao nhiêu lần đọc được phục vụ từ cache? |
| Cache miss rate | Tần suất phải truy vấn nguồn chuẩn? |
| Redis GET/SET/DEL latency | Cache có thực sự giảm latency tổng không? |
| Database read p95/p99 | Stampede sau invalidation có làm DB chậm không? |
| Cache invalidation errors | Có lần xóa cache nào thất bại? |
| Entry age / data version mismatch | Bao nhiêu bản sao đang lỗi thời? |
| Redis memory usage / evictions | Bộ nhớ và chính sách `maxmemory` có gây áp lực? |
| Cache refill traffic | Sau deploy/invalidation hàng loạt có burst vào DB không? |
| Outbox backlog | Có bao nhiêu sự kiện invalidation chưa xử lý? |
| Stale read incidents | Người dùng có nhận dữ liệu cũ quá mức cho phép? |

Redis `keyspace notifications` và `expired_keys` không tự cho biết tất cả cache entry đã bị invalidation đúng theo thay đổi database. Cần kết hợp metric ở tầng ứng dụng, nguồn chuẩn và event processing.

### Log có correlation ID và version

Một dòng log hữu ích:

~~~text
event=product_cache_evicted
product_id=42
db_version=8
cache_name=productById
cause=product_updated
trace_id=...
~~~

Không log toàn bộ nội dung nhạy cảm trong cache chỉ để chẩn đoán invalidation. ID và version thường đủ để nối các sự kiện.

## 29. Thiết kế cache cho hệ thống nhiều vùng hoặc nhiều Redis

Khi ứng dụng chạy ở nhiều region hoặc có nhiều Redis cluster độc lập:

~~~text
Region A               Region B
--------               --------
Spring A               Spring B
Redis A                Redis B
       \               /
        \             /
         Central database
~~~

Sau khi database cập nhật, xóa cache ở Redis A **không tự xóa** Redis B. Nếu cache được nhân bản giữa region, cần cơ chế invalidation phát tới mọi vùng, versioning hoặc TTL phù hợp.

Nếu một vùng bị ngắt mạng và nhận event muộn, cache ở vùng đó có thể tiếp tục giữ dữ liệu cũ. Không nên suy diễn chỉ vì tất cả instance cùng dùng “Redis” thì thực tế chúng cùng một namespace và cùng trạng thái.

Khi yêu cầu độ nhất quán mạnh trên nhiều vùng, độ trễ phân tán và cơ chế điều phối phức tạp hơn nhiều; dữ liệu quyết định nghiệp vụ nên quay về nguồn chuẩn hoặc sử dụng một giao thức nhất quán được thiết kế cụ thể.

## 30. Bài tập tình huống: thay đổi giá sản phẩm

Giả sử một hệ thống có:

~~~text
Database:
  products(id, name, price, version)

Redis cache:
  productById
  productList
  recommendedProducts

Luồng:
  GET /products/{id}
  GET /products?category=...
  PATCH /products/{id}/price
~~~

Yêu cầu:

- Khi người quản trị đổi giá, database phải commit giá mới.
- API chi tiết sản phẩm nên nhìn thấy giá mới nhanh.
- Danh sách sản phẩm có thể trễ tối đa 30 giây.
- Thanh toán phải tính bằng giá hợp lệ từ nguồn chuẩn tại thời điểm chốt đơn.
- Hệ thống có nhiều instance Spring Boot.

Một thiết kế khả thi:

1. **Database là nguồn chuẩn** của giá và version sản phẩm.
2. `productById` dùng `@Cacheable` với TTL ngắn và evict theo ID sau commit.
3. `productList` có TTL 30 giây; nếu có dependency rõ, chủ động evict key danh sách liên quan.
4. Khi checkout, không coi giá snapshot ở Redis là thẩm quyền cuối cùng; xác định giá từ database theo quy tắc giao dịch.
5. Nếu invalidation cần phục hồi qua crash, lưu outbox event cùng transaction update.
6. Khi event có thể đến sai thứ tự, dùng version hoặc chỉ evict để tránh snapshot cũ ghi đè snapshot mới.
7. Theo dõi tỉ lệ cache miss, invalidation errors, stale reads và ảnh hưởng tới database.

Sơ đồ:

~~~text
PATCH price
    |
    v
Database transaction
  UPDATE product / version
  INSERT outbox event (nếu cần)
    |
    v
COMMIT
    |
    +--> Evict productById::42
    +--> Invalidate dependent views / TTL
    |
    v
GET /products/42
    |
    +--> MISS -> DB version mới -> Redis -> API

POST /checkout
    |
    v
Xác minh giá và các điều kiện tại nguồn chuẩn
~~~

### Câu hỏi tự đánh giá

- Nếu cache bị lỗi trong lúc DB vẫn hoạt động, API nên tiếp tục đọc DB hay từ chối?
- Nếu một request đang nạp version 7 cùng lúc writer commit version 8, làm sao ngăn version 7 tồn tại quá lâu?
- Nếu Redis A được evict nhưng Redis B ở region khác chưa nhận event, mức trễ nào chấp nhận được?
- Nếu `ProductView` thay đổi schema giữa hai release, làm sao tránh lỗi deserialize cache cũ?
- Nếu một sản phẩm xuất hiện trong 50 danh sách, nên update 50 cache entry hay invalidate/TTL theo nhóm?
- Nếu yêu cầu số dư hay tồn kho chính xác tuyệt đối, có nên dùng Redis cache để quyết định thành công giao dịch không?

Những câu hỏi này cho thấy chiến lược cache là một **quyết định về tính đúng dữ liệu**, không chỉ là một annotation tối ưu tốc độ.

## 31. Câu hỏi thường gặp

**Khi ghi database thành công, có phải luôn dùng `@CachePut` không?**

Không. `@CachePut` phù hợp khi kết quả method chính là snapshot mới cần cache. Nếu có nhiều biểu diễn dữ liệu hoặc cần bảo đảm sau commit, invalidation thường đơn giản hơn. Cả hai vẫn cần xét concurrency và lỗi Redis.

**`@CacheEvict` có tự rollback khi database rollback không?**

Không thể mặc định suy ra như vậy chỉ từ annotation. Thời điểm cache advice chạy so với transaction advice phụ thuộc cấu hình. Với yêu cầu cụ thể, dùng cơ chế sau commit và test theo transaction manager của ứng dụng.

**Nếu cache miss thì dữ liệu có chắc chắn mới nhất không?**

Không tuyệt đối. Lần đọc từ database replica có lag, snapshot transaction cũ hoặc nguồn dữ liệu đọc khác cũng có thể trả trạng thái chưa cập nhật. Cache miss chỉ có nghĩa không tìm thấy entry ở tầng cache đó.

**Redis TTL 5 phút có nghĩa giá có thể cũ tối đa 5 phút?**

Chỉ trong giả định entry không được gia hạn ngoài ý muốn, dữ liệu được nạp từ nguồn đúng và cache là tầng gây stale duy nhất. Có thể còn stale ở L1, CDN, read replica hoặc race cache fill. TTL một mình không chứng minh giới hạn end-to-end.

**Vì sao đã evict mà cache lại chứa dữ liệu cũ?**

Một reader có thể đọc DB cũ trước commit rồi ghi cache sau khi writer evict. Hoặc một event cập nhật cũ chạy chậm, hoặc một cache tầng khác chưa bị xóa. Cần xem timeline, version và các tầng cache.

**`@CachePut` có bỏ qua thân method khi key đã có không?**

Không. Khác `@Cacheable`, nó thực thi method rồi đưa kết quả vào cache theo điều kiện của annotation.

**Có thể dùng Redis Pub/Sub để vô hiệu hóa mọi cache instance không?**

Có thể dùng làm tín hiệu best effort, nhưng Pub/Sub không phát lại message cho instance bị ngắt kết nối. Với yêu cầu nghiêm ngặt, bổ sung TTL, versioning hoặc event bền vững/outbox.

**Có nên xóa toàn bộ Redis khi một bản ghi thay đổi không?**

Thường không. Xóa toàn bộ gây cache miss hàng loạt, tăng tải database và ảnh hưởng các dữ liệu không liên quan. Ưu tiên xóa theo key hoặc nhóm phụ thuộc đã xác định.

**Nếu Redis là nguồn chuẩn thì có cần invalidation không?**

Có thể vẫn cần, nếu các view/cache khác được dẫn xuất từ trạng thái Redis chuẩn. Cần xác định rõ Redis key nào mang trạng thái có thẩm quyền và những key nào chỉ là bản sao.

**Có nên lưu giá đã giảm trong cache để checkout đọc nhanh?**

Có thể cache giá để hiển thị, nhưng checkout nên kiểm tra giá và điều kiện khuyến mại theo quy tắc nghiệp vụ ở nguồn có thẩm quyền. Đừng để snapshot cache cũ tự quyết định số tiền phải thu.

## 32. Ghi nhớ khi thiết kế với Spring Data Redis

- **Nguồn dữ liệu chuẩn** có thẩm quyền quyết định trạng thái đúng; cache phải có khả năng làm mới hoặc tái tạo từ nguồn đó.
- **Cập nhật cache** ghi snapshot mới và giúp lần đọc kế tiếp nhanh, nhưng phải tránh ghi snapshot cũ đè snapshot mới.
- **Vô hiệu hóa cache** xóa entry đã lỗi thời để lần đọc sau nạp lại, thường dễ áp dụng khi dữ liệu có nhiều biến thể.
- **`@Cacheable`** hỗ trợ đường đọc cache-aside, **`@CachePut`** ghi kết quả vào cache, **`@CacheEvict`** xóa entry. Các annotation không tự tạo giao dịch nguyên tử giữa Redis và database.
- **Sau commit** là ranh giới quan trọng khi database là nguồn chuẩn. `@TransactionalEventListener(AFTER_COMMIT)` giúp sắp thứ tự trong JVM, còn outbox giúp có thể phục hồi khi ứng dụng crash.
- **TTL giới hạn vòng đời entry**, không thay thế invalidation theo thay đổi nghiệp vụ và không tự bảo đảm độ mới tuyệt đối.
- **Concurrency, nhiều instance, nhiều tầng cache và nhiều region** có thể tạo stale data dù từng lệnh Redis là nguyên tử.
- **Dữ liệu quyết định giao dịch quan trọng** cần kiểm tra ở nguồn chuẩn hoặc một cơ chế nhất quán có thẩm quyền.

## Tài liệu tham khảo chính thức

- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework – Cache Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Data Redis – Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Framework – Transaction-Bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Redis – Key Expiration](https://redis.io/docs/latest/commands/expire/)
- [Redis – Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis – Cache Eviction](https://redis.io/docs/latest/develop/reference/eviction/)

# Cấu hình cache theo giao dịch và giới hạn tính nguyên tử xuyên hệ thống

Trong ứng dụng Spring Boot dùng **Spring Cache với Spring Data Redis**, một phương thức nghiệp vụ có thể đồng thời cập nhật cơ sở dữ liệu và ghi/xóa cache. Ví dụ: thay đổi giá sản phẩm trong PostgreSQL rồi cập nhật khóa cache để lần đọc sau không còn trả giá cũ.

Điểm dễ nhầm là `@Transactional` của Spring thường đang quản lý **giao dịch database**, trong khi Redis cache là một hệ thống lưu trữ khác. Nếu cache được cập nhật quá sớm rồi giao dịch SQL rollback, dữ liệu trong Redis có thể đi trước hoặc mâu thuẫn với database. Spring Data Redis cung cấp `RedisCacheManager.transactionAware()` để phối hợp thao tác cache với kết quả commit của giao dịch Spring, nhưng cơ chế này **không tạo ra giao dịch nguyên tử giữa SQL và Redis**.

Bài học giải thích cách cấu hình, thứ tự xử lý, những thao tác được hoãn đến sau commit, giới hạn khi có lỗi và chiến lược thiết kế để bảo đảm mức nhất quán phù hợp.

## 1. Vấn đề: cập nhật database và cache là hai thao tác khác nhau

Giả sử hệ thống lưu sản phẩm như sau:

```text
PostgreSQL:
  products(id=42, name="Bàn học", price=900000)

Redis cache:
  productsById::42 -> { id: 42, name: "Bàn học", price: 900000 }
```

Đơn vị tiền trong ví dụ là VND. Người dùng yêu cầu đổi giá thành `950000`. Service thông thường có thể làm:

```java
@Transactional
public void changePrice(long id, BigDecimal newPrice) {
    Product product = productRepository.findById(id).orElseThrow();
    product.setPrice(newPrice);

    cacheManager.getCache("productsById")
            .evict(id);
}
```

Đoạn mã chỉ để minh họa tình huống; transaction manager được chọn ở đây là transaction manager của database. Nếu lệnh evict tác động Redis **ngay trong lúc transaction SQL đang mở**, sau đó SQL thất bại, cache có thể bị xóa dù sản phẩm trong database vẫn giữ giá cũ. Việc xóa cache lúc rollback không phải lúc nào cũng gây sai dữ liệu lâu dài, nhưng tạo ra công việc truy vấn lại không cần thiết và có thể làm xuất hiện race condition.

Rủi ro cao hơn khi cập nhật **giá trị** cache trước khi SQL commit:

```text
T0  SQL transaction bắt đầu
T1  SQL sửa giá sản phẩm 42 thành 950000 (chưa commit)
T2  Cache ghi productsById::42 = 950000
T3  Một kiểm tra SQL khác ném RuntimeException
T4  SQL ROLLBACK, giá trong database vẫn là 900000

Kết quả:
  Database = 900000
  Redis    = 950000  <-- giá cache sai
```

Khi đó các request đọc qua cache có thể nhận giá không tồn tại trong dữ liệu đã commit. Cần hiểu rõ cách Spring điều phối thao tác cache với vòng đời giao dịch.

## 2. Phân biệt các thành phần và các loại transaction

| Thành phần | Vai trò | Có tự quản lý giao dịch của tài nguyên còn lại không? |
|---|---|---|
| `@Transactional` | Đánh dấu ranh giới giao dịch của một phương thức thông qua Spring AOP | Không |
| `JpaTransactionManager` hoặc `DataSourceTransactionManager` | Quản lý commit/rollback cho JPA/JDBC database | Không tự commit/rollback Redis |
| `CacheManager` | Tạo và cung cấp các `Cache` theo tên | Không mặc nhiên biết transaction của database |
| `RedisCacheManager` | Triển khai Spring Cache trên Redis | Mặc định không có cam kết commit đồng thời với database |
| `RedisCacheManager.transactionAware()` | Trì hoãn một số thao tác cache đến khi Spring transaction commit thành công | Không có commit phân tán |
| `RedisTemplate.setEnableTransactionSupport(true)` | Tích hợp các thao tác RedisTemplate với transaction Spring qua Redis `MULTI`/`EXEC` | Không tạo giao dịch SQL + Redis nguyên tử |
| Transactional outbox | Lưu ý định đồng bộ cùng transaction database để consumer xử lý sau | Cung cấp đường khôi phục/retry, chấp nhận nhất quán cuối cùng |

Ba câu hỏi thiết kế phải được tách riêng:

1. **Database có commit hay rollback?** Do transaction manager của database quyết định.
2. **Thao tác cache được thực hiện vào lúc nào?** Do interceptor Spring Cache, cache manager và cấu hình transaction-aware quyết định.
3. **Nếu database commit thành công nhưng Redis gặp lỗi thì sao?** Cần một chính sách nhất quán, retry hoặc phục hồi riêng; `@Transactional` không tự giải quyết.

## 3. Cấu hình RedisCacheManager theo giao dịch

Để các thao tác cache phù hợp được hoãn tới lúc Spring transaction đã commit, cấu hình một `RedisCacheManager` với `transactionAware()`.

```java
package example.cache;

import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCachingConfiguration {

    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10))
                        .disableCachingNullValues();

        RedisCacheConfiguration productCache =
                defaults.entryTtl(Duration.ofMinutes(5));

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withCacheConfiguration("productsById", productCache)
                .transactionAware()
                .build();
    }
}
```

Ý nghĩa của các lựa chọn:

- `@EnableCaching` bật cơ chế nhận diện các annotation như `@Cacheable`, `@CachePut` và `@CacheEvict`.
- `cacheDefaults(defaults)` đưa ra cấu hình mặc định cho cache không có cấu hình riêng.
- `entryTtl(Duration.ofMinutes(10))` đặt thời gian sống mặc định cho entry cache.
- `withCacheConfiguration("productsById", ...)` dùng TTL năm phút cho cache sản phẩm trong ví dụ.
- `disableCachingNullValues()` không lưu các giá trị `null` vào cache.
- **`transactionAware()`** làm cho những thao tác Spring Cache được hỗ trợ có thể đợi giao dịch hiện tại hoàn tất thành công rồi mới tác động Redis.

Đây là cấu hình một bean `CacheManager` tường minh. Trong ứng dụng dùng auto-configuration của Spring Boot, cần bảo đảm các method `@Cacheable` thực sự dùng **đúng bean** đã cấu hình; nếu có nhiều `CacheManager`, hãy xác định manager nào được chọn.

### Sự khác biệt giữa TTL và transaction-aware

TTL và transaction-aware xử lý hai câu hỏi độc lập:

| Cấu hình | Câu hỏi được giải quyết |
|---|---|
| `entryTtl(5 minutes)` | Một entry trong Redis còn hợp lệ tối đa bao lâu nếu không được thay thế/xóa? |
| `transactionAware()` | Lệnh cập nhật/xóa cache nên được chạy vào thời điểm nào so với Spring transaction? |

TTL không tự biết SQL rollback; transaction-aware không bảo đảm mọi giá trị cache luôn mới. Thực tế thường cần **kết hợp** hoãn cập nhật theo transaction với TTL, chính sách invalidation và cách phục hồi dữ liệu cũ.

### Serializer và namespace

`RedisCacheConfiguration.defaultCacheConfig()` mặc định có quy ước prefix chứa tên cache, chẳng hạn `productsById::42` nếu key tạo ra là `42`. Prefix giúp các cache khác tên không đụng khóa, nhưng cần xem key generator và cấu hình prefix thực tế trước khi tra Redis CLI.

Cache value mặc định thường sử dụng Java serialization trong cấu hình Spring Data Redis truyền thống; production có thể cần JSON serializer hoặc định dạng riêng được quản lý rõ ràng. Serializer phải thống nhất giữa phiên bản ứng dụng, class DTO, chính sách bảo mật và cách rollback/migration. Việc chọn serializer **không thay thế** việc lựa chọn transaction-aware.

## 4. Cách sử dụng với @Cacheable, @CachePut và @CacheEvict

Giả sử có service đọc/sửa giá sản phẩm:

```java
package example.product;

import java.math.BigDecimal;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "productsById", key = "#productId")
    public ProductView getProduct(long productId) {
        Product product = products.findById(productId).orElseThrow();
        return ProductView.from(product);
    }

    @Transactional(transactionManager = "transactionManager")
    @CachePut(cacheNames = "productsById", key = "#productId")
    public ProductView changePrice(
            long productId,
            BigDecimal newPrice) {

        Product product = products.findById(productId).orElseThrow();
        product.setPrice(newPrice);

        return ProductView.from(product);
    }

    @Transactional(transactionManager = "transactionManager")
    @CacheEvict(cacheNames = "productsById", key = "#productId")
    public void deleteProduct(long productId) {
        products.deleteById(productId);
    }
}
```

Trong ví dụ:

- `ProductRepository` quản lý bảng sản phẩm bằng JPA/JDBC theo ứng dụng.
- `ProductView` là DTO thích hợp để cache; cần tương thích với serializer đã cấu hình.
- `@Cacheable` ưu tiên đọc cache; khi không có entry thì chạy phương thức để nạp từ database và có thể lưu kết quả.
- `@CachePut` luôn chạy phương thức và yêu cầu cập nhật cache bằng giá trị trả về.
- `@CacheEvict` yêu cầu xóa entry; mặc định việc evict gắn với kết thúc phương thức thành công.
- `@Transactional` dùng transaction manager database, giả định bean thực tế có tên `transactionManager`.

**Quan trọng:** ví dụ là mô hình tổ chức API, không phải bảo đảm tự động đúng trong mọi thứ tự Spring AOP advice. Khi `@CachePut`, `@CacheEvict` và `@Transactional` cùng xuất hiện trên một method, **thứ tự interceptor** quyết định lúc cache operation được yêu cầu so với lúc giao dịch được mở/đóng. Cần xác nhận cấu hình advisor thực tế nếu bài toán đòi hỏi chính xác thời điểm; không giả định chỉ nhìn hai annotation là đã biết thứ tự mọi callback.

### Cache hit không đồng nghĩa có truy vấn database

Với `@Cacheable`:

```text
getProduct(42)
      |
      v
Spring Cache lookup
      |
      +-- HIT --> trả ProductView từ Redis
      |
      +-- MISS --> gọi phương thức thật
                        |
                        v
                    SQL SELECT
                        |
                        v
                    đưa kết quả vào cache
```

Nếu cache đã chứa dữ liệu, phương thức gốc có thể không chạy. Vì vậy `@Transactional` trên chính phương thức đọc, nếu đặt cùng `@Cacheable`, không nên được xem là bảo đảm mọi lần gọi đều mở transaction SQL; còn phụ thuộc thứ tự advice và việc method có thực sự được thực thi không.

## 5. Transaction-aware cache hoãn việc gì đến sau commit?

Khi ứng dụng thao tác với cache đã được trang trí để nhận biết transaction, Spring Cache có thể đăng ký callback thông qua **transaction synchronization**. Đối với các thao tác được hỗ trợ như `put`, `evict` và `clear`, hiệu ứng cache được trì hoãn đến phase **after-commit** nếu đang có một transaction Spring phù hợp.

Luồng minh họa cho `changePrice(42, 950000)`:

```text
HTTP request
      |
      v
Spring transaction (database)
      |
      +--> SELECT product 42
      +--> UPDATE price = 950000
      |      (chưa commit SQL)
      |
      +--> Spring Cache yêu cầu PUT/UPDATE
      |      (cache manager transaction-aware có thể hoãn)
      |
      v
Database COMMIT thành công
      |
      v
Spring afterCommit callback
      |
      v
Redis cache PUT sản phẩm 42 = 950000
```

Nếu trước commit có unchecked exception khiến SQL rollback:

```text
SQL UPDATE mới
      |
      v
RuntimeException
      |
      v
DB ROLLBACK
      |
      v
Không chạy cache PUT đã đăng ký cho after-commit
```

Đây là giá trị chính của `transactionAware()`: nó giúp tránh nhiều tình huống cache phản ánh một thay đổi database **chưa từng commit**.

### Nếu không có Spring transaction đang hoạt động thì sao?

Transaction-aware cache không phải một lệnh “luôn trì hoãn” mọi thao tác. Nếu không có ngữ cảnh transaction synchronization đang hoạt động tại thời điểm cache operation được gọi, thao tác thường được thực hiện **ngay**.

Điều này hay xảy ra khi:

- Method thực tế không được gọi qua Spring proxy, ví dụ self-invocation.
- Lệnh ghi cache chạy trên thread khác được tạo bằng `@Async` hoặc `CompletableFuture` mà không có cùng transaction context.
- Đường ghi cache được gọi từ một flow không mở database transaction.
- Thao tác chạy trước khi interceptor `@Transactional` bắt đầu hoặc sau khi transaction đã kết thúc.
- Dùng một `CacheManager` khác, chưa cấu hình transaction-aware.

Do vậy, cần xem **bối cảnh thực tế của lời gọi cache**, không chỉ xem annotation đặt trên class.

## 6. Không phải mọi thao tác Cache đều có thể trì hoãn

Điểm cần phân biệt là hai nhóm API:

| Nhóm thao tác | Tính chất khi cache transaction-aware |
|---|---|
| `put(key, value)` | Có thể hoãn tới sau commit |
| `evict(key)` | Có thể hoãn tới sau commit |
| `clear()` | Có thể hoãn tới sau commit |
| `get(key)` | Thực hiện lookup vào cache; không biến thành một lần đọc snapshot SQL |
| `putIfAbsent(key, value)` | Theo hợp đồng Spring `TransactionAwareCacheDecorator`, không thể đơn giản hoãn đến after-commit; cần xem semantics của thao tác tức thời |
| `evictIfPresent(key)` | Không thể giả định hoãn giống `evict`; kết quả tức thời có ý nghĩa riêng |
| Các API bất đồng bộ, loader và custom writer | Phải kiểm tra hợp đồng riêng thay vì suy rộng từ `put`/`evict` |

Lý do: `putIfAbsent` cần trả lời ngay **đã có giá trị hay chưa**, còn `evictIfPresent` mang ý nghĩa xác nhận trạng thái ngay tại thời điểm gọi. Nếu hoãn hoàn toàn đến sau commit thì không còn cách đưa ra kết quả tức thời chính xác cho bên gọi.

Cấu hình `transactionAware()` cũng không biến nhiều lệnh Redis liên quan cache thành một thao tác nguyên tử trên Redis server. Các thao tác như xóa cả cache có thể phải dùng nhiều command/khóa; tính atomicity bên trong Redis phụ thuộc vào cache writer và lệnh cụ thể.

## 7. Sự khác nhau giữa RedisCacheManager.transactionAware() và RedisTemplate transaction support

Trong Spring Data Redis có hai cơ chế dễ bị nhầm:

### 7.1. Spring Cache theo transaction

```java
RedisCacheManager.builder(connectionFactory)
        .transactionAware()
        .build();
```

Cơ chế chính: **hoãn các cache mutation được hỗ trợ đến sau khi Spring transaction commit thành công**.

- Có thể không có lệnh Redis ghi/xóa thực tế nào được gửi tại thời điểm application yêu cầu `cache.put(...)`.
- Khi database rollback, callback after-commit không chạy.
- Khi database đã commit, callback gửi lệnh cache đến Redis.
- Redis lỗi tại callback **không làm commit SQL đã hoàn tất tự biến mất**.

### 7.2. RedisTemplate transaction support

```java
StringRedisTemplate template =
        new StringRedisTemplate(connectionFactory);

template.setEnableTransactionSupport(true);
```

Cơ chế chính: khi template hoạt động trong Spring transaction phù hợp, nó có thể dùng kết nối Redis với `MULTI`/`EXEC`, queue các thao tác rồi đồng bộ thực thi/discard theo vòng đời transaction.

- Nhắm tới **RedisTemplate operations**.
- Có thể thay đổi semantics đọc trong transaction vì các write vẫn đang được queue.
- Không tự cấu hình Spring Cache dựa trên một bean `RedisCacheManager` khác.
- `MULTI`/`EXEC` không tạo commit nguyên tử với SQL.

### 7.3. So sánh trực tiếp

| Tiêu chí | Cache `transactionAware()` | RedisTemplate `enableTransactionSupport=true` |
|---|---|---|
| API chính | `@Cacheable`, `@CachePut`, `@CacheEvict`, `Cache` | `RedisTemplate`, `StringRedisTemplate` |
| Cơ chế cốt lõi | Hoãn `put`/`evict`/`clear` đến after-commit | Queue thao tác Redis qua cơ chế `MULTI`/`EXEC` và đồng bộ Spring |
| Phù hợp | Cache-aside, cache invalidation | Một nhóm Redis commands có yêu cầu riêng về transaction |
| Nguyên tử với database | Không | Không |
| Cần hiểu thêm | Thứ tự cache advice, TTL, đọc cache giữa transaction | Kết quả command queue, đọc ngoài queue, Redis `DISCARD` và `EXEC` |
| Có thay thế cho nhau không? | Không | Không |

Một dự án có thể dùng cả hai vì mục đích khác nhau, nhưng cần biết **bean và đường gọi nào** sử dụng cơ chế nào. Bật transaction support trên `StringRedisTemplate` không có nghĩa mọi cache operation của `RedisCacheManager` sẽ tự dùng kết nối đó hoặc có cùng semantics.

## 8. @Transactional bảo đảm điều gì và không bảo đảm điều gì?

Giả sử Spring service quản lý transaction thông qua `JpaTransactionManager`:

```java
@Transactional(transactionManager = "jpaTransactionManager")
public ProductView changePrice(long id, BigDecimal newPrice) {
    // Cập nhật JPA entity
    // và gửi yêu cầu cache PUT/evict.
}
```

`JpaTransactionManager` quản lý `EntityManager` cùng tài nguyên database phù hợp. Nó **không** trở thành Redis transaction manager chỉ vì Redis cache nằm cùng ứng dụng Spring.

Nếu RedisCacheManager transaction-aware đăng ký callback, luồng lý tưởng là:

1. Spring bắt đầu database transaction.
2. Ứng dụng sửa entity; Spring Cache đăng ký thao tác cache nếu đi qua interceptor/manager phù hợp.
3. Database commit thành công.
4. Spring thực hiện callback after-commit để cập nhật hoặc xóa cache.

Nhưng không có một transaction coordinator chung có thể bảo đảm **hoặc SQL và Redis đều commit, hoặc cả hai không thay đổi**.

### Hai loại nhất quán cần phân biệt

**Consistency trong một hệ thống:** Database có thể dùng transaction SQL để giữ bất biến của các hàng liên quan. Redis có các command nguyên tử và một số cơ chế riêng cho các key.

**Consistency xuyên hệ thống:** Giá trị Redis phải phản ánh thay đổi đã commit ở database. Đây là yêu cầu phối hợp **hai tài nguyên độc lập**. Transaction synchronization chỉ cung cấp một thứ tự hành động thuận lợi; nó không tự tạo atomic distributed commit.

## 9. Khoảng lỗi sau khi SQL commit và trước khi cache cập nhật

Đây là giới hạn quan trọng nhất:

```text
T0  @Transactional bắt đầu
T1  UPDATE products SET price = 950000 WHERE id = 42
T2  Database COMMIT thành công
T3  [Process dừng / Redis timeout / mạng mất kết nối]
T4  Cache PUT hoặc EVICT sau commit không hoàn tất

Database:
  sản phẩm 42 có giá 950000

Redis:
  có thể còn giá 900000
  hoặc cache chưa được xóa như dự kiến
```

Nếu Redis là cache và database là nguồn sự thật, hệ thống vẫn có thể phục hồi bằng TTL, một lần invalidation tiếp theo, retry hoặc rebuild. Nhưng trong khoảng thời gian giữa các bước, người dùng có thể nhận dữ liệu cũ.

Điều không thể làm bằng cách thêm `@Transactional`:

```text
DB COMMIT thành công
     |
     +--> Redis thất bại
                |
                v
     "Tự động rollback DB về giá cũ"
```

Database đã commit không thể mặc nhiên bị rollback chỉ vì callback Redis thất bại. Một exception phát sinh sau commit thậm chí có thể trả lỗi đến caller dù transaction SQL đã thực sự commit. Nếu client thấy lỗi rồi gửi lại yêu cầu, ứng dụng cần xác định thao tác có thể lặp lại an toàn hay không.

### Ma trận tình huống lỗi

| Tình huống | Database | Redis cache | Kết luận |
|---|---|---|---|
| Phương thức thành công, không có lỗi hạ tầng | Commit | PUT/EVICT after-commit thành công | Dữ liệu đạt trạng thái dự kiến |
| Exception khiến DB rollback trước commit | Rollback | Mutation được hoãn không chạy | Tránh ghi cache cho dữ liệu chưa commit |
| Redis không khả dụng sau DB commit | Commit | Có thể còn entry cũ | Cần cơ chế khôi phục |
| Process chết sau DB commit, trước callback | Commit | Không có bảo đảm callback đã chạy | Callback in-memory không bền vững |
| Redis cập nhật thành công, phản hồi mất | Commit | Có thể đã đổi nhưng caller không biết | Retry cần idempotency hoặc đọc/đối soát |
| Hai transaction cập nhật cùng key cạnh tranh | Có thể commit theo thứ tự | Mutation cache có thể đến khác thứ tự | Có nguy cơ giá trị cache cũ ghi đè mới |
| Cache entry bị xóa, sau đó reader đọc DB lúc transaction khác chưa commit | Reader thấy giá đã commit cũ | Có thể nạp lại giá cũ | Cần đánh giá race condition và khả năng evict lại |

Việc cấu hình transaction-aware giải quyết đáng kể **trường hợp rollback trước commit**, nhưng không xóa các trạng thái lệch dữ liệu sau commit hoặc khi có nhiều writer cạnh tranh.

## 10. @CachePut và @CacheEvict: nên chọn cách nào?

Hai cách cập nhật cache sau khi thay đổi database có mục đích khác nhau.

### 10.1. Cập nhật giá trị mới bằng @CachePut

```java
@Transactional(transactionManager = "transactionManager")
@CachePut(cacheNames = "productsById", key = "#productId")
public ProductView changePrice(long productId, BigDecimal price) {
    Product product = products.findById(productId).orElseThrow();
    product.setPrice(price);
    return ProductView.from(product);
}
```

**Ưu điểm:** sau khi cache put thành công, lần đọc có thể lấy ngay dữ liệu mới từ Redis, tránh query database.

**Rủi ro:** nếu hai thay đổi cùng key cạnh tranh hoặc một callback đến muộn, cache có thể bị ghi bằng một DTO cũ. Nếu dữ liệu còn do trigger/transaction khác điều chỉnh, DTO lấy trước commit cũng không nhất thiết mô tả chính xác trạng thái database cuối cùng.

### 10.2. Xóa entry để đọc lại nguồn chuẩn bằng @CacheEvict

```java
@Transactional(transactionManager = "transactionManager")
@CacheEvict(cacheNames = "productsById", key = "#productId")
public void changePrice(long productId, BigDecimal price) {
    Product product = products.findById(productId).orElseThrow();
    product.setPrice(price);
}
```

**Ưu điểm:** sau evict thành công, request tiếp theo sẽ lấy dữ liệu đã commit từ database rồi cache lại; không phải đóng gói giá trị mới ngay trong command ghi cache.

**Rủi ro:** callback evict cũng có thể thất bại sau SQL commit. Một reader đồng thời có thể đọc và đưa vào cache dữ liệu ở thời điểm chưa thích hợp nếu hệ thống có transaction/đọc từ replica database bị trễ. Hệ thống đọc có yêu cầu nhất quán mạnh cần thêm chính sách xử lý race.

### 10.3. Chọn theo đặc tính nghiệp vụ

| Đặc tính | `@CachePut` | `@CacheEvict` |
|---|---|---|
| Cache chứa gì sau thao tác thành công? | Giá trị do phương thức trả về | Entry bị xóa |
| Lần đọc kế tiếp | Thường là cache hit | Thường cache miss rồi nạp từ nguồn chuẩn |
| Rủi ro stale write | Có nếu callback dữ liệu cũ chạy muộn | Có thể stale nếu evict bị mất hoặc refill bị race |
| Phụ thuộc DTO/serializer | Cần lưu payload đúng định dạng | Chỉ cần xác định đúng key cần xóa |
| Phù hợp | Giá trị mới đã chắc chắn, cần hit nhanh | Cache chỉ là projection của DB, refill chấp nhận được |

Với cache-aside dùng database làm nguồn sự thật, **evict sau commit** thường dễ quản lý hơn việc duy trì hai bản cập nhật giá trị. Tuy nhiên, không có giải pháp nào trong bảng tự cung cấp bảo đảm nhất quán mạnh xuyên hệ thống.

## 11. Vòng đời cache khi có @Cacheable

Sự hiện diện của `@Cacheable` có thể tạo thêm các trạng thái khó thấy trong giai đoạn transaction.

### 11.1. Đọc trong khi transaction sửa dữ liệu

```text
Request A                         Request B
  |                                  |
  |--- BEGIN SQL transaction         |
  |--- UPDATE product=950000         |
  |--- cache EVICT được hoãn         |
  |                                  |--- @Cacheable getProduct(42)
  |                                  |--- cache HIT giá 900000
  |--- COMMIT                        |
  |--- Redis EVICT                    |
  v                                  v
```

Ở thời điểm Request B đọc trước khi A commit, giá `900000` có thể chính là dữ liệu **đã commit** hợp lệ. Transaction-aware cache không yêu cầu B nhìn thấy giá đang được A sửa nhưng chưa commit.

### 11.2. Cache miss có thể nạp dữ liệu tại thời điểm không mong muốn

```text
Request A                          Request B
  |                                   |
  |--- UPDATE product, chưa COMMIT    |
  |                                   |--- cache MISS
  |                                   |--- SELECT từ DB
  |                                   |--- đọc giá cũ 900000
  |                                   |--- cache PUT giá cũ
  |--- COMMIT                         |
  |--- EVICT after-commit             |
```

Nếu B ghi giá cũ trước khi A evict, evict có thể dọn entry cũ ngay sau đó. Nhưng các thứ tự interleaving khác, retry bất đồng bộ hoặc callback trì hoãn có thể tạo trạng thái stale. Cần xem toàn bộ đường nạp dữ liệu từ nguồn, chứ không chỉ một method cập nhật.

### 11.3. Đọc từ database replica có replication lag

Sau khi primary database commit, một request cache miss có thể đọc từ read replica chưa cập nhật. Nó lại đẩy dữ liệu cũ vào Redis. `transactionAware()` của Redis cache **không kiểm soát độ trễ replication của database**.

Với dữ liệu cần read-after-write consistency, có thể phải định tuyến một khoảng đọc về primary hoặc dùng version/watermark để tránh nạp giá trị cũ. Đây là vấn đề ngoài phạm vi atomicity giữa Redis và SQL, nhưng thường xuất hiện khi triển khai thật.

## 12. Thứ tự Spring AOP interceptor có thể ảnh hưởng kết quả

`@Transactional` và các annotation cache hoạt động qua interceptor/proxy Spring. Khi đặt trên cùng method, một thứ tự thường thấy là:

```text
Cache interceptor
  -> Transaction interceptor
      -> Target service method
  <- Transaction commit
<- Cache interceptor xử lý kết quả
```

Ở cách lồng này, cache put sau method có thể được yêu cầu **sau khi SQL đã commit**; khi đó thao tác cache không còn nằm trong transaction đang hoạt động để đăng ký after-commit. Đường đi khác có thể là:

```text
Transaction interceptor
  -> Cache interceptor
      -> Target service method
  <- Cache yêu cầu PUT (đang trong transaction)
<- SQL commit, after-commit callback PUT
```

Mục đích của `transactionAware()` là hỗ trợ trường hợp cache operation được gọi trong transaction active. **Không được suy ra thứ tự interceptor chỉ từ thứ tự annotation viết trên Java source.**

Một số nguyên tắc:

- Đặt ranh giới transaction tại một service public method được gọi qua Spring proxy; tránh self-invocation khiến annotation bị bỏ qua.
- Khi cần đảm bảo lệnh cache chỉ chạy sau commit, có thể tổ chức đường cache mutation rõ ràng bằng listener after-commit hoặc tầng orchestration; đồng thời chấp nhận giới hạn độ tin cậy của callback.
- Nếu tùy chỉnh `order` của `@EnableCaching` hoặc `@EnableTransactionManagement`, cần hiểu thứ tự áp dụng advice và kiểm tra tác động.
- `@Cacheable` có thể short-circuit method trên cache hit; một method không chạy nghĩa là transaction interceptor ở bên trong có thể không được gọi.
- Khi xử lý qua `@Async`, thread mới không tự thừa hưởng ngữ cảnh Spring transaction của thread cũ.

Sử dụng các annotation đúng cú pháp là bước đầu; **vị trí yêu cầu thao tác cache so với transaction** mới quyết định semantics.

## 13. Cache transaction-aware không có nghĩa Redis MULTI/EXEC

Một hiểu nhầm khác là “bật `transactionAware()` thì Redis chạy `MULTI` rồi queue tất cả lệnh cache”. Đây không phải mô hình cốt lõi của Spring Cache transaction-aware.

```text
Spring transaction (SQL)
         |
         v
Cache put(key, value)
         |
         v
Transaction-aware decorator:
  "Đợi SQL commit rồi mới thực hiện put"
         |
         v
SQL COMMIT
         |
         v
Redis writer thực hiện lệnh cache
```

Không có yêu cầu chung phải dùng Redis transaction `MULTI`/`EXEC` cho sơ đồ này. Do đó, các giới hạn của Redis cache writer vẫn tồn tại:

- Một lần `clear()` có thể cần tìm và xóa nhiều khóa.
- Một thao tác cache có thể gồm nhiều command tùy writer, batch strategy và API được gọi.
- Redis cache writer mặc định thường không khóa toàn bộ cache cho mọi thao tác; nhiều client có thể cùng cache miss hoặc refill.
- Một cache transaction-aware không biến cả bộ key trong nhiều cache name thành một transaction Redis nguyên tử.
- Redis Cluster còn phân bố các entry cache qua nhiều hash slot và primary.

Nếu ứng dụng cần **cập nhật hai khóa Redis nguyên tử** trong một slot, đó là bài toán Redis transaction hoặc Lua scripting phù hợp, không phải thứ mà `CacheManager.transactionAware()` hứa cung cấp. Nếu cần cập nhật **Redis và database** cùng nguyên tử, những công cụ Redis này cũng không tự giải quyết được.

## 14. Dùng @TransactionalEventListener(AFTER_COMMIT) khi muốn điều khiển rõ thời điểm

Một lựa chọn là phát event nghiệp vụ bên trong transaction database, rồi xử lý cache sau commit:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

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

    @Transactional(transactionManager = "transactionManager")
    public void changePrice(long id, BigDecimal price) {
        Product product = products.findById(id).orElseThrow();
        product.setPrice(price);

        events.publishEvent(new ProductChanged(id));
    }
}

public record ProductChanged(long productId) {}
```

Listener:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCacheInvalidator {

    private final CacheManager cacheManager;

    public ProductCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void invalidate(ProductChanged event) {
        Cache cache = cacheManager.getCache("productsById");

        if (cache != null) {
            cache.evict(event.productId());
        }
    }
}
```

`@TransactionalEventListener(phase = AFTER_COMMIT)` chỉ gọi handler cho event có giao dịch phù hợp đã commit thành công. Ví dụ mặc định không xử lý event ngoài transaction nếu không bật `fallbackExecution`.

**Nhưng event này là event trong bộ nhớ ứng dụng.** Nếu process dừng sau DB commit nhưng trước khi listener chạy, không có một hàng đợi bền vững mặc định để phát lại event. Ngoài ra, chính lệnh `cache.evict` có thể lỗi khi Redis không khả dụng. Đây là cách kiểm soát **thời điểm**, không phải bảo đảm delivery.

Nếu hệ thống cần chắc chắn phát lại các yêu cầu invalidation khi lỗi hoặc restart, cần một chiến lược bền vững hơn.

## 15. Transactional outbox: lưu ý định đồng bộ trong cùng giao dịch database

**Transactional outbox** là cách thường dùng khi Redis chứa dữ liệu đọc quan trọng và không được phép bỏ mất hoàn toàn yêu cầu cập nhật/invalidation sau khi database commit.

Quy trình:

1. Trong cùng transaction SQL, cập nhật dữ liệu nguồn và **ghi một dòng outbox** với ID sự kiện, ID entity và version.
2. Commit database. Thay đổi nghiệp vụ và yêu cầu đồng bộ cùng được lưu hoặc cùng rollback.
3. Một worker đọc các dòng outbox chưa xử lý.
4. Worker gửi thao tác xóa/cập nhật cache tới Redis.
5. Nếu thành công, worker đánh dấu event đã xử lý; nếu lỗi, giữ event để retry.
6. Nếu có khả năng xử lý lại, thao tác cache phải idempotent hoặc có cơ chế kiểm soát version.

```text
              Request changePrice(42)
                         |
                         v
                 Database transaction
                         |
             +-----------+-------------+
             |                         |
             v                         v
       UPDATE products             INSERT outbox
             |                         |
             +-----------+-------------+
                         |
                    DB COMMIT
                         |
                         v
                 Durable outbox row
                         |
                         v
                  Worker / Publisher
                         |
                         v
                   Redis EVICT / PUT
                         |
                success ?     retry
                         |
                         v
                  Mark event handled
```

Ví dụ mức khái niệm:

```java
@Transactional(transactionManager = "transactionManager")
public void changePrice(long id, BigDecimal price) {
    Product product = products.findById(id).orElseThrow();
    product.setPrice(price);

    outboxRepository.save(
            OutboxEvent.productChanged(id, product.getVersion()));
}
```

Worker có thể xử lý:

```text
for each pending outbox event:
    claim event để tránh worker khác xử lý cùng lúc
    nếu Redis đang sẵn sàng:
        invalidate cache entry hoặc ghi giá trị mới
        ghi nhận thành công vào outbox
    nếu Redis lỗi:
        ghi nhận lỗi, cho retry với backoff
```

Đây là sơ đồ quy trình, không phải mã sản xuất đầy đủ. Implementation cần xử lý claim ownership, độ trễ, transaction của bảng outbox, retry, dead letter, thứ tự event, metric và cleanup.

### Vì sao outbox giải quyết khoảng lỗi tốt hơn after-commit callback?

Sau khi SQL commit, **yêu cầu cập nhật Redis đã tồn tại dưới dạng một bản ghi database bền vững**. Nếu process chết hoặc Redis tạm ngừng, worker vẫn có thể tìm lại yêu cầu đó.

Đánh đổi là cache thường đạt **eventual consistency**, không phải ngay lập tức đồng bộ từng mili giây. Ứng dụng cần xác định độ trễ tối đa có thể chấp nhận và theo dõi outbox lag.

### At-least-once và idempotency

Giả sử worker xóa cache thành công nhưng bị mất kết nối trước khi ghi `processed=true` cho outbox. Event sẽ được chạy lại sau đó. Xóa cùng key lần nữa thường có thể chấp nhận, nhưng một event **ghi nguyên giá trị cũ** sau event mới có thể làm cache stale.

Cách giảm rủi ro:

- Ưu tiên invalidation thay vì blind overwrite nếu kiến trúc cho phép.
- Dùng event ID và version để phát hiện trùng/lệch thứ tự.
- Nếu ghi giá trị vào Redis, thiết kế logic chỉ nhận version mới hơn; so sánh version và ghi phải được thực hiện phù hợp với giới hạn Redis/Cluster.
- Giới hạn số lần retry hoặc chuyển event lỗi sang trạng thái cần xử lý thủ công, nhưng không im lặng bỏ mất event.
- Theo dõi độ trễ từ DB commit tới Redis đã được đồng bộ.

## 16. Khi nào TTL đủ, khi nào cần outbox?

Không phải mọi cache đều cần outbox. Thiết kế nên bắt đầu từ mức độ quan trọng của dữ liệu trong cache.

| Tình huống | Cách tiếp cận có thể phù hợp | Đánh đổi |
|---|---|---|
| Danh sách sản phẩm ít nhạy cảm, cache tồn tại vài chục giây | TTL ngắn + cache-aside | Có thể đọc dữ liệu cũ một thời gian ngắn |
| Cập nhật thông tin hiếm khi xảy ra, stale vài phút được chấp nhận | After-commit evict + TTL | Evict lỗi vẫn có TTL để tự hồi phục |
| Cache thuộc tính cá nhân nhưng nguồn DB vẫn là chuẩn | Evict after commit + monitoring/retry | Cần xem yêu cầu về dữ liệu cũ và bảo vệ quyền riêng tư |
| Trạng thái đơn hàng cần đồng bộ trong giới hạn thời gian chặt | Outbox + worker idempotent, quan sát lag | Phức tạp hơn, nhưng có cơ chế retry |
| Số dư, quyền truy cập, tồn kho là bất biến quyết định nghiệp vụ | Đọc/xác minh từ nguồn chuẩn khi quyết định quan trọng; cache chỉ hỗ trợ | Không coi cache làm nguồn sự thật đơn độc |
| Nhiều hệ thống cùng ghi cache và dữ liệu | Thống nhất writer/protocol, version, event ordering | Cần điều phối liên service |

Ví dụ: kiểm tra quyền truy cập chỉ dựa vào một Redis entry có TTL dài sau khi quyền đã bị thu hồi có thể gây rủi ro nghiệp vụ. Ngay cả outbox cũng có độ trễ; nếu cần thu hồi có hiệu lực tức thời ở mọi request, hãy thiết kế cơ chế kiểm tra ở nguồn phù hợp và xác định SLA nhất quán trước khi chọn cache.

## 17. Những lỗi thường gặp khi triển khai Spring Cache theo transaction

### 17.1. Bật transactionAware nhưng vẫn thấy cache thay đổi khi SQL rollback

Các khả năng cần xem:

- Lời gọi cache không chạy trong một transaction synchronization đang hoạt động.
- Method `@Transactional` bị gọi nội bộ qua `this.method()` nên không qua proxy.
- Có hơn một `CacheManager`, method sử dụng một manager khác.
- Method dùng một thread bất đồng bộ không có transaction context.
- Cache interceptor được gọi tại thời điểm nằm ngoài transaction thực tế.
- Code có thao tác Redis thấp cấp hoặc `RedisTemplate` riêng không thông qua cache manager đã cấu hình.

Không nên kết luận ngay rằng Redis lỗi transaction. Cần quan sát transaction boundary và đúng đường cache mutation.

### 17.2. @CacheEvict(beforeInvocation = true) gây khó hiểu

Annotation:

```java
@CacheEvict(
        cacheNames = "productsById",
        key = "#productId",
        beforeInvocation = true
)
```

yêu cầu Cache interceptor thực hiện eviction **trước khi method được gọi** theo semantics annotation. Nhưng nếu cache implementation nhận biết transaction và operation này được yêu cầu trong transaction, nó vẫn có thể bị hoãn theo hợp đồng của cache decorator; còn nếu chưa có transaction active, nó có thể chạy ngay.

Vì vậy, không kết hợp tùy tiện `beforeInvocation=true` với kỳ vọng “chỉ xóa sau commit”. Hãy làm rõ mục tiêu: muốn xóa dù method thất bại, hay muốn chỉ xóa nếu SQL commit? Hai mục tiêu khác nhau.

### 17.3. @Cacheable trên self-invocation không có hiệu lực

Ví dụ:

```java
@Service
public class ProductFacade {

    public ProductView loadTwice(long id) {
        ProductView first = this.getProduct(id);
        ProductView second = this.getProduct(id);
        return second;
    }

    @Cacheable(cacheNames = "productsById", key = "#id")
    public ProductView getProduct(long id) {
        // Read database
    }
}
```

Với cách proxy Spring thông thường, `this.getProduct(...)` là lời gọi nội bộ và **có thể không đi qua cache interceptor**. Tương tự cho `@Transactional`. Nếu cần semantics AOP, tổ chức method ở bean phù hợp và gọi qua Spring proxy thay vì tự gọi method trong cùng object.

### 17.4. Cache và database dùng cùng transaction manager?

`@Transactional(transactionManager="transactionManager")` chọn manager được định danh, thường là manager database. RedisCacheManager có thể **quan sát vòng đời giao dịch** thông qua Spring synchronization, nhưng không có nghĩa manager SQL đã trở thành manager cho Redis.

Nếu có nhiều database hoặc transaction manager, cần chọn đúng manager cho nghiệp vụ. Transaction-aware không tự phối hợp toàn bộ các database khác nhau thành một commit chung.

### 17.5. Callback sau commit thất bại

Nếu callback Redis lỗi:

- Database có thể đã commit.
- Caller có thể nhận exception hoặc không, tùy đường xử lý callback/lỗi.
- Không được retry toàn bộ update SQL một cách mù quáng chỉ vì cache callback lỗi.
- Cần xác định có thể xóa cache theo ID để phục hồi hay phải phát event theo giao thức riêng.

Nguyên tắc quan trọng là **tách kết quả commit nghiệp vụ khỏi kết quả đồng bộ cache** trong mô hình lỗi và quan sát.

### 17.6. Giả định @CachePut nhiều khóa là nguyên tử

Một method có thể đụng nhiều cache name hoặc nhiều key. Transaction-aware hoãn operation, nhưng không bảo đảm mọi cache entry được cập nhật đồng thời thành một transaction Redis duy nhất. Reader có thể thấy một phần dữ liệu mới trong lúc những phần khác chưa cập nhật, nhất là trong Redis Cluster.

Với yêu cầu đọc nhiều khóa nhất quán, cân nhắc snapshot/version hoặc lấy quyết định từ nguồn dữ liệu chuẩn thay vì suy ra atomicity chỉ từ annotation.

### 17.7. Không đo độ trễ và lỗi cache

Một hệ thống không có metric dễ trông như “chạy ổn” cho đến khi Redis outage làm dữ liệu cũ kéo dài hoặc DB chịu cache miss bất ngờ. Nên theo dõi:

- Cache hit/miss ratio theo tên cache.
- Số lỗi Redis read/write/evict và timeout.
- Độ trễ database transaction.
- Khoảng thời gian từ commit đến invalidation hoàn tất.
- Số outbox event đang chờ, số lần retry và độ trễ lớn nhất nếu dùng outbox.
- TTL và số lượng key theo cache namespace.

Metric không thay thế cơ chế phục hồi nhưng giúp phát hiện sai lệch và đánh giá mức độ ảnh hưởng.

## 18. Thực hành quan sát rollback và cache

Bài thực hành dành cho **database và Redis thử nghiệm**, giả định cấu hình Spring Cache cùng `RedisCacheManager.transactionAware()` đã có.

### Chuẩn bị

Tạo sản phẩm:

```text
products:
  id    = 42
  price = 900000
```

Gọi `getProduct(42)` để nạp cache trước. Dùng Redis CLI trong môi trường lab để quan sát:

```bash
# Chỉ quét node đang kết nối. Khi dùng Redis Cluster phải xét các primary.
redis-cli SCAN 0 MATCH 'productsById::*' COUNT 100
```

Nếu dùng serializer mặc định dạng nhị phân, không mặc định `GET` trả JSON dễ đọc. Có thể quan sát TTL/EXISTS mà không cần giải mã payload:

```bash
redis-cli EXISTS 'productsById::42'
redis-cli TTL 'productsById::42'
```

### Kịch bản A — Không bật transaction-aware

1. Bắt đầu một method `@Transactional` cập nhật giá sản phẩm.
2. Trong method, gọi `Cache.put` hoặc đường cache mutation thực thi ngay.
3. Ném `RuntimeException` trước commit.
4. Đọc lại database và cache sau rollback.

Quan sát xem cache có chứa giá mới dù database đã rollback không. Kết quả tùy thời điểm/cache API được gọi; mục tiêu là nhận diện thao tác cache đã xảy ra **trước commit**.

### Kịch bản B — Bật transaction-aware

1. Dùng CacheManager có `transactionAware()`.
2. Trong một Spring transaction active, yêu cầu `cache.put(...)`.
3. Ném `RuntimeException` để database rollback.
4. Đọc cache **ngoài** transaction.

Nếu operation được hoãn đúng cách, callback after-commit không chạy, nên không có bản cập nhật cache từ transaction bị rollback. Trên thực tế cần đảm bảo đoạn code gọi cache nằm bên trong transaction, không chỉ cùng method có annotation nhưng đi sai proxy/advisor.

### Kịch bản C — SQL commit rồi Redis lỗi

1. Trên môi trường thử nghiệm, khiến Redis không khả dụng đúng giai đoạn callback sau commit.
2. Quan sát kết quả database, lỗi ở Redis và trạng thái cache.
3. Khôi phục Redis, kiểm tra liệu có tác vụ tự retry hay không.
4. Nếu không có outbox/reconciliation, xem entry stale còn tới lúc TTL hay tới lần invalidation khác.

Kịch bản này cho thấy nguyên nhân **transaction-aware không đủ bảo đảm đồng bộ xuyên hệ thống**. Không thực hiện thử nghiệm ngắt Redis trên production.

### Kịch bản D — Cập nhật đồng thời cùng một sản phẩm

1. Transaction A đổi giá từ 900000 sang 930000.
2. Transaction B đổi giá sang 950000 trong thời gian gần nhau.
3. Quan sát thứ tự commit, thứ tự cache mutation và giá cuối ở cả hai nơi.
4. Đánh giá xem phiên bản DTO trong cache có thể cũ hơn phiên bản database không.

Nếu nghiệp vụ yêu cầu chặn stale write, cần bổ sung version hoặc tổ chức invalidation/reload rõ ràng. Thử nghiệm này có thể không tái hiện race ở mọi lần chạy; giá trị của nó là làm rõ các thứ tự có thể xảy ra.

## 19. Câu hỏi tự đánh giá

**1. Bật `@Transactional` trên service có tự rollback thay đổi Redis cache không?**

Không. Annotation điều khiển transaction manager được chọn; Redis cache có đường ghi riêng. Muốn hoãn thao tác cache theo transaction, cần cấu hình transaction-aware và đảm bảo đường gọi nằm trong transaction thực tế.

**2. `RedisCacheManager.transactionAware()` bảo đảm điều gì?**

Cho phép trì hoãn các thao tác cache được hỗ trợ như `put`, `evict`, `clear` tới sau khi transaction Spring commit thành công, khi có synchronization phù hợp. Nó không tạo transaction phân tán.

**3. Vì sao PostgreSQL có thể đã commit nhưng Redis vẫn chứa giá cũ?**

Vì callback cache chạy sau commit có thể lỗi, Redis offline, process dừng hoặc update bị bỏ lỡ. Database không tự rollback lại khi Redis gặp sự cố.

**4. `RedisTemplate.setEnableTransactionSupport(true)` và `RedisCacheManager.transactionAware()` có giống nhau không?**

Không. Cơ chế RedisTemplate dựa trên kết nối và Redis `MULTI`/`EXEC`, còn Spring Cache transaction-aware hoãn mutation cache đến after-commit.

**5. Vì sao `Cache.putIfAbsent` không nên được xem là luôn hoãn tới after-commit?**

Nó cần cung cấp kết quả về sự tồn tại của key ngay lúc gọi. Một số API mang ngữ nghĩa tức thời không thể trì hoãn như `put` thông thường.

**6. Nếu hai transaction cập nhật cùng sản phẩm, after-commit callback có loại hết stale write không?**

Không. Các callback hoặc event có thể thực thi/đến khác thứ tự, và cache vẫn có thể bị nạp bằng bản đọc cũ. Cần xem version, ordering, invalidation và source-of-truth.

**7. Khi nào một listener `@TransactionalEventListener(AFTER_COMMIT)` không đủ?**

Khi cần phát lại sự kiện sau crash hoặc retry bền vững lúc Redis lỗi. Listener mặc định không lưu event thành một bản ghi durable.

**8. Vì sao outbox đáng cân nhắc với cache quan trọng?**

Vì sự kiện đồng bộ được ghi trong cùng giao dịch với thay đổi database, nên vẫn tồn tại sau process crash để worker xử lý lại.

**9. TTL có loại bỏ hoàn toàn sự lệch dữ liệu giữa cache và database không?**

Không. TTL giới hạn thời gian một entry có thể tồn tại, nhưng trong khoảng TTL, cache vẫn có thể phục vụ dữ liệu cũ.

**10. Redis Lua hoặc MULTI/EXEC có tạo atomic commit giữa Redis và JPA không?**

Không. Chúng cung cấp các cơ chế nguyên tử/giao dịch trong Redis theo phạm vi hợp lệ, không thay thế một transaction coordinator cho hai hệ thống.

## 20. Ghi nhớ khi thiết kế cache theo giao dịch

- **`@Transactional` quản lý giao dịch của transaction manager được chọn**, thường là database manager trong ứng dụng JPA/JDBC.
- **`RedisCacheManager.transactionAware()` giúp hoãn các cache mutation được hỗ trợ đến after-commit**, tránh nhiều trường hợp cache ghi dữ liệu thuộc một SQL transaction cuối cùng rollback.
- **Không có cam kết SQL và Redis commit nguyên tử**. Redis lỗi sau SQL commit vẫn tạo cache stale hoặc thiếu dữ liệu.
- **Thứ tự Spring AOP và đường gọi thực tế quan trọng**: method có annotation chưa đủ nếu operation chạy ngoài transaction, qua self-invocation hoặc thread khác.
- **Đọc cache, putIfAbsent và các API tức thời có semantics riêng**; đừng giả định mọi thao tác đều hoãn giống `put`/`evict`.
- **Cache transaction-aware khác với RedisTemplate `MULTI`/`EXEC`**, và không biến nhiều cache key thành một transaction Redis nguyên tử.
- **Chọn cache policy theo mức độ cần nhất quán**: TTL + invalidation sau commit đủ cho cache ít quan trọng; outbox/idempotency/version cần thiết khi phải phục hồi sau sự cố.
- **Database thường là nguồn sự thật** trong cache-aside. Với bất biến quan trọng như quyền truy cập hoặc tiền, không để quyết định nghiệp vụ phụ thuộc duy nhất vào một cache entry có thể cũ.

Câu hỏi quan trọng cần trả lời khi thiết kế là: **“Nếu database đã commit nhưng không có lệnh cache nào chạy thành công sau đó, hệ thống sẽ tự phục hồi như thế nào?”** Cấu hình transaction-aware giảm nguy cơ cập nhật trước commit; cơ chế TTL, retry, outbox và đối soát mới xử lý phần rủi ro còn lại.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): `RedisCacheManager`, `RedisCacheConfiguration`, TTL, cache writer và `transactionAware()`.
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, key và proxy behavior.
- [Spring Framework — Transaction-aware Cache Decorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): thời điểm hoãn `put`, `evict`, `clear` và giới hạn các thao tác tức thời.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, manager, propagation, proxy và rollback.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, các transaction phase và after-commit.
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): `RedisTemplate` và cách Redis transactions phối hợp với Spring.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): giới hạn của `MULTI`/`EXEC` và tính nguyên tử trong Redis.

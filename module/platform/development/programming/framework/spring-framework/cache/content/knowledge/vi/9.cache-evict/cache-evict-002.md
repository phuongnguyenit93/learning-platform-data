# @CacheEvict(allEntries = true): xóa toàn bộ vùng cache trong Spring Framework

## 1. Vì sao cần xóa toàn bộ vùng cache?

Spring Cache giúp giảm số lần truy vấn hoặc tính toán bằng cách lưu kết quả theo khóa (key). Tuy nhiên, khi nguồn dữ liệu thay đổi, bản cache cũ cần được vô hiệu hóa (invalidate).

Với `@CacheEvict`, bạn có hai mức độ xóa:

- **Xóa một entry:** mặc định `allEntries = false`, Spring chọn cache và key của lời gọi rồi xóa entry tương ứng.
- **Xóa toàn bộ entries của cache được chọn:** `allEntries = true`, Spring bỏ qua việc xác định một key và yêu cầu mỗi vùng cache liên quan xóa tất cả entry.

Tình huống thường gặp: sau khi nhập lại toàn bộ danh mục sản phẩm hoặc thay đổi bảng quy tắc giá, hệ thống không biết chính xác những key nào đã bị ảnh hưởng. Xóa cả vùng cache liên quan là phương án đơn giản để lần đọc tiếp theo tải dữ liệu mới.

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void importAllProducts() {
    repository.importBatch();
}
```

Đây là đoạn method minh họa trong service có `repository` phù hợp, **không phải file Java độc lập**. Khi method kết thúc thành công và lời gọi đi qua Spring proxy, Spring yêu cầu xóa toàn bộ entries trong cache có tên `products`.

**Mục tiêu học:** hiểu chính xác phạm vi của `allEntries`, thời điểm xóa (`beforeInvocation`), điều kiện (`condition`), ảnh hưởng tới cache khác, thử nghiệm hoạt động trên Java 17+, cũng như những giới hạn khi dùng trong hệ thống phân tán và transaction.

## 2. Phạm vi xóa: “toàn bộ” nghĩa là gì?

### 2.1. Xóa toàn bộ *entries* của các cache được chọn, không xóa tất cả cache của ứng dụng

Ví dụ CacheManager có ba cache:

```text
CacheManager
├── products
│   ├── "A" -> Product A
│   └── "B" -> Product B
├── productSummary
│   └── "VN" -> Summary
└── users
    └── "u1" -> User
```

Với:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void reloadCatalog() { /* cập nhật nguồn dữ liệu */ }
```

Sau lần gọi thành công qua proxy, **chỉ các entries trong vùng `products` được yêu cầu xóa**. Cache `productSummary` và `users` không bị annotation này động tới, dù chúng có thể chứa dữ liệu phụ thuộc vào danh mục cũ.

Nếu cần xóa cả hai vùng liên quan:

```java
@CacheEvict(
    cacheNames = {"products", "productSummary"},
    allEntries = true
)
public void reloadCatalog() { /* cập nhật nguồn dữ liệu */ }
```

Với `CacheResolver` tùy biến, danh sách cache thực sự do resolver trả về cần được hiểu rõ. Trong cách cấu hình đơn giản, `cacheNames` chỉ định chính xác các cache sẽ xử lý.

**Không nhầm lẫn:** `allEntries=true` không xóa bean `CacheManager`, không xóa định nghĩa/cache instance và **không xóa dữ liệu gốc** trong database. Nó ra lệnh clear các entries của vùng cache liên quan; những lần `@Cacheable` tiếp theo sẽ có cache miss và nạp lại giá trị nếu provider đã hoàn tất clear.

### 2.2. Không cần key — và không được kết hợp với `key`

Khi xóa toàn bộ vùng, tham số `key` không có ý nghĩa. Javadoc của `@CacheEvict` trong Spring Framework 6.x nêu rõ: cấu hình `allEntries=true` cùng với `key()` là **không hợp lệ**. Hãy bỏ thuộc tính `key` thay vì hy vọng Spring chỉ bỏ qua biểu thức đó.

```java
// ĐÚNG: xóa mọi entry của cache "products".
@CacheEvict(cacheNames = "products", allEntries = true)
public void resetAll() { }

// ĐÚNG: xóa một entry cụ thể (mặc định allEntries=false).
@CacheEvict(cacheNames = "products", key = "#p0")
public void resetOne(String sku) { }

// SAI: key không được kết hợp với allEntries=true.
// @CacheEvict(cacheNames = "products", allEntries = true, key = "#p0")
// public void invalidConfiguration(String sku) { }
```

Đây là đoạn code minh họa các method đặt trong service. Cấu hình sai nằm trong comment, tránh hiểu nhầm đó là ví dụ nên chạy. Đừng dùng `allEntries=true` để xóa “mọi key của một tenant” trong cache dùng chung: thao tác này xóa **toàn vùng**, bao gồm cả các tenant khác nếu chúng dùng cùng vùng.

### 2.3. So sánh xóa một entry và toàn vùng

| Tiêu chí | `@CacheEvict` mặc định | `@CacheEvict(allEntries=true)` |
| --- | --- | --- |
| Đối tượng xóa | Entry theo key được sinh ra | Tất cả entry trong cache(s) được chọn |
| Có dùng `key`/`keyGenerator`? | Có, nếu cần chọn key | Không dùng một key; không chỉ định `key` |
| Hiệu lực trên cache khác | Không, trừ khi cùng được chọn | Không, trừ khi cùng được chọn |
| Phù hợp nhất | Một sản phẩm, một user, một bản ghi cụ thể | Import hàng loạt, thay đổi quy tắc diện rộng |
| Chi phí sau xóa | Ít entry phải nạp lại | Có thể gây nhiều cache miss và tăng tải |
| Phân vùng theo tenant | Có thể dùng key mang tenant | Phải tách cache region nếu chỉ muốn clear vùng riêng |

**Nguyên tắc:** chọn phạm vi xóa nhỏ nhất nhưng vẫn đúng. Xóa rộng để “cho chắc” thường làm giảm hiệu quả cache và có thể gây đợt tải đồng thời lên database.

## 3. Thời điểm xóa: `beforeInvocation` và việc phương thức thất bại

Mặc định:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void reload() { /* thay đổi dữ liệu */ }
```

Tương đương `beforeInvocation=false`. Spring thực hiện eviction **sau khi phương thức được gọi thành công**. Nếu phương thức ném exception, cache eviction sau lời gọi không diễn ra.

Trái lại:

```java
@CacheEvict(
    cacheNames = "products",
    allEntries = true,
    beforeInvocation = true
)
public void reload() { /* có thể ném exception */ }
```

Spring thực hiện eviction **trước khi thực thi method**. Vì vậy cache có thể đã bị xóa dù method sau đó lỗi. `@CacheEvict` không làm method bị bỏ qua và có thể áp dụng cho method `void` vì mục đích của annotation là kích hoạt thao tác xóa.

| Trường hợp | `beforeInvocation=false` (mặc định) | `beforeInvocation=true` |
| --- | --- | --- |
| Method hoàn thành bình thường | Xóa sau method | Xóa trước method |
| Method ném exception | Không thực hiện eviction sau method | Đã yêu cầu xóa trước method, không phụ thuộc kết quả |
| Có thể thấy dữ liệu cache cũ trong lúc method chạy | Có thể, do chưa xóa | Trong provider đồng bộ đơn giản, cache đã được clear trước khi body chạy |
| Phù hợp | Xóa dữ liệu cũ sau nghiệp vụ cập nhật thành công | Chủ động invalidate trước một công việc, kể cả khi công việc lỗi |

**Ranh giới quan trọng:** “sau khi method thành công” không đồng nghĩa “sau khi mọi giao dịch database liên quan đã commit” trong mọi cấu hình AOP/transaction. Việc phối hợp với `@Transactional`, transaction-aware cache manager, commit/rollback và backend cache phải được thiết kế và kiểm chứng riêng.

### 3.1. Luồng hoạt động

```text
@CacheEvict(allEntries=true, beforeInvocation=false)

Client -> Spring proxy -> gọi method -> [thành công?]
                                         |
                                       yes -> Cache.clear() -> return
                                         |
                                        no -> exception, không evict sau method

@CacheEvict(allEntries=true, beforeInvocation=true)

Client -> Spring proxy -> Cache.clear() -> gọi method -> return/exception
```

Sơ đồ trình bày luồng logic của cache interceptor trong bối cảnh đồng bộ; các provider hỗ trợ clear deferred/async có thể không khiến mọi entry biến mất ngay lập tức ở thời điểm thao tác clear được gọi.

## 4. Ví dụ Java 17+ hoàn chỉnh: nhiều key, nhiều vùng, điều kiện và lỗi

Ví dụ chạy không cần web server hay Redis. Nó dùng Spring Framework Cache thông qua `spring-boot-starter-cache` (BOM Spring Boot 3.3.13), `ConcurrentMapCacheManager` làm cache trong bộ nhớ và một bộ đếm để nhìn thấy lần body thực sự chạy.

Tạo cây thư mục:

```text
cache-evict-all-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/evict/EvictAllDemo.java
```

Nội dung `settings.gradle`:

```groovy
rootProject.name = 'cache-evict-all-demo'
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}

application {
    mainClass = 'demo.evict.EvictAllDemo'
}
```

Nội dung `src/main/java/demo/evict/EvictAllDemo.java`:

```java
package demo.evict;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class EvictAllDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products", "reference");
        }

        @Bean
        CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final AtomicInteger productLoads = new AtomicInteger();
        private final AtomicInteger referenceLoads = new AtomicInteger();

        @Cacheable(cacheNames = "products")
        public String product(String sku) {
            return sku + "-load-" + productLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "reference")
        public String reference(String code) {
            return code + "-ref-" + referenceLoads.incrementAndGet();
        }

        // Chỉ xóa khi enabled=true. Method vẫn chạy trong cả hai trường hợp.
        @CacheEvict(cacheNames = "products", allEntries = true,
                    condition = "#p0")
        public void clearIf(boolean enabled) {
            // Không cần thao tác dữ liệu cho mô phỏng này.
        }

        // Mặc định xóa sau khi method chạy thành công.
        @CacheEvict(cacheNames = "products", allEntries = true)
        public void clearAfter(boolean fail) {
            if (fail) {
                throw new IllegalStateException("simulated failure");
            }
        }

        // Xóa trước khi method chạy, kể cả khi method ném exception.
        @CacheEvict(cacheNames = "products", allEntries = true,
                    beforeInvocation = true)
        public void clearBefore(boolean fail) {
            if (fail) {
                throw new IllegalStateException("simulated failure");
            }
        }

        public int productExecutions() {
            return productLoads.get();
        }

        public int referenceExecutions() {
            return referenceLoads.get();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("A first: " + service.product("A"));
            System.out.println("B first: " + service.product("B"));
            System.out.println("A hit: " + service.product("A"));
            System.out.println("ref first: " + service.reference("R"));

            service.clearIf(false);
            System.out.println("condition false: " + service.product("B"));

            try {
                service.clearAfter(true);
            } catch (IllegalStateException e) {
                System.out.println("after error: " + e.getMessage());
            }
            System.out.println("after error A: " + service.product("A"));

            service.clearIf(true);
            System.out.println("after clear A: " + service.product("A"));
            System.out.println("after clear B: " + service.product("B"));
            System.out.println("ref still: " + service.reference("R"));

            try {
                service.clearBefore(true);
            } catch (IllegalStateException e) {
                System.out.println("before error: " + e.getMessage());
            }
            System.out.println("after before-error A: " + service.product("A"));

            service.clearAfter(false);
            System.out.println("after success B: " + service.product("B"));
            System.out.println("product executions: " + service.productExecutions());
            System.out.println("reference executions: " + service.referenceExecutions());
        }
    }
}
```

Chạy với JDK 17+ và Gradle tương thích Java 17:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper, dùng `./gradlew run --quiet` (Windows: `gradlew.bat run --quiet`). Dự kiến các dòng do chương trình in ra, không tính log build/framework:

```text
A first: A-load-1
B first: B-load-2
A hit: A-load-1
ref first: R-ref-1
condition false: B-load-2
after error: simulated failure
after error A: A-load-1
after clear A: A-load-3
after clear B: B-load-4
ref still: R-ref-1
before error: simulated failure
after before-error A: A-load-5
after success B: B-load-6
product executions: 6
reference executions: 1
```

Đọc kết quả theo từng giai đoạn:

1. `product("A")` và `product("B")` làm đầy hai key của cache `products`, nên `A hit` trả `A-load-1` mà không tăng bộ đếm.
2. `reference("R")` nằm trong **cache khác**. Nó chỉ chạy một lần trong toàn bộ demo.
3. `clearIf(false)` có `condition=false`, nên không xóa; key `"B"` vẫn hit.
4. `clearAfter(true)` ném exception, vì `beforeInvocation=false` nên không clear; key `"A"` vẫn hit.
5. `clearIf(true)` xóa **cả vùng products**: sau đó *cả A và B* đều miss, tăng bộ đếm lên 3 và 4. Cache `reference` vẫn giữ entry cũ.
6. `clearBefore(true)` xóa trước rồi mới ném exception; `product("A")` sau đó miss, tăng lên 5.
7. `clearAfter(false)` chạy thành công rồi clear; `product("B")` phải tính lại, tăng lên 6. Tổng hai cache cho thấy phạm vi và thời điểm xóa là độc lập.

**Tại sao phải lấy bean từ Spring context?** `@EnableCaching` kích hoạt hạ tầng cache cho các bean được Spring quản lý. Trong chế độ proxy mặc định, gọi từ bên ngoài qua bean do `context.getBean(...)` trả về mới kích hoạt `@Cacheable` và `@CacheEvict`. Gọi `new CatalogService()` hoặc gọi nội bộ `this.clearAfter(...)` có thể bỏ qua advice và khiến demo cho kết quả khác.

**Giới hạn của ví dụ:** `ConcurrentMapCacheManager` phù hợp với thực hành, và phương thức `clear()` của cache bộ nhớ đồng bộ đủ để minh họa hit/miss. Nó không đại diện cho độ trễ hoặc tính nhất quán trên Redis, Hazelcast, nhiều JVM hay cache decorator có transaction.

## 5. `condition` với allEntries: chỉ clear khi thỏa điều kiện

Bạn có thể đặt điều kiện SpEL trên một operation xóa toàn bộ:

```java
@CacheEvict(
    cacheNames = "reports",
    allEntries = true,
    condition = "#p0"
)
public void rebuildReports(boolean shouldInvalidate) {
    // Cập nhật dữ liệu hoặc phát sinh báo cáo.
}
```

Đây là method minh họa, dùng `#p0` để lấy đối số boolean đầu tiên. Với `shouldInvalidate=false`, phương thức **vẫn chạy** nhưng cache clear của annotation không được thực hiện; với true, Spring thực hiện clear theo thời điểm trước/sau method đã được cấu hình. `condition` quyết định **có thực hiện cache operation**, không quyết định method có chạy hay không.

Không dùng `condition` để tránh xóa khi code thực sự đã thay đổi dữ liệu nhưng flag lại sai. Với luồng cập nhật, luôn ưu tiên đảm bảo bất kỳ thay đổi có liên quan nào cũng invalidates đầy đủ vùng cache.

Một số cấu hình có `condition` dựa trên `#p0.type`, `#root.args[1]` hay biến môi trường; hãy giữ điều kiện rõ ràng, an toàn với null và có test. Nếu điều kiện phụ thuộc một biến có thể thay đổi giữa các hệ thống, quá trình clear có thể bất nhất.

## 6. Kết hợp với các cache operation khác

### 6.1. Khi nào xóa toàn vùng là hợp lý?

- **Nhập hàng loạt:** nguồn dữ liệu thay đổi cho nhiều key mà khó biết toàn bộ khóa bị ảnh hưởng.
- **Đổi quy tắc tính toán dùng chung:** ví dụ đổi bảng giá/tỷ lệ khiến hàng loạt entry không còn hợp lệ.
- **Refresh một vùng dữ liệu dẫn xuất:** cache chứa tổng hợp được tính từ nhiều bản ghi; cập nhật một phần của nguồn có thể ảnh hưởng nhiều entry.
- **Thiết lập lại sau đồng bộ dữ liệu:** cần làm mới các entry liên quan thay vì cố đếm/xóa từng key.

### 6.2. Khi nào nên tránh?

Nếu chỉ một sản phẩm thay đổi và key đã biết, dùng xóa theo key:

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void deleteProduct(String sku) {
    repository.delete(sku);
}
```

Đây là method minh họa phụ thuộc repository của ứng dụng. Xóa toàn bộ vùng cho mỗi cập nhật nhỏ có thể làm giảm tỷ lệ hit, tăng tải database và tạo **cache stampede** khi nhiều request cùng nạp lại dữ liệu.

Nếu cache chứa dữ liệu của nhiều tenant, `allEntries=true` với `cacheNames="products"` sẽ quét phạm vi cả region đó chứ không hiểu một tenant cụ thể. Dùng vùng cache riêng theo tenant, namespace có chủ đích, hoặc chiến lược evict theo key/tag do provider hỗ trợ nếu cần phạm vi hẹp hơn.

### 6.3. Nhiều cache cùng phụ thuộc một nguồn

Ví dụ doanh nghiệp có `products` và `productSummary` đều phụ thuộc vào bảng sản phẩm. Chỉ clear `products` sẽ để `productSummary` có nguy cơ stale. Có thể xóa cả hai bằng mảng `cacheNames` ở cùng operation như mục 2, hoặc dùng `@Caching(evict = {...})` khi mỗi vùng cần condition/key/beforeInvocation riêng:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "products", allEntries = true),
    @CacheEvict(cacheNames = "productSummary", allEntries = true)
})
public void reload() { /* import nguồn dữ liệu */ }
```

Đoạn này chỉ là method minh họa, cần import `@Caching` và các class của dự án. Nếu tất cả cache có cùng thời điểm và điều kiện, `cacheNames = {"products", "productSummary"}` ngắn gọn hơn.

**Không mặc định mọi vùng bị xóa cùng lúc một cách atomic.** Spring cache abstraction không cung cấp một transaction phân tán bao trùm nhiều cache backend. Nếu clear vùng thứ nhất thành công rồi vùng khác lỗi, cần chiến lược retry, observability hoặc nhất quán dữ liệu thích hợp.

## 7. Tính nhất quán và transaction trong thực tế

### 7.1. “Clear” không luôn có nghĩa “mọi request sau lập tức không thấy dữ liệu”

Ở mức API, `@CacheEvict(allEntries=true)` gửi yêu cầu clear cache. Javadoc `org.springframework.cache.Cache.clear()` cho phép thao tác clear thực tế được thực hiện **bất đồng bộ hoặc trì hoãn** bởi provider/decorator. Trong trường hợp đó, một lookup gần thời điểm clear có thể tạm thấy entry cũ.

Đặc biệt:
- Transaction-aware cache decorator có thể trì hoãn write/evict/clear đến thời điểm commit.
- Cache phân tán có thể cần thời gian lan truyền trạng thái hoặc đồng bộ đến các node.
- Request đang chạy và tính toán dữ liệu cũ **có thể ghi lại entry cũ** sau thao tác clear nếu không có biện pháp điều phối.

Do vậy, `allEntries=true` **không phải cam kết nhất quán tức thì trên mọi backend**. Nếu hệ thống cần clear với kỳ vọng entry vô hình ngay cho lookup kế tiếp, Spring Cache API có `Cache.invalidate()` với semantics mạnh hơn; tuy nhiên `@CacheEvict` không cung cấp một thuộc tính chuyển trực tiếp từ `clear()` sang `invalidate()`. Cần kiểm tra provider và thiết kế nhất quán ở mức phù hợp.

### 7.2. Không mặc nhiên đồng bộ với transaction database

`@CacheEvict(beforeInvocation=false)` chạy sau khi method trả thành công ở góc nhìn cache advice, **không tự bảo đảm database đã commit** trong mọi thứ tự advice.

Các lựa chọn tùy nhu cầu:
- Dùng cache manager/decorator hỗ trợ transaction-aware khi phù hợp, rồi kiểm tra chính xác cách `clear()` được đồng bộ với commit.
- Phát sự kiện sau commit (ví dụ xử lý ở `TransactionPhase.AFTER_COMMIT`) để invalidation sau giao dịch thành công khi kiến trúc yêu cầu.
- Với hệ thống đa dịch vụ, dùng event/outbox và cơ chế retry/reconciliation nếu cần bảo đảm invalidation không bị mất.
- Khi clear một cache rất lớn, cân nhắc versioned namespace hoặc chiến lược provider hỗ trợ thay cho xóa vật lý đồng loạt.

Chọn giải pháp theo SLA consistency: cache cho gợi ý thống kê có thể chịu stale ngắn; dữ liệu giá, tồn kho, phân quyền cần cam kết chặt hơn. Đặc biệt, **không dùng cache invalidation như biện pháp phân quyền duy nhất**.

### 7.3. Xóa toàn vùng không làm thay đổi dữ liệu gốc

Giả sử method đã xóa cache nhưng import database thất bại giữa chừng. Với `beforeInvocation=true`, cache đã mất entry nhưng dữ liệu nguồn có thể chưa cập nhật. Lần đọc kế tiếp sẽ nạp từ nguồn vẫn cũ hoặc đang dở dang. Chọn thời điểm xóa dựa trên tính chất tác vụ, không chỉ dựa vào ý muốn “luôn clear”.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `allEntries=true` nhưng một vài key vẫn hit | Advice không chạy, cache resolver chọn cache khác, provider clear bị delay, hoặc request đồng thời ghi lại | Kiểm tra Spring proxy, cacheNames/cacheResolver, provider và race condition |
| Xóa cả dữ liệu người dùng khác | Nhiều tenant chia sẻ một vùng và clear allEntries | Tách region/namespace hoặc giảm phạm vi xóa |
| Khởi động lỗi khi có `key` | Ghép `allEntries=true` với `key()` không hợp lệ | Bỏ thuộc tính `key` |
| Method lỗi nhưng cache vẫn bị xóa | `beforeInvocation=true` | Chọn thời điểm phù hợp |
| Method lỗi và cache không bị xóa | `beforeInvocation=false`, đây là mặc định | Kiểm tra thiết kế nghiệp vụ trước/sau lỗi |
| Method chạy nhưng không thấy eviction | `condition=false`, lời gọi bypass proxy hoặc sai cache | Test điều kiện, method visibility, instance thực |
| Xóa cache `products` nhưng `summary` stale | Quên cache phụ thuộc | Xóa đủ các vùng có liên quan |
| Luôn cache miss sau batch update nhỏ | Xóa rộng quá thường xuyên | Xóa theo key hoặc tổ chức lại vùng cache |
| Vừa clear xong nhưng dữ liệu vẫn cũ | Clear deferred, transaction chưa commit hoặc race với request in-flight | Kiểm tra commit timing, provider và chiến lược điều phối |
| Tên cache không tồn tại | CacheManager tĩnh không tạo cache đó hoặc resolver không trả về | Kiểm tra danh sách cache names/CacheManager |

Khi chẩn đoán, phải tách riêng bốn bước: **lời gọi có đi qua Spring proxy không**, **operation chọn vùng cache nào**, **eviction được kích hoạt trước/sau method hay bị condition bỏ qua**, và **backend cache đã thực sự phản ánh clear hay chưa**.

## 9. Checklist triển khai, kiểm thử và vận hành

Trước khi đưa `allEntries=true` vào production:

1. Xác nhận **các vùng cache** chịu ảnh hưởng. Kiểm tra các vùng phụ thuộc cùng nguồn dữ liệu, không chỉ vùng có tên giống phương thức.
2. Phân tích **mức độ thay đổi**: nếu biết key của một entity, ưu tiên `@CacheEvict(key=...)` để không gây invalidation thừa.
3. Kiểm tra `beforeInvocation` theo nghiệp vụ. Nếu cần xóa sau commit, giải quyết timing transaction thay vì cho rằng `beforeInvocation=false` tự cung cấp đảm bảo đó.
4. Đảm bảo phương thức có annotation được **Spring quản lý** và được gọi qua proxy, không phải self-invocation.
5. Đánh giá `condition`: khi false, method vẫn chạy nhưng không evict. Test cả true/false và ngoại lệ.
6. Tạo cache entry cho **ít nhất hai key khác nhau**, gọi method clear, rồi xác minh cả hai key đều miss và phải tính lại.
7. Đặt một entry trong **cache khác** và xác nhận nó không bị xóa ngoài ý muốn.
8. Với provider phân tán, kiểm thử visibility, độ trễ, concurrency và thao tác clear trong transaction; không suy diễn từ `ConcurrentMapCacheManager`.
9. Đo tỷ lệ hit/miss, tải database và mức tăng độ trễ sau clear; cân nhắc warm-up theo nhịp thay vì nạp đồng thời mọi key.
10. Bố trí logging/metrics cho thao tác invalidation diện rộng, vì đây là một tác động lớn đối với hiệu năng và tính đúng đắn của hệ thống.

Trong Spring Boot, ví dụ cấu hình ở mục 4 tự bật cache qua `@EnableCaching`. Khi dùng ứng dụng Boot thực tế, cấu hình cache phải ở `ApplicationContext` chứa các bean service tương ứng; việc có `CacheManager` không thay thế `@EnableCaching`. Nếu có nhiều `CacheManager`/`CacheResolver`, chỉ rõ operation sử dụng manager nào.

Bài kiểm tra nhỏ, theo logic:

```text
Given: cache products có key A và key B, cache reference có key R.
When : gọi @CacheEvict(cacheNames="products", allEntries=true) thành công qua proxy.
Then : A và B không còn được trả từ cache products theo semantics provider;
       cache reference vẫn có R.
And  : lần đọc mới cho A/B sẽ đi vào nguồn và có thể ghi lại entry.
```

Không dùng phép kiểm tra chỉ nhìn method return hoặc số phần tử của một cache riêng lẻ nếu mục tiêu là xác minh các vùng phụ thuộc. Hãy kiểm thử cả dữ liệu nguồn, số lần thực thi, tên vùng, key và tình trạng transactional consistency.

## 10. Câu hỏi tự kiểm tra

**Q1.** Có hai entry `"A"` và `"B"` trong cache `products`. Gọi `@CacheEvict(cacheNames="products", allEntries=true)` thành công sẽ xóa entry nào?

**Đáp:** Spring yêu cầu clear **cả A và B** của cache `products`; không dùng một key cụ thể. Các vùng cache khác không bị operation này đụng tới.

**Q2.** `allEntries=true` có xóa mọi cache trong `CacheManager` không?

**Đáp:** Không. Nó xóa mọi entry của **cache(s) được operation chọn**, thường qua `cacheNames` hoặc `CacheResolver`. Các vùng không được chọn vẫn giữ entry của chúng.

**Q3.** Ghép `allEntries=true` với `key="#p0"` có nên làm không?

**Đáp:** Không. Javadoc `@CacheEvict` quy định tổ hợp này không hợp lệ. Khi xóa toàn vùng, key không có vai trò.

**Q4.** Method ném exception, khi nào cache vẫn có thể đã bị xóa?

**Đáp:** Với `beforeInvocation=true`, eviction được yêu cầu trước method; exception không hoàn tác thao tác đó. Với `beforeInvocation=false`, Spring chỉ thực hiện after-invocation eviction khi method hoàn thành thành công.

**Q5.** Khi `condition=false` trên `@CacheEvict`, method có bị bỏ qua không?

**Đáp:** Không. Điều kiện chỉ kiểm soát cache operation; phương thức vẫn chạy.

**Q6.** Vì sao các entry cũ đôi khi vẫn xuất hiện ngay sau một lần clear?

**Đáp:** Provider có thể thực hiện clear deferred/async; transaction hoặc request đang xử lý song song cũng ảnh hưởng visibility. Cần kiểm chứng theo backend thực tế.

## 11. Ghi nhớ

- `@CacheEvict(allEntries=true)` **clear mọi entry của từng cache được chọn**, không xóa tất cả vùng cache của ứng dụng.
- Khi clear toàn vùng, **không khai báo `key`**; dùng `cacheNames`/`cacheResolver` để chọn cache.
- `beforeInvocation=false` (mặc định) xóa sau thành công; `true` yêu cầu xóa trước method kể cả khi method sau đó lỗi.
- `condition` có thể kiểm soát eviction nhưng **không ngăn method chạy**.
- Clear không tự bảo đảm đồng bộ transaction/visibility tức thời trên mọi backend; cần quan sát provider, concurrency và tác động tới hiệu năng.

### Tài liệu tham khảo chính thức

- [Spring Framework – Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework 6.1 – @CacheEvict Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/cache/annotation/CacheEvict.html)
- [Spring Framework – Cache interface Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework – Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Boot – Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)

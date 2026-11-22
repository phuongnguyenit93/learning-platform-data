# Điều kiện và khóa riêng cho từng thao tác được nhóm bằng @Caching

## 1. Bối cảnh và mục tiêu

Khi một thao tác nghiệp vụ ảnh hưởng nhiều vùng cache, không phải vùng nào cũng có **key** và **điều kiện áp dụng** giống nhau. Ví dụ khi cập nhật sản phẩm: cache `productById` cần xóa entry theo mã sản phẩm, còn cache `regionSummary` chỉ cần xóa theo mã vùng nếu thay đổi đó thật sự tác động số liệu tổng hợp vùng. Cả hai việc có thể thực hiện trên cùng phương thức nghiệp vụ, nhưng không nên dùng nhầm một key hay một condition chung.

Trong Spring Framework, `@Caching` là **annotation gom nhóm** nhiều `@Cacheable`, `@CachePut` và `@CacheEvict` trên một phương thức. Mỗi annotation con có thể khai báo `cacheNames`, `key` hoặc `keyGenerator`, `condition` và thuộc tính riêng hợp lệ.

Một ví dụ ngắn:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "productById",
                key = "#p0",
                condition = "#p0 != null"),
    @CacheEvict(cacheNames = "regionSummary",
                key = "#p1",
                condition = "#p2")
})
public void update(String productId, String region, boolean affectsRegion) {
    repository.update(productId, region);
}
```

Đoạn trên minh họa method trong service có `repository`, không phải file Java chạy độc lập. Với `update("P1", "VN", false)`, operation thứ nhất có thể xóa entry `productById["P1"]`, trong khi operation thứ hai không xóa `regionSummary["VN"]`. **Condition của từng operation được đánh giá độc lập**; condition false của một thao tác con không tự hủy thao tác khác.

Mục tiêu bài học: nắm đúng cơ chế nhóm, cấu trúc key/condition độc lập, tránh lỗi với `@Cacheable`/`@CachePut`, hiểu quan hệ với `@CacheConfig` và kiểm chứng qua chương trình Java 17+.

## 2. Cú pháp và phạm vi của @Caching

`@Caching` chứa ba nhóm cache operation:

| Thuộc tính | Thành phần con | Tác động chính |
| --- | --- | --- |
| `cacheable = { ... }` | `@Cacheable` | Có thể lấy kết quả từ cache; khi hit, method có thể không thực thi |
| `put = { ... }` | `@CachePut` | Method thực thi để lấy kết quả, sau đó cập nhật cache phù hợp |
| `evict = { ... }` | `@CacheEvict` | Xóa entry theo key hoặc toàn bộ cache được chọn |

Ví dụ khai báo hai eviction:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "byId", key = "#p0"),
    @CacheEvict(cacheNames = "byRegion", key = "#p1",
                condition = "#p2")
})
public void modify(String id, String region, boolean regionChanged) {
    // Cập nhật nguồn dữ liệu.
}
```

Khác với cách đặt `@CacheEvict(cacheNames={"byId","byRegion"}, key="#p0")`, mỗi annotation con ở đây có **key riêng**. Nếu hai vùng dùng khóa khác kiểu hoặc phải quyết định có xóa theo những điều kiện khác nhau, việc nhóm nhiều operation rõ ràng hơn việc đặt một tên cache dạng mảng vào cùng operation.

Cần phân biệt:
- **`@Caching` chỉ gom metadata**; không tạo cache, không bật annotation processing, không có thuộc tính `condition` hay `key` chung trên container.
- **`@EnableCaching`** bật cơ chế xử lý cache annotation trong `ApplicationContext` chứa các bean cần intercept.
- **`CacheManager`** cung cấp các vùng cache thực tế. `cacheNames` quyết định vùng, `key` quyết định entry.
- **`@CacheConfig`** có thể đặt một số mặc định cấp class; operation con vẫn có quyền ghi đè theo từng trường phù hợp.

Không nhầm “đặt chung trong @Caching” với “tất cả hoạt động trong một transaction nguyên tử”.

## 3. Điều kiện và key được đánh giá riêng

Xét hai operation:

```java
@Caching(evict = {
    @CacheEvict(
        cacheNames = "productById",
        key = "#p0",
        condition = "#p0 != null && !#p0.isBlank()"
    ),
    @CacheEvict(
        cacheNames = "regionSummary",
        key = "#p1",
        condition = "#p2 && #p1 != null && !#p1.isBlank()"
    )
})
public void modify(String productId, String region, boolean regionAffected) {
    // Thay đổi dữ liệu.
}
```

Khi gọi `modify("P1", "VN", false)`:

1. `#p0` là `"P1"`, nên operation `productById` thỏa condition và dùng key `"P1"`.
2. `#p1` là `"VN"` nhưng `#p2=false`, nên operation `regionSummary` bỏ qua eviction.
3. Method vẫn chạy. Condition trên `@CacheEvict` quyết định **có xóa cache hay không**, không ngăn nghiệp vụ thực thi.

Khi gọi `modify("P1","VN",true)`, cả hai operation có thể evict các entry tương ứng. Việc dùng `#p0` trong annotation thứ nhất không gây ảnh hưởng tới `#p1` của annotation thứ hai.

### 3.1. Biểu thức SpEL và chỉ số tham số

| Biểu thức | Ý nghĩa |
| --- | --- |
| `#p0` hoặc `#a0` | Tham số thứ nhất |
| `#p1` hoặc `#a1` | Tham số thứ hai |
| `#p2` hoặc `#a2` | Tham số thứ ba |
| `#root.args[0]` | Phần tử thứ nhất trong mảng arguments |
| `#root.methodName` | Tên phương thức hiện tại |
| `#result` | Kết quả method, chỉ trong các ngữ cảnh sau khi kết quả sẵn có |

Ưu tiên cú pháp `#p0`/`#p1` nếu không chắc tên tham số Java có được giữ bằng `-parameters`. Dùng short-circuit như `#p1 != null && !#p1.isBlank()` để tránh gọi phương thức trên null.

**Lưu ý về `#result`:** Với `@Cacheable`, `condition` cần quyết định việc lookup **trước khi method chạy**, nên không thể dùng kết quả chưa có. `unless` của `@Cacheable` được đánh giá sau method khi có kết quả. Với `@CachePut`, biểu thức tính key/condition có thể sử dụng kết quả sau invocation theo ngữ cảnh hỗ trợ. `@CacheEvict(beforeInvocation=true)` không thể dùng kết quả method ở bước trước lời gọi.

### 3.2. Key phải khớp với phương thức đọc

Giả sử:

```java
@Cacheable(cacheNames = "productById", key = "#p0")
public Product getProduct(String productId) {
    return repository.findProduct(productId);
}

@Cacheable(cacheNames = "regionSummary", key = "#p0")
public Summary getSummary(String region) {
    return repository.findSummary(region);
}
```

Đoạn trên chỉ minh họa service có repository/kiểu dữ liệu tương ứng. Phương thức đọc đều dùng `#p0` vì mỗi method nhận một tham số; method update nhận ba tham số nên cần evict theo `#p0` (ID) **và** `#p1` (region) tương ứng. Nếu evict region với `key="#p0"`, Spring sẽ xóa nhầm key `"P1"` trong cache vùng, bỏ lại entry `"VN"` có thể đã cũ.

Không đặt điều kiện chỉ vì muốn tối ưu vô căn cứ. Ví dụ nếu update đã thay đổi dữ liệu region mà truyền `regionAffected=false`, cache tổng hợp sẽ trở nên stale. Condition phải phản ánh đúng nghiệp vụ.

## 4. Ví dụ Java 17+ chạy được: hai vùng và hai key

Chương trình dùng `ConcurrentMapCacheManager`, dữ liệu bộ nhớ và hai bộ đếm để thấy rõ cache hit/miss. Để minh họa condition chính xác, khi `regionAffected=false`, method chỉ thay đổi phiên bản sản phẩm; khi true, nó cũng thay đổi phiên bản tổng hợp vùng.

Cấu trúc:

```text
grouped-cache-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/grouped/GroupedCacheDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'grouped-cache-demo'
```

`build.gradle`:

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
    mainClass = 'demo.grouped.GroupedCacheDemo'
}
```

`src/main/java/demo/grouped/GroupedCacheDemo.java` (một file Java đầy đủ):

```java
package demo.grouped;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Caching;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class GroupedCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {
        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager(
                    "productById", "regionSummary");
        }

        @Bean
        CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final Map<String, Integer> productVersions =
                new ConcurrentHashMap<>();
        private final Map<String, Integer> regionVersions =
                new ConcurrentHashMap<>();
        private final AtomicInteger productLoads = new AtomicInteger();
        private final AtomicInteger regionLoads = new AtomicInteger();

        @Cacheable(cacheNames = "productById", key = "#p0")
        public String product(String id) {
            int v = productVersions.getOrDefault(id, 0);
            return id + "-v" + v
                    + "-load" + productLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "regionSummary", key = "#p0")
        public String summary(String region) {
            int v = regionVersions.getOrDefault(region, 0);
            return region + "-v" + v
                    + "-load" + regionLoads.incrementAndGet();
        }

        @Caching(evict = {
            @CacheEvict(
                cacheNames = "productById",
                key = "#p0",
                condition = "#p0 != null && !#p0.isBlank()"
            ),
            @CacheEvict(
                cacheNames = "regionSummary",
                key = "#p1",
                condition = "#p2 && #p1 != null && !#p1.isBlank()"
            )
        })
        public void modify(String id, String region,
                           boolean regionAffected) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id is required");
            }
            if (regionAffected && (region == null || region.isBlank())) {
                throw new IllegalArgumentException("region is required");
            }

            productVersions.merge(id, 1, Integer::sum);
            if (regionAffected) {
                regionVersions.merge(region, 1, Integer::sum);
            }
        }

        public String counts() {
            return productLoads.get() + "/" + regionLoads.get();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(CacheConfig.class)) {

            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("id-first=" + service.product("P1"));
            System.out.println("id-hit=" + service.product("P1"));
            System.out.println("region-first=" + service.summary("VN"));
            System.out.println("region-hit=" + service.summary("VN"));

            // Chỉ sửa sản phẩm. Region không đổi nên không evict region.
            service.modify("P1", "VN", false);
            System.out.println("id-after-one=" + service.product("P1"));
            System.out.println("region-after-one=" + service.summary("VN"));

            // Thay đổi cả sản phẩm và thống kê vùng.
            service.modify("P1", "VN", true);
            System.out.println("id-after-two=" + service.product("P1"));
            System.out.println("region-after-two=" + service.summary("VN"));

            System.out.println("loads=" + service.counts());
        }
    }
}
```

Chạy từ thư mục dự án bằng JDK 17+ và Gradle:

```bash
gradle run --quiet
```

Hoặc `./gradlew run --quiet` khi đã có Gradle Wrapper; Windows: `gradlew.bat run --quiet`. Những dòng do chính chương trình in (không tính log khởi động từ thư viện/build) là:

```text
id-first=P1-v0-load1
id-hit=P1-v0-load1
region-first=VN-v0-load1
region-hit=VN-v0-load1
id-after-one=P1-v1-load2
region-after-one=VN-v0-load1
id-after-two=P1-v2-load3
region-after-two=VN-v1-load2
loads=3/2
```

**Giải thích theo lần gọi:**
1. Hai lần `product("P1")` cùng key nên lần hai hit, productLoads chỉ bằng 1. Tương tự, `summary("VN")` chỉ load một lần.
2. `modify("P1","VN",false)` làm tăng version sản phẩm từ 0 lên 1. Operation `productById` evict key `P1`; operation `regionSummary` có condition false, giữ key `VN`. Vì dữ liệu vùng không đổi, hit trên region vẫn hợp lệ.
3. `modify("P1","VN",true)` tăng version cả hai nguồn; cả hai operation evict. Hai lần đọc tiếp theo đều miss, nạp giá trị mới.
4. `loads=3/2` thể hiện ba lần thực thi method `product` và hai lần thực thi `summary` trong toàn bộ bài.

**Điều kiện để annotation có hiệu lực:** `@EnableCaching` được đăng ký trong đúng context, service là bean Spring và lời gọi đi qua proxy (ở đây lấy qua `context.getBean(...)`). Nếu gọi `new CatalogService()` hoặc `this.modify(...)` bên trong cùng target, advice cache ở chế độ proxy mặc định không được áp dụng. Ví dụ là mô hình đơn giản, không thay thế transaction hay cơ chế đồng bộ dữ liệu thật.

## 5. Nhóm @CachePut: hai phép ghi, hai key/condition

Khi một kết quả method cần cập nhật nhiều vùng cache với **hai kiểu key**, dùng `@Caching(put={...})`:

```java
@Caching(put = {
    @CachePut(cacheNames = "articleById", key = "#p0",
              condition = "#p2"),
    @CachePut(cacheNames = "articleBySlug", key = "#p1",
              condition = "#p3")
})
public Article save(String id, String slug,
                    boolean refreshId, boolean refreshSlug) {
    return repository.save(id, slug);
}
```

Đây là đoạn minh họa trong service có `Article` và `repository` phù hợp. `@CachePut` **luôn để method thực thi**. Sau khi có kết quả, các operation đủ điều kiện có thể ghi cùng giá trị trả về dưới key:
- `articleById[id]` khi `refreshId=true`;
- `articleBySlug[slug]` khi `refreshSlug=true`.

Một `condition=false` không làm ngừng operation còn lại. Nếu hai flag đều false, method vẫn chạy nhưng không có put từ hai annotation.

Khi lưu bản ghi đổi `slug` từ cũ sang mới, việc put theo key slug mới **không tự xóa key cũ**. Cần thêm eviction phù hợp hoặc thiết kế lại cache key để tránh còn dữ liệu stale. Với kết quả có thể null, cân nhắc `unless="#result == null"` để veto cache put theo nhu cầu.

## 6. Nhóm @Cacheable: điều kiện loại trừ nhau

Có thể dùng nhiều `@Cacheable` nếu mỗi nhánh phục vụ một chế độ đọc khác nhau:

```java
@Caching(cacheable = {
    @Cacheable(cacheNames = "lookupById",
               key = "#p0", condition = "#p1 == 'ID'"),
    @Cacheable(cacheNames = "lookupByAlias",
               key = "#p0", condition = "#p1 == 'ALIAS'")
})
public Item lookup(String value, String mode) {
    return repository.lookup(value, mode);
}
```

Đây là đoạn minh họa; kiểu `Item` và repository thuộc ứng dụng. Mode `ID` dùng vùng thứ nhất, `ALIAS` dùng vùng thứ hai. Vì hai condition loại trừ nhau nên cách chọn vùng dễ dự đoán. Mode khác làm cả hai condition false, method chạy không sử dụng hai cache đó.

**Nếu nhiều `@Cacheable` cùng thỏa condition**, các thao tác có thể cùng tham gia lookup/caching. Không dựa vào thứ tự sắp xếp trong `@Caching` để chọn vùng “đúng” khi hai vùng có dữ liệu khác nhau. Nếu đơn giản là muốn kiểm tra nhiều vùng cùng **một key/condition**, đôi khi một `@Cacheable(cacheNames={"cacheA","cacheB"},key="#p0")` rõ hơn.

**Đặc biệt tránh trộn `@Cacheable` và `@CachePut` cùng method:** Cacheable có thể bỏ qua method khi hit, trong khi CachePut cần chạy method. Spring Framework khuyến cáo không dùng chung, trừ trường hợp điều kiện đã được thiết kế loại trừ nhau chắc chắn **trước invocation**; không dùng `#result` trong condition để cố giải quyết mâu thuẫn này.

## 7. @CacheConfig là cấu hình mặc định, không phải nhóm operation

`@CacheConfig` dùng để tránh lặp lại một số thuộc tính cấp class, gồm `cacheNames`, `keyGenerator`, `cacheManager` và `cacheResolver`. Nó không tạo quy tắc `condition` dùng chung và không tự kích hoạt `@Caching`.

```java
@CacheConfig(cacheNames = "products")
@Service
public class ProductService {

    @Cacheable(key = "#p0")
    public Product find(String id) {
        return repository.find(id);
    }

    @Caching(evict = {
        @CacheEvict(key = "#p0"),
        @CacheEvict(cacheNames = "regionSummary",
                    key = "#p1", condition = "#p2")
    })
    public void update(String id, String region, boolean affected) {
        repository.update(id, region);
    }
}
```

Đoạn này minh họa cấu trúc service; cần class, imports và repository thật. Operation `@CacheEvict(key="#p0")` kế thừa `cacheNames="products"` từ `@CacheConfig`, còn operation thứ hai đặt `cacheNames="regionSummary"` để ghi đè mặc định **chỉ cho chính nó**. Key vẫn khác nhau.

Quy tắc xét cấu hình là **cấp operation > cấp class > cấu hình toàn cục** đối với những thuộc tính tương ứng có hỗ trợ. Không hiểu nhầm rằng tất cả operation của `@Caching` phải dùng một key chỉ vì cùng `@CacheConfig`.

## 8. Những sai lầm phổ biến

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Evict vùng nhưng key vẫn hit | Tham số của method ghi khác vị trí với method đọc | So sánh cache name và key thực tế, sửa `#p0`/`#p1` |
| Một vùng bị evict, vùng kia không | `condition` của operation thứ hai false hoặc thiếu annotation con | Test riêng nhánh true/false |
| Điều kiện true nhưng không có proxy | Sai `ApplicationContext`, self-invocation hoặc new object | Gọi qua bean Spring và bật `@EnableCaching` đúng nơi |
| Cần xóa một key nhưng cả vùng mất cache | Dùng `allEntries=true` quá rộng | Dùng key, tách cache theo tenant/nhu cầu |
| Lỗi khi vừa khai báo `key` và `keyGenerator` | Hai thuộc tính loại trừ nhau trong một operation | Chọn đúng một cách tạo key |
| Key cũ còn tồn tại sau đổi slug | `@CachePut` chỉ ghi key mới | Evict key cũ tương ứng |
| Method bị bỏ qua dù muốn cập nhật cache | Trộn `@Cacheable` và `@CachePut` không phù hợp | Tách đọc/ghi, hoặc conditions loại trừ an toàn |
| Evict không đúng khi method ném exception | Không hiểu `beforeInvocation` | Mặc định false xóa sau khi method thành công; true xóa trước |
| Cập nhật dữ liệu rồi cache vẫn cũ | Thiếu vùng phụ thuộc hoặc transaction/provider delay | Xây chiến lược invalidation sau commit, test backend |
| Dữ liệu bị trả nhầm tenant | Cache key thiếu tenant scope | Cần key/region và bảo mật đúng, không trông vào condition |

### 8.1. Từng @CacheEvict có beforeInvocation riêng

`@CacheEvict(beforeInvocation=false)` (mặc định) chỉ thực hiện eviction sau khi method hoàn thành thành công; `beforeInvocation=true` yêu cầu xóa trước khi method chạy, kể cả sau đó xảy ra lỗi. Nếu hai operation trong nhóm có hai giá trị khác nhau, chúng có thể chạy ở **hai giai đoạn khác nhau**. Đừng cho rằng annotation array luôn là “chuỗi lệnh tuần tự” có thứ tự nhất quán như một transaction.

### 8.2. allEntries là xóa vùng, không chọn một key

`@CacheEvict(cacheNames="reports", allEntries=true, condition="#p1")` sẽ clear vùng `reports` khi condition đúng; nó không dùng key riêng. **Không khai báo đồng thời `key` với `allEntries=true`.** Nhóm có thể chứa một operation xóa một key của cache A và operation clear toàn cache B, nhưng hãy giải thích rõ phạm vi.

### 8.3. Không có atomicity mặc định giữa nhiều cache

Một operation xóa thành công ở backend A và một operation khác thất bại ở backend B không được `@Caching` tự rollback lại như một transaction phân tán. Khi cần tính nhất quán cao, kiểm tra cache provider, transaction boundary, retry/outbox, việc xóa sau commit hoặc namespace versioned. Không xem `condition` như công cụ phân quyền; cache hit cũng phải được bảo vệ đúng.

## 9. Checklist kiểm thử theo từng thao tác

1. Liệt kê mọi vùng cache phụ thuộc một thao tác nghiệp vụ; mô tả cách xác định key của từng vùng.
2. Kiểm tra từng key của operation ghi/xóa có **cùng dạng và giá trị** với key mà phía đọc dùng.
3. Tạo dữ liệu cache mẫu ở hai vùng, hai key khác nhau. Gọi method với condition thứ hai false: xác minh chỉ vùng thứ nhất bị ảnh hưởng.
4. Gọi với condition thứ hai true: xác minh cả hai vùng được cập nhật/xóa đúng, không ảnh hưởng cache ngoài phạm vi.
5. Kiểm tra trường hợp null/chuỗi trống; SpEL có null-guard, nhưng business method phải xử lý input theo contract riêng.
6. Kiểm tra đổi region, đổi slug, đổi tenant và các key **cũ** phải evict; thay đổi key thường cần xóa cả cũ lẫn mới.
7. Thử exception với `beforeInvocation=true/false`, tránh giả định không có eviction khi method lỗi.
8. Dùng integration test lấy service từ Spring context; không chỉ kiểm thử bằng cách `new Service()` vì sẽ bỏ qua proxy.
9. Với provider thực tế, xác minh TTL, visibility và transaction synchronization, không suy luận hoàn toàn từ cache in-memory.
10. Theo dõi hit/miss, cache size và số lần truy vấn nguồn để kiểm chứng việc nhóm operations có đúng tác dụng.

Một kiểm tra ngắn tương đương output của ví dụ:
- Trước update, `product("P1")` và `summary("VN")` đều hit ở lần thứ hai.
- Sau update chỉ product, đọc `P1` miss và `VN` hit.
- Sau update cả hai, `P1` và `VN` đều miss.
- Bộ đếm là `3/2`; nếu khác, cần xem lại proxy, condition, cache name hoặc key.

## 10. Câu hỏi tự đánh giá

**Q1.** Hai `@CacheEvict` nằm cùng `@Caching(evict={...})`, condition thứ hai false. Cả nhóm có bị hủy không?

**Đáp:** Không. Mỗi operation có điều kiện riêng; operation thứ nhất vẫn có thể chạy.

**Q2.** Phương thức đọc nhận `(region)` ở `#p0`, còn method cập nhật nhận `(productId, region)`. Operation xóa summary dùng key nào?

**Đáp:** `#p1` tại method cập nhật, để key thực tế trùng region của phía đọc.

**Q3.** Muốn một lần save ghi kết quả vào hai vùng theo ID và slug, mỗi vùng có cờ bật riêng?

**Đáp:** Dùng `@Caching(put={@CachePut(...), @CachePut(...)})` với hai key và condition riêng. Phương thức save vẫn được gọi.

**Q4.** `@CacheConfig(cacheNames="products")` có áp cùng `condition` cho mọi annotation con không?

**Đáp:** Không; @CacheConfig chỉ hỗ trợ một số mặc định cấp class, không phải condition chung.

**Q5.** Vì sao không nên trộn `@Cacheable` và `@CachePut` bừa bãi?

**Đáp:** Cacheable có thể skip method khi hit, còn CachePut cần method chạy để put; semantics đối nghịch.

**Q6.** Hai eviction đã được nhóm có đồng nghĩa với một transaction atomic không?

**Đáp:** Không. Cần kiểm soát consistency, transaction và lỗi backend riêng.

## 11. Ghi nhớ và tài liệu tham khảo

- **`@Caching` nhóm nhiều operations; mỗi annotation con giữ key, condition và cache name riêng.**
- `condition=false` của một operation không tự ngăn operation khác.
- Key của xóa/ghi phải khớp key của thao tác đọc, kể cả khi tham số ở vị trí khác.
- `@CachePut` luôn thực thi method; thận trọng khi trộn với `@Cacheable`.
- `@CacheConfig` là các mặc định cấp class, không thay thế cấu hình per-operation hay `@EnableCaching`.
- Một nhóm operations không tự cung cấp tính nhất quán transaction/atomicity giữa các cache.

Nguồn chính thức để học sâu:
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — @Caching Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Caching.html)
- [Spring Framework — @CacheConfig Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheConfig.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)

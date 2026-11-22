# CacheResolver và lựa chọn cache cho từng thao tác trong Spring Framework

## 1. Vì sao cần chọn cache theo từng thao tác?

Spring Cache tách **nghiệp vụ** khỏi **nơi lưu kết quả tạm thời**. Cùng một phương thức đọc sản phẩm có thể cần cache khác nhau theo nhóm người dùng, tenant, vùng dữ liệu hoặc chính sách thời gian sống (TTL). Nếu chọn sai cache, hai nhóm có thể đọc nhầm dữ liệu của nhau; nếu thao tác đọc và cập nhật chọn khác cache, bản ghi cũ có thể tồn tại dù đã cập nhật.

Ví dụ: cùng mã sản phẩm 42 nhưng dữ liệu hiển thị cho PUBLIC và VIP khác nhau. Ta muốn các lời gọi `find(PUBLIC, 42)` truy cập `catalogPublic`, còn `find(VIP, 42)` truy cập `catalogVip`. Khi cập nhật/xóa cache, thao tác tương ứng phải xác định cùng vùng lưu trữ với thao tác đọc.

**Phân biệt hai việc:**
- *Chọn cache nào?* Do `CacheResolver` hoặc cấu hình tên cache + `CacheManager` quyết định.
- *Chọn entry nào trong cache?* Do cache key, thường qua `key`/`keyGenerator`, quyết định.

Khác cache không đồng nghĩa khác key. Hai cache riêng có thể cùng chứa key `42` mà không xung đột; ngược lại, nếu đặt nhiều tenant vào một cache chung, key phải chứa danh tính tenant.

## 2. Thành phần và cơ chế

| Thành phần | Vai trò |
| --- | --- |
| `Cache` | Một vùng lưu các cặp key/value; API có `get`, `put`, `evict`, `clear`. |
| `CacheManager` | Quản lý và trả về `Cache` qua `getCache(name)`. |
| `CacheResolver` | Nhận ngữ cảnh của **lời gọi đang được intercept**, quyết định một hoặc nhiều đối tượng `Cache` cần dùng. |
| `KeyGenerator` hoặc biểu thức `key` | Tạo key cho entry **bên trong** cache đã chọn. |
| `@EnableCaching` và Spring AOP | Bật xử lý các annotation cache khi lời gọi đi qua Spring proxy. |

Luồng khái niệm:

```text
Client -> Spring proxy -> nhận diện cache operation
                       -> resolve cache(s) theo cấu hình hoặc lời gọi thực tế
                       -> xác định key và điều kiện
                       -> @Cacheable: tra cache, miss thì gọi method và lưu kết quả
                       -> @CachePut: gọi method rồi ghi kết quả vào cache
                       -> @CacheEvict: xóa entry / toàn cache theo chính sách
```

Đây là sơ đồ chức năng, không phải thứ tự thực thi chi tiết cố định cho mọi điều kiện và provider.

Giao diện cốt lõi:

```java
@FunctionalInterface
public interface CacheResolver {
    Collection<? extends Cache> resolveCaches(
            CacheOperationInvocationContext<?> context);
}
```

`context.getArgs()` cung cấp tham số lời gọi; `context.getMethod()` và `context.getTarget()` giúp xem phương thức/đối tượng; `context.getOperation()` cho biết metadata của thao tác cache. Resolver **trả về đối tượng `Cache`, không trả về chuỗi tên**. Kết quả không được là `null`; khi không tìm được cache bắt buộc, nên báo lỗi rõ ràng. Implementation phải thread-safe vì bean có thể được gọi đồng thời.

Mặc định, Spring dùng cơ chế tương đương `SimpleCacheResolver` để tra các tên trong `cacheNames`/`value` từ `CacheManager` được cấu hình. Chỉ cần viết resolver riêng khi lựa chọn phụ thuộc vào thông tin mà tên tĩnh hoặc việc chỉ định manager không biểu đạt đủ.

## 3. Chọn cơ chế phù hợp với bài toán

| Yêu cầu | Cách cấu hình | Khi nào dùng |
| --- | --- | --- |
| Một cache cố định | `@Cacheable(cacheNames = "products")` | Phương thức luôn truy cập một cache. |
| Cùng tên cache nhưng chọn manager khác theo phương thức | `@Cacheable(cacheNames = "products", cacheManager = "fastCacheManager")` | Mỗi thao tác dùng backend cố định. |
| Phân vùng cache theo tham số runtime | `@Cacheable(cacheResolver = "audienceCacheResolver")` | Cache được quyết định theo audience/tenant/region của lời gọi. |
| Dùng cấu hình chung cho nhiều method | `@CacheConfig(cacheNames = "products")` hoặc `@CacheConfig(cacheResolver = "audienceCacheResolver")` | Giảm lặp trong một service; method vẫn có thể ghi đè khi cần. |
| Một method tác động nhiều cache operation | `@Caching(...)` | Kết hợp nhiều annotation có mục đích riêng; phải kiểm tra nhất quán giữa các operation. |

**Quy tắc quan trọng:** Trên **cùng một cache operation**, không đặt cả `cacheManager` và `cacheResolver` vì hai lựa chọn loại trừ nhau. Nếu sử dụng resolver tùy biến, `cacheNames` có thể bỏ trống: resolver tự quyết định danh sách cache. Tuy vậy, nếu resolver dựa vào `context.getOperation().getCacheNames()`, bạn vẫn phải khai báo các tên cần thiết.

Đừng dùng resolver chỉ để thay đổi key. Nếu cache vật lý giữ nguyên và chỉ cần phân biệt mã khách hàng/tenant, nhiều khi `key = "#p0 + ':' + #p1"` hoặc `KeyGenerator` là đủ. Nếu cần tách backend, TTL, quyền truy cập hay vùng lưu trữ theo lời gọi, resolver mới có ý nghĩa rõ ràng.

## 4. Ví dụ chạy được: chọn cache PUBLIC/VIP khi đọc, cập nhật và xóa

Ví dụ dùng **Java 17+, Spring Boot 3.3.x / Spring Framework 6.1.x**, gồm các dependency `spring-boot-starter` và `spring-boot-starter-cache`. Tạo ứng dụng Spring Boot với hai starter đó, đặt mã dưới đây tại `src/main/java/demo/cache/CacheRoutingDemo.java`. Cache in-memory `ConcurrentMapCacheManager` giúp nhìn thấy hành vi mà không cần Redis.

```java
package demo.cache;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableCaching
public class CacheRoutingDemo {

    public static void main(String[] args) {
        SpringApplication.run(CacheRoutingDemo.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        // Khai báo trước các cache được phép sử dụng.
        return new ConcurrentMapCacheManager("catalogPublic", "catalogVip");
    }

    @Bean("audienceCacheResolver")
    CacheResolver audienceCacheResolver(CacheManager manager) {
        return context -> {
            Object[] args = context.getArgs();
            if (args.length == 0 || !(args[0] instanceof Audience audience)) {
                throw new IllegalArgumentException(
                        "Tham số đầu tiên phải là Audience");
            }

            String name = audience == Audience.VIP
                    ? "catalogVip"
                    : "catalogPublic";
            Cache cache = manager.getCache(name);
            if (cache == null) {
                throw new IllegalStateException("Chưa cấu hình cache: " + name);
            }
            return List.of(cache);
        };
    }

    @Bean
    CommandLineRunner demo(CatalogService service) {
        return args -> {
            System.out.println(service.find(Audience.PUBLIC, 42L));
            System.out.println(service.find(Audience.PUBLIC, 42L));
            System.out.println(service.find(Audience.VIP, 42L));
            System.out.println(service.refresh(Audience.PUBLIC, 42L));
            System.out.println(service.find(Audience.PUBLIC, 42L));
            service.invalidate(Audience.VIP, 42L);
            System.out.println(service.find(Audience.VIP, 42L));
            System.out.println("Method executions: " + service.executionCount());
        };
    }
}

enum Audience {
    PUBLIC, VIP
}

@Service
class CatalogService {
    private final AtomicInteger executions = new AtomicInteger();

    @Cacheable(cacheResolver = "audienceCacheResolver", key = "#p1")
    public String find(Audience audience, long productId) {
        return audience + "#" + productId + "-load-"
                + executions.incrementAndGet();
    }

    @CachePut(cacheResolver = "audienceCacheResolver", key = "#p1")
    public String refresh(Audience audience, long productId) {
        return audience + "#" + productId + "-refresh-"
                + executions.incrementAndGet();
    }

    @CacheEvict(cacheResolver = "audienceCacheResolver", key = "#p1")
    public void invalidate(Audience audience, long productId) {
        // Nghiệp vụ xóa/sửa dữ liệu thật sẽ nằm ở đây.
    }

    public int executionCount() {
        return executions.get();
    }
}
```

Khởi chạy bằng lệnh `./gradlew bootRun` (Windows PowerShell: `./gradlew.bat bootRun`) trong dự án Spring Boot có Gradle Wrapper. Những dòng `System.out.println` sẽ tạo đúng kết quả sau; log khởi động Spring Boot có thể xuất hiện thêm:

```text
PUBLIC#42-load-1
PUBLIC#42-load-1
VIP#42-load-2
PUBLIC#42-refresh-3
PUBLIC#42-refresh-3
VIP#42-load-4
Method executions: 4
```

Giải thích từng bước:

1. Lần đọc PUBLIC đầu tiên: cache `catalogPublic` miss nên chạy `find` (lần thực thi 1).
2. Đọc lại PUBLIC/42: hit cùng cache/key nên bỏ qua body method; vẫn trả giá trị lần 1.
3. Đọc VIP/42: resolver chọn `catalogVip`, miss độc lập nên chạy `find` (lần 2).
4. `refresh(PUBLIC, 42)` có `@CachePut`: **luôn chạy method** rồi ghi giá trị mới vào `catalogPublic` (lần 3).
5. Đọc PUBLIC/42 nhận dữ liệu mới, không thực thi `find`.
6. `invalidate(VIP, 42)` chỉ xóa key 42 trong `catalogVip`; đọc lại VIP/42 sẽ miss (lần 4). PUBLIC không bị ảnh hưởng.

Điểm mấu chốt là cả ba thao tác **đọc – ghi – xóa** dùng cùng quy tắc định tuyến PUBLIC/VIP và cùng key `#p1`. Ở đây `#p1` là tham số thứ hai (`productId`), tránh phụ thuộc vào tên tham số khi biên dịch. Tham số thứ nhất (`audience`) tham gia **chọn cache**. Nếu gom tất cả vào một cache, key 42 đơn lẻ sẽ không đủ phân biệt hai audience.

## 5. Những biến thể cần biết

### 5.1. Chọn manager theo từng method không cần custom resolver

```java
@Cacheable(cacheNames = "productCards", cacheManager = "localCacheManager")
public ProductCard findCard(long id) { /* ... */ }

@Cacheable(cacheNames = "productDetails", cacheManager = "redisCacheManager")
public ProductDetails findDetails(long id) { /* ... */ }
```

Đoạn trên là **minh họa trong service có sẵn**, không phải chương trình độc lập. Hai bean `CacheManager` phải được cấu hình trước; mỗi method chọn manager cố định. Khi chọn dựa trên tham số thực tế của *cùng* method, dùng custom `CacheResolver` phù hợp hơn.

### 5.2. Phân biệt quy tắc cho từng operation

- `@Cacheable` đọc cache trước; nếu hit phù hợp thì không chạy method. `condition` và `unless` ảnh hưởng việc cache hóa theo thời điểm Spring hỗ trợ.
- `@CachePut` thực thi method và cập nhật cache theo điều kiện; không dùng để tối ưu lượt đọc. Tránh đặt `@CachePut` và `@Cacheable` chung một method nếu chưa chứng minh các điều kiện loại trừ nhau.
- `@CacheEvict` mặc định evict **sau khi method thành công**; `beforeInvocation = true` evict trước cả khi method có thể ném exception. `allEntries = true` xóa toàn bộ **các cache mà resolver trả về**, và không được cấu hình `key` đồng thời.
- `@Caching` nhóm nhiều operation. Mỗi operation có thể khai báo cache khác nhau, nhưng các thao tác liên quan cùng thực thể phải nhất quán về tuyến cache và key.

Ví dụ minh họa chính sách xóa toàn bộ **một vùng**:

```java
@CacheEvict(cacheResolver = "audienceCacheResolver", allEntries = true)
public void invalidateAudience(Audience audience) {
    // Thực hiện thay đổi dữ liệu của audience này.
}
```

Resolver đọc `audience` và chỉ trả về `catalogPublic` hoặc `catalogVip`; vì vậy `allEntries` ở đây không có nghĩa xóa **mọi cache trong CacheManager**. Ngược lại, nếu resolver trả nhiều cache, thao tác có thể tác động tới tất cả cache đó.

### 5.3. Dùng chung cấu hình resolver

```java
@CacheConfig(cacheResolver = "audienceCacheResolver")
@Service
class AnotherCatalogService {
    @Cacheable(key = "#p1")
    public String read(Audience audience, long id) { /* ... */ return ""; }
}
```

Đây là đoạn minh họa cú pháp của cấu hình ở cấp lớp; khi dùng thực tế phải thay body method bằng nghiệp vụ thật. `@CacheConfig` chia sẻ mặc định, còn annotation cấp method có thể chỉ định cấu hình cụ thể của operation.

## 6. Những rủi ro kiến trúc quan trọng

**Tách biệt tenant / phân quyền.** Resolver có thể dựa vào tenant từ tham số hoặc ngữ cảnh xác thực đáng tin cậy. Phải kiểm tra người gọi thực sự được phép truy cập tenant đó trước khi trả dữ liệu. Chia cache theo role chưa chắc đủ bảo mật: nếu hai người VIP có dữ liệu cá nhân khác nhau, key vẫn cần danh tính người dùng hoặc vùng dữ liệu an toàn hơn. Không đưa thông tin nhạy cảm vào tên cache/log.

**Nhất quán khi cập nhật dữ liệu.** Khi một sản phẩm được cache ở nhiều vùng, việc cập nhật database có thể yêu cầu invalidate **tất cả** vùng đang chứa dữ liệu chịu ảnh hưởng, không chỉ vùng của người gọi. Một resolver trả đúng một cache là quyết định chính sách, không tự đảm bảo toàn hệ thống không còn dữ liệu cũ. Xác định rõ các luồng create/update/delete và kiểm tra mức độ stale chấp nhận được; với giao dịch, cân nhắc thời điểm evict sau commit.

**Thread safety và hiệu năng.** Không dùng biến instance kiểu `currentAudience` hoặc lưu trạng thái mỗi request trong singleton resolver. Dùng biến cục bộ và cache manager thread-safe; tránh gọi API mạng nặng mỗi lần resolve. Nếu cache tên không tồn tại, báo lỗi cấu hình thay vì âm thầm đổi sang cache của nhóm khác.

**Resolver khác key và TTL.** Resolver chỉ chọn `Cache`; nó không tự tạo TTL/eviction policy. TTL, kích thước, serialization, backend, stats và chính sách phân tán do provider (Caffeine, Redis, v.v.) cấu hình. Nếu provider tạo cache động theo tên, phải quản lý số lượng tên cache để tránh tăng vô hạn theo tenant.

**Proxy boundary.** `@EnableCaching` cần được bật, service phải là Spring-managed bean, và lời gọi phải đi qua proxy. `this.find(...)` từ một method cùng object thường bỏ qua intercept với proxy mode mặc định, khiến resolver không được gọi. Giải pháp là tách method sang bean khác hoặc thiết kế lại luồng gọi qua Spring proxy; không gọi trực tiếp `new CatalogService()` rồi kỳ vọng annotation hoạt động.

**Cấu hình nhiều bean.** Khi có nhiều `CacheManager` hoặc `CacheResolver`, cần xác định rõ bean mặc định/bean name; `@Cacheable(cacheResolver="...")` trỏ theo **tên bean** chính xác. Đừng đặt cả `cacheManager` và `cacheResolver` trên một operation.

## 7. Kiểm thử và xử lý lỗi

Kiểm tra theo *hành vi quan sát được*, thay vì chỉ xác nhận resolver trả tên mong muốn:

| Tình huống | Kỳ vọng |
| --- | --- |
| PUBLIC/42 gọi hai lần | Body `find` chạy một lần; lượt sau cache hit. |
| Sau PUBLIC/42, gọi VIP/42 | VIP đọc cache riêng, không dùng dữ liệu PUBLIC. |
| `refresh(PUBLIC,42)` | Giá trị PUBLIC được thay, VIP giữ nguyên. |
| `invalidate(VIP,42)` | VIP miss ở lượt tiếp; PUBLIC vẫn hit. |
| Cache name thiếu | Lỗi cấu hình rõ ràng, không fallback sang audience khác. |
| Gọi qua `this.find` | Nhận diện đó là trường hợp self-invocation không qua proxy. |
| Nhiều thread gọi đồng thời | Resolver không có mutable state theo request; test thêm hành vi provider khi cache miss đồng thời. |

Khi kết quả khác mong đợi, kiểm tra theo thứ tự: (1) annotation có chạy qua proxy không; (2) bean name resolver đúng không; (3) `context.getArgs()` có đúng thứ tự/giá trị không; (4) resolver trả cache nào; (5) biểu thức key có trùng giữa đọc/ghi/xóa không; (6) provider có TTL, eviction, serialization hay bất đồng bộ riêng không. `@Cacheable(sync = true)` có thể hạn chế tải trùng khi cache miss trên cùng key nếu provider hỗ trợ, nhưng không thay thế chính sách chọn cache hay tính nhất quán dữ liệu.

## 8. Ghi nhớ

- Cách đơn giản nhất đủ dùng là `cacheNames`; thêm `cacheManager` khi cần backend cố định cho từng method; dùng `cacheResolver` khi lựa chọn thật sự phụ thuộc vào lời gọi.
- `CacheResolver` quyết định **cache(s)**, còn `key`/`KeyGenerator` quyết định **entry**; cả hai phải nhất quán giữa `@Cacheable`, `@CachePut` và `@CacheEvict`.
- Resolver được gọi trong đường đi cache, phải thread-safe, trả về cache hợp lệ và không phụ thuộc vào kết quả method chưa có.
- Tách cache không thay thế kiểm tra quyền truy cập, TTL hay invalidation xuyên các phân vùng.

### Tài liệu chính thức

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html)
- [CacheResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheResolver.html)

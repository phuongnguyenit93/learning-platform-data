# Luồng xử lý khi cache có hoặc không có khóa trong @Cacheable

## Mục tiêu học tập

Hiểu chính xác chuỗi thao tác của Spring Cache khi một phương thức có `@Cacheable` được gọi: tạo khóa (cache key), kiểm tra một entry đã tồn tại hay chưa, phân biệt **cache hit** với **cache miss**, thời điểm chạy phương thức thật và ghi kết quả vào cache. Bài cũng giải thích trường hợp annotation không khai báo `key`, tác động của `condition`/`unless`, invalidation, và lưu ý về các lời gọi đồng thời.

## 1. “Có hoặc không có khóa” nghĩa là gì?

Trong ngữ cảnh `@Cacheable`, **khóa (key)** là định danh của một entry trong cache. Mỗi entry ánh xạ **key → kết quả đã lưu**. Ví dụ:

~~~text
Cache tên "products"
┌─────────────┬──────────────────────────┐
│ Key         │ Cached value             │
├─────────────┼──────────────────────────┤
│ "SKU-01"    │ "Bút bi - 12000 VND"     │
│ "SKU-02"    │ "Sổ tay - 25000 VND"     │
└─────────────┴──────────────────────────┘
~~~

Khi gọi `findProduct("SKU-01")`, Spring tạo key tương ứng rồi hỏi cache:

- **Đã có entry cho key đó (cache hit):** trả giá trị lưu sẵn; thân `findProduct` không chạy.
- **Chưa có entry cho key đó (cache miss):** chạy thân `findProduct`; nếu thành công và được phép cache thì lưu kết quả cho key, rồi trả về.

**Lưu ý về từ ngữ:** “khóa” ở đây là *cache key*, không phải *lock* đồng bộ thread. Cache vẫn có key ngay cả khi chưa có entry tương ứng; “không có khóa” trong lời nói thường được hiểu chính xác hơn là **“không có entry ứng với key đang tra cứu”**. Chủ đề lock khi nhiều thread cùng miss được giải thích ở mục 8.

Một cách hiểu khác cần phân biệt: **không khai báo thuộc tính `key` trong `@Cacheable`** không có nghĩa cache không dùng key. Spring vẫn tự sinh key mặc định từ tham số; xem mục 5.

## 2. Các thành phần tham gia vào luồng

| Thành phần | Vai trò trong cache hit/miss |
| --- | --- |
| `@Cacheable` | Khai báo vùng cache (`cacheNames`), cách tạo key và điều kiện |
| Spring AOP proxy và `CacheInterceptor` | Chặn lời gọi từ bên ngoài qua proxy, điều phối các bước tìm/lưu |
| `CacheManager` / `CacheResolver` | Xác định vùng cache được dùng |
| `KeyGenerator` hoặc biểu thức SpEL `key` | Tạo key cho lời gọi |
| `Cache` | Hợp đồng thao tác `get`/`put`/`evict`/`clear` |
| Provider như ConcurrentMap, Caffeine, Redis | Lưu và tra entry thực tế, áp dụng chính sách tồn tại/eviction |
| Phương thức nghiệp vụ | Chỉ chạy khi cần tính/nạp kết quả, chẳng hạn khi miss |

Ví dụ khai báo:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public String findProduct(String sku) {
    return repository.loadName(sku);
}
~~~

Đoạn trên chỉ minh họa; `repository` chưa được định nghĩa. `#p0` là tham số đầu tiên (`sku`). Thông tin `cacheNames = "products"` chọn vùng cache, còn key xác định **entry trong vùng đó**. Ghép hai yếu tố này để hiểu truy vấn logic:

~~~text
cacheName = "products"
key       = "SKU-01"
             |
             v
CacheManager -> Cache("products") -> get("SKU-01")
~~~

Tên cache và key có hai trách nhiệm khác nhau: cùng key `"SKU-01"` ở cache `products` và cache `stocks` không mặc nhiên trỏ tới cùng entry.

## 3. Toàn bộ luồng từ lời gọi đến kết quả

Với proxy caching thông thường, có thể mô tả:

~~~text
Caller gọi service.findProduct("SKU-01")
                   |
                   v
       Spring proxy / CacheInterceptor
                   |
                   v
       Đọc @Cacheable và resolve Cache
                   |
                   v
       Kiểm tra condition (nếu có)
                   |
             false | true
                   |   |
                   |   v
                   | Tạo cache key
                   |   |
                   |   v
                   | Cache.get(key)
                   |   |
                   |   +---- HIT ------------------+
                   |   |                           |
                   |   +---- MISS ----+            |
                   |                  |            |
                   v                  v            |
           Gọi phương thức      Gọi phương thức    |
               thật                 thật           |
                   |                  |            |
                   |                  v            |
                   |        Kiểm tra unless       |
                   |             sau khi chạy      |
                   |                  |            |
                   |          Cho phép lưu?        |
                   |           /          \        |
                   |        Có            Không    |
                   |         |                |    |
                   |         v                |    |
                   |     Cache.put(key, value)|    |
                   |         |                |    |
                   +---------+----------------+----+
                             |
                             v
                     Trả kết quả cho caller
~~~

Sơ đồ biểu diễn luồng nhận thức cho **một `@Cacheable` đồng bộ, một vùng cache và lời gọi thành công**. Trường hợp provider bất đồng bộ, trả kiểu reactive, có nhiều cache hoặc có quy tắc bổ sung có thể có chi tiết thực thi khác; không dùng sơ đồ này như mô tả từng dòng mã nguồn nội bộ.

### Bước 1 — lời gọi phải đi qua cơ chế caching

Annotation không tự thay đổi bytecode của mọi đối tượng Java. Với Spring proxy mode thông dụng, container tạo một proxy/advice cho bean được cache. Caller phải gọi qua bean proxy và tính năng caching phải được bật, ví dụ `@EnableCaching`. Gọi `new MyService()` ngoài container hoặc `this.findProduct(...)` từ trong chính object có thể bỏ qua proxy, khiến mọi lần đều chạy thân phương thức.

### Bước 2 — xác định vùng cache và điều kiện trước lời gọi

Spring lấy thông tin `cacheNames` hoặc cấu hình tương đương để tìm `Cache`. Nếu có `condition`, biểu thức được đánh giá dựa vào ngữ cảnh lời gọi **trước khi truy cập cache**:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()"
)
~~~

Nếu `sku` null hoặc trống, điều kiện không thỏa; Spring bỏ qua tìm/lưu cache cho operation này và gọi phương thức nghiệp vụ bình thường. Đây là **bypass**, không phải cache miss, vì thực tế không thực hiện tra entry cho operation ấy.

### Bước 3 — tính key và kiểm tra entry

Ví dụ `key = "#p0"` sinh key `"SKU-01"` khi tham số đầu là chuỗi ấy. Provider được hỏi xem entry với key đó có tồn tại hay không. Entry có thể thiếu vì chưa bao giờ được nạp, đã bị evict/clear, đã hết TTL hoặc không tồn tại ở đúng cache instance đang được tra.

Cần phân biệt “không tìm thấy entry” với “cache lưu một kết quả null”. Giao diện `Cache.get(key)` trả `ValueWrapper` khi tìm thấy entry, trong khi trả `null` khi không có mapping; `ValueWrapper.get()` có thể chứa null nếu implementation hỗ trợ cache giá trị null. Ở tầng annotation, cách lưu null/`Optional.empty()` còn tùy hỗ trợ của provider.

### Bước 4A — cache hit: trả kết quả lưu sẵn

Nếu entry có sẵn, interceptor lấy giá trị và trả về cho caller. **Thân phương thức không chạy**, do đó không gọi repository/API đắt tiền. Đây là điểm tiết kiệm tài nguyên chủ yếu.

~~~text
Lần gọi 1: findProduct("SKU-01")
Cache["SKU-01"] = "Bút bi" -> HIT -> return "Bút bi"
Không có query database mới.
~~~

Điều này đồng nghĩa mọi side effect trong body cũng bị bỏ qua. Không đặt `@Cacheable` lên phương thức phải thực hiện giao dịch, gửi email hoặc kiểm tra trạng thái bắt buộc ở **mọi** lần gọi.

### Bước 4B — cache miss: chạy phương thức, có thể ghi lại

Nếu chưa có entry, interceptor chuyển lời gọi đến phương thức thật. Khi phương thức trả kết quả thành công, Spring xét `unless` (nếu được khai báo). Nếu không bị loại trừ, kết quả được đặt vào cache theo key tương ứng và trả về caller.

~~~text
Lần gọi 1: findProduct("SKU-02")
Cache["SKU-02"] không có -> MISS
  -> repository.loadName("SKU-02")
  -> nhận "Sổ tay"
  -> Cache.put("SKU-02", "Sổ tay")
  -> return "Sổ tay"

Lần gọi 2: findProduct("SKU-02")
Cache["SKU-02"] đã có -> HIT -> return "Sổ tay"
Thân phương thức không chạy lần thứ hai.
~~~

Khi method ném exception, đó không phải một kết quả thành công để `@Cacheable` mặc định lưu lại. Nếu thao tác đọc/ghi cache phát sinh lỗi, ứng dụng có thể cần chính sách xử lý lỗi riêng (`CacheErrorHandler`) và xem khả năng của provider.

## 4. Bảng so sánh cache hit, miss và bypass

| Tình huống | Tra cache? | Chạy thân phương thức? | Ghi cache? |
| --- | --- | --- | --- |
| Entry đã có (**hit**) | Có | Không | Không cần |
| Entry chưa có (**miss**) và method thành công | Có | Có | Có, nếu không bị `unless` từ chối |
| `condition` trả false (**bypass**) | Không cho operation đó | Có | Không |
| Miss, kết quả thỏa `unless` | Có | Có | Không |
| Miss, phương thức ném exception | Có | Có | Không ghi kết quả thành công |
| Entry bị `@CacheEvict` xóa, gọi lại | Có | Có ở lần gọi sau nếu vẫn miss | Có thể ghi lại |

“Không có trong cache” không phải “không trả giá trị”: **cache miss vẫn trả kết quả của phương thức gốc** nếu nó thực thi thành công. Cache chỉ quyết định có tái sử dụng kết quả đã biết hay tính/nạp mới.

## 5. Không khai báo thuộc tính key: Spring vẫn sinh khóa

Hai trường hợp sau có thể đều dùng key từ tham số `sku`, dù cách viết khác nhau:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public String load(String sku) { /* ... */ return sku; }

@Cacheable(cacheNames = "products")
public String loadDefaultKey(String sku) { /* ... */ return sku; }
~~~

Đây là snippet minh họa các quy tắc annotation, không nên coi hai method cùng cache name và cùng key là ví dụ tách biệt an toàn trong một ứng dụng thật; chúng có thể vô tình **dùng chung entry**.

Khi không cung cấp biểu thức `key` hoặc custom `keyGenerator`, Spring dùng `SimpleKeyGenerator` mặc định:

| Danh sách tham số của lời gọi | Key mặc định |
| --- | --- |
| Không có tham số | `SimpleKey.EMPTY` |
| Một tham số khác null | Chính đối tượng tham số đó |
| Nhiều tham số, hoặc một tham số null | `SimpleKey` gói các giá trị tham số |

Ví dụ với `@Cacheable("products")`: `load("SKU-01")` thường dùng key `"SKU-01"`; với `loadByPair("SKU-01", "vi")`, key là tổ hợp hai tham số. Vì key dựa vào tham số, phải kiểm soát `equals()`/`hashCode()` của đối tượng dùng làm key và tránh dùng đối tượng mutable khiến key không còn ổn định.

Đặc biệt, key mặc định **không tự chứa tên phương thức**. Hai method khác nhau dùng cùng `cacheNames`, cùng tham số và cùng giá trị key có thể đụng entry dù kết quả có ngữ nghĩa khác nhau. Hãy dùng các cache name tách biệt hoặc tự thiết kế key có namespace thích hợp.

## 6. Ví dụ Spring Framework runnable — quan sát entry có/không có

Ví dụ Java 17 sử dụng Spring Framework 6.2.10, Maven và `ConcurrentMapCacheManager` (cache in-memory). Dùng `CacheManager.getCache("products").get(...)` để nhìn trực tiếp trạng thái entry; dùng bộ đếm để chứng minh body có chạy hay không.

Cấu trúc dự án:

~~~text
spring-cache-flow/
├── pom.xml
└── src/main/java/demo/CacheFlowDemo.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-flow</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `src/main/java/demo/CacheFlowDemo.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheFlowDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public String getProduct(String sku) {
            int call = loads.incrementAndGet();
            System.out.println("LOAD " + sku + " #" + call);
            return "value-" + sku;
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(String sku) {
            System.out.println("EVICT " + sku);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var service = context.getBean(ProductService.class);
            var cache = context.getBean(CacheManager.class)
                               .getCache("products");

            System.out.println("Before A: " + (cache.get("A") != null));
            System.out.println("1: " + service.getProduct("A"));
            System.out.println("After A: " + (cache.get("A") != null));
            System.out.println("2: " + service.getProduct("A"));
            System.out.println("3: " + service.getProduct("B"));

            service.evict("A");
            System.out.println("A after evict: "
                               + (cache.get("A") != null));
            System.out.println("4: " + service.getProduct("A"));
        }
    }
}
~~~

Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheFlowDemo
~~~

Stdout do chương trình in ra (Maven có thể in thông báo riêng tùy môi trường):

~~~text
Before A: false
LOAD A #1
1: value-A
After A: true
2: value-A
LOAD B #2
3: value-B
EVICT A
A after evict: false
LOAD A #3
4: value-A
~~~

Phân tích từng dấu vết:

| Dòng | Trạng thái | Cơ chế |
| --- | --- | --- |
| `Before A: false` | Cache chưa có `A` | `Cache.get("A")` chưa có entry |
| `LOAD A #1` và `1: value-A` | Miss đầu tiên | Spring chạy method, sau đó lưu kết quả |
| `After A: true` | Đã có entry | Cache thực sự giữ key `A` |
| `2: value-A`, không có `LOAD A #2` | Hit | Method body bị bỏ qua |
| `LOAD B #2` | Key khác nên miss | `B` độc lập với `A` |
| `EVICT A`, `A after evict: false` | Xóa entry `A` | `@CacheEvict` xóa sau khi method thành công |
| `LOAD A #3` | Miss lại sau khi evict | Spring nạp lại và cache lần nữa |

Để suy luận đúng kết quả, cần để ý thứ tự các lần gọi. Sau hit lần hai, bộ đếm `loads` vẫn bằng 1; khi gọi key `B`, bộ đếm thành 2; xóa `A` không tăng bộ đếm; nạp lại `A` mới thành 3.

Trong demo này, việc thay đổi nội dung ở cache là do Spring interceptor phối hợp với `ConcurrentMapCache`. `@Cacheable` không tự tạo database và cũng không lưu dữ liệu mãi mãi; manager chọn nơi giữ dữ liệu.

### Tại sao ví dụ gọi qua ApplicationContext?

Lời gọi `context.getBean(ProductService.class)` đi qua Spring-managed bean, có proxy/interceptor xử lý annotation. Nếu thay bằng `new ProductService()` và gọi trực tiếp, annotation có thể không có tác dụng: mọi lần đều chạy `getProduct`, dù cú pháp annotation vẫn tồn tại trong mã. Với proxy mode, cả lời gọi nội bộ `this.getProduct("A")` cũng không đi qua proxy, nên cần tránh khi trông chờ cache.

## 7. Điều kiện khiến miss không ghi lại kết quả

### `condition`: quyết định có đi vào cơ chế cache không

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()"
)
public String find(String sku) {
    return repository.loadName(sku);
}
~~~

Snippet giả định có `repository`. Với `sku = ""`, condition false: không tra hay ghi cache. Với `sku = "A"`, condition true: tiếp tục lookup key `A` và sau đó hit/miss theo dữ liệu đang có.

### `unless`: chỉ xét sau khi method đã chạy

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    unless = "#result == null || #result.isBlank()"
)
public String find(String sku) {
    return repository.loadName(sku);
}
~~~

Nếu miss và method trả chuỗi rỗng, `unless` true nên **không ghi entry**. Vì vậy lần gọi sau với cùng key vẫn có thể miss và chạy method tiếp. Nếu method trả chuỗi hợp lệ, kết quả có thể được lưu.

Một lần **hit** thì method đã bị bỏ qua; `unless` không phải cách ép method chạy để kiểm tra dữ liệu mới nhất. Nếu cần đảm bảo dữ liệu thay đổi được nhìn thấy, hãy có chiến lược invalidation/TTL.

Đừng nhầm **miss** với “bị `unless` loại trừ”: miss nói về **trạng thái entry trước khi chạy**, còn unless quyết định **có lưu kết quả mới hay không**.

## 8. Nếu nhiều thread cùng tra một key chưa có thì sao?

Dù chủ đề chính là *cache key*, từ “khóa” cũng có nghĩa **lock** trong concurrency. Hai khái niệm khác nhau:

- **Cache key:** định danh kết quả, ví dụ `"SKU-01"`; có thể tồn tại dù không có lock.
- **Lock/synchronization:** phối hợp nhiều thread để không cùng tính toán dữ liệu đắt tiền cho một key trong cùng thời điểm.

Giả sử thread T1 và T2 đều gọi `getProduct("A")` khi cache còn rỗng:

~~~text
T1: Cache.get("A") -> MISS -> bắt đầu load A ----- put("A")
T2: Cache.get("A") -> MISS -> bắt đầu load A ----- put("A")
~~~

Với `@Cacheable` mặc định, hai lần load có thể cùng xảy ra. Hệ quả gọi là **cache stampede** (nhiều request cùng đổ vào nguồn chậm). Cache key bằng nhau **không tự tạo lock** bảo vệ việc tải dữ liệu.

Spring hỗ trợ:

~~~java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public String getProduct(String sku) {
    return repository.loadName(sku);
}
~~~

`sync = true` đề nghị provider đồng bộ việc nạp giá trị cho key tương ứng. Đây là capability **phụ thuộc implementation**; không phải cam kết về distributed lock giữa các JVM. Spring giới hạn kiểu dùng đồng bộ: chỉ một cache, không hỗ trợ `unless`, và không kết hợp operation cache khác trên cùng method. Cần kiểm thử provider đã chọn và đường tải dữ liệu thực tế khi có concurrency.

Một số tình huống thường gặp:

| Trạng thái | `sync = false` (mặc định) | `sync = true` |
| --- | --- | --- |
| Key đã có entry | Trả từ cache | Trả từ cache |
| Key chưa có, chỉ một caller | Gọi method, có thể lưu | Gọi method, có thể lưu |
| Nhiều caller cùng miss | Có thể cùng gọi method | Provider được yêu cầu phối hợp tải theo key |
| Nhiều instance độc lập | Tùy backend | Không mặc nhiên thành global lock |

Không nên chọn `sync = true` chỉ để “cache có khóa”. Đặt bài toán đúng: nếu kết quả tính được lặp lại nhanh, tải trùng có thể chấp nhận; nếu nạp rất tốn kém, đánh giá hỗ trợ của provider, latency, timeout và hành vi khi một request tải lỗi.

## 9. Invalidation: từ hit quay lại miss

Cache hit không đảm bảo dữ liệu luôn mới. Nếu database đổi sản phẩm nhưng entry `A` chưa bị xóa, lookup vẫn có thể hit và trả bản cũ. Một chiến lược thông dụng là **ghi dữ liệu gốc rồi xóa entry liên quan**:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product read(String sku) {
    return repository.findBySku(sku);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void update(String sku, Product newValue) {
    repository.save(sku, newValue);
}
~~~

Đây là snippet minh họa, không phải chương trình độc lập; cần định nghĩa `Product`, `repository` và cấu hình transaction. Theo mặc định, `@CacheEvict` xóa entry sau khi phương thức được gọi thành công. `beforeInvocation = true` có thể xóa trước lời gọi, nhưng phải hiểu hậu quả nếu cập nhật dữ liệu gốc thất bại.

Với transaction database, **lệnh cache evict và thời điểm commit có thể khác nhau**. Nếu xóa cache trước khi transaction commit, một reader khác có thể miss rồi nạp lại dữ liệu cũ. Ứng dụng phải cân nhắc chính sách sau commit/transaction-aware cache và yêu cầu consistency. Việc có `@Cacheable` không biến cache và database thành một transaction nguyên tử.

Tính mới của entry còn phụ thuộc TTL/eviction provider. Spring Cache abstraction không đưa ra TTL mặc định chung cho mọi backend; Caffeine/Redis có cơ chế lưu trữ và chính sách riêng. Khi entry hết hạn, lần gọi sau vẫn xử lý theo **miss** và có thể nạp lại.

## 10. Lỗi phổ biến khi giải thích hoặc debug luồng

**Lỗi 1: “Không ghi `key` thì Spring không có khóa”.** Sai; mặc định Spring sinh key từ tham số qua `SimpleKeyGenerator`. Muốn kiểm tra chính xác phải xác định phương thức nhận những tham số nào và cache name nào.

**Lỗi 2: “Cache miss trả về null”.** Sai; miss thường làm phương thức gốc chạy rồi trả kết quả của nó. Null có thể là **kết quả nghiệp vụ** được trả về, nhưng không phải là định nghĩa của miss.

**Lỗi 3: “Hit vẫn chạy phần thân để kiểm tra DB mới nhất”.** Sai; cache hit trả dữ liệu cũ đã lưu, trừ khi có cơ chế invalidation/expiry hoặc bypass phù hợp. Điều kiện freshness thuộc thiết kế nghiệp vụ.

**Lỗi 4: “Thêm `@Cacheable` là mọi lần gọi đều được intercept”.** Sai với lời gọi qua object tự tạo, self-invocation theo proxy mode, hoặc chưa bật caching. Phải xác minh đường gọi thông qua bean/proxy.

**Lỗi 5: “Hai request cùng key thì luôn chỉ một request tải”.** Sai ở mặc định. `sync = true` và provider thích hợp có thể hạn chế tính toán trùng; không phải cơ chế khóa phân tán phổ quát.

**Lỗi 6: “Dùng cùng key cho nhiều method luôn an toàn”.** Sai; key không chứa tên method theo mặc định. Nên tách cache name hoặc namespace/key strategy cho các giá trị khác loại.

### Checklist debug theo thứ tự

1. Kiểm tra ứng dụng đã bật caching và lời gọi có đi qua Spring bean proxy không.
2. Đọc chính xác `cacheNames`; tránh nhầm cache name với entry key.
3. Tính key từ lời gọi thực tế: `key`/`keyGenerator` hay `SimpleKeyGenerator` mặc định.
4. Kiểm tra `condition`: có bypass operation ngay từ đầu không?
5. Quan sát tồn tại entry tại **đúng provider/instance** đang phục vụ request.
6. Nếu miss, xem method trả gì, có ném exception không, `unless` có chặn ghi không.
7. Nếu sau đó vẫn miss, kiểm tra `@CacheEvict`, TTL, eviction, cache manager, các instance và cả quy tắc serialization/key mapping của backend.
8. Nếu có nhiều request cùng miss, kiểm tra concurrency và mức hỗ trợ `sync = true` của provider.

## 11. Bài tập tự kiểm tra

**Bài 1.** Cache rỗng. Gọi lần lượt `load("A")`, `load("A")`, `load("B")`, `load("A")` với `@Cacheable(cacheNames="items", key="#p0")`, các lời gọi đi qua proxy và không có eviction/expiry. Method gốc chạy bao nhiêu lần? **Hai lần:** miss đầu tiên cho A và miss đầu tiên cho B; hai lần A còn lại hit.

**Bài 2.** Phương thức có `@Cacheable(cacheNames="items", unless="#result == null")`, lần đầu trả null. Gọi lại cùng key có mặc nhiên hit không? **Không:** trừ khi entry được ghi từ nơi khác, kết quả null đã bị `unless` ngăn lưu nên lần sau tiếp tục miss.

**Bài 3.** `@Cacheable(cacheNames="items")` không khai báo `key`, nhận duy nhất tham số chuỗi `"A"`. Có lookup không? **Có.** Spring tự dùng key mặc định `"A"`, nên vẫn thực hiện hit/miss như bình thường.

**Bài 4.** Sau khi gọi `evict("A")`, lần tiếp theo `load("A")` xử lý thế nào? **Miss** nếu entry thật sự đã bị xóa khỏi đúng vùng cache và chưa có request khác nạp lại; method gốc chạy rồi có thể ghi entry mới.

**Bài 5.** Hai thread cùng miss key A, có chắc chỉ một thread vào method không? **Không** với mặc định. Muốn điều phối, nghiên cứu `sync = true` và năng lực cụ thể của provider.

## Kết luận

Với `@Cacheable`, hãy theo dõi **cache name → key → trạng thái entry → hành động**. Nếu entry đã có, Spring có thể trả giá trị ngay mà không chạy method. Nếu chưa có, method gốc chạy và kết quả có thể được ghi để lần sau hit. Không khai báo `key` thì vẫn có key mặc định; key dùng nhận diện entry, còn lock là câu chuyện điều phối truy cập đồng thời. Hiểu đúng chuỗi này giúp debug cache miss bất ngờ, dữ liệu stale và những lần tính toán trùng.

## Tài liệu chính thức

- Spring Framework Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Default Key Generation: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html#cache-annotations-cacheable-default-key
- Synchronized Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html#cache-annotations-cacheable-synchronized
- Spring Cache API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html

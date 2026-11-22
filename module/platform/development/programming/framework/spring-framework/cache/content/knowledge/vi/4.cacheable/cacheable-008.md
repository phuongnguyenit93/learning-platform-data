# Giới hạn dùng nhiều `cacheNames` như một hệ cache nhiều tầng trong `@Cacheable`

## 1. Kết luận kiến trúc cần nhớ

Trong Spring Framework, khai báo:

```java
@Cacheable(cacheNames = {"productsL1", "productsL2"}, key = "#p0")
public Product findProduct(String productId) {
    return repository.findById(productId);
}
```

có nghĩa là **một thao tác cache được liên kết với nhiều cache có tên khác nhau**. Với đường truy cập đồng bộ thông thường, Spring tìm kết quả theo thứ tự cache được giải quyết, trả về khi gặp hit và lưu kết quả mới vào các cache liên quan khi cần nạp từ phương thức. Cách khai báo này **không phải hợp đồng đầy đủ của cache nhiều tầng (L1/L2, near-cache/remote-cache)**.

Một hệ L1/L2 đúng nghĩa cần xác định: miss ở L1 thì chuyển sang L2; hit L2 có đưa kết quả trở lại L1 không, khi nào; cache nào được cập nhật trước; TTL/giới hạn dung lượng từng tầng; cách xóa đồng bộ khi dữ liệu nguồn thay đổi; tính nhất quán giữa các node; và điều gì xảy ra khi cache tầng dưới bị lỗi. `cacheNames` tự nó không mô tả hay bảo đảm đầy đủ các chính sách đó.

Trong bài này, “L1” chỉ lớp lưu gần, thường là local/in-process; “L2” chỉ lớp lưu xa/chung, thường là Redis. Đặt tên cache là `productsL1` và `productsL2` không tự biến chúng thành hai tầng có cơ chế phối hợp.

## 2. Hợp đồng thật sự của `@Cacheable` với nhiều tên

Tên trong `cacheNames` là **tên logic của các `Cache`**, không phải danh sách bean `CacheManager` hoặc cấu hình độ ưu tiên của backend. `CacheResolver` xác định các đối tượng `Cache`; cách mặc định thường thông qua một `CacheManager`. Spring dùng key của cùng lời gọi cho các cache được chọn.

```text
@Cacheable(cacheNames={"productsL1","productsL2"}, key="#p0")
                       │
                 CacheInterceptor
                       │
                 CacheResolver
                       │
             [Cache "productsL1",
              Cache "productsL2"]
                       │
            Tra cứu theo thứ tự
                       │
             Hit? trả cached value
             Không hit? gọi method
                       │
            Nạp kết quả vào cache liên quan
```

Với **truy cập đồng bộ bình thường**, xét các trạng thái:

| Trạng thái trước lần đọc | Kết quả | Điều đáng chú ý |
| --- | --- | --- |
| Cả hai cache miss | Chạy phương thức gốc, lấy kết quả và thực hiện put vào các cache chỉ định | Đây là nạp nhiều cache từ một kết quả, không chứng minh có kiến trúc L1/L2 |
| Cache đầu hit | Trả ngay giá trị cache đầu, không chạy phương thức | Không kiểm chứng bản sao phía sau mới hơn hoặc còn hợp lệ |
| Cache đầu miss, cache sau hit | Trả kết quả cache sau, không gọi nguồn | Tài liệu Spring mô tả việc cập nhật các cache khác đang thiếu kết quả; không nên lấy mô tả này thay cho hợp đồng promote/nhất quán riêng của hệ đa tầng |
| Hai cache chứa hai giá trị khác nhau cho cùng key | Giá trị ở cache được hit trước thắng theo thứ tự tra cứu | Không có so sánh version hay cơ chế chọn bản mới nhất |
| Cache trước ném lỗi truy cập | Lỗi được xử lý theo `CacheErrorHandler`/provider | Không tự có chính sách “L1 lỗi thì fallback L2” có bảo đảm |
| Giá trị bị evict hoặc hết hạn trong một cache | Cache kia không nhất thiết thay đổi | TTL/eviction mỗi cache là chính sách backend, không phải quan hệ phụ thuộc tự động |

Theo tài liệu Spring, các cache còn thiếu giá trị có thể được bổ sung trong luồng xử lý cache đồng bộ; **không suy ra mọi tình huống đọc bất đồng bộ, lỗi, cạnh tranh hay đa node đều bảo đảm việc đồng bộ hai tầng**. Cache entry bị hết hạn riêng rẽ, và các cache không chia sẻ một nguồn sự thật duy nhất chỉ nhờ đứng chung trong mảng `cacheNames`.

Từ góc nhìn API, `@Cacheable({"a","b"})` phù hợp hơn để mô tả **nhiều vùng dùng chung kết quả** so với việc khẳng định “A là L1, B là L2”. Thứ tự là thứ tự **tìm kết quả**, chưa phải chính sách thời gian thực đầy đủ.

## 3. Những điều `cacheNames` không cung cấp

### 3.1. Không tự chọn hai backend khác nhau

```java
@Cacheable(cacheNames = {"localProducts", "redisProducts"}, key = "#p0")
public Product findProduct(String id) {
    return repository.findById(id);
}
```

Đoạn trên chỉ khai báo **hai tên cache**. Nó không tự tạo Caffeine cho tên đầu và Redis cho tên sau. Cả hai phải được `CacheResolver` giải quyết thành `Cache` hợp lệ từ cấu hình đã có. Với một manager chỉ biết một tên, tên còn lại có thể không giải quyết được, làm thao tác lỗi; với manager tự tạo mọi region, cả hai có thể nằm trên cùng một backend.

Nếu cấu hình hai `CacheManager` riêng, `@Cacheable(cacheManager="...")` thường chọn **một manager cho thao tác**. `CacheResolver` tùy biến có thể trả nhiều đối tượng `Cache` từ những manager khác nhau, nhưng vẫn chưa triển khai logic ưu tiên, promotion, coherence và thất bại của cả hệ nhiều tầng.

### 3.2. Không có hợp đồng “L2 hit thì luôn promote vào L1”

Một cache L1/L2 thường được kỳ vọng:

```text
read(key)
  ├─ L1 hit  → trả
  └─ L1 miss
       ├─ L2 hit  → đưa dữ liệu vào L1 → trả
       └─ L2 miss → đọc nguồn → ghi L2 → ghi L1 → trả
```

Đó là **thuật toán cache phân tầng**. Trong khi đó, `@Cacheable` được định nghĩa là caching một lời gọi method qua danh sách `Cache`. Mặc dù tài liệu Spring có mô tả bổ sung các cache còn thiếu giá trị trong tình huống thông thường, annotation không cung cấp API để đặt chính sách promotion riêng, chọn phiên bản theo thời gian, điều khiển write-through/write-behind cho từng tầng, hoặc bảo đảm sự kiện promotion thành công nếu một backend lỗi. Không dựa vào hành vi quan sát được của một provider để cam kết các hành vi đó trên mọi provider.

### 3.3. Không tự quản lý tính nhất quán khi hai tầng có TTL khác nhau

Giả sử:

- L1 in-memory giữ bản ghi 20 giây.
- L2 Redis giữ bản ghi 5 phút.
- Database đã sửa sản phẩm thành phiên bản mới.

Nếu L1 bị xóa còn L2 vẫn giữ dữ liệu cũ, hệ thống có thể đọc lại L2 rồi điền **dữ liệu cũ** vào L1. Tăng hit rate không đồng nghĩa với đọc đúng. Ngược lại, khi L1 có dữ liệu cũ mà L2 đã mới, cache hit đầu có thể che khuất bản mới phía sau.

TTL là chính sách của từng cache provider (`Caffeine`, `RedisCacheManager`...), Spring Cache abstraction không có một TTL chung áp dụng bởi mảng `cacheNames`. TTL chỉ giới hạn vòng đời; invalidation, version và độ mới theo nghiệp vụ phải được quản lý riêng.

### 3.4. Không tự truyền invalidation giữa mọi node

`@CacheEvict(cacheNames={"productsL1","productsL2"}, key="#p0")` yêu cầu evict hai region được resolve trong **lời gọi ấy**. Nếu L1 là bộ nhớ trong từng JVM, evict từ node A không trực tiếp xóa bản sao L1 của node B. Một L2 phân tán chung cũng không mặc nhiên phát thông báo làm mới tất cả L1 local.

Một hệ phân tán cần chính sách rõ: sự kiện sau commit, pub/sub hay message bus để báo invalidation; version hoặc timestamp chống cập nhật ngược; fallback TTL nếu sự kiện bị mất; và test trên nhiều instance.

### 3.5. Không có giao dịch nguyên tử xuyên các cache và database

Khi ghi vào nhiều cache, các thao tác không đồng nghĩa với một commit nguyên tử. Nếu ghi L1 thành công, ghi L2 thất bại hoặc database rollback, dữ liệu hai nơi có thể lệch nhau. Transaction-aware cache giúp trì hoãn một số thay đổi đến sau commit của transaction Spring tương ứng, nhưng không biến database + Redis + local cache thành một hệ 2-phase commit tự động.

### 3.6. Không tự giải quyết stampede và cache failure

Nhiều request đồng thời miss có thể cùng gọi nguồn. Trong `@Cacheable`, chế độ `sync=true` yêu cầu **chỉ một cache**, vì vậy cách khai báo sau không hợp lệ:

```java
// SAI: sync=true chỉ chấp nhận một cache.
@Cacheable(cacheNames = {"productsL1", "productsL2"}, sync = true)
public Product findProduct(String id) {
    return repository.findById(id);
}
```

Ngay cả khi chỉ còn một cache, `sync=true` là gợi ý cho provider, không thay thế distributed lock khi cần bảo đảm toàn hệ thống. Các chính sách chống stampede, giới hạn lượng nạp và bỏ qua cache lỗi cần được thiết kế/test theo backend.

## 4. Ví dụ chạy được: hai cache name vẫn có thể trả dữ liệu cũ

Ví dụ này dùng Spring Framework **6.2.16**, Java 17+ và `ConcurrentMapCacheManager` chỉ để chứng minh **ngữ nghĩa tra cứu nhiều tên trong cùng một tiến trình**. Cả hai region là bộ nhớ local; tên `l1Products`/`l2Products` không chứng minh hai backend hay hệ cache phân tầng.

Tạo file `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>multi-cache-names-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/MultiCacheNamesDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class MultiCacheNamesDemo {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("l1Products", "l2Products");
    }

    @Bean
    ProductLookup productLookup() {
        return new ProductLookup();
    }

    public static class ProductLookup {
        private final AtomicInteger sourceCalls = new AtomicInteger();

        @Cacheable(cacheNames = {"l1Products", "l2Products"}, key = "#p0")
        public String find(String sku) {
            int count = sourceCalls.incrementAndGet();
            return "db-" + sku + "-call" + count;
        }

        public int sourceCalls() {
            return sourceCalls.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(MultiCacheNamesDemo.class)) {
            var service = context.getBean(ProductLookup.class);
            var manager = context.getBean(CacheManager.class);

            Cache l1 = Objects.requireNonNull(manager.getCache("l1Products"));
            Cache l2 = Objects.requireNonNull(manager.getCache("l2Products"));
            String key = "P1";

            // Cả hai miss: gọi nguồn một lần, ghi vào cả hai cache.
            System.out.println("Read 1: " + service.find(key));
            System.out.println("Stored L1: " + (l1.get(key) != null));
            System.out.println("Stored L2: " + (l2.get(key) != null));

            // L1 miss, L2 còn hit: không cần gọi lại nguồn.
            l1.evict(key);
            System.out.println("Read 2: " + service.find(key));
            System.out.println("Source calls: " + service.sourceCalls());

            // Hai bản sao mâu thuẫn nhau: tên đứng trước quyết định hit.
            l1.put(key, "STALE-L1");
            l2.put(key, "FRESH-L2");
            System.out.println("Read 3: " + service.find(key));
            System.out.println("Source calls: " + service.sourceCalls());
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`, máy đã cài Maven và JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=MultiCacheNamesDemo
```

Các dòng do chương trình in ra (không tính log riêng của Maven):

```text
Read 1: db-P1-call1
Stored L1: true
Stored L2: true
Read 2: db-P1-call1
Source calls: 1
Read 3: STALE-L1
Source calls: 1
```

Tại `Read 1`, cả hai region được điền với cùng value. Sau khi xóa riêng L1, `Read 2` vẫn lấy được bản từ cache còn lại mà không gọi nguồn thêm. Cuối cùng, ta cố tình đặt `STALE-L1` và `FRESH-L2` cho cùng một key; `Read 3` trả bản cũ vì cache đứng trước đã hit. Spring không so sánh freshness, version hay timestamp giữa các cache được chỉ định.

Chương trình chứng minh **cùng một key có thể đồng thời tồn tại hai phiên bản khác nhau**, từ đó cần ràng buộc nhất quán riêng. Nó không đo latency hay khẳng định một implementation cụ thể sẽ luôn promote L2 → L1 dưới mọi điều kiện.

## 5. Hai giới hạn API thường bị nhầm lẫn

### 5.1. `CompositeCacheManager` không phải cache hai tầng theo key

`CompositeCacheManager` nhận nhiều `CacheManager` rồi tìm manager **có thể cung cấp region theo tên**. Đó là fallback khi **resolve một tên cache**, không phải pipeline “cache L1 miss key thì qua cache L2 cùng key”.

```java
// Chỉ minh họa cấu hình, không phải chương trình độc lập.
@Bean
CacheManager cacheManager(
        CacheManager caffeineManager,
        CacheManager redisManager) {
    return new CompositeCacheManager(caffeineManager, redisManager);
}
```

Nếu manager đầu tiên trả một `Cache` cho tên `products`, quá trình resolve có thể dừng ở đó; lời gọi `get(key)` miss sau này **không khiến CompositeCacheManager tự tìm key trong manager thứ hai**. Các delegate phải trả `null` khi không nhận diện tên region để quá trình resolve được chuyển tiếp. Một provider tự động tạo region theo mọi tên có thể làm lu mờ manager tiếp theo.

### 5.2. Truy cập bất đồng bộ và reactive có thể không đi qua tất cả cache

Từ Spring Framework 6.1, `@Cacheable` hỗ trợ kết quả như `CompletableFuture` và các kiểu reactive được hỗ trợ. Tuy nhiên, tài liệu `Cacheable.cacheNames` cảnh báo rằng với cache có **miss được xác định muộn** (ví dụ kiểu truy cập bất đồng bộ tới Redis), Spring có thể **không tiếp tục tra các cache name phía sau**. Trái lại, cache có thể xác định miss sớm (ví dụ Caffeine trong chế độ phù hợp) thuận lợi hơn cho truy cập nhiều tên.

Vì vậy ví dụ Java đồng bộ ở trên **không phải bằng chứng** rằng thứ tự fallback hoạt động y hệt với `Mono`, `Flux`, `CompletableFuture` hoặc `Cache.retrieve(...)` trên mọi backend. Khi cần hợp đồng L1/L2 bất đồng bộ, phải test đúng provider, phiên bản Spring và cấu hình vận hành.

## 6. Muốn L1/L2 thực sự thì nên tổ chức thế nào?

Một phương án rõ ràng là cung cấp **một đối tượng `Cache` logic** tên `products`, bên trong là implementation phối hợp hai backend theo hợp đồng riêng. Bên ngoài service chỉ còn:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product findProduct(String id) {
    return repository.findById(id);
}
```

Bên trong implementation tầng cache sẽ quyết định cách đọc, ghi, xóa, version và xử lý lỗi:

```text
Cache "products" (một cache logic, implementation phối hợp hai tầng)
    get(key):
        nếu L1 hit hợp lệ           → trả
        nếu L1 miss, L2 hit hợp lệ   → promote vào L1 → trả
        nếu cả hai miss              → báo miss
    put(key, value):
        ghi theo chính sách được chọn, xác nhận/giám sát từng tầng
    evict(key):
        làm mất hiệu lực ở cả hai tầng, gửi tín hiệu cho L1 các node khác
    clear():
        vô hiệu hóa toàn bộ khóa thuộc region theo đúng phạm vi
```

`@Cacheable` vẫn chịu trách nhiệm gọi method gốc khi cache logic báo miss; implementation cache phối hợp L1/L2. Đây là **thuật toán mục tiêu**, chưa phải mã Java độc lập và phải được hoàn thiện theo hợp đồng `org.springframework.cache.Cache`. Nếu thay bằng orchestration ở tầng service, hãy tách rõ logic đọc, write/invalidate và quan sát.

Ví dụ **minh họa riêng cho đoạn get** trong một implementation, nơi `nearCache` và `remoteCache` là hai đối tượng `Cache` đã được cấu hình:

```java
// Đoạn minh họa trong custom cache; không phải file chạy độc lập.
public Object readThroughLayers(Object key) {
    Cache.ValueWrapper near = nearCache.get(key);
    if (near != null) {
        return near.get();
    }

    Cache.ValueWrapper remote = remoteCache.get(key);
    if (remote != null) {
        Object value = remote.get();
        nearCache.put(key, value); // Promotion có chủ đích.
        return value;
    }
    return null; // Ví dụ này bỏ qua phân biệt cached-null và miss.
}
```

Đoạn đơn giản trên **chưa đủ để triển khai production**: phải có cách phân biệt cached-null với cache miss, quyết định cách serialize/value type, TTL, timeout, thao tác concurrent, cache lỗi, version, chiến lược tránh stampede và làm mới bản cũ. Với implement `Cache.get(key)` thực tế, đừng làm mất thông tin hit-null bằng cách chỉ trả `Object` như ví dụ.

Một chiến lược cụ thể:

1. **Đọc:** L1 hit phải kiểm tra giá trị còn hợp lệ/version; nếu miss thì đọc L2; nếu L2 hit thì promote L1 theo TTL L1 và đúng version; cả hai miss thì nạp nguồn và ghi theo thứ tự đã chọn.
2. **Ghi dữ liệu nguồn:** lưu vào database, chỉ công bố/invalidate cache theo cơ chế sau commit phù hợp; không gọi một chuỗi put như một giao dịch phân tán nguyên tử.
3. **Invalidate:** evict L2 và yêu cầu các L1 local xóa key tương ứng; xét sự kiện bị mất, gửi trùng hoặc tới lệch thứ tự. TTL và version là cơ chế bổ trợ.
4. **Bảo vệ dữ liệu:** nếu key chứa tenant/user/locale, mọi tầng dùng cùng cấu trúc key và authorization phù hợp; không để cached value của đối tượng mutable bị sửa ngoài ý muốn.
5. **Resilience:** xác định chính sách khi L1 lỗi, L2 timeout, cache put thất bại, hoặc loader lỗi; có metrics và test phân tán.

## 7. Khi nào dùng nhiều `cacheNames`, khi nào cần cache phân tầng?

| Nhu cầu | Lựa chọn | Vì sao |
| --- | --- | --- |
| Một kết quả có thể cần hiện diện trong nhiều region logic | `@Cacheable(cacheNames={"a","b"})` nếu thật sự cần và đã kiểm thử | Khai báo nhiều cache cho một lời gọi, cùng key và value |
| Cần một cache local và một cache remote với read-through/promotion chắc chắn | Custom composite `Cache` hoặc layer orchestration tường minh | Chủ động mô tả thứ tự, fallback, promotion và lỗi |
| Chọn backend khác nhau cho các **loại** cache | `CacheManager`/`CacheResolver` được cấu hình theo tên và nghiệp vụ | Phân luồng cache, không nhất thiết là nhiều tầng cho cùng key |
| Cache một kết quả nhưng muốn tránh nhiều loader chạy đồng thời | `@Cacheable(sync=true)` với **một** cache hỗ trợ | Cơ chế sync có giới hạn số cache và phụ thuộc provider |
| Nhiều instance có L1 riêng, chung Redis làm L2 | Composite cache + invalidation đa node, hoặc bỏ L1 nếu không cần | `@CacheEvict` trên một node không tự xóa mọi L1 ở các node khác |
| Truy cập async/reactive với Redis ở một vị trí trong chuỗi | Kiểm chứng khả năng miss sớm/muộn; thường dùng custom adapter | Không giả định mảng `cacheNames` luôn duyệt hết mọi tầng |

**Đừng chọn nhiều `cacheNames` chỉ vì muốn “gắn thêm Redis để nhanh hơn”.** Thêm một cache cũng thêm lựa chọn dữ liệu stale, chi phí ghi, rủi ro lỗi và cách xử lý invalidation. Chọn kiến trúc theo mục tiêu nhất quán/độ trễ đã định lượng.

## 8. Checklist và các bài test bắt buộc nếu cân nhắc cache hai tầng

Trước khi đưa vào production, viết ra hợp đồng của từng tầng: kiểu key/value, provider, thời gian sống, phạm vi local/shared, quy tắc cache null, thời điểm refresh, giới hạn bộ nhớ, cách khôi phục sau restart, xử lý lỗi và chủ sở hữu invalidation. Sau đó kiểm thử tối thiểu các trường hợp:

| Kịch bản | Kết quả cần quan sát |
| --- | --- |
| L1 miss, L2 miss | Đọc nguồn một lần theo chính sách loader; ghi tới tầng được cấu hình |
| L1 miss, L2 hit | Trả value đúng và promotion L1 theo hợp đồng **đã thiết kế** |
| L1 hit cũ, L2 hit mới | Có quy tắc version/invalidation rõ; không âm thầm trả bản cũ nếu nghiệp vụ yêu cầu mạnh |
| Source update/delete | Các tầng và các node khác không tiếp tục trả bản cũ vượt ngưỡng được cho phép |
| Miss đồng thời | Kiểm soát số lượt load, race giữa read và evict, không hồi sinh giá trị stale |
| L2 timeout hoặc unavailable | Hành vi được định nghĩa: fallback DB, fail closed, bỏ qua cache hay trả stale có kiểm soát |
| L1 restart hoặc instance mới | Cold start hoạt động; không giả định L1 được pre-warm |
| TTL L1 và L2 chênh lệch | Không kéo dài tuổi thọ dữ liệu cũ ngoài hợp đồng |
| Async/reactive | Xác minh thật đường đi cache trên từng backend, nhất là miss xác định muộn |
| Transaction rollback | Không publish giá trị mới khi thay đổi nguồn không commit |
| Cache null/empty và serialization | Không nhầm hit-null với miss; dữ liệu tương thích giữa các tầng |

Đo hit/miss theo tầng, số lần loader chạy, p95/p99 latency, tỷ lệ promotion, lỗi provider, số eviction và thời gian stale thực tế. Một cache “trông như” nhiều tầng vì hit rate cao nhưng trả giá trị cũ là sai hợp đồng nghiệp vụ.

## 9. Những nhầm lẫn phải tránh

- **“Nhiều tên nghĩa là nhiều tầng.”** Tên được resolve thành cache; chưa có quản lý L1/L2.
- **“Đặt Caffeine trước Redis sẽ có near-cache chuẩn.”** Thứ tự lookup không bảo đảm coherency, invalidation phân tán hoặc lỗi backend.
- **“`CompositeCacheManager` sẽ thử Redis khi Caffeine miss key.”** Nó tìm manager theo **tên region**, không chạy fallback theo **key**.
- **“Cache nào cũng có thể dùng `sync=true` với nhiều tên.”** Spring giới hạn synchronized `@Cacheable` ở một cache.
- **“Tất cả trường hợp async sẽ duyệt đủ tên.”** Miss bất đồng bộ có thể làm việc tra tên tiếp theo dừng sớm.
- **“L1 hit luôn là dữ liệu mới nhất.”** Nếu không có version/invalidation, L1 cũ có thể che L2 mới.
- **“`@CacheEvict` xóa mọi nơi ngay lập tức.”** Hiệu lực và phạm vi theo backend/manager/node; invalidate xuyên node cần thiết kế riêng.
- **“TTL tự giải quyết mọi lỗi nhất quán.”** Nó chỉ hạn chế thời gian lưu; cần xác định mức stale chấp nhận được và cơ chế chủ động.

## Tài liệu tham khảo chính thức

- Spring Framework — `@Cacheable` và caching annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework 6.2 — Javadoc `Cacheable.cacheNames`, chú ý async miss: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework — Javadoc `CompositeCacheManager`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/cache/support/CompositeCacheManager.html
- Spring Framework — Cấu hình cache storage/backend: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — `Cache` API: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/Cache.html

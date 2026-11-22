# Phân biệt xóa chủ động với tự hết hạn tại kho lưu trữ

## Mục tiêu bài học

Sau bài này, bạn sẽ phân biệt được **xóa cache chủ động** (application-driven eviction) với **entry tự hết hạn** theo chính sách của kho cache (provider-driven expiration), biết Spring Cache chịu trách nhiệm phần nào, chọn được lúc sử dụng `@CacheEvict`, TTL hoặc kết hợp cả hai, và thực hành một ví dụ Java 17+ có kết quả kiểm chứng được.

Bài thuộc nhóm **`@CacheEvict`**: trọng tâm là **ai kích hoạt việc loại entry**, **khi nào giá trị cũ ngừng được sử dụng** và **điều gì xảy ra khi nguồn dữ liệu thay đổi trước lúc TTL kết thúc**. Một entry biến mất khỏi góc nhìn người đọc trong cả hai tình huống, nhưng nguyên nhân, bảo đảm và cách cấu hình khác nhau.

## 1. Cùng là cache miss, nhưng có hai nguyên nhân khác nhau

Giả sử phương thức `getProduct("P1")` đọc database và cache kết quả có tên sản phẩm `"Java"`:

```text
Lần 1: cache miss → đọc DB "Java" → lưu cache[P1] = "Java"
Lần 2: cache hit  → trả "Java" từ cache
DB thay đổi: P1 = "Spring"
```

Ngay lúc database đổi, cache **không tự biết** có giá trị mới. Có hai cách chính để entry cũ không còn được phục vụ:

1. **Xóa chủ động:** code ứng dụng thực hiện một hành động như `@CacheEvict(key = "#p0")` sau khi cập nhật nguồn thành công. Lần đọc sau thấy miss và nạp `"Spring"`.
2. **Tự hết hạn:** nhà cung cấp cache được cấu hình TTL, ví dụ `expireAfterWrite(10 phút)`. Khi thời hạn của entry đã trôi qua, lần đọc không được dùng giá trị `"Java"` nữa; có thể xảy ra cache miss và nạp `"Spring"` ngay cả khi ứng dụng **không gọi `@CacheEvict`**.

Trong khoảng từ khi DB đổi đến khi entry hết hạn, **TTL một mình vẫn có thể cho phép dữ liệu cũ**. Ngược lại, xóa chủ động cần ứng dụng biết chính xác dữ liệu nào bị ảnh hưởng và phải thực sự chạy cơ chế invalidation.

### Khái niệm không nên trộn lẫn

- **Evict/invalidate chủ động:** lệnh loại entry do nghiệp vụ hoặc tác vụ quản trị khởi phát, qua `@CacheEvict` hoặc API cache phù hợp.
- **Expiration:** chính sách tuổi thọ do backend áp dụng, thường dựa trên thời gian kể từ khi **ghi**, **đọc gần nhất** hoặc một mốc riêng.
- **Logical expiration:** entry đã quá hạn và **không còn hợp lệ cho lookup**, dù backend chưa dọn vật lý khỏi cấu trúc bộ nhớ.
- **Physical cleanup:** backend thực sự giải phóng slot/bộ nhớ hoặc xóa key; có thể diễn ra sau thời điểm logical expiration.
- **Eviction vì dung lượng:** backend loại bớt entry do vượt giới hạn kích thước/bộ nhớ. Đây là cơ chế khác với TTL, dù tài liệu backend có thể dùng từ *eviction* cho cả hai.

**Chốt mô hình:** người đọc quan tâm entry có còn được dùng hay không; người vận hành còn phải quan tâm ai kích hoạt, thời điểm, việc dọn vật lý và số lần truy cập lại nguồn.

## 2. So sánh trực tiếp

| Tiêu chí | Xóa chủ động bằng `@CacheEvict` | Tự hết hạn tại kho lưu trữ |
| --- | --- | --- |
| Ai quyết định? | Ứng dụng/Spring caching interceptor theo annotation hoặc lời gọi cache API. | Provider như Caffeine/Redis theo policy TTL/expiry. |
| Điều kiện kích hoạt | Có invocation đi qua proxy và thỏa điều kiện của `@CacheEvict`. | Thời gian sống/quy tắc backend đã đạt ngưỡng. |
| Mốc thời gian | Theo sự kiện nghiệp vụ: update, delete, import, đồng bộ dữ liệu... | Theo thời gian kể từ ghi/truy cập hoặc thời điểm expiry tùy provider. |
| Phạm vi | Một key, hoặc toàn bộ cache qua `allEntries=true`. | Thường từng entry theo tuổi thọ của nó. |
| Liên hệ với DB | Có thể đặt sát thao tác cập nhật nguồn và đúng key. | Không mặc định biết DB đã đổi hay chưa. |
| Nguy cơ dữ liệu cũ | Nếu quên evict, chọn sai key, chưa commit, gọi bỏ qua proxy... | Trong suốt cửa sổ TTL còn hiệu lực dù DB đã đổi. |
| Khi nào miss? | Sau khi lệnh xóa hoàn tất và lookup sau đó tới đúng cache/key. | Sau khi backend coi entry đã hết hạn; việc dọn vật lý có thể đến sau. |
| Cần cấu hình gì? | `@EnableCaching`, `CacheManager` và `@CacheEvict` với tên/key chính xác. | Backend hỗ trợ expiration và cấu hình thời hạn cụ thể. |
| Nên dùng khi | Biết chính xác lúc dữ liệu được sửa/xóa. | Nguồn có thể thay đổi ngoài tầm ứng dụng hoặc muốn giới hạn tuổi entry. |

Hai cơ chế **bổ sung nhau**: application events giảm thời gian trả dữ liệu cũ; TTL chặn cache sống quá lâu khi bỏ lỡ một sự kiện hoặc có thay đổi từ bên ngoài. Không có cơ chế nào tự bảo đảm tính nhất quán tuyệt đối trong mọi giao dịch và tình huống concurrent.

## 3. @CacheEvict thực sự làm gì?

`@CacheEvict` là annotation của **Spring Cache abstraction**; nó đánh dấu một phương thức là điểm kích hoạt xóa. Đây không phải cấu hình thời gian sống của entry.

Ví dụ một key:

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(String id, String title) {
    repository.updateTitle(id, title);
}
```

*Đoạn trên minh họa annotation; `repository` là dependency của ứng dụng thực tế.* Sau khi phương thức kết thúc **thành công**, Spring yêu cầu cache `products` loại entry được xác định bởi đối số thứ nhất. Lần đọc `@Cacheable(cacheNames = "products", key = "#p0")` tiếp theo có thể nạp lại giá trị mới.

Ví dụ xóa toàn bộ entries của một cache:

```java
@CacheEvict(cacheNames = "productSearch", allEntries = true)
public void rebuildSearchIndex() {
    searchIndexer.rebuild();
}
```

`allEntries=true` dành cho tình huống thay đổi làm **nhiều key** không còn hợp lệ; Spring không cần tính từng key và bỏ qua ý nghĩa của `key` trong trường hợp xóa toàn vùng. Nhưng xóa hàng loạt có thể tạo **cache miss đồng thời**, tăng tải lên DB hoặc downstream. Ưu tiên xóa đúng key nếu quan hệ dữ liệu cho phép.

### Trước hay sau phương thức?

Hai tùy chọn cần phân biệt:

```java
// Mặc định: evict SAU khi method chạy thành công.
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateAfterSuccess(String id, String title) {
    repository.updateTitle(id, title);
}
```

```java
// Evict TRƯỚC khi method chạy, kể cả sau đó method ném exception.
@CacheEvict(cacheNames = "products", key = "#p0", beforeInvocation = true)
public void evictBeforeWork(String id) {
    performMaintenance(id);
}
```

Ở ví dụ thứ hai, `performMaintenance` là hàm nghiệp vụ minh họa. `beforeInvocation=true` không có nghĩa thao tác cập nhật sau đó sẽ thành công; nó chỉ đổi **thời điểm loại cache**. Nếu công việc thất bại, cache đã bị xóa và lượt đọc tiếp có thể phải truy cập nguồn. Ngược lại, ở mặc định `beforeInvocation=false`, một method ném exception sẽ không kích hoạt eviction thông thường.

**Điểm quan trọng về transaction:** “sau invocation” **không đồng nghĩa chắc chắn sau database commit**. Thứ tự interceptor/transaction, việc rollback và các request đồng thời có thể tạo race: xóa cache trước commit rồi một request khác nạp lại dữ liệu cũ. Hệ thống cần nhất quán cao phải thiết kế invalidation sau commit hoặc cơ chế phối hợp transaction thích hợp và kiểm thử thực tế.

### Điều kiện để annotation có hiệu lực

- Cần bật caching, thường bằng `@EnableCaching`.
- Cần một `CacheManager` và cache có tên đúng.
- Phương thức có annotation phải được gọi **qua Spring proxy** ở chế độ proxy mặc định; `this.updateProduct(...)` gọi nội bộ trong cùng bean sẽ bỏ qua caching advice.
- `key` phải khớp với key của đường đọc; `#p0` là đối số thứ nhất. Cùng tên cache nhưng key khác kiểu (`Long 1L` và `String "1"`) có thể không khớp.
- Nếu nguồn đổi ảnh hưởng nhiều cache hoặc nhiều entry, phải invalidation đủ phạm vi; một `@CacheEvict` không tự biết các bản sao/alias khác.

## 4. Tự hết hạn do provider: Spring Cache không tự tạo TTL

Spring Framework cung cấp `Cache`, `CacheManager` và các annotation để điều phối việc lưu, tra cứu, cập nhật, xóa. **Chính sách hết hạn theo thời gian thuộc cache provider** hoặc tầng cấu hình tương ứng. Thêm `@Cacheable`/`@CacheEvict` không tự đặt TTL.

Một số ví dụ thường gặp:

| Backend | Chính sách thời gian | Cần hiểu |
| --- | --- | --- |
| `ConcurrentMapCacheManager` | Không có TTL tích hợp mặc định. | Dùng cho demo/test đơn giản; entry có thể ở đó cho tới khi bị xóa hoặc cache bị loại. |
| Caffeine local cache | `expireAfterWrite`, `expireAfterAccess`, có thể cấu hình expiry riêng. | Expired entry không được dùng để trả kết quả; cleanup vật lý có thể được thực hiện khi cache hoạt động/maintenance. |
| Redis | TTL/expiration trên key do Redis và cấu hình cache quyết định. | Việc GET có gia hạn TTL hay không phụ thuộc cách sử dụng/cấu hình; không mặc định “đọc là reset TTL”. |
| Hệ thống cache khác | Tùy API và cấu hình provider. | Không giả định mọi backend hỗ trợ cùng đơn vị, semantics, thống kê hay lịch cleanup. |

Hai chính sách phổ biến của Caffeine:

- **`expireAfterWrite(10 phút)`:** entry hết hạn sau khoảng thời gian từ lúc được tạo hoặc thay thế lần cuối; lookup hit thông thường **không làm mới** mốc này.
- **`expireAfterAccess(10 phút)`:** entry hết hạn sau khoảng thời gian không có truy cập phù hợp; đọc/ghi lại có thể kéo dài thời gian tồn tại. Hữu ích cho dữ liệu “nếu không dùng nữa thì loại”.

Một số hệ thống còn có TTL theo từng entry hoặc refresh. Cần phân biệt **refresh (tải lại giá trị mới)** với **expire (không còn được trả giá trị cũ)** và **evict thủ công (ra lệnh xóa)**. `@CacheEvict` không gọi “đặt TTL bằng 0 cho toàn ứng dụng”; nó gửi yêu cầu xóa đúng cache entry/region.

### Hết hạn không đồng nghĩa dọn bộ nhớ chính xác tại mili giây đó

Với Caffeine, một entry đã hết hạn **không nên được trả cho lookup**, nhưng cơ chế thu hồi vật lý có thể chạy khi có hoạt động đọc/ghi hoặc maintenance; không có lời hứa tất cả key sẽ bị xóa khỏi bộ nhớ ngay đúng thời điểm TTL kết thúc. Caffeine có thể cấu hình scheduler cho việc cleanup gần kịp thời, nhưng lịch chạy vẫn best effort.

Tương tự, ở Redis cần phân biệt hành vi trả giá trị của một key đã hết hạn với chiến lược thực thi xóa key khỏi bộ nhớ. Đừng thiết kế correctness dựa trên giả định “đúng thời điểm TTL là event handler chắc chắn đã chạy”. Cách kiểm chứng quan trọng là **lookup sau khi TTL qua có trả entry cũ hay không**.

## 5. Ví dụ chạy được: @CacheEvict và TTL tạo ra hai cache miss khác nhau

Ví dụ Spring Boot + Java 17+ dùng Caffeine làm cache bộ nhớ. Ta dùng một **đồng hồ giả lập** (`ManualTicker`) để điều chỉnh thời gian mà Caffeine nhìn thấy, giúp phân biệt eviction và expiration **không phải `Thread.sleep()`** và không phụ thuộc độ chậm của máy.

Điều kiện: tạo dự án Spring Boot Gradle đã có plugin phù hợp và Java 17+; trong `build.gradle` có hai dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
```

Các class sau đặt trong cùng package `example.eviction`. Phương thức `main` chạy bằng Gradle `bootRun`.

**File `src/main/java/example/eviction/ManualTicker.java`:**

```java
package example.eviction;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Component;
import com.github.benmanes.caffeine.cache.Ticker;

@Component
public class ManualTicker implements Ticker {
    private final AtomicLong nanoseconds = new AtomicLong();

    @Override
    public long read() {
        return nanoseconds.get();
    }

    public void advance(Duration duration) {
        if (duration.isNegative()) {
            throw new IllegalArgumentException("duration must be non-negative");
        }
        nanoseconds.addAndGet(duration.toNanos());
    }
}
```

Trong production, Caffeine dùng thời gian monotonic của hệ thống; ticker tự tạo ở đây chỉ để demo có đầu ra xác định.

**File `src/main/java/example/eviction/CacheConfiguration.java`:**

```java
package example.eviction;

import java.time.Duration;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.github.benmanes.caffeine.cache.Caffeine;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager(ManualTicker ticker) {
        CaffeineCacheManager manager = new CaffeineCacheManager("products");
        manager.setCaffeine(Caffeine.newBuilder()
                .expireAfterWrite(Duration.ofSeconds(10))
                .ticker(ticker));
        return manager;
    }
}
```

`@EnableCaching` bật interception; `CaffeineCacheManager` cung cấp backend; `expireAfterWrite` đặt tuổi thọ **10 giây tính theo ticker** cho entry trong `products`. Không có cấu hình TTL trên `@Cacheable`/`@CacheEvict`.

**File `src/main/java/example/eviction/ProductService.java`:**

```java
package example.eviction;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final Map<String, String> database =
            new ConcurrentHashMap<>(Map.of("P1", "Original"));
    private final AtomicInteger reads = new AtomicInteger();

    @Cacheable(cacheNames = "products", key = "#p0")
    public String find(String id) {
        System.out.println("DB_READ #" + reads.incrementAndGet());
        return database.get(id);
    }

    // Chỉ dành cho demo: sửa nguồn nhưng CỐ TÌNH bỏ qua invalidation,
    // để quan sát dữ liệu cũ trong cửa sổ TTL.
    public void changeSourceWithoutEvict(String id, String name) {
        database.put(id, name);
    }

    // Sau khi method thành công, Spring loại entry products[id].
    @CacheEvict(cacheNames = "products", key = "#p0")
    public void changeAndEvict(String id, String name) {
        database.put(id, name);
    }
}
```

Ở đây `database` chỉ là `ConcurrentHashMap` mô phỏng nguồn dữ liệu; trong ứng dụng thật, nó có thể là repository. Hai phương thức thay đổi nguồn cố ý khác nhau để minh họa việc **có/không có invalidation**.

**File `src/main/java/example/eviction/EvictionVsTtlApplication.java`:**

```java
package example.eviction;

import java.time.Duration;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EvictionVsTtlApplication {

    public static void main(String[] args) {
        SpringApplication.run(EvictionVsTtlApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProductService service, ManualTicker ticker) {
        return args -> {
            System.out.println("first = " + service.find("P1"));
            System.out.println("hit = " + service.find("P1"));

            service.changeSourceWithoutEvict("P1", "Changed");
            System.out.println("still cached = " + service.find("P1"));

            service.changeAndEvict("P1", "Updated");
            System.out.println("after evict = " + service.find("P1"));

            ticker.advance(Duration.ofSeconds(10));
            System.out.println("after expiry = " + service.find("P1"));
        };
    }
}
```

Chạy trong thư mục dự án:

```bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
```

**Các dòng `System.out` của demo** theo đúng thứ tự; bỏ qua log do Spring Boot/Gradle tạo:

```text
DB_READ #1
first = Original
hit = Original
still cached = Original
DB_READ #2
after evict = Updated
DB_READ #3
after expiry = Updated
```

Phân tích:

1. `find("P1")` lần đầu **miss**, đọc nguồn `Original` và tạo `products["P1"]`. Đồng hồ hiện là 0.
2. `find("P1")` lần hai **hit**; không in `DB_READ`.
3. `changeSourceWithoutEvict` sửa dữ liệu gốc thành `Changed` nhưng entry vẫn `Original`, nên lần đọc sau **vẫn hit dữ liệu cũ**. TTL chưa hết và ứng dụng không evict.
4. `changeAndEvict` sửa nguồn thành `Updated`; vì method kết thúc thành công, `@CacheEvict` loại entry ngay theo key `P1`. `find` tiếp theo **miss** và in `DB_READ #2`, lấy `Updated` rồi cache lại.
5. `ticker.advance(10 giây)` làm entry `Updated` vượt thời hạn `expireAfterWrite(10 giây)` mà không gọi `@CacheEvict`.
6. `find` sau đó **miss vì expiration**, in `DB_READ #3`, đọc `Updated`. Giá trị có thể giống nhau vì nguồn chưa đổi, nhưng **lượt đọc nguồn tăng** chứng minh cơ chế đã bỏ entry hết hạn.

Chính các dòng `DB_READ` chứng minh đường đi của cache; chỉ nhìn giá trị trả về giống nhau **không đủ** để biết là hit hay miss. Đồng hồ giả chỉ phục vụ thử nghiệm nên không cần chờ thời gian thực; việc lookup sau khi mốc TTL đã trôi qua là thời điểm kiểm tra hiệu lực logical expiration.

**Lưu ý kiểm thử:** demo cần gọi `ProductService` từ bean `CommandLineRunner` để đi qua proxy; gọi `this.find(...)` ngay trong `ProductService` sẽ bỏ qua proxy ở cấu hình mặc định. Các file là mã Spring Boot hoàn chỉnh trong một dự án có build, không phải một file Java duy nhất dùng `javac` không dependency.

## 6. Chọn chiến lược theo yêu cầu nhất quán

### Trường hợp A: biết rõ sự kiện sửa dữ liệu

Ví dụ cập nhật tên sản phẩm qua cùng ứng dụng:

```text
request update(P1, "Spring")
   → cập nhật database thành công
   → evict products[P1]
   → lần đọc tiếp miss và nạp lại nguồn
```

`@CacheEvict` phù hợp vì nghiệp vụ biết **key bị ảnh hưởng** và không cần đợi TTL. Nhưng phải đảm bảo path update/delete/import nào cũng xử lý invalidation, bao gồm batch jobs và các hệ thống khác sửa nguồn.

### Trường hợp B: dữ liệu cũng có thể thay đổi từ bên ngoài

Ví dụ ứng dụng khác cập nhật tỷ giá mà dịch vụ của bạn chỉ có đường đọc. Không có sự kiện update tại service hiện tại để gọi `@CacheEvict`. TTL cho phép quy định **tuổi tối đa của mỗi entry trước khi trở thành miss**, nhưng không đảm bảo trả dữ liệu mới ngay sau mỗi thay đổi nguồn.

Nếu cần giảm stale window, có thể dùng event/message invalidation chung hoặc kiểm chứng version dữ liệu; TTL là giới hạn dự phòng. Không thay `@CacheEvict` bằng TTL thật ngắn một cách vô điều kiện vì sẽ làm tăng truy cập nguồn.

### Trường hợp C: nhiều instance hoặc cache dùng chung

- Với **Caffeine local**, mỗi JVM thường giữ cache riêng. Evict trên instance A **không tự xóa** entry của instance B. Nếu dữ liệu thay đổi từ A, B có thể tiếp tục trả giá trị cũ đến khi TTL/eviction riêng có hiệu lực.
- Với **Redis shared cache**, các instance có thể cùng truy cập key chung. Evict trên shared cache có thể được các instance khác nhìn thấy qua những lần đọc tiếp theo, tùy kiến trúc và có lớp local cache bổ sung hay không.
- Với **multi-layer cache** (local + distributed), phải lên kế hoạch invalidation cho từng lớp, tránh chỉ xóa Redis trong khi local giữ giá trị cũ.

### Trường hợp D: dữ liệu cần độ chính xác rất cao

Nếu không chấp nhận stale dù trong thời gian ngắn (ví dụ trạng thái quyền truy cập, một số quyết định tài chính), cần đánh giá có nên cache kết quả đó không hoặc dùng phương án đồng bộ, version checking, giao dịch/lock theo yêu cầu. `@CacheEvict` lẫn TTL **không phải** một bảo đảm tuyến tính tuyệt đối rằng mọi request đồng thời sau update sẽ đọc đúng một phiên bản mới.

## 7. Khi nào dùng @CacheEvict, TTL hay cả hai?

| Yêu cầu | Hướng tiếp cận |
| --- | --- |
| Đọc lặp lại thường xuyên, dữ liệu gần như không đổi | Cache với TTL phù hợp, có thể evict khi có cập nhật. |
| Có API update/delete rõ ràng, cần cập nhật kết quả sớm | Evict theo key sau thay đổi nguồn; có thể giữ TTL làm lớp dự phòng. |
| Dữ liệu cập nhật ngoài ứng dụng và không có notification | TTL hoặc cơ chế đồng bộ/event chủ động. |
| Danh mục bị thay đổi hàng loạt, không xác định hết key liên quan | Cân nhắc `allEntries=true` sau thành công; đánh giá cache stampede. |
| Nhiều replica dùng local cache | Cần invalidation giữa các replica hoặc TTL đủ ngắn theo SLA stale. |
| Cần chấp nhận dữ liệu cũ tối đa vài phút | TTL có thể hỗ trợ giới hạn tuổi entry; kiểm tra semantics provider và cửa sổ nạp lại. |
| Không chấp nhận dữ liệu cũ | Thiết kế nguồn đọc/đồng bộ phù hợp hoặc không cache; không dựa duy nhất vào TTL. |

Một cách lập chính sách là viết ra trước ba câu:

1. **Nguồn dữ liệu nào là source of truth?** Cache chỉ giữ bản sao.
2. **Sự kiện nào làm entry không còn đúng?** Liệt kê update/delete/transaction/batch/external events, xác định cache name/key cần evict.
3. **Cho phép giá trị cũ bao lâu khi bỏ lỡ sự kiện?** Đây là đầu vào thiết kế TTL/expiry và monitoring.

## 8. Lưu ý về lỗi, hiệu năng và vận hành

**Evict bị bỏ qua:** annotation không được kích hoạt nếu gọi cùng bean qua `this`, object tạo bằng `new`, chưa `@EnableCaching` hoặc cache manager sai. Xác minh bằng thống kê hit/miss và kiểm tra entry theo key trên backend.

**Xóa sai key:** đọc theo `@Cacheable(key="#p0")` nhưng xóa theo mã khác hay kiểu khác. Đảm bảo cùng key schema và cache name cho các đường đọc/ghi/xóa.

**Xóa rộng quá mức:** `allEntries=true` dễ dùng nhưng khiến nhiều key cùng miss, có thể tạo tải đột biến. Với dữ liệu nóng, cân nhắc prewarm, refresh hoặc điều phối tải sau invalidation.

**TTL quá ngắn:** tránh stale nhưng hit rate giảm; nhiều request đồng thời sau expiry có thể gây stampede. `@Cacheable(sync=true)` có thể giúp đồng bộ tính toán cho cùng key nếu provider hỗ trợ, nhưng không mặc định là khóa phân tán giữa nhiều instance.

**TTL quá dài:** giúp hit cao nhưng tăng nguy cơ dữ liệu cũ và dùng bộ nhớ; cần kết hợp event invalidation, size limits hoặc refresh phù hợp.

**Lỗi trong cập nhật:** với eviction sau invocation mặc định, method ném exception thì không evict. Nếu nguồn đã bị thay đổi trước khi ném exception, cache có thể vẫn cũ. Cần hợp đồng transaction và xử lý lỗi phù hợp.

**Transaction race:** evict sau method nhưng trước commit có thể khiến request khác nạp giá trị chưa cập nhật. Với nghiệp vụ quan trọng, giải pháp có thể bao gồm invalidation sau commit, versioning và tái kiểm tra dữ liệu; cần test đồng thời.

**Ngữ cảnh người dùng/tenant:** dù đã xóa hoặc hết hạn đúng thời điểm, cache key thiếu tenant, locale, quyền hoặc dữ liệu ảnh hưởng kết quả vẫn có thể gây trả nhầm dữ liệu. Cache lifecycle không sửa được lỗi thiết kế key.

**Quan sát hệ thống:** theo dõi hit/miss, cache size, số lần đọc nguồn, tỷ lệ load thất bại, latency, tuổi entry, eviction/expiration metrics do backend hỗ trợ. Tránh suy diễn chỉ từ một chỉ số; ví dụ hit cao có thể đi kèm stale data hoặc key sai.

## 9. Bài tập và phép kiểm thử tự đánh giá

Trên demo ở mục 5, làm lần lượt:

1. Đổi TTL từ 10 giây thành 30 giây và tăng ticker 10 giây: lần cuối phải **hit**, không tăng `DB_READ`. Sau đó tăng thêm 20 giây: lần đọc mới miss do hết hạn.
2. Bỏ `@CacheEvict` khỏi `changeAndEvict` và chạy lại: sau khi update thành `Updated`, trước thời điểm expiry, cache vẫn có thể trả `Original`. Điều này chứng minh update database không tự invalidation.
3. Thử `expireAfterAccess` thay `expireAfterWrite`; tăng ticker vài giây giữa các lần đọc để quan sát việc access có thể làm mới cửa sổ sống của entry.
4. Cố ý dùng `key="#p1"` ở method update (đối số là tên mới) trong khi read dùng `#p0` (ID). Tìm dấu hiệu entry cũ không bị xóa; sửa lại cho đúng. Chỉ làm trong môi trường thử nghiệm.
5. Thử `beforeInvocation=true` và cho method update ném exception: kiểm tra eviction đã xảy ra trước khi lỗi, so với mặc định chỉ evict sau thành công.
6. Thêm sản phẩm `P2` và thử evict riêng `P1`, xác nhận entry `P2` vẫn hit; sau đó thử `allEntries=true` trên method phù hợp và xác nhận cả hai key miss.
7. Với ứng dụng dùng Caffeine nhiều replica, mô phỏng hai context/instance cache khác nhau và quan sát evict cục bộ không xóa cache của instance còn lại.

Câu hỏi ôn tập:

- **Nếu DB đổi nhưng không có `@CacheEvict` thì kết quả có lập tức mới không?** Không; entry có thể còn hợp lệ theo TTL hiện tại.
- **Nếu TTL đã hết nhưng backend chưa dọn vật lý, GET có thể lấy entry đã hết hạn không?** Với backend tuân thủ expiration như Caffeine, lookup không trả entry quá hạn; việc dọn vật lý có thể trễ.
- **`@CacheEvict` mặc định chạy trước hay sau method?** Sau khi method hoàn thành thành công; `beforeInvocation=true` chuyển sang trước.
- **`@CacheEvict` có tự đặt TTL cho cache không?** Không, TTL là trách nhiệm cấu hình provider.
- **Xóa entry có tự cập nhật DB không?** Không; chỉ loại bản sao cache, nghiệp vụ cập nhật nguồn phải được thực thi riêng.
- **Đã evict đúng key thì còn cần TTL không?** Tùy yêu cầu; TTL hữu ích khi entry có thể bị stale do nguồn khác thay đổi hoặc một sự kiện invalidation bị bỏ lỡ.

## Tài liệu đọc tiếp

- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html
- Caffeine — Eviction/Expiration: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine — Cleanup: https://github.com/ben-manes/caffeine/wiki/Cleanup

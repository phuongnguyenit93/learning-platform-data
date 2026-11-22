# TransactionAwareCacheManagerProxy: đồng bộ thao tác cache với commit giao dịch

## 1. Mục tiêu và tình huống sử dụng

Bài học thuộc nhóm **Giao dịch** của Spring Framework Cache. Sau bài này, bạn sẽ:

- Hiểu vì sao cập nhật database và thay đổi cache không mặc nhiên xảy ra cùng một thời điểm.
- Giải thích vai trò của `org.springframework.cache.transaction.TransactionAwareCacheManagerProxy` và `TransactionAwareCacheDecorator`.
- Cấu hình một `CacheManager` đích rồi expose một `CacheManager` bọc transaction-aware cho ứng dụng.
- Nắm chính xác các thao tác **`put`, `evict`, `clear` được hoãn sau commit** và các thao tác yêu cầu hiệu lực tức thì **không hoãn**.
- Phân biệt commit, rollback, không có transaction, đồng thời nhiều request, và transaction callback với tính nguyên tử thực sự.
- Chạy ví dụ **Spring Boot + H2 + Java 17+** minh họa dữ liệu database, cache cũ trong transaction, eviction sau commit và bỏ qua cập nhật cache khi rollback.

**Thông điệp chính:** `TransactionAwareCacheManagerProxy` không biến cache thành một phần của database transaction. Nó **trang trí các vùng cache** để một số lệnh thay đổi cache được **thực hiện trong callback sau khi giao dịch Spring commit thành công**, thay vì thực hiện ngay lúc code gọi lệnh.

## 2. Bài toán: database rollback nhưng cache đã bị sửa

Giả sử ứng dụng cache tên sản phẩm:

~~~text
database["P1"] = "Original"
cache["P1"]    = "Original"
~~~

Một nghiệp vụ thực hiện:

~~~java
@Transactional
public void renameProduct(String id, String newName) {
    repository.updateName(id, newName);
    cache.evict(id);
    performAnotherOperationThatMayFail();
}
~~~

Đây là **mã minh họa** trong service; `repository`, `cache` và `performAnotherOperationThatMayFail` phải được định nghĩa ở ứng dụng thật.

Nếu `cache.evict(id)` tác động ngay và bước cuối ném exception, database rollback nhưng cache đã bị xóa. Trường hợp đó thường gây cache miss và tải lại không cần thiết. Nguy hiểm hơn, một đường `cache.put(id, newName)` thực hiện **trước khi commit** có thể để giá trị **chưa từng được database commit** trong cache sau rollback.

Một race thường gặp:

~~~text
T0: database = Old, cache = Old
T1: giao dịch A cập nhật DB thành New (chưa commit)
T2: A gọi cache.put(key, New) nếu cache PUT ngay
T3: request B đọc cache → New (chưa phải dữ liệu committed)
T4: A rollback DB → Old
T5: cache vẫn New → dữ liệu sai
~~~

`TransactionAwareCacheManagerProxy` giúp tránh **một lớp lỗi nhất quán** này: khi lệnh `put` đi qua decorated cache và có transaction synchronization đang hoạt động, nó đợi **afterCommit**. Nếu transaction rollback, callback afterCommit không chạy, nên cache không nhận giá trị chưa commit.

Đối với `evict` và `clear`, sự trì hoãn còn giúp tránh làm mất entry khi DB transaction không thành công.

## 3. Cấu trúc của TransactionAwareCacheManagerProxy

`TransactionAwareCacheManagerProxy` là một implementation của interface `CacheManager`. Nó **bọc một CacheManager đã có**, không tự tạo backend riêng.

~~~text
Service / @Cacheable / @CacheEvict / Cache API
                     |
                     v
      TransactionAwareCacheManagerProxy
                     |
                getCache(name)
                     |
                     v
       TransactionAwareCacheDecorator
                     |
                     v
       Cache của CacheManager đích
          (ConcurrentMapCache, ...)
                     |
                 backend thực
~~~

Khi cần một cache có tên `products`, wrapper lấy cache từ manager đích rồi trả về đối tượng `Cache` được transaction-aware decorator bọc. Các thao tác tra cứu thông thường được chuyển đến target cache; các thao tác ghi/xóa thuộc phạm vi hỗ trợ có thể được đăng ký callback với `TransactionSynchronizationManager`.

### Ai phụ trách việc gì?

| Thành phần | Trách nhiệm |
| --- | --- |
| `PlatformTransactionManager` | Quản lý transaction thật, commit/rollback database hoặc tài nguyên tương ứng |
| `TransactionSynchronizationManager` | Theo dõi synchronization trong ngữ cảnh transaction Spring hiện tại và callback theo vòng đời |
| `TransactionAwareCacheManagerProxy` | Bọc manager đích để expose các cache có nhận thức transaction |
| `TransactionAwareCacheDecorator` | Trì hoãn một số lệnh thay đổi cache đến after-commit |
| `CacheManager` gốc | Quyết định vùng cache có tồn tại, kiểu backend và cấu hình của từng vùng |
| `Cache` gốc/provider | Thực thi đọc, ghi, xóa, TTL, serialization, dung lượng theo chính sách riêng |

**Không nhầm hai lớp proxy:** Spring AOP proxy có thể chặn lời gọi `@Transactional` hoặc `@Cacheable` trên service method. Còn `TransactionAwareCacheManagerProxy` là **một proxy của CacheManager**; nó không yêu cầu mọi method truy cập cache phải là service method dùng AOP, miễn hoạt động qua decorated `Cache` trong một giao dịch có synchronization.

## 4. Hành vi chính xác khi commit, rollback và ngoài transaction

Theo JavaDoc của Spring, `TransactionAwareCacheDecorator` đồng bộ các thao tác sau với giao dịch Spring:

| Cache API | Trong transaction có synchronization | Sau commit | Khi rollback |
| --- | --- | --- | --- |
| `put(key, value)` | Lên lịch ghi, chưa ghi target cache ngay | Ghi value vào target cache | Không thực hiện put đã lên lịch |
| `evict(key)` | Lên lịch xóa entry | Xóa entry khỏi target cache | Không thực hiện evict đã lên lịch |
| `clear()` | Lên lịch xóa vùng | Xóa các entries tại target cache | Không thực hiện clear đã lên lịch |
| `get(key)`, `get(key, Class)` | Đọc cache hiện tại; không “đọc phần ghi đang chờ” | Không có thao tác riêng | Không có thao tác riêng |
| `putIfAbsent(key, value)` | Yêu cầu hiệu lực tức thì; **không hoãn** | Đã tác động trước commit | Có thể vẫn còn hiệu lực sau rollback |
| `evictIfPresent(key)` | Yêu cầu loại key tức thì; **không hoãn** | Đã tác động trước commit | Không tự khôi phục entry |
| `invalidate()` | Yêu cầu toàn vùng hết hiệu lực ngay; **không hoãn** | Đã tác động trước commit | Không tự phục hồi vùng |

**Hai điểm dễ bỏ sót:**

1. **`put`/`evict`/`clear` chỉ được hoãn khi có synchronization transaction phù hợp.** Ngoài transaction, chúng thực thi ngay như cache thông thường. Chỉ có `@Transactional` viết trong mã nguồn mà cuộc gọi không đi qua Spring proxy không đủ để tạo transaction.
2. **`get` không có read-your-writes được bảo đảm.** Nếu trong transaction gọi `cache.put("P1","New")` rồi lập tức `cache.get("P1")`, có thể vẫn nhìn thấy `Old` (hoặc `null` nếu trước đó miss), bởi `New` chưa được chuyển vào target cache.

Các API `putIfAbsent`, `evictIfPresent` và `invalidate` được định nghĩa theo kỳ vọng **thấy tác động ngay**, nên không thể được trì hoãn như `put`/`evict`/`clear`. Đừng thay `evict` bằng `evictIfPresent` trong một transaction rồi mặc định rollback sẽ undo việc xóa.

### Timeline dễ nhớ

~~~text
TX BẮT ĐẦU
  |
  +-- update database trong transaction
  |
  +-- decoratedCache.evict("P1")
  |       └── đăng ký callback afterCommit; cache vẫn còn Old
  |
  +-- có thể đọc raw cache = Old
  |
  +-- COMMIT DB thành công
          |
          +-- callback afterCommit thực hiện evict("P1")
                   |
                   +-- đọc tiếp → cache miss → load từ DB mới
~~~

Nếu transaction rollback, callback afterCommit dành cho eviction **không chạy**, target cache vẫn giữ entry cũ trong ví dụ tuần tự.

## 5. Cấu hình Spring Boot: bọc CacheManager sẵn có

Ví dụ một cache in-memory:

~~~java
@Bean("rawCacheManager")
CacheManager rawCacheManager() {
    return new ConcurrentMapCacheManager("products");
}

@Bean("cacheManager")
@Primary
CacheManager cacheManager(
        @Qualifier("rawCacheManager") CacheManager raw) {
    return new TransactionAwareCacheManagerProxy(raw);
}
~~~

Đây là **đoạn cấu hình minh họa**: các annotation và lớp cần được import; có thể xem file Java đầy đủ ở mục 6. Ý nghĩa:

- `rawCacheManager` là provider/manager thật. Nó quản lý vùng `products` và không tự có transaction deferred behavior.
- `cacheManager` là bean expose cho phần lớn ứng dụng. `@Primary` giúp khi inject theo interface `CacheManager` mà không có qualifier, Spring chọn đúng wrapper.
- `@Qualifier` trên tham số cấu hình tránh dependency vòng hoặc inject nhầm chính wrapper.
- Từ đây, dùng `manager.getCache("products")` của **wrapper** để nhận decorated cache. Nếu lại inject `rawCacheManager` và ghi trực tiếp lên nó, bạn **bỏ qua** transaction-aware layer.
- Đối với annotation `@Cacheable`/`@CacheEvict`, bảo đảm cache interceptor đang dùng đúng manager có decorator; khi có nhiều CacheManager, nên kiểm soát bằng `@Primary` hoặc chỉ rõ manager/cấu hình theo ứng dụng.

Không cần thay provider bên dưới sang một cache “transactional” đặc biệt. Cơ chế này hoạt động ở tầng Spring Cache abstraction; nhưng giới hạn transaction synchronization vẫn phải được tôn trọng.

## 6. Ví dụ chạy được: rollback giữ cache cũ; commit xóa cache

Ví dụ tạo project **Spring Boot Java 17+** dùng H2, JDBC và Spring Cache; không cần Redis hay Caffeine nên dễ quan sát. Mọi thao tác cache trong demo là **API trực tiếp**. Sử dụng `TransactionTemplate` thay vì `@Transactional` để chỉ ra ranh giới begin/commit/rollback một cách minh bạch; cơ chế afterCommit mà decorator sử dụng vẫn là cơ chế Spring transaction bình thường.

### 6.1. Dependencies

Trong một dự án Spring Boot Gradle có plugin/version tương thích Java 17+, giữ cấu hình build hiện có và thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    runtimeOnly 'com.h2database:h2'
}
~~~

`spring-boot-starter-jdbc` cung cấp `JdbcTemplate` cùng infrastructure transaction của Spring. H2 là database in-memory hỗ trợ rollback. `spring-boot-starter-cache` cung cấp Spring Cache abstraction và `ConcurrentMapCacheManager`. Chạy ví dụ theo `bootRun` trong dự án Spring Boot; không dùng `javac` trần vì cần các thư viện ngoài JDK.

### 6.2. Tạo bảng và dữ liệu nguồn

Tạo `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE books (
    id VARCHAR(20) PRIMARY KEY,
    title VARCHAR(100) NOT NULL
);
~~~

Tạo `src/main/resources/data.sql`:

~~~sql
INSERT INTO books (id, title) VALUES ('B1', 'Original');
~~~

Spring Boot khởi tạo các SQL scripts cho H2 embedded database trước khi chạy `CommandLineRunner` (theo cấu hình SQL init mặc định phù hợp).

### 6.3. Một lớp Java đầy đủ

Tạo `src/main/java/example/txcache/TransactionAwareDemoApplication.java`:

~~~java
package example.txcache;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TransactionAwareDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransactionAwareDemoApplication.class, args);
    }

    @Bean("rawCacheManager")
    CacheManager rawCacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean("cacheManager")
    @Primary
    CacheManager cacheManager(
            @Qualifier("rawCacheManager") CacheManager rawManager) {
        return new TransactionAwareCacheManagerProxy(rawManager);
    }

    @Bean
    CommandLineRunner demo(
            JdbcTemplate jdbc,
            PlatformTransactionManager txManager,
            @Qualifier("cacheManager") CacheManager exposed,
            @Qualifier("rawCacheManager") CacheManager rawManager) {

        return args -> {
            Cache cache = Objects.requireNonNull(
                    exposed.getCache("books"), "wrapped cache missing");
            Cache raw = Objects.requireNonNull(
                    rawManager.getCache("books"), "raw cache missing");

            AtomicInteger loads = new AtomicInteger();
            Supplier<String> read = () -> {
                String hit = cache.get("B1", String.class);
                if (hit != null) {
                    return hit;
                }
                String fromDb = jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, "B1");
                System.out.println("DB_LOAD #" + loads.incrementAndGet());
                cache.put("B1", fromDb);
                return fromDb;
            };

            TransactionTemplate tx = new TransactionTemplate(txManager);

            // Ngoài transaction: put diễn ra ngay.
            System.out.println("initial = " + read.get());
            System.out.println("cached = " + read.get());

            // Transaction #1: cập nhật DB rồi yêu cầu evict,
            // nhưng cố ý rollback để kiểm chứng cache không bị xóa.
            tx.executeWithoutResult(status -> {
                jdbc.update("UPDATE books SET title = ? WHERE id = ?",
                        "RolledBack", "B1");
                cache.evict("B1");
                System.out.println("rollback tx raw = " +
                        raw.get("B1", String.class));
                status.setRollbackOnly();
            });
            System.out.println("after rollback = " + read.get());

            // Transaction #2: commit DB, sau commit mới evict.
            tx.executeWithoutResult(status -> {
                jdbc.update("UPDATE books SET title = ? WHERE id = ?",
                        "Committed", "B1");
                cache.evict("B1");
                System.out.println("commit tx raw = " +
                        raw.get("B1", String.class));
            });
            System.out.println("after commit = " + read.get());
            System.out.println("hit after commit = " + read.get());

            // put cũng được trì hoãn đến afterCommit.
            tx.executeWithoutResult(status -> {
                cache.put("manual", "ready");
                System.out.println("during put raw = " +
                        raw.get("manual", String.class));
            });
            System.out.println("after put raw = " +
                    raw.get("manual", String.class));

            // put trong transaction rollback sẽ bị bỏ qua.
            tx.executeWithoutResult(status -> {
                cache.put("rolled", "ghost");
                System.out.println("during rolled put raw = " +
                        raw.get("rolled", String.class));
                status.setRollbackOnly();
            });
            System.out.println("after rolled-back put = " +
                    raw.get("rolled", String.class));

            // Không có transaction: decorated cache put ngay.
            cache.put("outside", "immediate");
            System.out.println("outside transaction = " +
                    raw.get("outside", String.class));
        };
    }
}
~~~

**Giải thích cách chọn bean:**

- Có hai `CacheManager`: `rawCacheManager` là manager thật; `cacheManager` chứa `TransactionAwareCacheManagerProxy` và được đánh dấu `@Primary`.
- Biến `cache` lấy từ **wrapper**, nên `put`/`evict` đi qua `TransactionAwareCacheDecorator`. Biến `raw` chỉ dùng để **quan sát target cache** trước khi deferred operation chạy.
- `TransactionTemplate` sử dụng `PlatformTransactionManager` do Spring Boot cấu hình cho H2 `DataSource`. Callback `executeWithoutResult` tham gia transaction với synchronization; cuối callback, template commit hoặc rollback theo `status`.
- `Supplier<String> read` chỉ phục vụ demo để có đường đọc/put tường minh. Nó đọc `cache.get("B1", String.class)`, query H2 khi miss rồi `cache.put(...)`. Trong workload đồng thời, đường check-then-act này có race riêng; ví dụ cố tình chạy tuần tự và không dùng nó làm code cache loader production.
- Cache là local `ConcurrentMapCache`. Đây không phải ví dụ quản lý distributed transaction và không yêu cầu `@EnableCaching`, vì tất cả thao tác cache trong chương trình đều gọi qua API trực tiếp.

### 6.4. Chạy và kết quả

Trong thư mục project Spring Boot:

~~~bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
~~~

**Những dòng do ví dụ in qua `System.out`, theo thứ tự** (bỏ qua log Boot/Gradle):

~~~text
DB_LOAD #1
initial = Original
cached = Original
rollback tx raw = Original
after rollback = Original
commit tx raw = Original
DB_LOAD #2
after commit = Committed
hit after commit = Committed
during put raw = null
after put raw = ready
during rolled put raw = null
after rolled-back put = null
outside transaction = immediate
~~~

Đối chiếu:

1. Lần đọc đầu cache miss, JDBC đọc `Original` và in `DB_LOAD #1`. Vì chưa có transaction, `cache.put("B1", "Original")` tác động ngay. Lần hai hit, không in thêm `DB_LOAD`.
2. Trong transaction rollback, database tạm cập nhật `RolledBack`; `cache.evict("B1")` **chỉ đăng ký eviction sau commit**. Raw cache vẫn là `Original`. `status.setRollbackOnly()` khiến H2 rollback và callback afterCommit không chạy. Lần đọc sau vẫn hit `Original`.
3. Trong transaction commit, database đổi thành `Committed`. Eviction lại được lên lịch; **trước commit**, raw cache vẫn `Original`. Khi transaction commit thành công, callback xóa entry `B1`. Lần đọc tiếp miss, JDBC in `DB_LOAD #2`, trả `Committed` rồi cache lại; lần sau hit.
4. `cache.put("manual", "ready")` bên trong transaction chưa xuất hiện ở raw cache; vì thế `during put raw = null`. Sau commit, callback ghi và giá trị trở thành `ready`.
5. `cache.put("rolled", "ghost")` trong transaction rollback không xuất hiện trong raw cache ngay, và cũng không xuất hiện sau rollback. Đây là ví dụ **không cache dữ liệu chưa commit**.
6. `cache.put("outside", "immediate")` xảy ra ngoài transaction nên có hiệu lực ngay và raw cache đọc được `immediate`.

**Kết quả được suy ra từ kịch bản tuần tự** và hợp đồng của Spring TransactionAware cache decorator với `TransactionTemplate` và H2. Trong ứng dụng thật, cần chạy integration tests với cùng Spring/Boot version, cấu hình transaction manager và backend thực tế.

## 7. Sử dụng với @Transactional, @Cacheable và @CacheEvict

Trong ứng dụng service điển hình:

~~~java
@Service
public class BookWriteService {

    private final BookRepository repository;

    public BookWriteService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    @CacheEvict(cacheNames = "books", key = "#p0")
    public void rename(String id, String newTitle) {
        repository.rename(id, newTitle);
    }
}
~~~

Đây là **đoạn minh họa**, chưa phải Java file độc lập: cần khai báo `BookRepository` và imports của `@Service`, `@Transactional`, `@CacheEvict`. Để annotation cache có tác dụng, bật `@EnableCaching` và cấu hình interceptor dùng `CacheManager` đã bọc. `@Transactional` phải được áp dụng khi lời gọi đi qua Spring-managed proxy (hoặc cơ chế tương ứng).

Khi caching operation thực hiện `evict` trong một transaction đang có synchronization, decorator **hoãn xóa đến afterCommit**. Tuy vậy, **thứ tự giữa transaction advice và caching advice cũng quan trọng**: nếu cache advice chạy sau khi giao dịch đã kết thúc, thao tác cache ngoài transaction diễn ra ngay (nhưng lúc ấy commit đã xong); không nên dựa trên một thứ tự ngầm để chứng minh tính nhất quán phức tạp.

Tương tự, `@CachePut` có thể dẫn đến lệnh `Cache.put` và được hoãn sau commit nếu nó đi qua decorated cache trong transaction đang đồng bộ. `@Cacheable` khi miss thường thực hiện put; đọc lại trong cùng transaction **có thể chưa thấy entry mới**, vì pending put chưa phải cache value đã được ghi. Cần kiểm tra riêng những đường sử dụng `@Cacheable(sync=true)` hoặc cache loading APIs (`get(key, Callable)`/async retrieval): chúng có thể đi qua native loader semantics, **không nên giả định** đều được hoãn giống một lệnh `Cache.put` bình thường.

### Khác với beforeInvocation=true

~~~java
@CacheEvict(cacheNames = "books",
            key = "#p0",
            beforeInvocation = true)
public void rename(String id, String title) {
    // ...
}
~~~

Đoạn này là minh họa bên trong Spring bean. `beforeInvocation=true` quy định **khi nào Spring caching interceptor phát lệnh evict so với lúc method chạy**. Nếu lệnh `evict` phát ra khi có transaction synchronization và manager transaction-aware, **tác động thực tế lên target cache vẫn có thể bị hoãn**. Nếu chưa có transaction/synchronization, evict có thể xảy ra ngay. Không đồng nhất thuộc tính annotation với cam kết “xóa chắc chắn trước/sau database commit”.

## 8. Các giới hạn quan trọng: không phải XA transaction

`TransactionAwareCacheManagerProxy` **không thực hiện two-phase commit** với database và cache. Nó không bảo đảm tính nguyên tử kiểu “database và cache hoặc cùng commit hoặc cùng rollback” trong mọi tình huống.

### 8.1. Database commit xong, cache callback vẫn có thể lỗi

Trình tự thực tế có thể là: database commit thành công → callback `afterCommit` cố evict/put → provider cache mất kết nối hoặc lỗi. Database không thể được “uncommit” chỉ vì việc evict sau commit thất bại. Thiết kế retry, event/outbox, monitoring và cơ chế xử lý lỗi tùy yêu cầu nhất quán; đừng coi decorator là transaction manager của Redis/Caffeine.

### 8.2. Khoảng thời gian dữ liệu cũ trước commit

Vì evict bị trì hoãn, một request khác có thể đọc **entry cũ** trong lúc transaction update DB chưa commit. Điều này phù hợp với việc chưa công bố dữ liệu mới. Nhưng quanh thời điểm commit, các request đồng thời có thể tạo race nạp cache, ví dụ một request bắt đầu load nguồn cũ trước commit và kết thúc put sau thời điểm eviction. Decorator **không tự giải quyết toàn bộ race này**.

Nếu yêu cầu tính nhất quán rất cao, cân nhắc cache key theo version, kiểm soát concurrency/invalidation, transactional outbox/event, hoặc không cache dữ liệu cần strongly consistent.

### 8.3. put/evict không có read-your-writes

`cache.put(key, newValue)` đã được lên lịch nhưng chưa thay target cache. Trong cùng transaction, `cache.get(key)` vẫn có thể trả entry cũ. Đừng viết nghiệp vụ giả định “put xong thì get ngay phải ra newValue” khi dùng decorated cache. Nếu cần giá trị mới trong transaction, dùng biến/đối tượng nghiệp vụ vừa tính hoặc đọc database qua transaction phù hợp, không đọc cache để kiểm chứng pending put.

### 8.4. Thao tác immediate không được rollback

`putIfAbsent`, `evictIfPresent` và `invalidate` yêu cầu hiệu lực ngay. Chúng không được hoãn giống `put`/`evict`/`clear`, vì vậy rollback DB không tự undo những thay đổi cache đó. Hãy xét mục tiêu API trước khi sử dụng trong một transaction.

### 8.5. Không có transaction synchronization

Việc có `@Transactional` trên method chưa đủ nếu lời gọi đi qua `this.method()` và bypass proxy, hoặc transaction manager thực tế không mở synchronization. Khi không có Spring-managed transaction synchronization, các thao tác cache được decorator thực thi ngay. Với async thread, reactive flow hoặc code chạy ngoài ngữ cảnh thread của transaction, cần xác minh sự lan truyền context; **không suy ra** thread mới tự nhận transaction và callback.

### 8.6. Nhiều cache manager và nhiều replica

Nếu có hai `CacheManager` mà annotation vẫn dùng manager **gốc**, phần transaction-aware không có tác dụng. Xác định bean được inject và `cacheManager` mặc định của caching interceptor. Đối với Caffeine local, mỗi JVM có cache riêng: after-commit evict trên JVM A không tự xóa cache của JVM B. Đối với Redis shared cache, cần hiểu chính sách transaction và network của backend, cùng các lớp local cache bổ sung.

## 9. Khi nào nên dùng? So sánh các lựa chọn

| Nhu cầu | Giải pháp phù hợp |
| --- | --- |
| Ứng dụng đang có `CacheManager` nhưng muốn hoãn `put/evict/clear` đến sau commit | Bọc bằng `TransactionAwareCacheManagerProxy` |
| Chỉ có một `Cache` cụ thể cần decorator | Có thể dùng `new TransactionAwareCacheDecorator(cache)` nếu kiểm soát đầy đủ đường truy cập |
| Một manager có sẵn tính năng transaction-aware tích hợp | Xem API của **chính manager đó** để bật tính năng, nếu được hỗ trợ; tránh bọc lặp vô ích |
| Cache ngoài transaction hoặc dữ liệu chỉ đọc | Manager thông thường có thể đủ |
| Có distributed updates, event loss hoặc yêu cầu cực cao về nhất quán | Bổ sung outbox, event invalidation, versioning, retry, monitoring hoặc không cache |
| Cần exactly-once / atomic DB + cache như cùng tài nguyên | `TransactionAwareCacheManagerProxy` **không** cung cấp bảo đảm này |

Lưu ý với `AbstractTransactionSupportingCacheManager`: lớp cơ sở của Spring cung cấp `setTransactionAware(true)` cho những manager thật sự kế thừa nó. **Không giả định mọi loại manager**, đặc biệt Caffeine/Redis theo mọi phiên bản, đều có method này. `TransactionAwareCacheManagerProxy` có thể là lựa chọn rõ ràng để bọc một manager hiện hữu.

## 10. Các lỗi phổ biến và cách phát hiện

1. **Bọc manager nhưng code vẫn dùng raw manager:** deferred operation không xảy ra. Kiểm tra `@Primary`, `@Qualifier` và caching configuration.
2. **Tưởng proxy tạo transaction:** class này chỉ quan sát synchronization hiện có; phải có transaction manager thực thi giao dịch.
3. **Tưởng `@Transactional` tự chạy khi self-invocation:** gọi `this.rename(...)` thường bỏ qua AOP advice ở proxy mode.
4. **Nhầm deferred put với database write:** không có quyền điều khiển commit của cache backend như một participant XA.
5. **Tưởng `evictIfPresent` được hoãn:** nó là operation immediate, khác `evict`.
6. **Tưởng đọc được pending put:** cache hit/miss dựa trên target cache; hãy kiểm tra read-your-writes bằng test.
7. **Dùng `@Cacheable(sync=true)` rồi suy luận mọi put đều afterCommit:** loader path có semantics riêng; kiểm tra provider thực.
8. **Không xử lý cache callback lỗi sau commit:** DB có thể đã commit, trong khi cache vẫn sai/cũ; cần quan sát và chiến lược phục hồi.
9. **Chỉ kiểm thử happy path:** rollback mới là trường hợp chứng minh sự khác biệt quan trọng.
10. **Dùng eviction sau commit nhưng không đồng bộ replica khác:** local caches của nhiều process vẫn độc lập.
11. **Quên namespace và key:** evict `books["B1"]` không loại entry `searchResults["B1"]`; cache name/key phải đồng nhất.
12. **Cho rằng cache stats hoặc TTL được tự cấu hình:** decorator không thêm TTL/size/metrics; chúng thuộc provider.

## 11. Bài tập và kế hoạch kiểm thử

### 11.1. Bài tập từ demo

1. Bỏ `TransactionAwareCacheManagerProxy` và inject thẳng `rawCacheManager` vào `Cache cache`: trong transaction rollback, `cache.evict("B1")` sẽ xóa entry ngay. So sánh output và ghi lại vì sao rollback không tự khôi phục entry cache.
2. Ở transaction commit, thử `cache.put("manual", "ready")` rồi đọc raw cache **trước** commit: raw chưa có entry. Sau commit: raw mới có `ready`.
3. Đổi `status.setRollbackOnly()` thành việc ném `IllegalStateException`: dùng exception handling ngoài `TransactionTemplate`, kiểm tra database rollback và pending cache operation không áp dụng.
4. Đưa `cache.evict("B1")` ra ngoài `TransactionTemplate`: thao tác chạy ngay. Tự giải thích khác biệt với evict trong transaction.
5. Tạo một key `temporary`, gọi `evictIfPresent` hoặc `putIfAbsent` trong transaction rồi rollback; quan sát hành vi immediate và đối chiếu với `evict`/`put`.
6. Viết thêm một Spring service với `@Transactional` và `@CacheEvict`, bật `@EnableCaching` và kiểm tra đúng manager decorator được Spring cache interceptor dùng.
7. Thử chạy hai transaction đồng thời trong test để phát hiện race ở thời điểm commit/afterCommit và đề xuất versioned key hoặc invalidation event.

### 11.2. Bảng test nên có

| Trường hợp | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| Không có transaction | `cache.put(k,v)` qua decorated cache | Target cache thấy value ngay |
| Rollback + `put` | Ghi pending value rồi rollback | Target không có value mới |
| Commit + `put` | Ghi pending value rồi commit | Target thấy value sau commit |
| Rollback + `evict` | Lên lịch evict rồi rollback | Target vẫn có entry cũ |
| Commit + `evict` | Lên lịch evict rồi commit | Target entry bị xóa, lần đọc sau miss |
| Commit + `clear` | Clear pending rồi commit | Target region bị xóa entries sau commit |
| Immediate API | `putIfAbsent` hoặc `evictIfPresent` | Tác động tức thì, rollback không undo |
| Đọc sau pending put | `put` rồi `get` trong transaction | Có thể chưa thấy value mới |
| Đổi manager injection | Inject raw thay wrapper | Deferred behavior không còn |
| Cache backend lỗi ở afterCommit | Giả lập lỗi khi evict | DB đã commit; cần cơ chế phục hồi |
| Concurrency | Nạp cache xung quanh commit | Không giả định tuyệt đối không stale |
| Multi-instance | Evict local JVM A | Local cache của JVM B không tự đổi |

### Checklist trước khi triển khai

- [ ] `CacheManager` đích đã cấu hình đúng cache names, TTL, capacity và backend.
- [ ] Bean `TransactionAwareCacheManagerProxy` là manager thực sự được service/interceptor sử dụng.
- [ ] Transaction manager và synchronization hoạt động trên đúng ngữ cảnh/thread.
- [ ] Hiểu `put/evict/clear` deferred và `putIfAbsent/evictIfPresent/invalidate` immediate.
- [ ] Không kỳ vọng read-your-writes với pending put.
- [ ] Có test commit/rollback trên database thật (hoặc embedded) và cache backend đang dùng.
- [ ] Có phương án xử lý race, lỗi afterCommit, nhiều replica, retry và invalidation.
- [ ] Không coi decorator là thay thế cho transactional outbox hay giao dịch phân tán.

## 12. Tài liệu tham khảo chính thức

- Spring Framework — TransactionAwareCacheManagerProxy JavaDoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html
- Spring Framework — TransactionAwareCacheDecorator JavaDoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework — TransactionSynchronizationManager JavaDoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — TransactionTemplate: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html

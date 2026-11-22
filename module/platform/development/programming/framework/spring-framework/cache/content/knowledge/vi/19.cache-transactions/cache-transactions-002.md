# Rủi ro cache dữ liệu sau đó bị rollback trong Spring Framework

## 1. Vấn đề cốt lõi

Trong ứng dụng Spring có cả **database transaction** và **Spring Cache**, ta thường muốn kết quả cache phản ánh **dữ liệu đã commit**. Nhưng cache và cơ sở dữ liệu không mặc nhiên tham gia một giao dịch nguyên tử. Một lời gọi `@Cacheable` có thể đọc dữ liệu đang thay đổi **trong transaction chưa commit**, rồi ghi kết quả vào cache **ngay lúc đó**. Nếu transaction sau đó bị rollback, database trở về trạng thái trước, còn cache vẫn giữ giá trị đã lấy từ thay đổi bị hủy.

Đây là lỗi **cache chứa dữ liệu chưa từng được commit** (còn gọi là *cache pollution* do transaction hoặc *rollback leak*), không phải một cache miss bình thường.

### Ví dụ nhanh

Giả sử SKU `A` chưa tồn tại:

~~~text
DB (committed): không có A
Cache "prices":  không có A

T1: BEGIN
T1: INSERT A với giá 120, chưa COMMIT
T1: Gọi getPrice("A") trong cùng transaction
    -> SELECT nhìn thấy A=120 (read-your-writes)
    -> Cache MISS
    -> @Cacheable ghi Cache["A"]=120 ngay
T1: Gặp lỗi -> ROLLBACK
    -> DB không còn A

T2: Gọi getPrice("A")
    -> Cache HIT: 120
    -> không SELECT DB
    -> trả một sản phẩm KHÔNG TỒN TẠI trong dữ liệu committed
~~~

Việc T1 nhìn thấy giá trị mình vừa ghi là bình thường đối với transaction; điều sai là **phát tán giá trị đó ra cache dùng chung trước khi commit**. Một request ngoài transaction có thể đọc 120 từ cache dù ngay lúc đó database chưa từng công bố 120.

Cần phân biệt **dirty read qua database** với **đọc giá trị chưa commit qua cache**: database có thể vẫn dùng `READ_COMMITTED` đúng cách, nhưng cache không bị ràng buộc bởi database isolation, nên reader khác đọc được dữ liệu sai từ cache.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Vẽ timeline cho `@Cacheable` put trước commit rồi DB rollback.
- Giải thích vì sao `@Transactional` và `@Cacheable` không tự hợp thành một atomic transaction.
- Phân biệt rủi ro **put giá trị mới** với **evict/clear trước commit**.
- Dùng `TransactionAwareCacheManagerProxy` và hiểu giới hạn của nó.
- Dùng callback `TransactionSynchronization.afterCommit()` khi cần invalidation có chủ đích.
- Kiểm soát self-invocation, advisor order, rollback-only, async và nhiều node.
- Chạy demo Java 17 + H2 tái hiện giá trị cache “ma” sau rollback và đối chứng transaction-aware caching.
- Thiết kế test kiểm tra **cả database sau rollback lẫn entry cache**, không chỉ kết quả trả về.

## 2. Hai hệ thống trạng thái độc lập

Một phương thức service có thể tác động tới hai nơi:

~~~text
                  Business method
                        |
             +----------+----------+
             |                     |
             v                     v
       JDBC / JPA              Spring Cache
             |                     |
             v                     v
       DB transaction          Cache provider
             |                     |
       COMMIT/ROLLBACK         PUT/EVICT/CLEAR
             |                     |
        ACID của DB          Thường không nằm trong
                            cùng DB transaction
~~~

`@Transactional` thiết lập ranh giới và chính sách transaction cho các tài nguyên tham gia thông qua Spring transaction manager. `@Cacheable`, `@CachePut`, `@CacheEvict` điều phối thao tác cache thông qua `CacheInterceptor` và `CacheManager`.

**Không có bảo đảm chung** rằng cache put/evict luôn cùng commit hoặc rollback với database. Thậm chí hai annotation cùng đặt trên một method không tự tạo ra giao dịch ACID hai pha giữa DB và Redis/Caffeine/ConcurrentMap.

| Thao tác | Transaction database | Cache thông thường |
| --- | --- | --- |
| `INSERT/UPDATE` qua JDBC được enlist | Chưa công bố cho transaction khác trước commit, tùy isolation | Không thay đổi nếu chưa thao tác cache |
| `@Cacheable` miss → `Cache.put` | Không tự bảo vệ cache | Entry có thể hiển thị ngay |
| `ROLLBACK` | Hoàn tác dữ liệu DB đã ghi trong transaction | Không tự xóa một entry đã put |
| `@CacheEvict` | Không phải lệnh rollback/commit của DB | Có thể xóa entry ngay, theo cơ chế cache |
| `COMMIT` | Chốt thay đổi DB | Không tự đảm bảo invalidation xảy ra đúng lúc |

Vì vậy, khi đánh giá consistency, phải hỏi **cache operation xảy ra vào thời điểm nào so với DB commit**, và đường gọi nào thực sự đi qua Spring proxy.

## 3. Trình tự nguy hiểm: put trước rollback

### 3.1. Vì sao @Cacheable dễ ghi nhầm dữ liệu chưa commit?

Xét hai method thuộc hai bean khác nhau:

~~~java
// Snippet: repository và cấu hình Spring được cung cấp bởi ứng dụng.
@Transactional
public void createProduct(String sku, int price) {
    repository.insert(sku, price);
    priceReader.getPrice(sku);  // bean khác: có thể đi qua proxy cache
    downstream.notifyCreated(sku); // ném RuntimeException
}

@Cacheable(cacheNames = "prices", key = "#p0")
public Integer getPrice(String sku) {
    return repository.findPrice(sku);
}
~~~

Bên trong cùng transaction, việc `findPrice` thấy record mới là hợp lệ. Nhưng cache advice có thể thực hiện `Cache.put(sku, price)` **trước khi transaction kết thúc**. Nếu `notifyCreated` ném lỗi khiến DB rollback, cache vẫn chứa giá trị chưa commit trừ khi có biện pháp đồng bộ.

Đặc biệt đáng chú ý:

- Caching không cần có `@CachePut`; **`@Cacheable` khi miss cũng có hành vi put**.
- Một transaction có thể bị rollback không chỉ khi body method ném lỗi: có thể bị đặt `rollbackOnly`, gặp lỗi commit, ràng buộc DB, timeout hoặc rollback từ tầng gọi ngoài.
- Giá trị được cache có thể không chỉ là bản ghi mới: đó còn là tổng tiền, hạn mức, số lượng tồn, quyền truy cập hoặc dữ liệu tổng hợp tính trên các thay đổi chưa commit.

### 3.2. Read-your-writes không phải cache-safe

Hệ quản trị cơ sở dữ liệu thường cho transaction nhìn thấy thay đổi của **chính nó**. Nên `SELECT` trả 120 trước commit không phải bug của database. Bug xuất hiện ở chỗ `Cache.put` làm kết quả nội bộ này có thể được tái sử dụng **ngoài transaction**.

Một transaction khác không nhìn thấy uncommitted row khi dùng `READ_COMMITTED`, nhưng một cache local/shared không có cùng isolation có thể trả entry đó ngay.

### 3.3. Khi có lỗi sau khi value đã được cache

~~~text
T1: BEGIN
T1: UPDATE balance = balance - 50
T1: @Cacheable đọc balance mới (chưa commit)
T1: cache.put("user-1", balanceMới)
T1: downstream call thất bại
T1: ROLLBACK DB

T2: @Cacheable đọc lại "user-1"
    -> HIT balanceMới (đáng ra phải là balanceCũ)
~~~

Số dư ở đây chỉ để minh họa vì cache dữ liệu tài chính cần chính sách nhất quán/kiểm soát nghiêm ngặt hơn. Dùng cache như một optimization, không lấy nó làm nguồn có thẩm quyền thay database.

### 3.4. Cached-null có thể tạo lỗi ngược

Nếu một transaction **xóa** record rồi `@Cacheable` miss đọc ra `null` và provider cho phép cached-null, cache có thể giữ “không tồn tại”. Sau rollback, record vẫn ở database nhưng client nhận null qua cache.

Do đó, rollback leak bao gồm:

- Cache có **giá trị mới không tồn tại**.
- Cache có **giá trị cũ sai thời điểm**.
- Cache có **null đại diện vắng mặt** nhưng DB đã phục hồi record.
- Cache có **dữ liệu tổng hợp** dựa trên nhiều thay đổi đã bị hủy.

## 4. Rủi ro của @CacheEvict trước commit

Tình huống thứ hai không phải cache đã put giá trị sai, mà là **xóa entry hợp lệ quá sớm**:

~~~text
DB: A = 100 (đã commit)
Cache["A"] = 100

T1: BEGIN
T1: UPDATE A = 120, chưa commit
T1: cache.evict("A") ngay
T2: GET A -> cache MISS
T2: DB READ_COMMITTED vẫn thấy A = 100
T2: cache.put("A", 100)
T1: COMMIT A = 120

Kết quả: Cache["A"] = 100 dù DB là 120
~~~

Đây là **race giữa eviction và repopulation**. Dù T1 commit thành công, cache vẫn có thể stale. Nếu T1 rollback, việc xóa trước đó có thể chỉ khiến extra miss và tốn tải, nhưng có thể phát sinh vấn đề khác khi reader nạp dữ liệu chưa đồng bộ trong môi trường phức tạp.

### 4.1. beforeInvocation=false không đồng nghĩa afterCommit

~~~java
@CacheEvict(cacheNames = "prices", key = "#p0")
public void updatePrice(String sku, int value) {
    repository.update(sku, value);
}
~~~

Theo contract annotation, `beforeInvocation=false` mặc định xử lý evict **sau khi phần method được invoke thành công**. Điều này **không tự đảm bảo** là sau DB commit với mọi cách kết hợp `@Transactional`/cache advisor, transaction boundary và lời gọi.

Nếu transaction được mở ở service bên ngoài rồi một method con `@CacheEvict` trả thành công, giao dịch bên ngoài vẫn có thể rollback **sau đó**. Dùng `beforeInvocation=true` còn nguy hiểm hơn nếu mục tiêu là chỉ invalidate sau commit: thao tác cache được yêu cầu trước khi method thực thi.

### 4.2. Evict sau commit cải thiện nhưng không phải ACID

Đợi DB commit rồi mới evict thường giảm khoảng thời gian reader nạp dữ liệu cũ. Tuy nhiên vẫn có một khoảng ngắn **giữa commit và cache eviction**. Ở hệ thống nhiều node, còn có độ trễ network, replication hoặc xử lý message. Không nên hứa tính nhất quán tuyệt đối chỉ bằng việc thay vị trí lệnh evict.

## 5. Advisor order và transaction boundary

Khi một method dùng đồng thời:

~~~java
@Transactional
@Cacheable(cacheNames = "prices", key = "#p0")
public Integer load(String sku) {
    return repository.findPrice(sku);
}
~~~

bạn cần biết **ai bao quanh ai**. Cả transaction advice và cache advice đều được triển khai qua Spring AOP/proxy mode thông dụng. Thứ tự advice chịu ảnh hưởng cấu hình `@EnableTransactionManagement(order = ...)`, `@EnableCaching(order = ...)` và các interceptor khác. Không nên suy ra chính xác cache put sẽ xảy ra trước/sau commit chỉ từ thứ tự hai annotation viết trên source code.

Hai hình thức khái niệm:

~~~text
Trường hợp A: Transaction advice ở ngoài
  BEGIN
    Cache advice
      -> get/put cache
  COMMIT/ROLLBACK

Trường hợp B: Cache advice ở ngoài
  Cache advice
    BEGIN
      -> method DB
    COMMIT/ROLLBACK
  -> cache put theo kết quả
~~~

Ngay cả trong trường hợp B, transaction **ở tầng gọi ngoài** có thể vẫn chưa commit. Việc cấu hình advisor order không thay thế một hợp đồng rõ ràng về after-commit caching.

### Bốn bẫy về @Transactional

1. **Self-invocation:** `this.save()` trong cùng class có thể bypass transaction proxy và cache proxy; annotation trên method nội bộ không tự có hiệu lực.
2. **Rollback policy:** Mặc định Spring rollback với `RuntimeException`/`Error`; checked exception không tự rollback trừ khi cấu hình `rollbackFor` hoặc quy tắc khác.
3. **Ngoài cùng quyết định commit:** Method con có thể thành công nhưng transaction ngoài đánh dấu rollback-only; cache put ở method con không có nghĩa transaction đã an toàn.
4. **Đường bất đồng bộ:** `@Async`, thread khác hoặc event không đúng phase không tự kế thừa transaction thread-bound; cache operation có thể thực hiện ngoài transaction mong muốn.

Cần có integration test mô phỏng rollback **thực sự**, không dựa vào các giả định thứ tự proxy.

## 6. Giải pháp 1: transaction-aware CacheManager

Spring Framework cung cấp `TransactionAwareCacheManagerProxy`, một decorator cho `CacheManager`. Nó trả về các `Cache` được bọc bằng `TransactionAwareCacheDecorator` để đồng bộ một số thao tác với Spring-managed transaction.

Các thao tác **`put(key, value)`, `evict(key)`, `clear()`** có thể được **đẩy tới pha after-commit** của một transaction đồng bộ đang hoạt động. Nếu transaction rollback, các thao tác đã đăng ký after-commit này không được thực thi.

Ví dụ cấu hình:

~~~java
@Bean
public CacheManager cacheManager() {
    CacheManager nativeManager =
            new ConcurrentMapCacheManager("prices");
    return new TransactionAwareCacheManagerProxy(nativeManager);
}
~~~

Đây là snippet Spring configuration, cần import `CacheManager`, `ConcurrentMapCacheManager`, `TransactionAwareCacheManagerProxy`, `@Bean`. Nếu đã có cache manager hỗ trợ transaction-awareness thông qua một cách cấu hình riêng, hãy sử dụng cơ chế phù hợp của provider, tránh bọc trùng không cần thiết.

### Timeline khi dùng transaction-aware decorator

~~~text
T1: BEGIN
T1: INSERT A=120
T1: @Cacheable("A") -> miss -> reader thấy A=120
T1: cache.put("A",120) được ĐĂNG KÝ afterCommit
T1: cache trước commit vẫn không có A
T1: ROLLBACK
    -> callback afterCommit KHÔNG chạy
    -> entry A=120 KHÔNG được put

T2: getPrice("A") -> miss -> DB không có A
~~~

Khi transaction **commit thành công**, callback after-commit thực hiện `put`. Thời điểm đó database đã commit, nên tránh lưu kết quả từ transaction đã rollback.

**Cần phân biệt:** trì hoãn một lệnh put không có nghĩa data hiện tại trong method đã “được an toàn”. Caller bên trong transaction vẫn có thể nhận một kết quả đọc từ dữ liệu chưa commit; mục tiêu là **không phát tán kết quả ấy vào cache dùng chung trước commit**.

### 6.1. Giới hạn quan trọng của decorator

Theo Javadoc `TransactionAwareCacheDecorator`:

- Chỉ nhóm thao tác `put`, `evict`, `clear` có cơ chế after-commit nói trên.
- Các thao tác cần hiệu lực ngay như `putIfAbsent` và `evictIfPresent` **không thể được trì hoãn tương tự**. Không dùng chúng rồi suy ra luôn rollback-safe.
- Nếu **không có Spring transaction synchronization phù hợp**, thao tác cache được thực hiện ngay như bình thường.
- Các lookup `get` vẫn truy cập cache hiện tại. Một put bị hoãn có thể làm lần đọc kế tiếp **trong cùng transaction** vẫn nhìn thấy cache miss; cần cân nhắc số lần loader được gọi và các race phát sinh.
- Provider có thể có async semantics, TTL và các đặc tính khác; một decorator không biến tất cả thao tác cache thành giao dịch phân tán.

Đặc biệt, đừng mặc định `Cache.get(key, Callable)` hay mọi API nâng cao đều có cùng cơ chế trì hoãn `put`; cần kiểm tra API và implementation đang dùng.

### 6.2. Trì hoãn evict có thể giảm stale cache nhưng không loại bỏ mọi race

Với `@CacheEvict` hoặc `cache.evict(key)` đi qua decorator, eviction được đăng ký để thực hiện sau commit. Trường hợp transaction rollback, cache có thể giữ entry hiện tại thay vì xóa vô ích. Khi commit, callback mới xóa entry.

Tuy vậy, giữa thời điểm DB commit và eviction thực tế vẫn có cửa sổ concurrency. Với hệ thống yêu cầu consistency mạnh, cần chiến lược phù hợp hơn như versioning, kiểm soát đọc/ghi, invalidation event bền vững, hoặc bỏ cache trên đường nghiệp vụ nhạy cảm.

### 6.3. Không đủ nếu ứng dụng có hai CacheManager khác nhau

Nếu `@Cacheable` dùng manager A (thường), nhưng code evict qua manager B (transaction-aware), việc bọc manager B **không bảo vệ entry do manager A ghi**. Phải chọn đúng manager cho mỗi operation, nhất quán cache name và key.

## 7. Giải pháp 2: afterCommit callback có chủ đích

Khi một nghiệp vụ thay đổi dữ liệu rồi cần xóa cache, có thể đăng ký thao tác invalidation **chỉ sau khi database commit thành công**.

Ví dụ snippet dùng `TransactionSynchronizationManager`:

~~~java
// Trong một phương thức nghiệp vụ đã chạy dưới Spring transaction.
// repository, cacheManager và sku là dependency/đối số thực tế.
repository.updatePrice(sku, newPrice);

if (!TransactionSynchronizationManager.isSynchronizationActive()
        || !TransactionSynchronizationManager.isActualTransactionActive()) {
    throw new IllegalStateException("Expected an active transaction");
}

TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                Cache cache = Objects.requireNonNull(
                        cacheManager.getCache("prices"));
                cache.evict(sku);
            }
        });
~~~

Đây là **snippet tích hợp**, không độc lập. Cần import `TransactionSynchronizationManager`, `TransactionSynchronization`, `Cache`, `Objects` và repository thực tế. Trong code production, cân nhắc ranh giới transaction, lỗi callback, idempotency và event handler. Đừng “fallback evict ngay” nếu nghiệp vụ thật sự yêu cầu after-commit, vì fallback đó có thể lặp lại race ban đầu.

### Khi nào dùng callback?

- Có một hoặc vài key cần invalidate sau khi dữ liệu gốc commit.
- Muốn điều phối logic rõ ràng thay vì để mọi cache operation ngầm được hoãn.
- Sự kiện nội bộ chỉ nên phát sau commit.
- Cần giữ cache nhất quán với thời điểm nghiệp vụ có hiệu lực.

### Các giới hạn

- Callback sau commit thường **không tham gia cùng DB transaction**. Nếu cache/Redis gặp lỗi sau commit, DB không thể tự rollback lại.
- Khi transaction chưa từng commit hoặc bị rollback-only, `afterCommit` sẽ không được gọi.
- Một tác vụ `REQUIRES_NEW` có thể commit độc lập với transaction ngoài; phải xác định muốn invalidation theo **transaction nào**.
- Nếu dùng nested transactions/savepoints, cần kiểm thử thời điểm và phạm vi callback phù hợp.
- Với nhiều instance hoặc yêu cầu giao sự kiện bền vững, nên cân nhắc **transactional outbox** và consumer idempotent thay vì chỉ callback trong RAM.

## 8. Giải pháp 3: @TransactionalEventListener(AFTER_COMMIT)

Spring có `@TransactionalEventListener` để xử lý sự kiện theo pha transaction:

~~~java
// Snippet minh họa, các class nghiệp vụ được ứng dụng định nghĩa.
public record ProductChanged(String sku) {}

@Transactional
public void updatePrice(String sku, int price) {
    repository.updatePrice(sku, price);
    publisher.publishEvent(new ProductChanged(sku));
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onProductChanged(ProductChanged event) {
    Cache cache = Objects.requireNonNull(
            cacheManager.getCache("prices"));
    cache.evict(event.sku());
}
~~~

Snippet không độc lập vì cần service, publisher, repository, cache manager và imports. Khi event được publish trong transaction, listener `AFTER_COMMIT` chỉ chạy khi transaction commit (theo chính sách và cấu hình event listener). Nếu publish **không có transaction**, listener kiểu này mặc định không chạy, trừ khi thiết lập `fallbackExecution=true` có chủ đích.

Chú ý: sau callback commit, các transaction resources có thể còn bound trong một khoảng thời gian; nếu listener cần ghi DB mới, cân nhắc mở transaction mới (`REQUIRES_NEW`) phù hợp. Đừng lạm dụng event listener rồi cho rằng event delivery hoặc cache invalidation đã có bảo đảm exactly-once trong cluster.

## 9. Demo Java 17 + Maven + Spring JDBC + H2

Demo này **cố ý gây rollback** với H2, rồi so sánh hai kiểu cache:

- **UNSAFE:** `ConcurrentMapCacheManager` thông thường; put từ `@Cacheable` xảy ra ngay trước rollback.
- **SAFE:** `TransactionAwareCacheManagerProxy` bọc một manager khác; put được đăng ký after-commit và bị bỏ qua khi rollback.

Ví dụ dùng `TransactionTemplate` để tạo transaction một cách tường minh, tránh phải suy đoán advisor order của `@Transactional`. `@Cacheable` vẫn được Spring kích hoạt qua proxy của reader. Đây là thí nghiệm nhỏ chứng minh **cache và JDBC transaction không tự chung rollback semantics**.

### 9.1. Cấu trúc

~~~text
cache-rollback-demo/
├── pom.xml
└── src/main/java/demo/RollbackCacheDemo.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-rollback-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.16</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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

### 9.3. src/main/java/demo/RollbackCacheDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import javax.sql.DataSource;
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class RollbackCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:rollback_demo;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        // Manager mặc định, KHÔNG biết DB transaction.
        @Bean("cacheManager")
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("unsafe");
        }

        // Manager thứ hai có Cache decorator transaction-aware.
        @Bean("safeCacheManager")
        public CacheManager safeCacheManager() {
            return new TransactionAwareCacheManagerProxy(
                    new ConcurrentMapCacheManager("safe"));
        }

        @Bean
        public PriceReader priceReader(JdbcTemplate jdbc) {
            return new PriceReader(jdbc);
        }
    }

    public static class PriceReader {
        private final JdbcTemplate jdbc;
        private final AtomicInteger unsafeReads = new AtomicInteger();
        private final AtomicInteger safeReads = new AtomicInteger();

        public PriceReader(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Put ngay khi miss, kể cả transaction có thể rollback.
        @Cacheable(
                cacheNames = "unsafe",
                key = "#p0",
                unless = "#result == null")
        public Integer unsafe(String sku) {
            int n = unsafeReads.incrementAndGet();
            return load("UNSAFE", sku, n);
        }

        // Put được trì hoãn tới after-commit nếu transaction đang mở.
        @Cacheable(
                cacheNames = "safe",
                cacheManager = "safeCacheManager",
                key = "#p0",
                unless = "#result == null")
        public Integer safe(String sku) {
            int n = safeReads.incrementAndGet();
            return load("SAFE", sku, n);
        }

        private Integer load(String kind, String sku, int count) {
            List<Integer> values = jdbc.query(
                    "SELECT price FROM prices WHERE sku = ?",
                    (rs, row) -> rs.getInt(1),
                    sku);
            Integer price = values.isEmpty() ? null : values.get(0);
            System.out.println("DB_" + kind + " " + sku + " #"
                    + count + " -> " + price);
            return price;
        }

        public int unsafeReadCount() {
            return unsafeReads.get();
        }

        public int safeReadCount() {
            return safeReads.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PriceReader reader = context.getBean(PriceReader.class);
            PlatformTransactionManager txManager =
                    context.getBean(PlatformTransactionManager.class);
            TransactionTemplate tx = new TransactionTemplate(txManager);

            Cache unsafe = Objects.requireNonNull(
                    context.getBean("cacheManager", CacheManager.class)
                            .getCache("unsafe"));
            Cache safe = Objects.requireNonNull(
                    context.getBean("safeCacheManager", CacheManager.class)
                            .getCache("safe"));

            jdbc.execute("CREATE TABLE prices ("
                    + "sku VARCHAR(20) PRIMARY KEY, "
                    + "price INTEGER NOT NULL)");

            System.out.println("-- UNSAFE ROLLBACK --");
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "INSERT INTO prices(sku, price) VALUES(?, ?)",
                            "A", 120);
                    System.out.println("insideTx="
                            + reader.unsafe("A"));
                    System.out.println("unsafeCacheInTx="
                            + (unsafe.get("A") != null));
                    throw new IllegalStateException("rollback-A");
                });
            } catch (IllegalStateException ex) {
                System.out.println("rollback=" + ex.getMessage());
            }
            System.out.println("dbA="
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM prices WHERE sku = ?",
                            Integer.class, "A"));
            System.out.println("unsafeAfterRollback="
                    + reader.unsafe("A"));
            System.out.println("unsafeReads="
                    + reader.unsafeReadCount());

            System.out.println("-- SAFE ROLLBACK --");
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "INSERT INTO prices(sku, price) VALUES(?, ?)",
                            "B", 130);
                    System.out.println("insideTx="
                            + reader.safe("B"));
                    System.out.println("safeCacheInTx="
                            + (safe.get("B") != null));
                    throw new IllegalStateException("rollback-B");
                });
            } catch (IllegalStateException ex) {
                System.out.println("rollback=" + ex.getMessage());
            }
            System.out.println("dbB="
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM prices WHERE sku = ?",
                            Integer.class, "B"));
            System.out.println("safeCacheAfterRollback="
                    + (safe.get("B") != null));
            System.out.println("safeAfterRollback="
                    + reader.safe("B"));

            System.out.println("-- SAFE COMMIT --");
            tx.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO prices(sku, price) VALUES(?, ?)",
                        "C", 140);
                System.out.println("insideTx="
                        + reader.safe("C"));
                System.out.println("safeCacheBeforeCommit="
                        + (safe.get("C") != null));
            });

            System.out.println("safeCacheAfterCommit="
                    + (safe.get("C") != null));
            System.out.println("safeAfterCommit="
                    + reader.safe("C"));
            System.out.println("safeReads="
                    + reader.safeReadCount());
        }
    }
}
~~~

### 9.4. Chạy

Cần JDK 17+, Maven. Từ thư mục `cache-rollback-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.RollbackCacheDemo
~~~

Stdout **dự kiến do chương trình in** (không bao gồm log Maven/JVM):

~~~text
-- UNSAFE ROLLBACK --
DB_UNSAFE A #1 -> 120
insideTx=120
unsafeCacheInTx=true
rollback=rollback-A
dbA=0
unsafeAfterRollback=120
unsafeReads=1
-- SAFE ROLLBACK --
DB_SAFE B #1 -> 130
insideTx=130
safeCacheInTx=false
rollback=rollback-B
dbB=0
safeCacheAfterRollback=false
DB_SAFE B #2 -> null
safeAfterRollback=null
-- SAFE COMMIT --
DB_SAFE C #3 -> 140
insideTx=140
safeCacheBeforeCommit=false
safeCacheAfterCommit=true
safeAfterCommit=140
safeReads=3
~~~

### 9.5. Đọc từng nhóm kết quả

**UNSAFE rollback**

- `DB_UNSAFE A #1 -> 120`: trong transaction, query thấy row `A=120` chưa commit.
- `unsafeCacheInTx=true`: cache thường đã nhận entry `A` trước commit.
- `rollback=rollback-A` và `dbA=0`: database thực sự rollback, không còn row A.
- `unsafeAfterRollback=120`: lần đọc qua `@Cacheable` vẫn hit cache với 120.
- `unsafeReads=1`: không có query mới ở lần đọc sau rollback; đó chính là lỗi cache chứa dữ liệu bị hủy.

**SAFE rollback**

- `DB_SAFE B #1 -> 130`: method vẫn có thể đọc row B trong transaction.
- `safeCacheInTx=false`: cache transaction-aware chưa put ngay, vì put được đăng ký sau commit.
- `dbB=0`, `safeCacheAfterRollback=false`: transaction rollback, callback put không chạy.
- `DB_SAFE B #2 -> null`: đọc sau rollback thực sự query DB và nhận null. `unless="#result == null"` ngăn lưu cached-null cho lần này.

**SAFE commit**

- `DB_SAFE C #3 -> 140` và `safeCacheBeforeCommit=false`: trong transaction, value chưa được đưa vào cache.
- Khi transaction thành công, callback after-commit chạy: `safeCacheAfterCommit=true`.
- `safeAfterCommit=140` hit cache, không in thêm `DB_SAFE`. Tổng số lần query ở nhánh safe là 3.

### 9.6. Bài học từ demo

Thí nghiệm này không cần `@Transactional` trên method vì `TransactionTemplate` tạo một transaction Spring thật. `JdbcTemplate` lấy connection tham gia transaction thông qua Spring transaction infrastructure, nên query trong callback thấy các thay đổi chưa commit của chính transaction đó.

Method `PriceReader.unsafe`/`safe` **được gọi thông qua bean từ `ApplicationContext`**. Vì vậy `@Cacheable` thực sự chạy qua proxy; nếu tạo object bằng `new`, sẽ không tái hiện cache behavior tương tự.

Demo có H2 in-memory database và ConcurrentMap cache trong cùng JVM; nó chỉ chứng minh **trình tự rollback/after-commit**, không phải test distributed transaction hoặc consistency giữa nhiều replica.

## 10. Ngoài Spring Cache: các chiến lược bảo vệ bổ sung

### 10.1. Tránh cache dữ liệu đọc từ transaction đang thay đổi

Nếu dữ liệu rất nhạy cảm với consistency, hãy xác định những đường đọc diễn ra trong transaction có cập nhật. Có thể chọn **bypass cache** hoặc chỉ nạp/cache dữ liệu ở một tầng đã xác nhận commit. Không nên lấy một value chưa commit rồi đưa sang shared cache chỉ vì method mang `@Cacheable`.

### 10.2. Invalidation theo version

Khi kết quả cache chứa version/generation, reader có thể so sánh version với một nguồn đã commit (hoặc key có version) trước khi dùng. Cách này tăng chi phí nhưng giúp phát hiện entry cũ trong một số thiết kế. Đừng chỉ gắn timestamp mà giả định tự đảm bảo consistency.

### 10.3. Transactional outbox

Nếu transaction commit phải dẫn tới cache invalidation ở nhiều service, có thể **ghi outbox event trong cùng DB transaction**. Một worker sau commit đọc event, retry/idempotent processing và evict cache phân tán. Điều này giúp tránh mất event khi process chết ngay sau commit, nhưng vẫn có độ trễ eventual consistency; cần bảo đảm deduplication và replay.

### 10.4. Chọn TTL phù hợp nhưng không xem là sửa lỗi

TTL làm giới hạn thời gian entry sai tồn tại, **không ngăn** một request nhận dữ liệu chưa commit trong khoảng TTL. Những hệ thống có yêu cầu correctness cao không nên thay after-commit bằng TTL đơn thuần.

### 10.5. Quan sát và phục hồi

Khi phát hiện mismatch DB/cache, cần khả năng evict/clear một vùng đúng key, số liệu hit/miss, log transaction outcome và kiểm tra những key liên quan. Không log secret hoặc dữ liệu cá nhân trực tiếp. Đặt alarm cho cache invalidation failure và có cơ chế retry an toàn.

## 11. Kịch bản kiểm thử bắt buộc

| Kịch bản | Dữ liệu trước | Hành động | Kỳ vọng |
| --- | --- | --- | --- |
| Put rồi rollback, cache thường | DB và cache không có A | Insert A=120, gọi @Cacheable trong transaction, rollback | DB không có A nhưng cache có thể giữ A=120 (chứng minh lỗi) |
| Put rồi rollback, transaction-aware | DB/cache không có B | Insert B=130, @Cacheable trong tx, rollback | DB/cache cùng không có B |
| Put rồi commit, transaction-aware | DB/cache không có C | Insert C=140, @Cacheable trong tx, commit | Cache nhận C=140 sau commit |
| Evict trước commit, reader khác | DB A=100, cache A=100 | T1 sửa A=120 chưa commit, evict, T2 miss/reload 100, T1 commit | Có nguy cơ cache stale A=100 |
| Evict after-commit | DB A=100, cache A=100 | T1 sửa A=120 rồi commit, sau đó evict | Tăng khả năng lần đọc sau nạp đúng 120; vẫn cần test race |
| Rollback-only ở tầng ngoài | DB/cache ổn định | Method con kết thúc, outer rollback-only | Không đưa value chưa commit vào cache |
| Checked exception | DB/cache ổn định | Throw checked exception | Xác minh cấu hình rollbackFor nếu mong rollback |
| Self-invocation | Service tự gọi method annotated | `this.method()` | Có thể bypass cả cache/transaction proxy |
| Multiple cache managers | Manager thường + manager transaction-aware | Cấu hình annotation nhầm manager | Entry có thể không được bảo vệ |
| putIfAbsent/evictIfPresent | Transaction đang mở | Dùng operation immediate | Không mặc định được defer after-commit |
| Sau commit backend cache lỗi | DB đã chốt | afterCommit evict thất bại | DB không tự rollback; cần retry/reconcile |
| Multi-node | Cache local ở nhiều replica | One node evict | Node khác có thể vẫn stale |

**Không chỉ assert kết quả nghiệp vụ**. Một integration test phải so sánh:

1. **DB state sau rollback** bằng query ngoài transaction.
2. **Cache entry** đang có hoặc không có sau rollback.
3. **Số lần loader thực thi** (để biết hit từ cache hay query lại DB).
4. **Dữ liệu ở lần gọi kế tiếp** qua proxy cache.
5. **Kết quả commit** trong case khác rollback.

Với database/provider production, nên có test mô phỏng concurrency giữa writer chưa commit và reader ngoài transaction, vì demo tuần tự chỉ xác minh một loại lỗi.

## 12. Lỗi hiểu nhầm thường gặp

**“Có @Transactional nên nếu DB rollback thì cache cũng rollback”.** Sai. `@Transactional` không tự enlist `ConcurrentMapCache`/Redis/Caffeine vào database transaction. Phải có cách phối hợp cache operation riêng.

**“Chỉ @CachePut mới có rủi ro put trước commit”.** Sai. `@Cacheable` miss cũng có thể put kết quả, kể cả kết quả đọc từ database chưa commit.

**“beforeInvocation=false của @CacheEvict nghĩa là luôn sau commit”.** Sai. Nó là sau invocation thành công ở cache interceptor, không phải bảo đảm DB commit. Outer transaction vẫn có thể chưa kết thúc.

**“Rollback xảy ra thì cache sẽ tự refresh lại”.** Không. Cache không tự biết transaction bị rollback, trừ khi application/provider có phối hợp phù hợp.

**“Đưa eviction vào finally là an toàn”.** Không. `finally` chạy cả khi transaction rollback, và có thể xóa cache quá sớm. Nếu muốn chỉ sau commit, dùng một cơ chế ràng buộc commit rõ ràng.

**“TransactionAwareCacheManagerProxy biến cache thành transaction XA”.** Không. Nó dùng synchronization để hoãn một số thao tác tới after-commit; không đem lại atomic commit xuyên DB/cache hoặc bền vững trước process crash.

**“@Cacheable + transaction-aware bảo đảm các lần gọi trong cùng transaction đều hit”.** Không. Deferred put chưa xuất hiện trong cache cho tới after-commit, nên cùng key có thể được tải nhiều lần trước commit.

**“putIfAbsent và evictIfPresent luôn được rollback-safe như put và evict”.** Không. API immediate không thể được defer giống như những thao tác thường.

**“Sửa advisor order là đủ”.** Chưa chắc. Transaction ngoài, async flow hoặc cách gọi khác vẫn có thể làm cache operation xảy ra trước outer commit.

## 13. Câu hỏi tự kiểm tra

**1. Tại sao DB chạy READ_COMMITTED mà vẫn có thể trả dữ liệu chưa commit từ cache?** Vì cache không kế thừa isolation của DB; transaction đã đưa uncommitted value vào shared cache sớm.

**2. Có thể tạo cache pollution chỉ bằng @Cacheable không?** Có. Khi cache miss, loader có thể đọc dữ liệu chưa commit rồi kết quả bị put ngay.

**3. Điều gì xảy ra khi transaction-aware cache nhận lệnh put nhưng DB rollback?** Nếu lệnh put thuộc nhóm được hoãn và đồng bộ transaction phù hợp, callback after-commit không chạy; entry đó không được đưa vào cache.

**4. Vì sao evict ngay trong transaction có thể khiến cache stale ngay cả khi commit thành công?** Reader khác có thể miss, đọc bản DB cũ trước commit và repopulate entry cũ; commit không tự evict lần thứ hai.

**5. Khi nào @TransactionalEventListener(AFTER_COMMIT) phù hợp?** Khi cần phát tác vụ sau DB commit thành công. Phải hiểu transaction context, fallback policy, delivery và lỗi sau commit.

**6. Transaction-aware decorator có trì hoãn mọi API Cache không?** Không. Các operation immediate như putIfAbsent/evictIfPresent và những API nâng cao có semantics khác; cần đọc Javadoc/provider.

**7. Nếu afterCommit callback evict Redis thất bại thì DB có rollback không?** Không. DB đã commit, cần retry hoặc reconciliation thay vì kỳ vọng atomic rollback.

**8. Điều gì phải kiểm tra khi dùng nhiều CacheManager?** Annotation và API programmatic phải dùng đúng manager/region/key, và manager cần transaction-awareness ở chính đường thao tác được yêu cầu.

## 14. Kết luận

Rủi ro “**cache dữ liệu sau đó bị rollback**” xuất hiện khi ứng dụng cho phép **cache operation trở nên hiển thị trước khi số phận database transaction được quyết định**. `@Cacheable` có thể put uncommitted value sau miss; `@CacheEvict` quá sớm có thể mở cửa cho reader repopulate dữ liệu cũ. Cả hai đều là lỗi timing/consistency giữa hai hệ thống trạng thái độc lập.

Nguyên tắc thực hành:

- Đừng coi `@Transactional` là cơ chế rollback tự động cho cache.
- Với cache write/invalidation cần phụ thuộc kết quả giao dịch, hãy cân nhắc `TransactionAwareCacheManagerProxy` hoặc callback/event **after commit**.
- Phân biệt rõ **cache put trên rollback** với **early evict và race repopulation**.
- Hiểu giới hạn: callback sau commit không phải distributed transaction; các operation immediate và async vẫn có rủi ro.
- Kiểm chứng bằng DB sau rollback, entry cache, loader count và concurrency test.

## 15. Tài liệu chính thức

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Declarative @Transactional: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — TransactionAwareCacheDecorator Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework — TransactionAwareCacheManagerProxy Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html
- Spring Framework — TransactionSynchronization Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html

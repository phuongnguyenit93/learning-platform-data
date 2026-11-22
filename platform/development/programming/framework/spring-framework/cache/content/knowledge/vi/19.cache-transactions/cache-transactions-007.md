# Giao dịch cơ sở dữ liệu không tự làm cache phân tán nguyên tử

## Mục tiêu học tập

**@Transactional bảo vệ công việc của transaction manager được cấu hình; nó không tự tạo một giao dịch ACID chung giữa database và hệ thống cache phân tán.** Khi một service cập nhật dữ liệu trong PostgreSQL/MySQL rồi ghi hoặc xóa một key Redis, đây là **hai hệ thống với hai ranh giới commit khác nhau**. Dù cả hai thao tác đều được viết bên trong cùng một phương thức Java, thành công ở hệ thống này không buộc hệ thống còn lại thành công hoặc rollback theo.

Sau bài học, bạn sẽ:
1. Phân biệt **database transaction**, **Spring transaction synchronization**, **cache operation** và **giao dịch phân tán thật sự**.
2. Phân tích được các tình huống **DB rollback nhưng cache đã thay đổi**, **DB commit nhưng cập nhật cache thất bại**, **xóa cache quá sớm**, **request đọc cũ ghi lại cache sau eviction**, và **hai writer đến không đúng thứ tự**.
3. Hiểu vì sao **@Transactional + @CachePut/@CacheEvict** không tự đảm bảo tính nguyên tử xuyên database và Redis.
4. Dùng đúng **TransactionAwareCacheManagerProxy**, **TransactionAwareCacheDecorator** hoặc transaction-aware CacheManager để hoãn một số thao tác cache tới **after-commit**; nắm rõ giới hạn của chúng.
5. Nhận biết khi nào phải dùng **transactional outbox**, retry/idempotency, version/CAS, TTL, read validation, reconciliation hoặc bỏ cache khỏi một đường quyết định quan trọng.
6. Chạy ví dụ **Java 17 + Spring Framework 6.2 + H2** chứng minh rollback của database **không rollback Cache.put thông thường**, đồng thời kiểm chứng lợi ích và giới hạn của transaction-aware cache.

Trọng tâm của bài là **tính nguyên tử và nhất quán giữa database với cache**, không phải cấu hình riêng cho một Redis client hay hướng dẫn XA/2PC đầy đủ. Trong ví dụ runnable, cache in-memory được dùng để kiểm chứng ranh giới transaction một cách xác định; phần hệ thống phân tán được phân tích bằng timeline và kiến trúc production.

---

## 1. Một phương thức có hai nơi lưu không trở thành một giao dịch duy nhất

Giả sử một API cập nhật giá sản phẩm:

~~~java
@Transactional
public void updatePrice(String sku, int newPrice) {
    productRepository.updatePrice(sku, newPrice); // Database
    redisCache.put(sku, newPrice);                 // Cache ngoài DB
}
~~~

Đây là **mã minh họa**, chưa phải chương trình độc lập. **redisCache** là một đối tượng truy cập cache giả định; productRepository và các import phải được ứng dụng cung cấp. Việc cache được gọi trong thân method không chứng minh nó tham gia cùng database transaction.

Sơ đồ tài nguyên:

~~~text
HTTP request
    |
    v
Spring transaction interceptor (@Transactional)
    |
    +---- JDBC/JPA connection ----> DATABASE
    |                               BEGIN/UPDATE/COMMIT/ROLLBACK
    |
    +---- CacheManager/Redis -----> DISTRIBUTED CACHE
                                    SET / DEL / TTL / network
                                    (không mặc nhiên thuộc JDBC tx)
~~~

**Transaction manager** của ứng dụng chỉ phối hợp những tài nguyên được nó quản lý và các resource synchronization được khai báo phù hợp. Ví dụ DataSourceTransactionManager hoặc JpaTransactionManager quản lý transaction database theo contract của chúng. Redis không tự trở thành một enlisted XA resource vì code gọi RedisTemplate hay Cache.put bên trong method có @Transactional.

Cần phân biệt:
- **Cùng thread** không đồng nghĩa **cùng transaction vật lý**.
- **Cùng Spring bean/service method** không đồng nghĩa **hai hệ thống cùng rollback**.
- **Cùng dùng từ “transaction”** không có nghĩa transaction ở DB và Redis là một distributed commit protocol.
- **Redis MULTI/EXEC hoặc Redis Lua script** có thể nguyên tử đối với một chuỗi thao tác trong phạm vi Redis phù hợp, nhưng không tự bao gồm một JDBC commit.
- **Spring Cache abstraction** thiết kế cho caching, không tuyên bố là một transaction coordinator phân tán.

### Định nghĩa nguyên tử xuyên hai tài nguyên

Với cập nhật **DB=D2** và cache **C=C2**, hệ thống nguyên tử thực sự phải tránh trạng thái một nửa đã ghi như:

~~~text
DB = D2, Cache = C1     (DB mới, cache cũ)
DB = D1, Cache = C2     (DB cũ, cache mới)
~~~

Khi dữ liệu cache được phép stale, hai trạng thái này có thể tạm tồn tại theo hợp đồng **eventual consistency**. Nhưng **không** được mô tả chúng là “một transaction ACID”. Nếu nghiệp vụ bắt buộc *mọi read đều thấy bản mới ngay sau write*, cần một giao thức và giả định mạnh hơn caching mặc định.

## 2. Bài toán dual write: khi một trong hai nơi thất bại

Một yêu cầu ứng dụng thường thực hiện hai side effect:

~~~text
WRITE #1: cập nhật database
WRITE #2: ghi hoặc xóa cache / phát sự kiện invalidation
~~~

Hai write là **dual write**. Nếu không có coordinator giao dịch chung, lỗi hoặc crash có thể xảy ra **giữa** hai thao tác.

### Tình huống A — cache được cập nhật trước, DB rollback

~~~text
Database ban đầu: account A = v1
Cache ban đầu:    account A = v1

T1: BEGIN DB transaction
T2: UPDATE account A = v2 trong DB transaction (chưa commit)
T3: cache.put(A, v2) thành công và có thể thấy từ request khác
T4: DB transaction ROLLBACK do lỗi nghiệp vụ / lỗi commit

Kết quả: DB = v1, Cache = v2   <-- cache chứa trạng thái không commit
~~~

Cache không được rollback chỉ vì database rollback. Trường hợp này có thể lộ dữ liệu chưa cam kết cho các caller khác. Cách ghi sau commit hoặc transaction-aware decorator giúp giảm **nhóm lỗi trước-commit** này.

### Tình huống B — DB commit trước, ghi cache lỗi

~~~text
Database ban đầu: order O = APPROVED
Cache ban đầu:    order O = APPROVED

T1: DB UPDATE order O = CANCELED
T2: DB COMMIT thành công
T3: cache.put(O, CANCELED) / cache.evict(O) gọi Redis
T4: timeout / cache unavailable / network partition

Kết quả: DB = CANCELED, Cache = APPROVED   <-- stale
~~~

Việc dời cache operation đến sau commit **không loại bỏ T3–T4**. Nếu gọi lại API sau lỗi, một command nghiệp vụ không idempotent có thể bị thực thi lần hai. Cần phân biệt lỗi “database chưa commit” với lỗi “database **đã commit nhưng cache không theo kịp**”.

### Tình huống C — xóa cache trước commit, reader nạp lại giá trị cũ

~~~text
Writer                         Reader
-----------------------------  ------------------------------
BEGIN, DB update V2 chưa commit
evict cache key K
                               cache MISS K
                               DB isolation cho thấy V1
                               cache.put(K, V1)
DB COMMIT V2
Kết quả cache có thể giữ V1
~~~

Đổi thành **@CacheEvict(beforeInvocation=true)** có thể làm cửa sổ này rộng hơn; nó **không** tự khép lại race condition. Với Spring @CacheEvict mặc định (beforeInvocation=false), thời điểm eviction tương đối với method invocation, **không nhất thiết sau database commit**.

### Tình huống D — xóa sau commit nhưng reader cũ ghi lại

~~~text
Reader R đọc snapshot V1, đang xử lý chậm
Writer W COMMIT V2 rồi evict K
Reader R hoàn tất @Cacheable MISS và put(K, V1)
Sau đó caller khác HIT V1, dù DB đã là V2
~~~

Đây là **stale repopulation**: eviction đúng lúc chưa đủ vì còn reader in-flight. Muốn ngăn hoàn toàn cần kiểm soát loader, version hoặc phối hợp theo key. Chỉ hoãn evict tới after-commit không tự cấm một request khác put lại snapshot cũ.

### Tình huống E — ghi cache thành công nhưng ứng dụng mất phản hồi

~~~text
DB COMMIT thành công
Cache EVICT thành công
Process crash trước khi trả HTTP 200
Client tưởng request thất bại và retry
~~~

Đây là lý do **idempotency key**, optimistic version và khả năng đọc lại trạng thái sau lỗi quan trọng, ngay cả khi thao tác cache và database riêng lẻ đều thành công.

## 3. @Transactional thực sự cam kết điều gì?

Trong cấu hình thông thường, **@Transactional** kích hoạt advice của Spring Transaction Management khi annotation được enable và lời gọi qua proxy/AspectJ phù hợp. Transaction manager sẽ:
1. Mở hoặc tham gia transaction quản lý bởi tài nguyên được chọn.
2. Cho phép code nghiệp vụ thực thi.
3. Commit khi điều kiện thành công và không đánh dấu rollback-only.
4. Rollback theo rule của transaction interceptor khi exception thuộc diện rollback hoặc status được đánh dấu rollback-only.

Điểm cần nhớ:
- **RuntimeException và Error** thường khiến Spring rollback theo default; **checked exception** không tự rollback nếu chưa cấu hình rollbackFor hoặc rule tương đương.
- Lỗi **commit-time** có thể xuất hiện **sau khi thân method đã return**, ví dụ constraint được kiểm tra khi flush/commit.
- Một lệnh viết cache thường **không nằm trong JDBC resource**; nếu không được nối bằng transaction synchronization hoặc cơ chế giao dịch thực sự, transaction manager không undo cache put.
- Ở **proxy mode**, self-invocation qua **this.method()** có thể không đi qua @Transactional hoặc @CacheEvict advisor như dự kiến.
- @Transactional không biến việc gọi **phương thức từ một thread khác, một async task hoặc một HTTP request khác** thành cùng transaction; transaction context thường gắn với thread/scope nhất định.

### Thứ tự advisor gây bất ngờ

Khi cùng method có:

~~~java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0")
public void update(String sku, ProductUpdate input) {
    repository.update(sku, input);
}
~~~

Đây là snippet minh họa, không độc lập. Spring AOP có thể gắn **transaction advisor** và **cache advisor**. Theo thứ tự advice thực tế, cache eviction có thể được yêu cầu:
- Trong một transaction đang active, **trước khi database commit**, hoặc
- Sau khi một inner transactional invocation hoàn tất.

**Không suy từ thứ tự hai dòng annotation trong file Java** rằng cache chắc chắn chạy sau commit. Thứ tự advisor và việc cache manager có transaction awareness hay không mới quyết định hành vi. Nếu không đặt thứ tự, một số advisor có mặc định cùng mức ưu tiên; không nên biến điều đó thành một contract.

## 4. Spring Cache annotations không cung cấp distributed commit

| Annotation | Ý nghĩa ở lớp cache | Không bảo đảm |
| --- | --- | --- |
| **@Cacheable** | Cache HIT có thể bỏ qua thực thi method; MISS tải và put result | Không biết database transaction của writer khác đã commit chưa |
| **@CachePut** | Thực thi method rồi put result theo điều kiện | Không tự có DB+cache atomicity hoặc version compare |
| **@CacheEvict** | Evict key/region khi operation đến thời điểm được cấu hình | Không ngăn stale loader put lại sau eviction |
| **@Caching** | Gom nhiều operation cache cho một method | Không biến nhiều cache regions thành một transaction |
| **@CacheConfig** | Mặc định cacheNames/manager/resolver/keyGenerator ở lớp | Không quản lý transaction database |

**@CacheEvict(beforeInvocation=false)** là mặc định: thông thường evict **sau khi method hoàn thành thành công**. **beforeInvocation=true** yêu cầu evict trước method, ngay cả khi method sau đó lỗi. Đối với reactive/CompletableFuture ở các phiên bản Spring hỗ trợ, after-invocation có xử lý thời điểm completion riêng; đừng dùng code đồng bộ để suy luận bừa cho reactive transaction.

**Lỗi thường gặp:** viết @Transactional trên update rồi nhìn thấy @CacheEvict trên cùng method, sau đó khẳng định “Spring chắc chắn sẽ rollback cả Redis DEL khi DB rollback”. Không có bảo đảm tổng quát như vậy.

## 5. Hoãn put/evict đến after-commit với transaction-aware cache

Spring cung cấp **TransactionAwareCacheDecorator** và **TransactionAwareCacheManagerProxy**, ngoài ra một số CacheManager hỗ trợ transaction-aware trực tiếp. Những công cụ này dùng **Spring TransactionSynchronizationManager** để phối hợp thao tác cache với transaction đang active.

Với decorator được cấu hình đúng:
- **Cache.put(key, value)** được **hoãn thực thi thật đến after-commit** nếu có Spring-managed transaction active.
- **Cache.evict(key)** được hoãn tương tự.
- **Cache.clear()** cũng có thể được hoãn.
- Nếu transaction **rollback**, các thao tác thông thường được hoãn sẽ **không được áp dụng như một kết quả after-commit thành công**.
- Nếu **không có transaction active**, các thao tác được thực hiện ngay như thường lệ.

~~~text
BEGIN DB transaction
UPDATE row A=v2
transactionAwareCache.put(A, v2)
  -> đăng ký afterCommit callback, chưa put vào cache thực
COMMIT DB thành công
  -> afterCommit callback gọi cache thực .put(A, v2)
~~~

**Đây là phối hợp sau commit, không phải two-phase commit.** Nếu callback put Redis thất bại, database **đã commit rồi**. Spring không thể rollback lại transaction đã commit chỉ vì một cache operation sau commit gặp lỗi.

### Dùng TransactionAwareCacheManagerProxy

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;

CacheManager raw = new ConcurrentMapCacheManager("accounts");
CacheManager transactionAware =
    new TransactionAwareCacheManagerProxy(raw);
~~~

Đoạn này là Java cấu hình minh họa. Có thể đăng ký **transactionAware** làm CacheManager bean được application sử dụng, hoặc wire nó vào service cần semantics này. Không nên vừa inject raw vừa inject wrapped manager một cách tùy tiện nếu mong mọi đường cập nhật cache đều đi qua decorator.

### API nào KHÔNG được hoãn như put/evict thông thường?

Theo hợp đồng **TransactionAwareCacheDecorator**, các operation phải có phản hồi ngay như:
- **Cache.putIfAbsent(...)**
- **Cache.evictIfPresent(...)**

**Không thể mặc định defer các operation này tới after-commit**. Chúng có thể thực thi ngay vì caller cần kết quả ngay. Tương tự, **Cache.invalidate()** có hợp đồng xóa ngay, khác **Cache.clear()** có thể deferred. Các API loader, retrieval async và operation của từng provider cần được xem theo contract riêng, không khẳng định mọi method của Cache đều transaction-aware.

**Cảnh báo quan trọng:** “bật transaction-aware” không đồng nghĩa mọi cache API là transaction-safe, và cũng không tự làm **read của chính transaction đó** thấy một put chưa commit. Một Cache.get có thể vẫn quan sát state cũ trong khi transaction đã đăng ký put mới để chạy sau commit.

### Transaction-aware không có tác dụng nếu bạn bỏ qua wrapper

Nếu cấu hình cache manager đã được wrap nhưng service lại tự lấy **native Redis connection** hoặc bean **rawManager** để ghi trực tiếp, các thao tác đó không được decorator bảo vệ. Kiểm tra đúng bean được Spring cache interceptor/logic programmatic sử dụng.

## 6. Hai thuộc tính “sau commit” và “nguyên tử” là khác nhau

Giả sử transaction-aware decorator hoàn toàn hoạt động:

~~~text
Bước 1: BEGIN DB
Bước 2: UPDATE DB to V2
Bước 3: đăng ký callback evict(K)
Bước 4: COMMIT DB thành công
Bước 5: kết nối Redis bị timeout
Bước 6: callback evict(K) thất bại
~~~

**Kết quả:** DB có V2 nhưng cache còn có thể V1.

Vì vậy, sau-commit giải quyết tốt hai lỗi nhất định:
- Không đưa value chưa commit vào cache quá sớm qua **put** được hoãn.
- Không evict một entry chỉ vì một transaction **cuối cùng rollback**, nếu eviction được hoãn và rollback không chạy callback sau commit.

Nhưng nó **không giải quyết**:
- Lỗi cache khi DB đã commit.
- Crash tiến trình giữa commit DB và callback.
- Cache availability / network partition.
- Hai producer ghi version đảo thứ tự.
- Reader đang load V1 put lại sau khi evict V2.
- Invalidation giữa nhiều cache local L1 và một shared cache L2.
- Event gửi tới broker nhưng không được consumer xử lý.
- Client retry vì response lỗi sau khi transaction đã commit.

**Quy tắc thiết kế:** Nếu mục tiêu là “cache theo DB sau khi commit trong điều kiện bình thường”, transaction-aware là một lớp bảo vệ hữu ích. Nếu mục tiêu là “DB và cache luôn thay đổi đồng thời hoặc không bên nào thay đổi”, transaction-aware **không đáp ứng** yêu cầu đó.

## 7. Ví dụ chạy được: H2 rollback, cache thông thường và cache after-commit

Chương trình này cho thấy một cách **kiểm chứng bằng thao tác thật**, không chỉ dựa vào lý thuyết:

1. Thao tác cache **trực tiếp** trong DB transaction được áp dụng ngay, nên DB rollback mà cache vẫn có V2.
2. Thao tác **TransactionAwareCacheManagerProxy** được hoãn, nên transaction rollback không để lại một put.
3. Khi commit, put được thực thi sau commit; trong transaction, underlying cache vẫn trống.
4. Sau khi DB commit V5, chương trình **cố tình giả lập cache outage**; DB thành V5 còn cache giữ V4, chứng minh after-commit vẫn có khoảng thất bại.
5. Một lệnh evict được hoãn trong transaction: cache V4 vẫn hiển thị trước commit và mất sau commit.

**Quan trọng:** Demo dùng **ConcurrentMapCacheManager trong một JVM** để quan sát timing chính xác. Nó **không mô phỏng một Redis server thật**, nhưng minh họa đúng vấn đề logical dual write và contract của Spring transaction-aware decorator. Lỗi cache ở mục 4 được **inject có chủ đích**, không phải sự cố provider tự phát sinh.

### 7.1. Cấu trúc thư mục

~~~text
db-cache-not-atomic/
├── pom.xml
└── src/main/java/demo/DbCacheAtomicityDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>db-cache-not-atomic</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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

Đây là **Spring Framework thuần**, không cần Spring Boot hoặc Redis. **spring-jdbc** cung cấp JdbcTemplate, DriverManagerDataSource và DataSourceTransactionManager; **spring-context** cung cấp Cache abstraction, ConcurrentMapCacheManager và transaction-aware cache proxy theo các module chuyển tiếp của Spring Framework. H2 là database JDBC có rollback thật, chỉ nằm trong bộ nhớ để bài tập không cần cài database server.

### 7.3. src/main/java/demo/DbCacheAtomicityDemo.java

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Objects;

public class DbCacheAtomicityDemo {

    private static String dbValue(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT value_text FROM accounts WHERE id = ?",
            String.class, "A");
    }

    // Fault injection: không gọi cache thật, cố ý mô phỏng
    // lệnh cache write sau DB commit gặp lỗi mạng.
    private static void simulateCacheOutage(
            Cache cache, String key, String value) {
        throw new IllegalStateException("simulated-cache-outage");
    }

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:cache_tx_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.execute(
            "CREATE TABLE accounts (" +
            "id VARCHAR(20) PRIMARY KEY, " +
            "value_text VARCHAR(50) NOT NULL)");
        jdbc.update(
            "INSERT INTO accounts (id, value_text) VALUES (?, ?)",
            "A", "v1");

        TransactionTemplate tx = new TransactionTemplate(
            new DataSourceTransactionManager(ds));

        ConcurrentMapCacheManager rawManager =
            new ConcurrentMapCacheManager("accounts");
        Cache raw = Objects.requireNonNull(
            rawManager.getCache("accounts"));

        CacheManager awareManager =
            new TransactionAwareCacheManagerProxy(rawManager);
        Cache aware = Objects.requireNonNull(
            awareManager.getCache("accounts"));

        // A. Cùng code path nhưng cache raw không tham gia
        // DB rollback -> "ghost" v2 trong cache.
        raw.put("A", "v1");
        tx.execute(status -> {
            jdbc.update(
                "UPDATE accounts SET value_text = ? WHERE id = ?",
                "v2", "A");
            raw.put("A", "v2"); // Có hiệu lực ngay.
            status.setRollbackOnly();
            return null;
        });
        System.out.println("unsafe-rollback-db=" + dbValue(jdbc));
        System.out.println("unsafe-rollback-cache="
            + raw.get("A", String.class));

        // B. Wrapper hoãn put: rollback => không ghi.
        raw.evict("A");
        tx.execute(status -> {
            jdbc.update(
                "UPDATE accounts SET value_text = ? WHERE id = ?",
                "v3", "A");
            aware.put("A", "v3"); // Chỉ đăng ký afterCommit.
            System.out.println("aware-during-rollback-cache="
                + raw.get("A", String.class));
            status.setRollbackOnly();
            return null;
        });
        System.out.println("aware-rollback-db=" + dbValue(jdbc));
        System.out.println("aware-rollback-cache="
            + raw.get("A", String.class));

        // C. COMMIT => put chạy sau commit.
        tx.execute(status -> {
            jdbc.update(
                "UPDATE accounts SET value_text = ? WHERE id = ?",
                "v4", "A");
            aware.put("A", "v4");
            System.out.println("aware-during-commit-cache="
                + raw.get("A", String.class));
            return null;
        });
        System.out.println("aware-commit-db=" + dbValue(jdbc));
        System.out.println("aware-commit-cache="
            + raw.get("A", String.class));

        // D. DB commit V5, còn cache update giả lập bị lỗi.
        tx.execute(status -> {
            jdbc.update(
                "UPDATE accounts SET value_text = ? WHERE id = ?",
                "v5", "A");
            return null;
        });
        try {
            simulateCacheOutage(raw, "A", "v5");
        } catch (IllegalStateException ex) {
            System.out.println("cache-outage=" + ex.getMessage());
        }
        System.out.println("after-outage-db=" + dbValue(jdbc));
        System.out.println("after-outage-cache="
            + raw.get("A", String.class));

        // E. Hoãn evict cho tới sau khi transaction commit.
        tx.execute(status -> {
            aware.evict("A");
            System.out.println("evict-during-commit-cache="
                + raw.get("A", String.class));
            return null;
        });
        System.out.println("evict-after-commit-cache="
            + raw.get("A", String.class));
    }
}
~~~

### 7.4. Chạy chương trình

Yêu cầu JDK 17+ và Maven, từ thư mục có **pom.xml**:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.DbCacheAtomicityDemo
~~~

**Stdout kỳ vọng do các System.out.println tạo ra**, không tính logging riêng của Maven, Spring hoặc JDBC:

~~~text
unsafe-rollback-db=v1
unsafe-rollback-cache=v2
aware-during-rollback-cache=null
aware-rollback-db=v1
aware-rollback-cache=null
aware-during-commit-cache=null
aware-commit-db=v4
aware-commit-cache=v4
cache-outage=simulated-cache-outage
after-outage-db=v5
after-outage-cache=v4
evict-during-commit-cache=v4
evict-after-commit-cache=null
~~~

### 7.5. Phân tích kết quả

**A – DB rollback, cache raw không rollback.** H2 UPDATE v2 trong transaction chưa được commit, nhưng **raw.put("A","v2")** có hiệu lực ngay. Khi status.setRollbackOnly() khiến transaction rollback, DB quay lại v1, cache giữ v2. Đây là **mâu thuẫn được tái hiện**, không phải bug của ConcurrentMapCache.

**B – Transaction-aware put bị bỏ khi rollback.** Sau khi xóa key cũ, **aware.put("A","v3")** được đăng ký để chạy sau commit. Trong transaction, đọc underlying raw cache thấy null. Vì DB rollback nên callback afterCommit không thực hiện put, DB vẫn v1 và cache vẫn trống.

**C – Sau commit, put được thực hiện.** Trong transaction, raw cache vẫn trống. Khi H2 commit v4 thành công, Spring chạy afterCommit và raw cache nhận v4. Khi lệnh tx.execute trả về cho main, cả DB lẫn cache chứa v4 trong tình huống thành công này.

**D – Khe hở không bị transaction-aware loại bỏ.** UPDATE v5 đã commit. Chương trình cố ý ném exception để **giả lập lệnh ghi cache sau commit bị hỏng**. DB đã v5 nhưng cache vẫn v4. Đây là fault injection, không chứng minh rằng cache real sẽ luôn lỗi; nó chứng minh chỉ cần một failure ở khe hở này đã đủ để phá “atomic across DB and cache”.

**E – Eviction cũng có thể được hoãn.** Khi gọi **aware.evict("A")** trong transaction active, underlying raw cache vẫn hiện v4 trước commit. Sau commit, callback xóa entry; raw.get trả null. Điều này chứng minh after-commit timing cho **evict** nhưng không giải quyết mọi race concurrent reader khác.

### 7.6. Giới hạn và cách đưa demo gần production

- H2 có transaction rollback thật; cache là local map nên không mô phỏng độ trễ mạng, failover hoặc replication Redis.
- Không dùng **@Transactional** để tránh đưa một proxy khác vào đường test; dùng **TransactionTemplate** trực tiếp để xác định ranh giới BEGIN/COMMIT/ROLLBACK. Contract transaction là cùng Spring Transaction Management.
- Với ứng dụng thật, cần dùng transaction manager của JDBC/JPA đang lưu dữ liệu, và chắc chắn code lấy Cache qua manager đã được wrap.
- Khi dùng **@Cacheable/@CachePut/@CacheEvict**, cần **@EnableCaching** và gọi qua Spring proxy; chỉ dùng Cache API programmatic như demo thì không cần @EnableCaching.
- Trong một hệ thống Redis thật, viết thêm test có **Testcontainers**, fault injection/ngắt kết nối Redis, retry và hai instance ứng dụng. Kết quả của local map không thể thay thế kiểm thử provider thật.

## 8. Redis transaction và database transaction là hai miền khác nhau

Redis có cơ chế **MULTI/EXEC** hoặc script để phối hợp thao tác trong phạm vi Redis. Nhưng:

~~~text
RDBMS: BEGIN -> UPDATE -> COMMIT
Redis: MULTI -> SET/DEL -> EXEC

Không có mặc định một COMMIT duy nhất quyết định
cả hai nhánh thành công hoặc cả hai nhánh rollback.
~~~

Ngay cả khi mỗi hệ thống có atomic operation riêng, **composing two atomic operations is not automatically atomic**.

Một Redis command **SET** có thể được thực thi nguyên tử theo semantics Redis, nhưng thao tác **UPDATE PostgreSQL → SET Redis** vẫn có khoảng crash/failure giữa chúng. Nếu ứng dụng có Redis cache phân tán chia sẻ cho nhiều node, tất cả node đều có thể đọc một entry đã cập nhật quá sớm hoặc stale sau commit.

**Lưu ý:** Không đồng nhất Redis cache với Redis transaction support của một Redis client; thậm chí trong một client, Spring CacheManager có thể dùng một path khác với RedisTemplate được cấu hình transaction support. Luôn kiểm tra đúng bean/provider và API đang gọi.

### Vì sao một distributed lock vẫn chưa tạo atomicity?

Giả sử service khóa key K để chỉ một writer chạy:

~~~text
acquire distributed lock K
UPDATE DB K = V2
COMMIT DB
Redis SET K = V2  <-- fail
release lock K
~~~

Lock có thể ngăn một số interleaving giữa các writer hợp tác, nhưng vẫn **không rollback DB nếu SET thất bại**. Lock expiration, lease renewal, crash và stale lock owner còn thêm rủi ro. Distributed lock là công cụ **coordination**, không phải replacement cho distributed commit.

## 9. Xác định hợp đồng nhất quán trước khi chọn giải pháp

Hãy viết rõ yêu cầu thay vì chỉ nói “cache phải chính xác”:

| Mức kỳ vọng | Ý nghĩa | Gợi ý lựa chọn |
| --- | --- | --- |
| **Best-effort cache** | Có thể thấy dữ liệu cũ ngắn hạn | TTL, after-commit invalidation, metrics |
| **Eventual consistency** | Nếu cập nhật ngừng và hệ thống hồi phục, cache dần theo DB | Outbox/event retry, idempotent consumer, reconciliation |
| **Read-your-writes** | Cùng caller sau khi write thành công thấy kết quả của mình | Bypass cache khi cần, version token/session context, synchronous authoritative read |
| **Monotonic reads** | Không chuyển từ phiên bản mới về phiên bản cũ | Version-aware read/cache update, stale response rejection |
| **Linearizable read-after-write** | Mọi read bắt đầu sau khi write hoàn thành phải thấy bản mới theo hợp đồng | Phối hợp mạnh hơn hoặc không dùng cache thiếu bảo đảm trên đường quan trọng |
| **Atomic multi-resource commit** | DB và cache cùng commit/rollback như một tài nguyên | Cần giao thức/tài nguyên hỗ trợ distributed transaction thật; Spring Cache mặc định không cung cấp |

**Eventual consistency không đồng nghĩa dữ liệu cũ luôn tự mất:** nếu không có TTL, event bị mất không được retry và không có reconciliation, một entry cũ có thể tồn tại vô hạn. Phải định nghĩa **cơ chế hội tụ** và **SLO stale window**.

Với dữ liệu liên quan **phân quyền, số dư, hạn mức, trạng thái pháp lý**, đôi khi nên **đọc authoritative source** hoặc validate version trước khi thực hiện quyết định nhạy cảm, thay vì yêu cầu một cache ngoài transaction đáp ứng ACID mà nó không được thiết kế để đáp ứng.

## 10. Chiến lược cache-aside với invalidation sau commit

Một chiến lược thông dụng:

~~~text
Read:
  1. cache.get(key)
  2. HIT -> trả cached value
  3. MISS -> đọc DB -> cache.put -> trả value

Write:
  1. UPDATE DB trong transaction
  2. COMMIT DB thành công
  3. evict(key) để lần đọc sau lấy dữ liệu mới
~~~

**Ưu điểm:** đơn giản, tránh ghi cache giá trị chưa commit khi eviction được thực hiện sau commit. Cache được xây lại từ nguồn dữ liệu tin cậy.

**Giới hạn:** DB commit xong nhưng eviction fail vẫn stale; reader đã miss và chụp snapshot cũ trước eviction có thể put lại giá trị cũ sau eviction. Đây là cache-aside có **eventual consistency**, không mặc định là strict read-after-write.

Các cơ chế bù:
- TTL hữu hạn và theo loại dữ liệu.
- Retry eviction có backoff và giới hạn.
- Đo độ trễ từ **DB commit → cache invalidation thành công**.
- Ghi event/outbox vào cùng DB transaction để giảm nguy cơ mất tín hiệu.
- Version metadata hoặc compare-and-swap để chặn entry cũ ghi đè entry mới.
- Tránh dùng cache với dữ liệu không chấp nhận stale.

## 11. Transactional outbox: giải quyết dual write với event

**Transactional outbox** không làm database và Redis có một physical transaction. Nó thay đổi cách xử lý thành:

1. Ghi **dữ liệu nghiệp vụ** và một **outbox record** trong **cùng một database transaction**.
2. Commit cả hai hoặc rollback cả hai.
3. Một relay/worker/CDC đọc outbox đã commit và phát **event invalidation/update** đến broker hoặc consumer.
4. Consumer xóa/cập nhật cache, ghi nhận idempotency, retry nếu thất bại.
5. Giám sát backlog, lag và hành vi khi event duplicate/out of order.

~~~text
                    MỘT DB TRANSACTION
BEGIN ------------------------------------------------ COMMIT
   | UPDATE account V2  |
   | INSERT outbox event(accountId, version=2, eventId) |
   ------------------------------------------------------
                                     |
                              Sau DB commit
                                     v
                          Relay / CDC / polling
                                     |
                                     v
                      Broker / cache invalidator
                                     |
                           evict/update cache
                              retry/idempotent
~~~

**Điểm atomic đã đạt được:** *database update và outbox event record* nằm trong **cùng DB transaction**. Vì vậy, nếu DB commit dữ liệu thì event tương ứng được lưu bền trong DB để relay có thể đọc lại. **Điểm chưa atomic:** cache update vẫn đến **sau**, có độ trễ, có thể fail/retry và vẫn cần xử lý concurrent readers.

### Pseudocode minh họa outbox

~~~sql
-- PSEUDOCODE SQL: điều chỉnh cú pháp, constraints
-- và transaction management theo RDBMS thực tế.
BEGIN;

UPDATE accounts
SET status = 'CANCELED', version = version + 1
WHERE account_id = 'A-7';

INSERT INTO outbox_event(event_id, aggregate_id, event_type,
                         aggregate_version, payload)
VALUES ('event-unique-123', 'A-7', 'ACCOUNT_CHANGED',
        12, '{"cacheKey":"A-7"}');

COMMIT;
~~~

Đây **không phải SQL chạy độc lập** vì chưa định nghĩa schema hoặc ràng buộc version chính xác. Trong production, eventId phải được sinh duy nhất và aggregate_version phải khớp **version thực tế đã commit**, không hard-code 12 như minh họa.

### Vì sao consumer phải idempotent?

Relay có thể gửi cùng event nhiều lần khi:
- Consumer đã xử lý nhưng acknowledgment bị mất.
- Process crash sau khi evict nhưng trước khi ghi checkpoint.
- Broker phát lại sau rebalance hoặc retry.

Với eviction đơn giản, gọi **evict(K)** hai lần thường an toàn về mặt state, nhưng một event **PUT value V2** đến sau **PUT value V3** có thể ghi đè phiên bản mới. Vì vậy, nên:
- Gắn **eventId** duy nhất và cơ chế deduplication khi cần.
- Gắn **aggregateId + version** tăng theo commit.
- So sánh version/generation trước khi ghi value; bỏ update cũ.
- Xử lý event out-of-order, retry có giới hạn và dead-letter/reconciliation.
- Giám sát thời gian event nằm trong outbox và độ trễ invalidation.

**Không đặt event publish trực tiếp trong @Transactional rồi coi đó là outbox.** Nếu publish tới broker xảy ra trước DB commit, broker có thể đã nhận event nhưng DB rollback. Nếu publish sau commit, process có thể crash trước khi publish. Outbox đặt **record event trong chính DB transaction** để tránh khe hở giữa DB update và việc ghi nhận ý định phát event.

## 12. @TransactionalEventListener(AFTER_COMMIT): hữu ích nhưng chưa chắc bền

Trong ứng dụng một tiến trình, có thể đăng ký listener sau transaction commit:

~~~java
// Snippet minh họa; event và service do ứng dụng định nghĩa.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onProductChanged(ProductChanged event) {
    cacheManager.getCache("products").evict(event.sku());
}
~~~

Đây là **mã minh họa**, không độc lập. Sau khi một transaction được commit thành công trong ngữ cảnh phù hợp, listener có thể yêu cầu eviction. Nhưng:
- Nếu process chết sau commit trước hoặc trong listener, invalidation có thể bị mất.
- Nếu Redis timeout, DB đã commit; không thể rollback DB bằng một exception từ listener.
- Khi không có transaction thích hợp, event behavior còn phụ thuộc cấu hình (ví dụ fallbackExecution).
- **AFTER_COMMIT callback** không phải một transaction DB mới. Spring cảnh báo transaction resource có thể còn được bind trong callback; nếu listener muốn **thực hiện thêm DB write cần được commit riêng**, có thể phải dùng transaction mới (ví dụ REQUIRES_NEW) phù hợp.

Khi cần **durable notification và retry giữa nhiều node**, transactional outbox + relay thường đáng tin hơn một in-process listener không có lưu trữ event bền.

## 13. Reader đang chạy vẫn có thể tái tạo giá trị cũ

Ngay cả khi:
- DB commit đúng,
- eviction chỉ chạy after commit,
- eviction thành công,

một request @Cacheable đã bắt đầu trước đó có thể **đặt value cũ trở lại cache sau eviction**.

~~~text
t0 Reader R: cache MISS, đọc DB version 7
t1 Writer W: DB COMMIT version 8
t2 Writer W: evict(K) thành công
t3 Reader R: cache.put(K, value-version-7)
t4 Reader X: cache HIT version 7  <-- stale
~~~

**Đây không phải lỗi transaction manager** mà là race giữa quá trình load data và put cache. Do đó, muốn chứng minh **không thể đọc stale**, phải đưa các reader in-flight vào thiết kế.

### Những giải pháp có thể cân nhắc

**Versioned cache key:**
~~~text
key = accountId + ":" + dbVersion
A-7:7 và A-7:8 là hai entry khác nhau.
~~~

Reader version 7 không thể ghi đè slot version 8, nhưng caller cần biết version mới đáng tin. Nếu version “mới nhất” lấy từ một cache stale khác, bài toán vẫn còn.

**Version/CAS tại cache boundary:**
~~~text
putIfNewer(K, candidate):
  thực thi kiểm tra/ghi có tính atomic theo provider
  nếu candidate.version < existing.version -> từ chối
  nếu candidate.version >= existing.version -> ghi theo policy
~~~

Đây là **pseudocode**; Spring Cache annotation không có sẵn **onlyPutIfVersionNewer**. So sánh version bằng một lệnh GET rồi SET tách rời **không** đủ vì còn cửa sổ time-of-check/time-of-use. Có thể cần native atomic compute, Lua script hoặc cơ chế provider-specific.

**Per-key coordination:**
- Đồng bộ reader loader và writer trên cùng key/partition, không chỉ khóa writer.
- Khóa local chỉ tác động một JVM, không tự đồng bộ nhiều node.
- Khóa phân tán phải xét timeout, ownership, fencing token, crash và lease.
- Khi cần đọc đúng tuyệt đối, bỏ cache khỏi một số đường quyết định có thể đơn giản hơn.

**@Cacheable(sync=true)** chủ yếu phối hợp **nhiều lượt tải cùng key**, không tự tạo một transaction chung với @CachePut/@CacheEvict hoặc DB. Không gọi nó là giải pháp atomic DB+Redis.

## 14. Có cần XA/two-phase commit không?

Về mặt lý thuyết, muốn một protocol commit nguyên tử xuyên hai resource managers, người ta dùng cơ chế như **XA/2PC** nếu **tất cả tài nguyên thực sự hỗ trợ tham gia, coordinator được cấu hình và failure modes được giải quyết**.

Nhưng:
- **Spring Cache Abstraction** không phải một XA resource manager.
- Một CacheManager không tự tham gia XA chỉ vì @Transactional được gắn trên method.
- Nhiều hệ thống Redis cache không hỗ trợ kiểu participation mà ứng dụng mong muốn đối với XA database transaction.
- Distributed transaction có chi phí latency, khả năng block, vận hành recovery phức tạp.
- Ngay cả khi dùng XA cho các resource phù hợp, quyết định có cache dữ liệu hay không và cache invalidation semantics vẫn phải thiết kế riêng.

Trong đa số kiến trúc **database + distributed cache**, lựa chọn thực tế thường là **chấp nhận eventual consistency có kiểm soát**, và thiết kế **after-commit invalidation + outbox/retry + versioning/TTL**. Chỉ cân nhắc giao dịch phân tán thật khi use case và hệ thống tài nguyên cho phép, thay vì suy từ một annotation.

## 15. Hệ quả nguy hiểm ở tầng API và client

Một update API có thể:
1. Commit DB thành công.
2. Gặp lỗi trong after-commit callback cập nhật cache.
3. Trả HTTP 500 hoặc timeout cho client, dù bản ghi đã thay đổi.

Nếu client retry:
- Với PUT idempotent theo resource/version, có thể lặp một cách an toàn trong điều kiện phù hợp.
- Với lệnh **tăng số dư, trừ tồn kho, tạo thanh toán, đặt vé**, retry mù có thể thực thi tác động nghiệp vụ lần hai.
- Với optimistic lock/version guard, retry có thể trả conflict rõ ràng thay vì cập nhật lại vô ý.

Giải pháp thiết kế API:
- **Idempotency key** cho command quan trọng và lưu kết quả command trong authoritative DB.
- **Unique constraint** và transaction trong DB để phòng double-apply.
- **CorrelationId/eventId** để tra cứu trạng thái sau lỗi.
- Phân biệt failure của **DB update** và failure của **cache invalidation** trong metrics, logging và retry policy.
- Với cache outage, cân nhắc phục vụ read từ DB (degraded mode) hoặc bỏ qua cache thay vì thất bại toàn bộ nghiệp vụ nếu chính sách cho phép.

**Không được coi cache refresh thất bại là lý do “thử rollback DB đã commit”** bằng một lời gọi rollback bình thường; transaction commit rồi không còn rollback cùng giao dịch đó nữa. Nếu nghiệp vụ cần undo, đó là **compensation** riêng, phải đánh giá tính đúng đắn và idempotency.

## 16. Kiểm thử: phải chèn lỗi đúng giữa các ranh giới

Unit test một repository hoặc một CacheManager riêng rẽ sẽ không chứng minh hệ thống chịu được dual write. Cần **integration/fault-injection tests** với transaction manager và cache provider thật.

| Kiểm thử | Điểm gây lỗi/tình huống | Điều cần quan sát |
| --- | --- | --- |
| **Rollback sau raw cache.put** | DB rollback | DB cũ, cache mới: minh họa lỗi nếu không defer |
| **Rollback với transaction-aware put** | DB rollback | Cache put chưa được áp dụng |
| **Commit với transaction-aware put** | DB commit | Cache put thực thi after-commit |
| **Lỗi cache sau DB commit** | Redis unavailable/network timeout | DB mới, cache có thể cũ |
| **Crash sau commit trước event** | Kill process ở ranh giới | Nếu không outbox, có thể mất invalidation |
| **Rollback sau ghi outbox** | DB rollback | Cả dữ liệu và outbox record đều rollback |
| **Duplicate event** | Consumer xử lý lại eventId | Idempotent, không double-apply |
| **Out-of-order event** | V8 đến trước V7 | Không ghi đè V8 bằng V7 |
| **Reader load đang bay** | Reader chụp V7 trước evict V8 | Có stale repopulation không? |
| **Hai ứng dụng dùng cache local** | Node A update, node B giữ entry | Có invalidation cross-node không? |
| **Checked exception** | @Transactional không đặt rollbackFor | DB có commit ngoài kỳ vọng không? |
| **Self-invocation** | this.update(...) | Transaction/cache advice có bị bypass không? |
| **Cache.evictIfPresent** | Gọi trong transaction-aware wrapper | Có thao tác immediate ngoài after-commit không? |
| **Transaction không active** | Cache.put ngoài tx | Deferred hay chạy ngay? (thường ngay) |
| **Recovery sau outage** | Redis hồi phục | TTL/retry/reconciliation giúp hội tụ đúng SLO? |

### Gợi ý test có điều khiển

Dùng **CountDownLatch**, barrier và timeout thay vì Thread.sleep ngẫu nhiên để dàn dựng race. Khi kiểm tra một update, quan sát **DB value**, **cache value**, **commit result**, **cache invalidation event** và **response API**. Trong hệ thống distributed, thêm **network partition**, duplicate/out-of-order broker delivery và hai app instances.

**Đặc biệt:** test qua **Spring-managed beans/ApplicationContext** nếu sản phẩm dùng annotation AOP. Nếu unit test tự new service thì @Transactional/@CacheEvict không được intercept như production.

## 17. Checklist thiết kế production

Trước khi phát hành một thay đổi có cập nhật DB và Redis/Caffeine/Ehcache, hãy trả lời:

1. **Nguồn sự thật** là database nào? Cache có thể bị bỏ và tái tạo từ DB không?
2. **Hợp đồng freshness** là best-effort, eventual, read-your-writes hay strict linearizable?
3. Update thuộc transaction manager nào? @Transactional có thực sự được kích hoạt qua proxy không?
4. Có cache operation nào chạy trước DB commit hoặc ngay cả khi DB rollback không?
5. Có đang dùng transaction-aware CacheManager/Proxy? Đúng bean được inject chưa?
6. Có thao tác immediate **putIfAbsent/evictIfPresent/invalidate** bỏ qua deferred semantics không?
7. Có reader in-flight nào có thể put snapshot cũ sau eviction không?
8. Có nhiều writer/instance có thể áp dụng event hoặc put theo thứ tự đảo không?
9. TTL của cache có đảm bảo stale cuối cùng hết hạn trong giới hạn chấp nhận được không?
10. Khi Redis unavailable, **DB update vẫn cần hoạt động** hay phải fail closed?
11. Sau DB commit, lỗi cache update sẽ được **retry** như thế nào? Có backoff và giới hạn?
12. Nếu process crash ngay sau commit, có durable outbox/event hoặc reconciliation không?
13. Outbox relay/consumer có idempotency key, version và cảnh báo backlog không?
14. Hai tầng L1 cache local và L2 cache shared có invalidation đồng bộ ra sao?
15. Cache key có tenant, quyền hạn, locale, version nếu chúng làm thay đổi kết quả không?
16. Metric có đo cache hit/miss, stale read, invalidation delay, event lag, retry và provider errors không?
17. Khi trả HTTP error sau commit, client retry có gây double-apply nghiệp vụ không?
18. Có cách **bypass cache và đọc DB** cho đường kiểm tra quan trọng hay khi cache outage không?
19. Có integration test với DB và cache provider production (ít nhất cấu hình tương đương) không?
20. Nếu không đáp ứng được yêu cầu nhất quán, có nên **không dùng cache** cho dữ liệu đó không?

### Một số metric hữu ích

- **cache_invalidation_lag_seconds**: từ lúc DB commit đến khi eviction/update thành công.
- **cache_update_failures_total**: số lần cache update/evict thất bại.
- **outbox_pending_events** và **outbox_oldest_event_age_seconds**: tiến độ relay.
- **cache_version_mismatch_total**: số lần phát hiện value cache kém phiên bản DB.
- **idempotent_command_replays_total**: số lần client retry command đã xử lý.
- **database_fallback_reads_total**: lượt đọc DB khi cache bị bypass hoặc outage.

Các metric trên là **đề xuất đặt tên**; không phải các metric do Spring tự động sinh ra. Nên gắn nhãn hợp lý, tránh metric cardinality cao theo userId/orderId.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** @Transactional bao quanh repository.update và RedisCache.put. Có bảo đảm rollback DB sẽ rollback Redis put không?

**Không.** DB transaction manager không tự quản lý Redis cache như cùng một resource transaction.

**Câu 2.** TransactionAwareCacheManagerProxy trì hoãn put/evict tới after-commit. DB commit xong, Redis timeout. Có thể rollback lại DB không?

**Không.** Callback cache diễn ra sau commit; transaction-aware không tạo atomic DB+Redis commit.

**Câu 3.** Tại sao “evict trước khi update DB” có thể gây stale?

Reader khác có thể cache miss rồi đọc phiên bản DB cũ vì update chưa commit, sau đó put giá trị cũ trở lại cache.

**Câu 4.** “Evict sau commit” có chắc chắn ngăn stale repopulation không?

**Không.** Reader đã chụp snapshot cũ trước eviction có thể put sau eviction.

**Câu 5.** Dùng Redis MULTI/EXEC có biến UPDATE MySQL + Redis DEL thành một transaction ACID không?

**Không.** Redis transaction chỉ ràng buộc thao tác trong phạm vi Redis; nó không tự bao gồm commit của MySQL.

**Câu 6.** Transactional outbox bảo đảm phần nào nguyên tử?

**Database update và outbox event record** trong cùng một DB transaction; không làm Redis/broker cập nhật ngay trong chính commit ấy.

**Câu 7.** Nếu relay gửi event hai lần, consumer nên làm gì?

Thiết kế **idempotent**, nhận diện eventId/version và đảm bảo duplicate không tạo tác dụng sai.

**Câu 8.** Khi out-of-order update V7 đến sau V8, chỉ dùng Cache.put thông thường có an toàn không?

**Không.** Nó có thể ghi đè V8 bằng V7. Cần version/CAS hoặc chiến lược invalidation/ordering phù hợp.

**Câu 9.** @Cacheable(sync=true) có thay thế transaction DB hay distributed lock cho toàn bộ reader/writer không?

**Không.** Mục tiêu chính của nó là phối hợp các lượt tải cùng key khi cache miss và provider hỗ trợ.

**Câu 10.** Vì sao một API trả lỗi sau cache timeout vẫn cần kiểm tra DB trước khi retry?

Vì database có thể **đã commit**, chỉ cache operation hoặc response bị lỗi. Retry mù có thể thực thi thay đổi nghiệp vụ lần hai.

**Câu 11.** Trong transaction-aware cache, putIfAbsent có luôn đợi after-commit không?

**Không.** Đây là operation cần kết quả immediate; theo contract TransactionAwareCacheDecorator nó **không thể mặc định defer như put**.

**Câu 12.** Khi muốn read-after-write đúng tuyệt đối cho dữ liệu phân quyền, có nên đặt TTL cực ngắn là đủ không?

**Không.** TTL ngắn chỉ giảm thời gian stale trung bình, không chứng minh không có cửa sổ sai. Cần kiểm tra dữ liệu có thẩm quyền hoặc thiết kế consistency protocol phù hợp.

## Tổng kết

**Một database transaction không tự làm distributed cache nguyên tử.** Cập nhật database và ghi/xóa cache là hai side effects độc lập trừ khi có giao thức phối hợp rõ ràng. **@Transactional** chỉ điều khiển tài nguyên mà transaction manager quản lý; **@CachePut/@CacheEvict** không mặc định tạo ACID chung với database.

**TransactionAwareCacheManagerProxy** giúp hoãn các thao tác **put/evict/clear** tới **after-commit**, giảm rủi ro cache chứa dữ liệu của transaction rollback. Nhưng nó **không xóa khe hở commit DB thành công rồi cache update thất bại**, và cũng không chặn reader cũ tái điền cache.

Nếu chấp nhận eventual consistency, mô hình thực tế thường là **cache-aside + after-commit invalidation + TTL + retry**; với yêu cầu đáng tin cậy hơn, bổ sung **transactional outbox, idempotent event processing, version/CAS và reconciliation**. Với quyết định nghiệp vụ không chấp nhận stale, hãy **đọc authoritative DB hoặc dùng một kiến trúc nhất quán mạnh** thay vì đặt kỳ vọng sai vào caching annotation.

### Tài liệu tham khảo

- Spring Framework 6.2 – TransactionAwareCacheDecorator: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework 6.2 – TransactionAwareCacheManagerProxy: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html
- Spring Framework – Declarative annotation-based caching, @CacheEvict: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework – Transaction synchronization: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/tx-resource-synchronization.html
- Spring Framework – @TransactionalEventListener: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- AWS Prescriptive Guidance – Transactional outbox pattern: https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
- Maven Central – H2 2.3.232: https://central.sonatype.com/artifact/com.h2database/h2/2.3.232

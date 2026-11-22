# TransactionAwareCacheDecorator và thao tác sau commit trong Spring Cache

## 1. Bài học giải quyết vấn đề gì?

Trong Spring Framework, một phương thức cập nhật dữ liệu nguồn và một lời gọi `Cache.put`, `Cache.evict` hoặc `Cache.clear` là **những thao tác lên hai hệ thống trạng thái khác nhau**. Nếu database transaction vẫn chưa commit mà cache đã bị cập nhật, các request khác có thể quan sát một phiên bản không tương ứng với dữ liệu thực sự đã commit.

Ví dụ kinh điển:

1. Transaction T1 sửa giá sản phẩm từ `100` thành `120` nhưng **chưa commit**.
2. Spring xóa cache entry `products[42]` ngay.
3. Request T2 cache miss, đọc database ở mức isolation thông thường và vẫn thấy giá `100`.
4. T2 lưu `100` trở lại cache.
5. T1 commit `120`; cache lại đang có `100` và có thể stale.

Một cách phối hợp là **hoãn những thay đổi cache có thể trì hoãn đến sau khi database transaction commit thành công**. Spring hỗ trợ cơ chế này qua:

- `org.springframework.cache.transaction.TransactionAwareCacheDecorator`: bọc **một Spring Cache** đã có.
- `org.springframework.cache.transaction.TransactionAwareCacheManagerProxy`: bọc **một Spring CacheManager**, để các `Cache` lấy ra có hành vi transaction-aware.
- Một số `CacheManager` mở rộng `AbstractTransactionSupportingCacheManager`, có thể hỗ trợ cơ chế tương tự bằng cấu hình `transactionAware` của chính manager đó.

Điểm cần nhớ: decorator **không biến cache thành một thành viên ACID của database transaction**. Nó dùng **transaction synchronization callback** để chỉ thực hiện `put`/`evict`/`clear` khi Spring báo transaction đã commit. Đây là phối hợp theo vòng đời, không phải two-phase commit, không cung cấp transaction-local cache view và cũng không tự động rollback một cache write đã thực thi.

Trong phạm vi nhóm **Giao dịch**, bài này sẽ làm rõ lifecycle, chính sách after-commit, hành vi trước commit/rollback, cách cấu hình đúng manager, rủi ro advice order và test với Java 17+.

## 2. Vai trò chính xác của TransactionAwareCacheDecorator

Javadoc của Spring mô tả `TransactionAwareCacheDecorator` là một `Cache` decorator, nhận một `Cache targetCache` và **ủy quyền việc đọc**, trong khi đồng bộ ba thao tác thay đổi trạng thái với Spring-managed transaction:

| Thao tác qua decorated Cache | Nếu có transaction synchronization phù hợp | Nếu không có transaction synchronization |
| --- | --- | --- |
| `put(key, value)` | Đăng ký callback; cache thật được put trong `afterCommit` | Delegate ngay cho native cache |
| `evict(key)` | Đăng ký callback; evict thật trong `afterCommit` | Delegate ngay |
| `clear()` | Đăng ký callback; clear thật trong `afterCommit` | Delegate ngay |
| `get(key)` | Đọc cache thực tế, **không tự đọc các put/evict đang chờ** | Đọc cache thực tế |
| `putIfAbsent(key, value)` | **Immediate**, không hoãn như `put` | Immediate theo khả năng backend |
| `evictIfPresent(key)` | **Immediate**, không hoãn như `evict` | Immediate theo khả năng backend |
| `invalidate()` | **Immediate**, không hoãn như `clear` | Immediate theo khả năng backend |

Lớp thực thi dùng `TransactionSynchronizationManager`. Về mặt implementation, điểm kiểm tra quan trọng là **transaction synchronization có đang active hay không**, không chỉ việc có annotation `@Transactional` trên source. Một transaction manager có thể bật synchronization trong những chế độ propagation nhất định; vì vậy không được tự suy ra mốc callback chỉ bằng cách nhìn method signature.

### Phân biệt yêu cầu và hiệu lực

Với `Cache` đã decorate:

~~~java
cache.put("p:42", "new");
System.out.println(cache.get("p:42"));
~~~

Đây là snippet, không phải file độc lập. Nếu mã chạy trong một Spring transaction có synchronization và key chưa tồn tại trước đó, `cache.get("p:42")` ngay sau `put` có thể vẫn trả `null` (miss). Lệnh put mới chỉ **được xếp lịch after-commit**; decorator không tạo một bản ghi tạm để chính transaction đọc.

Tương tự, nếu key đang lưu `old` và gọi `cache.evict(key)` trong transaction, `cache.get(key)` trước commit **có thể vẫn hit `old`**. Không coi đây là lỗi của Spring: đây là hệ quả có chủ đích của deferred operation.

## 3. Timeline commit: cập nhật DB, đăng ký cache và callback

~~~mermaid
sequenceDiagram
    participant Client as Caller
    participant Tx as Transaction Manager
    participant Service as Business Service
    participant Decorator as TransactionAwareCacheDecorator
    participant DB as Database
    participant Cache as Native Cache

    Client->>Tx: begin transaction
    Tx->>Service: invoke updateProduct()
    Service->>DB: update product
    Service->>Decorator: evict(productKey)
    Decorator->>Tx: register afterCommit synchronization
    Decorator-->>Service: return (eviction chưa chạy)
    Service-->>Tx: business method returns
    Tx->>DB: commit transaction
    alt commit thành công
        Tx->>Decorator: afterCommit()
        Decorator->>Cache: evict(productKey)
        Cache-->>Decorator: applied
        Tx-->>Client: transaction finished
    else commit/transaction thất bại
        Tx-->>Client: rollback / exception
        Note over Cache: callback afterCommit không được chạy
    end
~~~

Sơ đồ minh họa ý tưởng, **không phải cam kết** mọi `@Transactional` + `@CacheEvict` luôn tạo thứ tự trên. Khi caching/transaction advice nằm ở các lớp proxy khác nhau, một `@CacheEvict` có thể phát lệnh sau lúc transaction interceptor đã kết thúc. Khi đó synchronization không còn active và decorator có thể thực thi eviction ngay. Phần **advice ordering** ở mục 10 rất quan trọng.

### Các thời điểm cần phân biệt

- **Trước invocation:** `@CacheEvict(beforeInvocation=true)` yêu cầu eviction trước khi gọi business method.
- **Sau invocation:** `@CacheEvict(beforeInvocation=false)` yêu cầu eviction khi business method kết thúc bình thường.
- **Sau commit:** `TransactionAwareCacheDecorator` thực hiện lệnh native cache trong `afterCommit` nếu đã đăng ký synchronization hợp lệ.

**“After invocation” không bằng “after commit”.** Hai thời điểm khác nhau, thuộc hai cơ chế khác nhau. Cũng không nên hiểu “đã gọi `cache.evict`” là “entry đã bị xóa vật lý”.

## 4. Ba thao tác có thể hoãn: put, evict và clear

### 4.1. put(key, value)

`Cache.put` đặt hoặc thay entry. Với decorator transaction-aware và synchronization active, lệnh native put được hoãn tới after-commit.

~~~java
cache.put("product:42", newProduct);
~~~

Đây là snippet với `cache` đã decorate, `newProduct` là DTO nghiệp vụ. Những điểm đặc biệt:

- Nếu transaction rollback, lệnh put đã đăng ký **không chạy**.
- `cache.get("product:42")` trước commit vẫn có thể thấy DTO **cũ**, hoặc miss.
- Giá trị object `newProduct` được giữ để callback sử dụng. Tránh tiếp tục mutate object có thể thay đổi trong lúc chờ commit; nên dùng DTO immutable/copy phù hợp.
- Một transaction có thể phát **nhiều lệnh put** cho cùng key. Kết quả và thứ tự native operation cần kiểm tra bằng integration test; không dùng cơ chế này như một transactional write buffer có coalescing hay isolation chuẩn DB.
- Khi callback put gặp lỗi **sau khi DB đã commit**, lỗi cache không thể làm DB tự động rollback. Cần xử lý consistency theo chính sách hệ thống.

### 4.2. evict(key)

`Cache.evict` yêu cầu loại bỏ một key. Sau commit thành công, native cache mới nhận lệnh xóa:

~~~java
cache.evict("product:42");
~~~

Lợi ích chính là hạn chế trường hợp reader khác **miss rồi nạp lại dữ liệu DB cũ** trước commit. Tuy nhiên, lệnh evict sau commit cũng không loại bỏ mọi race: một loader cũ bắt đầu trước đó có thể hoàn tất muộn và ghi lại stale value. Nếu dữ liệu đòi hỏi consistency mạnh, cần kết hợp versioned key, invalidation event, loader coordination hoặc TTL.

### 4.3. clear()

`Cache.clear` xóa toàn vùng cache được chọn:

~~~java
cache.clear();
~~~

Trong transaction-aware decorator, lệnh clear được hoãn đến after-commit. Điều đó tránh clear một vùng lớn cho một thay đổi đã rollback nhưng vẫn có chi phí: **cache stampede** khi nhiều request cache miss sau commit, tăng tải DB và độ trễ cold cache. Cần xác định chính xác cache name/tenant scope và tránh clear toàn cache chỉ vì một key thay đổi.

### Các lệnh có thể hoãn không có nghĩa không bao giờ hiệu lực

Nếu không có synchronization active, decorator **ủy quyền ngay** cho `targetCache`. Sau đó mức độ tức thời vật lý vẫn phụ thuộc implementation native (ví dụ remote cache/asynchronous write). Decorator không áp đặt một lớp chờ after-commit khi không có một synchronization cycle để đăng ký.

## 5. Rollback: callback afterCommit không chạy

Khi transaction bị rollback, `afterCommit` **không được gọi**. Hậu quả với ba operation đã đăng ký:

| Operation được yêu cầu trong transaction | Khi commit thành công | Khi rollback |
| --- | --- | --- |
| `put("x", newValue)` | Được phát tới cache sau commit | Không phát lệnh put đã đăng ký |
| `evict("x")` | Được phát tới cache sau commit | Không phát lệnh evict đã đăng ký |
| `clear()` | Được phát tới cache sau commit | Không clear qua callback đó |

Điều này giúp cache giữ tương thích với database **nếu** business changes cũng thực sự rollback cùng transaction. Nhưng không nên kết luận cứ có exception là DB chưa thay đổi: tài nguyên ngoài transaction (HTTP, message broker, file, DB khác hoặc transaction `REQUIRES_NEW`) có thể đã commit riêng.

### Ba loại kết thúc cần kiểm thử

1. **Return bình thường + commit thành công:** lệnh hoãn chạy.
2. **Method ném exception và transaction rollback:** lệnh hoãn không chạy, nếu đã được đăng ký trước exception.
3. **Method return bình thường nhưng outer transaction đánh dấu rollback-only:** vẫn không chạy after-commit; caller có thể nhận `UnexpectedRollbackException` tùy tình huống.

Vì vậy, **mốc quan trọng là kết quả commit thật**, không phải riêng việc method đã return hay đã đi tới một dòng `cache.evict` trong code.

## 6. Không có read-your-writes và không có transaction-local cache view

Một ngộ nhận phổ biến: “Dùng transaction-aware nghĩa là bên trong transaction đọc được những giá trị mới đang chờ put.”

Không đúng. Decorator thực hiện `get` trên target cache; nó **không cung cấp bảng thay đổi tạm** như persistence context của JPA.

| Tình huống | Trong transaction, trước commit | Sau commit (không có writer khác) |
| --- | --- | --- |
| Key trống, gọi `put(K, "v2")` | `get(K)` có thể vẫn miss | `get(K)` hit `v2` |
| Key là `v1`, gọi `put(K, "v2")` | `get(K)` có thể còn `v1` | `get(K)` hit `v2` |
| Key là `v1`, gọi `evict(K)` | `get(K)` có thể còn `v1` | `get(K)` miss |
| Cache có các entry, gọi `clear()` | Có thể vẫn thấy entry cũ | Các entry bị clear |

Khi business method cần đọc dữ liệu mới vừa cập nhật **trong cùng DB transaction**, hãy đọc qua repository/persistence context với isolation phù hợp, không dựa vào cache được decorate để thể hiện uncommitted state.

Ngoài ra, `Cache.get(Object)` phân biệt cache miss (`ValueWrapper` là null) với hit chứa null (`ValueWrapper` khác null nhưng `get()` trả null). Điều này quan trọng khi viết test kiểm tra deferred put/evict; typed `Cache.get(key, Type.class)` không phân biệt hai trường hợp ấy.

## 7. Cấu hình trực tiếp một Cache và bọc toàn CacheManager

### 7.1. Bọc một Cache

~~~java
Cache nativeCache = new ConcurrentMapCache("products");
Cache transactionAware = new TransactionAwareCacheDecorator(nativeCache);
~~~

Snippet này cần import `org.springframework.cache.Cache`, `ConcurrentMapCache` và `TransactionAwareCacheDecorator`. Hợp khi bạn sử dụng `Cache` qua API lập trình trực tiếp, hoặc muốn kiểm chứng lifecycle với một cache.

`transactionAware.getTargetCache()` cho phép truy cập target cache để test/diagnostic, nhưng business code **không nên dùng target native cache để ghi/xóa** nếu nó muốn bảo đảm after-commit. Một lời gọi `nativeCache.evict` trực tiếp bypass decorator và không hoãn.

### 7.2. Bọc cả CacheManager

~~~java
@Bean
org.springframework.cache.CacheManager cacheManager() {
    ConcurrentMapCacheManager nativeManager =
            new ConcurrentMapCacheManager("products", "priceBySku");
    return new TransactionAwareCacheManagerProxy(nativeManager);
}
~~~

Đây là snippet bên trong `@Configuration` class. Manager proxy trả `Cache` đã được decorate khi Spring annotations hoặc code gọi `getCache(name)`. Điều đó giúp mọi `@Cacheable`/`@CachePut`/`@CacheEvict` sử dụng **cùng chính sách** thay vì có method lấy cache bọc, method khác lấy cache raw.

Nếu có nhiều bean Spring `CacheManager`, phải xác định rõ manager dùng bởi caching advice, ví dụ bằng `CachingConfigurer` hoặc `cacheManager` thuộc tính của annotation. Tên class giống nhau không bảo đảm đúng bean.

### 7.3. CacheManager có transaction-aware support sẵn

Một số manager Spring kế thừa `AbstractTransactionSupportingCacheManager` và có cơ chế cấu hình transaction awareness riêng. Với những manager này, xem Javadoc `setTransactionAware(true)` cùng lifecycle của manager. Tránh bọc decorator/proxy hai lần hoặc vô tình dùng một bean raw khác; điều đó có thể làm policy khó quan sát và gây callback lặp.

**Cấu hình Spring Boot:** không suy ra chỉ từ việc có `spring-boot-starter-cache` rằng cache manager đã tự động transaction-aware. Xem bean thực tế, customizer, provider và phiên bản Boot. Không có một cờ cấu hình chung thay thế việc kiểm tra CacheManager đang được inject.

## 8. Ví dụ Java 17+ chạy độc lập với transaction synchronization

Để quan sát after-commit **không cần database bên ngoài**, ví dụ sau dùng:

- Spring Framework 6.2.14.
- `ConcurrentMapCache` làm native cache trong RAM.
- `TransactionAwareCacheDecorator` bọc cache đó.
- `TransactionTemplate` để chạy các nhánh commit/rollback.
- Một subclass nhỏ của `AbstractPlatformTransactionManager` chỉ dành cho **mô phỏng lifecycle**.

Transaction manager mô phỏng **không thực hiện giao dịch database**. Nó chỉ cho phép Spring phát transaction synchronization callbacks để minh họa. Không dùng class manager này cho production; khi cần chứng minh DB consistency, dùng `DataSourceTransactionManager`/`JpaTransactionManager` và DB thật.

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>transaction-aware-cache-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.14</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-tx</artifactId>
      <version>6.2.14</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.2</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 8.2. src/main/java/demo/TransactionAwareCacheDemo.java

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.transaction.TransactionAwareCacheDecorator;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

public final class TransactionAwareCacheDemo {
    private TransactionAwareCacheDemo() { }

    // Chỉ tạo lifecycle của Spring transaction synchronization.
    // Không quản lý DB, connection, lock hoặc commit dữ liệu thật.
    static final class DemoTransactionManager
            extends AbstractPlatformTransactionManager {
        private static final long serialVersionUID = 1L;

        @Override
        protected Object doGetTransaction() {
            return new Object();
        }

        @Override
        protected void doBegin(Object transaction,
                               TransactionDefinition definition) { }

        @Override
        protected void doCommit(DefaultTransactionStatus status) { }

        @Override
        protected void doRollback(DefaultTransactionStatus status) { }
    }

    private static String lookup(Cache cache, String key) {
        Cache.ValueWrapper wrapper = cache.get(key);
        return wrapper == null ? "MISS" : String.valueOf(wrapper.get());
    }

    public static void main(String[] args) {
        Cache nativeCache = new ConcurrentMapCache("products");
        Cache cache = new TransactionAwareCacheDecorator(nativeCache);
        TransactionTemplate tx =
                new TransactionTemplate(new DemoTransactionManager());

        nativeCache.put("a", "v1");
        tx.execute(status -> {
            cache.evict("a");
            System.out.println("before commit evict=" + lookup(cache, "a"));
            return null;
        });
        System.out.println("after commit evict=" + lookup(cache, "a"));

        tx.execute(status -> {
            cache.put("b", "v2");
            System.out.println("before commit put=" + lookup(cache, "b"));
            return null;
        });
        System.out.println("after commit put=" + lookup(cache, "b"));

        nativeCache.put("c", "v3");
        tx.execute(status -> {
            cache.clear();
            System.out.println("before commit clear=" + lookup(cache, "c"));
            return null;
        });
        System.out.println("after commit clear=" + lookup(cache, "c"));

        nativeCache.put("d", "v4");
        tx.execute(status -> {
            cache.evict("d");
            status.setRollbackOnly();
            System.out.println("inside rollback=" + lookup(cache, "d"));
            return null;
        });
        System.out.println("after rollback=" + lookup(cache, "d"));

        nativeCache.put("e", "v5");
        tx.execute(status -> {
            boolean existed = cache.evictIfPresent("e");
            System.out.println("immediate existed=" + existed);
            System.out.println("immediate inside=" + lookup(cache, "e"));
            status.setRollbackOnly();
            return null;
        });
        System.out.println("immediate after rollback=" + lookup(cache, "e"));

        cache.put("outside", "v6");
        System.out.println("without transaction=" + lookup(cache, "outside"));
    }
}
~~~

### 8.3. Chạy chương trình

Từ thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.TransactionAwareCacheDemo
~~~

### 8.4. Stdout dự kiến

Bỏ qua log Maven/Spring (nếu có), các dòng do chương trình in theo thứ tự:

~~~text
before commit evict=v1
after commit evict=MISS
before commit put=MISS
after commit put=v2
before commit clear=v3
after commit clear=MISS
inside rollback=v4
after rollback=v4
immediate existed=true
immediate inside=MISS
immediate after rollback=MISS
without transaction=v6
~~~

Giải thích:

1. `evict("a")` được hoãn; bên trong transaction còn `v1`; sau commit entry `a` bị xóa.
2. `put("b","v2")` được hoãn; bên trong transaction `b` còn miss; sau commit cache có `v2`.
3. `clear()` được hoãn; `c` vẫn visible trước commit, và miss sau commit.
4. `evict("d")` được đăng ký nhưng transaction đánh dấu rollback-only; callback after-commit không chạy, `d=v4` vẫn tồn tại.
5. `evictIfPresent("e")` là immediate operation; nó xóa ngay `e`, trả `true` vì key đã có; **rollback sau đó không phục hồi entry**.
6. `put("outside","v6")` được gọi khi không có transaction synchronization active, nên delegate ngay cho cache trong RAM.

**Điều ví dụ chứng minh:** hành vi của `TransactionAwareCacheDecorator` với Spring transaction synchronization và một local cache. **Điều ví dụ không chứng minh:** rollback database, advice order trong một Spring service thực, distributed cache coherence hoặc khả năng khôi phục khi provider lỗi sau commit. Stdout được suy ra từ code và Javadoc; chương trình cần được chạy với dependency đã khai báo để xác minh thực tế trên máy học viên.

## 9. Immediate operations trong transaction: dùng có chủ đích

Spring Cache còn có những operation với kỳ vọng thay đổi ngay, chẳng hạn:

| Method | Ý nghĩa | Điều cần cảnh giác khi đang có transaction |
| --- | --- | --- |
| `putIfAbsent(K, V)` | Ghi nếu chưa có mapping và trả previous wrapper | Có thể ghi **trước commit**, dù transaction sau đó rollback |
| `evictIfPresent(K)` | Xóa key với expectation ngay sau call không còn visible | Rollback DB không tự khôi phục entry đã xóa |
| `invalidate()` | Clear toàn cache với immediate visibility expectation | Có thể xóa nhiều entries trước khi biết DB transaction thành công |

Javadoc `TransactionAwareCacheDecorator` nêu rằng `putIfAbsent` và `evictIfPresent` **không thể hoãn** vào after-commit mà vẫn giữ ý nghĩa immediate. `invalidate` là biến thể clear kỳ vọng immediate, cũng cần được đánh giá như thao tác tức thời.

Cần phân biệt ý nghĩa return:

- `evictIfPresent(K)==false` không chắc là lỗi. Có thể key không tồn tại, hoặc provider không xác định được prior presence.
- `invalidate()==false` có thể vì cache vốn trống hoặc không xác định được trước đó có entries.
- `putIfAbsent(K,V)` **không overwrite** giá trị cũ. Nếu cache đã có K, operation trả wrapper của entry cũ; value mới có thể không được ghi.
- Implementation custom có thể dùng default methods không đạt mức atomic/immediate như native cache. Kiểm tra provider cụ thể trước khi dựa vào guarantees mạnh.

**Quy tắc thiết kế:** chọn deferred `put/evict/clear` khi mục tiêu là **chỉ thay cache sau commit thành công**; chọn immediate methods khi ứng dụng thực sự cần visibility trước commit và hiểu rõ rủi ro rollback/race. Không đổi `evict` thành `evictIfPresent` chỉ để chữa một cache miss mà chưa biết transaction semantics.

## 10. @Transactional kết hợp @CacheEvict: thứ tự AOP advice

Ví dụ:

~~~java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public void changePrice(long id, long newPrice) {
    repository.changePrice(id, newPrice);
}
~~~

Đoạn này là **snippet trong Spring-managed bean**; cần repository, transaction manager và cache manager thực tế. Khi gọi qua proxy, cache advice và transaction advice cùng tham gia xử lý. Tùy advisor order, lớp nào bao ngoài lớp nào, và transaction propagation:

**Trường hợp A – eviction được yêu cầu khi transaction còn active:**

~~~text
TransactionInterceptor: begin
  CacheInterceptor:
    changePrice(...)
    Cache.evict(K) -> decorator register afterCommit
TransactionInterceptor: DB commit
TransactionAwareCacheDecorator: native evict(K)
~~~

Với cách sắp xếp này, cache decorator thực sự có synchronization để đăng ký lệnh sau commit.

**Trường hợp B – eviction được yêu cầu sau khi transaction advice đã hoàn tất:**

~~~text
CacheInterceptor:
  TransactionInterceptor: begin
    changePrice(...)
  TransactionInterceptor: DB commit + cleanup
  Cache.evict(K) -> không còn sync active, delegate ngay
~~~

Trường hợp B cũng có thể đạt thứ tự “sau DB commit” đối với lời gọi đồng bộ đơn giản, nhưng sự khác biệt quan trọng là **lệnh không được đăng ký trong callback sau commit**, và thứ tự có thể thay đổi nếu có outer transaction hoặc advice khác.

**Không có câu trả lời chung “chỉ thêm hai annotation là bảo đảm after-commit”.** Spring cache advice có thuộc tính `order` của `@EnableCaching`; transaction advice có `@EnableTransactionManagement(order=...)`. Nếu cả hai không có thứ tự được kiểm soát, hãy test bằng transaction manager thật và xác định outer/inner boundary.

Một outer transaction có thể bao lời gọi annotated method; một transaction `REQUIRES_NEW` có commit riêng. Lệnh cache đăng ký vào synchronization của transaction đang active **tại thời điểm gọi**; không tự gắn vào “giao dịch nghiệp vụ cuối cùng” theo tên method.

### Self-invocation vẫn là vấn đề

Trong proxy mode mặc định:

~~~java
public void outer(long id) {
    this.changePrice(id, 123L); // self-invocation bypass proxy
}
~~~

Nếu gọi nội bộ từ target thay vì qua Spring proxy, cả `@CacheEvict` và `@Transactional` trên `changePrice` đều có thể bị bypass. Hãy tổ chức lại bean/call boundary hoặc dùng AspectJ weaving khi thực sự cần interception nội bộ. Không đổ lỗi cho decorator nếu caching operation chưa từng được gọi.

## 11. afterCommit không bằng một distributed transaction

Decorator có giá trị thiết thực, nhưng **không thể bảo đảm atomicity DB/cache**:

1. **DB commit thành công, cache put/evict thất bại:** DB đã commit, transaction không thể bị rollback ngược chỉ vì cache lỗi sau đó. Có thể còn entry stale; cần TTL, retry, outbox hoặc reconciliation.
2. **Concurrent loader vẫn có thể tái lưu giá trị cũ:** một reader bắt đầu trước commit có thể hoàn tất sau callback và ghi stale value trở lại. Cần versioned keys, loader coordination hoặc consistency protocol.
3. **TransactionAwareCacheDecorator không giữ pending-state để đọc:** `get` trước commit vẫn dùng native cache, không thấy các `put` đang chờ.
4. **Local vs distributed:** callback sau commit không làm cache provider ở tất cả node có immediate/linearizable replication. Kiểm tra consistency/near cache của backend.
5. **Quy trình nền hoặc message broker:** side effect ngoài transaction DB có thể hoàn tất thất bại hoặc trước commit; cache decorator không sắp xếp lại mọi resource.
6. **Application crash:** DB có thể đã commit nhưng process dừng trước hoặc trong callback after-commit. Callback in-process không phải message bền vững. Nếu bắt buộc invalidation eventual nhưng đáng tin, hãy dùng outbox/invalidation event với retry.
7. **Cache stampede:** `clear` sau commit có thể tạo đợt đồng loạt cache miss. Cân nhắc key-level eviction thay vì toàn vùng.

Cách phát biểu chính xác: **transaction-aware cache là cơ chế trì hoãn các cache operations đến sau commit của một Spring synchronization**, không phải transaction coordinator có thể bảo đảm mọi cache entry ở mọi hệ thống đều đồng bộ đúng thời điểm.

## 12. Khi afterCommit callback gặp lỗi

Transaction callback có thể thực thi khi dữ liệu nguồn đã commit. Giả sử:

~~~java
@Override
public void afterCommit() {
    cache.evict("product:42"); // provider có thể ném exception
}
~~~

Đây là snippet mô tả callback, không phải file Java độc lập. Nếu provider ném lỗi, outcome phụ thuộc transaction manager, error propagation và `CacheErrorHandler` khi thao tác được gọi qua caching advice. Điều không thay đổi là **DB commit đã xảy ra**; caller nhận exception sau commit không có nghĩa DB sẽ tự rollback.

Về vận hành:

- Theo dõi lỗi eviction/put qua metric, log và alert; tránh im lặng bỏ qua.
- Với cache có TTL, đánh giá cửa sổ stale tối đa nếu callback bị mất hoặc lỗi.
- Nếu cần delivery guarantee, dùng **transactional outbox** hoặc hàng đợi event đáng tin cậy để retry invalidation sau commit.
- Với remote cache, phân biệt timeout trước khi provider nhận lệnh và timeout sau khi thực thi nhưng chưa trả response. Retry có thể an toàn cho eviction idempotent theo key hơn là cho một số update khác, nhưng vẫn cần định nghĩa rõ ordering/version.
- Không ghi thêm dữ liệu vào database trong `afterCommit` mà mặc định nghĩ nó sẽ thuộc transaction vừa commit. Nếu thực sự cần một DB transaction mới, hãy chủ động dùng propagation `REQUIRES_NEW` cùng manager phù hợp.

## 13. @TransactionalEventListener(AFTER_COMMIT) khác gì decorator?

Một phương án khác là phát domain event trong transaction và xử lý sau commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onProductChanged(ProductChangedEvent event) {
    cacheManager.getCache("products").evict(event.productId());
}
~~~

Đây là **snippet Spring bean**, cần event type, cache manager, import annotation và một event được publish khi transaction active. `@TransactionalEventListener` gắn listener vào transaction lifecycle, hỗ trợ các phase như `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`.

So sánh:

| Cơ chế | Ý tưởng | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| `TransactionAwareCacheDecorator` | Intercept `put/evict/clear` qua Cache rồi defer | Không phải viết listener cho từng method; bao quanh API Cache | Chỉ áp dụng những operation qua decorator; không phải durable messaging |
| `@TransactionalEventListener(AFTER_COMMIT)` | Lắng nghe event khi transaction commit | Tách domain event khỏi policy invalidation; dễ mở rộng consumer | Listener in-process có thể lỗi/mất khi crash; cần định nghĩa event publish/transaction |
| Transactional outbox | Ghi event cùng DB transaction, worker giao nhận sau | Có thể retry và phục hồi khi process chết | Phức tạp hơn; cần idempotency, consumer handling và monitor backlog |

Đừng quên listener `AFTER_COMMIT` có caveat về tài nguyên transaction vẫn có thể còn bind trong callback; thao tác DB mới nếu muốn commit riêng cần transaction mới. Khi dùng async event listener, thời gian thực thi và visibility còn có độ trễ riêng.

Đối với nhiều service/nhiều cache region, event/outbox có thể thích hợp hơn việc gọi cache trực tiếp từ nơi update. Với một ứng dụng Spring đồng bộ và yêu cầu vừa phải, decorator là lựa chọn đơn giản.

## 14. Lỗi thường gặp

**Lỗi 1 – “`@Transactional` tự làm cache after-commit.”** Không chắc; còn phải chọn transaction-aware `CacheManager`, có active synchronization và đúng advice order.

**Lỗi 2 – “`@CacheEvict(beforeInvocation=false)` luôn là after commit.”** Sai; nó là after method invocation trong caching advice, không nhất thiết after DB commit.

**Lỗi 3 – “`cache.put` vừa gọi thì chính transaction đọc được value mới.”** Sai trong decorator: chưa có transaction-local write buffer; `get` có thể còn miss hoặc value cũ.

**Lỗi 4 – “Rollback sẽ hoàn tác `evictIfPresent`.”** Sai: immediate operation đã thay cache trước khi DB quyết định commit/rollback.

**Lỗi 5 – “`TransactionAwareCacheManagerProxy` tự tạo database transaction.”** Sai; nó chỉ bọc cache và nhận callback từ transaction infrastructure có sẵn.

**Lỗi 6 – “Gọi raw cache cũng được.”** Không nếu muốn after-commit; raw native cache bypass decorator và có thể mutate ngay.

**Lỗi 7 – “Sau commit xóa cache thì chắc chắn không stale.”** Concurrent loader, distributed replica và callback failure vẫn gây stale.

**Lỗi 8 – “Rollback thì mọi side effect đều biến mất.”** Tài nguyên ngoài DB transaction có thể đã commit riêng; decorator không rollback HTTP/message/file.

**Lỗi 9 – “Cache callback sau commit thất bại thì DB cũng rollback.”** Sai: DB commit đã hoàn tất. Cần remediation.

**Lỗi 10 – “Chỉ cần đặt `@CacheEvict` trong private method.”** Caching proxy mode không chặn lời gọi private/self-invocation thông thường.

**Lỗi 11 – “Mọi `CacheManager` đã tự bật transaction-aware.”** Không thể khẳng định; xem concrete bean, inheritance/config và wrapper.

**Lỗi 12 – “Một test local ConcurrentMap chứng minh consistency của Redis cluster.”** Sai; integration test với native provider và nhiều node là một bước riêng.

## 15. Kiểm thử và chẩn đoán

Một bộ kiểm thử đầy đủ nên kiểm tra những mốc sau:

| Kiểm thử | Setup | Kỳ vọng |
| --- | --- | --- |
| Deferred put | Transaction active, key trống | Trước commit còn miss; sau commit hit value mới |
| Deferred evict | Key đã có | Trước commit còn entry cũ; sau commit miss |
| Deferred clear | Cache có nhiều key | Trước commit còn entries; sau commit clear |
| Rollback sau put | Đăng ký put rồi rollback | Không thêm entry mới qua callback |
| Rollback sau evict | Đăng ký evict rồi rollback | Entry cũ không bị xóa qua callback |
| Immediate evict | `evictIfPresent` trong transaction | Native key bị xóa ngay khi provider hỗ trợ, rollback không khôi phục |
| No transaction | Gọi decorated put/evict | Delegate ngay, theo provider contract |
| Outer transaction | Method return nhưng outer txn chưa kết thúc | Operation vẫn có thể pending đến outer commit |
| `REQUIRES_NEW` | Transaction inner commit riêng | Callback của inner transaction có thể chạy trước outer commit |
| Cache exception | Native provider ném trong callback | DB commit không tự rollback, phải log/khắc phục |
| Concurrent reader | Reader miss trước/đúng lúc commit | Kiểm tra stale reload race |
| Multi-node | Nhiều instance dùng remote cache | Đo latency invalidation và consistency thực tế |

Cách quan sát:

~~~java
boolean synchronizationActive =
        TransactionSynchronizationManager.isSynchronizationActive();
boolean actualTransactionActive =
        TransactionSynchronizationManager.isActualTransactionActive();
~~~

Đây là snippet cần import `org.springframework.transaction.support.TransactionSynchronizationManager`. Hai boolean nói về **hai khái niệm khác nhau**: synchronization callback có thể đăng ký hay không và có transaction thật đang active hay không. Không dùng hai cờ này như thay thế cho việc kiểm tra dữ liệu đã commit ở DB.

Nếu dùng logger, có thể bật log Spring transaction/cache ở mức DEBUG trong môi trường test để xem thứ tự advisor/callback. Tuy nhiên, một chuỗi log đơn lẻ vẫn không chứng minh distributed visibility. Nên kiểm thử bằng assertions cụ thể, sau commit/rollback và trên các provider cần hỗ trợ.

## 16. Checklist thiết kế production

Trước khi bật transaction-aware cache cho hệ thống:

- Bean `CacheManager` được inject vào Spring caching advisor có thực sự là transaction-aware proxy hoặc manager hỗ trợ `setTransactionAware(true)`?
- Method annotated chạy qua **Spring AOP proxy** và transaction có active synchronization tại lúc put/evict/clear được gọi không?
- Trong code có đường ghi trực tiếp vào native cache bypass decorator không?
- Đối với cache read trong transaction, có chấp nhận **không có read-your-writes** không?
- Nếu một outer transaction rollback, callback cache đã đăng ký có được bỏ qua đúng như mong muốn không?
- Có dùng immediate `putIfAbsent`/`evictIfPresent`/`invalidate` trong transaction không? Có chấp nhận đổi cache trước commit?
- Advisor order và propagation giữa `@CacheEvict`/`@Transactional` đã được integration test trên ứng dụng thật chưa?
- DB commit xong nhưng cache callback thất bại hoặc process crash thì sao? Có TTL/retry/outbox/monitoring không?
- Có hệ thống nhiều node/remote cache và concurrent loader không? Đã xác định SLA về stale window chưa?
- Có thể dùng key-level eviction thay full cache clear để tránh cache stampede không?
- Đã kiểm thử những nhánh commit, rollback-only, exception từ DB, exception từ cache provider và `REQUIRES_NEW` chưa?

## 17. Tài liệu tham khảo chính thức

- [Spring Framework — TransactionAwareCacheDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): mô tả `put`, `evict`, `clear` sau commit và các immediate operations.
- [Spring Framework — TransactionAwareCacheManagerProxy Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html): wrapper cho `CacheManager` và lifecycle.
- [Spring Framework — AbstractTransactionSupportingCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/AbstractTransactionSupportingCacheManager.html): cơ chế manager hỗ trợ cấu hình transaction-aware.
- [Spring Framework — TransactionSynchronizationManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): đăng ký synchronization và truy vấn trạng thái.
- [Spring Framework — TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): `afterCommit`, `afterCompletion` và order.
- [Spring Framework — Cache API Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html): giá trị/timing của `put`, `evict`, `clear`, `evictIfPresent` và `putIfAbsent`.
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, proxy và before/after invocation.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener(AFTER_COMMIT)` và các phase callback.

**Kết luận:** `TransactionAwareCacheDecorator` là lớp thích nghi của Spring Cache cho phép `put`, `evict` và `clear` **chờ đến after-commit khi có transaction synchronization thích hợp**; rollback không chạy callback đó. Đổi lại, cache read trong transaction vẫn có thể thấy trạng thái cũ, immediate operations không được hoãn và lỗi/race sau commit vẫn phải được thiết kế riêng.
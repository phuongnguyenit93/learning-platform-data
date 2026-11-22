# Thao tác có thể trì hoãn và kỳ vọng hiệu lực tức thời trong Spring Cache

## 1. Vấn đề cốt lõi: API trả về không luôn đồng nghĩa đã thấy dữ liệu mới

`org.springframework.cache.Cache` là abstraction mà Spring Framework dùng để đọc, ghi và vô hiệu hóa cache. Một lời gọi `cache.put(key, value)`, `cache.evict(key)` hoặc `cache.clear()` **có thể kết thúc trước khi thao tác ghi/xóa thực sự có hiệu lực đối với lần lookup kế tiếp**. Javadoc Spring Cache cho phép các thao tác này triển khai bất đồng bộ (*asynchronous*) hoặc trì hoãn (*deferred*).

Ngược lại, `putIfAbsent`, `evictIfPresent` và `invalidate` được thiết kế với **kỳ vọng hiệu lực tức thời**. Ý nghĩa thực tế không chỉ nằm ở việc có thêm giá trị trả về: các method này mang contract khác về thời điểm thay đổi có thể quan sát được.

Đây là vấn đề của nhóm **API lập trình**, nhất là khi ứng dụng có Spring-managed transaction, `TransactionAwareCacheDecorator`, Redis/remote cache, Caffeine, concurrent readers hoặc công việc bất đồng bộ.

Các câu hỏi cần trả lời trước khi sử dụng:

- Sau khi `put` return, liệu `get` cùng key có thấy value mới ngay không?
- Sau khi `evict` return, liệu một request khác có còn lấy được entry cũ không?
- `evictIfPresent` hoặc `invalidate` trả `false` có đồng nghĩa thất bại không?
- Khi transaction rollback, lệnh xóa/ghi cache đã được yêu cầu có được thực hiện không?
- Dùng immediate API có đảm bảo đồng bộ nguyên tử với database và mọi node không?
- Tại sao `@CacheEvict(beforeInvocation=true)` vẫn chưa đủ để cam kết xóa cache vật lý ngay?

Mục tiêu của bài là hiểu **hợp đồng API, thời điểm quan sát, transaction-aware behavior và giới hạn provider**, rồi tự kiểm thử bằng một chương trình Java 17 với Spring Cache.

## 2. Bảng so sánh các thao tác Cache

| API | Công dụng | Contract thời điểm | Kết quả trả về |
| --- | --- | --- | --- |
| `void put(Object key, Object value)` | Ghi hoặc thay giá trị | **Có thể** async/deferred, lookup ngay có thể chưa thấy entry | Không có |
| `Cache.ValueWrapper putIfAbsent(key, value)` | Chỉ ghi khi key chưa tồn tại | Được thiết kế cho **immediate registration** | Wrapper của giá trị cũ, hoặc `null` khi trước đó chưa có mapping |
| `void evict(Object key)` | Xóa một mapping | **Có thể** async/deferred, lookup ngay có thể vẫn thấy entry | Không có |
| `boolean evictIfPresent(Object key)` | Xóa một mapping và mong nó mất ngay | **Immediate visibility expectation** | `true` nếu biết key từng có mapping, `false` nếu không có hoặc không xác định được |
| `void clear()` | Xóa tất cả mapping trong cache này | **Có thể** async/deferred | Không có |
| `boolean invalidate()` | Làm toàn cache trở nên không còn entry visible ngay | **Immediate visibility expectation** | `true` nếu biết cache từng có mappings, `false` nếu trống hoặc không xác định được |

`get(key)` là thao tác đọc: nó trả `Cache.ValueWrapper` khi có mapping hoặc `null` khi miss. `ValueWrapper` bản thân có thể chứa giá trị nghiệp vụ `null`; **hit-null khác miss**. Khi test eviction, phải kiểm tra `cache.get(key) == null` thay vì chỉ so sánh `wrapper.get() == null`.

Một cặp ví dụ đối chiếu:

~~~java
cache.evict("u:42");             // Có thể chưa evict xong ở thời điểm return.
cache.evictIfPresent("u:42");    // Mong lookup sau call không còn thấy mapping.

cache.clear();                  // Có thể deferred.
cache.invalidate();             // Mong tất cả mapping không còn visible ngay.
~~~

Đây là **snippet**, cần biến `Cache cache`. Không nên gọi cả hai dòng trong cùng một phép thử rồi kết luận dòng nào thực sự xóa; hãy tạo các tình huống test độc lập.

## 3. “Tức thời” là hợp đồng quan sát cục bộ, không phải ACID toàn hệ thống

Nên phân biệt ba mốc:

1. **Lệnh được gọi:** business code đã gọi `Cache.evict` hoặc `Cache.put`.
2. **Lệnh hoàn tất ở cache implementation:** native store/decorator đã thực thi thao tác tương ứng.
3. **Kết quả được các reader quan sát:** lookup từ cùng cache instance hoặc qua nhiều node/near cache thấy trạng thái sau thay đổi.

Một method trả về ở mốc 1 không luôn có nghĩa mốc 2 và 3 đã xảy ra. Method loại immediate đưa ra yêu cầu mạnh hơn cho mốc 3, nhưng **phải kiểm tra provider có triển khai chính xác hay không**.

“Immediate” không tự bảo đảm mọi replica, cache tầng 1/tầng 2, database transaction và reader ở mọi vùng đều đồng bộ. Trong khi một key bị evict, thread khác vẫn có thể ghi key đó lại ngay sau khi thao tác xong. Đây là **race condition**, không nhất thiết là bug của `evictIfPresent`.

Tương tự, một eviction immediate ở cache trước khi DB commit có thể gây tình huống reader miss, đọc giá trị **cũ** từ DB rồi cache lại, tạo dữ liệu stale sau commit. Phải giải quyết thời điểm commit và reader race riêng.

## 4. Vì sao put/evict/clear được phép trì hoãn?

**Transaction synchronization.** `TransactionAwareCacheDecorator` có thể trì hoãn `put`, `evict`, `clear` để chỉ thao tác native cache trong phase **after-commit** của Spring transaction thành công. Trước commit, cache có thể giữ nguyên entry cũ; nếu rollback, callback after-commit sẽ không chạy.

**Async backend.** Cache hỗ trợ non-blocking hoặc remote write-through có thể đưa yêu cầu vào hàng đợi hoặc gọi backend theo cách bất đồng bộ. Khi method return, chưa chắc reader đã quan sát thay đổi.

**Distributed/near cache.** Việc xóa local mapping và việc phát invalidation sang node khác có thể không cùng một mốc. Backend có thể có consistency policy riêng.

Điều này **không** có nghĩa mọi `put/evict/clear` luôn chậm hoặc luôn deferred. `ConcurrentMapCache` thông thường dùng map trong cùng JVM, thao tác có thể có hiệu lực ngay. Nhưng code dựa trên Spring `Cache` abstraction **không được suy ra bảo đảm chung** từ một implementation local.

### Timeline: trì hoãn eviction

~~~text
T0  Cache["product:42"] = old
T1  Transaction bắt đầu
T2  cache.evict("product:42")       => đăng ký after-commit
T3  cache.get("product:42")         => vẫn có thể thấy old
T4  Database transaction commit
T5  Cache callback afterCommit()   => evict thật
T6  cache.get("product:42")         => MISS nếu không có writer khác
~~~

Timeline trên là **ví dụ của transaction-aware cache**, không phải kết luận bắt buộc đối với mọi cache.

## 5. evictIfPresent và invalidate: hiểu đúng giá trị boolean

Với một cache thực thi đúng immediate semantics:

~~~java
boolean wasPresent = cache.evictIfPresent(key);
Cache.ValueWrapper after = cache.get(key);
// Không có concurrent writer: sau eviction, kỳ vọng after == null.
~~~

`wasPresent == true` nghĩa là cache **biết trước đó có mapping**; `false` có thể nghĩa là **không có mapping**, hoặc implementation **không xác định được** previous presence. Không dùng `false` như mã lỗi.

Tương tự:

~~~java
boolean hadEntries = cache.invalidate();
// hadEntries=false không tự chứng minh thao tác invalidate bị lỗi.
~~~

`invalidate()` hoạt động trên **cache instance/cached region đó**, không tự động trên mọi cache name trong `CacheManager`. `true` cũng không phải số entry bị xóa hay bằng chứng tất cả các node trong hệ thống đã xác nhận.

**Một anti-pattern:**

~~~java
if (!cache.evictIfPresent(id)) {
    throw new IllegalStateException("Eviction failed");
}
~~~

Nhánh exception ở trên sai về mặt semantics: “key vốn không có trong cache” không phải lỗi. Lỗi backend thường được biểu diễn bằng exception riêng hoặc error handling theo provider; còn `false` theo contract có những ý nghĩa bình thường.

## 6. Giới hạn của default implementation

Tên method mạnh hơn không phải lúc nào cũng đồng nghĩa implementation thực sự mạnh hơn:

- `Cache.evictIfPresent(key)` là **default method**. Theo Javadoc, default có thể delegate sang `evict(key)` rồi trả `false` do không xác định được previous presence. Khi `evict` deferred, không thể mặc định default này đem lại visibility tức thời.
- `Cache.invalidate()` có contract kỳ vọng clear immediate, nhưng custom cache dựa vào default method vẫn cần kiểm tra xem việc xóa native entries diễn ra ngay hay không.
- `Cache.putIfAbsent` có contract **conditional insert**, hướng đến atomicity/immediate registration. Tuy nhiên default implementation có thể làm `get(key)` rồi `put(key,value)`, về bản chất không atomic trong tranh chấp đồng thời. Javadoc yêu cầu xem provider-specific semantics.

Với custom `Cache`, cần override đúng nếu hệ thống yêu cầu immediate behavior hoặc atomic conditional insert. Với provider có sẵn, kiểm tra class đang chạy và tài liệu implementation; **không** kiểm tra chỉ dựa trên tên method.

**Mốc version:** `evictIfPresent` và `invalidate` xuất hiện trong Spring Cache API từ Spring Framework 5.2. Các phương thức async `retrieve` thuộc API mới hơn và có những semantics riêng.

## 7. TransactionAwareCacheDecorator và cách đồng bộ sau commit

Spring cung cấp `org.springframework.cache.transaction.TransactionAwareCacheDecorator` để bọc một `Cache`, cũng như `TransactionAwareCacheManagerProxy` để decorate các cache lấy từ một `CacheManager`.

Theo Javadoc, khi **Spring transaction đang active**, decorator đồng bộ `put`, `evict` và `clear` thông qua `TransactionSynchronizationManager`, thực thi native operation trong **after-commit**. Khi **không** có transaction active, các thao tác được delegate để thực thi bình thường ngay.

~~~mermaid
sequenceDiagram
    participant Caller
    participant Tx as Spring Transaction
    participant C as TransactionAwareCacheDecorator
    participant Native as Native Cache

    Caller->>Tx: begin
    Caller->>C: evict(K)
    C->>Tx: register afterCommit callback
    Caller->>C: get(K)
    C->>Native: get(K)
    Native-->>Caller: old vẫn còn
    alt Commit thành công
        Tx->>C: afterCommit()
        C->>Native: evict(K)
    else Rollback
        Note over Tx,Native: không có afterCommit eviction
    end
~~~

Các hệ quả cần nhớ:

1. Trong transaction, `cache.put(K,new)` có thể **chưa visible** cho chính lời gọi `cache.get(K)` ngay sau đó. Decorator không nhất thiết cung cấp một *transaction-local overlay* hay “read your uncommitted cache writes”.
2. Nếu transaction rollback, deferred `put/evict/clear` không chạy callback after-commit; cache giữ trạng thái trước đó (trừ thay đổi khác).
3. Nếu transaction được mở bởi caller ngoài, after-commit có thể đến **muộn hơn** thời điểm business method trả về.
4. `TransactionAwareCacheDecorator` không biến database và cache thành một distributed ACID transaction. Nếu cache provider lỗi khi callback after-commit chạy, cần cơ chế xử lý lỗi/khôi phục riêng.
5. Transaction propagation (`REQUIRES_NEW`, outer rollback, nested savepoint) và advice order quyết định transaction nào đang active khi lệnh được yêu cầu; phải test boundary thực tế.

### Tại sao immediate methods không được deferred như vậy?

`putIfAbsent`, `evictIfPresent` và `invalidate` có ý nghĩa phản hồi/tác động tức thời, nên không thể đơn giản xếp chúng vào callback after-commit mà vẫn giữ contract. Nếu dùng immediate operation trong transaction, bạn chấp nhận cache có thể thay đổi **trước khi biết DB commit hay rollback**.

Ví dụ: `evictIfPresent(K)` rồi transaction rollback khiến entry vẫn bị xóa, dù database không đổi. `putIfAbsent(K,new)` rồi rollback có thể để lại value chưa phản ánh committed DB state. Đây là đánh đổi giữa *visibility ngay* và *commit-consistent cache update*.

## 8. Ví dụ chạy được: Java 17, Maven và TransactionTemplate

Ví dụ này dùng một `ConcurrentMapCache` native và một `TransactionAwareCacheDecorator`. Transaction được điều khiển bởi `TransactionTemplate` với một implementation tối giản của `AbstractPlatformTransactionManager` nhằm tạo **Spring transaction synchronization thật**.

**Lưu ý bắt buộc:** transaction manager trong ví dụ **không quản lý database**, không khóa tài nguyên, không làm rollback dữ liệu nghiệp vụ. Nó chỉ mô phỏng begin/commit/rollback để quan sát callback. Không sử dụng class demo này trong production.

### 8.1. Maven pom.xml

Dùng Spring Framework 6.2.14, Java 17+:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>cache-visibility-demo</artifactId>
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

### 8.2. File src/main/java/demo/CacheVisibilityDemo.java

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.transaction.TransactionAwareCacheDecorator;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

public final class CacheVisibilityDemo {

    private CacheVisibilityDemo() { }

    // Dùng để trình diễn transaction synchronization của Spring.
    // Không phải transaction manager cho database thực.
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
        Cache nativeCache = new ConcurrentMapCache("examples");
        Cache cache = new TransactionAwareCacheDecorator(nativeCache);
        TransactionTemplate tx =
                new TransactionTemplate(new DemoTransactionManager());

        nativeCache.put("a", "v1");
        tx.execute(status -> {
            cache.evict("a");
            System.out.println("evict inside=" + lookup(cache, "a"));
            return null;
        });
        System.out.println("evict after commit=" + lookup(cache, "a"));

        nativeCache.put("b", "v2");
        tx.execute(status -> {
            boolean wasPresent = cache.evictIfPresent("b");
            System.out.println("evictIfPresent wasPresent=" + wasPresent);
            System.out.println("evictIfPresent inside=" + lookup(cache, "b"));
            return null;
        });

        tx.execute(status -> {
            cache.put("c", "v3");
            System.out.println("put inside=" + lookup(cache, "c"));
            return null;
        });
        System.out.println("put after commit=" + lookup(cache, "c"));

        tx.execute(status -> {
            boolean inserted = cache.putIfAbsent("d", "v4") == null;
            System.out.println("putIfAbsent inserted=" + inserted);
            System.out.println("putIfAbsent inside=" + lookup(cache, "d"));
            return null;
        });

        nativeCache.put("e", "v5");
        tx.execute(status -> {
            cache.clear();
            System.out.println("clear inside=" + lookup(cache, "e"));
            return null;
        });
        System.out.println("clear after commit=" + lookup(cache, "e"));

        nativeCache.put("f", "v6");
        tx.execute(status -> {
            boolean hadEntries = cache.invalidate();
            System.out.println("invalidate hadEntries=" + hadEntries);
            System.out.println("invalidate inside=" + lookup(cache, "f"));
            return null;
        });

        nativeCache.put("g", "v7");
        tx.execute(status -> {
            cache.evict("g");
            status.setRollbackOnly();
            System.out.println("rollback inside=" + lookup(cache, "g"));
            return null;
        });
        System.out.println("rollback after=" + lookup(cache, "g"));
    }
}
~~~

### 8.3. Chạy và quan sát

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheVisibilityDemo
~~~

Các dòng do chương trình tự in (không tính log Maven/Spring):

~~~text
evict inside=v1
evict after commit=MISS
evictIfPresent wasPresent=true
evictIfPresent inside=MISS
put inside=MISS
put after commit=v3
putIfAbsent inserted=true
putIfAbsent inside=v4
clear inside=v5
clear after commit=MISS
invalidate hadEntries=true
invalidate inside=MISS
rollback inside=v7
rollback after=v7
~~~

Diễn giải:

1. `evict("a")` chỉ đăng ký callback: trong transaction vẫn thấy `v1`; sau commit mới miss.
2. `evictIfPresent("b")` immediate trên `ConcurrentMapCache`, trả `true` vì mapping có trước đó, và lookup ngay trong transaction là miss.
3. `put("c","v3")` chưa visible trong transaction; sau commit thấy `v3`.
4. `putIfAbsent("d","v4")` ghi ngay, return `null` vì key chưa tồn tại, và subsequent lookup thấy `v4`.
5. `clear()` hoãn đến commit nên trong transaction vẫn thấy `e=v5`; sau commit miss.
6. `invalidate()` xóa ngay toàn cache tại thời điểm gọi trong demo; `true` vì cache có entries trước đó.
7. `evict("g")` được yêu cầu nhưng transaction rollback, callback after-commit không chạy; `g=v7` còn nguyên.

Các kết quả được suy ra từ contract và logic code; ví dụ Java **chưa được thực sự chạy trong môi trường của tài liệu**. Khi áp dụng trong dự án, hãy chạy bằng dependency/version đã chọn và bổ sung test trên transaction manager/provider thật.

## 9. putIfAbsent: immediate khác với overwrite và atomicity

`putIfAbsent(key,value)` không phải một phiên bản “nhanh hơn” của `put`:

- Nếu key **chưa có entry**, provider sẽ attempt insert và thường trả `null` vì không có previous value.
- Nếu key **đã có entry**, operation giữ nguyên mapping cũ, trả `Cache.ValueWrapper` của value cũ. Nếu mapping cũ lưu **cached null**, wrapper vẫn có thể khác null dù `wrapper.get()==null`.
- Nếu ứng dụng cần cập nhật giá trị cũ sang mới, **không thay `put` bằng `putIfAbsent`**; nếu key đã có, giá trị mới sẽ không ghi.
- Atomicity ở môi trường nhiều thread phải được kiểm tra tại implementation. Javadoc nói default có thể delegate `get` rồi `put` và không bảo đảm atomic tương đương native compute-if-absent.

~~~java
Cache.ValueWrapper previous = cache.putIfAbsent(key, candidate);
if (previous == null) {
    // Chưa có entry trước operation: attempt insert.
} else {
    Object oldValue = previous.get(); // Có thể chính là cached null.
    // candidate không được ghi thay value trước đó.
}
~~~

Snippet trên yêu cầu biến `Cache cache` và key/candidate đã được định nghĩa. Không kết luận transaction rollback sẽ xóa candidate đã immediate-put; hãy thiết kế riêng if needed.

## 10. evictIfPresent không loại bỏ race với loader

Giả sử một reader đang tải giá trị cũ từ database và một writer evict:

~~~text
Reader A: Cache miss; bắt đầu DB read, kết quả chưa trở về
Writer B: DB update; evictIfPresent(K) => không còn entry K
Reader A: DB read cũ hoàn thành; put(K, oldValue)
Reader C: Cache hit K=oldValue
~~~

Trình tự này có thể xảy ra dù `evictIfPresent(K)` hoàn thành đúng nghĩa immediate ở một cache instance. Nó không ngăn reader A **ghi dữ liệu cũ trở lại** sau eviction.

Những cách giảm rủi ro tùy mức consistency yêu cầu:

- Invalidation **sau DB commit** hoặc cơ chế after-commit đáng tin cậy.
- Versioned cache key hoặc version/generation check để old loader không thể ghi vào namespace hiện tại.
- Timeout/TTL và telemetry về stale reads.
- Synchronization/CAS/locking phù hợp khi dữ liệu cực nhạy với concurrency.
- Gắn invalidation event tới near caches và node khác với mức delivery phù hợp.

Không dùng cache là nguồn sự thật duy nhất cho invariant phải do database/transaction đảm bảo.

## 11. clear và invalidate: phạm vi, chi phí, cạnh tranh

`clear()` và `invalidate()` tác động tới **tất cả entries của một cache được chọn**, không tự làm sạch mọi cache name trong `CacheManager` hay mọi tầng local/remote trong ứng dụng khác.

- `clear()` có thể defer và khiến lookup ngay vẫn thấy entries cũ.
- `invalidate()` mong các entries không còn visible ngay trong semantics implementation.
- `invalidate() == false` không phải failure. Có thể cache trống, hoặc không xác định được trước đó có entries hay không.
- Clear/invalidate toàn cache có thể tạo **cache stampede**: đồng thời nhiều request miss rồi truy cập DB/upstream. Cần capacity planning và đôi khi background warming.
- Nếu nhiều cache có key schema khác nhau, phải invalidate đúng cache names; không mở rộng xóa toàn hệ thống chỉ để xử lý một key.

Với `@CacheEvict(allEntries=true)`, annotation có semantics clear cache theo `Cache` operation, **không tự chọn `invalidate()` chỉ vì caller cần immediate visibility**. Nếu immediate là một yêu cầu nghiệp vụ mạnh, hãy dùng direct API có verify provider hoặc thiết kế invalidation riêng.

## 12. Annotation và transaction: hai tầng thời gian độc lập

Trường hợp thường gặp:

~~~java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public void updateProduct(long id, String name) {
    repository.rename(id, name);
}
~~~

Đây là snippet trong một Spring bean có repository/transaction manager, không phải chương trình độc lập. Có hai tầng:

1. **Cache annotation timing:** `beforeInvocation=false` nghĩa là annotation yêu cầu eviction sau khi method mà cache advice quan sát return bình thường.
2. **Cache provider/decorator timing:** sau khi yêu cầu eviction, `Cache.evict` có thể thực hiện ngay, defer đến after-commit hoặc async tùy cache đang active.

**Do đó không đồng nhất** `@CacheEvict(beforeInvocation=true)` với “native entry bị xóa vật lý trước business method” nếu có transaction-aware cache đang active. Chỉ thay thứ tự annotation advice mà không xét transaction boundary và cache decorator có thể gây lỗi.

Nếu transaction rollback sau khi method return, deferred eviction có thể không chạy. Nếu method ném exception trước khi after-invocation eviction được yêu cầu, operation đó cũng không chạy. Cả hai tình huống đều cần hiểu chính xác trước khi dùng cache như tín hiệu business state.

## 13. API bất đồng bộ và remote provider

Spring Framework 6.1 bổ sung `Cache.retrieve(key)` và `Cache.retrieve(key, Supplier<CompletableFuture<T>>)` cho các implementation hỗ trợ async retrieval. Với những cache cần hỗ trợ `CompletableFuture`/reactive, Javadoc nêu `put`/`evict`/`clear` nên **effectively non-blocking**, với backend write-through có thể chạy async.

Đừng nhầm:

- `CompletableFuture` từ `retrieve` là contract **trả kết quả**, không phải bằng chứng `put`/`evict` đã áp dụng ở mọi replica.
- Cache native API của Redis/Caffeine có thể có semantics riêng, khác Spring `Cache`.
- “Evict immediate” ở một node chưa chắc có nghĩa near cache mọi node đều đã cập nhật, nếu provider không cung cấp guarantee đó.
- Runtime test một thread với `ConcurrentMapCache` không thể chứng minh một thiết kế distributed với Redis, transaction-aware decorator và nhiều service instance.

Khi có concurrency/async, phải test các mốc: call return, native change, local get, remote get, loader completion và database commit.

## 14. Ma trận lựa chọn API

| Nhu cầu | API/cơ chế có thể chọn | Điều cần kiểm tra |
| --- | --- | --- |
| Ghi giá trị mới, overwrite được | `put` | Có bị deferred? Read-your-writes có được bảo đảm không? |
| Chỉ ghi nếu key chưa tồn tại | `putIfAbsent` | Atomicity, previous wrapper, rollback risk |
| Evict một key, có thể đợi commit | `evict` qua transaction-aware cache | Transaction active và callback after-commit |
| Xóa key và mong lookup sau call miss | `evictIfPresent` | Override của provider, concurrent writers, DB race |
| Invalidate toàn cache và có thể hoãn | `clear` | Chi phí reload và transaction boundary |
| Invalidate toàn cache với immediate expectation | `invalidate` | Provider semantics, distributed visibility, boolean |
| Tránh cache chứa dữ liệu chưa commit | Deferred `put` sau commit | Đừng mong get trước commit thấy new value |
| Đảm bảo database + cache nhất quán mạnh | Transaction/consistency design riêng | Cache operation không thay DB transaction |
| Tối ưu latency cho async backend | Non-blocking cache operations | Completion/visibility và exception handling |

Với yêu cầu nghiệp vụ quan trọng, hãy ghi rõ **thời điểm nào được coi là thành công** và **reader nào cần nhìn thấy thay đổi** thay vì chọn method chỉ vì tên có từ `Present` hoặc `invalidate`.

## 15. Lỗi phổ biến

**Lỗi 1.** “`put` return thì `get` thấy value mới ngay.” Sai với deferred/async cache.

**Lỗi 2.** “`evict` return thì key chắc chắn đã mất.” Sai nếu provider trì hoãn.

**Lỗi 3.** “`evictIfPresent` trả `false` là lỗi xóa.” Sai; trước đó có thể không có key hoặc không xác định được presence.

**Lỗi 4.** “`invalidate` trả `false` nghĩa là vẫn còn entry.” Sai theo contract boolean.

**Lỗi 5.** “`putIfAbsent` cập nhật value cũ nhanh hơn `put`.” Sai: nó không overwrite.

**Lỗi 6.** “Default implementation `putIfAbsent` luôn atomic.” Không nên giả định; Javadoc cho phép default tương đương get rồi put.

**Lỗi 7.** “Chỉ cần gọi immediate API trong transaction là DB/cache cùng rollback.” Sai: immediate operation có thể đã hoàn tất trước rollback DB.

**Lỗi 8.** “TransactionAwareCacheDecorator tự tạo distributed transaction.” Sai: nó phối hợp callback, không thực hiện 2-phase commit giữa DB và cache.

**Lỗi 9.** “`@CacheEvict(beforeInvocation=true)` là bảo đảm native eviction immediate.” Sai nếu tầng cache/decorator còn defer.

**Lỗi 10.** “Immediate eviction chống mọi stale read.” Concurrent loader/near cache có thể ghi hoặc trả giá trị cũ.

**Lỗi 11.** “`invalidate` ảnh hưởng mọi cache name.” Nó xóa mappings của cache instance được gọi.

**Lỗi 12.** “Test `ConcurrentMapCache` đủ chứng minh Redis production.” Không đủ; phải test implementation, transaction and network thật.

## 16. Checklist kiểm thử và tài liệu

Một integration test nên chứng minh lần lượt:

1. Trong transaction-aware cache, `put/evict/clear` chưa visible trước commit, visible sau commit.
2. Rollback không chạy callback after-commit.
3. `putIfAbsent` ghi ngay khi key trống, không overwrite khi key tồn tại.
4. `evictIfPresent` và `invalidate` có immediate behavior theo implementation đã chọn.
5. Boolean return được giải thích đúng khi entry không tồn tại.
6. Cached-null và cache miss không bị nhầm khi kiểm tra `Cache.ValueWrapper`.
7. Multiple threads/loaders không tái tạo stale entry sau invalidation quan trọng.
8. Transaction manager, advice order, outer/inner transactions được test với DB thực khi cần consistency.
9. Cross-node/near cache thực sự đạt visibility target nếu sản phẩm có SLA.
10. Error handler, timeout và backend outage không khiến dữ liệu stale bị bỏ qua âm thầm.

Nguồn đọc chính thức:

- [Spring Cache API Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html) — `put`, `putIfAbsent`, `evict`, `evictIfPresent`, `clear`, `invalidate`, `retrieve`.
- [TransactionAwareCacheDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html) — after-commit synchronization và immediate methods.
- [TransactionAwareCacheManagerProxy Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html) — bọc `CacheManager`.
- [ConcurrentMapCache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html) — cache trong JVM, override các immediate operations.
- [Spring Framework Cache Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html) — annotation timing so với cache operations.
- [TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html) — transaction callback API.

**Tổng kết:** `put`, `evict`, `clear` có thể deferred; `putIfAbsent`, `evictIfPresent`, `invalidate` biểu diễn kỳ vọng hiệu lực tức thời. Cần đọc contract/provider implementation, xác định transaction boundary và kiểm thử concurrency để biến kỳ vọng đó thành tính đúng đắn thực tế.
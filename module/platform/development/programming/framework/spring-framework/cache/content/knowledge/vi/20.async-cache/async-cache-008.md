# Thời điểm @CachePut và @CacheEvict theo kết quả bất đồng bộ

## Mục tiêu

Bài học thuộc nhóm **Bất đồng bộ** của Spring Framework Cache. Sau bài này, bạn sẽ:

- Phân biệt thời điểm method Java **trả về** một `CompletableFuture<T>` với thời điểm future **hoàn tất** thành công hoặc thất bại.
- Giải thích chính xác khi nào `@CachePut` ghi cache và `@CacheEvict` xóa cache trong đường xử lý kết quả bất đồng bộ được Spring hỗ trợ.
- Phân biệt `@CacheEvict` mặc định (sau invocation và sau kết quả thành công) với `beforeInvocation = true` (phát lệnh evict trước khi chạy method).
- Tự kiểm chứng trạng thái cache **khi future còn pending**, sau `complete(...)` và sau `completeExceptionally(...)`.
- Nhận diện các giới hạn quan trọng của Reactor `Mono`/`Flux`, Spring `@Async`, AOP proxy, transaction, cancellation, race condition và cache provider.
- Xây dựng bài test không phụ thuộc `Thread.sleep` trên Spring Boot + Java 17+.

**Ý chính:** trong Spring Framework **6.1+**, Spring Cache hỗ trợ thích ứng với `CompletableFuture` và các kiểu reactive được công nhận. Với những operation theo kết quả, **method trả future chưa có nghĩa thao tác nền đã thành công**. `@CachePut` dùng giá trị hoàn tất thành công, trong khi `@CacheEvict` sau invocation đợi completion thành công; `beforeInvocation=true` là trường hợp xóa trước và không chờ outcome. Phải kiểm tra phiên bản Spring và backend thật trước khi dựa vào timing này.

## 1. Ba mốc thời gian cần phân biệt

Giả sử một phương thức cập nhật tài liệu:

~~~java
@CachePut(cacheNames = "documents", key = "#p0")
public CompletableFuture<String> update(String id) {
    return remoteRepository.updateAsync(id);
}
~~~

Đây là **đoạn minh họa**, trong đó `remoteRepository` là dependency nghiệp vụ.

Có ba thời điểm:

1. **T0 — Interceptor nhận lời gọi:** caller gọi Spring bean qua proxy; Spring cache advice xác định cache operation và key.
2. **T1 — Method trả một handle chưa hoàn thành:** Java đã quay về caller với `CompletableFuture<String>` nhưng I/O hoặc tác vụ nền vẫn pending.
3. **T2 — Completion signal:** future có thể hoàn tất thành công với `String`, hoàn tất exceptionally, bị cancel, hoặc không bao giờ hoàn tất.

~~~text
T0                           T1                            T2
|----------------------------|-----------------------------|
gọi update("D1")             trả future PENDING            future success("new")
                             cache vẫn giữ "old"          cache được put "new"

Nếu T2 = exceptional completion: không có giá trị thành công mới để put.
~~~

**Không nhập T1 và T2 làm một.** Kết thúc phần thân method không đồng nghĩa thành công nghiệp vụ nếu kết quả trả về còn pending. Ngoài ra, completion của một future cũng không mặc định tương đương **database transaction commit** hoặc toàn bộ side effect ở hệ thống ngoài đã hoàn tất.

## 2. @CachePut với kết quả bất đồng bộ

`@CachePut` khác `@Cacheable`: nó yêu cầu thực thi method và, khi caching operation được áp dụng, đưa kết quả thích hợp vào cache. Nó **không bỏ qua** thân method chỉ vì đã có entry cùng key.

### 2.1. Thành công sau khi future hoàn tất

~~~java
@CachePut(cacheNames = "documents", key = "#p0")
public CompletableFuture<String> update(String id) {
    return serviceClient.updateAsync(id);
}
~~~

Giả sử `documents["D1"] = "old"`:

~~~text
Trước lời gọi             cache["D1"] = "old"
Method trả PENDING         cache["D1"] vẫn = "old"
Future success("new")      Spring xử lý put giá trị "new"
Sau completion             cache["D1"] = "new"
~~~

Với hỗ trợ async-aware, kết quả được đưa vào cache là **giá trị nghiệp vụ đã hoàn tất**, không phải do annotation cố lưu một `CompletableFuture` chưa xong như thể là `String`.

### 2.2. Nếu future thất bại

~~~text
T0: cache["D1"] = "old"
T1: update("D1") trả incomplete future
T2: future.completeExceptionally(error)
    → không có value mới thành công
    → cache vẫn có "old" trong kịch bản không có writer khác
~~~

Trong trường hợp lỗi, caller vẫn phải xử lý future failed. Cần phân biệt **không put do lỗi** với việc một request khác cũng có thể đã đổi cache cùng key.

### 2.3. unless và #result

~~~java
@CachePut(
    cacheNames = "documents",
    key = "#p0",
    unless = "#result == null")
public CompletableFuture<String> update(String id) {
    return serviceClient.updateAsync(id);
}
~~~

`unless` là điều kiện sau khi có kết quả; khi Spring thích ứng đúng future, `#result` có thể phản ánh **giá trị đã hoàn tất** để quyết định bỏ qua put. `condition` thường dựa trên đối số để quyết định có thực hiện cache operation hay không. Nếu future hoàn tất thành công bằng `null`, chính sách `unless` và khả năng cached null của backend quyết định liệu có entry mới.

Không coi exception hoặc cancelled future là một `#result` bình thường để cache. Đoạn ví dụ trên chỉ minh họa, không phải một Java file độc lập.

## 3. @CacheEvict: sau thành công hay trước khi gọi method?

### 3.1. Mặc định: afterInvocation

~~~java
@CacheEvict(cacheNames = "documents", key = "#p0")
public CompletableFuture<Void> delete(String id) {
    return serviceClient.deleteAsync(id);
}
~~~

Giá trị mặc định là `beforeInvocation = false`. Với kết quả bất đồng bộ mà Spring hỗ trợ, evict sau invocation gắn với **completion thành công**, không chỉ việc đã trả về future.

~~~text
Cache ban đầu                documents["D1"] = "old"
Method trả pending future    documents["D1"] = "old"

Nếu future complete(null) thành công:
  → evict key D1
  → documents["D1"] vắng mặt

Nếu future completeExceptionally(error):
  → không thực hiện evict theo nhánh sau thành công
  → entry "old" được giữ (nếu không có writer khác)
~~~

Một `CompletableFuture<Void>` **hoàn tất thành công bằng null** vẫn là success. Không nhầm `null` của kiểu `Void` với exception hoặc cancellation.

### 3.2. beforeInvocation=true

~~~java
@CacheEvict(
    cacheNames = "documents",
    key = "#p0",
    beforeInvocation = true)
public CompletableFuture<Void> delete(String id) {
    return serviceClient.deleteAsync(id);
}
~~~

Ở chế độ này, cache interceptor phát lệnh `evict` **trước khi method được gọi**:

~~~text
T0: cache["D1"] = "old"
T1: gọi delete("D1") qua proxy
    → phát lệnh evict("D1") trước khi chạy method
T2: method trả future PENDING; entry đã bị yêu cầu xóa
T3: future FAILS; eviction trước invocation KHÔNG tự rollback
~~~

Đây là lựa chọn có chủ đích nếu bạn cần chủ động không phục vụ dữ liệu cũ ngay từ đầu thao tác, bất kể outcome. Nó có thể gây cache miss và reload ngay cả khi update/delete cuối cùng thất bại.

**Ngoại lệ về transaction:** nếu underlying Spring `Cache` được bọc bởi `TransactionAwareCacheManagerProxy` hoặc decorator transaction-aware, lệnh `evict` được *phát* trước invocation nhưng **có thể được thực thi sau transaction commit**. `beforeInvocation` chỉ xác định thứ tự tương đối với lời gọi method; nó không bỏ qua chính sách trì hoãn của cache decorator.

### 3.3. Bảng so sánh mốc thời gian

| Annotation | Method trả incomplete future | Future success | Future exceptional/cancel |
| --- | --- | --- | --- |
| `@CachePut` | Chưa có value hoàn tất để put | Put kết quả thực nếu điều kiện cho phép | Không put kết quả lỗi |
| `@CacheEvict` mặc định | Giữ entry trong lúc pending | Evict entry/vùng theo cấu hình | Không thực hiện eviction sau thành công |
| `@CacheEvict(beforeInvocation=true)` | Đã phát lệnh evict trước khi method bắt đầu | Không cần đợi để evict | Eviction sớm không được tự phục hồi |
| `@Cacheable` (đối chiếu) | Lookup/miss/hit theo provider | Có thể cache giá trị hoàn tất | Không có giá trị thành công để ghi |

Bảng mô tả **Spring Framework 6.1+** với return types được hỗ trợ và trong ngữ cảnh không có deferred transaction adapter; phiên bản cũ hoặc provider khác có thể có semantics khác.

## 4. Phiên bản, kiểu dữ liệu trả về và provider

Spring Framework 6.1 mở rộng cache annotation adaptation cho `CompletableFuture` và Reactor types. Để sử dụng bài này, cần xác minh:

- **Phiên bản:** Spring Framework 6.1+ (ví dụ các dòng Spring Boot từ 3.2 khi dùng cấu hình tương thích). Java 17 không tự đem lại khả năng annotation async-aware.
- **Return type:** `CompletableFuture<T>` được hỗ trợ; không suy luận mọi loại `java.util.concurrent.Future<T>` tùy biến hoặc callback library bất kỳ được đối xử giống nhau.
- **Provider:** manager phải cung cấp vùng đúng tên và hỗ trợ operations mà caching infrastructure thực hiện. Với async `@Cacheable`/`Cache.retrieve` hoặc reactive caching, khả năng async retrieval của provider đặc biệt quan trọng.
- **Proxy:** `@EnableCaching` được bật và method được gọi qua Spring-managed proxy. Lời gọi `this.method()` thường bypass cache advice ở proxy mode.
- **Completion:** success, failure, cancel, null, timeout và empty reactive publisher là những trường hợp khác nhau phải test riêng.

Ví dụ này sử dụng `ConcurrentMapCacheManager` để kiểm tra `put/evict`. Với Caffeine, Redis hoặc JCache, hãy kiểm tra integration tests trên backend thực tế. TTL, độ bền và đồng bộ giữa replica **không** được định nghĩa bởi `@CachePut` hay `@CacheEvict`.

## 5. Demo Java 17+: kiểm chứng đúng thời điểm bằng CompletableFuture điều khiển thủ công

Đây là ví dụ Spring Boot Java 17+ **không có cơ sở dữ liệu thật**. Những future do một bean điều khiển tạo ra, giúp kiểm tra cache trước/sau success và failure mà không dựa vào `Thread.sleep`, thread scheduler hoặc network. Sử dụng một dự án Spring Boot Gradle có plugin/version Spring 6.1+ phù hợp, bổ sung dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Bốn file Java bên dưới thuộc package `example.asyncresultcache`.

### 5.1. PendingSignals.java

Đặt tại `src/main/java/example/asyncresultcache/PendingSignals.java`:

~~~java
package example.asyncresultcache;

import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Component;

@Component
public class PendingSignals {
    private CompletableFuture<String> pendingWrite;
    private CompletableFuture<Void> pendingDelete;
    private CompletableFuture<Void> pendingEarlyDelete;

    public CompletableFuture<String> beginWrite() {
        pendingWrite = new CompletableFuture<>();
        return pendingWrite;
    }

    public void succeedWrite(String value) {
        pendingWrite.complete(value);
    }

    public void failWrite() {
        pendingWrite.completeExceptionally(
                new IllegalStateException("write failed"));
    }

    public CompletableFuture<Void> beginDelete() {
        pendingDelete = new CompletableFuture<>();
        return pendingDelete;
    }

    public void succeedDelete() {
        pendingDelete.complete(null);
    }

    public void failDelete() {
        pendingDelete.completeExceptionally(
                new IllegalStateException("delete failed"));
    }

    public CompletableFuture<Void> beginEarlyDelete() {
        pendingEarlyDelete = new CompletableFuture<>();
        return pendingEarlyDelete;
    }

    public void failEarlyDelete() {
        pendingEarlyDelete.completeExceptionally(
                new IllegalStateException("early delete failed"));
    }
}
~~~

Bean này **chỉ dùng cho demo tuần tự**: mỗi lần chỉ giữ một future pending cho từng loại thao tác. Không dùng các field pending toàn cục này trong production với nhiều request đồng thời.

### 5.2. AsyncDocumentService.java

Đặt tại `src/main/java/example/asyncresultcache/AsyncDocumentService.java`:

~~~java
package example.asyncresultcache;

import java.util.concurrent.CompletableFuture;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.stereotype.Service;

@Service
public class AsyncDocumentService {
    private final PendingSignals signals;

    public AsyncDocumentService(PendingSignals signals) {
        this.signals = signals;
    }

    @CachePut(cacheNames = "documents", key = "#p0")
    public CompletableFuture<String> update(String id) {
        return signals.beginWrite();
    }

    @CacheEvict(cacheNames = "documents", key = "#p0")
    public CompletableFuture<Void> delete(String id) {
        return signals.beginDelete();
    }

    @CacheEvict(
            cacheNames = "documents",
            key = "#p0",
            beforeInvocation = true)
    public CompletableFuture<Void> deleteBefore(String id) {
        return signals.beginEarlyDelete();
    }
}
~~~

Các method là `public`, nằm trên bean Spring và được gọi từ bean khác trong demo, nên AOP caching interceptor có thể áp dụng. `key = "#p0"` tạo key từ tham số đầu tiên, thống nhất với key `"D1"` ta tự đưa vào cache.

### 5.3. CacheConfiguration.java

Đặt tại `src/main/java/example/asyncresultcache/CacheConfiguration.java`:

~~~java
package example.asyncresultcache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("documents");
    }
}
~~~

`@EnableCaching` cần cho đường annotation; nó không tự tạo TTL, distributed cache hoặc database transaction. Demo dùng một cache region có tên `documents`, lưu trong JVM.

### 5.4. AsyncCacheDemoApplication.java

Đặt tại `src/main/java/example/asyncresultcache/AsyncCacheDemoApplication.java`:

~~~java
package example.asyncresultcache;

import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AsyncCacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncCacheDemoApplication.class, args);
    }

    private static void expectFailure(CompletableFuture<?> future) {
        try {
            future.join();
            throw new AssertionError("Expected exceptional completion");
        } catch (CompletionException expected) {
            // Exception đã được quan sát.
        }
    }

    @Bean
    CommandLineRunner demo(
            AsyncDocumentService service,
            PendingSignals signals,
            CacheManager manager) {

        return args -> {
            Cache cache = Objects.requireNonNull(
                    manager.getCache("documents"),
                    "documents cache missing");

            // 1) @CachePut: chưa completed thì cache vẫn là "old".
            cache.put("D1", "old");
            CompletableFuture<String> pendingPut =
                    service.update("D1");
            System.out.println("put future pending = " +
                    !pendingPut.isDone());
            System.out.println("put before success = " +
                    cache.get("D1", String.class));
            signals.succeedWrite("new");
            pendingPut.join();
            System.out.println("put after success = " +
                    cache.get("D1", String.class));

            // 2) Future update lỗi: không có value để put.
            CompletableFuture<String> failedPut = service.update("D1");
            signals.failWrite();
            expectFailure(failedPut);
            System.out.println("put after failure = " +
                    cache.get("D1", String.class));

            // 3) @CacheEvict after-invocation đợi completion.
            CompletableFuture<Void> pendingDelete =
                    service.delete("D1");
            System.out.println("evict before success = " +
                    cache.get("D1", String.class));
            signals.succeedDelete();
            pendingDelete.join();
            System.out.println("evict after success = " +
                    cache.get("D1", String.class));

            // 4) Future delete lỗi: entry cũ vẫn được giữ.
            cache.put("D1", "seed");
            CompletableFuture<Void> failedDelete = service.delete("D1");
            signals.failDelete();
            expectFailure(failedDelete);
            System.out.println("evict after failure = " +
                    cache.get("D1", String.class));

            // 5) Evict trước invocation: pending đã xóa.
            CompletableFuture<Void> early = service.deleteBefore("D1");
            System.out.println("early evict pending = " +
                    cache.get("D1", String.class));
            signals.failEarlyDelete();
            expectFailure(early);
            System.out.println("early evict after failure = " +
                    cache.get("D1", String.class));
        };
    }
}
~~~

Chạy tại thư mục dự án:

~~~bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
~~~

**Các dòng do chương trình in qua `System.out`, theo thứ tự** (không kể log Spring Boot/Gradle):

~~~text
put future pending = true
put before success = old
put after success = new
put after failure = new
evict before success = new
evict after success = null
evict after failure = seed
early evict pending = null
early evict after failure = null
~~~

**Phân tích đúng từng mốc:**

1. `pendingPut` chưa complete nên `!pendingPut.isDone()` là true. Khi Spring theo dõi tương lai, cache vẫn `old` thay vì lập tức chứa `new`.
2. `signals.succeedWrite("new")` hoàn thành future thành công. Cache operation cập nhật `documents["D1"]` thành `new`; `pendingPut.join()` bảo đảm đường kết quả đã hoàn tất khi kiểm tra.
3. Future `failedPut` hoàn thành exceptionally, nên không put thêm; cache vẫn `new`. Demo dùng `expectFailure` để quan sát kết quả thất bại mà không làm application dừng.
4. `service.delete("D1")` với annotation mặc định trả incomplete future; cache vẫn `new`. Sau `succeedDelete()`, future hoàn tất thành công bằng null (vì `Void`) nên entry bị evict; `cache.get("D1", String.class)` trả `null`.
5. Với delete lỗi, cache được nạp lại `seed` trước khi gọi. Future failure khiến after-invocation eviction không diễn ra, nên vẫn `seed`.
6. Với `deleteBefore`, cache bị evict ngay khi method được gọi qua proxy. Khi future vẫn pending, đọc đã thấy `null`. Exceptional completion về sau **không phục hồi** entry.

Điểm mạnh của ví dụ là không phụ thuộc vào độ trễ thực tế. Nó chứng minh completion timing, **không** chứng minh transaction commit hoặc tác dụng thật ở DB/remote system. Nếu chạy trên Spring phiên bản cũ, expected output có thể khác; đó chính là lý do phải kiểm tra version.

## 6. CompletableFuture lỗi, bị hủy và trả null

### Exceptional completion

~~~java
CompletableFuture<String> pending = new CompletableFuture<>();
pending.completeExceptionally(
        new IllegalStateException("remote write failed"));
~~~

Method vẫn có thể đã **trả future bình thường**, nhưng future sau đó thất bại. Caller có thể thấy `CompletionException` khi `join()`, hoặc xử lý bằng `handle`/`whenComplete`. `@CachePut` không có result nghiệp vụ thành công để ghi, `@CacheEvict` after-invocation không có successful completion để xóa. Tuy nhiên remote service có thể **đã commit rồi mới timeout**; một failure signal không bảo đảm database chưa bị đổi.

### Cancellation

~~~java
CompletableFuture<String> pending = new CompletableFuture<>();
pending.cancel(true);
~~~

Cancel là completion không bình thường, không nên coi là “update thành công” để put/evict after-invocation. Nhưng việc hủy future handle **không chắc** hủy I/O thực tế. Nếu remote side effect xảy ra dù caller cancel, hệ thống cần reconcile cache với nguồn.

### Null và CompletableFuture<Void>

`CompletableFuture<Void>` thành công với `complete(null)` là normal completion, phù hợp để `@CacheEvict` after-invocation thực hiện evict. Với `@CachePut`, `CompletableFuture<String>` có value `null` là normal success nhưng có ghi null hay không phụ thuộc `unless` và khả năng cached null của cache provider. Không nhầm **no value** với **exception**.

### Future không bao giờ hoàn thành

Nếu future bị treo, operation sau thành công cũng không có mốc để chạy. Thiết lập timeout/circuit breaker, giám sát số future pending và tránh giữ closure/context vô hạn. Không dùng caching annotation để giải quyết lifecycle của remote I/O.

## 7. Reactive: Mono/Flux không giống Java method return

Spring Framework 6.1+ cũng có khả năng thích ứng với các kiểu reactive phổ biến khi Reactor có mặt:

- `Mono<T>` đại diện zero hoặc one value. Việc Java method trả `Mono` thường chỉ tạo một publisher **lazy**; giá trị thật xuất hiện trong pipeline khi được subscribe.
- `Flux<T>` có thể phát nhiều item. Spring Cache abstraction có thể gom danh sách các item phát ra để cache như **một aggregate**, không tạo một entry riêng cho mỗi `onNext`.
- `@CachePut` trên reactive return cần xét **kết quả/pipeline được materialize**, không mặc định method trả publisher đã tương đương với việc lưu cache thành công.
- `@CacheEvict` after-invocation theo đường reactive được hỗ trợ gắn với **successful terminal signal**, không phải tạo publisher.
- `Mono.empty()` và `Flux.empty()` là successful completion **không có item**, khác `onError`. Cần test riêng behavior với empty/null policy và provider.
- Subscription cancellation không chứng minh remote side effect đã bị rollback.

~~~java
// Minh họa Reactor; cần dependency Reactor và remoteClient thực.
@CachePut(cacheNames = "documents", key = "#p0")
public reactor.core.publisher.Mono<String> updateReactive(String id) {
    return remoteClient.update(id);
}

@CacheEvict(cacheNames = "documents", key = "#p0")
public reactor.core.publisher.Mono<Void> deleteReactive(String id) {
    return remoteClient.delete(id);
}
~~~

Đoạn code này **không nằm trong project demo mục 5** và không phải Java standalone. Với các stream lớn hoặc vô hạn, không nên dùng tính năng tự động gom `Flux` thành cache list mà không xem xét bộ nhớ/backpressure.

Với backend có asynchronous retrieval, ví dụ `CaffeineCacheManager.setAsyncCacheMode(true)` khi phù hợp, Spring có thể phối hợp đường đọc `@Cacheable`/`Cache.retrieve` tốt hơn. Demo của bài tập trung vào **put/evict sau completion**, nên dùng manager đơn giản để cô lập hành vi.

## 8. @Async, AOP proxy và @Transactional

### 8.1. @Async thay đổi thread, không thay thế completion check

~~~java
@Async
@CachePut(cacheNames = "documents", key = "#p0")
public CompletableFuture<String> update(String id) {
    String updated = repository.writeAndReturn(id);
    return CompletableFuture.completedFuture(updated);
}
~~~

Đây là code minh họa cần `@EnableAsync`, bean và `repository` thật. `@Async` có thể chuyển thực thi sang executor khác; caller nhìn thấy outer future, và cache advice có thể hoạt động trong thứ tự interceptor khác với kỳ vọng nếu không kiểm thử. Đừng cho rằng vì method body trả completed future nên caller cũng đã nhận final completion ngay.

- `@EnableCaching` và `@EnableAsync` là hai cấu hình khác nhau.
- Đường gọi phải đi qua Spring proxy; `this.update(...)` trong cùng bean thường bypass proxy mode.
- Một future có thể hoàn thành ở worker thread, trong khi cache completion callback cũng có thể chạy trên thread đó; đừng dựa vào thread-local context mà chưa kiểm tra.
- Hãy kiểm thử đúng mốc thực tế với executor/config đang deploy, không chỉ code đường thành công.

### 8.2. TransactionAwareCacheManagerProxy không phải async adapter

| Khía cạnh | Async-aware cache annotation | Transaction-aware cache decorator |
| --- | --- | --- |
| Sự kiện chính | Future/reactive result hoàn tất thành công | Giao dịch Spring commit thành công |
| Mục tiêu | Dựa vào outcome của tác vụ bất đồng bộ | Hoãn `put`, `evict`, `clear` tới afterCommit |
| Không bảo đảm | DB đã commit hay chưa | Async operation đã hoàn tất hay chưa |
| Khi future chạy ở thread khác | Callback có thể chạy ngoài transaction context | Transaction synchronization thread-bound không tự truyền sang callback |
| Có phải distributed transaction? | Không | Không |

`@Transactional` trên method trả future có thể commit transaction theo phạm vi **method invocation**, trong khi future hoàn thành sau đó. Không được mặc định return future success và database commit là một mốc. Khi kết hợp async caching với `TransactionAwareCacheManagerProxy`, thời điểm cuối cùng còn phụ thuộc thứ tự AOP, thread completion và việc có transaction synchronization lúc cache operation chạy.

Nếu yêu cầu nhất quán mạnh, thiết kế sự kiện sau commit, outbox hoặc versioned keys; không chỉ xếp chồng annotation rồi cho rằng nó trở thành atomic DB+cache.

## 9. Race condition mà timing đúng vẫn chưa giải quyết

### 9.1. Put hoàn tất ngược thứ tự

~~~text
T0: Future A bắt đầu cập nhật cùng key K (kết quả A cũ hơn)
T1: Future B bắt đầu cập nhật key K (kết quả B mới hơn)
T2: Future B success → @CachePut ghi B
T3: Future A success → @CachePut ghi A
Kết quả: cache có A (stale) dù future A kết thúc cuối.
~~~

`@CachePut` không tự phân xử version/cập nhật nào mới nhất. Dùng versioned record, optimistic locking và compare version, hoặc tuần tự hóa writer theo key khi nghiệp vụ yêu cầu.

### 9.2. Evict rồi request khác lại nạp dữ liệu cũ

Một `@Cacheable` request có thể bắt đầu load từ source cũ trước commit, còn pending. Future update hoàn tất và eviction xóa key, nhưng loader cũ kết thúc sau eviction và put dữ liệu cũ vào cache. Đây là race giữa **invalidate** và **repopulation**. Xử lý bằng version-aware keys, locking hoặc mô hình consistency phù hợp.

### 9.3. Local cache không tự đồng bộ cluster

`ConcurrentMapCacheManager`/Caffeine local trong JVM A không tự evict JVM B. Sau completion success tại A, một request ở B vẫn có thể thấy stale entry. TTL là giới hạn tuổi, không phải broadcast invalidation. Với Redis/shared cache, lại phải tính tới lỗi mạng và semantics transaction/provider.

### 9.4. Cache value mutable

Nếu value hoàn tất là một Java object mutable và backend lưu theo reference, các caller có thể sửa cùng entry. Future completion chỉ quyết định **khi nào put**, không làm dữ liệu bất biến. Ưu tiên immutable DTO và defensive copy.

## 10. Sai lầm thường gặp

1. **Nhầm method return với future success:** dẫn tới evict/put quá sớm hoặc test không kiểm tra trạng thái pending.
2. **Đặt `beforeInvocation=true` mà muốn giữ cache khi delete lỗi:** đây là evict trước method, không có rollback tự động.
3. **Dùng Spring cũ nhưng áp dụng giả định của Spring 6.1+:** kiểm tra dependency tree/phiên bản runtime.
4. **Tự gọi `cache.put(key, future)` rồi mong có cùng semantics annotation:** imperative put không tự tương đương với future-aware `@CachePut`.
5. **Cho rằng `@CachePut` là cache lookup:** nó thực thi method và sử dụng kết quả để cập nhật, không skip method vì hit.
6. **Quên `@EnableCaching` hoặc gọi self-invocation:** caching interceptor không chạy như mong đợi.
7. **Chỉ test `CompletableFuture.completedFuture(...)`:** không quan sát được trạng thái trước completion; nên test future chưa hoàn tất.
8. **Bỏ qua exception/cancel:** future fail không giống successful completion; nhưng side effect nguồn có thể vẫn xảy ra.
9. **Nhầm `Mono.empty()` với `onError`:** successful empty và failure có semantics khác nhau.
10. **Tin rằng `@Async` tự truyền transaction sang completion callback:** kiểm tra thread context và ranh giới transaction.
11. **Không xét nhiều future cùng key:** completion out-of-order có thể ghi đè cache bằng value cũ.
12. **Không giới hạn timeout/pending:** tác vụ treo có thể làm cache không được cập nhật/xóa như mong muốn.
13. **Không nhất quán key và tenant:** cache hit có thể trả nhầm dữ liệu; không đặt authorization chỉ trong loader bị skip khi hit.

## 11. Bài tập và kiểm thử

| Tình huống | Thao tác | Kết quả cần quan sát |
| --- | --- | --- |
| `@CachePut` pending | Return incomplete `CompletableFuture` | Cache vẫn value cũ |
| Put success | Complete với `"new"` | Cache chứa `"new"` |
| Put failure | Complete exceptionally | Entry cũ không bị thay bởi kết quả lỗi |
| `@CacheEvict` pending | Return incomplete future | Key vẫn có entry |
| Evict success | Complete `CompletableFuture<Void>` bằng null | Key bị evict |
| Evict failure | Complete exceptionally | Entry cũ vẫn còn trong kịch bản tuần tự |
| Early eviction | `beforeInvocation=true` | Eviction được phát trước khi method chạy |
| Early evict + future fail | Exception sau khi method return | Không có undo cache mặc định |
| Null put result | Complete success với null | Kiểm tra `unless` và null policy |
| Reactive empty/error | `Mono.empty()`/`Mono.error(...)` | Test success terminal vs failure |
| Multi-writer | Hai future hoàn tất ngược thứ tự | Phân tích stale overwrite và bảo vệ bằng version |
| Transaction | Kết hợp DB commit và async completion | Xác định hai mốc khác nhau, test afterCommit |
| Multi-instance | Hai JVM có local caches | Evict ở A không tự đồng bộ sang B |

**Checklist trước production:** xác minh Spring version; cấu hình `CacheManager`/proxy; kiểm thử trạng thái pending, success, exceptional, cancel và null; chọn rõ `beforeInvocation`; phân biệt cache operation với DB commit; xử lý race, version và nhiều replica; quan sát timeout và failure; đừng suy luận hoàn tất future là atomic transaction.

## Tài liệu chính thức

- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — `CachePut` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework — `CacheEvict` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
- Spring Framework — Cache abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Proxying mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — TransactionAwareCacheManagerProxy: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html

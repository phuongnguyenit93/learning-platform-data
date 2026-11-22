# Hỗ trợ CompletableFuture và kiểu reactive từ Spring Framework 6.1

> **Spring Framework – Cache Abstraction · Nhóm: Bất đồng bộ.** Từ **Spring Framework 6.1**, hạ tầng khai báo cache hiểu các phương thức trả về `CompletableFuture`, `Mono` và `Flux`: cache được xử lý theo **giá trị được hoàn tất/phát ra**, thay vì đơn giản coi đối tượng wrapper tương lai hoặc `Publisher` là giá trị cần lưu. Bài học giải thích cách hoạt động, điều kiện backend cần có, ví dụ Java 17+ và các lỗi khi áp dụng vào ứng dụng bất đồng bộ.

## 1. Tại sao cache bất đồng bộ khác cache đồng bộ?

Với phương thức đồng bộ:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public BookView findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Spring Cache có thể kiểm tra cache **trước khi gọi** phần thân phương thức; nếu miss, phương thức chạy và trả `BookView`, rồi giá trị được đưa vào cache theo cấu hình.

Với phương thức trả `CompletableFuture<BookView>`, thời điểm Java method **trả về** có thể chỉ là thời điểm tạo một tác vụ chưa hoàn tất. Giá trị `BookView` có thể xuất hiện muộn hơn trên một thread khác. Với Reactor `Mono<BookView>` và `Flux<BookView>`, method có thể trả về mô tả pipeline; việc tạo dữ liệu thường xảy ra **khi có subscription**.

Nếu lưu nguyên object `CompletableFuture` hoặc `Mono` như một value tùy ý, cache có thể chia sẻ nhầm trạng thái tác vụ, phụ thuộc subscriber hoặc giữ một publisher có hành vi không phù hợp. Cơ chế hỗ trợ từ 6.1 nhằm cung cấp cách xử lý theo **kết quả bất đồng bộ được công bố**.

### Bảng trực quan

| Kiểu trả về của method | Đơn vị giá trị mà caching infrastructure hướng tới | Trên cache hit |
| --- | --- | --- |
| `BookView` | Một `BookView` | Trả `BookView` |
| `CompletableFuture<BookView>` | `BookView` sau khi future hoàn tất thành công | Trả về `CompletableFuture` thích hợp chứa kết quả cached |
| `Mono<BookView>` | Một `BookView` được `Mono` phát ra | Trả về `Mono` phát kết quả cached |
| `Flux<BookView>` | **`List<BookView>`** thu thập từ toàn bộ `Flux` khi kết thúc thành công | Trả về `Flux` phát lần lượt các phần tử đã lưu |

**Chú ý với `Flux`:** cache cần **đợi dòng hoàn thành** rồi mới có một danh sách đầy đủ để lưu. Đừng dùng chiến lược này vô điều kiện cho `Flux` vô hạn, luồng sự kiện kéo dài, dữ liệu quá lớn hoặc stream cần backpressure ở cấp phần tử.

## 2. Điều gì thay đổi từ Spring 6.1?

Trước khi có hỗ trợ chính thức cho kiểu asynchronous/reactive, việc đặt `@Cacheable` lên method trả Future/Publisher dễ dẫn tới xử lý wrapper như một object thông thường, không phản ánh đầy đủ thời điểm có kết quả thật. Bắt đầu từ **Spring Framework 6.1**, `@Cacheable` biết cách thích nghi với:

- **`CompletableFuture<T>`:** xử lý kết quả sau khi future hoàn thành; tạo future thích hợp khi cache hit.
- **Reactor `Mono<T>`:** cache phần tử được phát ra khi hoàn thành thành công; trên hit có thể chuyển giá trị đã lưu thành `Mono`.
- **Reactor `Flux<T>`:** gom các phần tử của dòng hữu hạn thành một `List` để lưu sau khi hoàn thành; trên hit tạo dòng phát lại các phần tử trong danh sách.
- **Lookup bất đồng bộ của cache provider:** khi provider có khả năng `Cache.retrieve`, Spring có thể tận dụng nó thay vì luôn ép thao tác đọc blocking.

Đây là hỗ trợ ở tầng **Spring caching interceptor**. Nó **không biến mọi cache backend thành hệ thống bất đồng bộ**, cũng không khiến `@Cacheable` tự tạo thread, executor, network non-blocking I/O hoặc scheduler. Method nghiệp vụ và provider vẫn phải được thiết kế đúng.

Spring cũng có hành vi thích nghi với asynchronous/reactive return types cho các caching operation khác như `@CachePut` và `@CacheEvict`. Tuy nhiên, **thời điểm hoàn tất và điều kiện invalidation** cần xét theo loại annotation, `beforeInvocation`, lỗi, transaction và provider; không mặc định việc nhận về một `Mono` ngay lập tức đồng nghĩa side effect đã hoàn tất.

## 3. CompletableFuture: cache kết quả, không chỉ cache lời hứa

Giả sử một service:

~~~java
@Cacheable(cacheNames = "bookDetails", key = "#p0")
public CompletableFuture<String> fetchBook(String isbn) {
    return CompletableFuture.supplyAsync(
            () -> remoteClient.fetchTitle(isbn)
    );
}
~~~

Đây là **method minh họa**, yêu cầu bean Spring và `remoteClient` được cấu hình; bản chạy được ở phần 7 dùng `completedFuture` để tránh lệ thuộc network hoặc executor.

Với `@Cacheable`:

1. Gọi qua **Spring-managed proxy** với key chưa được cache.
2. Cache miss nên Spring gọi method, nhận một `CompletableFuture` đại diện tác vụ.
3. Khi future **hoàn thành thành công**, Spring có thể lưu **giá trị `String` đã hoàn tất** dưới key ISBN.
4. Lần gọi sau cùng key có cache hit sẽ nhận một `CompletableFuture<String>` tương thích, có thể lấy kết quả bằng `join()` hoặc tiếp tục chain.
5. Nếu future hoàn tất đặc biệt với exception, không xem exception như một **giá trị thành công bình thường** cần cache; chính sách lỗi và cách provider xử lý vẫn cần kiểm tra.

### Phân biệt thời điểm invocation và completion

~~~text
t0   client gọi fetchBook("BK-1")
t1   cache miss, method trả CompletableFuture đang pending
t2   tác vụ I/O hoàn thành giá trị BookView mới
t3   Spring hoàn tất thao tác cache tương ứng
t4   client khác gọi cùng key: có thể nhận kết quả cached
~~~

Không được khẳng định mọi call giữa t1 và t3 đều tự động được hợp nhất. **Cache stampede** là vấn đề riêng: nhiều request cùng key miss trước khi future đầu tiên hoàn thành có thể đều chạy nguồn nếu cache/provider không hỗ trợ đồng bộ/async loading phù hợp.

### Tránh tự tạo “cache chứa Future” nếu không cần

Kiểu `Cache<String, CompletableFuture<BookView>>` do code tự viết có thể hữu ích trong một số kiến trúc, nhưng nó đưa cả retry, exceptional completion, cancellation, sharing state, lifecycle và eviction của future vào hợp đồng cache. Với Spring 6.1+, ưu tiên để caching infrastructure quản lý giá trị **T** nếu yêu cầu là cache kết quả nghiệp vụ bình thường.

**Không đồng nhất `CompletableFuture` với bất đồng bộ hiệu quả:** `CompletableFuture.completedFuture(value)` là kết quả đã sẵn, không tạo I/O asynchronous. `supplyAsync` dùng executor nhưng không tự biến một lời gọi blocking thành non-blocking network operation.

## 4. Reactor Mono: một kết quả hoặc completion rỗng

`Mono<T>` là `Publisher` phát **tối đa một phần tử**. Một `Mono` trả về từ method có thể là *cold*: nó chỉ bắt đầu công việc khi subscriber đăng ký.

~~~java
@Cacheable(cacheNames = "bookDetails", key = "#p0")
public Mono<String> findBook(String isbn) {
    return reactiveRepository.findTitleByIsbn(isbn);
}
~~~

Đây là **method minh họa**, cần `reactiveRepository` thực tế. Với hỗ trợ Spring 6.1+:

- Cache miss dẫn tới pipeline nghiệp vụ được thực thi khi cần; dữ liệu phát ra có thể được đưa vào cache khi hoàn thành theo cơ chế adaptation.
- Cache hit có thể trả một `Mono` phát ra **value đã cache** mà không cần chạy lại truy vấn nguồn.
- Do `Publisher` có subscription semantics, đừng suy luận việc cache được ghi chỉ vì một method đã **trả object `Mono`** nhưng chưa hề có subscriber.
- Nếu `Mono` kết thúc rỗng, cần kiểm tra **chính sách null/miss** của backend và hợp đồng domain; đừng mặc định mọi cache provider có cùng cách lưu completion rỗng.
- Nếu `Mono` phát error, thiết kế retry/cache lỗi phải nhất quán với nghiệp vụ; đừng coi một tín hiệu lỗi mạng là dữ liệu thành công.

### Những điều cần phân biệt

- **Memoization trong Reactor**: `Mono.cache()` giữ tín hiệu ở phạm vi **một instance Mono** theo operator Reactor.
- **Spring method cache**: `@Cacheable` quản lý key/cache region cho các method invocation **đi qua Spring proxy**.
- **Provider cache**: Caffeine/Redis/ConcurrentMap quyết định TTL, dung lượng, serialization, sharing giữa instance.

`Mono.cache()` và `@Cacheable` không phải tên gọi khác nhau của cùng một cơ chế. Chúng có phạm vi, lifecycle và ownership khác nhau. Chỉ thêm `Mono.cache()` vào pipeline không tự cung cấp invalidation theo SKU; thêm `@Cacheable` cũng không tự làm operator tùy chỉnh hoặc truy vấn downstream non-blocking.

## 5. Reactor Flux: phải thận trọng với collection của toàn dòng

`Flux<T>` phát **0 đến nhiều phần tử**. Spring 6.1+ xử lý kết quả `Flux` cho declarative caching bằng cách **thu gom các phần tử thành một `List<T>`** khi dòng hoàn tất, rồi có thể phát lại danh sách đó qua một `Flux` trên cache hit.

~~~java
@Cacheable(cacheNames = "recommendations", key = "#p0")
public Flux<String> recommendations(String category) {
    return repository.findRecommendedIds(category);
}
~~~

Đây là đoạn minh họa, cần repository reactive và bean được quản lý bởi Spring.

### Điều này có nghĩa gì?

- Dòng đầu tiên phải **hoàn thành** để có kết quả đầy đủ cần cache.
- Danh sách trong cache là **một snapshot** của toàn bộ dòng tại thời điểm hoàn tất.
- Hit về sau phát lại các giá trị cached, không nhất thiết thực hiện lại luồng I/O gốc.
- Bộ nhớ có thể tăng nhanh nếu một key tạo hàng trăm nghìn phần tử.
- Dòng vô hạn `Flux.interval`/SSE/live event stream **không có completion bình thường**, không phù hợp với chiến lược gom toàn dòng.
- Việc gom toàn dòng không mang lại **streaming từng phần tử đến cache**; không dùng nó nếu nghiệp vụ cần xử lý vô hạn với độ trễ từng sự kiện.

### Ví dụ quyết định

| Use case | Có nên `@Cacheable Flux`? | Lý do |
| --- | --- | --- |
| Danh sách 20 mã sản phẩm cho một category | Có thể | Dòng hữu hạn, kích thước kiểm soát được |
| Danh sách 10.000 đơn hàng phân trang | Cân nhắc | Kết quả lớn, cache key phải bao gồm trang/filter |
| Infinite market-tick stream | Không phù hợp | Không kết thúc để gom list đầy đủ |
| SSE websocket event stream | Không phù hợp | Dữ liệu sống, có subscriber-specific semantics |
| Một truy vấn lấy tối đa 1 row | Thường ưu tiên `Mono` | Không cần `Flux` và collection nhiều phần tử |
| Luồng phụ thuộc quyền/user/tenant | Chỉ khi key và access control đúng | Tránh chia sẻ dữ liệu giữa người dùng |

**Quan trọng về trí nhớ:** cache provider có thể giữ nguyên danh sách và tất cả phần tử, làm tăng pressure trên heap hoặc external store. Khi dùng `Flux` lớn, nên giới hạn số phần tử, chia key theo trang, lưu DTO gọn hoặc cache một đối tượng kết quả phân trang thay vì gom dòng không giới hạn.

## 6. Điều kiện để backend tương thích asynchronous caching

### 6.1. API Cache.retrieve của Spring

Spring Cache có API bất đồng bộ như:

~~~java
CompletableFuture<?> future = cache.retrieve("BK-1");
~~~

Đây là **đoạn minh họa** trong method đã có biến `cache` kiểu `org.springframework.cache.Cache`. API `retrieve` cho phép cache provider trả kết quả future khi không thể hoàn tất lookup ngay. Không nên đánh đồng API này với việc loader tự động chạy; lookup và compute-on-miss là hai vấn đề khác nhau.

Không phải mọi implementation `Cache` đều có lookup bất đồng bộ hữu dụng. Một implementation chỉ hỗ trợ các API đồng bộ có thể không đáp ứng các chiến lược `sync=true` và reactive non-blocking mà ứng dụng kỳ vọng.

### 6.2. ConcurrentMapCacheManager

Từ Spring 6.1, `ConcurrentMapCacheManager` có cấu hình:

~~~java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("futureBooks", "monoBooks", "fluxBooks");
manager.setAsyncCacheMode(true);
~~~

Đây là đoạn cấu hình độc lập trong method, cần import `org.springframework.cache.concurrent.ConcurrentMapCacheManager`. Chế độ này giúp manager hỗ trợ việc thích nghi asynchronous lookup cho ví dụ Java 17+ bên dưới.

Nó vẫn là **cache cục bộ trong JVM**, không biến thành Redis, không có persistence, không tự bảo đảm TTL. Vì lưu local, từng instance ứng dụng có cache riêng.

### 6.3. CaffeineCacheManager

Spring `CaffeineCacheManager` cũng hỗ trợ:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager("books");
manager.setAsyncCacheMode(true);
~~~

Đây là đoạn cấu hình tích hợp, cần Spring `spring-context-support` và dependency Caffeine phù hợp. Mode asynchronous sử dụng native asynchronous cache khi có thể. Hãy kiểm chứng cách kết hợp loader, kích thước, expireAfterWrite, serialization và error handling của provider thực tế.

**Phân biệt hai khái niệm:**

- `setAsyncCacheMode(true)`: cấu hình backend để hỗ trợ cách truy xuất/thao tác bất đồng bộ.
- `refreshAfterWrite`: chính sách riêng của Caffeine để **làm mới entry đang có**, đòi hỏi loader/async loader phù hợp.

Bật async cache mode **không tự tạo refresh**, TTL, prefetch hoặc một task nền định kỳ.

### 6.4. @Cacheable(sync = true)

~~~java
@Cacheable(cacheNames = "books", key = "#p0", sync = true)
public CompletableFuture<String> find(String isbn) {
    return remoteClient.fetch(isbn);
}
~~~

Đây là **mã method minh họa**, cần client thật, cache provider hỗ trợ và lời gọi đi qua proxy. `sync = true` cho phép Spring yêu cầu provider phối hợp việc tính giá trị khi nhiều caller cùng key miss, để hạn chế duplicate loads. Với phương thức trả Future, khả năng hỗ trợ thích hợp liên quan đến API bất đồng bộ của provider.

**Không hứa một cách tuyệt đối:** `sync=true` không phải khóa phân tán trên mọi JVM, không loại bỏ race DB/cache, không thay thế `@Transactional` và có một số hạn chế kết hợp với cache names/`unless`. Cần kiểm thử concurrency trên backend thật.

## 7. Ví dụ Java 17+ hoàn chỉnh: Future, Mono và Flux trong một ứng dụng

Ví dụ dùng **Spring Framework 6.2.14**, **Reactor Core 3.7.12**, Java 17 và `ConcurrentMapCacheManager` ở async cache mode. Đây là ứng dụng Java thuần tạo `AnnotationConfigApplicationContext`, **không cần Spring Boot, HTTP hoặc database**.

Ba cache region độc lập:

1. `futureBooks`: method trả `CompletableFuture<String>`.
2. `monoBooks`: method trả `Mono<String>`.
3. `fluxBooks`: method trả `Flux<String>`, có **hai phần tử**.

Mỗi method tăng một counter tại điểm **thật sự tính giá trị nguồn**. Khi gọi cùng key lần thứ hai, nếu cache hit counter sẽ không tăng.

**Tệp `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'io.projectreactor:reactor-core:3.7.12'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.AsyncCacheDemo'
}
~~~

**Tệp `src/main/java/demo/AsyncCacheDemo.java`:**

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class AsyncCacheDemo {

    public static class BookService {
        private final AtomicInteger futureLoads = new AtomicInteger();
        private final AtomicInteger monoLoads = new AtomicInteger();
        private final AtomicInteger fluxLoads = new AtomicInteger();

        @Cacheable(cacheNames = "futureBooks", key = "#p0")
        public CompletableFuture<String> findFuture(String isbn) {
            int n = futureLoads.incrementAndGet();
            return CompletableFuture.completedFuture(
                    "future-" + isbn + "-load-" + n
            );
        }

        @Cacheable(cacheNames = "monoBooks", key = "#p0")
        public Mono<String> findMono(String isbn) {
            return Mono.fromSupplier(() -> {
                int n = monoLoads.incrementAndGet();
                return "mono-" + isbn + "-load-" + n;
            });
        }

        @Cacheable(cacheNames = "fluxBooks", key = "#p0")
        public Flux<String> findFlux(String isbn) {
            return Flux.defer(() -> {
                int n = fluxLoads.incrementAndGet();
                return Flux.just(
                        "flux-" + isbn + "-A-" + n,
                        "flux-" + isbn + "-B-" + n
                );
            });
        }

        public int futureLoads() {
            return futureLoads.get();
        }

        public int monoLoads() {
            return monoLoads.get();
        }

        public int fluxLoads() {
            return fluxLoads.get();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            ConcurrentMapCacheManager manager =
                    new ConcurrentMapCacheManager(
                            "futureBooks", "monoBooks", "fluxBooks"
                    );
            manager.setAsyncCacheMode(true);
            return manager;
        }

        @Bean
        public BookService bookService() {
            return new BookService();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            BookService service = context.getBean(BookService.class);

            String futureFirst = service.findFuture("BK-1").join();
            String futureSecond = service.findFuture("BK-1").join();

            String monoFirst = service.findMono("BK-2").block();
            String monoSecond = service.findMono("BK-2").block();

            var fluxFirst = service.findFlux("BK-3").collectList().block();
            var fluxSecond = service.findFlux("BK-3").collectList().block();

            System.out.println("future first: " + futureFirst);
            System.out.println("future second: " + futureSecond);
            System.out.println("future loads: " + service.futureLoads());

            System.out.println("mono first: " + monoFirst);
            System.out.println("mono second: " + monoSecond);
            System.out.println("mono loads: " + service.monoLoads());

            System.out.println("flux first: " + fluxFirst);
            System.out.println("flux second: " + fluxSecond);
            System.out.println("flux loads: " + service.fluxLoads());
        }
    }
}
~~~

Chạy trong thư mục chứa `build.gradle` bằng JDK 17+ và Gradle tương thích:

~~~bash
gradle run --quiet
~~~

**Stdout dự kiến của chương trình** (không tính log do công cụ build):

~~~text
future first: future-BK-1-load-1
future second: future-BK-1-load-1
future loads: 1
mono first: mono-BK-2-load-1
mono second: mono-BK-2-load-1
mono loads: 1
flux first: [flux-BK-3-A-1, flux-BK-3-B-1]
flux second: [flux-BK-3-A-1, flux-BK-3-B-1]
flux loads: 1
~~~

### Vì sao có kết quả này?

**Future:** Lần đầu `findFuture("BK-1")` miss, phương thức tính giá trị và trả `completedFuture`. Spring xử lý giá trị `"future-BK-1-load-1"` rồi lưu kết quả. Lần sau có cache hit, bộ đếm vẫn là 1. `join()` chỉ làm ví dụ console chờ kết quả; trong ứng dụng thật caller có thể dùng `thenApply` hoặc chain asynchronous.

**Mono:** `Mono.fromSupplier` thể hiện nguồn tính khi **subscription**. Lệnh `block()` đầu tiên trong ví dụ chủ động subscribe, supplier tạo `"mono-BK-2-load-1"`. Khi hoàn thành, kết quả được cache. Lần `block()` kế tiếp trên invocation cùng key có thể nhận kết quả đã lưu, nên `monoLoads` không tăng.

**Flux:** `Flux.defer` tạo hai phần tử với cùng số lần load. Lần đầu `collectList().block()` làm luồng hoàn tất, Spring thu thập danh sách gồm hai phần tử và cache nó. Lần tiếp theo Spring có thể phát lại danh sách, vì vậy `fluxLoads = 1`.

**Ranh giới của ví dụ:** `block()` và `join()` chỉ để quan sát stdout **trong phương thức main**. **Không gọi `block()` trong luồng xử lý request WebFlux**; hãy trả `Mono`/`Flux` để framework quản lý subscription và event loop. Ví dụ dùng `completedFuture` nên không chứng minh I/O thực sự non-blocking.

**Độ tin cậy đầu ra:** stdout được suy luận từ logic và Spring 6.2.14 trong cấu hình nêu trên; không khẳng định đây là log đã chạy bằng Gradle trên môi trường hiện tại. Nếu môi trường của bạn quản lý dependency hoặc proxy khác, hãy chạy integration test phù hợp.

## 8. Dòng thời gian: khi nào cache được nạp?

### CompletableFuture

~~~text
Caller -> Spring proxy -> cache miss
                         |
                         v
                    gọi method
                         |
                    nhận Future
                         |
             Future hoàn thành thành công
                         |
                 lưu kết quả T vào cache
                         |
         lượt gọi sau có thể hit theo key
~~~

### Mono/Flux

~~~text
Caller -> Spring proxy -> trả Publisher phù hợp
                                   |
                            subscriber đăng ký
                                   |
                         thực thi source trên miss
                                   |
                      Mono phát T / Flux phát nhiều T
                                   |
                          Publisher hoàn tất
                                   |
                     lưu T / List<T> vào cache
                                   |
                   lượt gọi sau phát lại dữ liệu
~~~

Đây là sơ đồ khái niệm; thời điểm intercept, cách lookup được defer và scheduler thực tế phụ thuộc Spring/provider/pipeline. Không nên dựa vào **việc method đã trả về** để khẳng định cache đã được ghi nếu quá trình async còn pending hoặc Publisher chưa hoàn tất.

### Điều gì xảy ra với nhiều subscriber?

Một đối tượng `Mono`/`Flux` có thể được subscribe nhiều lần tùy cách caller sử dụng. Với code có side effect khi subscribe, tránh dựa vào một instance Publisher đang chia sẻ giữa các request để kiểm soát caching. Hãy kiểm tra **số lần thực sự gọi nguồn** và **số lần subscribe** trong test thực tế. `@Cacheable` hoạt động ở ranh giới method Spring; không phải mỗi đoạn pipeline nội bộ đều được cache riêng.

## 9. Những tương tác quan trọng với @CachePut và @CacheEvict

Trong ứng dụng thực, method chỉ đọc không đủ: phải invalidation khi nguồn thay đổi.

Ví dụ cấu trúc:

~~~java
@CacheEvict(cacheNames = "bookDetails", key = "#p0")
public Mono<Void> renameBook(String isbn, String title) {
    return reactiveRepository.rename(isbn, title);
}
~~~

Đây là **method tích hợp minh họa**; `reactiveRepository` và bean thực tế chưa được định nghĩa. Với asynchronous/reactive return types, caching advice cần tương tác với **kết quả bất đồng bộ**, không chỉ thời điểm method tạo ra `Mono` rỗng đang chờ subscribe. Trong Spring 6.1+, caching infrastructure có hỗ trợ thích nghi completion cho các operation tương ứng.

Tuy nhiên, đừng suy ra rằng:

- Eviction đồng nghĩa database commit.
- Method đã trả về `Mono` đồng nghĩa update đã xong.
- Mọi lỗi đều kích hoạt cùng một chính sách eviction.
- `beforeInvocation = true` và mặc định `false` có thời điểm giống nhau.
- Reactive transaction tự biến cache provider thành transactional cache.

Nếu update và eviction phải gắn với **sau commit**, cần thiết kế rõ transaction boundary, context và cơ chế invalidation. Với hệ thống cần tính nhất quán cao, tránh tình huống reader nạp bản DB cũ vào cache trong lúc writer chưa commit.

**Đối với `@CachePut`:** khi operation cache phụ thuộc giá trị trả ra từ một `CompletableFuture` hoặc `Mono`, framework phải chờ kết quả phù hợp thay vì đưa object Future/Publisher nguyên xi vào vùng cache. Kiểm thử đặc biệt khi method trả empty, error hoặc `Flux` nhiều phần tử. Không thay thế `@CachePut` bằng `@Cacheable` vì hai annotation có mục tiêu khác nhau: `@CachePut` thường luôn chạy method, còn `@Cacheable` có thể bỏ qua method khi hit.

## 10. Lỗi, rỗng, hủy tác vụ và dữ liệu cá nhân hóa

### 10.1. Exceptional completion và onError

Một `CompletableFuture` có thể `completeExceptionally`; một `Mono`/`Flux` có thể phát `onError`. Các trường hợp này cần được xét như **lỗi tác vụ**, không phải một giá trị domain đã tải thành công. Đừng ghi “cache đã được nạp thành công” chỉ vì method trả một wrapper.

Nếu có retry, timeout, circuit breaker hoặc fallback, thứ tự operator/interceptor quyết định **giá trị cuối cùng được cache**. Ví dụ một pipeline bắt exception rồi chuyển thành `"UNAVAILABLE"` có thể hoàn tất thành công; nếu cách đó được cache theo key, ứng dụng có thể giữ fallback quá lâu. Nên dùng TTL riêng hoặc chính sách không cache dữ liệu fallback nếu cần.

### 10.2. Empty Mono hoặc Flux

`Mono.empty()` không phát một giá trị `T` thông thường; `Flux.empty()` hoàn tất với danh sách phần tử rỗng. Cách thể hiện cache entry cho kết quả empty phụ thuộc Spring adapter, null policy và provider. Hãy viết test cho cả empty result, cached null và miss; đừng mặc định hai khái niệm giống nhau.

### 10.3. Cancellation

Nếu một subscriber hủy `Mono`/`Flux` trước completion, không nên dựa vào việc cache sẽ chứa snapshot hoàn chỉnh. Tác vụ bị cancel, upstream có thể bị hủy hoặc pipeline có thể còn hoạt động tùy thiết kế. Để khẳng định hành vi, viết test có controlled Publisher.

### 10.4. Context và key

Trong WebFlux, dữ liệu như tenant, user, locale và correlation ID có thể nằm trong **Reactor Context** thay vì một method parameter. Spring `key = "#p0"` không tự thêm Context này.

Nếu nội dung phụ thuộc tenant/user mà key chỉ có `isbn`, hai caller có thể chia sẻ nhầm dữ liệu. Hãy đưa thành phần định danh/phân quyền ảnh hưởng đến output vào key hoặc thiết kế vùng cache tách biệt. Không cache trực tiếp thông tin request-specific nhạy cảm bằng key chung.

### 10.5. Threading

- `CompletableFuture` không bắt buộc tạo thread mới; tùy pipeline/executor.
- `Mono`/`Flux` không mặc nhiên chạy trên thread khác; muốn thay thread phải dùng operator/scheduler thích hợp.
- Cache provider có thể hỗ trợ async lookup nhưng adapter vẫn có đường đi blocking trong một số cấu hình.
- Đừng dùng blocking repository trực tiếp trên event-loop rồi kỳ vọng `@Cacheable` che hết vấn đề.
- Đo latency end-to-end, tỷ lệ cache hit, thời gian I/O và thread usage trên môi trường vận hành.

## 11. Debug khi cache async/reactive không như mong muốn

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
| --- | --- | --- |
| `Mono` gọi nguồn lại ở mỗi request | Spring version cũ, method không đi qua proxy, key thay đổi, chưa subscribe/completion | Kiểm tra Spring 6.1+, bean proxy, hit/miss và pipeline |
| `Flux` chưa có cache entry | Flux chưa hoàn tất, bị cancel hoặc lỗi | Kiểm tra `onComplete`, số phần tử, kích thước dòng |
| Backend báo async retrieval unsupported | Cache provider chưa hỗ trợ `retrieve`/async mode cho đường dùng | Kiểm tra implementation, setAsyncCacheMode và test |
| Nhiều request cùng key cùng chạy nguồn | Các miss xảy ra trước completion, không có coordination | Cân nhắc `sync=true`, provider support và load deduplication |
| Cache hit nhưng vẫn lộ dữ liệu tenant khác | Key thiếu thành phần phân vùng | Thiết kế composite key/context đúng |
| Cache giữ fallback khi nguồn lỗi | `onErrorResume` chuyển lỗi thành value thành công | Tách cache policy cho fallback hoặc điều kiện lưu |
| `Flux` tiêu thụ quá nhiều heap | Caching thu gom toàn danh sách | Giới hạn, phân trang hoặc không cache Flux vô hạn |
| Caffeine bật async nhưng không tự reload dữ liệu | Async cache mode khác `refreshAfterWrite` | Phân biệt loader, TTL, refresh và lookup |
| `@CacheEvict` không chạy | Method gọi qua `this` trong cùng bean; hoặc publisher chưa hoàn tất | Kiểm tra proxy/self-invocation, subscription và error path |
| Dùng `block()` làm giảm throughput | Blocking trên event loop | Dùng reactive composition và instrumentation |
| Thay `@Cacheable` bằng `Mono.cache()` nhưng eviction không hiệu lực | Hai cơ chế có phạm vi/lifecycle khác nhau | Chọn cache scope đúng hoặc tích hợp rõ ràng |
| Kết quả cũ sau update | Eviction sai key hoặc race với transaction | Test update/commit/cache read với concurrency |

### Checklist 7 bước

1. Xác nhận runtime **Spring Framework 6.1 trở lên**; kiểm tra dependency Reactor nếu dùng `Mono`/`Flux`.
2. Kiểm tra bean được Spring quản lý, `@EnableCaching`, cache name và lời gọi qua proxy.
3. Kiểm tra đúng loại value thực sự được provider lưu: `T` hoặc `List<T>`, không giả định là publisher wrapper.
4. Xác minh backend có khả năng async phù hợp; dùng `setAsyncCacheMode(true)` khi ví dụ/provider yêu cầu.
5. Đo completion/subscription và các đường lỗi hoặc empty bằng logging/test, không dựa riêng vào dòng “method returned”.
6. Test read/update/evict với **cùng key**, transaction commit và các request concurrent.
7. Với reactive pipeline, đo memory khi `Flux` lớn, và bảo đảm request handling không block.

## 12. Bài tập tự kiểm tra

**Câu 1.** Từ Spring 6.1, một `@Cacheable` method trả `CompletableFuture<BookView>`. Về mặt abstraction, nội dung cần cache là Future hay BookView?

**Đáp án:** **Kết quả `BookView` hoàn tất thành công** là dữ liệu nghiệp vụ được cache; trên hit framework thích nghi để caller tiếp tục nhận `CompletableFuture<BookView>`.

**Câu 2.** Có `@Cacheable` trên một `Flux<String>` vô hạn, kỳ vọng cache liên tục từng item. Có đúng không?

**Đáp án:** Không. Spring 6.1+ hỗ trợ caching `Flux` bằng cách **thu gom toàn bộ phần tử thành danh sách khi kết thúc**, không phù hợp stream vô hạn.

**Câu 3.** `@Cacheable` trên `Mono` có nghĩa bất kỳ invocation nào vừa trả `Mono` đều lập tức tạo cache entry?

**Đáp án:** Không. Một pipeline cold chưa subscribe có thể chưa phát ra kết quả; cần xem completion và cách provider/infrastructure thích nghi.

**Câu 4.** Vì sao `@Cacheable(sync = true)` không đồng nghĩa cache phân tán loại bỏ mọi duplicate load?

**Đáp án:** Nó yêu cầu provider đồng bộ computation cho cùng key, với giới hạn của backend và phạm vi cache; không tạo distributed lock hoặc transaction giữa mọi node.

**Câu 5.** `setAsyncCacheMode(true)` trên `CaffeineCacheManager` có nghĩa cache tự refresh mỗi hai phút không?

**Đáp án:** Không. Async cache mode là cách truy cập/lưu bất đồng bộ; `refreshAfterWrite` là chính sách khác, cần loader phù hợp và cơ chế trigger.

**Câu 6.** Sau khi một `Flux` đầu tiên phát 3 phần tử và hoàn tất, lần đọc hit trả gì?

**Đáp án:** Một `Flux` có thể phát lại **ba phần tử đã được thu thập** từ list cached, không phải tự chạy lại truy vấn nguồn trong trường hợp hit hợp lệ.

**Câu 7.** Một `Mono` trả dữ liệu theo tenant nhưng cache key chỉ là SKU, liệu có an toàn?

**Đáp án:** Không nếu kết quả thay đổi theo tenant. Phải đưa tenant vào key hoặc phân vùng cache để tránh lộ dữ liệu.

## 13. Ghi nhớ và tài liệu chính thức

- **Từ Spring 6.1**, declarative caching thích nghi với `CompletableFuture` và Reactor `Mono`/`Flux`.
- `CompletableFuture<T>` và `Mono<T>` hướng tới cache **T** khi kết quả hoàn tất; `Flux<T>` hướng tới cache **List<T>`** khi toàn dòng hoàn tất.
- **Cache hit** khôi phục một return type thích hợp với method (`Future`, `Mono` hoặc `Flux`), không bắt caller tự đổi kiểu.
- Một `Mono` cold phải có subscription để phát kết quả; một `Flux` vô hạn không phù hợp với chiến lược thu gom toàn dòng.
- **Backend** cần hỗ trợ async behavior tương ứng. `ConcurrentMapCacheManager` và `CaffeineCacheManager` có async cache mode; không phải mọi provider đều hỗ trợ như nhau.
- `sync=true` là một cơ chế hạn chế duplicate loads, không phải TTL, refresh, transaction hoặc distributed lock.
- Dữ liệu cached vẫn cần **key chính xác, eviction đúng thời điểm, TTL, tenant isolation và kiểm tra completion/error/cancellation**.

**Tham khảo chính thức:**

- [Spring Framework 6.2 – Declarative Annotation-based Caching, Reactive and CompletableFuture Return Types](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
- [Spring Framework 6.2.14 – Cache interface](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/Cache.html)
- [Spring Framework 6.2.14 – ConcurrentMapCacheManager](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html)
- [Spring Framework 6.2.14 – CaffeineCacheManager](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html)
- [Project Reactor – Mono reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/mono.html)
- [Project Reactor – Flux reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html)

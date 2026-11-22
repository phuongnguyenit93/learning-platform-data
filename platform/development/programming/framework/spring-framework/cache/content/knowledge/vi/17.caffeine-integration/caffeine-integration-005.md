# Phân biệt hết hạn, nạp và làm mới giá trị trong Caffeine Cache

> **Spring Framework – Cache Abstraction · Nhóm: Tích hợp Caffeine.** Bài học giải thích ba khái niệm thường bị đánh đồng: **expiration** (entry không còn hợp lệ), **loading** (tính hoặc lấy giá trị khi cache miss) và **refreshing** (nạp bản mới để thay giá trị đã có). Trọng tâm là Caffeine 3.x, cách sử dụng cùng Spring Cache và những ranh giới nhất quán dữ liệu cần nhớ.

## 1. Bắt đầu từ một tình huống thực tế

Một ứng dụng đọc tỷ giá, thông tin sản phẩm hoặc cấu hình thông qua cache. Dữ liệu nguồn có thể thay đổi sau khi ứng dụng đã lưu bản sao. Ta cần trả lời ba câu hỏi **khác nhau**:

1. **Bao giờ một giá trị cached không được trả nữa?** Đó là chính sách **hết hạn (expiration)**.
2. **Khi chưa có entry hợp lệ, ai lấy dữ liệu để lấp chỗ trống?** Đó là cơ chế **nạp (loading)**.
3. **Khi vẫn có bản cũ nhưng muốn thay bằng bản mới, có cần khiến người đọc chờ không?** Đó là **làm mới (refreshing)**.

Caffeine là thư viện cache trong bộ nhớ JVM. Nó hỗ trợ manual cache, `LoadingCache` và các biến thể asynchronous. Spring Cache Abstraction dùng `CacheManager`, `@Cacheable` và các API chung để tích hợp cache provider. **Cấu hình TTL và refresh là chính sách Caffeine, không phải một tính năng tự sinh ra bởi annotation `@Cacheable`.**

Ví dụ trạng thái ban đầu:

~~~text
Dữ liệu nguồn: product-A = "V2"
Cache:        product-A = "V1"

Hết hạn:
  Entry V1 trở nên không hợp lệ.
  Đọc lại -> cache miss -> cần load V2.

Loading:
  Quy tắc chỉ ra cách lấy V2 khi cache miss.

Refresh:
  Entry V1 còn đủ điều kiện phục vụ.
  Đọc khi đến thời hạn refresh -> có thể trả V1 ngay
  trong lúc hệ thống tải V2 bất đồng bộ để thay thế.
~~~

**Ý tưởng cốt lõi:** Expiration quyết định **có được dùng bản cũ không**; loading quyết định **lấy bản mới từ đâu**; refreshing quyết định **khi nào chủ động thay bản đang còn dùng được**. Một cache có thể áp dụng nhiều cơ chế đồng thời, nhưng chúng không đồng nghĩa.

## 2. Expiration: entry hết hạn trở thành cache miss

Caffeine hỗ trợ nhiều loại thời hạn.

### 2.1. expireAfterWrite

~~~java
Caffeine.newBuilder()
        .expireAfterWrite(Duration.ofMinutes(5));
~~~

Đây là đoạn cấu hình **builder chưa gọi `build`**, dùng trong phần khai báo cache của ứng dụng. Thời hạn được tính từ lúc entry được **tạo hoặc thay giá trị bằng thao tác ghi**; đọc lại entry không tự kéo dài thời hạn này.

Timeline minh họa:

~~~text
00:00  put("A", V1)             -> bắt đầu đếm 5 phút
00:03  get("A")                 -> thấy V1; không reset write deadline
00:05  mốc hết hạn của V1
00:06  get("A")                 -> miss, không được phục vụ V1
       LoadingCache có loader -> load bản mới theo key A
~~~

Nếu ứng dụng gọi `put` và thay V1 bằng V2 ở phút 4, write time được đặt lại cho entry. Tuy nhiên **cache hit đọc thông thường không làm mới write time**.

### 2.2. expireAfterAccess

~~~java
Caffeine.newBuilder()
        .expireAfterAccess(Duration.ofMinutes(5));
~~~

Thời hạn được tính từ lần **truy cập đọc hoặc ghi gần nhất**. Nếu key được truy cập đều đặn với khoảng cách dưới 5 phút, nó có thể tiếp tục tồn tại lâu hơn mốc 5 phút tính từ lần tạo đầu tiên.

Ví dụ:

~~~text
00:00  put A  -> đếm từ 00:00
00:04  get A  -> reset thời hạn theo access
00:08  get A  -> lại reset
00:14  get A  -> đã quá 5 phút từ 00:08, A hết hạn
~~~

Chọn `expireAfterAccess` khi mục tiêu là xóa dữ liệu **không còn được dùng**; đừng chọn nó thay `expireAfterWrite` nếu dữ liệu dù được đọc liên tục vẫn cần có giới hạn độ cũ theo thời gian.

### 2.3. expireAfter(Expiry)

Caffeine cũng có API `expireAfter(Expiry)` để đặt thời gian sống riêng theo entry và sự kiện create/update/read. Đây là cấu hình nâng cao khi TTL của từng key đến từ trạng thái nghiệp vụ, ví dụ thời điểm hết hạn token hoặc hạn của báo giá. Phải xét kỹ contract callback và bảo đảm thời hạn không âm.

### 2.4. Hết hạn không có nghĩa xóa vật lý đúng từng mili-giây

Caffeine không cần một thread quét mọi entry đúng tại từng deadline. Việc dọn expired entry được xử lý qua hoạt động bảo trì trong quá trình ghi, một số lần đọc và các tác vụ maintenance. Có thể cấu hình `Scheduler` để thúc đẩy việc dọn sớm hơn.

Vì thế:

- **Logic:** entry đã expired không còn được trả như một cache hit thông thường.
- **Vật lý:** entry có thể chưa bị loại khỏi cấu trúc nội bộ cho đến đợt maintenance.
- `estimatedSize()` có thể tạm tính cả entry chưa được dọn dù nó không còn hợp lệ để đọc.
- Trong test, `cleanUp()` hữu ích để yêu cầu maintenance; trong ứng dụng tải bình thường không nên lạm dụng gọi liên tục chỉ để ép dọn cache.

Cũng cần phân biệt **expiration theo thời gian** với **capacity eviction** (`maximumSize`) và **manual invalidation** (`invalidate`). Chúng có thể cùng loại bỏ một entry nhưng có nguyên nhân khác nhau.

## 3. Loading: lấy dữ liệu khi không có entry hợp lệ

Caffeine có hai kiểu dùng phổ biến.

### Manual Cache

~~~java
com.github.benmanes.caffeine.cache.Cache<String, String> cache =
        Caffeine.newBuilder()
                .expireAfterWrite(Duration.ofMinutes(5))
                .build();

String value = cache.get("A", key -> repository.findName(key));
~~~

Đây là **mã tích hợp minh họa** trong method đã có biến `repository` và các import thích hợp. Lời gọi `get(key, mappingFunction)` tính giá trị khi không có mapping hợp lệ; Caffeine có cơ chế phối hợp atomic cho cùng key để hạn chế tính lặp trong trường hợp thông thường. `getIfPresent(key)` chỉ kiểm tra entry và không tự gọi hàm lấy nguồn.

Một manual cache **không biết cách tải dữ liệu** nếu caller chỉ gọi `getIfPresent` mà không có mapping function. Chỉ thêm expiration không tự tạo nguồn load.

### LoadingCache với CacheLoader

~~~java
LoadingCache<String, String> cache = Caffeine.newBuilder()
        .expireAfterWrite(Duration.ofMinutes(5))
        .build(key -> repository.findName(key));

String value = cache.get("A");
~~~

Đoạn này minh họa bên trong class có `repository`. Với `LoadingCache`, người lập trình cung cấp **`CacheLoader`** khi xây cache. Caffeine gọi loader khi `get(key)` gặp miss, kể cả miss do expiration. Khi cache hit, loader thường không cần chạy.

Bảng so sánh:

| Thao tác | Manual Cache | LoadingCache |
| --- | --- | --- |
| `getIfPresent(key)` | Trả entry hoặc null; không tự load | Kiểm tra entry; không nên xem là lời gọi bảo đảm load khi miss |
| `get(key, mappingFunction)` | Có thể tính khi miss | Có thể dùng API kế thừa, nhưng phải quản lý nguồn nạp nhất quán |
| `get(key)` không có mapping function | Không có trên manual interface | Load theo `CacheLoader` khi miss |
| Entry expired | Không trả bản expired | Không trả bản expired; `get` nạp giá trị mới |
| `put(key, value)` | Ghi hoặc thay giá trị | Ghi hoặc thay giá trị; thay đổi write time |
| Nguồn load | Code caller cung cấp | `CacheLoader` gắn với cache |

**Không đánh đồng việc load với refresh:** load khi miss cần tạo entry **từ chỗ chưa có entry hợp lệ**; refresh cố thay **entry đã tồn tại** mà không cần làm reader chờ trong thời gian nạp.

### Điều gì nếu loader thất bại?

Khi dữ liệu không thể tải, `LoadingCache.get(key)` có thể ném exception nếu loader ném lỗi; entry không được thiết lập như một giá trị bình thường. Không giả định “không tìm thấy record” và “loader lỗi” là cùng một trạng thái. Caffeine native cache không lưu mapping mang giá trị null; muốn negative caching cần thiết kế value/sentinel phù hợp hoặc sử dụng adapter Spring có hợp đồng null riêng.

Nếu nhiều request cùng key miss đồng thời, cần đo chi phí load và thận trọng với blocking, timeout và thread pool. Cache giúp giảm tải nhưng không thay thế backpressure hoặc cơ chế bảo vệ nguồn dữ liệu.

## 4. Refreshing: thay một entry đang có mà vẫn có thể trả bản cũ

`refreshAfterWrite` thuộc chính sách **LoadingCache** hoặc `AsyncLoadingCache` có loader. Ví dụ:

~~~java
LoadingCache<String, String> cache = Caffeine.newBuilder()
        .refreshAfterWrite(Duration.ofMinutes(2))
        .build(key -> repository.findName(key));
~~~

Đây là đoạn tích hợp minh họa, cần `repository` thực tế. Ý nghĩa chính xác:

1. Khi entry được tạo hoặc thay giá trị, bắt đầu tính **tuổi theo write time**.
2. Sau 2 phút, entry **đủ điều kiện refresh** (*eligible for refresh*), **chưa phải bị xóa vì hết hạn**.
3. Refresh tự động được **khởi động bởi một lần truy cập key đủ điều kiện**, không phải một timer cứ đến phút thứ 2 là chạy dù không ai đọc.
4. Trong khi refresh bất đồng bộ đang thực hiện, cache **thường trả giá trị hiện tại** cho các reader, nếu entry vẫn hợp lệ.
5. Khi refresh thành công, giá trị mới thay entry cũ. Nếu refresh thất bại, Caffeine giữ bản cũ nếu nó vẫn hợp lệ và log lỗi theo contract refresh.

Vì việc refresh là bất đồng bộ, thời điểm reader nhận bản mới phụ thuộc executor và thời gian tải nguồn. Không bảo đảm mọi lời gọi ở đúng mốc refresh sẽ nhận ngay bản mới; một refresh hoàn tất cực nhanh có thể cập nhật kịp trước khi lời gọi trả về.

### Timeline: refresh và expiration kết hợp

~~~text
Thiết lập:
  refreshAfterWrite = 2 phút
  expireAfterWrite  = 10 phút

00:00  get A lần đầu (miss) -> load V1, lưu A=V1
00:03  get A: A đủ điều kiện refresh
       Caffeine bắt đầu nạp V2 bất đồng bộ
       V1 vẫn có thể được trả trong lúc chờ
00:04  refresh thành công -> A=V2, write time được làm mới
00:10  nếu không có thêm read: không tự refresh theo đồng hồ
00:15  nếu vượt 10 phút tính từ write cuối -> A expired
       get A -> miss/load, không có stale V2 để tiếp tục phục vụ
~~~

**Điểm quan trọng:** `refreshAfterWrite` không phải TTL mềm kèm một scheduler chạy định kỳ độc lập. Nếu entry không còn được truy cập sau khi đủ tuổi refresh, nó **không bị refresh chỉ vì thời gian trôi**; nó vẫn có thể hết hạn bởi `expireAfterWrite`.

### Chủ động refresh một key

`LoadingCache.refresh(key)` cho phép yêu cầu nạp lại bằng API. Trong Caffeine 3.x, phương thức trả `CompletableFuture` cho công việc refresh để caller có thể theo dõi hoàn thành. Đây là thao tác khác với `invalidate(key)`:

- **Refresh**: nạp bản thay thế bất đồng bộ; bản cũ có thể tiếp tục phục vụ khi đang refresh.
- **Invalidate**: loại bỏ entry; lần đọc sau phải load lại và có thể chờ.

Refresh chủ động là hữu ích sau khi nguồn cập nhật, nhưng phải cân nhắc race giữa refresh và thao tác put/invalidate concurrent. Không mặc định rằng bất đồng bộ có nghĩa mọi reader đã nhận bản mới ngay khi phương thức `refresh` được gọi.

## 5. So sánh trực diện ba khái niệm

| Câu hỏi | Expiration | Loading | Refreshing |
| --- | --- | --- | --- |
| Mục đích | Giới hạn thời gian một entry còn hợp lệ | Lấy giá trị khi thiếu entry hợp lệ | Làm mới entry hiện có |
| Trigger thường gặp | Vượt thời hạn theo write/access | Cache miss, bao gồm miss do expiration | Truy cập entry đủ tuổi refresh hoặc gọi refresh thủ công |
| Có thể trả giá trị cũ? | **Không** khi entry đã expired | Không có entry hợp lệ để trả | **Có**, trong lúc nạp mới, nếu entry chưa hết hạn |
| Ai cung cấp dữ liệu? | Không tự cung cấp | Mapping function/CacheLoader | CacheLoader/AsyncCacheLoader |
| Có phải cứ đến mốc là load? | Không; cần truy cập hoặc hoạt động liên quan | Không; cần lookup miss | Không; eligible không đồng nghĩa tự khởi chạy |
| Tác động latency | Miss sau expiry có thể phải đợi load | Load đồng bộ có thể làm tăng latency | Tránh chờ cho nhiều lần đọc nhờ phục vụ bản cũ tạm thời |
| Tác động tính mới | Tránh phục vụ entry vượt TTL | Lấy snapshot mới khi cần | Cho phép stale-while-revalidate có kiểm soát |
| Ví dụ API | `expireAfterWrite`, `expireAfterAccess` | `get(key)`, `CacheLoader` | `refreshAfterWrite`, `refresh(key)` |

### Soft TTL và hard TTL

Trong một số hệ thống, người ta gọi thời hạn refresh là **soft TTL** và thời hạn expiration là **hard TTL**:

- Soft TTL (refresh threshold): entry đủ điều kiện làm mới, bản cũ còn có thể dùng.
- Hard TTL (expiration threshold): entry không còn hợp lệ cho lookup, phải tải lại.

Đây là cách diễn giải trực quan, **không phải tên API thay thế**. Bản mới từ refresh thành công thay đổi write time và ảnh hưởng lần tính thời hạn kế tiếp.

## 6. Ví dụ Java 17+ chạy được: dùng đồng hồ giả, không Thread.sleep

Để tránh test dựa trên `Thread.sleep` dễ chập chờn, ví dụ sử dụng `AtomicLong` làm **ticker theo nanosecond**. Nó mô phỏng thời gian trôi mà không cần chờ thời gian thực. Ví dụ cũng dùng `CompletableFuture` chưa hoàn thành để **chủ động giữ refresh pending**, cho thấy trong lúc refresh, reader vẫn nhận bản cũ.

Ví dụ thuần Caffeine nhằm minh họa chính xác semantics của thư viện. **Không cần Spring ApplicationContext để gọi native `LoadingCache`.** Liên kết với Spring được giải thích ở phần 7.

Tạo dự án Java 17 với hai tệp:

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.github.ben-manes.caffeine:caffeine:3.1.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ExpirationLoadingRefreshDemo'
}
~~~

**`src/main/java/demo/ExpirationLoadingRefreshDemo.java`**

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import com.github.benmanes.caffeine.cache.CacheLoader;
import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.LoadingCache;

public class ExpirationLoadingRefreshDemo {

    public static void main(String[] args) {
        expirationAndLoading();
        refreshWhileServingOldValue();
    }

    static void expirationAndLoading() {
        AtomicLong clock = new AtomicLong();
        AtomicInteger sourceVersion = new AtomicInteger(1);
        AtomicInteger loads = new AtomicInteger();

        LoadingCache<String, String> cache = Caffeine.newBuilder()
                .ticker(clock::get)
                .expireAfterWrite(Duration.ofMinutes(5))
                .build(key -> {
                    loads.incrementAndGet();
                    return key + "-v" + sourceVersion.get();
                });

        System.out.println("expire t0: " + cache.get("A"));

        sourceVersion.set(2);
        clock.addAndGet(Duration.ofMinutes(4).toNanos());
        System.out.println("expire t4: " + cache.get("A"));

        clock.addAndGet(Duration.ofMinutes(2).toNanos());
        System.out.println("expire t6: " + cache.get("A"));
        System.out.println("expire loads: " + loads.get());
    }

    static void refreshWhileServingOldValue() {
        AtomicLong clock = new AtomicLong();
        AtomicInteger sourceVersion = new AtomicInteger(1);
        AtomicInteger loads = new AtomicInteger();
        AtomicInteger refreshAttempts = new AtomicInteger();
        AtomicReference<CompletableFuture<String>> pending =
                new AtomicReference<>();

        CacheLoader<String, String> loader = new CacheLoader<>() {
            @Override
            public String load(String key) {
                loads.incrementAndGet();
                return key + "-v" + sourceVersion.get();
            }

            @Override
            public CompletableFuture<String> asyncReload(
                    String key,
                    String oldValue,
                    Executor executor
            ) {
                refreshAttempts.incrementAndGet();
                CompletableFuture<String> future = new CompletableFuture<>();
                pending.set(future);
                return future;
            }
        };

        LoadingCache<String, String> cache = Caffeine.newBuilder()
                .ticker(clock::get)
                .refreshAfterWrite(Duration.ofMinutes(2))
                .expireAfterWrite(Duration.ofMinutes(10))
                .executor(Runnable::run)
                .build(loader);

        System.out.println("refresh t0: " + cache.get("B"));

        sourceVersion.set(2);
        clock.addAndGet(Duration.ofMinutes(3).toNanos());
        System.out.println("refresh t3 pending: " + cache.get("B"));
        System.out.println("refresh started: " + (pending.get() != null));

        // Hoàn tất lần nạp bất đồng bộ bằng dữ liệu mới.
        CompletableFuture<String> future = pending.get();
        if (future == null) {
            throw new IllegalStateException("refresh did not start");
        }
        future.complete("B-v" + sourceVersion.get());

        System.out.println("refresh t3 completed: " + cache.get("B"));
        System.out.println("refresh initial loads: " + loads.get());
        System.out.println("refresh attempts: " + refreshAttempts.get());

        // Vượt hard TTL tính từ lần ghi V2 lúc phút 3.
        sourceVersion.set(3);
        clock.addAndGet(Duration.ofMinutes(11).toNanos());
        System.out.println("refresh t14 expired: " + cache.get("B"));
        System.out.println("refresh final loads: " + loads.get());
    }
}
~~~

Từ thư mục chứa `build.gradle`, chạy bằng JDK 17+ và phiên bản Gradle tương thích:

~~~bash
gradle run --quiet
~~~

**Stdout dự kiến** theo luồng thực thi đã điều khiển đồng hồ và future ở trên:

~~~text
expire t0: A-v1
expire t4: A-v1
expire t6: A-v2
expire loads: 2
refresh t0: B-v1
refresh t3 pending: B-v1
refresh started: true
refresh t3 completed: B-v2
refresh initial loads: 1
refresh attempts: 1
refresh t14 expired: B-v3
refresh final loads: 2
~~~

### Đọc kết quả expiration

- Tại t0, entry A chưa có: `LoadingCache.get("A")` gọi loader và tạo A-v1.
- Nguồn chuyển sang V2 nhưng t4 vẫn nằm trong TTL 5 phút kể từ t0: `get` trả A-v1 **mà không chạy loader**.
- T6 vượt `expireAfterWrite` kể từ lần ghi t0. A-v1 hết hạn, `get` trở thành miss, loader chạy lần hai và nhận A-v2. `loads = 2`.
- Đây là **load sau expiration**, không phải refresh: không có khoảng thời gian được phép trả A-v1 sau khi entry đã hết hạn.

### Đọc kết quả refresh

- T0, B chưa có nên loader chạy: B-v1 và `loads = 1`.
- T3, B đủ tuổi `refreshAfterWrite(2m)` nhưng **chưa expired** vì hard TTL là 10 phút. `get("B")` khởi động refresh bằng `asyncReload`, trong khi `CompletableFuture` còn pending. Giá trị trả về là B-v1.
- Chương trình chủ động hoàn thành future bằng B-v2. `Caffeine` thay entry sau khi refresh thành công, nên lookup kế tiếp ở t3 đọc B-v2; refresh **không cần nạp lại theo miss**.
- `refreshAttempts = 1` biểu thị có một lần làm mới, còn `loads = 1` vì đường `load` ban đầu khác với đường `asyncReload` đã override.
- Sau khi t3 có bản B-v2, đồng hồ tăng tới t14 (11 phút sau write V2). Entry B-v2 hết hạn theo `expireAfterWrite(10m)`. Một `get` lúc này phải load qua `load` và nhận B-v3, thay vì tiếp tục trả B-v2 như một stale hit.

**Lưu ý kiểm thử:** `executor(Runnable::run)` chạy các callback trong cùng thread để ví dụ dễ dự đoán; đây **không phải cấu hình được khuyến nghị cho mọi ứng dụng production**, vì có thể làm các tác vụ async nặng chạy trên thread của caller. Trong ví dụ, `asyncReload` trả future đang pending, nên không chạy truy vấn chậm trên thread đọc. Cách điều khiển đồng hồ giả dùng public `ticker` là kỹ thuật testing được Caffeine khuyến nghị.

**Ranh giới ví dụ:** output là kết quả được suy luận từ code/Caffeine 3.1.8 với future kiểm soát, không phải log thu được từ một quá trình build đã chạy trong bài. Nếu test trong môi trường cụ thể khác kết quả, kiểm tra version và executor trước.

## 7. Kết nối khái niệm với Spring Cache Abstraction

### 7.1. Cấu hình expiration thông qua CaffeineCacheManager

Với Spring Framework 6.2.x, adapter Caffeine nằm trong module `spring-context-support`; cần dependency Caffeine tương thích. Ví dụ cấu hình trong ứng dụng có component scanning:

~~~groovy
dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
    implementation 'org.springframework:spring-context-support:6.2.14'
    implementation 'com.github.ben-manes.caffeine:caffeine:3.1.8'
}
~~~

~~~java
import java.time.Duration;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager("products");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(1_000)
                .expireAfterWrite(Duration.ofMinutes(5)));
        return manager;
    }
}
~~~

Cấu hình này là **đoạn class Spring minh họa**, không phải chương trình độc lập có `main`. Với service:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductView find(String sku) {
    return repository.findViewBySku(sku);
}
~~~

Đây cũng là **mã service minh họa** cần kiểu `ProductView`, `repository` và bean do Spring quản lý. Cơ chế thường gặp:

1. `@Cacheable` gọi vào cache theo key SKU.
2. Nếu entry còn hợp lệ thì trả bản đã cache; method `find` không cần chạy.
3. Nếu cache miss, gồm trường hợp entry đã expired, Spring gọi phần thân `find` để lấy dữ liệu.
4. Spring đưa kết quả mới vào cache theo policy của adapter/provider.

**Vì vậy, khi dùng manual Caffeine cache trong Spring adapter, chính method gắn `@Cacheable` đóng vai nguồn load trên cache miss.** Đây là một con đường loading hợp lệ, nhưng nó **không tự là một `CacheLoader` native** được Caffeine dùng cho background refresh.

### 7.2. refreshAfterWrite không tự chạy lại @Cacheable method

Đây là điểm dễ mắc lỗi nhất khi chuyển từ Caffeine native sang Spring annotation:

- Muốn Caffeine quản lý **refresh bất đồng bộ** theo `refreshAfterWrite`, phải cung cấp **`CacheLoader` hoặc `AsyncCacheLoader`** để biết cách tính lại value.
- Chỉ khai báo `refreshAfterWrite` lên một builder tạo **manual cache** mà không có loader không tự biến method `@Cacheable` thành native reload callback.
- `CaffeineCacheManager` có các API `setCacheLoader`, `setAsyncCacheLoader` và hỗ trợ đăng ký native cache tùy chỉnh để tạo cache có khả năng load/refresh.
- Nếu kết hợp `@Cacheable` với Caffeine loader, hãy thiết kế rõ **ai sở hữu đường load trên miss và đường reload trên refresh**. Không để method cacheable và loader nạp từ hai nguồn hoặc dùng hai cách mapping khác nhau.

Một chiến lược dễ kiểm soát là: **mọi lần load/reload cùng gọi một service đọc dữ liệu thuần**; tầng adapter hoặc controller chịu trách nhiệm điều phối cache. Loader tránh gọi lại một phương thức `@Cacheable` qua chính cache mà nó đang nạp, vì như vậy có thể sinh vòng gọi hoặc deadlock.

Chú ý thêm: cấu hình loader của `CaffeineCacheManager` áp dụng theo cách cache manager tạo cache. Nếu nhiều vùng cache lưu kiểu giá trị khác nhau, việc dùng một loader `Object,Object` chung đòi hỏi xử lý key/type cẩn thận; đôi khi đăng ký riêng một native loading cache cho từng vùng dễ kiểm soát hơn.

### 7.3. @Cacheable(sync = true) không phải refresh

`@Cacheable(sync = true)` yêu cầu provider hỗ trợ đồng bộ việc tính giá trị khi **cùng key bị miss đồng thời**, nhằm giảm khả năng nhiều thread cùng chạy loader nghiệp vụ. Nó **không** làm phương thức `@Cacheable` thành asynchronous refresh sau một soft TTL.

Nếu yêu cầu sản phẩm là “lần đầu chờ đọc đúng dữ liệu, những lần sau không chờ khi đến mốc refresh”, cần chọn chính sách Caffeine phù hợp và **xem rõ hợp đồng stale value**. Không coi `sync = true` như một cấu hình tương đương `refreshAfterWrite`.

### 7.4. Async cache mode là chủ đề riêng

Spring `CaffeineCacheManager` còn có `setAsyncCacheMode(true)`/`setAsyncCacheLoader` để hỗ trợ kiểu cache asynchronous và các API như `Cache.retrieve`. Đây là lựa chọn về **cách thực hiện truy cập bất đồng bộ**, không đồng nghĩa với “mọi entry sẽ tự làm mới định kỳ”.

Trong ứng dụng reactive hoặc CompletableFuture, kiểm tra riêng phiên bản Spring, return type, null handling và backend. Đừng trộn mặc định manual loading, native asynchronous refresh và Spring `@Cacheable` vào cùng một giả định không có test.

## 8. Lựa chọn chính sách cho bài toán nghiệp vụ

| Mục tiêu | Cấu hình / chiến lược có thể phù hợp | Đổi lại |
| --- | --- | --- |
| Không trả bản quá 5 phút kể từ write | `expireAfterWrite(5m)` + đường load khi miss | Lần đọc sau expiry có thể chờ load |
| Loại bỏ entry ít được truy cập | `expireAfterAccess(5m)` | Key hot có thể sống lâu dù nguồn đổi |
| Đọc nhanh, chấp nhận bản cũ ngắn hạn | `refreshAfterWrite(2m)` với loader | Có cửa sổ stale và độ trễ cập nhật sau trigger |
| Có hard limit và refresh mượt | Kết hợp `refreshAfterWrite` và `expireAfterWrite` | Phải xử lý refresh thất bại và read sau hard expiry |
| Dữ liệu nhạy cảm cần mới ngay sau update | Invalidation theo sự kiện/commit hoặc versioned keys | Thiết kế nhất quán phức tạp hơn timer-based refresh |
| Muốn dữ liệu được nạp trước khi có request | Scheduled preload hoặc push-based update chủ động | Không thể chỉ dựa vào `refreshAfterWrite` |
| Tránh cache tăng vô hạn | `maximumSize` / `maximumWeight` | Capacity eviction độc lập với TTL |
| Test thời gian không flaky | Inject `Ticker`, future kiểm soát, test maintenance nếu cần | Cần test đúng provider và executor |

### Khi refresh thất bại thì sao?

Caffeine thường giữ bản cũ nếu refresh bất đồng bộ gặp lỗi và entry chưa hết hạn. Điều này giúp availability nhưng có thể khiến dữ liệu cũ kéo dài hơn kỳ vọng về *soft refresh*. Nếu entry vượt **hard expiration** thì nó không được trả như hit; một lượt load mới có thể tiếp tục lỗi và ảnh hưởng caller.

Do vậy, với tỷ giá hoặc cấu hình quan trọng, cần xác định **độ cũ tối đa chấp nhận được**, metric cho refresh failure, chính sách retry, timeout và nguồn fallback. Không đánh đồng “giữ stale để phục vụ” với “đảm bảo luôn nhận dữ liệu chính xác tức thì”.

### Nếu hệ thống có nhiều instance

Caffeine native là cache **trong bộ nhớ của từng JVM**. Instance A refresh thành công không tự cập nhật native Caffeine cache ở instance B. Khi cùng nguồn được thay đổi bởi nhiều service, có thể cần pub/sub invalidation, cache phân tán hoặc hạn dùng ngắn hơn; không chỉ dựa vào local TTL để bảo đảm tính nhất quán toàn hệ thống.

## 9. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Tưởng TTL 5 phút nhưng key hot vẫn còn sau nhiều giờ | Dùng `expireAfterAccess`; mỗi lần đọc reset deadline | Dùng `expireAfterWrite` nếu cần giới hạn tuổi kể từ write |
| Entry không được refresh đúng mốc 2 phút | `refreshAfterWrite` chỉ tạo eligibility; chưa có lượt truy cập kích hoạt | Kiểm tra có request key sau mốc refresh hay không |
| Cấu hình refresh nhưng không có loader | Manual cache không biết cách reload | Chuyển sang LoadingCache/AsyncLoadingCache có loader |
| Lần đọc sau expiry chậm | Expired entry dẫn tới cache miss và load đồng bộ | Xem latency nguồn, async design, refresh threshold phù hợp |
| Lần đọc tại thời điểm refresh vẫn thấy bản cũ | Refresh chạy nền, cố ý phục vụ stale | Chờ refresh hoàn thành hoặc yêu cầu invalidation chặt hơn |
| Refresh lỗi nhưng cache vẫn có dữ liệu | Caffeine giữ giá trị cũ nếu refresh thất bại | Giám sát lỗi, stale age và hard TTL |
| `estimatedSize` chưa giảm sau thời gian hết hạn | Maintenance chưa dọn vật lý | Kiểm tra logic get, thử `cleanUp` trong test, cân nhắc Scheduler |
| `@Cacheable` miss vẫn gọi method thay vì native CacheLoader | Spring và Caffeine có các đường nạp riêng | Xác định adapter, cache mode và đơn vị sở hữu loader |
| Refresh xong vẫn có stale ở instance khác | Caffeine local từng JVM | Thiết kế invalidation/refresh đa instance |
| Đọc sai kết quả khi source thay đổi sau update | TTL không đồng nghĩa invalidate theo nghiệp vụ | `@CacheEvict`, event after commit hoặc versioned key |
| Test refresh ngẫu nhiên pass/fail | Dùng `Thread.sleep` và executor bất định | Dùng fake ticker, controlled CompletableFuture, đồng bộ kết quả |

## 10. Tự kiểm tra

**Câu 1.** Cache dùng `expireAfterWrite(5m)`. Ở phút 4, caller đọc key A thành công. Ở phút 6, chỉ tính từ lần put t0, A còn hợp lệ không?

**Đáp án:** Không. Đọc thành công ở t4 không reset write deadline. Một `LoadingCache.get("A")` tại t6 phải xử lý miss và nạp lại.

**Câu 2.** Cache dùng `expireAfterAccess(5m)` và có lượt đọc vào t4. Tại t6, A đã expired chưa?

**Đáp án:** Chưa, giả sử không có sự kiện khác khiến eviction: chỉ 2 phút từ lần access gần nhất, chưa vượt 5 phút.

**Câu 3.** `refreshAfterWrite(2m)` có tự chạy đúng tại t2 dù không có request?

**Đáp án:** Không. Entry chỉ đủ điều kiện refresh; tự động làm mới thường bắt đầu khi key được query sau mốc đó.

**Câu 4.** Một refresh chưa hoàn thành và key vẫn chưa expired. Người đọc có thể nhận giá trị cũ không?

**Đáp án:** Có. Caffeine có thể trả bản cũ trong lúc nạp bản mới bất đồng bộ, giúp giảm latency.

**Câu 5.** `@Cacheable` trên method Spring có đồng nghĩa Caffeine biết cách chạy method đó trong `CacheLoader.reload`?

**Đáp án:** Không. Spring quản lý method invocation trên miss; native refresh cần loader/async loader được cấu hình rõ ràng cho Caffeine.

**Câu 6.** Kết hợp `refreshAfterWrite(2m)` và `expireAfterWrite(10m)` nhưng key không được đọc trong 15 phút. Khi đọc lại có thể dùng bản cũ và refresh nền không?

**Đáp án:** Không nếu entry đã expired. Refresh eligibility không chặn hard expiration; khi key được yêu cầu, phải xử lý miss/load.

**Câu 7.** Vì sao sau TTL `estimatedSize` đôi khi chưa giảm?

**Đáp án:** Cleanup vật lý được thực hiện trong đợt maintenance; trạng thái không còn hợp lệ để lookup và số lượng entry được dọn thực tế không nhất thiết cập nhật cùng một thời điểm.

## 11. Ghi nhớ và tài liệu tham khảo

- **Expiration** giới hạn khả năng dùng entry cũ; **loading** lấy giá trị mới khi miss; **refreshing** thay bản hiện có mà có thể tạm phục vụ stale.
- `expireAfterWrite` đếm theo lần ghi; `expireAfterAccess` đếm theo lần truy cập gần nhất.
- `LoadingCache.get(key)` có `CacheLoader` để xử lý miss; manual `Cache.getIfPresent(key)` không tự load.
- `refreshAfterWrite` cần loader, chỉ tạo **điều kiện refresh**, không phải một timer chạy nền độc lập.
- `refreshAfterWrite` có thể kết hợp `expireAfterWrite`; một key expired không được trả chỉ vì refresh đang được cấu hình.
- Spring `@Cacheable` trên miss và Caffeine `CacheLoader` là **hai con đường nạp cần phân biệt**. Muốn native refresh, cấu hình loader đúng provider.
- TTL, refresh và capacity eviction không bảo đảm atomic consistency với database hay giữa nhiều JVM.

**Tài liệu chính thức:**

- [Caffeine Wiki – Eviction và expiration](https://github.com/ben-manes/caffeine/wiki/Eviction)
- [Caffeine Wiki – Population/Loading](https://github.com/ben-manes/caffeine/wiki/Population)
- [Caffeine Wiki – Refresh](https://github.com/ben-manes/caffeine/wiki/Refresh)
- [Caffeine Wiki – Testing bằng Ticker](https://github.com/ben-manes/caffeine/wiki/Testing)
- [Caffeine Wiki – Specification](https://github.com/ben-manes/caffeine/wiki/Specification)
- [Spring Framework 6.2 – CaffeineCacheManager API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html)
- [Spring Framework 6.2 – Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)

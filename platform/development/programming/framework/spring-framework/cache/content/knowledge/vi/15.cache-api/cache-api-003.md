# Cache.ValueWrapper và biến thể get có kiểu trong Spring Cache

## Mục tiêu

Khi thao tác trực tiếp với **org.springframework.cache.Cache**, có hai cách đọc dễ bị nhầm:

- **Cache.ValueWrapper get(Object key)**: trả về *wrapper* nếu key có entry; trả về **null** nếu key không có entry. Bản thân wrapper vẫn có thể chứa **giá trị null**.
- **<T> T get(Object key, Class<T> type)**: trả về giá trị đã được kiểm tra theo kiểu runtime yêu cầu; trả về **null** nếu không có entry **hoặc** nếu entry có giá trị null. Vì vậy API này **không phân biệt hai trường hợp đó**.

Spring còn có **<T> T get(Object key, Callable<T> valueLoader)** để *đọc hoặc tải khi miss*. Đây là một overload khác: tham số thứ hai là **hàm tải**, không phải **Class<T>**. Bài học đi sâu vào sự khác nhau, xử lý null, type safety, exception, null sentinel, bẫy generic và ví dụ chạy thật trên Java 17.

Sau khi học, bạn có thể:
1. Phân biệt chính xác **MISS**, **HIT với null** và **HIT với giá trị khác null** bằng Cache.ValueWrapper.
2. Chọn **get(key, User.class)** khi chỉ muốn value đúng kiểu và không cần phân biệt missing với cached-null.
3. Giải thích trường hợp **IllegalStateException** khi entry không khớp type, và lý do generic `List<User>` không được kiểm tra bằng `List.class`.
4. Biết `get(key, Callable<T>)` **không phải typed-get**, hiểu cơ chế tải khi miss và `Cache.ValueRetrievalException`.
5. Hiểu `ConcurrentMapCacheManager.setAllowNullValues(true/false)`, tác dụng của cache entry null và khác biệt với Java `Map.get`.
6. Tự chạy chương trình minh họa bằng **JDK 17 + Spring Framework 6.2.19** để kiểm tra từng trạng thái.

Bối cảnh: Spring Cache Abstraction, sử dụng **programmatic Cache API** thay vì chỉ dùng annotation `@Cacheable`. Ví dụ dùng **ConcurrentMapCacheManager** trong một JVM; chính sách null và đồng thời của provider khác cần được xác minh riêng.

---

## 1. Một cache entry có ba trạng thái quan sát được

Với key `user:42`, trạng thái logic có thể là:

| Trạng thái | Có mapping cho key? | Giá trị logic của entry |
| --- | --- | --- |
| **MISS** | Không | Không có giá trị |
| **HIT–NULL** | Có | `null` |
| **HIT–VALUE** | Có | Đối tượng không null, ví dụ `User("42","Lan")` |

Tại sao cần phân biệt? Trong ứng dụng, `null` đôi khi là **kết quả nghiệp vụ hợp lệ**, chẳng hạn "đã tra cứu và xác định không có hồ sơ" (negative caching). Một key chưa từng tra cứu lại là **không có entry**. Nếu nhập nhằng, code có thể tải lại dữ liệu dù đã cache kết quả null, hoặc cho rằng đã cache trong khi key chưa hề tồn tại.

**Cache.ValueWrapper** được thiết kế để tách **sự hiện diện của entry** khỏi **giá trị bên trong entry**.

~~~text
cache.get(key)   // overload chỉ có một tham số
       |
       +-- trả Java null     => Không có mapping / MISS
       |
       +-- trả ValueWrapper  => Có mapping / HIT
                  |
                  +-- wrapper.get() == null  => cached-null
                  |
                  +-- wrapper.get() != null  => cached-value
~~~

**Lưu ý:** `Cache.ValueWrapper` là interface lồng trong `Cache`, không phải một kiểu generic `ValueWrapper<T>`. Method `get()` của wrapper trả **Object**, nên cần kiểm tra kiểu hoặc cast phù hợp.

## 2. get(key): kiểm tra ValueWrapper đúng cách

Khai báo trong interface Cache (đơn giản hóa phần annotation nullable):

~~~java
Cache.ValueWrapper get(Object key);
~~~

Hợp đồng:
- **Trả về null**: không có mapping tương ứng (cache miss).
- **Trả về một ValueWrapper**: có entry, kể cả khi value logic đã được cache là null.
- **wrapper.get()**: trả về payload sau khi Spring/provider chuyển đổi từ representation trong store về giá trị ứng dụng; payload có thể null.

Đoạn xử lý nên bắt đầu bằng **kiểm tra wrapper**, không gọi ngay wrapper.get():

~~~java
Cache.ValueWrapper wrapper = cache.get("user:42");

if (wrapper == null) {
    System.out.println("MISS");
} else if (wrapper.get() == null) {
    System.out.println("HIT_NULL");
} else {
    System.out.println("HIT_VALUE=" + wrapper.get());
}
~~~

Đây là **đoạn minh họa**, với biến `cache` đã được gán một Spring Cache. Chú ý `wrapper == null` và `wrapper.get() == null` là **hai điều kiện khác nhau**.

### Sai: dereference trực tiếp wrapper

~~~java
// SAI nếu key chưa được lưu:
Object result = cache.get("missing").get();
~~~

Khi `get("missing")` trả null, câu lệnh ném **NullPointerException** trước khi lấy payload. Cách sửa: kiểm tra wrapper null trước.

### Sai: chỉ xét payload để kết luận miss

~~~java
// SAI về mặt semantics nếu cache cho phép cached-null:
Cache.ValueWrapper wrapper = cache.get("user:42");
Object value = wrapper == null ? null : wrapper.get();

if (value == null) {
    // Không thể khẳng định đây là MISS.
}
~~~

`value == null` ở đây có thể có nghĩa **không có mapping** hoặc **mapping chứa null**. Nếu quyết định nghiệp vụ cần biết hai trạng thái, giữ lại thông tin từ wrapper.

### Tự xây một kiểu kết quả rõ ràng hơn

Với logic lớn, có thể chuyển trạng thái đọc thành một kiểu domain đơn giản:

~~~java
// Đoạn minh họa Java 17, các thành phần nằm trong một class phù hợp.
enum LookupState { MISS, HIT_NULL, HIT_VALUE }

static LookupState stateOf(Cache cache, Object key) {
    Cache.ValueWrapper w = cache.get(key);
    if (w == null) return LookupState.MISS;
    return w.get() == null
        ? LookupState.HIT_NULL
        : LookupState.HIT_VALUE;
}
~~~

Không cần truy cập `getNativeCache()` hoặc một sentinel riêng để phân biệt ba trạng thái. Đây là lý do Spring Cache cung cấp wrapper.

**Chú ý về tính đồng thời:** `stateOf` phản ánh trạng thái quan sát được ở thời điểm `get` trả về. Thread khác có thể `put` hoặc `evict` ngay sau đó. Một phép đọc wrapper không phải transaction hay snapshot bảo đảm lâu dài.

## 3. get(key, Class<T>): lấy giá trị có kiểm tra kiểu runtime

Khai báo tương đương:

~~~java
<T> T get(Object key, Class<T> type);
~~~

Ví dụ:

~~~java
User user = cache.get("user:42", User.class);
~~~

Đây là đoạn minh họa; `User` và `cache` cần được ứng dụng định nghĩa. Spring trả về:
- `User` nếu entry chứa giá trị tương thích với `User.class`.
- `null` nếu **không có entry**.
- `null` nếu có entry nhưng value logic đã lưu là **null**.
- **IllegalStateException** nếu entry tồn tại, value khác null và **không phù hợp kiểu yêu cầu**.

API typed get tiện khi code chỉ cần một object đúng type và không cần biết hit-null khác miss. Nó **không** phải lời gọi phát lệnh load từ database khi cache miss.

### Hai phép get khác nhau, cùng key

~~~java
Cache.ValueWrapper raw = cache.get("user:42");
User typed = cache.get("user:42", User.class);
~~~

Nếu entry có `null`:
- `raw` **khác null**, `raw.get()` là null.
- `typed` là null.

Nếu không có entry:
- `raw` là null.
- `typed` cũng là null.

Do đó **typed get loại bỏ một bit thông tin quan trọng: entry có tồn tại hay không**. Nếu cần làm *negative caching* hoặc kiểm tra tồn tại, ưu tiên wrapper.

### Khi sai kiểu: IllegalStateException, không phải miss

Ví dụ cache lưu `User` nhưng caller yêu cầu `String`:

~~~java
cache.put("user:42", new User("42", "Lan"));
String text = cache.get("user:42", String.class);
// IllegalStateException: value không tương thích String.class.
~~~

Đoạn này minh họa, cần có class/record User và biến cache. Đừng viết:

~~~java
// SAI về tư duy: coi tất cả lỗi kiểu là cache miss.
try {
    return cache.get(key, String.class);
} catch (IllegalStateException ignored) {
    return loadAndOverwriteFromSource(key);
}
~~~

Đây là code minh họa cố ý không đầy đủ. Lỗi sai kiểu thường báo **mâu thuẫn giữa schema cache và logic dùng cache**: dùng chung cacheName/key cho các kiểu khác nhau, dữ liệu phiên bản cũ, serializer/config sai hoặc cast thiếu kiểm tra. Bắt rồi mặc định load lại có thể che giấu lỗi và ghi đè entry của một nghiệp vụ khác.

**Kiểm tra kiểu không đồng nghĩa deserialize an toàn.** Nếu cache phân tán, provider có thể thất bại ngay trong bước deserialize hoặc chuyển đổi value, trước cả khi typed get thực hiện kiểm tra Class. Cần kiểm thử trên provider thực tế.

### Class<T> không kiểm tra sâu generic parameter

~~~java
// List.class chỉ thể hiện runtime type List, không phải List<User>.
List<?> items = cache.get("users:list", List.class);
~~~

Nếu entry thật sự chứa `List<String>`, nó vẫn là `List` tại runtime. `List.class` **không phát hiện** rằng caller muốn `List<User>`. Thông tin `<User>` bị **type erasure** trong Java, nên không thể viết `List<User>.class`.

Nếu cần đảm bảo mỗi phần tử là User, hãy tự kiểm tra phần tử, dùng DTO wrapper có kiểu rõ, hoặc để serializer/type metadata xử lý ở một lớp được thiết kế riêng.

### type có thể null, nhưng không nên lạm dụng

Hợp đồng của Spring cho phép tham số `Class<T> type` là null để **bỏ qua kiểm tra kiểu**:

~~~java
Object value = cache.get("user:42", (Class<Object>) null);
~~~

Đây là minh họa API hợp lệ về ý nghĩa; khi dùng Java hiện đại, thường dễ đọc và an toàn hơn nếu chọn một `Class` thực sự hoặc dùng wrapper. `type=null` **không** làm cache nhận biết kiểu generic từ biến gán ở bên trái. Nó chỉ bỏ qua bước xác minh kiểu runtime.

**Một lỗi overload đáng chú ý:** `cache.get(key, null)` có thể không biên dịch vì Java không biết chọn overload `Class<T>` hay `Callable<T>`. Hãy chỉ định kiểu/cast rõ nếu thực sự có chủ đích; tốt nhất không truyền null mơ hồ.

## 4. Bảng quyết định: wrapper hay typed get?

| Mục đích | Chọn API | Lý do |
| --- | --- | --- |
| Cần biết key có entry hay chưa | **get(key)** | Wrapper null nghĩa là miss |
| Cần phân biệt cached-null với miss | **get(key)** | Wrapper hiện diện dù payload null |
| Chỉ muốn một `User` hợp lệ hoặc null | **get(key, User.class)** | Type check và trả về trực tiếp |
| Cần phát hiện value sai kiểu | **get(key, Class<T>)** | Ném IllegalStateException khi mismatch |
| Muốn kiểm tra sâu `List<User>` | **Không đủ với get(key, List.class)** | Class chỉ kiểm tra raw List |
| Muốn tính giá trị khi miss | **get(key, Callable<T>)** | Overload loader riêng |
| Muốn chặn duplicate load ở cache provider | **get(key, Callable<T>)** + kiểm tra provider | Một số implementation phối hợp loader atomically |
| Muốn xử lý truy xuất bất đồng bộ | **retrieve(...)** nếu provider hỗ trợ | API khác, kết quả CompletableFuture |

Tất cả các biến thể đều cần **cacheName và key đúng**. Typed get không tự chọn đúng cache và không tự tạo một entry mới nếu không có loader.

## 5. Null được lưu thế nào trong ConcurrentMapCache?

Một `ConcurrentHashMap` thông thường **không cho phép value null**. Tuy nhiên, Spring `ConcurrentMapCacheManager` **mặc định cho phép giá trị null logic** bằng cách lưu một **giá trị đại diện nội bộ** (null sentinel, thường dựa trên NullValue) trong map và chuyển đổi khi trả về qua Cache API.

Với cấu hình mặc định:

~~~java
ConcurrentMapCacheManager manager =
    new ConcurrentMapCacheManager("users");

Cache cache = manager.getCache("users");
cache.put("u:null", null);

Cache.ValueWrapper wrapper = cache.get("u:null");
// wrapper != null, wrapper.get() == null.
~~~

Đoạn minh họa giả sử không có lỗi khởi tạo Cache và `manager.getCache("users")` khác null. Trong bài runnable bên dưới, ta dùng `Objects.requireNonNull` để kiểm tra rõ.

**Tại sao không trả null trực tiếp khi cache có cached-null?** Bởi nếu trả Java null thẳng, caller không phân biệt được "key không tồn tại" với "key tồn tại chứa null". Spring dùng ValueWrapper để bảo toàn sự khác biệt ở overload một tham số.

### Tắt khả năng cache null

~~~java
ConcurrentMapCacheManager manager =
    new ConcurrentMapCacheManager("users");
manager.setAllowNullValues(false);
~~~

Với `allowNullValues=false`, cache không chấp nhận lưu null theo cơ chế đó; tùy call path, cố put null có thể dẫn đến lỗi hoặc được xử lý theo quy tắc cụ thể của integration. **Không mặc định suy ra `put(key, null)` sẽ âm thầm xóa entry**.

Cần nhớ:
- `setAllowNullValues(true)` **là mặc định của ConcurrentMapCacheManager**, không phải thuộc tính bắt buộc của mọi cache provider.
- Thay đổi cấu hình null cho manager này có thể **reset các cache đã tạo** để áp dụng chính sách mới; không dùng thao tác này một cách tùy tiện trong production.
- Một provider khác có thể không hỗ trợ cache null, hoặc có quy tắc serialize/negative caching riêng.
- `get(key, User.class)` vẫn trả null cho cả **cached-null** và **miss**, bất kể cách implementation lưu sentinel nội bộ.

### Cached-null không giống Optional.empty()

Một vài ứng dụng muốn lưu `Optional.empty()` hoặc một value domain như `NotFound`. Đó là **đối tượng non-null** ở API Java, khác với lưu `null`.

Nếu dùng `Optional<User>` làm return type của `@Cacheable`, Spring annotation caching có các quy tắc thích ứng cho Optional riêng. Đừng suy diễn rằng `Cache.put(key, Optional.empty())`, `Cache.put(key, null)` và `@Cacheable` trả Optional.empty đều được lưu y hệt trong mọi provider. Thiết kế và kiểm tra trực tiếp trên abstraction/annotation đang sử dụng.

## 6. API thứ ba: get(key, Callable<T> valueLoader)

Ngoài hai overload chính, Cache có:

~~~java
<T> T get(Object key, java.util.concurrent.Callable<T> valueLoader);
~~~

Hợp đồng:
1. Nếu key đã có mapping hợp lệ, trả giá trị đang cache.
2. Nếu miss, gọi `valueLoader.call()` để tính giá trị.
3. Lưu kết quả của loader vào cache theo khả năng provider, rồi trả result.
4. Nếu loader ném exception, Spring Cache API cung cấp **Cache.ValueRetrievalException** bao lỗi nguồn.
5. Việc phối hợp tải đồng thời cho cùng key phụ thuộc implementation; không coi đây là distributed lock bảo vệ toàn bộ workflow.

Ví dụ:

~~~java
AtomicInteger loads = new AtomicInteger();

String first = cache.get("greeting", () ->
    "hello-" + loads.incrementAndGet());

String second = cache.get("greeting", () ->
    "hello-" + loads.incrementAndGet());
~~~

Trong một cache hoạt động bình thường mà không có eviction/concurrent writer, `first` và `second` đều là "hello-1"; bộ đếm loads là 1. **Đây không phải overload kiểm tra Class<T>**: compiler suy ra T từ Callable, nhưng runtime không nhận `Class<T>` để xác minh kiểu đã cache giống typed get.

### Khi nào loader không chạy?

Nếu entry đã tồn tại, kể cả entry **cached-null** trong provider có hỗ trợ null, loader có thể **không được gọi**. Điều này bảo toàn negative cache. Không viết code cho rằng `get(key, Callable)` sẽ gọi lại loader bất cứ khi nào result trả về null.

### Nếu loader ném checked exception

~~~java
try {
    cache.get("remote", () -> {
        throw new java.io.IOException("Remote service down");
    });
} catch (Cache.ValueRetrievalException ex) {
    Throwable root = ex.getCause();
    // Xử lý root hoặc phân loại lỗi hạ tầng tại đây.
}
~~~

Đoạn minh họa. Trong concurrent implementation hoặc provider từ xa, lỗi cache store/network có thể không được biểu diễn giống lỗi từ valueLoader; hãy phân biệt ngoại lệ của **loader** với lỗi của **cache provider**.

### Quan hệ với @Cacheable(sync=true)

Khi annotation `@Cacheable(sync=true)` được dùng, Spring cache interceptor yêu cầu Cache implementation phối hợp load cho cùng key qua các API loader thích hợp. Nhưng:
- Không phải mọi provider bảo đảm single-flight giống nhau.
- Nó không tuần tự hóa `@CachePut`, `@CacheEvict` và transaction database.
- `@Cacheable(sync=true)` có các ràng buộc annotation riêng (ví dụ không phối hợp `unless`); đừng áp các ràng buộc ấy lên mọi cách gọi programmatic `get(key, Callable)`.

## 7. Ví dụ Java 17 chạy được: quan sát cả ba trạng thái và ba overload

Ví dụ sau **không cần Spring Boot**, cũng không cần `@EnableCaching`, bởi chúng ta gọi **Cache API trực tiếp**. Việc dùng CacheManager từ Spring Framework chỉ cần đưa dependency `spring-context` vào Maven.

### 7.1. Cấu trúc thư mục

~~~text
cache-get-variants/
├── pom.xml
└── src/main/java/demo/CacheGetVariantsDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-get-variants</artifactId>
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

### 7.3. src/main/java/demo/CacheGetVariantsDemo.java

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;

import java.io.IOException;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class CacheGetVariantsDemo {

    public record User(String id, String name) {}

    public static void main(String[] args) {
        ConcurrentMapCacheManager manager =
            new ConcurrentMapCacheManager("users");
        manager.setAllowNullValues(true);

        Cache cache = Objects.requireNonNull(
            manager.getCache("users"), "Cache 'users' not found");

        cache.put("u1", new User("u1", "Lan"));
        cache.put("nil", null); // Cached-null thực sự.
        // Không put key "missing" -> MISS.

        Cache.ValueWrapper wrappedUser = cache.get("u1");
        Cache.ValueWrapper wrappedNull = cache.get("nil");
        Cache.ValueWrapper wrappedMissing = cache.get("missing");

        System.out.println("raw-user-present="
            + (wrappedUser != null));
        System.out.println("raw-user-value="
            + wrappedUser.get());
        System.out.println("raw-null-present="
            + (wrappedNull != null));
        System.out.println("raw-null-payload="
            + wrappedNull.get());
        System.out.println("raw-missing=" + wrappedMissing);

        System.out.println("typed-user="
            + cache.get("u1", User.class));
        System.out.println("typed-null="
            + cache.get("nil", User.class));
        System.out.println("typed-missing="
            + cache.get("missing", User.class));

        try {
            cache.get("u1", String.class);
            System.out.println("typed-wrong=unexpected");
        } catch (IllegalStateException ex) {
            System.out.println("typed-wrong="
                + ex.getClass().getSimpleName());
        }

        AtomicInteger computeCount = new AtomicInteger();
        String computed1 = cache.get("computed", () ->
            "computed-" + computeCount.incrementAndGet());
        String computed2 = cache.get("computed", () ->
            "computed-" + computeCount.incrementAndGet());

        System.out.println("computed-1=" + computed1);
        System.out.println("computed-2=" + computed2);
        System.out.println("compute-calls="
            + computeCount.get());

        AtomicInteger nullLoaderCount = new AtomicInteger();
        String fromCachedNull = cache.get("nil", () -> {
            nullLoaderCount.incrementAndGet();
            return "should-not-run";
        });
        System.out.println("cached-null-loader="
            + fromCachedNull);
        System.out.println("cached-null-loader-calls="
            + nullLoaderCount.get());

        try {
            cache.get("error", () -> {
                throw new IOException("boom");
            });
            System.out.println("loader-error=unexpected");
        } catch (Cache.ValueRetrievalException ex) {
            System.out.println("loader-error="
                + ex.getCause().getClass().getSimpleName());
        }

        cache.evict("nil");
        System.out.println("after-evict-null="
            + cache.get("nil"));
    }
}
~~~

**Đặc điểm của ví dụ:**
- `cache.put("nil", null)` được chấp nhận vì manager hỗ trợ cached-null. Dù ConcurrentHashMap nền không lưu trực tiếp Java null, API trả một wrapper có payload null.
- Record `User` có `toString()` sinh tự động ổn định với `User[id=..., name=...]`.
- Typed get sai `String.class` bị bắt dưới dạng `IllegalStateException`.
- Hai lượt `get("computed", Callable)` không xen kẽ writer/evict nên loader chạy một lần.
- `get("nil", Callable)` không chạy loader vì key có cached-null; result vẫn là null.
- Loader ném `IOException` được biểu diễn qua `Cache.ValueRetrievalException`; `getCause()` là IOException.
- Sau `evict("nil")`, overload một tham số trả Java null vì entry không còn.

### 7.4. Lệnh chạy

Từ thư mục có `pom.xml` (JDK 17+ và Maven đã cài):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheGetVariantsDemo
~~~

**Stdout do các System.out.println của chương trình tạo ra** (không tính log riêng của Maven hoặc thư viện):

~~~text
raw-user-present=true
raw-user-value=User[id=u1, name=Lan]
raw-null-present=true
raw-null-payload=null
raw-missing=null
typed-user=User[id=u1, name=Lan]
typed-null=null
typed-missing=null
typed-wrong=IllegalStateException
computed-1=computed-1
computed-2=computed-1
compute-calls=1
cached-null-loader=null
cached-null-loader-calls=0
loader-error=IOException
after-evict-null=null
~~~

### 7.5. Đọc output theo semantics của Cache API

1. **raw-user-present=true**: `get("u1")` có ValueWrapper vì key đã được put. Payload là User record.
2. **raw-null-present=true** cùng **raw-null-payload=null**: key `nil` là **HIT–NULL**, không phải miss.
3. **raw-missing=null**: key chưa từng được put, nên wrapper tự nó là null.
4. **typed-null=null** và **typed-missing=null**: typed get đã gộp hai trạng thái, đúng theo hợp đồng API.
5. **typed-wrong=IllegalStateException**: Spring phát hiện value User không phù hợp với type String.
6. **compute-calls=1**: loader chạy khi miss đầu tiên; lần thứ hai nhận cached value.
7. **cached-null-loader-calls=0**: với cached-null có mapping hợp lệ, provider không gọi loader dù giá trị trả về là null.
8. **loader-error=IOException**: IOException là nguyên nhân gốc bên trong ValueRetrievalException.
9. **after-evict-null=null**: sau khi xóa key, `get("nil")` một tham số cho thấy miss.

Ví dụ này dùng cache in-memory **theo một tiến trình và không tạo concurrent race**. Với Redis, JCache hoặc provider khác, cần kiểm tra null handling, serialization và hợp đồng lỗi riêng; không dùng output này để khẳng định mọi provider đồng nhất ở chi tiết nội bộ.

## 8. Khi nào nên tự dùng Cache API, khi nào dùng annotation?

Spring Cache có hai cách phổ biến:

**1. Cách khai báo bằng annotation**:

~~~java
@Cacheable(cacheNames = "users", key = "#p0")
public User findById(String id) {
    return repository.findById(id);
}
~~~

Đây là method minh họa, không độc lập. Spring cache interceptor phụ trách lookup và put result dựa trên annotation, với điều kiện cấu hình @EnableCaching và lời gọi qua Spring proxy đúng. Code nghiệp vụ không cần tự gọi `Cache.get` hay `Cache.put`.

**2. Cách lập trình qua Cache API**:

~~~java
Cache users = Objects.requireNonNull(
    cacheManager.getCache("users"));

Cache.ValueWrapper wrapper = users.get(id);
if (wrapper != null) {
    return (User) wrapper.get();
}
User result = repository.findById(id);
users.put(id, result);
return result;
~~~

Đây là ví dụ minh họa cần bổ sung context class, biến `id`, `cacheManager`, repository và cast hợp lệ. Nó **không tự động đồng bộ** toàn bộ check–load–put giữa các thread. Trong hệ thống thật, `get(key, Callable)` có thể đơn giản hóa load-on-miss và cung cấp phối hợp theo provider, nhưng vẫn phải xét type/null/concurrency.

**Chọn annotation** nếu cache operation trùng với method boundary, quy tắc key/condition tương đối rõ và bạn muốn tách cross-cutting concern khỏi code nghiệp vụ. **Chọn Cache API** nếu cần quyết định trên wrapper, quản lý negative cache, invalidate một key cụ thể hoặc chủ động điều khiển caching ở nhiều bước.

### Một sai lầm: dùng Cache.get mà không kiểm soát cacheName/key

~~~java
Cache cache = cacheManager.getCache("users");
Cache.ValueWrapper wrapper = cache.get(id);
~~~

Dù dùng wrapper hay typed get, dữ liệu chỉ khớp nếu **cacheName** và **key** đúng với nơi producer đã `put`. Nếu `@Cacheable` dùng key SpEL `#p0.toLowerCase()` mà code programmatic dùng nguyên chuỗi đầu vào, sẽ miss dù entry tồn tại dưới khóa khác.

Tương tự, nếu producer dùng `@CacheConfig(cacheManager="redisManager")` còn code programmatic đọc `localManager`, hai bên có thể truy cập hai kho khác nhau. Wrapper không tự sửa sai sót định danh cache.

## 9. Những lỗi thường gặp và cách sửa

### Lỗi 1: `cache.get(key).get()` gây NullPointerException

**Nguyên nhân:** key miss, nên ValueWrapper là null.

**Cách sửa:**

~~~java
Cache.ValueWrapper w = cache.get(key);
if (w == null) {
    // Miss -> có thể load hoặc trả về absent.
} else {
    Object payload = w.get(); // Payload vẫn có thể null.
}
~~~

### Lỗi 2: `get(key, User.class) == null` bị coi là chắc chắn miss

**Nguyên nhân:** typed get không phân biệt cached-null và miss.

**Cách sửa:** Dùng `Cache.ValueWrapper` để nhận biết entry có mặt; hoặc thiết kế một marker/DTO nghiệp vụ riêng nếu không muốn cache null.

### Lỗi 3: Type mismatch bị nuốt như cache miss

**Nguyên nhân:** cùng cacheName/key được dùng bởi nhiều loại dữ liệu, hoặc cache tồn tại sau khi code/schema đã thay đổi.

**Cách sửa:** sửa key namespace và type contract, có kế hoạch version/invalidation khi triển khai; tránh bắt IllegalStateException rồi âm thầm đè entry.

### Lỗi 4: Tin rằng `List.class` kiểm tra `List<User>`

**Nguyên nhân:** Java generics bị xóa type argument ở runtime.

**Cách sửa:** Dùng DTO wrapper chuyên biệt, validate từng phần tử hoặc dùng cơ chế serialization có type metadata phù hợp. `Class<List<User>>` không thể viết trực tiếp với `List<User>.class`.

### Lỗi 5: Nhầm `get(key, Callable)` là typed get

**Nguyên nhân:** cả hai overload đều có hai tham số và đều được gọi `get`.

**Cách sửa:** Nhìn tham số thứ hai:
- `User.class` → yêu cầu kiểm tra kiểu, **không load**.
- `() -> repository.load(id)` → **loader khi miss**, không truyền Class runtime.

### Lỗi 6: `get(key, Callable)` gọi loader nhiều lần khi có concurrent miss

**Nguyên nhân khả dĩ:** provider không phối hợp loader theo cùng key như mong đợi, key không ổn định, nhiều instance/cache tách biệt, entry bị evict/expire hoặc loader gặp lỗi.

**Cách sửa:** test trên đúng provider, quan sát key và cacheName, kiểm tra guarantee single-flight; nếu đòi hỏi nhất quán liên node, cần chiến lược mạnh hơn một API loader.

### Lỗi 7: `put(key, null)` không hoạt động trên provider khác

**Nguyên nhân:** chỉ một số implementation hỗ trợ cached-null, có thể thông qua sentinel.

**Cách sửa:** xác định chính sách null của provider/cache manager; khi cần negative cache giữa nhiều môi trường, cân nhắc marker DTO chuyên biệt thay vì dựa vào khả năng lưu null.

### Lỗi 8: Dùng `getNativeCache()` để suy luận cached-null

**Nguyên nhân:** nhìn trực tiếp map/Redis store và thấy sentinel, serialized value hoặc provider wrapper.

**Cách sửa:** Ưu tiên **Cache API** để nhận semantics thống nhất. `getNativeCache()` trả về đối tượng riêng của provider, chi tiết nội bộ có thể đổi; không dựa vào NullValue hay representation nội bộ để xác định miss.

### Lỗi 9: Tin rằng giá trị đã lấy từ cache là immutable snapshot

**Nguyên nhân:** một số cache lưu object reference; caller có thể sửa object, hoặc writer thay đổi entry ngay sau phép get.

**Cách sửa:** với dữ liệu cần ổn định, dùng immutable records/DTO, defensive copy nếu phù hợp, version và giao thức đồng bộ. **Typed get chỉ kiểm tra kiểu tại thời điểm lấy value**, không cam kết snapshot isolation.

## 10. Những giới hạn nâng cao cần nhớ

### 10.1. Wrapper không tạo transaction trên hai thao tác

Đoạn:

~~~java
Cache.ValueWrapper w = cache.get(key);
if (w == null) {
    cache.put(key, load());
}
~~~

có **cửa sổ giữa get và put**: hai thread cùng miss có thể cùng load. Nếu cache operation phải điều phối loader, cân nhắc `get(key, Callable)` và test trên provider cụ thể. Nếu read/write khác cũng cập nhật nguồn/cache đồng thời, vẫn phải thiết kế thêm cơ chế nhất quán/version; một cache loader được phối hợp không thay thế transaction.

### 10.2. ValueWrapper không tương đương `Optional<T>`

`Optional<T>` biểu diễn có/không có giá trị, nhưng không mang ba trạng thái **miss / cached-null / cached-value** theo cách ValueWrapper làm. `Optional.empty()` không đủ để nói entry chưa từng tồn tại, trừ khi bạn áp một quy ước nghiệp vụ rõ ràng.

### 10.3. Null caching cần ranh giới nghiệp vụ

Cache null có thể phù hợp với kết quả **not found** tương đối ổn định, nhưng có thể không phù hợp nếu:
- Bản ghi mới được tạo ngay sau lần miss ban đầu.
- Việc không thấy bản ghi là trạng thái tạm thời do lỗi mạng.
- Dữ liệu liên quan phân quyền hoặc trạng thái người dùng thay đổi nhanh.
- Provider có TTL dài khiến negative cache tồn tại lâu.

Khi cache negative result, nên đặt TTL/invalidation hợp lý; `ValueWrapper` không cung cấp TTL riêng, và `Cache.get` không cho biết entry được tạo lúc nào.

### 10.4. API async `retrieve` là một cơ chế khác

Spring Framework 6.1+ có các API như `retrieve(key)` sử dụng `CompletableFuture` khi cache implementation hỗ trợ. Hợp đồng của asynchronous retrieval phải biểu diễn **miss sớm, miss muộn và nullable cached value**; có thể có `ValueWrapper` bên trong kết quả future tùy trường hợp. **Không áp dụng máy móc quy tắc get(key, Class<T>) cho retrieve**.

Bài này tập trung các overload `get` đồng bộ. Khi cần lập trình async, hãy đọc riêng hợp đồng `retrieve` và kiểm tra support/exception behavior của provider.

### 10.5. CacheManager có thể không tìm thấy cacheName

~~~java
Cache cache = cacheManager.getCache("not-configured");
~~~

Theo interface `CacheManager`, kết quả có thể null nếu manager không resolve cache. Nếu code gọi `cache.get(...)` sau đó, đó là **NullPointerException do cache reference null**, khác với **ValueWrapper null do key miss**. Hai tầng null phải được xử lý riêng.

Ví dụ:

~~~java
Cache cache = Objects.requireNonNull(
    cacheManager.getCache("users"),
    "Cache 'users' is not configured");

Cache.ValueWrapper wrapper = cache.get("u1");
~~~

Đây là minh họa; `Objects` thuộc java.util. Kể cả khi cache object tồn tại, một provider phân tán vẫn có thể gặp timeout, lỗi mạng hoặc serialization khi thực thi get. Wrapper không có chức năng hấp thụ mọi lỗi.

## 11. Kiểm thử có chủ đích

Để kiểm thử contract giữa ứng dụng và provider, nên có các test case sau:

| Test | Setup | Kết quả cần kiểm tra |
| --- | --- | --- |
| **MISS** | Key chưa ghi | `get(key) == null`; `get(key, User.class) == null` |
| **HIT–VALUE** | `put(key, User)` | Wrapper khác null, value đúng; typed get trả User |
| **HIT–NULL** | `put(key, null)`, provider cho phép | Wrapper khác null, `wrapper.get()==null`; typed get trả null |
| **TYPE MISMATCH** | Value User, get String.class | `IllegalStateException` |
| **LOADER MISS** | Key trống, Callable đếm calls | Giá trị được tạo/lưu, loader chạy một lần trong chuỗi tuần tự |
| **LOADER HIT** | Key đã có value | Callable không chạy |
| **LOADER HIT–NULL** | Key lưu null hợp lệ | Callable không chạy trong provider hỗ trợ |
| **LOADER ERROR** | Callable ném checked exception | Exception được bọc theo Cache.ValueRetrievalException |
| **EVICT** | Xóa key đã tồn tại | `get(key)` chuyển sang null wrapper/miss |
| **GENERIC COLLECTION** | `List<String>`, đọc List.class | Runtime nhận diện List chứ không kiểm tra element type |
| **CONCURRENT MISS** | Hai thread cùng get-loader một key | Ghi nhận số loader calls theo guarantee provider |
| **CROSS-PROVIDER** | Lặp test với Redis/Caffeine/... | Xác minh null, type, serialization và errors thực tế |

Hãy viết integration test dùng cache manager thực tế của ứng dụng. **Không chỉ mock `Cache.get` trả null**, vì mock ấy không mô phỏng được điểm khác nhau quan trọng nhất giữa miss và cached-null.

## 12. Câu hỏi tự kiểm tra

**Câu 1:** `cache.get("x")` trả null. Có nghĩa cache có entry chứa null không?

**Không.** Overload một tham số trả Java null nghĩa là **không có mapping** cho key. Entry cached-null được biểu diễn bằng **ValueWrapper khác null**, với `get()` bên trong trả null.

**Câu 2:** `cache.get("x", User.class)` trả null. Kết luận được miss không?

**Không.** Typed get trả null trong **cả hai** trường hợp miss và cached-null.

**Câu 3:** Cache chứa User, nhưng ta gọi `cache.get("x", String.class)`. Điều gì xảy ra?

**IllegalStateException** khi non-null value không thuộc kiểu được yêu cầu. Đây là lỗi về hợp đồng type, không phải một cache miss.

**Câu 4:** `Cache.ValueWrapper` có phải `ValueWrapper<User>` không?

**Không.** Nó là interface lồng của Cache, trả payload kiểu Object; caller phải kiểm tra/cast hoặc dùng typed get khi thích hợp.

**Câu 5:** `get("x", List.class)` có đảm bảo mọi element là User không?

**Không.** Chỉ kiểm tra runtime raw type List; generic element type không được biểu diễn bởi Class<List>.

**Câu 6:** Muốn loader chạy khi cache miss thì dùng overload nào?

**get(key, Callable<T>)**, không phải `get(key, User.class)`.

**Câu 7:** Đã lưu cached-null, sau đó gọi `get(key, Callable)`. Loader bắt buộc chạy không?

**Không.** Với provider hỗ trợ cached-null như ConcurrentMapCache trong demo, key đã có mapping, nên loader **không chạy**.

**Câu 8:** ValueLoader ném IOException. Lỗi thường được API biểu diễn thế nào?

Qua **Cache.ValueRetrievalException** bao IOException. Khi xử lý, kiểm tra `getCause()` để phân loại nguồn lỗi.

**Câu 9:** `CacheManager.getCache("missing") == null` và `Cache.get("missingKey") == null` có cùng ý nghĩa không?

**Không.** Cái thứ nhất là **không lấy được đối tượng cache theo tên**; cái thứ hai là **cache đã tồn tại nhưng key không có mapping**.

## Tóm tắt

- **`Cache.get(key)`** trả **`Cache.ValueWrapper`** nếu key có mapping. Wrapper có thể chứa payload null; Java null từ chính method là **MISS**.
- **`Cache.get(key, Class<T>)`** trả trực tiếp value đúng runtime type hoặc null. **Không phân biệt cached-null với miss**, và ném **IllegalStateException** nếu non-null value sai type.
- **`Cache.get(key, Callable<T>)`** là loader overload, có thể gọi loader khi miss; lỗi trong loader được bọc bởi **Cache.ValueRetrievalException**. Khả năng phối hợp concurrent loads tùy provider.
- **ConcurrentMapCacheManager mặc định cho phép cached-null** bằng sentinel nội bộ; khả năng này không phải bảo đảm chung cho mọi provider.
- Khi cần phân biệt **entry tồn tại** và **giá trị nội dung**, dùng **ValueWrapper**; khi chỉ cần value đúng kiểu, dùng **typed get**; khi cần load-on-miss, dùng **Callable**.
- Dù chọn overload nào, cần giữ cacheName/key thống nhất, kiểm tra type contract, null policy và tính nhất quán khi có concurrent writers.

### Tài liệu tham khảo chính thức

- Spring Framework – Cache API (ba overload get, ValueWrapper và retrieve): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework – Cache.ValueWrapper: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/Cache.ValueWrapper.html
- Spring Framework – Cache.ValueRetrievalException: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/Cache.ValueRetrievalException.html
- Spring Framework – ConcurrentMapCacheManager null-value policy: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework – Annotation-based caching: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html

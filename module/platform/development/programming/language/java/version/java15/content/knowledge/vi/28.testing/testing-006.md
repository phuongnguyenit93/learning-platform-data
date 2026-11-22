# Vòng đời lớp, cache và tham chiếu giữ tài nguyên trong kiểm thử Java

Bài này thuộc chủ đề **Kiểm thử**. Mục tiêu là nhận ra vì sao một test đã kết thúc nhưng dữ liệu, class, class loader, thread hoặc tài nguyên vẫn có thể tồn tại; tìm đúng **đường tham chiếu còn sống** và thiết kế cleanup có thể kiểm chứng. Các kỹ thuật áp dụng cho Java hiện đại (ví dụ Java 17+; khái niệm JVM nền tảng cũng phù hợp khi bảo trì dự án Java 15). Trọng tâm là API hiện hành, đặc biệt JUnit Jupiter, `AutoCloseable`, `ThreadLocal`, `ClassValue`, các dạng reference và công cụ chẩn đoán JVM.

## 1. Phân biệt vòng đời class, object, test và tài nguyên

Một đối tượng Java, một lớp đã nạp, một đối tượng test và một tài nguyên hệ điều hành **không có chung thời điểm kết thúc**:

| Đối tượng cần quản lý | Khi được tạo | Khi nào có thể giải phóng? | Điều dễ nhầm |
| --- | --- | --- | --- |
| Object trên heap | `new`/factory/deserialization | Khi không còn đường tham chiếu giữ nó từ GC roots | Biến local ra khỏi scope chưa chứng minh object đã được thu gom |
| `Class<?>` và định nghĩa class | JVM nạp class qua *defining class loader* | Class có thể unload khi defining loader có thể được thu gom và JVM quyết định unload | Test kết thúc không tự unload class |
| Trạng thái `static` | Trong khởi tạo class và khi code cập nhật | Thông thường tồn tại cùng class/loader; có thể reset explicit | Tạo test instance mới không reset `static` |
| JUnit test instance | Mặc định tạo cho mỗi test method | Sau test và khi framework không còn giữ nó | `@TestInstance(PER_CLASS)` chia sẻ instance lâu hơn |
| Cache | Khi put/compute/load | Theo chính sách size, TTL, explicit invalidation hay lifetime owner | Cache không giới hạn có thể trở thành leak |
| `ThreadLocal` value | Khi gọi `set` trên một thread | Khi `remove` hoặc khi thread kết thúc (nếu không còn đường giữ khác) | Worker thread của pool sống qua nhiều test/task |
| Stream, socket, file, executor, listener | Khi mở/đăng ký/khởi chạy | Khi `close`/`shutdown`/`unregister` tương ứng được thực hiện và resource thực sự giải phóng | GC không thay thế cleanup đúng hợp đồng API |

**Rò rỉ tài nguyên** không nhất thiết chỉ là `OutOfMemoryError`: một connection, descriptor, pool thread, listener hoặc object lớn có thể vẫn bị giữ quá thời gian dự kiến dù ứng dụng vẫn chạy. Ngược lại, cache đang giữ dữ liệu **có chủ đích và có giới hạn** chưa chắc là leak. Muốn kết luận phải biết chính sách ownership, lifetime mong đợi và đường tham chiếu.

## 2. Vòng đời class: load → link → initialize → sử dụng → có thể unload

### 2.1. Ba bước đầu của class

Theo Java Language Specification, JVM:

1. **Loading:** tìm bytecode theo tên nhị phân và loader, tạo biểu diễn runtime. Cùng tên `com.example.Foo` do **hai defining class loader khác nhau** có thể là hai kiểu khác nhau.
2. **Linking:** verify bytecode; prepare các field `static` với giá trị mặc định; resolve các symbolic references lúc thích hợp.
3. **Initialization:** chạy các static field initializers và khối `static { ... }` theo quy tắc của JVM (thường tại *active use*: tạo instance, gọi static method, đọc/ghi static field không phải compile-time constant). Initialization cho một class diễn ra tối đa một lần **mỗi định nghĩa class trong một class loader** khi thành công.

`Class.forName(name, false, loader)` có thể tải class mà **chưa yêu cầu initialize**. `ClassLoader#loadClass` cũng không phải lời hứa chạy initializer. Cần phân biệt **class loaded** và **class initialized** khi debug test, plugin hoặc lỗi `ExceptionInInitializerError`.

Ví dụ độc lập, file `LifecycleDemo.java`:

~~~java
class ConfigHolder {
    static final int VALUE = initialize();

    private static int initialize() {
        System.out.println("initialized");
        return 7;
    }
}

public class LifecycleDemo {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName(
                "ConfigHolder",
                false,
                LifecycleDemo.class.getClassLoader()
        );
        System.out.println(type.getSimpleName());
        System.out.println(ConfigHolder.VALUE);
        System.out.println(ConfigHolder.VALUE);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 LifecycleDemo.java
java LifecycleDemo
~~~

Stdout chính xác:

~~~text
ConfigHolder
initialized
7
7
~~~

`VALUE` **không phải compile-time constant** vì được trả về từ method; lần đọc đầu kích hoạt initialization. Lần đọc tiếp theo không chạy lại initializer. Nếu `static final int VALUE = 7;` là *constant variable*, compiler có thể inline giá trị và **việc đọc không nhất thiết initialize class**.

### 2.2. Class unloading và vai trò class loader

Một định nghĩa class có thể được unload khi defining class loader của nó **có thể bị GC thu gom**; JVM không cam kết thời điểm thu gom hay class unloading. Một class loader còn reachable thường kéo theo các class nó định nghĩa và phần metadata liên quan. Trên HotSpot, metadata lớp thường gắn với **metaspace**; object Java (bao gồm key/value của cache) ở heap.

Ví dụ **đường giữ class loader từ bên ngoài**:

~~~text
GC root
  └── singleton/registry được nạp bởi class loader sống lâu
        └── Map<Class<?>, Metadata>
              └── key: Class<?> từ plugin được nạp bởi PluginLoader
                    └── defining PluginLoader
                          └── metadata/classes của plugin
~~~

Những nguồn khác có thể kéo dài lifetime của loader: listener không unregister, thread plugin tự tạo chưa dừng, `Thread.contextClassLoader` của thread sống lâu, reference tới `Method`/`Constructor`/`Class<?>`, timer/callback, MBean hoặc cache dùng key kiểu class.

**Lưu ý về chu trình tham chiếu:** `PluginLoader → class plugin → static cache → object plugin` có thể là một *cycle* tự chứa. Nếu không có **GC root bên ngoài** đi tới cycle đó thì GC vẫn có thể thu gom nó. Không kết luận leak chỉ vì thấy object tham chiếu qua lại; phải tìm đường giữ từ GC roots.

### 2.3. Đóng class loader không đồng nghĩa unload class

`URLClassLoader` implement `Closeable`; `close()` giải phóng các resource do loader sở hữu (ví dụ JAR/file handle) theo hợp đồng. Nó **không** ép JVM unload class, không xóa mọi reference tới các instance/plugin và không tự dừng thread của plugin.

Đoạn minh họa **cần JAR plugin thật**, không phải chương trình độc lập:

~~~java
try (var loader = new java.net.URLClassLoader(
        new java.net.URL[] { pluginJar.toUri().toURL() },
        ClassLoader.getPlatformClassLoader())) {
    Class<?> pluginType = Class.forName("demo.Plugin", true, loader);
    // Tạo và sử dụng plugin tại đây.
    // Trước khi kết thúc scope: unregister listener, đóng resource,
    // dừng thread/executor và bỏ references trong registry.
}
// Loader đã được close; class unloading, nếu xảy ra, vẫn do JVM quyết định.
~~~

Trong ứng dụng chạy nhiều lần redeploy/hot reload/test động, nên có **owner rõ ràng** cho loader và toàn bộ các object gắn với loader. Kiểm thử cả mở/đóng nhiều vòng, không chỉ một lần.

## 3. Reachability: vì sao object vẫn sống?

### 3.1. GC root và tham chiếu mạnh

Các **GC roots** có thể gồm stack/locals đang hoạt động, thread, static state của class còn sống và các tham chiếu được JVM giữ. Một object còn **strongly reachable** từ root thì GC không được thu gom nó, dù code nghiệp vụ không dùng nữa.

~~~text
Root (worker thread)
  └── ThreadLocalMap
        └── value: RequestContext
              └── largePayload (20 MiB)
~~~

Trong sơ đồ, vấn đề là **worker thread sống lâu** và value chưa được remove; payload tiếp tục sống qua nhiều request/test. Không thể sửa bằng `largePayload = null` ở một biến local khác.

### 3.2. Các loại reference

| Cơ chế | Có giữ referent sống không? | Khi dùng | Bẫy khi kiểm thử |
| --- | --- | --- | --- |
| **Strong reference**: field, list, map, local | Có, nếu đường dẫn tới root tồn tại | Ownership và cache được giới hạn | Map/static field không clear |
| **`WeakReference<T>`** | Không ngăn GC thu gom referent khi chỉ còn weakly reachable | Metadata tạm, canonicalization, quan sát khả năng thu gom | `get()` có thể bất ngờ trả `null`; không phù hợp dữ liệu bắt buộc tồn tại |
| **`SoftReference<T>`** | Có cơ chế GC dọn dưới áp lực bộ nhớ, thời điểm không ổn định | Trường hợp cache phụ thuộc chính sách GC rất đặc thù | Không đặt SLA/dung lượng cache dựa vào soft reference |
| **`PhantomReference<T>` + `ReferenceQueue`** | `get()` không trả referent | Theo dõi việc referent đã tới trạng thái xử lý sau GC; các cấu trúc cleanup nâng cao | Không phải thay thế `close()` cho resource cần release kịp thời |
| **`Cleaner`** | Đăng ký cleanup hậu kỳ theo reachability | Safety net cho một số resource có native state | Cleanup bất định, không dựa vào nó để assert thời gian đóng |

Ví dụ dùng `WeakReference`:

~~~java
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    public static void main(String[] args) {
        Object payload = new Object();
        WeakReference<Object> weak = new WeakReference<>(payload);
        System.out.println(weak.get() == payload);
        payload = null;

        // Từ đây có thể được GC thu gom nếu không còn strong reference.
        // Không assert weak.get() == null hoặc dự đoán thời điểm GC.
    }
}
~~~

Chạy `javac --release 17 WeakReferenceDemo.java` rồi `java WeakReferenceDemo`, stdout là `true`. Dòng `payload = null` chỉ bỏ **một** reference; kết luận GC tùy các reference còn lại và thời điểm JVM thu gom. Không viết test dạng `System.gc(); assertNull(weak.get());`: `System.gc()` chỉ là yêu cầu, không bảo đảm reclamation hay scheduling.

**`ReferenceQueue`** báo khi reference đã được GC xử lý; bản thân reference đăng ký phải còn được giữ nếu muốn nhận thông báo. Với resource như socket/stream, thiết kế API `AutoCloseable` và cleanup tường minh đáng tin hơn.

## 4. Cache: phân biệt tối ưu hợp lệ và giữ dữ liệu quá lâu

### 4.1. Các kiểu cache dễ gây giữ tài nguyên

- **Static map không giới hạn:** `static final Map<Key, Value> CACHE` có thể tăng mãi trong lifetime của class loader.
- **Cache theo class/reflection:** key `Class<?>`, value `Method`, `Constructor`, `MethodHandle` hoặc metadata tham chiếu tới plugin class; cache global có thể giữ class loader con.
- **Cache theo request/tenant/test:** key từ dữ liệu thay đổi không có expiry, eviction hoặc phân vùng phù hợp.
- **Cache chứa resource phải đóng:** cache giữ `Connection`, stream, client, executor, session; evict object chưa chắc đã release resource.
- **Cache giữ object mutable dùng chung:** test bất ổn do thứ tự chạy, hoặc request sau nhìn thấy state request trước; đó là vấn đề **isolation**, kể cả khi dung lượng không tăng.

Chỉ định rõ **owner**, key cardinality, max size, TTL/expire policy, invalidation, concurrency và cleanup khi ứng dụng dừng. Dùng cache library hiện hành như **Caffeine** khi cần eviction/metrics/concurrency; chọn `maximumSize`, `expireAfterWrite`/`expireAfterAccess` và chính sách cleanup phù hợp workload. TTL một mình không bảo đảm bộ nhớ không vượt mức nếu có quá nhiều key mới trong cửa sổ TTL.

### 4.2. `WeakHashMap` không tự giải quyết mọi class-loader leak

`WeakHashMap<K,V>` giữ **key yếu**, nhưng thường giữ **value mạnh**. Nếu value trực tiếp/gián tiếp tham chiếu lại key, chuỗi `map → value → key` có thể giữ key sống dù key của entry là weak:

~~~java
// Ví dụ gây rủi ro: Class<?> có thể đến từ loader ngắn hạn.
Map<Class<?>, Handler> registry = new java.util.WeakHashMap<>();
// Handler có field Class<?> declaringType trỏ về chính key.
// registry --> Handler --> Class<?> --> defining loader.
~~~

Đây là mã **minh họa cấu trúc**; `Handler` không được định nghĩa nên không chạy độc lập. Thay thế có thể là owner-scoped cache, explicit invalidate, hoặc `ClassValue` khi giá trị thực sự được gắn với class.

### 4.3. `ClassValue<T>` cho dữ liệu theo từng class

`ClassValue<T>` thuộc JDK, hỗ trợ gắn value tính lười với `Class<?>` mà không tự tạo một `ConcurrentHashMap<Class<?>, T>` toàn cục. `computeValue` có thể chạy nhiều lần khi có cạnh tranh; code không nên dựa vào việc chỉ gọi đúng một lần. `remove(type)` hủy association để lần `get(type)` kế tiếp tính lại.

Ví dụ độc lập, file `ClassValueDemo.java`:

~~~java
public class ClassValueDemo {
    private static final ClassValue<String> NAMES = new ClassValue<>() {
        @Override
        protected String computeValue(Class<?> type) {
            return type.getName();
        }
    };

    public static void main(String[] args) {
        System.out.println(NAMES.get(String.class));
        NAMES.remove(String.class);
        System.out.println(NAMES.get(String.class));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ClassValueDemo.java
java ClassValueDemo
~~~

Stdout:

~~~text
java.lang.String
java.lang.String
~~~

`ClassValue` hợp cho cache metadata **theo class**; không phải giải pháp thay thế cho cache không giới hạn theo request ID, và không tự đóng các resource nằm trong value. Nếu value chứa resource có lifetime cụ thể, phải thiết kế owner/close riêng.

### 4.4. Bảo đảm cache thread-safe

`HashMap` không an toàn khi nhiều thread cùng thay đổi. `ConcurrentHashMap.computeIfAbsent` thường thích hợp để tạo metadata dùng chung nhưng mapping function cần ngắn, tránh side effect và recursion cập nhật cùng map. Khi cache có chi phí tải lớn, cần kiểm tra failure behavior, cache stampede, khả năng invalidate và điều kiện loại bỏ. Trong test, tránh phụ thuộc vào **thứ tự** hoặc **time-based expiry tuyệt đối**; dùng clock/fake time do hệ thống cung cấp thay vì `Thread.sleep` dài và assertion nhạy lịch.

## 5. ThreadLocal và thread pool: sự cố thường xuất hiện trong test

`ThreadLocal<T>` lưu value **theo từng thread**, không theo request và không theo test. Executor có thể tái sử dụng worker thread sau khi test kết thúc. Nếu không `remove()` trong `finally`, giá trị còn lại có thể rò state hoặc giữ object lớn/classloader.

Ví dụ độc lập, file `ThreadLocalDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThreadLocalDemo {
    private static final ThreadLocal<String> USER = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            String first = pool.submit(() -> {
                USER.set("alice");
                try {
                    return USER.get();
                } finally {
                    USER.remove(); // Bắt buộc kể cả khi logic ném exception.
                }
            }).get();

            boolean clean = pool.submit(() -> USER.get() == null).get();
            System.out.println(first);
            System.out.println(clean);
        } finally {
            pool.shutdown();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ThreadLocalDemo.java
java ThreadLocalDemo
~~~

Stdout:

~~~text
alice
true
~~~

Nếu bỏ `USER.remove()`, task thứ hai chạy trên cùng thread thường nhìn thấy `"alice"` và kết quả `clean` là `false`. `ThreadLocal` cũng không tự truyền context đúng khi chuyển qua thread khác; nếu cần context propagation phải sử dụng cơ chế có chủ đích của framework, không tự cho rằng thread pool giữ scope request.

**Quy tắc:** ai `set` thì người đó chịu trách nhiệm `remove`, ưu tiên `try/finally` bên trong task được thực thi. Trong ứng dụng web, kiểm tra filter/interceptor và các task async có cleanup cho cả đường thành công, lỗi, timeout và hủy.

## 6. JUnit Jupiter: test instance mới vẫn có thể thấy cache cũ

### 6.1. Vòng đời trong JUnit 6

**JUnit Jupiter** (JUnit 6 và JUnit 5 đều dùng API này) có mặc định `@TestInstance(PER_METHOD)`: tạo một instance của test class cho mỗi test method. `@BeforeEach`/`@AfterEach` bao quanh từng method; `@BeforeAll`/`@AfterAll` áp dụng cho cả class. Với `@TestInstance(PER_CLASS)`, các test method dùng chung test instance, phù hợp một số fixture nhưng **state mutable phải reset** nếu muốn độc lập.

Điểm rất quan trọng: dù dùng `PER_METHOD`, JVM thường chỉ initialize class ứng dụng một lần trong cùng class loader. Vì vậy field `static`, singleton, cache của framework, system property, thread pool, registry... vẫn có thể tồn tại sau mỗi test. `@AfterEach` dọn test object chưa đủ nếu resource được đăng ký vào singleton khác.

### 6.2. Ví dụ integration với test isolation

Giả sử project Gradle Java có các file sau. Ví dụ dùng **JUnit Jupiter 6.1.3** (Java 17+), chạy trên Gradle có hỗ trợ JUnit Platform.

`build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:6.1.3')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

test {
    useJUnitPlatform()
}
~~~

`src/main/java/demo/CacheStore.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class CacheStore {
    private static final Map<String, byte[]> DATA = new ConcurrentHashMap<>();

    private CacheStore() {}

    public static void put(String key, byte[] data) {
        DATA.put(key, data);
    }

    public static int size() {
        return DATA.size();
    }

    public static void clear() {
        DATA.clear();
    }
}
~~~

`src/test/java/demo/CacheStoreTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CacheStoreTest {
    @BeforeEach
    void resetBefore() {
        CacheStore.clear();
    }

    @AfterEach
    void resetAfter() {
        CacheStore.clear();
    }

    @Test
    void newTestStartsWithEmptyCache() {
        assertEquals(0, CacheStore.size());
    }

    @Test
    void storedDataIsVisibleWithinOneTest() {
        CacheStore.put("sample", new byte[1024]);
        assertEquals(1, CacheStore.size());
    }
}
~~~

Chạy `./gradlew clean test` (Windows: `gradlew.bat clean test`). Với cấu hình này, **hai test phải PASS bất kể thứ tự thực thi tuần tự**. Không dự đoán chính xác stdout/console của Gradle vì phụ thuộc phiên bản và môi trường.

Giải thích:
- `clear()` làm test độc lập với dữ liệu của test trước. `@AfterEach` cố gắng dọn cả khi test body ném exception.
- `@BeforeEach` bảo đảm tiền điều kiện sạch, nhưng không thay thế cleanup sau test cho các tài nguyên như connection, listener hay thread.
- Đây là **global mutable cache**: nếu test chạy **song song** hoặc các test class khác truy cập cùng cache, việc clear vẫn có thể race. Khi đó ưu tiên **cache instance được inject vào system under test**, mỗi test có instance riêng; nếu không thể, dùng cơ chế đồng bộ/`@ResourceLock` hoặc giới hạn parallel execution một cách có lý do.
- Khi test framework giữ application context (ví dụ Spring test context cache), test instance khác **không có nghĩa context được tạo lại**. Reset state thuộc scope context hoặc dùng isolation phù hợp từng framework.

### 6.3. Ví dụ tốt hơn: cache có owner cụ thể

~~~java
package demo;

import java.util.HashMap;
import java.util.Map;

public final class LocalCache implements AutoCloseable {
    private final Map<String, String> values = new HashMap<>();
    private boolean closed;

    public void put(String key, String value) {
        if (closed) throw new IllegalStateException("cache closed");
        values.put(key, value);
    }

    public String get(String key) {
        if (closed) throw new IllegalStateException("cache closed");
        return values.get(key);
    }

    @Override
    public void close() {
        values.clear();
        closed = true;
    }
}
~~~

Trong test/production, dùng:

~~~java
try (var cache = new LocalCache()) {
    cache.put("a", "ok");
    // assertEquals("ok", cache.get("a")) trong JUnit.
}
~~~

Phần đầu là class Java độc lập; đoạn `try` là minh họa cách sử dụng trong một method, không phải chương trình riêng để chạy. Cache kiểu instance cho phép test tạo owner mới và đóng khi hết scope. Đây chỉ là cache học tập không thread-safe; nếu dùng đa luồng, cần cấu trúc và chính sách phù hợp.

### 6.4. Fixture có tài nguyên thật

Dùng `try-with-resources` khi resource có phạm vi một method; khi resource sống suốt test class, mở bằng `@BeforeAll` và đóng bằng `@AfterAll` (hoặc JUnit extension với cleanup tương ứng). Với `ExecutorService` trên Java 17, dùng `shutdown()` và chờ kết thúc có giới hạn; **`ExecutorService` chỉ có hợp đồng `AutoCloseable` từ các JDK mới hơn**, nên không sao chép `try (ExecutorService ...)` vào dự án Java 17. Luôn dừng các task và thread trước khi thả các reference còn lại.

Các thứ cần dọn tùy fixture: temp file/dir, filesystem watcher, socket/server, database transaction/connection, application context riêng, môi trường giả lập, listener/event subscription, scheduled task, system property đã thay đổi. Nếu test sửa system property hoặc default locale/time zone, phải lưu trạng thái cũ và khôi phục trong `finally`/cleanup, đồng thời cẩn trọng với test parallel.

## 7. Kiểm thử classloader leak và GC: kiểm thử điều kiểm soát được

### 7.1. Tình huống plugin/test classloader

Giả sử test tải plugin trong class loader riêng nhiều lần. Một vòng lifecycle hợp lý:

1. Tạo loader và khởi động plugin.
2. Đăng ký callback/listener cần thiết; dùng resource như dự kiến.
3. Dừng scheduler/executor, unregister callback, trả connection về pool và đóng resource.
4. Loại bỏ registry entry, context-class-loader reference và local reference theo ownership.
5. `close()` loader nếu loader có resource cần close.
6. Quan sát số lượng loader/class và heap/metaspace qua nhiều vòng lặp, sau giai đoạn warmup và các cơ hội GC tự nhiên.

**Không yêu cầu** plugin class loader phải biến mất *ngay trong assert tiếp theo*. Java spec không bắt buộc GC hoặc class unloading trong một thời hạn. Dùng weak reference/reference queue như **tín hiệu phụ trợ** trong stress test có điều kiện, nhưng đừng biến `System.gc()` + `assertNull(weak.get())` thành test bắt buộc.

### 7.2. Thử nghiệm logic giữ reference bằng registry

Đoạn sau **minh họa** một nguồn retention rõ ràng:

~~~java
final class PluginRegistry {
    private static final java.util.List<Class<?>> REGISTERED =
            new java.util.concurrent.CopyOnWriteArrayList<>();

    static void register(Class<?> type) {
        REGISTERED.add(type);
    }

    static void unregister(Class<?> type) {
        REGISTERED.remove(type);
    }

    static int size() {
        return REGISTERED.size();
    }
}
~~~

Nếu `PluginRegistry` do class loader sống lâu nạp, việc `register(pluginType)` tạo strong reference từ static list tới `Class<?>` của plugin. Test nên kiểm tra **unregister đúng và `size()` trở về baseline** sau khi đóng plugin (nếu registry chỉ do fixture này kiểm soát); điều đó kiểm chứng contract cleanup **một cách quyết định**. Muốn chứng minh loader thực sự có thể được unload, vẫn phải kiểm tra thêm các GC roots khác và dùng công cụ JVM.

**Không dùng** `WeakReference` để che lỗi quên unregister: nếu một event bus lưu listener, phải unsubscribe trên lifecycle phù hợp; chỉ đổi loại reference có thể gây mất event khó đoán.

## 8. Từ triệu chứng đến bằng chứng: phân tích heap, metaspace và GC roots

### 8.1. Phân biệt loại tăng bộ nhớ

| Dấu hiệu | Nghi ngờ | Kiểm tra tiếp |
| --- | --- | --- |
| Heap tăng theo số test/request, không về baseline sau các chu kỳ GC | Cache unbounded, static registry, queue, listener, session | Histogram theo thời điểm, heap dump, dominator tree, paths to GC roots |
| Class count/metaspace tăng qua nhiều lần reload | Classloader bị giữ bởi global cache, thread context loader, callback | Loader stats, metaspace, class-loading logs, heap path tới loader |
| Thread count tăng không giảm | Executor/scheduler/timer không shutdown | Thread dump, tìm owner và shutdown path |
| File descriptors/socket tăng | Stream/client/WatchService/loader không close | OS metrics, resource owners, try-with-resources |
| Test chỉ fail khi chạy cả suite, chạy một mình PASS | Shared static state, order dependency, thread-local, test context | Randomize order, cô lập test, bật/tắt parallel, xác minh before/after cleanup |
| OOM chỉ khi áp lực lớn, cache hit rate bất ổn | Cache size/TTL thiếu giới hạn, soft references không dự đoán được | Chốt max size, đo hit/miss/eviction/retained size |

### 8.2. Lệnh chẩn đoán HotSpot/JDK hiện đại

Chạy trên JVM thử nghiệm được phép quan sát, thay `<pid>` bằng PID thật; `jcmd` phải có quyền tương thích với tiến trình:

~~~bash
jcmd
jcmd <pid> help
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
jcmd <pid> Thread.print
jcmd <pid> GC.heap_dump /safe/path/heap.hprof
~~~

`VM.classloader_stats` cho thấy số/nhóm loader và class; `VM.metaspace` cho metadata memory; histogram nhóm các object heap; thread dump giúp tìm thread sống lâu. Heap dump có thể làm ứng dụng tạm dừng, tạo file lớn và chứa dữ liệu nhạy cảm — chỉ thu trong môi trường/đường dẫn được quản lý. Tên diagnostic command tùy JVM/JDK; kiểm tra `jcmd <pid> help` trước.

Khi chủ động chạy Java để quan sát load/unload của HotSpot có thể bật:

~~~bash
java -Xlog:class+load=info,class+unload=info -cp app.jar com.example.Main
~~~

Đây là **mẫu cú pháp**; classpath/main class phải thay bằng ứng dụng có thật. Không thấy log `class+unload` trong khoảng ngắn **không chứng minh** leak, vì class unloading phụ thuộc GC và khả năng thu gom loader.

Java Flight Recorder (JFR) có thể thu sự kiện allocations, class loading và GC tùy profile/setting; dùng Java Mission Control để xem xu hướng. Heap dump mở bằng Eclipse Memory Analyzer (MAT) hoặc profiler tương đương: tìm **retained heap**, **dominator tree** và **path to GC roots** của object/loader bị giữ. Chỉ histogram một thời điểm không nói được ai giữ đối tượng.

### 8.3. Cách thiết kế phép thử hồi quy đáng tin

Tránh khẳng định leak chỉ từ một giá trị memory sau một lần chạy. Thay vào đó:

- **Baseline** sau warmup; chạy N vòng tạo/sử dụng/đóng tài nguyên; đo các số đếm owner biết chắc (số listener đăng ký, cache entries, tasks còn active, connections mượn).
- **Assertion trực tiếp:** sau `close`, registry/owner state phải về baseline, executor không nhận task mới, file/socket được đóng theo API, ThreadLocal được remove.
- **Stress test riêng:** đo heap/metaspace/classloader trend khi lặp lại và GC có cơ hội chạy; giữ sự khác biệt giữa *growth tạm thời*, cache được giới hạn và leak thật.
- **So sánh before/after:** phân tích retained object và GC root của loader, không chỉ đo `Runtime.freeMemory()` bởi số liệu đó chịu ảnh hưởng kích thước heap và chính sách GC.
- **Chạy nhiều môi trường:** JDK thấp nhất được hỗ trợ, JDK đang nâng cấp, test suite đầy đủ và cấu hình parallel mà CI thật dùng.

## 9. Những lỗi phổ biến và cách sửa

| Lỗi | Vì sao xảy ra | Hướng sửa |
| --- | --- | --- |
| Nghĩ `@BeforeEach` tạo lại static cache | Test instance mới nhưng class vẫn ở cùng loader | Inject cache instance, clear/invalidate có owner rõ ràng |
| Nghĩ `@TestInstance(PER_METHOD)` cách ly mọi trạng thái | Singleton, context, system property, threads vẫn chia sẻ | Test isolation theo đúng phạm vi resource |
| Cho rằng `URLClassLoader.close()` là unload | Close resource của loader không ép GC | Bỏ external roots, unregister, dừng threads rồi theo dõi loader |
| Dùng `WeakHashMap` nhưng value giữ ngược key | Key weak vẫn reachable qua value strong | Giải quyết graph, dùng `ClassValue` hoặc owner-scoped cache |
| Quên `ThreadLocal.remove()` trong pool | Worker sống lâu và giữ value | `try/finally` ngay trong task, reset context đầy đủ |
| Cache chỉ có TTL, không có max size | Nhiều key mới trong cùng TTL vẫn làm heap tăng | Cấu hình size/weight budget và giám sát eviction |
| Test dự đoán thời điểm GC | JVM không hứa khi nào chạy GC/unload | Assert cleanup contract, phân tích trend/dump khi cần |
| Đợi GC đóng socket/file | Cleanup qua GC không có deadline | `AutoCloseable`/`close`/`shutdown` tường minh |
| Dùng static global registry cho plugin tạm | Registry ở loader sống lâu giữ class/plugin | Token registration + unregister trong close |
| Dùng finalization như đường cleanup chính | Cleanup bất định, API không phù hợp Java mới | Try-with-resources, owner lifecycle; Cleaner chỉ là safety net |

## 10. Bài tập áp dụng

1. Chạy `LifecycleDemo`, đổi `Class.forName(..., false, ...)` thành `Class.forName("ConfigHolder")` và ghi lại khác biệt về thứ tự output. Giải thích vì sao *initialization* xảy ra trước dòng in tên class khi dùng overload mặc định.
2. Chạy `ThreadLocalDemo`, bỏ `USER.remove()` trong `finally` và so sánh output. Đưa `remove()` trở lại, kiểm tra cả đường exception trong task.
3. Chạy hai test `CacheStoreTest` theo thứ tự khác nhau; bỏ `@BeforeEach`/`@AfterEach` để thấy state `static` có thể phụ thuộc thứ tự. Sau đó sửa bằng cache instance thay cho static field.
4. Dùng một test plugin thật tạo/đóng loader qua nhiều vòng; log số registry entries, threads và classloader stats. Nếu tăng không hồi phục, mở heap dump, truy theo GC roots và chỉ sửa đường giữ thực tế.
5. Đánh giá một cache có key là `Class<?>`: nếu value giữ type ngược lại, giải thích tại sao `WeakHashMap` chưa đủ. Thử dùng `ClassValue` khi semantics chỉ là metadata theo class.

## 11. Tài liệu chuẩn để đối chiếu

- [Java Language Specification, chương 12: loading, linking, initialization, unloading](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html)
- [Java API `java.lang.ref`: weak/soft/phantom reachability](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/package-summary.html)
- [Java API `ClassValue<T>`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassValue.html)
- [Java `ThreadLocal` và sự cần thiết của `remove()`](https://docs.oracle.com/en/java/javase/25/core/thread-local-variables.html)
- [JUnit Jupiter 6 — Test Instance Lifecycle](https://docs.junit.org/6.1.2/writing-tests/test-instance-lifecycle.html)
- [JUnit 6 — Build Support](https://docs.junit.org/6.1.2/running-tests/build-support.html)
- [Java `jcmd` diagnostics và classloader/metaspace stats](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html)

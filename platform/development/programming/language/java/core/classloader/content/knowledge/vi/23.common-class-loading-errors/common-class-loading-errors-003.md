# NoClassDefFoundError sau khi khởi tạo lớp thất bại

> **Java Core → ClassLoader → Lỗi thường gặp.** Một thông báo `NoClassDefFoundError: Could not initialize class X` thường không có nghĩa X.class bị xóa hay thiếu JAR. Class có thể **đã được nạp thành công**, nhưng quá trình chạy static initializer (`<clinit>`) thất bại. JVM đánh dấu đúng runtime class ấy ở trạng thái **erroneous**, và các lần cần khởi tạo tiếp theo sẽ báo `NoClassDefFoundError`. Bài này phân tích cơ chế, tái hiện bằng Java 17, xác định nguyên nhân ban đầu và giải pháp đúng cho application, test, server và plugin ClassLoader.

## 1. Cơ chế cốt lõi

Một lớp Java thường đi qua:

~~~text
Loading                Tìm bytecode / tạo runtime Class
   |
   v
Linking                Verify, prepare, resolve khi thích hợp
   |
   v
Initialization         Chạy static field initializer + static block
   |
   +--------------------------+
   |                          |
   v                          v
SUCCESS                   FAILURE
initialized               erroneous
                              |
                 first active use: EIIE hoặc Error gốc
                              |
                 later initialization attempt: NCDFE
~~~

`EIIE` là `ExceptionInInitializerError`, `NCDFE` là `NoClassDefFoundError`. Khi initializer của X ném một exception như `IllegalStateException` hoặc `NullPointerException`, JVM thường bọc nó trong `ExceptionInInitializerError` cho lần thất bại đầu tiên. Nếu initializer ném một `Error`, JVM có thể truyền chính Error đó chứ không bọc thêm EIIE.

Sau thất bại, JVM lưu trạng thái **erroneous** cho **runtime class X cụ thể**, tức class có binary name và defining ClassLoader nhất định. Một lần sử dụng tiếp theo **cần initialization** sẽ ném `NoClassDefFoundError` mà không chạy lại `<clinit>`. Sửa biến môi trường, file cấu hình hay `System.setProperty` sau sự kiện này không tự reset trạng thái của class.

Đây là quy tắc trong [JLS `12.4.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4.2), không chỉ là chi tiết của HotSpot.

### 1.1. Phân biệt ba lỗi dễ bị lẫn

| Lỗi | Tầng xảy ra | Dấu hiệu |
| --- | --- | --- |
| `ClassNotFoundException` | Một API yêu cầu tìm class theo tên nhưng không tìm thấy | Checked exception từ `loadClass`, `Class.forName` |
| `NoClassDefFoundError` do thiếu definition/dependency | JVM/linking không lấy được definition cần thiết | Có thể có tên class/dependency bị thiếu |
| `NoClassDefFoundError: Could not initialize class X` | X đã có runtime Class nhưng initialization trước đó fail | Nên tìm first exception của `X.<clinit>` |
| `ExceptionInInitializerError` | First failed init do non-Error exception | `getCause()` chứa exception gốc |
| `ClassFormatError` / `VerifyError` | Classfile/verification | Bytes hoặc bytecode không hợp lệ |
| `UnsupportedClassVersionError` | Runtime không hỗ trợ classfile version | Kiểm tra phiên bản JDK và `javac --release` |

Một `NoClassDefFoundError` không có cụm “Could not initialize class” vẫn có nhiều nguyên nhân, vì thế không chẩn đoán tất cả là static-init failure. Ngược lại, nếu đã có first `ExceptionInInitializerError` thì tiếp tục copy JAR không phải bước sửa đầu tiên.

## 2. Class initialization diễn ra lúc nào?

Theo JLS `12.4.1, initialization có thể được kích hoạt ngay trước:

- Tạo instance bằng `new X()`.
- Gọi static method của X: `X.run()`.
- Gán/đọc static field khai báo bởi X, trừ tình huống **constant variable** có giá trị compile-time constant.
- Các API reflection/`Class.forName(..., true, loader)` và một số method handles theo Java spec.
- Khi cần initialize subclass, JVM khởi tạo superclass và những superinterfaces phù hợp có default methods theo thuật toán đặc tả.

Các thao tác sau **không tự đồng nghĩa** đã init thành công:

~~~java
Class<?> type = X.class;
Class<?> onlyLoaded = loader.loadClass("demo.X");
Class<?> noInit = Class.forName("demo.X", false, loader);
~~~

Đây là snippet cần X và loader hợp lệ. `ClassLoader.loadClass` không được coi là lệnh initialize; `Class.forName(name,false,loader)` nêu rõ không yêu cầu initialize tại lời gọi ấy. Nhưng một số linking/resolution khác vẫn có thể xảy ra, nên “chưa init” không có nghĩa mọi thao tác reflection đều hoàn toàn không có lỗi.

### 2.1. Constant-variable ngoại lệ

~~~java
static final String LABEL = "hello";       // compile-time constant
static final int SIZE = 42;                // compile-time constant
static final Object OBJECT = new Object(); // không phải constant variable
static final int COUNT = compute();        // không phải constant variable
~~~

Đây là field declarations minh họa trong class. Compiler có thể inline `LABEL` hoặc `SIZE` ở caller, nên đọc chúng không nhất thiết khởi tạo class khai báo. Đọc `OBJECT` hoặc `COUNT` thường yêu cầu initialization.

## 3. Bài lab 1: first EIIE, next NoClassDefFoundError

**Tệp duy nhất `InitFailureDemo.java`:**

~~~java
public final class InitFailureDemo {
    static final class Broken {
        static final int NUMBER = initialize();

        private static int initialize() {
            System.out.println("initializer runs");
            throw new IllegalStateException("configuration missing");
        }

        static int read() {
            return NUMBER;
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            System.out.println("attempt=" + attempt);
            try {
                System.out.println("value=" + Broken.read());
            } catch (LinkageError error) {
                System.out.println("error="
                        + error.getClass().getSimpleName());
                if (error instanceof ExceptionInInitializerError e) {
                    System.out.println("root="
                            + e.getCause().getClass().getSimpleName());
                }
            }
        }
    }
}
~~~

Chạy JDK 17+:

~~~bash
javac --release 17 InitFailureDemo.java
java -cp . InitFailureDemo
~~~

Stdout dự kiến:

~~~text
attempt=1
initializer runs
error=ExceptionInInitializerError
root=IllegalStateException
attempt=2
error=NoClassDefFoundError
~~~

**Giải thích:**

1. `Broken.read()` là lời gọi static, JVM phải initialize `Broken` trước.
2. Static field initializer `NUMBER=initialize()` in `initializer runs` rồi ném `IllegalStateException`.
3. Vì đây không phải `Error`, lần đầu JVM báo `ExceptionInInitializerError` có `getCause()` là lỗi gốc.
4. Runtime class `Broken` chuyển thành erroneous; method `read` chưa thực sự trả về value.
5. Lần sau `Broken.read()` không thực thi lại static initializer. JVM ném `NoClassDefFoundError`.
6. Dùng `LinkageError` tại lab này vì cả EIIE và NCDFE đều là subclass của nó; trong production đừng bắt mọi `Error` rồi âm thầm bỏ qua.

**Vì sao không viết `static { throw new RuntimeException(); }` trực tiếp?** Java language có quy tắc static initializer **phải có khả năng hoàn tất bình thường**, nên một block luôn ném exception vô điều kiện có thể không biên dịch. Đưa lỗi vào method `initialize()` tạo mã hợp lệ và biểu thị tình huống thực tế như đọc configuration thất bại.

**Giới hạn stdout:** Bài lab chỉ in tên lớp Throwable; nếu in `printStackTrace()`, message hoặc cause stack có thể thay đổi theo JVM/JDK. Không yêu cầu test assert toàn bộ stack trace dòng-đến-dòng.

## 4. JVM lưu trạng thái class thế nào?

JLS `12.4.2 và JVMS `5.5` mô tả một trạng thái cho mỗi runtime class:

| Trạng thái | Hành vi khi cần initialize |
| --- | --- |
| Verified/prepared, chưa initialized | Một thread bắt đầu init |
| Đang initialized bởi thread T | Tái nhập ở chính T có quy tắc riêng; thread khác chờ |
| Initialized thành công | Dùng class, không chạy lại static init |
| Erroneous sau thất bại | Ném `NoClassDefFoundError` |

Class initialization có **initialization lock** do JVM quản lý. Nó không phải `ClassLoader.getClassLoadingLock(name)`: khóa thứ hai liên quan load/define class, tránh duplicate `defineClass`. Một loader implement thread-safe không đảm bảo static initializer không thất bại.

Nếu một thread T1 bắt đầu init và thread T2 đồng thời cần class đó, T2 chờ T1. Nếu T1 thất bại, T2 quay lại thấy erroneous và nhận NCDFE. **Thread nào được first error phụ thuộc scheduler**, không phụ thuộc tên thread.

### 4.1. Nếu static code ném một Error?

~~~java
static int load() {
    throw new AssertionError("invariant broken");
}
~~~

Snippet nằm trong class được init qua static field. Vì `AssertionError extends Error`, thuật toán initialization không bắt buộc wrap lần đầu thành `ExceptionInInitializerError`; caller đầu có thể thấy chính `AssertionError`. Sau đó class vẫn erroneous và lần cần init tiếp theo nhận `NoClassDefFoundError`.

Không viết lời giải thích “mọi lỗi lần đầu là EIIE”. Quy tắc chính xác là **wrap non-Error throwable**, giữ Error theo thuật toán đặc tả.

### 4.2. Nếu superclass khởi tạo thất bại?

Khi `Child extends Parent`, JVM cần initialize `Parent` trước khi thực thi static initializer của `Child`. Nếu Parent fail, Child có thể được đánh dấu erroneous mà static code của Child chưa từng chạy. Lỗi liên quan Child trong log sau đó không nhất thiết chỉ ra nguyên nhân trong `Child.<clinit>`.

Cách tìm root cause: lần theo **stack trace ở lần thất bại sớm nhất**, cả `Parent.<clinit>`/superinterfaces và dependent static factories. Đừng chỉ search tên class trên dòng NCDFE cuối.

## 5. Bài lab 2: load class không đồng nghĩa initialize

**`InitializationTriggerDemo.java`:**

~~~java
public final class InitializationTriggerDemo {
    static final class Sample {
        static {
            System.out.println("Sample initialized");
        }

        static final String CONSTANT = "fixed";
        static int dynamic = 7;
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName(
            "InitializationTriggerDemo$Sample",
            false,
            InitializationTriggerDemo.class.getClassLoader());

        System.out.println("loaded=" + type.getSimpleName());
        System.out.println("constant=" + Sample.CONSTANT);
        System.out.println("before dynamic read");
        System.out.println("dynamic=" + Sample.dynamic);
    }
}
~~~

~~~bash
javac --release 17 InitializationTriggerDemo.java
java -cp . InitializationTriggerDemo
~~~

Stdout:

~~~text
loaded=Sample
constant=fixed
before dynamic read
Sample initialized
dynamic=7
~~~

`Class.forName(name,false,loader)` lấy object Class nhưng không init; đọc compile-time constant `Sample.CONSTANT` không buộc init; đọc nonconstant `Sample.dynamic` mới kích hoạt static block. Đây là cách phân biệt **“class đã tìm thấy/nạp”** với **“class đã initialized thành công”**.

## 6. Sửa cấu hình rồi retry trong cùng loader có được không?

Giả sử một static singleton:

~~~java
public final class Settings {
    static final String TOKEN = readRequiredToken();

    static String readRequiredToken() {
        String token = System.getProperty("service.token");
        if (token == null) {
            throw new IllegalStateException("missing service.token");
        }
        return token;
    }
}
~~~

Đây là class biên dịch được (không có main). Lần đầu một active use khiến `readRequiredToken()` throw, `Settings` erroneous. Bạn có thể gọi `System.setProperty("service.token","fixed")`, nhưng **điều đó không làm static initializer của same runtime Settings được chạy lại**.

Những thao tác **không reset erroneous state**:

- `Class.forName(name, false, sameLoader)`.
- `ClassLoader.loadClass(name)` với cùng defining loader.
- Gọi `System.gc()`.
- Gọi `URLClassLoader.close()` rồi giữ `Class<?>` cũ.
- Thay/ghi đè JAR file trong lúc JVM vẫn giữ class đã nạp.
- Retry vô hạn một static method trên class đã failed init.

Không có Java SE API phổ quát kiểu `resetClinit`. Cách phục hồi thực tế là **khởi động lại JVM sau khi sửa nguyên nhân**, hoặc trong plugin architecture tạo **defining ClassLoader mới** để có runtime class mới.

## 7. Bài lab 3: phục hồi bằng loader mới cho plugin

Cấu trúc:

~~~text
new-loader-lab/
├── plugin-src/demo/plugin/Settings.java
├── host-src/NewLoaderDemo.java
└── build/
    ├── plugin/
    ├── host/
    └── plugin.jar
~~~

**`plugin-src/demo/plugin/Settings.java`:**

~~~java
package demo.plugin;

public final class Settings {
    private static final String VALUE = initialize();

    private static String initialize() {
        String token = System.getProperty("lesson.token");
        System.out.println("init token=" + token);
        if (token == null) {
            throw new IllegalStateException("token unavailable");
        }
        return token;
    }

    public static String read() {
        return VALUE;
    }
}
~~~

**`host-src/NewLoaderDemo.java`:**

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class NewLoaderDemo {
    private static final String TYPE = "demo.plugin.Settings";

    static URLClassLoader open(URL jar) {
        return new URLClassLoader(
            new URL[] {jar}, ClassLoader.getPlatformClassLoader());
    }

    static void initialize(String label, ClassLoader loader) {
        try {
            Class.forName(TYPE, true, loader);
            System.out.println(label + "=OK");
        } catch (LinkageError problem) {
            System.out.println(label + "="
                    + problem.getClass().getSimpleName());
        } catch (ClassNotFoundException missing) {
            throw new IllegalStateException(missing);
        }
    }

    public static void main(String[] args) throws Exception {
        URL jar = Path.of("build", "plugin.jar")
                .toAbsolutePath().toUri().toURL();
        System.clearProperty("lesson.token");

        try (URLClassLoader oldLoader = open(jar)) {
            Class<?> oldType = oldLoader.loadClass(TYPE);

            initialize("old-first", oldLoader);
            System.setProperty("lesson.token", "ready");
            initialize("old-again", oldLoader);

            try (URLClassLoader newLoader = open(jar)) {
                Class<?> fresh =
                        Class.forName(TYPE, true, newLoader);
                System.out.println("same-class="
                        + (oldType == fresh));
                System.out.println("new-value="
                        + fresh.getMethod("read").invoke(null));
            }
        } finally {
            System.clearProperty("lesson.token");
        }
    }
}
~~~

Từ root `new-loader-lab` (POSIX shell, Java 17+):

~~~bash
mkdir -p build/plugin build/host
javac --release 17 -d build/plugin \
    plugin-src/demo/plugin/Settings.java
jar --create --file build/plugin.jar -C build/plugin .

javac --release 17 -d build/host host-src/NewLoaderDemo.java
java -cp build/host NewLoaderDemo
~~~

Stdout kỳ vọng:

~~~text
init token=null
old-first=ExceptionInInitializerError
old-again=NoClassDefFoundError
init token=ready
same-class=false
new-value=ready
~~~

**Chú ý:**

1. Loader đầu `oldLoader` tìm class trên JAR và lần init đầu thất bại. Sau đó `lesson.token` được sửa nhưng lần init với same loader vẫn gặp NCDFE.
2. Loader mới `newLoader` thực sự **tự define** cùng binary name thành runtime Class khác. Vì nó chưa erroneous và config đã sửa, `<clinit>` chạy thành công.
3. `same-class=false` kiểm tra **runtime class identity**, không tuyên bố class cũ đã unload.
4. Đừng đặt `plugin.jar` vào host classpath hoặc thay parent thành loader đã define `demo.plugin.Settings`: parent delegation có thể làm cả hai “loader mới” vẫn nhận cùng Class cũ.
5. `System.setProperty` là cơ chế mô phỏng lỗi cho lab; trong production không dùng shared process properties như một mutable config trên nhiều concurrent requests.
6. `try-with-resources` close URLClassLoader/JAR handles nhưng không tự dừng threads, xóa static maps hay ép JVM unload classes.

**Không sử dụng loader mới như một cách che mọi lỗi:** phải **sửa nguyên nhân gốc** trước. Nếu config vẫn thiếu, class mới cũng sẽ fail.

## 8. Log lỗi đầu tiên mới là nơi cần điều tra

Trong server, request đầu tiên chạm `ConfigHolder` có thể thất bại lúc 09:00, nhưng log ứng dụng bị cắt và chỉ còn request lúc 10:00 in NCDFE. Điều này khiến người vận hành kết luận nhầm rằng JAR biến mất sau deploy.

Chẩn đoán:

1. Thu stack trace của **first failure** từ đúng JVM/process/generation.
2. Tìm `ExceptionInInitializerError`, `<clinit>`, `Caused by` hoặc `Error` trực tiếp từ static initializer.
3. Ghi class name, process id, defining loader và thời điểm first active use.
4. Phân biệt lỗi config, network, JDBC, native link, bytecode/dependency hoặc permission.
5. Kiểm tra những failures trong **thread khác**: initializer đồng bộ, request thứ hai có thể chỉ thấy NCDFE sau khi chờ thread đầu.
6. Khi lỗi bắt đầu từ superclass, tìm root exception ở superclass chứ không chỉ subclass hiện trong NCDFE mới nhất.
7. Không để framework bắt mọi `Throwable` rồi bỏ qua lỗi gốc; với component hỏng, ghi trạng thái FAILED/UNHEALTHY và tránh đưa vào active routing.

### 8.1. In nguyên cause chain

~~~java
static void report(Throwable failure) {
    Throwable current = failure;
    while (current != null) {
        System.err.println(current.getClass().getName()
                + ": " + current.getMessage());
        current = current.getCause();
    }
}
~~~

Snippet helper cần đặt trong một class. `ExceptionInInitializerError.getCause()` là API hiện đại để lấy exception được bọc; `getException()` còn tồn tại vì tương thích cũ. Với `NoClassDefFoundError` sau lỗi init, **không bảo đảm** cùng error/cause ban đầu luôn còn nguyên qua mọi JDK; first logs là nguồn quan trọng nhất.

### 8.2. Phân biệt ClassNotFoundException và NoClassDefFoundError

Ví dụ `Class.forName("missing.Dependency")` trả `ClassNotFoundException` nếu loader không tìm class theo tên. Nhưng nếu A.class tồn tại rồi khi link/init cần một B không có ở runtime, JVM có thể phát `NoClassDefFoundError`, và cause có thể cho biết B. Nếu A có `<clinit>` fail, những lần initialize lại A cũng có thể ném NCDFE **dù bytes A vẫn tồn tại**.

Bởi thế đầu tiên xem **full error message, root cause, thời điểm xuất hiện** trước khi sửa đường classpath/module path.

## 9. Static initialization thất bại phổ biến vì đâu?

| Nguyên nhân | Lỗi gốc thường gặp | Hành động hợp lý |
| --- | --- | --- |
| Static config đọc missing env/file | `IllegalStateException`, `NullPointerException` | Validate trước startup, nêu rõ key thiếu |
| Static singleton khởi tạo DB/HTTP client | Timeout hoặc unchecked exception | Chuyển sang instance lifecycle và bounded retry |
| Static initializer gọi một dependency missing | `NoClassDefFoundError`/`ClassNotFoundException` được bọc | Kiểm tra runtime dependencies và loader |
| Static reflective scanner thấy signature mismatch | `NoSuchMethodError`/`IllegalAccessError`/related | Kiểm tra binary compatibility và JPMS access |
| Native library load trong static block | `UnsatisfiedLinkError` | Kiểm tra OS/architecture, native library path, JNI symbols |
| Static code ném `AssertionError` | Một `Error` trực tiếp | Xử lý violated invariant, first error có thể là AssertionError |
| Tạo objects quá nhiều | `OutOfMemoryError` | Kiểm tra memory demand/limits/leak |
| Thứ tự init vòng/cross-thread | NPE do partial state hoặc deadlock | Refactor static dependency graph |
| Superclass initialization thất bại | Lỗi xuất phát từ `Parent.<clinit>` | Truy vết earliest parent failure |
| Loader close cạnh tranh với plugin callback | Lỗi khi cần load class/resource chưa có | Quiesce/drain trước close |

**Nếu lỗi là class initialization deadlock**, có thể không thấy EIIE hay NCDFE, vì threads **đang chờ nhau** chứ chưa đánh dấu class erroneous. Dùng thread dump/JFR hoặc `jcmd` cho JVM đang sống để phân biệt.

## 10. Thiết kế tốt hơn: đừng để transient I/O phá class

Một pattern rủi ro:

~~~java
public final class GatewayHolder {
    static final RemoteGateway CLIENT = RemoteGateway.connect();
}
~~~

Đây chỉ là snippet; `RemoteGateway` là type ứng dụng tự định nghĩa. Nếu `connect()` lỗi lúc first active use, `GatewayHolder` có thể erroneous **suốt đời runtime class**.

Một API instance đơn giản hơn:

~~~java
public final class GatewayManager {
    private volatile RemoteGateway current;

    public synchronized RemoteGateway getOrCreate() {
        RemoteGateway existing = current;
        if (existing != null && existing.isHealthy()) {
            return existing;
        }

        RemoteGateway fresh = RemoteGateway.connect();
        current = fresh;
        return fresh;
    }
}
~~~

Đây cũng là snippet và chưa phải giải pháp production hoàn chỉnh: cần xử lý resource cũ, concurrency với close, timeout, backoff và circuit breaker. Nó minh họa điểm cốt lõi: **class có thể initialized bình thường**, trong khi kết nối được tạo theo vòng đời service và có thể retry có giới hạn sau transient failure.

Nguyên tắc:

- Static fields nên ưu tiên constants/immutable dependencies có initialization đáng tin.
- Validation cấu hình và I/O có thể thất bại nên đặt ở factory/startup service rõ ràng.
- Không publish component đã fail health check.
- Retry phải bounded, tránh infinite loops, có logs/circuit breaker thích hợp.
- Với class đã erroneous trong application loader, restart JVM sau khi sửa config thường là phương án rõ ràng; đừng dùng reflection/Unsafe để “force chạy lại `<clinit>`”.

## 11. Unit test, plugin và ServiceLoader

**Unit tests:** test thứ nhất có thể làm class erroneous trong cùng test JVM, test thứ hai sửa mock/property nhưng vẫn NCDFE. Cách tốt là inject dependencies vào instance và tránh static initializer stateful, hoặc cô lập tests bằng **JVM forks / fresh defining loaders** khi chính initialization behavior là chủ đề test.

**Plugin:** phiên bản plugin mới nên được nạp qua loader thế hệ mới, giữ shared API identity ở parent, kiểm tra version/health trước publish, drain tasks cũ, unregister callback/DI/reflection caches, close plugin resources, rồi close old loader. Tạo một URLClassLoader object mới nhưng vẫn delegate implementation class về old parent **không tạo runtime class mới**.

**ServiceLoader:** có thể discover provider đúng, nhưng khi provider được khởi tạo, static initializer của provider fail. Caller có thể thấy `ServiceConfigurationError` được bọc tùy provider instantiation path. Luôn nhìn underlying cause/first log trước khi sửa `META-INF/services`/module `provides`.

**Class unloading:** `URLClassLoader.close()` không ép unload class đã loaded. GC xử lý unload khi defining loader đủ điều kiện reclaim và JVM quyết định. `System.gc()` không phải API reset static fields hay init state.

## 12. Checklist xử lý sự cố

- [ ] Xác định message **`Could not initialize class`** hay lỗi thiếu class/dependency khác.
- [ ] Tìm **first `ExceptionInInitializerError` hoặc `Error` gốc** trong log của cùng JVM/classloader.
- [ ] Kiểm tra method `<clinit>`/static field initializer cụ thể đã ném lỗi.
- [ ] Nếu superclass/superinterface fail, phân tích chain trước khi sửa child.
- [ ] Ghi Java version, startup command, classpath/module path, TCCL và defining loader.
- [ ] Sửa config/secret/dependency/native path **đầu tiên**.
- [ ] Không retry lại class erroneous trong same defining loader.
- [ ] Restart JVM hoặc dựng **new loader + new runtime class** khi cần init lại.
- [ ] Với plugin, không publish thế hệ mới cho tới khi initialize/health-check OK.
- [ ] Ghi đầy đủ root cause và kiểm thử cả success và failed-first-use.
- [ ] Không dùng `System.gc()`, `close(loader)` hoặc `Class.forName(...false...)` để kỳ vọng reset trạng thái.
- [ ] Khi unit test nhiều test cases, tránh share một static initialization failure giữa tests.

## 13. Câu hỏi tự kiểm tra

1. Class file vẫn có trong JAR nhưng sau static-init failure có NCDFE không? **Có**.
2. Lần first active use khi `IllegalStateException` thoát khỏi initializer thường nhận gì? **ExceptionInInitializerError**.
3. Lần cần initialize tiếp theo của same runtime class? **NoClassDefFoundError**.
4. Initializer có tự chạy lại sau khi sửa env/property không? **Không**.
5. Nếu initializer ném `AssertionError` lần đầu, JVM chắc chắn wrap EIIE? **Không**, Error có thể được ném trực tiếp.
6. `ClassLoader.loadClass` là lệnh initialize? **Không**.
7. `Class.forName(name,true,loader)` khác overload false thế nào? **true yêu cầu initialization**.
8. Đọc `static final String X="abc"` có bắt buộc init không? **Không**, có thể là compile-time constant.
9. Đọc `static final int N=calculate()` thì sao? **Đây không là constant variable**, active use có thể init.
10. Hai threads cùng initialize một Class có chạy `<clinit>` hai lần không? **Không**, JVM điều phối.
11. Parent class fail có thể làm Child erroneous không? **Có**.
12. Tạo new URLClassLoader luôn tạo Class mới? **Không**, nếu delegate lên parent đã define nó.
13. Vì sao `System.gc()` không chữa class erroneous? **GC không reset initialization state**.
14. Phục hồi trong plugin cần gì? **Sửa root cause và dùng new generation loader thực sự define class mới**.
15. Khác nhau căn bản giữa CNFE và NCDFE? **CNFE là checked lookup failure; NCDFE là Error lúc runtime/linking/init state**.
16. Lỗi nào quan trọng nhất trong log? **Lỗi gốc đầu tiên**, không chỉ NCDFE cuối.
17. Có nên tạo DB connection dễ fail trong `static {}` không? **Không nên**, nên quản lý lifecycle/retry ở service.
18. Nếu thread chết vì class-init error nhưng process sống, request khác có thể nhận NCDFE? **Có**, cùng runtime class đã erroneous.

## 14. Tài liệu chuẩn

1. [JLS `12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4.1): active use, constants.
2. [JLS `12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4.2): erroneous state, initialization locks, EIIE và NCDFE.
3. [JVMS `5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.5): runtime initialization procedure.
4. [ExceptionInInitializerError — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ExceptionInInitializerError.html): causal exception and hierarchy.
5. [NoClassDefFoundError — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NoClassDefFoundError.html): runtime linkage error.
6. [ClassNotFoundException — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassNotFoundException.html): checked lookup failure.
7. [Class — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `forName` và initialize flag.
8. [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, delegation, class identity.
9. [URLClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): loader lifecycle/close.
10. [JLS `12.7 — Class Unloading](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.7): GC/defining loader eligibility.

**Ghi nhớ:** Lỗi `NoClassDefFoundError: Could not initialize class X` thường là **hậu quả của một lần khởi tạo trước thất bại**, không phải thiếu `X.class`. Đọc first exception/cause ở `<clinit>`, sửa nguyên nhân gốc, rồi dùng fresh JVM hoặc new defining ClassLoader khi cần class mới. Đừng mong retry cùng erroneous class, sửa property hay `System.gc()` đặt lại trạng thái.

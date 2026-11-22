# Quản lý vòng đời URLClassLoader bằng close và try-with-resources

## 1. Vì sao URLClassLoader có vòng đời tài nguyên?

`java.net.URLClassLoader` là một triển khai `ClassLoader` có khả năng tìm class và tài nguyên từ một tập URL: thư mục, tệp JAR và các nguồn URL được hỗ trợ. Nó thường xuất hiện trong **plugin system**, công cụ chạy mã động, trình biên dịch/test runner và các môi trường cần thêm thư viện lúc runtime.

Khi tìm class trong một JAR, loader có thể mở tệp JAR và duy trì cấu trúc truy cập để phục vụ những lần nạp sau. Vì vậy, ngoài nhiệm vụ định nghĩa class, `URLClassLoader` còn có **tài nguyên I/O cần được đóng**.

Từ Java 7, `URLClassLoader` triển khai `java.io.Closeable` (và qua đó là `AutoCloseable`):

```java
public class URLClassLoader
        extends SecureClassLoader
        implements Closeable {

    public void close() throws IOException;
}
```

Đây là **trích đoạn khai báo API**, không phải code để tự định nghĩa lại class JDK.

**Nguyên tắc quan trọng nhất:** gọi `close()` là **đóng khả năng tìm class/resource mới từ các URL mà loader quản lý, đồng thời cố gắng giải phóng các tệp đã mở**. Nó **không đồng nghĩa** hủy mọi class đã được định nghĩa, dừng thread, chạy bộ hủy đối tượng, hoặc ép JVM unload class.

## 2. Chính xác close() làm gì?

Theo hợp đồng chính thức của `URLClassLoader.close()`:

1. **Đóng loader đối với việc tìm class/resource mới do chính loader này định nghĩa**: sau khi đóng, những class hay resource chưa được loader này tìm/nạp trước đó không còn được tải mới từ URL search path của nó theo cách bình thường.
2. **Các class/resource thuộc parent loader vẫn truy cập được** qua chuỗi ủy quyền khi phù hợp.
3. **Các class/resource đã được nạp vẫn có thể sử dụng**. Đối tượng `Class<?>`, class đã định nghĩa và các instance hiện có không bị biến mất chỉ vì loader đóng.
4. Với nguồn `jar:` và `file:`, loader cố gắng **đóng các tệp đã mở** khi phục vụ việc tìm kiếm. Điều này đặc biệt quan trọng để tránh giữ file handle/JAR bị khóa trên hệ điều hành.
5. **Một lần đóng nữa trên loader đã đóng không có tác dụng**; không cần viết thêm trạng thái tự tạo chỉ để gọi `close()` đúng một lần.
6. `close()` **có thể ném `IOException`**. Khi có nhiều lỗi I/O trong quá trình đóng, exception đầu tiên được ném ra, các lỗi tiếp theo được gắn vào `getSuppressed()`.

Có một giới hạn concurrency rất quan trọng: nếu thread khác **đang nạp class đúng lúc `close()` được gọi**, tài liệu Java nêu rằng **kết quả của lần nạp đó không xác định**. Vì thế cách quản lý vòng đời đúng phải **ngăn những công việc nạp mới và đợi các công việc đang chạy kết thúc trước khi đóng**; không dùng `close()` như cơ chế ngắt cưỡng bức một hoạt động nạp class.

### Bảng phân biệt hiệu ứng

| Hoạt động | `close()` có bảo đảm thực hiện? |
|---|---|
| Đóng những tệp JAR/file mà URLClassLoader đã mở | **Cố gắng thực hiện**, có thể ném `IOException` |
| Ngăn loader tự định nghĩa class mới từ các URL của nó | **Có**, theo hợp đồng `close()` |
| Tự xóa `Class<?>` đã nạp | **Không** |
| Vô hiệu hóa các object đã được tạo từ class plugin | **Không** |
| Dừng các thread, executor, timer do plugin khởi động | **Không** |
| Gỡ TCCL khỏi thread đang giữ plugin loader | **Không** |
| Xóa `static` caches, listener registrations hay ThreadLocal | **Không** |
| Ép JVM garbage collect hoặc unload class ngay | **Không** |
| Bảo đảm JAR có thể được xóa trong mọi hoàn cảnh | **Không**; nơi khác vẫn có thể giữ file |
| Tự làm class loader khác đổi phiên bản của class đã nạp | **Không** |

Tóm lại: `close()` giải quyết **một phần vòng đời tài nguyên I/O**, còn vòng đời plugin/ứng dụng là trách nhiệm lớn hơn.

## 3. URLClassLoader tìm class như thế nào trước và sau khi đóng?

Với một `URLClassLoader` dùng cơ chế `ClassLoader.loadClass` mặc định, thứ tự thường là:

```text
loadClass("plugin.Greeter")
       │
       ▼
findLoadedClass(name)
       │ đã nạp → dùng class cũ
       │ chưa nạp
       ▼
parent.loadClass(name) / bootstrap
       │ parent tìm thấy → dùng class của parent
       │ không tìm thấy
       ▼
URLClassLoader.findClass(name)
       │ trước close: tìm từ URL search path
       │ sau close: không tìm được class mới từ URL này
       ▼
Class<?> hoặc ClassNotFoundException
```

Vì vậy:

- Nếu **class đã được nạp trước khi đóng**, `loader.loadClass(name)` có thể trả lại **cùng đối tượng `Class<?>`** sau khi đóng.
- Nếu **class chỉ tồn tại ở plugin JAR và chưa từng được nạp**, sau khi đóng thì loader không còn con đường bình thường để định nghĩa class mới đó; `loadClass` có thể kết thúc bằng `ClassNotFoundException`.
- Nếu **class do parent hoặc bootstrap cung cấp**, ví dụ `java.lang.String`, parent delegation có thể tiếp tục hoạt động sau khi URLClassLoader đóng.

Đừng hiểu `close()` là đặt cờ làm **mọi lời gọi `loadClass`** thất bại. Nó chủ yếu chặn phần **tìm và nạp mới do chính URLClassLoader đảm nhiệm**.

Ngược lại, đừng hiểu “class đã nạp vẫn dùng được” là mọi thao tác của nó **luôn** chạy thành công: một phương thức đã nạp có thể về sau tham chiếu **class phụ thuộc chưa được nạp**, cần resource mới, hoặc cố mở lại tài nguyên trong JAR. Những hoạt động đó có thể thất bại vì loader đã đóng. Vì thế vẫn phải ngừng công việc plugin **trước** khi đóng loader.

## 4. Ví dụ đầy đủ: đóng loader nhưng class đã nạp vẫn tồn tại

Ta tạo một plugin JAR chứa hai class: `demo.Greeter` và `demo.Later`. Chương trình host chỉ nạp `Greeter` trước khi đóng. Sau đó ta thử dùng lại `Greeter`, nạp `Later`, truy cập `String` từ parent và gọi `close()` thêm lần nữa.

### 4.1. File src/demo/Greeter.java

```java
package demo;

public final class Greeter {
    static {
        System.out.println("Greeter initialized");
    }

    public static String say() {
        return "hello from plugin";
    }
}
```

### 4.2. File src/demo/Later.java

```java
package demo;

public final class Later {
    public static String name() {
        return "late class";
    }
}
```

Class `Later` cố ý **không được nạp trước khi đóng**. Nó tồn tại trong archive để kiểm chứng trường hợp loader không còn được phép tìm class mới từ JAR.

### 4.3. File LoaderLifecycleDemo.java

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderLifecycleDemo {
    public static void main(String[] args) throws Exception {
        Path pluginJar = Path.of("plugin.jar").toAbsolutePath();
        URL[] urls = {pluginJar.toUri().toURL()};

        URLClassLoader loader = new URLClassLoader(
                urls,
                LoaderLifecycleDemo.class.getClassLoader()
        );

        Class<?> greeter;
        try (loader) {
            System.out.println("inside scope");

            greeter = Class.forName("demo.Greeter", false, loader);
            System.out.println("defined by child: "
                    + (greeter.getClassLoader() == loader));

            System.out.println("before invocation");
            System.out.println(
                    greeter.getMethod("say").invoke(null)
            );
        }

        System.out.println("after close");

        Class<?> same = loader.loadClass("demo.Greeter");
        System.out.println("loaded class reused: " + (same == greeter));

        System.out.println("existing method still callable: "
                + greeter.getMethod("say").invoke(null));

        System.out.println("parent String available: "
                + (loader.loadClass("java.lang.String") == String.class));

        try {
            loader.loadClass("demo.Later");
            System.out.println("unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("new plugin class unavailable");
        }

        loader.close();
        System.out.println("second close completed");
    }
}
```

`try (loader)` là cú pháp Java 9+ cho một biến resource **đã được khai báo bên ngoài**, miễn là biến đó final hoặc effectively final. Trong ví dụ, không gán lại biến `loader`, nên code biên dịch được trên Java 17+. Nếu cần hỗ trợ Java 7/8 ở mức source, dùng mẫu `try (URLClassLoader loader = new URLClassLoader(...))`, nhưng khi đó không thể truy cập biến loader ngoài scope của `try` chỉ bằng tên đó.

### 4.4. Tạo JAR và chạy

Từ một thư mục làm việc chứa `LoaderLifecycleDemo.java` và hai file `src/demo/*.java`, chạy bằng JDK 17+.

Trên Bash:

```bash
mkdir -p plugin-classes
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force plugin-classes | Out-Null
```

Sau đó:

```bash
javac -d plugin-classes src/demo/Greeter.java src/demo/Later.java
jar --create --file plugin.jar -C plugin-classes .
javac LoaderLifecycleDemo.java
java -cp . LoaderLifecycleDemo
```

Cấu trúc sau build:

```text
project/
├── LoaderLifecycleDemo.java
├── LoaderLifecycleDemo.class
├── plugin.jar
├── src/
│   └── demo/
│       ├── Greeter.java
│       └── Later.java
└── plugin-classes/
    └── demo/
        ├── Greeter.class
        └── Later.class
```

**Điều kiện quan trọng để kết quả đúng:** chạy host với `-cp .`, **không** thêm `plugin.jar` hoặc `plugin-classes` vào application classpath. Nếu parent loader thấy class plugin trước, parent-first delegation có thể trả class từ parent và làm sai ý nghĩa thí nghiệm.

Stdout trên JDK 17+ với điều kiện trên:

```text
inside scope
defined by child: true
before invocation
Greeter initialized
hello from plugin
after close
loaded class reused: true
existing method still callable: hello from plugin
parent String available: true
new plugin class unavailable
second close completed
```

### 4.5. Phân tích kết quả

1. `Class.forName("demo.Greeter", false, loader)` yêu cầu tìm/nạp Greeter nhưng **không yêu cầu chạy static initializer**. `defined by child: true` cho biết URLClassLoader trong ví dụ là defining loader của Greeter.
2. `getMethod("say").invoke(null)` gọi static method, nên JVM khởi tạo Greeter và in `Greeter initialized` một lần.
3. Cuối block `try (loader)`, Java tự gọi `loader.close()`. Ta không cần gọi close thủ công trong `finally`.
4. Sau đó `loader.loadClass("demo.Greeter")` trả class đã ghi nhận. `same == greeter` là `true`: loader đã đóng **không xóa runtime class**.
5. Method `say()` đã được nạp và không đòi dependency/plugin resource mới, nên ví dụ vẫn gọi được sau close. Đây **không phải khuyến nghị tiếp tục chạy plugin sau close**.
6. `java.lang.String` do bootstrap cung cấp, nên tìm qua parent/boot vẫn hoạt động.
7. `demo.Later` đã có trong JAR nhưng **chưa được nạp** trước close. URLClassLoader không được tìm/định nghĩa nó từ JAR nữa nên trả `ClassNotFoundException`.
8. Gọi `close()` thêm lần nữa là **no-op** theo hợp đồng. Không có dòng `Greeter initialized` lần thứ hai.

Ví dụ cho thấy ranh giới giữa **trạng thái “loader đóng”** và **trạng thái “class đã định nghĩa”**. Đó là hai khái niệm riêng.

## 5. Mẫu chuẩn: try-with-resources

Khi chương trình tự tạo `URLClassLoader` để chạy một công việc có phạm vi hữu hạn, cách thông thường là:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class ScopedLoaderDemo {
    public static void main(String[] args) throws Exception {
        URL jarUrl = Path.of("plugin.jar").toUri().toURL();
        ClassLoader parent = ScopedLoaderDemo.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                     new URLClassLoader(new URL[] {jarUrl}, parent)) {
            Class<?> type = pluginLoader.loadClass("demo.Greeter");
            System.out.println("loaded: " + type.getName());
        }
    }
}
```

Với `plugin.jar` từ ví dụ trước, biên dịch/chạy:

```bash
javac ScopedLoaderDemo.java
java -cp . ScopedLoaderDemo
```

Stdout:

```text
loaded: demo.Greeter
```

Chỉ nạp class không yêu cầu chạy `Greeter.<clinit>`, nên không in `Greeter initialized`. Khi block `try` kết thúc bình thường hoặc kết thúc bởi exception, `close()` sẽ được gọi tự động.

Lợi ích:

- Dễ nhìn thấy **ai sở hữu loader** và **đến lúc nào nó phải đóng**.
- Đảm bảo cố gắng đóng tài nguyên ở cuối scope, kể cả khi logic trong block ném exception.
- Không cần lặp lại `close()` ở mọi nhánh `return`, `throw` hoặc `catch`.
- Hạn chế quên đóng loader khi build tool, plugin host hoặc test runner gặp lỗi.

**Không bọc URLClassLoader trong try-with-resources quá sớm nếu plugin phải sống lâu hơn scope đó.** Ví dụ một phương thức `createPlugin()` nạp class bằng `try (URLClassLoader loader = ...)` rồi trả đối tượng plugin cho caller có thể đóng loader trước khi caller sử dụng class khác/resource của plugin. Lỗi có thể chỉ xuất hiện khi chạy tính năng ít dùng.

## 6. try-with-resources đóng vào thời điểm nào?

Cấu trúc:

```java
try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
    usePlugin(loader);
}
// Tại đây close() đã được gọi.
```

là **mã minh họa**, các biến `urls`, `parent` và method `usePlugin` cần được định nghĩa trong ứng dụng.

Java đóng resource **sau khi thân try kết thúc và trước khi chuyển sang code phía sau**. Dù thân try có `return` hay ném exception, Java vẫn cố đóng resource.

Với nhiều resources:

```java
try (
    URLClassLoader loader = new URLClassLoader(urls, parent);
    java.io.InputStream stream = loader.getResourceAsStream("settings.txt")
) {
    // Sử dụng loader và stream.
}
```

Đây là **trích đoạn**: `urls`, `parent` là giá trị có sẵn, và `stream` có thể `null` nếu resource không tồn tại. Khi có nhiều resources, chúng được đóng theo **thứ tự ngược với thứ tự khai báo**: `stream.close()` trước, `loader.close()` sau. Đây là thứ tự hợp lý để hoàn thành việc đọc resource trước khi đóng chính loader/JAR.

Với `URLClassLoader.getResourceAsStream`, tài liệu còn cho biết các input streams được mở qua phương thức này có thể bị đóng khi loader đóng. Tuy vậy, **không nên dựa vào loader để dọn thay mọi stream**: đóng stream ngay tại nơi sử dụng (try-with-resources riêng) giúp quản lý tài nguyên rõ ràng và tránh giữ resource lâu hơn cần thiết.

Đừng đọc tiếp một `InputStream` đã bị đóng và kỳ vọng nội dung còn nguyên. Việc mở một URL resource lấy được trước close bằng `url.openStream()` cũng không có bảo đảm tất cả underlying handles vẫn khả dụng sau khi loader đã giải phóng tài nguyên.

## 7. Xử lý IOException khi đóng loader

`URLClassLoader.close()` khai báo:

```java
public void close() throws IOException
```

Nó cố đóng các tệp đã mở. Nếu một hoặc nhiều thao tác đóng thất bại, `IOException` có thể được ném ra. Nếu nhiều lỗi I/O được phát hiện, lỗi đầu tiên được ném, những lỗi tiếp theo có thể nằm trong `getSuppressed()`.

Có hai kiểu exception phải xét:

1. **Exception từ logic đang chạy trong thân try**: ví dụ provider khởi tạo thất bại hoặc code xử lý ném exception.
2. **Exception từ `close()`**: I/O khi giải phóng JAR/file resources.

Với try-with-resources, nếu cả hai cùng xảy ra, Java giữ exception từ **thân try làm exception chính**, và gắn lỗi đóng vào danh sách **suppressed**. Điều này giúp không che mất nguyên nhân ban đầu.

### Ví dụ chạy được minh họa suppressed exceptions

Đây là một resource mô phỏng, **không phải bản triển khai lại URLClassLoader**. Nó chỉ thể hiện ngữ nghĩa chung của try-with-resources khi `close()` lỗi.

Tạo `SuppressedDemo.java`:

```java
import java.io.IOException;

public final class SuppressedDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IllegalStateException("work failed");
        } catch (Exception ex) {
            System.out.println("primary: " + ex.getMessage());
            System.out.println("suppressed count: "
                    + ex.getSuppressed().length);
            System.out.println("first suppressed: "
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

Chạy:

```bash
javac SuppressedDemo.java
java SuppressedDemo
```

Stdout:

```text
closing
primary: work failed
suppressed count: 1
first suppressed: close failed
```

Điểm mấu chốt: lỗi gốc `work failed` không bị lỗi đóng `close failed` ghi đè. Khi cần chẩn đoán, xem cả `getCause()` lẫn `getSuppressed()`.

**Nếu thân try không có lỗi nhưng close() ném IOException**, lỗi đóng trở thành exception chính và phải được xử lý/khai báo. Với chương trình đơn giản, có thể khai báo `main(String[] args) throws Exception` như ví dụ mục 4. Với ứng dụng thật, quyết định báo lỗi/ghi log/rollback theo chính sách rõ ràng.

### Bắt lỗi khi đóng thủ công

Trong một lifecycle manager có phương thức `stop()`, đôi khi cần đóng loader sau nhiều thao tác cleanup:

```java
// Trích đoạn: loader là URLClassLoader do manager sở hữu.
try {
    loader.close();
} catch (java.io.IOException ex) {
    System.err.println("Failed to close plugin loader: " + ex);
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("Suppressed close error: " + suppressed);
    }
}
```

Không nên âm thầm nuốt IOException: nếu tệp JAR vẫn đang bị giữ mở, thao tác thay thế/xóa JAR sau đó có thể thất bại, nhất là ở hệ điều hành có file locking nghiêm ngặt.

## 8. Đóng loader không có nghĩa unloading classes

Cần phân biệt bốn khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| **Đóng loader** | `URLClassLoader.close()` đóng nguồn URL/JAR và ngăn tìm class/resource mới của nó |
| **Ngừng plugin** | Ứng dụng dừng tác vụ, unregister listeners, đóng tài nguyên plugin và không tiếp tục gọi plugin |
| **Loader không còn reachable** | Chương trình đã bỏ các strong references đến loader/class/instances khiến loader không thể được truy cập từ GC roots |
| **Class unloading** | JVM có thể thu gom metadata/classes tương ứng trong quá trình GC khi đủ điều kiện |

**`close()` không yêu cầu JVM unload ngay**. Class unloading là hoạt động do JVM quản lý, tùy reachability và chính sách GC; `System.gc()` cũng chỉ là một lời yêu cầu, không phải bảo đảm.

Ví dụ nguồn giữ loader sống:

```text
Thread pool worker
     │
     └── thread.contextClassLoader ───────┐
                                         ▼
Global static registry ──> Plugin object ──> PluginClassLoader
                                         ▲
Cached Class<?> / Method ────────────────┘
```

Mô hình này là sơ đồ **các đường tham chiếu có thể xảy ra**, không phải mọi đối tượng đều bắt buộc có đúng chuỗi reference như trên.

Một thread pool giữ TCCL trỏ đến plugin loader đã `close()` vẫn có thể ngăn GC thu gom loader. Một cache lưu `Class<?>`, `java.lang.reflect.Method`, constructor, proxy, callback hoặc object plugin cũng có thể kéo dài tuổi thọ runtime class tương ứng. Plugin tự tạo thread và không dừng thread có thể giữ classloader qua target/context hoặc static fields.

**Vì vậy:** muốn redeploy/reload thực sự, vừa phải **đóng nguồn I/O**, vừa phải **dọn các tham chiếu và công việc** liên quan đến plugin. Không được dùng kết quả `URLClassLoader.close()` thành công như bằng chứng JVM đã giải phóng toàn bộ bộ nhớ class metadata.

## 9. Vòng đời plugin: create → start → use → stop → close

Với loader phục vụ một plugin **lâu dài**, try-with-resources quanh toàn bộ vòng đời hợp lý hơn try quanh **chỉ bước nạp class đầu tiên**.

```text
[1] Create URLClassLoader
           │
           ▼
[2] Load/initialize plugin entry point
           │
           ▼
[3] Start plugin; đăng ký task/listener
           │
           ▼
[4] Use plugin qua các request
           │
           ▼
[5] Ngừng nhận request mới
           │
           ▼
[6] Chờ task đang chạy kết thúc (graceful shutdown)
           │
           ▼
[7] Unregister listener, stop executor,
    đóng stream/socket/db connection của plugin,
    dọn caches/TCCL/reference
           │
           ▼
[8] URLClassLoader.close()
           │
           ▼
[9] Bỏ references đến class/loader;
    JVM có thể unload khi đủ điều kiện
```

Thứ tự **ngừng công việc trước khi đóng loader** rất quan trọng vì việc nạp class cùng lúc với `close()` không có kết quả được bảo đảm. Không dùng `close()` để ép tất cả task kết thúc tức thời.

### Mẫu lifecycle scope mức cao

```java
// PSEUDOCODE / trích đoạn: PluginRuntime và các method
// stopAcceptingWork, awaitQuiescence, ... do ứng dụng cung cấp.
try (URLClassLoader loader = createPluginLoader(pluginJar)) {
    PluginRuntime runtime = startPlugin(loader);
    try {
        runtime.serve();
    } finally {
        runtime.stopAcceptingWork();
        runtime.awaitQuiescence();
        runtime.unregisterCallbacks();
        runtime.closeOwnedResources();
    }
}
// Loader chỉ close sau khi công việc/plugin đã được thu dọn.
```

Không sao chép đoạn trên làm file độc lập: các class và method `PluginRuntime` là mô hình thiết kế, **không phải API chuẩn Java**.

Nếu một bước cleanup thất bại, hệ thống vẫn cần cố gắng thu dọn **những tài nguyên còn lại**, rồi báo các lỗi phù hợp. Có thể dùng một đối tượng quản lý plugin implements `AutoCloseable` với `close()` tự dọn từng resource theo thứ tự; hoặc trong hệ thống phức tạp, dùng lifecycle manager với trạng thái và logging rõ ràng.

### Vì sao không nên trả plugin object ra ngoài scope loader quá ngắn?

Mẫu có vấn đề:

```java
// PSEUDOCODE — minh họa anti-pattern
Object createPlugin(Path jar) throws Exception {
    try (URLClassLoader loader = new URLClassLoader(
            new URL[] {jar.toUri().toURL()},
            getClass().getClassLoader())) {
        return loader.loadClass("demo.Plugin")
                .getDeclaredConstructor()
                .newInstance();
    }
}
// Loader đã bị đóng khi object được trả về!
// Object còn sống nhưng có thể cần dependency/resource mới sau đó.
```

Đừng nghĩ việc method trả về một object plugin đồng nghĩa loader không còn cần thiết. Object đã tạo có thể còn gọi một class chưa được nạp, đọc configuration hay tìm provider từ JAR ở lần sử dụng tiếp theo.

Thiết kế đúng là **đối tượng quản lý vòng đời** sở hữu cả plugin object và URLClassLoader, và chúng được dừng/đóng cùng nhau khi hết phiên sử dụng.

## 10. TCCL và thread pool: dọn một phần vòng đời thường bị quên

Nếu ứng dụng đặt **Thread Context ClassLoader (TCCL)** thành plugin loader để dùng `ServiceLoader` hoặc framework SPI, phải restore TCCL sau khi xử lý.

```java
// Trích đoạn dùng trong một method chạy trên worker thread.
// pluginLoader là đối tượng URLClassLoader phù hợp.
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Gọi framework/service-discovery dùng TCCL nếu cần.
} finally {
    current.setContextClassLoader(previous);
}
```

Nếu một worker thread lâu sống giữ TCCL của plugin cũ sau `close()`, nó có thể giữ **strong reference** đến loader và ngăn class unloading. Nó còn khiến request khác vô tình dùng ngữ cảnh plugin đã dừng.

Với executor:

- Dừng nhận task mới trước khi đóng loader.
- Chờ hoặc hủy tác vụ cũ theo hợp đồng của hệ thống.
- Dọn các ThreadLocal và TCCL do plugin/caller đã đặt.
- Đảm bảo tác vụ tiếp theo không tiếp tục sử dụng class/resource của plugin đã đóng.
- Không giả định việc đổi TCCL trong thread submit task tự đổi TCCL của tất cả worker tồn tại từ trước.

**Không xóa TCCL bằng `setContextClassLoader(null)` một cách tùy tiện.** Trạng thái trước có thể là loader của host hoặc container; phải restore **đúng giá trị cũ**.

## 11. Close và quyền truy cập tệp JAR trên Windows/Linux

Trên Windows, một JAR còn bị giữ handle có thể không đổi tên/ghi đè/xóa được. Trên Unix, file có thể unlink khi descriptor còn mở, nhưng descriptor vẫn tiêu thụ tài nguyên cho tới khi được đóng. `URLClassLoader.close()` cố đóng những handle của **chính loader đó**; một `JarFile`, stream, IDE hoặc tiến trình khác có thể tiếp tục giữ file.

Khi thay plugin, trước hết ngừng việc đang chạy, dọn callback/tài nguyên, gọi `close()` và xử lý `IOException`, rồi triển khai artifact mới. Khả năng xóa file sau close không chứng minh JVM đã unload class.

## 12. Mở loader mới không tự làm cùng tên class trở thành cùng kiểu

Hai `URLClassLoader` **tự định nghĩa** `demo.Greeter` tạo hai runtime types, dù binary name và bytecode giống nhau. Đóng loader cũ không biến instance hoặc `Class<?>` cũ thành định nghĩa của loader mới; host không được tự cast implementation giữa hai thế hệ.

Đặt shared API/DTO ở parent chung, implementation ở loader riêng theo thế hệ; kiểm tra `type.getClassLoader()` trong test reload. Nếu parent định nghĩa luôn implementation thì parent-first có thể che bản mới.

## 13. Theo dõi, debug và xác nhận cleanup

### 13.1. Dấu hiệu tài nguyên chưa được giải phóng

- JAR không thể được thay thế/xóa sau khi plugin stop.
- Số lượng open file descriptors tăng theo mỗi lần reload plugin.
- Sau nhiều lần redeploy, memory dành cho class metadata/metaspace hoặc số lượng class loader instance tăng.
- Threads của plugin tiếp tục chạy sau stop.
- Task mới không tìm được class/resource vì loader đã bị close quá sớm.
- `ClassNotFoundException` chỉ xảy ra khi lần đầu đi vào một tính năng ít dùng sau giai đoạn start plugin.

Đừng kết luận chỉ từ một triệu chứng: JAR lock có thể do nơi khác giữ; metaspace tăng có thể do nhiều nguyên nhân; class unloading không cần xảy ra ngay khi một loader đã không còn được tham chiếu.

### 13.2. Dùng công cụ JVM

Với HotSpot JDK có hỗ trợ unified logging, có thể quan sát class load/unload bằng:

```bash
java -Xlog:class+load=info,class+unload=info -cp . LoaderLifecycleDemo
```

Log có thể dài, phiên bản JDK khác nhau có định dạng khác nhau, và một run ngắn **không bắt buộc** ghi nhận class unloading. Không dùng việc thiếu dòng unload làm bằng chứng chắc chắn rằng `close()` thất bại.

Công cụ như `jcmd <pid> VM.classloader_stats` (nếu JDK/VM cung cấp) và thread dump giúp khảo sát các loader/threads còn sống, nhưng cần diễn giải trong bối cảnh GC và ứng dụng thực tế. Không tự động gọi `System.gc()` liên tục làm giải pháp vận hành để “đóng loader”.

### 13.3. Kiểm chứng close trong test

Một unit/integration test hữu ích nên phân tách các điều cần kiểm:

1. **Loaded before close:** load class plugin, xác minh defining loader.
2. **Closed resource path:** khi test không có race hoặc cache ngoài, các class mới của plugin không được loader cũ định nghĩa nữa.
3. **Parent delegation:** class chuẩn do parent/bootstrap định nghĩa vẫn dùng được.
4. **Cleanup:** executor, callbacks, streams được dừng/đóng và TCCL restore.
5. **Reload:** loader mới dùng JAR mới; API chung vẫn duy trì đúng runtime identity.
6. **Failure path:** throw exception khi đang dùng plugin; kiểm tra close vẫn được gọi; nếu close lỗi, suppressed exceptions được giữ.

Test **không nên** assert JVM phải unload class ngay sau `close()` hoặc ngay sau `System.gc()`: đó không phải bảo đảm portable.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách làm đúng |
|---|---|---|
| Không đóng loader sau job hữu hạn | JAR/files có thể bị giữ mở | Dùng try-with-resources hoặc lifecycle close rõ ràng |
| Đóng ngay sau khi load entry-point nhưng plugin còn chạy | Lazy dependency/resource load có thể thất bại | Giữ loader sống suốt thời gian plugin hoạt động |
| Coi close như “xóa class” | Sử dụng sai định danh/vòng đời, kỳ vọng unload vô căn cứ | Phân biệt close, stop, dereference, GC |
| Vừa close vừa có thread nạp class | Kết quả nạp không được xác định | Stop/await quiescence trước close |
| Gọi `loadClass` lại trên loader cũ để lấy phiên bản mới | Nhận lại `Class<?>` đã nạp hoặc CNFE | Tạo defining loader mới, thiết kế migration |
| Quên restore TCCL ở thread pool | Nhầm provider, rò rỉ ClassLoader | `try/finally` restore giá trị trước |
| Chỉ đóng loader, không đóng stream/socket/executor plugin | Rò rỉ tài nguyên và thread | Cleanup toàn bộ plugin-owned resources |
| Nuốt `IOException` khi close | Che lỗi file handle, khó chẩn đoán | Log/propagate và xem suppressed exceptions |
| Chỉ chạy test trên Linux rồi suy ra Windows thay JAR được | File handle khác nhau theo OS | Test file lifecycle trên môi trường triển khai |
| Mở JAR qua `JarFile` hoặc `JarURLConnection` ngoài loader rồi kỳ vọng loader đóng giúp | Vẫn còn handle khác | Đóng tài nguyên ở đúng owner |
| Đưa loader vào static cache lâu sống | Loader/class metadata không giải phóng | Quản lý cache theo phiên plugin, loại bỏ khi stop |

## 15. Checklist thiết kế vòng đời URLClassLoader

Trước khi tạo loader:

- Xác định **ai sở hữu URLClassLoader** và **khi nào kết thúc vòng đời**.
- Xác định các URL có thể trỏ tới JAR/directory nào và có cần isolation giữa các plugin không.
- Đặt API chung ở parent loader thích hợp để tránh class identity conflict.

Trong lúc plugin đang hoạt động:

- Không đóng loader trong khi vẫn còn công việc cần nạp class/resource từ nó.
- Quản lý stream, JDBC connection, sockets, executor, listener, timer và cache do plugin mở/tạo.
- Nếu cần TCCL, set/restore đúng phạm vi sử dụng.

Khi dừng:

- Dừng tiếp nhận task mới; chờ các task đang hoạt động đạt trạng thái an toàn.
- Hủy đăng ký callback/listener, tắt executor, đóng tài nguyên của plugin.
- Restore TCCL và xóa reference từ host caches nếu có.
- Gọi `URLClassLoader.close()`, xử lý `IOException` và suppressed failures.
- Bỏ các reference không còn cần, nhưng **không giả định GC/unload xảy ra lập tức**.

Khi reload:

- Tạo **URLClassLoader mới** cho thế hệ mới.
- Giữ boundary API chung rõ ràng, không trộn class implementation giữa hai loaders.
- Kiểm tra cả hành vi hoạt động và giải phóng tệp/classloader trong integration tests.

## 16. Câu hỏi tự kiểm tra

1. **URLClassLoader triển khai interface nào để dùng trong try-with-resources?** `Closeable`, đồng thời là `AutoCloseable`.
2. **`close()` có ngăn việc loader tự nạp class mới từ URL của nó không?** Có, theo hợp đồng URLClassLoader.
3. **Một class đã nạp có biến mất sau close không?** Không; class đã loaded và object hiện có vẫn có thể truy cập.
4. **Sau close, parent loader có thể vẫn cung cấp `java.lang.String` không?** Có.
5. **`loader.loadClass("demo.Greeter")` sau close có luôn thất bại không?** Không; nếu loader đã initiated class đó, nó có thể trả class cũ.
6. **Có nên tiếp tục chạy plugin sau close chỉ vì một method cũ vẫn gọi được không?** Không; dependency/resource được nạp muộn có thể không còn sẵn.
7. **`close()` có chờ tất cả threads đang nạp class hoàn tất không?** Không có bảo đảm; việc close đồng thời với class loading có kết quả không xác định.
8. **Nếu thân try và close cùng ném exception, exception nào là chính?** Exception trong thân try; close exception được giữ như suppressed.
9. **Gọi close hai lần với URLClassLoader đã đóng có phá hỏng loader không?** Không; lần sau không có tác dụng theo hợp đồng.
10. **Vì sao plugin không unload dù đã close?** Có thể còn strong references từ TCCL, ThreadLocal, cache, callback, Class object hoặc instance.
11. **Thay plugin.jar rồi gọi loadClass từ loader cũ có tạo class mới không?** Không tự tạo; cần loader/runtime class thế hệ mới theo kiến trúc reload.
12. **Với plugin sống lâu, nên đặt try-with-resources ở phạm vi nào?** Bao quanh toàn bộ vòng đời plugin, sau khi công việc đã được dừng và tài nguyên plugin được dọn.
13. **`URLClassLoader.close()` có tự đóng mọi `JarFile` do toàn ứng dụng mở không?** Không; chỉ những file/tài nguyên mà loader chịu trách nhiệm theo API.
14. **Vì sao một JVM test không thấy log class unload dù close thành công?** Unloading do GC, không bắt buộc diễn ra ngay sau close.

## Tài liệu tham khảo chính thức

- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): `Closeable`, `close()`, class/resource access sau close, hành vi lỗi/concurrency và `getResourceAsStream`.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): API tương thích ví dụ Java 17 trong bài.
- [Java SE 21 — AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng đóng tài nguyên.
- [Java Language Specification — `14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3): thứ tự đóng và suppressed exceptions.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `findLoadedClass` và cách nạp class.
- [Java Virtual Machine Specification — `5.3–5.5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): class loading, defining loader, linking và initialization.

**Kết luận:** **`close()` đóng nguồn I/O của URLClassLoader, chứ không “đóng” các class Java đã tồn tại.** Dùng **try-with-resources** khi biết rõ phạm vi sở hữu loader; với plugin sống lâu, dùng một lifecycle manager để **stop → cleanup → close → bỏ references**. Phân biệt bốn bước này giúp tránh JAR bị giữ mở, lỗi nạp dependency sau khi đóng và rò rỉ classloader khi redeploy.

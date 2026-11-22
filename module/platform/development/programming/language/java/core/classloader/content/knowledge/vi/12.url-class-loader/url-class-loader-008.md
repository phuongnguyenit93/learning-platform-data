# Ảnh hưởng của close tới JAR handle và thao tác tải đang diễn ra

## 1. Vì sao `URLClassLoader.close()` quan trọng?

Một `URLClassLoader` có thể tải class và tài nguyên từ một hoặc nhiều thư mục/JAR. Khi plugin, module mở rộng hoặc bộ công cụ nạp động không còn được sử dụng, ứng dụng thường muốn giải phóng tài nguyên liên quan tới các JAR đó. Java cung cấp:

~~~java
URLClassLoader loader = new URLClassLoader(urls, parent);
loader.close();
~~~

`URLClassLoader` triển khai `Closeable`/`AutoCloseable` và có phương thức `public void close() throws IOException`. Theo tài liệu Java 17, `close()` làm loader **không còn sử dụng được để tải class hay resource mới do chính loader ấy định nghĩa/tìm từ đường URL của nó**, đồng thời đóng các tệp đã được nó mở cho các URL kiểu `jar:` và `file:`. Các class đã được nạp vẫn có thể truy cập; class/resource từ **parent** vẫn có thể được yêu cầu thông qua delegation.

Hai ý phải học cùng nhau:

- **Đóng nguồn tải ≠ xóa class đã nạp.** JVM không “quay ngược” việc định nghĩa class khi `close()` được gọi.
- **Đóng loader ≠ bảo đảm mọi tác vụ đang chạy đã kết thúc.** Nếu thread khác đang nạp class lúc `close()` xảy ra, đặc tả API nói **kết quả của lần nạp ấy không được xác định**. Không được dựa vào race đó để triển khai hot reload.

Trong bài này, “JAR handle” là các tệp/cấu trúc I/O được loader mở để đọc JAR; nó **không** phải mọi tham chiếu object/class và cũng không đồng nghĩa JVM giải phóng toàn bộ bộ nhớ gắn với plugin.

## 2. Trước và sau `close()`: bảng hành vi

Giả sử `child` là `URLClassLoader` có URL tới `plugin.jar`; parent không chứa các class/resource riêng của plugin.

| Thao tác | Khi loader còn mở | Sau `child.close()` |
|---|---|---|
| Nạp class chưa từng được child nạp từ `plugin.jar` | Có thể thành công nếu bytecode hợp lệ | Không thể trông chờ child tìm/định nghĩa class mới từ URL của nó; `loadClass` thường ném `ClassNotFoundException` |
| Dùng instance của class đã được định nghĩa | Hoạt động theo chương trình | Vẫn có thể hoạt động nếu không cần thêm class/resource bị thiếu |
| Gọi `loadClass` cho class đã được loader ghi nhận là đã nạp | Trả class đã biết | Có thể trả lại chính class đã nạp, theo đường kiểm tra `findLoadedClass` |
| Nạp class do parent định nghĩa, ví dụ `java.lang.String` | Delegation tới parent/bootstrap | Parent vẫn có thể tìm/đưa lại class đó |
| `findResource` / `findResources` cho resource chỉ trong plugin JAR | Tìm theo đường URL của child | Tương ứng không tìm thấy hoặc không có phần tử mới từ đường URL đó |
| `getResource` qua child | Hỏi parent trước, rồi nguồn child | Parent vẫn có thể trả resource của nó; nguồn child đã đóng không còn là nguồn tra cứu mới |
| Đọc `InputStream` do `URLClassLoader.getResourceAsStream` mở | Đọc được khi stream/loader còn hợp lệ | Loader đóng các stream mà phương thức này đã mở; không tiếp tục dùng chúng |
| Đổi tên/xóa JAR trên đĩa | Có thể bị file handle của loader hoặc thành phần khác cản trở | Loader cố gắng nhả handle của **nó**; kết quả thao tác file còn phụ thuộc OS và handle khác |
| Class unloading | Phụ thuộc vòng đời object/classloader | **Không tự động xảy ra chỉ vì close** |

Không nên biến bảng thành cam kết mọi hoạt động sau `close()` đều luôn thất bại: class đã nạp và class của parent vẫn có thể truy cập; việc một instance chạy tiếp còn phụ thuộc vào các dependency mà bytecode có thể cần nạp **lần đầu** ở thời điểm chạy sau đó.

## 3. Vòng đời cơ bản của JAR và nguồn class

`URLClassLoader` nhận mảng `URL[]`, ví dụ:

~~~java
URL[] urls = {Path.of("plugins/hello.jar").toUri().toURL()};
ClassLoader parent = Host.class.getClassLoader();
// Mã minh họa: cần class Host và các import phù hợp.
URLClassLoader loader = new URLClassLoader(urls, parent);
~~~

Nó thường mở JAR **khi cần** đọc class hoặc resource, không phải bắt buộc mở mọi JAR ngay lúc constructor chạy. Sau khi có JAR handle, một số runtime/cấu hình có thể giữ nguồn đó mở để phục vụ các lookup tiếp theo.

~~~text
Tạo URLClassLoader
       |
       v
Chưa cần mở tất cả JAR
       |
       v
loadClass / getResource
       |
       v
Mở JAR khi cần, đọc bytecode hoặc resource
       |
       v
Class đã định nghĩa; JAR handle có thể đang được giữ
       |
       v
close()
  ├─ Ngừng khả năng tìm class/resource mới từ URL riêng
  ├─ Cố đóng các file/JAR handle đã mở bởi loader
  └─ Giữ nguyên class đã định nghĩa và parent loader

Class unloading: quá trình khác, không phải thao tác close trực tiếp.
~~~

Hệ quả thực tế: nếu một ứng dụng cập nhật JAR plugin, nên **ngừng tác vụ đang dùng plugin**, đóng loader cũ và các resource còn sử dụng, rồi tạo **loader mới** cho phiên bản mới. Chỉ thay bytecode của JAR trên đĩa không đổi nội dung của `Class<?>` đã được JVM định nghĩa bởi loader cũ.

## 4. Ví dụ Java 17+ hoàn chỉnh: class đã nạp, class mới và resource sau close

Thí nghiệm sẽ tạo một JAR với:

- `demo.plugin.Early`: class được nạp **trước** khi đóng.
- `demo.plugin.Late`: class **chưa nạp** lúc đóng.
- `plugin/data/label.txt`: resource chỉ thuộc JAR của child.

Host nạp bằng `URLClassLoader` qua reflection để **không** vô tình đặt class plugin lên application classpath.

### 4.1. Cấu trúc dự án

~~~text
close-demo/
├── host-src/
│   └── CloseDemo.java
├── plugin-src/
│   └── demo/plugin/
│       ├── Early.java
│       └── Late.java
└── plugin-resources/
    └── plugin/data/
        └── label.txt
~~~

File `plugin-resources/plugin/data/label.txt` chứa đúng dòng:

~~~text
FROM_JAR
~~~

Khi biên dịch, output được chia thành `build/host` và `build/plugin`, sau đó đóng một JAR tại `dist/plugin.jar`. Chỉ `build/host` nằm trong `-cp` lúc chạy chương trình.

### 4.2. Class plugin đã nạp sớm

File **`plugin-src/demo/plugin/Early.java`**:

~~~java
package demo.plugin;

public final class Early {
    public Early() {
    }

    public String message() {
        return "EARLY_OK";
    }
}
~~~

Method `message()` chỉ trả một string literal, không cần resolve thêm class implementation khác thuộc plugin. Điều này quan trọng: khi gọi method sau `close()`, ta chủ động tránh trường hợp method tự yêu cầu class mới từ JAR đã đóng.

### 4.3. Class chỉ nạp nếu được yêu cầu muộn

File **`plugin-src/demo/plugin/Late.java`**:

~~~java
package demo.plugin;

public final class Late {
    public Late() {
    }

    public String message() {
        return "LATE_OK";
    }
}
~~~

Host **không gọi `loadClass("demo.plugin.Late")` trước khi đóng loader**. Khi loader đã đóng, lookup mới từ JAR của child sẽ không thành công.

### 4.4. Host điều khiển thời điểm close

File **`host-src/CloseDemo.java`**:

~~~java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class CloseDemo {
    private CloseDemo() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: CloseDemo <path-to-plugin.jar>");
        }

        Path jar = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException("Plugin JAR not found");
        }

        URL[] urls = {jar.toUri().toURL()};
        ClassLoader parent = CloseDemo.class.getClassLoader();

        try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
            Class<?> earlyClass = loader.loadClass("demo.plugin.Early");
            Object earlyObject =
                    earlyClass.getConstructor().newInstance();

            System.out.println("Before close: "
                    + earlyClass.getMethod("message").invoke(earlyObject));

            try (InputStream in =
                         loader.getResourceAsStream("plugin/data/label.txt")) {
                if (in == null) {
                    throw new IllegalStateException("Missing resource");
                }
                System.out.println("Resource before close: "
                        + new String(
                                in.readAllBytes(),
                                StandardCharsets.UTF_8).strip());
            }

            // Đóng nguồn tải trước khi thử các lookup tiếp theo.
            loader.close();

            System.out.println("Existing object after close: "
                    + earlyClass.getMethod("message").invoke(earlyObject));

            System.out.println("Already loaded Class identity: "
                    + (loader.loadClass("demo.plugin.Early") == earlyClass));

            boolean lateUnavailable;
            try {
                loader.loadClass("demo.plugin.Late");
                lateUnavailable = false;
            } catch (ClassNotFoundException expected) {
                lateUnavailable = true;
            }
            System.out.println("Late class unavailable: "
                    + lateUnavailable);

            System.out.println("Own resource unavailable: "
                    + (loader.getResource("plugin/data/label.txt") == null));

            System.out.println("Parent String available: "
                    + (loader.loadClass("java.lang.String") == String.class));

            // close() gọi lần thứ hai không gây tác dụng mới.
            loader.close();
            System.out.println("Second close completed");
        }
    }
}
~~~

**Tại sao vừa `try-with-resources` vừa gọi `close()` tường minh?** Vì thí nghiệm phải quan sát các lookup *ngay sau thời điểm đóng*. `try-with-resources` vẫn đảm bảo cleanup nếu có exception trước khi đến lời gọi `close()`. Sau khi rời khối, Java gọi `close()` lần nữa; API quy định đóng loader đã đóng là thao tác không có hiệu lực.

**Tại sao không giữ `InputStream` rồi thử đọc sau close?** `URLClassLoader.getResourceAsStream` có đặc điểm tài liệu hóa: những stream mà loader đã mở qua phương thức này sẽ được đóng khi loader đóng. Đọc sau close là không an toàn và thông báo lỗi cụ thể phụ thuộc stream/URL implementation. Vì vậy ví dụ đọc và đóng stream **trước** loader.close().

### 4.5. Biên dịch, đóng gói và chạy

Dùng **JDK 17 trở lên**, mở terminal tại thư mục `close-demo/` có đầy đủ file.

**Bash (Linux, macOS, Git Bash):**

~~~bash
mkdir -p build/host build/plugin dist

javac -encoding UTF-8 \
  -d build/plugin \
  plugin-src/demo/plugin/Early.java \
  plugin-src/demo/plugin/Late.java

javac -encoding UTF-8 \
  -d build/host host-src/CloseDemo.java

jar --create --file dist/plugin.jar \
  -C build/plugin . \
  -C plugin-resources .

java -cp build/host CloseDemo dist/plugin.jar
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/host,build/plugin,dist | Out-Null

javac -encoding UTF-8 -d build/plugin plugin-src/demo/plugin/Early.java plugin-src/demo/plugin/Late.java

javac -encoding UTF-8 -d build/host host-src/CloseDemo.java

jar --create --file dist/plugin.jar -C build/plugin . -C plugin-resources .

java -cp build/host CloseDemo dist/plugin.jar
~~~

Đảm bảo JAR có ba entry:

~~~text
demo/plugin/Early.class
demo/plugin/Late.class
plugin/data/label.txt
~~~

Có thể kiểm tra bằng `jar --list --file dist/plugin.jar`; JAR còn có thể chứa manifest và entry thư mục.

**Stdout kỳ vọng trên Java 17+ với URLClassLoader chuẩn:**

~~~text
Before close: EARLY_OK
Resource before close: FROM_JAR
Existing object after close: EARLY_OK
Already loaded Class identity: true
Late class unavailable: true
Own resource unavailable: true
Parent String available: true
Second close completed
~~~

Phần sau `close()` minh họa ba ranh giới: **class đã nạp vẫn dùng được**, **URL của child không còn là nguồn tải class/resource mới**, **parent vẫn có thể cung cấp class**.

Đừng sửa cách chạy thành `java -cp "build/host:dist/plugin.jar" ...`. Khi plugin JAR đã nằm trong classpath của parent, `parent-first delegation` có thể nạp `Late` qua parent, làm kết quả demo không còn đại diện cho loader con đã đóng.

## 5. Điều gì vẫn hoạt động sau khi close?

### 5.1. Class đã nạp không bị “hủy”

`Class<?>`, reflection metadata và instance đã tạo trước `close()` vẫn có thể được dùng nếu không cần tìm thêm class/resource từ URL đã đóng. Thực nghiệm `Early.message()` chỉ trả literal để minh họa điều đó. Một method khác có thể thất bại khi lần đầu cần lazy dependency sau close; vì thế không tiếp tục phục vụ plugin qua loader đã đóng.

### 5.2. Parent vẫn là nguồn hợp lệ

`loader.loadClass("java.lang.String")` vẫn có thể thành công nhờ bootstrap/parent. Resource do parent sở hữu cũng có thể tìm thấy; không suy rằng mọi `loadClass` hay `getResource` sau close đều thất bại.

### 5.3. Không nhầm với JVM class unloading

Đóng handle I/O không loại bỏ `Class<?>` hoặc ép GC. Host cache, listener, TCCL hay task còn sống có thể giữ defining loader reachable; unloading do JVM quyết định khi đủ điều kiện.

## 6. JAR handle: tại sao Windows và Linux có thể khác nhau?

Khi `URLClassLoader` mở một JAR, có thể tồn tại handle/descriptor tới tệp đó. Trên một số hệ điều hành, đặc biệt Windows, handle đang mở có thể khiến thao tác **đổi tên, ghi đè hoặc xóa** tệp JAR bị từ chối. Trên nhiều filesystem kiểu Unix, có thể unlink/rename trong khi process vẫn giữ handle, nhưng nội dung bytecode/nguồn đọc còn dùng bởi tiến trình không tự đồng nhất với file mới trên đĩa.

Khi gọi `close()`:

1. Loader cố đóng những file mà **nó đã mở** qua đường `jar:`/`file:`.
2. Tài nguyên OS gắn với những file ấy có thể được nhả.
3. Ứng dụng có thể thử thay JAR an toàn hơn, **sau khi đã ngừng tác vụ sử dụng loader**.
4. Không có bảo đảm file sẽ lập tức đổi tên/xóa được: loader khác, `JarFile` khác, `InputStream` khác, tiến trình khác hoặc antivirus/file scanner vẫn có thể giữ handle.

**Không kiểm thử close bằng cách mặc định chạy `Files.delete(pluginJar)` và đòi kết quả giống hệt trên mọi OS.** Hãy quan sát file handles bằng công cụ hệ điều hành khi cần, nhưng lấy Javadoc làm contract về việc loader đóng các file do nó mở.

Một URL cũ từ `loader.getResource(name)` cũng không phải “con trỏ an toàn có thể đọc mãi” sau close. Nếu caller dùng `url.openStream()`, nó có thể mở **một kết nối mới** theo URL handler; điều này là hành vi riêng của URL/resource, không chứng minh loader chưa đóng. Vì vậy không dùng khả năng đọc lại URL cũ làm kiểm tra tính đóng của `URLClassLoader`.

## 7. Nếu thread khác đang tải class khi close thì sao?

Đây là giới hạn quan trọng nhất của bài học. Javadoc Java 17 quy định nếu **một thread đang thực hiện việc tải class** khi thread khác gọi `close()` trên cùng `URLClassLoader`, kết quả của lần tải đó là **không xác định**.

~~~text
Thread A                                Thread B
────────                                ────────
loader.loadClass("plugin.NewType")
   đang đọc/liên kết class
        │                                    │
        └──────────── giao nhau ─────────> loader.close()
                                             │
                                      đóng nguồn JAR
        │                                    │
   kết quả load không được API bảo đảm
~~~

Không nên dự đoán cứng một loại kết quả:

- Không thể khẳng định luôn ném `ClassNotFoundException`.
- Không thể khẳng định luôn hoàn tất thành công.
- Không thể khẳng định cứ đồng bộ hóa `close()` và `loadClass()` bằng một `synchronized` tùy ý ở caller là đủ cho mọi code/library trong hệ thống: còn có thread và API khác dùng loader.
- Không nên tạo race thử nghiệm rồi coi một lần chạy “thành công” là bằng chứng lifecycle đúng.

**Mẫu thiết kế an toàn:** Không gọi `close()` khi hệ thống vẫn có thể phát sinh thao tác nạp class/resource mới từ loader ấy. Muốn đóng loader, trước hết phải **chặn yêu cầu mới và đợi mọi tác vụ phụ thuộc loader hoàn thành**.

## 8. Trình tự ngừng plugin đúng cách

Một host có thể tổ chức vòng đời như sau:

~~~text
RUNNING
   |
   | 1. Chặn request mới gửi tới plugin
   v
DRAINING
   |
   | 2. Đợi các request/task đang dùng plugin kết thúc
   | 3. Gỡ listener/callback/scheduler, ngừng thread riêng
   | 4. Đóng stream, socket, JarFile và resource do plugin mở
   v
QUIESCED
   |
   | 5. Khôi phục TCCL và gỡ mọi tham chiếu host giữ tới loader cũ
   | 6. Gọi oldLoader.close() để nhả các file/JAR handle của loader
   v
CLOSED
   |
   | 7. Thay JAR và tạo loader MỚI để nạp plugin phiên bản mới
   v
RUNNING với plugin mới
~~~

Thứ tự `5` và `6` còn tùy thiết kế: lúc đóng loader, host phải còn một tham chiếu tới `oldLoader` để gọi `close()`; sau khi đóng mới nên loại bỏ tham chiếu cuối cùng. Điều bất biến là **không để loader đóng khi vẫn có task có thể cần nạp thêm class/resource qua nó**.

### Một ví dụ đồng bộ hóa ở cấp ứng dụng

Một mô hình đơn giản trong đó host điều khiển toàn bộ task:

~~~java
// Mã minh họa, không phải file chạy độc lập.
// Các hàm/phạm vi này là contract do ứng dụng tự cung cấp.
stopAcceptingNewTasks();
waitForInFlightTasksToFinish();
unregisterPluginCallbacks();
closePluginOwnedResources();
restoreOrClearThreadContextLoaders();
oldLoader.close();
oldLoader = null;
~~~

Nếu dùng `ExecutorService`, `shutdown()` chỉ có nghĩa **không nhận task mới**; bản thân lệnh đó không đợi task hoàn thành. Cần kết hợp `awaitTermination(...)`, `Future.get()` hoặc cơ chế đếm in-flight phù hợp. Nếu chờ quá hạn, **không được mặc nhiên đóng loader** khi task vẫn có khả năng sử dụng nó; chuyển sang quy trình xử lý timeout/cancel và xác nhận quiescence.

Ngoài method đang thực thi, một task có thể sử dụng:

- `Class.forName(name, true, pluginLoader)`, reflection hoặc dynamic proxies cần class mới.
- `ServiceLoader` có cơ chế discovery/lazy provider initialization.
- `pluginLoader.getResources(...)` hoặc `getResourceAsStream(...)`.
- Dynamic bytecode generation, class annotation scanning, framework dependency injection.
- Thread context class loader (`TCCL`) trỏ tới plugin loader.

Vì vậy việc “không thấy method plugin nào đang chạy” chưa đủ nếu vẫn còn task hoặc lazy-loading từ code khác.

## 9. `try-with-resources`, idempotence và lỗi close

`URLClassLoader` triển khai `AutoCloseable`, do đó có thể viết:

~~~java
try (URLClassLoader loader =
             new URLClassLoader(urls, parent)) {
    // Nạp và sử dụng plugin trong phạm vi này.
}
// loader.close() được gọi tự động.
~~~

Đây là **đoạn mã minh họa** dùng biến `urls` và `parent` được chuẩn bị trước. Trong môi trường thực tế, chỉ dùng `try-with-resources` nếu **mọi tác vụ cần loader kết thúc trước khi rời block**. Nếu plugin phải tồn tại qua nhiều request, giữ loader theo vòng đời plugin và đóng trong phase shutdown đã điều phối.

Một vài tính chất theo tài liệu:

- Gọi `close()` nhiều lần: nếu loader đã đóng, lời gọi sau không có tác dụng.
- `close()` có thể ném `IOException`. JVM cố đóng tất cả tệp đã mở, bắt các `IOException` trong quá trình đó; nếu có nhiều `IOException`, các lỗi sau được thêm vào danh sách **suppressed exceptions** của lỗi đầu.
- `close()` không bắt mọi `RuntimeException` hoặc `Error`.
- Với runtime còn sử dụng `SecurityManager` và policy tương ứng, có thể phát sinh `SecurityException` nếu thiếu quyền đóng classloader.
- Trong `try-with-resources`, nếu thân `try` và thao tác close cùng ném lỗi, lỗi close có thể được **suppressed** vào lỗi chính theo ngữ nghĩa `try-with-resources`.

**Đừng bỏ qua IOException của close.** Nó báo có ít nhất một việc đóng file không thành công; cần log, theo dõi handle còn lại và quyết định có thể cập nhật JAR an toàn hay chưa.

Mẫu xử lý lỗi minh họa:

~~~java
// Mã minh họa; không phải chương trình độc lập.
try {
    quiescePlugin();
} finally {
    try {
        loader.close();
    } catch (IOException ex) {
        // Log đầy đủ ex và ex.getSuppressed().
        reportCloseFailure(ex);
    }
}
~~~

Mẫu này chỉ có ý nghĩa nếu `quiescePlugin()` thực sự đạt trạng thái không còn công việc sử dụng loader. Không dùng `finally` như lý do để đóng loader khi task vẫn chạy.

## 10. Đóng stream và URL resource đúng thời điểm

Có ít nhất ba tầng tài nguyên cần phân biệt:

| Tầng | Ví dụ | Ai chịu trách nhiệm đóng? |
|---|---|---|
| ClassLoader | `URLClassLoader` | Host/plugin lifecycle manager gọi `close()` |
| Resource stream | `InputStream` từ `getResourceAsStream` | Caller đóng càng sớm càng tốt; URLClassLoader cũng đóng các stream do chính method này mở khi loader.close() |
| Tài nguyên riêng của plugin | `JarFile` tự mở, socket, thread, executor, JDBC pool | Code sở hữu tạo/chịu trách nhiệm đóng hoặc shutdown |

**Không coi `loader.close()` là thay thế cho mọi `try-with-resources` trong ứng dụng.** Ví dụ, nếu code plugin tự tạo `new JarFile(...)` độc lập, loader không có nghĩa vụ biết và đóng nó.

Cũng không nên giữ stream mở rồi đóng loader ngay lập tức:

~~~java
// Mã minh họa chống mẫu nguy hiểm.
InputStream stream = loader.getResourceAsStream("plugin/config.txt");
loader.close();
// Không đọc stream tại đây: loader có thể đã đóng stream đó.
~~~

Cách đúng là hoàn thành việc đọc trước khi đóng loader:

~~~java
// Mã minh họa; loader còn mở trong khối.
try (InputStream in = loader.getResourceAsStream("plugin/config.txt")) {
    if (in != null) {
        byte[] bytes = in.readAllBytes();
        // Xử lý bytes.
    }
}
// Sau khi mọi thao tác dùng loader kết thúc, mới close loader.
~~~

Vì resource đọc từ JAR có thể sử dụng cache/file handle riêng của URL handler, không nên suy đoán chính xác thời điểm hệ điều hành nhả mọi file descriptor chỉ từ việc đối tượng `URL` còn tồn tại.

## 11. Khác biệt giữa reload class và reload plugin

Thay `dist/plugin.jar` khi loader cũ đã định nghĩa `demo.plugin.Early` không thay bytecode hoặc runtime `Class<?>` của định nghĩa ấy. Loader **mới** có thể định nghĩa cùng tên thành runtime type mới. Quy trình chuyển plugin cần dừng và drain v1, đóng tài nguyên, triển khai JAR đã kiểm chứng, khởi tạo loader v2 và chỉ chuyển request sang v2 khi đã sẵn sàng.

Trong giai đoạn hai thế hệ cùng hoạt động, quản lý riêng task/callback/loader. Đừng đóng loader v1 trong lúc task còn có thể cần lazy loading.

## 12. Liên hệ với parent delegation và class identity

`URLClassLoader` dùng parent-first mặc định. `loadClass("java.lang.String")` qua loader đã đóng vẫn có thể trả class bootstrap; ngược lại `loadClass("demo.plugin.Late")`, nếu chỉ có trong JAR child và chưa load, không thể định nghĩa mới từ URL đã đóng. Trong test, tránh đặt JAR plugin lên parent application classpath vì parent có thể che mất tình huống cần đo.

Hai loader tự định nghĩa cùng binary name tạo hai runtime types khác nhau. Chia sẻ interface/DTO từ parent và quan sát defining loader qua `Class.getClassLoader()` khi giao tiếp giữa các thế hệ.

## 13. Chẩn đoán sự cố close/JAR handle

| Dấu hiệu | Giải thích có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Windows báo JAR đang được sử dụng | Một loader, `JarFile`, stream hoặc tiến trình vẫn giữ file handle | Quiesce plugin, đóng mọi nguồn; kiểm tra handle qua công cụ OS |
| `loadClass` cho plugin class mới thất bại sau close | Loader không còn tìm từ URL riêng | Tạo loader mới khi cần nạp phiên bản mới |
| Object plugin cũ vẫn chạy sau close | Class đã nạp còn reachable | Hành vi hợp lệ nếu không cần thêm dependency/resource |
| Method cũ lỗi khi lần đầu dùng dependency mới | Dependency chưa được child nạp trước close | Không đóng trước khi plugin thật sự kết thúc; đừng giả định toàn bộ dependency eager-loaded |
| `ClassNotFoundException` khi parent không có class | Sau close không thể tìm class mới từ child URL | Kiểm tra nguồn class và trạng thái loader |
| Một lần race close/load vẫn thành công | Kết quả khi đồng thời tải class và close là không xác định | Không lấy làm contract; điều phối dừng và đợi task |
| `getResourceAsStream` đọc lỗi sau close | Stream do loader mở đã bị đóng | Đọc và đóng stream trước `loader.close()` |
| `close()` ném `IOException` | Có file không đóng được | Log nguyên exception và suppressed exceptions; xem tình trạng handle |
| Plugin cũ không unload dù đã close | Host/thread/cache còn tham chiếu | Dọn callback, TCCL, ThreadLocal, executor, object/plugin reference |
| Có thể mở lại URL cũ | URL handler có thể tạo kết nối mới độc lập | Không coi đọc URL cũ là bằng chứng URLClassLoader còn mở |
| Dùng `URLClassLoader` trong try-with-resources rồi trả task bất đồng bộ | Scope kết thúc trước khi async task dùng loader xong | Chuyển ownership loader vào manager và đóng sau khi tasks kết thúc |

### Gợi ý quan sát môi trường

Trên Java 17, các lệnh có thể hỗ trợ phân tích class loading (các giá trị cụ thể phụ thuộc JVM và cấu hình):

~~~bash
java -Xlog:class+load=info -cp build/host CloseDemo dist/plugin.jar
~~~

Output logging JVM chứa nhiều dòng và không ổn định về thứ tự/đường dẫn, vì vậy **không** xem nó như stdout chuẩn của ví dụ. Với sự cố file locks, các công cụ hệ điều hành như Process Explorer (Windows) hoặc `lsof` (Unix-like) có thể giúp tìm tiến trình/file descriptor đang giữ JAR. Không tùy tiện xóa JAR đang được tiến trình sử dụng để “ép unload”.

## 14. Các tình huống cần tránh trong thiết kế

**Tránh 1: đóng ngay khi nhấn “disable plugin” nhưng task vẫn chạy.** Disable nên chặn công việc mới rồi đợi drain; không đồng nghĩa mọi thread đã xong.

**Tránh 2: đóng loader trong `finally` của mỗi request.** Nếu loader được chia sẻ qua nhiều request, request A có thể đóng tài nguyên khi request B đang tải class. Owner của loader phải là **plugin lifecycle manager**, không phải một request bất kỳ.

**Tránh 3: cho rằng `URLClassLoader.close()` là cơ chế reload.** Nó chỉ đóng nguồn/giải phóng handle, không tải bytecode mới vào runtime class cũ.

**Tránh 4: coi `close()` đảm bảo mọi JAR có thể xóa trên mọi hệ điều hành.** Có thể còn descriptor/handle từ thành phần khác.

**Tránh 5: tìm cách bắt `ClassNotFoundException` để “tự động thử lại trên loader đã đóng”.** Loader cũ không được thiết kế để tái mở bằng `loadClass` sau close; tạo loader mới với đường URL rõ ràng.

**Tránh 6: trộn API dùng chung vào JAR reload và mong object cũ cast được sang class mới.** Các class cùng tên nhưng do loader khác nhau định nghĩa có identity khác; API chung nên ở parent để host và plugin cùng nhận diện.

## 15. Tự kiểm tra

**Câu 1.** Đã load `Early`, tạo instance rồi gọi `loader.close()`. Instance cũ có lập tức vô hiệu không?

**Đáp án:** Không. Class/object đã tạo vẫn có thể được dùng. Nhưng nếu một thao tác sau close mới yêu cầu dependency thuộc child JAR chưa được nạp, nó có thể lỗi.

**Câu 2.** `URLClassLoader.close()` có buộc JVM dỡ class và GC ngay không?

**Đáp án:** Không. Nó đóng nguồn tải/JAR handle của loader; class unloading và GC là cơ chế khác.

**Câu 3.** Vì sao `loader.loadClass("java.lang.String")` có thể hoạt động sau close?

**Đáp án:** Parent/bootstrap loader vẫn có thể cung cấp class. Close của child không đóng parent.

**Câu 4.** Điều gì được API đảm bảo nếu một thread đang nạp class trong khi thread khác gọi `close()`?

**Đáp án:** Kết quả lần nạp class đồng thời đó **không xác định**. Không có cam kết luôn thành công hoặc luôn thất bại theo một cách cố định.

**Câu 5.** Nếu `InputStream` mở qua `loader.getResourceAsStream(...)` vẫn còn, có nên tiếp tục đọc nó sau `close()` không?

**Đáp án:** Không. API `URLClassLoader` đóng những stream được mở qua phương thức đó khi loader đóng.

**Câu 6.** Tại sao đã close vẫn không xóa được JAR trên Windows?

**Đáp án:** Có thể còn handle do loader khác, resource stream, `JarFile`, process khác hoặc công cụ ngoài JVM giữ. Close chỉ xử lý các file do loader này mở.

**Câu 7.** Khi ứng dụng hot reload plugin, khi nào được gọi `oldLoader.close()`?

**Đáp án:** Sau khi ngừng nhận việc mới, bảo đảm các tác vụ đang dùng old loader đã kết thúc, và các resource/callback/thread liên quan đã được dọn phù hợp.

## 16. Tài liệu chính thức

- [Java SE 17 — URLClassLoader.close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close()): đóng loader, JAR/file handle, class đã nạp, parent delegation và undefined result khi close đồng thời với class loading.
- [Java SE 17 — URLClassLoader.getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#getResourceAsStream(java.lang.String)): resource stream do loader mở được đóng khi loader đóng.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getResource`, `getParent`.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): cleanup với try-with-resources.
- [Java Virtual Machine Specification 17, Chương 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): vòng đời nạp, liên kết và định danh kiểu runtime.

**Ghi nhớ:** `URLClassLoader.close()` là thao tác **chấm dứt nguồn tải mới và cố nhả file/JAR handle của loader**, không phải lệnh xóa class đã nạp. Muốn đóng an toàn, **quiesce mọi tác vụ và hoạt động nạp**, đọc/đóng stream đúng lúc, rồi close; tuyệt đối không đặt cược vào kết quả của việc `close()` diễn ra đồng thời với class loading.
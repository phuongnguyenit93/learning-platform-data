# Đóng luồng đọc và tránh lưu tài nguyên hoặc context vượt vòng đời plugin

## 1. Bài toán trong hệ thống mở rộng runtime

Ứng dụng chủ (host) có thể nạp plugin từ JAR, để plugin đọc resource, sử dụng một đối tượng context của host, rồi dừng plugin khi cấu hình hoặc phiên bản thay đổi. Mỗi lần như vậy đều tạo ra những tài nguyên có **vòng đời**: luồng đọc file, handle tới JAR, socket, executor, listener, classloader, đối tượng ngữ cảnh và những tham chiếu gián tiếp từ thread.

Nếu plugin mở `InputStream` nhưng không đóng, vẫn giữ context của một request đã kết thúc hoặc để một thread còn trỏ tới classloader cũ, host có thể gặp file descriptor leak, không thay được JAR trên một số hệ điều hành, tiêu tốn bộ nhớ, dùng nhầm cấu hình cũ, tiếp tục gọi code của plugin đã dừng hoặc giữ classloader cũ không thể thu hồi.

Mục tiêu của bài là quản lý **đúng thời điểm** chứ không chỉ nhớ gọi một hàm `close()`:

- **Vòng đời thao tác:** resource chỉ phục vụ một lần đọc/ghi. Mở trong một phạm vi hẹp và đóng ngay sau khi tiêu thụ, dù thao tác ném lỗi.
- **Vòng đời plugin:** các thành phần do plugin sở hữu sống qua nhiều lời gọi, chẳng hạn executor, scheduler, listener, socket hoặc registration. Dừng và giải phóng chúng trước khi bỏ plugin.
- **Vòng đời context:** dữ liệu/capability do host cấp có thể chỉ hợp lệ trong một request hoặc phiên plugin. Plugin không được tùy tiện lưu nó vào `static` field, cache hoặc tác vụ nền.
- **Vòng đời classloader:** host có thể dùng loader riêng để nạp plugin JAR. Đóng loader sau khi dừng công việc liên quan và loại bỏ các tham chiếu giữ nó; `close()` không tự unload lớp đang được sử dụng.

Ở đây “context” có hai nghĩa cần phân biệt: **PluginContext** (đối tượng host cấp, ví dụ ID thao tác và dịch vụ được phép) và **thread context classloader** (TCCL, giá trị trên `Thread` hỗ trợ tìm lớp/resource/service). Mỗi loại có quy tắc dọn dẹp riêng.

## 2. Ownership: ai mở, ai đóng và ai được giữ?

Quy tắc thực hành: **bên tạo và sở hữu tài nguyên đóng nó; bên chỉ mượn không được đóng tài nguyên dùng chung khi hợp đồng chưa chuyển quyền sở hữu**.

| Tài nguyên | Chủ sở hữu thường gặp | Thời điểm kết thúc | Cần tránh |
| --- | --- | --- | --- |
| `InputStream` lấy từ `getResourceAsStream` để đọc config | Bên gọi phương thức mở resource, thường là plugin | Kết thúc thao tác đọc | Giữ trong field hoặc quên đóng ở nhánh lỗi |
| `Reader`, `BufferedReader`, `JarFile`, `ZipFile` | Bên mở reader/file | Khi đã tiêu thụ xong | Trả lazy stream ra ngoài sau khi đã đóng nguồn |
| `URLClassLoader` do plugin manager tạo | Host/plugin manager | Sau khi plugin quiesce, stop và dừng task | Nghĩ `close()` sẽ hủy mọi đối tượng/lớp đang sống |
| Executor/timer/socket do plugin tạo | Plugin | `stop()`/`close()` của plugin | Để task nền dùng plugin sau khi unload |
| Listener/callback do plugin đăng ký vào host | Chủ thể đăng ký hoặc plugin manager theo contract | Khi plugin ngừng hoạt động | Registry của host tiếp tục giữ plugin instance |
| PluginContext do host truyền theo request | Host sở hữu, plugin được mượn | Kết thúc lời gọi hoặc thời hạn cấp | Cache nguyên context, dùng sau khi request hết hiệu lực |
| TCCL trên thread do host tạm thay | Đoạn code thay đổi trên thread đó | Cuối khối gọi, trong `finally` | Thread pool tiếp tục trỏ vào loader plugin cũ |
| Logger, client hay executor do host quản lý và chia sẻ | Host | Theo vòng đời của host | Plugin tự đóng service của host khiến plugin khác hỏng |

Ví dụ: một plugin được phép nhận `InputStream` từ factory với hợp đồng **caller owns stream** thì plugin đóng stream. Nhưng nếu host đưa một `DataSource` chung để plugin gọi query, plugin không được tự đóng `DataSource` khi ngừng request. Quyền truy cập và quyền đóng là hai quyền khác nhau.

Khi thiết kế API plugin, ghi rõ: context có thể giữ lâu hay chỉ dùng ngay, các đối tượng trả về có còn dùng được sau `execute()` không, `close()` có idempotent không, host xử lý lời gọi đang chạy khi stop như thế nào.

## 3. Đọc resource trong JAR đúng classloader và đóng đúng phạm vi

Hai API phổ biến:

~~~java
// Đoạn minh họa đặt bên trong một lớp implementation của plugin.
InputStream first = getClass().getResourceAsStream("/demo/plugin/message.txt");
InputStream second = getClass().getClassLoader()
        .getResourceAsStream("demo/plugin/message.txt");
~~~

Đây là **mã minh họa**, nếu sử dụng phải bao cả hai stream trong try-with-resources hoặc đóng phù hợp. Quy tắc tên:

- `Class.getResourceAsStream("/demo/plugin/message.txt")`: dấu gạch chéo đầu là resource path tuyệt đối từ gốc classpath/module.
- `Class.getResourceAsStream("message.txt")`: tên tương đối với package của class.
- `ClassLoader.getResourceAsStream("demo/plugin/message.txt")`: tên resource được truyền thường không có dấu gạch chéo đầu.
- Các lời gọi có thể trả về `null` nếu không tìm thấy; phải kiểm tra thiếu resource và báo lỗi rõ nguyên nhân.

Khi plugin có classloader riêng, dùng `getClass().getClassLoader()` giúp gắn việc tìm resource với loader định nghĩa lớp plugin. Dùng nhầm system loader hoặc TCCL có thể không nhìn thấy JAR plugin. Dù vậy, delegation parent-first vẫn có thể tìm một resource trùng tên ở parent; tránh tên chung và ưu tiên namespace riêng, chẳng hạn `demo/plugin/message.txt`.

Mẫu đọc an toàn cho resource nhỏ:

~~~java
// Phương thức minh họa; cần import java.io.* và java.nio.charset.StandardCharsets.
String readText(ClassLoader loader, String path) {
    try (InputStream in = loader.getResourceAsStream(path)) {
        if (in == null) {
            throw new IllegalArgumentException("Missing resource: " + path);
        }
        return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException ex) {
        throw new UncheckedIOException("Cannot read: " + path, ex);
    }
}
~~~

`try-with-resources` gọi `close()` khi kết thúc khối, kể cả nhánh exception. Nếu `in` là null, Java bỏ qua gọi `close()` và nhánh kiểm tra ném lỗi. Khi đọc thất bại và đóng cũng thất bại, lỗi đóng thường xuất hiện trong danh sách suppressed exceptions của lỗi chính (`Throwable.getSuppressed()`). Vì vậy không nên thay đoạn trên bằng chuỗi `open → read → close` thủ công thiếu `finally`.

`InputStream.readAllBytes()` dùng được cho file nhỏ, tin cậy; nếu nguồn lớn hoặc do bên ngoài cung cấp, phải giới hạn byte đọc, dùng buffer và áp dụng giới hạn tài nguyên. Không trả `InputStream` hay `Stream<String>` đọc lazy từ một khối đã đóng. Nếu thật sự cần streaming qua ranh giới, contract phải chuyển ownership của stream cho bên nhận và yêu cầu bên nhận gọi `close()`; với dữ liệu cấu hình nhỏ, trả về `String` hoặc dữ liệu đã materialize thường đơn giản hơn.

Những resource khác cũng cần tuân theo phạm vi đóng: `Files.lines(path)`, `Files.list(path)` và `Files.walk(path)` trả một `Stream` có thể giữ resource I/O, nên dùng trong try-with-resources; `JarFile`/`ZipFile` cũng phải được đóng. Đừng giữ handle đến JAR trong cache nếu plugin không cần dùng xuyên các lần gọi.

## 4. Chương trình Java 17 chạy được: plugin JAR và resource

Ví dụ gồm **API dùng chung**, **plugin JAR độc lập** có tài nguyên văn bản và **host** tự nạp plugin. Nó minh họa việc đọc xong/đóng stream trong mỗi lượt, dùng context trong phạm vi `execute`, gọi `plugin.close()`, khôi phục TCCL và đóng `URLClassLoader`.

### 4.1. Cấu trúc thư mục

~~~text
plugin-resource-example/
  src/
    api/demo/api/Plugin.java
    api/demo/api/PluginContext.java
    plugin/demo/plugin/GreetingPlugin.java
    plugin-resources/demo/plugin/message.txt
    host/demo/host/HostApp.java
  build/                     (được tạo khi biên dịch)
~~~

API chỉ định nghĩa hợp đồng; host **không** import `GreetingPlugin`. Plugin JAR không kèm bản sao `demo.api.Plugin` để tránh hai định nghĩa khác nhau của cùng interface giữa host và loader plugin.

### 4.2. API chung do host sở hữu

**`src/api/demo/api/Plugin.java`**

~~~java
package demo.api;

public interface Plugin extends AutoCloseable {
    void execute(PluginContext context);

    @Override
    void close();
}
~~~

**`src/api/demo/api/PluginContext.java`**

~~~java
package demo.api;

import java.util.Objects;

public record PluginContext(String invocationId) {
    public PluginContext {
        Objects.requireNonNull(invocationId, "invocationId");
    }
}
~~~

`PluginContext` chứa một ID của một lần gọi và dùng Java 17 record. Plugin chỉ được sử dụng khi xử lý lời gọi. Nếu thực tế context mang service hoặc callback của host, contract phải ghi rõ thời hạn hiệu lực; record chỉ bảo đảm trường `String` là bất biến, không tự làm mọi đối tượng chứa trong record bất biến.

### 4.3. Implementation đọc resource của chính JAR

**`src/plugin/demo/plugin/GreetingPlugin.java`**

~~~java
package demo.plugin;

import demo.api.Plugin;
import demo.api.PluginContext;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

public final class GreetingPlugin implements Plugin {
    private boolean closed;

    public GreetingPlugin() {
    }

    @Override
    public void execute(PluginContext context) {
        if (closed) {
            throw new IllegalStateException("Plugin already closed");
        }

        try (InputStream in = getClass().getClassLoader()
                .getResourceAsStream("demo/plugin/message.txt")) {
            if (in == null) {
                throw new IllegalStateException("Missing message.txt");
            }

            String message = new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).strip();
            System.out.println(
                    "plugin[" + context.invocationId() + "]: " + message);
        } catch (IOException ex) {
            throw new UncheckedIOException(
                    "Reading plugin message failed", ex);
        }
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("plugin closed");
        }
    }
}
~~~

**`src/plugin-resources/demo/plugin/message.txt`**

~~~text
Xin chào từ JAR
~~~

Luồng đọc được mở trong `execute()` rồi đóng ngay khi kết thúc, không lưu vào field. Chuỗi kết quả đã độc lập với stream. Tệp có thể có newline cuối; `strip()` bỏ newline để output ổn định. Plugin chỉ đọc `context.invocationId()` khi đang xử lý, không lưu context sang phiên khác.

Trường `closed` là ví dụ đơn luồng. Nếu host cho phép gọi `execute()` và `close()` đồng thời, cần đồng bộ và quản lý số lời gọi đang chạy; một `boolean` đơn giản không đủ an toàn trong bối cảnh nhiều thread. `close()` ở đây chỉ in thông báo vì plugin không sở hữu resource dài hạn; trong sản phẩm thật phải thêm cleanup đúng với executor, listener, connection mà plugin thực sự tạo.

### 4.4. Host khôi phục context và đóng loader

**`src/host/demo/host/HostApp.java`**

~~~java
package demo.host;

import demo.api.Plugin;
import demo.api.PluginContext;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class HostApp {
    private HostApp() {
    }

    public static void main(String[] args) throws Exception {
        Path jar = Path.of("build/greeting-plugin.jar");
        if (!Files.isRegularFile(jar)) {
            throw new IllegalStateException("Plugin JAR missing: " + jar);
        }

        ClassLoader original =
                Thread.currentThread().getContextClassLoader();

        System.out.println("host started");
        URL[] urls = {jar.toUri().toURL()};

        try (URLClassLoader pluginLoader = new URLClassLoader(
                urls, HostApp.class.getClassLoader())) {
            try {
                Thread.currentThread()
                        .setContextClassLoader(pluginLoader);

                Class<?> type = Class.forName(
                        "demo.plugin.GreetingPlugin", true, pluginLoader);
                Plugin plugin = (Plugin) type
                        .getDeclaredConstructor().newInstance();

                try (plugin) {
                    plugin.execute(new PluginContext("req-001"));
                }
            } finally {
                Thread.currentThread()
                        .setContextClassLoader(original);
            }
        }

        System.out.println(
                "tccl restored=" +
                (Thread.currentThread().getContextClassLoader() == original));
        System.out.println("host finished");
    }
}
~~~

Ở đây host tạo loader chỉ chứa plugin JAR với parent là application classloader. Host và plugin chia sẻ `demo.api.Plugin` từ parent. Lệnh `Class.forName(..., true, pluginLoader)` chọn loader và khởi tạo class; reflection tạo instance theo public constructor.

Chuỗi cleanup khi xử lý thành công:

1. `plugin.execute` mở và đóng luồng đọc trong nội bộ.
2. `try (plugin)` gọi `plugin.close()` trước khi rời phạm vi plugin.
3. `finally` phục hồi TCCL **trên thread vừa thay đổi nó**.
4. Try-with-resources ngoài gọi `pluginLoader.close()` khi plugin đã xong.
5. Host in thông tin xác nhận TCCL trở lại cùng đối tượng loader ban đầu.

Nếu `execute()` hoặc `close()` ném exception, các khối `finally`/try-with-resources vẫn được thực hiện. Lệnh cuối in thành công chỉ chạy nếu chương trình không để exception lan ra khỏi `main`. Không nên nuốt exception cleanup rồi báo thành công giả.

### 4.5. Biên dịch và chạy

Tại thư mục `plugin-resource-example`, sau khi tạo đúng năm tệp ở trên, dùng JDK 17+ với Bash:

~~~bash
mkdir -p build/api build/plugin build/host

javac --release 17 -encoding UTF-8 \
  -d build/api \
  src/api/demo/api/Plugin.java src/api/demo/api/PluginContext.java
jar --create --file build/plugin-api.jar -C build/api .

javac --release 17 -encoding UTF-8 \
  -cp build/plugin-api.jar \
  -d build/plugin src/plugin/demo/plugin/GreetingPlugin.java
jar --create --file build/greeting-plugin.jar \
  -C build/plugin . -C src/plugin-resources demo/plugin/message.txt

javac --release 17 -encoding UTF-8 \
  -cp build/plugin-api.jar \
  -d build/host src/host/demo/host/HostApp.java

java -cp "build/host:build/plugin-api.jar" demo.host.HostApp
~~~

**Stdout chính xác khi đầy đủ JAR/resource:**

~~~text
host started
plugin[req-001]: Xin chào từ JAR
plugin closed
tccl restored=true
host finished
~~~

Lệnh chạy Windows PowerShell dùng dấu chấm phẩy để phân tách classpath:

~~~powershell
java -cp "build/host;build/plugin-api.jar" demo.host.HostApp
~~~

Các lệnh `javac`/`jar` nhiều dòng trên sử dụng dấu gạch chéo ngược để nối dòng theo cú pháp Bash; trên PowerShell có thể gộp mỗi lệnh thành một dòng. Host không đưa `build/greeting-plugin.jar` vào compile classpath hay application classpath; host nạp JAR đó qua `URLClassLoader`.

Để kiểm tra đóng gói:

~~~bash
jar --list --file build/greeting-plugin.jar
~~~

Cần tìm thấy `demo/plugin/GreetingPlugin.class` và `demo/plugin/message.txt`. Nếu quên đưa resource vào JAR, nhánh thiếu file sẽ báo `Missing message.txt`; `plugin.close()` và khôi phục TCCL vẫn diễn ra trước khi lỗi thoát lên `main`. Đoạn code minh họa luồng điều khiển đóng, nhưng **không chứng minh classloader đã được garbage collect/unload**.

## 5. Context sống lâu hơn plugin nguy hiểm thế nào?

### 5.1. Thread context classloader (TCCL)

TCCL là trường tham chiếu của `Thread`, thường được thư viện/framework sử dụng để tìm resource, class hoặc service. Khi host tạm thay TCCL cho plugin rồi trả thread lại pool mà không khôi phục, thread sống lâu có thể tiếp tục giữ loader plugin và truy cập nhầm thư viện cũ.

**Đoạn minh họa sai** (giả sử đã có `pluginLoader`, `plugin` và `context`):

~~~java
Thread.currentThread().setContextClassLoader(pluginLoader);
plugin.execute(context);  // Nếu ném lỗi, TCCL vẫn trỏ vào pluginLoader.
~~~

Đúng hơn:

~~~java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    plugin.execute(context);
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
~~~

Khôi phục phải thực hiện trên **chính thread** đã thay TCCL. Một thread khác không thể giải phóng TCCL của worker chỉ bằng cách thay TCCL của chính nó. `URLClassLoader.close()` cũng không tự xóa TCCL đang trỏ đến loader cũ.

### 5.2. ThreadLocal và dữ liệu của từng request

Thread pool của host thường tái sử dụng cùng thread cho các request khác nhau. `ThreadLocal` gắn giá trị với thread, không gắn tự động với vòng đời request; nếu giữ context, token, callback hoặc đối tượng plugin, nó có thể gây rò rỉ hay dùng dữ liệu cũ.

Khi thực sự cần ThreadLocal, đặt và dọn trong cùng phạm vi:

~~~java
// Minh họa; CONTEXT và processRequest() do ứng dụng định nghĩa.
CONTEXT.set(context);
try {
    processRequest();
} finally {
    CONTEXT.remove();
}
~~~

Ưu tiên truyền context tường minh qua tham số khi có thể. `remove()` phải chạy trên **thread đã set**; việc xóa từ thread điều phối không xóa giá trị nằm trong các worker thread khác. Một object `PluginContext` mượn từ host không nên bị plugin lưu vào `static` field hoặc closure của future sống lâu.

### 5.3. Executor, thread và scheduled task

Thread mới tạo có thể kế thừa TCCL của thread tạo. Nếu plugin khởi tạo executor khi thread hiện tại đang trỏ đến loader plugin, worker thread có thể giữ loader ấy trong suốt thời gian executor sống. Lambda/Runnable trong hàng đợi cũng có thể bắt giữ instance plugin hoặc request context.

Với executor do plugin sở hữu, `close()`/`stop()` cần chặn công việc mới, cancel các lịch lặp, gọi `shutdown()`, đợi `awaitTermination` trong thời gian đã định, sau đó áp dụng chính sách nếu task còn chạy. `shutdownNow()` chỉ cố ngắt thread, không bảo đảm task đang bỏ qua interrupt sẽ dừng ngay. Trước khi đóng loader phải chắc rằng không còn tác vụ sử dụng class hoặc resource của plugin.

Nếu executor do **host** cấp, plugin không được tùy tiện shutdown executor chung; host phải có API hủy các task **thuộc plugin này**. Mọi task cần tự dọn TCCL và ThreadLocal của thread thực thi trong `finally`.

### 5.4. Listener, callback, registry và cache

Một event bus singleton của host giữ callback đăng ký bởi plugin sẽ giữ plugin instance. Tương tự, `Map<Class<?>, ...>`, `Method`, `ServiceLoader`, list các provider hay cache trả về từ reflection có thể giữ những lớp và defining classloader mà plugin manager tưởng đã bỏ.

Khi dừng plugin, hủy đăng ký listener, đóng registration handle hoặc để host gỡ toàn bộ mục theo plugin ID. `ServiceLoader.reload()` xóa cache provider của **ServiceLoader instance đó**, nhưng không xóa reference mà host đã lưu ở list, registry hay callback khác.

Classloader thường chỉ có thể được thu hồi khi không còn tham chiếu sống cần đến lớp/loader liên quan. Vì vậy `URLClassLoader.close()` cần thiết đối với loader sở hữu, nhưng **chưa đủ** để đảm bảo việc unload; không có lời hứa GC xảy ra tức thì.

### 5.5. PluginContext là capability có thời hạn

Context thực tế có thể mang cấu hình, request ID, principal, logger, service proxy, transaction hoặc callback do host cấp. Nếu plugin giữ context sau khi `execute()` trả về, dữ liệu/quyền truy cập có thể hết hiệu lực và chuỗi tham chiếu có thể giữ cả request/host.

Một quy tắc hợp đồng phù hợp:

> Context của một lần gọi chỉ hợp lệ cho lần gọi ấy. Plugin được đọc và sử dụng trong phạm vi cấp. Khi cần tác vụ bất đồng bộ, chỉ chuyển một snapshot nhỏ, bất biến và được phép giữ, hoặc dùng API async mà host hỗ trợ lifecycle và cơ chế thu hồi tường minh.

Không tự đóng service chung có trong context, không đẩy nguyên context vào global cache, không giữ callback sau khi plugin đã bị ngừng. Nếu host thực sự cấp một capability sống dài, phải có scope, cơ chế revoke và owner rõ ràng.

## 6. Thiết kế vòng đời plugin từ start đến unload

Một luồng lifecycle gợi ý:

~~~text
NEW -> STARTING -> ACTIVE -> QUIESCING -> STOPPED -> RELEASED
                       \-> FAILED -> CLEANUP
~~~

Đây là **mô hình kiến trúc**, không phải state machine tự có của JVM. Trách nhiệm:

1. **STARTING:** tạo loader và plugin instance, kiểm tra API/version, mở tài nguyên cần thiết. Nếu lỗi một phần, cleanup các thứ đã tạo thành công.
2. **ACTIVE:** cấp context đúng phạm vi, đếm lời gọi đang chạy, đóng stream từng thao tác, theo dõi task và registration do plugin sở hữu.
3. **QUIESCING:** ngăn lời gọi mới, hủy entry point/listener, chờ in-flight call kết thúc hoặc hủy theo hợp đồng. Không đóng classloader khi task còn sử dụng nó.
4. **STOPPED:** gọi hook `close()`/`stop()` của plugin, shutdown executor riêng, giải phóng socket, watcher, timer, ThreadLocal và context trên các thread đã dùng.
5. **RELEASED:** loại reference khỏi registry/cache, đóng loader nếu host sở hữu, ghi lại lỗi cleanup và không còn thao tác nào nhắm vào plugin cũ.

Khi các tài nguyên phụ thuộc nhau, nên đóng theo thứ tự **ngược với thứ tự nhận/acquire**, tương tự try-with-resources. Đối tượng plugin thường phải dừng trước loader vì nó còn có thể cần đọc resource trong bước shutdown.

**Trạng thái an toàn khi stop cạnh tranh với execute:** chặn call mới, theo dõi call đang chạy, kết thúc/cancel theo policy, sau đó mới cho phép close. Một biến boolean `closed` bình thường không đủ nếu nhiều thread đọc/ghi đồng thời. Cần đồng bộ, reference counting/phạm vi invoke hoặc công cụ quản lý lifecycle thích hợp. Không được bắt mọi `Throwable` rồi tuyên bố plugin đã dừng nếu thread/registration vẫn hoạt động.

## 7. Những lỗi phổ biến và hướng kiểm tra

| Hiện tượng | Nguồn gốc có thể | Hướng xử lý |
| --- | --- | --- |
| Không thể thay JAR cũ ổn định, số handle tăng | InputStream/JarFile còn mở hoặc URLClassLoader chưa close | Dùng try-with-resources, kiểm tra open file handles và thứ tự stop |
| Plugin báo thiếu resource | Resource không được đóng gói, sai path, dùng sai loader | `jar --list --file`, kiểm tra dấu `/` và classloader |
| Lúc reload thỉnh thoảng lỗi | Task cũ vẫn chạy khi loader bị đóng hoặc registry đổi | Quiesce và chờ in-flight task trước khi close |
| Heap/metaspace tăng sau nhiều vòng | TCCL, ThreadLocal, listener, cache Class/Method/provider còn giữ loader | Xem thread dump, heap dominators, classloader identity |
| Request mới thấy context cũ | ThreadLocal không remove ở thread pool | Try/finally set/use/remove trên đúng worker thread |
| Host khác bị ngắt kết nối | Plugin đóng client/executor do host chia sẻ | Phân quyền ownership, chỉ đóng tài nguyên riêng |
| Plugin đã dừng nhưng callback vẫn chạy | Event bus, timer, future giữ callback/instance | Hủy registration, cancel lịch, chặn call mới |
| GC chưa unload lớp dù đã `close` | Reference vẫn sống hoặc GC chưa tiến hành | Đo retained reference qua nhiều vòng, không suy luận từ một lần GC |

Khi kiểm thử rò rỉ, không nên chỉ nhìn tổng heap một thời điểm. JVM có thể giữ vùng nhớ để dùng lại. Cần quan sát **số thread, file descriptor, classloader còn sống, chuỗi tham chiếu trong heap và trạng thái tác vụ** qua nhiều chu kỳ start/stop, cả nhánh lỗi.

## 8. Kiểm tra để bảo đảm cleanup

- **Luồng đọc thành công:** chạy ví dụ ở mục 4, đối chiếu đúng năm dòng stdout; đảm bảo resource đóng ngay khi `execute` kết thúc.
- **Thiếu resource:** đóng gói plugin JAR không kèm `message.txt` và xác nhận thông báo lỗi có ngữ cảnh; `close()` và `finally` vẫn chạy. Tình huống lỗi không dùng stdout thành công làm kết quả kỳ vọng.
- **Lỗi I/O:** dùng mock/fake InputStream ném `IOException` khi đọc và xác nhận `close()` vẫn được gọi, lỗi chính không bị mất vì lỗi đóng.
- **Context/TCCL:** gọi plugin trên thread pool, kể cả trường hợp ném exception, rồi xác nhận TCCL phục hồi và ThreadLocal không còn giá trị request cũ.
- **Stop khi có call:** cho một thao tác chậm chạy, yêu cầu stop song song, xác nhận không đóng loader sớm và không nhận thêm lời gọi sau khi quiesce.
- **Lặp chu kỳ:** start/execute/stop nhiều lần, kiểm tra không còn task nền hay callback, giảm reference tới loader cũ và không tăng số handle.
- **Quyền sở hữu:** plugin đóng đúng resource nó tạo; không đóng executor/service của host được chia sẻ cho nhiều plugin.
- **Metadata JAR:** kiểm tra `jar --list` để chắc resource được đóng gói đúng; kiểm tra mã host chỉ phụ thuộc API chung.

## 9. Checklist vận hành

- [ ] Mọi `InputStream`, `Reader` và JAR handle có owner và điểm đóng rõ ràng.
- [ ] Try-with-resources bao trọn thao tác có thể ném exception; stream lazy không vượt phạm vi nguồn đã đóng.
- [ ] Resource được tìm bằng loader phù hợp và tên tương đối/tuyệt đối chính xác.
- [ ] PluginContext không lưu qua request hoặc phiên được cấp; không giữ host service/callback quá thời hạn.
- [ ] TCCL được khôi phục trong finally trên cùng thread, ThreadLocal được remove.
- [ ] Executor/timer/scheduler của plugin có stop, hủy lịch và đợi hoàn tất theo timeout.
- [ ] Listener, registration, cache và ServiceLoader provider của plugin được host bỏ tham chiếu khi dừng.
- [ ] Host ngăn lời gọi mới và xử lý in-flight calls trước khi đóng plugin/loader.
- [ ] Không nhầm `URLClassLoader.close()` với unload lớp tức thì.
- [ ] Kiểm thử cả đường lỗi và nhiều vòng reload, quan sát file handle, thread và reference thực tế.

**Kết luận:** Đọc đúng resource mới chỉ giải quyết một phần của runtime extensibility. Sự an toàn khi dừng hoặc thay plugin phụ thuộc vào việc đóng các luồng ngắn hạn, chấm dứt các tài nguyên dài hạn, khôi phục ngữ cảnh trên đúng thread và hủy những tham chiếu từ host tới plugin. Hợp đồng ownership/lifecycle rõ ràng giúp host thay plugin mà không giữ lại một phiên cũ ngoài ý muốn.
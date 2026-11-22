# Vai trò của thread context class loader trong SPI và thư viện tích hợp

## 1. TCCL giải quyết vấn đề gì?

Trong ứng dụng mở rộng bằng plugin, giao diện dịch vụ (SPI) thường được nạp bởi classloader của host, trong khi lớp triển khai dịch vụ được đặt trong JAR do một classloader khác nạp sau. Một thư viện chung không biết trước danh sách plugin và classloader của chính thư viện có thể không nhìn thấy các JAR mới.

**Thread context class loader (TCCL)** là tham chiếu `ClassLoader` được gắn với thread hiện hành. Java cung cấp hai phương thức:

```java
ClassLoader context = Thread.currentThread().getContextClassLoader();
Thread.currentThread().setContextClassLoader(context);
```

Đây là đoạn minh họa, không phải chương trình độc lập. Host có thể đặt TCCL thành classloader nhìn thấy plugin khi gọi một thư viện cần tìm provider. Nếu thư viện sử dụng TCCL, thao tác tìm kiếm sẽ dựa trên **ngữ cảnh của bên gọi** thay vì chỉ dựa vào classloader vốn đã nạp thư viện.

Điều cần nhớ: TCCL **không tự nạp mọi plugin**, không thay đổi bộ nạp đã định nghĩa một lớp và không tự gọi phương thức kích hoạt plugin. Nó chỉ định nguồn tìm kiếm khi API tương ứng chọn sử dụng tham chiếu đó.

## 2. Mối quan hệ host, SPI, plugin và bộ nạp lớp

```text
Thread gọi thư viện
    |
    +---- TCCL ----------------------+
                                      |
                                      v
                    pluginLoader (URLClassLoader)
                    - plugin.jar
                    - provider implementation
                    - META-INF/services/...
                                      |
                                  parent-first
                                      |
                                      v
                    host/application loader
                    - service interface (SPI)
                    - host
                    - thư viện dùng SPI
```

Với cấu trúc ủy quyền parent-first, loader con có thể nhờ loader cha tìm kiểu SPI, còn loader cha thường không nhìn thấy lớp provider nằm riêng trong JAR của con. Nếu thư viện ở phía cha chỉ tra cứu qua chính classloader của nó, provider sẽ bị bỏ sót. TCCL là cơ chế để host trao cho thư viện một loader khác có thể nhìn thấy provider.

Tách ba khái niệm:

- **Classloader định nghĩa kiểu:** JVM nhận diện lớp bằng tên nhị phân và loader đã định nghĩa nó. Hai lớp cùng tên do hai loader khác nhau định nghĩa có thể là hai kiểu khác nhau.
- **Classloader tìm kiếm:** khi `loadClass` hoặc `getResources` được gọi, đường ủy quyền quyết định tìm thấy gì.
- **TCCL:** một tham chiếu trên thread; thư viện có thể chọn lấy nó làm loader tìm kiếm.

Đổi TCCL không đổi kết quả của `Greeter.class.getClassLoader()`. Hợp đồng SPI phải được dùng chung đúng cách để provider có thể được ép sang kiểu mà host mong đợi.

## 3. API SPI dùng TCCL như thế nào?

Trong Java SE 17, lời gọi:

```java
ServiceLoader<Greeter> services = ServiceLoader.load(Greeter.class);
```

sử dụng **context class loader của thread gọi**. Với SPI trên classpath, loader tương ứng cần thấy tài nguyên đăng ký mang tên:

```text
META-INF/services/demo.spi.Greeter
```

và nội dung tệp UTF-8 liệt kê tên nhị phân đầy đủ của provider:

```text
demo.plugin.WelcomeGreeter
```

Tên tệp theo **service type**, không theo provider. Classloader phải thấy cả tài nguyên đăng ký và các lớp phụ thuộc cần thiết.

Nếu host đã biết loader muốn dùng, nó có thể gọi overload tường minh:

```java
ServiceLoader<Greeter> services =
        ServiceLoader.load(Greeter.class, pluginLoader);
```

Hai đoạn là ví dụ rời, giả định `Greeter` và `pluginLoader` đã tồn tại.

| Cách gọi | Loader dùng để khám phá | Điểm cần lưu ý |
|---|---|---|
| `ServiceLoader.load(Greeter.class)` | TCCL tại thời điểm tạo ServiceLoader | Phụ thuộc ngữ cảnh của thread hiện tại |
| `ServiceLoader.load(Greeter.class, pluginLoader)` | Loader được truyền trực tiếp | Rõ ràng, dễ kiểm soát khi host sở hữu loader |
| `Greeter.class.getClassLoader()` | Loader đã định nghĩa kiểu SPI | Có thể là loader cha, không thấy provider ở loader con |
| `ClassLoader.getSystemClassLoader()` | System classloader | Không mặc nhiên biết mọi JAR được nạp động |

`ServiceLoader.load(...)` tạo đối tượng khám phá; provider thường được tìm và tạo **lười** khi duyệt, gọi `findFirst()` hoặc dùng `stream()`. Một `ServiceLoader` lưu các provider đã gặp và loader của chính nó. Đổi TCCL sau khi tạo đối tượng ServiceLoader không có nghĩa đối tượng đó tự chuyển sang loader mới. `reload()` xóa cache provider trong ServiceLoader, nhưng không tự thêm JAR vào classloader.

Với các **named module** trong JPMS, cơ chế `uses`/`provides ... with ...` và module layer cũng tham gia khám phá. Phần thực hành dưới đây dùng classpath để làm rõ tác dụng của TCCL.

## 4. Ví dụ Java 17 chạy được: cùng một SPI, hai ngữ cảnh

Ta đặt `Greeter` và host trên application classpath; JAR của provider **không nằm** trên application classpath. Host tự mở JAR bằng `URLClassLoader`, rồi so sánh ba phép tìm: TCCL mặc định, TCCL được đổi sang pluginLoader và loader truyền rõ ràng.

### Cấu trúc dự án

```text
tccl-demo/
├── api/src/demo/spi/Greeter.java
├── host/src/demo/host/Main.java
└── plugin/
    ├── src/demo/plugin/WelcomeGreeter.java
    └── resources/META-INF/services/demo.spi.Greeter
```

**Hợp đồng** tại `api/src/demo/spi/Greeter.java`:

```java
package demo.spi;

public interface Greeter {
    String greet(String name);
}
```

**Provider** tại `plugin/src/demo/plugin/WelcomeGreeter.java`:

```java
package demo.plugin;

import demo.spi.Greeter;

public final class WelcomeGreeter implements Greeter {
    public WelcomeGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

**Tệp đăng ký** `plugin/resources/META-INF/services/demo.spi.Greeter` có đúng nội dung:

```text
demo.plugin.WelcomeGreeter
```

Lớp provider là `public`, có constructor không tham số `public` và triển khai service interface để phù hợp với SPI trên classpath.

**Host** tại `host/src/demo/host/Main.java`:

```java
package demo.host;

import demo.spi.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class Main {
    private static String status() {
        return ServiceLoader.load(Greeter.class)
                .findFirst()
                .isPresent() ? "found" : "none";
    }

    public static void main(String[] args) throws Exception {
        Path jar = Path.of("plugins", "greeter-plugin.jar").toAbsolutePath();
        Thread current = Thread.currentThread();
        ClassLoader previous = current.getContextClassLoader();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {jar.toUri().toURL()},
                Greeter.class.getClassLoader())) {

            System.out.println("before=" + status());
            System.out.println("descriptor=" + (pluginLoader.getResource(
                    "META-INF/services/demo.spi.Greeter") != null));

            current.setContextClassLoader(pluginLoader);
            try {
                Greeter provider = ServiceLoader.load(Greeter.class)
                        .findFirst()
                        .orElseThrow();
                System.out.println("context=" + provider.greet("Java"));
            } finally {
                current.setContextClassLoader(previous);
            }

            Greeter explicit = ServiceLoader.load(
                    Greeter.class, pluginLoader).findFirst().orElseThrow();
            System.out.println("explicit=" + explicit.greet("Java"));
            System.out.println("restored=" + status());
        }
    }
}
```

Host dùng `Greeter.class.getClassLoader()` làm **loader cha** của `pluginLoader` để hai phía chia sẻ cùng lớp `Greeter`. Vì vậy việc trả về provider kiểu `Greeter` có thể hoạt động. `getResource` kiểm tra descriptor có nhìn thấy được trước khi tạo provider. Khối `finally` phục hồi TCCL ngay cả khi việc tìm/tạo plugin thất bại. `try-with-resources` đóng URLClassLoader khi rời phạm vi sử dụng.

### Lệnh biên dịch và chạy trên Windows PowerShell với JDK 17+

Chạy từ thư mục `tccl-demo`:

```powershell
New-Item -ItemType Directory -Force -Path out\api,out\host,out\plugin,plugins | Out-Null

javac -d out\api api\src\demo\spi\Greeter.java
javac -cp out\api -d out\plugin plugin\src\demo\plugin\WelcomeGreeter.java
javac -cp out\api -d out\host host\src\demo\host\Main.java

Copy-Item -Path plugin\resources\META-INF -Destination out\plugin -Recurse
jar --create --file plugins\greeter-plugin.jar -C out\plugin .

java -cp "out\api;out\host" demo.host.Main
```

**Kết quả stdout** với đúng cấu trúc ví dụ:

```text
before=none
descriptor=true
context=Hello, Java
explicit=Hello, Java
restored=none
```

- `before=none`: TCCL mặc định của application thread chưa thấy plugin JAR nằm ngoài `-cp`.
- `descriptor=true`: pluginLoader mới thấy `META-INF/services/demo.spi.Greeter` trong JAR.
- `context=Hello, Java`: sau khi đặt TCCL là pluginLoader, overload mặc định của ServiceLoader phát hiện provider.
- `explicit=Hello, Java`: overload truyền trực tiếp pluginLoader vẫn hoạt động dù đã phục hồi TCCL.
- `restored=none`: host trở về ngữ cảnh cũ, lần tìm mới theo TCCL cũ không thấy provider.

Trên macOS/Linux, thay dấu phân cách classpath `;` bằng `:` và dùng cú pháp shell tạo thư mục/sao chép tương đương. Không thêm `plugins/greeter-plugin.jar` vào `-cp` trong thí nghiệm này: nếu thêm, loader mặc định cũng có thể nhìn thấy provider nên không còn phân biệt rõ hai ngữ cảnh.

### Ba thay đổi để tự quan sát

1. **Bỏ `setContextClassLoader(pluginLoader)`:** `ServiceLoader.load(Greeter.class).findFirst().orElseThrow()` không tìm được provider trong ví dụ và ném `NoSuchElementException`. Overload truyền `pluginLoader` vẫn hoạt động.
2. **Đổi loader cha thành một loader không thấy `Greeter`:** dù tìm được lớp provider, có thể phát sinh lỗi phụ thuộc hoặc không khớp kiểu SPI. Chia sẻ classloader hợp đồng là yêu cầu khác với đặt TCCL.
3. **Bỏ tệp `META-INF/services` khỏi JAR:** `descriptor=false`, và không có provider nào được khai báo cho ServiceLoader classpath mặc dù `WelcomeGreeter.class` tồn tại.

Những thay đổi này chỉ nhằm kiểm chứng cách **khám phá provider**, không thể hiện toàn bộ cơ chế vòng đời plugin hay cập nhật nóng JAR.

## 5. Những thư viện tích hợp nào dùng TCCL?

TCCL được thiết kế hữu ích cho cơ chế khám phá do **thư viện chung** điều phối nhưng **ứng dụng** cung cấp triển khai. Ngoài `ServiceLoader`, ví dụ tiêu biểu là `javax.script.ScriptEngineManager`:

```java
// Đoạn minh họa; giả định pluginLoader đã được khai báo.
var managerA = new javax.script.ScriptEngineManager();
var managerB = new javax.script.ScriptEngineManager(pluginLoader);
```

Constructor không tham số của `ScriptEngineManager` dùng context class loader để khám phá script engine factories; constructor còn lại dùng loader được cung cấp. JDK 17 không bảo đảm sẵn JavaScript engine nên ví dụ trên **không khẳng định** sẽ tìm thấy engine cụ thể. Tính sẵn có phụ thuộc provider thực sự trên môi trường chạy.

Trong các nền tảng tích hợp và application server, framework có thể tạm thiết lập TCCL trước khi gọi thư viện hoặc phần mở rộng rồi khôi phục sau. Tuy nhiên:

- Không phải **mọi** thư viện, API tra cứu tài nguyên hoặc thư viện logging đều đọc TCCL.
- Một thư viện có thể ưu tiên property, file cấu hình, module, classloader của chính nó, hoặc overload nhận loader tường minh.
- `Class.getResource(...)`, `ClassLoader.getResources(...)` và `ServiceLoader` không phải ba cách tra cứu tương đương.
- Phải đọc hợp đồng **của thư viện cụ thể** để xác định lúc nào TCCL được lấy và liệu nó có lưu cache kết quả không.

TCCL không phải API truyền dữ liệu nghiệp vụ giữa host và plugin. Nó chỉ điều chỉnh **ngữ cảnh nạp lớp/tài nguyên** cho những thành phần tự chọn sử dụng nó.

## 6. Kế thừa và tái sử dụng thread: vì sao phải phục hồi TCCL?

TCCL thuộc về **thread thực thi**, không tự gắn với một request, một task hoặc một phiên làm việc riêng. Thread mới thường kế thừa context class loader từ thread tạo nó; thread pool có thể tái sử dụng một thread cho nhiều công việc.

Nếu task A đổi TCCL sang loader của plugin A nhưng quên khôi phục, task B trên cùng worker thread có thể nhìn nhầm provider của plugin A. TCCL còn giữ tham chiếu tới classloader cũ, khiến việc thu hồi plugin khó khăn hơn.

Một mẫu nhỏ dùng `try/finally`:

```java
// Helper minh họa; đặt trong một lớp và import java.util.function.Supplier.
static <T> T withContextLoader(
        ClassLoader wanted,
        java.util.function.Supplier<T> action) {
    Thread thread = Thread.currentThread();
    ClassLoader old = thread.getContextClassLoader();
    thread.setContextClassLoader(wanted);
    try {
        return action.get();
    } finally {
        thread.setContextClassLoader(old);
    }
}
```

Dùng mẫu này **trong chính task chạy trên thread cần tra cứu**. Đặt TCCL trên thread gửi việc không đồng nghĩa tự lan sang các thread executor đã được tạo từ trước. `CompletableFuture` và các callback bất đồng bộ cũng không mặc nhiên bảo đảm truyền ngữ cảnh loader qua mọi ranh giới.

Nếu thư viện cho phép truyền classloader như `ServiceLoader.load(service, loader)`, cách truyền tường minh thường dễ hiểu, dễ kiểm thử hơn việc điều chỉnh TCCL của thread. Khi buộc phải dùng TCCL, nên giữ phạm vi rất ngắn và luôn khôi phục ngữ cảnh ban đầu.

## 7. Chẩn đoán lỗi khi plugin không được phát hiện

| Hiện tượng | Cần kiểm tra |
|---|---|
| `ServiceLoader.load(service)` trả về rỗng | TCCL hiện tại; tên/đường dẫn `META-INF/services`; JAR có được loader thấy không |
| Overload truyền pluginLoader thấy provider, overload mặc định không thấy | TCCL đang khác pluginLoader; thiết lập tại đúng thời điểm gọi |
| Có descriptor nhưng báo `ServiceConfigurationError` | Tên class provider, constructor/factory, bytecode, phụ thuộc, khả năng tương thích SPI |
| Lỗi `ClassCastException` hoặc “not a subtype” | Provider và host có thể dùng hai bản interface cùng tên do loader khác nhau định nghĩa |
| `NoClassDefFoundError` hoặc `NoSuchMethodError` | Lớp/thư viện phụ thuộc thiếu hoặc phiên bản runtime không tương thích |
| Task sau thấy sai provider | TCCL trên thread pool không được khôi phục; cache provider không được quản lý |
| Plugin JAR cũ khó thu hồi | URLClassLoader, thread, ThreadLocal, cache, callback hoặc instance vẫn còn tham chiếu |

Một đoạn kiểm tra bên trong một phương thức có xử lý `IOException`:

```java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
System.out.println("TCCL=" + tccl);

String path = "META-INF/services/" + Greeter.class.getName();
if (tccl != null) {
    var urls = tccl.getResources(path);
    while (urls.hasMoreElements()) {
        System.out.println(urls.nextElement());
    }
}
```

Đoạn này giả định `Greeter` đã có trong phạm vi; không phải một chương trình độc lập. Nội dung URL và chuỗi `toString()` của classloader khác nhau theo môi trường. `getResources` có thể tìm nhiều descriptor cùng tên từ các JAR khác nhau.

Chỉ kiểm tra `getResource(...) != null` **chưa chứng minh** provider hợp lệ: tệp có thể khai báo lớp không tồn tại hoặc không tạo được instance. Ngược lại, không thấy descriptor với **một** loader không chứng minh mọi loader đều không thể thấy nó.

## 8. Giới hạn và nguyên tắc thiết kế

- **Phân tách khám phá với kích hoạt:** thấy provider không đồng nghĩa host đã gọi `start()` hay chấp nhận nó cho nghiệp vụ. Mã khởi tạo tĩnh và constructor provider có thể chạy khi thực sự tạo instance.
- **Tương thích kiểu:** đảm bảo host và plugin chia sẻ cùng định danh service type; không đóng gói một bản API riêng rồi yêu cầu host ép về bản khác.
- **Quản lý lifecycle:** `URLClassLoader.close()` không lập tức dỡ mọi class đã nạp. Nếu còn tham chiếu đến loader, provider, `ThreadLocal`, cache hoặc thread thì chúng có thể tiếp tục tồn tại.
- **Giữ ngữ cảnh đúng thread:** đặt TCCL tại nơi gọi thư viện và khôi phục bằng `finally`, kể cả khi xảy ra lỗi.
- **Không dùng TCCL như cơ chế cách ly:** TCCL không cấp quyền, kiểm tra tin cậy hay tự xử lý xung đột phiên bản thư viện. Những việc đó cần thiết kế cơ chế quản lý plugin riêng.
- **Ưu tiên tham số rõ ràng:** khi kiểm soát code gọi `ServiceLoader`, dùng overload nhận loader để tránh phụ thuộc vào trạng thái ngầm của thread.

## 9. Câu hỏi và thực hành

1. **Vì sao loader cha thường không thấy provider ở loader con?** Vì ủy quyền parent-first giúp con tìm lên cha, không tự tạo khả năng tìm ngược từ cha xuống con. TCCL cho thư viện biết loader nhìn thấy plugin khi nó chọn đọc TCCL.
2. **Đổi TCCL có đổi `Greeter.class.getClassLoader()` không?** Không; bộ nạp định nghĩa kiểu là thuộc tính của lớp đã được định nghĩa.
3. **Overload nào của ServiceLoader ít phụ thuộc ngữ cảnh ẩn hơn?** `load(service, loader)` vì loader được truyền trực tiếp.
4. **Vì sao trong ví dụ `descriptor=true` mà `before=none`?** Vì hai phép kiểm tra dùng hai loader khác nhau: pluginLoader thấy tài nguyên, còn TCCL mặc định chưa thấy plugin JAR.
5. **Điều gì xảy ra nếu task trong thread pool không khôi phục TCCL?** Task sau có thể sử dụng nhầm pluginLoader cũ và giữ loader đó sống lâu.
6. **`reload()` có tự thêm JAR mới vào URLClassLoader không?** Không. Nó làm mới cache nội bộ của ServiceLoader, còn classpath/classloader cần được quản lý riêng.
7. **Có nên xem TCCL là cách giải quyết lỗi `ClassCastException` giữa hai bản service interface?** Không. Phải sửa ranh giới API và định danh lớp.

**Thực hành:** chạy ví dụ, thử bỏ lệnh thiết lập TCCL, thử gọi overload nhận loader ở các vị trí khác nhau, rồi chuyển bước khám phá vào một task trên `ExecutorService`. In TCCL **trong task** để quan sát rõ ngữ cảnh thực tế của worker thread.

## Tài liệu tham khảo

- Java SE 17 — `Thread.getContextClassLoader`, `Thread.setContextClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Java SE 17 — `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 — `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 — `ScriptEngineManager`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html

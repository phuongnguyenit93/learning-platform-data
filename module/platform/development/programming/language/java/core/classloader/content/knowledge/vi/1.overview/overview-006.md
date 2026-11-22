# Một ví dụ xuyên suốt: ứng dụng chủ và plugin trong Java ClassLoader

## 1. Bài toán và điều cần quan sát

Giả sử một ứng dụng **host** muốn hỗ trợ nhiều tính năng mở rộng (plugin). Host biết một **hợp đồng Java** chung, nhưng không cần biết trước tên lớp triển khai hoặc biên dịch lại mỗi khi có plugin mới. Mỗi plugin được đóng gói trong một tệp JAR độc lập và được nạp khi host chạy.

Bài này dựng một ví dụ Java 17+ có thể chạy từ đầu đến cuối, qua đó trả lời các câu hỏi:

- Host và plugin nhìn thấy nhau qua interface nào?
- Ai nạp lớp API, ai nạp lớp triển khai của plugin?
- Vì sao cùng tên lớp chưa chắc là cùng kiểu Java?
- `ServiceLoader` tìm plugin qua metadata của JAR như thế nào?
- Khi thay JAR hoặc đóng `URLClassLoader`, điều gì thực sự xảy ra?

Mục tiêu là hiểu **đường đi của lớp và hợp đồng giữa host với plugin**. Đây là ví dụ plugin chạy trong **cùng JVM**, không phải sandbox bảo mật và không tạo tiến trình riêng.

## 2. Sơ đồ kiến trúc và ranh giới nạp lớp

~~~text
JVM
├── Application ClassLoader (cha)
│   ├── demo.api.GreetingPlugin        ← API chung, host sở hữu
│   └── demo.host.HostApp              ← chương trình host
│
└── URLClassLoader (con, parent = loader của GreetingPlugin)
    └── hello-plugin.jar
        ├── demo.plugins.HelloPlugin   ← lớp triển khai
        └── META-INF/services/demo.api.GreetingPlugin
~~~

`HostApp` tạo một `URLClassLoader` với **parent** là ClassLoader đã nạp `GreetingPlugin`. Trong hành vi ủy quyền thông thường của `URLClassLoader`, khi plugin cần `demo.api.GreetingPlugin`, loader của plugin hỏi cha trước. Vì vậy cả host và plugin dùng chung **một** đối tượng `Class<?>` của interface.

Ngược lại, `HelloPlugin` chỉ có trong JAR của plugin, không có trên classpath khởi động của host. Khi cần triển khai này, ClassLoader con tìm được nó trong JAR.

Luồng phụ thuộc:

~~~text
host source ──depends on──> api source
plugin source ─depends on──> api source
host runtime ──loads───────> plugin JAR bằng URLClassLoader
~~~

**Quy tắc thiết kế:** API chung thuộc phía host/parent; plugin JAR chỉ mang phần triển khai và tệp khai báo dịch vụ. Nếu mỗi bên cố dùng một bản API do loader riêng định nghĩa, việc ép kiểu có thể thất bại, ngay cả khi hai class có cùng tên đầy đủ.

## 3. Cấu trúc thư mục

Tạo dự án nhỏ sau; các thư mục `build/` và `dist/` sẽ được sinh bằng lệnh biên dịch ở phần 5:

~~~text
host-plugin-demo/
├── api/
│   └── demo/api/GreetingPlugin.java
├── host/
│   └── demo/host/HostApp.java
├── plugin/
│   └── demo/plugins/HelloPlugin.java
└── plugin-resources/
    └── META-INF/services/demo.api.GreetingPlugin
~~~

### 3.1. API chung: `api/demo/api/GreetingPlugin.java`

~~~java
package demo.api;

public interface GreetingPlugin {
    String id();

    String greet(String name);
}
~~~

`GreetingPlugin` là hợp đồng ổn định. Host chỉ gọi `id()` và `greet(String)` thông qua interface này, không `import` hoặc khởi tạo trực tiếp `HelloPlugin`.

### 3.2. Plugin: `plugin/demo/plugins/HelloPlugin.java`

~~~java
package demo.plugins;

import demo.api.GreetingPlugin;

public final class HelloPlugin implements GreetingPlugin {
    @Override
    public String id() {
        return "hello";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Lớp triển khai có `public` constructor không đối số mặc định (vì không tự khai báo constructor), đáp ứng cách khởi tạo provider dựa trên classpath của `ServiceLoader`. Nó tham chiếu interface API lúc biên dịch, nhưng mã bytecode của API **không cần được đóng gói lại** trong plugin JAR.

### 3.3. Đăng ký provider bằng tài nguyên của JAR

Tạo tệp văn bản **`plugin-resources/META-INF/services/demo.api.GreetingPlugin`** với đúng một dòng:

~~~text
demo.plugins.HelloPlugin
~~~

Tên tệp phải khớp **tên đầy đủ của interface**; mỗi dòng hữu hiệu trong tệp là tên đầy đủ của một provider. Đây **không phải** tệp Java, và phải được đưa vào JAR đúng vị trí `META-INF/services/`. Nếu thiếu hoặc viết sai đường dẫn, `ServiceLoader` thường không tìm thấy provider, dù `HelloPlugin.class` vẫn có trong JAR.

### 3.4. Host: `host/demo/host/HostApp.java`

~~~java
package demo.host;

import demo.api.GreetingPlugin;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class HostApp {
    private HostApp() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: HostApp <path-to-plugin-jar>");
        }

        Path pluginJar = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(pluginJar)) {
            throw new IllegalArgumentException("Plugin JAR not found: " + pluginJar);
        }

        // API chung đã được nạp từ classpath của ứng dụng chủ.
        ClassLoader parent = GreetingPlugin.class.getClassLoader();
        URL[] pluginUrls = {pluginJar.toUri().toURL()};

        // URLClassLoader chỉ sở hữu việc tìm bytecode/resources của plugin.
        try (URLClassLoader pluginLoader = new URLClassLoader(pluginUrls, parent)) {
            Class<?> apiSeenByPlugin =
                    pluginLoader.loadClass("demo.api.GreetingPlugin");

            System.out.println(
                    "Shared API: " + (apiSeenByPlugin == GreetingPlugin.class));

            // Chủ động truyền loader chứa provider và META-INF/services.
            ServiceLoader<GreetingPlugin> services =
                    ServiceLoader.load(GreetingPlugin.class, pluginLoader);

            int count = 0;
            for (GreetingPlugin plugin : services) {
                count++;
                System.out.println("Plugin ID: " + plugin.id());
                System.out.println("Greeting: " + plugin.greet("Java"));
                System.out.println(
                        "Implementation from child: "
                                + (plugin.getClass().getClassLoader() == pluginLoader));
            }
            System.out.println("Providers: " + count);
        }
    }
}
~~~

Ba điểm cốt lõi trong mã host:

1. `GreetingPlugin.class.getClassLoader()` xác định loader đã định nghĩa API. Truyền nó làm **parent** để plugin dùng cùng kiểu giao tiếp.
2. `ServiceLoader.load(GreetingPlugin.class, pluginLoader)` yêu cầu tìm khai báo provider bằng loader của plugin. `ServiceLoader` thường chỉ thực sự tra cứu và khởi tạo provider khi bắt đầu **duyệt**.
3. `try (URLClassLoader ...)` gọi `close()` sau khi dùng, giải phóng tài nguyên mà loader nắm giữ (như handle JAR); nó **không** bắt JVM lập tức dỡ các lớp đã nạp.

## 4. Phân biệt build-time classpath và runtime classpath

| Giai đoạn | Classpath | Mục đích |
|---|---|---|
| Biên dịch API | Không cần thư viện riêng | Tạo `GreetingPlugin.class` |
| Biên dịch host | `build/api` | Host nhận biết interface |
| Biên dịch plugin | `build/api` | Plugin implements đúng interface |
| Chạy host | `build/api` và `build/host` | **Không** đưa `hello-plugin.jar` lên classpath chính |
| Nạp plugin lúc chạy | URL của `hello-plugin.jar` | ClassLoader con tìm provider và class triển khai |

Host phải khởi chạy mà **không** cho plugin JAR vào classpath hệ thống. Nếu đặt JAR ở đó, Application ClassLoader có thể nạp luôn `HelloPlugin`, khiến thí nghiệm không còn chứng minh được ranh giới loader như thiết kế.

## 5. Biên dịch, đóng gói và chạy

Yêu cầu: **JDK 17 trở lên**, có `java`, `javac` và `jar` trên `PATH`. Chạy lệnh từ thư mục `host-plugin-demo/`. Dùng đúng các tệp đã tạo ở phần 3.

**Bash (Linux, macOS, Git Bash):**

~~~bash
mkdir -p build/api build/host build/plugin dist/plugins

javac -encoding UTF-8 -d build/api \
  api/demo/api/GreetingPlugin.java

javac -encoding UTF-8 -cp build/api -d build/host \
  host/demo/host/HostApp.java

javac -encoding UTF-8 -cp build/api -d build/plugin \
  plugin/demo/plugins/HelloPlugin.java

cp -R plugin-resources/META-INF build/plugin/

jar --create --file dist/plugins/hello-plugin.jar -C build/plugin .

java -cp "build/api:build/host" \
  demo.host.HostApp dist/plugins/hello-plugin.jar
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/api,build/host,build/plugin,dist/plugins | Out-Null

javac -encoding UTF-8 -d build/api api/demo/api/GreetingPlugin.java

javac -encoding UTF-8 -cp build/api -d build/host host/demo/host/HostApp.java

javac -encoding UTF-8 -cp build/api -d build/plugin plugin/demo/plugins/HelloPlugin.java

Copy-Item -Path plugin-resources/META-INF -Destination build/plugin -Recurse -Force

jar --create --file dist/plugins/hello-plugin.jar -C build/plugin .

java -cp "build/api;build/host" demo.host.HostApp dist/plugins/hello-plugin.jar
~~~

Ở bước đóng gói, `build/plugin/` chỉ chứa `demo/plugins/HelloPlugin.class` và `META-INF/services/demo.api.GreetingPlugin`. Có thể kiểm tra bằng:

~~~bash
jar --list --file dist/plugins/hello-plugin.jar
~~~

Đảm bảo có hai entry quan trọng: `demo/plugins/HelloPlugin.class` và `META-INF/services/demo.api.GreetingPlugin`. Lệnh `jar --list` có thể liệt kê thêm các thư mục và `META-INF/MANIFEST.MF`.

**Stdout chính xác của lệnh chạy host với đúng một plugin trên classpath đã nêu:**

~~~text
Shared API: true
Plugin ID: hello
Greeting: Hello, Java!
Implementation from child: true
Providers: 1
~~~

Không in định danh dạng `URLClassLoader@...` vì phần hậu tố phụ thuộc lần chạy. Các dòng `true` ở trên kiểm chứng trực tiếp điều cần học, thay vì dựa vào chuỗi `toString()` của ClassLoader.

## 6. Diễn tiến trong JVM, từ đầu đến cuối

1. JVM khởi động `demo.host.HostApp` bằng Application ClassLoader; `GreetingPlugin` cũng được định nghĩa từ `build/api` trên classpath này.
2. Host kiểm tra JAR tồn tại và tạo `URLClassLoader(pluginUrls, parent)`. Việc **khởi tạo loader không có nghĩa tất cả class trong JAR được nạp ngay**.
3. Host yêu cầu `pluginLoader.loadClass("demo.api.GreetingPlugin")`. Loader con ủy quyền cho parent. Parent đã có interface nên kết quả chính là `GreetingPlugin.class`: `Shared API: true`.
4. `ServiceLoader.load(...)` tạo đối tượng tra cứu dịch vụ. Khi vòng `for` bắt đầu, `ServiceLoader` tìm resource `META-INF/services/demo.api.GreetingPlugin` mà `pluginLoader` nhìn thấy.
5. Tệp dịch vụ chỉ tới `demo.plugins.HelloPlugin`. Loader con hỏi parent trước; parent không tìm thấy triển khai trên classpath host, nên loader con nạp `HelloPlugin.class` từ plugin JAR.
6. Khi liên kết lớp triển khai với interface, `demo.api.GreetingPlugin` được resolve qua cùng parent. Vì vậy `HelloPlugin` đúng là một `GreetingPlugin` mà host có thể gọi.
7. `ServiceLoader` khởi tạo provider và trả về đối tượng qua interface; host gọi `id()`, `greet("Java")`. `plugin.getClass().getClassLoader() == pluginLoader` là `true`.
8. Hết phạm vi `try`, loader được đóng. Việc tải lớp vào JVM, việc đóng nguồn JAR và việc dỡ lớp khi GC là **ba thời điểm khác nhau**.

Điểm thường gây nhầm lẫn: **parent delegation không có nghĩa mọi lớp đều do parent nạp**. Loader con nhờ parent tìm trước; khi parent không có `HelloPlugin`, loader con vẫn có thể tự định nghĩa nó từ JAR.

## 7. Bản sắc lớp: tên đầy đủ chưa đủ

Trong JVM, bản sắc kiểu tham chiếu được quyết định bởi **tên nhị phân của class/interface cùng với ClassLoader đã định nghĩa nó**. Chẳng hạn hai lớp đều có tên `demo.api.GreetingPlugin` nhưng được *hai loader độc lập định nghĩa* thì đó là hai kiểu khác nhau. Lỗi thường gặp là `ClassCastException` hoặc `ServiceConfigurationError: ... not a subtype` khi một bên cố dùng provider của bên kia.

Ví dụ hiện tại tránh xung đột nhờ:

- Chỉ **một bản API dùng ở runtime**: `GreetingPlugin.class` thuộc Application ClassLoader.
- Plugin loader sử dụng API này qua parent.
- Plugin JAR chứa triển khai và metadata; host có thể thao tác plugin dưới dạng interface chung.

Không nên kết luận rằng **cứ chép API vào hai JAR là lập tức có hai kiểu khác nhau**. Với `URLClassLoader` mặc định ủy quyền cho parent, ngay cả khi JAR con lỡ chứa API, parent vẫn thường được hỏi trước. Vấn đề xuất hiện khi **thực sự có hai loader tự định nghĩa API** (ví dụ hai classloader độc lập, hoặc một chiến lược child-first đặc biệt). Kiểu `String` hay kiểu thuộc `java.*` vẫn do cơ chế loader nền tảng quản lý theo cách riêng.

Một phép kiểm tra hữu ích là so sánh **bằng `==` trên `Class<?>`** giống `Shared API` trong chương trình; chỉ nhìn `getName()` không đủ.

## 8. Mở rộng ví dụ một cách có kiểm soát

**Thêm plugin thứ hai.** Tạo `ByePlugin implements GreetingPlugin`, đặt class của nó vào cùng plugin JAR và thêm tên đầy đủ `demo.plugins.ByePlugin` vào một dòng khác của tệp `META-INF/services/demo.api.GreetingPlugin`. Nếu cả hai provider có thể khởi tạo và tuân thủ interface, vòng lặp sẽ duyệt hai provider. Thứ tự phụ thuộc thứ tự khai báo/tìm kiếm provider; code nghiệp vụ không nên tự suy diễn ưu tiên từ thứ tự ngẫu nhiên của các JAR.

**Thay phiên bản plugin.** Biên dịch JAR mới, tạo **ClassLoader mới** trỏ vào JAR mới rồi tra cứu provider từ loader mới. Đối tượng và class cũ không tự biến thành phiên bản mới. Để có cơ hội thu hồi loader cũ, host phải thôi giữ các tham chiếu đến object/class/loader cũ; đồng thời plugin cần dừng thread, hủy đăng ký listener, đóng tài nguyên và dọn `ThreadLocal` hoặc cache có thể giữ các tham chiếu đó. `close()` đơn lẻ không bảo đảm class unloading.

**Plugin cần thư viện phụ thuộc.** Nếu thư viện không có trong parent, thêm JAR phụ thuộc vào `URL[]` của loader plugin (hoặc đóng gói đúng cách với kiểm soát xung đột). Đừng mặc định các plugin có thể tự chia sẻ mọi phiên bản thư viện: parent-first có thể chọn bản từ host; ngược lại các loader riêng có thể tạo ra những bản class không tương thích.

**Tài nguyên và metadata.** ClassLoader không chỉ tìm `.class` mà còn cung cấp resource qua `getResource(s)`. `ServiceLoader` trên classpath sử dụng tệp cấu hình `META-INF/services/...` để phát hiện provider. Vì vậy “class có trong JAR” và “service được phát hiện” là hai điều kiện khác nhau.

**Thread Context ClassLoader (TCCL).** Một số framework gọi `ServiceLoader.load(GreetingPlugin.class)` theo overload sử dụng context loader của thread. Trong tình huống đó provider có thể không được tìm thấy nếu context loader vẫn là loader của host. Ví dụ chủ động truyền `pluginLoader` để tránh phụ thuộc ngầm vào TCCL. Khi tích hợp thư viện thật có thể cần đặt lại context loader tạm thời, luôn khôi phục giá trị cũ trong `finally` và hiểu ảnh hưởng đến mã chạy trên cùng thread.

## 9. Lỗi phổ biến và cách xác minh

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra / xử lý |
|---|---|---|
| `Providers: 0` | Thiếu `META-INF/services/...`, sai FQCN, hoặc JAR không nằm trong loader đang truyền | `jar --list --file ...`; đọc đúng nội dung service descriptor; xác minh URL của loader |
| `ServiceConfigurationError` | Tên provider sai, class không public/không thể tạo instance, dependency thiếu, hoặc provider không đúng interface | Xem `cause` và stack trace, biên dịch lại với cùng API; kiểm tra constructor và classpath |
| `NoClassDefFoundError` | Provider tham chiếu class phụ thuộc không nhìn thấy từ loader plugin | Thêm dependency vào URL loader hoặc cung cấp qua parent theo thiết kế |
| `ClassCastException` hoặc “not a subtype” | Host/provider dùng hai `Class<?>` API do loader khác nhau định nghĩa | In `Class.getClassLoader()`; so sánh `Class<?>` bằng `==`; chia sẻ API qua parent |
| `Implementation from child: false` | Plugin class bị parent nạp trước, thường do plugin JAR ở classpath host | Chạy lại chỉ với `build/api;build/host` (Windows) hoặc `build/api:build/host` (Bash) |
| Đổi file JAR nhưng thấy hành vi cũ | Object/class vẫn thuộc loader cũ; plugin chưa được nạp lại bằng loader mới | Tạo loader/provider mới, thay tham chiếu nghiệp vụ có kiểm soát rồi dọn bản cũ |

**Hai lưu ý khi chẩn đoán:** `ClassNotFoundException` là ngoại lệ checked thường phát sinh từ yêu cầu tìm class; `NoClassDefFoundError` có thể xuất hiện khi JVM liên kết/khởi tạo class và không tìm được dependency dù class gốc đã được tìm thấy. Đồng thời, bản thân `ServiceLoader` có thể bọc lỗi provider thành `ServiceConfigurationError`; nên đọc stack trace gốc thay vì suy đoán chỉ từ số lượng provider.

## 10. Phạm vi an toàn và quyết định thiết kế

- Một JAR nạp bằng `URLClassLoader` chạy **mã thực trong cùng tiến trình và cùng quyền hệ điều hành của host**. ClassLoader là cơ chế phân giải và cách ly tên lớp ở mức JVM, **không phải ranh giới bảo mật** cho mã không tin cậy. Plugin chưa được tin cậy nên thực thi trong tiến trình/container tách biệt với cơ chế kiểm soát phù hợp.
- API nên ổn định: thay chữ ký của `GreetingPlugin` có thể làm plugin cũ không còn tương thích nhị phân. Có thể thêm version/khả năng tương thích của plugin và kiểm tra trước khi kích hoạt.
- Quản lý vòng đời nên là trách nhiệm của host: nạp, khởi tạo, kích hoạt, dừng, đóng tài nguyên và gỡ tham chiếu. Ví dụ tối giản chỉ minh họa **load → call → close**.
- Ví dụ dùng **classpath/unnamed modules**. Hệ thống plugin viết bằng JPMS named modules có quy tắc `module-info.java` và `ModuleLayer` riêng; không thể mặc nhiên coi `URLClassLoader` là cách xử lý đầy đủ mọi plugin JPMS.

## 11. Tự kiểm tra sau khi chạy

1. Bỏ file `META-INF/services/demo.api.GreetingPlugin` khỏi JAR, đóng gói lại rồi chạy: host vẫn tìm được API nhưng không discover provider; lý giải vì sao `Providers: 0`.
2. Khôi phục service descriptor, giữ nguyên lệnh chạy host không có plugin JAR trên classpath chính: xác minh `Shared API: true` và `Implementation from child: true`. Giải thích **hai kết quả khác nhau** bằng quy tắc ủy quyền cha.
3. Sửa `HelloPlugin.greet()` thành một chuỗi khác, chỉ biên dịch và đóng gói lại plugin, rồi chạy lại host: hợp đồng và mã host không đổi. Hãy chỉ ra phần nào được tái sử dụng và vì sao JVM mới hoặc ClassLoader mới nhìn thấy bytecode mới.

**Ghi nhớ:** Host và plugin giao tiếp qua **cùng một API do parent định nghĩa**, plugin triển khai được nạp qua **loader con**, `ServiceLoader` đọc metadata trong JAR để tạo provider; việc đóng loader và cập nhật phiên bản phải được quản lý như vòng đời của một thành phần động.
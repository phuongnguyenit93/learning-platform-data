# Tạo URLClassLoader từ thư mục và JAR

## 1. Bài toán: bổ sung nguồn lớp lúc chạy

Khi chương trình Java đã khởi động, đôi khi nó phải nạp plugin, extension, driver hoặc một thư viện bên ngoài mà không muốn đặt toàn bộ class/JAR ấy trên application classpath ban đầu. **`java.net.URLClassLoader`** là một class loader có sẵn, biết tìm lớp và tài nguyên qua **danh sách URL** trỏ tới thư mục chứa các tệp `.class` hoặc tới JAR.

Một ví dụ phổ biến: ứng dụng host có `PluginHost.class`, còn plugin `sample.Greeting` được biên dịch ra `out/plugin/sample/Greeting.class` hoặc được đóng gói thành `dist/plugin.jar`. Host tạo `URLClassLoader` với URL chỉ đúng **gốc package** hoặc **file JAR**, sau đó gọi `loadClass("sample.Greeting")`.

Các khái niệm:

- **URL search path**: các URL mà một `URLClassLoader` tìm kiếm **sau khi đã thử parent** theo chính sách parent-first mặc định.
- **Directory URL**: URL dùng lược đồ `file:`, kết thúc bằng dấu `/`, trỏ tới **thư mục gốc package**. Ví dụ `file:/home/user/app/out/plugin/`.
- **JAR URL**: thông thường là `file:` trỏ đến **chính file JAR**, chẳng hạn `file:/home/user/app/dist/plugin.jar`; `URLClassLoader` mở archive và tìm các entry theo đường dẫn package. API cũng hỗ trợ các URL thích hợp dùng giao thức `jar:`; trong tình huống file JAR thông thường, không cần tự ghép cú pháp `jar:file:...!/`.
- **Parent loader**: loader được hỏi trước. Thường nên dùng `PluginHost.class.getClassLoader()` để plugin có thể thấy các interface/API chung của ứng dụng.
- **Defining loader**: loader thực sự định nghĩa một lớp. Lấy bằng `SomeClass.class.getClassLoader()`; nó có thể khác đối tượng loader mà bạn gọi `loadClass` trên đó.

`URLClassLoader` hỗ trợ các lớp/tài nguyên trên classpath kiểu truyền thống. Nó **không** tự thiết lập một Java Platform Module System layer, không tự tìm mọi JAR nằm lồng bên trong một JAR khác, và không tự cấp môi trường sandbox bảo mật cho bytecode không tin cậy.

## 2. Cấu trúc URL và đường dẫn package phải đúng

Giả sử tên nhị phân của plugin là `sample.Greeting`. Tệp class tương ứng có đường dẫn `sample/Greeting.class` bên dưới **gốc** tìm kiếm.

### Trường hợp thư mục

~~~text
out/
└── plugin/                  <-- URL phải trỏ tới đây
    └── sample/
        ├── Greeting.class
        └── message.txt
~~~

URL hợp lệ theo ý nghĩa:

~~~text
file:/project/out/plugin/
~~~

`URLClassLoader` đổi tên nhị phân `sample.Greeting` thành đường dẫn tương ứng `sample/Greeting.class` và tìm bên dưới thư mục root. **Không** dùng `out/plugin/sample/` làm URL root nếu `sample` chính là package: khi đó loader sẽ tìm sai thành `.../sample/sample/Greeting.class`.

Theo Javadoc `URLClassLoader`, **URL `file:` kết thúc bằng `/` được coi là thư mục**; các URL `file:` khác được coi là tệp JAR để mở khi cần. Vì vậy dấu slash cuối cùng của URL thư mục rất quan trọng.

Để tạo URL một cách portable, ưu tiên:

~~~java
Path directory = Path.of("out", "plugin")
        .toAbsolutePath().normalize();
URL directoryUrl = directory.toUri().toURL();
~~~

Đoạn trên giả định thư mục **đã tồn tại**, vì cách `Path.toUri()` hình thành URL thư mục dựa vào thông tin filesystem; trong ví dụ đầy đủ ở phần 5, thư mục được tạo trước. Tránh tự nối chuỗi kiểu `"file://" + path` hoặc thay `\` bằng `/` thủ công; trên Windows, khoảng trắng, dấu ổ đĩa và ký tự đặc biệt cần được URI/URL encode đúng.

### Trường hợp JAR

~~~text
dist/
└── plugin.jar
    ├── META-INF/MANIFEST.MF
    └── sample/
        ├── Greeting.class
        └── message.txt
~~~

URL trỏ tới **file archive**:

~~~java
Path jarFile = Path.of("dist", "plugin.jar")
        .toAbsolutePath().normalize();
URL jarUrl = jarFile.toUri().toURL();
~~~

Ví dụ URL có thể hiển thị là `file:/project/dist/plugin.jar`; nó **không** kết thúc bằng `/`. `URLClassLoader` tự đọc các entry thích hợp từ JAR.

Không truyền `file:/project/dist/` rồi mặc định loader sẽ **tự quét mọi JAR** trong thư mục `dist`. Nếu đưa vào một directory URL thì nó dùng thư mục ấy làm nguồn các class file rời; các JAR muốn tham gia cần được liệt kê dưới dạng URL riêng hoặc thông qua metadata/thiết kế có hỗ trợ. Cú pháp wildcard như `lib/*` của Java launcher **không phải phép wildcard tự động của `new URLClassLoader(new URL[]{...})`**.

## 3. Khởi tạo URLClassLoader: constructor và parent

Các constructor thường dùng:

~~~java
URLClassLoader loader = new URLClassLoader(
        new URL[]{directoryUrl}, parentLoader);
~~~

~~~java
URLClassLoader loader = new URLClassLoader(
        new URL[]{jarUrl}, parentLoader);
~~~

Với nhiều nguồn, truyền một mảng URL:

~~~java
URLClassLoader loader = new URLClassLoader(
        new URL[]{directoryUrl, firstJarUrl, secondJarUrl},
        PluginHost.class.getClassLoader());
~~~

Đây là các **đoạn minh họa**, giả định mọi biến URL và `PluginHost` đã tồn tại; code chạy độc lập nằm ở phần 5. Danh sách URL được xét **theo thứ tự đã đưa**, nhưng chỉ sau khi parent được thử theo cách tìm mặc định.

| Constructor | Ý nghĩa |
| --- | --- |
| `new URLClassLoader(urls)` | Dùng parent mặc định theo cơ chế `ClassLoader`. |
| `new URLClassLoader(urls, parent)` | Chỉ rõ loader được ủy quyền trước. |
| `new URLClassLoader("plugin-loader", urls, parent)` | Đặt tên loader để hỗ trợ chẩn đoán (Java 9+). |
| `new URLClassLoader(urls, null)` | Parent delegation tương ứng bootstrap; **không** có nghĩa loader này là bootstrap và có thể làm thiếu các API không do bootstrap định nghĩa. |

**Khuyến nghị:** nếu host chia sẻ một interface, ví dụ `api.Plugin`, cho interface ấy nằm ở parent và cho child nạp lớp triển khai. Plugin dùng cùng `api.Plugin` mà host nhìn thấy, tránh hai bản định nghĩa interface có cùng tên nhưng khác defining loader.

### Parent-first không có nghĩa mọi lớp đều do parent định nghĩa

Mặc định `ClassLoader.loadClass`:

~~~text
Host yêu cầu loader.loadClass("sample.Greeting")
                      |
                      v
            Child đã có lớp?
                      |
                   Chưa có
                      |
                      v
        Parent.loadClass("sample.Greeting")
                 /           \
            Tìm được        Không thấy
                |               |
                v               v
        Trả Class parent   Child.findClass(...)
                                |
                         Tìm trong các URL
                                |
                         Định nghĩa class
~~~

Nếu parent đã có `sample.Greeting` trên application classpath, URLClassLoader con có thể trả **bản của parent**, chứ không định nghĩa bản bên trong JAR plugin. Muốn kiểm chứng lớp do đâu định nghĩa, dùng:

~~~java
Class<?> type = loader.loadClass("sample.Greeting");
boolean loadedByChild = type.getClassLoader() == loader;
~~~

Trong ví dụ độc lập bên dưới, plugin được cố ý **không** đặt trên classpath của host để phép kiểm chứng này luôn là `true`.

## 4. Hai API quan trọng: loadClass và tìm resource

### Nạp class theo binary name

~~~java
Class<?> type = loader.loadClass("sample.Greeting");
~~~

Tên phải ở dạng **binary name** (dấu `.` phân cách package). Không truyền `"sample/Greeting.class"` hay đường dẫn JAR vào `loadClass`. `loadClass` trả đối tượng `Class<?>`; bản thân lời gọi này không chủ động initialize static initializer của `Greeting`.

Để khởi tạo hoặc sử dụng kiểu động, có thể dùng reflection:

~~~java
String result = (String) type.getMethod("hello").invoke(null);
~~~

Đây là ví dụ gọi phương thức **static public `hello()`**, nên `Method.invoke(null)` hợp lệ. Lời gọi static method là active use; nếu class chưa khởi tạo thì JVM chạy khối static initializer trước khi thân method chạy. Với phương thức instance, phải tạo đối tượng hợp lệ và truyền instance thay vì `null`.

Nếu chỉ cần lấy đối tượng `Class<?>` mà chưa kích hoạt initialization, `loader.loadClass(name)` thường đúng mục đích. Còn `Class.forName(name, true, loader)` **chủ động yêu cầu initialization**, khác với `Class.forName(name, false, loader)`.

### Nạp resource qua URLClassLoader

URLClassLoader cũng có thể tìm resource trên cùng search path:

~~~java
URL configUrl = loader.getResource("sample/message.txt");
InputStream in = loader.getResourceAsStream("sample/message.txt");
~~~

Các tên resource của `ClassLoader` bắt đầu **từ gốc resource** và dùng dấu `/`; không thêm dấu `/` đầu giống kiểu absolute path của `Class.getResource`. Nếu không thấy, API có thể trả `null`.

Đọc dữ liệu bằng stream sẽ hoạt động tương tự khi resource nằm ở file trong thư mục hoặc entry bên trong JAR. Đặc biệt, không ép URL `jar:file:...!/sample/message.txt` thành một `java.io.File` trên ổ đĩa.

## 5. Thực hành Java 17+: cùng plugin trong thư mục và JAR

Bài thực hành có **hai tệp nguồn Java** ở hai phần độc lập: plugin được compile vào `out/plugin`, host được compile vào `out/host`. Sau đó đóng gói plugin thành `dist/plugin.jar`. Host chạy chỉ với `out/host` trên application classpath, nên plugin chỉ được tìm thấy bởi URLClassLoader do host tạo.

Cấu trúc làm việc:

~~~text
example/
├── src/
│   ├── plugin/
│   │   └── sample/Greeting.java
│   └── host/
│       └── PluginHost.java
├── out/
│   ├── plugin/          <-- tạo sau khi compile
│   └── host/            <-- tạo sau khi compile
└── dist/
    └── plugin.jar       <-- tạo sau khi đóng gói
~~~

### File `src/plugin/sample/Greeting.java`

~~~java
package sample;

public class Greeting {
    static {
        System.out.println("Greeting initialized");
    }

    public static String hello() {
        return "hello from plugin";
    }
}
~~~

Thông điệp trong khối static giúp quan sát mỗi lớp được **khởi tạo một lần đối với định nghĩa class cụ thể của nó**. Khi có hai loader định nghĩa cùng tên, mỗi bản `sample.Greeting` có quá trình khởi tạo riêng.

### File `src/host/PluginHost.java`

~~~java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class PluginHost {
    private static void inspect(String label, URL url) throws Exception {
        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{url}, PluginHost.class.getClassLoader())) {
            Class<?> type = loader.loadClass("sample.Greeting");

            System.out.println(label + " owns class: "
                    + (type.getClassLoader() == loader));
            System.out.println(label + " message: "
                    + type.getMethod("hello").invoke(null));

            try (InputStream in =
                         loader.getResourceAsStream("sample/message.txt")) {
                if (in == null) {
                    throw new IllegalStateException("missing resource");
                }
                System.out.println(label + " resource: "
                        + new String(in.readAllBytes(),
                                StandardCharsets.UTF_8).trim());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("dir jar");
        }

        URL dir = Path.of(args[0]).toAbsolutePath()
                .normalize().toUri().toURL();
        URL jar = Path.of(args[1]).toAbsolutePath()
                .normalize().toUri().toURL();

        System.out.println("directory URL ends in /: "
                + dir.toExternalForm().endsWith("/"));
        System.out.println("JAR URL ends in .jar: "
                + jar.toExternalForm().endsWith(".jar"));

        inspect("directory", dir);
        inspect("JAR", jar);
    }
}
~~~

Điểm học tập trong mã:

1. `Path.of(args[0]).toAbsolutePath().normalize().toUri().toURL()` tạo URL từ đường dẫn thư mục được truyền.
2. `Path.of(args[1])...toURL()` tạo URL từ đường dẫn JAR được truyền.
3. Mỗi lần `inspect` tạo **một URLClassLoader mới**, có parent là loader của `PluginHost` và chỉ một nguồn URL.
4. `loader.loadClass("sample.Greeting")` tìm class trong parent trước; ở ví dụ này parent không có plugin nên child định nghĩa.
5. `type.getClassLoader() == loader` kiểm chứng defining loader thực tế.
6. Reflection `type.getMethod("hello").invoke(null)` kích hoạt static initialization khi cần, sau đó gọi method và trả chuỗi.
7. `getResourceAsStream("sample/message.txt")` tìm file văn bản từ cả hai nguồn. Code xử lý `null` và đóng stream.
8. `try (URLClassLoader loader = ...)` bảo đảm gọi `close()` khi rời block, kể cả khi exception xảy ra.

### Biên dịch và chạy trên Linux/macOS

Đứng trong thư mục `example` (đã tạo hai source Java ở trên):

~~~bash
mkdir -p out/plugin/sample out/host dist

javac -d out/plugin src/plugin/sample/Greeting.java
printf 'resource from plugin\n' > out/plugin/sample/message.txt

javac -d out/host src/host/PluginHost.java
jar --create --file dist/plugin.jar -C out/plugin .

java -cp out/host PluginHost out/plugin dist/plugin.jar
~~~

**Quan trọng:** chỉ truyền `out/host` qua `-cp` lúc chạy. Không thêm `out/plugin` hoặc `dist/plugin.jar` vào application classpath; nếu thêm, parent có thể nhìn thấy plugin trước và ví dụ sẽ không còn chứng minh child định nghĩa class.

### Biên dịch và chạy trên Windows PowerShell

Đứng trong thư mục `example`:

~~~powershell
New-Item -ItemType Directory -Force out\plugin\sample, out\host, dist | Out-Null

javac -d out\plugin src\plugin\sample\Greeting.java
Set-Content -Path out\plugin\sample\message.txt -Value "resource from plugin" -Encoding Ascii

javac -d out\host src\host\PluginHost.java
jar --create --file dist\plugin.jar -C out\plugin .

java -cp out\host PluginHost out\plugin dist\plugin.jar
~~~

Ở Windows, `Path.toUri().toURL()` xử lý đường dẫn ổ đĩa, dấu cách và các ký tự URI phù hợp; bạn không cần tự tạo URL chuỗi bằng cách ghép `file:///C:/...`. Trong ví dụ, resource chỉ có ký tự ASCII để kết quả giống nhau trên các shell.

### Stdout đã kiểm chứng

~~~text
directory URL ends in /: true
JAR URL ends in .jar: true
directory owns class: true
Greeting initialized
directory message: hello from plugin
directory resource: resource from plugin
JAR owns class: true
Greeting initialized
JAR message: hello from plugin
JAR resource: resource from plugin
~~~

Chương trình trên đã được biên dịch và chạy thành công bằng JDK trên Windows với chính cấu trúc thư mục/JAR đã mô tả.

### Giải thích kết quả

- `directory URL ends in /: true`: `Path.toUri()` từ thư mục hiện hữu tạo URL thư mục kết thúc bằng `/`.
- `JAR URL ends in .jar: true`: đối số thứ hai trỏ chính tệp `plugin.jar`.
- `directory owns class: true` và `JAR owns class: true`: mỗi URLClassLoader **tự định nghĩa** bản `sample.Greeting` từ nguồn tương ứng.
- `Greeting initialized` xuất hiện **hai lần** vì có **hai định nghĩa lớp trong hai loader khác nhau**, không phải vì JVM “khởi tạo lại cùng một class”.
- `directory/JAR message` có cùng nội dung vì hai nguồn chứa cùng bytecode của plugin.
- `directory/JAR resource` giống nhau vì resource `sample/message.txt` đã được copy vào gốc thư mục plugin rồi đóng gói trong JAR.

Điều kiện để đầu ra đúng là **file và URL được chuẩn bị đầy đủ**. Nếu JAR chỉ chứa `Greeting.class` mà thiếu `message.txt`, chương trình sẽ ném `IllegalStateException("missing resource")` tại bước đọc JAR.

## 6. Nếu cần nạp nhiều JAR hoặc kết hợp thư mục và JAR

Truyền nhiều URL cùng lúc là cách trực tiếp:

~~~java
URL[] sources = {
    Path.of("out/plugin").toAbsolutePath().toUri().toURL(),
    Path.of("lib/dependency-a.jar").toAbsolutePath().toUri().toURL(),
    Path.of("lib/dependency-b.jar").toAbsolutePath().toUri().toURL()
};

try (URLClassLoader loader =
             new URLClassLoader(sources, PluginHost.class.getClassLoader())) {
    Class<?> plugin = loader.loadClass("sample.Greeting");
    // Sử dụng plugin ở đây.
}
~~~

Đoạn này là **mã minh họa dùng trong ngữ cảnh có đủ file**, không chạy độc lập nếu chưa tạo hai JAR phụ thuộc. Theo API, loader xét các URL **theo thứ tự đã cung cấp sau khi parent được xét**. Nếu hai URL đều chứa cùng một binary name, lớp đầu tiên tìm được theo chính sách tra cứu sẽ quyết định định nghĩa được dùng. Tránh hai version cùng class name để không có lỗi runtime khó dự đoán.

Một lỗi thường gặp là chỉ đưa `plugin.jar` vào URL mà quên các JAR có chứa dependency của plugin. `URLClassLoader` không tự quét thư mục chứa JAR để lục tìm các dependency; cần liệt kê URL phụ thuộc, dùng một cơ chế manifest phù hợp hoặc thiết lập loader tương ứng.

### JAR manifest Class-Path

Một JAR có thể khai báo thuộc tính `Class-Path` trong manifest để tham chiếu tới các JAR khác bằng URL tương đối, theo đặc tả JAR. Điều này có thể tác động tới quá trình tìm dependency, nhưng đừng coi nó là thay thế tuyệt đối cho một danh sách dependency được quản lý rõ ràng: phải kiểm tra file JAR thực tế, quan hệ đường dẫn, packaging và cách class loader sử dụng manifest.

### JAR lồng bên trong JAR

Một đường dẫn như `plugin.jar!/BOOT-INF/lib/dependency.jar` **không tự động** được xử lý như một tệp JAR bình thường khi chỉ truyền `file:/.../plugin.jar` cho URLClassLoader chuẩn. Một số framework có launcher/class loader riêng hỗ trợ nested JAR; đó là cơ chế bổ sung, không phải mặc định được bảo đảm của `URLClassLoader`.

## 7. Đóng URLClassLoader đúng cách và giới hạn của close()

`URLClassLoader` triển khai `Closeable`, vì vậy nên dùng *try-with-resources* để giải phóng các tài nguyên I/O gắn với JAR và URL:

~~~java
try (URLClassLoader loader = new URLClassLoader(
        new URL[]{jarUrl}, parentLoader)) {
    Class<?> clazz = loader.loadClass("sample.Greeting");
    // Thao tác với clazz và resource khi loader còn mở.
}
~~~

Những điểm quan trọng:

- `close()` đóng các JAR file được loader mở và ngừng khả năng dùng loader để nạp **class hoặc resource mới do chính loader định nghĩa**.
- `close()` **không hủy** các `Class<?>` hoặc instance đã được tạo, không tự ném mọi đối tượng plugin đang sống ra khỏi bộ nhớ.
- **Unload class** chỉ có thể xảy ra khi JVM quyết định và khi không còn những tham chiếu ngăn loader cùng các class liên quan được thu gom. Các tham chiếu từ static field, thread đang chạy, thread context loader, thread-local, callback/registry hoặc object plugin đều có thể giữ loader sống.
- Nếu bạn đã lấy `InputStream` từ resource, hãy **đóng stream riêng**. Nếu đóng loader khi còn đang đọc tài nguyên, hành vi đọc tiếp có thể không còn đáng tin; tài liệu API cũng cảnh báo phải đóng stream thích hợp.
- Đóng loader sau khi phục vụ xong plugin không tương đương “nạp lại version mới ngay lập tức”. Để có một namespace mới, thường cần tạo **loader mới**, tránh giữ tham chiếu class/object cũ và điều phối đúng vòng đời.
- `close()` có thể ném `IOException`; try-with-resources xử lý gọi close kể cả khi block lỗi, và exception vẫn phải được truyền/xử lý phù hợp.

**Không** giữ `URLClassLoader` như biến static toàn cục vô thời hạn nếu thiết kế chủ đích là load/unload plugin theo phiên. Ngược lại, cũng không đóng loader quá sớm nếu còn yêu cầu lazy loading hoặc tìm resource về sau.

## 8. Danh tính lớp, API chia sẻ và parent-first

Danh tính runtime của một class/interface Java thông thường gắn với **binary name + defining class loader**. Do đó:

~~~text
Parent loader: app.PluginApi
     |
     +---- child A: sample.Greeting (version A)
     |
     +---- child B: sample.Greeting (version B)
~~~

Nếu cả child A và child B đều tự định nghĩa `sample.Greeting`, chúng tạo hai kiểu khác nhau dù tên nhị phân giống hệt. Việc ép object từ bản này sang bản class của loader khác có thể gây `ClassCastException` hoặc lỗi liên kết. Đừng dùng chuỗi tên class để kết luận hai đối tượng `Class<?>` bằng nhau.

Để host làm việc với plugin an toàn hơn, đặt interface hợp đồng chung ở **parent**:

~~~java
package api;

public interface Plugin {
    String execute();
}
~~~

Trong JAR plugin:

~~~java
package plugin;

import api.Plugin;

public class Impl implements Plugin {
    @Override
    public String execute() {
        return "plugin result";
    }
}
~~~

Đây là **hai file Java minh họa tách biệt**, không nằm trong chương trình chạy ở phần 5. Khi `api.Plugin` đã được parent định nghĩa, child có thể hỏi parent để lấy cùng interface; host tải `plugin.Impl` bằng URLClassLoader rồi ép về `api.Plugin`. Đừng đóng gói một bản `api.Plugin` khác dưới chính sách child-first để tránh xung đột danh tính kiểu.

Một mẫu reflection khi loader còn mở:

~~~java
Class<?> implType = loader.loadClass("plugin.Impl");
api.Plugin plugin = (api.Plugin)
        implType.getDeclaredConstructor().newInstance();
String result = plugin.execute();
~~~

Điều kiện: `api.Plugin` nằm ở parent, plugin được biên dịch dựa trên cùng API, constructor tương ứng truy cập được, và không có xung đột module/security/accessibility. Đây là ví dụ riêng về API contract, không phải phần bắt buộc của chương trình `PluginHost` trước đó.

## 9. Những lỗi phổ biến và cách chẩn đoán

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException: sample.Greeting` khi truyền thư mục | URL trỏ nhầm `out/plugin/sample/` thay vì root `out/plugin/`; hoặc tên package/class không khớp. | Kiểm tra `sample/Greeting.class` có ngay dưới directory root. |
| `ClassNotFoundException` khi dùng URL file thư mục | Thiếu dấu `/` cuối, khiến URL `file:` bị hiểu không phải directory. | Tạo URL bằng `Path.of(existingDirectory).toUri().toURL()`. |
| `ClassNotFoundException` khi nạp JAR | URL trỏ sai file; JAR không chứa đúng entry; class có binary name khác. | Dùng `jar tf dist/plugin.jar`, kiểm tra `sample/Greeting.class`. |
| `NoClassDefFoundError` khi plugin dùng dependency | Dependency không có trong parent hoặc danh sách URL của child; hoặc class liên quan thất bại từ bước khác. | Xem cause và JAR chứa class cần thiết; thêm URL dependency đúng. |
| `ClassCastException` dù hai lớp cùng tên | Có hai defining loader khác nhau hoặc duplicate shared API. | Log `clazz.getClassLoader()` và kiểm tra interface ở parent. |
| `Plugin defined by child == false` | Parent đã nhìn thấy tên lớp trước vì host classpath chứa plugin. | Không đưa plugin JAR vào application `-cp` nếu muốn child định nghĩa. |
| Resource qua `getResourceAsStream` bằng `null` | Tệp chưa được copy vào root URL/JAR hoặc tên resource có `/` đầu không phù hợp. | Kiểm tra entry và dùng tên từ root như `sample/message.txt`. |
| `ClassFormatError` / `UnsupportedClassVersionError` | Bytecode không đúng định dạng hoặc build bằng target Java quá mới. | Kiểm tra `javac --release` và phiên bản JDK runtime. |
| `NoSuchMethodError` sau khi nạp được class | Phiên bản dependency runtime khác lúc compile; trùng JAR/loader. | So sánh dependency và nguồn loader, không chỉ tên class. |
| Trên Windows không thể thay thế/xóa JAR sau khi dùng | Loader còn giữ file handle tới JAR hoặc stream chưa được đóng. | Đóng stream và `URLClassLoader.close()`; kiểm tra tham chiếu sống. |
| Đóng loader xong vẫn thấy class/object hoạt động | `close` không lập tức unload lớp đã định nghĩa. | Hiểu vòng đời GC/loader, không dùng `close` như lệnh xóa class. |

### Cách debug thực tế

1. In các URL loader đang dùng qua `loader.getURLs()` để xác định directory có slash cuối và JAR trỏ đúng file.
2. In `type.getName()` và `type.getClassLoader()` để biết binary name và defining loader, không suy từ loader đã được gọi.
3. Dùng `jar tf plugin.jar` để kiểm tra entry; không truyền `sample/Greeting.class` cho `loadClass`.
4. Kiểm tra runtime application `-cp` có vô tình bao gồm plugin/dependency không. Nếu có, parent-first có thể lấy lớp parent.
5. Phân biệt `ClassNotFoundException` khi lookup theo tên với `NoClassDefFoundError` khi JVM giải phụ thuộc bị thiếu và `ExceptionInInitializerError` khi initializer lỗi.
6. Nếu host plugin thành công nhưng class dùng trong plugin lỗi, tìm dependency ở nguồn **defining loader của plugin** có thể nhìn thấy, không chỉ trong thư mục chứa JAR gốc.
7. Kiểm tra quyền truy cập reflection, tên method, constructor, module/package openness; nạp class thành công chưa bảo đảm gọi reflection thành công.

## 10. Những điều URLClassLoader không tự làm

- **Không tạo JPMS ModuleLayer:** truyền JAR vào URLClassLoader không đồng nghĩa resolve named module qua `--module-path` hoặc tạo module graph.
- **Không giải dependency kiểu Maven/Gradle:** nó tìm các bytecode/resource trong URL đã có (và những cơ chế mở rộng phù hợp) chứ không tự tải transitive dependencies từ repository.
- **Không hỗ trợ wildcard theo cú pháp launcher ở mảng URL:** phải tạo URL từng JAR hoặc tự liệt kê file bằng ứng dụng trước khi khởi tạo loader.
- **Không bảo đảm cô lập bảo mật:** custom class loader hoặc parent-child class loading **không là sandbox** cho plugin không tin cậy. Chỉ dùng plugin đáng tin cậy; thẩm định nguồn, checksum/chữ ký và quyền của tiến trình khi thích hợp.
- **Không đảm bảo reload bằng cách sửa file JAR tại chỗ:** với loader đang sống, các class đã định nghĩa không được thay bytecode trong cùng định nghĩa. Thường cần xây loader mới và kết thúc vòng đời loader cũ.
- **Không bảo đảm mọi URL có thể được tải an toàn:** URL từ network có thể chậm/không khả dụng và mở ra nguy cơ lấy code không tin cậy. Ví dụ học tập cố ý dùng file cục bộ, đường dẫn xác định trước.

## 11. Checklist ghi nhớ

Khi tạo URLClassLoader từ directory/JAR, hãy kiểm tra tuần tự:

1. Lớp cần nạp có **binary name** gì? Nó có đúng ở đường dẫn `package/Class.class` hay JAR entry tương ứng không?
2. Directory URL có trỏ tới **package root**, là URL `file:` và kết thúc bằng `/` không?
3. JAR URL có trỏ tới **chính file JAR** không? File có entry cần nạp không?
4. Có cần thêm URL của các JAR phụ thuộc? Có đang nhầm `lib/*` của launcher với mảng `URL[]`?
5. Parent loader là ai? Có chứa shared API hoặc một bản plugin trùng tên làm thay đổi defining loader không?
6. Đã dùng `loadClass("sample.Greeting")` với tên chấm package, thay vì file path không?
7. Có cần **khởi tạo** class hay chỉ load metadata? `loadClass` không thay thế `Class.forName(..., true, loader)`.
8. Có cần đọc resource? Dùng `loader.getResourceAsStream("sample/message.txt")` và kiểm tra `null`.
9. Đã đóng streams và loader trong đúng vòng đời chưa? Có đang giữ reference ngăn class unloading không?
10. Có đang giả định URLClassLoader là module loader, dependency manager hoặc security sandbox không? Nếu có, cần thiết kế khác phù hợp.

### Câu hỏi tự kiểm tra

**Câu 1.** Muốn nạp `com.example.Plugin` từ `plugins/classes/com/example/Plugin.class`, URL thư mục phải trỏ đâu?

**Đáp:** `plugins/classes/`, không phải `plugins/classes/com/example/`; dùng `Path.of("plugins/classes").toUri().toURL()` khi thư mục đã tồn tại.

**Câu 2.** Với `plugins/plugin.jar` chứa `com/example/Plugin.class`, nên truyền URL gì?

**Đáp:** URL của **file JAR** như `Path.of("plugins/plugin.jar").toUri().toURL()`; không cần tự viết `jar:file:...!/com/example/Plugin.class` làm URL search root.

**Câu 3.** `loader.loadClass(name)` trả lớp có `getClassLoader() != loader`. Có chắc URL bị sai?

**Đáp:** Không. Parent-first có thể trả lớp do parent định nghĩa. Kiểm tra parent classpath và defining loader.

**Câu 4.** Hai loader riêng đều nạp `sample.Greeting` từ cùng bytecode và gọi phương thức static. Vì sao khối static chạy hai lần?

**Đáp:** Chúng định nghĩa hai class runtime riêng theo cặp binary name + defining loader; mỗi class có trạng thái initialization riêng.

**Câu 5.** Đóng `URLClassLoader` xong có thể coi lớp và object plugin chắc chắn đã bị unload?

**Đáp:** Không. `close()` giải phóng tài nguyên I/O và ngừng nạp mới từ loader; unloading phụ thuộc vòng đời tham chiếu và quyết định GC/JVM.

## Tài liệu chuẩn

- [Java SE 21 – URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): constructor, URL thư mục/JAR, delegation, `getURLs`, `close()`.
- [Java SE 21 – ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent-first, resource lookup và defining loader.
- [Java SE 21 – Path.toUri()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html#toUri()): URI từ filesystem path.
- [JVMS Java SE 21 §5.3 – Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): danh tính class và class loader trong JVM.

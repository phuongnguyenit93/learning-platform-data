# Bổ sung khả năng tìm tài nguyên tương ứng với lớp trong ClassLoader tùy chỉnh

## 1. Vấn đề: tải được lớp nhưng không tìm được tài nguyên

Một ClassLoader tùy chỉnh có thể đọc bytecode từ thư mục, cơ sở dữ liệu, JAR hoặc kho lưu trữ riêng rồi dùng `defineClass(...)` để tạo runtime class. Nhưng nếu nó **chỉ override `findClass(...)`**, các tài nguyên đi kèm lớp — như `config.properties`, `messages.txt`, biểu mẫu hoặc descriptor dịch vụ — chưa chắc được tìm thấy bởi:

~~~java
Class<?> pluginType = customLoader.loadClass("demo.plugin.Widget");
URL url = pluginType.getResource("message.txt");
~~~

Hai thao tác đó đi qua **hai đường tra cứu khác nhau**:

- **Class lookup:** `loadClass` (thường ủy quyền parent trước) rồi `findClass` của custom loader.
- **Resource lookup:** `getResource`/`getResources` (thường hỏi parent trước) rồi `findResource`/`findResources` của custom loader.

Vì vậy, **nạp class thành công không tự động làm cho file dữ liệu bên cạnh `.class` có thể được tra cứu**. Khi viết custom ClassLoader, cần thiết kế đường tra cứu tài nguyên tương ứng với nơi lưu bytecode.

Mục tiêu bài này: từ một **thư mục gốc chứa cả `.class` và resource**, triển khai đủ `findClass`, `findResource`, `findResources`; kiểm tra resource tương đối với package, resource trùng tên với parent, và tránh hiểu lầm về thứ tự lookup. Ví dụ dùng **Java 17+** và chạy độc lập bằng `javac`/`java`.

## 2. Cặp phương thức class và resource

| API | Vai trò | Thường do ai gọi? |
|---|---|---|
| `ClassLoader.loadClass(name)` | Entry point tìm class, mặc định parent-first | Host, reflection, JVM/framework |
| `ClassLoader.findClass(name)` | Hook để loader tùy chỉnh **định nghĩa class** khi parent không tìm thấy | `loadClass` |
| `ClassLoader.getResource(name)` | Entry point tìm **một URL** của resource, mặc định parent-first | Host, `Class.getResource` qua defining loader |
| `ClassLoader.findResource(name)` | Hook tìm resource trong **nguồn riêng** của loader | `getResource` |
| `ClassLoader.getResources(name)` | Liệt kê **nhiều URL** theo cơ chế parent rồi resource riêng | Framework và ứng dụng |
| `ClassLoader.findResources(name)` | Hook liệt kê các resource trong **nguồn riêng** của loader | `getResources` |
| `ClassLoader.resources(name)` | Biểu diễn nhiều URL bằng `Stream<URL>` (Java 9+) | Ứng dụng dùng Stream API |
| `ClassLoader.getResourceAsStream(name)` | Mở `InputStream` cho resource đầu tiên | Ứng dụng đọc dữ liệu |

**Nguyên tắc thiết kế:** Khi loader của bạn có một kho lưu trữ chung cho bytecode và resource, `findClass` và `findResource(s)` nên dựa trên **cùng một root, cùng quy tắc ánh xạ đường dẫn và cùng vòng đời nguồn dữ liệu**.

Các hook `findResource`/`findResources` không định nghĩa class và không tự khởi tạo class. Chúng chỉ trả URL mà caller có thể mở để lấy dữ liệu. Ngược lại, `findClass` không tự quảng bá mọi file không phải class trong thư mục nguồn cho resource API.

## 3. Mapping từ tên class và tên resource

Giả sử tên binary class là `demo.plugin.Widget` và package là `demo.plugin`:

~~~text
Binary class name:     demo.plugin.Widget
Class file:            demo/plugin/Widget.class

Class-relative name:   message.txt
Resolved resource:     demo/plugin/message.txt

Root-relative name:    demo/plugin/message.txt
~~~

Quy tắc chủ yếu:

- `findClass("demo.plugin.Widget")` cần tìm `demo/plugin/Widget.class` trong class root.
- `ClassLoader.getResource("demo/plugin/message.txt")` tìm theo **tên resource từ root**. Thông thường **không** có dấu `/` ở đầu.
- `Widget.class.getResource("message.txt")` đổi tên tương đối thành `demo/plugin/message.txt` trước khi tìm qua loader của `Widget`.
- `Widget.class.getResource("/demo/plugin/message.txt")` xử lý dấu `/` đầu như **đường dẫn tuyệt đối theo resource root**, rồi bỏ slash này khi tra cứu loader.
- `Widget.class.getResourceAsStream("message.txt")` cũng tuân quy tắc đặt tên tương đối với package, nhưng trả stream thay vì URL.

Điểm quan trọng: `Class.getResource(...)` **không mặc định dùng Thread Context ClassLoader (TCCL)**. Nó gắn với class được gọi và loader/module của class đó. Vì thế nếu `Widget` được định nghĩa bởi loader tùy chỉnh, lời gọi `Widget.class.getResource("message.txt")` có thể tìm qua loader ấy — **miễn là loader đó triển khai lookup resource**.

## 4. Sơ đồ parent-first và phạm vi hook

Giả sử host sử dụng application loader (parent), plugin dùng `DirectoryLoader` (child):

~~~text
Caller gọi child.loadClass("demo.plugin.Widget")
    ├─ Parent thử tìm Widget
    └─ Không có → child.findClass("demo.plugin.Widget")
                       └─ đọc plugin-root/demo/plugin/Widget.class

Caller gọi child.getResource("demo/plugin/message.txt")
    ├─ Parent thử tìm message.txt
    └─ Không có → child.findResource("demo/plugin/message.txt")
                       └─ trả URL tới plugin-root/demo/plugin/message.txt

Caller gọi child.getResources("demo/plugin/shared.txt")
    ├─ Parent tìm shared.txt    → HOST_SHARED
    └─ child.findResources     → CHILD_SHARED
                                 |
                                 v
                     [URL(parent), URL(child)]
~~~

Với `ClassLoader` mặc định, bạn thường **không cần override `loadClass` hoặc `getResource`** để có parent-first. Override các hook `findClass`, `findResource` và `findResources` là đủ để cung cấp đường tìm riêng khi parent không tìm được hoặc khi cần liệt kê.

Nếu override `getResource` bằng một implementation chỉ tìm tài nguyên riêng, bạn có thể vô tình **bỏ qua tài nguyên của parent**. Nếu override `getResources` bằng một implementation chỉ trả tài nguyên riêng, bạn có thể làm mất các descriptor service/config của parent trong kết quả. Chỉ thay cơ chế delegation khi có lý do rõ ràng và thiết kế tương thích với các API khác.

## 5. Ví dụ Java 17+: DirectoryLoader hỗ trợ cả class và resource

Ta sẽ viết custom loader đọc từ một thư mục plugin trên đĩa, thay vì dùng `URLClassLoader` sẵn có, nhằm học cách bổ sung resource hooks một cách có kiểm soát.

Chương trình thể hiện hai trường hợp:

1. Resource `message.txt` **chỉ nằm trong plugin root** nên có thể được tìm bằng `Widget.class.getResource(...)` hoặc `DirectoryLoader.getResource(...)`.
2. Resource `shared.txt` xuất hiện **cả trong host root và plugin root**. Vì parent-first, lookup mặc định trả phiên bản của host; còn `findResource` trả phiên bản của child khi chủ động truy cập hook nguồn riêng.

### 5.1. Cấu trúc file

~~~text
directory-loader-demo/
├── src/
│   └── DirectoryLoaderDemo.java
├── plugin-src/
│   └── demo/plugin/Widget.java
├── host-resources/
│   └── demo/plugin/shared.txt
└── plugin-resources/
    └── demo/plugin/
        ├── message.txt
        └── shared.txt
~~~

Các file text là UTF-8 không BOM, có nội dung lần lượt:

| Đường dẫn | Nội dung |
|---|---|
| `host-resources/demo/plugin/shared.txt` | `HOST_SHARED` |
| `plugin-resources/demo/plugin/message.txt` | `PLUGIN_MESSAGE` |
| `plugin-resources/demo/plugin/shared.txt` | `CHILD_SHARED` |

Sau khi biên dịch, `build/host` chứa host class + host resource; `build/plugin` chứa bytecode plugin + resource plugin. **Không đưa `build/plugin` vào application classpath** lúc chạy.

### 5.2. Class plugin

File **`plugin-src/demo/plugin/Widget.java`**:

~~~java
package demo.plugin;

public final class Widget {
    public Widget() {
    }

    public String message() {
        return "Widget ready";
    }
}
~~~

Đây là class bình thường với `public` constructor không tham số. Host **không import** `Widget` vì phải để custom loader là nơi định nghĩa class ấy.

### 5.3. Host và custom loader hoàn chỉnh

File **`src/DirectoryLoaderDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.net.MalformedURLException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class DirectoryLoaderDemo {
    private static final String MESSAGE = "demo/plugin/message.txt";
    private static final String SHARED = "demo/plugin/shared.txt";

    private DirectoryLoaderDemo() {
    }

    static final class DirectoryLoader extends ClassLoader {
        private final Path root;

        DirectoryLoader(Path root, ClassLoader parent) {
            super(parent);
            this.root = root.toAbsolutePath().normalize();
        }

        private Path existingFile(String relativeName) {
            if (relativeName == null
                    || relativeName.isEmpty()
                    || relativeName.startsWith("/")
                    || relativeName.indexOf('\\') >= 0) {
                return null;
            }

            final Path relative;
            try {
                relative = Path.of(relativeName);
            } catch (InvalidPathException ex) {
                return null;
            }

            Path file = root.resolve(relative).normalize();
            if (!file.startsWith(root) || !Files.isRegularFile(file)) {
                return null;
            }
            return file;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = existingFile(
                    name.replace('.', '/') + ".class");

            if (file == null) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytes = Files.readAllBytes(file);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }

        @Override
        protected URL findResource(String name) {
            Path file = existingFile(name);
            if (file == null) {
                return null;
            }

            try {
                return file.toUri().toURL();
            } catch (MalformedURLException ex) {
                throw new UncheckedIOException(ex);
            }
        }

        @Override
        protected Enumeration<URL> findResources(String name)
                throws IOException {
            URL found = findResource(name);
            return Collections.enumeration(
                    found == null ? List.<URL>of() : List.of(found));
        }

        // Chỉ để minh họa resource riêng của child,
        // bỏ qua cơ chế parent-first của getResource.
        URL ownResource(String name) {
            return findResource(name);
        }
    }

    private static String text(URL url) throws IOException {
        if (url == null) {
            return "(missing)";
        }
        try (InputStream in = url.openStream()) {
            return new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    private static String text(InputStream input) throws IOException {
        if (input == null) {
            return "(missing)";
        }
        try (InputStream in = input) {
            return new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).strip();
        }
    }

    private static String all(Enumeration<URL> urls)
            throws IOException {
        List<String> labels = new ArrayList<>();
        while (urls.hasMoreElements()) {
            labels.add(text(urls.nextElement()));
        }
        return String.join(" > ", labels);
    }

    private static String all(Stream<URL> urls) {
        try (urls) {
            return urls.map(url -> {
                try {
                    return text(url);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            }).collect(Collectors.joining(" > "));
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: DirectoryLoaderDemo <plugin-root>");
        }

        Path pluginRoot = Path.of(args[0]).toAbsolutePath();
        if (!Files.isDirectory(pluginRoot)) {
            throw new IllegalArgumentException(
                    "Not a plugin directory: " + pluginRoot);
        }

        ClassLoader parent =
                DirectoryLoaderDemo.class.getClassLoader();
        DirectoryLoader child =
                new DirectoryLoader(pluginRoot, parent);

        Class<?> widget = child.loadClass("demo.plugin.Widget");
        Object instance = widget.getConstructor().newInstance();

        System.out.println("Widget says: "
                + widget.getMethod("message").invoke(instance));
        System.out.println("Widget defined by child: "
                + (widget.getClassLoader() == child));

        System.out.println("Class relative message: "
                + text(widget.getResource("message.txt")));
        System.out.println("Class absolute message: "
                + text(widget.getResource("/" + MESSAGE)));
        System.out.println("Loader message: "
                + text(child.getResource(MESSAGE)));
        System.out.println("Loader message stream: "
                + text(child.getResourceAsStream(MESSAGE)));
        System.out.println("Parent sees plugin message: "
                + (parent.getResource(MESSAGE) != null));

        System.out.println("Parent-first shared: "
                + text(child.getResource(SHARED)));
        System.out.println("Child's own shared: "
                + text(child.ownResource(SHARED)));
        System.out.println("All shared: "
                + all(child.getResources(SHARED)));
        System.out.println("Shared stream: "
                + all(child.resources(SHARED)));
        System.out.println("Class relative shared: "
                + text(widget.getResource("shared.txt")));

        System.out.println("Leading slash on loader fails: "
                + (child.getResource("/" + MESSAGE) == null));

        boolean parentCannotLoad;
        try {
            parent.loadClass("demo.plugin.Widget");
            parentCannotLoad = false;
        } catch (ClassNotFoundException expected) {
            parentCannotLoad = true;
        }
        System.out.println("Parent cannot load Widget: "
                + parentCannotLoad);
    }
}
~~~

**Vì sao `DirectoryLoader` chỉ override ba hook?** Cách này giữ nguyên hợp đồng parent-first của `loadClass`, `getResource` và `getResources` trong `ClassLoader`. Loader mới chỉ cần cho JVM biết cách lấy bytecode và URL tài nguyên từ `root`.

**Vì sao `ownResource` được khai báo riêng?** Nó chỉ là phương thức *quan sát* kết quả `findResource` của child. Không nên cho code ứng dụng dùng hook nguồn riêng như API mặc định, vì hook bỏ qua các tài nguyên do parent cung cấp. Nếu requirement của một hệ plugin đòi child-first thật sự, cần định nghĩa rõ hành vi đó trên toàn bộ hệ thống thay vì dựa vào một method tiện lợi.

## 6. Lệnh biên dịch và chạy

Yêu cầu JDK **17+**, gồm `javac` và `java`. Mở terminal tại thư mục `directory-loader-demo/` chứa đủ file nêu trên.

**Bash (Linux, macOS hoặc Git Bash):**

~~~bash
mkdir -p build/host build/plugin

javac -encoding UTF-8 -d build/host src/DirectoryLoaderDemo.java
javac -encoding UTF-8 -d build/plugin \
  plugin-src/demo/plugin/Widget.java

cp -R host-resources/. build/host/
cp -R plugin-resources/. build/plugin/

java -cp build/host DirectoryLoaderDemo build/plugin
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/host,build/plugin | Out-Null

javac -encoding UTF-8 -d build/host src/DirectoryLoaderDemo.java

javac -encoding UTF-8 -d build/plugin plugin-src/demo/plugin/Widget.java

Copy-Item -Path host-resources/* -Destination build/host -Recurse -Force
Copy-Item -Path plugin-resources/* -Destination build/plugin -Recurse -Force

java -cp build/host DirectoryLoaderDemo build/plugin
~~~

Sau khi build, kiểm tra cấu trúc:

~~~text
build/
├── host/
│   ├── DirectoryLoaderDemo.class
│   ├── DirectoryLoaderDemo$DirectoryLoader.class
│   └── demo/plugin/shared.txt            (HOST_SHARED)
└── plugin/
    └── demo/plugin/
        ├── Widget.class
        ├── message.txt                   (PLUGIN_MESSAGE)
        └── shared.txt                    (CHILD_SHARED)
~~~

Không thêm `build/plugin` vào `java -cp` của host. Nếu parent đã nạp `Widget` từ đó, `child.loadClass(...)` có thể trả class của parent thay vì dùng `findClass` và kết quả kiểm tra sẽ khác.

### Stdout dự kiến

Với đúng các file, classpath và runtime Java 17 thông thường:

~~~text
Widget says: Widget ready
Widget defined by child: true
Class relative message: PLUGIN_MESSAGE
Class absolute message: PLUGIN_MESSAGE
Loader message: PLUGIN_MESSAGE
Loader message stream: PLUGIN_MESSAGE
Parent sees plugin message: false
Parent-first shared: HOST_SHARED
Child's own shared: CHILD_SHARED
All shared: HOST_SHARED > CHILD_SHARED
Shared stream: HOST_SHARED > CHILD_SHARED
Class relative shared: HOST_SHARED
Leading slash on loader fails: true
Parent cannot load Widget: true
~~~

**Phân tích stdout:**

1. `Widget defined by child: true` xác nhận parent không có class và `DirectoryLoader.findClass` đã đọc bytecode tại `build/plugin/demo/plugin/Widget.class`.
2. Hai phép gọi `widget.getResource("message.txt")` và `widget.getResource("/demo/plugin/message.txt")` cùng quy về `demo/plugin/message.txt`, được tìm bởi defining loader của `Widget`.
3. `child.getResource(MESSAGE)` và `child.getResourceAsStream(MESSAGE)` tìm được resource thuộc plugin; host parent không có resource đó.
4. Với `shared.txt`, parent chứa `HOST_SHARED` nên `child.getResource(SHARED)` trả bản của parent, **không** phải bản đứng cạnh `Widget.class`. Đây là ý nghĩa của parent-first.
5. `child.ownResource(SHARED)` truy cập nguồn của child nên thấy `CHILD_SHARED`.
6. `getResources` và `resources` bao gồm cả URL parent rồi URL child, cho kết quả `HOST_SHARED > CHILD_SHARED`.
7. `widget.getResource("shared.txt")` dù bắt đầu từ class do child định nghĩa, vẫn đi qua parent-first của ClassLoader. Vì thế resource được chọn là `HOST_SHARED`.
8. Với `ClassLoader.getResource`, tên bắt đầu bằng `/` không được xử lý như `Class.getResource` và không khớp tên resource được lưu; parent cũng không có tên tương ứng.
9. Parent không tự tìm xuống child nên `parent.loadClass("demo.plugin.Widget")` ném `ClassNotFoundException`.

## 7. `findClass`: đường bytecode dùng chung quy tắc root

Trong `findClass`:

~~~java
// Trích logic cốt lõi từ ví dụ.
String relative = name.replace('.', '/') + ".class";
Path file = existingFile(relative);
byte[] bytes = Files.readAllBytes(file);
return defineClass(name, bytes, 0, bytes.length);
~~~

Đoạn trích ở trên chỉ minh họa nhánh thành công; code runnable đầy đủ đã kiểm tra null và bọc `IOException` bằng `ClassNotFoundException`.

Việc dùng cùng `root` cho `findClass` và `findResource` tạo một nguyên tắc dễ hiểu:

~~~text
root/demo/plugin/Widget.class  ← dữ liệu để defineClass
root/demo/plugin/message.txt   ← dữ liệu để findResource
root/demo/plugin/shared.txt    ← resource khác cùng package
~~~

Nhưng phải phân biệt:

- `defineClass` chỉ nhận bytecode Java class hợp lệ; không dùng nó để nạp file văn bản.
- `findResource` trả `URL` trỏ đến dữ liệu; nó không định nghĩa class hoặc kích hoạt static initializer.
- `getResource` có thể trả tài nguyên của parent ngay cả khi `findResource` của child cũng tìm thấy cùng tên.
- Có thể có nhiều source roots hoặc JARs; khi đó `findClass` và `findResources` phải sử dụng danh sách nguồn rõ ràng, không mặc định một Path duy nhất như ví dụ.

Nếu class nằm trong **JAR** thay vì thư mục, nên cân nhắc `URLClassLoader` sẵn có. Nó đã hỗ trợ class lookup, URL resource lookup, parent delegation và lifecycle `close()`. Không cần viết lại parser ZIP/JAR nếu mục tiêu chỉ là nạp một vài JAR thông thường.

## 8. `findResource` và `findResources`: vì sao cần cả hai?

Một lỗi rất phổ biến là chỉ override `findResource`:

~~~java
@Override
protected URL findResource(String name) {
    // Tìm resource đầu tiên trong kho riêng.
    ...
}
~~~

Khi đó `getResource(name)` có thể hoạt động, **nhưng `getResources(name)` chưa chắc liệt kê resource thuộc kho riêng**, vì implementation mặc định của `findResources` không tự tổng hợp từ `findResource` của subclass. Đây là điều khác biệt giữa **API tìm một** và **API liệt kê nhiều**.

Để hỗ trợ cả hai, cần cài:

~~~java
@Override
protected Enumeration<URL> findResources(String name)
        throws IOException {
    URL found = findResource(name);
    return Collections.enumeration(
            found == null ? List.<URL>of() : List.of(found));
}
~~~

Đây là cách phù hợp **khi mỗi tên chỉ có nhiều nhất một file trong root của child**. Khi loader tìm trên **nhiều JAR/root**, phải liệt kê mọi URL trong thứ tự mong muốn, ví dụ:

~~~java
// Mã minh họa, không chạy độc lập:
List<URL> found = new ArrayList<>();
for (Repository repository : repositories) {
    URL url = repository.find(name);
    if (url != null) {
        found.add(url);
    }
}
return Collections.enumeration(found);
~~~

Không thực hiện return ngay ở kết quả đầu tiên nếu contract của `findResources` là liệt kê tất cả URL có tên đó.

**Điều kiện nhất quán hữu ích:** URL đầu tiên do `getResources(name)` liệt kê nên phù hợp với `getResource(name)` khi hệ thống tra cứu không bị thay đổi đồng thời. Nếu subclass override phương thức entry-point một cách khác nhau, các framework dùng API một resource và nhiều resource có thể nhìn thấy các bộ dữ liệu khác nhau không chủ ý.

## 9. Class-relative resource: cùng package không bảo đảm cùng nguồn

Một nhận định dễ nhầm:

> “`Widget.class.getResource("shared.txt")` chắc chắn đọc file từ đúng thư mục chứa `Widget.class`.”

Điều đó **không đúng một cách tổng quát**. `Class.getResource` xử lý **tên resource tương đối với package** rồi ủy quyền tra cứu tới ClassLoader/module phù hợp. Nếu ClassLoader dùng parent-first và parent có resource trùng tên, **resource của parent có thể được ưu tiên**, dù class `Widget` do child định nghĩa.

Trong ví dụ:

~~~text
Widget.class        → child định nghĩa, nằm trong build/plugin
shared.txt (host)   → parent cung cấp, HOST_SHARED
shared.txt (plugin) → child cung cấp, CHILD_SHARED
~~~

Lệnh:

~~~java
URL chosen = widget.getResource("shared.txt");
~~~

nhận `HOST_SHARED`. Muốn truy vấn riêng root plugin trong một hệ thống có yêu cầu “resource phải đi cùng code plugin”, cần một API mà framework kiểm soát, ví dụ `ownResource`, hoặc thiết kế namespace/path tránh xung đột.

**Chiến lược thực tế tốt hơn:** đặt resource dưới đường dẫn định danh riêng, ví dụ `META-INF/my-plugin-id/config.json`, thay vì tên chung `config.properties` ở root của nhiều JAR. Nếu code cố ý muốn hỗ trợ nhiều resource trùng tên, dùng `getResources` và quy tắc merge/priority rõ ràng.

## 10. Tên resource và quy tắc slash

| Caller | Input | Ý nghĩa |
|---|---|---|
| `loader.getResource("demo/plugin/message.txt")` | Không có slash đầu | Path từ root loader |
| `loader.getResource("/demo/plugin/message.txt")` | Có slash đầu | Thông thường không khớp tên resource, đừng dùng |
| `Widget.class.getResource("message.txt")` | Tên tương đối | Từ package `demo.plugin` |
| `Widget.class.getResource("/demo/plugin/message.txt")` | Slash đầu | Tên tuyệt đối từ resource root |
| `Widget.class.getResourceAsStream("message.txt")` | Tên tương đối | InputStream của resource được chọn, cần đóng |

Với resource trong **named module**, còn có các quy tắc module encapsulation và `opens`. `Class.getResource` không đơn giản là thao tác cộng chuỗi rồi gọi bất kỳ loader nào; lookup có thể có các kiểm tra quyền của module. Mẫu này dùng **classpath/unnamed modules** để hành vi có thể kiểm chứng dễ dàng.

## 11. An toàn đường dẫn và tính đúng đắn của custom loader

Code ví dụ có hàm `existingFile` để giới hạn lookup trong root:

~~~java
Path file = root.resolve(relative).normalize();
if (!file.startsWith(root) || !Files.isRegularFile(file)) {
    return null;
}
~~~

Việc `normalize()` và kiểm tra `startsWith(root)` giúp tránh **một số** kiểu truy cập `../` đơn giản hoặc đường dẫn tuyệt đối ngoài root. Nhưng đây **không phải sandbox hay giải pháp chống traversal đầy đủ**:

- **Symbolic link** nằm bên trong root có thể trỏ tới file bên ngoài; so sánh path sau normalize **không** giải quyết được trường hợp đó. Nếu nguồn resource không tin cậy, cần chính sách symlink, kiểm tra real path và phòng tránh race thay đổi filesystem (TOCTOU).
- Path do caller cung cấp có thể khác quy tắc giữa Windows/Unix (separator, drive, case sensitivity). Thư viện production cần kiểm tra/chuẩn hóa đầu vào rõ ràng.
- Không nên cho untrusted caller tùy tiện yêu cầu mọi file trong plugin root nếu root có chứa secret/config nhạy cảm.
- `defineClass` không tạo ranh giới bảo mật: plugin bytecode chạy trong cùng JVM/process. Với mã không tin cậy, cách ly quyền bằng tiến trình/container phù hợp.
- Loader production còn phải cân nhắc `ProtectionDomain`, package metadata/sealing, chữ ký JAR, thread safety, lifecycle và nạp đồng thời; ví dụ tập trung vào **resource lookup**, không trình bày đây là loader JAR production hoàn chỉnh.

Nếu file biến mất giữa `Files.isRegularFile` và `Files.readAllBytes`, nhánh `IOException` trong `findClass` chuyển lỗi sang `ClassNotFoundException` có cause; nhánh URL resource cũng có thể gặp lỗi khi caller mở URL. Tìm được `URL` **không bảo đảm** file vẫn đọc được sau đó.

## 12. Resource lifecycle: URL và InputStream

`findResource` trả một `URL` trỏ tới file. Khi caller gọi `URL.openStream()` hoặc `getResourceAsStream`, một `InputStream` được mở. Caller phải **đóng stream**:

~~~java
// Mã minh họa nếu loader đã tồn tại.
try (InputStream in =
             loader.getResourceAsStream("demo/plugin/message.txt")) {
    if (in == null) {
        throw new IOException("Resource missing");
    }
    String text = new String(
            in.readAllBytes(), StandardCharsets.UTF_8);
    // Xử lý text...
}
~~~

Đừng coi URL là nội dung tài nguyên. Một URL là **vị trí**; tệp có thể thay đổi hoặc bị xóa sau lúc URL được trả về. Nếu resource phải bất biến trong suốt phiên bản plugin, hãy quản lý snapshot/version rõ ràng.

Lưu ý `DirectoryLoader` minh họa ở đây **không triển khai `AutoCloseable`**, cũng không giữ `JarFile`/stream handles để đóng. Không có `close()` tự động giống `URLClassLoader`. Nếu tự xây loader đọc ZIP, JAR hoặc kết nối mạng, phải thiết kế cơ chế đóng nguồn tài nguyên do loader sở hữu, ngừng task và dọn object/thread/callback trước khi unload plugin.

Việc làm `DirectoryLoader` không còn được tham chiếu có thể giúp JVM thu gom class/loader sau khi mọi object/class liên quan không còn reachable, nhưng không có lời hứa unload ngay; TCCL, `ThreadLocal` và cache framework có thể giữ loader lâu hơn dự kiến.

## 13. `getResources`, `resources` và metadata nhiều nguồn

Với root đơn, `findResources` của ví dụ chỉ trả một URL hoặc Enumeration rỗng. Nhưng `getResources` của ClassLoader **vẫn có thể trả nhiều URL**, vì nó ghép kết quả của parent và child.

Với `shared.txt`:

~~~text
child.getResources("demo/plugin/shared.txt")
    → [HOST_SHARED, CHILD_SHARED]

child.resources("demo/plugin/shared.txt")
    → Stream<URL> theo cùng lookup
~~~

`getResources` trả `Enumeration<URL>`. `resources` (Java 9+) trả `Stream<URL>`, cho phép lọc/map/collect. **Hai API trả URL, không trả nội dung file**. Khi đọc từng URL, mở và đóng các `InputStream` riêng như phương thức `text(url)` trong ví dụ.

Một trường hợp phổ biến là `META-INF/services/com.example.Service`:

- Nhiều JAR có thể cung cấp các descriptor cùng tên.
- `ServiceLoader` dùng lookup resource/provider theo quy tắc riêng.
- Nếu custom loader chỉ cài `findResource` nhưng không cài `findResources`, một framework cần enumerate nhiều descriptor có thể không thấy provider nằm trong nguồn riêng.
- Chỉ định nghĩa cùng tên file `META-INF/services/...` chưa đủ; provider và interface service cần thuộc đúng runtime type để `ServiceLoader` chấp nhận.

Khi có thể, dùng `ServiceLoader` thay vì tự parser descriptor. Nếu API cho phép truyền loader, dùng overload nhận `ClassLoader` tường minh; TCCL chỉ là lựa chọn tra cứu ngữ cảnh, không thay defining loader của class.

## 14. ClassLoader tùy chỉnh với JAR: khi nào không tự viết?

Nếu mục đích chỉ là “nạp lớp và resource từ danh sách JAR”, lựa chọn đơn giản hơn thường là `URLClassLoader`:

~~~java
// Mã minh họa, cần urls và parent.
try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
    Class<?> type = loader.loadClass("demo.plugin.Widget");
    URL resource = loader.getResource("demo/plugin/message.txt");
    // Dùng class và đọc resource khi loader vẫn còn mở.
}
~~~

`URLClassLoader` đã hỗ trợ `findClass`, `findResource`, `findResources`, thứ tự URL, parent delegation và `close()` giải phóng các file/JAR do loader mở. Điều đó giảm rất nhiều công việc và lỗi thường gặp so với một subclass tự đọc ZIP/JAR.

Chỉ cân nhắc custom ClassLoader khi nguồn dữ liệu thật sự khác biệt (ví dụ bytecode/resources từ encrypted bundle, database, network repository, nội dung sinh động) hoặc cần kiểm soát xác thực/version rõ ràng. Khi viết, phải xử lý **đồng thời class và tài nguyên**; chỉ nạp được `.class` nhưng bỏ `findResource(s)` là thiết kế thiếu.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `child.loadClass("demo.plugin.Widget")` thành công nhưng `Widget.class.getResource("message.txt")` trả null | Có `findClass` nhưng không có `findResource` | Cài resource lookup từ cùng root và đúng đường dẫn |
| `getResource` tìm được nhưng `getResources` không liệt kê file child | Có `findResource` nhưng thiếu `findResources` | Override cả hai hook; Enumerate mọi match của child |
| Resource của host “thắng” file bên cạnh class plugin | `getResource` parent-first và parent có tên trùng | Dùng namespace riêng hoặc API truy vấn nguồn plugin có chủ đích |
| `ClassLoader.getResource("/demo/plugin/message.txt")` null | Tên có slash đầu không đúng quy tắc `ClassLoader` | Dùng `"demo/plugin/message.txt"` |
| `Widget.class.getResource("message.txt")` không thấy file ở root | Class-relative lookup thêm package path | Di chuyển resource vào `demo/plugin/` hoặc dùng tên absolute |
| Parent không tìm được class của child | Parent không tự duyệt nguồn riêng của child | Host gọi child loader và giao tiếp qua API chung |
| `ClassCastException` khi class trùng tên | Hai loader đã định nghĩa hai runtime class không tương thích | Chia sẻ interface/DTO ở loader chung |
| `getResource` trả URL nhưng đọc sau đó gặp lỗi | File bị xóa/đổi hoặc I/O thất bại | Mở và đọc trong lifecycle được quản lý, xử lý `IOException` |
| Path chuẩn hóa nhưng vẫn ra ngoài root | Symlink hoặc filesystem race | Kiểm soát real path và chính sách nguồn tin cậy |
| Plugin unload khó dù không còn dùng | Thread/TCCL/cache giữ classloader | Dọn callback, thread, resource và references |
| `ServiceLoader` không phát hiện provider | Sai descriptor, sai lookup loader hoặc thiếu `findResources` | Kiểm tra `META-INF/services`, type identity và enumeration |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một custom ClassLoader chỉ override `findClass`. Nó nạp được `Widget.class` từ thư mục riêng. `Widget.class.getResource("message.txt")` có chắc tìm được file nằm cạnh `Widget.class` không?

**Đáp án:** Không. Class lookup và resource lookup là hai đường khác nhau; loader cần cung cấp `findResource` (và `findResources` nếu muốn liệt kê).

**Câu 2.** Vì sao `Widget.class.getResource("shared.txt")` có thể trả resource của parent dù `Widget.class.getClassLoader()` là child?

**Đáp án:** `Class.getResource` xác định tên tương đối với package rồi dùng cơ chế resource lookup. Với ClassLoader parent-first, parent có thể cung cấp resource trùng tên trước child.

**Câu 3.** Vì sao nên override `findResources` nếu đã có `findResource`?

**Đáp án:** Vì API `getResources` dành để liệt kê **nhiều URL**, thường gọi hook `findResources`; hook mặc định không tự liệt kê nội dung của `findResource` tùy biến.

**Câu 4.** `getResources("demo/plugin/shared.txt")` trong ví dụ trả bao nhiêu resource?

**Đáp án:** Hai URL: resource của host parent trước, sau đó resource riêng của child. `resources(...)` cung cấp chúng qua Stream API.

**Câu 5.** Khi custom loader đọc class từ database nhưng resource được lưu trong database cùng key prefix, nên thiết kế thế nào?

**Đáp án:** `findClass` ánh xạ binary name thành key bytecode, `findResource(s)` ánh xạ resource name thành URL/đường truy cập thích hợp (hoặc cung cấp protocol handler có vòng đời được quản lý). Cần bảo đảm URI/URL được trả thực sự có thể mở và kiểm soát lỗi/đóng tài nguyên.

**Câu 6.** Có cần override `getResource` để sử dụng parent-first với resource của loader tùy chỉnh không?

**Đáp án:** Thông thường không. Dùng `findResource`/`findResources`; `ClassLoader.getResource(s)` mặc định thực hiện parent delegation.

## 17. Tài liệu tham khảo

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `findClass`, `findResource`, `findResources`, `getResource`, `getResources` và `resources`.
- [Java SE 17 — Class.getResource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String)): quy tắc tên tương đối với package và tên tuyệt đối.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): triển khai loader có đường tìm JAR/resource.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): liên hệ giữa nhiều resource descriptor và provider discovery.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `normalize`, `startsWith` khi ánh xạ root.

**Ghi nhớ:** Một custom ClassLoader cần thiết kế **cặp tra cứu class và tài nguyên**. Override `findClass` để định nghĩa lớp, `findResource` để tìm một resource riêng và `findResources` để liệt kê các resource riêng; để entry point `loadClass`/`getResource(s)` quản lý parent-first nếu không có lý do thay đổi. Resource có cùng package với class **không bảo đảm** được lấy từ cùng nguồn khi parent có tên trùng; hãy kiểm tra namespace, đường dẫn và thứ tự delegation.
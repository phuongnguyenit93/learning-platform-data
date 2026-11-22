# Nạp lớp và tài nguyên qua URLClassLoader trong Java

`java.net.URLClassLoader` là class loader có sẵn trong Java dùng để tìm **lớp** và **tài nguyên** từ các URL trỏ tới thư mục hoặc file JAR. Nó thường xuất hiện trong hệ thống plugin, extension, các công cụ tải thư viện động hoặc chương trình cần đọc file resource từ một JAR không nằm sẵn trên application classpath.

Để sử dụng đúng URLClassLoader, phải hiểu năm điều:

1. URL phải trỏ đúng **gốc thư mục chứa package** hoặc **file JAR**, không phải tên class.
2. Tên truyền cho `loadClass` là **binary class name** dùng dấu chấm, còn resource name là path dùng dấu `/`.
3. Parent delegation mặc định có thể khiến **parent** định nghĩa class thay vì URLClassLoader đang được gọi.
4. `loadClass` không đồng nghĩa chạy static initializer hay tạo Java instance; `getResource` chỉ tìm URL, `getResourceAsStream` mới mở stream.
5. `URLClassLoader.close()` giúp đóng những file/JAR đã mở; **không bắt buộc** JVM unload các class đã được định nghĩa.

Bài này tập trung vào API, cơ chế, vòng đời và lỗi thường gặp, sau đó tạo ví dụ Java 17+ đọc cùng một plugin từ thư mục và từ JAR.

## 1. URLClassLoader nằm ở đâu trong hệ thống loader?

~~~text
java.lang.Object
  -> java.lang.ClassLoader
      -> java.security.SecureClassLoader
          -> java.net.URLClassLoader
~~~

URLClassLoader kế thừa mô hình class loading của `ClassLoader`, đồng thời cung cấp cách tìm bytecode/resources bằng URL search path và triển khai `Closeable`.

~~~text
Host application
      |
      v
new URLClassLoader(urls, parent)
      |
      +--> Parent loader (ưu tiên trong loadClass mặc định)
      |       |
      |       +--> Java classes, shared APIs
      |
      +--> URL search path (nếu parent không tìm được)
              |
              +--> file:/.../classes/
              |       example/plugin/HelloPlugin.class
              |       example/plugin/greeting.txt
              |
              +--> file:/.../plugin.jar
                      example/plugin/HelloPlugin.class
                      example/plugin/greeting.txt
~~~

Một số method quan trọng:

| API | Trả về | Mục đích |
|---|---|---|
| `loadClass(String)` | `Class<?>` hoặc ném `ClassNotFoundException` | Nạp kiểu theo binary name |
| `getResource(String)` | `URL` hoặc `null` | Tìm một resource |
| `getResources(String)` | `Enumeration<URL>` | Liệt kê nhiều resource cùng tên |
| `getResourceAsStream(String)` | `InputStream` hoặc `null` | Mở resource để đọc |
| `getURLs()` | `URL[]` | Quan sát danh sách URL của loader |
| `getParent()` | `ClassLoader` hoặc `null` | Xem loader cha |
| `getName()` | `String` hoặc `null` | Tên chẩn đoán của loader |
| `close()` | `void`, có thể ném `IOException` | Đóng file/JAR handles của loader |

**Lưu ý:** URLClassLoader không phải dependency resolver Maven/Gradle, không tự tải mọi dependency từ Internet và không phải sandbox bảo mật cho plugin không tin cậy.

## 2. Constructor và parent delegation

Những constructor thường dùng trên Java 17:

~~~java
URLClassLoader a = new URLClassLoader(urls);
URLClassLoader b = new URLClassLoader(urls, parent);
URLClassLoader c = new URLClassLoader("plugin-a", urls, parent);
~~~

Đây là **mảnh minh họa**, `urls` phải là `URL[]` và `parent` là `ClassLoader` thích hợp.

- `URLClassLoader(URL[])` lấy system class loader làm parent.
- `URLClassLoader(URL[], ClassLoader)` cho phép chọn parent tường minh.
- `URLClassLoader(String, URL[], ClassLoader)` tạo named loader (Java 9+); tên giúp log dễ đọc nhưng **không phải định danh duy nhất**.
- Nếu parent là `null`, việc delegation đến bootstrap không bảo đảm toàn bộ platform classes có thể dùng được.
- Với plugin cần implement interface chung của host, parent nên nhìn thấy **một bản duy nhất** của API đó. Không nên định nghĩa lại cùng interface trong từng child loader.

Đối với implementation mặc định của `ClassLoader.loadClass`:

~~~text
loadClass("example.plugin.HelloPlugin")
                 |
       findLoadedClass(name)?
          /              \
         có              không
         |                 |
      trả Class       hỏi parent trước
                           |
                  parent tìm được?
                    /       \
                  có        không
                  |           |
             trả Class   findClass trong URL[]
                                |
                             defineClass
~~~

Nếu parent đã thấy cùng binary name, child có thể nhận Class do parent định nghĩa. Do đó, đoạn:

~~~java
Class<?> type = loader.loadClass("example.plugin.HelloPlugin");
System.out.println(type.getClassLoader() == loader);
~~~

có thể in `false` dù lời gọi `loadClass` thành công. `Class.getClassLoader()` chỉ **defining loader**; không phải lúc nào cũng là initiating loader.

**Type identity của JVM = (binary class name, defining class loader).** Hai loader khác nhau tự định nghĩa cùng `example.plugin.HelloPlugin` là hai runtime types riêng, có thể không ép kiểu qua lại được.

## 3. URL thư mục và URL file JAR

### Thư mục

Nếu có `plugins/classes/example/plugin/HelloPlugin.class`, URL root cần trỏ tới **`plugins/classes/`**:

~~~java
import java.net.URL;
import java.nio.file.Path;

Path directory = Path.of("plugins", "classes").toAbsolutePath();
URL directoryUrl = directory.toUri().toURL();
~~~

`URLClassLoader` coi `file:` URL kết thúc bằng `/` là thư mục. Tạo URL bằng `Path.toUri().toURL()` thay vì tự nối `"file:" + path` để xử lý đúng Windows, dấu cách và ký tự đặc biệt. Khi directory thực sự tồn tại, URL của thư mục được tạo ở dạng thích hợp.

Không trỏ URL tới chính `HelloPlugin.class`; loader tự ghép `example/plugin/HelloPlugin.class` từ tên binary khi tìm trong root.

### File JAR

~~~java
Path jarPath = Path.of("plugins", "hello-plugin.jar").toAbsolutePath();
URL jarUrl = jarPath.toUri().toURL();
~~~

URL `file:/.../hello-plugin.jar` là đầu vào phù hợp. Với một resource ở trong JAR, `getResource` có thể trả URL dạng:

~~~text
jar:file:/.../hello-plugin.jar!/example/plugin/greeting.txt
~~~

Không cần tự viết `jar:file:...!/` làm URL input để nạp **toàn bộ JAR**. Các file bên trong JAR phải đúng package path:

~~~text
hello-plugin.jar
  META-INF/MANIFEST.MF
  example/plugin/HelloPlugin.class
  example/plugin/greeting.txt
~~~

**Plugin JAR không cần `Main-Class`.** `Main-Class` dùng cho executable JAR chạy bằng `java -jar`; URLClassLoader nạp theo tên `loadClass`, không thực thi entry point của JAR.

### Nhiều URL

~~~java
URL[] sources = {
    Path.of("plugins/classes").toUri().toURL(),
    Path.of("plugins/one.jar").toUri().toURL(),
    Path.of("plugins/two.jar").toUri().toURL()
};

try (URLClassLoader loader = new URLClassLoader(
        "extensions", sources, ClassLoader.getSystemClassLoader())) {
    Class<?> type = loader.loadClass("example.plugin.HelloPlugin");
}
~~~

Đây là **mảnh minh họa** cần các URL tương ứng tồn tại. Parent được ưu tiên theo delegation mặc định, sau đó child tìm các URL theo thứ tự cấu hình. Nếu hai JAR trùng class/resource name, vị trí search path có thể quyết định bản được tìm. Manifest `Class-Path` của JAR cũng có thể ảnh hưởng đến đường tìm kiếm hợp lệ; không tự cho rằng chỉ các URL gốc mới có mặt.

## 4. Tải class, khởi tạo class và tạo instance

Ba lời gọi:

~~~java
Class<?> a = loader.loadClass("example.plugin.HelloPlugin");

Class<?> b = Class.forName(
        "example.plugin.HelloPlugin", false, loader);

Class<?> c = Class.forName(
        "example.plugin.HelloPlugin", true, loader);
~~~

Đây là mảnh API; cần loader đã cấu hình và xử lý `ClassNotFoundException`.

| Thao tác | Ý nghĩa |
|---|---|
| `loader.loadClass(name)` | Yêu cầu nạp class nhưng **không yêu cầu initialize static** |
| `Class.forName(name, false, loader)` | Tìm/nạp/liên kết kiểu, không yêu cầu initialization |
| `Class.forName(name, true, loader)` | Tìm và yêu cầu initialize kiểu |
| `type.getConstructor().newInstance()` | Tạo object bằng reflection nếu constructor cho phép |
| `type.getMethod("sayHello").invoke(instance)` | Gọi method reflection; có thể ném exception hoặc lỗi target |

Một object `Class<?>` không đồng nghĩa đã có instance plugin. `loadClass` nhiều lần trên cùng loader thường trả định nghĩa runtime đã có, không định nghĩa lại cùng tên sau mỗi lần gọi.

Khi dùng plugin API chung:

~~~java
PluginApi plugin = (PluginApi) type.getConstructor().newInstance();
~~~

Đây là mảnh minh họa, **chỉ hợp lệ khi `PluginApi` đã được định nghĩa bởi loader chung và class plugin implement đúng runtime interface đó**. Nếu host và plugin loaders tự định nghĩa hai bản `PluginApi` có cùng tên, cast có thể gây `ClassCastException`.

## 5. Tìm resource: path và API

### `getResource`, `getResources` và `getResourceAsStream`

~~~java
URL first = loader.getResource("example/plugin/greeting.txt");

Enumeration<URL> matches =
        loader.getResources("example/plugin/greeting.txt");

try (InputStream input =
        loader.getResourceAsStream("example/plugin/greeting.txt")) {
    if (input == null) {
        throw new IllegalStateException("Resource not found");
    }
    String text = new String(
            input.readAllBytes(), StandardCharsets.UTF_8);
    System.out.println(text);
}
~~~

Đây là các **mảnh minh họa API** yêu cầu imports `URL`, `Enumeration`, `InputStream` và `StandardCharsets` cũng như xử lý exception thích hợp.

- `getResource` trả URL đầu tiên hoặc `null`.
- `getResources` trả enumeration nhiều URL; thích hợp nếu nhiều JAR có resource cùng tên.
- `getResourceAsStream` mở stream hoặc trả `null`. Đóng stream bằng try-with-resources, kể cả khi loader được đóng về sau.
- Resource có thể được parent tìm trước theo quy tắc delegation; URLClassLoader không chắc là nơi vật lý của resource trả về.

### Class và ClassLoader tính path khác nhau

Giả sử `example.plugin.HelloPlugin` nằm cạnh `example/plugin/greeting.txt`:

~~~java
Class<?> type = loader.loadClass("example.plugin.HelloPlugin");

// Class API: relative từ package example.plugin
InputStream a = type.getResourceAsStream("greeting.txt");

// Class API: absolute từ root
InputStream b = type.getResourceAsStream(
        "/example/plugin/greeting.txt");

// ClassLoader API: luôn truyền path từ root
InputStream c = loader.getResourceAsStream(
        "example/plugin/greeting.txt");
~~~

Cả ba stream có thể trỏ cùng resource. Chúng chỉ là minh họa và cần đóng sau khi sử dụng.

| Cách gọi | Tên được tìm |
|---|---|
| `type.getResource("greeting.txt")` | `example/plugin/greeting.txt` |
| `type.getResource("/example/plugin/greeting.txt")` | `example/plugin/greeting.txt` |
| `loader.getResource("example/plugin/greeting.txt")` | `example/plugin/greeting.txt` |
| `loader.getResource("greeting.txt")` | `greeting.txt` ở root |

Đừng đặt dấu `/` đầu trong resource name của `ClassLoader` theo thói quen từ `Class.getResource`. Resource path dùng dấu `/`, trong khi class binary name dùng dấu `.`.

Nếu resource nằm trong **named module** được nạp bằng cơ chế JPMS, còn có các quy tắc `opens`/module encapsulation; ví dụ sau dùng class plugin thuộc unnamed module để tập trung vào quy tắc URL/path.

## 6. Ví dụ runnable Java 17+: nạp cùng class và resource từ directory/JAR

Ví dụ có hai Java files và một text file; host được biên dịch **không cần plugin trên classpath**. Hai URLClassLoader độc lập sẽ định nghĩa hai bản riêng của `example.plugin.HelloPlugin` và đọc resource cùng tên.

### Cấu trúc thư mục

~~~text
project/
  src/
    plugin/example/plugin/HelloPlugin.java
    host/LoaderLab.java
  resources/
    example/plugin/greeting.txt
  out/
    plugin/
    host/
  dist/
    hello-plugin.jar
~~~

### File `src/plugin/example/plugin/HelloPlugin.java`

~~~java
package example.plugin;

public class HelloPlugin {
    public HelloPlugin() {
    }

    public String sayHello() {
        return "Hello from URLClassLoader";
    }
}
~~~

### File `resources/example/plugin/greeting.txt`

~~~text
resource-ok
~~~

### File `src/host/LoaderLab.java`

~~~java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class LoaderLab {
    private static final String CLASS_NAME =
            "example.plugin.HelloPlugin";
    private static final String RESOURCE_NAME =
            "example/plugin/greeting.txt";

    private static Class<?> loadSource(String label, URL source)
            throws Exception {
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader loader = new URLClassLoader(
                label, new URL[] {source}, parent)) {

            Class<?> type = loader.loadClass(CLASS_NAME);
            Object instance = type.getConstructor().newInstance();
            String hello = (String) type.getMethod("sayHello")
                    .invoke(instance);

            System.out.println(label + " class: " + hello);
            System.out.println(label + " defined here: "
                    + (type.getClassLoader() == loader));

            try (InputStream in =
                    loader.getResourceAsStream(RESOURCE_NAME)) {
                if (in == null) {
                    throw new IllegalStateException(
                            "Missing: " + RESOURCE_NAME);
                }
                String data = new String(
                        in.readAllBytes(), StandardCharsets.UTF_8).strip();
                System.out.println(label + " resource: " + data);
            }

            try (InputStream in =
                    type.getResourceAsStream("greeting.txt")) {
                System.out.println(label + " class-relative: "
                        + (in != null));
            }

            return type;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: LoaderLab <directory> <jar>");
        }

        URL dir = Path.of(args[0])
                .toAbsolutePath().toUri().toURL();
        URL jar = Path.of(args[1])
                .toAbsolutePath().toUri().toURL();

        Class<?> fromDir = loadSource("directory", dir);
        Class<?> fromJar = loadSource("jar", jar);

        System.out.println("same class name: "
                + fromDir.getName().equals(fromJar.getName()));
        System.out.println("same runtime class: "
                + (fromDir == fromJar));
    }
}
~~~

**Điểm chính của code:**

- `URLClassLoader(String, URL[], ClassLoader)` tạo loader có tên; mỗi nguồn một loader.
- Parent `getPlatformClassLoader()` được dùng **chỉ cho demo**, để nó không nhìn thấy plugin class trên application classpath và child sẽ là defining loader.
- `loadClass` trả `Class<?>`; reflection mới tạo object.
- `getResourceAsStream` của loader dùng tên từ root; `getResourceAsStream` của Class dùng tên tương đối package.
- Trả `Class<?>` từ method rồi đóng loader cho thấy đóng loader **không tự xóa runtime type** đã có.

### Biên dịch và đóng gói (Bash/Linux/macOS)

~~~bash
mkdir -p out/plugin/example/plugin out/host dist

javac -d out/plugin src/plugin/example/plugin/HelloPlugin.java

cp resources/example/plugin/greeting.txt out/plugin/example/plugin/greeting.txt

jar --create --file dist/hello-plugin.jar -C out/plugin .

javac -d out/host src/host/LoaderLab.java
~~~

`javac` không tự copy `.txt`, vì vậy lệnh `cp` quan trọng. Sau build:

~~~text
out/plugin/example/plugin/HelloPlugin.class
out/plugin/example/plugin/greeting.txt
out/host/LoaderLab.class
dist/hello-plugin.jar
~~~

Kiểm tra nội dung JAR bằng `jar --list --file dist/hello-plugin.jar`; phải có cả `example/plugin/HelloPlugin.class` và `example/plugin/greeting.txt`.

### Chạy host

~~~bash
java -cp out/host LoaderLab out/plugin dist/hello-plugin.jar
~~~

**Stdout mong đợi trên JDK 17+:**

~~~text
directory class: Hello from URLClassLoader
directory defined here: true
directory resource: resource-ok
directory class-relative: true
jar class: Hello from URLClassLoader
jar defined here: true
jar resource: resource-ok
jar class-relative: true
same class name: true
same runtime class: false
~~~

Bản từ directory và bản từ JAR có cùng binary name nhưng **không cùng runtime Class object**. Mỗi URLClassLoader định nghĩa một bản riêng. Đây là lý do loader identity ảnh hưởng tới tính tương thích kiểu, dù bytecode hoàn toàn giống nhau.

**Trên Windows PowerShell**, sử dụng `New-Item -ItemType Directory -Force` để tạo các thư mục, `Copy-Item` thay cho `cp`; các lệnh `javac`, `jar`, `java` vẫn dùng tương tự. Ví dụ chạy không có nhiều classpath entries nên không cần dấu phân cách `;`.

## 7. Vòng đời loader và đóng tài nguyên

URLClassLoader triển khai `Closeable` nên cần try-with-resources:

~~~java
try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
    // load class và đọc resources
}
~~~

Hành vi của `close()`:

- Cố gắng đóng JAR/file handles do loader mở.
- Không biến một class đã load thành class chưa load; class/instance đã được tạo có thể vẫn sử dụng được.
- Không bảo đảm **class unloading ngay lập tức**. Unload còn phụ thuộc việc giữ reference đến loader, object, `Class<?>`, thread, context loader, cache và quyết định của GC.
- Không nên gọi `close()` đồng thời lúc thread khác vẫn đang load class; hợp đồng API không bảo đảm kết quả xác định trong trường hợp đua.
- Các class/resource mới từ URL riêng có thể không còn tìm được sau khi loader đã đóng; parent vẫn có thể cung cấp lớp hoặc resource của nó.
- Dù loader sẽ được đóng, `InputStream` vẫn nên được đóng ngay sau khi đọc.

Nếu hệ thống plugin chạy lâu, quản lý mỗi plugin và URLClassLoader theo một lifecycle rõ ràng; không mở/đóng loader mới cho mọi lần gọi method.

## 8. URLClassLoader so với classpath và JPMS

**Classpath của host:** tạo một `URLClassLoader` riêng không sửa `java.class.path`, `CLASSPATH` hoặc đường tìm của loader khác. `Class.forName(String)` ở host dùng loader của caller; dùng `loader.loadClass(name)` hoặc overload `Class.forName(name, initialize, loader)` để tìm trong plugin loader.

**JPMS:** thêm một modular JAR vào mảng URL không tự resolve named modules, lập `ModuleLayer` hoặc thực thi mọi quy tắc `requires` như module path. Ví dụ trong bài dùng unnamed module.

**Đóng gói và bảo mật:** loader thuần không tự giải Maven/Gradle dependency graph, unpack nested JAR hoặc sandbox code không tin cậy. Cần giải quyết những vấn đề ấy qua build/launcher và ranh giới tiến trình phù hợp.

## 9. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| `ClassNotFoundException` | Sai URL root, tên nhị phân hoặc thiếu `.class` | Kiểm tra `example/plugin/HelloPlugin.class` |
| `NoClassDefFoundError` | Dependency thiếu, linkage hoặc initialization từng lỗi | Đọc chuỗi cause/stack trace |
| `UnsupportedClassVersionError` | Java runtime thấp hơn version class | Kiểm tra `javac --release` và runtime |
| `IllegalAccessException` | Constructor/method không truy cập được | Xem public API và JPMS |
| `ClassCastException` | Cùng API name nhưng khác defining loader | So `getClassLoader()` của hai Class |
| Resource trả `null` | File thiếu, path sai, resource chưa copy, khác loader, encapsulation | Kiểm tra JAR entries và path |
| Resource không mong đợi | Parent hoặc URL trước có resource cùng tên | Dùng `getResources` và xem delegation |
| JAR bị khóa | Stream/loader chưa đóng | Dùng try-with-resources |
| Class vẫn tồn tại sau `close()` | Loader/class/object còn tham chiếu | Xem cache, thread, callbacks |

### Chẩn đoán nhanh

**Xem URL đang dùng:**

~~~java
for (URL u : loader.getURLs()) {
    System.out.println(u);
}
~~~

**Xem defining loader của class:**

~~~java
Class<?> type = loader.loadClass("example.plugin.HelloPlugin");
System.out.println(type.getClassLoader() == loader);
~~~

**Kiểm tra resource từ root:**

~~~java
URL resource = loader.getResource("example/plugin/greeting.txt");
System.out.println(resource == null ? "missing" : resource);
~~~

Đây là các mảnh minh họa, cần biến `loader` là URLClassLoader cùng imports/exception handling. Đối với file JAR, `jar --list --file your-plugin.jar` giúp phân biệt file thiếu thật với resource lookup sai.

## 10. Sai lầm phổ biến

1. **“URL JAR tải ngay mọi class.”** Không; class được tìm/nạp theo nhu cầu.
2. **“`loadClass` đồng nghĩa initialize.”** Không; nếu cần khởi tạo chủ động, xem `Class.forName(name, true, loader)`.
3. **“ClassLoader tự ghép package hoặc chấp nhận `/` đầu đường resource.”** Dùng path từ classpath root; `Class.getResource` có quy tắc riêng.
4. **“`getResources` chỉ trả một URL.”** Nó có thể liệt kê nhiều resource cùng tên.
5. **“`getResourceAsStream` luôn khác `null` và tự đóng.”** Kiểm tra `null` và đóng stream.
6. **“Host luôn cast được interface cùng tên của plugin.”** Defining loader của API phải là một runtime type chia sẻ.
7. **“Đóng loader khiến mọi method của plugin dừng ngay.”** Class đã nạp còn tồn tại nhưng lazy dependency/resource sau close có thể thất bại.
8. **“URLClassLoader là dependency resolver, module launcher hoặc sandbox.”** Không; đó là những cơ chế khác.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Class `com.acme.Tool` nằm dưới `plugins/classes/com/acme/Tool.class`. URL root nên trỏ tới đâu?

**Đáp án:** `plugins/classes/`, có dạng URL thư mục kết thúc bằng `/`; nạp bằng `loadClass("com.acme.Tool")`.

**Câu 2.** Nếu parent định nghĩa `com.acme.Tool`, `toolClass.getClassLoader() == child` có đúng không?

**Đáp án:** Không, vì defining loader là parent; child chỉ khởi đầu yêu cầu.

**Câu 3.** Resource `com/acme/config.txt` nằm cùng package với Tool. `Tool.class.getResourceAsStream("config.txt")` tương ứng lời gọi nào trên loader?

**Đáp án:** `loader.getResourceAsStream("com/acme/config.txt")`, không phải `loader.getResourceAsStream("config.txt")`.

**Câu 4.** Hai URLClassLoader tự định nghĩa `com.acme.Tool` từ cùng bytecode. Chúng có một runtime type duy nhất không?

**Đáp án:** Không. Binary name giống nhưng defining loader khác tạo hai runtime types.

**Câu 5.** Tại sao phải đóng URLClassLoader?

**Đáp án:** Để giải phóng file/JAR handles và tài nguyên liên quan, không phải để bắt JVM unload class tức thì.

**Câu 6.** Host cần ép kiểu plugin thành interface `PluginApi`. Đặt API ở đâu?

**Đáp án:** Trong thư viện chung do parent định nghĩa để host và plugin dùng đúng một runtime interface.

**Câu 7.** Resource có trong JAR nhưng `getResourceAsStream` trả `null`, cần làm gì trước khi sửa code loader?

**Đáp án:** Kiểm tra tên entry, đường dẫn resource từ root, JAR được loader mở, việc copy resource khi build và nguồn parent.

## 12. Bản đồ quyết định

~~~text
Plugin classes/resources ở thư mục hay JAR?
               |
               v
Tạo URL root đúng bằng Path.toUri().toURL()
               |
               v
Chọn parent hợp lý cho shared APIs
               |
               v
new URLClassLoader(urls, parent)
               |
       +-------+--------+
       |                |
       v                v
  loadClass(name)   getResource(name)
       |                |
       v                v
  Class<?>          URL/InputStream
       |                |
  check defining    đọc resource,
  loader identity   đóng stream
       |
  tạo object nếu cần
       |
       +--------+-------+
                v
   close loader khi hết vòng đời
                |
       close != unload class ngay
~~~

**Tóm tắt:** `URLClassLoader` sử dụng một chuỗi **URL nguồn** kết hợp **parent delegation**. Muốn nạp class đúng phải có binary name và đúng URL root; muốn tìm resource đúng phải có path theo API; muốn plugin chạy ổn định cần quản lý type identity, dependency và vòng đời stream/loader.

### Tài liệu chính thức

- [Java SE 17 — URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [Java SE 17 — ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — Class.getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String))
- [JVMS `5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)

# Vì sao không nên ép application class loader thành URLClassLoader?

> **Phạm vi:** Java Core → ClassLoader → Loader tích hợp. Trọng tâm là giả định sai về kiểu cụ thể của *application/system class loader*, thay đổi từ JDK 9, hậu quả của phép ép kiểu, và các API an toàn để tra cứu tài nguyên hoặc nạp lớp từ đường dẫn riêng. Ví dụ sử dụng Java 17+.

## 1. Tình huống: đoạn code từng chạy trên JDK 8 nhưng lỗi trên Java hiện đại

Một đoạn code cũ có thể lấy application class loader bằng `ClassLoader.getSystemClassLoader()`, ép nó thành `URLClassLoader` rồi lấy danh sách URL hoặc cố thêm JAR:

```java
import java.net.URLClassLoader;

public class OldCode {
    public static void main(String[] args) {
        URLClassLoader loader =
                (URLClassLoader) ClassLoader.getSystemClassLoader();
        System.out.println(loader.getURLs().length);
    }
}
```

Biên dịch/chạy:

```bash
javac OldCode.java
java OldCode
```

Với bộ khởi chạy OpenJDK 21 thông thường, **phép ép kiểu ném `ClassCastException`** trước khi kịp gọi `getURLs()`. Không cần thiếu JAR hay sai đường dẫn: object do `getSystemClassLoader()` trả về đơn giản không phải một instance của `URLClassLoader`.

Vì sao code cũ đôi khi có vẻ hợp lệ? Trên một số JDK 8 (đặc biệt các bản Oracle/OpenJDK mặc định), application loader được triển khai bằng một subclass của `URLClassLoader`. Nhiều chương trình đã vô tình dựa vào chi tiết này. **Java SE API chưa bao giờ cam kết** system loader phải kế thừa `URLClassLoader`. Từ JDK 9, application loader tích hợp trên JDK dùng một lớp triển khai nội bộ khác; việc ép sang `URLClassLoader` theo thói quen không còn hoạt động.

**Kết luận thực hành:** biến cần dùng để tương tác với application loader thường phải có kiểu `ClassLoader`, và thao tác nên dựa trên hợp đồng `ClassLoader`. Chỉ dùng các tính năng riêng của `URLClassLoader` khi bạn **thực sự đã tạo hoặc được cung cấp** một instance của loại loader ấy.

## 2. Phân biệt tên gọi với kiểu runtime

Có ba khái niệm dễ bị nhầm:

- **Application (app) class loader tích hợp:** loader mặc định mà bộ khởi chạy JDK dùng để tải lớp ứng dụng từ các nguồn phù hợp (classpath và/hoặc application modules theo cấu hình).
- **System class loader:** object trả về từ `ClassLoader.getSystemClassLoader()`; thường là app loader cho chương trình chuẩn, **có thể bị thay thế** bằng custom loader qua thuộc tính `java.system.class.loader`.
- **`java.net.URLClassLoader`:** một lớp API công khai **có khả năng tải class/resource từ chuỗi URL** trỏ đến directory hoặc JAR. Đây là **một implementation cụ thể** của `ClassLoader`, không đồng nghĩa với mọi application loader.

Định hướng kiểu:

```text
java.lang.ClassLoader                      (API khái quát)
       |
       +-- java.security.SecureClassLoader
                   |
                   '-- java.net.URLClassLoader       (một subclass cụ thể)

ClassLoader.getSystemClassLoader()
       |
       '-- trả về một ClassLoader do runtime quy định
           (không có bảo đảm instanceof URLClassLoader)
```

Sơ đồ chỉ diễn tả **cấu trúc kế thừa API và kiểu trả về**, không minh họa cây parent delegation. Parent loader và quan hệ kế thừa class là hai vấn đề khác nhau.

Trên các JDK OpenJDK 9+ thường gặp, kiểu triển khai cụ thể có tên tương tự `jdk.internal.loader.ClassLoaders$AppClassLoader`. Tên package nội bộ đó dùng để chẩn đoán, **không phải lớp API công khai để ứng dụng import, ép kiểu hay truy cập qua reflection**.

### Vì sao JDK 9 thay đổi?

JDK 9 đưa vào Java Platform Module System (JPMS), cùng tổ chức lại các built-in class loader. Release Notes chính thức nêu rõ application loader không còn là instance của `URLClassLoader`; đồng thời extension loader cũ được thay bằng *platform class loader*. Runtime có thể tìm lớp từ classpath **và** môi trường module, nên suy diễn toàn bộ cơ chế class loading từ một mảng URL là không đầy đủ.

Bảng so sánh:

| Môi trường | Đặc điểm thường gặp | Có thể ép system loader thành `URLClassLoader`? |
| --- | --- | --- |
| Oracle/OpenJDK 8 mặc định | App loader từng là subclass của `URLClassLoader` | Có thể thành công trong cấu hình đó, nhưng vẫn phụ thuộc implementation. |
| JDK 9+ mặc định (Oracle/OpenJDK) | Built-in app loader không phải `URLClassLoader` | **Không**; ép kiểu gây `ClassCastException`. |
| JDK 9+ có `-Djava.system.class.loader=...` | System loader là implementation do ứng dụng chỉ định | Phụ thuộc đúng instance được tạo; **không thể giả định**. |
| Runtime/launcher chuyên biệt | Cơ chế loader có thể được tùy chỉnh | Dựa vào API/contract của môi trường thực tế. |

Không nên diễn đạt “mọi Java 9+ đều tuyệt đối không có `URLClassLoader`”: **bạn vẫn có thể tự tạo `URLClassLoader`** và dùng bình thường. Thay đổi nói tới kiểu của **application loader tích hợp mặc định**.

## 3. Tại sao ép kiểu là lỗi thiết kế, kể cả khi tình cờ chạy được?

### 3.1. `ClassCastException` lúc runtime

Ép kiểu `(URLClassLoader) someLoader` chỉ hợp lệ nếu `someLoader instanceof URLClassLoader`. Kiểu tĩnh mà method khai báo trả về là `ClassLoader` **không tạo ra quan hệ kế thừa ngược**.

Vì compiler thấy `URLClassLoader` là subclass hợp lệ của `ClassLoader` nên đoạn cast có thể **biên dịch thành công** trên Java 17 hoặc 21. Tuy nhiên, khi chạy, JVM kiểm tra kiểu thật của object và có thể ném `ClassCastException`. Đây là lỗi kiểu runtime, không phải lỗi `ClassNotFoundException` hay `NoClassDefFoundError` do thiếu dependency.

### 3.2. Lấy danh sách URL không phải cách chuẩn để biết mọi nơi JVM tìm class

`URLClassLoader.getURLs()` chỉ nói về các URL của **instance URLClassLoader cụ thể**. Nó không phải API hỏi “toàn bộ classpath/module path của JVM” hay “tất cả class có thể được tải”, và không cung cấp inventory các module, các nguồn được parent delegate, hoặc tài nguyên sinh động.

`System.getProperty("java.class.path")` cho một **thuộc tính khởi động** hữu ích khi chẩn đoán classpath, nhưng cũng không phải phép liệt kê đầy đủ mọi nguồn class/resource trong ứng dụng dùng modules, manifest `Class-Path`, custom class loaders hoặc container. Không coi nó là bản sao khả biến của runtime classpath.

### 3.3. Cố thêm JAR vào application loader bằng API không được bảo đảm

`URLClassLoader.addURL(URL)` là **protected**, không phải method public dành cho caller tùy ý mở rộng loader hiện có. Code cũ đôi khi dùng subclass, reflection hoặc truy cập implementation nội bộ để thêm đường dẫn vào system loader.

Trên Java 9+:

- Built-in app loader không có nghĩa vụ cung cấp method hoặc cấu trúc dữ liệu của `URLClassLoader`.
- Strong encapsulation của JPMS hạn chế reflection vào các package nội bộ JDK; ép `setAccessible(true)` không biến một API nội bộ thành hợp đồng bền vững.
- Cờ kiểu `--add-opens` để “lách” truy cập không sửa được giả định **sai loại object** và có thể tạo sự phụ thuộc khó bảo trì.
- Java SE/JDK không cung cấp **API ứng dụng chung** để tùy ý mở rộng application classpath trong lúc runtime đang chạy.

Nếu bài toán thật sự là nạp plugin/JAR động, hãy sở hữu một loader riêng hoặc dùng cơ chế plugin/agent được thiết kế cho mục đích ấy.

## 4. Kiểm tra runtime đúng cách: nhìn loại object mà không ép bừa

Tạo file `InspectLoader.java`:

```java
import java.net.URLClassLoader;

public class InspectLoader {
    public static void main(String[] args) {
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("system is URLClassLoader: "
                + (system instanceof URLClassLoader));
        System.out.println("system loader type: "
                + system.getClass().getName());
    }
}
```

Chạy:

```bash
javac InspectLoader.java
java InspectLoader
```

Đầu ra **đã quan sát trên OpenJDK 21 mặc định**:

```text
system is URLClassLoader: false
system loader type: jdk.internal.loader.ClassLoaders$AppClassLoader
```

Dòng thứ hai là **tên chi tiết implementation**, có thể khác trên các JVM/cấu hình. Dòng thứ nhất cũng có thể khác nếu system loader được tùy biến; ví dụ minh họa tình huống thường gặp, không phải một API guarantee trên mọi môi trường.

Nếu nhận `ClassLoader` từ API không kiểm soát, pattern matching `instanceof` của Java 17 cho phép dùng khả năng `URLClassLoader` **chỉ khi có**:

```java
// Đoạn minh họa đặt trong method có biến ClassLoader loader:
if (loader instanceof URLClassLoader urlLoader) {
    for (var url : urlLoader.getURLs()) {
        System.out.println(url);
    }
} else {
    System.out.println("Loader does not expose URLClassLoader APIs");
}
```

Đoạn này **không phải chương trình độc lập** vì `loader` là biến trong ngữ cảnh bên ngoài. Đây là biện pháp tương thích khi một interface cho phép nhiều loại loader; nó **không** phải cách chung để tìm classpath hay thêm JAR. Khi không phải `URLClassLoader`, nên dùng API phù hợp với mục tiêu thay vì cố ép.

## 5. Chọn API theo nhu cầu thực sự

| Bạn cần làm gì? | API / cách phù hợp | Tránh |
| --- | --- | --- |
| Nạp lớp bằng tên đã biết | `Class.forName(binaryName)`, overload có loader, hoặc `ClassLoader.loadClass(binaryName)` | Suy ra loader phải là `URLClassLoader`. |
| Tìm tài nguyên trong những nguồn loader nhìn thấy | `loader.getResource(name)` / `getResources(name)` / `getResourceAsStream(name)` | Ép loader rồi tự ghép đường dẫn URL/JAR. |
| Đọc file cấu hình trong cùng JAR của một lớp | `SomeClass.class.getResourceAsStream("/config.properties")` | Giả định tài nguyên là `java.io.File` trên đĩa. |
| Chẩn đoán command-line classpath | `System.getProperty("java.class.path")` cùng launch command/build metadata | Coi chuỗi ấy là toàn bộ module graph và dynamic class loading. |
| Nạp JAR/directory mở rộng lúc chạy | **Tạo `URLClassLoader` riêng** có URL và parent thích hợp; hoặc custom loader | Thay đổi system loader qua cast/reflection. |
| Tìm provider/plugin theo hợp đồng SPI | `ServiceLoader` với class loader phù hợp, module `uses/provides` khi dùng JPMS | Hardcode đường dẫn tới implementation rồi ép system loader. |
| Làm việc với module runtime | `ModuleLayer` và module APIs khi cần tải từ một cấu hình module mới | Đồng nhất module path với các URL của app loader. |

Một ví dụ tìm resource không cần biết loader là subclass nào:

```java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ReadResource {
    public static void main(String[] args) throws Exception {
        try (InputStream stream =
                ReadResource.class.getResourceAsStream("/message.txt")) {
            if (stream == null) {
                System.out.println("Resource not found");
                return;
            }
            System.out.println(new String(
                    stream.readAllBytes(), StandardCharsets.UTF_8));
        }
    }
}
```

Đây là **chương trình độc lập**, nhưng để in nội dung phải có file `message.txt` tại classpath root (ví dụ đặt cạnh `ReadResource.class` khi chạy từ thư mục chứa class). Nếu không có resource, stdout chính xác là:

```text
Resource not found
```

Tên resource dùng `/`; `Class.getResourceAsStream("/message.txt")` là đường dẫn tuyệt đối trong phạm vi tìm kiếm tài nguyên của lớp. API trả về `InputStream` để mã vẫn phù hợp khi tài nguyên nằm trong JAR, không phải file vật lý.

## 6. Nạp plugin đúng cách bằng URLClassLoader do ứng dụng sở hữu

Trong tình huống plugin nằm ở thư mục hoặc JAR ngoài classpath khởi động, ta có thể **tạo một `URLClassLoader` mới**. Loader này chủ động nhận URL và có vòng đời quản lý rõ ràng.

Cấu trúc ví dụ:

```text
plugin-src/
  plugin/
    Greeting.java
app-src/
  LoaderDemo.java
plugin-out/     (tạo bởi javac)
app-out/        (tạo bởi javac)
```

**File `plugin-src/plugin/Greeting.java`:**

```java
package plugin;

public class Greeting {
    public static String message() {
        return "Hello from plugin";
    }
}
```

**File `app-src/LoaderDemo.java`:**

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class LoaderDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Path.of("plugin-out").toAbsolutePath();
        URL pluginUrl = directory.toUri().toURL();
        ClassLoader app = ClassLoader.getSystemClassLoader();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[]{pluginUrl}, ClassLoader.getPlatformClassLoader())) {
            Class<?> type = Class.forName(
                    "plugin.Greeting", true, pluginLoader);
            String message = (String) type.getMethod("message").invoke(null);

            System.out.println("message: " + message);
            System.out.println("owned loader: "
                    + (type.getClassLoader() == pluginLoader));
            System.out.println("app loader unchanged: "
                    + (ClassLoader.getSystemClassLoader() == app));
        }
    }
}
```

Từ thư mục cha chứa `plugin-src` và `app-src`, chạy:

```bash
javac -d plugin-out plugin-src/plugin/Greeting.java
javac -d app-out app-src/LoaderDemo.java
java -cp app-out LoaderDemo
```

**Stdout chính xác trên OpenJDK 21 (đã biên dịch/chạy kiểm tra):**

```text
message: Hello from plugin
owned loader: true
app loader unchanged: true
```

Những điểm quan trọng:

1. `plugin-out` chứa `plugin/Greeting.class` và **không nằm trong `-cp app-out`**, nên application loader của ví dụ không trực tiếp nhìn thấy plugin qua launch classpath.
2. `directory.toUri().toURL()` tạo một `file:` URL kết thúc bằng `/` cho directory, phù hợp với `URLClassLoader`. Để nạp từ JAR, truyền `file:` URL của JAR thay vì URL thư mục.
3. Ta truyền `ClassLoader.getPlatformClassLoader()` làm parent để ví dụ chỉ cần Java platform APIs và tránh parent application loader nhận diện plugin trùng tên. Đây là **lựa chọn mô phỏng isolation cho ví dụ**.
4. `Class.forName(name, true, pluginLoader)` dùng loader được chỉ định để tìm class và yêu cầu initialization; `Class#getClassLoader() == pluginLoader` xác nhận **defining loader** ở ví dụ này.
5. `try-with-resources` gọi `URLClassLoader.close()` sau khi dùng để giải phóng các file/JAR handle do loader mở, giúp quản lý vòng đời. `close()` **không bảo đảm unload class đã nạp**; việc unload phụ thuộc khả năng JVM thu hồi class loader và các object/tham chiếu liên quan.
6. Chương trình không ép, thay đổi hoặc sửa internals của system loader. Việc tạo loader mới cho plugin là hành động tách biệt và được hỗ trợ qua API công khai.

### Chọn parent của plugin loader cho đúng

`URLClassLoader` mặc định thực hiện **parent-first delegation**: trước khi tự tìm lớp từ URL của mình, nó thường để parent thử tải class. Trong thực tế có hai tình huống:

- **Plugin độc lập chỉ dùng Java platform:** parent `ClassLoader.getPlatformClassLoader()` như ví dụ đủ cho `java.base` và các API Java SE phù hợp; hạn chế nhìn thấy lớp ứng dụng.
- **Plugin phải implement interface của host:** parent thường cần là loader nhìn thấy interface dùng chung, ví dụ `LoaderDemo.class.getClassLoader()`. Nếu host và plugin mỗi bên tự định nghĩa `com.example.Plugin` bằng loader khác nhau, object mang cùng *binary name* vẫn có thể **không cast được** qua interface của host.

Ví dụ cấu hình parent khi plugin cần host API (chỉ minh họa, không phải chương trình chạy độc lập):

```java
ClassLoader hostLoader = HostPluginApi.class.getClassLoader();
try (URLClassLoader pluginLoader =
        new URLClassLoader(pluginUrls, hostLoader)) {
    // Load implementation từ plugin; parent cung cấp cùng HostPluginApi.
}
```

Ở đoạn này `HostPluginApi` và `pluginUrls` là các symbol giả định thuộc hệ thống plugin đang phát triển. Đừng copy độc lập mà không định nghĩa chúng. Parent-first cũng có nghĩa nếu parent đã thấy một class cùng tên, parent có thể thắng plugin; cần thiết kế package boundary rõ ràng và kiểm soát trùng lớp, không âm thầm dựa vào thứ tự URL.

## 7. Built-in loader, classpath, module path và context loader

Khi debug, cần phân biệt một vài loader/nguồn lớp:

| Thành phần | Cách lấy/ý nghĩa | Lưu ý |
| --- | --- | --- |
| Bootstrap loader | `String.class.getClassLoader()` thường trả `null`. | `null` là cách Java API biểu diễn bootstrap loader, không phải lỗi. |
| Platform loader | `ClassLoader.getPlatformClassLoader()` (Java 9+). | Có thể nhìn thấy Java platform classes thông qua delegation; không kết luận class nào nhất định được định nghĩa trực tiếp bởi platform loader. |
| System/application loader | `ClassLoader.getSystemClassLoader()`. | Implementation-dependent; có thể custom qua `java.system.class.loader`. |
| Loader của một lớp cụ thể | `SomeClass.class.getClassLoader()`. | Thường đáng tin hơn giả định loader toàn cục khi tìm resource liên quan lớp. |
| Thread context class loader (TCCL) | `Thread.currentThread().getContextClassLoader()`. | Có thể khác system loader hoặc `null`; frameworks/SPI hay sử dụng nó để tìm provider. |

`ServiceLoader.load(MyService.class)` thường dùng TCCL theo API; `ServiceLoader.load(MyService.class, loader)` cho phép chọn loader chủ động. Trong ứng dụng modular, `uses` và `provides` hoặc module layer quyết định thêm yếu tố dịch vụ. **ServiceLoader giải bài toán khám phá provider**, còn `URLClassLoader` giải bài toán tìm class/resource từ các URL; không tráo hai mục đích cho nhau.

Với JPMS, named modules có ranh giới đọc module, package exports/opens và nguồn module path. Việc một loader có thể tìm thấy bytecode **chưa chắc** chương trình được quyền truy cập mọi class/member qua reflection. Không thể giải quyết mọi vấn đề access chỉ bằng cách thêm một URL.

## 8. Nếu thật sự cần mở rộng classpath ở runtime thì sao?

Đầu tiên phân loại yêu cầu:

**A. Chỉ muốn thêm dependency cố định khi khởi động.** Cấu hình launcher/build tool bằng `-cp`, `--class-path` hoặc `--module-path` trước khi khởi động JVM. Không cần class loader động.

**B. Muốn plugin mới được phát hiện sau startup.** Tạo một class loader ứng dụng kiểm soát riêng cho plugin và API giao tiếp với host; cần xét phiên bản, quyền truy cập, resource, đóng loader và unload. Không có bảo đảm mọi thư viện trên system loader tự nhận plugin mới.

**C. Muốn plugin có vòng đời, dependency và isolation đầy đủ.** Dùng mô hình plugin/SPI, `ServiceLoader`, hoặc xây/module layer thích hợp; với hệ thống nhiều plugin, thiết kế quản lý parent và class identity riêng.

**D. Muốn Java agent thay đổi classpath phục vụ instrumentation.** `java.lang.instrument.Instrumentation` có các API giới hạn như `appendToSystemClassLoaderSearch(JarFile)` trong ngữ cảnh agent hợp lệ. Đây là cơ chế dành cho agent, **không phải API chung của code ứng dụng** và không biến system loader thành `URLClassLoader`. Nó mang điều kiện riêng về class visibility và tìm class.

**E. Muốn nhìn danh sách nơi một class đang được nạp.** Sử dụng công cụ JVM phù hợp, ví dụ log class loading (`-Xlog:class+load=info` trên HotSpot), build/deploy metadata, `clazz.getProtectionDomain().getCodeSource()` khi có thể; code source có thể `null` và vẫn không đại diện đầy đủ cho mọi resource của loader. Không dựa một phép cast để đoán cả classpath.

## 9. Những lỗi phổ biến khi nâng cấp JDK hoặc viết framework

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `ClassCastException` giữa `AppClassLoader` và `URLClassLoader` | Ép system/app loader sang subclass không đúng kiểu. | Bỏ cast; dùng API `ClassLoader` hoặc tạo `URLClassLoader` riêng. |
| `InaccessibleObjectException` sau khi gọi `setAccessible(true)` | Truy cập trái phép implementation nội bộ do encapsulation. | Chuyển sang API công khai; không coi `--add-opens` là chiến lược thiết kế. |
| Tự sửa `java.class.path` nhưng `ClassNotFoundException` vẫn xảy ra | Đổi chuỗi system property không thay đổi nguồn tìm kiếm của loader đã thiết lập. | Cấu hình lúc startup hoặc dùng loader riêng. |
| Plugin nạp được nhưng cast về interface của host lỗi | Host và plugin có các bản class/interface do defining loader khác nhau. | Dùng một API chung từ parent loader được chia sẻ, phân tích class identity. |
| Resource chạy trong IDE nhưng không tìm được trong JAR | Giả định `file:` path hoặc đường dẫn tài nguyên sai. | Dùng `getResourceAsStream`; kiểm tra JAR contents và tên resource. |
| `NoClassDefFoundError` khi nạp plugin | Thiếu dependency ở loader/parent, hoặc class từng khởi tạo thất bại. | Đọc `Caused by`, dependency graph, loader boundaries và thời điểm initialization. |
| Plugin không unload dù gọi `close()` | Thread, static field, cache hoặc object vẫn giữ tham chiếu tới loader/class. | Kiểm tra vòng đời/references; `close()` chỉ đóng tài nguyên mở. |
| Không tìm thấy class trong named module dù có file | Module graph/loader/access khác suy đoán từ classpath. | Kiểm tra module configuration, layer, `exports`/`opens` và launch options. |

**Quy trình debug:** xác định chính xác loader của **class đang lỗi**, xem kiểu runtime bằng `getClass().getName()` để chẩn đoán (không để điều khiển logic), kiểm tra `instanceof` khi thực sự cần API subclass, kiểm tra module/classpath và resource. Sau đó chọn giải pháp theo mục tiêu: lookup, resource, plugin, SPI hay module.

## 10. Câu hỏi tự kiểm tra

1. **`ClassLoader.getSystemClassLoader()` khai báo trả về loại gì?**  
   `ClassLoader`. Không có contract Java SE rằng object runtime phải là `URLClassLoader`.
2. **Vì sao một cast từng chạy trên Oracle/OpenJDK 8 có thể lỗi trên Java 17/21?**  
   JDK 9 đã thay implementation built-in application loader, vốn không còn kế thừa `URLClassLoader`.
3. **`instanceof URLClassLoader` giải quyết được mọi yêu cầu tìm classpath không?**  
   Không. Nó chỉ kiểm tra khả năng của một instance; `getURLs()` không phản ánh mọi module, parent delegation hoặc loader khác.
4. **Nếu muốn tìm `config/app.properties` đóng gói trong JAR, nên dùng gì?**  
   `SomeClass.class.getResourceAsStream("/config/app.properties")` (hoặc loader-specific resource API), không ép class loader thành `URLClassLoader`.
5. **Nếu muốn nạp thư mục plugin sau khi app đã chạy, phải đổi system loader không?**  
   Không. Tạo và quản lý loader riêng hoặc thiết kế cơ chế plugin/module theo yêu cầu.
6. **Nếu plugin implement interface của host, nên chọn parent nào?**  
   Một parent có thể thấy **cùng định nghĩa interface** với host; thường loader định nghĩa host API, không mặc định chọn platform loader.
7. **`URLClassLoader.close()` có nghĩa là class đã unload ngay lập tức?**  
   Không. Nó đóng tài nguyên mở, còn class unloading phụ thuộc việc còn reachable references hay không.

## 11. Tài liệu chuẩn

- [Oracle JDK 9 Release Notes — Class Loader Changes](https://www.oracle.com/java/technologies/javase/9-relnotes.html): xác nhận application loader tích hợp không còn là `URLClassLoader` từ JDK 9.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): kiểu trả về/hợp đồng của `getSystemClassLoader`, `getPlatformClassLoader`, `getResource` và delegation.
- [Java SE 21 — `URLClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): constructor URL/parent, `getURLs`, `addURL`, `close`.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): bối cảnh JPMS và việc tổ chức lại loader.
- [Java SE 21 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): khám phá service provider có chỉ định class loader.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): cơ chế dành cho Java agent, `appendToSystemClassLoaderSearch`.

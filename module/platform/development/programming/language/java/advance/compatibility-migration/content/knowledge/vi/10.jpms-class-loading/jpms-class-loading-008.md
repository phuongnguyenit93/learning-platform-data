# ClassLoader sau JDK 8 và giả định ép kiểu sang URLClassLoader

Khi nâng cấp một ứng dụng hoặc thư viện từ Java 8 lên Java 9, 11, 17, 21 hoặc các bản JDK mới hơn, một lỗi phổ biến xuất hiện rất sớm trong quá trình khởi động:

```text
java.lang.ClassCastException:
  class jdk.internal.loader.ClassLoaders$AppClassLoader
  cannot be cast to class java.net.URLClassLoader
```

Lỗi này thường bắt nguồn từ đoạn mã đã hoạt động trên JDK 8:

```java
URLClassLoader loader =
    (URLClassLoader) ClassLoader.getSystemClassLoader();
```

Trên các bản OpenJDK/Oracle JDK 8 phổ biến, application class loader được triển khai dựa trên `URLClassLoader`. Từ JDK 9, hệ thống nạp lớp của JDK được tổ chức lại để hỗ trợ Java Platform Module System (JPMS). Application class loader mặc định không còn là một instance của `URLClassLoader`. Mã ép kiểu trên vì vậy không có hợp đồng tương thích và có thể ném `ClassCastException`.

Điểm mấu chốt là: **`ClassLoader` là abstraction được bảo đảm; một lớp triển khai cụ thể của system class loader không phải hợp đồng để code ứng dụng dựa vào.** `URLClassLoader` vẫn là một API công khai và còn hữu ích khi ứng dụng tự tạo loader để nạp JAR/plugin. Thứ không còn an toàn là giả định rằng loader do JVM tạo sẵn nhất định thuộc kiểu này.

Bài học trình bày các thay đổi sau JDK 8, khác biệt giữa classpath và module path, cách truy xuất resource, cách nạp JAR động, vai trò của context class loader, và quy trình migration để loại bỏ những phép ép kiểu phụ thuộc implementation.

## 1. Trước hết: ClassLoader thực sự làm gì?

`ClassLoader` là thành phần Java dùng để tìm và định nghĩa các class cần thiết cho JVM. Khi một class tham chiếu một class khác, JVM phải tìm ra định nghĩa tương ứng từ classpath, module, loader tùy chỉnh hoặc cơ chế đã được thiết lập bởi runtime.

Một số khái niệm cần tách riêng:

- **Binary name của class:** tên như `com.example.service.OrderService`.
- **Defining class loader:** loader thực sự định nghĩa class trong JVM.
- **Initiating class loader:** loader được yêu cầu nạp class, có thể ủy quyền việc định nghĩa cho loader khác.
- **Class identity:** về nguyên tắc được xác định bởi tên nhị phân và defining loader. Hai class cùng tên nhưng được định nghĩa bởi hai loader khác nhau là hai kiểu khác nhau.
- **Resource:** file dữ liệu đi kèm class/JAR, có thể được tìm qua API resource của loader hoặc module, nhưng không phải bản thân `Class`.

Cơ chế parent delegation là hành vi phổ biến: loader hỏi parent trước rồi mới thử tìm class ở nguồn của chính nó. Điều này giúp hạn chế việc một ứng dụng vô tình thay thế các class nền tảng và giữ thống nhất các kiểu dùng chung. Tuy nhiên, không phải mọi class loader tùy chỉnh đều dùng chính sách parent-first; plugin container và application server có thể có các quy tắc riêng.

Một sơ đồ tư duy đơn giản cho các runtime phổ biến:

```text
Bootstrap loader
    |
Platform loader
    |
Application (system) loader
    |
Custom loader(s) do framework/ứng dụng tạo
```

Sơ đồ là cách hình dung quan hệ phổ biến, không phải mô tả đầy đủ mọi đường đọc module hay mọi topology của class loader. Trong JPMS, khả năng đọc module và việc loader nào định nghĩa class không thể được suy ra hoàn toàn từ một chuỗi parent.

### 1.1. Khi nào nên dùng ClassLoader?

Các nhu cầu phổ biến:

1. Nạp một class theo tên trong lúc chạy, ví dụ plugin hoặc provider.
2. Tìm resource như `application.properties`, template hoặc file định dạng.
3. Phát hiện loader nào thực sự nạp một class để chẩn đoán xung đột dependency.
4. Dùng `ServiceLoader` để tìm provider theo cơ chế Java SPI.
5. Tạo loader riêng cho plugin hoặc cho một nhóm JAR có vòng đời độc lập.

Không cần tự thao tác `ClassLoader` để tạo instance của những class mà chương trình đã biết rõ khi biên dịch. Những lớp như thế nên được tham chiếu bằng cách thông thường, giúp compiler và build tool kiểm tra dependency.

## 2. Điều gì thay đổi khi đi từ JDK 8 sang JDK 9+?

### 2.1. JDK 8: bootstrap, extension và application loader

Ở JDK 8, một mô hình phổ biến gồm:

| Loader | Vai trò quen thuộc |
|---|---|
| Bootstrap | Nạp các class nền tảng của JDK |
| Extension | Nạp các extension được cấu hình theo cơ chế extension |
| Application/System | Nạp class ứng dụng theo classpath |

Trong các bản OpenJDK/Oracle JDK 8 thông dụng, application class loader và extension class loader là các implementation kế thừa `URLClassLoader`. Điều này khiến nhiều đoạn mã tình cờ thành công khi ép `ClassLoader.getSystemClassLoader()` sang `URLClassLoader`.

Nhưng method `ClassLoader.getSystemClassLoader()` có kiểu trả về được công bố là `ClassLoader`, **không phải** `URLClassLoader`. Kiểu implementation thực tế là chi tiết của JDK đang chạy và có thể khác khi vendor, phiên bản hoặc cấu hình loader thay đổi.

Ngay cả trên JDK 8, code ép kiểu như vậy vẫn dựa vào một giả định yếu: ứng dụng có thể cấu hình system loader tùy chỉnh hoặc chạy trong môi trường mà class loading không giống một Java launcher thông thường.

### 2.2. JDK 9: JPMS và cấu trúc loader mới

Từ Java 9, JPMS được đưa vào JDK. Các runtime module thay đổi cách đóng gói platform classes và làm rõ module readability, exports và opens. Cùng lúc, cách thực thi các built-in class loader được điều chỉnh.

Mô hình được công bố qua API gồm:

- **Bootstrap class loader:** cơ chế nền tảng để nạp các class lõi. Không có một object `ClassLoader` công khai đại diện cho nó trong nhiều API chẩn đoán.
- **Platform class loader:** có thể lấy qua `ClassLoader.getPlatformClassLoader()`, thay vai trò extension loader trước đây.
- **System/application class loader:** có thể lấy qua `ClassLoader.getSystemClassLoader()`. Nó thường nạp class trên application classpath và một số application module trên module path.

Ở những runtime OpenJDK hiện đại, system loader mặc định có thể có class name tương tự `jdk.internal.loader.ClassLoaders$AppClassLoader`. Đây là implementation nội bộ, **không phải** kiểu API mà ứng dụng nên import, ép kiểu hoặc phản chiếu để gọi các method riêng.

`URLClassLoader` **không bị xóa khỏi Java**. Nó vẫn tồn tại trong package `java.net` và có thể được tạo trực tiếp cho các trường hợp nạp URL/JAR do ứng dụng kiểm soát.

### 2.3. Extension mechanism của JDK 8 không còn là đường triển khai

Cơ chế extension directory và endorsed standards override của các JDK cũ không còn là mô hình triển khai được hỗ trợ theo cách trước JDK 9. Các script từng dựa vào `java.ext.dirs`, `java.endorsed.dirs` hoặc việc chép JAR vào thư mục extension cần được thiết kế lại.

Hướng triển khai hiện đại:

- Với thư viện thông thường, khai báo dependency và đưa chúng vào classpath hoặc module path.
- Với ứng dụng modular, định nghĩa module và các quan hệ `requires`/`exports`/`opens`.
- Với plugin runtime, dùng loader tùy chỉnh hoặc module layer theo hợp đồng rõ ràng.
- Với nâng cấp module thuộc nền tảng, chỉ dùng những cơ chế được JDK hỗ trợ và được tài liệu hóa; tránh thay thế class nền tảng bằng hack classloader.

### 2.4. So sánh ở mức hợp đồng

| Vấn đề | Điều dễ gặp trên JDK 8 | Điều nên làm trên JDK 9+ |
|---|---|---|
| Lấy system loader | `ClassLoader.getSystemClassLoader()` | Giữ nguyên API này nếu thật sự cần system loader |
| Giả định system loader là URLClassLoader | Thường tình cờ đúng | Sai; kiểm tra kiểu và bỏ ép kiểu |
| Lấy extension loader | Có extension mechanism | Dùng `getPlatformClassLoader()` khi cần platform loader |
| Liệt kê URL hệ thống | Ép sang `URLClassLoader` rồi `getURLs()` | Dùng dependency metadata và diagnostics phù hợp với classpath/module |
| Thêm JAR lúc chạy | Gọi method nội bộ hoặc phản chiếu vào app loader | Tạo loader do ứng dụng sở hữu, hoặc dùng plugin/module layer |
| Nạp class từ module path | Không có JPMS | Xem module ownership, readability và exports/opens |
| Tìm resource | Thường tìm theo classpath | Vẫn có resource APIs, nhưng cần lưu ý module encapsulation |

## 3. Vì sao phép ép kiểu sang URLClassLoader thất bại?

### 3.1. Code gây lỗi

```java
import java.net.URLClassLoader;

public class LegacyLoaderCode {
    public static void main(String[] args) {
        URLClassLoader loader =
            (URLClassLoader) ClassLoader.getSystemClassLoader();

        for (var url : loader.getURLs()) {
            System.out.println(url);
        }
    }
}
```

Khai báo `URLClassLoader` ở biến cục bộ **không** khiến system loader trở thành `URLClassLoader`. Java kiểm tra kiểu instance tại runtime. Nếu object không thuộc kiểu được ép, JVM ném `ClassCastException`.

Ví dụ trên có thể chạy trên JDK 8 của một vendor nhất định nhưng thất bại trên JDK 17 hoặc 21. Vấn đề không phải `getURLs()` bị đổi tên. Vấn đề là chương trình lấy một object không do mình tạo rồi giả định implementation của object đó.

### 3.2. Method `getURLs()` thuộc URLClassLoader, không thuộc ClassLoader

`URLClassLoader.getURLs()` trả về những URL đã được cấu hình cho **chính URLClassLoader đó**. `ClassLoader` cơ sở không hứa cung cấp danh sách URL, vì không phải mọi loader tìm class từ URL.

Một loader có thể lấy class từ:

- Runtime module image.
- Một archive hoặc hệ thống file khác URL thông thường.
- Byte array được tạo hoặc biến đổi lúc chạy.
- Network hoặc kho plugin tùy chỉnh.
- Container/application server.
- Classloader graph với nhiều nguồn khác nhau.

Do đó, một API chung để “lấy tất cả JAR mà mọi class loader nhìn thấy” không thể được suy ra từ `ClassLoader.getSystemClassLoader()`.

### 3.3. Không nên sửa bằng cách phản chiếu implementation nội bộ

Một số đoạn migration sai thường xuất hiện:

```java
// KHÔNG NÊN: phụ thuộc implementation nội bộ.
Class<?> impl = Class.forName(
    "jdk.internal.loader.ClassLoaders$AppClassLoader"
);

// KHÔNG NÊN: tìm phương thức nội bộ addURL bằng reflection.
// KHÔNG NÊN: mở hàng loạt package nội bộ chỉ để sửa giả định cũ.
```

Từ Java 9, module encapsulation có thể từ chối reflective access đến các thành phần nội bộ. Các tùy chọn `--add-opens` hoặc `--add-exports` có thể thay đổi quyền truy cập trong những trường hợp cần thiết, nhưng không biến implementation nội bộ thành API ổn định.

Hãy xác định **mục đích gốc** của phép ép kiểu: liệt kê classpath, nạp resource, hay thêm JAR động? Mỗi mục đích có một giải pháp khác nhau.

## 4. Chọn đúng giải pháp theo mục đích

| Mục đích gốc của mã cũ | Giải pháp phù hợp | Điều cần tránh |
|---|---|---|
| Tìm file cấu hình hoặc template | `getResourceAsStream`, `getResource` hoặc `Module.getResourceAsStream` | Ép system loader sang `URLClassLoader` để lục URL |
| Lấy đường dẫn classpath phục vụ log | `java.class.path`, dữ liệu từ build/launch config | Coi classpath là toàn bộ module path hoặc mọi nguồn class |
| Biết một class được nạp từ đâu | `Class.getProtectionDomain()`/`CodeSource` khi có, `getClassLoader()`/`getModule()` | Coi URL hoặc `CodeSource` luôn tồn tại |
| Nạp class từ một JAR plugin | Tạo `URLClassLoader` của riêng ứng dụng | Cố thêm URL vào system loader |
| Tìm service implementation | `ServiceLoader` với loader hoặc layer phù hợp | Quét mọi JAR rồi tự ép kiểu hoặc quét package nội bộ |
| Nạp ứng dụng modular | Module path, `ModuleLayer` | Giả định mọi named module nằm trên classpath |
| Chẩn đoán lỗi linkage | Logging, `-Xlog:class+load`, `jdeps`, module metadata | Chỉ in `getURLs()` của một loader |

Không nên đổi toàn bộ phép ép kiểu thành một `instanceof` rồi dừng:

```java
ClassLoader loader = ClassLoader.getSystemClassLoader();

if (loader instanceof URLClassLoader urls) {
    // Chỉ hoạt động khi loader thực sự là URLClassLoader.
}
```

`instanceof` có thể là biện pháp tương thích cục bộ nếu đây là đoạn chẩn đoán tùy chọn, nhưng nó không cung cấp giải pháp cho yêu cầu chức năng. Nếu việc nạp plugin hoặc resource là bắt buộc, phải có đường xử lý đúng khi loader không phải `URLClassLoader`.

## 5. Classpath và module path không phải một danh sách URL chung

### 5.1. Classpath truyền thống

Với ứng dụng không dùng module, JVM có thể nhận các JAR và directory qua classpath:

```shell
java -cp "app.jar:lib/*" com.example.Main
```

Ví dụ minh họa trên dùng dấu hai chấm thường gặp ở Unix-like OS. Trên Windows, dấu phân tách classpath thường là dấu chấm phẩy. Trong Maven/Gradle, IDE hoặc script triển khai, classpath có thể được sinh tự động.

Ứng dụng không modular thường nằm trong **unnamed module** gắn với class loader của nó. JPMS vẫn tồn tại trong JDK, nhưng ứng dụng có thể tiếp tục dùng classpath.

### 5.2. Module path và named module

Một ứng dụng modular có thể có descriptor:

```java
module com.example.app {
    requires com.example.api;
}
```

Và được khởi chạy bằng:

```shell
java --module-path mods --module com.example.app/com.example.app.Main
```

Các named module được phân giải theo cơ chế module path và module graph. Điều này bổ sung lớp kiểm soát truy cập và dependencies không thể biểu diễn chính xác bằng `URLClassLoader.getURLs()`.

Một số khác biệt:

- `requires` xác định quan hệ đọc module.
- `exports` cho phép module khác truy cập package public theo quy tắc JPMS.
- `opens` liên quan reflective access sâu và quyền truy cập một số resource.
- Module có thể được đặt trong layer khác nhau.
- Class loader có thể định nghĩa nhiều module, nhưng không đồng nghĩa mọi module trong layer đều do cùng loader định nghĩa.

Để kiểm tra module của một class cụ thể, dùng API chính thức:

```java
Class<?> type = com.example.app.Main.class;

Module ownerModule = type.getModule();
ClassLoader definingLoader = type.getClassLoader();

System.out.println("Module: " + ownerModule.getName());
System.out.println("Named module: " + ownerModule.isNamed());
System.out.println("Class loader: " + definingLoader);
```

`getClassLoader()` có thể trả `null` với class do bootstrap loader định nghĩa. Đừng coi null là một lỗi bắt buộc.

### 5.3. Vì sao `java.class.path` không đủ cho mọi ứng dụng?

`System.getProperty("java.class.path")` thường cho biết classpath của ứng dụng theo cấu hình launcher. Tuy nhiên, nó không phải một bản đồ đầy đủ cho:

- Named module nằm trên module path.
- Những module được tạo trong layer động.
- JAR được nạp bởi loader tùy chỉnh.
- Class được tạo từ byte array.
- Một số runtime image hoặc môi trường nhúng riêng.

Nếu chỉ cần log classpath, property này có thể hữu ích. Nếu cần kiểm kê toàn bộ dependency của hệ thống, hãy phối hợp với build tool, dependency graph, module descriptor và thông tin runtime tương ứng.

### 5.4. Đối chiếu module graph khi khởi chạy

Một số tùy chọn launcher hữu ích:

```shell
java --show-module-resolution \
     --module-path mods \
     --module com.example.app/com.example.app.Main
```

Dấu gạch chéo kết dòng ở trên minh họa kiểu Unix shell. Trên Windows PowerShell, hãy dùng một dòng lệnh hoặc cú pháp tiếp dòng phù hợp.

Lệnh giúp quan sát module resolution trong một cấu hình cụ thể. Nó không thay thế kiểm tra runtime loader riêng của plugin container.

## 6. Nạp resource mà không cần URLClassLoader

### 6.1. Dùng `getResourceAsStream` cho resource trong classpath

Một resource như `config/app.properties` có thể được đặt trong `src/main/resources` và đóng gói vào JAR. Sau đó có thể đọc trực tiếp:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ConfigReader {
    public static Properties load() throws IOException {
        ClassLoader loader = ConfigReader.class.getClassLoader();

        try (InputStream input = loader.getResourceAsStream(
                "config/app.properties")) {

            if (input == null) {
                throw new IOException("Resource not found");
            }

            Properties props = new Properties();
            props.load(input);
            return props;
        }
    }
}
```

Không cần biết loader là `URLClassLoader` hay một implementation nội bộ. Nếu class nằm trong bootstrap loader, có thể dùng đường resource khác phù hợp hoặc fallback đã được thiết kế; ví dụ ứng dụng trên thường có non-null application loader.

### 6.2. Khác biệt giữa `Class.getResource` và `ClassLoader.getResource`

`ClassLoader.getResource("x/y.txt")` nhận tên resource theo gốc mà loader tìm kiếm, **không** bắt đầu bằng dấu `/`.

`Class.getResource("file.txt")` thường tìm resource tương đối với package của class. `Class.getResource("/x/y.txt")` tìm theo đường dẫn tuyệt đối từ gốc của phạm vi resource phù hợp.

Ví dụ:

```java
// Resource cùng package với MyService.class:
var local = MyService.class.getResource("template.txt");

// Resource dùng đường dẫn tuyệt đối:
var absolute = MyService.class.getResource("/templates/page.html");

// Resource qua class loader:
var viaLoader = MyService.class
    .getClassLoader()
    .getResource("templates/page.html");
```

Nhầm lẫn ký tự `/` thường gây lỗi “không tìm thấy resource” khi chuyển code giữa các API. Hãy xác định rõ đường dẫn được đóng gói trong JAR và nguồn class/module chứa resource.

### 6.3. Resource của named module có thêm điều kiện truy cập

Trong JPMS, việc resource nằm trong JAR module không bảo đảm mọi loader đều có thể đọc nó từ mọi module. Với resource thuộc package của named module, các quy tắc đóng/mở package có thể tác động đến việc truy cập qua class loader hoặc module API.

Một module có thể đọc resource của chính nó:

```java
import java.io.IOException;
import java.io.InputStream;

static InputStream openOwnResource() throws IOException {
    Module module = MyService.class.getModule();

    InputStream input =
        module.getResourceAsStream("com/example/app/config.properties");

    if (input == null) {
        throw new IOException("Module resource unavailable");
    }

    return input;
}
```

Caller chịu trách nhiệm đóng stream trả về. Với module có mức encapsulation cao, hãy xem xét đặt resource ở vị trí phù hợp, sử dụng API module hoặc cung cấp API công khai để truy xuất thay vì mở rộng package không cần thiết.

Không nên đưa `--add-opens` vào mọi command chỉ để khắc phục việc đặt resource sai hoặc gọi API sai.

### 6.4. Resource trùng tên

Hai JAR có thể chứa cùng path, chẳng hạn `META-INF/services/...` hoặc `config/defaults.properties`. Method `getResource` trả một kết quả theo thứ tự tìm kiếm; thứ tự thực tế có thể phụ thuộc cấu hình loader.

Nếu nghiệp vụ cần phát hiện nhiều resource cùng tên:

```java
import java.io.IOException;
import java.net.URL;
import java.util.Enumeration;

static void printAllResources(
        ClassLoader loader,
        String name) throws IOException {

    Enumeration<URL> urls = loader.getResources(name);

    while (urls.hasMoreElements()) {
        URL url = urls.nextElement();
        System.out.println(url);
    }
}
```

`getResources` chỉ tìm trong phạm vi tìm kiếm của loader và những giới hạn liên quan; nó không phải một API kiểm kê toàn bộ module/URL của mọi loader trong tiến trình.

## 7. Chọn loader đúng cho dynamic class loading

### 7.1. Lấy system loader

`ClassLoader.getSystemClassLoader()` là API hợp lệ khi bạn muốn tham chiếu loader được cấu hình làm system loader. Không có lý do phải ép nó sang kiểu cụ thể:

```java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();

Class<?> type = Class.forName(
    "com.example.extension.ExampleService",
    true,
    systemLoader
);
```

Ví dụ chỉ hoạt động nếu class đó thực sự visible từ system loader. Class trong plugin loader con không nhất thiết visible ngược từ parent/system loader.

### 7.2. Lấy loader đã định nghĩa một class

Nếu code cần nạp resource hoặc class liên quan đến một API đã có, thường dùng loader của class đó:

```java
ClassLoader apiLoader = PublicPluginApi.class.getClassLoader();
```

Đây là lựa chọn tốt khi bạn muốn class identity của một API dùng chung nhất quán. Nhưng nếu API nằm trong bootstrap loader, kết quả có thể là `null`. Nhu cầu plugin có thể cần một parent cụ thể; hãy công bố rõ thay vì tùy tiện chuyển sang system loader trong mọi trường hợp.

### 7.3. Thread Context ClassLoader (TCCL)

Framework và SPI thường cần tìm implementation do ứng dụng cung cấp dù code framework được nạp bởi một loader ở tầng cha. `Thread.currentThread().getContextClassLoader()` là một cơ chế hữu ích cho tình huống này.

```java
ClassLoader contextLoader =
    Thread.currentThread().getContextClassLoader();

System.out.println("Context loader: " + contextLoader);
```

Đừng mặc định TCCL là system loader hoặc loader định nghĩa class hiện tại. Application server, executor, plugin container hoặc framework có thể thiết lập nó khác nhau. Context loader có thể là `null` trong một số cấu hình.

Nếu tạm đổi TCCL trong scope một tác vụ, phải khôi phục giá trị cũ:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    runPluginTask();
} finally {
    thread.setContextClassLoader(previous);
}
```

Không để thread trong pool giữ TCCL của plugin sau khi hoàn tất request; điều đó vừa tạo nguy cơ nạp sai implementation, vừa giữ tham chiếu đến plugin loader làm class loader không được thu hồi.

## 8. Nạp JAR plugin động bằng URLClassLoader do ứng dụng tạo

### 8.1. Đây là trường hợp URLClassLoader vẫn phù hợp

Nếu ứng dụng cần tải một JAR bổ sung trong lúc chạy, có thể tạo `URLClassLoader` mới:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

Path pluginJar = Path.of("plugins", "demo-plugin.jar");
URL[] pluginUrls = { pluginJar.toUri().toURL() };

URLClassLoader pluginLoader = new URLClassLoader(
    pluginUrls,
    Plugin.class.getClassLoader()
);
```

Ở đây `Plugin` đại diện cho interface API chung giữa host và plugin. Parent loader được chọn để plugin nhìn thấy API chung. Nếu parent không có API đó, hoặc plugin mang thêm một bản sao cùng tên của API, có thể dẫn đến xung đột kiểu.

Đừng lấy system loader rồi sửa danh sách URL bên trong nó bằng reflection. Loader mới tách rõ phạm vi các dependency của plugin và giúp triển khai vòng đời riêng.

### 8.2. Một ví dụ plugin hoàn chỉnh ở mức thiết kế

Host định nghĩa API:

```java
package com.example.api;

public interface Plugin {
    String execute(String input);
}
```

JAR plugin cung cấp implementation:

```java
package com.example.plugin;

import com.example.api.Plugin;

public final class UppercasePlugin implements Plugin {
    @Override
    public String execute(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

Host nạp plugin từ JAR theo tên class:

```java
import com.example.api.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PluginRunner {
    public static void main(String[] args) throws Exception {
        Path jar = Path.of("plugins", "uppercase-plugin.jar");
        URL[] urls = { jar.toUri().toURL() };

        try (URLClassLoader loader = new URLClassLoader(
                urls,
                Plugin.class.getClassLoader())) {

            Class<?> impl = Class.forName(
                "com.example.plugin.UppercasePlugin",
                true,
                loader
            );

            if (!Plugin.class.isAssignableFrom(impl)) {
                throw new IllegalArgumentException(
                    "Class does not implement host Plugin API"
                );
            }

            Plugin plugin = (Plugin) impl
                .getDeclaredConstructor()
                .newInstance();

            System.out.println(plugin.execute("hello"));
        }
    }
}
```

Lưu ý:

1. Host và plugin phải thống nhất một bản API `Plugin` được định nghĩa bởi loader tương thích.
2. Code trên minh họa plugin trên classpath; không tự động giải quyết các yêu cầu named module của plugin modular.
3. Plugin được chọn bằng tên class. Nếu cần discovery, có thể dùng `ServiceLoader`.
4. Đóng `URLClassLoader` sau khi hoàn tất sử dụng và sau khi các tài nguyên mà plugin tạo ra được đóng.
5. Loader close giải phóng một số tài nguyên mà loader sở hữu, nhưng không ép mọi class đã nạp được unload ngay. Nếu host còn giữ class, instance, thread, listener, static reference hoặc context loader, class loader có thể vẫn còn reachable.

### 8.3. Vòng đời và phiên bản plugin

Đối với hệ thống plugin thực tế, nên định nghĩa:

- `start()`, `stop()` hoặc API lifecycle tương đương.
- Ai tạo và đóng plugin loader.
- Những thread hoặc scheduled task mà plugin được phép tạo.
- Cách đăng ký/hủy listener, callback và registry entry.
- Version của plugin API và dependency cần thiết.
- Hành vi khi plugin bị lỗi khi khởi tạo hoặc dừng.
- Khả năng reload và cơ chế loại bỏ reference cũ.

Không nên chỉ gọi `URLClassLoader.close()` rồi tuyên bố plugin đã được unload. JVM có thể giữ class và loader lâu hơn nếu còn reference; các resource bên ngoài phải được dọn theo lifecycle đã thiết kế.

### 8.4. Cẩn trọng với parent-first và dependency trùng

`URLClassLoader` theo mô hình mặc định thường ủy quyền tìm class cho parent trước. Khi host và plugin dùng các phiên bản khác nhau của cùng thư viện, plugin có thể nhận class từ parent thay vì JAR của nó.

Cách giải quyết không phải đơn giản là tự viết child-first loader cho mọi package. Hãy phân vùng namespace:

- API chung phải có identity thống nhất.
- Thư viện nội bộ của plugin có thể cần cách ly.
- Không được cho plugin tự thay thế các class nền tảng của Java.
- Dependency dùng chung cần có chính sách version hoặc shading thích hợp.
- Nếu dùng custom child-first policy, kiểm tra class identity và bảo mật thật kỹ.

## 9. Khi plugin là named module: xem xét ModuleLayer

Một ứng dụng JPMS có thể cần nạp các module không có sẵn trong boot layer. `ModuleLayer` cung cấp cơ chế tạo layer module mới với configuration và class loader theo thiết kế.

Khái niệm:

```text
Boot module layer
  ├─ com.example.api
  └─ com.example.host
       |
       +-- Child module layer
             └─ com.example.plugin
```

Host có thể tìm module plugin bằng `ModuleFinder` và tạo configuration/layer mới bằng API module.

Ví dụ định hướng:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

Path plugins = Path.of("plugins");
ModuleFinder finder = ModuleFinder.of(plugins);

ModuleLayer parentLayer = ModuleLayer.boot();

Configuration configuration =
    parentLayer.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );

ModuleLayer pluginLayer =
    parentLayer.defineModulesWithOneLoader(
        configuration,
        ClassLoader.getSystemClassLoader()
    );
```

Mã giả định có module `com.example.plugin` trên đường dẫn plugin và module graph phân giải được. `defineModulesWithOneLoader` là một chiến lược; API JPMS có những cách khác để ánh xạ module sang loader. Không nên coi mọi plugin modular đều có thể dùng lại một URLClassLoader như plugin classpath.

Sau khi tạo layer, có thể lấy loader nạp module cụ thể:

```java
ClassLoader moduleLoader =
    pluginLayer.findLoader("com.example.plugin");
```

Nếu plugin cung cấp service, nên xem xét `ServiceLoader.load(layer, serviceType)` và khai báo `uses`/`provides ... with` đúng trong module descriptor. Các module cần có quan hệ readability và visibility thích hợp.

**Module layer không phải sandbox bảo mật.** Nó tổ chức module graph và loader, không giới hạn mã plugin ác ý truy cập filesystem hay network một cách đáng tin cậy. Khi chạy mã không tin cậy, cần isolation cấp tiến trình/container hoặc cơ chế tương ứng.

## 10. ServiceLoader: discovery thay cho tự quét URL

### 10.1. Vì sao API SPI hữu ích?

Nhiều ứng dụng cũ liệt kê JAR bằng `URLClassLoader.getURLs()` rồi tìm các class kết thúc bằng một hậu tố nào đó. Cách này phụ thuộc cấu trúc JAR, classpath và implementation loader.

`ServiceLoader` cho phép API định nghĩa service interface và plugin/provider khai báo implementation. Code tiêu thụ không cần biết chính xác file JAR hoặc URL của từng provider.

Ví dụ API:

```java
package com.example.api;

public interface ReportFormatter {
    String format(String report);
}
```

Với provider trên classpath, JAR chứa file:

```text
META-INF/services/com.example.api.ReportFormatter
```

Nội dung file là tên class implementation, mỗi dòng một tên:

```text
com.example.plugins.JsonFormatter
```

Ứng dụng có thể tìm provider:

```java
import com.example.api.ReportFormatter;
import java.util.ServiceLoader;

ServiceLoader<ReportFormatter> providers =
    ServiceLoader.load(ReportFormatter.class);

for (ReportFormatter formatter : providers) {
    System.out.println(formatter.format("sample"));
}
```

`ServiceLoader.load(serviceType)` thường dùng TCCL. Nếu loader cụ thể có ý nghĩa quan trọng, dùng overload nhận `ClassLoader`:

```java
ServiceLoader<ReportFormatter> providers =
    ServiceLoader.load(ReportFormatter.class, pluginLoader);
```

Với named module, provider có thể dùng directive trong `module-info.java`:

```java
module com.example.plugin {
    requires com.example.api;

    provides com.example.api.ReportFormatter
        with com.example.plugin.JsonFormatter;
}
```

Consumer modular cũng cần khai báo `uses` phù hợp theo hợp đồng JPMS. Với dynamic layer, sử dụng overload `ServiceLoader.load(layer, serviceType)`.

### 10.2. Giới hạn của ServiceLoader

`ServiceLoader` không phải framework quản lý vòng đời hoặc cơ chế versioning đầy đủ. Provider có thể ném exception khi khởi tạo; nhiều provider có thể cùng được phát hiện; kết quả có thể phụ thuộc loader và layer.

Cần kiểm tra:

- Provider nào được phép và theo thứ tự nào.
- Cách lựa chọn provider nếu có nhiều implementation.
- Cách đóng provider có resource.
- Cách reload khi plugin thay đổi.
- API service được định nghĩa bởi loader nào.
- Khả năng tương thích của provider khi interface thay đổi.

## 11. Chẩn đoán loader, classpath và module tại runtime

### 11.1. In thông tin class đang dùng

Khi điều tra lỗi, hãy in class, loader và module thay vì ép loader sang URLClassLoader:

```java
public final class LoaderReport {
    public static void report(Class<?> type) {
        Module module = type.getModule();
        ClassLoader loader = type.getClassLoader();

        System.out.println("Class: " + type.getName());
        System.out.println("Module: " + module.getName());
        System.out.println("Named: " + module.isNamed());
        System.out.println("Defining loader: " + loader);
        System.out.println("System loader: "
            + ClassLoader.getSystemClassLoader());
        System.out.println("Platform loader: "
            + ClassLoader.getPlatformClassLoader());
        System.out.println("Context loader: "
            + Thread.currentThread().getContextClassLoader());
    }

    public static void main(String[] args) {
        report(LoaderReport.class);
        report(String.class);
    }
}
```

`String.class.getClassLoader()` thường trả `null` vì class do bootstrap loader định nghĩa. Nếu in ra tên implementation nội bộ của loader, chỉ dùng nó để chẩn đoán; không thêm dependency compile vào package đó.

### 11.2. Kiểm tra CodeSource khi có

`ProtectionDomain` và `CodeSource` đôi khi có thể cho biết một class được nạp từ JAR hoặc location nào:

```java
import java.net.URL;
import java.security.CodeSource;
import java.security.ProtectionDomain;

static URL codeSourceOf(Class<?> type) {
    ProtectionDomain domain = type.getProtectionDomain();

    if (domain == null) {
        return null;
    }

    CodeSource source = domain.getCodeSource();
    return source == null ? null : source.getLocation();
}
```

Kết quả có thể là `null`, đặc biệt với một số class nền tảng, class tạo động hoặc cấu hình loader tùy chỉnh. `CodeSource` hữu ích cho diagnostic nhưng không được bảo đảm như API liệt kê classpath.

### 11.3. Dùng log JVM để biết class được nạp

Trên JDK hiện đại, unified logging hỗ trợ class loading diagnostics:

```shell
java -Xlog:class+load=info -jar app.jar
```

Log có thể cho biết tên class và nguồn nạp. Hãy bật trong môi trường phù hợp và kiểm soát dung lượng log. Cú pháp/chi tiết tag có thể khác theo phiên bản JVM; xác nhận trên JDK đích.

`jdeps` có thể dùng để kiểm kê static dependencies và vấn đề API nội bộ:

```shell
jdeps --jdk-internals app.jar
jdeps --print-module-deps app.jar
```

`jdeps` không thấy mọi dependency nạp qua reflection hoặc plugin runtime. Cần phối hợp unit/integration test và log thực tế.

### 11.4. In module hiện diện trong boot layer

```java
ModuleLayer.boot().modules().stream()
    .map(Module::getName)
    .sorted()
    .forEach(System.out::println);
```

Danh sách này không bao gồm mọi module ở các layer động khác. Nếu ứng dụng tự tạo layer, giữ metadata về layer đó để chẩn đoán.

## 12. Lỗi cùng tên class khác loader

### 12.1. Class identity không chỉ là tên

Giả sử host và plugin đều đóng gói `com.example.api.Plugin`, nhưng mỗi bản class được định nghĩa bởi loader khác nhau. Khi đó:

```text
com.example.api.Plugin defined by HostLoader
com.example.api.Plugin defined by PluginLoader
```

Hai kiểu này khác nhau dù cùng tên nhị phân. Phép cast có thể thất bại với `ClassCastException`, hoặc JVM có thể báo loading constraint violation tùy ngữ cảnh.

Không giải quyết bằng cách đổi tên hiển thị trong log. Hãy bảo đảm API dùng chung được nạp từ một loader có thể dùng chung; tránh đóng gói bản sao API vào JAR plugin khi không có lý do thiết kế hợp lệ.

### 12.2. Các lỗi liên quan có triệu chứng tương tự

| Lỗi | Nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| `ClassCastException` | Cast sai implementation loader hoặc hai class cùng tên khác defining loader | In `getClassLoader()` của cả hai kiểu |
| `ClassNotFoundException` | Loader được yêu cầu không tìm thấy class theo tên | Kiểm tra loader, classpath/module path và package |
| `NoClassDefFoundError` | Class đã được tham chiếu nhưng không thể định nghĩa/liên kết/khởi tạo đúng | Đọc cause, kiểm tra dependency và initializer |
| `IllegalAccessError` | Truy cập không hợp lệ ở runtime | Kiểm tra module exports, binary changes và class access |
| `InaccessibleObjectException` | Reflection sâu bị từ chối | Kiểm tra opens, dependency và API nội bộ |
| `ServiceConfigurationError` | Provider SPI thiếu, sai kiểu, không khởi tạo được hoặc khai báo sai | Kiểm tra `META-INF/services`, `provides` và loader/layer |
| `LinkageError` | Xung đột định nghĩa hoặc liên kết class | Kiểm tra class identity, version và loader graph |

Đừng chỉ nhìn exception đầu tiên trong log. Với lỗi khởi tạo lớp, cause chain thường chứa nguyên nhân gốc.

## 13. Vấn đề bảo mật và encapsulation sau JDK 8

### 13.1. JPMS không phải phép thay ClassLoader thành URLClassLoader

JPMS đưa ra mô hình module graph và package encapsulation. Việc mở package bằng `--add-opens` có thể cho phép một số reflective access, nhưng không biến system loader thành một instance của `URLClassLoader`.

Do đó, sửa lỗi `ClassCastException` bằng cách thêm `--add-opens java.base/jdk.internal.loader=ALL-UNNAMED` không giải quyết đúng nguyên nhân. Cơ chế inheritance của object không thay đổi theo JVM flags.

### 13.2. Tránh phụ thuộc vào `sun.*` và `jdk.internal.*`

Các package nội bộ có thể thay đổi hoặc bị hạn chế mà không bảo đảm source/binary compatibility như API công khai. Đối với migration:

- Dùng `ClassLoader`, `URLClassLoader`, `Module`, `ModuleLayer` và `ServiceLoader`.
- Thay `sun.misc.Launcher` hoặc implemention tương tự bằng API chính thức theo mục đích sử dụng.
- Không đặt tên class nội bộ trong cấu hình hoặc code chỉ để gọi method không công bố.
- Đọc release note của thư viện bên thứ ba nếu nó thao tác sâu vào classloading.

### 13.3. Plugin không tin cậy cần isolation riêng

Chỉ vì có loader riêng không có nghĩa code plugin bị sandbox. `ClassLoader` phục vụ nạp và cách ly namespace/class identity; nó không ngăn plugin gọi các API hệ điều hành mà process có quyền sử dụng.

Đối với plugin không tin cậy, cân nhắc chạy trong process hoặc container riêng, giới hạn filesystem, network và privilege theo threat model của hệ thống. Không dựa vào Security Manager như một giải pháp chung cho các JDK mới, vì cơ chế này đã bị vô hiệu hóa trong lộ trình hiện đại.

## 14. Migration từng bước từ JDK 8

### Bước 1: Kiểm kê các assumption trong mã nguồn

Tìm các pattern:

- Ép `ClassLoader.getSystemClassLoader()` sang `URLClassLoader`.
- Ép `getParent()` hoặc TCCL sang `URLClassLoader`.
- Phản chiếu vào `addURL` của loader hệ thống.
- Dùng `sun.misc.Launcher`, `sun.misc.URLClassPath` hoặc `jdk.internal.loader`.
- Quét `getURLs()` để tìm plugin, resource hoặc classpath.
- Dựa vào extension/endorsed directories.
- Tự thay thế logic module access bằng classpath URL.
- Giả định mọi class cùng tên có thể cast qua các loader.

Ví dụ truy vấn khởi đầu khi dùng ripgrep:

```shell
rg -n "URLClassLoader|getSystemClassLoader|getContextClassLoader" src
rg -n "getURLs\\(|addURL\\(|java\\.ext\\.dirs|endorsed" .
rg -n "sun\\.misc\\.Launcher|jdk\\.internal\\.loader" .
rg -n "Class\\.forName|ServiceLoader|ModuleLayer" src
```

Đây là truy vấn văn bản sơ bộ. Cần xem xét cả bytecode/dependency nếu code lỗi nằm trong thư viện ngoài dự án.

### Bước 2: Ghi rõ mục đích của từng vị trí

Tạo một bảng inventory:

| Vị trí | Mục đích | Code legacy | Hướng thay thế |
|---|---|---|---|
| ResourceUtil | Tìm config trong JAR | Cast system loader rồi duyệt URL | `getResourceAsStream` |
| StartupReporter | In classpath | `((URLClassLoader) loader).getURLs()` | `java.class.path` và module diagnostics |
| PluginManager | Thêm JAR lúc chạy | Reflective `addURL` | Custom `URLClassLoader` hoặc module layer |
| ProviderDiscovery | Tìm implementation | Tự scan JAR | `ServiceLoader` |
| ContainerAdapter | Lấy class từ framework | Cố lấy system loader | TCCL hoặc loader do framework cung cấp |

Đừng biến một bản sửa hợp lệ cho ResourceUtil thành quy tắc thay thế toàn cục. Mỗi mục đích cần API riêng.

### Bước 3: Tách phần abstraction khỏi implementation

Thay đổi kiểu biến nhận về từ `URLClassLoader` sang `ClassLoader` khi chỉ cần các method chung:

```java
// Trước migration:
URLClassLoader loader =
    (URLClassLoader) ClassLoader.getSystemClassLoader();

// Sau migration:
ClassLoader loader = ClassLoader.getSystemClassLoader();
```

Đây mới là bước đầu. Nếu code còn gọi `loader.getURLs()`, phải chuyển sang giải pháp theo mục đích của phương thức đó. Không đơn giản xóa câu lệnh `getURLs()` mà bỏ mất hành vi quan trọng.

### Bước 4: Cập nhật thư viện và framework

Một dependency có thể chứa phép cast mà mã nguồn ứng dụng không tìm thấy. Kiểm tra:

- Container/plugin framework cũ.
- Template hoặc script engine nạp class động.
- Serialization, ORM, proxy và bytecode framework.
- Test runner, mocking, classpath scanner và compiler plugin.
- Java agent hoặc bộ instrument code.
- SDK loader, JDBC driver và provider discovery.

Ưu tiên nâng cấp phiên bản chính thức hỗ trợ JDK đích. Fork hoặc patch dependency chỉ khi có kế hoạch duy trì rõ ràng. Không dùng blanket `--add-opens` để thay cho việc cập nhật library.

### Bước 5: Kiểm tra classpath và module path của môi trường đích

Phân biệt:

- JAR nào ở classpath?
- JAR nào là named module?
- Có automatic module nào trên module path?
- Có module layer động không?
- Loader nào định nghĩa API chung giữa host và plugin?
- TCCL được đặt thế nào trong web container hoặc thread pool?
- Có resource nào bị ẩn vì module encapsulation không?

Khi ứng dụng đang chuyển dần sang JPMS, không nhất thiết modularize mọi dependency trong một bước. Có thể tạm chạy ứng dụng trên classpath của JDK hiện đại, xử lý classloader assumptions, sau đó chuyển từng module nếu kiến trúc yêu cầu.

### Bước 6: Xác minh trong CI và runtime thật

Chạy cùng bộ test trên JDK 8 (nếu vẫn là target được hỗ trợ) và JDK mới. Đặc biệt cần:

- Unit test cho resource lookup.
- Integration test nạp plugin từ JAR ngoài.
- Test tạo provider qua `ServiceLoader`.
- Test tên class bị trùng giữa plugin và host.
- Test resource trùng tên trong hai JAR.
- Test module exports/opens và reflective access.
- Test async/thread pool với TCCL.
- Test plugin shutdown, reload và loader close.
- Startup smoke test với đúng launcher arguments.

Nên chạy trên runtime thật của vendor/OS dùng trong production, thay vì chỉ dựa vào IDE. IDE có thể thay đổi classpath, working directory hoặc class loader context.

## 15. Bộ thử nghiệm nhỏ để tái hiện và sửa vấn đề

### 15.1. In kiểu system loader mà không ép kiểu

```java
public final class SystemLoaderProbe {
    public static void main(String[] args) {
        ClassLoader loader = ClassLoader.getSystemClassLoader();

        System.out.println(loader.getClass().getName());
        System.out.println(
            "URLClassLoader: "
                + (loader instanceof java.net.URLClassLoader)
        );
        System.out.println("Java: " + System.getProperty("java.version"));
    }
}
```

Đoạn code này chạy được trên nhiều phiên bản Java (không cần dùng preview feature). Kết quả có thể khác theo vendor và cấu hình runtime, nhưng nó đủ để chứng minh vì sao cast phụ thuộc implementation là không an toàn.

### 15.2. Kiểm thử resource bằng ClassLoader API

```java
import java.io.InputStream;

public final class ResourceProbe {
    public static void main(String[] args) throws Exception {
        ClassLoader loader = ResourceProbe.class.getClassLoader();

        try (InputStream input =
                 loader.getResourceAsStream("sample.txt")) {

            if (input == null) {
                throw new IllegalStateException(
                    "sample.txt is not visible"
                );
            }

            System.out.println("Resource loaded");
        }
    }
}
```

Đặt `sample.txt` trên classpath hoặc trong vị trí resource hợp lệ của module. Test sẽ thất bại rõ ràng nếu resource không visible mà không cần biết loader là `URLClassLoader`.

### 15.3. Kiểm thử plugin riêng

Xây một JAR plugin nhỏ, tạo `URLClassLoader` riêng, nạp implementation và gọi interface chung. Kiểm tra cả trường hợp:

1. Plugin JAR có mặt, đúng tên class và đúng API.
2. Plugin JAR không tồn tại.
3. Plugin class thiếu public constructor.
4. Plugin class không triển khai API chung.
5. Host và plugin đóng gói trùng API gây xung đột class identity.
6. Plugin tạo thread hoặc listener chưa được shutdown.
7. Plugin có resource riêng trong JAR.

Kết quả của những test này cho thấy cách nạp plugin đã được làm chủ thay vì dựa vào chi tiết loader hệ thống.

### 15.4. Ma trận phiên bản

| Môi trường | Mục tiêu kiểm tra |
|---|---|
| JDK 8 | Baseline hành vi cũ nếu sản phẩm vẫn hỗ trợ |
| JDK 11 | Phát hiện thay đổi do JPMS và built-in loader |
| JDK 17 | Phát hiện lỗi strong encapsulation và dependency cũ |
| JDK 21 | Xác nhận môi trường LTS mới và các API runtime liên quan |
| JDK 25 hoặc JDK mục tiêu khác | Xác nhận hỗ trợ thực tế của dependency, agent và plugin |

Không bắt buộc mọi dự án phải hỗ trợ đủ các JDK trên. Hãy đặt matrix theo cam kết của sản phẩm, nhưng nếu lỗi xuất hiện trong một bước nâng cấp lớn, việc chạy bản trung gian có thể giúp xác định giai đoạn xuất hiện.

## 16. Hướng xử lý lỗi thường gặp

### Lỗi 1: `AppClassLoader cannot be cast to URLClassLoader`

**Dấu hiệu:** startup thất bại ngay khi code hoặc library ép system loader sang `URLClassLoader`.

**Nguyên nhân:** system loader hiện tại không kế thừa `URLClassLoader`.

**Xử lý:** xác định mục đích cast, đổi sang API resource/diagnostic chính thức hoặc tự tạo loader cho plugin. Không dùng reflection vào implementation nội bộ.

### Lỗi 2: Không tìm thấy resource sau khi đưa JAR lên module path

**Dấu hiệu:** `getResourceAsStream` trả null dù file có trong JAR.

**Nguyên nhân khả dĩ:** path sai, JAR không nằm trong phạm vi loader đang dùng, hoặc module encapsulation ảnh hưởng quyền truy cập.

**Xử lý:** xác minh path tương đối/tuyệt đối, module owner, nơi resource được đóng gói và API resource phù hợp. Dùng `Class.getResourceAsStream` hoặc `Module.getResourceAsStream` khi phù hợp.

### Lỗi 3: `ClassNotFoundException` dù JAR plugin tồn tại

**Dấu hiệu:** system loader không tìm thấy class được tải qua plugin loader.

**Nguyên nhân khả dĩ:** class chỉ visible từ loader con; parent không tự tìm trong child.

**Xử lý:** sử dụng đúng plugin loader khi gọi `Class.forName` hoặc thiết kế provider discovery. Không cố sửa classpath toàn JVM.

### Lỗi 4: `ClassCastException` giữa hai class cùng tên

**Dấu hiệu:** thông báo hai bên đều có tên class như nhau nhưng vẫn cast thất bại.

**Nguyên nhân:** class identity khác vì defining loader khác nhau.

**Xử lý:** in loader của từng class, tránh đóng gói trùng API, đặt shared interface ở parent phù hợp.

### Lỗi 5: `InaccessibleObjectException` trong thư viện cũ

**Dấu hiệu:** framework cố đọc private field/method trong module nền tảng.

**Nguyên nhân:** JPMS strong encapsulation từ các JDK mới.

**Xử lý:** nâng cấp thư viện, chuyển sang API công khai hoặc cấu hình quyền opens tối thiểu nếu thực sự cần và chấp nhận nợ kỹ thuật. Không liên hệ nhầm lỗi này với kiểu runtime của system loader.

### Lỗi 6: SPI provider không được phát hiện

**Dấu hiệu:** `ServiceLoader` không trả provider mong muốn hoặc ném `ServiceConfigurationError`.

**Nguyên nhân:** sai loader/layer, sai file `META-INF/services`, provider không visible, module descriptor thiếu `provides`/`uses` hoặc provider không hợp lệ.

**Xử lý:** kiểm tra SPI contract, provider metadata, service type identity và TCCL/module layer.

### Lỗi 7: Reload plugin làm tăng bộ nhớ

**Dấu hiệu:** sau nhiều lượt reload, số class và memory tăng, dù đã đóng `URLClassLoader`.

**Nguyên nhân khả dĩ:** còn reference đến loader, `Class`, instance, thread, TCCL, listener hoặc cache.

**Xử lý:** tổ chức plugin lifecycle, stop task và hủy registry, khôi phục TCCL; dùng profiling/class histogram để xác định reference còn giữ.

## 17. Checklist migration

### Mã nguồn và dependency

- [ ] Không còn ép system loader hoặc platform loader mặc định sang `URLClassLoader`.
- [ ] Đã tìm code phản chiếu vào `addURL` hoặc package loader nội bộ.
- [ ] Đã xác định nhu cầu thật: tìm resource, log classpath, tìm provider hay nạp JAR động.
- [ ] Đã cập nhật framework/agent/plugin chứa assumption về loader của JDK 8.
- [ ] Không dựa vào extension/endorsed directories cũ.

### Resource và module

- [ ] Resource lookup dùng API chính thức phù hợp với classpath/module.
- [ ] Đã kiểm tra khác biệt path của `Class.getResource` và `ClassLoader.getResource`.
- [ ] Đã xác định named module, unnamed module và module layer liên quan.
- [ ] Module `exports`/`opens` phản ánh đúng yêu cầu API và reflection.
- [ ] Không coi `java.class.path` là danh sách đầy đủ của module path và custom loader.

### Plugin và SPI

- [ ] Plugin loader do ứng dụng tạo và được đóng theo lifecycle rõ ràng.
- [ ] API chung giữa host/plugin không bị định nghĩa hai lần trong loader khác nhau.
- [ ] `ServiceLoader` dùng đúng loader hoặc layer.
- [ ] TCCL được thiết lập/khôi phục đúng khi framework yêu cầu.
- [ ] Không giữ tham chiếu plugin loader qua thread, listener hoặc cache sau khi unload.

### Xác minh

- [ ] Test startup trên JDK đích đã chạy.
- [ ] Test resource lookup và classpath/module path đã chạy.
- [ ] Test dynamic plugin loading và SPI đã chạy.
- [ ] Test lỗi class identity, duplicate dependency và missing provider đã chạy.
- [ ] Dependency và agent đã được xác nhận hỗ trợ JDK đích.
- [ ] Kế hoạch rollback và thông tin chẩn đoán loader/module đã được chuẩn bị.

## Kết luận

Giả định `ClassLoader.getSystemClassLoader()` luôn là `URLClassLoader` là một ví dụ điển hình của dependency vào implementation JDK 8 thay vì API công khai. JPMS và việc tổ chức lại built-in class loaders từ JDK 9 làm giả định đó không còn đúng; cast có thể thất bại ngay cả khi classpath và JAR đều hợp lệ.

Migration đúng không phải là cố biến system loader thành `URLClassLoader`, mà là **tách mục đích khỏi implementation**: dùng resource API để đọc file, dùng diagnostics phù hợp để quan sát classpath/module, dùng `ServiceLoader` để tìm provider, và tạo `URLClassLoader` hoặc `ModuleLayer` riêng khi ứng dụng thực sự cần nạp plugin động. Khi kết hợp với kiểm tra class identity, TCCL, module visibility và plugin lifecycle, ứng dụng Java có thể chạy ổn định trên JDK hiện đại mà không phụ thuộc vào những chi tiết nạp lớp cũ.


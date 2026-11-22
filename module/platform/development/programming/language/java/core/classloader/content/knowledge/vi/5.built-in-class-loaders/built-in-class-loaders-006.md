# ClassLoader.getPlatformClassLoader và getSystemClassLoader

## 1. Hai API dùng để làm gì?

Khi tìm hiểu cách JVM nạp lớp, ta thường gặp hai phương thức `static` của `java.lang.ClassLoader`:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();
~~~

Cả hai **trả về đối tượng ClassLoader**, nhưng chúng giữ vai trò khác nhau:

- `getPlatformClassLoader()` trả về **platform class loader**, loader tích hợp dùng cho các lớp của nền tảng Java và JDK. Phương thức xuất hiện từ Java 9.
- `getSystemClassLoader()` trả về **system class loader** (thường gọi là **application class loader**), loader mặc định thường được dùng để khởi chạy ứng dụng và tải lớp nằm trên application classpath hoặc application module path.

Không có tham số: các phương thức này không nhận tên class, không nạp trực tiếp một class cụ thể và không tự tạo loader mới mỗi lần được gọi. Chúng cung cấp **tham chiếu tới loader đã được JVM thiết lập**. Sau khi có loader, ta có thể gọi `loadClass(...)`, `getResource(...)` hoặc dùng loader làm parent cho loader tùy biến.

Trong JVM thông thường từ Java 9 trở lên, sơ đồ ủy quyền là:

~~~text
                       ┌───────────────────────────┐
                       │ Bootstrap loader          │
                       │ Lõi JVM / java.base       │
                       │ Java biểu diễn bằng null  │
                       └─────────────▲─────────────┘
                                     │ parent
                       ┌─────────────┴─────────────┐
                       │ Platform class loader     │
                       │ API Java SE / JDK modules │
                       └─────────────▲─────────────┘
                                     │ parent
                       ┌─────────────┴─────────────┐
                       │ System / Application      │
                       │ class loader              │
                       │ Mã ứng dụng               │
                       └─────────────▲─────────────┘
                                     │ parent
                       ┌─────────────┴─────────────┐
                       │ ClassLoader do ứng dụng   │
                       │ tạo (nếu có)              │
                       └───────────────────────────┘
~~~

Mũi tên chỉ **quan hệ parent/delegation**, không có nghĩa mọi class được nạp vào bộ nhớ theo thứ tự từ trên xuống dưới. Thông thường loader con kiểm tra đã nạp chưa, thử ủy quyền cho parent, rồi mới tìm bytecode của mình nếu parent không tìm thấy.

Sơ đồ trên mô tả **loader tích hợp mặc định**. JVM và công cụ chạy ứng dụng có thể sử dụng loader riêng; tùy chọn `java.system.class.loader` cũng có thể thay thế đối tượng system loader. Đối với named modules, khả năng nhìn thấy class có thêm quy tắc module và một số đường ủy quyền đặc biệt; sơ đồ parent đơn giản không đủ để mô tả mọi trường hợp.

## 2. Phân biệt bootstrap, platform và system

| Tiêu chí | Bootstrap loader | Platform loader | System loader |
|---|---|---|---|
| Cách lấy | Không có API trả về một đối tượng `ClassLoader` thông thường; thường biểu diễn bằng `null` | `ClassLoader.getPlatformClassLoader()` | `ClassLoader.getSystemClassLoader()` |
| Vai trò chính | Nạp các lớp nền tảng cốt lõi, như `java.lang.String` trong JDK 17 | Nạp các lớp nền tảng và module JDK được gán cho platform loader | Thường nạp lớp ứng dụng từ classpath/application module path |
| Quan hệ parent mặc định | Không có parent | Bootstrap | Platform |
| Kết quả `Class.getClassLoader()` | `null` cho lớp do bootstrap định nghĩa | Đối tượng platform loader cho lớp do nó định nghĩa | Đối tượng system loader cho lớp do nó định nghĩa |
| Có phải một loader mới cho mỗi lần gọi? | Không áp dụng | Không | Không |
| Có thể làm parent cho loader tùy biến? | Có thể truyền `null` để chỉ bootstrap (với giới hạn tầm nhìn lớp) | Có, phù hợp nếu chỉ cần API nền tảng | Có, phù hợp nếu plugin cần nhìn thấy API của ứng dụng |

**Điểm rất quan trọng:** `ClassLoader` mà ta gọi `loadClass` **không nhất thiết** là ClassLoader *đã định nghĩa* class được trả về.

Ví dụ, system loader có thể thực hiện:

~~~java
Class<?> type = ClassLoader.getSystemClassLoader()
        .loadClass("java.lang.String");
~~~

Dù yêu cầu xuất phát từ system loader, `String.class.getClassLoader() == null` vẫn là `true` trên JVM Java 17 tiêu chuẩn: bootstrap loader đã định nghĩa `String` và system loader chỉ chuyển yêu cầu lên parent theo cơ chế delegation.

Tương tự, class do platform loader định nghĩa có thể được hệ thống tìm thấy thông qua system loader. Do đó đừng dùng câu “class được yêu cầu qua loader X” thay cho “class do loader X định nghĩa”.

## 3. `getPlatformClassLoader()`

### 3.1. Chức năng và giá trị trả về

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
~~~

Phương thức `public static` này có từ **Java 9** và trả về platform class loader. Theo API Java 17, các **platform classes** có thể được nhìn thấy qua loader này. Chúng bao gồm API Java SE, class triển khai của chúng và những class runtime riêng của JDK do platform loader hoặc tổ tiên của nó quản lý.

Thông thường trên JDK 17:

- `platform != null`.
- `platform.getParent() == null`, vì parent là bootstrap loader được biểu diễn bằng `null`.
- `platform != ClassLoader.getSystemClassLoader()`.

Lưu ý **không phải** mọi lớp thuộc các gói `java.*` đều do cùng một loader cụ thể định nghĩa; module nào do loader nào quản lý là một phần của cơ chế runtime và cấu hình module. Không nên tự suy ra “cứ tên package bắt đầu bằng `java.` thì `getClassLoader() == null`”.

### 3.2. Vì sao dùng platform loader làm parent?

Giả sử muốn nạp JAR mở rộng nhưng **không tự động cấp quyền nhìn thấy toàn bộ classpath của host**. Ta có thể tạo loader con với parent là platform loader:

~~~java
ClassLoader parent = ClassLoader.getPlatformClassLoader();

// Mã minh họa, không phải chương trình đầy đủ:
// URL[] urls = ... các URL tới JAR tùy biến ...
// try (URLClassLoader pluginLoader = new URLClassLoader(urls, parent)) {
//     ...
// }
~~~

Khi đó plugin loader có thể ủy quyền việc tìm các lớp nền tảng cho platform loader. Nó **không mặc nhiên nhìn thấy** các class ứng dụng do system loader định nghĩa, vì system loader không phải tổ tiên của platform loader.

Nếu plugin cần triển khai một interface riêng của ứng dụng như `com.example.api.Plugin`, parent nên là **loader đã định nghĩa interface đó** hoặc một loader có thể ủy quyền tới class ấy, ví dụ:

~~~java
ClassLoader sharedApiParent = Plugin.class.getClassLoader();
~~~

Đoạn trên chỉ có ý nghĩa trong dự án đã định nghĩa `Plugin`; đây là **mã minh họa**, không phải file Java chạy độc lập. Dùng parent là loader của hợp đồng API giúp host và plugin chia sẻ đúng **cùng runtime type**, tránh hai loader tự định nghĩa các lớp API giống tên rồi phát sinh `ClassCastException` hoặc `ServiceConfigurationError`.

**Không nhầm tầm nhìn với bảo mật:** Đặt platform loader làm parent có thể hạn chế những class ứng dụng mà plugin nhìn thấy qua cơ chế ủy quyền; điều này **không tạo sandbox đáng tin cậy** cho mã plugin. Plugin chạy trong cùng JVM vẫn có thể thực thi mã với quyền của tiến trình.

### 3.3. Ghi chú về JPMS

Một số module nâng cấp (upgraded modules) có quan hệ đọc module khác; vì vậy triển khai platform loader có thể thực hiện ủy quyền tới loader **không phải tổ tiên** trong những tình huống module nhất định. Đây là điểm được chính Javadoc lưu ý. Không nên viết một quy tắc tuyệt đối rằng platform loader “không bao giờ ủy quyền tới system loader” hoặc chỉ dựa vào quan hệ `getParent()` để kết luận toàn bộ tầm nhìn module.

## 4. `getSystemClassLoader()`

### 4.1. Chức năng và giá trị trả về

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
~~~

Phương thức trả về system class loader, thường dùng để tải class khởi động ứng dụng. Đây cũng là **parent mặc định** của instance `ClassLoader` được tạo bằng constructor không nhận parent:

~~~java
class MyLoader extends ClassLoader {
    // super() ngầm định: parent mặc định là system class loader.
}
~~~

Với Java 17 chạy ứng dụng classpath thông thường:

- Loader định nghĩa class chứa phương thức `main` thường là system/application loader.
- `system.getParent() == ClassLoader.getPlatformClassLoader()` thường đúng với loader tích hợp mặc định.
- `Thread.currentThread().getContextClassLoader() == system` thường đúng trong luồng `main` mà Java launcher tạo.

Ba nhận xét trên mô tả **mặc định**, không phải lời hứa cho mọi application server, IDE, agent, plugin host, container Java tùy biến hoặc luồng mà ứng dụng tự đặt context loader.

### 4.2. System loader tìm các class ở đâu?

Trong một ứng dụng khởi chạy bằng classpath:

~~~bash
java -cp "build/classes:lib/example.jar" com.example.Main
~~~

System loader thường tìm class ứng dụng từ các thư mục/JAR trên application classpath. Trên Windows, dấu phân tách classpath là `;`; trên Linux/macOS thường là `:`.

Khi chạy ứng dụng JPMS với `--module-path` và `--module`, class của các module ứng dụng thường được hệ thống loader tương ứng quản lý. Tuy vậy không thể suy ra đơn giản rằng mọi module trên module path đều do **cùng một** ClassLoader định nghĩa: cấu hình module layers và quy tắc loader vẫn quan trọng.

Khác với Java 8, Java 9+ không đảm bảo system loader là `java.net.URLClassLoader`. Mã như:

~~~java
// Không an toàn trên JDK hiện đại:
// URLClassLoader urls = (URLClassLoader) ClassLoader.getSystemClassLoader();
~~~

có thể gây `ClassCastException`. Muốn xem classpath, hãy xem `System.getProperty("java.class.path")` (nếu phù hợp) hoặc API build/runtime đang dùng; muốn thêm URL cho plugin, tạo một `URLClassLoader` riêng. Không dựa vào class triển khai nội bộ như `jdk.internal.loader.ClassLoaders$AppClassLoader`.

### 4.3. Custom system loader

JVM cho phép đặt system property **ngay khi khởi động**:

~~~bash
java -Djava.system.class.loader=com.example.CustomLoader -cp ... com.example.Main
~~~

Tên class ở đây chỉ là ví dụ về cấu hình; lệnh **không chạy được nếu chưa viết và cung cấp** `com.example.CustomLoader` trên classpath thích hợp. Custom system loader phải có **public constructor nhận đúng một tham số kiểu `ClassLoader`**. JVM nạp class cấu hình bằng default system loader rồi truyền default system loader làm parent khi khởi tạo instance custom.

Hệ quả:

1. `getSystemClassLoader()` có thể trả về **custom loader**, không phải loader tích hợp ban đầu.
2. `getSystemClassLoader().getParent()` có thể là default system loader thay vì platform loader trực tiếp.
3. Trong constructor của custom loader, **không gọi ngược `getSystemClassLoader()`**: vòng lặp khởi tạo có thể gây `IllegalStateException`.
4. Nếu class cấu hình không thể nạp, constructor không phù hợp hoặc constructor lỗi, JVM có thể báo `Error` khi thiết lập system loader.
5. Runtime chỉ xét property này lúc khởi tạo system loader. Đổi `System.setProperty(...)` về sau không phải cách thay loader của JVM đang chạy.

Đây là cấu hình đặc biệt. Ứng dụng bình thường **không cần** thay thế system loader chỉ để tải plugin hoặc một JAR động.

## 5. Chương trình Java 17+ so sánh trực tiếp hai loader

Tạo **một file** `LoaderComparison.java` ở thư mục bất kỳ:

~~~java
public final class LoaderComparison {
    private LoaderComparison() {
    }

    static final class AppType {
    }

    private static String definedBy(
            Class<?> type, ClassLoader platform, ClassLoader system) {
        ClassLoader loader = type.getClassLoader();
        if (loader == null) {
            return "bootstrap";
        }
        if (loader == platform) {
            return "platform";
        }
        if (loader == system) {
            return "system";
        }
        return "other";
    }

    public static void main(String[] args) throws ClassNotFoundException {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("Platform exists: " + (platform != null));
        System.out.println("System differs from platform: " + (system != platform));

        System.out.println("Platform parent is bootstrap: "
                + (platform.getParent() == null));
        System.out.println("System parent is platform: "
                + (system.getParent() == platform));

        System.out.println("String defined by: "
                + definedBy(String.class, platform, system));
        System.out.println("AppType defined by: "
                + definedBy(AppType.class, platform, system));

        Class<?> delegated = system.loadClass("java.lang.String");
        System.out.println("Delegated String identical: "
                + (delegated == String.class));

        boolean platformCanFindApp;
        try {
            platform.loadClass("LoaderComparison$AppType");
            platformCanFindApp = true;
        } catch (ClassNotFoundException ex) {
            platformCanFindApp = false;
        }
        System.out.println("Platform finds application class: "
                + platformCanFindApp);

        System.out.println("Main context loader is system: "
                + (Thread.currentThread().getContextClassLoader() == system));
    }
}
~~~

**Biên dịch và chạy** bằng JDK 17+ từ thư mục chứa file, trong một phiên Java bình thường, **không** dùng `-Djava.system.class.loader`, `--patch-module` hay công cụ thay đổi loader:

~~~bash
javac -encoding UTF-8 LoaderComparison.java
java -cp . LoaderComparison
~~~

**Stdout dự kiến trên OpenJDK/Oracle JDK 17 tiêu chuẩn với các giả định trên:**

~~~text
Platform exists: true
System differs from platform: true
Platform parent is bootstrap: true
System parent is platform: true
String defined by: bootstrap
AppType defined by: system
Delegated String identical: true
Platform finds application class: false
Main context loader is system: true
~~~

Lệnh `-cp .` làm code ứng dụng nằm trên application classpath. Nếu môi trường chạy đã cấu hình loader tùy biến, module patching hoặc context ClassLoader khác, một số so sánh về parent, nơi định nghĩa class hoặc context loader có thể thay đổi. Khi đó kết quả là thông tin chẩn đoán hữu ích, không phải JVM “sai”.

### Giải thích từng phép kiểm tra

**`platform != null` và `system != platform`.** Platform loader là đối tượng loader riêng, khác system loader trong hệ loader tích hợp. Bootstrap loader mới là loader thường được biểu diễn bằng `null`.

**`getParent()`.** Parent của platform là bootstrap trong cấu hình mặc định, nên `platform.getParent() == null`. Parent của system tích hợp là platform. Nếu system loader được custom, so sánh parent trực tiếp cần xét lại.

**`String.class.getClassLoader()`.** `java.lang.String` được bootstrap định nghĩa, vì vậy `definedBy` trả về `bootstrap`. Việc gọi `system.loadClass("java.lang.String")` vẫn nhận đúng cùng đối tượng `Class<?>` nhờ delegation; system loader **không tự định nghĩa lại** `String`.

**`AppType.class.getClassLoader()`.** `AppType` là nested class thuộc source ứng dụng, được system loader nạp trong lần chạy classpath chuẩn; kết quả là `system`. Class lồng này không được JVM tự động coi là class của nền tảng chỉ vì nó nằm trong cùng file.

**`platform.loadClass("LoaderComparison$AppType")`.** Tên nhị phân của class lồng sử dụng `$`. Platform loader thông thường không có application classpath của chương trình và không tìm class ứng dụng này; do đó bắt `ClassNotFoundException` rồi in `false`.

**`Thread.currentThread().getContextClassLoader()`.** Java launcher thường gán system loader làm context loader của luồng `main`. Đây là trạng thái **của thread**, có thể sửa bởi framework và code ứng dụng, không phải một phương thức lấy loader định nghĩa class `LoaderComparison`.

## 6. Ba cách lấy ClassLoader khác nhau và khi nào dùng

Các API sau dễ bị nhầm lẫn nhưng câu hỏi mà chúng trả lời khác nhau:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();

ClassLoader system = ClassLoader.getSystemClassLoader();

ClassLoader defining = LoaderComparison.class.getClassLoader();

ClassLoader context = Thread.currentThread().getContextClassLoader();
~~~

| Cách lấy | Ý nghĩa chính | Khi phù hợp |
|---|---|---|
| `getPlatformClassLoader()` | Loader nền tảng tích hợp | Làm parent khi một loader con chỉ cần chia sẻ API của nền tảng |
| `getSystemClassLoader()` | System/application loader được JVM chọn | Tìm class/resource ứng dụng trong cấu hình runtime tiêu chuẩn; parent mặc định |
| `SomeApi.class.getClassLoader()` | Loader **đã định nghĩa** đúng runtime type `SomeApi` | Thiết kế host/plugin cần dùng chung interface và DTO |
| `Thread.currentThread().getContextClassLoader()` | Loader do thread giữ để framework tra cứu theo ngữ cảnh | `ServiceLoader` và cơ chế khám phá class/resource của một số thư viện |

**Ví dụ với `ServiceLoader`:** `ServiceLoader.load(MyService.class)` thường tra cứu provider qua thread context loader. Ngược lại, `ServiceLoader.load(MyService.class, explicitLoader)` nhận loader do ứng dụng truyền vào. Vì vậy một provider trong plugin loader có thể không được tìm thấy nếu thread context loader vẫn là system loader không thấy plugin JAR.

Nếu tạm đổi context loader, luôn khôi phục bằng `finally`:

~~~java
// Mã minh họa: cần khai báo pluginLoader tại chương trình thực tế.
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi API thư viện cần phát hiện class bằng context loader.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Đừng thay context loader vĩnh viễn cho toàn bộ ứng dụng nếu không hiểu ảnh hưởng của nó trên thread pool hoặc framework khác.

## 7. Vì sao “class loading” không giống “class initialization”?

Hai phương thức `getPlatformClassLoader()` và `getSystemClassLoader()` chỉ lấy tham chiếu loader. Khi gọi `loadClass("com.example.Widget")`, loader thường yêu cầu nạp class (và có thể resolve theo đường API khác) nhưng **không tự động thực thi static initializer của class đó**.

Phân biệt:

~~~java
Class<?> a = ClassLoader.getSystemClassLoader()
        .loadClass("com.example.Widget");

// Mã minh họa: nếu Widget tồn tại và cần kích hoạt initialization:
Class<?> b = Class.forName(
        "com.example.Widget",
        true,
        ClassLoader.getSystemClassLoader()
);
~~~

Trong overload ba tham số của `Class.forName`, `initialize = true` yêu cầu initialization nếu class chưa khởi tạo. Có thể dùng `false` khi muốn tìm class mà không chủ động kích hoạt initialization.

Mỗi runtime type được nhận diện bằng **tên nhị phân + loader định nghĩa**, nên hai loader tự định nghĩa hai class cùng FQCN có thể tạo hai kiểu không tương thích. `loadClass` có thể trả về class từ parent; **không thể** xác định nơi class được định nghĩa chỉ bằng tên ClassLoader mà caller đã dùng.

## 8. Thực tế sử dụng: chọn parent cho một loader plugin

Giả sử ứng dụng chủ khai báo interface `com.acme.api.Plugin` và plugin cần implements interface ấy.

~~~text
Application classpath
  └── com.acme.api.Plugin       ← do loader của host định nghĩa
Plugin JAR
  └── com.vendor.HelloPlugin    ← do loader con định nghĩa
~~~

Hai lựa chọn parent mang ý nghĩa khác nhau:

**A. Chia sẻ API của host:**

~~~java
// Đây là mẫu thiết kế, không phải chương trình chạy độc lập.
// Plugin là interface đã định nghĩa trong ứng dụng.
ClassLoader parent = Plugin.class.getClassLoader();
// URLClassLoader loader = new URLClassLoader(jarUrls, parent);
~~~

Loader con ủy quyền tới loader của `Plugin`, qua đó có thể resolve interface chung đúng bản sắc class. Điều này thường hợp lý cho plugin trong cùng JVM.

**B. Chỉ ủy quyền trực tiếp tới platform loader:**

~~~java
ClassLoader parent = ClassLoader.getPlatformClassLoader();
// URLClassLoader loader = new URLClassLoader(jarUrls, parent);
~~~

Nếu interface `Plugin` chỉ có ở classpath do system loader định nghĩa và không nằm trong plugin JAR, loader con **thường không tìm được** interface ấy. Hệ quả có thể là `NoClassDefFoundError` hoặc lỗi provider khi load class triển khai; việc platform loader là parent không làm classpath của system trở thành tầm nhìn của con.

Đây là lý do **chọn parent theo nhu cầu chia sẻ type** thay vì chọn máy móc platform hoặc system. Đối với plugin không tin cậy, cần giới hạn đặc quyền ở cấp tiến trình/container và giao thức tách biệt; ClassLoader không cung cấp ranh giới bảo mật đáng tin.

## 9. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân hoặc hiểu lầm | Cách xử lý |
|---|---|---|
| `ClassCastException` khi ép system loader sang `URLClassLoader` | Java 9+ không cam kết system loader có kiểu `URLClassLoader` | Dùng API `ClassLoader`, hoặc tự tạo `URLClassLoader` dành cho JAR cần nạp |
| `platform.getParent() == null` rồi kết luận platform cũng là bootstrap | `null` ở đây **biểu diễn parent bootstrap**, không nói platform là bootstrap | So sánh trực tiếp `platform == null` (false), hiểu ý nghĩa `getParent()` |
| System loader trả `String.class` rồi kết luận nó định nghĩa `String` | Delegation trả class do bootstrap định nghĩa | Kiểm tra `String.class.getClassLoader()` |
| `ClassNotFoundException` khi platform loader tìm class host | Application classpath không phải nguồn tìm class thông thường của platform loader | Dùng loader của API host hoặc system loader khi phù hợp |
| `NoClassDefFoundError` trong plugin | Plugin loader không thấy dependency hoặc interface cần resolve | Kiểm tra parent và URL chứa JAR phụ thuộc, cùng danh tính loader của interface |
| `getSystemClassLoader().getParent()` khác platform | Custom system loader hoặc cấu hình runtime khác | Kiểm tra `java.system.class.loader` và thứ bậc loader thực tế |
| `ServiceLoader` không tìm provider | Thread context loader không nhìn thấy JAR plugin hoặc thiếu `META-INF/services` | Chỉ rõ loader khi load service; kiểm tra descriptor và resource |
| Khởi tạo custom system loader gây lỗi vòng lặp | Constructor gọi lại `getSystemClassLoader()` | Dùng parent constructor được JVM truyền vào; tránh truy cập system loader trong quá trình khởi tạo |
| `getResource(...)` không thấy resource trong named module | Module đóng gói tài nguyên hoặc khác loader/tầm nhìn | Kiểm tra tên resource, loader, module và quy tắc `opens` của module |
| Code chạy được từ IDE nhưng không chạy từ CLI | IDE dùng classpath/module path hoặc context loader khác | So sánh lệnh chạy, classpath/module path và kết quả `getClassLoader()` |

Để debug, ưu tiên kiểm tra **object identity** của loader và class, ví dụ:

~~~java
System.out.println(Example.class.getClassLoader());
System.out.println(Example.class.getClassLoader()
        == ClassLoader.getSystemClassLoader());
~~~

Đây chỉ là mã minh họa khi đã có class `Example`. Không dùng chuỗi `toString()` của loader làm định danh ổn định: tên hiển thị và cấu trúc của lớp triển khai phụ thuộc runtime. Trong môi trường ứng dụng thực tế, còn nên kiểm tra tên module, `Class.getModule()`, và nguồn bytecode nếu liên quan.

## 10. Câu hỏi tự kiểm tra

**1. Vì sao `ClassLoader.getSystemClassLoader().loadClass("java.lang.String")` vẫn trả class có `getClassLoader() == null`?**

Vì yêu cầu nạp được system loader **ủy quyền** cho ancestor. Bootstrap định nghĩa `String`, còn system loader chỉ đưa ra class đã được nạp/định nghĩa đúng nơi.

**2. Tại sao `ClassLoader.getPlatformClassLoader().getParent() == null` không chứng minh rằng platform loader không tồn tại?**

`getParent()` trả về loader cha; `null` đại diện bootstrap trong cấu hình tiêu chuẩn. Bản thân platform loader vẫn là một instance mà `getPlatformClassLoader()` trả về.

**3. Dùng loader nào làm parent khi plugin cần implements một interface riêng của host?**

Thường là `HostApi.class.getClassLoader()`, hoặc loader khác được chứng minh có thể tìm đúng **cùng interface runtime type**. Không mặc nhiên chọn platform loader vì nó thường không thấy classpath host.

**4. Vì sao không ép kiểu system loader sang `URLClassLoader` trên Java 17?**

API chỉ hứa trả một `ClassLoader`. Java 9+ sử dụng triển khai loader tích hợp khác với Java 8, nên cast có thể thất bại.

**5. Nếu `getSystemClassLoader()` trả về custom loader, quan hệ parent mặc định có còn là “system → platform” trực tiếp không?**

Không chắc. Custom loader nhận default system loader làm parent; sơ đồ có thể là **custom system → default system → platform → bootstrap**.

**6. Thread context loader có luôn bằng system loader không?**

Không. Luồng `main` thường bắt đầu với system loader, nhưng framework, application server và code ứng dụng có thể đặt context loader khác. Muốn biết class do ai định nghĩa, dùng `SomeClass.class.getClassLoader()`.

## 11. Nguồn tham khảo

- [Java SE 17: ClassLoader — Built-in Class Loaders, getPlatformClassLoader và getSystemClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17: Class — getClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader())
- [Java SE 17: ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 17: Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader))

**Ghi nhớ:** `getPlatformClassLoader()` lấy loader dành cho API/runtime nền tảng; `getSystemClassLoader()` lấy loader hệ thống thường dùng cho ứng dụng. Quan hệ parent giúp delegation, nhưng **loader được gọi** không nhất thiết là **loader định nghĩa class**. Khi thiết kế plugin, chọn parent dựa vào class/interface mà plugin thực sự cần chia sẻ.
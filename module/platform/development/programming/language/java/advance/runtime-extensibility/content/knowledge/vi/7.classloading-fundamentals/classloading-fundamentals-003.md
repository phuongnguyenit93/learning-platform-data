# Vai trò của bootstrap, platform và application class loader trong Java

## 1. Vì sao cần hiểu ba class loader nền tảng?

Khi JVM cần sử dụng một class, câu hỏi quan trọng không chỉ là **file `.class` hoặc JAR nằm ở đâu**, mà còn là **class loader nào tìm thấy hoặc định nghĩa class đó**. Điều này ảnh hưởng trực tiếp đến:

- Cách JVM tải class nền tảng Java, API của JDK và mã ứng dụng.
- Khả năng một class nhìn thấy những class khác, thư viện hoặc tài nguyên.
- Cách hoạt động của classpath, module path, `ServiceLoader` và plugin được nạp lúc chạy.
- Việc tách phiên bản thư viện, nhận diện cùng một kiểu Java và chẩn đoán lỗi `ClassNotFoundException`, `NoClassDefFoundError` hay `ClassCastException`.

Trong Java 17+, ba **built-in class loader** đáng phân biệt là:

1. **Bootstrap class loader:** class loader tích hợp trong máy ảo, chịu trách nhiệm với các class nền tảng cốt lõi.
2. **Platform class loader:** class loader dành cho các lớp thuộc nền tảng Java/JDK được giao cho nó và các lớp thấy được qua cơ chế ủy quyền.
3. **Application (system) class loader:** class loader thông thường của mã ứng dụng, thư viện trên application classpath và các module được giao cho nó.

Đây là **ba vai trò khác nhau trong cơ chế nạp class**. Chúng không phải tên ba thư mục, không đồng nghĩa ba module layer và cũng không phải ba trạng thái lifecycle của class.

## 2. Sơ đồ quan hệ và phạm vi

Trong môi trường Java launcher mặc định, cách hình dung thường gặp là:

~~~text
          Bootstrap class loader
       (do JVM cung cấp; thường là null)
                     ▲
                     │ parent / delegation
          Platform class loader
            (platform classes)
                     ▲
                     │ parent / delegation
     Application/System class loader
       (application classpath/modules)
                     ▲
                     │ parent / delegation, nếu có
      Custom/plugin class loader
       (ứng dụng tự tạo thêm)
~~~

Mũi tên đi **lên** thể hiện một loader thường hỏi loader cha trước khi thử tự tìm class theo cơ chế *parent-first*. Với các built-in loader ở môi trường mặc định, platform là cha hoặc tổ tiên của system loader. Loader tùy chỉnh có thể chọn parent khác và trong một số trường hợp sử dụng chính sách tìm class khác.

**Không nên đọc sơ đồ như quy tắc “class nào ở dưới cũng bị nạp bởi loader ở trên”.** Một loader có thể **truy cập class đã được parent định nghĩa** mà không định nghĩa lại class đó. JPMS cũng có quy tắc truy cập theo module và đôi khi cơ chế delegation không hoàn toàn là một cây cứng nhắc.

| Tiêu chí | Bootstrap | Platform | Application/System |
|---|---|---|---|
| Vai trò chính | Đảm nhận class cốt lõi của runtime và các module được giao cho bootstrap | Làm cho các class của nền tảng Java SE/JDK có thể truy cập qua phạm vi platform | Tải mã ứng dụng, dependency và module ứng dụng được giao cho system loader |
| Lấy loader trong Java | Không có đối tượng Java công khai tương đương; thường biểu diễn là `null` | `ClassLoader.getPlatformClassLoader()` | `ClassLoader.getSystemClassLoader()` |
| Parent | Không có | Thường là bootstrap, biểu diễn bởi `getParent() == null` | Platform là cha hoặc tổ tiên; loader system có thể tùy biến |
| Nguồn class thường gặp | Class cơ bản của `java.base` như `java.lang.Object`, `String` | Một số module/API nền tảng và JDK | Class trong `-cp`, một số named modules trên application module path |
| Có phải `URLClassLoader`? | Không phải đối tượng `URLClassLoader` | Không nên giả định | **Không** nên ép kiểu thành `URLClassLoader` trên JDK 9+ |
| Dùng làm parent cho plugin? | Có thể dùng `null`, nhưng thường quá hạn chế | Có thể dùng cho loader cần thấy platform API và cố ý tránh parent application loader | Hay dùng khi plugin cần thấy cả SPI, API và thư viện chia sẻ của host |

**Phạm vi nhìn thấy không đồng nhất với nơi class được định nghĩa.** Một class nền tảng có thể **được định nghĩa bởi bootstrap** nhưng vẫn **nhìn thấy được qua platform hoặc application loader** do cơ chế ủy quyền.

## 3. Bootstrap class loader: nền tảng khởi động JVM

### 3.1. Nhiệm vụ

Bootstrap loader được tích hợp trong JVM. Nó chịu trách nhiệm định nghĩa những class thiết yếu để Java runtime hoạt động, chẳng hạn `java.lang.Object`. Các thành phần quan trọng của module `java.base` thường thuộc phạm vi bootstrap.

Java không cung cấp `ClassLoader.getBootstrapClassLoader()`. Trong API `ClassLoader`, bootstrap thường được biểu diễn bằng `null`:

~~~java
System.out.println(Object.class.getClassLoader() == null);
System.out.println(String.class.getClassLoader() == null);
~~~

Đầu ra trên cách triển khai JDK 17+ thông thường:

~~~text
true
true
~~~

**`null` ở đây không có nghĩa JVM “không tải class”.** Nó là cách biểu diễn việc class được định nghĩa bởi bootstrap loader, thay vì một đối tượng `ClassLoader` có thể lấy trực tiếp bằng Java API.

### 3.2. Bootstrap không tải toàn bộ thư viện chuẩn

Từ khi Java được modular hóa, **không nên mặc định mọi class có package `java.*` hoặc mọi class của Java SE đều được bootstrap định nghĩa**. Một số API hoặc implementation class của nền tảng được định nghĩa bởi platform loader. API chính thức đảm bảo *platform loader nhìn thấy các platform classes*, chứ không yêu cầu một class nền tảng cụ thể phải do platform hay bootstrap định nghĩa.

Vì vậy:

~~~java
ClassLoader parent = null;
~~~

là cách nói “tạo custom loader với bootstrap làm parent” ở API loader thông thường; **không** phải cách bảo đảm custom loader nhìn thấy mọi Java SE API. Một custom loader cần nhiều platform class thường nên chọn:

~~~java
ClassLoader parent = ClassLoader.getPlatformClassLoader();
~~~

Thực tế, đừng xây logic nghiệp vụ dựa trên giả định cố định rằng một Java SE class cụ thể luôn có `getClassLoader() == null` trên mọi JDK, ngoại trừ những trường hợp cốt lõi mà bạn đã chủ động kiểm tra.

### 3.3. Không nhầm bootstrap loader với boot module layer

Trong JPMS, **`ModuleLayer.boot()`** là layer chứa các named modules được resolve tại thời điểm khởi động. **Bootstrap class loader** là cơ chế định nghĩa class. Hai khái niệm khác nhau:

- Một module trong boot layer có thể được giao cho bootstrap, platform hoặc application loader.
- Một class được định nghĩa bởi bootstrap không chứng tỏ mọi module trong boot layer đều được bootstrap tải.
- `Module#getClassLoader()` và `Class#getClassLoader()` cho phép quan sát loader gắn với module/class; `null` biểu diễn bootstrap trong API tương ứng.

Tên “boot” giống nhau nhưng không đồng nghĩa.

## 4. Platform class loader: phạm vi các class nền tảng

### 4.1. Vai trò và cách lấy

Java 9 giới thiệu `ClassLoader.getPlatformClassLoader()`. Platform loader chịu trách nhiệm cho các class nền tảng do nó hoặc tổ tiên của nó định nghĩa. Một custom loader có thể dùng platform loader làm parent:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
ClassLoader child = new ClassLoader(platform) {};
~~~

Đây là đoạn mã Java hợp lệ trong ngữ cảnh một method hoặc initializer; nó tạo loader con mặc định mà chưa định nghĩa class mới.

Vai trò của platform loader:

- Làm cho platform classes có thể truy cập đối với code nạp qua phạm vi platform.
- Đóng vai trò cha/tổ tiên trong hệ thống loader khởi động mặc định.
- Tạo một parent thích hợp cho loader mở rộng cần Java SE API nhưng không chủ đích kế thừa toàn bộ application classpath.
- Tham gia việc xác định phạm vi service discovery: `ServiceLoader.loadInstalled(S.class)` tương đương việc tìm provider bằng platform loader.

Không nên hiểu platform loader là “loader tải mọi class thuộc JDK”. Nhiều class JDK/Java SE được bootstrap định nghĩa; platform vẫn có thể nhìn thấy chúng bằng delegation.

### 4.2. Platform loader thay thế vai trò extension loader cũ

Ở JDK 8 và trước đó, sơ đồ thường được dạy là:

~~~text
Bootstrap -> Extension -> Application
~~~

Java 9 loại bỏ extension mechanism dựa trên `jre/lib/ext` và `java.ext.dirs`, đồng thời dùng thuật ngữ **platform class loader** trong hệ thống loader modular. Trong Java 17+, không nên hướng dẫn người học chép JAR vào `lib/ext` để “cài” extension.

Một ứng dụng muốn dùng thư viện bên ngoài nên khai báo dependency bằng build tool, classpath/module path hoặc cơ chế nạp plugin riêng. Tên `platform` không có nghĩa ứng dụng có một thư mục “platform JAR” tự động được quét.

### 4.3. Platform không phải ranh giới cô lập tuyệt đối

Mô hình parent-first thông thường khiến platform loader không tìm mã chỉ có trên application classpath. Nhưng đặc tả `ClassLoader` ghi nhận rằng, trong một số tình huống liên quan đến upgraded modules và quan hệ module readability, **platform loader có thể phải delegate tới loader khác, kể cả application loader**.

Vì vậy, câu “platform không bao giờ có thể nhìn thấy bất kỳ class ứng dụng nào” là **quá tuyệt đối**. Quy tắc thiết kế đáng tin là:

- Platform loader đại diện cho phạm vi platform classes và là parent phù hợp khi cần API nền tảng.
- Không dùng nó như một giải pháp bảo mật hoặc sandbox để chắc chắn chặn mọi truy cập tới application code.
- Với class trên application classpath thông thường, platform loader **không phải** cơ chế dùng để tải chúng.

## 5. Application/system class loader: mã và dependency của ứng dụng

### 5.1. Nhiệm vụ và tên gọi

`ClassLoader.getSystemClassLoader()` trả về **system class loader**, thường gọi là **application class loader**. Trong khởi chạy thông thường, loader này định nghĩa class của ứng dụng nằm trên application classpath hoặc các module ứng dụng được giao cho nó.

Ví dụ:

~~~bash
java -cp "out:lib/*" com.example.Main
~~~

Trên Linux/macOS, `:` là dấu phân tách các mục classpath; trên Windows dùng `;`:

~~~powershell
java -cp "out;lib/*" com.example.Main
~~~

Application loader của trình khởi chạy thông thường có thể tìm class trong `out` và các JAR trực tiếp thuộc `lib/*`. Thứ tự tìm class thực tế còn phụ thuộc parent delegation, các module đã resolve và chính sách loader.

Với ứng dụng JPMS:

~~~bash
java --module-path mods --module com.example.app/com.example.Main
~~~

Application module path phục vụ **module discovery và resolution**; class trong những module đó được định nghĩa bởi loader mà runtime/layer gán cho module. Nhiều module ứng dụng trong boot layer mặc định dùng system loader, nhưng **module path không phải một class loader độc lập**.

### 5.2. Phân biệt system loader và class loader của một class

Đoạn sau thường trả về `true` khi `Main` khởi chạy từ application classpath:

~~~java
Main.class.getClassLoader()
        == ClassLoader.getSystemClassLoader()
~~~

Tuy nhiên, trong application server, môi trường plugin, test runner hoặc module layer tùy chỉnh, **class hiện tại có thể do custom loader định nghĩa**. `getSystemClassLoader()` không luôn là loader định nghĩa class đang chạy.

Cần đặt đúng câu hỏi:

- “Loader hệ thống của JVM là gì?” → `ClassLoader.getSystemClassLoader()`.
- “Ai định nghĩa class này?” → `SomeType.class.getClassLoader()`.
- “Loader nào gắn với module này?” → `SomeType.class.getModule().getClassLoader()`.
- “Loader nào được dùng làm ngữ cảnh bởi thread?” → `Thread.currentThread().getContextClassLoader()`.

Bốn biểu thức có thể cho kết quả khác nhau.

### 5.3. Không ép kiểu system loader thành `URLClassLoader`

Trên Java 8, nhiều ví dụ làm như sau:

~~~java
URLClassLoader loader =
    (URLClassLoader) ClassLoader.getSystemClassLoader();
~~~

Đây là **anti-pattern trên JDK 9+**: built-in application loader không còn được bảo đảm là `URLClassLoader`; việc ép kiểu có thể ném `ClassCastException`. Java SE cũng không cung cấp API được hỗ trợ để tùy tiện bổ sung entry vào application classpath đang chạy.

Để nạp JAR plugin sau khi khởi động, ứng dụng nên tạo **loader riêng** (ví dụ `URLClassLoader`) hoặc module layer riêng, cùng quy trình quản lý plugin rõ ràng.

## 6. Cơ chế parent delegation: loader nào thực sự tải class?

### 6.1. Trình tự mặc định

Hành vi mặc định của `ClassLoader.loadClass(name, resolve)`, nếu subclass không override, có thể tóm tắt:

1. Kiểm tra class cùng tên đã từng được tìm/khởi tạo thông qua loader này chưa bằng `findLoadedClass`.
2. Yêu cầu parent loader nạp class; nếu parent biểu diễn bằng `null`, hỏi cơ chế bootstrap.
3. Nếu parent không tìm thấy, dùng `findClass` của loader hiện tại.
4. Nếu tìm được và `resolve == true`, liên kết class khi cần bằng `resolveClass`.

Một sơ đồ trực quan:

~~~text
loadClass("com.example.Feature")
            |
            v
     Đã tìm thấy trước đó?
       /           \
     Có             Chưa
      |              |
  Trả Class       Hỏi parent
                    /   \
                 Thấy   Không thấy
                  |         |
              Trả Class   findClass tại loader con
                              |
                         Class / ClassNotFoundException
~~~

Với một plugin loader parent-first, nếu parent đã có `com.example.Feature`, loader con thường nhận lại **chính class của parent**, dù JAR plugin có bản class cùng tên. Muốn có chính sách child-first phải thiết kế custom loader cụ thể, giải quyết xung đột API và những giới hạn của hệ module; không tự giả định mọi loader đều parent-first.

### 6.2. “Loader được hỏi” khác “loader định nghĩa”

Giả sử:

~~~java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
Class<?> type = platform.loadClass("java.lang.String");
~~~

Lời gọi thành công có nghĩa platform loader **có thể lấy được** class `String`, nhưng `type.getClassLoader()` trên JDK thông thường vẫn là `null`, vì class đã được **bootstrap định nghĩa**.

Do đó, trong log/debug nên phân biệt:

- **Requesting/initiating loader:** loader nhận yêu cầu, có thể delegate tới nơi khác.
- **Defining loader:** loader thật sự định nghĩa class từ bytecode; gắn với định danh runtime của class.

Đối với class được tải qua parent, loader con có thể đóng vai trò initiating loader nhưng không phải defining loader.

### 6.3. Định danh của class phụ thuộc loader

Ở runtime, định danh kiểu gắn với **binary class name + defining class loader**. Hai loader có thể định nghĩa hai class cùng tên `com.example.api.Widget` nhưng JVM không coi chúng là một kiểu:

~~~text
com.example.api.Widget [định nghĩa bởi Loader A]
                       ≠
com.example.api.Widget [định nghĩa bởi Loader B]
~~~

Điều này giải thích lỗi `ClassCastException` tưởng như vô lý khi một plugin đóng gói **bản sao** API/SPI của host. Cách phổ biến là để interface dùng chung nằm trong parent loader hoặc module API được cả hai phía chia sẻ; implementation thuộc loader của plugin.

## 7. Chương trình Java 17+ chạy được: quan sát ba loader

Ví dụ sau dùng **một file độc lập**, cho phép kiểm tra bootstrap, platform, application loader và sự khác nhau giữa chọn platform hay system làm parent. Không cần framework, Maven hay thư viện ngoài.

Tạo file `LoaderRolesDemo.java`:

~~~java
import java.net.URL;
import java.net.URLClassLoader;

public final class LoaderRolesDemo {

    public static void main(String[] args) throws Exception {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("Object-bootstrap="
                + (Object.class.getClassLoader() == null));
        System.out.println("Platform-present=" + (platform != null));
        System.out.println("System-parent-platform="
                + (system.getParent() == platform));
        System.out.println("Demo-defined-by-system="
                + (LoaderRolesDemo.class.getClassLoader() == system));
        System.out.println("Main-TCCL-system="
                + (Thread.currentThread().getContextClassLoader() == system));
        System.out.println("Platform-can-load-Object="
                + (platform.loadClass("java.lang.Object") == Object.class));

        try (URLClassLoader platformChild =
                     new URLClassLoader(new URL[0], platform);
             URLClassLoader systemChild =
                     new URLClassLoader(new URL[0], system)) {

            System.out.println("Platform-child-Object="
                    + canLoad(platformChild, "java.lang.Object"));
            System.out.println("Platform-child-Demo="
                    + canLoad(platformChild, "LoaderRolesDemo"));
            System.out.println("System-child-Demo="
                    + canLoad(systemChild, "LoaderRolesDemo"));
        }

        System.out.println("Demo-module-named="
                + LoaderRolesDemo.class.getModule().isNamed());
        System.out.println("Object-module="
                + Object.class.getModule().getName());
    }

    private static boolean canLoad(ClassLoader loader, String binaryName) {
        try {
            return loader.loadClass(binaryName) != null;
        } catch (ClassNotFoundException expected) {
            return false;
        }
    }
}
~~~

Trên Bash (Linux/macOS hoặc Git Bash), tại thư mục chứa file:

~~~bash
mkdir -p out
javac --release 17 -d out LoaderRolesDemo.java
java -cp out LoaderRolesDemo
~~~

Kết quả trên cấu hình khởi chạy mặc định của JDK 17+ (không cấu hình system loader riêng, không thay TCCL, không nâng cấp module nền tảng):

~~~text
Object-bootstrap=true
Platform-present=true
System-parent-platform=true
Demo-defined-by-system=true
Main-TCCL-system=true
Platform-can-load-Object=true
Platform-child-Object=true
Platform-child-Demo=false
System-child-Demo=true
Demo-module-named=false
Object-module=java.base
~~~

**Giải thích từng nhóm kết quả:**

- `Object-bootstrap=true`: `Object` là class cốt lõi do bootstrap định nghĩa; `getClassLoader()` biểu diễn bằng `null`.
- `Platform-present=true`: Java 17+ cung cấp platform loader từ API `getPlatformClassLoader()`.
- `System-parent-platform=true`: với JDK launcher mặc định, system loader có platform làm parent trực tiếp. Hợp đồng API tổng quát cho phép platform là **cha hoặc tổ tiên**, vì system loader có thể được cấu hình tùy chỉnh.
- `Demo-defined-by-system=true`: file `LoaderRolesDemo.class` nằm trên application classpath `out` và do system/application loader của launcher thông thường định nghĩa.
- `Main-TCCL-system=true`: thread chạy `main` thông thường có TCCL là system loader. Framework có thể thay đổi TCCL.
- `Platform-can-load-Object=true`: platform loader nhìn thấy `Object` qua delegation, dù không phải loader định nghĩa `Object`.
- Hai custom loader có mảng URL rỗng. Cả hai nhìn thấy `Object` nhờ parent, nhưng chỉ loader có **system parent** nhìn thấy `LoaderRolesDemo` trên application classpath thông thường.
- `Demo-module-named=false` vì mã trên `-cp out` thuộc unnamed module. `Object` thuộc named module `java.base`.

**Lưu ý:** output có chủ đích kiểm tra *quan hệ bằng boolean*, không in tên implementation như `jdk.internal.loader.ClassLoaders$AppClassLoader` vì đây là chi tiết nội bộ và có thể khác giữa các JDK. Phần “platform child không thấy Demo” là tình huống classpath thông thường của ví dụ, không phải một định luật cô lập tuyệt đối cho mọi JPMS/module-upgrade setup.

Với PowerShell/CMD trên Windows, có thể dùng `javac --release 17 -d out LoaderRolesDemo.java` và `java -cp out LoaderRolesDemo`; chỉ cần tạo `out` bằng lệnh phù hợp với shell (ví dụ `New-Item -ItemType Directory -Force out` trong PowerShell).

## 8. Thread context class loader (TCCL) liên quan thế nào?

`Thread.currentThread().getContextClassLoader()` là **loader ngữ cảnh** được gắn với thread. Nó không nhất thiết là loader định nghĩa class đang thực thi; nó cho phép code nền tảng/framework làm việc với class hoặc provider thuộc ứng dụng.

Ví dụ: một thư viện dùng `ServiceLoader.load(MyService.class)`. Theo API, overload này dùng **TCCL của thread hiện tại**. Nếu framework tạo thread với TCCL chỉ nhìn thấy platform API, thư viện có thể không tìm được provider của ứng dụng trên classpath. Ngược lại, framework có thể chủ ý đặt TCCL thành plugin loader để code chung có thể tìm provider plugin.

Đoạn mã minh họa trong một method:

~~~java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(
            ClassLoader.getPlatformClassLoader());

    // Mã bên trong dùng TCCL mới nếu nó tự tra TCCL.
    // Loader đã định nghĩa class của method này không đổi.
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
~~~

Cần phân biệt:

1. `setContextClassLoader` **không di chuyển** class đang chạy sang loader mới.
2. `Class.forName(String)`, `Class.forName(String, boolean, ClassLoader)`, `ServiceLoader` và các framework có **quy tắc chọn loader riêng**; không nên đoán tất cả đều luôn dùng TCCL.
3. Một thread mới thường kế thừa TCCL của thread tạo nó, trừ khi bị điều chỉnh.
4. Khi thay đổi TCCL tạm thời, **phải phục hồi** bằng `finally` để tránh ảnh hưởng lời gọi khác trong cùng thread.

Đặc biệt với `ServiceLoader`:

~~~java
ServiceLoader.load(MyService.class);  // TCCL hiện tại

ServiceLoader.load(
    MyService.class,
    ClassLoader.getSystemClassLoader());  // Chỉ định system loader

ServiceLoader.loadInstalled(MyService.class);  // Platform loader
~~~

Đoạn trên cần import `java.util.ServiceLoader` và interface `MyService` có thật; đây là **minh họa API, không phải chương trình độc lập**. `loadInstalled` dùng platform loader và bỏ qua các provider chỉ nằm trên application classpath hoặc application module path. Không dùng nó để thay cho plugin discovery.

## 9. Classpath, module path và loader: ba tầng khái niệm

### 9.1. Classpath

`-cp`/`--class-path` là **đường tìm class và resource** khi chạy ứng dụng không modular hoặc các phần thuộc unnamed module. Với launcher thông thường, system loader dùng application classpath.

~~~bash
java --class-path "out:lib/*" com.example.Main
~~~

Trong command này, không có loader thứ tư tên “classpath loader”. **Application loader** là loader thường dùng các entry classpath đó. Dùng `URLClassLoader` hoặc custom loader khác có thể tạo thêm **classpath-like search path** tại runtime, nhưng đó vẫn là một loader cụ thể do ứng dụng quản lý.

### 9.2. Module path và JPMS

`--module-path` là vị trí nơi **JPMS tìm module**. Module resolver chọn những module tham gia graph; sau đó module layer/runtime gán mỗi named module cho class loader.

~~~bash
java --module-path mods \
     --module com.example.app/com.example.Main
~~~

Cần tách ba bước:

- Tìm thấy một JAR/module ở `mods`.
- Resolve module vào configuration/module layer theo roots, `requires`, `--add-modules` hoặc cơ chế khác.
- Định nghĩa class của module bằng loader được chỉ định cho module đó.

**Có JAR trên module path không đồng nghĩa mọi class trong đó đã được tải**, hoặc module đã tự resolve. Một module ở application module path thường được giao cho application loader trong boot layer mặc định, nhưng có thể có lớp/module layer do ứng dụng tự tạo dùng loader khác.

### 9.3. Module exports/opens khác class loader delegation

Loader có thể tìm thấy `com.example.impl.Secret` nhưng named module chứa class đó **không export package** cho caller, nên truy cập kiểu `public` từ module khác vẫn bị giới hạn. `exports` cho phép truy cập public API theo JPMS; `opens` điều khiển deep reflection. Ngược lại, khai báo `exports` không tự giúp một loader tải JAR không thuộc phạm vi của nó.

Để chẩn đoán cần hỏi đủ hai câu:

1. **Class có được tìm/định nghĩa bởi loader phù hợp?**
2. **Module của caller có readability/access cần thiết tới module/package chứa class?**

## 10. Khi thiết kế runtime extensibility hoặc plugin

Một host có thể dùng ba built-in loader làm nền, nhưng plugin thực sự thường cần thêm cơ chế:

~~~text
JVM
├─ Bootstrap: các class cốt lõi
├─ Platform: platform/JDK API
└─ Application: host + shared SPI/API + dependency chung
   ├─ PluginLoader A: plugin A + dependency của A
   └─ PluginLoader B: plugin B + dependency của B
~~~

Đây là **một thiết kế khả dĩ**, không phải cấu trúc JVM tự tạo cho mọi plugin. Plugin manager quyết định vị trí JAR, loader/layer, phát hiện provider, kiểm tra tương thích và vòng đời plugin.

### 10.1. Chọn parent theo API cần chia sẻ

- **Parent là application/system loader:** plugin có thể truy cập API/SPI và dependency do host cung cấp, phù hợp khi các interface chung nằm trong application loader.
- **Parent là platform loader:** plugin thấy platform API nhưng **không mặc nhiên thấy API chỉ có trên application classpath**. Nếu plugin implements interface host và hai phía không chia sẻ đúng định danh kiểu, ép kiểu có thể thất bại.
- **Parent là bootstrap (truyền `null`):** phạm vi nền tảng bị thu hẹp; trên JDK 9+ một số Java SE classes có thể không thấy được bằng parent này. Không chọn `null` chỉ vì nghĩ “mọi Java API nằm ở bootstrap”.

Với mỗi plugin, cần xác định class loader nào định nghĩa **contract/interface**, class loader nào định nghĩa **implementation**, và cơ chế trao đổi object, resource hoặc service.

### 10.2. Parent-first và xung đột dependency

Nếu host và plugin đều có `org.example.lib.Helper` nhưng parent-first loader thấy bản host trước, plugin có thể nhận **phiên bản host** thay vì phiên bản đi kèm JAR plugin. Ngược lại, child-first cho mọi package có thể gây nạp trùng API/SPI, thậm chí nạp nhầm các class nên chia sẻ.

Một chính sách có kiểm soát thường:

- Dùng đúng một class/interface API chung tại host/module chung.
- Chọn cho phép chia sẻ hay cách ly các package thư viện cụ thể.
- Không nạp lại class trong package nền tảng của JDK như giải pháp giải quyết xung đột.
- Ghi log tên class, defining loader, module và nguồn JAR khi phát hiện lỗi.

### 10.3. Thêm JAR sau khi JVM chạy

Gọi `System.setProperty("java.class.path", ...)` sau khởi động **không tự cập nhật** system loader. `ClassLoader.getSystemClassLoader()` cũng không cung cấp API chuẩn để thêm JAR tùy ý trong lúc chạy.

Một ví dụ về cách tạo loader mới:

~~~java
// Đoạn mã tích hợp, chưa độc lập:
// pluginJar là Path trỏ tới JAR plugin thực tế.
try (URLClassLoader pluginLoader = new URLClassLoader(
        new URL[] { pluginJar.toUri().toURL() },
        HostSpi.class.getClassLoader())) {

    Class<?> type = pluginLoader.loadClass("com.acme.plugin.Impl");
    // Kiểm tra contract, khởi tạo provider và quản lý lifecycle.
}
~~~

Cần import `java.net.URL`, `java.net.URLClassLoader`, và có `java.nio.file.Path` cùng interface `HostSpi`. Trong ứng dụng thực tế, loader **phải sống trong toàn bộ thời gian plugin hoạt động**. Đóng `URLClassLoader` giải phóng tài nguyên như JAR handles, không buộc JVM unload class ngay; lớp và loader cũ chỉ có thể được thu gom khi không còn tham chiếu còn sống.

Với plugin là named module, có thể dùng `ModuleFinder`, `Configuration` và `ModuleLayer` để resolve/tạo layer mới. **Đây là tầng giải quyết module và gán loader**, không phải việc làm của ba built-in loader một cách tự động.

### 10.4. Class loader không tạo sandbox bảo mật

Việc chọn platform loader làm parent **không biến mã plugin không tin cậy thành mã an toàn**. Class loader chủ yếu phục vụ tổ chức và tìm/định nghĩa class. Nếu plugin chạy cùng tiến trình, nó có thể hưởng quyền của tiến trình thông qua API cho phép truy cập. Với plugin không tin cậy cần xem xét cô lập ở cấp tiến trình/container, chính sách quyền hệ điều hành và giao thức trao đổi có giới hạn.

## 11. Các lỗi thường gặp và cách xác minh

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/khắc phục |
|---|---|---|
| `Object.class.getClassLoader() == null` | Đúng hành vi bootstrap, **không** phải class bị thiếu loader | Hiểu `null` là bootstrap marker |
| Custom loader parent `null` không thấy một Java SE API | API thuộc phần platform không được bootstrap định nghĩa | Cân nhắc `ClassLoader.getPlatformClassLoader()` làm parent |
| `ClassNotFoundException` cho class ứng dụng | Đã hỏi platform/boot hoặc một plugin loader không có đường tìm cần thiết | Xác định loader dùng ở lời gọi, kiểm tra classpath/JAR/module resolution |
| `NoClassDefFoundError` | Class chính được tìm thấy nhưng phụ thuộc, liên kết hoặc khởi tạo gặp vấn đề | Đọc cause đầy đủ, kiểm tra dependency và log nạp class |
| `ClassCastException` giữa hai class cùng tên | Hai defining loaders tạo hai kiểu khác nhau | Thống nhất loader/module cho API chung, tránh JAR trùng contract |
| `ClassCastException` khi ép system loader sang `URLClassLoader` | JDK 9+ không bảo đảm system loader là `URLClassLoader` | Tạo custom `URLClassLoader` riêng nếu cần |
| `ServiceLoader` không tìm thấy provider | TCCL/loader không thấy provider, thiếu `META-INF/services` hoặc module `provides` | Dùng đúng overload, descriptor và module graph |
| `IllegalAccessError` hoặc `InaccessibleObjectException` | Quy tắc JPMS `exports`/`opens` không phù hợp | Chỉnh module descriptor/thiết kế API thay vì bỏ qua encapsulation |
| Nạp lại JAR nhưng class cũ vẫn tồn tại | Class đã được định nghĩa trong loader cũ; còn reference/instance/thread | Dừng plugin, bỏ tham chiếu, dùng loader/layer mới |
| Đã chỉnh `java.class.path` nhưng mã mới không thấy | System loader đã được khởi tạo | Khởi động lại với classpath đúng hoặc tạo loader riêng |

Khi debug có thể quan sát:

~~~java
System.out.println("Class defining loader: "
        + SomeType.class.getClassLoader());
System.out.println("Class module: " + SomeType.class.getModule());
System.out.println("System loader: "
        + ClassLoader.getSystemClassLoader());
System.out.println("Platform loader: "
        + ClassLoader.getPlatformClassLoader());
System.out.println("TCCL: "
        + Thread.currentThread().getContextClassLoader());
~~~

Đây là đoạn minh họa cần class `SomeType` thực tế. Trên JDK hỗ trợ logging tương ứng, có thể chạy ứng dụng với `-Xlog:class+load=info` để xem thông tin hoạt động nạp class; số lượng và định dạng dòng log phụ thuộc JDK. Tránh suy luận “class do loader X định nghĩa” chỉ từ một đường dẫn JAR hoặc từ class loader đang được hỏi.

## 12. Các điểm dễ nhầm từ Java 8 sang Java 17+

**Thay đổi quan trọng từ Java 9:**

- Thuật ngữ **extension loader** của tài liệu Java 8 được thay bằng **platform loader**, đồng thời cơ chế `lib/ext` cũ không còn được hỗ trợ.
- Application/system loader **không được đảm bảo** là `URLClassLoader`.
- JPMS thêm named modules, module path, module layer và ràng buộc `requires`/`exports`/`opens`. Mối liên hệ “một classpath ứng với một loader” trở nên kém chính xác khi ứng dụng sử dụng nhiều loader/layer.
- Một số class của Java SE do platform loader định nghĩa; một số do bootstrap định nghĩa. Không được phụ thuộc vào mapping nội bộ này để thiết kế app.
- `ClassLoader.getPlatformClassLoader()` là API chuẩn để lấy platform loader; ứng dụng có thể dùng nó làm parent phù hợp cho một custom loader.

**Không đổi về bản chất:** parent delegation vẫn là cơ chế mặc định hữu ích; class có identity theo tên + defining loader; ứng dụng muốn nạp plugin lúc chạy vẫn cần chọn loader/module layer và quản lý vòng đời.

## 13. Tự kiểm tra

1. **`Object.class.getClassLoader()` trả `null` có nghĩa Java không nạp `Object`?** Không. `null` biểu diễn bootstrap loader.
2. **Platform loader luôn trực tiếp định nghĩa mọi class Java SE?** Không. Platform có thể nhìn thấy class do bootstrap định nghĩa; mapping thực tế phụ thuộc runtime/module.
3. **System loader có phải luôn là loader của class hiện tại?** Không. Class có thể đến từ plugin loader, test runner, application server hoặc layer tùy chỉnh.
4. **Một class được platform loader nạp qua delegation thì `Class#getClassLoader` nhất thiết trả platform?** Không. Phải phân biệt initiating và defining loader.
5. **`--module-path` có phải một class loader thứ tư?** Không. Đó là đường tìm module để JPMS resolve, sau đó module được gán cho class loader.
6. **Truyền `null` làm parent có đủ để custom loader thấy toàn bộ Java SE API?** Không nên giả định, nhất là từ JDK 9+.
7. **Vì sao loader A và B có thể tạo hai `com.example.Widget` không ép kiểu cho nhau được?** Vì JVM phân biệt kiểu theo binary name cộng defining class loader.
8. **TCCL có quyết định loader định nghĩa method đang chạy?** Không. Nó là loader ngữ cảnh của thread, hữu ích cho framework/SPI.
9. **Thêm một JAR vào thư mục plugin có tự khiến system loader nạp nó?** Không. Host phải thiết lập loader/layer và quá trình khám phá, khởi tạo, đăng ký.
10. **Có thể dùng class loader như sandbox cho mã bên thứ ba không tin cậy?** Không. Loader không thay thế cách ly tiến trình và kiểm soát quyền.

## Tài liệu tham khảo

- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): built-in loaders, delegation, `getPlatformClassLoader()` và `getSystemClassLoader()`.
- [Java SE 17 — `Thread`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): thread context class loader.
- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): phạm vi tìm provider theo TCCL/loader/layer.
- [JDK 9 Release Notes](https://www.oracle.com/java/technologies/javase/9-relnotes.html): thay đổi built-in loaders, module path và việc system loader không còn là `URLClassLoader`.
- [Oracle JDK Migration Guide — New Class Loader Implementations](https://docs.oracle.com/en/java/javase/11/migrate/): sự khác nhau giữa bootstrap, platform và application loader từ Java 9.

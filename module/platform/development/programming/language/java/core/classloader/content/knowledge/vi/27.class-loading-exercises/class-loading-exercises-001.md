# In cây loader và nguồn gốc các lớp trong một ứng dụng nhỏ

## 1. Bài thực hành này giải quyết câu hỏi gì?

Khi JVM đã chạy một ứng dụng Java, không đủ chỉ nhìn vào tên package hoặc classpath để biết **ClassLoader nào thực sự định nghĩa mỗi class**. Đặc biệt khi ứng dụng có plugin JAR, nhiều class loaders hoặc một thư viện được đóng gói lặp, các câu hỏi thường gặp là:

- **java.lang.String** được định nghĩa bởi loader nào?
- Class của chương trình **Main** đến từ application/system loader hay plugin loader?
- Một class chỉ có trong **plugin.jar** có defining loader nào?
- Cây quan hệ **parent** của custom loader có hình dạng gì?
- Parent và plugin cùng chứa **sample.host.HostApi** thì JVM chọn bản nào?
- Có thể xác định **CodeSource** và resource URL của class từ JAR hay từ thư mục không?
- Vì sao hai loaders dùng cùng binary name có thể tạo hai **Class objects khác nhau**?
- In cây loader có đồng nghĩa thấy toàn bộ delegation/module graph không?

Bài thực hành xây một ứng dụng **Java 17+** với host ở thư mục **host-out**, plugin trong **plugin.jar**, hai **URLClassLoaders**, rồi in các bằng chứng tại runtime. Mã đã được biên dịch và chạy trên **OpenJDK 21** với các lệnh nêu dưới đây; ứng dụng chỉ dùng Java standard library.

**Mục tiêu quan trọng nhất:** tách ba loại thông tin: **(1) class identity/defining loader; (2) quan hệ parent của loader; (3) nguồn artifact/code source hoặc URL resource**. Chúng liên quan nhưng không thể dùng thay thế cho nhau.

## 2. Những quan sát khác nhau khi in cây loader

Bài thực hành phải phân biệt **danh tính lớp**, **cây parent** và **nguồn bytes**. Một lớp thông thường được nhận diện bởi **(binary name, defining loader)**, vì vậy hai `URLClassLoader` thực sự định nghĩa `sample.plugin.Greeter` sẽ có hai `Class<?>` khác nhau; còn hai loader ủy quyền cho cùng parent có thể trả đúng **một** `Class<?>`.

| Quan sát | API | Không nên suy ra |
| --- | --- | --- |
| Ai định nghĩa class? | `clazz.getClassLoader()` | Loader được gọi `loadClass()` nhất thiết là defining loader |
| Cha của loader là ai? | `loader.getParent()` | Đây là danh sách tất cả loader đang sống hoặc toàn bộ JPMS graph |
| Nguồn gốc được ghi nhận? | `clazz.getProtectionDomain().getCodeSource()` | URL là bằng chứng mật mã hoặc mọi class đều có CodeSource |
| Resource nằm đâu? | `clazz.getResource(...)` / `loader.getResources(...)` | Resource tồn tại nghĩa là class đã được JVM nạp |
| Class thuộc module nào? | `clazz.getModule()` | Module identity và defining loader là cùng khái niệm |

Trong HotSpot/OpenJDK phổ biến, cây parent bắt đầu từ application loader đi tới platform, rồi bootstrap (thường biểu diễn bằng `null`). `String.class.getClassLoader() == null` vì String do bootstrap định nghĩa, **không phải lỗi nạp lớp**. Một số platform classes có defining loader khác bootstrap; kết quả cụ thể còn tùy runtime/JDK.

Cần phân biệt **initiating loader** (loader khởi phát yêu cầu, có thể delegate) với **defining loader** (loader sở hữu class thực sự). `Class.getClassLoader()` chỉ cho biết defining loader, không phải danh sách mọi initiating loader. Chương trình sẽ đối chiếu object identity, nguồn artifact, parent chain và module thay vì dựa vào tên class hay chuỗi `toString()` của loader.

## 3. Kết quả mong đợi của bài

Chúng ta sẽ xây:

~~~text
Host application:
  host-out/
    sample/app/InspectLoaders.class
    sample/app/IsolatedLoaderDemo.class
    sample/host/HostApi.class
          |
          +-- HostApi.origin() -> "host"

Plugin artifact:
  plugin.jar
    sample/plugin/Greeter.class
    sample/host/HostApi.class
          |
          +-- bản HostApi đóng gói bên plugin
          +-- HostApi.origin() -> "plugin-shadow"
~~~

**Cố ý có hai bản HostApi** để quan sát parent delegation; đây là fixture thực hành, không phải kiến trúc plugin nên mặc định áp dụng. Khi plugin loader có **application loader làm parent**, lời gọi HostApi sẽ chọn bản host trước. Khi một loader cô lập có **platform loader làm parent**, nó không thấy host-out qua parent chain và sẽ lấy bản đóng trong plugin.jar.

Hai trường hợp cùng tên class nhưng defining loader khác nhau sẽ cho kết quả khác nhau.

## 4. Tạo project

Cấu trúc source hoàn chỉnh:

~~~text
loader-tree-lab/
├── src/
│   └── sample/
│       ├── app/
│       │   ├── InspectLoaders.java
│       │   └── IsolatedLoaderDemo.java
│       └── host/
│           └── HostApi.java
├── plugin-src/
│   └── sample/
│       ├── host/
│       │   └── HostApi.java
│       └── plugin/
│           └── Greeter.java
├── host-out/       (sinh ra sau javac)
├── plugin-out/     (sinh ra sau javac)
└── plugin.jar      (sinh ra sau jar)
~~~

**Chạy tất cả các lệnh từ thư mục loader-tree-lab**. Không đặt host-out hoặc plugin.jar lẫn vào một source folder rồi kỳ vọng parent delegation tự chọn đúng; các đường output ở đây được chủ động tách biệt để kiểm chứng.

### 4.1 API bản host

**src/sample/host/HostApi.java**:

~~~java
package sample.host;

public final class HostApi {
    private HostApi() {
    }

    public static String origin() {
        return "host";
    }
}
~~~

Ở runtime, class này sẽ đến từ thư mục **host-out** trên classpath của application.

### 4.2 API bản plugin dùng làm phép thử shadow

**plugin-src/sample/host/HostApi.java**:

~~~java
package sample.host;

public final class HostApi {
    private HostApi() {
    }

    public static String origin() {
        return "plugin-shadow";
    }
}
~~~

Đây là **một class có cùng binary name sample.host.HostApi** nhưng body khác. Ta biên dịch ra **plugin-out** và đóng gói vào plugin.jar. Nó cho phép quan sát trực tiếp bản nào đã được loader chọn, qua kết quả **origin()**.

**Cảnh báo:** Đóng gói hai bản của một shared API trong host và plugin ở production dễ tạo type identity mismatch. Bản trùng ở đây chỉ phục vụ mục đích chẩn đoán.

### 4.3 Class của plugin

**plugin-src/sample/plugin/Greeter.java**:

~~~java
package sample.plugin;

import sample.host.HostApi;

public final class Greeter {
    static {
        System.out.println("plugin initialized");
    }

    public String greet() {
        return "hello from " + HostApi.origin();
    }
}
~~~

Greeter phụ thuộc vào HostApi. Nó cũng có static initializer để chứng minh **loadClass chưa tự kích hoạt khởi tạo class**, còn reflective instance creation sẽ kích hoạt.

**Biên dịch quan trọng:** Greeter được compile chống lại HostApi của host, nhưng khi JVM nạp **binary name sample.host.HostApi** ở runtime, loader resolution và parent delegation mới quyết định Class nào được dùng trong trường hợp cụ thể. Vì hai bản HostApi có cùng public method signature, demo có thể gọi method mà không gặp NoSuchMethodError. Nếu API schema khác nhau, đây sẽ là một loại lỗi cần điều tra riêng.

## 5. Chương trình chính: in cây loader và từng nguồn Class

Tạo **src/sample/app/InspectLoaders.java** với nội dung đầy đủ:

~~~java
package sample.app;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.ProtectionDomain;
import java.sql.DriverManager;
import java.util.Enumeration;

public final class InspectLoaders {
    private static String role(
            ClassLoader loader, ClassLoader plugin) {
        if (loader == null) {
            return "bootstrap";
        }
        if (loader == plugin) {
            return "plugin-loader";
        }
        if (loader == ClassLoader.getSystemClassLoader()) {
            return "application";
        }
        if (loader == ClassLoader.getPlatformClassLoader()) {
            return "platform";
        }
        return "other";
    }

    private static void tree(
            ClassLoader loader, ClassLoader plugin) {
        System.out.println("Loader ancestry:");

        int depth = 0;
        while (true) {
            System.out.println("  ".repeat(depth)
                    + role(loader, plugin));

            if (loader == null) {
                break;
            }

            loader = loader.getParent();
            depth++;
        }
    }

    private static String source(
            Class<?> c, Path host, Path jar) throws Exception {
        ProtectionDomain pd = c.getProtectionDomain();
        CodeSource cs =
                pd == null ? null : pd.getCodeSource();

        URL url = cs == null ? null : cs.getLocation();

        if (url == null) {
            return "unavailable";
        }

        // Fixture dùng URL file: từ thư mục hoặc JAR.
        Path actual = Path.of(url.toURI()).toRealPath();

        if (actual.equals(host.toRealPath())) {
            return "host-out";
        }
        if (actual.equals(jar.toRealPath())) {
            return "plugin.jar";
        }
        return "other";
    }

    public static void main(String[] args)
            throws Exception {

        Path host = Path.of("host-out");
        Path jar = Path.of("plugin.jar");
        URL jarUrl = jar.toUri().toURL();

        ClassLoader app =
                ClassLoader.getSystemClassLoader();

        try (URLClassLoader plugin =
                    new URLClassLoader(
                            "plugin-loader",
                            new URL[]{jarUrl},
                            app);
             URLClassLoader plugin2 =
                    new URLClassLoader(
                            "plugin-loader-2",
                            new URL[]{jarUrl},
                            app)) {

            tree(plugin, plugin);

            System.out.println("String loader = "
                    + role(String.class.getClassLoader(),
                           plugin));

            System.out.println("DriverManager loader = "
                    + role(DriverManager.class.getClassLoader(),
                           plugin));

            System.out.println("HostApi loader = "
                    + role(sample.host.HostApi.class
                            .getClassLoader(), plugin));

            Class<?> type =
                    plugin.loadClass("sample.plugin.Greeter");

            System.out.println("Greeter loader = "
                    + role(type.getClassLoader(), plugin));

            System.out.println("Greeter source = "
                    + source(type, host, jar));

            System.out.println("HostApi source = "
                    + source(sample.host.HostApi.class,
                             host, jar));

            Class<?> shared =
                    plugin.loadClass("sample.host.HostApi");

            System.out.println("shadow selected = "
                    + (shared == sample.host.HostApi.class));

            System.out.println("Greeter named module = "
                    + type.getModule().isNamed());

            System.out.println("String module = "
                    + String.class.getModule().getName());

            System.out.println("plugin class resource scheme = "
                    + type.getResource("Greeter.class")
                            .getProtocol());

            Enumeration<URL> paths = plugin.getResources(
                    "sample/host/HostApi.class");

            int n = 0;
            while (paths.hasMoreElements()) {
                paths.nextElement();
                n++;
            }

            System.out.println("shadow resource count = " + n);

            Class<?> again =
                    plugin.loadClass("sample.plugin.Greeter");

            System.out.println("same loader cache = "
                    + (type == again));

            Class<?> parallel =
                    plugin2.loadClass("sample.plugin.Greeter");

            System.out.println("second loader same Class = "
                    + (type == parallel));

            System.out.println("before instance");

            Object obj =
                    type.getConstructor().newInstance();

            System.out.println("greeting = "
                    + type.getMethod("greet").invoke(obj));
        }
    }
}
~~~

Đây là **chương trình độc lập hoàn chỉnh** trong package sample.app. Các method được tách để dễ hiểu khi debug.

### 5.1 Vì sao role() so object identity?

Code dùng:

~~~java
if (loader == ClassLoader.getSystemClassLoader()) {
    return "application";
}
~~~

thay vì so **loader.toString()** hoặc **loader.getClass().getName()**. Tên implementation của built-in loaders và identity hash thường thay đổi theo JVM/version; **so sánh identity object** đáng tin hơn để biết loader có phải đúng system/platform object trong chính tiến trình không.

**role() chỉ tạo nhãn cho demo.** Nếu runtime dùng thêm một loader tùy biến khác, nó có thể in **other**, không có nghĩa class lỗi. Với công cụ chẩn đoán production nên in cả **ClassLoader.getName()**, loại implementation và một định danh instance ổn định trong cùng tiến trình.

### 5.2 Vì sao dùng vòng lặp tree()?

~~~java
ClassLoader current = plugin;

while (true) {
    // In current.
    if (current == null) {
        break;
    }
    current = current.getParent();
}
~~~

Đây là snippet minh họa, không phải method hoàn chỉnh. Nó duyệt **parent chain** đến null. Với loader hierarchy hợp lệ, chuỗi parent hữu hạn.

**Không tạo một đối tượng BootstrapClassLoader Java giả.** Null là biểu diễn hữu dụng trong kết quả API của các platform JVMs như HotSpot.

Nếu cần tool tổng quát cho nhiều custom loaders, có thể giới hạn depth và thêm phát hiện cycle phòng trường hợp biểu diễn tùy biến không như giả định. Tuy nhiên, quan hệ parent của ClassLoader được thiết lập khi constructor chạy; thường không phải đồ thị người dùng tự sửa để tạo cycle.

### 5.3 getParent() khác loadClass()

**getParent()** chỉ trả thông tin về quan hệ loader; nó **không gọi loadClass()** hay nạp class. Đọc cây loader không tự khởi tạo Greeter.

**ClassLoader.loadClass(name)** mặc định kiểm tra class đã loaded, hỏi parent trước, rồi gọi findClass nếu parent không tìm thấy. Custom loaders có thể thay đổi chính sách này, vì thế một cây parent giống nhau **chưa đủ bảo đảm hành vi lookup giống nhau**.

### 5.4 CodeSource lấy từ đâu?

Method **source(c, host, jar)** sử dụng:

~~~java
ProtectionDomain pd = c.getProtectionDomain();
CodeSource cs = pd == null ? null : pd.getCodeSource();
URL url = cs == null ? null : cs.getLocation();
~~~

Các lệnh là snippet trong method.

**CodeSource.getLocation()** có thể trỏ đến một thư mục classes hoặc file JAR. Trong demo:

- HostApi từ **host-out/** → CodeSource location tương ứng thư mục host-out.
- Greeter do URLClassLoader đọc từ **plugin.jar** → location là file URL trỏ đến plugin.jar.

**CodeSource hoặc location có thể null**, đặc biệt với bootstrap/JDK classes, bytes được tự định nghĩa/custom code domains hoặc security/runtime contexts. Vì vậy không được tự gọi **.getLocation().toString()** mà bỏ null-check.

Method demo dùng **Path.of(url.toURI()).toRealPath()** vì biết trước hai nguồn hợp lệ là **file:** paths. Đây **không phải bộ chuyển đổi URL tổng quát**: URL có protocol **jrt:, jar:, http:** hoặc custom handler có thể không chuyển thành Path trực tiếp được.

### 5.5 Tại sao resource URL khác CodeSource?

Có hai câu hỏi khác nhau:

~~~java
type.getProtectionDomain()
        .getCodeSource().getLocation();
~~~

và:

~~~java
type.getResource("Greeter.class");
~~~

Dòng đầu hỏi **vị trí code source của class** do protection domain ghi nhận. Với URLClassLoader đọc từ JAR, nó thường là **file:/.../plugin.jar**.

Dòng thứ hai tìm **resource tương ứng class file**; với class nằm trong JAR, URL thường có dạng:

~~~text
jar:file:/.../plugin.jar!/sample/plugin/Greeter.class
~~~

Nó chứa đường entry trong JAR và có **protocol = jar**. Địa chỉ thật phụ thuộc đường filesystem, nên chương trình chỉ in protocol để kết quả dễ tái hiện.

**Lưu ý:** Class.getResource và ClassLoader.getResource không hoàn toàn có cùng quy tắc xử lý path: **Class.getResource("Greeter.class")** giải quyết tương đối theo package của class; **ClassLoader.getResource("sample/plugin/Greeter.class")** dùng absolute resource name với dấu slash giữa các segments, **không bắt đầu bằng /**.

### 5.6 Vì sao gọi getResources chứ không chỉ getResource?

Program gọi:

~~~java
plugin.getResources("sample/host/HostApi.class")
~~~

và đếm được **2** resource URLs: một từ **host-out**, một từ **plugin.jar**. Đây là dấu hiệu *có hai resources cùng path*, không phải JVM đã define hai Class HostApi trong cùng loader.

**getResource** thường dùng chính sách parent-first: parent resource có thể thắng. **getResources** có thể liệt kê nhiều URLs; trong ứng dụng thực sự còn cần xét duplicate entries, module encapsulation, custom resource delegation và launcher environment.

**Đừng kết luận “resource count = 2” đồng nghĩa “Class count = 2”.** Class identity chỉ được xác lập khi JVM định nghĩa Class theo loader, không phải khi JAR có một entry tương ứng.

## 6. Biên dịch và đóng gói

Đứng ở thư mục **loader-tree-lab** và tạo đủ các source files trên, thực hiện:

~~~bash
javac --release 17 -d host-out   src/sample/host/HostApi.java   src/sample/app/InspectLoaders.java

javac --release 17 -cp host-out -d plugin-out   plugin-src/sample/plugin/Greeter.java

javac --release 17 -d plugin-out   plugin-src/sample/host/HostApi.java

jar --create --file plugin.jar -C plugin-out .

java -cp host-out sample.app.InspectLoaders
~~~

Đây là lệnh nhiều dòng dùng **backslash** nối dòng phù hợp với bash trên Linux/macOS. Với Windows PowerShell, dùng một dòng cho mỗi lệnh:

~~~powershell
javac --release 17 -d host-out src/sample/host/HostApi.java src/sample/app/InspectLoaders.java
javac --release 17 -cp host-out -d plugin-out plugin-src/sample/plugin/Greeter.java
javac --release 17 -d plugin-out plugin-src/sample/host/HostApi.java
jar --create --file plugin.jar -C plugin-out .
java -cp host-out sample.app.InspectLoaders
~~~

**Tại sao compile Greeter trước bản HostApi của plugin?** Để nó được compile chống lại API của host qua **-cp host-out**. Sau đó ta bổ sung bản HostApi khác vào plugin-out và đóng gói. Trình biên dịch ghi symbolic reference tới **sample.host.HostApi**, còn defining loader của HostApi được JVM lựa chọn lúc runtime.

**Quan trọng về classpath:** Chỉ đưa **host-out** vào application classpath khi chạy chương trình. Không thêm **plugin.jar** vào application classpath trong lệnh demo chính; nếu thêm, application parent có thể tự load Greeter trước và phép thử ownership thay đổi.

**Vì sao dùng --release 17?** Đây là một chương trình Java 17+; dùng --release 17 giúp bytecode/class-file target tương thích Java 17 ngay cả khi biên dịch bằng JDK 21. Constructor **URLClassLoader(String name, URL[] urls, ClassLoader parent)** có từ Java 9 nên hợp lệ.

## 7. Output thực tế và giải thích từng dòng

Đây là **stdout đã kiểm chứng trên OpenJDK 21** với source tree và lệnh chạy như trên:

~~~text
Loader ancestry:
plugin-loader
  application
    platform
      bootstrap
String loader = bootstrap
DriverManager loader = platform
HostApi loader = application
Greeter loader = plugin-loader
Greeter source = plugin.jar
HostApi source = host-out
shadow selected = true
Greeter named module = false
String module = java.base
plugin class resource scheme = jar
shadow resource count = 2
same loader cache = true
second loader same Class = false
before instance
plugin initialized
greeting = hello from host
~~~

### 7.1 Dòng đầu: cây loader

~~~text
plugin-loader
  application
    platform
      bootstrap
~~~

Ý nghĩa:

- Plugin URLClassLoader có **parent là application/system loader**.
- System loader có **parent là platform loader** trong môi trường thử nghiệm.
- Platform loader có parent được biểu diễn bằng **null/bootstrap**.
- Độ thụt đầu dòng chỉ là phần code **"  ".repeat(depth)**, không phải tính năng vẽ cây của JVM.

**Đây không phải toàn bộ loaders đang tồn tại trong JVM.** Chương trình chỉ in parent chain bắt đầu từ **plugin**, không quét các loaders khác do JVM/framework đã tạo.

### 7.2 String và DriverManager

~~~text
String loader = bootstrap
DriverManager loader = platform
~~~

**java.lang.String** thuộc các core platform classes do bootstrap loader định nghĩa trên OpenJDK. **java.sql.DriverManager** được platform loader định nghĩa trong JVM thử nghiệm, cho một ví dụ platform class không phải bootstrap.

Một JVM khác có thể có mapping chi tiết không hoàn toàn giống; đừng viết assertion portable kiểu “mọi JDK phải có DriverManager loader là platform” trừ khi môi trường chạy đã được kiểm soát và xác nhận.

### 7.3 HostApi thuộc application

~~~text
HostApi loader = application
HostApi source = host-out
~~~

**HostApi.class** được compile và load từ **host-out**, do application loader. Đây là **Class object được host sử dụng để tham chiếu API chung**.

Trong demo, đối tượng application loader chính là parent của plugin, nên khi plugin yêu cầu tên này, parent đã nhìn thấy class.

### 7.4 Greeter thuộc plugin.jar

~~~text
Greeter loader = plugin-loader
Greeter source = plugin.jar
~~~

Application parent không có **sample.plugin.Greeter**, vì plugin.jar không nằm trên application classpath. URLClassLoader plugin tìm class trong URL duy nhất là plugin.jar và tự định nghĩa Greeter.

**getClassLoader() và CodeSource hỗ trợ lẫn nhau:**

- getClassLoader cho biết **ai định nghĩa**.
- CodeSource cho biết **nguồn artifact được ghi nhận**.
- Không thể hoán đổi vai trò của hai API; hai loaders khác nhau có thể đọc cùng một JAR và tạo hai Class khác nhau.

### 7.5 Plugin có bản trùng HostApi nhưng không được chọn

~~~text
shadow selected = true
greeting = hello from host
~~~

Ở đây biến **shadow selected** là tên in để kiểm tra **plugin.loadClass("sample.host.HostApi")** có trả chính Class HostApi của host hay không. Giá trị **true** nghĩa **parent/host thắng**, không phải plugin-shadow thắng.

Dòng **greeting = hello from host** chứng minh code Greeter đã gọi đúng implementation HostApi của host. Bản **plugin-shadow** nằm trong plugin.jar nhưng không phải class được chọn cho lookup này.

Đây là **parent-first delegation** phù hợp với mặc định ClassLoader.loadClass. Đừng sửa thông báo thành “plugin-shadow selected = true” vì nó sẽ làm người học hiểu ngược kết quả.

### 7.6 Module information

~~~text
Greeter named module = false
String module = java.base
~~~

Greeter được định nghĩa từ JAR qua URLClassLoader trong **unnamed module** của loader plugin, vì demo không dùng module-info.java hoặc JPMS ModuleLayer.

String thuộc **named module java.base**. ClassLoader identity và module membership là hai lớp thông tin khác nhau: một loader có thể định nghĩa nhiều named modules theo module layer, nhưng trong fixture này Greeter ở unnamed module.

**Class.getModule() không cho biết JAR filename**. Dùng CodeSource hoặc resource URL để điều tra artifact.

### 7.7 Một loader dùng lại class đã nạp

~~~text
same loader cache = true
~~~

Hai lời gọi **plugin.loadClass("sample.plugin.Greeter")** trả cùng Class object. Thuật toán ClassLoader.loadClass mặc định kiểm tra class đã loaded/initiated và không gọi defineClass lần hai cho cùng name.

Nếu một custom loader cố define class trùng trong cùng loader, có thể ném **LinkageError**, chứ không phải tạo một bản cập nhật method body.

### 7.8 Hai loader cùng JAR tạo hai Class khác nhau

~~~text
second loader same Class = false
~~~

**plugin** và **plugin2** đều có URL trỏ đến cùng **plugin.jar**, nhưng là **hai URLClassLoader objects khác nhau**. Khi mỗi loader tự định nghĩa sample.plugin.Greeter, ta có hai Class objects khác runtime identity.

Khi ứng dụng plugin cần cast object về shared interface, interface/DTO thường nên đến từ **một defining loader chung**. Nếu plugin2 tự define một bản interface API trùng tên với host, cast có thể thất bại dù source giống nhau.

### 7.9 loadClass chưa chạy static initializer

~~~text
before instance
plugin initialized
greeting = hello from host
~~~

Chương trình gọi loadClass, kiểm tra Class/CodeSource/Resource rồi in **before instance**. Chỉ khi:

~~~java
type.getConstructor().newInstance();
~~~

được thực hiện, Greeter mới bị khởi tạo, static block chạy và in **plugin initialized**.

**Loading không đồng nghĩa initialization**. Cờ resolve trong ClassLoader cũng không phải yêu cầu tự chạy class initializer; chỉ active use theo JLS mới kích hoạt initialization phù hợp.

## 8. Bài thực hành thứ hai: cùng JAR nhưng thay parent

Mục tiêu: thay đúng một yếu tố **parent loader** và quan sát kết quả. Lần này custom URLClassLoader có parent là **platform loader**, không phải application loader.

Vì platform loader không thấy **host-out** trong fixture, child có thể tự định nghĩa **sample.host.HostApi** bản đóng trong plugin.jar.

Tạo **src/sample/app/IsolatedLoaderDemo.java**:

~~~java
package sample.app;

import java.net.URLClassLoader;
import java.net.URL;
import java.nio.file.Path;
import sample.host.HostApi;

public class IsolatedLoaderDemo {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("plugin.jar").toUri().toURL();

        try (URLClassLoader isolated =
                new URLClassLoader(
                        "isolated",
                        new URL[]{jar},
                        ClassLoader.getPlatformClassLoader())) {

            Class<?> shadow =
                    isolated.loadClass("sample.host.HostApi");

            Class<?> greeter =
                    isolated.loadClass("sample.plugin.Greeter");

            System.out.println(
                    "host and isolated HostApi same = "
                    + (shadow == HostApi.class));

            System.out.println(
                    "shadow owner is isolated = "
                    + (shadow.getClassLoader() == isolated));

            System.out.println(
                    "greeter owner is isolated = "
                    + (greeter.getClassLoader() == isolated));

            Object g =
                    greeter.getConstructor().newInstance();

            System.out.println(
                    "greeting = "
                    + greeter.getMethod("greet").invoke(g));
        }
    }
}
~~~

Biên dịch/chạy từ thư mục project:

~~~bash
javac --release 17 -cp host-out -d host-out   src/sample/app/IsolatedLoaderDemo.java

java -cp host-out sample.app.IsolatedLoaderDemo
~~~

Windows PowerShell dùng một dòng javac:

~~~powershell
javac --release 17 -cp host-out -d host-out src/sample/app/IsolatedLoaderDemo.java
java -cp host-out sample.app.IsolatedLoaderDemo
~~~

**Stdout đã chạy trên OpenJDK 21:**

~~~text
host and isolated HostApi same = false
shadow owner is isolated = true
greeter owner is isolated = true
plugin initialized
greeting = hello from plugin-shadow
~~~

### 8.1 Vì sao khác chương trình đầu?

Trong chương trình đầu:

~~~text
PluginLoader -> ApplicationLoader -> Platform -> Bootstrap
                   |
                   +-- biết HostApi từ host-out
~~~

Trong chương trình thứ hai:

~~~text
IsolatedLoader -> Platform -> Bootstrap
      |
      +-- tự tìm HostApi trong plugin.jar
~~~

Vì application loader **không nằm trên parent chain của isolated**, việc code launcher dùng **HostApi.class** từ host-out không làm isolated bắt buộc lấy Class đó.

**Class equality = false** phản ánh hai defining loaders khác nhau: application loader và isolated loader.

**Kết quả "plugin-shadow"** cho thấy Greeter trong isolated dùng HostApi bản đóng trong plugin.jar.

### 8.2 Không nhầm parent platform với “full sandbox”

Việc chọn platform làm parent giúp minh họa cô lập class lookup, **không phải security sandbox**. Plugin có thể truy cập những Java APIs mà runtime/module constraints cho phép. Nếu chạy code không tin cậy, cần một mô hình isolation khác (ví dụ process/container sandbox) với quyền hạn phù hợp.

Nếu plugin cần gọi host API, chuyển parent sang platform có thể làm shared API không còn visible. Ví dụ thứ hai chạy được vì plugin.jar có bản HostApi của riêng nó; trong thực tế điều này có thể dẫn đến **ClassCastException/LinkageError** khi host-plugin boundary yêu cầu cùng Class identity.

## 9. Đọc CodeSource một cách an toàn trong chương trình thật

CodeSource là một tín hiệu hữu ích nhưng **không phải lúc nào cũng có URL**.

### 9.1 Helper cho code production

~~~java
static String codeSourceLocation(Class<?> type) {
    try {
        java.security.ProtectionDomain pd =
                type.getProtectionDomain();

        if (pd == null) {
            return "(no protection domain)";
        }

        java.security.CodeSource cs = pd.getCodeSource();

        if (cs == null || cs.getLocation() == null) {
            return "(no code source URL)";
        }

        return cs.getLocation().toExternalForm();

    } catch (SecurityException denied) {
        return "(access denied)";
    }
}
~~~

Đây là **method hoàn chỉnh** có thể đặt trong helper class, nhưng không có main riêng. Nó không tự động đọc/validate nội dung URL.

### 9.2 Khi nào CodeSource có thể khác mong đợi?

- **Bootstrap/JDK classes:** CodeSource thường không phải URL file JAR thông thường.
- **Custom ClassLoader dùng defineClass với ProtectionDomain tùy chỉnh:** Có thể không có location, hoặc location do loader đặt.
- **In-memory generated classes, proxies, hidden classes:** Nguồn vật lý có thể không tồn tại dưới dạng .class ở thư mục/JAR mà bạn trỏ được.
- **Named modules/runtime image:** Location có thể dùng **jrt:** hoặc không có source URL theo cách bạn mong đợi.
- **Container/nested JAR/custom URL protocols:** URL có thể biểu diễn vị trí logic thay vì Path file đơn giản.
- **Security policy:** Quyền truy cập ProtectionDomain/CodeSource có thể bị giới hạn tùy runtime.

**Không dùng CodeSource thay cơ chế xác thực file.** Nó là metadata liên quan protection domain, không phải bằng chứng cryptographic rằng bytes xuất phát từ artifact đã ký và đáng tin.

### 9.3 Không in đường dẫn bí mật ra production logs

CodeSource location có thể chứa đường dẫn home, build workspace, container mount, mạng hoặc URL nội bộ. Với bài thực hành ta chuẩn hóa thành **host-out/plugin.jar** để stdout ổn định. Với logs production, cân nhắc quyền truy cập và mức thông tin được phép xuất.

## 10. Resource lookup: thấy class file không có nghĩa Class đã được nạp

Hai API:

~~~java
ClassLoader loader = Greeter.class.getClassLoader();
java.net.URL url =
        loader.getResource("sample/plugin/Greeter.class");
~~~

Đây là snippet không độc lập và cần lớp Greeter visible ở compile-time. Nó tìm **resource URL**, không phải trả Class<?>.

**Sự khác nhau:**

| API | Trả về | Ý nghĩa |
| --- | --- | --- |
| **clazz.getClassLoader()** | ClassLoader hoặc null | Defining loader của runtime Class. |
| **clazz.getModule()** | Module | Named/unnamed module của Class. |
| **clazz.getProtectionDomain().getCodeSource()** | CodeSource hoặc null | Metadata nguồn/protection domain. |
| **clazz.getResource("X.class")** | URL hoặc null | Tìm resource tương đối với package của clazz. |
| **loader.getResource("p/X.class")** | URL hoặc null | Tìm resource theo tên /-separated qua loader. |
| **loader.getResources("p/X.class")** | Enumeration URL | Các resource matches có thể gồm parent và child. |
| **loader.loadClass("p.X")** | Class<?> | Tìm runtime class theo binary name. |

**Lưu ý JPMS:** Đối với resources trong named modules, **ClassLoader.getResource** còn có quy tắc package openness/encapsulation. Đừng giả định mọi resource bên trong named module đều được trả về chỉ vì JAR có entry ấy. Class.getResource có ngữ nghĩa module-aware riêng.

**Kiểm tra được đường dẫn không có nghĩa loadClass sẽ tự dùng đúng resource URL ấy:** URLClassLoader parent-first có thể chọn Class của parent mặc dù plugin JAR cũng chứa resource cùng tên.

## 11. In cây nhiều loaders trong ứng dụng phức tạp

Nếu hệ thống có nhiều plugin loaders, có thể ghi nhận từng loader theo một cấu trúc:

~~~text
Name: plugin-A
  implementation: java.net.URLClassLoader
  parent: application
  known artifact URL: file:/.../pluginA.jar
  class sample.plugin.PluginA:
      defining loader = plugin-A
      module = unnamed
      code source = pluginA.jar

Name: plugin-B
  implementation: java.net.URLClassLoader
  parent: application
  known artifact URL: file:/.../pluginB.jar
  class sample.plugin.PluginB:
      defining loader = plugin-B
      module = unnamed
      code source = pluginB.jar
~~~

Đây là **mẫu báo cáo**, không phải stdout của fixture.

Với nhiều loaders, bạn cần:

1. Đặt **tên hoặc deployment ID** khi tạo loader.
2. Lưu **owner** (host/plugin manager) của loader.
3. Ghi parent chain cho loader mới.
4. In **Class.getClassLoader()** cho từng class quan trọng.
5. So sánh identity của shared APIs qua **==**.
6. Liên hệ CodeSource/resource URLs với expected artifacts.
7. Ghi module name, layer nếu dùng JPMS.
8. Kiểm soát lifecycle/close của URLClassLoader khi deployment dừng.

**Không duyệt JVM để liệt kê mọi loader bằng cách giả định mọi loader nằm dưới system loader.** Những loader có parent là bootstrap/platform hoặc peer delegation có thể không được tìm bằng cách đi từ system parent chain.

### 11.1 Hiển thị parent chain theo kiểu không phụ thuộc toString()

Nếu dùng output như:

~~~text
jdk.internal.loader.ClassLoaders$AppClassLoader@30946e09
~~~

đây là class name và identity hash liên quan JVM implementation. Nó hữu ích để phân biệt instance trong một process, nhưng không ổn định giữa các lượt chạy. Không nên viết integration tests so sánh nguyên văn hash hoặc implementation class name.

Có thể thêm một stable label riêng như **plugin-loader, plugin-loader-2, deployment-v1** và đối chiếu identity trong chương trình.

### 11.2 Thread Context ClassLoader là một trục khác

~~~java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();
~~~

TCCL không nhất thiết bằng loader định nghĩa class đang chạy. Frameworks như ServiceLoader có thể dùng TCCL để tìm providers và resources.

Nếu đang debug SPI không tìm thấy provider, **Class.getClassLoader của service type và TCCL** đều hữu ích, nhưng không thay thế class identity checks. Việc set TCCL tạm phải **restore previous** trong finally nếu thread thuộc host pool.

## 12. Chẩn đoán khi output khác dự kiến

### 12.1 Greeter loader là application, không phải plugin

Nguyên nhân thường là bạn vô tình đưa **plugin.jar** hoặc plugin-out vào application classpath:

~~~bash
# Không dùng cho expected demo output:
java -cp "host-out:plugin.jar" sample.app.InspectLoaders
~~~

Vì URLClassLoader parent-first, application loader thấy Greeter trước, nên plugin.loadClass trả class của parent. Trong trường hợp này **CodeSource** của Greeter có thể vẫn là plugin.jar nhưng **defining loader** không còn là plugin.

**Bài học:** artifact source giống không bảo đảm loader owner giống.

### 12.2 Greeter source = unavailable

Đừng vội kết luận class “không có file”. Có thể runtime sử dụng custom defineClass, in-memory bytes, không có CodeSource, hoặc security/module context che thông tin.

Kiểm tra defining loader, resource lookup, class loading logs và thiết kế ProtectionDomain của loader đó.

### 12.3 FileNotFoundException hoặc NoSuchFileException khi chạy

Ví dụ dùng đường **plugin.jar** và **host-out** tương đối với **current working directory**. Nếu chạy trong IDE với working directory khác, sẽ không tìm file.

Khắc phục: chạy ở project root hoặc đổi cấu hình working directory/absolute input paths. Đừng dựa vào classpath tự tìm file **plugin.jar** nếu Path.of("plugin.jar") đang tìm trực tiếp theo filesystem.

### 12.4 ClassNotFoundException: sample.plugin.Greeter

Kiểm tra:

~~~bash
jar --list --file plugin.jar
~~~

Phải có entry:

~~~text
sample/plugin/Greeter.class
~~~

Nếu không có, xem javac -d plugin-out và jar -C plugin-out. Nếu có, xác nhận plugin URL dùng đúng **Path.of("plugin.jar").toUri().toURL()**, class name dùng dấu chấm và parent delegation.

### 12.5 ClassCastException dù tên class trùng

Nếu hai URLClassLoaders tự define cùng binary name, **Class objects khác nhau**. Một instance do plugin loader thứ nhất tạo không tự động cast thành type do plugin2 define.

Với shared host-plugin contracts, đặt interface/DTO trong parent loader và tránh đóng bản sao vào child-first packages.

### 12.6 NoClassDefFoundError: sample/host/HostApi

Nếu dùng platform parent và plugin.jar **không còn bản HostApi** nhưng Greeter vẫn phụ thuộc nó, loader isolated không nhìn thấy HostApi của host-out. Có thể loader cần parent khác hoặc API package phải được cho phép delegate tới loader shared.

**Sửa kiến trúc API boundary** thay vì chỉ nuốt exception rồi trả Class không tương thích.

### 12.7 Output DriverManager loader khác platform

Quan sát này phụ thuộc runtime JDK. Kiểm tra vendor/version và built-in ClassLoader mapping. Bài demo vẫn đúng nếu Class được load bởi loader khác; chỉ cần sửa expected output cho đúng môi trường được hỗ trợ và không đồng nhất mọi platform classes với một loader cố định.

### 12.8 Nguồn resource là jar: nhưng CodeSource file:

Đây là điều thường gặp và bình thường:

~~~text
CodeSource: file:/.../plugin.jar
Resource:   jar:file:/.../plugin.jar!/sample/plugin/Greeter.class
~~~

CodeSource chỉ vị trí artifact; resource URL chỉ entry riêng bên trong JAR. Hai URL khác protocol không có nghĩa hai class versions.

### 12.9 Không thấy static initializer chạy khi loadClass

Theo JLS, class initialization là bước khác với loading. Ví dụ chỉ chạy initializer lúc reflective construction. Không dùng **getClassLoader()**, **getModule()** hoặc **getResource()** để khẳng định static initializer đã thực thi.

## 13. Bài kiểm thử từ ví dụ

Các assertions nên tập trung vào **tính chất**, không phải string hash của loaders:

~~~java
// Snippet trong scope có plugin, type và plugin2:
assert type.getClassLoader() == plugin;
assert plugin.loadClass("sample.host.HostApi")
        == sample.host.HostApi.class;
assert type != plugin2.loadClass(
        "sample.plugin.Greeter");
~~~

Để bật assert trong Java:

~~~bash
java -ea -cp host-out sample.app.InspectLoaders
~~~

Trong bài chính, các assertions không được thêm vào launcher, nhưng nếu bạn đưa snippet vào scope phù hợp, ba thuộc tính trên đúng theo setup đã hướng dẫn. Lưu ý **assert disabled mặc định** trừ khi có **-ea**, nên integration tests quan trọng thường dùng assertions của framework kiểm thử (JUnit) hoặc explicit checks không tùy thuộc JVM assertion flags.

### 13.1 Không kiểm thử bằng System.identityHashCode cố định

**System.identityHashCode(loader)** có thể hữu ích để gắn nhãn identity trong một lần chạy, nhưng giá trị cụ thể không ổn định giữa processes. So **==** khi cùng JVM, và log thêm deployment ID có nghĩa với nghiệp vụ.

### 13.2 Kiểm thử Source location

Với fixture này, code dùng **toRealPath** để so CodeSource với host-out và plugin.jar, tránh khác biệt relative/absolute path của cùng file.

Trên Windows, nếu directory case, symlinks, permissions hoặc file layout khác, Path equality có thể cần xử lý phù hợp. Đây là **code fixture** cho hai file URLs, không phải một phép xác thực nguồn lớp có thể dùng cho mọi protocol.

## 14. Mở rộng thực hành

### Bài tập A — thêm một class chỉ có trong plugin JAR

Tạo một class mới **sample.plugin.Helper**, compile vào plugin-out rồi đóng lại plugin.jar. In:

~~~java
Class<?> helper =
        plugin.loadClass("sample.plugin.Helper");

System.out.println(helper.getClassLoader() == plugin);
~~~

Dự kiến **true** nếu parent không thấy class đó và loader plugin còn mở. Đặt code trong scope có URLClassLoader plugin của InspectLoaders.

### Bài tập B — quan sát CodeSource không có URL

Trong main, in:

~~~java
System.out.println(
        String.class.getProtectionDomain()
                .getCodeSource());
~~~

Kết quả có thể null hoặc dạng runtime-specific. Đừng viết exact-output assertion portable. Trong application thật, null-check ProtectionDomain trước nếu cần.

### Bài tập C — thêm plugin.jar vào application classpath

Chạy thử launcher với plugin.jar bổ sung vào classpath. Quan sát **Greeter loader**, **Class identity**, static initializer và **resource counts**; so với lần chạy plugin.jar chỉ nằm ở URLClassLoader.

**Giải thích:** Parent-first khiến application loader có thể định nghĩa Greeter, dù chương trình vẫn gọi plugin.loadClass. Tuy nhiên output **source = plugin.jar** vẫn có thể giống nhau. Đây là minh họa rõ rằng **source artifact và defining loader** là hai trục riêng.

### Bài tập D — tạo hai phiên bản plugin.jar

Đóng gói Greeter method trả hai kết quả khác nhau dưới hai JAR URLs, tạo loader riêng cho từng JAR, rồi so **Class identity** và kết quả method. Không cố redefine Greeter trong cùng loader bằng defineClass lần thứ hai. Khi cần hot reload, tạo loader mới và quản lý lifecycle.

### Bài tập E — in module name/unnamed module

Kiểm tra:

~~~java
System.out.println(type.getModule().isNamed());
System.out.println(type.getModule().getName());
~~~

Với URLClassLoader thường trên classpath-style JAR của fixture, output là **false** rồi **null** vì Greeter ở unnamed module. Với **String.class**, **getModule().getName()** là **java.base**.

### Bài tập F — đối chiếu ClassLoader.getResource và Class.getResource

Dùng resource path **sample/plugin/Greeter.class** cho ClassLoader và **Greeter.class** cho Class.getResource tương đối package. In protocols và kiểm tra có cùng entry theo logic hay không.

Không thêm dấu slash đầu vào **ClassLoader.getResource** theo cách tùy tiện, vì tên resource của ClassLoader theo contract dùng /-separated path không có slash đầu.

## 15. Câu hỏi tự kiểm tra

**1.** Trong HotSpot, tại sao **String.class.getClassLoader()** trả null?

**Đáp án:** Bootstrap loader là loader tích hợp JVM và thường được biểu diễn bằng null, không phải do String chưa được nạp.

**2.** **getParent()** có liệt kê toàn bộ loaders hiện có trong JVM không?

**Đáp án:** Không. Nó đi theo parent chain từ loader đang xét, không phải danh sách toàn bộ loader objects.

**3.** Một ClassLoader được gọi **loadClass** có chắc là defining loader của Class trả về không?

**Đáp án:** Không. Nó có thể delegate sang parent và chỉ là initiating loader trong ngữ cảnh liên quan.

**4.** API nào trả defining loader?

**Đáp án:** **Class.getClassLoader()** (có thể null cho bootstrap classes).

**5.** API nào cho code source location của Class?

**Đáp án:** **Class.getProtectionDomain().getCodeSource().getLocation()**, với null-check từng bước.

**6.** Parent và plugin JAR cùng có HostApi. Tại sao bản host thắng trong demo đầu?

**Đáp án:** URLClassLoader mặc định parent-first và có application loader làm parent, nơi HostApi đã có trên classpath.

**7.** Vì sao getResources tìm được hai **HostApi.class** URLs nhưng plugin.loadClass chỉ trả một Class object?

**Đáp án:** Resource lookup có thể liệt kê cả hai files; class lookup tuân theo delegation và trả một Class đã được định nghĩa/chọn, không define mỗi resource thành một Class.

**8.** **CodeSource** và **Class.getResource** có luôn cùng URL không?

**Đáp án:** Không. Một cái có thể là file:/.../plugin.jar, cái kia là jar:file:/.../plugin.jar!/path/Class.class.

**9.** Hai URLClassLoader mới cùng đọc một plugin.jar. Tại sao Greeter Class equality false?

**Đáp án:** Defining loader khác, nên hai runtime Class identities khác nhau.

**10.** **loadClass** có chạy static initializer không?

**Đáp án:** Không tự làm vậy. Initialization xảy ra theo các quy tắc active use khác, ví dụ tạo instance bằng reflection trong demo.

**11.** Loader isolated dùng parent platform nạp HostApi bản nào?

**Đáp án:** Nó nạp bản trong plugin.jar, vì platform parent không thấy bản của host-out trong fixture.

**12.** Một JAR có class đó nhưng chương trình vẫn báo ClassNotFoundException — cần kiểm tra gì?

**Đáp án:** Đúng binary name, đúng path trong JAR, URL tạo loader, parent delegation, loader đã close chưa, module encapsulation và runtime classpath/module path.

**13.** Có thể xác nhận Class bị unload chỉ bằng việc đóng URLClassLoader và gọi getClassLoader trước đó không?

**Đáp án:** Không. URLClassLoader.close chỉ đóng khả năng tìm class/resources mới của chính loader và tài nguyên do nó sở hữu; existing Class/instances vẫn có thể sống cho đến khi không còn strong references và JVM unload sau đó.

**14.** Khi log toàn bộ CodeSource URL, rủi ro gì?

**Đáp án:** Có thể lộ đường filesystem hoặc hạ tầng nội bộ; đồng thời URL không phải bảo đảm mật mã về nguồn class thực sự đáng tin.

## 16. Tóm tắt thực hành

~~~text
Tạo host-out chứa HostApi
               |
               v
Tạo plugin.jar chứa Greeter + HostApi trùng tên
               |
               v
AppLoader (parent) ------> HostApi bản host
               ^
               |
Plugin URLClassLoader ---> Greeter từ plugin.jar
               |
               +-- hỏi HostApi -> parent thắng
               |
               +-- class resource URLs có thể có 2 bản
               |
               v
Class.getClassLoader() => WHO defined?
Class.getModule()      => IN WHICH module?
CodeSource location    => SOURCE artifact metadata?
Class.getResource()    => RESOURCE entry URL?
ClassLoader.getParent()=> PARENT chain?
               |
               v
Tạo URLClassLoader khác cho plugin.jar
               |
               v
Greeter Class identity khác
~~~

**Ghi nhớ:**

- **Cây loader** giải thích parent relationships, không đầy đủ runtime graph.
- **Class.getClassLoader()** là cách trực tiếp hỏi defining loader của Class object.
- **CodeSource và resource URL** hỗ trợ tìm artifact nhưng không thay thông tin loader identity.
- **Parent-first** có thể khiến class thực sự lấy từ host ngay cả khi plugin JAR có file cùng tên.
- **Hai loader đọc cùng một JAR vẫn có thể tạo hai Class khác nhau**.
- **loadClass không tự initialize class**; active use như newInstance mới khiến static initializer trong fixture chạy.
- Khi chẩn đoán ứng dụng thật, in đồng thời **loader identity, module, CodeSource, resource URL và class-loading logs** thay vì chỉ nhìn tên class.

### Tài liệu tham khảo chính thức

- Java SE 21 **ClassLoader API** (getParent, loadClass, getResource, getSystemClassLoader): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 21 **URLClassLoader API** (constructors, class/resource loading, close): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 21 **Class API** (getClassLoader/getModule/getProtectionDomain/getResource): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- Java SE 21 **ProtectionDomain API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html
- Java SE 21 **CodeSource API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html
- Java SE 21 **JLS §12.2: Loading Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2
- Java SE 21 **JVMS §5.3: Creation and Loading**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3

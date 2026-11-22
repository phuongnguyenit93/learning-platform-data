# System Class Loader và Application Class Loader trong Java

## 1. Mục tiêu và câu trả lời cốt lõi

Khi học về các **class loader tích hợp** của Java, hai cách gọi dễ gây nhầm lẫn là **system class loader** và **application class loader (app class loader)**. Trong cách chạy ứng dụng phổ biến trên OpenJDK/HotSpot từ Java 9 trở lên, chúng **thường chỉ cùng một loader**: loader ứng dụng tích hợp, chịu trách nhiệm nạp nhiều lớp của ứng dụng, đặc biệt là các lớp trên **application class path**.

Tuy nhiên, đây không phải hai thuật ngữ luôn đồng nghĩa trong mọi cấu hình:

- **System class loader** nhấn mạnh **vai trò do API JVM/JDK công bố**: đối tượng được trả về bởi `ClassLoader.getSystemClassLoader()`. Nhiều API tĩnh như `ClassLoader.getSystemResource(...)` sử dụng loader hệ thống này.
- **Application class loader** nhấn mạnh **loader tích hợp của môi trường chạy tiêu chuẩn** thường nạp lớp của ứng dụng. Trong cách triển khai OpenJDK hiện đại, tên lớp triển khai thường có hậu tố `AppClassLoader`, nhưng đây là **chi tiết triển khai**, không phải tên kiểu công khai bảo đảm bởi Java SE.
- Nếu ứng dụng chỉ định thuộc tính khởi động `java.system.class.loader`, JVM có thể dùng **một class loader tùy chỉnh** làm system class loader. Khi đó không nên kết luận “system loader = đối tượng AppClassLoader mặc định”.
- Một ứng dụng có thể dùng thêm nhiều **custom class loader** cho plugin, ứng dụng web, bộ kiểm thử, module động hoặc cơ chế hot reload. Những lớp do loader con định nghĩa không nhất thiết được định nghĩa bởi system loader.

Bài học này tập trung vào vai trò, API, quan hệ ủy quyền, class path/module path, quan sát thực nghiệm và cách debug hai khái niệm trên ở Java 17+.

## 2. Vị trí của Application/System Loader trong các loader tích hợp

Trong môi trường JDK 17 thông thường, chuỗi parent delegation có thể hình dung như sau:

~~~text
Bootstrap Class Loader                (được biểu diễn bằng null trong nhiều API)
         ↑  được ủy quyền tìm lớp trước
Platform Class Loader                 ClassLoader.getPlatformClassLoader()
         ↑
Application Class Loader              thường = ClassLoader.getSystemClassLoader()
         ↑
Custom Child Class Loader             nếu chương trình tạo và đặt parent thích hợp
~~~

Mũi tên biểu thị **quan hệ parent và đường ủy quyền mặc định**, không phải “lớp con” trong hệ thống kế thừa Java. Class loader là đối tượng Java (trừ bootstrap được JVM triển khai theo cơ chế riêng). Quan hệ parent của class loader cũng **không đồng nghĩa** quan hệ `extends` của các lớp mà nó định nghĩa.

### Bootstrap loader

Bootstrap loader phụ trách nhiều lớp lõi của Java runtime, ví dụ `java.lang.String` trong JDK thông thường. Khi gọi `String.class.getClassLoader()`, kết quả thường là **null** để biểu diễn bootstrap loader; null không có nghĩa là lớp chưa được load.

### Platform loader

Từ Java 9, **platform class loader** thay vai trò tên gọi trước đây của extension class loader (`ExtClassLoader`). Lấy bằng `ClassLoader.getPlatformClassLoader()`; trong cấu hình JDK 17 chuẩn, parent của nó là bootstrap loader. Nó liên quan đến các module thuộc nền tảng Java và việc ủy quyền nạp lớp theo cơ chế module hiện đại. Không dùng sơ đồ Java 8 với `lib/ext` để giải thích máy chạy Java 17.

### Application loader

Application loader tích hợp thường nằm dưới platform loader và nạp các lớp ứng dụng. Trong một chương trình chạy bằng `java -cp out Main`, lớp `Main` thường do application loader định nghĩa và đó cũng là loader mà `ClassLoader.getSystemClassLoader()` trả về, nếu không có tùy chỉnh hệ thống.

Các lớp trên **class path** thường thuộc **unnamed module** tương ứng với loader định nghĩa chúng. Trong Java 9+, một loader còn có thể liên quan tới **named module**. Vì vậy “application loader chỉ biết class path” là mô tả không đầy đủ trong hệ thống module hiện đại.

> Quy tắc an toàn: gọi API để kiểm tra **đối tượng loader cụ thể** đang chạy; đừng suy luận chỉ từ tên `AppClassLoader`, `Launcher` hoặc cách tổ chức file bên trong JDK.

## 3. System class loader là tên một vai trò API

API chính:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
~~~

Đây là một **static method** của `java.lang.ClassLoader`. Theo hợp đồng API, nó trả về system class loader dùng cho cơ chế nạp lớp của Java runtime. Trong môi trường Java thông thường, lời gọi trả về một đối tượng không null.

Một số API liên quan:

| API | Mục đích |
| --- | --- |
| `ClassLoader.getSystemClassLoader()` | Lấy system class loader đang được JVM sử dụng |
| `ClassLoader.getPlatformClassLoader()` | Lấy platform class loader (Java 9+) |
| `ClassLoader.getSystemResource(String)` | Tìm một tài nguyên thông qua system class loader |
| `ClassLoader.getSystemResources(String)` | Liệt kê các URL tài nguyên có cùng tên qua system loader |
| `ClassLoader.getSystemResourceAsStream(String)` | Mở tài nguyên bằng system loader |
| `ClassLoader.loadClass(String)` | Yêu cầu một loader cụ thể tìm/định nghĩa lớp theo tên nhị phân |
| `Class.getClassLoader()` | Biết **defining loader** của một kiểu runtime cụ thể |
| `Thread.currentThread().getContextClassLoader()` | Lấy **thread context class loader (TCCL)**; có thể khác system loader |

Ba thao tác sau trả lời ba câu hỏi **khác nhau**:

~~~java
ClassLoader a = ClassLoader.getSystemClassLoader();        // Loader hệ thống
ClassLoader b = MyApp.class.getClassLoader();               // Loader định nghĩa MyApp
ClassLoader c = Thread.currentThread().getContextClassLoader(); // TCCL
~~~

Đây là **đoạn minh họa**, giả sử `MyApp` là lớp có thật. Trong lối chạy phổ biến, a, b và c có thể cùng đối tượng. Trong runtime phức tạp hoặc với custom system loader, các đối tượng này **có thể khác nhau**. Không nên thay thế lẫn nhau một cách tùy tiện trong thư viện.

## 4. Application loader: tên phổ biến của loader tích hợp

Một JVM/JDK phải hỗ trợ hệ thống nạp lớp theo đặc tả, nhưng **tên class Java nội bộ** của loader mặc định không phải API tương thích của ứng dụng. Với OpenJDK/HotSpot hiện đại, một dòng quan sát bằng `getClass().getName()` có thể có dạng:

~~~text
jdk.internal.loader.ClassLoaders$AppClassLoader
~~~

Dòng này là **ví dụ đầu ra phụ thuộc JDK**, không phải hợp đồng rằng mọi JVM hoặc bản phát hành luôn in y hệt. Phần `jdk.internal.*` biểu thị lớp triển khai nội bộ; không import nó, không ép kiểu sang nó và không viết logic dựa vào tên chuỗi này.

Trong một ứng dụng chạy thông thường:

1. JDK launcher chuẩn bị môi trường chạy, bao gồm class path hoặc module path theo tham số được truyền.
2. Loader ứng dụng tìm/định nghĩa những lớp thích hợp theo cấu hình đó.
3. `ClassLoader.getSystemClassLoader()` thường trả về chính loader ứng dụng mặc định.
4. Lớp của thư viện trên class path cũng thường do loader này nạp nếu chưa được parent hoặc loader khác xử lý.
5. Lớp thuộc runtime Java có thể do bootstrap hoặc platform loader định nghĩa dù được tham chiếu từ code ứng dụng.

Do đó **“lớp được app sử dụng” không đồng nghĩa “lớp được application loader định nghĩa”**. Ví dụ ứng dụng sử dụng `java.lang.String`, nhưng lớp `String` thuộc loader lõi, không vì được gọi từ `main` mà chuyển sang app loader.

## 5. Thí nghiệm Java 17+: in loader và quan hệ parent

Tạo file **SystemLoaderDemo.java** đúng như sau:

~~~java
public class SystemLoaderDemo {
    static class Marker {
    }

    private static String name(ClassLoader loader) {
        return loader == null ? "<bootstrap>" : loader.getClass().getName();
    }

    public static void main(String[] args) {
        ClassLoader system = ClassLoader.getSystemClassLoader();
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader mainLoader = SystemLoaderDemo.class.getClassLoader();
        ClassLoader markerLoader = Marker.class.getClassLoader();
        ClassLoader stringLoader = String.class.getClassLoader();
        ClassLoader context = Thread.currentThread().getContextClassLoader();

        System.out.println("system type: " + name(system));
        System.out.println("platform type: " + name(platform));
        System.out.println("main type: " + name(mainLoader));
        System.out.println("String: " + name(stringLoader));

        System.out.println("main == system: " + (mainLoader == system));
        System.out.println("Marker == main: " + (markerLoader == mainLoader));
        System.out.println("system parent == platform: "
                + (system.getParent() == platform));
        System.out.println("context == system: " + (context == system));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 SystemLoaderDemo.java
java SystemLoaderDemo
~~~

**Đầu ra minh họa trên OpenJDK/HotSpot 17 ở cấu hình launcher mặc định** (mục `type` có thể thay đổi theo JDK):

~~~text
system type: jdk.internal.loader.ClassLoaders$AppClassLoader
platform type: jdk.internal.loader.ClassLoaders$PlatformClassLoader
main type: jdk.internal.loader.ClassLoaders$AppClassLoader
String: <bootstrap>
main == system: true
Marker == main: true
system parent == platform: true
context == system: true
~~~

Giải thích:

- `main == system` so sánh **danh tính đối tượng ClassLoader**, phù hợp để xác nhận hai biến đang trỏ đến cùng loader.
- `Marker == main`: lớp thành viên `Marker` được javac phát sinh thành class riêng và thường do cùng loader định nghĩa như lớp chính trong cách chạy này.
- `String: <bootstrap>`: dấu hiệu lớp lõi được bootstrap loader nạp.
- `system parent == platform`: đúng trong cấu hình mặc định nêu trên. Nếu có custom system loader, parent trực tiếp có thể là application loader gốc; biểu thức có thể là false.
- `context == system` là giá trị thường gặp với luồng main từ launcher chuẩn. Một framework có thể thay TCCL theo từng thread hoặc theo từng thao tác.

**Đừng viết test tính đúng đắn nghiệp vụ yêu cầu class name bắt buộc bằng `jdk.internal.loader.ClassLoaders$AppClassLoader`.** Đây chỉ là công cụ quan sát môi trường.

## 6. Parent delegation hoạt động ra sao?

Với cách triển khai `ClassLoader.loadClass(String, boolean)` mặc định, luồng xử lý khái quát là:

~~~text
loadClass("com.example.Widget")
        |
        v
Class đã từng được loader này nạp chưa? -- Có --> trả Class<?>
        |
       Chưa
        v
Gọi parent.loadClass(...) nếu parent != null;
nếu không có parent, tìm bằng bootstrap loader
        |
   tìm được? ---- Có --> trả Class<?>
        |
       Không
        v
Gọi findClass(...) trên loader hiện tại
        |
        +-- tìm được --> có thể resolve --> trả Class<?>
        |
        +-- không --> ClassNotFoundException
~~~

Cần phân biệt:

- **Parent delegation** là chiến lược tìm lớp mặc định được `ClassLoader` cung cấp. Một custom loader có thể override `loadClass` để áp dụng chính sách khác (ví dụ child-first) trong những giới hạn hợp lệ.
- **Loading** không tự đồng nghĩa với **initialization**. `ClassLoader.loadClass("pkg.Type")` thường trả về `Class<?>` mà không chạy static initializer của Type chỉ vì lời gọi này.
- **Parent** là quan hệ giữa các loader, không phải quan hệ `extends` giữa hai loại dữ liệu.
- Loader gọi `loadClass` là **initiating loader** của yêu cầu. Loader thực sự định nghĩa một lớp cụ thể được gọi là **defining loader**. Class.getClassLoader() giúp biết defining loader; nó có thể là parent nếu quá trình ủy quyền thành công.
- Nếu parent đã định nghĩa `java.lang.String`, app loader thường chỉ nhận lại `Class` từ parent. Nó không cần tự định nghĩa bản `String` thứ hai.

Sơ đồ trên là cách hiểu cơ bản cho **class path và ClassLoader.loadClass**. Khi nạp lớp thuộc **named modules**, JVM áp dụng thêm các ánh xạ và quy tắc module; không nên khẳng định mọi class từ module đều trải qua một chuỗi parent-first tuyến tính đúng như sơ đồ.

## 7. System loader, class path và module path

### Class path

Chương trình truyền thống thường dùng:

~~~bash
javac -d out src/com/example/Main.java
java -cp out com.example.Main
~~~

Đây là **mẫu lệnh**, chỉ hoạt động khi file source thực sự tồn tại và package/class khớp như đường dẫn. `-cp` (hoặc `--class-path`) chỉ các thư mục/JAR mà ứng dụng cho phép tìm lớp. Những lớp tìm thấy trên application class path thường được định nghĩa bởi app/system loader mặc định và thuộc **unnamed module** của loader tương ứng.

Trong Java 17, nếu có một thư viện JAR trên class path, cách gọi loader của lớp đó vẫn phụ thuộc việc class có thể đã được parent nạp, có loader tùy chỉnh, hoặc quy tắc riêng của môi trường chạy. Không có bảo đảm “mọi thứ trên đường chạy đều phải do system loader định nghĩa”.

### Module path

Ứng dụng dạng JPMS có thể chạy với cấu hình module path:

~~~bash
java --module-path mods --module com.example.app/com.example.Main
~~~

Đây cũng là **mẫu lệnh**, yêu cầu module thích hợp đã được biên dịch và đặt trong thư mục `mods`. Với named modules, JDK có thể gắn các module với builtin loader và áp dụng quy tắc resolution, readability, exports và việc ánh xạ package/module. Vì vậy:

- **class path** và **module path** không phải cùng một danh sách;
- **system loader** không đồng nghĩa “bất kỳ JAR nào trên class path”;
- **module visibility** và **class loading** liên quan nhưng là những cơ chế khác nhau: load được một class theo tên không có nghĩa mã nguồn ở mọi module được phép truy cập public API của nó;
- `ClassLoader.getUnnamedModule()` cho biết unnamed module gắn với một loader, không phải toàn bộ named modules trong hệ thống.

Trong dự án sử dụng Gradle/Maven, class path thực tế do công cụ build hoặc launcher thiết lập. Lỗi “IDE chạy được nhưng `java -cp` không tìm thấy lớp” thường xuất phát từ class path/module path thiếu thành phần, không phải vì thiếu một lớp tên `AppClassLoader`.

## 8. System loader có thể được thay bằng custom loader

Java hỗ trợ cấu hình thuộc tính hệ thống tại **lúc khởi động JVM**:

~~~bash
java -Djava.system.class.loader=com.example.CustomSystemLoader -cp out com.example.Main
~~~

Đây là **minh họa cú pháp**, chưa thể chạy nếu chưa có lớp `com.example.CustomSystemLoader` tương thích trên đường nạp phù hợp. Một custom system loader hợp lệ phải đáp ứng yêu cầu API, trong đó có **constructor nhận một ClassLoader parent**, để JVM tạo instance. API khởi tạo system loader theo cơ chế riêng; cấu hình thiếu constructor, lớp không tìm thấy hoặc ném lỗi trong khởi tạo sẽ khiến quá trình thiết lập thất bại.

Ví dụ **phác họa thành phần tùy chỉnh**, không phải chương trình có thể chạy độc lập nếu chưa biên dịch/đặt đúng class path:

~~~java
package com.example;

public class CustomSystemLoader extends ClassLoader {
    public CustomSystemLoader(ClassLoader parent) {
        super(parent);
    }
}
~~~

Đoạn này chỉ kế thừa hành vi ủy quyền mặc định; nó chưa thêm cơ chế tìm bytecode của riêng mình. Mục đích là thể hiện **hình dạng constructor** mà system-loader customization yêu cầu, không phải hướng dẫn bắt buộc mọi ứng dụng phải dùng loader tùy chỉnh.

Trong JDK chuẩn, khi bật cấu hình này, loader được trả về từ `getSystemClassLoader()` là instance tùy chỉnh, còn loader ứng dụng tích hợp dùng để tải lớp tùy chỉnh thường đóng vai trò parent trong quá trình khởi tạo nó. Vì thế, so sánh:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader defining = Main.class.getClassLoader();
boolean same = (system == defining);
~~~

là **đoạn minh họa**; `same` không được mặc định là true trong mọi môi trường. Quan hệ và thứ tự nạp lớp phụ thuộc JDK launcher, custom loader và cách lớp Main được định nghĩa.

Không cố gắng “thay system class loader” sau khi JVM đã khởi chạy bằng việc gán một biến Java thông thường: API không cung cấp setter động cho vai trò đó. Muốn chọn system loader khác, cấu hình hợp lệ phải sẵn sàng tại thời điểm JVM thiết lập system class loader.

## 9. Ví dụ Java 17+ kiểm tra nạp lớp mà chưa khởi tạo

Tạo file **SystemLoadVsInitialize.java**:

~~~java
public class SystemLoadVsInitialize {
    static class Service {
        static {
            System.out.println("Service initialized");
        }

        static void hello() {
            System.out.println("Hello from Service");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader system = ClassLoader.getSystemClassLoader();

        Class<?> type = Class.forName(
                "SystemLoadVsInitialize$Service",
                false,
                system
        );

        System.out.println("Found: " + type.getSimpleName());
        System.out.println("Defined by system: "
                + (type.getClassLoader() == system));

        Service.hello();
    }
}
~~~

Biên dịch và chạy theo cách thông thường, không truyền `-Djava.system.class.loader`:

~~~bash
javac --release 17 SystemLoadVsInitialize.java
java SystemLoadVsInitialize
~~~

**Stdout dự kiến chính xác khi chạy trên JDK 17+ thông thường với class path mặc định:**

~~~text
Found: Service
Defined by system: true
Service initialized
Hello from Service
~~~

Cơ chế:

1. **Class.forName(binaryName, false, system)** yêu cầu tìm kiểu qua system loader với `initialize=false`. Đó không phải lời gọi constructor và không yêu cầu chạy mã `static { ... }`.
2. `type.getSimpleName()` chỉ đọc metadata class; không làm static initializer chạy trong ví dụ.
3. Khi `Service.hello()` được gọi (tương ứng `invokestatic`), JVM bảo đảm `Service` đã initialized nên in dòng **Service initialized** trước thân phương thức.
4. Chỉ thị truy cập class literal, lấy Class<?> hay nạp class và thực thi static initializer là các giai đoạn **khác nhau**.
5. Nếu custom system loader chủ động định nghĩa lớp theo chính sách riêng, `type.getClassLoader() == system` có thể đổi kết quả; do đó điều kiện `true` được ghi rõ cho cách chạy chuẩn của ví dụ.

Tên `SystemLoadVsInitialize$Service` là **binary name** của nested class; dấu chấm theo cú pháp source `SystemLoadVsInitialize.Service` không thay thế được dấu `$` trong yêu cầu `Class.forName(String,boolean,ClassLoader)`.

## 10. Thread Context Class Loader không mặc định là System Loader

Một số framework, cơ chế SPI, JNDI, service discovery hoặc runtime plugin cần tìm lớp/tài nguyên mà loader của chính thư viện không biết. JVM cung cấp **thread context class loader** (TCCL) như một tham chiếu ngữ cảnh cho thread:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
ClassLoader system = ClassLoader.getSystemClassLoader();
~~~

Đoạn này là mã minh họa. Nhiều launcher đặt TCCL ban đầu của main thread bằng system loader, nhưng:

~~~java
thread.setContextClassLoader(customLoader);
~~~

có thể thay nó cho thread hiện tại (nếu quy tắc bảo mật môi trường cho phép), mà **không thay đổi đối tượng mà `ClassLoader.getSystemClassLoader()` trả về**. Thread khác có thể kế thừa TCCL của thread tạo nó hoặc được framework cấu hình lại.

Khi một thư viện hỗ trợ SPI hay plugin, việc cố lấy mọi class bằng system loader có thể bỏ sót các class chỉ có ở loader riêng của ứng dụng hoặc plugin. Nếu API khuyến nghị dùng context loader, nên tuân thủ hợp đồng API và bảo tồn/khôi phục TCCL khi tạm thay:

~~~java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(customLoader);
    // Gọi API cần loader theo ngữ cảnh của plugin.
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
~~~

Đây là **đoạn minh họa**, giả sử `customLoader` đã được tạo và luồng đang giữ quyền chỉnh ngữ cảnh. Khôi phục TCCL là quan trọng trong thread pool: các tác vụ sau có thể dùng lại cùng thread.

## 11. System resource và quy tắc tên tài nguyên

Với class loader, tên tài nguyên thường dùng dấu **/** phân tách thư mục tương đối từ gốc class path/module resource, không dùng tên binary có dấu chấm:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();

java.net.URL first = system.getResource("config/app.properties");
java.net.URL viaStatic = ClassLoader.getSystemResource("config/app.properties");
~~~

Đây là **đoạn minh họa**, phụ thuộc việc `config/app.properties` thực sự nằm trong đường tìm tài nguyên của system loader. Khi system là loader được API sử dụng, hai cách tìm đều mô tả đường tra cứu tài nguyên hệ thống, nhưng các chi tiết về module/resource visibility còn phụ thuộc Java runtime.

So sánh:

| API | Quy tắc tên tài nguyên cần chú ý |
| --- | --- |
| `ClassLoader.getResource("pkg/file.txt")` | Tên đường dẫn từ gốc; thông thường **không có dấu /** ở đầu |
| `SomeClass.class.getResource("file.txt")` | Nếu không bắt đầu bằng /, tìm tương đối với package của SomeClass |
| `SomeClass.class.getResource("/pkg/file.txt")` | Nếu bắt đầu bằng /, tìm theo đường dẫn tuyệt đối tính từ gốc tìm kiếm của Class resource |
| `ClassLoader.getSystemResource("pkg/file.txt")` | Yêu cầu tìm tài nguyên qua system loader |

Đừng nhầm **file .class** với **tên binary**: lớp `demo.Widget` có resource path thông thường là `demo/Widget.class`, còn `Class.forName` dùng tên binary `demo.Widget`.

Khi có nhiều JAR chứa tài nguyên cùng tên, kết quả `getResource` có thể phụ thuộc đường tìm và chính sách của loader. `getResources` giúp liệt kê nhiều ứng viên; không dựa vào thứ tự duy nhất như một hợp đồng nghiệp vụ khi đặc tả không bảo đảm.

## 12. Danh tính lớp phụ thuộc cả tên nhị phân và defining loader

Trong Java, hai file có bytecode biểu diễn cùng class `com.example.Plugin` không nhất thiết tạo **một kiểu runtime**:

~~~text
Loader A --defines--> com.example.Plugin  --> Class object A
Loader B --defines--> com.example.Plugin  --> Class object B
~~~

Khi A và B thực sự **tự định nghĩa** cùng một tên nhị phân, JVM coi đây là **hai loại runtime khác nhau**. Một đối tượng kiểu A không thể tự động cast sang kiểu B chỉ vì tên package và tên class giống nhau; trường hợp không tương thích có thể dẫn đến `ClassCastException` hoặc lỗi liên kết tương ứng.

Từ đó suy ra:

- `Class.getName()` giống nhau **chưa đủ** để xác nhận cùng kiểu.
- `Class.getClassLoader()` trả về defining loader, giúp phân biệt.
- Parent-first delegation thường làm hai loader con cùng nhận một `Class` do parent định nghĩa, hạn chế việc tạo nhiều phiên bản của một API cốt lõi.
- Plugin loader đôi khi cố ý định nghĩa class riêng để cô lập dependency, nhưng cần thống nhất những interface/API mà plugin chia sẻ với host.
- Trạng thái khởi tạo static cũng gắn với **mỗi định nghĩa lớp runtime**, không chỉ chuỗi tên. Hai defining loader khác nhau có thể có hai bộ static state độc lập cho cùng binary name.

System/application loader thường là **một phần trong hệ thống danh tính lớp**, không phải nguồn gốc duy nhất của tất cả class được chạy trên JVM.

## 13. Xử lý ClassNotFoundException, NoClassDefFoundError và vấn đề loader

### ClassNotFoundException

Khi gọi:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
Class<?> plugin = system.loadClass("com.example.Plugin");
~~~

đây là **đoạn minh họa**: nếu plugin chỉ có trong một plugin loader khác, system loader có thể báo `ClassNotFoundException`. Cách xử lý là dùng **loader có khả năng tìm thấy lớp**, thiết lập đường tìm phù hợp, hoặc dùng API framework hỗ trợ TCCL; không mặc định sửa bằng cách copy JAR không kiểm soát sang nhiều nơi.

### NoClassDefFoundError

JVM có thể ném `NoClassDefFoundError` khi một lớp từng có sẵn lúc biên dịch nhưng không thể có được định nghĩa tương ứng tại runtime hoặc khi quá trình initialization trước đó đã thất bại (“Could not initialize class ...”). Cần xem **cause và thông điệp chính xác** để phân biệt thiếu dependency runtime, dependency transitively missing và lỗi static initializer.

### ClassCastException giữa các loader

Hai class cùng binary name nhưng do hai loader khác nhau định nghĩa có thể không cast được. Khi debug, nên in:

~~~java
static void describe(Class<?> type) {
    System.out.println(type.getName());
    System.out.println(type.getClassLoader());
    System.out.println(type.getModule());
}
~~~

Đây là **đoạn minh họa trong một lớp Java**, không phải file chạy độc lập. Để tránh nhầm, so sánh bằng `type1 == type2` khi cả hai đã là `Class<?>`, xem defining loader và cấu hình parent delegation. Trong môi trường JPMS cũng nên kiểm tra module và phạm vi exports/opens của package.

## 14. Khi nào dùng loader nào?

| Nhu cầu | Loader/API thích hợp và lý do |
| --- | --- |
| Quan sát system loader của JVM | `ClassLoader.getSystemClassLoader()` |
| Quan sát platform loader | `ClassLoader.getPlatformClassLoader()` |
| Biết loader thực sự định nghĩa một kiểu | `SomeType.class.getClassLoader()` |
| Tìm tài nguyên từ cùng package với lớp thư viện | `SomeType.class.getResource(...)` (xem quy tắc đường dẫn) |
| Tìm class ở cùng miền nạp với thư viện/đối tượng | Loader của class đó khi phù hợp với API |
| Framework SPI/plugin yêu cầu TCCL | `Thread.currentThread().getContextClassLoader()` theo hợp đồng framework |
| Tải class tùy biến mà hệ thống không biết | Loader riêng có cấu hình parent và cơ chế `findClass` phù hợp |
| Nạp class theo binary name và kiểm soát initialization | `Class.forName(binaryName, initialize, loader)` |
| Đọc resource thuộc system loader | `ClassLoader.getSystemResource(...)` / `getSystemResourceAsStream(...)` |

Sự lựa chọn loader phụ thuộc **lớp/tài nguyên thuộc phạm vi nào**, không chỉ phụ thuộc việc code được chạy từ `main`, từ server hay từ một JAR.

## 15. Lỗi thường gặp và cách tránh

1. **Khẳng định system loader luôn là `AppClassLoader`.** Trong cấu hình chuẩn hai vai trò thường trùng nhau; hệ thống cho phép custom system loader. Kiểm tra bằng API.
2. **Ép kiểu sang `jdk.internal.loader.ClassLoaders$AppClassLoader`.** Đây là triển khai nội bộ. Chỉ làm việc với API công khai `java.lang.ClassLoader`.
3. **Nghĩ system loader nạp mọi lớp của JVM.** Lớp lõi thường do bootstrap loader, một số lớp nền tảng do platform loader và plugin có thể do custom loader định nghĩa.
4. **Nghĩ `getSystemClassLoader() == Thread.currentThread().getContextClassLoader()` luôn true.** Framework/thread pool có thể thay TCCL.
5. **Cho rằng parent của loader là superclass của các lớp nó định nghĩa.** Parent delegation là cơ chế giữa những loader, độc lập với kế thừa kiểu Java.
6. **Dùng `getName()` của loader như một chuẩn nghiệp vụ.** Tên lớp triển khai có thể thay đổi giữa các JVM/JDK.
7. **Xem `loadClass` đồng nghĩa khởi tạo static.** Loading/linking và initialization là các giai đoạn khác nhau.
8. **Truyền tên canonical của nested class vào `loadClass`.** Với nested member class, thường cần binary name như `pkg.Outer$Inner`.
9. **Bỏ qua JPMS.** Named modules có các quy tắc tìm lớp/khả năng truy cập riêng; class path và module path không phải cùng nguồn.
10. **Thay đổi TCCL rồi không khôi phục.** Thread pool có thể tái sử dụng thread, khiến tác vụ sau tìm lớp/tài nguyên sai ngữ cảnh.
11. **Thấy `NoClassDefFoundError` và kết luận chắc chắn thiếu file class.** Lỗi initialization trước đó cũng có thể khiến lớp trở thành erroneous.
12. **Cho rằng hai lớp cùng fully-qualified name chắc chắn cast được.** Cần tính tới defining loader và class identity.

## 16. Quy trình debug ngắn cho một lỗi class loading

Khi một lớp/tài nguyên tìm được ở IDE nhưng thất bại khi chạy thực tế:

1. In `ClassLoader.getSystemClassLoader()`, `ClassLoader.getPlatformClassLoader()`, `Thread.currentThread().getContextClassLoader()`, và `ProblemType.class.getClassLoader()` nếu loại đã load được.
2. Ghi cách launch: `-cp` / `--class-path`, `--module-path`, `--module`, các VM arguments, và có `-Djava.system.class.loader` hay không.
3. Kiểm tra **binary name** có đúng package và dấu `$` cho nested class không; tài nguyên có đúng đường dẫn `/` không.
4. Xác định nơi JAR/class được cung cấp: class path, module path, plugin directory hay custom loader.
5. Kiểm tra parent delegation và TCCL mà thư viện thực sự sử dụng.
6. Nếu lớp được load nhưng không truy cập được, kiểm tra exports/opens/module access, lỗi liên kết hoặc initialization failure. Không gom mọi sự cố vào “class loader không tìm thấy”.
7. Khi nghi nhiều phiên bản của class, in **tên + defining loader + module** và so sánh `Class<?>` thực tế.

Trong JDK hiện đại, tùy bản Java có thể bật log JVM với `-Xlog:class+load=info` để quan sát tên lớp và nguồn nạp. Thông tin hiển thị phụ thuộc JVM và tùy chọn logging; kết hợp nó với reflection để hiểu **đối tượng loader cụ thể** thay vì chỉ suy từ đường dẫn file.

## 17. Tự kiểm tra

**Câu 1.** Trong ứng dụng Java 17 chạy chuẩn trên class path, `ClassLoader.getSystemClassLoader()` thường là loader nào?  
**Đáp án:** application class loader tích hợp, thường có tên triển khai `AppClassLoader`. Đây là hành vi phổ biến của JDK, không phải bảo đảm về tên class nội bộ.

**Câu 2.** `String.class.getClassLoader() == null` có nghĩa gì trong JDK chuẩn?  
**Đáp án:** `String` được bootstrap loader định nghĩa; null là cách API đại diện bootstrap loader, không phải không có loader.

**Câu 3.** Nếu thread có TCCL trỏ tới plugin loader, `getSystemClassLoader()` có đổi theo không?  
**Đáp án:** Không. Thay TCCL của thread không thay vai trò system loader toàn JVM.

**Câu 4.** Một custom loader được đặt làm system loader có đồng nghĩa mọi class của ứng dụng sẽ luôn được nó định nghĩa?  
**Đáp án:** Không. Việc định nghĩa class phụ thuộc cách launcher tìm class, parent delegation và chính sách loader; nhiều class có thể do parent định nghĩa.

**Câu 5.** Khi `loadClass("com.example.Plugin")` thành công, có chắc static block của Plugin đã chạy?  
**Đáp án:** Không. Loading không tự động là initialization; cần xét điểm kích hoạt initialization.

**Câu 6.** Hai plugin loader độc lập định nghĩa `com.example.Api` với bytecode giống nhau có tạo cùng runtime class không?  
**Đáp án:** Không. Danh tính kiểu gồm binary name và defining loader; phải chia sẻ một định nghĩa chung nếu cần dùng chung API runtime.

**Câu 7.** Cần đọc `config/service.properties` bằng system loader. Dùng dấu chấm theo package hay dấu / theo đường dẫn?  
**Đáp án:** Dùng `config/service.properties`, không dùng `config.service.properties`, và thường không đặt dấu / đầu tên đối với ClassLoader.getResource.

## Tài liệu chính thức để đối chiếu

- Java SE 17 API — **ClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API — **Class**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 API — **Thread** (context class loader): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Java SE 17 API — **Module**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java Virtual Machine Specification, §5.3 **Creation of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java Virtual Machine Specification, §5.5 **Initialization**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- Java Language Specification, §12.2 **Loading of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2

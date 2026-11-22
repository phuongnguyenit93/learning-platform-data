# Không giả định system class loader là URLClassLoader

Trong Java, **system class loader** là class loader dùng để nạp các lớp ứng dụng theo cấu hình khởi chạy của JVM. Có thể lấy nó bằng:

~~~java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
~~~

Không nên ép kiểu kết quả sang URLClassLoader hoặc gọi các phương thức riêng của URLClassLoader như getURLs(). API chỉ bảo đảm đối tượng trả về là một ClassLoader; kiểu implementation cụ thể phụ thuộc JVM, phiên bản Java và cấu hình khởi chạy.

Từ Java 9, implementation class loader tích hợp của JDK đã thay đổi cùng với JPMS. Trên các JDK hiện đại, application/system loader mặc định thường là implementation nội bộ của JDK, không phải URLClassLoader. Ứng dụng cần dùng API chung của ClassLoader, hoặc tự tạo URLClassLoader khi thật sự cần nạp lớp từ một tập URL do ứng dụng quản lý.

## 1. System class loader là gì?

JVM sử dụng class loader để tìm, nạp và định nghĩa class. Một số loader thường gặp trong môi trường Java hiện đại:

| Class loader | Vai trò |
|---|---|
| Bootstrap class loader | Nạp các lớp nền tảng của Java. Nó được triển khai ở mức JVM và có thể được biểu diễn bằng null khi truy vấn parent. |
| Platform class loader | Nạp các lớp nền tảng không thuộc bootstrap loader; có thể lấy bằng ClassLoader.getPlatformClassLoader() từ Java 9. |
| System / application class loader | Nạp các lớp ứng dụng theo cấu hình khởi chạy, classpath và các module được gán cho loader này. Lấy bằng ClassLoader.getSystemClassLoader(). |
| Custom class loader | Loader do ứng dụng hoặc framework tạo để nạp lớp theo quy tắc riêng. |

Các tên trên mô tả vai trò và quan hệ nạp lớp. Không nên suy ra một vai trò phải tương ứng với một implementation class cụ thể.

### 1.1. System class loader không có hợp đồng là URLClassLoader

URLClassLoader là một implementation cụ thể của ClassLoader. Nó có thể nạp class và resource từ một mảng URL, chẳng hạn thư mục class hoặc JAR.

Trong các JDK cũ, application class loader mặc định từng được triển khai bằng URLClassLoader. Từ Java 9, JDK sử dụng implementation class loader tích hợp để hỗ trợ module system. Tên lớp implementation là chi tiết nội bộ, không phải hợp đồng ứng dụng được phép dựa vào.

Ngoài ra, system class loader có thể được tùy biến bằng thuộc tính khởi chạy java.system.class.loader. Vì vậy, ngay cả khi một môi trường cụ thể trả về URLClassLoader, không thể coi đó là bảo đảm chung cho mọi JVM.

Đoạn code sau không an toàn:

~~~java
URLClassLoader loader =
        (URLClassLoader) ClassLoader.getSystemClassLoader();
~~~

Nếu system loader không phải URLClassLoader, lệnh ép kiểu có thể ném ClassCastException. Ngay cả khi ép kiểu thành công trên một môi trường, việc dùng getURLs() để suy ra toàn bộ classpath vẫn không phản ánh module path, custom loader, nested JAR hoặc các nguồn nạp lớp khác.

**Quy tắc:** dùng kiểu ClassLoader cho thao tác nạp lớp thông thường; chỉ dùng URLClassLoader khi chính ứng dụng đã tạo hoặc nhận một instance có kiểu đó theo hợp đồng rõ ràng.

## 2. Dùng API ClassLoader thay vì phụ thuộc implementation

### 2.1. Lấy system class loader

~~~java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
~~~

Giữ biến ở kiểu ClassLoader. Không cần biết implementation bên dưới là lớp nào để gọi các API chuẩn.

Nếu cần loader nền tảng từ Java 9 trở lên:

~~~java
ClassLoader platformLoader = ClassLoader.getPlatformClassLoader();
~~~

Platform loader và system loader có mục đích khác nhau. Không thay thế lẫn nhau một cách tùy tiện: ứng dụng thường dùng system loader cho lớp ứng dụng; platform loader phục vụ lớp nền tảng được phân tách khỏi bootstrap loader.

### 2.2. Nạp class

Dùng loadClass khi đã có tên đầy đủ của class:

~~~java
ClassLoader loader = ClassLoader.getSystemClassLoader();
Class<?> type = loader.loadClass("com.example.app.Main");
~~~

Hoặc dùng Class.forName khi muốn chỉ định loader và có quyền điều khiển việc khởi tạo class:

~~~java
Class<?> type = Class.forName(
        "com.example.app.Main",
        false,
        ClassLoader.getSystemClassLoader()
);
~~~

Tham số false yêu cầu không khởi tạo class ngay tại lời gọi này. Khởi tạo class thường bao gồm chạy static initializer và xảy ra khi class được sử dụng theo quy tắc JVM.

loadClass và Class.forName có thể ném ClassNotFoundException nếu loader không tìm thấy class. Lỗi liên kết hoặc khởi tạo có thể phát sinh sau đó nếu class thiếu dependency hoặc có lỗi trong quá trình khởi tạo.

### 2.3. Tìm resource

Nếu mục tiêu là đọc file cấu hình hoặc resource trong classpath, hãy dùng API resource thay vì lấy URL từ URLClassLoader:

~~~java
ClassLoader loader = ClassLoader.getSystemClassLoader();

URL config = loader.getResource("config/app.properties");

if (config == null) {
    throw new IllegalStateException("Cannot find config/app.properties");
}

try (InputStream input = config.openStream()) {
    Properties properties = new Properties();
    properties.load(input);
}
~~~

Ví dụ đầy đủ hơn:

~~~java
import java.io.InputStream;
import java.net.URL;
import java.util.Properties;

public class ResourceExample {
    public static void main(String[] args) throws Exception {
        ClassLoader loader = ClassLoader.getSystemClassLoader();
        URL resource = loader.getResource("config/app.properties");

        if (resource == null) {
            throw new IllegalStateException("Resource not found");
        }

        Properties properties = new Properties();
        try (InputStream input = resource.openStream()) {
            properties.load(input);
        }

        System.out.println(properties.getProperty("app.name"));
    }
}
~~~

Nếu resource thuộc một class cụ thể, SomeClass.class.getResource(...) hoặc SomeClass.class.getResourceAsStream(...) thường thuận tiện hơn vì việc tìm kiếm được gắn với class đó và quy tắc đường dẫn tương ứng.

### 2.4. Tìm tất cả resource cùng tên

Dùng getResources khi có thể có nhiều resource cùng tên, ví dụ nhiều JAR cùng cung cấp một file cấu hình:

~~~java
Enumeration<URL> resources =
        ClassLoader.getSystemClassLoader()
                .getResources("META-INF/services/com.example.spi.Plugin");

while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
~~~

getResource trả về một resource phù hợp đầu tiên theo quy tắc tìm kiếm của loader; getResources cho phép duyệt các resource được tìm thấy.

Trong môi trường JPMS, resource thuộc named module còn chịu quy tắc đóng gói module. Không nên giả định mọi resource trong package nội bộ của module đều có thể được nhìn thấy từ mọi module khác. Hãy công bố hoặc mở package theo đúng nhu cầu và dùng API/module phù hợp.

## 3. Khi nào nên tạo URLClassLoader?

Nếu ứng dụng cần nạp plugin từ một JAR nằm ở đường dẫn do người dùng cấu hình, có thể tự tạo URLClassLoader.

Ví dụ:

~~~java
Path pluginJar = Path.of("plugins", "greeting-plugin.jar");
URL[] urls = { pluginJar.toUri().toURL() };

try (URLClassLoader pluginLoader = new URLClassLoader(
        urls,
        ClassLoader.getSystemClassLoader()
)) {
    Class<?> pluginClass = Class.forName(
            "com.example.plugin.GreetingPlugin",
            true,
            pluginLoader
    );

    Object plugin = pluginClass.getDeclaredConstructor().newInstance();
}
~~~

Ở đây, ứng dụng chủ động tạo một URLClassLoader với URL cụ thể. Việc dùng kiểu URLClassLoader là hợp lệ vì đối tượng đó được khởi tạo bằng constructor tương ứng; không có giả định nào về kiểu của system class loader.

### 3.1. Parent delegation

Constructor nhận parent xác định loader cha. Theo mô hình delegation thông thường, loader sẽ hỏi parent trước khi tự tìm class. Nếu parent đã nạp class cùng tên, plugin loader có thể nhận lại class từ parent.

Ví dụ:

~~~java
URLClassLoader pluginLoader = new URLClassLoader(
        urls,
        ClassLoader.getSystemClassLoader()
);
~~~

Cách này cho phép plugin dùng các API ứng dụng đã có trên system classpath. Nếu cần cô lập plugin hoặc chia sẻ một API riêng, phải thiết kế parent và ranh giới class identity cẩn thận. Hai class cùng tên nhưng được định nghĩa bởi hai class loader khác nhau vẫn có thể là hai kiểu khác nhau đối với JVM.

### 3.2. Đóng URLClassLoader

URLClassLoader triển khai Closeable. Khi không còn cần nạp class/resource từ các URL của loader, hãy đóng nó, tốt nhất bằng try-with-resources:

~~~java
try (URLClassLoader loader = new URLClassLoader(urls, parent)) {
    Class<?> plugin = loader.loadClass("com.example.plugin.GreetingPlugin");
}
~~~

Đóng loader giúp giải phóng các tài nguyên như file JAR đang mở và ngăn loader tiếp tục nạp class/resource mới từ các URL đó. Các class đã được nạp không tự động bị unload ngay khi gọi close(). Việc unload còn phụ thuộc loader có thể được thu gom rác và không còn tham chiếu giữ lại hay không.

Không nên đóng system class loader do JVM quản lý. Ứng dụng chỉ đóng các loader mà chính nó tạo và sở hữu theo hợp đồng vòng đời.

## 4. Ví dụ hoàn chỉnh: nạp plugin từ JAR bằng URLClassLoader

Ví dụ này gồm hai phần:

- Ứng dụng chính chạy trên classpath và nhận đường dẫn plugin JAR qua tham số dòng lệnh.
- Plugin được biên dịch thành JAR riêng, không có mặt trên classpath của ứng dụng chính.
- Ứng dụng tạo một URLClassLoader riêng để nạp plugin.

### 4.1. Cấu trúc thư mục

~~~text
project/
├── app-src/
│   └── com/example/app/Main.java
├── plugin-src/
│   └── com/example/plugin/GreetingPlugin.java
├── app-out/
├── plugin-classes/
└── plugins/
    └── greeting-plugin.jar
~~~

### 4.2. Mã plugin

File plugin-src/com/example/plugin/GreetingPlugin.java:

~~~java
package com.example.plugin;

public final class GreetingPlugin {
    public GreetingPlugin() {
    }

    public String greet(String name) {
        return "Hello, " + name + " from plugin!";
    }
}
~~~

### 4.3. Ứng dụng nạp plugin

File app-src/com/example/app/Main.java:

~~~java
package com.example.app;

import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class Main {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: Main <plugin-jar>"
            );
        }

        ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
        System.out.println("System loader available: " + (systemLoader != null));

        Path pluginPath = Path.of(args[0]).toAbsolutePath();
        URL[] pluginUrls = { pluginPath.toUri().toURL() };

        try (URLClassLoader pluginLoader =
                     new URLClassLoader(pluginUrls, systemLoader)) {

            Class<?> pluginType = Class.forName(
                    "com.example.plugin.GreetingPlugin",
                    true,
                    pluginLoader
            );

            Object plugin = pluginType.getDeclaredConstructor().newInstance();
            Method greet = pluginType.getMethod("greet", String.class);

            Object result = greet.invoke(plugin, "Ada");
            System.out.println(result);
        }
    }
}
~~~

Ví dụ dùng reflection để giữ ứng dụng chính không cần compile-time dependency vào class GreetingPlugin. Trong hệ thống lớn, một SPI/interface chung thường dễ bảo trì và an toàn kiểu hơn; khi đó plugin triển khai interface và ứng dụng ép kiểu về interface được chia sẻ.

### 4.4. Biên dịch và đóng gói

Từ thư mục project, tạo thư mục đầu ra:

~~~bash
mkdir -p app-out plugin-classes plugins
~~~

Biên dịch ứng dụng chính:

~~~bash
javac -d app-out app-src/com/example/app/Main.java
~~~

Biên dịch plugin riêng:

~~~bash
javac -d plugin-classes plugin-src/com/example/plugin/GreetingPlugin.java
~~~

Đóng gói plugin thành JAR:

~~~bash
jar --create --file plugins/greeting-plugin.jar -C plugin-classes .
~~~

### 4.5. Chạy ứng dụng

Trên Windows PowerShell:

~~~powershell
java -cp app-out com.example.app.Main plugins/greeting-plugin.jar
~~~

Trên Linux hoặc macOS:

~~~bash
java -cp app-out com.example.app.Main plugins/greeting-plugin.jar
~~~

Kết quả stdout:

~~~text
System loader available: true
Hello, Ada from plugin!
~~~

Ứng dụng chỉ đưa app-out lên classpath. Plugin JAR được mở bởi URLClassLoader riêng nên ứng dụng không cần thêm plugin JAR vào system classpath.

Dòng System loader available: true chỉ xác nhận loader hệ thống có mặt. Ví dụ không in hoặc dựa vào tên implementation cụ thể, vì tên và kiểu class loader có thể thay đổi giữa các JVM.

## 5. Phân biệt ClassLoader, URLClassLoader và module path

| Công cụ/API | Dùng khi nào | Điều không nên giả định |
|---|---|---|
| ClassLoader | Nạp class, tìm resource, truy cập parent và loader theo API chuẩn | Không có phương thức getURLs() |
| ClassLoader.getSystemClassLoader() | Lấy loader hệ thống theo cấu hình JVM | Không đảm bảo kết quả là URLClassLoader |
| URLClassLoader | Tự tạo loader để nạp class/resource từ một hoặc nhiều URL | Không phải cách lấy toàn bộ classpath của JVM |
| ClassLoader.getPlatformClassLoader() | Lấy platform loader trên Java 9+ | Không phải loader thay thế system loader cho mọi ứng dụng |
| ModuleLayer | Làm việc với cấu hình và lớp module ở runtime | Không nên giả định mọi module đều được nạp bởi cùng một loader |

Classpath và module path cũng là hai cấu hình khác nhau. URLClassLoader không phải công cụ tổng quát để liệt kê hoặc quản lý module path. Với module JPMS, hãy dùng module system và API như ModuleLayer khi cần thao tác với module layer.

Ví dụ lấy loader gắn với một module trong boot layer:

~~~java
ClassLoader moduleLoader =
        ModuleLayer.boot().findLoader("com.example.app");
~~~

Tên module phải tồn tại trong layer; nếu không, API có thể ném IllegalArgumentException. Module trong cùng layer cũng không nhất thiết phải có một loader riêng biệt cho từng module.

## 6. Nếu cần biết classpath thì làm thế nào?

Không dùng ép kiểu system loader sang URLClassLoader rồi gọi getURLs() để suy ra classpath. Nếu chỉ cần xem giá trị classpath được truyền qua cấu hình JVM, có thể đọc system property:

~~~java
String configuredClasspath =
        System.getProperty("java.class.path");
System.out.println(configuredClasspath);
~~~

Giá trị này là chuỗi cấu hình classpath của tiến trình, không phải danh sách đầy đủ mọi nguồn mà mọi class loader có thể sử dụng. Nó không đại diện cho module path, các custom loader, plugin JAR được nạp động hay mọi nguồn resource có thể có.

Nếu mục tiêu là tìm một resource, dùng getResource hoặc getResources. Nếu mục tiêu là nạp plugin, quản lý rõ danh sách URL của plugin và tạo loader riêng. Nếu mục tiêu là kiểm tra module, dùng công cụ và API JPMS tương ứng.

## 7. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| ClassCastException khi ép system loader sang URLClassLoader | Implementation system loader không phải URLClassLoader | Giữ kiểu ClassLoader; không ép kiểu theo implementation |
| Không tìm thấy getURLs() trên ClassLoader | getURLs() chỉ có trên URLClassLoader | Dùng API ClassLoader hoặc tự quản lý URL nếu tự tạo loader |
| ClassNotFoundException khi nạp plugin | Plugin JAR không nằm trong URL của loader, sai tên class hoặc sai đường dẫn | Kiểm tra URL, nội dung JAR và tên đầy đủ của class |
| NoClassDefFoundError sau khi tìm thấy plugin class | Plugin thiếu dependency tại runtime hoặc dependency không được loader nhìn thấy | Bổ sung dependency phù hợp và thiết kế parent/child loader rõ ràng |
| Resource trả về null | Sai đường dẫn resource hoặc resource không nằm trong phạm vi loader tìm kiếm | Kiểm tra đường dẫn tương đối từ gốc classpath/module và dùng getResources nếu cần nhiều kết quả |
| Plugin không thể cast sang interface mà ứng dụng mong đợi | API interface bị nạp bởi hai loader khác nhau hoặc plugin không triển khai đúng interface | Đặt API dùng chung ở parent loader và dùng cùng một class identity |
| JAR bị khóa hoặc không giải phóng được file | URLClassLoader do ứng dụng tạo chưa được đóng | Dùng try-with-resources hoặc đóng loader khi vòng đời plugin kết thúc |
| Thay đổi file JAR nhưng class cũ vẫn được sử dụng | Class đã nạp không tự thay thế khi JAR đổi trên đĩa | Tạo loader mới cho phiên bản plugin mới và quản lý vòng đời loader cũ |

## 8. Nguyên tắc thực hành

- Dùng ClassLoader làm kiểu tham chiếu chung cho system loader.
- Không cast system loader sang URLClassLoader.
- Không dựa vào tên lớp implementation nội bộ của JDK.
- Dùng getResource/getResources cho resource và loadClass/Class.forName cho class.
- Tạo URLClassLoader riêng khi cần nạp plugin từ URL cụ thể.
- Chọn parent loader phù hợp để kiểm soát API được chia sẻ.
- Đóng các URLClassLoader do ứng dụng tạo khi hoàn tất.
- Không đóng system loader do JVM quản lý.
- Không nhầm classpath với module path; dùng API JPMS khi thao tác với module layer.
- Kiểm thử trên các JDK và cấu hình khởi chạy mà ứng dụng hỗ trợ.

## 9. Tài liệu tham khảo

- [Java SE 26 API — ClassLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): system loader, platform loader, nạp class và tìm resource.
- [Java SE 26 API — URLClassLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLClassLoader.html): tạo và đóng loader nạp class từ URL.
- [Java SE 26 API — ModuleLayer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ModuleLayer.html): module layer và loader gắn với module.
- [Java SE 26 — java command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): classpath, module path và thuộc tính cấu hình JVM.
- [Dev.java — Class Loaders](https://dev.java/learn/jvm/tools/core/class-loaders/): tổng quan về class loading trong Java.

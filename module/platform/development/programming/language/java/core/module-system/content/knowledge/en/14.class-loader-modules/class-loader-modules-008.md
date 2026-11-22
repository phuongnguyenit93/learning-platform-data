# Chẩn đoán ClassNotFoundException và NoClassDefFoundError trong Java Module System

Khi một ứng dụng Java không thể sử dụng một class ở runtime, hai tên lỗi thường xuất hiện là **ClassNotFoundException** và **NoClassDefFoundError**. Chúng có thể cùng liên quan đến việc thiếu bytecode hoặc class loader không tìm thấy class, nhưng không có cùng ý nghĩa, không phát sinh ở cùng giai đoạn và không nên được xử lý bằng một giải pháp chung như "thêm mọi JAR vào classpath".

Với Java Platform Module System (JPMS), việc tìm và nạp class còn chịu ảnh hưởng của module path, module resolution, module layer, class loader gắn với module và sự tách biệt giữa **readability** với **exports/opens**. Một JAR có mặt trên ổ đĩa chưa chắc module của nó đã tham gia cấu hình runtime. Ngược lại, một module đã được phân giải không bảo đảm mọi dependency class cần thiết trong những đường thực thi muộn đều đã được tìm và liên kết thành công.

Bài học này cung cấp quy trình chẩn đoán có thứ tự: xác định chính xác loại lỗi, đọc nguyên nhân gốc, kiểm tra tên class và artifact, quan sát class loader/module, phân biệt lỗi module resolution, kiểm tra dependency runtime và class initialization, sau đó khắc phục và kiểm thử lại.

## 1. Khác biệt cốt lõi giữa hai loại lỗi

**ClassNotFoundException** là checked exception. Nó thường xuất hiện khi ứng dụng hoặc một framework chủ động yêu cầu tìm class theo tên mà class loader tương ứng không tìm thấy.

Ví dụ:

~~~java
Class<?> type = Class.forName("com.example.plugin.CsvPlugin");
~~~

Nếu class không thể được tìm thấy bằng cơ chế nạp được dùng, lời gọi có thể ném ClassNotFoundException.

**NoClassDefFoundError** là một LinkageError, không phải checked exception. Nó thường xuất hiện khi JVM cần một định nghĩa class để liên kết hoặc sử dụng bytecode, nhưng định nghĩa đó không thể được tìm thấy tại thời điểm cần thiết. Nó cũng có thể xuất hiện sau khi quá trình khởi tạo một class đã thất bại trong lần sử dụng trước.

Ví dụ:

~~~java
Report report = new Report();
~~~

Nếu mã đã biên dịch dựa trên Report nhưng khi chạy JVM không thể tìm định nghĩa class cần thiết, việc thực thi có thể gặp NoClassDefFoundError.

Bảng so sánh:

| Khía cạnh | ClassNotFoundException | NoClassDefFoundError |
| --- | --- | --- |
| Phân loại | Checked exception | Error, kế thừa LinkageError |
| Thường phát sinh khi | API hoặc framework yêu cầu load class theo tên | JVM cần class tại runtime nhưng không thể định nghĩa hoặc sử dụng |
| Ví dụ phổ biến | Class.forName, ClassLoader.loadClass | new, gọi method, truy cập field, liên kết dependency |
| Có thể liên quan class initialization? | Không phải dấu hiệu điển hình | Có, sau một lần initialization thất bại |
| Có thể xử lý bằng catch? | Có thể được khai báo throws hoặc bắt có chủ đích | Thường là lỗi cấu hình/đóng gói cần sửa nguyên nhân, không nên catch như logic thường |
| Hướng điều tra đầu tiên | Tên class và loader đang được yêu cầu | Root cause, thiếu class runtime hoặc class khởi tạo lỗi |

Không nên suy ra "ClassNotFoundException luôn do reflection" hoặc "NoClassDefFoundError luôn do thiếu JAR". Framework có thể bao bọc một lỗi trong lỗi khác; mỗi trường hợp cần đọc toàn bộ stack trace và chuỗi cause.

## 2. Ba giai đoạn cần tách biệt: module, class và khởi tạo

Trong ứng dụng modular, có thể hình dung:

~~~text
module path / classpath
         |
         v
ModuleFinder tìm descriptor
         |
         v
Module resolution chọn module + dependency
         |
         v
ModuleLayer định nghĩa các module runtime
         |
         v
ClassLoader tìm và định nghĩa class theo nhu cầu
         |
         v
Linking: verification, preparation, resolution
         |
         v
Class initialization khi được kích hoạt
~~~

Mỗi tầng có thể thất bại theo cách khác nhau:

- **Module discovery/resolution** có thể ném FindException hoặc ResolutionException trước khi chạy class main.
- **Class loading** có thể gặp ClassNotFoundException khi một API tìm class theo tên.
- **Class linking/sử dụng** có thể gặp NoClassDefFoundError nếu class cần thiết không khả dụng.
- **Class initialization** có thể ném ExceptionInInitializerError hoặc một Error khác; những lần dùng sau có thể gặp NoClassDefFoundError với thông điệp liên quan đến việc class không khởi tạo được.
- **Package access** có thể gây IllegalAccessError, IllegalAccessException hoặc InaccessibleObjectException; đây là các vấn đề khác với việc class hoàn toàn không tìm thấy.

Bước đầu của chẩn đoán là xác định JVM đã đi đến tầng nào, chứ không sửa ngẫu nhiên nhiều tùy chọn module.

## 3. Đọc stack trace trước khi sửa dependency

Ví dụ ClassNotFoundException:

~~~text
java.lang.ClassNotFoundException: com.example.plugin.CsvPlugin
    at ...
    at java.base/java.lang.Class.forName(...)
    at com.example.app/com.example.app.PluginLoader.load(...)
~~~

Thông tin cần lấy:

1. **Tên binary class**: com.example.plugin.CsvPlugin.
2. **Lời gọi đầu tiên của ứng dụng**: PluginLoader.load.
3. **Loader được sử dụng**: Class.forName overload nào, class loader nào.
4. **Môi trường**: chạy trong IDE, test, JAR, container hay custom ModuleLayer.

Ví dụ NoClassDefFoundError:

~~~text
java.lang.NoClassDefFoundError: com/example/codec/Codec
    at com.example.app/com.example.app.Main.main(Main.java:12)
Caused by: java.lang.ClassNotFoundException: com.example.codec.Codec
    at ...
~~~

Đừng chỉ nhìn dòng đầu. Phần **Caused by** có thể chỉ ra loader không tìm được một class dependency.

Tên class trong NoClassDefFoundError thường được biểu diễn với dấu gạch chéo (/), ví dụ com/example/codec/Codec, trong khi ClassNotFoundException thường hiển thị binary name dùng dấu chấm. Hai cách viết có thể cùng chỉ tới một class Java.

Nếu stack trace có nhiều tầng wrapper của framework, hãy tìm cause sâu nhất có thông tin cụ thể. Không nên bỏ qua các lỗi đầu tiên xuất hiện trước đó trong log khởi động.

## 4. Tái hiện ClassNotFoundException bằng Class.forName

Tạo class:

~~~java
package com.example.app;

public final class DynamicLookup {
    public static void main(String[] args) {
        try {
            Class<?> type = Class.forName(
                "com.example.missing.OptionalFeature"
            );
            System.out.println(type.getName());
        } catch (ClassNotFoundException e) {
            System.err.println(
                "Cannot find optional feature: " + e.getMessage()
            );
        }
    }
}
~~~

Biên dịch:

~~~bash
javac -d out src/com/example/app/DynamicLookup.java
~~~

Chạy:

~~~bash
java -cp out com.example.app.DynamicLookup
~~~

Nếu không có class com.example.missing.OptionalFeature trên đường tìm class, lời gọi Class.forName không thành công. Mã ở ví dụ này chủ động bắt checked exception để thực hiện nhánh xử lý cho chức năng tùy chọn.

Trong một ứng dụng thực tế, tên class có thể đến từ:

- File cấu hình.
- Tham số command line.
- Plugin registry hoặc discovery của framework.
- JDBC driver hoặc provider được nạp bằng tên.
- Cơ chế reflection, dependency injection hoặc serialization.

Vì vậy, trước khi tìm kiếm JAR, hãy xác nhận tên class đúng package, đúng chữ hoa/chữ thường và không phải tên bị thay đổi sau refactor.

## 5. Tái hiện NoClassDefFoundError do thiếu dependency runtime

Giả sử có hai source:

~~~java
// src/com/example/codec/Codec.java
package com.example.codec;

public final class Codec {
    public static String encode(String value) {
        return "[" + value + "]";
    }
}
~~~

~~~java
// src/com/example/app/Main.java
package com.example.app;

import com.example.codec.Codec;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Codec.encode("hello"));
    }
}
~~~

Biên dịch:

~~~bash
javac -d build/codec src/com/example/codec/Codec.java
~~~

~~~bash
javac -cp build/codec \
      -d build/app \
      src/com/example/app/Main.java
~~~

Chạy với đủ dependency:

~~~bash
java -cp "build/app:build/codec" com.example.app.Main
~~~

Kết quả:

~~~text
[hello]
~~~

Chạy thiếu thư mục chứa Codec:

~~~bash
java -cp build/app com.example.app.Main
~~~

Khi JVM cần định nghĩa class Codec, nhưng bytecode Codec không có trên classpath runtime, ứng dụng có thể gặp:

~~~text
java.lang.NoClassDefFoundError: com/example/codec/Codec
~~~

Ví dụ cho thấy **compile-time classpath và runtime classpath là hai cấu hình khác nhau**. Việc javac tìm được một class trong khi biên dịch không bảo đảm Java launcher sẽ tìm được class đó khi chạy.

Trên Windows, dùng dấu chấm phẩy trong classpath nhiều entry:

~~~powershell
java -cp "build/app;build/codec" com.example.app.Main
~~~

Không nên "sửa" ví dụ này bằng cách đổi tên class hoặc thêm --add-opens. Nguyên nhân thật sự là thiếu bytecode ở runtime.

## 6. Module path làm thay đổi cách phân giải dependency

Với explicit named module, dependency bắt buộc được khai báo bằng requires:

~~~java
module com.example.app {
    requires com.example.codec;
}
~~~

Nếu com.example.codec không thể tìm thấy từ các module observable, việc khởi chạy bằng -m có thể thất bại trước khi Main.main được gọi:

~~~bash
java --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Thông báo có thể là:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: Module com.example.codec not found,
required by com.example.app
~~~

Đây là lỗi **module resolution**, không phải cùng một lỗi với NoClassDefFoundError của ví dụ classpath.

Điểm phân biệt:

- Missing module bắt buộc theo **requires** thường bị phát hiện ngay trong resolution.
- Class không tìm thấy khi code dùng reflection có thể xuất hiện muộn hơn, tùy cách nạp.
- Module đã được phân giải vẫn có thể gặp lỗi runtime khác nếu artifact không chứa class cần thiết, dependency không phải module bắt buộc hoặc class initialization thất bại.

Khi log có FindException, hãy kiểm tra tên module, descriptor, module path và dependency graph. Không nên chỉ tìm tên class bị thiếu hoặc thêm thư viện vào classpath rồi kỳ vọng requires sẽ tự được thỏa mãn.

## 7. Kiểm tra tên module và nội dung JAR

Để biết một artifact có phải explicit named module hay automatic module, kiểm tra:

~~~bash
jar --describe-module --file libs/com.example.codec.jar
~~~

Một modular JAR explicit thường chứa module-info.class ở gốc JAR. Tên module được xác định bởi descriptor, không nhất thiết trùng tên file JAR.

Để kiểm tra class có trong JAR không:

~~~bash
jar --list --file libs/com.example.codec.jar
~~~

Tìm entry:

~~~text
com/example/codec/Codec.class
~~~

Nếu thiếu entry, có thể nguyên nhân là:

- Build không đưa class vào JAR.
- Artifact đã bị exclude/shade hoặc relocate.
- Source set không chứa class mong đợi.
- Đang triển khai JAR không đúng version.
- JAR bị đổi cấu trúc package mà consumer vẫn tham chiếu tên cũ.

Nếu artifact nằm trong nhiều phiên bản, phải kiểm tra **đúng file JAR thực sự được runtime sử dụng**, không chỉ file trong thư mục source hoặc local Maven repository.

## 8. ClassLoader quyết định class được tìm ở đâu

Trong JVM, class loading không chỉ dựa vào một danh sách JAR toàn cục. Mỗi class loader có phạm vi tìm kiếm và quan hệ delegation riêng.

Các loader dựng sẵn thường gồm:

- **Bootstrap loader** cho nhiều class cốt lõi như java.lang.Object.
- **Platform loader** cho các module nền tảng được giao cho nó.
- **Application/system loader** cho class ứng dụng và nhiều module ứng dụng trong cấu hình launch thông thường.

Ví dụ:

~~~java
System.out.println(
    "Object loader: " + Object.class.getClassLoader()
);

System.out.println(
    "System loader: " + ClassLoader.getSystemClassLoader()
);

System.out.println(
    "Platform loader: " + ClassLoader.getPlatformClassLoader()
);
~~~

Object.class.getClassLoader() thường trả về null để biểu diễn bootstrap loader.

Nếu một custom class loader chỉ biết thư mục plugins, nó có thể không tìm thấy class nằm trong thư mục khác dù class đó hiện diện trên ổ đĩa. Ngược lại, một class loader khác có thể đã nạp class cùng tên nhưng điều đó không làm class tự xuất hiện trong phạm vi của loader được yêu cầu.

Class identity trong JVM gồm tên class và **defining class loader**. Hai class cùng binary name được định nghĩa bởi hai loader khác nhau là hai kiểu khác nhau; lỗi phát sinh có thể là ClassCastException hoặc lỗi linkage, không nhất thiết là ClassNotFoundException.

## 9. Class.forName, loadClass và tham số initialize

Có thể chủ động chỉ định loader:

~~~java
ClassLoader loader = ClassLoader.getSystemClassLoader();

Class<?> type = Class.forName(
    "com.example.plugin.CsvPlugin",
    false,
    loader
);
~~~

Ở đây:

- Tên class phải là binary name với dấu chấm.
- **false** yêu cầu không khởi tạo class chỉ vì lời gọi này.
- Loader được truyền vào quyết định phạm vi tìm kiếm khi class cần được nạp.
- JVM vẫn có thể thực hiện những bước loading/linking cần thiết; false không bảo đảm không đụng tới bất kỳ dependency nào.

Đối với ClassLoader.loadClass:

~~~java
Class<?> type = loader.loadClass(
    "com.example.plugin.CsvPlugin"
);
~~~

Cách gọi thường không khởi tạo class ngay. Nếu cần phân biệt lỗi loading với lỗi static initialization, hãy thử nạp class mà không yêu cầu initialize, rồi dùng đường code thực sự kích hoạt initialization.

Một lưu ý khi debug: việc **Class.forName(String)** dùng loader xác định theo caller khác với overload truyền loader cụ thể. Nếu ứng dụng/plugin chạy trong nhiều class loader, hãy luôn kiểm tra overload nào đang được framework gọi.

## 10. ClassNotFoundException trong custom ModuleLayer

JPMS cho phép ứng dụng tạo ModuleLayer riêng để nạp module động. Một module có thể thuộc layer con và được gắn với loader khác application/system loader.

Ví dụ khái quát:

~~~java
ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder =
    ModuleFinder.of(Path.of("plugins"));

Configuration config =
    parent.configuration().resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.example.plugin")
    );

ModuleLayer.Controller controller =
    parent.defineModulesWithOneLoader(
        config,
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();

ClassLoader pluginLoader =
    pluginLayer.findLoader("com.example.plugin");
~~~

Nếu plugin class thuộc loader này, dùng đúng loader khi nạp:

~~~java
Class<?> type = Class.forName(
    "com.example.plugin.impl.PluginImpl",
    false,
    pluginLoader
);
~~~

Dùng ClassLoader.getSystemClassLoader() để tìm class trong layer mới không nhất thiết thành công. Loader của module thuộc layer con có thể biết class mà loader ứng dụng cha không biết.

Cần phân biệt hai vấn đề:

1. **Module có trong ModuleLayer không?** Kiểm tra findModule.
2. **Class có được tìm bằng loader của module không?** Kiểm tra findLoader và Class.forName.

Việc ModuleLayer tìm thấy module chưa có nghĩa một loader bất kỳ trong ứng dụng có thể nạp mọi class của module đó.

## 11. Thread context ClassLoader và framework

Nhiều framework, container và cơ chế plugin dùng **thread context class loader** (TCCL) để tìm provider hoặc tài nguyên.

Quan sát loader:

~~~java
Thread thread = Thread.currentThread();

ClassLoader contextLoader =
    thread.getContextClassLoader();

System.out.println(contextLoader);
~~~

TCCL có thể khác defining loader của class đang chạy. Một service được gọi trong thread pool có thể dùng TCCL của thread, dẫn tới việc không tìm thấy provider mà một thread khác có thể tìm được.

Nếu framework phụ thuộc vào TCCL, có thể đặt trong phạm vi tác vụ:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);

    // Gọi framework dựa vào context class loader.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Luôn khôi phục loader cũ trong finally để tránh ảnh hưởng tác vụ sau, đặc biệt với thread pool.

Với JPMS service provider, có thể chọn rõ ModuleLayer:

~~~java
ServiceLoader<MyService> services =
    ServiceLoader.load(pluginLayer, MyService.class);
~~~

Khi ServiceLoader không tìm được provider, hãy kiểm tra **uses**, **provides ... with**, cấu hình resolution, loader/layer và cách framework nạp service. Một lỗi provider có thể bị wrapper của framework báo chung là "class not found", nên cần xem nguyên nhân thực tế.

## 12. NoClassDefFoundError sau khi class initialization thất bại

Một nguyên nhân dễ bị bỏ qua là lỗi trong static initializer hoặc quá trình khởi tạo static field.

Ví dụ:

~~~java
package com.example.app;

public final class BrokenConfig {
    static {
        if (System.getProperty("required.config") == null) {
            throw new IllegalStateException("Missing required.config");
        }
    }

    public static String value() {
        return "ready";
    }
}
~~~

Lần đầu một luồng thực sự kích hoạt initialization:

~~~java
System.out.println(BrokenConfig.value());
~~~

Nếu property required.config vắng mặt, static initializer ném exception. JVM có thể bọc nguyên nhân trong **ExceptionInInitializerError**.

Class đã có trạng thái initialization thất bại. Lần sử dụng tiếp theo có thể báo:

~~~text
java.lang.NoClassDefFoundError: Could not initialize class
com.example.app.BrokenConfig
~~~

Trong tình huống này, **class file có thể tồn tại đầy đủ trên classpath hoặc module path**. Vấn đề không phải JAR thiếu bytecode, mà là class initialization đã thất bại.

Cách chẩn đoán:

1. Tìm **exception đầu tiên trong log**, đặc biệt ExceptionInInitializerError.
2. Xem phần Caused by để tìm lỗi config, permission, environment hoặc resource.
3. Không giải quyết bằng cách thêm JAR không liên quan.
4. Sửa điều kiện khởi tạo rồi chạy lại trong một JVM mới để kiểm tra.

Một số lỗi khởi tạo còn có thể xảy ra khi static field phụ thuộc class khác, kết nối tài nguyên hoặc native library. Đừng chỉ nhìn thông điệp NoClassDefFoundError cuối cùng.

## 13. Lỗi thiếu class gián tiếp

Class được yêu cầu có thể tồn tại, nhưng một class mà nó phụ thuộc lại vắng mặt.

Ví dụ:

~~~text
application.jar
  └── com.example.app.Main

feature.jar
  └── com.example.feature.Service

codec.jar
  └── com.example.codec.Codec
~~~

Nếu Main dùng Service và Service lại cần Codec, một bản đóng gói thiếu codec.jar có thể làm lỗi chỉ xuất hiện khi code gọi một method nhất định.

Thông báo lỗi có thể nhắc **Codec**, dù developer đang tập trung vào **Service**. Vì vậy không nên chỉ kiểm tra JAR chứa class trực tiếp được gọi.

Các nguyên nhân thường gặp:

- Dependency scope chỉ có lúc compile, không có lúc runtime.
- Artifact bị exclude khỏi package hoặc container image.
- Một dependency transitive bị phiên bản khác ghi đè.
- Cấu hình production bỏ sót plugin hoặc module tùy chọn.
- Một thư viện đổi binary name/package giữa các version.
- Bytecode tham chiếu class chỉ xuất hiện trên một nhánh thực thi ít dùng.

Khi chẩn đoán, theo dõi dependency thực sự được báo trong stack trace rồi kiểm tra toàn bộ runtime dependency tree.

## 14. Maven: dependency có mặt lúc nào?

Trong Maven, một dependency có thể được khai báo với scope khác nhau. Ví dụ:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>codec</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Với một ứng dụng thông thường, dependency compile không bị giới hạn bởi scope đặc biệt sẽ được xem xét cho compile và runtime theo mô hình Maven.

Nếu dependency bị đặt scope provided:

~~~xml
<scope>provided</scope>
~~~

thì build giả định môi trường triển khai sẽ cung cấp dependency. Nếu môi trường thực tế không có nó, runtime có thể không tìm thấy class.

Tương tự, nếu một dependency chỉ có scope test, nó không được đưa vào runtime của ứng dụng production chỉ vì test biên dịch được.

Dùng:

~~~bash
mvn dependency:tree
~~~

để xem dependency và version được Maven chọn. Khi dùng modular application, còn phải kiểm tra plugin cấu hình module path hay classpath và lệnh java cuối cùng có nhận artifact hay không.

Không nên chỉ nhìn dependency trong pom.xml rồi mặc định JAR có trong bản đóng gói cuối. Container, runtime launcher và distribution có thể dùng một tập artifact khác.

## 15. Gradle: runtimeClasspath và compileClasspath

Gradle tách nhiều configuration cho các giai đoạn. Một dependency có thể có trong compileClasspath nhưng không có trong runtimeClasspath nếu dùng cấu hình không phù hợp.

Ví dụ khai báo thông thường:

~~~groovy
dependencies {
    implementation 'com.example:codec:1.0.0'
}
~~~

Nếu chỉ cần API ở compile-time mà thư viện không có ở runtime, cấu hình có thể khác. Nhưng nếu class thực sự được dùng trong production, cần bảo đảm dependency xuất hiện ở **runtimeClasspath** hoặc module path theo cấu hình ứng dụng.

Có thể xem dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Và xem riêng dependency:

~~~bash
./gradlew dependencyInsight \
  --dependency codec \
  --configuration runtimeClasspath
~~~

Các công cụ này giúp biết Gradle chọn version nào và có exclusion/conflict resolution hay không.

Khi dùng application plugin hoặc custom JavaExec, cần đối chiếu task đang chạy với classpath/module path thực tế. Một test task dùng dependency đầy đủ chưa chắc distribution production cũng chứa đủ những dependency đó.

## 16. Quan sát class loading của JVM

Từ JDK 9, có thể dùng unified logging:

~~~bash
java -Xlog:class+load=info \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Log cho thấy nhiều class được nạp và nguồn nạp tương ứng. Đây là cách hữu ích để kiểm tra:

- Class được nạp từ JAR hoặc module nào.
- Có version class khác kỳ vọng đang được dùng không.
- Một class được nạp trước thời điểm lỗi hay chưa.
- Các class cùng package được nạp từ những nguồn nào.

Có thể tăng mức chi tiết cho mục tiêu chẩn đoán:

~~~bash
java -Xlog:class+load=debug \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Logging class load có thể rất nhiều dòng. Hãy ghi vào file log nếu cần phân tích, thay vì trộn toàn bộ log với output ứng dụng trong production.

Quan trọng: log các class đã nạp thành công không nhất thiết giải thích đầy đủ mọi class bị thiếu. Phải kết hợp stack trace, class loader và kiểm tra nội dung artifact.

## 17. Quan sát module resolution

Để xem module nào được chọn khi khởi chạy:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.example.app/com.example.app.Main
~~~

Công cụ này hữu ích khi một module thiếu dependency requires hoặc bị phân giải theo cách khác dự kiến.

Có thể liệt kê module observable:

~~~bash
java --module-path mods --list-modules
~~~

Sự khác nhau:

- **--list-modules** giúp xem module có thể được tìm thấy.
- **--show-module-resolution** giúp xem các module được đưa vào cấu hình của lệnh chạy.
- **ModuleLayer.boot().findModule(name)** kiểm tra module có hiện diện trong boot layer của JVM đang chạy.

Ví dụ:

~~~java
boolean available =
    ModuleLayer.boot()
        .findModule("com.example.codec")
        .isPresent();

System.out.println("Codec in boot layer: " + available);
~~~

Một JAR có trong thư mục mods nhưng module của nó không được yêu cầu như root, dependency hoặc service provider cần phân giải thì có thể không nằm trong boot layer.

Nếu module không xuất hiện trong graph, cần kiểm tra requires, --add-modules, service binding và cấu hình custom layer. Đừng dùng --add-opens để cố đưa module vào graph.

## 18. Module đã tìm thấy nhưng package không truy cập được

Đây không phải lỗi class not found điển hình, dù thông báo từ framework có thể gây hiểu lầm.

Giả sử:

~~~java
module com.example.codec {
    exports com.example.codec.api;
}
~~~

Và:

~~~java
module com.example.app {
    requires com.example.codec;
}
~~~

App có thể dùng public API từ package com.example.codec.api. Nhưng nếu app cố import public class từ **com.example.codec.internal**, compiler có thể báo package is not visible.

Nếu framework dùng reflection vào private member của một package chưa mở, nó có thể báo InaccessibleObjectException.

Cần phân biệt:

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Module not found | Module path, module name, requires và roots |
| Package is not visible | requires/readability và exports |
| IllegalAccessError | Quyền truy cập ở runtime và bytecode |
| InaccessibleObjectException | opens và module identity của caller |
| ClassNotFoundException | Loader và tên class được yêu cầu |
| NoClassDefFoundError | Class runtime/linking hoặc initialization thất bại |

Không nên thêm hàng loạt --add-reads, --add-exports và --add-opens cho mọi lỗi. Các cờ giải quyết cơ chế khác nhau và có thể làm suy yếu encapsulation nếu bị lạm dụng.

## 19. Class loading từ automatic và unnamed modules

**Automatic module** là JAR chưa có descriptor explicit nhưng được đặt trên module path và nhận một module name theo quy tắc JPMS.

**Unnamed module** thường chứa các class/JAR trên classpath của một class loader.

Cùng một legacy JAR có thể được xử lý khác nhau khi di chuyển giữa hai đường:

~~~bash
java --class-path "libs/*" com.example.app.Main
~~~

so với:

~~~bash
java --module-path libs \
     --add-modules legacy.codec \
     -m com.example.app/com.example.app.Main
~~~

Tên **legacy.codec** trong ví dụ phải là module name thực tế của JAR, không được đoán từ tên file nếu chưa kiểm tra.

Khi chuyển sang module path:

- JAR có thể trở thành automatic named module.
- Consumer named module phải có quan hệ đọc phù hợp.
- Module graph phải thỏa mãn các ràng buộc JPMS.
- Split package hoặc module name collision có thể làm resolution thất bại.

Một lỗi sau chuyển đổi có thể là FindException hoặc ResolutionException, không nhất thiết là ClassNotFoundException. Vì vậy bước đầu tiên là xác định kiểu khởi chạy và giai đoạn thất bại.

## 20. Chẩn đoán ServiceLoader khi provider không được tìm thấy

Ứng dụng modular thường dùng ServiceLoader để khám phá implementation.

Ví dụ module consumer:

~~~java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.ReportProvider;
}
~~~

Module provider:

~~~java
module com.example.provider.csv {
    requires com.example.spi;

    provides com.example.spi.ReportProvider
        with com.example.provider.csv.CsvProvider;
}
~~~

Các điểm cần kiểm tra:

1. Service interface thuộc một module chung được các bên đọc.
2. Consumer khai báo uses phù hợp.
3. Provider khai báo provides ... with.
4. Provider module thực sự tham gia configuration được sử dụng.
5. ServiceLoader được gọi với đúng layer/loader.
6. Constructor hoặc provider method có thể thực thi thành công.
7. Dependency của provider có mặt và tương thích.

Với custom layer:

~~~java
ServiceLoader<ReportProvider> services =
    ServiceLoader.load(pluginLayer, ReportProvider.class);
~~~

Dùng đúng overload theo layer giảm nhầm lẫn so với dựa vào TCCL không đúng phạm vi.

ServiceLoader có thể ném **ServiceConfigurationError** nếu provider không hợp lệ hoặc không thể được tạo. Nếu cause là ClassNotFoundException, NoClassDefFoundError hoặc lỗi initialization, hãy xử lý nguyên nhân gốc thay vì chỉ đổi service configuration.

## 21. Công cụ kiểm tra artifact và dependency

Một bộ lệnh thực hành:

Kiểm tra module descriptor:

~~~bash
jar --describe-module --file libs/com.example.codec.jar
~~~

Liệt kê class trong JAR:

~~~bash
jar --list --file libs/com.example.codec.jar
~~~

Xem dependency ở cấp bytecode:

~~~bash
jdeps --module-path mods \
      --module com.example.app
~~~

Tìm tham chiếu đến API JDK nội bộ trong thư viện:

~~~bash
jdeps --jdk-internals libs/legacy-library.jar
~~~

Xem runtime module graph:

~~~bash
java --show-module-resolution -p mods \
     -m com.example.app/com.example.app.Main
~~~

Quan sát class load:

~~~bash
java -Xlog:class+load=info -p mods \
     -m com.example.app/com.example.app.Main
~~~

Các công cụ có điểm mù khác nhau. Ví dụ, jdeps phân tích dependency có thể nhận diện từ bytecode; tên class được tạo động từ string, reflection hoặc resource có thể không được suy ra đầy đủ. Vì vậy cần kết hợp runtime log và test theo đúng đường thực thi.

## 22. Quy trình chẩn đoán từng bước

Khi tiếp nhận một bug có thông báo "class not found" hoặc "no class definition", thực hiện theo thứ tự:

1. **Thu thập log đầu tiên**: stack trace đầy đủ, cause chain, thời điểm lỗi và version JDK.
2. **Ghi lại tên class**: binary name, package, tên cũ/mới sau khi relocate và class nào đang được yêu cầu.
3. **Xác định loại lỗi**: ClassNotFoundException, NoClassDefFoundError, FindException, ResolutionException, ServiceConfigurationError hay lỗi access.
4. **Kiểm tra artifact**: JAR có class thật không? Đang chạy đúng version không?
5. **Kiểm tra compile/runtime config**: classpath, module path, dependency scope và những exclusion.
6. **Kiểm tra module graph**: root, requires, automatic module, custom layer và service binding.
7. **Kiểm tra loader cụ thể**: system/application, platform, plugin loader hoặc TCCL.
8. **Tìm lỗi initialization trước đó**: đặc biệt khi thông báo là "Could not initialize class".
9. **Kiểm tra quyền truy cập riêng**: readability, exports, opens nếu log cho thấy access denied.
10. **Sửa nguyên nhân tối thiểu**: thêm đúng runtime dependency, sửa tên class, điều chỉnh descriptor hoặc loader, sửa static initialization.
11. **Chạy lại bằng cùng kiểu launcher**: IDE và CLI có thể khác đường classpath/module path.
12. **Thêm test hồi quy**: chạy trên môi trường gần production và cả nhánh chức năng gây lỗi.

Bảng quyết định nhanh:

| Dấu hiệu | Kiểm tra đầu tiên | Hướng khắc phục thường gặp |
| --- | --- | --- |
| Class.forName ném ClassNotFoundException | Tên class, loader, classpath/plugin layer | Dùng loader đúng, sửa tên hoặc đóng gói class |
| NoClassDefFoundError: com/.../Codec | Class runtime thực sự thiếu hoặc lỗi linkage | Bổ sung đúng dependency/version cho runtime |
| NoClassDefFoundError: Could not initialize class | Lỗi khởi tạo trước đó | Tìm ExceptionInInitializerError và sửa nguyên nhân |
| FindException: required module not found | Module name, module path và descriptor | Thêm module đúng vị trí hoặc sửa requires |
| ResolutionException về package | Split package hoặc module graph | Tái cấu trúc package/dependency |
| InaccessibleObjectException | Package chưa opens cho caller | Điều chỉnh reflection hoặc qualified opens |
| ServiceConfigurationError | Service provider descriptor và cause | Sửa provider, dependency, loader/layer |

## 23. Ngăn ngừa lỗi trong CI/CD và triển khai

Nhiều lỗi chỉ xuất hiện sau khi đóng gói hoặc triển khai. Để giảm nguy cơ:

- Dùng cùng JDK major version trong build, test và production nếu không có lý do tương thích cụ thể.
- Kiểm thử **artifact cuối cùng** thay vì chỉ chạy source qua IDE.
- Ghi lại command line java thực tế, nhất là --module-path, --class-path, --add-modules và JVM args.
- Kiểm soát version dependency và loại bỏ JAR trùng hoặc bản cũ còn sót trong distribution.
- Đảm bảo runtime-only dependency cần thiết được đưa vào image hoặc deployment package.
- Khi dùng plugin, có integration test nạp plugin từ thư mục và layer thực tế.
- Kiểm tra cả dynamic loading, ServiceLoader và static initializer thay vì chỉ test khởi động.
- Với optional dependency, thiết kế hành vi fallback và thông báo lỗi dễ hiểu nếu class không có.
- Không catch rộng LinkageError để bỏ qua lỗi cấu hình nghiêm trọng rồi tiếp tục với trạng thái nửa hoạt động.

Một test có thể xác nhận packaging:

~~~bash
jar --list --file dist/com.example.app.jar
~~~

Sau đó dùng lệnh khởi chạy production-like và chạy nhánh code cần class hay plugin được đóng gói.

## 24. Bài tập thực hành

1. Tạo ví dụ Codec ở phần 5, biên dịch thành công rồi bỏ build/codec khỏi runtime classpath. Ghi lại NoClassDefFoundError.
2. Tạo DynamicLookup gọi Class.forName với class không tồn tại. Ghi lại ClassNotFoundException.
3. So sánh hai stack trace và phần cause nếu có.
4. Đưa Codec vào một explicit named module, khai báo requires rồi cố chạy khi module Codec vắng khỏi module path. Quan sát FindException.
5. Đặt JAR Codec lên module path, chạy --list-modules và --show-module-resolution để phân biệt module observable với resolved.
6. Tạo class có static initializer thất bại; quan sát lỗi lần đầu và NoClassDefFoundError ở lần sử dụng sau trong cùng JVM.
7. Tạo plugin layer riêng và thử nạp plugin bằng system loader, sau đó bằng pluginLayer.findLoader.
8. Dùng -Xlog:class+load=info để xem class được nạp từ nguồn nào.
9. Thử thay đổi một dependency scope Maven/Gradle và so sánh compileClasspath/runtimeClasspath.
10. Ghi lại một checklist debug ngắn có thể áp dụng khi production báo class missing.

**ClassNotFoundException và NoClassDefFoundError không chỉ khác tên.** Chúng giúp xác định bạn đang gặp vấn đề trong thao tác tìm class theo tên, JVM linking/sử dụng class hay class initialization sau một lỗi trước đó. Trong ứng dụng modular, việc phân biệt thêm module resolution, class loader/module layer và package access sẽ dẫn bạn tới nguyên nhân thực tế nhanh hơn, thay vì thêm tùy chọn hoặc JAR một cách thử-và-sai.
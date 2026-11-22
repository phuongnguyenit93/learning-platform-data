# ClassNotFoundException do loader hoặc layer sai

Trong một ứng dụng Java có sử dụng **Java Platform Module System (JPMS)**, việc file JAR tồn tại trên ổ đĩa không bảo đảm mọi code trong JVM có thể tìm thấy class bên trong JAR đó. Class có thể nằm trong một named module đã được resolve nhưng lại được định nghĩa bởi **class loader khác** với loader mà framework hoặc ứng dụng đang dùng. Nó cũng có thể nằm trong một **ModuleLayer con** hoặc layer anh em, không thuộc phạm vi tìm kiếm của loader hiện tại.

Khi gọi **Class.forName(...)**, **ClassLoader.loadClass(...)** hoặc cơ chế tự động discovery, ứng dụng có thể gặp **ClassNotFoundException** dù tên class và JAR có vẻ đúng. Muốn xử lý chính xác phải phân biệt **module discovery**, **module resolution**, **layer definition**, **class loading** và **module access**. Một sai lầm phổ biến là dùng **--add-exports** hoặc **--add-opens** để chữa lỗi không tìm thấy class, trong khi nguyên nhân thực tế là đang dùng sai loader hoặc đang tìm ở sai layer.

Bài học này trình bày quy trình điều tra ClassNotFoundException theo module graph và class loader, kèm ví dụ tái hiện custom ModuleLayer và các cách sửa phù hợp.

## 1. Những khái niệm cần phân biệt

Một class Java được nhận diện ở runtime bởi **tên nhị phân (binary name)** cùng với **defining class loader**. Với JPMS, class còn thuộc một **Module** object, và named module được định nghĩa trong một ModuleLayer.

Các khái niệm liên quan:

| Thành phần | Vai trò | Câu hỏi chẩn đoán |
|---|---|---|
| JAR hoặc exploded module | Chứa class và module metadata | File class thực sự có trong artifact không? |
| ModuleFinder | Tìm các module có thể quan sát được | Finder đang tìm ở path nào? |
| Configuration | Kết quả resolve root modules và dependency | Module chứa class đã được resolve chưa? |
| ModuleLayer | Định nghĩa các module trong runtime | Module nằm ở boot layer hay custom child layer? |
| ClassLoader | Tìm và định nghĩa class | Code đang yêu cầu loader nào tìm class? |
| Module exports/opens | Kiểm soát quyền truy cập | Class đã tìm thấy nhưng caller có quyền dùng hay reflect không? |
| ServiceLoader | Tìm implementation theo service contract | Framework đang tìm service từ layer nào? |

Chuỗi hoạt động thường thấy:

~~~text
Artifact (JAR hoặc exploded module)
    |
    v
ModuleFinder -> Configuration.resolve(...) hoặc resolveAndBind(...)
    |
    v
ModuleLayer.defineModules...(...)
    |
    v
Module object + defining ClassLoader
    |
    v
Class.forName / loadClass / ServiceLoader
    |
    v
Kiểm tra readability, exports/opens khi sử dụng class
~~~

Nếu lỗi xuất hiện ở từng bước khác nhau, tên exception và cách xử lý sẽ khác nhau. Không nên gom tất cả lỗi thành “JPMS không cho truy cập”.

## 2. ClassNotFoundException thực sự có nghĩa gì?

**ClassNotFoundException** là checked exception thường xuất hiện khi một lời gọi yêu cầu tải class theo tên nhưng class loader được sử dụng không thể tìm class đó:

~~~java
Class<?> type = Class.forName("com.acme.plugin.internal.Parser");
~~~

Hoặc:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = loader.loadClass("com.acme.plugin.internal.Parser");
~~~

Các lời gọi này có thể thất bại vì:

- Tên binary class sai, bao gồm package hoặc tên nested class.
- JAR không tồn tại trong những đường dẫn mà loader có thể tìm.
- Class nằm trong một module chưa được resolve.
- Module đã resolve nhưng được định nghĩa trong class loader của child layer khác.
- Code dùng system class loader để tìm class do plugin loader định nghĩa.
- Thread context class loader (TCCL) đang trỏ tới loader không thấy plugin.
- Plugin nằm ở sibling layer, không thuộc quan hệ delegation của caller.
- Một thư viện hoặc framework tạo loader riêng nhưng không được truyền đúng loader.

Lưu ý: Java có thể tải được một class mà sau đó vẫn không được phép truy cập class đó. **ClassNotFoundException** nói về việc tìm class, còn **IllegalAccessError**, **IllegalAccessException** hoặc **InaccessibleObjectException** có thể nói về việc sử dụng class/member sau khi nó đã được tìm thấy.

## 3. Cách class loader liên quan tới JPMS

Trong Java truyền thống, nhiều ứng dụng đặt thư viện trên classpath và dựa vào system/application class loader. Khi dùng JPMS, module system có thể định nghĩa nhiều named modules trong các class loader khác nhau. Với custom layer, những loader được tạo để định nghĩa layer không nhất thiết là system class loader.

Hai cách định nghĩa layer phổ biến:

~~~java
ModuleLayer layer = parentLayer.defineModulesWithOneLoader(
    configuration,
    ClassLoader.getSystemClassLoader()
);
~~~

và:

~~~java
ModuleLayer layer = parentLayer.defineModulesWithManyLoaders(
    configuration,
    ClassLoader.getSystemClassLoader()
);
~~~

Trong trường hợp thứ nhất, các module của layer được ánh xạ vào một loader mới. Trong trường hợp thứ hai, mỗi module trong layer có loader riêng. Tham số **ClassLoader.getSystemClassLoader()** ở đây là parent loader để xây dựng loader của layer, **không có nghĩa các module mới được định nghĩa trực tiếp bởi system class loader**.

Do đó, đoạn code sau có thể không tìm được class thuộc một plugin layer mới:

~~~java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
Class<?> pluginType =
    systemLoader.loadClass("com.acme.plugin.impl.PluginImpl");
~~~

Class có thể đã tồn tại trong plugin layer nhưng được định nghĩa bởi loader của layer đó. Phải tìm đúng loader của module plugin thay vì đoán rằng system loader nhìn thấy mọi class.

## 4. Class.forName dùng loader nào?

Có nhiều overload của **Class.forName** và chúng không tương đương.

### 4.1. Class.forName(String)

~~~java
Class<?> type = Class.forName("com.acme.plugin.impl.PluginImpl");
~~~

Overload này dùng defining class loader của class gọi phương thức để tìm class theo tên, theo ngữ nghĩa do API quy định. Nếu caller nằm ở host classpath hoặc boot layer, nó không tự chuyển sang loader của một child layer mới.

Nếu class chỉ được định nghĩa ở child layer, overload này có thể ném ClassNotFoundException ngay cả khi module plugin đã được resolve và được định nghĩa thành công.

### 4.2. Class.forName(String, boolean, ClassLoader)

~~~java
ClassLoader pluginLoader = pluginLayer.findLoader("com.acme.plugin");
Class<?> type = Class.forName(
    "com.acme.plugin.impl.PluginImpl",
    false,
    pluginLoader
);
~~~

Tham số cuối cho phép chỉ định loader cần sử dụng. Giá trị **false** yêu cầu không khởi tạo class chỉ vì lời gọi Class.forName; điều này hữu ích khi muốn quan sát class trước khi chạy static initializer.

Khi cần khởi tạo class, có thể dùng **true**, nhưng cần biết static initialization có thể kích hoạt code và gây exception khác. Chỉ dùng true khi cần hành vi khởi tạo.

### 4.3. Class.forName(Module, String)

JPMS còn cung cấp:

~~~java
Module module = pluginLayer
    .findModule("com.acme.plugin")
    .orElseThrow();

Class<?> type = Class.forName(
    module,
    "com.acme.plugin.impl.PluginImpl"
);
~~~

Overload này tìm class trong module được chỉ định và **trả về null nếu class không được tìm thấy trong module đó**; nó không có cùng hợp đồng ném ClassNotFoundException như overload String thông thường. Nó cũng không khởi tạo class.

Cần kiểm tra kết quả null và xử lý quyền truy cập khi dùng class. Class được tìm thấy trong module không bảo đảm một caller khác có thể gọi mọi constructor hoặc method của class đó.

## 5. ModuleLayer.findLoader(String) là điểm bắt đầu đúng

Khi đã có ModuleLayer của plugin, dùng **findLoader(moduleName)** để lấy loader định nghĩa module tương ứng trong layer:

~~~java
String moduleName = "com.acme.plugin";

ClassLoader loader = pluginLayer.findLoader(moduleName);

Class<?> type = loader.loadClass(
    "com.acme.plugin.impl.PluginImpl"
);
~~~

Hàm **findLoader** nhận **module name**, không nhận package name hoặc tên class. Nó hữu ích nhất khi code đã biết plugin module được định nghĩa tại layer nào.

Nếu module name không thuộc layer theo hợp đồng API, lời gọi có thể ném **IllegalArgumentException**; cần phân biệt lỗi đó với ClassNotFoundException từ bước tiếp theo.

Một cách kiểm tra rõ ràng:

~~~java
String moduleName = "com.acme.plugin";

Module module = pluginLayer
    .findModule(moduleName)
    .orElseThrow(() -> new IllegalStateException(
        "Expected plugin module is absent: " + moduleName
    ));

ClassLoader loader = module.getClassLoader();

Class<?> type = Class.forName(
    "com.acme.plugin.impl.PluginImpl",
    false,
    loader
);
~~~

**Module.getClassLoader()** trả về loader định nghĩa module. Với một số module nền tảng, loader có thể được biểu diễn bằng null để chỉ bootstrap loader; code chẩn đoán cần xử lý null mà không coi đó là lỗi.

Khi có nhiều layer, nên lấy Module object từ đúng layer và giữ nó cùng ngữ cảnh layer, thay vì chỉ lưu một module name string toàn cục.

## 6. Ví dụ tái hiện: class tồn tại nhưng host dùng sai loader

Ví dụ có hai phần: một plugin là named module, và một chương trình host chạy trên classpath tạo ModuleLayer cho plugin.

Cấu trúc project:

~~~text
project/
├── plugin-src/
│   └── com.acme.greeter.plugin/
│       ├── module-info.java
│       └── com/acme/greeter/impl/Greeter.java
├── host-src/
│   └── Host.java
├── plugin-out/
└── host-out/
~~~

Descriptor plugin:

~~~java
module com.acme.greeter.plugin {
    exports com.acme.greeter.impl;
}
~~~

Class plugin:

~~~java
package com.acme.greeter.impl;

public final class Greeter {
    public Greeter() {
    }

    public String hello() {
        return "Hello from plugin layer";
    }
}
~~~

Host code:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class Host {
    public static void main(String[] args) throws Exception {
        ModuleLayer parent = ModuleLayer.boot();

        ModuleFinder pluginFinder =
            ModuleFinder.of(Path.of("plugin-out"));

        Configuration config =
            parent.configuration().resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.acme.greeter.plugin")
            );

        ModuleLayer pluginLayer =
            parent.defineModulesWithOneLoader(
                config,
                ClassLoader.getSystemClassLoader()
            );

        String className =
            "com.acme.greeter.impl.Greeter";

        try {
            Class.forName(className);
            System.out.println("Unexpected: host found class");
        } catch (ClassNotFoundException expected) {
            System.out.println(
                "Host loader cannot find plugin class"
            );
        }

        ClassLoader pluginLoader =
            pluginLayer.findLoader("com.acme.greeter.plugin");

        Class<?> greeterType =
            Class.forName(className, true, pluginLoader);

        Object instance =
            greeterType.getConstructor().newInstance();

        Object result =
            greeterType.getMethod("hello").invoke(instance);

        System.out.println(result);
    }
}
~~~

Biên dịch plugin thành exploded named module:

~~~bash
javac --module-source-path plugin-src \
      -d plugin-out \
      -m com.acme.greeter.plugin
~~~

Biên dịch host classpath:

~~~bash
javac -d host-out host-src/Host.java
~~~

Chạy host:

~~~bash
java --class-path host-out Host
~~~

Nếu directory layout đúng, host tạo child ModuleLayer từ module nằm trong **plugin-out**. Lời gọi **Class.forName(className)** từ host classpath không thấy plugin class trong loader của child layer. Sau đó host lấy đúng **pluginLayer.findLoader(...)** và tìm class thành công.

Kết quả minh họa:

~~~text
Host loader cannot find plugin class
Hello from plugin layer
~~~

Ở đây package plugin được export để host có thể gọi public constructor và method bằng reflection. Nếu không export package, class loader có thể vẫn tìm được class nhưng reflective invocation từ host có thể gặp lỗi access; đó là vấn đề khác với ClassNotFoundException.

## 7. Điều gì xảy ra khi plugin chưa được resolve?

Nếu module chưa được đưa vào Configuration, **findLoader** của layer không thể cung cấp loader cho module đó. Dù JAR có trong thư mục, module system chỉ giải quyết tập root và dependency cần thiết trong ngữ cảnh đã chọn.

Ví dụ có các JAR:

~~~text
plugins/
├── com.acme.greeter.plugin.jar
└── com.acme.codec.plugin.jar
~~~

Nếu configuration resolve chỉ root **com.acme.greeter.plugin** và module này không requires codec, module **com.acme.codec.plugin** có thể chưa được resolve.

Có thể kiểm tra configuration ngay sau resolve:

~~~java
config.modules().stream()
    .map(resolved -> resolved.name())
    .sorted()
    .forEach(System.out::println);
~~~

Và sau khi tạo layer:

~~~java
boolean inLayer = pluginLayer
    .findModule("com.acme.codec.plugin")
    .isPresent();

System.out.println(inLayer);
~~~

Nếu module không có trong graph, không giải quyết bằng cách thay loader tùy tiện. Cần xem lại root set, requires hoặc service binding tùy kiến trúc.

Những lỗi phát sinh trong bước module resolution thường là **FindException** hoặc **ResolutionException**, không phải ClassNotFoundException của lời gọi loadClass sau đó. Đọc đúng điểm phát sinh exception để tránh sửa nhầm.

## 8. Boot layer, child layer và sibling layer

Khi chạy bằng Java launcher theo module path, root application và dependency thường được định nghĩa trong **boot layer**. Khi ứng dụng tự tạo **custom ModuleLayer**, modules mới có thể được định nghĩa trong layer con.

Sơ đồ:

~~~text
Boot layer
├── com.acme.host
└── com.acme.plugin.api
       |
       +-- CSV plugin layer
       |   └── com.acme.csv.plugin
       |
       +-- JSON plugin layer
           └── com.acme.json.plugin
~~~

CSV và JSON có thể nằm trong **hai sibling layers**. Các layer đó không tự động tìm class của nhau thông qua cùng một loader. Một class chỉ nằm trong CSV plugin layer không vì thế xuất hiện khi JSON plugin loader được yêu cầu tìm class đó.

Khi module API dùng chung, nên đặt API ở boot layer hoặc parent layer phù hợp rồi cho plugin modules yêu cầu API đó. Host và plugin trao đổi qua những interface/DTO có cùng class identity.

Một sai lầm thường gặp là giả định:

~~~java
Class.forName("com.acme.csv.internal.CsvParser");
~~~

sẽ tự tìm trong tất cả ModuleLayer đang tồn tại. JVM không cung cấp một kho tìm class toàn cục kiểu đó. Mỗi lời gọi class loading dùng loader cụ thể.

Nếu ứng dụng quản lý plugin layer động, nên duy trì ánh xạ có chủ đích từ **plugin ID -> ModuleLayer -> module name -> loader**. Cách này giúp xác định nguồn nạp và dừng plugin theo vòng đời mà không quét mù tất cả class loaders.

## 9. Parent delegation có ý nghĩa gì?

Class loader thường có cơ chế delegation tới parent loader. Tuy nhiên, các loader do module system tạo còn phải tôn trọng mapping giữa named module và defining loader; không nên chỉ suy luận theo thuật toán parent-first đơn giản của classpath truyền thống.

Nếu loader của child layer có parent là system loader, điều đó **không** khiến system loader biết tìm class mới trong child. Delegation thường đi từ yêu cầu của child loader tới parent khi cần, không tự tạo chiều ngược để parent đi tìm trong mọi child loader.

Vì vậy:

~~~java
ClassLoader parentLoader =
    ClassLoader.getSystemClassLoader();

ClassLoader pluginLoader =
    pluginLayer.findLoader("com.acme.greeter.plugin");
~~~

Hai loader này có thể khác nhau. Một class do pluginLoader định nghĩa không mặc nhiên tải được bằng parentLoader.

Nếu một framework được cài đặt ở parent layer và tự gọi Class.forName từ code framework, nó có thể tìm với loader không thấy plugin. Phương án sửa tốt nhất thường là cung cấp loader/plugin layer đúng cho framework nếu API của framework hỗ trợ, hoặc sử dụng extension mechanism theo service contract.

## 10. Thread Context ClassLoader (TCCL)

Nhiều framework Java và thư viện legacy tra cứu class bằng **Thread.currentThread().getContextClassLoader()**. TCCL được gắn với thread, không tự đồng bộ với ModuleLayer chứa plugin.

Ví dụ:

~~~java
ClassLoader contextLoader =
    Thread.currentThread().getContextClassLoader();

System.out.println(contextLoader);
~~~

Nếu framework cần plugin class nhưng TCCL vẫn là system loader, thao tác discovery dựa trên TCCL có thể gặp ClassNotFoundException hoặc không phát hiện extension.

Có thể đặt TCCL đúng cho một phạm vi thực thi có kiểm soát:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

ClassLoader pluginLoader =
    pluginLayer.findLoader("com.acme.greeter.plugin");

try {
    thread.setContextClassLoader(pluginLoader);
    runFrameworkIntegration();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Trong ví dụ, **runFrameworkIntegration()** đại diện cho công việc framework, không phải API JDK có sẵn. Khi triển khai, thay bằng phương thức thực sự của thư viện đang dùng.

Điều quan trọng:

- Không thay TCCL của thread pool vĩnh viễn chỉ để chữa một test.
- Luôn khôi phục loader trước đó trong finally.
- Không giả định mọi framework dùng TCCL; một số dùng loader định nghĩa class framework hoặc loader được truyền tường minh.
- Không dùng TCCL để cố “ép” named module đọc những module mà module graph không cho phép.
- Cẩn thận với thread, executor hoặc callback giữ tham chiếu tới plugin loader và cản trở việc thu hồi plugin.

Nếu framework cho phép truyền class loader trực tiếp, cách này thường rõ ràng và dễ kiểm soát hơn thay đổi TCCL trên thread.

## 11. ServiceLoader và ModuleLayer

Với plugin architecture, việc host nạp implementation class theo tên string có thể gây coupling vào package nội bộ. JPMS cung cấp **ServiceLoader** để consumer làm việc với service interface.

Service API:

~~~java
module com.acme.plugin.api {
    exports com.acme.plugin.api;
}
~~~

Plugin provider:

~~~java
module com.acme.greeter.plugin {
    requires com.acme.plugin.api;

    provides com.acme.plugin.api.GreeterService
        with com.acme.greeter.impl.DefaultGreeter;
}
~~~

Module consumer:

~~~java
module com.acme.host {
    requires com.acme.plugin.api;
    uses com.acme.plugin.api.GreeterService;
}
~~~

Sau khi provider module được resolve và định nghĩa vào plugin layer phù hợp, host có thể tìm service:

~~~java
ServiceLoader<GreeterService> services =
    ServiceLoader.load(pluginLayer, GreeterService.class);

for (GreeterService service : services) {
    System.out.println(service.hello());
}
~~~

Đây là cách giảm nhu cầu gọi:

~~~java
Class.forName("com.acme.greeter.impl.DefaultGreeter");
~~~

Tuy nhiên, ServiceLoader vẫn cần provider module hiện diện trong layer phù hợp, và service API type phải có cùng class identity giữa host/provider.

Khi dùng một custom layer, overload **ServiceLoader.load(layer, serviceType)** thường giúp thể hiện đúng nơi tìm provider. Khi dùng overload dựa vào context class loader, kết quả có thể khác tùy loader của thread và cấu hình framework.

Lỗi **ServiceConfigurationError** do provider configuration hoặc construction sai không nên tự động được xem là ClassNotFoundException. Cần đọc nguyên nhân gốc và metadata uses/provides của provider.

## 12. Class identity: tìm thấy cùng tên vẫn có thể không cast được

Một vấn đề khác là hai loader định nghĩa hai class có cùng tên nhị phân. Điều này có thể xảy ra khi mỗi plugin đóng gói bản sao của cùng một API JAR.

Giả sử host dùng:

~~~java
com.acme.plugin.api.GreeterService
~~~

và plugin vô tình nạp một bản khác của API class từ loader riêng. Hai Class object có cùng tên nhưng khác defining loader, vì vậy có thể không tương thích khi cast:

~~~java
GreeterService service = (GreeterService) pluginInstance;
~~~

Kết quả có thể là **ClassCastException**, dù tên class trong thông báo rất giống nhau.

Kiểm tra:

~~~java
Class<?> hostApi = GreeterService.class;
Class<?> pluginApi = pluginInstance.getClass()
    .getInterfaces()[0];

System.out.println(hostApi == pluginApi);
System.out.println(hostApi.getClassLoader());
System.out.println(pluginApi.getClassLoader());
~~~

Đây là ví dụ minh họa: trong ứng dụng thật, một provider có thể implement nhiều interface, nên không nên dựa vào phần tử đầu tiên của **getInterfaces()** để kết luận. Hãy tìm chính xác interface type cần kiểm tra trong graph kế thừa.

Cách thiết kế bền vững là đưa module API vào một parent layer chung mà host và plugin đều đọc, tránh đóng gói lặp module API trong các child layers. Class identity khác nhau không được giải quyết bằng **--add-opens** hoặc **--add-exports**.

## 13. Phân biệt các loại exception

| Exception hoặc dấu hiệu | Giai đoạn thường gặp | Cách điều tra ưu tiên |
|---|---|---|
| **ClassNotFoundException** | Loader được yêu cầu không tìm thấy class theo tên | Binary name, class loader, layer, artifact location |
| **FindException** | Resolution không tìm được module hoặc descriptor cần thiết | ModuleFinder, module path, tên module, dependency |
| **ResolutionException** | Module graph không hợp lệ | requires, package conflicts, readability graph |
| **LayerInstantiationException** | Không định nghĩa được configuration vào loader/layer | Loader mapping, split package, parent layers |
| **NoClassDefFoundError** | JVM không định nghĩa/khởi tạo được class khi cần | Dependency class, linkage, class initialization, nguyên nhân gốc |
| **ClassCastException** | Class types không tương thích tại runtime | Defining loaders, API duplication, type identity |
| **IllegalAccessError** | Truy cập class/member vi phạm kiểm soát truy cập khi liên kết hoặc chạy | exports/readability, modifiers, binary compatibility |
| **InaccessibleObjectException** | Deep reflection bị strong encapsulation chặn | opens, qualified opens, module framework |
| **ServiceConfigurationError** | Service/provider không hợp lệ hoặc không nạp được | uses, provides, provider instance, ServiceLoader scope |

**NoClassDefFoundError** không đồng nghĩa với ClassNotFoundException. Nó có thể xuất hiện khi JVM đang liên kết một class nhưng dependency class của nó không thể được tìm, hoặc class initialization từng thất bại. Cần đọc cả **Caused by** và thời điểm phát sinh.

Tương tự, một **FindException** phát sinh khi chưa có ModuleLayer thì không nên xử lý bằng cách đổi TCCL trong code chạy sau đó. Code có thể chưa bắt đầu thực thi.

## 14. Quy trình chẩn đoán từng bước

Khi nhận stack trace có ClassNotFoundException:

### Bước 1. Xác minh binary class name

Ghi tên class chính xác từ exception. Với nested class, binary name có dấu **$** thay vì dấu chấm giữa outer và inner class.

Ví dụ:

~~~java
Class.forName("com.acme.order.Outer$Inner");
~~~

Tên này khác với canonical name **com.acme.order.Outer.Inner**. Kiểm tra code đang dùng **Class.getName()** hay **Class.getCanonicalName()** nếu tên được tạo động.

### Bước 2. Kiểm tra artifact thực sự chứa class

Dùng:

~~~bash
jar --list --file plugins/com.acme.greeter.plugin.jar
~~~

Tìm entry tương ứng:

~~~text
com/acme/greeter/impl/Greeter.class
~~~

Nếu class không có trong artifact, vấn đề nằm ở build/publish hoặc artifact version, không phải module access.

### Bước 3. Xác nhận tên và loại module

~~~bash
jar --describe-module --file plugins/com.acme.greeter.plugin.jar
~~~

Xác định module name thực tế. Đừng suy luận module name từ file JAR. Nếu là automatic module, descriptor được suy ra có thể có tên khác với dự kiến.

### Bước 4. Xác nhận module đã resolve

Nếu dùng boot layer:

~~~java
System.out.println(
    ModuleLayer.boot().findModule("com.acme.greeter.plugin")
);
~~~

Nếu dùng plugin layer:

~~~java
System.out.println(
    pluginLayer.findModule("com.acme.greeter.plugin")
);
~~~

Với custom layer, đối chiếu cả **configuration.modules()** ngay sau resolution. Không dùng boot layer để kết luận các child/sibling layers có hay không có module.

### Bước 5. Xác định loader được yêu cầu

Ghi lại:

~~~java
ClassLoader systemLoader =
    ClassLoader.getSystemClassLoader();

ClassLoader contextLoader =
    Thread.currentThread().getContextClassLoader();

ClassLoader moduleLoader =
    pluginLayer.findLoader("com.acme.greeter.plugin");

System.out.println("System: " + systemLoader);
System.out.println("Context: " + contextLoader);
System.out.println("Module: " + moduleLoader);
~~~

Nếu framework có API cung cấp loader, ghi cả loader được truyền vào framework.

### Bước 6. Thử tìm class bằng loader đúng

~~~java
ClassLoader moduleLoader =
    pluginLayer.findLoader("com.acme.greeter.plugin");

Class<?> type = Class.forName(
    "com.acme.greeter.impl.Greeter",
    false,
    moduleLoader
);

System.out.println(type.getModule().getName());
~~~

Nếu cách này thành công nhưng loader trước đó không tìm được class, bằng chứng chỉ ra nguyên nhân chính là loader/layer mismatch.

### Bước 7. Kiểm tra exports hoặc opens sau khi load được class

Khi class đã được tìm, nếu reflective constructor hoặc method invocation thất bại vì access, hãy kiểm tra module boundary:

~~~java
Module source = type.getModule();
Module caller = Host.class.getModule();

String pkg = type.getPackageName();

System.out.println(source.isExported(pkg, caller));
System.out.println(source.isOpen(pkg, caller));
~~~

**Host.class** là ví dụ class caller thực sự đang dùng; cần thay bằng đúng class trong code. Các quyền này không quyết định loader có tìm class được hay không, mà quyết định loại truy cập nào được chấp nhận.

### Bước 8. Ghi kết quả và sửa đúng tầng

Kết luận nên có dạng:

~~~text
Class name: com.acme.greeter.impl.Greeter
Owning module: com.acme.greeter.plugin
Module layer: plugin child layer
Defining loader: loader của plugin layer
Failing lookup: Class.forName(String) từ host
Successful lookup: Class.forName(name, false, pluginLoader)
Fix: truyền pluginLoader hoặc dùng ServiceLoader.load(pluginLayer, API.class)
~~~

Ghi đủ ngữ cảnh để người khác tái hiện, thay vì chỉ chú thích “đã thêm --add-opens và chạy được”.

## 15. Công cụ quan sát class loading

### 15.1. Log class loading của JVM

Trên JDK hiện đại, có thể bật unified logging:

~~~bash
java -Xlog:class+load=info \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Log giúp quan sát class nào được nạp và nguồn của nó. Output có thể rất lớn, nên chỉ bật khi cần điều tra, lưu log có kiểm soát và lọc theo tên package liên quan.

Với những môi trường khác, **-verbose:class** cũng là tùy chọn quan sát class loading thường dùng.

### 15.2. In thông tin Module/ClassLoader

~~~java
static void inspect(Class<?> type) {
    Module module = type.getModule();
    ClassLoader loader = type.getClassLoader();

    System.out.println("Class: " + type.getName());
    System.out.println("Module: " + module.getName());
    System.out.println("Layer: " + module.getLayer());
    System.out.println("Loader: " + loader);
    System.out.println("Package: " + type.getPackageName());
}
~~~

Hàm này chỉ chạy sau khi class đã được tìm. Nếu vấn đề là ClassNotFoundException, cần log thêm loader và layer được dùng trong thao tác tìm class bị lỗi.

### 15.3. Quan sát module resolution

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Lệnh này mô tả resolution của launcher. Nó hữu ích khi module chưa được chọn vào boot layer, nhưng không thay thế việc xem custom ModuleLayer được tạo sau khi ứng dụng khởi động.

## 16. Khi lỗi xảy ra trong test hoặc IDE

Một project có thể pass khi chạy bằng Maven/Gradle nhưng fail trong IDE hoặc ngược lại. Nguyên nhân thường nằm ở khác biệt về runtime graph và loader setup.

Những cấu hình cần so sánh:

- Test classes chạy trên classpath, trong named test module hay được patch vào production module?
- JavaExec/Test task truyền module path và root modules nào?
- IDE tạo runtime classpath và module path giống CI hay không?
- Framework test sử dụng system loader, TCCL hay loader của test module?
- Test plugin có tạo custom layer riêng để nạp test engines không?
- Các JAR plugin có được copy vào đúng thư mục mà ModuleFinder được cấu hình không?
- JVM flags **--add-modules**, **--add-reads** hoặc **--patch-module** có khác nhau giữa môi trường không?

Nếu lỗi chỉ xuất hiện trong JUnit/serialization/plugin discovery, hãy kiểm tra loader mà framework sử dụng. Một bài test chạy thành công từ classpath chưa chứng minh module trong custom layer cũng được nạp đúng ở production.

Để tránh phụ thuộc môi trường, nên có integration test tạo ModuleLayer từ đúng artifacts dự kiến phát hành và thực hiện class/service discovery bằng API mà production sử dụng.

## 17. Những cách sửa bền vững

### 17.1. Truyền loader tường minh

Nếu API hiện có cho phép truyền **ClassLoader**, dùng loader của module/layer sở hữu class:

~~~java
ClassLoader loader =
    pluginLayer.findLoader("com.acme.greeter.plugin");

Class<?> type = Class.forName(
    "com.acme.greeter.impl.Greeter",
    false,
    loader
);
~~~

Cách này phù hợp cho công cụ plugin loader hoặc framework nạp class bằng tên string.

### 17.2. Dùng ServiceLoader thay vì tên implementation

Nếu host chỉ cần một capability, thiết kế service API trong parent layer và đăng ký provider bằng **provides**. Host gọi **ServiceLoader.load(layer, serviceType)** để tránh phụ thuộc tên implementation class.

### 17.3. Sửa root set và resolution

Nếu module chưa resolve, điều chỉnh root modules hoặc service binding theo thiết kế. Đổi loader không giúp tìm class từ một module chưa được định nghĩa.

### 17.4. Đồng nhất service API identity

Nếu host và plugin đang dùng hai bản API thuộc loader khác nhau, đưa API lên parent layer chung, loại bỏ bản đóng gói lặp và kiểm tra type identity.

### 17.5. Cấu hình TCCL có phạm vi

Nếu framework bắt buộc dùng TCCL, đặt đúng loader chỉ trong phạm vi gọi framework rồi restore trong finally. Tránh để background thread hoặc pool giữ loader sau khi plugin ngừng hoạt động.

### 17.6. Không dùng escape hatch sai mục tiêu

Các tùy chọn **--add-exports**, **--add-opens** và **--add-reads** thay đổi quyền module; chúng không tự tạo child layer, không tải lại class và không biến system loader thành loader của plugin.

Chỉ sử dụng khi stack trace xác nhận vấn đề thật sự là readability, package export hoặc reflection. Nếu class chưa được loader tìm thấy, phải sửa nguồn class/loading trước.

## 18. Bài tập thực hành

1. Tạo named module **com.acme.greeter.plugin** và class Greeter như ví dụ.
2. Biên dịch plugin thành exploded module trong **plugin-out**.
3. Viết host trên classpath, tạo child layer bằng **Configuration.resolve** và **defineModulesWithOneLoader**.
4. Gọi **Class.forName(String)** từ host và quan sát ClassNotFoundException.
5. Lấy loader bằng **pluginLayer.findLoader(moduleName)** rồi gọi **Class.forName(name, false, loader)**.
6. In **Class.getModule()**, **Module.getLayer()** và **Class.getClassLoader()** sau khi tìm được class.
7. Thử đổi root module hoặc xóa artifact khỏi pluginFinder để phân biệt FindException và ClassNotFoundException.
8. Đặt hai plugin ở sibling layers, thử nạp class của plugin A bằng loader của plugin B.
9. Viết integration test dùng ServiceLoader thay cho hard-coded implementation class name.
10. Đặt TCCL sang loader plugin trong một phạm vi try/finally và xác minh nó được khôi phục.
11. Đưa một bản sao service API vào plugin layer, quan sát vấn đề class identity và sửa bằng parent API module.
12. Thử bỏ exports của package plugin: xác nhận class loading và reflective access là hai bước khác nhau.
13. Sử dụng **-Xlog:class+load=info** để quan sát class source khi nạp.
14. Viết một bảng chẩn đoán cho bốn lỗi: FindException, ClassNotFoundException, ClassCastException và InaccessibleObjectException.
15. So sánh command line thực tế của IDE, CI và production khi plugin discovery không nhất quán.

## 19. Những điểm cần ghi nhớ

- **ClassNotFoundException** thường cho biết loader được yêu cầu không tìm thấy class theo binary name.
- Có JAR trên đĩa hoặc module trên module path chưa bảo đảm class đã được resolve và loader hiện tại tìm được.
- Một custom ModuleLayer có loader riêng; system loader không tự nhìn thấy class của child layer.
- **Class.forName(String)** và **Class.forName(String, boolean, ClassLoader)** có thể dùng loader khác nhau.
- **Class.forName(Module, String)** trả về null nếu không tìm được class trong module được nêu.
- **ModuleLayer.findLoader(moduleName)** là cách rõ ràng để lấy loader của named module trong layer đã định nghĩa.
- Module chưa thuộc configuration thì không thể khắc phục bằng cách chỉ đổi TCCL.
- Sibling layers không tự động chia sẻ implementation class; API dùng chung nên nằm ở parent layer.
- **TCCL** quan trọng với một số framework legacy, nhưng phải có phạm vi và khôi phục sau khi sử dụng.
- Hai class cùng tên nhưng defining loader khác có thể không tương thích khi cast.
- **ServiceLoader** giúp giảm coupling vào implementation class name và cho phép chọn provider theo layer.
- **--add-opens** và **--add-exports** không phải cách trực tiếp sửa lỗi class loader không tìm thấy class.
- Khi debug, log **binary name, module name, layer, defining loader, caller loader, classpath/module path và root set**.

**Cách xử lý ClassNotFoundException do loader hoặc layer sai là xác định class thuộc module/layer nào, xác nhận module đã được resolve rồi tìm bằng đúng defining loader.** Khi phân biệt được class discovery, module resolution và quyền truy cập, ta có thể sửa lỗi ở đúng tầng và tránh các escape hatch không cần thiết.
# Thread context class loader và ServiceLoader

Trong Java, **class loader** quyết định cách JVM tìm và định nghĩa class. Đối với các hệ thống có plugin, framework hoặc application server, không phải mọi class đều được nạp bởi cùng một class loader. Một class thuộc thư viện lõi có thể được nạp bởi class loader cha, trong khi implementation của thư viện đó nằm trong một JAR do class loader con quản lý.

Đây là bối cảnh của **Thread Context Class Loader (TCCL)** và **ServiceLoader**. TCCL cung cấp cho code đang chạy một class loader *theo ngữ cảnh của luồng*. ServiceLoader có thể dùng class loader đó để phát hiện các provider của một service. Hiểu cách chúng kết hợp giúp chẩn đoán lỗi plugin không được tìm thấy, lỗi kiểu dữ liệu khác nhau giữa class loader và những tình huống hoạt động khác nhau giữa classpath với Java Platform Module System (JPMS).

## 1. Class loader và Service Provider Interface

Java Service Provider Interface (SPI) cho phép phần tiêu thụ khai báo **service contract**, còn một hoặc nhiều phần khác cung cấp implementation.

Ví dụ contract:

~~~java
package com.example.spi;

public interface GreetingService {
    String greet(String name);
}
~~~

Một provider:

~~~java
package com.example.provider;

import com.example.spi.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Code tiêu thụ:

~~~java
import com.example.spi.GreetingService;
import java.util.ServiceLoader;

ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : services) {
    System.out.println(service.greet("An"));
}
~~~

Ứng dụng không cần hard-code tên **EnglishGreeting**. Việc tìm provider dựa trên cấu hình service mà ServiceLoader có thể quan sát, và việc nạp provider phụ thuộc vào môi trường class loader/module layer.

## 2. Thread Context Class Loader là gì?

Mỗi Thread có một context class loader. Có thể lấy hoặc thay đổi nó bằng:

~~~java
Thread current = Thread.currentThread();

ClassLoader context = current.getContextClassLoader();

current.setContextClassLoader(context);
~~~

**getContextClassLoader()** trả về class loader ngữ cảnh của luồng hiện tại. **setContextClassLoader(ClassLoader)** thiết lập ngữ cảnh mới cho luồng.

TCCL không đồng nghĩa với class loader đã định nghĩa class đang chạy:

~~~java
ClassLoader definingLoader =
        SomeClass.class.getClassLoader();

ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();
~~~

Hai giá trị có thể giống nhau, nhưng không bắt buộc.

- **Defining class loader** gắn với danh tính của một class khi class được định nghĩa.
- **TCCL** là thuộc tính của thread, có thể được code thay đổi trong lúc thread chạy.
- **Class.getClassLoader()** trả về defining loader của class.
- **Thread.getContextClassLoader()** trả về class loader do ngữ cảnh xử lý hiện tại lựa chọn.

Một class do loader cha nạp có thể đang chạy trên thread mà TCCL trỏ đến loader con. Đây là cách thư viện framework do parent loader định nghĩa có thể phối hợp với plugin nằm trong child loader.

## 3. Vì sao cần TCCL?

Class loader thường dùng cơ chế delegation: loader con có thể hỏi loader cha trước khi tự tìm class. Nếu một thư viện nằm ở loader cha, nó có thể không trực tiếp nhìn thấy các class được nạp riêng bởi loader con.

Minh họa:

~~~text
Parent class loader
    |
    +-- GreetingService interface
    +-- Host framework
    |
    v
Plugin class loader (child)
    |
    +-- EnglishGreeting implementation
    +-- META-INF/services/com.example.spi.GreetingService
~~~

Framework biết interface **GreetingService**, nhưng implementation tồn tại trong JAR plugin. Nếu framework chỉ dùng defining loader của chính class framework, nó có thể không tìm được resource và implementation nằm dưới plugin loader.

TCCL cho phép thread mang “ngữ cảnh lớp” do nơi gọi thiết lập. Framework có thể dùng loader đó khi khám phá provider, thay vì mặc định giới hạn vào defining loader của framework.

TCCL không biến class loader cha thành owner của class plugin và cũng không tạo một quan hệ delegation ngược. Nó chỉ cung cấp **một đối tượng ClassLoader được chọn cho API biết sử dụng TCCL**.

## 4. ServiceLoader.load(Service.class) dùng loader nào?

Overload quen thuộc:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);
~~~

sử dụng **context class loader của thread hiện tại** để thực hiện việc tìm kiếm theo class loader. Có thể hình dung tương đương với:

~~~java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class, context);
~~~

Điều này lý giải vì sao cùng một lời gọi **ServiceLoader.load(...)** có thể phát hiện provider khác nhau trong những môi trường khác nhau. TCCL ở lúc tạo ServiceLoader có thể do application server, test runner, plugin manager hoặc code ứng dụng thiết lập.

Điểm quan trọng: ServiceLoader còn có cơ chế khám phá **named-module providers** được khai báo bằng JPMS. Vì vậy, không nên diễn giải đơn giản rằng nó chỉ đọc file META-INF/services. Phạm vi provider cụ thể phụ thuộc overload ServiceLoader, module graph/layer, class loader và cấu hình service liên quan.

## 5. Những overload quan trọng của ServiceLoader

Ba cách sử dụng thường gặp:

~~~java
// 1. Sử dụng TCCL của thread hiện tại.
ServiceLoader<GreetingService> a =
        ServiceLoader.load(GreetingService.class);

// 2. Chỉ định class loader tường minh.
ServiceLoader<GreetingService> b =
        ServiceLoader.load(
                GreetingService.class,
                pluginClassLoader
        );

// 3. Tìm service providers trong một ModuleLayer.
ServiceLoader<GreetingService> c =
        ServiceLoader.load(
                pluginLayer,
                GreetingService.class
        );
~~~

So sánh:

| Cách gọi | Ngữ cảnh khám phá | Phù hợp khi |
|---|---|---|
| **load(Service.class)** | Context class loader của thread | Framework hoặc ứng dụng dùng TCCL |
| **load(Service.class, loader)** | Class loader được chỉ định | Plugin manager đã biết loader cần dùng |
| **load(layer, Service.class)** | Module layer được chỉ định và các parent layer | Plugin được tổ chức thành named modules trong JPMS |

Khi ứng dụng biết chính xác class loader của plugin, việc truyền class loader trực tiếp thường rõ ràng hơn việc thay đổi TCCL cho toàn bộ đoạn xử lý. Nếu ứng dụng quản lý plugin bằng ModuleLayer, overload theo layer thường phù hợp hơn vì nó diễn tả đúng ranh giới module cần khám phá.

## 6. Ví dụ classpath provider với META-INF/services

Trong cách tổ chức SPI truyền thống trên classpath, JAR provider thường khai báo một resource có tên:

~~~text
META-INF/services/com.example.spi.GreetingService
~~~

Nội dung file là tên đầy đủ của provider class:

~~~text
com.example.provider.EnglishGreeting
~~~

Đóng gói JAR provider:

~~~text
english-greeting.jar
├── META-INF/
│   └── services/
│       └── com.example.spi.GreetingService
└── com/
    └── example/
        └── provider/
            └── EnglishGreeting.class
~~~

Provider class thực hiện **GreetingService**, có constructor public không tham số trong mô hình provider class classpath điển hình, và được cung cấp bằng một class loader có thể tìm thấy resource service cùng class đó.

Code tìm provider:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);

for (GreetingService provider : services) {
    System.out.println(provider.getClass().getName());
}
~~~

Để cơ chế này hoạt động, TCCL phải có khả năng thấy metadata **META-INF/services/** và class implementation thông qua các quy tắc tìm resource/class của loader tương ứng.

File service configuration phải chứa tên class chính xác. Nếu service provider file bị loại khỏi JAR khi packaging, provider sẽ không được khám phá theo cơ chế cấu hình classpath đó, dù class **EnglishGreeting** vẫn tồn tại.

## 7. Ví dụ nạp plugin bằng URLClassLoader

Giả sử ứng dụng đã biết đường dẫn tới JAR provider ngoài. Có thể tạo loader riêng cho plugin:

~~~java
import com.example.spi.GreetingService;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class PluginDemo {
    public static void main(String[] args) throws Exception {
        Path pluginJar = Path.of("plugins/english-greeting.jar");
        URL url = pluginJar.toUri().toURL();

        ClassLoader apiLoader =
                GreetingService.class.getClassLoader();

        try (URLClassLoader pluginLoader =
                     new URLClassLoader(
                             new URL[] {url},
                             apiLoader)) {

            ServiceLoader<GreetingService> services =
                    ServiceLoader.load(
                            GreetingService.class,
                            pluginLoader);

            for (GreetingService service : services) {
                System.out.println(service.greet("An"));
            }
        }
    }
}
~~~

Trong ví dụ:

1. Class **GreetingService** đã được ứng dụng nhìn thấy qua loader của API.
2. URLClassLoader có parent là loader của API.
3. Plugin loader được cung cấp JAR chứa provider.
4. ServiceLoader tìm provider với loader được truyền tường minh.
5. URLClassLoader được đóng bằng try-with-resources.

Việc chọn parent phù hợp rất quan trọng. Nếu plugin loader nạp **một bản sao khác** của chính interface GreetingService, instance của provider có thể không tương thích với service type được ứng dụng truyền cho ServiceLoader, mặc dù tên class và package trông giống nhau.

Đóng URLClassLoader giải phóng tài nguyên của loader; thao tác này **không bảo đảm mọi class/plugin instance đang được tham chiếu sẽ lập tức được unload**. Việc unload còn phụ thuộc khả năng JVM thu hồi loader cùng toàn bộ đối tượng liên quan.

## 8. Sử dụng TCCL thay vì truyền loader trực tiếp

Một số framework chỉ gọi overload **ServiceLoader.load(Service.class)**. Nếu muốn framework đó khám phá provider nằm trong plugin loader, caller có thể đặt TCCL trong một phạm vi ngắn:

~~~java
Thread thread = Thread.currentThread();

ClassLoader previous =
        thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);

    ServiceLoader<GreetingService> services =
            ServiceLoader.load(GreetingService.class);

    for (GreetingService service : services) {
        System.out.println(service.greet("An"));
    }
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Điểm cần tuân thủ:

- **Lưu TCCL cũ** trước khi thay.
- **Khôi phục trong finally**, kể cả khi provider ném lỗi.
- Chỉ giữ TCCL mới trong phạm vi thật sự cần plugin context.
- Không giả định TCCL mới tự truyền sang mọi thread đang tồn tại.
- Không lưu thay đổi TCCL như một trạng thái vĩnh viễn của thread pool.

Đây là cách thường dùng để tương thích với thư viện framework phụ thuộc TCCL. Nếu có quyền sửa code gọi ServiceLoader và biết class loader cần dùng, overload **load(service, loader)** tránh tác dụng phụ trên ngữ cảnh thread.

## 9. Vì sao phải khôi phục TCCL?

TCCL là trạng thái mutable của Thread. Khi một thread được tái sử dụng để xử lý nhiều request hoặc task, giá trị context class loader còn sót lại có thể tác động đến request sau.

Ví dụ một thread pool có hai plugin:

~~~text
Task A:
  set TCCL -> plugin A
  load services
  (quên restore)

Task B trên cùng worker thread:
  ServiceLoader.load(Service.class)
  vẫn dùng TCCL -> plugin A
~~~

Task B có thể nhìn thấy provider sai, không thấy provider B hoặc vô tình giữ tham chiếu tới class loader A lâu hơn cần thiết.

Mẫu an toàn:

~~~java
static void withContextLoader(
        ClassLoader desired,
        Runnable action) {

    Thread current = Thread.currentThread();
    ClassLoader previous = current.getContextClassLoader();

    try {
        current.setContextClassLoader(desired);
        action.run();
    } finally {
        current.setContextClassLoader(previous);
    }
}
~~~

Gọi:

~~~java
withContextLoader(pluginLoader, () -> {
    ServiceLoader<GreetingService> loader =
            ServiceLoader.load(GreetingService.class);

    loader.forEach(provider ->
            System.out.println(provider.greet("Mai")));
});
~~~

Nếu callback ném RuntimeException, finally vẫn khôi phục TCCL. Không nên dựa vào việc thread sẽ tự kết thúc sau callback, vì executor thường tái sử dụng thread.

## 10. TCCL trong ExecutorService và CompletableFuture

Khi chạy task bất đồng bộ, cần biết **thread nào thực sự gọi ServiceLoader**.

Ví dụ:

~~~java
ExecutorService executor =
        java.util.concurrent.Executors.newFixedThreadPool(2);

try {
    Future<?> future = executor.submit(() -> {
        ClassLoader tccl =
                Thread.currentThread().getContextClassLoader();

        System.out.println("Task TCCL = " + tccl);
    });

    future.get();
} finally {
    executor.shutdown();
}
~~~

Thread context loader gắn với thread thực thi task, **không nhất thiết bằng** TCCL của thread đã submit task. Thread mới thông thường thừa hưởng context loader của thread tạo nó tại thời điểm tạo thread, nhưng các thread trong pool có thể đã tồn tại từ trước và được tái sử dụng.

Do đó, nếu task cần plugin context riêng, hãy thiết lập TCCL **ngay bên trong task**:

~~~java
Future<?> future = executor.submit(() -> {
    Thread current = Thread.currentThread();
    ClassLoader previous = current.getContextClassLoader();

    try {
        current.setContextClassLoader(pluginLoader);

        ServiceLoader<GreetingService> services =
                ServiceLoader.load(GreetingService.class);

        services.forEach(service ->
                System.out.println(service.greet("Mai")));
    } finally {
        current.setContextClassLoader(previous);
    }
});
~~~

Với **CompletableFuture.supplyAsync** hoặc **runAsync**, code cũng có thể chạy trên thread của một executor khác. Không nên giả định TCCL của thread gọi sẽ tự động được chuyển sang task.

Nếu framework cung cấp cơ chế propagation context riêng, cần hiểu nó có bao gồm TCCL hay không. TCCL không phải một biến toàn cục của JVM.

## 11. TCCL và class identity

Một class trong JVM được nhận diện theo **tên binary cùng defining class loader**. Hai class loader khác nhau có thể định nghĩa hai kiểu cùng tên nhưng chúng không phải cùng một class.

Ví dụ:

~~~text
Parent loader
    com.example.spi.GreetingService  (Class A)

Plugin loader khác
    com.example.spi.GreetingService  (Class B)

A != B
~~~

Nếu provider implement **Class B**, nhưng ứng dụng gọi:

~~~java
ServiceLoader.load(ClassA);
~~~

thì provider có thể không được chấp nhận như implementation của service type ứng dụng mong đợi, dù tên interface trong source hoàn toàn giống nhau.

Nguyên tắc cho plugin classpath:

- Service interface nên được cung cấp từ API shared ở loader cha.
- Plugin loader nên delegate tới loader cha đối với service contract.
- Không đóng gói một bản API service dư thừa bên trong mỗi plugin nếu nó có thể bị định nghĩa bằng loader riêng.
- Nếu bắt lỗi **ServiceConfigurationError** hoặc **ClassCastException**, hãy kiểm tra class identity qua **getClassLoader()**.

Một chẩn đoán hữu ích:

~~~java
System.out.println(
        GreetingService.class.getClassLoader());

System.out.println(
        provider.getClass().getClassLoader());

System.out.println(
        provider instanceof GreetingService);
~~~

Việc provider class dùng loader con khác loader API là bình thường. Điều quan trọng là provider implement đúng **Class object** của service contract mà ứng dụng sử dụng.

## 12. Named modules: uses và provides

Trong JPMS, một module có thể khai báo service mà nó tiêu thụ bằng **uses**:

~~~java
module com.example.host {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
~~~

Module API:

~~~java
module com.example.spi {
    exports com.example.spi;
}
~~~

Module provider:

~~~java
module com.example.greeting.en {
    requires com.example.spi;

    provides com.example.spi.GreetingService
        with com.example.greeting.en.EnglishGreeting;
}
~~~

Khác với classpath SPI chỉ dựa trên **META-INF/services/**, explicit named module dùng directive **provides ... with ...** để mô tả provider trong module descriptor.

Các nguyên tắc:

- Module tiêu thụ service cần khai báo **uses ServiceType** khi sử dụng ServiceLoader trong named module.
- Module cung cấp service khai báo **provides ServiceType with ProviderType**.
- Provider class không bắt buộc nằm trong package được export chỉ để đăng ký provider hợp lệ.
- Module provider và dependency của nó phải có thể được quan sát và phân giải phù hợp với module graph/layer.
- TCCL không thay thế các directive JPMS hoặc tự cho phép truy cập package không export.

Một lỗi thường gặp là module host có requires tới module API nhưng quên uses. ServiceLoader có thể báo lỗi cấu hình/caller không được phép sử dụng service khi gọi trong named module.

## 13. TCCL có thay thế module readability không?

Không. Hai cơ chế thuộc hai lớp khác nhau:

- **TCCL** chọn class loader theo ngữ cảnh của thread.
- **JPMS readability** xác định module nào được phép đọc module nào.
- **exports** xác định public API package nào được module khác truy cập.
- **opens** xác định package nào cho phép reflection sâu.

Ví dụ một module host đang chạy với TCCL trỏ đến plugin loader. Điều đó không tự tạo:

~~~java
requires com.example.plugin;
~~~

trong module-info.java, không thêm **--add-reads** và không mở package private để framework reflection.

Một class có thể được class loader tìm thấy nhưng vẫn bị chặn truy cập bởi quy tắc module, package hoặc Java access modifiers. Vì vậy, khi lỗi xảy ra, cần phân biệt:

1. Không tìm thấy provider/resource.
2. Tìm thấy provider nhưng không nạp được class.
3. Nạp được class nhưng không liên kết với service contract.
4. Có class nhưng thiếu module readability/exports/opens.
5. Tạo instance provider thất bại.

Mỗi tình huống yêu cầu cách sửa khác nhau.

## 14. ServiceLoader với ModuleLayer

Trong hệ thống plugin modular, một nhóm provider có thể được định nghĩa trong một **ModuleLayer** riêng.

Ví dụ khái quát:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer parent = ModuleLayer.boot();

ModuleFinder finder =
        ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
        parent.configuration().resolveAndBind(
                finder,
                ModuleFinder.of(),
                Set.of("com.example.greeting.en")
        );

ModuleLayer pluginLayer =
        parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader()
        );
~~~

Module plugin phải có trong thư mục plugins, dependency cần thiết của nó phải được các finder hoặc parent configuration cung cấp, và module service API cần được tổ chức để host cùng provider sử dụng đúng service type.

Sau khi tạo layer:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(
                pluginLayer,
                GreetingService.class
        );

for (GreetingService service : services) {
    System.out.println(service.greet("An"));
}
~~~

Overload **load(ModuleLayer, Service.class)** tìm provider trong layer đã chọn và các parent layer theo cơ chế module service. Đây là cách rõ ràng khi ứng dụng muốn khám phá provider trong một plugin layer cụ thể.

Với module host có tên, descriptor của host vẫn cần **uses com.example.spi.GreetingService**.

Điều quan trọng: **đổi TCCL không tự tạo ModuleLayer** và không đưa một JAR bất kỳ vào layer đó. ModuleFinder, Configuration và định nghĩa layer là các bước riêng.

## 15. So sánh load(Class) với load(ModuleLayer, Class)

Giả sử ứng dụng có:

~~~text
Boot layer
  com.example.host
  com.example.spi

Child layer
  com.example.greeting.en
  com.example.greeting.vi
~~~

Nếu host muốn tìm provider trong child layer một cách tường minh:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(childLayer, GreetingService.class);
~~~

Cách này thể hiện mục tiêu rõ hơn việc chỉ đổi TCCL và hy vọng loader đang dùng sẽ khám phá đúng module provider.

Ngược lại, nếu plugin chỉ là JAR classpath được URLClassLoader nạp và khai báo provider bằng **META-INF/services**, overload:

~~~java
ServiceLoader.load(GreetingService.class, pluginLoader);
~~~

thường đơn giản và phù hợp.

Không nên đồng nhất **classpath plugin class loader** với **JPMS module layer**. Hai thứ có thể cùng xuất hiện trong một kiến trúc, nhưng chúng không phải cùng một cơ chế quản lý module.

## 16. Lazy discovery, caching và reload()

**ServiceLoader** khám phá provider theo cơ chế lazy khi code duyệt iterator hoặc stream. Nó lưu cache các provider đã được phát hiện theo hành vi của ServiceLoader instance.

Ví dụ:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.getClass().getName());
}
~~~

Nếu cấu hình provider thay đổi và muốn ServiceLoader làm mới việc khám phá, API có phương thức:

~~~java
loader.reload();
~~~

Tuy nhiên, **reload() không tự tạo class loader mới**, không sửa TCCL của thread và không nạp lại bytecode của class đã được định nghĩa trong cùng class loader. Nó làm sạch cache provider của ServiceLoader để lần duyệt tiếp theo thực hiện khám phá lại theo nguồn mà instance đó sử dụng.

Nếu ứng dụng cần thay phiên bản plugin JAR đã nạp, có thể phải quản lý vòng đời của class loader hoặc module layer riêng, giải phóng tham chiếu cũ và tạo cấu hình mới. Đổi file JAR trên đĩa rồi gọi reload không nhất thiết khiến JVM thay thế class đã định nghĩa.

ServiceLoader instance cũng **không được thiết kế để sử dụng đồng thời từ nhiều thread mà không đồng bộ hóa**. Với hệ thống concurrent, nên quản lý việc khám phá/khởi tạo provider tại một điểm có kiểm soát, hoặc tạo các ServiceLoader instance độc lập theo ngữ cảnh.

## 17. Provider.type() và Provider.get()

Từ Java 9, **ServiceLoader.stream()** trả về những handle **ServiceLoader.Provider<S>**. Hai thao tác quan trọng:

- **type()** trả về class của kiểu provider tương ứng.
- **get()** lấy một service instance.

Ví dụ:

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);

services.stream()
        .filter(provider ->
                provider.type().getName().contains("English"))
        .map(ServiceLoader.Provider::get)
        .forEach(service ->
                System.out.println(service.greet("An")));
~~~

Điều này giúp lọc provider dựa trên metadata class trước khi tạo instance. Tuy nhiên, **type()** không bảo đảm provider sẽ tạo instance thành công khi get() được gọi.

Trong named module có provider method, kiểu được trả về bởi **type()** có thể phản ánh kiểu trả về của provider method, không nhất thiết là class factory công bố trong directive provides.

Khi plugin có nhiều implementation, không nên dựa vào thứ tự provider trừ khi ứng dụng tự định nghĩa chính sách lựa chọn rõ ràng.

## 18. Lỗi ServiceConfigurationError và cách chẩn đoán

ServiceLoader có thể phát sinh **ServiceConfigurationError** khi cấu hình provider không hợp lệ, provider class không được nạp, không tương thích với service hoặc không thể tạo instance.

Ví dụ:

~~~java
try {
    ServiceLoader<GreetingService> loader =
            ServiceLoader.load(GreetingService.class);

    for (GreetingService provider : loader) {
        System.out.println(provider.greet("An"));
    }
} catch (java.util.ServiceConfigurationError error) {
    System.err.println(
            "Service discovery failed: " + error.getMessage());
}
~~~

Nên xử lý lỗi này tại ranh giới tích hợp plugin và ghi log đủ thông tin về service type, class loader, module hoặc JAR liên quan. **ServiceConfigurationError** là một Error, không phải Exception thông thường, nên một nhánh catch Exception không nhất thiết bắt được lỗi này.

Không nên bắt và nuốt mọi Throwable chỉ để bỏ qua một plugin lỗi. Framework cần chính sách rõ ràng: lỗi provider có làm startup thất bại, bị cô lập hoặc được ghi log rồi chuyển sang provider khác?

Các nguyên nhân thường gặp:

- Thiếu **META-INF/services** trong JAR classpath provider.
- Tên provider class trong file service sai.
- Plugin loader không nhìn thấy JAR hoặc resource.
- Plugin nạp bản service API khác với bản host sử dụng.
- Named module consumer thiếu **uses**.
- Named module provider thiếu hoặc khai báo sai **provides**.
- Provider class không thể tạo instance.
- Module provider chưa được phân giải vào layer cần tìm kiếm.

## 19. Diagnostic: in TCCL, defining loader và module

Một đoạn chẩn đoán ngắn:

~~~java
static void inspectContext(Class<?> serviceType) {
    Thread thread = Thread.currentThread();

    ClassLoader tccl = thread.getContextClassLoader();
    ClassLoader defining = serviceType.getClassLoader();
    Module module = serviceType.getModule();

    System.out.println("Thread: " + thread.getName());
    System.out.println("TCCL: " + tccl);
    System.out.println("Service defining loader: " + defining);
    System.out.println("Service module: " + module.getName());
    System.out.println("Service named: " + module.isNamed());
}
~~~

Nếu provider đã được tìm thấy:

~~~java
static void inspectProvider(Object provider) {
    Class<?> type = provider.getClass();

    System.out.println("Provider type: " + type.getName());
    System.out.println("Provider loader: " + type.getClassLoader());
    System.out.println("Provider module: "
            + type.getModule().getName());
}
~~~

Có thể thấy:

- TCCL là URLClassLoader của plugin.
- Service interface dùng class loader của ứng dụng.
- Provider class dùng loader con.
- Service type hoặc provider type thuộc unnamed module nếu là classpath class.
- Một named module thuộc boot hoặc custom module layer.

Không nên lấy **Module.getName()** làm điều kiện duy nhất vì unnamed module trả về null. Nếu cần kiểm tra layer, dùng **Module.getLayer()**, nhớ rằng module không thuộc layer có thể trả về null.

## 20. Khi nào chọn TCCL, explicit loader hoặc ModuleLayer?

| Bối cảnh | Phương án ưu tiên | Lý do |
|---|---|---|
| Ứng dụng classpath đơn giản | **ServiceLoader.load(Service.class)** | TCCL mặc định thường phù hợp |
| Plugin classpath có URLClassLoader riêng | **load(Service.class, pluginLoader)** | Rõ ràng nguồn provider |
| Framework chỉ biết ServiceLoader.load(Service.class) | Đặt TCCL trong try/finally | Tương thích với API phụ thuộc TCCL |
| Named-module plugin trong child layer | **load(pluginLayer, Service.class)** | Chọn đúng layer và các parent |
| Task chạy trong thread pool | Đặt/khôi phục TCCL ngay trong task nếu cần | Tránh leak ngữ cảnh giữa task |
| Nâng cấp plugin đã được nạp | Quản lý vòng đời loader/layer | reload() không thay class đã nạp |

Đừng thay đổi TCCL như một bước “chữa mọi lỗi class loading”. Trước tiên, cần xác định plugin là classpath provider hay named module provider, ai là loader của service API, và thành phần nào thực hiện lời gọi ServiceLoader.

## 21. Những hiểu nhầm phổ biến

**“ServiceLoader luôn dùng class loader định nghĩa service interface.”**

Không đúng với overload **load(Service.class)**: nó sử dụng TCCL. Muốn chỉ định loader rõ ràng, dùng overload nhận ClassLoader. Nếu dùng named module layer, có overload nhận ModuleLayer.

**“Thay TCCL sẽ khiến Class.forName(String) dùng loader mới.”**

Không thể suy luận như vậy. Overload **Class.forName(String)** sử dụng loader của caller theo quy tắc API, không tự đồng nghĩa TCCL. Muốn chỉ định loader khi nạp class, dùng overload **Class.forName(name, initialize, loader)** hoặc API loadClass của loader phù hợp.

**“Một TCCL mới làm mọi module đọc nhau.”**

Sai. TCCL không sửa requires, exports, opens hoặc module resolution.

**“Thread pool chắc chắn kế thừa TCCL của task submitter.”**

Sai. Pool thread có thể được tạo từ trước và tái sử dụng. Đặt ngữ cảnh ngay trong task nếu cần rồi restore.

**“Đổi TCCL sau khi đã tạo ServiceLoader sẽ khiến instance tự đổi nguồn.”**

Không nên dựa vào điều đó. Khi muốn nguồn class loader khác, tạo ServiceLoader mới bằng overload phù hợp. reload() chỉ làm mới cache của instance theo cơ chế của nó.

**“Provider trên classpath chỉ cần implement interface là đủ.”**

Chưa đủ cho cơ chế SPI tự khám phá. Provider classpath cần metadata service cấu hình đúng, class có thể được loader tìm thấy và phù hợp với service contract.

**“Có module-info.java rồi thì META-INF/services là bắt buộc.”**

Với explicit named module, provider thường được khai báo bằng **provides ... with ...** trong module descriptor. Cơ chế này không đồng nghĩa với việc phải tạo cùng file META-INF/services như classpath provider.

**“Cứ tìm được provider là có thể reflection vào mọi private field.”**

Sai. JPMS tiếp tục áp dụng quyền opens, module access và quy tắc reflection riêng.

## 22. Checklist thiết kế ServiceLoader trong plugin system

1. Đặt service interface ở API chung, có class identity rõ ràng.
2. Xác định plugin là JAR classpath, automatic module hay explicit named module.
3. Với classpath provider, đóng gói đúng **META-INF/services/**.
4. Với named module, khai báo **uses** ở consumer và **provides ... with ...** ở provider.
5. Nếu sử dụng class loader riêng, đảm bảo plugin loader thấy service API qua parent/delegation phù hợp.
6. Chọn overload ServiceLoader đúng phạm vi: mặc định TCCL, explicit ClassLoader hoặc ModuleLayer.
7. Nếu thay TCCL, luôn lưu và khôi phục trong finally.
8. Với executor, thiết lập context trong task thay vì giả định thừa kế từ submitter.
9. Xử lý **ServiceConfigurationError** và ghi log loader/module của provider.
10. Không dựa vào thứ tự provider nếu chưa có chính sách lựa chọn.
11. Đừng chia sẻ ServiceLoader instance một cách không đồng bộ giữa nhiều thread.
12. Khi reload plugin, hiểu giới hạn của **reload()** và quản lý vòng đời loader/layer.
13. Kiểm tra cả trường hợp plugin hiện diện, plugin vắng và plugin có dependency không tương thích.
14. Kiểm tra source đóng gói cuối cùng, vì resource service configuration có thể bị bỏ khỏi JAR khi build/shading.

## 23. Ghi nhớ

- **TCCL** là class loader ngữ cảnh của thread, không nhất thiết là loader định nghĩa class đang chạy.
- **ServiceLoader.load(Service.class)** sử dụng TCCL theo ngữ cảnh thread.
- **ServiceLoader.load(Service.class, loader)** cho phép chọn loader tường minh.
- **ServiceLoader.load(layer, Service.class)** phục vụ tìm provider theo ModuleLayer.
- TCCL hữu ích khi thư viện ở loader cha cần khám phá provider nằm ở loader con.
- Thay TCCL không sửa module graph hoặc cấp quyền exports/opens.
- Nếu dùng **setContextClassLoader**, hãy khôi phục giá trị cũ trong **finally**.
- Executor và CompletableFuture không bảo đảm mỗi task tự nhận TCCL của thread submitter.
- Service interface cần cùng class identity giữa host và provider; tên class giống nhau chưa đủ nếu defining loader khác.
- Classpath SPI dựa trên **META-INF/services**; named module SPI dựa trên **uses** và **provides ... with ...**.
- ServiceLoader có lazy discovery/cache; **reload()** không tự thay class loader hoặc class đã nạp.
- **ServiceConfigurationError** là tín hiệu quan trọng để chẩn đoán provider metadata, class visibility và module config.

**Kết luận:** dùng Thread Context Class Loader khi cần truyền ngữ cảnh tìm class/service qua ranh giới framework và plugin; dùng ServiceLoader để khám phá implementation theo contract. Khi kết hợp với JPMS, hãy phân biệt rõ **class loader context**, **ModuleLayer**, và **module access rules**. Chọn đúng overload ServiceLoader cùng chính sách quản lý thread sẽ giúp hệ thống plugin dễ dự đoán và ít gặp lỗi class loading khó tái hiện.

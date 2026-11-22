# Service Provider Interface (SPI) và vai trò của ServiceLoader trong Java

Khi xây ứng dụng có thể mở rộng, **host không nên phải sửa mã nguồn mỗi khi xuất hiện một implementation mới**. Java hỗ trợ mô hình **Service Provider Interface (SPI)**: một interface hoặc abstract class định nghĩa hợp đồng; nhiều **service providers** triển khai hợp đồng; code sử dụng dịch vụ (consumer) khám phá những provider ấy lúc runtime.

`java.util.ServiceLoader<S>` là API chuẩn để **tìm và tạo providers** mà không cần host hard-code tên class implementation. Cơ chế này liên quan trực tiếp tới **ClassLoader**, vì việc tìm provider và nạp bytecode còn phụ thuộc nơi đặt JAR, thread context class loader (TCCL), classpath hoặc JPMS module layers.

Ba ý cốt lõi:

1. **SPI là hợp đồng**, ví dụ `GreetingService`; provider là implementation, ví dụ `FriendlyGreeting`. `ServiceLoader` là công cụ khám phá/khởi tạo, **không phải chính SPI**.
2. **ServiceLoader không quét ngẫu nhiên mọi class trên classpath**. Trong môi trường classpath, nó đọc descriptor ở `META-INF/services/<tên nhị phân SPI>`; trong **named modules**, nó dùng `uses`/`provides` của JPMS.
3. **Có class trên đĩa chưa đủ**: provider và SPI phải có runtime type identity tương thích; loader chọn để khám phá phải nhìn thấy descriptor và provider. Trong chế độ mặc định, `ServiceLoader.load(SPI.class)` dùng **TCCL của thread hiện tại**.

Bài này trình bày mô hình, nguyên lý hoạt động, classloader boundary, lifecycle, lỗi thường gặp và ví dụ Java 17+ chạy được cả khi provider **không nằm trong application classpath của host**.

## 1. Mô hình SPI: consumer, service contract và provider

~~~text
                 Host / Consumer
                       |
                 sử dụng API SPI
                       |
                       v
                 GreetingService
                    /       \
                   /         \
       FriendlyGreeting    FormalGreeting
       (provider A)        (provider B)
                   \         /
                    \       /
                     ServiceLoader
                     discovery
~~~

Trong Java, một service thường được biểu diễn bởi `interface` hoặc `abstract class`. Provider là một kiểu cung cấp implementation cho service; việc provider được tạo như thế nào phụ thuộc cơ chế classpath hay named module.

~~~java
package spi;

public interface GreetingService {
    String greet(String name);
}
~~~

Đây là **hợp đồng SPI**. Consumer có thể gọi `greet` mà không cần biết service provider đến từ plugin JAR nào.

Provider ví dụ:

~~~java
package ext;

import spi.GreetingService;

public final class FriendlyGreeting implements GreetingService {
    public FriendlyGreeting() { }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Để provider được `ServiceLoader` khám phá, **không đủ chỉ `implements GreetingService`**: phải có cấu hình đăng ký provider hợp lệ.

### So sánh với Dependency Injection (DI)

| Tiêu chí | ServiceLoader/SPI | DI container/framework |
|---|---|---|
| Cách lựa chọn implementation | Dựa trên provider registration của Java | Theo component/configuration/annotations/container rules |
| Tìm provider ở runtime | Có, theo class loader/module metadata | Tùy framework |
| Constructor injection và scopes | Không phải nhiệm vụ chính | Thường hỗ trợ mạnh |
| API nằm trong JDK | `java.util.ServiceLoader` | Không bắt buộc |
| Độ phức tạp | Nhỏ, thuận tiện cho extension points | Có thể nhiều tính năng nhưng nhiều lifecycle hơn |

Không coi `ServiceLoader` là một DI container đầy đủ: nó **không tự tiêm mọi dependency**, cấu hình transaction, vòng đời HTTP request hoặc proxy cho provider. Nếu constructor của provider cần tham số cấu hình, cân nhắc dùng một SPI **factory** có constructor không tham số, rồi cho factory tạo object theo cấu hình.

## 2. ServiceLoader khám phá provider ở classpath thế nào?

Với các provider thuộc **unnamed module/classpath**, mỗi JAR hoặc thư mục chứa provider configuration file:

~~~text
META-INF/services/spi.GreetingService
~~~

**Tên file** sau `META-INF/services/` phải là **tên nhị phân đầy đủ của service**, ở đây `spi.GreetingService`. Bên trong là **tên nhị phân đầy đủ của từng provider**, một tên trên mỗi dòng:

~~~text
ext.FriendlyGreeting
~~~

Nếu có nhiều providers:

~~~text
ext.FriendlyGreeting
ext.FormalGreeting
~~~

Quy tắc:

- File provider configuration mã hóa **UTF-8**.
- Dùng **dấu chấm trong tên class** (`ext.FriendlyGreeting`), không dùng `ext/FriendlyGreeting.class`.
- Dòng trống và khoảng trắng/tab quanh tên được bỏ qua.
- Ký tự `#` bắt đầu comment đến hết dòng.
- Nếu cùng provider name xuất hiện nhiều lần trong các tệp cấu hình, các bản khai báo trùng được bỏ qua theo quy tắc ServiceLoader.
- Provider phải có thể nạp từ class loader được dùng để khám phá, đồng thời **assignable về đúng runtime service type**.
- Với provider trong unnamed module/classpath, provider class phải `public`, có **public constructor không tham số** phù hợp; provider phải là subtype của service.

`ServiceLoader` dùng `ClassLoader.getResources("META-INF/services/spi.GreetingService")` (và cơ chế liên quan) để tìm provider-configuration files trong vùng nhìn thấy của loader; nó không tự duyệt tất cả file `.class` hay lấy tất cả subclasses bằng reflection.

### Cấu trúc JAR phù hợp

~~~text
greeting-plugin.jar
  META-INF/
    MANIFEST.MF
    services/
      spi.GreetingService
  ext/
    FriendlyGreeting.class
~~~

Tệp `META-INF/services/spi.GreetingService` phải có mặt **trong artifact được chạy**, không chỉ ở thư mục `src/resources` của project. `javac` không tự copy resource config file ấy khi biên dịch nguồn Java.

Không cần `Main-Class`: plugin được `ServiceLoader` tìm, không cần chạy `java -jar greeting-plugin.jar`.

## 3. Các API `ServiceLoader` quan trọng

~~~java
import java.util.ServiceLoader;

// Lấy loader dựa trên TCCL của thread hiện tại.
ServiceLoader<GreetingService> a =
        ServiceLoader.load(GreetingService.class);

// Chỉ định loader tường minh để tìm provider.
ServiceLoader<GreetingService> b =
        ServiceLoader.load(GreetingService.class, pluginLoader);
~~~

Đây là **mảnh API minh họa**: cần `GreetingService`, `pluginLoader` tồn tại trong scope và import tương ứng.

| API | Vai trò |
|---|---|
| `ServiceLoader.load(Service.class)` | Tạo service loader, sử dụng **thread context class loader** |
| `ServiceLoader.load(Service.class, loader)` | Tạo service loader dùng class loader được chỉ định |
| `ServiceLoader.load(layer, Service.class)` | Tìm providers trong module layer và các parent layers phù hợp |
| `iterator()` / vòng `for-each` | Khám phá và instantiate providers một cách **lazy** |
| `stream()` | Truy cập `Provider<S>`, có thể xem `type()` trước khi yêu cầu `get()` |
| `findFirst()` | Tìm và lấy provider đầu tiên dưới dạng `Optional<S>` |
| `reload()` | Xóa cached providers để tìm lại vào lần iterate tiếp theo |

**Không nhầm:** `ServiceLoader.load(...)` tạo **đối tượng service loader**, không bảo đảm tất cả providers được tìm/tạo ngay tại lời gọi đó. Trong nhiều trường hợp, lỗi cấu hình chỉ xuất hiện lúc duyệt iterator/stream.

### Lazy discovery và cache

~~~text
ServiceLoader.load(GreetingService.class)
                |
                v
       ServiceLoader<GreetingService>
                |
             iterator()
                |
        +-------+---------+
        |                 |
   providers đã cache    Tìm provider kế tiếp
        |                 |
        v                 v
    trả instance       load + instantiate
                          |
                          v
                  thêm vào cache của
                  ServiceLoader instance
~~~

- Các provider đã được nạp/khởi tạo trong **ServiceLoader instance** được cache để vòng iterate kế tiếp có thể trả lại.
- `reload()` xóa cache provider đã khám phá/khởi tạo. Nó **không làm ClassLoader unload hoặc redefine class**.
- Sau `reload()` nên tạo iterator/stream mới; iterator đang sử dụng có thể không còn hợp lệ.
- ServiceLoader **không thread-safe**. Không sử dụng chung một instance và vừa `reload`, vừa iterate từ nhiều threads mà không có synchronization phù hợp.
- Đừng lưu một ServiceLoader instance **toàn JVM** cho tất cả ứng dụng/plugins; TCCL và provider visibility có thể khác nhau, đồng thời cached providers có thể giữ loader cũ sống lâu.

### `stream()` và Provider metadata

~~~java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(GreetingService.class);

services.stream().forEach(provider -> {
    Class<? extends GreetingService> type = provider.type();
    System.out.println(type.getName());
    GreetingService service = provider.get();
    System.out.println(service.greet("Java"));
});
~~~

Đây là **mảnh minh họa**; package SPI và provider phải được cấu hình. `Provider.type()` cho kiểu mà `ServiceLoader` biết là provider; `get()` yêu cầu instance. Không tự giả định chỉ gọi `stream()` sẽ tạo mọi service object.

Với **JPMS provider factory method** (phần sau), provider class chứa factory method có thể khác kiểu service do `Provider.type()` đại diện; vì vậy đừng dựa vào metadata này để định danh class triển khai trong mọi mode mà không đọc hợp đồng JDK.

## 4. Vì sao TCCL quan trọng trong kiến trúc plugin?

Thread có một **context class loader**:

~~~java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();
~~~

`ServiceLoader.load(GreetingService.class)` tương đương về việc chọn class loader với:

~~~java
ServiceLoader.load(
    GreetingService.class,
    Thread.currentThread().getContextClassLoader()
);
~~~

TCCL giải quyết trường hợp **thư viện API/host được nạp bởi parent** nhưng muốn khám phá provider do một child plugin loader thấy được. Nếu code API chỉ dùng defining loader của chính nó, nó có thể không nhìn thấy plugin bytecode/config ở child.

~~~text
                  Application class loader
                        |
                  spi.GreetingService
                        |
                  Host application
                        |
               tạo URLClassLoader plugin
                        |
                        +--> ext.FriendlyGreeting
                        +--> META-INF/services/spi.GreetingService

Thread Context ClassLoader = plugin URLClassLoader
                        |
                        v
     ServiceLoader.load(GreetingService.class)
                        |
                 tìm provider của plugin
~~~

Một ứng dụng có thể đặt TCCL tạm thời:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    for (GreetingService provider
            : ServiceLoader.load(GreetingService.class)) {
        // Gọi provider.
    }
} finally {
    current.setContextClassLoader(previous);
}
~~~

Đây là mảnh minh họa, `pluginLoader` phải có vòng đời phù hợp. **Luôn restore TCCL trong `finally`**: thread pools tái sử dụng thread, và quên restore có thể khiến request khác dùng sai plugin loader hoặc giữ loader đã dừng sống lâu.

Nếu đã có `pluginLoader` và không cần thay TCCL của framework khác, overload `ServiceLoader.load(SPI.class, pluginLoader)` thường rõ ràng và giới hạn tác động hơn.

## 5. Ví dụ Java 17+ hoàn chỉnh: SPI nằm ở host, provider nằm ở plugin directory

Thí nghiệm tạo một API contract, một provider class, một provider-configuration file và một host consumer. Điểm quan trọng là **classpath của lệnh chạy chỉ chứa host và SPI**, còn provider được đọc qua một `URLClassLoader` mới.

### 5.1. Cấu trúc project

~~~text
project/
  src/
    api/
      spi/
        GreetingService.java
    plugin/
      ext/
        FriendlyGreeting.java
    host/
      ServiceLoaderDemo.java
  resources/
    META-INF/
      services/
        spi.GreetingService
  out/
    api/
    plugin/
    host/
~~~

Output directories được tạo khi build. Tệp service configuration trong `resources` cần được **copy** vào `out/plugin/META-INF/services/spi.GreetingService`.

### 5.2. `src/api/spi/GreetingService.java`

~~~java
package spi;

public interface GreetingService {
    String greet(String name);
}
~~~

### 5.3. `src/plugin/ext/FriendlyGreeting.java`

~~~java
package ext;

import spi.GreetingService;

public final class FriendlyGreeting implements GreetingService {
    public FriendlyGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Constructor public không tham số phục vụ `ServiceLoader` theo cơ chế classpath. Provider class cần load/instantiate thành công và phải implement **đúng runtime interface `spi.GreetingService`**.

### 5.4. `resources/META-INF/services/spi.GreetingService`

~~~text
ext.FriendlyGreeting
~~~

Đây là **file văn bản**, không phải một Java class. File name **chính xác** là `spi.GreetingService`; nội dung **chính xác** là binary class name `ext.FriendlyGreeting`.

### 5.5. `src/host/ServiceLoaderDemo.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;
import spi.GreetingService;

public final class ServiceLoaderDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ServiceLoaderDemo <plugin-directory>");
        }

        ClassLoader parent = GreetingService.class.getClassLoader();
        URL source = Path.of(args[0]).toAbsolutePath()
                .toUri().toURL();

        // Parent không thấy config/provider của plugin directory.
        boolean viaParent = ServiceLoader
                .load(GreetingService.class, parent)
                .iterator().hasNext();
        System.out.println("provider through parent: " + viaParent);

        try (URLClassLoader pluginLoader =
                new URLClassLoader("greeting-plugin",
                        new URL[] {source}, parent)) {

            Thread current = Thread.currentThread();
            ClassLoader previous = current.getContextClassLoader();

            try {
                current.setContextClassLoader(pluginLoader);

                // Convenience overload lấy TCCL vừa được thiết lập.
                ServiceLoader<GreetingService> services =
                        ServiceLoader.load(GreetingService.class);

                int count = 0;
                for (GreetingService service : services) {
                    System.out.println("provider says: "
                            + service.greet("Java"));
                    System.out.println("same service API: "
                            + (service instanceof GreetingService));
                    System.out.println("provider defined by plugin: "
                            + (service.getClass().getClassLoader()
                               == pluginLoader));
                    count++;
                }

                System.out.println("providers: " + count);
            } finally {
                current.setContextClassLoader(previous);
            }
        }
    }
}
~~~

**Vì sao ví dụ dùng parent là loader của `GreetingService`?** Vì host và provider phải tham chiếu đến **cùng một interface runtime**, tức `(spi.GreetingService, parent)`. Plugin loader tự định nghĩa `ext.FriendlyGreeting`, nhưng delegate việc nạp `spi.GreetingService` về parent.

**Vì sao phải đặt TCCL?** Host program được nạp qua app loader không có plugin directory. Khi tạm đặt TCCL bằng URLClassLoader, `ServiceLoader.load(GreetingService.class)` tìm provider-configuration file và class implementation do plugin loader nhìn thấy.

### 5.6. Biên dịch và chạy (Bash / Linux / macOS)

Chạy từ thư mục `project`:

~~~bash
mkdir -p out/api out/plugin/META-INF/services out/host

javac -d out/api src/api/spi/GreetingService.java

javac -cp out/api -d out/plugin src/plugin/ext/FriendlyGreeting.java

cp resources/META-INF/services/spi.GreetingService \
   out/plugin/META-INF/services/spi.GreetingService

javac -cp out/api -d out/host src/host/ServiceLoaderDemo.java

java -cp "out/api:out/host" ServiceLoaderDemo out/plugin
~~~

Trên Windows, có thể tạo thư mục bằng `New-Item -ItemType Directory -Force`, copy file bằng `Copy-Item` và dùng dấu `;` để phân cách classpath:

~~~powershell
java -cp "out/api;out/host" ServiceLoaderDemo out/plugin
~~~

Chú ý **không đưa `out/plugin` vào `-cp` của host**. Nó chỉ là nguồn URL của custom loader. Nếu thêm `out/plugin` vào application classpath, lời gọi `ServiceLoader.load(SPI.class, parent)` có thể tìm provider trước khi đổi TCCL, khiến phần so sánh không còn đúng.

**Stdout xác định trong cấu hình được mô tả:**

~~~text
provider through parent: false
provider says: Hello, Java
same service API: true
provider defined by plugin: true
providers: 1
~~~

### 5.7. Giải thích output

- `provider through parent: false`: parent chỉ thấy host + API, không nhìn thấy descriptor/config `META-INF/services` trong `out/plugin`.
- `provider says: Hello, Java`: ServiceLoader đã đọc descriptor, load `ext.FriendlyGreeting` và instantiate provider.
- `same service API: true`: provider implement **đúng** runtime `spi.GreetingService` mà host sử dụng.
- `provider defined by plugin: true`: class `ext.FriendlyGreeting` do URLClassLoader tự tạo định nghĩa, không bị parent tìm thấy trước.
- `providers: 1`: chỉ một provider được đăng ký và tìm thấy trong cấu hình thí nghiệm.

### 5.8. Đóng plugin thành JAR

Từ output ở trên, đóng plugin class cùng descriptor:

~~~bash
mkdir -p dist

jar --create --file dist/greeting-plugin.jar -C out/plugin .

jar --list --file dist/greeting-plugin.jar
~~~

Các entry chính phải có:

~~~text
ext/FriendlyGreeting.class
META-INF/services/spi.GreetingService
~~~

Chạy lại bằng đường dẫn JAR thay vì thư mục:

~~~bash
java -cp "out/api:out/host" ServiceLoaderDemo dist/greeting-plugin.jar
~~~

Vì code chuyển đường dẫn sang `URL` bằng `Path.toUri().toURL()`, `URLClassLoader` hỗ trợ cả URL thư mục và URL JAR. Khi có đủ hai entries, **stdout giống hệt phần 5.6**.

Lưu ý: plugin JAR không cần `Main-Class`. ServiceLoader dùng descriptor `META-INF/services` và binary names.

## 6. ServiceLoader không được phép làm mờ ranh giới type identity

Một lỗi plugin phổ biến: plugin JAR đóng gói **cả một bản sao SPI** `spi.GreetingService` rồi được nạp child-first cho cả `spi.*`. Dù provider có khai báo `implements spi.GreetingService`, JVM có thể coi nó là **interface khác** với SPI của host:

~~~text
Host:    (spi.GreetingService, AppLoader)
Plugin:  (spi.GreetingService, PluginLoader)

Cùng binary name nhưng khác defining loader
=> hai runtime interfaces khác nhau
~~~

Khi ServiceLoader thử kiểm tra provider có assignable về service type hay không, provider sai ranh giới có thể gây `ServiceConfigurationError`; một thao tác cast thủ công có thể gặp `ClassCastException`.

**Đúng cách:** cho SPI, các public callback/DTO/shared exceptions sống ở loader cha chung. Plugin loader dùng parent delegation đối với API ấy, chỉ tự định nghĩa implementation/dependency riêng.

Không đủ để hai nơi có `GreetingService.class` cùng bytecode; JVM phân biệt chúng theo **defining loader object**.

### Lỗi do TCCL sai

Một framework chạy trong thread pool có thể dùng TCCL của thread được tạo trước khi plugin loader xuất hiện. Khi đó:

~~~java
ServiceLoader.load(GreetingService.class)
~~~

có thể trả kết quả trống dù `pluginLoader.loadClass("ext.FriendlyGreeting")` thành công. Đây không phải mâu thuẫn: ServiceLoader có thể **không tìm thấy provider configuration file** từ TCCL của thread hiện tại.

Chẩn đoán:

~~~java
System.out.println(Thread.currentThread()
        .getContextClassLoader());

System.out.println(GreetingService.class.getClassLoader());
~~~

Hai giá trị này không bắt buộc bằng nhau. Thử `ServiceLoader.load(GreetingService.class, pluginLoader)` để yêu cầu loader đích tường minh và so sánh.

## 7. Cơ chế SPI trong JPMS: `uses` và `provides`

Từ Java 9, **named modules** sử dụng module descriptor thay vì phải dựa hoàn toàn vào `META-INF/services`.

Ví dụ một module định nghĩa SPI:

**`greeting.api/module-info.java`**

~~~java
module greeting.api {
    exports spi;
}
~~~

Nội dung interface `spi.GreetingService` được biên dịch và đóng gói trong module `greeting.api`.

Module consumer:

**`greeting.consumer/module-info.java`**

~~~java
module greeting.consumer {
    requires greeting.api;
    uses spi.GreetingService;
}
~~~

Code trong module `greeting.consumer` có thể gọi `ServiceLoader.load(GreetingService.class)`. Khai báo **`uses`** cho service type là cần thiết đối với named module dùng ServiceLoader; `requires` cung cấp khả năng truy cập module export SPI.

Provider module:

**`greeting.provider/module-info.java`**

~~~java
module greeting.provider {
    requires greeting.api;
    provides spi.GreetingService
        with ext.FriendlyGreeting;
}
~~~

Khi provider module được **resolved và nằm trong module layer được tìm kiếm**, ServiceLoader có thể tìm provider qua `provides`. Cần cấu hình module path/resolution phù hợp, không phải chỉ copy `module-info.class` vào một JAR rồi mặc định provider sẽ hiện diện.

Một consumer class minh họa ở `greeting.consumer`:

~~~java
package app;

import java.util.ServiceLoader;
import spi.GreetingService;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader.load(GreetingService.class)
                .forEach(service ->
                        System.out.println(service.greet("Java")));
    }
}
~~~

Đây là **các mảnh tệp minh họa riêng cho JPMS**, không chép cùng chỗ vào classpath demo mà không sắp xếp cấu trúc modular. Phải tạo module source tree, compile/resolve các module và bảo đảm provider module có trong module graph; số lượng providers còn phụ thuộc môi trường.

### Vì sao `uses` không tương đương `requires provider.module`?

- `requires greeting.api` cho phép consumer tham chiếu service interface exported bởi `greeting.api`.
- `uses spi.GreetingService` khai báo **mục đích tiêu thụ service** để JPMS/ServiceLoader thực hiện discovery theo module model.
- `provides spi.GreetingService with ext.FriendlyGreeting` ở provider module đăng ký implementation.
- Consumer **không cần** phụ thuộc trực tiếp vào implementation module để gọi service. Đó là mục tiêu loose coupling của SPI.

Tránh ép consumer viết `requires greeting.provider` chỉ để có tên provider class trong compile classpath; làm vậy phá ý tưởng thay đổi implementation độc lập.

### Provider constructor và provider factory method

Theo JDK API, provider trong **classpath/unnamed module** được instantiate qua **public constructor không tham số** phù hợp.

Trong **explicit named module**, provider có thể được tạo qua:

1. **Provider constructor** không tham số phù hợp; hoặc
2. **Public static no-arg factory method có tên `provider`**, trả một instance kiểu assignable về service.

Ví dụ provider factory method (minh họa):

~~~java
package ext;

import spi.GreetingService;

public final class GreetingFactories {
    private GreetingFactories() { }

    public static GreetingService provider() {
        return name -> "Hello from factory, " + name;
    }
}
~~~

Với explicit module có khai báo `provides spi.GreetingService with ext.GreetingFactories;`, API có thể sử dụng provider method để tạo service. **Không áp dụng cơ chế provider method này cho provider-configuration file trong unnamed module**: ở classpath, class được liệt kê phải trực tiếp là subtype của service và có constructor phù hợp.

Lợi ích của provider factory method: có thể che giấu implementation thật hoặc trả factory/service đã được cấu hình, thay vì buộc service object đồng nhất với provider class được khai báo trong module descriptor.

### Provider ở module layers

`ServiceLoader.load(ModuleLayer layer, SPI.class)` tìm providers từ layer đã chỉ định và các ancestor layers thích hợp. Cách này phù hợp plugin modules được tạo qua `ModuleLayer` riêng.

Cần lưu ý:

- Khám phá module providers liên quan **module graph/layer**, không chỉ nhìn một URL classpath.
- Một layer có thể dùng nhiều classloaders; không suy ra loader được truyền cho một overload nhất định chỉ nhìn thread context.
- Module readability/exports/opens và provider resolution phải được thiết kế đúng.
- `ServiceLoader.load(layer, service)` **không tìm provider của unnamed modules** theo hợp đồng API.

## 8. Đa provider: lựa chọn, thứ tự và xung đột

Khi có nhiều providers cùng SPI:

~~~java
ServiceLoader<GreetingService> all =
        ServiceLoader.load(GreetingService.class);

for (GreetingService g : all) {
    System.out.println(g.greet("Java"));
}
~~~

Đây là mảnh minh họa. **Thứ tự providers không nên được coi là nghiệp vụ ổn định xuyên mọi môi trường**. Với classpath descriptors, thứ tự phụ thuộc thứ tự tìm resource files của classloader và dòng cấu hình. Với named modules, có những quy tắc riêng và một số thứ tự không được bảo đảm.

Không nên dựa vào “provider xuất hiện đầu luôn là provider tốt nhất” khi có nhiều JAR. Tốt hơn:

- Thiết kế interface với metadata như `id()`, `priority()`, `supports(...)`.
- Thu thập tất cả providers rồi **chọn theo policy tường minh**.
- Xử lý provider lỗi theo hợp đồng sản phẩm; không âm thầm bỏ qua lỗi cấu hình nghiêm trọng.
- Đối với extension được deploy/redeploy, gắn provider list với plugin generation/lifecycle.

### Sự khác nhau giữa `findFirst()` và `stream().findFirst()`

`findFirst()` trả `Optional<S>` và có thể instantiate provider đầu tiên để nhận service instance.

`stream()` trả stream các `ServiceLoader.Provider<S>`, cho phép kiểm tra `type()` trước khi gọi `get()`. Đây là một khác biệt hữu ích nếu muốn chọn provider dựa trên metadata mà không phải tạo hết instances.

Tuy nhiên, `stream()` vẫn thực hiện khám phá lazy và có thể ném `ServiceConfigurationError` khi provider config/class không hợp lệ. Không xem nó như phép kiểm tra tĩnh luôn thành công.

## 9. Lỗi `ServiceConfigurationError` và cách chẩn đoán

`ServiceLoader` báo lỗi qua `java.util.ServiceConfigurationError` (một subtype của `Error`). Nó có thể xuất hiện trong `hasNext()`, `next()`, stream operations hoặc `Provider.get()` khi cần nạp/instantiate provider.

Các nguyên nhân thường gặp:

| Lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Sai tên descriptor | `META-INF/services/GreetingService` thay vì `.../spi.GreetingService` | Dùng **binary name đầy đủ của SPI** |
| Sai tên provider | `ext/FriendlyGreeting.class` | Một dòng `ext.FriendlyGreeting` |
| Provider config không ở artifact runtime | `resources/` chưa được copy | Kiểm tra bằng `jar --list` |
| Provider class không thấy được | Plugin URL/TCCL sai hoặc dependency thiếu | Kiểm tra loader được chọn, classpath, parent chain |
| Không subtype cùng runtime SPI | Plugin định nghĩa lại `spi.GreetingService` | Chia sẻ SPI từ defining loader cha |
| Constructor không phù hợp ở classpath | Không có `public` no-arg constructor | Thêm constructor hợp lệ hoặc chuyển sang module provider method khi thiết kế phù hợp |
| Class abstract/không instantiate được | Provider không có implementation cụ thể | Sửa provider implementation |
| Constructor/provider method thất bại | Runtime exception khi instantiate | Kiểm tra stack trace/cause |
| Version/linkage không tương thích | `NoClassDefFoundError`, `NoSuchMethodError` | Kiểm tra JAR thực tế, defining loader, binary compatibility |
| File cấu hình UTF-8/syntax sai | Dòng tên class không hợp lệ | Sửa cấu trúc descriptor, encoding/comment |
| Module thiếu `uses` | Consumer ở explicit named module chưa khai báo service use | Thêm `uses SPI;` |
| Module provider chưa resolved | Chỉ có JAR trên module path nhưng không thuộc graph thực thi | Điều chỉnh module resolution/module layer |

Vì `ServiceConfigurationError` là `Error`, không nên quen tay bắt rồi lờ đi như thể không có provider. Nếu hệ thống thực sự cho phép plugin tùy chọn lỗi, cần policy cách ly, log nguyên nhân và đảm bảo không che lỗi của cả ứng dụng.

### Checklist chẩn đoán theo thứ tự

**Bước 1 — Xác nhận service type:**

~~~java
System.out.println(GreetingService.class.getName());
System.out.println(GreetingService.class.getClassLoader());
~~~

**Bước 2 — Xác nhận TCCL hoặc explicit loader:**

~~~java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();
System.out.println(loader);
~~~

**Bước 3 — Xác nhận resource provider descriptor:**

~~~java
var configs = loader.getResources(
        "META-INF/services/spi.GreetingService");

while (configs.hasMoreElements()) {
    System.out.println(configs.nextElement());
}
~~~

Các đoạn này là **mảnh minh họa**, cần exception handling `IOException` và biến loader khác `null`. Nhìn được descriptor không tự bảo đảm class/provider nạp hợp lệ nhưng giúp phân biệt lỗi discovery và lỗi instantiation.

**Bước 4 — Xác nhận class provider có thể load:**

~~~java
Class<?> impl = loader.loadClass("ext.FriendlyGreeting");
System.out.println(impl.getClassLoader());
System.out.println(GreetingService.class.isAssignableFrom(impl));
~~~

Nếu `isAssignableFrom` là `false`, hãy kiểm tra **hai bản SPI khác loader**, package/module access và binary incompatibility.

**Bước 5 — Kiểm tra artifact:**

~~~bash
jar --list --file dist/greeting-plugin.jar
~~~

Tìm chính xác `META-INF/services/spi.GreetingService` và `ext/FriendlyGreeting.class`, không chỉ kiểm tra Maven dependency declaration.

**Bước 6 — Đọc cause của `ServiceConfigurationError`:** khi lỗi do provider bytecode/constructor, nguyên nhân gốc có thể nằm bên trong `getCause()` hoặc chuỗi exception khác. Đừng khắc phục bằng việc thêm mọi JAR vào global classpath nếu mục tiêu là isolation.

## 10. ServiceLoader, ClassLoader và đời sống plugin

### 10.1. ServiceLoader giữ cache trong phạm vi instance

Sau khi một provider đã được khám phá/khởi tạo, ServiceLoader có thể giữ tham chiếu đến instance và class metadata. Nếu host giữ một `ServiceLoader` lâu hơn vòng đời plugin, plugin loader cũ có thể **không được thu gom/unload**.

Ví dụ khi redeploy:

~~~text
Generation A: pluginLoader-A -> providers-A
        |
        +-- Host còn giữ ServiceLoader<A> / provider instance
        |
        +-- Loader A chưa có cơ hội unload

Generation B: pluginLoader-B -> providers-B
        |
        +-- ServiceLoader instance mới theo B
~~~

Khi dừng plugin, nên:

1. Dừng các tasks/threads của plugin, hủy callback, đóng resources.
2. Dừng sử dụng provider objects cũ.
3. Xóa references tới ServiceLoader/provider instances và TCCL trỏ tới loader cũ.
4. Đóng URLClassLoader hoặc nguồn bytecode/JAR theo lifecycle.
5. Cho JVM/GC quyết định thời điểm class unloading thực tế.

`ServiceLoader.reload()` **không thay thế** toàn bộ các bước trên; nó chỉ xóa provider cache của instance loader, không tự tải lại class definitions.

### 10.2. Thread safety

ServiceLoader không phải một container concurrent-ready mặc định. Một instance bị iterate/reload đồng thời không có bảo đảm thread-safety. Khi cần đa luồng:

- Khám phá providers trong một phase có kiểm soát.
- Tạo snapshot danh sách service instances hoặc factories theo hợp đồng thread-safety của từng provider.
- Công bố snapshot một cách an toàn (ví dụ immutable list + volatile/atomic reference).
- Chỉ chia sẻ provider instance giữa threads nếu **implementation của provider** thread-safe.
- Với plugin reload, chuyển generation snapshot atomically thay vì sửa cùng list dùng chung giữa các threads.

ServiceLoader không tự bảo đảm rằng tất cả providers có trạng thái immutable hay reentrant.

### 10.3. Trust boundary

Đọc descriptor rồi instantiate provider có nghĩa ứng dụng thực thi code do nhà cung cấp plugin phát hành. `ServiceLoader` và `ClassLoader` **không tạo sandbox bảo mật**. Nếu plugin không tin cậy, cần quy trình xác minh chữ ký/nguồn artifact, quyền tiến trình, sandbox/process isolation thích hợp và chính sách update/deployment.

Không in file cấu hình chứa bí mật chỉ để debug service discovery; log tên provider, loader, version/hash và vị trí artifact khi cần.

## 11. Những hiểu lầm phổ biến

1. **“SPI và ServiceLoader là một.”** Sai: SPI là hợp đồng; ServiceLoader là cơ chế khám phá/khởi tạo provider.
2. **“Chỉ cần implement interface thì ServiceLoader tự tìm được.”** Sai: classpath cần `META-INF/services`; named module cần `provides`.
3. **“ServiceLoader tự quét tất cả `.class`.”** Sai: nó dựa trên cấu hình provider và module metadata.
4. **“`load(SPI.class)` luôn dùng system class loader.”** Sai: nó dùng **TCCL hiện tại**.
5. **“Tạo một URLClassLoader là TCCL tự đổi.”** Sai: phải truyền explicit loader hoặc đặt/restoring TCCL có kiểm soát.
6. **“Provider và SPI cùng tên class ở hai loader sẽ cast được.”** Sai: runtime type identity có defining loader.
7. **“Provider file phải tên provider class.”** Sai: tên file là **service binary name**; nội dung file liệt kê provider binary names.
8. **“Provider file chỉ cần ở source resources folder.”** Sai: nó phải có trong artifact/runtime search path.
9. **“`ServiceLoader.load` luôn instantiate ngay mọi provider.”** Sai: lazy discovery/instantiation.
10. **“`reload()` sẽ unload class và hot-replace plugin.”** Sai: chỉ reset provider cache; classloader lifecycle là chuyện khác.
11. **“`ServiceLoader` thread-safe.”** Sai: cần tự kiểm soát khi chia sẻ instance giữa nhiều threads.
12. **“Classpath provider method `public static provider()` thay cho constructor được.”** Sai: provider factory method thuộc quy tắc explicit module; classpath provider cần constructor đúng.
13. **“Module consumer phải `requires` provider module.”** Sai: `uses`/`provides` cho phép loose coupling, chỉ cần SPI type accessible.
14. **“Provider JAR phải có `Main-Class`.”** Sai: đó là quy tắc `java -jar`, không phải service discovery.
15. **“Provider đầu tiên luôn là implementation ưu tiên.”** Sai: thứ tự không phải hợp đồng selection nghiệp vụ trong mọi môi trường.
16. **“Một ServiceLoader global dùng cho mọi thread/plugin đều an toàn.”** Sai: TCCL visibility khác nhau và cached providers có thể giữ loader cũ.
17. **“`ServiceLoader.load(layer, service)` tự tìm cả unnamed-module classpath providers.”** Sai: overload layer tìm trong named modules ở layer/ancestors theo hợp đồng.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Phân biệt SPI, provider và `ServiceLoader`?

**Đáp án:** SPI định nghĩa hợp đồng, provider triển khai dịch vụ, ServiceLoader khám phá/khởi tạo providers đã đăng ký mà không cần consumer biết trước implementation name.

**Câu 2.** Service là `com.demo.Codec`; provider là `com.demo.impl.FastCodec` chạy trên classpath. Descriptor phải tên gì và nội dung gì?

**Đáp án:** File `META-INF/services/com.demo.Codec`, chứa dòng `com.demo.impl.FastCodec`. Provider class phải load được và có constructor no-arg public phù hợp.

**Câu 3.** Vì sao ServiceLoader từ host không tìm provider nằm trong plugin URLClassLoader mặc dù `pluginLoader.loadClass` thành công?

**Đáp án:** `ServiceLoader.load(SPI.class)` dùng TCCL; TCCL có thể là host loader không thấy descriptor/provider. Hãy truyền explicit pluginLoader hoặc tạm đặt TCCL rồi restore.

**Câu 4.** Plugin tự định nghĩa một bản `spi.GreetingService` riêng; host có interface cùng tên. Hậu quả?

**Đáp án:** Hai runtime interfaces khác defining loader; provider có thể không assignable về SPI của host, dẫn tới `ServiceConfigurationError` hoặc lỗi cast.

**Câu 5.** `reload()` có nạp lại bytecode provider mới trong cùng ClassLoader không?

**Đáp án:** Không. Nó chỉ reset cache provider của ServiceLoader; class definitions đã được JVM nạp vẫn tồn tại theo lifecycle riêng.

**Câu 6.** Trong named module, khai báo gì để consumer tìm provider không cần import class triển khai?

**Đáp án:** Consumer khai báo `uses spi.GreetingService;`, provider module khai báo `provides spi.GreetingService with ext.FriendlyGreeting;`, đồng thời module graph/readability cho service type được cấu hình đúng.

**Câu 7.** Có nên chia sẻ cùng ServiceLoader và provider instances giữa nhiều threads không?

**Đáp án:** ServiceLoader bản thân không thread-safe; hãy snapshot providers hoặc bảo vệ truy cập. Provider instance chỉ được chia sẻ nếu provider implementation đáp ứng thread-safety cần thiết.

## 13. Quy trình áp dụng trong một hệ thống plugin

~~~text
Định nghĩa SPI chung (host/shared API)
                 |
                 v
Build provider implementation
                 |
     +-----------+------------+
     |                        |
Classpath/unnamed         Named modules
     |                        |
META-INF/services/...    provides SPI with Impl
     |                        |
     +-----------+------------+
                 |
                 v
Chọn classloader/TCCL/module layer
                 |
                 v
ServiceLoader.load(...)
                 |
                 v
Iterator/stream: lazy discovery
                 |
                 v
Kiểm tra provider contract + lifecycle
                 |
                 v
Chọn provider theo policy ứng dụng
                 |
                 v
Sử dụng -> shutdown/reload có kiểm soát
~~~

**Ghi nhớ:** `ServiceLoader` là **cầu nối giữa service contract và nhiều provider runtime**, không phải công cụ tự thay đổi classloader. Provider discovery phải phù hợp **cấu hình `META-INF/services` hoặc JPMS `uses`/`provides`**, **loader visibility/TCCL** và **cùng runtime SPI type**. Nếu ba điều đó đúng, có thể thêm implementation mà không sửa consumer; nếu sai, lỗi thường nằm ở descriptor, module graph hoặc ranh giới defining loader.

### Tài liệu tham khảo chính thức

- [Java SE 17 — ServiceLoader API: service providers, classpath/JPMS, lazy loading](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 17 — ClassLoader API: getResources, delegation, defining loader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [JLS 17 §7.7 — Module declarations, uses and provides](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)

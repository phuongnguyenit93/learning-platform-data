# ServiceLoader và các API dùng thread context class loader (TCCL)

Trong Java, **`ServiceLoader`** là cơ chế *service provider interface* (SPI): ứng dụng định nghĩa một **service contract** (thường là interface hoặc abstract class), còn các thư viện/plugin đóng góp những **provider implementations** có thể được phát hiện lúc chạy. Điểm đặc biệt trong chủ đề class loader là overload:

```java
ServiceLoader<MyService> services = ServiceLoader.load(MyService.class);
```

Theo Java SE 17 API, `ServiceLoader.load(service)` sử dụng **thread context class loader** (TCCL) của thread hiện tại để tìm providers. Nhờ đó code thuộc một thư viện hoặc framework được nạp bởi loader cha vẫn có thể khám phá provider nằm trong loader con của ứng dụng/plugin — khi thread được gán đúng context loader.

**Không nên hiểu rằng tất cả API Java tự động dùng TCCL.** `ServiceLoader.load(service)` là trường hợp có hợp đồng rõ ràng; các API khác có chiến lược loader riêng và phải đọc đúng đặc tả của từng API.

## 1. Tại sao cần loader ngữ cảnh?

Hãy tưởng tượng hệ thống plugin:

```text
ApplicationClassLoader
    ├── spi.Greeting               (interface dùng chung)
    ├── app.Application            (code framework)
    └── java.util.ServiceLoader    (API từ JDK)
               ^
               | parent delegation
               |
PluginClassLoader
    ├── plugins.HelloGreeting      (implementation)
    └── META-INF/services/
        └── spi.Greeting           (provider declaration)
```

Mặc định, parent loader **không tự đi xuống toàn bộ child loaders** để tìm `plugins.HelloGreeting`. Nếu một thư viện chỉ dùng loader định nghĩa chính nó, thư viện có thể không nhìn thấy class của plugin.

TCCL mở ra một lựa chọn khác: framework hỏi thread “trong ngữ cảnh xử lý lần này, nên dùng loader nào để khám phá provider?” Khi ứng dụng thiết lập context loader thành `PluginClassLoader`, `ServiceLoader.load(Greeting.class)` có thể tìm provider qua child loader mà không đòi parent biết trước từng plugin.

Những khái niệm cần tách:

- **Defining loader:** loader thực sự định nghĩa một class. Danh tính runtime class dựa trên cặp `(binary name, defining loader)`.
- **Initiating loader:** loader tham gia yêu cầu nạp class, có thể ủy quyền cho parent và nhận class do parent định nghĩa.
- **Thread context class loader:** một tham chiếu `ClassLoader` gắn với `Thread`; thư viện có thể chủ động sử dụng nó để tra cứu providers/resources/classes.
- **Parent delegation:** chính sách mặc định của `ClassLoader.loadClass` ưu tiên parent trước khi gọi `findClass` ở child.

**TCCL không thay đổi defining loader của các class đã được nạp**, cũng không “bẻ ngược” parent delegation cho mọi lời gọi JVM. Nó chỉ quyết định loader nào được truyền/được API dùng ở những chỗ có chủ đích.

## 2. Lấy và đặt TCCL

API của `java.lang.Thread`:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi code/framework có contract dùng TCCL.
} finally {
    thread.setContextClassLoader(previous);
}
```

Đây là **đoạn mã minh họa**, yêu cầu `pluginLoader` đã được cung cấp. Một số quy tắc:

1. `Thread.currentThread().getContextClassLoader()` trả context loader hiện hành, **có thể là `null`**.
2. `setContextClassLoader(...)` điều chỉnh context loader của thread; cách code khác phản ứng với thay đổi tùy API có đọc TCCL hay không.
3. Luôn khôi phục `previous` trong `finally` nếu thay đổi tạm, nhất là trên **thread pool**: thread được tái sử dụng cho request/plugin khác.
4. Thread mới thường **kế thừa TCCL của thread tạo ra nó** theo quy tắc API; đừng coi đó là cấu hình độc lập bất biến. Với executor, thread factory, framework hoặc môi trường tùy biến, hãy xác minh loader thực tế.
5. Đừng giữ strong references đến plugin loader trong TCCL của thread tồn tại lâu khi muốn unload/reload plugin; điều này có thể khiến loader và các lớp của nó không được thu gom.

Lưu ý: `null` trong một số API nạp lớp mang nghĩa bootstrap loader; trong API khác có thể có fallback khác. Không thay thế `null` bằng “system loader” nếu không có tài liệu API cho phép suy luận đó.

## 3. ServiceLoader là gì?

`java.util.ServiceLoader<S>` là một công cụ **phát hiện và tải provider** cho loại service `S`.

Ví dụ:

```java
package spi;

public interface Greeting {
    String message();
}
```

Một triển khai:

```java
package plugins;

import spi.Greeting;

public final class HelloGreeting implements Greeting {
    public String message() {
        return "hello-from-plugin";
    }
}
```

Để `ServiceLoader` phát hiện provider khi dùng **classpath/unnamed module**, JAR hoặc thư mục classpath của plugin chứa tệp cấu hình:

```text
META-INF/services/spi.Greeting
```

Nội dung tệp:

```text
plugins.HelloGreeting
```

Tên tệp là **binary name của service type** (`spi.Greeting`), không phải tên provider và không có hậu tố `.class`. Mỗi dòng có tên nhị phân của một provider implementation, có thể có chú thích với `#`. Theo đặc tả, provider-configuration files có mã hóa **UTF-8**; các bản ghi trùng provider name được bỏ qua theo quy tắc của `ServiceLoader`.

Trong classpath SPI thông thường, provider phải là một class cụ thể, có thể gán cho service type, và có **public constructor không tham số**. `ServiceLoader` khởi tạo nó khi quá trình duyệt yêu cầu provider instance. Đối với named modules, hợp đồng có thêm lựa chọn **provider factory method**, được trình bày riêng bên dưới.

### Ba thành phần của SPI

| Thành phần | Vị trí thường gặp | Vai trò |
|---|---|---|
| **Service API** | Dependency chia sẻ ở parent/application loader | Hợp đồng mà cả application và plugin dùng chung |
| **Provider implementation** | Plugin JAR hoặc module | Class thực hiện service |
| **Provider registration** | `META-INF/services/<binary-name>` hoặc `provides ... with ...` trong `module-info.java` | Cho runtime biết provider nào được quảng bá |

**Đặt API contract ở loader chung** là yêu cầu quan trọng khi giao tiếp qua ranh giới plugin. Nếu ứng dụng và plugin tự định nghĩa hai bản `spi.Greeting` khác nhau, cùng binary name chưa đủ: chúng là hai runtime types khác nhau và việc kiểm tra khả năng gán/ép kiểu có thể thất bại.

## 4. Các overload ServiceLoader và lựa chọn loader

Những API cần phân biệt:

| API | Cách chọn namespace/provider source | Thường dùng khi |
|---|---|---|
| `ServiceLoader.load(MyService.class)` | **TCCL của thread hiện tại** | Framework/SPI muốn tìm provider theo ngữ cảnh ứng dụng |
| `ServiceLoader.load(MyService.class, loader)` | **ClassLoader tường minh** | Ứng dụng/plugin manager biết loader cần dùng |
| `ServiceLoader.loadInstalled(MyService.class)` | **Platform class loader** (Java 17) | Tìm provider trong phạm vi platform-installed; không thay thế plugin lookup |
| `ServiceLoader.load(layer, MyService.class)` | **ModuleLayer** được chỉ định theo quy tắc module | Provider trong các named modules và layer liên quan |

Tên `loadInstalled` được giữ để tương thích với lịch sử Java; trong Java 9+ nó dùng **platform class loader**, không có nghĩa “tìm mọi JAR mà app vừa cài vào bất kỳ thư mục nào”.

Một chú ý quan trọng: `ServiceLoader.load(service, loader)` không có nghĩa “chỉ định nghĩa provider bằng loader này”. Loader có thể **ủy quyền parent**, và service type bản thân nó có thể đã được parent định nghĩa. Điều quan trọng là provider được tìm thấy trong namespace/dải nguồn có thể truy cập từ loader đang dùng.

### Không nhầm với Class.forName(String)

```java
Class<?> type = Class.forName("plugins.HelloGreeting");
```

Overload **một tham số** của `Class.forName` dùng **defining loader của class đang gọi**, và yêu cầu initialization. Nó **không mặc định dùng TCCL**. Vì thế hai câu lệnh nằm trong cùng method có thể nhìn thấy tập class khác nhau:

```java
ServiceLoader.load(Greeting.class);                  // TCCL
Class.forName("plugins.HelloGreeting");              // caller defining loader
Class.forName("plugins.HelloGreeting", false, loader); // explicit loader
```

Đây là các dòng **minh họa**, cần có `Greeting`, `loader` và provider tương ứng. Nếu framework đang chạy trong parent loader nhưng provider nằm ở plugin child loader, lời gọi `ServiceLoader.load(...)` theo TCCL có thể thành công trong khi `Class.forName(name)` từ mã parent thất bại.

## 5. Ví dụ Java 17+ chạy được: khám phá provider theo TCCL

Bài thử cố ý tách service API/app và plugin provider vào **hai thư mục classpath khác nhau**. Ứng dụng chạy với chỉ `out/app` trên classpath. Provider nằm trong `out/plugin`, được một `URLClassLoader` con đưa vào namespace tại runtime.

Cấu trúc:

```text
spi-demo/
├── src/
│   ├── spi/
│   │   └── Greeting.java
│   ├── plugins/
│   │   └── HelloGreeting.java
│   └── app/
│       └── SpiDemo.java
└── out/
    ├── app/
    └── plugin/
        └── META-INF/
            └── services/
                └── spi.Greeting
```

### 5.1. Interface ở lớp API chia sẻ

Tạo tệp **`src/spi/Greeting.java`**:

```java
package spi;

public interface Greeting {
    String message();
}
```

### 5.2. Provider ở plugin

Tạo tệp **`src/plugins/HelloGreeting.java`**:

```java
package plugins;

import spi.Greeting;

public final class HelloGreeting implements Greeting {
    public String message() {
        return "hello-from-plugin";
    }
}
```

Lớp `HelloGreeting` là `public`. Khi không khai báo constructor, Java tự cung cấp default no-argument constructor với quyền truy cập tương ứng lớp `public`, phù hợp với classpath SPI.

### 5.3. Ứng dụng dùng ServiceLoader

Tạo tệp **`src/app/SpiDemo.java`**:

```java
package app;

import spi.Greeting;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.ServiceLoader;

public final class SpiDemo {
    static String discover() {
        var names = new ArrayList<String>();
        for (Greeting service : ServiceLoader.load(Greeting.class)) {
            names.add(service.message());
        }
        return names.isEmpty() ? "(none)" : String.join(",", names);
    }

    static String discover(ClassLoader loader) {
        var names = new ArrayList<String>();
        for (Greeting service :
                ServiceLoader.load(Greeting.class, loader)) {
            names.add(service.message());
        }
        return names.isEmpty() ? "(none)" : String.join(",", names);
    }

    public static void main(String[] args) throws Exception {
        ClassLoader appLoader = SpiDemo.class.getClassLoader();
        Thread current = Thread.currentThread();
        ClassLoader previous = current.getContextClassLoader();

        try {
            current.setContextClassLoader(appLoader);
            System.out.println("App TCCL: " + discover());

            try (URLClassLoader plugin = new URLClassLoader(
                    new java.net.URL[] {
                        Path.of(args[0]).toUri().toURL()
                    },
                    appLoader)) {
                current.setContextClassLoader(plugin);

                System.out.println("Plugin TCCL: " + discover());
                System.out.println("Explicit app: "
                        + discover(appLoader));
                System.out.println("Explicit plugin: "
                        + discover(plugin));
                System.out.println("Same service API: "
                        + (Greeting.class
                                == plugin.loadClass("spi.Greeting")));

                current.setContextClassLoader(appLoader);
                System.out.println("Restored app TCCL: " + discover());
            }
        } finally {
            current.setContextClassLoader(previous);
        }
    }
}
```

Đây là **chương trình hoàn chỉnh có `main`**, giả định `args[0]` là thư mục chứa plugin classes/descriptor. Lệnh chạy bên dưới cung cấp chính xác đối số đó.

### 5.4. Tạo provider configuration

Bên trong `out/plugin`, tạo chính xác:

```text
META-INF/services/spi.Greeting
```

với nội dung một dòng:

```text
plugins.HelloGreeting
```

Đây là **tệp UTF-8 text**, không phải Java source và không mang hậu tố `.java`.

### 5.5. Biên dịch/chạy trên Linux/macOS/Git Bash

Từ thư mục `spi-demo`:

```bash
mkdir -p out/app out/plugin/META-INF/services

javac --release 17 -d out/app \
  src/spi/Greeting.java src/app/SpiDemo.java

javac --release 17 -cp out/app -d out/plugin \
  src/plugins/HelloGreeting.java

printf 'plugins.HelloGreeting\n' \
  > out/plugin/META-INF/services/spi.Greeting

java -cp out/app app.SpiDemo out/plugin
```

Lưu ý dấu `\` ở cuối các dòng lệnh `javac` là cách Bash tiếp tục lệnh sang dòng sau. Trên Windows PowerShell có thể viết mỗi lệnh `javac` trên một dòng thay vì dùng `\`.

Tạo thư mục và descriptor tương đương trong Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path out/app, out/plugin/META-INF/services | Out-Null
javac --release 17 -d out/app src/spi/Greeting.java src/app/SpiDemo.java
javac --release 17 -cp out/app -d out/plugin src/plugins/HelloGreeting.java
[System.IO.File]::WriteAllText(
    "out/plugin/META-INF/services/spi.Greeting",
    "plugins.HelloGreeting" + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)
java -cp out/app app.SpiDemo out/plugin
```

Đầu ra được kiểm chứng khi biên dịch với `javac --release 17` và chạy trên JDK 21 (đúng APIs của Java 17):

```text
App TCCL: (none)
Plugin TCCL: hello-from-plugin
Explicit app: (none)
Explicit plugin: hello-from-plugin
Same service API: true
Restored app TCCL: (none)
```

### 5.6. Giải thích đầu ra từng dòng

1. **App TCCL: (none):** chỉ có `out/app` trong classpath chính, nên loader của app không thấy descriptor `META-INF/services/spi.Greeting` nằm riêng tại `out/plugin`.
2. **Plugin TCCL:** ứng dụng tạo `URLClassLoader` có URL tới `out/plugin`. Sau khi gán loader này làm TCCL, `ServiceLoader.load(Greeting.class)` khám phá provider.
3. **Explicit app:** dù thread đang có plugin TCCL, overload hai tham số được truyền `appLoader` vẫn chỉ tìm theo app loader, nên không thấy provider plugin.
4. **Explicit plugin:** khi truyền `plugin` tường minh, provider được phát hiện mà không cần dựa vào TCCL.
5. **Same service API: true:** plugin loader ủy quyền class `spi.Greeting` cho parent; provider và app đều dùng một runtime interface. Đây là điều kiện giúp vòng lặp `for (Greeting service : ...)` nhận implementation thành công.
6. **Restored app TCCL:** thay TCCL về app loader khiến lần khám phá mới không nhìn thấy provider plugin. `finally` ngoài cùng còn khôi phục TCCL ban đầu khi method kết thúc.

Chương trình không chỉnh sửa `java.class.path` để “thêm JAR động”; nó sử dụng **một loader có URL tới thư mục plugin**. Trong thực tế, URL đó thường chỉ đến **plugin JAR** thay vì thư mục. `URLClassLoader` là `AutoCloseable`, nên sử dụng `try-with-resources` để giải phóng các tài nguyên có thể đóng của loader; tuy nhiên đóng loader không tự unload mọi class ngay lập tức nếu còn tham chiếu sống.

## 6. ServiceLoader duyệt providers theo cách nào?

`ServiceLoader` hỗ trợ truy cập provider **lười (lazy)**: tạo một đối tượng `ServiceLoader` không đồng nghĩa khởi tạo ngay mọi provider instance.

Ví dụ:

```java
ServiceLoader<Greeting> loader =
        ServiceLoader.load(Greeting.class);

for (Greeting service : loader) {
    System.out.println(service.message());
}
```

- Đối tượng `loader` đại diện cho cơ chế khám phá/caching providers.
- Khi `iterator()` được duyệt, `ServiceLoader` có thể tải provider class và tạo provider instance khi cần.
- Các provider instances đã nạp được `ServiceLoader` giữ trong **cache của chính đối tượng ServiceLoader** theo hợp đồng API. Vì vậy việc duyệt lại cùng loader có thể trả lại instance đã cached thay vì tạo bản mới.
- Gọi `loader.reload()` xóa cache để việc khám phá và khởi tạo provider được thực hiện lại theo điều kiện hiện tại của nguồn/provider; **không tự thay defining class loader của các class đã nạp**.
- `ServiceLoader` **không an toàn để dùng đồng thời giữa nhiều thread** khi truy cập/mutate như cùng một object mà không có đồng bộ bên ngoài.

Một dạng sử dụng khác trên Java 17:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class);

services.stream().forEach(provider -> {
    Class<? extends Greeting> type = provider.type();
    System.out.println(type.getName());

    Greeting instance = provider.get();
    System.out.println(instance.message());
});
```

`ServiceLoader.Provider<S>` cung cấp `type()` để xem type của provider và `get()` để lấy instance. Chú ý với named modules sử dụng **provider factory method**, `type()` có thể phản ánh return type của factory theo hợp đồng API; đừng suy diễn lúc nào cũng là tên class khai báo trong cấu hình giống classpath.

### reload() không thay thế việc quản lý plugin lifecycle

Nếu một plugin JAR thay đổi trên disk nhưng vẫn dùng **cùng loader** và cùng `ServiceLoader`, chỉ gọi `reload()` không bảo đảm JVM sẽ tự định nghĩa lại các class đã được nạp, cũng không tự đóng provider instances cũ. Hệ thống hot reload cần một quy trình rõ ràng: ngừng sử dụng instance cũ, giải phóng tài nguyên/thread, tạo defining loader mới khi thích hợp, tái khám phá providers và tránh trộn kiểu giữa các thế hệ loader.

## 7. Khi có nhiều providers

Một service interface có thể có nhiều implementations. Ví dụ provider descriptor:

```text
plugins.EnglishGreeting
plugins.VietnameseGreeting
plugins.FrenchGreeting
```

Mỗi dòng phải tham chiếu đúng một provider class có thể được loader tìm thấy và gán cho service interface. Đoạn trên chỉ là **mẫu metadata**; các lớp minh họa chưa được định nghĩa trong chương trình chạy phần 5.

Việc iterator duyệt providers theo thứ tự chịu những quy tắc cụ thể của `ServiceLoader` và class loader/module source. Với nhiều JAR/modules, **không nên thiết kế nghiệp vụ phụ thuộc tuyệt đối vào thứ tự provider đầu tiên** nếu không có contract đảm bảo. Nếu có nhiều implementation, hãy dùng một thuộc tính cấu hình, priority được thiết kế riêng, hoặc bước lọc/định danh provider thay vì tự coi “provider đầu tiên” là phiên bản mong muốn.

Cũng không nên cho rằng service discovery sẽ lọc providers theo tình trạng runtime: một provider có thể được tìm thấy nhưng **constructor** hoặc **provider() factory** báo lỗi khi thực sự được khởi tạo.

## 8. Cơ chế đăng ký provider trong named modules (JPMS)

Java 9+ hỗ trợ SPI trong **named modules** mà không nhất thiết phải dùng `META-INF/services` cho providers nằm trong module.

Ví dụ module chứa API:

```java
module demo.api {
    exports spi;
}
```

Module của consumer:

```java
module demo.app {
    requires demo.api;
    uses spi.Greeting;
}
```

Module của provider:

```java
module demo.provider {
    requires demo.api;
    provides spi.Greeting with plugins.HelloGreeting;
}
```

Ba đoạn là các tệp **`module-info.java` minh họa riêng biệt**; để chạy thực tế cần xây dựng source tree module, class definitions và module path phù hợp. Không ghép cả ba `module` declarations vào một file.

Ý nghĩa:

- `uses spi.Greeting;` cho biết module consumer dùng service contract đó.
- `provides spi.Greeting with plugins.HelloGreeting;` đăng ký provider cho service.
- `requires demo.api;` giúp consumer/provider đọc API module.
- `exports spi;` cho phép module khác dùng kiểu public `spi.Greeting`.

Với provider module, `ServiceLoader` có thể phát hiện providers thông qua module metadata; không nhất thiết cần `META-INF/services/...` nếu provider đã đăng ký trong module descriptor. Named-module provider có thể có **public no-args constructor** hoặc **public static provider() method** với các ràng buộc cụ thể được `ServiceLoader` kiểm tra. Phương thức factory `provider()` là cơ chế của named-module provider, **không phải** cách thay thế tự do cho constructor khi provider chỉ được khai báo bằng classpath configuration file.

Nếu cần khám phá providers trong một tập module được tổ chức theo **ModuleLayer**, cân nhắc:

```java
ServiceLoader<Greeting> providers =
        ServiceLoader.load(layer, Greeting.class);
```

Đây là snippet minh họa cần biến `layer` kiểu `ModuleLayer` đã được dựng; không phải chương trình chạy độc lập. Dùng module layer có ích khi framework tạo nhiều module layers riêng thay vì chỉ dựa vào loader ngữ cảnh của thread.

### Không nhầm module với loader

Module và class loader là hai khái niệm khác nhau. Một loader có thể định nghĩa classes của nhiều modules theo mapping JVM/JDK; class có thể thuộc named module hoặc unnamed module. Điều kiện module readability, exports và service binding là tầng bổ sung, không thể được giải quyết chỉ bằng cách gán TCCL.

## 9. Những API khác có thể liên quan tới loader ngữ cảnh

`ServiceLoader` là API Java SE tiêu biểu để nhìn thấy TCCL rõ ràng. Những hệ sinh thái khác cũng có **provider discovery** nhưng không được đánh đồng tất cả:

| API/hệ sinh thái | Quan hệ với loader ngữ cảnh | Điều cần kiểm tra |
|---|---|---|
| `ServiceLoader.load(service)` | Dùng **TCCL** theo contract | TCCL có thấy provider declaration/class không? |
| `ServiceLoader.load(service, loader)` | Dùng **loader tường minh** | Đã truyền đúng plugin loader chưa? |
| `Class.forName(name)` | Dùng **caller defining loader**, không tự dùng TCCL | Code gọi đang được loader nào định nghĩa? |
| `ClassLoader.getSystemClassLoader()` | Trả system loader, không phải TCCL | System loader có thấy plugin không? |
| `javax.xml.parsers.DocumentBuilderFactory.newInstance()` (JAXP) | Quy trình tìm provider có thể dùng context class loader theo tài liệu JAXP, cùng các nguồn cấu hình/fallback khác | Provider factory, system property, service declarations, module context |
| `javax.xml.transform.TransformerFactory.newInstance()` (JAXP) | Cơ chế provider lookup và TCCL có thể liên quan | Provider discovery và version của JDK |
| `java.sql.DriverManager` / JDBC driver SPI | Driver discovery dùng service-provider mechanism cùng các quy tắc đăng ký/truy cập riêng | Loader của driver, module, driver visibility, lifecycle |
| JNDI và thư viện container/plugin | Có thể sử dụng TCCL tùy API/provider/framework | Contract và cấu hình provider cụ thể |

**Không biến bảng thành khẳng định rằng mọi API luôn đọc TCCL trong mọi phiên bản.** Chẳng hạn `ResourceBundle` có overload gắn với caller/module hoặc loader được cung cấp tường minh; chỉ nhìn tên “resource loading” không đủ để kết luận mặc định lấy TCCL. `java.util.logging`, JDBC và các framework còn có quy tắc cache, singleton, module và classloader checks riêng. Hãy đọc JavaDoc chính xác của overload đang dùng.

### Ví dụ về JAXP

`DocumentBuilderFactory.newInstance()` và `TransformerFactory.newInstance()` là những factory APIs có cơ chế tìm implementation thay thế dựa trên cấu hình/provider discovery. Chúng không tương đương trực tiếp với gọi `ServiceLoader.load` bằng tay: quy trình có thể kiểm tra system properties, cấu hình JDK, service providers và default implementation. TCCL có thể quyết định provider nào được thấy trong một số nhánh tra cứu.

Ví dụ minh họa:

```java
import javax.xml.parsers.DocumentBuilderFactory;

DocumentBuilderFactory factory =
        DocumentBuilderFactory.newInstance();
System.out.println(factory.getClass().getName());
```

Đây là đoạn **minh họa bên trong method**, không phải ứng dụng độc lập. Tên implementation in ra **không nên hardcode** vì thay đổi theo JDK, provider configuration và class loader. Nếu cần chọn provider cụ thể, tham khảo overload factory nhận class name/loader hoặc cơ chế configuration được API đó công bố.

## 10. Những lỗi thường gặp khi dùng TCCL và ServiceLoader

### 10.1. Descriptor không nằm đúng vị trí

Sai:

```text
META-INF/service/spi.Greeting
META-INF/services/spi/Greeting
META-INF/services/plugins.HelloGreeting
```

Đúng:

```text
META-INF/services/spi.Greeting
```

Tên entry là service **binary name**, và nội dung là provider implementation **binary name**. Với archive, cần đảm bảo descriptor thực sự nằm trong JAR có thể đọc từ loader được chọn, không chỉ tồn tại ở source directory.

### 10.2. Provider code tồn tại nhưng ServiceLoader không thấy

Có thể do:

- Descriptor không được copy vào build output/JAR.
- TCCL trỏ tới **parent/application loader** trong khi plugin provider chỉ thuộc child loader.
- Đã gọi overload nhận loader tường minh nhưng truyền **loader sai**.
- Named module khai báo `provides`/`uses` hoặc module layer không phù hợp.
- Provider class nằm trong nguồn mà loader không thể thấy, hoặc dependency của provider không giải quyết được.
- Một container/framework override parent-first/child-first theo namespace, khiến API contract và implementation không dùng chung runtime type.

**Chẩn đoán tối thiểu:**

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

System.out.println("TCCL = " + context);
System.out.println("API defining loader = "
        + Greeting.class.getClassLoader());
```

Đây là snippet cần interface `Greeting` trong project. Đừng so sánh loader bằng chuỗi `toString()`: mỗi custom loader có thể ghi log khác nhau. Nếu cần so sánh runtime type, dùng `==` trên `Class<?>` hoặc `ClassLoader` references.

### 10.3. ServiceConfigurationError

`ServiceLoader` có thể ném **`java.util.ServiceConfigurationError`** khi thông tin cấu hình/provider không hợp lệ, ví dụ provider class không thể tìm thấy, không tương thích service type, thiếu constructor/provider factory phù hợp, lỗi khi khởi tạo provider, hoặc không instantiate được theo hợp đồng.

Ví dụ nếu descriptor viết:

```text
plugins.DoesNotExist
```

`ServiceLoader` có thể phát hiện lỗi **khi thực sự iterate/stream providers**, không nhất thiết ngay tại `ServiceLoader.load(...)`. `ServiceConfigurationError` là `Error` (không phải checked exception), nên đừng dựa vào `catch (Exception ex)` để che mọi vấn đề provider discovery. Trong startup hoặc plugin manager, hãy ghi lại service/provider/loader và cause; có thể fail fast hoặc cô lập plugin lỗi tùy policy đã thiết kế.

### 10.4. TCCL chưa khôi phục

Một tác vụ dùng thread pool đặt TCCL sang `PluginLoaderA` rồi quên khôi phục. Tác vụ sau dành cho plugin B chạy trên cùng thread có thể tìm provider của A hoặc giữ tham chiếu lâu dài đến A. Hãy dùng `try/finally` như ví dụ ở phần 2 và đặt loader theo scope nhỏ nhất.

### 10.5. Tự thêm implementation nhưng vẫn dùng cache cũ

`ServiceLoader` cache providers đã khám phá. Việc thêm một JAR hoặc đổi TCCL sau khi tạo một `ServiceLoader` **không nên xem là cập nhật tự động toàn bộ providers trong object cũ**. Tạo `ServiceLoader` mới với đúng loader hoặc gọi `reload()` theo nhu cầu và hiểu rằng các class đã nạp có identity/lifecycle riêng.

### 10.6. Duplicate service API theo child-first

Nếu plugin tự đóng gói và child-first tải bản riêng của `spi.Greeting`, implementation có thể không được coi là subtype của `spi.Greeting` ở application loader. Kết quả có thể là `ServiceConfigurationError`, `ClassCastException` hoặc `LinkageError` tùy đường nạp/gọi. Bố trí service API trong parent/shared loader và bảo đảm plugin delegate namespace API.

## 11. Checklist thiết kế SPI/plugin đúng loader

1. **Xác định service contract** là lớp/interface nào, được defining loader nào định nghĩa.
2. **Đặt shared API ở parent/shared class loader** nếu caller và provider cần trao đổi object theo cùng Java type.
3. **Chọn nguồn đăng ký**: classpath descriptor `META-INF/services/<service-binary-name>` hoặc named module `provides ... with ...`.
4. **Xác nhận package/class entry đúng** trong JAR output, không chỉ ở source.
5. **Chọn loader cho discovery có chủ đích**: TCCL (`ServiceLoader.load(service)`), explicit loader, hoặc `ModuleLayer`.
6. **Không bỏ quên các dependencies** của provider trong namespace phù hợp.
7. **Thiết lập và phục hồi TCCL** quanh lời gọi framework nếu cần; để ý thread pools và asynchronous tasks.
8. **Duyệt provider và xử lý lỗi cấu hình rõ ràng**, thay vì giả định constructor không bao giờ lỗi.
9. **Quản lý cache, lifecycle và unload** của provider instances/class loaders; `reload()` không tự đóng resource.
10. **Tránh phụ thuộc thứ tự providers** nếu contract không yêu cầu; dùng config/metadata để chọn implementation mong muốn.

### Một lưu ý về bảo mật

TCCL và `ServiceLoader` là cơ chế **mở rộng ứng dụng**, không phải cơ chế bảo mật. Mã provider thực thi trong tiến trình với khả năng của code đã triển khai; đừng tự động tải provider không tin cậy chỉ vì có entry `META-INF/services`. Kiểm soát nguồn JAR, chữ ký/quy trình deploy, module/access policy và các quyền bên ngoài JVM theo nhu cầu hệ thống.

## 12. Câu hỏi tự kiểm tra

**1. `ServiceLoader.load(MyService.class)` dùng loader nào theo mặc định?** TCCL của thread gọi.

**2. `Class.forName("my.Provider")` có tự dùng TCCL không?** Không. Overload một tham số dùng defining loader của **calling class**; muốn loader cụ thể thì dùng overload ba tham số.

**3. Vì sao framework parent không thấy provider ở child khi không dùng context loader?** Parent delegation là từ child lên parent, không phải tìm ngược từ parent xuống tất cả children.

**4. Descriptor classpath cho `spi.Greeting` có tên gì?** `META-INF/services/spi.Greeting`. Nội dung là tên nhị phân của provider class.

**5. `ServiceLoader.load(...)` có chắc khởi tạo mọi provider ngay lập tức không?** Không. Cơ chế discovery/instantiation có tính lazy khi duyệt provider.

**6. `ServiceLoader.reload()` có bắt JVM định nghĩa lại một class đã load không?** Không. Nó xóa cache trong đối tượng ServiceLoader; class loading/loader lifecycle vẫn riêng.

**7. TCCL đã đổi mà `ServiceLoader.load(service, appLoader)` vẫn không thấy plugin là lỗi không?** Không, vì overload có tham số loader dùng loader **được truyền**, không dùng TCCL.

**8. Service API bị định nghĩa ở cả parent và child, hai bản có cùng tên. Có đảm bảo tương thích không?** Không. Class identity còn phụ thuộc defining loader.

**9. Provider trong named module bắt buộc luôn đăng ký bằng `META-INF/services` không?** Không. Có thể đăng ký trong `module-info.java` bằng `provides ... with ...`.

**10. API Java nào có thể có cơ chế tra provider theo TCCL khác ServiceLoader?** Một số JAXP factory APIs và hệ sinh thái plugin/container; phải xem JavaDoc của API và overload cụ thể, không áp dụng máy móc cùng một quy tắc.

## 13. Nguồn chính thức

- Java SE 17 API `ServiceLoader` — provider configuration, lazy loading, caching, overloads và module usage: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 API `Thread.getContextClassLoader / setContextClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Java SE 17 API `ClassLoader` — parent delegation, defining/initiating loaders: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API `DocumentBuilderFactory` — factory discovery: https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/parsers/DocumentBuilderFactory.html
- Java Language Specification `7.7.2, `uses` và `provides` trong module declarations: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2

**Ghi nhớ:** `ServiceLoader.load(service)` lấy **thread context class loader** để khám phá provider, còn `Class.forName(String)` dùng **caller defining loader**. Muốn plugin được nhận diện đúng, phải bảo đảm provider descriptor/module declaration có thể tìm thấy, service interface được chia sẻ bằng cùng runtime type, và context loader được đặt/khôi phục theo vòng đời tác vụ. Chọn loader chủ động tốt hơn việc hy vọng runtime luôn thấy mọi plugin.

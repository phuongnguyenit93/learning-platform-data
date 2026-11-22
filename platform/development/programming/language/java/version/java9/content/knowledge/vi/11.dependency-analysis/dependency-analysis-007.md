# Bổ sung phụ thuộc được nạp qua dịch vụ hoặc phản chiếu

## Mục tiêu

Trong Java Platform Module System (JPMS), `requires` mô tả các phụ thuộc đã biết khi thiết kế và biên dịch module. Một ứng dụng có thể cần bổ sung implementation hoặc plugin chỉ được biết lúc chạy. Hai cách phổ biến là **nạp implementation qua dịch vụ (`ServiceLoader`)** và **tìm lớp theo tên rồi gọi bằng reflection**.

Hai cách này không tự biến một JAR bất kỳ thành dependency đã được phân giải. Nếu plugin là named module, ứng dụng vẫn phải tìm module, resolve dependency graph và tạo `ModuleLayer` trước khi nạp lớp. Sau đó, service hoặc reflection mới chọn và sử dụng implementation.

## 1. Ba bước cần phân biệt

Với plugin được đóng gói thành module riêng, quy trình runtime có ba bước:

1. **Khám phá:** `ModuleFinder` tìm module trên một module path và cung cấp `ModuleReference`/descriptor.
2. **Phân giải và tạo layer:** `Configuration.resolve(...)` kiểm tra dependency của module gốc; `ModuleLayer` tạo cấu hình runtime và class loader cho module mới.
3. **Tìm implementation:** `ServiceLoader` tìm provider được khai báo trong descriptor, hoặc reflection nạp lớp theo tên từ class loader của layer.

`ServiceLoader` và reflection giải quyết việc chọn implementation. Chúng không thay thế bước resolve module và không tự thêm các dependency bị thiếu vào runtime.

## 2. Nạp implementation qua dịch vụ với ServiceLoader

`ServiceLoader` phù hợp khi ứng dụng định nghĩa một interface hoặc service contract ổn định, còn các module khác cung cấp implementation có thể cài thêm sau.

Trong JPMS, hai phía khai báo service bằng module descriptor:

- Module tiêu thụ dịch vụ dùng `uses ten.package.ServiceType;`.
- Module cung cấp implementation dùng `provides ten.package.ServiceType with ten.package.ProviderType;`.

Service type phải có thể truy cập từ module tiêu thụ, thường bằng cách export package API từ module chứa interface. Provider có thể nằm trong package nội bộ không export; `ServiceLoader` có thể tạo provider đã khai báo trong descriptor.

Ví dụ descriptor của module ứng dụng:

```java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
```

Descriptor của module plugin:

```java
module com.example.plugin {
    requires com.example.spi;
    requires java.logging;
    provides com.example.spi.GreetingService
            with com.example.plugin.internal.GreetingProvider;
}
```

Provider module có thể cần các dependency riêng như `java.logging`, thư viện cấu hình hoặc module API khác. Những dependency đó phải có mặt trong các nguồn mà resolver có thể tìm thấy; khai báo `provides` không tự tải chúng.

### Vì sao dùng ServiceLoader?

- Interface service cho phép ứng dụng phụ thuộc vào hợp đồng thay vì tên class triển khai.
- Provider có thể được thêm hoặc thay thế mà không sửa mã tiêu thụ.
- Module descriptor công bố rõ service nào được dùng và module nào cung cấp service.
- `ServiceLoader` hỗ trợ nhiều provider và khởi tạo provider theo nhu cầu.

Với ứng dụng chạy hoàn toàn trên class path, service provider truyền thống cũng có thể được khai báo bằng file `META-INF/services/<tên-interface>`. Khi dùng named modules, nên khai báo `uses` và `provides` trong `module-info.java`.

## 3. Tìm plugin và tạo ModuleLayer

Khi plugin không được đưa vào boot layer lúc khởi động, ứng dụng có thể tìm plugin trong thư mục riêng, resolve nó cùng dependency rồi tạo layer con.

```java
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

Configuration configuration = ModuleLayer.boot()
        .configuration()
        .resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.example.plugin"));

ModuleLayer.Controller controller = ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader());
ModuleLayer pluginLayer = controller.layer();
```

Ý nghĩa:

- `ModuleFinder.of(Path.of("plugins"))` tìm các module trong thư mục plugin.
- `ModuleLayer.boot().configuration()` là cấu hình cha đã được khởi động, chứa các module nền tảng và module API mà ứng dụng đã yêu cầu.
- `resolve(...)` bắt đầu từ module gốc `com.example.plugin`, sau đó resolve các dependency bắt buộc của nó.
- `ModuleLayer.defineModulesWithOneLoader(...)` định nghĩa các module đã resolve trong layer mới và dùng một class loader chung cho layer đó.

Nếu một dependency bắt buộc không có trong module path hoặc cấu hình cha, resolve thất bại trước khi provider được nạp. Có thể gặp `FindException` hoặc `ResolutionException`; hãy kiểm tra tên module, module path và các chỉ thị `requires`.

`defineModulesWithManyLoaders(...)` là lựa chọn khác khi cần class loader riêng cho từng module trong layer. Chọn cách tạo layer theo yêu cầu cách ly class loader và khả năng chia sẻ kiểu; một layer không phải sandbox bảo mật.

## 4. Tìm service trong một ModuleLayer

Khi provider nằm trong layer con, dùng overload `ServiceLoader.load(layer, ServiceType.class)` để chỉ rõ layer cần dò. Đây là điểm quan trọng với plugin động: overload `load(ServiceType.class)` dựa vào class loader ngữ cảnh và không thể hiện rõ layer plugin mà ứng dụng vừa tạo.

```java
ServiceLoader<GreetingService> services =
        ServiceLoader.load(pluginLayer, GreetingService.class);

GreetingService service = services.findFirst()
        .orElseThrow(() -> new IllegalStateException("No greeting provider found"));

System.out.println(service.greet("Ada"));
```

`ServiceLoader` có thể tìm provider trong layer được chỉ định và các layer cha. Việc duyệt/khởi tạo provider có thể diễn ra lười; lỗi cấu hình hoặc khởi tạo provider có thể xuất hiện khi iterator được duyệt, thường dưới dạng `ServiceConfigurationError`.

Nếu ứng dụng hỗ trợ nhiều plugin cùng cung cấp một service, duyệt toàn bộ provider thay vì `findFirst()`. Nếu thứ tự có ý nghĩa nghiệp vụ, hãy định nghĩa chính sách ưu tiên rõ ràng trong ứng dụng; không dựa vào thứ tự filesystem.

## 5. Ví dụ hoàn chỉnh: service provider trong plugin layer

Ví dụ gồm ba module:

- `com.example.spi`: công bố interface `GreetingService`.
- `com.example.app`: sử dụng service, tìm plugin và tạo layer con.
- `com.example.plugin`: cung cấp implementation, đồng thời phụ thuộc `java.logging`.

Cấu trúc thư mục:

```text
project/
├── src/
│   ├── com.example.spi/
│   │   ├── module-info.java
│   │   └── com/example/spi/GreetingService.java
│   ├── com.example.app/
│   │   ├── module-info.java
│   │   └── com/example/app/Main.java
│   └── com.example.plugin/
│       ├── module-info.java
│       └── com/example/plugin/internal/GreetingProvider.java
├── out/
├── plugin-out/
└── plugins/
    └── com.example.plugin.jar
```

**`src/com.example.spi/module-info.java`**

```java
module com.example.spi {
    exports com.example.spi;
}
```

**`src/com.example.spi/com/example/spi/GreetingService.java`**

```java
package com.example.spi;

public interface GreetingService {
    String greet(String name);
}
```

**`src/com.example.app/module-info.java`**

```java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingService;
}
```

**`src/com.example.app/com/example/app/Main.java`**

```java
package com.example.app;

import com.example.spi.GreetingService;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

public class Main {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: Main <plugin-directory>");
            return;
        }

        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        var configuration = ModuleLayer.boot().configuration()
                .resolve(finder, ModuleFinder.of(), Set.of("com.example.plugin"));

        ModuleLayer pluginLayer = ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader()).layer();

        ServiceLoader<GreetingService> services =
                ServiceLoader.load(pluginLayer, GreetingService.class);
        GreetingService service = services.findFirst()
                .orElseThrow(() -> new IllegalStateException("No provider found"));

        System.out.println("service=" + service.greet("Ada"));
        System.out.println("providerModule=" + service.getClass().getModule().getName());
        System.out.println("pluginInBoot="
                + ModuleLayer.boot().findModule("com.example.plugin").isPresent());
        System.out.println("pluginInChild="
                + pluginLayer.findModule("com.example.plugin").isPresent());
    }
}
```

**`src/com.example.plugin/module-info.java`**

```java
module com.example.plugin {
    requires com.example.spi;
    requires java.logging;
    provides com.example.spi.GreetingService
            with com.example.plugin.internal.GreetingProvider;
}
```

**`src/com.example.plugin/com/example/plugin/internal/GreetingProvider.java`**

```java
package com.example.plugin.internal;

import com.example.spi.GreetingService;
import java.util.logging.Logger;

public final class GreetingProvider implements GreetingService {
    private static final Logger LOG =
            Logger.getLogger(GreetingProvider.class.getName());

    public GreetingProvider() {}

    @Override
    public String greet(String name) {
        LOG.fine("Greeting requested");
        return "Hello, " + name + " from dynamic service";
    }
}
```

### Biên dịch và đóng gói

Chạy trong Windows PowerShell từ thư mục `project`: 

```powershell
New-Item -ItemType Directory -Force out, plugin-out, plugins
javac --module-source-path src -d out -m com.example.spi,com.example.app
javac --module-path out --module-source-path src -d plugin-out -m com.example.plugin
jar --create --file plugins/com.example.plugin.jar -C plugin-out/com.example.plugin .
java --module-path out -m com.example.app/com.example.app.Main plugins
```

Module plugin được biên dịch riêng vào `plugin-out` và đóng gói vào `plugins`; vì vậy nó chưa nằm trong boot layer khi ứng dụng khởi động. `com.example.spi` có trong `out` và boot layer vì ứng dụng khai báo `requires com.example.spi`.

Trên Linux hoặc macOS, lệnh tạo thư mục tương đương là `mkdir -p out plugin-out plugins`; các lệnh `javac`, `jar` và `java` còn lại giữ nguyên.

Stdout trên JDK 24.0.2:

```text
service=Hello, Ada from dynamic service
providerModule=com.example.plugin
pluginInBoot=false
pluginInChild=true
```

Kết quả xác nhận provider được tìm thấy trong child layer. Module plugin không có trong boot layer; nó chỉ được resolve và định nghĩa khi ứng dụng tạo layer con.

## 6. Nạp lớp bằng reflection

Reflection phù hợp khi tên implementation chỉ được biết lúc chạy, ví dụ cấu hình chỉ định tên class, framework cần kiểm tra annotation hoặc ứng dụng phải tích hợp một plugin không triển khai service interface chung.

Với plugin nằm trong `ModuleLayer`, hãy dùng class loader của module đó thay vì gọi `Class.forName(name)` theo class loader mặc định:

```java
ClassLoader pluginLoader = pluginLayer.findLoader("com.example.plugin");
Class<?> type = Class.forName(
        "com.example.plugin.api.PluginEntry",
        true,
        pluginLoader);

Object instance = type.getDeclaredConstructor().newInstance();
```

Điều này chỉ nạp lớp trong module đã được resolve và định nghĩa. Reflection không tự tìm module, resolve dependency hoặc đưa một JAR mới vào layer. Các dependency của module vẫn phải được cung cấp khi tạo cấu hình.

### Exports và opens có vai trò khác nhau

JPMS kiểm soát quyền truy cập ở cấp package:

- `exports package.name;` cho phép module khác truy cập các kiểu và thành viên `public` trong package theo quy tắc readability. Đây là lựa chọn cho API công khai.
- `opens package.name;` cho phép reflection sâu vào các thành viên của package lúc chạy, kể cả thành viên không `public`. Nó không cho phép mã nguồn khác dùng package như API thông thường khi biên dịch.
- `opens package.name to target.module;` chỉ mở package cho module đích được nêu.
- `open module name { ... }` mở tất cả package của module cho deep reflection; chỉ dùng khi thực sự cần phạm vi rộng.

Ví dụ plugin chỉ mở package nội bộ cho module ứng dụng:

```java
module com.example.plugin {
    requires com.example.spi;
    opens com.example.plugin.internal to com.example.app;
}
```

Ứng dụng có thể truy cập một private method qua reflection:

```java
ClassLoader loader = pluginLayer.findLoader("com.example.plugin");
Class<?> secret = Class.forName(
        "com.example.plugin.internal.Secret", true, loader);
Method method = secret.getDeclaredMethod("value");
method.setAccessible(true);
Object result = method.invoke(null);
```

Nếu package không được mở cho module gọi, `setAccessible(true)` có thể ném `InaccessibleObjectException`. `exports` đơn thuần không cho phép reflection truy cập private member. Với plugin động, khai báo `opens` có phạm vi hẹp trong descriptor thường dễ kiểm soát hơn việc mở toàn bộ module.

## 7. Ví dụ reflection với package được mở

Thêm vào descriptor plugin:

```java
module com.example.plugin {
    requires com.example.spi;
    requires java.logging;
    provides com.example.spi.GreetingService
            with com.example.plugin.internal.GreetingProvider;
    opens com.example.plugin.internal to com.example.app;
}
```

Thêm lớp **`src/com.example.plugin/com/example/plugin/internal/Secret.java`**:

```java
package com.example.plugin.internal;

public final class Secret {
    private Secret() {}

    private static String value() {
        return "opened-private-method";
    }
}
```

Sau khi tạo `pluginLayer` như ví dụ trước, thêm đoạn sau vào `Main.main`:

```java
Class<?> secret = Class.forName(
        "com.example.plugin.internal.Secret",
        true,
        pluginLayer.findLoader("com.example.plugin"));
Method method = secret.getDeclaredMethod("value");
method.setAccessible(true);
System.out.println("reflection=" + method.invoke(null));
```

Thêm import `java.lang.reflect.Method`. Stdout đầy đủ:

```text
service=Hello, Ada from dynamic service
providerModule=com.example.plugin
pluginInBoot=false
pluginInChild=true
reflection=opened-private-method
```

Nếu bỏ dòng `opens com.example.plugin.internal to com.example.app;`, việc gọi `method.setAccessible(true)` thất bại với `InaccessibleObjectException` vì module plugin không mở package nội bộ cho module ứng dụng.

## 8. Chọn ServiceLoader hay reflection?

| Tiêu chí | ServiceLoader | Reflection theo tên class |
|---|---|---|
| Hợp đồng | Interface/service type chung | Có thể không có interface chung |
| Khai báo JPMS | `uses` và `provides` | `requires` cho dependency tĩnh; module động vẫn cần resolve/layer |
| Chọn implementation | Tự tìm các provider đã khai báo | Ứng dụng đọc tên class từ cấu hình hoặc metadata |
| Kiểm tra kiểu | Có service interface tại compile time | Thường phải kiểm tra kiểu, constructor và method lúc chạy |
| Quyền package | Provider được khai báo có thể nằm trong package không export | Truy cập public cần export/readability; deep reflection cần opens |
| Lỗi thường gặp | Không có provider, `ServiceConfigurationError` | `ClassNotFoundException`, `NoSuchMethodException`, `InvocationTargetException`, `InaccessibleObjectException` |

Ưu tiên `ServiceLoader` khi thiết kế extension point mới vì hợp đồng rõ ràng và provider được khai báo trong descriptor. Dùng reflection khi framework hoặc cấu hình thật sự yêu cầu tên class, introspection hoặc truy cập thành viên theo metadata.

## 9. Xử lý lỗi và các điểm cần kiểm tra

- **Module không tìm thấy:** kiểm tra `ModuleFinder` có tìm được JAR/module không và tên trong tập root có khớp descriptor không.
- **Thiếu dependency:** kiểm tra tất cả `requires` của plugin và dependency bắc cầu có trong finder hoặc parent configuration không.
- **Không có service provider:** xác nhận consumer khai báo `uses`, provider khai báo `provides`, service type giống hệt nhau và plugin module được đưa vào layer được truyền cho `ServiceLoader.load`.
- **`ServiceConfigurationError`:** kiểm tra provider class, constructor, kiểu service và lỗi khởi tạo provider.
- **`ClassNotFoundException`:** kiểm tra tên class và class loader lấy từ đúng layer/module.
- **`NoSuchMethodException`:** kiểm tra method hoặc constructor có đúng tên, kiểu tham số và visibility không.
- **`InaccessibleObjectException`:** kiểm tra package có `opens` tới đúng module gọi hay không; `exports` không thay thế `opens` cho private member.
- **`InvocationTargetException`:** xem `getCause()` để tìm exception thực sự phát sinh bên trong method được gọi.
- **Khác biệt class loader:** không truyền interface service được nạp từ một class loader khác với interface mà provider triển khai; hai class cùng tên nhưng khác class loader vẫn là hai kiểu khác nhau.

Không nên bắt mọi lỗi rồi tiếp tục như thể plugin đã được nạp. Ghi lại tên module, tên provider/class và nguyên nhân gốc để chẩn đoán.

## 10. Các nguyên tắc thiết kế

1. Xác định API service nhỏ, ổn định và đặt trong module riêng để ứng dụng cùng provider có thể phụ thuộc vào.
2. Để ứng dụng khai báo `uses`; để module plugin khai báo `provides` và mọi `requires` cần thiết.
3. Resolve module plugin trước khi tạo layer; không kỳ vọng `ServiceLoader` hoặc reflection tự tìm dependency bị thiếu.
4. Dùng `ServiceLoader.load(layer, Service.class)` khi provider nằm trong layer động.
5. Chỉ dùng reflection theo tên khi có lý do cụ thể; kiểm tra kiểu và chữ ký method trước khi gọi.
6. Export package cho API công khai; chỉ opens các package nội bộ thực sự cần deep reflection.
7. Đóng gói plugin và dependency theo cấu trúc module path có thể kiểm soát, tránh hai module trùng tên trong cùng finder.
8. Không xem module layer hoặc reflection là sandbox bảo mật. Với plugin không tin cậy, cần cách ly bằng tiến trình hoặc cơ chế của hệ điều hành.

## Tài liệu tham khảo

1. [Java SE 25 API — ServiceLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html), cách tìm provider trong module layer và class loader.
2. [Java SE 25 API — ModuleLayer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html), tạo layer và class loader cho module động.
3. [Java SE 25 API — Configuration](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/Configuration.html), resolve dependency graph.
4. [Java SE 25 API — ModuleFinder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleFinder.html), tìm module trên module path.
5. [Java SE 25 API — Module](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html), readability, exports và opens.
6. [Java SE 25 API — AccessibleObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html), kiểm soát truy cập phản chiếu.
7. [Java Language Specification — Module Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7), các chỉ thị `requires`, `uses`, `provides`, `exports` và `opens`.
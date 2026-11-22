# Configuration tạo layer mới trong Java ModuleLayer (JPMS)

## 1. Mục tiêu

Trong Java Platform Module System (JPMS, từ Java 9), một chương trình có thể tạo thêm `ModuleLayer` khi đang chạy để nạp các module ngoài tập module được giải quyết lúc khởi động. Tình huống phổ biến là ứng dụng chính chạy ổn định trong boot layer, còn các plugin được tìm trong một thư mục riêng và nạp vào layer con khi cần.

Để làm điều đó, cần phân biệt hai khái niệm:

- `Configuration` (`java.lang.module.Configuration`) là **đồ thị các module đã được phân giải**: module nào được chọn, module nào yêu cầu module nào, và cấu hình cha là gì. Configuration chưa tạo `Module` đang chạy và chưa tải class.
- `ModuleLayer` (`java.lang.ModuleLayer`) là **môi trường module lúc chạy** được tạo từ một `Configuration`, liên kết các module đã giải quyết với các `ClassLoader` tương ứng và với layer cha.

Luồng cơ bản:

```text
Các JAR module trong plugins/
            |
            v
    ModuleFinder.of(...)
            |
            v
ModuleLayer.boot().configuration()
    .resolve(finder, after, roots)
            |
            v
       Configuration
            |
            v
bootLayer.defineModulesWithOneLoader(config, parentLoader)
            |
            v
       ModuleLayer mới
            |
            v
  ServiceLoader / findLoader / findModule
```

Đây là cách xây dựng một layer mới; `Configuration` không tự trở thành layer chỉ bằng việc gọi `resolve`.

## 2. Các thành phần liên quan

| Thành phần | Vai trò |
| --- | --- |
| `ModuleFinder` | Tìm mô tả module trong thư mục hoặc JAR modular, ví dụ `plugins/`. |
| `ModuleDescriptor` | Mô tả `requires`, `exports`, `uses`, `provides` và các thuộc tính module. |
| `Configuration` | Kết quả phân giải module; có các `ResolvedModule` và quan hệ đọc ở mức cấu hình. |
| `ModuleLayer.boot()` | Layer mặc định sau khi JVM khởi động; thường được dùng làm layer cha. |
| `ModuleLayer.defineModulesWithOneLoader(...)` | Định nghĩa các module của configuration mới trong một layer con, dùng chung một loader cho các module ở layer đó. |
| `ModuleLayer.findModule(...)` | Tìm module theo tên trong layer đang xét và các layer cha. |
| `ModuleLayer.findLoader(...)` | Lấy loader được gán cho module nằm trong layer này. |
| `ServiceLoader.load(layer, serviceType)` | Tìm implementation của dịch vụ trong layer được chỉ định và các layer cha phù hợp. |

Một `Configuration` mới có thể tham chiếu các module đã tồn tại ở configuration cha. Những module cha không bị sao chép vào layer con.

## 3. Tạo Configuration từ ModuleFinder

Giả sử ứng dụng host đã khởi động và `plugins/` chứa `com.example.plugin.jar`. Module `com.example.plugin` sẽ được nạp vào layer mới.

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class CreateConfiguration {
    public static void main(String[] args) {
        ModuleLayer parentLayer = ModuleLayer.boot();
        Configuration parentConfig = parentLayer.configuration();

        ModuleFinder before = ModuleFinder.of(Path.of("plugins"));
        ModuleFinder after = ModuleFinder.of(); // Không tìm thêm module ngoài nguồn đã chọn

        Configuration childConfig = parentConfig.resolve(
                before,
                after,
                Set.of("com.example.plugin")
        );

        childConfig.modules().forEach(resolved ->
                System.out.println(resolved.name())
        );
    }
}
```

Ý nghĩa của các tham số `resolve(before, after, roots)`:

1. `before` là nguồn module ưu tiên tìm trước khi xét các cấu hình cha. Ở ví dụ là các module trong `plugins/`.
2. `after` là nguồn bổ sung để tìm module chưa tìm thấy ở `before` và các cấu hình cha. `ModuleFinder.of()` tạo finder rỗng.
3. `roots` là tên module gốc cần phân giải. Bộ phân giải đưa cả các dependency `requires` cần thiết vào đồ thị.

`Configuration` là bất biến sau khi tạo. Nếu cần chọn tập module khác, hãy tạo configuration khác và định nghĩa layer mới từ configuration đó.

Khi plugin phụ thuộc vào `com.example.api` đã nằm trong boot layer, bộ phân giải có thể sử dụng module ở configuration cha. Plugin không cần đóng gói bản sao của API.

## 4. Ví dụ hoàn chỉnh: nạp plugin qua SPI

Ví dụ dưới đây gồm ba module:

- `com.example.api` định nghĩa giao diện dịch vụ; có mặt trong boot layer.
- `com.example.host` là ứng dụng chính; có mặt trong boot layer.
- `com.example.plugin` triển khai dịch vụ; được đưa vào layer con lúc chạy.

Cấu trúc nguồn:

```text
src/
  api/
    module-info.java
    com/example/api/GreetingProvider.java
  host/
    module-info.java
    com/example/host/Main.java
  plugin/
    module-info.java
    com/example/plugin/HelloProvider.java
mods/       # API và host khi chạy
plugins/    # JAR plugin được tìm động
```

### 4.1. API module

`src/api/module-info.java`:

```java
module com.example.api {
    exports com.example.api;
}
```

`src/api/com/example/api/GreetingProvider.java`:

```java
package com.example.api;

public interface GreetingProvider {
    String greet(String name);
}
```

### 4.2. Plugin module

`src/plugin/module-info.java`:

```java
module com.example.plugin {
    requires com.example.api;

    provides com.example.api.GreetingProvider
            with com.example.plugin.HelloProvider;
}
```

`src/plugin/com/example/plugin/HelloProvider.java`:

```java
package com.example.plugin;

import com.example.api.GreetingProvider;

public class HelloProvider implements GreetingProvider {
    public HelloProvider() {}

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Plugin cung cấp dịch vụ bằng `provides ... with ...`. Không bắt buộc `exports com.example.plugin` chỉ để `ServiceLoader` khởi tạo provider đã khai báo hợp lệ.

### 4.3. Host module và điểm tạo layer

`src/host/module-info.java`:

```java
module com.example.host {
    requires com.example.api;
    uses com.example.api.GreetingProvider;
}
```

`src/host/com/example/host/Main.java`:

```java
package com.example.host;

import com.example.api.GreetingProvider;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

public class Main {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();

        // Bước 1: phát hiện JAR modular nằm ngoài module-path của host.
        ModuleFinder plugins = ModuleFinder.of(Path.of("plugins"));

        // Bước 2: phân giải module plugin và những dependency cần thiết.
        Configuration config = boot.configuration().resolve(
                plugins,
                ModuleFinder.of(),
                Set.of("com.example.plugin")
        );

        // Bước 3: định nghĩa các module vừa phân giải trong layer con.
        ModuleLayer pluginLayer = boot.defineModulesWithOneLoader(
                config,
                ClassLoader.getSystemClassLoader()
        );

        // Bước 4: lấy provider từ layer con qua hợp đồng API chung.
        ServiceLoader<GreetingProvider> providers =
                ServiceLoader.load(pluginLayer, GreetingProvider.class);

        for (GreetingProvider provider : providers) {
            System.out.println(provider.greet("Minh"));
        }

        // Quan sát kết quả nạp module, phục vụ chẩn đoán.
        pluginLayer.findModule("com.example.plugin")
                .ifPresent(module ->
                        System.out.println("Đã nạp: " + module.getName())
                );
    }
}
```

Đầu ra dự kiến:

```text
Xin chào, Minh!
Đã nạp: com.example.plugin
```

Ứng dụng host và API cần dùng cùng một định nghĩa `GreetingProvider` từ parent layer. Nếu host và plugin sử dụng hai bản class API được tải ở các loader khác nhau, có thể gặp lỗi kiểu dữ liệu (`ClassCastException`) hoặc không nhận diện đúng SPI.

### 4.4. Biên dịch và chạy

Tạo sẵn các thư mục `build/api`, `build/plugin`, `build/host`, `mods` và `plugins`. Với JDK 9 trở lên, từ thư mục gốc của ví dụ:

```bash
javac -d build/api \
  src/api/module-info.java \
  src/api/com/example/api/GreetingProvider.java

jar --create --file mods/com.example.api.jar -C build/api .

javac --module-path mods -d build/plugin \
  src/plugin/module-info.java \
  src/plugin/com/example/plugin/HelloProvider.java

jar --create --file plugins/com.example.plugin.jar -C build/plugin .

javac --module-path mods -d build/host \
  src/host/module-info.java \
  src/host/com/example/host/Main.java

jar --create --file mods/com.example.host.jar -C build/host .

java --module-path mods -m com.example.host/com.example.host.Main
```

Dấu `\` cuối dòng ở đoạn lệnh trên dùng để xuống dòng trong shell Unix. Trong PowerShell hoặc CMD, có thể nhập mỗi lệnh trên một dòng. Mấu chốt là `mods/` chứa host và API, còn `plugins/` được chương trình đọc khi đang chạy; đặt plugin vào boot module path sẽ làm thay đổi cấu trúc phân giải ban đầu.

## 5. Chọn cách tạo layer từ Configuration

Sau khi có configuration, JPMS cung cấp các cách ánh xạ module sang class loader:

### Một loader cho layer

```java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithOneLoader(config, ClassLoader.getSystemClassLoader());
```

Đây là cách ngắn gọn khi nhóm module mới có thể dùng chung loader. Các module trong layer mới được ánh xạ vào một loader do API thiết lập, còn tham số `parentLoader` xác định loader cha phục vụ delegation.

### Một loader riêng cho từng module

```java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithManyLoaders(config, ClassLoader.getSystemClassLoader());
```

Cách này tạo mapping tách biệt hơn giữa các module của layer. Việc chia loader không tự động biến plugin thành sandbox bảo mật.

### Ánh xạ loader tùy chỉnh

```java
// Chỉ là khuôn mẫu; hàm mapping phải trả về loader phù hợp cho từng module.
ModuleLayer layer = ModuleLayer.boot()
        .defineModules(config, moduleName -> chooseLoader(moduleName));
```

`defineModules` nhận hàm ánh xạ tên module sang `ClassLoader`. Đây là phương án nâng cao khi ứng dụng đã quản lý loader và package ownership rõ ràng.

Với nhiều parent layer, nhóm API tĩnh như `ModuleLayer.defineModulesWithOneLoader(config, parentLayers, parentLoader)` trả về `ModuleLayer.Controller`; lấy layer mới bằng `controller.layer()`. Các parent layer truyền vào phải tương ứng với danh sách configuration cha của `config`.

## 6. resolve và resolveAndBind khác nhau thế nào?

`resolve(...)` bắt đầu từ tập `roots` rồi đi theo các dependency bắt buộc (`requires`). Đây là lựa chọn rõ ràng khi đã biết tên module plugin phải nạp.

`resolveAndBind(...)` còn thực hiện service binding: khi các module đã giải quyết khai báo `uses`, bộ phân giải có thể tìm thêm module provider phù hợp trong các nguồn module được cung cấp. Điều này hữu ích cho hệ thống mở rộng bằng SPI, nơi host không muốn liệt kê trước tên từng provider.

Ví dụ thay cách phân giải ở trên:

```java
Configuration config = ModuleLayer.boot().configuration()
        .resolveAndBind(
                ModuleFinder.of(Path.of("plugins")),
                ModuleFinder.of(),
                Set.of("com.example.plugin")
        );
```

`resolveAndBind` không thay thế việc khai báo `uses` và `provides` đúng trong `module-info.java`; cũng không tự quét mọi thư mục trên máy. Phạm vi tìm kiếm phụ thuộc các `ModuleFinder` được truyền vào.

Khi chỉ có một plugin đã xác định bằng tên, `resolve` là đủ cho ví dụ ở mục 4.

## 7. Kiểm tra graph và layer sau khi tạo

```java
Configuration config = pluginLayer.configuration();

// Các module thuộc configuration của chính layer con.
config.modules().forEach(rm -> {
    System.out.println("Module: " + rm.name());
    rm.reads().forEach(dep ->
            System.out.println("  reads -> " + dep.name())
    );
});

// Các module runtime được định nghĩa trực tiếp trong layer con.
pluginLayer.modules().forEach(m ->
        System.out.println("Runtime module: " + m.getName())
);

// Có thể tìm module trong layer này hoặc ở layer cha.
System.out.println(pluginLayer.findModule("com.example.api").isPresent());

// findLoader yêu cầu module thuộc chính layer được truy vấn.
ClassLoader pluginLoader = pluginLayer.findLoader("com.example.plugin");
System.out.println(pluginLoader);
```

`Configuration.modules()` và `ModuleLayer.modules()` đều phản ánh module trực tiếp của đối tượng đang xét; không nên mặc định chúng chứa toàn bộ module ở các parent. Muốn xem parent layers, dùng `pluginLayer.parents()`.

Khi cần tự tải một class plugin cụ thể, có thể lấy loader qua `findLoader` rồi dùng `Class.forName(className, true, loader)`. Tuy nhiên, việc tìm được class không tự cấp quyền truy cập vào các package chưa `exports` hoặc `opens`. Khi chỉ cần gọi điểm mở rộng, SPI thường làm giảm phụ thuộc vào tên class nội bộ của plugin.

## 8. Lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân hay gặp | Hướng xử lý |
| --- | --- | --- |
| `FindException` | Không tìm thấy module gốc hoặc dependency; JAR không phải module mong đợi. | Kiểm tra `Path` truyền vào `ModuleFinder`, tên module thật và cấu trúc JAR. |
| `ResolutionException` | Đồ thị module có xung đột, ví dụ về package hoặc ràng buộc đọc. | Kiểm tra `requires`, package trùng và các dependency transitively readable. |
| `LayerInstantiationException` | Không thể định nghĩa graph bằng mapping class loader đã chọn, chẳng hạn package trùng trong cùng loader. | Đổi cách ánh xạ loader hoặc chỉnh cấu trúc module/package. |
| Không tìm thấy provider qua `ServiceLoader` | Thiếu `uses`/`provides`, provider chưa được đưa vào graph, hoặc gọi `load` trên layer khác. | Kiểm tra descriptor, roots/`resolveAndBind` và layer truyền cho `ServiceLoader.load`. |
| `IllegalAccessException` / `InaccessibleObjectException` | Code ngoài module cố truy cập package chưa `exports` hoặc reflective access chưa `opens`. | Thiết kế API công khai và khai báo `exports`/`opens` phù hợp; tránh mở rộng quyền không cần thiết. |
| `ClassCastException` / `ServiceConfigurationError` | Interface dịch vụ khác class identity hoặc provider không hợp lệ. | Dùng chung API ở layer cha, kiểm tra constructor và khai báo `provides`. |

Một vài điểm cần nhớ:

- Nếu module đã có trong boot layer, `resolve` cho layer con không có nghĩa JVM sẽ “nạp lại” module đó vào layer con. Module ở configuration cha tiếp tục được sử dụng từ cha.
- Các module có cùng tên có thể thuộc những layer khác nhau, nhưng sự tồn tại của các layer không cho phép bỏ qua nguyên tắc đọc module, export package hay identity của class loader.
- Tạo layer mới không tự động cập nhật layer cũ hoặc thay thế class đã nạp. Muốn thay phiên bản plugin, thường cần tạo configuration/layer mới và quản lý vòng đời tham chiếu đến phiên bản cũ.
- Layer là cơ chế tổ chức và liên kết module, **không phải** cơ chế sandbox bảo mật để chạy mã không tin cậy.

## 9. Khi nào nên dùng Configuration + ModuleLayer?

Nên xem xét khi ứng dụng cần nạp tập module theo lựa chọn lúc chạy, cần quản lý plugin từ thư mục độc lập với boot module path, hoặc cần tạo những không gian module khác nhau cho các phiên bản extension.

Nếu toàn bộ module đã biết khi đóng gói và không có nhu cầu nạp động, cấu hình module path và để JVM tạo boot layer thường đơn giản hơn.

Quy trình thao tác cần thuộc:

1. Xác định layer cha và lấy `parentLayer.configuration()`.
2. Tạo `ModuleFinder` để tìm module mới.
3. Gọi `resolve` hoặc `resolveAndBind` với roots có chủ đích.
4. Chọn chiến lược class loader và định nghĩa `ModuleLayer` mới.
5. Truy cập module qua SPI, `findModule` hoặc `findLoader`.
6. Kiểm tra đồ thị và lỗi phân giải khi module/dependency không hợp lệ.

## 10. Bài tập thực hành

1. Thêm module `com.example.plugin.fr` cùng triển khai `GreetingProvider`, đặt JAR vào `plugins/`. Cho cả hai module plugin vào tập roots và quan sát hai provider được tìm thấy.
2. Thử bỏ `requires com.example.api` khỏi plugin rồi biên dịch để thấy vai trò của dependency trong module descriptor.
3. Thử bỏ `provides ... with ...` và so sánh kết quả của `ServiceLoader.load(pluginLayer, GreetingProvider.class)`.
4. In danh sách `config.modules()`, `pluginLayer.modules()`, `pluginLayer.parents()` và giải thích module nào thuộc layer cha.
5. Chuyển `defineModulesWithOneLoader` sang `defineModulesWithManyLoaders` và quan sát loader của plugin qua `findLoader`.

**Ghi nhớ:** `Configuration` quyết định **module nào và quan hệ đọc ra sao**; `ModuleLayer` quyết định **các module đã giải quyết được hiện thực hóa trong runtime và gắn với class loader nào**.
# `ModuleLayer.boot()` và tạo lớp mô-đun con trong Java

`ModuleLayer` là API JPMS dùng để biểu diễn một lớp (layer) các module đã được phân giải và nạp tại runtime. JVM tạo sẵn boot layer khi khởi động; ứng dụng có thể truy cập nó bằng `ModuleLayer.boot()`. Khi cần nạp plugin hoặc một nhóm module động sau khi ứng dụng đã chạy, có thể tìm module, giải quyết cấu hình rồi tạo một child layer có boot layer làm parent.

Mỗi layer có module graph và quan hệ parent riêng. Module trong child layer có thể đọc các module ở parent theo quy tắc readability của JPMS, trong khi module mới được định nghĩa trong child layer và có thể dùng class loader riêng. Layer giúp tổ chức việc nạp module trong cùng một JVM; nó không phải sandbox bảo mật hay tiến trình cách ly.

## 1. Module layer là gì?

Module layer là một runtime container cho các module đã được resolve. Một layer có:

- **Configuration:** kết quả giải quyết module graph, gồm module roots và dependency cần thiết.
- **Module objects:** các module được định nghĩa trong layer.
- **Class loaders:** loader gắn với module theo chiến lược khi tạo layer.
- **Parent layers:** một hoặc nhiều layer cha mà module trong layer hiện tại có thể phụ thuộc vào.

Layer có thể được tổ chức thành cây hoặc đồ thị có nhiều parent. Mô hình phổ biến là một ứng dụng có boot layer và tạo một child layer cho mỗi nhóm plugin:

```text
Boot layer (JVM tạo khi khởi động)
├── java.base
├── java.logging
├── các module ứng dụng đã resolve
└── Child layer (ứng dụng tạo lúc runtime)
    ├── com.acme.plugin.alpha
    └── dependency của plugin
```

Child layer không sửa nội dung boot layer. Module mới được định nghĩa trong child layer; các module của boot layer tiếp tục nằm ở layer ban đầu.

## 2. `ModuleLayer.boot()`

`ModuleLayer.boot()` trả về boot layer được JVM tạo trong quá trình khởi động. Đây là điểm bắt đầu để ứng dụng xem các module nền tảng và module ứng dụng đã được resolve:

```java
ModuleLayer boot = ModuleLayer.boot();

System.out.println("Boot modules: " + boot.modules().size());
System.out.println("java.base present: "
        + boot.findModule("java.base").isPresent());
System.out.println("Boot configuration: " + boot.configuration());
```

Các API thường dùng:

| API | Công dụng |
|---|---|
| `ModuleLayer.boot()` | Lấy boot layer của JVM hiện tại. |
| `ModuleLayer.parents()` | Lấy danh sách layer cha trực tiếp. |
| `ModuleLayer.modules()` | Lấy các module được định nghĩa trực tiếp trong layer hiện tại. |
| `ModuleLayer.findModule(name)` | Tìm module theo tên trong layer và các parent layer. |
| `ModuleLayer.configuration()` | Lấy configuration đã resolve để tạo layer. |
| `ModuleLayer.findLoader(name)` | Lấy class loader gắn với module trong layer hoặc parent layer có tên tương ứng. |

`modules()` chỉ liệt kê module thuộc layer hiện tại; `findModule()` còn tìm trong các parent layer. Vì vậy, khi muốn biết một module được định nghĩa ở layer nào, hãy kiểm tra `modules()` của layer đó thay vì chỉ dựa vào `findModule()`.

Boot layer thường có platform layer làm parent. Không nên giả định mọi module có thể tìm thấy trên module path đều đã nằm trong boot layer: module phải được resolve khi JVM khởi động thông qua dependency hoặc root module.

## 3. Vì sao cần tạo child layer?

Child layer hữu ích khi ứng dụng muốn nạp module sau thời điểm khởi động, ví dụ:

- Plugin được cài thêm sau khi ứng dụng đã chạy.
- Các implementation thay thế cho một API chung.
- Nhiều nhóm plugin cần module graph hoặc class loader riêng.
- Một hệ thống cần resolve module theo cấu hình hoặc theo thư mục plugin.
- Kiểm thử hoặc chạy một phiên bản module trong layer riêng mà không đưa nó vào boot layer.

Nếu toàn bộ module đã biết từ đầu và luôn cần trong tiến trình, đặt chúng trên module path và resolve cùng ứng dụng thường đơn giản hơn. Tạo layer động phù hợp khi vòng đời nạp module thực sự cần tách biệt.

## 4. Quy trình tạo child layer

Việc tạo layer thường có bốn bước:

1. **Tìm module:** tạo `ModuleFinder` trỏ tới thư mục hoặc JAR chứa plugin.
2. **Resolve configuration:** dùng configuration của boot layer để resolve các module root và dependency.
3. **Define layer:** chọn class-loader strategy và tạo layer với boot layer làm parent.
4. **Load và sử dụng:** tìm module/class loader trong child layer rồi gọi API của plugin.

Ví dụ các API quan trọng:

```java
ModuleFinder finder = ModuleFinder.of(pluginPath);

Configuration configuration = ModuleLayer.boot()
        .configuration()
        .resolve(finder, ModuleFinder.of(), Set.of("com.acme.plugin"));

ModuleLayer.Controller controller = ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader());

ModuleLayer child = controller.layer();
```

`resolve()` trả về `Configuration`; nó chưa tạo class loader hoặc định nghĩa module trong JVM. `defineModulesWithOneLoader()` mới tạo layer và các module runtime. Đối tượng `Controller` cho phép ứng dụng lấy layer vừa tạo và, khi thực sự cần, điều chỉnh một số quan hệ truy cập runtime.

## 5. Tìm module bằng `ModuleFinder`

`ModuleFinder` tìm module reference trong một hoặc nhiều nguồn. Ví dụ:

```java
ModuleFinder finder = ModuleFinder.of(
        Path.of("plugins"),
        Path.of("optional-modules"));
```

`ModuleFinder.of(path)` có thể tìm explicit modular JAR, automatic module JAR và exploded module directory hợp lệ. Mỗi module cần có module name duy nhất trong tập được resolve.

Để kiểm tra các module finder nhìn thấy:

```java
finder.findAll().forEach(reference ->
        System.out.println(reference.descriptor().name()));
```

Không nhầm `ModuleFinder` với class loader. Finder chỉ tìm và cung cấp mô tả/nguồn module; class loader được tạo ở bước define layer.

## 6. Resolve module graph bằng `Configuration`

Configuration của boot layer là điểm xuất phát để resolve child configuration:

```java
Configuration parentConfiguration = ModuleLayer.boot().configuration();

Configuration childConfiguration = parentConfiguration.resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin"));
```

Tham số của `resolve(before, after, roots)`:

- `before`: finder có độ ưu tiên trước các module đã có trong parent configuration.
- `after`: finder được tìm sau parent configuration.
- `roots`: tên các module muốn dùng làm điểm bắt đầu của graph.

Resolver tìm các module roots và dependency bắc cầu qua `requires`. Nếu module phụ thuộc không tìm thấy, tên module trùng hoặc graph vi phạm quy tắc JPMS, bước resolve có thể thất bại trước khi tạo layer.

### `resolve()` và `resolveAndBind()`

`resolve()` giải quyết graph dựa trên các module roots và quan hệ `requires`. `resolveAndBind()` thực hiện thêm service binding: các provider module phù hợp với service mà module graph sử dụng có thể được đưa vào graph.

```java
Configuration childConfiguration = parentConfiguration.resolveAndBind(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin.host"));
```

Dùng `resolveAndBind()` khi kiến trúc plugin dựa trên `uses`/`provides` và muốn resolver tìm provider module theo cơ chế service binding. Nếu plugin được chọn trực tiếp theo tên và không cần service binding, `resolve()` thường đủ.

## 7. Chọn class-loader strategy khi define layer

JPMS cung cấp ba cách chính để định nghĩa module trong layer:

| API | Cách gắn class loader | Khi phù hợp |
|---|---|---|
| `defineModulesWithOneLoader(...)` | Tất cả module mới trong configuration dùng chung một loader. | Nhóm module có quan hệ chặt chẽ hoặc plugin cần một namespace loader chung. |
| `defineModulesWithManyLoaders(...)` | Mỗi module mới có loader riêng. | Muốn tách namespace loader giữa các module trong layer. |
| `defineModules(..., Function<String, ClassLoader>)` | Ứng dụng cung cấp loader cho từng tên module. | Có class-loader strategy riêng hoặc tích hợp hệ thống nạp lớp đặc biệt. |

Cả ba API nhận configuration và danh sách parent layers. Với các overload `WithOneLoader`/`WithManyLoaders`, tham số class loader cuối là parent loader của các loader mới. Chọn parent loader phù hợp với cách ứng dụng nạp API dùng chung.

Ví dụ một loader cho toàn bộ plugin modules:

```java
ModuleLayer.Controller controller = ModuleLayer.defineModulesWithOneLoader(
        childConfiguration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader());
ModuleLayer child = controller.layer();
```

Ví dụ mỗi module có loader riêng:

```java
ModuleLayer.Controller controller = ModuleLayer.defineModulesWithManyLoaders(
        childConfiguration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader());
ModuleLayer child = controller.layer();
```

Không chọn nhiều loader chỉ vì nghĩ rằng nó tự tạo sandbox. Class loader tách namespace nạp lớp; mã plugin vẫn chạy trong cùng JVM và có thể sử dụng các quyền mà tiến trình cho phép.

## 8. Lấy class loader và gọi class trong child layer

Sau khi tạo layer, dùng `findLoader(moduleName)` để lấy loader của module. Có thể nạp class theo loader này:

```java
ClassLoader pluginLoader = child.findLoader("com.acme.plugin");
Class<?> pluginClass = Class.forName(
        "com.acme.plugin.PluginMain", true, pluginLoader);
```

Nếu ứng dụng gọi class qua reflection từ module khác, package chứa class cần được export phù hợp và class/member phải có access hợp lệ. Cách tốt hơn cho plugin lâu dài là định nghĩa một service API ổn định trong parent layer rồi dùng `ServiceLoader` để tìm implementation, thay vì hard-code tên class và method.

Ví dụ khi service API đã nằm trong boot layer:

```java
ServiceLoader<PluginService> services =
        ServiceLoader.load(child, PluginService.class);

for (PluginService service : services) {
    service.start();
}
```

Consumer module cần khai báo `uses`; provider module cần khai báo `provides ... with ...`. Khi provider nằm trong child layer, truyền layer đó vào `ServiceLoader.load(layer, serviceType)` để tìm provider trong layer được chọn và các parent layer của nó.

## 9. Ví dụ hoàn chỉnh: nạp một plugin vào child layer

Ví dụ dưới đây chạy host trên classpath và nạp một explicit module plugin từ thư mục `plugin-mods`. Plugin được định nghĩa trong child layer có boot layer làm parent.

Cấu trúc thư mục:

```text
workspace/
├── plugin-src/
│   └── com.acme.plugin/
│       ├── module-info.java
│       └── com/acme/plugin/PluginMain.java
├── plugin-mods/
└── host-src/
    └── Main.java
```

**1. Module plugin — `plugin-src/com.acme.plugin/module-info.java`:**

```java
module com.acme.plugin {
    exports com.acme.plugin;
}
```

Package được export để host trên classpath có thể gọi class public của plugin trong ví dụ này.

**2. Class plugin — `plugin-src/com.acme.plugin/com/acme/plugin/PluginMain.java`:**

```java
package com.acme.plugin;

public final class PluginMain {
    private PluginMain() {
    }

    public static String message() {
        return "Loaded in child layer";
    }
}
```

**3. Host — `host-src/Main.java`:**

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public class Main {
    public static void main(String[] args) throws Exception {
        Path pluginPath = Path.of(args[0]);
        ModuleFinder finder = ModuleFinder.of(pluginPath);

        Configuration configuration = ModuleLayer.boot()
                .configuration()
                .resolve(finder, ModuleFinder.of(), Set.of("com.acme.plugin"));

        ModuleLayer.Controller controller = ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader());
        ModuleLayer child = controller.layer();

        ClassLoader pluginLoader = child.findLoader("com.acme.plugin");
        Class<?> pluginClass = Class.forName(
                "com.acme.plugin.PluginMain", true, pluginLoader);
        Object message = pluginClass.getMethod("message").invoke(null);

        System.out.println("boot contains plugin: "
                + ModuleLayer.boot().findModule("com.acme.plugin").isPresent());
        System.out.println("child contains plugin: "
                + child.findModule("com.acme.plugin").isPresent());
        System.out.println(message);
    }
}
```

### Biên dịch plugin và host

Chạy từ thư mục `workspace/` bằng JDK 17 trở lên:

```shell
javac --module-source-path plugin-src -d plugin-mods -m com.acme.plugin
javac -d host-classes host-src/Main.java
```

Lệnh đầu biên dịch plugin thành exploded module directory `plugin-mods/com.acme.plugin`. Lệnh thứ hai biên dịch host thành classpath application.

### Chạy host và nạp plugin

```shell
java -cp host-classes Main plugin-mods
```

Stdout:

```text
boot contains plugin: false
child contains plugin: true
Loaded in child layer
```

Ví dụ đã được biên dịch và chạy bằng JDK 24.0.2. Kết quả xác nhận `com.acme.plugin` không được định nghĩa trong boot layer nhưng có trong child layer; host đã lấy loader từ child và gọi được class plugin.

## 10. Quản lý nhiều parent layers và module access

API define layer nhận danh sách parent layers, không chỉ một parent. Điều này cho phép một child layer đọc module từ nhiều nhánh layer cha, miễn là các configuration và module graph tương thích.

```java
List<ModuleLayer> parents = List.of(
        ModuleLayer.boot(),
        anotherLayer);

ModuleLayer.Controller controller = ModuleLayer.defineModulesWithOneLoader(
        childConfiguration, parents, ClassLoader.getSystemClassLoader());
```

Khi thiết kế nhiều parent, tránh đưa các phiên bản không tương thích của cùng một module name vào các nhánh khác nhau. Hãy giữ service API và các kiểu dùng chung trong parent layer chung để tránh tạo hai bản class cùng tên nhưng khác identity.

`ModuleLayer.Controller` còn cung cấp các thao tác runtime như `addReads`, `addExports`, `addOpens` và `addUses`. Chúng điều chỉnh quan hệ module/access cho các module thuộc layer do controller quản lý. Chỉ sử dụng khi có nhu cầu cụ thể; ưu tiên khai báo dependency và access trong `module-info.java` để module graph thể hiện đúng thiết kế.

## 11. Vòng đời và giới hạn của child layer

Layer không có API `close()` chung để tự động dỡ toàn bộ module hoặc class loader. Việc một plugin có thể được thu hồi khỏi ứng dụng phụ thuộc vào việc ứng dụng giải phóng mọi tham chiếu tới layer, module, class loader, class, instance, thread, thread context class loader và resource do plugin tạo.

Để hỗ trợ unload:

- Tránh giữ static reference từ boot layer tới class hoặc instance của plugin.
- Dừng thread, executor, timer và callback do plugin tạo trước khi bỏ layer.
- Gỡ listener, hook và thread context class loader trỏ tới plugin.
- Đóng các tài nguyên do plugin mở, chẳng hạn file hoặc socket.
- Không giữ `Class`, `Method`, `ServiceLoader`, provider instance hoặc class loader trong cache toàn cục sau khi plugin bị tháo.

Ngay cả khi không còn tham chiếu rõ ràng, việc thu hồi class loader và metadata lớp do garbage collector quyết định. Không thể bảo đảm unload tức thời chỉ bằng cách bỏ biến tham chiếu tới `ModuleLayer`.

Layer cũng không phải ranh giới bảo mật. Plugin chạy trong cùng tiến trình, có thể tiêu thụ CPU/bộ nhớ và thực hiện thao tác mà quyền của JVM cho phép. Nếu cần cách ly bảo mật hoặc giới hạn tài nguyên mạnh, dùng tiến trình/container riêng và giao tiếp qua IPC.

## 12. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `FindException` khi tạo `ModuleFinder` hoặc resolve. | Module path không hợp lệ, JAR lỗi, module name trùng hoặc nguồn module không đọc được. | Kiểm tra module finder và `jar --describe-module`; xác minh module name duy nhất. |
| `ResolutionException`. | Không tìm thấy dependency, có split package hoặc module graph không nhất quán. | Kiểm tra `requires`, module path và các package thuộc nhiều module. |
| `LayerInstantiationException`. | Configuration không tương thích với parent layers hoặc không thể tạo class loader/module layer. | Resolve từ configuration của đúng parent layer và kiểm tra danh sách parent. |
| `IllegalArgumentException` từ `findLoader`. | Tên module không thuộc layer hoặc các parent của layer. | Kiểm tra tên module và layer đã được tạo thành công. |
| `ClassNotFoundException`. | Class name sai, module không thuộc configuration hoặc dùng nhầm loader. | Kiểm tra package/class name, module name và `child.findLoader(...)`. |
| `IllegalAccessException`. | Package chưa export cho caller hoặc class/member không public theo cách truy cập. | Export đúng package hoặc dùng service API công khai. |
| Không tìm thấy service provider trong child layer. | Provider không được resolve/bind hoặc dùng loader mặc định thay cho layer chứa provider. | Dùng `resolveAndBind()` khi cần service binding và `ServiceLoader.load(child, serviceType)`. |
| Không unload được plugin. | Vẫn còn thread, callback, static reference hoặc context class loader giữ class loader. | Thiết kế quy trình dừng plugin và giải phóng tham chiếu. |

## 13. Checklist triển khai

- Xác định module nào phải có trong boot layer và module nào nên nạp động.
- Đặt plugin JAR hoặc exploded module vào nguồn mà `ModuleFinder` có thể tìm thấy.
- Dùng configuration của parent layer thích hợp để resolve roots và dependency.
- Chọn `resolveAndBind()` nếu plugin được phát hiện qua `uses`/`provides`.
- Chọn một loader chung, nhiều loader hoặc loader tùy chỉnh theo yêu cầu namespace.
- Tạo layer với đúng parent layers và lưu `Controller` nếu cần thao tác runtime access.
- Dùng `child.findLoader()` hoặc `ServiceLoader.load(child, serviceType)` để truy cập plugin.
- Giữ service API và kiểu dùng chung trong parent layer để tránh class identity mismatch.
- Có quy trình dừng plugin, giải phóng thread/resource/reference nếu cần unload.
- Không coi module layer hoặc class loader là sandbox bảo mật.

## Tài liệu tham khảo

- [Java API — `ModuleLayer` (Java SE 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ModuleLayer.html)
- [Java API — `Configuration` (Java SE 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/Configuration.html)
- [Java API — `ModuleFinder` (Java SE 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/ModuleFinder.html)
- [Java API — `ServiceLoader` (Java SE 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/ServiceLoader.html)
- [Java Language Specification — Module Resolution (Java SE 24)](https://docs.oracle.com/en/java/javase/24/docs/specs/jls/jls-7.html)

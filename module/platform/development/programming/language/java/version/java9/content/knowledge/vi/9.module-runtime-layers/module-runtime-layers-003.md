# Tìm mô-đun bằng `ModuleFinder`

## Mục tiêu

Java Platform Module System (JPMS) cung cấp API `java.lang.module.ModuleFinder` để tìm và khám phá các mô-đun từ những vị trí đã biết. API này hữu ích khi ứng dụng cần kiểm tra thư viện modular, xây dựng danh sách plugin, xem metadata của mô-đun hoặc chuẩn bị một cấu hình mô-đun động.

`ModuleFinder` giúp trả lời câu hỏi **mô-đun nào có thể được tìm thấy ở những vị trí này?** Nó cung cấp tham chiếu và descriptor của mô-đun. Việc tìm thấy một mô-đun chưa đồng nghĩa với việc JVM đã phân giải toàn bộ dependency, tạo class loader hoặc nạp lớp của mô-đun đó.

## 1. `ModuleFinder` là gì?

`ModuleFinder` là interface trong package `java.lang.module`, được giới thiệu cùng JPMS từ Java 9 và vẫn là API công khai được hỗ trợ trong các JDK hiện đại. Nó cung cấp hai thao tác chính:

- `find(String name)`: tìm mô-đun theo tên và trả về `Optional<ModuleReference>`. Nếu không tìm thấy mô-đun có tên đó, kết quả là `Optional.empty()`.
- `findAll()`: trả về tập hợp `ModuleReference` của tất cả mô-đun mà finder tìm thấy. Tập hợp không đảm bảo thứ tự; nếu cần kết quả ổn định để hiển thị hoặc kiểm thử, hãy sắp xếp theo tên mô-đun.

Các factory method thường dùng:

| Method | Phạm vi tìm kiếm |
|---|---|
| `ModuleFinder.of(Path... entries)` | Các vị trí trên module path do ứng dụng chỉ định: thư mục chứa mô-đun, exploded module hoặc modular JAR |
| `ModuleFinder.ofSystem()` | Các mô-đun hệ thống có trong runtime image của JDK hiện tại |
| `ModuleFinder.compose(ModuleFinder... finders)` | Kết hợp nhiều finder thành một finder để tìm kiếm từ nhiều nguồn |

Ví dụ:

```java
ModuleFinder pluginFinder = ModuleFinder.of(Path.of("plugins"));
ModuleFinder systemFinder = ModuleFinder.ofSystem();

boolean pluginExists = pluginFinder.find("com.example.plugin").isPresent();
boolean sqlExists = systemFinder.find("java.sql").isPresent();
```

Trong ví dụ, `plugins` là thư mục chứa các mô-đun có thể khám phá, còn `java.sql` được tìm trong các mô-đun của JDK đang chạy.

## 2. Các kiểu mô-đun mà finder có thể tìm

`ModuleFinder.of(...)` tìm các mô-đun trên những đường dẫn được truyền vào. Các mục có thể là:

- **Exploded module:** thư mục đã biên dịch có `module-info.class` ở gốc và các package chứa `.class`.
- **Modular JAR:** JAR có `module-info.class`, thường được tạo từ một dự án đã khai báo module descriptor.
- **Automatic module:** JAR chưa có module descriptor nhưng được đặt trên module path. Tên mô-đun được lấy từ thuộc tính `Automatic-Module-Name` trong manifest nếu có; nếu không, tên được suy ra từ tên JAR theo quy tắc của JPMS.

Một JAR nằm trên class path thuộc unnamed module của class loader. `ModuleFinder.of(...)` không biến một JAR chỉ nằm trên class path thành named module. Muốn khám phá JAR như một mô-đun, hãy đưa chính đường dẫn JAR hoặc thư mục module path chứa nó vào finder.

Ví dụ truyền một thư mục chứa nhiều modular JAR:

```java
ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));
```

Ví dụ truyền nhiều vị trí:

```java
ModuleFinder finder = ModuleFinder.of(
        Path.of("plugins"),
        Path.of("vendor-modules"));
```

## 3. `ModuleReference` và `ModuleDescriptor`

Khi `find` tìm được mô-đun, kết quả là một `ModuleReference`. Đối tượng này đại diện cho mô-đun có thể được tìm thấy và cung cấp metadata cần thiết để tiếp tục xử lý.

Những API quan trọng:

- `ModuleReference.descriptor()`: lấy `ModuleDescriptor` mô tả mô-đun.
- `ModuleReference.location()`: trả về `Optional<URI>` cho vị trí mô-đun nếu vị trí đó có thể được cung cấp. Không nên giả định mọi mô-đun đều có URI.
- `ModuleReference.open()`: mở `ModuleReader` để đọc tài nguyên trong mô-đun; reader cần được đóng sau khi sử dụng.

`ModuleDescriptor` cho phép kiểm tra:

- `name()`: tên mô-đun.
- `rawVersion()` hoặc `version()`: phiên bản nếu descriptor khai báo.
- `requires()`: các mô-đun được yêu cầu.
- `exports()`: các package được xuất.
- `opens()`: các package được mở cho reflection.
- `uses()` và `provides()`: các service mà mô-đun sử dụng hoặc cung cấp.
- `packages()`: tập package trong descriptor.
- `mainClass()`: lớp main nếu descriptor khai báo.

Đọc descriptor không cần nạp các lớp của mô-đun. Đây là cách nhẹ để kiểm tra cấu trúc dependency và API mà thư viện công bố trước khi quyết định có sử dụng mô-đun hay không.

## 4. Ví dụ đầy đủ: tìm và đọc descriptor của một modular JAR

Ví dụ tạo một mô-đun plugin tên `com.example.plugin`, đóng gói thành JAR trong thư mục `mods`, rồi dùng một ứng dụng riêng gọi `ModuleFinder` để tìm mô-đun và đọc descriptor.

Cấu trúc dự án:

```text
project/
├── plugin-src/
│   └── com.example.plugin/
│       ├── module-info.java
│       └── com/example/plugin/api/PluginApi.java
├── plugin-out/
├── mods/
│   └── com.example.plugin.jar
├── finder-src/
│   └── com.example.finder/
│       ├── module-info.java
│       └── com/example/finder/Main.java
└── finder-out/
```

### Mô-đun cần tìm

**`plugin-src/com.example.plugin/module-info.java`**

```java
module com.example.plugin {
    requires java.logging;
    exports com.example.plugin.api;
}
```

**`plugin-src/com.example.plugin/com/example/plugin/api/PluginApi.java`**

```java
package com.example.plugin.api;

import java.util.logging.Logger;

public final class PluginApi {
    private static final Logger LOG = Logger.getLogger(PluginApi.class.getName());

    private PluginApi() {}

    public static String name() {
        LOG.fine("Plugin API was called");
        return "sample-plugin";
    }
}
```

### Ứng dụng dùng ModuleFinder

**`finder-src/com.example.finder/module-info.java`**

```java
module com.example.finder {
}
```

**`finder-src/com.example.finder/com/example/finder/Main.java`**

```java
package com.example.finder;

import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Optional;

public class Main {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println("Usage: Main <module-path> <module-name>");
            return;
        }

        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        String target = args[1];

        var moduleNames = finder.findAll().stream()
                .map(reference -> reference.descriptor().name())
                .sorted()
                .toList();
        System.out.println("found=" + moduleNames);
        System.out.println("system-java.sql="
                + ModuleFinder.ofSystem().find("java.sql").isPresent());

        Optional<ModuleReference> found = finder.find(target);
        if (found.isEmpty()) {
            System.out.println("not-found=" + target);
            return;
        }

        ModuleReference reference = found.get();
        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("name=" + descriptor.name());
        System.out.println("requires=" + descriptor.requires().stream()
                .map(ModuleDescriptor.Requires::name)
                .sorted()
                .toList());
        System.out.println("exports=" + descriptor.exports().stream()
                .map(ModuleDescriptor.Exports::source)
                .sorted()
                .toList());
        System.out.println("locationPresent=" + reference.location().isPresent());
    }
}
```

### Biên dịch và đóng gói

Chạy từ thư mục `project` trong Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force plugin-out, mods, finder-out
javac --module-source-path plugin-src -d plugin-out -m com.example.plugin
jar --create --file mods/com.example.plugin.jar -C plugin-out/com.example.plugin .
javac --module-source-path finder-src -d finder-out -m com.example.finder
```

Trên Linux hoặc macOS, tạo các thư mục bằng `mkdir -p plugin-out mods finder-out`; các lệnh `javac` và `jar` giữ nguyên.

### Tìm mô-đun và đọc descriptor

```powershell
java --module-path finder-out -m com.example.finder/com.example.finder.Main mods com.example.plugin
```

Stdout:

```text
found=[com.example.plugin]
system-java.sql=true
name=com.example.plugin
requires=[java.base, java.logging]
exports=[com.example.plugin.api]
locationPresent=true
```

Kết quả cho thấy finder tìm thấy JAR trong `mods`, đọc được tên, dependency và package được export. `java.base` xuất hiện trong `requires` vì mọi mô-đun thông thường đều đọc mô-đun nền tảng này theo quy tắc của Java.

Thử tìm tên không tồn tại:

```powershell
java --module-path finder-out -m com.example.finder/com.example.finder.Main mods com.example.missing
```

Stdout:

```text
found=[com.example.plugin]
system-java.sql=true
not-found=com.example.missing
```

`find` trả về `Optional.empty()` khi không tìm thấy tên mô-đun. Ứng dụng có thể xử lý tình huống này rõ ràng thay vì cố lấy một `ModuleReference` không tồn tại.

## 5. Tìm kiếm mô-đun hệ thống của JDK

`ModuleFinder.ofSystem()` tạo finder cho các mô-đun có trong runtime image của JDK. Có thể dùng nó để kiểm tra một API chuẩn có thuộc mô-đun nào và mô-đun đó có sẵn trong JDK hiện tại hay không.

```java
ModuleFinder systemFinder = ModuleFinder.ofSystem();

systemFinder.find("java.sql").ifPresent(reference -> {
    System.out.println(reference.descriptor().name());
});
```

Stdout trên JDK có mô-đun `java.sql`:

```text
java.sql
```

Không nên hard-code giả định mọi JDK đều chứa mọi mô-đun ngoài nền tảng. Nếu ứng dụng phụ thuộc vào một mô-đun tùy chọn của runtime image, hãy kiểm tra bằng `ofSystem().find(name)` và xử lý trường hợp không có.

## 6. Từ tìm mô-đun đến phân giải cấu hình

`ModuleFinder` chỉ tìm và trả tham chiếu mô-đun. Nó không tự kiểm tra toàn bộ đồ thị dependency và không tự tạo module layer.

Khi cần xác minh mô-đun gốc cùng các dependency bắt buộc có thể được phân giải, dùng `Configuration.resolve(...)`. Ví dụ:

```java
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

var configuration = ModuleLayer.boot().configuration()
        .resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.example.plugin"));

System.out.println(
        "resolved=" + configuration.findModule("com.example.plugin").isPresent());
```

Ở đây:

- `ModuleLayer.boot().configuration()` là cấu hình của boot layer hiện tại, đóng vai trò cấu hình cha.
- `finder` cung cấp các mô-đun mới cần phân giải.
- `ModuleFinder.of()` là finder rỗng cho vị trí tìm kiếm bổ sung.
- `Set.of("com.example.plugin")` chỉ định mô-đun gốc cần phân giải.

Nếu một dependency bắt buộc không tìm thấy hoặc đồ thị module không hợp lệ, quá trình resolve có thể ném `FindException` hoặc `ResolutionException`. Khi đó cần bổ sung đúng mô-đun hoặc sửa descriptor trước khi tiếp tục.

Phân biệt ba bước:

1. **Find:** khám phá module reference bằng `ModuleFinder`.
2. **Resolve:** kiểm tra và tạo `Configuration` hợp lệ cho module gốc cùng dependency.
3. **Define/load:** tạo `ModuleLayer` và dùng class loader của layer để nạp lớp.

## 7. Nạp plugin vào ModuleLayer động

Với kiến trúc plugin, sau khi tìm và resolve mô-đun, ứng dụng có thể tạo layer riêng. Layer giúp nhóm các module và class loader của chúng trong một cấu hình runtime độc lập với boot layer.

Ví dụ dưới đây dùng lại plugin `com.example.plugin` đã đóng gói trong thư mục `mods`. Ứng dụng tạo cấu hình, định nghĩa layer bằng một class loader chung cho các module trong layer, sau đó nạp lớp API đã export:

```java
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

var configuration = ModuleLayer.boot().configuration()
        .resolve(finder, ModuleFinder.of(), Set.of("com.example.plugin"));

ModuleLayer.Controller controller = ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader());

ModuleLayer pluginLayer = controller.layer();
Class<?> api = pluginLayer.findLoader("com.example.plugin")
        .loadClass("com.example.plugin.api.PluginApi");

Object pluginName = api.getMethod("name").invoke(null);
System.out.println("loaded=" + pluginName);
System.out.println("layerContains="
        + pluginLayer.findModule("com.example.plugin").isPresent());
```

Stdout:

```text
loaded=sample-plugin
layerContains=true
```

Ví dụ dùng reflection để minh họa việc nạp lớp. Package API được export trong `module-info.java`, vì vậy lớp công khai có thể được truy cập từ module gọi. Trong ứng dụng thực tế, nên thiết kế một interface plugin ổn định và cân nhắc `ServiceLoader` với các chỉ thị `uses`/`provides` thay vì phụ thuộc vào tên lớp được viết cứng.

`ModuleLayer.defineModulesWithOneLoader` dùng chung một class loader cho các module của layer. Với hệ thống plugin có yêu cầu cô lập class loader riêng cho từng module, có thể cân nhắc `defineModulesWithManyLoaders`. Cả hai lựa chọn đều tạo layer; chúng không phải sandbox bảo mật hay ranh giới tiến trình.

## 8. Xử lý lỗi và các trường hợp cần chú ý

- **Không tìm thấy tên:** `find(name)` trả `Optional.empty()`. Kiểm tra tên trong descriptor hoặc tên automatic module.
- **Không có mô-đun trên đường dẫn:** kiểm tra đường dẫn có tồn tại, có đúng thư mục/JAR và có chứa mô-đun hợp lệ hay không.
- **Descriptor không hợp lệ hoặc mô-đun trùng tên:** thao tác tìm có thể ném `FindException`. Không nên coi mọi lỗi đều là `Optional.empty()`.
- **Tìm thấy nhưng resolve thất bại:** finder có thể đọc descriptor của mô-đun, nhưng dependency của mô-đun đó vẫn có thể thiếu. Hãy kiểm tra kết quả `Configuration.resolve` và thông báo lỗi.
- **Location không có giá trị:** `ModuleReference.location()` là `Optional<URI>`; dùng `orElse` hoặc kiểm tra `isPresent`, không gọi `get()` một cách mù quáng.
- **Không tìm thấy lớp sau khi tạo layer:** kiểm tra tên lớp, package, package export, module layer và class loader dùng để nạp.
- **JAR chỉ nằm trên class path:** JAR đó thuộc unnamed module; đưa JAR vào module path nếu muốn finder khám phá nó như automatic module hoặc explicit module.
- **Thứ tự kết quả không ổn định:** `findAll()` trả về `Set`; hãy sort theo `descriptor().name()` khi hiển thị hoặc so sánh.

## 9. Những gì ModuleFinder không làm

`ModuleFinder` không:

- nạp hoặc khởi tạo lớp của mô-đun;
- thực thi mã static initializer trong plugin;
- tự động resolve toàn bộ dependency;
- tự tạo `ModuleLayer` hoặc class loader;
- kiểm tra plugin có an toàn để chạy hay không;
- biến JAR trên class path thành named module.

Vì vậy, không nên xem việc `find` thành công là bằng chứng plugin có thể chạy. Cần resolve cấu hình, tạo layer nếu kiến trúc yêu cầu, kiểm tra API và xử lý lỗi khi nạp lớp. Nếu plugin đến từ nguồn không tin cậy, việc dùng module layer không thay thế sandbox ở cấp tiến trình/hệ điều hành.

## 10. Checklist khi xây dựng bộ khám phá plugin

- [ ] Đường dẫn plugin được xác định rõ và chỉ trỏ đến thư mục/JAR dự kiến.
- [ ] Dùng `ModuleFinder.of(...)` để tìm module từ đường dẫn đó.
- [ ] Dùng `findAll()` để liệt kê và sort tên module khi hiển thị.
- [ ] Dùng `find(name)` để kiểm tra một plugin cụ thể và xử lý `Optional.empty()`.
- [ ] Đọc `ModuleDescriptor` để xác minh tên, requires, exports, uses/provides và metadata cần thiết.
- [ ] Xử lý `FindException` cho JAR hỏng, descriptor không hợp lệ hoặc tên module xung đột.
- [ ] Resolve cấu hình bằng `Configuration.resolve(...)` trước khi tạo layer.
- [ ] Chọn `defineModulesWithOneLoader` hoặc `defineModulesWithManyLoaders` theo mô hình class loader.
- [ ] Chỉ nạp lớp/API sau khi đã kiểm tra module và package cần thiết.
- [ ] Không coi module layer là ranh giới bảo mật cho mã plugin không tin cậy.

## Tài liệu tham khảo

1. [Java SE 25 API — ModuleFinder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleFinder.html), các factory method `of`, `ofSystem`, `compose`, `find` và `findAll`.
2. [Java SE 25 API — ModuleReference](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleReference.html), descriptor, location và ModuleReader.
3. [Java SE 25 API — ModuleDescriptor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleDescriptor.html), metadata của module.
4. [Java SE 25 API — Configuration](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/Configuration.html), resolve đồ thị module.
5. [Java SE 25 API — ModuleLayer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html), định nghĩa layer và nạp module động.
6. [The jar Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html), tạo và kiểm tra modular JAR.
# Tra cứu module, loader và quan hệ layer cha

## 1. Bối cảnh: ModuleLayer trong hệ thống plugin

`ModuleLayer` là một tập module đã được resolve và định nghĩa tại runtime, kèm quan hệ với các layer cha. Boot layer được tạo khi JVM khởi động; một host có thể tạo layer khác để nạp plugin sau này. Mỗi layer có `Configuration` (đồ thị module đã resolve) và các module thực tế được định nghĩa với một hoặc nhiều class loader.

Cần phân biệt ba câu hỏi:

1. **Module nào có trong layer?** Dùng `layer.modules()` hoặc `layer.findModule(name)`.
2. **Class loader nào được dùng để nạp module?** Dùng `layer.findLoader(name)` khi module thuộc chính layer đó; dùng `Module.getClassLoader()` khi đã có đối tượng `Module`.
3. **Module được tìm ở layer hiện tại hay layer cha?** Dùng `layer.parents()` để duyệt cây/đồ thị quan hệ; `findModule` có thể tìm qua ancestors.

Layer không đồng nghĩa class loader. Có thể định nghĩa nhiều module trong một loader hoặc chia nhiều loader, tùy lựa chọn khi tạo layer. Named module có danh tính và readability riêng; một layer mới không mặc nhiên là sandbox bảo mật hoặc cơ chế hot-unload.

## 2. Các API tra cứu quan trọng

| API | Kết quả | Điều cần nhớ |
|---|---|---|
| `ModuleLayer.boot()` | Boot layer của JVM hiện tại | Không tự thay đổi khi nạp plugin về sau |
| `layer.modules()` | `Set<Module>` trực tiếp thuộc layer | Không trả toàn bộ module của ancestors |
| `layer.findModule("name")` | `Optional<Module>` | Tìm trong layer và các ancestor layers |
| `layer.findLoader("name")` | `ClassLoader` cho module được định nghĩa trong layer | Có thể ném `IllegalArgumentException` nếu module không được định nghĩa **trong layer này** |
| `layer.parents()` | `List<ModuleLayer>` cha trực tiếp | Một layer có thể có nhiều cha; không giả định duy nhất |
| `layer.configuration()` | `Configuration` đã resolve | Khác với việc nạp class hoặc tạo instance |
| `module.getLayer()` | Layer chứa named module (nếu có) | Với unnamed module, giá trị là `null` |
| `module.getClassLoader()` | Defining loader của module | Có thể là `null` với module do bootstrap loader định nghĩa |
| `Class.getModule()` | Module sở hữu class | Hữu ích khi debug lớp nào thực sự được nạp |

**Bẫy phổ biến:** `layer.findModule(name)` tìm cả layer cha; nhưng `layer.findLoader(name)` yêu cầu tên module thuộc **chính layer**. Vì vậy một module lấy được qua `findModule` chưa đủ để gọi `findLoader` trên layer đang xét. Hãy lấy đối tượng `Module`, kiểm tra `module.getLayer()` rồi gọi `module.getClassLoader()` nếu cần.

## 3. Ví dụ chạy được trên Java 17+: tra cứu boot layer

Tạo file `BootLayerInspect.java`:

```java
import java.lang.ModuleLayer;
import java.util.Comparator;

public final class BootLayerInspect {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();
        Module javaBase = boot.findModule("java.base").orElseThrow();

        System.out.println("java.base present: " + boot.modules().contains(javaBase));
        System.out.println("java.base layer is boot: " + (javaBase.getLayer() == boot));
        System.out.println("java.base loader is bootstrap: "
                + (javaBase.getClassLoader() == null));
        System.out.println("boot parent count: " + boot.parents().size());

        boot.modules().stream()
                .map(Module::getName)
                .filter(name -> name.startsWith("java."))
                .sorted(Comparator.naturalOrder())
                .limit(3)
                .forEach(name -> System.out.println("sample: " + name));
    }
}
```

Biên dịch và chạy:

```bash
javac BootLayerInspect.java
java BootLayerInspect
```

Đầu ra có những dòng ổn định:

```text
java.base present: true
java.base layer is boot: true
java.base loader is bootstrap: true
boot parent count: 1
```

Danh sách `sample:` phụ thuộc vào tập module được resolve bởi launcher và môi trường, nên không gắn cứng toàn bộ stdout. Boot layer có parent là `ModuleLayer.empty()`; đây là một layer rỗng đặc biệt. Không nên kết luận mọi module hệ thống đều nằm trong boot layer: chỉ module được resolve mới xuất hiện trong `modules()`.

## 4. Ví dụ đầy đủ: tạo plugin layer và lần theo layer cha

Ta tạo `demo.api` chứa interface, `demo.plugin` chứa provider và host tạo layer mới. Mục tiêu chính là quan sát quan hệ layer, module và class loader; không cần network hoặc framework.

Cây thư mục:

```text
layer-demo/
├── src-api/
│   ├── module-info.java
│   └── demo/api/Greeter.java
├── src-plugin/
│   ├── module-info.java
│   └── demo/plugin/HelloGreeter.java
└── Host.java
```

`src-api/module-info.java`:

```java
module demo.api {
    exports demo.api;
}
```

`src-api/demo/api/Greeter.java`:

```java
package demo.api;

public interface Greeter {
    String greet(String name);
}
```

`src-plugin/module-info.java`:

```java
module demo.plugin {
    requires demo.api;
    provides demo.api.Greeter with demo.plugin.HelloGreeter;
}
```

`src-plugin/demo/plugin/HelloGreeter.java`:

```java
package demo.plugin;

import demo.api.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {}
    @Override public String greet(String name) {
        return "Hello, " + name;
    }
}
```

`Host.java` (ứng dụng host chạy trên class path):

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) {
        ModuleLayer parent = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of("mods/plugin"));
        Configuration config = parent.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("demo.plugin"));

        ModuleLayer child = parent.defineModulesWithOneLoader(
                config, ClassLoader.getSystemClassLoader());

        Module plugin = child.findModule("demo.plugin").orElseThrow();
        Module api = child.findModule("demo.api").orElseThrow();

        System.out.println("child owns plugin: " + child.modules().contains(plugin));
        System.out.println("child owns api: " + child.modules().contains(api));
        System.out.println("plugin layer is child: " + (plugin.getLayer() == child));
        System.out.println("api layer is parent: " + (api.getLayer() == parent));
        System.out.println("child parent is boot: " + (child.parents().get(0) == parent));
        System.out.println("plugin loader matches: "
                + (child.findLoader("demo.plugin") == plugin.getClassLoader()));

        // API nằm ở boot layer; KHÔNG gọi child.findLoader("demo.api").
        ServiceLoader<demo.api.Greeter> services =
                ServiceLoader.load(child, demo.api.Greeter.class);
        for (demo.api.Greeter service : services) {
            System.out.println(service.greet("JPMS"));
        }
    }
}
```

**Điều kiện cấu hình:** Để `demo.api` có mặt trong boot layer khi chạy host class path, cần thêm module API vào module path và resolve nó qua `--add-modules demo.api`. Host là code thuộc unnamed module, và được phép dùng public API đã export từ `demo.api`. Plugin nằm trong một JAR riêng chưa nằm trên boot module path; `ModuleFinder` chỉ đọc JAR đó khi tạo child layer.

Biên dịch và đóng gói với JDK 17+ từ thư mục `layer-demo/` (lệnh shell POSIX):

```bash
mkdir -p build/api build/plugin mods/api mods/plugin
javac -encoding UTF-8 -d build/api \
  src-api/module-info.java src-api/demo/api/Greeter.java
jar --create --file mods/api/demo.api.jar -C build/api .
javac -encoding UTF-8 --module-path mods/api -d build/plugin \
  src-plugin/module-info.java src-plugin/demo/plugin/HelloGreeter.java
jar --create --file mods/plugin/demo.plugin.jar -C build/plugin .
javac --module-path mods/api --add-modules demo.api Host.java
java --module-path mods/api --add-modules demo.api -cp . Host
```

Đầu ra chính xác trong mô hình trên:

```text
child owns plugin: true
child owns api: false
plugin layer is child: true
api layer is parent: true
child parent is boot: true
plugin loader matches: true
Hello, JPMS
```

`child.findModule("demo.api")` tìm được module API từ layer cha dù `child.modules()` không chứa nó. Đây là điểm phân biệt quan trọng giữa **visible via ancestors** và **defined in this layer**.

Với thiết kế khác, ví dụ không resolve API ở parent, `resolve(...)` có thể đưa API vào configuration của child nếu finder có API module. Khi đó kết quả ownership khác. Luôn kiểm tra graph và lớp loader thực tế thay vì áp dụng một giả định cứng.

## 5. Quan hệ layer cha và đồ thị configuration

ModuleLayer tổ chức dưới dạng đồ thị có hướng không chu trình theo quan hệ parent. Các layer cha có thể chia sẻ module giữa các nhánh; một layer có thể có nhiều parent nếu được tạo bằng API tương ứng.

Phân biệt:

- `layer.parents()`: danh sách **cha trực tiếp** của runtime layer.
- `layer.configuration().parents()`: danh sách parent **configuration** dùng khi resolve, phản ánh graph cấu hình.
- `layer.modules()`: module được định nghĩa trực tiếp trong layer.
- `layer.findModule(name)`: có thể trả module trong layer hoặc ancestors, tùy tập module được xét.

Nếu chỉ cần module cụ thể, `findModule` là API trực tiếp. Nếu cần hiển thị toàn bộ cây, có thể duyệt `parents()` nhưng phải tránh lặp layer trong graph có nhiều đường dẫn tới cùng ancestor.

Đoạn tiện ích minh họa duyệt ancestors (đặt trong một class Java đã import `java.util.*`):

```java
static void printLayers(ModuleLayer root) {
    Set<ModuleLayer> seen = java.util.Collections.newSetFromMap(
            new java.util.IdentityHashMap<ModuleLayer, Boolean>());
    java.util.ArrayDeque<ModuleLayer> queue = new java.util.ArrayDeque<>();
    queue.add(root);
    while (!queue.isEmpty()) {
        ModuleLayer layer = queue.removeFirst();
        if (!seen.add(layer)) continue;
        System.out.println("modules=" + layer.modules().size());
        queue.addAll(layer.parents());
    }
}
```

Đây là **đoạn mã minh họa**, không phải chương trình độc lập. Sử dụng identity set để tránh duyệt lặp cùng một layer trong đồ thị.

## 6. Class loader và loại module

JPMS cho phép nhiều chiến lược định nghĩa module trong child layer:

| Cách tạo | Đặc điểm |
|---|---|
| `defineModulesWithOneLoader` | Module trong configuration child được định nghĩa bằng một loader do cơ chế tạo layer quản lý; phù hợp khi dependency của plugin có thể chia sẻ loader |
| `defineModulesWithManyLoaders` | Mỗi module trong configuration được nạp qua loader riêng do cơ chế tạo layer quản lý |
| `defineModules` | Cho phép ánh xạ module name tới loader theo chính sách tùy chỉnh |

`ClassLoader` truyền vào `defineModulesWithOneLoader` là **parent loader** của loader mới mà cơ chế tạo layer sử dụng; nó không đồng nghĩa loader mới chính là đối tượng được truyền. Vì vậy trong ví dụ kiểm tra `child.findLoader("demo.plugin") == plugin.getClassLoader()` và không so sánh với `ClassLoader.getSystemClassLoader()`.

Trong mô hình plugin, API contract nên được định nghĩa một lần trong parent layer/loader mà host và provider cùng nhìn thấy. Nếu cùng binary name của interface bị định nghĩa bởi nhiều loader, ép kiểu hoặc `ServiceLoader` có thể thất bại dù tên package/class giống nhau.

Không nên thiết kế giao tiếp host-plugin dựa vào package-private member giữa các loader khác nhau. Runtime package phụ thuộc tên package và defining loader; các module có tên còn chịu ràng buộc `exports`/`opens`.

## 7. Lỗi và giới hạn thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `findModule(...)` trả rỗng | Module không nằm trong layer hoặc ancestor được tìm | Xem root set, `ModuleFinder`, resolution và layer parents |
| `findLoader(...)` ném `IllegalArgumentException` | Module nằm ở layer cha hoặc không thuộc layer đang hỏi | Dùng `module.getLayer()` rồi tra loader tại layer sở hữu, hoặc `module.getClassLoader()` |
| Không tìm thấy provider | Provider module chưa resolve, thiếu `provides`, service API không thống nhất, sai layer | Kiểm tra descriptor, `ServiceLoader.load(layer, ...)` và graph |
| `LayerInstantiationException` | Cấu hình loader/package/module không hợp lệ khi định nghĩa layer | Kiểm tra split package, package mapping và cách tạo loader |
| `FindException` / `ResolutionException` | Module descriptor thiếu/sai dependency, trùng module hoặc graph không hợp lệ | Kiểm tra module path, tên module và `requires` |
| `ClassCastException` / `ServiceConfigurationError` | Host và plugin nhìn thấy các bản API khác nhau hoặc provider sai kiểu | Giữ API ở parent, tránh duplicate contract |

**Quan sát đúng:** `module.getClassLoader()` trả `null` là bình thường đối với module do bootstrap loader định nghĩa (ví dụ `java.base`), không tự chỉ ra lỗi. `module.getLayer()` trả `null` đối với class thuộc unnamed module. Tránh dùng tên hiển thị của loader làm danh tính tuyệt đối.

## 8. Checklist khi thêm một plugin mới

1. Xác định JAR nào là named module, automatic module hoặc class path artifact.
2. Kiểm tra `ModuleFinder.of(...)` nhìn thấy đúng module name và version metadata.
3. Resolve graph từ `parentLayer.configuration()` với root đúng; xác minh các dependency cần thiết tồn tại.
4. Tạo child layer với số loader phù hợp; ghi lại owner layer của từng module.
5. Tra module bằng `findModule`, chỉ dùng `findLoader` trên layer trực tiếp định nghĩa nó.
6. Dùng `ServiceLoader.load(layer, serviceApiClass)` và kiểm chứng provider assignable với API chung.
7. Có test cho thiếu provider, thiếu dependency, module trùng tên, split package và lỗi khi kích hoạt.
8. Quản lý close/dừng plugin, thread và resource riêng; tạo layer không tự unload hoặc sandbox mã.

**Ghi nhớ:** `findModule` trả lời *module ở đâu trong layer graph*; `findLoader` trả lời *loader của module trực tiếp thuộc layer này*; `parents()` cho biết đường đi tới các layer trước đó. Việc nhìn thấy module ở ancestor không có nghĩa nó thuộc layer hiện tại. Phân biệt chính xác ba điều này giúp host tránh nạp trùng API, chọn sai loader và mất provider trong hệ thống plugin.

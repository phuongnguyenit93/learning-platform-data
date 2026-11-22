# findLoader và chọn ClassLoader cho module

## 1. Bài toán: khi một ModuleLayer có nhiều module, lấy đúng loader thế nào?

Từ Java 9, Java Platform Module System (**JPMS**) không chỉ tổ chức class thành các package trên classpath, mà còn đưa ra **named module**, **module descriptor**, **Configuration** và **ModuleLayer**. Một ứng dụng có thể resolve plugin modules lúc runtime, tạo một module layer mới, rồi muốn nạp class thuộc module cụ thể.

Trong tình huống ấy, câu hỏi “lấy system ClassLoader rồi gọi `loadClass` là đủ chứ?” có thể sai. **Module và loader không có quan hệ 1:1 cố định.** Một layer có thể ánh xạ nhiều named modules vào cùng một loader hoặc cấp riêng loader cho mỗi module.

API chính:

~~~java
ClassLoader loader = layer.findLoader("demo.alpha");
~~~

**`ModuleLayer.findLoader(String moduleName)` trả ClassLoader mà named module được định nghĩa vào**. Nó có thể tìm module trong layer đang xét **hoặc các parent layers**. Nó **không** tải class theo tên và **không** tự tạo layer hay loader mới.

Các điểm quyết định:

- `layer.findLoader("demo.alpha")` chọn **loader theo tên module**, không phải theo tên class.
- Module được tìm trong layer đó hoặc các layer cha, theo quy tắc tìm kiếm của `findModule`.
- Nếu không có named module với tên yêu cầu trong layer/parents, phương thức ném **`IllegalArgumentException`**.
- Nếu module được định nghĩa bởi **bootstrap loader**, kết quả **`null` là hợp lệ** — không có nghĩa module bị thiếu.
- Một module có thể được định nghĩa vào loader chung với các module khác. Không suy ra “mỗi module luôn có loader riêng”.
- Việc có được `ClassLoader` không chứng minh một class cụ thể tồn tại, được exported, đã initialized hoặc caller có quyền truy cập tất cả member của class.

**Kết quả học tập:** hiểu `findLoader`, tạo layer bằng `defineModulesWithOneLoader`/`defineModulesWithManyLoaders`, so sánh `Class.getClassLoader`/`Module.getClassLoader`, xử lý module không tồn tại và bootstrap loader, phân biệt quan hệ parent layer với parent ClassLoader, và chọn loader đúng khi nạp class/plugin.

## 2. Nền tảng: Module, Configuration, ModuleLayer và ClassLoader

### 2.1. Named module là gì?

Một module có tên, ví dụ `demo.alpha`, thường khai báo trong `module-info.java`:

~~~java
module demo.alpha {
    exports demo.alpha;
}
~~~

Descriptor này xác định tên module và các quan hệ như `requires`, `exports`, `opens`, `uses` hoặc `provides`. Module được **resolve** trong một `Configuration` và **định nghĩa** thành runtime `Module` khi tạo `ModuleLayer`.

Đây là hai bước khác nhau:

~~~text
ModuleFinder (tìm module artifacts)
    |
    v
Configuration.resolve(...) (giải quyết module graph)
    |
    v
ModuleLayer.defineModules...(...) (tạo runtime Module objects
                                    và gán ClassLoader)
    |
    v
layer.findModule("demo.alpha") -> Module
layer.findLoader("demo.alpha") -> ClassLoader (có thể null)
    |
    v
Class.forName(module, binaryName) hoặc loader.loadClass(binaryName)
~~~

Không có quy tắc “JAR nằm trong `--module-path` thì mọi class tự được load”. Một module phải được resolve và nằm trong cấu hình runtime thích hợp. Tạo layer chỉ khai báo module/loader mapping; class còn được tải khi cần.

### 2.2. Layer lưu thông tin gì?

`ModuleLayer` đại diện cho các runtime named modules được tạo từ một configuration, cùng ánh xạ module → loader. Một layer có thể có một hay nhiều **parent layers**.

Các API hữu ích:

| API | Vai trò |
|---|---|
| `ModuleLayer.boot()` | Lấy boot layer khi JVM đã khởi động |
| `layer.configuration()` | Lấy `Configuration` tương ứng |
| `layer.modules()` | Tập modules **được định nghĩa trực tiếp trong layer này** |
| `layer.parents()` | Danh sách các parent layers theo thứ tự tìm kiếm |
| `layer.findModule(name)` | Tìm `Module` trong layer hoặc parent layers, trả `Optional<Module>` |
| `layer.findLoader(name)` | Tìm loader của named module trong layer/parents; trả `ClassLoader` hoặc `null` cho bootstrap |
| `module.getLayer()` | Layer của runtime module, nếu có |
| `module.getClassLoader()` | Defining ClassLoader của module, có thể `null` cho bootstrap |
| `SomeType.class.getModule()` | Runtime module chứa class đó |
| `SomeType.class.getClassLoader()` | Defining loader của chính runtime class |

**Quan trọng:** `layer.modules()` chỉ liệt kê modules **trực tiếp** trong layer; `findModule` và `findLoader` có thể tìm thấy module **thuộc layer cha**. Đừng dùng `layer.modules().contains(...)` như điều kiện duy nhất để cho phép gọi `findLoader`.

### 2.3. ModuleLoader mapping không phải module readability

Một module A `requires` module B nghĩa là graph của JPMS có readability edge phù hợp. Còn việc A và B có cùng ClassLoader hay không là lựa chọn ánh xạ khi tạo layer.

Các điều kiện độc lập:

- **Module resolution/readability:** module nào đọc module nào theo `requires` và các thay đổi hợp lệ.
- **Exports:** package công khai của module nào được truy cập bởi module khác.
- **Opens:** điều kiện mở package cho deep reflection.
- **ClassLoader mapping:** loader nào định nghĩa các class thuộc module nào.
- **Java visibility:** `public`, `protected`, package-private và `private` vẫn có hiệu lực.

Không thay thế `requires`, `exports` hay `opens` bằng việc chỉ đổi loader. Ngược lại, mở module không tự đổi defining loader.

## 3. Hợp đồng chính xác của `ModuleLayer.findLoader(String)`

Chữ ký:

~~~java
public ClassLoader findLoader(String name)
~~~

Theo [Java SE 21 ModuleLayer API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html#findLoader(java.lang.String)):

1. Tìm named module có tên `name` **trong layer hiện tại**.
2. Nếu không có ở layer hiện tại, tiếp tục tìm trong **parent layers** theo cách `findModule` tìm kiếm (theo thứ tự parent, với các parent của chúng).
3. Trả loader mà module tìm được được định nghĩa vào.
4. Nếu không có module cùng tên trong layer **và mọi parent layers**, ném `IllegalArgumentException`.
5. Với module do **bootstrap ClassLoader** định nghĩa, trả `null`. Chính vì vậy return type không phải `Optional<ClassLoader>`.
6. Theo quy tắc chung của `ModuleLayer`, `name == null` gây `NullPointerException`. Trên môi trường có SecurityManager cũ, kiểm tra quyền `RuntimePermission("getClassLoader")` có thể gây `SecurityException`.

### 3.1. Phân biệt ba trường hợp trả kết quả

~~~java
ModuleLayer boot = ModuleLayer.boot();

ClassLoader baseLoader = boot.findLoader("java.base");
// baseLoader == null: java.base được bootstrap định nghĩa, không bị thiếu.

ClassLoader appLoader = boot.findLoader("java.sql");
// Trong cấu hình boot layer có java.sql, có thể nhận một loader built-in.
// Không nên hardcode mọi module đều cùng loader.
~~~

Các dòng trên là **snippet minh họa**, không độc lập; module `java.sql` phải hiện diện trong boot layer hiện tại mới gọi được `findLoader("java.sql")`. `java.base` là module nền bắt buộc của boot layer.

Nếu module không tồn tại:

~~~java
try {
    boot.findLoader("module.that.does.not.exist");
} catch (IllegalArgumentException ex) {
    System.out.println("No such module in the layer hierarchy");
}
~~~

Đây không phải `ClassNotFoundException` vì chúng ta đang **tìm module**, chưa gọi `loadClass`.

### 3.2. Tìm module ở parent layer vẫn hợp lệ

~~~java
ModuleLayer child = /* một layer được tạo với boot làm parent */;
ClassLoader bootstrap = child.findLoader("java.base");
~~~

Đoạn code trên là snippet minh họa; biến `child` cần được tạo trước. Lúc đó, `java.base` được tìm ở **boot parent layer**, và loader là `null`.

Suy luận “`child.modules()` không chứa `java.base` nên `child.findLoader("java.base")` phải ném exception” là **sai**. API được thiết kế để tìm tiếp parent layer.

### 3.3. `null` có nghĩa bootstrap, không phải “module missing”

Hai đường không tìm thấy cần tách biệt:

~~~text
layer.findModule("no.such.module")
    -> Optional.empty()

layer.findLoader("no.such.module")
    -> IllegalArgumentException

layer.findLoader("java.base")
    -> null (bootstrap loader; module hợp lệ)
~~~

Nếu ứng dụng cần biểu diễn kết quả tùy chọn, hãy **kiểm tra module trước**:

~~~java
String name = "java.base";
Module found = layer.findModule(name).orElse(null);
if (found == null) {
    System.out.println("Module not found");
} else {
    ClassLoader loader = layer.findLoader(name);
    System.out.println(loader == null ? "bootstrap" : "non-bootstrap");
}
~~~

Mẫu này tránh đánh đồng loader bootstrap với module vắng mặt.

## 4. Ai quyết định module được gán cho loader nào?

**Mapping module → loader được quyết định khi tạo layer**, không phải khi gọi `findLoader`. Các lựa chọn phổ biến:

| Cách tạo layer | Mapping | Khi dùng |
| --- | --- | --- |
| `parent.defineModulesWithOneLoader(cf, parentLoader)` | Một loader **mới** cho tất cả modules trong `cf` | Module packages không overlap và cần loader chung |
| `parent.defineModulesWithManyLoaders(cf, parentLoader)` | Mỗi module trong `cf` dùng một loader **mới** riêng | Cần phân biệt loader/module rõ ràng |
| `parent.defineModules(cf, mapping)` | Application chọn mapping `moduleName -> ClassLoader` | Có custom loader đủ hiểu JPMS/module ownership |

`parentLoader` là parent **class loader** cho loader mới; nó không thay thế parent `ModuleLayer`. `WithOneLoader` và `WithManyLoaders` phải tuân thủ module graph và ràng buộc package. Nếu nhiều modules cùng tên package được gán chung loader, bước định nghĩa layer có thể ném `LayerInstantiationException`. Một loader cũng có thể delegate trực tiếp theo package/module khác với chuỗi parent-first đơn giản.

Trong cùng một layer được tạo bằng `WithOneLoader`:

~~~java
ClassLoader alpha = layer.findLoader("demo.alpha");
ClassLoader beta = layer.findLoader("demo.beta");
System.out.println(alpha == beta);  // true
~~~

Nếu layer được tạo bằng `WithManyLoaders` với hai modules ấy, phép so sánh trên là `false`. Đây là **snippet minh họa** yêu cầu `layer` thực sự chứa hai named modules; lớp có tên `demo.alpha` và `demo.beta` phải thuộc configuration đã resolve.

Bản **instance** trả trực tiếp `ModuleLayer`; các static overload `ModuleLayer.defineModulesWithOneLoader(cf, parents, parentLoader)` hoặc `defineModulesWithManyLoaders` trả `ModuleLayer.Controller`, lấy layer qua `controller.layer()`. Dùng static khi cần nhiều parent layers hoặc muốn điều chỉnh read/export/open edges qua Controller. Bài riêng về hai phương thức `defineModulesWithOneLoader/ManyLoaders` giải thích cụ thể lệnh build, direct delegation và lựa chọn chiến lược; phần này giữ trọng tâm ở cách `findLoader` đọc mapping đã tồn tại.

## 5. Parent layer khác parent ClassLoader thế nào?

Đây là một trong những nhầm lẫn phổ biến nhất khi thiết kế plugin:

~~~text
           JPMS ModuleLayer hierarchy
       ModuleLayer.boot()
             |
             v
       Child ModuleLayer
          |        |
          v        v
       Module A   Module B

           ClassLoader relationships
       System ClassLoader (parentLoader argument)
          |             |
          v             v
       Module loader A  Module loader B
       (nếu dùng WithManyLoaders)
~~~

Hai kiểu quan hệ được khai báo ở **hai chỗ khác nhau**:

- **Parent `ModuleLayer`**: mô tả nơi có thể tìm parent modules và module resolution graph.
- **Parent `ClassLoader`**: tham số `parentLoader` điều khiển quan hệ loader được tạo với loader cha về mặt API; nhưng loaders tạo bởi phương thức layer có thể triển khai **direct delegation theo module/package** phù hợp JPMS.

**Không đồng nhất:** “`ModuleLayer.boot()` là cha” không có nghĩa mỗi class loader của child layer đều dùng một parent tương ứng duy nhất với toàn bộ boot layer; boot layer có thể dùng bootstrap, platform hoặc application loaders.

Chỉ định `ClassLoader.getSystemClassLoader()` làm `parentLoader` **không** đưa modules mới vào system/application loader. `WithOneLoader`/**`WithManyLoaders` tạo loader mới** và cấu hình chúng với parent loader được truyền.

Nếu Java API trả `null` cho `java.base`, đó là bootstrap loader, **không phải một đối tượng null cần sửa bằng `new URLClassLoader`**. Bootstrap được JVM triển khai đặc biệt.

## 6. Ví dụ Java 17+ chạy độc lập: `findLoader` với một và nhiều loader

Thực hành tạo hai named modules `demo.alpha`, `demo.beta`, resolve chúng từ thư mục `mods` và tạo **hai child layers độc lập** trên cùng boot layer:

- Layer `single` với **một loader cho cả hai modules**.
- Layer `many` với **hai loaders riêng**.
- So sánh module loader, ClassLoader của class thật và module identity.
- Tìm `java.base` từ child layer để chứng minh **parent search + bootstrap null**.
- Gọi `findLoader` với tên module vắng mặt để chứng minh `IllegalArgumentException`.
- Chứng minh hai runtime `Module` objects mang cùng tên ở **hai sibling layers** không phải cùng một đối tượng.

### 6.1. Cấu trúc thư mục

~~~text
demo/
├── src/
│   ├── demo.alpha/
│   │   ├── module-info.java
│   │   └── demo/alpha/Alpha.java
│   ├── demo.beta/
│   │   ├── module-info.java
│   │   └── demo/beta/Beta.java
│   └── app/
│       └── LayerDemo.java
├── mods/
│   ├── demo.alpha/         # exploded named module
│   └── demo.beta/
└── out/
    └── app/                # Launcher ở unnamed module
~~~

Chương trình launcher `LayerDemo` nằm trên classpath và không import `Alpha`/`Beta`. Nó chỉ biết tên module/class tại runtime, giúp tách biệt compile classpath của launcher với module resolution.

### 6.2. Tệp `src/demo.alpha/module-info.java`

~~~java
module demo.alpha {
    exports demo.alpha;
}
~~~

### 6.3. Tệp `src/demo.alpha/demo/alpha/Alpha.java`

~~~java
package demo.alpha;

public class Alpha {
    public static String id() {
        return "alpha";
    }
}
~~~

### 6.4. Tệp `src/demo.beta/module-info.java`

~~~java
module demo.beta {
    exports demo.beta;
}
~~~

### 6.5. Tệp `src/demo.beta/demo/beta/Beta.java`

~~~java
package demo.beta;

public class Beta {
    public static String id() {
        return "beta";
    }
}
~~~

`Beta` được biên dịch thành module hợp lệ để kiểm tra nhiều module/loader; launcher không cần trực tiếp gọi method `Beta.id()`.

### 6.6. Tệp `src/app/LayerDemo.java`

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        Configuration config = boot.configuration().resolve(
                finder, ModuleFinder.of(),
                Set.of("demo.alpha", "demo.beta"));

        ClassLoader parentLoader =
                ClassLoader.getSystemClassLoader();

        ModuleLayer single =
                boot.defineModulesWithOneLoader(config, parentLoader);
        System.out.println("singleSharedLoader="
                + (single.findLoader("demo.alpha")
                        == single.findLoader("demo.beta")));

        ModuleLayer many =
                boot.defineModulesWithManyLoaders(config, parentLoader);
        ClassLoader aMany = many.findLoader("demo.alpha");
        ClassLoader bMany = many.findLoader("demo.beta");
        System.out.println("manyDistinctLoaders="
                + (aMany != bMany));

        Module alphaModule =
                many.findModule("demo.alpha").orElseThrow();
        Class<?> alpha =
                Class.forName(alphaModule, "demo.alpha.Alpha");
        System.out.println("classFromSelectedLoader="
                + (alpha != null
                        && alpha.getClassLoader() == aMany));

        System.out.println("correctModuleIdentity="
                + (alpha.getModule() == alphaModule));
        System.out.println("parentModuleVisible="
                + many.findModule("java.base").isPresent());
        System.out.println("parentLoaderLookupWorks="
                + (many.findLoader("java.base")
                        == boot.findLoader("java.base")));
        System.out.println("bootBaseUsesBootstrap="
                + (boot.findLoader("java.base") == null));

        try {
            many.findLoader("module.that.does.not.exist");
            System.out.println("missingModuleRejected=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("missingModuleRejected=true");
        }

        System.out.println("sameModuleDifferentLayers="
                + (single.findModule("demo.alpha").orElseThrow()
                        != alphaModule));
    }
}
~~~

### 6.7. Lệnh biên dịch và chạy

Trên Linux/macOS, đứng trong thư mục `demo`:

~~~sh
mkdir -p mods/demo.alpha mods/demo.beta out/app

javac --release 17 -d mods/demo.alpha \
    src/demo.alpha/module-info.java \
    src/demo.alpha/demo/alpha/Alpha.java

javac --release 17 -d mods/demo.beta \
    src/demo.beta/module-info.java \
    src/demo.beta/demo/beta/Beta.java

javac --release 17 -d out/app src/app/LayerDemo.java
java -cp out/app LayerDemo
~~~

Dấu `\` cuối dòng là nối lệnh shell POSIX. Nếu dùng Windows PowerShell, viết mỗi lệnh `javac` một dòng:

~~~powershell
New-Item -ItemType Directory -Force mods/demo.alpha, mods/demo.beta, out/app | Out-Null
javac --release 17 -d mods/demo.alpha src/demo.alpha/module-info.java src/demo.alpha/demo/alpha/Alpha.java
javac --release 17 -d mods/demo.beta src/demo.beta/module-info.java src/demo.beta/demo/beta/Beta.java
javac --release 17 -d out/app src/app/LayerDemo.java
java -cp out/app LayerDemo
~~~

**Chú ý:** không thêm `mods` vào `-cp`. `ModuleFinder.of(Path.of("mods"))` đọc các module artifacts để tạo configuration riêng; lớp `Alpha`/`Beta` không cần xuất hiện trên system classpath.

**Stdout chính xác**, đã biên dịch bằng `javac --release 17` và chạy bằng JDK:

~~~text
singleSharedLoader=true
manyDistinctLoaders=true
classFromSelectedLoader=true
correctModuleIdentity=true
parentModuleVisible=true
parentLoaderLookupWorks=true
bootBaseUsesBootstrap=true
missingModuleRejected=true
sameModuleDifferentLayers=true
~~~

### 6.8. Phân tích chín kết quả

| Dòng | Ý nghĩa |
|---|---|
| `singleSharedLoader=true` | `defineModulesWithOneLoader` ánh xạ hai modules mới tới cùng một loader |
| `manyDistinctLoaders=true` | `defineModulesWithManyLoaders` tạo loader riêng cho từng module |
| `classFromSelectedLoader=true` | `Class.forName(Module,String)` trả class có defining loader đúng như `findLoader("demo.alpha")` |
| `correctModuleIdentity=true` | Class `Alpha` thật sự thuộc runtime `Module` mà `many.findModule` trả về |
| `parentModuleVisible=true` | Child layer tìm thấy `java.base` trong boot parent layer |
| `parentLoaderLookupWorks=true` | `findLoader` của child **đã tra parent layers**; kết quả khớp `boot.findLoader` |
| `bootBaseUsesBootstrap=true` | `java.base` dùng bootstrap loader, được biểu diễn bằng `null` |
| `missingModuleRejected=true` | Một module không ở layer hay parents làm `findLoader` ném `IllegalArgumentException` |
| `sameModuleDifferentLayers=true` | Named module cùng tên ở hai sibling layers là hai runtime `Module` objects độc lập |

**Kết luận quan trọng:** không thể biết một module dùng ClassLoader nào chỉ từ tên hoặc hệ ba loader tích hợp. Phải truy vấn **ModuleLayer đúng ngữ cảnh**, và còn phải xét module thuộc layer nào khi tồn tại nhiều sibling layers.

### 6.9. Vì sao lấy `Class<?>` và so loader chưa đủ để kiểm tra access?

Ở ví dụ trên, `Class.forName(alphaModule, "demo.alpha.Alpha")` dùng overload theo module. Nó trả `Class<?>` khi tìm được class thuộc module được yêu cầu, hoặc `null` nếu class không nằm trong module đó. API này **không tự link/initialize** class và không kiểm tra caller access đối với class.

Nếu code tiếp tục dùng reflection, constructor, field hoặc method, cần kiểm tra `exports`/`opens`, `requires` và Java access rules riêng. Truy vấn loader thành công không tự mở module.

## 7. Chọn loader khi code thực tế cần nạp class

### 7.1. Bạn biết module name và binary class name

Mẫu đơn giản:

~~~java
static Class<?> locate(ModuleLayer layer,
                       String moduleName,
                       String binaryName) {
    Module module = layer.findModule(moduleName)
            .orElseThrow(() -> new IllegalArgumentException(
                    "Module not in layer hierarchy: " + moduleName));
    return Class.forName(module, binaryName);
}
~~~

**Đây là method minh họa**, cần đặt trong class; không phải một chương trình chạy độc lập. Nó kiểm tra `Module` thực tế, rồi gọi overload theo module để bảo đảm class kết quả thuộc module chỉ định.

Caller:

~~~java
Class<?> type = locate(layer, "demo.alpha", "demo.alpha.Alpha");
if (type == null) {
    System.out.println("Named module không cung cấp class đó");
}
~~~

Dùng `Class.forName(Module,String)` có ý nghĩa khi loader của layer có thể định nghĩa nhiều modules; nó giúp tránh giả định “loader tìm thấy class” đồng nghĩa class thuộc **module đang yêu cầu**.

### 7.2. Bạn có module name và muốn dùng loader tường minh

~~~java
ClassLoader loader = layer.findLoader("demo.alpha");
Class<?> type = loader.loadClass("demo.alpha.Alpha");
~~~

Snippet trên thích hợp khi named module được gán cho **non-null loader**. Nếu named module dùng bootstrap loader, `loader == null`; bạn **không thể** gọi `loader.loadClass`. Cần chọn API phù hợp:

~~~java
Module module = layer.findModule(moduleName).orElseThrow();
Class<?> type = Class.forName(module, binaryName);
~~~

Phép tìm theo module xử lý được trường hợp bootstrap loader; `Class.forName(Module,String)` trả null cho class không nằm trong module, và có những exception/error được tài liệu hóa riêng.

### 7.3. Loader chung có thể định nghĩa nhiều modules

Trong layer `single` của demo, cả `demo.alpha` và `demo.beta` dùng cùng loader. Vì vậy:

~~~text
single.findLoader("demo.alpha") == single.findLoader("demo.beta")
=> true
~~~

Chỉ nhìn `ClassLoader` không phân biệt class thuộc module nào. Khi cần kiểm tra chính xác:

~~~java
Module expected = layer.findModule("demo.alpha").orElseThrow();
boolean rightModule = clazz.getModule() == expected;
~~~

Đây là snippet cần biến `layer`/`clazz`. Tránh chỉ so chuỗi `clazz.getModule().getName()` nếu ứng dụng có nhiều sibling layers cùng module name: **Module object identity** quan trọng.

### 7.4. Bạn cần xác định loader của một class đã tồn tại

Nếu đã có `Class<?>`, thường dùng trực tiếp:

~~~java
ClassLoader loader = actualClass.getClassLoader();
Module owner = actualClass.getModule();
ModuleLayer ownerLayer = owner.getLayer();
~~~

- `getClassLoader()` phản ánh defining loader của class.
- `getModule()` xác định module thật chứa class.
- `getLayer()` cho biết layer của **named module** được tạo trong layer; có thể `null` trong những trường hợp module không thuộc một layer điển hình.
- Nếu `ownerLayer != null` và module có tên, có thể đối chiếu `ownerLayer.findLoader(owner.getName())` với defining loader.

Đây là một hướng chẩn đoán thực tế tốt hơn “chỉ in `ClassLoader.getSystemClassLoader()`”.

## 8. Các trường hợp khác và giới hạn

### 8.1. Unnamed module và classpath

Mỗi `ClassLoader` có **unnamed module** gắn với các class không thuộc named module. Nhưng `ModuleLayer.findLoader` nhận **tên named module**, không phải binary class name và không phải một selector cho unnamed module.

Nếu module của class có `isNamed() == false`, `module.getName()` là `null`. Đừng gọi `layer.findLoader(module.getName())`; hãy dùng `clazz.getClassLoader()` hoặc `module.getClassLoader()` trực tiếp khi muốn biết loader thực tế.

### 8.2. Module path không có nghĩa đã resolve

`ModuleFinder.of(Path.of("mods"))` tìm module artifacts trên đường dẫn, nhưng một module chỉ xuất hiện trong runtime layer sau bước `Configuration.resolve(...)` và `defineModules...` phù hợp.

Tình huống:

~~~text
foo.jar nằm trên disk -> finder có thể nhận diện foo
configuration không resolve foo -> layer không có foo
layer.findLoader("foo") -> tìm parent; nếu cũng không có -> IllegalArgumentException
~~~

Vì vậy, `findLoader` không tự tải module artifact hoặc mở JAR chưa resolve. Cần kiểm tra roots, `requires`, và graph resolution trước.

### 8.3. Cùng tên module ở các sibling layers

Hai child layers được tạo độc lập trên cùng boot layer có thể mỗi layer định nghĩa một module tên `demo.alpha`. Kết quả:

~~~text
Layer S -> Module demo.alpha (Module object S)
Layer M -> Module demo.alpha (Module object M)

Module object S != Module object M
Module loader S != Module loader M (trong demo)
~~~

Bạn cần giữ đúng layer reference tương ứng plugin/application. Nếu vô tình dùng `layerS.findLoader("demo.alpha")` để xử lý class từ `layerM`, loader đúng tên nhưng **sai runtime module identity**, có thể sinh `ClassCastException`, reflection failure hoặc mất access theo JPMS.

### 8.4. Named module ở boot layer

`ModuleLayer.boot()` chứa `java.base` và các resolved modules của startup. Những modules này có thể thuộc bootstrap, platform hoặc application loaders của JVM.

Không có quy tắc “tất cả boot modules có `ClassLoader == null`”. Demo cố ý kiểm tra **`java.base`**, một trường hợp có loader bootstrap. Với các modules khác, đừng hardcode, hãy hỏi `findLoader` hoặc `module.getClassLoader()`.

### 8.5. Không thể “chuyển module sang loader khác” bằng `findLoader`

`findLoader` là thao tác đọc. Không có API `layer.setLoader(module, anotherLoader)` để hoán đổi loader của runtime named module đã được định nghĩa. Muốn thay đổi mapping thường phải tạo **layer khác** với configuration và policy khác, hoặc dùng thiết kế launcher/plugin phù hợp.

Tạo layer mới có thể tạo **class identity mới**. Code phải xử lý vòng đời plugin, tham chiếu class cũ, service instances, threads, caches và `ModuleLayer` cũ để tránh rò rỉ bộ nhớ.

### 8.6. Resource lookup và TCCL cũng khác

`Thread.currentThread().getContextClassLoader()` là Thread Context ClassLoader, có thể khác loader của module trong layer. Chỉ khi API được thiết kế dùng TCCL thì giá trị ấy mới được áp dụng.

`ServiceLoader.load(service)` thường dùng TCCL theo overload tiện ích, trong khi `ServiceLoader.load(layer, service)` chọn providers theo layer/module semantics. Không đổi TCCL rồi suy rằng `layer.findLoader(name)` sẽ trả loader khác: module mapping không bị thay bởi thread context.

## 9. Những lỗi thường gặp khi dùng `findLoader`

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| `IllegalArgumentException` từ `findLoader("foo")` | `foo` không có trong layer hoặc ancestors | Kiểm tra `findModule`, `configuration`, roots và layer reference |
| `NullPointerException` khi gọi `loader.loadClass` | Loader trả `null` hợp lệ cho bootstrap module | Xử lý null; cân nhắc `Class.forName(Module,String)` |
| Có loader nhưng `ClassNotFoundException` | Tên class không đúng, class chưa có, mapping/delegation không tìm được | Kiểm tra binary name, package, module artifact, dùng overload theo module khi thích hợp |
| `Class.forName(Module,name) == null` | Class không có trong **module chỉ định**, có thể ở module khác | Đối chiếu `clazz.getModule()` và module path |
| `LayerInstantiationException` khi `WithOneLoader` | Overlapping packages hoặc split delegation không thể xử lý | Điều chỉnh module graph/mapping, cân nhắc nhiều loaders |
| Layer có module name nhưng class thuộc module sai | Đang nhầm layer, loader chung hoặc sibling layer | So `clazz.getModule() == expectedModule` |
| `ClassCastException` khi tên type giống nhau | Hai class có defining loaders khác nhau | Dùng shared API module được map và đọc nhất quán |
| `IllegalAccessError`/`InaccessibleObjectException` | Java/JPMS accessibility, `exports`/`opens` không phù hợp | Phân tích quyền riêng, không chỉ đổi loader |
| Module ở `--module-path` nhưng lookup không thấy | Module chưa resolve hoặc không có trong đúng layer | Kiểm tra `ModuleFinder`, roots, `Configuration` |
| Deadlock khi dùng custom `defineModules` loaders | Delegation không theo readability hoặc class loading locks | Thiết kế parallel-capable, tránh dependency cycles |
| TCCL trỏ plugin cũ nhưng `findLoader` trả loader hiện tại | Hai cơ chế hoàn toàn độc lập | Khôi phục TCCL và quản lý layer/plugin lifecycle |

### Checklist khi chẩn đoán

1. Bạn có đúng **ModuleLayer instance** không, hay chỉ có một layer khác trong hệ plugin?
2. Named module có trong `layer.modules()` hay chỉ là parent module thấy qua `findModule`?
3. `findLoader` trả `null` thì đó có phải module bootstrap không?
4. Nếu bị exception, có tồn tại module trong layer **và mọi parent** không?
5. Layer được tạo bằng `WithOneLoader`, `WithManyLoaders` hay `defineModules` custom?
6. `parentLoader` là parent ClassLoader nào, còn parent `ModuleLayer` là layer nào?
7. Nếu đã có class, `clazz.getModule()` và `clazz.getClassLoader()` là gì?
8. Tên truyền vào `findLoader` là module name, không phải package/class name?
9. Có xung đột packages, readability, exports/opens, custom delegation?
10. Module đang dùng thuộc classpath unnamed module hay named module thật sự?
11. Nếu reload plugin, loader/layer cũ còn được cache/thread tham chiếu không?

## 10. Những nhận định dễ sai

1. **“Mỗi named module luôn có một loader riêng.”** Sai: `WithOneLoader` cho phép nhiều named modules dùng chung một loader.
2. **“`findLoader` chỉ tìm trong layer trực tiếp.”** Sai: tìm tiếp các parent layers.
3. **“Loader null nghĩa là module không có.”** Sai: `null` là cách API biểu diễn bootstrap loader.
4. **“`findLoader` thiếu module trả null.”** Sai: ném `IllegalArgumentException` khi thiếu ở cả layer và ancestors.
5. **“`findLoader("pkg.Class")` tìm loader cho class đó.”** Sai: đầu vào là **module name**.
6. **“Thêm JAR vào module path khiến `findLoader` tự nhận ra module.”** Sai: cần resolve và tạo layer.
7. **“Có cùng loader thì class thuộc cùng module.”** Sai: một loader có thể định nghĩa nhiều named modules.
8. **“Parent ModuleLayer chính là parent ClassLoader.”** Sai: hai quan hệ khác nhau.
9. **“Đổi TCCL sẽ đổi `layer.findLoader`.”** Sai: layer mapping độc lập TCCL.
10. **“Loader tìm được class nghĩa là caller được phép gọi mọi method.”** Sai: JPMS + Java visibility vẫn được kiểm tra.
11. **“Hai module cùng tên ở hai sibling layers là cùng một runtime Module.”** Sai: object identity và mapping có thể khác.
12. **“`findLoader` tự nạp class và chạy static initializer.”** Sai: nó chỉ trả loader.
13. **“Gọi static `defineModulesWithOneLoader` trả ModuleLayer trực tiếp.”** Sai: bản static trả `ModuleLayer.Controller`.
14. **“Dùng loader tùy chỉnh với `defineModules` là tự động thỏa module delegation rules.”** Sai: ứng dụng chịu trách nhiệm.
15. **“Boot layer chỉ có bootstrap loader.”** Sai: boot modules có thể do nhiều built-in loaders định nghĩa.
16. **“Chỉ cần so module name String là xác định đúng layer.”** Sai khi có sibling layers cùng tên.

## 11. Bài tập và câu hỏi tự kiểm tra

1. `ModuleLayer.findLoader` nhận tên module hay tên class?
2. Khi không có module trong layer và mọi parent layers, `findLoader` ném gì?
3. Vì sao `findLoader("java.base")` có thể trả `null` nhưng không bị lỗi?
4. `findModule(name)` và `findLoader(name)` khác nhau thế nào về return type và trường hợp không tìm thấy?
5. `layer.modules()` có liệt kê các module chỉ xuất hiện ở parent layers không?
6. Tại sao `many.findLoader("java.base")` trong demo không ném lỗi?
7. `defineModulesWithOneLoader` tạo bao nhiêu ClassLoader cho modules mới?
8. `defineModulesWithManyLoaders` xử lý như thế nào với mỗi named module?
9. Tham số `parentLoader` có phải một `ModuleLayer` không? Nó có ý nghĩa gì?
10. `ModuleLayer.defineModulesWithOneLoader(cf, parents, loader)` trả `ModuleLayer` hay `Controller`?
11. Khi nào nên dùng `defineModules` với `Function<String,ClassLoader>` thay vì hai phương thức tiện ích?
12. Vì sao lớp `Alpha` ở child module layer vẫn có thể thuộc loader khác system loader, dù truyền system loader làm `parentLoader`?
13. `Class.forName(Module,String)` và `loader.loadClass(binaryName)` khác nhau thế nào khi một loader định nghĩa nhiều modules?
14. Vì sao `alpha.getClassLoader() == many.findLoader("demo.alpha")` là một phép kiểm tra hữu ích?
15. Khi cùng tên `demo.alpha` ở hai sibling layers, nên so `Module.getName()` hay so trực tiếp `Module` object?
16. Những quy tắc nào ngoài class loader mapping ảnh hưởng việc gọi public class/method qua JPMS?
17. Có thể sửa loader gán cho module đã được định nghĩa chỉ bằng `findLoader` không?
18. Khi `ClassNotFoundException` xuất hiện, vì sao cần xác nhận module đã được resolve và loader thật sự nhìn thấy binary name?
19. Vì sao không nên mặc định TCCL chính là `findLoader` của named module?
20. Nếu loader của `java.base` là null, làm sao lấy `Class<?>` của một class trong module đó một cách đúng hợp đồng?

**Tiêu chí hoàn thành:** chạy demo và giải thích đủ chín dòng stdout; biết dùng `findLoader` để chọn loader theo module; phân biệt lookup qua parent layers, kết quả bootstrap `null`, exception khi không có module, và hiểu module mapping được quyết định tại lúc tạo layer.

## 12. Tài liệu chính thức

- [Java SE 21 — `ModuleLayer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): layer, parent layers, `findLoader`, `findModule` và các phương thức tạo layer.
- [Java SE 21 — `ModuleLayer.findLoader(String)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html#findLoader(java.lang.String)): cách tìm module ở layer/parents, bootstrap null, exception.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `getClassLoader()`, `getLayer()`, module identity.
- [Java SE 21 — `Configuration`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html): module graph resolution.
- [Java SE 21 — `ModuleFinder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html): đọc module artifacts từ directories/JARs.
- [Java SE 21 — `Class.forName(Module,String)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.Module,java.lang.String)): locate/load theo runtime module, phân biệt với overload theo ClassLoader.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loader, delegation và `loadClass`.

**Phạm vi:** Java 17+ và JPMS. Ví dụ đã được biên dịch với `javac --release 17` và thực thi thành công, không phụ thuộc Maven/Gradle hoặc framework. Với custom module layers trong hệ plugin, hãy đối chiếu runtime `Module` object cùng loader thực tế, không kết luận dựa trên chuỗi tên hoặc sơ đồ ba loader đơn giản.
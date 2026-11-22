# ModuleLayer.boot và các layer được tạo động

Từ **Java 9**, Java Platform Module System (JPMS) tổ chức các **named module** cùng những quan hệ phụ thuộc và quy tắc truy cập qua một hoặc nhiều **module layer**. `ModuleLayer.boot()` trả về **boot layer** được tạo khi JVM khởi động để chứa những named module đã được giải quyết cho lần chạy hiện tại. Khi chương trình cần khám phá và nạp module **sau khi JVM đã chạy** — chẳng hạn hệ plugin hay công cụ extensible — ta có thể tạo **dynamic module layer** dựa trên boot layer hoặc các layer khác.

Hai việc này liên quan nhưng **không tương đương**:

- **Boot layer** phản ánh tập module *đã được resolved vào boot layer lúc khởi động*. Nó không phải mọi module có thể tồn tại trong JDK hoặc trên ổ đĩa.
- **Dynamic layer** tạo không gian module bổ sung với `Configuration` và class loader được gán. Tạo layer mới **không sửa trực tiếp boot layer**, không tự biến module mới thành classpath toàn cục và không tự cho mọi module hiện tại quyền đọc module mới.
- **Module, configuration, layer, class loader** là những đối tượng khác nhau. Module graph quyết định readability/exports/opens; defining class loader vẫn tham gia **type identity** của class/interface.

Bài học này xây dựng một project **Java 17 có thể chạy đầy đủ**, tự biên dịch một named module vào thư mục `mods`, tạo **hai dynamic layer** từ cùng module, rồi quan sát class có tên giống nhau nhưng identity khác nhau.

## 1. Nắm bốn khái niệm: module, configuration, layer và loader

| Khái niệm | Ý nghĩa | API chính |
| --- | --- | --- |
| **Module descriptor** | Metadata của named module: tên, `requires`, `exports`, `opens`, `uses`, `provides` và thông tin liên quan. | `module-info.java` / `module-info.class`, `ModuleDescriptor` |
| **Resolved module configuration** | Kết quả giải quyết tập module gốc và phụ thuộc từ một hoặc nhiều `ModuleFinder`, trên cơ sở các parent configuration. | `Configuration`, `resolve(...)`, `ResolvedModule` |
| **Module layer** | Tập named module đã được định nghĩa cho một cấu hình, gắn với loader và các parent layer. | `ModuleLayer`, `ModuleLayer.boot()`, `defineModules...` |
| **Class loader** | Định nghĩa class/interface và giúp JVM nạp chúng theo tên. Một layer có thể dùng một hoặc nhiều loader. | `ClassLoader`, `ModuleLayer.findLoader(...)` |

Sơ đồ tư duy:

~~~text
               module-info.class + module artifacts
                          |
                          v
          ModuleFinder / Configuration.resolve(...)
                          |
                          v
          Resolved Configuration (module graph)
                          |
                          v
             ModuleLayer.defineModules...
                          |
                    ModuleLayer
                          |
                named Module objects
                          |
            loader(s) được gán cho module
                          |
               Class<?> của từng kiểu
~~~

**Resolution** chưa phải **definition**: `Configuration.resolve` xác lập các module và quan hệ phụ thuộc ở mức cấu hình, nhưng chưa biến các lớp bên trong module thành Class của một dynamic layer. Sau bước định nghĩa layer, chương trình mới có thể dùng loader tương ứng để nạp từng class theo yêu cầu.

**Layer** cũng không phải một class loader. Một layer có thể chứa nhiều named module và các phương thức tạo layer khác nhau quyết định cách gán loader:

- `defineModulesWithOneLoader(...)`: các module của layer mới dùng **một loader được tạo cho layer**.
- `defineModulesWithManyLoaders(...)`: mỗi module trong layer mới được gán **loader riêng được tạo**.
- `defineModules(...)`: caller cung cấp hàm ánh xạ tên module sang loader; cần tuân thủ các điều kiện và ràng buộc do API quy định.

Tùy cấu hình, class của một module trong parent layer vẫn do loader được thiết lập trước đó định nghĩa; việc tạo child layer không “nạp lại” tự động mọi module cha.

## 2. Boot layer: ModuleLayer.boot() chứa những gì?

Trong một chương trình Java thông thường:

~~~java
ModuleLayer boot = ModuleLayer.boot();
System.out.println(boot.findModule("java.base").isPresent());
~~~

Đây là **fragment hợp lệ khi đặt trong method**. `java.base` là module nền tảng của mọi module và có trong boot layer của Java 17 tiêu chuẩn, nên dòng thứ hai in `true`.

Để hiểu output, phân biệt ba tập sau:

1. **Modules có thể quan sát được (observable)**: những module mà bộ giải quyết có thể tìm thấy từ system modules, module path và nguồn module tương ứng.
2. **Modules đã được resolved cho boot layer**: những module JVM đưa vào configuration của boot layer khi khởi động, phụ thuộc entry point, root modules, `--add-modules` và quy tắc resolution.
3. **Modules trong dynamic layers**: những named module được chương trình giải quyết và định nghĩa **sau đó** qua API `ModuleLayer`.

`java --list-modules` cho biết các module **observable** với Java launcher trong môi trường tương ứng, không được coi là lệnh liệt kê chính xác mọi module đang resolved trong `ModuleLayer.boot()`. Muốn biết nội dung thực của boot layer tại runtime, dùng `ModuleLayer.boot().modules()` hoặc `findModule(...)`.

### Liệt kê boot modules

Tệp fragment Java 17 sau (đặt trong method):

~~~java
ModuleLayer boot = ModuleLayer.boot();

boot.modules().stream()
        .map(Module::getName)
        .sorted()
        .forEach(System.out::println);
~~~

Kết quả phụ thuộc cách chạy và runtime image, vì vậy không liệt kê stdout cố định cho toàn bộ danh sách. Lệnh `boot.modules()` chỉ trả những module được định nghĩa **ngay trong boot layer**. Nếu dùng `boot.findModule(name)`, API tìm trên layer được gọi và **các parent layer** theo hợp đồng; boot layer thường là gốc nên không có parent.

### Những thuộc tính quan trọng

- `ModuleLayer.boot()` trả **cùng boot layer đang tồn tại** trong runtime, không tạo layer mới mỗi lần gọi.
- Boot layer là một đối tượng quản lý module đã được định nghĩa, không phải bản sao tất cả nội dung `$JAVA_HOME/jmods` hay một directory bất kỳ.
- Class ứng dụng trên classpath thông thường thuộc **unnamed module** của defining loader, không trở thành named module trong `boot.modules()` chỉ vì chạy trên JDK 17.
- Khi khởi động bằng `java --module-path ... -m my.module/...`, module ứng dụng đã được resolved cho thời điểm khởi động có thể nằm ở **boot layer**. Đừng khẳng định boot layer chỉ chứa module `java.*`.
- `ModuleLayer.boot()` không bị động thay đổi khi sau đó chương trình tạo các child layer.

## 3. Dynamic layer: tạo module mới trong khi JVM đang chạy

Giả sử ban đầu chương trình chỉ cần host và các module nền tảng, sau đó phát hiện một module plugin có tên `dev.demo.greeter`. Thay vì yêu cầu restart JVM và resolve module từ startup, ta có thể:

~~~text
JVM startup
    |
    v
ModuleLayer.boot()
    |
    | Ứng dụng tìm thấy module plugin ở thư mục mods/
    v
ModuleFinder.of(Path.of("mods"))
    |
    v
boot.configuration().resolve(...)
    |
    v
Resolved Configuration cho plugin
    |
    v
boot.defineModulesWithOneLoader(...)
    |
    v
Layer động: dev.demo.greeter
    |
    v
layer.findLoader("dev.demo.greeter")
    |
    v
loadClass("dev.demo.greeter.Greeter")
~~~

Các bước cốt lõi:

**Bước 1 — tìm module:** `ModuleFinder` có thể quan sát modular JAR hoặc exploded module directories trong đường dẫn truyền vào, tùy nội dung và quy tắc module path. `ModuleFinder.of(Path.of("mods"))` yêu cầu tìm từ vị trí xác định, không tự scan mọi nơi trong hệ thống.

**Bước 2 — resolve cấu hình:** `boot.configuration().resolve(before, after, roots)` giải quyết tập root module và dependencies; các module đã nằm trong parent configuration thường được tham chiếu ở parent thay vì bị định nghĩa lại tại child. Kết quả là một `Configuration` mới, chưa phải layer.

**Bước 3 — define layer:** dùng một phương thức `defineModules...` để biến configuration thành named module được JVM biết và gán class loader tương ứng.

**Bước 4 — dùng module:** `layer.findModule(name)` tìm `Module`, `layer.findLoader(name)` trả loader của module được định nghĩa trong layer tương ứng, rồi dùng `loadClass` hoặc cơ chế framework để làm việc với type.

**Bước 5 — bảo vệ boundary:** dù module mới đã được nạp, các kiểm tra **readability, exports, opens, service binding và type identity** vẫn tồn tại; không được giả định có `Class<?>` nghĩa là mọi method đều được gọi phản chiếu hợp pháp.

## 4. Project Java 17 chạy độc lập: boot và hai layer động

Để có output không phụ thuộc module ngoài, tạo **đúng ba file** theo cấu trúc:

~~~text
layer-demo/
├── LayerDemo.java
├── src/
│   └── dev.demo.greeter/
│       ├── module-info.java
│       └── dev/
│           └── demo/
│               └── greeter/
│                   └── Greeter.java
└── mods/                      (javac tự tạo sau bước biên dịch)
~~~

### File 1: src/dev.demo.greeter/module-info.java

~~~java
module dev.demo.greeter {
    exports dev.demo.greeter;
}
~~~

Module này **export package** `dev.demo.greeter` để code không nằm trong module có thể truy cập public API theo các quy tắc JPMS. Không cần `requires java.base;` bởi mọi named module ngầm đọc `java.base`.

### File 2: src/dev.demo.greeter/dev/demo/greeter/Greeter.java

~~~java
package dev.demo.greeter;

public final class Greeter {
    public static String message() {
        return "hello from plugin module";
    }
}
~~~

Class công khai, method công khai và package được export để phần host trên classpath có thể gọi method qua reflection sau khi lấy Class bằng loader của layer.

### File 3: LayerDemo.java

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer boot = ModuleLayer.boot();
        System.out.println("Boot contains java.base: "
                + boot.findModule("java.base").isPresent());
        System.out.println("Boot contains plugin: "
                + boot.findModule("dev.demo.greeter").isPresent());

        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        Configuration configuration = boot.configuration().resolve(
                finder, ModuleFinder.of(), Set.of("dev.demo.greeter"));

        ModuleLayer layer1 = boot.defineModulesWithOneLoader(
                configuration, ClassLoader.getSystemClassLoader());
        ModuleLayer layer2 = boot.defineModulesWithOneLoader(
                configuration, ClassLoader.getSystemClassLoader());

        Class<?> first = layer1.findLoader("dev.demo.greeter")
                .loadClass("dev.demo.greeter.Greeter");
        Class<?> second = layer2.findLoader("dev.demo.greeter")
                .loadClass("dev.demo.greeter.Greeter");

        System.out.println("Layer1 has plugin: "
                + layer1.findModule("dev.demo.greeter").isPresent());
        System.out.println("Layer1 parent is boot: "
                + (layer1.parents().get(0) == boot));
        System.out.println("Defined in layer1: "
                + (first.getModule().getLayer() == layer1));
        System.out.println("Same binary name: "
                + first.getName().equals(second.getName()));
        System.out.println("Same Class identity: "
                + (first == second));
        System.out.println("Greeting: "
                + first.getMethod("message").invoke(null));
    }
}
~~~

**Biên dịch bằng JDK 17 trở lên**, đứng trong thư mục `layer-demo`:

~~~bash
javac --release 17 -d mods --module-source-path src -m dev.demo.greeter
javac --release 17 LayerDemo.java
java LayerDemo
~~~

Không truyền `--module-path mods` cho bước `java LayerDemo`: ta cố ý để `dev.demo.greeter` **chưa phải root module của startup**, sau đó resolver của ứng dụng sẽ tìm nó bằng `ModuleFinder.of(...)`. Lệnh biên dịch đầu tạo cấu trúc `mods/dev.demo.greeter/...` chứa `module-info.class` và `Greeter.class`; `LayerDemo` được biên dịch như class thông thường trên classpath.

**Stdout chính xác** với project được tạo như hướng dẫn trên JDK 17 tiêu chuẩn:

~~~text
Boot contains java.base: true
Boot contains plugin: false
Layer1 has plugin: true
Layer1 parent is boot: true
Defined in layer1: true
Same binary name: true
Same Class identity: false
Greeting: hello from plugin module
~~~

### Giải thích output và quá trình chạy

1. `ModuleLayer.boot()` tồn tại sẵn khi `LayerDemo.main` bắt đầu, chứa `java.base`, nên dòng đầu `true`.
2. `dev.demo.greeter` chưa nằm trong boot layer vì ứng dụng được chạy như một class trên classpath và không thêm plugin như root ở command line, nên dòng thứ hai `false`.
3. `ModuleFinder.of(Path.of("mods"))` khám phá exploded named module đã biên dịch. `Configuration.resolve` tìm root `dev.demo.greeter`; sự phụ thuộc vào `java.base` được giải quyết qua parent configuration của boot layer.
4. Hai lời gọi `boot.defineModulesWithOneLoader(configuration, systemLoader)` tạo **hai layer mới** tương ứng; mỗi layer có module `dev.demo.greeter` do layer đó định nghĩa.
5. `layer1.findModule(...)` có module plugin, còn `layer1.parents().get(0) == boot` cho biết layer 1 dùng boot làm parent.
6. `layer1.findLoader(...)` trả **class loader được gán cho module plugin của layer 1**. `first.getModule().getLayer() == layer1` đúng vì Class này thuộc module được định nghĩa ở layer 1.
7. `first` và `second` đều có binary name `dev.demo.greeter.Greeter` nhưng vì được định nghĩa trong **hai loader khác nhau** (mỗi lần defineModulesWithOneLoader tạo loader cho layer), `first == second` là `false`.
8. `Greeter.message` là public trong một package được export, nên lời gọi reflection từ host in đúng `hello from plugin module`.

**Quan trọng:** Ví dụ đã cố ý tạo **hai bản identity của cùng một module/class** để học về isolation. Trong ứng dụng thật, không tạo layer trùng lặp nếu muốn trực tiếp trao đổi object implementation giữa các plugin hoặc giữa host và plugin. Hai module có cùng tên ở hai layer **không biến hai Class thành một**.

### Nếu muốn biết loader thực tế

Trong method `main`, có thể thêm fragment:

~~~java
System.out.println(first.getClassLoader()
        == layer1.findLoader("dev.demo.greeter"));

System.out.println(first.getModule().getName());
System.out.println(first.getModule().isNamed());
~~~

Nếu giữ đúng chương trình, ba dòng lần lượt in `true`, `dev.demo.greeter`, `true`. Đây là **fragment bổ sung**, không nằm trong stdout đã công bố phía trên.

## 5. Boot layer không nhận module mới khi tạo child layer

Sơ đồ kiến trúc sau đúng với chương trình:

~~~text
                              ModuleLayer.boot()
                              ├── java.base
                              ├── ... named modules
                              └── parent configuration
                                  /           \
                                 /             \
                                v               v
                      dynamic layer 1     dynamic layer 2
                       dev.demo.greeter    dev.demo.greeter
                            |                   |
                         loader 1            loader 2
                            |                   |
                       Greeter #1           Greeter #2
                              \                 /
                               same name, distinct identity
~~~

Sau khi tạo layer 1/2, hỏi `boot.findModule("dev.demo.greeter")` vẫn cho `Optional.empty()` trong bối cảnh ví dụ, vì boot layer không bị gắn thêm module. Muốn lấy module mới phải giữ tham chiếu tới `layer1`/`layer2` và tra cứu từ layer tương ứng.

### findModule khác findLoader ở đâu?

- `layer.findModule(name)` tìm `Module` trong layer được chỉ định và theo các parent layer. Trả `Optional<Module>`.
- `layer.findLoader(name)` yêu cầu tên của module **được định nghĩa trong layer mà phương thức được gọi**, trả defining class loader được gán; nếu không có module mang tên ấy tại layer tương ứng, có thể ném `IllegalArgumentException`. Nếu cần loader của module ở parent, hãy hỏi **parent layer** chứa module đó, không giả định child.findLoader được dùng giống child.findModule.
- `module.getLayer()` cho biết layer chứa named module đó (với module layer được định nghĩa theo API). Điều này rất hữu ích khi debug vấn đề lookup hoặc reflection.
- `type.getModule()` cho `Module` định nghĩa kiểu thực tế; `type.getClassLoader()` cho defining loader. Hai API trả lời **hai câu hỏi khác nhau**.

Một vấn đề phổ biến là tìm thấy module qua `child.findModule("java.base")` rồi tưởng rằng `child.findLoader("java.base")` có nghĩa tương tự: `java.base` ở boot layer, không được định nghĩa lại bởi child. Do đó `child.findLoader("java.base")` không phải đường tra cứu loader của module parent.

## 6. Resolution và module dependency: không chỉ có tên trong thư mục

Ví dụ chỉ có một module mới. Trong ứng dụng phức tạp, một plugin có thể có descriptor:

~~~java
module acme.plugin {
    requires acme.contract;
    requires java.logging;
    exports acme.plugin.api;
}
~~~

Đây là **fragment `module-info.java`**, không phải module độc lập có đủ source/build script trong bài. Nó nói `acme.plugin` cần đọc `acme.contract` và `java.logging`. Trước khi tạo layer, resolver phải tìm được các module đó trong finder hoặc parent configurations. Nếu `acme.contract` thuộc boot/parent layer, dynamic layer có thể dùng module đã resolved ở parent mà không định nghĩa lại nó.

Giải quyết module **không đồng nghĩa toàn bộ class được tải ngay**. JVM có thể nạp từng Class khi cần; `Configuration` mô tả graph đã resolved, còn class loader quyết định định nghĩa cụ thể khi class được sử dụng.

### ModuleFinder là bộ tìm module, không phải ClassLoader

`ModuleFinder.of(Path.of("mods"))` cung cấp các `ModuleReference`/descriptor để phục vụ resolution. Nó không có method `loadClass` như ClassLoader và không tự định nghĩa JVM types. Phải đi tiếp qua bước **define layer** rồi lấy loader của named module.

### before và after finder trong resolve

API `Configuration.resolve(before, after, roots)` ưu tiên thứ tự tìm module và tham chiếu các parent configurations theo hợp đồng. Về mặt ứng dụng, điều quan trọng là root modules và tất cả dependencies phải được giải quyết **từ nguồn đáng tin, nhất quán**. Không nên mô tả đơn giản rằng “before/after sẽ lần lượt load ClassFile”: chúng tham gia **module resolution**, không chạy `ClassLoader.loadClass`.

Nếu module bị thiếu, descriptor conflict, graph không hợp lệ hoặc tên root sai, resolution có thể thất bại trước khi define layer. Nếu resolution thành công nhưng ràng buộc về gán loader/package conflict không thỏa, bước define layer còn có thể thất bại riêng.

## 7. Một loader hay nhiều loader cho một layer?

Hai API phổ biến của `ModuleLayer` quyết định cách các named module được gắn với defining class loader.

| API | Chính sách loader | Khi nào cân nhắc |
| --- | --- | --- |
| `defineModulesWithOneLoader(configuration, parentLoader)` | Mọi module trong layer mới dùng **một class loader mới** do API tạo. | Plugin gồm nhiều module cần chia sẻ cùng không gian loader, đóng gói thống nhất. |
| `defineModulesWithManyLoaders(configuration, parentLoader)` | Mỗi module trong layer mới có **một loader mới riêng** do API tạo. | Cần tách không gian loader theo module. |
| `defineModules(configuration, parents, mapper)` | Caller tự cung cấp **hàm tên module → class loader**, dùng static API tạo layer/controller. | Nhu cầu tích hợp loader tùy biến, module mapping phức tạp. |

Đừng diễn giải tên `WithOneLoader` thành “dùng nguyên system loader có sẵn để định nghĩa tất cả module”. `parentLoader` là **parent loader của loader mới**, không phải yêu cầu định nghĩa trực tiếp module mới vào `ClassLoader.getSystemClassLoader()`.

Vì vậy, chương trình phần 4 dù truyền cùng `ClassLoader.getSystemClassLoader()` cho hai lời gọi `defineModulesWithOneLoader` vẫn tạo **hai defining loader khác nhau**, dẫn đến hai identity Greeter khác nhau.

### Nhiều loader không đồng nghĩa không thể đọc dependencies

Module readability và class loader mapping phải tương thích. Với phương thức do JDK cung cấp, JVM tạo loader và thiết lập cơ chế tìm class tương ứng. Với custom mapper, người viết phải đảm bảo loader support việc nạp class của module, giới hạn package và các điều kiện JVM/API. Không nên xem một graph `requires` hợp lệ là giấy phép tự định nghĩa trùng một API class trong nhiều loader.

## 8. Class identity, API dùng chung và hai layer độc lập

Một lớp `dev.demo.greeter.Greeter` trong layer 1 và cùng binary name trong layer 2 có thể **khác `Class<?>`**. JVM dùng cặp:

~~~text
type identity = (binary name, defining class loader)
~~~

Các tình huống cần xét:

- **Plugin tải độc lập:** nhiều dynamic layer cho cùng module cho phép cô lập hai phiên bản/module deployment, nhưng không tự cho phép ép object implementation của layer A sang Class implementation của layer B.
- **Host–plugin giao tiếp:** cần interface/DTO contract có cùng defining loader/layer phù hợp; thường đặt một module API ổn định ở **parent layer/loader dùng chung** để plugin tham chiếu.
- **ServiceLoader:** có thể khám phá provider từ named module qua `ServiceLoader.load(layer, Service.class)` khi cấu hình service phù hợp. Trong trường hợp này, API service type vẫn phải được định nghĩa tương thích ở host và provider.
- **Hot redeploy:** tạo layer mới không tự làm object của layer cũ biến mất. Nếu cache, thread, service registry hoặc TCCL giữ object/class/loader cũ, class unloading có thể chưa xảy ra.

Nếu một module API `com.acme.contract` được tự định nghĩa hai lần ở các sibling layers thì host có thể gặp lỗi giống “class A cannot be cast to class A”. Thiết kế thường tốt hơn là đặt contract ở parent/loader dùng chung để cả hai child cùng tham chiếu, còn implementation nằm trong từng child.

### Không có API unload ModuleLayer trực tiếp

`ModuleLayer` không có `close()` để tự tháo một layer khỏi JVM. Việc JVM thu hồi class/class loader cần điều kiện reachability và garbage collection tương ứng, nên cần quản lý lifecycle: dừng plugin tasks, release `ServiceLoader`/provider, listener, cache, TCCL, method handle và reference đến layer/loader. Đừng coi việc gán `layer = null` là lệnh unload ngay lập tức.

## 9. Readability, exports và opens vẫn áp dụng

Tạo layer thành công không có nghĩa code ở bất cứ module nào cũng truy cập được mọi package của module mới.

**Khái niệm cần tách:**

- `requires`: module phụ thuộc và thường có quan hệ **readability** với module được yêu cầu.
- `exports`: cho phép truy cập **public types/members** trong package được export từ bên ngoài, theo quy tắc module system.
- `opens`: cho phép truy cập bằng **deep reflection** khi phù hợp (ví dụ dùng `setAccessible(true)`), không đồng nghĩa public compile-time API.
- `uses` / `provides ... with ...`: khai báo consumer/provider cho service binding và discovery.

Trong ví dụ, `exports dev.demo.greeter;` cho phép host gọi public method `Greeter.message()` qua reflection. Nếu bỏ exports, ta vẫn có thể định vị Class qua layer loader trong những tình huống cho phép, nhưng lời gọi phản chiếu từ một module không được quyền truy cập có thể gặp `IllegalAccessException` hoặc lỗi truy cập phù hợp.

### Host muốn import trực tiếp class trong dynamic module?

`LayerDemo.java` là code nằm trên classpath và dùng `Class<?>`/reflection, **không** có dòng `import dev.demo.greeter.Greeter;`. Đây là chủ ý: module chỉ được định nghĩa **sau khi chương trình đã khởi động**, nên trình biên dịch/loader của host không tự nhận nó như một dependency tĩnh.

Nếu host muốn truy cập trực tiếp theo kiểu compile-time, cần thiết kế module graph/runtime phù hợp từ đầu; một lựa chọn phổ biến cho plugin là **shared API module** mà host và plugin cùng biết ở startup, rồi truyền implementation qua API hoặc `ServiceLoader`. Dynamic layer không tự thêm cạnh `requires` vào `module-info` của host hay biến package plugin thành classpath tự do.

## 10. Controller và những điều chỉnh ở runtime

Ngoài instance method `boot.defineModulesWithOneLoader(...)` trả trực tiếp `ModuleLayer`, các static API `ModuleLayer.defineModulesWithOneLoader(configuration, List.of(boot), parentLoader)` hoặc những biến thể khác có thể trả `ModuleLayer.Controller`. Controller giúp lấy `layer()` và thực hiện các điều chỉnh có phạm vi:

~~~java
// Fragment: nằm trong method có sẵn các biến cf, boot, parentLoader.
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                cf, java.util.List.of(boot), parentLoader);

ModuleLayer layer = controller.layer();
~~~

Đây là **fragment phụ thuộc biến** `cf`, `boot`, `parentLoader`; không phải chương trình biên dịch độc lập. Controller có các method như `addReads`, `addExports` và `addOpens` với những điều kiện về module trong layer được controller quản lý.

Các phương thức này thay đổi **quan hệ truy cập tại runtime** theo API; chúng không thay đổi mã nguồn `module-info.java`, không viết lại `module-info.class` và không tự cho phép nạp các module chưa được resolved/defined.

Tránh dùng controller để “mở tất cả package cho mọi nơi” theo phản xạ. Với plugin, nên giữ boundary tối thiểu cần dùng và chỉ mở package thật sự phục vụ API/reflection.

## 11. Lỗi phổ biến khi làm dynamic layers

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `boot.findModule("my.plugin")` rỗng sau khi tạo child layer | Boot layer không bị bổ sung module mới. | Dùng `child.findModule("my.plugin")`; giữ reference child layer. |
| `LayerInstantiationException` | Configuration/loader mapping hoặc các quy tắc của layer không thể đáp ứng. | Đọc thông báo, kiểm tra package/module/loader constraints. |
| `FindException` hoặc `ResolutionException` | Resolver không tìm được module hoặc graph phụ thuộc không hợp lệ. | Kiểm tra `ModuleFinder`, roots, dependency descriptors và parent configs. |
| `ClassNotFoundException` dù `findModule` trả module | Dùng sai loader, tên class sai hoặc class không tồn tại trong module. | Lấy loader qua `layer.findLoader(moduleName)` và kiểm tra binary name/JAR contents. |
| `IllegalArgumentException` ở `findLoader` | Hỏi tên module không được định nghĩa trong layer đang gọi. | Xác định module được định nghĩa ở layer nào, dùng đúng layer đó. |
| `IllegalAccessException` hoặc `InaccessibleObjectException` | Package chưa export/open phù hợp cho caller/reflection. | Kiểm tra `module-info.java`, `isExported`, `isOpen` và quyền truy cập. |
| `ServiceConfigurationError` | Provider không tìm thấy/không hợp lệ hoặc identity interface không khớp. | Kiểm tra `uses`/`provides`, service layer và shared API type. |
| `ClassCastException` giữa hai class cùng tên | Hai layer/loader định nghĩa hai kiểu độc lập. | So `Class<?> ==`, `getClassLoader()`, `getModule()`, `getLayer()`. |
| Plugin cũ không được thu hồi | Reference còn giữ layer/loader/instances hoặc thread còn sống. | Dọn lifecycle plugin và monitor references. |

**Lưu ý:** Không phải mọi lỗi trong bảng đều do module layer trực tiếp tạo ra. `ClassNotFoundException` có thể chỉ là sai binary name; `IllegalAccessException` còn do Java reflection access khác; `ServiceConfigurationError` có nhiều nguyên nhân. Hãy đọc message, cause và cấu hình thực tế.

### Bẫy “cùng tên module” không có nghĩa cùng Module object

Ví dụ:

~~~java
Module m1 = layer1.findModule("dev.demo.greeter").orElseThrow();
Module m2 = layer2.findModule("dev.demo.greeter").orElseThrow();

System.out.println(m1 == m2);
~~~

Đây là **fragment phụ thuộc layer1/layer2 của chương trình phần 4**. Nó in `false` vì đó là hai named Module object thuộc hai layer khác nhau. Tương tự, `Greeter` class của hai layer khác defining loader. **Không nên dùng riêng chuỗi `module.getName()` để khẳng định cùng module runtime instance.**

## 12. Checklist khi thiết kế plugin với ModuleLayer

1. **Xác định module nào thuộc boot/parent layer** và module nào cần nạp động.
2. **Tách API contract chung khỏi implementation:** API/module dùng chung nên ở parent layer/loader ổn định nếu host và plugin cần giao tiếp trực tiếp.
3. **Chuẩn bị module artifacts** có `module-info.class` hợp lệ; phân biệt modular JAR, exploded module và classpath JAR thường.
4. **Dùng ModuleFinder phù hợp** và chỉ định đúng root module names, không biến file path thành module name.
5. **Resolve configuration** có đủ dependencies, kiểm tra conflict và thông báo ngoại lệ.
6. **Chọn chiến lược loader** (one loader, many loaders, custom mapping) theo yêu cầu isolation/type identity.
7. **Define layer với parent layer đúng**, rồi giữ tham chiếu để lookup module/loader.
8. **Kiểm tra module readability/exports/opens**, không chỉ việc Class đã được load.
9. **Thử hai layer chứa cùng module** để nhận diện đúng tình huống split identity nếu thiết kế cần coexistence.
10. **Service provider và resources:** xác nhận loader/TCCL/ServiceLoader được dùng thực sự nhìn thấy các provider và class API chung.
11. **Quản lý lifecycle:** dừng threads, hủy callbacks, dọn cache và reference nếu plugin bị vô hiệu hóa/redeploy.
12. **Không tự chỉnh boot layer** bằng giả định rằng tạo dynamic layer sẽ khiến mọi class loader trong JVM nhìn thấy module mới.

## 13. Tự kiểm tra kiến thức

**Câu 1.** `ModuleLayer.boot()` có chứa mọi module có trong `$JAVA_HOME` không?

**Đáp án:** Không. Boot layer chứa các **named module đã được resolved và defined cho boot layer** lúc startup; những module observable khác có thể chưa được resolved vào đó.

**Câu 2.** `ModuleFinder.of(Path.of("mods"))` có tự load class plugin chưa?

**Đáp án:** Chưa. Nó tìm **module references/descriptors** phục vụ resolution; cần resolve, define layer và dùng loader mới khi muốn nạp class.

**Câu 3.** Tạo `layer1` từ `boot.defineModulesWithOneLoader` có làm `boot.findModule("plugin")` tự trả giá trị không?

**Đáp án:** Không. Layer con là một đối tượng mới, không tự thêm module vào boot layer.

**Câu 4.** Hai layer cùng resolve một module tên `dev.demo.greeter` và dùng `defineModulesWithOneLoader` riêng biệt. `Greeter.class` của chúng có nhất thiết cùng identity không?

**Đáp án:** Không. Trong ví dụ, mỗi layer tạo loader riêng nên `Class<?>` khác nhau, dù binary name giống hệt.

**Câu 5.** `layer.findModule("java.base")` tìm thấy module ở parent, có nên gọi ngay `layer.findLoader("java.base")` để lấy loader tương ứng không?

**Đáp án:** Không suy vậy. `findModule` có thể tra cứu parent layer; `findLoader` cần tên module được định nghĩa ngay trong layer được gọi. Với `java.base` hãy dùng layer thực sự định nghĩa nó (thường là boot layer).

**Câu 6.** Dynamic layer đã nạp plugin, host có được gọi mọi private member bằng reflection không?

**Đáp án:** Không. Vẫn chịu quy tắc `exports`/`opens` và điều kiện reflection; module được tìm thấy không đồng nghĩa được deep-reflect tự do.

**Câu 7.** `defineModulesWithOneLoader(cf, parentLoader)` có nghĩa dùng nguyên parentLoader để định nghĩa tất cả module mới không?

**Đáp án:** Không. API này **tạo loader mới cho module của layer** với parentLoader được truyền làm parent; điều này giải thích vì sao hai lần định nghĩa riêng có class identity khác nhau.

## Ghi nhớ

`ModuleLayer.boot()` đại diện cho **boot module graph** khi JVM khởi động. Khi cần module plugin lúc runtime, ta **tìm module → resolve `Configuration` → define dynamic `ModuleLayer` → lấy module loader → nạp/khám phá class**. Dynamic layer không sửa boot layer và không tự tạo quyền truy cập toàn cục. Class identity vẫn phụ thuộc defining loader; để host–plugin tương tác an toàn hãy đặt **API contract chung** ở parent layer/loader, xác định đúng module access và quản lý lifecycle của các layer/loader động.

**Tài liệu chính thức:**

- Java SE 17 API, `ModuleLayer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 17 API, `Configuration`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- Java SE 17 API, `ModuleFinder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java SE 17 API, `Module`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java SE 17 API, `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java Virtual Machine Specification, Java SE 17 `5.3 (*Creation of Classes and Interfaces*): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3

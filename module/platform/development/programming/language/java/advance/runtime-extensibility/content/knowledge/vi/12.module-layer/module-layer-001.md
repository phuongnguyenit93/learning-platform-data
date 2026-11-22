# Quan hệ giữa Configuration, ModuleLayer, module và class loader trong Java

## 1. Bốn khái niệm cùng tham gia một cơ chế, nhưng không đồng nghĩa

Từ Java 9, **Java Platform Module System (JPMS)** bổ sung khái niệm *named module* và một mô hình rõ ràng cho sự phụ thuộc, khả năng đọc (*readability*), xuất package (*exports*) và quyền phản chiếu sâu (*opens*). Khi host cần nạp các module mở rộng lúc chạy, bốn thực thể sau thường xuất hiện cùng nhau:

- **`Configuration`** (`java.lang.module.Configuration`): đồ thị các **module đã được giải quyết phụ thuộc** ở cấp mô tả; các đỉnh là `ResolvedModule`. Nó biểu diễn module nào được chọn và module nào được phép *đọc* module nào trước khi module được định nghĩa vào JVM.
- **`ModuleLayer`** (`java.lang.ModuleLayer`): một **tầng module runtime** được tạo từ `Configuration` và một phép ánh xạ mỗi module sang `ClassLoader`. Việc tạo layer khiến JVM biết những named module nào tồn tại ở tầng đó, class thuộc module nào, và các quan hệ module tương ứng.
- **`Module`** (`java.lang.Module`): **đối tượng module runtime cụ thể**, do JVM tạo khi layer được định nghĩa. Các class thuộc named module ấy có thể xác định module của mình qua `Class.getModule()`.
- **`ClassLoader`** (`java.lang.ClassLoader`): cơ chế **tìm và định nghĩa class**, cung cấp lớp và resource ở runtime. Class loader được gắn với các module trong layer, nhưng **một class loader có thể phục vụ nhiều module** tùy cách tạo layer.

Dòng chảy tư duy:

```text
JAR/module directory
    └─ module-info.class + classes + resources
                     │
                     ▼
           ModuleFinder (nhìn thấy module)
                     │
                     ▼
         Configuration.resolve(...)
           - root modules
           - requires / readability graph
           - parent Configuration(s)
                     │
                     ▼
         ModuleLayer.defineModules...
           + chọn ánh xạ module -> ClassLoader
           + xác định parent layer(s)
                     │
                     ▼
        JVM tạo java.lang.Module objects
        + liên kết với layer
        + ánh xạ tới class loaders
                     │
                     ▼
    Loader định nghĩa class khi cần
    Class<?>.getModule() -> runtime Module
    Module.getLayer()   -> runtime ModuleLayer
```

**Điểm mấu chốt:** `Configuration` trả lời “*đồ thị module hợp lệ gồm những gì và ai đọc ai?*”; `ModuleLayer` trả lời “*đồ thị ấy được hiện thực thành các module runtime ở tầng nào?*”; `Module` là “*module runtime cụ thể*”; `ClassLoader` trả lời “*code của module được tìm/nạp bởi loader nào?*”.

### Bảng phân biệt nhanh

| Khía cạnh | `Configuration` | `ModuleLayer` | `Module` | `ClassLoader` |
| --- | --- | --- | --- | --- |
| Package | `java.lang.module` | `java.lang` | `java.lang` | `java.lang` |
| Đơn vị | Đồ thị đã resolve | Tập module runtime trong một layer | Một module runtime | Một đối tượng nạp class |
| Vai trò chính | Xác định phụ thuộc và readability | Định nghĩa module trong JVM, gắn module với loader | Đại diện module và quyền truy cập runtime | Nạp/định nghĩa class, tìm resource |
| Chứa/truy xuất | `ResolvedModule` và quan hệ `reads` | `Module`, parent layers, `Configuration` | Descriptor, packages, layer, loader | Class/resource đã nạp hoặc có thể nạp |
| API thường dùng | `modules()`, `findModule()`, `resolve()` | `configuration()`, `modules()`, `findLoader()`, `findModule()` | `getName()`, `getLayer()`, `getClassLoader()`, `canRead()` | `loadClass()`, `getResource()` |
| Tồn tại trước khi JVM định nghĩa module mới? | Có | Chưa, cho layer mới | Chưa, cho module mới | Loader cha có thể đã tồn tại; loader con có thể được tạo khi định nghĩa layer |

`ResolvedModule` **không** phải `java.lang.Module`: đối tượng thứ nhất thuộc bước resolution, đối tượng thứ hai đại diện module đã định nghĩa trong runtime.

## 2. Từ module descriptor đến Configuration

### 2.1. Descriptor xác định các quan hệ khai báo

Một named module thường có `module-info.java`:

```java
module plugin.greeting {
    requires app.api;
    provides app.api.GreetingService
        with plugin.greeting.HelloGreeting;
}
```

Đây là **mô tả module**:

- `module plugin.greeting` đặt tên module.
- `requires app.api` khai báo module phụ thuộc vào API chung.
- `provides ... with ...` đăng ký provider để `ServiceLoader` có thể tìm dịch vụ trong layer thích hợp.
- Nếu package implementation không cần API khác gọi trực tiếp thì **không cần `exports plugin.greeting`** chỉ để SPI khởi tạo provider.

Ngoài `requires`, JPMS còn có `requires transitive`, `requires static`, `exports`, `opens` và `uses`. Chúng giải quyết các yêu cầu khác nhau: khả năng đọc module, khả năng sử dụng public types, reflective access và cơ chế dịch vụ.

Những dòng trên mới là **khai báo**; tên module trong file không tự tạo một module runtime mới cho JVM.

### 2.2. ModuleFinder xác định module có thể quan sát

`ModuleFinder` (`java.lang.module.ModuleFinder`) là cơ chế tìm **module artifact**, ví dụ một modular JAR hoặc một exploded module directory.

```java
Path pluginJar = Path.of("dist/plugins/plugin.greeting.jar");
ModuleFinder finder = ModuleFinder.of(pluginJar);
```

Đây là **mã minh họa** (cần `import java.nio.file.Path;` và `import java.lang.module.ModuleFinder;`, và file JAR hợp lệ). `ModuleFinder.of(path)` không tự tạo `ModuleLayer`, không khởi chạy `main` và không tự gọi provider của SPI. Nó chỉ cung cấp cách tìm module reference và metadata cho bước resolution.

Khi làm ứng dụng thực tế, plugin artifact nên được xác minh nguồn, tính toàn vẹn, version và policy trước khi đưa vào module finder nếu không tin cậy. Tìm artifact không phải cơ chế cô lập bảo mật.

### 2.3. Configuration.resolve tạo đồ thị đọc được

Mẫu thường dùng với **boot layer làm cha**:

```java
ModuleLayer parent = ModuleLayer.boot();

Configuration cf = parent.configuration().resolve(
    finder,                 // tìm module mới trước
    ModuleFinder.of(),     // finder bổ sung (rỗng ở đây)
    Set.of("plugin.greeting") // tên root module cần giải quyết
);
```

Đây là **đoạn minh họa** có import `java.lang.module.Configuration`, `ModuleFinder` và `java.util.Set`; ví dụ chạy hoàn chỉnh ở mục 6.

Ý nghĩa các tham số:

- `parent.configuration()` là đồ thị module đã được giải quyết của boot layer; module trong boot layer, ví dụ `java.base` và `app.api` nếu ứng dụng đã khởi chạy với API module ấy, có thể là dependency của module mới.
- `finder` là tập module tìm kiếm **trước** các parent configuration khi giải quyết.
- `ModuleFinder.of()` là finder bổ sung **sau** parent configurations; ở ví dụ để trống.
- `Set.of("plugin.greeting")` là các module gốc (*roots*) của phép giải quyết, không phải toàn bộ các module bắt buộc có trong configuration. `requires` có thể kéo thêm module từ finder.

Với `resolve(before, after, roots)`, resolution áp dụng thứ tự tìm kiếm trước → parent configuration → sau để tìm module cần thiết. **Module đã tìm thấy ở parent configuration không bị “chép” sang configuration mới**; đồ thị mới có thể tham chiếu tới module ở parent. Vì vậy với `plugin.greeting requires app.api`, nếu `app.api` đã thuộc boot configuration, layer mới thường chỉ cần định nghĩa `plugin.greeting`, còn `app.api` tiếp tục sống ở parent layer.

### 2.4. Configuration chứa ResolvedModule, không chứa class loader

Một `Configuration` cung cấp:

```java
for (ResolvedModule m : cf.modules()) {
    System.out.println(m.name());
    for (ResolvedModule dependency : m.reads()) {
        System.out.println("  reads: " + dependency.name());
    }
}
```

Đây là **đoạn minh họa** với `import java.lang.module.ResolvedModule;`, thực hiện sau khi tạo `cf`. `cf.modules()` chỉ liệt kê `ResolvedModule` **trực tiếp trong configuration đó**; `cf.findModule(name)` có thể tìm trong configuration hoặc parent configuration. Phân biệt điều này quan trọng khi debug dependency graph.

`Configuration` mô tả *module readability graph* nhưng không ấn định class loader của từng module. Nó có thể được tính trước khi host chọn dùng một loader chung hoặc mỗi module một loader. Thông tin như version, module descriptor, references và các cạnh `reads` không tương đương việc class đã được nạp vào JVM.

**Resolution thành công chưa bảo đảm code runtime hoàn toàn chạy được**: file bytecode có thể hỏng, thư viện có lỗi liên kết, quyền reflective access thiếu, service provider khởi tạo thất bại hoặc logic ứng dụng cần cấu hình khác. Đây là các bước cần kiểm tra tiếp.

### 2.5. Phân biệt resolve và resolveAndBind

- `resolve(...)` giải quyết từ những **root modules** và dependency cần thiết của chúng.
- `resolveAndBind(...)` còn thực hiện **service binding** để có thể kéo vào các module provider được tìm thấy và phù hợp với các service được dùng, theo quy tắc JPMS.

Nếu plugin được đưa trực tiếp vào roots (`Set.of("plugin.greeting")`), ví dụ này dùng `resolve(...)` là đủ. Đừng nghĩ rằng chỉ khai báo `uses` là `resolve(...)` sẽ mặc nhiên gom mọi module provider đang có trên ổ đĩa; khi muốn khám phá provider module nhờ service binding, hãy tìm hiểu `resolveAndBind` và phạm vi `ModuleFinder`.

## 3. Từ Configuration sang ModuleLayer

### 3.1. Layer hiện thực hóa đồ thị đã resolve

API tiêu biểu:

```java
ModuleLayer parent = ModuleLayer.boot();

ModuleLayer child = parent.defineModulesWithOneLoader(
    cf,
    ClassLoader.getSystemClassLoader()
);
```

Khi gọi:

1. JVM kiểm tra tính hợp lệ của cấu hình đối với layer cha; trường hợp dùng phương thức instance, configuration mới phải có đúng **một parent configuration**, chính là `parent.configuration()`.
2. API tạo một class loader mới cho tất cả module **trong configuration mới** (đối với `defineModulesWithOneLoader`), với class loader truyền vào làm **parent của loader mới**.
3. JVM tạo một `java.lang.Module` tương ứng với mỗi `ResolvedModule` ở configuration mới và gắn nó với `ModuleLayer` mới.
4. Runtime thiết lập quan hệ đọc module được resolve; module mới có thể đọc module trong layer của nó hoặc trong parent layer theo đồ thị.
5. Layer mới sẵn sàng để class được nạp theo nhu cầu, nhưng việc **định nghĩa layer chưa đồng nghĩa mọi class đều được nạp/khởi tạo hoặc provider đã chạy**.

`ModuleLayer.boot()` là boot layer JVM tạo lúc khởi động, chứa `java.base` và những module khác đã được resolve cho lần chạy ấy. Một ứng dụng có thể tạo nhiều child layers từ boot layer hoặc xây một cây/đồ thị layer; layer không phải namespace duy nhất của toàn JVM.

**Lưu ý về tên tham số `parentLoader`:** Đây là **loader cha của loader mới**, chứ không phải yêu cầu JVM đưa toàn bộ module mới trực tiếp vào đúng đối tượng loader truyền vào. Trong ví dụ `defineModulesWithOneLoader(cf, ClassLoader.getSystemClassLoader())`, loader cho plugin là **loader mới**, thường không bằng system loader.

### 3.2. Các lựa chọn ánh xạ module → loader

| Cách tạo layer | Module được ánh xạ ra sao? | Khi nào cân nhắc? |
| --- | --- | --- |
| `parent.defineModulesWithOneLoader(cf, parentLoader)` | **Tất cả module trong configuration mới dùng cùng một loader mới** | Nhóm module được đóng gói cùng, đơn giản và không xung đột package/delegation |
| `parent.defineModulesWithManyLoaders(cf, parentLoader)` | **Mỗi module có một loader mới riêng** | Muốn phân tách module rõ hơn, dependency/module graph phức tạp hơn |
| `parent.defineModules(cf, moduleName -> loader)` | Host tự ánh xạ tên module sang loader theo chính sách | Tích hợp custom class loader hoặc cơ chế nạp code chuyên biệt |
| Các phương thức `ModuleLayer.defineModules...(cf, parents, ...)` dạng static | Cho phép nhiều parent layers, trả `ModuleLayer.Controller` | Cấu trúc nhiều layer cha hoặc cần quyền điều khiển runtime đọc/xuất/mở module |

Đối với dạng **instance**, kết quả của `defineModulesWithOneLoader` và `defineModulesWithManyLoaders` là `ModuleLayer`. Đối với những dạng **static có danh sách parent layers**, kết quả là `ModuleLayer.Controller`; gọi `controller.layer()` để lấy layer. Không trộn hai chữ ký API với nhau.

`defineModulesWithOneLoader` có thể thất bại khi các module cùng layer có package trùng nhau hoặc việc ủy quyền của một loader cho một package bị phân tách giữa nhiều loader. `defineModulesWithManyLoaders` tạo loader riêng cho mỗi module, nhưng **không tự giải quyết** mọi vấn đề dependency/version, readability hay xung đột package theo quy tắc JPMS. `defineModules` với custom loader đòi host tự bảo đảm quy tắc ủy quyền phù hợp readability, tránh những trường hợp loader định nghĩa trùng package/module và các deadlock khi tải class đồng thời.

### 3.3. Quan hệ cha của layer và cha của class loader là hai quan hệ khác nhau

Một sai lầm thường gặp là đồng nhất:

- **Parent ModuleLayer:** quan hệ giữa *tầng module runtime*. `child.parents()` trả các parent layers; chúng phản ánh cấu trúc từ parent configurations khi tạo layer.
- **Parent ClassLoader:** quan hệ ủy quyền tìm class giữa các loader. Nó do cách khởi tạo class loader quyết định, ví dụ `defineModulesWithOneLoader(cf, parentLoader)` dùng một loader mới có `parentLoader` làm cha.

Hai quan hệ này **không bắt buộc có cùng cấu trúc**. Parent layer có thể chứa module được nạp bởi nhiều built-in class loaders. Loader trong child layer có thể dùng direct delegation đến đúng loader của module phụ thuộc thay vì chỉ theo một chuỗi cha thông thường. Không kết luận “layer A là cha B” nghĩa là mọi class của A đều được nạp bởi parent trực tiếp của mọi loader ở B.

Ví dụ sơ đồ:

```text
            ModuleLayer.boot()
             configuration0
           /               \
   java.base             app.api
   bootstrap loader      app/system loader
           \               /
            \  readability
             \            /
             ModuleLayer child
               configuration1
               plugin.greeting
               loader L (new)
                      │
               parentLoader = system
```

Đây là mô hình khái niệm; class loader cụ thể cho module boot phụ thuộc cách JVM tổ chức built-in modules. `plugin.greeting` được giải quyết phụ thuộc vào `app.api` ở boot configuration; lớp của plugin được định nghĩa ở loader L; lớp của `app.api` vẫn thuộc loader đã định nghĩa API ở boot layer. Phần ràng buộc đọc module và cơ chế nạp lớp phối hợp nhau nhưng giải quyết hai khía cạnh khác nhau.

## 4. Module runtime và các đường truy vấn qua API

### 4.1. Phân biệt hai tập “modules()”

`Configuration.modules()` trả tập **`ResolvedModule`**, còn `ModuleLayer.modules()` trả tập **`java.lang.Module`**.

```java
Set<ResolvedModule> resolved = cf.modules();
Set<Module> runtime = child.modules();
```

Đây là đoạn minh họa sau khi có `cf` và `child`.

Nếu module `app.api` đã nằm ở boot layer, còn `plugin.greeting` nằm trong child layer:

- `child.modules()` chứa `plugin.greeting`, **không tự chứa** `app.api` chỉ vì plugin đọc API.
- `child.findModule("app.api")` **có thể tìm ra** module `app.api` trong parent layer.
- `cf.modules()` chứa những module mới được resolve trong configuration của child; `cf.findModule("app.api")` có thể tra cứu qua parent configuration.

Vì vậy nếu định kiểm tra “module này được tạo **trong chính layer mới** hay chỉ nằm ở cha?”, hãy xem `child.modules().contains(module)` thay vì chỉ xét `child.findModule(name).isPresent()`.

### 4.2. Dùng Class và Module để kiểm tra vị trí thực tế

Khi lớp đã được nạp:

```java
Module module = provider.getClass().getModule();
ModuleLayer ownerLayer = module.getLayer();
ClassLoader loader = provider.getClass().getClassLoader();
```

Đoạn minh họa sau khi `provider` đã được tạo.

- `Class.getModule()` cho biết runtime module mà class thuộc về.
- `Module.getLayer()` trả layer chứa named module đó; có thể là `null` với unnamed module.
- `Module.getClassLoader()` trả class loader định nghĩa module (có thể là `null` cho bootstrap loader).
- `Class.getClassLoader()` trả defining loader của class, cũng có thể là `null` cho lớp từ bootstrap loader.

Với plugin là named module do `child` tạo, `provider.getClass().getModule().getLayer() == child`. Với service API nằm ở `app.api` thuộc boot layer, `GreetingService.class.getModule().getLayer() == ModuleLayer.boot()`.

### 4.3. Tìm module và loader theo tên

```java
Module pluginModule = child.findModule("plugin.greeting")
    .orElseThrow();

ClassLoader pluginLoader = child.findLoader("plugin.greeting");
```

`ModuleLayer.findModule(name)` trả `Optional<Module>`, tìm trong layer hiện tại rồi parent layers theo thứ tự. `ModuleLayer.findLoader(name)` cũng tra cứu cả parent layers, nhưng:

- Trả trực tiếp `ClassLoader`; giá trị **`null` là hợp lệ** khi module thuộc bootstrap loader.
- Ném `IllegalArgumentException` nếu không có module tên đó ở layer hay các parent layers.
- **Không** trả `Optional<ClassLoader>`, chính vì phải có cách biểu diễn bootstrap loader bằng `null`.

Những API này giúp chẩn đoán module nào thực sự sở hữu class loader. Chúng không có nghĩa loader tự quyết định module reads hay exports.

### 4.4. Readability, exports, opens và class loader

Giả sử `plugin.greeting` cần lớp public từ `app.api`.

- `requires app.api` làm cho `plugin.greeting` **đọc** `app.api` theo graph đã resolve.
- `app.api` phải **exports** package chứa public API đến `plugin.greeting` (unqualified hoặc qualified export phù hợp) để code plugin sử dụng type một cách hợp lệ.
- `opens` chủ yếu liên quan đến reflective access sâu; không thể dùng `opens` thay cho `exports` khi muốn compile module thông thường tham chiếu public type.
- Class loader phải thực sự tìm thấy bytecode phù hợp, nhưng **việc nạp được class không tự cấp quyền truy cập** nếu readability/export bị vi phạm.

Module API có `canRead(other)` và `isExported(package, other)` để quan sát quan hệ runtime. Loader có thể giúp tìm class, còn JVM vẫn thực thi module access rules. Điều này khác classpath/unnamed module, nơi mô hình truy cập mặc định rộng hơn.

### 4.5. Có thể có các module cùng tên ở các layer khác nhau

Một host có thể có hai layer riêng, mỗi layer định nghĩa một module tên `plugin.greeting` (với loader tách biệt) để phục vụ hai bộ plugin/version. Hai đối tượng `java.lang.Module` ấy **không phải một module runtime duy nhất**. Class có cùng fully qualified name do hai loader khác nhau định nghĩa cũng không mặc định có cùng kiểu runtime.

Điều đó có ích cho side-by-side versions, nhưng có những giới hạn:

- API chung nên nằm trong module/loader ổn định mà các plugin đọc cùng một kiểu.
- Không ép kiểu object của version A sang class của version B nếu defining loader khác nhau.
- Không cho version cũ giữ thread, TCCL, static cache hoặc listener làm loader không thể được thu gom.
- `ModuleLayer` mới không tự chuyển trạng thái và không tự dừng code cũ.

## 5. Ví dụ Java 17+: từ Configuration đến ModuleLayer và provider runtime

Chương trình dưới đây xây ba module:

1. **`app.api`:** contract `GreetingService`.
2. **`app.host`:** chương trình khởi động, chạy ở **boot layer**, biết contract và cần service qua `uses`.
3. **`plugin.greeting`:** một named module nằm trong **JAR riêng**, được host resolve và đưa vào một **child layer** lúc chạy.

Mục tiêu là nhìn thấy trực tiếp: `Configuration` resolve provider module, `ModuleLayer` định nghĩa nó, `Module` gắn với layer mới, `ClassLoader` được ánh xạ cho provider. Chương trình dùng `ServiceLoader.load(layer, ...)` để gọi provider, kiểm chứng contract chung vẫn tương thích giữa layer cha và con.

### 5.1. Cấu trúc thư mục

```text
demo/
├── src/
│   ├── app.api/
│   │   ├── module-info.java
│   │   └── app/api/GreetingService.java
│   ├── app.host/
│   │   ├── module-info.java
│   │   └── app/host/Main.java
│   └── plugin.greeting/
│       ├── module-info.java
│       └── plugin/greeting/HelloGreeting.java
├── mods/                       # thư mục output biên dịch
└── dist/plugins/               # nơi đặt JAR module plugin
```

Các file `module-info.java` phải được biên dịch cùng các lớp của đúng module. Bước tạo `mods` và `dist` nằm ở phần lệnh PowerShell.

### 5.2. Module API chung

**`src/app.api/module-info.java`**

```java
module app.api {
    exports app.api;
}
```

**`src/app.api/app/api/GreetingService.java`**

```java
package app.api;

public interface GreetingService {
    String greet(String name);
}
```

`exports app.api` cho phép các named modules đọc `app.api` và dùng interface công khai này. Contract nằm ở một module được host đưa vào boot layer, tránh mỗi plugin có một bản sao `GreetingService` được loader riêng định nghĩa.

### 5.3. Module provider riêng

**`src/plugin.greeting/module-info.java`**

```java
module plugin.greeting {
    requires app.api;
    provides app.api.GreetingService
        with plugin.greeting.HelloGreeting;
}
```

**`src/plugin.greeting/plugin/greeting/HelloGreeting.java`**

```java
package plugin.greeting;

import app.api.GreetingService;

public final class HelloGreeting implements GreetingService {
    public HelloGreeting() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Provider có public constructor không tham số, thích hợp cho minh họa SPI. Package `plugin.greeting` **không được exports** ra ngoài chỉ vì module dùng `provides`; host không cần truy cập class triển khai trực tiếp mà chỉ cần nhìn nó qua contract `GreetingService`.

### 5.4. Host module và chương trình tạo child layer

**`src/app.host/module-info.java`**

```java
module app.host {
    requires app.api;
    uses app.api.GreetingService;
}
```

`uses` khai báo rằng host là người tiêu thụ service. Trong named module, khi gọi `ServiceLoader`, caller module cần khai báo service được dùng theo cơ chế JPMS.

**`src/app.host/app/host/Main.java`**

```java
package app.host;

import app.api.GreetingService;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.module.ResolvedModule;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {
    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: Main <plugin-modular-jar>");
        }

        // (1) Boot layer đã có app.host và app.api.
        ModuleLayer boot = ModuleLayer.boot();

        // (2) Cho resolution quan sát JAR modular plugin.
        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));

        // (3) Resolve tên module plugin và các requires liên quan.
        Configuration cf = boot.configuration().resolve(
            finder,
            ModuleFinder.of(),
            Set.of("plugin.greeting")
        );

        boolean inNewConfig = cf.modules().stream()
            .map(ResolvedModule::name)
            .anyMatch("plugin.greeting"::equals);

        // (4) Định nghĩa child layer; một loader MỚI cho module mới.
        ModuleLayer child = boot.defineModulesWithOneLoader(
            cf,
            ClassLoader.getSystemClassLoader()
        );

        // (5) Runtime Module và loader được ánh xạ.
        Module pluginModule = child.findModule("plugin.greeting")
            .orElseThrow();
        ClassLoader mappedLoader = child.findLoader("plugin.greeting");

        // (6) ServiceLoader dùng layer này để tìm/tạo provider.
        GreetingService provider = ServiceLoader
            .load(child, GreetingService.class)
            .findFirst()
            .orElseThrow(() -> new IllegalStateException(
                "No GreetingService provider in layer"));

        System.out.println("Config parent is boot: "
            + (cf.parents().get(0) == boot.configuration()));
        System.out.println("Resolved plugin in config: "
            + inNewConfig);
        System.out.println("Plugin belongs to child layer: "
            + child.modules().contains(pluginModule));
        System.out.println("Provider module is plugin module: "
            + (provider.getClass().getModule() == pluginModule));
        System.out.println("API module belongs to boot: "
            + (GreetingService.class.getModule().getLayer() == boot));
        System.out.println("Provider loader is mapped loader: "
            + (provider.getClass().getClassLoader() == mappedLoader));
        System.out.println("Plugin loader differs from system loader: "
            + (mappedLoader != ClassLoader.getSystemClassLoader()));
        System.out.println(provider.greet("JPMS"));
    }
}
```

Đoạn trên là **chương trình hoàn chỉnh** cho Java 17+. Ý nghĩa từng thao tác:

1. `boot` là layer đã có khi host được khởi chạy dưới dạng named module.
2. `finder` quan sát JAR module plugin được chỉ định qua tham số.
3. `cf` chứa resolved module `plugin.greeting`; `app.api` được tìm từ parent configuration do host đã đưa vào boot.
4. `child` định nghĩa runtime module mới; `defineModulesWithOneLoader` tạo **loader mới** có system loader làm cha.
5. `child.findModule(...)` trả runtime `java.lang.Module`; `child.findLoader(...)` trả loader thực sự được ánh xạ.
6. `ServiceLoader.load(child, GreetingService.class)` tìm provider trong child layer và các layer cha có liên quan; với demo chỉ có một provider được khai báo ở plugin. `findFirst()` tạo instance provider rồi gọi qua API chung.

`ServiceLoader` **không** tự gọi method nghiệp vụ như `start`/`stop`; ví dụ này chỉ thực hiện thao tác `greet` để tập trung vào sự khác biệt giữa configuration, layer, module và loader.

### 5.5. Biên dịch trên Windows PowerShell (JDK 17+)

Đứng tại thư mục `demo`; cần `java`, `javac` và `jar` trong `PATH`:

```powershell
# Tạo API module trước.
New-Item -ItemType Directory -Force mods/app.api | Out-Null
javac -encoding UTF-8 -d mods/app.api src/app.api/module-info.java src/app.api/app/api/GreetingService.java

# Host cần đọc API đã biên dịch.
New-Item -ItemType Directory -Force mods/app.host | Out-Null
javac -encoding UTF-8 --module-path mods/app.api -d mods/app.host src/app.host/module-info.java src/app.host/app/host/Main.java

# Provider cũng cần API, nhưng không cần host implementation.
New-Item -ItemType Directory -Force mods/plugin.greeting, dist/plugins | Out-Null
javac -encoding UTF-8 --module-path mods/app.api -d mods/plugin.greeting src/plugin.greeting/module-info.java src/plugin.greeting/plugin/greeting/HelloGreeting.java

# Đóng modular JAR, bao gồm module-info.class.
jar --create --file dist/plugins/plugin.greeting.jar -C mods/plugin.greeting .

# Chỉ API và host ở module path khởi động.
# Host tự tạo ModuleFinder cho plugin JAR lúc chạy.
java --module-path 'mods/app.api;mods/app.host' --module app.host/app.host.Main dist/plugins/plugin.greeting.jar
```

Lưu ý dấu chấm phẩy `;` trong module path của **Windows**; đặt trong dấu nháy để PowerShell giữ nguyên một argument. Trên Linux/macOS dùng dấu hai chấm `:`, ví dụ `--module-path 'mods/app.api:mods/app.host'`. `dist/plugins/plugin.greeting.jar` không được đưa vào module path lúc khởi động; nó là nguồn dành cho `ModuleFinder` của host.

**Stdout dự kiến, chính xác:**

```text
Config parent is boot: true
Resolved plugin in config: true
Plugin belongs to child layer: true
Provider module is plugin module: true
API module belongs to boot: true
Provider loader is mapped loader: true
Plugin loader differs from system loader: true
Hello, JPMS!
```

Chương trình dùng `boolean` và chuỗi cố định để stdout không phụ thuộc vào `ClassLoader.toString()`, thứ tự của `Set` hoặc cách JVM đặt tên lớp loader. Nếu chạy bằng JDK 17 với cấu trúc và lệnh đúng như trên, những dòng này minh họa các quan hệ sẽ quan sát được.

### 5.6. Đọc kết quả dưới góc nhìn API

`Config parent is boot: true` chứng minh configuration mới được xây trên configuration của boot layer. `Resolved plugin in config: true` cho thấy module plugin đã được resolve trong configuration mới.

`Plugin belongs to child layer: true` chứng minh đối tượng `Module` của plugin thuộc tập `child.modules()`; nó không chỉ được tìm qua parent layer. `Provider module is plugin module: true` cho thấy class thực thi provider đúng là thành viên runtime module đó.

`API module belongs to boot: true` cho thấy service contract đến từ module cha, tránh trùng định nghĩa `GreetingService` giữa host và plugin. `Provider loader is mapped loader: true` và `Plugin loader differs from system loader: true` chứng minh API `defineModulesWithOneLoader` tạo loader mới và ánh xạ plugin vào nó; tham số `parentLoader` không trở thành loader của plugin.

Cuối cùng, `Hello, JPMS!` chứng minh host lấy được provider qua `ServiceLoader.load(child, GreetingService.class)` và gọi method qua service contract chung.

### 5.7. Thử trường hợp lỗi

**Không tìm thấy JAR hoặc sai tên module:** thay tham số bằng đường dẫn thiếu file, hoặc đổi roots từ `plugin.greeting` thành tên không tồn tại. Resolution có thể thất bại với `FindException` hoặc lỗi liên quan khi module không quan sát được; `ModuleFinder` không tự tải JAR thiếu từ Maven Central.

**Không có `requires app.api`:** provider implementation đang tham chiếu `app.api.GreetingService`; khi biên dịch named module sẽ có lỗi không đọc được package/module, trừ khi cấu hình bổ sung làm thay đổi điều kiện. Điều này chứng minh readability là thuộc tính module graph, không phải việc class loader nhìn thấy file `GreetingService.class`.

**Không có `exports app.api`:** host/plugin không thể truy cập public interface từ named module khác theo quy tắc truy cập JPMS thông thường, dù module API đã được resolve.

**Không khai báo `provides`:** plugin vẫn có thể được resolve và định nghĩa trong layer, nhưng `ServiceLoader` sẽ không thấy provider qua module declaration. Đây là ví dụ rõ ràng rằng “module tồn tại trong layer” và “service đã được đăng ký” là hai khái niệm khác nhau.

**Không khai báo `uses` ở host:** lời gọi `ServiceLoader` từ named host module có thể bị `ServiceConfigurationError` do caller module không khai báo sử dụng service. Dù class loader và module graph hợp lệ, cơ chế SPI vẫn có ràng buộc riêng.

**Đổi sang `defineModulesWithManyLoaders`:** với một module plugin duy nhất, kết quả nghiệp vụ vẫn tương tự nhưng kiến trúc nạp class có khả năng khác; nếu có nhiều module mới, mỗi module trong configuration được gán một loader riêng. Không suy luận rằng module bị cách ly an toàn về quyền OS chỉ vì có loader riêng.

## 6. Đặt các API cạnh nhau để tránh nhầm

| API | Trả về | Điều thực sự diễn ra |
| --- | --- | --- |
| `ModuleFinder.of(paths...)` | `ModuleFinder` | Cho phép tìm module references từ artifact |
| `Configuration.resolve(...)` | `Configuration` | Giải quyết graph module và readability |
| `Configuration.resolveAndBind(...)` | `Configuration` | Resolve kèm service binding |
| `cf.modules()` | `Set<ResolvedModule>` | Xem modules được resolve **trực tiếp trong configuration** |
| `cf.findModule(name)` | `Optional<ResolvedModule>` | Tìm trong configuration và parent configs |
| `parent.defineModulesWithOneLoader(cf, loader)` | `ModuleLayer` | Tạo layer với **một loader mới** cho toàn bộ modules mới |
| `parent.defineModulesWithManyLoaders(cf, loader)` | `ModuleLayer` | Tạo layer với một loader mới **cho mỗi module** |
| `ModuleLayer.defineModulesWithOneLoader(cf, parents, loader)` | `ModuleLayer.Controller` | Tạo layer dạng static có thể dùng nhiều parent layers |
| `child.configuration()` | `Configuration` | Lấy configuration dùng để định nghĩa layer |
| `child.modules()` | `Set<Module>` | Lấy runtime modules trực tiếp trong layer |
| `child.findModule(name)` | `Optional<Module>` | Tìm module trong layer hoặc parent layers |
| `child.findLoader(name)` | `ClassLoader` (có thể `null`) | Tìm loader của runtime module, hoặc lỗi nếu module không tồn tại |
| `SomeClass.class.getModule()` | `Module` | Xác định runtime module chứa class |
| `module.getLayer()` | `ModuleLayer` (có thể `null`) | Xác định layer của named runtime module |
| `module.getClassLoader()` | `ClassLoader` (có thể `null`) | Loader định nghĩa module |
| `ServiceLoader.load(layer, Service.class)` | `ServiceLoader<Service>` | Tìm service providers trong layer đã được định nghĩa |

**Sai kiểu thường gặp:**

```java
// SAI: Configuration.modules() không trả về Set<Module>.
// Set<Module> wrong = cf.modules();

// ĐÚNG:
Set<ResolvedModule> description = cf.modules();
Set<Module> runtimeModules = child.modules();
```

Đoạn này là minh họa, giả sử `cf` và `child` được khai báo và đã import `Set`, `ResolvedModule`. `ResolvedModule` khác `Module` về cả ý nghĩa lẫn kiểu dữ liệu.

Một lỗi khác:

```java
// SAI: truyền cấu hình có parent không khớp với layer receiver.
// ModuleLayer unrelated = ...;
// unrelated.defineModulesWithOneLoader(cf, someLoader);

// ĐÚNG: dùng parent layer tương ứng với parent Configuration.
ModuleLayer child = boot.defineModulesWithOneLoader(
    cf, ClassLoader.getSystemClassLoader());
```

Đoạn trên có `boot`, `cf` lấy từ quá trình chuẩn bị trước; câu sai chỉ là phản ví dụ. Nếu có **nhiều parent configurations**, dùng phương thức static nhận `List<ModuleLayer>` tương ứng đúng thứ tự và làm việc qua `Controller`.

## 7. Các tình huống thiết kế ở hệ thống plugin thực tế

### 7.1. Một plugin module đơn giản

Host có thể giữ `app.api` và `app.host` trong boot layer, đưa một `plugin.greeting` vào child layer. `requires app.api` và `exports app.api` bảo đảm implementation nhìn thấy API. `ServiceLoader.load(child, Service.class)` chọn provider, host tự quản lý hợp đồng nghiệp vụ.

Ưu điểm: cấu trúc rõ ràng, không thêm toàn bộ plugin vào module path lúc JVM khởi động. Hạn chế: vẫn cần xử lý version, dependency, metadata, lỗi nạp module, khởi tạo provider, logging, shutdown và class loader leaks.

### 7.2. Nhiều plugin cùng chia sẻ một thư viện phụ thuộc

Giả sử `plugin.report` và `plugin.export` đều đọc `lib.common`. Có thể resolve `lib.common` cùng configuration mới hoặc đưa thư viện chung lên parent layer ổn định, tùy khả năng tương thích và chính sách nâng cấp. Chọn `defineModulesWithOneLoader` sẽ đặt các module mới vào **cùng một loader**; chọn `defineModulesWithManyLoaders` cấp loader riêng.

Không có một lựa chọn luôn tốt cho mọi ứng dụng: loader riêng giúp phân tách tên lớp và lifecycle tốt hơn, nhưng đòi quản lý chuyển giao kiểu, context và dependency cẩn thận. Cả hai đều phải tôn trọng `requires`/`exports` và các ràng buộc package của JPMS.

### 7.3. Hai phiên bản plugin cùng lúc

Tạo hai child layers từ cùng một boot layer, mỗi layer resolve một version khác của `plugin.greeting` từ JAR tương ứng (nếu cấu hình và identity cho phép). Mỗi layer có runtime `Module`/loader riêng. Host có thể chuẩn bị bản mới, health-check, sau đó chuyển traffic trước khi dừng bản cũ.

**Không** chuyển trực tiếp instance implementation class của version cũ sang nơi kỳ vọng implementation class của version mới; hai class trùng tên nhưng do loader khác định nghĩa không tự tương thích. Giữ contract/DTO ở module chung hoặc chuyển state qua định dạng trung lập.

### 7.4. Một layer có nhiều parent layers

Một plugin có thể cần module ở hai nhánh layer. API static:

```java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithManyLoaders(
        childConfiguration,
        List.of(parentLayerA, parentLayerB),
        ClassLoader.getSystemClassLoader()
    );
ModuleLayer child = controller.layer();
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. `childConfiguration` phải có parent configurations tương ứng **chính xác, cùng thứ tự** với `List.of(parentLayerA, parentLayerB)`. API instance `parentLayerA.defineModulesWithManyLoaders(...)` chỉ dùng khi configuration có đúng một parent. `Controller` cung cấp những khả năng điều chỉnh runtime như thêm read/export/open edges theo giới hạn của API; nó không thay đổi việc runtime cần quản lý plugin lifecycle.

### 7.5. Cần resource hoặc reflection của plugin

Nếu host muốn đọc resource từ named module, phải chú ý quy tắc đóng gói resource và module openness. `ClassLoader.getResourceAsStream(...)` không bảo đảm đọc được mọi resource từ named module do resource có thể bị encapsulated; dùng API `Module.getResourceAsStream` hoặc resource API từ code ở đúng module khi phù hợp.

Nếu framework cần deep reflection vào package của plugin, chỉ có `requires` và `exports` có thể không đủ; cần `opens` đúng đối tượng được phép truy cập. Mở mọi package không kiểm soát làm yếu đi ranh giới encapsulation của module.

### 7.6. Service discovery không tương đương module resolution

Một module có thể được resolve và định nghĩa trong layer nhưng không đăng ký `provides` cho service nào; lúc ấy `ServiceLoader` không có provider. Ngược lại, service declaration có thể hợp lệ ở metadata nhưng việc tạo instance lỗi do implementation hoặc dependency. Vì vậy cần phân biệt rõ:

1. **Module được quan sát:** `ModuleFinder` có tìm thấy artifact không?
2. **Module được resolve:** `Configuration` có chứa `ResolvedModule` phù hợp không?
3. **Module được định nghĩa:** `ModuleLayer` đã tạo runtime `Module` chưa?
4. **Class được nạp:** class loader đã định nghĩa class cần dùng chưa?
5. **Provider được tạo:** `ServiceLoader`/factory có tạo instance thành công không?
6. **Plugin sẵn sàng:** host đã kiểm tra cấu hình, phụ thuộc nghiệp vụ và gọi lifecycle start chưa?

Không gọi sáu trạng thái đó là một sự kiện duy nhất “plugin đã load”.

## 8. Chẩn đoán lỗi theo ranh giới

| Thời điểm | Triệu chứng/API lỗi | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- | --- |
| Finder | Không thấy root module | Sai path/JAR; không có module-info; sai module name | Kiểm tra JAR với `jar --describe-module`, path và tên |
| Resolve | `FindException` | Module gốc hoặc dependency không quan sát được | Kiểm tra finder trước/sau, parent configs, `requires` |
| Resolve | `ResolutionException` | Đồ thị không nhất quán; package/readability xung đột hoặc các ràng buộc resolution không hợp lệ | Xem tên module/package và quan hệ đọc |
| Define layer | `IllegalArgumentException` | Parent của `Configuration` không khớp với layer(s) được truyền | Tạo cf từ đúng parent.configuration(), đúng thứ tự |
| Define layer | `LayerInstantiationException` | Xung đột package/loader, module Java đặc biệt hoặc ánh xạ loader không hợp lệ | Xem policy one/many/custom loaders và module packages |
| Class link/load | `ClassNotFoundException` / `NoClassDefFoundError` / `LinkageError` | Dependency bị thiếu, binary không tương thích, loader map sai | Kiểm tra artifact, module graph, version và class loaders |
| Java access | `IllegalAccessError` hoặc lỗi reflection | Thiếu `requires`, `exports` hoặc `opens` | Tách readability khỏi accessibility; sửa module descriptors |
| Service lookup | `ServiceConfigurationError` | `uses/provides` sai, provider constructor/class không hợp lệ | Kiểm tra khai báo module và implementation |
| Runtime | Không tìm thấy provider dù module đã có | Module có trong layer nhưng chưa đăng ký service hoặc chọn sai layer | Dùng `ServiceLoader.load(layer, ...)`, kiểm tra `provides` |
| Reload | Class cũ vẫn còn | Layer/loader/instance cũ còn tham chiếu; hiểu sai `reload()` | Quản lý version, stop, callback, thread và class loader |

Khi có vấn đề, in những thông tin **có thể kiểm chứng**, chẳng hạn module name, `cf.modules()`, `layer.modules()`, `module.getLayer()`, `module.getClassLoader()`, `layer.parents()` và runtime descriptor. Đừng in secret hoặc phụ thuộc vào chuỗi `toString()` của loader như một định danh ổn định.

### Lỗi thiết kế cần tránh

- **Nhầm `Configuration` với `ModuleLayer`:** có `ResolvedModule` chưa nghĩa JVM đã định nghĩa runtime module.
- **Nhầm `ResolvedModule` với `Module`:** chúng là hai kiểu và hai giai đoạn khác nhau.
- **Nhầm parent layer với parent class loader:** một bên là đồ thị module, bên kia là cơ chế delegation nạp class.
- **Cho rằng `defineModulesWithOneLoader(..., parentLoader)` dùng đúng loader truyền vào:** API **tạo loader mới**, nhận `parentLoader` làm cha.
- **Cho rằng `child.modules()` bao gồm tất cả modules của cha:** chỉ gồm runtime modules trực tiếp trong child; `findModule` mới tìm xuyên cha.
- **Cho rằng loader thấy bytecode là có thể dùng mọi public class:** vẫn phải tuân theo `requires` và `exports`; deep reflection cần `opens`.
- **Cho rằng cùng tên module/class ở hai layer là một identity:** lớp/module runtime và defining loader phải được xét đồng thời.
- **Cho rằng layer là ranh giới sandbox:** module graph và loader không tự cô lập quyền tiến trình; plugin không tin cậy cần ranh giới process/OS phù hợp.
- **Cho rằng định nghĩa layer tự khởi động/dừng plugin:** host vẫn phải thực thi lifecycle nghiệp vụ.

## 9. Checklist khi thiết kế ModuleLayer cho plugin

- [ ] Xác định rõ contract module ở layer ổn định và provider modules cần nạp động.
- [ ] Khai báo `module-info.java` chính xác: `requires`, `exports`, `uses`, `provides`, `opens` khi cần.
- [ ] Dùng `ModuleFinder` để quan sát đúng modular JAR/đường dẫn và xác minh nguồn.
- [ ] Giải quyết `Configuration` dựa trên đúng parent configurations; phân biệt `resolve` với `resolveAndBind`.
- [ ] Kiểm tra `ResolvedModule` và đồ thị `reads` trước khi định nghĩa layer nếu cần chuẩn đoán dependency.
- [ ] Chọn one/many/custom loader mapping theo package, dependency và nhu cầu nâng cấp.
- [ ] Phân biệt parent layer, parent configuration và parent class loader.
- [ ] Sau khi tạo layer, kiểm tra `ModuleLayer.modules()`, `Module.getLayer()` và `findLoader()` thay vì đoán.
- [ ] Chọn provider qua service contract và `ServiceLoader.load(layer, ...)`; không nhầm provider discovery với instance readiness.
- [ ] Quản lý start, invocations, stop, cleanup và tham chiếu loader cũ trong plugin manager; không xem `ServiceLoader.reload()` là hot swap.

**Tài liệu Java SE 17 chính thức:** [`Configuration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html), [`ResolvedModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ResolvedModule.html), [`ModuleFinder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html), [`ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html), [`Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html), [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).

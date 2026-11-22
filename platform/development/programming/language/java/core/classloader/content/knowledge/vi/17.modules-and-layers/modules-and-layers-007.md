# ModuleFinder, Configuration và giải quyết phụ thuộc module trong Java 17

## 1. Bức tranh tổng thể: tìm module khác với giải quyết module và nạp class

Từ Java 9, Java Platform Module System (JPMS) bổ sung khái niệm **named module**, **module descriptor**, **module graph** và **module layer**. Khi xây ứng dụng modular hoặc plugin có module riêng, thường cần phối hợp ba thành phần:

1. **`ModuleFinder`** trả lời: “Trong một nguồn module có những module nào có thể quan sát được, và descriptor của chúng là gì?”
2. **`Configuration`** trả lời: “Với một nhóm root modules và các quan hệ `requires`, tập module nào được giải quyết thành một đồ thị phụ thuộc hợp lệ?”
3. **`ModuleLayer`** trả lời: “Các resolved modules này sẽ trở thành runtime modules trong layer nào và được loader nào định nghĩa class?”

Có thể diễn đạt thành một pipeline:

```text
Module artifacts (exploded modules / modular JARs / automatic modules)
                         |
                         v
                   ModuleFinder
                   find / findAll
                         |
                         v
            ModuleReference + ModuleDescriptor
                         |
                         v
       Configuration.resolve / resolveAndBind
       + Parent configuration + Root module names
                         |
                         v
             Resolved module graph
                         |
                         v
             ModuleLayer definition
       + mapping module -> ClassLoader
                         |
                         v
        Runtime Class<?> / services / reflective API
```

**Quan trọng:** một module được `ModuleFinder` tìm thấy **chưa có nghĩa** nó được resolve. Một module đã nằm trong `Configuration` **chưa có nghĩa** class của nó đã được load hay `<clinit>` đã chạy. Cấu hình chỉ mô tả module graph, còn class loading/linking/initialization là các hoạt động JVM tiếp theo.

Bài này tập trung vào cơ chế **khám phá module**, **giải quyết phụ thuộc theo descriptor**, **service binding** và **biến configuration thành layer thực thi**, đồng thời phân biệt chúng với Maven/Gradle dependency resolution, class loader delegation và Java access control.

## 2. Module descriptor: nguồn thông tin cho dependency graph

Một named module được khai báo trong `module-info.java`. Ví dụ:

```java
module m.extension {
    requires m.core;
    exports plugin;
}
```

Các directive phổ biến:

| Directive | Ý nghĩa |
|---|---|
| `requires m.core;` | Module hiện tại yêu cầu `m.core`; tạo dependency/readability theo JPMS |
| `requires transitive m.core;` | Dependency được truyền tiếp về khả năng đọc cho module phụ thuộc vào module hiện tại |
| `requires static m.optional;` | Dependency bắt buộc tại compile time, có tính tùy chọn tại runtime theo quy tắc `requires static` |
| `exports plugin;` | Cho phép truy cập public types trong package `plugin` từ các module đọc được module này |
| `exports internal to m.friend;` | Qualified export chỉ tới module được nêu |
| `opens model to m.serializer;` | Cho phép deep reflection vào package `model` tới module cụ thể |
| `uses api.Greeter;` | Module tiêu thụ service `api.Greeter` |
| `provides api.Greeter with impl.DefaultGreeter;` | Module khai báo một service provider implementation |

`module-info.java` được biên dịch thành **`module-info.class`**. `ModuleFinder` đọc metadata module và cung cấp **`ModuleReference`**, từ đó lấy `ModuleDescriptor`. Descriptor mô tả requires/exports/opens/uses/provides, tên, các packages và thông tin module liên quan; nó **không chứa sẵn các instance provider** và không tự chạy code trong module.

Ví dụ minh họa khi đã có `ModuleReference reference`:

```java
java.lang.module.ModuleDescriptor descriptor =
        reference.descriptor();

System.out.println(descriptor.name());
descriptor.requires().forEach(System.out::println);
```

Đây là **snippet**, không phải ứng dụng chạy độc lập; `reference` phải lấy từ một `ModuleFinder`. `descriptor.requires()` trả metadata của các dependencies được khai báo, chưa chắc tất cả đã được resolve trong configuration hiện tại.

### Module name không phải Java package name

Tên module như `m.extension` là tên của một named module. Package `plugin` là nơi đặt class `plugin.Worker`. Binary name của class này là `plugin.Worker`. JPMS resolution dùng **module names**, còn class loading dùng **class names** qua các loaders.

Không được truyền `"plugin.Worker"` làm tên root cho `Configuration.resolve` khi root cần `"m.extension"`. Ngược lại, `Class.forName` dùng `"plugin.Worker"` chứ không nhận module name như một class name.

## 3. ModuleFinder là gì?

`java.lang.module.ModuleFinder` là interface dùng để **tìm observable modules** từ một nguồn cụ thể. Hai phương thức chính:

```java
Optional<ModuleReference> find(String name);
Set<ModuleReference> findAll();
```

- `find(name)` tìm một module theo **tên module**, trả `Optional<ModuleReference>`. Nếu không thấy, trả `Optional.empty()`.
- `findAll()` trả các module mà finder quan sát được; thứ tự của `Set` **không phải hợp đồng dùng làm thứ tự xử lý dependencies**.
- Một `ModuleReference` mô tả named module và cho phép runtime hoặc công cụ mở nội dung module qua `ModuleReader` trong điều kiện phù hợp.
- `ModuleFinder` **không phải class loader**; việc finder thấy descriptor chưa có `Class<?>` nào bắt buộc được JVM định nghĩa.

### Ba cách tạo ModuleFinder thường dùng

**Tìm module theo các đường dẫn đã cho:**

```java
ModuleFinder finder = ModuleFinder.of(
        Path.of("out/mods"),
        Path.of("libs/plugin-module.jar"));
```

Đây là snippet cần import `java.lang.module.ModuleFinder` và `java.nio.file.Path`. Finder có thể duyệt **exploded modules** hoặc **modular JARs** trong các đường dẫn thích hợp. Nếu đường dẫn không hợp lệ hoặc chứa metadata xung đột, thao tác tìm có thể thất bại theo contract.

**Tìm các system modules:**

```java
ModuleFinder system = ModuleFinder.ofSystem();
```

System finder cung cấp những system modules trong runtime image. Nó không đồng nghĩa với `ClassLoader.getSystemClassLoader()`: một bên là **module discovery**, một bên là **class loader object**.

**Một finder rỗng:**

```java
ModuleFinder empty = ModuleFinder.of();
```

Không truyền đường dẫn tạo finder không nhìn thấy module nào từ nguồn đường dẫn đó. Finder rỗng thường dùng ở tham số `after` khi muốn không cung cấp nguồn fallback bổ sung.

### ModuleFinder.of(path) là snapshot các class đã nạp?

**Không.** Finder làm việc với **artifact/module references**, không cung cấp registry `Class<?>` đã loaded. Nếu file JAR/module bị thay thế khi chương trình đang chạy, đừng giả định finder và một configuration/layer đã định nghĩa trước tự cập nhật toàn bộ graph hay class definitions.

Cơ chế plugin/hot reload thường cần **tạo finder/configuration/layer mới**, quản lý vòng đời layer/loader cũ và các tham chiếu tới class instances.

## 4. ModuleReference và ModuleDescriptor: biết module trước khi có Class<?>

Khi `finder.find("m.extension")` trả một `ModuleReference`:

```java
var reference = finder.find("m.extension")
        .orElseThrow();

String moduleName = reference.descriptor().name();
```

Bạn có thể kiểm tra:

- Tên module `reference.descriptor().name()`.
- `requires` của module qua `reference.descriptor().requires()`.
- Các packages được `exports` và `opens`.
- Service usage/provision metadata.
- Tùy trường hợp, `reference.location()` trả một `Optional<URI>` trỏ tới nơi module được tìm, nhưng không phải mọi reference đều bắt buộc có location.

`ModuleReference` và `ModuleDescriptor` không tạo lớp:

```text
Finder tìm được: m.extension
Descriptor says: requires m.core
Configuration mới sẽ giải quyết phụ thuộc
Layer mới sẽ định nghĩa modules
JVM mới load class theo nhu cầu
```

Nếu mục tiêu chỉ là **phân tích module dependencies** hoặc xây công cụ kiểm tra module path, có thể dùng finder và descriptor mà không cần tạo layer chứa class thực thi.

### Automatic modules

Một ordinary JAR đặt trên module path có thể được nhận diện như **automatic module** theo quy tắc JPMS khi không có explicit `module-info.class`. Finder thích hợp có thể nhìn thấy automatic module và cung cấp descriptor tương ứng.

Tên automatic module có thể được ảnh hưởng bởi `Automatic-Module-Name` trong manifest, hoặc suy ra từ tên JAR theo quy tắc JDK. Đừng dựa mù quáng vào file name nếu muốn API module name ổn định.

Automatic module thường có quan hệ readability và export khác explicit modules. Nó có thể là công cụ chuyển tiếp nhưng **không thay thế** việc kiểm thử dependency graph, split packages và tính ổn định tên khi thiết kế plugin lâu dài.

## 5. Configuration là gì?

`java.lang.module.Configuration` biểu diễn **một cấu hình module đã được giải quyết**: tập các `ResolvedModule` cùng quan hệ `reads` và những **parent configurations** có liên quan.

Trong một ứng dụng Java thông thường:

```java
Configuration bootConfig =
        ModuleLayer.boot().configuration();
```

Boot configuration đã được runtime tạo khi launcher khởi động ứng dụng. Ta có thể tạo **child configuration** mới dựa trên boot configuration mà không làm boot configuration bị sửa đổi.

Khác biệt:

| Đối tượng | Chứa/biểu diễn | Không làm gì? |
|---|---|---|
| `ModuleFinder` | Các module references có thể quan sát ở nguồn | Không tự resolve graph |
| `ModuleReference` | Metadata/location/reader của một module | Không tự định nghĩa class |
| `ModuleDescriptor` | Module declaration: requires/exports/uses/... | Không kiểm tra toàn bộ graph |
| `Configuration` | Graph các resolved modules và parent configurations | Không tự khởi tạo runtime ModuleLayer |
| `ResolvedModule` | Module đã resolve với các read edges | Không phải `Class<?>` |
| `ModuleLayer` | Runtime modules được gán cho loaders và layer parents | Không tự bảo đảm class initialization |

Trong `Configuration`:

```java
Optional<ResolvedModule> module =
        configuration.findModule("m.extension");
```

Đây là snippet yêu cầu biến `configuration`. `findModule` có thể tìm module đã resolve trong configuration hoặc parent configurations theo contract; khi muốn biết module được giải quyết **trong chính** child configuration, kiểm tra tập `configuration.modules()` hoặc graph chi tiết thay vì suy từ mỗi `findModule`.

## 6. Configuration.resolve: từ roots đến dependency closure

Một phương thức quan trọng trên Java 17:

```java
Configuration child = parent.resolve(
        beforeFinder,
        afterFinder,
        Set.of("m.extension"));
```

Trong đó:

- `parent`: parent configuration, thường là `ModuleLayer.boot().configuration()`.
- `beforeFinder`: module finder ưu tiên khi cần tìm các root/dependency chưa được đáp ứng.
- `afterFinder`: finder bổ sung cho lookup theo quy tắc của resolution.
- `roots`: tên các module bắt đầu quá trình resolution, **không phải class names**.
- Kết quả: một **Configuration mới**, có các module resolution cần thiết và parent configuration; original parent không bị chỉnh sửa.

Ví dụ module:

```java
module m.extension {
    requires m.core;
}
```

Nếu root là `m.extension` và `m.core` không có sẵn trong parent configuration, resolver cần tìm một `ModuleReference` của `m.core` trong những nguồn finder áp dụng. Khi thành công, child configuration thường bao gồm cả `m.extension` lẫn `m.core`.

### Có phải chỉ các roots mới được resolve?

**Không.** Resolver đi theo các quan hệ `requires` cần thiết, không chỉ ghi đúng tên roots rồi dừng. Đó là ý nghĩa của dependency closure.

Ví dụ:

```text
Root: m.extension
     requires m.core
          requires java.logging
               requires java.base

Child configuration: m.extension, m.core
Parent boot configuration: java.base, java.logging, ...
```

Hình trên chỉ là **minh họa** khi `java.logging` đã ở parent configuration, không khẳng định mọi boot layer đều bắt buộc có `java.logging`. Tập resolved modules thực tế phụ thuộc launcher roots, runtime image, parent graph và finders.

**Không nên** yêu cầu resolver định nghĩa thêm một bản `java.base` vào child layer. Các modules đã được cung cấp bởi parent configuration có vai trò riêng trong graph; kiểm tra parent trước khi suy cần thêm bản sao.

### Vai trò của before/after finder

Resolver tìm module trong các nguồn theo thứ tự và quy tắc được `Configuration` định nghĩa, với **before finder**, các parent configurations và **after finder**. Hai finder không đơn giản là “classpath prepend” và “classpath append” cho mỗi `ClassLoader.loadClass`.

- `before` thường chứa artifacts plugin/module mà caller muốn resolve trước nguồn fallback.
- `after` có thể cung cấp mô-đun ứng dụng bổ sung khi một tên chưa được tìm trong các nguồn trước đó.
- Parent configuration là một graph **đã được resolve**, không phải một thư mục để tùy tiện quét lại.
- Khi module cùng tên xuất hiện nhiều nơi, quy tắc lookup/configuration có thể chọn một reference hoặc báo lỗi tùy tình huống. Đừng dựa vào thứ tự filesystem không rõ ràng.

Module path order và JPMS configuration **không** phải dependency solver kiểu Maven: Java resolver không tự chọn phiên bản “cao nhất” dựa trên semver hay tải artifact từ internet.

## 7. Những kiểm tra mà resolution thực hiện

Resolver phải xây được graph có cấu trúc module hợp lệ. Các vấn đề điển hình:

1. **Root module không tìm được**: tên `m.extension` được yêu cầu nhưng không nằm ở finder hoặc parent phù hợp.
2. **Requires dependency thiếu**: descriptor `requires m.core`, nhưng resolver không tìm được `m.core`.
3. **Module descriptors không hợp lệ**: tên module/package hoặc metadata không phù hợp, artifact lỗi.
4. **Xung đột package hoặc cấu trúc graph**: ví dụ readability dẫn tới các tình huống package mà module không được phép đọc từ hai nguồn gây mơ hồ, hoặc modules được gán không hợp lệ khi định nghĩa layer.
5. **Ràng buộc với parent**: khi có các parent configurations/layers, giải pháp phải tương thích với cấu trúc đã có, không tùy tiện thay các modules trong parent.
6. **Service binding**: khi yêu cầu `resolveAndBind`, tập module cần thiết có thể mở rộng để cung cấp providers cho services được sử dụng.

Các lỗi có thể được báo bằng `FindException`, `ResolutionException` hoặc lỗi khi định nghĩa layer như `LayerInstantiationException`. **Không gom mọi lỗi vào ClassNotFoundException**: nếu root module chưa được resolve, lỗi có thể xảy ra **trước khi** ứng dụng hỏi loader tìm bất kỳ class nào.

### Configuration không đảm bảo mọi class hoạt động được

Resolution kiểm tra module graph theo JPMS; nó không tự chứng minh tất cả method invocations, reflection, native libraries hay resources của chương trình chạy được.

Sau khi layer được định nghĩa, một class còn có thể gặp:

- `ClassNotFoundException` nếu loader không nhìn thấy binary name được yêu cầu.
- `NoClassDefFoundError` do dependency/linking hoặc initialization failure.
- `IllegalAccessError` khi bytecode access vi phạm module/package/member visibility.
- `InaccessibleObjectException` khi deep reflection bị chặn vì package không open.
- `ServiceConfigurationError` nếu provider configuration hoặc provider type không hợp lệ.

Vì vậy, **module resolution thành công là một bước cần, không phải chứng nhận toàn bộ ứng dụng chạy đúng**.

## 8. Ví dụ Java 17 hoàn chỉnh: ModuleFinder → Configuration → ModuleLayer

Ví dụ sau chạy với **hai explicit modules** trên một child layer:

- `m.core` export package `api` có class `api.Greeting`.
- `m.extension` `requires m.core` và export package `plugin` có class `plugin.Worker`.
- Host `LayerDemo` chạy từ class path, tự tạo `ModuleFinder`, resolve root `m.extension`, định nghĩa child `ModuleLayer` rồi gọi method public.

Điểm có thể quan sát: finder thấy **hai modules**, resolver chọn cả root và dependency, còn runtime tạo layer và nạp class từ đúng loader của layer.

### 8.1. Cây nguồn

```text
src/
  m.core/
    module-info.java
    api/
      Greeting.java
  m.extension/
    module-info.java
    plugin/
      Worker.java
  host/
    LayerDemo.java
out/
  mods/
    m.core/
    m.extension/
  host/
```

`out` là thư mục **sẽ được tạo bởi biên dịch**, không cần viết tay các class files.

### 8.2. Code của m.core

Tạo file `src/m.core/module-info.java`:

```java
module m.core {
    exports api;
}
```

Tạo file `src/m.core/api/Greeting.java`:

```java
package api;

public final class Greeting {
    public String text() {
        return "Hello modules";
    }
}
```

### 8.3. Code của m.extension

Tạo file `src/m.extension/module-info.java`:

```java
module m.extension {
    requires m.core;
    exports plugin;
}
```

Tạo file `src/m.extension/plugin/Worker.java`:

```java
package plugin;

import api.Greeting;

public final class Worker {
    public static String message() {
        return new Greeting().text();
    }
}
```

`m.extension` compile được vì `m.core` export package `api`, và `m.extension` có `requires m.core`. `plugin` được export để host code từ unnamed module gọi public member qua reflection. Nếu xóa `exports plugin`, việc tìm class vẫn có thể thành công nhưng invocation từ host có thể bị từ chối do module accessibility.

### 8.4. Host dùng finder và resolver

Tạo file `src/host/LayerDemo.java`:

```java
import java.lang.module.Configuration;
import java.lang.module.FindException;
import java.lang.module.ModuleFinder;
import java.lang.ModuleLayer;
import java.nio.file.Path;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        ModuleFinder finder = ModuleFinder.of(Path.of("out/mods"));

        Set<String> available = finder.findAll().stream()
                .map(ref -> ref.descriptor().name())
                .collect(Collectors.toCollection(TreeSet::new));
        System.out.println("Available: " + available);

        Configuration parent = ModuleLayer.boot().configuration();
        Configuration resolved = parent.resolve(
                finder, ModuleFinder.of(), Set.of("m.extension"));

        System.out.println("Resolved core: " +
                resolved.findModule("m.core").isPresent());
        System.out.println("Resolved extension: " +
                resolved.findModule("m.extension").isPresent());

        ModuleLayer layer = ModuleLayer.boot().defineModulesWithOneLoader(
                resolved, ClassLoader.getSystemClassLoader());

        ClassLoader extensionLoader = layer.findLoader("m.extension");
        Class<?> worker = Class.forName(
                "plugin.Worker", false, extensionLoader);

        System.out.println("Worker in child layer: " +
                (worker.getModule().getLayer() == layer));
        System.out.println("Invocation: " +
                worker.getMethod("message").invoke(null));

        try {
            parent.resolve(
                    finder, ModuleFinder.of(), Set.of("m.absent"));
            System.out.println("Unexpected missing root success");
        } catch (FindException expected) {
            System.out.println("Missing root rejected");
        }
    }
}
```

### 8.5. Biên dịch và chạy

Đứng ở thư mục chứa `src` và `out`, dùng JDK 17+.

Với Bash (Linux/macOS):

```bash
mkdir -p out/mods/m.core out/mods/m.extension out/host

javac -d out/mods/m.core \
  src/m.core/module-info.java \
  src/m.core/api/Greeting.java

javac --module-path out/mods -d out/mods/m.extension \
  src/m.extension/module-info.java \
  src/m.extension/plugin/Worker.java

javac -d out/host src/host/LayerDemo.java

java -cp out/host LayerDemo
```

Với Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/mods/m.core,out/mods/m.extension,out/host

javac -d out/mods/m.core src/m.core/module-info.java src/m.core/api/Greeting.java

javac --module-path out/mods -d out/mods/m.extension src/m.extension/module-info.java src/m.extension/plugin/Worker.java

javac -d out/host src/host/LayerDemo.java

java -cp out/host LayerDemo
```

**Lưu ý module path:** classpath chạy `LayerDemo` chỉ chứa `out/host`; `out/mods` được **chương trình chủ động đưa vào `ModuleFinder`**. Nếu đặt tất cả vào application class path, ví dụ sẽ không còn minh họa đúng việc host chủ động resolve một child configuration/layer.

### 8.6. Stdout chính xác

Với cấu trúc module sạch và lệnh trên:

```text
Available: [m.core, m.extension]
Resolved core: true
Resolved extension: true
Worker in child layer: true
Invocation: Hello modules
Missing root rejected
```

Các dòng giải thích cơ chế:

1. `Available: ...` — `ModuleFinder` thấy hai modules trong `out/mods`. `TreeSet` cho thứ tự tên ổn định khi in; `findAll()` tự nó không cam kết thứ tự.
2. `Resolved core: true` — `requires m.core` trong descriptor của `m.extension` đã được resolver theo để tìm dependency.
3. `Resolved extension: true` — root `m.extension` có mặt trong configuration.
4. `Worker in child layer: true` — khi định nghĩa layer rồi tìm loader `m.extension`, class `plugin.Worker` thuộc runtime module ở **child layer** đã tạo.
5. `Invocation: Hello modules` — call qua reflection thành công vì `plugin` exported, còn `Worker` phụ thuộc `api.Greeting` đã được giải quyết/cho phép truy cập.
6. `Missing root rejected` — `parent.resolve(..., Set.of("m.absent"))` không tìm thấy root `m.absent`, ném `FindException`, **không phải ClassNotFoundException**.

### 8.7. Điều gì thay đổi nếu bỏ requires hoặc exports?

- Bỏ `requires m.core` khỏi `m.extension/module-info.java` nhưng giữ `import api.Greeting`: Java compiler sẽ không cho code `m.extension` đọc `m.core` theo ordinary modular compilation; đó là lỗi **readability**, không phải “finder hỏng”.
- Bỏ `exports api` trong `m.core`: `m.extension` đọc module nhưng không thể import dùng public `api.Greeting` từ một package không exported; resolution thuần về tên module khác compile/access checking.
- Bỏ `exports plugin` khỏi `m.extension`: child module vẫn có thể được resolve và `Class.forName` vẫn có thể tìm `plugin.Worker` qua loader, nhưng reflective invocation từ unnamed host module có thể bị chặn vì package không được export.
- Sửa `requires m.core` thành `requires m.nonexistent`: nếu thiếu named module được yêu cầu, resolution/compile sẽ thất bại trước khi chạy ví dụ.
- Đổi root từ `"m.extension"` thành `"m.core"`: resolver không phải chọn `m.extension` nếu không có dependency/service binding nào dẫn tới nó; finder vẫn có thể **quan sát** extension nhưng configuration không bắt buộc chứa nó.

Các thay đổi này minh họa ba tầng độc lập: **module discovery**, **module resolution**, **accessibility khi compile/runtime**.

## 9. ModuleLayer: đưa Configuration vào JVM runtime

Một `Configuration` chỉ là module graph. Để ứng dụng dùng module như runtime modules, cần định nghĩa một **`ModuleLayer`** với loader mapping phù hợp.

Trong ví dụ:

```java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithOneLoader(
                resolved, ClassLoader.getSystemClassLoader());
```

Đây là code của `LayerDemo` sau khi biến `resolved` đã có.

- Parent layer là `ModuleLayer.boot()`.
- Configuration `resolved` được tạo với parent configuration tương ứng.
- Java tạo một loader mới để định nghĩa các modules trong child layer này; loader được truyền vào phương thức là **parent loader** cho loader mới, không phải loader mới sẽ được trả về trực tiếp.
- Các modules được định nghĩa trong child layer có thể lấy qua `layer.findModule(name)`.
- Loader phục vụ một module có thể lấy qua `layer.findLoader(moduleName)`.

Điểm dễ nhầm: `ClassLoader.getSystemClassLoader()` trong lời gọi `defineModulesWithOneLoader` **không có nghĩa** toàn bộ các class của `m.extension` đã trở thành class do system loader định nghĩa. API tạo mapping runtime module-to-loader cho layer; trong ví dụ, class `plugin.Worker` thuộc loader do layer mới tổ chức.

### One loader, many loaders, custom mapping

`ModuleLayer` cung cấp những cách định nghĩa module layer tùy nhu cầu:

- `defineModulesWithOneLoader`: nhiều modules trong configuration được định nghĩa với một loader mới.
- `defineModulesWithManyLoaders`: một cách sắp xếp với nhiều loaders, thường một loader cho từng module.
- `defineModules` với hàm ánh xạ tên module tới loader theo thiết kế của caller; cần tuân thủ ràng buộc về packages và loader ownership.

Không có lựa chọn nào “đúng nhất” cho mọi plugin. One-loader thuận tiện khi modules trong một plugin group cần chia sẻ loader; nhiều loaders/layers có thể hỗ trợ isolation khác nhau nhưng tăng độ phức tạp về identity, resources và lifecycle.

**Không nên dùng cùng binary name/package trong một loader/layer theo cách xung đột**. Nếu hai phiên bản của cùng module/library cần cùng tồn tại, có thể phải dùng layers/loaders khác nhau và giữ shared API types ổn định; JPMS không tự xử lý semantic version selection.

### Parent configuration phải phù hợp parent layer

Child configuration được resolve dựa trên `boot.configuration()` thì việc định nghĩa child layer cũng dùng `boot` làm parent trong ví dụ. Nếu dùng nhiều parent configurations hoặc layers, cần bảo đảm mapping và parent relationships phù hợp; không lấy một configuration bất kỳ rồi tùy ý gắn vào parent layer không tương ứng.

## 10. resolve và resolveAndBind khác nhau thế nào?

`Configuration.resolve(...)` và `Configuration.resolveAndBind(...)` đều làm **module resolution**, nhưng `resolveAndBind` còn thực hiện **service binding** để bổ sung provider modules có thể quan sát được khi cần.

Một khung kiến trúc:

```java
Configuration graph = parent.resolve(
        finder, ModuleFinder.of(), Set.of("m.client"));

Configuration graphWithProviders = parent.resolveAndBind(
        finder, ModuleFinder.of(), Set.of("m.client"));
```

Đây là **snippet minh họa** cần biến `parent` và `finder` được khai báo hợp lệ. Không yêu cầu đồng thời chạy hai phương thức trên cùng ứng dụng; dùng một phương thức tùy nhu cầu.

Giả sử module descriptors:

```java
module m.client {
    requires m.api;
    uses api.Greeter;
}
```

```java
module m.provider {
    requires m.api;
    provides api.Greeter with impl.GreeterImpl;
}
```

Hai khối này là **hai file module-info.java của hai module khác nhau**, không phải một chương trình biên dịch trong cùng file. Khi `m.client` là root, `resolve` thường chỉ đi theo các `requires` và không bắt buộc thêm `m.provider` nếu không có dependency khiến provider module được chọn. `resolveAndBind` có thể tìm các modules cung cấp service mà resolved modules sử dụng, đưa provider modules vào configuration rồi tiếp tục giải quyết phụ thuộc tương ứng.

**Service binding không instantiate providers.** Việc tạo provider instance thường được thực hiện sau đó qua `ServiceLoader` theo contract và layer/loader phù hợp. `uses` và `provides` là metadata trong descriptors; chúng không tự chạy constructor ở bước resolution.

### Dùng ServiceLoader sau khi định nghĩa layer

Với một `ModuleLayer layer` và interface `api.Greeter` đã accessible ở boundary:

```java
ServiceLoader<api.Greeter> providers =
        ServiceLoader.load(layer, api.Greeter.class);
```

Đây là snippet cần import `java.util.ServiceLoader` và có class/interface `api.Greeter`. Trong thực tế, class identity của service interface được truyền vào phải phù hợp với cách provider modules resolve interface đó. Nếu host và child layer có **hai runtime identities khác nhau cho cùng binary name API**, provider discovery hoặc ép kiểu có thể thất bại.

Overload `ServiceLoader.load(service)` dùng thread context class loader (TCCL), **không đồng nghĩa** với việc dùng provider modules trong layer vừa được tạo. Khi biết layer cần truy vấn, overload `ServiceLoader.load(layer, service)` thường diễn đạt mục tiêu rõ hơn.

### Có phải resolveAndBind luôn được dùng?

Không. Với ứng dụng modular trực tiếp và không có yêu cầu resolve thêm provider modules, `resolve` có thể là đủ. Với service-based plugin discovery, `resolveAndBind` có thể hữu ích nhưng cũng có thể đưa thêm modules vào graph; phải kiểm tra tập providers được quan sát và ranh giới plugin mong muốn.

Nếu dùng Java launcher thông thường với `--bind-services` hoặc module linker options khác, resolution/service binding trong quá trình khởi động có các cơ chế tương ứng, nhưng không nên suy rằng một lời gọi `ModuleFinder.findAll()` đã làm service binding.

## 11. requires, requires transitive và requires static

### requires: dependency trực tiếp

`requires m.core;` biểu diễn một dependency của module hiện tại vào `m.core`. Khi module hiện tại được resolve và dependency chưa có từ parent, resolver tìm module được yêu cầu trong các nguồn thích hợp.

### requires transitive: truyền readability

Giả sử:

```java
module m.facade {
    requires transitive m.core;
    exports facade;
}
```

```java
module m.client {
    requires m.facade;
}
```

Đây là descriptors minh họa của **hai modules riêng**. Khi `m.client` đọc `m.facade`, `requires transitive m.core` có thể truyền readability tới `m.core` theo JPMS. Điều đó **không** tự export mọi package của `m.core`: module `m.core` vẫn cần khai báo exports phù hợp để client dùng các public types của package được hỏi.

### requires static: dependency có tính tùy chọn ở runtime

Ví dụ:

```java
module m.extension {
    requires static m.optional;
}
```

`requires static` làm dependency cần thiết trong ngữ cảnh **compile time** nhưng không phải một yêu cầu cứng phải hiện diện ở runtime. Không được coi nó là “nếu thiếu thì Java tự tải từ Maven” hay “ngay cả khi thiếu vẫn dùng mọi class của optional module bình thường”.

Nếu code thật sự dùng class của optional module trong một execution path, vẫn cần kiểm tra module được cung cấp/đọc và class liên quan được resolve đúng khi path ấy chạy. Thiết kế optional feature phải có guard/fallback tương ứng.

### Vì sao phân biệt ba loại?

- Dependency graph không đơn thuần là danh sách tất cả JAR mà build tool đã tải.
- `requires` và `requires transitive` ảnh hưởng cách modules được resolve/read.
- `requires static` ảnh hưởng ngữ nghĩa dependency ở compile/runtime.
- `exports`/`opens` lại quyết định accessibility của packages, không được suy ra tự động từ `requires`.

## 12. ModuleFinder không giải quyết dependency versions kiểu Maven/Gradle

JPMS chủ yếu dùng **module name** làm định danh trong module configuration và quan hệ `requires`; nó **không phải** dependency manager chọn version theo range `[1.2,2.0)`, tải transitive artifacts từ repository hay thay thế lockfile.

Nếu có:

```text
libs/v1/m.core.jar
libs/v2/m.core.jar
```

và cả hai cung cấp cùng tên module `m.core`, không nên kỳ vọng `ModuleFinder` tự chọn “bản mới nhất” theo semantic version. Một configuration không được xây như danh sách hai modules độc lập trùng module name mà JPMS sẽ tự hài hòa.

Cách xử lý phụ thuộc trường hợp:

1. Chọn **một** version thống nhất khi cùng module phải được chia sẻ.
2. Thiết kế **plugin layers/loaders riêng** để cô lập implementations, đồng thời bảo đảm shared API types có identity chung.
3. Đổi tên package/module hợp lệ bằng **relocation/shading** nếu xây dựng artifact yêu cầu.
4. Tách process nếu cần cách ly state/native dependencies hay mức độ an toàn cao hơn.

Với named modules và nhiều layers, đừng bỏ qua module exports, readability và việc một class có thể được định nghĩa dưới loader nào. Classloader isolation không tự giải quyết mọi compatibility issue giữa các versions.

## 13. Lỗi thực tế trong module discovery, resolution và layer definition

### Lỗi 1: Module có trên disk nhưng ModuleFinder không thấy

Kiểm tra:

- Có đưa **đúng directory/JAR path** vào `ModuleFinder.of(Path...)` không?
- Nếu trỏ directory chứa nhiều module directories, cấu trúc đó có phải module-path entry đúng theo JDK không?
- JAR có `module-info.class` hoặc automatic-module metadata hợp lệ không?
- Module name thực tế có trùng tên bạn gọi `finder.find(name)` không?
- Có artifact xung đột module name hoặc format không hợp lệ khiến finder ném `FindException` không?

`findAll()` trả metadata, không phải classloader cache. Có thể in danh sách tên theo thứ tự ổn định để chẩn đoán:

```java
Set<String> names = finder.findAll().stream()
        .map(ref -> ref.descriptor().name())
        .collect(java.util.stream.Collectors.toCollection(
                java.util.TreeSet::new));
System.out.println(names);
```

Đây là snippet cần `finder` và `Set` import phù hợp.

### Lỗi 2: Root module không tìm thấy khi resolve

`Configuration.resolve` nhận roots là **module names**, không phải class names hoặc file paths. Nếu truyền `plugin.Worker` thay `m.extension`, root không đúng và resolver có thể ném `FindException`.

Khi một module yêu cầu module khác bị thiếu, cần cung cấp module đó trong before/after finder hoặc parent graph thích hợp, chứ không thể sửa bằng cách chuyển sang `Class.forName`.

### Lỗi 3: Dependency module đã resolve nhưng code không compile

Có thể do package không exported, không có `requires`/readability phù hợp, hoặc Java access modifiers. Đây không nhất thiết là lỗi `ModuleFinder`.

Ví dụ `m.extension` `requires m.core` nhưng `m.core` không export `api` thì `import api.Greeting` trong extension bị chặn. Chọn loader khác không thay module exports.

### Lỗi 4: Configuration thành công nhưng defineModules... thất bại

`Configuration` là graph metadata; `ModuleLayer` definition còn áp dụng ràng buộc classloader/layer mapping và package ownership. Một số lỗi chỉ bộc lộ khi gán modules cho loaders, ví dụ các module packages không thể cùng được định nghĩa hợp lệ trên loader được chọn.

Dùng `LayerInstantiationException` và message thực tế để xem ràng buộc nào bị vi phạm; không suy rằng mọi `ResolutionException` và `LayerInstantiationException` là một.

### Lỗi 5: findLoader không thấy module

`layer.findLoader("m.extension")` tra module theo layer đó; nếu module không nằm ở layer được hỏi, có thể ném `IllegalArgumentException`. Phân biệt `Configuration.findModule` (có thể xét parent configurations) với `ModuleLayer.findLoader` cần tên module thuộc phạm vi layer theo API.

Khi hệ plugin tạo nhiều layers, đừng luôn gọi `ModuleLayer.boot().findLoader(...)` để tìm loader của plugin trong child layer.

### Lỗi 6: Nạp class thành công nhưng reflection bị chặn

`Class.forName("plugin.Worker", false, pluginLoader)` có thể trả `Class<?>` nhưng việc gọi `getMethod(...).invoke(...)` vẫn phụ thuộc `exports` của package, Java modifiers và module access rules.

Cần xem:

- Caller module có đọc module đích không?
- Package của public class có export tới caller không?
- Nếu deep reflection vào private member, package có open đúng phạm vi không?
- Method/constructor có đúng signature và access modifier không?

`--add-exports` và `--add-opens` xử lý **quyền truy cập**, không thay thế module resolution khi root/dependency chưa được tìm thấy.

### Lỗi 7: Service provider không xuất hiện

Nếu chỉ dùng `resolve`, provider module **không nhất thiết** được chọn nếu không phải root hoặc required dependency. `resolveAndBind` có thể đưa service providers vào graph nếu descriptor `uses`/`provides` và nguồn finder phù hợp.

Sau khi định nghĩa layer, vẫn phải dùng `ServiceLoader` đúng API/layer và chia sẻ service interface type identity đúng cách.

## 14. Công cụ kiểm tra module graph

Trên JDK 17, có thể dùng:

```bash
java --list-modules
java --describe-module java.base
java --module-path out/mods --describe-module m.extension
```

Lưu ý `--describe-module` mô tả **module thấy được trong cấu hình launcher**; không phải mỗi child layer tạo sau đó đều tự được hiển thị như launcher root. Với custom layer, log/print `finder.findAll()`, `configuration.modules()` và `layer.modules()` trong chính chương trình thường sát ngữ cảnh hơn.

Có thể quan sát module resolution khi JVM khởi chạy app modular:

```bash
java --show-module-resolution --module-path mods -m m.app/app.Main
```

Đây là **lệnh minh họa**, cần `mods` chứa module `m.app` và main class `app.Main`. Nó không phải lệnh chạy ví dụ `LayerDemo` ở phần 8, vì `LayerDemo` cố ý tự resolve modules trong chương trình. Không nhầm launcher boot resolution với custom child configuration resolution.

Đối với class loading ở HotSpot:

```bash
java -Xlog:class+load=info -cp out/host LayerDemo
```

Log có thể rất dài; module discovery/resolution và class loading là hai cấp độ khác nhau. Chỉ nhìn một dòng class load không chứng minh toàn bộ module graph hoặc service binding đúng.

## 15. Bài tập tự kiểm tra

**Câu 1.** `ModuleFinder.find("m.extension")` có nghĩa `m.extension` đã được resolve vào configuration hiện tại chưa?

**Đáp án:** Chưa. Finder cho thấy module reference observable; resolver còn phải giải quyết roots/dependencies và kiểm tra graph.

**Câu 2.** Root `m.extension` có `requires m.core`. Nếu `m.core` có trong finder nhưng không nằm trong danh sách roots, resolver có chọn nó không?

**Đáp án:** Có, khi đó là dependency cần thiết và chưa được parent configuration cung cấp. Resolver theo các `requires` để tạo dependency closure.

**Câu 3.** `Configuration.resolve` có tự tạo class loader và chạy `static { ... }` của `plugin.Worker` không?

**Đáp án:** Không. Nó tạo module graph. Layer definition gán modules cho loaders; JVM class loading và initialization xảy ra về sau theo nhu cầu.

**Câu 4.** Vì sao ví dụ in `Available: [m.core, m.extension]` theo thứ tự chữ cái?

**Đáp án:** Code dùng `TreeSet` để sắp tên trước khi in; `ModuleFinder.findAll()` trả `Set` không bảo đảm thứ tự đó.

**Câu 5.** `m.extension` `requires m.core` nhưng `m.core` không export `api`. Đây là lỗi module không tìm thấy hay quyền truy cập package?

**Đáp án:** Chủ yếu là package accessibility trong modular compilation/bytecode access. Dependency module có thể đã resolved, nhưng public type trong package chưa exported tới client.

**Câu 6.** `resolveAndBind` khác `resolve` ở đâu?

**Đáp án:** `resolveAndBind` có bước service binding để tìm/bổ sung provider modules cho các services được dùng bởi resolved modules. Nó không tự instantiate provider objects.

**Câu 7.** Vì sao class `plugin.Worker` trong ví dụ thuộc child layer, không phải boot layer?

**Đáp án:** Host tạo child `Configuration` và định nghĩa child `ModuleLayer`, lấy loader qua `layer.findLoader("m.extension")` rồi load class của module đó.

**Câu 8.** Module đã tồn tại trên module path và finder nhìn thấy, nhưng không có `requires` hoặc root nào dẫn tới nó. Nó có nhất thiết xuất hiện trong `Configuration` không?

**Đáp án:** Không. Resolution chọn roots và dependencies (cùng providers khi service binding), không tự include mọi module finder quan sát.

**Câu 9.** Hai JAR cùng cung cấp module `m.core` bản khác nhau. JPMS có tự chọn “bản mới hơn” theo semver không?

**Đáp án:** Không. JPMS module resolution không phải Maven/Gradle dependency version resolver. Cần quản lý artifact/graph/loader architecture cụ thể.

**Câu 10.** Khi `parent.resolve(... Set.of("m.absent"))` không tìm thấy root, lỗi dự kiến là gì?

**Đáp án:** `FindException`, như ví dụ chạy được trong phần 8; khác `ClassNotFoundException` của class lookup.

## 16. Tóm tắt và tài liệu chính thức

**Năm mốc cần phân biệt:**

1. **Discover:** `ModuleFinder` tìm `ModuleReference` theo module name và module path/system image.
2. **Describe:** `ModuleDescriptor` cung cấp `requires`, `exports`, `opens`, `uses`, `provides` và metadata.
3. **Resolve:** `Configuration.resolve` tạo module graph từ roots, dependencies và parent configuration; `resolveAndBind` bổ sung service binding.
4. **Define:** `ModuleLayer` định nghĩa các resolved modules vào runtime với loader mapping phù hợp.
5. **Load/use:** `ClassLoader`/`Class.forName` lấy `Class<?>`; JPMS readability/exports/opens và Java access rules tiếp tục chi phối cách code sử dụng class/member.

**Tài liệu chính thức Java 17:**

- [Java SE 17 — ModuleFinder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html): `of`, `ofSystem`, `find` và `findAll`.
- [Java SE 17 — Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html): `resolve`, `resolveAndBind`, parent configurations, `findModule` và `modules`.
- [Java SE 17 — ModuleReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleReference.html) và [ModuleDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html): metadata của module.
- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): layer definition, loader mapping và `findLoader`.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): service providers trong module/layer.
- [JLS 17 — `7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens`, `uses` và `provides`.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): kiến trúc JPMS, launcher/module path và resolution.
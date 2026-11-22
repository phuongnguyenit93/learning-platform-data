# Dùng ModuleLayer mới cho nhóm plugin mới và hiểu giới hạn thay đổi layer đã tạo

## 1. Bài toán của plugin runtime với JPMS

Trong Java Platform Module System (JPMS), `ModuleLayer` là tập các named module đã được giải quyết (resolved), gắn với một `Configuration` và các classloader. Một layer có thể có một hoặc nhiều parent layer. Khi host cần bổ sung hoặc thay thế nhóm plugin **sau khi ứng dụng đã chạy**, phương án thích hợp là tạo **layer con mới**, thay vì cố sửa danh sách module bên trong layer hiện hữu.

Ví dụ host đang chạy plugin `report.plugin.v1`. Khi phát hành phiên bản `report.plugin.v2` hay triển khai nhóm provider mới, host có thể:

1. Đặt modular JAR mới vào kho artifact hoặc thư mục được phép tải.
2. Dùng `ModuleFinder` tìm module, tạo `Configuration` mới dựa trên parent configuration.
3. Định nghĩa **module layer mới** với classloader tương ứng.
4. Dùng `ServiceLoader.load(layer, Service.class)` khám phá provider trong layer đó.
5. Chuyển các yêu cầu **mới** sang registry/provider mới sau kiểm tra sức khỏe.
6. Dừng hoặc drain yêu cầu cũ, đóng tài nguyên và bỏ tham chiếu layer/loader cũ khi an toàn.

**Điểm mấu chốt:** đây là cơ chế *thay thế bằng cách tạo cấu hình/layer mới*, không phải chỉnh sửa in-place module graph của layer cũ.

## 2. Cần phân biệt module path, Configuration và ModuleLayer

| Khái niệm | Chức năng | Có tự thay đổi khi thêm JAR? |
| --- | --- | --- |
| Thư mục JAR / module path | Nguồn artifact cho `ModuleFinder` | File trên đĩa có thể thay đổi, nhưng Java không tự nạp lại |
| `ModuleFinder` | Tìm module descriptors từ nguồn đã chỉ định | Không phải watcher/hot-reload engine |
| `Configuration` | Mô tả module graph đã resolve (module names, requirements, readability) | Không thêm/bớt module sau khi resolve |
| `ModuleLayer` | Gắn configuration với runtime modules và classloaders | Không có API add/remove module tùy ý |
| `ServiceLoader` | Tìm provider phù hợp trong loader/layer | Một loader cần khám phá lại theo API; không biến module graph cũ thành graph mới |
| Registry của host | Quyết định provider nào xử lý request | Có thể thiết kế để thay đổi qua tham chiếu/phiên bản |

Java có các API điều chỉnh giới hạn như `Module.addReads`, `Module.addExports`, `Module.addOpens` cho các trường hợp được phép. Chúng **không tương đương** thêm module mới vào một `Configuration` hay thay bytecode của module đã định nghĩa. Không nên xem các API này là hot-swap module graph.

## 3. Ví dụ Java 17+: tạo layer riêng và khám phá plugin

Ví dụ gồm ba named module: `demo.api` chứa service contract; `demo.host` chạy ở boot layer; `demo.plugin` là provider được nạp từ thư mục `plugins/` vào **child layer**.

Cấu trúc:

```text
demo/
  src/
    demo.api/
      module-info.java
      demo/api/Greeter.java
    demo.host/
      module-info.java
      demo/host/Main.java
    demo.plugin/
      module-info.java
      demo/plugin/HelloGreeter.java
  plugins/
```

### 3.1. Contract module

`src/demo.api/module-info.java`:

```java
module demo.api {
    exports demo.api;
}
```

`src/demo.api/demo/api/Greeter.java`:

```java
package demo.api;

public interface Greeter {
    String id();
    String greet(String name);
}
```

### 3.2. Host module

`src/demo.host/module-info.java`:

```java
module demo.host {
    requires demo.api;
    uses demo.api.Greeter;
}
```

`src/demo.host/demo/host/Main.java`:

```java
package demo.host;

import demo.api.Greeter;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        Path pluginDir = Path.of("plugins");
        ModuleFinder pluginFinder = ModuleFinder.of(pluginDir);
        ModuleLayer parent = ModuleLayer.boot();

        Configuration configuration = parent.configuration().resolve(
                pluginFinder, ModuleFinder.of(), Set.of("demo.plugin"));

        ModuleLayer layer = parent.defineModulesWithOneLoader(
                configuration, ClassLoader.getSystemClassLoader());

        List<Greeter> plugins = ServiceLoader.load(layer, Greeter.class)
                .stream()
                .map(ServiceLoader.Provider::get)
                .toList();

        if (plugins.size() != 1) {
            throw new IllegalStateException(
                    "Expected one provider, got " + plugins.size());
        }

        Greeter greeter = plugins.get(0);
        System.out.println("Plugin: " + greeter.id());
        System.out.println(greeter.greet("Java"));
        System.out.println("Plugin layer is boot: "
                + (greeter.getClass().getModule().getLayer() == parent));
    }
}
```

Ở đây `resolve(pluginFinder, ModuleFinder.of(), roots)` dùng plugin finder làm **before finder**, empty after finder, còn parent configuration cung cấp các module được resolve trước đó (trong đó có `demo.api`). `defineModulesWithOneLoader` đưa các module **của configuration mới** vào một loader con có parent là system classloader. Với module API đã ở boot layer, plugin được tạo và dùng qua cùng `Greeter` class identity.

### 3.3. Provider module

`src/demo.plugin/module-info.java`:

```java
module demo.plugin {
    requires demo.api;
    provides demo.api.Greeter with demo.plugin.HelloGreeter;
}
```

`src/demo.plugin/demo/plugin/HelloGreeter.java`:

```java
package demo.plugin;

import demo.api.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {}

    @Override
    public String id() {
        return "hello";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Provider package không cần `exports` chỉ để được `ServiceLoader` khởi tạo qua khai báo `provides ... with ...`. Host không viết `requires demo.plugin`; phụ thuộc biên dịch chỉ hướng tới contract.

### 3.4. Compile, đóng gói và chạy

Trong thư mục `demo` trên shell bash, dùng JDK 17+:

```bash
mkdir -p mods plugins
javac --module-source-path src -d mods --module demo.api,demo.host,demo.plugin
jar --create --file plugins/demo.plugin.jar -C mods/demo.plugin .
java --module-path mods/demo.api:mods/demo.host --module demo.host/demo.host.Main
```

Output kỳ vọng:

```text
Plugin: hello
Hello, Java
Plugin layer is boot: false
```

Trên Windows, module path separator là `;`, ví dụ `--module-path "mods/demo.api;mods/demo.host"`. Quan trọng là **không thêm `demo.plugin` vào boot module path trong lệnh cuối**; provider JAR được đọc qua `ModuleFinder.of(Path.of("plugins"))` và nằm trong layer con. Trong lệnh biên dịch, `mods` là output gồm ba thư mục module.

**Vì sao kiểm tra `false`?** Provider thuộc named module `demo.plugin` được định nghĩa trong layer con; `greeter.getClass().getModule().getLayer()` không phải boot layer. Kết quả này chứng minh host đang sử dụng module ở layer mới, không phải bản provider vô tình xuất hiện trên classpath/boot module path.

## 4. Tạo layer mới cho phiên bản hoặc nhóm plugin tiếp theo

Giả sử host đang giữ một `ActivePlugins` registry tham chiếu provider của layer A. Khi plugin B được triển khai, quy trình thay thế có thể là:

```text
Release A                           Release B
Configuration A                     Configuration B
     |                                    |
ModuleLayer A                       ModuleLayer B
     |                                    |
Providers A                         Providers B
     |                                    |
active registry -------- atomic swap --> active registry
     |
drain A -> close A -> drop references
```

Trong ứng dụng, mỗi nhóm artifact/version nên có thư mục riêng, ví dụ `plugins/release-001/` và `plugins/release-002/`. Cách này giảm rủi ro `ModuleFinder` hoặc classloader đọc một JAR đang bị thay byte giữa chừng.

Pseudo-code Java minh họa điểm chuyển giao (không phải chương trình độc lập):

```java
record PluginSet(ModuleLayer layer, List<Greeter> providers) {}

AtomicReference<PluginSet> active = new AtomicReference<>();

void publish(PluginSet next) {
    PluginSet previous = active.getAndSet(next);
    // Điều phối để request đang dùng previous hoàn thành,
    // rồi gọi plugin stop/close và bỏ references.
}
```

Đoạn này cần các import, field và lifecycle implementation thích hợp; riêng `AtomicReference` **không tự bảo đảm drain**. Request đã lấy `previous` vẫn có thể đang gọi provider cũ. Muốn không dừng khi còn request, cần reference counting, lease, read-write coordination hoặc scheduler/quiescence thích hợp.

### Có thể reuse cùng module name ở layer khác không?

Trong nhiều thiết kế, **cùng module name có thể tồn tại trong các module layer khác nhau**, mỗi layer có configuration/runtime module identity và classloader riêng. Điều này hữu ích khi hai phiên bản plugin cùng có module name `demo.plugin`. Tuy nhiên phụ thuộc parent/layer relation và cách module resolution; không được đưa **hai bản cùng tên** vào **cùng một configuration** rồi kỳ vọng JVM chọn bản theo version. Tách artifact/version theo finder và tạo layer riêng.

Giữ service contract ở parent layer giúp cả provider mới và host dùng cùng API identity. Nếu mỗi plugin layer lại tự mang bản sao interface service, classloader/type identity có thể không tương thích và `ServiceLoader` không trả provider như mong đợi.

## 5. Những giới hạn của layer đã tạo

### 5.1. Không thêm/bớt named module trong layer hiện hữu

Không có API `layer.addModule(jar)` hoặc `layer.removeModule(name)`. Một layer sau khi được định nghĩa gắn với graph đã resolve. Thêm JAR vào thư mục `plugins/` **không tự đưa module mới vào layer A**. `ServiceLoader.reload()` chỉ reset cache khám phá của **ServiceLoader instance**, không khiến layer cũ có thêm module.

Muốn nhìn module mới, phải resolve configuration khác và define **layer khác**, hoặc dùng cơ chế classpath/classloader riêng nếu kiến trúc không dựa vào named modules.

### 5.2. Không thay thế class/bytecode đã nạp bằng cách sửa JAR

Class đã được định nghĩa bởi JVM không được cập nhật đơn giản khi file JAR bị ghi đè. Một module layer mới với classloader mới có thể nạp phiên bản mới, nhưng object cũ, class cũ và các request đang sử dụng chúng vẫn tồn tại nếu còn reference.

Ngay cả Java instrumentation/redefinition cũng có giới hạn riêng và không phải cơ chế thay đổi module graph của layer. Với plugin upgrade, hãy dùng new layer + lifecycle handoff thay vì giả định ghi đè file JAR là hot reload.

### 5.3. Ràng buộc module graph và classloader

Module resolution có thể thất bại với `FindException` nếu không tìm được module cần thiết hoặc `ResolutionException` khi graph xung đột. Layer definition có thể ném `LayerInstantiationException` nếu strategy mapping modules/classloaders không hợp lệ (ví dụ package conflicts theo loader).

Phân biệt các API:

- `defineModulesWithOneLoader`: các module trong configuration mới được đặt trên một loader; cần tránh package conflicts tương ứng.
- `defineModulesWithManyLoaders`: mỗi module trong configuration mới nhận loader riêng.
- `defineModules`: callback ánh xạ module name tới classloader; dùng khi cần kiểm soát loader cụ thể.

Không tùy tiện dùng `defineModulesWithManyLoaders` để “bỏ qua mọi split-package conflict”: resolver vẫn kiểm tra graph, và classloader design phải bảo đảm service contract/runtime type identity.

### 5.4. Layer không phải security sandbox

Code của mọi plugin chạy cùng JVM vẫn chia sẻ system properties, heap, thread pools, file/network permissions và native libraries; riêng module encapsulation/readability không cấp process permissions khác. Plugin chưa tin cậy cần tiến trình/container và OS restrictions riêng. Một layer khác cũng không bảo đảm plugin không làm JVM crash hoặc cạn tài nguyên.

### 5.5. Không có unload hoặc close(ModuleLayer) ngay lập tức

`ModuleLayer` **không triển khai `AutoCloseable`**, không có `close()` để dỡ toàn bộ module; garbage collection chỉ có thể thu hồi loader/class metadata khi không còn reference thích hợp. Threads, thread-context-classloader, ThreadLocal, singleton registry, static state ở parent loader, callbacks, schedulers và provider references có thể giữ layer cũ tồn tại.

Lifecycle nên gồm stop/close providers, hủy đăng ký listener, đóng executor/file/network resources, bỏ reference và kiểm tra memory leaks. Không hứa “unload thành công ngay” khi bỏ reference.

## 6. ServiceLoader trong nhiều layer

`ServiceLoader.load(layer, Service.class)` tìm provider trong layer chỉ định và các ancestor theo cơ chế API; không nên hiểu đây là cách chọn ngẫu nhiên tất cả providers từ **mọi layer ngang hàng**. Nếu host tạo hai sibling layers A và B, hãy quản lý registry riêng cho mỗi nhóm hoặc kết hợp một cách tường minh.

Ví dụ khi chuyển sang layer B:

```java
ServiceLoader<Greeter> loader = ServiceLoader.load(layerB, Greeter.class);
List<Greeter> selected = loader.stream()
        .map(ServiceLoader.Provider::get)
        .toList();
```

Đoạn minh họa này đặt trong method có `layerB` là `ModuleLayer` và import tương ứng. `ServiceLoader` giữ cache riêng; nó không biến layer A thành B. Khi cần ưu tiên provider, hãy áp policy của host trên tập provider đã load, không dựa vào thứ tự khám phá.

Vì host giữ reference đến provider instance, lớp wrapper/registry nên gắn provider với **phiên bản/layer** của nó để tránh trộn object giữa hai class identity khác nhau. Trường hợp plugin trả về class thuộc plugin-private packages, phải tránh đưa class đó làm API public chung trừ khi có hợp đồng chuyển đổi dữ liệu rõ ràng.

## 7. Vấn đề với dependency và service API

Một nhóm plugin mới có thể gồm nhiều module phụ thuộc lẫn nhau. Các module mới cần được resolve **cùng một configuration thích hợp** nếu muốn dùng nhau trong cùng graph. Khi `rootSet` không đầy đủ, dependency chưa có trong module finder/parent có thể khiến resolution thất bại.

Nên đặt các loại dependency như sau:

| Thành phần | Vị trí hợp lý | Lý do |
| --- | --- | --- |
| Service interfaces / DTO chuẩn | Parent layer (`demo.api`) | Giữ class identity chung |
| Host implementation | Boot/host layer | Không để plugin nắm vòng đời host |
| Plugin-private dependencies | Layer mới nếu được module hóa, hoặc classloader thiết kế riêng | Giảm xung đột version |
| Plugin providers | Layer mới | Có thể thay theo nhóm/phiên bản |
| Registry chọn active plugin | Host | Điều phối request và chính sách chuyển phiên bản |

JPMS named modules không tự giải quyết tất cả xung đột thư viện, nhất là khi thư viện legacy là automatic module với split packages hoặc phụ thuộc chưa được module hóa đúng. Cần kiểm tra module descriptors bằng `jar --describe-module`, chạy artifact cuối và thử resolution của đúng layer.

## 8. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Thêm plugin JAR nhưng layer cũ vẫn không thấy | Layer graph không đổi sau khi tạo | Resolve và define layer mới |
| `ServiceLoader` trả 0 provider | `provides` thiếu, root/layer không đúng, module không resolved | Kiểm tra descriptor, finder, layer và dùng đúng overload |
| `FindException: Module ... not found` | Module/dependency không được finder hoặc parent nhìn thấy | Sửa module path/finder, tên module và root set |
| `ResolutionException` | Module graph có ràng buộc xung đột | Sửa split packages, readability và graph |
| Plugin mới `ClassCastException` với API | Plugin có bản sao service API hoặc classloader identity khác | Giữ contract ở parent và thống nhất type identity |
| Đóng JAR nhưng loader/layer không được GC | Thread, cache, listener hoặc object reference giữ lại | Dừng provider và bỏ mọi reference |
| Request chạy sai version sau swap | Registry bị thay nhưng in-flight requests chưa drain | Dùng lease/ref-count và lifecycle handoff |
| Thay file JAR nhưng vẫn chạy bytecode cũ | JVM đã định nghĩa class trong layer cũ | Load bản mới trong layer/classloader mới |

## 9. Checklist triển khai an toàn

- [ ] Giữ service contract dùng chung ở layer cha.
- [ ] Tách artifact theo release/version và kiểm tra modular JAR thực tế.
- [ ] Tạo `ModuleFinder` với nguồn artifact rõ ràng.
- [ ] Resolve `Configuration` mới từ parent configuration cùng root modules đúng.
- [ ] Chọn loader strategy phù hợp (`one`, `many`, custom).
- [ ] Dùng `ServiceLoader.load(newLayer, Service.class)` và xác minh provider identity.
- [ ] Kiểm tra health/compatibility của nhóm mới trước khi publish.
- [ ] Swap registry/route theo cơ chế thread-safe; drain requests cũ.
- [ ] Gọi stop/close và dọn ThreadLocal, TCCL, listener, executor, cache.
- [ ] Không kỳ vọng `reload()` hoặc đổi JAR sẽ biến đổi layer hiện hữu.
- [ ] Dùng process isolation nếu cần giới hạn quyền, CPU/memory hay chịu lỗi mạnh.

**Kết luận:** `ModuleLayer` hỗ trợ kiến trúc **nhiều phiên bản/nhóm plugin bằng các layer khác nhau**. Mỗi layer là một cấu hình module đã được resolve và định nghĩa; khi muốn thay đổi thành phần module, hãy tạo layer mới rồi chuyển người sử dụng sang nó có kiểm soát. Không thể cập nhật module graph của layer cũ theo kiểu thêm/bớt JAR tại chỗ.

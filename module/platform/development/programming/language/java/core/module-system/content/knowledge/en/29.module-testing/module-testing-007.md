# Test custom ModuleLayer

Trong Java Platform Module System (JPMS), `ModuleLayer` cho phép ứng dụng tạo một nhóm named module ở runtime, tách khỏi boot layer nhưng liên kết với một hoặc nhiều parent layer. Cơ chế này thường dùng cho plugin, extension, hệ thống nạp nhiều phiên bản thư viện hoặc môi trường cần kiểm soát class loader.

Kiểm thử custom `ModuleLayer` không chỉ là xác nhận `defineModulesWithOneLoader(...)` chạy không ném exception. Một bộ test đáng tin cậy phải chứng minh **module nào đã được resolve, module nào thực sự thuộc layer mới, module nào được tìm qua parent, class loader nào định nghĩa lớp, service provider có được tìm đúng layer và các trường hợp lỗi có thất bại đúng nguyên nhân**.

Bài này xây dựng một fixture nhỏ gồm host, service API và plugin; thực hiện smoke test chạy được từ dòng lệnh; sau đó mở rộng thành checklist kiểm thử tích hợp, isolation và compatibility.

## 1. Ba giai đoạn cần kiểm thử riêng

Một custom layer được tạo theo luồng:

~~~text
Plugin JARs / exploded modules
            |
            v
       ModuleFinder
            |
            v
 Configuration.resolve(...)
 hoặc resolveAndBind(...)
            |
            v
 ModuleLayer.defineModules...
            |
            v
       ModuleLayer
            |
            +--> Module objects
            +--> ClassLoader mapping
            +--> ServiceLoader discovery
~~~

Mỗi giai đoạn có câu hỏi kiểm thử riêng:

1. **Discovery:** `ModuleFinder` có nhìn thấy module JAR hoặc exploded module trong đúng thư mục?
2. **Resolution:** `Configuration` có chứa các module root, dependency và service provider mong đợi?
3. **Definition:** `ModuleLayer` có định nghĩa các module đó với parent/class loader đúng và cho phép ứng dụng sử dụng chúng?

Một lỗi `FindException` xảy ra trước khi layer được tạo khác với lỗi `LayerInstantiationException` trong lúc định nghĩa layer. Một layer tạo thành công nhưng không tìm được provider lại thuộc nhóm vấn đề service registration hoặc phạm vi discovery.

## 2. Thiết kế fixture: API và host ở parent, plugin ở layer con

Để kiểm thử rõ ràng, xây dựng ba module:

~~~text
Boot layer
├── com.acme.spi
└── com.acme.host

Custom plugin layer
└── com.acme.plugin.hello
       |
       └── parent: Boot layer
~~~

API service:

~~~java
// src/host/com.acme.spi/module-info.java
module com.acme.spi {
    exports com.acme.spi;
}
~~~

~~~java
// src/host/com.acme.spi/com/acme/spi/Greeter.java
package com.acme.spi;

public interface Greeter {
    String greet(String name);
}
~~~

Module host:

~~~java
// src/host/com.acme.host/module-info.java
module com.acme.host {
    requires com.acme.spi;
    uses com.acme.spi.Greeter;
}
~~~

Module plugin:

~~~java
// src/plugins/com.acme.plugin.hello/module-info.java
module com.acme.plugin.hello {
    requires com.acme.spi;

    provides com.acme.spi.Greeter
        with com.acme.plugin.hello.HelloGreeter;
}
~~~

Implementation:

~~~java
// src/plugins/com.acme.plugin.hello/com/acme/plugin/hello/HelloGreeter.java
package com.acme.plugin.hello;

import com.acme.spi.Greeter;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Chủ ý **không export** `com.acme.plugin.hello`. Host chỉ cần service type `Greeter` từ module API ở parent; provider được `ServiceLoader` tạo theo `provides` mà không cần host import lớp implementation.

Đây là fixture phù hợp để kiểm thử: API dùng chung có cùng class identity, trong khi implementation được định nghĩa trong custom layer.

## 3. Biên dịch fixture với module output tách biệt

Cấu trúc thư mục:

~~~text
src/
├── host/
│   ├── com.acme.spi/
│   │   ├── module-info.java
│   │   └── com/acme/spi/Greeter.java
│   └── com.acme.host/
│       ├── module-info.java
│       └── com/acme/host/LayerSmokeTest.java
└── plugins/
    └── com.acme.plugin.hello/
        ├── module-info.java
        └── com/acme/plugin/hello/HelloGreeter.java
~~~

Sau khi tạo mã host ở phần tiếp theo, biên dịch:

~~~bash
javac --module-source-path src/host \
      -d out/host \
      -m com.acme.spi,com.acme.host
~~~

Biên dịch plugin với API host trên module path:

~~~bash
javac --module-path out/host \
      --module-source-path src/plugins \
      -d out/plugins \
      -m com.acme.plugin.hello
~~~

Kết quả:

~~~text
out/
├── host/
│   ├── com.acme.spi/
│   └── com.acme.host/
└── plugins/
    └── com.acme.plugin.hello/
~~~

Khi chạy host, **chỉ đưa `out/host` vào boot module path**. Plugin sẽ được tìm qua `ModuleFinder.of(Path.of("out/plugins"))` và định nghĩa sau trong layer con. Nếu vô tình thêm cả `out/plugins` vào boot module path rồi làm nó trở thành root, test có thể không còn kiểm tra đúng hành vi nạp plugin động.

Trên Windows PowerShell có thể viết từng lệnh trên một dòng. Nếu dùng dấu phân cách nhiều module path entries, Windows dùng dấu `;`, Linux/macOS dùng dấu `:`.

## 4. Tạo custom layer và xác nhận cấu hình

Lớp smoke test nằm trong named module `com.acme.host`:

~~~java
// src/host/com.acme.host/com/acme/host/LayerSmokeTest.java
package com.acme.host;

import com.acme.spi.Greeter;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;
import java.util.Set;

public final class LayerSmokeTest {
    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected plugin directory");
        }

        ModuleLayer boot = ModuleLayer.boot();
        ModuleFinder plugins = ModuleFinder.of(Path.of(args[0]));

        Configuration configuration = boot.configuration().resolve(
            plugins,
            ModuleFinder.of(),
            Set.of("com.acme.plugin.hello")
        );

        if (configuration.findModule("com.acme.plugin.hello").isEmpty()) {
            throw new AssertionError("Plugin not resolved");
        }

        ModuleLayer.Controller controller =
            ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(boot),
                ClassLoader.getSystemClassLoader()
            );

        ModuleLayer layer = controller.layer();

        verifyLayer(boot, layer);
        verifyServices(layer);

        System.out.println("CUSTOM LAYER TEST PASS");
    }

    private static void verifyLayer(ModuleLayer boot, ModuleLayer layer) {
        Module plugin = layer
            .findModule("com.acme.plugin.hello")
            .orElseThrow();

        Module apiFromLayer = layer
            .findModule("com.acme.spi")
            .orElseThrow();

        Module apiFromBoot = boot
            .findModule("com.acme.spi")
            .orElseThrow();

        if (plugin.getLayer() != layer) {
            throw new AssertionError("Plugin not owned by child layer");
        }
        if (!layer.modules().contains(plugin)) {
            throw new AssertionError("Plugin absent from layer.modules()");
        }
        if (layer.modules().contains(apiFromBoot)) {
            throw new AssertionError("Parent API was defined again");
        }
        if (apiFromLayer != apiFromBoot) {
            throw new AssertionError("API module identity was duplicated");
        }
        if (!layer.parents().contains(boot)) {
            throw new AssertionError("Missing boot parent");
        }
        if (!plugin.canRead(apiFromBoot)) {
            throw new AssertionError("Plugin cannot read API module");
        }
        if (!apiFromBoot.isExported("com.acme.spi", plugin)) {
            throw new AssertionError("API package not exported to plugin");
        }
    }

    private static void verifyServices(ModuleLayer layer) {
        List<Greeter> providers = ServiceLoader
            .load(layer, Greeter.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .filter(p -> p.getClass().getModule().getLayer() == layer)
            .toList();

        if (providers.size() != 1) {
            throw new AssertionError(
                "Expected one provider in plugin layer, got "
                + providers.size()
            );
        }

        String output = providers.get(0).greet("JPMS");

        if (!"Hello, JPMS".equals(output)) {
            throw new AssertionError("Unexpected provider result: " + output);
        }
    }
}
~~~

Ví dụ kiểm tra đúng các ranh giới: plugin thuộc layer con, API vẫn thuộc boot layer, plugin đọc được API, và provider thực sự đến từ custom layer.

**Quan trọng:** `ServiceLoader.load(layer, Greeter.class)` có thể tìm provider ở layer được truyền và các parent theo quy tắc API. Vì vậy, ví dụ lọc instance theo `getModule().getLayer() == layer` trước khi khẳng định chỉ có một provider plugin. Nếu không lọc, một provider được host cài ở parent có thể khiến test đếm sai.

## 5. Chạy smoke test

Chạy lệnh sau từ thư mục dự án, sau khi đã biên dịch host và plugin:

~~~bash
java --module-path out/host \
     -m com.acme.host/com.acme.host.LayerSmokeTest \
     out/plugins
~~~

Kết quả mong đợi:

~~~text
CUSTOM LAYER TEST PASS
~~~

Ở đây:

- Host và service API là named modules được khởi chạy từ `out/host`.
- Plugin module tồn tại dưới `out/plugins`, chưa được khởi tạo như root của boot layer.
- Host chủ động dùng finder để resolve plugin rồi tạo custom layer.
- Service provider được định nghĩa trong layer con và được khám phá bằng `ServiceLoader.load(layer, Greeter.class)`.

Nếu gặp lỗi trước khi tới dòng PASS, hãy xem **giai đoạn lỗi**: finder, resolution, definition, discovery hay provider execution. Không thêm bừa mọi module vào `--add-modules ALL-MODULE-PATH`, vì điều đó có thể làm sai cấu hình test nạp động.

## 6. modules() khác findModule() trong test

Có hai API dễ bị nhầm:

- `layer.modules()` trả về các module **được định nghĩa trực tiếp** trong layer đó.
- `layer.findModule(name)` có thể tìm module từ layer hiện tại **và các parent layer**.

Với fixture:

~~~java
boolean pluginHere = layer.modules().stream()
    .anyMatch(m -> "com.acme.plugin.hello".equals(m.getName()));

boolean apiHere = layer.modules().stream()
    .anyMatch(m -> "com.acme.spi".equals(m.getName()));

boolean apiVisible = layer.findModule("com.acme.spi").isPresent();
~~~

Kết quả mong đợi:

~~~text
pluginHere = true
apiHere    = false
apiVisible = true
~~~

Một test chỉ gọi `findModule` rồi kết luận module thuộc child layer là **chưa đủ**. Cần kiểm tra `getLayer()` hoặc `modules()` để khẳng định ownership.

Tương tự, `configuration.modules()` trả về các `ResolvedModule` thuộc configuration mới, còn `layer.modules()` là các đối tượng `Module` đã được định nghĩa ở runtime. Nên dùng cả hai khi test cần phân biệt resolution với definition.

## 7. Kiểm tra parent layer và API identity

ModuleLayer có thể có nhiều parent, vì vậy `parents()` là danh sách chứ không phải một parent duy nhất.

Với ví dụ chỉ dùng boot parent:

~~~java
if (!layer.parents().equals(List.of(ModuleLayer.boot()))) {
    throw new AssertionError("Unexpected parent layers");
}
~~~

Để tránh vô tình định nghĩa lại API dùng chung, kiểm tra object identity:

~~~java
Module bootApi = ModuleLayer.boot()
    .findModule("com.acme.spi")
    .orElseThrow();

Module childView = layer
    .findModule("com.acme.spi")
    .orElseThrow();

if (bootApi != childView) {
    throw new AssertionError("Different API module objects");
}
~~~

Đây là kiểm tra quan trọng trong plugin architecture. Nếu mỗi plugin mang bản sao API `Greeter` trong loader khác, đối tượng có cùng tên class vẫn có thể là kiểu khác ở runtime, gây lỗi ép kiểu hoặc không tương thích giữa host và provider.

Cách tổ chức hợp lý là đặt shared contract ở parent layer, còn plugin chỉ `requires` shared API.

## 8. Kiểm tra class loader strategy

Tùy API định nghĩa layer, các module trong child layer có thể dùng một class loader, nhiều loader, hoặc loader do ứng dụng chỉ định.

Các lựa chọn tiêu biểu:

~~~java
ModuleLayer.defineModulesWithOneLoader(
    configuration,
    List.of(boot),
    ClassLoader.getSystemClassLoader()
);
~~~

~~~java
ModuleLayer.defineModulesWithManyLoaders(
    configuration,
    List.of(boot),
    ClassLoader.getSystemClassLoader()
);
~~~

Cùng một configuration, hai chiến lược loader có thể cho class identity và mức cô lập khác nhau. Không nên mặc định “một layer luôn có một class loader”.

Kiểm tra loader thực tế:

~~~java
ClassLoader pluginLoader =
    layer.findLoader("com.acme.plugin.hello");

Class<?> impl = pluginLoader
    .loadClass("com.acme.plugin.hello.HelloGreeter");

Module pluginModule = layer
    .findModule("com.acme.plugin.hello")
    .orElseThrow();

if (impl.getModule() != pluginModule) {
    throw new AssertionError("Class belongs to wrong module");
}
if (impl.getClassLoader() != pluginLoader) {
    throw new AssertionError("Wrong class loader");
}
~~~

Lưu ý: `loadClass` chỉ giúp kiểm tra class loading và identity. Nó không chứng minh class thuộc package chưa export có thể được gọi tùy ý bằng reflection. Với provider plugin, nên sử dụng `ServiceLoader` qua service interface để giữ encapsulation.

## 9. Hai custom layers độc lập để kiểm tra isolation

Một bài test nâng cao là tạo **hai layer từ cùng plugin artifact**:

~~~java
ModuleLayer first = createPluginLayer(pluginDir);
ModuleLayer second = createPluginLayer(pluginDir);

Module p1 = first.findModule("com.acme.plugin.hello").orElseThrow();
Module p2 = second.findModule("com.acme.plugin.hello").orElseThrow();

if (p1 == p2) {
    throw new AssertionError("Expected different runtime modules");
}
if (p1.getClassLoader() == p2.getClassLoader()) {
    throw new AssertionError("Expected separate plugin loaders");
}
~~~

Hàm `createPluginLayer` trong ví dụ phải **thực sự tạo layer mới ở mỗi lần gọi** bằng `defineModulesWithOneLoader` hoặc chiến lược tương đương; không trả lại layer đã cache.

Mục tiêu của test:

- Hai runtime `Module` có thể mang cùng tên nhưng là instance khác khi ở hai layer độc lập.
- Những class plugin có cùng fully qualified name nhưng loader khác sẽ là những kiểu runtime khác nhau.
- Shared API ở boot parent vẫn giữ class identity chung, nên service interface được host dùng để gọi plugin không bị nhân bản.

Không lấy việc dùng loader khác làm bằng chứng cách ly bảo mật. Custom layer không phải sandbox, không cung cấp giới hạn CPU, filesystem hoặc network cho code plugin.

## 10. Test ServiceLoader đúng phạm vi

Phân biệt ba overload:

~~~java
ServiceLoader.load(Greeter.class);

ServiceLoader.load(Greeter.class, loader);

ServiceLoader.load(layer, Greeter.class);
~~~

Overload thứ nhất dùng thread context class loader (TCCL), thứ hai dùng class loader được chỉ định, và thứ ba tìm provider theo phạm vi ModuleLayer.

Với test custom layer, overload `load(layer, service)` thường thể hiện đúng ý định hơn vì nó gắn trực tiếp với layer cần kiểm tra. Không nên vô tình dùng `load(service)` rồi coi việc không tìm thấy provider là lỗi của `ModuleLayer` — TCCL có thể không nhìn thấy child layer mới.

**Caller module phải khai báo `uses`** nếu caller là named module. Trong ví dụ, phương thức `verifyServices` nằm ở `com.acme.host` nên descriptor host có:

~~~java
uses com.acme.spi.Greeter;
~~~

Nếu chuyển logic gọi `ServiceLoader` vào một named helper module khác, module helper đó mới là caller và cần khai báo `uses`. Đây là nguyên nhân thường gặp của `ServiceConfigurationError` trong test.

## 11. Test resolve và resolveAndBind

Để tạo configuration từ finder:

~~~java
Configuration cfg = boot.configuration().resolve(
    pluginFinder,
    ModuleFinder.of(),
    Set.of("com.acme.plugin.hello")
);
~~~

`resolve` đi từ root module và dependency được yêu cầu. Vì `com.acme.plugin.hello` là root tường minh, nó sẽ có mặt nếu tìm thấy và graph hợp lệ.

Nếu host cần tự tìm các provider được kéo vào dựa trên `uses`, có thể cân nhắc `resolveAndBind`:

~~~java
Configuration cfg = boot.configuration().resolveAndBind(
    pluginFinder,
    ModuleFinder.of(),
    Set.of("com.acme.plugin.hello")
);
~~~

`resolveAndBind` thực hiện service binding cho các service được module trong cấu hình sử dụng. Bài test cần phân biệt: provider được đưa vào vì nó là **root** hay được kéo vào bởi **service binding**.

Để kiểm chứng service binding thực sự, hãy tạo fixture có một module consumer trong configuration mới khai báo `uses`, còn provider module khác không nằm trong root/dependency trực tiếp. Sau đó so sánh `configuration.modules()` giữa `resolve` và `resolveAndBind`. Tránh kết luận binding hoạt động chỉ vì một provider vốn đã được chọn làm root xuất hiện.

Ngoài ra, mọi provider cần phải nằm trong phạm vi module finder quan sát được. Service binding không tự tìm JAR nằm ngoài những nguồn module được cấu hình.

## 12. Test lỗi: module không tồn tại

Một negative test quan trọng là yêu cầu một root không thể tìm thấy:

~~~java
ModuleFinder plugins = ModuleFinder.of(Path.of("out/plugins"));

try {
    ModuleLayer.boot().configuration().resolve(
        plugins,
        ModuleFinder.of(),
        Set.of("com.acme.plugin.does.not.exist")
    );

    throw new AssertionError("Expected resolution failure");
} catch (java.lang.module.FindException expected) {
    System.out.println("Missing module detected");
}
~~~

Lỗi `FindException` xảy ra ở giai đoạn resolution, **trước** khi tạo layer. Không nên khẳng định sẽ nhận `LayerInstantiationException` cho một module hoàn toàn không tìm thấy.

Có thể mở rộng bằng các tình huống:

- Plugin khai báo `requires` tới module không tồn tại.
- Plugin và dependency có version/classification không phù hợp.
- Một module có tên sai trong `ModuleFinder` do đóng gói JAR hoặc directory layout.
- Provider module được đặt sai module path nên không được finder phát hiện.

Các negative test nên kiểm tra **loại failure và nội dung chẩn đoán chính**, tránh phụ thuộc cứng vào toàn bộ chuỗi exception message có thể khác giữa JDK versions.

## 13. Test lỗi: xung đột package, module và layer definition

Bên cạnh module thiếu, module graph có thể không hợp lệ do package hoặc loader conflicts.

Những tình huống nên có fixture riêng:

1. Hai module trong cùng configuration gây xung đột package theo quy tắc JPMS.
2. Module được resolve thành công nhưng không thể định nghĩa vào layer với loader strategy đã chọn.
3. Một class loader được yêu cầu định nghĩa các module có layout/package không hợp lệ.
4. Module descriptor khai báo dependency/readability mâu thuẫn với cấu hình parent.

Các lỗi có thể là `ResolutionException` ở resolution hoặc `LayerInstantiationException` ở definition, tùy tình huống. Không nên đặt cùng một expected exception cho tất cả các trường hợp.

Ví dụ mẫu tách hai pha:

~~~java
Configuration configuration = boot.configuration().resolve(
    pluginFinder,
    ModuleFinder.of(),
    Set.of("com.acme.plugin.hello")
);

// Lỗi phát sinh ở bước này là lỗi definition/layer setup.
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(boot),
        ClassLoader.getSystemClassLoader()
    );
~~~

Khi báo lỗi, giữ riêng stack trace của resolver và của layer definition để chẩn đoán đúng nguyên nhân. Không sửa tắt bằng cách đưa toàn bộ JAR vào classpath nếu bài test có mục tiêu kiểm tra ranh giới JPMS.

## 14. Kiểm tra readability, exports và opens

Một plugin ở child layer có thể nhìn thấy API từ parent nhưng vẫn không dùng được package do thiếu readability hoặc exports.

Các kiểm tra runtime:

~~~java
Module plugin = layer.findModule("com.acme.plugin.hello")
    .orElseThrow();

Module api = layer.findModule("com.acme.spi")
    .orElseThrow();

boolean readable = plugin.canRead(api);
boolean exported = api.isExported("com.acme.spi", plugin);

System.out.println("canRead=" + readable);
System.out.println("exported=" + exported);
~~~

Với fixture, cả hai phải đúng. Tuy nhiên, `canRead` và `isExported` không thay thế kiểm thử hành vi provider thật sự. Nếu provider method ném exception trong constructor hoặc thiếu resource, layer vẫn có thể được định nghĩa và quyền module vẫn hợp lệ.

Khi framework cần deep reflection vào package plugin, phải kiểm tra `opens` theo module thực hiện reflection. Với module do custom layer định nghĩa, cấu hình runtime có thể được điều chỉnh có chủ đích qua `ModuleLayer.Controller.addOpens(...)`, nếu chủ sở hữu layer cho phép:

~~~java
controller.addOpens(
    pluginModule,
    "com.acme.plugin.hello",
    hostModule
);
~~~

Lệnh minh họa đòi hỏi `pluginModule` thuộc layer do `controller` quản lý và package thực sự tồn tại trong module đó. Chỉ mở package khi framework có nhu cầu reflection rõ ràng. Không tự động mở tất cả package chỉ để test tiện hơn.

## 15. Test resource loading

Không phải mọi plugin chỉ chứa class. Một số còn có template, JSON, text, cấu hình hoặc certificate.

Ví dụ resource:

~~~text
src/plugins/com.acme.plugin.hello/
└── com/acme/plugin/hello/
    ├── HelloGreeter.java
    └── greeting.txt
~~~

Khi biên dịch bằng `javac`, resource phi Java có thể cần bước copy riêng sang output module. Hãy xác nhận file nằm trong artifact/plugin directory được dùng ở runtime.

Một test có thể yêu cầu provider tự đọc resource thuộc module của nó và trả về một kết quả đã biết. Cách này kiểm tra đầy đủ:

- Resource có được đóng gói không.
- Class loader/module resource lookup có tìm đúng file.
- Encoding được thống nhất, ví dụ UTF-8.
- Module encapsulation không cản trở một truy cập ngoài dự kiến.
- Plugin chạy đúng với cách đóng gói thực tế, không chỉ trong IDE.

Đừng chỉ kiểm tra resource tồn tại ở source directory; bản runtime thường chạy từ exploded module output hoặc modular JAR, nơi resource có thể bị bỏ sót.

## 16. Test nhiều plugin và danh sách provider

Nếu cấu hình chứa nhiều provider:

~~~text
com.acme.plugin.hello
com.acme.plugin.goodbye
com.acme.plugin.echo
~~~

Bộ test cần kiểm tra **tập provider mong đợi**, không dựa vào thứ tự iteration.

Ví dụ:

~~~java
Set<String> providerModules = ServiceLoader
    .load(layer, Greeter.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .filter(p -> p.getClass().getModule().getLayer() == layer)
    .map(p -> p.getClass().getModule().getName())
    .collect(java.util.stream.Collectors.toSet());

Set<String> expected = Set.of(
    "com.acme.plugin.hello",
    "com.acme.plugin.goodbye",
    "com.acme.plugin.echo"
);

if (!providerModules.equals(expected)) {
    throw new AssertionError("Unexpected providers: " + providerModules);
}
~~~

Không nên assert “provider đầu tiên là X” nếu hợp đồng nghiệp vụ không định nghĩa thứ tự. Thứ tự provider discovery không phải cơ chế xếp ưu tiên plugin đáng tin cậy để dùng thay cho cấu hình rõ ràng.

Khi một module có nhiều implementation cho cùng service, việc chỉ kiểm tra tên module có thể chưa đủ. Khi đó nên so sánh class name hoặc metadata provider cụ thể.

## 17. JUnit 5: tổ chức test harness

Fixture có thể được gọi bằng một test runner, JUnit hoặc lệnh smoke test trong CI. Nếu dùng JUnit với project modular, cần quan tâm module chứa code gọi `ServiceLoader.load` và các quyền reflection của test engine.

Hai hướng thực hành:

- **Integration test như consumer bên ngoài:** test/module host gọi một entry point public và kiểm tra kết quả. Mô hình này phản ánh hệ thống thực tế và giảm nhu cầu mở package.
- **Test được patch vào host module:** dùng `--patch-module` ở compile/test nếu cần truy cập helper package-private bên trong host. Khi dùng framework trên classpath, có thể cần `--add-reads` và `--add-opens` phù hợp để framework gọi test.

Ví dụ phương thức test ở mức ý tưởng:

~~~java
@Test
void pluginProviderIsLoadedFromChildLayer() {
    ModuleLayer layer = createPluginLayer(pluginOutputDirectory);

    long count = ServiceLoader.load(layer, Greeter.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(p -> p.getClass().getModule().getLayer() == layer)
        .count();

    assertEquals(1L, count);
}
~~~

Đây là mẫu cấu trúc assertion; cần thêm import JUnit, setup fixture và module/test-runner options của dự án. Nếu test class nằm trong một named module khác host và gọi trực tiếp `ServiceLoader`, module test ấy phải khai báo `uses com.acme.spi.Greeter`.

Giữ test fixtures và nguồn plugin tách khỏi artifact sản phẩm. Không export package nội bộ trong production descriptor chỉ để test tiện hơn.

## 18. CI: chạy trên đúng artifact, đúng JDK

Một pipeline kiểm thử nên gồm:

~~~text
compile host and SPI modules
    |
compile plugin modules
    |
inspect descriptors and dependency graph
    |
run custom layer smoke test
    |
run negative tests
    |
run plugin service/resource tests
    |
package modular JARs
    |
run smoke test on packaged artifacts
~~~

Các bước chẩn đoán hữu ích:

~~~bash
jar --describe-module --file plugins/com.acme.plugin.hello.jar
~~~

~~~bash
jdeps --module-path out/host:out/plugins \
      --print-module-deps \
      plugins/com.acme.plugin.hello.jar
~~~

Trên Windows, `--module-path` với nhiều entry dùng dấu `;`, không phải dấu `:`.

Chú ý so sánh hai trường hợp: chạy từ exploded module output và chạy từ modular JAR. Nếu chỉ test từ output directory, có thể bỏ sót lỗi đóng gói như resource thiếu, descriptor không đi vào JAR hoặc filename/module name không đúng.

Không cần đánh giá chất lượng toàn bộ README trong workflow thực thi test này; mục tiêu ở đây là kiểm chứng kỹ thuật ModuleLayer mà ứng dụng xây dựng.

## 19. Cleanup, caching và lifecycle

Một `ModuleLayer` không có API đóng như `AutoCloseable.close()`. Nếu test tạo nhiều layer mới, cần quản lý các tham chiếu tới:

- `ModuleLayer` và `Module`.
- `ClassLoader` tùy biến.
- `ServiceLoader` và provider instance được cache.
- Thread, executor, timer hoặc callback do plugin tạo.
- Static registry, listener hoặc context giữ class loader.

`ServiceLoader.reload()` chỉ xóa cache provider của loader đó; nó không thay đổi module graph hoặc nạp lại bytecode trong layer cũ. Muốn thử phiên bản plugin mới, thường phải tạo configuration/layer mới với class loader phù hợp.

Việc giải phóng tham chiếu có thể tạo điều kiện cho garbage collection, nhưng không nên viết test giả định lớp/plugin chắc chắn được unload ngay tại một thời điểm cụ thể. Dừng thread và đóng các tài nguyên do plugin sở hữu trước khi kết thúc fixture.

Khi chạy nhiều test song song, dùng thư mục output/fixture độc lập để tránh test này sửa JAR hoặc xóa resource khi test khác đang tạo layer.

## 20. Ma trận kiểm thử đề xuất

| Test case | Kiểm tra chính | Kết quả kỳ vọng |
|---|---|---|
| Load plugin hợp lệ | Finder, resolution, definition | Child layer được tạo |
| Module ownership | `layer.modules()` và `getLayer()` | Plugin thuộc child layer |
| Parent visibility | `findModule` và `parents()` | Shared API tìm thấy từ parent |
| API identity | Đối chiếu object `Module` | API parent không bị nhân bản |
| Readability/export | `canRead` và `isExported` | Quyền truy cập contract đúng |
| Provider discovery | `ServiceLoader.load(layer, service)` | Provider đúng layer, hành vi đúng |
| Class loader mapping | `findLoader` và `Class.getClassLoader` | Loader đúng chiến lược |
| Missing module | `resolve` với tên không tồn tại | `FindException` |
| Invalid graph | Fixture xung đột | Resolution/definition thất bại đúng giai đoạn |
| Multiple providers | So sánh tập provider | Đủ provider, không phụ thuộc thứ tự |
| Resource loading | Template/config trong plugin artifact | Resource đọc được |
| Two independent layers | Hai lần định nghĩa plugin | Module/loader identity tách biệt |
| Packaged modular JAR | Chạy với artifact đóng gói | Cùng kết quả như exploded module |
| Plugin lifecycle | Dọn thread/registry/service | Không để lại resource giữ test process |

## 21. Quy trình chẩn đoán khi test thất bại

Khi test không đạt, xử lý theo thứ tự:

1. **Kiểm tra module path:** API và host có ở boot path; plugin có đúng trong plugin finder path không?
2. **Kiểm tra descriptor:** dùng `jar --describe-module`; đúng tên module, `requires`, `provides` và service type?
3. **Kiểm tra resolution:** `configuration.findModule(name)` có kết quả; có dependency thiếu không?
4. **Kiểm tra definition:** `defineModulesWithOneLoader` hoặc chiến lược khác có lỗi loader/package conflict không?
5. **Kiểm tra parent:** shared API module có phải cùng instance với boot layer không?
6. **Kiểm tra quyền:** plugin có đọc API và API có export package cho plugin không?
7. **Kiểm tra service discovery:** caller named module có `uses`; provider có `provides` và đúng layer không?
8. **Kiểm tra class loader:** TCCL, `findLoader` và class identity có đúng với thiết kế không?
9. **Kiểm tra resource:** plugin JAR/output có đủ resource và dependency runtime không?
10. **Kiểm tra lifecycle:** cache/provider/thread từ test trước có ảnh hưởng test sau không?

Một lỗi provider không được tìm thấy chưa chắc là lỗi `ModuleFinder`: module có thể đã được định nghĩa đúng nhưng `ServiceLoader` được gọi sai overload hoặc metadata service không khớp. Tương tự, một plugin class có thể nạp được nhưng việc truy cập từ host vẫn bị cản bởi package không export; điều đó có thể là hành vi encapsulation đúng.

## 22. Ghi nhớ

Để test custom `ModuleLayer` đáng tin cậy, hãy kiểm tra **cả ba giai đoạn discovery → resolution → definition**, sau đó xác nhận runtime ownership, parent visibility, module identity, class loader mapping và service provider behavior. Đặt service API dùng chung ở parent layer; giữ implementation trong module plugin ở child layer và khám phá qua `ServiceLoader.load(layer, service)`.

`layer.modules()` chỉ kể module trực tiếp thuộc layer, còn `findModule()` tìm cả parent. Test `resolve` khác `resolveAndBind`, đừng nhầm provider đã là root với provider được service binding kéo vào. Dùng negative fixture cho module thiếu và graph xung đột; chạy test trên cả exploded output và modular JAR thật.

Custom layer không phải sandbox bảo mật, không tự reload/unload plugin và không tự sửa các ranh giới readability, exports hoặc opens. Một bộ kiểm thử có giá trị là bộ test xác nhận rõ **module nào được định nghĩa ở đâu, provider nào được chạy, lỗi nào được phát hiện ở giai đoạn nào và cấu hình triển khai có thể tái tạo được**.

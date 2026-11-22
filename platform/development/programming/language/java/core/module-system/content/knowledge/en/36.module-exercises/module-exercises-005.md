# Tạo custom ModuleLayer từ ModuleFinder

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của `ModuleFinder`, `Configuration` và `ModuleLayer`.
- Tìm module từ thư mục chứa modular JAR hoặc exploded module.
- Resolve dependency của plugin dựa trên một parent layer.
- Tạo custom layer bằng `defineModulesWithOneLoader()` hoặc `defineModulesWithManyLoaders()`.
- Dùng `ServiceLoader.load(layer, serviceType)` để tìm provider trong custom layer.
- Phân biệt resolve thông thường với service binding bằng `resolveAndBind()`.
- Quản lý lỗi resolution, class loader và vòng đời plugin.

## 1. Vì sao cần custom ModuleLayer?

JPMS tổ chức ứng dụng thành các named module. Khi khởi chạy ứng dụng, JVM tạo module graph và đưa các module đã resolve vào một `ModuleLayer`. Các module nền tảng của JDK và những module ứng dụng ban đầu thường nằm trong boot layer:

~~~java
ModuleLayer boot = ModuleLayer.boot();

System.out.println(boot.modules());
~~~

Một ứng dụng có thể cần nạp plugin sau khi chương trình đã chạy. Ví dụ, host application cung cấp service API `Codec`, còn các plugin JSON và XML được đóng gói thành các modular JAR riêng.

Nếu muốn bổ sung các module này mà không phải đưa chúng vào module graph lúc khởi động, ứng dụng có thể:

1. Dùng `ModuleFinder` để tìm module trong thư mục plugin.
2. Resolve các module đó cùng dependency của chúng thành một `Configuration`.
3. Tạo một `ModuleLayer` mới từ configuration.
4. Dùng layer mới để truy cập module hoặc tìm service provider.

Custom layer có quan hệ parent với layer hiện có. Module trong layer con có thể đọc các module thích hợp ở parent theo module graph đã resolve. Các module của layer con không tự động trở thành thành viên của boot layer.

## 2. Ba thành phần chính

### 2.1. ModuleFinder: tìm module

`ModuleFinder` là abstraction dùng để tìm `ModuleReference` theo module name. JDK cung cấp các cách tạo finder phổ biến:

~~~java
ModuleFinder systemFinder = ModuleFinder.ofSystem();

ModuleFinder pluginFinder =
        ModuleFinder.of(Path.of("plugins"));
~~~

- `ModuleFinder.ofSystem()` tìm các module hệ thống của runtime image.
- `ModuleFinder.of(path...)` tìm module trong các đường dẫn được chỉ định, bao gồm modular JAR và exploded module.
- `find(moduleName)` tìm một module theo tên và trả về `Optional<ModuleReference>`.
- `findAll()` trả về tập module reference mà finder phát hiện.

Ví dụ kiểm tra nội dung thư mục plugin:

~~~java
Path pluginDirectory = Path.of("plugins");

ModuleFinder finder = ModuleFinder.of(pluginDirectory);

finder.findAll().forEach(reference ->
        System.out.println(reference.descriptor().name()));
~~~

`ModuleFinder` chỉ giúp tìm module metadata và vị trí nội dung. Nó chưa định nghĩa module vào JVM và chưa tạo class loader cho plugin.

### 2.2. Configuration: resolve module graph

`Configuration` biểu diễn kết quả resolve module graph. Nó xác định các module cần có, dependency `requires` và quan hệ module cần thiết để tạo layer.

Có thể lấy configuration của parent layer:

~~~java
Configuration parentConfiguration =
        ModuleLayer.boot().configuration();
~~~

Sau đó resolve các root module từ finder:

~~~java
Configuration configuration =
        parentConfiguration.resolve(
                pluginFinder,
                ModuleFinder.of(),
                Set.of("com.example.codec.json"));
~~~

Các tham số của `resolve(before, after, roots)`:

- `before`: finder được tìm trước parent configuration.
- Parent configuration: module đã có trong layer cha.
- `after`: finder được tìm sau parent configuration.
- `roots`: tập module name bắt đầu quá trình resolve.

Ví dụ dùng `pluginFinder` ở vị trí `before` giúp module plugin được ưu tiên tìm trong thư mục plugin; dependency có sẵn ở parent configuration, chẳng hạn module API đã có trong boot layer, có thể được sử dụng từ parent.

Nếu module được yêu cầu không tìm thấy, thiếu dependency hoặc graph không hợp lệ, quá trình resolve sẽ thất bại với lỗi resolution. Vì vậy, hãy kiểm tra module name, module path và descriptor của các dependency.

### 2.3. ModuleLayer: định nghĩa module vào runtime

Sau khi có configuration, dùng parent layer để tạo layer con:

~~~java
ModuleLayer parent = ModuleLayer.boot();

ModuleLayer.Controller controller =
        parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader());

ModuleLayer pluginLayer = controller.layer();
~~~

`ModuleLayer` là runtime container cho các module đã được resolve. Layer giữ quan hệ với parent layer và ánh xạ các module sang class loader.

API trả về `ModuleLayer.Controller` để ứng dụng có thể lấy layer vừa tạo và, khi thật sự cần, điều chỉnh một số quan hệ module bằng các phương thức của controller.

## 3. Ví dụ: tạo custom layer từ thư mục plugin

Giả sử host application đã có service API trong boot layer:

~~~java
package com.example.codec;

public interface Codec {
    String name();
    byte[] encode(String input);
}
~~~

Module API được export:

~~~java
module com.example.codec.api {
    exports com.example.codec;
}
~~~

Các plugin là named module riêng. Ví dụ JSON plugin:

~~~java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.Codec
            with com.example.codec.json.JsonCodec;
}
~~~

Implementation:

~~~java
package com.example.codec.json;

import com.example.codec.Codec;

public final class JsonCodec implements Codec {

    public JsonCodec() {
    }

    @Override
    public String name() {
        return "json";
    }

    @Override
    public byte[] encode(String input) {
        return ("{\"value\":\"" + input + "\"}")
                .getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

JAR plugin được đặt trong thư mục `plugins`. Host application có thể nạp plugin như sau:

~~~java
import com.example.codec.Codec;

import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;

public class PluginLoader {

    public static void main(String[] args) {
        ModuleLayer parent = ModuleLayer.boot();

        ModuleFinder pluginFinder =
                ModuleFinder.of(Path.of("plugins"));

        Configuration configuration =
                parent.configuration().resolve(
                        pluginFinder,
                        ModuleFinder.of(),
                        Set.of("com.example.codec.json"));

        ModuleLayer.Controller controller =
                parent.defineModulesWithOneLoader(
                        configuration,
                        ClassLoader.getSystemClassLoader());

        ModuleLayer pluginLayer = controller.layer();

        ServiceLoader<Codec> codecs =
                ServiceLoader.load(pluginLayer, Codec.class);

        codecs.forEach(codec ->
                System.out.println("Loaded: " + codec.name()));
    }
}
~~~

Các bước trong ví dụ:

1. Lấy boot layer làm parent.
2. Tạo `ModuleFinder` cho thư mục `plugins`.
3. Resolve root module `com.example.codec.json` cùng các dependency chưa có trong parent.
4. Tạo custom layer với một class loader chung cho các module trong configuration.
5. Dùng overload `ServiceLoader.load(pluginLayer, Codec.class)` để tìm provider trong layer plugin và các parent layer của nó.
6. Duyệt provider để tạo instance và sử dụng service.

Ví dụ giả định `com.example.codec.api` đã được resolve trong boot layer và export package `com.example.codec`. Nếu API module cũng nằm trong thư mục plugin, finder có thể resolve nó vào child layer thay vì dùng API class ở parent. Không nên để host và plugin vô tình dùng hai bản service API khác nhau, vì hai class có cùng tên nhưng thuộc hai module/class loader khác nhau không nhất thiết là cùng một kiểu Java.

## 4. Nạp nhiều plugin module

Một thư mục có thể chứa nhiều modular JAR:

~~~text
plugins/
├── com.example.codec.json.jar
├── com.example.codec.xml.jar
└── com.example.codec.binary.jar
~~~

Có thể chỉ rõ nhiều root module:

~~~java
Set<String> roots = Set.of(
        "com.example.codec.json",
        "com.example.codec.xml",
        "com.example.codec.binary");

Configuration configuration =
        parent.configuration().resolve(
                pluginFinder,
                ModuleFinder.of(),
                roots);
~~~

Khi resolve, dependency `requires` của từng root cũng được xử lý. Nếu một dependency đã có trong parent configuration, module graph con có thể sử dụng module ở parent thay vì định nghĩa lại module đó.

Sau khi tạo layer, ServiceLoader có thể tìm tất cả provider phù hợp:

~~~java
ServiceLoader<Codec> codecs =
        ServiceLoader.load(pluginLayer, Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.name());
}
~~~

Nếu plugin không khai báo `provides` cho service, module vẫn có thể được resolve nhưng không xuất hiện như một provider của `Codec`. Việc module có mặt trong layer và việc module cung cấp một service là hai điều kiện khác nhau.

## 5. resolve() và resolveAndBind()

`Configuration.resolve()` xử lý root modules và các dependency `requires`. `Configuration.resolveAndBind()` còn thực hiện service binding để bổ sung các provider module phù hợp với service được các module đã resolve khai báo sử dụng.

Ví dụ, một module host trong finder khai báo:

~~~java
module com.example.plugin.host {
    requires com.example.codec.api;

    uses com.example.codec.Codec;
}
~~~

Nếu muốn resolver tự tìm các provider `Codec` có thể quan sát được trong plugin finder, có thể dùng:

~~~java
Configuration configuration =
        parent.configuration().resolveAndBind(
                ModuleFinder.of(),
                pluginFinder,
                Set.of("com.example.plugin.host"));
~~~

Trong ví dụ này:

- Finder đầu tiên rỗng; các module chưa có trong parent sẽ được tìm ở finder thứ hai.
- `com.example.plugin.host` là root module.
- Directive `uses` cho biết service mà host cần.
- Các module trong `pluginFinder` khai báo `provides` cho service phù hợp có thể được thêm vào graph.

`resolveAndBind()` không tạo provider instance. Nó chỉ bổ sung module vào configuration. Việc tạo instance vẫn do `ServiceLoader` thực hiện khi ứng dụng tiêu thụ provider.

Khi đã biết chính xác các plugin cần nạp, `resolve()` với danh sách roots tường minh thường dễ kiểm soát hơn. Khi muốn tìm provider theo service declaration, `resolveAndBind()` phù hợp hơn.

## 6. Chọn class loader cho layer

ModuleLayer cung cấp nhiều cách ánh xạ module sang class loader.

### 6.1. Một class loader cho toàn layer

~~~java
ModuleLayer.Controller controller =
        parent.defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader());
~~~

`defineModulesWithOneLoader()` định nghĩa các module trong configuration bằng một class loader chung. Cách này thường đơn giản cho một nhóm plugin có quan hệ dependency với nhau.

### 6.2. Một class loader cho mỗi module

~~~java
ModuleLayer.Controller controller =
        parent.defineModulesWithManyLoaders(
                configuration,
                ClassLoader.getSystemClassLoader());
~~~

`defineModulesWithManyLoaders()` tạo class loader riêng cho từng module trong layer. Cách này có thể hữu ích khi muốn tách biệt việc nạp class của các module.

### 6.3. Tự ánh xạ class loader

Nếu cần kiểm soát chi tiết hơn, dùng `defineModules()` và cung cấp hàm ánh xạ module name sang class loader:

~~~java
ModuleLayer.Controller controller =
        parent.defineModules(
                configuration,
                moduleName -> chooseLoaderFor(moduleName));
~~~

Hàm ánh xạ phải trả về class loader phù hợp cho từng module theo thiết kế. Không được trả về `null` cho module cần định nghĩa.

Việc dùng nhiều class loader không tự tạo sandbox bảo mật. Module readability, exports và opens vẫn là cơ chế kiểm soát truy cập của JPMS; class loader chủ yếu quyết định cách nạp và định danh class ở runtime.

## 7. Quan sát module trong custom layer

Sau khi tạo layer, có thể kiểm tra module đã được định nghĩa:

~~~java
ModuleLayer layer = controller.layer();

layer.modules().forEach(module ->
        System.out.println(module.getName()));

Module jsonModule =
        layer.findModule("com.example.codec.json")
                .orElseThrow();

System.out.println(jsonModule.getClassLoader());
~~~

Các API hữu ích:

- `modules()` trả về tập module thuộc layer hiện tại.
- `findModule(name)` tìm module trong layer và có thể tìm cả module ở parent layer theo quy tắc API.
- `configuration()` trả về configuration gắn với layer.
- `parents()` trả về các parent layer trực tiếp.
- `findLoader(moduleName)` tìm class loader được ánh xạ cho module trong layer.

Nếu muốn kiểm tra chỉ các module được định nghĩa trực tiếp trong child layer, hãy dùng `layer.modules()`; đừng nhầm nó với toàn bộ module có thể truy cập qua parent hierarchy.

## 8. Controller và điều chỉnh quyền truy cập

`ModuleLayer.Controller` được trả về khi định nghĩa layer. Controller cung cấp các thao tác như:

- `layer()` lấy layer đã tạo.
- `addReads(source, target)` bổ sung readability.
- `addExports(source, packageName, target)` bổ sung quyền export package.
- `addOpens(source, packageName, target)` mở package cho deep reflection.

Ví dụ, nếu framework cần reflection vào package plugin và việc mở package không được khai báo sẵn trong descriptor, controller có thể bổ sung quyền ở runtime:

~~~java
Module source = pluginLayer.findModule("com.example.codec.json")
        .orElseThrow();

Module target = PluginFramework.class.getModule();

controller.addOpens(
        source,
        "com.example.codec.json",
        target);
~~~

Chỉ dùng controller khi có yêu cầu runtime cụ thể. Nếu quyền truy cập là một phần ổn định của thiết kế plugin, hãy khai báo `exports` hoặc `opens` trong module descriptor để quyền được thể hiện rõ ràng.

## 9. Lỗi thường gặp khi tạo layer

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `FindException` | Module finder không đọc được module hoặc module path không hợp lệ | Kiểm tra đường dẫn và JAR |
| `ResolutionException` | Thiếu dependency, xung đột module hoặc graph không hợp lệ | Kiểm tra `requires`, module name và parent configuration |
| `LayerInstantiationException` | Không thể định nghĩa module trong layer theo cấu hình class loader/package | Kiểm tra split package và ánh xạ class loader |
| `ServiceConfigurationError` | Provider không hợp lệ hoặc module consumer thiếu `uses` | Kiểm tra `uses`, `provides` và quy tắc provider |
| Không tìm thấy provider | Dùng sai layer hoặc plugin không khai báo `provides` | Dùng `ServiceLoader.load(layer, Service.class)` và kiểm tra descriptor |
| `ClassCastException` dù class có cùng tên | Service API bị nạp thành hai class khác nhau qua các loader/module khác nhau | Đặt API dùng chung ở parent layer và chia sẻ cùng class identity |

Một lỗi thiết kế phổ biến là đóng gói service API vào từng plugin JAR. Khi mỗi plugin nạp một bản API riêng, consumer có thể nhận một object không assignable tới interface mà host đang dùng. Hãy đặt service API ở parent layer, export package cần thiết và để plugin `requires` module API đó.

## 10. Vòng đời plugin và việc tạo layer mới

ModuleLayer không có API `close()` để tự động unload toàn bộ module. Khi plugin cần cập nhật phiên bản, cách làm thường là tạo layer mới từ module finder/configuration mới, sau đó chuyển traffic sang layer mới.

Để class loader cũ có thể được garbage collector thu hồi, ứng dụng phải giải phóng các tham chiếu giữ layer, class loader, module, class, service instance, thread, thread context class loader và resource của plugin. Việc thu hồi không diễn ra ngay lập tức và không được bảo đảm tại một thời điểm cụ thể.

Không thể thay class definition của một module đang chạy chỉ bằng cách gọi lại `resolve()` hoặc `reload()` trên ServiceLoader. Muốn nạp phiên bản plugin khác, hãy tạo module layer mới và quản lý vòng đời của layer cũ.

## 11. Tóm tắt

`ModuleFinder` tìm module metadata từ module path; `Configuration.resolve()` hoặc `resolveAndBind()` xây dựng module graph; `ModuleLayer` định nghĩa graph đó trong runtime với quan hệ parent và class loader cụ thể.

Để tạo plugin layer, hãy bắt đầu từ configuration của parent layer, resolve các root module từ finder, sau đó dùng `defineModulesWithOneLoader()` hoặc `defineModulesWithManyLoaders()`. Dùng `ServiceLoader.load(layer, serviceType)` để tìm provider trong layer. Đặt service API dùng chung ở parent layer để host và plugin chia sẻ cùng class identity, và quản lý rõ vòng đời layer khi cập nhật plugin.

Tài liệu tham khảo:

- [ModuleFinder — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html)
- [Configuration — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html)
- [ModuleLayer — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html)
- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)

# Class loading trong one-loader và many-loader layer

> Phạm vi: Java Platform Module System (JPMS) và **ModuleLayer**. Một module layer kết hợp module configuration đã resolve với cách các module được định nghĩa và nạp bởi class loader. Java cung cấp hai cách tạo layer phổ biến: dùng một class loader chung cho các module hoặc tạo một class loader riêng cho từng module.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích quan hệ giữa **ModuleLayer**, **Configuration**, **Module** và **ClassLoader**.
- Phân biệt cách nạp class của **defineModulesWithOneLoader** và **defineModulesWithManyLoaders**.
- Tạo child layer từ module path dành cho plugin.
- Lấy class loader của một module bằng **ModuleLayer.findLoader**.
- Hiểu class identity, parent delegation và ranh giới readability/exports.
- Chọn chiến lược loader phù hợp với ứng dụng modular và plugin.
- Xử lý lỗi class loading thường gặp khi dùng nhiều layer hoặc nhiều loader.

## 1. ModuleLayer là gì?

**ModuleLayer** biểu diễn một lớp module đã được resolve và định nghĩa trong runtime. Một layer chứa các module thuộc một **Configuration** và có thể có một hoặc nhiều parent layer.

Khi JVM khởi động, Java tạo boot layer chứa các module nền tảng và các module được resolve cho ứng dụng. Có thể lấy layer này bằng:

~~~java
ModuleLayer bootLayer = ModuleLayer.boot();
~~~

Ứng dụng có thể tạo thêm child layer để nạp plugin hoặc một nhóm module khác sau khi chương trình đã khởi động.

Một layer không phải là class loader. Layer quản lý quan hệ module và ánh xạ module tới class loader. Cách ánh xạ đó phụ thuộc phương thức dùng để định nghĩa layer.

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| **Configuration** | Mô tả module graph đã resolve: module nào có mặt và dependency nào được thỏa mãn |
| **ModuleLayer** | Đại diện cho một layer chứa các module được định nghĩa từ configuration |
| **Module** | Đại diện runtime cho một module cụ thể |
| **ClassLoader** | Nạp class/resource; một loader có thể định nghĩa class thuộc một hoặc nhiều module tùy cách tạo layer |
| **ModuleLayer.Controller** | Cung cấp quyền điều chỉnh quan hệ module trong layer được tạo, ví dụ thêm reads, exports hoặc opens khi cần |

Module system và class loading phối hợp với nhau. Class loader chịu trách nhiệm tìm và định nghĩa class; module system kiểm soát readability, exports và opens giữa các module.

## 2. Configuration và ModuleLayer khác nhau thế nào?

**Configuration** trả lời câu hỏi: module graph nào đã được resolve? Nó chứa thông tin về các module và dependency, nhưng chưa tự tạo class loader hoặc nạp class.

**ModuleLayer** dùng configuration để định nghĩa module trong runtime và gắn chúng với class loader.

Quy trình tổng quát:

1. Tìm module bằng **ModuleFinder**.
2. Resolve dependency để tạo **Configuration**.
3. Chọn cách định nghĩa layer: one-loader, many-loaders hoặc mapping loader tùy chỉnh.
4. Lấy layer từ **ModuleLayer.Controller**.
5. Nạp class hoặc tìm service provider trong layer.

Có thể hình dung:

~~~text
ModuleFinder
    |
    v
Configuration.resolve(...)
    |
    v
Module graph đã resolve
    |
    v
ModuleLayer.defineModulesWith...
    |
    +---- one-loader: một loader cho các module trong layer
    |
    +---- many-loaders: một loader cho mỗi module
    |
    v
ModuleLayer
    |
    v
Class loading / ServiceLoader / reflection
~~~

Điểm quan trọng: **resolve module graph** và **định nghĩa class loader** là hai bước riêng. Nếu configuration không resolve được dependency, chưa thể tạo layer hợp lệ.

## 3. One-loader layer là gì?

Tạo layer bằng **ModuleLayer.defineModulesWithOneLoader** sẽ định nghĩa các module trong configuration vào cùng một class loader mới.

Ví dụ:

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader()
        );

ModuleLayer layer = controller.layer();
~~~

Ý nghĩa:

- **configuration** là configuration đã resolve cho các module cần nạp.
- **List.of(ModuleLayer.boot())** chỉ định boot layer là parent.
- **ClassLoader.getSystemClassLoader()** là parent loader của loader được tạo cho layer.
- **controller.layer()** trả về layer mới.

Trong one-loader layer, các module được định nghĩa bởi một loader chung. Điều đó có thể giảm số lượng class loader cần quản lý và làm đơn giản cấu trúc nạp class trong một nhóm module có liên quan.

Tuy nhiên, **một loader chung không có nghĩa các module bị hợp nhất thành một module**. Mỗi module vẫn giữ descriptor, tên module, package ownership, readability và exports riêng. Việc class cùng được định nghĩa bởi một loader không tự cấp quyền truy cập package giữa các module.

One-loader phù hợp khi các module tạo thành một nhóm triển khai gắn bó, cần chia sẻ một không gian class loading và không yêu cầu cách ly loader riêng cho từng module.

## 4. Many-loader layer là gì?

Tạo layer bằng **ModuleLayer.defineModulesWithManyLoaders** sẽ tạo một class loader riêng cho mỗi module trong configuration.

Ví dụ:

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithManyLoaders(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader()
        );

ModuleLayer layer = controller.layer();
~~~

Mỗi module có loader riêng. Các loader được tạo với parent loader đã chỉ định; việc truy cập module khác vẫn phải tuân theo module graph và cơ chế delegation của loader do Java tạo.

Many-loader hữu ích khi ứng dụng muốn tách class loading theo module, ví dụ một hệ thống plugin có nhiều module độc lập. Nó tạo ranh giới loader rõ hơn, giúp phát hiện sớm các giả định sai về class identity và tránh việc tất cả class của layer dùng chung một defining loader.

Đổi lại, nhiều loader làm tăng số đối tượng cần quản lý và có thể làm việc debug, resource lookup, reflection hoặc chia sẻ API phức tạp hơn. Không nên giả định many-loader luôn nhanh hơn hoặc an toàn hơn; cần đo đạc theo ứng dụng thực tế.

## 5. So sánh one-loader và many-loaders

| Tiêu chí | One-loader | Many-loaders |
|---|---|---|
| Số loader cho module trong configuration | Một loader chung | Một loader cho mỗi module |
| Ranh giới class loader | Chung trong layer | Tách theo module |
| Module descriptor và exports | Vẫn được áp dụng riêng cho từng module | Vẫn được áp dụng riêng cho từng module |
| Chi phí quản lý loader | Thường thấp hơn | Có thể cao hơn khi có nhiều module |
| Cách ly class loading | Ít hơn giữa các module cùng layer | Rõ hơn theo module |
| Tình huống thường dùng | Nhóm module triển khai gắn bó | Plugin hoặc module cần loader riêng |

Lựa chọn loader không thay thế thiết kế module. Dù dùng one-loader hay many-loaders, module vẫn cần khai báo dependency bằng **requires**, công bố API bằng **exports** và mở package cho reflection bằng **opens** khi cần.

## 6. Tạo Configuration và child layer từ plugin directory

Giả sử ứng dụng có thư mục **plugins** chứa các modular JAR:

~~~text
application/
├── app/
└── plugins/
    ├── com.acme.plugin.alpha.jar
    └── com.acme.plugin.beta.jar
~~~

Mỗi plugin là explicit module và có module descriptor. Ví dụ module alpha:

~~~java
module com.acme.plugin.alpha {
    requires com.acme.plugin.api;
}
~~~

Module API nên nằm trong boot layer hoặc một parent layer mà plugin có thể đọc. Điều này giúp ứng dụng và plugin dùng chung một định nghĩa API thay vì nạp hai bản interface có class identity khác nhau.

Tạo configuration cho các plugin:

~~~java
Path pluginPath = Path.of("plugins");

ModuleFinder finder = ModuleFinder.of(pluginPath);

Configuration parentConfiguration =
        ModuleLayer.boot().configuration();

Configuration pluginConfiguration =
        parentConfiguration.resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.acme.plugin.alpha", "com.acme.plugin.beta")
        );
~~~

Giải thích:

- **ModuleFinder.of(pluginPath)** tìm module trong thư mục plugin.
- **ModuleLayer.boot().configuration()** lấy configuration của boot layer làm parent configuration.
- **resolve** tạo configuration mới từ các module được tìm thấy và dependency cần thiết.
- Tập roots chỉ định các module plugin muốn nạp.

Nếu một plugin có dependency vào module khác trong cùng thư mục, resolver sẽ cố gắng resolve dependency đó từ module finder. Nếu thiếu dependency hoặc descriptor không hợp lệ, bước resolve sẽ thất bại trước khi tạo layer.

## 7. Tạo child layer với one-loader hoặc many-loaders

Sau khi có **pluginConfiguration**, chọn một trong hai cách.

### Dùng one-loader

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                pluginConfiguration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader()
        );

ModuleLayer pluginLayer = controller.layer();
~~~

Các module plugin trong configuration được định nghĩa bằng cùng một loader. Có thể dùng khi các plugin cần chia sẻ class loading và được quản lý như một nhóm.

### Dùng many-loaders

~~~java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithManyLoaders(
                pluginConfiguration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader()
        );

ModuleLayer pluginLayer = controller.layer();
~~~

Mỗi module plugin có loader riêng. Đây là lựa chọn phù hợp khi muốn tách class loading theo module.

Không tạo cả hai layer cho cùng một configuration trong ứng dụng thật chỉ để chọn ngẫu nhiên. Hãy quyết định chiến lược trước dựa trên quan hệ giữa plugin, cách chia sẻ API và yêu cầu cô lập.

## 8. Tìm class loader của module trong layer

Sau khi tạo layer, dùng **findLoader** để lấy loader gắn với một module:

~~~java
ClassLoader loader =
        pluginLayer.findLoader("com.acme.plugin.alpha");
~~~

Hoặc lấy từ đối tượng Module:

~~~java
Module module =
        pluginLayer.findModule("com.acme.plugin.alpha")
                   .orElseThrow();

ClassLoader loader = module.getClassLoader();
~~~

Với module được định nghĩa bởi bootstrap loader, **Module.getClassLoader()** có thể trả về **null**. Đối với plugin module do loader của layer định nghĩa, thông thường nhận được loader tương ứng.

Có thể nạp class theo tên bằng loader đã tìm:

~~~java
Class<?> pluginClass =
        Class.forName(
                "com.acme.plugin.alpha.PluginMain",
                true,
                pluginLayer.findLoader("com.acme.plugin.alpha")
        );
~~~

Việc nạp class thành công không đồng nghĩa mọi thao tác truy cập đều được phép. Module readability, exports, opens, visibility của constructor và các quy tắc reflection vẫn được áp dụng.

Nếu ứng dụng cần gọi API plugin, nên dùng interface/service API được export từ module API chung. Tránh dựa vào tên class nội bộ hoặc reflection vào package không được mở.

## 9. Class identity và lỗi ClassCastException

Trong JVM, class identity gắn với tên nhị phân của class và defining class loader. Vì vậy, hai class cùng tên nhưng được định nghĩa bởi hai loader khác nhau là hai kiểu runtime khác nhau.

Ví dụ:

- Loader A định nghĩa **com.acme.api.Plugin**.
- Loader B cũng định nghĩa một bản **com.acme.api.Plugin** khác.
- Một object implement bản interface do Loader B định nghĩa không thể được cast sang bản interface do Loader A định nghĩa.

Điều này có thể gây lỗi:

~~~text
ClassCastException: com.acme.api.Plugin cannot be cast to com.acme.api.Plugin
~~~

Tên class trong thông báo giống nhau nhưng defining loader khác nhau.

Để tránh lỗi:

1. Đặt interface/API dùng chung trong boot layer hoặc một parent layer.
2. Để plugin khai báo **requires** module API chung.
3. Không đóng gói thêm bản sao API vào từng plugin nếu chúng cần tương tác với host.
4. Dùng loader của layer để nạp implementation, nhưng giữ kiểu API ở parent layer.
5. Kiểm tra defining loader khi debug.

Ví dụ kiểm tra:

~~~java
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
~~~

Với object:

~~~java
System.out.println(plugin.getClass().getClassLoader());
System.out.println(plugin.getClass().getModule());
~~~

So sánh cả module và loader giúp xác định object thuộc layer/module nào.

## 10. Readability, exports và class loader là ba vấn đề khác nhau

Khi một module cần dùng type của module khác, cần phân biệt:

- **Class loading**: loader tìm và định nghĩa bytecode.
- **Readability**: module nguồn có đọc được module chứa type hay không, thường được khai báo bằng **requires**.
- **Exports**: module đích có export package chứa type cho module nguồn hay không.

Nếu class loader tìm thấy class nhưng module không đọc được module chứa class hoặc package không được export, truy cập vẫn có thể thất bại.

Ví dụ:

~~~java
module com.acme.plugin.api {
    exports com.acme.plugin.api;
}
~~~

Plugin:

~~~java
module com.acme.plugin.alpha {
    requires com.acme.plugin.api;
}
~~~

Host hoặc module khác muốn gọi API phải có quan hệ readability phù hợp. Package nội bộ không export không trở thành public API chỉ vì dùng one-loader.

Đối với deep reflection, module đích có thể cần **opens** package cho module thực hiện reflection. **exports** chủ yếu cho truy cập kiểu public ở mức compile/runtime thông thường; **opens** phục vụ reflection sâu.

## 11. Dùng ServiceLoader với ModuleLayer

Nếu plugin cung cấp implementation của một service, nên dùng **ServiceLoader** thay vì tự ghép tên class và gọi reflection.

Module API:

~~~java
module com.acme.plugin.api {
    exports com.acme.plugin.api;
}
~~~

Interface service:

~~~java
package com.acme.plugin.api;

public interface Plugin {
    String name();
    void start();
}
~~~

Provider module:

~~~java
module com.acme.plugin.alpha {
    requires com.acme.plugin.api;

    provides com.acme.plugin.api.Plugin
        with com.acme.plugin.alpha.AlphaPlugin;
}
~~~

Sau khi tạo plugin layer, tìm provider trong layer:

~~~java
ServiceLoader<Plugin> plugins =
        ServiceLoader.load(pluginLayer, Plugin.class);

for (Plugin plugin : plugins) {
    System.out.println(plugin.name());
    plugin.start();
}
~~~

Overload **ServiceLoader.load(layer, service)** tìm provider trong layer được chỉ định và các parent layer của nó. Module chứa lời gọi cũng cần khai báo **uses** cho service khi caller là explicit named module.

Nếu plugin module được tạo trong child layer, provider phải được resolve vào layer đó hoặc một parent layer phù hợp. Chỉ đặt JAR trong thư mục plugin chưa đủ nếu module finder, configuration hoặc roots không đưa module vào layer.

## 12. Parent loader và parent layer

Khi tạo layer, cần phân biệt **parent layer** và **parent class loader**:

- Parent layer xác định quan hệ module configuration và module graph kế thừa.
- Parent class loader là loader mà loader mới dùng làm parent trong cấu trúc class loading.

Hai khái niệm có liên quan nhưng không thay thế nhau. Một module có thể đọc module từ parent layer theo configuration, còn việc nạp class vẫn đi qua loader tương ứng.

Ví dụ dùng boot layer làm parent:

~~~java
List<ModuleLayer> parents = List.of(ModuleLayer.boot());
ClassLoader parentLoader = ClassLoader.getSystemClassLoader();
~~~

Chọn parent loader phù hợp với môi trường chạy. Trong ứng dụng container hoặc môi trường plugin có custom class loader, không nên mặc định system class loader luôn là lựa chọn đúng. Hãy xác định loader nào nhìn thấy API chung và các thư viện nền tảng mà plugin cần.

## 13. Khi nào nên chọn one-loader hoặc many-loaders?

Chọn **one-loader** khi:

- Các module trong layer tạo thành một đơn vị triển khai gắn bó.
- Muốn giảm số lượng loader cần quản lý.
- Không cần tách class loading theo từng module.
- API và dependency giữa các module đã được thiết kế rõ.

Chọn **many-loaders** khi:

- Mỗi module/plugin cần loader riêng.
- Muốn tách class loading để hạn chế xung đột giữa các module.
- Cần quản lý nhiều plugin độc lập và có thể kiểm soát dependency.
- Có thể chấp nhận chi phí quản lý loader và độ phức tạp tăng thêm.

Cả hai cách đều không phải sandbox bảo mật. Class loader riêng không thay thế quy trình kiểm soát plugin, giới hạn quyền truy cập hệ thống, xác minh nguồn artifact hoặc cách ly tiến trình khi chạy mã không đáng tin cậy.

Hiệu năng phụ thuộc số module, số class, kích thước dependency, tần suất nạp class và cách ứng dụng dùng reflection/service. Hãy đo trên workload thật thay vì kết luận một-loader hoặc many-loaders luôn nhanh hơn.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| **FindException** khi resolve | Thiếu module hoặc dependency không resolve được | Kiểm tra ModuleFinder, module path, roots và các directive requires |
| **ResolutionException** | Module graph không hợp lệ, có thể do split package hoặc xung đột khác | Đọc tên module/package trong lỗi; kiểm tra descriptor và package inventory |
| **LayerInstantiationException** | Không thể định nghĩa module trong layer theo cách loader đã chọn | Kiểm tra configuration, parent layers và điều kiện package/loader |
| **ClassNotFoundException** | Tìm sai tên class hoặc dùng loader không gắn với module cần nạp | Dùng đúng tên đầy đủ và lấy loader bằng findLoader |
| **NoClassDefFoundError** | Dependency runtime không được tìm thấy hoặc class khởi tạo thất bại | Kiểm tra module graph, dependency và nguyên nhân gốc |
| **ClassCastException** dù tên class giống nhau | Hai bản class được định nghĩa bởi hai loader khác nhau | Đặt API chung trong parent layer và tránh đóng gói trùng API |
| **IllegalAccessError** | Thiếu readability hoặc package không được export | Kiểm tra requires, exports và module graph |
| Reflection bị chặn | Package chưa mở cho module thực hiện deep reflection | Dùng opens trong descriptor hoặc cấu hình mở phù hợp |
| Không tìm thấy provider bằng ServiceLoader | Provider chưa được resolve vào layer hoặc thiếu uses/provides | Kiểm tra module descriptor, roots, layer và dùng overload load(layer, service) |

Quy trình debug:

1. In tên module và configuration đang dùng.
2. Kiểm tra module finder tìm thấy đúng plugin JAR.
3. Xác nhận configuration resolve được với đúng roots.
4. Xác định layer parent và cách tạo loader.
5. Dùng **findLoader** để lấy loader của module.
6. In **Class.getClassLoader()** và **Class.getModule()** của type gây lỗi.
7. Kiểm tra requires, exports và opens.
8. Nếu dùng service, kiểm tra uses/provides và tìm provider trong đúng layer.

## 15. Ghi nhớ

- **ModuleLayer** chứa các module đã được resolve và định nghĩa trong runtime.
- **Configuration** mô tả module graph; nó chưa tự tạo class loader.
- **defineModulesWithOneLoader** dùng một loader chung cho các module trong configuration.
- **defineModulesWithManyLoaders** tạo một loader riêng cho mỗi module.
- Một loader chung không hợp nhất module; readability, exports và opens vẫn được kiểm tra.
- Class cùng tên nhưng khác defining loader là hai runtime type khác nhau.
- Đặt API dùng chung trong parent layer giúp host và plugin chia sẻ cùng class identity.
- Dùng **ModuleLayer.findLoader** để lấy loader của module.
- Dùng **ServiceLoader.load(layer, service)** khi cần tìm provider trong plugin layer.
- One-loader và many-loaders là lựa chọn kiến trúc; hãy đo hiệu năng và kiểm thử class identity theo workload thực tế.

## Tài liệu tham khảo

- [ModuleLayer — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html)
- [Configuration — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html)
- [ClassLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)

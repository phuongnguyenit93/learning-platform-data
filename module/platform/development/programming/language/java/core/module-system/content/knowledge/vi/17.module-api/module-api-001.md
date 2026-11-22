# `java.lang.Module` và module identity trong runtime

## Mục tiêu

Sau bài này, bạn có thể giải thích `Module` đại diện cho điều gì khi ứng dụng đang chạy, phân biệt tên module với danh tính của một module instance, truy vết module của một class và đọc các quan hệ readability, exports, opens trong runtime.

## 1. Từ khai báo module đến đối tượng runtime

Trong Java Platform Module System (JPMS), file `module-info.java` khai báo tên module và các quan hệ như `requires`, `exports`, `opens`, `uses`, `provides`. Khi biên dịch, khai báo này được lưu trong `module-info.class`. Khi ứng dụng được phân giải và nạp, JVM tạo các module instance để áp dụng ranh giới module và quy tắc truy cập.

`java.lang.Module` là lớp đại diện cho một module instance trong runtime. Nó không phải là file `module-info.java`, cũng không phải là một `ClassLoader`. Một đối tượng `Module` cho biết class đang thuộc module nào, module có tên gì, nằm trong layer nào, dùng class loader nào và đang có những quan hệ truy cập nào với module khác.

Bạn thường lấy đối tượng này từ một class:

~~~java
Module module = SomeType.class.getModule();
~~~

Mỗi class runtime có thể được truy ngược về module chứa nó. Vì vậy, khi gặp lỗi truy cập kiểu `IllegalAccessError`, lỗi reflection như `InaccessibleObjectException`, hoặc vấn đề khi nạp plugin, `Class.getModule()` là điểm bắt đầu hữu ích để kiểm tra.

## 2. Module name và module identity là hai khái niệm khác nhau

Tên module là nhãn dùng trong khai báo và phân giải module, ví dụ `java.base` hoặc `com.acme.payment`. Tên này giúp module system tìm dependency và diễn đạt các quan hệ trong cấu hình.

Danh tính runtime là module instance cụ thể được JVM tạo ra. Khi cần biết hai class có thuộc cùng một module instance hay không, hãy so sánh đối tượng `Module` mà chúng trả về:

~~~java
Module first = FirstType.class.getModule();
Module second = SecondType.class.getModule();

boolean sameRuntimeModule = first == second;
~~~

Không nên dùng riêng `getName()` làm khóa nhận diện toàn cục. Các module layer khác nhau có thể chứa những module instance có cùng tên. Điều này hữu ích khi ứng dụng nạp các phiên bản plugin độc lập trong những layer riêng. Hai module có cùng tên nhưng nằm trong hai layer khác nhau vẫn là hai module instance khác nhau.

Một module instance cũng không đồng nghĩa với một class loader. Một class loader có thể định nghĩa nhiều named module; ngược lại, các layer có thể dùng những class loader khác nhau. Module biểu diễn ranh giới module và các quy tắc truy cập, còn class loader chịu trách nhiệm định nghĩa class.

Đối với class, danh tính kiểu ở JVM gắn với tên nhị phân của class và defining class loader. Nếu hai class loader thực sự định nghĩa riêng hai class cùng tên, hai đối tượng `Class` đó vẫn là hai kiểu khác nhau, kể cả khi bytecode giống nhau. Module cung cấp thêm ngữ cảnh về ranh giới truy cập của class.

## 3. Ba loại module thường gặp ở runtime

### Explicit named module

Đây là module khai báo rõ trong `module-info.java`. Ví dụ:

~~~java
module com.acme.orders {
    requires java.logging;
    exports com.acme.orders.api;
    opens com.acme.orders.model;
}
~~~

Module này có tên `com.acme.orders` và một `ModuleDescriptor` mô tả các khai báo của nó.

### Automatic module

Một JAR không có `module-info.class`, khi được đặt trên module path, có thể được xem như automatic module. Module system tạo descriptor tự động dựa trên thông tin của JAR và tên module suy ra từ tên file hoặc manifest. Automatic module vẫn là named module, vì vậy `Module.isNamed()` trả về `true`.

Automatic module có quy tắc tương thích rộng hơn explicit module, chẳng hạn khả năng đọc các module khác và xuất các package của nó. Không nên dựa vào các quy tắc rộng này như thiết kế lâu dài cho một module có ranh giới API rõ ràng.

### Unnamed module

Các class được nạp từ class path thường thuộc unnamed module của class loader tương ứng. Mỗi class loader có unnamed module riêng. Unnamed module không có tên module và không có `ModuleDescriptor` như named module.

~~~java
Module module = SomeClasspathType.class.getModule();

System.out.println(module.isNamed()); // false
System.out.println(module.getName()); // null
System.out.println(module.getDescriptor()); // null
~~~

Đừng nhầm unnamed module với automatic module: automatic module là named module được suy ra từ JAR; unnamed module thường gắn với class path và một class loader.

## 4. Các API quan trọng của `java.lang.Module`

| API | Ý nghĩa |
| --- | --- |
| `getName()` | Trả về tên module; trả về `null` với unnamed module. |
| `isNamed()` | Cho biết module có phải named module hay không. |
| `getDescriptor()` | Trả về `ModuleDescriptor` của named module; có thể là `null` với unnamed module. |
| `getLayer()` | Trả về `ModuleLayer` chứa module; có thể là `null` nếu module không thuộc layer. |
| `getClassLoader()` | Trả về class loader định nghĩa module; `null` biểu thị bootstrap class loader. |
| `getPackages()` | Trả về tập tên package thuộc module. |
| `canRead(Module)` | Kiểm tra module hiện tại có readability edge tới module được truyền vào hay không. |
| `isExported(String, Module)` | Kiểm tra package của module hiện tại có được export tới module đích hay không. |
| `isOpen(String, Module)` | Kiểm tra package của module hiện tại có được open cho module đích hay không. |
| `getResourceAsStream(String)` | Đọc resource theo tên từ module, tuân theo quy tắc đóng gói tài nguyên của module. |

Ví dụ sau in thông tin runtime của một class:

~~~java
import java.lang.module.ModuleDescriptor;

public final class ModuleInspector {
    public static void print(Class<?> type) {
        Module module = type.getModule();
        ModuleDescriptor descriptor = module.getDescriptor();

        System.out.println("class       : " + type.getName());
        System.out.println("module      : "
                + (module.isNamed() ? module.getName() : "<unnamed>"));
        System.out.println("module obj  : " + module);
        System.out.println("class loader: " + module.getClassLoader());
        System.out.println("layer       : " + module.getLayer());
        System.out.println("packages    : " + module.getPackages());

        if (descriptor != null) {
            System.out.println("requires: " + descriptor.requires());
            System.out.println("exports : " + descriptor.exports());
            System.out.println("opens   : " + descriptor.opens());
        }
    }
}
~~~

`ModuleDescriptor` thuộc package `java.lang.module`. Nó mô tả metadata của named module, ví dụ các dependency và package được export hoặc open. Descriptor là metadata; đối tượng `Module` mới là module instance đang tồn tại trong runtime. Với unnamed module, `getDescriptor()` trả về `null`, vì vậy cần kiểm tra trước khi đọc descriptor.

`System.identityHashCode(module)` đôi khi hữu ích khi ghi log để phân biệt các object trong một lần chạy, nhưng giá trị hash có thể trùng. Khi cần kiểm tra hai tham chiếu có trỏ tới đúng cùng module instance hay không, dùng phép so sánh `==`.

## 5. Đọc đúng ba quan hệ: readability, exports và opens

Ba khái niệm này thường xuất hiện cùng nhau nhưng giải quyết ba câu hỏi khác nhau.

- **Readability**: module client có thể đọc module API hay không? Quan hệ này thường được khai báo bằng `requires`.
- **Exports**: package API có được module nguồn export cho module client hay không? Export cho phép module khác dùng các kiểu public trong package theo quy tắc truy cập Java thông thường.
- **Opens**: package có được mở cho module client thực hiện deep reflection hay không? Opens phục vụ truy cập reflective, kể cả các thành viên không public khi các điều kiện reflection được đáp ứng.

Ví dụ kiểm tra từ phía module client:

~~~java
Module clientModule = Client.class.getModule();
Module apiModule = PublicApi.class.getModule();

boolean canReadApi =
        clientModule.canRead(apiModule);

boolean apiIsExported =
        apiModule.isExported("com.acme.api", clientModule);

boolean internalsAreOpen =
        apiModule.isOpen("com.acme.internal", clientModule);

System.out.println("readable: " + canReadApi);
System.out.println("exported: " + apiIsExported);
System.out.println("open    : " + internalsAreOpen);
~~~

Hãy chú ý hướng gọi:

- Gọi `clientModule.canRead(apiModule)` vì client là module cần đọc API.
- Gọi `apiModule.isExported(packageName, clientModule)` vì package nằm trong module API và cần kiểm tra có export cho client không.
- Gọi `apiModule.isOpen(packageName, clientModule)` vì module API là bên sở hữu package cần mở cho reflection.

Có readability không tự động có nghĩa là mọi package của dependency đều được export. Export cũng không đồng nghĩa với open. Một package có thể được export để dùng API public nhưng vẫn đóng với deep reflection.

Trong `module-info.java`, có thể khai báo export hoặc open không giới hạn module đích, hoặc chỉ định rõ module đích:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
    exports com.acme.domain.spi to com.acme.plugin;

    opens com.acme.domain.model;
    opens com.acme.domain.internal to com.acme.serializer;
}
~~~

Khai báo `open module com.acme.domain { ... }` mở tất cả package của module cho deep reflection. Điều này không có nghĩa là tất cả package được export để module khác truy cập API theo cách thông thường.

## 6. `ModuleLayer` và danh tính module trong nhiều layer

`ModuleLayer` là một nhóm module đã được phân giải thành runtime graph. JVM khởi động ứng dụng với boot layer, có thể truy cập qua `ModuleLayer.boot()`. Ứng dụng cũng có thể tạo layer mới để nạp plugin hoặc thành phần cần vòng đời và class loader riêng.

~~~java
Module javaBase = ModuleLayer.boot()
        .findModule("java.base")
        .orElseThrow();

System.out.println(javaBase.getName());
System.out.println(javaBase.getLayer() == ModuleLayer.boot());
~~~

Ví dụ nâng cao: nạp một module plugin từ thư mục `plugins` vào layer mới. Module plugin cần có mặt trên module path mà `ModuleFinder` quét được.

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
        ModuleLayer.boot().configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.example.plugin"));

ModuleLayer pluginLayer =
        ModuleLayer.boot().defineModulesWithOneLoader(
                configuration,
                ClassLoader.getSystemClassLoader());

Module pluginModule = pluginLayer
        .findModule("com.example.plugin")
        .orElseThrow();

System.out.println(pluginModule.getName());
System.out.println(pluginModule.getLayer() == pluginLayer);
~~~

Ở ví dụ này, `defineModulesWithOneLoader` tạo layer mới và dùng một class loader cho các module được định nghĩa trong layer đó. API `defineModulesWithManyLoaders` là lựa chọn khác khi muốn mỗi module có class loader riêng.

Tên module có ý nghĩa trong phạm vi cấu hình/layer. Khi hệ thống có nhiều layer, đừng giả định rằng một tên module chỉ có duy nhất một module instance trong toàn bộ tiến trình. Nếu đang debug plugin, hãy kiểm tra đồng thời tên module, layer và class loader:

~~~java
Module module = PluginEntry.class.getModule();

System.out.println("name   = " + module.getName());
System.out.println("layer  = " + module.getLayer());
System.out.println("loader = " + module.getClassLoader());
~~~

## 7. Dùng Module API khi debug lỗi truy cập

Khi một module không truy cập được class hoặc package, kiểm tra theo thứ tự sau:

1. Lấy module của class đang gọi và class được truy cập bằng `Class.getModule()`.
2. In `getName()`, `getLayer()` và `getClassLoader()` của cả hai module để xác định đúng module instance.
3. Kiểm tra module gọi có đọc module đích không bằng `canRead`.
4. Kiểm tra package chứa API có export cho module gọi không bằng `isExported`.
5. Nếu lỗi xảy ra khi dùng reflection để truy cập thành viên không public, kiểm tra package có open cho module gọi không bằng `isOpen`.

Các tùy chọn JVM như `--add-reads`, `--add-exports` và `--add-opens` có thể bổ sung quan hệ khi chạy ứng dụng hoặc hỗ trợ chẩn đoán tương thích. Chúng lần lượt tác động đến readability, export và open. Với thiết kế ổn định, nên khai báo quan hệ cần thiết trong `module-info.java`; chỉ mở package nội bộ khi có lý do rõ ràng.

## 8. Những nhầm lẫn thường gặp

- **Dùng tên module như ID toàn cục**: cùng tên có thể xuất hiện trong các layer khác nhau. Kiểm tra module instance và layer khi cần phân biệt.
- **Coi `Module` là `ClassLoader`**: một loader có thể định nghĩa nhiều module; một module có class loader riêng được trả về bởi `getClassLoader()`.
- **Coi `requires` là đủ để truy cập mọi package**: readability không thay thế exports.
- **Coi exports và opens giống nhau**: exports phục vụ truy cập API public; opens phục vụ deep reflection.
- **Giả định module nào cũng có descriptor**: unnamed module trả về `null` từ `getDescriptor()`.
- **Chỉ log tên module khi debug plugin**: hãy log thêm layer và class loader để hiểu module instance và nguồn định nghĩa class.

## Ghi nhớ

`java.lang.Module` là góc nhìn runtime về một module instance. `getName()` cho biết tên, `getLayer()` cho biết layer chứa module, `getClassLoader()` cho biết loader định nghĩa module, còn `canRead`, `isExported` và `isOpen` giúp kiểm tra các quan hệ truy cập. Khi làm việc với nhiều module layer, tên module không đủ để nhận diện duy nhất một module instance; hãy kiểm tra chính đối tượng `Module` và ngữ cảnh layer của nó.

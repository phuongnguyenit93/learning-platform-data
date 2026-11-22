# Quyền điều chỉnh quan hệ mô-đun qua ModuleLayer.Controller

## 1. Mục tiêu

Java Platform Module System (JPMS) xác định module nào đọc được module nào, package nào được export và package nào được mở cho reflection. Những quan hệ này thường được khai báo tĩnh trong module-info.java. Tuy nhiên, ứng dụng có thể cần nạp plugin hoặc module bổ sung sau khi khởi động. Trong trường hợp đó, cấu hình module graph lúc build có thể chưa đủ.

ModuleLayer.Controller là đối tượng điều khiển được trả về khi tạo module layer bằng các API defineModules của ModuleLayer. Controller cho phép thay đổi một số quan hệ truy cập của các module thuộc layer mà nó quản lý trong runtime.

Các thao tác chính:

- addReads: cho phép module nguồn đọc module đích.
- addExports: export một package của module nguồn cho module đích.
- addOpens: mở một package của module nguồn cho module đích truy cập sâu bằng reflection.
- layer: lấy ModuleLayer do controller quản lý.

Trong JDK hiện hành, Controller còn có enableNativeAccess cho module cần quyền truy cập native. Quyền này độc lập với reads, exports và opens.

Controller hữu ích cho hệ thống plugin, module được nạp động và framework cần điều chỉnh quyền truy cập có kiểm soát. Đây không phải cơ chế thay thế toàn bộ module-info.java và cũng không phải sandbox bảo mật cho mã không tin cậy.

## 2. Phân biệt module, configuration, layer và controller

| Thành phần | Vai trò |
|---|---|
| ModuleDescriptor | Mô tả tên module, requires, exports, opens, uses và provides |
| Configuration | Kết quả resolve module dependency graph từ các ModuleFinder |
| ModuleLayer | Tập module đã được định nghĩa và gắn với class loader trong runtime |
| ModuleLayer.Controller | Quyền điều khiển các quan hệ truy cập của module được định nghĩa trong layer tương ứng |

ModuleDescriptor mô tả cấu hình của module. Configuration giải quyết phụ thuộc giữa các module. ModuleLayer tạo các đối tượng Module thực tế và class loader để nạp class. Controller là capability cho phép ứng dụng điều chỉnh một số quan hệ của các module trong layer sau khi layer được tạo.

Một ModuleLayer có thể có parent layer. Các module của layer con có thể đọc module ở parent theo module graph đã resolve. Controller của layer con chỉ được điều chỉnh module nguồn thuộc chính layer con mà controller quản lý; nó không thể dùng để sửa module nguồn thuộc boot layer hoặc parent layer.

## 3. Ba loại quan hệ cần phân biệt

### 3.1. Readability — addReads

Một module cần đọc module khác trước khi có thể sử dụng các kiểu public mà module kia cung cấp và package đã được export phù hợp.

~~~java
controller.addReads(sourceModule, targetModule);
~~~

Lệnh này thêm quan hệ để sourceModule đọc targetModule. Nó không tự export package nào của targetModule và cũng không mở package cho reflection.

Ví dụ: plugin module được nạp sau khi ứng dụng khởi động cần đọc một module API đã tồn tại. Controller có thể thêm cạnh readability từ plugin module tới module API.

### 3.2. Export — addExports

Exports cho phép module đích truy cập các public type trong package được export của module nguồn:

~~~java
controller.addExports(
    sourceModule,
    "com.acme.plugin.api",
    targetModule
);
~~~

Đây là quyền truy cập theo quy tắc ngôn ngữ Java đối với public type và public member. Nó không cho phép reflection truy cập tùy ý vào private field hoặc private method.

Nếu package đã được export tĩnh trong module-info.java cho module đích, không cần thêm export động cho cùng quan hệ đó.

### 3.3. Open — addOpens

Opens cho phép module đích dùng reflection sâu trên package của module nguồn, bao gồm truy cập các thành viên không public khi các điều kiện của core reflection được đáp ứng:

~~~java
controller.addOpens(
    sourceModule,
    "com.acme.plugin.internal",
    targetModule
);
~~~

addOpens thường cần cho dependency injection, object mapper, serializer, ORM hoặc framework cần truy cập private member bằng reflection.

opens không tương đương exports. Một package được mở cho reflection không vì thế trở thành API public có thể import và gọi khi biên dịch. Ngược lại, exports cũng không tự cho phép setAccessible trên private member của package.

### Bảng so sánh

| API | Quan hệ được thêm | Dùng khi |
|---|---|---|
| addReads(source, target) | source đọc target | Source cần đọc kiểu trong target |
| addExports(source, package, target) | source export package cho target | Target cần truy cập public type/member |
| addOpens(source, package, target) | source mở package cho target | Target cần deep reflection |

Các quan hệ có hướng. addReads(A, B) không khiến B đọc A. addExports(A, p, B) và addOpens(A, p, B) chỉ cấp quyền cho B đối với package p của A.

## 4. Tạo ModuleLayer.Controller

Các phương thức static defineModules của ModuleLayer trả về Controller. Ví dụ thường dùng là defineModulesWithOneLoader:

~~~java
ModuleLayer.Controller controller =
    ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader()
    );

ModuleLayer pluginLayer = controller.layer();
~~~

Tham số:

- configuration là kết quả resolve các module cần nạp.
- List.of(ModuleLayer.boot()) là danh sách parent layer.
- ClassLoader.getSystemClassLoader() là parent class loader dùng khi định nghĩa layer.
- controller.layer() trả về layer mới đã được định nghĩa.

Các lựa chọn tạo layer:

| API | Cách gắn class loader |
|---|---|
| defineModulesWithOneLoader | Các module mới dùng chung một class loader cho layer |
| defineModulesWithManyLoaders | Mỗi module mới có class loader riêng |
| defineModules | Ứng dụng cung cấp Function ánh xạ tên module sang class loader |

Chọn one loader khi các module plugin cần chia sẻ cách nạp class trong cùng một layer và không cần cô lập loader riêng. Chọn many loaders khi muốn mỗi module có loader riêng, ví dụ cần kiểm soát vòng đời hoặc xung đột class. Dùng defineModules khi hệ thống có chính sách class loader đặc thù.

Các phương thức instance cùng tên trên một ModuleLayer có thể trả về ModuleLayer trực tiếp. Nếu cần Controller để điều chỉnh quan hệ truy cập, dùng overload static nhận danh sách parent layer.

## 5. Ví dụ điều chỉnh reads, exports và opens

Giả sử ứng dụng có một module plugin được biên dịch riêng. Module plugin không export package nội bộ:

~~~java
module com.acme.plugin {
}
~~~

Lớp trong package nội bộ:

~~~java
package com.acme.plugin.internal;

public final class PluginApi {
    private static final String secret = "module-private";

    private PluginApi() {
    }

    public static String message() {
        return "Hello from dynamic module";
    }
}
~~~

Ứng dụng chính chạy trên classpath và tạo layer cho plugin. Sau đó ứng dụng thêm các quan hệ cần thiết bằng controller:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public final class Main {
    public static void main(String[] args) throws Exception {
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));

        Configuration configuration =
            ModuleLayer.boot().configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("com.acme.plugin")
            );

        ModuleLayer.Controller controller =
            ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader()
            );

        ModuleLayer layer = controller.layer();

        Module plugin = layer.findModule("com.acme.plugin")
            .orElseThrow();

        Module caller = Main.class.getModule();
        String packageName = "com.acme.plugin.internal";

        System.out.println("before.reads=" + plugin.canRead(caller));
        System.out.println(
            "before.exported=" + plugin.isExported(packageName, caller)
        );
        System.out.println(
            "before.open=" + plugin.isOpen(packageName, caller)
        );

        controller.addReads(plugin, caller);
        controller.addExports(plugin, packageName, caller);
        controller.addOpens(plugin, packageName, caller);

        Class<?> api = layer.findLoader("com.acme.plugin")
            .loadClass(packageName + ".PluginApi");

        Method message = api.getMethod("message");
        Field secret = api.getDeclaredField("secret");
        secret.setAccessible(true);

        System.out.println("after.reads=" + plugin.canRead(caller));
        System.out.println(
            "after.exported=" + plugin.isExported(packageName, caller)
        );
        System.out.println(
            "after.open=" + plugin.isOpen(packageName, caller)
        );
        System.out.println("message=" + message.invoke(null));
        System.out.println("secret=" + secret.get(null));
    }
}
~~~

Giải thích:

1. ModuleFinder.of(Path.of("mods")) tìm các module đã được biên dịch trong thư mục mods.
2. resolve tạo Configuration từ boot configuration và module plugin được chọn làm root.
3. defineModulesWithOneLoader tạo layer con và trả về controller.
4. controller.layer() lấy layer mới.
5. findModule tìm module plugin trong layer.
6. addReads thêm quan hệ đọc từ plugin tới module chứa Main.
7. addExports cho phép module chứa Main truy cập public type trong package nội bộ.
8. addOpens cho phép module chứa Main truy cập private member qua reflection.
9. findLoader lấy class loader của module plugin để nạp PluginApi.

Trong ví dụ, module đích là unnamed module chứa Main vì Main chạy trên classpath. Trong ứng dụng modular thực tế, nên truyền module đích cụ thể của framework hoặc module ứng dụng cần quyền truy cập.

## 6. Biên dịch và chạy ví dụ

Cấu trúc thư mục:

~~~text
project/
├── src/
│   └── com.acme.plugin/
│       ├── module-info.java
│       └── com/acme/plugin/internal/PluginApi.java
├── mods/
├── app-out/
└── Main.java
~~~

Biên dịch module plugin theo Java 17:

~~~bash
mkdir -p mods app-out

javac --release 17 \
  --module-source-path src \
  -d mods \
  -m com.acme.plugin
~~~

Biên dịch ứng dụng khởi chạy:

~~~bash
javac --release 17 -d app-out Main.java
~~~

Chạy từ thư mục project:

~~~bash
java -cp app-out Main
~~~

Output:

~~~text
before.reads=false
before.exported=false
before.open=false
after.reads=true
after.exported=true
after.open=true
message=Hello from dynamic module
secret=module-private
~~~

Output cho thấy trước khi điều chỉnh, plugin không đọc module chứa Main, package chưa được export và chưa được mở cho module đó. Sau khi gọi controller, cả ba quan hệ đều được thiết lập và các thao tác truy cập tương ứng thành công.

## 7. Phạm vi và giới hạn của Controller

Controller chỉ cho phép điều chỉnh module nguồn thuộc layer do chính controller quản lý. Đối số target có thể là module khác, ví dụ module trong parent layer hoặc unnamed module, nhưng source phải thuộc controlled layer.

Nếu source không nằm trong layer đó, controller ném IllegalArgumentException. Nếu package được export hoặc mở không tồn tại trong source module, thao tác cũng không hợp lệ.

Ví dụ kiểm tra giới hạn layer:

~~~java
Module bootModule = Object.class.getModule();

try {
    controller.addReads(bootModule, caller);
} catch (IllegalArgumentException expected) {
    System.out.println("source outside controlled layer");
}
~~~

java.base thuộc boot layer, không thuộc layer plugin mới. Controller của plugin layer vì vậy không thể sửa quan hệ đọc của java.base.

Một số lưu ý khác:

- Controller chỉ thêm quan hệ truy cập; không xóa các quan hệ đã tồn tại.
- Thay đổi chỉ áp dụng trong runtime của tiến trình hiện tại.
- Controller không sửa module-info.class, source code hoặc artifact JAR.
- Thay đổi không giúp mã nguồn biên dịch được nếu package chưa export tại thời điểm compile. Cần khai báo module descriptor phù hợp hoặc thiết kế bước build riêng.
- Controller không tự resolve dependency bị thiếu. Module graph phải resolve thành công trước khi layer được tạo.
- Controller không tự tải module mới vào layer đã tồn tại. Muốn nạp tập module khác, hãy resolve và tạo layer mới.
- Controller không cung cấp cơ chế rollback các thay đổi đã áp dụng. Hãy xác định quyền cần cấp trước khi gọi.
- ModuleLayer và controller không phải sandbox cách ly mã độc. Mã plugin chạy trong cùng tiến trình vẫn có thể sử dụng các API mà runtime cấp cho nó.

## 8. Không nhầm Controller với Module API

Lớp Module cũng có các phương thức addReads, addExports, addOpens và addUses. Đây là API trên một Module instance và có quy tắc caller riêng.

ModuleLayer.Controller được thiết kế để framework hoặc launcher kiểm soát các module nguồn thuộc layer mà nó vừa tạo. Vì vậy, khi ứng dụng tạo module layer động, giữ controller ở thành phần quản lý layer và chỉ cấp nó cho code đáng tin cậy.

Một điểm dễ nhầm: ModuleLayer.Controller không có phương thức addUses. Trong JDK hiện đại, Module có phương thức addUses(Class<?>) riêng. Nếu consumer cần dùng service, cách khai báo tĩnh rõ ràng vẫn là uses trong module-info.java; provider khai báo provides. Không tự thêm một API addUses vào Controller vì API đó không tồn tại trên lớp này.

Tương tự, Controller không có addExportsToAllUnnamed hay addOpensToAllUnnamed. Nó cấp quyền cho một module đích cụ thể qua addExports và addOpens. Nếu cần mở cho nhiều module, hãy xác định từng module đích và cấp quyền có chủ đích.

## 9. addOpens và framework reflection

Framework như dependency injection, ORM hoặc serializer có thể cần truy cập private field và constructor. Trong JPMS, public API và deep reflection là hai quyền riêng.

Ví dụ module ứng dụng mở một package cho framework ngay từ descriptor:

~~~java
module com.acme.model {
    opens com.acme.model.entity to com.acme.orm;
}
~~~

Nếu package chỉ cần mở tại runtime sau khi plugin layer được tạo, controller có thể cấp quyền:

~~~java
controller.addOpens(
    modelModule,
    "com.acme.model.entity",
    ormModule
);
~~~

Nên ưu tiên opens có giới hạn module đích. Mở package cho tất cả module làm tăng bề mặt truy cập và khiến ranh giới encapsulation khó kiểm soát.

Nếu chỉ cần gọi public API, dùng exports thay vì opens. Nếu framework cần đọc hoặc ghi private field bằng reflection, dùng opens. Không thêm cả hai nếu chỉ một quyền đáp ứng yêu cầu.

## 10. ModuleLayer và ServiceLoader

Module layer thường được dùng để nạp plugin cung cấp service. Consumer khai báo uses và provider khai báo provides trong module descriptor. Sau khi tạo layer, ứng dụng có thể khám phá provider trong layer đó:

~~~java
ServiceLoader<PluginService> services =
    ServiceLoader.load(pluginLayer, PluginService.class);

for (PluginService service : services) {
    service.start();
}
~~~

Module tiêu thụ service vẫn cần khai báo uses trong module descriptor hoặc đáp ứng điều kiện của API Module.addUses. Module provider phải được resolve vào layer và khai báo provides đúng service type.

Controller không tự đăng ký provider, không thay thế uses/provides và không làm cho module chưa resolve trở thành provider. Vai trò của nó là điều chỉnh quan hệ đọc/export/open khi module layer đã được tạo.

Nếu plugin layer có nhiều provider, hãy xử lý trường hợp không có provider và ServiceConfigurationError riêng biệt. Provider discovery có thể lazy; lỗi chỉ xuất hiện khi duyệt iterator hoặc stream.

## 11. Quản lý vòng đời và quyền truy cập

Trong hệ thống plugin, nên có một thành phần quản lý vòng đời module layer:

1. Xác định module plugin và phiên bản API tương thích.
2. Resolve module graph trước khi định nghĩa layer.
3. Tạo layer bằng một trong các defineModules* phù hợp.
4. Giữ controller trong thành phần quản lý tin cậy.
5. Chỉ thêm reads, exports hoặc opens tối thiểu cho module đích đã xác định.
6. Khởi tạo service/plugin và theo dõi lỗi nạp.
7. Khi cần thay đổi tập module, tạo layer mới và chuyển traffic theo kế hoạch.
8. Loại bỏ tham chiếu tới layer, class loader và plugin instance khi không còn sử dụng.

Java không cung cấp thao tác unload một module riêng lẻ khỏi ModuleLayer. Class có thể được thu hồi khi class loader và mọi đối tượng liên quan không còn được tham chiếu, nhưng garbage collection không phải thao tác đồng bộ hay được bảo đảm xảy ra ngay. Thiết kế plugin cần tránh giữ static reference, thread, executor hoặc callback tới class loader cũ.

Không truyền controller cho plugin không tin cậy. Bất kỳ code nào có controller đều có thể thay đổi các quan hệ mà controller cho phép trong layer. Hãy xem controller như một capability nhạy cảm và giữ nó trong bootstrap hoặc plugin manager.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| IllegalArgumentException: module not in layer | Source module không thuộc layer của controller | Dùng controller được trả về khi tạo đúng layer chứa source |
| Package không tồn tại | Tên package truyền cho addExports/addOpens sai hoặc module không chứa package đó | Kiểm tra Module.getPackages() và tên package |
| ClassNotFoundException khi nạp plugin | Module không được resolve hoặc dùng sai class loader | Kiểm tra ModuleFinder, Configuration và layer.findLoader |
| IllegalAccessException khi gọi public method | Package chưa export cho module gọi hoặc module gọi không đọc source | Kiểm tra addReads và addExports |
| InaccessibleObjectException khi setAccessible | Package chưa open cho module thực hiện reflection | Cấp addOpens cho đúng module đích |
| LayerInstantiationException | Module graph có dependency thiếu, tên trùng hoặc split package | Kiểm tra configuration và module path |
| Controller không sửa được boot module | Source thuộc parent/boot layer, ngoài phạm vi controller | Tạo layer phù hợp hoặc thiết kế quyền tĩnh từ module nguồn |
| Thay đổi không có tác dụng lúc compile | Controller chỉ thay đổi runtime | Khai báo requires/exports phù hợp trong module descriptor hoặc điều chỉnh cấu hình build |

Không dùng addOpens để chữa mọi lỗi truy cập. Hãy xác định lỗi nằm ở readability, export hay deep reflection rồi chỉ cấp đúng quyền cần thiết.

## 13. Checklist áp dụng

- [ ] Module plugin được resolve thành công trước khi tạo layer.
- [ ] Chọn one loader, many loaders hoặc custom loader theo kiến trúc.
- [ ] Dùng static defineModules* khi cần giữ ModuleLayer.Controller.
- [ ] Source module truyền vào controller thuộc layer mà controller quản lý.
- [ ] addReads chỉ được dùng khi source thực sự cần đọc target.
- [ ] addExports chỉ mở public API cần thiết cho module đích.
- [ ] addOpens chỉ dùng khi framework cần deep reflection.
- [ ] Controller được giữ bởi thành phần quản lý tin cậy.
- [ ] Không coi ModuleLayer là sandbox bảo mật.
- [ ] Kiểm thử module graph và plugin trên JDK runtime thực tế.
- [ ] Thiết kế vòng đời class loader và plugin để tránh giữ reference không cần thiết.

## Tài liệu tham khảo

- [ModuleLayer API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ModuleLayer.html)
- [ModuleLayer.Controller API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ModuleLayer.Controller.html)
- [Module API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Module.html)
- [Configuration API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/Configuration.html)
- [ModuleFinder API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/ModuleFinder.html)
- [The Java Platform Module System — JEP 261](https://openjdk.org/jeps/261)

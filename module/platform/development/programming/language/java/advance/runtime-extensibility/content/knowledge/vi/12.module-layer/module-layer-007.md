# Điều chỉnh reads, exports và opens bằng ModuleLayer.Controller trong phạm vi cho phép

Khi Java chạy với **Java Platform Module System (JPMS)**, quan hệ giữa các module không chỉ phụ thuộc vào class path hoặc tên package. Ba thông tin quan trọng quyết định khả năng tương tác là:

- Module nào **đọc** (reads) module nào: một quan hệ trong module graph.
- Package nào được **export** cho module khác: cho phép truy cập các kiểu và thành viên `public` theo cơ chế truy cập Java thông thường, khi các điều kiện truy cập khác thỏa mãn.
- Package nào được **open** cho module khác: cho phép truy cập **phản chiếu sâu** bằng các API như `setAccessible(true)`, kể cả thành viên không `public`, nếu các điều kiện reflective access tương ứng được thỏa mãn.

`ModuleLayer.Controller` là API từ Java 9 cho phép **bên tạo một module layer mới** bổ sung những quan hệ đó ở runtime đối với **module thuộc chính layer mà controller quản lý**. Nó hữu ích cho hệ thống plugin, ứng dụng tạo module layer riêng và các framework tin cậy cần cấp quyền truy cập có giới hạn.

Quy tắc trọng tâm:

> `Controller.addReads(source, target)`, `Controller.addExports(source, packageName, target)` và `Controller.addOpens(source, packageName, target)` chỉ có thể chỉnh quan hệ **đi ra từ module nguồn thuộc layer đang được điều khiển**. Controller không được dùng để sửa tùy ý module nguồn thuộc boot layer, parent layer hoặc một layer độc lập khác.

Các thao tác này **bổ sung quyền ở runtime**, không viết lại `module-info.java`, không sửa `ModuleDescriptor` gốc và không cấp khả năng thu hồi quyền sau đó. Vì thế, controller phải được giữ trong code hạ tầng đáng tin cậy, không trao trực tiếp cho plugin không tin cậy.

## 1. Vì sao cần controller khi đã có module-info.java?

Trong một explicit named module, descriptor mô tả quan hệ bình thường:

~~~java
module sample.consumer {
    requires sample.provider;
}
~~~

~~~java
module sample.provider {
    exports sample.provider.api to sample.consumer;
    opens sample.provider.internal to sample.framework;
}
~~~

Đây là **hai đoạn `module-info.java` minh họa độc lập**, chưa phải cấu hình của ví dụ runnable phía dưới. `requires` quyết định readability khi tạo configuration; `exports` cho phép truy cập API công khai; `opens` cho phép framework được chỉ định truy cập sâu bằng reflection.

Nhưng nhiều hệ thống mở rộng không biết toàn bộ module đích khi xây dựng mã nguồn:

1. Host có thể nạp module plugin sau khi ứng dụng đã chạy, từ một thư mục do người dùng lựa chọn.
2. Host có thể tạo `ModuleLayer` mới ở runtime và muốn cấp quyền riêng giữa các module trong layer đó.
3. Framework được host kiểm soát có thể cần đọc package nội bộ của plugin qua reflection mà plugin không muốn `opens ...` cho mọi module.
4. Ứng dụng có thể muốn bổ sung một cạnh readability cho một cặp module đã được resolve nhưng chưa có quan hệ `requires` tĩnh.

`ModuleLayer.Controller` phục vụ việc **cấu hình access graph của layer mới** dưới quyền bên tạo layer. Đây là công cụ điều phối có phạm vi giới hạn; nó không thay thế cách thiết kế `module-info.java` rõ ràng khi module dependencies là tĩnh và đã biết từ trước.

## 2. Ba thao tác và ý nghĩa chính xác

| Phương thức | Thay đổi trên module nguồn | Điều nó cho phép | Điều nó không tự làm |
| --- | --- | --- | --- |
| `addReads(source, target)` | Thêm quan hệ `source` đọc `target` | Kiểm tra `source.canRead(target)` có thể chuyển sang `true` | Không tự export package của `target`; không thêm class/module vào layer |
| `addExports(source, "p.q", target)` | Export package `p.q` của `source` riêng cho `target` | `source.isExported("p.q", target)` thành `true`; hỗ trợ truy cập công khai theo các điều kiện khác | Không mặc nhiên cho phép reflection sâu vào private member; không tự tạo cạnh reads ngược chiều |
| `addOpens(source, "p.q", target)` | Open package `p.q` của `source` riêng cho `target` | `source.isOpen("p.q", target)` thành `true`; hỗ trợ `setAccessible(true)` và reflection sâu phù hợp | Không mở package cho tất cả module; không tự tải/khởi tạo plugin hay cho phép tùy tiện truy cập module khác |

Ba lời gọi đều trả về chính `ModuleLayer.Controller` nên có thể nối chuỗi:

~~~java
controller.addReads(consumer, provider)
          .addExports(provider, "sample.provider.api", consumer)
          .addOpens(provider, "sample.provider.internal", framework);
~~~

Trong đoạn trên, **module nguồn của lời gọi thứ nhất là `consumer`**, còn nguồn của hai lời gọi sau là `provider`. Cả hai phải thuộc **layer do `controller` quản lý**. `framework` hoặc `consumer` ở vị trí **target** có thể là module khác tùy kịch bản, kể cả module thuộc parent layer hoặc unnamed module, nhưng việc mở/export phải áp dụng đúng package của module nguồn.

### 2.1. Readability không đồng nghĩa access vào mọi class

Chỉ thêm:

~~~java
controller.addReads(consumer, provider);
~~~

cho phép `consumer` **đọc** `provider`, nhưng không tự làm một package chưa export trở nên truy cập công khai. Nếu `provider` chứa `sample.provider.api.PublicFeature` mà package đó chưa export, thông thường `consumer` vẫn chưa thể liên kết vào class public đó qua cơ chế truy cập thông thường.

Ngược lại, `addExports(provider, "sample.provider.api", consumer)` mở quyền public access đến package theo hướng `provider → consumer`, nhưng cũng không tự thêm quan hệ `consumer → provider`. Để module consumer dùng public API bình thường, cần xét **cả readability và export**.

Thêm quan hệ reads ở runtime cũng không sửa lỗi compile-time khi một source file đang import kiểu từ module mà `javac` chưa cho phép đọc. Với code nguồn có dependency tĩnh, hãy khai báo `requires`, cấu hình compiler phù hợp hoặc thiết kế interface chung; controller hoạt động sau khi chương trình bắt đầu tạo layer.

### 2.2. Export khác open

`exports p.q` được thiết kế cho **truy cập public API thông thường**. Nó không trao quyền cho một framework gọi `setAccessible(true)` để truy cập private field trong một package bị đóng.

`opens p.q` dành cho **phản chiếu sâu**, ví dụ dependency injection, serializer hoặc framework khởi tạo object. Với `addOpens`, chỉ **target module được chọn** nhận quyền mở package. Tránh suy diễn rằng mở cho một module sẽ mở cho toàn bộ JVM. Với reflection, các kiểm tra readability có quy ước riêng; điều kiện quan trọng đối với deep reflection của private member trong ví dụ là package được open cho module thực hiện lời gọi.

Ví dụ một package có class với private field:

~~~java
package sample.provider.internal;

public final class Secrets {
    private static final String TOKEN = "layer-secret";
}
~~~

Nếu host không được open package này, `Field.setAccessible(true)` có thể ném `InaccessibleObjectException`. Sau khi host được open package cho **đúng module của mình**, reflective access phù hợp có thể thành công.

Không nên dùng `addOpens` như cách “sửa nhanh” mọi lỗi import hoặc classloading: đó là quyền truy cập sâu, có hậu quả về đóng gói và bảo mật thông tin nội bộ.

### 2.3. Các thao tác là bổ sung, không phải thay thế

Theo API Java 17:

- `addReads` không làm gì nếu `source` đã đọc `target`.
- `addExports` không làm gì nếu package đã được export ít nhất cho `target`.
- `addOpens` không làm gì nếu package đã được open ít nhất cho `target`.

Không có `removeReads`, `removeExports` hoặc `removeOpens` trong `ModuleLayer.Controller`. Sau khi bổ sung một quan hệ cho các `Module` đang hoạt động, không thể dùng controller để thu hồi đúng quyền đó. Nếu cần thay policy hoàn toàn, thường phải xây một thế hệ layer mới và ngừng sử dụng layer cũ khi an toàn; tạo layer mới cũng không cưỡng bức JVM hủy tham chiếu đến các module/class cũ.

## 3. Controller được tạo như thế nào?

Hai nhóm API trông khá giống nhau nhưng khác về kết quả:

| Cách gọi | Giá trị trả về | Có controller để điều chỉnh thêm? |
| --- | --- | --- |
| `parentLayer.defineModulesWithOneLoader(configuration, parentLoader)` | `ModuleLayer` | Không trả controller |
| `parentLayer.defineModulesWithManyLoaders(configuration, parentLoader)` | `ModuleLayer` | Không trả controller |
| `parentLayer.defineModules(configuration, loaderFunction)` | `ModuleLayer` | Không trả controller |
| **`ModuleLayer.defineModulesWithOneLoader(configuration, parentLayers, parentLoader)`** | **`ModuleLayer.Controller`** | **Có** |
| **`ModuleLayer.defineModulesWithManyLoaders(configuration, parentLayers, parentLoader)`** | **`ModuleLayer.Controller`** | **Có** |
| **`ModuleLayer.defineModules(configuration, parentLayers, loaderFunction)`** | **`ModuleLayer.Controller`** | **Có** |

Các overload **static** nhận danh sách parent layers là đường tạo layer trả controller. Sau đó lấy layer mới qua:

~~~java
ModuleLayer.Controller controller = ModuleLayer.defineModulesWithOneLoader(
        configuration,
        List.of(ModuleLayer.boot()),
        ClassLoader.getSystemClassLoader());

ModuleLayer layer = controller.layer();
~~~

Đây là snippet minh họa; biến `configuration` phải được resolve đúng theo các parent configurations tương ứng. Không thể lấy một `ModuleLayer` tùy ý đã tạo từ trước rồi “xin lại controller” bằng một API chuẩn tương đương `getController()`.

### 3.1. Trình tự dựng module layer

Thông thường host thực hiện:

1. Lựa chọn `ModuleFinder` tìm các module JAR/exploded modules.
2. Resolve thành `Configuration` với parent configuration, danh sách root modules phù hợp và dependency được kiểm tra.
3. Dùng **static** `ModuleLayer.defineModulesWith...` để tạo một layer kèm controller.
4. Lấy những `Module` cụ thể từ `controller.layer().findModule(name)`; xác nhận đúng layer/module identity.
5. Cấp quyền **nhỏ nhất cần thiết** với `addReads`, `addExports`, `addOpens`.
6. Sau khi cấu hình xong mới cho các thành phần trong layer sử dụng API hoặc chạy code plugin.

Ví dụ skeleton:

~~~java
ModuleLayer boot = ModuleLayer.boot();
ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
Configuration cf = boot.configuration().resolve(
        finder, ModuleFinder.of(), Set.of("sample.provider", "sample.consumer"));

ModuleLayer.Controller ctl = ModuleLayer.defineModulesWithOneLoader(
        cf, List.of(boot), ClassLoader.getSystemClassLoader());
ModuleLayer child = ctl.layer();
~~~

Đây là **đoạn Java minh họa cần imports**, không phải chương trình độc lập; phần tiếp theo có một chương trình đầy đủ.

`defineModulesWithOneLoader` dùng một class loader mới cho các module được định nghĩa trong layer, còn `defineModulesWithManyLoaders` dùng loader riêng theo module. Hai lựa chọn ảnh hưởng đến cô lập code, package/loader constraints và khả năng tải lớp. Việc thêm reads/exports/opens **không** tự bổ sung URL/JAR, không sửa chiến lược classloading và không giải quyết lỗi `ClassNotFoundException` do thiếu artifact.

## 4. Ví dụ Java 17 đầy đủ: điều chỉnh ba quyền trên layer mới

Ví dụ này cố ý đặt các module vào cùng một **child layer**, nhưng không khai báo `requires` hay `exports`/`opens` giữa chúng. Host nằm trên classpath (unnamed module), giữ controller và làm người gọi reflection.

Mục tiêu quan sát:

- Ban đầu `consumer.canRead(provider)`, `provider.isExported(..., consumer)` và `provider.isOpen(..., host)` đều `false`.
- Ban đầu host không thể dùng `setAccessible(true)` để đọc private field `TOKEN` của module provider.
- Sau ba lời gọi controller, cả ba phép kiểm tra chuyển thành `true` và reflective access thành công.
- Descriptor của module provider vẫn không có `exports`.
- Thử sửa `java.base` của boot layer bằng controller của child layer hoặc export một package không tồn tại bị từ chối.

### 4.1. Cấu trúc tệp

~~~text
src/
├── sample.provider/
│   ├── module-info.java
│   └── sample/provider/
│       ├── api/Visible.java
│       └── internal/Secrets.java
└── sample.consumer/
    ├── module-info.java
    └── sample/consumer/Anchor.java
host/
└── LayerControllerDemo.java
~~~

Tệp `src/sample.provider/module-info.java`:

~~~java
module sample.provider { }
~~~

Descriptor không export hoặc open package nào. Hai package của module đều có class thực sự nên được compiler ghi nhận là các package thuộc module.

Tệp `src/sample.provider/sample/provider/api/Visible.java`:

~~~java
package sample.provider.api;

public final class Visible {
    public static String ping() { return "public"; }
}
~~~

`Visible` là public class nhưng package `sample.provider.api` **chưa export**. Java không vì modifier `public` mà cho mọi named module khác truy cập class thuộc package không export.

Tệp `src/sample.provider/sample/provider/internal/Secrets.java`:

~~~java
package sample.provider.internal;

public final class Secrets {
    private static final String TOKEN = "layer-secret";
}
~~~

Private static field `TOKEN` được dùng để kiểm tra khả năng deep reflection khi package chưa mở và khi đã được open cho module host.

Tệp `src/sample.consumer/module-info.java`:

~~~java
module sample.consumer { }
~~~

Module consumer chưa `requires sample.provider;`. Mục đích của bài là **cấp readability bằng controller tại runtime**, chứ không tạo dependency tĩnh trong descriptor.

Tệp `src/sample.consumer/sample/consumer/Anchor.java`:

~~~java
package sample.consumer;

public final class Anchor {}
~~~

Class `Anchor` giúp ví dụ có class thực sự trong module consumer. Nó không cần import hay gọi `Visible`; host đang minh họa việc thay đổi module graph và kiểm tra metadata runtime.

### 4.2. Chương trình host tạo layer và điều khiển quan hệ

Tệp `host/LayerControllerDemo.java`:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public final class LayerControllerDemo {
    public static void main(String[] args) throws Exception {
        ModuleLayer parent = ModuleLayer.boot();
        Configuration configuration = parent.configuration().resolve(
                ModuleFinder.of(Path.of("mods")), ModuleFinder.of(),
                Set.of("sample.provider", "sample.consumer"));

        ModuleLayer.Controller controller =
                ModuleLayer.defineModulesWithOneLoader(
                        configuration, List.of(parent), ClassLoader.getSystemClassLoader());
        ModuleLayer layer = controller.layer();
        Module provider = layer.findModule("sample.provider").orElseThrow();
        Module consumer = layer.findModule("sample.consumer").orElseThrow();
        Module host = LayerControllerDemo.class.getModule();

        Field token = layer.findLoader("sample.provider")
                .loadClass("sample.provider.internal.Secrets")
                .getDeclaredField("TOKEN");

        System.out.println("before reads=" + consumer.canRead(provider));
        System.out.println("before exports="
                + provider.isExported("sample.provider.api", consumer));
        System.out.println("before opens="
                + provider.isOpen("sample.provider.internal", host));
        try {
            token.setAccessible(true);
            System.out.println("deep reflection before=allowed");
        } catch (InaccessibleObjectException expected) {
            System.out.println("deep reflection before=denied");
        }

        controller.addReads(consumer, provider)
                .addExports(provider, "sample.provider.api", consumer)
                .addOpens(provider, "sample.provider.internal", host);

        System.out.println("after reads=" + consumer.canRead(provider));
        System.out.println("after exports="
                + provider.isExported("sample.provider.api", consumer));
        System.out.println("after opens="
                + provider.isOpen("sample.provider.internal", host));
        token.setAccessible(true);
        System.out.println("token=" + token.get(null));
        System.out.println("descriptor exports unchanged="
                + provider.getDescriptor().exports().isEmpty());

        try {
            controller.addReads(String.class.getModule(), provider);
            System.out.println("parent source rejected=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("parent source rejected=true");
        }
        try {
            controller.addExports(provider, "missing.package", consumer);
            System.out.println("missing package rejected=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("missing package rejected=true");
        }
    }
}
~~~

Điểm kỹ thuật cần chú ý:

- `ModuleLayer.boot()` là parent layer; `ModuleFinder.of(Path.of("mods"))` chỉ tìm các module được biên dịch vào `mods`.
- `parent.configuration().resolve(...)` đưa hai root modules vào một resolved configuration mới. Vì consumer không khai báo `requires sample.provider`, nó chưa có cạnh reads.
- Static `ModuleLayer.defineModulesWithOneLoader(...)` trả **controller**, không chỉ trả layer.
- `layer.findModule(...)` lấy đúng các `Module` thuộc child layer; `String.class.getModule()` là `java.base` thuộc **boot layer**, nên không phải source hợp lệ cho controller này.
- `LayerControllerDemo.class.getModule()` là **unnamed module của host** trong lần chạy trên classpath. Nó là **target** được phép nhận opens; host không cần trở thành member của child layer.
- `token.setAccessible(true)` ở lần đầu thất bại vì package chưa được open cho host. Sau `addOpens` đúng target, lời gọi tương tự có thể truy cập private field.
- `provider.getDescriptor().exports().isEmpty()` vẫn `true` vì controller thay **động** trạng thái access runtime, không viết lại module descriptor.

### 4.3. Biên dịch và chạy

Tạo các thư mục/tệp đúng cây trên. Từ thư mục chứa `src` và `host`, chạy JDK 17 trở lên:

~~~bash
javac --release 17 --module-source-path src -d mods -m sample.provider,sample.consumer
javac --release 17 -d out-host host/LayerControllerDemo.java
java -cp out-host LayerControllerDemo
~~~

Ở ví dụ này `mods` **không cần** đặt trên `--module-path` lúc khởi động, vì chính chương trình dùng `ModuleFinder.of(Path.of("mods"))` để tìm và resolve module vào child layer. Host sử dụng classpath, còn plugin modules được tải theo layer mới.

Stdout đã kiểm chứng khi biên dịch với `--release 17` và chạy:

~~~text
before reads=false
before exports=false
before opens=false
deep reflection before=denied
after reads=true
after exports=true
after opens=true
token=layer-secret
descriptor exports unchanged=true
parent source rejected=true
missing package rejected=true
~~~

**Diễn giải theo từng bằng chứng:**

1. Ba giá trị `false` ban đầu xác nhận quan hệ reads/exports/opens chưa tồn tại giữa các `Module` được nêu trong code.
2. `deep reflection before=denied` phản ánh việc JPMS từ chối phá đóng gói private member của package chưa open.
3. Các giá trị `true` sau khi gọi controller chứng minh ba quan hệ runtime được bổ sung.
4. `token=layer-secret` xác nhận deep reflection hoạt động sau khi cấp quyền open chỉ cho module host.
5. `descriptor exports unchanged=true` chứng minh metadata khai báo không bị thay đổi.
6. `parent source rejected=true` là bằng chứng về ranh giới quản lý: controller của child layer không điều chỉnh được module nguồn `java.base` của parent layer.
7. `missing package rejected=true` xác nhận không thể export tên package bất kỳ mà module nguồn không sở hữu.

Ví dụ cố tình **không** biên dịch source trong `sample.consumer` có import trực tiếp `sample.provider.api.Visible`. Chương trình đang chứng minh **điều chỉnh runtime access graph**. Với compile-time import thông thường, `javac` cũng cần được cấu hình các quan hệ modules tương ứng; controller được tạo khi chạy không quay ngược thời gian để thay đổi kết quả biên dịch.

## 5. Phạm vi chính xác mà controller được phép sửa

### 5.1. Source phải thuộc chính controlled layer

Ví dụ:

~~~text
boot layer
    java.base                  <-- không thể dùng làm source cho controller bên dưới
       |
       +---- child layer (controller.layer())
                sample.consumer  <-- source hợp lệ cho addReads
                sample.provider  <-- source hợp lệ cho addExports/addOpens
~~~

Trong mỗi lời gọi:

~~~java
controller.addReads(source, target);
controller.addExports(source, "some.package", target);
controller.addOpens(source, "some.package", target);
~~~

`source` phải là đối tượng `Module` thuộc `controller.layer()`. **Không** đủ nếu module chỉ có cùng tên chuỗi với một module thuộc layer đó. Hai layer khác nhau có thể chứa module trùng tên nhưng là các đối tượng `Module` và class khác nhau.

Đối với `addExports`/`addOpens`, `some.package` phải là **package thuộc module nguồn**. Tên package phải khớp chính xác; xuất tên package cha không tự áp dụng cho package con. Ví dụ `sample.provider` không phải tên thay thế của `sample.provider.internal`.

### 5.2. Target không có cùng giới hạn membership như source

Target của ba phương thức là module nhận quan hệ mới; API không yêu cầu target nằm cùng layer với source. Ví dụ bài viết cấp `opens` từ module nguồn trong child layer sang **unnamed module của host**. Điều này hợp lệ, trong khi việc lấy `java.base` làm **source** để cập nhật từ controller child layer không hợp lệ.

Điều kiện target tùy thao tác còn chịu các ràng buộc thông thường của module graph và API. Không nhầm “target có thể nằm bên ngoài layer” với “controller có quyền sửa bản thân target”: thêm `source.reads(target)` hoặc `source.exports(package, target)` **không** cấp cho host quyền cập nhật những exports/opens nội bộ của module target.

### 5.3. Quyền không chuyển tiếp tự động

Nếu `A` đọc `B` và `B` đọc `C`, không thể kết luận mọi quan hệ đọc và truy cập public API đều được truyền tới `A`. JPMS có khái niệm đọc theo `requires transitive` trong descriptor và các quy tắc khi resolve; một cạnh `addReads` đơn lẻ không đồng nghĩa “toàn bộ phụ thuộc của B đều công khai cho A”.

Tương tự, export `p` từ module `B` sang `A` không đồng nghĩa export `p` cho mọi module mà `A` đọc, và open `p` cho framework `F` không mở package cho mọi module bị framework gọi.

### 5.4. Không có API thu hồi trong Controller

Controller giữ quyền bổ sung edge/permission trong vòng đời module. API không cung cấp thao tác inverse. Đừng thiết kế cơ chế “mở package trong 5 mili-giây rồi đóng lại” bằng `addOpens`: Java không cung cấp `removeOpens` tương ứng ở đây.

Nếu cần cô lập provider theo phiên hoặc tenant, tạo layer/loader riêng theo chính sách và quản lý reference/lifecycle. Tuy nhiên một layer mới không xóa các đối tượng `Module`, `Class` hoặc instance của layer cũ nếu host vẫn giữ tham chiếu.

## 6. So sánh với Module.addReads/addExports/addOpens

Đối tượng `Module` cũng có các method như `Module.addReads`, `Module.addExports`, `Module.addOpens`, nhưng chúng có **ràng buộc với caller**: thông thường chỉ code trong module nguồn có thể tự cấp những quan hệ cho module của mình, nếu thỏa điều kiện API.

Controller là cơ chế mà **bên có quyền tạo layer mới** có thể dùng để điều chỉnh các module thuộc layer đó mà không cần code được thực thi từ chính từng module nguồn. Đó là khác biệt về **phạm vi quyền điều phối**, không phải tính năng vô hiệu hóa mọi giới hạn của JPMS.

| Trường hợp | Công cụ phù hợp |
| --- | --- |
| Module đã biết dependency public tại compile time | `requires` / `exports` trong `module-info.java` |
| Module chủ động mở package cho framework đã biết | `opens p.q to framework.module;` trong descriptor |
| Một module tự cấp quyền ở runtime theo hợp đồng của chính nó | `Module.addReads/addExports/addOpens`, khi caller hợp lệ |
| Host vừa tạo child layer và cần bổ sung quan hệ trong phạm vi layer đó | `ModuleLayer.Controller` |
| Điều chỉnh access cho source module thuộc boot/parent layer | Không thể dùng controller của child layer; xem lại kiến trúc/descriptor/cơ chế được chủ module hoặc launcher cho phép |

Tránh đồng nhất API `Controller` với tùy chọn JVM `--add-reads`, `--add-exports` và `--add-opens`. Các option launcher có phạm vi/lifecycle khác nhau và được cấu hình lúc khởi chạy; controller thao tác trên đối tượng `Module` của layer được tạo tại runtime.

## 7. Khác biệt giữa quyền access và việc tìm/resolve/nạp lớp

Một quan hệ module được bổ sung không tự giải quyết tất cả vấn đề runtime:

- **Resolve:** `Configuration.resolve` phải giải quyết được các module cần có trước khi tạo layer. `addReads` không làm một module chưa được resolve xuất hiện.
- **Class loading:** `ModuleLayer` ánh xạ module đến class loader. Nếu artifact/JAR không có hoặc class loader không thể tìm bytecode, thêm readability không sửa được `ClassNotFoundException`.
- **Readability:** module `A` cần read đúng module chứa `B` để truy cập kiểu qua liên kết thông thường.
- **Exports:** package chứa kiểu public cần export cho module truy cập (trừ các cơ chế truy cập đặc biệt có điều kiện riêng).
- **Opens/reflection:** private access qua reflection cần đúng package được open cho module của mã thực hiện thao tác reflective.
- **Service use/provision:** `uses`, `provides` và cơ chế `ServiceLoader` có hợp đồng riêng; việc thêm reads/exports không tự đăng ký một service provider mới.

Ví dụ lớp provider tồn tại nhưng không thể load do sai JAR vẫn không được giải quyết bằng cách gọi `addOpens`. Ngược lại, một class đã load được bằng loader vẫn có thể không được truy cập bởi code module khác vì module readability/package exports.

Thêm quyền động có thể phục vụ các lần liên kết và reflective access phù hợp từ thời điểm đó; không được suy ra nó đã “tái biên dịch” bytecode hoặc tự khôi phục những thao tác đã thất bại/khởi tạo dở trước khi thêm quyền.

## 8. Lỗi thường gặp và chính sách xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `IllegalArgumentException` từ `addReads` | `source` không thuộc đúng layer do controller quản lý | Kiểm tra `source.getLayer() == controller.layer()` và cách lấy Module |
| `IllegalArgumentException` từ `addExports`/`addOpens` | Source sai layer hoặc package không thuộc source | Kiểm tra đúng `Module` và tên package đầy đủ |
| `InaccessibleObjectException` khi `setAccessible(true)` | Package chưa open cho module thực hiện reflection | Cấp qualified opens đúng target hoặc sửa descriptor |
| `IllegalAccessException` lúc gọi reflection | Member/class không accessible theo chế độ hiện hành | Kiểm tra module của caller, exports/opens, và cách gọi reflection |
| `ClassNotFoundException` | Loader không tìm được class/JAR | Kiểm tra `ModuleFinder`, layer loader, module artifact; không chỉ chỉnh reads |
| `NoClassDefFoundError`/`LinkageError` | Thiếu dependency, classloader identity/loader constraints, hoặc lỗi khởi tạo trước | Kiểm tra causes, module graph, class loaders và thời điểm linkage |
| `java.lang.SecurityException` khi tạo layer | Môi trường/security manager (nếu có) từ chối thao tác cần permission | Tuân theo chính sách môi trường; không coi controller là bypass |
| `findModule(name)` trả empty | Module chưa được resolve vào layer/parents hoặc tên sai | Rà soát roots, finder, configuration |
| Package đã open nhưng code vẫn không chạy | Vấn đề ở compile-time, class loading, loại access hoặc sai target module | Tách từng tầng đọc/export/open và xác nhận object Module thực tế |

Các phương thức controller theo Javadoc có thể trả `IllegalArgumentException` cho source không thuộc layer, và với export/open thêm trường hợp package không tồn tại trong source. Đối số `null` nói chung dẫn đến `NullPointerException` nếu tài liệu không quy định khác. Đừng che lỗi bằng cách thử một package bất kỳ cho đến khi “hết lỗi”: đó là tín hiệu metadata hoặc ownership của module bị sai.

### 8.1. Kiểm tra access graph bằng API, không chỉ dựa vào log

~~~java
boolean reads = source.canRead(target);
boolean exports = source.isExported("sample.provider.api", target);
boolean opens = source.isOpen("sample.provider.internal", target);
~~~

Đây là ba biểu thức được dùng với biến `source`, `target` đã có; chúng kiểm tra trạng thái quan hệ runtime. Đối với chương trình ví dụ chính, ba phương thức được gọi với **cặp module nguồn/đích khác nhau** đúng theo từng quyền.

Khi chẩn đoán, ghi thêm:

~~~java
System.out.println("source=" + source.getName() + " layer=" + source.getLayer());
System.out.println("target=" + target.getName() + " layer=" + target.getLayer());
~~~

Đoạn này chỉ có ý nghĩa khi `source` và `target` là những đối tượng `Module` đã lấy được, không phải một chương trình độc lập. Nếu target là unnamed module, `getName()` có thể là `null` và `getLayer()` có thể không có layer theo nghĩa named modules; tuyệt đối không dùng tên chuỗi như khóa duy nhất thay cho module identity.

### 8.2. Kiểm tra package có thực sự thuộc source không

Với một named module đã resolve, `source.getPackages()` trả các package mà module chứa. Có thể kiểm tra:

~~~java
if (!source.getPackages().contains("sample.provider.internal")) {
    throw new IllegalArgumentException("Source module does not contain package");
}
~~~

Điều này giúp phát hiện sai tên package trước khi gọi controller. Package trong `ModuleDescriptor`/`Module` là tên package thực tế; **không** có quy tắc “export cả namespace con” khi export package cha.

## 9. An toàn vận hành và giới hạn quyền

**Không đưa controller cho code không tin cậy.** Đây là khuyến cáo trực tiếp từ Javadoc `ModuleLayer.Controller`: nắm controller nghĩa là có khả năng nới rộng module relationships của cả layer được điều khiển. Nếu một plugin giữ được controller, nó có thể làm suy giảm nguyên tắc encapsulation giữa các module trong layer.

Đối với host quản lý plugin, nên:

1. Giữ controller trong module hoặc thành phần hạ tầng tin cậy, không đưa vào extension context công khai.
2. Xác thực **module source** bằng chính đối tượng `Module` và layer ownership, không chỉ tên module do plugin cung cấp.
3. Xác định **target module** có chủ đích, cấp opens/exports theo package và target cụ thể, tránh mở rộng bề mặt truy cập không cần thiết.
4. Hoàn tất cấu hình trước khi công bố provider vào registry hoặc chạy callback. Tránh để một request đang chạy quan sát trạng thái quyền nửa chừng nếu đó không phải thiết kế có chủ đích.
5. Ghi log/audit những quan hệ mới với source, target, package, lý do và phiên bản plugin; ghi nhận mọi lỗi thay vì âm thầm tiếp tục.
6. Không dựa vào việc đảo ngược quyền qua controller: muốn thay policy, hãy thiết kế thế hệ layer mới và quá trình chuyển tiếp được kiểm soát.
7. Dọn loader, thread, service instance, listener, cache và context references khi ngừng plugin. Giữ `Module` hoặc `Class<?>` lâu dài có thể giữ layer/loader cũ không được thu gom.
8. Hiểu giới hạn của JPMS: encapsulation module là cơ chế access control giữa các module, **không phải sandbox bảo mật toàn diện** để chạy mã độc ngay trong cùng tiến trình.

**Ghi chú về reachability:** Javadoc của `addReads` nêu rằng các read edge được thêm là **weak**, không tự giữ target module sống chỉ vì source còn strong reachable. Đừng dựa vào quan hệ reads để quản lý vòng đời đối tượng hoặc plugin; host phải giữ những tham chiếu cần thiết trong thời gian sử dụng.

## 10. Tình huống áp dụng và lựa chọn thiết kế

### Tình huống A: plugin consumer cần đọc API mới của provider

Consumer và provider đã nằm trong child layer, nhưng descriptor của consumer không khai báo dependency tĩnh; host muốn bổ sung quyền ở runtime:

~~~java
controller.addReads(consumer, provider)
          .addExports(provider, "sample.provider.api", consumer);
~~~

Điều này bổ sung readability và quyền truy cập public API của package. Nó hợp lý khi host **cố ý** nối các module runtime đã resolve. Nếu consumer cần import và dùng API ở thời điểm biên dịch, vẫn phải xử lý dependency compiler phù hợp.

### Tình huống B: framework cần truy cập private field để serialize

Host muốn framework module cụ thể đọc nội bộ model:

~~~java
controller.addOpens(provider, "sample.provider.internal", serializerModule);
~~~

Chỉ cấp qualified open đến `serializerModule` khi thật sự cần reflective access. Nếu host chạy ở unnamed module, truyền đối tượng module của chính host như ví dụ. Không tự động truyền module của caller cuối cùng hoặc mở cho mọi plugin.

### Tình huống C: plugin đã biết API tĩnh từ đầu

Nếu toàn bộ quan hệ module đã cố định khi xây dựng, mô tả bằng `module-info.java` có thể dễ bảo trì và dễ kiểm chứng hơn:

~~~java
module consumer.module {
    requires provider.api;
}
~~~

Việc dùng controller trong trường hợp này chỉ bổ sung một điểm cấu hình động mà không nhất thiết tạo ra giá trị. Giữ dynamic access control cho trường hợp cần điều phối runtime thực sự.

## 11. Bộ kiểm thử cần có

Khi triển khai host có `ModuleLayer.Controller`, nên kiểm chứng ít nhất:

| Nhóm | Điều cần kiểm tra | Dấu hiệu đúng |
| --- | --- | --- |
| Layer creation | Configuration/parent layers đúng, static factory trả Controller | `controller.layer()` là layer mới với modules dự kiến |
| Readability | Trước/sau `addReads` cho source/target xác định | `canRead` chuyển từ `false` sang `true` nếu trước đó chưa có cạnh |
| Qualified exports | Package source tồn tại, đúng target module | `isExported(pn, target)` đúng, không nhầm target |
| Qualified opens | Reflection sâu bị chặn trước và được cấp đúng target sau | `isOpen` thay đổi và `setAccessible(true)` chỉ thành công khi phù hợp |
| Ownership/scope | Thử source thuộc boot/parent/another layer | `IllegalArgumentException`, không sửa module ngoài phạm vi |
| Package validation | Thử package không có trong source | `IllegalArgumentException` |
| Descriptor invariance | Kiểm tra `getDescriptor()` trước/sau | Descriptor không tự sinh thêm `requires`, `exports`, `opens` |
| Module resolution | Bỏ một root/artifact khỏi finder | Lỗi resolution hoặc không tìm thấy module được phát hiện sớm |
| Classloader | Cố ý dùng sai artifact/loader | Phân biệt lỗi loading với lỗi access |
| Lifecycle | Reload nhiều thế hệ layer, đóng tài nguyên plugin | Không rò rỉ callback/thread/reference làm giữ loader cũ |

Không dựa vào một lần thao tác reflection thành công để suy rằng mọi package đã được export hay mọi module đều được quyền đọc nhau. Kiểm tra **từng quan hệ chính xác theo source, package và target**.

## 12. Điểm cần ghi nhớ

~~~text
static ModuleLayer.defineModulesWithOneLoader(...)
          |
          +--> ModuleLayer.Controller
                     |
                     +--> layer() : child ModuleLayer
                     |
                     +--> addReads(source, target)
                     |         source thuộc child layer
                     |
                     +--> addExports(source, package, target)
                     |         source thuộc child layer
                     |         package thuộc source
                     |
                     +--> addOpens(source, package, target)
                               source thuộc child layer
                               package thuộc source

Controller:
  + bổ sung quan hệ ở runtime
  + có qualified target
  + không sửa module-info/ModuleDescriptor
  + không gỡ lại quyền vừa thêm
  + không điều khiển source ở parent/boot/another layer
~~~

**Quy tắc thực hành:** Đầu tiên xác định **module nguồn nào thuộc layer vừa tạo**, sau đó xác định chính xác **module đích và package cần cấp quyền**, rồi dùng controller để thêm quan hệ nhỏ nhất phục vụ nhu cầu runtime. Đối với một hệ thống plugin, phải xem controller là năng lực quản trị layer có giới hạn và chỉ để host đáng tin cậy nắm giữ.

### Tài liệu tham khảo chuẩn

- [JDK 17 – ModuleLayer.Controller](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.Controller.html): mô tả controller, `addReads`, `addExports`, `addOpens`, phạm vi source và lỗi.
- [JDK 17 – ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): cách tạo layer bằng static hoặc instance factories, configuration và class loaders.
- [JDK 17 – Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen` và các API module-level.
- [JDK 17 – Configuration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html): `resolve` module graph từ finder và parent configuration.
- [JDK 17 – AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): các điều kiện của `setAccessible` và reflection access qua ranh giới module.

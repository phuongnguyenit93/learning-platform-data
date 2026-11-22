# ModuleLayer xác định class loader cho module trong Java

`ModuleLayer` là cơ chế của Java Platform Module System (JPMS, từ Java 9) dùng để tạo một tập module đã được giải quyết phụ thuộc và **gắn mỗi module với một class loader cụ thể**. Muốn biết class loader nào chịu trách nhiệm nạp lớp của một module trong layer, gọi `layer.findLoader(moduleName)`; muốn biết lớp đã nạp thực sự thuộc module nào, kiểm tra `clazz.getModule()`.

Bài này tập trung vào quan hệ giữa `ModuleLayer`, `Configuration`, `Module` và `ClassLoader`; cách định nghĩa layer con; cách lấy đúng loader; và những giới hạn khi áp dụng cho plugin hoặc ứng dụng cần tách biệt các bộ module.

## 1. Phân biệt bốn thành phần

| Thành phần | Trách nhiệm |
| --- | --- |
| `module-info.java` / `ModuleDescriptor` | Khai báo tên module, `requires`, `exports`, `opens`, `uses`, `provides`. |
| `Configuration` | Mô tả tập **resolved modules** và đồ thị phụ thuộc sau quá trình resolution; chưa tạo các đối tượng `Module` chạy thực tế. |
| `ModuleLayer` | Chứa các module lúc chạy cùng quan hệ layer cha; khi định nghĩa layer, Java xác lập module nào đi với class loader nào. |
| `ClassLoader` | Nạp các `Class`; một loader có thể được gắn với nhiều module, hoặc mỗi module có loader riêng, tùy cách tạo layer. |

Có thể hình dung:

```text
ModuleLayer.boot()                     (layer cha, có các module nền tảng)
       |
       | định nghĩa layer con từ Configuration
       v
ModuleLayer pluginLayer                (layer con)
  +-- module com.demo.api    -------> ClassLoader L
  +-- module com.demo.impl   -------> ClassLoader L  (one-loader)
```

Đồ thị **quan hệ cha giữa các layer** và chuỗi **ủy quyền cha giữa các class loader** là hai quan hệ khác nhau. Khi truyền `parentLoader` vào phương thức tạo layer, bạn chỉ định cha của loader mới được tạo, chứ không biến mọi loader trong layer cha thành một loader duy nhất.

## 2. Từ module path đến class loader: trình tự hoạt động

1. **Tìm module:** `ModuleFinder` đọc modular JAR hoặc thư mục module đã biên dịch.
2. **Giải quyết phụ thuộc:** `Configuration.resolve(...)` xác định các module cần thiết cho tập root modules và nối chúng với cấu hình cha.
3. **Định nghĩa layer:** Một trong các phương thức `defineModules...` tạo module lúc chạy và xác lập ánh xạ `tên module → class loader`.
4. **Truy xuất ánh xạ:** `layer.findLoader("ten.module")` trả về loader gắn với module được định nghĩa **trong layer đó**.
5. **Nạp lớp:** Dùng loader này để nạp một lớp thuộc module, rồi kiểm tra `Class.getModule()` và `Module.getLayer()` để thấy kết quả.

Ví dụ luồng API rút gọn:

```java
ModuleLayer parent = ModuleLayer.boot();
ModuleFinder finder = ModuleFinder.of(Path.of("build/modules"));

Configuration config = parent.configuration().resolve(
    finder,
    ModuleFinder.of(),
    Set.of("com.example.greeting")
);

ModuleLayer child = parent.defineModulesWithOneLoader(
    config,
    ClassLoader.getSystemClassLoader()
);

ClassLoader loader = child.findLoader("com.example.greeting");
Class<?> greetingClass =
    loader.loadClass("com.example.greeting.api.Greeter");
```

`Configuration` quyết định **module nào** tham gia và phụ thuộc vào ai; `defineModulesWithOneLoader` quyết định **loader nào** được dùng để định nghĩa những module đó. Chỉ `resolve` thì chưa có layer con và chưa có class loader mới cho các module.

## 3. Ba cách xác định loader cho một layer

| API | Ánh xạ module → loader | Phù hợp khi |
| --- | --- | --- |
| `defineModulesWithOneLoader(config, parentLoader)` | Các module mới của layer **dùng chung một loader mới** có `parentLoader` làm cha. | Nhóm module có thể chia sẻ không gian nạp lớp trong một plugin hoặc một tính năng. |
| `defineModulesWithManyLoaders(config, parentLoader)` | **Mỗi module mới có loader riêng**; các loader mới cùng ủy quyền lên `parentLoader`. | Cần tách biệt loader của từng module trong cùng layer. |
| `defineModules(config, moduleName -> loader)` | Chương trình cung cấp loader cho **từng tên module** qua hàm ánh xạ. | Đã có chiến lược custom class loader và kiểm soát được việc nạp lớp của các module. |

Các overload dạng instance ở bảng trên sử dụng layer nhận lời gọi làm layer cha. Java còn có các factory tĩnh nhận `List<ModuleLayer>` để cấu hình nhiều layer cha; chúng trả về `ModuleLayer.Controller`, từ đó lấy layer bằng `controller.layer()` và có thể điều chỉnh một số quan hệ đọc, export, open khi thật sự cần.

Cần hiểu rõ:

- **One loader** không có nghĩa tất cả module được nhập thành một module. Mỗi module vẫn giữ tên, descriptor, quan hệ `requires`, `exports` và quy tắc truy cập riêng.
- **Many loaders** không làm cho mỗi module thành một tiến trình hay sandbox bảo mật. Đây là cách chia không gian nạp lớp, không phải cơ chế cách ly tài nguyên hệ điều hành.
- **Custom mapping** đòi hỏi class loader bạn cung cấp thực sự nạp được các lớp thuộc module được gán cho nó, đồng thời đáp ứng các ràng buộc của JPMS. Không nên chuyển tùy tiện nhiều module có package xung đột vào cùng loader.

## 4. Ví dụ đầy đủ có thể biên dịch và chạy

Ví dụ sử dụng Java 17+ (các API layer đã có từ Java 9). Ta tạo một module `com.example.greeting` rồi nạp nó từ ứng dụng chạy trên classpath.

Cấu trúc thư mục:

```text
src/
├── com.example.greeting/
│   ├── module-info.java
│   └── com/example/greeting/api/Greeter.java
└── app/
    └── Main.java
```

**Tệp `src/com.example.greeting/module-info.java`**

```java
module com.example.greeting {
    exports com.example.greeting.api;
}
```

**Tệp `src/com.example.greeting/com/example/greeting/api/Greeter.java`**

```java
package com.example.greeting.api;

public final class Greeter {
    private Greeter() {}

    public static String message() {
        return "Xin chào từ module "
            + Greeter.class.getModule().getName();
    }
}
```

**Tệp `src/app/Main.java`**

```java
package app;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class Main {
    public static void main(String[] args) throws Exception {
        // 1. Chọn layer cha đang hoạt động.
        ModuleLayer boot = ModuleLayer.boot();

        // 2. Tìm các module đã biên dịch.
        ModuleFinder finder = ModuleFinder.of(Path.of("build/modules"));

        // 3. Giải quyết com.example.greeting cùng các phụ thuộc.
        Configuration config = boot.configuration().resolve(
            finder,
            ModuleFinder.of(),
            Set.of("com.example.greeting")
        );

        // 4. Tạo layer con; module của layer dùng chung loader mới.
        ModuleLayer child = boot.defineModulesWithOneLoader(
            config,
            ClassLoader.getSystemClassLoader()
        );

        // 5. Lấy loader qua layer thay vì đoán loader hệ thống.
        ClassLoader loader = child.findLoader("com.example.greeting");

        // 6. Dùng loader tương ứng để nạp lớp của module.
        Class<?> clazz =
            loader.loadClass("com.example.greeting.api.Greeter");

        Module module = clazz.getModule();

        System.out.println("Module: " + module.getName());
        System.out.println("Đúng layer: " + (module.getLayer() == child));
        System.out.println("Đúng loader: "
            + (module.getClassLoader() == loader));
        System.out.println(clazz.getMethod("message").invoke(null));
    }
}
```

Tại thư mục gốc của ví dụ, biên dịch và chạy:

```bash
javac --module-source-path src -d build/modules -m com.example.greeting
javac -d build/app src/app/Main.java
java -cp build/app app.Main
```

Kết quả dự kiến:

```text
Module: com.example.greeting
Đúng layer: true
Đúng loader: true
Xin chào từ module com.example.greeting
```

Giải thích từng điểm:

- `ModuleFinder.of(Path.of("build/modules"))` tìm module đã biên dịch trong thư mục chứa các module con.
- `boot.configuration().resolve(...)` dùng cấu hình của boot layer làm cha; những module nền tảng cần thiết được giải quyết theo quan hệ phụ thuộc.
- `boot.defineModulesWithOneLoader(...)` tạo layer con và class loader mới. `ClassLoader.getSystemClassLoader()` ở đây là **loader cha**, không đồng nghĩa loader được trả về bởi `child.findLoader(...)`.
- `clazz.getModule()` trả về module đã định nghĩa chính lớp đó. `module.getLayer() == child` và `module.getClassLoader() == loader` xác nhận ánh xạ thực tế.
- Lời gọi reflective `getMethod("message").invoke(null)` hợp lệ vì lớp và phương thức là `public`, còn package `com.example.greeting.api` được `exports`.

Trong ví dụ này, gọi `Class.forName("com.example.greeting.api.Greeter")` từ `app.Main` bằng loader mặc định có thể thất bại: loader đang chạy ứng dụng trên classpath không tự tìm vào loader con của `ModuleLayer`. Hãy lấy loader từ đúng layer.

## 5. Quy tắc tra cứu module và loader

```java
ModuleLayer layer = /* layer đã tạo */;

Module module = layer.findModule("com.example.greeting")
    .orElseThrow();
ClassLoader loader = layer.findLoader("com.example.greeting");

System.out.println(module.getName());
System.out.println(module.getClassLoader() == loader);
```

`findModule(name)` tìm module trong layer và có thể đi lên các layer cha. `findLoader(name)` yêu cầu tên module **được định nghĩa ngay trong layer nhận lời gọi**; nếu tên module không có ở layer đó, phương thức ném `IllegalArgumentException`. Vì vậy, nếu cần loader của một module thuộc layer cha, hãy tra cứu trên chính layer đã định nghĩa module đó.

Không phải module nào cũng dùng class loader do ứng dụng tạo. Các module nền tảng có thể được nạp bởi bootstrap class loader; với trường hợp đó, `Module.getClassLoader()` hoặc `findLoader(...)` có thể trả về `null`. `null` trong ngữ cảnh này không có nghĩa là module chưa được nạp.

Một layer có thể chứa nhiều module; một module thuộc đúng một layer tại thời điểm nó được định nghĩa. Hai layer khác nhau có thể chứa module **cùng tên** nhưng là những đối tượng `Module` khác nhau, với lớp và loader riêng. Do đó, khi quản lý plugin, khóa nhận dạng theo mỗi tên module đơn lẻ thường chưa đủ: phải xét layer chứa module.

## 6. Phân biệt tải lớp, đọc module và truy cập package

Đúng loader chỉ giải quyết việc **tìm và định nghĩa lớp**. Việc chương trình có được phép sử dụng lớp hay thành viên của nó còn phụ thuộc vào quy tắc JPMS:

- `requires` thiết lập quan hệ module này đọc module khác; `Configuration` phân giải đồ thị đó.
- `exports p` cho phép mã ở module khác truy cập các kiểu `public` trong package `p` theo quy tắc của module.
- `opens p` hỗ trợ truy cập phản chiếu sâu vào package `p`; `exports` thông thường không cấp quyền truy cập vào thành viên `private`.
- `uses` và `provides ... with ...` khai báo giao tiếp dịch vụ. `ServiceLoader.load(layer, ServiceType.class)` là một cách tìm provider nằm trong layer được cung cấp.

Vì vậy, `loader.loadClass("a.b.C")` có thể tìm được đối tượng `Class` nhưng thao tác truy cập `C` vẫn thất bại khi package không được export hoặc open thích hợp. Việc nạp lớp thành công không xóa bỏ kiểm soát truy cập theo module.

## 7. Khi nào nên tạo layer riêng?

**Hệ thống plugin.** Mỗi nhóm plugin có thể được giải quyết thành một `Configuration` rồi định nghĩa trong một layer con. Ứng dụng giữ lại layer và gọi `findLoader` khi cần nạp entry point của plugin. Muốn nhận các implementation theo chuẩn dịch vụ, ưu tiên `ServiceLoader` thay vì hardcode tên lớp.

**Nhiều phiên bản thư viện.** Những tập module ở layer khác nhau có thể có tên trùng nhau nhưng không chia sẻ cùng định danh lớp. Đây là công cụ để thiết kế việc cô lập phụ thuộc, với điều kiện các dependency và loader delegation được tổ chức phù hợp. Hai lớp cùng tên binary nhưng được định nghĩa bởi hai loader khác nhau không phải cùng một kiểu đối với JVM.

**Ứng dụng chia thành nhóm tính năng.** Có thể dùng `defineModulesWithOneLoader` để nhóm module liên quan hoặc `defineModulesWithManyLoaders` để tách loader theo module. Lựa chọn phải phản ánh nhu cầu về tính tương thích kiểu, giải quyết phụ thuộc và tài nguyên.

Một `ModuleLayer` không tự thực hiện hot reload. Để thay một phiên bản module đã nạp, ứng dụng thường tạo configuration/layer/loader mới và chuyển tham chiếu sang đối tượng mới. Layer và các class loader cũ chỉ có thể được thu gom rác khi ứng dụng không còn giữ các tham chiếu ngăn việc thu gom.

## 8. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `FindException`: không tìm thấy module | Sai đường dẫn module path, tên root module hoặc thiếu module artifact. | Kiểm tra `ModuleFinder.of(...)`, thư mục đầu ra và tên trong `module-info.java`. |
| `ResolutionException` khi `resolve` | Đồ thị phụ thuộc hoặc tập module không hợp lệ. | Kiểm tra `requires`, các module cùng tham gia và thông báo resolution cụ thể. |
| `LayerInstantiationException` khi định nghĩa layer | Ánh xạ module → loader không hợp lệ, chẳng hạn package xung đột trong cùng loader. | Kiểm tra trùng package và chiến lược `one/many/custom loader`. |
| `IllegalArgumentException` từ `findLoader` | Tra cứu module không thuộc layer hiện tại. | Lấy đúng layer đã định nghĩa module; đối chiếu bằng `module.getLayer()`. |
| `ClassNotFoundException` | Dùng sai loader hoặc sai tên đầy đủ của lớp. | Lấy loader bằng `layer.findLoader(moduleName)` và dùng tên lớp đầy đủ dạng `package.ClassName`. |
| `IllegalAccessException` / `InaccessibleObjectException` | Quy tắc `exports`/`opens` hoặc mức truy cập của lớp, thành viên không cho phép thao tác. | Kiểm tra API public, descriptor module và loại reflection đang sử dụng. |
| `ClassCastException` giữa hai lớp có tên giống nhau | Hai loader đã định nghĩa hai đối tượng `Class` khác nhau. | Dùng API chia sẻ có cùng danh tính lớp và thiết kế ranh giới loader rõ ràng. |

Không chữa lỗi truy cập bằng cách tự động mở toàn bộ package hoặc chuyển mọi module về cùng loader. Cần xác định trước vấn đề thuộc **resolution**, **loader mapping**, **class identity** hay **module access**.

## 9. Ghi nhớ khi triển khai

1. `ModuleFinder` tìm module, `Configuration` giải quyết phụ thuộc, `ModuleLayer` định nghĩa module và gắn loader, `ClassLoader` nạp lớp.
2. Để biết loader của module được định nghĩa trong layer: `layer.findLoader(moduleName)`. Để kiểm tra một lớp đã nạp: `clazz.getModule().getClassLoader()`.
3. Chọn `defineModulesWithOneLoader` khi muốn các module mới dùng chung loader; chọn `defineModulesWithManyLoaders` khi muốn mỗi module có loader riêng; chỉ dùng mapping tùy chỉnh khi kiểm soát được class loader.
4. Phân biệt **layer parent**, **loader parent**, **readability** và **exports/opens** vì chúng giải quyết các vấn đề khác nhau.
5. Khi debug, in `clazz.getName()`, `clazz.getModule().getName()`, `clazz.getModule().getLayer()` và `clazz.getClassLoader()`; dữ liệu này giúp biết lớp thực sự do module/layer/loader nào định nghĩa.

**API nên tra cứu thêm:** `java.lang.ModuleLayer`, `java.lang.ModuleLayer.Controller`, `java.lang.Module`, `java.lang.ClassLoader`, `java.lang.module.Configuration`, `java.lang.module.ModuleFinder` và `java.util.ServiceLoader` trong tài liệu JDK đang dùng.

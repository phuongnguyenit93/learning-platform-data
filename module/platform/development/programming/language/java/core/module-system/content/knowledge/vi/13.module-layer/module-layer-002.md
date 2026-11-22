# Boot layer và module layer mặc định trong Java (JPMS)

## 1. Mục tiêu

Sau bài này, bạn có thể:
- Giải thích `ModuleLayer` là gì và vì sao JVM cần boot layer khi khởi động ứng dụng có module.
- Xác định module nào đã được phân giải vào boot layer; phân biệt module đang *có trên module path* với module đã *được đưa vào đồ thị module lúc chạy*.
- Dùng `ModuleLayer.boot()`, `modules()`, `findModule()`, `configuration()` và `Module.getLayer()` để kiểm tra cấu trúc module.
- Phân biệt boot layer với unnamed module trên classpath và với một module layer được tạo thêm tại thời điểm chạy.
- Hiểu giới hạn của boot layer khi thiết kế hệ thống plugin hoặc nạp module động.

**Phạm vi:** Java 9 trở lên; các ví dụ lệnh và mã nguồn phù hợp với Java 21.

## 2. Ba khái niệm nền tảng

JPMS (Java Platform Module System) nhóm mã nguồn thành **module** với tên, phụ thuộc và các ranh giới truy cập được khai báo qua `module-info.java`. Khi chương trình chạy, các đối tượng sau liên quan nhưng không đồng nghĩa:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Module** (`java.lang.Module`) | Đại diện cho một module ở runtime; chứa thông tin tên, package, lớp nạp và lớp chứa module | `java.base`, `java.logging`, `vn.demo.boot` |
| **Configuration** (`java.lang.module.Configuration`) | Kết quả phân giải quan hệ phụ thuộc của các module; tập các `ResolvedModule` và quan hệ đọc giữa chúng | Cấu hình giải được `vn.demo.boot → java.logging → java.base` |
| **Module layer** (`java.lang.ModuleLayer`) | Gắn các module đã được phân giải với class loader tại runtime và liên kết với các layer cha | Boot layer hoặc một layer dành riêng cho plugin |

Có thể hình dung mối quan hệ:

~~~text
module-info.java + module path + tập root modules
                  |
                  v
         Bộ phân giải module
                  |
                  v
           Configuration
                  |
                  v
ModuleLayer (module + class loader + parent layers)
                  |
                  v
    Class được nạp / kiểm soát truy cập
~~~

**Điểm cốt lõi:** `Configuration` mô tả đồ thị đã phân giải; `ModuleLayer` hiện thực đồ thị đó trong JVM. Một layer không đơn giản là một thư mục chứa các file JAR, và một class loader cũng không đồng nghĩa với một layer.

## 3. Boot layer là gì?

**Boot layer** là module layer do JVM thiết lập khi khởi động. Đây là layer ban đầu chứa những **named modules đã được phân giải trong giai đoạn startup**, bao gồm các module nền tảng cần thiết và các module ứng dụng được chọn làm root cùng các phụ thuộc được phân giải của chúng.

Truy cập layer này qua:

~~~java
ModuleLayer boot = ModuleLayer.boot();
~~~

Những tính chất cần nhớ:

1. Trong một JVM, `ModuleLayer.boot()` trả về boot layer đã được thiết lập trong quá trình khởi động. Ứng dụng có thể *tra cứu* layer này nhưng không gắn thêm module vào nó bằng cách sửa trực tiếp tập `modules()`.
2. Boot layer có **empty layer** làm cha. `ModuleLayer.empty()` không chứa module nào và không có cha.
3. `java.base` là module nền tảng bắt buộc và có mặt trong boot layer. Sự có mặt của các module JDK khác phụ thuộc cấu hình khởi chạy và môi trường runtime.
4. Với ứng dụng được khởi chạy bằng `-m` / `--module`, module khởi chạy đã được phân giải nằm trong boot layer.
5. Boot layer có thể chứa cả system modules và các named modules lấy từ application module path, nếu chúng thực sự được phân giải lúc startup.

Một cách nhìn đơn giản:

~~~text
                 ModuleLayer.empty()
                         |
                         v
                 Boot module layer
                 +------------------+
                 | java.base        |
                 | java.logging     |  (khi được phân giải)
                 | vn.demo.boot     |  (ứng dụng dạng module)
                 | ...              |
                 +------------------+
                         |
           Một layer mới có thể được
            định nghĩa thêm tại runtime
~~~

Sơ đồ là ví dụ minh họa: tập module thực tế phụ thuộc cấu hình khởi chạy. **Tên “module layer mặc định” trong ngữ cảnh JPMS thường chỉ boot layer**; nó không có nghĩa rằng mọi JAR hay mọi module khả dụng đều tự động thuộc layer này.

### Boot layer hình thành khi nào?

Trước khi gọi `main()`, runtime xác định tập module gốc (*root modules*), tìm các phụ thuộc theo khai báo `requires`, phân giải đồ thị và thiết lập boot layer. Tập root được ảnh hưởng bởi cách launch chương trình cùng các tùy chọn module.

Ví dụ khi chạy:

~~~text
java --module-path out --module vn.demo.boot/vn.demo.boot.Main
~~~

`vn.demo.boot` là module gốc. Nếu `module-info.java` có `requires java.logging;`, module `java.logging` phải được phân giải cùng các phụ thuộc cần thiết. Module nào không được chọn hoặc không nằm trong đồ thị phân giải không tự động xuất hiện trong boot layer chỉ vì file JAR của nó có trên module path.

## 4. Các API quan sát boot layer

| API | Ý nghĩa |
| --- | --- |
| `ModuleLayer.boot()` | Lấy boot layer của JVM hiện tại |
| `boot.modules()` | Lấy tập **module nằm trực tiếp trong layer này** (`Set<Module>`) |
| `boot.findModule("java.base")` | Tìm module theo tên, trả về `Optional<Module>`; cơ chế tìm cũng xét các layer cha |
| `boot.configuration()` | Lấy `Configuration` tương ứng để kiểm tra các `ResolvedModule` |
| `boot.parents()` | Lấy các layer cha; với boot layer, cha là empty layer |
| `SomeClass.class.getModule()` | Lấy module chứa class đó |
| `someModule.getLayer()` | Lấy layer chứa module, hoặc `null` nếu module không nằm trong layer nào |
| `boot.findLoader(name)` | Tìm class loader được gắn với module có tên cho trước; bootstrap loader có thể biểu diễn bằng `null` |

`modules()` chỉ liệt kê module thuộc **chính layer đó**. Trái lại, `findModule()` có thể tìm trong layer cha khi gọi từ layer con. Hai hành vi này đặc biệt quan trọng khi ứng dụng tự tạo thêm module layer.

Không dùng `findModule("x").get()` khi chưa xác nhận sự tồn tại: module `x` có thể không được phân giải tại lần khởi chạy hiện tại. Nên dùng `isPresent()`, `ifPresent(...)` hoặc `orElseThrow(...)` với thông báo phù hợp.

## 5. Ví dụ 1 — Khảo sát boot layer khi chạy trên classpath

Tạo file `BootInspector.java`:

~~~java
import java.lang.Module;
import java.lang.ModuleLayer;
import java.util.Comparator;

public class BootInspector {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();
        Module current = BootInspector.class.getModule();

        System.out.println("java.base present: "
                + boot.findModule("java.base").isPresent());
        System.out.println("Number of boot modules: "
                + boot.modules().size());
        System.out.println("Current class in named module: "
                + current.isNamed());
        System.out.println("Current module inside boot: "
                + boot.modules().contains(current));

        System.out.println("Boot layer parents: "
                + boot.parents().size());
        System.out.println("Parent is empty: "
                + boot.parents().get(0).modules().isEmpty());

        boot.modules().stream()
                .map(Module::getName)
                .sorted(Comparator.naturalOrder())
                .limit(10)
                .forEach(name -> System.out.println("  " + name));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BootInspector.java
java BootInspector
~~~

Những điều có thể quan sát một cách ổn định:

- `java.base present: true`.
- `Current class in named module: false` vì `BootInspector` được chạy qua classpath, nên thuộc một **unnamed module**.
- `Current module inside boot: false`: unnamed module của classpath không được đưa vào `boot.modules()`.
- Boot layer có một layer cha rỗng; danh sách tên module và số lượng module phụ thuộc JDK và cách khởi chạy.

**Chú ý:** Chạy trên classpath **không làm boot layer biến mất**. Các module JDK đã được phân giải vẫn nằm trong boot layer, còn lớp ứng dụng ví dụ này thuộc unnamed module.

## 6. Ví dụ 2 — Module ứng dụng nằm trong boot layer

Tạo cấu trúc dự án:

~~~text
src/
└── vn.demo.boot/
    ├── module-info.java
    └── vn/
        └── demo/
            └── boot/
                └── Main.java
~~~

File `src/vn.demo.boot/module-info.java`:

~~~java
module vn.demo.boot {
    requires java.logging;
}
~~~

File `src/vn.demo.boot/vn/demo/boot/Main.java`:

~~~java
package vn.demo.boot;

import java.lang.Module;
import java.lang.ModuleLayer;

public class Main {
    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();
        Module app = Main.class.getModule();

        System.out.println("App module: " + app.getName());
        System.out.println("App is named: " + app.isNamed());
        System.out.println("App layer is boot: "
                + (app.getLayer() == boot));
        System.out.println("App found in boot: "
                + boot.findModule("vn.demo.boot").isPresent());
        System.out.println("java.logging found in boot: "
                + boot.findModule("java.logging").isPresent());
        System.out.println("java.base found in boot: "
                + boot.findModule("java.base").isPresent());

        boot.configuration()
                .findModule("vn.demo.boot")
                .ifPresent(resolved -> System.out.println(
                        "Resolved name: " + resolved.name()));
    }
}
~~~

Ở thư mục gốc dự án, biên dịch và chạy:

~~~bash
javac --module-source-path src -d out -m vn.demo.boot
java --module-path out -m vn.demo.boot/vn.demo.boot.Main
~~~

Những dòng kết quả dự kiến:

~~~text
App module: vn.demo.boot
App is named: true
App layer is boot: true
App found in boot: true
java.logging found in boot: true
java.base found in boot: true
Resolved name: vn.demo.boot
~~~

Vì chương trình được launch như **named module**, `vn.demo.boot` thuộc boot layer. Khai báo `requires java.logging;` làm `java.logging` trở thành một phần của đồ thị cần phân giải. `java.base` là phụ thuộc cơ bản được mọi module sử dụng, kể cả khi không khai báo `requires java.base;` một cách tường minh.

Có thể bổ sung tùy chọn:

~~~bash
java --show-module-resolution --module-path out -m vn.demo.boot/vn.demo.boot.Main
~~~

Tùy chọn này hiển thị thông tin JVM đang phân giải module nào và quan hệ phụ thuộc nào trong lúc khởi chạy. Nội dung và thứ tự chi tiết có thể khác giữa các bản JDK.

## 7. Điều gì quyết định thành phần boot layer?

**Module path** là nơi runtime tìm ứng viên module; **module resolution** mới quyết định module nào tham gia đồ thị ban đầu. Một module có mặt trên module path chưa chắc đã nằm trong boot layer.

| Cách chạy / tùy chọn | Ảnh hưởng chính |
| --- | --- |
| `java -cp ... Main` | Lớp ứng dụng trên classpath thuộc unnamed module; boot layer vẫn chứa các named modules đã phân giải |
| `java --module-path mods -m app.mod/pkg.Main` | `app.mod` là root module được phân giải vào boot layer cùng các phụ thuộc cần thiết |
| `--add-modules m1,m2` | Bổ sung root modules vào quá trình phân giải lúc khởi chạy |
| `--limit-modules m1,m2` | Giới hạn tập module có thể quan sát được khi phân giải; có thể ảnh hưởng graph được tạo |
| `--show-module-resolution` | In thông tin giải module để quan sát quá trình khởi chạy |

Một số lưu ý dễ nhầm:

- `java --list-modules` chủ yếu liệt kê các system modules có trong runtime image, **không phải phép đo trực tiếp toàn bộ `ModuleLayer.boot().modules()` của ứng dụng**.
- Một module của JDK như `java.sql` có thể có sẵn trong runtime image nhưng không được phân giải vào boot layer cho một cấu hình khởi chạy cụ thể.
- Nếu dùng runtime image thu gọn được tạo bằng `jlink`, số module khả dụng còn phụ thuộc nội dung image đó.
- Cùng một đoạn mã khảo sát boot layer có thể cho danh sách khác nhau giữa các lần chạy có tùy chọn module khác nhau; không nên hard-code số lượng module.

## 8. Boot layer khác gì so với layer tạo động?

Boot layer được thiết lập khi startup. Ứng dụng cần nạp một tập module mới sau khi đã chạy có thể **tạo layer con** từ một `Configuration` đã phân giải, thay vì cố thay đổi boot layer.

Ví dụ minh họa, giả sử thư mục `plugins/` đã chứa các module hợp lệ và có module tên `vn.demo.plugin`:

~~~java
import java.lang.ModuleLayer;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleLayer boot = ModuleLayer.boot();
ModuleFinder plugins = ModuleFinder.of(Path.of("plugins"));

Configuration pluginConfig = boot.configuration().resolve(
        plugins,
        ModuleFinder.of(),
        Set.of("vn.demo.plugin"));

ModuleLayer pluginLayer = boot.defineModulesWithOneLoader(
        pluginConfig,
        ClassLoader.getSystemClassLoader());

System.out.println(
        pluginLayer.modules().stream()
                .anyMatch(m -> "vn.demo.plugin".equals(m.getName())));
System.out.println(
        boot.findModule("vn.demo.plugin").isPresent());
~~~

Đây là đoạn mã minh họa cho phần thiết lập layer trong một phương thức; muốn chạy cần chuẩn bị module plugin và graph phụ thuộc hợp lệ. `pluginLayer` được định nghĩa với `boot` là layer cha. Module `vn.demo.plugin` nằm trong layer con; việc tạo layer con **không bổ sung module này vào boot layer**.

So sánh hai loại layer:

| Tiêu chí | Boot layer | Layer được ứng dụng tạo thêm |
| --- | --- | --- |
| Thời điểm tạo | Khi JVM khởi động | Trong lúc chương trình chạy |
| Cách truy cập | `ModuleLayer.boot()` | Giá trị trả về từ `defineModulesWithOneLoader`, `defineModulesWithManyLoaders` hoặc API liên quan |
| Cấu hình | Dựa trên graph được phân giải lúc startup | Dựa trên `Configuration` do ứng dụng phân giải |
| Quan hệ cha | Empty layer | Một hoặc nhiều layer cha được chỉ định |
| Mục đích điển hình | Chạy module nền tảng và ứng dụng ban đầu | Plugin, thành phần mở rộng, tách biệt cách nạp module |

Khi gọi `pluginLayer.findModule("java.base")`, API có thể tìm thấy `java.base` từ layer cha. Nhưng `pluginLayer.modules()` chỉ chứa các module **được định nghĩa trực tiếp** trong `pluginLayer`.

**Quan trọng về class loader:** layer và class loader là hai trục liên quan. Một layer có thể ánh xạ nhiều module tới cùng loader hoặc những loader khác nhau; lớp trong boot layer cũng có thể được nạp bởi bootstrap, platform hay application class loader. Vì thế “cùng layer” không đồng nghĩa “cùng class loader”.

## 9. Các hiểu lầm thường gặp

**“Tôi đặt JAR vào module path, vì sao `findModule()` trả về rỗng?”**  
Vì module path chỉ cung cấp ứng viên. Module cần được phân giải bởi root module, quan hệ phụ thuộc hoặc tùy chọn khởi chạy thích hợp. Trước tiên kiểm tra cách chạy và `module-info.java`.

**“Chạy ứng dụng bằng `-cp` thì không có boot layer?”**  
Không đúng. JVM vẫn tạo boot layer; chỉ có mã ứng dụng trên classpath thuộc unnamed module thay vì một named module ở boot layer.

**“Boot layer là nơi chứa tất cả các module?”**  
Không. Module được tải vào layer mới có thể nằm ở layer con. Module chưa được phân giải thì chưa nằm trong graph của boot layer.

**“Một layer là một class loader?”**  
Không. `ModuleLayer` tổ chức các module và quan hệ cha; mỗi module được ánh xạ với class loader phù hợp. Nhiều module có thể dùng chung một class loader.

**“Tôi có thể thêm trực tiếp module vào tập trả về bởi `boot.modules()`?”**  
Không. Tập trả về không phải cấu trúc cho phép sửa graph của boot layer. Muốn dùng module mới sau startup, cần xây dựng cấu hình và layer mới theo cơ chế JPMS.

**“`Module.getLayer()` luôn trả về boot layer?”**  
Không. Với module ở layer con, nó trả về layer chứa module đó; với unnamed module có thể trả về `null` vì không thuộc layer nào.

## 10. Bài tập thực hành

1. Chạy `BootInspector` bằng classpath, ghi lại số module được liệt kê và kết quả kiểm tra `current.isNamed()`. Giải thích vì sao lớp ứng dụng không thuộc boot layer.
2. Chạy module `vn.demo.boot` ở ví dụ 2, sau đó bỏ khai báo `requires java.logging;` nhưng vẫn giữ các câu lệnh kiểm tra `java.logging`. Quan sát kết quả trong môi trường đang dùng và giải thích vì sao không thể kết luận cố định sự có mặt của mọi module JDK chỉ từ một lần chạy.
3. Thêm tùy chọn `--show-module-resolution` rồi so sánh danh sách module được giải với kết quả `boot.modules()`. Chỉ ra vai trò của module gốc và phụ thuộc.
4. Viết một hàm `boolean isInBootLayer(Class<?> type)` dựa trên `type.getModule()` và `ModuleLayer.boot().modules()`, rồi thử với class ứng dụng và `String.class`.
5. Giải thích vì sao ứng dụng plugin có thể cần một module layer riêng khi các plugin chỉ được phát hiện sau khi chương trình đã chạy.

Gợi ý cho bài 4:

~~~java
static boolean isInBootLayer(Class<?> type) {
    return ModuleLayer.boot().modules().contains(type.getModule());
}
~~~

Với `String.class`, kết quả là `true` vì lớp này thuộc `java.base`. Với `BootInspector.class` chạy trên classpath, kết quả là `false`.

## 11. Ghi nhớ

- **Boot layer** là module layer ban đầu do JVM tạo tại startup, truy cập bằng `ModuleLayer.boot()`.
- Boot layer chứa **named modules đã được phân giải**, không tự động chứa mọi module tìm được trên module path.
- Ứng dụng khởi chạy bằng `-m` có named module chính trong boot layer; ứng dụng chạy trên classpath dùng unnamed module.
- `modules()` liệt kê module thuộc chính layer; `findModule()` tìm theo tên, kể cả qua các layer cha.
- Boot layer không bị “mở rộng tại chỗ” khi định nghĩa layer con. Layer con là một đối tượng `ModuleLayer` khác với configuration và ánh xạ class loader riêng.
- Khi cần chẩn đoán, kết hợp `--show-module-resolution`, `ModuleLayer.boot()`, `Class.getModule()` và `Module.getLayer()` để biết module thực sự nằm ở đâu.

## Tài liệu tham khảo

- [Java SE 21 — ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html)
- [Java SE 21 — Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [Java SE 21 — Configuration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)

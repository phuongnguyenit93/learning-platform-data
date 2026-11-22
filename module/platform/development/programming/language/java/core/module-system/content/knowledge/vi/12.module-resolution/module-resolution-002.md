# System module finder và các module JDK

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích “system modules” là gì trong Java Platform Module System (JPMS).
- Dùng API `java.lang.module.ModuleFinder.ofSystem()` để phát hiện các module mà runtime hiện tại cung cấp.
- Đọc `ModuleReference` và `ModuleDescriptor` để biết tên, phụ thuộc, exports và thông tin của module.
- Phân biệt **module có thể tìm thấy**, **module được chọn trong quá trình resolution** và **module đã hiện diện trong boot layer**.
- Dùng lệnh JDK để xem module, phân tích quan hệ phụ thuộc và kiểm tra đồ thị module được resolve.
- Nhận ra sự khác nhau giữa các module `java.*` và `jdk.*`, cũng như tác động của bản JDK hoặc runtime image tùy chỉnh.

Ví dụ trong bài sử dụng Java 17 trở lên; các API module cốt lõi đã xuất hiện từ Java 9. Danh sách module và kết quả cụ thể có thể thay đổi theo phiên bản hoặc bản phân phối JDK.

## 2. “System module” nằm ở đâu trong JPMS?

JPMS tổ chức chương trình thành **named module**. Một module có tên (chẳng hạn `java.sql`) được mô tả bằng descriptor, thường được khai báo trong `module-info.java` khi xây dựng từ mã nguồn.

Có ba khái niệm cần tách bạch:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **System module** | Module được cung cấp trong runtime image hiện đang chạy, thường thuộc Java SE/JDK. |
| **Observable module** | Module mà quá trình resolution có thể xét đến, phụ thuộc system modules, module path và các lựa chọn khởi chạy. |
| **Resolved module** | Module đã được chọn vào một `Configuration` vì thuộc tập root hoặc nằm trên đường phụ thuộc cần thiết. |
| **Module trong layer** | Module được gắn vào một `ModuleLayer` cụ thể, có thể tra bằng `findModule`. |

System module thường nằm trong runtime image hiện đại thay cho cách coi toàn bộ thư viện chuẩn là một file `rt.jar` như trước Java 9. Runtime image có hệ thống tệp đặc biệt `jrt:/` để biểu diễn nội dung các module.

Hệ sinh thái có hai nhóm tên thường gặp:

- `java.*`: các module API Java SE, ví dụ `java.base`, `java.logging`, `java.xml`, `java.sql`, `java.net.http`.
- `jdk.*`: các module tính năng, công cụ hoặc triển khai do JDK cung cấp, ví dụ `jdk.compiler`, `jdk.javadoc`, `jdk.jfr`, `jdk.httpserver`, `jdk.jdeps`. Sự hiện diện và tính ổn định của API công khai cần xem theo từng module; tiền tố `jdk.` không đồng nghĩa mọi package bên trong đều được export.

`java.base` là module nền tảng: mọi module đều đọc nó theo quy tắc JPMS, và bạn không cần khai báo `requires java.base;`.

Một số bản JDK có module gom nhóm `java.se` để biểu diễn tập module chuẩn, nhưng không nên giả định mọi runtime đã thu gọn đều có module này. Runtime do `jlink` tạo có thể chỉ chứa các module được chọn.

## 3. System module finder: `ModuleFinder.ofSystem()`

`ModuleFinder` là interface trong package `java.lang.module`. Nó là cơ chế **tìm mô tả module**, không phải class loader và bản thân nó không resolve hay khởi tạo module.

Các phương thức cần nhớ:

| API | Tác dụng |
| --- | --- |
| `ModuleFinder.ofSystem()` | Lấy finder cho các system module của runtime hiện tại. |
| `finder.find("java.sql")` | Trả về `Optional<ModuleReference>` nếu tìm thấy module tên `java.sql`. |
| `finder.findAll()` | Trả về `Set<ModuleReference>` của các module mà finder nhìn thấy. |
| `ModuleFinder.of(paths...)` | Tạo finder trên các đường dẫn chứa modular JAR hoặc exploded module. |
| `ModuleFinder.compose(f1, f2, ...)` | Kết hợp finder; khi trùng tên, finder xuất hiện trước được ưu tiên. |

`findAll()` cho biết những module có thể truy cập qua finder. Nó **không có nghĩa** tất cả module ấy đang tham gia đồ thị module của ứng dụng.

Một finder trả về `ModuleReference`, cho phép truy cập:

- `descriptor()`: đối tượng `ModuleDescriptor` có tên module, `requires`, `exports`, `opens`, `uses`, `provides`, phiên bản nếu có.
- `location()`: `Optional<URI>` cho nơi tham chiếu tới module; system module thường có dạng `jrt:/java.base`.
- `open()`: mở `ModuleReader` để duyệt hoặc đọc tài nguyên trong module; cần đóng reader đúng cách khi dùng.

Finder dùng để quan sát metadata và xây dựng cấu hình. Quyền truy cập kiểu dữ liệu trong code vẫn phụ thuộc graph và các khai báo `exports`/`opens`, chứ không phụ thuộc việc finder tìm được module.

## 4. Chương trình Java liệt kê các system module

Tạo file `SystemModuleExplorer.java`:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.util.Comparator;

public class SystemModuleExplorer {
    public static void main(String[] args) {
        ModuleFinder systemFinder = ModuleFinder.ofSystem();

        System.out.println("=== System modules ===");
        systemFinder.findAll().stream()
                .sorted(Comparator.comparing(ref -> ref.descriptor().name()))
                .forEach(ref -> {
                    ModuleDescriptor descriptor = ref.descriptor();
                    String location = ref.location()
                            .map(Object::toString)
                            .orElse("(khong co URI)");
                    String version = descriptor.rawVersion()
                            .orElse("(khong ghi version)");

                    System.out.printf("%-26s version=%-12s location=%s%n",
                            descriptor.name(), version, location);
                });

        String name = "java.sql";
        boolean available = systemFinder.find(name).isPresent();
        boolean inBootLayer = ModuleLayer.boot().findModule(name).isPresent();

        System.out.println();
        System.out.printf("%s tim thay boi system finder: %s%n", name, available);
        System.out.printf("%s co trong boot layer: %s%n", name, inBootLayer);
    }
}
~~~

Biên dịch và chạy trong terminal có `javac`/`java` từ một JDK:

~~~bash
javac SystemModuleExplorer.java
java SystemModuleExplorer
~~~

Dòng kết quả có thể giống:

~~~text
java.base                  version=17.0.x       location=jrt:/java.base
java.logging               version=17.0.x       location=jrt:/java.logging
java.sql                   version=17.0.x       location=jrt:/java.sql
jdk.compiler               version=17.0.x       location=jrt:/jdk.compiler
...
java.sql tim thay boi system finder: true
java.sql co trong boot layer: true
~~~

Đây chỉ là minh họa: số module, thứ tự sau sắp xếp, phiên bản và trạng thái boot layer phụ thuộc runtime/cách khởi chạy. `rawVersion()` có thể rỗng; không nên viết mã giả định module nào cũng có version.

Điểm chính của hai giá trị boolean cuối: **finder cho biết sự hiện diện trong nguồn module; boot layer cho biết module có nằm trong layer khởi động của lần chạy này hay không**. Hai câu hỏi này không đồng nhất.

## 5. Đọc metadata của một module JDK

Muốn kiểm tra module `java.sql` mà không cần đoán package hoặc dependency:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;

public class InspectModule {
    public static void main(String[] args) {
        String target = args.length == 0 ? "java.sql" : args[0];

        var optionalRef = ModuleFinder.ofSystem().find(target);
        if (optionalRef.isEmpty()) {
            System.out.println("System module khong ton tai: " + target);
            return;
        }

        ModuleDescriptor descriptor = optionalRef.get().descriptor();

        System.out.println("Ten: " + descriptor.name());
        System.out.println("La automatic module: " + descriptor.isAutomatic());
        System.out.println("La open module: " + descriptor.isOpen());

        System.out.println("Requires:");
        descriptor.requires().stream()
                .sorted(java.util.Comparator.comparing(ModuleDescriptor.Requires::name))
                .forEach(r -> System.out.println("  " + r));

        System.out.println("Exports:");
        descriptor.exports().stream()
                .sorted(java.util.Comparator.comparing(ModuleDescriptor.Exports::source))
                .forEach(e -> System.out.println("  " + e));

        System.out.println("Uses:");
        descriptor.uses().stream().sorted()
                .forEach(s -> System.out.println("  " + s));

        System.out.println("Provides:");
        descriptor.provides()
                .forEach(p -> System.out.println("  " + p));
    }
}
~~~

Chạy:

~~~bash
javac InspectModule.java
java InspectModule java.sql
java InspectModule java.base
java InspectModule jdk.compiler
~~~

Ý nghĩa của các mục trong descriptor:

- `requires x`: module phụ thuộc trực tiếp vào `x`.
- `requires transitive x`: ngoài việc phụ thuộc, khả năng đọc `x` được lan truyền tới module đọc module hiện tại.
- `requires static x`: dependency cần tại thời điểm biên dịch nhưng có thể vắng mặt lúc chạy.
- `exports p`: công khai package `p` để code ở module khác dùng API public của package, với giới hạn nếu là qualified export.
- `opens p`: cho phép truy cập reflective sâu tới package tương ứng theo quy tắc JPMS.
- `uses S`, `provides S with P`: công bố tiêu thụ hoặc cung cấp service.

`ModuleDescriptor` mô tả hợp đồng module; nó không tự xác nhận rằng mọi implementation class có thể được truy cập bởi module của bạn. Một package không được export vẫn bị đóng gói mạnh đối với truy cập thông thường từ module khác.

## 6. Finder và module resolution phối hợp ra sao?

Resolution là quá trình xác định một đồ thị module hợp lệ từ **root modules** và các quan hệ phụ thuộc. Runtime hoặc API cấu hình tìm module bằng finder, rồi duyệt các `requires` cần thiết. Kết quả nằm trong `java.lang.module.Configuration` dưới dạng những `ResolvedModule`.

Sơ đồ khái niệm:

~~~text
System runtime image (java.*, jdk.*)
            |
            v
   ModuleFinder.ofSystem()
            |
            v
  ModuleReference/Descriptor
            |
            v
      Chon root modules
            |
            v
 Resolution: requires, transitive,
 service binding (neu duoc yeu cau)
            |
            v
     Configuration (graph)
            |
            v
 ModuleLayer (module da duoc dinh nghia)
~~~

Khi chạy ứng dụng modular, Java còn có thể quan sát module từ `--module-path`. Trong cấu hình thực tế, finder dùng lúc resolution có thể bao gồm cả system modules và application modules. `ModuleFinder.ofSystem()` riêng lẻ chỉ giải quyết phần nguồn system modules, không thay thế module path của ứng dụng.

Ví dụ module ứng dụng:

`src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires java.sql;
}
~~~

`src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        Module me = Main.class.getModule();
        Module sql = ModuleLayer.boot()
                .findModule("java.sql")
                .orElseThrow();

        System.out.println("My module: " + me.getName());
        System.out.println("java.sql is named: " + sql.isNamed());
        System.out.println("App reads java.sql: " + me.canRead(sql));
    }
}
~~~

Biên dịch module và chạy:

~~~bash
javac -d mods/com.example.app src/com.example.app/module-info.java src/com.example.app/com/example/app/Main.java
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main
~~~

Ở ví dụ này, `com.example.app` là root từ `--module`; `java.sql` được đưa vào graph vì `requires java.sql` và những phụ thuộc cần thiết của `java.sql` cũng được resolve. Với `--show-module-resolution`, JVM in thông tin resolution trước khi chạy chương trình.

Lệnh `--module-path mods` cung cấp module ứng dụng; finder hệ thống cung cấp `java.sql` và các module JDK. Nếu thiếu module được yêu cầu trong những nguồn có thể quan sát, resolution thất bại, thường với lỗi dạng `Module ... not found, required by ...`.

### 6.1. Boot layer là gì?

`ModuleLayer.boot()` trả về layer khởi động của JVM. `ModuleLayer.boot().modules()` liệt kê module thực sự được định nghĩa trong layer đó, không phải danh sách toàn bộ module runtime.

Có thể khảo sát:

~~~java
ModuleLayer.boot().modules().stream()
        .map(Module::getName)
        .sorted()
        .forEach(System.out::println);
~~~

`ModuleLayer.boot().configuration()` là configuration liên quan đến boot layer. API `Configuration` có thể được dùng để resolve các cấu hình khác trong những hệ thống plugin hoặc layer tùy chỉnh. Đừng nhầm finder (tìm ứng viên) với configuration (đồ thị đã resolve) hoặc layer (module được định nghĩa khi chạy).

### 6.2. Sự hiện diện không bảo đảm khả năng đọc

Ví dụ `ModuleFinder.ofSystem().find("jdk.compiler")` có kết quả không làm cho mọi module ứng dụng tự động đọc `jdk.compiler`, và cũng không làm cho các package nội bộ của module ấy trở thành API công khai.

Để code trong một **named module** sử dụng API công khai từ module khác, cần có quan hệ đọc tương ứng (thường qua `requires`) và package phải được export cho module gọi. Reflection sâu cần xét thêm `opens` hoặc cơ chế mở package được cho phép.

## 7. Các lệnh JDK hữu ích khi điều tra system modules

| Lệnh | Công dụng |
| --- | --- |
| `java --list-modules` | Liệt kê các module thuộc runtime hiện tại. |
| `java --describe-module java.base` | Xem descriptor của module chỉ định. |
| `java --describe-module jdk.compiler` | Xem metadata của một module JDK nếu tồn tại. |
| `java --show-module-resolution -m ...` | Theo dõi module graph khi chạy một modular application. |
| `jdeps --list-deps app.jar` | Phân tích các module/package mà ứng dụng phụ thuộc ở mức bytecode. |
| `jdeps --print-module-deps app.jar` | Đề xuất danh sách module phục vụ việc tạo runtime image; cần kiểm tra dependency runtime và reflection riêng. |
| `jlink --list-plugins` | Xem các plugin có thể dùng khi xây runtime image, phụ thuộc phiên bản công cụ. |

Lưu ý cú pháp `-m ...` yêu cầu một modular main module có sẵn; chỉ chạy `java --show-module-resolution` kèm lệnh chạy thực tế. `jdeps` phân tích tĩnh, nên không luôn phát hiện những dependency chỉ xuất hiện qua reflection, service loading hoặc cấu hình.

Một vài lệnh thực hành độc lập:

~~~bash
java --list-modules
java --describe-module java.sql
java --describe-module jdk.compiler
jdeps --print-module-deps my-app.jar
~~~

Ví dụ đầu ra có thể chứa tên dạng `java.base@17.0.x` hoặc `jdk.compiler@17.0.x`. Không hard-code danh sách JDK modules theo một máy: JDK đầy đủ, runtime image rút gọn và bản phân phối có thể cho kết quả khác nhau.

### 7.1. Runtime image rút gọn và `jlink`

`jlink` có thể xây runtime image chứa tập module đã chọn. Ví dụ minh họa (thay đường dẫn cho đúng môi trường):

~~~bash
jlink --module-path /path/to/jdk/jmods --add-modules java.base,java.logging --output custom-runtime
~~~

Để xem module được gói trong image tạo ra:

~~~bash
custom-runtime/bin/java --list-modules
~~~

Trên Windows, tệp chạy thường là `custom-runtime\bin\java.exe`. Phụ thuộc hệ điều hành, đường dẫn `--module-path` cần trỏ tới thư mục `jmods` phù hợp của JDK.

Chương trình chạy trên image này sẽ nhận system finder của **chính image đó**. Vì vậy một module có trong JDK lúc phát triển có thể vắng mặt ở runtime tối giản. Nếu ứng dụng cần `java.sql`, image phải chứa nó và các dependency của nó.

Một số JDK có lệnh `jmod` để thao tác archive `.jmod`. File `.jmod` chủ yếu phục vụ liên kết/đóng gói runtime, không phải định dạng thường dùng để đưa lên application module path khi chạy như modular JAR. Nên phân biệt file `.jmod` của JDK với URI `jrt:/...` nhìn thấy khi runtime đã được tạo.

## 8. Các tình huống lỗi thường gặp

**1. Tìm module thấy, nhưng `ModuleLayer.boot().findModule(...)` rỗng.** Module hiện diện trong runtime, nhưng không được chọn cho boot graph của lần chạy. Kiểm tra root modules, `requires` và tham số khởi chạy; chưa cần suy ra runtime bị hỏng.

**2. Ứng dụng báo “Module ... not found”.** Xác minh tên module, phiên bản/runtime đang thực thi, `java --list-modules`, `--module-path` và module descriptor. Có thể đang chạy bằng một image đã rút gọn, hoặc module application không nằm trên đúng path.

**3. Module tồn tại nhưng compiler báo package không visible.** Kiểm tra module gọi có đọc module đích không, package có được `exports` không và export có giới hạn đích hay không. `--add-exports` là tùy chọn tương thích đặc biệt, không thay thế việc thiết kế module descriptor đúng.

**4. Reflection bị `InaccessibleObjectException`.** `requires`/`exports` thường chưa đủ cho truy cập reflective sâu. Kiểm tra `opens`, `open module` hoặc lựa chọn runtime `--add-opens` trong trường hợp phù hợp.

**5. Mã chạy trên một JDK nhưng lỗi trên máy khác.** So sánh `java -version`, `java --list-modules` và đường dẫn executable. Không mặc định module `jdk.*`, công cụ JDK hay internal package luôn có ở mọi distribution.

**6. Thấy `java.se` rồi cho rằng nó là tất cả module JDK.** `java.se` là aggregate module trong các runtime có cung cấp nó, liên quan các module Java SE; các module `jdk.*` không đồng nghĩa đều thuộc `java.se`.

## 9. Bài thực hành

1. Viết chương trình in tổng số module mà `ModuleFinder.ofSystem().findAll()` trả về; nhóm theo tiền tố `java.`, `jdk.` và nhóm khác. Giải thích vì sao tổng số này có thể khác máy bạn bè.
2. Tìm `java.base`, `java.sql`, `jdk.compiler` bằng `find(name)`. Với mỗi module tìm thấy, in `descriptor().name()`, `rawVersion()` và `location()`. Xử lý `Optional.empty()` an toàn.
3. In danh sách module trong `ModuleLayer.boot()` rồi đối chiếu với finder của system. Tìm ít nhất một trường hợp khác nhau nếu môi trường cho phép và giải thích sự khác biệt về ý nghĩa.
4. Tạo modular app nhỏ với `requires java.logging;`, dùng `java.util.logging.Logger`, rồi khởi chạy bằng `--show-module-resolution`. Chỉ ra root và module được kéo vào graph.
5. Dùng `java --describe-module java.sql` đối chiếu với dữ liệu `descriptor.requires()` từ code. Nêu ví dụ về `requires transitive` nếu descriptor trong JDK của bạn thể hiện.
6. Nếu đã quen `jlink`, tạo một image rút gọn và chạy `--list-modules` bằng executable nằm trong image đó. So sánh với JDK gốc.

Gợi ý khi làm bài: lưu lại **phiên bản Java và lệnh khởi chạy** để kết quả có thể được tái hiện; đừng lấy danh sách module in ra trên một máy làm chuẩn tuyệt đối cho mọi môi trường.

## 10. Ghi nhớ

- `ModuleFinder.ofSystem()` tìm **module mà runtime hiện tại cung cấp**, dựa trên mô tả module chứ không tải class.
- `ModuleReference` mô tả vị trí/thông tin một module; `ModuleDescriptor` cho biết hợp đồng phụ thuộc và khả năng công khai package.
- **Resolution** chọn module từ roots và dependencies để tạo `Configuration`; `ModuleLayer` là nơi các module được định nghĩa cho quá trình thực thi.
- Có mặt trong finder, tham gia configuration và có mặt trong boot layer là ba trạng thái cần phân biệt khi debug.
- Công cụ `java --list-modules`, `--describe-module` và `--show-module-resolution` giúp kiểm tra trực tiếp; `jdeps`/`jlink` hỗ trợ phân tích dependency và đóng gói runtime.
- Danh sách `java.*`/`jdk.*` phụ thuộc runtime image, nên luôn kiểm tra trên đúng JDK/runtime mà ứng dụng đang sử dụng.

## 11. Tài liệu tham khảo

- Java SE API: `java.lang.module.ModuleFinder`, `ModuleReference`, `ModuleDescriptor`, `Configuration`.
- Java SE API: `java.lang.ModuleLayer`.
- Java Platform Module System (JPMS), JEP 261.
- Tài liệu lệnh `java`, `jdeps`, `jlink` và `jmod` của phiên bản JDK đang sử dụng.

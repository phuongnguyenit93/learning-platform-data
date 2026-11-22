# ModuleFinder.of và tìm module trên module path

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Hiểu `ModuleFinder` trong Java Platform Module System (JPMS) và vai trò của nó trong **module resolution**.
- Tạo `ModuleFinder` từ đường dẫn vật lý bằng `ModuleFinder.of(Path... entries)`.
- Tìm một module bằng `find(name)`, liệt kê các module quan sát được bằng `findAll()`, đọc `ModuleDescriptor` và vị trí của `ModuleReference`.
- Phân biệt **tìm thấy module** với **giải quyết đồ thị phụ thuộc module** và **nạp module để thực thi**.
- Nhận diện các trường hợp thường gặp: module JAR, exploded module, automatic module, trùng tên và đường dẫn sai.

Ví dụ áp dụng cho Java 9 trở lên. Các lệnh ví dụ giả định thư mục làm việc hiện tại là thư mục dự án.

## 2. ModuleFinder nằm ở đâu trong quy trình resolution?

JPMS mô tả ứng dụng qua các module có tên, khai báo trong `module-info.java`. Một module có thể yêu cầu module khác bằng `requires`, xuất package bằng `exports`, hoặc khai báo dịch vụ qua `uses`/`provides`.

`java.lang.module.ModuleFinder` là giao diện **tìm định nghĩa module**. Một finder cung cấp `ModuleReference` cho từng module mà nó nhìn thấy; reference chứa `ModuleDescriptor` (tên, `requires`, `exports`, `opens`, v.v.) và có thể cung cấp URI nơi module được lưu.

Trình tự tư duy:

1. **Locate/discovery:** `ModuleFinder.of(...)` chỉ ra những module nào có trên các đường dẫn.
2. **Resolve:** `Configuration.resolve(...)` chọn các module gốc và giải quyết những phụ thuộc bắt buộc để tạo một `Configuration`.
3. **Load/runtime:** một `ModuleLayer` cùng class loader phù hợp mới đưa cấu hình vào môi trường chạy.

Vì vậy, `finder.find("com.example.greeting")` trả về giá trị không rỗng **không có nghĩa** module đã được đưa vào đồ thị resolution hoặc đã được JVM nạp vào một layer.

## 3. API quan trọng

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Optional;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
Optional<ModuleReference> one = finder.find("com.example.greeting");
Set<ModuleReference> all = finder.findAll();
~~~

| API | Ý nghĩa |
| --- | --- |
| `ModuleFinder.of(Path... entries)` | Tạo finder quét các entry trên module path được chỉ định. |
| `finder.find(String name)` | Tìm một module theo **tên module**; trả `Optional<ModuleReference>`. |
| `finder.findAll()` | Lấy tập các module mà finder tìm thấy; không dựa vào thứ tự của `Set`. |
| `reference.descriptor()` | Đọc `ModuleDescriptor`: tên, phiên bản nếu có, các phụ thuộc và chỉ thị module. |
| `reference.location()` | Trả `Optional<URI>` cho vị trí module nếu finder biết vị trí đó. |
| `ModuleFinder.ofSystem()` | Tìm các system modules do runtime image cung cấp. |
| `ModuleFinder.of()` | Finder rỗng khi không truyền entry nào. |

Đối số của `of` là các `Path` đến **module-path entry**, chẳng hạn một modular JAR hoặc thư mục chứa nhiều module. Thư mục chứa module JAR thường là entry tiện dụng nhất, ví dụ `mods/`. Một exploded module là thư mục chứa `module-info.class` và các class/package của chính module ấy. Với automatic module, một JAR không có `module-info.class` vẫn có thể được nhận diện trên module path; tên sẽ dựa vào metadata hoặc tên JAR.

`Path.of("mods")` là đường dẫn tương đối so với working directory của tiến trình Java. API không tự dùng classpath hay tự đọc biến môi trường để tìm module thay bạn; hãy truyền đường dẫn thực tế.

## 4. Chuẩn bị một modular JAR để thử nghiệm

Tạo hai tệp nguồn sau:

**`src/com.example.greeting/module-info.java`**

~~~java
module com.example.greeting {
    exports com.example.greeting;
}
~~~

**`src/com.example.greeting/com/example/greeting/Greeting.java`**

~~~java
package com.example.greeting;

public final class Greeting {
    private Greeting() {}

    public static String text() {
        return "Xin chào từ module!";
    }
}
~~~

Tạo trước hai thư mục `out/com.example.greeting` và `mods` bằng lệnh tương ứng với hệ điều hành, rồi chạy:

~~~sh
javac -d out/com.example.greeting src/com.example.greeting/module-info.java src/com.example.greeting/com/example/greeting/Greeting.java
jar --create --file mods/com.example.greeting.jar -C out/com.example.greeting .
~~~

Kiểm tra JAR:

~~~sh
jar --describe-module --file mods/com.example.greeting.jar
~~~

Bạn sẽ thấy tên `com.example.greeting` và package được `exports`. Lúc này thư mục `mods` chứa một module JAR sẵn sàng để `ModuleFinder` dò tìm. Nếu các lệnh có khoảng trắng trong đường dẫn, dùng cú pháp trích dẫn thích hợp của shell.

## 5. Ví dụ: find, findAll và ModuleReference

Lưu chương trình sau ở **`InspectModulePath.java`**. Đây là chương trình Java chạy trên classpath thông thường, dùng ModuleFinder để *kiểm tra metadata* của module ở một đường dẫn do người dùng đưa vào.

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Comparator;

public class InspectModulePath {
    public static void main(String[] args) {
        if (args.length == 0) {
            System.err.println("Usage: java InspectModulePath <module-path-entry>...");
            return;
        }

        Path[] entries = Arrays.stream(args)
                .map(Path::of)
                .toArray(Path[]::new);

        ModuleFinder finder = ModuleFinder.of(entries);

        finder.find("com.example.greeting").ifPresentOrElse(ref -> {
            ModuleDescriptor descriptor = ref.descriptor();
            System.out.println("Tim thay: " + descriptor.name());
            System.out.println("Automatic: " + descriptor.isAutomatic());
            System.out.println("Requires: " + descriptor.requires());
            System.out.println("Location: " +
                    ref.location().map(Object::toString).orElse("(khong co URI)"));
        }, () -> System.out.println("Khong tim thay com.example.greeting"));

        System.out.println("Tat ca module trong finder:");
        finder.findAll().stream()
                .sorted(Comparator.comparing(ref -> ref.descriptor().name()))
                .forEach(ref -> System.out.println("- " +
                        ref.descriptor().name()));
    }
}
~~~

Biên dịch và chạy:

~~~sh
javac InspectModulePath.java
java InspectModulePath mods
~~~

Kết quả có thể có dạng (URI và cách hiển thị phụ thuộc hệ điều hành):

~~~text
Tim thay: com.example.greeting
Automatic: false
Requires: [mandated java.base]
Location: file:///.../mods/com.example.greeting.jar
Tat ca module trong finder:
- com.example.greeting
~~~

`requires()` của descriptor có thể biểu diễn `java.base` bằng các modifier khác nhau tùy module; không viết chương trình dựa trên chuỗi in ra của một `Set` hay thứ tự `findAll()`. Nếu `find(name)` trả về `Optional.empty()`, cần kiểm tra tên module thật và đường dẫn đã truyền.

Muốn tìm trực tiếp từ file JAR thay vì thư mục, có thể dùng:

~~~java
ModuleFinder oneJar = ModuleFinder.of(
        Path.of("mods/com.example.greeting.jar"));
~~~

Không thêm đồng thời cả `mods` và chính JAR bên trong `mods` vào finder nếu điều đó làm một module xuất hiện lặp lại.

## 6. Từ ModuleFinder tới module resolution

Sau khi finder nhìn thấy module, có thể dùng nó làm nguồn định nghĩa module cho `Configuration.resolve`. Ví dụ độc lập dưới đây giả định JAR đã được tạo ở mục 4.

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

public class ResolveGreeting {
    public static void main(String[] args) {
        ModuleFinder applicationModules = ModuleFinder.of(Path.of("mods"));

        Configuration configuration = ModuleLayer.boot()
                .configuration()
                .resolve(
                        applicationModules,
                        ModuleFinder.ofSystem(),
                        Set.of("com.example.greeting")
                );

        configuration.findModule("com.example.greeting")
                .ifPresent(module -> {
                    System.out.println("Resolved: " + module.name());
                    module.reads().forEach(dependency ->
                            System.out.println("Reads: " + dependency.name()));
                });
    }
}
~~~

Chạy bằng `javac ResolveGreeting.java` và `java ResolveGreeting`.

Ở đây:

- `ModuleLayer.boot().configuration()` cung cấp cấu hình cha từ boot layer.
- `applicationModules` là finder được ưu tiên để tìm module ứng dụng trong phép giải quyết này.
- `ModuleFinder.ofSystem()` có thể cung cấp module hệ thống chưa sẵn có trong cấu hình cha.
- `Set.of("com.example.greeting")` chọn **root module**. Resolver lần theo những `requires` cần thiết, kiểm tra tính hợp lệ và tạo `Configuration`; nó có thể báo `FindException` hoặc `ResolutionException` khi không thể giải quyết.
- `configuration.findModule(...)` kiểm tra module đã được resolve; khác với `finder.find(...)`, vốn chỉ kiểm tra module có thể được tìm thấy.

Đoạn code trên **chưa tạo `ModuleLayer` mới**. Nếu cần gọi class trong module được resolve lúc chạy, phải định nghĩa layer và class loader thích hợp, ví dụ qua các API `ModuleLayer.defineModulesWithOneLoader` hoặc `ModuleLayer.defineModulesWithManyLoaders`; chỉ `resolve` chưa làm được việc ấy.

## 7. Automatic module, system module và composed finder

**Modular JAR:** chứa descriptor `module-info.class`, `descriptor.isAutomatic()` là `false`. Tên, `requires`, `exports` đến từ descriptor.

**Automatic module:** JAR không có descriptor khi được xem như module-path entry; `descriptor.isAutomatic()` là `true`. Tên có thể lấy từ thuộc tính manifest `Automatic-Module-Name` hoặc được suy ra từ tên file JAR. Tên suy ra có thể thay đổi khi đổi tên/phiên bản JAR, nên không nên giả định tên theo ý mình. Kiểm tra bằng `jar --describe-module --file path/to/library.jar` hoặc liệt kê descriptor qua finder. Automatic module có các quy tắc readability/exports đặc biệt; không thể xem nó tương đương module tường minh.

**System modules:** `ModuleFinder.ofSystem()` tìm module thuộc runtime Java hiện tại, ví dụ `java.base`; không thay thế cho finder trỏ tới JAR ứng dụng trong `mods`.

Khi cần kết hợp nhiều nguồn tìm kiếm, có API `ModuleFinder.compose(first, second, ...)`. Finder ở vị trí sớm hơn được ưu tiên nếu nhiều finder cùng đưa ra một tên module; cần chủ động thiết kế thứ tự này. Khác với việc có tên trùng nhau trong *cùng một module path*, đây là cơ chế tổng hợp các finder.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `find(name)` rỗng | Đường dẫn sai, khác working directory hoặc tên module sai | In `Path.of("mods").toAbsolutePath()`, kiểm tra tệp tồn tại và `jar --describe-module`. |
| `findAll()` rỗng | Thư mục module path chưa có module hợp lệ | Xác nhận JAR hoặc exploded module đã được build, entry trỏ đúng cấp thư mục. |
| `FindException` khi dò tìm | JAR/descriptor không hợp lệ hoặc xung đột định nghĩa module, chẳng hạn trùng tên | Xem thông điệp exception, liệt kê module path, bỏ entry trùng và sửa JAR. |
| Finder thấy module nhưng resolution thất bại | Có `requires` chưa tìm được hoặc đồ thị phụ thuộc có vấn đề | Đọc `descriptor.requires()`, bổ sung finder có module phụ thuộc, xem root và cấu hình cha. |
| Tìm được nhưng không gọi được class lúc runtime | Chỉ discovery/resolve, chưa tạo layer hoặc chưa cấu hình readability/exports | Kiểm tra `Configuration`, `ModuleLayer`, exports và class loader. |
| JAR bên thứ ba có tên module lạ | JAR đang là automatic module, tên suy từ manifest/file | Kiểm tra `descriptor.name()` thay vì đoán theo tên thư viện. |

Lưu ý: `ModuleFinder.of(Path...)` làm việc với **module path** được bạn truyền cho nó. `--module-path` của launcher là tham số cấu hình khi chạy chương trình; hai cơ chế liên quan nhưng không có nghĩa việc đặt một JAR trên classpath sẽ tự khiến finder phát hiện được. Khi debug, luôn làm rõ entry nào đã đưa cho finder.

## 9. Bài tập thực hành

1. Đổi lệnh chạy inspector thành `java InspectModulePath mods/com.example.greeting.jar`. So sánh `find` và `findAll` với trường hợp trỏ thư mục.
2. Đổi tên truyền vào `finder.find` thành `com.example.unknown`. Giải thích vì sao `Optional` rỗng không đồng nghĩa với exception của resolution.
3. Tạo thêm module `com.example.consumer` khai báo `requires com.example.greeting;`, đóng gói vào `mods`. Đặt root cho resolver là `com.example.consumer` và quan sát cả hai module trong `Configuration`.
4. Đưa một JAR không có `module-info.class` vào thư mục riêng. Xem `descriptor.name()` và `isAutomatic()`. Thử chỉ rõ tên bằng manifest `Automatic-Module-Name` khi đóng gói lại JAR.
5. Tạm đổi đường dẫn `mods` thành đường dẫn không chứa module, sau đó phân biệt kết quả finder rỗng với lỗi khi resolver cố resolve root chưa tồn tại.

**Tự kiểm tra kiến thức:** `find` trả về gì khi thiếu module? `findAll` có bảo đảm thứ tự không? Lúc nào cần `Configuration.resolve`? Vì sao `ModuleFinder.ofSystem()` không thay cho đường dẫn JAR của ứng dụng? Để *chạy code* trong module vừa resolve, còn cần đối tượng nào?

## 10. Ghi nhớ

`ModuleFinder.of` tạo điểm bắt đầu cho việc **khám phá các module trên module path**. `find` và `findAll` cung cấp metadata qua `ModuleReference`, còn `Configuration.resolve` mới giải quyết đồ thị phụ thuộc từ các root được chỉ định. Khi cần thực thi module động, tiếp tục tạo `ModuleLayer` và chọn class loader phù hợp. Phân biệt ba bước này giúp tránh nhầm lẫn giữa “module có trên ổ đĩa”, “module được resolve” và “module đã sẵn sàng để tải lớp”.

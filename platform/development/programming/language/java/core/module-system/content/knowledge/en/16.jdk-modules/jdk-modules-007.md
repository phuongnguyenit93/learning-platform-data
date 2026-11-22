# jmods và module metadata của JDK

Java Platform Module System (JPMS), được đưa vào từ Java 9, chia nền tảng và ứng dụng Java thành các module có tên, có quan hệ phụ thuộc rõ ràng và có ranh giới đóng gói. Khi làm việc với module của JDK, cần phân biệt hai thứ liên quan nhưng khác vai trò: **module descriptor** mô tả cấu trúc và hợp đồng của module; **JMOD** là định dạng gói chứa module cùng các tài nguyên cần thiết cho quá trình liên kết runtime image.

Bài này dùng JDK 21 làm mốc. Tên module và một số dòng đầu ra có thể khác giữa các bản JDK hoặc nhà phân phối.

## 1. Module metadata nằm ở đâu?

Một module được khai báo bằng file `module-info.java`. Khi biên dịch, javac tạo ra `module-info.class`, chứa metadata nhị phân mà công cụ Java và JVM dùng để hiểu module.

Ví dụ:

~~~java
module com.acme.reporting {
    requires java.sql;
    requires transitive com.acme.model;
    requires static org.slf4j;

    exports com.acme.reporting.api;
    opens com.acme.reporting.internal to com.acme.di;

    uses com.acme.spi.ReportExporter;
    provides com.acme.spi.ReportExporter
        with com.acme.reporting.csv.CsvReportExporter;
}
~~~

Các chỉ thị chính:

- `requires` khai báo module mà module hiện tại cần đọc và sử dụng. Mọi module thông thường đều phụ thuộc ngầm định vào `java.base`; không cần viết `requires java.base`.
- `requires transitive` làm cho module phụ thuộc cũng được truyền vào khả năng đọc của module khách hàng. Chỉ dùng khi kiểu công khai trong API của bạn phụ thuộc vào kiểu thuộc module đó.
- `requires static` yêu cầu dependency khi biên dịch nhưng cho phép dependency vắng mặt lúc chạy, miễn là không có quan hệ khác buộc module đó phải được nạp.
- `exports` công khai một package để module khác truy cập các kiểu và thành viên public theo quy tắc truy cập Java. Nếu ghi `exports package.name to module.a, module.b`, package chỉ được xuất cho các module được liệt kê.
- `opens` cho phép truy cập phản chiếu sâu vào package, thường cần cho framework đọc field hoặc constructor không public. `opens` không thay thế `exports` cho việc sử dụng API Java thông thường.
- `uses` khai báo module tiêu thụ một service.
- `provides ... with ...` đăng ký implementation cho service đó, thường được tìm qua `ServiceLoader`.

Module descriptor còn chứa tên module, các modifier của module, danh sách package, dependency, export, open, service sử dụng/cung cấp và một số metadata tùy chọn như version hoặc main class. Tên module trong descriptor là định danh có thẩm quyền; không nên suy ra tên module chỉ từ tên file.

Vị trí descriptor tùy cách đóng gói:

- Module dạng thư mục (exploded module): `module-info.class` nằm ở thư mục gốc module.
- Modular JAR: `module-info.class` nằm ở gốc file JAR.
- JMOD: descriptor nằm trong phần `classes/module-info.class`.

## 2. JMOD là gì?

JMOD là định dạng archive do JDK cung cấp để đóng gói module cho **thời điểm liên kết** (link time), đặc biệt khi tạo runtime image bằng `jlink`. File thường có đuôi `.jmod`; các file module của một JDK đầy đủ thường nằm trong thư mục `jmods` dưới thư mục cài đặt JDK.

Một JMOD có thể chứa nhiều nhóm nội dung:

| Phần | Nội dung thường gặp |
|---|---|
| `classes/` | Class Java, resource và `module-info.class` |
| `bin/` | Native command đi kèm module |
| `conf/` | File cấu hình |
| `include/` | Header dùng khi tích hợp native code |
| `legal/` | Thông tin giấy phép và pháp lý |
| `lib/` | Native library |
| `man/` | Trang hướng dẫn lệnh |

Không phải module nào cũng có đủ mọi phần. Ví dụ, một module thuần Java có thể chủ yếu chứa nội dung trong `classes/`.

### JMOD khác modular JAR như thế nào?

| Tiêu chí | Modular JAR | JMOD |
|---|---|---|
| Mục đích | Phân phối thư viện hoặc ứng dụng Java | Cung cấp đầu vào cho công cụ liên kết runtime image |
| Metadata module | Có thể chứa `module-info.class` | Có thể chứa `module-info.class` trong `classes/` |
| Nội dung native/config/header/legal/man | Không có các section JMOD chuyên biệt | Có thể đóng gói các section này |
| Dùng trực tiếp với `java --module-path` | Có | Không |
| Đầu vào cho `jlink` | Có thể | Có, là trường hợp sử dụng quan trọng |

JMOD không phải một loại JAR khác tên. JVM launcher không nạp file `.jmod` trực tiếp như một module runtime. Khi chạy ứng dụng, hãy dùng modular JAR hoặc module dạng thư mục trên module path. JMOD chủ yếu được dùng để `jlink` xây dựng runtime image.

## 3. Thư mục jmods của JDK và runtime image

Trong một bản cài JDK đầy đủ, thư mục `$JAVA_HOME/jmods` thường chứa các file như:

- `java.base.jmod`
- `java.sql.jmod`
- `java.logging.jmod`
- `jdk.compiler.jmod`
- `jdk.management.jmod`

Tên và số lượng file phụ thuộc vào bản JDK. Các module này tạo thành nguồn đầu vào để công cụ liên kết chọn đúng phần nền tảng cần thiết.

Cần phân biệt thư mục `jmods/` với runtime image của JDK:

- `jmods/` chứa các gói module dùng trong quá trình liên kết.
- Runtime image đã cài đặt chứa các module để JVM chạy. Với JDK thông thường, dữ liệu module được lưu trong image nội bộ, thường thấy ở `lib/modules`.
- Một runtime image tối giản được tạo bởi `jlink` có thể chỉ chứa các module được chọn và không có thư mục `jmods/`.

Vì vậy, thiếu thư mục `jmods` thường có nghĩa là bạn đang dùng runtime image tối giản hoặc bản cài không cung cấp bộ JDK đầy đủ. Muốn chạy `jlink`, hãy dùng JDK phù hợp với hệ điều hành và kiến trúc đích.

## 4. Đọc metadata của module JDK bằng command line

Trước tiên, xem các module có trong runtime hiện tại:

~~~bash
java --list-modules
~~~

Lệnh này liệt kê module mà runtime image hiện tại cung cấp, kèm version nếu có. Nó hữu ích để kiểm tra module có tồn tại trong JDK đang chạy hay không.

Xem descriptor của một module trong runtime image:

~~~bash
java --describe-module java.sql
~~~

Đầu ra rút gọn có thể trông như sau (version và chi tiết có thể thay đổi):

~~~text
java.sql@21
exports java.sql
exports javax.sql
requires java.base mandated
requires java.logging transitive
requires java.transaction.xa transitive
uses java.sql.Driver
~~~

Cách đọc:

- `exports` cho biết package được công khai.
- `requires` cho biết dependency.
- `mandated` là modifier do nền tảng quy định; ví dụ dependency ngầm định vào `java.base`.
- `transitive` cho biết dependency được truyền tiếp cho module đọc module hiện tại.
- `uses` liệt kê service mà module tiêu thụ.

Để đọc trực tiếp file JMOD trong thư mục JDK, dùng công cụ `jmod`:

~~~bash
jmod describe "$JAVA_HOME/jmods/java.sql.jmod"
jmod list "$JAVA_HOME/jmods/java.sql.jmod"
~~~

- `jmod describe` in metadata của module trong file JMOD.
- `jmod list` liệt kê các entry được đóng gói.

Trên PowerShell của Windows, có thể dùng:

~~~powershell
$jmodFile = Join-Path $env:JAVA_HOME "jmods/java.sql.jmod"
jmod describe $jmodFile
jmod list $jmodFile
~~~

Nếu cần xem cấu trúc đã giải nén:

~~~bash
jmod extract --dir extracted "$JAVA_HOME/jmods/java.sql.jmod"
~~~

Sau đó có thể đọc bytecode của descriptor:

~~~bash
javap -v extracted/classes/module-info.class
~~~

`javap -v` hiển thị chi tiết class file, bao gồm thuộc tính `Module`. Cách này hữu ích khi cần kiểm tra metadata ở mức bytecode; trong công việc thông thường, `java --describe-module` hoặc `jmod describe` dễ đọc hơn.

Với modular JAR, dùng lệnh dành cho JAR:

~~~bash
jar --describe-module --file library.jar
~~~

Hãy chọn công cụ theo loại đầu vào: `jmod describe` cho JMOD, `jar --describe-module` cho JAR, và `java --describe-module` để hỏi runtime image đang chạy.

## 5. Đọc module metadata bằng Java API

Java cung cấp API trong package `java.lang.module`. `ModuleFinder.ofSystem()` tìm các module thuộc runtime image hiện tại; `ModuleReference` đại diện cho nguồn module được tìm thấy; `ModuleDescriptor` cung cấp metadata đã phân tích.

Ví dụ đọc dependency, package export và service của module `java.sql`:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.util.Comparator;

public class InspectSystemModule {
    public static void main(String[] args) {
        ModuleReference reference = ModuleFinder.ofSystem()
            .find("java.sql")
            .orElseThrow();

        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("module " + descriptor.name());

        descriptor.requires().stream()
            .sorted(Comparator.comparing(ModuleDescriptor.Requires::name))
            .forEach(r -> System.out.println(
                "requires " + r.name() + " " + r.modifiers()));

        descriptor.exports().stream()
            .sorted(Comparator.comparing(ModuleDescriptor.Exports::source))
            .forEach(e -> System.out.println(
                "exports " + e.source()
                    + (e.isQualified() ? " to " + e.targets() : "")));

        descriptor.uses().stream().sorted()
            .forEach(service -> System.out.println("uses " + service));

        descriptor.provides().stream()
            .sorted(Comparator.comparing(ModuleDescriptor.Provides::service))
            .forEach(p -> System.out.println(
                "provides " + p.service() + " with " + p.providers()));
    }
}
~~~

Một số API đáng nhớ:

- `ModuleFinder.ofSystem()`: tìm module của runtime image hiện tại.
- `ModuleFinder.of(path)`: tìm module trong một hoặc nhiều đường dẫn do ứng dụng cung cấp, chẳng hạn thư mục chứa modular JAR.
- `ModuleReference.descriptor()`: lấy descriptor của module được tìm thấy.
- `ModuleDescriptor.requires()`, `exports()`, `opens()`, `uses()`, `provides()`: đọc từng nhóm metadata.

Nếu đang chạy bên trong một ứng dụng và muốn biết class hiện tại thuộc module nào, có thể dùng API `Module`:

~~~java
Module module = java.sql.Driver.class.getModule();

System.out.println(module.getName());
System.out.println(module.isNamed());
System.out.println(module.getDescriptor());
~~~

`ModuleDescriptor` mô tả module; `Module` đại diện cho module đã được nạp trong một `ModuleLayer` tại runtime. Với unnamed module, `getName()` trả về `null` và `getDescriptor()` cũng có thể trả về `null`.

Lưu ý: `ModuleFinder.ofSystem()` chỉ tìm module hệ thống của runtime image. Khi kiểm tra module ứng dụng nằm trên module path, hãy tạo finder bằng `ModuleFinder.of(Path.of("mods"))` với đường dẫn phù hợp.

## 6. JMOD được dùng như thế nào khi tạo runtime image?

`jlink` ghép các module đã chọn cùng dependency của chúng để tạo một runtime image nhỏ hơn JDK đầy đủ. Module descriptor là cơ sở để công cụ giải quyết dependency; JMOD cung cấp nội dung module và các tài nguyên bổ sung cần thiết.

Ví dụ, tạo runtime chỉ có module `java.sql` và các dependency cần thiết:

~~~bash
jlink   --module-path "$JAVA_HOME/jmods"   --add-modules java.sql   --output runtime-sql
~~~

Nếu ứng dụng của bạn là module `com.acme.app`, đã được biên dịch và đóng gói thành modular JAR trong thư mục `mods`, có thể đưa cả JMOD của JDK và thư mục ứng dụng vào module path:

~~~bash
jlink   --module-path "$JAVA_HOME/jmods:mods"   --add-modules com.acme.app   --output runtime-app
~~~

Trên Windows, dấu phân cách các phần tử module path là dấu chấm phẩy:

~~~powershell
$jmods = Join-Path $env:JAVA_HOME "jmods"
jlink --module-path "$jmods;mods" --add-modules com.acme.app --output runtime-app
~~~

Sau khi tạo, kiểm tra runtime mới:

~~~bash
runtime/bin/java --list-modules
~~~

Trên Windows, executable tương ứng là `runtime\bin\java.exe`.

Một số tùy chọn thường gặp:

- `--add-modules`: chỉ định module gốc cần đưa vào image; các dependency bắt buộc sẽ được giải quyết theo descriptor.
- `--bind-services`: bổ sung các provider module phù hợp cho service binding.
- `--strip-debug`: bỏ thông tin debug.
- `--no-header-files` và `--no-man-pages`: bỏ header và man page nếu runtime không cần chúng.
- `--compress=2`: nén tài nguyên trong runtime image theo mức được công cụ hỗ trợ.

JMOD thường gắn với nền tảng cụ thể vì có thể chứa native library và native command. Không trộn JMOD từ các JDK khác hệ điều hành hoặc kiến trúc. Hãy dùng bộ `jmods` đi cùng JDK phù hợp với runtime image đích.

## 7. Lỗi thường gặp và cách xử lý

**Không tìm thấy lệnh `jmod` hoặc `jlink`.** Hai công cụ này thuộc JDK. Kiểm tra `JAVA_HOME` và `PATH`, rồi xác nhận `java`, `javac`, `jmod` đến từ cùng một bản cài. Trên Windows có thể chạy `where java` và `where jmod`; trên macOS/Linux dùng `which java` và `which jmod`.

**Không có thư mục `$JAVA_HOME/jmods`.** Có thể bạn đang trỏ `JAVA_HOME` vào runtime image tối giản hoặc bản cài chỉ dành cho chạy ứng dụng. Cài hoặc chọn JDK đầy đủ có cung cấp thư mục `jmods`.

**Đưa file `.jmod` vào `java --module-path` nhưng runtime không nạp được.** Đây là nhầm lẫn giữa link time và runtime. Dùng modular JAR hoặc module dạng thư mục để chạy ứng dụng; dùng JMOD làm đầu vào cho `jlink`.

**`jlink` báo không tìm thấy module.** Kiểm tra tên module trong descriptor, module path có trỏ đúng thư mục chứa JMOD/JAR hay không, và module gốc đã được chỉ định trong `--add-modules`. Tên file không nhất thiết là nguồn xác định tên module; descriptor mới là nguồn chính xác.

**Kết quả mô tả khác với tài liệu trên mạng.** Kiểm tra version của JDK đang dùng. Các bản JDK có thể thêm, bỏ hoặc thay đổi module, package export, dependency và service provider. Hãy xem đầu ra từ chính JDK mục tiêu trước khi kết luận.

## 8. Phân biệt nhanh các khái niệm

| Khái niệm | Vai trò | Cách xem |
|---|---|---|
| `module-info.java` | Nguồn khai báo module do lập trình viên viết | Đọc source |
| `module-info.class` | Descriptor nhị phân sau biên dịch | `javap -v` |
| Modular JAR | Gói module dùng trên module path khi biên dịch/chạy | `jar --describe-module` |
| JMOD | Gói module có thể chứa thêm native/config/header/legal/man, chủ yếu dùng lúc liên kết | `jmod describe`, `jmod list` |
| Module trong runtime image | Module thực tế mà JVM của runtime đó cung cấp | `java --list-modules`, `java --describe-module` |
| `ModuleDescriptor` | Java API để đọc metadata đã phân tích | `ModuleFinder` và `ModuleReference` |

## 9. Thực hành

1. Chạy `java --list-modules`, tìm `java.sql`, `java.logging` và `jdk.compiler`.
2. Chạy `java --describe-module java.sql`. Ghi lại các package được export và các dependency có modifier.
3. Dùng `jmod describe` với file `java.sql.jmod` trong thư mục `jmods`; đối chiếu với kết quả ở bước 2.
4. Dùng `jmod extract` để giải nén vào thư mục riêng, sau đó chạy `javap -v` trên `classes/module-info.class`.
5. Biên dịch và chạy ví dụ `InspectSystemModule`; xác nhận chương trình đọc được tên module, dependency, export và service.
6. Dùng `jlink` tạo runtime chỉ có `java.sql`, sau đó chạy `--list-modules` trên runtime vừa tạo để quan sát tập module đã được chọn.

Khi đọc cấu trúc module của JDK, hãy bắt đầu từ descriptor để hiểu module cần gì và công khai những gì. Sau đó dùng JMOD để xem nội dung được đóng gói và dùng `jlink` để quan sát cách các module đó tạo thành một runtime image có thể triển khai.

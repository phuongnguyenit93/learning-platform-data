# ModuleDescriptor: đọc metadata của module

## 1. Vai trò của ModuleDescriptor

Từ Java 9, Java Platform Module System (JPMS) cho phép một ứng dụng được chia thành các module có tên, khai báo phụ thuộc và kiểm soát package nào được module khác truy cập. Các khai báo này được viết trong file nguồn `module-info.java`, sau đó được biên dịch thành metadata trong `module-info.class`.

`java.lang.module.ModuleDescriptor` là API biểu diễn metadata đó dưới dạng đối tượng Java bất biến. Ta có thể dùng nó để đọc tên module, modifier, phiên bản, các module phụ thuộc, package được export hoặc open, các service module sử dụng và các implementation service module cung cấp.

`ModuleDescriptor` nằm trong package `java.lang.module`, thuộc module nền tảng `java.base`. API này phù hợp khi cần introspection, viết công cụ kiểm tra module, hiển thị dependency hoặc phân tích cấu hình JPMS mà không phải tự đọc cấu trúc nhị phân của `module-info.class`.

Cần phân biệt hai khái niệm:

- `Module` (`java.lang.Module`) đại diện cho một module đang tồn tại trong JVM.
- `ModuleDescriptor` (`java.lang.module.ModuleDescriptor`) mô tả metadata khai báo của module đó.

Descriptor mô tả các khai báo của module. Nó không phải bản ghi đầy đủ về mọi thay đổi truy cập được thực hiện động trong JVM.

## 2. Lấy ModuleDescriptor từ module đang chạy

Nếu đã có một class thuộc module cần kiểm tra, gọi `Class.getModule()` để lấy đối tượng `Module`, sau đó gọi `Module.getDescriptor()`.

~~~java
import java.lang.module.ModuleDescriptor;

public class CurrentModuleInfo {
    public static void main(String[] args) {
        Module module = CurrentModuleInfo.class.getModule();
        ModuleDescriptor descriptor = module.getDescriptor();

        if (descriptor == null) {
            System.out.println("Class đang thuộc unnamed module");
            return;
        }

        System.out.println("Module name: " + descriptor.name());
        System.out.println("Module modifiers: " + descriptor.modifiers());
    }
}
~~~

Với một named module, `getDescriptor()` thường trả về descriptor tương ứng. Nếu class chạy trên classpath và thuộc unnamed module, phương thức này trả về `null`, vì unnamed module không có module descriptor như named module. Vì vậy, luôn kiểm tra kết quả trước khi truy cập các thuộc tính.

Có thể lấy module của một class bất kỳ, ví dụ:

~~~java
ModuleDescriptor descriptor = String.class.getModule().getDescriptor();
~~~

Trong trường hợp này, descriptor mô tả module `java.base`, vì `String` thuộc module đó.

## 3. Tìm descriptor bằng ModuleFinder

Không cần module phải được load vào JVM mới có thể đọc metadata. Package `java.lang.module` cung cấp `ModuleFinder` để tìm module trên module path hoặc trong các module hệ thống. Kết quả `find(name)` là `Optional<ModuleReference>`; từ `ModuleReference` có thể lấy descriptor bằng `descriptor()`.

### 3.1. Đọc một module hệ thống

Ví dụ sau tìm module `java.sql` trong các module hệ thống của JDK:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;

public class FindSystemModule {
    public static void main(String[] args) {
        ModuleDescriptor descriptor = ModuleFinder.ofSystem()
                .find("java.sql")
                .map(ModuleReference::descriptor)
                .orElseThrow(() ->
                        new IllegalArgumentException("Không tìm thấy module java.sql"));

        System.out.println(descriptor.name());
        System.out.println(descriptor.requires());
    }
}
~~~

`ModuleFinder.ofSystem()` tìm các module thuộc runtime image của JDK. Tên truyền vào `find()` là tên module, chẳng hạn `java.sql`, không phải tên package như `java.sql` trong một câu lệnh import được hiểu như package.

### 3.2. Đọc module từ module path

Khi có một thư mục chứa các modular JAR hoặc module đã được biên dịch, dùng `ModuleFinder.of(Path...)`:

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class FindApplicationModule {
    public static void main(String[] args) {
        Path modulePath = Path.of("mods");

        ModuleDescriptor descriptor = ModuleFinder.of(modulePath)
                .find("com.acme.catalog")
                .map(ModuleReference::descriptor)
                .orElseThrow(() ->
                        new IllegalArgumentException("Không tìm thấy com.acme.catalog"));

        System.out.println("Found: " + descriptor.name());
    }
}
~~~

Đường dẫn truyền vào `ModuleFinder.of()` có thể trỏ đến thư mục module hoặc modular JAR. Nếu kết quả rỗng, hãy kiểm tra tên module thực tế trong `module-info.java`, vị trí file JAR và module path đang sử dụng.

`ModuleFinder` đọc và mô tả module mà không yêu cầu khởi tạo class của module đó. Đây là lựa chọn phù hợp cho công cụ phân tích dependency, kiểm tra cấu trúc bản phân phối hoặc tạo báo cáo trước khi khởi chạy ứng dụng.

## 4. Những metadata quan trọng

Các phương thức của `ModuleDescriptor` trả về metadata ở dạng có kiểu rõ ràng. Phần lớn tập hợp được trả về là các collection không thể sửa đổi; không nên giả định thứ tự phần tử của chúng. Nếu cần kết quả ổn định khi in báo cáo, hãy sắp xếp trước khi hiển thị.

| Phương thức | Ý nghĩa |
| --- | --- |
| `name()` | Tên module, ví dụ `java.sql` hoặc `com.acme.catalog`. |
| `modifiers()` | Các modifier của module như `OPEN`, `AUTOMATIC`, `SYNTHETIC`, `MANDATED`. |
| `version()` | Phiên bản đã được parse, trả về `Optional<ModuleDescriptor.Version>`. |
| `rawVersion()` | Chuỗi phiên bản gốc, trả về `Optional<String>`. |
| `requires()` | Các module mà module này khai báo phụ thuộc. |
| `exports()` | Các package được export cho module khác. |
| `opens()` | Các package được mở cho truy cập reflection. |
| `uses()` | Tên các service mà module cần sử dụng. |
| `provides()` | Các service cùng danh sách provider implementation mà module cung cấp. |
| `packages()` | Tập hợp tên package thuộc module theo metadata descriptor. |
| `mainClass()` | Tên lớp main nếu descriptor khai báo, trả về `Optional<String>`. |
| `isOpen()` | Cho biết module được khai báo là open module. |
| `isAutomatic()` | Cho biết đây là automatic module. |

### 4.1. Tên, modifier và phiên bản

`name()` trả về tên module. `modifiers()` cho biết những thuộc tính đặc biệt của descriptor. Hai trạng thái thường cần kiểm tra riêng là:

- `isOpen()`: module được khai báo bằng cú pháp `open module`, nghĩa là các package của module được mở cho truy cập reflection theo quy tắc của JPMS.
- `isAutomatic()`: module là automatic module, thường được suy ra từ một JAR không có `module-info.class` khi JAR đó được đặt trên module path.

Không phải module nào cũng khai báo version hoặc main class. Do đó, `version()`, `rawVersion()` và `mainClass()` trả về `Optional`; chỉ đọc giá trị khi có mặt.

### 4.2. requires — dependency của module

Mỗi phần tử trong `requires()` là một `ModuleDescriptor.Requires`. Có thể đọc tên module phụ thuộc bằng `name()` và modifier bằng `modifiers()`.

Các modifier quan trọng:

- `TRANSITIVE`: dependency được truyền tiếp cho module phụ thuộc vào module hiện tại.
- `STATIC`: dependency được yêu cầu khi biên dịch nhưng có thể không bắt buộc ở runtime.
- `SYNTHETIC` và `MANDATED`: metadata được đánh dấu là synthetic hoặc mandated bởi công cụ/ngôn ngữ.

Ví dụ, khai báo `requires transitive com.acme.domain;` sẽ tạo một dependency có modifier `TRANSITIVE`. Một descriptor cũng có thể chứa dependency `java.base` với modifier `MANDATED`, dù ta không viết trực tiếp dòng `requires java.base;` trong source. Vì vậy, không nên coi mọi phần tử trong `requires()` đều là một dòng khai báo tường minh do người viết module thêm vào.

### 4.3. exports — package được công khai

Mỗi phần tử trong `exports()` là một `ModuleDescriptor.Exports`. Dùng `source()` để lấy tên package được export.

- Export không giới hạn module đích cho phép các module khác đọc public API của package.
- Qualified export chỉ cho phép các module có tên nằm trong `targets()` truy cập package đó.
- `isQualified()` cho biết export có giới hạn module đích hay không.

Export điều khiển khả năng truy cập các public type ở cấp module. Nó không biến mọi thành phần package thành public; quy tắc truy cập của Java như `public`, `protected`, package-private và `private` vẫn có hiệu lực.

### 4.4. opens — package mở cho reflection

Mỗi phần tử trong `opens()` là một `ModuleDescriptor.Opens`. Cấu trúc tương tự `Exports`, gồm package nguồn, modifier và danh sách module đích.

`opens` phục vụ deep reflection, chẳng hạn framework cần truy cập field hoặc constructor không public. Nó khác với `exports`: export phục vụ truy cập API theo quy tắc truy cập Java thông thường, còn open cho phép reflection sâu theo quy tắc module.

Một module có khai báo `open module` sẽ mở tất cả package cho reflection. Với module thông thường, có thể chỉ mở một số package bằng các chỉ thị `opens` riêng lẻ. `isOpen()` kiểm tra trạng thái open ở cấp toàn module; `opens()` liệt kê các chỉ thị mở package trong descriptor.

### 4.5. uses và provides — ServiceLoader

JPMS tích hợp cơ chế service:

- `uses()` chứa tên interface hoặc abstract service mà module tiêu thụ.
- `provides()` chứa các `ModuleDescriptor.Provides`; `service()` trả về tên service, còn `providers()` trả về tên các lớp triển khai.

Metadata này tương ứng với các chỉ thị `uses` và `provides ... with ...` trong `module-info.java`. Nó giúp công cụ kiểm tra cấu hình plugin/service mà không phải tự phân tích source code.

### 4.6. packages và mainClass

`packages()` cung cấp tập hợp tên package mà descriptor ghi nhận. Không nên dùng riêng `exports()` để suy ra toàn bộ package của module, vì một module có thể chứa package nội bộ không export.

`mainClass()` trả về tên lớp main nếu metadata có khai báo. Giá trị này hữu ích khi kiểm tra module có entry point được chỉ định hay không; nó không tự khởi chạy lớp đó.

## 5. Ví dụ đọc toàn bộ metadata

Giả sử module có descriptor như sau:

~~~java
module com.acme.catalog {
    requires java.sql;
    requires transitive com.acme.domain;

    exports com.acme.catalog.api;
    exports com.acme.catalog.spi to com.acme.plugin;

    opens com.acme.catalog.model to com.fasterxml.jackson.databind;

    uses com.acme.spi.Formatter;
    provides com.acme.spi.Formatter
            with com.acme.catalog.JsonFormatter;
}
~~~

Ta có thể dùng đoạn chương trình sau để đọc descriptor của module hệ thống `java.sql`. Đổi `ModuleFinder.ofSystem()` thành `ModuleFinder.of(Path.of("mods"))` và đổi tên module nếu muốn kiểm tra module ứng dụng.

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.util.Comparator;

public class ModuleDescriptorInspector {
    public static void main(String[] args) {
        ModuleDescriptor descriptor = ModuleFinder.ofSystem()
                .find("java.sql")
                .map(ModuleReference::descriptor)
                .orElseThrow();

        print(descriptor);
    }

    private static void print(ModuleDescriptor descriptor) {
        System.out.println("Name: " + descriptor.name());
        System.out.println("Modifiers: " + descriptor.modifiers());
        System.out.println("Open module: " + descriptor.isOpen());
        System.out.println("Automatic module: " + descriptor.isAutomatic());

        descriptor.version().ifPresent(
                version -> System.out.println("Version: " + version));
        descriptor.rawVersion().ifPresent(
                version -> System.out.println("Raw version: " + version));
        descriptor.mainClass().ifPresent(
                mainClass -> System.out.println("Main class: " + mainClass));

        System.out.println("\nRequires:");
        descriptor.requires().stream()
                .sorted(Comparator.comparing(ModuleDescriptor.Requires::name))
                .forEach(required -> System.out.printf(
                        "  %s %s%n", required.name(), required.modifiers()));

        System.out.println("\nExports:");
        descriptor.exports().stream()
                .sorted(Comparator.comparing(ModuleDescriptor.Exports::source))
                .forEach(export -> {
                    String targets = export.isQualified()
                            ? String.join(", ", export.targets())
                            : "all modules";
                    System.out.printf("  %s -> %s%n", export.source(), targets);
                });

        System.out.println("\nOpens:");
        descriptor.opens().stream()
                .sorted(Comparator.comparing(ModuleDescriptor.Opens::source))
                .forEach(open -> {
                    String targets = open.isQualified()
                            ? String.join(", ", open.targets())
                            : "all modules";
                    System.out.printf("  %s -> %s%n", open.source(), targets);
                });

        System.out.println("\nUses:");
        descriptor.uses().stream().sorted().forEach(
                service -> System.out.println("  " + service));

        System.out.println("\nProvides:");
        descriptor.provides().stream()
                .sorted(Comparator.comparing(ModuleDescriptor.Provides::service))
                .forEach(provides -> System.out.printf(
                        "  %s -> %s%n", provides.service(), provides.providers()));

        System.out.println("\nPackages:");
        descriptor.packages().stream().sorted().forEach(
                packageName -> System.out.println("  " + packageName));
    }
}
~~~

Kết quả thực tế phụ thuộc descriptor của module được tìm thấy và phiên bản JDK. Ví dụ này sắp xếp các tập hợp theo tên để log dễ đọc và có thứ tự ổn định. Với module `com.acme.catalog`, các nhóm metadata sẽ phản ánh dependency, package API công khai, package mở cho Jackson và service provider đã khai báo trong ví dụ.

## 6. Đọc trực tiếp file module-info.class

Khi đã có đường dẫn đến file `module-info.class` đã biên dịch, có thể dùng `ModuleDescriptor.read(InputStream)`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.module.ModuleDescriptor;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadModuleInfoClass {
    public static ModuleDescriptor read(Path moduleInfoClass)
            throws IOException {
        try (InputStream input = Files.newInputStream(moduleInfoClass)) {
            return ModuleDescriptor.read(input);
        }
    }
}
~~~

Phương thức này đọc bytecode descriptor đã biên dịch; nó không đọc file nguồn `module-info.java` và cũng không nhận nguyên một JAR như thể đó là luồng `module-info.class`. Nếu descriptor nằm trong modular JAR hoặc module path, `ModuleFinder` thường thuận tiện hơn vì nó xử lý việc tìm module và cung cấp `ModuleReference`.

Dữ liệu không phải descriptor hợp lệ có thể làm thao tác đọc thất bại. Khi đọc từ file, cần xử lý `IOException`; descriptor sai định dạng có thể phát sinh `InvalidModuleDescriptorException`.

## 7. Tạo descriptor bằng Builder

Ngoài việc đọc metadata có sẵn, API còn cho phép tạo một `ModuleDescriptor` trong bộ nhớ bằng builder:

~~~java
import java.lang.module.ModuleDescriptor;

public class BuildDescriptor {
    public static void main(String[] args) {
        ModuleDescriptor descriptor = ModuleDescriptor
                .newModule("com.acme.tools")
                .requires("java.logging")
                .exports("com.acme.tools.api")
                .build();

        System.out.println(descriptor.name());
        System.out.println(descriptor.requires());
        System.out.println(descriptor.exports());
    }
}
~~~

Builder hữu ích khi viết test hoặc công cụ cần tạo một descriptor để xử lý tiếp. Đối tượng được tạo chỉ là metadata trong bộ nhớ; gọi `build()` không tự tạo file `module-info.class`, không ghi JAR và không thêm module vào một `ModuleLayer`.

## 8. Giới hạn và những nhầm lẫn thường gặp

1. **Descriptor có thể không tồn tại.** `Module.getDescriptor()` trả về `null` đối với unnamed module. Hãy kiểm tra null trước khi đọc metadata.
2. **Descriptor phản ánh khai báo.** Các thao tác động như `Module.addReads()`, `addExports()` hoặc `addOpens()` có thể thay đổi khả năng truy cập ở runtime. Những thay đổi đó không biến descriptor ban đầu thành một bản ghi trạng thái runtime đầy đủ.
3. **Không đồng nhất exports với opens.** `exports` công khai package theo quy tắc truy cập module; `opens` cho phép deep reflection. Một framework cần reflection sâu có thể cần package được mở dù package đó không phải public API.
4. **Không đồng nhất isOpen() với opens().** `isOpen()` cho biết module được khai báo là open module. `opens()` mô tả các chỉ thị mở package trong descriptor của module thông thường.
5. **Không phải mọi dependency đều được viết tường minh.** `requires()` có thể có các dependency được đánh dấu `MANDATED`, ví dụ `java.base`. Hãy đọc modifier trước khi kết luận về nguồn gốc khai báo.
6. **Không giả định có version hoặc main class.** Hai thuộc tính này là optional; code phải xử lý trường hợp không có giá trị.
7. **Không dựa vào thứ tự Set.** `requires()`, `exports()`, `opens()`, `uses()`, `provides()` và `packages()` là các tập hợp. Sắp xếp khi cần log, snapshot hoặc báo cáo ổn định.
8. **Tên module khác tên package.** `ModuleFinder.find()` nhận tên module, ví dụ `java.sql` hoặc `com.acme.catalog`; nó không tìm theo tên một package bất kỳ.

## 9. Chọn API phù hợp

| Nhu cầu | API nên dùng |
| --- | --- |
| Đọc descriptor của module chứa một class đang chạy | `SomeClass.class.getModule().getDescriptor()` |
| Tìm metadata của module JDK | `ModuleFinder.ofSystem().find(name)` |
| Tìm metadata của modular JAR/thư mục module | `ModuleFinder.of(path...).find(name)` |
| Đọc byte của một file `module-info.class` đã biên dịch | `ModuleDescriptor.read(inputStream)` |
| Tạo descriptor tạm trong bộ nhớ | `ModuleDescriptor.newModule(name)` hoặc builder tương ứng |
| Kiểm tra khả năng truy cập thực tế giữa các module lúc runtime | Các phương thức của `Module`, chẳng hạn `canRead()`, `isExported()`, `isOpen()` |

Khi viết công cụ phân tích JPMS, nên dùng `ModuleDescriptor` để đọc cấu trúc khai báo và dùng `Module` khi câu hỏi liên quan đến trạng thái truy cập thực tế của một module đang chạy. Kết hợp đúng hai API giúp tránh nhầm lẫn giữa metadata được biên dịch và trạng thái runtime của JVM.

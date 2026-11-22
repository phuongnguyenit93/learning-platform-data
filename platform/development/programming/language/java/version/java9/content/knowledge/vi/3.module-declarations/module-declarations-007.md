# ModuleDescriptor và việc đọc thông tin khai báo

JPMS (Java Platform Module System) mô tả một mô-đun bằng tệp `module-info.java`. Khi biên dịch, khai báo này được lưu thành `module-info.class` ở gốc mô-đun. `ModuleDescriptor` trong `java.lang.module` cung cấp mô hình bất biến để đọc những thông tin đã được biên dịch đó: tên mô-đun, phụ thuộc, package được xuất, package được mở cho reflection và khai báo dịch vụ.

`ModuleDescriptor` vẫn là API chuẩn trong các phiên bản Java hiện hành. Khi cần kiểm tra một mô-đun nằm trên module path, cách thông dụng là dùng `ModuleFinder` để tìm mô-đun rồi lấy descriptor từ `ModuleReference`. Cách này giúp tránh tự giải mã cấu trúc nhị phân của `module-info.class`.

## 1. Những thông tin có trong ModuleDescriptor

| API | Ý nghĩa |
| --- | --- |
| `name()` | Tên mô-đun được khai báo. |
| `modifiers()`, `isOpen()`, `isAutomatic()` | Các modifier và trạng thái của mô-đun. |
| `requires()` | Những mô-đun mà mô-đun hiện tại đọc được theo khai báo phụ thuộc. |
| `exports()` | Những package được công khai cho mô-đun khác truy cập ở mức kiểu công khai. |
| `opens()` | Những package được mở cho truy cập reflection sâu khi chạy. |
| `uses()` | Các service mà mô-đun cần tìm thông qua cơ chế service. |
| `provides()` | Các service mà mô-đun cung cấp cùng lớp triển khai. |
| `packages()` | Tập package thuộc mô-đun. |
| `version()`, `rawVersion()` | Phiên bản mô-đun nếu descriptor có khai báo. |
| `mainClass()` | Lớp main được khai báo nếu có. |

Các thuộc tính phiên bản và main class là tùy chọn. Ứng dụng không nên suy ra phiên bản phát hành của sản phẩm chỉ từ `ModuleDescriptor.version()` nếu quá trình đóng gói không đặt module version rõ ràng.

### `requires`, `exports` và `opens`

- `requires` khai báo quan hệ phụ thuộc. `requires transitive` truyền khả năng đọc phụ thuộc đến các mô-đun phụ thuộc vào mô-đun hiện tại. `requires static` cho phép phụ thuộc chỉ cần có lúc biên dịch và có thể không hiện diện lúc chạy.
- `exports` công khai package cho mã thuộc mô-đun khác truy cập các kiểu public. Nếu `targets()` rỗng, package được export không giới hạn tới các mô-đun khác; nếu có tên đích, đây là qualified export.
- `opens` cho phép reflection sâu trên package trong thời gian chạy. `opens` không thay thế `exports`: một package có thể được mở để framework đọc/ghi thành viên bằng reflection mà không trở thành API compile-time công khai.
- `open module` mở tất cả package cho reflection. `isOpen()` cho biết descriptor có modifier này; nó khác với việc chỉ mở một số package qua `opens`.

Các tập `requires()`, `exports()`, `opens()`, `uses()` và `provides()` phản ánh descriptor đã biên dịch. Với mô-đun thông thường, descriptor cũng có thể hiển thị `java.base` là dependency có modifier `MANDATED`, dù dòng `requires java.base` không xuất hiện trong tệp nguồn.

## 2. Tìm descriptor bằng ModuleFinder

`ModuleFinder.of(Path...)` tìm các mô-đun trong những vị trí được chỉ định, chẳng hạn modular JAR hoặc thư mục mô-đun đã biên dịch. `ModuleFinder.ofSystem()` tìm các mô-đun của JDK đang chạy. Mỗi kết quả là một `ModuleReference`; gọi `descriptor()` để lấy metadata.

Ví dụ ngắn để đọc descriptor của mô-đun `java.sql` trong JDK hiện tại:

```java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;

ModuleDescriptor descriptor = ModuleFinder.ofSystem()
        .find("java.sql")
        .orElseThrow(() -> new IllegalStateException("Không tìm thấy java.sql"))
        .descriptor();

System.out.println(descriptor.name());
System.out.println(descriptor.requires());
System.out.println(descriptor.exports());
```

Kết quả đầu tiên là `java.sql`. Các tập phụ thuộc và export phụ thuộc phiên bản JDK đang chạy, vì vậy nên đọc trực tiếp thay vì đóng đinh toàn bộ kết quả của một bản JDK vào chương trình.

## 3. Chương trình đọc descriptor từ modular JAR

Ví dụ sau nhận một đường dẫn module path entry, tìm các mô-đun tại đó và in những phần chính của descriptor. Các tập được sắp xếp để kết quả dễ so sánh giữa các lần chạy.

**ModuleDescriptorInspector.java**

```java
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Set;
import java.util.TreeSet;

public class ModuleDescriptorInspector {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java ModuleDescriptorInspector <module-path-entry>");
            return;
        }

        Set<ModuleReference> modules = ModuleFinder.of(Path.of(args[0])).findAll();
        if (modules.isEmpty()) {
            throw new IllegalArgumentException("No modules found at: " + args[0]);
        }

        modules.stream()
                .sorted(Comparator.comparing(ref -> ref.descriptor().name()))
                .forEach(ModuleDescriptorInspector::printDescriptor);
    }

    private static void printDescriptor(ModuleReference reference) {
        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("Module: " + descriptor.name());
        System.out.println("Automatic: " + descriptor.isAutomatic());
        System.out.println("Open: " + descriptor.isOpen());
        System.out.println("Version: " + descriptor.version()
                .map(version -> version.toString()).orElse("(not declared)"));
        System.out.println("Main class: " + descriptor.mainClass().orElse("(not declared)"));

        System.out.println("Requires:");
        descriptor.requires().stream()
                .sorted(Comparator.comparing(ModuleDescriptor.Requires::name))
                .forEach(requirement -> System.out.println("  " + requirement.name()
                        + " " + new TreeSet<>(requirement.modifiers())));

        System.out.println("Exports:");
        descriptor.exports().stream()
                .sorted(Comparator.comparing(ModuleDescriptor.Exports::source))
                .forEach(export -> System.out.println("  " + export.source()
                        + " -> " + targetText(export.targets())));

        System.out.println("Opens:");
        descriptor.opens().stream()
                .sorted(Comparator.comparing(ModuleDescriptor.Opens::source))
                .forEach(open -> System.out.println("  " + open.source()
                        + " -> " + targetText(open.targets())));

        printStrings("Packages", descriptor.packages());
        printStrings("Uses", descriptor.uses());

        System.out.println("Provides:");
        if (descriptor.provides().isEmpty()) {
            System.out.println("  (none)");
        } else {
            descriptor.provides().stream()
                    .sorted(Comparator.comparing(ModuleDescriptor.Provides::service))
                    .forEach(provide -> System.out.println("  " + provide.service()
                            + " with " + String.join(", ", new TreeSet<>(provide.providers()))));
        }
        System.out.println();
    }

    private static void printStrings(String title, Set<String> values) {
        System.out.println(title + ":");
        if (values.isEmpty()) {
            System.out.println("  (none)");
            return;
        }
        new TreeSet<>(values).forEach(value -> System.out.println("  " + value));
    }

    private static String targetText(Set<String> targets) {
        return targets.isEmpty() ? "ALL" : String.join(", ", new TreeSet<>(targets));
    }
}
```

### Tạo mô-đun mẫu để kiểm tra

Tạo cấu trúc nguồn sau:

```text
src/
└── com.example.orders/
    ├── module-info.java
    └── com/example/orders/
        ├── api/Order.java
        └── internal/OrderRepository.java
```

**src/com.example.orders/module-info.java**

```java
module com.example.orders {
    requires java.sql;
    exports com.example.orders.api;
    opens com.example.orders.internal;
}
```

**src/com.example.orders/com/example/orders/api/Order.java**

```java
package com.example.orders.api;

public record Order(String id) {
}
```

**src/com.example.orders/com/example/orders/internal/OrderRepository.java**

```java
package com.example.orders.internal;

public final class OrderRepository {
}
```

Trong PowerShell, chạy từ thư mục chứa `src`:

```powershell
New-Item -ItemType Directory -Force -Path out, build | Out-Null
javac -d out --module-source-path src -m com.example.orders
jar --create --file build/com.example.orders.jar -C out/com.example.orders .
javac --release 17 ModuleDescriptorInspector.java
java ModuleDescriptorInspector build/com.example.orders.jar
```

Với mô-đun mẫu trên, kết quả của chương trình inspector là:

```text
Module: com.example.orders
Automatic: false
Open: false
Version: (not declared)
Main class: (not declared)
Requires:
  java.base [MANDATED]
  java.sql []
Exports:
  com.example.orders.api -> ALL
Opens:
  com.example.orders.internal -> ALL
Packages:
  com.example.orders.api
  com.example.orders.internal
Uses:
  (none)
Provides:
  (none)
```

`java.base [MANDATED]` là dependency ngầm định của mô-đun thông thường. `java.sql []` là dependency được khai báo trực tiếp và không có modifier. `ALL` trong kết quả inspector có nghĩa `targets()` rỗng, tức export/open không giới hạn theo tên mô-đun đích.

## 4. Đọc descriptor khác với resolve và truy cập mô-đun

`ModuleDescriptor` chỉ mô tả metadata của một mô-đun. Việc đọc thành công descriptor không chứng minh toàn bộ dependency đã được resolve, mô-đun đã được đưa vào runtime layer hoặc một lớp cụ thể có thể được truy cập. Quá trình tìm mô-đun, resolve đồ thị phụ thuộc và tạo `ModuleLayer` là các bước riêng của JPMS.

`ModuleReference.location()` có thể cung cấp URI vị trí mô-đun nếu có. `ModuleReference.open()` mở một `ModuleReader` để liệt kê hoặc đọc resource bên trong mô-đun. Dùng `ModuleReader` khi cần nội dung resource; dùng `descriptor()` khi cần metadata khai báo.

Trong trường hợp đã có trực tiếp byte của tệp `module-info.class`, `ModuleDescriptor.read(InputStream)` hoặc overload nhận `ByteBuffer` có thể đọc descriptor ở mức thấp hơn. Với đường dẫn JAR hoặc module path, `ModuleFinder` thường phù hợp hơn vì nó tìm và tạo `ModuleReference` theo cơ chế của JPMS.

## 5. Công cụ dòng lệnh để kiểm tra nhanh

- `jar --describe-module --file build/com.example.orders.jar` hiển thị descriptor được đóng gói trong JAR.
- `java --module-path build/com.example.orders.jar --describe-module com.example.orders` yêu cầu runtime mô tả mô-đun theo module path đã chỉ định.
- `java --describe-module java.sql` xem descriptor của mô-đun JDK có tên `java.sql` trong runtime hiện tại.

Các lệnh này hữu ích khi kiểm tra artifact trước khi chạy ứng dụng. Nếu kết quả khác với `module-info.java`, hãy kiểm tra đúng JAR vừa build, đường dẫn module path và artifact thực tế đang được chạy.

## 6. Những nhầm lẫn thường gặp

1. **Xem `exports` và `opens` là tương đương:** `exports` phục vụ truy cập kiểu public giữa các mô-đun; `opens` phục vụ reflection sâu lúc chạy. Chỉ mở package khi framework hoặc use case thực sự cần.
2. **Coi descriptor là kết quả resolve:** descriptor ghi lại khai báo của một mô-đun riêng lẻ. Muốn biết đồ thị đã resolve, cần kiểm tra `Configuration` hoặc `ModuleLayer` tương ứng.
3. **Giả định luôn có version hoặc main class:** cả hai trường đều có thể vắng mặt. Hãy xử lý `Optional` thay vì gọi `get()` vô điều kiện.
4. **Chỉ kiểm tra tên mô-đun:** khi chẩn đoán lỗi truy cập, cần xem cả `requires`, `exports`, `opens` và module đích. Tên mô-đun đúng chưa đủ để chứng minh package được phép truy cập.
5. **Tự đọc cấu trúc nhị phân thay vì dùng API:** `module-info.class` có cấu trúc class-file riêng. Dùng `ModuleFinder` và `ModuleDescriptor` để tránh phụ thuộc vào chi tiết định dạng.

Khi xây dựng công cụ kiểm tra dependency, audit module path hoặc chẩn đoán lỗi encapsulation, có thể dùng `ModuleDescriptor` làm nguồn metadata có cấu trúc. Nên ghi nhận cả tên mô-đun, các quan hệ `requires`, phạm vi `exports`/`opens` và nguồn JAR đang được kiểm tra để kết quả có thể đối chiếu với artifact triển khai.
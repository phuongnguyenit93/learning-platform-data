# Kiểm tra tập mô-đun bằng `--list-modules` và `--describe-module`

Java Platform Module System (JPMS) cung cấp các lệnh để xem những mô-đun mà runtime có thể quan sát và đọc descriptor của từng mô-đun. Hai lệnh quan trọng là:

- `java --list-modules`: liệt kê các mô-đun có thể quan sát trong runtime image và trên module path.
- `java --describe-module <module-name>`: hiển thị mô tả của một mô-đun theo tên mô-đun.

Khi cần kiểm tra một JAR cụ thể mà không cần tra cứu mô-đun qua module path, dùng thêm `jar --describe-module --file <jar-file>`.

## 1. Phân biệt module path, mô-đun có thể quan sát và mô-đun đã được resolve

JPMS tìm mô-đun từ hai nguồn chính:

- **Runtime image**: các mô-đun đi kèm JDK/JRE đang chạy, thường có tên bắt đầu bằng `java.` hoặc `jdk.`.
- **Module path**: các mô-đun ứng dụng hoặc thư viện được cung cấp qua tùy chọn `--module-path` (`-p`). Module path có thể chứa modular JAR và thư mục mô-đun đã giải nén (exploded module).

Khái niệm **observable module** có nghĩa là mô-đun mà hệ thống mô-đun có thể tìm thấy từ các nguồn đó. Một mô-đun xuất hiện trong `--list-modules` chưa chắc đã được resolve hoặc nạp vào ứng dụng hiện tại.

Ví dụ, một JAR mô-đun nằm trên module path có thể xuất hiện trong danh sách dù ứng dụng chưa khai báo `requires` tới nó. `--list-modules` giúp kiểm tra khả năng quan sát, không phải báo cáo đầy đủ đồ thị dependency đã resolve.

## 2. `java --list-modules` — liệt kê các mô-đun

Cú pháp:

```bash
java --list-modules
java --module-path mods --list-modules
```

Lệnh đầu liệt kê các mô-đun có thể quan sát từ runtime image. Lệnh thứ hai bổ sung các mô-đun có thể quan sát trong thư mục `mods` trên module path.

Ví dụ, runtime image có thể chứa các mô-đun như:

```text
java.base@24.0.2
java.compiler@24.0.2
java.logging@24.0.2
java.sql@24.0.2
java.xml@24.0.2
jdk.compiler@24.0.2
jdk.jartool@24.0.2
```

Phiên bản hiển thị phụ thuộc JDK đang chạy. Danh sách đầy đủ thường dài hơn nhiều; ví dụ trên chỉ trích một số dòng tiêu biểu.

Nếu module path có mô-đun ứng dụng, phần tương ứng có thể xuất hiện như sau:

```text
com.example.inventory file:///.../mods/com.example.inventory.jar
```

JAR automatic module có thể được đánh dấu `automatic`:

```text
legacy.utils@2.1 file:///.../mods/legacy-utils-2.1.jar automatic
```

Để lọc một tên mô-đun khi dùng PowerShell:

```powershell
java --module-path mods --list-modules | Select-String 'java.sql|com.example.inventory'
```

Trên Bash hoặc shell tương tự:

```bash
java --module-path mods --list-modules | grep -E 'java.sql|com.example.inventory'
```

### Điều cần nhớ về `--list-modules`

- Danh sách gồm các mô-đun có thể quan sát, không chỉ các mô-đun mà ứng dụng đang dùng.
- Mô-đun trên module path có thể xuất hiện dù chưa được resolve.
- JAR trên classpath thuộc unnamed module; nó không được liệt kê như một named module riêng.
- Tên mô-đun và tên tệp JAR không nhất thiết giống nhau, đặc biệt với automatic module.

## 3. `java --describe-module` — xem descriptor của một mô-đun

Cú pháp:

```bash
java --describe-module java.base
java --describe-module java.sql
java --module-path mods --describe-module com.example.inventory
```

Đối số là **tên mô-đun**, không phải đường dẫn JAR. Với mô-đun trên module path, truyền cùng module path khi tra cứu. Với mô-đun của runtime image như `java.sql`, không cần chỉ định module path.

Ví dụ rút gọn khi chạy `java --describe-module java.sql`:

```text
java.sql@24.0.2
exports java.sql
exports javax.sql
requires java.logging transitive
requires java.xml transitive
requires java.base mandated
requires java.transaction.xa transitive
uses java.sql.Driver
```

Kết quả giúp đọc các thành phần chính của descriptor:

| Dòng trong kết quả | Ý nghĩa |
| --- | --- |
| `java.sql@24.0.2` | Tên mô-đun và phiên bản (nếu có) |
| `exports java.sql` | Package được export không giới hạn cho mô-đun khác |
| `qualified exports ... to ...` | Package chỉ được export cho những mô-đun được chỉ định |
| `requires other.module` | Dependency tới mô-đun khác |
| `requires other.module transitive` | Dependency được truyền khả năng đọc tới mô-đun đọc mô-đun hiện tại |
| `requires other.module static` | Dependency chỉ bắt buộc lúc biên dịch; có thể vắng mặt khi chạy nếu không được dùng |
| `requires java.base mandated` | Dependency ngầm định do hệ thống mô-đun thêm vào |
| `opens package.name` | Package được mở cho phản chiếu sâu ở runtime |
| `uses service.Type` | Mô-đun sử dụng một service theo ServiceLoader |
| `provides service.Type with Impl` | Mô-đun cung cấp implementation cho một service |
| `contains package.name` | Package nằm trong mô-đun nhưng không được export như API công khai |
| `main-class ...` | Lớp main được khai báo trong descriptor hoặc metadata của JAR |

Không phải mô-đun nào cũng có tất cả các dòng trên. Kết quả phản ánh descriptor thực tế và có thể khác giữa các phiên bản JDK.

`java --describe-module` tự hiển thị các directive cần thiết; không thêm tùy chọn `--verbose` vào lệnh này.

## 4. `jar --describe-module` — kiểm tra trực tiếp một JAR

`java --describe-module` tìm mô-đun theo tên trong runtime image hoặc module path. Nếu muốn xem descriptor của đúng tệp JAR đang phát hành, dùng công cụ `jar`:

```bash
jar --describe-module --file mods/com.example.inventory.jar
```

Ví dụ kết quả:

```text
com.example.inventory jar:file:///.../com.example.inventory.jar!/module-info.class
exports com.example.inventory
requires java.base mandated
main-class com.example.inventory.Main
```

Đầu ra cho biết JAR chứa `module-info.class`, tên mô-đun, package export, dependency và lớp main nếu có. Cách này hữu ích khi kiểm tra artifact sau khi build hoặc trước khi phát hành.

### So sánh hai lệnh describe

| Lệnh | Tra cứu theo | Phù hợp khi |
| --- | --- | --- |
| `java --describe-module com.example.inventory` | Tên mô-đun có thể quan sát | Muốn xem mô-đun mà runtime tìm được trên module path hoặc runtime image |
| `jar --describe-module --file mods/com.example.inventory.jar` | Tệp JAR cụ thể | Muốn xác minh descriptor thực sự được đóng gói trong artifact |

## 5. Ví dụ hoàn chỉnh: build và kiểm tra một modular JAR

Ta tạo mô-đun `com.example.inventory`, export package `com.example.inventory` và có lớp main để chạy thử.

### Cấu trúc thư mục

```text
src/
└── com.example.inventory/
    ├── module-info.java
    └── com/example/inventory/
        ├── InventoryService.java
        └── Main.java
```

### `src/com.example.inventory/module-info.java`

```java
module com.example.inventory {
    exports com.example.inventory;
}
```

### `src/com.example.inventory/com/example/inventory/InventoryService.java`

```java
package com.example.inventory;

public final class InventoryService {
    private InventoryService() { }

    public static String status() {
        return "ready";
    }
}
```

### `src/com.example.inventory/com/example/inventory/Main.java`

```java
package com.example.inventory;

public class Main {
    public static void main(String[] args) {
        System.out.println("inventory status = " + InventoryService.status());
    }
}
```

### Biên dịch và đóng gói

Tạo hai thư mục output `out` và `mods`. Với Windows PowerShell:

```powershell
New-Item -ItemType Directory -Path out, mods -Force | Out-Null
```

Với Bash:

```bash
mkdir -p out mods
```

Biên dịch mô-đun:

```bash
javac --module-source-path src -d out -m com.example.inventory
```

`--module-source-path src` cho biết thư mục chứa các cây mã nguồn mô-đun; `-m` chọn mô-đun cần biên dịch. Kết quả được đặt trong `out/com.example.inventory`.

Đóng gói thành modular JAR:

```bash
jar --create --file mods/com.example.inventory.jar \
    --main-class com.example.inventory.Main \
    -C out/com.example.inventory .
```

`module-info.class` nằm ở gốc thư mục đầu vào `out/com.example.inventory`, nên được đóng gói ở gốc JAR.

### Chạy mô-đun

```bash
java --module-path mods --module com.example.inventory
```

Kết quả:

```text
inventory status = ready
```

### Liệt kê và mô tả mô-đun vừa tạo

Liệt kê mô-đun trên module path:

```bash
java --module-path mods --list-modules
```

Trong danh sách, tìm dòng có `com.example.inventory` và đường dẫn tới JAR.

Mô tả theo tên mô-đun:

```bash
java --module-path mods --describe-module com.example.inventory
```

Kết quả tiêu biểu:

```text
com.example.inventory file:///.../mods/com.example.inventory.jar
exports com.example.inventory
requires java.base mandated
```

Kiểm tra trực tiếp JAR:

```bash
jar --describe-module --file mods/com.example.inventory.jar
```

Kết quả tiêu biểu:

```text
com.example.inventory jar:file:///.../com.example.inventory.jar!/module-info.class
exports com.example.inventory
requires java.base mandated
main-class com.example.inventory.Main
```

Đường dẫn `file:///...` thay đổi theo máy. Điều quan trọng là tên mô-đun, directive và `module-info.class` được đọc đúng.

## 6. Automatic module: nhận diện JAR chưa có `module-info.class`

Một JAR chưa có module descriptor vẫn có thể được đưa lên module path như một **automatic module**. Cơ chế này giúp tích hợp thư viện JAR hiện có trong quá trình chuyển đổi sang JPMS.

Nếu JAR không có `module-info.class` và không khai báo tên mô-đun trong manifest, runtime suy ra tên từ tên tệp. Ví dụ:

```text
legacy-utils-2.1.jar
```

Có thể được suy ra thành mô-đun `legacy.utils`, phiên bản `2.1`. Nếu manifest có thuộc tính `Automatic-Module-Name`, tên được khai báo ở đó được dùng thay cho tên suy ra từ tệp.

Đặt JAR trên module path:

```text
mods/
├── com.example.inventory.jar
└── legacy-utils-2.1.jar
```

Liệt kê:

```bash
java --module-path mods --list-modules
```

Trong kết quả, automatic module được đánh dấu:

```text
legacy.utils@2.1 file:///.../mods/legacy-utils-2.1.jar automatic
```

Mô tả bằng Java launcher:

```bash
java --module-path mods --describe-module legacy.utils
```

Kết quả tiêu biểu:

```text
legacy.utils@2.1 file:///.../mods/legacy-utils-2.1.jar automatic
requires java.base mandated
contains org.example.legacy
```

Kiểm tra trực tiếp JAR:

```bash
jar --describe-module --file mods/legacy-utils-2.1.jar
```

Đầu ra bắt đầu bằng thông báo:

```text
No module descriptor found. Derived automatic module.
```

Automatic module có các quy tắc tương thích riêng, trong đó các package của nó được export ngầm và mô-đun có thể đọc các mô-đun quan sát được. Khi có thể, thư viện nên cung cấp module descriptor tường minh để khai báo rõ dependency và API được export.

## 7. Kiểm tra module graph khi chạy ứng dụng

`--list-modules` cho biết mô-đun nào có thể quan sát; `--describe-module` cho biết descriptor của một mô-đun. Nếu cần xem quá trình resolve dependency khi ứng dụng khởi chạy, dùng:

```bash
java --show-module-resolution --module-path mods --module com.example.inventory
```

Tùy chọn này in các dòng như `root`, `requires` và `binds` để cho thấy mô-đun gốc cùng những dependency được resolve hoặc liên kết trong lần chạy đó. Đầu ra có thể dài vì service binding.

Để kiểm tra tính nhất quán của cấu hình mô-đun trên module path:

```bash
java --validate-modules --module-path mods
```

Lệnh này kiểm tra cấu hình mô-đun và thoát; khi không có lỗi, thường không in thông báo. Nếu có xung đột hoặc cấu hình không hợp lệ, runtime in chẩn đoán để xử lý.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Module ... not found` | Tên mô-đun sai hoặc mô-đun không nằm trong runtime image/module path | Kiểm tra tên trong `--list-modules`, đường dẫn `--module-path` và tên suy ra của automatic module |
| JAR không xuất hiện trong `--list-modules` | Thư mục module path sai, JAR không phải mô-đun quan sát được hoặc JAR nằm trên classpath | Kiểm tra đường dẫn và thử `jar --describe-module --file ...` |
| Tên mô-đun khác tên JAR | Tên trong `module-info.class`, `Automatic-Module-Name` hoặc quy tắc suy ra tên automatic module | Dùng `jar --describe-module --file ...` |
| `No module descriptor found` | JAR không chứa `module-info.class` | Kiểm tra xem JAR được nhận diện là automatic module hay không |
| Mô-đun xuất hiện trong danh sách nhưng ứng dụng không dùng được | Có thể mô-đun chỉ observable nhưng chưa được resolve; hoặc thiếu `requires`/export cần thiết | Đọc descriptor bằng `--describe-module`, xem resolution bằng `--show-module-resolution` |
| Descriptor không như mong đợi | Đang kiểm tra nhầm JAR hoặc artifact cũ | Dùng `jar --describe-module --file` với đúng tệp vừa build |

## 9. Quy trình kiểm tra thực tế

1. Chạy `java --list-modules` để xem các mô-đun runtime cung cấp.
2. Nếu ứng dụng dùng thư viện ngoài, thêm module path và chạy `java --module-path mods --list-modules`.
3. Xác định đúng tên mô-đun từ danh sách; không suy đoán tên từ tên tệp JAR.
4. Chạy `java --module-path mods --describe-module ten.module` để kiểm tra exports, requires, opens, uses và provides.
5. Dùng `jar --describe-module --file path/to/library.jar` để xác minh descriptor trong artifact thực tế.
6. Khi cần biết dependency nào được resolve lúc khởi chạy, dùng `--show-module-resolution`.
7. Chạy `--validate-modules` nếu cần kiểm tra xung đột trong cấu hình module path.

## Ghi nhớ

- `--list-modules` liệt kê mô-đun có thể quan sát; không đồng nghĩa tất cả đã được resolve hoặc nạp.
- `--describe-module` tra cứu bằng tên mô-đun và hiển thị descriptor.
- `jar --describe-module --file` kiểm tra trực tiếp một JAR.
- Automatic module được đánh dấu `automatic`; tên có thể đến từ manifest hoặc được suy ra từ tên JAR.
- `--show-module-resolution` dùng để quan sát đồ thị được resolve khi khởi chạy; `--validate-modules` dùng để kiểm tra cấu hình.

## Tài liệu tham khảo

- [Java Launcher — JDK 24 Tool Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [The `jar` Command — JDK 24 Tool Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [Java Platform Module System API — `java.lang.module`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/package-summary.html)
# Tạo runtime image bằng `--module-path`, `--add-modules` và `--output`

Từ Java 9, công cụ `jlink` có thể liên kết các mô-đun cần thiết thành một **runtime image tùy chỉnh**. Image này chứa JVM cùng đúng tập mô-đun nền tảng và mô-đun ứng dụng đã chọn, giúp triển khai ứng dụng modular mà không phải phân phối toàn bộ JDK.

Ba tùy chọn chính trong quy trình:

- `--module-path`: chỉ nơi `jlink` tìm các mô-đun đầu vào, bao gồm mô-đun ứng dụng và các mô-đun của JDK.
- `--add-modules`: chỉ định mô-đun gốc cần đưa vào image. `jlink` resolve các dependency bắt buộc của chúng.
- `--output`: chỉ định thư mục đích để tạo runtime image.

`jlink` là công cụ của JDK, không phải lệnh chạy ứng dụng. Sau khi tạo image, ứng dụng có thể chạy bằng `java` nằm ngay trong image đó.

## 1. Runtime image là gì?

Runtime image là một bản phân phối runtime được liên kết từ các mô-đun. Nó thường chứa:

- Runtime launcher như `bin/java`.
- JVM và thư viện runtime cần thiết.
- Các mô-đun nền tảng như `java.base`, cùng các mô-đun ứng dụng được chọn.
- Metadata và tài nguyên nội bộ để runtime nạp các mô-đun.

Runtime image do `jlink` tạo ra có thể chạy ứng dụng modular mà không cần cài toàn bộ JDK trên máy triển khai. Image không phải một JDK đầy đủ: các công cụ phát triển như `javac`, `javadoc` và `jlink` không được đưa vào trừ khi có cơ chế riêng.

Runtime image gắn với nền tảng và kiến trúc mà bộ JDK đầu vào hỗ trợ. Hãy tạo image bằng JDK phù hợp với hệ điều hành và kiến trúc CPU đích.

## 2. Chuẩn bị mô-đun ứng dụng

`jlink` cần các mô-đun có descriptor tường minh. Ứng dụng trên classpath hoặc JAR automatic module không thể được liên kết trực tiếp thành runtime image; hãy đóng gói ứng dụng dưới dạng named module có `module-info.class`.

Ví dụ tạo mô-đun `com.example.greeter` sử dụng `java.logging` để ghi log.

### Cấu trúc thư mục

```text
project/
└── src/
    └── com.example.greeter/
        ├── module-info.java
        └── com/example/greeter/Main.java
```

`src/com.example.greeter/module-info.java`:

```java
module com.example.greeter {
    requires java.logging;
    exports com.example.greeter;
}
```

`src/com.example.greeter/com/example/greeter/Main.java`:

```java
package com.example.greeter;

import java.util.logging.Logger;

public class Main {
    private static final Logger LOGGER = Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        String recipient = args.length == 0 ? "Java 9" : args[0];
        LOGGER.info("Preparing greeting");
        System.out.println("Hello, " + recipient + "!");
    }
}
```

`requires java.logging` khai báo dependency trực tiếp. `java.base` được JPMS yêu cầu ngầm định, vì vậy không cần viết `requires java.base;`.

## 3. Biên dịch và đóng gói modular JAR

Chạy từ thư mục gốc `project/`. Tạo thư mục output:

```bash
mkdir -p mods app-mods
```

Biên dịch mô-đun:

```bash
javac --module-source-path src -d mods -m com.example.greeter
```

Sau khi biên dịch, mô-đun đã giải nén nằm trong `mods/com.example.greeter`. Đóng gói thành modular JAR và ghi nhận lớp main:

```bash
jar --create \
    --file app-mods/com.example.greeter.jar \
    --main-class com.example.greeter.Main \
    -C mods/com.example.greeter .
```

JAR này có `module-info.class` ở gốc archive nên là explicit named module. Có thể kiểm tra descriptor trước khi liên kết:

```bash
jar --describe-module --file app-mods/com.example.greeter.jar
```

Kết quả tiêu biểu:

```text
com.example.greeter
exports com.example.greeter
requires java.base mandated
requires java.logging
main-class com.example.greeter.Main
```

## 4. `--module-path` — chỉ định nơi tìm mô-đun

Cú pháp:

```bash
jlink --module-path <module-path> ...
```

Module path là danh sách các thư mục hoặc vị trí chứa mô-đun. Trong ví dụ, cần hai nguồn:

- Thư mục `jmods` của JDK, chứa các mô-đun nền tảng như `java.base` và `java.logging`.
- Thư mục `app-mods`, chứa modular JAR `com.example.greeter.jar`.

Trên Linux/macOS, dấu phân cách các phần tử module path là dấu hai chấm `:`:

```bash
jlink --module-path "$JAVA_HOME/jmods:app-mods" ...
```

Trên Windows, dấu phân cách là dấu chấm phẩy `;`:

```powershell
$modulePath = "$env:JAVA_HOME\jmods;app-mods"
jlink --module-path $modulePath ...
```

Nếu không truyền `--module-path`, `jlink` mặc định dùng thư mục `jmods` của JDK đang chạy khi thư mục đó tồn tại. Khi cần thêm mô-đun ứng dụng, phải bổ sung vị trí chứa chúng vào module path.

Module path không phải classpath. `jlink` cần descriptor mô-đun để resolve dependency và liên kết image; JAR thường trên classpath và automatic module không thay thế được explicit module.

## 5. `--add-modules` — chọn mô-đun gốc

Cú pháp:

```bash
jlink --add-modules module.name[,another.module...] ...
```

Giá trị là **tên mô-đun**, không phải tên tệp JAR hay package. Các mô-đun được liệt kê trở thành root modules của image.

Ví dụ:

```bash
--add-modules com.example.greeter
```

Vì `com.example.greeter` yêu cầu `java.logging`, và mọi named module đều yêu cầu `java.base`, `jlink` resolve thêm các dependency bắt buộc. Không cần liệt kê lại toàn bộ dependency closure trong `--add-modules`.

Có thể chỉ định nhiều root module bằng dấu phẩy:

```bash
--add-modules com.example.greeter,java.sql
```

Chỉ thêm `java.sql` nếu ứng dụng thực sự cần module đó. Thêm root không cần thiết làm runtime image lớn hơn.

`ALL-MODULE-PATH` là lựa chọn đặc biệt để thêm tất cả mô-đun quan sát được trên module path. Nó tiện trong một số quy trình plugin hoặc đóng gói, nhưng thường tạo image lớn hơn việc chọn root modules cụ thể:

```bash
--add-modules ALL-MODULE-PATH
```

### Dependency tĩnh và service provider

Dependency được khai báo bằng `requires` sẽ được resolve theo đồ thị mô-đun. Nếu ứng dụng dùng `ServiceLoader` và cần liên kết các provider quan sát được trên module path, có thể thêm `--bind-services`:

```bash
jlink --module-path "$JAVA_HOME/jmods:app-mods" \
    --add-modules com.example.greeter \
    --bind-services \
    --output runtime
```

`--bind-services` yêu cầu công cụ liên kết các mô-đun provider cho những service mà các root modules sử dụng, cùng dependency của provider. Chỉ dùng khi kiến trúc ứng dụng cần service binding; nếu provider là dependency bắt buộc và đã được chỉ định tường minh, có thể đưa provider vào `--add-modules`.

## 6. `--output` — tạo runtime image

Cú pháp:

```bash
jlink --output <directory>
```

Đường dẫn là thư mục đích cho runtime image. Hãy chọn một thư mục mới chưa tồn tại để tránh ghi đè nhầm một image hoặc dữ liệu triển khai cũ.

Lệnh đầy đủ trên Linux/macOS:

```bash
jlink --module-path "$JAVA_HOME/jmods:app-mods" \
    --add-modules com.example.greeter \
    --output runtime
```

Lệnh tương đương trên Windows PowerShell:

```powershell
$modulePath = "$env:JAVA_HOME\jmods;app-mods"
jlink --module-path $modulePath `
    --add-modules com.example.greeter `
    --output runtime
```

Khi thành công, `runtime/` chứa runtime image có thể phân phối. Công cụ `jlink` không sửa JDK đầu vào hoặc JAR ứng dụng; nó tạo image ở thư mục đích.

## 7. Chạy ứng dụng bằng runtime image

Không cần dùng `java` từ JDK phát triển nữa. Gọi launcher trong image:

Trên Linux/macOS:

```bash
runtime/bin/java --module com.example.greeter/com.example.greeter.Main Ada
```

Trên Windows:

```powershell
.\runtime\bin\java.exe --module com.example.greeter/com.example.greeter.Main Ada
```

Kết quả trên standard output:

```text
Hello, Ada!
```

Ứng dụng cũng ghi log `INFO: Preparing greeting` ra standard error; thời gian và định dạng dòng log phụ thuộc môi trường.

### Kiểm tra những mô-đun có trong image

Dùng chính runtime vừa tạo:

```bash
runtime/bin/java --list-modules
runtime/bin/java --describe-module com.example.greeter
```

Với ví dụ này, danh sách mô-đun gồm:

```text
com.example.greeter
java.base@24.0.2
java.logging@24.0.2
```

Phiên bản hiển thị theo JDK được dùng để tạo image. Kết quả cho thấy image có mô-đun ứng dụng cùng hai mô-đun nền tảng mà dependency closure yêu cầu.

## 8. Tạo launcher riêng cho ứng dụng

`jlink` có tùy chọn `--launcher` để tạo lệnh khởi chạy tiện dụng trong image:

```bash
jlink --module-path "$JAVA_HOME/jmods:app-mods" \
    --add-modules com.example.greeter \
    --launcher greeter=com.example.greeter/com.example.greeter.Main \
    --output runtime
```

Cú pháp là `--launcher <command>=<module>[/<main-class>]`. Sau khi tạo image:

- Linux/macOS: chạy `runtime/bin/greeter Ada`.
- Windows: chạy `runtime\bin\greeter.bat Ada`.

Launcher gọi đúng module và main class đã cấu hình, giúp script triển khai không phải lặp lại tham số `--module`.

## 9. Tùy chỉnh kích thước image

`jlink` có các plugin để điều chỉnh nội dung và kích thước runtime image. Một số tùy chọn phổ biến:

| Tùy chọn | Tác dụng |
| --- | --- |
| `--strip-debug` | Loại bỏ thông tin debug khỏi image |
| `--no-header-files` | Không đưa header files vào image |
| `--no-man-pages` | Không đưa man pages vào image |
| `--compress zip-6` | Nén tài nguyên bằng mức nén được chỉ định |
| `--bind-services` | Liên kết provider modules cho service được sử dụng |

Ví dụ image tối ưu thêm:

```bash
jlink --module-path "$JAVA_HOME/jmods:app-mods" \
    --add-modules com.example.greeter \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --compress zip-6 \
    --output runtime
```

Các plugin có thể thay đổi theo phiên bản JDK. Kiểm tra danh sách thực tế trước khi dùng:

```bash
jlink --list-plugins
```

Không nên loại bỏ resource, locale hoặc thành phần runtime chỉ để giảm dung lượng nếu ứng dụng hoặc thư viện cần chúng.

## 10. Lỗi thường gặp

| Lỗi hoặc biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Module ... not found` | Tên module sai hoặc thư mục chứa module không có trong module path | Kiểm tra `--module-path`, tên trong `module-info.java` và nội dung JAR |
| `Module ... not found` với `java.base` | Thiếu JDK `jmods` hoặc đang dùng sai JDK đầu vào | Thêm `$JAVA_HOME/jmods` vào module path và dùng `jlink` từ JDK tương ứng |
| `automatic module ... not supported` | Đầu vào là automatic module hoặc JAR không có descriptor tường minh | Chuyển thư viện sang explicit named module trước khi liên kết |
| `Module ... does not read ...` hoặc dependency không resolve | Descriptor thiếu `requires` hoặc module phụ thuộc không có trên module path | Bổ sung dependency đúng trong descriptor và đưa module vào module path |
| Image thiếu một module được nạp động | Module đó không nằm trong dependency closure và chưa được chọn làm root | Thêm tên module vào `--add-modules`; với service provider, xem xét `--bind-services` |
| Thư mục output đã tồn tại | Đích tạo image không phải thư mục mới phù hợp | Chọn một đường dẫn output mới; chỉ xóa image cũ khi đã xác định rõ đó là artifact có thể thay thế |
| Image chạy trên máy build nhưng không chạy trên máy đích | Image không tương thích OS/CPU hoặc thiếu quyền thực thi | Tạo image cho nền tảng đích và kiểm tra quyền thực thi của launcher |
| Ứng dụng thiếu resource sau khi liên kết | Build chưa đóng gói resource hoặc plugin đã loại bỏ resource cần thiết | Kiểm tra nội dung modular JAR và cấu hình plugin |

## 11. Quy trình triển khai đề xuất

1. Xác định các named module mà ứng dụng trực tiếp cần và khai báo `requires` đúng trong `module-info.java`.
2. Biên dịch và đóng gói ứng dụng thành modular JAR có `module-info.class`.
3. Kiểm tra descriptor của JAR bằng `jar --describe-module`.
4. Đặt JDK `jmods` và các modular JAR ứng dụng trên `--module-path`.
5. Chọn root modules tối thiểu bằng `--add-modules`; để JPMS resolve các dependency bắt buộc.
6. Thêm `--bind-services` nếu cần provider modules được tìm qua service binding.
7. Dùng `--output` để tạo image tại một thư mục mới.
8. Chạy `bin/java` trong image, kiểm tra `--list-modules` và chạy các bài kiểm thử trên môi trường tương đương máy đích.
9. Đóng gói thư mục runtime image cùng cấu hình triển khai của ứng dụng.

## Ghi nhớ

- `--module-path` chỉ nơi tìm JDK modules và application modules.
- `--add-modules` chọn root modules; các dependency `requires` được resolve tự động.
- `--output` xác định nơi tạo runtime image; nên dùng đường dẫn đích mới.
- `jlink` cần explicit named modules; classpath JAR và automatic modules không phải đầu vào modular phù hợp.
- Dùng `--bind-services` khi cần đưa provider modules của `ServiceLoader` vào image.
- Chạy ứng dụng bằng `java` nằm trong image; image chỉ chứa runtime và tập module đã liên kết, không phải toàn bộ JDK.

## Tài liệu tham khảo

- [The `jlink` Command — JDK 24 Tool Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html)
- [The `jar` Command — JDK 24 Tool Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261)
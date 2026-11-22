# Liệt kê phụ thuộc mô-đun của ứng dụng bằng `jdeps`

Khi một ứng dụng Java được chia thành nhiều mô-đun, cần biết nó đọc những mô-đun nào để biên dịch, chạy và đóng gói đúng. Công cụ `jdeps` đi kèm JDK phân tích bytecode và module descriptor để liệt kê các phụ thuộc. Nó hỗ trợ kiểm tra module path, tìm dependency còn thiếu, xem đồ thị phụ thuộc đã rút gọn và chuẩn bị danh sách mô-đun cho `jlink`.

`jdeps` thực hiện phân tích tĩnh: nó đọc class file và metadata mô-đun, không chạy ứng dụng. Vì vậy kết quả rất hữu ích cho kiểm tra build và đóng gói, nhưng vẫn cần kiểm thử runtime cho các đường nạp lớp động, reflection hoặc plugin.

## 1. `jdeps` đọc những gì?

`jdeps` có thể phân tích một file `.class`, thư mục chứa class đã biên dịch hoặc JAR. Với ứng dụng modular, nó đọc cả `module-info.class` để biết các chỉ thị `requires`, đồng thời phân tích tham chiếu kiểu trong bytecode để tìm các module/package mà mã sử dụng.

Các loại quan hệ thường gặp:

- **Phụ thuộc khai báo:** module descriptor có `requires other.module;`.
- **Phụ thuộc từ bytecode:** class tham chiếu tới kiểu thuộc một module khác, ví dụ `java.sql.DriverManager`.
- **Phụ thuộc bắc cầu:** một module có thể đọc module khác thông qua `requires transitive` của dependency.
- **Phụ thuộc nền tảng:** mọi named module thông thường đều đọc `java.base`; descriptor hiển thị nó với modifier `mandated` dù không cần viết `requires java.base`.

Phân biệt module dependency với package/class dependency. `jdeps --list-deps` hiển thị tên module; các chế độ `-verbose:package` và `-verbose:class` cho biết chi tiết package hoặc class tạo ra quan hệ đó.

## 2. Ví dụ ứng dụng modular

Ví dụ tạo ứng dụng `com.example.billing` dùng ba module của JDK: `java.sql`, `java.net.http` và `java.logging`. Mục đích là minh họa cách phân tích; chương trình chỉ tham chiếu API để in tên module, không kết nối database hoặc gọi mạng.

Cấu trúc nguồn:

```text
src/
└── com.example.billing/
    ├── module-info.java
    └── com/example/billing/
        └── Main.java
```

**`src/com.example.billing/module-info.java`**

```java
module com.example.billing {
    requires java.sql;
    requires java.net.http;
    requires java.logging;
}
```

**`src/com.example.billing/com/example/billing/Main.java`**

```java
package com.example.billing;

import java.net.http.HttpClient;
import java.sql.DriverManager;
import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        System.out.println(DriverManager.class.getModule().getName());
        System.out.println(HttpClient.class.getModule().getName());
        System.out.println(Logger.class.getModule().getName());
    }
}
```

Biên dịch từ thư mục chứa `src`:

```powershell
javac --release 17 --module-source-path src -d out -m com.example.billing
```

Chạy ứng dụng từ thư mục chứa `out`:

```powershell
java --module-path out -m com.example.billing/com.example.billing.Main
```

STDOUT:

```text
java.sql
java.net.http
java.logging
```

Đóng gói module thành JAR để các lệnh phân tích dùng một artifact rõ ràng:

```powershell
New-Item -ItemType Directory -Force build | Out-Null
jar --create --file build/com.example.billing.jar -C out/com.example.billing .
```

## 3. Liệt kê các module phụ thuộc

Đặt JAR của ứng dụng và các modular library cần thiết trên module path, sau đó chỉ định module gốc cần phân tích:

```powershell
jdeps --module-path build --module com.example.billing --list-deps
```

Có thể viết ngắn `-m` thay cho `--module`:

```powershell
jdeps --module-path build -m com.example.billing --list-deps
```

Với ví dụ trên, kết quả trên JDK 24 là:

```text
   java.base
   java.logging
   java.net.http
   java.sql
```

Ý nghĩa:

- `java.base` là module nền tảng bắt buộc, được đưa vào ngầm định.
- `java.net.http` cung cấp `HttpClient`.
- `java.sql` cung cấp `DriverManager`.
- `java.logging` cung cấp `Logger`.

`--list-deps` cũng phân tích các thư viện trên class path và module path khi chúng được tham chiếu. Nếu phân tích một JAR không có module descriptor, vẫn có thể truyền đường dẫn JAR trực tiếp cho `jdeps`; tên module được suy ra hoặc lấy từ `Automatic-Module-Name` khi phù hợp.

## 4. Phân biệt danh sách đầy đủ và đồ thị đã rút gọn

`--list-reduced-deps` bỏ các cạnh readability đã được hàm ý bởi quan hệ `requires transitive` trong module graph:

```powershell
jdeps --module-path build --module com.example.billing --list-reduced-deps
```

Kết quả:

```text
   java.base
   java.net.http
   java.sql
```

Trong JDK hiện hành, `java.sql` khai báo `requires transitive java.logging`. Vì vậy ứng dụng đọc được `java.logging` thông qua `java.sql`; đồ thị rút gọn không cần liệt kê cạnh đã được hàm ý này. `jdeps --list-deps` vẫn liệt kê `java.logging` trong danh sách đầy đủ.

Điều đó không có nghĩa ứng dụng không dùng `Logger`. Nó cũng không tự động khuyến nghị xóa `requires java.logging` khỏi module descriptor. Nếu mã nguồn trực tiếp dùng API của một module, hãy giữ dependency trực tiếp rõ ràng trong hợp đồng của ứng dụng; đồ thị rút gọn chỉ trình bày các cạnh cần thiết sau khi tính các quan hệ bắc cầu.

## 5. In danh sách module dạng CSV cho `jlink`

`--print-module-deps` tạo danh sách module phụ thuộc cách nhau bằng dấu phẩy. Kết quả này thuận tiện để đưa vào cấu hình tạo runtime image:

```powershell
jdeps --module-path build --module com.example.billing --print-module-deps
```

STDOUT:

```text
java.base,java.net.http,java.sql
```

Với ứng dụng modular, hãy thêm module gốc của ứng dụng vào `--add-modules`; danh sách in ra là các dependency, không phải tên module ứng dụng. Ví dụ PowerShell:

```powershell
$deps = jdeps --module-path build --module com.example.billing --print-module-deps
$javaHome = Split-Path (Split-Path (Get-Command java).Source -Parent) -Parent
jlink --module-path "$javaHome\jmods;build" --add-modules "com.example.billing,$deps" --output billing-runtime
```

Chạy ứng dụng bằng runtime image vừa tạo:

```powershell
.\billing-runtime\bin\java.exe -m com.example.billing/com.example.billing.Main
```

`jlink` giải quyết các dependency bắc cầu của module gốc khi tạo image. Danh sách từ `jdeps` giúp kiểm tra và xác định các module nền tảng cần thiết; hãy chạy thử ứng dụng bằng image đã tạo trước khi phát hành.

## 6. Xem tóm tắt và kiểm tra module descriptor

Để xem quan hệ phụ thuộc theo từng module, dùng `-s` hoặc `-summary`:

```powershell
jdeps -s --module-path build --module com.example.billing
```

Kết quả:

```text
com.example.billing -> java.base
com.example.billing -> java.logging
com.example.billing -> java.net.http
com.example.billing -> java.sql
```

`--check` kiểm tra module descriptor, hiển thị descriptor hiện tại, descriptor được đề xuất và đồ thị bắc cầu đã rút gọn:

```powershell
jdeps --module-path build --check com.example.billing
```

Phần `Module descriptor` cho biết các dòng `requires` đang có. Phần `Suggested module descriptor` trình bày khai báo được đề xuất từ phân tích. Phần `Transitive reduced graph` cho biết các quan hệ đọc còn cần thiết sau khi loại cạnh được hàm ý. Lệnh này cũng có thể phát hiện qualified export không được sử dụng.

Không nên chỉ dựa vào đồ thị rút gọn để xóa dependency trực tiếp. Hãy cân nhắc API mà mã nguồn sử dụng, ý định thiết kế và kết quả biên dịch sau mỗi thay đổi descriptor.

## 7. Tìm dependency còn thiếu

`--missing-deps` tìm các tham chiếu phụ thuộc mà `jdeps` không giải quyết được. Cung cấp đầy đủ module path hoặc class path để tránh kết quả thiếu do cấu hình phân tích chưa hoàn chỉnh:

```powershell
jdeps --module-path build --missing-deps build/com.example.billing.jar
```

Nếu không có dòng nào được in ra, `jdeps` không phát hiện dependency bị thiếu trong phạm vi phân tích đó. Đây không phải bằng chứng rằng mọi nhánh runtime đều hoạt động; hãy kết hợp với biên dịch, test và kiểm tra cấu hình nạp class động.

Đừng dùng `--ignore-missing-deps` để che một dependency chưa được giải quyết trong bước nghiệm thu. Chỉ bỏ qua khi đã xác định rõ đó là tham chiếu tùy chọn và có cách kiểm tra riêng.

## 8. Các tùy chọn hữu ích khi phân tích ứng dụng lớn

| Tùy chọn | Công dụng |
| --- | --- |
| `--module-path` | Chỉ định nơi tìm named module và modular JAR. Trên Windows, nhiều thư mục được phân cách bằng dấu `;`. |
| `--class-path` | Chỉ định thư viện hoặc class không được xử lý như named module. Có thể dùng wildcard như `lib/*`. |
| `--add-modules` | Bổ sung module vào tập root khi phân tích module graph. |
| `--no-recursive` | Chỉ phân tích dependency trực tiếp, không đi tiếp qua các dependency khác. |
| `-R` hoặc `--recursive` | Duyệt đệ quy các runtime dependency; tùy chọn này cũng bỏ lọc archive mặc định. |
| `-verbose:package` | Hiển thị quan hệ phụ thuộc ở mức package. |
| `-verbose:class` | Hiển thị quan hệ phụ thuộc ở mức class. |
| `--api-only` | Chỉ xét dependency xuất hiện trong public/protected API của public class. |
| `--jdk-internals` | Tìm tham chiếu tới API nội bộ của JDK cần thay thế bằng API được hỗ trợ. |
| `--multi-release 17` | Phân tích phần class phù hợp của multi-release JAR tại phiên bản chỉ định. |
| `--dot-output deps-dot` | Xuất các file DOT để trực quan hóa đồ thị dependency. |

Ví dụ với một ứng dụng không modular hóa nhưng có thư viện bên ngoài:

```powershell
jdeps --class-path "lib/*" --list-deps build/legacy-app.jar
```

Ví dụ chỉ xem dependency tới module `java.sql`:

```powershell
jdeps --module-path build --module com.example.billing --require java.sql
```

Ví dụ kiểm tra API nội bộ của JDK:

```powershell
jdeps --jdk-internals build/com.example.billing.jar
```

Khi dùng `--multi-release`, hãy chọn đúng phiên bản Java mà ứng dụng sẽ chạy. Với multi-release JAR, bytecode khác nhau theo phiên bản có thể tạo ra tập dependency khác nhau.

## 9. Đọc kết quả đúng cách và các giới hạn

`jdeps` là công cụ phân tích tĩnh nên cần hiểu phạm vi kết quả:

1. **Không phải mọi dependency đều được thực thi.** Một class có thể tham chiếu module mà nhánh code hiện tại chưa chạy; `jdeps` vẫn có thể liệt kê dependency đó.
2. **Reflection có thể che giấu tham chiếu.** Tên class được tạo từ chuỗi, cấu hình plugin hoặc class được nạp động không nhất thiết xuất hiện như tham chiếu class trực tiếp trong bytecode.
3. **Service và provider cần được kiểm tra cả descriptor.** Xem `uses` ở consumer, `provides ... with ...` ở provider và bảo đảm provider nằm trong module path/layer khi chạy.
4. **Classpath và module path khác nhau.** JAR trên classpath thuộc unnamed module; cùng JAR trên module path có thể được xử lý như automatic module. Phân tích phải dùng đúng cấu hình triển khai.
5. **Danh sách module không thay thế kiểm thử.** `jdeps` không kiểm tra kết nối database, quyền truy cập, endpoint mạng, cấu hình môi trường hay kết quả nghiệp vụ.

Khi kết quả có module không mong đợi, hãy xem `-verbose:package` hoặc `-verbose:class` để truy ngược package/class tạo dependency. Sau đó xác định dependency là bắt buộc, bắc cầu, tùy chọn hay chỉ phát sinh từ thư viện phụ thuộc.

## 10. Quy trình kiểm tra trước khi phát hành

1. Biên dịch ứng dụng và đóng gói đúng artifact sẽ phát hành.
2. Cung cấp đầy đủ module path và class path giống cấu hình triển khai.
3. Chạy `jdeps --list-deps` để xem tập module đầy đủ.
4. Dùng `--list-reduced-deps` và `--print-module-deps` để hiểu đồ thị bắc cầu và chuẩn bị runtime image.
5. Chạy `--check` để xem descriptor và các quan hệ đọc.
6. Chạy `--missing-deps` và xử lý mọi dependency chưa giải quyết.
7. Chạy `--jdk-internals` nếu cần bảo đảm ứng dụng không phụ thuộc API nội bộ.
8. Biên dịch, test và chạy ứng dụng trong runtime image hoặc môi trường triển khai cuối cùng.

`jdeps` giúp trả lời ứng dụng tham chiếu tới những module nào, dependency nào được truyền qua quan hệ bắc cầu và module nền tảng nào cần cho runtime image. Kết hợp kết quả này với module descriptor, cấu hình triển khai và test runtime sẽ giúp kiểm soát dependency rõ ràng trước khi phát hành.
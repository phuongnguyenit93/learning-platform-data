# Tạo JMOD bằng công cụ jmod

JMOD (Java Module) là định dạng archive dùng để đóng gói một module Java cùng các thành phần có thể cần trong quá trình liên kết và tạo runtime image. Công cụ dòng lệnh **`jmod`** thuộc JDK cho phép tạo, liệt kê, mô tả và giải nén tệp JMOD.

JMOD thường được dùng cùng **`jlink`** để tạo runtime image tùy chỉnh. JMOD không phải định dạng thay thế trực tiếp cho JAR: JAR thường được dùng khi biên dịch, chạy hoặc phân phối ứng dụng, còn JMOD được thiết kế chủ yếu cho giai đoạn liên kết (link time).

## 1. JMOD là gì?

Một tệp JMOD có phần mở rộng `.jmod` và có thể chứa nhiều nhóm nội dung:

- **classes:** class file, module descriptor và tài nguyên của module.
- **libs:** thư viện native.
- **bin/cmds:** chương trình hoặc lệnh native đi kèm module.
- **conf:** tệp cấu hình.
- **include/header files:** header dùng khi tích hợp native.
- **legal:** thông tin giấy phép và thông báo pháp lý.

JMOD hữu ích khi một module cần được đóng gói cùng các thành phần ngoài Java bytecode, chẳng hạn thư viện native hoặc tệp cấu hình.

Một JMOD thông thường có thể chứa các lớp Java và `module-info.class`. Với module Java tự tạo, cần biên dịch module trước khi đóng gói.

## 2. Phân biệt JMOD và JAR

| Tiêu chí | JAR | JMOD |
| --- | --- | --- |
| Phần mở rộng | `.jar` | `.jmod` |
| Nội dung | Class file, tài nguyên, manifest và metadata | Class file/module descriptor cùng các section như native libraries, config, headers và legal notices |
| Biên dịch và chạy | Có thể dùng trên classpath hoặc module path theo cấu trúc JAR | Không dùng trực tiếp làm dependency compile-time hoặc runtime thông thường |
| Liên kết bằng jlink | Modular JAR có thể được dùng làm module đầu vào | Là định dạng đầu vào phù hợp cho quá trình link |
| Mục đích phổ biến | Phân phối thư viện và ứng dụng Java | Đóng gói module cho JDK/runtime image |

Một điểm cần nhớ: JMOD được thiết kế để dùng ở thời điểm liên kết. Không truyền tệp `.jmod` cho `java -cp` hoặc `javac -cp` như thể đó là một JAR thông thường. Khi cần tạo runtime image từ module, hãy dùng `jlink`.

## 3. Kiểm tra công cụ jmod

`jmod` được cung cấp trong JDK. Mở terminal và chạy:

```bash
jmod --version
jmod --help
```

Nếu hệ thống không nhận diện lệnh:

- Kiểm tra máy đã cài JDK đầy đủ.
- Kiểm tra thư mục `bin` của JDK có trong `PATH`.
- Kiểm tra `JAVA_HOME` trỏ đến thư mục gốc của JDK.
- Mở terminal mới sau khi cập nhật biến môi trường.

Có thể gọi trực tiếp công cụ bằng đường dẫn trong `JAVA_HOME/bin` nếu chưa muốn thay đổi `PATH`.

## 4. Cú pháp cơ bản của jmod

Các thao tác chính:

```text
jmod create [options] jmod-file
jmod list jmod-file
jmod describe [options] jmod-file
jmod extract [--dir dir] jmod-file
```

| Lệnh | Công dụng |
| --- | --- |
| `jmod create` | Tạo tệp JMOD từ class file và các section đầu vào |
| `jmod list` | Liệt kê các mục bên trong JMOD |
| `jmod describe` | Hiển thị mô tả module và module descriptor |
| `jmod extract` | Giải nén nội dung JMOD ra thư mục |
| `jmod hash` | Tính và ghi hash cho các module phụ thuộc theo cấu hình |

Tùy chọn cụ thể có thể thay đổi theo phiên bản JDK. Dùng `jmod --help` của chính JDK đang sử dụng để kiểm tra cú pháp được hỗ trợ.

## 5. Chuẩn bị một module Java

Ví dụ sau tạo module `com.example.hello`, biên dịch module thành class file rồi đóng gói thành JMOD.

Cấu trúc mã nguồn:

```text
project/
  src/
    com.example.hello/
      module-info.java
      com/
        example/
          hello/
            Main.java
```

Tạo tệp **`src/com.example.hello/module-info.java`**:

```java
module com.example.hello {
    exports com.example.hello;
}
```

Module descriptor khai báo tên module và package được export cho module khác.

Tạo tệp **`src/com.example.hello/com/example/hello/Main.java`**:

```java
package com.example.hello;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JMOD module");
    }
}
```

Lớp `Main` là điểm bắt đầu của ví dụ. Package `com.example.hello` được export trong `module-info.java`.

## 6. Biên dịch module trước khi tạo JMOD

Tại thư mục gốc `project`, tạo thư mục đầu ra và biên dịch module.

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force mods | Out-Null
javac -d mods --module-source-path src -m com.example.hello
```

**macOS/Linux:**

```bash
mkdir -p mods
javac -d mods --module-source-path src -m com.example.hello
```

Sau khi biên dịch, cấu trúc đầu ra có dạng:

```text
mods/
  com.example.hello/
    module-info.class
    com/
      example/
        hello/
          Main.class
```

Thư mục `mods/com.example.hello` là thư mục gốc của module đã biên dịch. Nó chứa `module-info.class` và các class file theo cấu trúc package.

Có thể kiểm tra module đã biên dịch bằng:

```bash
java --module-path mods --list-modules
```

Hoặc chạy module trực tiếp trước khi đóng gói:

```bash
java --module-path mods -m com.example.hello/com.example.hello.Main
```

Kết quả:

```text
Hello from JMOD module
```

Bước chạy thử này xác nhận module descriptor, tên module và lớp chính hoạt động trên module path.

## 7. Tạo JMOD bằng jmod create

Sau khi có class file, tạo JMOD:

```bash
jmod create --class-path mods/com.example.hello --module-version 1.0.0 --main-class com.example.hello.Main com.example.hello.jmod
```

Ý nghĩa các tùy chọn:

- `create`: tạo archive JMOD mới.
- `--class-path mods/com.example.hello`: lấy class file và tài nguyên từ thư mục module đã biên dịch.
- `--module-version 1.0.0`: gắn phiên bản cho module.
- `--main-class com.example.hello.Main`: khai báo lớp chính của module.
- `com.example.hello.jmod`: tên tệp JMOD đầu ra.

Lệnh này đóng gói module đã biên dịch; nó không biên dịch mã nguồn Java. Nếu sửa mã nguồn, hãy biên dịch lại trước khi tạo JMOD mới.

Một số tùy chọn khác của `jmod create`:

| Tùy chọn | Nội dung được thêm vào JMOD |
| --- | --- |
| `--class-path` | Class file và tài nguyên của module |
| `--cmds` | Các lệnh/chương trình native |
| `--config` | Tệp cấu hình |
| `--header-files` | Header native |
| `--libs` | Thư viện native |
| `--legal-notices` | Tệp thông báo pháp lý |
| `--module-version` | Phiên bản module |
| `--main-class` | Lớp chính của module |
| `--target-platform` | Nền tảng đích cho nội dung module khi cần |

Các section như native library, command và header chỉ cần thiết khi module thực sự có các thành phần đó. Với module Java thuần, `--class-path` thường là đủ.

## 8. Liệt kê nội dung JMOD bằng jmod list

Sau khi tạo archive, chạy:

```bash
jmod list com.example.hello.jmod
```

Kết quả sẽ có các mục tương tự:

```text
classes/module-info.class
classes/com/example/hello/Main.class
```

Tùy phiên bản JDK, cách hiển thị và các mục bổ sung có thể khác. Cần xác nhận JMOD có module descriptor và các class file mong muốn.

Nếu không thấy `module-info.class`, hãy kiểm tra lại thư mục truyền cho `--class-path` và bước biên dịch module. Một JMOD dành cho named module cần có module descriptor hợp lệ.

## 9. Mô tả module bằng jmod describe

Chạy:

```bash
jmod describe com.example.hello.jmod
```

Với module ví dụ, kết quả có dạng:

```text
com.example.hello@1.0.0
exports com.example.hello
requires java.base mandated
main-class com.example.hello.Main
```

Thông tin có thể gồm:

- Tên module.
- Phiên bản module nếu được khai báo.
- Các package được export.
- Các module được yêu cầu.
- Main class nếu đã khai báo.
- Các thuộc tính module khác.

`jmod describe` hữu ích để xác minh metadata mà không cần tự giải nén hoặc đọc trực tiếp binary class file.

## 10. Giải nén JMOD bằng jmod extract

Để kiểm tra nội dung chi tiết, giải nén archive:

```bash
jmod extract --dir extracted com.example.hello.jmod
```

Sau khi giải nén, các section được đưa vào thư mục tương ứng. Với ví dụ Java thuần, cấu trúc có thể là:

```text
extracted/
  classes/
    module-info.class
    com/
      example/
        hello/
          Main.class
```

Có thể dùng `javap` để xem module descriptor hoặc class file đã giải nén:

```bash
javap -p -v extracted/classes/com/example/hello/Main.class
```

Khi cần kiểm tra module descriptor:

```bash
javap -v extracted/classes/module-info.class
```

Giải nén chỉ phục vụ kiểm tra hoặc xử lý nội dung archive. Để tạo runtime image, hãy dùng JMOD gốc làm đầu vào cho `jlink`.

## 11. Dùng JMOD với jlink để tạo runtime image

JMOD thường phát huy tác dụng khi liên kết các module thành runtime image. `jlink` đọc module từ module path, chọn các module cần thiết và tạo một runtime image tùy chỉnh.

Để link module ví dụ, module path cần có:

- Thư mục JMOD chuẩn của JDK hiện tại, thường là `$JAVA_HOME/jmods`.
- Thư mục chứa JMOD tùy chỉnh, trong ví dụ là thư mục hiện tại `.`.

**macOS/Linux:**

```bash
jlink --module-path "$JAVA_HOME/jmods:." --add-modules com.example.hello --output image
```

**Windows PowerShell:**

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;." --add-modules com.example.hello --output image
```

Giải thích:

- `--module-path`: nơi `jlink` tìm các module JDK và module tùy chỉnh.
- `--add-modules com.example.hello`: module gốc cần đưa vào runtime image; các dependency cần thiết được phân giải theo đồ thị module.
- `--output image`: thư mục runtime image đầu ra.

Thư mục `image` cần chưa tồn tại hoặc đáp ứng yêu cầu của `jlink` về thư mục đầu ra. Nên tạo runtime image mới ở một đường dẫn riêng cho mỗi lần build.

Chạy ứng dụng từ runtime image:

**macOS/Linux:**

```bash
./image/bin/java -m com.example.hello/com.example.hello.Main
```

**Windows PowerShell:**

```powershell
.\image\bin\java.exe -m com.example.hello/com.example.hello.Main
```

Kết quả:

```text
Hello from JMOD module
```

Runtime image chỉ chứa các module được chọn và những dependency cần thiết. Điều này giúp giảm kích thước môi trường chạy so với việc phân phối toàn bộ JDK, tùy vào module và thành phần thực tế của ứng dụng.

## 12. JMOD có thể chứa native library và cấu hình

Một ưu điểm của JMOD là khả năng đóng gói nội dung ngoài class file. Ví dụ một module cần thư viện native có thể thêm thư mục thư viện bằng `--libs`:

```bash
jmod create --class-path mods/com.example.hello --libs native-libs --module-version 1.0.0 com.example.hello.jmod
```

Các tùy chọn bổ sung có thể đưa lệnh, cấu hình, header và legal notices vào archive:

```bash
jmod create --class-path mods/com.example.hello --cmds commands --config config --header-files include --libs native-libs --legal-notices legal com.example.hello.jmod
```

Các đường dẫn trong ví dụ phải tồn tại và chứa đúng loại nội dung tương ứng. Không cần tạo các thư mục này nếu module không có thành phần native hoặc metadata bổ sung.

Khi đóng gói native library:

- Chọn đúng kiến trúc và hệ điều hành mục tiêu.
- Đảm bảo tên và vị trí thư viện phù hợp với cách module sử dụng chúng.
- Kiểm tra phụ thuộc native của thư viện.
- Dùng toolchain và JDK tương thích với nền tảng đích.
- Kiểm thử runtime image trên môi trường triển khai tương ứng.

JMOD có thể mang nội dung đặc thù nền tảng, do đó không nên mặc định một JMOD chứa native library có thể dùng nguyên trạng trên mọi hệ điều hành.

## 13. Các lưu ý quan trọng khi tạo JMOD

- **Biên dịch trước khi đóng gói:** `jmod create` nhận class file/tài nguyên, không nhận mã nguồn để tự biên dịch.
- **Module descriptor:** module tự tạo cần có `module-info.class` hợp lệ.
- **Tên module:** phải nhất quán giữa `module-info.java`, lệnh `javac`, `--main-class` và `jlink --add-modules`.
- **Phiên bản JDK:** dùng phiên bản JDK phù hợp cho `javac`, `jmod` và `jlink`; tránh trộn các định dạng module từ toolchain không tương thích.
- **JMOD không phải runtime dependency thông thường:** không đưa JMOD vào classpath của `java` hoặc `javac` như JAR.
- **JMOD và JAR có mục đích khác nhau:** nếu chỉ cần phân phối thư viện Java hoặc ứng dụng thông thường, JAR thường phù hợp hơn.
- **JMOD có thể chứa thành phần native:** cần xác định nền tảng đích và kiểm thử trên hệ điều hành/kiến trúc tương ứng.
- **Runtime image:** sau khi dùng `jlink`, kiểm thử image đầu ra thay vì chỉ kiểm tra việc tạo JMOD thành công.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `jmod` không được nhận diện | Chưa cài JDK hoặc `PATH` chưa có thư mục `bin` | Kiểm tra `JAVA_HOME` và `PATH` |
| `jmod create` không tìm thấy class file | `--class-path` trỏ sai thư mục hoặc chưa biên dịch module | Kiểm tra thư mục đầu ra và biên dịch lại bằng `javac` |
| Module descriptor không hợp lệ | Thiếu hoặc sai `module-info.class` | Kiểm tra `module-info.java`, tên module và cấu trúc output |
| `jmod describe` báo lỗi | Tệp không phải JMOD hợp lệ hoặc bị hỏng | Tạo lại archive và kiểm tra bằng `jmod list` |
| `jlink` không tìm thấy module | Module path thiếu JMOD hoặc tên module sai | Bổ sung thư mục JDK `jmods` và thư mục chứa JMOD tùy chỉnh |
| Runtime image không khởi chạy được | Module chưa được thêm hoặc main class không đúng | Kiểm tra `--add-modules`, `--main-class` và lệnh `java -m` |
| JMOD chạy được trên máy này nhưng lỗi ở máy khác | Có native library hoặc nội dung đặc thù nền tảng | Tạo và kiểm thử artifact theo đúng OS/kiến trúc đích |
| Dùng JMOD trong `java -cp` nhưng không tìm được lớp | JMOD không phải JAR runtime thông thường | Dùng JMOD với `jlink` hoặc phân phối modular JAR phù hợp |

## 15. Quy trình tạo JMOD đề xuất

Một quy trình làm việc có thể lặp lại:

1. Tạo module với `module-info.java` và các package cần thiết.
2. Biên dịch module bằng `javac` vào một thư mục đầu ra riêng.
3. Chạy thử module trên module path để xác nhận module descriptor và lớp chính.
4. Dùng `jmod create` để đóng gói class file và các section cần thiết.
5. Dùng `jmod list` xác nhận nội dung archive.
6. Dùng `jmod describe` kiểm tra tên module, version, exports, requires và main class.
7. Dùng `jmod extract` khi cần kiểm tra chi tiết các section.
8. Dùng `jlink` để tạo runtime image từ JMOD và các module JDK cần thiết.
9. Chạy thử ứng dụng bằng Java trong runtime image.
10. Lưu lại phiên bản JDK, lệnh build và nền tảng mục tiêu để có thể tái tạo artifact.

## 16. Ghi nhớ

- JMOD là archive dành cho module Java và quá trình liên kết runtime.
- `jmod create` tạo JMOD từ class file và các section đầu vào.
- `jmod list`, `describe`, `extract` lần lượt dùng để liệt kê, mô tả và giải nén archive.
- Module tự tạo cần được biên dịch trước và có module descriptor hợp lệ.
- JMOD có thể chứa class file, native library, command, config, header và legal notices.
- JMOD không dùng trực tiếp như JAR trên classpath compile/runtime thông thường.
- `jlink` dùng JMOD và các module cần thiết để tạo runtime image tùy chỉnh.

Khi nắm được quy trình `javac` → `jmod create` → kiểm tra archive → `jlink`, bạn có thể đóng gói module Java và tạo môi trường runtime gọn hơn, có kiểm soát cho ứng dụng triển khai.

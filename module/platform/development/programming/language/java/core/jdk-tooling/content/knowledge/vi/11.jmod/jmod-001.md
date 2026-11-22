# Lệnh jmod trong JDK

`jmod` là công cụ dòng lệnh đi kèm JDK để tạo, xem, trích xuất và quản lý các tệp JMOD. JMOD là định dạng lưu trữ dành cho Java module, có thể chứa class file, module descriptor và các thành phần bổ sung như thư viện native, lệnh native, cấu hình, header, tài liệu và legal notices.

JMOD thường xuất hiện trong quy trình tạo runtime image bằng `jlink` hoặc khi một module cần đóng gói các thành phần native. Với phần lớn ứng dụng Java thông thường, modular JAR vẫn là định dạng phù hợp hơn để chạy, phân phối và phát hành qua repository. JMOD dùng cho giai đoạn biên dịch hoặc liên kết runtime image; nó không phải định dạng có thể chạy trực tiếp trên JVM.

Bài học sử dụng JDK 21 làm mốc. Các tùy chọn cụ thể có thể khác giữa các phiên bản JDK, vì vậy hãy kiểm tra trợ giúp của JDK đang cài trên máy.

## 1. JMOD là gì?

Một JMOD là archive chứa nội dung của một Java module. Ngoài các class file và `module-info.class`, nó có thể chứa các phần nội dung bổ sung:

- **Classes:** class file của module và các resource đi kèm.
- **Native libraries:** thư viện native được module sử dụng.
- **Native commands:** executable hoặc lệnh native liên quan.
- **Configuration:** tệp cấu hình có thể được chỉnh sửa.
- **Header files:** header, thường phục vụ tích hợp native/JNI.
- **Man pages:** tài liệu hướng dẫn lệnh.
- **Legal notices:** thông tin pháp lý và giấy phép.

JMOD cho phép gom những thành phần này thành một archive để công cụ build hoặc linker sử dụng.

### 1.1. JMOD và modular JAR

Hai định dạng đều có thể đóng gói một module, nhưng mục tiêu sử dụng khác nhau:

| Đặc điểm | Modular JAR | JMOD |
|---|---|---|
| Chứa class file và module descriptor | Có | Có |
| Chứa resource Java | Có | Có |
| Đóng gói native libraries/configuration theo các section của JMOD | Không theo cấu trúc JMOD | Có |
| Chạy trực tiếp bằng Java launcher trên module path | Có | Không |
| Dùng trong compile/link time | Có | Có |
| Phù hợp với phân phối ứng dụng thông thường | Thường phù hợp | Thường không phải lựa chọn đầu tiên |
| Dùng làm đầu vào cho jlink | Có thể | Là trường hợp sử dụng chính |

Không chạy một tệp JMOD bằng `java -jar`. JMOD không phải executable JAR. Nếu cần chạy ứng dụng, hãy dùng modular JAR hoặc tạo runtime image bằng `jlink` rồi chạy launcher được tạo trong image đó.

## 2. Cú pháp và các chế độ của jmod

Cú pháp tổng quát:

~~~text
jmod (create|extract|list|describe|hash) [options] jmod-file
~~~

Năm chế độ chính:

| Chế độ | Công dụng |
|---|---|
| `create` | Tạo JMOD archive mới từ class file và các nội dung bổ sung |
| `extract` | Giải nén nội dung của một JMOD |
| `list` | Liệt kê các entry bên trong JMOD |
| `describe` | Hiển thị thông tin module được lưu trong JMOD |
| `hash` | Tính và ghi hash của các module liên quan theo module graph |

Kiểm tra phiên bản và trợ giúp:

~~~bash
jmod --version
jmod --help
jmod --help-extra
~~~

`--help-extra` hiển thị các tùy chọn bổ sung như `--do-not-resolve-by-default` và `--warn-if-resolved`. Không nên đoán tùy chọn theo một bản JDK khác; hãy xem trợ giúp từ executable `jmod` thực tế mà build đang dùng.

## 3. Chuẩn bị một module mẫu

Tạo một module nhỏ để thực hành các lệnh. Cấu trúc source:

~~~text
project/
└── src/
    └── com.example.greetings/
        ├── module-info.java
        └── com/
            └── greetings/
                └── Main.java
~~~

Tệp `src/com.example.greetings/module-info.java`:

~~~java
module com.example.greetings {
    exports com.greetings;
}
~~~

Tệp `src/com.example.greetings/com/greetings/Main.java`:

~~~java
package com.greetings;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from JMOD");
    }
}
~~~

Module có tên `com.example.greetings` và export package `com.greetings`. Phương thức `main` là điểm vào của chương trình.

Biên dịch module bằng JDK:

~~~bash
javac --module-source-path src -d mods -m com.example.greetings
~~~

Sau khi biên dịch, thư mục `mods` có cấu trúc tương tự:

~~~text
mods/
└── com.example.greetings/
    ├── module-info.class
    └── com/
        └── greetings/
            └── Main.class
~~~

Thử chạy module từ các class file đã biên dịch:

~~~bash
java --module-path mods -m com.example.greetings/com.greetings.Main
~~~

Kết quả:

~~~text
Hello from JMOD
~~~

Đây là module đã biên dịch. Ta sẽ đóng gói thư mục module đó thành JMOD ở bước tiếp theo.

## 4. Tạo JMOD bằng create

Chế độ `create` tạo archive từ nội dung đã biên dịch. Tạo thư mục đích rồi chạy:

~~~bash
mkdir -p jmods
jmod create --class-path mods/com.example.greetings \
  --main-class com.greetings.Main \
  --module-version 1.0 \
  jmods/com.example.greetings.jmod
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force jmods | Out-Null
jmod create --class-path mods/com.example.greetings --main-class com.greetings.Main --module-version 1.0 jmods/com.example.greetings.jmod
~~~

Ý nghĩa các phần:

- `create` yêu cầu tạo archive mới.
- `--class-path` chỉ định JAR hoặc thư mục chứa class file được sao chép vào JMOD.
- `--main-class` ghi tên lớp chính vào module descriptor.
- `--module-version` ghi phiên bản module vào descriptor.
- Đối số cuối là đường dẫn JMOD cần tạo.

Thư mục class path phải chứa module descriptor `module-info.class` và các class file tương ứng. Với module mẫu, thư mục đó là `mods/com.example.greetings`.

Nếu module có thư viện native, có thể bổ sung:

~~~bash
jmod create --class-path mods/com.example.greetings \
  --libs native-libs \
  --cmds native-commands \
  --config config \
  --header-files include \
  --legal-notices legal \
  --man-pages man \
  jmods/com.example.greetings.jmod
~~~

Các đường dẫn bổ sung là tùy chọn. Chỉ đưa vào những thư mục thực sự có trong dự án. JMOD sẽ sao chép nội dung của các đường dẫn được chỉ định, bao gồm thư mục con, trừ những tệp khớp mẫu loại trừ.

## 5. Liệt kê nội dung bằng list

Dùng `list` để xem các entry có trong JMOD:

~~~bash
jmod list jmods/com.example.greetings.jmod
~~~

Kết quả liệt kê tên các entry trong archive. Với module mẫu, có thể thấy các entry liên quan đến module descriptor và class file, chẳng hạn:

~~~text
classes/module-info.class
classes/com/greetings/Main.class
~~~

Tên entry cụ thể phụ thuộc nội dung đã đóng gói. Nếu archive có thư viện native, cấu hình hoặc header, danh sách cũng sẽ có entry tương ứng.

`list` chỉ cho biết nội dung nào được đóng gói. Nó không kiểm tra ứng dụng có chạy đúng hay thư viện native có tương thích với hệ điều hành hiện tại hay không.

## 6. Xem thông tin module bằng describe

Dùng `describe` để đọc thông tin module từ JMOD:

~~~bash
jmod describe jmods/com.example.greetings.jmod
~~~

Đầu ra mô tả module thường cho biết:

- Tên module và phiên bản nếu có.
- Các package được export.
- Các module được yêu cầu qua `requires`.
- Lớp chính nếu metadata có khai báo.
- Các thông tin module khác như hashes nếu được ghi.

Với module mẫu, các thông tin quan trọng gồm tên `com.example.greetings`, package `com.greetings` được export và module `java.base` được yêu cầu ngầm theo quy tắc Java module system.

Dùng `describe` khi muốn kiểm tra metadata của archive mà không cần giải nén hoặc xem từng class file.

## 7. Giải nén bằng extract

Chế độ `extract` giải nén toàn bộ entry của JMOD. Dùng `--dir` để chỉ định thư mục đích:

~~~bash
jmod extract --dir extracted jmods/com.example.greetings.jmod
~~~

Trên Windows PowerShell:

~~~powershell
jmod extract --dir extracted jmods/com.example.greetings.jmod
~~~

Sau khi chạy, thư mục `extracted` chứa các thành phần đã giải nén theo cấu trúc JMOD. Ví dụ có thể thấy thư mục `classes` cùng các thư mục bổ sung nếu archive chứa native library, config hoặc header.

Giải nén hữu ích khi:

- Kiểm tra class file và module descriptor thực tế.
- Xem thư viện native hoặc tệp cấu hình được đóng gói.
- So sánh nội dung giữa hai bản JMOD.
- Điều tra lỗi do thiếu hoặc đóng gói sai tài nguyên.

Chỉ giải nén vào thư mục đích phù hợp. Tránh giải nén đè lên source tree hoặc thư mục chứa dữ liệu dự án khác.

## 8. Dùng JMOD với jlink

Một trong những mục đích quan trọng của JMOD là làm đầu vào để tạo runtime image tùy chỉnh bằng `jlink`.

Với JDK đang dùng, các module nền tảng nằm trong thư mục `jmods` bên dưới `JAVA_HOME`. Có thể kết hợp JMOD ứng dụng với các module của JDK:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:jmods" \
  --add-modules com.example.greetings \
  --launcher greetings=com.example.greetings/com.greetings.Main \
  --output greetings-image
~~~

Trên Windows PowerShell, dấu phân cách module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;jmods" --add-modules com.example.greetings --launcher greetings=com.example.greetings/com.greetings.Main --output greetings-image
~~~

Lệnh này:

- Tìm module nền tảng trong `JAVA_HOME/jmods`.
- Tìm module ứng dụng trong thư mục `jmods`.
- Thêm module `com.example.greetings` và các phụ thuộc cần thiết vào runtime image.
- Tạo launcher tên `greetings` để gọi lớp chính.
- Ghi runtime image vào `greetings-image`.

Chạy launcher trên macOS/Linux:

~~~bash
./greetings-image/bin/greetings
~~~

Trên Windows, chạy tệp launcher trong thư mục `greetings-image/bin`, thường là `greetings.bat`.

Kết quả:

~~~text
Hello from JMOD
~~~

Runtime image chứa các module cần thiết và launcher đã cấu hình. JMOD vẫn là đầu vào của bước link; chương trình được chạy từ runtime image được tạo, không chạy trực tiếp từ tệp JMOD.

## 9. Chế độ hash và module hashing

Java module system hỗ trợ qualified exports: một module có thể export package chỉ cho một hoặc một số module được nêu tên. Module hashing giúp gắn kết các module trong quan hệ này bằng cách ghi hash của module phụ thuộc vào descriptor của module được yêu cầu.

Chế độ `hash` phân tích module graph, xác định các module ở đầu nhánh phụ thuộc (leaf modules) và ghi hash của chúng vào các module cần ràng buộc. Khi runtime hoặc linker giải quyết module, hash được kiểm tra; nếu nội dung module không còn khớp với giá trị đã ghi, quá trình giải quyết có thể báo lỗi.

### 9.1. Xem trước bằng --dry-run

Ví dụ chạy từ thư mục dự án có thư mục `jmods`:

~~~bash
jmod hash --dry-run --module-path jmods --hash-modules '.*'
~~~

`--module-path` chỉ định nơi tìm các JMOD hoặc modular JAR tham gia module graph. `--hash-modules` nhận regular expression dùng để chọn module. `--dry-run` cho xem những hash sẽ được ghi mà chưa sửa archive.

### 9.2. Ghi hash

Sau khi kiểm tra kết quả dry run, có thể bỏ `--dry-run`:

~~~bash
jmod hash --module-path jmods --hash-modules '.*'
~~~

Lệnh ghi hash vào module archive phù hợp trên module path. Đây là thao tác thay đổi nội dung archive, nên cần chạy trong quy trình build có kiểm soát và chỉ sau khi module graph đã được xác định.

### 9.3. Khi nào cần hashing?

Module hashing không phải bước bắt buộc cho mọi dự án. Nó hữu ích khi dùng qualified exports và cần ràng buộc module được phép phụ thuộc vào package được export. Nếu module phụ thuộc bị thay thế bằng một nội dung khác, hash mismatch giúp phát hiện sự thay đổi so với module đã được gắn kết.

Không nên dùng hashing như cơ chế thay thế chữ ký số, kiểm soát nguồn phát hành hoặc kiểm tra bảo mật toàn bộ dependency. Nó phục vụ tính nhất quán giữa các module trong module graph.

## 10. Các tùy chọn jmod thường dùng

Các tùy chọn được sử dụng cùng chế độ tương ứng:

| Tùy chọn | Công dụng |
|---|---|
| `--class-path path` | Lấy JAR hoặc thư mục chứa class để đưa vào JMOD |
| `--libs path` | Thêm thư viện native |
| `--cmds path` | Thêm lệnh native |
| `--config path` | Thêm tệp cấu hình có thể chỉnh sửa |
| `--header-files path` | Thêm header files |
| `--legal-notices path` | Thêm legal notices |
| `--man-pages path` | Thêm man pages |
| `--main-class class` | Ghi lớp chính vào module descriptor |
| `--module-version version` | Ghi phiên bản module |
| `--target-platform platform` | Ghi nền tảng đích của JMOD |
| `--compress zip-N` | Chọn mức nén khi tạo archive |
| `--date timestamp` | Đặt timestamp entry trong archive |
| `--exclude patterns` | Loại trừ các tệp khớp glob/regex |
| `--module-path path` | Chỉ định module path; cần khi dùng `--hash-modules` |
| `--hash-modules regex` | Chọn module để tính và ghi hash |
| `--dry-run` | Chỉ xem trước thao tác hash |
| `--dir path` | Chỉ định thư mục giải nén |
| `@filename` | Đọc tùy chọn từ options file |

### 10.1. Mức nén

`--compress` nhận dạng `zip-0` đến `zip-9`:

- `zip-0` không nén.
- `zip-9` nén mạnh nhất.
- Mặc định trong JDK 21 là `zip-6`.

Nén mạnh hơn có thể giảm kích thước archive nhưng tăng thời gian tạo/đọc. Chọn mức nén dựa trên thời gian build, dung lượng phân phối và nhu cầu triển khai.

### 10.2. Timestamp và build có thể tái lập

`--date` cho phép chỉ định timestamp entry theo định dạng ISO-8601 extended offset date-time. Việc cố định timestamp giúp giảm khác biệt không cần thiết giữa các lần build khi nội dung đầu vào không đổi.

Ví dụ:

~~~bash
jmod create --class-path mods/com.example.greetings \
  --date 2025-01-01T00:00:00Z \
  jmods/com.example.greetings.jmod
~~~

Để có build có thể tái lập, ngoài timestamp cần kiểm soát cả nội dung đầu vào, phiên bản JDK, thứ tự và cấu hình build, cùng các metadata khác.

### 10.3. Loại trừ tệp

`--exclude` nhận danh sách mẫu phân tách bằng dấu phẩy. Mỗi mẫu có thể là glob, `glob:` hoặc `regex:`. Dùng nó để loại các tệp không nên đưa vào archive, ví dụ tệp tạm hoặc metadata build không cần thiết.

Hãy kiểm tra danh sách bằng `jmod list` sau khi tạo để xác nhận các nội dung cần thiết vẫn được đóng gói.

## 11. Options file

Có thể đặt các tùy chọn `jmod` vào một tệp văn bản rồi truyền với tiền tố @:

Tệp `jmod-create.args`:

~~~text
create
--class-path
mods/com.example.greetings
--main-class
com.greetings.Main
--module-version
1.0
jmods/com.example.greetings.jmod
~~~

Chạy:

~~~bash
jmod @jmod-create.args
~~~

Options file hữu ích khi lệnh dài hoặc cần lưu cấu hình build có thể xem xét trong repository. Tệp này chứa các tùy chọn và giá trị như khi nhập trên command prompt. Không giả định rằng biến môi trường trong đường dẫn sẽ được mở rộng bên trong options file; tài liệu JDK quy định không dùng biến môi trường cho path name trong tệp này.

## 12. Quy trình thực hành đầy đủ

Với module mẫu ở phần trên, quy trình tạo và kiểm tra JMOD:

1. **Biên dịch module:** dùng `javac --module-source-path src -d mods -m com.example.greetings`.
2. **Tạo thư mục JMOD:** tạo `jmods` để lưu archive.
3. **Đóng gói:** dùng `jmod create --class-path mods/com.example.greetings` cùng main class/version nếu cần.
4. **Xem metadata:** chạy `jmod describe` để xác nhận tên module, package export, requires và main class.
5. **Kiểm tra entry:** chạy `jmod list` để xác nhận class file và tài nguyên có trong archive.
6. **Giải nén khi cần:** dùng `jmod extract --dir extracted` để kiểm tra nội dung.
7. **Liên kết runtime:** dùng `jlink` với module path chứa JDK JMODs và JMOD ứng dụng.
8. **Chạy image:** gọi launcher trong thư mục `bin` của runtime image.
9. **Hash nếu cần:** chỉ dùng `jmod hash` khi module design cần ràng buộc qualified exports.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jmod` không được nhận diện | Chưa cài JDK hoặc `PATH` không trỏ tới JDK `bin` | Kiểm tra `JAVA_HOME`, `PATH` và `jmod --version` |
| Không tạo được JMOD | Thư mục class path không tồn tại hoặc thiếu module descriptor/class file cần thiết | Kiểm tra output của `javac` và đường dẫn `--class-path` |
| `jmod describe` báo lỗi archive | Đường dẫn sai hoặc tệp không phải JMOD hợp lệ | Kiểm tra tên tệp và tạo archive lại từ module output hợp lệ |
| `jmod list` thiếu class/resource | Nội dung chưa được biên dịch hoặc chưa nằm trong các đường dẫn đưa vào archive | Kiểm tra source/build output và các tùy chọn đường dẫn |
| `jlink` không tìm thấy module | Module path không chứa JMOD hoặc phụ thuộc cần thiết | Kiểm tra `--module-path` và `requires` của module |
| `jlink` báo module không phù hợp nền tảng | JMOD chứa native code hoặc target-platform khác với máy đích | Build JMOD phù hợp hệ điều hành/kiến trúc đích |
| Ứng dụng không chạy trực tiếp từ JMOD | JMOD không phải định dạng runtime executable | Dùng modular JAR hoặc tạo runtime image bằng `jlink` |
| Hash mismatch khi link | Module phụ thuộc đã thay đổi so với hash ghi trong module được yêu cầu | Kiểm tra module graph và build lại hash từ bộ module nhất quán |

## 14. Lưu ý khi làm việc với JMOD

- JMOD là định dạng cho compile/link time; không dùng nó thay modular JAR để chạy trực tiếp.
- Với ứng dụng Java thông thường, ưu tiên modular JAR nếu không cần các section native/configuration của JMOD.
- Khi có native library hoặc native command, JMOD và target platform cần phù hợp hệ điều hành, kiến trúc và môi trường triển khai.
- Kiểm tra nội dung archive bằng `jmod list` và metadata bằng `jmod describe` sau khi tạo.
- Dùng `jlink` để tạo runtime image có thể chạy; không nhầm bước đóng gói JMOD với bước tạo runtime.
- `jmod hash` chỉ nên được dùng khi module design cần ràng buộc module thông qua qualified exports.
- Không dựa vào output của một phiên bản JDK khác mà bỏ qua `jmod --help` của toolchain đang build.

## 15. Ghi nhớ

`jmod` cung cấp năm thao tác chính: `create`, `extract`, `list`, `describe` và `hash`. `create` đóng gói module đã biên dịch cùng thành phần native hoặc metadata bổ sung; `list` và `describe` giúp kiểm tra archive; `extract` giải nén để điều tra; `hash` ghi hash ràng buộc module khi thiết kế qualified exports yêu cầu.

JMOD phát huy tác dụng trong quy trình build module và tạo runtime image bằng `jlink`. Với phần lớn ứng dụng cần chạy hoặc phân phối thông thường, modular JAR vẫn là lựa chọn phù hợp. Hãy xác định rõ mục tiêu compile, link hay runtime trước khi chọn định dạng đóng gói.

Tài liệu tham khảo: [The jmod Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jmod.html); [The jlink Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html).
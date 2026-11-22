# Hash trong JMOD và cơ chế ModuleHashes của Java

## 1. JMOD và module hash là gì?

JMOD là định dạng archive của JDK dùng để đóng gói một module cùng các thành phần phục vụ build và liên kết runtime, chẳng hạn class file, native library, header, command, man page và tệp cấu hình. Công cụ `jmod` có các chế độ `create`, `extract`, `list`, `describe` và `hash`.

Module hash là giá trị băm được ghi vào module descriptor để liên kết một module đã đóng gói với những module khác phụ thuộc vào nó. Khi một module được phát hành cùng các module phụ thuộc, metadata hash giúp công cụ module nhận biết tập module phụ thuộc đã được dùng để tạo liên kết đó.

Điểm cần phân biệt:

- **JMOD archive** là gói module ở giai đoạn build/link; nó có thể chứa nhiều loại nội dung ngoài class file.
- **Module hash** là metadata về nội dung của module phụ thuộc, được ghi trong descriptor của module đang được gắn kết.
- **File checksum** như SHA-256 của toàn bộ tệp JMOD là giá trị kiểm tra artifact ở cấp file.
- **Chữ ký số** xác thực nguồn phát hành và tính toàn vẹn theo khóa/chứng thư. Module hash không thay thế chữ ký số.

`jmod hash` không đơn giản tính một checksum cho toàn bộ tệp JMOD. Nó tính hash của những module được chọn theo biểu thức chính quy và có quan hệ phụ thuộc trực tiếp hoặc gián tiếp vào module đang được đóng gói.

## 2. Vì sao cần ghi hash của module phụ thuộc?

Giả sử có hai module:

- `com.example.base` cung cấp API dùng chung.
- `com.example.app` khai báo `requires com.example.base` và gọi API của module base.

Khi đóng gói module base, có thể ghi hash của module app vào module descriptor của base. Quan hệ này tạo một liên kết giữa bản base đã đóng gói và những bản module app được lựa chọn.

Nếu một module phụ thuộc được thay thế bằng nội dung khác sau khi hash được tạo, metadata hash không còn tương ứng với nội dung phụ thuộc mới. Công cụ module có thể phát hiện sự không nhất quán khi phân giải hoặc liên kết module graph. Cơ chế này hữu ích khi xây dựng runtime image và quản lý một tập module đã được kiểm thử cùng nhau.

Một số trường hợp sử dụng:

- Gắn module nền tảng với các module mở rộng phụ thuộc vào nó.
- Đóng gói một nhóm module có quan hệ phụ thuộc chặt chẽ thành một runtime image.
- Giúp phát hiện module phụ thuộc đã bị thay đổi so với bản được ghi nhận lúc tạo liên kết.
- Hỗ trợ quy trình build có kiểm soát phiên bản và nguồn gốc module.

Không cần tạo module hash cho mọi ứng dụng Java. Nó có ý nghĩa nhất khi dự án dùng JPMS, JMOD và quy trình liên kết runtime có chủ đích. Ứng dụng Java đơn giản chạy trên classpath thường không cần thao tác này.

## 3. Hash được lưu ở đâu trong JMOD?

Khi ghi hash, `jmod` cập nhật module descriptor `module-info.class` bên trong JMOD. Trong class file, dữ liệu này được biểu diễn bằng attribute `ModuleHashes`.

Attribute `ModuleHashes` chứa:

- Tên thuật toán hash.
- Danh sách module phụ thuộc được chọn.
- Giá trị hash tương ứng với từng module.

Trong JMOD đã tạo, class file thường nằm dưới entry `classes/module-info.class`. Có thể giải nén JMOD rồi dùng `javap -v` để xem attribute này.

Ví dụ dạng thông tin mà `javap` có thể hiển thị:

~~~text
ModuleHashes:
  algorithm: SHA-256
  hashes: 1
  module: com.example.app
  hash: [giá trị băm dạng byte]
~~~

Tên thuật toán và digest cụ thể do công cụ/JDK tạo ra. Trong ví dụ kiểm chứng với JDK hiện tại, `jmod` hiển thị thuật toán `SHA-256`. Không nên hard-code digest trong script vì chỉ cần nội dung module thay đổi, giá trị hash sẽ thay đổi.

## 4. Cú pháp `jmod hash`

Cú pháp:

~~~bash
jmod hash --module-path <module-path> --hash-modules <regex-pattern> [--dry-run] <module.jmod>
~~~

Ý nghĩa các tham số:

| Tùy chọn | Ý nghĩa |
|---|---|
| `hash` | Chọn chế độ ghi module hash vào JMOD đích. |
| `--module-path` hoặc `-p` | Đường dẫn chứa các module cần phân tích để tìm module phụ thuộc. |
| `--hash-modules` | Biểu thức chính quy chọn tên module phụ thuộc cần hash. |
| `--dry-run` | Chỉ tính và hiển thị kết quả dự kiến, không ghi hash vào JMOD. |
| `<module.jmod>` | JMOD đích sẽ nhận metadata `ModuleHashes`. |

`--hash-modules` nhận **regular expression**, không phải glob pattern. Ví dụ:

- `com\.example\.app` chọn đúng tên module `com.example.app`.
- `com\.example\..*` chọn các module thuộc nhóm tên bắt đầu bằng `com.example.`.
- `.*` chọn mọi module phù hợp trong module path, vì vậy cần dùng cẩn thận.

Công cụ chỉ ghi hash cho các module được pattern chọn và phụ thuộc trực tiếp hoặc gián tiếp vào module của JMOD đích. Một module không phụ thuộc vào JMOD đích sẽ không được đưa vào tập hash chỉ vì tên nó khớp regex.

## 5. Ví dụ: hai module có quan hệ phụ thuộc

Tạo cấu trúc thư mục:

~~~text
jmod-hash-demo/
├── src/
│   ├── com.example.base/
│   │   ├── module-info.java
│   │   └── com/example/base/Base.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
├── mods/
└── jmods/
~~~

Module base, tệp `src/com.example.base/module-info.java`:

~~~java
module com.example.base {
    exports com.example.base;
}
~~~

Tệp `src/com.example.base/com/example/base/Base.java`:

~~~java
package com.example.base;

public class Base {
    public static String value() {
        return "base";
    }
}
~~~

Module app, tệp `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.base;
}
~~~

Tệp `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.base.Base;

public class Main {
    public static void main(String[] args) {
        System.out.println(Base.value());
    }
}
~~~

Quan hệ module được khai báo bằng `requires` và `exports`: app đọc module base; base export package mà app sử dụng.

## 6. Biên dịch và tạo JMOD

Từ thư mục gốc dự án, biên dịch hai module bằng JDK 17:

~~~bash
mkdir -p mods jmods

javac --release 17 --module-source-path src -d mods --module com.example.base,com.example.app
~~~

Sau khi biên dịch, cấu trúc output có dạng:

~~~text
mods/
├── com.example.base/
│   ├── module-info.class
│   └── com/example/base/Base.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Tạo JMOD cho module base:

~~~bash
jmod create --class-path mods/com.example.base --module-version 1.0 jmods/com.example.base.jmod
~~~

`--class-path` ở đây chỉ thư mục chứa các class file và `module-info.class` của module được đóng gói. `--module-version 1.0` ghi phiên bản module vào descriptor.

Để `jmod hash` có thể tìm module app trong module path, đóng gói module app thành modular JAR:

~~~bash
jar --create --file jmods/com.example.app.jar -C mods/com.example.app .
~~~

Thư mục `jmods` hiện chứa JMOD đích `com.example.base.jmod` và modular JAR phụ thuộc `com.example.app.jar`.

## 7. Xem trước hash bằng `--dry-run`

Trước khi thay đổi JMOD, chạy chế độ dry run:

~~~bash
jmod hash --dry-run --module-path jmods --hash-modules 'com\.example\.app' jmods/com.example.base.jmod
~~~

Công cụ sẽ:

1. Đọc module base từ JMOD đích.
2. Phân giải các module trong module path.
3. Tìm module app khớp regex và có quan hệ phụ thuộc vào base.
4. Tính digest của module app.
5. In kết quả dự kiến mà không sửa JMOD.

Output có dạng:

~~~text
Dry run:
com.example.base
  hashes com.example.app SHA-256
~~~

Trong output thực tế, sau tên thuật toán còn có chuỗi digest dạng hexadecimal. Giá trị này phụ thuộc vào nội dung module và build cụ thể.

Dùng `--dry-run` để xác nhận regex và module path chọn đúng các module trước khi ghi metadata vào artifact phát hành.

## 8. Ghi hash vào JMOD

Sau khi kết quả dry run đúng, chạy lại lệnh và bỏ `--dry-run`:

~~~bash
jmod hash --module-path jmods --hash-modules 'com\.example\.app' jmods/com.example.base.jmod
~~~

Kết quả thành công có dạng:

~~~text
Hashes are recorded in module com.example.base
~~~

Lệnh cập nhật JMOD đích và ghi hash của module app vào metadata module base. Hãy chạy thao tác này sau khi các module phụ thuộc đã được build xong và trước khi JMOD được dùng để tạo runtime image hoặc phát hành.

Nếu thay đổi nội dung app sau khi tạo hash, hãy chạy lại quy trình hash để metadata phản ánh đúng bản module mới. Tránh cập nhật JMOD sau khi hash mà không tái tạo hoặc tính lại hash liên quan.

## 9. Kiểm tra hash bằng `jmod describe`

Dùng `jmod describe` để xem thông tin module:

~~~bash
jmod describe jmods/com.example.base.jmod
~~~

Kết quả có thể bao gồm:

~~~text
com.example.base@1.0
exports com.example.base
requires java.base mandated
hashes com.example.app SHA-256 ...
~~~

Dòng `hashes` cho biết module base đang ghi nhận hash của module app và thuật toán được dùng. Dấu `...` trong ví dụ chỉ phần digest dài được rút gọn khi trình bày; output thực tế hiển thị giá trị đầy đủ.

`jmod describe` là cách kiểm tra nhanh, dễ đọc và phù hợp cho script QA sau khi tạo JMOD.

## 10. Kiểm tra attribute `ModuleHashes` bằng `javap`

Để xem cấu trúc class file bên trong JMOD, giải nén archive:

~~~bash
jmod extract --dir extracted jmods/com.example.base.jmod
~~~

JMOD được giải nén thành các thư mục thành phần, trong đó module descriptor nằm ở:

~~~text
extracted/
└── classes/
    └── module-info.class
~~~

Dùng `javap`:

~~~bash
javap -v extracted/classes/module-info.class
~~~

Trong output, tìm attribute `ModuleHashes`. Nó cho biết thuật toán hash, số module được ghi nhận, tên module phụ thuộc và digest tương ứng.

Có thể lọc trên Linux/macOS:

~~~bash
javap -v extracted/classes/module-info.class | grep -A8 ModuleHashes
~~~

Trên Windows PowerShell:

~~~powershell
javap -v extracted/classes/module-info.class | Select-String -Pattern "ModuleHashes" -Context 0,8
~~~

Dùng `jmod describe` khi chỉ cần kiểm tra tổng quan. Dùng `javap -v` khi cần kiểm tra sâu cấu trúc attribute hoặc điều tra lỗi ở mức class file.

## 11. `jmod hash` khác checksum và chữ ký số thế nào?

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| Module hash trong JMOD | Các module được chọn có quan hệ phụ thuộc với module đích. | Gắn module đã đóng gói với các module phụ thuộc cụ thể. |
| Checksum SHA-256 của file JMOD | Toàn bộ byte của một file JMOD. | Kiểm tra file có thay đổi so với checksum đã lưu hay không. |
| Chữ ký số | Artifact được ký và chứng thư/khóa ký. | Xác thực nguồn ký và kiểm tra tính toàn vẹn theo chữ ký. |

Module hash không phải cơ chế xác thực người phát hành. Nếu kẻ tấn công có thể thay cả module phụ thuộc và JMOD chứa digest, họ có thể tạo lại metadata tương ứng. Vì vậy, vẫn cần bảo vệ artifact repository, checksum phát hành và chữ ký số nếu yêu cầu bảo mật đòi hỏi.

Module hash cũng không thay thế versioning. Hãy tiếp tục quản lý phiên bản module, dependency lock và quy trình phát hành rõ ràng.

## 12. JMOD được dùng với `jlink` như thế nào?

JMOD thường được dùng ở giai đoạn tạo runtime image. Công cụ `jlink` đọc các module trên module path, giải quyết quan hệ phụ thuộc và tạo runtime chỉ chứa những module cần thiết.

Quy trình khái quát:

~~~text
Source modules
     |
     | javac
     v
Compiled modules
     |
     | jar / jmod create
     v
Modular JAR + JMOD
     |
     | jmod hash
     v
JMOD có ModuleHashes
     |
     | jlink
     v
Custom runtime image
~~~

`jmod` archive không phải executable JAR và thông thường không được truyền trực tiếp cho `java -cp` như một thư viện. JMOD là định dạng phục vụ các công cụ module ở giai đoạn liên kết, đặc biệt là `jlink`. Khi chạy ứng dụng phát hành, dùng runtime image do `jlink` tạo hoặc dùng modular JAR trên module path theo cấu trúc phân phối phù hợp.

Khi tạo runtime image, module path có thể chứa JMOD của ứng dụng/module mở rộng, modular JAR và thư mục JMOD của JDK. Cần giữ đúng tập module và phiên bản đã dùng trong quy trình hash.

## 13. Các tùy chọn `jmod` liên quan

| Tùy chọn | Công dụng |
|---|---|
| `create` | Tạo JMOD mới. |
| `hash` | Tính và ghi hash của các module phụ thuộc được chọn vào JMOD đích. |
| `--hash-modules regex` | Chọn module phụ thuộc bằng biểu thức chính quy. |
| `--module-path path` hoặc `-p path` | Chỉ định nơi tìm các module được phân tích để tính hash. |
| `--dry-run` | Tính và hiển thị kết quả hash mà không ghi. |
| `describe` | Hiển thị module descriptor, version, requires, exports và hash đã ghi. |
| `list` | Liệt kê entry bên trong JMOD. |
| `extract --dir path` | Giải nén nội dung JMOD để kiểm tra. |
| `--module-version version` | Ghi phiên bản module khi tạo JMOD. |
| `--compress zip-0 ... zip-9` | Chọn mức nén archive khi tạo. |
| `--date timestamp` | Chuẩn hóa timestamp của các entry theo thời điểm được chỉ định. |
| `--target-platform platform` | Ghi nền tảng đích cho JMOD khi cần đóng gói theo nền tảng. |

Có thể xem các tùy chọn mà JDK đang cài hỗ trợ bằng:

~~~bash
jmod --help
jmod --help-extra
~~~

Tên tùy chọn và tính năng có thể khác giữa các phiên bản JDK. Hãy dùng trợ giúp của đúng JDK trong CI thay vì giả định mọi máy build đều có cùng phiên bản công cụ.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy module phụ thuộc | Module không nằm trong module path hoặc tên module không đúng. | Kiểm tra modular JAR/JMOD, module descriptor và đường dẫn truyền cho `--module-path`. |
| Không có hash nào được ghi | Regex không khớp tên module hoặc module được chọn không phụ thuộc vào module đích. | Kiểm tra tên module bằng `jmod describe` và sửa regex. |
| `jmod hash` báo lỗi khi đọc module path | Module path thiếu artifact, chứa archive không hợp lệ hoặc module không thể đọc. | Đưa đúng modular JAR/JMOD vào module path và kiểm tra bằng `jar --describe-module` hoặc `jmod describe`. |
| `Invalid JMOD file` | Tệp đích không phải JMOD hợp lệ hoặc truyền nhầm JAR làm JMOD đích. | Dùng `jmod create` để tạo JMOD; modular JAR có thể là module phụ thuộc trên module path nhưng không phải JMOD đích cho lệnh `jmod hash`. |
| `jmod describe` không có dòng hashes | JMOD chưa được hash hoặc regex không chọn module phụ thuộc nào. | Chạy `jmod hash --dry-run` để kiểm tra trước, sau đó ghi hash. |
| Digest thay đổi sau build | Nội dung class/resource hoặc module phụ thuộc đã thay đổi. | Build lại tập module nhất quán và chạy lại `jmod hash`. |
| `java` không tìm thấy module khi truyền JMOD vào module path | JMOD là định dạng phục vụ link-time, không phải modular JAR để chạy trực tiếp bằng launcher. | Dùng `jlink` tạo runtime image hoặc dùng modular JAR trên module path. |
| JMOD được tạo nhưng `jlink` không phân giải được module | Thiếu module phụ thuộc, sai module path hoặc artifact không tương thích nền tảng/JDK. | Kiểm tra module graph, JDK tương ứng và toàn bộ module path. |

Quy trình chẩn đoán:

1. Xác nhận JDK bằng `jmod --version` hoặc `jmod --help`.
2. Dùng `jmod describe` để kiểm tra module đích.
3. Dùng `jar --describe-module` hoặc `jmod describe` để xác định tên module phụ thuộc.
4. Dùng `jmod hash --dry-run` để xác nhận regex và danh sách module được chọn.
5. Ghi hash rồi kiểm tra bằng `jmod describe`.
6. Nếu cần kiểm tra bytecode, giải nén JMOD và xem `ModuleHashes` bằng `javap -v`.
7. Kiểm tra lại module path trước khi chạy `jlink`.

## 15. Checklist trước khi phát hành

- Đã xác định đúng module đích cần ghi hash.
- Module descriptor khai báo đúng `requires` và `exports`.
- Các module phụ thuộc đã được build và đóng gói với phiên bản dự kiến.
- Module path chứa các modular JAR/JMOD cần thiết để tính hash.
- Regex `--hash-modules` chọn đúng tên module phụ thuộc.
- Đã chạy `jmod hash --dry-run` và xem kết quả trước khi ghi.
- Đã chạy `jmod hash` trên JMOD đích.
- `jmod describe` hiển thị đúng danh sách hash và thuật toán.
- Khi cần kiểm tra sâu, `javap -v` hiển thị attribute `ModuleHashes`.
- Sau khi thay đổi module phụ thuộc, đã tính lại hash.
- JMOD được dùng ở giai đoạn link phù hợp; runtime image được tạo và kiểm tra bằng `jlink`.
- Checksum và chữ ký số của artifact phát hành được quản lý riêng nếu quy trình yêu cầu.

Module hash trong JMOD giúp gắn một module đã đóng gói với những module phụ thuộc cụ thể. Hãy chọn đúng module đích, đặt các module phụ thuộc trên module path, dùng regex phù hợp, kiểm tra trước bằng `--dry-run` rồi ghi hash và xác nhận bằng `jmod describe` hoặc `javap -v`.

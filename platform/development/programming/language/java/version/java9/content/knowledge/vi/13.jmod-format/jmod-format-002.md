# Lớp, cấu hình, thư viện native và lệnh trong JMOD

## Mục tiêu

JMOD là định dạng archive dành cho module của Java Platform Module System (JPMS). Ngoài bytecode và resource của module, JMOD còn có thể đóng gói cấu hình, header native, thư viện native, lệnh native, legal notices và trang hướng dẫn. Nhờ các section này, công cụ `jlink` có thể tạo runtime image chứa cả thành phần Java lẫn thành phần native mà một module cần.

Bài này giải thích cấu trúc JMOD, vai trò từng section, cách tạo và kiểm tra một file JMOD, rồi liên kết module đó vào runtime image.

Sau bài này, bạn có thể:

- Phân biệt JMOD với modular JAR và runtime image.
- Nhận diện các section `classes`, `conf`, `include`, `legal`, `lib`, `bin` và `man`.
- Đóng gói module đã biên dịch cùng cấu hình, native library và native command.
- Dùng `jmod create`, `list`, `describe`, `extract` và hiểu mục đích của `hash`.
- Dùng `jlink` để tạo runtime image từ JMOD.
- Kiểm tra đúng đường dẫn đầu vào, target platform và các lỗi đóng gói thường gặp.

Ví dụ Java được biên dịch bằng `javac --release 17` và kiểm tra bằng JDK 24.0.2.

## 1. JMOD là gì?

JMOD là định dạng đóng gói một module. Nó lưu module descriptor cùng class files và có thể lưu thêm những thành phần cần thiết khi liên kết hoặc phân phối runtime.

Một JMOD thường được tạo từ một module đã biên dịch. Công cụ `jmod` cung cấp các thao tác tạo, trích xuất, liệt kê, mô tả và ghi module hashes.

JMOD đặc biệt hữu ích khi module cần mang theo những thành phần ngoài bytecode, ví dụ:

- File cấu hình mà người vận hành có thể chỉnh sửa.
- Header C/C++ để biên dịch native code tích hợp với Java.
- Thư viện native theo hệ điều hành và kiến trúc.
- Lệnh native đi kèm module.
- Legal notices và manual pages.

JMOD thường được dùng làm đầu vào cho quá trình liên kết bằng `jlink`. Nó không phải một cách thay thế trực tiếp cho modular JAR khi chạy ứng dụng.

## 2. Phân biệt JMOD, modular JAR và runtime image

| Artifact | Chứa gì? | Vai trò chính |
|---|---|---|
| Modular JAR | `module-info.class`, class files và resource | Phân phối module để compile hoặc chạy ứng dụng |
| JMOD | Module classes cùng các section bổ sung như config, headers, native libraries, commands, legal và man pages | Đóng gói module để xử lý và liên kết runtime |
| Runtime image | Runtime Java đã được liên kết với các module cần thiết | Chạy ứng dụng trên môi trường triển khai |

JMOD được thiết kế cho compile/link time, đặc biệt là quá trình tạo runtime image. Java launcher không dùng file JMOD như một modular JAR thông thường trên runtime module path. Nếu cần chạy ứng dụng từ module path, hãy dùng modular JAR hoặc dùng runtime image do `jlink` tạo.

Cũng không nên xem JMOD như một file JAR đổi đuôi. JMOD có định dạng riêng và các section riêng; dùng lệnh `jmod` để kiểm tra, không thao tác như thể đó là một JAR thông thường.

## 3. Cấu trúc các section trong JMOD

Các section chính được đặt tên theo mục đích:

| Section trong JMOD | Dữ liệu | Tùy chọn tạo |
|---|---|---|
| `classes/` | `module-info.class`, class files và resource của module | `--class-path` |
| `conf/` | File cấu hình có thể chỉnh sửa sau khi cài đặt | `--config` |
| `include/` | Header native, thường là C/C++ hoặc JNI headers | `--header-files` |
| `legal/` | License, copyright và legal notices | `--legal-notices` |
| `lib/` | Native libraries như DLL, SO hoặc dylib | `--libs` |
| `bin/` | Native commands đi kèm module | `--cmds` |
| `man/` | Manual pages cho lệnh hoặc thành phần module | `--man-pages` |

Các section bổ sung là tùy chọn. Một module Java thuần có thể chỉ có `classes/`; module có tích hợp native hoặc cung cấp công cụ cho hệ điều hành có thể dùng thêm các section còn lại.

Ví dụ kết quả của `jmod list`:

~~~text
classes/module-info.class
classes/com/example/jmoddemo/Main.class
conf/demo.properties
include/demo.h
legal/LICENSE.txt
man/demo-helper.1
bin/demo-helper.exe
lib/demo-native.dll
~~~

### 3.1. classes — module descriptor, bytecode và resource

Đây là section quan trọng nhất. Nó chứa:

- `module-info.class`: descriptor đã biên dịch, mô tả tên module, `requires`, `exports`, `opens`, `uses`, `provides` và các thuộc tính module liên quan.
- Các class đã biên dịch.
- Resource mà module cần khi chạy.

Khi tạo JMOD từ thư mục output của `javac`, thư mục truyền vào `--class-path` phải là thư mục chứa trực tiếp `module-info.class` của module đó.

Ví dụ với lệnh:

~~~bash
javac --release 17 -d out --module-source-path src -m com.example.jmoddemo
~~~

Compiler tạo cấu trúc:

~~~text
out/
└── com.example.jmoddemo/
    ├── module-info.class
    └── com/example/jmoddemo/Main.class
~~~

Do đó, đường dẫn đúng cho `--class-path` là `out/com.example.jmoddemo`, không phải thư mục cha `out`. Nếu truyền nhầm thư mục cha, `jmod create` có thể báo không tìm thấy `module-info.class`.

### 3.2. conf — cấu hình có thể chỉnh sửa

Section `conf/` chứa file cấu hình người vận hành có thể chỉnh sửa sau khi runtime image được cài đặt.

Ví dụ:

~~~text
conf/demo.properties
~~~

Nội dung mẫu:

~~~properties
mode=production
cache-size=256
~~~

Khi tạo JMOD, truyền thư mục cấu hình bằng `--config`. Khi liên kết module bằng `jlink`, các file cấu hình có thể được đưa vào thư mục `conf` của runtime image.

Không đặt bytecode Java vào `conf`. Class files và resource của module thuộc `classes/`; cấu hình có thể chỉnh sửa thuộc `conf/`.

### 3.3. include — header native

Section `include/` chứa header files cần cho native development hoặc tích hợp native code.

Ví dụ:

~~~text
include/demo.h
include/demo_jni.h
~~~

Header có thể công bố cấu trúc dữ liệu, macro hoặc function prototype để native code tương tác với module. Với JNI, header được tạo từ Java native declarations có thể được đưa vào section này nếu module phân phối cần cung cấp chúng.

Tùy chọn tương ứng là `--header-files`.

Header file không phải thư viện đã biên dịch. Nó cung cấp khai báo để compiler native sử dụng; binary native đã biên dịch được đặt trong `lib/` hoặc `bin/` tùy loại.

### 3.4. legal — legal notices

Section `legal/` chứa các thông báo bản quyền, giấy phép và thông tin pháp lý cần đi kèm module.

Ví dụ:

~~~text
legal/LICENSE.txt
legal/THIRD-PARTY-NOTICES.txt
~~~

Đóng gói legal notices giúp runtime image phân phối các thông tin pháp lý cùng thành phần đã liên kết. Tùy chọn tạo section này là `--legal-notices`.

Chỉ đưa các notice thực sự áp dụng cho module và các thành phần được phân phối cùng nó.

### 3.5. lib — thư viện native

Section `lib/` chứa thư viện native mà module cần, ví dụ:

- Windows: `.dll`.
- Linux: `.so`.
- macOS: `.dylib`.

Ví dụ:

~~~text
lib/demo-native.dll
~~~

Tùy chọn tạo là `--libs`.

Thư viện native phải được biên dịch cho hệ điều hành, kiến trúc CPU và ABI tương thích với runtime image mục tiêu. Việc chép một file DLL vào JMOD không biến file đó thành thư viện hợp lệ; JMOD chỉ đóng gói file, còn tính tương thích và khả năng nạp phụ thuộc vào binary thực tế cùng các dependency native của nó.

Nếu module dùng JNI hoặc FFM để gọi native code, cần kiểm tra cả tên thư viện, đường dẫn tìm kiếm, kiến trúc và dependency native khi chạy trên môi trường triển khai.

### 3.6. bin — native commands

Section `bin/` chứa các native command đi kèm module. Ví dụ trên Windows là file thực thi `.exe`; trên Linux/macOS có thể là executable phù hợp với nền tảng.

Ví dụ:

~~~text
bin/demo-helper.exe
~~~

Tùy chọn tạo là `--cmds`.

Đây là chương trình native đi kèm module, không phải class Java có phương thức `main`. Nếu cần cung cấp Java application entry point, hãy đóng gói class Java trong `classes/` và có thể khai báo main class cho module.

### 3.7. man — manual pages

Section `man/` chứa trang hướng dẫn cho native command hoặc công cụ mà module cung cấp.

Ví dụ:

~~~text
man/demo-helper.1
~~~

Tùy chọn tạo là `--man-pages`. Manual pages có thể được đưa vào runtime image để người vận hành tra cứu lệnh và tham số của module.

## 4. Các tùy chọn quan trọng của jmod

Công cụ có năm operation mode:

| Lệnh | Mục đích |
|---|---|
| `jmod create` | Tạo file JMOD mới |
| `jmod list` | Liệt kê entry trong JMOD |
| `jmod describe` | Hiển thị thông tin module |
| `jmod extract` | Trích xuất các section ra thư mục |
| `jmod hash` | Ghi module hashes để ràng buộc các module liên quan |

Một số tùy chọn tạo thường dùng:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--class-path` | JAR hoặc thư mục chứa module classes |
| `--config` | Thư mục cấu hình |
| `--header-files` | Thư mục header native |
| `--legal-notices` | Thư mục legal notices |
| `--libs` | Thư mục native libraries |
| `--cmds` | Thư mục native commands |
| `--man-pages` | Thư mục manual pages |
| `--module-version` | Ghi module version |
| `--main-class` | Khai báo main class |
| `--target-platform` | Ghi target platform cho module |
| `--compress` | Chọn mức nén archive |
| `--date` | Đặt timestamp entry |
| `--exclude` | Loại bỏ các file khớp pattern |

Mức nén có dạng `zip-0` đến `zip-9`; `zip-0` không nén, `zip-9` nén mạnh nhất và mặc định là `zip-6`. Với build cần tái lập, `--date` giúp cố định timestamp entry thay vì để thời điểm build làm thay đổi archive.

`--target-platform` hữu ích khi JMOD chứa native binaries. Hãy ghi đúng nền tảng mà các binary hướng tới, ví dụ `windows-amd64` hoặc `linux-amd64`, theo quy ước target platform của môi trường build. Không dùng cùng một JMOD chứa native binary của nền tảng này cho runtime image của nền tảng khác.

## 5. Tạo JMOD từ một module Java

Ví dụ tạo module nhỏ tên `com.example.jmoddemo`.

### 5.1. Cấu trúc source

~~~text
jmod-demo/
├── src/
│   └── com.example.jmoddemo/
│       ├── module-info.java
│       └── com/example/jmoddemo/Main.java
├── jmod-input/
│   ├── config/
│   ├── include/
│   ├── legal/
│   ├── libs/
│   ├── cmds/
│   └── man/
├── out/
└── jmods/
~~~

File `src/com.example.jmoddemo/module-info.java`:

~~~java
module com.example.jmoddemo {
    exports com.example.jmoddemo;
}
~~~

File `src/com.example.jmoddemo/com/example/jmoddemo/Main.java`:

~~~java
package com.example.jmoddemo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("JMOD demo");
    }
}
~~~

### 5.2. Biên dịch module

Chạy từ thư mục `jmod-demo`:

~~~bash
javac --release 17 -d out --module-source-path src -m com.example.jmoddemo
~~~

Sau khi biên dịch, kiểm tra rằng `out/com.example.jmoddemo/module-info.class` tồn tại.

### 5.3. Chuẩn bị các section bổ sung

Ví dụ cây dữ liệu đầu vào:

~~~text
jmod-input/
├── config/
│   └── demo.properties
├── include/
│   └── demo.h
├── legal/
│   └── LICENSE.txt
├── libs/
│   └── demo-native.dll
├── cmds/
│   └── demo-helper.exe
└── man/
    └── demo-helper.1
~~~

Các file `demo-native.dll` và `demo-helper.exe` trong ví dụ là tên minh họa. Khi phân phối thực tế, thay chúng bằng native library và native command đã biên dịch đúng cho target platform. JMOD không biên dịch C/C++ và không tự tạo executable native.

### 5.4. Tạo JMOD

Lệnh đóng gói đầy đủ:

~~~bat
jmod create ^
  --class-path out/com.example.jmoddemo ^
  --config jmod-input/config ^
  --header-files jmod-input/include ^
  --legal-notices jmod-input/legal ^
  --libs jmod-input/libs ^
  --cmds jmod-input/cmds ^
  --man-pages jmod-input/man ^
  --module-version 1.2.3 ^
  --main-class com.example.jmoddemo.Main ^
  --compress zip-6 ^
  jmods/com.example.jmoddemo.jmod
~~~

Trên PowerShell có thể viết thành một dòng hoặc dùng dấu backtick để nối dòng. Dấu `^` trong ví dụ là cách nối dòng của Windows Command Prompt.

Nếu JMOD có native binary, có thể thêm `--target-platform` với giá trị phù hợp, ví dụ:

~~~bat
--target-platform windows-amd64
~~~

Nếu module không có native library hoặc native command, bỏ các tùy chọn section tương ứng. Một JMOD chỉ chứa module classes vẫn hợp lệ.

## 6. Kiểm tra JMOD sau khi tạo

### 6.1. Liệt kê entry bằng jmod list

~~~bash
jmod list jmods/com.example.jmoddemo.jmod
~~~

Output có thể bao gồm:

~~~text
classes/module-info.class
classes/com/example/jmoddemo/Main.class
conf/demo.properties
include/demo.h
legal/LICENSE.txt
man/demo-helper.1
bin/demo-helper.exe
lib/demo-native.dll
~~~

Dùng lệnh này để xác nhận file đã vào đúng section. Nếu thiếu file, kiểm tra đường dẫn đầu vào của tùy chọn tương ứng và cấu trúc thư mục.

### 6.2. Xem module descriptor bằng jmod describe

~~~bash
jmod describe jmods/com.example.jmoddemo.jmod
~~~

Với module mẫu, output trên JDK 24.0.2:

~~~text
com.example.jmoddemo@1.2.3
exports com.example.jmoddemo
requires java.base mandated
main-class com.example.jmoddemo.Main
~~~

Lệnh này mô tả module name, version, exports, requires và main class. Nó giúp kiểm tra descriptor đã được đóng gói đúng.

### 6.3. Trích xuất bằng jmod extract

~~~bash
jmod extract --dir extracted jmods/com.example.jmoddemo.jmod
~~~

Các section được trích xuất vào thư mục `extracted`:

~~~text
extracted/
├── classes/
├── conf/
├── include/
├── legal/
├── lib/
├── bin/
└── man/
~~~

Có thể kiểm tra từng file sau khi extract. Đây là cách xác nhận nội dung archive mà không cần dùng công cụ xử lý JAR thông thường.

## 7. Liên kết JMOD thành runtime image bằng jlink

JMOD phát huy vai trò chính trong bước liên kết. `jlink` đọc module từ JMOD và các module của JDK, phân giải dependency rồi tạo runtime image chứa các module cần thiết.

Lệnh:

~~~bash
jlink --module-path jmods --add-modules com.example.jmoddemo --output runtime-image
~~~

Chạy ứng dụng bằng runtime image vừa tạo.

Trên Linux/macOS:

~~~bash
runtime-image/bin/java --module com.example.jmoddemo/com.example.jmoddemo.Main
~~~

Trên Windows:

~~~powershell
.\runtime-image\bin\java.exe --module com.example.jmoddemo/com.example.jmoddemo.Main
~~~

Stdout:

~~~text
JMOD demo
~~~

Khi JMOD chứa native library hoặc native command hợp lệ, `jlink` có thể đưa các file đó vào runtime image. Trong thử nghiệm đóng gói, file native được kiểm tra ở section `lib/` và `bin/`, được extract thành công và xuất hiện trong image sau khi liên kết. Việc gọi hoặc chạy native binary cần binary thật, đúng nền tảng và dependency native tương ứng.

Có thể dùng `--strip-debug`, `--no-header-files`, `--no-man-pages` hoặc các plugin `jlink` khác khi muốn điều chỉnh kích thước và nội dung runtime image. Chỉ loại bỏ header, man pages hoặc dữ liệu debug khi runtime image không cần các thành phần đó.

## 8. Vì sao không chạy JMOD trực tiếp bằng java?

JMOD là đầu vào đóng gói/liên kết, không phải artifact runtime module path thông thường. Ví dụ, không chạy:

~~~bash
java --module-path jmods --module com.example.jmoddemo
~~~

để thay thế cho bước liên kết. Thay vào đó:

- Dùng modular JAR nếu muốn chạy module trực tiếp từ module path.
- Dùng JMOD cùng `jlink` nếu muốn tạo runtime image chuyên biệt.
- Dùng launcher trong runtime image để chạy ứng dụng sau khi liên kết.

Điều này cũng giải thích vì sao JMOD có thể chứa header, legal notices, man pages và native commands: các section đó phục vụ quá trình đóng gói và tạo môi trường triển khai, không chỉ phục vụ class loader.

## 9. jmod hash và module hashes

Operation `jmod hash` dùng để tính và ghi module hashes nhằm ràng buộc một module với các module khác có quan hệ phụ thuộc. Nó không phải lệnh tạo SHA-256 checksum chung để kiểm tra file JMOD có bị thay đổi hay không.

Một dạng lệnh:

~~~bash
jmod hash --module-path module-path --hash-modules "com.example.*" module.jmod
~~~

`--hash-modules` nhận regular expression để chọn các module cần ghi hash. Các hash được ghi vào JMOD hoặc modular JAR liên quan theo quy tắc tied modules của JPMS.

Đây là tính năng dành cho quy trình phân phối module có ràng buộc hash. Với ứng dụng thông thường chỉ cần tạo JMOD và liên kết bằng jlink, không cần thêm bước hash nếu module descriptor và quy trình phát hành không yêu cầu.

## 10. Các lưu ý về native libraries và target platform

Native binary tạo ra nhiều ràng buộc hơn class Java:

- File phải đúng hệ điều hành: DLL, SO hoặc dylib.
- Kiến trúc CPU phải tương thích, ví dụ x64 hoặc ARM64.
- ABI và runtime native cần thiết phải có trên môi trường đích.
- Các thư viện native phụ thuộc cũng phải được phân phối hoặc có sẵn trên hệ điều hành.
- Tên file và cơ chế tìm kiếm thư viện phải khớp với cách ứng dụng nạp native library.
- Nếu JMOD ghi target platform, metadata phải phản ánh đúng binary được đóng gói.

Không đặt một file placeholder hoặc binary sai nền tảng vào JMOD rồi coi như native integration đã hoàn thành. Có thể kiểm tra rằng file được đóng gói và liên kết, nhưng cần integration test riêng để chứng minh native library load được và native command chạy được trên hệ điều hành mục tiêu.

Header native trong `include/` cũng cần tương thích với phiên bản binary và API mà module cung cấp. Khi thay đổi ABI, cần cập nhật header, native library và tài liệu đi kèm đồng bộ.

## 11. Lỗi thường gặp và cách xử lý

### jmod create báo không tìm thấy module-info.class

Nguyên nhân thường là `--class-path` trỏ vào thư mục cha chứa nhiều module thay vì thư mục module đã biên dịch.

Cách sửa: trỏ thẳng vào thư mục có `module-info.class`, ví dụ `out/com.example.jmoddemo`.

### JMOD list thiếu một section

Kiểm tra tùy chọn đã dùng và thư mục đầu vào. Ví dụ native libraries phải truyền qua `--libs`; native commands phải truyền qua `--cmds`; headers phải truyền qua `--header-files`.

### jmod describe không hiện module version hoặc main class

Kiểm tra đã truyền `--module-version` và `--main-class` khi tạo chưa. Main class cũng phải tồn tại trong classes section và có entry point hợp lệ.

### jlink không tìm thấy module

Kiểm tra module name trong `module-info.class`, tên file JMOD, module path và các dependency của module. Dùng `jmod describe` để xác nhận module name và `jmod list` để kiểm tra nội dung.

### Dùng JMOD như modular JAR

Java launcher không dùng JMOD theo cách dùng modular JAR. Dùng `jlink` để tạo runtime image hoặc phân phối modular JAR nếu cần chạy trực tiếp từ module path.

### Native library không nạp được sau khi liên kết

Kiểm tra target platform, kiến trúc, ABI, dependency native, tên file và đường dẫn tìm kiếm của native loader. Việc file có mặt trong JMOD hoặc runtime image chưa chứng minh nó có thể được nạp.

### Native command không chạy được

Kiểm tra executable bit trên Unix, định dạng binary, target platform và các dependency cần thiết. JMOD chỉ đóng gói file; nó không chuyển đổi một script hoặc file sai định dạng thành native executable.

### Dùng jar để kiểm tra JMOD

Dùng `jmod list`, `jmod describe` và `jmod extract` cho file JMOD. Dùng `jar` cho JAR archive.

## 12. Checklist trước khi phát hành JMOD

- [ ] Module đã biên dịch và có `module-info.class`.
- [ ] `--class-path` trỏ đến đúng thư mục module, không phải thư mục cha.
- [ ] Class files và resource cần thiết nằm trong `classes/`.
- [ ] Cấu hình người vận hành chỉnh sửa được đã nằm trong `conf/`.
- [ ] Header native cần phân phối đã nằm trong `include/`.
- [ ] Legal notices và license đã nằm trong `legal/`.
- [ ] Native libraries đã nằm trong `lib/` và đúng target platform.
- [ ] Native commands đã nằm trong `bin/` và đúng định dạng.
- [ ] Manual pages đã nằm trong `man/` nếu module cung cấp lệnh cần tài liệu.
- [ ] Module version và main class đã được khai báo đúng khi cần.
- [ ] `jmod list` cho thấy đủ section và file.
- [ ] `jmod describe` hiển thị đúng module descriptor.
- [ ] `jmod extract` xác nhận nội dung có thể trích xuất.
- [ ] `jlink` liên kết được module và runtime image chạy thành công.
- [ ] Native library và command đã được kiểm thử trên hệ điều hành/kiến trúc mục tiêu.

## Tóm tắt

JMOD đóng gói module Java trong section `classes/` và có thể mang thêm cấu hình `conf/`, header native `include/`, legal notices `legal/`, thư viện native `lib/`, native commands `bin/` và manual pages `man/`. Dùng `jmod create` để tạo archive, `list` để kiểm tra entry, `describe` để xem module descriptor và `extract` để trích xuất. JMOD chủ yếu phục vụ compile/link time; `jlink` đọc JMOD để tạo runtime image. Native binary phải đúng target platform và cần được kiểm thử riêng; chỉ đóng gói thành công chưa chứng minh binary chạy được.

## Tài liệu tham khảo chính thức

- [The jmod Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmod.html)
- [The jlink Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [Java Platform Module System — JMOD files](https://openjdk.org/jeps/261#Packaging:-JMOD-files)

# Tạo JAR bằng công cụ `jar`

## 1. JAR là gì và khi nào cần tạo?

JAR (Java Archive) là tệp lưu trữ dựa trên định dạng ZIP, dùng để đóng gói bytecode Java, tài nguyên và metadata vào một artifact có thể phân phối. Một JAR có thể chứa:

- Các tệp `.class` được compiler tạo ra.
- Tài nguyên như `.properties`, `.xml`, `.json`, ảnh hoặc mẫu giao diện.
- Manifest tại `META-INF/MANIFEST.MF`.
- Module descriptor `module-info.class` nếu đây là modular JAR.
- Các metadata khác phục vụ đóng gói hoặc phát hành.

JAR giúp gom nhiều tệp thành một đơn vị dễ lưu trữ, chia sẻ và đưa vào classpath hoặc module path. Một JAR thư viện thường cung cấp các lớp để ứng dụng khác sử dụng; một executable JAR có thêm thông tin về lớp khởi chạy để người dùng có thể chạy bằng `java -jar`.

Công cụ `jar` nằm trong JDK. Nó tạo, liệt kê, cập nhật và giải nén archive. Công cụ này không tự biên dịch mã nguồn Java; hãy dùng `javac` để tạo `.class` trước khi đóng gói.

## 2. Cấu trúc đầu vào trước khi tạo JAR

Giả sử dự án có một lớp Java và một tệp tài nguyên:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── Hello.java
├── resources/
│   └── config/
│       └── greeting.txt
├── out/
└── dist/
~~~

Nội dung `src/com/example/Hello.java`:

~~~java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class Hello {
    public static void main(String[] args) throws IOException {
        String name = args.length == 0
                ? "Java"
                : String.join(" ", args);

        try (InputStream input =
                     Hello.class.getResourceAsStream("/config/greeting.txt")) {
            if (input == null) {
                throw new IllegalStateException("Missing greeting resource");
            }

            String greeting = new String(
                    input.readAllBytes(), StandardCharsets.UTF_8).trim();

            System.out.println(greeting + ", " + name + "!");
        }
    }
}
~~~

Nội dung `resources/config/greeting.txt`:

~~~text
Hello
~~~

Lớp đọc tài nguyên bằng `getResourceAsStream("/config/greeting.txt")`. Dấu `/` đầu đường dẫn có nghĩa là tìm từ gốc của classpath hoặc module tương ứng. Vì vậy, khi đóng gói, tệp cần xuất hiện trong JAR tại `config/greeting.txt`.

## 3. Biên dịch mã nguồn trước khi đóng gói

Tạo thư mục đầu ra và biên dịch lớp:

~~~bash
mkdir -p out dist
javac --release 17 -encoding UTF-8 -d out src/com/example/Hello.java
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out, dist | Out-Null
javac --release 17 -encoding UTF-8 -d out src/com/example/Hello.java
~~~

Tùy chọn `-d out` đặt bytecode vào thư mục `out`. Do lớp khai báo package `com.example`, compiler tạo tệp:

~~~text
out/com/example/Hello.class
~~~

Thư mục `out` là gốc của cây bytecode. Khi đưa vào JAR, cần giữ cấu trúc `com/example/Hello.class` ở gốc archive để Java launcher tìm được lớp `com.example.Hello`.

Không đóng gói tệp `.java` thay cho `.class` khi mục tiêu là một JAR chạy bằng JVM thông thường. Source file có thể được đưa vào archive nếu dự án có yêu cầu riêng, nhưng không thay thế bytecode đã biên dịch.

## 4. Tạo JAR cơ bản bằng `jar --create`

Cú pháp tổng quát:

~~~bash
jar --create --file <archive.jar> [options] [-C <directory> <files>...]
~~~

Các thành phần thường gặp:

| Thành phần | Ý nghĩa |
|---|---|
| `--create` hoặc `-c` | Chọn chế độ tạo archive mới. |
| `--file` hoặc `-f` | Chỉ định tên và đường dẫn tệp JAR đầu ra. |
| `-C directory files` | Chuyển vào thư mục chỉ định rồi thêm các tệp/thư mục theo đường dẫn tương đối từ đó. |
| `--verbose` hoặc `-v` | In tên các mục được thêm vào archive. |
| `--main-class` hoặc `-e` | Khai báo lớp khởi chạy cho executable JAR hoặc modular JAR. |
| `--manifest` hoặc `-m` | Dùng manifest do người dùng cung cấp. |

Tạo JAR chứa bytecode và tài nguyên của ví dụ:

~~~bash
jar --create --file dist/hello.jar --main-class com.example.Hello -C out . -C resources .
~~~

Giải thích lệnh:

1. `--create` tạo archive mới.
2. `--file dist/hello.jar` đặt tên JAR đầu ra.
3. `--main-class com.example.Hello` khai báo lớp có phương thức `main`.
4. `-C out .` chuyển vào `out` và thêm toàn bộ nội dung của thư mục này.
5. `-C resources .` chuyển vào `resources` và thêm toàn bộ tài nguyên của thư mục này.

Có thể bật chế độ verbose để quan sát các mục được thêm:

~~~bash
jar --create --verbose --file dist/hello.jar --main-class com.example.Hello -C out . -C resources .
~~~

Tùy chọn `-C` có thể xuất hiện nhiều lần. Mỗi lần nó thay đổi thư mục làm việc của `jar` cho các mục đứng sau nó. Dùng `-C out .` giúp các tệp trong `out` nằm ở đúng vị trí gốc của JAR; nếu chỉ thêm thư mục `out` mà không chuyển vào trong, archive có thể chứa `out/com/example/Hello.class`, khiến classpath không khớp với tên lớp.

## 5. Cấu trúc JAR sau khi tạo

Liệt kê nội dung archive:

~~~bash
jar --list --file dist/hello.jar
~~~

Các entry chính của ví dụ sẽ có dạng:

~~~text
META-INF/
META-INF/MANIFEST.MF
com/example/Hello.class
config/greeting.txt
~~~

JAR mặc định có manifest do công cụ tạo. Khi dùng `--main-class`, manifest có thuộc tính `Main-Class` trỏ tới lớp khởi chạy.

Có thể đọc manifest bằng cách giải nén archive hoặc mở JAR bằng công cụ ZIP. Nội dung quan trọng sẽ tương tự:

~~~text
Manifest-Version: 1.0
Created-By: ...

Main-Class: com.example.Hello

~~~

Một số thuộc tính như `Created-By` có thể khác tùy JDK. Điều cần kiểm tra là `Main-Class` có đúng tên lớp đầy đủ và manifest có định dạng hợp lệ.

## 6. Chạy executable JAR

Sau khi JAR có `Main-Class`, chạy bằng:

~~~bash
java -jar dist/hello.jar Ada
~~~

Stdout:

~~~text
Hello, Ada!
~~~

Không cần truyền tên lớp sau tên JAR vì launcher lấy entry point từ manifest. Các đối số đặt sau tên JAR được chuyển vào `main(String[] args)`.

Nếu chạy không có đối số:

~~~bash
java -jar dist/hello.jar
~~~

Stdout:

~~~text
Hello, Java!
~~~

Lệnh `java -jar` yêu cầu JAR có manifest khai báo `Main-Class`. Nếu JAR chỉ là thư viện hoặc manifest thiếu thuộc tính này, launcher sẽ báo không có main manifest attribute. Trong trường hợp đó, chạy bằng classpath và tên lớp đầy đủ:

~~~bash
java -cp dist/library.jar com.example.SomeMain
~~~

JAR thư viện thông thường không cần `Main-Class`; chỉ thêm entry point khi archive được thiết kế để chạy độc lập.

## 7. Tạo manifest thủ công

Khi cần khai báo thêm thông tin, có thể tạo file manifest riêng, ví dụ `manifest.mf`:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Hello
Implementation-Title: Hello Demo
Implementation-Version: 1.0.0

~~~

Dòng trống cuối cùng là cần thiết để kết thúc phần manifest chính. Tên lớp trong `Main-Class` phải là tên đầy đủ, không có đuôi `.class`.

Tạo JAR bằng manifest này:

~~~bash
jar --create --file dist/hello.jar --manifest manifest.mf -C out . -C resources .
~~~

Sau đó chạy:

~~~bash
java -jar dist/hello.jar Ada
~~~

Có hai cách phổ biến để thiết lập entry point:

- Dùng `--main-class com.example.Hello` ngay trong lệnh `jar`.
- Khai báo `Main-Class: com.example.Hello` trong manifest rồi truyền `--manifest manifest.mf`.

Chọn một nơi làm nguồn cấu hình chính để tránh nhầm lẫn khi manifest được tạo hoặc cập nhật trong pipeline. Manifest có quy tắc định dạng riêng; nếu một dòng thuộc tính dài, cần dùng dòng tiếp nối theo định dạng manifest thay vì ngắt tùy ý.

## 8. Khai báo thư viện phụ thuộc bằng manifest

Một executable JAR không tự động chứa tất cả thư viện mà ứng dụng sử dụng. Nếu ứng dụng phụ thuộc vào các JAR bên ngoài, có thể khai báo `Class-Path` trong manifest.

Ví dụ cấu trúc phân phối:

~~~text
dist/
├── app.jar
└── lib/
    ├── library-a.jar
    └── library-b.jar
~~~

Manifest `manifest.mf`:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/library-a.jar lib/library-b.jar

~~~

Tạo JAR:

~~~bash
jar --create --file dist/app.jar --manifest manifest.mf -C out .
~~~

Khi chạy `java -jar dist/app.jar`, Java launcher đọc các entry trong manifest và bổ sung những JAR được khai báo vào đường dẫn tìm lớp. Các đường dẫn `Class-Path` là URL tương đối theo vị trí của JAR chứa manifest; chúng không phải đường dẫn tính từ thư mục làm việc của terminal.

Lưu ý:

- Các entry trong `Class-Path` được phân tách bằng dấu cách.
- Các đường dẫn tương đối phải khớp với cấu trúc thư mục phân phối.
- Manifest `Class-Path` không tải dependency từ Maven/Gradle repository và không giải quyết phiên bản thư viện.
- Khi dùng `java -jar`, classpath do tùy chọn `-cp` cung cấp không được dùng để thay thế classpath của executable JAR; hãy cấu hình dependency theo cách phù hợp với chế độ chạy.

Nếu muốn một JAR chứa cả ứng dụng và dependency, cần dùng quy trình tạo fat/uber JAR của build tool hoặc đóng gói dependency theo cấu trúc được launcher hỗ trợ. Lệnh `jar --create` chỉ đóng gói những tệp và thư mục được chỉ định; nó không tự tìm và gộp dependency.

## 9. Tạo JAR thư viện

Một thư viện Java thường chỉ cần bytecode và tài nguyên, không cần lớp khởi chạy. Ví dụ nếu `out` chứa các lớp của package `com.example.greetings`, tạo thư viện:

~~~bash
jar --create --file dist/greetings.jar -C out .
~~~

Kiểm tra nội dung:

~~~bash
jar --list --file dist/greetings.jar
~~~

Ứng dụng có thể dùng thư viện trên classpath:

~~~bash
java -cp "out:dist/greetings.jar" com.example.Main
~~~

Trên Windows:

~~~powershell
java -cp "out;dist/greetings.jar" com.example.Main
~~~

Thứ tự các mục classpath có thể ảnh hưởng lớp nào được nạp nếu nhiều JAR chứa cùng tên lớp. Tránh đưa nhiều phiên bản trùng của một thư viện vào cùng classpath.

Đối với thư viện được phân phối cho người dùng khác, nên cân nhắc thêm tài liệu API, phiên bản, license và metadata cần thiết. Các thông tin này có thể nằm trong manifest hoặc được quản lý bởi hệ thống phát hành artifact.

## 10. Tạo modular JAR

Một modular JAR chứa `module-info.class` ở gốc archive. Module descriptor khai báo tên module và các package được export hoặc module được yêu cầu.

Ví dụ `src/module-info.java`:

~~~java
module com.example.app {
}
~~~

Ví dụ `src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from modular JAR!");
    }
}
~~~

Biên dịch module:

~~~bash
javac --release 17 -d mods/com.example.app src/module-info.java src/com/example/Main.java
~~~

Tạo modular JAR:

~~~bash
jar --create --file dist/modular-app.jar --main-class com.example.Main -C mods/com.example.app .
~~~

Kiểm tra module descriptor:

~~~bash
jar --describe-module --file dist/modular-app.jar
~~~

Chạy bằng module path:

~~~bash
java --module-path dist/modular-app.jar -m com.example.app
~~~

Stdout:

~~~text
Hello from modular JAR!
~~~

Tên module trong `-m` phải khớp với tên khai báo trong `module-info.java`. Đối với modular JAR có main class được khai báo, launcher có thể sử dụng entry point đó khi chạy module. Nếu không khai báo main class, chỉ định lớp đầy đủ sau dấu `/`, ví dụ `-m com.example.app/com.example.Main`.

Modular JAR khác JAR thông thường ở module descriptor và quy tắc đóng gói. Đừng chỉ đổi tên tệp JAR hoặc thêm một thư mục vào archive rồi xem đó là modular JAR; `module-info.class` phải được biên dịch từ module descriptor hợp lệ và nằm ở gốc archive.

## 11. JAR nhiều phiên bản (multi-release JAR)

Multi-release JAR cho phép một archive chứa các phiên bản class khác nhau theo phiên bản Java. JVM chọn lớp phù hợp với phiên bản runtime khi nạp archive.

Ví dụ cấu trúc:

~~~text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 17/
│           └── com/example/Feature.class
└── com/
    └── example/
        └── Feature.class
~~~

Phiên bản nền nằm ở gốc JAR; phiên bản thay thế cho Java 17 nằm dưới `META-INF/versions/17/`. Manifest phải có thuộc tính:

~~~text
Multi-Release: true

~~~

Có thể tạo archive với các tệp theo phiên bản bằng tùy chọn `--release` của `jar`:

~~~bash
jar --create --file dist/library.jar --manifest manifest.mf -C base . --release 17 -C java17 .
~~~

Trong đó `base` chứa các lớp nền, còn `java17` chứa những lớp thay thế cho Java 17. Chỉ các tệp đứng sau `--release 17` mới được đặt dưới `META-INF/versions/17/`.

Dùng multi-release JAR khi cần cung cấp implementation tối ưu cho runtime mới nhưng vẫn giữ implementation nền cho runtime cũ hơn. Cần kiểm tra API của các phiên bản nhất quán và thử trên từng runtime mục tiêu.

Kiểm tra tính nhất quán:

~~~bash
jar --validate --file dist/library.jar
~~~

Đây là tính năng đóng gói nâng cao. Nếu dự án chỉ hỗ trợ một phiên bản Java, một JAR thông thường sẽ đơn giản hơn.

## 12. Cập nhật, liệt kê và giải nén JAR

Các thao tác thường dùng:

~~~bash
# Liệt kê entry trong archive
jar --list --file dist/hello.jar

# Liệt kê chi tiết
jar --list --verbose --file dist/hello.jar

# Cập nhật hoặc thêm tài nguyên vào archive
jar --update --file dist/hello.jar -C resources .

# Giải nén toàn bộ archive vào thư mục extracted
jar --extract --file dist/hello.jar --dir extracted
~~~

`--update` thay thế entry trùng tên hoặc thêm entry mới. Dùng nó khi cần cập nhật archive hiện có, nhưng với artifact phát hành nên cân nhắc tạo lại từ đầu để build dễ tái lập và kiểm tra hơn.

Không cập nhật nội dung JAR sau khi đã ký bằng `jarsigner`. Mọi thay đổi đối với các entry được ký có thể làm chữ ký không còn hợp lệ. Nếu cần sửa artifact, hãy tạo lại JAR, ký lại và xác minh chữ ký sau cùng.

Có thể xem mô tả module bằng:

~~~bash
jar --describe-module --file dist/modular-app.jar
~~~

Với JAR thông thường không có module descriptor, công cụ có thể hiển thị tên automatic module suy ra hoặc thông tin tương ứng; điều đó không có nghĩa JAR đã có một `module-info.class` tường minh.

## 13. Kiểm soát thời gian và tính tái lập của JAR

Hai lần build cùng mã nguồn có thể tạo archive khác nhau nếu timestamp, thứ tự đầu vào, manifest hoặc môi trường build thay đổi. Điều này gây khó khăn khi so sánh checksum và truy vết artifact.

Tùy chọn `--date` của `jar` cho phép đặt timestamp thống nhất cho các entry:

~~~bash
jar --create --file dist/hello.jar --date=2024-01-01T00:00:00Z --main-class com.example.Hello -C out . -C resources .
~~~

Để tăng tính tái lập:

- Dùng cùng phiên bản JDK và cùng cấu hình compiler.
- Tạo đầu ra từ thư mục build sạch.
- Giữ thứ tự danh sách đầu vào ổn định nếu truyền từng tệp riêng.
- Chuẩn hóa timestamp bằng `--date` khi quy trình phát hành yêu cầu.
- Dùng manifest ổn định, tránh ghi dữ liệu thay đổi theo máy build.
- Lưu checksum của artifact sau khi hoàn tất đóng gói.

`--date` chỉ chuẩn hóa timestamp của entry; nó không tự bảo đảm toàn bộ build tái lập nếu nội dung file, thứ tự đầu vào, manifest hoặc compiler khác nhau.

## 14. Lỗi thường gặp khi tạo JAR

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `no main manifest attribute` | JAR không có `Main-Class`. | Dùng `--main-class` hoặc manifest có `Main-Class`. |
| `Could not find or load main class` | Lớp không nằm ở đúng đường dẫn bên trong JAR hoặc tên lớp sai. | Kiểm tra `jar --list`; đóng gói nội dung thư mục output bằng `-C out .`. |
| `ClassNotFoundException` khi chạy | Thiếu dependency runtime hoặc đường dẫn `Class-Path` sai. | Kiểm tra các JAR phụ thuộc và manifest. |
| Resource trả về `null` | Tệp tài nguyên không được đóng gói hoặc đường dẫn resource sai. | Liệt kê JAR, kiểm tra entry và dùng đường dẫn tương đối từ gốc classpath đúng cách. |
| JAR có thư mục `out/` ở gốc | Đã thêm cả thư mục output thay vì chuyển vào trong. | Dùng `-C out .` khi tạo archive. |
| Chạy classpath được nhưng `java -jar` thất bại | JAR thiếu manifest entry point hoặc dependency chỉ có trong classpath ngoài. | Khai báo `Main-Class` và cấu hình dependency qua manifest `Class-Path` hoặc cách đóng gói phù hợp. |
| Module không được nhận diện | `module-info.class` thiếu, sai vị trí hoặc module path không đúng. | Kiểm tra `jar --describe-module` và cấu trúc root của archive. |
| Chữ ký JAR không hợp lệ sau cập nhật | Archive đã bị thay đổi sau khi ký. | Tạo lại artifact, ký sau cùng và chạy `jarsigner -verify`. |
| JAR khác checksum giữa các lần build | Timestamp, thứ tự entry, manifest hoặc nội dung đầu vào thay đổi. | Chuẩn hóa đầu vào và timestamp, cố định môi trường build. |

Quy trình kiểm tra khi có lỗi:

1. Dùng `jar --list --file app.jar` để xác nhận entry thực tế.
2. Kiểm tra manifest và `Main-Class` nếu chạy bằng `java -jar`.
3. Xác nhận đường dẫn package trong JAR khớp tên lớp đầy đủ.
4. Kiểm tra resource có mặt tại đúng đường dẫn.
5. Kiểm tra dependency runtime và module descriptor nếu ứng dụng modular.
6. Nếu JAR đã ký, xác minh lại chữ ký sau khi hoàn tất mọi cập nhật.

## 15. Checklist trước khi phát hành

- Đã biên dịch thành công bằng phiên bản JDK phù hợp.
- Đã xác định JAR là thư viện, executable JAR hay modular JAR.
- Các class file nằm đúng cấu trúc package ở gốc archive.
- Tài nguyên cần thiết đã được thêm và có đường dẫn đúng.
- Dùng `--main-class` hoặc manifest đúng khi JAR cần chạy bằng `java -jar`.
- Dependency runtime được đóng gói hoặc khai báo rõ ràng.
- Với modular JAR, `module-info.class` nằm ở gốc và module name hợp lệ.
- Đã kiểm tra entry bằng `jar --list` và module bằng `jar --describe-module` nếu cần.
- Đã chạy thử artifact cuối cùng bằng đúng chế độ dự kiến.
- Nếu ký JAR, chỉ ký sau khi archive hoàn tất và xác minh chữ ký.
- Nếu cần build tái lập, đã chuẩn hóa timestamp, đầu vào và môi trường build.

Khi tạo JAR, hãy bắt đầu từ thư mục chứa bytecode và tài nguyên đã chuẩn bị, dùng `jar --create --file ... -C ... .` để giữ đúng đường dẫn entry. Nếu archive cần chạy độc lập, khai báo `Main-Class`; nếu là modular JAR, đóng gói `module-info.class` ở gốc và kiểm tra bằng module path. Cuối cùng, liệt kê nội dung và chạy thử chính artifact sẽ phát hành.

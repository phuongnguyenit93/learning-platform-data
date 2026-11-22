# JMOD là gì?

JMOD là định dạng archive chuyên dụng của JDK để đóng gói một Java module cùng các thành phần có thể cần khi tạo runtime image, chẳng hạn class file, thư viện native, lệnh native, tệp cấu hình, header, giấy phép và man page. Công cụ **jmod** tạo, liệt kê, giải nén, mô tả và quản lý hash của các tệp JMOD.

JMOD thường xuất hiện trong thư mục jmods của một JDK và trong quy trình tạo runtime tùy biến bằng jlink. JMOD có liên quan đến modular JAR nhưng phục vụ mục đích đóng gói khác: JAR phù hợp để phân phối thư viện hoặc ứng dụng Java; JMOD được thiết kế cho các công cụ JDK, đặc biệt là quá trình liên kết runtime image.

## 1. JMOD là gì và dùng khi nào?

**JMOD** là định dạng archive dành cho các module của nền tảng Java. Một JMOD có thể chứa:

- Java class file và tài nguyên của module.
- Native library mà module cần.
- Native command hoặc executable đi kèm.
- Tệp cấu hình.
- Header phục vụ native development.
- Legal notice, license và man page.
- Metadata của module như phiên bản và lớp chính.

Một số module chuẩn của JDK được phân phối dưới dạng JMOD trong thư mục JDK_HOME/jmods. Ví dụ, JDK thường có các tệp như java.base.jmod và java.logging.jmod. Những tệp này được các công cụ như jlink dùng làm đầu vào để tạo runtime image.

### Những tình huống thường dùng JMOD

1. **Đóng gói module cho jlink:** đưa module ứng dụng hoặc module tùy biến vào module path để jlink liên kết runtime image.
2. **Đóng gói thành phần native:** kết hợp class file với native library, command hoặc header liên quan.
3. **Phân phối module trong quy trình xây dựng JDK:** JMOD có thể chứa những thành phần không phù hợp để đặt trong JAR thông thường.
4. **Kiểm tra module:** đọc module descriptor, liệt kê hoặc giải nén nội dung archive để chẩn đoán.

Với ứng dụng Java thông thường hoặc thư viện cần phân phối cho người dùng, JAR vẫn là lựa chọn phổ biến. Chỉ tạo JMOD khi quy trình đóng gói hoặc tạo runtime image thực sự cần định dạng này.

## 2. JMOD khác gì JAR?

JMOD và JAR đều là archive liên quan đến Java, nhưng không thể thay thế nhau trong mọi tình huống.

| Tiêu chí | JAR | JMOD |
|---|---|---|
| Mục đích chính | Phân phối ứng dụng, thư viện và tài nguyên Java | Đóng gói module cho công cụ JDK và tạo runtime image |
| Nội dung | Class file, resource, manifest, module descriptor nếu là modular JAR | Class file, resource và các section bổ sung như native library, command, config, header, legal notice, man page |
| Cấu trúc | Archive ZIP theo quy ước JAR | Định dạng archive JMOD riêng, có header và các section được phân loại |
| Dùng trực tiếp với java | Có thể chạy bằng -jar hoặc đặt trên classpath/module path tùy loại JAR | Không dùng JMOD trực tiếp như JAR trên classpath hoặc module path lúc chạy |
| Công cụ chính | jar, java, javac | jmod và jlink |
| Trường hợp phổ biến | Thư viện, executable JAR, modular JAR | Module của JDK và đầu vào cho custom runtime image |

JMOD có cấu trúc riêng, không nên coi tệp .jmod là một JAR hoặc ZIP thông thường. Không dùng java -jar ten-tep.jmod để chạy module; cũng không đưa JMOD vào classpath như một thư viện JAR.

Điểm quan trọng: **jmod đóng gói module; jlink liên kết các module để tạo runtime image; java chạy ứng dụng từ runtime image đó.**

## 3. Cấu trúc và các section của JMOD

JMOD tổ chức nội dung theo các nhóm section. Tùy module, archive có thể chỉ chứa một số section.

| Section | Nội dung thường gặp | Tùy chọn tạo tương ứng |
|---|---|---|
| classes | Class file Java và resource | --class-path |
| bin | Native command hoặc executable | --cmds |
| conf | Tệp cấu hình có thể chỉnh sửa | --config |
| include | Header file dùng cho native development | --header-files |
| legal | License và legal notice | --legal-notices |
| lib | Native library | --libs |
| man | Man page | --man-pages |

Ví dụ, module thuần Java thường chủ yếu có section classes. Một module thuộc JDK có thể cần thêm thư viện native, tệp cấu hình hoặc tài liệu đi kèm.

Module descriptor module-info.class được lưu cùng nội dung class của module. Các chỉ thị trong descriptor như requires, exports, opens, uses và provides vẫn có ý nghĩa trong quá trình phân giải module. JMOD không thay đổi quy tắc JPMS; nó là một cách đóng gói module có thêm các loại dữ liệu ngoài class file.

## 4. Công cụ jmod và các chế độ chính

Công cụ jmod nằm trong thư mục bin của JDK. Có thể kiểm tra phiên bản và cú pháp:

~~~bash
jmod --version
jmod --help
~~~

Các chế độ chính:

| Chế độ | Công dụng |
|---|---|
| create | Tạo JMOD archive mới |
| list | In tên các entry trong JMOD |
| extract | Giải nén nội dung JMOD ra thư mục |
| describe | Hiển thị thông tin module |
| hash | Ghi hash để ràng buộc các module có quan hệ phụ thuộc phù hợp |

Cú pháp tổng quát:

~~~bash
jmod create [OPTIONS] module.jmod
jmod list module.jmod
jmod describe module.jmod
jmod extract --dir extracted module.jmod
jmod hash [OPTIONS] module.jmod
~~~

Tên và tùy chọn chi tiết có thể thay đổi theo phiên bản JDK. Hãy dùng jmod --help của JDK đang triển khai để kiểm tra cú pháp chính xác.

## 5. Tạo JMOD từ một module đã biên dịch

jmod không biên dịch mã nguồn Java. Trước tiên, cần dùng javac tạo class file và module descriptor; sau đó mới dùng jmod create để đóng gói đầu ra.

Ví dụ tạo module đơn giản có tên com.example.hello.

Cấu trúc thư mục:

~~~text
jmod-demo/
└── src/
    └── com.example.hello/
        ├── module-info.java
        └── com/
            └── example/
                └── hello/
                    └── Main.java
~~~

Tệp src/com.example.hello/module-info.java:

~~~java
module com.example.hello {
}
~~~

Tệp src/com.example.hello/com/example/hello/Main.java:

~~~java
package com.example.hello;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a linked runtime!");
    }
}
~~~

### Bước 1: Biên dịch module

Từ thư mục gốc jmod-demo:

~~~bash
javac --release 17 -d mods/com.example.hello \
  src/com.example.hello/module-info.java \
  src/com.example.hello/com/example/hello/Main.java
~~~

Kết quả là một exploded module trong mods/com.example.hello:

~~~text
mods/
└── com.example.hello/
    ├── module-info.class
    └── com/
        └── example/
            └── hello/
                └── Main.class
~~~

### Bước 2: Tạo JMOD

Đóng gói thư mục module đã biên dịch:

~~~bash
jmod create \
  --class-path mods/com.example.hello \
  --module-version 1.0 \
  --main-class com.example.hello.Main \
  com.example.hello.jmod
~~~

Giải thích:

- create tạo một JMOD mới.
- --class-path chỉ định JAR hoặc thư mục chứa class file của module.
- --module-version ghi phiên bản module.
- --main-class ghi lớp chính của module.
- com.example.hello.jmod là tệp JMOD đầu ra.

Đầu vào phải là nội dung module đã được biên dịch và có module descriptor hợp lệ. Tùy chọn --main-class là metadata hỗ trợ công cụ khác; nó không biến JMOD thành một JAR có thể chạy bằng java -jar.

### Bước 3: Mô tả và liệt kê JMOD

Xem thông tin module:

~~~bash
jmod describe com.example.hello.jmod
~~~

Liệt kê entry:

~~~bash
jmod list com.example.hello.jmod
~~~

Danh sách có thể hiển thị các đường dẫn với tiền tố section, ví dụ classes/module-info.class và classes/com/example/hello/Main.class. Cách hiển thị cụ thể phụ thuộc phiên bản JDK.

### Bước 4: Giải nén JMOD

Giải nén vào thư mục riêng:

~~~bash
jmod extract --dir extracted com.example.hello.jmod
~~~

Sau khi giải nén, các section được đặt dưới thư mục extracted. Thao tác này hữu ích khi cần kiểm tra class file, native library hoặc cấu hình đã được đóng gói.

## 6. Dùng JMOD với jlink để tạo runtime image

Một trong những mục đích quan trọng của JMOD là làm đầu vào cho jlink. jlink phân giải module graph, chọn các module cần thiết và tạo một runtime image chỉ chứa những thành phần được yêu cầu.

Với ví dụ module ở trên, cần có:

- JMOD ứng dụng com.example.hello.jmod.
- Thư mục jmods của JDK đang dùng, chứa java.base.jmod và các module chuẩn khác.

Trên Linux/macOS, giả sử JAVA_HOME trỏ đến JDK hiện tại và đang đứng trong thư mục có com.example.hello.jmod:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:." \
  --add-modules com.example.hello \
  --launcher hello=com.example.hello/com.example.hello.Main \
  --output runtime
~~~

Trên Windows Command Prompt, dấu phân cách giữa các mục module path là dấu chấm phẩy:

~~~bat
jlink --module-path "%JAVA_HOME%\jmods;." --add-modules com.example.hello --launcher hello=com.example.hello/com.example.hello.Main --output runtime
~~~

Giải thích:

- --module-path cung cấp vị trí các module. Ví dụ gồm JMOD của JDK và thư mục hiện tại chứa JMOD ứng dụng.
- --add-modules chọn module gốc cần đưa vào runtime image; jlink tự phân giải các module phụ thuộc.
- --launcher tạo lệnh khởi chạy tên hello trỏ đến module và lớp main.
- --output runtime chỉ định thư mục runtime image đầu ra.

Nếu module path không chứa java.base, một số phiên bản jlink có thể tự bổ sung thư mục jmods của JDK hiện tại. Dù vậy, chỉ định rõ JDK jmods giúp lệnh dễ hiểu và kiểm soát hơn. Không trộn JMOD từ các JDK release hoặc nền tảng khác nhau.

### Chạy ứng dụng từ runtime image

Trên Linux/macOS:

~~~bash
runtime/bin/hello
~~~

Output:

~~~text
Hello from a linked runtime!
~~~

Có thể chạy trực tiếp bằng Java launcher trong runtime image:

~~~bash
runtime/bin/java -m com.example.hello/com.example.hello.Main
~~~

Trên Windows, executable được tạo trong runtime/bin; dùng runtime\bin\hello.bat nếu launcher script được tạo dưới dạng .bat, hoặc gọi runtime\bin\java.exe với tùy chọn -m tương ứng.

Runtime image là một thư mục runtime có thể triển khai. Nó không phải JMOD và cũng không phải JDK đầy đủ; chỉ chứa các module và thành phần đã được jlink đưa vào.

## 7. Các tùy chọn jmod thường gặp

Các tùy chọn tạo JMOD có thể dùng để bổ sung những loại nội dung khác nhau:

| Tùy chọn | Ý nghĩa |
|---|---|
| --class-path | JAR hoặc thư mục chứa class file và resource |
| --cmds | Thư mục chứa native commands |
| --config | Thư mục chứa tệp cấu hình |
| --header-files | Thư mục chứa header files |
| --legal-notices | Thư mục chứa license và legal notice |
| --libs | Thư mục chứa native libraries |
| --man-pages | Thư mục chứa man pages |
| --module-version | Phiên bản module |
| --main-class | Lớp chính của module |
| --target-platform | Nền tảng đích của module |
| --compress | Mức nén archive, thường từ zip-0 đến zip-9 |
| --date | Timestamp dùng cho entry archive |
| --exclude | Mẫu loại trừ tệp khỏi archive |
| --hash-modules | Mẫu module cần được ghi hash ràng buộc |

Không phải mọi module đều cần tất cả section. Với module chỉ chứa mã Java, thường chỉ cần --class-path. Chỉ thêm native library, command hoặc config khi module thực sự có các thành phần đó và chúng tương thích với target platform.

### Nén archive

Tùy chọn --compress điều khiển mức nén:

- zip-0: không nén.
- zip-1 đến zip-9: các mức nén tăng dần.
- Mặc định của JDK hiện đại thường là zip-6.

Nén mạnh có thể giảm kích thước archive nhưng làm tăng thời gian đóng gói hoặc giải nén. Hãy đo trên nội dung thực tế thay vì chọn mức nén cao nhất theo mặc định.

### Target platform

JMOD có thể chứa native code phụ thuộc hệ điều hành và kiến trúc. Tùy chọn --target-platform ghi nền tảng mục tiêu cho archive. Khi đóng gói module có native library, cần bảo đảm thư viện được build cho đúng hệ điều hành, kiến trúc CPU và ABI.

Không thể lấy JMOD chứa native library của một nền tảng rồi giả định nó chạy được trên nền tảng khác. Class file Java có tính di động hơn, nhưng native library vẫn chịu ràng buộc nền tảng.

### Hash của module phụ thuộc

Chế độ hash hỗ trợ ghi hash để ràng buộc các module có quan hệ phụ thuộc nhất định. Nó được dùng trong các quy trình đóng gói module nâng cao, đặc biệt khi cần đảm bảo module liên quan được xây dựng cùng một tập module tương ứng.

Đây không phải thao tác kiểm tra checksum chung cho mọi file JMOD. Khi sử dụng, cần đọc tài liệu jmod hash của đúng JDK và xác định rõ module path cùng regex module được chọn.

## 8. JMOD trong thư mục JDK

Một JDK đầy đủ thường có cấu trúc tương tự:

~~~text
jdk/
├── bin/
│   ├── java
│   ├── javac
│   ├── jmod
│   └── jlink
├── jmods/
│   ├── java.base.jmod
│   ├── java.logging.jmod
│   ├── java.sql.jmod
│   └── ...
└── lib/
~~~

Thư mục jmods chứa các module JDK ở dạng JMOD. Đây là đầu vào quan trọng khi jlink tạo runtime image. Không nên xóa hoặc thay thế tùy tiện các JMOD đi kèm JDK vì chúng phải tương thích với các công cụ và runtime của cùng bản phân phối.

Có thể xem vị trí JDK đang dùng bằng:

~~~bash
java --version
javac --version
~~~

Trên Linux/macOS, có thể kiểm tra JAVA_HOME và liệt kê thư mục $JAVA_HOME/jmods. Trên Windows, thư mục tương ứng thường là %JAVA_HOME%\jmods.

JMOD của các nhà cung cấp hoặc bản phát hành khác nhau không nên được trộn lẫn trong cùng một lần link nếu không có hướng dẫn tương thích rõ ràng.

## 9. Chẩn đoán lỗi thường gặp

### jmod: command not found hoặc không nhận diện lệnh

Máy có thể chỉ cài runtime tối giản hoặc PATH chưa trỏ đến thư mục bin của JDK. Kiểm tra JDK đầy đủ và đường dẫn thực tế của jmod.

### Invalid JMOD file hoặc không đọc được archive

Tệp có thể bị hỏng, không phải định dạng JMOD hợp lệ hoặc được tạo bởi công cụ không tương thích. Kiểm tra nguồn archive, kích thước, phiên bản JDK và thử jmod describe/list.

### Module descriptor không hợp lệ

JMOD cần mô tả một module phù hợp. Kiểm tra module-info.java, tên module, cú pháp requires/exports và kết quả biên dịch module-info.class. jmod chỉ đóng gói đầu ra; nó không sửa module descriptor sai.

### jlink không tìm thấy module

Kiểm tra module path có chứa JMOD ứng dụng và JMOD của JDK tương ứng hay không. Xác nhận tên module bằng jmod describe. Đảm bảo tên trong --add-modules khớp với tên module thực tế, không nhầm tên file với module name.

### Module dependency không được giải quyết

Một module được khai báo requires nhưng không có trên module path có thể làm jlink thất bại. Bổ sung JMOD hoặc modular JAR dependency phù hợp; không giải quyết lỗi bằng cách đưa archive bất kỳ vào classpath.

### Runtime image thiếu class hoặc resource

Kiểm tra module graph, module descriptor, resource đã được đóng gói trong section classes chưa và module có được đưa vào image không. jlink chỉ liên kết những module được chọn cùng các dependency cần thiết.

### Native library không tải được

Kiểm tra section libs, target platform, kiến trúc CPU, ABI và các thư viện hệ thống phụ thuộc. Một class file có thể đúng nhưng native library vẫn không tương thích với môi trường chạy.

### Dùng nhầm JMOD như JAR

JMOD không phải JAR để chạy bằng java -jar hoặc thêm vào classpath. Dùng jmod để kiểm tra/đóng gói và jlink để tạo runtime image; chạy ứng dụng từ runtime image bằng java hoặc launcher được tạo.

## 10. JMOD và các công cụ liên quan

| Công cụ | Vai trò |
|---|---|
| javac | Biên dịch mã nguồn thành class file và module descriptor |
| jar | Tạo và thao tác với JAR dùng cho ứng dụng/thư viện |
| jmod | Tạo, liệt kê, giải nén và mô tả JMOD |
| jlink | Liên kết module thành runtime image tùy biến |
| java | Chạy module hoặc ứng dụng trong runtime |
| jdeps | Phân tích phụ thuộc ở cấp class, package và module |

Luồng làm việc thường gặp:

~~~text
.java sources
     |
     v
javac
     |
     v
exploded module (class files + module-info.class)
     |
     v
jmod create
     |
     v
application.jmod
     |
     +------ JDK jmods
     |
     v
jlink
     |
     v
custom runtime image
     |
     v
java / generated launcher
~~~

Mỗi công cụ có trách nhiệm riêng: javac tạo đầu ra biên dịch, jmod đóng gói module, jlink tạo runtime image và java thực thi ứng dụng.

## 11. Checklist khi tạo và dùng JMOD

- Xác định rõ có cần JMOD hay chỉ cần JAR cho mục đích phân phối.
- Biên dịch module trước bằng javac và kiểm tra module-info.class.
- Dùng --class-path trỏ đến thư mục hoặc JAR chứa đầu ra đã biên dịch.
- Chọn đúng --module-version và --main-class nếu quy trình cần metadata đó.
- Chỉ thêm section native/config/header/legal/man khi module thực sự cần.
- Chọn đúng target platform nếu archive chứa thành phần native.
- Dùng jmod describe để xác nhận module name và descriptor.
- Dùng jmod list để kiểm tra entry đã đóng gói.
- Dùng jmod extract khi cần kiểm tra nội dung section.
- Đưa JMOD ứng dụng cùng JDK jmods phù hợp vào module path của jlink.
- Chọn module gốc bằng --add-modules và kiểm tra dependency closure.
- Chạy thử runtime image đã tạo trên đúng nền tảng đích.
- Không dùng JMOD trực tiếp như JAR trên classpath hoặc với java -jar.
- Giữ các công cụ JDK và JMOD cùng một release/vendor tương thích trong quy trình build.

## 12. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| JMOD | Định dạng archive chuyên dụng để đóng gói module cho công cụ JDK |
| JMOD file | Tệp có phần mở rộng .jmod |
| Section | Nhóm nội dung như classes, bin, conf, include, legal, lib và man |
| Exploded module | Module đã biên dịch nằm trong một thư mục |
| module-info.class | Module descriptor đã biên dịch |
| jmod create | Tạo JMOD từ đầu vào đã biên dịch |
| jmod describe | Hiển thị thông tin module |
| jmod list | Liệt kê các entry |
| jmod extract | Giải nén các section |
| jmod hash | Ghi hash ràng buộc module theo quy tắc công cụ |
| jlink | Tạo runtime image từ các module |
| Runtime image | Môi trường chạy Java đã được liên kết theo tập module chọn trước |

JMOD là định dạng đóng gói phục vụ các công cụ JDK và quá trình tạo runtime image. Hãy nhớ đúng vai trò của từng bước: **javac biên dịch module, jmod đóng gói module, jlink tạo runtime image, và java chạy ứng dụng từ runtime image đó**.
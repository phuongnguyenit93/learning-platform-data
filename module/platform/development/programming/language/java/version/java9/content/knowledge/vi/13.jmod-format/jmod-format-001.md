# Phân biệt JMOD với modular JAR

Trong Java Platform Module System (JPMS), **modular JAR** và **JMOD** đều có thể đóng gói một module Java, nhưng phục vụ những giai đoạn khác nhau của quá trình build và triển khai. Modular JAR là dạng archive tiêu chuẩn để phân phối và chạy module. JMOD là định dạng đóng gói chuyên dụng của JDK, đặc biệt hữu ích khi tạo runtime image bằng công cụ **jlink**.

Điểm cần nhớ: **dùng modular JAR khi ứng dụng cần nạp module lúc chạy; dùng JMOD khi cần đóng gói module cùng các thành phần bổ sung để công cụ JDK, đặc biệt là jlink, tạo runtime image.** JMOD không phải một modular JAR chỉ đổi phần mở rộng.

## 1. Modular JAR là gì?

Modular JAR là một tệp JAR tiêu chuẩn có chứa **module-info.class** ở thư mục gốc của archive. File này được biên dịch từ **module-info.java** và mô tả module: tên module, các module phụ thuộc, package được export, package được open, service được sử dụng hoặc cung cấp.

Một modular JAR thường chứa:

- **module-info.class**.
- Các class đã biên dịch.
- Resource mà module cần khi chạy.
- Metadata tiêu chuẩn của JAR, chẳng hạn manifest nếu dự án sử dụng.

Ví dụ cấu trúc sau khi biên dịch:

~~~text
out/
├── module-info.class
└── com/
    └── example/
        └── greeter/
            └── Main.class
~~~

Khi đóng gói toàn bộ nội dung của thư mục **out** thành JAR, **module-info.class** nằm ở gốc archive. Java có thể nhận diện JAR đó là một explicit module khi JAR nằm trên module path.

Modular JAR được dùng trực tiếp trong các bước phổ biến:

- Biên dịch module phụ thuộc bằng **javac --module-path**.
- Chạy ứng dụng theo module system bằng **java --module-path**.
- Phân phối thư viện hoặc ứng dụng Java dưới dạng JAR.
- Kiểm tra descriptor bằng **jar --describe-module**.

Ví dụ chạy module từ thư mục **mods**:

~~~bash
java --module-path mods --module com.example.greeter/com.example.greeter.Main
~~~

Ở đây **com.example.greeter** là tên module; phần sau dấu gạch chéo là lớp có phương thức **main**. Module được tìm thấy từ các artifact trên module path.

**Lưu ý về JAR không có descriptor:** một JAR không chứa **module-info.class** vẫn có thể được đặt trên module path và được xử lý như automatic module theo quy tắc đặt tên của JPMS. Tuy nhiên, đó không phải explicit modular JAR. Nếu đặt một JAR lên classpath, **module-info.class** không được dùng để tạo module; các lớp của JAR thuộc unnamed module.

## 2. JMOD là gì?

JMOD là định dạng archive chuyên dụng do công cụ **jmod** của JDK quản lý. Một JMOD cũng đóng gói nội dung của module, nhưng ngoài class và resource, nó có thể chứa những thành phần mà JAR thông thường không có cấu trúc chuyên biệt để quản lý, ví dụ:

- Native libraries.
- Native command hoặc executable đi kèm module.
- File cấu hình.
- Header files.
- Legal notices.
- Man pages.

JMOD có các section riêng cho những nhóm nội dung này. Section **classes** chứa class và resource của module; các section khác chỉ xuất hiện khi gói JMOD có các thành phần tương ứng. Vì vậy, JMOD phù hợp với cách đóng gói các module của JDK và các module cần thêm thành phần phục vụ việc tạo runtime image.

Công cụ **jmod** hỗ trợ các thao tác chính:

- **jmod create**: tạo JMOD từ nội dung module.
- **jmod describe**: xem descriptor và thông tin module.
- **jmod list**: liệt kê nội dung archive.
- **jmod extract**: giải nén nội dung JMOD.
- **jmod hash**: ghi hash phụ thuộc module khi quy trình đóng gói cần dùng.

Các JDK hiện đại tiếp tục cung cấp thư mục **jmods** bên trong JDK distribution. Những JMOD này là đầu vào quan trọng khi **jlink** lắp ghép một runtime image tùy chỉnh.

JMOD chủ yếu phục vụ đóng gói và liên kết module trong toolchain. Java launcher không nạp tệp **.jmod** trực tiếp như một module runtime. Khi ứng dụng cần module để chạy, hãy cung cấp modular JAR hoặc runtime image đã được tạo bằng **jlink**.

## 3. So sánh trực tiếp

| Tiêu chí | Modular JAR | JMOD |
|---|---|---|
| Phần mở rộng | **.jar** | **.jmod** |
| Định dạng | JAR tiêu chuẩn | Định dạng đóng gói riêng do **jmod** quản lý |
| Mô tả module | **module-info.class** ở gốc JAR | Descriptor nằm trong nội dung module của JMOD |
| Nội dung chính | Class, resource và metadata JAR | Class, resource và các section bổ sung như native libraries, commands, config, headers, legal notices, man pages |
| Mục đích điển hình | Phân phối thư viện/ứng dụng và nạp module khi chạy | Đóng gói module cho toolchain, đặc biệt là tạo runtime image |
| Công cụ thường dùng | **jar**, **javac**, **java** | **jmod**, **jlink** |
| Nạp trực tiếp bằng Java launcher | Có thể nạp từ runtime module path | Không nạp trực tiếp từ file JMOD |
| Phù hợp với | Module Java thông thường cần phân phối hoặc chạy | Module cần mang thêm thành phần hệ thống hoặc được đóng gói để link |

Cả hai đều có thể đại diện cho một module trong hệ sinh thái JPMS, nhưng không thể thay thế cho nhau ở mọi bước. Khác biệt quan trọng nhất là mục đích sử dụng và khả năng đóng gói thành phần bổ sung của JMOD.

## 4. Hai luồng sử dụng khác nhau

### 4.1. Modular JAR: phân phối và chạy module

Luồng phổ biến của một thư viện hoặc ứng dụng Java:

~~~text
module-info.java + source code
          |
          | javac
          v
module-info.class + class files
          |
          | jar
          v
modular JAR (.jar)
          |
          | java --module-path
          v
Java application chạy theo JPMS
~~~

Modular JAR là lựa chọn phù hợp khi cần gửi một module cho ứng dụng khác, lưu trong kho artifact hoặc đưa trực tiếp lên module path để chạy.

### 4.2. JMOD: đóng gói và tạo runtime image

Luồng tạo runtime image tùy chỉnh:

~~~text
module-info.java + source code
          |
          | javac
          v
module-info.class + class files
          |
          | jmod create
          v
JMOD (.jmod)
          |
          | jlink
          v
Custom runtime image
          |
          | java nằm trong image
          v
Ứng dụng chạy trên runtime image đó
~~~

**jlink** phân tích module và các phụ thuộc cần thiết, sau đó tạo một runtime image chứa những module được chọn cùng runtime cần thiết. JMOD là một đầu vào phù hợp cho bước link này, đặc biệt khi module có native libraries hoặc các section bổ sung.

**jlink** cũng làm việc với module được cung cấp dưới dạng modular JAR hoặc exploded module khi phù hợp. Vì vậy, không phải mọi module đều bắt buộc chuyển thành JMOD. Chọn JMOD khi cần khả năng đóng gói bổ sung của định dạng này hoặc khi quy trình build/runtime image yêu cầu nó.

## 5. Ví dụ: tạo modular JAR và JMOD từ cùng một module

Ví dụ dùng cú pháp JDK hiện đại (Java 17+). Giả sử source có cấu trúc:

~~~text
src/
├── module-info.java
└── com/
    └── example/
        └── greeter/
            └── Main.java
~~~

Nội dung **src/module-info.java**:

~~~java
module com.example.greeter {
}
~~~

Nội dung **src/com/example/greeter/Main.java**:

~~~java
package com.example.greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from modular JAR!");
    }
}
~~~

### Bước 1: biên dịch module

Tạo các thư mục **out**, **mods** và **jmods** trước khi chạy lệnh:

~~~bash
javac -d out src/module-info.java src/com/example/greeter/Main.java
~~~

Sau khi biên dịch, thư mục **out** có **module-info.class** và class của **Main**.

### Bước 2: tạo và chạy modular JAR

~~~bash
jar --create --file mods/com.example.greeter.jar -C out .
java --module-path mods --module com.example.greeter/com.example.greeter.Main
~~~

Kết quả:

~~~text
Hello from modular JAR!
~~~

Có thể kiểm tra module descriptor:

~~~bash
jar --describe-module --file mods/com.example.greeter.jar
~~~

### Bước 3: tạo và kiểm tra JMOD

Dùng chính nội dung đã biên dịch để tạo JMOD:

~~~bash
jmod create --class-path out jmods/com.example.greeter.jmod
~~~

Xem descriptor và danh sách nội dung:

~~~bash
jmod describe jmods/com.example.greeter.jmod
jmod list jmods/com.example.greeter.jmod
~~~

Các lệnh này cho thấy module được đóng gói trong JMOD và những entry có trong archive. JMOD vẫn chứa nội dung class/resource của module; định dạng này còn cho phép bổ sung các section khác khi quy trình đóng gói cần chúng.

### Bước 4: dùng JMOD để tạo runtime image

Module hệ thống của JDK nằm trong **$JAVA_HOME/jmods**. Thêm thư mục **jmods** chứa JMOD vừa tạo vào module path của **jlink**.

Trên Linux/macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:jmods" --add-modules com.example.greeter --output runtime
runtime/bin/java --module com.example.greeter/com.example.greeter.Main
~~~

Trên Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;jmods" --add-modules com.example.greeter --output runtime
.\runtime\bin\java.exe --module com.example.greeter/com.example.greeter.Main
~~~

Kết quả chạy ứng dụng từ runtime image:

~~~text
Hello from modular JAR!
~~~

Trong ví dụ, JMOD là đầu vào cho **jlink**. Chương trình được chạy bằng Java launcher nằm trong runtime image đã tạo; launcher không chạy trực tiếp file **com.example.greeter.jmod**.

## 6. Chọn định dạng nào?

Chọn **modular JAR** khi:

- Bạn phát triển thư viện hoặc ứng dụng Java thông thường.
- Artifact cần được phân phối qua kho Maven/Gradle hoặc chuyển cho ứng dụng khác.
- Module cần được biên dịch và nạp lúc chạy qua module path.
- Nội dung chủ yếu là class và resource Java.

Chọn **JMOD** khi:

- Bạn cần đóng gói module cùng native libraries, commands, configuration, header files hoặc các section bổ sung.
- Bạn đang xây dựng một runtime image tùy chỉnh bằng **jlink**.
- Quy trình đóng gói module của JDK hoặc toolchain yêu cầu JMOD.

Nếu chỉ có class và resource Java, modular JAR thường là artifact phân phối đơn giản và phù hợp hơn. Không cần tạo JMOD cho mọi thư viện hoặc ứng dụng. Nếu JMOD chứa native code, các thành phần đó phải phù hợp với nền tảng đích của runtime image.

## 7. Những nhầm lẫn thường gặp

1. **Đổi tên file JAR thành .jmod không tạo ra JMOD.** JMOD có định dạng riêng và phải được tạo bằng **jmod**.
2. **Không đưa JMOD vào runtime module path của ứng dụng.** Java launcher không nạp trực tiếp file JMOD; hãy dùng modular JAR hoặc chạy ứng dụng từ runtime image do **jlink** tạo.
3. **Không phải JAR nào trên module path cũng là explicit modular JAR.** JAR không có **module-info.class** có thể được xử lý như automatic module; cần phân biệt với module có descriptor tường minh.
4. **Không nhầm jmod với jlink.** **jmod** quản lý định dạng JMOD; **jlink** ghép các module và phụ thuộc để tạo runtime image.
5. **Không giả định JMOD luôn cần thiết.** Modular JAR đáp ứng tốt phần lớn nhu cầu phân phối module Java thông thường.

## 8. Kết luận

Modular JAR là dạng JAR tiêu chuẩn có module descriptor, phù hợp để phân phối và nạp module khi ứng dụng chạy. JMOD là định dạng đóng gói chuyên dụng của JDK, có thể mang thêm native code và các thành phần hệ thống, chủ yếu phục vụ toolchain và bước tạo runtime image bằng **jlink**.

Hãy quyết định theo nơi artifact được sử dụng: **module cần được ứng dụng nạp lúc chạy → modular JAR; module cần được đóng gói để link thành runtime image → cân nhắc JMOD.**
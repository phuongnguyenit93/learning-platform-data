# Source encoding với javac

Source encoding là cách diễn giải các byte trong tệp mã nguồn thành ký tự Unicode mà trình biên dịch Java có thể đọc. Khi encoding của tệp và encoding mà javac sử dụng không khớp, chương trình có thể báo lỗi ký tự không hợp lệ hoặc biên dịch thành công nhưng các chuỗi tiếng Việt bị sai dấu (mojibake).

Với javac, cách làm rõ ràng và ổn định là lưu mã nguồn bằng UTF-8 và truyền tùy chọn **-encoding UTF-8** khi biên dịch. Tùy chọn này nói cho compiler biết cách giải mã các tệp nguồn; nó không chuyển đổi byte của tệp và cũng không quyết định encoding của dữ liệu chương trình ghi ra terminal hay file.

## 1. Encoding xảy ra ở bước nào?

Một tệp **.java** trên đĩa là một dãy byte. Trước khi phân tích cú pháp, javac cần giải mã dãy byte đó theo một character set để nhận được chuỗi ký tự. Luồng xử lý khái quát:

1. Editor hoặc công cụ tạo tệp và lưu các ký tự thành byte theo một encoding, ví dụ UTF-8.
2. javac đọc byte và giải mã theo encoding được chỉ định bằng **-encoding**; nếu không chỉ định, compiler dùng charset mặc định của môi trường/JDK.
3. Sau khi giải mã, compiler thực hiện các bước xử lý ký tự Unicode, phân tích từ vựng, cú pháp, kiểm tra kiểu và sinh bytecode.
4. Khi chạy, JVM đọc các hằng chuỗi đã được lưu trong class file. Encoding nguồn không còn được dùng để giải mã lại tệp .java.

Điểm cần nhớ: **encoding của source file là quyết định ở thời điểm biên dịch**. Một ứng dụng đã biên dịch không cần giữ lại encoding ban đầu của tệp .java để hiển thị chuỗi.

## 2. Tùy chọn -encoding của javac

Cú pháp:

~~~bash
javac -encoding <encoding> <source-files>
~~~

Ví dụ:

~~~bash
javac -encoding UTF-8 Chao.java
~~~

Tùy chọn **-encoding** chỉ định character set mà javac dùng để đọc các tệp nguồn trong lượt biên dịch. Tên charset thường không phân biệt chữ hoa/chữ thường. Một số tên hay gặp:

| Encoding | Trường hợp sử dụng |
|---|---|
| UTF-8 | Lựa chọn khuyến nghị cho dự án Java mới; hỗ trợ Unicode và tương thích tốt giữa các hệ điều hành |
| windows-1252 | Một số mã nguồn Windows/Western Europe cũ |
| Shift_JIS | Một số hệ thống Nhật Bản cũ |
| GBK | Một số hệ thống Trung Quốc cũ |
| ISO-8859-1 | Dự án hoặc dữ liệu legacy dùng Latin-1 |

Chỉ chọn encoding phù hợp với byte thực tế của tệp. Không thể sửa một tệp đang lưu bằng Windows-1252 chỉ bằng cách đổi tên encoding trong cấu hình nếu byte chưa được chuyển đổi.

Có thể xem các tùy chọn compiler bằng:

~~~bash
javac --help
~~~

Tùy chọn **-encoding** có thể được dùng cùng với các tùy chọn khác như **-d**, **-classpath**, **--release** và **-Xlint**:

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:all -d out src/Chao.java
~~~

Ở ví dụ này, **--release 17** chọn API và mức tương thích ngôn ngữ/bytecode Java 17; **-encoding UTF-8** độc lập với lựa chọn release và điều khiển cách đọc source file.

## 3. Charset mặc định thay đổi theo phiên bản JDK

Nếu không truyền **-encoding**, javac sử dụng charset mặc định của môi trường Java. Điều này có thể làm kết quả biên dịch khác nhau giữa các máy.

- Trước JDK 18, charset mặc định thường phụ thuộc hệ điều hành, locale và cấu hình máy. Một máy Windows có thể dùng một code page địa phương trong khi máy Linux dùng UTF-8.
- Từ JDK 18, theo JEP 400, UTF-8 trở thành charset mặc định của Java trên hầu hết môi trường triển khai chuẩn. Có chế độ tương thích để giữ hành vi mặc định cũ trong một số trường hợp.
- Dù dùng JDK 18 trở lên, chỉ định **-encoding UTF-8** vẫn giúp ý định của dự án được ghi rõ trong lệnh build và tránh phụ thuộc vào cấu hình môi trường.

Không nên dựa vào charset mặc định để quyết định encoding của source code. Cấu hình tường minh giúp IDE, máy CI, máy của lập trình viên và máy build release đọc cùng một nội dung.

## 4. Ví dụ thực hành với tiếng Việt

Tạo tệp **Chao.java** và lưu bằng UTF-8:

~~~java
public class Chao {
    public static void main(String[] args) {
        String greeting = "Xin chào, thế giới!";
        String vietnamese = "Tiếng Việt có đủ dấu: ă â đ ê ô ơ ư";
        System.out.println(greeting);
        System.out.println(vietnamese);
    }
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 Chao.java
~~~

Chạy:

~~~bash
java Chao
~~~

Stdout trên terminal có khả năng hiển thị UTF-8:

~~~text
Xin chào, thế giới!
Tiếng Việt có đủ dấu: ă â đ ê ô ơ ư
~~~

Nếu compiler đọc tệp UTF-8 bằng một charset không phù hợp, có thể xảy ra hai loại vấn đề:

- Compiler báo lỗi như unmappable character hoặc malformed input khi một dãy byte không hợp lệ theo charset được chọn.
- Compiler vẫn giải mã được byte nhưng thành ký tự khác. Khi đó mã nguồn có thể biên dịch thành công, song chuỗi trong chương trình đã bị sai ngay từ lúc biên dịch.

Ví dụ, nếu byte UTF-8 của từ **chào** bị diễn giải như một encoding đơn byte khác, chuỗi có thể biến thành dạng mojibake như **chÃ o**. Đây là lỗi giải mã source, không phải lỗi của System.out.println.

## 5. Phân biệt source encoding với output encoding

Ba việc sau độc lập với nhau:

| Thành phần | Điều khiển điều gì? | Cách cấu hình thường dùng |
|---|---|---|
| Source encoding | javac đọc byte của tệp .java như thế nào | javac -encoding UTF-8 |
| Runtime file/resource encoding | Chương trình đọc hoặc ghi nội dung file/resource như thế nào | Chỉ định Charset trong API I/O |
| Terminal/console encoding | Terminal hiển thị byte stdout như thế nào | Cấu hình terminal, locale và môi trường chạy |

Vì vậy, chương trình có thể được biên dịch đúng với **-encoding UTF-8** nhưng terminal vẫn hiển thị sai nếu console không giải mã output theo UTF-8. Ngược lại, terminal UTF-8 không thể sửa một chuỗi đã bị javac giải mã sai từ source file.

Khi ghi file, nên chỉ định charset rõ ràng thay vì phụ thuộc mặc định:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class WriteUtf8 {
    public static void main(String[] args) throws Exception {
        Path output = Path.of("message.txt");
        Files.writeString(output, "Xin chào từ Java", StandardCharsets.UTF_8);
    }
}
~~~

Ở đây **StandardCharsets.UTF_8** điều khiển encoding của file được ghi tại runtime. Nó không thay thế tùy chọn **javac -encoding UTF-8**.

## 6. Unicode trong mã nguồn Java

Java hỗ trợ Unicode trong string literal, character literal, comment và identifier theo các quy tắc của ngôn ngữ. Với source file UTF-8, có thể viết ký tự trực tiếp:

~~~java
String city = "Hồ Chí Minh";
char letter = 'đ';
~~~

Java cũng có cú pháp Unicode escape với dạng **\\uXXXX**, trong đó XXXX là bốn chữ số hex biểu diễn một UTF-16 code unit. Ví dụ:

~~~java
String cafe = "Caf\u00E9";
System.out.println(cafe);
~~~

Stdout:

~~~text
Café
~~~

Unicode escape được xử lý trong giai đoạn dịch ký tự nguồn trước khi phân tích token. Vì thế, escape có thể tạo ra ký tự mang ý nghĩa cú pháp, kể cả trong trường hợp người viết không mong đợi. Không nên dùng escape một cách tùy tiện để thay thế cho việc thống nhất UTF-8.

Với ký tự nằm ngoài Basic Multilingual Plane, Java biểu diễn trong UTF-16 bằng một cặp surrogate. Source UTF-8 cho phép lưu trực tiếp các ký tự đó; khi cần xử lý theo Unicode code point, dùng các API như **String.codePoints()** thay vì giả định mỗi ký tự hiển thị tương ứng với một giá trị char.

## 7. Đặt encoding trong quy trình build

Điều quan trọng là cấu hình encoding ở nơi thực sự gọi javac. Nếu chỉ cấu hình editor lưu UTF-8 nhưng CI chạy compiler với encoding mặc định khác, build vẫn có thể lỗi.

### Biên dịch trực tiếp bằng command line

Giả sử cấu trúc thư mục:

~~~text
project/
  src/
    Chao.java
  out/
~~~

Linux/macOS:

~~~bash
mkdir -p out
javac -encoding UTF-8 -d out src/Chao.java
java -cp out Chao
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/Chao.java
java -cp out Chao
~~~

Thư mục **out** là nơi javac ghi class file. Tùy chọn **-d** không liên quan đến source encoding.

### Maven

Trong Maven, khai báo encoding ở project và compiler plugin để cấu hình được thể hiện rõ:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

**project.build.sourceEncoding** là property chuẩn thường được các plugin Maven dùng để xử lý nội dung nguồn và tài nguyên. Cấu hình **encoding** trong maven-compiler-plugin đặt rõ charset mà compiler dùng cho source files. Trong dự án thực tế, hãy dùng phiên bản plugin đã được tổ chức chuẩn hóa và quản lý.

Chạy build:

~~~bash
mvn clean compile
~~~

### Gradle Groovy DSL

Trong **build.gradle**:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

### Gradle Kotlin DSL

Trong **build.gradle.kts**:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

Cấu hình trên áp dụng cho các task biên dịch Java. Nếu dự án có nhiều module, hãy đặt ở convention plugin hoặc cấu hình dùng chung để các module không vô tình dùng encoding khác nhau.

## 8. Chẩn đoán lỗi encoding

### Trường hợp 1: Compiler báo unmappable character

Nguyên nhân thường gặp là tệp được lưu bằng một charset nhưng javac đang giải mã bằng charset khác.

Cách xử lý:

1. Kiểm tra encoding thực tế của tệp trong editor.
2. Xác nhận lệnh build đang dùng **-encoding** nào hoặc build tool đang đặt **options.encoding** ra sao.
3. Nếu dự án thống nhất UTF-8, chuyển đổi tệp sang UTF-8 bằng editor hoặc công cụ chuyển đổi có kiểm soát.
4. Biên dịch lại với **-encoding UTF-8**.
5. Kiểm tra cả những source file khác được compiler đọc trong cùng lượt build.

Đừng chỉ đổi cấu hình sang một charset bất kỳ để làm mất thông báo lỗi. Hãy xác định encoding thực tế trước, nếu không có thể biến lỗi hiển thị rõ thành dữ liệu sai nhưng vẫn biên dịch được.

### Trường hợp 2: Biên dịch thành công nhưng tiếng Việt bị sai dấu

Đây là trường hợp compiler đã đọc byte thành các ký tự hợp lệ nhưng các ký tự đó không phải nội dung mong muốn.

Cách xử lý:

1. Mở source file và xác nhận nội dung hiển thị đúng trong editor.
2. Xem trạng thái encoding của tệp, ví dụ UTF-8.
3. Kiểm tra encoding trong lệnh javac hoặc cấu hình Maven/Gradle.
4. Xóa output biên dịch cũ rồi build lại để chắc chắn class file được sinh từ source đã sửa.
5. Chạy chương trình trong terminal được cấu hình hiển thị UTF-8.

Nếu output terminal sai nhưng nội dung source và class file đã đúng, kiểm tra console encoding riêng thay vì tiếp tục thay đổi source encoding.

### Trường hợp 3: Máy lập trình chạy được nhưng CI thất bại

Nguyên nhân phổ biến là máy local và CI có charset mặc định khác nhau, hoặc CI dùng một lệnh build khác IDE.

Cách xử lý:

- Đặt source file encoding thống nhất trong repository, khuyến nghị UTF-8.
- Đặt compiler encoding rõ ràng trong Maven/Gradle hoặc command line.
- Đảm bảo CI dùng cùng build script với lập trình viên.
- Thực hiện clean build trên môi trường CI.
- Kiểm tra các module hoặc task biên dịch riêng có cấu hình ghi đè hay không.

### Trường hợp 4: Lỗi ngay ký tự đầu tiên của file

Nếu compiler báo ký tự không hợp lệ ngay đầu tệp, kiểm tra xem tệp có byte order mark (BOM) hoặc ký tự vô hình ở đầu hay không. Hãy kiểm tra bằng editor hoặc công cụ xem byte, rồi lưu lại theo encoding mà dự án quy định. Tránh xóa byte đầu một cách máy móc khi chưa xác định định dạng file.

## 9. Quy trình chuẩn hóa source encoding cho dự án

Một quy trình dễ duy trì:

1. Chọn một encoding thống nhất cho mã nguồn; với dự án mới, chọn UTF-8.
2. Cấu hình editor và formatter lưu tệp Java bằng UTF-8.
3. Cấu hình compiler bằng **-encoding UTF-8**, hoặc cấu hình tương đương trong Maven/Gradle.
4. Chuyển đổi các tệp legacy sang UTF-8 một lần, kiểm tra diff để phát hiện thay đổi ký tự ngoài dự kiến.
5. Đặt CI chạy clean build và dùng cùng build script với local.
6. Kiểm tra terminal và encoding của file I/O riêng khi chương trình đọc/ghi dữ liệu văn bản.
7. Ghi quy ước encoding trong tài liệu dự án để thành viên mới dùng cùng cấu hình.

Không trộn nhiều encoding trong cùng một lượt javac nếu có thể tránh. Tùy chọn **-encoding** là một lựa chọn chung cho các source file được đọc trong lượt biên dịch. Nếu repository có mã nguồn legacy ở nhiều encoding, nên chuyển đổi về một chuẩn hoặc tách quy trình build có kiểm soát trước khi hợp nhất.

## 10. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| JDK 18+ luôn khiến mọi dự án không cần -encoding | Charset mặc định UTF-8 giúp giảm khác biệt môi trường, nhưng cấu hình tường minh vẫn làm build dễ tái lập |
| -encoding chuyển đổi source file sang UTF-8 | Nó chỉ chỉ định cách javac giải mã byte; muốn chuyển đổi phải dùng editor hoặc công cụ chuyển mã |
| Terminal UTF-8 bảo đảm javac đọc source đúng | Terminal chỉ ảnh hưởng cách hiển thị output; javac có bước giải mã source riêng |
| Biên dịch thành công nghĩa là encoding đúng | Byte có thể giải mã thành ký tự hợp lệ nhưng sai nội dung |
| --release 17 chọn encoding tương ứng với Java 17 | --release chọn mức ngôn ngữ/API/bytecode; -encoding điều khiển source charset |
| String trong class file cần biết encoding của file .java gốc | JVM dùng dữ liệu đã được compiler ghi vào class file; source encoding không được dùng lại lúc chạy |

## 11. Ghi nhớ

- Lưu mã nguồn Java bằng UTF-8 và đặt **javac -encoding UTF-8** trong quy trình build.
- Encoding của source file, encoding của file I/O runtime và encoding của terminal là ba cấu hình khác nhau.
- JDK 18 trở lên mặc định UTF-8 theo JEP 400; trước đó mặc định thường phụ thuộc môi trường.
- Nếu compiler báo unmappable character, kiểm tra encoding thực tế của tệp và cấu hình compiler trước khi chuyển đổi.
- Nếu biên dịch thành công nhưng tiếng Việt sai dấu, kiểm tra cả source decoding, output class cũ và terminal.
- Dùng Maven/Gradle configuration để local và CI biên dịch theo cùng một quy ước.
- Unicode escape là cú pháp của Java; với dự án hiện đại, lưu source UTF-8 thường dễ đọc và dễ bảo trì hơn.
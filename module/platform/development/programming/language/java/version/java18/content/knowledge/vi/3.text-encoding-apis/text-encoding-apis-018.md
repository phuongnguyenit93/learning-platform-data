# Biên dịch mã nguồn tiếng Việt với javac -encoding UTF-8 và phân biệt mã hóa nguồn với mã hóa dữ liệu

> **Chương:** API văn bản  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Cấu hình compiler đọc mã nguồn Java tiếng Việt bằng UTF-8; hiểu phạm vi của `javac -encoding`; phân biệt encoding của source file với encoding của file dữ liệu, stdin, stdout và giao thức; áp dụng cấu hình tường minh trên JDK hiện đại.

## 1. Vì sao cần phân biệt mã hóa mã nguồn và mã hóa dữ liệu?

Một dự án Java có thể chứa tiếng Việt ở nhiều nơi:

- Comment và Javadoc trong file `.java`.
- String literal trong mã nguồn, ví dụ `"Xin chào"`.
- File cấu hình, CSV, JSON, XML hoặc văn bản đọc lúc chạy.
- Dữ liệu nhận từ HTTP, database, message broker hoặc stdin.
- Nội dung ghi ra file, socket, stdout hoặc stderr.

Những dữ liệu này không đi qua cùng một bước xử lý. Compiler cần decode byte của file nguồn thành ký tự để phân tích cú pháp. Khi chương trình chạy, API I/O lại decode hoặc encode các byte dữ liệu theo charset riêng.

| Vị trí | Bước chuyển đổi | Cách chỉ định |
|---|---|---|
| File mã nguồn `.java` | Byte trên đĩa → ký tự compiler đọc | `javac -encoding UTF-8` |
| String literal trong source | Ký tự source → giá trị String trong class | Compiler xử lý theo quy tắc ngôn ngữ |
| File văn bản lúc chạy | Byte file ↔ String | `Files.readString(path, UTF_8)`, `Files.writeString(path, text, UTF_8)` |
| Input stream | Byte → ký tự | `InputStreamReader(stream, UTF_8)` |
| Output stream | Ký tự → byte | `OutputStreamWriter(stream, UTF_8)` |
| HTTP hoặc giao thức khác | Byte ↔ text theo protocol metadata | Tuân thủ charset mà protocol quy định |

`javac -encoding UTF-8` chỉ giải quyết việc compiler đọc source file. Nó không tự cấu hình cách ứng dụng đọc CSV, ghi log, xử lý HTTP body hoặc hiển thị tiếng Việt trên terminal.

Từ JDK 18, JEP 400 đặt UTF-8 làm default charset của Java trên cấu hình mặc định. Thay đổi này giúp giảm khác biệt giữa hệ điều hành, nhưng không làm cho mọi boundary dữ liệu tự động có cùng encoding. Với source file và dữ liệu có định dạng xác định, cấu hình tường minh vẫn là cách dễ kiểm soát và tái hiện.

## 2. Compiler đọc file Java như thế nào?

Một file Java trên đĩa là chuỗi byte. Trước khi phân tích cú pháp, compiler phải chuyển byte đó thành ký tự.

Ví dụ file `src/VietnameseGreeting.java` được lưu bằng UTF-8:

~~~java
public class VietnameseGreeting {
    public static void main(String[] args) {
        // Lời chào bằng tiếng Việt
        String message = "Xin chào, Java!";
        System.out.println(message);
    }
}
~~~

Các ký tự ASCII như chữ cái tiếng Anh có byte giống nhau trong nhiều charset tương thích ASCII. Ký tự tiếng Việt có dấu thường cần nhiều byte trong UTF-8. Nếu compiler dùng charset khác với charset thực tế của file, phần tiếng Việt có thể bị đọc sai hoặc gây lỗi biên dịch.

Tùy charset được chọn, lỗi có thể biểu hiện theo hai cách:

- Byte không hợp lệ theo charset: compiler báo lỗi đọc/giải mã hoặc ký tự không thể biểu diễn.
- Byte hợp lệ nhưng được diễn giải theo charset khác: compiler có thể vẫn biên dịch, nhưng String literal/comment trở thành mojibake.

Do đó, việc compile thành công chưa chứng minh source đã được đọc bằng đúng encoding.

## 3. Dùng javac -encoding UTF-8

### 3.1. Cú pháp

Tùy chọn `-encoding` chỉ định charset dùng để đọc source file:

~~~shell
javac -encoding UTF-8 -d out src/VietnameseGreeting.java
~~~

Trong đó:

- `-encoding UTF-8` yêu cầu compiler decode source file bằng UTF-8.
- `-d out` chỉ định thư mục chứa class file.
- Đường dẫn sau cùng là source file cần compile.

Chạy chương trình:

~~~shell
java -cp out VietnameseGreeting
~~~

Kết quả:

~~~text
Xin chào, Java!
~~~

Ví dụ trên giả định file được lưu thực sự bằng UTF-8 và terminal hiển thị được tiếng Việt. Nếu source được lưu bằng charset khác, cần chuyển file về UTF-8 hoặc chọn đúng encoding tương ứng; không chỉ đổi cờ compiler để che sự không nhất quán trong repository.

### 3.2. Compile nhiều source file

Có thể truyền nhiều source file trong cùng một lệnh:

~~~shell
javac -encoding UTF-8 -d out src/Customer.java src/CustomerService.java src/Main.java
~~~

Một tùy chọn encoding được áp dụng cho các source file mà compiler đọc trong lần biên dịch đó. Vì vậy, dự án nên thống nhất source file cùng encoding. Nếu repository chứa file nguồn trộn UTF-8 và encoding khác, hãy chuẩn hóa file trước khi build thay vì kỳ vọng một lần gọi `javac` tự nhận diện từng file.

### 3.3. Kết hợp với --release

`-encoding` và `--release` giải quyết hai vấn đề độc lập:

~~~shell
javac -encoding UTF-8 --release 25 -d out src/VietnameseGreeting.java
~~~

- `-encoding UTF-8` xác định cách đọc byte source file.
- `--release 25` xác định source language, class file target và API platform mà compiler cho phép sử dụng theo Java 25.

`--release` không thay thế `-encoding`. Ngược lại, `-encoding` không quyết định phiên bản Java hoặc API mà source được phép gọi.

Ví dụ dùng release 25 chỉ phù hợp khi compiler JDK hỗ trợ release đó. Hãy chọn release baseline theo chính sách hỗ trợ của dự án và JDK toolchain đang cài; không giữ một target cũ chỉ vì bài học ban đầu được viết cho Java 18.

### 3.4. Nếu bỏ -encoding thì sao?

Nếu không truyền `-encoding`, `javac` dùng charset mặc định của môi trường/toolchain theo tài liệu của compiler. JEP 400 làm UTF-8 trở thành default charset trên JDK 18+ theo cấu hình mặc định, nên các JDK hiện đại thường có hành vi thống nhất hơn.

Tuy nhiên, dự án vẫn nên ghi `-encoding UTF-8` rõ ràng vì:

- Người đọc biết source file được kỳ vọng lưu bằng encoding nào.
- Build không phụ thuộc giả định ngầm về môi trường.
- IDE, local build và CI dễ đồng bộ cấu hình.
- Khi gặp compiler option hoặc compatibility setting, source encoding vẫn được xác định tại lệnh build.

Không dùng `-Dfile.encoding=UTF-8` như cách thay thế cho `javac -encoding UTF-8`. Một property runtime không diễn đạt rõ hợp đồng encoding của source file; tùy chọn compiler mới là nơi chỉ định trực tiếp việc đọc source.

## 4. Ví dụ khi source UTF-8 nhưng compiler đọc sai charset

Giả sử source file chứa literal `"café"` và được lưu bằng UTF-8. Nếu compiler đọc byte bằng một charset khác, các byte của ký tự có dấu có thể biến thành ký tự sai.

Với một charset single-byte như Windows-1252, byte UTF-8 của `é` là `C3 A9` có thể bị diễn giải thành hai ký tự `Ã©`. Compiler vẫn có thể chấp nhận các ký tự đó trong String literal. Khi chạy, chương trình in ra chuỗi sai dù source code không có lỗi cú pháp.

Một tình huống khác là dùng US-ASCII để đọc source UTF-8 chứa ký tự ngoài ASCII. Compiler có thể báo lỗi vì byte nguồn không thể được decode theo charset đã chỉ định.

Cách sửa đúng:

1. Xác định encoding thực tế của file source.
2. Chuyển source file về UTF-8 nếu đó là chuẩn của repository.
3. Compile bằng `javac -encoding UTF-8`.
4. Kiểm tra output String literal sau khi chạy.
5. Kiểm tra terminal riêng nếu output vẫn hiển thị sai.

Đừng thay chữ tiếng Việt bằng chuỗi escape chỉ để build qua lỗi encoding. Cần xử lý đúng encoding của file nguồn.

## 5. Source encoding không được lưu như metadata để JVM đọc lại

Compiler đọc source bytes thành ký tự, sau đó phân tích và tạo class file. Runtime nạp class file; nó không mở lại file `.java` để decode String literal.

String literal được lưu trong class file dưới dạng dữ liệu constant pool theo định dạng class file, trong đó mục `CONSTANT_Utf8` sử dụng Modified UTF-8. Đây là định dạng nội bộ của class file, không phải chỉ thị để runtime đoán lại encoding của source file.

Điều này có nghĩa:

- Source file có thể được lưu bằng UTF-8.
- Compiler đọc nó đúng và tạo class file.
- JVM chạy class file mà không cần biết source ban đầu được lưu bằng UTF-8 hay encoding nào khác.
- Nếu compiler đọc source sai, class file đã chứa giá trị String sai; đổi charset khi chạy không sửa được literal đã biên dịch.

`-encoding` là tùy chọn ở thời điểm compile. Nó không được nhúng vào class file như một thiết lập để các API I/O lúc chạy tự dùng cùng charset.

## 6. Unicode trong Java source và Unicode escape

Java source được xử lý theo mô hình ký tự Unicode. Một cách viết trực tiếp ký tự tiếng Việt trong file UTF-8 thường dễ đọc và dễ bảo trì:

~~~java
String greeting = "Xin chào";
~~~

Java cũng có Unicode escape:

~~~java
String greeting = "Xin ch\u00E0o";
~~~

Trong ví dụ trên, `\u00E0` biểu diễn code point U+00E0 (chữ `à`). Unicode escape được xử lý ở giai đoạn sớm của quá trình dịch source, trước khi compiler phân tích token thông thường.

Unicode escape hữu ích khi cần biểu diễn ký tự cụ thể trong source, nhưng không nên dùng để né cấu hình encoding sai:

- Nó làm source khó đọc hơn nếu dùng quá nhiều.
- Nó không giải quyết encoding của file dữ liệu lúc chạy.
- Nó không làm cho source file chứa tiếng Việt trực tiếp trở nên an toàn nếu các phần khác vẫn bị đọc sai.
- Một số escape có thể tạo ký tự ảnh hưởng đến cấu trúc source vì quá trình chuyển đổi diễn ra sớm.

Với repository viết tiếng Việt, lựa chọn rõ ràng là lưu source UTF-8 và compile bằng `-encoding UTF-8`.

## 7. Phân biệt source encoding với encoding của file dữ liệu lúc chạy

### 7.1. Source code dùng UTF-8 không có nghĩa mọi file I/O dùng UTF-8 explicit

Ví dụ source file được compiler đọc bằng UTF-8:

~~~shell
javac -encoding UTF-8 -d out src/ReadMessage.java
~~~

Nhưng code sau lại dùng default charset khi đọc byte thành String:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

String text = Files.readString(Path.of("message.txt"));
~~~

`Files.readString(Path)` dùng UTF-8 theo hợp đồng API. Tuy nhiên, không phải mọi API I/O đều có cùng quy tắc; một số API dùng default charset hoặc yêu cầu caller truyền charset.

Nên ghi encoding rõ ràng khi định dạng file quy định một charset:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String text = Files.readString(
        Path.of("message.txt"),
        StandardCharsets.UTF_8);
~~~

Cách viết này thể hiện hợp đồng dữ liệu ngay tại nơi đọc file.

### 7.2. Đọc và ghi text với charset explicit

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8FileIO {
    public static void main(String[] args) throws Exception {
        Path path = Path.of("message.txt");

        Files.writeString(path, "Xin chào", StandardCharsets.UTF_8);
        String text = Files.readString(path, StandardCharsets.UTF_8);

        System.out.println(text);
    }
}
~~~

Byte file được tạo bằng UTF-8 và được đọc lại bằng UTF-8. Đây là round-trip có encoding được xác định, độc lập với encoding của source file.

### 7.3. InputStreamReader và OutputStreamWriter

Với API stream, hãy chỉ định charset khi chuyển byte stream thành character stream hoặc ngược lại:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

BufferedReader reader = new BufferedReader(
        new InputStreamReader(inputStream, StandardCharsets.UTF_8));

BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(outputStream, StandardCharsets.UTF_8));
~~~

`InputStreamReader` là cầu nối từ byte sang ký tự; `OutputStreamWriter` là cầu nối từ ký tự sang byte. Charset ở hai hướng phải tuân theo giao thức hoặc định dạng dữ liệu, không phụ thuộc charset dùng để compile source.

## 8. JEP 400 thay đổi default charset, không xóa nhu cầu chỉ định encoding

JEP 400 đặt UTF-8 làm default charset trên JDK 18+ theo cấu hình mặc định. Điều này làm các API phụ thuộc default charset có hành vi dễ dự đoán hơn trên nhiều hệ điều hành.

Tuy nhiên, cần phân biệt ba điều:

1. **Default charset của JVM:** hỏi bằng `Charset.defaultCharset()`.
2. **Source encoding:** charset compiler dùng để đọc file `.java`, có thể chỉ định bằng `javac -encoding`.
3. **Encoding của dữ liệu:** charset mà file format, protocol hoặc API yêu cầu ở từng lần đọc/ghi.

Ví dụ kiểm tra default charset lúc chạy:

~~~java
import java.nio.charset.Charset;

public class DefaultCharsetCheck {
    public static void main(String[] args) {
        System.out.println(Charset.defaultCharset().name());
    }
}
~~~

Trên JDK 18+ với cấu hình mặc định, kết quả là:

~~~text
UTF-8
~~~

Kết quả này không chứng minh source file đã được lưu bằng UTF-8. Nó cũng không chứng minh terminal hoặc mọi hệ thống nhận dữ liệu đều dùng UTF-8. Muốn biết compiler đã dùng source encoding nào, hãy xem build command/configuration và bảo đảm nó có `-encoding UTF-8`.

## 9. Đồng bộ encoding giữa IDE, build tool và CI

Một dự án có thể compile đúng trong IDE nhưng lỗi ở CI nếu hai môi trường dùng source encoding khác nhau. Hãy cấu hình cùng một chuẩn ở các nơi:

- File source thực sự được lưu bằng UTF-8.
- IDE mở và lưu source bằng UTF-8.
- Maven/Gradle truyền encoding UTF-8 cho compiler.
- Script build local và CI dùng cùng cấu hình.
- Code generator tạo source theo encoding thống nhất.

### 9.1. Maven

Có thể khai báo encoding ở project properties:

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Hoặc cấu hình trực tiếp compiler plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <encoding>UTF-8</encoding>
    </configuration>
</plugin>
~~~

Hãy dùng phiên bản plugin đã được dự án quản lý và kiểm tra effective POM nếu cấu hình parent/plugin có thể ghi đè giá trị.

### 9.2. Gradle

Với Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Với Kotlin DSL:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

Cấu hình ở build script giúp compiler task dùng cùng encoding thay vì dựa vào máy chạy Gradle.

### 9.3. IDE và editor

Trong IDE, kiểm tra:

- Project encoding.
- Encoding riêng của từng source file.
- Encoding mặc định khi tạo file mới.
- Encoding của file được generate.
- Có cảnh báo khi mở file bằng charset khác hay không.

Nếu editor đã lưu file thành mojibake, đổi project encoding sang UTF-8 không tự phục hồi nội dung. Cần lấy bản gốc hoặc xác định chính xác chuỗi chuyển đổi sai rồi sửa file trước khi build.

## 10. Kiểm tra source file và build command

### 10.1. Xem byte của source file

Trên PowerShell:

~~~powershell
Format-Hex -Path .\src\VietnameseGreeting.java
~~~

Trên Linux:

~~~shell
xxd -g 1 -l 96 src/VietnameseGreeting.java
~~~

Với source chứa `Xin chào`, các byte UTF-8 của phần `chào` gồm:

~~~text
63 68 C3 A0 6F
~~~

Nếu byte không khớp với encoding mà build khai báo, hãy kiểm tra cách editor lưu file. Không dùng kết quả hiển thị của terminal làm bằng chứng duy nhất về byte thực tế.

### 10.2. Build sạch và chạy lại

Ví dụ trên Linux/macOS:

~~~shell
rm -rf out
mkdir -p out
javac -encoding UTF-8 -d out src/VietnameseGreeting.java
java -cp out VietnameseGreeting
~~~

Trên PowerShell:

~~~powershell
Remove-Item -Recurse -Force .\out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path .\out | Out-Null
javac -encoding UTF-8 -d out .\src\VietnameseGreeting.java
java -cp out VietnameseGreeting
~~~

Build sạch giúp tránh chạy nhầm class file được tạo từ source cũ. Nếu output vẫn sai, kiểm tra source bytes, class output và terminal như các bước riêng biệt.

### 10.3. Nhận diện lỗi compiler đọc sai encoding

Các dấu hiệu có thể gặp:

- Compiler báo unmappable character hoặc lỗi ký tự trong source.
- Comment/Javadoc bị lỗi dấu nhưng code vẫn compile.
- String literal được in ra dưới dạng mojibake.
- Build local thành công nhưng CI báo lỗi do cấu hình compiler khác.

Không sửa bằng cách xóa dấu tiếng Việt khỏi comment hoặc thay toàn bộ literal bằng escape. Hãy xác minh byte source, encoding thực tế và cờ compiler.

## 11. Một ví dụ tổng hợp: source UTF-8 và data UTF-8 là hai cấu hình riêng

Cấu trúc dự án:

~~~text
encoding-example/
├── src/
│   └── VietnameseFileExample.java
├── data/
│   └── greeting.txt
└── out/
~~~

File `src/VietnameseFileExample.java` được lưu bằng UTF-8:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class VietnameseFileExample {
    public static void main(String[] args) throws Exception {
        Path file = Path.of("data", "greeting.txt");

        Files.writeString(
                file,
                "Xin chào từ file dữ liệu!",
                StandardCharsets.UTF_8);

        String message = Files.readString(
                file,
                StandardCharsets.UTF_8);

        System.out.println("Đọc từ file: " + message);
    }
}
~~~

Compile source bằng UTF-8:

~~~shell
javac -encoding UTF-8 -d out src/VietnameseFileExample.java
~~~

Chạy từ thư mục `encoding-example/`:

~~~shell
java -cp out VietnameseFileExample
~~~

Kết quả:

~~~text
Đọc từ file: Xin chào từ file dữ liệu!
~~~

Trong ví dụ này có hai quyết định độc lập:

- Compiler đọc `VietnameseFileExample.java` bằng UTF-8 nhờ `-encoding UTF-8`.
- Ứng dụng ghi và đọc `greeting.txt` bằng UTF-8 nhờ `StandardCharsets.UTF_8`.

Nếu bỏ một trong hai cấu hình, cấu hình còn lại không tự bù cho nó.

## 12. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `javac -encoding UTF-8` làm mọi file I/O lúc chạy dùng UTF-8 | Cờ chỉ điều khiển việc compiler đọc source file |
| JEP 400 khiến không cần cấu hình source encoding | JEP 400 thay đổi default charset; `-encoding` vẫn mô tả rõ source bytes |
| `--release 25` quyết định encoding source | `--release` đặt source/API/class target; `-encoding` đặt source charset |
| Source compile được nghĩa là đã đọc đúng UTF-8 | Charset sai vẫn có thể tạo ký tự hợp lệ nhưng sai nội dung |
| String literal cần được decode lại lúc chạy theo source encoding | Literal đã trở thành dữ liệu trong class file; JVM không đọc lại source |
| UTF-8 trong source bảo đảm file dữ liệu UTF-8 | File dữ liệu cần charset explicit theo format/protocol |
| Terminal hiển thị sai chứng minh compiler sai | Terminal/font/console encoding là một lớp riêng |
| Đổi encoding trong IDE sẽ phục hồi mojibake | Chỉ thay cách diễn giải byte; nội dung đã bị ghi sai cần phục hồi từ bản gốc |
| Unicode escape thay thế được cấu hình encoding | Escape chỉ biểu diễn code point trong source, không giải quyết mọi boundary I/O |

## 13. Bài tập thực hành

### Bài 1 — Compile source tiếng Việt

Tạo `VietnameseGreeting.java` chứa comment và String literal tiếng Việt. Lưu file bằng UTF-8, compile với `javac -encoding UTF-8` và chạy.

**Tiêu chí đạt:** Comment/source hiển thị đúng trong editor và String literal giữ đúng nội dung sau khi chạy.

### Bài 2 — Quan sát khi compiler dùng sai encoding

Tạo một bản sao source UTF-8. Thử compile bản sao bằng một charset không tương ứng nếu môi trường có hỗ trợ.

**Tiêu chí đạt:** Phân biệt trường hợp compiler báo lỗi với trường hợp compile thành công nhưng literal bị mojibake. Không ghi đè source gốc.

### Bài 3 — Tách source encoding và data encoding

Dùng source UTF-8 để ghi/đọc một file bằng `StandardCharsets.UTF_8`. Sau đó thay charset của API file trong một bản thử nghiệm.

**Tiêu chí đạt:** Giải thích vì sao cờ `javac -encoding` không thay đổi encoding của file được đọc lúc chạy.

### Bài 4 — Đồng bộ Maven hoặc Gradle

Cấu hình compiler encoding UTF-8 trong build tool. Chạy build local và CI với cùng cấu hình.

**Tiêu chí đạt:** Không phụ thuộc default charset của máy build.

### Bài 5 — Kiểm tra byte source và data

Dùng `Format-Hex` hoặc `xxd` để kiểm tra byte source và file dữ liệu. Đối chiếu với charset đã khai báo.

**Tiêu chí đạt:** Xác định được byte thuộc source file hay file dữ liệu, không suy luận từ cách terminal hiển thị.

## 14. Checklist trước khi commit source tiếng Việt

- [ ] Source file được lưu thực sự bằng UTF-8.
- [ ] Build command có `javac -encoding UTF-8` hoặc build tool tương đương.
- [ ] IDE/editor dùng cùng encoding với repository.
- [ ] Maven/Gradle và CI có cấu hình thống nhất.
- [ ] `--release` được chọn độc lập theo API baseline của dự án.
- [ ] File dữ liệu được đọc/ghi bằng charset theo định dạng.
- [ ] Không dựa vào default charset cho giao thức yêu cầu encoding cố định.
- [ ] Đã kiểm tra byte source nếu xuất hiện lỗi dấu.
- [ ] Đã kiểm tra output String riêng với encoding của terminal.
- [ ] Không dùng Unicode escape để che giấu source file bị lưu sai encoding.
- [ ] Không commit file source đã bị mojibake.

## 15. Tài liệu chính thức

1. [The javac Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): tùy chọn `-encoding` và cách compiler nhận source file.
2. [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ JDK 18 và phạm vi tương thích.
3. [Java Language Specification — Java SE 27](https://docs.oracle.com/javase/specs/jls/se27/html/index.html): quy tắc source text, Unicode escape và lexical translation.
4. [The Java Virtual Machine Specification — Java SE 27](https://docs.oracle.com/javase/specs/jvms/se27/html/index.html): cấu trúc class file và constant pool.
5. [Charset — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html): charset và default charset.
6. [StandardCharsets — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn được Java bảo đảm.
7. [Files — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): đọc/ghi chuỗi với charset tường minh.
8. [InputStreamReader — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/InputStreamReader.html): chuyển byte stream thành character stream với charset được chọn.
9. [OutputStreamWriter — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/OutputStreamWriter.html): chuyển character stream thành byte stream.

**Kết quả cần đạt:** Có thể lưu source tiếng Việt bằng UTF-8, cấu hình compiler đọc đúng source với `javac -encoding UTF-8`, đồng bộ IDE/build/CI và chỉ định encoding riêng cho dữ liệu lúc chạy. Hiểu được JEP 400 làm default charset thống nhất hơn trên JDK hiện đại nhưng không thay thế việc khai báo encoding tại từng boundary dữ liệu.

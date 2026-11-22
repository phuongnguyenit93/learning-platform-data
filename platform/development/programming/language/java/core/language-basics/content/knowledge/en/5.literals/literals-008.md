# Text block: cú pháp mở, đóng và xử lý thụt lề trong Java

> **Java core — language-basics / Literal**  
> **Yêu cầu:** JDK 17+; text block là tính năng ổn định từ Java 15, không cần bật preview.  
> **Mục tiêu:** Viết đúng dấu mở/đóng `"""`; xác định khi nào chuỗi chứa newline cuối; giải thích xử lý *incidental indentation*; biết dùng escape `\s` và nối dòng; tự biên dịch và kiểm tra giá trị chuỗi.

## 1. Text block vẫn là `String`

**Text block** là cú pháp literal nhiều dòng, thích hợp cho JSON, HTML hoặc câu truy vấn dài. Nó tạo ra một `String` thông thường, không phải một kiểu dữ liệu riêng.

~~~java
String ordinary = "Hello\nJava\n";
String block = """
        Hello
        Java
        """;
System.out.println(ordinary.equals(block)); // true
~~~

Text block thường giúp mã dễ đọc hơn cách ghép nhiều chuỗi với `+ "\n"`, nhưng **không đảm bảo bảo toàn mọi dấu cách nguyên xi từ mã nguồn**. Java có quy tắc chuẩn hóa dấu xuống dòng và loại bỏ thụt lề phụ.

## 2. Cú pháp của delimiter mở và đóng

Cấu trúc điển hình:

~~~java
String message = """
        Dong thu nhat
        Dong thu hai
        """;
~~~

- **Dấu mở** gồm ba dấu nháy kép `"""`, sau đó có thể có khoảng trắng và **bắt buộc phải có line terminator**. Nội dung bắt đầu ở dòng **tiếp theo**; dấu xuống dòng bắt buộc ngay sau delimiter mở không trở thành ký tự đầu tiên của giá trị.
- **Dấu đóng** cũng gồm `"""`, nhưng có thể nằm trên **dòng riêng** hoặc **cùng dòng với phần nội dung cuối**.
- Dấu `;` kết thúc câu lệnh khai báo biến; nó không phải thành phần của giá trị String.
- Không cần escape dấu nháy kép `"` đơn lẻ bên trong text block như trong chuỗi thường, miễn không vô tình tạo một delimiter kết thúc.

**Cú pháp cố ý sai** (để trong comment, không chạy):

~~~java
// String bad = """Hello""";  // Thiếu line terminator sau delimiter mở.
~~~

Text block không phải string template: tên biến đặt trong nội dung không tự được thay bằng giá trị biến. Nếu muốn chèn dữ liệu động, dùng phép ghép, `String.format` hoặc API khác thích hợp.

## 3. Dấu đóng quyết định có newline ở cuối hay không

So sánh:

~~~java
String withNewline = """
        A
        B
        """;

String noNewline = """
        A
        B""";
~~~

| Cách đặt delimiter đóng | Giá trị Java tương đương | Điểm cần nhớ |
| --- | --- | --- |
| Dòng riêng sau B | `"A\nB\n"` | Newline sau B **thuộc chuỗi** |
| Sát B trên cùng dòng | `"A\nB"` | Không có newline cuối |

Đây là khác biệt **dữ liệu thực**, không chỉ khác biệt hình thức mã nguồn. Nếu phần mềm xuất JSON hay tạo văn bản kiểm thử mà không muốn newline cuối, nên chủ động chọn vị trí delimiter đóng hoặc định dạng lại chuỗi theo đúng yêu cầu.

**Không dùng `strip()` bừa bãi** để “sửa” newline thừa vì phương thức này còn bỏ khoảng trắng đầu/cuối vốn có thể mang ý nghĩa.

## 4. Quy tắc xử lý thụt lề phụ (*incidental indentation*)

Khi code được đặt trong method hay class, các dòng text block thường phải thụt theo định dạng Java. Java **loại phần thụt lề chung mang tính trình bày**, còn mức thụt sâu hơn được giữ.

~~~java
String list = """
        root
          child
        """;
~~~

Chuỗi `list` có giá trị tương đương:

~~~text
root
  child
~~~

Ngoài ra, nó có **newline ở cuối** do delimiter đóng nằm trên dòng riêng.

Quy tắc thực hành:

1. Để dấu đóng cùng mức với dòng nội dung có mức thụt lề cơ sở nếu bạn muốn loại bỏ phần thụt do code.
2. Dòng nào được thụt sâu hơn mức chung thì vẫn giữ **phần chênh lệch**. Ở ví dụ, `child` giữ hai dấu cách.
3. **Đặt dấu đóng lùi sang trái** có thể khiến Java loại bỏ ít thụt lề hơn và giữ thêm khoảng trắng ở đầu tất cả dòng.
4. Nên dùng space nhất quán thay vì trộn tab và space vì nhìn giống nhau trong editor không có nghĩa dấu thụt thực giống nhau.
5. Dòng trống và dấu cách cuối dòng cũng chịu quy tắc xử lý riêng; đừng mặc định mọi ký tự trắng gõ trong source đều được giữ.

Nói chính xác hơn, Java sử dụng các dòng không trống và vị trí dấu đóng để xác định mức *incidental indentation*. Đây không phải thao tác tùy ý “xóa mọi khoảng trắng đầu dòng”.

## 5. Thứ tự xử lý newline và escape

Java chuẩn hóa các line terminator trong nội dung text block về **LF** (`\n`), kể cả source lưu theo kiểu CRLF. Tiếp đó, nó loại bỏ thụt lề phụ và khoảng trắng cuối dòng thích hợp; **sau cùng** mới diễn giải escape.

| Cú pháp nội dung | Ý nghĩa |
| --- | --- |
| `\n` | Ký tự xuống dòng theo escape |
| `\t` | Ký tự tab theo escape |
| `\s` | Một dấu cách; đặc biệt hữu ích để **giữ khoảng trắng cuối dòng** |
| `\` ngay trước line terminator | **Line continuation**: bỏ dấu kết thúc dòng đó, ghép hai phần nội dung |

Ví dụ:

~~~java
String spaces = """
        end\s\s
        """;

String joined = """
        pre\
        fix
        """;
~~~

Giá trị của `spaces` là `"end  \n"` (hai dấu cách trước newline). Giá trị của `joined` là `"prefix\n"`: dấu `\` nối `pre` và `fix`, nhưng newline sau `fix` vẫn còn.

**Khác nhau:** `\n` trong source tạo một ký tự LF trong giá trị; còn khi in bản thân hai ký tự dấu gạch chéo ngược và chữ `n`, bạn phải escape phù hợp, ví dụ chuỗi thường `"\\n"`.

## 6. Một chương trình Java 17+ kiểm chứng chính xác

Tạo file **TextBlockDemo.java**:

~~~java
public class TextBlockDemo {
    private static String visible(String value) {
        return value.replace(" ", "_").replace("\n", "|");
    }

    public static void main(String[] args) {
        String indented = """
                first
                  second
                """;

        String noFinalNewline = """
                one
                two""";

        String keptSpaces = """
                end\s\s
                """;

        String joined = """
                pre\
                fix
                """;

        System.out.println("indented=" + visible(indented));
        System.out.println("noFinalNewline=" + visible(noFinalNewline));
        System.out.println("keptSpaces=" + visible(keptSpaces));
        System.out.println("joined=" + visible(joined));
        System.out.println("sameType=" + indented.getClass().getSimpleName());
    }
}
~~~

Chạy từ thư mục có file trên Bash, PowerShell hoặc Command Prompt:

~~~bash
javac -encoding UTF-8 TextBlockDemo.java
java TextBlockDemo
~~~

**Expected output:**

~~~text
indented=first|__second|
noFinalNewline=one|two
keptSpaces=end__|
joined=prefix|
sameType=String
~~~

Hàm `visible` chỉ chuyển dấu cách thành `_` và newline thành `|` để thấy chúng rõ ràng trên console; nó **không sửa chuỗi gốc**.

Giải thích từng dòng:

- `indented` giữ hai dấu cách trước `second` và một newline cuối.
- `noFinalNewline` không có newline sau `two` vì dấu đóng đứng sát phần nội dung cuối.
- `keptSpaces` có hai dấu cách thật nhờ hai `\s`, ngay trước newline cuối.
- `joined` nối `pre` với `fix`, không còn newline ở giữa; newline cuối vẫn còn.
- `sameType` khẳng định đối tượng được tạo là `String`.

## 7. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Compiler báo delimiter mở không hợp lệ | Viết nội dung ngay sau `"""` mở | Đặt line terminator sau dấu mở |
| Dữ liệu có `\n` cuối ngoài ý muốn | Dấu đóng ở dòng riêng | Đặt dấu đóng ngay sau nội dung cuối nếu muốn bỏ newline đó |
| Dấu cách cuối dòng bị mất | Khoảng trắng cuối dòng được loại bỏ khi chuẩn hóa text block | Dùng `\s` để giữ khoảng trắng có chủ đích |
| Dữ liệu giữ nhiều khoảng trắng đầu dòng | Dấu đóng lùi trái làm giảm mức incidental indentation được loại bỏ | Căn lại các dòng và dấu đóng |
| Chuỗi từ Windows khác newline của tệp gốc | Java chuẩn hóa CRLF thành LF bên trong text block | Kiểm tra dữ liệu đầu ra thay vì dựa trên dòng mã nguồn |
| Text block tự nhiên không chèn biến | Text block là String literal, không phải template | Dùng định dạng/ghép chuỗi có chủ đích |
| Có ba dấu nháy kép liên tiếp trong nội dung | Có thể kết thúc text block sớm | Escape hoặc cấu trúc lại đoạn chứa dấu nháy |

Nếu yêu cầu bảo toàn **từng byte** của tài liệu bên ngoài, text block không phải lựa chọn mặc định: hãy cân nhắc đọc resource/file và kiểm soát encoding/line endings.

## 8. Bài tập ngắn

**Bài 1 — Newline cuối:** Viết hai text block chứa `Hello`: một đóng ở dòng riêng, một đóng sát `Hello`. So sánh `length()` và đầu ra qua `visible`.

**Bài 2 — Thụt lề:** Viết hai dòng `root` và `  child`, thay đổi vị trí dấu đóng sang trái rồi quan sát số dấu cách còn lại bằng `visible`.

**Bài 3 — Dấu cách cuối:** So sánh hai dấu cách thật ở cuối dòng source với hai escape `\s\s`. Chúng được giữ giống nhau không?

**Bài 4 — Nối dòng:** Sửa `pre` và `fix` thành `foo` và `bar`, thử có/không có dấu `\` trước line terminator. Đoán giá trị có newline nào.

**Bài 5 — JSON:** Viết JSON nhiều dòng trong text block và in ra. Kiểm tra mức thụt lề của nội dung, dấu nháy kép, newline cuối trước khi dùng làm dữ liệu thực.

### Ghi nhớ

**Text block là `String`**, dùng ba dấu nháy kép; dấu mở bắt buộc theo sau bởi xuống dòng. **Vị trí dấu đóng quyết định newline cuối.** Java chuẩn hóa newline, loại bỏ thụt lề phụ rồi mới diễn giải escape như `\s` và dấu `\` nối dòng. Khi cần chính xác từng dấu cách hoặc newline, hãy hiển thị chúng bằng một hàm như `visible`.

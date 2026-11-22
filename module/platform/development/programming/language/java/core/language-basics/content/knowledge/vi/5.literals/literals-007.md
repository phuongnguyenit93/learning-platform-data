# Escape sequence cho xuống dòng, dấu nháy và dấu gạch chéo ngược trong Java

## 1. Escape sequence là gì?

Trong **string literal** (`"..." `) và **character literal** (`'...'`) của Java, dấu gạch chéo ngược `\\` mở đầu một **escape sequence**: cách viết một ký tự đặc biệt bằng tổ hợp ký tự trong mã nguồn.

Ví dụ:

~~~java
System.out.println("Dong mot\nDong hai");
~~~

Trong file nguồn, `\n` được viết bằng hai ký tự `\\` và `n`, nhưng **khi Java tạo chuỗi**, chúng biểu diễn **một ký tự xuống dòng** (line feed, LF, U+000A). Đầu ra:

~~~text
Dong mot
Dong hai
~~~

Điều này khác chuỗi `"Dong mot\\nDong hai"`, trong đó `\\` đã được escape để trở thành **dấu gạch chéo ngược thật**, rồi theo sau là chữ `n`.

**Ba escape cần nắm chắc trong bài:**

- `\n`: xuống dòng LF.
- `\"`: đưa dấu nháy kép `"` vào một chuỗi được bao bởi nháy kép.
- `\\`: đưa một dấu gạch chéo ngược `\\` vào chuỗi hoặc ký tự.

Các escape được xử lý khi phân tích **literal trong mã nguồn**, không phải là quy tắc tự động áp dụng cho mọi dữ liệu nhận từ bàn phím, file hoặc API.

## 2. Bảng tra cứu ngắn

| Cú pháp trong mã Java | Ký tự/ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| `\n` | Line feed, LF (U+000A) | Tạo dòng mới trong chuỗi |
| `\r` | Carriage return, CR (U+000D) | Giao thức hoặc dữ liệu cần CR |
| `\t` | Tab ngang | Thụt/căn bằng ký tự tab |
| `\"` | Dấu nháy kép `"` | Viết nháy kép trong string literal |
| `\'` | Dấu nháy đơn `'` | Viết nháy đơn trong char literal |
| `\\` | Một dấu gạch chéo ngược `\\` | Đường dẫn, regex, biểu diễn escape dưới dạng chữ |
| `\b` | Backspace | Ký tự điều khiển, ít dùng để định dạng văn bản |
| `\f` | Form feed | Ký tự điều khiển, ít dùng |

Tất cả ví dụ thuộc **Java 17+**. Những ký tự như `\\`, `"`, `'` trong bảng là ký hiệu mô tả; để viết chúng trong mã Java, phải chú ý dấu phân cách và escape của từng loại literal.

Java không hỗ trợ mọi kết hợp bắt đầu bằng `\\`: chẳng hạn `\q` không phải escape hợp lệ trong string literal thông thường.

## 3. Xuống dòng: `\\n` khác với `\\\\n`

Xét hai giá trị:

~~~java
String withNewline = "A\nB";
String literalBackslashN = "A\\nB";

System.out.println(withNewline);
System.out.println(literalBackslashN);
~~~

Đầu ra:

~~~text
A
B
A\nB
~~~

Có thể tự kiểm chứng bằng độ dài:

~~~java
System.out.println("\n".length());   // 1
System.out.println("\\n".length());  // 2
System.out.println("A\nB".length()); // 3
System.out.println("A\\nB".length());// 4
~~~

Giải thích: `"A\nB"` gồm `A`, **một** ký tự LF, `B`; `"A\\nB"` gồm `A`, `\\`, `n`, `B`.

### `print` khác `println`

~~~java
System.out.print("A\nB");
System.out.println("C");
~~~

Kết quả:

~~~text
A
BC
~~~

`print` không tự thêm dấu kết thúc dòng sau giá trị; chỉ có `\n` nằm trong chuỗi. `println` in phần nội dung và thêm dấu kết thúc dòng theo môi trường.

**Phân biệt LF với xuống dòng theo hệ điều hành:**

- `\n` luôn là ký tự LF, bất kể chương trình chạy trên Windows, Linux hay macOS.
- `System.lineSeparator()` cho ký tự/chuỗi phân tách dòng theo nền tảng.
- `System.out.println(...)` thêm dấu xuống dòng theo cơ chế của `PrintStream`, thường phù hợp với nền tảng.
- `System.out.printf("A%nB%n");` dùng `%n` của định dạng để xuống dòng theo nền tảng.

Nếu giao thức/tệp dữ liệu yêu cầu **LF chính xác**, hãy dùng `\n`; nếu mong đầu ra văn bản theo nền tảng, `println` hoặc `%n` thường thích hợp. Đừng tự giả định mọi tình huống đều cần `\r\n`.

## 4. Dấu nháy kép: `\\\"`

String literal Java dùng dấu nháy kép làm dấu **mở và đóng**. Muốn chứa dấu nháy kép thật bên trong chuỗi, phải escape:

~~~java
String message = "Lan noi: \"Xin chao!\"";
System.out.println(message);
~~~

Đầu ra:

~~~text
Lan noi: "Xin chao!"
~~~

Không có escape, đoạn sau gây lỗi biên dịch do dấu nháy kết thúc chuỗi quá sớm:

~~~java
// Sai: String bad = "Lan noi: "Xin chao!"";
~~~

Dấu nháy đơn **không bắt buộc escape trong string literal** được bao bằng nháy kép:

~~~java
String text = "It's Java";
System.out.println(text); // It's Java
~~~

Đừng thêm dấu `\\` không cần thiết khắp chuỗi, vì một số tổ hợp escape không hợp lệ hoặc khiến nội dung thật khác mong muốn.

## 5. Dấu nháy đơn và char literal: `\\'`

Character literal dùng dấu nháy đơn `'...'` và phải biểu diễn **một giá trị `char`**, tức một đơn vị mã UTF-16.

~~~java
char quote = '\'';
char doubleQuote = '"';
char newline = '\n';

System.out.println(quote);       // '
System.out.println(doubleQuote);// "
System.out.println((int) newline); // 10
~~~

Vì dấu `'` là dấu phân cách của character literal, bạn cần `'\''` để biểu diễn chính dấu nháy đơn. Dấu nháy kép có thể viết trực tiếp trong char literal như `'"'`.

Không nhầm:

- `'\n'` là **một char** mang mã 10.
- `"\n"` là **một String** có độ dài 1.
- `'\\'` là **một char** mang dấu gạch chéo ngược.
- `"\\n"` là **một String** gồm hai ký tự gạch chéo ngược và `n`.

Những đoạn như `char invalid = 'ab';` hoặc `char invalid = '';` không hợp lệ: character literal không được chứa hai ký tự thông thường hoặc rỗng.

## 6. Dấu gạch chéo ngược: `\\\\`

Trong Java source, dấu `\\` mở đầu escape. Vì vậy để có **một dấu gạch chéo ngược thật** trong chuỗi hoặc ký tự, viết **hai dấu** `\\`:

~~~java
String separator = "\\";
char slash = '\\';
System.out.println(separator); // \
System.out.println(slash);     // \
~~~

Ví dụ đường dẫn Windows:

~~~java
String path = "C:\\Users\\Lan\\notes.txt";
System.out.println(path);
~~~

Đầu ra:

~~~text
C:\Users\Lan\notes.txt
~~~

**Hai bẫy phổ biến:**

1. `"C:\Users\Lan"` chứa `\U` và `\L` không hợp lệ trong Java string literal; compiler báo lỗi *illegal escape character*.
2. `"C:\new\temp"` **có thể biên dịch** nhưng sai nội dung đường dẫn: `\n` thành xuống dòng, `\t` thành tab.

Tốt nhất khi thao tác đường dẫn thực tế là dùng `java.nio.file.Path`/ `Paths`, thay vì nối đường dẫn phụ thuộc hệ điều hành bằng tay:

~~~java
java.nio.file.Path file =
        java.nio.file.Path.of("data", "notes.txt");
System.out.println(file.getFileName()); // notes.txt
~~~

Với API nhận đường dẫn, cách viết `Path.of("data", "notes.txt")` tránh phải chèn `\\` chỉ để nối hai thành phần. Đây là ví dụ về đường dẫn tương đối; file không nhất thiết phải tồn tại.

## 7. Chương trình Java 17 chạy được và kết quả rõ ràng

Tạo tệp **`EscapeDemo.java`**:

~~~java
public final class EscapeDemo {
    private EscapeDemo() {}

    public static void main(String[] args) {
        String multiLine = "Dong 1\nDong 2";
        String quoted = "Lan noi: \"Xin chao!\"";
        String path = "C:\\Users\\Lan\\notes.txt";
        String visibleEscape = "\\n";
        char singleQuote = '\'';
        char backslash = '\\';

        System.out.println("1) newline:");
        System.out.println(multiLine);
        System.out.println("2) quote: " + quoted);
        System.out.println("3) path: " + path);
        System.out.println("4) literal: " + visibleEscape);
        System.out.println("5) char: " + singleQuote + " / " + backslash);
        System.out.println("6) lengths: "
                + "\n".length() + " vs " + "\\n".length());
        System.out.println("7) newline code: " + (int) '\n');
        System.out.println("8) equals: "
                + multiLine.equals("Dong 1\nDong 2"));
    }
}
~~~

Mở terminal trong thư mục chứa file; cần **JDK 17+**.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 EscapeDemo.java
java -cp . EscapeDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\EscapeDemo.java
java -cp . EscapeDemo
~~~

Đầu ra kỳ vọng:

~~~text
1) newline:
Dong 1
Dong 2
2) quote: Lan noi: "Xin chao!"
3) path: C:\Users\Lan\notes.txt
4) literal: \n
5) char: ' / \
6) lengths: 1 vs 2
7) newline code: 10
8) equals: true
~~~

Hai dòng `Dong 1` và `Dong 2` xuất hiện tách biệt vì `multiLine` chứa **LF thật**. Dòng `4) literal: \n` hiển thị đúng hai ký tự `\\` và `n` vì biến `visibleEscape` có giá trị `"\\n"`.

Các lệnh ví dụ được thiết kế chạy độc lập; kết quả trên là **expected output** để người học tự đối chiếu, không phụ thuộc thư viện ngoài.

## 8. Escape trong chuỗi không phải phép thay thế cho mọi dữ liệu

Nếu ứng dụng đọc một chuỗi có **hai ký tự** `\\` và `n` từ file hoặc đầu vào người dùng, Java **không tự chuyển** chúng thành LF. Escape sequence được diễn giải khi phân tích literal trong **source code**.

Ví dụ:

~~~java
String typed = "\\n";
String actual = "\n";

System.out.println(typed.equals(actual)); // false
~~~

Trong một API nhận chuỗi, muốn hỗ trợ cú pháp escape từ dữ liệu đầu vào thì cần có **quy tắc parse riêng** cho định dạng ấy (JSON, properties, ngôn ngữ template, v.v.). Mỗi định dạng có quy tắc escape khác nhau: không lấy cú pháp Java áp đặt nguyên xi cho mọi trường hợp.

### Nhiều lớp escape

Khi chuỗi Java được dùng làm **regex**, backslash có thể phải đi qua **hai lớp cú pháp**: string literal của Java và biểu thức chính quy. Ví dụ:

~~~java
String regex = "\\d+";
System.out.println("123".matches(regex)); // true
~~~

Trong source Java, `"\\d+"` tạo chuỗi thật là `\d+`; sau đó regex engine diễn giải `\d` là lớp ký tự chữ số. Viết `"\d+"` trực tiếp trong Java source là **illegal escape character** vì `\d` không phải escape của string literal Java.

**Ranh giới bài học:** chỉ cần nhận ra dấu `\\` có thể mang vai trò khác nhau ở mỗi lớp cú pháp; học đầy đủ regex/JSON là chủ đề khác.

## 9. Những lỗi thường gặp

| Code / triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `String s = "A\nB";` nhưng muốn thấy `A\nB` trên một dòng | `\n` tạo LF thật | `"A\\nB"` |
| `String s = "C:\Users\Lan";` | `\U` và `\L` không hợp lệ | `"C:\\Users\\Lan"` |
| `String s = "A\qB";` | `\q` không phải escape hợp lệ | Bỏ `\\` hoặc dùng `\\q` nếu cần ký tự `\\` thật |
| `String s = "Lan noi: "Hi"";` | Dấu nháy kép không được escape | `"Lan noi: \"Hi\""` |
| `char c = ''';` | Dấu nháy đơn đóng literal sớm | `char c = '\'';` |
| `String s = "A\nB";` cho length 3 | Hiểu nhầm `\n` gồm 2 ký tự khi chạy | LF là **1 char** |
| `String s = "\\n";` cho length 2 | Nhầm `\\n` với LF | Giá trị gồm `\\` và `n` |
| `System.out.print("A\nB")` không xuống dòng sau B | `print` không thêm dấu dòng cuối | Dùng `println` hoặc thêm ký tự cần thiết |

Trong những lỗi dạng *illegal escape character*, trước tiên hãy xác định ký tự **ngay sau dấu `\\`** ở vị trí bị báo; đó thường là phần mã nguồn không hợp lệ.

## 10. Những lưu ý quan trọng cho Java 17+

**Không gõ xuống dòng thật bên trong string literal thông thường:**

~~~java
// Sai nếu viết như dưới đây thành hai dòng source:
// String s = "A
// B";
~~~

Muốn xuống dòng, dùng `\n` trong string literal hoặc sử dụng **text block** (`"""`) khi nội dung thực sự nhiều dòng. Trong text block, các escape như `\n`, `\"`, `\\` vẫn có quy tắc riêng của Java; tuy nhiên text block có thêm cách xử lý xuống dòng và thụt lề, không nên dùng chỉ để thay cho một dấu `\n` đơn giản.

**Unicode escape khác escape trong string literal:** Java xử lý Unicode escapes kiểu `\\uXXXX` ở giai đoạn đọc nguồn đặc biệt, **trước khi nhận diện token**; vì vậy không đồng nhất `\n` với mã Unicode escape của LF. Để ghi một ký tự xuống dòng trong string literal, **ưu tiên `\n`** vì dễ đọc và tránh rắc rối từ giai đoạn xử lý Unicode escape.

**Không dùng `\r` thay thế `\n` một cách tùy tiện.** `\r` là carriage return; cách terminal hiển thị có thể khác tùy môi trường. Để tạo CRLF trong định dạng yêu cầu cặp ký tự này, dùng `\r\n`.

**Đừng nhầm dấu gạch chéo xuôi và ngược:** `/` là dấu slash thông thường, không phải mở đầu escape trong Java string literal. `"https://example.com"` không cần viết `\\` trước dấu `/`.

## 11. Bài tập có đáp án

### Bài A — dự đoán độ dài

~~~java
System.out.println("A\nB".length());
System.out.println("A\\nB".length());
System.out.println("\\".length());
~~~

**Đáp án:**

~~~text
3
4
1
~~~

### Bài B — in dấu nháy

Hãy tạo chuỗi in ra: `Co ay noi: "Java!"`.

**Đáp án:**

~~~java
System.out.println("Co ay noi: \"Java!\"");
~~~

### Bài C — đường dẫn Windows

Hãy viết một string literal có giá trị `C:\data\notes.txt` (dấu gạch chéo ngược thật).

**Đáp án:**

~~~java
String path = "C:\\data\\notes.txt";
~~~

### Bài D — dấu nháy đơn kiểu char

Muốn khai báo ký tự dấu nháy đơn, viết gì?

**Đáp án:** `char apostrophe = '\'';`. Không thể viết `char apostrophe = ''';` vì dấu nháy đơn là ký tự phân cách char literal.

### Bài E — phân biệt Java escape và dữ liệu

Hai ký tự `\\` và `n` được đọc từ một file văn bản. Biến `String` có tự chứa LF không?

**Đáp án:** Không. Chúng vẫn là hai ký tự riêng trừ khi định dạng của file/API và code đọc file có cơ chế diễn giải escape. Không gọi `String.replace` mù quáng với dữ liệu chưa hiểu quy tắc.

## 12. Checklist hoàn thành

- [ ] Giải thích được tại sao `\n` tạo LF và `\\n` tạo hai ký tự `\\` + `n`.
- [ ] Biết dùng `\"` để đưa dấu nháy kép vào string literal.
- [ ] Biết dùng `\'` cho dấu nháy đơn trong char literal.
- [ ] Biết dùng `\\` để biểu diễn dấu gạch chéo ngược.
- [ ] Phân biệt `print`, `println`, `\n` và `%n`.
- [ ] Viết đúng literal cho đường dẫn có dấu `\\`, tránh `\U`/ `\q` không hợp lệ.
- [ ] Biết `"\n".length() == 1` và `"\\n".length() == 2`.
- [ ] Không nhầm escape trong source Java với dữ liệu string nhận từ bên ngoài.
- [ ] Biên dịch và chạy `EscapeDemo.java` trên JDK 17+, đối chiếu từng dòng output.

**Kết luận:** Trong Java, dấu `\\` là ký hiệu mở đầu escape khi nằm trong string/char literal. `\n` tạo LF thật, `\"` tạo dấu nháy kép và `\\` tạo một dấu gạch chéo ngược. Muốn **in nguyên văn ký hiệu escape** như `\n`, hãy escape chính dấu gạch chéo ngược thành `\\n`.
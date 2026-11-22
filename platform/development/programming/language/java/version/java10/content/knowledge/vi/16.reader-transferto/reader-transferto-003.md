# Vị trí đọc hiện tại và thời điểm kết thúc nguồn khi dùng `Reader.transferTo(Writer)` trong Java

## Mục tiêu bài học

`java.io.Reader.transferTo(Writer)` được bổ sung từ **Java 10** và vẫn là API chuẩn trong Java hiện đại. Phương thức này chuyển tất cả **ký tự còn lại** từ một `Reader` sang một `Writer` theo đúng thứ tự được đọc. Điểm quan trọng nhất: `transferTo` **không tự quay về đầu nguồn**. Nó bắt đầu tại **vị trí đọc hiện tại** và, nếu hoàn tất bình thường, đưa Reader đến **cuối luồng (EOF — end of stream)**.

Sau bài học, bạn sẽ có thể:

- Xác định chính xác phần dữ liệu nào được chuyển khi trước đó đã gọi `read()`, `read(char[])`, `skip()` hoặc `BufferedReader.readLine()`.
- Giải thích vì sao `transferTo` dừng ở **EOF**, không dừng ở xuống dòng, hết buffer hay khi `ready()` trả `false`.
- Hiểu giá trị trả về `long` là **số ký tự Java đã chuyển**, không phải số byte, số dòng hoặc kích thước cuối cùng của Writer.
- Dự đoán điều gì xảy ra khi gọi lần hai sau EOF, khi dùng `mark/reset`, và khi nguồn chưa phát tín hiệu kết thúc.
- Xử lý đúng vòng đời Reader/Writer, trường hợp thao tác có thể block, nguồn vô hạn và lỗi I/O.
- Chạy ví dụ Java 17+ có kết quả được xác minh.

## 1. Hợp đồng của `Reader.transferTo`

Chữ ký API:

~~~java
public long transferTo(Writer out) throws IOException
~~~

`transferTo` là **instance method** của `Reader`; ví dụ:

~~~java
Reader input = new StringReader("abc");
Writer output = new StringWriter();

long count = input.transferTo(output);
~~~

Trong một lần gọi **thành công bình thường**:

1. Reader đọc từ **vị trí hiện tại**, không nhất thiết từ đầu dữ liệu.
2. Các ký tự được ghi vào `out` theo đúng thứ tự được đọc.
3. Quá trình tiếp tục đến khi **không còn ký tự trong nguồn** (EOF).
4. Reader nằm tại EOF khi phương thức trả về bình thường.
5. Phương thức trả về một số `long` biểu thị lượng **ký tự được chuyển trong chính lời gọi này**.
6. `transferTo` **không tự đóng** Reader hoặc Writer.

Nếu `out == null`, lời gọi ném `NullPointerException`. Nếu việc đọc hoặc ghi xảy ra lỗi I/O, phương thức ném `IOException`; tình trạng Reader/Writer sau lỗi không nhất thiết giống tình trạng sau khi hoàn tất thành công.

**Không có tham số offset hay length** trong `Reader.transferTo(Writer)`. Muốn chuyển một đoạn theo giới hạn do ứng dụng tự đặt, bạn phải điều chỉnh vị trí/nguồn hoặc dùng một vòng lặp sao chép có giới hạn riêng.

## 2. “Vị trí đọc hiện tại” được hiểu như thế nào?

Hình dung Reader như con trỏ tiến dần qua một chuỗi ký tự. Mỗi lần đọc hoặc bỏ qua có thể làm vị trí logic tiến về phía trước:

~~~text
Nguồn ban đầu:     H E A D | b o d y \n n e x t
Vị trí ban đầu:    ^
Sau skip(5):                 ^
transferTo(...) đọc:          b o d y \n n e x t
Sau thành công:                                 ^ EOF
~~~

Dấu `|` trong minh họa là ký tự phân cách nội dung, còn `\n` tượng trưng cho một ký tự xuống dòng thực sự. Ký hiệu `^` chỉ **vị trí logic của ký tự tiếp theo sẽ được đọc**.

Ví dụ:

~~~java
try (var reader = new StringReader("HEAD|body\nnext");
     var writer = new StringWriter()) {

    long skipped = reader.skip(5);
    long transferred = reader.transferTo(writer);

    System.out.println(skipped);      // 5
    System.out.println(transferred);  // 9
    // Nội dung writer gồm "body", newline, "next".
}
~~~

Chuỗi đầu vào gồm `HEAD|` (5 ký tự) và `body\nnext` (9 ký tự). `skip(5)` loại 5 ký tự đầu **khỏi phần còn lại sẽ đọc**. Vì vậy `transferTo` chỉ chuyển 9 ký tự ở đuôi; không đọc lại `HEAD|`.

`skip(n)` trả số ký tự **thực sự** bỏ qua, không nhất thiết đúng `n` nếu đã sát EOF. Đừng suy luận rằng `skip(1000)` luôn thành công trọn 1000 ký tự.

### 2.1. Nếu đã gọi `read()`

~~~java
try (var reader = new StringReader("ABCDE");
     var writer = new StringWriter()) {

    int first = reader.read();         // Đã lấy 'A'
    long count = reader.transferTo(writer);

    System.out.println((char) first); // A
    System.out.println(count);        // 4
    System.out.println(writer);       // BCDE
}
~~~

Ký tự `A` đã được tiêu thụ bởi `read()`; `transferTo` không tự bổ sung nó vào Writer.

### 2.2. Nếu đã đọc một mảng ký tự

~~~java
try (var reader = new StringReader("abcdef");
     var writer = new StringWriter()) {

    char[] prefix = new char[2];
    int readCount = reader.read(prefix); // 2: 'a', 'b'
    long copied = reader.transferTo(writer);

    System.out.println(readCount);      // 2
    System.out.println(copied);         // 4
    System.out.println(writer);         // cdef
}
~~~

Tương tự, `read(char[], off, len)` tiêu thụ số ký tự **thực tế được trả về**. Nếu một lệnh đọc đã tiến Reader, chỉ phần chưa đọc mới được chuyển.

## 3. `BufferedReader.readLine()` ảnh hưởng tới phần còn lại

Trường hợp dễ nhầm nhất là đọc một dòng trước, rồi dùng `transferTo` để chuyển phần còn lại.

~~~java
try (var reader = new BufferedReader(
            new StringReader("one\nTWO\nthree"));
     var writer = new StringWriter()) {

    String first = reader.readLine(); // "one"
    long copied = reader.transferTo(writer);

    System.out.println(first);       // one
    System.out.println(copied);      // 9
    // writer chứa "TWO", newline, "three".
}
~~~

`readLine()` trả nội dung dòng **không kèm ký tự kết thúc dòng**; nó cũng đã tiêu thụ dấu kết thúc dòng tương ứng nếu có. Vì vậy Reader ở vị trí ngay trước `T` của dòng thứ hai. Phần còn lại `TWO\nthree` có (3 + 1 + 5 = 9) ký tự.

Với dòng kết thúc bằng `\r\n` (CRLF), `readLine()` cũng nhận diện và tiêu thụ dấu kết thúc dòng; `transferTo` bắt đầu từ **vị trí logic sau dòng đã đọc**, không in lại CRLF vừa được tiêu thụ.

**Lưu ý về buffering:** `BufferedReader` có thể đọc trước một số ký tự vào bộ đệm nội bộ, nhưng vị trí logic mà API tiếp tục cung cấp vẫn là vị trí **sau dữ liệu đã tiêu thụ**. Không trộn việc đọc trực tiếp từ Reader nền với việc đọc qua `BufferedReader` bao ngoài, vì bộ đệm có thể đã đọc trước làm kết quả khó dự đoán. Hãy tiếp tục thao tác nhất quán trên cùng đối tượng `BufferedReader`.

## 4. `transferTo` thực sự dừng khi nào?

**Điều kiện kết thúc bình thường là EOF**, tức bên đọc đã xác định không còn ký tự để cung cấp. Nó **không** dừng chỉ vì:

- Gặp `\n` hoặc `\r\n`: xuống dòng vẫn là dữ liệu ký tự.
- Gặp chuỗi rỗng hoặc dòng trống: nội dung dòng không phải dấu kết thúc toàn bộ nguồn.
- Đọc hết một lần vào buffer: phương thức tiếp tục đọc các lần tiếp theo khi còn nguồn.
- `ready()` trả `false`: điều này chỉ nói về khả năng đọc không bị block ngay, **không chứng minh EOF**.
- Đã nhận được vài ký tự từ một kết nối: nguồn có thể còn ký tự sẽ đến sau.

Với `StringReader` hay một tệp văn bản hữu hạn, EOF sẽ đến khi đọc hết nội dung. Với nguồn như pipe, socket hoặc đầu vào tương tác, `transferTo` có thể **tiếp tục chờ** dữ liệu cho đến khi phía cung cấp báo kết thúc luồng. Nếu phía cung cấp giữ luồng mở, lời gọi có thể không kết thúc.

Theo hợp đồng `Reader.transferTo`, phương thức **có thể block vô hạn** trong lúc đọc nguồn hoặc ghi sang đích; ứng dụng cần tính tới vòng đời của cả producer và consumer. Không lấy “đã thấy một dòng được gửi” làm tín hiệu cho rằng `transferTo` phải dừng.

### `ready()` không phải phép thử EOF

~~~java
// Không nên dựa vào mẫu này để quyết định hết dữ liệu:
if (!reader.ready()) {
    // Không thể kết luận reader đã tới EOF.
}
~~~

`Reader.ready()` mô tả khả năng đọc ký tự tiếp theo mà không block (với những sắc thái riêng của implementation). Để nhận diện EOF khi **đọc thủ công**, kiểm tra `read(...)` trả `-1` với yêu cầu đọc độ dài dương; nếu dùng `transferTo`, bản thân phương thức đã đọc cho tới EOF khi trả về bình thường.

## 5. Khi đã tới EOF, Reader và Writer ra sao?

### 5.1. Reader ở cuối nguồn, nhưng chưa đóng

~~~java
try (var reader = new StringReader("abc");
     var writer = new StringWriter()) {

    long first = reader.transferTo(writer);
    int after = reader.read();
    long second = reader.transferTo(new StringWriter());

    System.out.println(first);  // 3
    System.out.println(after);  // -1
    System.out.println(second); // 0
}
~~~

Đối với `StringReader`, lời gọi đầu tiên chuyển ba ký tự và đưa vị trí tới EOF. `read()` tiếp theo trả `-1`; `transferTo` tiếp theo không còn gì để chuyển và trả 0.

**EOF khác đóng luồng.** Sau `transferTo` thành công, Reader vẫn mở. Nếu Reader bị **đóng**, nhiều thao tác đọc tiếp sẽ ném `IOException` thay vì trả `-1`. Không coi `close()` là cách “đọc hết” tương đương với EOF.

### 5.2. Writer không tự bị đóng, nội dung sẵn có được giữ

~~~java
try (var reader = new StringReader("abc");
     var writer = new StringWriter()) {

    writer.write("prefix:");
    long copied = reader.transferTo(writer);
    writer.write("!");

    System.out.println(copied); // 3
    System.out.println(writer); // prefix:abc!
}
~~~

`copied` bằng **3**, không phải độ dài `prefix:abc!`. Lời gọi chỉ đếm các ký tự nó chuyển từ Reader; nó không đếm ký tự đã có trong Writer hay ký tự được ghi **sau đó**.

`transferTo` không đóng Reader hay Writer, và **không thay thế bước flush cần thiết** của một Writer có bộ đệm. Nếu cần dữ liệu được đẩy ra đích tại một thời điểm xác định, gọi `flush()` theo hợp đồng Writer. Khi sử dụng try-with-resources, việc đóng tài nguyên diễn ra **khi rời khối**, chứ không phải do `transferTo` tự đóng.

## 6. `mark()` và `reset()`: có thể đọc lại trong trường hợp nào?

`transferTo` **không tự rewind**. Nhưng một số Reader hỗ trợ đánh dấu và đặt lại vị trí; chẳng hạn `StringReader` có `markSupported() == true`.

~~~java
try (var reader = new StringReader("xyz");
     var first = new StringWriter();
     var second = new StringWriter()) {

    reader.mark(10);
    System.out.println(reader.transferTo(first));  // 3

    reader.reset(); // StringReader hỗ trợ quay lại vị trí đã mark.
    System.out.println(reader.transferTo(second)); // 3

    System.out.println(first.toString().equals(second.toString())); // true
}
~~~

Ở đây lần thứ hai chỉ có dữ liệu để đọc vì **`reset()` đã thay đổi vị trí**. Không phải `transferTo` tự đọc lại nội dung.

Cần lưu ý:

- Không phải Reader nào cũng hỗ trợ `mark/reset`: kiểm tra `markSupported()` nếu API của bạn nhận Reader bất kỳ.
- Với những Reader như `BufferedReader`, dấu `mark` có thể bị mất hiệu lực nếu đọc vượt giới hạn `readAheadLimit`. Sau một `transferTo` dài, không giả định `reset()` luôn thành công.
- `reset()` thay đổi vị trí Reader, **không xóa nội dung đã ghi trong Writer**. Nếu dùng cùng một Writer và chuyển lại sau reset, phần dữ liệu có thể được ghi thêm lần nữa.
- Nếu cần đọc lại toàn bộ tệp, cách dễ hiểu thường là mở **Reader mới**, không dựa vào mọi loại Reader có thể quay lại.

## 7. Giá trị trả về `long`: số ký tự, không phải số byte

`Reader` và `Writer` làm việc ở **mức ký tự**. Giá trị `long` của `transferTo` đo số đơn vị ký tự Java được chuyển. Nó **không** phải:

- Số byte mã hóa UTF-8/UTF-16 đã ghi xuống tệp.
- Số dòng hoặc số ký tự trong toàn bộ nguồn từ đầu nếu đã tiêu thụ một phần.
- Số ký tự đã tồn tại trong Writer trước khi chuyển.
- Số **Unicode code point** nếu có ký tự ngoài BMP được biểu diễn bằng cặp surrogate UTF-16.

Ví dụ ký tự U+1F642 được Java biểu diễn bằng **hai `char`**:

~~~java
String text = "A" + new String(Character.toChars(0x1F642)) + "B";

try (var reader = new StringReader(text);
     var writer = new StringWriter()) {

    reader.read(); // Tiêu thụ 'A'.
    long count = reader.transferTo(writer);

    System.out.println(count); // 3: hai char của ký tự U+1F642 và 'B'
    System.out.println(writer.toString().codePointCount(
            0, writer.toString().length())); // 2 code point
}
~~~

Vì vậy, trong chương trình cần phân biệt:

| Đại lượng | Ví dụ ở trên |
| --- | --- |
| Số `char` được `transferTo` chuyển | 3 |
| Số Unicode code point trong phần chuyển | 2 |
| Số byte nếu mã hóa phần chuyển sang UTF-8 | Phụ thuộc charset; không suy từ số `char` |

Khi dùng `InputStream.transferTo(OutputStream)`, câu chuyện khác: `InputStream` xử lý **byte**, còn `Reader.transferTo(Writer)` xử lý **ký tự** sau bước giải mã từ byte nếu nguồn được tạo qua `InputStreamReader`. Đừng lẫn các giá trị đếm của hai API.

## 8. Chương trình Java 17+ hoàn chỉnh

Lưu đoạn mã sau thành tệp **ReaderTransferPositionDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;

public class ReaderTransferPositionDemo {
    public static void main(String[] args) throws IOException {
        // (1) Vị trí sau skip(5), Writer có tiền tố.
        try (var reader = new StringReader("HEAD|body\nnext");
             var writer = new StringWriter()) {
            long skipped = reader.skip(5);
            writer.write("P:");
            long moved = reader.transferTo(writer);

            System.out.println("skipped: " + skipped);
            System.out.println("transferred: " + moved);
            System.out.println(
                    "writer: " + writer.toString().replace("\n", "\\n")
            );
            System.out.println("writer total chars: " + writer.toString().length());
            System.out.println("after read: " + reader.read());
            System.out.println(
                    "second transfer: " + reader.transferTo(new StringWriter())
            );

            writer.write("!");
            System.out.println(
                    "writer still open: " + writer.toString().endsWith("!")
            );
        }

        // (2) Đọc dòng đầu tiên, sau đó chuyển phần còn lại.
        try (var reader = new BufferedReader(
                    new StringReader("one\nTWO\nthree"));
             var writer = new StringWriter()) {
            System.out.println("first line: " + reader.readLine());
            long moved = reader.transferTo(writer);
            System.out.println("line tail chars: " + moved);
            System.out.println(
                    "line tail: " + writer.toString().replace("\n", "\\n")
            );
        }

        // (3) Đếm đơn vị char UTF-16, không phải Unicode code point.
        String unicode = "A" + new String(Character.toChars(0x1F642)) + "B";
        try (var reader = new StringReader(unicode);
             var writer = new StringWriter()) {
            System.out.println("first character: " + (char) reader.read());
            long moved = reader.transferTo(writer);

            System.out.println("unicode char units: " + moved);
            System.out.println(
                    "unicode code points: " +
                    writer.toString().codePointCount(
                            0, writer.toString().length())
            );
        }

        // (4) Đọc lại chỉ vì Reader hỗ trợ mark/reset.
        try (var reader = new StringReader("xyz");
             var first = new StringWriter();
             var second = new StringWriter()) {
            reader.mark(10);
            System.out.println(
                    "first marked transfer: " + reader.transferTo(first)
            );
            reader.reset();
            System.out.println(
                    "after reset transfer: " + reader.transferTo(second)
            );
            System.out.println(
                    "equal after reset: " +
                    first.toString().equals(second.toString())
            );
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac ReaderTransferPositionDemo.java
java ReaderTransferPositionDemo
~~~

Kết quả chính xác (ký hiệu `\n` được in thành **hai ký tự** `\` và `n` nhờ `replace`):

~~~text
skipped: 5
transferred: 9
writer: P:body\nnext
writer total chars: 11
after read: -1
second transfer: 0
writer still open: true
first line: one
line tail chars: 9
line tail: TWO\nthree
first character: A
unicode char units: 3
unicode code points: 2
first marked transfer: 3
after reset transfer: 3
equal after reset: true
~~~

**Đối chiếu kết quả:**

1. `skip(5)` đưa Reader qua `HEAD|`; `transferTo` chuyển phần `body\nnext` gồm 9 `char`.
2. Writer đã có `P:` (2 ký tự), nên độ dài cuối lời gọi bằng `2 + 9 = 11`, nhưng giá trị trả về vẫn là 9.
3. Sau khi đã đọc tới EOF, `read()` trả `-1`, và lần `transferTo` tiếp theo chuyển 0 ký tự.
4. Ghi thêm `!` vào Writer còn mở thành công; `transferTo` không đóng Writer.
5. `readLine()` đã tiêu thụ `one` và dấu xuống dòng, nên phần còn lại `TWO\nthree` gồm 9 `char`.
6. Ký tự ngoài BMP U+1F642 chiếm 2 đơn vị `char`, nên sau khi tiêu thụ `A`, phần còn lại có 3 `char` nhưng chỉ 2 code point.
7. `mark/reset` cho phép `StringReader` quay lại vị trí đã đánh dấu; hai lần chuyển ra hai Writer riêng đều đọc `xyz`.

Đây là chương trình có đầu ra xác định và không cần mạng, tệp hay thư viện bên ngoài.

## 9. Khi nguồn là tệp: xác định charset và quản lý tài nguyên

`Reader.transferTo` làm việc với ký tự, nên khi lấy nguồn từ tệp byte cần chọn charset đúng. Với Java 17+, có thể dùng `Files.newBufferedReader` và `Files.newBufferedWriter`:

~~~java
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

// Đoạn mã minh họa trong phương thức throws IOException.
// Hai đường dẫn phải khác nhau; không ghi đè chính tệp nguồn.
Path source = Path.of("input.txt");
Path target = Path.of("copy.txt");

try (Reader in = Files.newBufferedReader(source, StandardCharsets.UTF_8);
     Writer out = Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {

    long moved = in.transferTo(out);
    System.out.println("chars transferred: " + moved);
}
~~~

Phần dữ liệu được chuyển vẫn bắt đầu từ **vị trí hiện tại** của `in`. Trong ví dụ trên, Reader mới được mở nên bắt đầu ở đầu tệp. Nếu đã đọc hoặc `skip` một số ký tự trước `transferTo`, chỉ phần còn lại được chuyển. `out` ghi các ký tự này theo charset đã chọn; số byte của tệp `copy.txt` **có thể khác** số ký tự `moved`.

`Files.newBufferedWriter(target, UTF_8)` theo cấu hình mặc định có thể tạo mới hoặc ghi đè nội dung cũ của tệp đích; hãy chọn đường dẫn và chế độ mở phù hợp. Không dùng chung đường dẫn nguồn và đích trong ví dụ copy, vì ghi đè có thể làm mất dữ liệu gốc.

**Try-with-resources** đóng hai đối tượng sau khi thoát khối (kể cả khi có lỗi). Đừng hiểu nhầm rằng việc đóng xảy ra do `transferTo`: chính cú pháp quản lý tài nguyên thực hiện bước đó.

## 10. EOF, thời gian chờ và nguồn chưa kết thúc

### 10.1. Tệp, chuỗi và kết nối có “cuối nguồn” khác nhau

| Nguồn | Thời điểm thường có EOF | Điều cần lưu ý |
| --- | --- | --- |
| `StringReader("abc")` | Sau khi đọc hết chuỗi | EOF xác định, dễ kiểm tra |
| `BufferedReader` đọc một tệp hữu hạn | Sau khi đọc hết nội dung tệp qua Reader | Buffer rỗng một lần không phải điều kiện kết thúc độc lập |
| `InputStreamReader` trên `System.in` | Khi đầu vào thực sự báo EOF | Nhấn Enter chỉ tạo xuống dòng, thường không làm `transferTo` kết thúc |
| Reader trên pipe/socket | Khi phía cung cấp tín hiệu kết thúc theo giao thức/stream | Có thể block trong khi chờ dữ liệu hoặc EOF |
| `Reader.nullReader()` (Java 11+) | Ngay khi đọc, nếu còn mở | `transferTo` trả 0 vì không có ký tự |

Nếu nguồn có thể sống vô hạn, `transferTo` không có tham số “ngừng sau N ký tự” và không có điều kiện dừng theo newline. Khi cần giới hạn, timeout hoặc giao thức ngắt, thiết kế cơ chế đọc có ranh giới ở tầng ứng dụng.

### 10.2. Không tự đoán hiệu năng hoặc số lần đọc

Cú pháp `transferTo` giúp code rõ ràng và tránh tự viết vòng lặp đọc/ghi trong trường hợp cần chuyển **hết phần còn lại**. Tuy nhiên, hợp đồng API không hứa một kích thước buffer cố định, số lần gọi `read` hay `write`, hoặc thời gian hoàn thành trong mọi môi trường.

Với `StringWriter`, toàn bộ dữ liệu được giữ trong bộ nhớ; nếu nguồn rất lớn, bộ nhớ cho đích có thể tăng theo nội dung. Dùng Writer tới tệp hoặc một đích tiêu thụ theo luồng khi không cần giữ tất cả vào một String, nhưng vẫn cần kiểm soát dung lượng và thời gian của đầu vào.

Nếu chỉ cần đọc **một đoạn** hoặc **một thông điệp** trong một kết nối dài, `transferTo` trực tiếp có thể không phù hợp: nó cố đọc đến EOF của Reader, không dừng ở ranh giới thông điệp tùy ý do ứng dụng định nghĩa.

## 11. Trường hợp lỗi đọc/ghi: không có tính nguyên tử

`Reader.transferTo` có thể ném `IOException` khi Reader đọc lỗi hoặc Writer ghi lỗi. Trước khi ngoại lệ xuất hiện, phương thức **có thể đã đọc một phần nguồn và ghi một phần đích**.

Điều quan trọng:

- Không được giả định Reader chắc chắn đã tới EOF nếu `transferTo` ném lỗi.
- Không được giả định Writer chưa nhận ký tự nào; đầu ra có thể bị ghi dở.
- Không có hợp đồng **rollback** hoặc giao dịch nguyên tử cho Reader/Writer.
- Sau lỗi I/O, trạng thái một hoặc cả hai luồng có thể không nhất quán; tài liệu API khuyến nghị đóng cả hai sớm.
- Nếu cần tránh xuất hiện tệp đầu ra chưa hoàn chỉnh, hãy thiết kế ghi vào **tệp tạm**, đóng/xác minh thành công rồi công bố hoặc đổi tên theo quy trình an toàn của hệ thống tệp.

Ví dụ xử lý ở mức cấu trúc:

~~~java
try (Reader in = Files.newBufferedReader(source, StandardCharsets.UTF_8);
     Writer out = Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
    long count = in.transferTo(out);
    // Chỉ ở nhánh thành công mới sử dụng count như số ký tự đã chuyển.
} catch (IOException ex) {
    // Xử lý bản sao đầu ra có thể đang dở; log/báo lỗi theo ứng dụng.
    throw ex;
}
~~~

Đoạn trên là **mảnh mã minh họa** bên trong một phương thức có `source`, `target` dạng `Path` và import tương ứng; không phải chương trình độc lập. Đừng tự động retry bằng cùng Reader sau một lỗi I/O nếu chưa xác định được vị trí đọc và trạng thái đích.

## 12. Các lỗi tư duy thường gặp

| Hiểu nhầm | Thực tế | Cách sửa |
| --- | --- | --- |
| “`transferTo` luôn copy từ đầu.” | Bắt đầu ở **vị trí đọc hiện tại**. | Mở Reader mới hoặc `reset` hợp lệ nếu muốn đọc lại. |
| “Đã `readLine()` rồi `transferTo` sẽ chuyển cả dòng đầu.” | Dòng đã đọc và delimiter của nó đã bị tiêu thụ. | Ghi dòng đầu riêng nếu muốn lưu cả nó; chú ý không tự khôi phục đúng delimiter nếu đã mất thông tin. |
| “Đến newline là xong.” | Phương thức tiếp tục tới **EOF**. | Nếu chỉ xử lý một dòng, dùng `readLine` hoặc logic giới hạn riêng. |
| “`ready()==false` nghĩa là EOF.” | `ready` nói về khả năng đọc không block, không chứng minh hết nguồn. | Dựa vào `read` trả `-1` khi đọc thủ công. |
| “`transferTo` chuyển đúng số byte `long` trả về.” | Trả số đơn vị ký tự Java. | Phân biệt char, code point và byte theo charset. |
| “Chuyển xong tức Reader/Writer đã đóng.” | `transferTo` không đóng hai luồng. | Dùng try-with-resources và `flush` khi cần. |
| “Tại EOF, gọi lại sẽ đọc lại từ đầu.” | Không tự rewind; với `StringReader` lần sau trả 0. | Tạo Reader mới hoặc `reset` khi hợp lệ. |
| “Một lỗi I/O nghĩa là chưa ghi gì.” | Có thể chuyển dở một phần. | Xử lý partial output và đóng tài nguyên. |
| “Dòng trống, hết buffer hoặc không có dữ liệu tức thời nghĩa là EOF.” | Nguồn có thể còn dữ liệu và `transferTo` có thể block. | Tách ranh giới thông điệp khỏi EOF, đặt chính sách chờ/hạn mức. |
| “Reader nào cũng hỗ trợ `mark/reset`.” | Khả năng phụ thuộc implementation và giới hạn read-ahead. | Kiểm tra `markSupported`, hoặc tạo Reader mới. |
| “Sau khi `BufferedReader` đọc, có thể tiếp tục đọc Reader nền tùy ý.” | Buffer có thể đã đọc trước, dễ làm sai vị trí logic. | Duy trì thao tác trên cùng wrapper Reader. |

## 13. Bài tập tự kiểm tra

### Bài 1 — đọc trước và EOF

Dự đoán kết quả:

~~~java
try (var r = new StringReader("0123456789");
     var w = new StringWriter()) {
    r.read();             // '0'
    long skipped = r.skip(3);
    long transferred = r.transferTo(w);

    // A. skipped = ?
    // B. transferred = ?
    // C. w.toString() = ?
    // D. r.read() = ?
}
~~~

**Đáp án:**

- A = `3`: bỏ qua `'1'`, `'2'`, `'3'`.
- B = `6`: còn `"456789"`.
- C = `"456789"`, vì phần đã đọc/bỏ qua không được chuyển.
- D = `-1`, vì `transferTo` đã đưa `StringReader` đến EOF.

### Bài 2 — `readLine` và dòng trống

~~~java
try (var r = new BufferedReader(
            new StringReader("A\n\nBC"));
     var w = new StringWriter()) {
    String first = r.readLine();
    long transferred = r.transferTo(w);

    // first = ?
    // transferred = ?
    // w chứa gì?
}
~~~

**Đáp án:** `first` là `"A"`; `readLine()` đã tiêu thụ `A\n`; phần còn lại là `\nBC` gồm **3 ký tự**, nên `transferred == 3`. Dòng trống **không** kết thúc toàn bộ nguồn.

### Bài 3 — số ký tự khác độ dài Writer

~~~java
try (var r = new StringReader("XY");
     var w = new StringWriter()) {
    w.write("prefix-");
    long transferred = r.transferTo(w);

    // transferred = ?
    // w.toString().length() = ?
}
~~~

**Đáp án:** `transferred == 2`; `w.toString().length() == 9` vì `"prefix-"` dài 7 ký tự, cộng thêm 2 ký tự đã chuyển. Kết quả `long` không đếm dữ liệu có trước trong Writer.

## 14. Ghi nhớ và tài liệu chuẩn

- **`Reader.transferTo(Writer)` từ Java 10** chuyển các ký tự **còn lại từ vị trí đọc hiện tại tới EOF**.
- **`read` và `skip` tiêu thụ đầu vào trước đó**; `BufferedReader.readLine` tiêu thụ cả dấu kết thúc dòng.
- Trên đường thành công, Reader tới EOF; với `StringReader` đã ở EOF, lần `transferTo` kế tiếp trả `0`.
- Kết quả `long` là số **ký tự Java được chuyển**, không phải bytes, số dòng hay toàn bộ Writer.
- `transferTo` **không đóng Reader hay Writer**; try-with-resources quản lý tài nguyên, và Writer cần được flush khi hợp đồng đích yêu cầu.
- Phương thức có thể **block** đến khi nguồn phát EOF; không dừng ở newline, hết buffer hay `ready()==false`.
- Nếu xảy ra `IOException`, nội dung đầu ra có thể dở dang; không giả định đã hoàn thành hoặc chưa ghi gì.
- `mark/reset` chỉ cho phép đọc lại nếu Reader cụ thể hỗ trợ và mark còn hiệu lực.

Tài liệu chính thức áp dụng cho Java hiện đại:

- [Java SE 17 — `Reader.transferTo(Writer)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer))
- [Java SE 17 — `Reader.read`, `skip`, `ready`, `mark/reset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html)
- [Java SE 17 — `BufferedReader.readLine()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#readLine())
- [Java SE 17 — `StringReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/StringReader.html)
- [Java SE 17 — `Files.newBufferedReader` và `newBufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)

**Kết luận:** Khi gọi `transferTo`, hãy hỏi hai câu: **“Reader đang ở vị trí nào?”** và **“Khi nào nguồn thực sự báo EOF?”**. Hai câu trả lời này quyết định phần ký tự được chuyển, số lượng trả về và việc lời gọi có kết thúc hay còn phải chờ.

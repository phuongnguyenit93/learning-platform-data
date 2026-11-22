# Readable, Appendable và khả năng ghép API trong Java

Trong Java I/O, nhiều API xử lý **ký tự** có thể ghép với nhau mà không cần phụ thuộc vào một lớp nguồn hoặc đích cụ thể. Hai giao diện quan trọng cho cách thiết kế này là `java.lang.Readable` (nguồn cung cấp ký tự) và `java.lang.Appendable` (đích nhận thêm ký tự). Chúng là những **hợp đồng tối thiểu**: một bên biết đọc vào `CharBuffer`, bên kia biết nối nội dung ký tự.

Điểm đáng học không chỉ là thuộc tên phương thức, mà là cách viết thành phần dùng chung cho `StringReader`, `BufferedReader`, `CharBuffer`, `StringBuilder`, `Writer`, v.v. mà không phải viết lại thuật toán theo từng loại.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt `Readable`, `Reader`, `Appendable`, `Writer` và `CharSequence` theo đúng vai trò.
- Giải thích hợp đồng `read(CharBuffer)`, `append(...)`, giá trị trả về và khả năng ném `IOException`.
- Ghép một nguồn ký tự với một đích ký tự nhờ khai báo tham số theo interface.
- Sử dụng `CharBuffer` đúng các bước **ghi → flip → tiêu thụ → clear**.
- Biết khi nào cần thêm `Closeable`, `Flushable`, charset, giới hạn dữ liệu hoặc cơ chế chờ I/O.
- Nhận diện các lỗi thường gặp: đọc một lần rồi tưởng đủ, quên `flip()`, quên EOF, lạm dụng `toString()`, hoặc đóng tài nguyên không thuộc sở hữu.

## 2. Hai interface tối thiểu

### `Readable`: một nguồn ký tự

Hợp đồng của `java.lang.Readable` có một phương thức chính:

~~~java
int read(java.nio.CharBuffer cb) throws java.io.IOException;
~~~

Phương thức đọc ký tự vào `cb` từ **vị trí hiện tại** của `CharBuffer`; vị trí sẽ tiến lên theo số ký tự đã thêm. Giá trị trả về:

- Số ký tự thực sự đã đưa vào buffer (có thể **ít hơn** `cb.remaining()` ban đầu).
- `-1` nếu đã đến **end of stream (EOF)**.
- `0` trong một số trường hợp không đọc ký tự nào, ví dụ buffer không còn chỗ hoặc nguồn hiện chưa tạo ra tiến độ. Cách phản ứng với `0` phụ thuộc nguồn; không nên quay vòng CPU vô hạn.

`Readable` không định nghĩa `close()`, `mark()`, `reset()`, `ready()` hay cách đổi từ byte sang ký tự. Những khả năng đó, nếu có, nằm ở các kiểu hoặc tầng API khác.

Ví dụ triển khai: `java.io.Reader` là lớp trừu tượng triển khai `Readable`; `StringReader` và `BufferedReader` là các loại `Reader` cụ thể. `java.nio.CharBuffer` cũng triển khai `Readable`, nên một vùng ký tự có thể được dùng làm nguồn đọc cho API cần interface này.

### `Appendable`: một đích nhận thêm ký tự

`java.lang.Appendable` cung cấp ba overload:

~~~java
Appendable append(CharSequence csq) throws java.io.IOException;
Appendable append(CharSequence csq, int start, int end)
        throws java.io.IOException;
Appendable append(char c) throws java.io.IOException;
~~~

Các thao tác bổ sung ký tự vào đích và trả về `Appendable` để có thể nối lời gọi:

~~~java
sink.append("Hello").append(' ').append("Java");
~~~

`CharSequence` là mô tả một chuỗi **ký tự**, có thể được thể hiện bằng `String`, `StringBuilder`, `CharBuffer` hoặc kiểu triển khai khác. Trong `append(csq, start, end)`, `start` **bao gồm**, `end` **loại trừ**, và chỉ số tính theo đơn vị **UTF-16 char**, không phải số Unicode code point.

Theo hợp đồng `Appendable`, truyền `null` làm `CharSequence` sẽ dẫn đến việc thêm chuỗi bốn ký tự `"null"`. Điều đó không thay thế cho kiểm tra dữ liệu đầu vào khi `null` phải mang ý nghĩa khác.

Ví dụ triển khai: `StringBuilder`, `StringBuffer`, `java.io.Writer` và `java.nio.CharBuffer`. `Appendable` không hứa dữ liệu đã xuống đĩa, không có `flush()` hoặc `close()` trong chính interface và không bảo đảm đồng bộ đa luồng.

### Bảng đối chiếu

| Kiểu | Vai trò | Năng lực ngoài hợp đồng tối thiểu |
| --- | --- | --- |
| `Readable` | Đọc ký tự vào `CharBuffer` | Chỉ bảo đảm `read(CharBuffer)` |
| `Reader` | Nguồn ký tự thuộc Java I/O | `read(char[])`, `close()` và nhiều tiện ích khác; là một `Readable` |
| `Appendable` | Nhận ký tự qua `append` | Không có `flush`/`close` bắt buộc |
| `Writer` | Đích ký tự thuộc Java I/O | `write(...)`, `flush()`, `close()`; là một `Appendable` |
| `CharSequence` | Biểu diễn dãy ký tự để đọc theo chỉ số | `length()`, `charAt()`, `subSequence()`; không đồng nghĩa một nguồn I/O |
| `CharBuffer` | Buffer ký tự NIO có `position/limit` | Có thể đóng vai trò `Readable`, `Appendable` và `CharSequence` |

**Không đánh đồng** `Readable` với `Reader`: một đối tượng có thể là `Readable` mà không phải `Reader`; tương tự, `Appendable` không nhất thiết là `Writer`. Nếu hàm chỉ đọc/append, khai báo tham số tối thiểu thường làm hàm dùng lại được rộng hơn.

## 3. Ghép API: đầu vào và đầu ra có thể thay thế

Ta có thể viết một thuật toán chỉ biết:

~~~text
Readable (nguồn ký tự)
        |
        | read(CharBuffer)
        v
CharBuffer [ghi vào các ô trống]
        |
        | flip() => chỉ lộ các ký tự vừa đọc
        v
Appendable (đích nhận thêm ký tự)
~~~

Ví dụ cùng một logic có thể đọc từ `StringReader` vào `StringBuilder` khi kiểm thử, rồi đọc từ `BufferedReader` vào `BufferedWriter` khi xử lý file. Thuật toán trung gian không cần biết nguồn ở RAM hay trên đĩa.

Tuy nhiên, đây là **ghép hợp đồng ký tự**. Với byte thuần, dùng `InputStream`/`OutputStream` hoặc byte channel. Nếu dữ liệu đi qua file/socket ở dạng byte mà cần xử lý văn bản, phải chọn charset để chuyển đổi tại biên thông qua `InputStreamReader` và `OutputStreamWriter`.

## 4. Ví dụ chạy được: sao chép ký tự từ `Readable` sang `Appendable`

Tạo file **`ReadableAppendableDemo.java`**:

~~~java
import java.io.IOException;
import java.io.StringReader;
import java.nio.CharBuffer;

public class ReadableAppendableDemo {
    public static long copy(Readable source, Appendable destination)
            throws IOException {
        CharBuffer buffer = CharBuffer.allocate(4);
        long total = 0;

        while (true) {
            int count = source.read(buffer);

            if (count == -1) {
                break;
            }
            if (count == 0) {
                // Chính sách của helper minh họa này: yêu cầu nguồn có tiến độ.
                // Nguồn non-blocking cần cơ chế chờ khả dụng riêng.
                throw new IOException("Source made no progress");
            }

            buffer.flip();
            destination.append(buffer);
            total += count;
            buffer.clear();
        }

        return total;
    }

    public static void main(String[] args) throws IOException {
        StringBuilder result = new StringBuilder();

        try (StringReader source = new StringReader("Hello, Java!")) {
            long copied = copy(source, result);
            System.out.println("characters=" + copied);
        }

        System.out.println("text=" + result);
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac ReadableAppendableDemo.java
java ReadableAppendableDemo
~~~

**Stdout chính xác:**

~~~text
characters=12
text=Hello, Java!
~~~

**Vì sao chạy đúng:**

1. `StringReader` là một `Reader`, do đó dùng được làm `Readable`. `StringBuilder` triển khai `Appendable`.
2. `CharBuffer.allocate(4)` có sức chứa 4 ký tự; chuỗi 12 ký tự được xử lý nhiều lượt. Mỗi `read` trả về **số ký tự thực nhận**, không phải lệnh yêu cầu đọc đúng bốn.
3. `read` ghi từ `buffer.position()` và tăng `position`; `flip()` chuyển sang trạng thái có thể đọc, đặt `limit` bằng vị trí đã ghi và đưa `position` về 0.
4. `destination.append(buffer)` nhận `CharBuffer` dưới dạng `CharSequence`; tại thời điểm này chuỗi nhìn thấy chỉ là những ký tự vừa đọc.
5. `clear()` đặt lại `position=0` và `limit=capacity` để vòng sau ghi tiếp. **`clear()` không xóa vật lý các ký tự cũ**; chúng chỉ không còn thuộc phần dữ liệu hợp lệ của lượt kế tiếp.
6. Khi `read` trả `-1`, helper kết thúc và trả tổng số **đơn vị `char`** đã chép. Con số này không nhất thiết bằng số byte UTF-8 hoặc số Unicode code point.

Đoạn này chủ động ném `IOException` khi `read` trả `0` để tránh một vòng lặp không tiến triển. **Đây là chính sách giới hạn của helper minh họa**, phù hợp nguồn blocking có tiến độ như `StringReader`. Một `Readable` tổng quát có thể trả `0`; với nguồn non-blocking phải tích hợp cơ chế báo sẵn sàng, huỷ/timeout hoặc quy tắc thử lại phù hợp, không mặc định đó là EOF và cũng không spin vô hạn.

### Nếu quên `flip()` thì sao?

~~~java
CharBuffer buffer = CharBuffer.allocate(4);
int count = source.read(buffer);

// Sai: buffer vẫn ở trạng thái chuẩn bị ghi; position đã tăng,
// remaining() có thể bằng 0 hoặc chứa vùng chưa được ghi.
destination.append(buffer);
~~~

Nếu mảng được lấp đầy, `position == limit` khiến phần `CharSequence` đang nhìn thấy rỗng. Nếu chỉ đọc một phần, đoạn còn “remaining” có thể chính là các ô **chưa được ghi**. Cần `flip()` trước khi chuyển dữ liệu đã đọc sang đích. Không tự chuyển `CharBuffer` thành `String` trước khi biết rõ `position` và `limit`.

Một thiết kế khác có thể dùng mảng `char[]` với `Reader.read(char[])` và `Writer.write(char[], 0, count)`, nhưng lúc đó hàm yêu cầu **`Reader/Writer`** cụ thể, kém tổng quát hơn helper `Readable/Appendable` ở trên.

## 5. Ví dụ ghép thư viện chuẩn: `Scanner` và `Formatter`

`java.util.Scanner` nhận `Readable` làm nguồn phân tích token; `java.util.Formatter` có thể nhận `Appendable` làm đích định dạng. Điều này cho phép ta kết nối parser và formatter với các nguồn/đích khác nhau mà không bắt mỗi nơi phải là file.

Tạo file **`ScannerFormatterDemo.java`**:

~~~java
import java.io.StringReader;
import java.util.Formatter;
import java.util.Locale;
import java.util.Scanner;

public class ScannerFormatterDemo {
    public static void main(String[] args) {
        StringBuilder result = new StringBuilder();

        try (Scanner scanner = new Scanner(new StringReader("8 13"));
             Formatter formatter = new Formatter(result, Locale.ROOT)) {
            int a = scanner.nextInt();
            int b = scanner.nextInt();

            formatter.format("a=%d, b=%d, sum=%d", a, b, a + b);
        }

        System.out.println(result);
    }
}
~~~

Chạy:

~~~bash
javac ScannerFormatterDemo.java
java ScannerFormatterDemo
~~~

Stdout:

~~~text
a=8, b=13, sum=21
~~~

`Scanner` tiêu thụ nguồn triển khai `Readable`; `Formatter` ghi qua đích triển khai `Appendable`. Ở ví dụ trên đích là `StringBuilder` nên không có `IOException` do I/O đĩa. Nếu dùng `Writer` làm đích cho `Formatter`, lưu ý `Formatter` có thể ghi nhận lỗi I/O và cho truy vấn qua `formatter.ioException()`; việc gọi `format` không thay thế hoàn toàn kiểm tra lỗi đầu ra.

**Vòng đời tài nguyên:** `Scanner.close()` đóng nguồn nếu nguồn đó triển khai `Closeable`; `Formatter.close()` đóng đích nếu đích triển khai `Closeable`. Trong ví dụ, `StringBuilder` không cần đóng. Khi được **truyền** nguồn/đích từ bên ngoài vào một utility, không tự ý đóng chúng nếu hợp đồng sở hữu tài nguyên không giao quyền cho utility.

## 6. Thiết kế hàm có thể ghép từ các thành phần nhỏ

Giả sử nhiệm vụ là viết tiêu đề và tên vào nhiều loại đích. Nên khai báo kiểu tham số theo năng lực thực sự cần dùng:

~~~java
import java.io.IOException;

public final class GreetingWriter {
    private GreetingWriter() {}

    public static void writeGreeting(
            Appendable destination, CharSequence name) throws IOException {
        destination.append("Xin chào, ")
                   .append(name)
                   .append('!');
    }
}
~~~

Lớp này có thể biên dịch nhưng **không có `main`**; được gọi từ chương trình khác. Nó dùng được với `StringBuilder`, `StringBuffer` hoặc `Writer`. Kiểu trả về của các lệnh `append` được phép **covariant**: lớp triển khai như `StringBuilder` có thể trả về `StringBuilder` thay vì `Appendable` mà vẫn tuân thủ interface.

Tương tự, khai báo `Readable` cho API chỉ cần nhận luồng ký tự:

~~~java
static int firstCharacter(Readable source) throws IOException {
    java.nio.CharBuffer one = java.nio.CharBuffer.allocate(1);

    while (true) {
        int read = source.read(one);
        if (read == -1) {
            return -1; // Hết dữ liệu, không có ký tự đầu tiên.
        }
        if (read > 0) {
            one.flip();
            return one.get();
        }
        throw new IOException("Source made no progress");
    }
}
~~~

Mảnh mã trên cần nằm trong một lớp Java và có `import java.io.*` phù hợp. Đây cũng là chính sách **fail khi không có tiến độ**, không phải lời khuyên rằng mọi nguồn `Readable` đều phải ném lỗi khi tạm thời trả `0`.

**Nguyên tắc lựa chọn:** khai báo `Appendable` khi chỉ cần nối ký tự; dùng `Writer` khi cần `write(char[])`, `flush()` hay `close()` trong hợp đồng thao tác; dùng `Readable` khi chỉ cần `read(CharBuffer)`; dùng `Reader` khi cần `read(char[])`, `read()`, `close()` hoặc phương thức riêng của `Reader`. Đừng ép người gọi biến mọi nguồn thành `String` bằng `toString()`: một file lớn hoặc luồng vô hạn không thể xử lý hiệu quả theo cách đó.

## 7. `append`, `CharSequence` và các giới hạn dễ nhầm

### `append(csq, start, end)` không phải `substring` tự động

~~~java
StringBuilder builder = new StringBuilder();
builder.append("012345", 1, 4);
System.out.println(builder); // 123
~~~

Chỉ số bắt đầu **1** bao gồm, kết thúc **4** loại trừ. Nếu `start < 0`, `end > csq.length()` hoặc `start > end`, thao tác có thể báo `IndexOutOfBoundsException` theo hợp đồng. Chỉ số là đơn vị `char` (UTF-16): không tùy tiện cắt đôi surrogate pair nếu muốn giữ nguyên một Unicode code point.

### `append` chỉ hứa nhận thêm ký tự

- Giao diện không buộc thao tác append phải **nguyên tử**. Nếu đích I/O lỗi giữa chừng, dữ liệu có thể đã được ghi một phần.
- Giao diện không hứa thread safety. `StringBuilder` không đồng bộ; `StringBuffer` đồng bộ các thao tác riêng lẻ, nhưng điều đó không làm nhiều lệnh nối liên tiếp thành một giao dịch nguyên tử.
- Giao diện không hứa có `flush()`; nếu đích là `BufferedWriter`, bạn cần quyết định lúc nào flush/close dựa vào **chủ sở hữu đích**, không dựa vào type `Appendable`.
- Giao diện không hứa một `append` tương đương một bản tin hay một dòng. Với network/file protocol cần tự quy định khung/định dạng.

### `CharSequence` có thể thay đổi trong lúc dùng

`String` bất biến, nhưng `StringBuilder` hoặc `CharBuffer` có trạng thái/giới hạn thay đổi được. Tránh sửa nguồn khi một thao tác append khác đang đọc nội dung từ nó; hợp đồng `Appendable` không hứa tự chụp snapshot của mọi `CharSequence` ở mọi thời điểm.

## 8. Ghép với byte stream đúng charset

`Readable` và `Appendable` hoạt động trên ký tự Java (`char`/UTF-16). Để đọc/ghi dữ liệu file hoặc mạng ở dạng byte, cần tầng chuyển đổi rõ ràng:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileBridge {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("source.txt");
        Path target = Path.of("target.txt");

        try (BufferedReader reader =
                     Files.newBufferedReader(source, StandardCharsets.UTF_8);
             BufferedWriter writer =
                     Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
            ReadableAppendableDemo.copy(reader, writer);
        }
    }
}
~~~

Ví dụ này cần **`ReadableAppendableDemo.java`** từ mục 4 cùng thư mục để biên dịch; đồng thời cần `source.txt` tồn tại trước khi chạy. Biên dịch cả hai lớp:

~~~bash
javac ReadableAppendableDemo.java TextFileBridge.java
java TextFileBridge
~~~

Kết quả là **`target.txt`** nhận văn bản từ `source.txt` theo UTF-8; chương trình không in stdout. `Files.newBufferedReader/newBufferedWriter` chọn đúng charset tường minh; `try-with-resources` đóng cả nguồn và đích để flush đích khi thành công hoặc khi có ngoại lệ. Trong ứng dụng thực tế, nên xác định rõ hành vi ghi đè/tạo file mục tiêu và yêu cầu an toàn trước khi chạy.

**Giới hạn Unicode:** `Readable.read(CharBuffer)` đếm **UTF-16 code units**, không phải số byte UTF-8 hoặc số ký tự mà người dùng nhìn thấy. Một ký tự ngoài BMP có thể chiếm hai `char` (surrogate pair). Chuyển nối nguyên chuỗi `char` đúng thứ tự vào `Writer` tương thích thì bộ mã hóa có thể xử lý các cặp, nhưng tự mã hóa riêng từng chunk không đầy đủ dễ cắt đôi ký tự và làm hỏng dữ liệu. Khi cần đếm code point, dùng API code point riêng sau khi hiểu ranh giới văn bản.

## 9. Khi nào nên dùng interface nào?

| Yêu cầu | Loại đầu vào/đầu ra đề xuất | Lý do |
| --- | --- | --- |
| Chỉ cần tiêu thụ ký tự vào buffer | `Readable` | API nhận được nhiều nguồn hơn |
| Cần đọc ký tự theo mảng hoặc xử lý từng dòng | `Reader` / `BufferedReader` | Có các thao tác đọc tiện dụng |
| Chỉ cần thêm ký tự | `Appendable` | Có thể dùng `StringBuilder` hoặc `Writer` |
| Cần ghi mảng ký tự, flush hoặc đóng | `Writer` | Diễn đạt đầy đủ năng lực I/O |
| Cần định dạng dữ liệu ra nhiều loại đích | `Formatter(Appendable)` | Dựa vào hợp đồng append |
| Cần phân tích token từ nguồn khác nhau | `Scanner(Readable)` | Dựa vào hợp đồng đọc ký tự |
| Sao chép file nhị phân, ảnh, ZIP | `InputStream` / `OutputStream` hoặc byte channel | Không chuyển đổi qua `char` |
| Cần xử lý nội dung lớn | Streaming bằng buffer | Không giữ toàn bộ nội dung trong RAM |

Đừng chọn `Readable` chỉ vì tên nghe tổng quát hơn. Nếu bài toán cần biết EOF theo giao thức, cần truy cập ngẫu nhiên, xử lý số lượng byte chính xác, cần backpressure hoặc cần quản lý đóng/mở, những năng lực đó phải được thiết kế rõ thay vì giả định chúng có sẵn trong hai interface nhỏ.

## 10. Lỗi phổ biến và cách sửa

**Lỗi 1 — Một lần `read` phải đầy buffer.**  
Sai: bỏ qua số ký tự trả về; dùng cả `buffer.capacity()` làm dữ liệu hợp lệ.  
Đúng: dùng vị trí/limit sau `read`, `flip()` trước khi đưa buffer sang đích, sau đó `clear()`.

**Lỗi 2 — Xem `0` là EOF hoặc luôn quay vòng khi nhận 0.**  
Sai: `if (count == 0) break;` với mọi `Readable`, hoặc `while (count == 0) read(...)` không có cơ chế chờ.  
Đúng: `-1` là EOF; `0` cần xử lý theo đặc tính nguồn, nhất là non-blocking. Với utility chỉ hỗ trợ nguồn có tiến độ, có thể chủ động báo lỗi rõ ràng như ví dụ.

**Lỗi 3 — Dùng `append(buffer)` trước `flip()`.**  
Sai: buffer còn ở trạng thái viết, phần `CharSequence` lộ ra không phải dữ liệu vừa đọc.  
Đúng: chuyển buffer về trạng thái đọc rồi mới append.

**Lỗi 4 — Giả định `Appendable` cũng có `flush()` và `close()`.**  
Sai: ép kiểu thẳng sang `Writer` hoặc đóng tài nguyên do người gọi truyền vào.  
Đúng: chỉ dùng các phương thức của hợp đồng đã yêu cầu; thêm `Writer` hoặc khả năng riêng khi bài toán thật sự cần, và xác định ai sở hữu việc đóng.

**Lỗi 5 — Đổi byte stream thành text không xác định charset.**  
Sai: decode bằng charset mặc định ngoài ý muốn, hoặc xử lý mỗi đoạn byte như một string độc lập.  
Đúng: xác định charset, dùng `Reader`/`Writer` bọc quanh nguồn/đích byte và duy trì trạng thái decoder/encoder.

**Lỗi 6 — Cho rằng mọi `CharSequence` đều là `String` bất biến.**  
Sai: giả định dữ liệu không thay đổi khi `StringBuilder` hoặc `CharBuffer` vẫn được sửa.  
Đúng: chọn quy tắc sở hữu/mutability rõ ràng; chụp `toString()` khi thực sự cần snapshot và dữ liệu đủ nhỏ.

## 11. Câu hỏi tự kiểm tra

**1.** Một hàm chỉ cần nối văn bản vào đích bất kỳ; chọn tham số `Writer` hay `Appendable`?  
**Trả lời:** `Appendable` đủ nếu chỉ gọi `append`, giúp hàm nhận cả `StringBuilder`, `Writer` và kiểu tương thích khác.

**2.** Sau `read(CharBuffer)`, vì sao không append buffer ngay?  
**Trả lời:** Vị trí đang ở trạng thái ghi; phải `flip()` để `position=0` và `limit` chỉ đến cuối vùng vừa đọc.

**3.** `Readable` có bắt buộc `close()` không?  
**Trả lời:** Không. Một số lớp cụ thể như `Reader` hỗ trợ `close()`, nhưng bản thân `Readable` không yêu cầu.

**4.** `append(CharSequence, 2, 5)` dùng ranh giới nào?  
**Trả lời:** Lấy chỉ số 2, 3, 4; `end=5` là exclusive, tính theo UTF-16 `char`.

**5.** `Scanner` và `Formatter` liên quan gì đến hai giao diện này?  
**Trả lời:** `Scanner` có thể nhận một `Readable` làm nguồn; `Formatter` có thể ghi vào một `Appendable`. Chúng minh họa cách các API thư viện ghép với nhau theo hợp đồng tối thiểu.

**Ghi nhớ:** `Readable` định nghĩa **cách nhận ký tự từ nguồn**, `Appendable` định nghĩa **cách thêm ký tự vào đích**. `CharBuffer` nối hai thế giới qua `read → flip → append → clear`. Sức mạnh của chúng là khả năng thay thế nguồn/đích, với điều kiện bạn vẫn quản lý rõ số ký tự thực đọc, trạng thái buffer, encoding và vòng đời tài nguyên.
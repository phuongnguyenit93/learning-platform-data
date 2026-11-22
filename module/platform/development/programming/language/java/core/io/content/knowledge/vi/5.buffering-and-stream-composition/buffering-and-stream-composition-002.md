# BufferedReader và BufferedWriter trong Java I/O

`BufferedReader` và `BufferedWriter` là hai lớp xử lý **luồng ký tự có bộ đệm** trong gói `java.io`. Chúng bọc một `Reader` hoặc `Writer` khác để gom các thao tác nhỏ thành những đợt trao đổi dữ liệu lớn hơn, giảm chi phí gọi liên tục xuống nguồn hoặc đích bên dưới. `BufferedReader` còn có `readLine()` để đọc văn bản theo dòng; `BufferedWriter` có `newLine()` để viết dấu kết thúc dòng phù hợp với môi trường chạy.

Điều quan trọng là hiểu **bộ đệm thuộc luồng ký tự**, **cách xác định dòng**, **khi nào phải flush/close**, và những dữ liệu nào có thể bị thay đổi nếu đọc bằng `readLine()` rồi ghi bằng `newLine()`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả cách buffered character streams giảm chi phí I/O và phân biệt buffer nội bộ với mảng `char[]` do bạn cấp.
- Tạo `BufferedReader`, `BufferedWriter` từ `Reader`/`Writer` hoặc từ `Files.newBufferedReader/newBufferedWriter` với charset rõ ràng.
- Sử dụng `readLine()`, `read(char[])`, `write(...)`, `append(...)`, `newLine()` và `flush()` đúng hợp đồng.
- Xử lý chính xác `null` (EOF) và chuỗi rỗng `""` (dòng trống), đồng thời hiểu một lần `read` có thể trả về ít hơn số ký tự được yêu cầu.
- Chọn sao chép theo dòng hay theo khối ký tự tùy việc có cần giữ nguyên ký tự xuống dòng hay không.
- Kiểm soát việc đóng tài nguyên, giới hạn bộ nhớ và các lỗi hay gặp khi làm việc với văn bản Unicode.

## 2. Vị trí của hai lớp trong hệ thống Java I/O

Hai lớp không trực tiếp đại diện cho file hoặc mạng: chúng là **lớp bọc (decorator)** nhận một luồng ký tự đã có.

~~~text
Đọc file hoặc nguồn byte:
byte từ file/socket
    -> InputStream / lớp byte bên dưới
    -> InputStreamReader (giải mã byte theo charset)
    -> BufferedReader (buffer ký tự, readLine)
    -> ứng dụng

Ghi file hoặc đích byte:
ứng dụng
    -> BufferedWriter (buffer ký tự, newLine)
    -> OutputStreamWriter (mã hóa ký tự theo charset)
    -> OutputStream / lớp byte bên dưới
    -> byte đến file/socket
~~~

Với `Files.newBufferedReader(path, charset)` và `Files.newBufferedWriter(path, charset)`, Java tạo chuỗi thành phần cần thiết ở bên dưới; bạn không phải lắp thủ công từng lớp. Đối với text trong bộ nhớ, `StringReader` và `StringWriter` có thể thay thế phần file/byte.

| Thành phần | Đơn vị dữ liệu | Chức năng chính |
| --- | --- | --- |
| `InputStream` / `OutputStream` | Byte | Đọc/ghi dữ liệu nhị phân |
| `InputStreamReader` / `OutputStreamWriter` | Chuyển byte ↔ ký tự | Giải mã/mã hóa theo charset |
| `Reader` / `Writer` | Ký tự Java (UTF-16 `char`) | Hợp đồng trừu tượng đọc/ghi ký tự |
| `BufferedReader` | Ký tự, dòng | Bộ đệm để đọc và `readLine()` |
| `BufferedWriter` | Ký tự | Bộ đệm để ghi và `newLine()` |

**Lưu ý:** bọc `InputStream` bằng `BufferedReader` trực tiếp là sai kiểu: constructor của `BufferedReader` nhận `Reader`. Tương tự, `BufferedWriter` nhận `Writer`, không nhận `OutputStream`. Nếu cần chuyển đổi byte–ký tự, thêm `InputStreamReader` hoặc `OutputStreamWriter` với charset phù hợp.

### Constructor

~~~java
BufferedReader reader = new BufferedReader(existingReader);
BufferedReader customReader = new BufferedReader(existingReader, 16 * 1024);

BufferedWriter writer = new BufferedWriter(existingWriter);
BufferedWriter customWriter = new BufferedWriter(existingWriter, 16 * 1024);
~~~

Đây là **mảnh mã**: `existingReader` và `existingWriter` phải là các biến đã khai báo. Giá trị `16 * 1024` là **số ký tự** trong buffer nội bộ, không phải byte. Constructor có tham số kích thước yêu cầu `size > 0`, nếu không sẽ ném `IllegalArgumentException`. Constructor một tham số chọn dung lượng mặc định do triển khai cung cấp; không nên xây dựng logic đúng/sai dựa vào một con số buffer mặc định cụ thể.

## 3. `BufferedReader`: đọc ký tự và đọc dòng

`BufferedReader` kế thừa `Reader`, do đó có thể dùng như một `Reader` thông thường và có thêm những tiện ích quan trọng:

- `int read()`: đọc một đơn vị `char` (giá trị số không âm), hoặc `-1` nếu EOF.
- `int read(char[] cbuf, int off, int len)`: đọc tối đa `len` ký tự vào mảng từ chỉ số `off`; trả số ký tự thực nhận, `-1` nếu hết nguồn, hoặc `0` khi `len == 0`.
- `String readLine()`: đọc một dòng; trả chuỗi **không chứa** ký tự kết thúc dòng, hoặc `null` khi đã hết dữ liệu và không còn ký tự nào tạo nên dòng tiếp theo.
- `boolean ready()`: cho biết một thao tác đọc kế tiếp có thể thực hiện mà không bị chặn trong điều kiện được báo; **không phải phép kiểm tra EOF**.
- `mark(int readAheadLimit)` và `reset()`: đánh dấu và quay về vị trí đọc trước đó trong giới hạn cho phép; không phải tua lại cả nguồn tùy ý.
- `Stream<String> lines()`: tạo stream dòng lazy; tài nguyên bên dưới vẫn cần quản lý, và lỗi I/O khi duyệt có thể xuất hiện dưới dạng `UncheckedIOException`.

### Hợp đồng của `readLine()`

`readLine()` coi **LF** (`\n`), **CR** (`\r`) hoặc **CRLF** (`\r\n`) là ranh giới dòng. Dấu kết thúc không nằm trong `String` được trả về.

| Nội dung nguồn | Các giá trị `readLine()` lần lượt trả |
| --- | --- |
| `"red\nblue"` | `"red"`, `"blue"`, sau đó `null` |
| `"red\r\nblue\n"` | `"red"`, `"blue"`, sau đó `null` |
| `"\n"` | `""` (dòng rỗng), sau đó `null` |
| `""` | `null` ngay lần đầu |
| `"red\n\nblue"` | `"red"`, `""`, `"blue"`, rồi `null` |

Đặc biệt:

- **`null`** biểu thị không còn dòng để đọc; **`""`** là một dòng thật nhưng không có ký tự.
- Dòng cuối **không cần** kết thúc bằng newline vẫn được trả về.
- Một newline ở cuối nguồn kết thúc dòng trước đó; không mặc nhiên tạo thêm một dòng rỗng khác sau nó.
- Không thể dùng `readLine()` để biết chính xác dòng trước đó kết thúc bằng LF, CR, CRLF hay không có terminator: thông tin này đã bị loại bỏ.

Vòng lặp chuẩn:

~~~java
String line;
while ((line = reader.readLine()) != null) {
    process(line);
}
~~~

Đây là mảnh mã với `reader` là một `BufferedReader` đã tạo và `process` là thao tác riêng của ứng dụng. Không viết `while (!line.isEmpty())`, vì dòng trống **không phải EOF**. Cũng không dùng `reader.ready()` làm điều kiện lặp đọc tất cả các dòng.

## 4. `BufferedWriter`: ghi ký tự, xuống dòng và đẩy bộ đệm

`BufferedWriter` kế thừa `Writer`, hỗ trợ các phương thức:

- `write(int c)`: ghi một đơn vị `char`, phần 16 bit thấp của `c`.
- `write(char[] cbuf, int off, int len)`: ghi đúng vùng ký tự được yêu cầu.
- `write(String s)` và `write(String s, int off, int len)`: ghi chuỗi hoặc đoạn chuỗi.
- `append(CharSequence)`, `append(CharSequence, start, end)` và `append(char)`: bổ sung ký tự theo hợp đồng `Appendable`.
- `newLine()`: ghi chuỗi phân cách dòng do môi trường xác định.
- `flush()`: yêu cầu đẩy các ký tự đang giữ trong buffer xuống `Writer` bên dưới, đồng thời flush đối tượng bên dưới.
- `close()`: flush dữ liệu còn lại rồi đóng writer bên dưới; gọi nhiều lần được phép theo hợp đồng `Writer`.

Ví dụ:

~~~java
writer.write("Xin chào");
writer.newLine();
writer.append("Java");
writer.flush();
~~~

Đây là mảnh mã với biến `writer` đã khai báo. Nếu muốn tạo file văn bản mà không chờ đến `close()` mới đưa dữ liệu xuống tầng tiếp theo, có thể gọi `flush()` tại các mốc cần quan sát dữ liệu. Tuy nhiên, **flush không đồng nghĩa dữ liệu đã được đồng bộ bền vững xuống phần cứng**; bộ đệm của hệ điều hành và thiết bị lưu trữ vẫn tồn tại.

### `newLine()` so với ký tự `'\n'`

`newLine()` dùng chuỗi phân cách dòng do môi trường chạy quy định, thường ứng với `System.lineSeparator()`. Nếu định dạng file hoặc giao thức quy định chính xác byte/ký tự `LF`, hãy ghi `'\n'` theo quy ước đó, thay vì phụ thuộc newline của hệ điều hành.

Ví dụ file chuẩn hóa LF:

~~~java
writer.write("header");
writer.write('\n'); // Chính xác LF trong chuỗi ký tự
writer.write("value");
writer.write('\n');
~~~

Ngược lại, với file text dành cho thao tác thông thường trên máy hiện tại, `newLine()` có thể phù hợp hơn.

## 5. Chương trình Java 17+ chạy được: đọc theo dòng, ghi có buffer

Ví dụ này dùng nguồn và đích trong bộ nhớ để bạn quan sát chính xác cách `readLine()` bỏ terminator, nhận dòng trống và cách `newLine()` tạo terminator mới.

Tạo **`BufferedTextDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;

public class BufferedTextDemo {
    public static void main(String[] args) throws IOException {
        String input = "alpha\r\n\r\nbeta\n";
        StringWriter result = new StringWriter();
        int lines = 0;

        try (BufferedReader reader =
                     new BufferedReader(new StringReader(input), 4);
             BufferedWriter writer =
                     new BufferedWriter(result, 4)) {

            String line;
            while ((line = reader.readLine()) != null) {
                writer.write('[');
                writer.write(line);
                writer.write(']');
                writer.newLine();
                lines++;
            }
        }

        String visible = result.toString()
                .replace("\r\n", "\n")
                .replace('\r', '\n')
                .replace("\n", "\\n");

        System.out.println("lines=" + lines);
        System.out.println("content=" + visible);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BufferedTextDemo.java
java BufferedTextDemo
~~~

**Stdout chính xác, không phụ thuộc newline của Windows/Linux/macOS vì phần in đã chuẩn hóa:**

~~~text
lines=3
content=[alpha]\n[]\n[beta]\n
~~~

Giải thích:

1. Nguồn có ba dòng: `alpha`, dòng trống và `beta`. Lần `readLine()` thứ tư trả `null`, nên vòng lặp kết thúc.
2. Buffer nội bộ dung lượng 4 **không giới hạn** chiều dài dòng. `readLine()` có thể ghép nhiều lần đọc để tạo chuỗi dài hơn buffer.
3. Mỗi dòng được ghi kèm dấu `[ ]` và gọi `newLine()`. `BufferedWriter` có thể giữ dữ liệu tạm thời trước khi đưa xuống `StringWriter`.
4. `try-with-resources` đóng `writer` và đẩy phần ký tự còn lại. Việc đọc `result.toString()` sau đó là hợp lệ với `StringWriter`: lớp này vẫn cho phép truy xuất buffer qua `toString()` sau `close()`.
5. `replace("\r\n", "\n").replace('\r', '\n')` chuẩn hóa line ending để trình bày trên console; nó chỉ dùng cho minh họa, không làm thay đổi nguồn ban đầu.

Chọn cỡ buffer 4 chỉ nhằm làm rõ buffering; không nên kết luận 4 là kích thước tối ưu. Khi xử lý thực tế, ưu tiên cỡ mặc định trừ khi đo hiệu năng và chứng minh cần thay đổi.

## 6. Chương trình sao chép file UTF-8 và giữ nguyên ký tự xuống dòng

Khi dùng cặp `readLine()` / `newLine()`, ranh giới dòng của nguồn bị viết lại theo định dạng mới. Nếu mục tiêu là **sao chép chính xác chuỗi ký tự sau giải mã**, bao gồm cả CR, LF và CRLF như chúng xuất hiện, hãy đọc `char[]` và ghi đúng số ký tự vừa đọc.

Tạo file **`BufferedFileCopy.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class BufferedFileCopy {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("Usage: java BufferedFileCopy <source> <target>");
            return;
        }

        Path source = Path.of(args[0]);
        Path target = Path.of(args[1]);

        // Chỉ dùng khi source và target là hai file khác nhau.
        try (BufferedReader reader =
                     Files.newBufferedReader(source, StandardCharsets.UTF_8);
             BufferedWriter writer =
                     Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {

            char[] buffer = new char[4096];
            int count;

            while ((count = reader.read(buffer)) != -1) {
                writer.write(buffer, 0, count);
            }
        }
    }
}
~~~

Biên dịch và chạy với file `source.txt` đang tồn tại:

~~~bash
javac BufferedFileCopy.java
java BufferedFileCopy source.txt copy.txt
~~~

Chương trình **không in stdout** khi thành công. File `copy.txt` chứa nội dung văn bản nguồn được đọc và ghi lại bằng UTF-8; thứ tự các đơn vị `char`, bao gồm CR và LF, được giữ nguyên. Vì đầu vào và đầu ra cùng định nghĩa UTF-8, đây là cách sao chép **văn bản**. Nó **không phải công cụ sao chép byte nhị phân** và không hứa kết quả luôn trùng mọi byte của nguồn (ví dụ trường hợp BOM hoặc dữ liệu bị xử lý bởi decoder/encoder theo chính sách charset).

### Chú ý khi áp dụng

- `Files.newBufferedReader(source, UTF_8)` trả về `BufferedReader`. `Files.newBufferedWriter(target, UTF_8)` trả về `BufferedWriter`.
- Khi không truyền `OpenOption`, `newBufferedWriter` mặc định tạo file nếu chưa có, hoặc ghi đè bằng cách **truncate** nội dung file đích đã tồn tại. Vì vậy, **phải bảo đảm hai đường dẫn trỏ tới hai file khác nhau**; nếu cùng file (kể cả alias/hard link), file nguồn có thể bị cắt nội dung. Đây là giới hạn an toàn của ví dụ.
- Với output cần **append** cuối file, dùng đúng open options như `StandardOpenOption.CREATE` và `StandardOpenOption.APPEND`; không tưởng rằng `BufferedWriter` tự quyết định append.
- `char[4096]` là buffer **của ứng dụng**, khác với buffer riêng nằm bên trong `BufferedReader` và `BufferedWriter`.
- Một lần `reader.read(buffer)` **không bảo đảm lấp đầy mảng**. Chỉ `buffer[0]` đến `buffer[count - 1]` thuộc lần đọc ấy; phương thức `writer.write(buffer, 0, count)` tránh ghi ký tự cũ từ lần trước.
- Với file nhị phân hoặc yêu cầu giữ nguyên mọi byte, dùng `Files.copy(...)` hoặc luồng byte. Khi cần biến đổi line ending theo chủ đích, có thể chọn `readLine()` và ghi terminator rõ ràng.
- `try-with-resources` bảo đảm đóng cả hai luồng khi khối kết thúc, kể cả khi có lỗi. Trong trường hợp lỗi ghi, file đích có thể đã chứa **một phần dữ liệu**; ghi vào file tạm và di chuyển sau khi thành công có thể phù hợp với quy trình yêu cầu tính toàn vẹn.

## 7. Luồng ký tự, byte và Unicode: nên chọn đúng lớp

`BufferedReader`/`BufferedWriter` làm việc với đơn vị Java `char`, tức **UTF-16 code unit**, không phải byte UTF-8 và không nhất thiết trùng số Unicode code point. Ví dụ ký tự emoji ngoài BMP chiếm **hai** đơn vị `char` nhưng chỉ là một code point.

- Khi đọc bằng `read(char[])`, một cặp surrogate có thể nằm ở hai lần đọc khác nhau. Nếu chỉ chuyển các đoạn ký tự đúng thứ tự sang `Writer` cùng một quá trình mã hóa, không nên tự giả định mỗi khối đã chứa code point hoàn chỉnh.
- Tránh tạo một `String` rồi xử lý Unicode theo code point từ từng khối bất kỳ nếu khối có thể cắt giữa surrogate pair.
- Việc giải mã UTF-8 thuộc `InputStreamReader` hay tầng đọc do `Files.newBufferedReader` tạo ra, **không** thuộc riêng cơ chế buffering của `BufferedReader`.
- Nếu dùng `new FileReader(path)` hoặc `new FileWriter(path)` theo overload dựa vào default charset, kết quả có thể phụ thuộc môi trường/JDK. Ưu tiên chỉ rõ `StandardCharsets.UTF_8` ở ranh giới byte–text để dữ liệu có ý nghĩa nhất quán.

Chẳng hạn với socket:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

// Mảnh mã nằm trong phương thức có biến socket kiểu Socket:
BufferedReader reader = new BufferedReader(
        new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
~~~

Đây là **mảnh mã**, không phải chương trình độc lập. `readLine()` chờ cho đến khi nhận được ký tự kết thúc dòng, EOF hoặc gặp lỗi; nếu peer tiếp tục giữ socket mở nhưng không gửi newline, lệnh có thể chặn. Khi thiết kế giao thức mạng cần định nghĩa framing, kích thước dòng tối đa và timeout phù hợp.

## 8. `flush()`, `close()` và sự khác nhau giữa “ghi” và “đã tới đích”

Hình dung:

~~~text
Ứng dụng gọi write("abc")
        |
        v
BufferedWriter [buffer chứa "abc"]
        |
        | đủ chỗ hoặc flush()/close()
        v
Writer bên dưới -> encoder/file/socket -> hệ điều hành/thiết bị
~~~

`BufferedWriter.write(...)` thường có thể hoàn thành sau khi chỉ ghi vào buffer nội bộ, còn `flush()` chuyển dữ liệu tồn đọng sang writer bên dưới. `close()` cũng đẩy dữ liệu cần thiết rồi đóng writer bên dưới. `flush()` không phải lời hứa về durable persistence xuống thiết bị hay xác nhận peer đã đọc các byte qua mạng.

Chương trình độc lập minh họa `flush` bằng đích trong bộ nhớ, **`FlushDemo.java`**:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.StringWriter;

public class FlushDemo {
    public static void main(String[] args) throws IOException {
        StringWriter target = new StringWriter();

        try (BufferedWriter writer = new BufferedWriter(target, 8)) {
            writer.write("abc");
            writer.flush();
            System.out.println("afterFlush=" + target);
        }

        System.out.println("afterClose=" + target);
    }
}
~~~

Chạy:

~~~bash
javac FlushDemo.java
java FlushDemo
~~~

Kết quả:

~~~text
afterFlush=abc
afterClose=abc
~~~

Kích thước buffer 8 lớn hơn chuỗi `abc`. Sau `flush()`, dữ liệu đã tới `StringWriter` nên quan sát được trước khi đóng. Trong ứng dụng ghi file, nên dùng `try-with-resources` và **tránh gọi `flush` sau mỗi ký tự/dòng** trừ khi thật sự cần đầu ra xuất hiện ngay, bởi flush liên tục làm giảm lợi ích gom dữ liệu.

Nếu truyền một `Writer` do người gọi sở hữu vào helper, thiết kế cần thống nhất **ai được đóng đích**. Không tùy ý đóng writer của người gọi chỉ vì helper tạm bọc nó bằng `BufferedWriter`. Đóng lớp bọc thông thường kéo theo đóng đích bên dưới.

## 9. `readLine()` so với đọc theo khối `char[]`

| Tiêu chí | `readLine()` | `read(char[])` |
| --- | --- | --- |
| Đơn vị ứng dụng nhận | Một dòng `String` | Số ký tự thực đọc vào mảng |
| Newline nguồn | Bị loại khỏi chuỗi | Có thể giữ nguyên CR/LF |
| Kết thúc | `null` khi EOF | `-1` khi EOF và yêu cầu đọc dương |
| Dòng trống | `""` | Đơn vị không liên quan đến dòng |
| Giới hạn bộ nhớ | Có thể phải tích lũy **cả dòng** trong RAM | Buffer do chương trình chọn có giới hạn |
| Bài toán phù hợp | File cấu hình, bản ghi văn bản có newline | Sao chép ký tự, xử lý streaming và bảo toàn separator |

Nếu file có các dòng dài bất thường do dữ liệu không tin cậy, **`readLine()` không cung cấp tham số độ dài tối đa**. Kiểm tra `line.length()` sau khi `readLine()` đã hoàn thành có thể là quá muộn để ngăn tiêu thụ bộ nhớ lớn. Với giao thức không tin cậy, cần bộ đọc theo từng ký tự/khối có **giới hạn tích lũy**, bộ phân tích cú pháp chuyên dụng hoặc cơ chế định khung khác.

Nếu cần giữ chính xác separator từng dòng, `readLine()` không đủ vì nó xóa thông tin `\r`/`\n`/`\r\n`. Đọc theo khối và xử lý separator theo trạng thái, hoặc dùng API hỗ trợ bảo toàn nếu cần.

## 10. `ready()`, `mark()`, `reset()` và `lines()`

### `ready()` không có nghĩa “còn dữ liệu”

~~~java
if (reader.ready()) {
    int ch = reader.read();
}
~~~

Đoạn mã này chỉ hỏi khả năng đọc **mà không chặn** ở thời điểm đó, không xác định còn bao nhiêu dòng/ký tự, cũng không xác định EOF. Nguồn socket chưa có dữ liệu tức thời nhưng chưa kết thúc có thể chưa ready; từ đó không được suy luận “đã xong”. Vòng lặp đọc file nên dựa vào giá trị `-1` hoặc `null` của thao tác đọc thực tế.

### `mark()/reset()`: xem trước rồi đọc lại trong giới hạn

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class MarkResetDemo {
    public static void main(String[] args) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader("ABCDE"))) {
            reader.mark(3);
            System.out.println((char) reader.read());
            System.out.println((char) reader.read());
            reader.reset();
            System.out.println((char) reader.read());
        }
    }
}
~~~

Chạy:

~~~bash
javac MarkResetDemo.java
java MarkResetDemo
~~~

Stdout:

~~~text
A
B
A
~~~

`mark(3)` đặt giới hạn lưu ký tự cần giữ để `reset()`. Nếu đọc vượt xa `readAheadLimit`, việc reset không còn được bảo đảm; `reset()` có thể ném `IOException`. Không dùng `mark` làm cơ chế quay lại toàn bộ file có kích thước tùy ý.

### `lines()` là một stream lazy

~~~java
try (BufferedReader reader = java.nio.file.Files.newBufferedReader(
        java.nio.file.Path.of("source.txt"),
        java.nio.charset.StandardCharsets.UTF_8)) {
    reader.lines().filter(line -> !line.isBlank()).forEach(System.out::println);
}
~~~

Đây là đoạn mã chạy được **khi đặt trong phương thức có khai báo xử lý `IOException`**, ví dụ `main(String[] args) throws IOException`, và file `source.txt` tồn tại. `lines()` không háo hức đọc hết trước. Hãy duyệt stream **khi reader còn mở**; đóng stream không thay thế trách nhiệm đóng `BufferedReader`. Không xen kẽ việc gọi `readLine()` trên reader với duyệt `lines()` khi chưa kết thúc, vì cùng tiêu thụ một vị trí đọc. Các lỗi I/O xảy ra trong lúc duyệt có thể thành `UncheckedIOException`.

## 11. Các lỗi thường gặp

**Lỗi 1 — Xem dòng trống là hết dữ liệu.**

~~~java
// Sai: dừng sớm khi xuất hiện một dòng trống.
while (!(line = reader.readLine()).isEmpty()) {
    // ...
}
~~~

Đoạn trên còn có thể ném `NullPointerException` khi `readLine()` trả `null`. Cách đúng là so sánh với `null`, sau đó tùy nghiệp vụ quyết định xử lý hay bỏ qua dòng rỗng.

**Lỗi 2 — Quên `flush()` hoặc `close()`.**  
Nếu chỉ ghi vài ký tự vào buffer và chương trình ngừng dùng writer mà không đóng/flush, dữ liệu có thể vẫn nằm trong RAM và chưa đến writer bên dưới. Dùng `try-with-resources` cho tài nguyên tự sở hữu; gọi `flush()` khi thực sự cần đầu ra ngay.

**Lỗi 3 — Một lần `read(char[])` phải đầy mảng.**

~~~java
// Sai: count có thể nhỏ hơn buffer.length.
char[] buffer = new char[1024];
int count = reader.read(buffer);
if (count != -1) {
    writer.write(buffer); // Ghi cả ký tự chưa đọc/giá trị cũ.
}
~~~

Cách đúng là `writer.write(buffer, 0, count)`. Buffer là sức chứa; `count` là số ký tự hợp lệ.

**Lỗi 4 — Tưởng `readLine()/newLine()` giữ nguyên nội dung nguồn.**  
Đọc theo dòng xóa dấu kết thúc dòng, ghi `newLine()` thêm separator do môi trường chọn. Chỉ dùng khi **cho phép chuẩn hóa** line endings và chính sách thêm newline; để giữ chuỗi ký tự nguyên trạng, dùng `read(char[])`/`write(char[],off,len)`.

**Lỗi 5 — Chọn sai mức abstraction.**  
Không dùng bộ đệm ký tự để sao chép ZIP, ảnh, dữ liệu nén hoặc payload nhị phân. Dùng byte streams hoặc `Files.copy` cho byte. Cũng đừng tạo `BufferedReader` để hỏi tổng độ dài file: không có hợp đồng này.

**Lỗi 6 — Giả định buffering chữa mọi vấn đề hiệu năng.**  
Buffer giúp giảm nhiều lời gọi nhỏ xuống tầng bên dưới, nhưng không loại bỏ latency mạng, parsing tốn CPU hay chi phí mã hóa charset. Buffer quá lớn tốn bộ nhớ; buffer quá nhỏ có thể làm tăng số lần tương tác. Lựa chọn theo số liệu đo và khối lượng công việc.

**Lỗi 7 — Dùng file nguồn và đích giống nhau khi sao chép.**  
Nếu đích bị truncate khi mở, có thể phá dữ liệu trước khi đọc xong. Kiểm tra nguồn và đích khác nhau; nếu ghi đè an toàn là yêu cầu quan trọng, dùng file tạm và bước thay thế phù hợp.

**Lỗi 8 — Để giao thức mạng không có giới hạn dòng.**  
`readLine()` có thể chặn khi chưa có newline/EOF và có thể tiêu thụ rất nhiều RAM trên một dòng dài. Với dữ liệu bên ngoài, hãy quy định framing, độ dài tối đa, timeout, charset và chính sách lỗi.

## 12. Checklist thực hành

- [ ] Dữ liệu là **text** và charset đã được quy định rõ, ví dụ `UTF-8`?
- [ ] Đang dùng `BufferedReader`/`BufferedWriter` trên đúng tầng `Reader`/`Writer`?
- [ ] Vòng lặp `readLine()` kiểm tra `null`, không nhầm với `""`?
- [ ] Nếu đọc mảng `char[]`, chỉ ghi **`count`** ký tự vừa nhận?
- [ ] Có chủ đích giữ nguyên hoặc chuẩn hóa CR/LF/CRLF?
- [ ] Đã tính đến trường hợp dòng rất dài và luồng có thể chặn?
- [ ] `flush()` và `close()` phù hợp quyền sở hữu tài nguyên, có `try-with-resources` khi cần?
- [ ] Không dùng `ready()` để kết luận EOF và không áp đặt kích thước buffer như số ký tự chắc chắn đọc được?
- [ ] Khi ghi file, đã xét hành vi tạo/truncate/append và tránh tự ghi đè nguồn?

### Câu hỏi tự kiểm tra

**1.** `readLine()` trả `""`. Nguồn đã hết chưa?  
**Đáp án:** Chưa thể kết luận. Đó là một dòng rỗng hợp lệ; chỉ `null` cho biết không còn dòng.

**2.** Buffer nội bộ có 8192 ký tự nhưng một dòng dài 100.000 ký tự. `readLine()` sẽ trả gì?  
**Đáp án:** Có thể trả chuỗi toàn bộ 100.000 ký tự (nếu dòng hợp lệ/đủ dữ liệu và bộ nhớ), bởi nó ghép qua nhiều lượt đọc; buffer không đặt giới hạn dòng.

**3.** Vì sao `readLine()` rồi `newLine()` không thể bảo toàn file một cách chính xác theo ký tự?  
**Đáp án:** `readLine()` bỏ dấu CR/LF/CRLF và `newLine()` ghi dấu mới phụ thuộc môi trường, đồng thời có thể thêm terminator cho dòng cuối.

**4.** Khi nào nên gọi `flush()`?  
**Đáp án:** Khi dữ liệu cần chuyển xuống writer bên dưới trước lúc đóng, ví dụ một phản hồi phải gửi ngay. Khi dùng `try-with-resources` với file được đóng sau khi ghi xong, `close()` đã bao gồm việc đẩy buffer.

**5.** Buffer là ký tự hay byte?  
**Đáp án:** Bộ đệm của hai lớp này chứa **ký tự**; khi kết hợp với file byte, lớp mã hóa/giải mã phía dưới mới chuyển đổi giữa UTF-16 `char` của Java và byte theo charset.

**Ghi nhớ:** `BufferedReader` giúp đọc văn bản và từng dòng thuận tiện; `BufferedWriter` gom thao tác ghi và hỗ trợ xuống dòng. **Buffer chỉ cải thiện cách vận chuyển ký tự**; ứng dụng vẫn phải xử lý EOF, độ dài đọc thực, charset, ranh giới dòng, flush và quyền sở hữu tài nguyên.
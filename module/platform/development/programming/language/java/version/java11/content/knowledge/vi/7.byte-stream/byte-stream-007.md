# Reader.nullReader và Writer.nullWriter (Java 11+)

## 1. Bối cảnh: nguồn ký tự rỗng và nơi nhận ký tự không lưu dữ liệu

Khi xây dựng một luồng xử lý văn bản, đôi khi ứng dụng cần truyền vào một đối tượng `Reader` dù không có dữ liệu để đọc, hoặc một đối tượng `Writer` dù kết quả chủ động không cần được lưu. Từ **Java 11**, Java SE cung cấp trực tiếp hai phương thức tĩnh:

```java
Reader.nullReader()
Writer.nullWriter()
```

Chúng nằm trong gói `java.io` và vẫn là API phù hợp ở Java hiện đại:

- **`Reader.nullReader()`** trả về một `Reader` **không có ký tự nào**. Mọi lần đọc hợp lệ khi còn mở đều gặp *end of stream* (EOF) ngay.
- **`Writer.nullWriter()`** trả về một `Writer` **bỏ đi tất cả ký tự được ghi**. Lúc còn mở, những lời gọi ghi, thêm ký tự và flush hợp lệ không lưu bất kỳ nội dung nào.
- Dù tên chứa chữ `null`, cả hai **trả về một đối tượng thực sự, khác tham chiếu `null`**. Chúng có thể truyền cho API nhận `Reader`/`Writer` và có vòng đời `close()`.

Lưu ý quan trọng về ngữ cảnh **byte stream**: `Reader`/`Writer` làm việc với **ký tự** (các giá trị `char` UTF-16), trong khi `InputStream`/`OutputStream` làm việc với **byte**. Java 11 cũng có `InputStream.nullInputStream()` và `OutputStream.nullOutputStream()` cho byte stream. Không thay thế hai họ cho nhau khi kiểu tham số API yêu cầu khác nhau.

Mục tiêu bài học: hiểu đúng hợp đồng EOF và đầu ra bị bỏ đi, chọn tình huống sử dụng hợp lý, quản lý đóng luồng và chạy được một chương trình minh họa có kết quả xác định.

## 2. `Reader.nullReader()`: nguồn ký tự luôn hết dữ liệu

Chữ ký phương thức:

```java
public static Reader nullReader()
```

Đối tượng trả về ở trạng thái **đang mở**. Nó hoạt động như một nguồn đã hết ký tự ngay từ đầu, không phải nguồn trả về ký tự `'\0'`, chuỗi `"null"` hoặc một đối tượng Java `null`.

### 2.1. Giá trị trả về của các thao tác đọc

| Phương thức khi Reader đang mở | Kết quả hoặc ý nghĩa |
| --- | --- |
| `read()` | Trả `-1`: đã EOF, không có ký tự để đọc. |
| `read(char[] buffer)` với buffer dài hơn 0 | Trả `-1`: không đọc được ký tự nào vì EOF. |
| `read(buffer, off, len)` với `len > 0` hợp lệ | Trả `-1`. |
| `read(buffer, off, 0)` với tham số hợp lệ | Trả `0` vì yêu cầu đọc **0** ký tự. |
| `read(CharBuffer)` với vùng đệm còn chỗ | Thể hiện EOF, thường trả `-1`. |
| `ready()` | Trả `false`. |
| `skip(n)` với `n >= 0` | Trả `0`: không có ký tự để bỏ qua. |
| `transferTo(Writer)` | Trả `0L`: không có ký tự nào được chuyển. |
| `markSupported()` | Trả `false`. |

Đây là hành vi của **reader đặc biệt** tạo bởi `nullReader()`. Không được suy rộng rằng `ready() == false` của mọi `Reader` đều tương đương EOF; trên các reader khác, `ready()` chỉ cho biết liệu lần đọc tiếp theo có chắc chắn không phải đợi dữ liệu hay không.

Để phân biệt EOF và ký tự hợp lệ trong chương trình đọc một ký tự:

```java
try (Reader source = Reader.nullReader()) {
    int value = source.read();
    if (value == -1) {
        System.out.println("No characters");
    }
}
```

Đây là đoạn minh họa cần import `java.io.Reader` và được đặt trong phương thức có khai báo/xử lý `IOException`. `read()` trả về `int` để biểu diễn cả các giá trị ký tự hợp lệ và giá trị đặc biệt `-1` chỉ EOF.

### 2.2. EOF không có nghĩa Java trả về null

Hai cách hiểu sai thường gặp:

```java
Reader source = Reader.nullReader(); // source != null
int code = source.read();             // code == -1, KHÔNG phải 0 hay null
```

Biến `source` không phải `null`. Điều này tránh việc phải kiểm tra null khi API yêu cầu một nguồn đã đóng/mở theo hợp đồng `Reader`. Nhưng nếu nghiệp vụ **bắt buộc phải có dữ liệu đầu vào**, việc âm thầm thay nguồn bị thiếu bằng `nullReader` có thể che giấu lỗi; lúc đó nên báo lỗi rõ ràng.

### 2.3. `mark` và `reset` không được hỗ trợ

`Reader.nullReader()` báo `markSupported() == false`. Gọi `mark(int)` hoặc `reset()` sẽ ném `IOException`; không thể đánh dấu vị trí hay quay lại, vì nguồn này không chứa dữ liệu. Không chọn `nullReader` cho code bắt buộc hỗ trợ `mark/reset`.

## 3. `Writer.nullWriter()`: nơi ghi ký tự và chủ động bỏ dữ liệu

Chữ ký:

```java
public static Writer nullWriter()
```

`Writer` trả về ở trạng thái **đang mở**. Những thao tác hợp lệ như `write(...)`, `append(...)` và `flush()` **không ghi nội dung vào tệp, buffer hay thiết bị nào**:

```java
try (Writer sink = Writer.nullWriter()) {
    sink.write("Xin chào");
    sink.write(new char[] {'A', 'B'}, 0, 2);
    sink.append('!').append(" OK");
    sink.flush();
}
```

Đây là một đối tượng `Writer` hợp lệ cho pipeline cần một đích ghi mà kết quả được **chủ động bỏ qua**. `flush()` không thể đẩy dữ liệu ra ngoài vì không có dữ liệu được lưu.

Không đồng nhất nó với:
- `StringWriter`: ghi ký tự vào vùng nhớ để sau đó gọi `toString()` lấy văn bản.
- `BufferedWriter`: lưu đệm rồi chuyển ký tự sang một writer khác.
- `FileWriter` hoặc `Files.newBufferedWriter`: ghi tệp thật.
- `PrintWriter`: wrapper cung cấp các phương thức `print/println/format` trên writer/stream khác; hành vi xử lý lỗi khác với `Writer` cơ bản.

`nullWriter()` không cung cấp `toString()` để lấy nội dung đã ghi. Khi bạn cần kiểm tra nội dung đầu ra trong test, `StringWriter` thường là lựa chọn phù hợp hơn.

### 3.1. Nơi nên dùng

- **Một nhánh đầu ra tùy chọn:** ứng dụng có giao diện yêu cầu `Writer` nhưng người dùng đã chọn tắt kênh xuất.
- **Đo hiệu năng một phần pipeline:** vẫn cho chạy logic tạo dữ liệu ký tự trong khi bỏ chi phí lưu vào tệp hoặc buffer đầu ra; kết quả đo chỉ có ý nghĩa khi bạn biết phần nào đang được đo.
- **Test đơn giản về luồng điều khiển và xử lý ngoại lệ:** code có thể nhận một writer hợp lệ và gọi `write` mà không sinh file.
- **Ghép nối code nhận `Reader`/`Writer`:** tránh dùng `null` khi bạn có chủ đích muốn đầu vào rỗng hoặc đầu ra bỏ qua.

Một cảnh báo thiết thực: **việc ghi thành công vào `Writer.nullWriter()` không chứng minh nội dung đã được lưu**. Đừng dùng nó cho dữ liệu bắt buộc phải ghi như log kiểm toán, kết quả nghiệp vụ, thông tin cần phục hồi hay tài liệu xuất cho người dùng. Nếu một kênh bắt buộc bị thiếu, phải xử lý lỗi thay vì âm thầm bỏ dữ liệu.

## 4. Vòng đời: mở, `close()` và try-with-resources

Cả hai factory đều tạo đối tượng **đang mở**. Chúng triển khai `Closeable`/`AutoCloseable` thông qua `Reader` và `Writer`, nên dùng được với `try-with-resources`:

```java
try (Reader input = Reader.nullReader();
     Writer output = Writer.nullWriter()) {
    // Hai đối tượng hợp lệ trong vùng try.
}
```

Khi thoát khối `try`, Java tự gọi `close()` theo thứ tự ngược lại. Gọi `close()` lần hai hoặc nhiều lần không gây tác dụng bổ sung (*idempotent close*).

Sau khi một `nullReader` bị đóng, các lời gọi như `read()`, `ready()`, `skip()` và `transferTo()` ném `IOException`. Sau khi `nullWriter` bị đóng, các phương thức ghi, `append` và `flush()` ném `IOException`. **Đừng hiểu rằng “không có dữ liệu thật” thì trạng thái đóng/mở không quan trọng.**

```java
Reader source = Reader.nullReader();
source.close();
// source.read(); // IOException: source đã đóng.

Writer sink = Writer.nullWriter();
sink.close();
// sink.write("x"); // IOException: sink đã đóng.
```

Hai dấu comment minh họa **lời gọi có thể biên dịch nhưng sẽ lỗi lúc chạy** nếu bỏ comment và có khai báo/xử lý ngoại lệ. Đây không phải lỗi cú pháp Java. Nếu chỉ cần viết mã dùng một lần, `try-with-resources` dễ đọc và tránh bỏ quên đóng luồng.

## 5. Ví dụ chạy được bằng Java 11+: đọc rỗng, ghi bỏ qua, sao chép

Tạo tệp **`NullCharacterStreamsDemo.java`**:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;

public class NullCharacterStreamsDemo {
    private static long copy(Reader source, Writer destination)
            throws IOException {
        char[] buf = new char[256];
        long total = 0;
        int n;
        while ((n = source.read(buf)) != -1) {
            destination.write(buf, 0, n);
            total += n;
        }
        destination.flush();
        return total;
    }

    public static void main(String[] args) throws IOException {
        try (Reader empty = Reader.nullReader()) {
            char[] four = new char[4];
            System.out.println("single=" + empty.read());
            System.out.println("array=" + empty.read(four, 0, four.length));
            System.out.println("zeroLength=" + empty.read(four, 0, 0));
            System.out.println("ready=" + empty.ready());
            System.out.println("skip=" + empty.skip(10));
            System.out.println("markSupported=" + empty.markSupported());
            try (StringWriter capture = new StringWriter()) {
                System.out.println("emptyTransfer=" + empty.transferTo(capture));
                System.out.println("capturedLength=" + capture.toString().length());
            }
        }

        try (Writer sink = Writer.nullWriter()) {
            sink.write("Java");
            sink.write(new char[] {'1', '1'}, 0, 2);
            sink.append('!').append(" OK");
            sink.flush();
            System.out.println("discardWrite=ok");
        }

        try (Reader source = new StringReader("Hi!\n");
             Writer sink = Writer.nullWriter()) {
            System.out.println("discardCount=" + copy(source, sink));
        }

        try (Reader source = Reader.nullReader();
             StringWriter output = new StringWriter()) {
            System.out.println("emptyCopy=" + copy(source, output));
            System.out.println("emptyOutput=" + output.toString().length());
        }

        Reader closedReader = Reader.nullReader();
        closedReader.close();
        closedReader.close();
        try {
            closedReader.read();
        } catch (IOException ex) {
            System.out.println("readerAfterClose=" + ex.getClass().getSimpleName());
        }

        Writer closedWriter = Writer.nullWriter();
        closedWriter.close();
        closedWriter.close();
        try {
            closedWriter.write('x');
        } catch (IOException ex) {
            System.out.println("writerAfterClose=" + ex.getClass().getSimpleName());
        }
        try {
            closedWriter.flush();
        } catch (IOException ex) {
            System.out.println("flushAfterClose=" + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch với compiler hỗ trợ Java 11; tên tệp phải trùng tên `public class`:

```bash
javac -encoding UTF-8 --release 11 NullCharacterStreamsDemo.java
java NullCharacterStreamsDemo
```

**Kết quả đã kiểm chứng trên JDK 24 với `javac --release 11`:**

```text
single=-1
array=-1
zeroLength=0
ready=false
skip=0
markSupported=false
emptyTransfer=0
capturedLength=0
discardWrite=ok
discardCount=4
emptyCopy=0
emptyOutput=0
readerAfterClose=IOException
writerAfterClose=IOException
flushAfterClose=IOException
```

Giải thích kết quả theo thứ tự:

1. `single=-1` và `array=-1` xác nhận nguồn đã EOF ngay. `zeroLength=0` là **lời gọi yêu cầu đọc 0 phần tử**, không mâu thuẫn với EOF. Vòng lặp đọc nên kiểm tra `-1` và chỉ xử lý dữ liệu khi có số ký tự thực sự được đọc.
2. `ready=false`, `skip=0`, `markSupported=false` là đặc tính của reader rỗng này. `transferTo` không chuyển ký tự nào nên `emptyTransfer=0`, `capturedLength=0`.
3. `discardWrite=ok` chỉ xác nhận các lời gọi trên writer mở đã thực thi, **không có output được lưu**.
4. Trong `copy`, chuỗi `"Hi!\n"` gồm **4 đơn vị `char`**: `H`, `i`, `!` và xuống dòng `\n`. `discardCount=4` là số ký tự pipeline đã chuyển cho sink; nó không nói rằng writer đã lưu 4 ký tự.
5. Khi nguồn là `Reader.nullReader()`, `copy` dừng ngay vì EOF: `emptyCopy=0`, `emptyOutput=0`.
6. Sau `close()`, cả việc đọc và ghi/flush đều ném `IOException`. Việc gọi `close()` nhiều lần không làm thay đổi kết quả.

Phương thức `copy` là một ví dụ tổng quát đơn giản: đọc lần lượt vào `char[]`, viết đúng số ký tự thực sự đọc được, cộng dồn và flush. Trong dự án thật, nếu chỉ cần sao chép nội dung ký tự, Java đã có `Reader.transferTo(Writer)`, cũng dùng được từ Java 10; với `nullReader` nó trả `0`. `transferTo` **không tự đóng** source hay destination, nên caller cần quản lý vòng đời.

## 6. Cách dùng trong API nhận Reader/Writer

Giả sử có một hàm phân tích văn bản nhận `Reader`:

```java
static long countCharacters(Reader in) throws IOException {
    long count = 0;
    char[] buffer = new char[1024];
    int n;
    while ((n = in.read(buffer)) != -1) {
        count += n;
    }
    return count;
}
```

Khi **nghiệp vụ chủ động quy định “không có nội dung” là đầu vào hợp lệ**, caller có thể dùng:

```java
try (Reader in = Reader.nullReader()) {
    System.out.println(countCharacters(in)); // 0
}
```

Cả hai là **đoạn mã minh họa bên trong lớp**, cần import `java.io.Reader` và `java.io.IOException`. Hàm đếm số **đơn vị mã UTF-16** được đọc, không phải số Unicode code point hay số ký tự hiển thị. Đối với các yêu cầu đếm code point hoặc grapheme cluster, phải xử lý ở mức phù hợp.

Với đầu ra tùy chọn:

```java
static void writeReport(Writer out) throws IOException {
    out.write("report: ready\n");
    out.flush();
}

// Chỉ khi yêu cầu nghiệp vụ nói rõ "bỏ output".
try (Writer out = Writer.nullWriter()) {
    writeReport(out);
}
```

Các đoạn này cũng là **mảnh mã minh họa** trong lớp và không phải chương trình hoàn chỉnh độc lập. Một `Writer.nullWriter()` không giúp xác nhận output đúng nội dung. Nếu bạn cần kiểm tra văn bản trong unit test, đổi sang:

```java
try (StringWriter output = new StringWriter()) {
    writeReport(output);
    System.out.println(output.toString()); // report: ready
}
```

Tùy tình huống, còn có thể sử dụng `new StringReader("nội dung")` để mô phỏng input có ký tự thay vì nguồn EOF.

## 7. So sánh với byte stream và các lớp liên quan

Do bài học đặt trong ngữ cảnh byte stream, cần phân biệt **đơn vị xử lý** khi chọn sink/source:

| API | Đơn vị dữ liệu | Hành vi | Bắt đầu có từ |
| --- | --- | --- | --- |
| `Reader.nullReader()` | Ký tự (`char`) | EOF ngay. | Java 11 |
| `Writer.nullWriter()` | Ký tự (`char`) | Bỏ mọi ký tự ghi vào. | Java 11 |
| `InputStream.nullInputStream()` | Byte | EOF ngay cho byte stream. | Java 11 |
| `OutputStream.nullOutputStream()` | Byte | Bỏ mọi byte ghi vào. | Java 11 |
| `StringReader(String)` | Ký tự (`char`) | Đọc từ nội dung chuỗi đã cấp. | API Java hiện hành |
| `StringWriter` | Ký tự (`char`) | Tích lũy output trong bộ nhớ để xem lại. | API Java hiện hành |

Ví dụ Java khi API yêu cầu byte stream:

```java
import java.io.InputStream;
import java.io.OutputStream;

try (InputStream in = InputStream.nullInputStream();
     OutputStream out = OutputStream.nullOutputStream()) {
    System.out.println(in.read()); // -1
    out.write(65);                  // Bỏ byte 65
}
```

Đây là **mảnh mã minh họa** và cần đặt trong một phương thức có xử lý `IOException`. Đừng truyền một `Reader` vào nơi cần `InputStream`; compiler sẽ báo không tương thích kiểu. Khi thực sự cần chuyển từ byte sang ký tự hoặc ngược lại, chọn lớp cầu nối như `InputStreamReader`/`OutputStreamWriter` và **charset rõ ràng** (thường là `StandardCharsets.UTF_8`). Hai null factory không tự thực hiện mã hóa hay giải mã văn bản.

Đặc biệt, một ký tự Unicode ngoài BMP có thể được biểu diễn bởi **hai `char` UTF-16**, còn ở UTF-8 có thể gồm nhiều byte. Số ký tự `copy` trả về không phải số byte trên đĩa hay số *user-perceived characters*. Bản chất của `Reader`/`Writer` vẫn là **character streams**.

## 8. Hạn chế và điều kiện sử dụng an toàn

### 8.1. Không suy luận có dữ liệu được lưu

`sink.write("abc")` chạy xong không có nghĩa `"abc"` được ghi vào tệp hay buffer. `Writer.nullWriter` là **đích hủy dữ liệu có chủ đích**. Nếu API trả về “xuất báo cáo thành công” sau khi dùng null writer mà nghiệp vụ cần file thật, đó là lỗi thiết kế nghiệp vụ, không phải lỗi Java.

Tương tự, `Reader.nullReader` đại diện **dòng đầu vào rỗng**, không phải một cách đọc file bị thiếu mà vẫn giữ ý nghĩa nghiệp vụ. Nếu file bắt buộc phải tồn tại, hãy dùng I/O thật và xử lý trường hợp không mở được.

### 8.2. Vẫn có chi phí xử lý trước khi ghi

Dù sink bỏ dữ liệu, các biểu thức chuẩn bị nội dung có thể vẫn được đánh giá:

```java
String expensive = buildText(); // Tạo dữ liệu trước khi gọi writer
sink.write(expensive);          // Sink bỏ nội dung, nhưng buildText vẫn đã chạy
```

Đây là **mã minh họa** với `buildText` và `sink` do ứng dụng cung cấp. Không coi `nullWriter` là công tắc tắt mọi chi phí CPU, format, truy vấn dữ liệu hoặc logging. Muốn tránh tạo dữ liệu khi tắt đầu ra, phải thiết kế nhánh điều khiển ở tầng gọi phù hợp.

### 8.3. Không dùng luồng sau khi đã đóng

Khi dùng chung một `Reader`/`Writer` giữa các lớp, phải xác định **ai sở hữu quyền đóng**. Nếu một hàm nhận writer do caller tạo rồi tự đóng, caller có thể gặp `IOException` khi tiếp tục ghi. Quy tắc đóng luồng đúng với cả null streams, vì chúng có trạng thái đóng/mở theo hợp đồng.

### 8.4. Không giả định chúng là singleton hoặc buffer

Mỗi factory được mô tả là trả về một stream mới. Không dùng `==` để biểu đạt “hai nguồn rỗng giống nhau”, không tìm dữ liệu đã ghi bằng `getBuffer()`/`toString()`, và không trông chờ vào các chi tiết nội bộ, tên lớp cụ thể hoặc đối tượng `lock` được trả về. Chỉ dựa vào hợp đồng của API.

### 8.5. Không nhầm `Reader.nullReader()` với `StringReader("")`

Cả hai có thể cho EOF khi đọc một nguồn rỗng, nhưng mục đích và API bổ trợ không giống nhau:
- `Reader.nullReader()` nói rõ ý định **không có input** và không hỗ trợ `mark/reset`.
- `new StringReader("")` là reader trên một chuỗi có nội dung rỗng, với tập hành vi riêng (ví dụ `mark/reset` được hỗ trợ).
- Cần **dữ liệu thử nghiệm cụ thể** thì dùng `StringReader("sample")`; cần **đầu vào rỗng theo hợp đồng** thì dùng `Reader.nullReader()`.

## 9. Lỗi thường gặp và cách xử lý

| Lỗi | Vì sao sai | Cách dùng đúng |
| --- | --- | --- |
| `Reader in = null; in.read();` | Gọi phương thức trên tham chiếu `null` gây `NullPointerException`. | Nếu nguồn rỗng hợp lệ, dùng `Reader.nullReader()`. |
| Đợi `nullReader.read()` trả `0` cho lần đọc một ký tự | `read()` dùng `-1` báo EOF. | Kiểm tra `-1`; riêng lời gọi đọc `0` ký tự có thể trả `0`. |
| Dùng `ready()==false` như quy tắc EOF cho mọi reader | `ready` không phải phép thử EOF tổng quát. | Dựa vào `read()==-1` hoặc số đọc `-1`. |
| Gọi `mark/reset` trên `nullReader` | Loại reader này không hỗ trợ đánh dấu. | Kiểm tra `markSupported` hoặc chọn reader hỗ trợ. |
| Cho rằng `nullWriter.write(...)` lưu nội dung | Nó cố ý bỏ ký tự. | Dùng `StringWriter` nếu cần kiểm tra output, hoặc writer thật để lưu. |
| Gọi `flush` hay `write` sau `close` | Null writer vẫn có trạng thái đóng. | Dùng writer trong phạm vi còn mở, ưu tiên `try-with-resources`. |
| Dùng `nullWriter` khi ghi tệp là bắt buộc | Âm thầm mất dữ liệu nghiệp vụ. | Dùng writer thật và xử lý lỗi I/O đúng mức. |
| Truyền `Reader` thay cho `InputStream` | Khác kiểu và đơn vị dữ liệu. | Chọn họ API phù hợp hoặc bộ chuyển byte/ký tự có charset. |
| Dùng số đếm `char` làm số byte/Unicode code point | `char` là đơn vị mã UTF-16. | Xác định đại lượng cần đếm trước khi chọn thuật toán. |
| Nghĩ bỏ output nghĩa là mọi xử lý trước `write` bị bỏ qua | Chuẩn bị dữ liệu vẫn diễn ra. | Đặt điều kiện ở tầng tạo dữ liệu khi cần tránh công việc đó. |

## 10. Bài tập tự đánh giá

**Câu 1.** Đoạn dưới đây có ném `NullPointerException` không?

```java
Reader r = Reader.nullReader();
System.out.println(r.read());
```

**Trả lời:** Không, nếu đặt trong ngữ cảnh có import và xử lý `IOException`. `r` là đối tượng hợp lệ. Lời gọi `read()` trả `-1`.

**Câu 2.** Đang mở `Writer w = Writer.nullWriter();`, gọi `w.write("Hello"); w.flush();` có tạo tệp `Hello` hay buffer trong bộ nhớ không?

**Trả lời:** Không. Các ký tự bị bỏ đi. Muốn lưu chuỗi để test, dùng `StringWriter`; muốn tạo tệp, dùng file writer hoặc `Files`.

**Câu 3.** Vì sao `Reader.nullReader().read(new char[10], 0, 0)` có thể trả `0` trong khi một lời gọi đọc buffer có độ dài dương trả `-1`?

**Trả lời:** Lần thứ nhất yêu cầu đọc đúng **0** ký tự, nên thành công mà không đọc. Lần thứ hai muốn đọc dữ liệu nhưng gặp EOF ngay.

**Câu 4.** Dùng `Reader.nullReader().transferTo(Writer.nullWriter())` sẽ trả số lượng bao nhiêu khi hai luồng đang mở?

**Trả lời:** `0L`, vì nguồn không có ký tự nào để chuyển. Khi viết mã thật, cần quản lý đóng cả hai stream theo quyền sở hữu.

**Câu 5.** Có thể dùng `Writer.nullWriter()` như một kênh output của pipeline khi người dùng chọn “không xuất file” không?

**Trả lời:** Có, **nếu việc bỏ output là một trạng thái nghiệp vụ được chủ động chấp nhận và thể hiện rõ**. Nếu output bắt buộc hoặc liên quan lưu trữ quan trọng, không được âm thầm thay writer thật bằng null writer.

**Câu 6.** Để bỏ 100 byte khi ghi dữ liệu nhị phân, dùng `Writer.nullWriter()` hay `OutputStream.nullOutputStream()`?

**Trả lời:** `OutputStream.nullOutputStream()` vì đó là byte stream. `Writer.nullWriter()` dành cho ký tự; không cùng đơn vị dữ liệu.

**Câu 7.** Sau `Reader r = Reader.nullReader(); r.close();`, gọi `r.read()` có còn trả `-1` nữa không?

**Trả lời:** Không. Khi đã đóng, `read()` ném `IOException`. EOF là kết quả khi reader **còn mở**.

## 11. Ghi nhớ và tài liệu chuẩn

- Hai factory `Reader.nullReader()` và `Writer.nullWriter()` được bổ sung từ **Java 11**, vẫn dùng được với Java hiện đại.
- `nullReader`: nguồn ký tự rỗng hợp lệ; khi đang mở, đọc gặp EOF, `read() == -1`; `markSupported() == false`.
- `nullWriter`: đích ghi ký tự hợp lệ nhưng **không giữ dữ liệu**; ghi/append/flush khi đang mở không sinh output.
- Cả hai có trạng thái đóng/mở: `close()` có thể gọi lặp lại; sử dụng sau khi đóng gây `IOException` trong các thao tác I/O.
- `Reader`/`Writer` xử lý **ký tự UTF-16**; `InputStream`/`OutputStream` xử lý **byte**. Chọn đúng kiểu API nhận dữ liệu.
- Sử dụng khi đầu vào rỗng hoặc đầu ra bị loại bỏ là **chủ ý**. Khi muốn kiểm chứng nội dung, chọn `StringReader`/`StringWriter` hoặc luồng thật phù hợp.

Tài liệu API chính thức:
- [Java SE 11 — Reader.nullReader()](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/Reader.html#nullReader()).
- [Java SE 11 — Writer.nullWriter()](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/Writer.html#nullWriter()).
- [Java SE 11 — InputStream.nullInputStream()](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html#nullInputStream()).
- [Java SE 11 — OutputStream.nullOutputStream()](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/OutputStream.html#nullOutputStream()).
- [Java SE 11 — Reader.transferTo(Writer)](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer)).
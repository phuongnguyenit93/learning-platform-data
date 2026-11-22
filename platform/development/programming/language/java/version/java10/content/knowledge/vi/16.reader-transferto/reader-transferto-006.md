# Quyền sở hữu tài nguyên và việc đóng `Reader`, `Writer` khi dùng `Reader.transferTo` (Java 10+)

## 1. Mục tiêu và kết luận cốt lõi

`java.io.Reader.transferTo(Writer out)` được giới thiệu từ **Java 10** để chuyển toàn bộ ký tự còn lại trong một `Reader` sang một `Writer`. Phương thức này giúp thay vòng lặp đọc/ghi ký tự thủ công bằng một lời gọi ngắn:

~~~java
long copiedCharacters = reader.transferTo(writer);
~~~

**Quy tắc quan trọng nhất:** `transferTo` **không đóng `reader` và cũng không đóng `writer`**. Việc đóng tài nguyên là trách nhiệm của đoạn code **sở hữu** các đối tượng ấy, theo hợp đồng API. Java không mặc nhiên chuyển quyền sở hữu chỉ vì một `Reader` được yêu cầu ghi dữ liệu sang `Writer`.

Bài học tập trung vào câu hỏi: **Ai phải gọi `close()`, và khi nào?** Sau bài này, bạn sẽ hiểu:

- `Reader.transferTo(Writer)` thực sự làm gì, làm gì **không** làm.
- Phân biệt tài nguyên **do chính hàm mở** với tài nguyên **được caller truyền vào**.
- Sử dụng `try-with-resources` để quản lý `Reader` và `Writer` mà không đóng nhầm tài nguyên người khác sở hữu.
- Thứ tự đóng khi có nhiều tài nguyên, tác dụng của `close()`, `flush()` và các wrapper.
- Cách xử lý `IOException`, ngoại lệ trong `close()` và **suppressed exceptions**.
- Những rủi ro khi thao tác với `System.in`, `System.out`, writer được dùng chung hoặc dữ liệu đầu ra đang ghi dở.
- Cách thiết kế hàm copy dễ tái sử dụng và dễ kiểm thử.

**Phiên bản:** `Reader.transferTo(Writer)` có từ Java 10 và còn áp dụng trong Java hiện đại. Các ví dụ chạy độc lập dưới đây dùng **JDK 17+**, không phụ thuộc tính năng preview hay API đã lỗi thời.

## 2. Hợp đồng chính thức của `Reader.transferTo`

Chữ ký:

~~~java
public long transferTo(Writer out) throws IOException
~~~

Hành vi được định nghĩa:
1. Đọc tất cả ký tự còn lại từ `Reader` hiện tại.
2. Ghi các ký tự đó sang `Writer out` theo thứ tự đọc được.
3. Trả về **số ký tự đã chuyển**, kiểu `long`, nếu hoàn tất thành công.
4. Khi hoàn tất bình thường, `Reader` đã đến **cuối luồng (EOF)**.
5. Không gọi `close()` trên `Reader` hoặc `Writer`.

Nếu `out == null`, phương thức ném `NullPointerException`. Nếu đọc/ghi lỗi, `IOException` có thể phát sinh **sau khi đã chuyển một phần dữ liệu**; không có cam kết rollback.

~~~java
Reader reader = new StringReader("Java 10");
Writer writer = new StringWriter();

long count = reader.transferTo(writer);

System.out.println(count);             // 7
System.out.println(writer.toString()); // Java 10
System.out.println(reader.read());     // -1, đã ở EOF
~~~

Đây là đoạn minh họa cần import `java.io.Reader`, `Writer`, `StringReader`, `StringWriter`, và đặt trong phương thức khai báo `throws IOException` hoặc có `try/catch`.

**Lưu ý quan trọng:** `reader.read() == -1` sau khi chuyển **không có nghĩa reader đã bị đóng**. EOF chỉ là trạng thái không còn ký tự để đọc. Một `Reader` đã đóng thường không cho đọc tiếp, nhưng hành vi sau `close()` của từng implementation cần xem hợp đồng của lớp đó.

### Số ký tự khác với số byte

`transferTo` thao tác trên **ký tự** (`char`/đơn vị UTF-16 mà `Reader` cung cấp), không phải byte thô:

~~~java
var source = new StringReader("A😀B");
var target = new StringWriter();
long chars = source.transferTo(target);

System.out.println(chars);                 // 4
System.out.println(target.toString());     // A😀B
~~~

Chuỗi trên có ba **Unicode code points** (`A`, emoji, `B`), nhưng emoji được biểu diễn bằng một *surrogate pair* gồm hai đơn vị UTF-16; `String.length()` là 4 và lượng ký tự `Reader` chuyển cũng là 4. Đừng dùng số trả về làm số byte của tệp UTF-8 hay số ký tự người dùng nhìn thấy.

### Không tự đóng cũng không đồng nghĩa tự flush

Tài liệu `transferTo` cam kết **không đóng** hai đối tượng, nhưng **không đưa ra bảo đảm rằng mọi writer sẽ được `flush()`** sau lời gọi. Nếu bạn dùng `BufferedWriter` hoặc writer có bộ đệm, việc gửi dữ liệu đi ngay lập tức có thể cần `flush()` **theo hợp đồng của bên sở hữu writer**. Nếu một writer được đóng đúng cách, implementation thường xử lý các bộ đệm theo đặc tả `close()` của nó.

Không nên viết helper tự động `flush()` hay `close()` mọi writer được truyền vào nếu caller còn cần tiếp tục ghi; một API nên định nghĩa rõ chính sách đó.

## 3. “Quyền sở hữu tài nguyên” có nghĩa là gì?

Trong Java, quyền sở hữu (*resource ownership*) là **quy ước thiết kế và hợp đồng API**, không phải một kiểu dữ liệu được Java tự động suy ra. Câu hỏi cần trả lời là: đoạn code nào chịu trách nhiệm hoàn tất vòng đời một reader/writer và giải phóng tài nguyên mà nó quản lý?

Quy tắc thực hành hữu ích:

| Tình huống | Ai thường sở hữu? | Ai đóng? |
| --- | --- | --- |
| Hàm tự gọi `Files.newBufferedReader(path)` | Hàm mở reader | Hàm đó, thường bằng `try-with-resources` |
| Hàm tự gọi `Files.newBufferedWriter(path)` | Hàm mở writer | Hàm đó, thường bằng `try-with-resources` |
| Caller truyền `Reader` vào helper `copy(reader, writer)` | Caller, trừ khi API nói rõ chuyển quyền sở hữu | Caller |
| Caller truyền `Writer` vào helper | Caller, trừ khi API nói rõ chuyển quyền sở hữu | Caller |
| Thư viện nhận một writer dùng chung để ghi log/báo cáo | Thành phần tạo và quản lý writer | Thành phần ấy, không phải helper ghi một lần |
| Wrapper như `BufferedReader` bọc một reader khác | Phụ thuộc hợp đồng về việc ai tạo wrapper/luồng nền | Đóng wrapper thường đóng cả luồng nền |

**Nguyên tắc mặc định an toàn:** *Hàm chỉ mượn tài nguyên từ caller thì không nên đóng tài nguyên ấy.* Hàm **tự mở** tài nguyên thì nên đóng trước khi trả về hoặc để một owner rõ ràng quản lý tiếp.

Không có ranh giới ngữ nghĩa nào trong `Reader.transferTo` tự “chuyển quyền sở hữu” writer sang reader. `reader.transferTo(writer)` chỉ chuyển **nội dung**.

## 4. Mẫu A: Hàm tự mở cả Reader và Writer — tự đóng cả hai

Khi hàm tự mở hai tệp, nó chịu trách nhiệm đóng hai tài nguyên:

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileTextCopy {
    public static long copy(Path source, Path destination)
            throws IOException {

        try (Reader reader =
                    Files.newBufferedReader(source, StandardCharsets.UTF_8);
             Writer writer =
                    Files.newBufferedWriter(destination, StandardCharsets.UTF_8)) {

            return reader.transferTo(writer);
        }
    }
}
~~~

**Đây là tệp class minh họa hoàn chỉnh có phương thức `copy`, nhưng không có `main`; muốn chạy phải gọi từ một chương trình khác.** Mục 8 có chương trình demo đầy đủ với lệnh `javac`/`java`.

Diễn giải:
1. `Files.newBufferedReader` mở reader và dùng bộ giải mã UTF-8.
2. `Files.newBufferedWriter` mở writer và dùng bộ mã hóa UTF-8.
3. `reader.transferTo(writer)` chuyển ký tự, **không tự đóng** luồng.
4. Khi rời khối `try`, `try-with-resources` gọi `close()` cho các tài nguyên đã khởi tạo thành công.
5. Vì khai báo reader **trước**, writer **sau**, writer được **đóng trước reader** (ngược thứ tự khai báo).
6. Nếu đóng writer gặp `IOException`, phương thức có thể ném lỗi dù phần `transferTo` đã hoàn tất và tính được `long`; không được coi việc có số đếm ký tự là bảo đảm toàn bộ ghi/flush/close thành công.

**Thận trọng với tệp đích:** `Files.newBufferedWriter` với tùy chọn mặc định có thể tạo mới hoặc cắt ngắn tệp đích đã tồn tại. Nếu không muốn thay thế dữ liệu, lựa chọn `StandardOpenOption.CREATE_NEW` hoặc chiến lược ghi qua tệp tạm theo yêu cầu ứng dụng. `transferTo` không cung cấp giao dịch cập nhật tệp nguyên tử.

Mã sử dụng **text Reader/Writer**, phù hợp khi cần giải mã/mã hóa ký tự. Nếu phải sao chép tệp *nhị phân* giữ nguyên byte, hãy dùng API byte như `Files.copy` hoặc `InputStream.transferTo(OutputStream)`, thay vì đi qua Reader/Writer.

## 5. Mẫu B: Helper nhận Reader và Writer của caller — không tự đóng

Hãy thiết kế helper **mượn** tài nguyên một cách rõ ràng:

~~~java
static long transferBorrowed(Reader input, Writer output) throws IOException {
    return input.transferTo(output);
}
~~~

Đoạn này đặt trong một lớp có import `java.io.Reader`, `Writer`, `IOException`; chính nó không tự mở hoặc đóng stream nào.

Caller quyết định vòng đời:

~~~java
try (Reader reader = Files.newBufferedReader(pathIn, StandardCharsets.UTF_8);
     Writer writer = Files.newBufferedWriter(pathOut, StandardCharsets.UTF_8)) {

    long transferred = transferBorrowed(reader, writer);
    System.out.println("Transferred chars: " + transferred);
}
~~~

Đây là đoạn minh họa cần biến `pathIn`, `pathOut` kiểu `Path` và các import tương ứng.

Lợi ích của nguyên tắc này:
- Helper có thể được gọi giữa nhiều lần đọc/ghi trên cùng writer.
- Caller có thể tiếp tục `writer.write(...)` sau lời gọi.
- Caller có quyền `flush()` tại thời điểm cần và đóng khi xong toàn bộ công việc.
- Helpers dễ kết hợp với `StringReader`, `StringWriter`, file streams, network streams hoặc writer được ứng dụng quản lý.

### Vì sao đóng writer của caller bên trong helper là rủi ro?

~~~java
static long badTransfer(Reader input, Writer output) throws IOException {
    try (output) { // KHÔNG đúng nếu output do caller sở hữu.
        return input.transferTo(output);
    }
}
~~~

Nếu caller muốn dùng tiếp `output`, helper đã đóng nó khi thoát khỏi `try`. Với file/network writer, việc ghi tiếp có thể thất bại. Ngoại trừ trường hợp API **nêu rõ chuyển quyền sở hữu**, helper như trên thường tạo ra bug vòng đời khó phát hiện.

**Không nên chốt dựa trên `StringWriter`**: `StringWriter.close()` không có tác động thông thường, nên test với `StringWriter` có thể che giấu lỗi đóng nhầm writer. Hãy kiểm thử cả với một writer theo dõi hoặc từ chối thao tác sau khi đóng, hoặc đọc hợp đồng writer thực tế.

## 6. Mẫu C: Hàm tự mở Reader nhưng nhận Writer từ caller — chỉ đóng Reader

Một phương thức hỗn hợp có thể mở tài nguyên đầu vào nhưng **mượn đầu ra**:

~~~java
static long appendFileToWriter(Path source, Writer destination)
        throws IOException {

    try (Reader input =
                 Files.newBufferedReader(source, StandardCharsets.UTF_8)) {
        return input.transferTo(destination);
    }
    // Không đóng destination: caller vẫn sở hữu writer.
}
~~~

Đây là đoạn minh họa trong một lớp có import `Path`, `Files`, `StandardCharsets`, `Reader`, `Writer`, `IOException`.

Hợp đồng nên được mô tả như sau:
- Hàm **đóng reader do nó tự mở**, cả khi copy thành công hoặc lỗi.
- Hàm **không đóng writer được truyền vào**.
- Hàm **không cam kết tự flush writer**; caller quyết định khi nào flush hoặc close.
- Nếu `transferTo` ném `IOException` giữa chừng, writer có thể đã nhận một phần dữ liệu. Caller phải quyết định có tiếp tục, hủy hay đóng writer.

Trong ứng dụng thực tế, hãy viết rõ các hành vi này trong tài liệu phương thức, nhất là với các API thư viện công khai.

## 7. `try-with-resources`: cơ chế và thứ tự đóng

`Reader` và `Writer` triển khai `Closeable`/`AutoCloseable`, nên có thể khai báo trong `try-with-resources`:

~~~java
try (Reader input = openInput();
     Writer output = openOutput()) {

    input.transferTo(output);
}
~~~

Đây là **đoạn minh họa**, `openInput()`/`openOutput()` là hai phương thức giả định cần được định nghĩa; chương trình đầy đủ ở mục 8 sử dụng lớp cụ thể.

Quy tắc:
- Các tài nguyên được **khởi tạo từ trái sang phải**.
- Các tài nguyên đã khởi tạo thành công được **đóng từ phải sang trái**.
- Nếu khởi tạo writer thất bại sau khi reader đã mở, reader đã được khởi tạo vẫn được đóng.
- Nếu `transferTo` thành công, `close()` vẫn được thực hiện khi rời block, kể cả có `return`.
- Nếu `transferTo` ném ngoại lệ, `close()` vẫn được cố gắng thực hiện cho tất cả tài nguyên.
- Nếu đóng nhiều tài nguyên cùng lỗi, Java dùng **suppressed exceptions** để không làm mất thông tin lỗi.

Ví dụ với hai tài nguyên:

~~~text
Khởi tạo: reader → writer
Transfer: reader.transferTo(writer)
Đóng:     writer → reader
~~~

Bạn có thể khai báo tài nguyên đã tạo bên ngoài vào `try` nếu biến **final hoặc effectively final** (cú pháp có từ Java 9):

~~~java
Reader input = new StringReader("Java");
Writer output = new StringWriter();

try (input; output) {
    input.transferTo(output);
}
~~~

**Cẩn thận:** chỉ đưa tài nguyên của bạn hoặc tài nguyên đã được caller **ủy quyền đóng** vào `try-with-resources`. `try(input; output)` sẽ đóng cả hai, dù chúng được khai báo từ trước. *Effectively final* là điều kiện để dùng biến có sẵn, **không** đồng nghĩa code tự động trở thành owner hợp lệ.

### Khi bọc Reader/Writer bằng wrapper

~~~java
var underlying = Files.newBufferedReader(path, StandardCharsets.UTF_8);
var wrapped = new java.io.BufferedReader(underlying);
~~~

Đoạn trên minh họa quan hệ wrapper, **không phải mã hoàn chỉnh có bảo đảm đóng tài nguyên**.

Đóng `wrapped` thông thường sẽ đóng cả reader nền mà nó bọc. Vì vậy:
- Không để một helper đóng wrapper đang dùng chung nếu caller vẫn cần underlying reader.
- Tránh quản lý trùng lặp cả wrapper và underlying reader trong nhiều tầng với những owner khác nhau.
- Khi **chính bạn tạo chuỗi wrapper hoàn chỉnh**, thường quản lý **wrapper ngoài cùng** bằng `try-with-resources`; nó sẽ đóng tài nguyên nền theo hợp đồng wrapper.
- Nếu wrapper bọc một luồng **không thuộc sở hữu của bạn**, đừng đóng wrapper khi thao tác `close()` sẽ lan xuống luồng nền — trừ khi hợp đồng cho phép.

Một lỗi thường gặp là bọc `System.out` bằng `OutputStreamWriter`, sau đó đưa wrapper vào `try-with-resources`; khi wrapper đóng, `System.out` cũng có thể bị đóng, ảnh hưởng những phần còn lại của chương trình.

## 8. Chương trình Java 17+ độc lập: chứng minh ai đóng và khi nào

Tạo tệp **ReaderTransferOwnershipDemo.java**:

~~~java
import java.io.FilterReader;
import java.io.FilterWriter;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;

public class ReaderTransferOwnershipDemo {

    static final class TraceReader extends StringReader {
        boolean closed;

        TraceReader(String content) {
            super(content);
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("close reader");
            super.close();
        }
    }

    static final class TraceWriter extends StringWriter {
        boolean closed;

        @Override
        public void close() {
            closed = true;
            System.out.println("close writer");
            // StringWriter không giữ tài nguyên file.
        }
    }

    static final class FailingCloseReader extends FilterReader {
        FailingCloseReader() {
            super(new StringReader("X"));
        }

        @Override
        public void close() throws IOException {
            throw new IOException("reader close failed");
        }
    }

    static final class FailingCloseWriter extends FilterWriter {
        FailingCloseWriter() {
            super(new StringWriter());
        }

        @Override
        public void close() throws IOException {
            throw new IOException("writer close failed");
        }
    }

    // Hàm chỉ mượn Reader/Writer: không close, không flush.
    static long copyBorrowed(Reader input, Writer output)
            throws IOException {
        return input.transferTo(output);
    }

    static void borrowedExample() throws IOException {
        var input = new TraceReader("Hi");
        var output = new TraceWriter();

        // Caller quản lý cả hai tài nguyên.
        try (input; output) {
            long chars = copyBorrowed(input, output);

            System.out.println("borrowed chars = " + chars);
            System.out.println("borrowed text = " + output.toString());
            System.out.println("borrowed still open = "
                    + (!input.closed && !output.closed));

            // Vẫn ghi tiếp được vì copyBorrowed không đóng output.
            output.write("!");
            System.out.println("borrowed appended = "
                    + output.toString());
        }

        System.out.println("borrowed closed = "
                + (input.closed && output.closed));
    }

    static void ownedExample() throws IOException {
        var input = new TraceReader("A\nB");
        var output = new TraceWriter();

        try (input; output) {
            long chars = input.transferTo(output);
            System.out.println("owned chars = " + chars);
            System.out.println("owned text = "
                    + output.toString().replace("\n", "|"));
            System.out.println("reader at EOF = "
                    + (input.read() == -1));
            System.out.println("owned open in block = "
                    + (!input.closed && !output.closed));
        }

        System.out.println("owned closed = "
                + (input.closed && output.closed));
    }

    static void failureExample() {
        // Cố ý tạo lỗi ở cả thân try và hai thao tác close.
        try (var input = new FailingCloseReader();
             var output = new FailingCloseWriter()) {

            input.transferTo(output);
            throw new IOException("body failed");

        } catch (IOException ex) {
            System.out.println("primary = " + ex.getMessage());
            for (int i = 0; i < ex.getSuppressed().length; i++) {
                System.out.println("suppressed[" + i + "] = "
                        + ex.getSuppressed()[i].getMessage());
            }
        }
    }

    public static void main(String[] args) throws IOException {
        borrowedExample();
        ownedExample();
        failureExample();
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac ReaderTransferOwnershipDemo.java
java ReaderTransferOwnershipDemo
~~~

**Đầu ra chính xác:**

~~~text
borrowed chars = 2
borrowed text = Hi
borrowed still open = true
borrowed appended = Hi!
close writer
close reader
borrowed closed = true
owned chars = 3
owned text = A|B
reader at EOF = true
owned open in block = true
close writer
close reader
owned closed = true
primary = body failed
suppressed[0] = writer close failed
suppressed[1] = reader close failed
~~~

### Phân tích từng phần

**Mục borrowed:**
- `copyBorrowed` chuyển hai ký tự `H`, `i` và **không đóng** `TraceReader` hoặc `TraceWriter`.
- Biểu thức `borrowed still open = true` xác nhận cả hai chưa có lời gọi `close()` khi hàm helper trả về.
- Caller ghi tiếp dấu `!` vào writer thành `Hi!`.
- Khi thoát `try (input; output)`, Java đóng **output trước input**, đúng thứ tự ngược với khai báo.
- Sau khối, cả hai được đánh dấu đã đóng.

**Mục owned:**
- `"A\nB"` dài 3 đơn vị `char`, nên `transferTo` trả `3`.
- `reader.read() == -1` xác nhận đã đến EOF; cả hai vẫn chưa bị đóng **ngay trong khối try**.
- Khi rời khối, `try-with-resources` gọi `close()` cho writer rồi reader.

**Mục failure:**
- Sau khi chuyển dữ liệu, ví dụ **cố ý** ném `IOException("body failed")` từ thân `try`.
- Trong lúc dọn dẹp, writer đóng trước và ném `IOException("writer close failed")`; reader đóng sau và ném `IOException("reader close failed")`.
- Lỗi từ thân `try` là **primary exception**. Hai lỗi khi đóng được gắn vào `getSuppressed()` theo thứ tự writer, reader.
- Ví dụ minh họa cơ chế quản lý ngoại lệ của `try-with-resources`; không dùng các lớp `FailingClose...` này cho I/O thật.

**Ghi chú về `TraceWriter`:** đây là một lớp theo dõi tự định nghĩa dựa trên `StringWriter`; phương thức `close()` của nó chỉ ghi nhận sự kiện. Vì `StringWriter` không đại diện cho file hoặc socket nên không dùng ví dụ này làm bằng chứng rằng **mọi writer đều cho phép ghi sau khi đã đóng**. Trong ví dụ, thao tác ghi tiếp chỉ diễn ra **trước** lúc caller đóng writer.

## 9. Khi `transferTo` thất bại: đóng tài nguyên và xử lý dữ liệu dở

`Reader.transferTo` có thể ném `IOException` trong lúc:
- Đọc dữ liệu từ `Reader`;
- Ghi dữ liệu xuống `Writer`;
- Làm việc với nguồn/đích bị lỗi, bị đóng từ nơi khác hoặc không thể tiếp tục I/O.

Khi lỗi xảy ra, **một số ký tự có thể đã được đọc hoặc ghi**. Đừng giả định reader vẫn ở vị trí ban đầu, writer không nhận dữ liệu, hay file đích còn nguyên.

~~~java
try (Reader reader =
             Files.newBufferedReader(source, StandardCharsets.UTF_8);
     Writer writer =
             Files.newBufferedWriter(destination, StandardCharsets.UTF_8)) {

    long copied = reader.transferTo(writer);
    System.out.println("Transferred: " + copied);

} catch (IOException ex) {
    System.err.println("Copy failed: " + ex.getMessage());
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("Close also failed: " + suppressed);
    }
}
~~~

Đây là đoạn minh họa trong phương thức có `source`, `destination` kiểu `Path`, cùng import `Files`, `StandardCharsets`, `Reader`, `Writer`, `IOException`.

`try-with-resources` giúp **đóng tài nguyên đã mở dù copy lỗi**. Tuy nhiên, **đóng thành công không có nghĩa tự khôi phục nội dung đầu ra đã ghi một phần**.

Nếu tác vụ yêu cầu “thành công trọn vẹn hoặc giữ nguyên tệp cũ”, hãy thiết kế thêm bước ghi ra tệp tạm, kiểm tra hoàn tất và thay thế đích khi đủ điều kiện. `Reader.transferTo` không cung cấp atomic transaction cho tệp.

### Ngoại lệ khi đóng cũng quan trọng

Một `Writer` có bộ đệm có thể phát sinh lỗi khi `flush()`/`close()`; nếu code chỉ xử lý lỗi từ `transferTo`, bạn có thể bỏ qua lỗi ở giai đoạn hoàn tất đầu ra.

`try-with-resources` giúp gọi `close()` và không im lặng nuốt lỗi: nếu thân try thành công nhưng close thất bại, exception từ close có thể được ném; nếu thân try đã có lỗi, lỗi close thường nằm trong `getSuppressed()`.

**Không tự biến mọi lỗi close thành log rồi tiếp tục coi thao tác thành công** khi yêu cầu dữ liệu đầu ra phải được ghi đầy đủ.

## 10. `flush()` và `close()`: khác nhau về mục đích

| Thao tác | Ý nghĩa chủ yếu | Có tự động giải phóng toàn bộ tài nguyên không? |
| --- | --- | --- |
| `reader.transferTo(writer)` | Đọc ký tự từ reader, ghi sang writer | Không |
| `writer.flush()` | Yêu cầu writer đẩy dữ liệu đang được đệm theo hợp đồng | Không |
| `writer.close()` | Đóng writer, giải phóng tài nguyên và xử lý việc hoàn tất theo implementation | Có, đối với tài nguyên writer sở hữu |
| `reader.close()` | Đóng reader, giải phóng tài nguyên nguồn | Có, đối với tài nguyên reader sở hữu |
| `try-with-resources` | Gọi `close()` cho các resource đã khai báo khi rời khối | Có, theo cơ chế của từng `AutoCloseable` |

Khi writer thuộc về caller, một API kiểu `appendTo(writer)` cần ghi rõ **có flush hay không**. Có nhiều trường hợp hợp lý:
- **Helper không flush:** caller gom nhiều thao tác ghi rồi flush một lần để tối ưu hiệu năng.
- **Helper flush theo hợp đồng:** phù hợp khi lời gọi phải làm dữ liệu khả dụng ngay, nhưng cần cân nhắc chi phí và hành vi của writer.
- **Helper không đóng:** đây thường là mặc định đối với writer mượn từ caller.

Việc `flush()` có làm dữ liệu tồn tại vĩnh viễn trên thiết bị lưu trữ hay không là câu hỏi khác: `Writer.flush()` không phải bảo đảm *fsync* hay giao dịch bền vững.

### Không đóng nhầm `System.out`

Ví dụ minh họa in dữ liệu text ra console:

~~~java
try (Reader input =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

    Writer console = new OutputStreamWriter(
            System.out, StandardCharsets.UTF_8);

    input.transferTo(console);
    console.flush(); // Muốn nội dung hiện ra ngay.
    // KHÔNG đưa console vào try-with-resources ở đây:
    // close wrapper có thể đóng System.out.
}
~~~

Đoạn này cần import `Reader`, `Writer`, `OutputStreamWriter`, `Files`, `StandardCharsets` và biến `path` kiểu `Path`; đây là **đoạn minh họa không độc lập**.

Lưu ý cần thiết kế vòng đời wrapper đúng với hệ thống. Wrapper `OutputStreamWriter` ở đây không có owner đóng riêng vì `System.out` là luồng dùng chung do runtime quản lý; không nên áp dụng mẫu này cho một socket hoặc file **do bạn sở hữu**, vì khi đó bỏ đóng có thể gây rò rỉ tài nguyên.

## 11. Những tình huống ownership điển hình

| Tình huống | Khuyến nghị |
| --- | --- |
| Hàm `copyText(Path from, Path to)` mở cả hai file | Dùng `try-with-resources`, đóng cả hai |
| Hàm `copy(Reader in, Writer out)` nhận cả hai từ caller | Không đóng hai tài nguyên; mô tả hợp đồng rõ |
| Hàm mở file `Reader` nhưng nhận `Writer out` | Đóng reader tự mở, giữ writer của caller |
| Hàm nhận reader nhưng tự mở file writer | Đóng writer tự mở, không đóng reader mượn |
| Viết vào writer dùng chung qua nhiều lời gọi | Không đóng writer trong từng helper |
| Wrapper `BufferedWriter` trên file do helper mở | Đóng wrapper ngoài cùng trong `try-with-resources` |
| Wrapper `OutputStreamWriter` trên `System.out` | Tránh đóng wrapper nếu close lan xuống `System.out`; flush theo nhu cầu |
| Có lỗi giữa lúc chuyển dữ liệu | Đảm bảo dọn dẹp nguồn/đích do mình sở hữu, xử lý file dở |
| Cần đóng có thứ tự khi nhiều resource | Nhớ `try-with-resources` đóng **ngược thứ tự khai báo** |
| Transfer xong nhưng caller cần ghi tiếp | Helper không đóng; caller quản lý ghi tiếp và flush/close |

Các lựa chọn trên là **quy ước API**. Nếu hệ thống có giao kèo chuyển quyền sở hữu rõ ràng khác đi, hãy tuân theo giao kèo và ghi rõ cho người gọi.

## 12. Các lỗi và hiểu lầm thường gặp

### Hiểu lầm 1 — “`Reader.transferTo` tự đóng Reader và Writer”

Không. Hợp đồng Java 10+ nói rõ phương thức **không đóng cả hai**. Nếu bạn tự mở file reader/writer mà chỉ gọi `transferTo` rồi bỏ đó, có nguy cơ rò rỉ tài nguyên hoặc chưa hoàn tất dữ liệu đệm.

### Hiểu lầm 2 — “Hàm nhận writer làm tham số thì phải đóng writer sau khi ghi”

Không mặc nhiên. Caller thường sở hữu writer được truyền vào. Đóng writer trong helper có thể làm hỏng các thao tác tiếp theo hoặc đóng ngầm file/socket/standard stream.

### Hiểu lầm 3 — “EOF nghĩa là Reader đã đóng”

Không. `transferTo` thành công đưa reader đến EOF nhưng **không gọi `close()`**. Đừng nhầm trạng thái dữ liệu đã đọc hết với vòng đời tài nguyên.

### Hiểu lầm 4 — “Khi hàm return trong try, `close()` không chạy”

Sai. `try-with-resources` vẫn thực hiện đóng các tài nguyên do nó quản lý trước khi thoát khối, kể cả khi có `return`; lỗi close có thể ảnh hưởng kết quả bằng một exception.

### Hiểu lầm 5 — “Hai resource được đóng đúng thứ tự khai báo”

Sai. Chúng được đóng **ngược thứ tự khởi tạo**. Nếu khai báo `reader` trước `writer`, writer đóng trước.

### Hiểu lầm 6 — “`StringWriter.close()` không gây lỗi, nên mọi Writer đóng rồi vẫn ghi được”

Sai. `StringWriter` là implementation đặc biệt trong bộ nhớ. File writer, socket writer, `BufferedWriter` và wrapper có thể xử lý sau close rất khác nhau. Đừng suy luận chung từ `StringWriter`.

### Hiểu lầm 7 — “`transferTo` bảo đảm flush ngay”

Không có bảo đảm chung như vậy trong hợp đồng của phương thức. Khi cần gửi dữ liệu đệm đi ngay, caller hoặc owner nên quyết định `flush()` dựa trên writer thực tế.

### Hiểu lầm 8 — “Có lỗi thì chưa ký tự nào được chuyển”

Sai. Việc đọc/ghi có thể đã tiến hành một phần trước khi ném `IOException`. Không có rollback hoặc cơ chế atomic commit mặc định.

### Hiểu lầm 9 — “Đóng nhiều wrapper độc lập trên cùng một stream là vô hại”

Không nên giả định. Đóng wrapper thường lan xuống stream nền. Nếu nhiều thành phần cùng nghĩ mình sở hữu một stream, có thể đóng sớm hoặc đóng trùng, gây lỗi khó chẩn đoán. Hãy chỉ định một owner rõ ràng.

### Hiểu lầm 10 — “`try (borrowedReader; borrowedWriter)` không sao vì biến là effectively final”

Điều kiện effectively final chỉ là **điều kiện cú pháp**. `try-with-resources` sẽ gọi `close()` cả hai object. Nếu thuộc caller, việc tự đóng trong helper vẫn vi phạm hợp đồng ownership.

### Hiểu lầm 11 — “Mọi ký tự được đếm tương ứng với một byte”

Sai. `Reader`/`Writer` xử lý ký tự; số `long` trả về không phải dung lượng byte của tệp. Số byte phụ thuộc encoding và nội dung.

### Hiểu lầm 12 — “`try-with-resources` nuốt hết lỗi close”

Sai. Khi vừa có lỗi trong body vừa có lỗi close, các lỗi close có thể nằm trong danh sách suppressed của lỗi chính. Nếu không có lỗi trước, lỗi close có thể được ném trực tiếp.

## 13. Tự kiểm tra kiến thức

**Câu 1.** `reader.transferTo(writer)` có tự đóng `reader` và `writer` không?

**Đáp án:** Không. Việc đóng thuộc về chủ sở hữu các tài nguyên theo hợp đồng.

**Câu 2.** Hàm `copy(Reader input, Writer output)` nhận hai tham số từ caller nên đóng những gì theo mặc định?

**Đáp án:** Thông thường **không đóng cả hai**, vì đó là tài nguyên mượn. Caller chịu trách nhiệm dọn dẹp, trừ khi hợp đồng API quy định chuyển ownership.

**Câu 3.** Nếu một hàm tự dùng `Files.newBufferedReader` và `Files.newBufferedWriter`, cách xử lý thích hợp là gì?

**Đáp án:** Dùng `try-with-resources` quản lý cả hai, chuyển dữ liệu trong khối và đóng khi thoát.

**Câu 4.** Trong `try (Reader a = ...; Writer b = ...)`, tài nguyên nào được đóng trước?

**Đáp án:** `b` (writer) đóng trước `a` (reader), vì đóng ngược thứ tự khai báo.

**Câu 5.** Tại sao `reader.read() == -1` sau khi transfer không chứng minh reader đã được đóng?

**Đáp án:** `-1` biểu thị đã đến EOF. `transferTo` không gọi `close`, nên đây là hai trạng thái khác nhau.

**Câu 6.** `transferTo` trả `long` đếm byte hay ký tự?

**Đáp án:** **Ký tự** được Reader cung cấp; không phải số byte đầu ra sau mã hóa. Với ký tự bổ sung Unicode, số đơn vị UTF-16 cũng có thể khác số code point.

**Câu 7.** Nếu writer là `BufferedWriter` do caller sở hữu và caller muốn dùng tiếp, helper có nên tự đóng nó không?

**Đáp án:** Không, trừ khi caller trao quyền đóng rõ ràng. Khi cần dữ liệu đệm được đẩy đi, caller quyết định `flush()` hoặc đóng lúc hoàn tất.

**Câu 8.** Một wrapper `OutputStreamWriter` bọc `System.out` có nên đưa vào `try-with-resources` trong helper thông thường không?

**Đáp án:** Thường không, vì `close()` wrapper có thể đóng `System.out` được các thành phần khác dùng chung.

**Câu 9.** Nếu `transferTo` lỗi giữa chừng, tệp đích có chắc không thay đổi không?

**Đáp án:** Không. Có thể đã ghi một phần. Cần xử lý tài nguyên và chiến lược dữ liệu dở; muốn all-or-nothing thì phải thiết kế cơ chế bổ sung.

**Câu 10.** Nếu lỗi xảy ra trong body và khi đóng hai resource, lỗi close ở đâu?

**Đáp án:** Lỗi body là primary exception; lỗi close được gắn trong `getSuppressed()` theo cơ chế của `try-with-resources`.

## 14. Ghi nhớ cuối bài

1. **`Reader.transferTo(Writer)` (Java 10+) chỉ chuyển ký tự, không đóng Reader hay Writer.**
2. Quyền sở hữu tài nguyên là **hợp đồng thiết kế**, không được Java tự động suy ra từ một lời gọi copy.
3. **Ai mở thì thường người đó đóng**; helper nhận tài nguyên của caller thường **không đóng**.
4. Với tài nguyên do mình sở hữu, dùng **`try-with-resources`** để bảo đảm đóng cả khi thành công, lỗi hoặc `return`.
5. `try-with-resources` đóng tài nguyên **theo thứ tự ngược** và giữ thông tin lỗi đóng dưới dạng **suppressed exceptions** khi cần.
6. EOF không đồng nghĩa đã đóng; `transferTo` không bảo đảm flush cho mọi writer.
7. Chú ý wrapper và standard streams: đóng một wrapper có thể đóng luôn stream nền.
8. Nếu copy có lỗi, dữ liệu đầu ra có thể đã được ghi một phần. `transferTo` không tự rollback.

**Tài liệu tham khảo chính thức, còn áp dụng:**
- [Oracle Java SE 17 — `Reader.transferTo(Writer)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer)).
- [Oracle Java SE 17 — `Writer.flush()` và `close()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Writer.html).
- [Java Language Specification 17, §14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3).
- [Oracle Java SE 17 — `Files.newBufferedReader` / `newBufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).

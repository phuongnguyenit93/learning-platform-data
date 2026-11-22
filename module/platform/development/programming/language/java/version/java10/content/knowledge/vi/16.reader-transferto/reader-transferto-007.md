# Yêu cầu `flush()` theo hợp đồng của đích ghi khi dùng `Reader.transferTo(Writer)`

**Chủ đề:** `Reader.transferTo` — Java 10 trở lên.

`Reader.transferTo(Writer out)` đọc phần ký tự còn lại của nguồn và ghi chúng theo thứ tự vào một `Writer` được cung cấp. Một điểm quan trọng trong thiết kế luồng I/O là **gọi `transferTo` thành công không đồng nghĩa dữ liệu đã được `flush` tới đích ghi cuối cùng**. Quyết định có gọi `flush()`, khi nào gọi và có đóng writer hay không phải dựa trên **hợp đồng của Writer đích** và **quyền sở hữu tài nguyên**.

`Reader.transferTo` được bổ sung trong Java 10 và vẫn là API hiện hành. Những ví dụ trong bài sử dụng Java 10 source level; không dùng phương pháp hoặc API đã lỗi thời. Nội dung cũng phân biệt rõ việc flush bộ đệm với việc bảo đảm ghi bền vững xuống đĩa hoặc được phía nhận mạng xác nhận.

## 1. Hiểu đúng `transferTo` trước khi nghĩ đến `flush`

Chữ ký:

~~~java
public long transferTo(Writer out) throws IOException
~~~

Ý nghĩa theo Javadoc của `java.io.Reader`:

1. Đọc các ký tự còn lại từ vị trí hiện tại của `Reader`, ghi theo thứ tự vào `out` cho đến khi hết nguồn.
2. Trả về số lượng **đơn vị `char`** đã truyền, kiểu `long`. Đây không phải số byte đã mã hóa thành UTF-8 hoặc kích thước file.
3. Khi thành công, reader ở cuối luồng (*EOF*).
4. **Không tự đóng** Reader hoặc Writer.
5. Có thể bị chặn khi đọc/ghi. Nếu I/O lỗi, việc sao chép có thể đã hoàn thành một phần; không được giả định reader hoặc writer còn ở trạng thái nhất quán.
6. Nếu tham số `out` là `null`, ném `NullPointerException`.

**Về `flush`:** hợp đồng `Reader.transferTo` **không hứa tự gọi `out.flush()`** hoặc bảo đảm mọi bộ đệm của writer đích đã được đẩy ra. Chương trình cần quyết định bước flush dựa trên writer và mục đích sử dụng. Một writer tự cài đặt có thể chuyển dữ liệu ngay trong `write`, trong khi một writer có buffer có thể giữ lại ký tự trước khi gửi đi.

Cú pháp thông dụng:

~~~java
long copied = reader.transferTo(writer);
writer.flush(); // chỉ khi yêu cầu đầu ra cần được đẩy đi ngay
~~~

Đây là **đoạn mã minh họa nằm trong phương thức**; `reader`/`writer` đã được khởi tạo và đang mở. Gọi `flush()` trong tình huống cần thiết là **trách nhiệm của nơi điều phối Writer**, không phải tác dụng phụ nên mặc định trông chờ từ `transferTo`.

## 2. Ba lớp trách nhiệm: chuyển ký tự, flush và close

| Thao tác | Ai chịu trách nhiệm? | Cam kết chính | Không được suy diễn |
| --- | --- | --- | --- |
| `reader.transferTo(writer)` | Reader điều phối việc đọc và ghi vào `Writer` | Chuyển các `char` theo thứ tự đến các lời gọi ghi của writer; trả số ký tự | Không hứa writer đã flush/close hoặc dữ liệu bền vững |
| `writer.flush()` | Caller hoặc lớp sở hữu writer theo hợp đồng đầu ra | Đẩy dữ liệu nằm trong bộ đệm của writer và chuỗi writer/output stream bên dưới | Không cam kết bytes đã nằm trên thiết bị lưu trữ vật lý hoặc phía nhận đã xử lý |
| `writer.close()` | **Bên sở hữu writer**, thường thông qua `try-with-resources` | Đóng writer, thông thường flush trước theo hợp đồng `Writer.close()` | Không nên đóng writer do một thành phần khác còn sở hữu và cần dùng tiếp |

Java `Writer.flush()` có hợp đồng đưa dữ liệu còn lưu trong các buffer của chuỗi writer/output stream tới đích kế tiếp. Với đích file do hệ điều hành quản lý, Javadoc nói rõ flush **không đảm bảo bytes đã thực sự được ghi tới thiết bị đĩa vật lý**. Nếu ứng dụng cần độ bền dữ liệu sau mất điện, phải thiết kế biện pháp đồng bộ/commit phù hợp với loại đích ghi; chỉ `flush` là chưa đủ.

Một kết luận thực tế:

- **Chuyển dữ liệu xong và sắp đóng writer do mình sở hữu:** `try-with-resources` bảo đảm gọi `close`, và `close` flush theo hợp đồng. Không cần tự động gọi thêm `flush` ngay trước `close` chỉ để tránh mất buffer; có thể gọi nếu ứng dụng có checkpoint cụ thể trước đó.
- **Writer dùng chung hoặc cần tiếp tục mở:** không tự ý `close`. Nếu đích cần nhìn thấy dữ liệu ngay sau lần sao chép, gọi `flush` ở ranh giới giao thức mà bên sở hữu đã quy định.
- **Writer chỉ dùng trong bộ nhớ:** `StringWriter` ghi nội dung vào `StringBuffer` trong bộ nhớ; `flush` của nó không có ý nghĩa buộc gửi dữ liệu xuống hệ thống file hoặc mạng. Không phải loại writer nào cũng cần flush sau mọi lần ghi.

Không nên viết quy tắc “luôn flush sau mọi `transferTo`” hoặc “không bao giờ flush vì transferTo đã hoàn tất”. Cả hai đều bỏ qua **hợp đồng của đích ghi**.

## 3. Vì sao writer có bộ đệm cần được quan tâm?

`BufferedWriter` thu thập ký tự trong một buffer để hạn chế số lần ghi vào writer bên dưới. Với dữ liệu nhỏ hơn buffer và chưa gặp tình huống đẩy buffer khác, nội dung mới ghi có thể **chưa xuất hiện tại writer bên dưới**.

Sơ đồ dòng dữ liệu:

~~~text
Reader
  |
  | transferTo(writer) -> các lần writer.write(...)
  v
BufferedWriter [bộ đệm ký tự]
  |
  | flush() hoặc close() của bên sở hữu
  v
OutputStreamWriter [mã hóa ký tự thành bytes, có thể có buffer]
  |
  | flush() đẩy tiếp qua chuỗi
  v
OutputStream / file / socket / đích khác
~~~

Đây là sơ đồ khái niệm, không phải khẳng định mỗi loại writer luôn dùng đúng số bộ đệm hoặc mỗi `write` đều dừng ở bộ đệm. Khi buffer đầy, hoặc `BufferedWriter` quyết định ghi một đoạn lớn trực tiếp, dữ liệu có thể được đưa xuống lớp dưới **trước khi gọi `flush()`**. Vì vậy **không dùng việc “đã thấy một ít bytes” để kết luận tất cả dữ liệu đã được đẩy đi**.

Với wrapper như `BufferedWriter`, hãy flush chính writer **ngoài cùng** đang sở hữu chuỗi và để lời gọi truyền xuống các writer bên dưới. Sau khi đã bọc writer gốc, tránh ghi trực tiếp qua writer gốc song song nếu không có giao thức đồng bộ rõ ràng.

## 4. Ví dụ độc lập 1 — Kiểm chứng `transferTo` không tự gọi `flush/close`

Lưu chương trình sau vào **`TransferFlushDemo.java`**:

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.Writer;

public class TransferFlushDemo {
    static final class TrackingWriter extends Writer {
        final StringBuilder text = new StringBuilder();
        int flushCount;
        int closeCount;
        boolean closed;

        @Override
        public void write(char[] chars, int off, int len) throws IOException {
            if (closed) {
                throw new IOException("closed");
            }
            text.append(chars, off, len);
        }

        @Override
        public void flush() {
            flushCount++;
        }

        @Override
        public void close() {
            closeCount++;
            closed = true;
        }
    }

    public static void main(String[] args) throws IOException {
        TrackingWriter target = new TrackingWriter();

        try (Reader reader = new StringReader("hello")) {
            long count = reader.transferTo(target);
            System.out.println("written=" + count);
            System.out.println("data=" + target.text);
            System.out.println("flushes=" + target.flushCount);
            System.out.println("closes=" + target.closeCount);
            System.out.println("reader-at-eof=" + reader.read());
        }

        target.write("!");
        System.out.println("after-write=" + target.text);

        target.flush();
        System.out.println("after-flush=" + target.flushCount);

        target.close();
        System.out.println("after-close=" + target.closeCount);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 TransferFlushDemo.java
java TransferFlushDemo
~~~

**Stdout chính xác:**

~~~text
written=5
data=hello
flushes=0
closes=0
reader-at-eof=-1
after-write=hello!
after-flush=1
after-close=1
~~~

Giải thích:

1. `count=5` vì nguồn có 5 `char`.
2. `flushes=0` xác nhận trường hợp **`StringReader.transferTo(TrackingWriter)` trong chương trình** không tự gọi `flush`.
3. `closes=0` cho thấy writer vẫn mở; có thể `write("!")` tiếp.
4. `reader.read()` trả `-1` vì đã ở EOF, không phải vì reader đã tự bị đóng. `try-with-resources` đóng reader sau khi thoát block.
5. `after-flush=1` và `after-close=1` xảy ra vì **chính chương trình** gọi hai thao tác ấy.

Đây là **kiểm thử minh họa hành vi**, không phải khuyến nghị luôn cần đếm `flush` trong ứng dụng. Quy tắc thiết kế cần dùng là **không dựa vào `transferTo` như một cam kết flush theo hợp đồng Reader**.

## 5. Ví dụ độc lập 2 — `BufferedWriter` giữ dữ liệu tới khi flush/close

Một thử nghiệm có thể quan sát rõ sự khác biệt giữa “đã chuyển tới `BufferedWriter`” và “đã chuyển tới writer bên dưới”. Lưu **`BufferedDestinationDemo.java`**:

~~~java
import java.io.BufferedWriter;
import java.io.StringReader;
import java.io.StringWriter;

public class BufferedDestinationDemo {
    public static void main(String[] args) throws Exception {
        StringWriter underlying = new StringWriter();
        BufferedWriter buffered = new BufferedWriter(underlying, 128);

        long copied = new StringReader("alpha\nbeta").transferTo(buffered);
        System.out.println("copied=" + copied);
        System.out.println("before-flush=" + underlying.toString().length());

        buffered.flush();
        System.out.println(
                "after-flush=" + underlying.toString().replace("\n", "|"));

        buffered.write("!");
        buffered.close();
        System.out.println(
                "after-close=" + underlying.toString().replace("\n", "|"));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 BufferedDestinationDemo.java
java BufferedDestinationDemo
~~~

Stdout:

~~~text
copied=10
before-flush=0
after-flush=alpha|beta
after-close=alpha|beta!
~~~

Phần giải thích chính:

- Chuỗi `"alpha\nbeta"` có **10 đơn vị `char`**, do đó `transferTo` trả 10.
- Trong thử nghiệm này buffer có dung lượng 128 ký tự, dữ liệu ngắn và chưa đầy buffer, nên ngay sau `transferTo`, `underlying` chưa có ký tự nào.
- `buffered.flush()` đẩy phần còn giữ trong `BufferedWriter` tới `StringWriter`; khi đó `underlying` chứa đúng chuỗi với ký tự xuống dòng.
- Phần `"!"` được ghi thêm sau đó, rồi `buffered.close()` flush phần còn lại trước khi đóng. Kết quả sau close có thêm `!`.

**Không tổng quát hóa `before-flush=0` thành quy tắc cho mọi buffer và mọi kích thước dữ liệu.** Đây là kết quả cố định của ví dụ có payload ngắn và buffer lớn. Nếu payload lớn, writer có thể tự đẩy các khối trước khi `flush` được gọi; việc **chưa flush vẫn không cam kết tất cả đã tới đích**.

## 6. Nếu đích là file: quyền sở hữu quyết định `flush` hay `close`

Với một tác vụ sao chép file văn bản hoàn chỉnh, thành phần thực hiện thường **sở hữu cả Reader và Writer**. Cách rõ ràng là dùng `try-with-resources`:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class TextFileCopy {
    public static long copy(Path input, Path output) throws IOException {
        try (BufferedReader source =
                     Files.newBufferedReader(input, StandardCharsets.UTF_8);
             BufferedWriter target =
                     Files.newBufferedWriter(
                             output,
                             StandardCharsets.UTF_8,
                             StandardOpenOption.CREATE,
                             StandardOpenOption.TRUNCATE_EXISTING)) {
            return source.transferTo(target);
        }
    }
}
~~~

Đây là **lớp minh họa có phương thức đầy đủ nhưng không có `main`**; cần gọi `copy` với các `Path` hợp lệ trong ứng dụng. Các API đều có trong Java 10.

`return source.transferTo(target)` tính số ký tự, sau đó **try-with-resources vẫn đóng `target`** khi rời block. Đóng `Writer` theo hợp đồng sẽ flush bộ đệm trước khi giải phóng tài nguyên. Vì vậy không cần thêm `target.flush()` chỉ để hoàn thành bản sao **nếu đã đóng thành công ở cuối thao tác**.

Một số lưu ý:

- Chọn charset rõ ràng, ví dụ `StandardCharsets.UTF_8`; `transferTo` chuyển **ký tự**, còn reader/writer làm việc đọc/ghi bytes và mã hóa.
- `StandardOpenOption.TRUNCATE_EXISTING` xóa nội dung cũ của file đích nếu file đã tồn tại và được mở theo tùy chọn ghi phù hợp; không dùng tùy chọn này nếu mục tiêu là nối nội dung.
- Không mở cùng một file làm cả đầu vào và đầu ra với chế độ truncate rồi kỳ vọng sao chép an toàn: file nguồn có thể bị rỗng khi tạo writer. Trường hợp hai `Path` trỏ tới cùng file phải được kiểm soát riêng.
- `close` hoặc `flush` thành công **không đồng nghĩa** dữ liệu được bảo đảm sống sót sau mất điện; nhu cầu bền vững cần cơ chế filesystem/transaction phù hợp.
- Nếu I/O lỗi giữa chừng, đầu ra có thể chỉ chứa **một phần văn bản**. Một quy trình đòi hỏi tính nguyên tử có thể cần ghi tệp tạm, kiểm tra thành công và chuyển/replace tệp theo khả năng của filesystem.

### Writer do caller sở hữu: không được tự ý đóng

Nếu hàm chỉ mượn Writer do caller cung cấp, tách trách nhiệm:

~~~java
static long copyToSharedWriter(Reader source, Writer destination)
        throws IOException {
    return source.transferTo(destination);
}
~~~

Đây là **phương thức minh họa**, cần import `Reader`, `Writer`, `IOException`. Hàm **không** close và cũng **không tự động flush** vì nó không sở hữu giao thức output.

Caller quyết định:

~~~java
long copied = copyToSharedWriter(source, sharedWriter);
sharedWriter.flush(); // khi hợp đồng của caller yêu cầu công bố ngay dữ liệu
// Không close sharedWriter ở đây nếu phần khác còn cần nó.
~~~

Phần này là đoạn minh họa trong phương thức và giả sử hai biến đang mở. Nếu đích là Writer dùng chung với nhiều nguồn ghi, caller cần cả **đồng bộ hóa** và quy ước ranh giới bản ghi phù hợp, không chỉ gọi `flush`.

## 7. `OutputStreamWriter`: flush ký tự qua lớp mã hóa bytes

`OutputStreamWriter` kết nối hai thế giới: dữ liệu ký tự của `Reader`/`Writer` và bytes của một `OutputStream`. Nó mã hóa theo charset như UTF-8; số `char` của `transferTo` không nhất thiết bằng số bytes cuối cùng.

### Ví dụ độc lập 3 — UTF-8 và flush qua chuỗi writer

Lưu **`CharsetFlushDemo.java`**:

~~~java
import java.io.BufferedWriter;
import java.io.ByteArrayOutputStream;
import java.io.OutputStreamWriter;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;

public class CharsetFlushDemo {
    public static void main(String[] args) throws Exception {
        String payload = "A\uD83D\uDE80B\n";

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        BufferedWriter target = new BufferedWriter(
                new OutputStreamWriter(bytes, StandardCharsets.UTF_8), 128);

        long chars = new StringReader(payload).transferTo(target);
        System.out.println("char-units=" + chars);
        System.out.println("before-flush-bytes=" + bytes.size());

        target.flush();
        System.out.println("after-flush-bytes=" + bytes.size());

        String decoded = new String(
                bytes.toByteArray(), StandardCharsets.UTF_8);
        System.out.println("decoded-equal=" + payload.equals(decoded));

        target.close();
    }
}
~~~

Chạy:

~~~bash
javac --release 10 CharsetFlushDemo.java
java CharsetFlushDemo
~~~

**Stdout chính xác:**

~~~text
char-units=5
before-flush-bytes=0
after-flush-bytes=7
decoded-equal=true
~~~

Trong literal `payload`, giữa `A` và `B` có một ký tự Unicode được biểu diễn bằng **cặp surrogate UTF-16**. Chuỗi có 5 `char`: `A` (1), cặp surrogate (2), `B` (1), xuống dòng (1). Khi mã hóa UTF-8 thành bytes, hai đơn vị surrogate tạo một code point dùng 4 bytes, nên toàn bộ payload có 7 bytes.

`before-flush-bytes=0` chỉ là kết quả của việc buffer chưa cần đẩy dữ liệu trong ví dụ này. Sau `target.flush()`, cả `BufferedWriter` và `OutputStreamWriter` trong chuỗi được yêu cầu đẩy phần dữ liệu chưa gửi xuống `ByteArrayOutputStream`. So sánh chuỗi giải mã xác nhận dữ liệu chính xác.

**Hai quy tắc độc lập:** `transferTo` trả số ký tự truyền, còn `flush` kiểm soát thời điểm đẩy dữ liệu qua chuỗi writer. Không dùng giá trị `long` trả về làm bằng chứng file hoặc socket đã ghi đủ bytes ở đích cuối.

## 8. `PrintWriter(autoFlush=true)` không phải bảo hiểm cho `transferTo`

`PrintWriter` có tùy chọn `autoFlush`, nhưng cần hiểu hợp đồng cụ thể của nó. Với `PrintWriter` bật auto-flush, các lời gọi **`println`, `printf` hoặc `format`** là những thao tác kích hoạt flush tự động theo quy tắc của lớp. Chỉ gọi `write(...)`, kể cả khi chuỗi chứa ký tự xuống dòng, **không đồng nghĩa tự flush**.

Vì `Reader.transferTo(Writer)` dùng thao tác ghi ký tự qua writer, **đừng mặc định `autoFlush=true` sẽ flush ngay sau transfer**.

### Ví dụ độc lập 4 — `PrintWriter` và auto-flush

Lưu **`PrintWriterFlushDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;

public class PrintWriterFlushDemo {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        PrintWriter target = new PrintWriter(
                new OutputStreamWriter(bytes, StandardCharsets.UTF_8), true);

        long chars = new StringReader("note").transferTo(target);
        System.out.println("chars=" + chars);
        System.out.println("bytes-before=" + bytes.size());

        target.flush();
        System.out.println("bytes-after=" + bytes.size());

        System.out.println("result=" +
                new String(bytes.toByteArray(), StandardCharsets.UTF_8));
        System.out.println("writer-error=" + target.checkError());
        target.close();
    }
}
~~~

Chạy:

~~~bash
javac --release 10 PrintWriterFlushDemo.java
java PrintWriterFlushDemo
~~~

Stdout:

~~~text
chars=4
bytes-before=0
bytes-after=4
result=note
writer-error=false
~~~

Trong ví dụ này `autoFlush=true` không làm dữ liệu xuất hiện ngay tại `ByteArrayOutputStream` sau `transferTo`. Chỉ sau `target.flush()` mới có 4 bytes. Ngoài ra **`PrintWriter.checkError()` có thể flush khi kiểm tra trạng thái lỗi**; không dùng nó để quan sát một “before-flush” mà vẫn mong bộ đệm không bị thay đổi.

**Một khác biệt quan trọng về báo lỗi:** nhiều phương thức của `PrintWriter` không ném `IOException` ra caller mà ghi nhận trạng thái lỗi bên trong; kiểm tra qua `checkError()` khi cần. Vì vậy với tác vụ copy đòi hỏi báo lỗi I/O chính xác và dừng ngay khi ghi thất bại, `BufferedWriter`/`OutputStreamWriter` thường dễ phối hợp với `throws IOException` hơn là dựa vào `PrintWriter`.

## 9. Khi nào thật sự cần gọi `flush` sau `transferTo`?

| Loại đích | Có nên `flush` ngay sau lần chuyển? | Hợp đồng/ghi chú |
| --- | --- | --- |
| `StringWriter` chỉ dùng trong bộ nhớ | Thường **không cần** | Nội dung sẵn có trong bộ đệm nội bộ của `StringWriter`, không có file/socket chờ flush |
| `BufferedWriter` phải cho lớp dưới đọc ngay sau copy, nhưng chưa đóng | **Có**, ở ranh giới cần quan sát | Flush writer ngoài cùng để đẩy dữ liệu còn nằm trong buffer |
| Writer ghi file và **sắp được đóng** bằng `try-with-resources` | Không bắt buộc flush riêng chỉ để hoàn tất | `close` flush trước; xử lý ngoại lệ close đúng cách |
| Writer ghi file vẫn phải mở cho nhiều phần ghi | **Theo chính sách output** | Flush tại checkpoint/ranh giới dữ liệu cần được nhìn thấy, không buộc flush từng đoạn nhỏ |
| `OutputStreamWriter` sang output stream | Khi cần đẩy bytes đã mã hóa tới stream bên dưới | Charset và bộ đệm mã hóa ảnh hưởng thời điểm xuất bytes |
| Socket/text protocol đòi gửi một thông điệp để phía nhận bắt đầu xử lý | Thường cần flush sau khi đã ghi **đầy đủ và đúng framing** | Flush không thay thế ký tự kết thúc, length prefix, quy tắc parse hoặc acknowledgment |
| Log hoặc telemetry dùng writer có buffering | Theo SLA độ trễ và chính sách batching | Flush mỗi record có thể tăng overhead; flush theo batch nếu hợp đồng cho phép |
| `PrintWriter(autoFlush=true)` nhận dữ liệu từ `transferTo` | **Không thể chỉ tin autoFlush** | Auto-flush của `PrintWriter` gắn với `println/printf/format`, không phải mọi `write` |
| Output cần bảo đảm tồn tại sau mất điện | `flush` **chưa đủ** | Cần cơ chế durability/commit tương ứng với loại đích ghi |

Lựa chọn đúng cần xét cả **tính kịp thời** lẫn **hiệu năng**. Flush sau mọi mẩu dữ liệu nhỏ có thể làm giảm lợi ích của buffering. Ngược lại, không flush trong một giao thức tương tác có thể khiến bên nhận chờ mãi dù bên gửi đã hoàn tất `transferTo`.

### Tình huống tương tác mạng

Giả sử một protocol text quy định mỗi message kết thúc bằng newline. Khi Reader chứa phần nội dung **chưa có newline**, `transferTo` không tự thêm dấu kết thúc. Nếu chỉ gọi `flush` mà không viết newline, phía nhận vẫn có thể chưa xem message là hoàn chỉnh.

Một phương thức minh họa nằm trong ứng dụng:

~~~java
static void sendLine(Reader message, Writer networkWriter)
        throws IOException {
    message.transferTo(networkWriter);
    networkWriter.write('\n'); // ranh giới dòng theo giao thức giả định
    networkWriter.flush();     // đẩy phần buffered output
}
~~~

Mẫu này **chỉ phù hợp** khi protocol thực sự dùng newline làm dấu phân cách, nội dung message không cần escaping, và caller sở hữu trách nhiệm flush. Nếu protocol dùng length prefix hoặc quy tắc framing khác, phải tuân theo protocol ấy thay vì tự thêm newline. **`flush` không xác nhận remote đã nhận/xử lý**; nếu cần cam kết giao hàng, thiết kế ACK/transaction riêng.

### Trường hợp chỉ cần tạo một chuỗi

~~~java
StringWriter memory = new StringWriter();
source.transferTo(memory);
String result = memory.toString();
~~~

Đây là đoạn minh họa trong method với `source` là Reader đang mở. Không cần flush cho mục đích đọc chuỗi đã nằm trong `StringWriter`. Điều này cho thấy quy tắc flush phụ thuộc hoàn toàn **đích ghi**, không phụ thuộc vào sự hiện diện của `transferTo`.

## 10. I/O lỗi giữa chừng: flush không phải cơ chế phục hồi

`Reader.transferTo` có thể ném `IOException` khi đọc nguồn hoặc ghi đích. Lỗi có thể xảy ra **sau khi một phần ký tự đã được đọc và ghi**. Khi đó:

- Giá trị `long` kết quả không được trả bình thường, vì phương thức kết thúc bằng exception.
- Không được suy ra reader còn ở đúng vị trí trước lần sao chép, hoặc writer không có dữ liệu nào.
- Javadoc khuyến nghị đóng cả hai stream sớm sau I/O failure. Nếu đang dùng `try-with-resources`, việc đóng được đảm bảo khi rời block.
- Đừng coi `flush` là cách “sửa” bản ghi bị thiếu. Flush chỉ cố đẩy buffer còn lại, không khôi phục phần đã bị mất hoặc bảo đảm thứ tự nghiệp vụ.
- Với tác vụ cần nguyên tử, xây dựng cơ chế ghi tạm/commit/rollback theo loại hệ thống đích.

### Ví dụ độc lập 5 — Writer lỗi sau khi nhận một phần dữ liệu

Lưu **`PartialFailureDemo.java`**:

~~~java
import java.io.IOException;
import java.io.StringReader;
import java.io.Writer;

public class PartialFailureDemo {
    static final class FailingWriter extends Writer {
        final StringBuilder accepted = new StringBuilder();
        boolean closed;

        @Override
        public void write(char[] data, int offset, int length)
                throws IOException {
            accepted.append(data, offset, Math.min(length, 3));
            throw new IOException("sink-failed");
        }

        @Override
        public void flush() throws IOException {
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    public static void main(String[] args) throws Exception {
        FailingWriter target = new FailingWriter();

        try (StringReader source = new StringReader("abcdef");
             FailingWriter owned = target) {
            try {
                source.transferTo(owned);
            } catch (IOException expected) {
                System.out.println("error=" + expected.getMessage());
                System.out.println("partial=" + owned.accepted);
            }
        }

        System.out.println("closed-by-owner=" + target.closed);
    }
}
~~~

Chạy:

~~~bash
javac --release 10 PartialFailureDemo.java
java PartialFailureDemo
~~~

Stdout:

~~~text
error=sink-failed
partial=abc
closed-by-owner=true
~~~

`FailingWriter` cố tình nhận ba ký tự rồi ném `IOException`. Đây là writer giả lập dành cho kiểm thử; nó không phải mẫu writer lưu file thực tế. Ví dụ cho thấy `transferTo` có thể thất bại **sau một phần ghi**. `try-with-resources` vẫn đóng writer vì ứng dụng sở hữu nó. Không dựa vào số ký tự đã đọc thực tế từ source sau lỗi: chi tiết này phụ thuộc Reader và cách buffering.

## 11. Những lỗi thường gặp khi áp dụng

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `transferTo` đã flush writer vì trả về `long` | Đích ghi có buffer có thể chưa thấy toàn bộ dữ liệu | Xác định hợp đồng đích, gọi `flush` khi cần nhìn thấy kết quả trước close |
| Luôn `flush` sau từng `write` rất nhỏ | Giảm lợi ích của buffer, tăng số lần I/O | Flush ở ranh giới transaction/message/checkpoint phù hợp |
| Dùng `close` thay `flush` trên writer dùng chung | Phần khác không thể tiếp tục ghi | Không đóng tài nguyên mình không sở hữu |
| Sở hữu writer nhưng quên close | Có thể còn buffer chưa gửi và rò tài nguyên | `try-with-resources` |
| Tưởng `BufferedWriter` luôn giữ dữ liệu cho đến flush | Khi buffer đầy, dữ liệu có thể được đẩy xuống trước đó | Không dựa vào trạng thái buffer bên dưới làm hợp đồng |
| Dùng `StringWriter` rồi lo bắt buộc flush mới đọc được string | Gây nhầm ý nghĩa của flush | Đọc `toString()` trực tiếp |
| Dùng `PrintWriter(autoFlush=true)` và nghĩ `transferTo` sẽ tự flush | `write` không kích hoạt autoFlush theo quy tắc `PrintWriter` | Gọi `flush` rõ ràng, cân nhắc `checkError` và hợp đồng báo lỗi |
| Tưởng `flush` đảm bảo file được fsync xuống đĩa | Có thể chỉ đẩy dữ liệu sang hệ điều hành | Dùng cơ chế durability riêng nếu cần |
| Tưởng `flush` đảm bảo remote đã nhận message | Không xác nhận application bên kia đã đọc/xử lý | Thiết kế framing và ACK nếu protocol yêu cầu |
| Dùng số `transferTo` trả về như số bytes | Sai với encoding đa byte/Unicode surrogate | Phân biệt `char` (UTF-16 code unit) và byte sau encoding |
| Bắt `IOException` rồi tiếp tục dùng cùng writer mà không đánh giá state | Có thể để lại output một phần và dữ liệu sai | Đóng, báo lỗi, cân nhắc ghi lại từ nguồn có thể reset |
| Đóng Writer gốc trước khi đóng wrapper ngoài cùng | Dễ làm sai thứ tự flush/close | Quản lý chuỗi tài nguyên một cách nhất quán; thường sở hữu wrapper ngoài cùng |

## 12. Checklist review khi có `reader.transferTo(writer)`

1. **Reader và Writer thuộc về ai?** Thành phần nào có quyền `close`? Không đóng shared writer một cách tùy tiện.
2. **Writer đích có buffering không?** Có `BufferedWriter`, `OutputStreamWriter` hoặc `PrintWriter` trong chuỗi không?
3. **Tại thời điểm nào caller cần quan sát output?** Ngay sau `transferTo`, sau cả batch, khi close, hay sau một ACK?
4. **Có phải một protocol message không?** Đã ghi đủ newline/length prefix/terminator chưa? `flush` không tự tạo framing.
5. **Đích là file, socket hay memory?** `StringWriter` khác `BufferedWriter`, file khác một kết nối cần phản hồi.
6. **Có cần bảo đảm durability không?** Nếu cần, `flush` đơn thuần không giải quyết được; dùng cơ chế của hệ thống lưu trữ.
7. **Có quan tâm throughput không?** Flush quá thường xuyên có thể không phù hợp với batching.
8. **Encoding đã chỉ định đúng chưa?** Với byte stream, chủ động chọn charset phù hợp; `transferTo` chỉ làm việc với `char`.
9. **Nếu I/O thất bại giữa chừng thì sao?** Đã có đường xử lý partial output và đóng tài nguyên?
10. **Test dựa trên hợp đồng hay hiện tượng tình cờ?** Không giả định `BufferedWriter` luôn rỗng/đầy theo kích thước cố định hay chỉ vì dữ liệu đã có ở output stream là flush không cần thiết.

Một unit test đáng tin nên kiểm tra **điểm quan sát phù hợp với đích**: với writer buffer, xem trạng thái trước/sau `flush` trong tình huống kiểm soát; với protocol, test một message hoàn chỉnh và phản hồi; với file cần độ bền, test cơ chế commit chứ không chỉ `flush`.

## 13. Câu hỏi tự kiểm tra

1. Sau `long n = reader.transferTo(writer);`, có thể khẳng định writer đã được flush chưa?
2. `transferTo` có tự đóng source hoặc destination không?
3. Trong ví dụ `BufferedDestinationDemo`, vì sao `underlying` rỗng trước khi flush, dù `copied=10`?
4. Với `StringWriter`, có bắt buộc `flush` trước `toString()` để thấy dữ liệu vừa ghi không?
5. Nếu writer thuộc quyền caller và vẫn cần ghi tiếp, nên dùng `close` hay `flush` khi muốn đẩy buffer đi?
6. Vì sao writer file được đóng bằng `try-with-resources` thường không cần `flush` riêng ngay trước close?
7. `transferTo` trả số bytes hay số đơn vị `char`? Ví dụ một ký tự ngoài BMP có thể ảnh hưởng con số thế nào?
8. `PrintWriter(autoFlush=true)` có tự flush sau mọi `write` từ `transferTo` không?
9. Vì sao gọi `flush` không thay thế ký tự kết thúc message của một protocol text?
10. Nếu Writer ném `IOException` sau khi ghi một phần, có được coi output còn nguyên vẹn và tiếp tục dùng Reader ở vị trí cũ không?

**Đáp án:**

1. Không. Hợp đồng `Reader.transferTo` không bảo đảm writer đã flush; xét yêu cầu đích và gọi `flush` đúng nơi.
2. Không đóng cả hai.
3. Payload nhỏ hơn buffer 128 ký tự trong thử nghiệm; dữ liệu còn giữ trong buffer `BufferedWriter` cho tới khi flush.
4. Không; `StringWriter` có sẵn nội dung trong bộ nhớ.
5. Flush theo hợp đồng giao thức; không close tài nguyên của người khác.
6. `Writer.close()` flush trước khi đóng; tài nguyên được sở hữu và đóng thành công là điểm kết thúc hợp lệ.
7. Số `char` (đơn vị UTF-16), không phải số bytes; ký tự ngoài BMP có thể chiếm hai `char`.
8. Không; auto-flush của `PrintWriter` được quy định cho `println`, `printf` và `format`, không phải mọi `write`.
9. Flush đẩy buffer, không định nghĩa ranh giới hoặc cú pháp message; bên nhận vẫn cần dữ liệu theo protocol.
10. Không; lỗi có thể xảy ra sau khi ghi một phần, trạng thái hai luồng có thể không nhất quán. Nên đóng và xử lý lỗi/khôi phục riêng.

## 14. Tham khảo tài liệu Java chính thức đang áp dụng

- **Oracle Javadoc — `Reader.transferTo(Writer)` (Java 10):** https://docs.oracle.com/javase/10/docs/api/java/io/Reader.html#transferTo(java.io.Writer)
- **Oracle Javadoc — `Reader` (Java SE 25), hợp đồng chuyển, EOF và close:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Reader.html
- **Oracle Javadoc — `Writer.flush()` và `Writer.close()`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Writer.html
- **Oracle Javadoc — `BufferedWriter`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedWriter.html
- **Oracle Javadoc — `OutputStreamWriter`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStreamWriter.html
- **Oracle Javadoc — `PrintWriter` và quy tắc auto-flush:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PrintWriter.html
- **Oracle Javadoc — `Files.newBufferedWriter`:** https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html

**Ghi nhớ:** `Reader.transferTo(Writer)` chỉ chịu trách nhiệm **chuyển ký tự vào Writer** và trả số ký tự đã chuyển; nó **không hứa Writer đã `flush` hoặc được đóng**. Nếu Writer cần công bố dữ liệu ngay, bên sở hữu điều phối gọi `flush` theo **hợp đồng đầu ra**. Nếu đã sở hữu writer và đóng nó đúng bằng `try-with-resources`, `close` sẽ flush trước. `flush` không phải `fsync` và cũng không phải thông báo bên nhận đã xử lý thành công.
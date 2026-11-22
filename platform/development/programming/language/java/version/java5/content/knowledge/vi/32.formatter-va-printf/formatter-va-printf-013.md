# Quản lý đích ghi, tài nguyên và lỗi I/O của Formatter

## 1. Định dạng xong chưa có nghĩa dữ liệu đã được ghi thành công

Một lời gọi định dạng có hai trách nhiệm liên quan nhưng khác nhau:

1. Chuyển đối số thành văn bản theo mẫu.
2. Gửi văn bản đến đích ghi.

Mẫu có thể hoàn toàn hợp lệ nhưng đích ghi gặp lỗi. Ngược lại, đích ghi vẫn hoạt động nhưng conversion không phù hợp với đối số làm định dạng thất bại.

Với `Formatter`, cần xác định thêm:

- Văn bản đang được ghi vào bộ nhớ, tệp hay một luồng dùng chung?
- Ai sở hữu tài nguyên và ai được phép đóng?
- Khi nào cần đẩy phần đệm?
- Lỗi I/O được ném ra hay được lưu để kiểm tra?

Điểm dễ bỏ sót nhất: **Formatter có thể lưu IOException của đích thay vì ném nó trực tiếp ra từ format, flush hoặc close**. Không có ngoại lệ thoát ra chưa đủ chứng minh việc ghi đã thành công.

## 2. Đích ghi là Appendable

`Formatter` làm việc với một đích có khả năng nhận ký tự, thường qua `Appendable`.

| Loại đích | Ví dụ | Điều cần quản lý |
| --- | --- | --- |
| Bộ đệm trong bộ nhớ | `StringBuilder` | Cách lấy nội dung và chia sẻ bộ đệm |
| Luồng ký tự | `Writer`, `BufferedWriter` | Flush, close, charset ở lớp chuyển sang byte |
| Luồng in | `PrintStream` | Quyền đóng và trạng thái lỗi riêng |
| Tệp | Tạo formatter cho tệp hoặc truyền writer của tệp | Mở tệp, chế độ ghi, mã hóa, vòng đời tài nguyên |

Nếu tạo `new Formatter()`, formatter dùng một `StringBuilder` làm đích mặc định.

```java
// Mã minh họa, chưa có tài nguyên tệp bên ngoài.
try (Formatter formatter = new Formatter(Locale.ROOT)) {
    formatter.format("items=%d", 3);
    String text = formatter.toString();
    System.out.println(text);
}
```

Với đích bộ nhớ này, `toString()` lấy được nội dung đã định dạng. Nhưng **Formatter.toString() không luôn là bản sao nội dung đã ghi ra mọi loại đích**. Nó gọi `toString()` trên đích; một stream hoặc writer không bắt buộc cung cấp nội dung theo cách đó. Xem [Formatter.out và toString](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html#toString()).

Nếu cần văn bản trong một biến và chưa cần một formatter sống qua nhiều lời gọi, `String.format` thường đủ.

## 3. Quyền sở hữu quyết định có được close hay không

### Tài nguyên do đoạn mã tạo và sở hữu

Nếu đoạn mã mở một writer riêng để xuất báo cáo, nó phải bảo đảm writer được đóng. Formatter có thể đảm nhận việc đó: khi `close()`, nếu đích triển khai `Closeable`, formatter gọi `close()` của đích.

```text
Mã xuất báo cáo tạo Writer
    ↓ chuyển quyền đóng cho Formatter
Formatter dùng Writer
    ↓
Formatter.close() → Writer.close()
```

Có thể dùng `try-with-resources` cho formatter trong trường hợp sở hữu vòng đời này.

### Tài nguyên được bên gọi cho mượn

Một phương thức nhận writer từ bên ngoài không nên tự quyết định đóng nó nếu hợp đồng chỉ cho phép ghi thêm.

Đoạn sau có thể làm writer của bên gọi bị đóng:

```java
// Ví dụ không phù hợp nếu caller vẫn cần dùng writer sau lời gọi.
try (Formatter formatter = new Formatter(borrowedWriter, Locale.ROOT)) {
    formatter.format("items=%d", count);
}
```

Khi đích là tài nguyên dùng chung như `System.out`, đóng formatter bao quanh nó cũng có thể đóng chính luồng xuất dùng chung.

Một cách đơn giản khi chỉ cần tạo một đoạn văn bản là:

```java
// Mã minh họa: phương thức cho phép IOException đi lên.
String text = String.format(Locale.ROOT, "items=%d%n", count);
borrowedWriter.write(text);
// Không close writer; bên sở hữu quyết định flush/close.
```

Nếu cần giữ một formatter dùng đích mượn qua nhiều lần gọi, hợp đồng phải nói rõ ai quản lý vòng đời. Formatter không có một tùy chọn mặc định “đóng formatter nhưng luôn giữ đích Closeable mở”.

Xem [hợp đồng close của Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html#close()).

## 4. Flush làm gì và không làm gì?

`Formatter.flush()` gọi `flush()` của đích nếu đích triển khai `Flushable`.

Với một writer có đệm, việc này đẩy phần ký tự đang đệm xuống lớp dưới. Nếu đích không triển khai `Flushable`, không có thao tác flush đích để thực hiện.

Cần phân biệt:

- `format()`: tạo và ghi ký tự theo mẫu.
- `flush()`: yêu cầu lớp đệm chuyển dữ liệu xuống dưới.
- `close()`: kết thúc vòng đời formatter và đóng đích nếu đích có hợp đồng đóng.

Không coi việc thêm `%n` vào mẫu là một quy tắc luôn flush của mọi Formatter. Khả năng tự flush thuộc chính sách của từng đích, chẳng hạn một `PrintStream` có cấu hình phù hợp.

Flush cũng không tương đương một cam kết dữ liệu đã bền vững trên thiết bị lưu trữ hoặc bên nhận mạng đã xử lý xong. Các bảo đảm đó thuộc API và giao thức lưu trữ/truyền dữ liệu tương ứng.

Nếu cần thấy lỗi tại một mốc ghi báo cáo, hãy flush rồi kiểm tra kênh lỗi phù hợp; đừng chỉ nhìn việc `format()` đã trở về.

## 5. IOException được lưu trong ioException()

Đích `Appendable` có thể ném `IOException` khi nhận ký tự. Formatter lưu lỗi I/O gần nhất để lấy qua:

```java
IOException failure = formatter.ioException();
```

- `null`: formatter chưa ghi nhận IOException từ đích.
- Khác null: IOException gần nhất được ghi nhận.

Hành vi này khác với lỗi mẫu hoặc đối số như `IllegalFormatConversionException`, vốn là lỗi định dạng không kiểm tra và có thể thoát ra trực tiếp.

```text
Mẫu hoặc đối số sai
    → IllegalFormatException hoặc lớp con tương ứng

Đích ném IOException
    → Formatter lưu lại
    → kiểm tra ioException()
```

`ioException()` là **lỗi gần nhất**, không phải một danh sách lịch sử đầy đủ. Nếu ghi lỗi rồi flush lỗi rồi close lỗi, các lỗi sau có thể thay lỗi trước ở thuộc tính quan sát này. Muốn giữ đủ bằng chứng, phải lấy và ghi nhận lỗi tại các mốc cần thiết.

Một lần gọi thành công sau lỗi cũng không phải thao tác “xóa trạng thái lỗi” được API cung cấp. Không dùng `ioException()` như một cờ riêng chỉ cho lời gọi cuối mà không xét lịch sử của formatter.

## 6. Ví dụ đầy đủ: lỗi ghi, flush và close

Chương trình tạo một writer thử nghiệm có hai chế độ:

- Chế độ thường: lưu nội dung và ghi nhận đã đóng.
- Chế độ lỗi: ném IOException riêng ở write, flush và close.

Đây là lỗi được tạo có chủ ý để minh họa API, không phụ thuộc việc tệp có bị đầy đĩa hay không.

Tệp `FormatterIoDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.io.IOException;
import java.io.Writer;
import java.util.Formatter;
import java.util.FormatterClosedException;
import java.util.Locale;

public class FormatterIoDemo {
    private static final class ProbeWriter extends Writer {
        private final StringBuilder data = new StringBuilder();
        private final boolean fail;
        private boolean closed;

        ProbeWriter(boolean fail) {
            this.fail = fail;
        }

        @Override
        public void write(char[] chars, int offset, int length)
                throws IOException {
            if (fail) {
                throw new IOException("write failed");
            }
            data.append(chars, offset, length);
        }

        @Override
        public void flush() throws IOException {
            if (fail) {
                throw new IOException("flush failed");
            }
        }

        @Override
        public void close() throws IOException {
            closed = true;
            if (fail) {
                throw new IOException("close failed");
            }
        }
    }

    public static void main(String[] args) {
        ProbeWriter owned = new ProbeWriter(false);
        Formatter successful = new Formatter(owned, Locale.ROOT);
        try (successful) {
            successful.format("items=%d", 3);
            successful.flush();
        }
        System.out.println("text=" + owned.data);
        System.out.println("destinationClosed=" + owned.closed);
        System.out.println("successError=" + successful.ioException());

        ProbeWriter failing = new ProbeWriter(true);
        Formatter formatter = new Formatter(failing, Locale.ROOT);
        formatter.format("items=%d", 3);
        System.out.println("formatReturned=true");
        System.out.println("afterWrite=" + formatter.ioException().getMessage());

        formatter.flush();
        System.out.println("afterFlush=" + formatter.ioException().getMessage());

        formatter.close();
        System.out.println("afterClose=" + formatter.ioException().getMessage());
        System.out.println("failingDestinationClosed=" + failing.closed);

        try {
            formatter.format("more");
        } catch (FormatterClosedException expected) {
            System.out.println("reuse=FormatterClosedException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac FormatterIoDemo.java
java FormatterIoDemo
```

Kết quả:

```text
text=items=3
destinationClosed=true
successError=null
formatReturned=true
afterWrite=write failed
afterFlush=flush failed
afterClose=close failed
failingDestinationClosed=true
reuse=FormatterClosedException
```

Diễn giải:

1. Formatter đầu tiên ghi đúng `items=3`.
2. Ra khỏi `try-with-resources` đã gọi close của writer.
3. Không có IOException nào nên `successError=null`.
4. Formatter thứ hai vẫn trở về từ `format()` dù writer ném lỗi ghi.
5. Sau flush, lỗi gần nhất trở thành `flush failed`.
6. Sau close, lỗi gần nhất trở thành `close failed`.
7. Dù close của đích bị lỗi, formatter đã đóng và không thể dùng lại để định dạng.

`ProbeWriter` chỉ dùng để thử đường lỗi; nó không phải một writer sản xuất đầy đủ với mọi yêu cầu quản lý trạng thái và đồng thời.

Lớp `Writer` là một đích ký tự có các hợp đồng write, flush và close; xem [Writer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Writer.html).

## 7. Try-with-resources vẫn cần đi cùng kiểm tra lỗi

`try-with-resources` bảo đảm gọi `close()` khi rời khối, nhưng không thay đổi chính sách lưu IOException của formatter.

Do đó đoạn này chưa đủ để kết luận xuất báo cáo thành công:

```java
// Mã minh họa chưa kiểm tra kênh lỗi I/O.
try (Formatter formatter = new Formatter(writer, Locale.ROOT)) {
    formatter.format("items=%d%n", count);
}
```

Có thể giữ biến formatter bên ngoài để kiểm tra cả lỗi xảy ra trong close:

```java
// Mã minh họa trong phương thức throws IOException.
// writer là đích do phương thức này sở hữu.
Formatter formatter = new Formatter(writer, Locale.ROOT);
try (formatter) {
    formatter.format("items=%d%n", count);
}
IOException failure = formatter.ioException();
if (failure != null) {
    throw failure;
}
```

`ioException()` có thể được đọc sau khi formatter đã đóng. Trong khi đó các thao tác sử dụng như `format()`, `flush()`, `out()` hoặc `toString()` sau khi đóng sẽ báo `FormatterClosedException`. Gọi close lần nữa không có tác dụng.

Mẫu phía trên chuyển lỗi I/O gần nhất thành lỗi mà tầng gọi nhận được nếu phần thân kết thúc bình thường. Nếu phần thân đã ném lỗi định dạng, luồng điều khiển đi theo ngoại lệ đó; đoạn kiểm tra phía sau không tự được chạy.

Khi cần giữ đồng thời lỗi chính, lỗi ghi và lỗi đóng, hãy thiết kế thu thập riêng tại ranh giới xử lý, thay vì giả định cơ chế suppressed exception sẽ tự nhận mọi IOException mà formatter đã giữ nội bộ.

## 8. Ghi tệp: chọn charset và chế độ mở tệp rõ ràng

Mã minh họa sau nằm trong một phương thức có `throws IOException`. Nó tạo một báo cáo mới và chủ động dùng UTF-8:

```java
// Các import tương ứng: java.io.*, java.nio.charset.*,
// java.nio.file.*, java.util.*.

Path target = Path.of("report.txt");
Writer writer = Files.newBufferedWriter(
        target,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE);

Formatter formatter = new Formatter(writer, Locale.ROOT);
try (formatter) {
    formatter.format("items=%d%n", 3);
}

IOException failure = formatter.ioException();
if (failure != null) {
    throw failure;
}
```

Đây là đoạn minh họa có tác dụng tạo tệp `report.txt` mới trong thư mục làm việc. `CREATE_NEW` từ chối nếu tên đó đã tồn tại, thay vì ghi đè nội dung.

Nếu ứng dụng muốn ghi đè hoặc ghi nối tiếp, phải chọn chế độ mở tương ứng theo yêu cầu. Không suy ra chế độ từ tên tệp. Một số constructor Formatter nhận tên tệp có thể làm tệp sẵn có bị cắt nội dung khi mở.

`Files.newBufferedWriter` có thể ném IOException ngay trong lúc mở tệp. Lỗi này xảy ra **trước khi formatter được tạo**, khác với lỗi ghi/flush/close do formatter giữ lại sau đó. Xem [Files.newBufferedWriter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#newBufferedWriter(java.nio.file.Path,java.nio.charset.Charset,java.nio.file.OpenOption...)).

Charset và locale cũng khác nhau:

- UTF-8 quyết định mã hóa ký tự thành byte.
- Locale quyết định một số quy tắc biểu diễn như dấu thập phân hoặc tên tháng.

Chọn `Locale.ROOT` không tự chọn UTF-8; chọn UTF-8 không tự làm số dùng dấu chấm thập phân.

## 9. PrintStream có kênh lỗi riêng

Một điểm cần lưu ý khi dùng `System.out` hoặc `PrintStream` khác: PrintStream thường giữ lỗi I/O dưới một cờ nội bộ, thay vì ném IOException ra ngoài. Có thể kiểm tra bằng `checkError()`. Xem [PrintStream và checkError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintStream.html#checkError()).

Nếu Formatter ghi vào PrintStream mà PrintStream đã giữ lỗi bên trong, Formatter có thể không nhận được một IOException để lưu. Khi đó:

```text
formatter.ioException() == null
```

không đủ để kết luận PrintStream không có lỗi.

Với luồng in:

```java
// Mã minh họa; out là PrintStream thuộc quyền quản lý phù hợp.
out.printf(Locale.ROOT, "items=%d%n", count);
if (out.checkError()) {
    reportOutputFailure();
}
```

Không tự đóng `System.out` chỉ để buộc flush hoặc kiểm tra thành công. Luồng đó thường là tài nguyên dùng chung của ứng dụng.

Tương tự, khi xếp nhiều lớp bao đầu ra, phải biết lớp nào giữ lỗi và lớp nào ném lỗi. Kiểm tra một lớp không tự kiểm tra đầy đủ mọi lớp bên dưới.

## 10. Lỗi I/O không tự hoàn tác nội dung đã ghi

Một báo cáo có thể được ghi thành công một phần rồi lỗi ở đoạn sau. Formatter không cung cấp giao dịch tự xóa các byte hoặc ký tự đã ra đích.

Có thể phải phân biệt:

- Văn bản đã được tạo đủ chưa?
- Writer đã nhận đủ chưa?
- Flush và close có thành công không?
- Tệp đã đủ điều kiện được công bố cho bên đọc chưa?

Nếu không muốn một tệp báo cáo dở dang xuất hiện như bản hoàn chỉnh, tầng xuất báo cáo cần một quy trình phù hợp, chẳng hạn ghi vào một tệp tạm riêng, kiểm tra thành công rồi mới công bố theo khả năng hệ thống tệp. Đó là trách nhiệm ở lớp quản lý đầu ra, không phải một tính chất sẵn có của Formatter.

Cũng không thử lại toàn bộ thao tác ghi chỉ vì thấy IOException mà chưa xác định phần nào đã đến đích. Với ghi nối tiếp hoặc gửi qua giao thức bên ngoài, thử lại có thể tạo dữ liệu trùng.

## 11. Không chia sẻ Formatter tùy ý giữa các luồng

Formatter không có bảo đảm an toàn đồng thời chung. Dù đích ghi có một số thao tác được đồng bộ hóa, điều đó không tự khiến toàn bộ chuỗi `format → flush → kiểm tra lỗi` thành một giao dịch giữa nhiều luồng.

Khi có nhiều bên cùng xuất:

- Tạo văn bản riêng trước khi bàn giao cho một tầng ghi chung.
- Hoặc bảo vệ toàn bộ giao thức sử dụng formatter theo phạm vi thống nhất.
- Xác định rõ bên nào được flush và close.
- Gắn lỗi với lần xuất hoặc báo cáo đang thực hiện, không dựa vào một thuộc tính “lỗi gần nhất” bị nhiều bên ghi đè.

Đặc biệt, một luồng gọi close trong khi luồng khác đang format là một lỗi thiết kế vòng đời; không thể xử lý đầy đủ chỉ bằng cách bắt `FormatterClosedException` rồi thử lại.

## 12. Tự kiểm tra trước khi dùng

1. Đích ghi là gì, ai tạo và ai sở hữu?
2. Đóng formatter có làm đóng tài nguyên mà bên khác còn cần không?
3. Có cần flush tại một mốc cụ thể không?
4. Lỗi mở đích đi ra trực tiếp hay lỗi ghi được formatter lưu?
5. Có kiểm tra lỗi cả sau close không?
6. Nếu đích là PrintStream, đã xét `checkError()` chưa?
7. Khi lỗi xảy ra, nội dung dở dang hoặc lần ghi thử lại được xử lý ra sao?
8. Formatter có đang bị nhiều luồng dùng cùng lúc không?

Bài tập: trong ví dụ, chỉ gọi `ioException()` một lần sau close. Bạn chỉ còn thấy `close failed`, không còn toàn bộ ba thông điệp lỗi. Điều này cho thấy vì sao thời điểm kiểm tra và lưu bằng chứng quan trọng.

Một lần xuất thành công cần cả **mẫu/đối số hợp lệ**, **đích ghi hoàn tất theo giao thức**, **lỗi được kiểm tra đúng kênh** và **tài nguyên được đóng bởi đúng bên**.

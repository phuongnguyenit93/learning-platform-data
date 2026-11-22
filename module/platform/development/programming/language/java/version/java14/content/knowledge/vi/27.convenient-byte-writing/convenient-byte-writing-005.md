# Cờ lỗi và kiểm tra bằng checkError() khi ghi byte với PrintStream

## 1. Vấn đề: ghi byte không ném IOException thì biết lỗi bằng cách nào?

`java.io.PrintStream` là lớp bọc `OutputStream` để **ghi byte và in biểu diễn các giá trị** tiện dụng. Bạn thường gặp nó ở `System.out`, `System.err` hoặc khi tạo một luồng ghi ra file/thiết bị khác. Từ **Java 14**, `PrintStream` có phương thức `writeBytes(byte[])` giúp ghi toàn bộ mảng byte **mà không cần khai báo hoặc bắt checked `IOException` ở call site**.

Sự tiện lợi này **không đồng nghĩa ghi chắc chắn thành công**. Theo thiết kế của `PrintStream`, lỗi I/O được nó phát hiện thường **không được đẩy ra bằng `IOException`** từ các thao tác ghi/flush. Thay vào đó, đối tượng ghi nhận trạng thái lỗi bên trong, và người gọi phải hỏi:

~~~java
boolean failed = printStream.checkError();
~~~

Đây chính là mục tiêu của bài **“Cờ lỗi và kiểm tra bằng checkError”** thuộc nhóm **“Ghi byte tiện dụng”**:

- Hiểu `PrintStream` dùng cờ lỗi (*error flag/trouble flag*) như thế nào.
- Biết `checkError()` trả về `true`/`false` có ý nghĩa gì.
- Hiểu vì sao `checkError()` có thể **gọi flush**, chứ không chỉ đọc một biến boolean.
- Biết cờ lỗi có tính **ghi nhớ** (*sticky*), không tự chuyển về `false` sau lần ghi thành công.
- Phân biệt `writeBytes(byte[])`, `write(byte[], int, int)`, `write(byte[])` và `print/println`.
- Biết khi nào nên dùng `OutputStream`/`Files.write` để nhận trực tiếp nguyên nhân `IOException` thay vì chỉ kiểm tra cờ.
- Thực hành bằng ví dụ **Java 17+ hoàn chỉnh**, chủ động mô phỏng lỗi ghi và lỗi flush để kết quả tái lập được.

**Giới hạn phiên bản:** `checkError()` là cơ chế đã tồn tại từ trước Java 14; điểm mới gắn với chủ đề Java 14 là `PrintStream.writeBytes(byte[])` được giới thiệu ở **Java 14**. Cả hai tiếp tục được hỗ trợ trong JDK hiện đại. Bài chỉ mô tả hành vi và API hiện còn áp dụng, không sử dụng kỹ thuật legacy hoặc cờ JVM đã lỗi thời.

## 2. Hai đặc điểm quan trọng của PrintStream

### 2.1. PrintStream bao lấy OutputStream

~~~java
import java.io.PrintStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

PrintStream ps = new PrintStream(
        someOutputStream, false, StandardCharsets.UTF_8);
~~~

Đây là **đoạn minh họa trong phương thức**; `someOutputStream` là một đối tượng `OutputStream` do ứng dụng cung cấp.

`PrintStream` có thể chuyển giá trị từ Java sang text bằng `print`, `println`, `printf`, `format`, hoặc ghi **byte đã có sẵn** bằng `writeBytes`/`write`. Constructor có `Charset` giúp tránh phụ thuộc mặc định vào charset của môi trường **khi in ký tự**, nhưng `writeBytes` **không thực hiện mã hóa chuỗi**: nó chuyển những byte trong mảng trực tiếp đến luồng nền.

### 2.2. Lỗi I/O được phản ánh thành trạng thái

Với một `OutputStream` thông thường, lời gọi:

~~~java
output.write(bytes);
~~~

có thể khai báo và ném `IOException`, cho phép caller biết lỗi và có thể xem cause/message. Ngược lại:

~~~java
printStream.writeBytes(bytes);
boolean failed = printStream.checkError();
~~~

`PrintStream` sẽ bắt các lỗi I/O theo hợp đồng của lớp và cập nhật cờ lỗi. Sau một thao tác ghi, **không có exception** từ `writeBytes` không chứng minh byte đã được ghi thành công.

Đặc biệt, vì `checkError()` trả về một **boolean trạng thái tổng hợp**, nó không cho biết cụ thể thao tác nào hỏng, bao nhiêu byte đã đến đích hoặc nguyên nhân từ hệ thống tệp/mạng.

## 3. API chính: checkError()

Chữ ký:

~~~java
public boolean checkError()
~~~

Theo Javadoc `PrintStream`, phương thức này:

1. **Flush luồng nếu chưa đóng**. Flush có thể thực hiện I/O và bản thân nó cũng có thể thất bại.
2. **Kiểm tra trạng thái lỗi** mà `PrintStream` đã lưu.
3. Trả về **`true`** khi luồng đã ghi nhận `IOException` theo hợp đồng hoặc `setError()` đã được gọi; trả về **`false`** khi không có trạng thái lỗi đã ghi nhận.

Bảng hiểu nhanh:

| Giá trị | Ý nghĩa thực tế | Không được kết luận |
|---|---|---|
| `false` | Chưa có lỗi I/O tương ứng được `PrintStream` ghi nhận tại thời điểm kiểm tra | Mọi byte chắc chắn đã được đồng bộ xuống đĩa hoặc được hệ thống bên kia xác nhận |
| `true` | Luồng đã có trạng thái lỗi, do I/O hoặc `setError()` | Tất cả byte đều mất, hoặc biết chính xác lần nào/loại lỗi nào xảy ra |

**`checkError()` không có tác dụng xóa lỗi.** Nó không phải “đọc rồi reset” hay “đặt lại cho lần tiếp theo”. Cũng không có cơ chế tự reset lỗi sau một lần ghi thành công; cờ có thể giữ `true` cho tới khi `clearError()` được gọi trong lớp kế thừa.

### Cờ lỗi được hình thành như thế nào?

~~~text
Ứng dụng
   |
   +--- ps.writeBytes(data)
   |        |
   |        v
   |   OutputStream phía dưới
   |        |
   |   +----+-----------+
   |   |                |
   |  Ghi được       IOException
   |   |                |
   |   |                v
   |   |         PrintStream lưu lỗi
   |   |                |
   +---+----------------+
   |
   v
ps.checkError()
   |
   +-- flush nếu chưa đóng
   |         |
   |         +-- lỗi flush? => cập nhật cờ
   |
   v
true hoặc false
~~~

Sơ đồ mô tả luồng khái niệm. Trong Java 17, `InterruptedIOException` có xử lý đặc biệt được nói ở phần sau; không nên đồng nhất mọi kiểu ngắt với một `IOException` thông thường.

## 4. Cờ lỗi “sticky”: một lần lỗi, những lần kiểm tra sau vẫn thấy lỗi

Giả sử `OutputStream` phía dưới chỉ thất bại ở **lần ghi đầu tiên**, nhưng thành công ở lần tiếp theo. Với một `PrintStream` cùng vòng đời:

~~~java
ps.writeBytes(firstBatch);   // Lần đầu làm OutputStream ném IOException.
boolean a = ps.checkError(); // true

ps.writeBytes(secondBatch);  // Lần sau thành công.
boolean b = ps.checkError(); // vẫn true
~~~

Đây là **mảnh code minh họa**, với `ps` và hai mảng byte được khởi tạo ở nơi khác. `b` vẫn `true` vì `checkError()` phản ánh **lịch sử lỗi chưa được xóa**, không phải chỉ trạng thái của lời gọi `writeBytes` ngay trước nó.

**Hệ quả:**

- Nếu xử lý nhiều bản ghi bằng cùng `PrintStream`, không thể hỏi `checkError()` sau mỗi bản ghi rồi coi `true/false` là **kết quả riêng biệt của mỗi bản ghi** khi cờ đã từng `true`.
- Khi có lỗi, ứng dụng cần phân loại xử lý: ngừng ghi, báo lỗi, tái tạo output stream, retry có kiểm soát hoặc chuyển sang API có exception/cause.
- **Không tự “chữa” tình trạng I/O bằng cách xóa flag**. Cờ báo lỗi là thông tin quan sát, không sửa ổ đĩa đầy, quyền truy cập hoặc kết nối mạng bị đứt.

### setError() và clearError() là protected

`PrintStream` có:

~~~java
protected void setError()
protected void clearError()
~~~

Chúng **không phải public API** để mọi client tùy ý thay đổi cờ lỗi của `System.out` hay một `PrintStream` đang sử dụng. Một **subclass** có thể gọi `setError()` để ghi nhận lỗi và `clearError()` để xóa flag.

`clearError()` làm lần `checkError()` sau có thể trả `false` **nếu không phát sinh lỗi mới**. Nhưng nếu underlying `OutputStream` vẫn hỏng hoặc `flush()` thất bại, `checkError()` có thể lại trả `true` ngay. Vì vậy không dùng `clearError()` như thủ thuật giả vờ đã sửa xong lỗi.

## 5. checkError() có thể flush: tại sao quan trọng?

Giả sử `PrintStream` được tạo với `autoFlush=false`. Trong trường hợp đó:

~~~java
ps.writeBytes(new byte[] { 1, 2, 3 });
boolean failed = ps.checkError();
~~~

Dù chưa gọi `ps.flush()` trực tiếp, `checkError()` **gọi flush khi luồng chưa đóng**. Nếu tầng bên dưới chỉ phát hiện lỗi khi flush, cờ lỗi có thể chuyển `true` **ngay trong lời gọi kiểm tra**.

Điều này có hai hệ quả:

1. **`checkError()` không phải một boolean getter thuần túy.** Nó có thể đi qua I/O (và có thể tốn thời gian, block, hoặc gặp lỗi).
2. Nếu chỉ hỏi sau khi write mà chưa xét flush, kết quả sẽ khác so với cách một `OutputStream` thẳng ném exception trong `flush()`.

### autoFlush=true không có nghĩa mọi byte đã xuống đĩa

Với `new PrintStream(out, true, charset)`, theo Javadoc, PrintStream có thể tự flush sau **một lần ghi mảng byte**, sau `println` hoặc sau khi ghi newline character/byte `'\n'` theo overload phù hợp. Điều đó khác với **đồng bộ bền vững xuống thiết bị lưu trữ**.

**Không nhầm `flush()` với `fsync`, `FileChannel.force(...)`, xác nhận từ server hoặc atomic commit.** `flush()` xử lý bộ đệm theo hợp đồng của stream, không bảo đảm giao dịch của ứng dụng đã thành công bền vững.

### close() và checkError()

`close()` của `PrintStream` có thể cố flush/close tầng phía dưới. Nếu tầng dưới ném `IOException` và PrintStream ghi nhận, trạng thái lỗi có thể trở thành `true`. `checkError()` khi stream đã đóng **không cố tiếp tục flush một stream đã đóng**, nhưng vẫn có thể đọc trạng thái lỗi đã ghi nhận.

Một lời gọi `writeBytes` **sau khi đóng `PrintStream`** không phải thao tác ghi hợp lệ; PrintStream có thể đánh dấu lỗi và `checkError()` báo `true`, như ví dụ chạy thử trong bài.

**Lưu ý:** đóng `PrintStream` bọc `System.out` hoặc `System.err` có thể làm đóng luồng console của toàn bộ tiến trình. Không dùng `try-with-resources` để tự đóng các stream toàn cục này trong ứng dụng thông thường.

## 6. Ghi byte với writeBytes từ Java 14

### 6.1. Ba overload dễ nhầm

| API | Tính năng | Checked IOException ở chữ ký | Nên dùng khi |
|---|---|---|---|
| `PrintStream.writeBytes(byte[])` | Ghi toàn bộ mảng byte | **Không** | Muốn ghi byte gọn với cơ chế cờ lỗi của PrintStream |
| `PrintStream.write(byte[],int,int)` | Ghi một đoạn mảng theo offset/length | **Không** | Muốn chọn một vùng byte, không cần `catch IOException` |
| `PrintStream.write(byte[])` | Ghi toàn bộ byte, nhưng kế thừa chữ ký khai báo `throws IOException` | **Có** ở chữ ký; implementation `PrintStream` không ném IOException I/O đó | Cần tương thích API/overload, nhưng call site vẫn phải xử lý checked exception |
| `OutputStream.write(byte[])` | Ghi toàn bộ byte vào stream thường | **Có** | Cần exception và nguyên nhân lỗi I/O trực tiếp |

`PrintStream.writeBytes(byte[])` (từ Java 14) có **ngữ nghĩa tương đương**:

~~~java
ps.write(buf, 0, buf.length);
~~~

Với `PrintStream`, hai cách không yêu cầu `catch IOException`. Dùng `writeBytes` giúp rõ ý định “ghi toàn bộ mảng”, tránh việc `write(byte[])` có chữ ký `throws IOException` làm call site cần xử lý checked exception dù implementation `PrintStream` bắt I/O.

### 6.2. Ghi raw bytes không phải in text

~~~java
byte[] payload = { 0x41, 0x00, (byte) 0xff };
ps.writeBytes(payload);
~~~

Byte trong mảng được truyền như dữ liệu thô. Khi dùng `print("A")` hoặc `println("Xin chào")`, ký tự được chuyển sang byte bằng charset được cấu hình. Tách rõ hai mục đích:

- **Dữ liệu nhị phân:** `writeBytes` hoặc `OutputStream.write`.
- **Văn bản:** `print/println` với charset rõ ràng, hoặc `Writer`/`PrintWriter` nếu mục tiêu chủ yếu là ký tự.

`writeBytes` không tự thêm newline, không tự mã hóa UTF-8, không gắn thông tin độ dài bản ghi và không tự checksum payload.

### 6.3. Cẩn thận với lỗi đối số không phải I/O

Một `byte[]` null có thể gây `NullPointerException` khi tính `buf.length`. Một vùng byte không hợp lệ với `write(buf,off,len)` có thể gây `IndexOutOfBoundsException`. Đây là **unchecked exceptions** do lời gọi sai, **không phải trạng thái lỗi I/O chỉ cần quan sát bằng `checkError()`**.

**Không viết code giả định mọi lỗi, kể cả lập trình sai, đều chuyển thành `checkError()==true`**. PrintStream chủ yếu che giấu lỗi **I/O** của output; bug argument/call site vẫn cần xử lý đúng.

## 7. Chương trình Java 17+ hoàn chỉnh: thành công, lỗi ghi, lỗi flush và cờ sticky

Bài thực hành dưới đây **không cần quyền truy cập file thật hoặc mạng thật**. Chúng ta tạo các `OutputStream` giả lập để kiểm soát lỗi một cách xác định, rồi bọc bằng `PrintStream`. Điều này tránh phụ thuộc vào hệ điều hành, đường dẫn, dung lượng đĩa hay kết nối mạng.

Lưu file **`PrintStreamCheckErrorDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public final class PrintStreamCheckErrorDemo {
    private static final class FailOnce extends OutputStream {
        int attempts;

        @Override
        public void write(int b) throws IOException {
            if (++attempts == 1) {
                throw new IOException("simulated write failure");
            }
        }
    }

    private static final class FailsOnFlush extends OutputStream {
        int flushCalls;

        @Override
        public void write(int b) { }

        @Override
        public void flush() throws IOException {
            flushCalls++;
            throw new IOException("simulated flush failure");
        }
    }

    private static final class Controllable extends PrintStream {
        Controllable(OutputStream out) {
            super(out, false, StandardCharsets.UTF_8);
        }

        void mark() { setError(); }
        void resetFlag() { clearError(); }
    }

    public static void main(String[] args) {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (PrintStream ps =
                new PrintStream(sink, false, StandardCharsets.UTF_8)) {
            ps.writeBytes(new byte[] { 0x41, 0x00, (byte) 0xff });
            System.out.println("ok.error=" + ps.checkError());
        }
        System.out.println("ok.hex=" +
                HexFormat.of().formatHex(sink.toByteArray()));

        FailOnce broken = new FailOnce();
        try (PrintStream ps =
                new PrintStream(broken, false, StandardCharsets.UTF_8)) {
            ps.writeBytes(new byte[] { 1 });
            System.out.println("write.error=" + ps.checkError());
            ps.writeBytes(new byte[] { 2 });
            System.out.println("write.sticky=" + ps.checkError());
            System.out.println("write.attempts=" + broken.attempts);
        }

        FailsOnFlush flushOnly = new FailsOnFlush();
        try (PrintStream ps =
                new PrintStream(flushOnly, false, StandardCharsets.UTF_8)) {
            ps.writeBytes(new byte[] { 7 });
            System.out.println("flush.error=" + ps.checkError());
            System.out.println("flush.calls=" + flushOnly.flushCalls);
        }

        try (Controllable ps =
                new Controllable(new ByteArrayOutputStream())) {
            ps.mark();
            System.out.println("marked.error=" + ps.checkError());
            ps.resetFlag();
            System.out.println("cleared.error=" + ps.checkError());
        }

        PrintStream closed = new PrintStream(
                new ByteArrayOutputStream(),
                false, StandardCharsets.UTF_8);
        closed.close();
        closed.writeBytes(new byte[] { 5 });
        System.out.println("closedWrite.error=" + closed.checkError());
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac --release 17 PrintStreamCheckErrorDemo.java
java PrintStreamCheckErrorDemo
~~~

**Standard output đã biên dịch và chạy thực tế:**

~~~text
ok.error=false
ok.hex=4100ff
write.error=true
write.sticky=true
write.attempts=2
flush.error=true
flush.calls=1
marked.error=true
cleared.error=false
closedWrite.error=true
~~~

`HexFormat` là API chuẩn Java 17; `HexFormat.of().formatHex(...)` cho phép kiểm tra byte bằng hex thay vì chuyển byte nhị phân sang `String` với charset không xác định.

### Phân tích phần thành công

~~~java
ByteArrayOutputStream sink = new ByteArrayOutputStream();
try (PrintStream ps =
        new PrintStream(sink, false, StandardCharsets.UTF_8)) {
    ps.writeBytes(new byte[] { 0x41, 0x00, (byte) 0xff });
    System.out.println("ok.error=" + ps.checkError());
}
~~~

`ByteArrayOutputStream` giữ byte trong bộ nhớ, không tự ném lỗi I/O trong trường hợp bình thường; `checkError()==false`. Byte gốc gồm `0x41`, `0x00`, `0xFF`, nên hex là `4100ff`. Byte `0xFF` không được tự động thay hoặc biến thành ký tự khác, vì `writeBytes` không làm text encoding.

### Phân tích lỗi write

~~~java
@Override
public void write(int b) throws IOException {
    if (++attempts == 1) {
        throw new IOException("simulated write failure");
    }
}
~~~

`FailOnce` cố tình thất bại **lần write đầu**, thành công lần hai. `PrintStream.writeBytes` không đẩy IOException ra caller mà ghi cờ lỗi. Lần sau ghi được nhưng `write.sticky=true` — đây là bằng chứng trực tiếp về tính **sticky**. `attempts=2` cho thấy underlying stream nhận cả hai lần thử ghi.

**Không được suy ra “lần ghi thứ hai cũng hỏng” chỉ vì cờ vẫn true.** Nó có thể chỉ phản ánh lỗi trước đó. Nếu cần phân biệt kết quả từng record một cách mạnh mẽ, chọn thiết kế khác thay vì dùng một cờ lỗi tồn tại suốt đời stream.

### Phân tích lỗi flush

`FailsOnFlush` chấp nhận `write(int)` nhưng ném `IOException` tại `flush()`. Vì chúng ta dùng `autoFlush=false`, `writeBytes(new byte[]{7})` không tự flush, và `checkError()` kích hoạt flush. Do đó:

~~~text
flush.error=true
flush.calls=1
~~~

`flush.calls=1` được in **trước khi khối try đóng stream**; đóng stream có thể thêm thao tác flush/close sau đó, nhưng không làm thay đổi dòng output đã in. Đoạn này kiểm chứng `checkError()` là **thao tác có thể gây I/O**, không phải getter không tác dụng phụ.

### Phân tích setError / clearError

`Controllable` là subclass chỉ dành cho thử nghiệm. Nó gọi được hai phương thức `protected`:

~~~java
void mark() { setError(); }
void resetFlag() { clearError(); }
~~~

Sau `mark()`, `checkError()` trả `true`; sau `resetFlag()`, với `ByteArrayOutputStream` khỏe mạnh, `checkError()` trả `false`. **Điều đó không đồng nghĩa bạn nên xóa flag để cho qua lỗi I/O thật**. Trong ví dụ, lỗi được đặt nhân tạo để minh họa quyền truy cập `protected`.

### Phân tích ghi sau close

Sau khi `closed.close()`, lời gọi `closed.writeBytes(...)` bị PrintStream xử lý như thao tác trên luồng đã đóng, và ví dụ nhận `closedWrite.error=true`. Luồng đã đóng không được sử dụng để gửi payload mới. Hãy dùng vòng đời `try-with-resources` đối với stream mà chính ứng dụng sở hữu.

## 8. checkError() không phải cam kết giao byte thành công tuyệt đối

Một số giới hạn cần hiểu khi làm việc với file, socket hoặc hệ thống bất đồng bộ:

1. **Không có cause chi tiết:** `checkError()` trả boolean, không cho lại `IOException` gốc để phân tích đường dẫn, mã lỗi OS hoặc kết nối.
2. **Không có số byte thành công:** đặc biệt với các stream có thể ghi một phần, cờ lỗi không trả về số lượng byte đã đến đích.
3. **Không đảm bảo bền vững:** tầng dưới có thể đang buffer; flush có thể chuyển dữ liệu xuống lớp thấp hơn nhưng không tương đương durable commit hay remote acknowledgment.
4. **Không giải quyết được lỗi phát sinh về sau:** một hệ thống nhận dữ liệu bất đồng bộ có thể báo thất bại sau khi lần `checkError` hiện tại đã trả `false`.
5. **Không phát hiện được lỗi mà tầng dưới tự che giấu:** nếu một `OutputStream` wrapper khác tự nuốt lỗi và không báo lại, PrintStream không thể tự biết điều nó không nhận được.
6. **Cờ có tính tích lũy:** `true` có thể phản ánh thao tác ghi trước đó, không gắn cố định với batch đang được kiểm tra.
7. **Flush có thể block:** đừng gọi `checkError()` trong vòng hot loop tần suất cực cao nếu không cân nhắc chi phí I/O.
8. **Không thay kiểm tra toàn vẹn dữ liệu:** muốn chắc chắn payload đúng ở đích, cần protocol, hash, checksum, transaction hoặc acknowledgment phù hợp với ứng dụng.

**Kết luận thực dụng:** `PrintStream.checkError` hữu ích cho ghi log, console và output đơn giản. Với giao dịch hoặc bản ghi không được phép mất, nên ưu tiên API cho phép xử lý `IOException` trực tiếp và thiết kế xác nhận bền vững.

## 9. Khi nào nên dùng OutputStream hoặc Files thay vì PrintStream?

So sánh:

| Nhu cầu | API phù hợp | Lý do |
|---|---|---|
| In text ra console | `System.out.println(...)` và tùy trường hợp `System.out.checkError()` | Tiện dụng, mặc định có sẵn |
| Ghi mảng byte ra console | `System.out.writeBytes(bytes)`, sau đó `checkError()` nếu cần | Không cần checked IOException, dữ liệu raw byte |
| Ghi vài byte vào `ByteArrayOutputStream` | `writeBytes` hoặc `write` | Tác vụ đơn giản trong bộ nhớ |
| Ghi file có yêu cầu phát hiện I/O failure chi tiết | `Files.write(...)` hoặc `Files.newOutputStream(...)` | Có `IOException` gốc và stack trace/cause |
| Gửi qua socket hoặc giao thức cần acknowledgment | `OutputStream` phù hợp, cộng giao thức xác nhận | Không được dùng `checkError()==false` làm ACK |
| Định dạng văn bản | `Writer` hoặc `PrintWriter` với Charset rõ ràng | Là API hướng ký tự; `PrintWriter` có cơ chế lỗi riêng |
| Cần durability của file | `FileChannel.force(...)` hoặc cơ chế lưu trữ tương ứng | `flush()` không thay thế flush xuống storage như `force` |

### Ví dụ OutputStream báo lỗi trực tiếp

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("output.bin");
byte[] payload = { 1, 2, 3 };

try (OutputStream output = Files.newOutputStream(path)) {
    output.write(payload);
    output.flush();
} catch (IOException ex) {
    System.err.println("Không ghi được output.bin: " + ex.getMessage());
    // Ứng dụng quyết định retry, rollback hoặc dừng công việc.
}
~~~

Đây là **đoạn Java minh họa**, chạy trong một phương thức. `Files.newOutputStream` có thể ném `IOException` khi mở; `write`, `flush` và `close` cũng có thể ném `IOException`, nên `try-with-resources` giúp báo lỗi I/O liên quan đến vòng đời stream. Nó không tự cam kết `fsync`, atomic replace hay dữ liệu đã được bên nhận xác nhận.

**Lợi thế:** exception mang nguyên nhân cụ thể, tiện cho logging, phân tích và điều phối retry. **Không phải `OutputStream` nào cũng luôn thành công hoặc có cùng semantics**, nhưng caller có con đường xử lý lỗi rõ ràng.

### Ví dụ vẫn dùng PrintStream nhưng buộc kiểm tra cờ

~~~java
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

try (PrintStream ps = new PrintStream(
        targetOutputStream, false, StandardCharsets.UTF_8)) {
    ps.writeBytes(payload);

    if (ps.checkError()) {
        throw new IOException("PrintStream đã ghi nhận lỗi I/O");
    }
}
~~~

Đây là **đoạn minh họa**, với `targetOutputStream` và `payload` đã được tạo. Nó có thể báo khi `write` hoặc `flush` hỏng **trước khi close**, nhưng chưa kiểm tra lỗi chỉ phát sinh **trong close** vì khối try sẽ đóng sau khi ra khỏi body. Với yêu cầu nghiêm ngặt, phải thiết kế cách kiểm tra thêm sau close và cân nhắc dùng `OutputStream` trực tiếp.

### Lưu ý việc kiểm tra sau close

Nếu stream do ứng dụng sở hữu, có thể lưu tham chiếu và kiểm tra trạng thái sau khi đã đóng:

~~~java
PrintStream ps = new PrintStream(
        targetOutputStream, false, StandardCharsets.UTF_8);
try {
    ps.writeBytes(payload);
} finally {
    ps.close();
}
if (ps.checkError()) {
    throw new IOException("Lỗi ghi hoặc đóng PrintStream");
}
~~~

`targetOutputStream` và `payload` là biến minh họa; constructor nhận `OutputStream` và `Charset` phù hợp. Trường hợp này giúp kiểm tra cờ sau vòng đời close, nhưng **vẫn chỉ có boolean**, không thay thế được exception gốc như `OutputStream.close()`. Và với stream bao nhiều lớp có luồng xử lý bên dưới không báo lỗi trực tiếp, kết quả vẫn theo khả năng quan sát của `PrintStream`.

## 10. System.out, System.err và một số lỗi vận hành

`System.out` và `System.err` là `PrintStream`. Bạn có thể viết:

~~~java
System.out.println("Hello");
if (System.out.checkError()) {
    // Có vấn đề I/O được PrintStream ghi nhận ở console output.
}
~~~

**Đây không phải cách ép console phản hồi người dùng.** Nó chỉ hỏi trạng thái của output stream theo cơ chế Java. Nếu stdout được pipe sang lệnh khác và phía nhận đóng sớm, ghi console có thể thất bại mà không ném checked `IOException`; kiểm tra `checkError` giúp phát hiện lỗi đã ghi nhận.

Tuy nhiên, có vài giới hạn vận hành:

- **Không tự đóng `System.out`/`System.err`** trong một method thư viện; chúng là tài nguyên dùng chung của tiến trình.
- Nếu `System.out.checkError()==true`, in thông báo lỗi tiếp bằng **chính `System.out`** có thể lại thất bại. Cân nhắc `System.err` hoặc một kênh diagnostic độc lập, nhưng cũng phải xử lý trường hợp kênh ấy hỏng.
- Một ứng dụng CLI quan trọng có thể cần đặt **exit status không bằng 0** khi phát hiện output error; `PrintStream` tự nó không thay đổi exit code giúp bạn.
- Nếu stream được thay bằng `System.setOut(...)`, hành vi bên dưới phụ thuộc stream mới; tránh giả định nó luôn là console vật lý.
- Đừng gọi `System.out.checkError()` thay cho việc kiểm tra kết quả công việc không liên quan I/O.

### PrintWriter khác PrintStream ra sao?

`java.io.PrintWriter` cũng có `checkError()` và cơ chế ghi nhận lỗi, nhưng là API **ghi ký tự**. Nó **không cung cấp `writeBytes(byte[])`**, và quy tắc autoFlush của `PrintWriter` khác: thường flush khi gọi `println`, `printf` hoặc `format` theo thiết lập, không phải tự động flush khi chỉ ghi một ký tự newline bình thường.

**Chọn theo dữ liệu:** byte thô → `PrintStream`/`OutputStream`; text → `Writer`/`PrintWriter`. Nếu cần exception trực tiếp, sử dụng writer/stream có phương thức ghi khai báo `IOException` phù hợp, thay vì cho rằng PrintWriter sẽ ném lỗi I/O từ mọi `print`.

## 11. Ngoại lệ và trường hợp biên

### 11.1. Lỗi I/O so với lỗi lập trình

`checkError()` là kênh phát hiện **lỗi I/O mà PrintStream ghi nhận**. Nó không phải cách thay tất cả exception:

- `writeBytes(null)` có thể ném `NullPointerException`.
- `write(buf, off, len)` với `off/len` ngoài biên có thể ném `IndexOutOfBoundsException`.
- `String.format`/`printf` với format string sai có thể ném `IllegalFormatException`.
- Những lỗi runtime nghiêm trọng ngoài phạm vi xử lý I/O vẫn có thể xảy ra; đừng bắt `Throwable` rồi xem như chỉ có flag.

### 11.2. InterruptedIOException có lưu ý theo JDK

Javadoc `PrintStream` của **Java 17** mô tả rằng `InterruptedIOException` được xử lý bằng cách **đặt interrupt status của thread** (hoặc tương đương), khác cách đánh dấu trouble của `IOException` thông thường. Javadoc Java 26 mô tả phạm vi `IOException` ngắn gọn hơn. Do đó, khi xử lý cancellation/interruption, **đừng chỉ nhìn `checkError()` rồi coi nó là tín hiệu đầy đủ cho interrupt**; phải giữ đúng hợp đồng interrupt của API/JDK đang chạy.

Ví dụ xử lý ở một công việc có thể bị interrupt phải kiểm tra `Thread.currentThread().isInterrupted()` tại ranh giới thích hợp, và không xóa trạng thái interrupt một cách tùy tiện. Không dựa vào một tình huống giả lập `InterruptedIOException` duy nhất để kết luận tất cả vendor/JDK đều có behavior y hệt.

### 11.3. Trạng thái từ nhiều tầng output

Khi một `PrintStream` bọc nhiều tầng `OutputStream`/buffer, việc `checkError` phát hiện gì phụ thuộc các lỗi mà tầng dưới **thực sự báo lên trên**. Nếu tầng bên dưới tự nuốt exception, ghi bất đồng bộ hoặc chỉ xác nhận đã đưa vào queue, `PrintStream` không có thông tin để chứng minh byte đã được tiêu thụ bền vững.

Nếu API/kiến trúc có yêu cầu tin cậy cao, chọn **acknowledgment protocol**, write + fsync/atomic replacement hoặc transaction theo miền nghiệp vụ. Một boolean cờ lỗi không thay thế những điều kiện đó.

## 12. Checklist ứng dụng checkError()

- [ ] Đang dùng `PrintStream` thực sự hay `OutputStream`/`PrintWriter`?
- [ ] Muốn ghi byte raw bằng `writeBytes` hay text bằng `print/println`?
- [ ] Nếu dùng `writeBytes(byte[])`, đã biết đây là API Java 14+?
- [ ] Mảng byte không null và phần offset/length (nếu có) hợp lệ?
- [ ] Có cấu hình charset rõ ràng cho những phần in ký tự?
- [ ] Hiểu `checkError()` **có thể flush**, vì vậy có thể chặn hoặc phát sinh lỗi mới?
- [ ] Có kiểm tra lỗi tại ranh giới phù hợp thay vì mỗi byte?
- [ ] Không coi `false` là bằng chứng fsync/remote acknowledgment?
- [ ] Không coi `true` là thất bại của **riêng** lần ghi vừa xảy ra?
- [ ] Biết cờ lỗi sticky và `clearError()` là protected, không nên dùng để che lỗi?
- [ ] Có xét lỗi chỉ phát sinh ở `close()`?
- [ ] Nếu phát hiện lỗi, có dừng/ghi log/đặt exit status/retry theo chính sách?
- [ ] Không đóng `System.out`/`System.err` từ helper dùng chung?
- [ ] Nếu cần nguyên nhân I/O, đã cân nhắc `OutputStream` hoặc `Files.write`?
- [ ] Nếu chạy trên nhiều JDK, đã xét hợp đồng xử lý interruption?
- [ ] Với file/remote output quan trọng, đã có kiểm tra toàn vẹn hoặc durability riêng?

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `PrintStream.writeBytes(byte[])` bắt đầu được hỗ trợ từ Java bao nhiêu?

**Đáp án:** Java 14. Cơ chế `PrintStream.checkError()` đã tồn tại trước đó và vẫn được dùng để kiểm tra cờ lỗi I/O.

**Câu 2.** Gọi `ps.writeBytes(data)` không ném `IOException`, vậy có chắc dữ liệu đã ghi hết không?

**Đáp án:** Không. PrintStream có thể bắt lỗi I/O và đặt cờ; cần kiểm tra `checkError()`, nhưng kết quả false vẫn không bảo đảm fsync hoặc remote acknowledgment.

**Câu 3.** `checkError()` chỉ đọc boolean hay còn làm gì?

**Đáp án:** Nếu stream chưa đóng, nó **flush** rồi kiểm tra trạng thái lỗi. Do đó chính lần kiểm tra có thể gặp lỗi flush.

**Câu 4.** Sau một lần lỗi, lần write sau thành công. `checkError()` có tự trở về false không?

**Đáp án:** Không. Cờ sticky, giữ true cho tới khi bị clear bởi subclass hoặc tình trạng phù hợp được quản lý theo API; một lần ghi thành công không reset.

**Câu 5.** Vì sao `writeBytes(data)` tiện hơn `write(data)` khi biến có kiểu `PrintStream`?

**Đáp án:** `write(byte[])` có chữ ký kế thừa khai báo `throws IOException` nên call site phải xử lý checked exception. `writeBytes(byte[])` và `write(byte[],0,len)` không khai báo checked IOException trong `PrintStream`, trong khi vẫn ghi thông qua cơ chế cờ lỗi.

**Câu 6.** `writeBytes` có dùng charset constructor để chuyển byte không?

**Đáp án:** Không. Nó ghi đúng những byte từ mảng. Charset dùng khi PrintStream chuyển **ký tự** thành byte qua `print/println`.

**Câu 7.** `setError()` và `clearError()` có public không?

**Đáp án:** Không, chúng là **protected**. Chỉ những ngữ cảnh Java có quyền phù hợp (ví dụ subclass) mới gọi được. `clearError` không tự sửa luồng hỏng.

**Câu 8.** Nếu `System.out.checkError()==true`, liệu in thêm lỗi ra System.out có đáng tin không?

**Đáp án:** Không. Cùng kênh output có thể vẫn hỏng. Cần một kênh diagnostics khác hoặc cơ chế báo lỗi/exit status phù hợp.

**Câu 9.** Vì sao `HexFormat` phù hợp để xem byte `0xFF` trong demo?

**Đáp án:** Nó hiển thị dữ liệu byte dưới dạng hex xác định, tránh giả định byte nhị phân bất kỳ là text hợp lệ theo charset nào đó.

**Câu 10.** Khi ghi file phải biết chính xác nguyên nhân thất bại, nên chọn gì?

**Đáp án:** `OutputStream`/`Files.newOutputStream` hoặc `Files.write` với xử lý `IOException`, vì `checkError` chỉ trả boolean.

**Câu 11.** `checkError()==false` sau flush có nghĩa file đã an toàn trước mất điện không?

**Đáp án:** Không. Flush của stream không đồng nghĩa flush bền vững xuống thiết bị lưu trữ. Cần kỹ thuật durability riêng theo yêu cầu.

**Câu 12.** Trong demo, vì sao `flush.calls=1` dù không gọi `ps.flush()` thủ công?

**Đáp án:** `ps.checkError()` gọi flush cho stream còn mở. Test in số lần flush **trước khi try-with-resources đóng stream**, nên quan sát được đúng một lời gọi tại thời điểm in.

## 14. Tài liệu tham khảo còn áp dụng

- [Oracle Java SE 17 — PrintStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html): `writeBytes(byte[])` (Since 14), `checkError()`, `setError()`, `clearError()`, `write(...)`, autoFlush và xử lý lỗi I/O.
- [Oracle Java SE 26 — PrintStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/PrintStream.html): đối chiếu API hiện đại; ghi nhận khác biệt diễn đạt Javadoc về `checkError` và interruption.
- [Oracle Java SE 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): cách ghi byte và hợp đồng `IOException` của output stream.
- [Oracle Java SE 17 — PrintWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html): phương thức `checkError` khi ghi ký tự và khác biệt autoFlush.
- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): ghi file, mở output stream và exception khi thất bại.
- [Oracle Java SE 17 — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): hiển thị byte dưới dạng hex chuẩn, dùng trong chương trình Java 17+.
- [Oracle Java SE 17 — ByteArrayOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html): stream lưu byte trong bộ nhớ để kiểm thử.

**Ghi nhớ:** `PrintStream.writeBytes(byte[])` là tiện ích ghi raw bytes từ Java 14, nhưng **không ném `IOException` khi underlying output gặp lỗi I/O theo cơ chế của PrintStream**. Muốn quan sát lỗi, dùng `checkError()`, biết rằng nó **có thể flush** và trả **trạng thái lỗi sticky**, không phải xác nhận bền vững hay kết quả riêng của một lần ghi. Với dữ liệu quan trọng cần nguyên nhân lỗi và xử lý tin cậy, ưu tiên `OutputStream`/`Files` và cơ chế kiểm tra toàn vẹn, durability thích hợp.
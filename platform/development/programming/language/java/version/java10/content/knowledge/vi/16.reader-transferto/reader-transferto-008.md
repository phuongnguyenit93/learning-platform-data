# `Reader.transferTo`: `IOException` và dữ liệu có thể đã được chuyển một phần

> **Java 10 — `java.io.Reader.transferTo(Writer)`.** Khi việc chuyển dòng ký tự thất bại, đừng giả định rằng đích còn nguyên, nguồn vẫn ở vị trí ban đầu hoặc có thể an toàn gọi lại `transferTo`. Phương thức được bổ sung trong Java 10 và **vẫn được hỗ trợ trên các JDK hiện đại**. Bài tập trung vào tình huống `IOException` xảy ra *sau khi đã đọc/ghi được một phần*; không khuyến khích cài hoặc triển khai dựa trên JDK 10 đã hết vòng đời.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Đọc đúng hợp đồng của `Reader.transferTo(Writer)`, phân biệt **giá trị `long` khi thành công** với **`IOException` khi thất bại**.
2. Giải thích **lỗi ở Reader** và **lỗi ở Writer** có thể xảy ra sau những lần đọc/ghi thành công, khiến nguồn/đích ở trạng thái không xác định hoàn toàn.
3. Phân biệt ký tự Java (`char`, UTF-16 code unit) với byte và Unicode code point; tránh suy luận sai số byte từ giá trị trả về.
4. Viết một ví dụ tái hiện lỗi đọc **sau khi 5 ký tự đã được ghi** và lỗi ghi **sau khi 3 ký tự được chấp nhận**, không dựa vào ổ cứng hoặc mạng thật.
5. Nhận biết vì sao `transferTo` **không rollback**, **không tự flush/close** và không trả tổng số ký tự tin cậy khi ném lỗi.
6. Chọn chiến lược an toàn: staging ra tệp tạm, chỉ công bố sau khi ghi/đóng thành công, hoặc dùng transaction/idempotency/acknowledgement khi ghi tới DB, dịch vụ hay endpoint.
7. Xây dựng test fault injection và checklist xử lý lỗi cho pipeline ký tự mà không giả định thông điệp exception hoặc trạng thái stream sau thất bại.

## 2. Hợp đồng API cần đọc trước khi viết mã

Chữ ký:

```java
public long transferTo(Writer out) throws IOException
```

Đây là phương thức của `java.io.Reader`; gọi ví dụ `reader.transferTo(writer)` để đọc **toàn bộ các ký tự còn lại** từ reader và ghi sang writer theo thứ tự đọc. Javadoc Java SE 25 khẳng định: **nếu trở về bình thường**, reader đã ở cuối dòng và kết quả `long` là số **ký tự** chuyển đi; phương thức **không đóng** reader hoặc writer. `Reader.transferTo` có mặt từ **Java 10**.

Ví dụ chỉ dùng bộ nhớ:

```java
try (var reader = new java.io.StringReader("Java");
     var writer = new java.io.StringWriter()) {
    long count = reader.transferTo(writer);
    System.out.println(count);             // 4
    System.out.println(writer.toString()); // Java
}
```

Cả input và output là các character streams; bản thân `transferTo` không thực hiện việc chỉ định charset, tạo tệp, commit transaction hay chuẩn hóa nội dung.

### Ma trận hành vi

| Tình huống | Hành vi có thể dựa vào | Điều **không** được suy ra |
| --- | --- | --- |
| Chuyển hoàn tất bình thường | Trả `long` số ký tự đã chuyển; reader ở EOF | Writer đã được flush/close, dữ liệu đã fsync lên đĩa hoặc bên nhận từ xa đã commit |
| `out == null` | Ném `NullPointerException` | Đây là I/O failure hay có kết quả đếm hợp lệ |
| Reader gặp `IOException` | Lỗi được truyền tới caller theo hợp đồng; có thể đã chuyển dữ liệu trước đó | Writer chưa nhận gì, hoặc Reader chắc chắn ở vị trí có thể retry |
| Writer gặp `IOException` | Lỗi được truyền tới caller nếu writer báo lỗi bằng exception | Việc ghi được thực hiện nguyên tử, writer không thể đã chấp nhận một phần buffer |
| Writer có bộ đệm | `transferTo` gọi API ghi ký tự của writer | Dữ liệu đã nằm trên đĩa trước khi flush/close |
| Reader/Writer bị đóng bất đồng bộ hoặc thread bị interrupt | Hành vi phụ thuộc triển khai cụ thể | Lúc nào cũng dừng ngay, rollback hoặc phát ra đúng một loại exception |
| Chuyển quá nhiều ký tự | Giá trị trả về bão hòa ở `Long.MAX_VALUE` theo Javadoc | Có thể dùng số trả về làm số byte hoặc độ dài code point |

### Đếm ký tự không phải đếm byte

`Reader` và `Writer` thao tác với **đơn vị ký tự `char` của Java**, về bản chất là đơn vị mã UTF-16. Ví dụ chuỗi `"A💡B"` có **4 `char`**: `A` (1), biểu tượng `💡` (2 surrogate code units), `B` (1), dù có **3 Unicode code points**. Khi mã hóa UTF-8, số byte lại khác. Do đó **đừng dùng `long transferred` làm kích thước tệp byte, progress của mạng theo byte hoặc vị trí resume trong file UTF-8**.

Khi dùng `Files.newBufferedReader` / `Files.newBufferedWriter`, hãy chỉ rõ `StandardCharsets.UTF_8` nếu đó là định dạng của dữ liệu. Mọi lỗi mã hóa/giải mã, flush hoặc đóng tài nguyên phải được xử lý như các bước có thể thất bại riêng; `transferTo` không thay thế chính sách charset.

## 3. Vấn đề chính: lỗi có thể đến **sau khi đã chuyển một phần**

Hợp đồng Javadoc `Reader.transferTo` nêu rằng khi lỗi I/O xảy ra trong lúc đọc hoặc ghi, lỗi **có thể xuất hiện sau khi một số ký tự đã được đọc hoặc đã được ghi**. Vì vậy Reader chưa chắc ở EOF, và một hoặc cả hai stream **có thể ở trạng thái không nhất quán**. Javadoc khuyến nghị đóng kịp thời cả hai stream khi xảy ra lỗi I/O.

Một cách hình dung:

```text
Reader nguồn                         Writer đích
    |                                   |
    |-- đọc "ABCD" -------------------> |-- nhận "ABCD" thành công
    |                                   |
    |-- đọc tiếp ---------------------> | 
    X IOException                        (vẫn đã chứa "ABCD")
    
=> transferTo NÉM exception, KHÔNG trả tổng ký tự.
=> Đích KHÔNG tự quay về trạng thái trước khi gọi.
```

Với lỗi ghi:

```text
Reader nguồn                         Writer đích
    |                                   |
    |-- đọc "HELLO!" ----------------> |-- chấp nhận "HEL"
    |                                   X IOException trong write(...)
    |
    | Reader có thể đã tiêu thụ        |
    | nhiều hơn những gì đích nhận.     |

=> Nguồn và đích có thể KHÔNG còn cùng một vị trí logic.
=> Không thể lấy "bao nhiêu ký tự đã ghi" từ exception chuẩn.
```

Đây **không phải** cam kết mỗi lỗi đều xảy ra sau khi đã chuyển ký tự; lỗi cũng có thể xảy ra ngay từ đầu. Điểm đúng cần ghi nhớ là **không có bảo đảm all-or-nothing**. Mã nghiệp vụ không được xem `IOException` là tín hiệu “chưa có tác động gì”.

### 3.1. Khi lỗi xảy ra trong Reader

Một lần `read(...)` có thể trả các ký tự, rồi ở lần đọc sau mới ném `IOException`. Các ký tự trước đó có thể đã đi qua Writer. Ví dụ: đọc được phần đầu của một tệp lớn rồi ổ đĩa lỗi, stream giải mã lỗi, kết nối bị ngắt hoặc thiết bị đầu vào hỏng. Không thể lấy một exception để chứng minh reader chưa đọc gì.

Trong ví dụ lab, ta tạo một Reader **cố ý trả `ABCDE` trước rồi ném lỗi**, giúp thấy Writer đã giữ `ABCDE` dù chuyển không thành công.

### 3.2. Khi lỗi xảy ra trong Writer

Writer có thể chấp nhận một phần dữ liệu trong một lần `write(char[],off,len)`, rồi báo lỗi. Với writer ghi tệp, có thể một số byte đã được gửi tới hệ điều hành; với writer qua socket, có thể bên nhận đã nhận một số đoạn; với Writer có buffer, dữ liệu thậm chí còn nằm trong bộ đệm ứng dụng.

Điều này quan trọng vì Reader **có thể đã đọc trước** một khối ký tự rồi mới gọi `writer.write`. Khi `write` ném lỗi, vị trí nguồn chưa chắc bằng số ký tự đích thực sự lưu được. Không lấy “reader đang ở đâu” làm offset retry đáng tin cậy nếu không có hợp đồng checkpoint riêng.

Trong lab, một Writer giả lập **chấp nhận đúng ba ký tự** của `HELLO!` rồi ném `IOException`. Việc đích giữ tiền tố `HEL` là một hành vi hợp lệ trong mô hình lỗi I/O.

### 3.3. Lỗi sau một lần gọi `write` không phải commit của Writer

`transferTo` không tự gọi `flush()` và `close()`. Với `BufferedWriter` hoặc writer có trạng thái nội bộ, `transferTo` trở về bình thường **chưa đồng nghĩa dữ liệu đã rời buffer**, chưa chắc hoàn tất mã hóa, ghi ra thiết bị hay nhận bởi một dịch vụ ở xa. `flush()/close()` là những bước cần xem xét và **cũng có thể ném `IOException`**.

Đối với tệp cần tính bền vững đặc biệt cao (ví dụ dữ liệu giao dịch), việc flush hoặc đóng Java Writer vẫn không tự tương đương với bảo đảm `fsync` bền vững trước sự cố mất điện. Mức độ cần bảo đảm phải được thiết kế theo hệ thống file, channel, giao thức và yêu cầu nghiệp vụ.

## 4. Tại sao không thể lấy số ký tự trả về khi thất bại?

Ví dụ dễ nhầm:

```java
long transferred = reader.transferTo(writer);
System.out.println(transferred);
```

Nếu `transferTo` ném `IOException`, phép gán cho `transferred` **không hoàn tất**; dòng in sẽ không chạy. Không tồn tại “giá trị trả về một phần” kèm theo exception trong hợp đồng này.

Nên viết theo hai nhánh có ý nghĩa khác nhau:

```java
try {
    long chars = reader.transferTo(writer);
    // Thành công ở bước transferTo; vẫn cần kiểm tra flush/close
    // và bước publish dữ liệu, nếu pipeline có các bước đó.
    System.out.println("chars transferred: " + chars);
} catch (java.io.IOException failure) {
    // Không suy ra số ký tự đã tới đích từ exception.
    // Đích có thể đã bị thay đổi và nguồn có thể không ở đầu.
    System.err.println("Transfer failed: " + failure);
    throw failure;
}
```

**Đây là đoạn minh họa trong một phương thức có `reader` và `writer` đã được khai báo**, không phải chương trình độc lập. Khi caller có trách nhiệm sở hữu reader/writer, nên dùng `try-with-resources` để tài nguyên được đóng kể cả lúc lỗi. Không viết handler tiếp tục giả vờ “thành công” chỉ vì một phần dữ liệu đã xuất hiện ở đích.

Một biến đếm tự viết trong vòng lặp `read/write` cũng **không tự giải quyết** bài toán này: nếu `Writer.write(...)` chấp nhận một phần rồi ném exception, mã sau `write` không chạy, và bạn không biết chính xác bao nhiêu ký tự thực sự đã tới đích trừ khi Writer/giao thức có cơ chế xác nhận riêng.

## 5. Lab Java: tái hiện thành công, lỗi đọc và lỗi ghi một phần

Mục tiêu của lab là kiểm tra hành vi **có thể tái hiện được**, không cần làm hỏng tệp thật hoặc ngắt mạng. Nó dùng các lớp `Reader` / `Writer` giả lập để chèn lỗi tại điểm đã biết.

### 5.1. Chuẩn bị

Dùng JDK **còn được nhà cung cấp hỗ trợ và cập nhật bản vá**, chẳng hạn một bản phân phối JDK 21 hoặc 25 LTS phù hợp môi trường. Phương thức chính `Reader.transferTo` được bổ sung từ Java 10 và vẫn có trên JDK hiện đại.

```bash
java -version
javac -version
```

Lưu mã sau vào tệp **`PartialTransferLab.java`**:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.util.Objects;

public class PartialTransferLab {
    /**
     * Trả toàn bộ "text" qua read(...), sau đó lỗi ở lần đọc
     * tiếp theo thay vì trả -1. Không override transferTo.
     */
    static final class FailAfterContentReader extends Reader {
        private final String text;
        private int pos;
        private boolean closed;

        FailAfterContentReader(String text) {
            this.text = text;
        }

        @Override
        public int read(char[] dst, int off, int len)
                throws IOException {
            Objects.checkFromIndexSize(off, len, dst.length);
            if (closed) {
                throw new IOException("closed");
            }
            if (len == 0) {
                return 0;
            }
            if (pos == text.length()) {
                throw new IOException("injected");
            }

            int n = Math.min(len, text.length() - pos);
            text.getChars(pos, pos + n, dst, off);
            pos += n;
            return n;
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    /**
     * Chỉ chấp nhận tối đa "limit" ký tự, có thể ghi được
     * một tiền tố của char[] rồi mới ném IOException.
     */
    static final class CappedWriter extends Writer {
        private final int limit;
        private final StringBuilder accepted = new StringBuilder();

        CappedWriter(int limit) {
            this.limit = limit;
        }

        @Override
        public void write(char[] chars, int off, int len)
                throws IOException {
            Objects.checkFromIndexSize(off, len, chars.length);
            int canWrite = Math.min(len,
                    Math.max(0, limit - accepted.length()));
            accepted.append(chars, off, canWrite);

            if (canWrite < len) {
                throw new IOException("injected");
            }
        }

        @Override public void flush() { }
        @Override public void close() { }

        String acceptedText() {
            return accepted.toString();
        }
    }

    /**
     * Theo dõi transferTo có tự flush/close Writer không.
     */
    static final class TrackingWriter extends Writer {
        final StringBuilder text = new StringBuilder();
        boolean flushed;
        boolean closed;

        @Override
        public void write(char[] chars, int off, int len) {
            text.append(chars, off, len);
        }

        @Override
        public void flush() {
            flushed = true;
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    public static void main(String[] args) throws IOException {
        // Bình thường: đếm UTF-16 char, không phải code point.
        try (var in = new StringReader("A\uD83D\uDCA1B");
             var out = new StringWriter()) {
            long count = in.transferTo(out);
            System.out.println(
                    "success UTF-16 chars: " + count);
            System.out.println(
                    "success text matches: "
                            + out.toString().equals(
                                    "A\uD83D\uDCA1B"));
        }

        try (var in = new StringReader("");
             var out = new StringWriter()) {
            System.out.println(
                    "empty chars: " + in.transferTo(out));
        }

        // Lỗi bên đọc sau khi Writer đã nhận "ABCDE".
        var readTarget = new StringWriter();
        try (var in = new FailAfterContentReader("ABCDE")) {
            in.transferTo(readTarget);
        } catch (IOException ex) {
            System.out.println(
                    "read failure: " + ex.getMessage());
        }
        System.out.println("read partial: " + readTarget);

        // Lỗi bên ghi sau khi Writer chấp nhận "HEL".
        var writeTarget = new CappedWriter(3);
        try (var in = new StringReader("HELLO!")) {
            in.transferTo(writeTarget);
        } catch (IOException ex) {
            System.out.println(
                    "write failure: " + ex.getMessage());
        }
        System.out.println(
                "write partial: " + writeTarget.acceptedText());

        // Bản thân transferTo không flush hoặc close Writer.
        var writer = new TrackingWriter();
        var input = new StringReader("Hi");
        long n = input.transferTo(writer);

        System.out.println("tracking chars: " + n);
        System.out.println(
                "transfer auto flush: " + writer.flushed);
        System.out.println(
                "transfer auto close: " + writer.closed);

        writer.write('!');
        System.out.println(
                "writer after transfer: " + writer.text);

        // Trong mã thật, tài nguyên cần được quản lý đúng owner.
        writer.close();
        input.close();
        readTarget.close();
        writeTarget.close();
    }
}
```

Biên dịch và chạy:

```bash
javac PartialTransferLab.java
java PartialTransferLab
```

### 5.2. Stdout dự kiến (xác định, không phụ thuộc mã hóa console)

```text
success UTF-16 chars: 4
success text matches: true
empty chars: 0
read failure: injected
read partial: ABCDE
write failure: injected
write partial: HEL
tracking chars: 2
transfer auto flush: false
transfer auto close: false
writer after transfer: Hi!
```

Bộ kiểm thử dùng chuỗi `"injected"` do **chính các lớp giả lập** ném ra, nên có thể in chính xác thông báo trong lab. Trong mã production, **không nên** phụ thuộc thông báo do hệ điều hành/JDK cung cấp để xác định loại lỗi.

### 5.3. Điều quan trọng trong output

1. **`success UTF-16 chars: 4`**: chuỗi có một code point ngoài BMP được biểu diễn bởi **hai `char`**; số 4 không phải số Unicode code points hay byte UTF-8.
2. **`success text matches: true`**: dữ liệu gốc và đích bằng nhau khi chuyển thành công; không cần in biểu tượng Unicode trực tiếp ra console.
3. **`empty chars: 0`**: reader không còn ký tự thì chuyển thành công 0 ký tự.
4. **`read failure: injected`** và **`read partial: ABCDE`**: một Reader có thể đọc/ghi được một phần trước lần `read` kế tiếp ném `IOException`. `transferTo` **không có giá trị `long` thành công** trong nhánh này.
5. **`write failure: injected`** và **`write partial: HEL`**: Writer giả lập nhận ba ký tự rồi báo lỗi trong lúc ghi; nó không rollback phần đã nhận. Không đoán Reader đã tiêu thụ bao nhiêu chỉ bằng kích thước `HEL`.
6. **`tracking chars: 2`**: trường hợp thành công chuyển hai `char` từ `Hi`. Hai cờ **`transfer auto flush/close: false`** xác nhận bản thân `transferTo` không gọi `flush` hoặc `close` của Writer trong lab.
7. **`writer after transfer: Hi!`**: Writer còn dùng được vì `transferTo` không tự đóng. Lệnh `close()` thủ công cuối chương trình minh họa trách nhiệm chủ sở hữu.

### 5.4. Vì sao các lỗi giả lập khác với lỗi thực tế?

Đối tượng `FailAfterContentReader` chủ động trả dữ liệu trước rồi báo lỗi, còn `CappedWriter` chủ động chấp nhận một tiền tố trước khi ném. Cách này **chứng minh khả năng xảy ra partial transfer** và luyện test dựa trên hợp đồng.

Trong ứng dụng thực tế, lỗi có thể xảy ra tại:
- Lần `Reader.read` đầu tiên (đích chưa được Writer ghi gì).
- Lần đọc sau khi đã chuyển một số khối.
- Lần `Writer.write` đầu tiên hoặc giữa một lần ghi.
- `Writer.flush` hoặc `Writer.close` sau khi `transferTo` đã hoàn tất.
- Đường truyền, đĩa, bộ giải mã hoặc bộ mã hóa qua Reader/Writer wrapper.

Không suy ra số ký tự vật lý đã được ghi ở đích từ độ dài tiền tố trong một mock nếu Writer thật có buffer, mã hóa hoặc phía nhận từ xa. Đó là lý do hệ thống cần cách **commit/recover** riêng cho từng loại đích.

## 6. Cách xử lý `IOException` bằng try-with-resources

### 6.1. Đóng tài nguyên khi lỗi

Một mẫu tối thiểu khi method **sở hữu** cả hai stream:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DirectTextCopy {
    public static long copyDirect(Path source, Path target)
            throws IOException {
        try (Reader in = Files.newBufferedReader(
                     source, StandardCharsets.UTF_8);
             Writer out = Files.newBufferedWriter(
                     target, StandardCharsets.UTF_8)) {
            return in.transferTo(out);
        }
    }
}
```

Đây là **class độc lập** nhưng chỉ minh họa quản lý tài nguyên, **không bảo đảm atomicity**. `Files.newBufferedWriter(target, UTF_8)` với tùy chọn mặc định có thể tạo/truncate tệp đích. Vì thế nếu `transferTo` hoặc `close` thất bại, tệp đích có thể **bị cắt cụt hoặc chỉ chứa một phần**. Không dùng mẫu này để ghi đè dữ liệu quan trọng nếu cần giữ nguyên phiên bản đích khi lỗi.

`try-with-resources` bảo đảm **cố gắng gọi `close`** cho các stream khi ra khỏi scope, kể cả lúc lỗi. Đối với Writer có buffer, `close` thường flush dữ liệu đệm rồi có thể ném `IOException`. Vì vậy file đích có thể thay đổi **trong quá trình đóng**, kể cả sau khi đã xảy ra một lỗi trước đó.

Nếu `transferTo` ném một exception và `close` cũng ném, Java lưu exception từ close dưới dạng **suppressed exception** của lỗi chính. Khi điều tra sự cố, ghi log cả exception chính và suppressed exceptions thay vì chỉ giữ message đầu tiên.

### 6.2. Ai mở thì người ấy chịu trách nhiệm đóng?

`transferTo` không đóng Reader/Writer. Nếu helper nhận Reader/Writer do caller quản lý, cần xác định **quyền sở hữu** trong API: helper sẽ đóng cả hai hay caller sẽ đóng? Không tự ý đóng Writer được dùng chung bởi nhiều thành phần.

Hợp đồng API của `transferTo` khuyến nghị **đóng kịp thời cả hai stream** sau lỗi I/O vì trạng thái có thể không nhất quán. Trong lớp ứng dụng, nếu helper không sở hữu chúng, hãy báo lỗi rõ để caller đóng/dispose và **không tiếp tục dùng stream lỗi như bình thường**.

### 6.3. Không che giấu exception

Mẫu nguy hiểm:

```java
try {
    reader.transferTo(writer);
} catch (IOException ex) {
    System.err.println("ignored");
}
// Sau đây ứng dụng vẫn công bố kết quả như thể thành công.
```

Đây là **đoạn minh họa sai**. Khi có lỗi, kết quả có thể chỉ gồm một tiền tố của dữ liệu. Nếu ứng dụng vẫn gửi thông báo thành công, dữ liệu sai có thể trở thành trạng thái chính thức và khó khôi phục.

Thay vì bỏ qua lỗi: phân loại failure, đánh dấu kết quả chưa hoàn thành, cleanup staging nếu có, giải phóng tài nguyên, rồi **trả lỗi hoặc kết quả thất bại có cấu trúc** để tầng trên quyết định có retry hay không. Chỉ khi chính sách nghiệp vụ chấp nhận partial result và có cách hiển thị/truy vết minh bạch mới được công bố dữ liệu một phần.

## 7. Chiến lược an toàn khi ghi vào **tệp quan trọng**

### 7.1. Vì sao ghi thẳng vào tệp đích dễ nguy hiểm?

Nếu dùng writer mở với `CREATE`/`TRUNCATE_EXISTING`, tệp đích có thể bị cắt cụt **ngay khi mở**, trước cả khi đọc ký tự đầu tiên. Trong lúc truyền, một phần dữ liệu được ghi dần. Lỗi ở giữa làm đích không còn chắc chắn là nội dung cũ lẫn nội dung mới hoàn chỉnh.

Mẫu khuyến nghị khi cần publish theo lần:

```text
Tệp nguồn → Reader
                |
                v
       ghi vào TỆP TẠM riêng
                |
           transferTo
                |
        đóng Writer thành công
                |
           xác minh nội dung
                |
         atomic move (nếu hỗ trợ)
                |
                v
       Tệp đích chính thức
```

Nếu lỗi xảy ra trước khi publish, chỉ tệp tạm có thể chứa phần dữ liệu thiếu; hãy đóng và xóa tệp tạm theo chính sách. Tệp đích chính thức không phải bị ghi đè dần từng ký tự bằng `transferTo`.

### 7.2. Ví dụ helper staging bằng JDK NIO

```java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;

public final class StagedTextCopy {
    /**
     * Ví dụ cho đích tệp mới; nếu đích đã tồn tại thì chính sách
     * ghi đè/phân quyền cần được quyết định rõ theo file system.
     */
    public static long copyAndPublish(Path source, Path target)
            throws IOException {
        Path destination = target.toAbsolutePath();
        Path directory = destination.getParent();
        Path temporary = Files.createTempFile(
                directory, ".text-transfer-", ".tmp");
        boolean published = false;

        try {
            long characters;
            try (Reader in = Files.newBufferedReader(
                         source, StandardCharsets.UTF_8);
                 Writer out = Files.newBufferedWriter(
                         temporary, StandardCharsets.UTF_8,
                         StandardOpenOption.WRITE,
                         StandardOpenOption.TRUNCATE_EXISTING)) {
                characters = in.transferTo(out);
            }

            // Chỉ chuyển tệp tạm sang đích sau khi transfer
            // và đóng Writer đều thành công.
            Files.move(temporary, destination,
                    StandardCopyOption.ATOMIC_MOVE);
            published = true;
            return characters;
        } finally {
            if (!published) {
                Files.deleteIfExists(temporary);
            }
        }
    }
}
```

**Giới hạn quan trọng:**

- Đây là class độc lập có thể biên dịch bằng JDK hiện đại, nhưng chỉ chạy thành công khi đường dẫn, quyền truy cập, charset và file system phù hợp. Không phải một transaction đa hệ thống.
- `ATOMIC_MOVE` yêu cầu file system/provider hỗ trợ. Nếu không hỗ trợ, `Files.move` ném `AtomicMoveNotSupportedException`. Đoạn code **không tự fallback** sang move thường vì yêu cầu nguyên tử hóa cần được chủ ứng dụng quyết định, không được âm thầm giảm bảo đảm.
- Theo Javadoc `Files.move`, nếu **tệp đích đã tồn tại** và yêu cầu `ATOMIC_MOVE`, việc thay thế hay báo lỗi có chi tiết **phụ thuộc implementation**. Không dùng đoạn mẫu như một chính sách “chắc chắn không overwrite”; phải giải quyết đích tồn tại và cạnh tranh giữa các writer ở tầng cao hơn.
- Tệp tạm đặt trong **thư mục đích** để tăng khả năng move cùng file store, nhưng điều đó không bảo đảm mọi hệ thống đều hỗ trợ atomic move.
- Sau `transferTo` trở về bình thường, `close` vẫn có thể ném `IOException`. Vì lệnh move nằm **sau** `try-with-resources`, trường hợp đóng thất bại không dẫn đến publish.
- Nếu có yêu cầu xác minh checksum, schema, độ dài byte, nội dung, chữ ký số hoặc durability khi mất điện, phải thêm quy trình thích hợp **trước/sau move**. `long characters` không phải byte checksum hoặc lệnh bảo đảm fsync.
- Cần xử lý tình huống riêng về symbolic links, đường dẫn đích trùng nguồn, phân quyền, giới hạn dung lượng và file system khi triển khai production.
- `finally` xóa tệp tạm khi chưa publish; một lỗi cleanup có thể phát sinh thêm `IOException`. Trong hệ thống quan trọng hãy log cả nguyên nhân ban đầu và lỗi cleanup, tránh làm mất thông tin gốc.

### 7.3. Với output nhỏ có thể stage trong bộ nhớ

Nếu dữ liệu chắc chắn nhỏ và chấp nhận chi phí bộ nhớ, có thể `transferTo` sang `StringWriter` (staging) trước, xác minh kết quả hoàn chỉnh rồi mới ghi vào đích thật. Điều này ngăn **lỗi đọc nguồn** làm thay đổi đích trong giai đoạn staging. Nhưng bước ghi cuối từ `StringWriter` sang Writer/tệp thật **vẫn có thể lỗi một phần**; StringWriter không biến đích bên ngoài thành transaction.

Không sử dụng `StringWriter` cho đầu vào kích thước không được kiểm soát vì nó lưu toàn bộ dữ liệu trong RAM. Tệp tạm hoặc pipeline có giới hạn dung lượng thường phù hợp hơn cho dữ liệu lớn.

## 8. Retry sau lỗi: vì sao **gọi lại** thường không an toàn?

Giả sử Writer đã nhận `"ABC"` của `"ABCDEFG"`, sau đó ném exception. Nếu chỉ gọi lại:

```java
reader.transferTo(writer); // Không phải cách retry an toàn sau lỗi.
```

thì có thể gặp các tình huống:

- Reader đã tiến xa hơn `ABC`: dữ liệu còn lại khi đọc tiếp **không bắt đầu đúng vị trí** cần ghi.
- Writer còn giữ `ABC` và lần retry append thêm tiền tố lại: nội dung có thể **bị nhân đôi**.
- Writer đã bị đóng hoặc ở trạng thái lỗi: thao tác tiếp theo có thể tiếp tục lỗi.
- Với Writer buffered, một phần ký tự chỉ nằm trong buffer, nên bạn **không biết trạng thái lưu bền vững** của đích.
- Nếu lỗi bắt nguồn từ kết nối/mạng, phía nhận có thể đã commit một phần hoặc toàn bộ yêu cầu trước khi client nhận được thông báo lỗi.

**Không thể suy ra retry offset từ `IOException` mặc định.** Javadoc không cung cấp trường “charactersSuccessfullyCommitted” trong exception của `Reader.transferTo`.

### 8.1. Retry từ đầu với nguồn/đích *mới*

Với tệp đầu vào bất biến có thể đọc lại, cách đơn giản hơn là **mở Reader mới từ đầu** và ghi vào **tệp staging mới/trống** cho mỗi lần thử; chỉ publish nếu toàn bộ các bước cần thiết thành công.

Điều kiện:
- Nguồn **thật sự có thể tái đọc** và không thay đổi giữa các lần; nếu nguồn là network response/queue, không giả định điều đó.
- Đích staging của mỗi lần retry phải độc lập; không append vào tệp tạm cũ chưa kiểm chứng.
- Quá trình publish phải có chính sách rõ về cập nhật/ghi đè và cạnh tranh.
- Retry nên có giới hạn số lần, backoff phù hợp và phân loại lỗi có thể phục hồi so với lỗi dữ liệu vĩnh viễn.

Không phải mọi `IOException` đều nên retry. Ví dụ dữ liệu không giải mã được theo charset yêu cầu có thể là lỗi dữ liệu, không phải transient. Lỗi phân quyền hay filesystem đầy cũng đòi hỏi xử lý nguyên nhân thay vì lặp vô hạn.

### 8.2. Muốn **resume từ giữa** cần giao thức riêng

Để tiếp tục từ một checkpoint thay vì chạy lại từ đầu, cần một cơ chế rõ ràng để xác định **đã ghi/được chấp nhận bền vững đến offset nào**. Ví dụ giao thức có sequence number, chunk ID, checksum, acknowledgement và khả năng truncate/seek hợp lệ.

`Reader.transferTo` không phơi ra các mốc checkpoint để bảo đảm resume. Cần thiết kế thêm:
- Nguồn có thể đọc lại theo offset xác định.
- Bên nhận xác nhận/commit từng chunk hoặc transaction.
- Phương pháp nhận biết chunk đã được áp dụng (idempotency/dedup).
- Mapping giữa offset **ký tự UTF-16** và offset **byte encoding** nếu dùng tệp/stream byte; hai offset không thể mặc định bằng nhau.
- Cách khôi phục sau crash/restart và cách xử lý ACK thất lạc.

Nếu không cần resume mà chỉ cần kết quả cuối cùng toàn vẹn, staging + publish theo lần thường đơn giản và ít sai sót hơn.

### 8.3. Khi Writer là đích DB, HTTP hoặc queue

Một Writer wrapper có thể gửi văn bản ra dịch vụ khác. Lúc `IOException`, phía nhận có thể đã nhận và xử lý một phần; nếu retry, có nguy cơ ghi trùng. Dùng transaction thực sự được backend hỗ trợ, idempotency key, message ID, checksum, acknowledged sequence, hoặc ghi ra đối tượng tạm rồi commit bằng API dịch vụ.

Đừng xem `long` được `transferTo` trả về là **xác nhận nghiệp vụ** rằng DB/network đã commit. Nó chỉ xác nhận phần ký tự đi qua quá trình transfer bình thường theo hợp đồng Reader/Writer.

## 9. `flush`, `close`, `PrintWriter` và các bẫy chẩn đoán lỗi

### 9.1. `transferTo` không flush

Nếu Writer được bọc bằng `BufferedWriter`, dữ liệu có thể nằm trong buffer sau `transferTo`. `flush` sẽ đẩy buffer xuống Writer bên dưới; `close` thường flush rồi giải phóng tài nguyên. Cả hai có thể báo lỗi.

Thứ tự báo hoàn tất nên là:

```text
transferTo thành công
  -> xử lý flush/close thành công theo hợp đồng của Writer
  -> xác minh / publish / commit thành công
  -> mới báo SUCCESS ở cấp nghiệp vụ
```

Đừng in “đã lưu file” chỉ vì `transferTo` trả một số ký tự, trong khi Writer chưa được đóng hoặc quá trình publish chưa hoàn tất.

### 9.2. `PrintWriter` có xử lý lỗi đặc biệt

`java.io.PrintWriter` có API **không ném I/O exceptions từ các phương thức ghi thông thường**, mà ghi nhận trạng thái lỗi để caller kiểm tra bằng `checkError()`. Nếu truyền một `PrintWriter` vào `reader.transferTo(...)`, đừng mặc định mọi lỗi I/O bên dưới đều sẽ làm `transferTo` ném exception.

```java
// Trong một phương thức, printWriter là PrintWriter do caller quản lý:
long count = reader.transferTo(printWriter);
if (printWriter.checkError()) {
    throw new java.io.IOException(
            "PrintWriter reported an output error");
}
```

`checkError()` thực hiện kiểm tra trạng thái (bao gồm flush nếu thích hợp). Khi thiết kế pipeline yêu cầu phát hiện lỗi I/O bằng exception, thường nên dùng `BufferedWriter`/`OutputStreamWriter` với chính sách charset và propagation rõ ràng thay vì dựa trên `PrintWriter` mà không kiểm tra lỗi. **Không phải mọi Writer đều truyền lỗi bên dưới theo cùng một cách**.

### 9.3. Exception chính và suppressed exception

Trong try-with-resources, nếu quá trình transfer ném `IOException`, và việc `close` của một stream cũng lỗi, exception từ `close` thường được gắn vào lỗi chính như suppressed. Tránh dùng một khối `finally` ném exception mới mà bỏ mất nguyên nhân đầu tiên.

Khi chẩn đoán, có thể log:
- Loại và thông điệp exception chính.
- Danh sách `getSuppressed()`.
- Metadata không nhạy cảm: loại reader/writer, tên tác vụ, ID của bản chuyển, nguồn/đích logic, trạng thái staging/publish.
- Số ký tự **đếm được một cách xác nhận** nếu ứng dụng có cơ chế tương ứng; nếu không, ghi **“không rõ”** thay vì con số phỏng đoán.

Không log toàn bộ nội dung đọc/ghi nếu dữ liệu có thể chứa bí mật, thông tin cá nhân hoặc payload lớn.

### 9.4. Có nên bắt mỗi `IOException` trong `transferTo`?

Nên xử lý tại ranh giới phù hợp: helper có trách nhiệm đóng và cleanup, tầng nghiệp vụ quyết định retry/report. Không “nuốt lỗi” ở tầng thấp. Ngoài `IOException` còn có `NullPointerException` khi `out` là null, hoặc lỗi lập trình/dữ liệu khác; đừng dùng `catch (Exception)` rồi báo chung “transfer thành công một phần” vì có thể che bug.

`Reader.transferTo` có thể **block vô hạn** tùy Reader/Writer. Nếu đọc/ghi mạng, timeout và cancellation phải được cấu hình ở các thành phần thích hợp và kiểm tra theo hợp đồng của chúng; chỉ interrupt thread không bảo đảm trạng thái khôi phục nhất quán.

## 10. Kiểm thử lỗi một phần bằng fault injection

Không cần làm hỏng tệp thật để xác nhận mã có xử lý partial transfer. Dùng **test doubles** như `FailAfterContentReader` và `CappedWriter` trong lab để tạo lỗi tại các mốc xác định.

### 10.1. Ma trận ca kiểm thử đề xuất

| Ca | Thiết lập | Điều cần xác nhận |
| --- | --- | --- |
| Tệp/chuỗi rỗng | Reader trống, Writer bình thường | Trả `0`, không phát sinh ký tự ngoài dự kiến |
| Chuyển thành công | Reader `"HELLO"`, Writer bình thường | Trả `5` và đích có nội dung `HELLO` |
| Lỗi đọc ngay lần đầu | Reader ném `IOException` trước dữ liệu | Handler báo thất bại, không giả định success |
| Lỗi đọc sau tiền tố | Reader trả `ABCDE`, rồi ném | Writer có thể đã nhận `ABCDE`; hàm vẫn ném |
| Lỗi ghi ở giữa buffer | Writer ghi tối đa 3 ký tự rồi ném | Writer có tiền tố `HEL`; không có `long` trả về |
| Lỗi trong `close` sau transfer thành công | Writer giả lập ném khi close | Toàn pipeline phải xem là thất bại ở bước hoàn tất |
| `Writer` có buffer | Flush trễ | Không khẳng định dữ liệu đã lưu trước flush/close |
| Đầu vào có ký tự ngoài BMP | Chuỗi `A💡B` | Trả 4 Java `char`, không phải 3 Unicode code points |
| Reader/Writer bên ngoài quản lý | Helper không sở hữu stream | Không tự đóng trong quá trình gọi; caller vẫn phải xử lý |
| Retry sau lỗi | Reader/Writer lỗi; mở mới từ đầu | Không append vào kết quả cũ chưa xác minh |
| `PrintWriter` nuốt lỗi | Writer bên dưới ném `IOException` | `checkError()` hoặc policy phát hiện lỗi ngoài giá trị `long` |
| Tệp staging | Lỗi khi đọc/ghi/đóng trước publish | Không publish tệp tạm chưa hoàn chỉnh |

### 10.2. Những assertion nên có

- `assertThrows(IOException.class, ... )` cho loại lỗi đã chèn; không khóa message của lỗi hệ thống thật.
- Với mock lưu ký tự, sau khi lỗi hãy kiểm tra **đích có thể đã bị thay đổi**, không chỉ exception được ném.
- Với workflow staging, kiểm tra **đích chính thức** không bị thay thế khi lỗi transfer/close trước publish; kiểm tra tệp tạm được xử lý đúng chính sách.
- Khi success, kiểm tra `count` và **nội dung kết quả**; không chỉ count.
- Nếu dùng một Reader/Writer cụ thể có hợp đồng vị trí riêng, có thể kiểm thử nó riêng; không suy từ kết quả ấy thành bảo đảm chung của mọi `Reader.transferTo`.
- Không sử dụng tệp cấu hình production làm fixture. Chạy trong thư mục test/temporary do test sở hữu và cleanup sau đó.

### 10.3. Có cần tự viết vòng lặp `read/write` thay cho `transferTo`?

`Reader.transferTo` tiện lợi khi yêu cầu “chuyển mọi ký tự còn lại” và không cần can thiệp từng chunk. Với nhu cầu:
- áp dụng giới hạn kích thước từng chunk,
- kiểm tra/biến đổi dữ liệu theo dòng,
- phát hiện checksum,
- ghi checkpoint và nhận ACK theo giao thức,
- kiểm soát cancellation/timeout theo cơ chế của tầng I/O,
- hoặc triển khai retry/resume có xác nhận,

một vòng lặp thủ công hoặc một API thích hợp khác có thể hợp lý hơn.

Tuy nhiên **vòng lặp thủ công không tự biến việc ghi thành atomic**. Một lần `writer.write(chars,off,len)` vẫn có thể nhận một phần rồi báo lỗi; bộ đếm “đã ghi” chỉ đáng tin khi chính giao thức/Writer xác nhận rõ phạm vi đã commit.

## 11. Những lỗi thường gặp và cách sửa

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Catch `IOException` rồi ghi “0 ký tự đã chuyển” | Đích có thể đã chứa một phần | Ghi trạng thái **UNKNOWN/PARTIAL POSSIBLE**, không bịa số |
| Giả định lỗi xảy ra trước khi Writer được gọi | Có thể đã có vài lần `write` thành công | Cleanup/đánh dấu kết quả staging chưa hoàn thành |
| Gọi lại `transferTo` trên cùng Reader và Writer sau lỗi | Bỏ sót hoặc ghi trùng nội dung | Mở nguồn mới và đích staging mới; retry theo chính sách |
| Dựa vào `reader.ready()` để xác nhận kết thúc | `ready` không phải phép thử EOF hay sự toàn vẹn dữ liệu | Dựa trên quá trình đọc đến EOF thành công và protocol/checksum phù hợp |
| Dùng giá trị `long` làm số byte UTF-8 | Đếm sai với ký tự nhiều byte/UTF-16 surrogate | Đếm byte ở tầng encoder/output stream nếu nghiệp vụ cần |
| Ghi thẳng `newBufferedWriter` lên tệp quan trọng | Có thể truncate/partial file khi lỗi | Stage tệp tạm, đóng/xác minh rồi publish |
| Báo success trước `close` | `close`/flush có thể gặp lỗi | Chỉ công bố sau các bước hoàn tất cần thiết |
| Chỉ đóng Reader khi lỗi | Writer cũng có thể ở trạng thái bất nhất | Cố gắng đóng kịp thời cả hai theo ownership |
| Tin `PrintWriter` luôn ném `IOException` | Nó có thể ghi nhận lỗi nội bộ | Kiểm tra `checkError()` hoặc dùng Writer truyền lỗi trực tiếp |
| Ghi retry vào Writer đang có tiền tố một phần | Duplicate payload hoặc sai offset | Reset staging từ đầu hoặc giao thức resume có ACK |
| Tin source EOF khi `IOException` | Reader có thể chưa EOF hoặc đọc trước | Đánh dấu vị trí chưa tin cậy; không dùng stream lỗi |
| Gộp lỗi transfer với lỗi close thành một chuỗi | Mất dấu vết nguyên nhân | Log exception chính và `getSuppressed()` |
| Tin `ATOMIC_MOVE` có sẵn trên mọi filesystem | Có thể ném `AtomicMoveNotSupportedException` | Kiểm tra khả năng hỗ trợ; chọn policy fallback có chủ đích |
| Tin `Reader.transferTo` tự rollback network/database | Đích ngoài có thể đã commit một phần | Transaction/idempotency/ACK theo hệ thống đích |

## 12. Bài tập vận dụng (có đáp án)

### Bài 1 — Kết quả trả về khi thành công

```java
var reader = new java.io.StringReader("abc");
var writer = new java.io.StringWriter();
long n = reader.transferTo(writer);
```

**Đáp án:** `n == 3`; `writer.toString().equals("abc")`. Reader đã tới EOF khi phương thức trả về bình thường. `transferTo` không tự close cả hai stream; caller cần quản lý tài nguyên.

### Bài 2 — Lỗi sau khi ghi tiền tố

Một custom Reader trả `"OK"`, sau đó ném `IOException` ở lần `read` tiếp theo. Đích có thể chứa gì?

**Đáp án:** Có thể đã có `"OK"`. `transferTo` ném lỗi nên không trả kết quả `long`. Không được coi Writer chắc chắn trống hoặc đã rollback. Tại bước xử lý lỗi, kết quả chưa hoàn tất và không được công bố như một bản dữ liệu đầy đủ.

### Bài 3 — Writer nhận một phần char array

Writer nhận ba ký tự đầu của `"HELLO!"`, sau đó ném `IOException`. Có thể retry từ ký tự thứ tư bằng cách tiếp tục cùng Reader không?

**Đáp án:** Không an toàn theo hợp đồng chung. Reader có thể đã tiêu thụ cả buffer `"HELLO!"` trước khi Writer báo lỗi. Nếu cần retry, hãy dùng nguồn có thể tái đọc và một đích staging mới hoặc một giao thức resume có xác nhận offset.

### Bài 4 — Đếm đơn vị ký tự

`"A💡B"` có bao nhiêu đơn vị `char` được chuyển từ `StringReader` qua `transferTo` khi không có lỗi?

**Đáp án:** `4`. Đây là số UTF-16 code units (A=1, biểu tượng=2, B=1), không phải số code points hay byte UTF-8. `String.codePointCount(...)` và `getBytes(UTF_8).length` có ý nghĩa khác.

### Bài 5 — Bẫy `try-with-resources`

Mã gọi `reader.transferTo(writer)` thành công, nhưng `writer.close()` tiếp tục ném `IOException`. Đã được phép báo “ghi tệp thành công” chưa?

**Đáp án:** Chưa. `try-with-resources` có thể truyền lỗi từ close. Phải phân biệt hoàn tất copy ký tự với hoàn tất ghi/publish dữ liệu. Nếu sử dụng staging, chưa move tệp tạm khi close thất bại.

### Bài 6 — Bản ghi partial trong tệp đích

Ứng dụng mở tệp hiện có bằng `Files.newBufferedWriter(path, UTF_8)` rồi thực hiện `transferTo`, sau đó lỗi. Có giữ nguyên nội dung trước đó được không?

**Đáp án:** Không. Tùy open options, tệp có thể bị truncate lúc mở, và dữ liệu mới có thể đã ghi một phần. Nếu yêu cầu giữ bản cũ tới lúc bản mới hoàn chỉnh, cần staging + publish hoặc giao dịch được file system/hệ thống hỗ trợ.

### Bài 7 — Có nên chuyển sang vòng lặp thủ công?

Bạn thay `transferTo` bằng vòng lặp: gọi `read`, sau đó `writer.write` và chỉ tăng biến đếm sau khi write trả về. Điều đó đã bảo đảm biết mọi ký tự ghi thành công trong ca lỗi chưa?

**Đáp án:** Chưa. Nếu `writer.write` ghi một phần rồi ném, biến đếm chưa được tăng nhưng đích đã thay đổi. Cần cơ chế writer/protocol xác nhận phạm vi commit hoặc công bố theo staging; vòng lặp chỉ cung cấp điểm can thiệp chi tiết hơn.

### Bài 8 — `PrintWriter` và phát hiện I/O error

Vì sao `reader.transferTo(printWriter)` có thể trở về bình thường dù writer bên dưới gặp lỗi?

**Đáp án:** `PrintWriter` có thể **ghi nhận trạng thái lỗi thay vì ném IOException** từ các phương thức ghi thông thường. Caller cần kiểm tra `printWriter.checkError()`, hoặc chọn Writer truyền lỗi theo exception khi muốn dùng `try/catch(IOException)` làm cơ chế phát hiện chính.

### Bài 9 — Xử lý lỗi đọc sau khi gửi tới dịch vụ

Một Writer gửi nội dung tới một dịch vụ từ xa. Khi client nhận `IOException`, có nên gửi lại toàn bộ ngay mà không có ID?

**Đáp án:** Chưa chắc. Dịch vụ có thể đã nhận/commit một phần hoặc toàn bộ nhưng client không nhận được xác nhận. Phải dùng idempotency key, transaction/commit protocol hoặc xác nhận theo chunk phù hợp. `transferTo` không cung cấp bảo đảm đúng-một-lần.

### Bài 10 — `Reader.transferTo` có đóng tài nguyên không?

Vì sao lab có thể `writer.write('!')` sau khi `transferTo` hoàn tất?

**Đáp án:** `transferTo` không tự đóng Reader hay Writer; Writer vẫn mở trong lab. Chủ sở hữu vẫn phải đóng tài nguyên. Nếu có lỗi, Javadoc đặc biệt khuyến nghị đóng kịp thời cả hai stream vì trạng thái có thể không nhất quán.

### Bài 11 — Đích atomic nhưng file system không hỗ trợ

Một pipeline chỉ cho phép publish nếu việc rename tệp tạm là atomic. `Files.move(temp, dest, ATOMIC_MOVE)` ném `AtomicMoveNotSupportedException`. Nên tự đổi sang move thường không?

**Đáp án:** Không nếu yêu cầu nghiệp vụ bắt buộc tính atomic. Hãy coi publish thất bại, cleanup/giữ staging theo chính sách, báo lỗi vận hành. Chỉ dùng fallback không atomic khi hợp đồng đã cho phép và đánh giá được rủi ro. Nếu dest đã tồn tại, cần thêm policy xử lý phụ thuộc file system.

### Bài 12 — Viết test assertion đúng trọng tâm

Một test chỉ `assertThrows(IOException.class, () -> reader.transferTo(writer))` đã đủ để xác nhận “không bị chuyển một phần” chưa?

**Đáp án:** Không. Nó chỉ xác nhận exception. Cần test kiểm tra trạng thái Writer đích sau lỗi, và nếu yêu cầu atomic publish thì kiểm tra **đích chính thức** chưa bị thay đổi trước khi publish. Test đầu vào sau lỗi cũng không nên mặc định Reader có thể tiếp tục từ một offset xác định.

## 13. Checklist code review cho chuyển văn bản

- [ ] Dùng `Reader.transferTo` khi thực sự cần chuyển toàn bộ ký tự còn lại từ Reader tới Writer.
- [ ] Ghi rõ `Charset` nếu Reader/Writer chuyển đổi qua byte streams.
- [ ] Phân biệt số `char` trả về với byte, Unicode code points và số đơn vị nghiệp vụ.
- [ ] Không xử lý `IOException` như “chưa ghi gì”; coi partial transfer là khả năng có thật.
- [ ] Không lấy `long transferred` từ lời gọi thất bại; không bịa số “đã ghi” từ exception.
- [ ] Không retry ngay trên cùng Reader/Writer không được bảo đảm trạng thái sau lỗi.
- [ ] Xác định **ai sở hữu tài nguyên** và trách nhiệm close khi thành công/lỗi.
- [ ] Tính đến lỗi `flush/close` sau khi `transferTo` đã hoàn tất.
- [ ] Phân biệt Reader fail, Writer fail, lỗi mã hóa và lỗi publish trong log/metrics.
- [ ] Đích quan trọng được ghi theo staging hoặc transaction thực sự, không cập nhật trực tiếp rồi kỳ vọng rollback.
- [ ] Nếu cần resume, có checkpoint, byte/char mapping, ACK/idempotency rõ ràng.
- [ ] Khi dùng `PrintWriter`, kiểm tra `checkError()`.
- [ ] Không phụ thuộc thông điệp exception hoặc vị trí stream sau lỗi.
- [ ] Với file system, chỉ yêu cầu `ATOMIC_MOVE` khi đã xác định policy nếu không hỗ trợ hoặc đích đã tồn tại.
- [ ] Có fault-injection tests cho lỗi ở đầu/giữa/cuối, lỗi khi close và cleanup staging.
- [ ] Chạy `PartialTransferLab.java`, đối chiếu đúng **11 dòng stdout**.

## 14. Ghi nhớ

**`Reader.transferTo(Writer)` là thao tác chuyển dòng ký tự, không phải transaction.** Nếu xảy ra `IOException` khi đọc hoặc ghi, một số ký tự có thể đã đi qua Writer; Reader/Writer có thể không còn ở trạng thái nhất quán và phương thức không trả số ký tự đáng tin của lần chuyển thất bại. `transferTo` cũng không tự flush hoặc close. Vì vậy hãy xem kết quả là **chưa hoàn thành**, đóng/cleanup tài nguyên theo ownership và chỉ công bố sau khi toàn bộ quy trình ghi, đóng, kiểm tra và commit thích hợp đã thành công.

Khi thao tác được thiết kế đúng, có thể dùng `transferTo` thuận tiện cho việc chuyển văn bản trên các JDK hiện đại, đồng thời kiểm soát riêng failure semantics, retry và tính toàn vẹn của dữ liệu.

## Tài liệu chính thức

- [Oracle Java SE 25 — Reader.transferTo(Writer)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer)): mô tả rõ partial transfer, `IOException`, số ký tự trả về, không close, khuyến nghị đóng cả hai stream sau lỗi. **Since: 10**.
- [Oracle Java SE 25 — Writer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Writer.html): `write`, `flush`, `close` và ngoại lệ I/O.
- [Oracle Java SE 25 — BufferedWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedWriter.html): buffering, `flush` và `close` có thể phát sinh `IOException`.
- [Oracle Java SE 25 — Files](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `newBufferedReader`, `newBufferedWriter`, `move` và `ATOMIC_MOVE`.
- [Oracle Java SE 25 — StandardCopyOption](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/StandardCopyOption.html): ý nghĩa của `ATOMIC_MOVE`.
- [Oracle Java SE 25 — PrintWriter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PrintWriter.html): xử lý I/O error và `checkError()`.
- [Oracle Java SE 25 — Throwable.getSuppressed()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): truy vết ngoại lệ thứ cấp trong try-with-resources.
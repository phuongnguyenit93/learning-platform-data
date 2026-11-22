# checkError() và các lỗi I/O không được ném trực tiếp trong Java

Trong Java I/O, phần lớn luồng ghi có thể báo thất bại bằng `IOException`. Tuy nhiên, hai lớp chuyên in và định dạng đầu ra là **`java.io.PrintStream`** và **`java.io.PrintWriter`** có cách báo lỗi khác: các thao tác ghi thông thường **không ném `IOException` trực tiếp** cho người gọi, mà ghi nhận lỗi vào trạng thái nội bộ. Phương thức **`checkError()`** cho phép kiểm tra trạng thái đó.

Điều này đặc biệt quan trọng khi ghi log, xuất báo cáo, tạo văn bản định dạng hoặc in ra console. Việc `print()`, `println()` hoặc `printf()` chạy xong mà không xuất hiện `IOException` **không đồng nghĩa dữ liệu đã được ghi thành công**.

Bài học nằm trong chủ đề **Console và định dạng** của Java Core I/O; trọng tâm là cách nhận biết, giải thích và xử lý lỗi đối với các API có cơ chế “giữ lỗi trong cờ trạng thái”.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt cách báo lỗi của `PrintStream`, `PrintWriter` so với `OutputStream` và `Writer` thông thường.
- Nêu đúng hợp đồng `checkError()`, bao gồm việc kiểm tra có thể **flush** đầu ra.
- Hiểu vì sao `print()`, `println()`, `printf()` chạy không ném `IOException` vẫn có thể mất dữ liệu.
- Sử dụng `checkError()` tại điểm thích hợp và biết rằng boolean này **không cho biết nguyên nhân chi tiết**.
- Phân biệt `autoFlush` của `PrintStream` với `PrintWriter` và nhận diện các ngoại lệ **không phải** lỗi I/O vẫn có thể được ném.
- Viết chương trình Java 17+ tái hiện lỗi ghi một cách tất định, không phụ thuộc ổ đĩa, mạng hay terminal thực tế.
- Chọn API cấp thấp có `throws IOException` khi nghiệp vụ cần quản lý lỗi và nguyên nhân cụ thể.

## 2. Vì sao hai lớp in định dạng xử lý lỗi đặc biệt?

### `PrintStream`

`java.io.PrintStream` kế thừa `FilterOutputStream` và được dùng để in biểu diễn văn bản của nhiều kiểu giá trị:

~~~java
stream.print("name=");
stream.println("Java");
stream.printf("count=%d%n", 3);
~~~

`System.out` và `System.err` thông thường là hai `PrintStream` được JVM cung cấp. `PrintStream` cũng có các thao tác ghi byte, nhưng `print`/`println`/`printf` tập trung vào xuất ký tự đã được mã hóa xuống đầu ra byte.

Theo hợp đồng `PrintStream` trong Java 17, **các thao tác ghi không truyền `IOException` thông thường cho bên gọi**; khi luồng nền báo lỗi I/O, lớp in ghi nhớ lỗi vào một cờ để `checkError()` kiểm tra. Ngoại lệ đáng chú ý là `InterruptedIOException` từ luồng nền: `PrintStream` xử lý bằng cách đặt trạng thái ngắt của thread thay vì đơn giản ghi nhận như lỗi I/O thông thường.

### `PrintWriter`

`java.io.PrintWriter` kế thừa `Writer`, cung cấp các thao tác in văn bản tương tự `PrintStream`:

~~~java
writer.print("name=");
writer.println("Java");
writer.printf("count=%d%n", 3);
~~~

`PrintWriter` làm việc với **ký tự**; bản thân nó không có phương thức ghi byte thô giống `OutputStream`. Các phương thức của `PrintWriter` không truyền `IOException` do ghi/flush/close ra ngoài theo cách mà `Writer` thông thường có thể làm; muốn phát hiện tình trạng lỗi phải kiểm tra `checkError()`.

**Phân biệt quan trọng:** việc khởi tạo `PrintStream`/`PrintWriter` bằng constructor mở file vẫn **có thể ném `IOException`** (hoặc ngoại lệ checked cụ thể) khi không mở/tạo được file. “Không ném IOException” ở đây chủ yếu nói đến cơ chế báo lỗi **khi đã có đối tượng in và thực hiện thao tác I/O**, không phải miễn mọi lỗi ở mọi giai đoạn.

## 3. Bảng so sánh các API ghi

| Kiểu | Đơn vị làm việc | Lỗi I/O lúc ghi/flush/close | Cách người gọi nhận biết |
| --- | --- | --- | --- |
| `OutputStream`, ví dụ `FileOutputStream` | Byte | Phương thức thường khai báo `throws IOException` | Bắt/lan truyền ngoại lệ |
| `Writer`, ví dụ `BufferedWriter` | Ký tự | Phương thức thường khai báo `throws IOException` | Bắt/lan truyền ngoại lệ |
| `PrintStream` | In định dạng, ghi byte | Không truyền `IOException` I/O thông thường từ thao tác in/ghi | `checkError()`; lưu ý trạng thái ngắt riêng |
| `PrintWriter` | In định dạng, ghi ký tự | Không truyền `IOException` I/O thông thường từ thao tác in/ghi | `checkError()` |
| `Formatter` | Định dạng theo mẫu | Lỗi I/O với `Appendable` có thể được ghi nhận thay vì ném trực tiếp | `ioException()` |

Không phải mọi thứ mang tên “print” đều có cùng hợp đồng. Khi chọn cách xử lý lỗi, hãy nhìn vào **kiểu API cụ thể** và trách nhiệm của tầng gọi.

## 4. `checkError()` hoạt động thế nào?

Hai lớp đều có:

~~~java
boolean failed = output.checkError();
~~~

Với `PrintStream`, `checkError()` **flush đầu ra nếu còn mở**, sau đó kiểm tra trạng thái lỗi. Với `PrintWriter`, `checkError()` cũng **flush nếu writer chưa đóng** rồi kiểm tra trạng thái lỗi. Do đó lời gọi này **không đơn thuần là đọc một biến boolean**; nó có thể kích hoạt một thao tác I/O còn đang được hoãn.

| Kết quả | Có thể kết luận | Không được kết luận |
| --- | --- | --- |
| `true` | Lớp in đã ghi nhận một tình trạng lỗi theo cơ chế của nó | Không biết chắc lỗi gốc là gì, bao nhiêu byte/ký tự đã ra đích hoặc có thể tiếp tục an toàn |
| `false` | Tại thời điểm kiểm tra không có lỗi được ghi nhận trong trạng thái mà API quan sát được | Không chứng minh dữ liệu đã ghi bền vững xuống đĩa, tới máy nhận, hay sẽ không lỗi sau này |

**Ví dụ thường gặp:** `print("abc")` chỉ đưa dữ liệu vào buffer; `checkError()` có thể dẫn đến flush, và chính flush làm tầng dưới phát sinh `IOException`. Khi đó `checkError()` trả `true`. Nếu chưa hề kiểm tra, chương trình có thể tưởng thao tác in đã thành công.

### Cờ lỗi thường “dính” sau khi đã được đặt

Cả hai lớp đều cung cấp `protected setError()` và `protected clearError()`. Khi cờ đã thành `true`, các lần `checkError()` sau vẫn có thể trả `true` cho đến khi cờ được xóa bằng cơ chế nội bộ/phân lớp phù hợp, kể cả khi một thao tác về sau không gặp lỗi mới.

**Không có API public để lấy hoặc reset toàn bộ lỗi một cách đáng tin cậy** trên một đối tượng `PrintStream`/`PrintWriter` thông thường. `clearError()` là `protected`, không phải lời khuyên để caller tự “phớt lờ lỗi rồi tiếp tục”. Nếu đầu ra đã hỏng, thường phải điều tra, thay thế tài nguyên hoặc báo thất bại ở tầng nghiệp vụ.

Đặc biệt, `checkError()` không trả về `IOException` gốc, stack trace hay đường dẫn file lỗi. Nếu cần giữ nguyên nguyên nhân, dùng `Writer`/`OutputStream` thích hợp hoặc tạo lớp giám sát riêng khi thiết kế API.

## 5. Ví dụ Java 17+ chạy được: `PrintStream` nuốt lỗi ghi I/O

Ta có thể tạo `OutputStream` giả lập: bất cứ lần ghi nào cũng ném `IOException`. Dùng nó làm đích của `PrintStream` sẽ cho kết quả ổn định, không cần làm hỏng file thật.

Tạo **`PrintStreamErrorDemo.java`**:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public class PrintStreamErrorDemo {
    static final class BrokenOutputStream extends OutputStream {
        @Override
        public void write(int value) throws IOException {
            throw new IOException("simulated disk failure");
        }
    }

    public static void main(String[] args) {
        try (PrintStream out = new PrintStream(
                new BrokenOutputStream(), true, StandardCharsets.UTF_8)) {

            out.println("record-1");

            System.out.println("afterPrintln=continued");
            System.out.println("checkError=" + out.checkError());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PrintStreamErrorDemo.java
java PrintStreamErrorDemo
~~~

**Stdout chính xác:**

~~~text
afterPrintln=continued
checkError=true
~~~

Vì sao?

1. `BrokenOutputStream.write(int)` ném `IOException` mỗi khi có thao tác ghi thực tế.
2. `PrintStream.println` thử ghi xuống stream bên dưới; khi gặp lỗi I/O thông thường, `PrintStream` ghi nhận lỗi thay vì trả ngoại lệ checked lên `main`.
3. Dòng `afterPrintln=continued` chứng minh **luồng điều khiển tiếp tục**.
4. `checkError()` trả `true` vì cờ lỗi đã được bật.
5. `try-with-resources` vẫn đóng tài nguyên in, nhưng bản thân `close()` của `PrintStream` cũng không truyền `IOException` I/O thông thường ra ngoài.

Đây là ví dụ minh họa việc **dữ liệu ghi có thể thất bại mà chương trình vẫn tiếp tục**. Nó không chứng minh ghi vào console hay file luôn thất bại; việc tạo một nguồn hỏng làm trường hợp lỗi tái hiện được.

## 6. Ví dụ Java 17+ chạy được: `PrintWriter` cũng cần `checkError()`

`PrintWriter` dùng `Writer` bên dưới. Một writer có thể ném `IOException` khi được yêu cầu ghi, nhưng `PrintWriter` không truyền lỗi đó ra như `BufferedWriter` thông thường.

Tạo **`PrintWriterErrorDemo.java`**:

~~~java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.Writer;

public class PrintWriterErrorDemo {
    static final class BrokenWriter extends Writer {
        @Override
        public void write(char[] chars, int offset, int length)
                throws IOException {
            throw new IOException("simulated writer failure");
        }

        @Override
        public void flush() {
            // Không có buffer bên dưới.
        }

        @Override
        public void close() {
            // Không có tài nguyên thực để đóng.
        }
    }

    public static void main(String[] args) {
        try (PrintWriter out = new PrintWriter(new BrokenWriter(), true)) {
            out.println("record-2");

            System.out.println("afterPrintln=continued");
            System.out.println("checkError=" + out.checkError());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PrintWriterErrorDemo.java
java PrintWriterErrorDemo
~~~

**Stdout chính xác:**

~~~text
afterPrintln=continued
checkError=true
~~~

`BrokenWriter` cố tình lỗi trên thao tác ghi mảng ký tự. `PrintWriter` nhận lỗi từ writer bên dưới và đánh dấu trạng thái lỗi nội bộ. `println()` trở về như một thao tác thông thường; `checkError()` mới chỉ ra đã xảy ra vấn đề.

**Điểm dễ nhầm:** nếu bạn gọi trực tiếp `BrokenWriter.write(...)`, người gọi phải xử lý `IOException`. Nhưng khi gọi qua `PrintWriter`, lỗi I/O có thể bị chuyển thành cờ thay vì được ném.

## 7. So sánh với `BufferedWriter` khi muốn biết lỗi gốc

Trong tác vụ cần phản ứng nghiêm ngặt, chẳng hạn ghi báo cáo bắt buộc đầy đủ, ghi file cấu hình hoặc xuất dữ liệu mà lỗi ghi phải làm thao tác nghiệp vụ thất bại, `BufferedWriter` hoặc `OutputStream` có thể phù hợp hơn vì không cố ý giấu nguyên nhân I/O.

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.Writer;

public final class StrictWrite {
    private StrictWrite() {}

    public static void writeRequiredRecord(
            Writer destination, String record) throws IOException {
        BufferedWriter buffered = new BufferedWriter(destination);
        buffered.write(record);
        buffered.newLine();
        buffered.flush();
    }
}
~~~

Lớp có thể biên dịch nhưng không có `main`. Nó không đóng `destination` vì ownership vẫn thuộc bên gọi; tuy nhiên cần bảo đảm hàm hoàn tất `flush()` và chính sách đóng ở caller. `BufferedWriter` sẽ ném hoặc lan truyền `IOException` nếu tầng dưới báo lỗi, giúp caller có nguyên nhân cụ thể để xử lý/log và báo thất bại.

Trong thực tế, nếu bạn là người **mở file**, có thể bọc việc mở writer bằng `try-with-resources`:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReportWriter {
    private ReportWriter() {}

    public static void save(Path target, String report) throws IOException {
        try (BufferedWriter writer =
                     Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
            writer.write(report);
            writer.newLine();
        }
    }
}
~~~

Đây là lớp không có `main`. `Files.newBufferedWriter` có thể tạo file mới hoặc truncate file đích theo mặc định; caller phải chọn đường dẫn/chiến lược cập nhật an toàn. Nếu ghi hoặc đóng gặp lỗi I/O, thao tác có thể ném `IOException` ra ngoài thay vì chỉ đặt cờ. Với yêu cầu ghi nguyên tử, cần có thiết kế file tạm và thay thế file đích sau khi xác minh.

**Lưu ý:** việc `flush()` hoặc `close()` kết thúc thành công vẫn chưa bảo đảm dữ liệu đã được đồng bộ bền vững xuống thiết bị lưu trữ. `checkError() == false` còn là bằng chứng yếu hơn; nó chỉ phản ánh trạng thái báo lỗi được lớp in biết đến.

## 8. `autoFlush` và vì sao hai lớp không giống nhau

Cả `PrintStream` và `PrintWriter` đều có constructor nhận cờ `autoFlush`, nhưng các sự kiện kích hoạt flush khác nhau.

### `PrintStream` với `autoFlush=true`

Theo tài liệu Java 17, tự flush có thể xảy ra khi:

- Ghi một **mảng byte**.
- Gọi một phương thức `println(...)`.
- Ghi một ký tự hoặc byte newline `'\n'`.

`PrintStream` làm việc với byte dưới lớp mã hóa, nên hợp đồng tự flush này **không giống** hành vi của `PrintWriter`.

### `PrintWriter` với `autoFlush=true`

Tự flush xảy ra khi gọi:

- `println(...)`
- `printf(...)`
- `format(...)`

**Không có bảo đảm autoFlush chỉ vì bạn tự ghi ký tự `'\n'` bằng `write('\n')`** hoặc chỉ gọi `print(...)` không có newline. Ngay cả khi `autoFlush=false`, `checkError()` vẫn có thể flush nếu writer còn mở.

| Hành động | `PrintStream(autoFlush=true)` | `PrintWriter(autoFlush=true)` |
| --- | --- | --- |
| `println("x")` | Tự flush | Tự flush |
| `write('\n')` | Tự flush theo hợp đồng `PrintStream` | Không có autoFlush theo chỉ sự kiện này |
| `print("x")` không newline | Không suy ra luôn flush | Không suy ra luôn flush |
| `checkError()` khi chưa đóng | Flush để kiểm tra lỗi | Flush để kiểm tra lỗi |

### Demo độc lập: khác nhau ở `write('\n')`

Tạo file **`AutoFlushDifferenceDemo.java`**:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;

public class AutoFlushDifferenceDemo {
    static final class CountingOutputStream extends OutputStream {
        int flushes;

        @Override
        public void write(int value) {
            // Cố ý bỏ dữ liệu để chỉ đếm flush.
        }

        @Override
        public void flush() {
            flushes++;
        }
    }

    static final class CountingWriter extends StringWriter {
        int flushes;

        @Override
        public void flush() {
            flushes++;
        }
    }

    public static void main(String[] args) throws IOException {
        CountingOutputStream byteTarget = new CountingOutputStream();
        try (PrintStream out = new PrintStream(
                byteTarget, true, StandardCharsets.UTF_8)) {
            out.write('\n');
            System.out.println("streamFlushed=" + (byteTarget.flushes > 0));
        }

        CountingWriter charTarget = new CountingWriter();
        try (PrintWriter out = new PrintWriter(charTarget, true)) {
            out.write('\n');
            System.out.println("writerFlushedAfterWrite="
                    + (charTarget.flushes > 0));

            out.println("done");
            System.out.println("writerFlushedAfterPrintln="
                    + (charTarget.flushes > 0));
        }
    }
}
~~~

Chạy Java 17+:

~~~bash
javac AutoFlushDifferenceDemo.java
java AutoFlushDifferenceDemo
~~~

Stdout:

~~~text
streamFlushed=true
writerFlushedAfterWrite=false
writerFlushedAfterPrintln=true
~~~

Bộ đếm chỉ được đọc **trước khi đóng các stream**, nên kết quả không bị ảnh hưởng bởi `close()`. Không khẳng định số lần flush chính xác của `PrintStream`, vì một phương thức có thể gọi flush nhiều hơn một lần tùy cách triển khai; ví dụ chỉ kiểm tra có ít nhất một lần.

**Hiệu năng:** `autoFlush=true` có thể khiến hệ thống chuyển dữ liệu xuống tầng dưới thường xuyên hơn, hữu ích cho phản hồi tương tác nhưng có chi phí khi ghi nhiều mục nhỏ. `autoFlush=false` thường phù hợp khi đợi đến cuối một đợt và chủ động flush. Dù theo cách nào, nếu tính chính xác quan trọng, vẫn cần kiểm tra kết quả ghi chứ không chỉ dựa vào việc method đã trả về.

## 9. Mẫu xử lý lỗi ở ranh giới tác vụ

Giả sử bạn buộc phải dùng `PrintWriter` vì đang sử dụng các phương thức in định dạng. Một chiến lược tối thiểu là:

~~~java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.Writer;

public final class CheckedPrintTask {
    private CheckedPrintTask() {}

    public static void writeRecord(
            Writer sink, String name, int quantity) throws IOException {
        PrintWriter printer = new PrintWriter(sink, false);

        printer.printf("item=%s, quantity=%d%n", name, quantity);

        if (printer.checkError()) {
            throw new IOException("Formatted output failed");
        }
    }
}
~~~

Lớp có thể biên dịch; caller cấp `Writer` và quản lý lúc đóng nó. `checkError()` yêu cầu flush trước khi trả trạng thái, nên lỗi ở tầng dưới vào thời điểm flush có cơ hội được phát hiện.

Nhưng cách này có các giới hạn:

1. **Không giữ `IOException` gốc:** bạn chỉ có boolean để tạo ngoại lệ mô tả chung.
2. **Không phân biệt ghi một phần:** có thể đã ghi một phần dữ liệu trước khi báo lỗi.
3. **Không thay thế kiểm tra lỗi lúc đóng đích thực sự:** nếu caller đóng `sink` sau đó mới xảy ra lỗi, cần chính sách báo lỗi của `sink` và cách sở hữu tài nguyên rõ ràng.
4. **Không chắc lỗi xảy ra chính xác ở bản ghi đang viết:** trạng thái lỗi từ thao tác trước có thể vẫn còn.
5. Nếu `sink` chính là một `PrintWriter` khác, các lớp wrapper có thể che giấu thông tin gốc sâu hơn; nên tránh lồng các lớp print không cần thiết.

Khi bạn kiểm soát cả API và vòng đời tài nguyên, thường **tốt hơn dùng `Writer`/`BufferedWriter` trực tiếp** với `throws IOException` thay vì ép một đường đi qua `PrintWriter` rồi tái tạo một ngoại lệ không có nguyên nhân.

### Đọc trạng thái sau `close()`

Nếu thao tác đóng/flush cuối cùng **có thể tạo lỗi mới**, việc kiểm tra `checkError()` **sau khi đóng** có giá trị để phát hiện lỗi mà `PrintWriter.close()` tự ghi nhận. Ví dụ:

~~~java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.Writer;

public final class CloseErrorCheck {
    private CloseErrorCheck() {}

    public static void writeAndCheck(Writer sink, String text)
            throws IOException {
        PrintWriter out = new PrintWriter(sink);
        try {
            out.print(text);
        } finally {
            out.close();
        }
        if (out.checkError()) {
            throw new IOException("Output or close failed");
        }
    }
}
~~~

Lớp này không có `main` và **cố ý chuyển quyền đóng `sink` cho helper**; chỉ dùng khi hợp đồng của phương thức cho phép đóng sink do caller truyền vào. `checkError()` của `PrintWriter` sau khi đóng không flush writer đã đóng, nhưng vẫn phản ánh lỗi đã được lớp này ghi nhận.

Nếu code có ngoại lệ runtime ngay trong khối `try`, Java tiếp tục lan truyền ngoại lệ sau `finally` và không đi tới `if`; vì thế ví dụ chủ yếu kiểm tra tình trạng thao tác I/O bình thường và đóng tài nguyên. Khi cần bảo toàn tất cả nguyên nhân và lỗi đóng, nên làm việc với `Writer` gốc và `try-with-resources` để Java ghi nhận cả suppressed exceptions.

## 10. Các ngoại lệ vẫn có thể ném ra bình thường

Không diễn giải “`PrintStream`/`PrintWriter` không ném `IOException` khi ghi” thành “mọi lệnh `print` luôn không ném ngoại lệ”. Các lỗi không thuộc cơ chế I/O nội bộ vẫn có thể phát sinh:

- `IllegalFormatException` (và các lớp con) khi chuỗi định dạng sai hoặc kiểu dữ liệu không khớp trong `printf`/`format`.
- `NullPointerException` cho tham số bắt buộc không được `null`, tùy overload/API.
- `IndexOutOfBoundsException` cho đoạn mảng/chuỗi sai chỉ số.
- `RuntimeException` do mã người dùng chạy trong `Object.toString()` hoặc `Formattable.formatTo(...)`.
- Lỗi lúc **mở file** ở constructor có thể là `IOException` hoặc ngoại lệ checked cụ thể; lỗi bảo mật/quyền truy cập có thể có cách biểu diễn khác.
- `Error` cấp JVM không được cơ chế này biến thành boolean thành công.

Ví dụ định dạng sai:

~~~java
System.out.printf("%d%n", "not a number");
~~~

Đoạn mã ném `IllegalFormatConversionException` (một loại `IllegalFormatException`); `checkError()` **không phải** cơ chế dùng để phát hiện lỗi định dạng này. Nó không phải `IOException` từ thiết bị I/O.

### Trường hợp `InterruptedIOException` của `PrintStream`

Tài liệu `PrintStream` Java 17 phân biệt `InterruptedIOException` với những `IOException` khác: khi bên dưới ném ngoại lệ dạng này, lớp có thể **đặt interrupt flag** của thread để biểu thị tín hiệu ngắt thay vì đặt cờ lỗi theo cách thông thường. Vì thế, **`checkError() == false` không phải bằng chứng rằng mọi trạng thái bất thường đều đã được loại trừ**. Khi ứng dụng có cơ chế hủy công việc/ngắt thread, cần xử lý cờ interrupt đúng ý nghĩa của thiết kế.

Không nên tự động xóa trạng thái ngắt bằng `Thread.interrupted()` chỉ để làm ví dụ “đẹp”, bởi phương thức đó **vừa đọc vừa xóa** cờ ngắt. Nếu cần kiểm tra mà không xóa, dùng `Thread.currentThread().isInterrupted()`.

## 11. `System.out` / `System.err` cần chú ý gì?

`System.out.println(...)` và `System.err.println(...)` thường được dùng với giả định “in được tức là thành công”. Trên console tương tác, nhiều lỗi không xảy ra thường xuyên, nhưng vẫn có thể gặp **đích đã đóng**, pipe bị phía nhận đóng sớm, môi trường redirect output, lỗi file log, hoặc đích I/O đặc biệt.

~~~java
System.out.println("export complete");
if (System.out.checkError()) {
    // Phát hiện trạng thái lỗi của PrintStream.
    // Quyết định xử lý ở tầng nghiệp vụ hoặc kênh báo lỗi khác.
}
~~~

Nếu `System.out` đã lỗi, việc tiếp tục báo lỗi bằng chính `System.out` có thể cũng không tới nơi. Tùy ứng dụng, có thể dùng một kênh quan sát khác, trả mã trạng thái, ném ngoại lệ ở tầng ứng dụng hoặc ghi vào hệ thống logging được thiết kế riêng.

**Không tự ý `close()` `System.out` hoặc `System.err`** trong thư viện hay chương trình còn cần in tiếp. Đây là các tài nguyên chia sẻ của tiến trình. `System.console()` có thể trả `null` khi chạy trong IDE, CI hoặc môi trường không có console tương tác; không nên coi việc có console là mặc định.

`checkError()` trên `System.out` cũng có thể flush. Nó **không xác nhận** người dùng đã nhìn thấy văn bản trên terminal, file redirect đã fsync, hay hệ thống giám sát đã tiếp nhận log.

## 12. `Formatter.ioException()`: cơ chế tương tự nhưng khác API

`java.util.Formatter` nhận `Appendable` làm đích và hỗ trợ `format(...)`. Khi gặp `IOException` lúc ghi qua đích, `Formatter` có thể ghi nhớ ngoại lệ thay vì truyền lên qua phương thức format; có thể kiểm tra với **`formatter.ioException()`**.

~~~java
import java.io.IOException;
import java.io.Writer;
import java.util.Formatter;
import java.util.Locale;

public class FormatterErrorDemo {
    static final class FailingWriter extends Writer {
        @Override
        public void write(char[] chars, int offset, int length)
                throws IOException {
            throw new IOException("formatter output failed");
        }

        @Override
        public void flush() { }

        @Override
        public void close() { }
    }

    public static void main(String[] args) {
        try (Formatter formatter =
                     new Formatter(new FailingWriter(), Locale.ROOT)) {
            formatter.format("item=%d", 42);

            IOException cause = formatter.ioException();
            System.out.println("formatterError=" + (cause != null));
            System.out.println("message="
                    + (cause == null ? "none" : cause.getMessage()));
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FormatterErrorDemo.java
java FormatterErrorDemo
~~~

**Stdout dự kiến:**

~~~text
formatterError=true
message=formatter output failed
~~~

Điểm khác biệt với `PrintWriter.checkError()`: `Formatter.ioException()` có thể trả lại **`IOException` được ghi nhận**, thay vì chỉ một giá trị boolean. Tuy nhiên `Formatter` và `PrintWriter` không phải cùng một lớp; đừng gọi `checkError()` trên `Formatter` hay gọi `ioException()` trên `PrintStream`.

Lỗi cú pháp định dạng như `IllegalFormatException` vẫn được xử lý theo hợp đồng riêng và có thể ném trực tiếp. Khi dùng `Formatter` bọc các đối tượng khác, phải rõ ai sở hữu đích và liệu `Formatter.close()` có đóng đích nếu đích triển khai `Closeable` hay không.

## 13. Lỗi lúc flush/close: thời điểm thường bị bỏ sót

Một số hệ thống có buffer ở nhiều tầng:

~~~text
print / println / printf
          |
          v
PrintWriter / PrintStream [trạng thái lỗi]
          |
          v
BufferedWriter / encoder / OutputStream
          |
          v
File / pipe / socket / thiết bị
~~~

Lệnh in có thể chỉ đưa dữ liệu vào buffer. Lỗi chỉ xuất hiện khi:

- Dữ liệu đủ nhiều làm buffer phải đẩy xuống tầng dưới.
- `autoFlush` kích hoạt một đợt flush.
- `checkError()` gọi flush.
- `flush()` hoặc `close()` được gọi trực tiếp.
- Tầng bên dưới thực hiện chuyển dữ liệu rồi mới biết đích không còn khả dụng.

Vì vậy có thể **chưa có lỗi được ghi nhận ở thời điểm `print()` trả về**, nhưng sau một lần flush/checkError lại là `true`. Khi có nhiều tầng buffering, cần xác định chỗ nào là **ranh giới hoàn thành** của tác vụ.

Nếu một quy trình có yêu cầu xác thực dữ liệu đã được lưu bền vững hoặc nhận bởi hệ thống khác, cần cơ chế mạnh hơn (ví dụ xác nhận phía nhận, transaction, checksum/ack, `FileChannel.force` khi có yêu cầu đồng bộ file). Bản thân `checkError()` chỉ kiểm tra trạng thái lỗi mà print API quan sát được.

## 14. Hướng dẫn quyết định chọn API

### Chỉ cần in cho người dùng hoặc debug

`System.out.print/println/printf` phù hợp. Khi công cụ CLI có yêu cầu đầu ra bắt buộc chính xác, hãy cân nhắc kiểm tra `System.out.checkError()` sau khi hoàn tất và phản ánh lỗi bằng mã thoát hoặc kênh khác.

### Cần in định dạng ra một `Writer` đã có

`PrintWriter` rất tiện cho `printf/println`. Nếu lỗi ghi là vấn đề nghiệp vụ, **kiểm tra `checkError()` sau đợt ghi/flush**, đồng thời hiểu rằng mất nguyên nhân gốc khiến báo lỗi kém chi tiết.

### Cần độ chính xác và khả năng retry/audit

Ưu tiên `Writer`/`BufferedWriter` hoặc `OutputStream`/`BufferedOutputStream` với `throws IOException`. Khi lỗi xảy ra, giữ nguyên nguyên nhân và quyết định rõ chính sách ghi một phần, retry, file tạm, timeout và đóng tài nguyên.

### Cần format qua `Appendable` tùy ý

`Formatter` có thể phù hợp; kiểm tra `ioException()` cho lỗi I/O của đích và vẫn xử lý lỗi format/runtime bằng cách khác.

### Có nhiều tầng wrapper

Đừng bọc nhiều `PrintWriter`/`PrintStream` không cần thiết rồi giả định tầng ngoài phản ánh đầy đủ từng lỗi. Hợp đồng có thể chuyển lỗi thành trạng thái nội bộ ở tầng đầu tiên; dùng một API lỗi rõ ràng ở biên nghiệp vụ sẽ dễ quản lý hơn.

## 15. Những hiểu nhầm thường gặp

**1. “Không thấy exception tức là đã ghi thành công.”**  
Sai với `PrintStream`/`PrintWriter`: lỗi I/O thông thường có thể chỉ bật cờ. Hãy dùng `checkError()` nếu kết quả ghi cần được kiểm tra.

**2. “`checkError()` chỉ đọc cờ, không tác động I/O.”**  
Sai: khi còn mở, phương thức có thể gọi flush, và flush lại có thể gây lỗi mới hoặc độ trễ I/O.

**3. “`checkError() == false` nghĩa là byte đã đến đích cuối và bền vững.”**  
Sai: nó không bảo đảm fsync, nhận trên socket hay thành công của các bước lưu trữ bên ngoài. Cờ phản ánh lỗi được lớp print nhận biết, không phải biên bản giao hàng.

**4. “Nếu in thất bại sẽ biết chính xác IOException nào từ `checkError()`.”**  
Sai: kết quả chỉ là boolean. Cần API ném lỗi trực tiếp hoặc cơ chế giám sát riêng nếu cần nguyên nhân.

**5. “`PrintStream` và `PrintWriter` autoFlush giống nhau.”**  
Sai: `PrintWriter` kích hoạt autoFlush theo `println/printf/format`; `PrintStream` có thêm hành vi theo ghi mảng byte và newline.

**6. “Tất cả ngoại lệ đều bị các lớp print bắt lại.”**  
Sai: lỗi định dạng `IllegalFormatException`, lỗi chỉ số và các ngoại lệ runtime vẫn có thể phát sinh. `InterruptedIOException` ở `PrintStream` còn có đường xử lý riêng.

**7. “Gọi `close()` xong là mọi lỗi đều tự được báo bằng exception.”**  
Sai với `PrintStream`/`PrintWriter`: lỗi I/O lúc flush/close cũng có thể được ghi nhận trong trạng thái thay vì ném. Với tác vụ quan trọng, cần chính sách kiểm tra cuối đời tài nguyên và ownership rõ ràng.

**8. “Cờ lỗi true nghĩa là lần ghi gần nhất thất bại hoàn toàn.”**  
Sai: trạng thái có thể tích lũy lỗi cũ, và thao tác ghi có thể thành công một phần trước khi xảy ra lỗi. Đừng dùng cờ lỗi như một bộ đếm số byte đã ghi hoặc phân loại lỗi chi tiết.

## 16. Checklist kiểm tra mã sản xuất

- [ ] Biết biến đầu ra là `PrintStream`, `PrintWriter`, `Formatter` hay `Writer/OutputStream`?
- [ ] Nếu dùng lớp print, có `checkError()` ở mốc mà nghiệp vụ cần biết tình trạng I/O?
- [ ] Nếu dùng `Formatter`, đã kiểm tra `ioException()` khi điều kiện đầu ra yêu cầu không có lỗi?
- [ ] Có phân biệt lỗi I/O được ghi vào cờ với lỗi runtime/format có thể ném trực tiếp?
- [ ] Có hiểu `checkError()` có thể flush khi đối tượng còn mở?
- [ ] Không coi trạng thái false là bảo đảm durable commit, network ACK hoặc giao hàng thành công?
- [ ] Nếu dùng `autoFlush`, đã hiểu đúng khác biệt giữa `PrintStream` và `PrintWriter`?
- [ ] Quyền đóng resource đã rõ: ai sở hữu `Writer`/`OutputStream`, ai chịu trách nhiệm đóng và báo lỗi ở cuối?
- [ ] Khi cần nguyên nhân `IOException` và chính sách retry nghiêm ngặt, đã cân nhắc dùng API trực tiếp có `throws IOException`?
- [ ] Không đóng `System.out`/`System.err` do thư viện không sở hữu?
- [ ] Test có mô phỏng lỗi ghi bằng `OutputStream`/`Writer` giả lập thay vì kỳ vọng lỗi file/ngẫu nhiên?

### Câu hỏi tự kiểm tra

**Câu 1.** `PrintWriter.println("A")` hoàn thành, không có exception. Có chắc đã ghi thành công không?  
**Đáp án:** Không. Cần quan sát `checkError()` tại mốc hợp lý và hiểu giới hạn của tín hiệu này.

**Câu 2.** `checkError()` có thể tự làm một thao tác I/O không?  
**Đáp án:** Có. Nếu luồng còn mở, nó flush trước khi kiểm tra trạng thái lỗi.

**Câu 3.** `PrintWriter(autoFlush=true).write('\n')` có chắc tự flush không?  
**Đáp án:** Không. AutoFlush của `PrintWriter` gắn với `println/printf/format`; khác `PrintStream`.

**Câu 4.** Nếu muốn giữ nguyên nguyên nhân `IOException` khi ghi file cấu hình, nên dùng gì?  
**Đáp án:** Dùng `Writer`/`BufferedWriter` hoặc `OutputStream` với `throws IOException` và `try-with-resources`; các API này có thể truyền nguyên nhân lỗi gốc lên caller.

**Câu 5.** `System.out.checkError() == false` có chứng minh log đã được hệ thống giám sát đọc chưa?  
**Đáp án:** Không. Nó không phải xác nhận từ hệ thống nhận log.

**Câu 6.** Nếu gọi `printf("%d", "text")` và Java ném `IllegalFormatConversionException`, có phải `checkError` là cơ chế xử lý?  
**Đáp án:** Không. Đây là lỗi định dạng runtime, cần xử lý theo hợp đồng định dạng, khác lỗi I/O được giữ trong cờ.

**Ghi nhớ:** `PrintStream` và `PrintWriter` chọn sự tiện lợi khi in văn bản/định dạng nên **có thể chuyển lỗi I/O thành trạng thái**. `checkError()` giúp phát hiện lỗi mà lớp in biết tới, nhưng **không mang nguyên nhân chi tiết và không bảo đảm dữ liệu đã tới nơi cuối cùng**. Khi tính đúng đắn đòi hỏi xử lý lỗi chính xác, hãy chọn abstraction cho phép `IOException` đi tới caller và quản lý đầy đủ vòng đời tài nguyên.

## Tham khảo API chính thức (Java 17)

- [PrintStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html)
- [PrintWriter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html)
- [Formatter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html)
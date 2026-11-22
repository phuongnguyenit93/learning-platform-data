# Tác động của `autoFlush` khi ghi mảng byte với `PrintStream` (Java 14+)

> **Mục tiêu:** hiểu đúng cơ chế `autoFlush` của `java.io.PrintStream` khi ghi `byte[]`: khi `autoFlush=true`, **mỗi thao tác ghi mảng byte được phép gọi `flush()` của luồng đích**, kể cả khi các byte **không** chứa ký tự xuống dòng; khi `autoFlush=false`, thao tác đó không tự kích hoạt flush theo quy tắc của `PrintStream`. Bài phân biệt `writeBytes(byte[])` và hai overload `write(byte[])`, `write(byte[],off,len)` với `write(int)`, giải thích dữ liệu nhị phân so với text encoding, việc đẩy buffer và cách nhận biết lỗi I/O. API `PrintStream.writeBytes(byte[])` và override `PrintStream.write(byte[])` được bổ sung trong **Java 14** và vẫn áp dụng trong Java SE hiện hành; chương trình chạy bằng **JDK 17+**, kiểm chứng trên OpenJDK 24.

## 1. Bối cảnh: `PrintStream` ghi byte và văn bản như thế nào?

`PrintStream` là một stream bọc quanh `OutputStream` để cung cấp thêm các thao tác `print`, `println`, `printf`, `format` và ghi dữ liệu. Nó cũng là kiểu của các luồng `System.out` / `System.err`. Một đối tượng `PrintStream` có thể được khởi tạo với cờ `autoFlush` cùng một `Charset` tường minh:

```java
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

PrintStream stream = new PrintStream(
    outputStream, true, StandardCharsets.UTF_8);
```

Đây là **snippet** trong phương thức có biến `OutputStream outputStream` do ứng dụng sở hữu. `true` là cờ `autoFlush`; `UTF_8` dùng **khi chuyển ký tự thành byte** bởi `print`/`println`, không làm thay đổi giá trị các byte thô được gửi vào `writeBytes`.

Có hai đường ghi khác nhau:

- **Ghi raw bytes:** `writeBytes(byte[])`, `write(byte[])`, `write(byte[],int,int)`, `write(int)`. Những byte bạn đưa vào được gửi **nguyên giá trị**, không được tự chuyển mã theo `Charset`.
- **Ghi dạng text:** `print(String)`, `println(String)`, `printf(...)`, v.v. Những ký tự được mã hóa thành byte bằng charset của `PrintStream`; thao tác xuống dòng còn có quy tắc riêng theo API.

Bài này tập trung **tác động của autoFlush khi ghi mảng byte**, không đánh đồng nó với hành vi của mọi stream Java hoặc khái niệm kết thúc dòng text.

## 2. Chính xác khi nào `PrintStream` tự flush?

JavaDoc Java SE 17/25/26 mô tả: nếu bật automatic flushing, `PrintStream` gọi `flush` ở luồng bên dưới **sau khi ghi một mảng byte**, khi gọi một trong các phương thức `println`, hoặc khi ký tự/byte newline `'\n'` được ghi.

| Thao tác trên `PrintStream` | Với `autoFlush=true` | Với `autoFlush=false` |
|---|---|---|
| `writeBytes(byte[])` | **Flush sau thao tác ghi mảng**, dù không chứa `'\n'` | Không tự flush do thao tác mảng |
| `write(byte[])` | **Flush sau thao tác ghi mảng** | Không tự flush do thao tác mảng |
| `write(byte[], off, len)` | **Flush sau thao tác ghi mảng** | Không tự flush do thao tác mảng |
| `write(int b)` với `b == '\n'` | **Flush** vì byte newline | Không tự flush |
| `write(int b)` với `b != '\n'` | Không tự flush theo quy tắc của `write(int)` | Không tự flush |
| `println(...)` | **Flush** khi gọi `println` | Không tự flush do `println` |
| `print(String)` / `printf(...)` | Có thể flush do quy tắc xuống dòng hoặc đường mã hóa nội bộ; xem `println` khi cần ranh giới dòng rõ | Không dùng làm bảo đảm đẩy dữ liệu tới đích |
| `flush()` gọi tường minh | Flush bất kể `autoFlush` | Flush bất kể `autoFlush` |
| `close()` | Có thao tác hoàn tất/đóng luồng đích | Có thao tác hoàn tất/đóng luồng đích |

**Điểm dễ sai nhất:** `autoFlush=true` **không có nghĩa “chỉ flush khi gặp newline”**. Mảng byte `{'A','B'}` không chứa `'\n'` nhưng `print.writeBytes(new byte[]{'A','B'})` vẫn gây flush. Đây là hợp đồng nổi bật của `PrintStream`, khác với trực giác line-buffering từ một số thư viện khác.

**Không nhầm `flush()` với đồng bộ vật lý:** gọi flush ở `OutputStream` đích có nghĩa yêu cầu đẩy các byte đang nằm trong lớp buffer của luồng đích xuống tầng kế tiếp. Điều đó **không tự đảm bảo** dữ liệu đã được fsync xuống disk, đã truyền tới toàn bộ peer mạng, hoặc đã được người dùng nhìn thấy ngay trên terminal.

## 3. Vì sao `writeBytes(byte[])` đặc biệt phù hợp từ Java 14?

Từ Java 14, `PrintStream` cung cấp phương thức tiện dụng:

```java
public void writeBytes(byte[] buf)
```

Ý nghĩa: ghi **toàn bộ** các byte trong `buf`, tương đương:

```java
stream.write(buf, 0, buf.length);
```

Tài liệu cũng định nghĩa `PrintStream.write(byte[])` ghi toàn mảng với cùng hiệu ứng. Sự khác biệt quan trọng với người gọi là **checked exception trong chữ ký**:

| API | Biên dịch có phải xử lý `IOException` không? | Có flush khi `autoFlush=true`? |
|---|---|---|
| `PrintStream.writeBytes(byte[])` | **Không** | Có |
| `PrintStream.write(byte[],int,int)` | **Không** | Có |
| `PrintStream.write(byte[])` | **Có**, vì chữ ký khai báo `throws IOException` | Có |
| `PrintStream.write(int)` | **Không** | Chỉ khi byte newline |

Ví dụ trong phương thức Java:

```java
byte[] payload = {65, 66, 67};

stream.writeBytes(payload);             // Java 14+, không checked IOException
stream.write(payload, 0, payload.length); // Tương đương về dữ liệu
stream.write(payload);                  // Chữ ký có throws IOException
```

**Vì sao `write(byte[])` lại khai báo `IOException`?** Nó override phương thức `FilterOutputStream.write(byte[])`, phải duy trì chữ ký tương thích. Nhưng JavaDoc của `PrintStream` nói rõ override này **không thực sự ném IOException**; lỗi I/O được ghi vào cờ lỗi nội bộ như các phương thức `PrintStream` khác.

**Đừng hiểu ba lời gọi trên nên thực hiện nối tiếp để “ghi một lần”**: đoạn snippet chỉ so sánh API. Thực thi cả ba sẽ **ghi payload ba lần**, và nếu `autoFlush=true` thì mỗi lần có thể kích hoạt flush. Trong ứng dụng, chọn **một** phương thức phù hợp.

### `writeBytes` không phải là chuyển String thành bytes

```java
byte[] utf8 = "Xin chào".getBytes(StandardCharsets.UTF_8);
stream.writeBytes(utf8);
```

Đoạn trên mã hóa `String` **tường minh** thành UTF-8 trước rồi ghi các byte. Nếu đã có bytes từ protocol, file hoặc network, `writeBytes` **không** biến chúng thành text và không tự sinh newline. Ngược lại:

```java
stream.println("Xin chào");
```

là thao tác text: charset của `PrintStream` sẽ được sử dụng, rồi thêm line separator theo quy tắc của `println`.

**Lưu ý `print(byte[])` không có overload riêng** để đẩy raw bytes. Do đó không sử dụng `print(bytes)` với hy vọng ghi từng byte; một `byte[]` đi qua `print(Object)` có thể in dạng biểu diễn của object, không phải payload nhị phân.

## 4. Điểm đối chứng: `write(int)` và một byte newline

```java
PrintStream stream = new PrintStream(
    outputStream, true, StandardCharsets.UTF_8);

stream.write('A');   // Không có lý do tự flush vì đây không phải newline.
stream.write('\n');  // Tự flush khi autoFlush=true.
```

Đây là snippet có `OutputStream outputStream` tồn tại trước. Mỗi `write(int)` chỉ gửi **8 bit thấp** của số nguyên; không coi nó là phương thức mã hóa một Java `char` Unicode bất kỳ. Với `'\n'` giá trị byte là `10` trong ASCII/UTF-8, nên hành vi newline rõ ràng.

Cần tách hai câu hỏi:

- Nếu truyền một byte `10` **qua `write(int)`**, trường hợp autoFlush bật sẽ trigger flush vì nó chính là newline.
- Nếu truyền mảng `{65,66}` **qua `writeBytes`**, autoFlush vẫn trigger flush **không cần byte 10**.

Không nên dùng “mỗi lần gọi `write` đều flush” để mô tả mọi overload. Đúng hơn là **theo loại thao tác**. `write(int)` trên ký tự không newline khác với `write(byte[])` ở điều kiện flush.

### Trường hợp mảng rỗng

Theo implementation requirements, `writeBytes(buf)` tương đương `write(buf,0,buf.length)`. Với `new byte[0]`, không có byte dữ liệu mới, nhưng **lời gọi ghi mảng vẫn diễn ra**; trên OpenJDK 24, với `autoFlush=true`, nó **vẫn gọi flush**.

Điều này dễ bị bỏ sót khi ghi nhiều chunk:

```java
stream.writeBytes(new byte[0]); // Không thêm byte nhưng có thể flush.
```

Không dùng `writeBytes(new byte[0])` làm “lệnh flush” có ý đồ: rõ ràng hơn là gọi `stream.flush()`. Một mảng rỗng không tạo dữ liệu, và chi tiết flush trong thực tế có thể gắn với implementation; ưu tiên lệnh flush tường minh khi đó là mục tiêu của code.

## 5. `autoFlush` ảnh hưởng thế nào đến `BufferedOutputStream`?

`PrintStream` thường bọc quanh một tầng đệm `BufferedOutputStream`:

```text
PrintStream (autoFlush=true / false)
            |
            v
BufferedOutputStream (buffer capacity)
            |
            v
FileOutputStream / Socket OutputStream / byte sink
```

Giả sử bạn đưa 4 bytes `PING` vào `PrintStream` bằng `writeBytes`, trong khi buffer ở dưới chưa đầy:

- Với **autoFlush=false**, dữ liệu có thể chỉ nằm ở `BufferedOutputStream`, chưa chuyển sang output stream cuối. Bạn vẫn có thể nhìn thấy dữ liệu trong các vùng buffer khác nhau, nhưng không được giả định tầng đích đã nhận ngay.
- Với **autoFlush=true**, sau lần ghi mảng, `PrintStream` yêu cầu flush ở tầng đích; `BufferedOutputStream.flush()` đẩy bytes đang đệm xuống output stream tiếp theo.
- Với cả hai chế độ, gọi `print.flush()` tường minh sẽ cố flush tầng được bọc và các lớp downstream theo hợp đồng API.

**Mô hình quan sát bằng bộ đệm trong Java (không dùng mạng hay đĩa):**

```java
ByteArrayOutputStream sink = new ByteArrayOutputStream();
try (PrintStream print = new PrintStream(
        new BufferedOutputStream(sink, 64),
        false, StandardCharsets.UTF_8)) {
    print.writeBytes("PING".getBytes(StandardCharsets.UTF_8));
    System.out.println(sink.size()); // 0 trong ví dụ: 4 bytes chưa qua buffer 64 B.
    print.flush();
    System.out.println(sink.size()); // 4: đã đẩy xuống ByteArrayOutputStream.
}
```

Snippet đầy đủ này cần các import `java.io` tương ứng và phù hợp để dùng trong một method. Kết quả không mô tả **thời điểm bytes ra mạng**: đích cuối ở đây là một mảng byte trong RAM, còn `ByteArrayOutputStream.flush()` vốn không cần đẩy dữ liệu tới thiết bị nào.

**Ảnh hưởng hiệu năng:** nếu ghi hàng nghìn mảng rất nhỏ với `autoFlush=true` qua tầng `BufferedOutputStream`, mỗi lần ghi có thể làm giảm lợi ích gộp batch và tăng số lần gọi flush xuống tầng I/O; tuỳ filesystem/socket, có thể làm tăng overhead, giảm throughput hoặc tăng số lần write nhỏ. Bật autoFlush khi cần cập nhật thường xuyên hoặc đáp ứng nhanh, tắt để quản lý ranh giới batch khi ưu tiên throughput — **đo với workload thật** trước khi kết luận tốc độ.

## 6. Chương trình Java 17+ hoàn chỉnh, kiểm chứng chính xác

Tạo tệp **`PrintStreamAutoFlushArrayDemo.java`** sau. Chương trình dùng ba kỹ thuật minh họa:

1. `CountingOutputStream` ghi lại **số lần nhận `flush()`** từ `PrintStream`. Đây là subclass của `ByteArrayOutputStream`; cách đếm tách biệt với việc nội dung bytes đã có trong mảng RAM.
2. `bufferVisibility` đặt `BufferedOutputStream` ở giữa để xem byte có xuống sink trước lần flush thủ công hay chưa.
3. `FailingOutputStream` ném `IOException` cố ý để kiểm chứng `PrintStream.checkError()`.

```java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class PrintStreamAutoFlushArrayDemo {
    static final class CountingOutputStream extends ByteArrayOutputStream {
        private int flushCalls;

        @Override
        public void flush() throws IOException {
            super.flush();
            flushCalls++;
        }

        int flushCalls() {
            return flushCalls;
        }
    }

    static void measure(String label, boolean autoFlush) throws IOException {
        CountingOutputStream target = new CountingOutputStream();
        try (PrintStream print =
                 new PrintStream(target, autoFlush, StandardCharsets.UTF_8)) {
            System.out.println(label + ".start=" + target.flushCalls());

            print.writeBytes(new byte[] {'A', 'B'});
            System.out.println(label + ".writeBytes=" + target.flushCalls());

            print.write('C');
            System.out.println(label + ".writeC=" + target.flushCalls());

            print.write('\n');
            System.out.println(label + ".writeNewline=" + target.flushCalls());

            print.write(new byte[] {'D', 'E'}, 0, 2);
            System.out.println(label + ".writeSlice=" + target.flushCalls());

            print.writeBytes(new byte[0]);
            System.out.println(label + ".writeEmpty=" + target.flushCalls());

            print.write(new byte[] {'F', 'G'});
            System.out.println(label + ".writeArray=" + target.flushCalls());

            print.flush();
            System.out.println(label + ".manualFlush=" + target.flushCalls());
            System.out.println(label + ".bytes=" +
                Arrays.toString(target.toByteArray()));
        }
    }

    static void bufferVisibility(String label, boolean autoFlush) {
        ByteArrayOutputStream target = new ByteArrayOutputStream();
        try (PrintStream print = new PrintStream(
                new BufferedOutputStream(target, 64),
                autoFlush, StandardCharsets.UTF_8)) {
            print.writeBytes("PING".getBytes(StandardCharsets.UTF_8));
            System.out.println(label + ".beforeManual=" + target.size());
            print.flush();
            System.out.println(label + ".afterManual=" + target.size());
        }
    }

    static final class FailingOutputStream extends OutputStream {
        @Override
        public void write(int b) throws IOException {
            throw new IOException("simulated failure");
        }

        @Override
        public void write(byte[] bytes, int off, int len) throws IOException {
            throw new IOException("simulated failure");
        }
    }

    public static void main(String[] args) throws IOException {
        measure("on", true);
        measure("off", false);
        bufferVisibility("bufferOn", true);
        bufferVisibility("bufferOff", false);

        try (PrintStream print = new PrintStream(
                new FailingOutputStream(),
                true, StandardCharsets.UTF_8)) {
            print.writeBytes(new byte[] {42});
            System.out.println("failed.checkError=" + print.checkError());
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 PrintStreamAutoFlushArrayDemo.java
java PrintStreamAutoFlushArrayDemo
```

**Stdout đã kiểm chứng khi chạy trên OpenJDK 24 Windows:**

```text
on.start=0
on.writeBytes=1
on.writeC=1
on.writeNewline=2
on.writeSlice=3
on.writeEmpty=4
on.writeArray=5
on.manualFlush=6
on.bytes=[65, 66, 67, 10, 68, 69, 70, 71]
off.start=0
off.writeBytes=0
off.writeC=0
off.writeNewline=0
off.writeSlice=0
off.writeEmpty=0
off.writeArray=0
off.manualFlush=1
off.bytes=[65, 66, 67, 10, 68, 69, 70, 71]
bufferOn.beforeManual=4
bufferOn.afterManual=4
bufferOff.beforeManual=0
bufferOff.afterManual=4
failed.checkError=true
```

### Bảng giải nghĩa các nhóm dòng

| Nhóm | Quan sát | Ý nghĩa |
|---|---|---|
| `on.writeBytes=1` | Ghi `{'A','B'}` làm tăng flush lên 1 | Mảng không newline vẫn flush khi bật autoFlush |
| `on.writeC=1` | `write('C')` không tăng flush | Byte đơn không newline khác mảng |
| `on.writeNewline=2` | `write('\n')` tăng flush | Byte newline là điều kiện flush riêng |
| `on.writeSlice=3` | `write(byte[],off,len)` tăng flush | Chỉ chọn một phần mảng vẫn trigger |
| `on.writeEmpty=4` | `writeBytes(new byte[0])` tăng flush trên JDK kiểm tra | Không có payload mới nhưng vẫn có lời gọi flush |
| `on.writeArray=5` | `write(byte[])` cũng tăng flush | Ba dạng ghi mảng có hành vi autoFlush nhất quán |
| `on.manualFlush=6` | `flush()` tường minh tăng tiếp | Tác động không phụ thuộc trigger tự động |
| Mọi dòng `off.write...=0` | Tắt autoFlush thì các lần ghi không gọi flush | Chỉ `off.manualFlush=1` tăng |
| `on.bytes` và `off.bytes` giống nhau | Dãy raw byte cuối cùng giống nhau | Cờ autoFlush **không tự sửa payload** |
| `bufferOn.beforeManual=4` | Sink bên dưới đã có 4 bytes | AutoFlush đã đẩy tầng buffer trung gian |
| `bufferOff.beforeManual=0` | Sink chưa có byte trước flush | BufferedOutputStream giữ bytes khi chưa flush |
| `bufferOff.afterManual=4` | Flush thủ công đẩy 4 bytes | Manual flush có hiệu lực dù autoFlush false |
| `failed.checkError=true` | PrintStream đánh dấu lỗi I/O | Việc không ném IOException không có nghĩa đã ghi thành công |

**Tại sao không in count sau `try-with-resources`?** `close()` có thể flush/đóng luồng bên dưới nên làm thay đổi số lần flush khi rời block. Ví dụ chụp snapshot **trước khi close**, để đếm đúng những thao tác muốn so sánh.

**Vì sao không dùng `System.out` làm stream đang đo?** Các dòng giải thích được in ra `System.out` để tránh phép đo tự gây tác dụng phụ trên `print`. `System.out` cũng là một `PrintStream`, nhưng số flush thực tế của console phụ thuộc môi trường; ta không nên suy ra cấu hình autoFlush của nó từ ví dụ này.

## 7. Kiểm tra lỗi đúng cách: `checkError()` có side effect flush

`PrintStream` có quy ước khác `FileOutputStream`/`BufferedOutputStream`: những lỗi I/O xảy ra trong quá trình ghi/flush **thường không được ném ra dưới dạng checked `IOException`**; chúng khiến stream đặt một **internal error flag**. Có thể hỏi:

```java
boolean hasFailed = stream.checkError();
```

**Lưu ý:** theo JavaDoc, `checkError()` cũng **flush stream nếu chưa đóng** trước khi trả trạng thái, nên đây không phải thao tác “đọc cờ” hoàn toàn không có side effect. Khi đo số lần flush, **đừng gọi `checkError()` giữa các lần đo** trừ khi chủ đích ghi nhận cả lời gọi flush của chính nó.

Mã `FailingOutputStream` trong chương trình đầy đủ ném `IOException("simulated failure")` ngay tại `write`. `PrintStream.writeBytes` không chuyển ngoại lệ đó trực tiếp cho caller; `print.checkError()` trả `true`. Điều này lý giải vì sao code cần xử lý `checkError()` nếu tính toàn vẹn của đầu ra rất quan trọng.

Ví dụ ghi xong rồi kiểm tra một lần:

```java
try (PrintStream print = new PrintStream(
        target, true, StandardCharsets.UTF_8)) {
    print.writeBytes(payload);
    if (print.checkError()) {
        throw new java.io.UncheckedIOException(
            new java.io.IOException("Failed to write output bytes"));
    }
}
```

Đây là **snippet** trong phương thức có `OutputStream target` và `byte[] payload`. Ngoại lệ trong code do **ứng dụng tự tạo** để báo status; nó không tái tạo được cause gốc nếu `PrintStream` không cung cấp lại exception. Với hệ thống cần biết **chính xác IOException/cause**, thường nên dùng `OutputStream`/`BufferedOutputStream` trực tiếp, cho phép propagate IOException, thay vì chọn `PrintStream`.

**Không hiểu `write(byte[]) throws IOException` là ngoại lệ Java checked sẽ luôn được ném trong runtime:** chữ ký có khai báo nhưng JavaDoc xác định `PrintStream` không ném `IOException` từ override. Đừng dùng `catch(IOException)` làm cơ chế phát hiện lỗi ghi mảng từ `PrintStream`.

## 8. So sánh `PrintStream`, `PrintWriter` và `BufferedOutputStream`

| Thành phần | Dữ liệu hướng đến | Khi nào autoFlush? | Phù hợp |
|---|---|---|---|
| **`PrintStream`** với `autoFlush=true` | Raw bytes và text đã mã hóa | Mảng byte, `println`, newline | Console/output có cả text và byte |
| **`PrintWriter`** với `autoFlush=true` | **Ký tự/text** | Khi gọi `println`, `printf`, `format`; không chỉ vì `'\n'` xuất hiện trong `write` | Xuất văn bản |
| **`BufferedOutputStream`** | **Raw bytes** | Không có tham số `autoFlush` kiểu `PrintStream`; flush khi buffer đầy, đóng hoặc gọi `flush` | Ghi byte theo batch, kiểm soát IOException |
| **`OutputStream`** nói chung | Raw bytes | Phụ thuộc implementation của từng subclass, không thừa hưởng quy tắc của `PrintStream` | API byte stream nền tảng |

**Đặc biệt với `PrintWriter`:** JavaDoc nói autoFlush chỉ tự diễn ra khi gọi `println`/`printf`/`format`, không đơn thuần khi một ký tự newline đi qua `write`. `PrintWriter` không có `writeBytes(byte[])` để ghi raw bytes. Không sao chép cách vận hành autoFlush của `PrintStream` sang `PrintWriter`.

**Lớp buffer bên dưới cũng quan trọng.** `BufferedOutputStream` có thể tự đẩy dữ liệu khi đầy ngay cả khi `PrintStream` autoFlush false. Vì vậy kết luận “autoFlush=false thì bytes không bao giờ ra đích trước manual flush” là **sai**: buffer có thể đầy hoặc một thao tác khác khiến flush xảy ra. Ví dụ của chúng ta cố tình dùng buffer 64 byte với payload 4 byte để loại bỏ trường hợp đầy buffer.

## 9. Phân biệt flush, đóng stream và cam kết lưu trữ bền vững

`flush` là yêu cầu đẩy dữ liệu qua lớp đệm của `OutputStream`. Nó không tự đồng nghĩa:

- **`FileDescriptor.sync()`/`FileChannel.force(...)`:** yêu cầu đồng bộ dữ liệu tới thiết bị lưu trữ theo hợp đồng API.
- **Xác nhận giao dịch database:** commit có semantics của hệ quản trị dữ liệu, không thể thay bằng flush của một stream bất kỳ.
- **ACK từ mạng/peer:** số byte đã được ghi tới socket buffer không đồng nghĩa peer đã xử lý payload.
- **Ranh giới thông điệp/record:** một lần gọi `writeBytes` không tự thêm delimiter, length prefix, checksum hay tạo transaction atomic.

Nếu ghi file có yêu cầu độ bền đặc biệt khi mất điện, hãy đánh giá API đồng bộ file và thuộc tính của storage/filesystem. Nếu truyền network protocol, cần ứng dụng định nghĩa framing và acknowledgment. **Bật `autoFlush=true` không thay các cơ chế này.**

### `close()` và sở hữu stream

`try-with-resources` được dùng khi code **sở hữu** PrintStream và OutputStream bên dưới. Đóng `PrintStream` sẽ đóng luồng bên dưới và thường hoàn tất các thao tác flush còn cần thiết. Nếu ứng dụng đang ghi `System.out` hoặc `System.err` chung, **không đóng chúng** chỉ vì một đoạn code tiện dùng `try-with-resources`: nó có thể ảnh hưởng toàn bộ tiến trình. Nếu cần đóng riêng một wrapper mà không đóng đích chung, phải có thiết kế lifecycle riêng.

Đừng dùng việc `close()` thành công làm bằng chứng không có lỗi ghi, vì `PrintStream` có cơ chế error flag. Khi cần bảo đảm I/O chính xác, kiểm tra kết quả/lỗi ở đúng tầng API.

## 10. Các trường hợp sử dụng và tác động hiệu năng

### 10.1. Ghi từng mảng nhỏ để phản hồi tương tác

Ứng dụng muốn từng bản tin xuất đi sớm:

```java
PrintStream stream = new PrintStream(
    socketOutput, true, StandardCharsets.UTF_8);
stream.writeBytes("READY\n".getBytes(StandardCharsets.UTF_8));
```

Đây là snippet trong method có `OutputStream socketOutput`. Flush sớm có thể giúp giảm thời gian ở buffer Java; **không đảm bảo peer đã đọc và phản hồi**. Vì mảng byte vốn đã trigger flush, việc có thêm `'\n'` chỉ là **dữ liệu protocol**, không phải điều kiện bắt buộc để autoFlush hoạt động.

### 10.2. Ghi file/batch lớn và kiểm soát số flush

Khi ưu tiên throughput, có thể quản lý flush theo batch:

```java
try (PrintStream stream = new PrintStream(
        bufferedTarget, false, StandardCharsets.UTF_8)) {
    for (byte[] chunk : chunks) {
        stream.writeBytes(chunk);
    }
    stream.flush();
    if (stream.checkError()) {
        throw new IllegalStateException("Output stream error");
    }
}
```

Snippet trên giả định `OutputStream bufferedTarget`, `Iterable<byte[]> chunks`. Có thể gom nhiều chunk trước một flush thay vì flush sau từng mảng; tuy nhiên độ lớn buffer, deadline truyền tin, nhu cầu xử lý lỗi và số lượng chunk phải do ứng dụng quyết định.

**Cẩn thận:** `stream.checkError()` cũng flush lại nếu còn mở; trong snippet nó được dùng để kiểm tra lỗi **sau** khi ghi, không phải tuyên bố rằng chỉ có đúng một lần flush. Nếu muốn tránh thêm lần flush do `checkError`, phải chọn API có cách báo lỗi phù hợp hoặc chấp nhận tác động đó.

### 10.3. Ghi dữ liệu nhị phân không dùng API văn bản

Nếu đang tạo một binary file hoặc protocol mà độ chính xác của bytes quan trọng, sử dụng `OutputStream`, `DataOutputStream` hoặc `FileChannel` có thể hợp lý hơn `PrintStream`, vì chúng đưa rõ `IOException` và hỗ trợ kiểm soát layout/endianness thích hợp. `PrintStream` tiện khi cần thêm thao tác in text nhưng không phải thư viện framing binary protocol hay transactional storage.

## 11. Lỗi phổ biến

| Nhầm lẫn / triệu chứng | Giải thích | Cách xử lý |
|---|---|---|
| “Mảng `byte[]` không chứa `'\n'` thì không autoFlush” | `PrintStream` flush sau **ghi mảng**, không cần newline | Dùng `writeBytes`, nhớ autoFlush trigger theo thao tác |
| “Bật autoFlush thì mỗi `write(int)` đều flush” | `write(int)` chỉ autoFlush khi byte là newline | Phân biệt single-byte với array overload |
| “Ghi `byte[]` là ghi text theo charset” | `writeBytes` ghi raw bytes | Mã hóa rõ bằng `String.getBytes(Charset)` khi cần |
| “`print(bytes)` ghi đúng bytes” | `print` không có overload `byte[]` cho raw data | Dùng `writeBytes(bytes)` |
| “`write(byte[])` khác dữ liệu của `writeBytes`” | Cùng viết toàn mảng theo implementation requirements | Chọn theo checked-exception signature |
| “Tắt autoFlush thì không bao giờ flush đến lúc đóng” | Buffer bên dưới có thể đầy, có code tự flush, hoặc `checkError` gây flush | Kiểm soát toàn bộ pipeline |
| “Mảng rỗng không thể gây flush” | Ghi mảng rỗng có thể được xem là thao tác ghi mảng; JDK đã test vẫn flush | Gọi `flush()` rõ ràng khi chỉ muốn flush |
| “`flush()` chắc chắn sync tới disk hoặc gửi thành công qua mạng” | Flush Java không cam kết disk persistence hoặc peer acknowledgment | Dùng API/bảo đảm ở đúng tầng |
| “Không ném `IOException` thì ghi luôn thành công” | `PrintStream` đặt internal error flag | Kiểm tra `checkError()` hoặc dùng API propagate IOException |
| “`checkError()` là getter thuần” | Nó flush nếu chưa đóng | Tránh gọi khi đang đo flush |
| “`PrintWriter` autoFlush giống `PrintStream`” | `PrintWriter` chỉ tự flush trên `println`/`printf`/`format` | Chọn đúng API text/raw |
| “`System.out` luôn có một cấu hình autoFlush cố định ở mọi runtime” | Thiết lập/đích có thể bị thay đổi bởi môi trường | Kiểm tra stream do chính code tạo |
| “Bật autoFlush luôn nhanh hơn vì đẩy dữ liệu sớm” | Flush thường xuyên có thể phá lợi ích batching | Đo với workload thực |

## 12. Checklist khi sử dụng `PrintStream` để ghi mảng

1. Xác định bạn cần **raw byte** hay xuất văn bản. Nếu raw byte, dùng `writeBytes` hoặc `write` đúng overload.
2. Chọn `new PrintStream(output, autoFlush, charset)` và charset rõ ràng khi in văn bản.
3. Ghi nhớ `autoFlush=true` sẽ flush **sau ghi mảng** ngay cả khi không có newline.
4. Phân biệt `write(int)` (newline-trigger) với `write(byte[])` và `writeBytes(byte[])` (array-trigger).
5. Khi cần truyền liên tục nhiều mảng nhỏ, quyết định có nên dùng autoFlush hay batch + manual flush dựa trên latency/throughput.
6. Kiểm tra tầng buffer thực tế, độ đầy buffer và thời điểm dữ liệu xuống sink.
7. Tránh trộn raw bytes với text có charset khác mà không có protocol rõ ràng.
8. Nếu I/O lỗi có ý nghĩa nghiệp vụ, dùng `checkError()` với hiểu biết rằng phương thức này tự flush; khi cần cause hãy dùng stream API có checked IOException.
9. Đừng dùng `flush()` làm bằng chứng fsync/ACK/trạng thái giao dịch.
10. Đóng wrapper chỉ khi sở hữu luồng đích; không vô ý đóng `System.out`/`System.err` dùng chung.
11. Kiểm thử các trường hợp mảng có/không có newline, mảng rỗng, nhiều chunk, autoFlush on/off và luồng đích báo lỗi.
12. Áp dụng API Java 14+ hiện hành, tránh dạy các workaround cũ cho `writeBytes`/`write(byte[])` hoặc quy tắc của `PrintWriter` thay cho `PrintStream`.

## Tài liệu chính thức

- Oracle Java SE 26 API — **PrintStream**: định nghĩa autoFlush, `writeBytes(byte[])`, `write(byte[])`, `write(byte[],off,len)`, `write(int)` và `checkError()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/PrintStream.html
- Oracle Java SE 25 API — **PrintStream** (hành vi vẫn áp dụng trong JDK hiện đại): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PrintStream.html
- Oracle Java SE 17 API — **PrintStream** (mẫu code Java 17+): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html
- Oracle Java SE 25 API — **PrintWriter**, quy tắc autoFlush chỉ ở `println`/`printf`/`format`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PrintWriter.html
- Oracle Java SE 25 API — **BufferedOutputStream**, buffer và `flush`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedOutputStream.html
- Oracle Java SE 25 API — **OutputStream**, `flush` và `close`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStream.html

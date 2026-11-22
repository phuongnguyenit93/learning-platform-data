# `PrintStream.writeBytes`: ghi toàn bộ mảng byte trong Java

## 1. Mục tiêu bài học

Khi làm việc với `java.io.PrintStream`, nhiều lập trình viên quen dùng `print(...)` hoặc `println(...)` để xuất **văn bản**. Tuy nhiên, có lúc dữ liệu đã nằm sẵn trong `byte[]`: một header nhị phân, kết quả của `String.getBytes(...)`, dữ liệu mã hóa hoặc một thông điệp được tạo bởi serializer. Lúc đó ta muốn gửi **đúng các byte**, không chuyển chúng thành các chữ số hoặc mã hóa lại như văn bản.

Từ **Java 14**, `PrintStream` cung cấp phương thức tiện dụng:

```java
public void writeBytes(byte[] buf)
```

Ý nghĩa: **ghi toàn bộ nội dung của mảng `buf` vào stream** theo đúng thứ tự. Không thêm ký tự xuống dòng, không thêm dấu kết thúc mảng và không tự mã hóa byte.

Ví dụ:

```java
byte[] payload = {65, 66, 67};
System.out.writeBytes(payload);
```

Ba byte được gửi đi là `0x41 0x42 0x43`, tương ứng chữ `ABC` trong ASCII/UTF-8. Đây là **đoạn mã minh họa**, không phải chương trình Java hoàn chỉnh. Khi xuất byte nhị phân tùy ý, **không nên ghi thẳng ra terminal** vì có thể chứa ký tự điều khiển hoặc dãy byte không hợp lệ với charset hiển thị.

**Tính hiện hành theo Special Note:** `writeBytes(byte[])` được thêm vào Java 14 và **vẫn là API công khai trong các JDK hiện nay**. Ví dụ chính bên dưới được biên dịch theo **Java 17**, không dùng preview/legacy API.

## 2. Ngữ nghĩa chính xác: toàn bộ mảng, đúng byte

Javadoc của `PrintStream.writeBytes(byte[])` quy định phương thức **tương đương**:

```java
this.write(buf, 0, buf.length);
```

Nghĩa là:

- `buf` là nguồn dữ liệu đầu vào, không phải tên file hoặc chuỗi cần chuyển mã.
- `0` là offset bắt đầu, tính từ phần tử đầu tiên.
- `buf.length` là **số byte** được yêu cầu ghi, không phải số ký tự của chuỗi.
- Với `buf = {1, 2, 3, 4}`, lời gọi gửi đủ bốn byte đó theo thứ tự.
- Với mảng có byte `0x00` hoặc byte âm ở dạng `byte` của Java (ví dụ `(byte) 0xFF`), dữ liệu vẫn được ghi dưới dạng byte gốc.
- Phương thức **không thêm `\n`**, không tự thêm một byte `0x00` và không thêm chiều dài mảng vào đầu payload.
- `buf == null` là lỗi đầu vào, sẽ dẫn tới `NullPointerException`; không xem `null` như một mảng rỗng.
- `new byte[0]` có độ dài bằng 0, nên không cung cấp byte dữ liệu nào để ghi.

**Lưu ý về I/O thực:** một lời gọi `writeBytes` yêu cầu ghi toàn mảng qua `PrintStream`, nhưng điều đó **không có nghĩa** hệ điều hành, thiết bị hoặc server bên kia đã ghi bền vững, xác nhận nhận đủ, hay đồng bộ với bộ nhớ lưu trữ. `writeBytes` không phải giao thức truyền tải có ACK và cũng không phải một transaction.

### Minh họa về byte có giá trị âm

Kiểu nguyên thủy `byte` trong Java là số nguyên có dấu từ -128 đến 127. Ví dụ `(byte) 0xFF` có giá trị số học là `-1`, nhưng **mẫu 8 bit** gửi ra vẫn là `11111111` (`FF` ở hệ hex). Không có bước “chuyển -1 thành các ký tự `-` và `1`”.

```java
byte[] raw = {0x41, 0x00, (byte) 0xFF, 0x0A};
out.writeBytes(raw);
```

Đây là đoạn minh họa với biến `out` có kiểu `PrintStream`. Khi quan sát bằng hex, dữ liệu là:

```text
41 00 ff 0a
```

Byte `0x0A` là mã LF, nhưng `writeBytes` **không quan tâm** rằng nó đại diện dấu xuống dòng; phương thức chỉ chuyển byte sang stream.

## 3. Phân biệt `writeBytes`, `write`, `print` và `println`

| Cách gọi | Dữ liệu đầu vào | Hành vi | Có tự thêm newline? |
| --- | --- | --- | --- |
| `out.writeBytes(bytes)` | `byte[]` | Ghi **toàn bộ byte** thô | Không |
| `out.write(bytes, off, len)` | `byte[]` + vùng chọn | Ghi `len` byte bắt đầu tại `off` | Không |
| `out.write(bytes)` | `byte[]` | Ghi toàn bộ byte thô, nhưng chữ ký phương thức **khai báo `throws IOException`** | Không |
| `out.write(intValue)` | `int` | Ghi **một byte** là 8 bit thấp của số | Không |
| `out.print(intValue)` | `int` | Chuyển số thành **ký tự thập phân** rồi mã hóa | Không |
| `out.print("text")` | `String` | Mã hóa ký tự theo charset được cấu hình của `PrintStream` | Không |
| `out.println("text")` | `String` | Mã hóa text rồi thêm **dấu kết thúc dòng của nền tảng** | Có |

Đối chiếu với giá trị số `65`:

```java
out.write(65);  // Một byte: 0x41, tương ứng 'A' theo ASCII.
out.print(65);  // Hai byte trong UTF-8/ASCII: 0x36 0x35, tức "65".
```

Nếu mã xử lý giao thức yêu cầu byte `0x41` mà ta vô tình `print(65)`, dữ liệu nhận được sẽ **khác hoàn toàn**.

### Sự khác biệt ít được chú ý: checked exception ở overload một đối số

Trên Java 17+, `PrintStream.write(byte[])` vẫn có khai báo `throws IOException` trong chữ ký API, mặc dù **implementation `PrintStream` thông thường bắt lỗi I/O nội bộ và đánh dấu lỗi để kiểm tra bằng `checkError()`**. `writeBytes(byte[])` được tạo như một cách ghi toàn mảng tiện lợi **không phải bắt hoặc khai báo checked `IOException`**.

```java
void send(PrintStream out, byte[] bytes) {
    out.writeBytes(bytes);                // Không đòi catch IOException.
    out.write(bytes, 0, bytes.length);    // Cũng không đòi catch IOException.

    // out.write(bytes);                  // Chữ ký đòi xử lý IOException.
}
```

Đây là **phương thức minh họa**, cần đặt trong một lớp hợp lệ và import `PrintStream`. Phần comment chỉ so sánh chữ ký compile-time, không có nghĩa hai overload luôn khác dữ liệu đầu ra.

**Tóm lại:** `writeBytes(bytes)` là cách gọn, rõ mục đích khi phải ghi **toàn bộ mảng byte** bằng `PrintStream` mà không muốn viết `write(bytes, 0, bytes.length)`.

### Nếu chỉ muốn ghi một phần của mảng

`writeBytes` **không có** tham số offset/length. Muốn ghi phần tử từ chỉ số `start` với `count` byte, dùng:

```java
out.write(bytes, start, count);
```

Cần đảm bảo `start >= 0`, `count >= 0` và `count <= bytes.length - start`. Nếu không, `IndexOutOfBoundsException` có thể xảy ra. Không tạo một mảng copy mới chỉ để dùng `writeBytes` nếu việc ghi theo khoảng bằng `write(...)` trực tiếp phù hợp hơn.

## 4. Charset: `writeBytes` không tự mã hóa text

Trong `PrintStream`, có thể chỉ định charset khi tạo đối tượng:

```java
new PrintStream(destination, true, StandardCharsets.UTF_8)
```

Ý nghĩa: những phương thức **xuất ký tự** như `print(String)` sẽ dùng UTF-8. Nhưng `writeBytes(byte[])` **bỏ qua mọi bước chuyển ký tự thành byte** vì đầu vào đã là byte.

Ví dụ:

```java
String text = "é";
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
out.writeBytes(utf8);
```

Với UTF-8, ký tự `é` được biểu diễn bằng hai byte `c3 a9`. `writeBytes` ghi chính xác hai byte đó.

**Cách đúng khi muốn chuyển String thành byte:** gọi `getBytes(StandardCharsets.UTF_8)` một cách tường minh. Tránh `getBytes()` không chỉ định charset nếu định dạng file/giao thức yêu cầu UTF-8 độc lập với cấu hình môi trường.

### Một byte không phải lúc nào cũng là một ký tự

Ví dụ mảng:

```java
byte[] bytes = {0x41, 0x00, (byte) 0xFF};
```

gồm ba byte, nhưng **không phải một chuỗi UTF-8 hợp lệ hoàn chỉnh** vì `0xFF` không phải byte hợp lệ trong UTF-8. Nếu cố giải mã toàn bộ mảng để hiển thị văn bản, decoder có thể thay byte lỗi bằng ký tự replacement.

Vì vậy, **không kiểm thử chính xác dữ liệu nhị phân bằng cách `new String(bytes, UTF_8)` rồi so lại chuỗi**. Hãy so sánh byte bằng `Arrays.equals`, dùng `HexFormat`, hoặc đối chiếu checksum khi phù hợp.

### Dấu kết thúc dòng

`writeBytes(new byte[] {0x0A})` ghi **một byte LF**. `println()` tạo dấu kết thúc dòng theo nền tảng và xử lý qua cơ chế text của stream. Trên Windows, hai cách có thể tạo chuỗi byte khác nhau. Nếu giao thức quy định chính xác `CRLF` (`0d 0a`), gửi rõ byte tương ứng hoặc dùng encoder/serializer của giao thức, không dựa vào `println()`.

## 5. Ví dụ Java 17+ hoàn chỉnh: byte thô, UTF-8, autoflush và lỗi I/O

Chương trình dùng `ByteArrayOutputStream` làm đích trong bộ nhớ, vì vậy không phát ra các byte nhị phân khó đọc trực tiếp ra terminal. `HexFormat` là API có từ Java 17 giúp hiển thị chính xác các byte đã ghi.

Lưu **`PrintStreamWriteBytesDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class PrintStreamWriteBytesDemo {
    static final class CountingOutputStream extends OutputStream {
        int flushCount;
        @Override public void write(int b) { }
        @Override public void flush() { flushCount++; }
    }

    static final class BrokenOutputStream extends OutputStream {
        @Override public void write(int b) throws IOException {
            throw new IOException("simulated failure");
        }
    }

    public static void main(String[] args) {
        byte[] prefix = {0x41, 0x00, (byte) 0xff, 0x0a};
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (PrintStream output =
                new PrintStream(sink, true, StandardCharsets.UTF_8)) {
            output.writeBytes(prefix);
            output.writeBytes("é".getBytes(StandardCharsets.UTF_8));
            output.print("!");
            System.out.println("writeError=" + output.checkError());
        }

        byte[] written = sink.toByteArray();
        System.out.println("byteCount=" + written.length);
        System.out.println("hex=" + HexFormat.of().formatHex(written));
        System.out.println("prefixUnchanged=" +
                Arrays.equals(prefix, Arrays.copyOf(written, prefix.length)));
        System.out.println("decodedSuffix=" +
                new String(Arrays.copyOfRange(written, prefix.length,
                        written.length), StandardCharsets.UTF_8));

        CountingOutputStream counting = new CountingOutputStream();
        try (PrintStream output =
                new PrintStream(counting, true, StandardCharsets.UTF_8)) {
            output.writeBytes(new byte[] {1, 2, 3});
            System.out.println("autoFlushed=" + (counting.flushCount > 0));
        }

        try (PrintStream broken =
                new PrintStream(new BrokenOutputStream(), false,
                                StandardCharsets.UTF_8)) {
            broken.writeBytes(new byte[] {42});
            System.out.println("errorFlag=" + broken.checkError());
        }
    }
}
```

**Cách biên dịch và chạy:**

```bash
javac --release 17 -encoding UTF-8 PrintStreamWriteBytesDemo.java
java PrintStreamWriteBytesDemo
```

**Đầu ra đã kiểm chứng trên OpenJDK 24 khi biên dịch với `--release 17`:**

```text
writeError=false
byteCount=7
hex=4100ff0ac3a921
prefixUnchanged=true
decodedSuffix=é!
autoFlushed=true
errorFlag=true
```

Máy console không hiển thị Unicode tốt có thể thể hiện chữ `é` khác đi; **dòng hex vẫn là bằng chứng độc lập với charset terminal**.

### Giải thích từng dòng

1. `writeError=false`: `PrintStream` ghi vào `ByteArrayOutputStream` mà không phát hiện lỗi I/O.
2. `byteCount=7`: mảng đầu gồm **4 byte**, ký tự `é` trong UTF-8 gồm **2 byte**, còn `print("!")` ghi **1 byte**.
3. `hex=4100ff0ac3a921`: chính xác `41 00 ff 0a c3 a9 21`. Các byte `00` và `ff` không bị xóa, đổi thành chữ số hay bị mã hóa lại.
4. `prefixUnchanged=true`: `Arrays.equals` xác nhận 4 byte đầu đúng bằng payload gốc.
5. `decodedSuffix=é!`: chỉ giải mã **phần suffix đã biết hợp lệ UTF-8**; không giải mã prefix có `ff`.
6. `autoFlushed=true`: với `autoFlush=true`, ghi mảng bằng `writeBytes` kích hoạt `flush()` trên output stream bên dưới.
7. `errorFlag=true`: output stream giả lập ném `IOException`; `PrintStream` bắt lỗi I/O trong thao tác ghi, và `checkError()` phản ánh trạng thái lỗi.

Đây là chương trình **runnable đầy đủ**, không cần dependency ngoài JDK. `BrokenOutputStream` được tạo chỉ để thử **đường đi lỗi**; không phải một nguồn I/O thực cần truy cập.

### Vì sao dùng `HexFormat`?

`HexFormat.of().formatHex(byte[])` cho ra biểu diễn hex trực tiếp của dữ liệu. Java 17 đã có `java.util.HexFormat` nên không cần thư viện bên ngoài hoặc phương pháp cũ tự nối chuỗi hex bằng vòng lặp. Nếu ứng dụng nhắm mục tiêu một phiên bản Java thấp hơn 17, cần chọn cách hiển thị khác; **ví dụ này cố ý thống nhất Java 17+**.

### Vì sao `CountingOutputStream.write(int)` không lưu byte?

Lớp phụ này chỉ để kiểm tra hành vi **flush**, không kiểm tra payload. Vì vậy `write(int)` được override rỗng. Nếu muốn kiểm tra **cả byte được ghi lẫn flush**, hãy viết một `OutputStream` bọc `ByteArrayOutputStream` và forward cả `write(...)` lẫn `flush()`, sau đó kiểm tra byte và số lần flush.

## 6. Auto-flush không đồng nghĩa ghi bền vững

Constructor sau bật tự động flush:

```java
PrintStream out = new PrintStream(destination, true, StandardCharsets.UTF_8);
```

Javadoc quy định: khi auto-flush được bật, `writeBytes` **sẽ gọi `flush`** sau khi ghi mảng. Phần này khác với `BufferedOutputStream` thông thường mà bạn phải quản lý flush theo chính sách buffering.

**Nhưng có ba mức khác nhau:**

| Mức | Cơ chế | Điều nó không đảm bảo |
| --- | --- | --- |
| `writeBytes(bytes)` | Chuyển các byte vào `PrintStream` và stream đích | Không đảm bảo đích đã lưu bền vững |
| `flush()` hoặc autoFlush | Đẩy dữ liệu đang buffer xuống các tầng bên dưới theo hợp đồng flush | Không tự bảo đảm `fsync`, giao dịch, hay receiver đã xác nhận |
| Đồng bộ/bảo vệ ở tầng file/giao thức | Ví dụ file channel force, giao thức có ACK, ứng dụng có transaction | Cần thiết kế và xử lý lỗi riêng |

Nếu `autoFlush=false`, việc ghi bằng `writeBytes` **không tự yêu cầu flush theo cờ**. Khi kết thúc một đơn vị công việc có ý nghĩa, có thể gọi `out.flush()` hoặc `close()` (nếu stream thuộc quyền sở hữu của bạn). Đối với `System.out` hay `System.err` dùng chung của tiến trình, **không tùy tiện gọi `close()`** vì sẽ ảnh hưởng các phần khác.

### Có nên bật autoFlush cho mọi lần ghi?

Không nhất thiết. Việc flush mỗi lần `writeBytes` có thể làm giảm hiệu quả gom dữ liệu trong ứng dụng ghi lượng lớn byte. Nếu cần throughput cao, có thể dùng một `BufferedOutputStream` hoặc OutputStream phù hợp, ghi theo khối, flush ở điểm hợp lý. Nếu yêu cầu ghi ra bên ngoài kịp thời, `autoFlush=true` dễ quan sát nhưng vẫn phải đánh đổi chi phí.

**Chú ý:** `writeBytes` gọi `flush` theo cấu hình **ngay cả khi trong mảng không có ký tự newline**. Không phải đợi `\n`. Ngược lại, trong nhiều trường hợp `print("Hello")` sẽ không yêu cầu auto-flush chỉ vì đã in text không có newline.

## 7. Lỗi I/O: `checkError()` thay vì chỉ trông đợi ngoại lệ

Khác `OutputStream` thông thường, `PrintStream` được thiết kế để **không ném checked `IOException` cho các phép in/ghi thông dụng**; thay vào đó nó đặt một **error flag** bên trong khi gặp lỗi I/O.

```java
out.writeBytes(bytes);
if (out.checkError()) {
    throw new IllegalStateException("Output failed");
}
```

Đây là một đoạn **mã minh họa** với biến `out` và `bytes` đã khai báo, thích hợp khi ứng dụng muốn phát hiện lỗi sau khi ghi.

**`checkError()` có thể gọi flush khi stream chưa đóng** rồi trả trạng thái lỗi. Một khi lỗi I/O đã xảy ra, `checkError()` thường tiếp tục trả true cho tới khi trạng thái được xóa bởi cơ chế được lớp cung cấp; đừng mặc nhiên coi nó chỉ nói về lời gọi `writeBytes` gần nhất.

### Các lỗi khác vẫn có thể xuất hiện trực tiếp

Không phải mọi sự cố đều trở thành `checkError()==true`:

- `writeBytes(null)` có thể ném `NullPointerException` do đầu vào null.
- Nếu gọi `write(byte[],off,len)` với khoảng không hợp lệ, có thể ném `IndexOutOfBoundsException`.
- Sự cố runtime khác hoặc lỗi cấu hình tài nguyên không nhất thiết là `IOException` bị `PrintStream` nuốt.
- Nếu đã đóng stream, không nên tiếp tục ghi; việc ghi có thể đánh dấu lỗi hoặc thất bại theo trạng thái stream.

Nếu phải **xác nhận chính xác việc ghi đã thành công** ở tầng file/protocol, nhất là khi xử lý dữ liệu quan trọng, có thể **ưu tiên `OutputStream`/`FileChannel`** với cơ chế lỗi rõ ràng thay vì dùng `PrintStream` chỉ vì API ngắn. Trong code kiểm toán, sự khác nhau giữa “lời gọi không ném ngoại lệ” và “dữ liệu thực sự đến đích” rất quan trọng.

### Ví dụ ghi vào file: chỉ định file đích và charset

```java
Path file = Path.of("payload.bin");
try (PrintStream out = new PrintStream(
        Files.newOutputStream(file), false, StandardCharsets.UTF_8)) {
    out.writeBytes(new byte[] {0x01, 0x02, 0x03});
    if (out.checkError()) {
        throw new IOException("Cannot write payload");
    }
}
```

Đây là **đoạn mã minh họa**, cần đặt trong phương thức có xử lý/khai báo `IOException` và import `Path`, `Files`, `PrintStream`, `StandardCharsets`. Mã dùng `try-with-resources` để đóng **luồng do chương trình sở hữu**. Kiểm tra `checkError` không thay thế kiểm tra lỗi khi mở file và chính sách độ bền dữ liệu.

Nếu mục tiêu duy nhất là ghi byte vào file, `Files.write(file, byte[])` hoặc `Files.newOutputStream(file).write(bytes)` thường trực tiếp hơn và báo lỗi `IOException` theo cách dễ xử lý. `PrintStream.writeBytes` đặc biệt tiện khi đã có sẵn một `PrintStream` và muốn ghi **toàn bộ mảng**.

## 8. Trường hợp sử dụng phù hợp và không phù hợp

### Phù hợp

- Đã có `PrintStream` trong API và cần ghi một payload `byte[]` đã được chuẩn hóa.
- Ghi một phần nhị phân vào file test/buffer để xác minh định dạng bằng hex.
- Ghi dữ liệu UTF-8 **đã được mã hóa sẵn**, khi muốn giữ chính xác byte encoding đó.
- Viết đoạn kiểm thử so sánh `writeBytes` với `write(byte[],0,len)`.
- Xuất header hoặc marker nhị phân vào luồng ghi có kiểm soát.

### Cần thận trọng

- Gửi dữ liệu nhị phân chưa kiểm soát ra `System.out`: terminal có thể nhận ký tự điều khiển hoặc byte không đúng charset.
- Ghép text của `print` và byte gốc của `writeBytes` mà **không định nghĩa rõ format/charset**: receiver khó phân tích và có thể bị lệch ranh giới.
- Viết giao thức mạng cần length-prefix, framing, checksum, retry hoặc ACK: `writeBytes` không tự làm những việc này.
- Ghi dữ liệu quan trọng cần báo lỗi I/O ngay: `PrintStream` thường chuyển lỗi sang `checkError`; `OutputStream` có thể phù hợp hơn.
- Đọc/ghi dữ liệu có nguồn không tin cậy: giới hạn kích thước, xác minh format, tránh đưa tùy ý byte điều khiển vào log/console.

### Khi làm việc với chuỗi

Nếu cần ghi text, `print(text)` thường rõ mục đích hơn `writeBytes(text.getBytes(...))`, miễn charset của `PrintStream` được cấu hình đúng. Nếu yêu cầu **UTF-8 độc lập với máy chạy**, dùng constructor có `StandardCharsets.UTF_8` thay vì ngầm dựa vào charset mặc định.

Khi đã có bộ mã hóa chuẩn ở tầng khác, `writeBytes(encoded)` phù hợp vì **không mã hóa lại**, không làm thay đổi payload.

## 9. Những lỗi thường gặp

| Sai lầm | Điều xảy ra | Cách sửa |
| --- | --- | --- |
| Nghĩ `writeBytes` mới có trong Java 17 | Tính năng có từ Java 14, vẫn hỗ trợ | Dùng Java 14+; ví dụ bài nhắm Java 17+ |
| Gọi `print(bytes)` thay vì `writeBytes(bytes)` | Có thể in biểu diễn đối tượng mảng `[B@...`, không phải payload | Dùng `writeBytes` hoặc `write` |
| Dùng `print(65)` để ghi byte `0x41` | Gửi ký tự `"65"` thay vì một byte `A` | Dùng `write(65)` hoặc `writeBytes(new byte[]{65})` |
| Tưởng `writeBytes` tự chuyển `String` sang UTF-8 | Phương thức nhận `byte[]`, không mã hóa | `text.getBytes(StandardCharsets.UTF_8)` trước |
| Cho rằng `buf.length` là số ký tự văn bản | UTF-8 có thể nhiều byte trên một ký tự | Phân biệt ký tự, code point và byte length |
| Tưởng `writeBytes` tự thêm dòng mới | Dữ liệu bị ghép sát với phần tiếp theo | Thêm byte newline **có chủ đích** theo giao thức |
| Tưởng `autoFlush=true` chỉ flush nếu mảng có LF | Ghi mảng cũng kích hoạt flush | Hiểu đúng tài liệu `PrintStream.writeBytes` |
| Đồng nhất `flush` với ghi bền vững lên đĩa | Thiếu fsync/giao dịch | Thiết kế durability ở tầng tương ứng |
| Không kiểm tra `checkError()` | Có thể bỏ qua lỗi I/O thực | Kiểm tra error flag hoặc dùng stream báo lỗi tường minh |
| Gọi `writeBytes(null)` và mong không có tác dụng | `NullPointerException` | Kiểm tra input, phân biệt null và mảng rỗng |
| Gọi `writeBytes` khi chỉ cần một đoạn mảng | Bắt buộc ghi toàn bộ mảng | Dùng `write(bytes,offset,length)` |
| Dùng `new String(binary,UTF_8)` để kiểm tra byte | Byte không hợp lệ bị thay đổi khi decode | Dùng `Arrays.equals` hoặc `HexFormat` |
| Dùng `System.out.writeBytes` với binary tùy ý | Terminal bị lỗi hiển thị hoặc nhận control bytes | Ghi vào file/buffer hoặc hiển thị hex |
| Đóng `System.out` trong try-with-resources | Đóng stdout của tiến trình | Chỉ đóng stream do code sở hữu |
| So sánh `out.write(byte[])` và `out.writeBytes(byte[])` theo checked exception không chính xác | Có thể gặp lỗi compile do `throws IOException` | `writeBytes` không yêu cầu catch checked I/O |
| Nghĩ viết toàn bộ mảng đảm bảo reader nhận đủ một “message” | Stream không tự có ranh giới thông điệp | Tự thiết kế framing/protocol |
| Ghi payload lớn từng byte bằng vòng lặp | Tốn lời gọi, giảm hiệu suất | Ghi từng khối `byte[]` hoặc `OutputStream` phù hợp |

## 10. Bài tập có đáp án

**Câu 1.** `PrintStream.writeBytes(byte[])` được giới thiệu trong Java nào và có còn dùng được trên Java 17+ không?  
**Đáp án:** Có từ **Java 14**, vẫn là API công khai hiện hành trong Java 17+.

**Câu 2.** `writeBytes(new byte[]{65, 66})` ghi bao nhiêu byte và giá trị là gì?  
**Đáp án:** Hai byte, `41 42` ở hex. Không thêm `\n` hay dấu kết thúc.

**Câu 3.** `print(65)` và `write(65)` khác gì?  
**Đáp án:** `print(65)` chuyển số thành hai ký tự `"65"`; `write(65)` ghi **một byte `0x41`**.

**Câu 4.** `writeBytes(bytes)` tương đương phép gọi nào?  
**Đáp án:** `write(bytes, 0, bytes.length)`.

**Câu 5.** `writeBytes` có chịu tác động bởi charset UTF-8 truyền trong constructor `PrintStream` không?  
**Đáp án:** **Không mã hóa lại**. Charset tác động lên phép xuất văn bản; `writeBytes` gửi byte đã có. Muốn bytes UTF-8, gọi `text.getBytes(StandardCharsets.UTF_8)`.

**Câu 6.** Mảng `{0x41, 0x00, (byte)0xFF}` có phải ba ký tự UTF-8 hợp lệ không?  
**Đáp án:** Không. `0xFF` không hợp lệ trong UTF-8. Mảng vẫn là 3 byte hợp lệ ở cấp byte stream.

**Câu 7.** Nếu bật `autoFlush`, `writeBytes` có thể kích hoạt flush dù không có `\n` không?  
**Đáp án:** Có. Javadoc nêu `flush` được gọi khi ghi mảng với auto-flush bật.

**Câu 8.** `writeBytes` có checked `IOException` trong chữ ký không? Có nghĩa là mọi lỗi ghi đều bị bỏ qua?  
**Đáp án:** Không khai báo checked `IOException`. `PrintStream` ghi nhận lỗi I/O qua error flag để kiểm tra bằng `checkError()`; **không** có nghĩa lỗi không tồn tại.

**Câu 9.** Muốn ghi phần tử `bytes[4]` đến `bytes[7]` thì dùng gì?  
**Đáp án:** `out.write(bytes, 4, 4)` — 4 byte bắt đầu tại offset 4, sau khi kiểm tra kích thước mảng.

**Câu 10.** Vì sao không nên decode cả một payload nhị phân thành String để kiểm tra?  
**Đáp án:** Dữ liệu có thể không phải text hợp lệ, decoder có thể thay byte lỗi. Cần so sánh bytes hoặc dạng hex.

**Câu 11.** `writeBytes` có phải lựa chọn tốt nhất để tạo giao thức mạng có message framing và ACK không?  
**Đáp án:** Nó chỉ viết byte thô. Nếu giao thức đòi độ dài, checksum, xác nhận và retry, cần tầng xử lý/serialization chuyên biệt.

## 11. Ghi nhớ và nguồn chính thức

**Quy tắc một dòng:** `PrintStream.writeBytes(buf)` **ghi toàn bộ `byte[]` như đã có**, tương đương `write(buf,0,buf.length)`, không tự mã hóa, không thêm newline, và nếu auto-flush bật thì sẽ flush.

- **Text:** dùng `print/println` với charset được chọn rõ ràng.
- **Byte thô:** dùng `writeBytes` (toàn mảng) hoặc `write(...,off,len)` (một phần).
- **I/O:** hiểu `checkError` của `PrintStream`; không nhầm flush với durability.
- **Kiểm tra:** ưu tiên byte equality và hex output; đừng ép payload binary thành chuỗi.

Tài liệu chính thức, hiện vẫn áp dụng:

- [Oracle Java SE 17 — `PrintStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html): `writeBytes(byte[])` (since 14), `write` overloads, `print`, `checkError` và autoflush.
- [Oracle Java SE 21 — `PrintStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintStream.html): API và ngữ nghĩa còn hiệu lực.
- [Oracle Java SE 17 — `OutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): ghi byte, flush, close và checked `IOException`.
- [Oracle Java SE 17 — `ByteArrayOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html): buffer byte trong bộ nhớ, lưu/so sánh dữ liệu.
- [Oracle Java SE 17 — `HexFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): trình bày byte dưới dạng hex.
- [Oracle Java SE 17 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): mã hóa UTF-8 tường minh.

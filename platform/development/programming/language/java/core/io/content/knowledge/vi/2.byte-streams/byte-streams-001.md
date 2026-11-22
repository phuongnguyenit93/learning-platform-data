# InputStream và OutputStream trong Java: đọc và ghi luồng byte

## 1. Bức tranh tổng thể

Trong Java I/O, **luồng byte (byte stream)** là cách đọc một chuỗi byte từ **nguồn** hoặc ghi byte đến **đích** mà không buộc chương trình biết nguồn/đích được hiện thực như thế nào. Hai lớp trừu tượng cốt lõi trong gói `java.io` là:

- **`InputStream`**: đọc byte từ nguồn vào chương trình.
- **`OutputStream`**: ghi byte từ chương trình ra đích.

```text
Nguồn (tệp / bộ nhớ / kết nối ...)
              │
              ▼
         InputStream
              │ đọc byte
              ▼
          Ứng dụng
              │ ghi byte
              ▼
         OutputStream
              │
              ▼
Đích (tệp / bộ nhớ / kết nối ...)
```

Đây là **hai lớp trừu tượng**, không phải hai lớp dành riêng cho tệp. Cùng một vòng lặp sao chép byte có thể làm việc với `FileInputStream`, `ByteArrayInputStream`, hoặc một luồng được cung cấp từ API khác. Những đối tượng ấy khác nguồn dữ liệu, nhưng có chung hợp đồng `InputStream`. Tương tự với đầu ra.

**Khi nào chọn byte stream?** Khi cần giữ nguyên byte: sao chép tệp, tải dữ liệu nhị phân, xử lý ảnh, nén, định dạng nhị phân, hoặc giao thức truyền byte. Nếu mục tiêu là xử lý **ký tự/văn bản** theo encoding, ưu tiên `Reader`/`Writer` hoặc API văn bản với `Charset` xác định; byte stream tự nó không giải mã UTF-8, UTF-16 hay encoding nào.

### Một số thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Nguồn (source) | Nơi cung cấp byte cho `InputStream` |
| Đích (sink) | Nơi tiếp nhận byte từ `OutputStream` |
| EOF (end of stream) | Luồng đầu vào đã hết dữ liệu; `read()` trả `-1` |
| Buffer | Vùng nhớ tạm dùng để đọc/ghi theo lô, giảm số lần gọi I/O |
| Wrapper/decorator | Luồng bọc luồng khác để bổ sung hành vi như buffering hoặc đọc kiểu dữ liệu |

Một luồng có thể **chặn luồng thực thi (blocking)** khi chưa có dữ liệu đọc hoặc khi việc ghi phải chờ thiết bị/đích. Không nên coi mỗi lời gọi `read` hoặc `write` là một “gói tin” hay một bản ghi ứng dụng.

## 2. InputStream: hợp đồng đọc byte

`InputStream` là lớp trừu tượng. Phương thức nền tảng `read()` trả một `int` để biểu diễn **một byte không dấu từ 0 đến 255**, hoặc `-1` nếu đã hết luồng. Kiểu trả về là `int` vì byte `0xFF` cũng là dữ liệu hợp lệ (giá trị 255) và phải phân biệt được với `-1` báo EOF.

```java
int value = in.read();
if (value == -1) {
    // Đã đến cuối luồng.
} else {
    // Một byte hợp lệ: 0..255.
}
```

Trong đoạn này, `in` là một `InputStream` đã được mở; đây là **đoạn minh họa**, chưa phải chương trình chạy độc lập.

Các thao tác đọc thường gặp:

| Phương thức | Hành vi chính |
| --- | --- |
| `int read()` | Đọc tối đa một byte; trả `0..255` hoặc `-1` |
| `int read(byte[] b)` | Đọc vào mảng; trả số byte đọc được hoặc `-1` |
| `int read(byte[] b, int off, int len)` | Đọc vào `b[off .. off+len)`; trả số byte thực nhận hoặc `-1` |
| `byte[] readNBytes(int len)` | Cố đọc tối đa `len` byte; mảng trả về có thể ngắn hơn khi gặp EOF |
| `int readNBytes(byte[] b, int off, int len)` | Cố đọc đủ `len` byte, dừng khi EOF hoặc lỗi; trả số byte đã đọc |
| `byte[] readAllBytes()` | Đọc tất cả byte còn lại vào RAM; chỉ nên dùng khi kích thước được kiểm soát |
| `long transferTo(OutputStream out)` | Chuyển các byte còn lại sang luồng đích; trả số byte đã chuyển |
| `long skip(long n)` | Yêu cầu bỏ qua tối đa `n` byte; có thể bỏ qua ít hơn |
| `void skipNBytes(long n)` | Bỏ qua đúng `n` byte hoặc ném ngoại lệ khi không thể |
| `int available()` | Ước lượng lượng byte có thể đọc ngay mà không chặn; **không phải tổng kích thước luồng** |
| `boolean markSupported()`, `mark(int)`, `reset()` | Hỗ trợ đánh dấu/quay lại **nếu** implementation cho phép |
| `void close()` | Đóng luồng và giải phóng tài nguyên liên quan |

Hầu hết hoạt động I/O có thể ném `IOException`. Với `read(b, off, len)`, số byte thực nhận **không nhất thiết bằng `len`**; chẳng hạn yêu cầu 8192 byte có thể chỉ nhận 300 byte. Chỉ vùng `b[off .. off+soByteDoc)` có dữ liệu mới của lần đọc. Với `len == 0`, kết quả là `0`.

### Vòng lặp đọc đúng

```java
byte[] buffer = new byte[8192];
int count;
while ((count = in.read(buffer)) != -1) {
    // Chỉ xử lý buffer[0] đến buffer[count - 1].
}
```

Đây là **mẫu mã nằm trong ngữ cảnh** đã có `InputStream in`. Điều kiện dựa vào kết quả `read`, không dựa vào `available()` và cũng không yêu cầu phải đọc đầy mảng. Với bộ đệm có độ dài dương, `InputStream` chuẩn thường đợi để nhận ít nhất một byte, EOF hoặc lỗi.

## 3. OutputStream: hợp đồng ghi byte

`OutputStream` cũng là lớp trừu tượng. Các phương thức thông dụng:

| Phương thức | Hành vi chính |
| --- | --- |
| `void write(int b)` | Ghi **8 bit thấp** của `b` làm một byte |
| `void write(byte[] b)` | Ghi toàn bộ byte trong mảng |
| `void write(byte[] b, int off, int len)` | Ghi đúng `len` byte bắt đầu ở `off` |
| `void flush()` | Yêu cầu đẩy dữ liệu được giữ trong các bộ đệm của luồng xuống tầng đích |
| `void close()` | Đóng luồng; implementation có thể flush trước khi giải phóng tài nguyên |

Khác `InputStream.read(...)`, `OutputStream.write(...)` trả về `void`; khi lời gọi hoàn tất bình thường, nó được kỳ vọng đã xử lý số byte yêu cầu theo hợp đồng của luồng. Nếu không ghi được, thông thường sẽ có `IOException`. Không có giá trị trả về “đã ghi một phần” để người gọi tiếp tục ở offset khác.

Ví dụ `out.write(0x1FF)` ghi một byte `0xFF` vì chỉ lấy tám bit thấp. Ví dụ `out.write(buffer, 0, count)` chỉ ghi số byte thật sự đọc ở lượt hiện tại.

**`flush()` khác `close()`:** `flush` hữu ích khi muốn dữ liệu đã ghi qua `BufferedOutputStream` được chuyển đến luồng bên dưới trong khi vẫn tiếp tục sử dụng luồng. `close` kết thúc vòng đời và giải phóng tài nguyên. `flush` **không bảo đảm dữ liệu đã được đồng bộ xuống thiết bị lưu trữ bền vững**; điều đó còn phụ thuộc hệ điều hành và cơ chế lưu trữ.

## 4. Ví dụ 1: nhận biết byte 255 và sao chép trong bộ nhớ

Chương trình độc lập dưới đây dùng `ByteArrayInputStream` làm nguồn và `ByteArrayOutputStream` làm đích. Nó minh họa đồng thời ba ý: `read()` trả `int`, EOF là `-1`, và luồng byte giữ nguyên dữ liệu nhị phân.

**Tệp `ByteBasics.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;
import java.util.StringJoiner;

public class ByteBasics {
    public static void main(String[] args) throws IOException {
        byte[] payload = {0, 65, (byte) 0xFF};
        StringJoiner numbers = new StringJoiner(", ");

        try (InputStream in = new ByteArrayInputStream(payload);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {

            int value;
            while ((value = in.read()) != -1) {
                numbers.add(Integer.toString(value));
                out.write(value);
            }

            System.out.println("read(): " + numbers);
            System.out.println(
                    "same bytes: " + Arrays.equals(payload, out.toByteArray()));
        }
    }
}
```

Chạy với Java 17 trở lên:

```bash
javac ByteBasics.java
java ByteBasics
```

**Stdout chính xác:**

```text
read(): 0, 65, 255
same bytes: true
```

Tại sao `(byte) 0xFF` in ra 255 khi đọc? Trong mảng Java, `byte` có dấu nên `(byte) 0xFF` có giá trị số `-1`. Nhưng `InputStream.read()` trả dữ liệu byte đó dưới dạng `int` không dấu `255`. Nếu kiểm tra `byte value == -1` để phát hiện EOF, ta có thể nhầm dữ liệu hợp lệ `0xFF` với kết thúc luồng. **Luôn giữ kết quả `read()` ở kiểu `int` cho đến khi đã kiểm tra `-1`.**

`ByteArrayOutputStream.toByteArray()` tạo bản sao byte đã ghi. Với dữ liệu nằm hoàn toàn trong bộ nhớ, ví dụ này không cần đụng tới hệ thống tệp; `try-with-resources` vẫn thể hiện thói quen quản lý luồng thống nhất.

## 5. Ví dụ 2: sao chép tệp nhị phân bằng buffer

Khi làm việc với tệp, ta có thể mở luồng qua `Files.newInputStream(Path)` và `Files.newOutputStream(Path)` thuộc `java.nio.file`. Cả hai trả về đúng kiểu trừu tượng `InputStream`/`OutputStream` nên thuật toán sao chép độc lập với cách mở tệp. Đệm 8192 byte giúp tránh việc gọi I/O ở tầng ngoài từng byte một.

**Tệp `CopyBytes.java`:**

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyBytes {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("Usage: java CopyBytes <source> <target>");
            return;
        }

        Path source = Path.of(args[0]).toAbsolutePath().normalize();
        Path target = Path.of(args[1]).toAbsolutePath().normalize();

        if (source.equals(target)
                || (Files.exists(target) && Files.isSameFile(source, target))) {
            throw new IllegalArgumentException(
                    "Source and target must be different files");
        }

        try (InputStream in =
                     new BufferedInputStream(Files.newInputStream(source));
             OutputStream out =
                     new BufferedOutputStream(Files.newOutputStream(target))) {

            byte[] buffer = new byte[8192];
            int count;
            while ((count = in.read(buffer)) != -1) {
                out.write(buffer, 0, count);
            }
        }

        System.out.println("Copied bytes: " + Files.size(target));
    }
}
```

Biên dịch và chạy:

```bash
javac CopyBytes.java
java CopyBytes input.bin output.bin
```

Tệp `input.bin` cần tồn tại; `output.bin` sẽ được tạo nếu chưa có, hoặc bị **ghi đè nội dung** nếu đã có. Dòng stdout là `Copied bytes: N` với `N` bằng kích thước đầu ra tính theo byte; `N` tùy thuộc tệp đầu vào nên không gán một kết quả cố định. Các tên `input.bin`/`output.bin` có thể thay bằng đường dẫn thật.

Phân tích theo từng thao tác:

1. **Mở nguồn và đích:** `Files.newInputStream(source)` đọc từ tệp; `Files.newOutputStream(target)` mặc định tạo tệp khi thiếu và ghi đè (truncate) khi tệp tồn tại.
2. **Bọc buffer:** `BufferedInputStream`/`BufferedOutputStream` bổ sung đệm nội bộ. Mảng `buffer` trong chương trình vẫn có ý nghĩa rõ ràng: gom nhiều byte cho mỗi lượt xử lý.
3. **Đọc rồi ghi:** `count` là số byte hợp lệ của lần đọc. `out.write(buffer, 0, count)` không phát tán byte cũ còn lại trong mảng.
4. **Tự động đóng:** `try-with-resources` đóng `out` rồi `in` theo thứ tự ngược lúc khai báo, kể cả khi phát sinh ngoại lệ. Khi đóng `BufferedOutputStream`, dữ liệu đệm còn lại được chuyển xuống luồng dưới.
5. **Kiểm tra kết quả:** chương trình in kích thước đầu ra. Muốn xác nhận byte giống hệt, có thể so sánh byte hoặc checksum; kích thước bằng nhau **chưa chứng minh** nội dung bằng nhau.

Kiểm tra `Files.isSameFile` nếu đích tồn tại nhằm tránh mở đích trỏ vào chính nguồn và làm mất dữ liệu. Với đường dẫn bí danh phức tạp, kiểm tra trước không phải giao dịch nguyên tử: nếu luồng cần chạy trong môi trường có bên khác thay đổi đường dẫn đồng thời, hãy thiết kế thêm cơ chế bảo vệ phù hợp. Đoạn ví dụ cũng **không tự tạo thư mục cha** của đích.

### Giải pháp gọn hơn với transferTo

Với bài toán chuyển toàn bộ byte còn lại từ nguồn sang đích, `InputStream.transferTo(OutputStream)` (Java 9+) thay vòng lặp thủ công:

```java
// Đoạn nằm trong ngữ cảnh đã có Path source và Path target hợp lệ,
// đã kiểm tra không cùng tệp.
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    long transferred = in.transferTo(out);
    System.out.println("Transferred bytes: " + transferred);
}
```

Ở đoạn này, `Files`, `Path`, `InputStream`, `OutputStream` là các kiểu trong `java.nio.file` và `java.io` cần import. `transferTo` đọc cho đến EOF và trả số byte đã chuyển; không hứa chắc sẽ sử dụng cơ chế zero-copy của hệ điều hành. Nếu cần xử lý, giới hạn, đo đếm hoặc biến đổi từng khối byte, vòng lặp `read(buffer)` vẫn rõ ràng và linh hoạt.

## 6. Các implementation thường gặp và quan hệ giữa chúng

| Nhóm | Đầu vào | Đầu ra | Công dụng |
| --- | --- | --- | --- |
| Tệp | `FileInputStream` hoặc `Files.newInputStream` | `FileOutputStream` hoặc `Files.newOutputStream` | Đọc/ghi byte của tệp |
| Bộ nhớ | `ByteArrayInputStream` | `ByteArrayOutputStream` | Test, tích lũy dữ liệu nhỏ/vừa |
| Có đệm | `BufferedInputStream` | `BufferedOutputStream` | Giảm lời gọi I/O ở luồng bên dưới |
| Giá trị nguyên thủy | `DataInputStream` | `DataOutputStream` | Đọc/ghi giá trị như `int`, `long`, `double` theo định dạng nhị phân đã quy định |
| Luồng có lớp bọc khác | `GZIPInputStream` (trong `java.util.zip`) | `GZIPOutputStream` | Giải nén/nén các byte đi qua luồng |

Một implementation có thể **bọc** implementation khác: `new BufferedInputStream(Files.newInputStream(path))`. Luồng ngoài nhận hành vi bổ sung, nhưng vẫn tuân thủ hợp đồng `InputStream`. Đối với kiểu dữ liệu có cấu trúc, `DataInputStream` và `DataOutputStream` cần được dùng theo **cùng thứ tự và định dạng** ở hai phía. Nếu viết `writeInt(42)` thì phía đọc cần `readInt()`, chứ không tự tách byte bằng encoding văn bản.

**Không phải mọi stream đều seek được.** `InputStream` là cách đọc tuần tự. Nếu cần truy cập vị trí tùy ý của tệp, cân nhắc `SeekableByteChannel` hoặc `RandomAccessFile`. `mark/reset` chỉ là tùy chọn: luôn kiểm tra `markSupported()`; `BufferedInputStream` hỗ trợ, còn `FileInputStream` không hỗ trợ đánh dấu/quay lại theo cách đó.

## 7. Quản lý tài nguyên và lỗi I/O

Luồng gắn với tệp hoặc kết nối thường giữ tài nguyên hệ điều hành. Hãy sử dụng **`try-with-resources`** khi tạo và sở hữu luồng:

```java
try (InputStream in = Files.newInputStream(source)) {
    // Đọc dữ liệu ở đây.
} // close() tự động được gọi.
```

Đoạn này giả định có `Path source` và các import cần thiết. Không gọi `close()` sớm khi còn cần truy cập; thao tác với stream đã đóng có thể ném `IOException` (tùy implementation). Ngoại lệ phát sinh ở phần xử lý vẫn được ném ra; nếu `close()` cũng lỗi, Java gắn lỗi đóng thành **suppressed exception** để không che mất lỗi chính. Có thể xem qua `Throwable.getSuppressed()` khi gỡ lỗi.

Phân biệt **quyền sở hữu**: code tự mở luồng thường tự đóng; code nhận luồng từ bên gọi nên thống nhất hợp đồng ai đóng. Tránh tùy tiện đóng `System.in` hoặc `System.out` vì đây là tài nguyên dùng chung của quá trình chạy.

`IOException` có thể xuất hiện khi tệp không tồn tại, không đủ quyền, thiết bị bị lỗi, hoặc luồng bên ngoài bị gián đoạn. Một phép sao chép thất bại giữa chừng có thể để lại **tệp đích một phần**; `try-with-resources` giúp đóng tài nguyên chứ không đảm bảo rollback. Nếu ứng dụng cần thay thế tệp một cách an toàn, có thể ghi vào tệp tạm cùng filesystem, xác minh rồi thay thế/di chuyển theo khả năng và điều kiện hệ thống; đó là vấn đề riêng ngoài hợp đồng `InputStream`/`OutputStream`.

## 8. Đọc text qua byte stream: phải chỉ rõ charset

Byte stream không biết ký tự. Khi cần chuyển giữa chuỗi và byte, **chọn `Charset` tường minh**:

```java
// Đoạn minh họa, cần import java.nio.charset.StandardCharsets.
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
String text = new String(bytes, StandardCharsets.UTF_8);
```

Việc cắt tùy ý một mảng byte UTF-8 rồi giải mã từng phần có thể chia đôi chuỗi mã hóa một ký tự và gây lỗi/nhân vật thay thế. Nếu xử lý văn bản có cấu trúc, hãy dùng `InputStreamReader`/`OutputStreamWriter` với charset rõ ràng, hoặc `Files.newBufferedReader`/`Files.newBufferedWriter`. Với byte thuần, giữ byte đến cuối quá trình sao chép thì không có vấn đề encoding.

Chẳng hạn, **sao chép ảnh PNG qua `InputStream`/`OutputStream` không được chuyển ảnh thành `String`**. Chuyển byte nhị phân qua String với charset không phù hợp có thể làm thay đổi byte và hỏng tệp.

## 9. Các góc cạnh API dễ hiểu sai

**`available()` không đo kích thước nguồn.** Nó là ước lượng số byte có thể đọc ngay mà không chặn, có thể trả 0 dù sẽ có thêm dữ liệu sau đó. Không dùng `new byte[in.available()]` làm chiến lược đọc toàn bộ nội dung, đặc biệt với luồng mạng.

**`skip(n)` không chắc bỏ qua đủ n byte.** Nó trả số thực sự đã bỏ qua. Nếu cần đảm bảo bỏ qua đúng `n`, Java hiện đại có `skipNBytes(n)`, phương thức có thể ném `EOFException` nếu luồng kết thúc sớm.

**`readAllBytes()` đổi tính tiện lợi lấy bộ nhớ.** Với đầu vào rất lớn hoặc không giới hạn, dữ liệu có thể vượt RAM. Dùng vòng lặp theo khối khi kích thước chưa biết hoặc khi cần streaming.

**Một lần `read(buffer)` không tương đương một thông điệp.** Luồng byte không bảo toàn ranh giới bản ghi. Nếu giao thức có bản ghi, ứng dụng phải định nghĩa cách phân ranh: độ dài cố định, trường length-prefix, dấu phân cách có quy tắc escape, hoặc cách mã hóa khác.

**`flush()` không thay thế `close()`.** Flush yêu cầu chuyển dữ liệu đang đệm, còn close giải phóng tài nguyên. Với các lớp bọc lồng nhau, đóng lớp ngoài thường đóng cả lớp bên trong; không cần khai báo cả outer stream và underlying stream thành hai tài nguyên riêng để đóng hai lần.

**`write(int)` không viết bốn byte của một `int`.** Nó chỉ ghi 8 bit thấp. Nếu muốn biểu diễn một `int` thành 4 byte theo định dạng xác định, dùng `DataOutputStream.writeInt` hoặc tự đặc tả mã hóa; đầu đọc phải dùng cùng định dạng.

**`byte` của Java là có dấu, byte trên luồng không có kiểu dấu.** Khi cần đổi `byte b` sang số nguyên 0..255, dùng `b & 0xFF`. Trái lại, `InputStream.read()` đã trả `int` 0..255 nên không cần thao tác đó.

## 10. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `byte b = (byte) in.read(); if (b == -1) ...` | Giá trị dữ liệu `0xFF` bị nhầm với EOF | Dùng `int value = in.read()`, kiểm tra `value == -1` |
| `out.write(buffer)` ngay sau `read(buffer)` | Lượt cuối có thể đọc ít hơn kích thước buffer, ghi cả byte cũ | `out.write(buffer, 0, count)` |
| Cho rằng `read(buffer)` luôn đọc đủ mảng | `read` có thể trả số byte dương nhỏ hơn yêu cầu | Dựa vào số byte trả về; tích lũy nếu cần một khối đủ dài |
| Lặp `while (in.available() > 0)` để đọc đến hết | `available` không là EOF/total-size signal | Lặp đến khi `read` trả `-1` |
| Dùng `readAllBytes()` cho file không giới hạn | Có nguy cơ hết bộ nhớ | Đọc/ghi theo khối |
| Quên đóng file stream | Có thể rò rỉ file descriptor hoặc thiếu flush | `try-with-resources` |
| Giải mã byte nhị phân thành String rồi ghi lại | Charset có thể làm thay đổi dữ liệu | Giữ nguyên byte, chỉ decode khi thực sự là text |
| Mở đầu ra trên cùng tệp nguồn | Đầu ra mặc định truncate, mất dữ liệu nguồn | Kiểm tra hai đường dẫn và thiết kế quy trình thay thế an toàn |
| Coi `flush()` là xác nhận ghi bền vững xuống đĩa | Flush không mang cam kết fsync | Dùng cơ chế đồng bộ lưu trữ riêng khi yêu cầu độ bền |
| Chỉ so `Files.size` để xác nhận bản sao | Tệp khác nội dung vẫn có thể cùng kích thước | So byte, hash phù hợp hoặc `Files.mismatch` khi cần xác minh |

## 11. Chọn API trong các tình huống thực tế

- **Sao chép luồng byte không giới hạn:** `read(buffer)` + `write(buffer, 0, count)`, hoặc `transferTo` nếu chỉ cần sao chép nguyên trạng.
- **Tệp nhỏ, đã biết giới hạn:** `Files.readAllBytes`/ `InputStream.readAllBytes` có thể thuận tiện nhưng sử dụng RAM tỉ lệ kích thước nội dung.
- **Đọc/ghi text:** `Reader`/`Writer` hoặc `Files` API kèm `StandardCharsets.UTF_8` khi phù hợp.
- **Cần đọc/ghi số nguyên/giá trị nguyên thủy theo định dạng nhị phân:** `DataInputStream` và `DataOutputStream`, đồng bộ thứ tự đọc/ghi.
- **I/O tuần tự với nhiều thao tác nhỏ:** thêm `BufferedInputStream`/`BufferedOutputStream` khi chưa có buffering phù hợp ở tầng dưới.
- **Truy cập ngẫu nhiên vị trí file:** chọn API random-access/channels thay vì cố gắng dùng byte stream tuần tự.

Thường nên khai báo biến theo **kiểu trừu tượng** `InputStream`/`OutputStream` và tạo một implementation cụ thể ở biên ứng dụng. Cách này giúp thay tệp bằng dữ liệu in-memory trong test mà không thay logic xử lý.

## 12. Tự thực hành và câu hỏi kiểm tra

1. Chạy `ByteBasics`, thay `payload` bằng `{(byte) 0x80, (byte) 0xFF, 0}`. Dự đoán `read()` trả các số nào (đáp án: `128, 255, 0`).
2. Dùng `CopyBytes` với một tệp nhị phân nhỏ và một tệp lớn. Kiểm tra nội dung bằng `Files.mismatch(Path, Path)` (Java 12+): kết quả `-1` nghĩa là không tìm thấy byte khác nhau; giá trị không âm là vị trí byte khác nhau đầu tiên.
3. Giải thích tại sao trong vòng lặp sao chép cần `out.write(buffer, 0, count)` và điều gì xảy ra nếu lượt đọc cuối chỉ trả 7 byte trong buffer 8192 byte.
4. Viết một phiên bản dùng `transferTo`, sau đó sửa thành phiên bản chỉ sao chép tối đa 1024 byte đầu. Với bài toán có giới hạn như vậy, cần tự kiểm soát số byte yêu cầu đọc ở từng vòng.
5. Tự trả lời: `read()` trả `-1` có giống với byte `0xFF` không? `flush()` có đồng nghĩa đóng luồng không? `available()` có biểu thị file còn bao nhiêu byte không?

**Ghi nhớ:** `InputStream` cung cấp byte và tín hiệu EOF; `OutputStream` nhận byte; vòng lặp phải dùng **đúng số byte vừa đọc**; tài nguyên phải có vòng đời rõ ràng. Nắm chắc bốn điều này sẽ giúp áp dụng cùng tư duy cho tệp, bộ nhớ và nhiều loại nguồn/đích byte khác trong Java.

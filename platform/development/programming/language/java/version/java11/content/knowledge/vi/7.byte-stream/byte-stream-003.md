# Phân biệt đọc một phần với đọc đủ theo giao thức (Java 11, Byte stream)

## 1. Bài toán: số byte một lần đọc khác với độ dài thông điệp

Khi làm việc với `InputStream`, đặc biệt là stream từ socket, file, bộ giải nén hoặc các tầng I/O khác, **một lần gọi `read(...)` không có nghĩa là đã nhận được toàn bộ một thông điệp**.

Giả sử giao thức quy định bản tin tiếp theo có 5 byte `HELLO`. Một lời gọi:

```java
byte[] body = new byte[5];
int count = input.read(body);
```

có thể trả về `count = 2` cùng hai byte `HE`. Đây là một lần đọc **hợp lệ** theo hợp đồng `InputStream.read(byte[])`: phương thức đọc **tối đa** số byte mà buffer chứa, không cam kết lấp đầy buffer. Ba byte `LLO` còn lại cần được đọc ở các lần tiếp theo.

Hai khái niệm phải tách rõ:

- **Đọc một phần (partial read):** một lần gọi API nhận được `n` byte, `0 < n < requested`, dù dòng dữ liệu có thể còn byte tiếp theo.
- **Đọc đủ theo giao thức (complete frame/message read):** chương trình đã thu thập **đúng tập byte mà đặc tả giao thức quy định** cho một đơn vị dữ liệu. Muốn biết "đủ" phải có quy tắc phân định thông điệp (*framing*): số byte cố định, độ dài nằm trong header, delimiter, kết thúc kết nối, hoặc cách mã hóa khung khác.

Ví dụ: nếu nhận 2/5 byte thì việc đọc đã tiến triển, nhưng **khung 5 byte vẫn chưa hoàn tất**. Nếu đã nhận 5/5 byte thì khung hoàn tất, ngay cả khi stream có byte tiếp theo thuộc khung khác. Trong kết nối giữ lâu, không được chờ EOF để quyết định thông điệp vừa hoàn tất khi giao thức có độ dài riêng.

Nội dung này áp dụng cho Java 11 và các phiên bản Java hiện hành. Đặc biệt, từ **Java 11** có overload `InputStream.readNBytes(int len)` giúp đọc đến giới hạn byte được yêu cầu mà không phải tự tạo mảng trước.

## 2. Hiểu đúng hợp đồng của những API đọc byte

| API | Có thể đọc ít hơn số yêu cầu? | Điều kiện kết thúc / kết quả | Cách dùng phù hợp |
| --- | --- | --- | --- |
| `int read()` | Chỉ đọc một byte mỗi lần | Trả về `0..255` hoặc `-1` ở EOF; có thể chặn chờ dữ liệu | Đọc một byte hay cấu trúc đơn giản |
| `int read(byte[] b)` | **Có** | Trả số byte thực đọc, `-1` ở EOF; buffer không tự lấp đầy | Đọc theo khối, loop xử lý từng phần |
| `int read(byte[] b, int off, int len)` | **Có** | Tối đa `len` byte vào vị trí `off`; trả số thực đọc, `-1` ở EOF | Đọc tiếp vào vị trí còn thiếu |
| `int readNBytes(byte[] b, int off, int len)` | **Có, nếu gặp EOF trước** | Cố đọc đến `len` byte, EOF hoặc lỗi I/O; trả số byte thực đọc (`0..len`) | Đọc nhiều lần để tích lũy số byte biết trước |
| `byte[] readNBytes(int len)` | **Có, nếu gặp EOF trước** | Cố đọc đến `len`, EOF hoặc lỗi I/O; trả mảng dài bằng số byte thực nhận | Khung nhỏ có độ dài biết trước, sau đó kiểm tra `array.length` |
| `DataInputStream.readFully(byte[] b)` | Không trả một phần như kết quả hợp lệ | Đọc đủ `b.length` hoặc ném `EOFException` khi hết stream sớm | Khung cố định hoặc payload biết độ dài |
| `DataInputStream.readFully(b, off, len)` | Tương tự | Đọc đúng `len` hoặc ném `EOFException` | Đọc đủ vào một phần buffer |
| `readAllBytes()` | Đọc đến EOF, không theo chiều dài khung | Trả các byte còn lại đến EOF; có thể chiếm nhiều bộ nhớ hoặc chờ rất lâu | Nguồn hữu hạn, kích thước được kiểm soát |
| `available()` | Không phải lệnh đọc | Ước lượng byte có thể đọc ngay mà không chặn, **không phải số byte còn lại** | Tình huống tối ưu hóa hạn chế, không dùng làm ranh giới thông điệp |

Với buffer có chiều dài dương, hợp đồng thông thường của `read(b, off, len)` là trả ít nhất một byte nếu chưa EOF và không có exception; trả `0` khi `len == 0`. Đừng dùng `buffer.length` để đo số byte nhận được: chỉ `count` do phương thức trả về mới cho biết phần có dữ liệu hợp lệ.

**Lưu ý quan trọng:** `readNBytes(...)` là công cụ **cố đọc đủ**; nó **không bảo đảm giao thức đã nhận đủ** khi đầu vào kết thúc sớm. Với overload trả `byte[]`, phải kiểm tra `bytes.length == expectedLength`. Với overload ghi vào buffer, phải kiểm tra `count == expectedLength`. `DataInputStream.readFully` đóng gói luôn việc kiểm tra thiếu byte và ném `EOFException`.

### Giá trị trả về của `read(...)` nói gì?

Giả sử `read(buffer, 0, 5)`:

- Trả `5`: đã nhận 5 byte, có thể hoàn tất phần giao thức cần 5 byte.
- Trả `2`: có 2 byte hợp lệ trong `buffer[0]` và `buffer[1]`; phải tiếp tục tích lũy nếu giao thức yêu cầu 5 byte.
- Trả `-1`: đã gặp **end of stream** (EOF) tại vị trí này. Nếu giao thức còn thiếu byte, đây là một thông điệp bị cắt cụt; nếu giao thức định nghĩa EOF là kết thúc thông điệp thì có thể là kết thúc hợp lệ.
- Ném `IOException`: xảy ra lỗi I/O; không được tự coi là EOF thông thường. Nếu lỗi xảy ra sau khi đã đọc một phần, trạng thái stream/buffer có thể không còn phù hợp để tiếp tục parse khung mà không có quy tắc khôi phục.

Một số triển khai có thể **block** trong lời gọi đọc cho đến khi có dữ liệu, phát hiện EOF hoặc gặp lỗi. "Đọc một phần" không có nghĩa là `read` luôn trả về ngay nếu chưa có byte.

## 3. Nguyên tắc giao thức: byte stream không tự mang ranh giới thông điệp

Xem một luồng byte logic:

```text
[HELLO][WORLD]
  frame1  frame2
```

Các lần `read` có thể quan sát những đoạn dữ liệu như:

```text
Lần 1: [HE]
Lần 2: [LLO]
Lần 3: [W]
Lần 4: [ORLD]
```

Hoặc bất kỳ kiểu chia nào khác mà hợp đồng của stream cho phép. **Số byte trả về ở mỗi lần gọi không phải số byte thuộc về một bản tin.** Điều này đặc biệt quan trọng với TCP: TCP cung cấp byte stream có thứ tự, không cam kết một lần `write` của phía gửi ứng với một lần `read` của phía nhận. Một thông điệp có thể đến thành nhiều lần đọc; nhiều thông điệp cũng có thể nằm sát nhau trong stream.

Không có parser framing thì `InputStream` không thể tự nhận biết chỗ kết thúc `HELLO` và bắt đầu `WORLD`.

Các kiểu framing phổ biến:

| Kiểu giao thức | Biết khi nào đủ? | Rủi ro cần xử lý |
| --- | --- | --- |
| **Cố định N byte** | Đã đọc đúng `N` byte | EOF sớm; nhầm đệm dữ liệu cuối khung |
| **Length-prefixed** | Đọc header, lấy `length`, rồi đọc đúng `length` byte payload | Header thiếu, độ dài âm/quá lớn, endianness hoặc đơn vị độ dài không thống nhất |
| **Delimiter-terminated** | Đã gặp dấu kết thúc quy định, ví dụ `LF` | Dấu phân cách nằm trong payload, escaping, byte encoding, giới hạn chiều dài trước delimiter |
| **EOF-delimited** | Phía gửi đóng/half-close theo giao thức để đánh dấu hết thông điệp | Không thích hợp khi cần giữ kết nối để gửi tiếp nhiều thông điệp không có marker |
| **Chunked/structured framing** | Phân tích lần lượt header chunk và số byte của từng chunk, đến marker cuối theo protocol | Đếm sai byte, thiếu chunk, giới hạn tài nguyên, parser sai trạng thái |

Chọn thuật toán đọc theo **đặc tả giao thức** trước, rồi mới chọn API Java. Không phải mọi giao thức đều nên dùng `readNBytes(N)`: API này hợp lý khi đã biết chính xác `N`. Với giao thức delimiter, cần parser tìm delimiter; với protocol có khung phân cấp, cần parser trạng thái phù hợp.

## 4. Ví dụ tái hiện partial read bằng stream trả tối đa hai byte

`ByteArrayInputStream` có thể trả đủ byte sẵn có trong một lần đọc, nên không phải mô phỏng tốt cho lần đọc ngắn. Để thử parser, tạo lớp wrapper chủ động giới hạn mỗi lần `read(byte[], off, len)` tối đa hai byte:

```java
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;

final class ChunkedInputStream extends FilterInputStream {
    ChunkedInputStream(byte[] bytes) {
        super(new ByteArrayInputStream(bytes));
    }

    @Override
    public int read(byte[] buffer, int off, int len) throws IOException {
        if (len == 0) {
            return 0;
        }
        return super.read(buffer, off, Math.min(len, 2));
    }
}
```

Đây là **lớp hỗ trợ dùng trong test**, không phải stream mạng. Với `byte[] raw = "HELLO!".getBytes(StandardCharsets.UTF_8)`:

```java
try (InputStream input = new ChunkedInputStream(raw)) {
    byte[] buffer = new byte[5];
    int count = input.read(buffer);

    System.out.println(count); // 2
    System.out.println(new String(
            buffer, 0, count, StandardCharsets.UTF_8)); // HE
}
```

Chúng ta đã **yêu cầu tối đa 5 byte** nhưng chỉ nhận **2 byte**. Đó không phải lỗi parser hay lỗi `InputStream`. Sai lầm nằm ở việc viết chương trình giả định buffer đã được lấp đầy.

Điều cần làm khi muốn đủ 5 byte: tích lũy đọc nhiều lần hoặc dùng API hỗ trợ đọc theo số lượng byte, rồi đối chiếu chính xác kết quả. Trong cả hai trường hợp, phải phân biệt thiếu dữ liệu tạm thời với **EOF** và **lỗi I/O**.

## 5. Đọc chính xác N byte trong Java 11

### 5.1. Dùng `InputStream.readNBytes(int)` và kiểm tra độ dài

```java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

static byte[] readExactly(InputStream input, int length)
        throws IOException {
    final int maxFrameBytes = 1024;

    if (length < 0 || length > maxFrameBytes) {
        throw new IOException("Invalid frame length: " + length);
    }

    byte[] bytes = input.readNBytes(length);

    if (bytes.length != length) {
        throw new EOFException(
                "Expected " + length + " bytes, got " + bytes.length);
    }

    return bytes;
}
```

Đây là **phương thức đặt trong một lớp**, không phải chương trình độc lập. `readNBytes(int)` được bổ sung từ Java 11. Nó cố đọc `length` byte và trả về mảng chứa số byte thực nhận, kể cả khi gặp EOF sớm. Kiểm tra `bytes.length` biến điều kiện "khung chưa đủ" thành `EOFException` phù hợp với giao thức yêu cầu độ dài chính xác.

Trong hệ thống thật, `maxFrameBytes` phải là một giới hạn do protocol/nghiệp vụ xác định; giá trị **1024 chỉ là giới hạn minh họa**. Không tạo buffer dựa trực tiếp trên length do client gửi nếu chưa xác thực giá trị, kể cả khi `readNBytes` có sẵn.

### 5.2. Dùng `readNBytes(byte[], off, len)` khi có buffer

```java
byte[] body = new byte[5];
int received = input.readNBytes(body, 0, 5);

if (received != 5) {
    throw new EOFException(
            "Expected 5 bytes, got " + received);
}

// Chỉ dùng body[0..4] sau khi đã xác nhận received == 5
```

Overload ghi vào buffer có từ Java 9 và vẫn hữu ích trong Java 11+. Khi EOF sớm, nó trả số byte đã nhận thay vì tự ném `EOFException`. Trên buffer có dữ liệu cũ, các ô ngoài vùng được ghi **không tự bị xóa**. Vì thế phải dựa trên `received` và không parse phần chưa được xác nhận có dữ liệu.

### 5.3. Dùng `DataInputStream.readFully(...)` khi muốn API ném EOFException

```java
import java.io.DataInputStream;
import java.io.EOFException;

DataInputStream data = new DataInputStream(input);
byte[] body = new byte[5];

data.readFully(body); // Hoàn tất 5 byte hoặc ném EOFException
```

`readFully` xử lý các lần đọc ngắn và tự ném `EOFException` nếu không đủ byte trước EOF. Bản thân `readFully` **không biết framing**; người gọi vẫn phải quyết định cần đúng bao nhiêu byte và kiểm tra giới hạn. Việc tạo `DataInputStream` không làm thay đổi giao thức hoặc tự giải quyết length prefix.

Nếu `input` thuộc sở hữu của caller (ví dụ socket dùng cho nhiều thông điệp), phải xác định rõ thành phần nào chịu trách nhiệm đóng stream; đóng wrapper `DataInputStream` thường đóng luôn stream bên trong.

### 5.4. Viết vòng lặp khi cần kiểm soát tiến độ

```java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

static void readFullyManually(
        InputStream input, byte[] dest, int off, int len)
        throws IOException {
    if (off < 0 || len < 0 || len > dest.length - off) {
        throw new IndexOutOfBoundsException();
    }

    int received = 0;
    while (received < len) {
        int n = input.read(dest, off + received, len - received);

        if (n == -1) {
            throw new EOFException(
                    "Expected " + len + " bytes, got " + received);
        }
        received += n;
    }
}
```

Vòng lặp này **chỉ yêu cầu phần byte còn thiếu**, nên không đọc sang thông điệp kế tiếp. Theo hợp đồng `InputStream.read(byte[],off,len)` thông thường, khi `len > 0`, lời gọi sẽ trả số byte dương hoặc `-1` (hoặc ném exception); vì thế `received` sẽ tăng hoặc có lỗi. Trong adapter tùy biến không tuân thủ hợp đồng mà liên tục trả `0`, vòng lặp có thể không tiến triển; đây là lỗi của adapter cần được phát hiện và sửa.

Vòng lặp thủ công hữu ích khi muốn gắn thống kê tiến độ, áp đặt deadline tổng hoặc tích hợp parser nhiều trạng thái. Với trường hợp đơn giản, `readNBytes` hoặc `readFully` dễ đọc hơn và ít rủi ro sai offset.

## 6. Độ dài tiền tố: đọc header rồi đọc payload

Một thiết kế binary frame đơn giản có cấu trúc:

```text
+----------------------+-------------------------+
| Header: 4 byte int   | Payload: exactly L byte |
| L (big-endian)       | UTF-8 bytes             |
+----------------------+-------------------------+
```

Quy tắc của giao thức minh họa:

1. Đọc đúng 4 byte header.
2. Diễn giải số nguyên có dấu 32-bit theo thứ tự **big-endian** thành `L`.
3. Kiểm tra `0 <= L <= MAX_FRAME_BYTES`.
4. Đọc **đúng L byte**; thiếu byte là thông điệp lỗi/không hoàn chỉnh.
5. Giải mã nội dung bằng UTF-8. Byte tiếp theo, nếu có, thuộc khung/đối tượng tiếp theo.

`DataInputStream.readInt()` phù hợp với header big-endian kiểu `DataOutputStream.writeInt()`. **Đây là một giao thức ví dụ**, không phải Java tự động chọn framing cho mọi stream. Khi giao tiếp với hệ thống khác, phải thống nhất thứ tự byte, kiểu số, độ dài header và encoding theo tài liệu protocol.

### Phải đếm byte, không đếm số ký tự

`String.length()` đếm các đơn vị UTF-16, không phải số byte UTF-8. Ví dụ Java string `"Xin ch\u00E0o"` (hiển thị là "Xin chào") có 8 đơn vị UTF-16 nhưng mã hóa UTF-8 chiếm **9 byte**. Đối với protocol biểu diễn độ dài payload bằng byte:

```java
import java.nio.charset.StandardCharsets;

String text = "Xin ch\u00E0o";
byte[] payload = text.getBytes(StandardCharsets.UTF_8);

System.out.println(text.length());    // 8
System.out.println(payload.length);   // 9
```

Phía gửi phải ghi `payload.length` vào header, không dùng `text.length()`. Phía nhận đọc đúng số byte rồi mới giải mã UTF-8. Không giải mã tùy tiện các fragment ngay lập tức, vì một ký tự UTF-8 nhiều byte có thể bị chia giữa hai lần đọc.

### Kiểm tra length trước khi cấp phát

Nếu một client gửi header `L = 2_147_483_647`, gọi ngay `new byte[L]` hoặc `readNBytes(L)` có thể gây tiêu hao bộ nhớ nghiêm trọng. Quy trình nhận phải kiểm tra `L < 0`, `L > MAX_FRAME_BYTES`, giới hạn tài nguyên và trạng thái phiên **trước khi** phân bổ. Độ dài bằng 0 có thể hợp lệ nếu giao thức cho phép payload rỗng.

Khi parse nhiều frame trên một stream, sau khi đọc đúng `L` byte, không cần chờ EOF: tiếp tục đọc header của frame sau theo protocol.

## 7. Chương trình Java 11+ hoàn chỉnh: partial read, exact read, EOF và length prefix

Lưu toàn bộ ví dụ sau thành **`PartialReadVsExactDemo.java`**:

```java
import java.io.*;
import java.nio.charset.StandardCharsets;

public class PartialReadVsExactDemo {
    private static final int MAX_FRAME = 1024;

    // Test stream: mỗi lần đọc vào buffer trả tối đa 2 byte.
    static final class ChunkedInputStream extends FilterInputStream {
        ChunkedInputStream(byte[] bytes) {
            super(new ByteArrayInputStream(bytes));
        }

        @Override
        public int read(byte[] buffer, int off, int len)
                throws IOException {
            if (len == 0) {
                return 0;
            }
            return super.read(buffer, off, Math.min(len, 2));
        }
    }

    static byte[] readExactly(InputStream input, int length)
            throws IOException {
        if (length < 0 || length > MAX_FRAME) {
            throw new IOException("Invalid frame length: " + length);
        }

        byte[] bytes = input.readNBytes(length);
        if (bytes.length != length) {
            throw new EOFException(
                    "Expected " + length + " bytes, got " + bytes.length);
        }
        return bytes;
    }

    static byte[] encodeFrame(String text) throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(payload.length);  // Header: big-endian int
            out.write(payload);             // Payload: UTF-8 bytes
            out.writeByte(127);             // Byte đánh dấu sau payload
        }

        return buffer.toByteArray();
    }

    public static void main(String[] args) throws IOException {
        byte[] raw = "HELLO!".getBytes(StandardCharsets.UTF_8);

        // Một lần đọc chỉ trả 2 byte dù buffer chứa được 5.
        try (InputStream input = new ChunkedInputStream(raw)) {
            byte[] buffer = new byte[5];
            int count = input.read(buffer);

            System.out.println("oneRead=" + count + ":" +
                    new String(buffer, 0, count, StandardCharsets.UTF_8));

            byte[] next = input.readNBytes(3);
            System.out.println("nextThree=" +
                    new String(next, StandardCharsets.UTF_8));

            int last = input.read();
            System.out.println("last=" + (char) last);
        }

        // readExactly lấy đúng 5 byte, giữ byte "!" cho phần sau.
        try (InputStream input = new ChunkedInputStream(raw)) {
            byte[] exact = readExactly(input, 5);
            System.out.println("exact=" +
                    new String(exact, StandardCharsets.UTF_8));
            System.out.println("afterExact=" + (char) input.read());
        }

        // readNBytes vào buffer có thể trả ít hơn 5 khi EOF.
        try (InputStream input = new ChunkedInputStream(
                "ABC".getBytes(StandardCharsets.UTF_8))) {
            byte[] buffer = new byte[5];
            int count = input.readNBytes(buffer, 0, 5);

            System.out.println("shortRead=" + count + ":" +
                    new String(buffer, 0, count, StandardCharsets.UTF_8));
        }

        // Trường hợp giao thức đòi 5 byte: EOF sớm là lỗi.
        try (InputStream input = new ChunkedInputStream(
                "ABC".getBytes(StandardCharsets.UTF_8))) {
            try {
                readExactly(input, 5);
            } catch (EOFException ex) {
                System.out.println("incomplete=" + ex.getMessage());
            }
        }

        // Khung: 4 byte length + payload UTF-8 + marker 127.
        try (DataInputStream input = new DataInputStream(
                new ChunkedInputStream(encodeFrame("Xin ch\u00E0o")))) {
            int length = input.readInt();
            if (length < 0 || length > MAX_FRAME) {
                throw new IOException("Invalid frame length: " + length);
            }

            byte[] payload = new byte[length];
            input.readFully(payload);

            String decoded = new String(payload, StandardCharsets.UTF_8);
            System.out.println("frameLength=" + length);
            System.out.println("frameTextOK=" +
                    decoded.equals("Xin ch\u00E0o"));
            System.out.println("marker=" + input.readUnsignedByte());
        }
    }
}
```

Biên dịch và chạy với JDK 11 trở lên:

```bash
javac --release 11 PartialReadVsExactDemo.java
java PartialReadVsExactDemo
```

Stdout:

```text
oneRead=2:HE
nextThree=LLO
last=!
exact=HELLO
afterExact=!
shortRead=3:ABC
incomplete=Expected 5 bytes, got 3
frameLength=9
frameTextOK=true
marker=127
```

**Giải thích kết quả:**

- `oneRead=2:HE` chứng minh một lần `read(buffer)` không bảo đảm buffer đầy; `nextThree=LLO` là ba byte kế tiếp và `last=!` còn sau đó.
- `exact=HELLO` chứng minh `readNBytes(5)` trong helper tích lũy đủ 5 byte dù nguồn cung cấp tối đa 2 byte mỗi lần; `afterExact=!` cho thấy không đọc tràn sang dữ liệu tiếp theo.
- `shortRead=3:ABC` chứng minh `readNBytes(buffer,0,5)` khi gặp EOF sớm có thể trả 3 mà không tự ném `EOFException`. Khi *giao thức* yêu cầu đủ 5, `readExactly` biến tình huống ấy thành `incomplete=...`.
- `frameLength=9` vì chuỗi có ký tự `à` chiếm 2 byte UTF-8. `DataInputStream.readInt()` đọc đủ header và `readFully` đọc đúng payload dài 9 byte qua nhiều lần đọc nhỏ.
- `frameTextOK=true` xác nhận giải mã sau khi thu đủ payload; `marker=127` chứng minh byte nằm sau payload vẫn còn nguyên, để parser đọc phần tiếp theo.

Mẫu này dùng stream trong bộ nhớ để kết quả quyết định và dễ chạy. Trong mạng thật, lần đọc ngắn có thể đến từ các lớp I/O hay thời điểm dữ liệu sẵn sàng; không nên dùng kết quả 2 byte từ mô phỏng làm một giả định cố định về TCP.

## 8. EOF, timeout và dữ liệu thiếu: phân biệt đúng trạng thái

Một parser framing chặt chẽ nên phân biệt:

| Trạng thái | Ví dụ | Xử lý |
| --- | --- | --- |
| Đã đọc đủ | Đã nhận đúng `L` byte payload | Xác nhận frame, chuyển sang frame kế |
| Partial read nhưng chưa EOF | `read` trả 2/5 | Tiếp tục đọc phần thiếu |
| EOF sau khi đã đọc hết **trọn** các frame | Không còn header của frame tiếp theo và giao thức cho phép đóng kết nối | Kết thúc phiên theo quy tắc |
| EOF ở giữa header/payload | Header 4 byte mới nhận 2, hoặc payload 5 byte mới nhận 3 | Báo frame bị cắt cụt, thường `EOFException` |
| Socket read timeout | Peer chưa cung cấp byte cần thiết trong thời hạn đọc | Xử lý `SocketTimeoutException` theo chính sách timeout; **không** coi là EOF |
| Lỗi I/O khác | Kết nối reset, storage error, v.v. | Bảo toàn thông tin lỗi, xử lý/đóng tài nguyên phù hợp; không giả định dữ liệu đã hoàn chỉnh |
| Length prefix không hợp lệ | `L < 0` hoặc `L > max` | Từ chối trước khi cấp phát/đọc payload |

### `-1` không phải ranh giới bản tin trong mọi giao thức

`-1` từ `InputStream.read()` là EOF của **stream**, không phải tín hiệu "đã đọc hết một frame" trừ khi giao thức thật sự định nghĩa frame kết thúc bằng việc bên gửi đóng đầu ghi. Kết nối có thể giữ mở sau khi gửi một frame để gửi tiếp frame khác.

Ví dụ, server nhận 4-byte length prefix và đúng `L` byte payload: frame đã đủ. Chờ đến `-1` sẽ làm server đợi peer đóng kết nối, có thể gây treo nếu peer đang chờ phản hồi của server.

### Không dùng `available()` để đo số byte còn thiếu

`available()` chỉ ước lượng số byte có thể đọc mà không block **ở thời điểm gọi**. Nó có thể trả `0` ngay cả khi phía gửi sẽ gửi thêm dữ liệu hoặc dữ liệu đang truyền. Vì vậy:

```java
// SAI: không phải cách xác định đã nhận đủ frame
while (input.available() > 0) {
    // ...
}
```

Đặc biệt **không** dùng `new byte[input.available()]` rồi gọi một lần `read` và coi kết quả là toàn bộ một message. Với file hay `ByteArrayInputStream`, kết quả có thể "trông đúng" trong thử nghiệm nhỏ, nhưng không phải hợp đồng dùng chung cho `InputStream`.

### Không dùng `readAllBytes()` theo thói quen trên kết nối giữ lâu

`readAllBytes()` đợi EOF; nó không có thông tin về frame length, delimiter hoặc boundary của protocol. Nếu peer gửi một frame rồi giữ socket mở để chờ phản hồi, receiver dùng `readAllBytes()` có thể đợi đến khi timeout hoặc đóng kết nối. Ngoài ra, nó có thể cấp phát nhiều bộ nhớ khi nguồn chưa giới hạn.

Dùng `readAllBytes()` phù hợp hơn cho nội dung hữu hạn mà ta chấp nhận đọc đến EOF và đã có giới hạn nguồn/tài nguyên, ví dụ một file nhỏ đã biết kích thước và nằm trong phạm vi tin cậy.

## 9. Thiết kế parser an toàn và dễ kiểm thử

### 9.1. Giới hạn độ dài, thời gian và tài nguyên

- **Giới hạn khung:** xác nhận length prefix trước khi cấp phát; đặt `MAX_FRAME_BYTES` theo nghiệp vụ. Cần thêm giới hạn tổng số frame, tổng byte mỗi phiên hoặc tốc độ nhập khi hệ thống đối diện dữ liệu không tin cậy.
- **Deadline/timeout:** các hàm đọc đủ có thể tiếp tục chờ nếu peer không gửi đủ và cũng không đóng kết nối. Với blocking `Socket`, cân nhắc `setSoTimeout(...)` để đặt read timeout; nếu cần giới hạn thời gian **cho cả một frame**, deadline tổng là một chính sách riêng, không được mặc nhiên xem mỗi lần read timeout là deadline của toàn frame.
- **Giới hạn bộ nhớ:** `readNBytes(int)` cần đủ bộ nhớ cho dữ liệu mà nó giữ; với payload lớn, xử lý theo từng chunk giới hạn rồi ghi ra đích phù hợp thay vì materialize toàn bộ.
- **Không bỏ qua IOException:** một lỗi I/O giữa frame có thể khiến stream và buffer rơi vào trạng thái khó khôi phục; không tiếp tục parse cùng frame một cách mù quáng.

### 9.2. Đơn vị đo của protocol phải là byte

Length prefix của binary protocol thông thường đo bằng **byte payload đã mã hóa**. Một ký tự Unicode có thể cần nhiều byte UTF-8; byte order của header cũng phải khớp ở cả hai phía. Nếu protocol quy định *code points*, *UTF-16 code units* hay số phần tử thay vì byte, cần tuân thủ đúng định nghĩa đó và không tự đồng nhất với `byte[].length`.

Để giải mã UTF-8 nghiêm ngặt (khi dữ liệu lỗi phải bị từ chối), `new String(bytes, StandardCharsets.UTF_8)` mặc định có thể thay thế byte lỗi bằng ký tự replacement; trong parser yêu cầu strict validation, sử dụng `CharsetDecoder` với `CodingErrorAction.REPORT` để phát hiện dữ liệu mã hóa không hợp lệ. Đây là bước kiểm tra **sau khi đã đọc đủ byte của frame**.

### 9.3. Framing delimiter và vấn đề escape

Với giao thức phân cách bằng `\n`, cần quyết định rõ:

- Delimiter có thuộc nội dung message không?
- Payload có cho phép `\n` bên trong không? Nếu có, escape/quoting như thế nào?
- Độ dài tối đa trước khi gặp delimiter là bao nhiêu?
- Dữ liệu được mã hóa theo charset gì? Có được phép cắt byte ở giữa ký tự đa byte không?

`BufferedReader.readLine()` tiện cho một số giao thức văn bản theo dòng, nhưng tự bỏ ký tự kết thúc dòng và không giải quyết escaping, length limit hoặc binary payload. Không ép dữ liệu nhị phân tùy ý thành chuỗi bằng `readLine()`.

### 9.4. Một stream, một parser giữ trạng thái khung

Nếu có nhiều consumer đồng thời đọc chung một `InputStream` mà không có cơ chế đồng bộ và phân phối, mỗi consumer có thể lấy một phần byte của frame do consumer khác đang chờ. Thông thường nên có **một nơi sở hữu parser/stream** và phân phối các message đã hoàn chỉnh. Đọc song song ở tầng ứng dụng phải được thiết kế rõ ràng theo protocol, không chỉ gọi `read` từ nhiều thread rồi ghép kết quả.

### 9.5. Kiểm thử các tình huống fragment có chủ đích

Dù bài chạy với `ByteArrayInputStream` một cách trơn tru, code production nên được thử với wrapper khiến mỗi `read` trả 1 byte, 2 byte, đôi khi đủ buffer, và EOF đúng lúc đang đọc header hoặc payload. Xác nhận parser vẫn cho cùng thông điệp hoàn chỉnh khi dữ liệu được chia thành các đoạn khác nhau.

Có thể kiểm thử thêm: payload rỗng nếu protocol cho phép; length âm; length vượt giới hạn; hai frame liên tiếp; UTF-8 nhiều byte bị chia giữa các lần đọc; timeout/lỗi I/O; giải mã sai charset; delimiter không xuất hiện trước giới hạn.

## 10. Lỗi thường gặp và cách sửa

| Biểu hiện | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Buffer dài 1024 nhưng chỉ có vài byte hợp lệ | `read` có quyền trả về ít hơn yêu cầu | Sử dụng `n` thực đọc, tích lũy hoặc `readNBytes`/`readFully` |
| Hiển thị ký tự `\0` hoặc dữ liệu rác cuối buffer | Parse toàn bộ `buffer.length` thay vì `n` | Chỉ xử lý `buffer[0..n-1]`, kiểm tra n trước |
| Nhận message thiếu mà vẫn xử lý | Dùng `readNBytes` nhưng không so `n`/`length` | Kiểm tra đủ byte, báo `EOFException` khi EOF sớm |
| Client/server chờ nhau vô hạn | Receiver đợi EOF thay vì đọc đúng protocol length | Dựa vào framing, áp dụng timeout/deadline |
| Một request bị ghép với request sau | Đọc quá ranh giới frame, hoặc thiếu parser trạng thái | Chỉ tiêu thụ đúng byte của frame |
| Chia một request làm hai vì mỗi `read` ít byte | Xem mỗi lần `read` là một message | Đọc theo định nghĩa frame, tách khỏi số lần đọc |
| `available() == 0` bị coi là EOF | Nhầm ước lượng không block với kết thúc stream | EOF dùng `read(...) == -1`; đủ frame dùng bộ đếm theo protocol |
| Độ dài header bé hơn payload UTF-8 thật | Dùng `String.length()` thay vì byte count | Mã hóa trước, header ghi `payload.length` |
| Cấp phát bộ nhớ rất lớn | Tin length prefix do bên ngoài cung cấp | Validate length theo giới hạn trước khi allocate |
| Bỏ qua timeout rồi tiếp tục parse từ đầu | Một phần frame có thể đã được tiêu thụ | Quản lý trạng thái/offset và chính sách retry rõ ràng |

## 11. Tự kiểm tra (có đáp án)

**1.** `byte[] b = new byte[10]; int n = in.read(b);` trả `n=3`. Có phải API lỗi vì không lấp đầy buffer?

**Đáp án:** Không. `read` được phép trả số byte ít hơn yêu cầu. Chỉ 3 byte đầu hợp lệ cho lần đọc đó; nếu protocol yêu cầu 10 byte thì phải đọc tiếp.

**2.** `in.readNBytes(10)` trả về mảng 7 byte. Mặc định Java có ném `EOFException` không?

**Đáp án:** Không. Overload trả mảng sẽ trả các byte đã đọc khi gặp EOF trước 10. Caller phải kiểm tra `bytes.length == 10` nếu giao thức yêu cầu đủ.

**3.** Gọi `data.readFully(new byte[10])` trên stream chỉ có 7 byte sẽ thế nào?

**Đáp án:** `DataInputStream.readFully` ném `EOFException` khi không đủ 10 byte trước EOF.

**4.** Sau khi đọc đủ 4-byte header và 20-byte payload, socket còn mở. Frame đã hoàn tất chưa?

**Đáp án:** Nếu đặc tả nói frame gồm header 4 byte và payload 20 byte thì **đã hoàn tất**. EOF không phải điều kiện bắt buộc.

**5.** Có được dùng `available()==0` để kết luận phía gửi không còn dữ liệu?

**Đáp án:** Không. `available()` không phản ánh tổng dữ liệu sẽ đến hoặc EOF một cách tổng quát.

**6.** Chuỗi `"Xin ch\u00E0o"` có `length() == 8` và UTF-8 byte length bằng 9. Protocol length-prefix lưu byte count thì gửi giá trị mấy?

**Đáp án:** **9**, vì đơn vị độ dài là byte payload đã mã hóa.

**7.** Vì sao `readAllBytes()` có thể gây chờ lâu trên kết nối giữ mở?

**Đáp án:** Nó cần EOF mới kết thúc bình thường; phía gửi có thể chưa đóng kết nối sau frame và đang chờ phản hồi.

**8.** Có thể sử dụng `readFully` cho một giao thức có payload kết thúc bằng newline nhưng chưa biết độ dài không?

**Đáp án:** Không trực tiếp, vì `readFully` cần biết số byte phải đọc. Cần parser phát hiện delimiter theo đúng encoding/escape rule, có giới hạn chiều dài, rồi hoàn tất message khi gặp điều kiện của giao thức.

## Tài liệu chuẩn còn áp dụng

- [Oracle Java SE 11: InputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html) — hợp đồng `read`, `readNBytes`, `available`, `readAllBytes`; overload `readNBytes(int)` xuất hiện từ Java 11.
- [Oracle Java SE 11: DataInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/DataInputStream.html) — `readFully`, `readInt` và các ngoại lệ khi thiếu byte.
- [Oracle Java SE 11: DataOutputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/DataOutputStream.html) — ghi byte payload và các giá trị nguyên thủy tương thích với `DataInputStream`.
- [Oracle Java SE 11: Socket.setSoTimeout](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/Socket.html#setSoTimeout(int)) — giới hạn thời gian chờ của một blocking read trên socket.
- [Oracle Java SE 26: InputStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html) — xác nhận ý nghĩa các API đọc byte vẫn được duy trì trong JDK hiện hành.

**Điểm cốt lõi:** `read(...)` cho biết **lần gọi này đã nhận bao nhiêu byte**; giao thức mới quyết định **khi nào thông điệp hoàn chỉnh**. Muốn đọc đủ, phải xác định framing, tích lũy đúng số byte hoặc đúng marker, xử lý EOF trước hạn, giới hạn tài nguyên và tránh đọc tràn sang khung tiếp theo.
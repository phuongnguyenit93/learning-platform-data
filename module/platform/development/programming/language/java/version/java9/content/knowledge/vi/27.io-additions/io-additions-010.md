# Kiểm thử dữ liệu rỗng, dữ liệu lớn và lỗi giữa chừng

Khi làm việc với luồng vào/ra (I/O), một chương trình chạy đúng với tệp nhỏ và đầy đủ chưa chắc xử lý đúng dữ liệu rỗng, nguồn rất lớn hoặc lỗi xuất hiện sau khi đã đọc/ghi một phần. Các tình huống này cần được kiểm thử có chủ đích vì chúng ảnh hưởng đến tính đúng đắn của dữ liệu, bộ nhớ và việc giải phóng tài nguyên.

Bài này tập trung vào `InputStream` và `OutputStream`, với các API hiện hành từ Java 9 như `readAllBytes()` và `transferTo()`. Ví dụ kiểm thử chạy độc lập bằng JDK 17, không cần thư viện bên ngoài; các API được dùng cũng có từ Java 9.

## 1. Ba nhóm tình huống phải kiểm thử

| Tình huống | Điều cần xác nhận | Lỗi thường bị bỏ sót |
| --- | --- | --- |
| Dữ liệu rỗng | Kết quả rỗng hợp lệ, không truy cập phần tử hoặc tạo dữ liệu giả | Nhầm EOF với lỗi; trả `null` thay vì mảng rỗng |
| Dữ liệu lớn | Xử lý đủ dữ liệu với bộ nhớ có giới hạn và bộ đếm đủ lớn | Đọc toàn bộ vào RAM, tràn bộ đếm `int`, bỏ sót phần cuối |
| Lỗi giữa chừng | Exception được truyền đúng, tài nguyên được đóng và trạng thái đầu ra được hiểu rõ | Giả định dữ liệu chưa được ghi; rò rỉ stream; tiếp tục từ vị trí không còn đồng bộ |

Không nên chỉ kiểm thử trường hợp thành công. Với I/O, cần xác minh cả số byte, nội dung, trạng thái tài nguyên và hành vi khi thao tác dừng giữa chừng.

## 2. Dữ liệu rỗng và dấu hiệu EOF

Với `InputStream`, `read()` trả `-1` khi đã đến cuối luồng. Nếu gọi `read(byte[], offset, length)` với `length` lớn hơn `0`, phương thức có thể trả về ít byte hơn số lượng yêu cầu; nếu không còn byte nào để đọc, nó trả `-1`. Yêu cầu đọc có độ dài `0` trả `0`, vì vậy không được nhầm `0` trong trường hợp đó với EOF.

Java 9 bổ sung `InputStream.readAllBytes()`. Với một stream rỗng, phương thức trả về `byte[]` có độ dài `0`:

```java
try (InputStream input = new ByteArrayInputStream(new byte[0])) {
    byte[] data = input.readAllBytes();
    System.out.println(data.length);
}
```

Kết quả:

```text
0
```

Với `transferTo`, stream rỗng không ghi byte nào và số byte trả về là `0`:

```java
try (InputStream input = new ByteArrayInputStream(new byte[0]);
     ByteArrayOutputStream output = new ByteArrayOutputStream()) {
    long copied = input.transferTo(output);
    System.out.println(copied);
    System.out.println(output.size());
}
```

Kết quả:

```text
0
0
```

Phân biệt các trạng thái sau:

- **Stream rỗng:** nguồn hợp lệ nhưng không có byte nào; kết quả đọc là dữ liệu rỗng.
- **EOF:** đã đọc hết dữ liệu; `read()` trả `-1` khi không còn byte.
- **Tham chiếu null:** không có đối tượng stream; đây là lỗi đầu vào riêng, thường được xác thực bằng `Objects.requireNonNull`.
- **I/O failure:** thao tác đọc không hoàn tất do `IOException`; không được chuyển lỗi này thành dữ liệu rỗng nếu nghiệp vụ không quy định rõ.

Một tệp có kích thước `0` khác với đường dẫn không tồn tại hoặc không có quyền đọc. Hãy tạo kiểm thử riêng cho các trường hợp đó khi API của ứng dụng xử lý đường dẫn.

## 3. Đừng giả định một lần đọc sẽ lấy đủ dữ liệu

`InputStream.read(byte[], offset, length)` được phép trả về ít byte hơn `length`, dù stream chưa đến EOF. Điều này thường xảy ra với luồng mạng, pipe, stream được bọc hoặc nguồn dữ liệu chia thành nhiều khối.

Vì vậy, không viết logic dựa trên giả định rằng một lần `read` sẽ lấp đầy toàn bộ buffer:

```java
byte[] buffer = new byte[8192];
int count = input.read(buffer);
// count có thể nhỏ hơn buffer.length mà chưa phải EOF.
```

Với `readAllBytes()` hoặc `transferTo()`, việc lặp đọc được API xử lý. Nếu tự viết vòng lặp, phải tiếp tục đọc cho đến khi gặp `-1` và xử lý mọi `IOException`:

```java
byte[] buffer = new byte[8192];
int count;
while ((count = input.read(buffer)) != -1) {
    output.write(buffer, 0, count);
}
```

Không dùng `count == buffer.length` làm điều kiện kết thúc. Một lần đọc ngắn không có nghĩa là đã hết dữ liệu.

Để kiểm thử trường hợp này một cách ổn định, tạo một `InputStream` giả chỉ trả tối đa vài byte trong mỗi lần gọi. Không cần dựa vào mạng hoặc thiết bị thật để tạo ra short read.

## 4. Dữ liệu lớn: giới hạn bộ nhớ và dùng bộ đếm `long`

`readAllBytes()` tiện lợi khi dữ liệu có kích thước vừa phải và có thể giữ toàn bộ trong bộ nhớ. Với dữ liệu lớn hoặc không biết trước kích thước, việc tạo một `byte[]` chứa toàn bộ nội dung có thể làm tăng áp lực heap và dẫn đến `OutOfMemoryError`.

Để sao chép hoặc xử lý dữ liệu lớn, hãy dùng luồng và buffer có kích thước cố định. Java 9 bổ sung `InputStream.transferTo(OutputStream)`, phương thức này chuyển dữ liệu đến output stream và trả về tổng số byte đã truyền dưới dạng `long`:

```java
try (InputStream input = Files.newInputStream(sourcePath);
     OutputStream output = Files.newOutputStream(destinationPath)) {
    long bytesCopied = input.transferTo(output);
    System.out.println(bytesCopied);
}
```

`transferTo` không đóng input hoặc output stream. `try-with-resources` ở ví dụ trên chịu trách nhiệm đóng cả hai khi hoàn tất hoặc khi có exception.

Khi tự viết vòng lặp, dùng `long` cho tổng số byte vì dữ liệu có thể vượt giới hạn của `int`:

```java
byte[] buffer = new byte[8192];
long total = 0L;
int count;

while ((count = input.read(buffer)) != -1) {
    output.write(buffer, 0, count);
    total += count;
}
```

Buffer có kích thước cố định giúp lượng bộ nhớ do vòng lặp sử dụng không tăng theo tổng kích thước nguồn. Tuy nhiên, bộ nhớ thực tế còn phụ thuộc vào output stream và các lớp bọc bên dưới; chẳng hạn `ByteArrayOutputStream` vẫn tích lũy toàn bộ dữ liệu trong RAM.

### Kiểm thử dữ liệu lớn mà không tạo một mảng khổng lồ

Không cần cấp phát trước một mảng 32 MiB hoặc vài GB chỉ để kiểm thử đường truyền. Có thể tạo một `InputStream` sinh byte theo yêu cầu và một `OutputStream` chỉ đếm, kiểm tra byte rồi bỏ đi. Cách này kiểm tra được số byte và nội dung mà không lưu toàn bộ đầu ra.

Trong ví dụ hoàn chỉnh ở phần sau, stream giả sinh 32 MiB byte `0x5A`. Output stream kiểm tra mọi byte nhận được và đếm bằng `long`. Nếu thiếu byte hoặc sai nội dung, kiểm thử sẽ thất bại.

### Các kích thước biên nên có

- `0` byte: xác nhận xử lý dữ liệu rỗng.
- `1` byte: xác nhận trường hợp nhỏ nhất có dữ liệu.
- Nhỏ hơn buffer một byte, đúng bằng buffer và lớn hơn buffer một byte.
- Nhiều buffer liên tiếp, có phần dư ở buffer cuối.
- Kích thước lớn hơn giới hạn `int` khi hệ thống hỗ trợ kiểm thử stream sinh dữ liệu và bộ đếm `long`.

Kiểm thử các kích thước sát biên giúp phát hiện lỗi chỉ xuất hiện khi vòng lặp xử lý buffer cuối hoặc khi phép đếm vượt giới hạn kiểu số.

## 5. Lỗi giữa chừng khi đọc

Một stream có thể đọc được một số byte rồi ném `IOException`. Đây là tình huống cần kiểm thử riêng vì chương trình đã có dữ liệu một phần trước khi thao tác thất bại.

Ví dụ, nguồn có tám byte nhưng được cấu hình để ném lỗi sau khi phát ra năm byte. Khi dùng `transferTo`, năm byte đầu có thể đã được ghi sang output trước khi lần đọc tiếp theo thất bại.

Những điều cần xác nhận:

1. `IOException` được truyền ra hoặc được xử lý theo hợp đồng của phương thức.
2. Không biến lỗi đọc thành EOF hoặc kết quả thành công giả.
3. Những byte đã chuyển trước lỗi được xem là dữ liệu một phần.
4. Các stream được đóng trong `finally` hoặc `try-with-resources`.
5. Nếu cần thử lại, phải có chiến lược xác định vị trí đọc lại; không giả định mọi stream đều hỗ trợ `mark/reset` hoặc seek.

Không nên phụ thuộc vào lỗi I/O thật để kiểm thử. Một `InputStream` giả có thể phát ra đúng N byte rồi ném một `IOException` có thông điệp xác định, giúp bài kiểm thử lặp lại ổn định.

## 6. Lỗi giữa chừng khi ghi

Output stream cũng có thể ném `IOException` sau khi đã nhận một phần dữ liệu. Khi đó, đích có thể đã chứa một phần nội dung.

Ví dụ, một output stream giả nhận năm byte rồi ném lỗi ở lần ghi tiếp theo. `transferTo` truyền exception ra ngoài; phương thức không hoàn tác năm byte đã ghi và cũng không trả về số byte hoàn tất vì lời gọi kết thúc bằng exception.

Điều này có ý nghĩa quan trọng với việc ghi tệp hoặc gửi dữ liệu qua mạng:

- Không giả định thao tác thất bại đồng nghĩa với đích vẫn rỗng.
- Không tự động ghi tiếp vào cùng đích nếu chưa xác định trạng thái hiện tại và giao thức cho phép tiếp tục.
- Với tệp cần công bố toàn bộ hoặc không công bố, hãy ghi vào tệp tạm; chỉ chuyển tệp tạm thành tệp đích sau khi ghi và đóng thành công.
- Với giao thức mạng, cần định danh yêu cầu, offset hoặc cơ chế xác nhận để tránh gửi lặp hoặc thiếu dữ liệu khi thử lại.

Trong ví dụ kiểm thử, output stream giả giữ lại số byte đã nhận trước exception. Kiểm thử xác nhận chính xác năm byte được ghi và lỗi không bị nuốt.

## 7. Quản lý tài nguyên khi có lỗi

`InputStream.readAllBytes()` và `InputStream.transferTo()` không tự đóng stream. Người gọi vẫn phải chịu trách nhiệm quản lý vòng đời của input và output.

`try-with-resources` bảo đảm các tài nguyên được đóng khi khối lệnh kết thúc bình thường hoặc bằng exception:

```java
try (InputStream input = Files.newInputStream(sourcePath);
     OutputStream output = Files.newOutputStream(destinationPath)) {
    input.transferTo(output);
}
```

Nếu thao tác đọc hoặc ghi ném exception, Java vẫn gọi `close()` cho các tài nguyên đã mở. Nếu việc đóng cũng ném exception trong lúc một exception chính đang được truyền ra, lỗi đóng được ghi nhận dưới dạng suppressed exception.

Kiểm thử lỗi giữa chừng nên dùng stream giả có cờ `closed` để xác nhận `close()` đã được gọi. Chỉ kiểm tra exception xuất hiện là chưa đủ; cần xác nhận tài nguyên không bị rò rỉ.

## 8. Chương trình kiểm thử hoàn chỉnh với Java 17

Chương trình sau không cần JUnit hoặc thư viện ngoài. Nó kiểm thử stream rỗng, short read, truyền 32 MiB với bộ nhớ giới hạn, lỗi khi đọc và lỗi khi ghi. Các stream giả được tạo ngay trong chương trình để lỗi luôn xuất hiện tại đúng vị trí.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Objects;

public class Main {
    public static void main(String[] args) throws Exception {
        testEmptyInput();
        testPartialReads();
        testLargeTransfer();
        testReadFailure();
        testWriteFailure();
    }

    private static void testEmptyInput() throws IOException {
        try (InputStream input = new ByteArrayInputStream(new byte[0])) {
            check(input.readAllBytes().length == 0, "empty readAllBytes");
        }

        try (InputStream input = new ByteArrayInputStream(new byte[0]);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            check(input.transferTo(output) == 0L, "empty transfer count");
            check(output.size() == 0, "empty transfer output");
        }
        System.out.println("empty input: 0 bytes");
    }

    private static void testPartialReads() throws IOException {
        byte[] expected = "partial reads are normal".getBytes(StandardCharsets.US_ASCII);
        try (InputStream input = new ChunkedInputStream(expected, 2)) {
            byte[] actual = input.readAllBytes();
            check(Arrays.equals(expected, actual), "partial read content");
        }
        System.out.println("short reads: content preserved");
    }

    private static void testLargeTransfer() throws IOException {
        long expectedSize = 32L * 1024L * 1024L;
        try (InputStream input = new GeneratedInputStream(expectedSize, (byte) 0x5A);
             CountingOutputStream output = new CountingOutputStream((byte) 0x5A)) {
            long transferred = input.transferTo(output);
            check(transferred == expectedSize, "large transfer return count");
            check(output.count == expectedSize, "large transfer output count");
        }
        System.out.println("large transfer: 33554432 bytes verified with bounded memory");
    }

    private static void testReadFailure() throws IOException {
        FailingInputStream input = new FailingInputStream(
            "abcdefgh".getBytes(StandardCharsets.US_ASCII), 5);
        TrackingByteArrayOutputStream output = new TrackingByteArrayOutputStream();
        boolean failed = false;

        try (input; output) {
            input.transferTo(output);
        } catch (IOException ex) {
            failed = "simulated read failure".equals(ex.getMessage());
        }

        check(failed, "read failure propagated");
        check("abcde".equals(new String(output.toByteArray(), StandardCharsets.US_ASCII)),
            "read failure partial output");
        check(input.closed, "read-failing source closed");
        check(output.closed, "read-failing destination closed");
        System.out.println("read failure: propagated after 5 bytes; partial output retained; resources closed");
    }

    private static void testWriteFailure() throws IOException {
        TrackingByteArrayInputStream input = new TrackingByteArrayInputStream(
            "abcdefgh".getBytes(StandardCharsets.US_ASCII));
        FailingOutputStream output = new FailingOutputStream(5);
        boolean failed = false;

        try (input; output) {
            input.transferTo(output);
        } catch (IOException ex) {
            failed = "simulated write failure".equals(ex.getMessage());
        }

        check(failed, "write failure propagated");
        check(output.accepted == 5, "write failure partial output");
        check(input.closed, "write-failing source closed");
        check(output.closed, "write-failing destination closed");
        System.out.println("write failure: propagated after 5 bytes; partial output retained; resources closed");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static final class ChunkedInputStream extends ByteArrayInputStream {
        private final int maxChunk;

        ChunkedInputStream(byte[] data, int maxChunk) {
            super(data);
            this.maxChunk = maxChunk;
        }

        @Override
        public synchronized int read(byte[] buffer, int offset, int length) {
            return super.read(buffer, offset, Math.min(length, maxChunk));
        }
    }

    private static final class GeneratedInputStream extends InputStream {
        private long remaining;
        private final byte value;

        GeneratedInputStream(long size, byte value) {
            this.remaining = size;
            this.value = value;
        }

        @Override
        public int read() {
            if (remaining == 0L) {
                return -1;
            }
            remaining--;
            return value & 0xFF;
        }

        @Override
        public int read(byte[] buffer, int offset, int length) {
            Objects.checkFromIndexSize(offset, length, buffer.length);
            if (length == 0) {
                return 0;
            }
            if (remaining == 0L) {
                return -1;
            }
            int count = (int) Math.min((long) length, remaining);
            Arrays.fill(buffer, offset, offset + count, value);
            remaining -= count;
            return count;
        }
    }

    private static final class CountingOutputStream extends OutputStream {
        private final byte expected;
        private long count;

        CountingOutputStream(byte expected) {
            this.expected = expected;
        }

        @Override
        public void write(int value) throws IOException {
            if ((byte) value != expected) {
                throw new IOException("unexpected byte");
            }
            count++;
        }

        @Override
        public void write(byte[] buffer, int offset, int length) throws IOException {
            Objects.checkFromIndexSize(offset, length, buffer.length);
            for (int i = offset; i < offset + length; i++) {
                if (buffer[i] != expected) {
                    throw new IOException("unexpected byte");
                }
            }
            count += length;
        }
    }

    private static final class FailingInputStream extends InputStream {
        private final byte[] data;
        private final int failAfter;
        private int position;
        private boolean closed;

        FailingInputStream(byte[] data, int failAfter) {
            this.data = data;
            this.failAfter = failAfter;
        }

        @Override
        public int read() throws IOException {
            if (position >= failAfter) {
                throw new IOException("simulated read failure");
            }
            if (position >= data.length) {
                return -1;
            }
            return data[position++] & 0xFF;
        }

        @Override
        public int read(byte[] buffer, int offset, int length) throws IOException {
            Objects.checkFromIndexSize(offset, length, buffer.length);
            if (length == 0) {
                return 0;
            }
            if (position >= failAfter) {
                throw new IOException("simulated read failure");
            }
            if (position >= data.length) {
                return -1;
            }
            int count = Math.min(length, Math.min(failAfter - position, data.length - position));
            System.arraycopy(data, position, buffer, offset, count);
            position += count;
            return count;
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    private static final class TrackingByteArrayOutputStream extends ByteArrayOutputStream {
        private boolean closed;

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    private static final class TrackingByteArrayInputStream extends ByteArrayInputStream {
        private boolean closed;

        TrackingByteArrayInputStream(byte[] data) {
            super(data);
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    private static final class FailingOutputStream extends OutputStream {
        private final int failAfter;
        private int accepted;
        private boolean closed;

        FailingOutputStream(int failAfter) {
            this.failAfter = failAfter;
        }

        @Override
        public void write(int value) throws IOException {
            if (accepted >= failAfter) {
                throw new IOException("simulated write failure");
            }
            accepted++;
        }

        @Override
        public void write(byte[] buffer, int offset, int length) throws IOException {
            Objects.checkFromIndexSize(offset, length, buffer.length);
            for (int i = 0; i < length; i++) {
                write(buffer[offset + i]);
            }
        }

        @Override
        public void close() {
            closed = true;
        }
    }
}
```

Lưu mã thành `Main.java`, biên dịch và chạy:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Stdout chính xác:

```text
empty input: 0 bytes
short reads: content preserved
large transfer: 33554432 bytes verified with bounded memory
read failure: propagated after 5 bytes; partial output retained; resources closed
write failure: propagated after 5 bytes; partial output retained; resources closed
```

Chương trình không lưu 32 MiB vào một mảng hoặc `ByteArrayOutputStream`. `GeneratedInputStream` tạo từng buffer khi được đọc, còn `CountingOutputStream` kiểm tra byte và chỉ giữ bộ đếm `long`.

## 9. Kiểm thử tệp thật và nội dung văn bản

Stream giả giúp kiểm soát chính xác thời điểm short read hoặc exception xảy ra. Sau đó, nên có thêm kiểm thử tích hợp với tệp tạm để xác nhận cách ứng dụng mở, đọc, ghi và dọn dẹp tệp.

Với tệp đầu ra quan trọng, một quy trình an toàn thường là:

1. Tạo tệp tạm trong cùng filesystem với tệp đích.
2. Stream dữ liệu vào tệp tạm và kiểm tra số byte hoặc checksum nếu hợp đồng yêu cầu.
3. Đóng thành công output stream.
4. Chỉ sau khi toàn bộ thao tác thành công mới chuyển tệp tạm sang tên đích.
5. Nếu có lỗi, xóa tệp tạm và giữ trạng thái tệp đích theo chính sách của ứng dụng.

`Files.move` với `StandardCopyOption.ATOMIC_MOVE` có thể dùng khi filesystem hỗ trợ thao tác di chuyển nguyên tử; ứng dụng cần xác định cách xử lý nếu filesystem không hỗ trợ. Không nên tuyên bố một lần ghi trực tiếp vào tệp đích là giao dịch nguyên tử.

Với dữ liệu văn bản, hãy phân biệt byte và ký tự. UTF-8 có thể dùng nhiều byte cho một ký tự; số byte đọc không bằng số ký tự. Dùng `InputStreamReader`/`OutputStreamWriter` với `StandardCharsets.UTF_8` hoặc charset được giao thức quy định, không dựa vào charset mặc định của máy.

Kiểm thử văn bản nên có ký tự ASCII, ký tự nhiều byte, ký tự ở cuối buffer và dữ liệu rỗng. Nếu một luồng byte bị ngắt giữa một chuỗi mã hóa, decoder có thể báo lỗi hoặc xử lý theo `CodingErrorAction`; hành vi này cần phù hợp với hợp đồng dữ liệu.

## 10. Cách tổ chức bộ kiểm thử

Một bộ kiểm thử I/O thực tế nên chia rõ các nhóm:

| Nhóm | Dữ liệu/điều kiện | Kỳ vọng |
| --- | --- | --- |
| Empty | 0 byte, tệp rỗng | Kết quả rỗng, không phát sinh dữ liệu giả |
| Small | 1 byte và vài byte | Nội dung khớp tuyệt đối |
| Short read | Mỗi lần trả tối đa 1–3 byte | Vòng lặp vẫn đọc đủ đến EOF |
| Buffer boundary | `bufferSize - 1`, `bufferSize`, `bufferSize + 1` | Không mất hoặc lặp byte ở ranh giới buffer |
| Large | Nhiều buffer, bộ đếm `long` | Đủ số byte, bộ nhớ không tăng theo toàn bộ nguồn |
| Read failure | Ném `IOException` sau N byte | Exception được truyền; đầu ra một phần được nhận diện |
| Write failure | Từ chối ghi sau N byte | Exception được truyền; không giả định đích rỗng |
| Resource | Thành công và thất bại | Tất cả tài nguyên được đóng |
| Text encoding | ASCII và ký tự UTF-8 nhiều byte | Nội dung sau giải mã đúng theo charset |

Đối với dữ liệu lớn, nên xác minh cả số byte và tính toàn vẹn nội dung. Bộ đếm chỉ phát hiện thiếu/thừa byte; checksum hoặc so sánh nội dung mẫu còn giúp phát hiện dữ liệu sai thứ tự hoặc bị thay đổi.

## 11. Lỗi thường gặp

1. **Coi stream rỗng là lỗi.** Stream rỗng hợp lệ và thường trả về mảng rỗng hoặc số byte truyền bằng `0`.
2. **Coi một lần đọc ngắn là EOF.** Chỉ `-1` mới biểu thị EOF cho một lần đọc có độ dài yêu cầu lớn hơn `0`.
3. **Dùng `readAllBytes()` cho dữ liệu không giới hạn.** Phương thức giữ toàn bộ kết quả trong bộ nhớ; dùng cách xử lý theo buffer hoặc `transferTo` với đích phù hợp.
4. **Dùng `int` cho tổng byte.** Luồng lớn có thể vượt giới hạn `int`; dùng `long` cho tổng số byte.
5. **Nuốt `IOException` rồi trả kết quả thành công.** Nếu lỗi ảnh hưởng đến dữ liệu, phải truyền lỗi hoặc biểu diễn trạng thái thất bại theo hợp đồng.
6. **Cho rằng lỗi ghi sẽ hoàn tác dữ liệu đã ghi.** Output có thể đã nhận một phần nội dung trước khi exception xảy ra.
7. **Cho rằng `transferTo` tự đóng stream.** Người gọi phải quản lý vòng đời bằng `try-with-resources` hoặc cơ chế tương đương.
8. **Thử lỗi bằng cách ngắt mạng hoặc rút thiết bị trong kiểm thử tự động.** Dùng stream giả để tạo lỗi xác định; kiểm thử thiết bị thật là một lớp tích hợp riêng.
9. **Chỉ kiểm tra số byte.** Dữ liệu đủ độ dài vẫn có thể sai nội dung; hãy so sánh byte hoặc kiểm tra checksum.
10. **So sánh số byte với số ký tự.** Với UTF-8, một ký tự có thể chiếm nhiều byte; kiểm tra theo đúng đơn vị của API.
11. **Tiếp tục ghi vào tệp đích sau lỗi mà không xác minh trạng thái.** Dùng tệp tạm và chỉ công bố sau khi ghi hoàn tất nếu cần kết quả toàn vẹn.

## 12. Ghi nhớ

1. Stream rỗng là dữ liệu hợp lệ; `readAllBytes()` trả mảng rỗng và `transferTo()` trả `0`.
2. Một lần đọc có thể trả ít byte hơn buffer; chỉ `-1` biểu thị EOF.
3. Dữ liệu lớn nên được xử lý theo buffer, dùng `long` để đếm và tránh giữ toàn bộ nguồn trong RAM.
4. Java 9 cung cấp `readAllBytes()` và `transferTo()`; các phương thức này không tự đóng stream.
5. Lỗi giữa chừng có thể để lại dữ liệu đầu ra một phần; exception không tự hoàn tác các byte đã ghi.
6. Dùng stream giả để kiểm thử short read, read failure và write failure tại vị trí xác định.
7. Dùng `try-with-resources` để đóng tài nguyên ngay cả khi có exception.
8. Kiểm tra cả nội dung, số byte, trạng thái đóng tài nguyên và dọn dẹp tệp tạm.
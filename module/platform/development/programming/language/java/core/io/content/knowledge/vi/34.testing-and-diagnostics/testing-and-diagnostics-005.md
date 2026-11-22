# Java I/O: kiểm thử tệp rỗng, tệp lớn, EOF sớm và bản ghi không hoàn chỉnh

## 1. Vì sao phải kiểm thử các trường hợp biên?

Code đọc/ghi file có thể chạy đúng với một file nhỏ, đầy đủ dữ liệu, nhưng hỏng khi dữ liệu ít hơn mong đợi hoặc vượt giới hạn bộ nhớ. Những lỗi này thường xuất hiện khi tải lên tệp, xử lý log, đọc bản ghi nhị phân, truyền file, phục hồi sau crash hay đọc file được ứng dụng khác ghi đồng thời.

Những trường hợp tiêu biểu:

- File **0 byte** không có header, nhưng format yêu cầu header.
- Header cho biết payload dài **0 byte**, đây có thể là **một bản ghi hợp lệ**.
- Một lần `read(...)` trả ít byte hơn buffer yêu cầu, không phải EOF.
- EOF xuất hiện khi header mới có 1–3 byte, hoặc khi payload chưa đủ.
- File dài nhiều GiB nhưng code ép `long` sang `int` rồi cấp phát một mảng.
- Length prefix bị âm hoặc quá lớn; cấp phát ngay có thể gây `NegativeArraySizeException`/`OutOfMemoryError`.
- Reader mở file đang được writer append/truncate; `Files.size(...)` không còn mô tả snapshot ổn định.
- Writer crash giữa record, khiến file chứa header hợp lệ nhưng payload mới chỉ ghi một phần.
- Code nhầm `read()==0` với `read()==-1`, hoặc gọi `ByteBuffer.getInt()` trước khi đủ bốn byte.
- Bản ghi đủ byte nhưng bị hỏng dữ liệu; chỉ kiểm tra kích thước không đủ phát hiện.

Bài này xây dựng một contract đơn giản để giải thích, kèm chương trình Java 17+ tự tạo fixture và kiểm tra **đúng trường hợp nào phải thành công, trường hợp nào phải thất bại**.

## 2. Định dạng nhị phân ví dụ và nguyên tắc EOF

Giả sử file chỉ chứa **đúng một bản ghi**:

~~~text
+----------------------------+--------------------------+
| Header: 4 byte, big-endian | Payload: length byte     |
| int length >= 0            | có thể rỗng nếu length=0 |
+----------------------------+--------------------------+
   file offsets [0,4)             file offsets [4,4+N)
~~~

Ví dụ:
- `00 00 00 02 4F 4B`: payload dài 2 byte, nội dung ASCII `OK`.
- `00 00 00 00`: **một record hoàn chỉnh** chứa payload rỗng.
- File 0 byte: **không có record**, lỗi nếu định dạng buộc phải có một record.
- `00 00`: **header bị cắt**, vì mới có 2/4 byte.
- `00 00 00 05 41 42`: header công bố 5 byte payload, thực tế chỉ có 2; **record thiếu**.

Cần phân biệt **EOF hợp lệ ở ranh giới** và **EOF sớm trong record**:

~~~text
Multi-record:
  [record #1 complete][record #2 complete][EOF]
    -> Kết thúc hợp lệ nếu format cho phép nhiều record.

  [record #1 complete][2/4 byte header #2][EOF]
    -> TRUNCATED_HEADER.

  [record #1 complete][header #2 says 5][2 payload bytes][EOF]
    -> TRUNCATED_PAYLOAD.
~~~

Chính sách của chương trình demo là **single-record file**, nên sau payload còn bất kỳ byte nào cũng là lỗi `TRAILING_BYTES`. Parser multi-record sẽ khác: tiếp tục tìm header kế tiếp, và chỉ coi EOF là bình thường khi chưa nhận byte nào của header tiếp theo.

## 3. EOF, short read và read trả 0 không giống nhau

### InputStream

`InputStream.read()` trả:
- `0..255` khi đọc được một byte.
- `-1` khi hết stream.

`InputStream.read(byte[], off, len)` trả số byte đã đọc, có thể **nhỏ hơn len**. Khi `len == 0`, nó có thể trả `0` ngay. Không giả định một lệnh `read` luôn đọc đủ length.

`InputStream.readNBytes(int n)` trả mảng có thể **ngắn hơn n** nếu EOF đến trước. Nếu cần chính xác n byte, kiểm tra mảng/giá trị thực nhận. `DataInputStream.readFully(byte[])` sẽ cố đọc đủ hoặc ném `EOFException` khi không đủ.

~~~java
// Minh họa: in là DataInputStream, expected được kiểm tra.
if (expected < 0 || expected > MAX_RECORD_BYTES) {
    throw new IOException("Invalid length");
}
byte[] payload = new byte[expected];
in.readFully(payload); // Thiếu payload => EOFException.
~~~

Đoạn trên chưa độc lập vì `expected`, `MAX_RECORD_BYTES` và `in` phải được định nghĩa. Không dùng `readFully` với length prefix chưa kiểm tra vì array đã được cấp phát trước lời gọi.

### FileChannel và ByteBuffer

`FileChannel.read(ByteBuffer dst)` trả:
- Giá trị dương khi có thêm n byte và cập nhật `dst.position()`.
- `-1` khi EOF.
- `0` khi không đọc được byte trong lượt đó; với file thông thường đang đọc buffer còn chỗ, điều này không phải tín hiệu EOF.

~~~java
int n = channel.read(buffer);
if (n < 0) {
    // EOF.
} else if (n == 0) {
    // Chưa có tiến triển.
} else {
    // n byte mới được nạp, position tăng n.
}
~~~

**Không biến `0` thành `-1`**. Với `SocketChannel` ở non-blocking mode, 0 là tình huống thường gặp; cần chờ Selector/readiness thay vì spin. Với `FileChannel`, code kiểm thử có thể fail rõ ràng nếu lặp mà không tiến triển để tránh treo vô hạn.

### Read-exactly là một vòng lặp, không phải một lần read

~~~java
// Minh họa: FileChannel đang mở, dst đã cấp phát.
static int readUpTo(FileChannel channel, ByteBuffer dst)
        throws IOException {
    int total = 0;
    while (dst.hasRemaining()) {
        int n = channel.read(dst);
        if (n == -1) {
            break;
        }
        if (n == 0) {
            throw new IOException("no read progress");
        }
        total += n;
    }
    return total;
}
~~~

Hàm trả số byte thực nhận. Caller biết độ dài kỳ vọng và phân loại:
- Header cần 4, nhận 0 ở lần đầu ⇒ EMPTY_FILE hoặc normal EOF tùy contract.
- Header cần 4, nhận 1–3 rồi EOF ⇒ TRUNCATED_HEADER.
- Payload cần N, nhận k nhỏ hơn N rồi EOF ⇒ TRUNCATED_PAYLOAD.

## 4. ByteBuffer: position, limit và flip

Một lỗi phổ biến:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
channel.read(header);
int length = header.getInt(); // Sai: chưa biết đủ byte, chưa flip.
~~~

Khi ghi vào ByteBuffer, `position()` dịch về phía cuối. Phải kiểm tra đủ dữ liệu rồi `flip()` để chuyển sang chế độ đọc:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
int actual = readUpTo(channel, header);
if (actual != 4) {
    throw new EOFException("incomplete header: " + actual + "/4");
}
header.flip();
int length = header.getInt();
~~~

Trong parser nhiều record, `compact()` giữ những byte còn lại chưa parse sau một lượt đọc, trong khi `clear()` sẽ làm vùng dữ liệu còn lại bị coi như không cần giữ nữa. Dùng sai `clear()` khi buffer đã chứa nửa header của record kế tiếp sẽ gây mất dữ liệu dù file không bị hỏng.

## 5. Validate length trước khi allocate

Header nhị phân có thể chứa số âm hoặc cực lớn. Đừng viết:

~~~java
int length = header.getInt();
byte[] bytes = new byte[length]; // Không giới hạn, không an toàn.
~~~

Thay bằng:

~~~java
int length = header.getInt();
if (length < 0 || length > MAX_RECORD_BYTES) {
    throw new IOException("invalid record length: " + length);
}
byte[] bytes = new byte[length];
~~~

`MAX_RECORD_BYTES` là giới hạn **theo giao thức và bộ nhớ ứng dụng**, không phải hằng số chuẩn của Java. Ví dụ demo đặt MAX=1024 để fixture dễ đọc; service thực cần định nghĩa theo workload và quota.

Các điều kiện quan trọng:
- `length == 0` có thể là payload rỗng hợp lệ, **khác file rỗng**.
- `length < 0` phải reject nếu format dùng signed nonnegative int.
- `length > MAX` phải reject **trước** cấp phát.
- Nếu cộng offset/length, tính bằng `long` để tránh tràn int.
- Nếu parser hỗ trợ unsigned 32-bit length, phải đặc tả riêng bằng `Integer.toUnsignedLong(length)` rồi kiểm giới hạn trước; **không tự suy ra signed và unsigned tương đương**.
- Không được báo thành công chỉ vì header hợp lệ; vẫn phải kiểm đủ payload và checksum nếu có.

## 6. Tệp rỗng và payload rỗng: bộ test tối thiểu

| Fixture | Kích thước file | Kết quả theo single-record contract |
|---|---:|---|
| File hoàn toàn rỗng | 0 | EMPTY_FILE |
| Header length 0 | 4 | COMPLETE, payload rỗng |
| Header length 0, thêm 1 byte | 5 | TRAILING_BYTES |
| Header chỉ có byte `00` | 1 | TRUNCATED_HEADER(1/4) |
| Header có 3 byte | 3 | TRUNCATED_HEADER(3/4) |
| Header length 1 + một byte | 5 | COMPLETE |
| Header length 1 + không có payload | 4 | TRUNCATED_PAYLOAD(0/1) |

Đây là test các ranh giới của **format**, không phải lỗi Files API. `Files.createTempFile` tạo file rỗng hợp lệ ở tầng filesystem; parser mới là nơi quyết định empty file có được chấp nhận hay không.

Không dùng `catch(EOFException e) { return new byte[0]; }` vì điều đó che giấu record thiếu và khiến payload rỗng hợp lệ không thể phân biệt với dữ liệu hỏng.

## 7. File lớn và nguy cơ tràn kiểu dữ liệu

Một file 3 GiB có kích thước lớn hơn `Integer.MAX_VALUE`. Trong Java:

- `Files.size(path)` trả `long`.
- `FileChannel.size()` trả `long`.
- `FileChannel.position(long)` và `read(dst, long offset)` xử lý offset kiểu long.
- `ByteBuffer.allocate(int capacity)` giới hạn bởi int và bộ nhớ.
- `Files.readAllBytes(path)` có giới hạn mảng/bộ nhớ, không phù hợp với file khổng lồ.

Sai:

~~~java
int size = (int) Files.size(path);
byte[] all = new byte[size];
~~~

Ép kiểu có thể cho số âm hoặc kích thước sai. Ngay cả file dưới 2 GiB, một mảng lớn vẫn có thể gây OOM.

Đúng hơn, đọc theo block:

~~~java
long total = 0L;
byte[] buffer = new byte[16 * 1024];

try (InputStream in = Files.newInputStream(path)) {
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n == 0) {
            throw new IOException("no stream progress");
        }
        total += n;
        // Xử lý/hash/chuyển từng chunk ở đây.
    }
}
~~~

Bộ nhớ đệm khoảng 16 KiB bất kể file có 5 MiB hay nhiều GiB, chưa kể bộ nhớ parser. Nếu file hoặc stream không đáng tin, đặt **quota tổng bytes** và deadline, không chỉ giới hạn kích thước từng chunk.

### Sparse files và test lớn hơn 2 GiB

Một số filesystem hỗ trợ sparse files: kích thước logic lớn mà không cần chiếm mọi block đĩa. Test với `RandomAccessFile.setLength(long)` hoặc ghi ở offset rất cao có thể kiểm logic long offset, nhưng:
- Không phải provider nào cũng hỗ trợ sparse theo cùng cách.
- File size logic lớn không chứng minh code streaming đúng với toàn bộ dữ liệu thực tế.
- Không được tạo fixture nhiều GiB bừa bãi trên CI hoặc volume sản xuất.
- Dùng test riêng cho long offset và test riêng cho dữ liệu streaming/throughput.

## 8. Chương trình Java 17+ hoàn chỉnh: tám trường hợp biên

Chương trình sau tạo fixture trong thư mục tạm, đọc **một record duy nhất** dạng `[int32 length][payload]` và in kết quả ổn định.

Các case gồm: file rỗng, payload rỗng, record hoàn chỉnh, header cắt, payload cắt, length quá lớn, dữ liệu thừa và file 5 MiB đọc streaming.

Lưu là **`IoBoundaryCasesDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.stream.Stream;

public class IoBoundaryCasesDemo {
    private static final int MAX_RECORD_BYTES = 1024;

    private static int readUpTo(FileChannel ch, ByteBuffer dst)
            throws IOException {
        int total = 0;
        while (dst.hasRemaining()) {
            int n = ch.read(dst);
            if (n < 0) {
                break; // EOF.
            }
            if (n == 0) {
                throw new IOException("no read progress");
            }
            total += n;
        }
        return total;
    }

    private static byte[] readOneRecord(Path file)
            throws IOException {
        try (FileChannel ch = FileChannel.open(
                file, StandardOpenOption.READ)) {

            ByteBuffer header = ByteBuffer.allocate(4);
            int headerCount = readUpTo(ch, header);

            if (headerCount == 0) {
                throw new EOFException("empty file");
            }
            if (headerCount < 4) {
                throw new EOFException(
                        "incomplete header: " + headerCount + "/4");
            }

            header.flip();
            int length = header.getInt();

            if (length < 0 || length > MAX_RECORD_BYTES) {
                throw new IOException(
                        "invalid record length: " + length);
            }

            byte[] payload = new byte[length];
            int payloadCount = readUpTo(
                    ch, ByteBuffer.wrap(payload));

            if (payloadCount < length) {
                throw new EOFException(
                        "incomplete payload: "
                        + payloadCount + "/" + length);
            }

            // Theo contract, file chỉ chứa một record.
            if (ch.read(ByteBuffer.allocate(1)) != -1) {
                throw new IOException("unexpected trailing bytes");
            }

            return payload;
        }
    }

    private static byte[] framed(byte[] payload) {
        return ByteBuffer.allocate(4 + payload.length)
                .putInt(payload.length)
                .put(payload)
                .array();
    }

    private static void testCase(
            Path dir, String label, byte[] input)
            throws IOException {

        Path file = Files.createTempFile(dir, "case-", ".bin");
        Files.write(file, input);

        try {
            byte[] value = readOneRecord(file);
            System.out.println(label + ": ok="
                    + new String(value, StandardCharsets.US_ASCII));
        } catch (IOException ex) {
            System.out.println(label + ": error="
                    + ex.getMessage());
        }
    }

    private static long largeStreamingCase(Path dir)
            throws IOException {
        Path file = Files.createTempFile(dir, "large-", ".bin");
        byte[] writeBuffer = new byte[8192];
        Arrays.fill(writeBuffer, (byte) 'x');

        try (OutputStream out = Files.newOutputStream(file)) {
            for (int i = 0; i < 640; i++) {
                out.write(writeBuffer);
            }
        }

        byte[] readBuffer = new byte[16 * 1024];
        long total = 0L;
        try (InputStream in = Files.newInputStream(file)) {
            int n;
            while ((n = in.read(readBuffer)) != -1) {
                if (n == 0) {
                    throw new IOException("no stream progress");
                }
                total += n;
            }
        }
        return total;
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("io-boundary-");

        try {
            testCase(dir, "empty-file", new byte[0]);
            testCase(dir, "empty-payload",
                    framed(new byte[0]));
            testCase(dir, "complete", framed(
                    "OK".getBytes(StandardCharsets.US_ASCII)));

            testCase(dir, "short-header",
                    new byte[] {0, 0});

            testCase(dir, "short-payload",
                    ByteBuffer.allocate(6)
                            .putInt(5)
                            .put((byte) 'A')
                            .put((byte) 'B')
                            .array());

            testCase(dir, "too-large",
                    ByteBuffer.allocate(4)
                            .putInt(MAX_RECORD_BYTES + 1)
                            .array());

            testCase(dir, "trailing",
                    ByteBuffer.allocate(6)
                            .putInt(1)
                            .put((byte) 'Q')
                            .put((byte) '!')
                            .array());

            System.out.println("large-file: bytes="
                    + largeStreamingCase(dir));
        } finally {
            // Directory chỉ chứa fixture do demo vừa tạo.
            try (Stream<Path> entries = Files.list(dir)) {
                for (Path p : entries.toList()) {
                    Files.deleteIfExists(p);
                }
            }
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac IoBoundaryCasesDemo.java
java IoBoundaryCasesDemo
~~~

**Stdout mong đợi khi thao tác với file tạm thành công:**

~~~text
empty-file: error=empty file
empty-payload: ok=
complete: ok=OK
short-header: error=incomplete header: 2/4
short-payload: error=incomplete payload: 2/5
too-large: error=invalid record length: 1025
trailing: error=unexpected trailing bytes
large-file: bytes=5242880
~~~

### Giải thích output và tính đúng đắn

1. `empty-file`: 0/4 byte header. Trong contract một record, không thể coi là bản ghi hợp lệ.
2. `empty-payload`: header đủ 4 byte, length=0, payload là mảng rỗng; output có `ok=` không kèm ký tự.
3. `complete`: 4 byte header và hai byte `OK`, đọc hết file sau payload.
4. `short-header`: chỉ 2 byte, parser báo chính xác 2/4 thay vì getInt khi thiếu.
5. `short-payload`: header công bố 5 byte, chỉ có hai byte A/B; parser báo 2/5.
6. `too-large`: length=1025 vượt MAX=1024; reject **trước allocate**.
7. `trailing`: length=1 chỉ nhận Q, byte `!` thừa làm file sai single-record contract.
8. `large-file`: 640 lần ghi khối 8192 byte = **5.242.880 byte**, đọc bằng buffer 16 KiB, không cấp phát mảng theo file size.

Chương trình cố tình dùng `FileChannel` bình thường, không dùng `SocketChannel` non-blocking. Ở socket không blocking, `read()==0` là trạng thái thường gặp và cần quay lại event loop; không ném IOException như helper của demo.

Dữ liệu demo chỉ dùng ASCII và fixed big-endian header để stdout không phụ thuộc locale/charset hệ điều hành. Thư mục và file tạm được dọn sau cả đường thành công lẫn exception thông thường; JVM crash/kill vẫn có thể để lại fixture, như mọi loại cleanup dựa trên finally.

## 9. Đọc một file chứa nhiều record

Nếu file có các record nối tiếp, ta không thể dùng cùng hàm `readOneRecord` bởi nó cấm trailing bytes. Thay vào đó:

~~~text
LOOP:
   đọc header 4 byte
      - 0 byte rồi EOF      -> END_OF_STREAM (bình thường)
      - 1..3 byte rồi EOF   -> TRUNCATED_HEADER (lỗi)
      - đủ 4 byte          -> kiểm length
   đọc payload length byte
      - thiếu rồi EOF       -> TRUNCATED_PAYLOAD (lỗi)
      - đủ                  -> COMPLETE(frame), xử lý record
   quay lại LOOP
~~~

Nên có các kiểu kết quả hoặc error codes rõ ràng:
`END_OF_STREAM_AT_BOUNDARY`, `TRUNCATED_HEADER`, `INVALID_LENGTH`, `TRUNCATED_PAYLOAD`, `CHECKSUM_MISMATCH` và `IO_FAILURE`.

Nếu đó là append-only log, EOF tại tail cần xét hoàn cảnh: writer có thể **đang tiếp tục ghi**, khác với một snapshot file đã commit nhưng bị thiếu. Recovery có thể cho phép bỏ một tail chưa commit **chỉ nếu giao thức log đã thiết kế như thế**, không tự ý truncate mọi file gặp EOF.

## 10. Partial write và file bị cắt giữa chừng

Nguyên nhân record thiếu thường đến từ phía ghi:

~~~java
// Mã minh họa: channel FileChannel mở WRITE, buffer đã chuẩn bị.
while (buffer.hasRemaining()) {
    int n = channel.write(buffer);
    if (n <= 0) {
        throw new IOException("no write progress");
    }
}
~~~

Một lần `write` không chắc ghi hết buffer. Nếu writer ghi header length=100 rồi chỉ ghi 60 byte payload trước khi crash, reader sẽ gặp EOF tại 60/100. Đừng biến lỗi đó thành một record “hợp lệ nhưng ngắn”.

Một thiết kế publish file hoàn chỉnh thường là:

1. Tạo file tạm cùng filesystem đích.
2. Ghi đủ dữ liệu, xử lý partial writes.
3. Kiểm tra độ dài, checksum và content format.
4. Chủ động `channel.force(...)` nếu cần durability theo hợp đồng storage tương ứng.
5. Đóng writer.
6. Công bố qua `Files.move(temp, target, ATOMIC_MOVE)` khi được hỗ trợ.
7. Reader vẫn phải kiểm record boundaries và checksum.

`ATOMIC_MOVE` **không tự đảm bảo durability sau crash**, cũng không phải transaction nhiều file. Trên filesystem mạng, cần xem xét thêm consistency và tính bền vững của server.

## 11. Checksum: đủ byte chưa chắc đúng nội dung

Một record có đủ header + payload nhưng bị sửa một byte vẫn có thể vượt qua mọi kiểm tra độ dài.

~~~text
Expected: length=4, payload=01 02 03 04
Actual:   length=4, payload=01 02 03 05
Cả hai đều có file size=8, nhưng nội dung khác.
~~~

Phương pháp thường dùng:
- **CRC32/CRC32C** để phát hiện nhiều lỗi ngẫu nhiên trong dữ liệu.
- **SHA-256** nếu cần hash mạnh để xác minh một nội dung cụ thể.
- **HMAC/chữ ký số** khi cần chống sửa có chủ ý và đối thủ có thể thay đổi cả file lẫn checksum.

Thứ tự trong parser nên là: kiểm magic/version nếu có → đọc đủ header → validate length → đọc đủ payload → validate checksum/schema → công nhận record. Đừng đưa dữ liệu vào business logic trước khi kiểm tra những invariant cần thiết.

## 12. Kiểm thử short read có chủ đích

FileChannel local có thể tình cờ làm đầy buffer trong một lần, khiến bug “chỉ đọc một lần” không bộc lộ. Dùng một wrapper trả tối đa 2 byte/lượt:

~~~java
// Mã minh họa: source là InputStream, thêm import cần thiết.
InputStream shortReads = new FilterInputStream(source) {
    @Override
    public int read(byte[] dst, int off, int len)
            throws IOException {
        return super.read(dst, off, Math.min(len, 2));
    }
};
~~~

Với payload chứa 4-byte header và 5-byte body, wrapper có thể chia thành lượt 2+2+2+2+1 byte; parser đúng vẫn phải dựng lại đầy đủ.

**Short read khác early EOF:** short read được nối tiếp bằng bytes ở lần sau; early EOF là nguồn trả `-1` trước khi lượng byte bắt buộc đủ. Cần negative tests cho cả hai hành vi.

Một wrapper trả 0 liên tục (khi caller yêu cầu length dương) có thể gây busy loop trong parser viết sai. Test cần timeout hữu hạn để phát hiện vòng lặp không tiến triển.

## 13. Kích thước file không phải snapshot

Ví dụ:

~~~java
long observed = Files.size(path);
try (InputStream in = Files.newInputStream(path)) {
    // File có thể bị truncate hoặc append sau phép size().
}
~~~

Không dùng `Files.size()==expected` như bằng chứng file vẫn giữ nguyên khi đã bắt đầu đọc. Một writer khác có thể sửa, truncate, replace path hoặc làm reader gặp EOF sớm. Tùy use case:

- File immutable được publish sau hoàn tất.
- File locking/coordination khi cần nhiều tiến trình truy cập.
- Filesystem snapshot hoặc transactional storage nếu yêu cầu snapshot thật.
- Với tailer, giữ parser state và chính sách chờ/timeout cho record đang ghi.

Những điều này quan trọng hơn khi file được chia sẻ qua network filesystem với cache/visibility riêng; việc `read` chính xác vẫn chỉ đảm bảo đọc đúng bytes **mà hệ thống cung cấp**, không tự xác nhận storage snapshot toàn hệ thống.

## 14. Bảng chẩn đoán exception

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| `EOFException` lúc header | File 0–3 byte hoặc EOF đúng boundary tùy format | Header bytes đã nhận |
| `EOFException` lúc payload | Length hợp lệ nhưng body thiếu | Declared vs actual |
| `BufferUnderflowException` | Buffer thiếu dữ liệu hoặc chưa flip | position/limit/remaining |
| `NegativeArraySizeException` | Length âm dùng trực tiếp | Validate trước allocate |
| `OutOfMemoryError` | Đọc file quá lớn trong một mảng | Streaming, limits |
| `IOException` khi read()==0 | Không tiến triển, helper file-specific | Blocking mode/provider |
| `ClosedChannelException` | Channel đóng giữa lúc dùng | Resource ownership |
| `NonReadableChannelException` | Channel mở không có READ | OpenOption |
| `AccessDeniedException` | Quyền file/ACL | Filesystem permissions |
| `NoSuchFileException` | File đã bị xóa/thay path | Concurrent operations |
| `FileSystemException` | Lỗi storage/mount/file busy | Cause, platform diagnostics |
| Dữ liệu decode sai | Charset/order/framing không thống nhất | Big-endian/UTF-8 và parser |
| Đủ byte nhưng nội dung sai | Corruption/overwrite/race | Checksum, concurrency |
| Parser treo CPU cao | Vòng read()==0 không thoát | Readiness/backoff/timeout |

Không bắt `IOException` rồi trả payload rỗng như trường hợp thành công. Lỗi đọc phải được tách khỏi payload length 0 thật sự.

## 15. Log và đo đạc để tái hiện lỗi

Thông tin nên có trong diagnostic log (không ghi nội dung nhạy cảm):

- Request ID hoặc job ID.
- Tên operation: open, read-header, read-payload, verify, write, close.
- Record offset trong file (kiểu long), byte đã nhận và byte mong đợi.
- Length prefix, giới hạn tối đa, file size quan sát.
- Exception class và cause, trạng thái channel/EOF.
- Số lượng retry, deadline nếu đọc từ nguồn bất đồng bộ.
- Trạng thái checksum/version và cleanup đã thực hiện.

Ví dụ thông điệp:

~~~text
job=42 op=read-payload offset=4 declared=100
received=60 status=TRUNCATED_PAYLOAD
~~~

Cố gắng dùng **mã lỗi có cấu trúc** như `EMPTY_FILE`, `TRUNCATED_HEADER`, `TRUNCATED_PAYLOAD`, `INVALID_LENGTH`, `TRAILING_BYTES`, `CHECKSUM_MISMATCH` thay vì để code nghiệp vụ parse chuỗi ngoại lệ.

## 16. Ma trận kiểm thử đề xuất

| Test | Input | Kỳ vọng |
|---|---|---|
| File rỗng | 0 byte | EMPTY_FILE nếu cần 1 record |
| Empty payload | Header N=0, không body | COMPLETE |
| Header 1 byte | EOF | TRUNCATED_HEADER 1/4 |
| Header 2 byte | EOF | TRUNCATED_HEADER 2/4 |
| Header 3 byte | EOF | TRUNCATED_HEADER 3/4 |
| Payload thiếu 1 byte | N-1/N | TRUNCATED_PAYLOAD |
| Payload thiếu toàn bộ | 0/N với N>0 | TRUNCATED_PAYLOAD |
| Length âm | -1 | INVALID_LENGTH |
| Length đúng MAX | Đủ bytes | COMPLETE |
| Length MAX+1 | Header vượt max | INVALID_LENGTH, không allocate |
| Trailing garbage | Thừa sau record | TRAILING_BYTES |
| Partial read | Wrapper 1–2 byte/lượt | COMPLETE nếu đủ |
| Read 0 nhiều lần | Simulated custom channel | Không spin vô hạn |
| File 5 MiB | Stream chunks | Đếm đúng, heap nhỏ |
| Long offset >2 GiB | Sparse fixture | Không cast int |
| Checksum mismatch | Body đủ nhưng sửa byte | REJECT |
| Writer crash giữa payload | Record tail thiếu | Recovery policy rõ |
| Concurrent truncate | File thay khi reader mở | Không báo complete sai |
| Permission error | Không được mở file | Báo I/O error |
| Disk full khi write | Ghi được một phần | Không publish file |
| EOF đúng giữa nhiều records | Không có header mới | END_OF_STREAM |
| EOF giữa header record tiếp | 1–3 byte | TRUNCATED_HEADER |

Tạo fixture bằng byte arrays hoặc file tạm riêng biệt giúp kết quả tái lập và không phụ thuộc file ở ngoài repo. Nếu dùng JUnit 5, `@TempDir` có thể tự cung cấp workspace cho mỗi test; vẫn nên xác nhận cleanup và resource closing.

## 17. Property-based testing và kiểm tra bất biến

Các thuộc tính cần chứng minh cho codec length prefix:

~~~text
decode(encode(payload)) == payload
    với 0 <= payload.length <= MAX.

Cắt encoded stream trước khi đủ 4 byte:
    TRUNCATED_HEADER hoặc EMPTY_FILE.

Cắt encoded stream sau header nhưng trước đủ payload:
    TRUNCATED_PAYLOAD.

Thay declared length bằng giá trị âm hoặc >MAX:
    INVALID_LENGTH trước khi allocate.

Nối một byte bất kỳ vào record hoàn chỉnh:
    TRAILING_BYTES khi contract chỉ cho một record.
~~~

Đây là **pseudo-spec**, không phải Java syntax. Test giá trị biên 0, 1, MAX, MAX+1, Integer.MAX_VALUE, số âm và dữ liệu nhiều byte UTF-8 (byte length khác character count).

Nếu parser xử lý string UTF-8, length prefix thường nên đếm **byte** sau encode, không phải số ký tự Java `String.length()`; ký tự tiếng Việt có thể chiếm nhiều byte.

## 18. Hiệu năng và an toàn của chương trình đọc file lớn

1. Đọc theo khối cố định, không cấp phát toàn file.
2. Dùng `long` cho tổng bytes và offsets.
3. Áp quota tổng số bytes và số lượng records.
4. Không vô hạn lặp khi read trả 0.
5. Hạn chế số file open và số I/O pending.
6. Kiểm tra bộ nhớ của cả ứng dụng, không chỉ một ByteBuffer.
7. Với non-blocking socket, dùng Selector và giữ state giữa các event.
8. Không dùng `MappedByteBuffer` đơn lẻ để biểu diễn file vượt phạm vi capacity int; chia mapping thành vùng nếu cần.
9. Có chính sách timeout/retry khác nhau cho transient I/O errors và dữ liệu malformed.
10. Không dùng atomic rename hay `force()` để thay kiểm tra header/payload/checksum.

## 19. Những nhầm lẫn phổ biến

| Sai lầm | Cách hiểu đúng |
|---|---|
| File 0 byte giống payload dài 0 | File 0 byte không có header; payload 0 có header hợp lệ |
| Một lần read lấp đầy buffer | Có thể đọc một phần |
| Read 0 nghĩa EOF | EOF là -1 |
| Header hợp lệ nghĩa payload đủ | Writer có thể crash trước khi ghi xong body |
| File size trả int | Java trả long |
| Ép long xuống int luôn ổn | Có thể overflow |
| readNBytes luôn đủ | Có thể ngắn ở EOF |
| readFully trả ít bytes mà không lỗi | Nó ném EOFException khi không đủ |
| Buffer getInt đọc ngay sau read | Phải kiểm số byte và flip |
| Gặp EOF giữa record là kết thúc bình thường | Đó là truncated record |
| EOF đúng boundary của multi-record là lỗi | Có thể là normal end |
| Length trên file đáng tin | Validate negative/max trước allocate |
| File có đúng size nên checksum đúng | Size không kiểm tra nội dung |
| Đã ghi bằng write một lần là đủ | Phải kiểm và lặp nếu còn remaining |
| Files.size là snapshot cố định | File có thể đổi sau phép đo |
| Unit test file local đủ phát hiện mọi short read | Nên có wrapper ép partial reads |
| Một exception được bắt nghĩa parser thành công | Phải phản ánh trạng thái lỗi đúng |

## 20. Câu hỏi tự kiểm tra

1. File 0 byte, cần đúng một record có header 4 byte: kết quả? **EMPTY_FILE**.
2. File gồm bốn byte 0: kết quả? **Bản ghi payload rỗng hợp lệ**.
3. Header mới 3/4 byte rồi EOF: **TRUNCATED_HEADER**.
4. Header length 9 nhưng nhận 7 byte body rồi EOF: **TRUNCATED_PAYLOAD 7/9**.
5. `FileChannel.read` trả 2 khi remaining=4: **đọc tiếp**, không phải EOF.
6. `read()==0` có phải EOF không? **Không**, EOF = -1.
7. Length âm nên xử lý trước hay sau allocate? **Trước**.
8. File dài 3 GiB có thể ép size long sang int không? **Không**.
9. `DataInputStream.readFully` bị thiếu bytes làm gì? **Ném EOFException**.
10. `InputStream.readNBytes(100)` ở EOF sau 40 byte trả gì? **Mảng 40 byte**.
11. Header length hợp lệ có chứng minh record hoàn chỉnh không? **Không**.
12. File đúng kích thước có chắc nội dung hợp lệ không? **Không**, kiểm checksum/schema.
13. Có nên chỉ thử parser bằng file đầy đủ? **Không**, cần test partial/EOF.
14. Multi-record parser gặp EOF trước byte đầu header kế tiếp thì sao? **Có thể kết thúc hợp lệ**.
15. EOF giữa payload log mới ghi dở có thể xử lý thế nào? **Theo recovery protocol; không tự ý coi là complete/truncate**.
16. Vì sao dùng streaming với file lớn? **Giảm footprint bộ nhớ và tránh allocate theo kích thước file**.
17. Vì sao cần dọn fixture tạm cả khi test fail? **Tránh rò tài nguyên và ảnh hưởng các test sau**.

## 21. Tài liệu chính thức Java SE 17

- [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): read/write, size, position và long offsets.
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): position/limit/flip/getInt/compact và byte order.
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): read, readNBytes và EOF.
- [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): readFully, readInt và EOFException.
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): size, newInputStream, readAllBytes, temp files.
- [EOFException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/EOFException.html): end-of-file bất ngờ trong dữ liệu nhị phân.
- [SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking reads, zero reads và partial I/O.

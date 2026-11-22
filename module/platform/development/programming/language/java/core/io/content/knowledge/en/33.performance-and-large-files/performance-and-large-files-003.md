# Chi phí syscall, chuyển đổi charset và số lớp bọc trong Java I/O

## 1. Bức tranh tổng thể: chậm ở đâu khi đọc/ghi dữ liệu lớn?

Hiệu năng Java I/O không chỉ phụ thuộc tốc độ SSD, ổ mạng hay băng thông socket. Trên đường đi của dữ liệu, một ứng dụng có thể phải trả nhiều loại chi phí khác nhau:

1. **Lời gọi từ code ứng dụng tới Java API:** gọi `read()`/`write()`, kiểm tra điều kiện, tạo object, dispatch qua các lớp wrapper.
2. **Chi phí hệ điều hành:** những lần cần đi qua ranh giới user mode ↔ kernel mode để yêu cầu I/O; thường được gọi là **system call (syscall)**.
3. **Chi phí copy và buffering:** di chuyển byte giữa Java arrays, ByteBuffer, buffer của wrapper, kernel buffers và thiết bị/network stack.
4. **Chuyển đổi ký tự:** decode `byte[]/ByteBuffer` thành text, hoặc encode `char/String` thành bytes bằng `Charset`.
5. **Xử lý chức năng khác:** nén/giải nén, checksum, mã hóa, TLS, phân tích cú pháp, kiểm tra khung bản tin.
6. **Cấp phát/GC:** nhiều buffer hay String trung gian có thể tăng allocation, memory pressure và garbage collection.
7. **Chờ thực tế:** disk seek, page cache miss, filesystem, mạng, locking, backpressure hoặc xử lý của peer.

Một thao tác được gọi là “I/O chậm” có thể bị giới hạn bởi **IOPS, syscall overhead, throughput, CPU charset conversion, memory bandwidth, GC hoặc độ trễ của thiết bị**. Cần đo trước khi tối ưu.

Ví dụ đường đi khi đọc một file text:

~~~text
Java application: đọc từng dòng
      |
      v
BufferedReader: char buffer / readLine
      |
      v
InputStreamReader: UTF-8 decoder / byte buffer
      |
      v
FileInputStream: đọc byte
      |
      v
JDK/native/OS: những yêu cầu read tới kernel
      |
      v
Page cache, filesystem, block device

Lưu ý: không phải mỗi mũi tên hoặc mỗi Java read() là một syscall.
~~~

Nội dung dưới đây tập trung **chi phí syscall, charset conversion và số lớp wrapper** trong nhóm “Hiệu năng và tệp lớn”, đồng thời chỉ ra cách đo và thiết kế pipeline an toàn trên Java 17+.

## 2. Phân biệt Java read/write call và syscall thật

### 2.1. Ba cấp thao tác

Giả sử ứng dụng gọi:

~~~java
int one = input.read();
~~~

Đây là **đoạn minh họa** với `InputStream input` đã mở. Một invocation của `read()` là **lời gọi Java**, không tự động bằng một system call. Với `ByteArrayInputStream`, toàn bộ byte nằm trong RAM của JVM và việc đọc đó thường không cần truy cập kernel. Với `BufferedInputStream`, lời gọi `read()` có thể chỉ lấy byte đã được cache ở buffer. Với file/socket stream thực, lời gọi đến lớp dưới có thể phải chờ dữ liệu và dẫn tới syscall hoặc một cơ chế native/OS khác.

Bảng cần nhớ:

| Đơn vị | Ai thực hiện? | Ý nghĩa | Đo ở đâu? |
|---|---|---|---|
| `input.read()` của ứng dụng | Java code | Một yêu cầu đọc mức API | Instrumentation trong JVM |
| `underlying.read(...)` ở stream bên dưới | Wrapper/JDK code | Một yêu cầu xuống lớp kế | Wrapper đếm call, profiler |
| Kernel `read` / `write` / các I/O syscall khác | JVM/native/OS | Yêu cầu đi qua ranh giới OS | Tracing, performance counters |
| Physical disk I/O | Storage stack | Trao đổi thật với thiết bị | Disk metrics, OS telemetry |

**Không đồng nhất bốn chỉ số.** Đặc biệt khi file đã nằm trong **OS page cache**, kernel vẫn có thể xử lý syscall đọc mà không phải chờ physical disk read. Với memory-mapped file, ứng dụng có thể gặp page fault thay vì đường đi syscall `read` thông thường cho từng lần truy cập.

### 2.2. Tại sao nhiều syscall nhỏ có thể đắt?

Khi một chương trình yêu cầu một byte mỗi lần trên đường I/O không được buffer, tổng chi phí có thể bao gồm:

- Nhiều lần qua ranh giới user/kernel.
- Kiểm tra file descriptor/socket state và dispatch native.
- Phí lập lịch, synchronization và chờ I/O.
- Nhiều thao tác copy/metadata nhỏ.
- Độ trễ lặp của filesystem hoặc network stack.

Với dữ liệu kích thước `N` và chunk `B`, số **yêu cầu đọc bulk của ứng dụng** có thể xấp xỉ `ceil(N/B)` nếu mỗi lần thật sự trả đủ B byte. Nhưng đây **không phải công thức cam kết cho syscall**: `read` có thể trả ngắn hơn yêu cầu, EOF cần được kiểm tra, và wrapper/JDK/OS có thể dùng chiến lược buffering riêng.

~~~text
Dữ liệu:      [--------------------------------] 32 KiB

Cách 1:      32768 yêu cầu đọc 1 byte (ở cấp ứng dụng)
Cách 2:          4 yêu cầu đọc 8 KiB (nếu tất cả đọc đầy)
Cách 3:          1 yêu cầu đọc 32 KiB (nếu đầy)

Số syscall tương ứng: KHÔNG thể suy ra chỉ từ sơ đồ này.
~~~

Với socket, một lần `read(byte[])` có thể nhận ít byte hơn `len`, ngay cả ở blocking mode. Không viết parser giả định một lần bulk read trả đúng số byte đã yêu cầu.

### 2.3. Đọc bulk thay vì read từng byte

Ví dụ kiểu đọc từng byte, thường không lý tưởng với file lớn:

~~~java
int b;
while ((b = in.read()) != -1) {
    out.write(b);
}
~~~

Cách xử lý theo buffer:

~~~java
byte[] buffer = new byte[16 * 1024];
for (int n; (n = in.read(buffer)) != -1; ) {
    if (n == 0) {
        continue; // hoặc xử lý theo đặc điểm stream để tránh busy loop
    }
    out.write(buffer, 0, n);
}
~~~

Đây là **hai đoạn mã minh họa** với `InputStream in` và `OutputStream out` đã quản lý vòng đời; không phải chương trình độc lập. Với một số stream đặc biệt/non-blocking bridge có thể trả 0, không được tạo busy spin vô hạn. Thư viện `InputStream.transferTo(OutputStream)` của Java 17 cũng có thể giúp copy byte stream bằng buffer mà không cần tự viết vòng lặp.

**Điểm quan trọng:** Nếu `in` đã là `BufferedInputStream` thì vòng đọc từng byte có thể chỉ gọi xuống lớp nguồn ít lần. Nhưng vòng lặp từng byte vẫn trả chi phí Java dispatch, kiểm tra và ghi từng byte. Vì thế thiết kế bulk read/write rõ ràng thường dễ kiểm soát hơn.

## 3. BufferedInputStream/BufferedOutputStream giảm loại chi phí nào?

`BufferedInputStream` giữ một vùng đệm trong Java để phục vụ nhiều lần đọc nhỏ mà không phải gọi lớp bên dưới tương ứng từng byte. `BufferedOutputStream` gom nhiều lần ghi nhỏ để tạo các write xuống stream bên dưới theo khối.

Ví dụ:

~~~java
try (InputStream in = new BufferedInputStream(
        Files.newInputStream(source), 64 * 1024);
     OutputStream out = new BufferedOutputStream(
        Files.newOutputStream(target), 64 * 1024)) {
    in.transferTo(out);
}
~~~

Đoạn minh họa yêu cầu `Path source`, `Path target` và import `java.io.*`, `java.nio.file.*`. `transferTo` đi qua `InputStream`/`OutputStream` tương ứng, không tự cam kết zero-copy hoặc một syscall cho toàn file. Đóng outermost stream sẽ flush/đóng lớp trong theo hợp đồng, vì vậy `try-with-resources` giúp quản lý vòng đời.

### Khi buffering có lợi

- Ứng dụng thường yêu cầu nhiều read/write rất nhỏ.
- Lớp bên dưới có chi phí I/O cao khi gọi lặp.
- Ghi được gom thành khối, tránh phát sinh nhiều lần dispatch xuống lớp nguồn.
- Parser đọc từng ký tự/dòng, nhưng nguồn thực là byte stream.

### Khi buffering có thể không giúp nhiều

- Đường gọi đã xử lý theo buffer lớn sẵn (ví dụ `Files.copy` hay vòng đọc bulk).
- Lớp byte stream bên dưới/JDK đã có internal buffer/readahead.
- I/O bị giới hạn bởi disk/network bandwidth thay vì syscall dispatch.
- Kích thước buffer lớn gây áp lực heap, tăng allocation/GC hoặc vượt nhu cầu.
- Ứng dụng cần flush thật sự sau mỗi record; gom buffer quá lâu có thể tăng latency.
- Wrapping thêm tạo copy và các nhánh xử lý trong trường hợp không còn chi phí nhỏ để tối ưu.

**Không có quy tắc “càng nhiều lớp BufferedInputStream càng nhanh”.** Một layer buffer được chọn đúng có thể đủ. Các buffer nằm ở **những cấp khác nhau** đôi khi có chức năng khác nhau, đặc biệt byte buffer và char buffer.

### Read-ahead và write-behind

Buffer đọc có thể nạp nhiều byte hơn ứng dụng đang cần để các read kế tiếp rẻ hơn. Buffer ghi có thể trì hoãn việc gửi byte xuống underlying stream tới khi buffer đầy, `flush()` hoặc `close()`.

Điều này quan trọng với protocol tương tác: nếu bạn gửi một lệnh ngắn qua `BufferedOutputStream` rồi đợi phản hồi, **hãy flush đúng thời điểm** để dữ liệu không chỉ nằm ở user-space buffer. `flush()` không có nghĩa dữ liệu đã được lưu bền trên storage hoặc peer đã xử lý; nó chỉ yêu cầu đẩy output đã buffer theo hợp đồng các lớp.

## 4. Lớp chuyển đổi charset: bytes khác characters

**Charset** định nghĩa cách chuyển giữa chuỗi ký tự Unicode của Java và byte của dữ liệu ngoài. Hai chiều:

~~~text
bytes  -- CharsetDecoder --> Unicode chars/String
chars  -- CharsetEncoder --> bytes
~~~

Trong Java:

- `InputStream` đọc **bytes**.
- `Reader` đọc **UTF-16 code units** (Java `char`), không trực tiếp là byte.
- `OutputStream` ghi **bytes**.
- `Writer` ghi **chars/String** và lớp bridge có thể encode thành bytes.
- `InputStreamReader` nối byte input với char input thông qua decoder.
- `OutputStreamWriter` nối char output với byte output thông qua encoder.

Ví dụ cấu trúc hợp lý để đọc file text:

~~~java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                Files.newInputStream(path),
                StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý text đã được decode.
    }
}
~~~

Đoạn mã minh họa cần `Path path`, `StandardCharsets` và các import Java tương ứng. `InputStreamReader` đã thực hiện decoding. `BufferedReader` buffer chars để đọc theo dòng hiệu quả, chứ **không decode lại**.

### UTF-8: byte, char, code point không cùng đơn vị

Với string `"Java: tiếng Việt 🌍"`:

- `String.length()` đếm **UTF-16 code units**, không phải số Unicode code points.
- Một emoji ngoài BMP như `🌍` dùng **surrogate pair** (2 `char`).
- UTF-8 mã hóa dấu tiếng Việt và emoji bằng nhiều byte.
- Một số tiếng Việt có thể biểu diễn dưới dạng precomposed hoặc combining sequence; byte length còn phụ thuộc cách chuẩn hóa Unicode.

Không được suy luận `data.length == text.length()` sau `text.getBytes(UTF_8)`. Nếu thao tác xử lý là **byte protocol**, đặt giới hạn bằng byte; nếu là **ký tự người dùng nhìn thấy**, còn có khái niệm grapheme cluster ngoài code point.

### Chi phí của conversion

Decoding/encoding có thể tốn:

1. Quét byte hoặc UTF-16 code units.
2. Duy trì trạng thái cho multibyte/escape sequences của charset.
3. Kiểm tra malformed/unmappable sequences.
4. Ghi dữ liệu kết quả vào `char[]`, `String`, `byte[]` hoặc buffer.
5. Cấp phát các đối tượng trung gian nếu ứng dụng chuyển kiểu lặp đi lặp lại.

Vì vậy pipeline như **bytes → String → bytes → String** không có lợi nếu chương trình không hề cần hiểu nội dung text. Ví dụ copy ZIP, PNG hoặc file bất kỳ nên giữ **byte-oriented**; chuyển sang String bằng charset có thể phá dữ liệu nhị phân.

## 5. Ranh giới chunk và ký tự nhiều byte

UTF-8 có thể mã hóa một Unicode code point thành **nhiều byte**. Một network/file chunk có thể kết thúc **giữa một ký tự**, ví dụ emoji 4 byte bị chia thành 2 + 2 byte giữa hai lần đọc.

~~~text
UTF-8 emoji 🌍: [F0 9F 8C 8D]

Network read #1: F0 9F
Network read #2: 8C 8D
~~~

Lỗi thường thấy là:

~~~java
// PHẢN VÍ DỤ nếu chunk có thể cắt giữa UTF-8 sequence:
String left  = new String(chunk1, StandardCharsets.UTF_8);
String right = new String(chunk2, StandardCharsets.UTF_8);
String text  = left + right;
~~~

Nếu `chunk1` và `chunk2` cắt giữa một multibyte sequence, mỗi lần decode độc lập có thể **thay byte chưa đầy đủ bằng replacement character** hoặc gây lỗi tùy decoder configuration. Ghép các string bị lỗi sau đó không phục hồi được byte gốc.

**Giải pháp đúng:**

- Với stream, dùng **một `InputStreamReader` liên tục** cho toàn luồng để decoder giữ trạng thái.
- Với NIO `ByteBuffer`, dùng `CharsetDecoder` có state, giữ byte chưa tiêu thụ qua `compact()` giữa các lần `decode(input, output, endOfInput)`, cuối stream thực hiện `decode(..., true)` và `flush(output)`.
- Không giả định vị trí chia byte trùng code point boundary hoặc line/message boundary.
- Với protocol có frame chứa UTF-8, nhận **đủ byte của frame** rồi decode một lần theo charset đã thống nhất.

Điều này vừa là vấn đề **tính đúng đắn**, vừa là vấn đề hiệu năng: xây String cho từng chunk quá nhỏ tạo allocation và decoder setup lặp lại.

### CharsetDecoder và xử lý lỗi

`CharsetDecoder` hỗ trợ `CodingErrorAction.REPORT`, `REPLACE` và `IGNORE` cho malformed/unmappable input. Với dữ liệu protocol cần xác thực nghiêm ngặt, `REPORT` thường giúp phát hiện lỗi thay vì âm thầm làm biến dạng tên định danh, log hay payload.

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String decoded = decoder.decode(ByteBuffer.wrap(payload)).toString();
~~~

Đây là đoạn mã minh họa có `byte[] payload` và các import `java.nio.*`, `java.nio.charset.*`. Khi byte không hợp lệ, `decode(ByteBuffer)` có thể ném `CharacterCodingException`. Đối với API tiện lợi như `Charset.decode(ByteBuffer)`, Java 17 có thể dùng **replacement behavior** cho invalid sequences; đừng mặc định chúng luôn ném lỗi.

**Đừng lạm dụng `IGNORE`** cho dữ liệu có ý nghĩa bảo mật: bỏ byte lỗi có thể biến hai tên/ID khác nhau thành cùng một chuỗi.

## 6. Số lớp wrapper: không chỉ là đếm object

Java I/O dùng **decorator/wrapper** để kết hợp các chức năng. Ví dụ:

~~~text
BufferedReader
     |
InputStreamReader(UTF-8)
     |
BufferedInputStream
     |
FileInputStream
~~~

Các lớp làm những công việc khác nhau:

| Lớp | Công việc chính | Chi phí có thể thêm |
|---|---|---|
| `FileInputStream` | Lấy byte từ file | Native I/O, copy, synchronization tùy đường đi |
| `BufferedInputStream` | Buffer byte | Java byte array, copy, logic buffer |
| `InputStreamReader` | Decode byte thành UTF-16 chars | Decoder CPU, char output buffer |
| `BufferedReader` | Buffer char và cung cấp `readLine` | Char array, scanning line separators |
| `DataInputStream` | Đọc primitive/binary structures | Nhiều read nhỏ, các phép ghép byte |
| `GZIPInputStream` | Giải nén gzip | CPU decompression, buffer nội bộ |
| `CipherInputStream` | Giải mã theo cipher | CPU crypto, padding/state và buffer |
| `CheckedInputStream` | Cập nhật checksum | Phép tính checksum trên byte |
| `ObjectInputStream` | Deserialize object graph | Reflection/metadata, allocation, security risks |

**Số lớp wrapper không tỷ lệ tuyến tính với số syscalls.** Một lớp `BufferedInputStream` có thể giảm underlying calls mạnh; thêm `BufferedReader` có thể giúp đọc dòng hiệu quả. Ngược lại, thêm hai hay ba buffer ở cùng một tầng mà không có lý do có thể tăng copy, allocations và độ phức tạp mà không giảm syscall thêm.

### Wrapper đúng thứ tự có ý nghĩa

Với text:

~~~java
Reader reader = new BufferedReader(
        new InputStreamReader(
                Files.newInputStream(file),
                StandardCharsets.UTF_8));
~~~

Với ghi text:

~~~java
Writer writer = new BufferedWriter(
        new OutputStreamWriter(
                Files.newOutputStream(file),
                StandardCharsets.UTF_8));
~~~

Đây là hai **đoạn mã minh họa**, phải đóng outermost `Reader`/`Writer` sau khi dùng; `file` là `Path` hợp lệ. Có thể dùng gọn:

~~~java
try (BufferedReader in =
        Files.newBufferedReader(file, StandardCharsets.UTF_8);
     BufferedWriter out =
        Files.newBufferedWriter(output, StandardCharsets.UTF_8)) {
    String line;
    while ((line = in.readLine()) != null) {
        out.write(line);
        out.newLine();
    }
}
~~~

Mã minh họa có `Path file` và `Path output`. **Lưu ý semantics:** `readLine()` loại ký tự kết thúc dòng, `newLine()` tạo line separator theo hệ thống; ví dụ này **không copy text file bit-for-bit**. Nếu cần giữ chính xác CRLF/LF, BOM, trailing newline hay bytes gốc, hãy copy bytes thay vì line-oriented conversion.

### BufferedInputStream có cần thêm dưới InputStreamReader?

**Không có đáp án luôn đúng.** `InputStreamReader` tự có cơ chế đọc byte/readahead cần cho charset decoder; thêm `BufferedInputStream` có thể không giúp gì đáng kể và đôi khi tạo thêm copy. Nếu chương trình đã dùng `BufferedReader(InputStreamReader(...))`, hãy đo trước khi thêm lớp byte buffer nữa. Nhưng nếu một phần pipeline khác cũng đọc byte từ nguồn, có thể cần chiến lược buffering thống nhất — tuyệt đối không dùng đồng thời hai reader trên cùng stream mà không điều phối vì readahead sẽ làm rối vị trí dữ liệu.

### Lớp chức năng không phải "thừa" chỉ vì tốn CPU

`GZIPInputStream` hoặc `CipherInputStream` bổ sung **nghĩa vụ giải nén/giải mã**. Bỏ chúng có thể nhanh hơn nhưng **đổi hẳn semantics**, không còn cùng tác vụ. Tối ưu hợp lý là chọn đúng vị trí buffer và hạn chế intermediate copies **trong cùng một chức năng**, không cắt bỏ tính đúng đắn.

## 7. Ví dụ Java 17+ chạy được: đếm underlying calls và kiểm tra charset

Ví dụ này mô phỏng một nguồn byte bằng `ByteArrayInputStream`, cố ý **không dùng file** để các số đếm Java calls xác định trên chính class fixture. Nó cho thấy hiệu ứng buffer 8 byte, đồng thời chứng minh khác biệt số byte UTF-8 với UTF-16/code points và việc strict decoder từ chối UTF-8 lỗi.

**Tệp: `IoCostDemo.java`**

~~~java
import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class IoCostDemo {
    static class MeasuredInputStream extends FilterInputStream {
        int singleCalls, bulkCalls;

        MeasuredInputStream(byte[] bytes) {
            super(new ByteArrayInputStream(bytes));
        }

        @Override
        public int read() throws IOException {
            singleCalls++;
            return in.read();
        }

        @Override
        public int read(byte[] b, int off, int len)
                throws IOException {
            bulkCalls++;
            return in.read(b, off, len);
        }
    }

    public static void main(String[] args) throws Exception {
        // Unicode escapes giữ dữ liệu fixture ổn định trên console khác nhau.
        String original = "Java: ti\u1EBFng Vi\u1EC7t \uD83C\uDF0D";
        byte[] payload = original.getBytes(StandardCharsets.UTF_8);

        // Đọc từng byte trực tiếp, gồm cả lần cuối phát hiện EOF.
        MeasuredInputStream direct = new MeasuredInputStream(payload);
        int directBytes = 0;
        while (direct.read() != -1) {
            directBytes++;
        }

        // Ứng dụng vẫn read từng byte; buffer gom các request xuống nguồn.
        MeasuredInputStream backing = new MeasuredInputStream(payload);
        int bufferedBytes = 0;
        try (BufferedInputStream buffered =
                     new BufferedInputStream(backing, 8)) {
            while (buffered.read() != -1) {
                bufferedBytes++;
            }
        }

        System.out.println("utf8Bytes=" + payload.length);
        System.out.println("singleReadCalls=" + direct.singleCalls);
        System.out.println(
                "bufferedBulkCalls=" + backing.bulkCalls);
        System.out.println(
                "sameByteCount=" + (directBytes == bufferedBytes));

        // Decode đúng UTF-8 và phát hiện input malformed thay vì thay chữ.
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        String restored = decoder.decode(
                ByteBuffer.wrap(payload)).toString();

        System.out.println("utf16Units=" + restored.length());
        System.out.println("unicodeCodePoints=" +
                restored.codePointCount(0, restored.length()));
        System.out.println("roundTrip=" + original.equals(restored));

        try {
            decoder.reset();
            decoder.decode(ByteBuffer.wrap(
                    new byte[]{(byte) 0xC3, 0x28}));
            System.out.println("badUtf8Rejected=false");
        } catch (CharacterCodingException expected) {
            System.out.println("badUtf8Rejected=true");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac IoCostDemo.java
java IoCostDemo
~~~

**Stdout đã thử trên JDK 17 (với `ByteArrayInputStream` và buffer 8 byte):**

~~~text
utf8Bytes=25
singleReadCalls=26
bufferedBulkCalls=5
sameByteCount=true
utf16Units=19
unicodeCodePoints=18
roundTrip=true
badUtf8Rejected=true
~~~

### Giải thích kết quả

1. Chuỗi `Java: tiếng Việt 🌍` có **25 byte UTF-8**, nhưng `String.length() == 19` UTF-16 code units và **18 Unicode code points**. Emoji `🌍` chiếm 2 UTF-16 units, 1 code point và 4 byte UTF-8; tiếng Việt có hai ký tự được mã hóa nhiều byte.
2. 25 byte được đọc từng byte; vòng lặp còn gọi `read()` một lần để nhận `-1` (EOF). Vì vậy `singleReadCalls=26`.
3. `BufferedInputStream(backing, 8)` dùng các lần đọc 8 + 8 + 8 + 1 byte và một lần thấy EOF: **5 lần đọc bulk** xuống `MeasuredInputStream`, trong khi ứng dụng vẫn gọi 26 lần `buffered.read()`. Đây là con số của fixture cụ thể, **không phải 5 syscall**.
4. `sameByteCount=true` xác nhận buffer không làm mất hay nhân đôi byte.
5. CharsetDecoder `REPORT` decode lại dữ liệu đúng và từ chối cặp byte UTF-8 lỗi `C3 28`. Việc dùng `reset()` trước lần decode thứ hai tuân thủ vòng đời state của decoder.

### Những gì demo *không* đo

- Không đo physical disk read hay kernel syscall: nguồn chỉ là `ByteArrayInputStream`.
- Không đo throughput/tốc độ: stdout là **counter và kiểm tra đúng đắn**, không là kết quả benchmark.
- Không đo chi phí của tất cả wrapper khác: không phải mọi stream có hành vi giống `ByteArrayInputStream`.
- Không đo tác dụng của page cache, JIT, thiết bị, filesystem hoặc network.
- Không chứng minh cấu hình buffer 8 byte là tối ưu; đó chỉ là kích thước nhỏ giúp nhìn được số lần read.

**Quy tắc đo lường:** nếu muốn đánh giá syscall, phải dùng nguồn file/socket thật và công cụ OS/JVM phù hợp, không chỉ nhìn vào counter Java trong một stream giả lập.

## 8. Tối ưu pipeline text: tránh decode/encode lặp

Một pipeline không hiệu quả thường có kiểu:

~~~text
raw bytes
  -> UTF-8 decode thành String
  -> UTF-8 encode lại byte[]
  -> decode lại thành String
  -> parse rồi format
  -> encode sang UTF-8 trước khi ghi
~~~

Nếu chương trình chỉ **chuyển tiếp nguyên nội dung bytes**, các lần round-trip text có thể là công việc không cần thiết:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out); // Byte-to-byte copy
}
~~~

Đây là mã minh họa với `Path source`/`Path target` hợp lệ. Nó **giữ nguyên byte** và không cần charset. Việc copy bytes không có nghĩa kernel zero-copy; `InputStream.transferTo` được phép dùng buffer ở Java.

Ngược lại, nếu cần **lọc dòng, chuyển format, kiểm tra text**, hãy decode một lần ở ranh giới vào và encode một lần ở ranh giới ra:

~~~text
InputStream --> InputStreamReader(UTF-8)
            --> BufferedReader / parser / business logic
            --> BufferedWriter / OutputStreamWriter(UTF-8)
            --> OutputStream
~~~

### Tránh các String trung gian không cần

- `new String(chunk, UTF_8)` cho từng read nhỏ có thể tạo nhiều allocation và làm hỏng split multibyte sequences.
- Gọi `text.getBytes(UTF_8)` trong vòng lặp khi `text` không đổi có thể tạo byte arrays lặp lại; encode trước nếu phù hợp.
- `readLine()` tạo một String cho mỗi dòng. Với file log chứa hàng triệu dòng rất ngắn, chi phí allocation và parse có thể đáng kể.
- `Files.readString`/`readAllBytes` tiện nhưng tải toàn file vào bộ nhớ; không phù hợp file rất lớn nếu không có memory budget.
- Charset conversion không phải thứ nên xóa nếu cần giữ đúng encoding; tối ưu bằng streaming decoder và buffering hợp lý.

### CharsetEncoder/Decoder không dùng chung tùy ý giữa threads

`CharsetDecoder` và `CharsetEncoder` có **state** cho nhiều bước chuyển đổi. Không chia sẻ cùng một instance stateful giữa nhiều threads/luồng độc lập mà không có synchronization và reset protocol phù hợp. `Charset` và `StandardCharsets.UTF_8` là đối tượng mô tả charset; có thể dùng chúng để tạo coder riêng cho mỗi stream.

Với UTF-8, phải xác định **malformed input policy**. Thay thế lỗi bằng `U+FFFD` có thể phù hợp xử lý text không quan trọng, nhưng không nên mặc định cho dữ liệu identity, protocol keys hoặc trường cần so khớp byte/chữ chính xác.

## 9. Chọn kích thước buffer cho file lớn

Không có “magic buffer size” tối ưu cho mọi thiết bị, file system và ứng dụng. Một số điểm thực tế:

- **Quá nhỏ:** tăng số lần vào Java layer và thường làm tăng số underlying calls/syscalls.
- **Vừa đủ:** thường giảm call overhead mà không chiếm quá nhiều RAM.
- **Quá lớn:** có thể tăng per-connection memory, allocation/GC, cache pressure, latency time-to-first-byte hoặc mất cân bằng concurrency.
- **Nhiều stream đồng thời:** memory ≈ số stream × tổng dung lượng buffer mà mỗi stream giữ, chưa tính page cache và network buffers.
- **File I/O:** OS có page cache và readahead; tăng Java buffer mãi không tự làm storage nhanh hơn.
- **Mạng:** nhiều ghi nhỏ có thể tương tác với TCP buffering/Nagle/backpressure/TLS records, không chỉ syscall count.

Ví dụ nếu có 10.000 kết nối và mỗi kết nối giữ một byte buffer 64 KiB, riêng các buffer này chiếm xấp xỉ **625 MiB** (10.000 × 65.536 bytes), chưa tính objects và buffers ở tầng khác. Đây là **phép tính kích thước thô**, không phải đo memory thực tế.

Với application, có thể benchmark các chunk như **4 KiB, 16 KiB, 64 KiB, 256 KiB**, nhưng không gán chúng là giá trị chuẩn. Chọn buffer theo workload, latency, số channel mở đồng thời và memory budget.

### ByteBuffer heap và direct

Trong NIO:

- `ByteBuffer.allocate(size)` cấp buffer heap.
- `ByteBuffer.allocateDirect(size)` cấp direct buffer ngoài Java heap; nhiều native I/O implementation có thể tận dụng nó để giảm một số intermediate copies.
- Direct buffer có chi phí cấp phát/thu hồi và gây memory pressure ở khu vực ngoài heap; không nên cấp mới cho từng read rất nhỏ.
- `FileChannel.map` là memory mapping, có cơ chế page fault riêng; không đồng nghĩa luôn không copy hoặc luôn ít syscall/nhanh hơn.

**Không có cam kết “direct luôn nhanh hơn heap” hay “mmap luôn nhanh hơn buffered stream”**. Cần đo trên JDK/OS/filesystem và pattern truy cập thực.

### FileChannel.transferTo/transferFrom

`FileChannel.transferTo(position, count, target)` và `transferFrom` có thể tận dụng các đường native transfer trên một số nền tảng, nhưng không bảo đảm **mọi byte trong count được chuyển trong một invocation**. Kết quả trả về là số byte thực sự chuyển, nên cần tăng file position theo số byte đã chuyển và xử lý zero-progress/EOF có chính sách. Không dùng API này cho text nếu còn cần charset conversion ở tầng ứng dụng mà không giải quyết semantics byte.

## 10. Benchmark đúng để xác định nút thắt

### 10.1. Xác định workload và đại lượng

Một phép đo hữu ích cần nêu:

- Kích thước dữ liệu, số lượng file/record, độ dài record, tỷ lệ ASCII/Unicode.
- Loại thiết bị (local SSD, network filesystem, memory cache), trạng thái cold/warm.
- Read sequential hay random; sync hay async; số luồng và số kết nối.
- Charset, malformed input policy và có cần parse line/content không.
- Dung lượng buffer ở **mỗi lớp**.
- CPU time, wall time, throughput, latency p50/p95/p99, allocations/GC.
- Số Java calls, OS syscalls và disk/network I/O nếu có instrumentation.

Phải đo **end-to-end**: nếu tăng buffer giúp giảm syscalls nhưng làm latency/tổng CPU tăng vì copy nhiều hơn hoặc trì hoãn flush, chưa chắc là tối ưu cho sản phẩm.

### 10.2. Các baseline nên thử

| Baseline | Ý nghĩa |
|---|---|
| `InputStream.read()` từng byte | Điểm đối chứng API-call-heavy, không mặc định là mỗi byte = syscall |
| `read(byte[16KiB])` | Bulk read với buffer một tầng |
| `BufferedInputStream` + read() từng byte | Quan sát giảm underlying calls nhờ byte buffering |
| `BufferedReader(InputStreamReader(UTF_8))` | Workload text/line parsing |
| `InputStreamReader` không BufferedReader | Đối chứng cho chi phí char buffering |
| `Files.newBufferedReader(UTF_8)` | API idiomatic đọc text |
| `FileChannel` + `ByteBuffer` | I/O channel với buffer do ứng dụng quản lý |
| `FileChannel.transferTo` | Byte-transfer path khi không cần parse nội dung |

**Không so hai baseline nếu chúng không làm cùng một việc**. Ví dụ bulk byte copy không thể so trực tiếp với decode UTF-8 + parse JSON, vì công việc khác nhau.

### 10.3. Công cụ quan sát

- **JMH:** microbenchmark phần Java CPU, buffer, charset conversion có warm-up và fork; tránh tự lấy một kết quả `System.nanoTime()` làm kết luận.
- **Java Flight Recorder (JFR):** giúp quan sát allocation, Java events, file/socket I/O và thread activity tùy cấu hình JDK.
- **Async profiler/CPU profiler:** xác định thời gian CPU ở decoding, encoding, buffer copy, parsing và native methods.
- **Linux strace/perf hoặc OS-specific tools:** quan sát syscalls và counters cấp hệ điều hành, với overhead do tracing.
- **Disk/network metrics:** giúp phân biệt data cached và physical I/O.
- **GC logs/JFR allocation profiling:** xác định nhiều String/byte[] hoặc wrapper objects có trở thành nút thắt không.

Ví dụ chạy trên Linux **nếu đã cài và được phép sử dụng strace**:

~~~bash
strace -c -e trace=read,write,openat java IoCostDemo
~~~

Lệnh **chỉ minh họa công cụ**, và demo `IoCostDemo` dùng `ByteArrayInputStream` nên không đại diện workload file I/O. Nếu đo Java process bằng tracing syscalls, các syscall của **JVM startup, runtime, class loading và stdout** cũng được tính. Cần tách workload mục tiêu (ví dụ qua tracing scope/tiến trình chạy dài hoặc đối chiếu baseline), tránh kết luận từ số tổng.

### 10.4. Sai lầm benchmark thường gặp

1. Chỉ chạy một lần và đo thời gian khi JIT chưa warm.
2. Lần một cold file cache, lần hai warm rồi so hai chiến lược khác nhau.
3. Tạo input/encode data trong đoạn benchmark đo đọc file.
4. Không kiểm tra dữ liệu đầu ra, khiến một phương án nhanh vì **làm ít việc hơn**.
5. Không giới hạn memory, dẫn đến GC/swap làm sai mục tiêu.
6. Chỉ xem CPU khi bottleneck thật là device I/O hoặc network backpressure.
7. Chỉ xem số syscall khi overhead lớn hơn nằm ở UTF-8 decoding hoặc parsing.
8. Dùng output trên console trong hot loop: `println` có chi phí đồng bộ/format/I/O lớn.
9. Coi direct buffer hay thêm wrapper là tối ưu mặc định.
10. Không đo p99 latency trong hệ thống phục vụ nhiều request đồng thời.

## 11. Checklist thiết kế pipeline cho file lớn

Để vừa **đúng dữ liệu** vừa có hiệu năng tốt, nên hỏi theo thứ tự:

1. **Dữ liệu là bytes hay text?** Nếu binary hoặc copy nguyên file, không decode charset không cần thiết.
2. **Ứng dụng đọc theo block, line hay message?** Chọn `read(byte[])`/`ByteBuffer` hoặc `BufferedReader` đúng yêu cầu.
3. **Ai sở hữu charset?** Chỉ định `StandardCharsets.UTF_8` (hoặc encoding thực của dữ liệu), không phỏng đoán từ platform default.
4. **Decoder state được giữ qua chunk?** Dùng `InputStreamReader` hoặc stateful `CharsetDecoder` đúng cách.
5. **Có wrapper trùng chức năng?** Vẽ sơ đồ các byte/char buffers và vai trò thực tế của từng lớp.
6. **Buffer/chunk bao lớn?** Đo với workload thực, cân đối concurrency memory.
7. **Khi nào phải flush?** Ghi text/binary có protocol boundary khác với flush về storage; đừng nhầm `flush` và `FileChannel.force`.
8. **Đã xử lý partial read/write và EOF?** Không giả định một lần I/O trả hết bytes; tránh busy spin khi không tiến triển.
9. **Có giới hạn memory/CPU?** Không `readAllBytes` với file khổng lồ nếu thiếu quota; stream theo chunk.
10. **Đã đo đúng nút thắt?** Quan sát syscall, charset CPU, allocations, device latency thay vì chọn giải pháp theo cảm giác.

## 12. Những hiểu lầm phổ biến

1. **“Mỗi lần gọi `InputStream.read()` là một syscall.”** Sai: nguồn in-memory hoặc wrapper có thể không xuống kernel.
2. **“Mỗi syscall đọc file đều gây physical disk read.”** Sai: OS page cache có thể phục vụ dữ liệu.
3. **“Đọc 1 byte từng lần luôn gây một syscall/byte.”** Không đúng khi đã buffer; số Java calls vẫn có thể lớn.
4. **“Dùng buffer càng lớn càng tốt.”** Sai: bộ nhớ/copy/latency và concurrency có thể bị ảnh hưởng.
5. **“Hai lớp BufferedInputStream luôn nhanh hơn một.”** Sai: có thể tăng overhead mà không giảm underlying calls.
6. **“InputStreamReader và BufferedReader cùng decode UTF-8 hai lần.”** Sai: InputStreamReader decode, BufferedReader buffer ký tự.
7. **“UTF-8 byte count bằng String.length().”** Sai: length là số UTF-16 code units.
8. **“Có thể new String riêng cho mọi byte chunk rồi ghép.”** Sai: split UTF-8 sequence có thể bị lỗi.
9. **“Charset.defaultCharset() giống nhau trên mọi Java 17 runtime.”** Không bảo đảm: JDK 17 còn có khác biệt platform/locale; chỉ định charset rõ ràng.
10. **“Chuyển binary thành String rồi lại getBytes không mất gì.”** Sai: charset conversion có thể thay byte invalid.
11. **“`CharsetDecoder.REPORT` và `REPLACE` cùng trả dữ liệu như nhau.”** Sai: REPORT báo lỗi, REPLACE thay byte lỗi bằng ký tự thay thế.
12. **“`flush()` bảo đảm dữ liệu lưu bền hoặc peer đã nhận.”** Sai: nghĩa flush tùy wrapper, không thay fsync/ACK.
13. **“`Files.readString` thích hợp với mọi file vài GiB.”** Sai: có thể dùng quá nhiều heap; stream theo chunk.
14. **“Direct ByteBuffer luôn nhanh hơn heap ByteBuffer.”** Sai: còn phụ thuộc operations, allocations và I/O backend.
15. **“`transferTo` luôn chuyển đủ count một lần.”** Sai: kiểm tra số byte trả về.
16. **“Giảm số Java calls = giảm bằng số syscalls.”** Sai: mối quan hệ tùy implementation/wrapper.
17. **“Đo `System.nanoTime()` một lần là đủ benchmark.”** Sai: JIT, OS cache, allocation và noise ảnh hưởng kết quả.

## 13. Tự kiểm tra kiến thức

**Câu 1:** Nếu đọc một `ByteArrayInputStream` 10.000 lần bằng `read()`, có chắc đã gọi 10.000 syscall không?

**Đáp án:** Không. Dữ liệu nằm trong Java heap; các lời gọi read cấp Java không nhất thiết gây OS syscall.

**Câu 2:** Vì sao `BufferedInputStream` giảm underlying read calls nhưng vẫn có thể không giúp nhiều với `Files.copy` đã dùng bulk I/O?

**Đáp án:** Khi ứng dụng đã đọc theo block và backend đã buffer, thêm một layer có thể ít giảm call thực tế nhưng tăng chi phí copy và object.

**Câu 3:** Chuỗi có ký tự `🌍` dài mấy Java `char` và bao nhiêu UTF-8 byte cho riêng emoji đó?

**Đáp án:** 2 UTF-16 code units (`String.length` tăng 2) và 4 byte UTF-8, nhưng chỉ 1 Unicode code point.

**Câu 4:** Một emoji UTF-8 4 byte bị tách qua hai lần socket read. Có nên gọi `new String(chunk, UTF_8)` riêng mỗi chunk?

**Đáp án:** Không. Phải giữ decoder state hoặc gom đủ byte frame, tránh malformed/replacement do tách sequence.

**Câu 5:** Ghi các message ngắn qua BufferedOutputStream mà không flush rồi đợi response có thể gặp vấn đề gì?

**Đáp án:** Byte có thể vẫn ở buffer ứng dụng, chưa được đẩy xuống underlying stream, nên peer chưa thấy yêu cầu. Cần flush đúng protocol boundary; nhưng flush không thay ACK của ứng dụng.

**Câu 6:** Nếu phần lớn CPU nằm ở UTF-8 decoding, giảm 50% số syscall có chắc làm latency giảm 50% không?

**Đáp án:** Không. Tổng latency còn phụ thuộc phần việc khác; syscall chỉ là một thành phần. Cần đo end-to-end và CPU profile.

**Câu 7:** Tại sao không thể suy ra số syscalls từ `bufferedBulkCalls=5` trong ví dụ?

**Đáp án:** Đó chỉ là số lời gọi `read(byte[],off,len)` vào `MeasuredInputStream` bọc `ByteArrayInputStream`. Không có disk I/O; giữa Java calls và OS syscalls không có quan hệ 1:1 bắt buộc.

### Tài liệu chính thức Java 17

- [InputStream và transferTo](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html)
- [BufferedOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html)
- [InputStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html)
- [OutputStreamWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html)
- [BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [BufferedWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [Charset, CharsetDecoder và CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html)

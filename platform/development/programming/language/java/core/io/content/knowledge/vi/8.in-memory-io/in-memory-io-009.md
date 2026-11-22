# Dùng stream bộ nhớ trong kiểm thử và các phép biến đổi Java

## 1. Ý tưởng: thay nguồn/đích thật bằng dữ liệu trong RAM

Một chương trình Java thường đọc hoặc ghi qua các trừu tượng `InputStream`, `OutputStream`, `Reader`, `Writer`. **Stream bộ nhớ** cung cấp các implementation làm việc với mảng byte hoặc chuỗi ký tự ngay trong RAM. Nhờ đó, ta có thể kiểm thử logic đọc/ghi, chuẩn hóa nội dung, nén, giải nén hay biến đổi dữ liệu mà không cần tạo tệp tạm hoặc khởi chạy một máy chủ.

```text
Dữ liệu kiểm thử trong RAM
            |
            v
   ByteArrayInputStream / StringReader
            |
            v
     Logic xử lý I/O chung
            |
            v
  ByteArrayOutputStream / StringWriter
            |
            v
  So sánh kết quả / kiểm tra bất biến
```

Cùng một hàm nhận `InputStream` có thể chạy với `Files.newInputStream(path)` ở ứng dụng thật và `ByteArrayInputStream(bytes)` trong unit test. Tương tự, hàm nhận `OutputStream` có thể ghi ra tệp trong sản xuất và ghi vào `ByteArrayOutputStream` trong test. Điểm quan trọng là **thiết kế hàm nhận luồng qua tham số**, chứ không gắn chặt logic vào tệp cụ thể.

Tình huống phù hợp:

- Kiểm thử một parser, bộ chuyển mã, serializer hoặc thuật toán sao chép mà không phụ thuộc filesystem.
- So sánh byte đầu ra chính xác, kể cả byte `0x00`, `0xFF`, newline, chữ có dấu hoặc định dạng nhị phân.
- Xây dựng payload nhỏ hoặc vừa trong RAM trước khi gửi đến API, lưu trữ hoặc truyền qua luồng khác.
- Thử một chuỗi phép biến đổi: văn bản → byte UTF-8 → nén → giải nén → văn bản.
- Kiểm tra rằng code giữ nguyên thứ tự byte, số byte đọc được, charset và quy tắc đóng/flush.

**Phạm vi:** stream bộ nhớ vẫn tuân thủ hợp đồng I/O của Java nhưng thường nhanh, có sẵn dữ liệu và ít lỗi môi trường. Chúng không tự mô phỏng độ trễ mạng, read ngắn bất thường, lỗi đĩa hoặc sự cố đóng luồng. Muốn kiểm thử những nhánh đó, ta cần thêm implementation giả lập có chủ đích.

## 2. Bốn stream bộ nhớ nền tảng

| Mục đích | Loại byte | Loại ký tự |
| --- | --- | --- |
| Đọc từ dữ liệu đã có trong RAM | `ByteArrayInputStream` | `StringReader`, `CharArrayReader` |
| Gom dữ liệu đầu ra vào RAM | `ByteArrayOutputStream` | `StringWriter`, `CharArrayWriter` |
| Trừu tượng mà logic xử lý nên nhận | `InputStream` | `Reader` |
| Trừu tượng mà logic xuất kết quả nên nhận | `OutputStream` | `Writer` |

Các lớp trên thuộc `java.io`.

- `ByteArrayInputStream`: một `InputStream` đọc byte từ **mảng byte đã có**.
- `ByteArrayOutputStream`: một `OutputStream` có buffer tự tăng, gom toàn bộ byte đã được ghi.
- `StringReader`: một `Reader` đọc các đơn vị `char` từ một `String`.
- `StringWriter`: một `Writer` gom các đơn vị `char` thành nội dung chuỗi có thể lấy qua `toString()`.

Hai nhóm byte và ký tự có ý nghĩa khác nhau. **Stream byte không tự hiểu encoding**, còn `StringReader`/`StringWriter` làm việc với các đơn vị UTF-16 của Java và không phải là nơi tự động sinh byte UTF-8. Khi cần kiểm tra byte của văn bản, phải **mã hóa/giải mã với charset đã chọn**, thường là `StandardCharsets.UTF_8`.

## 3. ByteArrayInputStream: cung cấp byte cho code cần InputStream

Khởi tạo thông dụng:

```java
byte[] fixture = {0, 65, (byte) 0xFF};
InputStream source = new ByteArrayInputStream(fixture);
```

Đây là **đoạn minh họa**, cần import `java.io.InputStream` và `java.io.ByteArrayInputStream`.

`ByteArrayInputStream` coi mảng đã truyền là nguồn byte. Nó hỗ trợ:

| Phương thức | Hành vi |
| --- | --- |
| `read()` | Trả một byte dưới dạng `int` 0–255; `-1` khi EOF |
| `read(byte[], off, len)` | Đọc vào vùng chỉ định, trả số byte thực đọc |
| `available()` | Số byte còn lại có thể đọc của **implementation bộ nhớ này** |
| `skip(n)` | Bỏ qua tối đa `n` byte còn lại |
| `mark(...)` và `reset()` | Đánh dấu vị trí rồi quay về đó; lớp này hỗ trợ `mark/reset` |
| `transferTo(OutputStream)` | Chuyển các byte còn lại sang một output stream (Java 9+) |
| `close()` | **Không có tác dụng** đối với lớp này; có thể tiếp tục gọi các phương thức sau khi close |

Khác với file stream, `ByteArrayInputStream` không sở hữu file descriptor hoặc socket. Vì vậy nó hữu ích làm fixture cho test và ví dụ có thể chạy độc lập.

### Hai lưu ý về tính bất biến

**Thứ nhất, constructor không tạo bản sao phòng vệ của mảng byte nguồn.** Nếu bên khác thay đổi nội dung `fixture` sau khi tạo luồng nhưng trước khi đọc, kết quả đọc có thể thay đổi. Với một fixture cần ổn định, đừng sửa mảng gốc, hoặc tự tạo bản sao:

```java
byte[] safeFixture = fixture.clone();
InputStream source = new ByteArrayInputStream(safeFixture);
```

**Thứ hai, `mark/reset` của `ByteArrayInputStream` không có nghĩa mọi `InputStream` đều quay ngược được.** Trước khi dùng `reset()` trên luồng bất kỳ, kiểm tra `markSupported()` và hiểu hợp đồng của implementation. Với luồng file, network hoặc các wrapper khác, hành vi có thể khác.

## 4. ByteArrayOutputStream: gom byte rồi lấy kết quả

Một `ByteArrayOutputStream` chứa buffer byte tăng kích thước khi cần:

```java
ByteArrayOutputStream sink = new ByteArrayOutputStream();
sink.write(65);
sink.write(new byte[]{66, 67});
byte[] result = sink.toByteArray(); // Các byte 65, 66, 67.
```

Đây là **đoạn minh họa**, cần import `java.io.ByteArrayOutputStream`.

Các thao tác chủ yếu:

| Phương thức | Ý nghĩa |
| --- | --- |
| `write(int)`, `write(byte[], off, len)` | Ghi byte vào buffer trong RAM |
| `size()` | Số byte đã ghi hiện tại |
| `toByteArray()` | Tạo **một bản sao mới** của các byte đã ghi |
| `toString(Charset)` | Giải mã các byte đã ghi thành `String` với charset xác định |
| `writeTo(OutputStream)` | Chuyển toàn bộ byte đã gom đến một đích khác |
| `reset()` | Đặt số byte đã ghi về 0 để dùng lại buffer |
| `close()` | Không có tác dụng; phương thức của lớp vẫn dùng được sau close |

`ByteArrayOutputStream` khác với `ByteArrayInputStream` ở hướng dữ liệu: một bên **gom byte**, một bên **phát byte đã có**.

`toByteArray()` tạo bản sao, vì vậy việc gọi `reset()` hoặc ghi thêm vào `ByteArrayOutputStream` sau đó không làm thay đổi mảng kết quả đã lấy trước đó. Ngược lại, lấy một bản sao lớn có chi phí bộ nhớ và sao chép dữ liệu; đừng gọi `toByteArray()` liên tục trong mỗi lượt ghi nếu dữ liệu lớn.

**Không chuyển byte nhị phân thành `String` chỉ để xem kết quả.** Với nội dung UTF-8 đã biết, dùng `toString(StandardCharsets.UTF_8)`. Với ảnh, ZIP hoặc dữ liệu nhị phân, hãy so sánh byte/hex/hash phù hợp.

## 5. Ví dụ chạy được: sao chép byte trong RAM và xác minh

**Tệp `MemoryBytesDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;
import java.util.HexFormat;

public class MemoryBytesDemo {
    public static void main(String[] args) throws IOException {
        byte[] original = {0, 65, (byte) 0xFF};

        try (InputStream in = new ByteArrayInputStream(original);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {

            long transferred = in.transferTo(out);
            byte[] snapshot = out.toByteArray();

            System.out.println("Transferred: " + transferred);
            System.out.println("Hex: " + HexFormat.of().formatHex(snapshot));
            System.out.println("Exact match: "
                    + Arrays.equals(original, snapshot));

            out.reset();
            System.out.println("Size after reset: " + out.size());
            System.out.println("Snapshot length: " + snapshot.length);
        }
    }
}
```

Lệnh:

```bash
javac MemoryBytesDemo.java
java MemoryBytesDemo
```

**Stdout chính xác trên Java 17+:**

```text
Transferred: 3
Hex: 0041ff
Exact match: true
Size after reset: 0
Snapshot length: 3
```

Giải thích:

1. Byte `0xFF` hợp lệ và được `read()` biểu diễn bằng số nguyên 255, **khác** EOF `-1`.
2. `transferTo(out)` chuyển các byte còn lại từ luồng nguồn sang luồng đích, trả số byte đã chuyển.
3. `Arrays.equals(original, snapshot)` kiểm tra từng byte theo đúng thứ tự; phù hợp để xác minh **kết quả nhị phân chính xác**.
4. `HexFormat` (Java 17+) giúp biểu diễn byte dưới dạng hex dễ đọc.
5. `out.reset()` bỏ nội dung logic trong buffer đầu ra; mảng `snapshot` do `toByteArray()` tạo trước đó vẫn chứa ba byte.

Không có tệp nào được tạo trong ví dụ này. Bản thân `ByteArrayInputStream` không mô phỏng tình huống đọc một phần do mạng; nó chỉ cung cấp nguồn byte được xác định trước.

## 6. StringReader và StringWriter: kiểm thử logic ký tự

Nếu đầu vào/đầu ra ở cấp **văn bản**, dùng `Reader` và `Writer` thay vì ép text thành byte rồi ngược lại khi không cần. Cách này giúp test tập trung vào thuật toán xử lý chuỗi.

`StringReader` cho phép `read()`, `read(char[])`, `skip()`, `mark()`, `reset()` trên nội dung `String`. Sau khi `StringReader.close()`, các lần đọc tiếp thường ném `IOException`; nên không dựa vào hành vi đóng giống `ByteArrayInputStream`.

`StringWriter` tích lũy ký tự; `toString()` trả kết quả, `getBuffer()` trả buffer kiểu `StringBuffer` có thể thay đổi nên tránh cho code không tin cậy sửa trực tiếp. `StringWriter.close()` không có tác dụng, nhưng vẫn nên theo hợp đồng quản lý tài nguyên khi làm việc với các `Writer` tổng quát.

Để code xử lý text tái sử dụng được, hãy nhận `Reader source`, `Writer target` và để bên gọi quyết định chúng là memory hay file streams.

### Ví dụ chạy được: chuẩn hóa từng dòng bằng Reader/Writer

Bài toán: bỏ dòng trắng, `strip()` khoảng trắng ở đầu/cuối và chuyển các dòng còn lại thành chữ hoa. Kết quả sử dụng LF `'\n'` tường minh để dễ kiểm thử trên mọi hệ điều hành.

**Tệp `MemoryTextTransform.java`:**

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.util.Locale;

public class MemoryTextTransform {
    // Chỉ xử lý nội dung; caller sở hữu source và target.
    static int normalize(Reader source, Writer target) throws IOException {
        BufferedReader lines = new BufferedReader(source);
        int kept = 0;
        String line;

        while ((line = lines.readLine()) != null) {
            String value = line.strip();
            if (value.isEmpty()) {
                continue;
            }

            target.write(value.toUpperCase(Locale.ROOT));
            target.write('\n');
            kept++;
        }
        target.flush();
        return kept;
    }

    public static void main(String[] args) throws IOException {
        String input = "  Hà Nội  \n   \n Cần Thơ \n";
        StringWriter output = new StringWriter();

        try (StringReader inputReader = new StringReader(input)) {
            int kept = normalize(inputReader, output);
            String expected = "HÀ NỘI\nCẦN THƠ\n";

            System.out.println("Kept lines: " + kept);
            System.out.println("Exact text: "
                    + expected.equals(output.toString()));
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 MemoryTextTransform.java
java MemoryTextTransform
```

**Stdout chính xác:**

```text
Kept lines: 2
Exact text: true
```

Hàm `normalize` không hề biết dữ liệu đến từ `StringReader`. Khi cần đọc từ tệp, bên gọi có thể tạo một `BufferedReader` hoặc `InputStreamReader` với charset phù hợp rồi truyền theo kiểu `Reader`. Khi cần ghi file, dùng `Writer` mở từ đường dẫn tệp. **Logic xử lý không đổi**.

Lưu ý `BufferedReader.readLine()` bỏ dấu kết thúc dòng gốc, và hàm cố ý ghi lại LF. Do đó phép biến đổi này chuẩn hóa newline chứ không bảo toàn byte gốc. `String.toUpperCase(Locale.ROOT)` cũng có thể làm độ dài chuỗi thay đổi đối với một số ký tự Unicode; đây là biến đổi văn bản có chủ đích, không phải sao chép nhị phân.

### CharArrayReader và CharArrayWriter

Nếu dữ liệu được biểu diễn trực tiếp dưới dạng `char[]`, dùng `CharArrayReader` và `CharArrayWriter`. `CharArrayWriter.toCharArray()` trả bản sao ký tự đã ghi; `reset()` cho phép dùng lại buffer. Chúng phục vụ các thao tác ký tự, **không thực hiện chuyển đổi charset**. Với Unicode ngoài BMP, một code point có thể gồm hai `char`, vì thế không cắt tùy ý giữa một cặp surrogate khi muốn thu được các đoạn text độc lập hợp lệ.

## 7. Thiết kế unit test bằng cách truyền InputStream/OutputStream

Giả sử code nghiệp vụ có nhiệm vụ sao chép đúng byte từ nguồn sang đích. Thiết kế kém cho việc test là hàm mở cứng `input.bin` và `output.bin` ở bên trong; test phải chuẩn bị tệp và dọn dẹp. Một thiết kế linh hoạt hơn:

```java
static long copy(InputStream source, OutputStream target)
        throws IOException {
    byte[] buffer = new byte[4096];
    long total = 0;
    int count;

    while ((count = source.read(buffer)) != -1) {
        target.write(buffer, 0, count);
        total += count;
    }
    return total;
}
```

Đây là **phương thức minh họa trong ngữ cảnh**, yêu cầu `java.io.InputStream`, `java.io.OutputStream`, `java.io.IOException`. Test có thể truyền `ByteArrayInputStream` và `ByteArrayOutputStream`. Code sản xuất có thể truyền luồng mở từ file, socket hoặc API khác.

Ba điều cần kiểm thử riêng biệt:

1. **Dữ liệu:** đầu ra phải bằng đúng byte đầu vào; giữ nguyên byte `0x00`, `0xFF`, newline và Unicode đã mã hóa.
2. **Ranh giới:** `read(buffer)` có thể trả ít hơn chiều dài buffer. Chỉ được ghi `count` byte.
3. **Lỗi:** nguồn/đích thật có thể phát sinh `IOException`. Stream bộ nhớ mặc định ít khi tạo được lỗi kiểu này nên cần luồng giả lập khi muốn test nhánh thất bại.

### Ví dụ hoàn chỉnh: kiểm thử kết quả và lỗi I/O mô phỏng

**Tệp `CopyServiceTestDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CopyServiceTestDemo {
    static long copy(InputStream source, OutputStream target)
            throws IOException {
        byte[] buffer = new byte[4];
        int count;
        long total = 0;

        while ((count = source.read(buffer)) != -1) {
            target.write(buffer, 0, count);
            total += count;
        }
        return total;
    }

    // OutputStream giả lập lỗi ngay khi đã nhận đủ limit byte.
    static final class FailAfter extends OutputStream {
        private int remaining;

        FailAfter(int limit) {
            remaining = limit;
        }

        @Override
        public void write(int value) throws IOException {
            if (remaining == 0) {
                throw new IOException("synthetic write failure");
            }
            remaining--;
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] payload = "abcde".getBytes(StandardCharsets.US_ASCII);

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        long copied = copy(new ByteArrayInputStream(payload), output);

        System.out.println("Copied: " + copied);
        System.out.println("Exact bytes: "
                + Arrays.equals(payload, output.toByteArray()));

        boolean failedAsExpected = false;
        try {
            copy(new ByteArrayInputStream(payload), new FailAfter(2));
        } catch (IOException exception) {
            failedAsExpected =
                    "synthetic write failure".equals(exception.getMessage());
        }
        System.out.println("Failure detected: " + failedAsExpected);
    }
}
```

Biên dịch/chạy:

```bash
javac CopyServiceTestDemo.java
java CopyServiceTestDemo
```

**Stdout chính xác:**

```text
Copied: 5
Exact bytes: true
Failure detected: true
```

`FailAfter` là `OutputStream` tự định nghĩa cho test. Hàm `OutputStream.write(byte[], off, len)` mặc định của lớp cha ghi lần lượt qua `write(int)`, nên khi tới byte thứ ba, `FailAfter.write(int)` ném `IOException`. Đây là bằng chứng có thể kiểm tra nhánh xử lý lỗi mà không cần làm hỏng ổ đĩa thật.

Trong dự án dùng JUnit 5, có thể chuyển các dòng `System.out.println` của ví dụ thành `assertEquals(5, copied)`, `assertArrayEquals(payload, output.toByteArray())`, và `assertThrows(IOException.class, ...)`. Cốt lõi là **kết quả test có thể xác định** và không cần dữ liệu nằm ngoài tiến trình.

## 8. Kiểm thử từ byte UTF-8 đến logic xử lý text

Nếu ứng dụng thực tế nhận dữ liệu qua `InputStream` nhưng nội dung là text, một test chỉ dùng `StringReader` có thể bỏ sót lỗi **charset**. Để kiểm tra toàn tuyến:

```text
String fixture
    │ getBytes(UTF_8)
    ▼
ByteArrayInputStream
    │
    ▼ InputStreamReader(UTF_8)
Logic xử lý Reader / Writer
    │
    ▼ OutputStreamWriter(UTF_8)
ByteArrayOutputStream
    │ toByteArray()
    ▼
So sánh byte UTF-8 hoặc giải mã với UTF-8
```

Ví dụ đoạn mã đặt trong một phương thức đã có hàm `normalize(Reader, Writer)` ở mục trước:

```java
byte[] incoming = "  Hà Nội\n".getBytes(StandardCharsets.UTF_8);
ByteArrayOutputStream outputBytes = new ByteArrayOutputStream();

try (Reader reader = new InputStreamReader(
            new ByteArrayInputStream(incoming), StandardCharsets.UTF_8)) {
    Writer writer = new OutputStreamWriter(
            outputBytes, StandardCharsets.UTF_8);
    normalize(reader, writer);
    writer.flush(); // Cần để byte kết quả được chuyển xuống outputBytes.
}
String result = outputBytes.toString(StandardCharsets.UTF_8);
```

Đây là **đoạn minh họa**, cần các import tương ứng. `result` khi thành công là `"HÀ NỘI\n"`. Không cần đóng writer bọc `ByteArrayOutputStream` trong ví dụ này vì `flush()` đủ cho UTF-8 trong trường hợp này, nhưng với writer khác hoặc encoder stateful, **`close()` có thể cần thiết để hoàn tất mã hóa**. Nếu đang quản lý một writer do code tự mở, nên dùng `try-with-resources` theo đúng quyền sở hữu.

Nếu test sử dụng byte fixtures nhưng code gọi `new String(bytes)` hoặc `text.getBytes()` mà **không chỉ định charset**, kết quả có thể phụ thuộc runtime hoặc môi trường. Test hướng tới tính xác định nên sử dụng `StandardCharsets.UTF_8` rõ ràng cả khi tạo đầu vào và khi đọc đầu ra.

Đặc biệt tránh `(char) byteValue` để tự giải mã tiếng Việt: UTF-8 mã hóa một ký tự thành nhiều byte. `ByteArrayInputStream` chỉ trả byte chứ không giữ ranh giới code point.

## 9. Phép biến đổi nhị phân trong RAM: nén và giải nén GZIP

Một pipeline có thể bọc nhiều stream:

```text
Mảng byte gốc
    │
    ▼ GZIPOutputStream
ByteArrayOutputStream (gom byte đã nén)
    │ toByteArray()
    ▼ ByteArrayInputStream (đọc byte nén)
GZIPInputStream
    │ transferTo(...)
    ▼ ByteArrayOutputStream (gom byte giải nén)
So sánh với byte gốc
```

`GZIPOutputStream` và `GZIPInputStream` thuộc `java.util.zip`. Đây là **phép biến đổi byte**, không phải chuyển đổi charset. Khi nguồn là văn bản, ta chủ động mã hóa UTF-8 một lần ở rìa pipeline rồi giải mã một lần sau cùng.

### Ví dụ hoàn chỉnh: kiểm tra nén/giải nén trong RAM

**Tệp `MemoryGzipDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public class MemoryGzipDemo {
    public static void main(String[] args) throws IOException {
        byte[] original =
                "Java memory stream. ".repeat(20)
                        .getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream compressedSink = new ByteArrayOutputStream();

        try (GZIPOutputStream gzip =
                     new GZIPOutputStream(compressedSink)) {
            gzip.write(original);
        } // close() hoàn tất phần cuối của định dạng GZIP.

        byte[] compressed = compressedSink.toByteArray();
        boolean hasGzipHeader = compressed.length >= 2
                && (compressed[0] & 0xFF) == 0x1F
                && (compressed[1] & 0xFF) == 0x8B;

        ByteArrayOutputStream restoredSink = new ByteArrayOutputStream();
        try (GZIPInputStream gunzip = new GZIPInputStream(
                new ByteArrayInputStream(compressed))) {
            gunzip.transferTo(restoredSink);
        }

        System.out.println("GZIP header: " + hasGzipHeader);
        System.out.println("Restored exact bytes: "
                + Arrays.equals(original, restoredSink.toByteArray()));
    }
}
```

Biên dịch/chạy:

```bash
javac MemoryGzipDemo.java
java MemoryGzipDemo
```

**Stdout chính xác:**

```text
GZIP header: true
Restored exact bytes: true
```

Tại sao phải **đóng `GZIPOutputStream` trước khi đọc mảng byte nén**? Vì GZIP có trailer và trạng thái nén cần hoàn tất; chỉ gọi `flush()` không thay thế chắc chắn cho `finish()` hoặc `close()`. Trong ví dụ, `try-with-resources` kết thúc luồng GZIP trước `toByteArray()`, nên byte đã nén có cấu trúc đầy đủ. Đóng `GZIPOutputStream` cũng đóng `ByteArrayOutputStream` bên dưới, nhưng với lớp bộ nhớ này `close()` không có tác dụng, nên vẫn có thể lấy kết quả.

Đừng so sánh byte nén với byte gốc hoặc đòi hỏi kích thước nén luôn nhỏ hơn: dữ liệu ngắn hoặc khó nén có thể tạo đầu ra **lớn hơn** do header và metadata. Phép kiểm thử thích hợp là **giải nén lại và so sánh byte nguyên bản**, đồng thời kiểm tra lỗi cho dữ liệu nén hỏng ở test khác.

## 10. Phép biến đổi có cấu trúc: DataOutputStream và DataInputStream

Khi truyền/ghi dữ liệu nhị phân có cấu trúc, có thể xếp `DataOutputStream` trên `ByteArrayOutputStream`, rồi dùng `DataInputStream` trên `ByteArrayInputStream` để kiểm tra đọc ngược.

**Tệp `MemoryDataRecord.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;

public class MemoryDataRecord {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream memory = new ByteArrayOutputStream();

        try (DataOutputStream writer = new DataOutputStream(memory)) {
            writer.writeInt(42);
            writer.writeBoolean(true);
            writer.writeUTF("Java");
        }

        byte[] serialized = memory.toByteArray();
        try (DataInputStream reader = new DataInputStream(
                new ByteArrayInputStream(serialized))) {
            int id = reader.readInt();
            boolean active = reader.readBoolean();
            String name = reader.readUTF();

            System.out.println("Record: " + id + "/" + active + "/" + name);
            System.out.println("EOF: " + (reader.read() == -1));
        }
    }
}
```

Lệnh:

```bash
javac MemoryDataRecord.java
java MemoryDataRecord
```

**Stdout chính xác:**

```text
Record: 42/true/Java
EOF: true
```

`DataOutputStream.writeInt` ghi bốn byte theo thứ tự high-order byte trước; `writeBoolean` ghi một byte; `writeUTF` ghi độ dài rồi dữ liệu theo **modified UTF-8**, khác UTF-8 thông thường ở một số trường hợp. Chương trình đọc phải dùng đúng **thứ tự và phương thức tương ứng**: `readInt`, `readBoolean`, `readUTF`.

**Lưu ý thực tế:** `DataOutputStream.writeUTF`/ `DataInputStream.readUTF` không phải giải pháp tổng quát để phát ra JSON, text UTF-8 thuần hoặc giao thức bên ngoài. Nếu định dạng tương tác yêu cầu UTF-8 chuẩn với chiều dài kiểu khác, hãy đặc tả rõ framing, endian và charset, rồi viết bộ mã hóa phù hợp. Stream bộ nhớ giúp tạo fixture nhị phân để đối chiếu các byte kỳ vọng.

## 11. Chọn byte hay char cho phép biến đổi?

| Dữ liệu và phép biến đổi | Nên xử lý bằng | Vì sao |
| --- | --- | --- |
| Sao chép ảnh, ZIP, PDF, protobuf, checksum | `InputStream`/`OutputStream` | Giữ nguyên byte, không giải mã |
| Nén GZIP, mã hóa nhị phân, parse định dạng binary | Byte streams và wrapper tương ứng | Phép biến đổi được định nghĩa trên byte |
| Chuẩn hóa dòng, loại khoảng trắng, đổi chữ hoa | `Reader`/`Writer` | Phép biến đổi được định nghĩa trên ký tự |
| Đọc UTF-8 từ file/network để parse text | `InputStreamReader` + charset | Chuyển từ byte sang ký tự có kiểm soát |
| Xuất text UTF-8 ra network/file | `OutputStreamWriter` + charset | Chuyển từ ký tự sang byte rõ quy ước |
| Test kết quả serialize chính xác | `ByteArrayOutputStream.toByteArray()` | Xác minh byte, độ dài, thứ tự |
| Test hàm xử lý text | `StringReader`/`StringWriter` | Dễ tạo input, so sánh string |
| Test toàn tuyến encoding/decoding | ByteArray streams + Reader/Writer wrappers | Phát hiện lỗi charset và BOM khi có |

Việc **ghép nhiều wrapper** là bình thường. Ví dụ `BufferedReader(new InputStreamReader(new ByteArrayInputStream(bytes), UTF_8))` tạo luồng đọc theo dòng từ byte fixture. Nhưng lớp càng nhiều, quyền sở hữu và thứ tự flush/close càng phải rõ; đóng wrapper ngoài thường đóng luôn lớp bên trong.

## 12. Quan trọng: không đồng nhất memory stream với I/O thực tế

Stream bộ nhớ tạo ra môi trường test có dữ liệu sẵn, ít biến động. Điều đó hữu ích cho unit test nhưng cũng có giới hạn.

### 12.1 Lần read thường đầy dữ liệu hơn thực tế

`ByteArrayInputStream.read(byte[], off, len)` có thể trả phần lớn số byte yêu cầu ngay lập tức (đến giới hạn dữ liệu còn lại). Trong mạng hoặc hệ thống file, `InputStream.read(...)` được phép trả **ít hơn** số byte yêu cầu. Không viết thuật toán đòi mỗi lần đọc phải bằng `buffer.length`.

Khi cần test trường hợp đọc từng phần, có thể bọc luồng bằng `FilterInputStream` và giới hạn số byte của mỗi `read(byte[], off, len)`:

```java
// Lớp minh họa trong ngữ cảnh; cần import java.io.*.
final class SmallChunkInputStream extends FilterInputStream {
    SmallChunkInputStream(InputStream delegate) {
        super(delegate);
    }

    @Override
    public int read(byte[] bytes, int offset, int length) throws IOException {
        if (length == 0) {
            return 0;
        }
        return in.read(bytes, offset, Math.min(length, 2));
    }
}
```

Một hàm copy đúng phải xử lý được khi chỉ có 1 hoặc 2 byte mỗi lần. Khi test văn bản UTF-8, byte chunk thậm chí có thể kết thúc giữa ký tự đa byte; dùng **decoder streaming** như `InputStreamReader` thay vì gọi `new String(chunk, UTF_8)` trên từng mảnh.

### 12.2 Luồng bộ nhớ thông thường không báo lỗi môi trường

`ByteArrayOutputStream.write` và `StringWriter.write` làm việc trong RAM, thường không ném `IOException` do lỗi đĩa. Một phần mềm xử lý tệp/network phải được test bổ sung với fake streams ném lỗi sau N byte, lỗi khi close, EOF sớm, hay `Reader` lỗi giữa chừng. Đó là lý do ví dụ `FailAfter` ở trên có ích.

### 12.3 Bộ nhớ có giới hạn

Gom toàn bộ nội dung với `ByteArrayOutputStream` hoặc `StringWriter` tiêu thụ RAM theo lượng dữ liệu. Khi buffer tăng và khi gọi `toByteArray()`, có thể có **nhiều bản sao dữ liệu cùng tồn tại**. Với vài MB đã biết, điều này thường chấp nhận được; với hàng GB, stream thực sự theo chunk sẽ tốt hơn.

Nếu input không đáng tin hoặc có thể không giới hạn (ví dụ request tải lên hay dữ liệu giải nén), phải đặt **giới hạn kích thước** trước khi gom tất cả vào RAM. GZIP có thể giải nén thành dữ liệu lớn hơn rất nhiều so với byte nén ban đầu, vì vậy test thành công với payload nhỏ không bảo đảm chống hết bộ nhớ trong sản xuất.

### 12.4 Không đại diện cho tính đồng thời hay atomicity

Một stream bộ nhớ đơn giản không mô phỏng khóa file, write atomicity, nhiều tiến trình ghi đồng thời, mạng chậm hoặc socket bị ngắt. Unit test tập trung vào logic chuyển đổi; integration test cần cơ chế thật hoặc môi trường kiểm thử gần thực tế khi các yếu tố này quan trọng.

## 13. Quản lý vòng đời: ai tạo stream, ai đóng stream?

Trong Java, một số memory streams có `close()` không tác dụng: `ByteArrayInputStream`, `ByteArrayOutputStream`, `StringWriter`. Nhưng **điều đó không có nghĩa mọi stream được thay thế trong sản xuất cũng đóng tùy tiện được**.

Một API xử lý I/O có thể có hợp đồng:

```java
static void process(InputStream source, OutputStream target)
        throws IOException {
    // Đọc từ source và ghi sang target.
    // Caller tạo và sở hữu hai stream nên phương thức không đóng chúng.
}
```

Đây là mẫu **phân quyền sở hữu**, không phải chương trình chạy độc lập. Khi caller tạo stream, caller sẽ quyết định dùng `try-with-resources` để đóng. Code xử lý có thể gọi `flush()` nếu API yêu cầu kết quả đến ngay, nhưng cần tránh đóng stream ngoài ý muốn, đặc biệt nếu một luồng được dùng cho nhiều bước hoặc là `System.in/out`.

Nếu chính API tự mở file hay `GZIPOutputStream`, hãy dùng `try-with-resources` tại nơi sở hữu tài nguyên. Với wrapper nén hoặc bộ mã hóa có trạng thái, **close/finish có thể là bước kết thúc dữ liệu** cần thiết. Các test chỉ dùng memory stream có thể che giấu lỗi quên đóng wrapper.

### Ví dụ điển hình về thứ tự close

```java
ByteArrayOutputStream bytes = new ByteArrayOutputStream();
try (GZIPOutputStream gzip = new GZIPOutputStream(bytes)) {
    gzip.write(payload);
}
byte[] completeGzip = bytes.toByteArray();
```

Đây là đoạn minh họa với `byte[] payload` đã có, cần import `ByteArrayOutputStream`, `GZIPOutputStream` và xử lý `IOException`. Dữ liệu sau `close()` của wrapper đã hoàn tất cấu trúc GZIP. Việc `bytes.close()` không có tác dụng không thay đổi yêu cầu phải kết thúc đúng wrapper GZIP.

## 14. Những lỗi thường gặp

| Lỗi | Vì sao sai hoặc nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Dùng `new String(output.toByteArray())` khi test text | Phụ thuộc default charset | Chỉ rõ `StandardCharsets.UTF_8` hoặc charset của dữ liệu |
| Dùng `ByteArrayOutputStream.toString()` không charset rõ | Có thể phụ thuộc encoding mặc định | `toString(StandardCharsets.UTF_8)` |
| So sánh String để kiểm thử ảnh/ZIP | Nhị phân không phải văn bản | `assertArrayEquals`/`Arrays.equals` trên byte |
| Cắt UTF-8 thành chunk rồi giải mã mỗi chunk độc lập | Có thể tách byte của một ký tự | Dùng `InputStreamReader`/decoder streaming |
| Coi `char` luôn là một Unicode code point | UTF-16 có surrogate pair | Dùng API code point khi xử lý ở cấp ký tự Unicode |
| Luôn ghi `out.write(buffer)` sau `read(buffer)` | Ghi cả phần dữ liệu cũ của buffer ở lượt cuối | `out.write(buffer, 0, count)` |
| Cho rằng `ByteArrayInputStream` mô phỏng mọi I/O | Không có độ trễ, lỗi mạng và nhiều read ngắn như thực tế | Thêm fake streams và integration test |
| Quên gọi flush/close wrapper mã hóa/nén | Byte cuối/trailer có thể chưa được hoàn tất | Đóng wrapper đúng vòng đời |
| Gọi `toByteArray()` sau từng lần write lớn | Tạo nhiều bản sao và tốn RAM | Chỉ lấy snapshot khi cần kiểm tra/kết quả |
| Tạo `ByteArrayOutputStream` cho đầu vào không giới hạn | Có thể hết heap | Streaming + giới hạn kích thước |
| Cho rằng reset thay đổi snapshot đã lấy | `toByteArray()` tạo bản sao độc lập | Phân biệt buffer nội bộ với bản sao đầu ra |
| Sửa mảng byte đã truyền vào `ByteArrayInputStream` | Fixture có thể thay đổi ngoài dự kiến | Giữ mảng bất biến theo quy ước hoặc clone |
| Đóng luồng do caller sở hữu trong hàm xử lý | Có thể khiến các bước sau mất stream | Công bố ownership, để caller đóng |
| Dùng `System.setOut` cho mọi test | Thay đổi trạng thái global của cả JVM | Truyền `OutputStream`/`PrintStream` qua tham số |
| So sánh dữ liệu nén byte-for-byte giữa công cụ | Header, metadata và implementation có thể khác | Xác minh giải nén phục hồi byte gốc và cấu trúc hợp lệ |

## 15. Mẫu thiết kế cho mã sản xuất và test

Một cách chia trách nhiệm rõ ràng:

```text
Application boundary
  ├─ Mở FileInputStream / socket / API source
  ├─ Mở FileOutputStream / socket / API destination
  ├─ Gọi logic xử lý với InputStream, OutputStream
  └─ Đóng tài nguyên mà application sở hữu

Unit test
  ├─ ByteArrayInputStream / StringReader từ fixture
  ├─ ByteArrayOutputStream / StringWriter thu kết quả
  ├─ Gọi cùng logic xử lý
  └─ So sánh chính xác hoặc kiểm tra bất biến

Failure test
  ├─ FakeInputStream / FakeOutputStream trả chunk ngắn hoặc ném lỗi
  └─ Kiểm tra phản ứng, không làm hỏng file thật
```

Tách **nguồn/đích** khỏi **phép biến đổi** là chìa khóa. Khi cần, API nên nhận chính `InputStream`, `OutputStream`, `Reader` hay `Writer` qua constructor hoặc tham số. Điều đó cũng giúp đo hiệu năng/streaming: thuật toán không cần đọc toàn bộ input vào RAM chỉ vì test đang dùng stream bộ nhớ.

Có thể dùng `InputStream.nullInputStream()`, `OutputStream.nullOutputStream()`, `Reader.nullReader()` hay `Writer.nullWriter()` trong Java hiện đại để mô phỏng EOF hoặc đích bỏ qua dữ liệu, nhưng chúng không thay thế được memory stream **khi cần kiểm tra byte hoặc ký tự đầu ra**. Chẳng hạn một output sink bỏ qua nội dung có thể giúp thử hàm có chạy xong không, nhưng không chứng minh thuật toán ghi đúng dữ liệu.

## 16. Bài tập thực hành

1. Sửa `MemoryBytesDemo` để byte nguồn là `{0, 1, (byte) 0x80, (byte) 0xFF}`. Dự đoán `HexFormat` và kiểm tra `Arrays.equals`.
2. Trong `MemoryTextTransform`, thêm dòng tiếng Việt có emoji và chữ kết hợp dấu. Quan sát kết quả `strip()`/`toUpperCase(Locale.ROOT)` và so sánh dựa trên Unicode thay vì số byte.
3. Thay `StringWriter` bằng `OutputStreamWriter` trên `ByteArrayOutputStream` với UTF-8, rồi xác minh byte nhận được sau `flush()`.
4. Thay buffer 4 byte trong `CopyServiceTestDemo` thành 2 byte. Kết quả byte và số byte copy phải giữ nguyên.
5. Dùng `SmallChunkInputStream` bọc một `ByteArrayInputStream`. Chạy lại hàm `copy` và thử dữ liệu dài có byte `0xFF`; kiểm tra thuật toán vẫn đúng.
6. Thay `FailAfter(2)` bằng `FailAfter(0)` hoặc `FailAfter(5)`; giải thích lúc nào exception sẽ xuất hiện.
7. Thay payload nén GZIP bằng 1000 byte ngẫu nhiên rồi kiểm tra byte giải nén. Giải thích vì sao compressed size có thể lớn hơn original size.
8. Trong `MemoryDataRecord`, đổi thứ tự `readBoolean()` và `readInt()` và quan sát giá trị sai hoặc lỗi; khôi phục đúng thứ tự theo định dạng.
9. Tạo một hàm tính checksum cho `InputStream`, chạy bằng `ByteArrayInputStream` với fixture biết trước rồi dùng file stream với cùng byte. Kết quả phải giống nhau.
10. Viết JUnit test cho một hàm nhận `Reader` và `Writer`, dùng `StringReader`/`StringWriter` và `assertEquals(expected, actual)`. Sau đó bổ sung một test giả lập reader ném `IOException` giữa chừng.

## 17. Tóm lược kiến thức cần nhớ

**`ByteArrayInputStream`** và **`StringReader`** thay nguồn I/O bằng dữ liệu xác định trong RAM; **`ByteArrayOutputStream`** và **`StringWriter`** gom kết quả để đối chiếu. Khi thiết kế thuật toán nhận **các interface/class trừu tượng của luồng**, cùng logic có thể chạy trên memory fixtures, file, pipe hoặc dữ liệu khác mà không sửa code.

Ba nguyên tắc đặc biệt quan trọng:

1. **Xác định tầng dữ liệu:** byte cho nhị phân, reader/writer cho văn bản, charset rõ ràng ở ranh giới giữa byte và ký tự.
2. **Kiểm thử cả thành công và thất bại:** so sánh dữ liệu chính xác; dùng fake streams cho read ngắn, EOF sớm, ngoại lệ hoặc nhánh cần mô phỏng.
3. **Không quên giới hạn môi trường:** stream trong RAM tiêu thụ heap và không phản ánh đầy đủ file/network; wrapper biến đổi như GZIP vẫn cần kết thúc đúng vòng đời.

### Tài liệu tra cứu

- Java SE 17: [`ByteArrayInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayInputStream.html) và [`ByteArrayOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html).
- Java SE 17: [`StringReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/StringReader.html), [`StringWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/StringWriter.html), [`CharArrayReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/CharArrayReader.html), [`CharArrayWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/CharArrayWriter.html).
- Java SE 17: [`InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html), [`OutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html), [`DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html), [`DataOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html).
- Java SE 17: [`GZIPInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html) và [`GZIPOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPOutputStream.html).

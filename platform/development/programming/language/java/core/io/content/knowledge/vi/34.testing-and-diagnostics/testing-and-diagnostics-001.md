# Kiểm thử bằng stream bộ nhớ trước khi phụ thuộc tệp thật trong Java I/O

## 1. Mục tiêu của chiến lược kiểm thử

Khi một chức năng có nhiệm vụ **đọc dữ liệu, biến đổi nội dung rồi ghi kết quả**, lỗi trong thuật toán xử lý byte hoặc ký tự thường có thể được tìm ra mà không cần tạo tệp trên ổ đĩa. Thay vì gắn cứng logic vào `Path`, `FileInputStream` hay `FileOutputStream`, hãy tách **phần xử lý dữ liệu** khỏi **phần mở tài nguyên** và kiểm tra phần xử lý bằng stream lưu trữ trong RAM.

Ví dụ, muốn kiểm thử thao tác sao chép:

~~~text
Cách gắn chặt tệp:
  Path đầu vào -> Files.newInputStream -> copy -> Files.newOutputStream -> Path đích
                  ^                       ^     ^
                  |                       |     |
             khó cô lập              logic bị lẫn vào I/O thật

Cách tách phụ thuộc:
  InputStream  ----------------> copy(input, output) ----------------> OutputStream
       ^                                                               ^
       |                                                               |
  ByteArrayInputStream                                     ByteArrayOutputStream
  (kiểm thử trong RAM)                                      (kiểm thử trong RAM)

Khi triển khai thật:
  Files.newInputStream(path)                                Files.newOutputStream(path)
~~~

Với mô hình này, cùng một phương thức `copy(InputStream, OutputStream)` chạy trên **dữ liệu trong bộ nhớ** ở unit test và **tệp thực tế** ở integration test; không cần fork logic thành hai phiên bản.

Lợi ích thường thấy:

- **Nhanh, lặp lại được:** không phụ thuộc vị trí thư mục, quyền ghi, tên tệp bị trùng hoặc dung lượng ổ đĩa khi chỉ kiểm tra thuật toán.
- **Dễ định vị lỗi:** sai offset, thứ tự byte, encoding, EOF hoặc việc gọi `flush` thể hiện trực tiếp qua mảng byte/string kỳ vọng.
- **Đưa lỗi đặc biệt vào bài test:** có thể tạo stream giả giới hạn byte mỗi lần đọc, hoặc chủ động ném `IOException`.
- **Ít side effect:** test không tạo file rác, ít vấn đề dọn dẹp, tránh làm thay đổi dữ liệu người dùng.
- **Dễ song song hóa:** mỗi test sở hữu mảng byte và đối tượng stream độc lập.

Tuy vậy, kiểm thử trong RAM **không thay thế hoàn toàn** integration test với filesystem: quyền truy cập, symlink, symbolic link race, khóa, việc file bị sửa đồng thời, durability, khác biệt giữa các provider và xử lý tên đường dẫn vẫn cần được kiểm tra trong môi trường phù hợp.

## 2. Hiểu hai tầng: byte streams và character streams

Java I/O phân biệt hai hệ stream:

| Nhóm | Kiểu gốc | Triển khai bộ nhớ | Dùng kiểm thử |
| --- | --- | --- | --- |
| Byte-oriented | `InputStream` / `OutputStream` | `ByteArrayInputStream` / `ByteArrayOutputStream` | File nhị phân, giao thức byte, checksum, ZIP, dữ liệu mã hóa. |
| Character-oriented | `Reader` / `Writer` | `StringReader` / `StringWriter` | Nội dung văn bản đã decode, parser, chuẩn hóa dòng, template. |
| Character-oriented dạng mảng | `Reader` / `Writer` | `CharArrayReader` / `CharArrayWriter` | Tác vụ làm việc trực tiếp trên `char[]`, kiểm tra đoạn ký tự. |

**Byte không đồng nghĩa ký tự.** Một chữ Việt có dấu như `é` khi mã hóa UTF-8 dùng nhiều byte, nhưng khi thao tác qua `Reader`, chương trình thấy một hoặc nhiều **UTF-16 code unit** tùy code point. Nếu chức năng cần kiểm tra encoding, hãy dùng `ByteArrayInputStream` kết hợp `InputStreamReader` với charset rõ ràng, không dùng `StringReader` rồi tuyên bố đã kiểm thử UTF-8.

Với text, cần trả lời trước:

- Phần được kiểm thử có trách nhiệm **giải mã bytes thành characters** không?
- Hay phần được kiểm thử chỉ **xử lý text** sau khi charset đã được chọn?

Nếu chỉ kiểm thử parser ký tự, `StringReader` giúp cô lập logic. Nếu muốn phát hiện lỗi decode, malformed UTF-8 hoặc BOM, phải kiểm tra tại tầng byte-to-character.

## 3. ByteArrayInputStream: dựng đầu vào trong RAM

`ByteArrayInputStream` đọc từ một `byte[]` đã có:

~~~java
byte[] fixture = {10, 20, 30};
try (InputStream in = new ByteArrayInputStream(fixture)) {
    System.out.println(in.read()); // 10
    System.out.println(in.read()); // 20
    System.out.println(in.read()); // 30
    System.out.println(in.read()); // -1: EOF
}
~~~

Đây là **mảnh mã đặt trong phương thức**; cần import `java.io.InputStream` và `java.io.ByteArrayInputStream`. `read()` trả một `int` từ 0 đến 255 hoặc `-1` khi EOF, không dùng `byte` âm để biểu diễn EOF.

Các điểm cần nhớ:

1. Constructor `ByteArrayInputStream(byte[])` dùng **mảng được truyền vào**, không tự sao chép toàn bộ nó. Nếu test thay đổi mảng sau khi tạo stream, dữ liệu đọc được cũng có thể đổi.
2. `ByteArrayInputStream(byte[], offset, length)` có thể mô phỏng một đoạn dữ liệu bắt đầu từ vị trí khác 0.
3. Stream hỗ trợ `markSupported() == true`, `mark(...)` và `reset()`. Điều này hữu ích để test code cần đọc thử rồi quay lại, nhưng **không được suy ra mọi `InputStream` đều hỗ trợ mark/reset**.
4. `available()` cho biết số byte còn lại trong riêng memory stream này. Trong các nguồn I/O chung, `available()` **không** phải kích thước toàn bộ nội dung và không phải cách xác định EOF.
5. `close()` của `ByteArrayInputStream` không làm gì. Đừng dùng hành vi đó để kết luận rằng code đóng stream đầu vào của caller luôn vô hại.

Dùng chuỗi tiếng Việt làm fixture thì phải chọn charset cụ thể:

~~~java
byte[] inputBytes = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
InputStream in = new ByteArrayInputStream(inputBytes);
~~~

Đây là mảnh minh họa, cần import `java.nio.charset.StandardCharsets`. Không dùng `getBytes()` thiếu charset nếu kết quả byte phải ổn định giữa môi trường.

## 4. ByteArrayOutputStream: quan sát kết quả không cần tệp

`ByteArrayOutputStream` ghi byte vào một buffer có thể tăng dung lượng:

~~~java
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.write(new byte[] {65, 66, 67});
byte[] written = out.toByteArray();
System.out.println(Arrays.toString(written)); // [65, 66, 67]
~~~

Mảnh mã trên cần `java.io.ByteArrayOutputStream` và `java.util.Arrays`. `toByteArray()` trả về **một bản sao độc lập** của nội dung hiện tại. Có thể gọi lại sau khi ghi thêm để quan sát phần mới.

Một số API hữu ích:

| API | Ý nghĩa |
| --- | --- |
| `new ByteArrayOutputStream()` | Tạo output buffer trong RAM. |
| `new ByteArrayOutputStream(initialCapacity)` | Chọn dung lượng ban đầu, không giới hạn độ dài cuối cùng. |
| `write(int b)` | Ghi một byte, sử dụng 8 bit thấp. |
| `write(byte[], off, len)` | Ghi đúng vùng mảng chỉ định. |
| `size()` | Số byte đã ghi. |
| `toByteArray()` | Trả bản sao nội dung byte hiện tại. |
| `toString(StandardCharsets.UTF_8)` | Decode byte theo charset, tiện cho bài test text. |
| `reset()` | Xóa nội dung logic để tái sử dụng đối tượng. |
| `writeTo(OutputStream out)` | Sao chép nội dung hiện tại sang output stream khác. |

**Giới hạn:** buffer này giữ toàn bộ output trong RAM. Với dữ liệu hàng gigabyte, việc kiểm thử bằng một `ByteArrayOutputStream` không phản ánh đặc tính bộ nhớ của tệp/stream streaming thật; có thể dùng output giả đếm byte hoặc tính checksum mà không tích lũy mọi byte.

`ByteArrayOutputStream.close()` không có hiệu lực; các lệnh ghi sau close vẫn có thể hoạt động. `FileOutputStream`/network output thông thường không có hành vi đó. Do vậy, nếu muốn kiểm tra đúng ownership/close semantics thì cần stream giả theo dõi close hoặc integration test thực.

## 5. Thiết kế mã dễ kiểm thử: nhận stream thay vì tự mở path

**Đừng đặt `Files.newInputStream(...)` trong chính hàm chứa thuật toán** nếu logic cần unit test độc lập với filesystem. Tách hai lớp:

~~~java
// Logic có thể kiểm thử trong RAM:
static long copy(InputStream source, OutputStream target)
        throws IOException {
    byte[] buffer = new byte[8192];
    long copied = 0;
    int n;

    while ((n = source.read(buffer)) != -1) {
        if (n == 0) {
            throw new IOException("InputStream không tiến triển");
        }
        target.write(buffer, 0, n);
        copied += n;
    }
    target.flush();
    return copied;
}

// Adapter mở file thực tế:
static long copyFile(Path from, Path to) throws IOException {
    try (InputStream source = Files.newInputStream(from);
         OutputStream target = Files.newOutputStream(to)) {
        return copy(source, target);
    }
}
~~~

Hai phương thức trên là **mảnh mã**, cần import `java.io.*`, `java.nio.file.Files` và `Path`.

Quy ước ownership:

- Hàm `copy(InputStream, OutputStream)` **không đóng** stream được caller truyền vào, bởi vì caller có thể muốn sử dụng tiếp hoặc truyền output qua một bước khác.
- Hàm `copyFile(Path, Path)` **sở hữu** hai resource mà nó vừa mở, nên đóng bằng `try-with-resources`.
- `flush()` được gọi khi copy thành công để hỗ trợ những output có bộ đệm; nhưng `flush` không đồng nghĩa dữ liệu đã được đồng bộ bền vững tới thiết bị lưu trữ.
- Nếu output nằm trên tệp đã tồn tại, `Files.newOutputStream(to)` mặc định có thể tạo/truncate theo API. Production cần quyết định riêng chuyện overwrite, atomic replace, backup, quyền và lỗi.
- Nếu input và output trỏ cùng một file, adapter trên có thể phá dữ liệu. Kiểm tra và xử lý theo yêu cầu; unit test trong RAM sẽ **không phát hiện** vấn đề này.

Vòng lặp `read(buffer)` thông thường trên InputStream với mảng có độ dài dương có hợp đồng chờ ít nhất một byte hoặc EOF; nhánh `n == 0` ở đây để phát hiện implementation bất thường hoặc wrapper không tuân thủ. Không dùng nó làm quy tắc cho `SocketChannel.read(ByteBuffer)` non-blocking, nơi `0` là kết quả hợp lệ.

## 6. Bài test cơ bản nên bao phủ những gì?

Một unit test cho sao chép/biến đổi stream không chỉ cần tình huống “hello world”. Tối thiểu nên kiểm tra:

| Trường hợp | Dữ liệu / tình huống | Cần xác nhận |
| --- | --- | --- |
| Empty input | `byte[0]` | Output rỗng, số byte 0, không exception. |
| Một byte | Một giá trị như `0xFF` | Bảo toàn byte không dấu, EOF đúng. |
| Buffer nhiều chunk | Input dài hơn buffer | Không thiếu/lặp byte, thứ tự giữ nguyên. |
| Đợt đọc ngắn | Stream trả tối đa 1–2 byte mỗi read | Code sử dụng `n`, không giả định một read đầy buffer. |
| Byte đặc biệt | `0x00`, `0x80`, `0xFF` | Không nhầm null byte với kết thúc dữ liệu. |
| UTF-8 đa byte | `"AéB"`, `"Tiếng Việt"` | Đối chiếu chính xác byte và charset. |
| Output lỗi | Wrapper ném `IOException` sau vài byte | Exception được truyền/giải quyết đúng, không tuyên bố thành công. |
| Input lỗi | Stream ném lỗi sau một số lần đọc | Không nuốt lỗi, không ghi output giả thành công. |
| Flush/close | Stream theo dõi số lần flush/close | Ownership theo hợp đồng. |
| Mark/reset | Stream hỗ trợ và không hỗ trợ | Code không phụ thuộc sai vào đặc tính ByteArrayInputStream. |
| Partial parsing | Header/payload chia chunk | Parser giữ dữ liệu còn thiếu và phát hiện EOF thiếu dữ liệu. |

Số byte nhận được từ một lần `InputStream.read(byte[])` **có thể nhỏ hơn chiều dài mảng**, kể cả khi vẫn còn dữ liệu để đọc. Test nên cố tình tạo điều kiện đó.

## 7. Chương trình kiểm thử độc lập Java 17+ trong RAM

Ví dụ dưới đây có:

- `copy(...)` là logic cần kiểm thử.
- `TwoByteInputStream`: wrapper cố tình cho mỗi lần đọc tối đa hai byte.
- `FailAfterThreeBytesOutputStream`: output giả phát sinh `IOException` ngay khi ứng dụng cố ghi byte thứ tư.
- Các phép xác nhận dùng `require(...)` ném `AssertionError` nếu sai; không cần thư viện test ngoài JDK.
- Test dữ liệu UTF-8 `AéB`, empty input, check read chunk, stream ký tự và DataInput/DataOutput nhị phân.

Lưu file `MemoryStreamTestDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class MemoryStreamTestDemo {

    static long copy(InputStream source, OutputStream target)
            throws IOException {
        byte[] buffer = new byte[4];
        long total = 0;
        int n;
        while ((n = source.read(buffer)) != -1) {
            if (n == 0) {
                throw new IOException("InputStream không tiến triển");
            }
            target.write(buffer, 0, n);
            total += n;
        }
        target.flush();
        return total;
    }

    static long copyChars(Reader source, Writer target)
            throws IOException {
        char[] chars = new char[3];
        long total = 0;
        int n;
        while ((n = source.read(chars)) != -1) {
            if (n == 0) {
                throw new IOException("Reader không tiến triển");
            }
            target.write(chars, 0, n);
            total += n;
        }
        target.flush();
        return total;
    }

    static final class TwoByteInputStream extends ByteArrayInputStream {
        TwoByteInputStream(byte[] data) {
            super(data);
        }

        @Override
        public synchronized int read(byte[] bytes, int offset, int length) {
            return super.read(bytes, offset, Math.min(length, 2));
        }
    }

    static final class FailAfterThreeBytesOutputStream
            extends OutputStream {
        private int accepted;

        @Override
        public void write(int b) throws IOException {
            if (accepted >= 3) {
                throw new IOException("Injected output error");
            }
            accepted++;
        }
    }

    static void require(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] original =
                "AéB".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        long count;
        try (InputStream input = new TwoByteInputStream(original)) {
            count = copy(input, output);
        }

        require(count == 4, "Số byte sao chép");
        require(Arrays.equals(original, output.toByteArray()),
                "Nội dung byte không giống input");
        System.out.println("copiedBytes=" + count);
        System.out.println("copiedText=" +
                output.toString(StandardCharsets.UTF_8));

        ByteArrayOutputStream emptyOutput =
                new ByteArrayOutputStream();
        long emptyCount = copy(
                new ByteArrayInputStream(new byte[0]), emptyOutput);
        require(emptyCount == 0 && emptyOutput.size() == 0,
                "Input rỗng phải cho output rỗng");
        System.out.println("emptyBytes=" + emptyCount);

        StringWriter writer = new StringWriter();
        long chars = copyChars(
                new StringReader("abc\nxyz"), writer);
        require(chars == 7 && writer.toString().equals("abc\nxyz"),
                "Character stream bị đổi nội dung");
        System.out.println("copiedChars=" + chars);
        System.out.println("textLines=" +
                writer.toString().replace("\n", "|"));

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream data =
                new DataOutputStream(bytes)) {
            data.writeInt(0x01020304);
            data.writeUTF("Hi");
        }

        try (DataInputStream data = new DataInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            int value = data.readInt();
            String text = data.readUTF();
            require(value == 0x01020304 && text.equals("Hi"),
                    "Sai định dạng dữ liệu nhị phân");
            System.out.println("dataBytes=" + bytes.size());
            System.out.println("dataRoundTrip=" +
                    Integer.toHexString(value) + ":" + text);
        }

        boolean writeErrorCaught = false;
        try {
            copy(
                    new ByteArrayInputStream(new byte[] {1, 2, 3, 4, 5}),
                    new FailAfterThreeBytesOutputStream());
        } catch (IOException expected) {
            writeErrorCaught = true;
        }
        require(writeErrorCaught, "Lỗi output phải được báo");
        System.out.println("writeErrorCaught=" + writeErrorCaught);
        System.out.println("allChecksPassed=true");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MemoryStreamTestDemo.java
java MemoryStreamTestDemo
~~~

**Stdout chính xác trên Java 17+ khi chạy chương trình với file nguồn UTF-8:**

~~~text
copiedBytes=4
copiedText=AéB
emptyBytes=0
copiedChars=7
textLines=abc|xyz
dataBytes=8
dataRoundTrip=1020304:Hi
writeErrorCaught=true
allChecksPassed=true
~~~

### 7.1. Tại sao `copiedBytes=4`, không phải 3?

Chuỗi `AéB` có ba ký tự hiển thị, nhưng `é` có mã Unicode U+00E9 được mã hóa thành **hai byte UTF-8**. Dãy byte là:

~~~text
'A'    'é'      'B'
41     C3 A9    42
     tổng: 4 byte
~~~

`TwoByteInputStream` khiến thuật toán không thể mặc định một lần `read` điền đầy buffer 4 byte. Sau cùng, `Arrays.equals` so sánh **dữ liệu byte** chính xác với bản gốc. Nếu lập trình viên ghi nhầm `target.write(buffer)` thay vì `write(buffer, 0, n)`, test với lượt đọc ngắn/lượt cuối ngắn sẽ phát hiện byte dư.

### 7.2. Tại sao `copiedChars=7`?

Dữ liệu `"abc\nxyz"` có bảy UTF-16 code unit: ba chữ, một newline và ba chữ. Trong `Reader`/`Writer`, phép đếm là số `char`, **không tự đồng nghĩa số byte UTF-8** và cũng không phải số Unicode code point trong trường hợp chứa supplementary characters.

### 7.3. Vì sao `dataBytes=8`?

`DataOutputStream.writeInt` ghi **4 byte** big-endian cho `0x01020304`. `writeUTF("Hi")` ghi độ dài modified UTF-8 theo định dạng `DataOutput` trong **2 byte** rồi ghi hai byte `'H'` và `'i'`. Tổng bằng `4 + 2 + 2 = 8`. `DataInputStream.readUTF` tương thích với định dạng modified UTF-8 này, khác với việc tùy tiện dùng một chuỗi UTF-8 thuần không có tiền tố độ dài.

### 7.4. Vì sao output lỗi được kiểm thử riêng?

`FailAfterThreeBytesOutputStream` nhận ba byte rồi cố ý ném lỗi khi ghi byte thứ tư. `OutputStream.write(byte[], off, len)` mặc định có thể gọi lần lượt `write(int)`, vì vậy lỗi được đẩy lên `copy`. Test xác nhận chương trình **không giả vờ báo copy thành công** khi output thất bại. Với ứng dụng thật, còn phải kiểm tra file đích ở trạng thái nào sau lỗi và chính sách xóa tệp tạm/rollback.

## 8. StringReader và StringWriter: kiểm tra parser ký tự

`StringReader` đọc ký tự từ một `String`, còn `StringWriter` ghi ký tự vào vùng nhớ tăng được. Không có thao tác charset conversion ở bên trong hai lớp này.

Ví dụ parser chỉ cần chuẩn hóa các dòng:

~~~java
static String linesToCsvLike(Reader reader) throws IOException {
    BufferedReader input = new BufferedReader(reader);
    StringJoiner result = new StringJoiner(",");
    String line;
    while ((line = input.readLine()) != null) {
        result.add(line.trim());
    }
    return result.toString();
}
~~~

Đây là **mảnh phương thức**, cần import `BufferedReader`, `Reader`, `IOException`, `StringJoiner`. Hàm không tự đóng `reader` vì resource được caller sở hữu.

Kiểm thử hoàn toàn trong bộ nhớ:

~~~java
String actual = linesToCsvLike(
        new StringReader("  blue \r\n green\nred"));
if (!actual.equals("blue,green,red")) {
    throw new AssertionError(actual);
}
~~~

Vì `BufferedReader.readLine()` loại bỏ ký tự xuống dòng theo các dấu kết thúc dòng mà API hỗ trợ, kết quả có thể kiểm chứng ổn định cho fixture có `\r\n` và `\n`.

**Chú ý:** `StringReader` nhận sẵn ký tự Java, nên test này **không phát hiện lỗi decode UTF-8** của file thật. Nếu parser phụ thuộc BOM, newline encoding hoặc malformed bytes, test riêng tầng decoder bằng `InputStreamReader`.

### 8.1. CharArrayReader và CharArrayWriter

Hai lớp này hữu ích nếu hệ thống đã có `char[]` hoặc chỉ muốn dùng một đoạn mảng ký tự:

~~~java
char[] chars = {'a', 'b', 'c', 'd'};
try (Reader reader = new CharArrayReader(chars, 1, 2);
     CharArrayWriter writer = new CharArrayWriter()) {
    reader.transferTo(writer);
    System.out.println(writer.toString()); // bc
}
~~~

Đây là mảnh mã cần import `java.io.*`. Chú ý `Reader.transferTo(Writer)` có từ Java 10, nên dùng được trên Java 17.

## 9. Kiểm thử cả tầng charset bằng stream byte

Một nguy cơ là lập trình viên phụ thuộc charset mặc định của máy, khiến code chạy trên CI và máy cá nhân cho kết quả khác nhau.

Nên truyền charset hoặc cố định `StandardCharsets.UTF_8`:

~~~java
static String readUtf8(InputStream source) throws IOException {
    try (Reader reader =
            new InputStreamReader(source, StandardCharsets.UTF_8)) {
        StringWriter writer = new StringWriter();
        reader.transferTo(writer);
        return writer.toString();
    }
}
~~~

Đây là **mảnh phương thức minh họa**; cần import `InputStreamReader`, `InputStream`, `StringWriter` và `StandardCharsets`. Ở đây phương thức **đóng Reader và vì vậy đóng InputStream đầu vào**: hành vi khác với `copy` trước đó. Hãy chọn hợp đồng ownership nhất quán với thiết kế, hoặc để caller quản lý Reader nếu caller sở hữu nguồn.

Unit test:

~~~java
byte[] utf8 = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
String actual = readUtf8(new ByteArrayInputStream(utf8));
if (!"Tiếng Việt".equals(actual)) {
    throw new AssertionError(actual);
}
~~~

Nếu cần test **malformed UTF-8**, `InputStreamReader` mặc định thường thay dữ liệu không hợp lệ bằng ký tự replacement theo cấu hình decoder. Muốn kiểm tra việc từ chối byte sai thay vì thay thế âm thầm, tạo `CharsetDecoder` với `CodingErrorAction.REPORT` và test nhánh xử lý `MalformedInputException`. Chính sách replace/report phải thuộc hợp đồng ứng dụng.

Đặc biệt, đọc từng chunk byte rồi gọi `new String(chunk, UTF_8)` độc lập có thể làm hỏng một ký tự UTF-8 nằm giữa hai chunk. Stream decoder giữ trạng thái là hướng tiếp cận đúng khi xử lý dữ liệu text theo nhiều đợt.

## 10. Tiêm lỗi để kiểm thử đường thất bại

Memory streams chuẩn thường thành công và nhanh đến mức có thể **che mất bug xử lý lỗi**. Có thể tạo test doubles bằng subclass/wrapper:

- `FilterInputStream`: giới hạn số byte trong mỗi lần read, ghi log số lần đọc, hoặc ném lỗi ở một lần gọi nhất định.
- `FilterOutputStream`: theo dõi `flush`/`close` và từ chối write sau một ngưỡng.
- Custom `InputStream`: kiểm thử EOF ngay sau header, stream chỉ trả một byte/lần, hoặc lỗi I/O giữa chừng.
- Custom `OutputStream`: giả disk-full, broken pipe hoặc permission error, nhưng cần làm rõ đó chỉ là **mô phỏng** của kết quả API.

### 10.1. Giới hạn số byte mỗi lượt đọc

~~~java
final class OneByteAtATime extends FilterInputStream {
    OneByteAtATime(InputStream inner) {
        super(inner);
    }

    @Override
    public int read(byte[] bytes, int offset, int length)
            throws IOException {
        return super.read(bytes, offset, Math.min(length, 1));
    }
}
~~~

Đây là mảnh khai báo class, cần `java.io.FilterInputStream`, `InputStream` và `IOException`. Trong trường hợp `length == 0`, wrapper vẫn truyền 0 về bên dưới, giữ hành vi zero-length read.

Lý do quan trọng: thuật toán đúng không được dựa vào “`read(buffer)` luôn trả `buffer.length`”; nhiều nguồn thật trả ít hơn do network, buffering hoặc EOF.

### 10.2. Theo dõi flush và close

~~~java
final class TrackingOutputStream extends ByteArrayOutputStream {
    int flushCount;
    int closeCount;

    @Override
    public void flush() throws IOException {
        flushCount++;
        super.flush();
    }

    @Override
    public void close() throws IOException {
        closeCount++;
        super.close();
    }
}
~~~

Đây là mảnh class có thể đặt trong test và cần import tương ứng. Với thiết kế `copy` ở phần 5, ta kỳ vọng:

- Sau copy thành công, `flushCount == 1`.
- `closeCount == 0` vì hàm `copy` không sở hữu output stream.
- Khi caller tự đóng output, `closeCount` mới tăng.

Nếu test muốn xác minh resource được đóng khi có lỗi, hãy tạo wrapper có close tracking và dùng code adapter có `try-with-resources`. Nhưng không nên biến mọi helper xử lý thành hàm tự đóng stream của caller.

### 10.3. Test lỗi InputStream giữa chừng

Một lớp có thể ném lỗi sau hai byte:

~~~java
final class FailAfterTwoBytes extends InputStream {
    private int position;

    @Override
    public int read() throws IOException {
        if (position == 2) {
            throw new IOException("Injected read error");
        }
        position++;
        return 'x';
    }
}
~~~

Đây là mảnh class test. Lưu ý `InputStream.read(byte[],off,len)` mặc định có thể **trả phần dữ liệu đã đọc thành công trước khi gặp IOException**, rồi ném lỗi ở lời gọi tiếp theo. Vì vậy đừng viết test đòi “lần gọi đầu tiên phải ném” khi wrapper có thể trả partial read trước.

Cần kiểm thử rằng lỗi cuối cùng được chuyển tới caller, không được silently ignore hoặc biến thành kết quả đã copy đủ dữ liệu.

## 11. In-memory test có thể bỏ sót điều gì?

Kiểm thử bằng `ByteArrayInputStream`/`ByteArrayOutputStream` hữu ích nhưng không mô phỏng hoàn chỉnh môi trường sản xuất:

| Hành vi quan trọng | In-memory test | Vì sao cần test tệp thật / môi trường khác |
| --- | --- | --- |
| Đọc/ghi bytes và transform | Rất phù hợp. | Algorithm có thể được test đầy đủ. |
| EOF, short read, lỗi giả lập | Có thể chủ động mô phỏng. | Stream giả chỉ mô phỏng các trường hợp đã nghĩ tới. |
| Charset encode/decode | Có thể test bằng byte fixture. | Provider, file BOM, dữ liệu thực tế có thể đa dạng hơn. |
| Quyền truy cập và ACL | Không mô phỏng thật. | Hệ điều hành/provider kiểm soát quyền. |
| Symlink/path traversal/TOCTOU | Không đủ. | Tác động đường dẫn và đối tượng tệp thật. |
| Kích thước/độ bền sau flush | Không kiểm chứng. | `flush` không tương đương `FileChannel.force`/fsync. |
| File lock và concurrent writer | Không thực tế. | Cần process/thread/filesystem test. |
| Tên tệp, separator, case sensitivity | Không có trong byte stream. | Khác nhau theo OS/provider. |
| Atomic move/rename | Không được kiểm tra. | Phụ thuộc filesystem. |
| File bị truncate trong lúc đọc | Có thể giả stream lỗi, không đủ. | Cần kiểm tra cơ chế file/ownership thật. |
| Buffering/close của file/network | Chỉ theo custom wrappers. | Runtime/hệ điều hành có semantics riêng. |
| ZIP/GZIP nén/giải nén | Có thể dùng byte array rất tốt. | Nếu phụ thuộc file metadata/quota/path extraction phải test riêng. |

Một phép kiểm tra memory stream thành công chứng minh **logic được test chạy đúng trên input và stream double đã dùng**, chứ không chứng minh tất cả resource thực sẽ hoạt động đúng.

## 12. Khi nào chuyển từ unit test sang integration test với file?

Một trình tự thực tế:

1. **Kiểm thử core** với `ByteArrayInputStream`/`ByteArrayOutputStream` hoặc `StringReader`/`StringWriter`: nội dung, empty, chunk, EOF, lỗi I/O được mô phỏng.
2. **Kiểm thử adapter** mở file bằng thư mục tạm `Files.createTempDirectory` hoặc JUnit `@TempDir`: xác nhận đường dẫn, quyền, đóng resource, file có nội dung kỳ vọng.
3. **Kiểm thử định dạng** với file/stream thật của XML, JSON, ZIP, GZIP hoặc binary protocol: charset, metadata, cấu trúc.
4. **Kiểm thử môi trường đặc biệt** khi yêu cầu: readonly filesystem, thiếu quyền, symbolic link, atomic move, file lock, file bị thay đổi đồng thời, networking.
5. **E2E / stress tests** cho dữ liệu lớn, cạnh tranh, tải cao, timeout, resource leaks và hành vi sau crash.

Không nhất thiết chạy tất cả integration tests ở mỗi chỉnh sửa nhỏ, nhưng nên có ít nhất một tập kiểm tra adapter tệp thật trong CI tương ứng những nền tảng mục tiêu.

### 12.1. Test với tệp tạm để xác nhận adapter

~~~java
Path input = Files.createTempFile("input-", ".bin");
Path output = Files.createTempFile("output-", ".bin");
try {
    byte[] original = {0, 1, 2, (byte) 0xFF};
    Files.write(input, original);

    long count = copyFile(input, output);
    if (count != original.length
            || !Arrays.equals(original, Files.readAllBytes(output))) {
        throw new AssertionError("File adapter sai");
    }
} finally {
    Files.deleteIfExists(input);
    Files.deleteIfExists(output);
}
~~~

Đây là **mảnh code minh họa tích hợp**, giả định hai phương thức `copy`/`copyFile` trong phần trước đã được khai báo, và các import `Files`, `Path`, `Arrays` có sẵn. Trong bài kiểm thử thật, nên dùng thư mục tạm riêng thay vì tên dự đoán được; JUnit có `@TempDir` để cung cấp thư mục riêng và dọn sau bài test.

**Không tạo file tạm trong một vị trí dùng chung rồi giả định không ai khác có thể thay đổi nó.** Khi dữ liệu không tin cậy, phải có chính sách quyền/ownership phù hợp. `Files.createTempFile` tạo tên khó đoán và tạo mới nguyên tử theo provider, nhưng những giả định về bảo mật vẫn phụ thuộc hệ điều hành.

## 13. Test bằng JUnit 5 thay cho main có AssertionError

Chương trình `MemoryStreamTestDemo` chạy được chỉ với Java 17, phù hợp ví dụ độc lập. Trong dự án thật, nên tách từng case thành test method bằng JUnit Jupiter và tích hợp Maven/Gradle.

Ví dụ một phương thức test (không phải mã độc lập nếu chưa có JUnit):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

@Test
void copyWorksWithShortReads() throws IOException {
    byte[] original = "AéB".getBytes(StandardCharsets.UTF_8);

    ByteArrayOutputStream target = new ByteArrayOutputStream();
    try (InputStream source = new TwoByteInputStream(original)) {
        long copied = copy(source, target);
        assertEquals(original.length, copied);
    }

    assertArrayEquals(original, target.toByteArray());
}
~~~

Code trên giả định có phương thức `copy` và lớp `TwoByteInputStream` trong lớp test, cùng các import `java.io.*` và `StandardCharsets`. Cần dependency JUnit Jupiter và test runner tương ứng, khác với ví dụ main không có dependency ở phần 7.

### 13.1. Assert theo ý nghĩa hợp đồng

- **`assertArrayEquals(expected, actual)`:** chính xác byte-by-byte với payload binary.
- **`assertEquals(expectedText, actualText)`:** phù hợp với output text sau khi đã định nghĩa charset.
- **`assertThrows(IOException.class, ...)`:** xác minh đường thất bại đúng loại lỗi.
- **`assertTimeout...`:** cần dùng thận trọng; timeout test không phải bằng chứng mọi I/O trong production có deadline phù hợp.
- **`@TempDir`:** cho integration test filesystem mà không phải tự dự đoán tên file hoặc làm bẩn repository.

Đừng chỉ dùng `assertTrue(output.size() > 0)` cho thuật toán copy. Nó không phát hiện thiếu byte, lặp byte, sai thứ tự hay encoding sai.

## 14. Quy tắc tạo fixture ổn định và dễ chẩn đoán

Một test tốt nên **ít phụ thuộc môi trường**:

- Không dùng `Charset.defaultCharset()` hoặc `String.getBytes()` thiếu charset nếu test cần kết quả byte xác định.
- Không phụ thuộc line separator của OS: dùng ký tự `\n`/`\r\n` do test định nghĩa hoặc chuẩn hóa đầu ra trước khi so sánh, tùy yêu cầu.
- Không dùng `System.currentTimeMillis()` cho nội dung kỳ vọng khi có thể truyền clock giả hoặc giá trị cố định.
- Không dựa vào thứ tự trả về của `Files.list`/directory iteration nếu không có quy tắc sort.
- Không phụ thuộc port mạng cố định khi có thể để OS cấp port 0, nhưng đó đã là integration test network chứ không còn unit test memory.
- Không dùng mảng/shared stream mutable giữa các test chạy song song; tạo fixture riêng cho từng test.
- Khi thất bại, đưa vào thông điệp assert số byte kỳ vọng/thực tế và định dạng hex với binary payload.
- Đối với test Unicode, cần có fixture đa byte UTF-8 và supplementary code point khi logic xử lý code point.
- Không vô tình đưa dữ liệu thật nhạy cảm vào fixture hoặc log của CI.

## 15. Chọn stream giả nào cho từng trường hợp?

| Muốn kiểm tra | Gợi ý |
| --- | --- |
| Sao chép byte và đối chiếu tuyệt đối | `ByteArrayInputStream` + `ByteArrayOutputStream`. |
| Parser dòng văn bản | `StringReader` / `BufferedReader`. |
| Format text output | `StringWriter`. |
| Chuyển đổi UTF-8 | `ByteArrayInputStream` + `InputStreamReader(UTF_8)`. |
| Write bytes có độ dài và số nhị phân | `DataOutputStream` bọc `ByteArrayOutputStream`. |
| Read protocol theo số nhị phân | `DataInputStream` bọc `ByteArrayInputStream`. |
| Đọc chậm/chia chunk | `FilterInputStream` tùy chỉnh giới hạn read size. |
| Phát sinh IOException | Custom `InputStream` / `OutputStream`. |
| Kiểm tra flush/close | Wrapper ghi nhận số lần gọi. |
| Đếm byte output rất lớn mà không giữ toàn bộ trong RAM | `OutputStream` tùy chỉnh chỉ tăng counter/checksum. |
| Kiểm tra path/ACL/symlink/provider | Integration test với tệp thực. |

Một mô hình bền vững là **core stream-oriented + adapters resource-oriented**. Core chỉ biết `InputStream`/`OutputStream` hoặc `Reader`/`Writer`, còn adapter xử lý `Path`, file locks, buffer policy, charset và vòng đời OS resource.

## 16. Những sai lầm thường gặp

### 16.1. Tin ByteArrayInputStream có hành vi giống mọi nguồn thực

`ByteArrayInputStream` thường trả dữ liệu tức thì và hỗ trợ `mark/reset`, nên code có lỗi giả định về short read hoặc `available()` có thể vẫn “đúng” trong test cơ bản. Bổ sung stream giả giới hạn read, và không gọi `available()` để đo tổng chiều dài input chung.

### 16.2. Luôn truyền buffer.length thay cho n

Lượt đọc cuối có thể ít byte hơn buffer; ghi `output.write(buffer)` sẽ đưa byte cũ của lượt trước vào output. Dùng `write(buffer, 0, n)` với **n thực nhận**.

### 16.3. Chuyển text bằng charset mặc định

`new String(bytes)` và `text.getBytes()` thiếu charset có thể khác nhau theo runtime/OS. Chỉ rõ `StandardCharsets.UTF_8` (hoặc charset theo protocol) để test có tính tái lập.

### 16.4. Không tách xử lý khỏi mở file

Hàm chỉ nhận `Path` và tự mở tệp trong mọi nhánh khiến các kiểm thử chính phải tạo file tạm và phối hợp cleanup không cần thiết. Tách core thành hàm nhận stream, adapter mở file ở biên.

### 16.5. Đóng stream của caller trong core

Một phương thức helper tự đóng `OutputStream` được chia sẻ có thể khiến pipeline phía sau không tiếp tục ghi được. Hãy xác định **ai sở hữu stream** và kiểm thử hợp đồng đó. Test riêng với ByteArrayOutputStream có thể không phát hiện vì close của lớp đó vô hiệu.

### 16.6. Chỉ kiểm tra happy path

Không kiểm tra empty input, short read, encoding, dữ liệu nhị phân có `0x00`, IOException giữa chừng và xử lý output lỗi khiến phần lớn bug I/O bị bỏ sót.

### 16.7. Dùng memory output cho dữ liệu lớn không giới hạn

`ByteArrayOutputStream` giữ toàn bộ byte và có thể tăng nhiều bộ nhớ. Stress test cho stream dữ liệu lớn nên dùng sink đếm byte/checksum, hoặc môi trường tệp tạm và giới hạn cụ thể.

### 16.8. Coi test trong RAM là đủ cho filesystem semantics

Một method dùng `Files.move`, `Files.delete`, `FileChannel.force` hay file lock phụ thuộc OS/provider; stream memory không thể kiểm tra ý nghĩa của chúng. Cần integration tests thích hợp.

### 16.9. Nhầm write thành công với lưu dữ liệu bền vững

`ByteArrayOutputStream.flush()` không biểu diễn fsync. Trong tệp thật, `OutputStream.flush()` không mặc định bảo đảm bytes đã nằm bền vững trên thiết bị; với yêu cầu durability, kiểm tra API như `FileChannel.force` và tài liệu provider.

### 16.10. Tự viết file giả quá phức tạp

Chỉ giả lập **hành vi cần kiểm thử** (read chunk ngắn, lỗi, close tracking). Đừng tự tái tạo toàn bộ filesystem trong một mock khó chứng minh đúng; khi cần kiểm tra path/file attributes, chuyển sang tệp tạm và provider thật.

## 17. Câu hỏi tự kiểm tra

1. **Vì sao truyền InputStream/OutputStream thay vì chỉ truyền Path giúp test nhanh hơn?** Vì có thể thay nguồn/đích bằng memory streams, không cần truy cập filesystem cho thuật toán.
2. **`ByteArrayInputStream.read()` trả gì khi hết dữ liệu?** `-1`.
3. **`ByteArrayInputStream` có tự sao chép mảng được đưa vào không?** Không, nó dùng mảng đó làm backing data.
4. **`ByteArrayOutputStream.toByteArray()` có chia sẻ mảng nội bộ không?** Không, trả một bản sao.
5. **Một read nhận 2 byte vào buffer 8 byte thì write bao nhiêu byte?** Đúng 2 byte qua `write(buffer, 0, 2)`.
6. **`AéB` dưới UTF-8 có bao nhiêu byte?** 4 byte.
7. **`StringReader` có kiểm tra quá trình giải mã UTF-8 không?** Không; nó đọc ký tự đã có.
8. **Dùng gì để test decoder UTF-8 từ bytes?** `ByteArrayInputStream` cùng `InputStreamReader`/`CharsetDecoder` với charset và chính sách lỗi cụ thể.
9. **Vì sao mark/reset test chỉ dùng ByteArrayInputStream là chưa đủ?** Stream này hỗ trợ mark, nhưng nhiều stream khác không.
10. **Khi output ném IOException sau vài byte, copy có được báo thành công không?** Không; phải truyền/giải quyết lỗi đúng hợp đồng.
11. **Ai nên đóng stream đã được caller truyền cho helper?** Theo ownership đã định; nếu caller sở hữu thì helper không tự đóng.
12. **`flush()` của ByteArrayOutputStream có chứng minh dữ liệu đã nằm bền vững trên disk không?** Không.
13. **Bao giờ phải chuyển sang test tệp thật?** Khi kiểm tra mở/đóng file, permission, symlink, atomic move, metadata, file locks, durability hoặc provider behavior.
14. **Có nên dùng assert output không rỗng thay cho so sánh toàn bộ byte?** Không; thiếu/lặp/sai thứ tự có thể vẫn cho output không rỗng.
15. **Cách mô phỏng read chunk nhỏ trong unit test?** Dùng custom InputStream/FilterInputStream trả tối đa 1–2 byte mỗi lần.
16. **Vì sao một số trường hợp malformed UTF-8 cần CharsetDecoder với REPORT?** Vì decode mặc định có thể thay byte không hợp lệ bằng ký tự replacement, không ném lỗi theo mong muốn.
17. **Làm sao kiểm thử file copy với tệp tạm?** Viết input, gọi adapter, đọc output rồi so sánh byte và dọn resource, hoặc dùng JUnit `@TempDir`.
18. **Nếu logic dựa trên tính duy nhất của đường dẫn, memory streams có đủ không?** Không. Cần filesystem integration test và mô hình concurrency thích hợp.

## 18. Tài liệu Java 17 chính thức

- [ByteArrayInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayInputStream.html) và [ByteArrayOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html): stream byte trong bộ nhớ.
- [StringReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/StringReader.html) và [StringWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/StringWriter.html): stream ký tự.
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html) và [OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): hợp đồng chung, EOF, read/write.
- [InputStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html) và [CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): decode byte thành char.
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): adapter tệp thật, tệp tạm và thao tác đường dẫn.

**Ghi nhớ:** trước khi kiểm thử trên file thật, hãy tạo **core nhận InputStream/OutputStream hoặc Reader/Writer** và kiểm chứng bằng ByteArrayInputStream/ByteArrayOutputStream, StringReader/StringWriter. Thêm fixture empty, Unicode, read chunk ngắn và IOException để kiểm tra đường thất bại. Sau khi core ổn định, dùng integration test với tệp tạm để kiểm chứng **filesystem semantics**, đừng coi memory stream là một filesystem giả hoàn chỉnh.

# Inflater với ByteBuffer và cập nhật vị trí (Java 11 trở lên)

## 1. Vấn đề cần hiểu: giải nén làm thay đổi cả vị trí đọc và vị trí ghi

`java.util.zip.Inflater` là bộ giải nén **DEFLATE** có trạng thái. Với cấu hình mặc định `new Inflater()`, đầu vào thường là luồng nén theo định dạng **zlib** (có header và checksum). Từ **Java 11**, có thể cấp dữ liệu nén trực tiếp bằng `ByteBuffer` và yêu cầu ghi kết quả giải nén vào `ByteBuffer`:

```java
Inflater inflater = new Inflater();

inflater.setInput(compressedBuffer);       // Đầu vào: ByteBuffer
int produced = inflater.inflate(outputBuffer); // Đầu ra: ByteBuffer
```

Điểm đặc biệt của hai overload này là **Inflater cập nhật `position()` của các buffer khi nó thực sự tiêu thụ/sinh dữ liệu**. Người học cần hiểu độc lập:

1. `compressedBuffer.position()` tăng khi Inflater tiêu thụ các **byte nén**, tối đa đến `compressedBuffer.limit()`.
2. `outputBuffer.position()` tăng khi Inflater sinh **byte đã giải nén**, với số byte bằng giá trị trả về của `inflate(outputBuffer)` khi thành công.
3. Không có quy tắc rằng mỗi byte nén sinh đúng một byte đầu ra. **Mức tăng hai vị trí thường khác nhau**.
4. `inflate` là thao tác có trạng thái: nếu đầu ra đầy, có thể cần gọi tiếp với buffer đầu ra khác; nếu đầu vào đã hết, có thể phải cung cấp chunk nén kế tiếp.
5. **Đã nhận đủ byte văn bản dự kiến chưa chắc là luồng nén đã hoàn chỉnh**: cần kiểm tra `inflater.finished()` để xác định bộ giải nén đã thấy kết thúc hợp lệ của luồng nén.

Đây là các quy tắc API đã có từ Java 11 và tiếp tục được hỗ trợ trong Java hiện hành. Bài này tập trung vào quản lý `ByteBuffer`, trạng thái của `Inflater` và các lỗi dễ gặp khi xử lý dữ liệu nén.

## 2. Nhớ mô hình position, limit, capacity trước khi dùng Inflater

Với một `ByteBuffer`:

- `capacity()`: kích thước vùng chứa, không thay đổi trong vòng đời của buffer.
- `position()`: vị trí thao tác đọc/ghi tiếp theo theo ngữ cảnh sử dụng.
- `limit()`: ranh giới **không được vượt qua** khi đọc/ghi.
- `remaining()`: số phần tử từ `position` đến `limit`, bằng `limit - position`.
- `hasRemaining()`: cho biết còn phần tử trong vùng `[position, limit)` hay không.

Ví dụ:

```java
ByteBuffer buffer = ByteBuffer.allocate(16);
buffer.position(3);
buffer.limit(10);

System.out.println(buffer.remaining()); // 7
```

Ở đây chỉ vùng index `3..9` đang được nhìn như dữ liệu có thể đọc/ghi; `capacity = 16` không khiến Inflater tự động đọc đến byte thứ 16.

Hai thao tác trạng thái rất quan trọng:

```java
buffer.clear(); // position = 0, limit = capacity; chuẩn bị ghi đè dữ liệu
buffer.flip();  // limit = position cũ, position = 0; chuẩn bị đọc dữ liệu đã ghi
```

`clear()` **không xóa/zero hóa các byte vật lý**; nó chỉ đặt lại mốc position/limit. `flip()` cũng không chuyển đổi hay sao chép byte.

Khi dùng `Inflater`, đầu vào thường ở **read mode**: buffer đã được `flip()` sau khi điền byte, có `position` trỏ tới byte nén đầu tiên và `limit` ở sau byte nén cuối. Buffer đầu ra thường ở **write mode**, có phần từ `position` đến `limit` để nhận byte giải nén.

### Minh họa từng bước

```text
ĐẦU VÀO (byte nén)
            position          limit
               |                |
[header...][ byte nén còn lại ][không truy cập]
         -- Inflater.consume -->
            position tăng dần

ĐẦU RA (byte đã giải nén)
           position                   limit
              |                         |
[byte đã ghi][   vùng còn để ghi       ]
           -- Inflater.produce -->
              position tăng dần
```

Đọc một đầu ra hoàn tất cho mỗi lượt thường theo thứ tự:

```java
output.flip();  // chuyển byte đã giải nén thành vùng để đọc
// Tiêu thụ output.get(...) hoặc gửi đi nơi khác
output.clear(); // chỉ sau khi đã tiêu thụ hết dữ liệu cần giữ
```

Nếu gọi `clear()` trước khi lấy dữ liệu đã giải nén, chương trình có thể ghi đè lên dữ liệu chưa xử lý.

## 3. Hợp đồng chính xác của API ByteBuffer

| API | Tác động đến buffer | Ý nghĩa |
| --- | --- | --- |
| `setInput(ByteBuffer input)` | **Chưa cần** tăng position ngay lúc gọi; các lượt `inflate(...)` sau sẽ đẩy `input.position` theo số byte nén đã tiêu thụ | Cung cấp vùng `[position,limit)` làm dữ liệu nén |
| `inflate(ByteBuffer output)` | Ghi từ `output.position`, tăng vị trí đầu ra theo số byte giải nén thực sự sinh | Trả `int produced`; có thể trả 0 nếu chưa thể sinh thêm |
| `inflate(byte[] output)` | Không có `ByteBuffer` đầu ra để tự cập nhật; vẫn có thể đẩy vị trí input nếu trước đó gọi `setInput(ByteBuffer)` | Thay loại vùng đích nhưng không thay cách theo dõi input |
| `getRemaining()` | Không sửa buffer | Số byte đầu vào **chưa bị tiêu thụ** trong vùng đã cấp |
| `needsInput()` | Không sửa buffer | `true` khi Inflater không còn dữ liệu đầu vào đã cấp để dùng |
| `needsDictionary()` | Không sửa buffer | `true` khi luồng nén cần dictionary định trước |
| `finished()` | Không sửa buffer | `true` khi đã đạt kết thúc của luồng nén theo định dạng |
| `getBytesRead()` | Không sửa buffer | Tổng byte nén đã tiêu thụ từ lúc khởi tạo/reset |
| `getBytesWritten()` | Không sửa buffer | Tổng byte giải nén đã sinh từ lúc khởi tạo/reset |
| `end()` | Giải phóng tài nguyên của bộ giải nén | Phải gọi khi không còn sử dụng Inflater |

**Chú ý:** `inflate(ByteBuffer)` ném `DataFormatException` nếu dữ liệu nén không hợp lệ và ném `ReadOnlyBufferException` nếu buffer **đầu ra** là read-only. Buffer **đầu vào** có thể là read-only vì Inflater chỉ đọc từ nó. Heap buffer (`ByteBuffer.allocate`) và direct buffer (`ByteBuffer.allocateDirect`) đều dùng được.

Một chi tiết dễ bỏ sót trong hợp đồng API: nếu `DataFormatException` xảy ra, **position của input/output có thể đã được cập nhật** theo phần dữ liệu thực sự tiêu thụ/sinh ra **trước khi** exception xuất hiện; các bộ đếm byte cũng cập nhật. Không được giả định một lượt inflate là thao tác nguyên tử có thể rollback bằng cách dùng lại position cũ.

### Cách đo tiến độ trong một lần inflate

```java
int beforeIn = input.position();
int beforeOut = output.position();

int produced = inflater.inflate(output);

int consumedCompressed = input.position() - beforeIn;
int producedUncompressed = output.position() - beforeOut;

System.out.println(producedUncompressed == produced); // true khi thành công
```

Trong đoạn này, `input` chính là buffer đã truyền vào `setInput(input)`. `consumedCompressed` đo byte nén đã được tiêu thụ **trong lời gọi này**, còn `produced` đo byte giải nén vừa ghi. Thường `consumedCompressed != produced`. Nếu đầu vào được cấp bằng `setInput(byte[])` thì không có một input `ByteBuffer` tương ứng để tự đọc thay đổi position; thay vào đó dùng `getBytesRead()`/`getRemaining()` nếu cần theo dõi tiến độ.

Giá trị `produced == 0` **không mặc nhiên là EOF, không mặc nhiên là lỗi và không đủ để kết luận đã giải nén xong**. Cần kiểm tra trạng thái của Inflater.

## 4. Chu kỳ chuẩn với một output buffer nhỏ

Mỗi lần cấp buffer đầu ra, chương trình nên:

1. Đặt buffer đầu ra ở trạng thái có thể ghi, ví dụ `output.clear()` nếu dữ liệu cũ đã được chuyển đi.
2. Gọi `int n = inflater.inflate(output)`.
3. Với lượt thành công, kiểm tra `n` và `output.position()` (đã tăng `n` so với đầu lượt).
4. Gọi `output.flip()` để đọc chính những byte vừa sinh; chỉ đọc đến `output.limit()`.
5. Tiêu thụ/copy/gửi các byte đầu ra.
6. Nếu chưa `finished()`, lặp lại. Khi `n == 0`, kiểm tra `needsDictionary()`, `needsInput()` và dấu hiệu không tiến triển để quyết định bước tiếp.

Ví dụ **mã khung** (đặt trong phương thức có thể ném `DataFormatException`/`IOException`; giả định đã cấp đủ compressed input và có `ByteArrayOutputStream result`):

```java
ByteBuffer output = ByteBuffer.allocate(1024);

while (!inflater.finished()) {
    output.clear();
    int n = inflater.inflate(output);

    output.flip();
    while (output.hasRemaining()) {
        result.write(output.get() & 0xff);
    }

    if (n == 0 && !inflater.finished()) {
        if (inflater.needsDictionary()) {
            throw new IOException("A preset dictionary is required");
        }
        if (inflater.needsInput()) {
            throw new EOFException("Compressed stream is incomplete");
        }
        // Nếu không đầu ra, không hết input, không cần dictionary:
        // kiểm tra tiến độ thực tế để tránh vòng lặp vô hạn.
    }
}
```

Đây là ví dụ **khung ý tưởng**, không thay thế kiểm tra tiến độ đầy đủ. Phần chương trình hoàn chỉnh ở dưới có kiểm tra `input.position()` và chặn tình huống lặp mà không đọc/ghi được dữ liệu.

### Tại sao output buffer nhỏ vẫn hợp lệ?

Bộ giải nén có thể tạo lượng byte đầu ra lớn hơn rất nhiều so với lượng byte đầu vào đã tiêu thụ. Nếu output buffer chỉ có 5 byte `remaining()`, mỗi `inflate(output)` có thể chỉ tạo tối đa 5 byte trong lượt ấy; dữ liệu chưa giải nén sẽ được xử lý ở lượt kế. Không phải tạo output buffer bằng kích thước đã giải nén ngay từ đầu, và **cũng không được giả định một lần `inflate` xuất toàn bộ payload**.

Nếu output có `remaining() == 0`, không còn chỗ ghi; lời gọi thường không tạo tiến độ. Phải `flip()` và giải phóng/chuyển dữ liệu cũ trước khi gọi tiếp, không spin trong vòng lặp với một buffer luôn đầy.

## 5. Ví dụ hoàn chỉnh: cập nhật position, direct output và byte đuôi còn lại

Tình huống: một vùng byte gồm **2 byte tiền tố** không thuộc dữ liệu zlib, tiếp theo là **một luồng zlib**, rồi **2 byte marker** thuộc cấu trúc bao ngoài. Ta sẽ:

- Đặt `input.position(2)` để bắt đầu giải nén ngay sau tiền tố.
- Cấp `input` cho `Inflater`.
- Giải nén nhiều lượt vào `ByteBuffer.allocateDirect(5)`.
- Theo dõi vị trí đầu vào/đầu ra và đối chiếu bộ đếm.
- Sau khi `finished()`, giữ lại 2 byte marker chưa bị dùng trong quá trình giải nén.
- Thử buffer input read-only, output read-only và một luồng bị cắt cụt.

Lưu file **`InflaterByteBufferDemo.java`**:

```java
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.*;

public class InflaterByteBufferDemo {
    static byte[] compress(String value) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DeflaterOutputStream output =
                new DeflaterOutputStream(bytes)) {
            output.write(value.getBytes(StandardCharsets.UTF_8));
        }
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws Exception {
        String text = "Java 11 / ByteBuffer / Xin ch\u00E0o";
        byte[] expected = text.getBytes(StandardCharsets.UTF_8);
        byte[] compressed = compress(text);

        // [2 byte prefix][zlib stream][2 byte trailer]
        ByteBuffer input =
                ByteBuffer.allocate(2 + compressed.length + 2);
        input.put((byte) 0x11).put((byte) 0x22);
        input.put(compressed).put((byte) 0x33).put((byte) 0x44);
        input.flip();
        input.position(2);

        int start = input.position();
        Inflater inflater = new Inflater();
        ByteBuffer output = ByteBuffer.allocateDirect(5);
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        boolean outputPositionsMatch = true;

        try {
            inflater.setInput(input);

            while (!inflater.finished()) {
                output.clear();
                int beforeInput = input.position();
                int beforeOutput = output.position();

                int produced = inflater.inflate(output);

                outputPositionsMatch &=
                        output.position() - beforeOutput == produced;

                output.flip();
                while (output.hasRemaining()) {
                    result.write(output.get() & 0xff);
                }

                if (produced == 0 && !inflater.finished()) {
                    if (inflater.needsDictionary()) {
                        throw new IOException("Dictionary required");
                    }
                    if (inflater.needsInput()) {
                        throw new EOFException("Truncated zlib stream");
                    }
                    if (input.position() == beforeInput) {
                        throw new IOException("No decompression progress");
                    }
                }
            }

            System.out.println("start=" + start);
            System.out.println("inputPositionOK=" +
                    (input.position() - start == compressed.length));
            System.out.println("outputPositionsOK=" +
                    outputPositionsMatch);
            System.out.println("bytesReadOK=" +
                    (inflater.getBytesRead() == compressed.length));
            System.out.println("bytesWrittenOK=" +
                    (inflater.getBytesWritten() == expected.length));
            System.out.println("inputRemaining=" + input.remaining());
            System.out.println("inflaterRemaining=" +
                    inflater.getRemaining());
            System.out.println("roundTrip=" +
                    Arrays.equals(expected, result.toByteArray()));
            System.out.println("marker1=" + (input.get() & 0xff));
            System.out.println("marker2=" + (input.get() & 0xff));
        } finally {
            inflater.end();
        }

        // Input read-only: hợp lệ vì Inflater chỉ cần đọc.
        Inflater readOnlyIn = new Inflater();
        try {
            ByteBuffer source = ByteBuffer.wrap(compressed)
                    .asReadOnlyBuffer();
            readOnlyIn.setInput(source);
            ByteBuffer dest = ByteBuffer.allocate(expected.length + 8);
            int produced = readOnlyIn.inflate(dest);
            System.out.println("readOnlyInputOK=" +
                    (produced == expected.length && readOnlyIn.finished()));
        } finally {
            readOnlyIn.end();
        }

        // Output read-only: không thể ghi kết quả giải nén.
        Inflater readOnlyOut = new Inflater();
        try {
            readOnlyOut.setInput(ByteBuffer.wrap(compressed));
            try {
                readOnlyOut.inflate(
                        ByteBuffer.allocate(expected.length + 8)
                                .asReadOnlyBuffer());
            } catch (ReadOnlyBufferException ex) {
                System.out.println("readOnlyOutputRejected=true");
            }
        } finally {
            readOnlyOut.end();
        }

        // Thiếu 2 byte checksum cuối của zlib stream.
        Inflater truncated = new Inflater();
        try {
            ByteBuffer source = ByteBuffer.wrap(
                    Arrays.copyOf(compressed, compressed.length - 2));
            truncated.setInput(source);

            ByteBuffer dest = ByteBuffer.allocate(expected.length + 8);
            int produced = truncated.inflate(dest);

            System.out.println("truncatedProducedAll=" +
                    (produced == expected.length));
            System.out.println("truncatedFinished=" +
                    truncated.finished());
            System.out.println("truncatedNeedsInput=" +
                    truncated.needsInput());
        } finally {
            truncated.end();
        }
    }
}
```

Chạy với JDK 11 hoặc mới hơn:

```bash
javac --release 11 InflaterByteBufferDemo.java
java InflaterByteBufferDemo
```

Stdout với dữ liệu ví dụ:

```text
start=2
inputPositionOK=true
outputPositionsOK=true
bytesReadOK=true
bytesWrittenOK=true
inputRemaining=2
inflaterRemaining=2
roundTrip=true
marker1=51
marker2=68
readOnlyInputOK=true
readOnlyOutputRejected=true
truncatedProducedAll=true
truncatedFinished=false
truncatedNeedsInput=true
```

### Diễn giải kết quả

- `start=2`: inflater bắt đầu đọc dữ liệu nén tại vị trí 2, đã bỏ qua hai byte tiền tố của cấu trúc bao ngoài.
- `inputPositionOK=true`: sau khi luồng zlib hoàn tất, `input.position() - start` đúng bằng độ dài dữ liệu zlib nén.
- `outputPositionsOK=true`: mỗi lần `inflate(output)` thành công, thay đổi `output.position()` đúng bằng số byte được trả về.
- `bytesReadOK`/`bytesWrittenOK`: thống kê nội bộ Inflater khớp với tổng byte nén và tổng byte giải nén. Đây là **tổng tích lũy**, khác phép đo position riêng của một lời gọi.
- `inputRemaining=2` và `inflaterRemaining=2`: Inflater gặp điểm kết thúc zlib trước hai byte marker. Cả hai marker vẫn còn trong `input`, được đọc ra sau đó là 51 (`0x33`) và 68 (`0x44`). Điều này minh họa việc **không đọc tràn qua phần cấu trúc tiếp theo**.
- `roundTrip=true`: sau nhiều lượt giải nén với output buffer chỉ 5 byte, dữ liệu thu được vẫn giống dữ liệu gốc.
- Input read-only được chấp nhận; output read-only bị từ chối bằng `ReadOnlyBufferException`.
- Trường hợp bị cắt 2 byte checksum cuối có thể **đã sinh đủ byte payload**, nhưng `finished()==false` và `needsInput()==true`. Không được coi payload là hợp lệ chỉ vì số byte giải nén trông đủ; cần xác minh kết thúc hợp lệ của luồng nén.

Kích thước byte **nén** có thể thay đổi theo phiên bản thư viện zlib hoặc lựa chọn nén; chương trình chủ động in các so sánh boolean thay vì khẳng định một kích thước nén cố định. Dữ liệu giải nén và quan hệ vị trí vẫn có thể kiểm chứng độc lập.

## 6. Làm việc với input được cấp theo từng chunk

Trong ứng dụng đọc từ file, network hoặc `ReadableByteChannel`, dữ liệu nén có thể đến thành nhiều đoạn. Khi `inflater.needsInput()` trả `true`, chương trình mới cần cấp thêm một chunk bằng `setInput(...)`. Với `ByteBuffer`, phải bảo đảm `position` và `limit` bao trùm chính xác số byte thực sự vừa nhận.

Đoạn mã dưới đây minh họa dữ liệu nén **đã có trong mảng** nhưng được cấp theo từng đoạn 3 byte, để mô phỏng nguồn chỉ cung cấp các mảnh nhỏ. Đây là **phương thức hỗ trợ đặt trong một lớp**, dùng cùng các import `java.io.*`, `java.nio.ByteBuffer` và `java.util.zip.*`.

```java
static byte[] inflateFragments(byte[] compressed, int maxOutputBytes)
        throws IOException, DataFormatException {
    Inflater inflater = new Inflater();
    ByteArrayOutputStream result = new ByteArrayOutputStream();
    ByteBuffer output = ByteBuffer.allocate(16);
    ByteBuffer activeInput = null;
    int nextOffset = 0;

    try {
        while (!inflater.finished()) {
            if (inflater.needsInput()) {
                if (nextOffset == compressed.length) {
                    throw new EOFException("Incomplete compressed stream");
                }

                int chunkLength = Math.min(
                        3, compressed.length - nextOffset);
                activeInput = ByteBuffer.wrap(
                        compressed, nextOffset, chunkLength);
                nextOffset += chunkLength;
                inflater.setInput(activeInput);
            }

            int beforeInput = activeInput.position();

            output.clear();
            int produced = inflater.inflate(output);

            if (produced > maxOutputBytes - result.size()) {
                throw new IOException("Decompressed output too large");
            }

            output.flip();
            while (output.hasRemaining()) {
                result.write(output.get() & 0xff);
            }

            if (produced == 0 && !inflater.finished()) {
                if (inflater.needsDictionary()) {
                    throw new IOException("Dictionary required");
                }
                if (!inflater.needsInput()
                        && activeInput.position() == beforeInput) {
                    throw new IOException("Inflate made no progress");
                }
            }
        }
        return result.toByteArray();
    } finally {
        inflater.end();
    }
}
```

Một lời gọi minh họa (sau khi đã có `byte[] compressed` ở định dạng zlib):

```java
byte[] plain = inflateFragments(compressed, 1_000_000);
```

Ý nghĩa:

1. `ByteBuffer.wrap(compressed, nextOffset, chunkLength)` tạo buffer view cho mảnh dữ liệu. Chú ý overload này có **`position = nextOffset` và `limit = nextOffset + chunkLength`**, không tạo vị trí 0.
2. Sau khi `setInput(activeInput)`, mỗi lượt inflate làm tăng `activeInput.position()` theo lượng nén đã tiêu thụ.
3. Chỉ khi `needsInput()` đúng mới cấp mảnh tiếp theo; không tự ý bỏ phần còn lại của mảnh hiện tại.
4. Output buffer 16 byte được `clear()`, gọi `inflate`, `flip()` và tiêu thụ hết trước khi dùng tiếp.
5. Kiểm tra `maxOutputBytes` **trước khi** thêm byte vào kết quả. Trong hệ thống thật, chọn giới hạn phù hợp để tránh payload nén nhỏ nhưng bung ra cực lớn.
6. Nếu hết tất cả byte nguồn mà chưa `finished()`, phương thức báo `EOFException` thay vì trả thành công một payload có thể thiếu trailer hoặc checksum.

Đây là mô phỏng chunk trên mảng nén sẵn. Với `SocketChannel` ở chế độ không chặn, `read()` còn có thể trả 0; cần quản lý sự kiện đọc và tránh vòng lặp quay CPU khi chưa có byte mới. Với `InputStream` chặn, phải quản lý timeout và EOF theo giao thức bao ngoài.

### Khi nào dùng clear, flip và compact cho input?

Giả sử chương trình điền dữ liệu vào buffer bằng `channel.read(input)`:

```java
ByteBuffer input = ByteBuffer.allocate(4096);

// Trong pha ghi từ channel:
input.clear();
int n = channel.read(input);

// Chỉ sau khi n > 0 và buffer chứa byte hợp lệ:
input.flip();
inflater.setInput(input);
```

Sau đó **Inflater tự tăng `input.position()`** mỗi khi tiêu thụ dữ liệu nén. Nếu còn `input.hasRemaining()`, chưa được `clear()` buffer rồi ghi đè vùng chứa byte chưa sử dụng. Trong trường hợp muốn dồn byte chưa xử lý về đầu buffer để điền thêm, `compact()` giữ phần từ position đến limit; nhưng chỉ thao tác buffer **giữa các lượt inflate** và quản lý lại `setInput(...)` một cách có kiểm soát.

Khi đọc nhiều frame từ cùng một kênh, dữ liệu dư sau `finished()` có thể thuộc frame tiếp theo. Phải giữ các byte dư hoặc trả chúng về parser của protocol; **không tự xóa chúng bằng `clear()`**.

## 7. Đọc position qua slice, duplicate và wrap

### `slice()` cho một view độc lập về position/limit

```java
ByteBuffer source = ByteBuffer.wrap(new byte[]{10, 20, 30, 40, 50});
source.position(1);
source.limit(4);

ByteBuffer slice = source.slice();

System.out.println(slice.position());  // 0
System.out.println(slice.limit());     // 3
System.out.println(source.position()); // 1
```

`slice` tạo view chia sẻ dữ liệu nhưng có position/limit riêng, nên sau khi gọi `inflater.setInput(slice)`, Inflater cập nhật **`slice.position()`**, không cập nhật `source.position()`. Điều này hữu ích khi parser bên ngoài cần giữ nguyên vị trí của buffer gốc, nhưng chính bạn phải tự cập nhật parser dựa trên số byte đã tiêu thụ từ view.

`duplicate()` cũng chia sẻ dữ liệu nhưng có các mốc position/limit độc lập. Tránh dùng `duplicate()` rồi giả định Inflater đã di chuyển vị trí của buffer ban đầu.

### `ByteBuffer.wrap(byte[], offset, length)` không reset position về 0

```java
byte[] bytes = {10, 20, 30, 40, 50};

ByteBuffer view = ByteBuffer.wrap(bytes, 2, 2);
System.out.println(view.position());  // 2
System.out.println(view.limit());     // 4
System.out.println(view.remaining()); // 2
```

Muốn đọc vị trí tính từ 0, có thể tạo `view.slice()`; nếu không, cần nhớ position tính trên mảng gốc. Dù là heap hay direct buffer, chính `position/limit` của đối tượng **được truyền vào `setInput`** mới là các mốc mà Inflater cập nhật.

## 8. Đọc đúng trạng thái: finished, needsInput, needsDictionary và return 0

`int produced = inflater.inflate(output)` có thể trả `0` trong nhiều tình huống khác nhau:

| Trạng thái sau lượt inflate | Ý nghĩa | Bước xử lý |
| --- | --- | --- |
| `finished() == true` | Đã đạt kết thúc hợp lệ của stream nén | Chốt payload, xử lý byte dư theo giao thức |
| `needsInput() == true`, chưa finished | Hết chunk đầu vào đã cấp, nhưng stream nén có thể còn tiếp | Cấp chunk tiếp theo; nếu nguồn thực sự EOF, báo stream bị cắt |
| `needsDictionary() == true` | Luồng zlib yêu cầu preset dictionary | Xác định đúng dictionary theo protocol, cấp bằng `setDictionary` |
| Output có `remaining() == 0` | Không còn chỗ để xuất byte | Lấy dữ liệu cũ ra, `clear()`/chuẩn bị buffer mới |
| Không thuộc các trạng thái trên và không có tiến độ | Có nguy cơ vòng lặp vô hạn hoặc giả định sai | Đo chênh lệch position/counters và báo lỗi khi thực sự không tiến triển |

`needsInput()` không đồng nghĩa `finished()`. Một luồng zlib bị cắt ngắn phần checksum có thể trả ra mọi byte giải nén nhưng vẫn `finished()==false`; coi `needsInput()` là dấu hiệu thành công sẽ âm thầm chấp nhận dữ liệu không hợp lệ.

### Preset dictionary và vị trí của buffer dictionary

Một số luồng zlib được tạo với *preset dictionary*. Khi `inflate(...)` trả 0 và `needsDictionary()` đúng, có thể dùng `getAdler()` để nhận mã Adler-32 của dictionary được yêu cầu (giúp nhận diện dictionary trong tập cấu hình đã được thống nhất), rồi cấp dictionary phù hợp:

```java
if (inflater.needsDictionary()) {
    ByteBuffer dictionary = ByteBuffer.wrap(knownDictionaryBytes);
    inflater.setDictionary(dictionary);

    System.out.println(dictionary.position() == dictionary.limit());
    // true: setDictionary(ByteBuffer) tiêu thụ toàn bộ vùng dictionary
}
```

`setDictionary(ByteBuffer)` cũng được hỗ trợ từ Java 11, nhưng khác `setInput(ByteBuffer)` ở chỗ nó **tiêu thụ hết dictionary ngay khi gọi**, nên sau lời gọi `dictionary.position() == dictionary.limit()`. Chỉ dùng dictionary đã được protocol cung cấp/định nghĩa đúng; không đoán dictionary từ dữ liệu nhận được hoặc bỏ qua trạng thái `needsDictionary`.

Nếu bộ giải nén không dùng preset dictionary, không cần thêm `setDictionary` theo thói quen.

## 9. Lỗi, định dạng và quản lý tài nguyên

### `DataFormatException`: dữ liệu nén sai không được xem là kết quả thành công

```java
try {
    int count = inflater.inflate(output);
    // Chỉ xử lý count byte nếu thành công và đúng chính sách giao thức.
} catch (DataFormatException ex) {
    // Luồng nén không hợp lệ hoặc không khớp định dạng.
    // Không sử dụng kết quả giải nén dở dang như một payload đã xác thực.
    throw ex;
}
```

Theo hợp đồng API, input/output position và tổng byte có thể đã tiến sau khi một lỗi dữ liệu xảy ra. Nếu cần ghi log, lấy các mốc hiện tại và context parser; **không rollback bằng cách tự giảm position** hoặc gọi inflate tiếp như thể dữ liệu vẫn hợp lệ. Bộ giải nén có trạng thái và nội dung nén có thể đã không nhất quán. Kết thúc lỗi và hủy frame hoặc áp dụng chiến lược khôi phục được protocol định nghĩa rõ.

### Chọn đúng container zlib, raw DEFLATE hay GZIP

| Dữ liệu đang có | Cách xử lý thông thường |
| --- | --- |
| Một luồng **zlib** có header/checksum | `new Inflater()`; thường khớp với `new Deflater()`/`DeflaterOutputStream` mặc định |
| **Raw DEFLATE** không có zlib wrapper | `new Inflater(true)` nếu định dạng quy định; chú ý đặc thù native zlib với tùy chọn `nowrap` |
| Một file hoặc member **GZIP** đầy đủ | `GZIPInputStream` hoặc parser GZIP tương ứng |
| Một file **ZIP** có entry, metadata, header | `ZipInputStream`/`ZipFile` hoặc parser ZIP phù hợp |

**`new Inflater(true)` không có nghĩa tự động hiểu toàn bộ container GZIP/ZIP.** Nó giải nén raw DEFLATE; header/trailer và metadata của container cần được xử lý riêng. Đọc toàn bộ bytes `.gz` rồi cấp thẳng vào `new Inflater()` thường dẫn đến `DataFormatException` vì wrapper không đúng.

### `end()` và tái sử dụng `reset()`

`Inflater` sử dụng tài nguyên của bộ giải nén và cần `end()` khi xong:

```java
Inflater inflater = new Inflater();
try {
    // setInput(...), inflate(...), kiểm tra finished()...
} finally {
    inflater.end();
}
```

Nếu muốn tái sử dụng đối tượng cho một **luồng nén độc lập khác**, gọi `reset()` để đặt lại trạng thái trước khi cung cấp dữ liệu mới. Không tự `reset()` ở giữa một stream còn chưa hoàn tất: làm vậy bỏ mất trạng thái cần thiết để giải nén tiếp. Khi đã gọi `end()`, không tiếp tục dùng đối tượng ấy.

Không chia sẻ một instance `Inflater` cho nhiều thread thao tác đồng thời. Ngoài vấn đề trạng thái nội bộ, tài liệu `setInput(ByteBuffer)` quy định thay đổi contents/position/limit của buffer **đồng thời với `inflate`** là hành vi không xác định, có thể cho kết quả sai hoặc thất bại.

## 10. Độ an toàn bộ nhớ và tính đúng đắn khi xử lý dữ liệu không tin cậy

Dữ liệu DEFLATE có thể bung thành số byte lớn hơn rất nhiều kích thước nén. Ngay cả khi gọi `inflate(ByteBuffer)` từng lượt nhỏ, nếu cứ cộng kết quả vào `ByteArrayOutputStream` không giới hạn thì vẫn có thể hết bộ nhớ.

Để xử lý an toàn:

1. Áp dụng giới hạn **tổng byte giải nén** trước khi lưu/ghi thêm đầu ra. Nếu có header khai báo kích thước giải nén, xác thực nó và vẫn kiểm tra kích thước thực trong quá trình xử lý.
2. Giới hạn tổng byte nén đầu vào, tỷ lệ nở, thời gian xử lý và số frame tùy nguồn dữ liệu; không tin tưởng tuyệt đối thông tin kích thước do peer gửi.
3. Phân biệt **luồng nén hoàn chỉnh** (`finished()`) với **byte đầu ra tạm thời** (`inflate` sinh `n` byte). Dữ liệu chưa hoàn tất/không qua checksum không nên được coi là payload đã xác thực.
4. Không lấy `output.capacity()` làm số byte thực ghi; dùng giá trị trả về `inflate` và `output.position()`.
5. Giữ lại byte đầu vào chưa tiêu thụ cho phần tiếp theo của giao thức; kiểm tra `getRemaining()` và `input.remaining()` trước khi giải phóng hoặc tái sử dụng buffer.
6. Chỉ mutate `ByteBuffer` giữa các lời gọi inflate theo quy tắc quản lý dữ liệu; không thay đổi đồng thời.
7. Bảo đảm mỗi stream nén có vòng đời đúng: `finished`/lỗi, `reset` khi cần một stream mới, `end` khi kết thúc tài nguyên.

**Ví dụ giới hạn output** trong quá trình ghi:

```java
int allowed = 1_000_000; // Giới hạn minh họa, phải phù hợp nghiệp vụ
int alreadyWritten = result.size();
int justProduced = produced;

if (justProduced > allowed - alreadyWritten) {
    throw new IOException("Decompressed payload exceeds limit");
}
```

Bài toán an toàn không kết thúc ở việc dùng direct buffer; direct buffer có thể giảm một số thao tác copy giữa heap/native trong những hệ thống nhất định, nhưng không tự kiểm soát khối lượng dữ liệu, kiểm chứng CRC/Adler hay chống payload nén độc hại.

## 11. Các lỗi hay gặp liên quan đến position

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `inflate(output)` ghi vào vị trí sai | Output `position` chưa được thiết lập đúng trước khi ghi | Kiểm tra `position/limit`, dùng `clear`/`compact` theo chính sách quản lý dữ liệu |
| Lấy dữ liệu từ output thấy 0 byte | Chưa `flip()` trước khi đọc hoặc đã `clear()` làm mất mốc dữ liệu | `inflate -> flip -> đọc -> clear` |
| Có byte nén nhưng `needsInput()` đúng | Chunk đã cấp bị tiêu thụ hết; còn byte ở nguồn khác | Cấp chunk mới bằng `setInput`, không chờ buffer tự nạp |
| Lặp vô hạn khi `inflate` trả 0 | Không xét `finished`/`needsInput`/`needsDictionary` hoặc output đầy | Kiểm tra trạng thái và tiến độ, tạo output trống/cấp input đúng |
| Đọc tràn sang frame kế tiếp | Không giữ `input.remaining()` sau khi `finished` | Dùng các byte dư cho parser tầng ngoài |
| Input từ channel không giải nén | Buffer còn ở write mode, `position` sau dữ liệu và `limit=capacity` | Gọi `flip()` trước `setInput` |
| Mất byte chưa đọc sau khi `clear()` input | Dùng lại vùng chứa khi vẫn có dữ liệu chưa tiêu thụ | Chỉ refill khi thích hợp; bảo toàn phần dư bằng `compact`/slice/ownership rõ ràng |
| Dùng `slice()` nhưng buffer gốc không tăng vị trí | Slice có position riêng | Theo dõi `slice.position()` và tự cập nhật parser gốc khi cần |
| Cấp sai byte nén vào `Inflater` | Nhầm zlib/raw DEFLATE/GZIP/ZIP | Chọn đúng wrapper/API theo định dạng |
| Kết quả giải nén có đủ byte nhưng `finished=false` | Luồng nén thiếu phần kết thúc/checksum hoặc cần input thêm | Không chấp nhận payload; đọc tiếp hoặc báo truncated stream |
| `ReadOnlyBufferException` | Output `ByteBuffer` không cho ghi | Cấp buffer writable; input read-only vẫn có thể hợp lệ |
| `DataFormatException` và position đã thay đổi | Trạng thái cập nhật trước khi phát hiện dữ liệu sai | Hủy/khôi phục frame theo protocol; không giả định transaction rollback |
| Nhiều bộ nhớ dù dùng buffer nhỏ | Kết quả được tích lũy không giới hạn | Áp dụng output cap, streaming sink và giới hạn tài nguyên |

## 12. Tự kiểm tra (kèm đáp án)

**Câu 1.** `input.position()` ban đầu là 7, sau `inflater.inflate(output)` thành 12, trong khi hàm trả `produced=30`. Điều này có sai không?

**Đáp án:** Không. Inflater đã tiêu thụ 5 byte **nén** và sinh 30 byte **giải nén**. Hai con số đo các miền dữ liệu khác nhau.

**Câu 2.** `inflate(ByteBuffer)` thành công và trả `17`. Nếu `output.position()` ban đầu là 3, sau lời gọi hợp lệ nó bằng bao nhiêu?

**Đáp án:** **20**, miễn còn đủ chỗ trống để sinh 17 byte; API tăng output position đúng bằng số byte thực ghi.

**Câu 3.** Có thể gọi `output.clear()` ngay khi `inflate(output)` trả 5 để chuẩn bị lượt tiếp không?

**Đáp án:** Chỉ khi 5 byte vừa sinh **đã được tiêu thụ hoặc chuyển đi**. Nếu chưa, clear đặt lại marker và lượt inflate mới có thể ghi đè dữ liệu cũ.

**Câu 4.** `inflater.needsInput() == true` thì chắc chắn stream nén đã hoàn tất chưa?

**Đáp án:** **Chưa.** Cần kiểm tra `finished()`. Nếu nguồn thật sự EOF nhưng chưa finished, luồng nén bị cắt cụt/không hoàn chỉnh.

**Câu 5.** Với `ByteBuffer.wrap(data, 5, 3)`, `position` và `limit` ban đầu là bao nhiêu?

**Đáp án:** `position=5`, `limit=8`, `remaining=3`. Muốn view có position 0, dùng `slice()` trên vùng phù hợp.

**Câu 6.** Khi Inflater đã giải nén xong và `getRemaining() == 2`, hai byte còn lại có bị mất không?

**Đáp án:** Chưa. Chúng là byte chưa tiêu thụ trong buffer đầu vào hiện tại; với `setInput(ByteBuffer)`, position phản ánh phần đã tiêu thụ, nên caller có thể truy cập phần còn lại để xử lý trailer/frame tiếp theo theo protocol.

**Câu 7.** Buffer input là `asReadOnlyBuffer()`; output là `ByteBuffer.allocateDirect(1024)`. Có được không?

**Đáp án:** Có. Inflater chỉ đọc từ input nên input read-only hợp lệ; output direct vẫn writable. Nếu output là read-only, `inflate(ByteBuffer)` sẽ ném `ReadOnlyBufferException`.

**Câu 8.** `inflate(output)` ném `DataFormatException`. Có chắc `input.position()` và `output.position()` chưa đổi?

**Đáp án:** Không. Theo Javadoc, các vị trí có thể đã tiến theo byte được tiêu thụ/sinh trước khi lỗi xảy ra. Không được giả định rollback.

**Câu 9.** Một stream zlib bị thiếu hai byte checksum cuối, nhưng đã giải nén đủ số byte nội dung được dự đoán. Có được coi là thành công không?

**Đáp án:** Không. Phải xác nhận `finished()`; thiếu phần kết thúc hợp lệ có thể khiến `finished=false` dù số byte đầu ra đã đủ.

**Câu 10.** `new Inflater(true)` có tự giải mã mọi file `.gz` không?

**Đáp án:** Không. Chế độ `nowrap=true` nhắm tới raw DEFLATE; GZIP có thêm header/trailer và metadata riêng. Dùng `GZIPInputStream` hoặc parser phù hợp cho GZIP đầy đủ.

## Tài liệu chuẩn còn áp dụng

- [Oracle Java SE 11 — Inflater](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/Inflater.html): `setInput(ByteBuffer)`, `inflate(ByteBuffer)`, cách cập nhật position, `needsInput`, `finished`, `needsDictionary`, `getRemaining`, `end`.
- [Oracle Java SE 25 — Inflater](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/zip/Inflater.html): xác nhận các overload `ByteBuffer` và quy tắc position tiếp tục được hỗ trợ.
- [Oracle Java SE 11 — ByteBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `remaining`, `flip`, `clear`, `compact`, `slice` và `duplicate`.
- [Oracle Java SE 11 — DeflaterOutputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/DeflaterOutputStream.html): tạo luồng zlib/DEFLATE nén trong ví dụ.
- [Oracle Java SE 11 — DataFormatException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/DataFormatException.html): báo lỗi định dạng dữ liệu nén.
- [Oracle Java SE 11 — GZIPInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/GZIPInputStream.html): đọc GZIP với wrapper/header/trailer phù hợp.

**Ghi nhớ:** Khi truyền `ByteBuffer` cho `Inflater`, **input position đếm byte nén đã tiêu thụ; output position đếm byte đã giải nén được ghi**. Dùng `flip/clear` đúng chu kỳ, chỉ cấp thêm input khi cần, xử lý dữ liệu dư và xác nhận `finished()` trước khi tin rằng luồng nén hợp lệ.
# Thực hành: Thiết kế định dạng nhị phân có version và length trong Java

## 1. Bài toán và mục tiêu

Giả sử ứng dụng Java cần lưu hàng nghìn bản ghi vào một tệp nhị phân hoặc truyền chúng liên tiếp qua TCP. Mỗi bản ghi có mã định danh và tên; ở phiên bản mới, bản ghi có thêm độ ưu tiên. Ta cần một định dạng mà chương trình có thể:

- Xác định **ranh giới** của từng bản ghi mà không phải đoán byte kết thúc.
- Biết **phiên bản cấu trúc** để giải mã đúng trường dữ liệu.
- Đọc tuần tự nhiều bản ghi trong cùng file/luồng TCP.
- Phát hiện đầu vào không hợp lệ, bị cắt cụt hoặc có checksum sai.
- Giới hạn kích thước trước khi cấp phát bộ nhớ.
- Có chính sách rõ ràng khi gặp bản ghi thuộc phiên bản chưa được hỗ trợ.
- Chạy được giữa các tiến trình/JDK mà không lệ thuộc serialization mặc định của class Java.

Đây là vấn đề **binary protocol design** và **record framing**. Không nên đơn giản ghi một loạt số nguyên/chuỗi rồi kỳ vọng bên đọc tự biết lúc nào bản ghi kết thúc.

~~~text
Tệp nhị phân hoặc luồng TCP
  |
  +-- [HEADER record 1][PAYLOAD 1][CHECKSUM 1]
  +-- [HEADER record 2][PAYLOAD 2][CHECKSUM 2]
  +-- [HEADER record 3][PAYLOAD 3][CHECKSUM 3]
                 |
                 v
        Parser theo từng frame
                 |
       validate -> decode theo version
~~~

**Cặp version + length giải quyết hai câu hỏi khác nhau:**

- **Version:** byte bên trong payload phải được diễn giải theo cấu trúc nào?
- **Length:** byte của frame hiện tại kết thúc ở đâu và frame kế tiếp bắt đầu tại vị trí nào?

Version không thay thế length, và length không tự nói cho decoder biết dữ liệu bên trong có cấu trúc gì.

## 2. Trước tiên hãy viết đặc tả định dạng byte

Một giao thức tốt không chỉ có code Java. Nó cần mô tả chính xác **thứ tự trường, độ dài, byte order, encoding, giới hạn và điều kiện lỗi**. Ta chọn một định dạng minh họa tên `JBIN`:

| Offset trong frame | Độ dài | Trường | Quy tắc |
| ---: | ---: | --- | --- |
| 0 | 4 byte | `magic` | ASCII `JBIN`, tương đương hex `4A 42 49 4E` |
| 4 | 1 byte | `version` | Số nguyên không dấu 0–255; hỗ trợ version 1 và 2 |
| 5 | 4 byte | `payloadLength` | Số nguyên signed 32-bit, **big-endian**, chỉ chấp nhận 0 tới 65.536 |
| 9 | `payloadLength` byte | `payload` | Cấu trúc theo version |
| 9 + length | 4 byte | `crc32` | Giá trị CRC-32 **chỉ của payload**, ghi thành 32-bit big-endian |

Tổng độ dài một frame:

\[
\mathrm{frameBytes} = 4 + 1 + 4 + \mathrm{payloadLength} + 4
= 13 + \mathrm{payloadLength}.
\]

Sơ đồ byte:

~~~text
      4B       1B          4B                 L bytes         4B
+-----------+---------+--------------+-----------------------+----------+
|   JBIN    | version | payloadLength|       payload         |  CRC32   |
+-----------+---------+--------------+-----------------------+----------+
  magic       u8          i32 BE        bytes theo version      u32 BE

Frame 1 | Frame 2 | Frame 3 | ... | EOF tại ranh giới frame
~~~

Đây là **định dạng tự thiết kế để thực hành**, không phải tiêu chuẩn JDK. Hai chương trình khác ngôn ngữ vẫn có thể trao đổi dữ liệu nếu tuân thủ cùng đặc tả.

### Vì sao cần magic?

Magic giúp phát hiện sớm đầu vào không đúng định dạng. Nếu bốn byte đầu không bằng `JBIN`, parser từ chối trước khi diễn giải length hoặc payload.

Magic **không phải chứng thực bảo mật** và không bảo đảm tự động tìm lại ranh giới khi file hỏng. Việc quét tùy tiện để tìm chuỗi `JBIN` trong payload có thể nhận nhầm byte dữ liệu là header thật. Khi cần khả năng phục hồi, hãy xây cơ chế resynchronization/commit/index có quy tắc rõ ràng.

### Vì sao dùng length dạng số nguyên cố định?

Length-prefix cho phép xác định frame tiếp theo mà không cần ký tự phân cách. Điều đó quan trọng với payload nhị phân, nơi mọi giá trị byte từ 0 tới 255 đều có thể hợp lệ.

Nhưng đừng tin giá trị length đến từ file hoặc mạng. Bốn byte có thể được diễn giải thành một số âm hoặc hàng tỷ byte. **Kiểm tra giới hạn trước khi tạo `new byte[length]`.**

Ở bài này giới hạn bài tập là 65.536 byte cho **mỗi payload**, không phải tổng kích thước file. Production cần một mức tối đa phù hợp với nghiệp vụ, bộ nhớ và số connection đồng thời.

## 3. Thiết kế payload theo version

Chọn hai phiên bản khác nhau có chủ đích:

### Version 1

~~~text
+------------+----------------+-----------------------+
| id: i32 BE | nameLen: u16 BE| nameUtf8: nameLen B   |
+------------+----------------+-----------------------+
     4B             2B             0..65535 B
~~~

Ví dụ một message có `id=7` và `name="Alpha"`. Tên được mã hóa **UTF-8**, còn `nameLen` là **số byte UTF-8**, không phải `String.length()`.

### Version 2

Giữ nguyên các trường v1 và **thêm cuối payload** một số nguyên `priority`:

~~~text
+------------+----------------+----------------------+------------------+
| id: i32 BE | nameLen: u16 BE| nameUtf8: nameLen B | priority: i32 BE |
+------------+----------------+----------------------+------------------+
     4B             2B            n bytes                4B
~~~

Với version 2, decoder phải đọc thêm đúng bốn byte priority. Nếu không có đủ bốn byte, frame không hợp lệ. Nếu decoder gặp byte dư không được đặc tả, **không tự im lặng bỏ qua** đối với version đã biết: có thể đã encode sai schema hoặc parser bị lệch.

### Version chưa hỗ trợ

Nếu reader hiện hỗ trợ version 1 và 2 nhưng bắt gặp version 99:

- Nó **vẫn đọc và giới hạn length** theo header chung.
- Nó **đọc và kiểm tra toàn bộ frame** theo những quy tắc chung mà nó hiểu.
- Nó **không tự đoán** cấu trúc payload version 99.
- Nó có thể **bỏ qua frame nguyên vẹn** rồi đọc frame kế tiếp, nếu chính sách giao thức cho phép; hoặc **từ chối toàn bộ file/kết nối** nếu mọi message đều bắt buộc phải hiểu.

Hai chính sách đều có thể đúng. Việc skip chỉ hợp lệ khi mỗi frame được đóng gói độc lập và không mang trạng thái làm thay đổi ý nghĩa frame sau. Nếu version mới thay đổi **cấu trúc header chung**, reader cũ có thể không skip được; khi đó cần protocol negotiation hoặc file-format major version ở cấp container.

## 4. Byte order: Java phải ghi và đọc nhất quán

Với số nguyên nhiều byte, thứ tự byte (*endianness*) phải được đặc tả. Ta chọn **big-endian**:

~~~text
Số int 0x01020304
Big-endian:    01 02 03 04
Little-endian: 04 03 02 01
~~~

`DataOutputStream.writeInt()` và `DataInputStream.readInt()` dùng thứ tự **big-endian**. `writeShort/readUnsignedShort` cũng trao đổi theo thứ tự byte từ cao xuống thấp.

`ByteBuffer` mặc định là big-endian nhưng có thể đổi bằng `order(ByteOrder.LITTLE_ENDIAN)`; đừng giả định ByteBuffer được truyền từ code khác vẫn giữ byte order mặc định. Nếu triển khai cùng định dạng bằng `ByteBuffer`, nên khai báo `buffer.order(ByteOrder.BIG_ENDIAN)` có chủ đích.

Một reader C/Python/Go phải tuân thủ cùng endianness. Không ghi cấu trúc `struct` native tùy ý rồi coi padding/alignment của C giống Java.

### Unsigned và signed

- Version: 1 byte không dấu, Java dùng `readUnsignedByte()` để nhận 0..255.
- `nameLen`: 2 byte không dấu, Java dùng `readUnsignedShort()` để nhận 0..65.535.
- `payloadLength`: 4 byte signed. Ta quy định **0..65.536 hợp lệ**, âm hoặc vượt trần là lỗi.
- CRC32: 32-bit bit pattern, được ghi bằng `writeInt((int) crc.getValue())` và so sánh theo bit pattern khi đọc.

Java `byte` là signed; nếu cần in hex của một byte, dùng `value & 0xFF` để tránh sign extension.

## 5. UTF-8 và các bẫy độ dài chuỗi

Ví dụ chuỗi `"A"` dài 1 ký tự UTF-16, có 1 byte UTF-8. Chuỗi `"Đ"` dài 1 UTF-16 code unit nhưng có **2 byte UTF-8**; các ký tự ngoài BMP có thể cần 4 byte UTF-8 và 2 UTF-16 code unit.

Do đó, không làm thế này:

~~~java
out.writeShort(name.length()); // SAI nếu độ dài phải tính theo byte UTF-8
out.write(name.getBytes(StandardCharsets.UTF_8));
~~~

Mảnh code trên minh họa lỗi. Cách đúng:

~~~java
byte[] encodedName = name.getBytes(StandardCharsets.UTF_8);
if (encodedName.length > 65535) {
    throw new IOException("Name too long");
}
out.writeShort(encodedName.length);
out.write(encodedName);
~~~

`writeShort` ghi 16 bit thấp; **nó không tự từ chối** tên dài hơn 65.535 byte theo ý định giao thức, vì vậy phải kiểm tra trước.

Không dùng `DataOutputStream.writeUTF()` như thay thế tùy tiện cho định dạng vừa thiết kế. Phương thức đó dùng **modified UTF-8** với framing riêng của Java và các giới hạn riêng; nó không tương đương “u16 length + UTF-8 chuẩn” của đặc tả này. Để tương thích đa ngôn ngữ, hãy tự ghi byte UTF-8 chuẩn kèm độ dài rõ ràng.

Decoder cũng cần chính sách cho UTF-8 lỗi. `new String(bytes, UTF_8)` có thể thay byte không hợp lệ bằng ký tự thay thế; nếu giao thức yêu cầu **từ chối dữ liệu UTF-8 hỏng**, dùng `CharsetDecoder` với `CodingErrorAction.REPORT`.

## 6. Vì sao cần checksum? CRC32 kiểm tra được gì?

Ta thêm CRC-32 để phát hiện **nhiều dạng hỏng byte ngẫu nhiên** trong payload, ví dụ lỗi lưu trữ/truyền dữ liệu. CRC32 không phải encryption, không có key bí mật và **không chống giả mạo có chủ đích**: một kẻ tấn công có thể sửa payload rồi tính lại CRC.

Ví dụ:

~~~text
Payload gốc         → CRC32 0x12345678 (giá trị minh họa)
Một byte bị thay đổi → CRC32 tính lại thường khác
Reader so sánh CRC được lưu với CRC tính lại → báo lỗi
~~~

Ở định dạng bài tập này, CRC **chỉ bảo vệ payload**, không bảo vệ magic/version/length. Parser vẫn kiểm tra header hợp lệ và giới hạn length, nhưng nếu nghiệp vụ đòi phát hiện header bị sửa hoặc xác thực nguồn dữ liệu, cần bổ sung checksum bao phủ trường thích hợp hoặc sử dụng cơ chế xác thực mật mã như MAC/AEAD.

Đối với frame rất lớn, có thể tính CRC khi streaming từng chunk mà không giữ toàn bộ payload trong RAM. Trong ví dụ dưới, vì `MAX_PAYLOAD` chỉ 65.536 byte, việc giữ payload từng frame trong một mảng là hợp lý để minh họa.

## 7. Chương trình Java 17+ hoàn chỉnh: ghi và đọc ba frame

Ví dụ dưới đây tự xây serializer/deserializer với `DataOutputStream` và `DataInputStream`. Nó ghi ba frame vào một luồng byte:

1. Version 1 chứa `id=7`, `name="Alpha"`.
2. Version 99 là một frame **không hiểu payload**, nhưng có header/length/CRC hợp lệ, để thử chính sách skip.
3. Version 2 chứa `id=8`, `name="Beta"`, `priority=42`.

Sau đó chương trình cố ý cắt cụt một frame và sửa một byte payload để kiểm tra hai dạng lỗi. Mọi test dùng mảng byte trong RAM để stdout không phụ thuộc filesystem hay thời gian.

Lưu thành `VersionedBinaryFormatDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.CRC32;

public class VersionedBinaryFormatDemo {

    private static final int MAGIC = 0x4A42494E; // ASCII "JBIN"
    private static final int MAX_PAYLOAD = 65_536;

    record Frame(int version, byte[] payload) {}

    record Message(int id, String name, Integer priority) {}

    static byte[] encodeMessage(
            int version, int id, String name, Integer priority)
            throws IOException {

        if (version != 1 && version != 2) {
            throw new IllegalArgumentException("Unsupported writer version");
        }
        if (version == 2 && priority == null) {
            throw new IllegalArgumentException("V2 needs priority");
        }

        byte[] nameBytes = name.getBytes(StandardCharsets.UTF_8);
        if (nameBytes.length > 65_535) {
            throw new IOException("Name length exceeds u16");
        }

        ByteArrayOutputStream raw = new ByteArrayOutputStream();
        try (DataOutputStream payload = new DataOutputStream(raw)) {
            payload.writeInt(id);
            payload.writeShort(nameBytes.length);
            payload.write(nameBytes);
            if (version == 2) {
                payload.writeInt(priority);
            }
        }

        byte[] result = raw.toByteArray();
        if (result.length > MAX_PAYLOAD) {
            throw new IOException("Payload exceeds maximum");
        }
        return result;
    }

    static void writeFrame(
            DataOutputStream out, int version, byte[] payload)
            throws IOException {

        if (version < 0 || version > 255
                || payload.length > MAX_PAYLOAD) {
            throw new IOException("Invalid version or payload size");
        }

        CRC32 crc = new CRC32();
        crc.update(payload);

        out.writeInt(MAGIC);
        out.writeByte(version);
        out.writeInt(payload.length);
        out.write(payload);
        out.writeInt((int) crc.getValue());
    }

    static Frame readFrame(DataInputStream in) throws IOException {
        // EOF hợp lệ CHỈ khi chưa đọc byte nào của header kế tiếp.
        int first = in.read();
        if (first == -1) {
            return null;
        }

        int magic = (first << 24)
                | (in.readUnsignedByte() << 16)
                | (in.readUnsignedByte() << 8)
                | in.readUnsignedByte();
        if (magic != MAGIC) {
            throw new IOException("Invalid magic");
        }

        int version = in.readUnsignedByte();
        int length = in.readInt();

        if (length < 0 || length > MAX_PAYLOAD) {
            throw new IOException("Invalid payload length");
        }

        byte[] payload = new byte[length];
        in.readFully(payload); // EOF giữa payload => EOFException.

        int storedCrc = in.readInt(); // EOF giữa trailer => EOFException.
        CRC32 calculated = new CRC32();
        calculated.update(payload);

        if ((int) calculated.getValue() != storedCrc) {
            throw new IOException("CRC32 mismatch");
        }
        return new Frame(version, payload);
    }

    static Message decodeMessage(Frame frame) throws IOException {
        if (frame.version() != 1 && frame.version() != 2) {
            throw new IOException("Unknown message schema");
        }

        try (DataInputStream payload = new DataInputStream(
                new ByteArrayInputStream(frame.payload()))) {

            int id = payload.readInt();
            int nameLength = payload.readUnsignedShort();
            int extraBytes = frame.version() == 2 ? 4 : 0;

            if (nameLength > payload.available() - extraBytes) {
                throw new IOException("Invalid name length");
            }

            byte[] nameBytes = new byte[nameLength];
            payload.readFully(nameBytes);

            String name = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(nameBytes)).toString();

            Integer priority =
                    frame.version() == 2 ? payload.readInt() : null;

            if (payload.available() != 0) {
                throw new IOException("Unexpected trailing payload bytes");
            }

            return new Message(id, name, priority);
        }
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(destination)) {
            writeFrame(out, 1,
                    encodeMessage(1, 7, "Alpha", null));
            writeFrame(out, 99, new byte[] {1, 2, 3});
            writeFrame(out, 2,
                    encodeMessage(2, 8, "Beta", 42));
        }

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(destination.toByteArray()))) {
            Frame frame;
            while ((frame = readFrame(in)) != null) {
                if (frame.version() != 1 && frame.version() != 2) {
                    System.out.println(
                            "unknown version=" + frame.version()
                                    + " skipped");
                    continue;
                }

                Message message = decodeMessage(frame);
                String priority = message.priority() == null
                        ? "n/a"
                        : message.priority().toString();

                System.out.println("v" + frame.version()
                        + ": id=" + message.id()
                        + " name=" + message.name()
                        + " priority=" + priority);
            }
        }

        ByteArrayOutputStream one = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(one)) {
            writeFrame(out, 1,
                    encodeMessage(1, 1, "Test", null));
        }

        byte[] original = one.toByteArray();

        // Giả lập file bị cắt mất hai byte ở cuối CRC.
        byte[] truncated = Arrays.copyOf(
                original, original.length - 2);
        boolean truncationDetected = false;
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(truncated))) {
            readFrame(in);
        } catch (EOFException expected) {
            truncationDetected = true;
        }
        System.out.println(
                "truncated detected=" + truncationDetected);

        // Header dài 9 byte; byte đầu của payload ở offset 9.
        byte[] corrupted = original.clone();
        corrupted[9] ^= 1;
        boolean crcDetected = false;
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(corrupted))) {
            readFrame(in);
        } catch (IOException ex) {
            crcDetected = "CRC32 mismatch".equals(ex.getMessage());
        }
        System.out.println("crc mismatch detected=" + crcDetected);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac VersionedBinaryFormatDemo.java
java VersionedBinaryFormatDemo
~~~

Stdout:

~~~text
v1: id=7 name=Alpha priority=n/a
unknown version=99 skipped
v2: id=8 name=Beta priority=42
truncated detected=true
crc mismatch detected=true
~~~

### Phân tích chương trình theo từng giai đoạn

**Bước 1 — Ghi payload:** `encodeMessage` tạo một byte array theo schema v1/v2: `id`, `nameLen` và byte UTF-8, thêm `priority` nếu là v2. Hàm kiểm tra `nameLen` và tổng payload không vượt giới hạn.

**Bước 2 — Ghi frame:** `writeFrame` ghi magic, version, length, payload và CRC32. `DataOutputStream` quy định big-endian cho số nguyên nhiều byte. Một lời gọi tương ứng một frame có ranh giới rõ ràng.

**Bước 3 — Đọc header:** `readFrame` cho phép trả `null` **chỉ khi EOF ở đúng đầu frame tiếp theo**. Nếu chỉ còn 1–3 byte của magic hoặc thiếu version/length, các lệnh `readUnsignedByte`/`readInt` ném `EOFException`; đó là dữ liệu cắt cụt, không phải kết thúc hợp lệ.

**Bước 4 — Bảo vệ cấp phát:** `length < 0` hoặc `length > MAX_PAYLOAD` bị từ chối **trước** `new byte[length]`. Parser không tin một length do đối tác cung cấp.

**Bước 5 — Đọc payload và CRC:** `readFully` buộc đọc đủ đúng `length` byte; `readInt` buộc có đủ trailer. CRC32 tính lại khác checksum lưu sẽ ném `IOException`.

**Bước 6 — Phân nhánh theo version:** `decodeMessage` chỉ hiểu v1/v2. Version 99 đã được đọc trọn frame và kiểm tra CRC nên có thể bỏ qua như một đơn vị độc lập; v2 tiếp theo vẫn đọc đúng.

**Bước 7 — Kiểm tra schema bên trong payload:** Decoder dùng `readUnsignedShort` để nhận name length, kiểm tra còn đủ byte cho name **và trường priority nếu là v2**, giải mã UTF-8 strict, sau đó yêu cầu không còn byte dư.

**Bước 8 — Test sai dữ liệu:** Trường hợp cắt mất hai byte cuối CRC sinh `EOFException`. Trường hợp sửa một byte payload nhưng giữ nguyên trailer CRC sinh `IOException` có thông báo `CRC32 mismatch`. Không có dựa vào network timing hoặc thứ tự thread.

Ví dụ đã cố tình sử dụng `ByteArrayInputStream` để tái lập kết quả. Khi chuyển sang file hoặc socket thật, logic framing giữ nguyên, còn việc đệm, xử lý I/O và lifecycle phải thích ứng với nguồn.

## 8. Những quyết định thiết kế nên chốt trước khi triển khai

### Header cấp file hay header mỗi record?

Hai mô hình có thể được chọn:

**Mô hình A — header một lần cho cả file:**

~~~text
[FILE_MAGIC][FILE_FORMAT_VERSION]
[RECORD_LENGTH][RECORD]
[RECORD_LENGTH][RECORD]
...
~~~

Phù hợp khi toàn file luôn có cùng schema/định dạng hoặc khi ứng dụng muốn negotiate một phiên bản file trước khi đọc nội dung. Reader phải biết liệu mỗi record có cùng version hay có type/version riêng.

**Mô hình B — header mỗi frame**, như bài thực hành:

~~~text
[MAGIC][VERSION][LENGTH][PAYLOAD][CRC]
[MAGIC][VERSION][LENGTH][PAYLOAD][CRC]
...
~~~

Phù hợp khi cần trộn các version record hoặc nối frame độc lập. Đổi lại, overhead header và CRC lặp lại trên mỗi record.

Không có lựa chọn duy nhất đúng cho mọi ứng dụng. Điều quan trọng là **đặc tả nhất quán** và tính độc lập của từng frame nếu muốn skip những phiên bản không hiểu.

### Version cấp giao thức hay version cấp payload?

Một **protocol major version** có thể mô tả cú pháp header chung; một **payload schema version** mô tả trường bên trong một loại message. Trong ví dụ chúng cùng biểu diễn bằng một byte `version` vì định dạng đơn giản.

Nếu sau này muốn đổi cả cấu trúc frame (ví dụ length từ 32-bit thành 64-bit), reader cũ không nhất thiết còn nhận ra ranh giới. Hãy xem đó là **thay đổi giao thức lớn**, không chỉ tăng version payload từ 2 lên 3.

### Type và flags có cần không?

Nếu file chứa nhiều loại record, có thể mở rộng header thành:

~~~text
[MAGIC][FORMAT_VERSION][RECORD_TYPE][FLAGS][PAYLOAD_LENGTH][PAYLOAD][CRC]
~~~

Khi đó đặc tả phải bổ sung:

- Các giá trị type/flag hợp lệ.
- Unknown type/flag có được skip không.
- Những flag bắt buộc người đọc hiểu để giải mã đúng payload.
- Quy tắc dành riêng bit tương lai và thứ tự xử lý compression/encryption.
- Kích thước tối đa sau giải nén nếu payload được nén.

Không thêm type/flag một cách tùy tiện mà quên cập nhật parser và test tương thích.

## 9. DataInputStream so với ByteBuffer/FileChannel

Java cung cấp nhiều mức trừu tượng:

| Công cụ | Hữu ích khi nào? | Điểm cần chú ý |
| --- | --- | --- |
| `DataOutputStream` / `DataInputStream` | Ghi/đọc primitive trên OutputStream/InputStream | Big-endian; `readFully` phù hợp với frame length |
| `ByteBuffer` | Đóng/gỡ byte từ mảng/direct buffer | Phải quản lý `position/limit/flip` và byte order |
| `FileChannel` | Random access, đọc/ghi theo offset cho file lớn | `read`/`write` có thể chuyển một phần; phải kiểm tra vòng lặp |
| `SocketChannel` non-blocking | Giao thức mạng với Selector | Có thể trả 0 byte; state machine phải tích lũy header/payload qua nhiều lượt |
| `BufferedInputStream` | Giảm lần gọi I/O nhỏ khi đọc stream | Không làm thay đổi protocol framing |
| `CRC32` | Phát hiện nhiều dạng lỗi byte ngẫu nhiên | Không xác thực/chống giả mạo |

Trong demo, `DataInputStream` rất phù hợp vì `readFully` đợi/đọc đủ số byte yêu cầu hoặc ném EOF. Với non-blocking `SocketChannel`, không được giả định một lần `read(buffer)` sẽ trả đủ 9 byte header hay đủ payload. Cần một **state machine**:

~~~text
NEED_HEADER
    |
    | nhận đủ 9 byte
    v
VALIDATE_LENGTH
    |
    | length hợp lệ, cấp bộ đệm có giới hạn
    v
NEED_PAYLOAD_AND_CRC
    |
    | nhận đủ length + 4 byte
    v
VERIFY_CRC
    |
    v
DECODE_OR_SKIP
    |
    v
NEED_HEADER (frame tiếp theo)
~~~

Một request TCP có thể bị chia thành nhiều packet, hoặc nhiều frame có thể đến trong một lần `read`. Giao thức dựa trên length làm rõ cách tích lũy, không phụ thuộc ranh giới packet.

## 10. File rất lớn: nên streaming theo frame

Một file có thể lớn hàng chục gigabyte nhưng mỗi frame chỉ dài vài kilobyte. Đừng dùng `Files.readAllBytes` để nạp cả file chỉ vì định dạng là nhị phân.

Với `InputStream`/`DataInputStream`, parser có thể đọc từng frame và xử lý ngay. Với `FileChannel`, có thể đọc vào buffer có giới hạn, giữ offset và phân tích incremental.

Quy tắc:

- **Giới hạn payload của mỗi frame**, tổng số frame và tổng byte xử lý theo yêu cầu.
- Đừng cấp phát `new byte[fileSize]`; xử lý từng frame.
- Bảo vệ số frame đồng thời khi nhiều client gửi.
- Không đưa các tham chiếu tới buffer có thể bị tái sử dụng vào job asynchronous mà không có ownership rõ ràng.
- Theo dõi bytes read, frames rejected và nguyên nhân lỗi để có thể vận hành.
- Khi frame lớn thật sự cần streaming, tính CRC incremental và dùng bounded input để không đọc lấn sang frame tiếp theo.

Trong ví dụ, ta dùng bộ đệm payload tối đa 65.536 byte, đủ nhỏ để minh họa độc lập mà không cần cơ chế xử lý hàng gigabyte.

## 11. Truncation, crash và giao thức append

Có một khác biệt quan trọng giữa **EOF hợp lệ** và **file bị cắt giữa record**:

~~~text
Hợp lệ:
[frame 1 hoàn chỉnh][frame 2 hoàn chỉnh][EOF]

Không hợp lệ:
[frame 1 hoàn chỉnh][nửa header frame 2][EOF]

Không hợp lệ:
[frame 1 hoàn chỉnh][header frame 2][nửa payload][EOF]
~~~

Vì vậy `readFrame` trả `null` chỉ khi **chưa đọc byte nào của frame kế tiếp**. Sau khi đã thấy bất kỳ byte header nào, thiếu dữ liệu còn lại phải là lỗi hoặc tình trạng cần đợi thêm byte nếu đang đọc mạng chưa đóng.

Nếu ứng dụng append record vào file và bị mất điện/JVM crash giữa một lần ghi, file có thể kết thúc bằng một frame chưa hoàn chỉnh. Những chiến lược production thường gặp:

1. Đọc các frame hoàn chỉnh từ đầu và ghi nhận **offset commit hợp lệ cuối cùng**.
2. Nếu phần cuối bị cắt, từ chối toàn file hoặc cô lập phần đuôi dở theo chính sách.
3. Với cấu trúc append-only log, có thể phục hồi bằng cách **truncate về offset cuối hợp lệ**, nhưng chỉ khi đã kiểm chứng độc lập, không có writer khác đang hoạt động và có cơ chế lưu trạng thái phù hợp.
4. Nếu cần durability, dùng `FileChannel.force(...)` theo chính sách và xem xét thứ tự ghi, metadata và filesystem.
5. Nếu cần cập nhật atomic cả file, cân nhắc ghi tệp tạm hoàn chỉnh rồi move/rename phù hợp trên cùng filesystem, với lưu ý khả năng `ATOMIC_MOVE` phụ thuộc provider.

**Một length-prefix không tự biến nhiều write thành giao dịch nguyên tử.** Nó giúp phát hiện record thiếu dữ liệu; khả năng phục hồi và durability là quyết định khác.

## 12. Khả năng tương thích: backward, forward và schema evolution

Có ba tình huống cần kiểm thử độc lập:

| Tình huống | Kỳ vọng nếu thiết kế hỗ trợ |
| --- | --- |
| Reader mới đọc record v1 | Đọc được bằng decoder v1 |
| Reader mới đọc record v2 | Đọc được bằng decoder v2 |
| Reader cũ gặp record v2/v99 | Skip an toàn nếu protocol cho phép; hoặc lỗi rõ ràng |

### Backward compatibility

Reader mới có thể hiểu các version cũ. Trong demo, decoder xử lý v1 và v2. Đó là **khả năng đọc dữ liệu cũ**, không đồng nghĩa mọi writer cũ sẽ hiểu dữ liệu do writer mới tạo.

### Forward compatibility

Reader cũ có thể chịu được các thay đổi mới trong phạm vi được đặc tả. Ví dụ parser đọc length, kiểm tra checksum, **skip unknown version** để tiếp tục frame sau. Nhưng nếu unknown frame thay đổi state, như thiết lập dictionary/encryption cho frame tiếp theo, skip có thể **không an toàn**.

### Migrations và defaults

Nếu cần đưa record v1 lên data model mới, một cách là chọn giá trị default hợp lý cho `priority` khi đọc v1, hoặc để `null` nghĩa là “chưa có”. **Không lấy 0 làm default mà không nói rõ semantics**, vì 0 có thể là một mức priority hợp lệ.

Tương tự, khi bỏ một field ở v3, nên viết rõ v1/v2/v3 là schema nào, không chỉ coi tất cả byte sau tên là field tùy chọn không có marker.

## 13. An toàn trước đầu vào không tin cậy

Một parser nhị phân cần giả định file/input có thể bị lỗi hoặc được tạo bởi đối tác không tin cậy. Thứ tự xử lý an toàn:

1. **Kiểm tra magic** trước khi hiểu payload.
2. **Đọc version có giới hạn** và xác định chính sách unknown.
3. **Kiểm tra length** không âm, không vượt max, không gây integer overflow khi tính `header + length + trailer`.
4. **Giới hạn cấp phát** trước khi tạo buffer.
5. **Đọc đầy đủ đúng length** và xử lý EOF giữa frame như lỗi.
6. **Kiểm tra checksum** theo đúng phạm vi byte đã định nghĩa.
7. **Kiểm tra schema nội bộ**, length của chuỗi/mảng và UTF-8 hợp lệ.
8. **Từ chối byte dư** nếu schema version đã biết không cho phép.
9. **Giới hạn tổng tải**: số frame, tốc độ, deadline, nesting, số kết nối, memory budget và CPU.
10. **Không xem CRC như xác thực**: nếu cần chống attacker giả mạo, dùng MAC/AEAD/chữ ký theo giao thức an toàn phù hợp.

Đặc biệt, đoạn mã:

~~~java
int length = in.readInt();
byte[] payload = new byte[length]; // NGUY HIỂM nếu chưa kiểm tra
~~~

là anti-pattern. Một length âm gây lỗi cấp phát; một length cực lớn có thể dẫn đến `OutOfMemoryError`. Trong bài demo, `MAX_PAYLOAD` được kiểm tra trước allocation. Trong production, còn phải hạn chế số frame đang được giữ đồng thời.

### Length lồng nhau

Frame đã có `payloadLength`, nhưng payload có thể lại chứa `nameLen`, `arrayLength` hoặc danh sách element. **Mọi độ dài lồng nhau** đều phải được kiểm tra so với byte còn lại và giới hạn nghiệp vụ; không vì frame ngoài hợp lệ mà tin mọi trường trong payload đều hợp lệ.

Ví dụ decoder demo xác nhận `nameLength <= remaining - extraBytes`. Nếu thêm một danh sách bản ghi con, parser phải giới hạn count và kiểm tra số byte cần thiết trước khi lặp hoặc cấp phát.

## 14. ByteBuffer: ví dụ ngắn về header big-endian

Nếu muốn dựng header bằng `ByteBuffer` thay vì `DataOutputStream`:

~~~java
ByteBuffer header = ByteBuffer.allocate(9)
        .order(ByteOrder.BIG_ENDIAN);

header.putInt(0x4A42494E); // "JBIN"
header.put((byte) 1);      // version
header.putInt(123);       // payloadLength

header.flip();             // Chuẩn bị cho channel.write(header)
~~~

Đây là **mảnh code minh họa**; import `java.nio.ByteBuffer` và `java.nio.ByteOrder`, và không tự gửi dữ liệu.

`flip()` là bước quan trọng: sau `put`, position đứng ở cuối vùng đã ghi; nếu quên `flip` mà gọi `channel.write(header)`, có thể truyền 0 byte hoặc dữ liệu không mong muốn. Với `SocketChannel` non-blocking, ngay cả sau `flip`, `write` có thể gửi một phần header; cần giữ buffer chưa gửi hết.

Reader phía ByteBuffer:

~~~java
header.order(ByteOrder.BIG_ENDIAN);
int magic = header.getInt();
int version = Byte.toUnsignedInt(header.get());
int length = header.getInt();
~~~

Chỉ được gọi các lệnh `get` sau khi **đã nhận đủ 9 byte**; nếu không, `BufferUnderflowException` có thể xuất hiện. Đọc và kiểm tra length trước khi cấp phát buffer payload. Những byte này cùng đặc tả với `DataInputStream` demo.

## 15. Những sai lầm phổ biến

**Sai lầm 1 — Không có length-prefix.** Khi ghép nhiều record nhị phân, parser không biết ranh giới. Giải pháp: đặc tả framing theo độ dài hoặc một cơ chế đóng gói đủ chặt khác.

**Sai lầm 2 — Chỉ có length mà không version.** Khi thêm một field, parser cũ có thể diễn giải nhầm byte. Giải pháp: schema version và chính sách tương thích.

**Sai lầm 3 — Quên quy định byte order.** Java, C và hệ điều hành có thể dùng cách biểu diễn khác. Giải pháp: định nghĩa big-endian/little-endian trong đặc tả và test bytes.

**Sai lầm 4 — Dùng `String.length()` làm độ dài UTF-8.** Ký tự nhiều byte khiến reader lệch offset. Giải pháp: encode UTF-8 rồi ghi độ dài byte.

**Sai lầm 5 — Dùng `writeUTF/readUTF` cho giao thức UTF-8 chuẩn.** Đó là modified UTF-8 có framing riêng. Giải pháp: ghi u16/u32 byteLength rồi ghi byte UTF-8 chuẩn.

**Sai lầm 6 — Cấp phát theo length chưa kiểm tra.** Có thể tạo mảng khổng lồ hoặc âm. Giải pháp: kiểm tra phạm vi trước allocation.

**Sai lầm 7 — Coi EOF giữa payload là kết thúc file hợp lệ.** Đó là frame bị cắt cụt. Giải pháp: phân biệt EOF đúng ranh giới và EOF giữa frame.

**Sai lầm 8 — Gặp unknown version thì đọc payload bằng schema gần giống.** Có thể sai hoàn toàn. Giải pháp: skip toàn frame nếu giao thức cho phép, hoặc lỗi rõ ràng.

**Sai lầm 9 — Không kiểm tra byte dư của schema đã biết.** Parser có thể chấp nhận record encode lệch schema. Giải pháp: yêu cầu payload được tiêu thụ trọn vẹn khi version cố định.

**Sai lầm 10 — Nghĩ CRC bảo vệ chống sửa giả mạo.** CRC32 không phải MAC. Giải pháp: dùng xác thực mật mã nếu có attacker.

**Sai lầm 11 — Giả định một lần đọc TCP trả đủ một frame.** TCP là byte stream; cần state machine tích lũy header và payload.

**Sai lầm 12 — Không test nhiều frame nối tiếp.** Parser có thể đọc lấn sang frame sau hoặc không reset state đúng. Giải pháp: round-trip nhiều version, unknown version ở giữa, frame cuối, EOF và dữ liệu hỏng.

## 16. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Đọc byte theo đặc tả

Với header:

~~~text
4A 42 49 4E 01 00 00 00 0B
~~~

Hãy xác định:

- Magic: **`JBIN`**.
- Version: **1**.
- Payload length: **11 byte**.
- Tổng frame length theo cấu trúc bài học: **13 + 11 = 24 byte**, gồm CRC32 4 byte ở cuối.

Đây chỉ là **header**, chưa có payload/CRC đi kèm để kết luận cả frame hợp lệ.

### Bài tập 2 — Version 1 và version 2

Nếu v1 có id=7 và name `"Alpha"`:

- id: 4 byte.
- name length: 2 byte.
- UTF-8 `Alpha`: 5 byte.
- Tổng payload v1: **11 byte**.
- Tổng frame: **24 byte**.

Nếu v2 có cùng name/id và thêm priority i32 thì payload là **15 byte**, frame là **28 byte**. Không lấy số ký tự Java thay cho số byte UTF-8 khi có ký tự ngoài ASCII.

### Bài tập 3 — Bổ sung loại message

Thêm trường type vào header: version chung, type 1 byte, length 4 byte. Cần:

1. Cập nhật header size từ 9 thành 10 byte.
2. Viết lại encoder/decoder đồng bộ.
3. Xác định type không được hỗ trợ phải skip hay reject.
4. Cân nhắc cách phân biệt tệp dùng header cũ với header mới (ví dụ thay format major version/magic), không âm thầm đọc sai.

### Bài tập 4 — Trường hợp length không hợp lệ

Viết test với `payloadLength = -1`, `65_537`, `0`, `65_536`. Trong demo:

- -1 và 65.537: **từ chối**.
- 0 và 65.536: **nằm trong phạm vi length cho phép** ở cấp frame; tuy vậy payload 0 byte không đủ schema v1/v2 và sẽ bị decoder của các version đó từ chối.

### Câu hỏi

1. Version dùng để làm gì? **Chọn cấu trúc/ý nghĩa trường payload**.
2. Length dùng để làm gì? **Xác định ranh giới frame, giới hạn cấp phát và hỗ trợ skip**.
3. Có thể chỉ dùng magic để tìm frame kế tiếp không? **Không an toàn theo mặc định**, vì magic có thể xuất hiện trong payload.
4. Byte order của `DataOutputStream.writeInt` là gì? **Big-endian**.
5. UTF-8 byte length có luôn bằng `String.length()`? **Không**.
6. Reader gặp unknown version mà vẫn biết frame length, có luôn được skip không? **Chỉ nếu hợp đồng giao thức cho phép và frame độc lập**.
7. `readFully` có trả ít byte mà không báo lỗi khi EOF giữa payload không? **Không**, nó ném `EOFException` khi không đọc đủ.
8. CRC32 có bảo mật trước attacker không? **Không**, chỉ phát hiện nhiều dạng lỗi dữ liệu ngẫu nhiên.
9. Đọc tới EOF ở đúng ranh giới giữa hai frame khác gì EOF sau vài byte header? **Trường hợp đầu có thể hợp lệ; trường hợp sau là frame bị cắt cụt**.
10. Nếu length = 2 GiB và reader có ít RAM thì nên làm gì? **Từ chối theo giới hạn** hoặc thiết kế streaming có budget rõ ràng; không cấp phát trực tiếp.
11. Khi thêm field tùy chọn cần mô tả gì? **Version, presence flag/schema, thứ tự, kích thước, default và chính sách unknown**.
12. Để lưu file có thể bị mất điện giữa lần append, cần gì ngoài length? **Phát hiện record dở, commit/recovery rule và durability policy nếu cần**.

**Ghi nhớ:** một định dạng nhị phân có **magic + version + length** giúp parser nhận biết loại dữ liệu và ranh giới record; thêm schema byte order/UTF-8, giới hạn độ dài, checksum và quy tắc lỗi thì mới thành một giao thức có thể vận hành. Luôn **kiểm tra length trước khi cấp phát**, phân biệt EOF hợp lệ với dữ liệu bị cắt cụt, và chỉ skip phiên bản chưa biết khi có cơ sở từ đặc tả. Một ví dụ round-trip đúng phải được kiểm thử bằng nhiều phiên bản, nhiều frame, đầu vào sai và khôi phục sau lỗi.

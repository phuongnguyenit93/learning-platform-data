# DataInput, DataOutput và định dạng dữ liệu nguyên thủy trong Java I/O

## 1. Từ giá trị Java đến dữ liệu nhị phân

Một file hoặc kết nối mạng chỉ truyền **byte**. Khi cần lưu `int`, `long`, `boolean`, `float`, `double`, `char` hay chuỗi ký tự, chương trình phải quy định **bao nhiêu byte, theo thứ tự nào và cách diễn giải ra sao**.

Ví dụ cùng một giá trị 300:

- Ghi như **văn bản UTF-8** `"300"`: các byte hex `33 30 30`, dài 3 byte, phía đọc phải parse chuỗi số.
- Ghi như **nhị phân bằng `writeInt(300)`**: các byte hex `00 00 01 2C`, dài 4 byte; `readInt()` tái tạo số 300 theo quy tắc Java.

**`java.io.DataOutput`** là interface quy định cách viết các giá trị Java kiểu nguyên thủy và một dạng chuỗi vào luồng byte. **`java.io.DataInput`** là interface quy định cách đọc theo cùng hợp đồng byte.

Hai lớp triển khai điển hình là **`DataOutputStream`**, bọc một `OutputStream`, và **`DataInputStream`**, bọc một `InputStream`. Chúng chuyển giữa giá trị Java và byte có cấu trúc; chúng không tự biết tên trường, schema bản ghi, số lượng bản ghi hoặc phiên bản file.

~~~text
Bên ghi                                   Bên đọc
int, double, boolean, String             byte trong file/network
           |                                      |
           v                                      v
     DataOutputStream                        DataInputStream
           |                                      |
           +---- byte layout phải khớp ----------+
~~~

**Nguyên tắc cốt lõi:** phía đọc phải biết đúng **thứ tự và kiểu** đã được phía ghi sử dụng. Nếu ghi `int` rồi `double` mà đọc `short` rồi `double`, dữ liệu sẽ lệch ranh giới byte; lỗi đôi khi âm thầm tạo giá trị sai trước khi xảy ra EOF.

## 2. Kích thước và thứ tự byte của primitive

Theo hợp đồng `DataInput`/`DataOutput` của Java:

| Ghi / đọc | Byte | Diễn giải |
| --- | ---: | --- |
| `writeBoolean` / `readBoolean` | 1 | 0 = false, khác 0 = true khi đọc; writer ghi 0 hoặc 1 |
| `writeByte` / `readByte` | 1 | Đọc dạng byte có dấu (-128 đến 127) |
| `writeByte` / `readUnsignedByte` | 1 | Đọc cùng 8 bit dưới dạng int 0–255 |
| `writeShort` / `readShort` | 2 | Số signed 16 bit |
| `writeShort` / `readUnsignedShort` | 2 | Cùng 16 bit, trả int 0–65535 |
| `writeChar` / `readChar` | 2 | Một đơn vị mã UTF-16 của Java |
| `writeInt` / `readInt` | 4 | Số signed 32 bit |
| `writeLong` / `readLong` | 8 | Số signed 64 bit |
| `writeFloat` / `readFloat` | 4 | Bit float qua Float.floatToIntBits |
| `writeDouble` / `readDouble` | 8 | Bit double qua Double.doubleToLongBits |
| `writeUTF` / `readUTF` | 2 + N | Độ dài unsigned 16 bit + N byte **modified UTF-8** |

Với những kiểu nhiều byte, **byte cao (most significant byte) đi trước**: đây là **big-endian**, được định nghĩa bởi DataInput/DataOutput và **không phụ thuộc CPU** đang chạy big-endian hay little-endian.

~~~text
writeInt(0x01020304) -> 01 02 03 04
writeShort(300)      -> 01 2C
writeChar('A')       -> 00 41
writeLong(1)         -> 00 00 00 00 00 00 00 01
~~~

Không nhầm với little-endian: `0x01020304` ở little-endian thường là `04 03 02 01`. Nếu giao thức ngoài Java yêu cầu little-endian, có thể dùng **`ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)`** hoặc parser thích hợp; **`DataInputStream.readInt()` không có tùy chọn little-endian**.

Đối số dạng `int` truyền vào `writeByte`, `writeShort`, `writeChar` bị lấy **8 hoặc 16 bit thấp** tương ứng. Không được coi `writeByte(300)` là cách ghi nguyên số 300. Muốn giữ đúng giá trị phải chọn kích thước và signed/unsigned của trường trước khi ghi.

## 3. Ví dụ Java 17+: ghi rồi đọc một bản ghi binary

Tạo file **PrimitiveBinaryDemo.java** (lưu mã nguồn bằng UTF-8):

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.Arrays;
import java.util.HexFormat;

public class PrimitiveBinaryDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(0x01020304);
            out.writeShort(300);
            out.writeBoolean(true);
            out.writeDouble(1.5);
            out.writeUTF("Hi");
        }

        byte[] data = buffer.toByteArray();
        System.out.println("bytes=" + data.length);
        System.out.println("prefix="
                + HexFormat.of().formatHex(Arrays.copyOf(data, 7)));

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(data))) {
            System.out.printf("id=%08X%n", in.readInt());
            System.out.println("count=" + in.readUnsignedShort());
            System.out.println("enabled=" + in.readBoolean());
            System.out.println("ratio=" + in.readDouble());
            System.out.println("label=" + in.readUTF());
            System.out.println("eof=" + in.read());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PrimitiveBinaryDemo.java
java PrimitiveBinaryDemo
~~~

Kết quả:

~~~text
bytes=19
prefix=01020304012c01
id=01020304
count=300
enabled=true
ratio=1.5
label=Hi
eof=-1
~~~

Giải thích bố cục 19 byte:

| Trường | Byte (hex) | Dài |
| --- | --- | ---: |
| id, `writeInt` | 01 02 03 04 | 4 |
| count, `writeShort` | 01 2C | 2 |
| enabled, `writeBoolean` | 01 | 1 |
| ratio, `writeDouble(1.5)` | 3F F8 00 00 00 00 00 00 | 8 |
| label, `writeUTF("Hi")` | 00 02 48 69 | 4 |
| **Tổng** | | **19** |

**`HexFormat` có sẵn từ Java 17**. `Arrays.copyOf(data, 7)` chỉ lấy bảy byte đầu để thấy byte của int, short và boolean. `readUnsignedShort()` phục hồi count=300, còn `in.read()` sau cùng trả `-1` vì toàn bộ bản ghi đã được tiêu thụ.

Dùng **try-with-resources** để đóng wrapper. Trong ví dụ, ByteArrayOutputStream giữ dữ liệu trong bộ nhớ, không cần file vật lý; cùng logic có thể bọc Files.newOutputStream/Files.newInputStream để ghi/đọc file.

## 4. Vì sao DataInput/DataOutput chưa phải một file format hoàn chỉnh?

`writeInt` chỉ ghi bốn byte. Không có tên trường `id`, không có số thứ tự field, không tự lưu version, checksum hoặc dấu tách record. Vì thế hai chương trình có thể đọc cùng dãy byte ra kết quả khác nhau nếu schema của chúng khác nhau.

Giả sử một format quy định:

~~~text
record = [id:int, 4 bytes][score:double, 8 bytes]
record = [id:int, 4 bytes][score:double, 8 bytes]
~~~

Mỗi record dài 12 byte. Nếu file có hai record, tổng dữ liệu record là 24 byte. Reader phải biết có hai record, hoặc có header `count`, hoặc một quy tắc kết thúc đã được định nghĩa.

Một format nhị phân ổn định nên có sơ đồ rõ ràng:

~~~text
+---------------+---------+--------------+------------------+
| MAGIC (4 byte)| VERSION | RECORD_COUNT | RECORDS ...      |
+---------------+---------+--------------+------------------+
~~~

- **Magic** xác định loại file, giúp từ chối dữ liệu không cùng định dạng.
- **Version** cho reader biết layout được dùng.
- **Record count** hoặc **length prefix** cho phép xác định ranh giới dữ liệu, không phải đoán bằng dấu EOF tùy tiện.
- **Schema cho từng field** mô tả kích thước, endian, dấu, charset chuỗi, thứ tự và phạm vi hợp lệ.

Nếu phiên bản 1 có `int id` rồi `double score`, còn phiên bản 2 chèn thêm `boolean active` ở giữa, reader v1 sẽ đọc lệch byte của score. Tạo version mới và parser tương thích là giải pháp đúng; không coi việc chèn thêm một byte là tương thích tự động.

**DataOutputStream không phải ObjectOutputStream.** Nó không tự ghi đồ thị object hay metadata class; ứng dụng chủ động chuyển object thành các trường primitive theo schema riêng. Java Object Serialization là cơ chế khác, có định dạng và yêu cầu an toàn riêng.

## 5. writeUTF/readUTF: modified UTF-8 với tiền tố độ dài

Đây là điểm rất quan trọng khi làm việc giữa các ngôn ngữ.

**`DataOutput.writeUTF(String)` không ghi UTF-8 chuẩn thuần túy**. Nó ghi:

1. Hai byte big-endian chứa **độ dài payload tính bằng byte**, trong khoảng 0–65535.
2. N byte mã hóa theo **modified UTF-8** của Java.

**`DataInput.readUTF()`** đọc đúng cấu trúc này: đọc length unsigned 16 bit, sau đó giải mã N byte theo modified UTF-8.

Khác biệt với UTF-8 chuẩn:

- Ký tự NUL `U+0000` ghi thành `C0 80` trong modified UTF-8, thay vì byte `00` theo UTF-8 chuẩn.
- Code point ngoài BMP (ví dụ một số emoji) được thể hiện bằng hai đơn vị UTF-16 surrogate và mỗi đơn vị được mã hóa riêng, thường tổng cộng 6 byte, trong khi UTF-8 chuẩn mã hóa trực tiếp code point đó thành 4 byte.
- Giá trị length là **số byte modified UTF-8 thực tế**, không phải số ký tự String hay `String.length()`.
- Nếu payload modified UTF-8 cần hơn **65.535 byte**, `writeUTF` ném `UTFDataFormatException`.

Các ví dụ byte:

~~~text
writeUTF("Hi")    -> 00 02 48 69
writeUTF("")      -> 00 00
writeUTF(U+0000)  -> 00 02 C0 80
~~~

Điều đó có nghĩa một file TXT UTF-8 thông thường **không thể đọc bằng `readUTF`** nếu file không hề có length prefix và modified UTF-8 theo quy ước trên. Hai byte đầu file sẽ bị hiểu nhầm thành length, gây lỗi, đợi thêm dữ liệu hoặc cho kết quả sai.

Đối với giao thức ngoài Java yêu cầu **UTF-8 chuẩn**, nên viết byte UTF-8 bằng `String.getBytes(StandardCharsets.UTF_8)`, đồng thời định nghĩa **length prefix hoặc delimiter** theo hợp đồng riêng.

## 6. Ví dụ Java 17+: chuỗi UTF-8 chuẩn có chiều dài 4 byte

Tạo file **LengthPrefixedUtf8Demo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class LengthPrefixedUtf8Demo {
    public static void main(String[] args) throws IOException {
        String original = "café";
        byte[] payload = original.getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(payload.length);
            out.write(payload);
        }

        byte[] wire = buffer.toByteArray();
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(wire))) {
            int length = in.readInt();
            if (length < 0 || length > 1_000_000) {
                throw new IOException("Invalid length: " + length);
            }

            byte[] content = new byte[length];
            in.readFully(content);

            String restored = new String(
                    content, StandardCharsets.UTF_8);
            System.out.println("length=" + length);
            System.out.println("hex=" + HexFormat.of().formatHex(content));
            System.out.println("text=" + restored);
            System.out.println("wireBytes=" + wire.length);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LengthPrefixedUtf8Demo.java
java LengthPrefixedUtf8Demo
~~~

Stdout:

~~~text
length=5
hex=636166c3a9
text=café
wireBytes=9
~~~

Bố cục trên wire:

~~~text
00 00 00 05 | 63 61 66 C3 A9
  4 byte    |    5 byte UTF-8 chuẩn
 length=5   |    "café"
~~~

Bên đọc biết bốn byte đầu là length kiểu int big-endian, rồi cần đọc **chính xác length byte**. Vì hai phía cùng thỏa thuận layout và UTF-8 chuẩn, một chương trình Python/Go/C khác cũng có thể đọc nếu triển khai đúng đặc tả; không cần gọi Java `readUTF`.

**`readFully(content)` khác `read(content)`**: `readFully` đọc đủ số byte yêu cầu hoặc ném `EOFException` nếu luồng kết thúc trước; `read(byte[])` có thể đọc ít byte hơn mà không phải lỗi. Trong một frame có độ dài định trước, `readFully` giúp phát hiện payload bị cắt cụt.

Trong ví dụ, ngưỡng `1_000_000` chỉ là **giới hạn của ứng dụng minh họa**, không phải chuẩn chung của Java. Nếu nhận length/count từ đầu vào không đáng tin, cần giới hạn trước khi cấp phát mảng, tính toán dung lượng, hoặc lặp đọc nhiều record.

## 7. Signed/unsigned và sự khác nhau giữa dữ liệu FF với EOF

Java `byte` là kiểu **signed**. Giá trị hex `FF` biểu diễn 8 bit toàn 1:

- `DataInput.readByte()` trả `byte -1`.
- `DataInput.readUnsignedByte()` trả `int 255`.
- `InputStream.read()` đọc byte thô và trả `int 255`, còn **`-1` riêng biệt** để báo đã EOF.

Do đó không được đánh đồng `readByte() == -1` với EOF: **-1 có thể là giá trị byte hợp lệ** khi đọc có dấu. Khi thiếu byte, `readByte()` ném **EOFException**.

Tương tự, `readShort()` trả số signed trong khoảng -32768..32767, còn `readUnsignedShort()` trả int từ 0..65535. Writer dùng `writeShort` ghi 16 bit; reader chọn signed/unsigned theo hợp đồng trường.

Một chi tiết với boolean: `writeBoolean(true)` ghi byte `01`; `writeBoolean(false)` ghi `00`. `readBoolean()` chấp nhận **bất cứ byte khác 0 là true**. Nếu giao thức của ứng dụng chỉ cho phép 0 hoặc 1, reader cần tự kiểm tra byte để từ chối giá trị 2, 3... thay vì dựa duy nhất vào readBoolean.

## 8. EOF và file bị cắt cụt

Có khác biệt giữa **đọc một byte đến hết** và **đọc một trường cố định nhưng không đủ byte**:

- `InputStream.read()` trả **-1** nếu ở EOF.
- `DataInputStream.readInt()` cần đủ 4 byte. Nếu chỉ có 2 byte trước EOF, nó ném **EOFException**, không tự bù 0.
- `DataInputStream.readDouble()` cần 8 byte; nếu thiếu cũng ném EOFException.
- `DataInputStream.readFully(byte[])` yêu cầu đúng chiều dài và ném EOFException nếu thiếu.
- `DataInputStream.readUTF()` cần đủ length prefix cùng payload đúng encoding; có thể ném EOFException hoặc UTFDataFormatException khi lỗi.

**Không được coi mọi EOFException là kết thúc thành công.** Nếu giao thức yêu cầu 10 record nhưng record thứ 9 mới được một nửa thì EOFException là bằng chứng bị cắt cụt, cần báo lỗi. Nếu giao thức chủ động dùng EOF để kết thúc danh sách các bản ghi hoàn chỉnh, phải có logic phân biệt EOF tại **ranh giới bản ghi** với EOF giữa bản ghi.

Đặc biệt, **không viết vòng lặp `while (in.readInt() != -1)`** để tìm EOF. Giá trị số nguyên -1 hoàn toàn hợp lệ và có thể nằm trong dữ liệu; hơn nữa `readInt()` báo thiếu byte bằng exception. Dùng count, length-prefixed records hoặc một marker được định nghĩa rõ và không nhập nhằng.

**`available()` không phải số byte còn lại và không phải kiểm tra EOF** cho mọi nguồn: với network/pipe, nó thường chỉ ước lượng số byte có thể đọc ngay mà không chặn. `available() == 0` không chứng minh rằng luồng đã kết thúc.

## 9. Buffering, flush và đóng luồng

Có thể ghép buffer với data stream:

~~~java
// Mảnh code trong phương thức đã có Path path,
// cùng import Java và xử lý IOException thích hợp.
try (DataOutputStream out = new DataOutputStream(
        new java.io.BufferedOutputStream(
                java.nio.file.Files.newOutputStream(path)))) {
    out.writeInt(123);
    out.writeDouble(4.5);
}
~~~

Ở chiều đọc:

~~~java
try (DataInputStream in = new DataInputStream(
        new java.io.BufferedInputStream(
                java.nio.file.Files.newInputStream(path)))) {
    int id = in.readInt();
    double score = in.readDouble();
    // Xử lý hai trường theo schema của file.
}
~~~

`BufferedOutputStream` gom dữ liệu để giảm thao tác I/O. Nó **không đổi byte order** hay format của DataOutputStream. Đóng qua try-with-resources sẽ đóng wrapper và tầng stream bên dưới, đồng thời đẩy dữ liệu còn đệm nếu quá trình đóng thành công. Khi giao thức cần bên nhận đọc dữ liệu **trong lúc stream vẫn mở**, gọi `flush()` đúng điểm thích hợp; flush không đồng nghĩa đồng bộ bền vững dữ liệu xuống đĩa.

Không đọc và ghi đồng thời trên cùng một file bằng nhiều wrapper thiếu phối hợp rồi mong thứ tự byte ổn định. Không dùng Reader/Writer ở giữa dữ liệu binary vì bước decode/encode ký tự có thể biến đổi byte.

## 10. So sánh với các API khác trong Java I/O

| API | Dùng cho | Lưu ý |
| --- | --- | --- |
| `InputStream`/`OutputStream` | Byte thô | Không biết field kiểu int/double |
| `DataInput`/`DataOutput` | Hợp đồng binary cho các primitive | Không tự quản schema toàn file |
| `DataInputStream`/`DataOutputStream` | Thực thi DataInput/DataOutput bằng stream | Ghi/đọc theo thứ tự xác định |
| `BufferedInputStream`/`BufferedOutputStream` | Giảm lần gọi I/O | Chỉ tối ưu buffering, không đổi format |
| `Reader`/`Writer` | Ký tự/charset | Không dùng để bảo toàn byte binary tùy ý |
| `ObjectInputStream`/`ObjectOutputStream` | Java object serialization | Có định dạng riêng, không tương đương primitive record |
| `ByteBuffer` | Buffer byte và primitive có tùy chọn endian | Dùng khi format ngoài Java yêu cầu little-endian |

**DataOutputStream không tự làm file “portable” theo nghĩa mọi ứng dụng đều đọc được.** Nó cung cấp layout độc lập máy cho từng phép ghi. Muốn tương tác giữa nhiều ngôn ngữ, phải chia sẻ chính xác **bản đặc tả cấu trúc**: magic, version, số byte cho mỗi trường, byte order, signed/unsigned, cách encode chuỗi, cách biểu diễn null, length, checksum nếu có.

## 11. Các lỗi phổ biến và hướng tránh

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Ghi int, đọc short | Lệch vị trí những trường sau | Ghép cặp ghi/đọc theo schema |
| Nghĩ DataInput tự phát hiện endian | Đọc sai file little-endian | Chọn parser/ByteBuffer đúng byte order |
| Gọi readUTF cho file TXT UTF-8 | Hai byte đầu bị hiểu thành độ dài | Chỉ dùng cho payload writeUTF |
| Nhầm modified UTF-8 với UTF-8 chuẩn | Sai ký tự NUL/emoji, sai giao thức | Định nghĩa charset và framing rõ |
| Tưởng String.length() bằng số byte | Length prefix sai cho ký tự đa byte | Dùng encodedBytes.length |
| Vượt giới hạn writeUTF | UTFDataFormatException | Dùng length prefix/payload khác |
| Chỉ gọi read(byte[]) một lần | Có thể thiếu payload | Dùng readFully hoặc lặp đến đủ |
| Bỏ qua EOFException khi đọc giữa record | Chấp nhận file bị cắt cụt | Xử lý truncated như lỗi |
| Tin count/length tùy ý | Cấp phát hoặc xử lý quá lớn | Kiểm tra giới hạn trước |
| Dùng available() đo kích thước toàn stream | Dừng quá sớm hoặc sai EOF | Dựa vào count, length, read/EOF |
| Không version khi đổi schema | File cũ/mới không tương thích | Ghi version và parse có nhánh |
| Không đóng/flush bộ đệm | Thiếu dữ liệu hoặc rò tài nguyên | try-with-resources, flush khi cần |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Cùng số 300, tại sao writeInt ghi 4 byte còn text UTF-8 “300” ghi 3 byte?  
**Trả lời:** writeInt ghi biểu diễn 32 bit của số nguyên; text ghi ký tự chữ số và phải parse mới ra int.

**Câu 2.** DataInputStream.readInt dùng big-endian hay little-endian?  
**Trả lời:** Big-endian theo hợp đồng Java, độc lập với kiến trúc CPU.

**Câu 3.** writeUTF("Hi") ghi mấy byte?  
**Trả lời:** Bốn byte: 00 02 là độ dài payload, 48 69 là nội dung modified UTF-8 của hai ký tự ASCII.

**Câu 4.** Có thể đọc một file TXT UTF-8 bất kỳ bằng readUTF không?  
**Trả lời:** Không. readUTF đòi hỏi tiền tố độ dài hai byte và modified UTF-8.

**Câu 5.** writeUTF giới hạn 65.535 ký tự hay 65.535 byte?  
**Trả lời:** 65.535 **byte mã hóa modified UTF-8**.

**Câu 6.** Nếu dữ liệu định dạng int + double chỉ còn 6 byte, readDouble sau readInt sẽ làm gì?  
**Trả lời:** Chỉ còn 2 byte mà double cần 8; readDouble ném EOFException.

**Câu 7.** Vì sao cần readFully với length-prefixed record?  
**Trả lời:** Nó đọc đủ số byte đã khai báo hoặc báo EOFException; read(byte[]) có thể trả một phần mà không báo lỗi.

**Câu 8.** Một byte FF trả bao nhiêu khi gọi readByte và readUnsignedByte?  
**Trả lời:** Lần lượt là -1 và 255, nếu hai lần đọc được đặt trước một byte FF tương ứng.

**Câu 9.** Tại sao đổi layout từ int+double sang int+boolean+double cần version?  
**Trả lời:** Trường boolean chèn thêm một byte, khiến phía đọc cũ giải mã các byte của double sai vị trí.

## 13. Tài liệu API Java SE 17

- [DataInput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html): primitive, signed/unsigned, big-endian, readFully, modified UTF-8.
- [DataOutput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html): layout byte của phương thức ghi.
- [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): đọc primitive từ InputStream.
- [DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html): ghi primitive vào OutputStream.
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): primitive trong byte buffer, có tùy chọn byte order.

**Ghi nhớ:** DataInput/DataOutput giải quyết **cách mã hóa và giải mã mỗi giá trị nguyên thủy thành byte**. Để tạo một định dạng dữ liệu có thể đọc lại và trao đổi lâu dài, vẫn phải quy định **thứ tự trường, kiểu, độ dài, byte order, charset, version và cách xử lý file bị cắt cụt**. Đặc biệt, writeUTF/readUTF dùng **modified UTF-8 với tiền tố 2 byte**, khác với UTF-8 chuẩn.

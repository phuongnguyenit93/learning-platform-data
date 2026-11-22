# Thiết kế bản ghi nhị phân có magic number, version và length trong Java

## Mục tiêu bài học

Một luồng byte có thể chứa tệp, dữ liệu từ socket hoặc nhiều bản ghi nối tiếp nhau. Bản thân `InputStream` chỉ cung cấp byte theo thứ tự; nó **không tự biết byte nào thuộc bản ghi nào, bản ghi thuộc loại gì hoặc được mã hóa theo phiên bản nào**. Nếu chỉ ghi payload rồi đọc theo cảm tính, chương trình rất dễ phân tích lệch vị trí, cấp phát sai bộ nhớ hoặc đọc nhầm dữ liệu.

Bài này hướng dẫn thiết kế một định dạng bản ghi nhị phân có ba trường đầu tiên:

1. **Magic number**: dấu nhận diện kiểu dữ liệu/định dạng.
2. **Version**: phiên bản cấu trúc để parser biết bộ quy tắc nào phải áp dụng.
3. **Length**: số byte của payload tiếp theo, giúp xác định ranh giới bản ghi.

Bạn sẽ định nghĩa chính xác byte layout, mã hóa và giải mã bằng Java 17+, xử lý bản ghi lỗi, phiên bản không hỗ trợ và payload bị cắt, đồng thời hiểu các giới hạn về tương thích và an toàn.

## 1. Vì sao phải có cấu trúc bản ghi rõ ràng?

Giả sử ứng dụng cần lưu hoặc truyền thông điệp văn bản `Hi`, sau đó là thông điệp khác. Nếu chỉ ghi hai byte UTF-8 `48 69` rồi viết tiếp payload thứ hai, phía đọc không biết khi nào thông điệp đầu kết thúc.

Một header cố định giải quyết nhiều câu hỏi ngay ở đầu:

- **Magic number** giúp kiểm tra nhanh: có vẻ đây là đúng loại file/thông điệp mà parser mong đợi?
- **Version** trả lời: các trường phía sau cần được hiểu theo phiên bản cấu trúc nào?
- **Length** trả lời: parser cần đọc chính xác bao nhiêu byte để kết thúc payload hiện tại?

Đây gọi là **framing** (đóng khung dữ liệu). Với socket TCP, framing đặc biệt quan trọng: TCP truyền **dòng byte liên tục**, không giữ ranh giới của mỗi lần gọi `write()` hoặc mỗi lần người gửi coi là một thông điệp. Một lần `read()` có thể trả một phần, một bản ghi hay dữ liệu từ nhiều bản ghi tùy thời điểm và buffering.

## 2. Định nghĩa giao thức mẫu: JREC phiên bản 1

Không nên tùy tiện ghi các con số vào stream trước khi viết ra **hợp đồng byte chính thức**. Ta định nghĩa một giao thức học tập tên `JREC` như sau:

| Offset (byte) | Số byte | Trường | Giá trị/quy tắc |
| --- | ---: | --- | --- |
| `0..3` | 4 | `magic` | Bốn byte ASCII `JREC`: hex `4A 52 45 43` |
| `4..5` | 2 | `version` | Số nguyên **unsigned 16-bit**, big-endian; hỗ trợ giá trị `1` |
| `6..9` | 4 | `length` | Số nguyên **signed 32-bit**, big-endian; phải thuộc `0..1_048_576` |
| `10..(9 + length)` | `length` | `payload` | Chính xác `length` byte UTF-8 |
| Tiếp theo | — | Bản ghi tiếp theo hoặc EOF | Không có padding/trailer trong phiên bản 1 |

**Tổng kích thước mỗi bản ghi = 10 + length byte.** Header luôn dài `10` byte; `length` đếm **payload byte**, không gồm header, cũng không phải số Java `char` hay Unicode code point.

```text
   0                 3 4     5 6                 9 10
   +-------------------+-------+-------------------+---------------------+
   |  MAGIC "JREC"     | VER   | PAYLOAD_LENGTH    | PAYLOAD bytes ...   |
   |     4 byte        | 2 byte|      4 byte       |  length byte        |
   +-------------------+-------+-------------------+---------------------+
     BE byte order cho các trường số của header       UTF-8, không BOM
```

Quy ước cụ thể:

- Các trường số trong header là **big-endian (network byte order)**. Người viết và người đọc phải thống nhất điều này.
- Version chỉ hỗ trợ `1`; parser **từ chối** version lạ. Không tự đoán cấu trúc mới từ bản cũ.
- `length` được mã hóa bằng `int` 32-bit nhưng **bị giới hạn ở 1 MiB** theo hợp đồng để ngăn payload quá lớn. Phải kiểm tra giới hạn **trước khi cấp phát bộ nhớ**.
- Payload phiên bản 1 là **UTF-8 hợp lệ**; parser nghiêm ngặt báo lỗi nếu byte không hợp lệ thay vì tự thay bằng ký tự thay thế.
- Một stream có thể gồm **nhiều bản ghi** nối tiếp nhau; mỗi parser chỉ đọc đúng header + payload của bản ghi mà nó xử lý.
- Magic chỉ là **dấu nhận diện định dạng**, không phải chữ ký số, checksum hay bằng chứng xác thực nguồn gửi.

Ví dụ văn bản `Hi` có byte UTF-8 `48 69`, nghĩa là `length = 2`:

```text
Magic         Version  Length      Payload
4A 52 45 43 | 00 01 | 00 00 00 02 | 48 69
```

Khi ghép không có dấu phân cách:

```text
4a5245430001000000024869
```

Đây là **12 byte**: 4 magic + 2 version + 4 length + 2 payload. Các ký tự `|` và dấu cách ở sơ đồ chỉ để dễ đọc, không nằm trong dữ liệu thật.

## 3. Vì sao lựa chọn magic, version, length như trên?

### Magic number: phát hiện nhanh sai loại đầu vào

Magic thường là một giá trị dễ nhận biết ở những byte đầu, ví dụ bốn byte ASCII cố định. Với `JREC`, đọc sai magic có thể nghĩa là:

- Người dùng gửi nhầm file thuộc định dạng khác.
- Parser bắt đầu ở sai offset, có thể vì đã đọc thiếu/thừa byte ở phần trước.
- Nội dung bị thay đổi hoặc hỏng.
- Luồng không tuân thủ giao thức đã cam kết.

Không nên chỉ dựa vào magic để kết luận dữ liệu **chắc chắn hợp lệ**: bất kỳ người gửi nào cũng có thể tạo đúng bốn byte magic. Sau khi kiểm tra magic, vẫn cần kiểm tra version, length, payload và các ràng buộc dữ liệu khác.

Magic có thể được ghi bằng `DataOutputStream.writeInt(0x4A524543)` vì API này ghi số nguyên theo **big-endian**. Trong giao thức khác, magic cũng có thể được ghi trực tiếp bằng bốn byte ASCII. Quan trọng là byte layout nhất quán giữa các ngôn ngữ.

### Version: không đọc dữ liệu mới như bản cũ

Version là mã định danh **cấu trúc wire format**, không nhất thiết trùng với phiên bản ứng dụng. Parser phiên bản 1 biết chính xác payload hiện tại là UTF-8; nếu ở version 2 payload thay đổi thành các trường nhị phân, parser v1 phải từ chối version 2 (trừ khi đã được thiết kế hỗ trợ).

Nên xác định rõ:

- Giá trị nào được hỗ trợ.
- Khi không hỗ trợ: báo lỗi với thông tin thích hợp.
- Đổi version khi một thay đổi không tương thích với quy tắc cũ.
- Nếu cần đọc nhiều version: tách parser theo version, tránh dùng một bố cục duy nhất để “đoán” mọi phiên bản.

### Length: xác định ranh giới và chống đọc vượt

Trường `length` phải nói rõ nó đo **byte**, không đo ký tự; tính **payload hay toàn bản ghi**; chứa giá trị âm hay không; và có **giới hạn tối đa** không.

Trong giao thức mẫu, `length` là số byte payload `0..1_048_576`. Giá trị âm hoặc lớn hơn ngưỡng đều bị từ chối. Không cần gọi `InputStream.available()` để tìm độ dài: `available()` chỉ cho biết ước lượng số byte có thể đọc ngay mà không bị chặn, không phải tổng độ dài bản ghi.

## 4. Java 17+: ghi và đọc một bản ghi đầy đủ

Java `DataOutputStream` và `DataInputStream` phù hợp khi định dạng có các trường số big-endian cố định:

- `writeInt(int)`: ghi bốn byte big-endian.
- `writeShort(int)`: ghi hai byte big-endian, lấy 16 bit thấp.
- `readInt()`: đọc đủ bốn byte big-endian thành `int`.
- `readUnsignedShort()`: đọc hai byte thành số `0..65535`.
- `readFully(byte[])`: đọc **đúng số byte** theo độ dài mảng, hoặc ném `EOFException` nếu stream kết thúc sớm.

**Lưu thành `RecordProtocolDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class RecordProtocolDemo {
    private static final int MAGIC = 0x4A524543; // ASCII "JREC"
    private static final int VERSION = 1;
    private static final int MAX_PAYLOAD_BYTES = 1_048_576;

    static void writeRecord(OutputStream target, String text) throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        if (payload.length > MAX_PAYLOAD_BYTES) {
            throw new IllegalArgumentException("payload too large");
        }

        // Không đóng wrapper vì target thuộc quyền sở hữu của người gọi.
        DataOutputStream out = new DataOutputStream(target);
        out.writeInt(MAGIC);
        out.writeShort(VERSION);
        out.writeInt(payload.length);
        out.write(payload);
        out.flush();
    }

    static String readRecord(InputStream source) throws IOException {
        DataInputStream in = new DataInputStream(source);

        int magic = in.readInt();
        if (magic != MAGIC) {
            throw new IOException("invalid magic");
        }

        int version = in.readUnsignedShort();
        if (version != VERSION) {
            throw new IOException("unsupported version");
        }

        int length = in.readInt();
        if (length < 0 || length > MAX_PAYLOAD_BYTES) {
            throw new IOException("invalid length");
        }

        byte[] payload = new byte[length];
        in.readFully(payload);

        // Giải mã nghiêm ngặt: UTF-8 hỏng sẽ báo CharacterCodingException.
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(payload))
                .toString();
    }

    private static void expectFailure(String label, byte[] wire) {
        try {
            readRecord(new ByteArrayInputStream(wire));
            System.out.println(label + " = unexpectedly accepted");
        } catch (IOException e) {
            System.out.println(label + " = "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream destination = new ByteArrayOutputStream();
        writeRecord(destination, "Hi");
        byte[] wire = destination.toByteArray();

        System.out.println("wire = " + HexFormat.of().formatHex(wire));
        System.out.println("decoded = "
                + readRecord(new ByteArrayInputStream(wire)));
        System.out.println("total bytes = " + wire.length);

        byte[] badMagic = wire.clone();
        badMagic[0] = 0;
        expectFailure("bad magic", badMagic);

        byte[] badVersion = wire.clone();
        badVersion[5] = 2;
        expectFailure("unsupported version", badVersion);

        byte[] tooLarge = wire.clone();
        tooLarge[6] = 0x7F; // Length > MAX_PAYLOAD_BYTES.
        expectFailure("oversized length", tooLarge);

        byte[] truncated = Arrays.copyOf(wire, wire.length - 1);
        expectFailure("truncated payload", truncated);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac RecordProtocolDemo.java
java RecordProtocolDemo
```

Đầu ra chính xác:

```text
wire = 4a5245430001000000024869
decoded = Hi
total bytes = 12
bad magic = IOException
unsupported version = IOException
oversized length = IOException
truncated payload = EOFException
```

### Giải thích luồng xử lý

**Ghi (serialize):**

1. Chuyển `text` thành byte UTF-8 bằng `getBytes(StandardCharsets.UTF_8)`. Độ dài lấy từ **`payload.length`**, không phải `text.length()`.
2. Kiểm tra giới hạn kích thước trước khi xuất header.
3. Viết magic, version, length theo thứ tự và đúng kích thước byte đã công bố.
4. Viết toàn bộ payload; `flush()` đẩy dữ liệu xuống tầng thấp hơn. Nó **không chứng minh** dữ liệu đã được lưu bền vững trên đĩa hoặc đầu bên kia đã xử lý.

**Đọc (deserialize):**

1. `readInt()` lấy đủ bốn byte magic hoặc ném `EOFException` khi header không hoàn chỉnh.
2. `readUnsignedShort()` lấy version; nếu không hỗ trợ thì từ chối.
3. `readInt()` đọc length; từ chối giá trị âm hoặc vượt ngưỡng **trước khi gọi `new byte[length]`**.
4. `readFully(payload)` thu đúng `length` byte, kể cả nguồn trả ít byte trong từng lần đọc. Nếu thiếu payload thì ném `EOFException`.
5. Giải mã UTF-8 nghiêm ngặt: dữ liệu sai chuẩn ném `CharacterCodingException` (là một loại `IOException`).

Các phương thức trên không tự đóng `source` hoặc `target`. Trong ứng dụng thực tế, lớp sở hữu stream quyết định vòng đời và thường dùng `try-with-resources` tại điểm mở file/socket. Điều này cho phép nhiều bản ghi dùng chung một stream mà không bị đóng giữa chừng.

### Vì sao hai bài kiểm tra lỗi còn lại hoạt động?

- Khi sửa byte magic đầu thành `00`, parser từ chối magic không trùng `JREC`.
- Khi sửa byte cuối của trường version tại offset `5` thành `02`, version trở thành `2`, parser từ chối.
- Khi sửa byte đầu trường length tại offset `6` thành `7F`, length vượt giới hạn 1 MiB. Chương trình **không cấp phát** một mảng hàng tỉ byte.
- Khi cắt byte cuối của payload, header vẫn khai `length=2`, nhưng chỉ còn một byte. `readFully` ném `EOFException`, không giả vờ nhận bản ghi hợp lệ.

## 5. Tại sao không thể dùng một lần `read(byte[])`?

Đây là cách viết **sai** khi cần đọc chính xác `length` byte:

```java
// MINH HỌA SAI; giả định đã có InputStream in và int length.
byte[] payload = new byte[length];
int count = in.read(payload); // Có thể đọc ít hơn length byte.
```

Trên file hoặc TCP stream, một lần `read` **không được bảo đảm** điền đầy mảng. Dữ liệu có thể đến thành nhiều phần; `count` có thể nhỏ hơn `length` dù chưa EOF.

Đối với giao thức yêu cầu đủ số byte:

```java
// Đoạn minh họa: in là DataInputStream, length đã được kiểm tra an toàn.
byte[] payload = new byte[length];
in.readFully(payload); // Đọc đủ hoặc báo EOFException.
```

Chỉ sử dụng `readFully` sau khi kiểm tra length và giới hạn tài nguyên. Với payload lớn mà bạn không muốn đưa hết vào RAM, dùng vòng lặp đọc từng khối cho đến khi tổng byte đã đọc bằng đúng length. **Đọc đến EOF để xác định cuối một bản ghi không đúng** nếu một kết nối có thể mang nhiều bản ghi: EOF có thể chỉ tới khi kết nối được đóng, rất lâu sau khi thông điệp hiện tại hoàn thành.

### Không dựa vào `available()`

`available() == 0` không có nghĩa bản ghi đã hết. Nó chỉ cho biết tại thời điểm đó không có byte nào được bảo đảm có thể đọc ngay mà không chặn. Sử dụng field length đã công bố và xác nhận kết quả đọc thay vì dựa vào `available()`, kể cả khi bạn đã dùng `BufferedInputStream`.

## 6. Nhiều bản ghi nối tiếp trên cùng luồng

Nếu dữ liệu gồm ba bản ghi, trình tự byte là:

```text
[MAGIC | VERSION | LENGTH | PAYLOAD #1]
[MAGIC | VERSION | LENGTH | PAYLOAD #2]
[MAGIC | VERSION | LENGTH | PAYLOAD #3]
```

Sau khi `readRecord` đọc xong **đúng** `length` byte payload, vị trí luồng sẽ nằm ngay trước header của bản ghi tiếp theo. Không cần separator giữa hai bản ghi vì length cung cấp ranh giới.

Nếu ứng dụng đã biết số bản ghi (ví dụ do một header container bên ngoài quy định), có thể gọi `readRecord` đúng số lần, cùng một `InputStream`. Nếu không biết số lượng và muốn dừng khi stream kết thúc, cần phân biệt:

- **EOF sạch trước khi bắt đầu header mới:** không còn bản ghi nào.
- **EOF giữa chừng trong magic/version/length/payload:** dữ liệu đã bị cắt hoặc truyền chưa hoàn chỉnh, phải báo lỗi.

Ví dụ `DataInputStream.readInt()` ném `EOFException` cả khi **chưa đọc được byte đầu magic** lẫn khi **mới đọc được một vài byte của magic**. Vì vậy không nên bắt mọi `EOFException` rồi coi là kết thúc bình thường.

Một cách thiết kế parser chuỗi bản ghi là đọc **một byte đầu của magic**:

1. Nếu byte đầu trả `-1`, chỉ khi đó coi là EOF sạch trước bản ghi mới.
2. Nếu đã nhận byte đầu, phải đọc tiếp đủ ba byte còn lại của magic; thiếu byte nào là bản ghi lỗi.
3. Sau đó áp dụng toàn bộ kiểm tra version, length, payload như trên.

Không dùng hai `BufferedInputStream` hay hai parser độc lập cùng tranh một nguồn: lớp đệm có thể đã đọc trước byte của header tiếp theo.

## 7. Kiểm tra độ dài an toàn và chống cấp phát quá mức

Trường length là **dữ liệu do phía gửi hoặc file cung cấp**. Dù có phép kiểm tra magic, dữ liệu vẫn có thể độc hại hoặc hỏng. Hãy coi mọi trường trong header là không đáng tin cho đến khi kiểm tra:

| Rủi ro | Cách xử lý |
| --- | --- |
| Length âm | Từ chối trước khi tạo mảng. |
| Length cực lớn | Đặt giới hạn ứng dụng/giao thức; từ chối trước khi cấp phát. |
| Length nhỏ hơn payload thực | Parser sẽ hiểu các byte thừa là header kế tiếp; có thể sai magic hoặc lệch frame. Cần kiểm tra đúng định dạng phía gửi. |
| Length lớn hơn dữ liệu thực | `readFully` báo `EOFException`; nếu stream mạng chưa EOF có thể chờ thêm byte. |
| Header thiếu byte | Báo bản ghi không hoàn chỉnh, không đọc vượt sang dữ liệu không thuộc bản ghi. |
| Byte UTF-8 không hợp lệ | Decoder nghiêm ngặt báo lỗi. |
| Length hợp lệ nhưng tổng bản ghi quá nhiều | Thêm giới hạn số bản ghi, tổng byte, thời gian hoặc tốc độ phù hợp. |

**Không dùng `Files.size(path)` hoặc tổng dữ liệu còn lại trong file thay cho length từng bản ghi**, trừ khi định dạng thực sự khai báo “một file chỉ chứa một payload”. Với nhiều bản ghi nối tiếp, kích thước file là thông tin của toàn container, còn length là thông tin mỗi frame.

Với payload lớn, không nên cấp phát toàn bộ `byte[length]`. Có thể dùng buffer cố định và biến `remaining`:

```java
// MINH HỌA THUẬT TOÁN, chưa phải chương trình chạy độc lập.
// in: DataInputStream đã đọc header; out: OutputStream đích; remaining = length đã xác thực.
byte[] buffer = new byte[8192];
while (remaining > 0) {
    int chunk = (int) Math.min(buffer.length, remaining);
    in.readFully(buffer, 0, chunk);
    out.write(buffer, 0, chunk);
    remaining -= chunk;
}
```

Trong đoạn minh họa, `remaining` là biến kiểu `long` hoặc `int` đã được khởi tạo bằng length hợp lệ; `in` và `out` được quản lý bởi người gọi. Cách này không cần RAM tỷ lệ theo payload và vẫn đọc **đúng số byte của frame**. Nó chưa làm các bước kiểm tra magic/version, checksum hay policy riêng của ứng dụng; các bước đó thuộc lớp parser bên ngoài.

## 8. Byte order, charset và ranh giới dữ liệu

### Big-endian phải là quy tắc được viết ra

`DataOutputStream.writeInt` và `DataInputStream.readInt` ghi/đọc số nguyên big-endian, nhưng không phải mọi thư viện, ngôn ngữ, CPU hay `ByteBuffer` tùy chỉnh đều mặc định giống nhau.

Nếu phía gửi ghi length `2` bằng little-endian (`02 00 00 00`) còn phía nhận đọc big-endian, giá trị sẽ thành `33_554_432` và có thể bị từ chối hoặc gây cấp phát sai nếu không kiểm tra. Vì vậy bản đặc tả cần công bố endian **cho từng trường số**.

Đừng “thử đảo byte” không có kiểm soát khi length trông sai. Khi có nhiều biểu diễn hợp lệ, cách đoán dễ dẫn tới parser mơ hồ và lỗi bảo mật. Phải xác định byte order bằng đặc tả và version.

### Length của UTF-8 đếm byte

Payload `"é"` có:

- Một Unicode code point.
- Một Java UTF-16 code unit (nên `"é".length() == 1`).
- **Hai byte UTF-8**: `C3 A9`.

Vì vậy length cho payload này phải là `2`, không phải `1`. Với emoji 😀, UTF-8 cần bốn byte, còn `String.length()` trong Java trả `2` (surrogate pair). Khi ghi, **luôn mã hóa trước rồi lấy `payload.length`**.

### Không nhầm `writeUTF/readUTF` với UTF-8 payload của giao thức

`DataOutputStream.writeUTF(String)` sử dụng một dạng **modified UTF-8** với độ dài 2 byte ở phía trước và quy tắc mã hóa khác UTF-8 chuẩn cho một số ký tự. `DataInputStream.readUTF()` chỉ phù hợp khi cả hai phía cố ý sử dụng **đúng định dạng của `writeUTF`**.

Với JREC v1, header đã có length 4 byte và payload là UTF-8 chuẩn; **không dùng `writeUTF/readUTF`** để thay `writeInt(payload.length)` + `write(payload)`. Làm vậy sẽ thay đổi layout và khiến parser ngoài Java khó tương thích.

## 9. Thiết kế version để có thể tiến hóa

Một format tốt không chỉ đọc bản ghi hôm nay mà còn xác định hành vi khi gặp dữ liệu của ngày mai.

Ví dụ các tình huống tương lai:

- **Version 1:** payload text UTF-8 như ví dụ.
- **Version 2:** payload có trường loại bản ghi, timestamp hoặc checksum.
- **Version 3:** thêm cơ chế nén hay biến thể cấu trúc.

Nếu đổi ý nghĩa byte của header, phải xác định rõ **version được đọc ở đâu và parser phân nhánh khi nào**. Ở ví dụ, cả v1 và các version tương lai sẽ phải giữ magic và vị trí version như một phần giao kèo chung, hoặc phải công bố cơ chế phát hiện định dạng mới.

Các phương án tiến hóa:

1. **Tăng version** khi bố cục hoặc ý nghĩa trường thay đổi không tương thích.
2. **Giữ header tối thiểu ổn định** đủ để chọn parser đúng version.
3. **Đưa các trường tùy chọn vào payload có cấu trúc** (ví dụ TLV: type-length-value) khi cần thêm trường mà không phá dữ liệu cũ, nhưng phải định nghĩa rõ type, endian, duplicate fields và cách xử lý trường chưa biết.
4. **Không tự coi mọi version lớn hơn là tương thích.** Khả năng bỏ qua trường lạ chỉ có nếu giao thức được thiết kế hỗ trợ ngay từ đầu.
5. **Có dữ liệu mẫu chuẩn (golden bytes)** trong bộ kiểm thử liên ngôn ngữ: cùng một chuỗi phải tạo cùng các byte, đọc lại cùng giá trị.

Trong mọi trường hợp, việc đổi kích thước trường length hoặc đơn vị đo byte cũng là thay đổi giao thức: không được âm thầm sửa ở một phía.

## 10. Checksum, xác thực và đồng bộ lại luồng

Magic + version + length giúp **đóng khung và nhận diện** bản ghi, nhưng không bảo đảm tính toàn vẹn hay tính xác thực.

- **Checksum/CRC** (ví dụ CRC32) có thể phát hiện nhiều lỗi dữ liệu vô tình thay đổi; nếu thêm, phải quy định nó đặt trước/sau payload, tính trên byte nào, endian và cách parser xác minh. CRC không bảo vệ trước đối thủ có thể chủ động sửa dữ liệu và tính lại CRC.
- **MAC hoặc chữ ký số** là vấn đề khác: dùng khi giao thức cần chống giả mạo và xác minh bên gửi. Cần thiết kế key management và phạm vi dữ liệu được xác thực theo mô hình an ninh của ứng dụng.
- **Magic không bảo đảm có thể khôi phục đồng bộ.** Khi một length bị hỏng, parser có thể đứng sai vị trí. Việc quét tìm magic ở byte tiếp theo chỉ là heuristic; chuỗi giống magic có thể xuất hiện hợp lệ trong payload.
- **Độ bền ghi:** `flush()` không tương đương cam kết atomic record hoặc fsync. Một tiến trình có thể dừng giữa header và payload, để lại bản ghi cuối bị cắt. Parser cần báo EOF giữa frame; nếu cần commit nguyên tử, phải có thiết kế file/transaction riêng.

Đối với tệp chỉ phục vụ học tập hoặc dữ liệu tin cậy, header mẫu là đủ để hiểu framing. Khi dùng trong hệ thống thực, lựa chọn checksum/xác thực/nén phải dựa trên nhu cầu cụ thể và được mô tả thành version hoặc cờ trường có nghĩa rõ ràng.

## 11. Phân biệt lỗi và cách phản hồi

| Phát hiện | Ý nghĩa có thể xảy ra | Cách xử lý đề xuất |
| --- | --- | --- |
| Magic sai | Sai loại file, offset sai, dữ liệu hỏng | Từ chối, ghi nhận vị trí và magic thực tế nếu an toàn. |
| Version không hỗ trợ | Định dạng mới hoặc parser quá cũ | Từ chối rõ ràng; cập nhật parser nếu được phép. |
| Length âm | Header bất hợp lệ | Từ chối trước cấp phát. |
| Length vượt giới hạn | Dữ liệu vượt chính sách/tấn công tiêu tốn tài nguyên | Từ chối, giới hạn nguồn và số byte xử lý. |
| EOF giữa header hoặc payload | File bị cắt, truyền chưa hoàn chỉnh, kết nối đóng | Báo lỗi frame thiếu dữ liệu; không coi là EOF sạch. |
| UTF-8 sai | Payload không theo giao thức | Báo lỗi giải mã nghiêm ngặt. |
| Nội dung ngữ nghĩa sai dù đúng framing | Payload không hợp quy tắc nghiệp vụ | Xác thực thêm sau khi giải mã. |

Không phải mọi lỗi đều được sửa bằng cách thử đọc thêm. Với magic/version/length sai, parser có thể đã mất khả năng xác định ranh giới; tiếp tục đọc bừa dễ làm che giấu lỗi và khiến dữ liệu kế tiếp bị hiểu sai.

## 12. Những lỗi phổ biến cần tránh

1. **Chỉ định dạng header bằng chuỗi** như `out.print(length)`: nó tạo các chữ số text, không tạo bốn byte big-endian như `writeInt`.
2. **Không công bố byte order**: hai phía có thể hiểu cùng bốn byte thành hai số khác nhau.
3. **Lấy `String.length()` làm length của payload UTF-8**: sai với nhiều ký tự Unicode.
4. **Dùng `available()` để xác định đã nhận đủ payload**: giá trị này không đo tổng số byte sẽ đến.
5. **Gọi `read(payload)` đúng một lần rồi mặc định mảng đã đầy**: phải lặp cho đủ hoặc dùng `readFully`.
6. **Cấp phát `new byte[length]` trước khi giới hạn length**: dữ liệu không tin cậy có thể ép cấp phát quá lớn.
7. **Bắt mọi `EOFException` rồi xem là hết file bình thường**: header/payload có thể mới đọc một phần.
8. **Dùng `writeUTF/readUTF` cho payload UTF-8 chuẩn**: hai API đó dùng định dạng modified UTF-8 và có prefix riêng.
9. **Thấy magic đúng là cho rằng bản ghi an toàn**: cần còn kiểm tra version, length, dữ liệu và điều kiện nghiệp vụ.
10. **Thay đổi trường khi không đổi version**: khiến bộ đọc cũ hiểu sai wire format.
11. **Đọc tiếp đến EOF cho một bản ghi trên socket**: kết nối có thể giữ mở và chứa nhiều bản ghi, phải dừng sau đúng `length` byte.
12. **Không kiểm soát vòng đời stream**: đóng wrapper ở mỗi bản ghi có thể đóng luôn kết nối dùng cho các bản ghi tiếp theo.
13. **Quên rằng packet của TCP không phải record của ứng dụng**: số lần `write` không quyết định số lần `read` tương ứng.
14. **Chỉ kiểm tra checksum mà không kiểm tra giới hạn length**: checksum không chống cấp phát hoặc đọc quá giới hạn.

## 13. Bài tập tự kiểm tra

**1.** Với header `JREC` v1 và payload có byte UTF-8 `48 69`, tổng số byte của bản ghi là bao nhiêu?

**Đáp án:** `10 + 2 = 12` byte; header 10 byte và payload 2 byte.

**2.** Nếu gửi payload `é` nhưng ghi length bằng `"é".length()` thì có lỗi gì?

**Đáp án:** Length bị ghi thành `1` trong khi payload UTF-8 gồm `2` byte. Parser sẽ đọc thiếu payload, để sót byte và có thể làm lệch header bản ghi kế tiếp.

**3.** Vì sao phải kiểm tra version *trước* khi parse payload?

**Đáp án:** Cấu trúc payload phụ thuộc phiên bản. Parser v1 không được mặc nhiên áp dụng luật v1 cho byte version mới nếu chưa biết tương thích.

**4.** Khi `readFully(payload)` ném `EOFException`, có nên trả payload đã đọc dở như bản ghi hợp lệ không?

**Đáp án:** Không. Giao thức công bố cần đủ `length` byte; bản ghi thiếu byte phải báo lỗi, không thể coi là hoàn chỉnh.

**5.** Magic number có ngăn người gửi giả mạo bản ghi hay không?

**Đáp án:** Không. Magic chỉ đánh dấu kiểu dữ liệu. Muốn xác thực nguồn và chống thay đổi có chủ đích cần cơ chế xác thực mật mã được thiết kế riêng.

**6.** Vì sao parser một stream chứa nhiều bản ghi không nên đóng `InputStream` ngay sau mỗi `readRecord`?

**Đáp án:** Vì tất cả bản ghi có thể dùng chung nguồn. Đóng stream sau bản ghi đầu tiên sẽ ngăn đọc những bản ghi tiếp theo.

**7.** Nếu phía gửi ghi length little-endian nhưng phía đọc dùng `DataInputStream.readInt()`, điều gì xảy ra?

**Đáp án:** Parser có thể nhận giá trị length sai, dẫn tới đọc sai hoặc từ chối theo giới hạn. Phải thống nhất byte order trong đặc tả.

## Tóm tắt

Một bản ghi nhị phân có **magic number + version + length + payload** chỉ đáng tin khi có một **hợp đồng byte rõ ràng**: vị trí/kích thước trường, byte order, đơn vị đo length, charset, giới hạn và quy tắc xử lý lỗi.

Với Java 17+, `DataOutputStream`/`DataInputStream` giúp ghi/đọc trường số big-endian. Hãy xác nhận magic, version, length **trước cấp phát**, đọc đúng payload bằng `readFully`, phân biệt EOF sạch với bản ghi bị cắt, rồi kiểm tra nội dung và khả năng tương thích theo phiên bản. Khi nhu cầu hệ thống tăng, cân nhắc cơ chế checksum/xác thực và chiến lược chuyển phiên bản thay vì sửa âm thầm format v1.

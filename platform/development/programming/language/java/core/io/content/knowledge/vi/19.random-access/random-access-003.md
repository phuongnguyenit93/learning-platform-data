# Đọc ghi dữ liệu nguyên thủy qua DataInput và DataOutput trong Java

`DataInput` và `DataOutput` là hai giao diện trong `java.io` định nghĩa **cách đọc và ghi dữ liệu nhị phân có cấu trúc**: số nguyên, số thực, ký tự, `boolean` và chuỗi theo quy ước. Chúng đặc biệt hữu ích khi lưu bản ghi vào file hoặc truyền dữ liệu giữa các thành phần Java. Trong chủ đề **truy cập ngẫu nhiên**, `RandomAccessFile` là ví dụ quan trọng: lớp này thực thi cả hai giao diện, đồng thời có `seek(long)` để đọc hoặc sửa dữ liệu ở một vị trí byte cụ thể.

Bài học giải thích hợp đồng nhị phân, cách kết hợp stream và `RandomAccessFile`, cách thiết kế bản ghi có độ dài cố định, kiểm soát sai lệch định dạng, và những giới hạn của việc cập nhật file tại chỗ.

## 1. Vì sao cần DataInput và DataOutput?

Một file nhị phân không tự mô tả kiểu dữ liệu. Ví dụ dãy byte `00 00 00 2A` có thể biểu diễn số nguyên 42 theo thứ tự byte big-endian, nhưng chương trình phải **biết trước** đây là một `int` để đọc đúng. Nếu chỉ ghi các byte rồi đoán kiểu khi đọc, kết quả rất dễ sai hoặc phát sinh lỗi thiếu dữ liệu.

Hai giao diện đóng vai trò một **hợp đồng về cấu trúc và thứ tự trường**:

- `DataOutput` cung cấp `writeInt`, `writeLong`, `writeDouble`, `writeBoolean`, `writeChar`, `writeUTF` và các phương thức khác.
- `DataInput` cung cấp các phương thức đối ứng `readInt`, `readLong`, `readDouble`, `readBoolean`, `readChar`, `readUTF`, cùng `readFully` và `skipBytes`.
- Chương trình **tự quyết định schema**: trường nào xuất hiện trước, ý nghĩa và độ dài từng trường, phiên bản format và số bản ghi.
- Cả hai là **interface**, không phải stream có thể tạo bằng `new DataInput()` hay `new DataOutput()`.

Các hiện thực phổ biến:

| Lớp | DataInput | DataOutput | Kiểu truy cập |
| --- | --- | --- | --- |
| `DataInputStream` | Có | Không | Đọc tuần tự từ `InputStream`. |
| `DataOutputStream` | Không | Có | Ghi tuần tự vào `OutputStream`. |
| `RandomAccessFile` | Có | Có | Đọc/ghi và di chuyển vị trí trong file bằng `seek`. |

Cần phân biệt `DataInputStream`/`DataOutputStream` với `ObjectInputStream`/`ObjectOutputStream`: bài này ghi **giá trị nguyên thủy theo schema tự định nghĩa**, không dùng Java object serialization.

## 2. Quy ước byte: ghi gì thì phải đọc đúng thứ tự ấy

Các phương thức kiểu số của DataInput/DataOutput sử dụng **big-endian** (byte có trọng số cao đứng trước). Độ dài phổ biến:

| Cặp API | Số byte | Quy tắc và lưu ý |
| --- | ---: | --- |
| `writeBoolean` / `readBoolean` | 1 | Ghi 1 cho `true`, 0 cho `false`; khi đọc, byte khác 0 cũng được xem là `true`. |
| `writeByte` / `readByte` | 1 | Đọc dưới dạng `byte` có dấu (-128..127); `readUnsignedByte` cho 0..255. |
| `writeShort` / `readShort` | 2 | `short` có dấu; `readUnsignedShort` cho 0..65535. |
| `writeChar` / `readChar` | 2 | Một **UTF-16 code unit**, không nhất thiết là cả ký tự Unicode nếu là surrogate pair. |
| `writeInt` / `readInt` | 4 | `int` có dấu, big-endian. |
| `writeLong` / `readLong` | 8 | `long` có dấu, big-endian. |
| `writeFloat` / `readFloat` | 4 | Biểu diễn bit IEEE 754, có thể có `NaN`/vô cực. |
| `writeDouble` / `readDouble` | 8 | Biểu diễn bit IEEE 754, chú ý sai số khi dùng cho tiền. |
| `writeUTF` / `readUTF` | Biến đổi | Chuỗi dạng **modified UTF-8**, có tiền tố độ dài 2 byte không dấu. |

Ví dụ `writeInt(0x01020304)` tạo bốn byte theo đúng thứ tự `01 02 03 04`. Nếu đọc lại bằng `readInt()`, ta nhận `0x01020304`. Nhưng nếu đọc bằng `readShort()` rồi `readInt()`, con trỏ đọc lệch so với schema; những trường tiếp theo sẽ bị giải nghĩa sai hoặc ném `EOFException`.

Các quy tắc có tác dụng ở **mọi** hiện thực DataInput/DataOutput đúng chuẩn, kể cả `RandomAccessFile`. Không được tự suy rằng thứ tự byte phụ thuộc CPU đang chạy. Nếu tương tác với một format little-endian, phải sử dụng bộ đọc/ghi được cấu hình tương ứng (chẳng hạn `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)`) hoặc chuyển byte có chủ đích; các phương thức `readInt`/`writeInt` của hợp đồng DataInput/DataOutput không có tùy chọn little-endian.

## 3. Ví dụ hoàn chỉnh: file bản ghi cố định và cập nhật bằng seek

Giả sử lưu điểm của thành viên. Mỗi bản ghi gồm:

- `id`: `int` = 4 byte.
- `points`: `long` = 8 byte.
- `active`: `boolean` = 1 byte.

Tổng **13 byte/bản ghi**, không có padding. File bắt đầu bằng header gồm `magic`, `version` và `count`, mỗi trường `int` (tổng 12 byte).

```text
Offset (byte)   Nội dung                         Độ dài
0..3            magic = 0x44494F31 ("DIO1")       4
4..7            version = 1                      4
8..11           count = 3                        4
12..24          record[0]                        13
25..37          record[1]                        13
38..50          record[2]                        13

Vị trí record[i] = 12 + i * 13
Trong record[i]: id ở +0, points ở +4, active ở +12
```

Mục tiêu: tạo file tuần tự bằng `DataOutputStream`, nhảy thẳng đến bản ghi thứ hai để cộng 500 điểm bằng `RandomAccessFile`, rồi đọc toàn bộ bằng `DataInputStream`. Ví dụ sử dụng Java 17+ và tạo file tạm, cuối cùng tự dọn dẹp.

Lưu thành **`DataIoRandomAccessDemo.java`**:

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInput;
import java.io.DataInputStream;
import java.io.DataOutput;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;

public class DataIoRandomAccessDemo {
    private static final int MAGIC = 0x44494F31; // ASCII "DIO1"
    private static final int VERSION = 1;
    private static final int COUNT = 3;
    private static final int HEADER_BYTES = 3 * Integer.BYTES;
    private static final int RECORD_BYTES =
            Integer.BYTES + Long.BYTES + 1;

    private record Member(int id, long points, boolean active) {}

    private static void writeMember(DataOutput out, Member m)
            throws IOException {
        out.writeInt(m.id());
        out.writeLong(m.points());
        out.writeBoolean(m.active());
    }

    private static Member readMember(DataInput in) throws IOException {
        int id = in.readInt();
        long points = in.readLong();
        boolean active = in.readBoolean();
        return new Member(id, points, active);
    }

    private static long offsetOf(int index) {
        if (index < 0 || index >= COUNT) {
            throw new IndexOutOfBoundsException("index=" + index);
        }
        return HEADER_BYTES + (long) index * RECORD_BYTES;
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("data-io-", ".bin");
        try {
            // Lần 1: ghi tuần tự file mới qua DataOutputStream.
            try (DataOutputStream out = new DataOutputStream(
                    new BufferedOutputStream(Files.newOutputStream(file)))) {
                out.writeInt(MAGIC);
                out.writeInt(VERSION);
                out.writeInt(COUNT);
                writeMember(out, new Member(101, 1200, true));
                writeMember(out, new Member(102, 2250, false));
                writeMember(out, new Member(103, 900, true));
            }

            // Lần 2: truy cập trực tiếp record[1] nhờ RandomAccessFile.
            try (RandomAccessFile raf =
                    new RandomAccessFile(file.toFile(), "rw")) {
                long second = offsetOf(1); // byte 25
                raf.seek(second);
                Member before = readMember(raf);
                if (before.id() != 102) {
                    throw new IOException("Sai bản ghi tại byte " + second);
                }

                // Chỉ ghi đè 8 byte của trường points.
                raf.seek(second + Integer.BYTES);
                raf.writeLong(before.points() + 500);
            }

            // Lần 3: đọc tuần tự bằng DataInputStream.
            try (DataInputStream in = new DataInputStream(
                    new BufferedInputStream(Files.newInputStream(file)))) {
                int magic = in.readInt();
                int version = in.readInt();
                int count = in.readInt();

                if (magic != MAGIC || version != VERSION ||
                        count != COUNT) {
                    throw new IOException("Header không hợp lệ");
                }

                System.out.printf(
                        "magic=%08X version=%d count=%d%n",
                        magic, version, count);

                for (int i = 0; i < count; i++) {
                    Member member = readMember(in);
                    System.out.printf(
                            "id=%d points=%d active=%b%n",
                            member.id(), member.points(), member.active());
                }

                System.out.println("EOF after records: " +
                        (in.read() == -1));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac DataIoRandomAccessDemo.java
java DataIoRandomAccessDemo
```

Stdout mong đợi (không phụ thuộc đường dẫn của tệp tạm):

```text
magic=44494F31 version=1 count=3
id=101 points=1200 active=true
id=102 points=2750 active=false
id=103 points=900 active=true
EOF after records: true
```

**Vì sao mã được chia làm ba phiên?**

1. Khi ghi, `DataOutputStream` cung cấp các phương thức `writeInt`, `writeLong`, `writeBoolean` nhưng chỉ tiến về phía trước trong `OutputStream`. Đóng stream trước khi mở file để sửa bảo đảm buffer được flush và giải phóng.
2. `RandomAccessFile(file.toFile(), "rw")` mở file có quyền đọc và ghi, đồng thời thực thi cả `DataInput` và `DataOutput`. `seek(25)` đặt con trỏ ngay đầu bản ghi thứ hai. Sau `readMember`, con trỏ đi qua 13 byte; `seek(25 + 4)` quay về đúng byte đầu của `points`. `writeLong` ghi đè đúng tám byte, giữ nguyên `id` và `active`.
3. `DataInputStream` đọc header rồi đúng `count` bản ghi theo **cùng thứ tự và kiểu** đã ghi. `in.read() == -1` xác nhận stream đã hết sau các bản ghi dự kiến, không còn byte dư.
4. Hai helper nhận `DataOutput` và `DataInput` thay vì loại stream cụ thể, nên hoạt động được với cả stream tuần tự và `RandomAccessFile`.

Mã mẫu dùng `long` cho `points`. Nếu biểu diễn giá trị tiền, hãy lưu số đơn vị nhỏ nhất bằng `long` kèm quy ước về đơn vị/scale, hoặc sử dụng một định dạng `BigDecimal` được mô tả rõ; không nên dùng `double` để kỳ vọng tính toán thập phân chính xác.

## 4. RandomAccessFile và vị trí con trỏ

`RandomAccessFile` có các chế độ mở phổ biến:

- `"r"`: chỉ đọc, file phải tồn tại; gọi phương thức ghi sẽ thất bại.
- `"rw"`: đọc và ghi; có thể tạo file nếu chưa có. Việc tạo file không tự bảo đảm schema hợp lệ.
- `"rws"` và `"rwd"`: yêu cầu đồng bộ hóa cập nhật tương ứng, chi phí có thể cao hơn; semantics và bảo đảm thực tế còn phụ thuộc hệ điều hành/filesystem.

Các phương thức liên quan:

| Phương thức | Ý nghĩa |
| --- | --- |
| `seek(long pos)` | Đặt vị trí byte tiếp theo sẽ đọc/ghi, bắt đầu từ 0; vị trí âm không hợp lệ. |
| `getFilePointer()` | Lấy vị trí byte hiện tại. |
| `length()` | Lấy kích thước file tính bằng byte. |
| `setLength(long newLength)` | Cắt bớt hoặc mở rộng file; mở rộng không mặc định tạo ra dữ liệu bản ghi hợp lệ. |
| `readInt()`/`writeInt(int)` | Đọc/ghi 4 byte tại con trỏ, rồi dịch vị trí 4 byte. |
| `readFully(byte[])` | Đọc đúng số byte của mảng hoặc ném lỗi khi kết thúc sớm. |

Cần nhớ:

- `seek` đến vị trí phía sau EOF **không tự thêm dữ liệu**; ghi tại đó có thể làm file dài hơn và để khoảng trống chưa có nội dung bản ghi hợp lệ.
- `RandomAccessFile` dùng file thông thường và nhận đối số `File` hoặc đường dẫn hệ điều hành; khác với API `Files.newByteChannel(Path, ...)` có thể làm việc với provider NIO khác.
- Không đồng thời vừa sửa bằng `RandomAccessFile` vừa đọc qua `BufferedInputStream` cũ: buffer có thể chứa dữ liệu từ trước khi cập nhật. Đóng/đồng bộ phiên thao tác rồi mở reader mới khi cần kết quả nhất quán.
- Bản ghi kích thước cố định cho phép tính offset trực tiếp. Nếu chứa trường dài biến đổi, ví dụ `writeUTF`, vị trí của những bản ghi sau **không còn là** `headerSize + index * recordSize`. Khi đó cần bảng chỉ mục offset, cấu trúc có độ dài hoặc giải pháp lưu trữ khác.

Khi tính offset từ chỉ mục và kích thước không tin cậy, kiểm tra biên và dùng `Math.multiplyExact`/`Math.addExact` (với kiểu `long`) để phát hiện tràn số. Xác minh `offset + recordSize <= file.length()` trước khi đọc nếu muốn trả thông báo lỗi rõ ràng.

## 5. Đọc tuần tự: các phương thức bổ trợ của DataInput

Ngoài `readInt` và `readLong`, `DataInput` có các phương thức xử lý byte hữu ích:

- **`readFully(byte[] dst)`** đọc đủ `dst.length` byte hoặc ném `EOFException`. `readFully(dst, off, len)` dùng một đoạn mảng. Hữu ích với payload có độ dài biết trước.
- **`readUnsignedByte()`**, **`readUnsignedShort()`** trả về `int` không dấu theo số byte được ghi. Cùng dữ liệu `FF` được `readByte()` diễn giải là -1 nhưng `readUnsignedByte()` là 255.
- **`skipBytes(int n)`** có thể bỏ qua **ít hơn n byte** (đặc biệt khi gần EOF); kiểm tra giá trị trả về, không coi đó là một phép seek chắc chắn.
- **`readUTF()`** đọc chuỗi mã hóa theo quy ước `writeUTF()`; không dùng để đọc mọi chuỗi UTF-8 tùy ý.
- **`readLine()`** của `DataInput` đã bị deprecated; với văn bản hãy dùng `BufferedReader` có charset cụ thể.

Phân biệt API `InputStream.read(byte[])` (có thể trả về **ít hơn** số byte yêu cầu ngay cả khi chưa EOF) với `DataInput.readFully` (cố lấy đủ hoặc thất bại). Ví dụ khung nhị phân có 4 byte length + payload:

```java
int length = in.readInt();
if (length < 0 || length > 1_048_576) {
    throw new IOException("Kích thước payload không hợp lệ: " + length);
}
byte[] payload = new byte[length];
in.readFully(payload);
```

Đây là **snippet**, giả định `in` là một `DataInput` đã mở và `IOException` được xử lý/truyền ra ngoài. Giới hạn 1 MiB chỉ là ví dụ; trong ứng dụng thực tế chọn hạn mức theo hợp đồng và tài nguyên. Nếu payload lớn, không tạo mảng theo mọi giá trị độ dài mà nguồn bên ngoài khai báo: đọc theo chunk có quota và kiểm tra bytes thực tế.

## 6. Chuỗi: writeUTF không đồng nghĩa UTF-8 thông thường

`DataOutput.writeUTF(String)` ghi tiền tố **2 byte không dấu** chứa *số byte của phần dữ liệu đã mã hóa*, sau đó ghi chuỗi theo **modified UTF-8**. `DataInput.readUTF()` đọc đúng định dạng này. Khác biệt đáng chú ý:

- Byte độ dài là số byte của bản mã, **không phải số ký tự Java**.
- `writeUTF` giới hạn phần đã mã hóa tối đa 65.535 byte và có thể ném `UTFDataFormatException` khi vượt quá.
- Modified UTF-8 xử lý mã null (`\u0000`) và surrogate UTF-16 khác UTF-8 chuẩn; chuỗi đọc/ghi bằng `writeUTF/readUTF` không mặc định tương thích với một parser UTF-8 của ngôn ngữ khác.
- `writeChars(String)` ghi mỗi UTF-16 code unit thành 2 byte và **không** tự ghi độ dài; `writeBytes(String)` chỉ ghi 8 bit thấp của từng char, có thể làm mất thông tin Unicode. Tránh dùng hai phương thức này cho văn bản trao đổi chung.

Một ví dụ đối ứng hợp lệ với biến `out` kiểu `DataOutput` và `in` kiểu `DataInput` đang trỏ đúng vị trí trong cùng format:

```java
out.writeUTF("Tiếng Việt");   // Ghi modified UTF-8 kèm length.
String text = in.readUTF();  // Đọc đúng format đó.
```

Hai dòng là **minh họa riêng**, không phải đoạn mã chạy tuần tự trên cùng một object. Không gọi `readUTF` trên dữ liệu được ghi bằng `Files.writeString(..., UTF_8)` vì luồng đó không có length prefix và dùng UTF-8 chuẩn.

Nếu cần format để nhiều ngôn ngữ đọc được, có thể định nghĩa **UTF-8 chuẩn + độ dài 4 byte big-endian**:

```java
// Phía ghi (out: DataOutput, text: String)
byte[] bytes = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
out.writeInt(bytes.length);
out.write(bytes);

// Phía đọc (in: DataInput)
int len = in.readInt();
if (len < 0 || len > 1_048_576) {
    throw new IOException("Độ dài chuỗi không hợp lệ");
}
byte[] encoded = new byte[len];
in.readFully(encoded);
String decoded = new String(
        encoded, java.nio.charset.StandardCharsets.UTF_8);
```

Đây là hai đoạn độc lập trong cùng schema, dùng biến được khai báo bên ngoài. Bên đọc phải tuân thủ cùng thứ tự byte, charset và giới hạn. Hàm khởi tạo `new String(bytes, UTF_8)` có chính sách thay thế chuỗi byte không hợp lệ; nếu yêu cầu **từ chối** UTF-8 lỗi, dùng `CharsetDecoder` với `CodingErrorAction.REPORT`. Khi dữ liệu quan trọng, xác định thêm chuẩn hóa Unicode, trường rỗng và cách biểu diễn `null` trong schema.

## 7. Thiết kế một file nhị phân an toàn và có thể nâng cấp

Bản ghi là giao ước giữa chương trình ghi và đọc. Một file hợp lý thường có:

1. **Magic number**: xác nhận đúng loại file trước khi đọc các trường khác; ví dụ bốn byte của `0x44494F31`.
2. **Version**: phân biệt các phiên bản layout. Nếu version chưa hỗ trợ, từ chối hoặc chuyển đổi theo quy tắc rõ ràng; không đoán schema mới.
3. **Count/length**: cho biết số bản ghi hoặc kích thước payload; phải kiểm tra giá trị hợp lý trước khi lặp hay cấp phát.
4. **Record layout**: xác định kiểu, thứ tự, số byte, đơn vị, encoding, giá trị đặc biệt và có padding hay không.
5. **Integrity policy**: khi cần, dùng checksum/hash, ghi file tạm và thay thế có kiểm soát; header và count một mình không chứng minh dữ liệu không hỏng.

Ví dụ ở phần 3 có thể xác minh với file chuẩn:

```text
expectedLength = 12 + 3 * 13 = 51 byte
```

Nếu kích thước không khớp, có thể có truncation, byte thừa hoặc một phiên bản layout khác. Với file có payload biến độ dài, cần kiểm tra theo từng trường thay vì công thức cố định. Không chỉ dựa vào `count` khi đầu vào không tin cậy: số lượng khổng lồ có thể gây vòng lặp kéo dài, lỗi I/O hoặc cạn tài nguyên.

**Truy cập ngẫu nhiên có thể cập nhật tại chỗ khi kích thước trường không thay đổi.** Ghi `long` mới vào 8 byte cũ là phù hợp; chèn một chuỗi dài hơn vào giữa file sẽ đẩy các byte phía sau, nên `RandomAccessFile` không tự quản lý việc dịch dữ liệu hay tái xây chỉ mục. Nếu cần bản ghi dài biến đổi hoặc tra cứu phức tạp, cân nhắc cấu trúc indexed/append-only hoặc database tùy yêu cầu.

## 8. Lỗi phổ biến và nguyên nhân

| Hiện tượng | Nguyên nhân | Cách phòng tránh |
| --- | --- | --- |
| `EOFException` trong `readInt/readLong/readFully` | File dừng trước khi đủ số byte của trường. | Xác minh header, count/length và biên file; xử lý dữ liệu hỏng. |
| Dữ liệu đọc thành giá trị vô lý | Sai thứ tự trường, sai signed/unsigned, nhầm byte order. | Ghi rõ schema; đọc đúng cùng thứ tự; test bằng byte fixture. |
| `UTFDataFormatException` | Chuỗi modified UTF-8 hỏng hoặc quá dài lúc `writeUTF`. | Dùng đúng cặp API; giới hạn encoded bytes; chọn format khác khi cần. |
| Sai offset khi seek | Tính index theo số phần tử mà bỏ qua header hoặc nhầm kích thước primitive. | Dùng hằng số kích thước và công thức với `long`; kiểm tra biên. |
| File bị truncate ngoài ý muốn | Mở `Files.newOutputStream(path)` mặc định để ghi lại file hiện có. | Phân biệt tạo mới, append và update; giữ chính sách ghi đè rõ ràng. |
| Đọc thấy dữ liệu cũ | Stream có buffer chưa flush hoặc reader cũ còn buffer. | Hoàn thành/đóng writer trước khi đọc lại; không chia sẻ hỗn hợp buffer. |
| File hỏng sau ghi giữa chừng | Cập nhật nhiều trường bị gián đoạn, thao tác không transaction. | Ghi bản mới ra file tạm, kiểm tra, thay thế có chính sách và backup. |
| Bộ nhớ tăng đột biến | Tin trường length/count từ input rồi cấp phát mảng lớn. | Đặt quota và phát hiện overflow; đọc streaming nếu dữ liệu lớn. |

Các phương thức đọc nhiều byte được mô tả bởi `DataInput` ném `EOFException` nếu chưa đủ byte. Ngược lại `InputStream.read()` trả `-1` khi EOF thông thường. **Đừng dùng bắt `EOFException` thay cho schema có count/length** nếu file đã định nghĩa số bản ghi; EOF bất ngờ thường là dấu hiệu dữ liệu thiếu hoặc hỏng.

`DataInputStream` và `DataOutputStream` được đóng qua `try-with-resources`. Khi bọc `BufferedInputStream/BufferedOutputStream`, đóng lớp ngoài cũng đóng stream phía dưới. `flush()` có thể đẩy dữ liệu trong buffer, nhưng **không đồng nghĩa** dữ liệu đã được lưu bền vững trên thiết bị. Tương tự, `RandomAccessFile` đóng tài nguyên nhưng không biến chuỗi cập nhật thành transaction.

## 9. Khi nào nên chọn giải pháp khác?

- **Stream tuần tự + DataInput/DataOutput:** tốt cho protocol nhị phân nhỏ, file có schema rõ, quá trình ghi một chiều và đọc một chiều.
- **RandomAccessFile:** phù hợp khi file nằm trên OS, có bản ghi kích thước cố định, cần đọc/ghi tại offset cụ thể và có thể kiểm soát đồng bộ truy cập.
- **`FileChannel` hoặc `SeekableByteChannel`:** thích hợp khi cần thao tác ở vị trí byte, buffer, khả năng làm việc theo NIO hoặc I/O dung lượng lớn; `ByteBuffer` cho phép chọn thứ tự byte, khác hợp đồng DataInput/DataOutput.
- **`ObjectOutputStream/ObjectInputStream`:** phục vụ Java object serialization, là cơ chế khác và có vấn đề versioning, interoperability, rủi ro deserialization riêng; không dùng thay thế tùy tiện cho schema nhị phân cố định.
- **Database hoặc format có schema:** phù hợp hơn khi có bản ghi biến độ dài, nhiều writer, truy vấn/chỉ mục, transaction hoặc nhu cầu nâng cấp lâu dài.

**Không dùng Java serialization làm mặc định** chỉ vì cần ghi một vài `int` và `long`. Khi tự thiết kế format, cũng cần tự quản lý compatibility, lỗi và integrity; lựa chọn phù hợp phụ thuộc loại dữ liệu và thời gian bảo trì.

## 10. Bài tập luyện tập

**Bài tập 1 — Tính offset và quan sát byte.** Với layout ví dụ, hãy xác định byte đầu của `record[2]` và byte đầu trường `active` của nó. Đáp án: `12 + 2 * 13 = 38` và `38 + 4 + 8 = 50`. Thử `raf.seek(50); raf.readBoolean()` trên file trước khi xóa để kiểm tra giá trị `true`.

**Bài tập 2 — Cập nhật an toàn.** Bổ sung hàm `updatePoints(Path file, int index, long increment)`. Mở file dạng `"rw"`, kiểm tra magic/version/count, offset và chiều dài file, sau đó dùng `Math.addExact` cho điểm mới rồi chỉ ghi 8 byte tương ứng. Giải thích vì sao nhiều writer vẫn phải được đồng bộ.

**Bài tập 3 — Phát hiện file hỏng.** Sau khi tạo file, dùng `setLength(30)` trên `RandomAccessFile` để cố tình cắt bớt các bản ghi. Chạy chương trình đọc và kiểm tra khi nào phát sinh `EOFException`. Sau đó bổ sung kiểm tra `file.length() == HEADER_BYTES + count * RECORD_BYTES` để phát hiện sai kích thước sớm hơn.

**Bài tập 4 — Chuỗi biến độ dài.** Viết thêm `writeUTF` ở cuối một record và quan sát vì sao `RECORD_BYTES` không còn cố định. Đề xuất bảng index offset hoặc dùng length-prefix để truy cập đúng bản ghi có kích thước biến thiên.

**Tự kiểm tra:** Vì sao `DataInput` không tự lưu kiểu dữ liệu? Khi nào `readUnsignedByte` phù hợp hơn `readByte`? Vì sao `readFully` hữu ích hơn `read` cho khung nhị phân? Vì sao `writeUTF` không tương đương UTF-8 chuẩn? Và vì sao `seek` chỉ an toàn khi đã xác định rõ vị trí, kích thước và schema?

Các nguyên tắc cần mang sang dự án thật là: **thiết kế format trước, giữ thứ tự đọc/ghi đối xứng, xác minh header/length, dùng byte offset chính xác và quản lý tài nguyên/vòng đời file**. `DataInput/DataOutput` đảm bảo cách chuyển primitive sang byte; tính toàn vẹn, đồng bộ và compatibility vẫn là trách nhiệm của chương trình.

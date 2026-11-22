# Thứ tự ghi phải tương ứng với thứ tự đọc trong Java I/O nhị phân

## 1. Nguyên tắc cốt lõi: dữ liệu nhị phân không tự mang tên và kiểu trường

Trong I/O nhị phân, `OutputStream` ghi các **byte liên tiếp**. Các byte không tự cho biết đoạn nào là số nguyên, số thực, chuỗi, số phần tử hoặc điểm kết thúc một bản ghi. Phía nhận phải biết trước **giao thức/định dạng**: các trường có thứ tự ra sao, mỗi trường dùng bao nhiêu byte, kiểu mã hóa gì và được giới hạn như thế nào.

Ví dụ nếu phía ghi làm:

```java
out.writeInt(42);
out.writeBoolean(true);
out.writeDouble(3.5);
```

thì phía đọc tương ứng phải làm:

```java
int id = in.readInt();
boolean active = in.readBoolean();
double score = in.readDouble();
```

Hai đoạn trên chỉ minh họa; `out` phải là `DataOutputStream`, `in` là `DataInputStream` cùng đọc đúng luồng byte đã ghi, và cần xử lý `IOException`. Đọc `double` trước `int` hoặc dùng `readShort()` thay `readInt()` sẽ tiêu thụ sai số byte; từ đó các trường phía sau có thể bị hiểu sai hoặc gặp EOF.

**Quy tắc:** Với mỗi trường được ghi, bên đọc phải dùng phương thức giải mã **tương ứng về định dạng**, theo **đúng thứ tự**, đồng thời tuân thủ mọi quy ước độ dài, endian, charset, phiên bản và ranh giới bản ghi.

## 2. Vì sao thứ tự quan trọng?

Một luồng byte thông thường chỉ có vị trí đọc hiện tại (cursor). Mỗi lần đọc:

1. Lấy một số byte từ vị trí hiện tại.
2. Diễn giải số byte đó theo phương thức đã gọi.
3. Tiến cursor đúng số byte phương thức tiêu thụ.

`readInt()` cần 4 byte; `readShort()` cần 2 byte; `readLong()` cần 8 byte. Nếu ghi một `int` 4 byte nhưng lại đọc một `short` 2 byte, còn **2 byte của trường cũ** nằm phía trước trường tiếp theo. Tất cả những lần đọc sau có thể bị lệch.

Hình dung định dạng có ba trường:

```text
Ghi:  [int id: 4 byte][boolean active: 1 byte][double score: 8 byte]
        └── 4 byte ──┘ └─ 1 byte ─┘ └────── 8 byte ──────┘

Đọc đúng:
       readInt()       readBoolean()           readDouble()

Đọc sai:
       readShort()     readBoolean()           readDouble()
       └─ chỉ 2 byte ─┘
                        ↑ cursor giờ nằm giữa trường id
```

Dòng dữ liệu ở đây mô tả một chuỗi byte thuần. Không có dấu phân cách ngầm giữa các lời gọi `writeInt`/`writeDouble`; việc gọi `flush()` hoặc `close()` không tự thêm tên trường.

Đặc biệt, **giá trị đôi khi nhìn có vẻ hợp lệ dù đọc sai**: 2 hoặc 4 byte lệch nhau vẫn tạo được một số nguyên Java bất kỳ. Chỉ dựa vào “không ném ngoại lệ” là chưa đủ để xác nhận dữ liệu đã được giải mã đúng.

## 3. Cặp API ghi/đọc tương ứng của `DataOutputStream` và `DataInputStream`

`java.io.DataOutputStream`/`DataInputStream` cung cấp cách biểu diễn một số kiểu nguyên thủy theo hợp đồng **binary** của Java:

| Ghi | Đọc phù hợp | Số byte / cách diễn giải |
| --- | --- | --- |
| `writeBoolean(boolean)` | `readBoolean()` | 1 byte; ghi `1` cho `true`, `0` cho `false` |
| `writeByte(int)` | `readByte()` hoặc `readUnsignedByte()` | 1 byte; đọc signed `-128..127` hoặc unsigned `0..255` |
| `writeShort(int)` | `readShort()` hoặc `readUnsignedShort()` | 2 byte, big-endian; signed/unsigned |
| `writeChar(int)` | `readChar()` | 2 byte, một UTF-16 code unit, big-endian |
| `writeInt(int)` | `readInt()` | 4 byte, big-endian, số nguyên signed |
| `writeLong(long)` | `readLong()` | 8 byte, big-endian, số nguyên signed |
| `writeFloat(float)` | `readFloat()` | 4 byte, bit IEEE 754 theo đặc tả của DataOutput |
| `writeDouble(double)` | `readDouble()` | 8 byte, bit IEEE 754 theo đặc tả của DataOutput |
| `writeUTF(String)` | `readUTF()` | 2 byte ghi **độ dài số byte**, rồi nội dung **modified UTF-8** |
| `write(byte[])` | `readFully(byte[])` | Đúng số byte trong mảng; phải biết trước độ dài |

Các phương thức `writeByte`/`writeShort` chỉ ghi những byte thấp của số được truyền vào, không phải bất kỳ giá trị `int` nào cũng được giữ nguyên khi thu hẹp. `readUnsignedByte`/`readUnsignedShort` dùng khi giao thức định nghĩa trường là không dấu; **cùng một byte** có thể được diễn giải khác nhau tùy API đọc.

Đối với các kiểu nhiều byte của `DataOutputStream`, thứ tự là **big-endian** (byte có trọng số lớn nhất trước). `DataInputStream` đọc theo chính quy ước đó. Nếu tương tác với phần mềm dùng little-endian hoặc cấu trúc tùy chỉnh, phải thực hiện đúng đặc tả của bên kia, ví dụ qua `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` hoặc API phù hợp; không mặc định mọi định dạng nhị phân của mọi hệ thống giống Data Streams.

### Phân biệt `read()`, `readFully()` và `readInt()`

- `InputStream.read()` lấy **một byte** và trả số nguyên `0..255` hoặc `-1` khi EOF.
- `InputStream.read(byte[])` được phép trả **ít byte hơn kích thước mảng** ngay cả khi chưa EOF. Nó không bảo đảm một lần đọc sẽ đầy mảng.
- `DataInputStream.readFully(byte[])` cố đọc đủ toàn bộ số byte cần thiết; nếu EOF xảy ra trước thì ném `EOFException`.
- `DataInputStream.readInt()` đọc chính xác 4 byte và diễn giải thành một `int`; không giống gọi `read()` rồi mặc định đã có đủ dữ liệu của một trường.

Một lệnh đọc thành công chỉ có nghĩa là phương thức ấy đã đọc theo **quy tắc riêng của nó**; chương trình vẫn chịu trách nhiệm bảo đảm quy tắc ấy khớp schema của tệp.

## 4. Ví dụ chạy được: ghi và đọc đúng thứ tự

Tạo file **`BinaryWriteReadOrderDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.Locale;

public class BinaryWriteReadOrderDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(42);
            out.writeBoolean(true);
            out.writeDouble(3.5);
            out.writeUTF("Cà phê");
        }

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            int id = in.readInt();
            boolean active = in.readBoolean();
            double score = in.readDouble();
            String name = in.readUTF();

            System.out.println("id=" + id);
            System.out.println("active=" + active);
            System.out.printf(Locale.ROOT, "score=%.1f%n", score);
            System.out.println("name=" + name);
            System.out.println("remaining=" + in.available());
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 BinaryWriteReadOrderDemo.java
java BinaryWriteReadOrderDemo
```

Đầu ra:

```text
id=42
active=true
score=3.5
name=Cà phê
remaining=0
```

Các điểm cần hiểu:

1. `DataOutputStream` ghi lần lượt **`int` → `boolean` → `double` → chuỗi có tiền tố độ dài**. Không thêm tên trường hoặc dấu ngăn cách.
2. `DataInputStream` đọc **đúng thứ tự và đúng cặp API**, nên khôi phục được bốn giá trị ban đầu.
3. `writeUTF`/`readUTF` là cặp tương ứng với *modified UTF-8 của Data Streams*, không phải ghi byte UTF-8 thô. Chữ có dấu trong ví dụ vẫn round-trip đúng.
4. `DataOutputStream` được đóng trước khi `toByteArray()` được gọi để mọi tầng writer hoàn tất. Ở ví dụ chỉ có bộ đệm trong RAM, nhưng nguyên tắc hoàn tất/đóng quan trọng khi kết hợp file hoặc các wrapper khác.
5. `available() == 0` ở **`ByteArrayInputStream` cụ thể này** cho thấy không còn byte trong mảng. **Không dùng `available() == 0` làm phép kiểm tra EOF tổng quát cho mọi `InputStream`**, nhất là socket hay stream phức tạp.

Đây là ví dụ nhị phân thuần trong RAM; nếu đổi nguồn/đích thành file, thứ tự các lệnh vẫn phải được giữ nguyên.

## 5. Ví dụ đọc sai thứ tự: chương trình vẫn chạy nhưng dữ liệu sai

Một trường `int` gồm 4 byte và một trường `short` gồm 2 byte. Cho phép minh họa chính xác mà không phải dựa vào hành vi lỗi ngẫu nhiên.

Tạo file **`WrongBinaryOrderDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.Locale;

public class WrongBinaryOrderDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(0x01020304);
            out.writeShort(0x0506);
        }

        byte[] content = bytes.toByteArray();

        try (DataInputStream right = new DataInputStream(
                new ByteArrayInputStream(content))) {
            System.out.printf(Locale.ROOT, "correct=%08X,%04X%n",
                    right.readInt(), right.readUnsignedShort());
        }

        try (DataInputStream wrong = new DataInputStream(
                new ByteArrayInputStream(content))) {
            System.out.printf(Locale.ROOT, "wrong=%04X,%08X%n",
                    wrong.readUnsignedShort(), wrong.readInt());
        }
    }
}
```

Chạy:

```bash
javac WrongBinaryOrderDemo.java
java WrongBinaryOrderDemo
```

Đầu ra:

```text
correct=01020304,0506
wrong=0102,03040506
```

Giải thích theo byte:

```text
Thực tế đã ghi: 01 02 03 04 | 05 06
                 └── int ───┘   short

Đọc đúng:        01 02 03 04 | 05 06
                 readInt        readUnsignedShort

Đọc sai:         01 02 | 03 04 05 06
                 short   int (đã trượt ranh giới)
```

Điều đáng chú ý là cả hai lần đọc sai **đều có đủ byte để hoàn thành**, nên không nhất thiết có ngoại lệ. Nếu muốn phân tích lỗi, kiểm tra schema và offset, hoặc so byte ở dạng hex; không chỉ bắt `EOFException` là đủ.

**Lưu ý:** Nếu số byte còn lại không đủ cho `readInt()`, Java sẽ ném `EOFException`. Nếu còn đủ nhưng không đúng trường, Java vẫn tạo ra một giá trị từ những byte đó. Hai tình huống này cần được chẩn đoán khác nhau.

## 6. Trường có độ dài thay đổi: phải thống nhất quy tắc “framing”

`int`, `long` và `double` có độ dài cố định, nhưng `String` và dữ liệu mảng thường **không có độ dài cố định**. Nếu ghi nhiều chuỗi liên tiếp như byte UTF-8 thô mà không có thông tin ranh giới, bên đọc không biết byte của chuỗi thứ nhất dừng ở đâu.

Một cách phổ biến là **length prefix**: ghi trước độ dài dưới dạng một `int`, rồi mới ghi đúng số byte. Phía đọc cần gọi `readInt()` để nhận chiều dài, xác thực chiều dài, rồi `readFully(...)` để lấy chính xác payload.

Định dạng hai bản ghi ví dụ:

```text
[int count]
    [int id][int nameByteLength][nameUtf8Bytes]
    [int id][int nameByteLength][nameUtf8Bytes]
```

Ở đây độ dài chuỗi được tính bằng **số byte UTF-8**, không phải `String.length()` (số đơn vị mã UTF-16). Ví dụ tên chứa dấu tiếng Việt có thể chiếm nhiều byte hơn số ký tự hiển thị.

Ví dụ Java 17+ chạy được **`LengthPrefixedRecordsDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class LengthPrefixedRecordsDemo {
    private static void writeRecord(
            DataOutputStream out, int id, String name) throws IOException {
        byte[] utf8 = name.getBytes(StandardCharsets.UTF_8);
        out.writeInt(id);
        out.writeInt(utf8.length);
        out.write(utf8);
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(2); // số bản ghi
            writeRecord(out, 7, "An");
            writeRecord(out, 8, "Bình");
        }

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            int count = in.readInt();
            if (count < 0 || count > 100) {
                throw new IOException("Invalid record count: " + count);
            }

            for (int i = 0; i < count; i++) {
                int id = in.readInt();
                int length = in.readInt();

                if (length < 0 || length > 1024) {
                    throw new IOException("Invalid name length: " + length);
                }

                byte[] payload = new byte[length];
                in.readFully(payload);
                String name = new String(payload, StandardCharsets.UTF_8);

                System.out.println("id=" + id + ", name=" + name);
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 LengthPrefixedRecordsDemo.java
java LengthPrefixedRecordsDemo
```

Đầu ra:

```text
id=7, name=An
id=8, name=Bình
```

Các bước tương ứng rất rõ:

| Thứ tự | Ghi | Đọc |
| ---: | --- | --- |
| 1 | `out.writeInt(2)` | `int count = in.readInt()` |
| 2 | `out.writeInt(id)` | `int id = in.readInt()` |
| 3 | `out.writeInt(utf8.length)` | `int length = in.readInt()` |
| 4 | `out.write(utf8)` | `in.readFully(payload)` |
| 5 | Lặp lại bước 2–4 cho record tiếp theo | Lặp đúng `count` record |

Nếu bên ghi dùng byte UTF-8 nhưng bên đọc lại gọi `readUTF()`, dữ liệu không tương thích: `readUTF()` kỳ vọng **prefix 2 byte và modified UTF-8**, trong khi ví dụ dùng **prefix 4 byte và UTF-8 chuẩn**. Cùng nói là “chuỗi” không đủ; phải thống nhất **từng byte của định dạng chuỗi**.

**Bảo vệ khi đọc dữ liệu không tin cậy:** Kiểm tra `count` và `length` trước khi cấp phát `byte[]`. Giới hạn tối đa phụ thuộc nghiệp vụ; `1024` trong ví dụ chỉ là giới hạn giả định. Đừng cho dữ liệu đầu vào tự cấp phát mảng hàng gigabyte hoặc lặp vô hạn bằng cách khai số bản ghi cực lớn.

## 7. EOF, bản ghi cắt cụt và việc đọc có đủ byte hay không

`EOFException` thường báo rằng một phương thức như `readInt()`, `readLong()` hoặc `readFully()` không lấy đủ byte cần thiết. Với giao thức cố định, điều này thường chỉ ra tệp/luồng bị **cắt cụt**, quá trình truyền chưa đủ, hoặc schema hai phía không đồng nhất.

Phân biệt:

- **Kết thúc hợp lệ:** đã đọc đủ số bản ghi được khai báo, hoặc gặp marker kết thúc được giao thức quy định.
- **Kết thúc bất ngờ:** schema đòi hỏi thêm trường hoặc byte nhưng byte đã hết, dẫn tới `EOFException`.
- **Giá trị sai nhưng không EOF:** đọc lạc ranh giới tạo số vẫn hợp lệ về kiểu Java nhưng không hợp lệ theo nghiệp vụ.
- **Nguồn chưa có dữ liệu ngay:** stream mạng có thể chờ, không có nghĩa là EOF. `available()` không cung cấp ranh giới bản ghi đáng tin cậy.

Không nên dùng `catch (EOFException e) { /* bỏ qua */ }` như một quy tắc chung. Chỉ xem EOF là kết thúc bình thường nếu **định dạng cho phép EOF làm dấu kết thúc** và không có bản ghi nào đang đọc dở. Với số bản ghi/độ dài đã được khai báo, EOF giữa một bản ghi là lỗi.

Nếu định dạng phải phát hiện byte dư ngoài dữ liệu hợp lệ, sau khi đọc đủ record có thể kiểm tra một byte tiếp theo:

```java
int extra = in.read();
if (extra != -1) {
    throw new IOException("Unexpected trailing bytes");
}
```

Đây là **đoạn minh họa** có `DataInputStream in` đã đọc xong phần hợp lệ, cần import `IOException`. Phép đọc có thể chờ với một nguồn mạng còn mở; nó phù hợp khi giao thức/tệp dự kiến đã kết thúc hoặc có cách truyền đạt kết thúc rõ ràng, không nên áp dụng vô điều kiện cho một kết nối streaming dài hạn.

## 8. Chuỗi trong định dạng nhị phân: `writeUTF` không đồng nghĩa UTF-8 thông thường

Java Data Streams có cặp:

```java
out.writeUTF(text);
String restored = in.readUTF();
```

Đây là **đoạn mã minh họa**, cần `out`/`in` tương ứng. `writeUTF` ghi **2 byte độ dài không dấu** (tối đa 65.535 byte payload mã hóa), rồi dữ liệu theo **modified UTF-8**. `readUTF` đọc đúng quy ước này. Với chuỗi được mã hóa quá dài, `writeUTF` có thể ném `UTFDataFormatException`.

Modified UTF-8 của `DataOutputStream` không đồng nhất với UTF-8 chuẩn:

- Ký tự NUL `U+0000` được biểu diễn khác dạng một byte `00` của UTF-8 chuẩn.
- Ký tự Unicode ngoài BMP đi qua các UTF-16 surrogate code unit và có thể dùng **6 byte** trong modified UTF-8, thay vì 4 byte UTF-8 chuẩn.
- Tiền tố độ dài của `writeUTF` chỉ 2 byte; với length prefix tùy chỉnh `writeInt(length)` thì tiền tố dài 4 byte.

Vì vậy trước khi đọc **bất cứ chuỗi nào**, cần trả lời: byte này do `writeUTF` tạo ra, hay là UTF-8/UTF-16/charset khác theo định dạng đã công bố? Không dùng `readUTF()` để đọc dữ liệu do `OutputStreamWriter(UTF_8)` ghi, trừ khi phía ghi đã chủ động xây đúng tiền tố và modified UTF-8.

Tương tự, `writeChars(String)` ghi **mỗi `char` thành 2 byte** theo big-endian, không kèm độ dài. `writeBytes(String)` ghi 8 bit thấp của từng `char` và có thể mất dữ liệu Unicode. Cả hai không tương đương `writeUTF` hoặc mã hóa UTF-8 chuẩn.

## 9. Những quy tắc khác ngoài thứ tự phải được thống nhất

Thứ tự là điều kiện cần, nhưng chưa đủ. Một “hợp đồng dữ liệu” nhị phân nên ghi rõ:

1. **Magic/header:** có hay không chữ ký nhận dạng định dạng; ví dụ 4 byte hằng để tránh đọc nhầm tệp.
2. **Version:** phiên bản schema; bên đọc biết cách diễn giải phần sau theo version nào.
3. **Field order:** trường nào trước, trường nào sau; trường bắt buộc và tùy chọn.
4. **Primitive encoding:** độ rộng, signed/unsigned, endian, biểu diễn boolean và floating point.
5. **String encoding:** UTF-8 chuẩn, modified UTF-8, UTF-16..., và cách giới hạn độ dài.
6. **Framing:** số bản ghi, prefix độ dài, delimiter, sentinel hoặc EOF có ý nghĩa gì.
7. **Bounds và validation:** giới hạn count, length, miền giá trị, checksum nếu cần.
8. **Compatibility:** quy tắc khi thêm trường, bỏ trường hoặc thay đổi kiểu.

### Ví dụ thêm phiên bản vào đầu tệp

Một schema có thể được thiết kế:

```text
[int magic = 0x4A494F31]
[short version = 1]
[int recordCount]
[record 1]
[record 2]
...
```

Phía ghi sẽ gọi `writeInt(magic)` → `writeShort(version)` → `writeInt(recordCount)` → ghi records. Phía đọc phải theo đúng thứ tự `readInt` → `readShort` → `readInt` → đọc records, và kiểm tra giá trị magic/version trước khi đi tiếp. Đây là **sơ đồ định dạng minh họa**, không phải tệp chuẩn chung của Java.

Khi nâng version, không chỉ “ghi thêm một trường cuối” rồi mong reader cũ hiểu được. Nếu reader cũ còn đọc các bản ghi tiếp theo, trường thêm có thể bị xem là phần mở đầu của record kế tiếp. Cần định nghĩa cơ chế tương thích, như header/version, bản ghi có length prefix để bỏ qua trường chưa biết, hoặc định dạng tự mô tả như Protocol Buffers. Không nhầm bản ghi nhị phân tự thiết kế với Java Object Serialization (`ObjectOutputStream`/`ObjectInputStream`), vốn có định dạng và quy tắc riêng.

## 10. Trường hợp nhiều lớp stream, file và buffer

Có thể kết hợp buffer để giảm lệnh I/O vật lý mà **không đổi thứ tự trường**:

```java
try (DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(
                Files.newOutputStream(path)))) {
    out.writeInt(42);
    out.writeLong(123L);
}
```

Đây là **đoạn minh họa**, cần `Path path`, import `java.nio.file.Files`, `java.io.BufferedOutputStream`, `java.io.DataOutputStream` và xử lý `IOException`. `Files.newOutputStream(path)` mặc định có thể **tạo hoặc cắt ngắn tệp**. Đối với dữ liệu quan trọng, chọn đường dẫn/chính sách mở tệp có chủ đích.

Đọc tương ứng:

```java
try (DataInputStream in = new DataInputStream(
        new BufferedInputStream(
                Files.newInputStream(path)))) {
    int id = in.readInt();
    long value = in.readLong();
}
```

Đây là **đoạn minh họa**, cần import các lớp thích hợp và xử lý `IOException`.

Luồng ghi dữ liệu chạy từ ứng dụng qua `DataOutputStream` → `BufferedOutputStream` → đích byte. Bên đọc đi từ nguồn byte → `BufferedInputStream` → `DataInputStream` → ứng dụng. Buffer tăng hiệu quả truyền byte nhưng không tự chèn delimiter hoặc sửa schema.

Với file, hãy đóng `DataOutputStream` để flush bộ đệm theo dây chuyền. Với socket, `flush()` có thể giúp đẩy dữ liệu đang giữ trong buffer, nhưng **không đồng nghĩa phía nhận đã đọc hay xử lý thành công**. Nếu giao thức cần xác nhận, phải thiết kế ACK/response ở lớp ứng dụng.

Không đóng wrapper khi còn cần dùng luồng nền bên dưới; đóng lớp ngoài cùng thường kéo theo đóng các lớp mà nó sở hữu. Thiết kế rõ trách nhiệm đóng của caller/callee.

## 11. Kiểm thử tính tương ứng giữa ghi và đọc

Tốt nhất kiểm tra định dạng nhị phân bằng cả **round-trip** và **golden bytes**.

### Round-trip

Viết một record vào `ByteArrayOutputStream`, đọc bằng `DataInputStream` trên `ByteArrayInputStream` rồi so từng trường. Các ví dụ chạy được ở trên đã dùng kỹ thuật này. Hãy thử thêm:

- Các giá trị biên: `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MAX_VALUE`, số âm, zero, boolean false.
- Chuỗi rỗng, chuỗi có dấu tiếng Việt, emoji và ký tự NUL.
- Mảng byte rỗng, payload lớn hơn kích thước buffer đọc.
- Nhiều bản ghi nối liên tiếp, count đúng và count sai.
- Dữ liệu bị cắt ngay giữa một trường 2/4/8 byte hoặc giữa payload của chuỗi.

### Golden bytes

Kiểm tra chính byte được ghi ra theo định dạng công bố. Ví dụ `writeInt(0x01020304)` phải ghi `01 02 03 04` theo big-endian; `writeShort(0x0506)` tiếp sau phải tạo `05 06`. Golden bytes giúp phát hiện trường hợp cả writer và reader cùng mắc **một lỗi giống nhau**: bài round-trip vẫn có thể đi qua, nhưng dữ liệu không tương thích với ngôn ngữ/phần mềm khác.

### Thử đọc sai có chủ đích

Tạo một bản ghi hợp lệ, cố tình đọc `readShort` thay `readInt` hoặc đảo vị trí hai trường. Kỳ vọng **giá trị sai, EOFException hoặc vi phạm validation** chứ không mặc định chỉ một dạng lỗi duy nhất. Kiểm tra thông báo và hành vi phục hồi: có bỏ bản ghi, dừng toàn bộ tệp hay yêu cầu gửi lại dữ liệu?

Một parser tốt nên giữ **offset/bối cảnh bản ghi** khi báo lỗi, ví dụ “record 12, field nameLength không hợp lệ”, thay vì chỉ “không đọc được file”.

## 12. Lỗi thường gặp và checklist

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Ghi `int` nhưng đọc `short` | Cursor trượt ranh giới 2 byte | Dùng `readInt` khớp `writeInt` |
| Ghi các trường theo A → B → C nhưng đọc A → C → B | Giá trị bị diễn giải sai | Tạo schema trường có thứ tự rõ |
| Ghi byte chuỗi UTF-8 nhưng đọc bằng `readUTF` | Sai tiền tố/charset, có thể EOF hoặc lỗi Unicode | Thống nhất cặp encode/decode và framing |
| Dùng `String.length()` làm số byte UTF-8 | Đọc thiếu/thừa khi gặp chữ có dấu/emoji | Tính độ dài từ `getBytes(UTF_8).length` |
| Đọc `read(byte[])` một lần và tin đã đủ | Payload có thể bị đọc thiếu | `readFully` hoặc vòng lặp xử lý số byte trả về |
| Dùng `available()` để tính độ dài bản ghi | Không phản ánh ranh giới dữ liệu ở mọi stream | Prefix độ dài hoặc schema/framing |
| Không kiểm tra chiều dài do input khai báo | Có thể cấp phát quá lớn hoặc lỗi | Giới hạn count/length trước khi cấp phát |
| Nuốt mọi `EOFException` | Bỏ qua dữ liệu cắt cụt | Chỉ xem EOF hợp lệ nếu schema nói như vậy |
| Đổi byte order mà không đổi decoder | Giá trị số sai | Thống nhất big-/little-endian |
| Ghi thêm field không tăng version | Reader cũ mất đồng bộ | Version/header và quy tắc tương thích |
| Đọc bytes bằng `Reader` tùy tiện | Charset decode có thể thay đổi byte tùy ý | Với binary dùng `InputStream`/`DataInputStream` |
| Ghi xong chưa flush/close rồi cho reader mở đọc | Dữ liệu chưa được đẩy đủ qua buffer | Hoàn tất writer trước khi reader đọc |

**Checklist trước khi lưu hoặc gửi một giao thức nhị phân:**

- [ ] Viết thứ tự các trường từ byte đầu đến byte cuối.
- [ ] Định nghĩa kích thước, signedness, endian và kiểu dữ liệu của từng trường.
- [ ] Định nghĩa chuỗi theo charset nào, prefix độ dài bao nhiêu byte, độ dài tính theo đơn vị gì.
- [ ] Ghi rõ cách xác định số record hoặc dấu kết thúc.
- [ ] Xác minh writer/reader dùng đúng cặp API và cùng schema/version.
- [ ] Chặn chiều dài và số lượng bất hợp lý trước khi cấp phát.
- [ ] Kiểm thử dữ liệu hợp lệ, cắt cụt, sai thứ tự và byte dư.
- [ ] Với định dạng giao tiếp nhiều ngôn ngữ, kiểm tra byte thực tế thay vì chỉ round-trip trong Java.

**Bài tự luyện:** Thiết kế định dạng `[int count][int id][short age][int utf8Length][utf8NameBytes]` cho hai người. Viết bằng `DataOutputStream` và đọc lại bằng `DataInputStream`. Sau đó cố tình đảo thứ tự đọc `age` với `utf8Length`, quan sát vị trí bắt đầu sai và giải thích vì sao lỗi có thể không xuất hiện ngay ở trường đầu tiên.

**Ghi nhớ:** **Thứ tự ghi là một phần của định dạng dữ liệu nhị phân.** Người đọc phải tuân thủ cùng thứ tự, cùng kích thước và cách mã hóa. `DataOutputStream`/`DataInputStream` giúp đọc/ghi byte có cấu trúc, nhưng chính **schema được hai phía thống nhất** mới bảo đảm dữ liệu được hiểu đúng.
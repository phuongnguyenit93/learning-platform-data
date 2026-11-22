# Big-endian, signed byte và đọc giá trị unsigned trong Java

Khi xử lý tệp nhị phân hoặc một giao thức mạng, chương trình không chỉ phải đọc đủ số byte mà còn phải **diễn giải đúng ý nghĩa các bit**. Hai vấn đề dễ gây lỗi là **thứ tự byte** (*endianness*) của số nhiều byte và **cách biểu diễn số có dấu/không dấu** (*signed/unsigned*) trong Java.

Java dùng `byte` có dấu từ -128 đến 127, nhưng một byte vật lý có thể chứa mọi mẫu 8 bit từ `00` đến `FF`. Java cũng cung cấp những API đọc unsigned như `DataInputStream.readUnsignedByte()`, `readUnsignedShort()` và hàm chuyển kiểu như `Byte.toUnsignedInt(...)` hoặc `Integer.toUnsignedLong(...)`. Đồng thời, `DataInputStream` đọc số nguyên nhiều byte theo **big-endian**; còn `ByteBuffer` cho phép chọn big-endian hay little-endian.

Bài này giải thích cơ chế, các thao tác bit an toàn, cách kiểm tra dữ liệu thiếu byte và ví dụ chạy được với Java 17+.

## 1. Một byte thô khác với giá trị byte có dấu

Một byte chứa 8 bit, có 256 mẫu bit từ `00000000` đến `11111111`, tương ứng `0x00` đến `0xFF`. **Mẫu bit không tự mang khái niệm số âm**; đó là ý nghĩa do chương trình gán khi diễn giải.

Trong Java, kiểu nguyên thủy `byte` luôn là **signed 8-bit** theo biểu diễn bù hai (*two's complement*), trong khoảng **-128..127**.

| Mẫu bit / hex | Xem như unsigned 8-bit | Xem như `byte` Java |
|---|---:|---:|
| `00000000` / `0x00` | 0 | 0 |
| `01111111` / `0x7F` | 127 | 127 |
| `10000000` / `0x80` | 128 | -128 |
| `11111111` / `0xFF` | 255 | -1 |

Từ 0 đến 127, signed và unsigned cho cùng giá trị. Từ 128 đến 255, bit cao nhất bằng 1 nên khi giữ trong `byte`, giá trị được biểu diễn là một số âm. Điều này **không có nghĩa các bit đã bị hỏng**: `(byte) 0xFF` vẫn có 8 bit `11111111`.

Để chuyển **mẫu bit của `byte` thành số unsigned 0..255**, có hai cách tương đương:

~~~java
// Mảnh mã minh họa: b là biến byte đã có.
int unsigned1 = b & 0xFF;
int unsigned2 = Byte.toUnsignedInt(b);
~~~

Toán tử `& 0xFF` giữ lại 8 bit thấp sau khi `byte` được mở rộng sang `int`. Ví dụ `b = (byte) 0xFF` có giá trị `-1` khi xem là `byte`, nhưng cả hai biểu thức đều cho `255`.

**Không dùng `Math.abs(b)` để chuyển unsigned**. Với `0xFF`, `Math.abs((int) b)` chỉ được `1`, không phải `255`.

## 2. Vì sao phép chuyển kiểu và dịch bit có thể gây lỗi?

Trong biểu thức Java, `byte` và `short` thường được **nâng kiểu lên `int`** trước khi tính toán. Khi mở rộng một giá trị signed âm, Java thực hiện *sign extension*: bit dấu được kéo dài sang các bit cao.

Ví dụ:

~~~java
byte b = (byte) 0x80;   // -128
int signed = b;         // -128
int unsigned = b & 0xFF; // 128
~~~

Biểu diễn khái niệm:

~~~text
Byte gốc:              1000 0000
Mở rộng có dấu sang int: 11111111 11111111 11111111 10000000
Sau phép AND 0xFF:      00000000 00000000 00000000 10000000
~~~

Nếu ghép nhiều byte bằng toán tử dịch trái mà **không mask**, các bit dấu có thể lan vào phần cao hơn và làm sai kết quả:

~~~java
// Sai khi high có bit 7 bằng 1:
int wrong = (high << 8) | low;

// Đúng cho hai byte nguồn theo big-endian:
int unsigned16 = ((high & 0xFF) << 8) | (low & 0xFF);
~~~

Đây là mảnh mã minh họa, với `high` và `low` là `byte`. Trong `wrong`, nếu `high` âm thì bit cao của `int` có thể bị bật sai; nếu `low` âm, phép OR cũng có thể kéo các bit 1 ra khỏi 8 bit thấp. Mask từng byte **trước khi dịch/OR** làm rõ rằng hai byte nguồn là các giá trị 0..255.

### Khi ghép bốn byte thành unsigned 32-bit

Một giá trị unsigned 32-bit có thể lên đến **4.294.967.295**, lớn hơn giới hạn `int` là 2.147.483.647. Muốn kết quả số học luôn không âm, dùng `long` và mask từng byte:

~~~java
// Mảnh mã minh họa: a, b, c, d là bốn biến byte theo thứ tự big-endian.
long unsigned32 =
        ((long) (a & 0xFF) << 24)
      | ((long) (b & 0xFF) << 16)
      | ((long) (c & 0xFF) << 8)
      |  (long) (d & 0xFF);
~~~

Hãy cast sang `long` trước phép dịch khi cần biểu diễn số unsigned 32-bit dưới dạng số không âm; nếu ghép vào `int`, mẫu bit vẫn đúng nhưng số Java có thể âm. Có thể chuyển một `int` đã đọc thành unsigned 32-bit bằng `Integer.toUnsignedLong(value)`.

## 3. Big-endian và little-endian là thứ tự lưu byte

**Endianness** quy định thứ tự các **byte** trong một giá trị nhiều byte (như `short`, `int`, `long`). Nó không thay đổi thứ tự bit bên trong từng byte.

Giả sử giá trị 32-bit là `0x12345678`:

| Kiểu | Các byte theo thứ tự xuất hiện trong file/network |
|---|---|
| **Big-endian** | `12 34 56 78` |
| **Little-endian** | `78 56 34 12` |

- **Big-endian**: byte có trọng số lớn nhất (*most significant byte*) được ghi/đọc trước.
- **Little-endian**: byte có trọng số nhỏ nhất (*least significant byte*) được ghi/đọc trước.

Với hai byte `12 34`, nếu đọc unsigned 16-bit theo big-endian thì giá trị là `0x1234 = 4660`; nếu hiểu theo little-endian thì là `0x3412 = 13330`.

**Signedness và endianness là hai vấn đề độc lập**:

- Signed/unsigned quy định cách diễn giải bit cao nhất và miền giá trị.
- Big/little-endian quy định thứ tự byte khi dựng một giá trị **nhiều byte**.
- Một byte đơn lẻ không có vấn đề endianness; chỉ có mẫu 8 bit và cách diễn giải signed/unsigned.

Khi đọc file nhị phân, **không được tự suy đoán** endianness từ máy đang chạy. Quy tắc đúng phải lấy từ định dạng file hoặc giao thức. Trong nhiều giao thức mạng, thứ tự big-endian còn được gọi là *network byte order*, nhưng không phải giao thức nào cũng mặc nhiên dùng big-endian.

## 4. InputStream.read() đã trả về unsigned 8-bit — cần phân biệt EOF

`InputStream.read()` trả về kiểu `int`, có hai loại kết quả:

- `0..255`: giá trị của một byte vừa đọc thành công, đã hiểu theo dạng **unsigned**.
- `-1`: không còn byte (EOF, *end of file/stream*).

Do đó, khi đọc byte `0xFF`, `read()` trả **255**, không trả `-1`. Nếu ép ngay kết quả vào `byte` rồi so sánh với `-1`, chương trình có thể **nhầm dữ liệu hợp lệ `0xFF` là EOF**.

### Ví dụ Java 17+: signed byte, unsigned byte và EOF

Tạo file **`SignedUnsignedByteDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

public class SignedUnsignedByteDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = {0x7F, (byte) 0x80, (byte) 0xFF};

        for (byte value : data) {
            System.out.printf("signed=%d unsigned=%d%n",
                    value, Byte.toUnsignedInt(value));
        }

        try (InputStream in = new ByteArrayInputStream(data)) {
            int value;
            while ((value = in.read()) != -1) {
                System.out.println("read()=" + value);
            }
            System.out.println("EOF=" + in.read());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 SignedUnsignedByteDemo.java
java SignedUnsignedByteDemo
~~~

Stdout:

~~~text
signed=127 unsigned=127
signed=-128 unsigned=128
signed=-1 unsigned=255
read()=127
read()=128
read()=255
EOF=-1
~~~

Điểm chính:

1. Trong mảng `byte[]`, hai byte `0x80` và `0xFF` có giá trị signed âm.
2. `Byte.toUnsignedInt(...)` trả giá trị tương ứng 128 và 255, giữ nguyên mẫu bit.
3. `InputStream.read()` đã trả unsigned 8-bit dạng `int`; `-1` chỉ là EOF.
4. Vòng lặp so sánh `-1` **trước khi ép kiểu hoặc diễn giải**. Không dùng `byte value = (byte) in.read()` làm điều kiện hết dữ liệu.

Với `InputStream.read(byte[] buffer)`, **giá trị trả về** là số byte đọc được (hoặc `-1` khi EOF), còn **từng phần tử `buffer[i]` vẫn là `byte` có dấu**. Muốn tính unsigned từ các phần tử mảng, vẫn dùng `buffer[i] & 0xFF`.

## 5. DataInputStream đọc số nhiều byte theo big-endian

`java.io.DataInputStream` bọc một `InputStream` để đọc dữ liệu nhị phân có kiểu. Theo hợp đồng của các phương thức đọc số nhiều byte, nó sử dụng **big-endian**, độc lập với CPU và hệ điều hành.

| Phương thức | Số byte đọc | Kiểu kết quả | Miền giá trị hoặc ý nghĩa |
|---|---:|---|---|
| `readByte()` | 1 | `byte` | signed -128..127 |
| `readUnsignedByte()` | 1 | `int` | unsigned 0..255 |
| `readShort()` | 2 | `short` | signed -32768..32767, big-endian |
| `readUnsignedShort()` | 2 | `int` | unsigned 0..65535, big-endian |
| `readChar()` | 2 | `char` | đơn vị UTF-16 không dấu 0..65535, big-endian |
| `readInt()` | 4 | `int` | signed 32-bit, big-endian |
| `readLong()` | 8 | `long` | signed 64-bit, big-endian |
| `readFloat()` | 4 | `float` | mẫu bit IEEE 754 được đọc theo big-endian |
| `readDouble()` | 8 | `double` | mẫu bit IEEE 754 được đọc theo big-endian |

`DataInputStream` **không** có phương thức `readUnsignedInt()` riêng trong Java SE. Cách chuẩn là:

~~~java
// Mảnh mã minh họa: dataIn là DataInputStream đã mở.
long unsigned32 = Integer.toUnsignedLong(dataIn.readInt());
~~~

Mặc dù `readInt()` có thể cho số âm, **32 bit thu được vẫn đúng**. `Integer.toUnsignedLong(...)` diễn giải mẫu 32 bit đó thành giá trị `0..4294967295` trong kiểu `long`.

Tương tự, với một `short` đã có, `Short.toUnsignedInt(value)` chuyển sang `int` không âm trong khoảng `0..65535`.

### Không đọc số nhiều byte như một lần đọc đơn lẻ

Lệnh `readUnsignedShort()` phải lấy đủ **hai byte** theo thứ tự big-endian. Nếu luồng kết thúc sau một byte, phương thức ném `EOFException` (lớp con của `IOException`), thay vì âm thầm trả một số sai. `readInt()` tương tự đòi hỏi đủ bốn byte.

Một thông điệp nhị phân chỉ đọc đúng khi **hai phía đồng ý** về số byte, thứ tự byte, signedness và ngữ nghĩa từng trường; dùng đúng method nhưng sai schema vẫn giải mã sai.

## 6. Ví dụ Java 17+: DataOutputStream + DataInputStream

`DataOutputStream` ghi các kiểu nguyên thủy ra byte theo thứ tự tương thích với `DataInputStream` (big-endian cho số nhiều byte). Ví dụ sau dùng luồng trong bộ nhớ để quan sát chính xác từng byte.

Tạo file **`BigEndianDataDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.Locale;

public class BigEndianDataDemo {
    public static void main(String[] args) throws IOException {
        byte[] bytes;

        try (ByteArrayOutputStream memory = new ByteArrayOutputStream();
             DataOutputStream out = new DataOutputStream(memory)) {
            out.writeShort(0x1234);
            out.writeInt(0x89ABCDEF);
            out.writeByte(0xFF);
            out.flush();
            bytes = memory.toByteArray();
        }

        StringBuilder hex = new StringBuilder();
        for (byte b : bytes) {
            if (hex.length() > 0) {
                hex.append(' ');
            }
            hex.append(String.format(Locale.ROOT, "%02X", b & 0xFF));
        }
        System.out.println("bytes=" + hex);

        try (DataInputStream in =
                     new DataInputStream(new ByteArrayInputStream(bytes))) {
            int unsigned16 = in.readUnsignedShort();
            int signed32 = in.readInt();
            int unsigned8 = in.readUnsignedByte();

            System.out.println("u16=" + unsigned16);
            System.out.println("i32=" + signed32);
            System.out.println("u32=" + Integer.toUnsignedLong(signed32));
            System.out.println("u8=" + unsigned8);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 BigEndianDataDemo.java
java BigEndianDataDemo
~~~

Stdout chính xác:

~~~text
bytes=12 34 89 AB CD EF FF
u16=4660
i32=-1985229329
u32=2309737967
u8=255
~~~

Phân tích:

- `writeShort(0x1234)` tạo hai byte `12 34`. `readUnsignedShort()` trả `4660`.
- `writeInt(0x89ABCDEF)` tạo `89 AB CD EF`. Bit dấu 32-bit là 1 nên `readInt()` trả số signed âm, nhưng `Integer.toUnsignedLong(...)` cho số unsigned `2309737967`.
- `writeByte(0xFF)` chỉ ghi 8 bit thấp. `readUnsignedByte()` trả `255`.
- `String.format("%02X", b & 0xFF)` in byte ở dạng hex hai chữ số; `& 0xFF` giúp tránh nhầm sign extension.
- `ByteArrayOutputStream` giữ dữ liệu trong RAM; ví dụ này phục vụ học tập. Với file hoặc socket thật, hãy quản lý vòng đời stream, kích thước dữ liệu và lỗi I/O tương ứng.

**Không ghi và đọc cùng đối tượng stream theo kiểu tự đoán định dạng**: `DataOutputStream.writeUTF/readUTF` có quy ước modified UTF-8 và tiền tố độ dài riêng, **không** tương đương với việc ghi một chuỗi UTF-8 thô. Học endianness qua các trường số không có nghĩa văn bản nào cũng theo cùng kiểu mã hóa.

## 7. ByteBuffer: mặc định big-endian nhưng có thể đổi thứ tự

`java.nio.ByteBuffer` cung cấp phương thức `getShort()`, `getInt()`, `getLong()` và các phương thức `put...` tương ứng. Nó có một thuộc tính `ByteOrder` để quy định thứ tự byte của các phép đọc/ghi **nhiều byte**.

- Một `ByteBuffer` mới có byte order mặc định là **`ByteOrder.BIG_ENDIAN`**.
- Có thể đặt lại bằng `buffer.order(ByteOrder.LITTLE_ENDIAN)`.
- Thuộc tính order áp dụng cho các phép truy cập đa byte như `getShort/getInt/putInt`; nó **không** tự đảo byte khi gọi `get()` lấy một byte.
- `getInt()` vẫn trả về **signed `int`** dù thứ tự byte nào; nếu giá trị cần hiểu unsigned, dùng `Integer.toUnsignedLong(...)`.

### Ví dụ Java 17+: cùng bốn byte, hai giá trị khác nhau

Tạo file **`ByteOrderDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class ByteOrderDemo {
    public static void main(String[] args) {
        byte[] data = {0x01, 0x02, 0x03, 0x04};

        int big = ByteBuffer.wrap(data)
                .order(ByteOrder.BIG_ENDIAN)
                .getInt();

        int little = ByteBuffer.wrap(data)
                .order(ByteOrder.LITTLE_ENDIAN)
                .getInt();

        System.out.println("big=" + big);
        System.out.println("little=" + little);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ByteOrderDemo.java
java ByteOrderDemo
~~~

Stdout:

~~~text
big=16909060
little=67305985
~~~

Giải thích:

- Big-endian diễn giải `01 02 03 04` thành `0x01020304`, tức `16909060`.
- Little-endian diễn giải cùng dãy byte thành `0x04030201`, tức `67305985`.
- Không byte nào bị thay đổi trong mảng `data`; chỉ quy tắc ghép chúng thành `int` khác nhau.

`ByteOrder.nativeOrder()` cho biết thứ tự byte gốc của nền tảng phục vụ các tình huống tương tác bộ nhớ/native. **Đừng dùng nó để quyết định cách đọc định dạng tệp hoặc giao thức**: định dạng mới là thứ quy định big- hay little-endian.

`DataInputStream` không có `order(ByteOrder.LITTLE_ENDIAN)`. Nếu giao thức dùng little-endian, có thể dùng `ByteBuffer` được cấu hình đúng, đọc từng byte rồi ghép thủ công, hoặc sử dụng một thư viện I/O có API little-endian.

## 8. Tự ghép unsigned 16-bit và unsigned 32-bit theo big-endian

Khi một định dạng có cấu trúc byte cụ thể hoặc không muốn dùng `DataInputStream`, có thể ghép bằng phép dịch và OR. Với hai byte `hi`, `lo`, giá trị unsigned 16-bit big-endian là:

\[
(\mathrm{hi}\ \&\ 255)\times 256 + (\mathrm{lo}\ \&\ 255)
\]

Với bốn byte `a, b, c, d`, giá trị unsigned 32-bit big-endian là:

\[
((a\ \&\ 255)\ll 24)\;|\;((b\ \&\ 255)\ll 16)\;|\;((c\ \&\ 255)\ll 8)\;|\;(d\ \&\ 255)
\]

Trong Java cần dùng kiểu `long` nếu muốn in ra giá trị **unsigned 32-bit không âm**. Khi đọc trực tiếp từ `InputStream.read()`, giá trị mỗi byte đã là `0..255`; nhưng vẫn phải kiểm tra EOF (`-1`) **trước khi ghép**. Nếu một byte còn thiếu, không được đưa `-1` vào phép dịch rồi coi là dữ liệu hợp lệ.

### Ví dụ Java 17+: thao tác mask và dịch với unsigned

Tạo file **`UnsignedBitwiseDemo.java`**:

~~~java
public class UnsignedBitwiseDemo {
    public static void main(String[] args) {
        byte high = (byte) 0xAB;
        byte low = (byte) 0xCD;

        int u16 = ((high & 0xFF) << 8) | (low & 0xFF);
        short signed16 = (short) u16;

        System.out.println("u16=" + u16);
        System.out.println("s16=" + signed16);

        byte[] four = {
                (byte) 0xFF, (byte) 0xFF,
                (byte) 0xFF, (byte) 0xFF
        };

        long u32 = ((long) (four[0] & 0xFF) << 24)
                 | ((long) (four[1] & 0xFF) << 16)
                 | ((long) (four[2] & 0xFF) << 8)
                 |  (long) (four[3] & 0xFF);

        System.out.println("u32=" + u32);
        System.out.println("asInt=" + (int) u32);
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnsignedBitwiseDemo.java
java UnsignedBitwiseDemo
~~~

Stdout:

~~~text
u16=43981
s16=-21555
u32=4294967295
asInt=-1
~~~

Hai byte `AB CD` có **cùng mẫu bit 16-bit**, nhưng `int u16` lưu ý nghĩa unsigned là 43981, còn ép sang `short` signed cho -21555. Bốn byte `FF FF FF FF` đại diện số unsigned 32-bit lớn nhất `4294967295`; ép về `int` giữ 32 bit nhưng diễn giải signed thành -1.

Nếu chỉ cần chuyển đổi mẫu signed 16/32-bit đã có, tránh viết lại toàn bộ bitwise:

~~~java
// Mảnh mã minh họa với short s và int i đã được đọc.
int unsigned16 = Short.toUnsignedInt(s);
long unsigned32 = Integer.toUnsignedLong(i);
~~~

Các hàm chuẩn làm rõ ý định và tránh nhiều lỗi mask/shift.

## 9. Đọc “unsigned” nhiều hơn 32 bit trong Java

Java không có primitive `unsigned byte`, `unsigned short`, `unsigned int` hoặc `unsigned long` độc lập như trong một số ngôn ngữ. Tuy nhiên có thể **giữ cùng mẫu bit** và sử dụng các API diễn giải unsigned.

| Số bit unsigned | Phạm vi | Cách Java biểu diễn phù hợp |
|---|---|---|
| 8 | 0..255 | `int` với `Byte.toUnsignedInt(byte)` hoặc `DataInputStream.readUnsignedByte()` |
| 16 | 0..65535 | `int` với `Short.toUnsignedInt(short)` hoặc `DataInputStream.readUnsignedShort()` |
| 32 | 0..4294967295 | `long` với `Integer.toUnsignedLong(int)` |
| 64 | 0..18446744073709551615 | Mẫu bit trong `long` kèm các hàm unsigned, hoặc `BigInteger` nếu cần giá trị toán học vượt `Long.MAX_VALUE` |

Với dữ liệu unsigned 64-bit:

- `DataInputStream.readLong()` lấy đủ 8 byte big-endian, trả kiểu `long` signed mang **đúng mẫu 64 bit**.
- `Long.toUnsignedString(value)` hiển thị giá trị đó dưới dạng số thập phân unsigned.
- `Long.compareUnsigned(a, b)` và `Long.divideUnsigned(...)`/`remainderUnsigned(...)` hỗ trợ so sánh và phép chia unsigned.
- `BigInteger` có thể biểu diễn đầy đủ miền 0..2^64-1 khi ứng dụng cần tính toán ngoài giới hạn signed `long`. Việc chuyển byte sang `BigInteger` phải xác định rõ **dấu, độ dài và byte order**; constructor `new BigInteger(1, magnitudeBigEndian)` nhận mảng độ lớn dạng big-endian và ép dấu dương.

Không tự cộng `2^64` bằng một biểu thức `long`, vì số đó không biểu diễn được trong signed `long`. Tránh thao tác ngầm định overflow như thể nó là số nguyên dương không giới hạn.

## 10. Những lỗi đọc nhị phân cần tránh

### 10.1. Nhầm `0xFF` với EOF

Sai:

~~~java
// Mảnh mã minh họa: sai vì ép int trả về từ read() thành byte trước.
byte value = (byte) input.read();
if (value == -1) {
    // Không phân biệt được byte 0xFF với EOF.
}
~~~

Đúng:

~~~java
// Mảnh mã minh họa: input là InputStream đang mở.
int value = input.read();
if (value == -1) {
    // EOF.
} else {
    int unsigned8 = value; // 0..255
}
~~~

### 10.2. Dịch `byte` âm trước khi mask

Sai:

~~~java
// Mảnh mã minh họa: b0 và b1 là byte có thể âm.
int combined = (b0 << 8) | b1;
~~~

Đúng:

~~~java
int combined = ((b0 & 0xFF) << 8) | (b1 & 0xFF);
~~~

Nếu cần bốn byte thành số unsigned 32-bit không âm, dùng `long` như ví dụ phần 8.

### 10.3. Đọc unsigned bằng kiểu quá nhỏ

Sai:

~~~java
// Mảnh mã minh họa: readUnsignedShort() có thể trả 65535.
short size = (short) dataIn.readUnsignedShort();
~~~

Với giá trị vượt 32767, biến `size` sẽ âm do ép kiểu `short`. Đúng là giữ trong `int`:

~~~java
int size = dataIn.readUnsignedShort();
~~~

### 10.4. Dùng đúng kiểu nhưng sai endian

Nếu file chứa hai byte `34 12` được định nghĩa là số little-endian `0x1234`, gọi `readUnsignedShort()` của `DataInputStream` sẽ cho `0x3412`, **không** cho giá trị mong đợi 4660. Cần đọc little-endian đúng hợp đồng nguồn.

### 10.5. Cho rằng một lần `read(byte[])` luôn đủ độ dài

`InputStream.read(byte[])` có thể trả ít byte hơn kích thước mảng dù chưa tới EOF. Nếu dữ liệu cố định cần đủ N byte, dùng `DataInputStream.readFully(byte[])`, `readNBytes(...)` với kiểm tra số byte nhận được, hoặc lặp cho đến khi đủ. `readFully(...)` ném `EOFException` khi không thể đọc đủ byte yêu cầu.

`DataInputStream.readInt()`/`readUnsignedShort()` tự đọc theo số byte cần thiết, không phải một lệnh `read(byte[])` thiếu kiểm tra.

## 11. Khi nào dùng API nào?

| Nhu cầu | Lựa chọn thực tế | Lưu ý |
|---|---|---|
| Lấy từng byte từ luồng | `InputStream.read()` | Trả `0..255` hoặc `-1` khi EOF |
| Diễn giải một `byte` signed theo unsigned | `Byte.toUnsignedInt(b)` hoặc `b & 0xFF` | Không đổi bit |
| Đọc unsigned 16-bit big-endian | `DataInputStream.readUnsignedShort()` | Trả `int`, ném lỗi nếu thiếu 2 byte |
| Đọc unsigned 32-bit big-endian | `Integer.toUnsignedLong(in.readInt())` | Trả `long` 0..4294967295 |
| Đọc nhiều kiểu big-endian liên tiếp | `DataInputStream` | Cùng schema với phía ghi |
| Đọc int/short có thể chọn endian | `ByteBuffer.order(...).getInt()/getShort()` | Nhớ chuyển unsigned nếu cần |
| Xử lý một định dạng nhị phân đặc biệt | Đọc các byte và mask/shift theo tài liệu | Phải kiểm tra độ dài, EOF, thứ tự |
| Unsigned 64-bit | `Long.toUnsignedString` hoặc `BigInteger` | Không có primitive số dương đủ toàn miền |

### Checklist khi thiết kế hoặc phân tích định dạng nhị phân

1. **Độ dài** trường là bao nhiêu byte? Có tiền tố độ dài hoặc padding không?
2. **Thứ tự byte** là big-endian hay little-endian?
3. **Có dấu hay không dấu**? Miền giá trị hợp lệ là gì?
4. **Kiểu lưu kết quả** có đủ miền không? Ví dụ unsigned 16-bit cần `int`, unsigned 32-bit không âm cần `long`.
5. **Nguồn đã đọc đủ** chưa? Cần xử lý `-1`/`EOFException` thay vì đưa giá trị thiếu vào phép bit.
6. **Kích thước đầu vào có được giới hạn** không? Đừng dùng một trường length từ file không đáng tin để cấp phát mảng tùy ý.
7. **Byte thô khác văn bản**: các phương thức số của `DataInputStream` không thay thế quy tắc charset cho chuỗi ký tự.

## 12. Ghi nhớ trọng tâm

- `byte` Java là **signed -128..127**, còn mẫu 8 bit của dữ liệu vẫn có thể được hiểu **unsigned 0..255** bằng `b & 0xFF` hoặc `Byte.toUnsignedInt(b)`.
- `InputStream.read()` trả `int 0..255` cho byte hợp lệ và `-1` cho **EOF**; tuyệt đối không ép về `byte` trước khi kiểm tra EOF.
- **Big-endian** đặt byte có trọng số lớn nhất trước; **little-endian** đặt byte có trọng số nhỏ nhất trước. Endianness không liên quan đến dấu của một byte riêng lẻ.
- `DataInputStream`/`DataOutputStream` dùng **big-endian** khi đọc/ghi số nhiều byte. `ByteBuffer` mặc định big-endian và cho phép chọn `ByteOrder.LITTLE_ENDIAN`.
- `readUnsignedByte()` trả `int`; `readUnsignedShort()` trả `int`. Với unsigned 32-bit, dùng `Integer.toUnsignedLong(readInt())`.
- Khi ghép byte, **mask trước khi dịch/OR**, giữ kết quả trong kiểu đủ rộng và kiểm tra đủ số byte đầu vào.
- Bất cứ giá trị nào chỉ đúng khi **độ dài, endian, signedness và schema** khớp với tài liệu định dạng/giao thức.

### Tài liệu chính thức

- [Java SE 17 — Byte](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html)
- [Java SE 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html)
- [Java SE 17 — DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html)
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 17 — Integer.toUnsignedLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#toUnsignedLong(int))

# Byte.toUnsignedInt, Short.toUnsignedInt và mở rộng giá trị trong Java

## 1. Vì sao byte âm lại có thể đại diện số 255?

Trong Java, kiểu nguyên thủy `byte` là số nguyên **có dấu** 8 bit, biểu diễn giá trị từ **-128 đến 127**; kiểu `short` là số nguyên **có dấu** 16 bit, từ **-32768 đến 32767**. Nhưng trong định dạng file, giao thức mạng, ảnh, thiết bị nhúng hoặc packet nhị phân, cùng 8 hoặc 16 bit đó thường được quy định là **số không dấu**:

| Số bit | Kiểu lưu bit trong Java | Miền số có dấu | Miền diễn giải không dấu |
| --- | --- | --- | --- |
| 8 | `byte` | -128…127 | 0…255 |
| 16 | `short` | -32768…32767 | 0…65535 |

Ví dụ chuỗi bit `11111111` (hex `FF`) được Java lưu trong `byte` với giá trị **-1**. Nhưng một protocol định nghĩa trường này là **unsigned 8-bit integer** thì cùng chuỗi bit ấy có ý nghĩa **255**, không phải -1.

Tương tự, `short` có toàn bộ 16 bit là 1 (`FFFF`) mang giá trị có dấu `-1` hoặc giá trị không dấu `65535` tùy **hợp đồng dữ liệu**.

Hai API trọng tâm của bài là:

```java
// Chữ ký từ java.lang, có từ Java 8.
public static int Byte.toUnsignedInt(byte value);
public static int Short.toUnsignedInt(short value);
```

Cách gọi đúng của các static method này:

```java
byte b = (byte) 0xFF;
short s = (short) 0xFFFF;

int unsignedByte = Byte.toUnsignedInt(b);   // 255
int unsignedShort = Short.toUnsignedInt(s); // 65535
```

Không có kiểu primitive riêng tên `unsigned byte` hay `unsigned short` trong Java. Các phương thức trên **không đổi bit gốc của b/s**; chúng đưa các bit vào kiểu `int` đủ rộng để biểu diễn giá trị **không dấu** tương ứng.

Đây là kiến thức nền đã có từ Java 8 và **vẫn áp dụng trong Java hiện đại**, kể cả khi ứng dụng chạy JDK 17 trở lên. Bài sử dụng API hiện hành, không khuyến nghị cách làm lỗi thời/legacy.

## 2. Hai cơ chế khác nhau: sign extension và zero extension

### 2.1. Mở rộng nguyên thủy thông thường: giữ **giá trị có dấu**

Phép `byte -> int` hoặc `short -> int` là **widening primitive conversion**. Với các kiểu nguyên có dấu, Java dùng **sign extension**: lặp lại bit dấu vào các bit mới thêm ở phía trái.

Nếu giá trị âm, bit dấu bằng `1`, nên khi mở rộng thành 32 bit, các bit cao mới cũng bằng `1`.

```text
byte -1:
8 bit:    11111111                  = 0xFF

(int) b:
32 bit:   11111111 11111111 11111111 11111111
hex:      FFFFFFFF
signed:   -1
```

Với `short -1`:

```text
short -1:
16 bit:            11111111 11111111  = 0xFFFF

(int) s:
32 bit:   11111111 11111111 11111111 11111111
signed:   -1
```

**Widening không có nghĩa biến mọi số thành số dương.** Widening thông thường giữ nguyên **giá trị signed**. Vì thế:

```java
byte raw = (byte) 255;

int a = raw;        // -1: sign extension
int b = (int) raw;  // -1: cũng sign extension
```

Việc có hoặc không viết cast `(int)` không làm thay đổi kết quả.

### 2.2. Mở rộng theo ngữ nghĩa unsigned: giữ **các bit thấp**, thêm zero

`Byte.toUnsignedInt(b)` giữ nguyên 8 bit thấp và đặt **24 bit cao của int bằng 0**. `Short.toUnsignedInt(s)` giữ nguyên 16 bit thấp và đặt **16 bit cao bằng 0**.

```text
Byte.toUnsignedInt((byte) 0xFF)

8 bit nguồn:         11111111
32 bit kết quả:      00000000 00000000 00000000 11111111
hex:                000000FF
giá trị int:         255

Short.toUnsignedInt((short) 0xFFFF)

16 bit nguồn:        11111111 11111111
32 bit kết quả:      00000000 00000000 11111111 11111111
hex:                0000FFFF
giá trị int:         65535
```

Với số nguồn không âm, hai cách mở rộng tạo cùng giá trị số. Chúng khác nhau khi bit dấu của `byte`/`short` đang là 1.

### 2.3. Công thức chính xác

Với byte `b`:

```text
Byte.toUnsignedInt(b)
  = b                    nếu 0 <= b <= 127
  = b + 256              nếu -128 <= b < 0
  nằm trong [0, 255]
```

Với short `s`:

```text
Short.toUnsignedInt(s)
  = s                    nếu 0 <= s <= 32767
  = s + 65536            nếu -32768 <= s < 0
  nằm trong [0, 65535]
```

Đây là **diễn giải giá trị từ cùng một mẫu bit**, không phải điều chỉnh giá trị thực bằng cách cộng 256/65536 trong mọi trường hợp. Khi triển khai, ưu tiên gọi phương thức thư viện thay cho tự viết nhánh điều kiện.

## 3. Ví dụ 1 — signed widening và unsigned widening

Tạo file **WideningDemo.java**:

```java
public class WideningDemo {
    public static void main(String[] args) {
        byte b = (byte) 0xFF;
        short s = (short) 0xFFFF;

        System.out.println("byteSigned=" + b);
        System.out.println("byteWiden=" + (int) b);
        System.out.println(
            "byteUnsigned=" + Byte.toUnsignedInt(b)
        );
        System.out.println("byteMask=" + (b & 0xFF));
        System.out.println(
            "byteUnsignedLong=" + Byte.toUnsignedLong(b)
        );

        System.out.println("shortSigned=" + s);
        System.out.println("shortWiden=" + (int) s);
        System.out.println(
            "shortUnsigned=" + Short.toUnsignedInt(s)
        );
        System.out.println(
            "shortMask=" + (s & 0xFFFF)
        );
        System.out.println(
            "shortUnsignedLong=" + Short.toUnsignedLong(s)
        );
    }
}
```

Chạy:

```bash
javac WideningDemo.java
java WideningDemo
```

Stdout đã kiểm thử với JDK 21:

```text
byteSigned=-1
byteWiden=-1
byteUnsigned=255
byteMask=255
byteUnsignedLong=255
shortSigned=-1
shortWiden=-1
shortUnsigned=65535
shortMask=65535
shortUnsignedLong=65535
```

**Giải thích:**

- `(int)b` và `(int)s` giữ nghĩa có dấu: đều là `-1`.
- `Byte.toUnsignedInt`/`Short.toUnsignedInt` tạo `int` không âm, đúng miền 8/16 bit unsigned.
- Các phép mask `b & 0xFF` và `s & 0xFFFF` cho kết quả tương đương trong ngữ cảnh này, nhưng tên phương thức `toUnsignedInt` diễn đạt ý định rõ hơn.
- `Byte.toUnsignedLong` và `Short.toUnsignedLong` cũng có từ Java 8, trả cùng giá trị unsigned nhưng ở kiểu `long`. Không có ý nghĩa “byte/short nay được nâng lên 32 hoặc 64 bit về số bit nguồn”; chỉ là kiểu **chứa kết quả**.

## 4. Bảng các giá trị ranh giới cần thuộc

| Mẫu bit | Giá trị kiểu Java | Diễn giải unsigned |
| --- | ---: | ---: |
| byte `0x00` | 0 | 0 |
| byte `0x7F` | 127 | 127 |
| byte `0x80` | -128 | 128 |
| byte `0xFF` | -1 | 255 |
| short `0x0000` | 0 | 0 |
| short `0x7FFF` | 32767 | 32767 |
| short `0x8000` | -32768 | 32768 |
| short `0xFFFF` | -1 | 65535 |

Một lỗi rất thường gặp là coi `0x80` là 128 **ở mọi biểu thức**. Trong một `byte`, nó được lưu thành -128; chỉ khi dùng unsigned conversion thì kết quả mới là 128.

### Ví dụ 2 — BoundaryDemo.java

```java
public class BoundaryDemo {
    public static void main(String[] args) {
        byte[] bytes = {
            0,
            127,
            (byte) 128,
            (byte) 255
        };

        for (byte b : bytes) {
            System.out.printf(
                "byte signed=%d unsigned=%d%n",
                b,
                Byte.toUnsignedInt(b)
            );
        }

        short[] shorts = {
            0,
            32767,
            (short) 32768,
            (short) 65535
        };

        for (short s : shorts) {
            System.out.printf(
                "short signed=%d unsigned=%d%n",
                s,
                Short.toUnsignedInt(s)
            );
        }
    }
}
```

```bash
javac BoundaryDemo.java
java BoundaryDemo
```

Stdout:

```text
byte signed=0 unsigned=0
byte signed=127 unsigned=127
byte signed=-128 unsigned=128
byte signed=-1 unsigned=255
short signed=0 unsigned=0
short signed=32767 unsigned=32767
short signed=-32768 unsigned=32768
short signed=-1 unsigned=65535
```

Không cần đoán bit âm có giá trị unsigned gì; chuyển về `int` trước khi xử lý số học, validate hoặc log giá trị protocol.

## 5. Bit mask: b & 0xFF và s & 0xFFFF

Trong Java, toán tử bit `&` khi nhận `byte`/`short` sẽ thúc đẩy toán hạng lên `int` (*binary numeric promotion*). Vì vậy:

```java
byte b = (byte) 0xFF;

int x = b & 0xFF; // 255

short s = (short) 0xFFFF;

int y = s & 0xFFFF; // 65535
```

Giải thích cho `b & 0xFF`:

```text
b được sign-extend thành:   FFFFFFFF
mask:                        000000FF
AND:                         000000FF  -> 255
```

`s & 0xFFFF` tương tự giữ lại 16 bit thấp. Như vậy hai cặp biểu thức sau tương đương về **giá trị** cho mọi giá trị nguồn:

```java
Byte.toUnsignedInt(b)  == (b & 0xFF)
Short.toUnsignedInt(s) == (s & 0xFFFF)
```

**Khuyến nghị:** Dùng phương thức `toUnsignedInt` khi muốn người đọc hiểu rõ dữ liệu là **unsigned 8/16 bit**. Dùng mask khi đang thao tác **bitfields, extraction hoặc layout nhị phân** và bit mask giúp thể hiện rõ cấu trúc.

**Đừng nhầm:** `b & 0xFF` trả về kiểu `int`, không trả kiểu `byte`. Nếu bạn cast kết quả về `byte`, biểu diễn signed lại hiện ra:

```java
int u = ((byte) 0xFF) & 0xFF; // 255
byte back = (byte) u;         // -1
```

Cùng 8 bit được giữ nguyên; chỉ khác **loại giá trị và cách diễn giải**.

## 6. Ví dụ 3 — đọc mảng byte và tránh cộng sai vì dấu

Giả sử mảng dữ liệu nhị phân gồm byte `C8 FF 00 7F`, tương ứng bốn giá trị unsigned `200, 255, 0, 127`. Nếu cộng trực tiếp các `byte` dưới phép toán Java, hai byte đầu lại được xem như `-56` và `-1`.

Tạo file **PacketArrayDemo.java**:

```java
import java.util.Arrays;

public class PacketArrayDemo {
    public static void main(String[] args) {
        byte[] payload = {
            (byte) 0xC8,
            (byte) 0xFF,
            0x00,
            0x7F
        };

        int signedSum = 0;
        int unsignedSum = 0;

        for (byte b : payload) {
            signedSum += b;
            unsignedSum += Byte.toUnsignedInt(b);
        }

        System.out.println(
            "stored=" + Arrays.toString(payload)
        );
        System.out.println("signedSum=" + signedSum);
        System.out.println("unsignedSum=" + unsignedSum);
        System.out.println(
            "firstUnsigned=" +
            Byte.toUnsignedInt(payload[0])
        );
        System.out.println(
            "secondHex=" +
            String.format(
                "%02X",
                Byte.toUnsignedInt(payload[1])
            )
        );
    }
}
```

```bash
javac PacketArrayDemo.java
java PacketArrayDemo
```

Stdout:

```text
stored=[-56, -1, 0, 127]
signedSum=70
unsignedSum=582
firstUnsigned=200
secondHex=FF
```

Ở đây `Arrays.toString(byte[])` hiển thị các giá trị **signed**. Nó không tự làm hỏng byte đã lưu; sai sót chỉ xuất hiện nếu người dùng **đọc signed value như số unsigned**. Khi xử lý packet/image/file có định nghĩa unsigned octets, dùng `Byte.toUnsignedInt(payload[i])`.

**Cẩn thận với cộng dồn:** Với số lượng rất lớn, `int unsignedSum` vẫn có thể overflow. Cần dùng `long` cho tổng dài:

```java
// Đoạn minh họa, không phụ thuộc lớp demo.
long total = 0;
for (byte b : payload) {
    total += Byte.toUnsignedInt(b);
}
```

Chuyển đổi unsigned **không tự phòng overflow của các phép toán tiếp theo**.

## 7. Ghép nhiều byte thành một số 16 bit không dấu

Trong protocol nhị phân, hai octet `FF FE` có thể biểu diễn một unsigned 16-bit number bằng `65534` theo thứ tự **big-endian**.

Công thức đúng:

```java
int high = Byte.toUnsignedInt(wire[0]);
int low = Byte.toUnsignedInt(wire[1]);

int value = (high << 8) | low;
```

Giới hạn:

- `high` và `low` đều thuộc `0..255`.
- `high << 8` thuộc `0..65280`, an toàn trong `int`.
- `value` thuộc `0..65535`, không âm.
- Không có loss do sign extension vì đã diễn giải từng byte unsigned.

Nếu viết `(wire[0] << 8) | wire[1]`, cả hai byte sẽ được sign-extend lên `int`. Khi byte đầu/cuối có bit dấu, kết quả có thể bị ảnh hưởng bởi những bit cao được mở rộng. Đặt conversion/mask **trước khi shift và OR** để đúng contract.

### Ví dụ 4 — CombineBytesDemo.java

```java
public class CombineBytesDemo {
    public static void main(String[] args) {
        byte[] wire = {
            (byte) 0xFF,
            (byte) 0xFE
        };

        int high = Byte.toUnsignedInt(wire[0]);
        int low = Byte.toUnsignedInt(wire[1]);
        int unsigned16 = (high << 8) | low;

        short stored16 = (short) unsigned16;

        System.out.println("high=" + high);
        System.out.println("low=" + low);
        System.out.println("combined=" + unsigned16);
        System.out.println(
            "storedShort=" + stored16
        );
        System.out.println(
            "restored=" +
            Short.toUnsignedInt(stored16)
        );
        System.out.println(
            "hex=" +
            String.format("%04X", unsigned16)
        );
    }
}
```

```bash
javac CombineBytesDemo.java
java CombineBytesDemo
```

Stdout:

```text
high=255
low=254
combined=65534
storedShort=-2
restored=65534
hex=FFFE
```

**Ý nghĩa của `storedShort=-2`:** Khi cast `65534` về `short`, chỉ 16 bit thấp được giữ. Java diễn giải mẫu `FFFE` là signed -2. Dùng `Short.toUnsignedInt(stored16)` sẽ diễn giải đúng lại là 65534.

Nếu bạn cần thực hiện số học 0..65535, nên **giữ ở int** trong ứng dụng; chỉ cast về `short` khi API/storage yêu cầu chính xác 16 bit.

## 8. Endianness: đúng unsigned vẫn có thể đọc sai thứ tự byte

Unsigned conversion giải quyết **ngữ nghĩa bit dấu**, không giải quyết **thứ tự byte** (*byte order*).

Hai byte `AB CD`:

- Big-endian: `0xABCD` = **43981**.
- Little-endian: `0xCDAB` = **52651**.

Cả hai đều là các số unsigned hợp lệ, nhưng **chỉ một cách đọc** đúng theo protocol.

`ByteBuffer.getShort()` trả `short` **signed**. Sau đó `Short.toUnsignedInt(...)` cho phép diễn giải 16 bit ấy thành unsigned. `ByteBuffer` có thể cấu hình `ByteOrder.BIG_ENDIAN` hoặc `ByteOrder.LITTLE_ENDIAN`.

### Ví dụ 5 — EndiannessDemo.java

```java
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class EndiannessDemo {
    public static void main(String[] args)
            throws Exception {
        byte[] wire = {
            (byte) 0xAB,
            (byte) 0xCD
        };

        short big = ByteBuffer.wrap(wire)
            .order(ByteOrder.BIG_ENDIAN)
            .getShort();

        short little = ByteBuffer.wrap(wire)
            .order(ByteOrder.LITTLE_ENDIAN)
            .getShort();

        System.out.println("bigSigned=" + big);
        System.out.println(
            "bigUnsigned=" +
            Short.toUnsignedInt(big)
        );
        System.out.println(
            "littleUnsigned=" +
            Short.toUnsignedInt(little)
        );

        try (DataInputStream input =
                new DataInputStream(
                    new ByteArrayInputStream(wire)
                )) {
            System.out.println(
                "streamUnsignedShort=" +
                input.readUnsignedShort()
            );
        }
    }
}
```

```bash
javac EndiannessDemo.java
java EndiannessDemo
```

Stdout:

```text
bigSigned=-21555
bigUnsigned=43981
littleUnsigned=52651
streamUnsignedShort=43981
```

`DataInputStream.readUnsignedShort()` đọc hai byte theo thứ tự big-endian và trả `int` 0..65535. Nếu protocol dùng little-endian, không dùng trực tiếp cách đọc này mà không đổi thứ tự theo đặc tả. Việc “unsigned” và việc “big/little endian” là **hai quyết định độc lập**.

**Rủi ro thực tế:** Kiểu `short` không lưu thông tin endian trong giá trị của nó. Endian chỉ là cách nhiều byte nằm trong buffer/file/wire được **sắp xếp/đọc**.

## 9. Shift và toán tử >>>: một lỗi rất tinh vi khi byte âm

Trong Java, khi `byte`/`short` tham gia phép dịch bit, nó được thúc đẩy lên `int` trước khi shift. Điều đó có nghĩa toán tử dịch logic `>>>` hoạt động trên **32 bit của int đã sign-extend**, không phải trực tiếp 8 bit của byte.

Ví dụ `byte b=(byte)0xF0`, nghĩa signed -16 và unsigned 240.

```java
int bad = b >>> 4;
// Không phải 15! Vì b được sign-extend trước shift.
```

Khi b được chuyển thành `int -16`, 32 bit là `FFFFFFF0`. Dịch phải không dấu 4 bit tạo `0FFFFFFF` = **268435455**.

Cách đúng nếu cần 4 bit cao của unsigned octet:

```java
int highNibble =
    Byte.toUnsignedInt(b) >>> 4; // 15

// Hoặc:
int highNibble2 =
    (b & 0xFF) >>> 4; // 15
```

### Ví dụ 6 — ShiftDemo.java

```java
public class ShiftDemo {
    public static void main(String[] args) {
        byte b = (byte) 0xF0;
        short s = (short) 0xFF00;

        System.out.println("byteSigned=" + b);
        System.out.println(
            "arithmeticShift=" + (b >> 4)
        );
        System.out.println(
            "logicalShiftOnPromotedInt=" +
            (b >>> 4)
        );
        System.out.println(
            "unsignedHighNibble=" +
            (Byte.toUnsignedInt(b) >>> 4)
        );
        System.out.println(
            "unsignedLowNibble=" +
            (Byte.toUnsignedInt(b) & 0x0F)
        );
        System.out.println(
            "shortHighByte=" +
            (Short.toUnsignedInt(s) >>> 8)
        );
        System.out.println(
            "shortLowByte=" +
            (Short.toUnsignedInt(s) & 0xFF)
        );
    }
}
```

```bash
javac ShiftDemo.java
java ShiftDemo
```

Stdout:

```text
byteSigned=-16
arithmeticShift=-1
logicalShiftOnPromotedInt=268435455
unsignedHighNibble=15
unsignedLowNibble=0
shortHighByte=255
shortLowByte=0
```

Bài học: **zero-extend/mask trước** rồi mới dùng `>>>` nếu nghiệp vụ đang xử lý trường unsigned 8 hoặc 16 bit. Toán tử `>>>` không tự diễn giải biến `byte`/`short` là unsigned.

### 9.1. Khi nào dùng >> và >>>

- `>>`: dịch phải có dấu, giữ bit dấu sau khi operand được promotion.
- `>>>`: dịch phải logic, điền zero ở bit cao của kiểu operand được promotion.
- Với `byte`/`short`, operand đã thành **int** khi shift.
- Chọn `toUnsignedInt`/mask trước khi dịch nếu muốn thao tác trên dữ liệu protocol không dấu.

Không áp dụng công thức `>>>` của một `int` 32 bit trực tiếp để suy ra cách một giá trị byte 8 bit được diễn giải; cần xét bước promotion.

## 10. Phép ép kiểu hẹp và kiểm tra phạm vi trước khi đóng gói

`(byte)255` không tạo một số `byte` dương 255: Java giữ 8 bit thấp, nên kết quả signed là -1. `(short)65535` tương tự có giá trị -1.

Đó là **narrowing primitive conversion**. Nếu input vượt miền số nguyên unsigned mong muốn, cast vẫn chỉ giữ các bit thấp và có thể **lặng lẽ mất dữ liệu**:

```java
byte wrong = (byte) 256;  // 0
short wrong2 = (short) 65536; // 0
```

Với parser của unsigned field, hãy:

1. Đọc input ở kiểu `int` hoặc `long` đủ rộng.
2. **Validate** phạm vi `0..255` hoặc `0..65535`.
3. Cast xuống `byte`/`short` chỉ để lưu các bit.
4. Khi cần số học/hiển thị, dùng `toUnsignedInt` để đọc lại.

**Không dùng `Byte.parseByte("255")` để parse unsigned byte.** Phương thức đó parse số `byte` **signed**, tối đa 127. Với unsigned 8-bit field dưới dạng chuỗi thập phân, có thể dùng `Integer.parseInt` rồi kiểm tra miền.

### Ví dụ 7 — CheckedConversionDemo.java

```java
public class CheckedConversionDemo {
    static byte toByteBits(int unsigned) {
        if (unsigned < 0 || unsigned > 255) {
            throw new IllegalArgumentException(
                "uint8 out of range"
            );
        }
        return (byte) unsigned;
    }

    static short toShortBits(int unsigned) {
        if (unsigned < 0 || unsigned > 65535) {
            throw new IllegalArgumentException(
                "uint16 out of range"
            );
        }
        return (short) unsigned;
    }

    public static void main(String[] args) {
        byte b = toByteBits(
            Integer.parseInt("255")
        );
        short s = toShortBits(
            Integer.parseInt("65535")
        );

        System.out.println("signedByte=" + b);
        System.out.println(
            "roundTripByte=" +
            Byte.toUnsignedInt(b)
        );
        System.out.println("signedShort=" + s);
        System.out.println(
            "roundTripShort=" +
            Short.toUnsignedInt(s)
        );

        try {
            Byte.parseByte("255");
        } catch (NumberFormatException ex) {
            System.out.println(
                "signedByteParser=REJECTED"
            );
        }

        try {
            toByteBits(256);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                "byte256=REJECTED"
            );
        }

        try {
            toShortBits(65536);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                "short65536=REJECTED"
            );
        }
    }
}
```

```bash
javac CheckedConversionDemo.java
java CheckedConversionDemo
```

Stdout:

```text
signedByte=-1
roundTripByte=255
signedShort=-1
roundTripShort=65535
signedByteParser=REJECTED
byte256=REJECTED
short65536=REJECTED
```

**Điểm cần nhớ:** Round-trip `int(0..255) → byte bits → Byte.toUnsignedInt` giữ nguyên giá trị nếu đã validate phạm vi. Còn cast không kiểm tra `256 → byte 0` sẽ đánh mất dữ liệu ban đầu và có thể gây lỗi nghiêm trọng khi xử lý length, offset, checksum hay security-sensitive protocol.

Đối với input số nguyên từ text không tin cậy, còn cần kiểm tra null, chuỗi rỗng, dấu, radix, chiều dài chuỗi, lỗi `NumberFormatException` và quy tắc dữ liệu nghiệp vụ. Không cố chuyển mọi lỗi parse về 0 hoặc 255 nếu contract không yêu cầu.

## 11. So sánh unsigned: đừng dùng thứ tự signed

Giả sử hai byte có ý nghĩa unsigned:

```text
low  = 127   -> signed  127
high = 200   -> signed  -56
```

So sánh trực tiếp theo signed sẽ cho `127 > -56`. Nhưng theo unsigned thì `127 < 200`.

Trong Java 9+ có:

```java
Byte.compareUnsigned(byte x, byte y)
Short.compareUnsigned(short x, short y)
```

Đây là API hiện hành, nhưng **được bổ sung sau Java 8**. Nếu mã nguồn của bạn cần biên dịch Java 8, dùng `Integer.compare(Byte.toUnsignedInt(x),Byte.toUnsignedInt(y))` và tương tự cho short. Hãy phân biệt **module học Java 8** với các bổ sung Java phiên bản mới hơn để không giới thiệu nhầm API Java 9 như API có sẵn của Java 8.

### Ví dụ 8 — UnsignedCompareDemo.java

```java
public class UnsignedCompareDemo {
    public static void main(String[] args) {
        byte low = 127;
        byte high = (byte) 200;

        short s1 = 32767;
        short s2 = (short) 65535;

        System.out.println(
            "byteSignedOrdering=" +
            (Byte.compare(low, high) > 0)
        );
        System.out.println(
            "byteUnsignedOrdering=" +
            (Byte.compareUnsigned(low, high) < 0)
        );
        System.out.println(
            "portableByteOrdering=" +
            (Integer.compare(
                Byte.toUnsignedInt(low),
                Byte.toUnsignedInt(high)
            ) < 0)
        );
        System.out.println(
            "shortSignedOrdering=" +
            (Short.compare(s1, s2) > 0)
        );
        System.out.println(
            "shortUnsignedOrdering=" +
            (Short.compareUnsigned(s1, s2) < 0)
        );
    }
}
```

```bash
# Ví dụ có compareUnsigned(byte/short) yêu cầu Java 9+.
javac UnsignedCompareDemo.java
java UnsignedCompareDemo
```

Stdout trên JDK 21:

```text
byteSignedOrdering=true
byteUnsignedOrdering=true
portableByteOrdering=true
shortSignedOrdering=true
shortUnsignedOrdering=true
```

Khi sort các bản ghi theo unsigned byte/short, comparator phải dùng unsigned value. Nếu dùng comparator signed cho trường protocol unsigned, dải 128..255 hoặc 32768..65535 sẽ bị sắp trước các số không âm.

**Không nhầm `Byte.compareUnsigned` với `Byte.toUnsignedInt`:** phương thức thứ nhất trả thứ tự hai giá trị, phương thức thứ hai trả một giá trị số unsigned.

## 12. Bitfield: giải mã flag từ một byte âm

Một byte có thể chứa nhiều trường bit độc lập. Ví dụ `0b1011_0101` là:

```text
bit:       7 6 5 4 3 2 1 0
giá trị:   1 0 1 1 0 1 0 1

hex:       B5
signed:    -75
unsigned:  181
```

Ta có thể tách:

- 4 bit cao: `1011` = 11.
- 4 bit thấp: `0101` = 5.
- Bit 7: 1.
- Bit 6: 0.
- Bit 4: 1.

Giải mã nên bắt đầu bằng `int u = Byte.toUnsignedInt(flags)` để các biểu thức shift/mask dễ suy luận.

### Ví dụ 9 — BitfieldDemo.java

```java
public class BitfieldDemo {
    public static void main(String[] args) {
        byte flags = (byte) 0b1011_0101;

        int u = Byte.toUnsignedInt(flags);

        System.out.println("signed=" + flags);
        System.out.println("unsigned=" + u);
        System.out.println(
            "upperNibble=" + (u >>> 4)
        );
        System.out.println(
            "lowerNibble=" + (u & 0x0F)
        );
        System.out.println(
            "bit7=" + ((u >>> 7) & 1)
        );
        System.out.println(
            "bit6=" + ((u >>> 6) & 1)
        );
        System.out.println(
            "bit4=" + ((u >>> 4) & 1)
        );
    }
}
```

```bash
javac BitfieldDemo.java
java BitfieldDemo
```

Stdout:

```text
signed=-75
unsigned=181
upperNibble=11
lowerNibble=5
bit7=1
bit6=0
bit4=1
```

**Đừng suy ngữ nghĩa chỉ từ bit:** việc bit 7 có giá trị 1 có thể là flag boolean, bit trạng thái, version hoặc phần của một số nguyên; cần dựa vào đặc tả protocol. `toUnsignedInt` chỉ giúp diễn giải **giá trị số của bit pattern**, không biết cấu trúc của field.

## 13. InputStream.read() đã trả int unsigned — đừng chuyển sớm sang byte

Một điểm rất quan trọng trong `java.io`: `InputStream.read()` trả về **int**, với:

- `0..255` cho một byte đọc thành công.
- `-1` khi đã tới EOF.

Vì sao không trả `byte`? Vì `-1` được dành làm **sentinel EOF** và các giá trị byte thật có thể gồm `0xFF`. Nếu trả signed byte, hai trường hợp này dễ bị nhầm.

**Sai:**

```java
// Phản ví dụ: làm mất thông tin EOF vs dữ liệu 0xFF.
byte raw = (byte) input.read();

// Nếu input.read() trả -1 (EOF), raw = -1.
// Nếu input.read() trả 255 (byte FF), raw cũng = -1.
```

**Đúng:**

```java
int value = input.read();

if (value == -1) {
    // EOF
} else {
    // value chắc chắn từ 0 tới 255.
}
```

`DataInputStream.readUnsignedByte()` cũng trả `int` 0..255. `DataInputStream.readUnsignedShort()` trả `int` 0..65535 và đọc 2 byte big-endian. `ByteBuffer.get()` thì trả **byte signed**, nên khi đọc qua ByteBuffer cần `Byte.toUnsignedInt(buffer.get())`.

### Ví dụ 10 — StreamUnsignedDemo.java

```java
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.InputStream;

public class StreamUnsignedDemo {
    public static void main(String[] args)
            throws Exception {
        byte[] payload = {
            (byte) 0x80,
            (byte) 0xFF,
            0x01
        };

        try (InputStream in =
                new ByteArrayInputStream(payload)) {
            System.out.println("first=" + in.read());
            System.out.println("second=" + in.read());
            System.out.println("third=" + in.read());
            System.out.println("eof=" + in.read());
        }

        try (DataInputStream in =
                new DataInputStream(
                    new ByteArrayInputStream(payload)
                )) {
            System.out.println(
                "dataUnsignedByte=" +
                in.readUnsignedByte()
            );
        }
    }
}
```

```bash
javac StreamUnsignedDemo.java
java StreamUnsignedDemo
```

Stdout:

```text
first=128
second=255
third=1
eof=-1
dataUnsignedByte=128
```

Khi đọc byte stream theo từng byte, **giữ kết quả ở int trước khi kiểm tra EOF**. Nếu bạn đã có `byte[]` hoặc `ByteBuffer.get()`, đó là signed byte; khi protocol cần unsigned, gọi `Byte.toUnsignedInt`.

## 14. Chuyển đổi unsigned không đồng nghĩa mở rộng số bit của protocol

Khi gọi `Byte.toUnsignedInt`:

- Số bit dữ liệu có ý nghĩa vẫn là **8**.
- Kiểu mang kết quả là **int 32 bit**, với 24 bit cao bằng zero.
- Không có việc tạo thêm giá trị thông tin mới.

Tương tự `Short.toUnsignedInt` giữ 16 bit có ý nghĩa và thêm zero ở 16 bit cao.

Điều này quan trọng khi ghi dữ liệu ngược vào protocol. Một số `int 255` có thể được encode thành byte `FF` nếu hợp đồng field là uint8. Nhưng số `int 256` **không thể mã hóa nguyên vẹn bằng một byte**; cần từ chối hoặc xử lý theo chính sách dữ liệu chứ không cast âm thầm.

### 14.1. byte và short không có toán học unsigned tự động

Sau khi đã có unsigned int, phép toán diễn ra theo **quy tắc int**:

```java
int u = Byte.toUnsignedInt((byte) 255);

int plusOne = u + 1; // 256, không tự wrap về 0
```

Nếu protocol định nghĩa arithmetic modulo 256, cần áp dụng mask có chủ đích:

```java
int wrapped = (u + 1) & 0xFF; // 0
```

Không tự thêm `&0xFF` sau mọi phép cộng vì điều đó có thể **che lỗi overflow/range**. Với count, length, offset hoặc số tiền, giá trị 256 khi input chỉ cho uint8 có thể phải **báo lỗi**, không wrap.

### 14.2. Overflow sau khi mở rộng

`Short.toUnsignedInt` trả tối đa 65535, phù hợp với `int`. Nhưng phép **nhân** hai số uint16 có thể vượt `Integer.MAX_VALUE`:

```java
// Ví dụ minh họa, Java:
int u = Short.toUnsignedInt((short) 0xFFFF);

int overflow = u * u;        // -131071 (int overflow)
long safe = (long) u * u;    // 4294836225
```

Việc ép sang `long` phải xảy ra **trước phép nhân**, không phải sau:

```java
long wrong = (long) (u * u); // Kết quả int đã overflow.
long right = (long) u * u;   // Đúng trong long.
```

Tương tự, đối với byte unsigned (tối đa 255), các phép cộng/tích lũy với lượng dữ liệu lớn vẫn có thể vượt `int`. Chọn miền số cho **toàn bộ phép toán**, không chỉ cho một phần tử.

### 14.3. Mở rộng nguyên thủy sang long

Khi `byte`/`short` được chuyển trực tiếp thành `long`, Java vẫn **sign-extend** nếu nguồn âm:

```java
byte b = -1;

long signed = b;                 // -1
long unsigned = Byte.toUnsignedLong(b); // 255
```

`Byte.toUnsignedLong` và `Short.toUnsignedLong` có từ Java 8, thích hợp khi caller muốn kiểu long trực tiếp. Nhưng nếu chỉ xử lý uint8/uint16 và không có lý do dùng long, `toUnsignedInt` là API rõ ràng và đủ rộng.

## 15. Ví dụ 11 — kiểm thử toàn miền thay vì chỉ vài giá trị mẫu

Với byte và short, miền không quá lớn: 256 giá trị uint8 và 65.536 giá trị uint16. Vì vậy một bộ test có thể kiểm tra **tất cả** các trường hợp:

```java
Byte.toUnsignedInt((byte)i) == i
// với 0 <= i <= 255

Short.toUnsignedInt((short)i) == i
// với 0 <= i <= 65535
```

### ExhaustiveRoundTripDemo.java

```java
public class ExhaustiveRoundTripDemo {
    public static void main(String[] args) {
        int badByte = 0;
        int badShort = 0;

        for (int i = 0; i <= 255; i++) {
            if (Byte.toUnsignedInt((byte) i) != i) {
                badByte++;
            }
        }

        for (int i = 0; i <= 65535; i++) {
            if (Short.toUnsignedInt((short) i) != i) {
                badShort++;
            }
        }

        System.out.println("byteCases=256");
        System.out.println(
            "byteMismatches=" + badByte
        );
        System.out.println("shortCases=65536");
        System.out.println(
            "shortMismatches=" + badShort
        );
    }
}
```

```bash
javac ExhaustiveRoundTripDemo.java
java ExhaustiveRoundTripDemo
```

Stdout:

```text
byteCases=256
byteMismatches=0
shortCases=65536
shortMismatches=0
```

Bài test đã đi qua **toàn bộ miền unsigned byte và short**. Đây là phép kiểm tra rất mạnh cho round-trip của phép ép bit và `toUnsignedInt`, nhưng **không tự kiểm tra** endianness, giới hạn độ dài packet hoặc các quy tắc nghiệp vụ của protocol; chúng cần test riêng.

## 16. Sự khác biệt với char, int và các API unsigned khác

### 16.1. char được mở rộng theo zero extension

`char` trong Java là kiểu 16 bit không dấu dùng cho **UTF-16 code unit**, không phải một số short signed. Khi chuyển `char` sang `int`, Java **zero-extend** chứ không sign-extend:

```java
char c = '\uFFFF';

int fromChar = c; // 65535

short s = (short) 0xFFFF;
int fromShort = s; // -1

int interpreted = Short.toUnsignedInt(s); // 65535
```

**Không coi char là kiểu uint16 thay thế trong mọi API:** `char` có vai trò xử lý ký tự/code units; việc dùng nó làm số của protocol có thể gây nhầm lẫn tên trường và ý nghĩa dữ liệu. Với unsigned short binary, dùng `int` trong phần tính toán và `short`/`byte[]` ở ranh giới lưu trữ là dễ hiểu hơn.

### 16.2. Integer.toUnsignedLong không giống Short.toUnsignedInt

Một `int` có 32 bit signed; `Integer.toUnsignedLong(int)` diễn giải nó như uint32 và trả `long` trong miền 0..4294967295. Nó là ví dụ tương tự nhưng ngoài trọng tâm 8/16 bit của bài.

Các hàm `Byte.toUnsignedInt`, `Short.toUnsignedInt`, `Byte.toUnsignedLong`, `Short.toUnsignedLong` đã có từ **Java 8**. `Byte.compareUnsigned` và `Short.compareUnsigned` xuất hiện ở **Java 9**. Nếu codebase có yêu cầu source/target Java 8, cân nhắc version của API khi biên dịch; không vì tính năng còn mới hơn mà lầm rằng nó là thành phần Java 8.

### 16.3. Không phải số âm nào cũng “nên chuyển unsigned”

Không bao giờ tự áp dụng `Byte.toUnsignedInt` cho mọi `byte` âm. Nếu giá trị trong một dữ liệu y tế/âm thanh được **quy định signed** thì `-1` thật sự có ý nghĩa -1. Chuyển sang 255 sẽ **sai ngữ nghĩa**. Hãy đọc schema/data format trước: unsigned conversion chỉ đúng khi field được **định nghĩa là không dấu**.

## 17. Một số tình huống ứng dụng thực tế

| Dữ liệu | Kiểu lưu/đọc | Cách diễn giải đúng |
| --- | --- | --- |
| Một kênh pixel 8 bit theo quy định unsigned | `byte` trong mảng | `Byte.toUnsignedInt(pixel)` |
| Octet của địa chỉ IPv4 | `byte` | 0..255 qua `toUnsignedInt` |
| Byte flags của header | `byte` | `int u=Byte.toUnsignedInt(b)` rồi mask/shift |
| Số thứ tự 16 bit unsigned | `short` | `Short.toUnsignedInt(s)` |
| Hai byte big-endian tạo uint16 | `byte[2]` | `(u0<<8)\|u1` |
| Đọc 2 byte từ DataInputStream | `int` | `readUnsignedShort()` vốn unsigned |
| ByteBuffer.getShort() | `short` | `Short.toUnsignedInt(buffer.getShort())` |
| InputStream.read() | `int` | Đã là 0..255; -1 dành cho EOF |
| Nạp text "255" vào uint8 | `int` parse | `Integer.parseInt`, validate 0..255, cast |
| Nhân hai uint16 | `int` input | Convert sang `long` trước phép nhân |
| Sort unsigned byte | `byte` | `Byte.compareUnsigned` (Java 9+) hoặc convert rồi compare |
| Ngày/giá trị được quy định signed | `byte`/`short` | Giữ signed, **không** tự convert |

### 17.1. Đọc độ dài và offset từ dữ liệu không tin cậy

Một protocol có trường length uint16 được đọc bằng `Short.toUnsignedInt` có thể trả tới 65535. Nhưng trước khi dùng làm offset/index phải xác minh:

- Buffer còn đủ byte để đọc header.
- Endian đúng.
- Trường length hợp lệ với spec, không vượt max business.
- Không vượt `remaining()` của buffer khi đọc payload.
- Khi tính `offset + length`, tránh overflow và kiểm tra ranh giới.
- Không dùng giá trị length âm theo signed khiến validation sai.

**Unsigned conversion không phải validation.** Nó chỉ biến bit thành một số không âm phù hợp miền biểu diễn; còn quy tắc protocol và kiểm tra an toàn bộ nhớ vẫn phải thực hiện.

### 17.2. Ghi lại giá trị unsigned

Nếu API nhận `int` trong miền 0..255, bạn có thể cast xuống `byte` để **lưu đúng 8 bit** sau khi validate. Khi ghi `OutputStream.write(int)`, nó ghi 8 bit thấp của int; nếu cần bảo toàn contract uint8, vẫn phải validate input trước khi gọi:

```java
// Đoạn minh họa:
int code = 255;

if (code < 0 || code > 255) {
    throw new IllegalArgumentException("uint8");
}

output.write(code);
```

Lời gọi `write(256)` sẽ chỉ ghi byte thấp `00` theo API, không tự báo rằng dữ liệu đầu vào ngoài miền unsigned byte. Vì thế **kiểm tra phạm vi trước khi ghi**, đừng phụ thuộc cast/bit truncation để làm validation.

## 18. Các lỗi phổ biến cần tránh

### Lỗi 1 — Cho rằng ép kiểu (int) là unsigned conversion

`(int)((byte)0xFF)` bằng -1, không phải 255. Dùng `Byte.toUnsignedInt`.

### Lỗi 2 — Cho rằng mở rộng long tự zero-extend

`long x = (byte)-1` vẫn là -1. Dùng `Byte.toUnsignedLong` nếu cần 255.

### Lỗi 3 — Coi short unsigned luôn có thể chứa bằng short signed dương

`65535` không thể là giá trị dương của `short`; lưu bits bằng `(short)65535` rồi dùng `Short.toUnsignedInt` để đọc số.

### Lỗi 4 — Cast trước khi kiểm tra phạm vi

`(byte)256` thành 0; `(short)65536` thành 0. Validate `0..255`/`0..65535` ở `int` trước.

### Lỗi 5 — Dùng Byte.parseByte("255") đọc uint8

Parser này dành cho signed byte. Dùng `Integer.parseInt` và kiểm tra miền.

### Lỗi 6 — Thực hiện phép dịch >>> trực tiếp trên byte âm

Operand được sign-extend lên int. Dùng `Byte.toUnsignedInt` hoặc mask trước khi shift.

### Lỗi 7 — Ghép hai byte bằng shift/OR không mask

Byte âm bị sign extension. Đổi từng byte sang unsigned int trước khi ghép.

### Lỗi 8 — Nhầm endian với signedness

`Short.toUnsignedInt` không sửa byte order. Phải chọn big/little-endian theo format.

### Lỗi 9 — Chuyển InputStream.read() thành byte trước khi kiểm tra EOF

`-1` (EOF) và `255` (FF) đều thành byte -1. Giữ kết quả int cho tới khi kiểm tra EOF.

### Lỗi 10 — Dùng Arrays.toString(byte[]) để diễn giải octet unsigned

Nó in số signed. In qua `Byte.toUnsignedInt` khi format dữ liệu là unsigned.

### Lỗi 11 — Dùng Byte.compare khi cần thứ tự unsigned

Các octet ≥128 sẽ là số âm, nên sort không đúng. Dùng `compareUnsigned` (Java 9+) hoặc so giá trị đã convert.

### Lỗi 12 — Sử dụng compareUnsigned không kiểm tra yêu cầu Java 8

`Byte.compareUnsigned`/`Short.compareUnsigned` từ Java 9; nếu source Java 8, dùng `Integer.compare(Byte.toUnsignedInt(...),...)`.

### Lỗi 13 — Nghĩ sau khi toUnsignedInt thì mọi phép toán không thể overflow

`int u=65535; u*u` có thể overflow. Đưa phép toán cần miền lớn lên `long` trước khi tính.

### Lỗi 14 — Mask mọi kết quả tính toán để “cho vừa”

`(value & 0xFF)` là modulo 256, có thể che giá trị ngoài miền. Chỉ dùng khi protocol định nghĩa wrap.

### Lỗi 15 — Mặc định mọi dữ liệu byte âm đều phải unsigned

Nếu field quy định signed, kết quả -1 có thể là giá trị hợp lệ. Schema quyết định.

### Lỗi 16 — Lẫn chiều rộng lưu trữ và chiều rộng giá trị xử lý

`Byte.toUnsignedInt` trả int 32 bit nhưng dữ liệu vẫn chỉ chứa 8 bit thông tin; không thay kích thước payload.

### Lỗi 17 — Dùng char thay short unsigned mà không có lý do

`char` là UTF-16 code unit; có quy tắc zero-extension riêng, nhưng không phải một kiểu numeric uint16 tổng quát phù hợp mọi API.

### Lỗi 18 — Đọc field length mà không kiểm tra remaining/buffer bounds

Unsigned 0..65535 không có nghĩa giá trị đó hợp lệ với kích thước packet thực tế. Validate length và offset.

## 19. Checklist khi code review

1. Data format định nghĩa field là signed hay unsigned?
2. Field có độ rộng 8 hay 16 bit?
3. Kiểu lưu bit là byte, short, byte array hay ByteBuffer?
4. Dữ liệu từ `InputStream.read` đã được trả dưới dạng int 0..255 chưa?
5. Có kiểm tra EOF ở int trước khi cast sang byte không?
6. Khi mở rộng byte/short, cần sign extension hay zero extension?
7. Có dùng `Byte.toUnsignedInt`/`Short.toUnsignedInt` thay cho cast `(int)` khi cần unsigned không?
8. Nếu dùng mask, mask đã đúng `0xFF` hoặc `0xFFFF` chưa?
9. Phép shift có chạy trên int đã được zero-extend chưa?
10. Có xác định big/little-endian trước khi ghép nhiều byte không?
11. `ByteBuffer.getShort` được convert nếu field là uint16 chưa?
12. Input text được parse trong kiểu đủ rộng rồi validate 0..255/0..65535 chưa?
13. Có cast xuống byte/short **sau khi** validate không?
14. Các trường length, offset, count có kiểm tra giới hạn business/buffer không?
15. Có tránh overflow trong cộng/nhân bằng `long` trước phép toán cần thiết không?
16. Khi sort/compare, semantics có phải unsigned không?
17. Có xét phiên bản JDK trước khi dùng `Byte.compareUnsigned`/`Short.compareUnsigned` không?
18. Có test 0, max signed, min signed và max unsigned chưa?
19. Có test byte `0x80`, `0xFF` và short `0x8000`, `0xFFFF` chưa?
20. Có test endianness với cặp byte khác nhau như `AB CD` chưa?
21. Có test toàn bộ 256/65536 trường hợp round-trip khi điều kiện cho phép không?
22. Có tránh nhầm một giá trị unsigned hợp lệ với lỗi EOF hoặc dấu âm không?
23. Nếu ghi ra protocol, có validate trước khi `OutputStream.write` hoặc cast không?
24. Log/hiển thị của các octet unsigned có phản ánh đúng giá trị 0..255 không?
25. Có tài liệu hóa field interpretation để người bảo trì không đoán từ kiểu Java không?

## 20. Câu hỏi tự kiểm tra

**1.** `byte b=(byte)0xFF; int x=b;` — x bằng bao nhiêu?

**Đáp án:** -1 do sign extension.

**2.** `Byte.toUnsignedInt((byte)0xFF)` bằng bao nhiêu?

**Đáp án:** 255.

**3.** `Short.toUnsignedInt((short)0xFFFF)` bằng bao nhiêu?

**Đáp án:** 65535.

**4.** `(int)(short)-1` có phải 65535 không?

**Đáp án:** Không, nó là -1.

**5.** Hai biểu thức `Byte.toUnsignedInt(b)` và `b & 0xFF` có cùng giá trị không?

**Đáp án:** Có, đối với mọi `byte b`.

**6.** Với short thì mask phù hợp là gì?

**Đáp án:** `s & 0xFFFF`.

**7.** Khi nào `(byte)255` có thể là cách lưu dữ liệu đúng?

**Đáp án:** Khi input đã được xác nhận là unsigned 8-bit value và cần lưu đúng 8 bit `FF`. Giá trị `byte` sẽ hiển thị -1.

**8.** Vì sao `Byte.parseByte("255")` ném lỗi?

**Đáp án:** Vì parser nhận signed byte tối đa 127.

**9.** `InputStream.read()` trả gì cho byte `FF`?

**Đáp án:** 255, không phải -1.

**10.** `InputStream.read()` trả `-1` khi nào?

**Đáp án:** Khi EOF.

**11.** Vì sao `b>>>4` với b=(byte)F0 không ra 15?

**Đáp án:** Vì b được sign-extend thành int trước khi shift logic.

**12.** Hai byte `FF FE` big-endian tạo uint16 bao nhiêu?

**Đáp án:** 65534.

**13.** ByteBuffer.getShort() trả signed hay unsigned short?

**Đáp án:** Signed short. Dùng `Short.toUnsignedInt` nếu field là unsigned.

**14.** Big-endian `AB CD` và little-endian `AB CD` có cùng giá trị uint16 không?

**Đáp án:** Không; lần lượt 43981 và 52651.

**15.** Byte.compareUnsigned có từ Java 8 không?

**Đáp án:** Không, từ Java 9. Java 8 có thể so `Integer.compare(Byte.toUnsignedInt(a),Byte.toUnsignedInt(b))`.

**16.** `Byte.toUnsignedInt` có thay đổi bit trong byte gốc không?

**Đáp án:** Không, chỉ diễn giải bằng int với zero extension.

**17.** Vì sao `65535*65535` nguy hiểm trong int?

**Đáp án:** Kết quả 4294836225 vượt miền int signed, cần long trước khi nhân.

**18.** char và short được widen lên int giống nhau không?

**Đáp án:** Không; char zero-extend, short signed sign-extend.

**19.** Vì sao test toàn 65.536 giá trị short có ích?

**Đáp án:** Xác minh round-trip bit interpretation của mọi uint16, không bỏ sót ranh giới.

**20.** Có nên luôn áp dụng toUnsignedInt cho một byte âm không?

**Đáp án:** Không, chỉ khi định dạng dữ liệu quy định field unsigned.

**21.** Nếu uint8 field chứa 256, cast về byte rồi lấy unsigned lại có phục hồi được 256 không?

**Đáp án:** Không, sẽ thu được 0 vì 256 không nằm trong 8 bit.

**22.** Dùng toUnsignedInt cho field length đã đủ bảo vệ việc đọc buffer chưa?

**Đáp án:** Chưa; còn cần kiểm tra tính hợp lệ của length, buffer remaining và overflow offset.

## 21. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 25 — Byte](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Byte.html): `toUnsignedInt`, `toUnsignedLong`, `compareUnsigned`, signed `parseByte`.
- [Oracle Java SE 25 — Short](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Short.html): `toUnsignedInt`, `toUnsignedLong`, `compareUnsigned`, `parseShort`.
- [Java Language Specification `5.1.2 — Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html): sign extension của signed integers, zero extension của `char`.
- [Oracle Java SE 25 — InputStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStream.html): `read()` trả int 0..255 hoặc -1 khi EOF.
- [Oracle Java SE 25 — DataInputStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/DataInputStream.html): `readUnsignedByte()`/`readUnsignedShort()`.
- [Oracle Java SE 25 — ByteBuffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html): `get()`, `getShort()` và byte order.
- [Oracle Java SE 25 — Integer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html): `parseInt` và công cụ diễn giải số nguyên.

**Ghi nhớ:** `byte`/`short` luôn có dấu trong Java; ép rộng bằng `(int)` là **sign extension**. `Byte.toUnsignedInt` và `Short.toUnsignedInt` là **zero extension theo độ rộng 8/16 bit**, trả các miền số 0..255 và 0..65535. Chúng **không thay bit gốc**, không tự xử lý endianness, overflow, validation hay cấu trúc protocol. Hãy chuyển sang unsigned `int` khi ý nghĩa dữ liệu yêu cầu, kiểm tra range trước khi ghi/cast, và giữ kiểu đủ rộng cho các phép toán tiếp theo.
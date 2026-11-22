# Biểu diễn bit của số nguyên có dấu — Java 17+

Java biểu diễn các kiểu **số nguyên có dấu** `byte`, `short`, `int` và `long` bằng **bù hai** (*two's complement*) với độ rộng cố định. Đọc đúng mẫu bit giúp hiểu số âm, phép toán bit, phép dịch, mở rộng dấu và tràn số.

Ví dụ với **8 bit**:

~~~text
Giá trị     8 bit nhị phân    Hex
     5      0000 0101         0x05
    -5      1111 1011         0xFB
     0      0000 0000         0x00
    -1      1111 1111         0xFF
  -128      1000 0000         0x80
   127      0111 1111         0x7F
~~~

**Điểm cốt lõi:** bit cao nhất là **bit dấu** trong cách diễn giải có dấu: 0 ở đầu chỉ giá trị không âm, 1 ở đầu chỉ giá trị âm. Nhưng **không** phải chỉ cần đổi bit đầu tiên để đổi dấu; toàn bộ các bit được diễn giải theo quy tắc **bù hai**.

## 1. Độ rộng và miền giá trị của từng kiểu

| Kiểu | Số bit | Miền giá trị có dấu |
| --- | ---: | --- |
| `byte` | 8 | −128 đến 127 |
| `short` | 16 | −32.768 đến 32.767 |
| `int` | 32 | −2.147.483.648 đến 2.147.483.647 |
| `long` | 64 | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |

Với độ rộng `w`, miền bù hai là:

\[
-2^{w-1}\ \leq\ x\ \leq\ 2^{w-1}-1
\]

Mẫu bit bằng 0 biểu diễn số 0; mẫu có bit cao nhất bằng 1 biểu diễn số âm. Miền **bất đối xứng**: có một giá trị âm nhiều hơn các giá trị dương; vì vậy, ví dụ, `Integer.MIN_VALUE` không có số đối dương trong `int`.

**Phân biệt:** `char` cũng rộng **16 bit** nhưng là **đơn vị mã UTF-16 không dấu**, giá trị 0 đến 65.535. `boolean` không phải kiểu số nguyên dùng để thao tác các bit dấu.

## 2. Bù hai hoạt động thế nào?

Với mẫu bit độ rộng `w`, có thể diễn giải giá trị theo **trọng số bit**:

- Các bit từ vị trí 0 đến `w-2` mang trọng số dương `2^i`.
- Bit cao nhất, vị trí `w-1`, mang trọng số **`-2^(w-1)`**.

Ví dụ `11111011` (8 bit):

~~~text
Bit:       1   1  1  1  1  0  1  1
Trọng số: -128 64 32 16  8  4  2  1

Giá trị: -128 + 64 + 32 + 16 + 8 + 0 + 2 + 1 = -5
~~~

Một cách dựng mẫu bit âm từ số dương trong độ rộng cố định:

1. Viết giá trị dương thành đúng `w` bit.
2. **Đảo tất cả bit** (0 ↔ 1).
3. **Cộng 1**, giữ đúng `w` bit thấp.

~~~text
 +5:          0000 0101
 Đảo bit:     1111 1010
 Cộng 1:      1111 1011    => -5
~~~

Quy tắc này áp dụng cho mẫu bit ở độ rộng cố định. Không thể tạo `+128` trong kiểu `byte` để đổi dấu `-128` mà vẫn giữ kiểu `byte`: `+128` nằm ngoài miền.

### Quan hệ với diễn giải không dấu

Cùng mẫu bit 8-bit `11111011` có thể được đọc là:

- **Có dấu:** `-5`.
- **Không dấu:** `251`.

Nếu một mẫu `w` bit có giá trị không dấu `u`, giá trị có dấu là:

~~~text
Nếu bit cao nhất = 0:  signed = u
Nếu bit cao nhất = 1:  signed = u - 2^w
~~~

Đây là **hai cách diễn giải cùng một mẫu bit**, không phải hai dãy bit khác nhau.

## 3. Chương trình Java 17+ độc lập và runnable

Tạo tệp UTF-8 tên **`SignedIntegerBitsDemo.java`**:

~~~java
public class SignedIntegerBitsDemo {
    private static String padded(String bits, int width) {
        return "0".repeat(width - bits.length()) + bits;
    }

    private static String bits8(int n) {
        return padded(Integer.toBinaryString(n & 0xFF), 8);
    }

    private static String bits16(int n) {
        return padded(Integer.toBinaryString(n & 0xFFFF), 16);
    }

    private static String bits32(int n) {
        return padded(Integer.toBinaryString(n), 32);
    }

    private static String bits64(long n) {
        return padded(Long.toBinaryString(n), 64);
    }

    public static void main(String[] args) {
        System.out.println("== widths and ranges ==");
        System.out.println("byte=" + Byte.SIZE + ":"
                + Byte.MIN_VALUE + ".." + Byte.MAX_VALUE);
        System.out.println("short=" + Short.SIZE + ":"
                + Short.MIN_VALUE + ".." + Short.MAX_VALUE);
        System.out.println("int=" + Integer.SIZE + ":"
                + Integer.MIN_VALUE + ".." + Integer.MAX_VALUE);
        System.out.println("long=" + Long.SIZE + ":"
                + Long.MIN_VALUE + ".." + Long.MAX_VALUE);

        System.out.println("== two's complement ==");
        System.out.println("byte5=" + bits8(5));
        System.out.println("byteMinus5=" + bits8(-5));
        System.out.println("byteMinus1=" + bits8(-1));
        System.out.println("byteMin=" + bits8(Byte.MIN_VALUE));
        System.out.println("byteMax=" + bits8(Byte.MAX_VALUE));
        System.out.println("intMinus5=" + bits32(-5));
        System.out.println("longMinus1=" + bits64(-1L));
        System.out.println("intMinHex="
                + Integer.toHexString(Integer.MIN_VALUE));
        System.out.println("minusOneHex="
                + Integer.toHexString(-1));
        System.out.println("notFour=" + (~4));
        System.out.println("negateFive=" + (~5 + 1));

        System.out.println("== sign extension ==");
        byte minusOne = -1;
        int widened = minusOne;
        System.out.println("widenedValue=" + widened);
        System.out.println("widenedHex="
                + Integer.toHexString(widened));
        System.out.println("lowByte=" + bits8(widened));
        System.out.println("maskedByte=" + (minusOne & 0xFF));
        System.out.println("unsignedByte="
                + Byte.toUnsignedInt(minusOne));

        short minusTwo = -2;
        System.out.println("shortBits=" + bits16(minusTwo));
        System.out.println("widenedShortHex="
                + Integer.toHexString(minusTwo));
        System.out.println("unsignedShort="
                + Short.toUnsignedInt(minusTwo));

        char maximumChar = (char) 0xFFFF;
        System.out.println("charValue=" + (int) maximumChar);
        System.out.println("charBits=" + bits16(maximumChar));
        System.out.println("castFFToByte=" + ((byte) 0xFF));

        System.out.println("== shifts ==");
        int negative = -8;
        System.out.println("minus8=" + bits32(negative));
        System.out.println("arithmeticRight=" + (negative >> 1));
        System.out.println("arithmeticBits="
                + bits32(negative >> 1));
        System.out.println("logicalRight=" + (negative >>> 1));
        System.out.println("logicalBits="
                + bits32(negative >>> 1));
        System.out.println("longLogicalRight="
                + (-8L >>> 1));
        System.out.println("byteShift=" + ((byte) -8 >> 1));
        System.out.println("oneShift32=" + (1 << 32));

        System.out.println("== limits ==");
        System.out.println("intOverflow="
                + (Integer.MAX_VALUE + 1));
        System.out.println("negatedIntMin="
                + (-Integer.MIN_VALUE));
        System.out.println("leadingZerosOne="
                + Integer.numberOfLeadingZeros(1));
        System.out.println("leadingZerosMinusOne="
                + Integer.numberOfLeadingZeros(-1));
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) trong thư mục chứa file, dùng **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 SignedIntegerBitsDemo.java
java SignedIntegerBitsDemo
~~~

**Exact expected stdout** của riêng lệnh `java SignedIntegerBitsDemo`:

~~~text
== widths and ranges ==
byte=8:-128..127
short=16:-32768..32767
int=32:-2147483648..2147483647
long=64:-9223372036854775808..9223372036854775807
== two's complement ==
byte5=00000101
byteMinus5=11111011
byteMinus1=11111111
byteMin=10000000
byteMax=01111111
intMinus5=11111111111111111111111111111011
longMinus1=1111111111111111111111111111111111111111111111111111111111111111
intMinHex=80000000
minusOneHex=ffffffff
notFour=-5
negateFive=-5
== sign extension ==
widenedValue=-1
widenedHex=ffffffff
lowByte=11111111
maskedByte=255
unsignedByte=255
shortBits=1111111111111110
widenedShortHex=fffffffe
unsignedShort=65534
charValue=65535
charBits=1111111111111111
castFFToByte=-1
== shifts ==
minus8=11111111111111111111111111111000
arithmeticRight=-4
arithmeticBits=11111111111111111111111111111100
logicalRight=2147483644
logicalBits=01111111111111111111111111111100
longLogicalRight=9223372036854775804
byteShift=-4
oneShift32=1
== limits ==
intOverflow=-2147483648
negatedIntMin=-2147483648
leadingZerosOne=31
leadingZerosMinusOne=0
~~~

Hai lệnh kiểm tra phiên bản JDK in thông tin tùy máy, không thuộc khối stdout cố định. `bits8` và `bits16` trong demo **che các bit cao** bằng mask trước khi in, nhằm quan sát **đúng 8/16 bit** thay vì vô tình in mẫu `int` đã mở rộng dấu.

## 4. Tại sao số âm in ra nhiều bit 1?

~~~java
System.out.println(Integer.toBinaryString(-1));
~~~

Với `int` 32 bit, `-1` có mẫu bù hai gồm **32 bit 1**. `Integer.toBinaryString` trả **chuỗi bit theo biểu diễn bù hai của `int`**; đối với số âm, chuỗi có độ dài 32.

Tuy nhiên, với một `byte`:

~~~java
byte value = -1;
System.out.println(Integer.toBinaryString(value));
~~~

Kết quả vẫn là **32 bit 1**, vì `byte` được **nâng thành `int` trước khi truyền tham số**. Muốn xem đúng 8 bit thấp:

~~~java
byte value = -1;
String eightBits = Integer.toBinaryString(value & 0xFF);
// eightBits == "11111111".
~~~

Với số dương, `Integer.toBinaryString(5)` chỉ in `101` chứ **không tự đệm đủ 32 bit**. Hàm `padded` trong chương trình giúp tạo chuỗi đúng độ rộng để đối chiếu.

**Chú ý:** hiển thị hex/binary là biểu diễn dữ liệu, không biến một số âm thành số dương chỉ vì không có dấu trừ trong chuỗi. `Integer.toHexString(-1)` là `"ffffffff"`, tương ứng mẫu 32 bit bù hai.

## 5. Mở rộng dấu khi chuyển `byte`/`short` sang `int`

Khi chuyển kiểu số nguyên **có dấu** hẹp sang kiểu rộng, Java giữ nguyên giá trị bằng cách **mở rộng bit dấu** (*sign extension*).

~~~text
byte  -1:           11111111            (8 bit)
int   -1:  11111111111111111111111111111111  (32 bit)
~~~

Vì vậy:

~~~java
byte value = -1;
int wide = value;        // -1, khong phai 255.
int unsigned = value & 0xFF; // 255.
~~~

- `int wide = value` giữ **giá trị có dấu**.
- `value & 0xFF` giữ **8 bit thấp** rồi diễn giải thành số nguyên không âm 0–255.
- `Byte.toUnsignedInt(value)` thể hiện rõ mục đích đọc `byte` như số không dấu.

Với `short` có thể dùng `Short.toUnsignedInt(value)` để đọc 16 bit dưới dạng 0–65.535.

### Vì sao `char` khác `short`?

Cả hai đều có 16 bit, nhưng:

~~~java
short signed = -1;
char unsigned = (char) 0xFFFF;

int fromShort = signed;    // -1.
int fromChar = unsigned;   // 65535.
~~~

`short` **mở rộng dấu** khi chuyển sang `int`; `char` **mở rộng với bit 0** vì là đơn vị mã **không dấu**. Không dùng `char` như một “unsigned short” thay thế tùy tiện trong mã thao tác ký tự vì `char` có ý nghĩa riêng về UTF-16.

## 6. Số âm khi dịch bit

Mẫu bit có dấu cũng giải thích vì sao các phép dịch phải cho kết quả khác nhau. Với `int -8` (`0xFFFFFFF8`), `>>` lấp bit dấu 1, còn `>>>` lấp bit 0:

~~~java
System.out.println(-8 >> 1);  // -4: vẫn âm.
System.out.println(-8 >>> 1); // 2147483644: bit cao mới bằng 0.
~~~

`<<` dịch trái và chèn bit 0 ở bên phải; các bit vượt ngoài độ rộng `int`/`long` bị bỏ. Đây là phép thao tác bit, không phải phép nhân luôn an toàn trước tràn. `byte`, `short`, `char` được nâng thành `int` trước phép dịch; `int` dùng 5 bit thấp của khoảng dịch, `long` dùng 6 bit thấp. Vì thế `1 << 32` là 1. Các bài về dịch bit phân tích riêng từng cơ chế và trường hợp biên.

## 7. Đảo bit, đổi dấu và tràn số

Trong biểu diễn bù hai với độ rộng cố định, `~x` đảo toàn bộ bit và `-x == ~x + 1` theo phép toán số nguyên của Java. Ví dụ `~4` là -5; `~5 + 1` cũng là -5. Tràn không tự gây ngoại lệ: `Integer.MAX_VALUE + 1` và `-Integer.MIN_VALUE` đều cho `Integer.MIN_VALUE`.

~~~java
int min = Integer.MIN_VALUE;
System.out.println(-min);            // -2147483648 (tràn int).
System.out.println(-(long) min);     // 2147483648 (nâng trước).
~~~

Nếu cần phát hiện tràn trong tính toán nghiệp vụ, chọn `Math.addExact`/`Math.negateExact`; nếu cần miền lớn hơn `long`, dùng `BigInteger`. Chính độ rộng và cách diễn giải có dấu của mẫu bit quyết định kết quả.

## 8. Cách đọc literal nhị phân và hex

Java hỗ trợ literal cơ số 2 với tiền tố `0b` và cơ số 16 với tiền tố `0x`:

~~~java
int positive = 0b0000_0101; // 5.
int mask = 0xFF;           // 255.
byte minusOne = (byte) 0xFF; // -1, giu 8 bit thap.
~~~

Các dấu gạch dưới chỉ để dễ đọc literal, không thay đổi giá trị.

**Đừng nhầm literal `0xFF` với `byte -1`**: không có cast, `0xFF` là số nguyên dương 255 kiểu `int`. Khi thu hẹp xuống `byte`, mẫu 8 bit thấp `11111111` được diễn giải thành **-1**.

Các literal hex/binary `int` có thể thể hiện trọn 32 bit, vì thế literal như `0x80000000` tương ứng mẫu bit của `Integer.MIN_VALUE`. Việc cùng một dãy bit mang ý nghĩa âm hoặc dương phụ thuộc **độ rộng và cách diễn giải có dấu/không dấu**.

## 9. Dữ liệu trong bộ nhớ và mẫu bit không phải cùng vấn đề với thứ tự byte

Biểu diễn **bù hai** trả lời câu hỏi: *những bit nào biểu diễn một giá trị số nguyên có dấu?* Còn **endianness** (big-endian/little-endian) trả lời câu hỏi khác: *khi nhiều byte được lưu/truyền, byte nào xuất hiện trước?*

Ví dụ một `int` rộng 32 bit có thể có cùng giá trị và cùng 32 bit về mặt số học, nhưng trật tự bốn byte trong một định dạng nhị phân cần tuân theo quy ước lưu trữ/truyền tải. Khi đọc file hoặc giao thức, phải chọn rõ byte order (ví dụ qua `ByteBuffer.order(...)`); không suy ra endianness từ việc thấy số âm có bit dấu bằng 1.

## 10. Những lỗi thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Số âm chỉ khác số dương ở bit dấu.” | Bù hai liên quan **toàn bộ mẫu bit**, không chỉ đảo bit đầu |
| “`byte -1` khi sang `int` thành 255.” | Chuyển kiểu có dấu **mở rộng dấu**, vẫn là -1 |
| “`Integer.toBinaryString(byte âm)` in 8 bit.” | `byte` bị nâng thành `int`, thường in 32 bit nếu âm |
| “`0xFF` mặc định là `byte -1`.” | `0xFF` là 255 kiểu `int` |
| “`char` 16 bit nên là kiểu số nguyên có dấu.” | `char` là đơn vị mã UTF-16 **không dấu** |
| “`>>` và `>>>` giống nhau với số âm.” | `>>` điền bit dấu; `>>>` điền 0 |
| “`1 << 32` cho 0.” | Với `int`, khoảng dịch được mask; kết quả là 1 |
| “`-Integer.MIN_VALUE` luôn thành số dương.” | Tràn `int` nên vẫn là `MIN_VALUE` |
| “Bù hai cho biết thứ tự các byte trong bộ nhớ.” | Endianness là vấn đề khác |

## 11. Bài tập tự kiểm tra

1. Biểu diễn `-1` ở độ rộng 8 bit?  
   *Đáp án:* `11111111`.
2. Dãy 8 bit `11111011` được hiểu là số có dấu bao nhiêu? Không dấu bao nhiêu?  
   *Đáp án:* **-5** và **251**.
3. Vì sao `byte b = -1; int x = b;` cho `x = -1` chứ không phải 255?  
   *Đáp án:* Mở rộng bit dấu khi chuyển có dấu sang kiểu rộng.
4. Viết cách lấy mẫu byte `-1` dưới dạng `int` không dấu 255.  
   *Đáp án:* `b & 0xFF` hoặc `Byte.toUnsignedInt(b)`.
5. `-8 >> 1` và `-8 >>> 1` lần lượt bằng bao nhiêu?  
   *Đáp án:* **-4** và **2147483644**.
6. `1 << 32` bằng bao nhiêu với toán hạng `int`?  
   *Đáp án:* **1**, vì khoảng dịch dùng 5 bit thấp.
7. `~4` bằng bao nhiêu trong `int`?  
   *Đáp án:* **-5**.
8. `Integer.MAX_VALUE + 1` cho gì?  
   *Đáp án:* **Integer.MIN_VALUE = -2147483648**, do tràn `int`.
9. `short s = -1; char c = (char) 0xFFFF;`; khi chuyển sang `int`, `s` và `c` khác thế nào?  
   *Đáp án:* `s` thành **-1**, `c` thành **65535**.

## Checklist

- [ ] Biết `byte`, `short`, `int` và `long` là các kiểu nguyên **có dấu, bù hai**, rộng 8/16/32/64 bit.
- [ ] Giải thích được vì sao bit cao nhất có trọng số âm và mẫu `111...111` bằng -1.
- [ ] Hiểu cách tạo bù hai: đảo bit rồi cộng 1 trong độ rộng cố định.
- [ ] Phân biệt cách diễn giải **có dấu** và **không dấu** của cùng mẫu bit.
- [ ] Biết chuyển `byte`/`short` âm sang `int` thực hiện **mở rộng dấu**.
- [ ] Dùng mask và `Byte.toUnsignedInt`/`Short.toUnsignedInt` khi cần đọc phần dữ liệu không dấu.
- [ ] Phân biệt `>>` (giữ dấu) và `>>>` (điền 0) và hiểu numeric promotion.
- [ ] Nhận diện overflow, `Integer.MIN_VALUE` và giới hạn khoảng cách dịch.
- [ ] Không nhầm bù hai với endianness.

**Kết luận:** Bù hai quy định cách Java diễn giải mẫu bit của số nguyên có dấu. Muốn dùng toán tử bit đúng, hãy luôn theo dõi **độ rộng kiểu**, **bit dấu**, **mở rộng/thu hẹp kiểu**, và **quy tắc dịch bit**, thay vì suy luận chỉ từ chuỗi 0/1 in ra.

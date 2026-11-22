# Mở rộng dấu khi nâng kiểu `byte` hoặc `short` trong Java

Trong Java, `byte` và `short` là **số nguyên có dấu** (*signed integers*). Khi chuyển từ `byte`/`short` sang một kiểu nguyên rộng hơn như `int` hoặc `long`, Java bảo toàn **giá trị số học**. Đối với số âm trong biểu diễn bù hai, điều đó đòi hỏi **mở rộng dấu** (*sign extension*): điền các bit `1` vào phần bit mới ở bên trái. Đối với giá trị không âm, các bit mới là `0`.

Hành vi này rất quan trọng khi xử lý byte nhị phân, mã màu, dữ liệu mạng, file và bitmask. Nếu muốn hiểu một mẫu 8/16 bit theo nghĩa **số không dấu**, cần diễn giải rõ ràng, chẳng hạn `b & 0xFF`, `s & 0xFFFF`, `Byte.toUnsignedInt(b)` hoặc `Short.toUnsignedInt(s)`.

## 1. Kiểu `byte` và `short` biểu diễn những gì?

| Kiểu Java | Số bit | Miền giá trị có dấu | Bit dấu |
| --- | ---: | --- | --- |
| `byte` | 8 | -128 đến 127 | Bit thứ 7 |
| `short` | 16 | -32768 đến 32767 | Bit thứ 15 |
| `int` | 32 | -2147483648 đến 2147483647 | Bit thứ 31 |
| `long` | 64 | -9223372036854775808 đến 9223372036854775807 | Bit thứ 63 |
| `char` | 16 | 0 đến 65535 | Không có bit dấu |

Java sử dụng biểu diễn **bù hai** (*two's complement*) cho kiểu nguyên có dấu. Chẳng hạn một byte gồm tám bit `1111_1111` được hiểu là `-1` nếu nhìn như `byte`, nhưng cũng có thể được hiểu là `255` nếu áp dụng quy ước *unsigned 8-bit*.

Trong Java **không có primitive `unsigned byte` hoặc `unsigned short`**. Dữ liệu thô thường được chứa trong `byte`/`short`; người lập trình cần chủ động chọn cách diễn giải có dấu hay không dấu khi tính toán.

### Minh họa hai cách diễn giải cùng một byte

```text
Bit gốc:            1111 1111
Đọc như byte signed:        -1
Đọc như unsigned 8-bit:    255

Bit gốc:            1000 0000
Đọc như byte signed:      -128
Đọc như unsigned 8-bit:    128
```

Hai cách nhìn không làm thay đổi tám bit gốc; chỉ thay đổi **ý nghĩa số học** của chúng. Ngay trong mã Java, literal `0xFF` có kiểu `int` và giá trị `255`; để giữ tám bit đó vào một `byte`, cần ép kiểu:

```java
byte raw = (byte) 0xFF; // bit 11111111, giá trị byte = -1
```

## 2. Cơ chế sign extension khi nâng lên `int` và `long`

Khi widening một giá trị số nguyên có dấu từ `byte` thành `short`, `int` hoặc `long`, Java **giữ nguyên giá trị có dấu**. Theo biểu diễn nhị phân bù hai, các bit được bổ sung ở bên trái bằng bit dấu của giá trị nguồn:

- Nếu bit dấu của giá trị nguồn là `0` (giá trị không âm), thêm các bit `0`.
- Nếu bit dấu là `1` (giá trị âm), thêm các bit `1`.

Ví dụ `byte b = -128` có bit gốc `1000_0000`. Khi nâng lên `int`:

```text
byte -128 (8 bit):
                            1000 0000
int -128  (32 bit):
1111 1111 1111 1111 1111 1111 1000 0000
          24 bit mới = toàn các bit 1
```

Kết quả được diễn giải thành `-128` trong `int`, **không thành +128**. Việc mở rộng dấu giữ nguyên giá trị âm thay vì coi bit dấu cũ là bit dữ liệu thông thường.

Với `byte b = 5`, bit gốc là `0000_0101`; khi nâng lên `int`, 24 bit thêm vào đều bằng `0` và kết quả vẫn là `5`.

### Bảng kết quả chuẩn

| Biểu thức | Giá trị số thập phân | Mẫu 32 bit dưới dạng hex |
| --- | ---: | --- |
| `(int) (byte) 0x7F` | 127 | `0x0000007F` |
| `(int) (byte) 0x80` | -128 | `0xFFFFFF80` |
| `(int) (byte) 0xFF` | -1 | `0xFFFFFFFF` |
| `(int) (short) 0x7FFF` | 32767 | `0x00007FFF` |
| `(int) (short) 0x8000` | -32768 | `0xFFFF8000` |
| `(int) (short) 0xFFFF` | -1 | `0xFFFFFFFF` |

Các cast từ literal `int` sang `byte`/`short` ở đây **thu hẹp số bit trước**, rồi cast `int` phía ngoài thực hiện sign extension. Không nên đọc chuỗi cast như một phép “bỏ qua dấu”.

## 3. Sign extension khác với zero extension

**Zero extension** là điền các bit `0` vào phần bên trái khi mở rộng. Với `byte`/`short` âm, chuyển kiểu nguyên thông thường sẽ thực hiện **sign extension**. Nếu dữ liệu thực sự là một số không dấu 8/16 bit, phải loại bỏ phần mở rộng dấu để lấy mẫu bit dưới dạng số dương.

Với `byte b = (byte) 0xFF`:

```text
b dưới dạng byte:  1111 1111             (signed -1)

Nâng kiểu bình thường:
int b:              FFFFFFFF             (signed -1)

Giữ tám bit thấp, điền 0 vào các bit còn lại:
b & 0xFF:          000000FF             (unsigned 255)
```

Dùng toán tử AND:

```java
byte b = (byte) 0xFF;
int signed = b;             // -1: mở rộng dấu
int unsigned = b & 0xFF;    // 255: giữ tám bit thấp

short s = (short) 0xFFFF;
int signedShort = s;        // -1
int unsignedShort = s & 0xFFFF; // 65535
```

Điều cốt lõi là `& 0xFF` **không biến kiểu `byte` thành unsigned**; nó tạo một biểu thức kiểu `int` có kết quả trong miền `0..255`. Với `short` và `& 0xFFFF`, kết quả nằm trong `0..65535`.

### Tại sao mặt nạ hoạt động?

Trong biểu thức `b & 0xFF`, `b` được nâng kiểu lên `int` **trước** khi phép AND xảy ra. Nếu `b == -1`, bit sau nâng kiểu là `0xFFFFFFFF`. Mặt nạ `0x000000FF` giữ tám bit thấp và xóa 24 bit cao:

```text
0xFFFFFFFF   // b = -1 sau sign extension
0x000000FF   // mặt nạ
----------
0x000000FF   // 255
```

Với `short`, mặt nạ `0x0000FFFF` giữ 16 bit thấp và xóa 16 bit cao. Mặt nạ cần phù hợp **chiều rộng của dữ liệu gốc**: `0xFF` cho byte, `0xFFFF` cho short.

## 4. API `Byte.toUnsignedInt` và `Short.toUnsignedInt`

Java có sẵn các phương thức biểu diễn giá trị có dấu thành giá trị không dấu tương ứng:

| Phương thức | Giá trị có dấu đầu vào | Giá trị `int` trả về |
| --- | --- | --- |
| `Byte.toUnsignedInt((byte) -1)` | -1 | 255 |
| `Byte.toUnsignedInt((byte) -128)` | -128 | 128 |
| `Byte.toUnsignedInt((byte) 127)` | 127 | 127 |
| `Short.toUnsignedInt((short) -1)` | -1 | 65535 |
| `Short.toUnsignedInt((short) -32768)` | -32768 | 32768 |

`Byte.toUnsignedInt(b)` tương đương về kết quả với `b & 0xFF`; `Short.toUnsignedInt(s)` tương đương `s & 0xFFFF`. Các method này có ý nghĩa rõ ràng khi người đọc gặp mã xử lý dữ liệu nhị phân.

```java
byte byteData = (byte) 0x80;
short shortData = (short) 0x8000;

int unsignedByte = Byte.toUnsignedInt(byteData);     // 128
int unsignedShort = Short.toUnsignedInt(shortData);  // 32768
```

Chú ý: `Byte.toUnsignedInt` nhận **`byte`**, không nhận mọi số nguyên. `Short.toUnsignedInt` nhận **`short`**. Muốn xem tám bit thấp của một giá trị `int`, biểu thức `value & 0xFF` thường trực tiếp và rõ ý hơn việc ép tạm sang `byte` rồi gọi method.

Đừng nhầm `Integer.toUnsignedLong(int)` với API trên: nó diễn giải **toàn bộ 32 bit** của một `int` theo miền `0..4294967295` và trả `long`; không thay thế cho yêu cầu chỉ lấy 8 hoặc 16 bit thấp của dữ liệu.

## 5. `char` được mở rộng bằng bit 0: trường hợp đối chiếu

`char` có 16 bit **không dấu**. Khi `char` được nâng lên `int`, Java điền các bit `0` ở phần cao và giữ giá trị trong khoảng `0..65535`. Ngược lại, `short` là kiểu **có dấu** nên hai giá trị có cùng 16 bit có thể cho kết quả `int` khác nhau.

```java
short signed = (short) 0xFFFF;  // -1
char unsigned = (char) 0xFFFF; // 65535

int fromShort = signed;   // -1, mẫu int là FFFFFFFF
int fromChar = unsigned;  // 65535, mẫu int là 0000FFFF
```

`char` trong Java đại diện một **UTF-16 code unit**; ví dụ trên chỉ dùng khả năng biểu diễn không dấu của nó để đối chiếu cách mở rộng bit. Không nên dùng `char` như một cách thay thế tổng quát cho số nguyên không dấu trong mọi API.

### Ép `byte` âm sang `char`: chi tiết cần cẩn thận

`byte` không thể tự động mở rộng sang `char` vì miền giá trị của hai kiểu không bao chứa nhau theo quy tắc widening primitive conversion. Ép tường minh có thể tạo kết quả bất ngờ:

```java
byte minusOne = -1;
// char invalid = minusOne; // lỗi biên dịch: cần cast

char castDirectly = (char) minusOne;      // 65535 (0xFFFF)
char lowEightBits = (char) (minusOne & 0xFF); // 255 (0x00FF)
```

Khi cast trực tiếp `byte` âm sang `char`, việc chuyển từ giá trị có dấu sang miền 16 bit của `char` cho `0xFFFF` trong trường hợp `-1`. Nếu mục tiêu là chuyển **một byte không dấu** thành code unit mang giá trị `0..255`, hãy che bằng `& 0xFF` trước.

## 6. Quy tắc unary/binary numeric promotion và phép toán bit

Không chỉ phép gán như `int x = b;` mới gây sign extension. Java thực hiện **nâng kiểu số học** (*numeric promotion*) với nhiều toán tử:

- `b + 1`, `b - 1`, `b * 2`: `byte` được nâng lên `int` trước khi tính.
- `~b`: toán tử bù bit làm việc trên giá trị `int` đã nâng kiểu.
- `b << 1`, `b >> 1` và `b >>> 1`: toán hạng trái `byte`/`short` được nâng lên `int` trước khi dịch bit.
- `b & mask`, `b | mask`, `b ^ mask`: thao tác bit trên kết quả sau binary numeric promotion.

Ví dụ `byte b = -1`:

```java
byte b = -1;
int promoted = b;     // -1, bit FFFFFFFF
int complement = ~b;  // 0, vì ~FFFFFFFF = 00000000
int shifted = b >> 1; // -1, dịch phải số học giữ bit dấu
```

Nếu người học chỉ hình dung `b` là tám bit `11111111`, có thể dự đoán sai kết quả của phép dịch hay của `~b`; hầu hết các biểu thức trên **đã làm việc với int 32 bit**.

### `>>` và `>>>` khi nguồn là byte âm

`>>` dịch phải có bảo toàn bit dấu của kiểu đã nâng; `>>>` dịch phải logic và điền `0`. Tuy nhiên **`>>>` không tự giới hạn phép dịch trong tám bit ban đầu**:

```java
byte b = -1;
int arithmetic = b >> 1;          // -1
int logicalOnInt = b >>> 1;       // 2147483647 (0x7FFFFFFF)
int logicalOnByte = (b & 0xFF) >>> 1; // 127 (0x7F)
```

Tại sao `b >>> 1` không ra 127? `b` đã trở thành `0xFFFFFFFF` kiểu `int`, nên phép dịch logic 32 bit ra `0x7FFFFFFF`. Để dịch **giá trị 8 bit không dấu**, áp dụng `& 0xFF` **trước phép dịch**.

Quy tắc tương tự với `short`: `(s & 0xFFFF) >>> 1` dịch giá trị không dấu 16 bit đúng mục đích.

## 7. Kết hợp nhiều byte thành một số nguyên không dấu

Khi ghép hai byte từ file hay giao thức mạng thành một số 16 bit **không dấu**, cần giữ đúng tám bit thấp của **từng byte** trước khi ghép.

Giả sử byte cao có bit `1000_0000` (`0x80`) và byte thấp là `1111_1111` (`0xFF`). Giá trị không dấu 16 bit mong muốn là `0x80FF` = `33023`.

```java
byte high = (byte) 0x80;  // -128
byte low = (byte) 0xFF;   // -1

int combined = ((high & 0xFF) << 8) | (low & 0xFF);
// combined = 0x80FF = 33023
```

Từng bước:

1. `high & 0xFF` biến mẫu `0x80` thành `128` kiểu `int`.
2. Dịch trái tám bit: `128 << 8` thành `0x8000` (32768).
3. `low & 0xFF` biến mẫu `0xFF` thành `255`.
4. Phép OR `0x8000 | 0x00FF` thu được `0x80FF` (33023).

**Lỗi phổ biến:** viết `(high << 8) | low` mà không mask sẽ khiến `low = -1` mở rộng thành `0xFFFFFFFF`, kéo toàn bộ kết quả OR thành `-1`, sai giá trị mong muốn.

Với dữ liệu giao thức, quy ước **byte order** (*big endian/little endian*) vẫn phải được biết từ đặc tả. Ví dụ trên giả định `high` là byte cao; sign extension chỉ là một phần của việc giải mã nhị phân đúng.

## 8. Ví dụ Java 17+ hoàn chỉnh và output

Tạo file **`SignExtensionDemo.java`**:

```java
public class SignExtensionDemo {
    public static void main(String[] args) {
        byte minusOne = (byte) 0xFF;
        byte minus128 = (byte) 0x80;
        short shortMinusOne = (short) 0xFFFF;
        short shortMin = (short) 0x8000;

        System.out.println("byteSigned=" + (int) minusOne);
        System.out.printf("byteBitsInt=%08X%n", (int) minusOne);
        System.out.println("byteUnsigned=" + (minusOne & 0xFF));
        System.out.println("byteUnsignedAPI=" + Byte.toUnsignedInt(minusOne));
        System.out.println("byte128Signed=" + (int) minus128);
        System.out.println("byte128Unsigned=" + Byte.toUnsignedInt(minus128));

        System.out.println("shortSigned=" + (int) shortMinusOne);
        System.out.printf("shortBitsInt=%08X%n", (int) shortMin);
        System.out.println("shortUnsigned=" + (shortMinusOne & 0xFFFF));
        System.out.println("shortUnsignedAPI=" + Short.toUnsignedInt(shortMin));

        char chars = (char) 0xFFFF;
        System.out.printf("charBitsInt=%08X%n", (int) chars);
        System.out.println("castByteToChar=" + (int) (char) minusOne);
        System.out.println("maskedByteToChar=" + (int) (char) (minusOne & 0xFF));

        System.out.println("arithmeticShift=" + (minusOne >> 1));
        System.out.println("logicalShiftInt=" + (minusOne >>> 1));
        System.out.println("logicalShiftByte=" + ((minusOne & 0xFF) >>> 1));
        System.out.println("bitwiseComplement=" + (~minusOne));

        byte high = (byte) 0x80;
        byte low = (byte) 0xFF;
        int combined = ((high & 0xFF) << 8) | (low & 0xFF);
        int wrongCombined = (high << 8) | low;
        System.out.println("combinedUnsigned16=" + combined);
        System.out.println("combinedWithoutMask=" + wrongCombined);

        System.out.println("signedComparison=" + (minusOne == 0xFF));
        System.out.println("unsignedComparison=" + ((minusOne & 0xFF) == 0xFF));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac SignExtensionDemo.java
java SignExtensionDemo
```

**Output đúng:**

```text
byteSigned=-1
byteBitsInt=FFFFFFFF
byteUnsigned=255
byteUnsignedAPI=255
byte128Signed=-128
byte128Unsigned=128
shortSigned=-1
shortBitsInt=FFFF8000
shortUnsigned=65535
shortUnsignedAPI=32768
charBitsInt=0000FFFF
castByteToChar=65535
maskedByteToChar=255
arithmeticShift=-1
logicalShiftInt=2147483647
logicalShiftByte=127
bitwiseComplement=0
combinedUnsigned16=33023
combinedWithoutMask=-1
signedComparison=false
unsignedComparison=true
```

Khi chạy, `printf("%08X")` in tám chữ số hex của biểu diễn `int`. Vì thế `FFFFFFFF` chứng tỏ dấu âm của byte `-1` đã mở rộng lên 32 bit; `0000FFFF` của `char` cho thấy 16 bit cao được điền bằng `0`.

## 9. Những nhầm lẫn thường gặp

| Hiểu nhầm | Quy tắc đúng |
| --- | --- |
| “`byte b = (byte) 0xFF` thì `int x = b` cho 255.” | `byte` có dấu: `b == -1`; khi nâng lên `int` vẫn `-1` vì sign extension. |
| “Cast `(int) b` loại bỏ phần dấu.” | Cast widening giữ nguyên giá trị signed và mở rộng bit dấu. |
| “`b & 0xFF` làm `b` trở thành unsigned.” | `b` không đổi; biểu thức tạo **`int`** dương từ tám bit thấp. |
| “`Short.toUnsignedInt(s)` mở rộng bằng dấu.” | API diễn giải `short` theo **16 bit không dấu** và trả `int` trong 0..65535. |
| “`byte` và `char` đều 8 bit.” | `byte` 8 bit signed; `char` 16 bit unsigned UTF-16 code unit. |
| “`(char) (byte) 0xFF` có giá trị 255.” | Cast trực tiếp byte `-1` sang char tạo `65535`; cần mask trước nếu muốn 255. |
| “`b >>> 1` dịch đúng tám bit của byte.” | `b` được nâng thành `int` 32 bit trước; để dịch unsigned 8 bit, mask trước. |
| “Ghép hai byte bằng `(high << 8) | low` luôn đúng.” | `low` âm mở rộng bit dấu; mask từng byte để không làm bẩn các bit cao. |
| “`(byte) 0xFF` là cách viết một kiểu unsigned byte mới.” | Cast về `byte` chỉ giữ tám bit thấp và diễn giải signed: kết quả `-1`. |
| “Sign extension làm giá trị âm đổi thành số dương.” | Sign extension **bảo toàn giá trị âm** khi chuyển sang kiểu nguyên rộng hơn. |

## 10. Quy trình kiểm tra mã xử lý bit

1. **Xác định kiểu nguồn:** `byte` 8 bit signed, `short` 16 bit signed, `char` 16 bit unsigned. Kiểu nguồn quyết định việc thêm các bit dấu hay bit `0`.
2. **Xác định ý nghĩa dữ liệu:** dữ liệu thật sự là số signed hay chỉ là 8/16 bit thô cần hiểu theo unsigned?
3. **Kiểm tra điểm nâng kiểu:** `int i = b`, `b + 1`, `b >> 1`, `b & mask` đều có thể làm việc với `int` đã sign-extend.
4. **Chuyển sang diễn giải unsigned trước khi tính nếu cần:** byte dùng `b & 0xFF` hoặc `Byte.toUnsignedInt(b)`; short dùng `s & 0xFFFF` hoặc `Short.toUnsignedInt(s)`.
5. **Khi dịch/ghép byte:** mask mỗi thành phần trước khi shift/OR; chú ý thứ tự byte do định dạng dữ liệu quy định.
6. **Kiểm tra bằng hex có độ rộng cố định:** `%08X` cho `int`, so sánh mẫu bit với kết quả số học; phân biệt giá trị signed và mẫu bit nguyên thủy.

**Ghi nhớ:** nâng `byte`/`short` âm lên `int`/`long` thực hiện **sign extension**, giữ giá trị âm bằng cách bổ sung bit `1`. Khi muốn đọc bit gốc như số **không dấu**, dùng **mặt nạ** hoặc **API unsigned** trước những phép toán mà độ rộng và dấu có thể ảnh hưởng kết quả.
# Biểu diễn số âm bằng bù hai (two's complement) trong Java

> **Java core – numbers · Kiểu số nguyên**  
> **Mục tiêu:** Đọc được mẫu bit của số nguyên âm; tự mã hóa/giải mã bù hai; hiểu vì sao Java dịch bit, mở rộng dấu và tràn số như vậy; áp dụng đúng khi xử lý byte, mask và dữ liệu nhị phân.

## 1. Vì sao cần biểu diễn số âm bằng bit?

Máy tính lưu bit `0` và `1`. Với cùng 8 bit, mẫu `11111011` không tự mang ý nghĩa “−5” hay “251”: **kiểu dữ liệu và quy ước diễn giải** quyết định ý nghĩa của nó. Nếu coi 8 bit là số nguyên **không dấu**, mẫu này bằng 251; nếu coi là số nguyên **có dấu theo bù hai**, nó bằng −5.

Java sử dụng biểu diễn bù hai cho các kiểu nguyên có dấu `byte`, `short`, `int` và `long`. Nhờ đó, cùng mạch cộng nhị phân có thể xử lý cả số dương và âm theo phép toán modulo một lũy thừa của hai. Bù hai cũng giải thích được mẫu bit của số âm, cách lan truyền dấu khi mở rộng kiểu và kết quả khi dịch bit.

Bài này chỉ xét **số nguyên độ rộng cố định**. `float`/`double` sử dụng quy tắc dấu phẩy động IEEE 754, **không** biểu diễn phần số âm của chúng theo bù hai. `char` là mã đơn vị UTF-16 16 bit không dấu; nó cũng không phải kiểu số nguyên âm.

## 2. Độ rộng bit, bit dấu và miền giá trị

Với **n bit**, có đúng `2^n` mẫu bit khác nhau. Trong bù hai:

- Bit bên trái cùng (bit cao nhất, **MSB**) là **bit dấu**: bằng `0` thì giá trị không âm; bằng `1` thì giá trị âm.
- Khoảng giá trị là **−2^(n−1) đến 2^(n−1) − 1**. Số âm ít nhất hơn số dương nhiều nhất một đơn vị vì có giá trị `0`.
- Bit bên phải cùng (bit thấp nhất, **LSB**) là bit số `0`; chỉ số bit tăng dần từ phải sang trái.

| Kiểu Java | Độ rộng | Miền giá trị | Bit dấu |
| --- | ---: | --- | ---: |
| `byte` | 8 | −128 đến 127 | 7 |
| `short` | 16 | −32.768 đến 32.767 | 15 |
| `int` | 32 | −2.147.483.648 đến 2.147.483.647 | 31 |
| `long` | 64 | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | 63 |

Ví dụ 8 bit:

```text
Bit index:      7 6 5 4 3 2 1 0
                ^             ^
             bit dấu         LSB

 0000 0000 =    0
 0000 0001 =   +1
 0111 1111 = +127
 1000 0000 = -128
 1111 1110 =   -2
 1111 1111 =   -1
```

**Không phải** “bit đầu là dấu, 7 bit còn lại là trị tuyệt đối”. Đó là một cách biểu diễn khác tên *sign–magnitude*. Trong bù hai, toàn bộ 8 bit cùng tham gia giá trị theo quy tắc riêng; `1000 0000` là **−128**, không phải “−0”. Vì thế bù hai có một biểu diễn duy nhất cho số không ở độ rộng cố định.

## 3. Từ số dương sang số âm: đảo bit rồi cộng 1

Để tìm biểu diễn **−x** với `x > 0` và `x` nằm trong phạm vi biểu diễn phù hợp của độ rộng đang xét:

1. Viết `+x` bằng **đủ n bit**, thêm `0` bên trái nếu cần.
2. **Đảo tất cả n bit**: `0 ↔ 1` (bù một / one's complement).
3. **Cộng 1**, giữ n bit thấp nếu có bit nhớ vượt ra khỏi n bit.

Ví dụ `−5` trong **8 bit**:

```text
 +5:                   0000 0101
 Đảo từng bit:         1111 1010
 Cộng 1:             + 0000 0001
                       ---------
 -5:                   1111 1011
```

Mẫu `11111011` là `0xFB` trong hệ 16. Nếu diễn giải **không dấu**, nó bằng `251`; nếu diễn giải **có dấu bù hai**, nó bằng `−5`. Chuyển từ 251 sang −5 ở đây là **đổi cách diễn giải cùng mẫu 8 bit**, không phải thay bit.

Ta cũng có thể thấy `2^8 − 5 = 256 − 5 = 251`. Tổng quát, đối với số âm `−x` trong n bit, mẫu bit không dấu tương ứng là `2^n − x` (với `1 ≤ x ≤ 2^(n−1)`).

Ví dụ `−13` trong 8 bit:

```text
 +13:       0000 1101
 Đảo bit:   1111 0010
 Cộng 1:    1111 0011   = 0xF3 = 243 nếu đọc không dấu
 Đọc có dấu: 243 - 256 = -13
```

**Cẩn thận với độ rộng:** thao tác đảo bit bằng toán tử `~` trong Java trên `int` có hiệu lực 32 bit; muốn minh họa một mẫu 8 bit, lấy 8 bit thấp bằng mask `& 0xFF`. Phương pháp “đảo rồi cộng 1” được trình bày ở đây trên **độ rộng đã chọn**, không phải tự động áp dụng theo số lượng chữ số trong cách in ra màn hình.

## 4. Giải mã một mẫu bit bù hai

Cho mẫu n bit, gọi `U` là giá trị nếu đọc **không dấu** (0 đến `2^n − 1`). Giá trị **có dấu** `S` là:

```text
Nếu bit dấu = 0: S = U
Nếu bit dấu = 1: S = U - 2^n
```

Ví dụ 8 bit `1110 0111`:

- Không dấu: `128 + 64 + 32 + 4 + 2 + 1 = 231`.
- Bit dấu = `1` nên có dấu: `231 − 256 = −25`.
- Kiểm tra ngược: `+25 = 0001 1001`; đảo `1110 0110`; cộng 1 được `1110 0111`.

Một cách tương đương là quy tắc **trọng số của bit cao nhất âm**:

```text
Với 8 bit:
b7 b6 b5 b4 b3 b2 b1 b0
 |
 └── trọng số -128, các bit còn lại có trọng số +64,+32,+16,+8,+4,+2,+1

1110 0111 = -128 + 64 + 32 + 4 + 2 + 1 = -25
```

Hai cách giải mã luôn cho cùng một giá trị. Cách `U − 2^n` đặc biệt tiện khi đọc byte từ tệp hoặc từ mạng dưới dạng số không dấu.

## 5. Vì sao cộng, trừ và đổi dấu có thể dùng cùng biểu diễn?

Các phép cộng, trừ trên nguyên độ rộng cố định giữ **n bit thấp** của kết quả, tương đương cộng/trừ theo **modulo `2^n`**. Ví dụ 8 bit:

```text
    0000 0101  (+5)
  + 1111 1011  (-5)
  -----------
  1 0000 0000  (9 bit)
    0000 0000  (giữ 8 bit thấp) = 0
```

Đó là lý do `x + (−x) = 0` ở tầng mẫu bit, kể cả khi phép tính tạm có bit nhớ ngoài độ rộng. Trong Java, hệ thức `~x + 1` cho cùng mẫu bit với `-x` khi `x` là một `int` (tương tự với `long`). Do đó:

```java
int x = 5;
int negative = ~x + 1; // -5
int bitwiseNot = ~x;   // -6; vì ~x = -x - 1
```

Tuy nhiên, bit nhớ ra ngoài độ rộng **không phải** tiêu chí duy nhất cho **tràn số có dấu**. Ví dụ cộng hai số dương 8 bit `127 + 1` được mẫu `1000 0000`, tức `−128` nếu diễn giải có dấu. Phép toán toán học là 128 nhưng 128 nằm ngoài miền có dấu 8 bit.

### Khi nào tràn số?

Với hai số có dấu cùng độ rộng, cộng bị tràn có dấu nếu **hai toán hạng cùng dấu** nhưng kết quả có **dấu ngược lại**. Trong Java, cộng `int` hoặc `long` thông thường không ném lỗi khi tràn; kết quả giữ bit thấp theo độ rộng của kiểu.

Lưu ý đặc biệt với `byte`/`short`: trong biểu thức như `(byte) (127 + 1)`, phép cộng `127 + 1` diễn ra bằng **`int`** và cho 128, sau đó phép ép hẹp thành `byte` mới lấy 8 bit thấp để ra `−128`. Do đó không nên gọi đây là “phép cộng 8 bit trực tiếp của Java”.

Dùng `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.negateExact` cho `int`/`long` khi muốn **phát hiện tràn** bằng `ArithmeticException`. Dùng `BigInteger` nếu phép toán thực sự cần số nguyên lớn hơn miền `long`.

## 6. Giá trị âm nhỏ nhất và tính bất đối xứng

Với 8 bit:

```text
 0111 1111 = +127   (MAX)
 1000 0000 = -128   (MIN)
```

Không tồn tại `+128` trong `byte`. Nếu đảo bit của `1000 0000` rồi cộng 1 trong đúng 8 bit, ta nhận lại `1000 0000`: `−(−128)` có giá trị toán học +128 nhưng không nằm trong miền biểu diễn, nên mẫu bit quay lại −128.

Tương tự:

```java
int min = Integer.MIN_VALUE;
System.out.println(min);             // -2147483648
System.out.println(-min);            // -2147483648 (tràn)
System.out.println(Math.abs(min));   // -2147483648 (vẫn âm)
```

Đây là **trường hợp biên đặc biệt**, không phải tính chất rằng “phủ định số âm luôn trả lại chính nó”. `Math.negateExact(Integer.MIN_VALUE)` ném `ArithmeticException` để báo không thể biểu diễn giá trị dương tương ứng bằng `int`.

Nếu cần giá trị dương tương ứng của `Integer.MIN_VALUE`, hãy **mở rộng trước**: `long positive = -(long) Integer.MIN_VALUE;` cho `2147483648L`. Với `Long.MIN_VALUE`, `long` không còn kiểu primitive nguyên lớn hơn; có thể dùng `BigInteger.valueOf(Long.MIN_VALUE).negate()`.

## 7. Mở rộng dấu khi đổi kiểu: vì sao `byte -5` thành `int -5`?

Khi đổi một số nguyên có dấu từ loại hẹp sang loại rộng hơn, Java **mở rộng dấu** (*sign extension*): sao chép bit dấu vào các bit cao vừa thêm để giữ nguyên giá trị.

```text
byte -5 (8 bit):   1111 1011

int -5 (32 bit):   1111 1111 1111 1111 1111 1111 1111 1011
                   ^^^^^^^^^^^^^^^^^^^^^^^^
                   các bit mới đều là 1 vì số gốc âm

Hex:
byte pattern:      FB
int -5:            FFFFFFFB
```

Ví dụ:

```java
byte signedByte = (byte) 0xFB; // -5
int signedInt = signedByte;    // -5, do mở rộng dấu
int unsigned = signedByte & 0xFF; // 251, giữ đúng 8 bit thấp
int viaApi = Byte.toUnsignedInt(signedByte); // 251
```

**Mask `0xFF`** có tám bit thấp bằng 1. Sau khi `signedByte` được nâng lên `int`, phép `& 0xFF` xóa 24 bit cao, giữ mẫu byte nguyên vẹn và diễn giải nó như giá trị 0..255. Đây là thao tác nền tảng khi parse giao thức nhị phân có các **octet không dấu**.

Cần phân biệt:

- `byte → int`: **mở rộng dấu**, bảo toàn giá trị có dấu.
- `byte & 0xFF`: **lấy 8 bit thấp**, cho cách diễn giải không dấu.
- `int → byte`: **narrowing cast**, chỉ giữ 8 bit thấp rồi diễn giải chúng theo bù hai; các bit cao bị bỏ đi. Ví dụ `(byte) 255 == -1`.
- `char → int`: chuyển mã `char` **không dấu** sang số nguyên dương, không mở rộng dấu như `short` âm. `char` và `short` cùng 16 bit nhưng khác cách diễn giải.

## 8. Dịch bit trên số âm: `>>` khác `>>>`

Các phép dịch chỉ làm việc với **mẫu bit**, sau đó kiểu Java quyết định cách diễn giải kết quả. Ba toán tử quan trọng:

| Toán tử | Hành vi | Ý nghĩa thường gặp |
| --- | --- | --- |
| `<<` | Dịch trái, các bit thấp mới điền `0`; bit cao bị bỏ | Nhân với `2^k` trong phạm vi có thể biểu diễn; có thể tràn |
| `>>` | Dịch phải **số học**, điền bit dấu từ trái | Giữ dấu; với số âm tương tự làm tròn phép chia cho `2^k` về −∞ |
| `>>>` | Dịch phải **logic**, điền `0` từ trái | Xử lý mẫu bit như số không dấu ở độ rộng `int`/`long` |

Với `int x = -5`:

```text
x (int):  11111111 11111111 11111111 11111011   = -5
x >> 1:  11111111 11111111 11111111 11111101   = -3
x >>> 1: 01111111 11111111 11111111 11111101   = 2147483645
```

Trong Java, phép chia nguyên `-5 / 2` trả **−2** vì phép chia nguyên làm tròn về 0, trong khi `-5 >> 1` trả **−3** (dịch phải số học làm tròn về −∞ với số âm). **Không thay** `x / 2` bằng `x >> 1` một cách máy móc nếu `x` có thể âm.

Cẩn thận với `byte`, `short` và `char`: trước khi thực hiện `<<`, `>>` hoặc `>>>`, toán hạng trái được **promote thành `int`**. Ví dụ:

```java
byte b = -5;
int promotedShift = b >>> 1;        // 2147483645 (dịch 32 bit của -5)
int unsignedByteShift = (b & 0xFF) >>> 1; // 125 (dịch giá trị byte không dấu 251)
```

Một số chi tiết về số lượng dịch: với `int` chỉ 5 bit thấp của số lượng dịch được dùng (thực tế modulo 32); với `long` là 6 bit thấp (modulo 64). Vì vậy `1 << 32` bằng `1`, không phải 0; `1L << 32` có kết quả khác vì toán hạng trái là `long`.

## 9. Toán tử bit và hệ 16 khi đọc bù hai

Các toán tử `&` (AND), `|` (OR), `^` (XOR), `~` (NOT) giúp thao tác bit. Hệ 16 thuận tiện vì **một chữ số hex tương ứng đúng 4 bit**.

```text
8 bit:     1111 1011  = 0xFB
32 bit:    11111111 11111111 11111111 11111011 = 0xFFFFFFFB

Java:
Integer.toHexString(-5)    -> "fffffffb"
Integer.toBinaryString(-5) -> 32 ký tự bit, bắt đầu bằng '1'
```

`Integer.toBinaryString` cho số âm trả đủ 32 bit bù hai; cho số không âm nó không tự thêm `0` dẫn đầu để đủ 32 bit. `Long.toBinaryString` cũng tương tự với 64 bit. Khi muốn in **đúng 8 bit thấp**, dùng mask và tự thêm `0` đầu chuỗi.

**Chú ý về literal hex:** `int raw = 0xFFFFFFFF;` mang mẫu 32 bit toàn `1`, được đọc có dấu là `-1`. Nếu cùng mẫu 32 bit được diễn giải theo **không dấu**, giá trị toán học là `4_294_967_295`; biến `int` vẫn lưu đúng bit đó.

Các API `Integer.toUnsignedString(int)`, `Integer.toUnsignedLong(int)`, `Integer.parseUnsignedInt(String)` và `Integer.compareUnsigned` xử lý **cách diễn giải không dấu** của 32 bit. Java không có primitive `unsigned int` riêng; các API này không đổi kiểu `int` thành một kiểu số mới.

## 10. Chương trình Java 17+ chạy độc lập

Tạo tệp **`TwosComplementDemo.java`** với nội dung đầy đủ sau:

```java
public class TwosComplementDemo {
    // Lấy 8 bit thấp rồi thêm số 0 vào đầu để hiển thị đủ 8 bit.
    private static String bits8(int value) {
        String binary = Integer.toBinaryString(value & 0xFF);
        return String.format("%8s", binary).replace(' ', '0');
    }

    public static void main(String[] args) {
        byte minusFive = -5;

        System.out.println("+5   : " + bits8(5));
        System.out.println("~5+1 : " + bits8(~5 + 1));
        System.out.println("-5   : " + bits8(minusFive));

        System.out.println("signed byte: " + minusFive);
        System.out.println("unsigned byte: " + Byte.toUnsignedInt(minusFive));
        System.out.println("sign-extended int hex: "
                + Integer.toHexString(minusFive));

        System.out.println("-5 >> 1 = " + (-5 >> 1));
        System.out.println("-5 >>> 1 = " + (-5 >>> 1));
        System.out.println("8-bit unsigned >>> 1 = "
                + ((minusFive & 0xFF) >>> 1));

        System.out.println("(byte) 128 = " + (byte) 128);
        System.out.println("int MAX + 1 = " + (Integer.MAX_VALUE + 1));
        System.out.println("-int MIN = " + (-Integer.MIN_VALUE));
        System.out.println("unsigned int(-1) = "
                + Integer.toUnsignedString(-1));

        try {
            Math.negateExact(Integer.MIN_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("negateExact(MIN): overflow detected");
        }
    }
}
```

Chạy ở thư mục chứa tệp:

```bash
javac TwosComplementDemo.java
java TwosComplementDemo
```

**Kết quả chuẩn:**

```text
+5   : 00000101
~5+1 : 11111011
-5   : 11111011
signed byte: -5
unsigned byte: 251
sign-extended int hex: fffffffb
-5 >> 1 = -3
-5 >>> 1 = 2147483645
8-bit unsigned >>> 1 = 125
(byte) 128 = -128
int MAX + 1 = -2147483648
-int MIN = -2147483648
unsigned int(-1) = 4294967295
negateExact(MIN): overflow detected
```

**Đọc kết quả theo từng cơ chế:**

1. `bits8(~5 + 1)` dùng kết quả `int` rồi mask 8 bit; mẫu cuối `11111011` khớp `byte -5`.
2. Cùng mẫu `11111011` đọc theo signed byte thành `−5`, theo unsigned byte thành `251`.
3. Khi ép từ `byte` âm sang `int`, các bit cao thêm `1`; vì thế hiển thị hex là `fffffffb`.
4. `>>` giữ bit dấu, `>>>` điền `0` ở 32 bit; mask trước khi dịch tạo cách dịch logic của 8 bit.
5. Ép `(byte) 128` trả `−128` vì `128` có bit thấp `10000000`.
6. `int MAX + 1` và `-int MIN` đều minh họa miền 32 bit có dấu; `negateExact` giúp phát hiện trường hợp thứ hai.

## 11. Áp dụng khi đọc dữ liệu nhị phân

Giả sử giao thức quy định **một octet không dấu** chứa độ dài 0..255. Một byte có bit `1000 0001` được lưu vào Java `byte` sẽ có giá trị `−127`, nhưng độ dài theo giao thức là **129**.

```java
byte lengthOctet = (byte) 0x81;
int length = Byte.toUnsignedInt(lengthOctet); // 129
```

Ngược lại, nếu giao thức quy định số nguyên **có dấu 8 bit theo bù hai**, giá trị `−127` mới chính xác. Không có “đổi sang không dấu” nào là đúng cho mọi dữ liệu; phải đọc **đặc tả giao thức**, xác định bit-width và signedness, rồi mới diễn giải.

Khi ghép hai octet thành số 16 bit không dấu ở thứ tự *big-endian*:

```java
byte high = (byte) 0xAB;
byte low = (byte) 0xCD;
int unsigned16 = ((high & 0xFF) << 8) | (low & 0xFF);
// unsigned16 = 43981 (0xABCD)
```

Mask từng `byte` **trước** khi ghép tránh dấu âm lan lên các bit cao. Nếu thiếu mask của `low`, phép OR với `int` đã mở rộng dấu có thể làm sai nhiều bit của kết quả. Nếu muốn diễn giải `0xABCD` như số nguyên **có dấu 16 bit**, giá trị sẽ là `43981 − 65536 = −21555`; có thể dùng `(short) unsigned16`.

## 12. Sai lầm phổ biến và cách tự kiểm tra

| Hiểu nhầm | Điều đúng cần nhớ |
| --- | --- |
| Bit đầu là dấu, phần còn lại là độ lớn | Đó là sign–magnitude; bù hai giải mã theo trọng số bit cao âm hoặc `U−2^n` |
| `11111111` luôn bằng −1 | Chỉ khi được diễn giải **có dấu 8 bit**; dạng không dấu là 255 |
| `~5` bằng `−5` | `~5` là −6; `~5 + 1` mới là −5 |
| `int result = 127 + 1` tạo ra `byte -128` | Biểu thức `int` là 128; chỉ khi ép hẹp xuống `byte` mới thành −128 |
| `-Integer.MIN_VALUE` ra số dương | Nó tràn và vẫn bằng `Integer.MIN_VALUE` |
| `-5 >> 1` và `-5 / 2` giống nhau | Dịch phải số học ra −3; chia nguyên ra −2 |
| `byteValue >>> 1` dịch 8 bit | `byte` được promote thành `int` rồi dịch **32 bit** |
| `Integer.toBinaryString(x)` luôn trả đúng 32 ký tự | Số không âm có thể được bỏ `0` dẫn đầu |
| Java có primitive `unsigned int` | Không; dùng `int` và API unsigned để diễn giải mẫu 32 bit |
| `double` cũng lưu số âm theo bù hai | `double` dùng IEEE 754, bài này chỉ mô tả số nguyên có dấu |

Để xử lý bit đúng, luôn xác định **ba thông tin** trước: (1) độ rộng 8/16/32/64 bit, (2) signed hay unsigned, (3) thao tác đang thực hiện **trước hay sau** promotion/cast. Với thao tác nhị phân, hãy viết ví dụ ở hệ 2 hoặc hex và kiểm tra kết quả với mask đúng độ rộng.

## 13. Bài tập tự kiểm tra

**Bài 1.** Biểu diễn `−18` bằng 8 bit bù hai.  
**Bài 2.** Diễn giải `1101 0000` như unsigned và signed 8 bit.  
**Bài 3.** Dự đoán kết quả của `(byte) 255` và `((byte) 255) & 0xFF`.  
**Bài 4.** Vì sao `Integer.MIN_VALUE` là một số âm không có trị dương tương ứng trong `int`?  
**Bài 5.** Giải thích vì sao `byte b = -2; int x = b >>> 1;` không tương đương dịch phải logic 8 bit của `11111110`.

**Đáp án và lời giải:**

1. `+18 = 0001 0010` → đảo `1110 1101` → cộng 1 `1110 1110`, tức `0xEE`.
2. Unsigned: `0xD0 = 208`. Signed: `208 − 256 = −48`.
3. `(byte)255` giữ tám bit thấp `1111 1111` nên là `−1`; sau mask `& 0xFF` kết quả `int 255`.
4. Miền `int` là `−2^31 .. 2^31−1`, thiếu giá trị `+2^31`. Khi phủ định trong 32 bit, bit pattern `1000...0000` quay về chính nó; `Math.negateExact` phát hiện tràn.
5. `b` được nâng lên `int -2` (32 bit có 31 bit `1` và bit cuối `0`); `>>> 1` cho `2147483647`. Muốn dịch mẫu **8 bit** như unsigned `254`, làm `(b & 0xFF) >>> 1` để được `127`.

**Điểm cốt lõi:** Bù hai là cách **diễn giải và tính toán các mẫu bit cố định**. Nắm được quy tắc `U−2^n`, phép `đảo bit + 1`, mở rộng dấu và giữ bit thấp sẽ giúp bạn giải thích phần lớn các kết quả số nguyên âm, cast và dịch bit trong Java.

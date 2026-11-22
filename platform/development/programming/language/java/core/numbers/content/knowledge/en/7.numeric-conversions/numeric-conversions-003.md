# Thu hẹp số nguyên và các bit bị loại bỏ trong Java

> **Java core – numbers · Chuyển kiểu**  
> Mục tiêu: xác định chính xác bit nào còn lại sau narrowing integer conversion, cách Java diễn giải lại bit có dấu và không dấu, và cách tránh mất dữ liệu trong chuyển kiểu, phép gán và xử lý nhị phân.

## 1. Bài toán: một giá trị lớn đi vào kiểu nhỏ

Trong Java, các kiểu nguyên có độ rộng và miền giá trị cố định:

| Kiểu | Độ rộng | Miền | Có dấu? |
| --- | ---: | --- | --- |
| `byte` | 8 bit | −128 đến 127 | Có |
| `short` | 16 bit | −32.768 đến 32.767 | Có |
| `char` | 16 bit | 0 đến 65.535 | Không |
| `int` | 32 bit | −2³¹ đến 2³¹−1 | Có |
| `long` | 64 bit | −2⁶³ đến 2⁶³−1 | Có |

*Thu hẹp số nguyên* (*narrowing primitive conversion*) là chuyển một giá trị nguyên sang kiểu đích không bảo đảm chứa được mọi giá trị của kiểu nguồn. Ví dụ:

```java
int source = 130;
byte result = (byte) source;
System.out.println(result); // -126
```

**Java không chọn giá trị gần nhất trong miền `byte`.** Khi cast từ nguyên rộng sang nguyên hẹp, nó loại bỏ bit cao và chỉ giữ **n bit thấp**, trong đó n là độ rộng của kiểu đích; sau đó đọc mẫu bit này theo quy tắc kiểu đích. Vì `130` có 8 bit thấp là `1000_0010`, mẫu ấy là `−126` khi diễn giải signed byte theo bù hai.

Narrowing integer conversion cũng không tự ném ngoại lệ khi không giữ được giá trị gốc. Cast là một lời yêu cầu chuyển kiểu theo quy tắc ngôn ngữ, **không phải lời hứa rằng giá trị còn nguyên**.

## 2. Cơ chế bit: cắt bên trái, giữ bên phải

Xét `int 130` (32 bit) sang `byte` (8 bit):

```text
int (32 bit): 00000000 00000000 00000000 10000010
             \________ 24 bit cao bị loại ______/ \__ 8 bit __/
                                                    10000010

Nếu đọc 8 bit KHÔNG dấu: 128 + 2 = 130
Nếu đọc dưới kiểu byte có dấu: 130 - 256 = -126
```

Với `int 255`:

```text
int:    00000000 00000000 00000000 11111111
byte:                              11111111
                                              -> -1 (signed byte)
```

Với `int 256`:

```text
int:    00000000 00000000 00000001 00000000
byte:                              00000000
                                              -> 0 (bit ở vị trí 8 đã bị loại)
```

Để dự đoán kết quả, có thể sử dụng phép toán học hai bước:

1. Tìm `U` là **phần dư không âm** của số nguồn khi chia cho `2^n`. Khi đó `U` nằm trong `0..2^n−1` và mô tả n bit thấp.
2. Nếu kiểu đích là `char`, kết quả bằng `U`. Nếu kiểu đích có dấu n bit, kết quả bằng `U` khi `U < 2^(n−1)`, hoặc bằng `U−2^n` khi `U ≥ 2^(n−1)`.

Với `(byte) 300`: `300 mod 256 = 44` nên kết quả là `44`. Với `(byte) -130`: phần dư **không âm** của −130 khi chia 256 là 126, nên kết quả `126`.

**Chú ý:** ký hiệu `mod` ở trên là phần dư toán học không âm. Toán tử `%` trong Java có thể trả phần dư âm nếu số bị chia âm; ví dụ `-130 % 256 == -130`. Muốn phần dư không âm với môđun dương có thể dùng `Math.floorMod(-130, 256)`.

## 3. Bảng mẫu: cast int sang byte

| Nguồn `int` | 8 bit thấp | `(byte)` | Diễn giải |
| ---: | --- | ---: | --- |
| 100 | `0110_0100` | 100 | Vẫn vừa byte |
| 127 | `0111_1111` | 127 | Biên dương |
| 128 | `1000_0000` | −128 | Bit dấu của byte bật |
| 129 | `1000_0001` | −127 | Giá trị bù hai |
| 130 | `1000_0010` | −126 | Giá trị bù hai |
| 255 | `1111_1111` | −1 | Tám bit đều là 1 |
| 256 | `0000_0000` | 0 | Bit thứ 8 đã mất |
| 257 | `0000_0001` | 1 | Chỉ còn bit 0 |
| −1 | `1111_1111` | −1 | Vẫn giữ giá trị |
| −128 | `1000_0000` | −128 | Biên âm |
| −129 | `0111_1111` | 127 | Quay vòng qua miền byte |

Ví dụ `(byte) 128` cho `−128`, còn `(byte) 255` cho `−1`. Không có logic **clamp** về −128/127. Những giá trị nguồn khác nhau cách nhau bội số 256 có cùng mẫu 8 bit thấp và sẽ cho cùng giá trị `byte`.

## 4. Thu hẹp long thành int

`long` có 64 bit, `int` có 32 bit. Khi cast `long → int`, Java loại 32 bit cao:

```java
long large = 0x1_0000_0001L; // 4294967297
int shortened = (int) large; // 1
```

```text
long: 00000001 00000001  (mỗi nhóm ở đây là 32 bit hex: 0x00000001_00000001)
                   ^^^^^^^^
                   32 bit thấp = 0x00000001 -> int 1
```

Để thấy trường hợp đổi dấu:

```java
long source = 0x00000001_FFFFFFFFL;
int shortened = (int) source;
System.out.println(shortened); // -1
```

Phần thấp `0xFFFFFFFF` của `long` được giữ nguyên, nhưng trong `int` có dấu đó là −1.

Khi rút gọn ID hoặc giá trị số lượng từ `long` sang `int`, việc mất 32 bit cao có thể làm nhiều giá trị khác nhau trở thành cùng một giá trị. Ví dụ `1L` và `0x1_0000_0001L` đều cast thành `int 1`. Chỉ dùng cách thu hẹp để trích bit nếu **đặc tả thực sự cần trích**; nếu phải bảo toàn giá trị, kiểm tra miền trước cast.

## 5. int sang short: giữ 16 bit, diễn giải có dấu

```java
System.out.println((short) 32767); // 32767
System.out.println((short) 32768); // -32768
System.out.println((short) 65535); // -1
System.out.println((short) 65536); // 0
```

```text
 32768 (0x00008000) -> giữ 0x8000 -> short -32768
 65535 (0x0000FFFF) -> giữ 0xFFFF -> short -1
 65536 (0x00010000) -> giữ 0x0000 -> short 0
```

Cách thu hẹp `long → short` có cùng đích là 16 bit thấp. Việc đi qua `int` trước rồi chuyển tiếp sang `short` (không xen phép toán làm đổi giá trị) cũng giữ cùng 16 bit thấp.

## 6. char: cùng 16 bit với short, nhưng không dấu

`char` là đơn vị mã UTF-16 không dấu, có giá trị số từ 0 đến 65.535. Narrowing thành `char` vẫn giữ 16 bit thấp, nhưng **không dùng bit cao nhất làm bit dấu**:

```java
char a = (char) 65;       // 'A'
char b = (char) 65535;    // giá trị số 65535
char c = (char) 65536;    // giá trị số 0
char d = (char) -1;       // giá trị số 65535
System.out.println((int) d); // 65535
```

Khi in một biến `char` trực tiếp, Java có thể in ra **ký tự**, không phải mã số. Muốn quan sát mã số, ép `char` lên `int` như trên.

So sánh hai kiểu 16 bit:

```java
char unit = '\uFFFF';
short signed = (short) unit;   // -1
char restored = (char) signed; // 65535
```

Bản thân 16 bit `1111_1111_1111_1111` không đổi. Nhưng `short` đọc là −1 còn `char` đọc là 65.535. Vì khác miền, chuyển giữa hai kiểu này yêu cầu cast dù số bit bằng nhau. Không nên coi `char` là kiểu số không dấu thay thế tùy tiện cho dữ liệu: một đơn vị UTF-16 không nhất thiết là một ký tự Unicode độc lập hoặc ký tự hiển thị được.

## 7. Chuyển theo chuỗi cast: vẫn giữ bit thấp khi không có phép toán xen giữa

```java
long number = 0x1234_5678_9ABC_DEF0L;

int low32 = (int) number;       // 0x9ABCDEF0
short low16 = (short) number;   // 0xDEF0
byte low8 = (byte) number;      // 0xF0
```

```text
long:   1234 5678 9ABC DEF0
int:              9ABC DEF0
short:                 DEF0
byte:                    F0
```

Có thể xác nhận `(byte) number`, `(byte)(int) number` và `(byte)(short) number` đều thành `−16`, vì 8 bit thấp luôn là `0xF0`. Đây chỉ là tương đương trong trường hợp các bước trung gian thuần túy là chuyển kiểu nguyên. Xen các phép số học, cast qua `float`/`double` hoặc dịch bit có thể tạo mẫu khác.

## 8. Tại sao một số phép gán không cần cast: constant expression

Narrowing từ biến `int` sang `byte` thường đòi cast:

```java
int value = 100;
// byte invalid = value; // lỗi: biến int không được thu hẹp ngầm
byte explicit = (byte) value;
```

Nhưng Java có ngoại lệ **chuyển đổi gán cho biểu thức hằng** (constant expression) kiểu `byte`, `short`, `char` hoặc `int` nếu giá trị nằm trong miền của kiểu đích thích hợp:

```java
byte a = 100;          // được: literal int 100 vừa byte
short b = 30000;       // được: hằng int vừa short
char c = 65;           // được: hằng int nằm trong miền char
byte total = 40 + 2;   // được: biểu thức hằng int bằng 42

final int FIXED = 120;
byte fromFixed = FIXED; // được: biến hằng final int

int ordinary = 120;
// byte wrong = ordinary; // không được

// byte tooLarge = 128;  // không được: ngoài miền
byte wrapped = (byte) 128; // được: -128
```

Nên phân biệt rõ **ngoại lệ khi gán hằng trong miền** với cast tường minh: compiler biết được giá trị hằng và cho phép gán nếu an toàn; cast tường minh ngoài miền vẫn giữ bit thấp và có thể mất giá trị. Quy tắc gán hằng này cũng **không đồng nghĩa** mọi lời gọi phương thức nhận `byte` đều có thể nhận literal `int` mà không cast.

## 9. Numeric promotion: toán học được thực hiện trước narrowing

Trong phép cộng, trừ, nhân, chia giữa các primitive nguyên, các toán hạng `byte`, `short` và `char` thường được nâng lên `int` trước (*binary numeric promotion*).

```java
byte x = 100;
byte y = 30;
int sum = x + y;           // 130, kiểu int
byte result = (byte) (x + y); // -126
// byte invalid = x + y;  // lỗi: tổng có kiểu int
```

Nếu phép tính chạy bằng `int` và **tràn trước khi cast**, cast sau đó không thể khôi phục thông tin đã mất:

```java
int a = 1_500_000_000;
long bad = a * 2;           // -1294967296L, int tràn trước
long good = (long) a * 2;  // 3000000000L, long trước phép nhân
```

Khi cần kiểm tra tràn trong `int`/`long`, dùng `Math.addExact`, `Math.multiplyExact` và các hàm exact liên quan; khi cần miền số nguyên lớn hơn `long`, chuyển toán hạng sang `BigInteger` **trước phép tính**.

Không lẫn quy tắc trên với cast từ số thực sang số nguyên. `(int) 3.9` có quy tắc bỏ phần lẻ, còn `(byte) 130` có quy tắc giữ bit thấp. Với số thực `NaN`, vô cực và ngoài miền còn có quy tắc riêng, nằm ngoài trọng tâm của bài này.

## 10. Compound assignment và ++/--: có narrowing ngầm

Phép gán kết hợp (*compound assignment*) như `+=` chứa chuyển đổi ngầm về kiểu vế trái:

```java
byte b = 127;
b += 1;
System.out.println(b); // -128
```

Nhưng phép gán thường lại khác:

```java
byte b = 127;
// b = b + 1; // lỗi: b + 1 là int
b = (byte) (b + 1); // -128
```

Về mặt khái niệm, `E1 op= E2` gần với `E1 = (T)(E1 op E2)`, nhưng có điểm thiết yếu: **E1 chỉ được đánh giá một lần**. Vì vậy không thay thế tùy tiện nếu vế trái có truy cập mảng, tăng chỉ số hoặc lời gọi phương thức.

Toán tử `++`/`--` trên `byte`, `short`, `char` cũng có thể quay vòng:

```java
byte b = 127;
b++;
System.out.println(b); // -128

char unit = '\uFFFF';
unit++;
System.out.println((int) unit); // 0
```

Nếu nghiệp vụ không chấp nhận quay vòng, hãy dùng kiểu đủ rộng và kiểm tra miền trước phép gán.

## 11. Mask và diễn giải byte không dấu

Trong Java, `byte` có dấu. Nhưng định dạng nhị phân/giao thức thường dùng một octet **không dấu** từ 0..255:

```java
byte raw = (byte) 0xFF;  // signed byte -1
int signed = raw;        // -1: sign extension khi nâng lên int
int unsigned = raw & 0xFF; // 255: giữ 8 bit thấp
int api = Byte.toUnsignedInt(raw); // 255
```

Điểm khác nhau:

- `byte → int` là **widening** giữ giá trị có dấu: bit dấu `1` được mở rộng vào 24 bit cao.
- `raw & 0xFF` là phép mask sau khi operand đã được nâng lên `int`: xóa các bit cao để giữ giá trị 0..255.

Khi ghép hai octet big-endian:

```java
byte high = (byte) 0xAB;
byte low = (byte) 0xCD;
int unsigned16 = ((high & 0xFF) << 8) | (low & 0xFF);
System.out.println(unsigned16); // 43981 (0xABCD)
```

Mask từng byte trước khi dịch/OR tránh sign extension làm sai các bit. Quy tắc thực tế: xác định **độ rộng trường, signedness và thứ tự byte** từ đặc tả giao thức; chỉ dùng cast xuống byte khi thật sự muốn lấy bit thấp, còn dùng kiểm tra miền khi cần giữ nguyên **giá trị số học**.

## 12. Phát hiện mất dữ liệu trước khi cast

### 12.1. Kiểm tra miền trước khi thu hẹp

```java
public static byte checkedByte(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new ArithmeticException("Outside byte range");
    }
    return (byte) value;
}
```

Đây là một **phương thức minh họa**, đặt trong một lớp trước khi sử dụng. Với `short` dùng `Short.MIN_VALUE`/`Short.MAX_VALUE`. Với `char` dùng điều kiện `value >= Character.MIN_VALUE && value <= Character.MAX_VALUE`.

### 12.2. Math.toIntExact và BigInteger exact

```java
long large = 0x1_0000_0001L;
int truncated = (int) large; // 1
// Math.toIntExact(large) sẽ ném ArithmeticException
```

`Math.toIntExact(long)` là API có sẵn để yêu cầu chuyển sang `int` mà **không làm mất giá trị**. Với `BigInteger` có `byteValueExact()`, `shortValueExact()`, `intValueExact()`, `longValueExact()`. Ngược lại, `BigInteger.intValue()` và `longValue()` có thể bỏ bit cao mà không báo lỗi.

### 12.3. Kiểm tra cast bằng vòng ngược

```java
int original = 130;
byte narrowed = (byte) original;
boolean preserved = ((int) narrowed == original); // false
```

Đây là cách tự kiểm chứng sự mất mát, nhưng khi validate đầu vào thực tế, **kiểm tra miền trước cast** dễ đọc hơn và tránh nhầm lẫn khi chuyển qua `char` không dấu.

## 13. Chương trình Java 17+ chạy độc lập

Tạo tệp **`IntegerNarrowingDemo.java`**:

```java
public class IntegerNarrowingDemo {
    private static byte checkedByte(int value) {
        if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
            throw new ArithmeticException("byte range exceeded");
        }
        return (byte) value;
    }

    private static String bits8(int value) {
        String binary = Integer.toBinaryString(value & 0xFF);
        return String.format("%8s", binary).replace(' ', '0');
    }

    public static void main(String[] args) {
        int source = 130;
        byte narrowed = (byte) source;

        System.out.println("130 -> byte = " + narrowed);
        System.out.println("low 8 bits = " + bits8(source));
        System.out.println("255 -> byte = " + (byte) 255);
        System.out.println("256 -> byte = " + (byte) 256);
        System.out.println("-129 -> byte = " + (byte) -129);

        long wide = 0x1_0000_0001L;
        System.out.println("long -> int = " + (int) wide);
        System.out.println("32768 -> short = " + (short) 32768);
        System.out.println("-1 -> char code = " + (int) (char) -1);

        byte octet = (byte) 0xFF;
        System.out.println("signed byte = " + octet);
        System.out.println("unsigned octet = " + Byte.toUnsignedInt(octet));

        byte counter = 127;
        counter += 1;
        System.out.println("byte += 1 = " + counter);

        try {
            checkedByte(130);
        } catch (ArithmeticException e) {
            System.out.println("checked byte: rejected");
        }
        try {
            Math.toIntExact(wide);
        } catch (ArithmeticException e) {
            System.out.println("toIntExact: rejected");
        }
    }
}
```

Chạy trong thư mục chứa tệp:

```bash
javac IntegerNarrowingDemo.java
java IntegerNarrowingDemo
```

**Stdout chính xác:**

```text
130 -> byte = -126
low 8 bits = 10000010
255 -> byte = -1
256 -> byte = 0
-129 -> byte = 127
long -> int = 1
32768 -> short = -32768
-1 -> char code = 65535
signed byte = -1
unsigned octet = 255
byte += 1 = -128
checked byte: rejected
toIntExact: rejected
```

Đọc kết quả:

1. `130` thành `-126` vì `10000010` là signed byte −126.
2. `255` thành `−1`, `256` thành `0`, `−129` thành `127` vì cùng quy tắc modulo 256 ở mức bit.
3. `long 0x1_0000_0001L` mất 32 bit cao và trở thành `int 1`; cast sang `short`/`char` cũng giữ số bit thấp của kiểu đích.
4. Cùng octet `0xFF` được đọc signed byte −1 hoặc unsigned 255.
5. `+=` thu hẹp ngầm và quay vòng; các helper checked từ chối chuyển không bảo toàn giá trị.

## 14. Lỗi phổ biến

| Nhầm lẫn | Quy tắc đúng |
| --- | --- |
| `(byte) 130` sẽ chặn ở 127 | Giữ 8 bit thấp, trả −126 |
| Narrowing integer cast tự báo overflow | Cast không tự báo; phải kiểm tra biên |
| Thu hẹp nguyên là làm tròn số học | Nó loại bit cao và diễn giải bit đích |
| `short` và `char` đều 16 bit nên cùng giá trị | `short` có dấu, `char` không dấu |
| `(char) -1` vẫn bằng −1 | Giá trị là 65535 |
| `byte` âm nâng lên `int` sẽ thành 0..255 | Nâng kiểu giữ dấu; mask nếu cần unsigned |
| `byte + byte` vẫn là `byte` | Toán tử số học nhị phân promote thành `int` |
| `byte b = 100;` chứng minh mọi gán int→byte được | Đó là ngoại lệ cho hằng vừa miền |
| `byte += 1` kiểm tra tràn | Compound assignment thu hẹp ngầm |
| Cast sau phép nhân khôi phục tràn trước đó | Thông tin đã mất không tự quay lại |
| Mask và cast luôn bằng nhau về giá trị | Mask phục vụ bit không dấu; cast giữ kiểu đích có dấu |
| Cast sang `char` tạo Unicode scalar value hợp lệ | `char` chỉ là một đơn vị UTF-16 |

## 15. Bài tập có lời giải

**Bài 1.** `(byte) 300` bằng bao nhiêu?  
**Lời giải:** `300 mod 256 = 44`, mẫu `00101100`, kết quả **44**.

**Bài 2.** `(short) 65535` và `(char) 65535` cho các giá trị số nào?  
**Lời giải:** cùng mẫu `FFFF` nhưng lần lượt là **−1** và **65535**. In bằng `(int)(short)65535` và `(int)(char)65535`.

**Bài 3.** `(int) 0x0000_0002_0000_0005L` bằng bao nhiêu?  
**Lời giải:** **5**; chỉ 32 bit thấp `00000005` còn lại.

**Bài 4.** Những câu nào biên dịch: `byte a = 127;`, `byte b = 128;`, `byte c = (byte)128;`?  
**Lời giải:** a được (=127), b lỗi compile do hằng ngoài miền, c được (=−128).

**Bài 5.** Với `byte b = (byte)0xFE;`, `b`, `(int)b` và `b & 0xFF` là gì?  
**Lời giải:** **−2**, **−2**, **254**. Nâng lên `int` giữ dấu; mask đọc 8 bit không dấu.

**Bài 6.** Làm sao từ chối một `int` ngoài miền `short`?  
**Lời giải:** kiểm tra `x >= Short.MIN_VALUE && x <= Short.MAX_VALUE` trước `(short)x`; nếu sai, trả lỗi thích hợp.

**Bài 7.** Vì sao `b += 1` được nhưng `b = b + 1` với `byte b` không được?  
**Lời giải:** `+=` có narrowing ngầm về kiểu vế trái; `b + 1` là `int` và gán thường không tự thu hẹp biến `int`.

## 16. Checklist trước khi thu hẹp

1. Xác định **độ rộng bit đích** và bit nào sẽ bị loại bỏ.
2. Phân biệt **kiểu có dấu** với `char` không dấu; cùng bit có thể mang giá trị khác.
3. Hỏi rõ cần **bảo toàn giá trị số** hay chỉ lấy **bit thấp** cho giao thức.
4. Kiểm tra **phép tính nào diễn ra trước cast**, có promotion hoặc overflow không.
5. Nếu không được mất thông tin, dùng **kiểm tra miền**, `Math.toIntExact` hoặc các hàm `BigInteger.*ValueExact` phù hợp.
6. Kiểm tra `+=`/`++` có narrowing ngầm; chú ý các biên ±128, ±32.768, ±2³¹.
7. Với byte nhị phân, xác định giao thức là **signed/unsigned** và mask chính xác trước shift/OR.
8. Tự kiểm tra cả hai phía của biên: giá trị trong miền, đúng biên, ngay ngoài biên.

**Điểm cần nhớ:** Narrowing giữa các kiểu nguyên trong Java **giữ n bit thấp của kiểu đích và bỏ bit cao**. Kết quả cuối phụ thuộc cách kiểu đích đọc n bit ấy, có dấu hay không dấu. Cast tường minh không đảm bảo không mất dữ liệu; kiểm tra biên mới đảm bảo giữ nguyên giá trị số học.

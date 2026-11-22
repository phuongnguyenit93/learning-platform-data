# Thập phân, nhị phân, bát phân và thập lục phân trong Java

## 1. Một giá trị, bốn cách biểu diễn

Một số nguyên là **giá trị**, còn hệ cơ số (*numeral system*) là **cách viết giá trị** đó. Ví dụ, số nguyên bốn mươi hai có thể viết:

| Hệ cơ số | Cơ số | Chữ số được phép | Cách viết số 42 trong toán học | Literal nguyên trong Java |
|---|---:|---|---|---|
| Thập phân (*decimal*) | 10 | 0–9 | \(42_{10}\) | `42` |
| Nhị phân (*binary*) | 2 | 0, 1 | \(101010_2\) | `0b101010` |
| Bát phân (*octal*) | 8 | 0–7 | \(52_8\) | `052` |
| Thập lục phân (*hexadecimal*) | 16 | 0–9, A–F | \(2A_{16}\) | `0x2A` |

Các literal `42`, `0b101010`, `052` và `0x2A` đều có cùng **giá trị nguyên 42**. Chọn cơ số khác không làm biến `int` to hơn, nhanh hơn hoặc chính xác hơn: nó chỉ thay đổi cách mã nguồn biểu diễn một số.

Khi đọc một literal, phân biệt **tiền tố** (cho biết hệ cơ số), **phần chữ số**, **dấu gạch dưới** (cho dễ đọc) và **hậu tố `L`** (cho biết kiểu `long`). Những thành phần này không có cùng vai trò.

## 2. Nguyên lý của hệ giá trị theo vị trí

Với cơ số \(b\), mỗi vị trí từ phải sang trái mang trọng số \(b^0, b^1, b^2,\ldots\). Một chuỗi chữ số \(d_nd_{n-1}\dots d_0\) biểu thị:

\[
d_n b^n + d_{n-1}b^{n-1}+\cdots+d_1 b+d_0.
\]

Mọi chữ số \(d_i\) phải thỏa \(0 \le d_i < b\). Riêng hệ 16 dùng thêm A = 10, B = 11, C = 12, D = 13, E = 14, F = 15; chữ hoa và chữ thường đều được chấp nhận.

Áp dụng với số 42:

- Thập phân `42` = \(4\times10+2=42\).
- Nhị phân `101010` = \(1\times32+0\times16+1\times8+0\times4+1\times2+0=42\).
- Bát phân `52` = \(5\times8+2=42\).
- Hex `2A` = \(2\times16+10=42\).

Từ đó thấy rõ: không thể suy ra giá trị chỉ bằng nhìn chuỗi `10` mà bỏ qua cơ số. `10` trong hệ 2 bằng 2; trong hệ 8 bằng 8; trong hệ 10 bằng 10; trong hệ 16 bằng 16.

## 3. Cú pháp literal nguyên của Java

### 3.1. Thập phân — mặc định

Literal không có tiền tố đặc biệt và bắt đầu bằng chữ số 1–9 được hiểu là thập phân; chữ số `0` đứng một mình cũng hợp lệ:

```java
int ten = 10;
int thousand = 1_000;
long large = 3_000_000_000L;
int zero = 0;
```

Thêm hậu tố `L` hoặc `l` để chỉ literal kiểu `long`; nên ưu tiên **`L` viết hoa**, dễ phân biệt với chữ số 1.

### 3.2. Nhị phân — tiền tố `0b` hoặc `0B`

Hỗ trợ từ Java 7, chỉ dùng 0 và 1:

```java
int flags = 0b1010;       // 10 thập phân
int eight = 0B1000;       // 8 thập phân
long wide = 0b1_0000L;   // 16 thập phân
```

`0b102` **không hợp lệ** vì chữ số 2 không có trong cơ số 2. Không có tiền tố nhị phân nào ngầm nói rằng literal là `byte`: `0b1111_1111` là literal `int` mang giá trị 255; `(byte) 0b1111_1111` mới tạo giá trị `byte` -1.

### 3.3. Bát phân — tiền tố **chữ số 0**

Java viết bát phân bằng **chữ số 0 đặt đầu literal**, theo cú pháp lịch sử:

```java
int tenInOctal = 012;  // 1*8 + 2 = 10 thập phân
int permission = 0755; // 7*64 + 5*8 + 5 = 493 thập phân
int eight = 010;       // 8 thập phân, KHÔNG phải 10
```

Đây là bẫy hay gặp: `010` **không bằng** `10`. Viết `08` hoặc `09` sẽ **lỗi biên dịch**, vì 8 và 9 không phải chữ số bát phân.

Java **không** dùng tiền tố `0o` kiểu Python để biểu diễn bát phân. Nếu muốn số 10 thập phân, viết `10`; nếu cần diễn đạt bát phân rõ ràng trong văn bản, ghi \(12_8\), còn trong Java dùng `012`.

### 3.4. Thập lục phân — tiền tố `0x` hoặc `0X`

Hex dùng chữ số 0–9 và A–F (không phân biệt hoa thường):

```java
int answer = 0x2A;          // 42 thập phân
int byteMask = 0xFF;        // 255 thập phân
int color = 0x12_AB_34;     // 1_223_476 thập phân
long wide = 0X1_0000_0000L; // 4_294_967_296 thập phân
```

Hex thuận tiện khi thao tác byte hoặc bit: 1 chữ số hex tương ứng **4 bit**, 2 chữ số hex tương ứng **8 bit**. Ví dụ `0xFF` = `0b1111_1111` = 255.

`0xG1` không hợp lệ vì G không phải chữ số hex. Khi viết literal hex nguyên, có thể dùng các chữ cái A–F ở cả hai dạng; Java nhận `0x2a` và `0X2A` như nhau.

## 4. Dấu gạch dưới, hậu tố và kiểu của literal

Java cho phép dấu gạch dưới **giữa các chữ số** nhằm tăng khả năng đọc:

```java
int population = 2_147_483_647;
int bits = 0b1010_0101;
int code = 0xCAFE_BABE;
long id = 0xFFFF_FFFF_FFFF_FFFFL;
```

Dấu gạch dưới không thay đổi giá trị. Các dạng sau **không hợp lệ**:

```java
// int bad1 = _123;      // '_' không được đứng đầu literal
// int bad2 = 123_;      // '_' không được đứng cuối literal
// int bad3 = 0x_FF;     // '_' không được đứng ngay sau tiền tố
// int bad4 = 0b_1010;   // '_' không được đứng ngay sau tiền tố
// long bad5 = 123_L;    // '_' không được đứng trước hậu tố L
```

Các dòng này đều là comment để chương trình mẫu không gặp lỗi biên dịch. Thêm hậu tố `L` cho literal nguyên để chọn kiểu `long`; tiền tố `0b`, `0`, `0x` chỉ chọn **cơ số**, không chọn `byte`/`short` hay `long`.

Với literal nguyên chưa có `L`, kiểu là `int`; có `L`, kiểu là `long`, trong phạm vi cách viết hợp lệ. Java cho phép vài hằng số nguyên thập phân đặc biệt dưới dạng toán tử trừ đơn ngôi với trị nhỏ nhất như `-2147483648`; thường dùng `Integer.MIN_VALUE` và `Long.MIN_VALUE` để khỏi nhầm giới hạn.

**Lưu ý khi gán biến nhỏ:** Java có thể cho phép `byte b = 0x7F;` vì đây là biểu thức hằng `int` mà giá trị 127 vừa `byte`. Điều đó không có nghĩa `0x7F` thuộc kiểu `byte`. `byte b = 0xFF;` lỗi biên dịch vì 255 ngoài miền `byte`, trừ khi ép kiểu chủ động.

## 5. Chương trình chứng minh bốn cách viết là cùng một số

Lưu tệp `RadixLiteralDemo.java`:

```java
public class RadixLiteralDemo {
    public static void main(String[] args) {
        int decimal = 42;
        int binary = 0b101010;
        int octal = 052;
        int hex = 0x2A;

        System.out.println(decimal == binary
                && binary == octal
                && octal == hex);
        System.out.println("decimal: " + decimal);
        System.out.println("binary: " + Integer.toBinaryString(decimal));
        System.out.println("octal: " + Integer.toOctalString(decimal));
        System.out.println("hex: " + Integer.toHexString(decimal));
        System.out.println("010 in Java = " + 010);
        System.out.println("0xFF = " + 0xFF);
        System.out.println("0b11111111 = " + 0b11111111);
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac RadixLiteralDemo.java
java RadixLiteralDemo
```

Kết quả chính xác:

```text
true
decimal: 42
binary: 101010
octal: 52
hex: 2a
010 in Java = 8
0xFF = 255
0b11111111 = 255
```

`Integer.toBinaryString`, `toOctalString` và `toHexString` **trả về chuỗi chữ số**, không tự thêm tiền tố nguồn `0b`/`0`/`0x`. Chuỗi hex mặc định dùng a–f chữ thường.

## 6. Liên hệ hệ cơ số với bit và số có dấu

### 6.1. Các nhóm bit đổi sang hex hoặc bát phân

Vì \(16=2^4\), chia biểu diễn nhị phân thành **nhóm 4 bit từ phải sang trái** để đổi sang hex:

```text
binary:       0010 1010
hex digits:      2    A
hex:             0x2A
```

Vì \(8=2^3\), chia nhị phân thành **nhóm 3 bit từ phải sang trái** để đổi sang bát phân:

```text
binary:     101 010
oct digits:   5   2
octal:        052
```

Nếu nhóm bên trái chưa đủ 4 hoặc 3 bit, chỉ cần thêm số 0 ở **bên trái phần biểu diễn số dương** để dễ đọc, không làm thay đổi giá trị.

### 6.2. Cơ số không làm mất quy tắc số nguyên có dấu

`int` luôn có 32 bit, `long` luôn có 64 bit. Cách biểu diễn số nguyên có dấu trong Java là **bù hai** (*two's complement*).

Vì vậy, một literal không thập phân đủ 32 bit với bit cao nhất là 1 có thể mang giá trị `int` **âm**:

```java
int allOnes = 0xFFFF_FFFF;        // -1 dưới dạng int 32 bit
int lowest = 0x8000_0000;        // Integer.MIN_VALUE
long positive = 0xFFFF_FFFFL;    // 4294967295L (64 bit)
long longAllOnes = 0xFFFF_FFFF_FFFF_FFFFL; // -1 dưới dạng long
```

Sự khác nhau giữa `0xFFFF_FFFF` và `0xFFFF_FFFFL` là **hậu tố `L`**: cùng những chữ số hex nhưng được biểu diễn thành giá trị kiểu `int` hoặc `long`. Với `int`, 32 bit tất cả bằng 1 là -1; với `long`, cùng mẫu 32 bit ấy được mở rộng bằng các bit 0 phía trước, nên là số dương 4_294_967_295.

Đặc biệt, `0xFFFF_FFFF` **không mang giá trị dương 4_294_967_295** nếu lưu dưới dạng `int` có dấu. Nếu cần diễn giải 32 bit không dấu, có thể dùng `Integer.toUnsignedLong(int)` hoặc `Integer.toUnsignedString(int)`.

### 6.3. Một chuỗi bit có nhiều cách diễn giải

Ví dụ 8 bit `1111_1111` có thể là:

- **255** nếu diễn giải theo 8 bit không dấu.
- **-1** nếu diễn giải theo kiểu `byte` có dấu và dùng bù hai.

Trong Java, literal `0b1111_1111` trước tiên là `int` 255. Phép ép `(byte) 0b1111_1111` giữ 8 bit thấp rồi hiểu chúng như `byte` có dấu, cho ra -1.

Đừng nhầm chuyện này với việc **đổi cơ số**. Đổi từ `0xFF` sang `0b1111_1111` chỉ đổi cách viết cùng số 255; ép sang `byte` có thể đổi giá trị do thay đổi **miền kiểu dữ liệu**.

## 7. Đổi số thành chuỗi và đọc chuỗi theo cơ số

Literal dùng khi viết **mã nguồn**. Dữ liệu đọc từ người dùng, file hoặc mạng là **chuỗi lúc chạy**, cần API chuyển đổi. Java cung cấp:

| Nhu cầu | API phổ biến | Ví dụ kết quả |
|---|---|---|
| Số nguyên → nhị phân | `Integer.toBinaryString(42)` | `"101010"` |
| Số nguyên → bát phân | `Integer.toOctalString(42)` | `"52"` |
| Số nguyên → hex | `Integer.toHexString(42)` | `"2a"` |
| Số nguyên → chuỗi theo cơ số tùy chọn | `Integer.toString(42, 16)` | `"2a"` |
| Chuỗi nhị phân → `int` | `Integer.parseInt("101010", 2)` | 42 |
| Chuỗi bát phân → `int` | `Integer.parseInt("52", 8)` | 42 |
| Chuỗi hex → `int` | `Integer.parseInt("2A", 16)` | 42 |
| Chuỗi thập phân → `int` | `Integer.parseInt("42", 10)` | 42 |

`Integer.parseInt(String, int)` và `Integer.toString(int, int)` hỗ trợ hệ cơ số **2 đến 36**. Với cơ số lớn hơn 10, Java dùng các chữ cái a–z cho các chữ số bổ sung, khi cần.

**Bẫy tiền tố:** `Integer.parseInt("0x2A", 16)` sẽ ném `NumberFormatException` vì `parseInt` yêu cầu **các chữ số thuộc cơ số** (có thể kèm dấu) và không bỏ tiền tố `0x` như cú pháp nguồn Java. `Integer.decode("0x2A")` có thể nhận tiền tố `0x`; `Integer.decode("052")` hiểu theo bát phân, còn `Integer.decode("42")` hiểu thập phân. `Integer.decode` không nhận tiền tố nhị phân `0b`.

Không dùng `Integer.parseInt("052")` mặc định để kỳ vọng ra 42: overload không có đối số cơ số sẽ đọc **thập phân**, nên kết quả là 52.

### Ví dụ chạy được: parse và định dạng

Lưu `RadixConversionDemo.java`:

```java
public class RadixConversionDemo {
    public static void main(String[] args) {
        int fromBinary = Integer.parseInt("101010", 2);
        int fromOctal = Integer.parseInt("52", 8);
        int fromHex = Integer.parseInt("2A", 16);

        System.out.println(fromBinary + ", " + fromOctal + ", " + fromHex);
        System.out.println(Integer.toString(42, 16));
        System.out.println(Integer.decode("0x2A"));
        System.out.println(Integer.parseInt("052"));
        System.out.println(Integer.toUnsignedLong(0xFFFF_FFFF));

        try {
            Integer.parseInt("0x2A", 16);
        } catch (NumberFormatException e) {
            System.out.println("parseInt: invalid prefix");
        }
    }
}
```

Chạy:

```bash
javac RadixConversionDemo.java
java RadixConversionDemo
```

Kết quả:

```text
42, 42, 42
2a
42
52
4294967295
parseInt: invalid prefix
```

Nếu số vượt miền `int`, dùng `Long.parseLong` khi vừa `long`; với số lớn hơn nữa, dùng `new java.math.BigInteger("FF...", 16)` và chủ động truyền đúng cơ số. `BigInteger(String, radix)` cũng nhận chuỗi chữ số theo cơ số, không tự dùng các tiền tố literal Java.

## 8. Cách in giá trị số theo cơ số

`System.out.println(number)` in số nguyên theo **thập phân**. Khi muốn in nhị phân/bát phân/hex, dùng các phương thức chuyển đổi ở trên hoặc `printf`.

```java
int n = 42;
System.out.printf("dec=%d, oct=%o, hex=%x, HEX=%X%n", n, n, n, n);
```

Kết quả:

```text
dec=42, oct=52, hex=2a, HEX=2A
```

Trong `printf`, `%d` là thập phân, `%o` là bát phân, `%x`/`%X` là hex. **`%b` KHÔNG có nghĩa là nhị phân** trong `Formatter` của Java; nó là định dạng boolean. Để in binary, dùng `Integer.toBinaryString(n)` hoặc `Long.toBinaryString(n)`.

Khi in số âm với `toBinaryString`/`toHexString`, kết quả phản ánh **mẫu bit bù hai không dấu** của kiểu tương ứng; ví dụ `Integer.toHexString(-1)` trả `"ffffffff"`, không phải `"-1"`. Nếu cần biểu diễn có dấu theo một cơ số, dùng `Integer.toString(value, radix)`: `Integer.toString(-1, 16)` trả `"-1"`.

Cũng cần phân biệt **hiển thị text** và **mã hóa nhị phân**. Chuỗi `"FF"` chứa hai ký tự F, không tự trở thành một byte `0xFF`. Phải parse theo cơ số rồi chọn cách ghi byte phù hợp.

## 9. Những lỗi điển hình và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `010` cho 8 thay vì 10 | Số 0 đầu tiên biến literal thành bát phân | Viết `10` nếu muốn mười thập phân |
| `08` không biên dịch | Số 8 không thuộc cơ số 8 | Bỏ số 0 đầu hoặc sửa chữ số |
| `0o12` không biên dịch | Java không có tiền tố `0o` | Dùng `012` |
| `0b102` không biên dịch | 2 không hợp lệ trong hệ 2 | Chỉ viết 0, 1 |
| `0xGG` không biên dịch | G không thuộc các chữ số hex | Chỉ viết 0–9, A–F |
| `0x_FF` không biên dịch | Gạch dưới sát tiền tố | Viết `0xFF` hoặc `0xF_F` |
| `0xFFFF_FFFF` thành -1 | Mẫu bit int 32 bit có dấu | Sử dụng `0xFFFF_FFFFL` hoặc API unsigned khi phù hợp |
| `Integer.parseInt("FF")` báo lỗi | Mặc định parse thập phân | Truyền cơ số 16 |
| `Integer.parseInt("0xFF",16)` báo lỗi | `parseInt` không nhận `0x` | Dùng `"FF"` với radix 16 hoặc `Integer.decode` |
| `printf("%b", 42)` in `true` | `%b` là boolean formatter | Dùng `Integer.toBinaryString(42)` |

Một số nguyên có thể lưu cùng các bit cho dù bạn đã viết literal ở hệ nào. Nếu thao tác bitmask, **hex dễ nhìn theo byte**; nếu cần quan sát từng bit, **binary trực quan**; bát phân thường thấy trong định dạng/quy ước cũ; thập phân dễ đọc với dữ liệu nghiệp vụ. Chọn cách viết phù hợp người đọc và định dạng dữ liệu.

## 10. Bài tập tự kiểm tra

**Bài 1.** `0b1111`, `017`, `15`, `0xF` có bằng nhau không?  
**Đáp án:** Có, cả bốn đều bằng 15 thập phân.

**Bài 2.** `010` và `10` có cùng giá trị không?  
**Đáp án:** Không; `010` = 8 thập phân, `10` = 10 thập phân.

**Bài 3.** Chuyển `0x3C` sang nhị phân và thập phân.  
**Đáp án:** `0b0011_1100` (có thể bỏ các số 0 đầu là `0b11_1100`), bằng \(3\times16+12=60\).

**Bài 4.** Vì sao `Integer.toBinaryString(-1)` xuất ra 32 chữ số `1`, còn `Integer.toString(-1, 2)` xuất `"-1"`?  
**Đáp án:** Phương thức thứ nhất trình bày **mẫu bit bù hai** của `int` 32 bit; phương thức thứ hai biểu diễn **giá trị số có dấu** trong cơ số 2.

**Bài 5.** Dùng API nào để parse chuỗi `"11111111"` thành giá trị số 255?  
**Đáp án:** `Integer.parseInt("11111111", 2)`. Nếu ép tiếp sang `byte`, giá trị trở thành -1 vì miền kiểu `byte`.

**Bài 6.** `0xFFFF_FFFFL` có khác `0xFFFF_FFFF` không?  
**Đáp án:** Có; dạng `L` là `long` dương 4_294_967_295, dạng không hậu tố là `int` -1.

**Bài 7.** Vì sao `Integer.parseInt("052")` trả 52 nhưng literal `052` trong mã nguồn là 42?  
**Đáp án:** `parseInt` không truyền radix mặc định dùng **thập phân**, còn literal có số 0 đứng đầu dùng **bát phân**.

**Ghi nhớ:** Cơ số quyết định cách *viết/đọc chữ số*; kiểu dữ liệu quyết định *miền số và độ rộng bit*. Trong Java: **thập phân** viết thường, **nhị phân** bắt đầu `0b`, **bát phân** bắt đầu `0`, **hex** bắt đầu `0x`. Khi xử lý chuỗi từ bên ngoài, truyền cơ số rõ ràng và kiểm tra miền giá trị trước khi ép kiểu.

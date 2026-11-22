# Đọc mẫu bit của literal hex khi bit dấu được bật trong Java

Với Java, literal thập lục phân như `0x8000_0000` thường khiến người mới học ngạc nhiên: khi in ra dưới dạng `int`, kết quả là **-2_147_483_648** chứ không phải số dương 2_147_483_648. Tương tự, `0xFFFF_FFFF` có giá trị **-1** nếu là `int`; nhưng `0xFFFF_FFFFL` có giá trị **4_294_967_295** khi là `long`.

Không có sự thay đổi tùy ý của các chữ số hex. Điều cần xác định là **mẫu bit có bao nhiêu bit, bit cao nhất của kiểu có được bật hay không, và ta đang đọc mẫu bit đó như số nguyên có dấu hay không dấu**.

## 1. Từ chữ số hex đến mẫu bit

Hệ thập lục phân có 16 ký hiệu `0`–`9` và `A`–`F`. Mỗi chữ số hex tương ứng **4 bit**. Ví dụ:

| Hex | Nhị phân 4 bit | Giá trị hex |
| --- | --- | ---: |
| `0` | `0000` | 0 |
| `7` | `0111` | 7 |
| `8` | `1000` | 8 |
| `F` | `1111` | 15 |

Mỗi chữ số hex ghép vào mẫu bit theo thứ tự từ trái sang phải. Ví dụ, `0x8000_0000` tương ứng mẫu `10000000 00000000 00000000 00000000` (32 bit): chỉ bit ở vị trí cao nhất được bật. `0xFFFF_FFFF` biểu diễn 32 bit bằng 1.

Tiền tố `0x` (hoặc `0X`) chỉ cho trình biên dịch biết literal dùng **cơ số 16**; chữ `L` cuối literal chọn kiểu `long`. Dấu gạch dưới `_` chỉ giúp nhóm chữ số cho dễ đọc: `0xFFFF_FFFF` và `0xFFFFFFFF` hoàn toàn tương đương.

## 2. Phạm vi của `int` và `long`: bit nào là bit dấu?

Java dùng kiểu nguyên có dấu `int` **32 bit** và `long` **64 bit**, với biểu diễn **bù hai (two's complement)**. Vị trí bit được đánh số từ 0 ở phía phải.

| Kiểu | Tổng số bit | Bit dấu | Mẫu có bit dấu = 0 | Mẫu có bit dấu = 1 |
| --- | ---: | ---: | --- | --- |
| `int` | 32 | bit 31 | Giá trị không âm | Giá trị âm |
| `long` | 64 | bit 63 | Giá trị không âm | Giá trị âm |

- `0x7FFF_FFFF`: bit 31 bằng 0, giá trị `int` bằng **2_147_483_647**.
- `0x8000_0000`: bit 31 bằng 1, giá trị `int` bằng **-2_147_483_648** (`Integer.MIN_VALUE`).
- `0xFFFF_FFFF`: mọi bit đều bằng 1, giá trị `int` bằng **-1**.
- `0x7FFF_FFFF_FFFF_FFFFL`: bit 63 bằng 0, giá trị `long` bằng **9_223_372_036_854_775_807**.
- `0x8000_0000_0000_0000L`: bit 63 bằng 1, giá trị `long` bằng **-9_223_372_036_854_775_808** (`Long.MIN_VALUE`).
- `0xFFFF_FFFF_FFFF_FFFFL`: mọi bit đều bằng 1, giá trị `long` bằng **-1**.

**Quan trọng:** một chữ số hex bắt đầu bằng `8` hoặc `F` **không tự động** biến cả literal thành số âm. Chẳng hạn `0x8` là `int` dương 8, `0xFF` là `int` dương 255, vì bit dấu ở vị trí 31 vẫn bằng 0. Chỉ khi bit dấu của **độ rộng kiểu thực tế** được bật thì diễn giải có dấu mới là âm. Đối với `int`, 8 chữ số hex có thể phủ hết 32 bit; đối với `long`, 16 chữ số hex có thể phủ hết 64 bit.

## 3. Đọc số có dấu từ mẫu bit bù hai

Hãy tưởng tượng cùng một mẫu bit có giá trị **không dấu** `U` với độ rộng `w` bit. Giá trị **có dấu** là:

```text
signed = U                  nếu bit dấu = 0
signed = U - 2^w            nếu bit dấu = 1
```

Với `int` (`w = 32`):

1. `0x8000_0000` có giá trị không dấu `U = 2^31 = 2_147_483_648`. Vì bit 31 bằng 1, giá trị có dấu là `2_147_483_648 - 4_294_967_296 = -2_147_483_648`.
2. `0xFFFF_FFFF` có giá trị không dấu `U = 2^32 - 1 = 4_294_967_295`. Giá trị có dấu là `4_294_967_295 - 4_294_967_296 = -1`.
3. `0xF000_0000` có giá trị không dấu `4_026_531_840`, còn giá trị có dấu là **-268_435_456**.

Với `long` (`w = 64`), `0x8000_0000_0000_0000L` là `-2^63`, còn `0xFFFF_FFFF_FFFF_FFFFL` là `-1L`. Nếu diễn giải mẫu toàn bit 1 dưới dạng **không dấu 64 bit**, giá trị của nó là `2^64 - 1 = 18_446_744_073_709_551_615`; giá trị này không chứa được trong `long` dương có dấu.

Đây là **hai cách diễn giải cùng mẫu bit**. Java không cần đảo bit hoặc sửa literal để in ra số âm: cách đọc là hệ quả của định nghĩa kiểu `int` và `long`.

## 4. Vì sao literal hex có thể bật bit dấu mà vẫn hợp lệ?

Ở literal **thập phân**, `2_147_483_648` không có hậu tố `L` thường vượt phạm vi `int` và gây lỗi biên dịch. Ở literal **không thập phân** như hex, Java cho phép mô tả trực tiếp mẫu 32 bit của `int`, kể cả bit cao nhất bằng 1. Vì vậy đoạn sau hợp lệ:

```java
int a = 0x8000_0000; // -2147483648
int b = 0xFFFF_FFFF; // -1
```

Hai dòng trên là **mảnh mã** có thể đặt trong phương thức. Không nên suy rằng `0xFFFF_FFFF` lớn hơn `Integer.MAX_VALUE` sẽ làm Java tự nâng thành `long`: literal không `L` vẫn thuộc `int`, và diễn giải thành số âm theo mẫu bit. Tuy nhiên, mẫu đòi hỏi hơn 32 bit **có nghĩa** không thể dùng làm `int` literal, chẳng hạn `0x1_0000_0000` (không có `L`) không hợp lệ; dạng `0x1_0000_0000L` là `long` hợp lệ.

Với `long`, literal hex có hậu tố `L` có thể mô tả mẫu 64 bit, kể cả bật bit 63:

```java
long c = 0x8000_0000_0000_0000L; // Long.MIN_VALUE
long d = 0xFFFF_FFFF_FFFF_FFFFL; // -1L
```

Chữ `L` xác định **độ rộng 64 bit**, không có nghĩa “giá trị chắc chắn dương”. Nếu bit 63 bằng 1, một `long` vẫn là số âm.

## 5. Cùng chữ số hex nhưng thêm `L` có thể đổi kết quả

Một tình huống quan trọng là so sánh **`0xFFFF_FFFF`** với **`0xFFFF_FFFFL`**:

| Biểu thức | Kiểu literal | Mẫu bit của kiểu | Giá trị có dấu |
| --- | --- | --- | ---: |
| `0xFFFF_FFFF` | `int` | 32 bit 1 | -1 |
| `0xFFFF_FFFFL` | `long` | 32 bit thấp 1, **32 bit cao 0** | 4_294_967_295 |
| `0x8000_0000` | `int` | chỉ bit 31 bằng 1 | -2_147_483_648 |
| `0x8000_0000L` | `long` | chỉ bit 31 bằng 1; bit 63 bằng 0 | 2_147_483_648 |

Đây chính là lý do cần nhìn **kiểu literal** trước khi kết luận một chữ số hex biểu diễn số âm hay dương. Chẳng hạn `0x8000_0000` có bit 31 bật nên âm đối với `int`. Nhưng `0x8000_0000L` là `long`: bit 31 chỉ là một bit giá trị, còn bit dấu 63 bằng 0, nên dương.

## 6. Gán `int` âm vào `long`: mở rộng dấu và mở rộng bằng 0

Khi chuyển `int` âm sang `long`, Java dùng **mở rộng dấu (sign extension)**: giữ nguyên giá trị số học bằng cách điền thêm bit 1 ở phía cao. Vì vậy:

```java
int bits = 0xFFFF_FFFF;                 // -1
long signed = bits;                     // -1L
long unsigned = Integer.toUnsignedLong(bits); // 4294967295L
long masked = bits & 0xFFFF_FFFFL;      // 4294967295L
```

Các khai báo này là mảnh mã. Với `signed`, mẫu `int` gồm 32 bit 1 được sign-extend thành `0xFFFF_FFFF_FFFF_FFFF` (64 bit 1), vẫn mang giá trị `-1L`. Với `unsigned` và `masked`, mục tiêu là **diễn giải 32 bit gốc như số không dấu**, tức điền 32 bit cao bằng 0 để có `0x0000_0000_FFFF_FFFF` = `4_294_967_295L`.

Hai cách chuyển quan trọng khi giữ nguyên thông tin mẫu bit:

- `Integer.toUnsignedLong(bits)`: thể hiện rõ ý định coi 32 bit của `int` như một giá trị không dấu từ 0 tới `2^32 - 1`.
- `bits & 0xFFFF_FFFFL`: thực hiện phép AND với một mặt nạ **`long`**, khiến phép toán ở 64 bit và chỉ giữ 32 bit thấp. Nếu dùng `bits & 0xFFFF_FFFF` (hai toán hạng đều `int`) thì vẫn nhận `int` có dấu; phép gán tiếp sang `long` lại mở rộng dấu.

Đừng nhầm **`long signed = 0xFFFF_FFFF;`** với **`long unsigned = 0xFFFF_FFFFL;`**. Trong trường hợp đầu, literal là `int` -1 rồi được mở rộng dấu thành `long` -1; trong trường hợp sau, bản thân literal là `long` dương `4_294_967_295L`.

## 7. Chương trình hoàn chỉnh chạy trên Java 17+

Tạo tệp **`HexSignBitDemo.java`** với nội dung sau:

```java
public class HexSignBitDemo {
    public static void main(String[] args) {
        int largestPositive = 0x7FFF_FFFF;
        int intSignBit = 0x8000_0000;
        int intAllOnes = 0xFFFF_FFFF;

        long widened = intAllOnes;
        long zeroExtended = Integer.toUnsignedLong(intAllOnes);
        long longFromSameDigits = 0xFFFF_FFFFL;
        long longSignBit = 0x8000_0000_0000_0000L;
        long longAllOnes = 0xFFFF_FFFF_FFFF_FFFFL;

        System.out.println("max positive int=" + largestPositive);
        System.out.println("int sign bit=" + intSignBit);
        System.out.println("int all ones=" + intAllOnes);
        System.out.println("int hex=" + String.format("%08X", intSignBit));
        System.out.println("int binary=" + Integer.toBinaryString(intSignBit));
        System.out.println("widened=" + widened);
        System.out.println("widened hex=" + Long.toHexString(widened));
        System.out.println("zero extended=" + zeroExtended);
        System.out.println("zero extended hex=" + Long.toHexString(zeroExtended));
        System.out.println("same digits with L=" + longFromSameDigits);
        System.out.println("long sign bit=" + longSignBit);
        System.out.println("long all ones=" + longAllOnes);
        System.out.println("long all ones unsigned=" + Long.toUnsignedString(longAllOnes));
        System.out.println("unsigned int text=" + Integer.toUnsignedString(intAllOnes));
        System.out.println("unsigned mask=" + (intSignBit & 0xFFFF_FFFFL));
        System.out.println("signed right shift=" + (intSignBit >> 31));
        System.out.println("unsigned right shift=" + (intSignBit >>> 31));
        System.out.println("parse unsigned hex=" + Integer.toUnsignedLong(Integer.parseUnsignedInt("FFFFFFFF", 16)));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 HexSignBitDemo.java
java HexSignBitDemo
```

Kết quả stdout:

```text
max positive int=2147483647
int sign bit=-2147483648
int all ones=-1
int hex=80000000
int binary=10000000000000000000000000000000
widened=-1
widened hex=ffffffffffffffff
zero extended=4294967295
zero extended hex=ffffffff
same digits with L=4294967295
long sign bit=-9223372036854775808
long all ones=-1
long all ones unsigned=18446744073709551615
unsigned int text=4294967295
unsigned mask=2147483648
signed right shift=-1
unsigned right shift=1
parse unsigned hex=4294967295
```

Các dòng đáng chú ý:

- `int hex=80000000` và `int binary=1000...` cho thấy **mẫu bit 32 bit**; dòng `int sign bit=-2147483648` cho thấy **giá trị có dấu** của chính mẫu đó.
- `widened hex=ffffffffffffffff` minh họa mở rộng dấu của `int` -1 sang `long`; `zero extended hex=ffffffff` hiển thị không có chữ số 0 dẫn đầu, nhưng giá trị tương đương mẫu 64 bit `00000000ffffffff`.
- `same digits with L=4294967295` cho thấy khi literal được khai báo là `long` ngay từ đầu, bit dấu 63 không được bật.
- `long all ones=-1` nhưng `long all ones unsigned=18446744073709551615` là hai cách hiển thị có dấu và không dấu của **cùng 64 bit toàn 1**.
- `unsigned mask=2147483648` minh họa mặt nạ `long` giữ giá trị không dấu của `0x8000_0000`.
- `signed right shift=-1` và `unsigned right shift=1` cho thấy khác biệt giữa `>>` và `>>>` khi dịch bit của số âm.

## 8. In ra mẫu bit thay vì chỉ xem giá trị thập phân

`System.out.println(value)` sử dụng giá trị `int`/`long` **có dấu**. Khi cần quan sát mẫu bit, dùng:

```java
int x = 0x8000_0000;
System.out.println(Integer.toHexString(x));    // "80000000"
System.out.println(Integer.toBinaryString(x)); // "10000000000000000000000000000000"
System.out.printf("%08X%n", x);                // 80000000
```

Đây là các câu lệnh đặt trong `main`. `Integer.toHexString` và `Integer.toBinaryString` cho chuỗi biểu diễn mẫu bit theo cơ số tương ứng; `printf("%08X%n", x)` yêu cầu ít nhất 8 ký tự hex, thêm các số 0 dẫn đầu nếu thiếu. Với `long`, có thể dùng `Long.toHexString(value)` hoặc `%016X` nếu muốn hiển thị đủ 16 chữ số.

Phân biệt **hình thức trình bày** và **giá trị lưu**: `Integer.toHexString(-1)` là `"ffffffff"`, không có dấu trừ, nhưng `Integer.toString(-1)` là `"-1"`. Chỉ vì chuỗi hex không có dấu `-` không có nghĩa số `int` hiện tại dương.

## 9. Dịch phải có dấu và dịch phải không dấu

Khi bit dấu đã bật, hai toán tử dịch phải có ý nghĩa khác nhau:

```java
int x = 0x8000_0000;
int arithmetic = x >> 31; // -1: điền thêm 1 ở phía trái.
int logical = x >>> 31;   // 1: điền thêm 0 ở phía trái.
```

`>>` là **dịch phải giữ dấu (arithmetic shift)**; `>>>` là **dịch phải không giữ dấu (logical shift)**. Hai toán tử này đều làm việc với mẫu bit, còn cách biểu diễn kết quả vẫn phụ thuộc kiểu `int` hoặc `long` của toán hạng. Chúng không thay đổi kiểu của biến thành kiểu “unsigned”; Java vẫn lưu `int`/`long` có dấu.

Để kiểm tra bit dấu của `int`, có thể viết `(x & 0x8000_0000) != 0` hoặc đơn giản `x < 0`. Với `long`, dùng mặt nạ `0x8000_0000_0000_0000L`. Đừng dùng `x > 0` để phát hiện xem bất kỳ bit nào được bật: ví dụ `-1` có **mọi bit bật** nhưng lại nhỏ hơn 0.

## 10. Đọc hex từ chuỗi và giữ cách diễn giải không dấu

Khi giá trị hex nằm trong văn bản, phải phân biệt cách phân tích có dấu/không dấu:

```java
int signedBits = Integer.parseUnsignedInt("FFFFFFFF", 16);
String unsignedText = Integer.toUnsignedString(signedBits); // "4294967295"
long unsignedValue = Integer.toUnsignedLong(signedBits);   // 4294967295L
long parsedLong = Long.parseLong("FFFFFFFF", 16);           // 4294967295L
```

Đoạn trên là mảnh mã hợp lệ trong một phương thức. `Integer.parseUnsignedInt` cho phép phân tích mẫu thuộc khoảng không dấu 32 bit, nhưng **kết quả lưu trong `int`**; vì vậy `signedBits` có giá trị số học có dấu `-1`. Dùng `Integer.toUnsignedString` hoặc `Integer.toUnsignedLong` khi muốn diễn giải thành không dấu.

`Integer.parseInt("FFFFFFFF", 16)` sẽ báo `NumberFormatException` do giá trị hex dương tương ứng vượt `Integer.MAX_VALUE` trong cách parse có dấu. Trong khi đó, `Long.parseLong("FFFFFFFF", 16)` thành công vì giá trị đó vẫn nằm trong phạm vi dương của `long`.

Đối với mẫu không dấu **64 bit** có giá trị lớn hơn `Long.MAX_VALUE`, `Long.parseUnsignedLong("FFFFFFFFFFFFFFFF", 16)` trả về mẫu bit nằm trong `long` (biểu diễn có dấu là `-1L`); `Long.toUnsignedString(-1L)` hiển thị giá trị không dấu `18446744073709551615`. Nếu muốn một **đối tượng số nguyên dương thật sự** lưu giá trị đó để tính toán tùy độ lớn, dùng `new java.math.BigInteger("FFFFFFFFFFFFFFFF", 16)`.

## 11. Những nhầm lẫn phổ biến

| Nhầm lẫn | Thực tế | Cách đọc đúng |
| --- | --- | --- |
| `0x8` âm vì hex bắt đầu bằng 8 | `int` vẫn có bit 31 bằng 0 | `0x8 == 8` |
| `0x8000_0000` là số dương 2_147_483_648 | `int` có bit 31 bằng 1 | `-2_147_483_648` |
| `0xFFFF_FFFF` không thể là `int` vì “quá lớn” | Literal hex có thể diễn tả 32 bit toàn 1 | `int` bằng `-1` |
| Thêm `L` luôn biến mẫu hex thành số dương | `long` cũng có bit dấu 63 | `0xFFFF_FFFF_FFFF_FFFFL == -1L` |
| `long x = 0xFFFF_FFFF;` thành 4_294_967_295 | Literal có kiểu `int` âm rồi được mở rộng dấu | `x == -1L` |
| `x & 0xFFFF_FFFF` làm `int` thành số dương không dấu | AND trên hai `int` vẫn cho `int` | Dùng `Integer.toUnsignedLong(x)` hoặc mặt nạ `0xFFFF_FFFFL` |
| `Integer.toHexString(-1)` không có dấu trừ nên số dương | Chuỗi hex thể hiện mẫu bit | `"ffffffff"` là mẫu của `int` -1 |
| `>>` và `>>>` luôn giống nhau | Với bit dấu bật, cách điền bit phía trái khác nhau | `0x80000000 >> 31 == -1`, nhưng `>>> 31 == 1` |

## 12. Tự kiểm tra

1. **`int x = 0x7FFF_FFFF;`** có giá trị gì? **2_147_483_647**, vì bit 31 chưa được bật.
2. **`int x = 0xFFFF_FFFF;`** có giá trị gì? **-1**, vì đó là 32 bit toàn 1 ở dạng bù hai.
3. **`long x = 0xFFFF_FFFF;`** và **`long y = 0xFFFF_FFFFL;`** có bằng nhau không? **Không**: `x == -1L`, `y == 4_294_967_295L`.
4. **`0x8000_0000`** và **`0x8000_0000L`** có cùng giá trị số học không? **Không**: lần lượt là `-2_147_483_648` và `2_147_483_648L`.
5. **Muốn đọc `int x = 0xFFFF_FFFF;` như số không dấu, phải làm gì?** Dùng `Integer.toUnsignedLong(x)` để nhận `4_294_967_295L`, hoặc `Integer.toUnsignedString(x)` để nhận văn bản `"4294967295"`.
6. **`0x8000_0000_0000_0000L` âm hay dương?** **Âm**, bằng `Long.MIN_VALUE`, vì bit 63 đã bật.

**Kết luận:** khi gặp literal hex có bit dấu bật, hãy xác định **kiểu literal (32 hay 64 bit)**, tìm **bit dấu ở vị trí 31 hay 63**, rồi diễn giải mẫu bit theo **bù hai**. Nếu cần giá trị không dấu, dùng API unsigned hoặc mở rộng bằng 0; nếu gán một `int` âm sang `long`, nhớ rằng Java sẽ **mở rộng dấu**, không tự biến mẫu bit thành giá trị dương.

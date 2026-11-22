# `compareUnsigned`, `divideUnsigned` và `remainderUnsigned` trong Java

## 1. Vấn đề: `int`/`long` có dấu nhưng dữ liệu đôi khi phải hiểu là không dấu

Java chỉ có kiểu nguyên thủy `int` 32 bit và `long` 64 bit **có dấu**; không có kiểu nguyên thủy `uint` hay `ulong`. Tuy nhiên, cùng một chuỗi bit có thể được diễn giải thành số có dấu hoặc không dấu:

| Mẫu bit | Diễn giải có dấu | Diễn giải không dấu |
| --- | ---: | ---: |
| `int` toàn bit `0` | 0 | 0 |
| `int` `0x7FFFFFFF` | 2.147.483.647 | 2.147.483.647 |
| `int` `0x80000000` | -2.147.483.648 | 2.147.483.648 |
| `int` `0xFFFFFFFF` | -1 | 4.294.967.295 |
| `long` `0xFFFFFFFFFFFFFFFFL` | -1 | 18.446.744.073.709.551.615 |

Với 32 bit, miền không dấu là `0..2^32-1`; với 64 bit, miền không dấu là `0..2^64-1`. Hai cách hiểu **không thay đổi các bit đang lưu**. Chúng chỉ thay đổi ý nghĩa của việc so sánh, chia, lấy dư hoặc hiển thị các bit đó.

Ví dụ, `int value = -1;` có mẫu bit `0xFFFFFFFF`. Nếu dùng quy tắc số có dấu, `-1 < 1`; nếu diễn giải như số không dấu 32 bit, `4_294_967_295 > 1`. Java cung cấp các phương thức tĩnh giúp thực hiện **phép toán theo cách hiểu không dấu** mà vẫn dùng `int`/`long`.

Ba nhóm API chính (có từ Java 8):

- `Integer.compareUnsigned(int x, int y)` và `Long.compareUnsigned(long x, long y)`.
- `Integer.divideUnsigned(int dividend, int divisor)` và `Long.divideUnsigned(long dividend, long divisor)`.
- `Integer.remainderUnsigned(int dividend, int divisor)` và `Long.remainderUnsigned(long dividend, long divisor)`.

Các phương thức này phù hợp khi một **giao thức, trường bit, định dạng file, bộ đếm hoặc mã định danh** định nghĩa các bit là số nguyên không dấu. Chúng không biến Java thành ngôn ngữ có kiểu nguyên thủy unsigned mới.

## 2. Ngữ nghĩa của `compareUnsigned`

`compareUnsigned(x, y)` so sánh hai mẫu bit sau khi diễn giải chúng là **số không dấu**, rồi trả về một `int`:

- Giá trị **âm**: `x` nhỏ hơn `y` theo thứ tự không dấu.
- `0`: hai mẫu bit bằng nhau.
- Giá trị **dương**: `x` lớn hơn `y` theo thứ tự không dấu.

Không nên phụ thuộc vào giá trị chính xác là `-1` hay `1`; hợp đồng của phương thức là **dấu của kết quả**. Khi dùng Comparator, kiểm tra `< 0`, `== 0` hoặc `> 0`.

```java
int a = -1;  // bit 0xFFFFFFFF => unsigned 4294967295.
int b = 1;

System.out.println(Integer.compare(a, b) < 0);         // true.
System.out.println(Integer.compareUnsigned(a, b) > 0); // true.
```

Với phép so sánh thông thường, `-1 < 1`. Với unsigned, `0xFFFFFFFF` đại diện cho `4_294_967_295` nên lớn hơn `1`.

Một cách đọc nhanh mẫu bit:

- Nếu hai `int` cùng có bit dấu bằng `0`, so sánh có dấu và không dấu có cùng thứ tự.
- Nếu hai `int` cùng có bit dấu bằng `1`, thứ tự so sánh của chúng cũng giống nhau (cả hai cùng nằm ở nửa cao của miền unsigned).
- Nếu một giá trị có bit dấu `1` (hiện ra là số âm) và giá trị kia có bit dấu `0`, **giá trị hiện ra âm sẽ lớn hơn theo unsigned**.

Quy tắc tương tự áp dụng cho `long` với 64 bit.

### Ví dụ sắp xếp theo thứ tự không dấu

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(-1, 2, 0, -2));
numbers.sort(Integer::compareUnsigned);
System.out.println(numbers); // [0, 2, -2, -1]
```

Danh sách vẫn in các giá trị theo kiểu `int` **có dấu**, nhưng thứ tự sắp xếp đã dựa trên ý nghĩa unsigned: `0`, `2`, `4_294_967_294`, `4_294_967_295`. Đừng dùng `Comparator.naturalOrder()` hoặc phép so sánh `<` có dấu nếu trường dữ liệu bắt buộc được xếp theo unsigned.

Lưu ý `Arrays.sort(int[])` sắp xếp theo số `int` có dấu. Để có comparator unsigned, ví dụ trên dùng danh sách `Integer` hoặc cần triển khai chiến lược sắp xếp unsigned riêng.

## 3. Ngữ nghĩa của `divideUnsigned` và `remainderUnsigned`

Với hai mẫu bit có cùng độ rộng `w`, đặt:

- `A` là giá trị không dấu của `dividend`, trong miền `0..2^w-1`.
- `B` là giá trị không dấu của `divisor`, **phải khác 0**.
- `Q = floor(A / B)` là thương nguyên không dấu.
- `R = A - B * Q` là số dư, thỏa `0 <= R < B`.

Khi `divisor` có mẫu bit bằng 0, cả hai phương thức chia/lấy dư unsigned đều ném `ArithmeticException`, giống phép chia nguyên thông thường.

### Ví dụ với `int`

```java
int dividend = -1; // 0xFFFFFFFF, nghĩa unsigned = 4294967295.
int divisor = 10;

int signedQuotient = dividend / divisor;
int signedRemainder = dividend % divisor;
int unsignedQuotient = Integer.divideUnsigned(dividend, divisor);
int unsignedRemainder = Integer.remainderUnsigned(dividend, divisor);

System.out.println(signedQuotient);   // 0
System.out.println(signedRemainder);  // -1
System.out.println(unsignedQuotient); // 429496729
System.out.println(unsignedRemainder);// 5
```

Về unsigned, `4_294_967_295 = 10 × 429_496_729 + 5`. Kết quả unsigned khác hoàn toàn so với `-1 / 10 == 0` và `-1 % 10 == -1` theo phép toán có dấu. Đây là **thay đổi quy tắc số học**, không đơn thuần thay đổi cách in số.

### Trường hợp mẫu số có bit dấu bằng 1

```java
int dividend = 10;
int divisor = -1; // Nghĩa unsigned = 4294967295.

System.out.println(Integer.divideUnsigned(dividend, divisor));    // 0
System.out.println(Integer.remainderUnsigned(dividend, divisor)); // 10
```

Dưới cách hiểu unsigned, mẫu số lớn hơn tử số, nên thương bằng 0 và dư bằng chính tử số. Không được coi mẫu số `-1` là số âm khi suy luận về kết quả unsigned.

## 4. Kết quả phép chia unsigned vẫn có kiểu `int`/`long`

Đây là điểm dễ gây hiểu nhầm nhất: các API unsigned **trả về kiểu nguyên thủy có dấu của Java**.

`Integer.divideUnsigned` trả về `int`; `Long.divideUnsigned` trả về `long`. Nếu thương unsigned lớn hơn miền dương của kiểu đó, mẫu bit kết quả khi in trực tiếp có thể xuất hiện như **một số âm**.

```java
int x = -1; // unsigned 4294967295.
int q = Integer.divideUnsigned(x, 1);

System.out.println(q);                         // -1
System.out.println(Integer.toUnsignedString(q)); // 4294967295
System.out.println(Integer.toUnsignedLong(q));   // 4294967295
```

Lý do: thương unsigned thực sự là `4_294_967_295`, có mẫu bit `0xFFFFFFFF`. API trả mẫu bit đó dưới kiểu `int`, nên `System.out.println(q)` in `-1` theo cách hiểu có dấu. Muốn đọc đúng unsigned, dùng `Integer.toUnsignedString(q)` hoặc chuyển thành `long` không dấu với `Integer.toUnsignedLong(q)`.

**Đặc biệt với `long`**:

```java
long allBits = -1L; // unsigned 18446744073709551615.
long quotient = Long.divideUnsigned(allBits, 1L);

System.out.println(quotient);                       // -1
System.out.println(Long.toUnsignedString(quotient)); // 18446744073709551615
```

Không có một kiểu nguyên thủy Java nào đủ lưu toàn bộ miền unsigned 64 bit dưới dạng một **số không âm**. Nếu cần biểu diễn số nguyên toán học từ 0 đến `2^64-1`, có thể dùng `BigInteger` thông qua chuỗi unsigned:

```java
import java.math.BigInteger;

long bits = -1L;
BigInteger asPositive = new BigInteger(Long.toUnsignedString(bits));
System.out.println(asPositive); // 18446744073709551615
```

Đừng dùng `BigInteger.valueOf(bits)` trong trường hợp muốn số **không dấu**: nó bảo toàn giá trị có dấu `-1`.

## 5. So sánh unsigned không đồng nghĩa với ép kiểu mở rộng thông thường

Một `int` âm khi gán thẳng vào `long` được **mở rộng dấu**:

```java
int bits = -1;

long signedWiden = bits;
long unsignedWiden = Integer.toUnsignedLong(bits);

System.out.println(signedWiden);   // -1
System.out.println(unsignedWiden); // 4294967295
```

`Integer.toUnsignedLong(bits)` tương đương với `bits & 0xFFFF_FFFFL`. Mặt nạ giữ đúng 32 bit của `int` và xóa các bit cao trong `long`. Đây là cách có ích khi muốn làm phép tính unsigned 32 bit bằng một kiểu **đủ rộng để giữ toàn bộ giá trị 32 bit ở dạng không âm**.

```java
int a = -1;
int b = 2;

long unsignedA = Integer.toUnsignedLong(a);
long unsignedB = Integer.toUnsignedLong(b);

long quotient = unsignedA / unsignedB; // 2147483647
long remainder = unsignedA % unsignedB; // 1
```

Với `int`, cách mở rộng đúng vào `long` rồi chia hoạt động vì `long` đủ sức chứa `0..2^32-1`. Nhưng với **unsigned `long`**, không thể dùng `long` như một nơi chứa toàn bộ miền 0..2^64-1 dưới dạng số không âm. Đó là lý do `Long.divideUnsigned`/`Long.remainderUnsigned` đặc biệt hữu ích; nếu cần tính toán với số lớn vượt miền, hãy dùng `BigInteger`.

## 6. Ví dụ unsigned 64 bit: so sánh và chia mà không mất bit

```java
long maxUnsignedBits = -1L; // 0xFFFFFFFFFFFFFFFF.
long divisor = 2L;

System.out.println(Long.compare(maxUnsignedBits, 1L) < 0); // true.
System.out.println(Long.compareUnsigned(maxUnsignedBits, 1L) > 0); // true.

long q = Long.divideUnsigned(maxUnsignedBits, divisor);
long r = Long.remainderUnsigned(maxUnsignedBits, divisor);

System.out.println(Long.toUnsignedString(q)); // 9223372036854775807
System.out.println(Long.toUnsignedString(r)); // 1
```

Unsigned `2^64-1` chia `2` cho thương `2^63-1`, dư `1`. Trường hợp này thương vừa đúng miền dương `long`, nhưng các phép chia khác có thể trả về bit mang dấu âm; vì vậy dùng `Long.toUnsignedString` là thói quen tốt khi xuất dữ liệu theo định dạng unsigned.

**Lưu ý:** `Long.divideUnsigned(x, y)` không làm phép chia dấu phẩy động, không làm tròn và không trả `Infinity`. Đây là phép chia **nguyên không dấu** trên 64 bit; mẫu số bằng `0L` ném `ArithmeticException`.

## 7. Liên hệ giữa ba phép toán và quy tắc chia có dư

Với các giá trị unsigned `A`, `B != 0`, phép chia đảm bảo:

```text
A = B * Q + R
0 <= R < B
Q = floor(A / B)
```

Các biểu thức toán học phía trên được hiểu **trên miền số nguyên không dấu**. Nếu kiểm chứng bằng toán tử `*` và `+` của Java ở cùng độ rộng bit, các phép tính trung gian có thể tràn theo phép toán nguyên cố định và kết quả hiển thị dưới dạng số có dấu.

Để kiểm chứng một ví dụ unsigned 32 bit một cách dễ đọc, hãy dùng `long` và `Integer.toUnsignedLong`:

```java
int a = -1;
int b = 10;
int q = Integer.divideUnsigned(a, b);
int r = Integer.remainderUnsigned(a, b);

long A = Integer.toUnsignedLong(a);
long B = Integer.toUnsignedLong(b);
long Q = Integer.toUnsignedLong(q);
long R = Integer.toUnsignedLong(r);

System.out.println(A == B * Q + R); // true.
System.out.println(R < B);          // true.
```

Với phép chia unsigned 64 bit, việc nhân `B * Q` có thể vượt miền `long`, nên muốn kiểm chứng bằng số nguyên toán học không mất dữ liệu có thể dùng `BigInteger` (hoặc so sánh theo quan hệ modulo phù hợp).

## 8. Chuyển dữ liệu unsigned sang/ra khỏi chuỗi

Nếu dữ liệu giao tiếp dùng văn bản thập phân unsigned, đừng lấy `String.valueOf(value)` hoặc `Integer.parseInt` làm giải pháp mặc định cho các giá trị vượt `Integer.MAX_VALUE`.

| Mục đích | API | Kết quả/ghi chú |
| --- | --- | --- |
| In `int` theo unsigned | `Integer.toUnsignedString(value)` | In từ 0 đến 4294967295. |
| In `long` theo unsigned | `Long.toUnsignedString(value)` | In từ 0 đến 18446744073709551615. |
| Đọc chuỗi unsigned 32 bit | `Integer.parseUnsignedInt(text)` | Trả `int` mang đúng mẫu bit; có thể trông âm khi in signed. |
| Đọc chuỗi unsigned 64 bit | `Long.parseUnsignedLong(text)` | Trả `long` mang đúng mẫu bit; có thể trông âm khi in signed. |
| Đọc `int` như unsigned thành `long` dương | `Integer.toUnsignedLong(value)` | Giữ 32 bit và diễn giải thành 0..4294967295. |
| Đọc unsigned `long` thành số toán học dương | `new BigInteger(Long.toUnsignedString(value))` | Có thể biểu diễn đầy đủ miền 64 bit. |

Ví dụ:

```java
int u32 = Integer.parseUnsignedInt("4294967295");
long u64 = Long.parseUnsignedLong("18446744073709551615");

System.out.println(u32);                         // -1.
System.out.println(Integer.toUnsignedString(u32)); // 4294967295.
System.out.println(u64);                         // -1.
System.out.println(Long.toUnsignedString(u64)); // 18446744073709551615.
```

Các phương thức `parseUnsignedInt` và `parseUnsignedLong` kiểm tra miền hợp lệ của kiểu unsigned tương ứng và ném `NumberFormatException` với chuỗi không hợp lệ hoặc số vượt giới hạn. Chúng **không** mở rộng kích thước biến thành một kiểu unsigned mới.

Cùng một dữ liệu có thể có cách hiển thị rất khác nhau. Khi xây dựng API, log hoặc lưu tệp, hãy thống nhất rõ **trường được mô tả là signed hay unsigned**, dùng phương thức chuyển đổi tương ứng.

## 9. So sánh với `byte`/`short` và xử lý bit

Các phương thức `compareUnsigned`, `divideUnsigned` và `remainderUnsigned` trực tiếp được cung cấp bởi `Integer` và `Long`. Với `byte` và `short`, nên chuyển sang giá trị dương theo miền unsigned trước khi so sánh/chia:

```java
byte raw = (byte) 0xFF;
int u8 = Byte.toUnsignedInt(raw); // 255.

short raw16 = (short) 0xFFFF;
int u16 = Short.toUnsignedInt(raw16); // 65535.

System.out.println(u8 / 10);   // 25
System.out.println(u8 % 10);   // 5
System.out.println(u16 > u8);  // true
```

`Byte.toUnsignedInt` tương đương với `raw & 0xFF`; `Short.toUnsignedInt` tương đương với `raw16 & 0xFFFF`. Sau khi chuyển sang `int` dương, các phép so sánh và chia có dấu thông thường có cùng kết quả với unsigned **vì mọi toán hạng đang ở trong miền dương đủ rộng**.

Khi dữ liệu nhị phân được ghép thành `int` hoặc `long`, cần xác định cách sắp xếp byte (*endianness*) và cách diễn giải trường từ giao thức. Một trường 32 bit có bit cao nhất bằng 1 sẽ trông âm trong Java, dù giao thức quy định đó là số unsigned lớn; khi đó ba API trên giữ đúng ngữ nghĩa cần dùng.

## 10. Ví dụ Java 17+ hoàn chỉnh

Tạo tệp **`UnsignedOperationsDemo.java`**:

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;

public class UnsignedOperationsDemo {
    public static void main(String[] args) {
        int x = -1;
        int divisor = 10;

        System.out.println("signed compare -1 < 1 = "
                + (Integer.compare(x, 1) < 0));
        System.out.println("unsigned compare -1 > 1 = "
                + (Integer.compareUnsigned(x, 1) > 0));
        System.out.println("signed quotient = " + (x / divisor));
        System.out.println("signed remainder = " + (x % divisor));
        System.out.println("unsigned quotient = "
                + Integer.divideUnsigned(x, divisor));
        System.out.println("unsigned remainder = "
                + Integer.remainderUnsigned(x, divisor));
        System.out.println("unsigned int text = "
                + Integer.toUnsignedString(x));

        List<Integer> items = new ArrayList<>(List.of(-1, 2, 0, -2));
        items.sort(Integer::compareUnsigned);
        System.out.println("unsigned sorted = " + items);

        long bigBits = -1L;
        long quotient64 = Long.divideUnsigned(bigBits, 2L);
        long remainder64 = Long.remainderUnsigned(bigBits, 2L);
        System.out.println("unsigned long quotient = "
                + Long.toUnsignedString(quotient64));
        System.out.println("unsigned long remainder = "
                + Long.toUnsignedString(remainder64));

        long allBitsQuotient = Long.divideUnsigned(bigBits, 1L);
        System.out.println("quotient signed view = " + allBitsQuotient);
        System.out.println("quotient unsigned view = "
                + Long.toUnsignedString(allBitsQuotient));

        BigInteger fullUnsignedLong =
                new BigInteger(Long.toUnsignedString(bigBits));
        System.out.println("BigInteger view = " + fullUnsignedLong);

        int parsed = Integer.parseUnsignedInt("4294967295");
        System.out.println("parsed unsigned int bits = " + parsed);

        try {
            Integer.divideUnsigned(123, 0);
        } catch (ArithmeticException ex) {
            System.out.println("division by zero detected");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac UnsignedOperationsDemo.java
java UnsignedOperationsDemo
```

Kết quả:

```text
signed compare -1 < 1 = true
unsigned compare -1 > 1 = true
signed quotient = 0
signed remainder = -1
unsigned quotient = 429496729
unsigned remainder = 5
unsigned int text = 4294967295
unsigned sorted = [0, 2, -2, -1]
unsigned long quotient = 9223372036854775807
unsigned long remainder = 1
quotient signed view = -1
quotient unsigned view = 18446744073709551615
BigInteger view = 18446744073709551615
parsed unsigned int bits = -1
division by zero detected
```

Bài toán trong ví dụ dùng đúng một bộ bit nhưng so sánh, chia và in theo hai cách hiểu khác nhau. Chú ý `items` sau sort vẫn hiển thị các giá trị có dấu; điều quan trọng là comparator đã xếp chúng theo **thứ tự không dấu**.

## 11. Lỗi thường gặp

1. **Dùng `x < y` để so sánh trường giao thức unsigned.** Nếu bit dấu khác nhau, thứ tự có dấu có thể trái ngược unsigned. Dùng `compareUnsigned`.
2. **Dùng `x / y` hoặc `x % y` cho hai mẫu bit unsigned.** Phép chia/lấy dư mặc định diễn giải toán hạng theo signed. Dùng `divideUnsigned`/`remainderUnsigned` khi quy tắc dữ liệu là unsigned.
3. **Nghĩ kết quả `divideUnsigned` luôn hiển thị không âm.** Kiểu trả về vẫn là `int` hoặc `long`. Với kết quả vượt miền signed dương, hãy dùng `toUnsignedString` hoặc chuyển sang kiểu đủ rộng thích hợp.
4. **Đổi `int` âm sang `long` bằng gán trực tiếp và tưởng là unsigned.** Chuyển đổi mở rộng thông thường giữ dấu. Dùng `Integer.toUnsignedLong` hoặc `x & 0xFFFF_FFFFL`.
5. **Cho rằng `Long.toUnsignedString(x)` sửa đổi giá trị `x`.** Hàm chỉ tạo cách biểu diễn chuỗi của cùng một mẫu 64 bit.
6. **Gọi `Math.abs(x)` để xử lý số nguyên unsigned.** Trị tuyệt đối không chuyển cách diễn giải bit, và với `MIN_VALUE` còn có bẫy tràn.
7. **Quên kiểm tra mẫu số 0.** Cả phép chia/lấy dư unsigned đều ném `ArithmeticException` khi mẫu số có bit bằng 0.
8. **Đánh đồng `Math.floorDiv`/`Math.floorMod` với phép toán unsigned.** Các hàm `floorDiv`/`floorMod` dùng quy tắc làm tròn/dấu trên toán hạng có dấu, không phải unsigned 32/64 bit.
9. **Đọc `long` unsigned tối đa bằng `Long.parseLong`.** Giá trị `2^64-1` vượt `Long.MAX_VALUE`; dùng `Long.parseUnsignedLong` rồi hiển thị bằng `Long.toUnsignedString`.
10. **Nhầm giữa “bit pattern” và “số nguyên toán học”.** API unsigned định nghĩa cách xử lý mẫu 32/64 bit; khi cần lưu giá trị dương từ 0 đến `2^64-1` như số toán học, chuyển sang `BigInteger` thích hợp.

## 12. Chọn API nào trong thực tế?

| Nhu cầu | Cách dùng |
| --- | --- |
| So sánh thứ tự hai trường unsigned 32 bit | `Integer.compareUnsigned(a, b)` |
| So sánh thứ tự hai trường unsigned 64 bit | `Long.compareUnsigned(a, b)` |
| Chia unsigned 32 bit | `Integer.divideUnsigned(a, b)` |
| Lấy dư unsigned 32 bit | `Integer.remainderUnsigned(a, b)` |
| Chia/lấy dư unsigned 64 bit | `Long.divideUnsigned(a, b)`, `Long.remainderUnsigned(a, b)` |
| In đúng số unsigned | `Integer.toUnsignedString(x)`, `Long.toUnsignedString(x)` |
| Đọc số unsigned trong chuỗi | `Integer.parseUnsignedInt(s)`, `Long.parseUnsignedLong(s)` |
| Mở rộng unsigned 32 bit thành số dương | `Integer.toUnsignedLong(x)` |
| Biểu diễn unsigned 64 bit như số dương tùy ý | `new BigInteger(Long.toUnsignedString(x))` |

**Ghi nhớ:** Java vẫn lưu `int`/`long` như các kiểu số nguyên có dấu, nhưng `compareUnsigned`, `divideUnsigned` và `remainderUnsigned` thực hiện thao tác theo **cách diễn giải không dấu của cùng mẫu bit**. Phân biệt phép toán với cách hiển thị kết quả, xử lý mẫu số 0 và dùng API chuyển đổi/chuỗi unsigned khi cần giao tiếp với bên ngoài.

**Tài liệu tham khảo:** [Java SE 21 Integer API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html), [Java SE 21 Long API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html), [Java Language Specification §4.2.1 — Integral Types and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.1).

# compareUnsigned, divideUnsigned và remainderUnsigned trong Java

## 1. Mục tiêu: diễn giải đúng các bit số nguyên theo nghĩa không dấu

Java có các kiểu nguyên thủy `byte`, `short`, `int` và `long` **có dấu**. Đôi khi bạn đọc 32 bit hoặc 64 bit từ một gói mạng, file nhị phân, mã băm, giá trị phiên bản hay bộ đếm do hệ thống khác cung cấp, mà đặc tả của dữ liệu lại coi dãy bit ấy là **số nguyên không dấu (unsigned integer)**.

Một dãy bit có thể mang hai ý nghĩa:

- Với `int`, 32 bit `0xFFFFFFFF` được in theo signed decimal là `-1`, nhưng unsigned decimal là **4.294.967.295**.
- Với `long`, 64 bit `0xFFFFFFFFFFFFFFFF` được in theo signed decimal là `-1`, nhưng unsigned decimal là **18.446.744.073.709.551.615**.
- Với một `int` có bit cao nhất bằng 1, phép toán `<`, `/`, `%` mặc định dùng **signed semantics**, không phải unsigned semantics của đặc tả dữ liệu bên ngoài.

Kể từ **Java 8**, hai lớp `java.lang.Integer` và `java.lang.Long` cung cấp ba phương thức tĩnh trọng tâm:

```java
Integer.compareUnsigned(int x, int y);
Integer.divideUnsigned(int dividend, int divisor);
Integer.remainderUnsigned(int dividend, int divisor);

Long.compareUnsigned(long x, long y);
Long.divideUnsigned(long dividend, long divisor);
Long.remainderUnsigned(long dividend, long divisor);
```

Cả ba nhóm API này vẫn có trong Java SE hiện đại. Chúng **không tạo kiểu primitive unsigned mới**. Thay vào đó, chúng nhận những giá trị `int` hoặc `long` có sẵn và **diễn giải cùng các bit theo nghĩa không dấu** trong đúng phép toán.

Bài này thuộc chủ đề cha **“Số học”** và đề mục trực tiếp **“compareUnsigned, divideUnsigned, remainderUnsigned”** của module Java 8. Mục tiêu là giải thích cách dùng đúng cả `Integer` lẫn `Long`, kết quả có thể mang dấu âm khi in bằng phương thức thông thường, các lỗi dễ gặp và cách kiểm thử. Các ví dụ dùng API hiện còn áp dụng; chương trình hoàn chỉnh có thể biên dịch với **JDK 17+**.

### Bạn sẽ học được gì?

1. Phân biệt **bit pattern**, **signed value** và **unsigned interpretation**.
2. Hiểu miền giá trị unsigned 32-bit, unsigned 64-bit và vai trò bit dấu.
3. Dùng `Integer.compareUnsigned` và `Long.compareUnsigned` để so sánh đúng khi đầu vào có bit cao nhất bằng 1.
4. Dùng `divideUnsigned`, `remainderUnsigned` thay cho `/`, `%` khi đặc tả nói unsigned.
5. Hiểu thương/số dư trả về **vẫn là `int` hoặc `long`**, có thể in ra số âm nếu lớn hơn giới hạn signed.
6. Hiển thị/parse unsigned decimal bằng `toUnsignedString` và `parseUnsignedInt/Long`.
7. Biết khi nào `Integer.toUnsignedLong` đủ, khi nào cần `BigInteger`.
8. Không nhầm `>>>` với giải pháp cho mọi bài toán chia unsigned.
9. Dùng unsigned remainder trong phép chia bucket có kiểm tra divisor và hiểu giới hạn phân phối.
10. Kiểm thử cùng kết quả bằng `BigInteger` để tránh kỳ vọng sai do signed display.
11. Xử lý chia cho 0, input vượt miền và mixed-width conversion.
12. Đánh giá các rủi ro khi truyền số unsigned qua JSON, database hoặc API khác.

## 2. Java lưu bit, còn “có dấu/không dấu” là cách diễn giải

Về mặt bit, một `int` có **32 bit**, một `long` có **64 bit**. Khi coi chúng là số signed, Java diễn giải theo **two's complement**: bit cao nhất góp phần tạo ra giá trị âm nếu nó được đặt.

| Kiểu / cách diễn giải | Dãy bit | Miền giá trị theo số học |
| --- | --- | --- |
| `int` signed | 32 | -2^31 đến 2^31 - 1 |
| `int` unsigned | Cùng 32 bit | 0 đến 2^32 - 1 |
| `long` signed | 64 | -2^63 đến 2^63 - 1 |
| `long` unsigned | Cùng 64 bit | 0 đến 2^64 - 1 |

Không có `uint` hay `ulong` primitive riêng trong Java. Trong bảng, “unsigned `int`” và “unsigned `long`” có nghĩa là **diễn giải dãy bit** của một `int/long` theo miền không dấu, chứ không phải khai báo kiểu mới.

### 2.1. Ví dụ -1 chính là dãy toàn bit 1

```java
int bits32 = -1;
long bits64 = -1L;

System.out.println(bits32);                       // -1
System.out.println(Integer.toUnsignedString(bits32)); // 4294967295

System.out.println(bits64);                       // -1
System.out.println(Long.toUnsignedString(bits64));    // 18446744073709551615
```

**Không có bit nào thay đổi.** Hai phương thức `toUnsignedString` chỉ định dạng lại cùng bit pattern theo một cách diễn giải khác.

### 2.2. Bit dấu không phải bit “dữ liệu thừa”

Nếu đặc tả gói tin ghi rằng 32 bit là một unsigned sequence number, bit cao nhất **là một phần của giá trị**. Khi nó bằng 1, Java có thể nhìn `int` đó như số âm, nhưng điều này **không có nghĩa dữ liệu bị hỏng**.

Ví dụ:

```java
int minAsSigned = Integer.MIN_VALUE;  // -2147483648
System.out.println(Integer.toUnsignedString(minAsSigned));
// 2147483648.
```

Giá trị bit `0x80000000` là âm theo signed, nhưng là 2^31 theo unsigned. Tương tự, `Long.MIN_VALUE` biểu diễn unsigned **9.223.372.036.854.775.808**, tức 2^63.

### 2.3. Quy ước ký hiệu U32 và U64

Để tránh nhầm các phép tính, ký hiệu:

- `U32(x)`: xem 32 bit của `int x` như số từ 0 tới 2^32 - 1.
- `U64(x)`: xem 64 bit của `long x` như số từ 0 tới 2^64 - 1.

Ví dụ:

```text
x (int) = -1
U32(x)  = 4_294_967_295

y (long) = -1L
U64(y)   = 18_446_744_073_709_551_615
```

Về mặt toán học, đối với giá trị signed âm, `U32(x) = x + 2^32` và `U64(y) = y + 2^64`. Đây là **cách hiểu toán học**, không phải khuyến nghị viết `2^32` trong Java (toán tử `^` trong Java là XOR, **không** phải lũy thừa).

## 3. Ba phương thức cốt lõi: cùng chữ ký nhưng khác phép toán

| Phương thức | Đầu vào | Giá trị trả về | Ý nghĩa |
| --- | --- | --- | --- |
| `Integer.compareUnsigned(x,y)` | Hai `int` | `int` âm/0/dương | So sánh thứ tự unsigned 32 bit |
| `Integer.divideUnsigned(a,b)` | Hai `int` | `int` | Thương khi chia hai số unsigned 32 bit |
| `Integer.remainderUnsigned(a,b)` | Hai `int` | `int` | Số dư khi chia hai số unsigned 32 bit |
| `Long.compareUnsigned(x,y)` | Hai `long` | `int` âm/0/dương | So sánh thứ tự unsigned 64 bit |
| `Long.divideUnsigned(a,b)` | Hai `long` | `long` | Thương khi chia hai số unsigned 64 bit |
| `Long.remainderUnsigned(a,b)` | Hai `long` | `long` | Số dư khi chia hai số unsigned 64 bit |

**Điểm dễ nhầm:** `Long.compareUnsigned(...)` trả **`int`**, không phải `long`, vì so sánh chỉ cần biểu thị quan hệ nhỏ hơn/bằng/lớn hơn. Ngược lại `Long.divideUnsigned` và `Long.remainderUnsigned` trả `long` để chứa 64 bit kết quả.

**Không phải hai phép `compareUnsigned` cùng dùng một thứ tự signed.** Cùng bit pattern âm theo signed được xếp **ở phía trên** những giá trị có bit cao nhất bằng 0 trong unsigned order.

## 4. Integer.compareUnsigned: so sánh theo 32 bit không dấu

Chữ ký từ Java 8:

```java
public static int compareUnsigned(int x, int y)
```

Hợp đồng trả:

- Một `int` **âm** khi `U32(x) < U32(y)`.
- `0` khi hai dãy bit bằng nhau.
- Một `int` **dương** khi `U32(x) > U32(y)`.

### 4.1. Ví dụ signed khác unsigned

```java
int a = -1;
int b = 1;

System.out.println(Integer.compare(a, b));         // -1.
System.out.println(Integer.compareUnsigned(a, b)); // 1.
```

Với signed, `-1 < 1`. Nhưng theo unsigned, `4_294_967_295 > 1`. Do đó cả hai phép so sánh đều đúng **theo những ý nghĩa khác nhau**.

Một sai lầm là thấy `a` âm rồi kết luận nó “nhỏ hơn” trong mọi giao thức. Nếu tài liệu giao thức nói trường đó là `uint32`, phải dùng đúng unsigned order.

### 4.2. Ví dụ Integer.MIN_VALUE so với Integer.MAX_VALUE

```java
int highBitSet = Integer.MIN_VALUE; // U32 = 2147483648.
int highBitClear = Integer.MAX_VALUE; // U32 = 2147483647.

boolean greaterAsUnsigned =
        Integer.compareUnsigned(highBitSet, highBitClear) > 0;
// true.
```

Đây là ranh giới giữa hai nửa của không gian 32 bit. Signed order đặt `Integer.MIN_VALUE` thấp nhất; unsigned order đặt nó **ngay sau `Integer.MAX_VALUE`**.

### 4.3. Chỉ kiểm tra dấu của kết quả

Không nên xây business logic phụ thuộc `compareUnsigned(x,y) == 1` hoặc `== -1`. Javadoc cam kết **âm/0/dương**, không yêu cầu người dùng suy luận một độ lớn kết quả cụ thể. Dùng:

```java
if (Integer.compareUnsigned(x, y) < 0) {
    // x đứng trước y theo unsigned order.
}
```

Đoạn này là snippet trong method với `x/y` đã khai báo.

### 4.4. Phép so sánh cũng có dạng tương đương theo bit

Đối với những `int` cụ thể, bạn có thể hiểu unsigned comparison bằng cách đảo bit cao nhất của cả hai rồi dùng signed comparison:

```java
int unsignedOrdering =
        Integer.compare(x ^ Integer.MIN_VALUE,
                        y ^ Integer.MIN_VALUE);
```

Theo two's-complement ordering, kết quả quan hệ có cùng dấu với `Integer.compareUnsigned(x,y)`. Nhưng trong code production, ưu tiên **`compareUnsigned`** vì rõ ý nghĩa và tránh lỗi triển khai tự viết.

## 5. Long.compareUnsigned: so sánh theo 64 bit không dấu

Chữ ký:

```java
public static int compareUnsigned(long x, long y)
```

Ví dụ:

```java
long x = -1L; // U64 = 18446744073709551615.
long y = 1L;

System.out.println(Long.compare(x, y));          // -1.
System.out.println(Long.compareUnsigned(x, y));  // 1.
```

Điểm quan trọng: số `18_446_744_073_709_551_615` **lớn hơn `Long.MAX_VALUE`**. Java `long` không thể giữ nó dưới dạng signed nonnegative value; vì vậy bạn vẫn giữ nguyên 64 bit trong một `long` và so sánh bằng `Long.compareUnsigned`.

### 5.1. Long.MIN_VALUE là 2^63 theo unsigned

```java
long highBitSet = Long.MIN_VALUE;
long highBitClear = Long.MAX_VALUE;

boolean larger =
        Long.compareUnsigned(highBitSet, highBitClear) > 0;
// true.
```

Đây là một ranh giới hữu ích để kiểm thử: nếu một hàm so sánh unsigned trả kết quả ngược, nó đã có bug ở trường hợp bit dấu.

### 5.2. Sorting danh sách unsigned long

```java
List<Long> values = new ArrayList<>(
        List.of(-1L, 0L, Long.MIN_VALUE, Long.MAX_VALUE));

values.sort(Long::compareUnsigned);
```

Sau khi sort, các phần tử theo unsigned tăng dần: 0; Long.MAX_VALUE; Long.MIN_VALUE; -1L (khi in signed phần tử thứ ba và thứ tư là âm, nhưng thứ tự bit theo unsigned là đúng).

**Không dùng `Long::compare` hoặc default `Long.compareTo`** khi muốn thứ tự của một trường `uint64`. Java Collection comparator tự nhiên đối với `Long` là signed.

## 6. Integer.divideUnsigned: chia 32 bit theo unsigned

Chữ ký:

```java
public static int divideUnsigned(int dividend, int divisor)
```

Nó trả **thương** của `U32(dividend) / U32(divisor)` dưới dạng **32 bit `int`**.

Ví dụ:

```java
int x = -1;
int divisor = 10;

int signedQuotient = x / divisor;
int unsignedQuotient = Integer.divideUnsigned(x, divisor);

System.out.println(signedQuotient); // 0.
System.out.println(Integer.toUnsignedString(unsignedQuotient));
// 429496729.
```

Giải thích:

```text
Signed:    -1 / 10 = 0           (Java chia số nguyên, cắt về 0).
Unsigned:  4294967295 / 10 = 429496729, dư 5.
```

Cùng hai bit patterns nhưng khác cách diễn giải số học. Đừng thay `divideUnsigned` bằng `/` khi dữ liệu là unsigned và có thể đặt bit cao nhất.

### 6.1. Thương có thể được lưu thành int âm

Đặc biệt:

```java
int q = Integer.divideUnsigned(-1, 1);

System.out.println(q);                           // -1.
System.out.println(Integer.toUnsignedString(q)); // 4294967295.
```

Thương toán học là 4.294.967.295; nhưng phương thức trả **`int`**, không phải `long`. Nó trả dãy bit `0xFFFFFFFF`, được `System.out.println(int)` diễn giải signed thành `-1`.

Điều này **không có nghĩa phép chia sai hoặc có overflow ngoài contract**. Bạn phải tiếp tục dùng unsigned semantics khi xử lý/hiển thị kết quả.

### 6.2. Divisor âm theo signed vẫn có thể hợp lệ

```java
int dividend = -1; // U32 = 4294967295.
int divisor = -2;  // U32 = 4294967294.

int quotient = Integer.divideUnsigned(dividend, divisor);
System.out.println(quotient); // 1.
```

Dù `divisor < 0` theo signed, nó **không âm theo unsigned**. Nó là một số lớn và khác 0, hoàn toàn có thể dùng làm divisor.

Không viết rule sai `if (divisor <= 0) throw ...` cho dữ liệu unsigned, vì rule ấy loại bỏ cả một nửa miền hợp lệ. Nếu business yêu cầu divisor nằm trong khoảng nhỏ, kiểm tra theo **unsigned bounds** đã quy định.

### 6.3. Divisor bằng 0

Như phép chia nguyên thông thường, `Integer.divideUnsigned(a, 0)` ném `ArithmeticException`. Không phải trả 0, không phải saturate tới MAX và không phải lấy số dư tự động.

```java
try {
    int q = Integer.divideUnsigned(7, 0);
} catch (ArithmeticException error) {
    // Dữ liệu hoặc điều kiện chia không hợp lệ.
}
```

Trong production, nếu divisor đến từ request hoặc cấu hình, validate `divisor != 0` và nêu lỗi có ngữ cảnh nghiệp vụ. Không cần tìm một “giá trị unsigned đặc biệt” thay cho 0.

## 7. Integer.remainderUnsigned: số dư 32 bit theo unsigned

Chữ ký:

```java
public static int remainderUnsigned(int dividend, int divisor)
```

Nó trả số dư theo phép chia không dấu. Với divisor unsigned khác 0:

```text
U32(dividend) = U32(divisor) * U32(quotient) + U32(remainder)
0 <= U32(remainder) < U32(divisor)
```

Đây là **quan hệ số học unsigned**, không phải so sánh signed Java thông thường.

Ví dụ:

```java
int signedRemainder = -1 % 10; // -1.
int unsignedRemainder = Integer.remainderUnsigned(-1, 10);

System.out.println(signedRemainder);                    // -1.
System.out.println(Integer.toUnsignedString(unsignedRemainder)); // 5.
```

Vì `4_294_967_295 = 10 * 429_496_729 + 5`, số dư unsigned là 5. Toán tử `%` trên `int` lại dùng signed operands và giữ dấu liên quan đến dividend.

### 7.1. Kết quả dư có thể là int âm khi in signed

Nếu unsigned divisor lớn, số dư hợp lệ theo unsigned có thể mang bit dấu:

```java
int dividend = -1;                  // U32 = 4294967295.
int divisor = Integer.MIN_VALUE;    // U32 = 2147483648.

int remainder = Integer.remainderUnsigned(dividend, divisor);
// U32(remainder) = 2147483647, trường hợp này vẫn dương.
```

Một số dư bất kỳ phải **nhỏ hơn divisor theo unsigned**, nhưng divisor có thể lớn hơn `Integer.MAX_VALUE`, nên về nguyên tắc remainder có thể rơi vào nửa signed-âm tùy dữ liệu. Đừng kiểm tra `remainder >= 0` để xác minh độ hợp lệ; dùng `Integer.compareUnsigned(remainder, divisor) < 0`.

### 7.2. Đừng nhầm với Math.floorMod

`Math.floorMod(int,int)` giải quyết mô đun dựa trên giá trị **signed** và quy tắc làm tròn xuống, không phải diễn giải unsigned bit pattern.

Ví dụ với 32-bit high bit:

```java
int x = Integer.MIN_VALUE;
System.out.println(x % 10);                         // -8.
System.out.println(Math.floorMod(x, 10));            // 2.
System.out.println(Integer.remainderUnsigned(x, 10)); // 8.
```

Ba kết quả là khác nhau:

- `x % 10` là remainder có signed dividend âm, ra -8.
- `floorMod` cho 2 vì diễn giải số signed -2.147.483.648.
- `remainderUnsigned` cho 8 vì diễn giải cùng bit pattern thành unsigned 2.147.483.648.

**Không thay thế một API bằng API khác chỉ vì mục tiêu “lấy phần dư không âm”.** Chọn theo **ý nghĩa dữ liệu**.

## 8. Long.divideUnsigned: chia theo unsigned 64 bit

Chữ ký:

```java
public static long divideUnsigned(long dividend, long divisor)
```

Đặc biệt hữu ích khi gặp unsigned 64-bit values không biểu diễn được bằng signed positive `long`.

Ví dụ:

```java
long bits = -1L; // 2^64 - 1 theo unsigned.

long quotient = Long.divideUnsigned(bits, 10L);
long remainder = Long.remainderUnsigned(bits, 10L);

System.out.println(Long.toUnsignedString(quotient));
// 1844674407370955161.
System.out.println(Long.toUnsignedString(remainder));
// 5.
```

Quan hệ:

```text
18446744073709551615 = 10 * 1844674407370955161 + 5
```

Nếu dùng `bits / 10L` trực tiếp, Java hiểu `bits == -1L` nên quotient signed là 0 — hoàn toàn khác.

### 8.1. Thương Long.divideUnsigned vẫn có thể in âm

```java
long q = Long.divideUnsigned(-1L, 1L);

System.out.println(q);                       // -1.
System.out.println(Long.toUnsignedString(q)); // 18446744073709551615.
```

Hãy nhìn vào **bit pattern của kết quả**, không chỉ định dạng signed decimal. Khi tiếp tục so sánh hai quotient unsigned, dùng `Long.compareUnsigned`.

### 8.2. Long.MIN_VALUE và divisor 3

```java
long value = Long.MIN_VALUE;

System.out.println(Long.toUnsignedString(value));
// 9223372036854775808.

System.out.println(Long.toUnsignedString(
        Long.divideUnsigned(value, 3L)));
// 3074457345618258602.

System.out.println(Long.toUnsignedString(
        Long.remainderUnsigned(value, 3L)));
// 2.
```

Đây là test tốt vì signed `Long.MIN_VALUE` rất âm, nhưng unsigned nó nằm đúng ở 2^63.

### 8.3. Divisor mang bit dấu hợp lệ

```java
long numerator = -1L;
long divisor = Long.MIN_VALUE;

long quotient = Long.divideUnsigned(numerator, divisor);
// 1.

long remainder = Long.remainderUnsigned(numerator, divisor);
// Long.MAX_VALUE, tức unsigned 9223372036854775807.
```

Divisor signed-âm không phải nguyên nhân lỗi: unsigned divisor ở đây là 2^63. Lỗi chia chỉ xuất hiện nếu **bit pattern divisor bằng 0**.

## 9. Long.remainderUnsigned: modulo unsigned 64 bit

Chữ ký:

```java
public static long remainderUnsigned(long dividend, long divisor)
```

Nó trả số dư trong **unsigned 64-bit arithmetic**. Không dùng `%` khi dividend hoặc divisor có thể đặt sign bit và giao thức muốn unsigned semantics.

```java
long raw = -1L;

long signedRemainder = raw % 10L; // -1.
long unsignedRemainder =
        Long.remainderUnsigned(raw, 10L); // 5.
```

Nếu một giá trị `long` đại diện unsigned ID/hash trong protocol, việc lấy bucket bằng `Long.remainderUnsigned(hash, bucketCount)` có thể phù hợp.

### 9.1. Remainder và quotient luôn là bit patterns kiểu long

Đừng làm:

```java
long q = Long.divideUnsigned(raw, divisor);
if (q < 0) {
    throw new IllegalStateException("Quotient overflow");
}
```

Lỗi tư duy ở đây: `q < 0` theo signed không có nghĩa quotient **unsigned** vô hiệu. Một thương lớn hơn `Long.MAX_VALUE` được trả thành một `long` có bit cao nhất đặt. Hãy dùng `Long.toUnsignedString(q)` hoặc `Long.compareUnsigned` để đánh giá.

### 9.2. Trường hợp số dư không âm khi divisor nhỏ

Khi divisor là một số signed dương **nhỏ** (ví dụ 10 hoặc một bucket count dương), unsigned remainder luôn trong `0 .. divisor-1`, vì vậy nó cũng là một `long` không âm. Nhưng với divisor có bit cao nhất đặt, remainder có thể nằm trong miền signed-âm. Vì vậy câu “`remainderUnsigned` luôn trả số không âm khi in bằng System.out.println” là **không chính xác trong mọi trường hợp**.

## 10. Các thuộc tính toán học cần nhớ

Với độ rộng `w=32` hoặc `w=64`, khi divisor khác 0:

```text
UnsignedDividend = UnsignedDivisor * UnsignedQuotient
                 + UnsignedRemainder
0 <= UnsignedRemainder < UnsignedDivisor
```

Đây là **số học toán học không giới hạn**; để kiểm chứng trên Java khi w=64 và có số lớn, dùng `BigInteger`, không bắt buộc mọi tích đều nằm trong `long` signed.

### 10.1. Remainder khi divisor lớn hơn dividend

Nếu `Integer.compareUnsigned(a,b) < 0` và b khác 0, thì:

```java
Integer.divideUnsigned(a, b) == 0
Integer.remainderUnsigned(a, b) == a
```

Điều tương tự đúng cho `Long`. Ví dụ `U32(1) < U32(-1)`, nên `Integer.divideUnsigned(1,-1) == 0` và `remainderUnsigned(1,-1)==1`.

Không dùng signed compare `a < b` để quyết định trường hợp này, vì `b` có thể là signed âm nhưng unsigned rất lớn.

### 10.2. Cộng, trừ, nhân có cùng bit result theo hai cách hiểu modulo 2^w

Javadoc của `Integer.divideUnsigned` và `Long.divideUnsigned` giải thích rằng trong số học two's complement, ba phép toán **cộng, trừ, nhân** trên cùng bit width tạo kết quả bit-wise giống nhau dù xem operands là signed hay unsigned khi tính **modulo 2^w**. Do đó không có các API riêng `addUnsigned`, `subtractUnsigned` hoặc `multiplyUnsigned` chỉ để thực hiện các phép toán cơ bản ấy.

Ví dụ:

```java
int result = -1 + 1;
System.out.println(result); // 0.
```

Đây cũng là phép cộng unsigned `4_294_967_295 + 1` **bị tràn modulo 2^32 thành 0**. Nếu nghiệp vụ **không** cho phép wrap-around, phải dùng kiểu rộng hơn (`long` cho unsigned int) hoặc `BigInteger` (cho unsigned long) và kiểm tra giới hạn.

### 10.3. Vì sao chia và remainder cần API riêng?

Phép chia có đáp án phụ thuộc cách diễn giải số (ví dụ signed -1/10 = 0, unsigned 4294967295/10 = 429496729). Số dư cũng khác. Vì vậy Java cung cấp `divideUnsigned` và `remainderUnsigned` thay vì kỳ vọng toán tử `/`/`%` tự đoán.

### 10.4. Chia cho 0 luôn không hợp lệ

`Integer.divideUnsigned(x,0)`, `Integer.remainderUnsigned(x,0)`, `Long.divideUnsigned(x,0L)` và `Long.remainderUnsigned(x,0L)` đều ném `ArithmeticException`. Không có định nghĩa kiểu “remainder unsigned của phép chia cho 0 bằng x”.

## 11. Hiển thị đúng kết quả: toUnsignedString

Nếu bạn muốn lưu giá trị unsigned vào log, JSON, SQL/text, CSV hay HTTP response, phải định dạng đúng:

```java
int unsigned32Bits = -1;
String decimal32 = Integer.toUnsignedString(unsigned32Bits);
// "4294967295".

long unsigned64Bits = -1L;
String decimal64 = Long.toUnsignedString(unsigned64Bits);
// "18446744073709551615".
```

Không làm:

```java
String wrong32 = Integer.toString(unsigned32Bits); // "-1".
String wrong64 = Long.toString(unsigned64Bits);    // "-1".
```

Hai chuỗi sai chỉ là **sai đối với ý nghĩa unsigned**, không phải lỗi của `toString`. Phải chọn đúng format theo hợp đồng dữ liệu.

### 11.1. Định dạng theo radix

`Integer.toUnsignedString(int value, int radix)` và `Long.toUnsignedString(long value,int radix)` cho phép hiển thị hệ 2, 8, 10, 16 và các radix hợp lệ khác.

```java
int bits = -1;

System.out.println(Integer.toUnsignedString(bits, 16));
// ffffffff.

long longBits = -1L;
System.out.println(Long.toUnsignedString(longBits, 16));
// ffffffffffffffff.
```

Hex display hữu ích với bit masks, packet fields, file formats và debugging. Không nhầm biểu diễn ký tự hex với một kiểu primitive unsigned mới.

### 11.2. Không ghi literal unsigned max dưới dạng signed long literal

Mẫu này **không hợp lệ**:

```java
// long maxUnsigned = 18446744073709551615L; // Lỗi biên dịch: out of range.
```

Thay vào đó, nếu cần đúng bit pattern max unsigned 64:

```java
long maxUnsignedBits =
        Long.parseUnsignedLong("18446744073709551615");
// raw signed value là -1L.
```

Dữ liệu thực tế thường đến từ network/file hoặc parse input, không cần hardcode literal vượt miền signed.

## 12. Parse unsigned values: số thập phân lớn nhưng cùng bit

Các API từ Java 8:

```java
int raw32 = Integer.parseUnsignedInt("4294967295");
long raw64 = Long.parseUnsignedLong("18446744073709551615");

System.out.println(raw32); // -1.
System.out.println(raw64); // -1.
```

Hai giá trị đã được parse đúng theo **unsigned range**, nhưng kết quả Java vẫn là int/long với bit pattern tương ứng. Khi muốn trả lại chuỗi decimal cho người dùng, dùng `toUnsignedString`.

### 12.1. Giá trị vượt miền được từ chối

```java
Integer.parseUnsignedInt("4294967296");
// NumberFormatException: vượt 2^32 - 1.

Long.parseUnsignedLong("18446744073709551616");
// NumberFormatException: vượt 2^64 - 1.
```

Đây là **code cố ý gây lỗi**, không phải happy path. Một unsigned parser không được chấp nhận các giá trị ngoài miền, dù bạn có thể parse chuỗi ấy bằng `BigInteger`.

### 12.2. Chuỗi có dấu âm không phải unsigned decimal hợp lệ

```java
Long.parseUnsignedLong("-1"); // NumberFormatException.
```

`"-1"` **không giống** `"18446744073709551615"` ở mặt hợp đồng đầu vào: chuỗi đầu là một signed decimal âm; chuỗi sau là unsigned decimal tối đa. Dù cả hai có thể tương ứng cùng bit pattern theo một phép chuyển đổi có chủ đích, parser unsigned từ chối dấu âm.

### 12.3. Dùng parse theo radix của format

```java
int bits = Integer.parseUnsignedInt("ffffffff", 16);
long longBits = Long.parseUnsignedLong("ffffffffffffffff", 16);
```

Cả hai cho raw bit pattern -1. Nếu dữ liệu có tiền tố `0x`, đừng mặc định overload `parseUnsignedInt(...,16)` tự bỏ tiền tố: hãy parse đúng theo định dạng/protocol của ứng dụng, xử lý prefix riêng nếu có.

### 12.4. Round-trip có thể kiểm thử chính xác

Đối với raw `int` bất kỳ:

```java
int original = -1;
int parsed = Integer.parseUnsignedInt(
        Integer.toUnsignedString(original));
boolean sameBits = original == parsed; // true.
```

Tương tự `long`. Đây là một cách kiểm tra chắc chắn khi xuất dữ liệu unsigned ra text và đọc lại: **phải round-trip nguyên 32 hoặc 64 bit**, không dựa vào signed decimal được hiển thị.

## 13. Integer.toUnsignedLong: cầu nối unsigned 32 bit sang long chính xác

Java `long` signed có tối đa `Long.MAX_VALUE`, lớn hơn rất nhiều so với `2^32 - 1`. Vì vậy toàn bộ unsigned 32-bit range **biểu diễn chính xác được dưới dạng long không âm**.

API từ Java 8:

```java
int raw = -1;

long unsignedValue = Integer.toUnsignedLong(raw);
System.out.println(unsignedValue); // 4294967295.
```

Đây là lựa chọn tốt khi bạn muốn:

- Tính toán một trường `uint32` trong miền không dấu nhưng không muốn thao tác bit patterns.
- Kết hợp với arithmetic trên `long` và kiểm tra range.
- Serialize ra decimal mà vẫn chính xác trong Java.
- Lấy giá trị không âm từ 4 bytes được nạp vào `int`.

### 13.1. Cast thông thường là sai cho giá trị int âm

```java
int raw = -1;

long signExtended = (long) raw;              // -1.
long zeroExtended = Integer.toUnsignedLong(raw); // 4294967295.
```

Cast `(long)raw` là **sign extension**; nó giữ ý nghĩa signed của raw. Còn `toUnsignedLong` thực hiện **zero extension**, giữ 32 bit thấp và đặt 32 bit cao thành 0.

Tương đương trong trường hợp cần hiểu bit:

```java
long masked = raw & 0xFFFF_FFFFL;
// Cùng kết quả với Integer.toUnsignedLong(raw).
```

Ưu tiên `toUnsignedLong` vì ý nghĩa trực tiếp hơn.

### 13.2. Khi có thể tính phép chia unsigned int bằng long arithmetic?

Nếu bạn đã chuyển **cả hai operands** sang `long` không âm bằng `Integer.toUnsignedLong`, phép `/` và `%` trên `long` có cùng kết quả toán học với chia/remainder unsigned 32 bit:

```java
int rawDividend = -1;
int rawDivisor = 10;

long a = Integer.toUnsignedLong(rawDividend);
long b = Integer.toUnsignedLong(rawDivisor);

long quotient = a / b;  // 429496729.
long remainder = a % b; // 5.
```

Nhưng nếu chỉ cast dividend còn để divisor với signed semantics, bạn có thể sai. Nếu không cần kiểu rộng cho downstream, `Integer.divideUnsigned`/`remainderUnsigned` thể hiện hợp đồng rõ ràng và ít cơ hội cast sai hơn.

### 13.3. Đổi ngược từ long unsigned 32 bit về int raw

Khi caller cung cấp `long` trong miền 0..4294967295, bạn có thể kiểm tra:

```java
if (value < 0 || value > 0xFFFF_FFFFL) {
    throw new IllegalArgumentException("Outside uint32 range");
}
int bits = (int) value;
```

Đây là snippet trong method với `long value`. `(int) value` sau validation trả raw 32 bit đúng. Không bỏ kiểm tra nếu nguồn có thể chứa long âm hoặc lớn hơn miền uint32.

## 14. Unsigned long và BigInteger: khi cần một số dương thật sự

Unsigned 64-bit tối đa `18_446_744_073_709_551_615`, lớn hơn signed `Long.MAX_VALUE = 9_223_372_036_854_775_807`. Không có một primitive signed rộng hơn `long` trong Java để biểu diễn **đầy đủ** miền unsigned long dưới dạng không âm.

Khi nghiệp vụ cần số nguyên toán học không âm thực sự, dùng `java.math.BigInteger`:

```java
long raw = -1L;

BigInteger unsigned = new BigInteger(
        Long.toUnsignedString(raw));

System.out.println(unsigned);
// 18446744073709551615.
```

**Không dùng `BigInteger.valueOf(raw)`** nếu muốn unsigned semantics:

```java
BigInteger wrongForUnsigned = BigInteger.valueOf(-1L);
// -1.
```

Cả hai đều hợp lệ theo ý nghĩa riêng; phải chọn theo nguồn dữ liệu.

### 14.1. Chuyển qua byte array với signum dương

Nếu bạn có chính xác 8 bytes mạng biểu diễn một unsigned 64-bit number, có thể tạo:

```java
byte[] bytes = {
    (byte) 0xFF, (byte) 0xFF, (byte) 0xFF, (byte) 0xFF,
    (byte) 0xFF, (byte) 0xFF, (byte) 0xFF, (byte) 0xFF
};

BigInteger value = new BigInteger(1, bytes);
// 18446744073709551615.
```

Ở constructor `new BigInteger(signum, magnitude)`, `signum=1` yêu cầu số dương và `magnitude` là độ lớn dạng big-endian bytes. Nếu protocol là little-endian, phải sắp xếp bytes đúng trước khi giải mã; đừng nhầm signedness với endianness.

### 14.2. So sánh/ký tự/chia khi dùng BigInteger

Nếu cả hai unsigned longs đã được chuyển thành `BigInteger` không âm:

```java
BigInteger numerator =
        new BigInteger(Long.toUnsignedString(rawA));
BigInteger denominator =
        new BigInteger(Long.toUnsignedString(rawB));

int order = numerator.compareTo(denominator);
BigInteger[] qr = numerator.divideAndRemainder(denominator);
```

Đây là code minh họa với `long rawA/rawB` và `denominator.signum()!=0`. Kết quả tương thích về số học với `Long.compareUnsigned` và `Long.divideUnsigned/Long.remainderUnsigned` sau khi ta diễn giải raw quotients/remainders thành unsigned.

Dùng BigInteger khi **vượt khỏi miền 64-bit**, cần biểu diễn nonnegative decimal nhiều thao tác, hoặc cần arithmetic chính xác không wrap. Không dùng BigInteger chỉ để thay một `Long.compareUnsigned` đơn giản trong hot path nếu không có yêu cầu.

## 15. Byte/Short không dấu và width conversion

Mặc dù đề bài tập trung vào Integer/Long, dữ liệu binary thường có field 8 hoặc 16 bit unsigned.

### 15.1. Dùng các API chuyển đổi hiện đại

```java
byte rawByte = (byte) 0xFF;
short rawShort = (short) 0xFFFF;

int unsigned8 = Byte.toUnsignedInt(rawByte);
int unsigned16 = Short.toUnsignedInt(rawShort);

System.out.println(unsigned8);  // 255.
System.out.println(unsigned16); // 65535.
```

Các API chuyển đổi này có từ Java 8. Chúng rõ ý nghĩa hơn việc tự viết `rawByte & 0xFF` hoặc `rawShort & 0xFFFF` khi không cần làm việc với masks.

### 15.2. CompareUnsigned cho Byte/Short ở JDK mới

`Byte.compareUnsigned` và `Short.compareUnsigned` xuất hiện **từ Java 9**, không phải Java 8 gốc. Nếu cần tương thích source level Java 8, bạn có thể zero-extend sang `int` rồi dùng `Integer.compare`:

```java
int a = Byte.toUnsignedInt(rawByteA);
int b = Byte.toUnsignedInt(rawByteB);
int order = Integer.compare(a, b);
```

Đây là snippet với hai `byte` đã khai báo. Vì giá trị đã nằm trong 0..255, signed comparison trên `int` là đúng cho unsigned byte values. Phân biệt **phiên bản có API** giúp code không vô tình fail khi biên dịch `--release 8`.

### 15.3. ByteBuffer đọc int/long raw bits

Một giao thức có thể lưu 4 bytes unsigned trong network order. `ByteBuffer.getInt()` trả signed `int` có cùng bit pattern:

```java
byte[] bytes = {
    (byte) 0xFF, (byte) 0xFF, (byte) 0xFF, (byte) 0xFF
};

int raw = ByteBuffer.wrap(bytes).getInt();
// raw == -1.

long unsigned = Integer.toUnsignedLong(raw);
// 4294967295.
```

`ByteBuffer` mặc định sử dụng big-endian. Nếu giao thức đòi little-endian, phải gọi `order(ByteOrder.LITTLE_ENDIAN)`. **Endianness** điều khiển thứ tự bytes; **unsignedness** điều khiển cách diễn giải giá trị số sau khi đã ghép bytes. Đây là hai vấn đề khác nhau.

## 16. Shift và bitwise: >>> không đồng nghĩa phép chia unsigned tổng quát

Java có hai toán tử dịch phải:

- `>>`: arithmetic right shift, giữ bit dấu.
- `>>>`: logical right shift, chèn 0 vào bit cao.

Ví dụ:

```java
System.out.println(-1 >> 1);   // -1.
System.out.println(-1 >>> 1);  // 2147483647.
```

Với 32 bit `-1`, phép `>>> 1` tương ứng phép chia unsigned cho 2 và lấy phần nguyên. Đây là trường hợp đặc biệt vì divisor là lũy thừa của 2.

### 16.1. Khi divisor bằng 2^k

Trong arithmetic unsigned, chia cho 2^k tương ứng dịch phải logical k bit:

```java
int raw = -1;

int q = Integer.divideUnsigned(raw, 8);
int shifted = raw >>> 3;

boolean sameBits = q == shifted; // true.
```

Nhưng **không** thể thay chia cho 10 bằng dịch phải một số bit nào đó. Đừng tự viết bit hack nếu divisor tùy ý; sử dụng `divideUnsigned`.

### 16.2. Remainder với power-of-two divisor

Khi divisor là một lũy thừa của 2 và nhỏ hơn 2^w, unsigned remainder tương ứng giữ những bit thấp:

```java
int raw = -1;
int rem = Integer.remainderUnsigned(raw, 16);

System.out.println(rem);          // 15.
System.out.println(raw & 0x0F);   // 15.
```

Nhưng khi divisor không phải lũy thừa của 2, dùng phép AND mask như `raw & (divisor-1)` **không** nói chung tương đương remainder. Trong code production, dùng `Integer.remainderUnsigned`/`Long.remainderUnsigned` cho độ rõ, trừ khi bạn có benchmark và case đặc biệt được kiểm chứng.

### 16.3. Shift distance có quy tắc riêng

Java chỉ dùng 5 bit thấp của shift distance cho `int` và 6 bit thấp cho `long`. Nghĩa là `x >>> 32` với `int` thực chất như dịch 0 bit, **không** phải kết quả unsigned division cho 2^32. Đừng viết code nhận shift distance chưa validate rồi suy ra phép chia/nhân bằng lũy thừa vô hạn.

## 17. Unsigned sorting trong Collection và data processing

Default sort trên `Integer` và `Long` là signed order:

```java
List<Integer> ids = new ArrayList<>(
        List.of(-1, 0, 1, Integer.MIN_VALUE, Integer.MAX_VALUE));

ids.sort(Integer::compareUnsigned);
```

Khi định dạng unsigned, thứ tự là:

```text
0,1,2147483647,2147483648,4294967295
```

Các giá trị có bit cao nhất bằng 1 được đặt **sau** mọi giá trị 0..Integer.MAX_VALUE, đúng unsigned order.

### 17.1. Stream.sorted và comparator

```java
List<String> ordered =
        ids.stream()
                .sorted(Integer::compareUnsigned)
                .map(Integer::toUnsignedString)
                .toList();
```

Dùng Java 17+ vì `Stream.toList()` có từ Java 16. Với Java 8 gốc, dùng `collect(Collectors.toList())`. `Integer::compareUnsigned` có từ Java 8 nên cả hai cách chỉ khác terminal collection API.

### 17.2. Arrays.sort(int[]) mặc định theo signed order

`Arrays.sort(int[])` không tự chọn unsigned semantics. Nếu bạn sort một mảng primitive `int[]` và muốn unsigned order, cần một chiến lược riêng, ví dụ chuyển sang `Integer[]` với comparator rõ ràng, hoặc thiết kế primitive sorting/bit transform đã kiểm thử.

Không viết:

```java
int[] ids = {-1, 0, 1};
Arrays.sort(ids);
// Kết quả signed: [-1, 0, 1], không phải unsigned order.
```

Nếu dùng `Arrays.compareUnsigned` cho mảng, lưu ý API này có từ **Java 9**, và nó là **so sánh thứ tự từ điển các mảng**, không phải thuật toán tự động sắp xếp từng phần tử.

### 17.3. TreeSet và HashMap không dùng cùng nghĩa thứ tự

Một `TreeSet<Integer>` với default comparator dùng signed ordering. Nếu cần unsigned order:

```java
NavigableSet<Integer> ordered =
        new TreeSet<>(Integer::compareUnsigned);
```

Ngược lại `HashMap`/`HashSet` dùng equality/hash, không có khái niệm thứ tự signed/unsigned đối với key. `Integer.equals` so bit pattern; một raw `-1` chỉ là một key, còn cách hiển thị/so sánh thứ tự là chính sách khác.

## 18. Ứng dụng thực tế: chia bucket bằng remainderUnsigned

Khi một key đã được ánh xạ thành một `int` gồm các bit hash, bạn thường muốn bucket index thuộc `0..bucketCount-1`.

```java
static int bucketFor(int rawHash, int bucketCount) {
    if (bucketCount <= 0) {
        throw new IllegalArgumentException(
                "bucketCount must be positive");
    }
    return Integer.remainderUnsigned(rawHash, bucketCount);
}
```

Vì `bucketCount` được validate là một `int` dương, unsigned divisor cũng là cùng số. Số dư nằm trong `0..bucketCount-1` và có thể được dùng làm array index.

Ví dụ:

```java
int rawHash = Integer.MIN_VALUE;
int bucket = Integer.remainderUnsigned(rawHash, 10);
// 8.
```

So sánh:

```text
rawHash                  = -2147483648 (signed)
rawHash % 10              = -8
Math.floorMod(rawHash,10) = 2
U32(rawHash)              = 2147483648
U32(rawHash) % 10         = 8
```

**Không có “modulo đúng duy nhất”** nếu chưa xác định có đang băm một signed integer hay lấy bucket từ unsigned hash bits. Với raw hash 32 bit được coi unsigned, `remainderUnsigned` trực tiếp biểu thị ý định.

### 18.1. Đừng kỳ vọng tự đảm bảo phân phối đều

Nếu giá trị hash không phân bố đều hoặc bucketCount không chia hết kích thước không gian 2^32, modulo có thể có bias. `remainderUnsigned` **chỉ tính toán đúng số dư**, không tự cải thiện chất lượng hash hoặc bảo đảm uniform distribution.

Khi các đối tượng được phân vùng giữa nhiều máy, cần thêm quy tắc stability của hash function, thay đổi số bucket, consistent hashing và protocol chung; unsigned remainder chỉ là một bước.

### 18.2. Cẩn thận với Math.abs(hash)

`Math.abs(Integer.MIN_VALUE)` vẫn là `Integer.MIN_VALUE` vì miền signed `int` không chứa 2^31 dưới dạng số dương. Do đó dùng `Math.abs(hash) % bucketCount` có thể còn âm, gây index lỗi.

Đối với unsigned bits, `Integer.remainderUnsigned(hash,bucketCount)` không có bẫy này. Nếu yêu cầu signed modulo không âm, `Math.floorMod(hash,bucketCount)` có nghĩa khác, không được đánh tráo.

### 18.3. BucketCount hợp lệ phải được validate

`bucketCount==0` làm unsigned remainder ném `ArithmeticException`. `bucketCount < 0` tuy là unsigned divisor rất lớn nhưng không có ý nghĩa là “số bucket âm” đối với Java arrays. Validate `bucketCount > 0` trước khi tính index.

## 19. Ranh giới giao thức: unsigned không phải kiểu dữ liệu mới

Một field 32 bit trong file có thể được document là uint32, nhưng trong code Java bạn vẫn khai báo `int`. Việc **đúng về nghĩa** phụ thuộc các điểm tiếp nối:

1. **Đọc bytes:** diễn giải đúng byte order và bit width.
2. **So sánh:** `Integer.compareUnsigned` hoặc `Long.compareUnsigned`.
3. **Chia và modulo:** `divideUnsigned`, `remainderUnsigned` tương ứng.
4. **Hiển thị:** `toUnsignedString` hoặc chuyển rộng đúng cách.
5. **Parse input:** `parseUnsignedInt/Long`, kiểm tra range.
6. **Lưu trữ/transport:** chọn kiểu hoặc format hỗ trợ đủ miền.
7. **Viết tests:** có sign-bit-set cases và divisor boundary.

### 19.1. Đọc long unsigned từ 8 bytes

Ví dụ:

```java
byte[] payload = {
        (byte) 0xFF, (byte) 0xFF, (byte) 0xFF, (byte) 0xFF,
        (byte) 0xFF, (byte) 0xFF, (byte) 0xFF, (byte) 0xFF
};
long raw = ByteBuffer.wrap(payload).getLong(); // -1L.
String unsignedDecimal = Long.toUnsignedString(raw);
// "18446744073709551615".
```

Nếu một API JSON khác nhận số dưới dạng JavaScript `Number`, những nguyên lớn hơn 2^53-1 không được đảm bảo chính xác nguyên dạng. Với unsigned 64-bit, nên cân nhắc **serialize decimal dưới dạng chuỗi** và parse với logic hỗ trợ 64-bit unsigned hoặc BigInt/BigInteger ở phía nhận.

### 19.2. Database signed BIGINT không chứa toàn miền unsigned 64

Một cột SQL `BIGINT` signed thông thường có miền gần tương ứng signed long; không thể trực tiếp lưu mọi uint64 như số dương. Có thể dùng decimal/numeric type đủ precision hoặc lưu bit pattern/chuỗi với contract rõ.

Không ghi `Long.toUnsignedString(raw)` vào signed BIGINT rồi giả định cơ sở dữ liệu tự mở rộng miền. Cũng không lấy raw `-1` lưu vào cột signed rồi mong báo cáo SQL biết nó đại diện 2^64-1 nếu chưa có quy ước.

### 19.3. ID/sequence number wrapping cần protocol riêng

Một sequence number unsigned thường tăng rồi **wrap từ MAX về 0**. `compareUnsigned` cung cấp **unsigned total order**, không tự giải quyết **cửa sổ wrap-around** cho giao thức mạng.

Ví dụ, nếu counter vừa wrap: unsigned MAX → 0, việc hỏi “0 có mới hơn MAX không?” phụ thuộc quy tắc sequence-window của giao thức, **không thể chỉ dùng** `compareUnsigned(0, -1) > 0` (nó false vì 0 nhỏ hơn MAX theo unsigned). Nếu protocol định nghĩa thứ tự tuần hoàn, phải xây logic modular ordering riêng và nêu giới hạn khoảng cách rõ.

### 19.4. Unsigned không có nghĩa thông tin được mã hóa hoặc bí mật

Unsigned comparison/division là số học bit pattern, không phải biện pháp bảo mật. Không dùng nó để tự tạo hash có khả năng chống tấn công, không tuyên bố các phương thức unsigned chạy constant-time hoặc mã hóa thông tin. Với security-sensitive algorithms, theo API/provider và kiểm toán chuyên biệt.

## 20. Các lỗi hay gặp và cách sửa

### Lỗi 1. Tưởng int và long đã có primitive unsigned riêng

**Sai:** `uint`/`ulong` không phải primitive Java. **Đúng:** giữ bits trong `int/long`, sử dụng API unsigned đúng phép toán.

### Lỗi 2. Dùng dấu của biến raw để kiểm tra dữ liệu xấu

**Sai:** thấy `raw < 0` rồi bác bỏ một uint32 từ network. **Sửa:** xác định protocol unsigned, dùng `toUnsignedLong` hoặc format/compare tương ứng.

### Lỗi 3. Dùng `Integer.compare` thay compareUnsigned cho uint32

Một raw signed -1 được xếp trước 1 thay vì sau. **Sửa:** dùng `Integer.compareUnsigned`.

### Lỗi 4. Dùng `Long.compare` thay compareUnsigned cho uint64

Giá trị raw long âm có thể đại diện unsigned rất lớn. **Sửa:** dùng `Long.compareUnsigned`.

### Lỗi 5. Dựa vào kết quả compareUnsigned luôn bằng -1/0/1

Javadoc bảo đảm âm/0/dương. **Sửa:** kiểm tra `<0`, `==0`, `>0` thay vì suy đoán magnitude.

### Lỗi 6. Dùng `/` khi input thực sự là unsigned

`-1 / 10 = 0` không phải `U32(-1) / 10 = 429496729`. **Sửa:** `Integer.divideUnsigned` hoặc tính trên long đã zero-extend chính xác.

### Lỗi 7. Dùng `%` khi input thực sự là unsigned

`-1 % 10 = -1`, unsigned remainder là 5. **Sửa:** `Integer.remainderUnsigned`.

### Lỗi 8. Dùng `Math.floorMod` vì tưởng đó là unsigned modulo

Floor mod của signed negative không nhất thiết bằng modulo của unsigned bits. **Sửa:** dùng đúng remainderUnsigned theo đặc tả giao thức.

### Lỗi 9. Thấy kết quả unsigned quotient âm rồi coi là lỗi

Kết quả vẫn là raw int/long bits. **Sửa:** `toUnsignedString` khi in hoặc `toUnsignedLong` khi là int.

### Lỗi 10. Coi divisor signed-âm là không hợp lệ trong mọi trường hợp

Unsigned divisor với bit cao nhất bằng 1 là một số unsigned lớn. **Sửa:** chỉ check zero nếu cần chia; validation nghiệp vụ riêng cho domain.

### Lỗi 11. Quên chia cho 0

`divideUnsigned` và `remainderUnsigned` ném ArithmeticException. **Sửa:** validate divisor khi nhận dữ liệu từ caller.

### Lỗi 12. Dùng `Long.parseLong` với unsigned long decimal tối đa

Không thể parse thành signed positive long vì vượt `Long.MAX_VALUE`. **Sửa:** `Long.parseUnsignedLong` rồi xử lý raw bits.

### Lỗi 13. Dùng `Integer.parseInt` với unsigned int decimal tối đa

`"4294967295"` vượt `Integer.MAX_VALUE`. **Sửa:** `Integer.parseUnsignedInt`.

### Lỗi 14. Dùng `Integer.toString(raw)`/`Long.toString(raw)` cho unsigned decimal

Có thể in -1, không theo contract. **Sửa:** `toUnsignedString`.

### Lỗi 15. Gán `(long) rawInt` rồi tưởng đã zero extend

Cast sign-extends int âm. **Sửa:** `Integer.toUnsignedLong(rawInt)`.

### Lỗi 16. Gọi `BigInteger.valueOf(rawLong)` rồi coi nó unsigned

Giữ signed nghĩa của rawLong. **Sửa:** `new BigInteger(Long.toUnsignedString(rawLong))` hoặc constructor magnitude với signum=1.

### Lỗi 17. Ép một số unsigned 64 bit vượt MAX_VALUE thành signed long để in số dương

Không thể biểu diễn nguyên vẹn toàn miền dưới dạng signed positive long. **Sửa:** giữ raw bits + format unsigned hoặc BigInteger.

### Lỗi 18. Dùng `Math.abs(Integer.MIN_VALUE)` để tạo bucket

`Math.abs(Integer.MIN_VALUE)` vẫn âm. **Sửa:** chọn `remainderUnsigned` hoặc `floorMod` tùy ý nghĩa dữ liệu và check divisor dương.

### Lỗi 19. Nghĩ `>>>` thay được divideUnsigned với divisor bất kỳ

Logical shift chỉ tương đương unsigned division trong những trường hợp power-of-two tương ứng. **Sửa:** dùng `divideUnsigned` cho divisor chung.

### Lỗi 20. Không chú ý shift distance bị mask

`int >>> 32` không phải dịch 32 bit theo cách toán học mong đợi. **Sửa:** validate khoảng 0..31 cho int và 0..63 cho long khi dùng shift.

### Lỗi 21. Sort Integer/Long bằng natural order trong dữ liệu unsigned

`Arrays.sort` và default comparators dùng signed. **Sửa:** comparator unsigned phù hợp hoặc representation dương.

### Lỗi 22. Trộn int và long rồi so sánh sai width

Cùng bit pattern 32 bit có thể thành `long -1` qua sign extension, khác `4294967295L`. **Sửa:** chuẩn hóa width và zero-extend theo contract.

### Lỗi 23. Bỏ qua endianness khi đọc uint32/uint64 từ bytes

Byte order và signedness là hai khái niệm độc lập. **Sửa:** cấu hình `ByteOrder` đúng rồi xử lý unsigned.

### Lỗi 24. Serialize uint64 vào JavaScript Number không kiểm soát precision

Trên 2^53-1, nhiều số nguyên không được biểu diễn chính xác bằng Number. **Sửa:** protocol lưu decimal string/BigInt hoặc format chính xác có schema rõ.

### Lỗi 25. Dùng signed BIGINT cho toàn miền unsigned 64 bit

Không chứa đủ giá trị nonnegative. **Sửa:** database numeric precision đủ hoặc lưu raw bit pattern với lớp diễn giải.

### Lỗi 26. Coi compareUnsigned là thứ tự thời gian của sequence đã wrap

Unsigned total order không tự tính toán recency theo vòng modulo. **Sửa:** thuật toán window/sequence-wrap phù hợp giao thức.

### Lỗi 27. Dùng phép cộng unsigned mà không định nghĩa overflow policy

Cộng trừ nhân trong fixed width có thể wrap. **Sửa:** dùng kiểu rộng/BigInteger nếu không được wrap, và validate bounds.

### Lỗi 28. Viết comparator bằng phép trừ `x-y`

Phép trừ có thể overflow; dấu kết quả không bảo đảm quan hệ thứ tự đúng. **Sửa:** dùng `Integer.compareUnsigned`/`Long.compareUnsigned`.

### Lỗi 29. Bỏ qua remainder unsigned âm khi divisor lớn

Remainder là raw bit pattern; signed print có thể âm dù hợp lệ theo unsigned. **Sửa:** compareUnsigned và format unsigned.

### Lỗi 30. Chọn modulo nhưng không xem phân phối hash hoặc bucketCount

Remainder tính đúng toán học nhưng không tự bảo đảm uniformity hay cân bằng cluster. **Sửa:** thiết kế hash function và partitioning policy riêng.

### Lỗi 31. Dùng unsigned methods như crypto primitive

Các hàm là arithmetic helpers, không tuyên bố constant-time. **Sửa:** dùng thư viện mật mã khi yêu cầu an toàn side-channel.

### Lỗi 32. Tạo expected results bằng cùng API cần test

Nếu test gọi `divideUnsigned` để tạo expected cho chính `divideUnsigned`, lỗi có thể bị che. **Sửa:** dùng independent oracle như `BigInteger`.

## 21. Kiểm thử boundary: trường hợp nên có trong test suite

| Input | Phép toán | Kết quả đúng / ý nghĩa |
| --- | --- | --- |
| `-1, 1` | `Integer.compareUnsigned` | Dương; 4294967295 lớn hơn 1 |
| `-1L, 1L` | `Long.compareUnsigned` | Dương; 2^64-1 lớn hơn 1 |
| `Integer.MIN_VALUE, Integer.MAX_VALUE` | compareUnsigned | Dương |
| `Long.MIN_VALUE, Long.MAX_VALUE` | compareUnsigned | Dương |
| `-1, 10` | `Integer.divideUnsigned` | 429496729, trả int dương |
| `-1, 10` | `Integer.remainderUnsigned` | 5 |
| `-1, 1` | `Integer.divideUnsigned` | Raw `-1`, unsigned decimal 4294967295 |
| `-1, -2` | `Integer.divideUnsigned` | 1 |
| `-1, -2` | `Integer.remainderUnsigned` | 1 |
| `Integer.MIN_VALUE, 10` | `Integer.remainderUnsigned` | 8 |
| `-1L, 10L` | `Long.divideUnsigned` | 1844674407370955161 |
| `-1L, 10L` | `Long.remainderUnsigned` | 5 |
| `-1L, 1L` | `Long.divideUnsigned` | Raw -1L, unsigned decimal 18446744073709551615 |
| `Long.MIN_VALUE, 3L` | `Long.divideUnsigned` | 3074457345618258602 |
| `Long.MIN_VALUE, 3L` | `Long.remainderUnsigned` | 2 |
| `anyValue, 0` | Divide/remainder unsigned | ArithmeticException |
| `"4294967295"` | parseUnsignedInt | Raw -1 |
| `"18446744073709551615"` | parseUnsignedLong | Raw -1L |
| `"4294967296"` | parseUnsignedInt | NumberFormatException |
| `"-1"` | parseUnsignedLong | NumberFormatException |
| `byte 0xFF` | Byte.toUnsignedInt | 255 |
| `short 0xFFFF` | Short.toUnsignedInt | 65535 |

Khi test cần so sánh các kết quả lớn, chuyển thành **decimal unsigned** bằng `toUnsignedString` hoặc so với **BigInteger**. Đừng viết assertion signed kiểu `assert q >= 0` khi quotient unsigned có thể vượt miền signed dương.

## 22. Chương trình Java 17+ hoàn chỉnh, có kiểm chứng chéo bằng BigInteger

Tạo file **`UnsignedArithmeticDemo.java`**. Chương trình chỉ dùng Java Standard Library và bao gồm:

- Hai cách hiển thị signed/unsigned trên cùng bit pattern.
- `Integer.compareUnsigned` và `Long.compareUnsigned`.
- Chia/số dư signed so với unsigned.
- Thương lớn hơn max signed khi divisor = 1.
- Trường hợp `MIN_VALUE` và trường hợp divisor có sign bit.
- Logical shift so với arithmetic shift.
- Sort 5 giá trị `int` theo unsigned order.
- Bucket modulo từ raw negative hash.
- Chuyển đổi Byte/Short không dấu.
- Parse uint32/uint64 tối đa và chuyển sang BigInteger.
- Input bị từ chối khi vượt unsigned range, có dấu âm hoặc chia cho 0.
- Đối chiếu **42 phép chia/số dư unsigned 32-bit và 42 phép 64-bit** với BigInteger oracle; cùng lúc kiểm chứng dấu của kết quả compareUnsigned với phép so sánh BigInteger trong toàn bộ 49 cặp mỗi width.

```java
import java.math.*;
import java.util.*;
import java.util.stream.*;
import java.nio.*;

public class UnsignedArithmeticDemo {
    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    // Chuyển bit pattern long thành BigInteger dương theo unsigned 64.
    static BigInteger u64(long value) {
        return new BigInteger(Long.toUnsignedString(value));
    }

    static int sign(int value) {
        return Integer.compare(value, 0);
    }

    // Independent mathematical oracle cho unsigned 32-bit.
    static int test32() {
        int[] values = {
            0, 1, -1, Integer.MIN_VALUE, Integer.MAX_VALUE,
            -2, 2
        };
        int checks = 0;

        for (int a : values) {
            for (int b : values) {
                BigInteger ua =
                        BigInteger.valueOf(Integer.toUnsignedLong(a));
                BigInteger ub =
                        BigInteger.valueOf(Integer.toUnsignedLong(b));

                check(sign(Integer.compareUnsigned(a, b))
                        == sign(ua.compareTo(ub)), "compare32");

                if (b != 0) {
                    BigInteger[] qr = ua.divideAndRemainder(ub);
                    check(
                        Integer.toUnsignedLong(
                                Integer.divideUnsigned(a, b))
                            == qr[0].longValueExact(),
                        "divide32");
                    check(
                        Integer.toUnsignedLong(
                                Integer.remainderUnsigned(a, b))
                            == qr[1].longValueExact(),
                        "rem32");
                    checks++;
                }
            }
        }
        return checks;
    }

    // Independent mathematical oracle cho unsigned 64-bit.
    static int test64() {
        long[] values = {
            0, 1, -1, Long.MIN_VALUE, Long.MAX_VALUE, -2, 2
        };
        int checks = 0;

        for (long a : values) {
            for (long b : values) {
                BigInteger ua = u64(a);
                BigInteger ub = u64(b);

                check(sign(Long.compareUnsigned(a, b))
                        == sign(ua.compareTo(ub)), "compare64");

                if (b != 0) {
                    BigInteger[] qr = ua.divideAndRemainder(ub);
                    check(
                        u64(Long.divideUnsigned(a, b)).equals(qr[0]),
                        "divide64");
                    check(
                        u64(Long.remainderUnsigned(a, b)).equals(qr[1]),
                        "rem64");
                    checks++;
                }
            }
        }
        return checks;
    }

    public static void main(String[] args) {
        int allOnes32 = -1;
        long allOnes64 = -1L;

        System.out.println("signedInt=" + allOnes32);
        System.out.println("unsignedInt="
                + Integer.toUnsignedString(allOnes32));
        System.out.println("unsignedIntAsLong="
                + Integer.toUnsignedLong(allOnes32));

        System.out.println("signedLong=" + allOnes64);
        System.out.println("unsignedLong="
                + Long.toUnsignedString(allOnes64));

        System.out.println("signedCompare32="
                + Integer.compare(allOnes32, 1));
        System.out.println("unsignedCompare32="
                + Integer.compareUnsigned(allOnes32, 1));
        System.out.println("unsignedCompare64="
                + Long.compareUnsigned(allOnes64, 1L));

        System.out.println("intSignedQuotient=" + (allOnes32 / 10));
        System.out.println("intUnsignedQuotient="
                + Integer.toUnsignedString(
                        Integer.divideUnsigned(allOnes32, 10)));

        System.out.println("intSignedRemainder=" + (allOnes32 % 10));
        System.out.println("intUnsignedRemainder="
                + Integer.toUnsignedString(
                        Integer.remainderUnsigned(allOnes32, 10)));

        System.out.println("intUnsignedQuotientBitsWithDivisor1="
                + Integer.divideUnsigned(allOnes32, 1));
        System.out.println("intUnsignedQuotientDecimalWithDivisor1="
                + Integer.toUnsignedString(
                        Integer.divideUnsigned(allOnes32, 1)));

        System.out.println("intUnsignedMaxDivUnsignedMaxMinus1="
                + Integer.divideUnsigned(-1, -2));
        System.out.println("intUnsignedMaxRemUnsignedMaxMinus1="
                + Integer.remainderUnsigned(-1, -2));

        System.out.println("longUnsignedQuotient="
                + Long.toUnsignedString(
                        Long.divideUnsigned(allOnes64, 10L)));
        System.out.println("longUnsignedRemainder="
                + Long.toUnsignedString(
                        Long.remainderUnsigned(allOnes64, 10L)));
        System.out.println("longUnsignedQuotientBitsWithDivisor1="
                + Long.divideUnsigned(allOnes64, 1L));
        System.out.println("longUnsignedQuotientDecimalWithDivisor1="
                + Long.toUnsignedString(
                        Long.divideUnsigned(allOnes64, 1L)));

        System.out.println("intMinUnsigned="
                + Integer.toUnsignedString(Integer.MIN_VALUE));
        System.out.println("longMinUnsigned="
                + Long.toUnsignedString(Long.MIN_VALUE));
        System.out.println("intMinUnsignedDiv3="
                + Integer.toUnsignedString(
                        Integer.divideUnsigned(
                                Integer.MIN_VALUE, 3)));
        System.out.println("longMinUnsignedDiv3="
                + Long.toUnsignedString(
                        Long.divideUnsigned(
                                Long.MIN_VALUE, 3L)));
        System.out.println("longMinUnsignedRem3="
                + Long.toUnsignedString(
                        Long.remainderUnsigned(
                                Long.MIN_VALUE, 3L)));

        System.out.println("unsignedShiftVsSigned="
                + Integer.toUnsignedString(-1 >>> 1)
                + "," + (-1 >> 1));

        int[] ids = {
            -1, 0, 1, Integer.MIN_VALUE, Integer.MAX_VALUE
        };
        List<Integer> sorted = Arrays.stream(ids)
                .boxed()
                .sorted(Integer::compareUnsigned)
                .toList();
        System.out.println("sortedUnsigned="
                + sorted.stream()
                        .map(Integer::toUnsignedString)
                        .collect(Collectors.joining(",")));

        int key = Integer.MIN_VALUE;
        System.out.println("signedBucket=" + (key % 10));
        System.out.println("unsignedBucket="
                + Integer.remainderUnsigned(key, 10));

        System.out.println("unsignedByte="
                + Byte.toUnsignedInt((byte) 0xff));
        System.out.println("unsignedShort="
                + Short.toUnsignedInt((short) 0xffff));

        System.out.println("parsedIntBits="
                + Integer.parseUnsignedInt("4294967295"));
        System.out.println("parsedLongBits="
                + Long.parseUnsignedLong(
                        "18446744073709551615"));
        System.out.println("bigUnsignedLong=" + u64(allOnes64));

        boolean overflowRejected = false;
        boolean negativeRejected = false;
        boolean zeroRejected32 = false;
        boolean zeroRejected64 = false;
        try {
            Integer.parseUnsignedInt("4294967296");
        } catch (NumberFormatException error) {
            overflowRejected = true;
        }
        try {
            Long.parseUnsignedLong("-1");
        } catch (NumberFormatException error) {
            negativeRejected = true;
        }
        try {
            Integer.divideUnsigned(1, 0);
        } catch (ArithmeticException error) {
            zeroRejected32 = true;
        }
        try {
            Long.remainderUnsigned(1L, 0L);
        } catch (ArithmeticException error) {
            zeroRejected64 = true;
        }

        check(overflowRejected && negativeRejected
                && zeroRejected32 && zeroRejected64, "errors");

        System.out.println("intParseOverflowRejected="
                + overflowRejected);
        System.out.println("negativeUnsignedLongRejected="
                + negativeRejected);
        System.out.println("zeroDivisorIntRejected="
                + zeroRejected32);
        System.out.println("zeroDivisorLongRejected="
                + zeroRejected64);

        System.out.println("bigIntegerCrossChecks32=" + test32());
        System.out.println("bigIntegerCrossChecks64=" + test64());
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch/chạy:

```bash
javac UnsignedArithmeticDemo.java
java UnsignedArithmeticDemo
```

**Stdout chính xác khi chạy JDK 17+**:

```text
signedInt=-1
unsignedInt=4294967295
unsignedIntAsLong=4294967295
signedLong=-1
unsignedLong=18446744073709551615
signedCompare32=-1
unsignedCompare32=1
unsignedCompare64=1
intSignedQuotient=0
intUnsignedQuotient=429496729
intSignedRemainder=-1
intUnsignedRemainder=5
intUnsignedQuotientBitsWithDivisor1=-1
intUnsignedQuotientDecimalWithDivisor1=4294967295
intUnsignedMaxDivUnsignedMaxMinus1=1
intUnsignedMaxRemUnsignedMaxMinus1=1
longUnsignedQuotient=1844674407370955161
longUnsignedRemainder=5
longUnsignedQuotientBitsWithDivisor1=-1
longUnsignedQuotientDecimalWithDivisor1=18446744073709551615
intMinUnsigned=2147483648
longMinUnsigned=9223372036854775808
intMinUnsignedDiv3=715827882
longMinUnsignedDiv3=3074457345618258602
longMinUnsignedRem3=2
unsignedShiftVsSigned=2147483647,-1
sortedUnsigned=0,1,2147483647,2147483648,4294967295
signedBucket=-8
unsignedBucket=8
unsignedByte=255
unsignedShort=65535
parsedIntBits=-1
parsedLongBits=-1
bigUnsignedLong=18446744073709551615
intParseOverflowRejected=true
negativeUnsignedLongRejected=true
zeroDivisorIntRejected=true
zeroDivisorLongRejected=true
bigIntegerCrossChecks32=42
bigIntegerCrossChecks64=42
ALL CHECKS PASSED
```

### 22.1. Diễn giải nhóm so sánh

`signedCompare32=-1` vì -1 nhỏ hơn 1 theo signed; `unsignedCompare32=1` và `unsignedCompare64=1` vì dãy toàn bit 1 biểu diễn unsigned value tối đa.

### 22.2. Diễn giải nhóm phép chia/số dư

`intUnsignedQuotient=429496729` và `intUnsignedRemainder=5` xuất phát từ phép chia 4.294.967.295 cho 10. Với long, kết quả tương ứng là 1.844.674.407.370.955.161 và dư 5.

Khi divisor = 1, quotient bằng chính unsigned max nên raw int/long là -1; chương trình in riêng **bit pattern signed** và **decimal unsigned** để bạn thấy cả hai đều đúng.

### 22.3. Diễn giải trường hợp sign bit

`intMinUnsigned=2147483648` và `longMinUnsigned=9223372036854775808` là hai giá trị tại ranh giới signed/unsigned. Chia chúng cho 3 bằng unsigned methods cho các quotient/remainder được tính theo số học không dấu, không phải lấy giá trị âm mà chia thông thường.

### 22.4. Diễn giải sorting/bucket/parse

Unsigned sort đặt `-1` ở cuối vì U32(-1) là lớn nhất. Khi lấy modulo cho `Integer.MIN_VALUE` bằng 10, remainder unsigned là 8; signed modulo ra -8. Byte 0xFF trở thành 255, short 0xFFFF thành 65535 sau zero-extension.

Parse unsigned decimal tối đa trả raw -1, đúng bit pattern. Overflow và input âm bị từ chối bằng `NumberFormatException`.

### 22.5. Vì sao có 42 trường hợp mỗi độ rộng?

Test dùng 7 bit patterns đại diện: 0, 1, -1, MIN_VALUE, MAX_VALUE, -2 và 2. Trong mỗi vòng lặp, có 7 lựa chọn dividend và **6 lựa chọn divisor khác 0**, nên số phép chia/số dư mỗi width là **7 * 6 = 42**.

Mỗi kết quả được so độc lập với `BigInteger.divideAndRemainder` sau khi chuyển operands thành unsigned positive values. Ngoài ra, test kiểm chứng dấu compareUnsigned với BigInteger.compareTo cho **toàn bộ 7 * 7 = 49 cặp** mỗi width, kể cả divisor=0 vì phép compare không bị hạn chế bởi zero.

### 22.6. Có cần import java.nio trong code?

Ví dụ đầy đủ import `java.nio.*` để gợi ý ngữ cảnh byte-oriented; chương trình chính không đọc `ByteBuffer` nên import ấy không bắt buộc. Việc import thừa này không thay đổi kết quả. Trong code production, giữ imports tối thiểu theo quy ước dự án.

## 23. Bài tập thực hành và đáp án

**Bài 1.** Java có `uint` và `ulong` primitive chuẩn không?

**Đáp án:** Không. Dùng `int`/`long` giữ raw bit patterns, với các static helpers trên `Integer`/`Long` để diễn giải unsigned khi cần.

**Bài 2.** `Integer.compareUnsigned(-1,1)` trả dấu gì?

**Đáp án:** Dương vì U32(-1)=4.294.967.295 lớn hơn 1.

**Bài 3.** `Integer.compare(-1,1)` trả dấu gì?

**Đáp án:** Âm vì đây là so sánh signed -1 với 1.

**Bài 4.** `Long.compareUnsigned(Long.MIN_VALUE, Long.MAX_VALUE)` lớn hơn 0 không?

**Đáp án:** Có. U64(Long.MIN_VALUE)=2^63, còn Long.MAX_VALUE=2^63-1.

**Bài 5.** `Integer.divideUnsigned(-1,10)` cho thương unsigned bao nhiêu?

**Đáp án:** 429496729, số dư 5.

**Bài 6.** Tại sao `Integer.divideUnsigned(-1,1)` in bằng println lại là -1?

**Đáp án:** Kết quả vẫn là raw int 32 bit `0xFFFFFFFF`, diễn giải signed là -1, unsigned là 4294967295. Dùng `toUnsignedString`.

**Bài 7.** `Integer.remainderUnsigned(-1,10)` trả gì?

**Đáp án:** 5, vì 4.294.967.295 chia 10 dư 5.

**Bài 8.** Có thể dùng `Math.floorMod(-1,10)` thay `remainderUnsigned(-1,10)` không?

**Đáp án:** Không nếu đặc tả là unsigned bits. FloorMod(-1,10)=9, còn unsigned remainder của 4.294.967.295 mod 10 là 5.

**Bài 9.** `Integer.MIN_VALUE` diễn giải unsigned là bao nhiêu?

**Đáp án:** 2147483648, tức 2^31.

**Bài 10.** `Long.MIN_VALUE` diễn giải unsigned là bao nhiêu?

**Đáp án:** 9223372036854775808, tức 2^63.

**Bài 11.** `Long.divideUnsigned(-1L,10L)` có thương unsigned bao nhiêu?

**Đáp án:** 1844674407370955161, dư 5.

**Bài 12.** `Long.divideUnsigned(-1L,1L)` có phải ném overflow exception vì quá Long.MAX_VALUE không?

**Đáp án:** Không. Trả raw long -1L; diễn giải unsigned của quotient là 18446744073709551615.

**Bài 13.** Nếu divisor signed âm như -2, có thể chia unsigned không?

**Đáp án:** Có, vì U32(-2)=4294967294, khác 0 và hợp lệ. `Integer.divideUnsigned(-1,-2)==1`.

**Bài 14.** Chia unsigned cho 0 có trả 0 không?

**Đáp án:** Không; ném `ArithmeticException`.

**Bài 15.** `Integer.parseUnsignedInt("4294967295")` trả raw signed value nào?

**Đáp án:** -1, cùng bit pattern 32 bit.

**Bài 16.** `Long.parseUnsignedLong("18446744073709551615")` trả raw signed value nào?

**Đáp án:** -1L, cùng bit pattern 64 bit.

**Bài 17.** `Long.parseUnsignedLong("-1")` có hợp lệ không?

**Đáp án:** Không. Chuỗi decimal có dấu âm bị từ chối; phải dùng chuỗi unsigned decimal hoặc một conversion bit pattern có chủ đích.

**Bài 18.** Có thể viết literal `18446744073709551615L` không?

**Đáp án:** Không; vượt miền literal signed long. Dùng `Long.parseUnsignedLong` hoặc một bit pattern tương ứng.

**Bài 19.** Đổi `int raw=-1` sang `long value=(long)raw` có bằng U32(raw) không?

**Đáp án:** Không, nó sign-extend và trả -1. Dùng `Integer.toUnsignedLong(raw)` để có 4294967295.

**Bài 20.** Tại sao unsigned long cần BigInteger khi muốn biểu diễn số dương thật sự?

**Đáp án:** U64 max lớn hơn Long.MAX_VALUE, nên chỉ giữ raw bits trong long và định dạng unsigned; BigInteger chứa được số nguyên dương toán học đầy đủ.

**Bài 21.** `BigInteger.valueOf(-1L)` có diễn giải U64(-1L) không?

**Đáp án:** Không; nó trả -1. Dùng `new BigInteger(Long.toUnsignedString(-1L))` để được 18446744073709551615.

**Bài 22.** `Byte.toUnsignedInt((byte)0xFF)` trả gì?

**Đáp án:** 255.

**Bài 23.** `Short.toUnsignedInt((short)0xFFFF)` trả gì?

**Đáp án:** 65535.

**Bài 24.** `raw >>> 3` có luôn tương đương `divideUnsigned(raw,8)` với int không?

**Đáp án:** Có cho phép dịch phải logical 3 và divisor unsigned 8 trong ngữ cảnh 32 bit; nhưng không thể thay divideUnsigned tùy ý bằng shift khi divisor không phải power of two.

**Bài 25.** `Integer.remainderUnsigned(Integer.MIN_VALUE,10)` là 2 hay 8?

**Đáp án:** 8. Số 2 là kết quả của `Math.floorMod(Integer.MIN_VALUE,10)` theo signed meaning.

**Bài 26.** Khi sort `List<Integer>` unsigned, viết comparator nào?

**Đáp án:** `Integer::compareUnsigned`.

**Bài 27.** `Arrays.sort(int[])` mặc định sắp theo unsigned không?

**Đáp án:** Không. Nó dùng signed integer ordering.

**Bài 28.** Lấy hash âm làm bucket index bằng `Math.abs(hash) % n` luôn an toàn không?

**Đáp án:** Không, vì `Math.abs(Integer.MIN_VALUE)` vẫn âm. Dùng semantics rõ ràng `Math.floorMod` hoặc `remainderUnsigned` tùy dữ liệu, và validate n>0.

**Bài 29.** Có thể truyền uint64 lớn hơn 2^53 qua JSON number của JavaScript mà luôn chính xác không?

**Đáp án:** Không. Nếu không có BigInt/decimal support chính xác ở phía nhận, cân nhắc gửi dạng chuỗi decimal unsigned và có schema rõ.

**Bài 30.** compareUnsigned có tự biết sequence number nào “mới hơn” sau wrap-around không?

**Đáp án:** Không. Nó là unsigned total order, không phải thuật toán modular recency cho sequence đã wrap.

**Bài 31.** Nếu một phép cộng unsigned 32-bit vượt MAX, có được ném overflow exception mặc định không?

**Đáp án:** Các phép cộng primitive Java tính theo fixed width và wrap bits; nếu nghiệp vụ không cho wrap, chuyển sang kiểu rộng và kiểm tra range.

**Bài 32.** Với U32(1) và U32(-1), chia 1 cho -1 bằng divideUnsigned cho kết quả gì?

**Đáp án:** Quotient 0, remainder 1 vì unsigned divisor lớn hơn dividend.

**Bài 33.** Vì sao BigInteger là oracle tốt cho kiểm thử divideUnsigned 64 bit?

**Đáp án:** Nó biểu diễn toàn bộ unsigned 64-bit range dưới dạng số dương và phép chia/số dư toán học không bị signed 64-bit wrap.

**Bài 34.** `Integer.compareUnsigned(x,y)` có cần chuyển x,y thành long trước không?

**Đáp án:** Không; nó nhận trực tiếp int bit patterns và thực hiện unsigned comparison theo contract.

**Bài 35.** Nên kiểm tra `remainder >= 0` để xác nhận mọi remainderUnsigned hợp lệ không?

**Đáp án:** Không cho divisor unsigned lớn. Dùng `Integer.compareUnsigned(remainder,divisor) < 0` hoặc phiên bản Long tương ứng.

## 24. Checklist production khi xử lý unsigned integer

- [ ] Đã xác định **bit width**: uint8/uint16/uint32/uint64; không suy luận width từ kiểu Java khác đi.
- [ ] Đã phân biệt bit pattern và signed decimal được in bởi Java.
- [ ] Dữ liệu unsigned int có thể mang raw int âm; không loại bỏ nó chỉ vì `raw < 0`.
- [ ] Dữ liệu unsigned long có thể mang raw long âm; không ép tất cả vào positive long.
- [ ] Với unsigned int order, dùng `Integer.compareUnsigned`.
- [ ] Với unsigned long order, dùng `Long.compareUnsigned`.
- [ ] Đã kiểm tra dấu âm/0/dương của compare result, không phụ thuộc magnitude -1/1.
- [ ] Với phép chia unsigned int, dùng `Integer.divideUnsigned` hoặc cả hai operands đã zero-extend chính xác sang long.
- [ ] Với phép chia unsigned long, dùng `Long.divideUnsigned`.
- [ ] Với modulo unsigned int, dùng `Integer.remainderUnsigned`.
- [ ] Với modulo unsigned long, dùng `Long.remainderUnsigned`.
- [ ] Không dùng `Math.floorMod` thay unsigned remainder nếu protocol không có signed meaning.
- [ ] Nếu divisor lấy từ input, có xử lý divisor 0 và validate domain/bucketCount đúng.
- [ ] Không xem divisor raw signed âm là vô hiệu khi dữ liệu unsigned cho phép giá trị ấy.
- [ ] Hiểu quotient/remainder vẫn là int/long bits, có thể in âm khi diễn giải signed.
- [ ] Khi in/serialize unsigned, dùng `Integer.toUnsignedString` hoặc `Long.toUnsignedString`.
- [ ] Khi parse unsigned decimal, dùng `parseUnsignedInt` hoặc `parseUnsignedLong` và xử lý NumberFormatException.
- [ ] Đã kiểm tra input vượt 2^32-1 hoặc 2^64-1; không silently truncate số ngoại miền.
- [ ] Khi chuyển int unsigned sang long, dùng `Integer.toUnsignedLong`, không chỉ cast sign-extend.
- [ ] Khi cần unsigned long positive full-range, dùng BigInteger có conversion đúng.
- [ ] Không dùng `BigInteger.valueOf(rawLong)` như unsigned converter.
- [ ] Khi đọc bytes, đã thiết lập đúng byte order (endianness) và width.
- [ ] Đã kiểm tra sort, min/max, compare và bucket dùng cùng unsigned convention.
- [ ] Đã kiểm tra Math.abs(MIN_VALUE) trap khi lấy bucket.
- [ ] Không thay divideUnsigned tùy ý bằng logical shift hoặc signed division.
- [ ] Nếu dùng shift distance, đã validate giới hạn bởi width.
- [ ] Không nghĩ add/subtract/multiply primitive có overflow exception; nếu không muốn wrap, kiểm tra bằng kiểu rộng/BigInteger.
- [ ] Nếu unsigned sequence number có wrap, đã dùng modular protocol riêng thay cho unsigned total order.
- [ ] Với JSON/JavaScript, có xử lý precision của uint64 vượt safe integer range.
- [ ] Với database, đã xác định signed BIGINT có chứa được toàn miền dữ liệu không.
- [ ] Test có trường hợp 0,1,-1,MIN_VALUE,MAX_VALUE, divisor 0, divisor có sign bit.
- [ ] Test sử dụng independent BigInteger oracle, không lấy expected bằng cùng hàm được test.
- [ ] Đã phân biệt API Java 8 và API hỗ trợ từ Java 9+ (ví dụ Byte.compareUnsigned).
- [ ] Không coi unsigned helpers là crypto/security primitives.
- [ ] Code comment/Javadoc ghi rõ khi một trường `int/long` đại diện unsigned protocol value.

## 25. Tài liệu tham khảo chính thức vẫn áp dụng

1. [Oracle Java SE 26 — Integer: compareUnsigned, divideUnsigned, remainderUnsigned, parseUnsignedInt, toUnsignedString, toUnsignedLong](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Integer.html)
2. [Oracle Java SE 26 — Long: compareUnsigned, divideUnsigned, remainderUnsigned, parseUnsignedLong, toUnsignedString](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Long.html)
3. [Oracle Java SE 26 — BigInteger: biểu diễn số nguyên lớn và divideAndRemainder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html)
4. [Oracle Java SE 26 — Byte: toUnsignedInt, toUnsignedLong và compareUnsigned từ Java 9](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Byte.html)
5. [Oracle Java SE 26 — Short: toUnsignedInt và compareUnsigned từ Java 9](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Short.html)
6. [Oracle Java SE 26 — ByteBuffer: getInt/getLong và byte order](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html)
7. [Oracle Java SE 26 — Math: floorMod và sự khác nhau với remainder unsigned](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html)
8. [Oracle Java SE 26 — Arrays: compareUnsigned cho mảng từ Java 9, khác sort signed](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html)
9. [Java Language Specification — `15.17: Multiplicative Operators (/ và %) và `15.19: Shift Operators](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.17)
10. [Oracle Java SE 26 — Comparator: quan hệ thứ tự khi truyền Integer::compareUnsigned hoặc Long::compareUnsigned](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html)

**Ghi nhớ:** `compareUnsigned` so sánh theo **giá trị không dấu của các bit**; `divideUnsigned` và `remainderUnsigned` trả thương/số dư theo cùng cách diễn giải. Chúng **không tạo unsigned primitives mới**: mọi kết quả vẫn là `int` hoặc `long`. Khi có sign bit, phép toán `<, /, %` thông thường và cách in signed decimal có thể khác unsigned semantics. Muốn chương trình đúng, hãy thống nhất cách hiểu tại mọi điểm **đọc dữ liệu → xử lý → so sánh/chia/modulo → xuất dữ liệu**, và kiểm chứng boundary bằng BigInteger khi cần.

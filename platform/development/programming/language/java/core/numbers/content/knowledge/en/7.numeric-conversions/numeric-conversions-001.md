# Widening và narrowing giữa các kiểu số trong Java

**Chuyển kiểu số (*numeric conversion*)** là việc đổi một giá trị giữa các kiểu primitive số của Java: `byte`, `short`, `char`, `int`, `long`, `float`, `double`. Hai nhóm quan trọng:

- **Widening primitive conversion**: chuyển sang kiểu được Java cho phép mở rộng **tự động**, chẳng hạn `int` → `long` hoặc `int` → `double`.
- **Narrowing primitive conversion**: chuyển theo hướng mà Java yêu cầu **ép kiểu tường minh** trong phần lớn ngữ cảnh, chẳng hạn `long` → `int`, `double` → `int` hoặc `int` → `byte`.

Cần phân biệt ba câu hỏi độc lập: **chuyển đổi có được phép về cú pháp không**, **giá trị toán học có được giữ chính xác không**, và **phạm vi của kiểu đích có đủ chứa kết quả không**. Widening được phép tự động không có nghĩa mọi chữ số được giữ tuyệt đối; narrowing không chỉ đơn giản là “cắt phần thập phân” cho tất cả các cặp kiểu.

## 1. Các kiểu primitive số và giới hạn

| Kiểu | Độ rộng | Miền giá trị hoặc ý nghĩa |
| --- | ---: | --- |
| `byte` | 8 bit | -128 đến 127 |
| `short` | 16 bit | -32.768 đến 32.767 |
| `char` | 16 bit | 0 đến 65.535 (mã đơn vị UTF-16 không dấu) |
| `int` | 32 bit | -2.147.483.648 đến 2.147.483.647 |
| `long` | 64 bit | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |
| `float` | 32 bit | Số thực dấu phẩy động IEEE 754, độ chính xác khoảng 6–9 chữ số thập phân có nghĩa |
| `double` | 64 bit | Số thực dấu phẩy động IEEE 754, độ chính xác khoảng 15–17 chữ số thập phân có nghĩa |

`char` là **kiểu nguyên không dấu** trong các phép chuyển đổi số Java, dù thường được dùng làm ký tự. `boolean` **không thuộc nhóm kiểu số**: không thể chuyển tự động hoặc ép kiểu primitive giữa `boolean` và `int`.

`float` và `double` có phạm vi độ lớn rất rộng nhưng không biểu diễn chính xác mọi số nguyên hoặc mọi phân số thập phân. Độ rộng bit của số thực gồm bit dấu, số mũ và phần trị (*significand*); không thể suy luận độ chính xác chỉ từ độ rộng 32/64 bit.

## 2. Các đường widening hợp lệ

Java cho phép widening primitive conversion sau:

| Kiểu nguồn | Các kiểu đích widening |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | Không có kiểu primitive số nào rộng hơn |

Ví dụ:

```java
byte b = -12;
short s = b;      // byte -> short
int i = s;        // short -> int
long l = i;       // int -> long
float f = l;      // long -> float
double d = f;     // float -> double

char letter = 'A';
int codePointUnit = letter; // 65: char -> int
long codeAsLong = letter;   // char -> long
```

Cả hai nhánh đều **không cần ép kiểu**. Chú ý `char` không widening sang `short`, vì `short` mang dấu không chứa toàn bộ dải 0..65535 của `char`; `byte` cũng không widening sang `char` vì `byte` có giá trị âm.

```java
char c = 'A';
// short invalid = c; // lỗi: char -> short không widening
byte b = 65;
// char invalid2 = b; // lỗi: byte -> char không widening
```

Đây là các đoạn minh họa để đặt bên trong class, không phải chương trình độc lập. Các dòng chú thích sẽ gây lỗi biên dịch nếu bỏ dấu chú thích.

### Widening có thể mất độ chính xác

Các chuyển đổi sau **luôn giữ chính xác giá trị**:

- `byte` → `short`/`int`/`long`/`float`/`double`.
- `short` và `char` → `int`/`long`/`float`/`double`.
- `int` → `long` hoặc `double`.
- `float` → `double` giữ đúng giá trị số thực nhị phân đang chứa, kể cả `NaN` và vô cực.

Nhưng `int` → `float`, `long` → `float` và `long` → `double` **có thể làm tròn**. Cụ thể, `float` có 24 bit độ chính xác phần trị, `double` có 53 bit; các số nguyên liên tiếp quá lớn sẽ không còn biểu diễn tách biệt được.

```java
int preciseAsInt = 16_777_217;    // 2^24 + 1
float roundedAsFloat = preciseAsInt; // làm tròn thành 16777216.0f

long preciseAsLong = 9_007_199_254_740_993L; // 2^53 + 1
double roundedAsDouble = preciseAsLong; // làm tròn thành 9007199254740992.0
```

Cả hai phép gán trên là **widening hợp lệ**, không gây lỗi biên dịch, cũng không ném exception. Tuy nhiên dữ liệu mất một đơn vị vì kiểu đích không đủ độ chính xác. Khi so sánh ID, số tiền nguyên hoặc bộ đếm lớn, đây là lý do không nên vô tình chuyển `long` thành `double`.

## 3. Narrowing: khi nào phải viết phép ép kiểu?

Narrowing primitive conversion thường được ghi bằng toán tử cast `(TargetType) value`:

```java
long large = 1_000;
int number = (int) large;        // long -> int
double decimal = 42.75;
int truncated = (int) decimal;   // double -> int: 42
int value = 260;
byte small = (byte) value;       // int -> byte: 4
```

Nếu bỏ cast trong ngữ cảnh gán thông thường thì trình biên dịch từ chối:

```java
long large = 1_000;
// int wrong = large;    // lỗi: possible lossy conversion from long to int
double price = 42.75;
// int wrong2 = price;   // lỗi: double -> int cần cast
```

Cast **cho phép chuyển đổi theo quy tắc ngôn ngữ**, không xác nhận giá trị nằm trong miền kiểu đích. Java không tự phát hiện tràn khi cast số nguyên primitive; mã biên dịch được vẫn có thể mất thông tin.

Các ví dụ narrowing phổ biến gồm `int` → `byte`/`short`/`char`, `long` → `int`, `double` → `float`, và `float`/`double` → một kiểu nguyên.

## 4. Narrowing từ kiểu nguyên sang kiểu nguyên: giữ các bit thấp

Khi chuyển một số nguyên sang kiểu nguyên có độ rộng nhỏ hơn, Java loại bỏ các bit cao và giữ số bit thấp theo độ rộng của kiểu đích. Sau đó:

- `byte` và `short` được diễn giải theo bù hai có dấu.
- `char` là giá trị không dấu 16 bit từ 0 đến 65.535.

Ví dụ:

| Biểu thức | Kết quả | Giải thích |
| --- | ---: | --- |
| `(byte) 127` | 127 | Nằm trong miền byte |
| `(byte) 128` | -128 | 8 bit thấp là `0x80`, có bit dấu |
| `(byte) 255` | -1 | 8 bit thấp là `0xFF` |
| `(byte) 256` | 0 | 8 bit thấp đều bằng 0 |
| `(byte) 260` | 4 | 260 mod 256 bằng 4 |
| `(short) 65_535` | -1 | 16 bit thấp đều bằng 1 |
| `(char) -1` | 65.535 | 16 bit thấp là `0xFFFF` |
| `(int) Long.MAX_VALUE` | -1 | Giữ 32 bit thấp của `long` |

```java
int source = 260;
byte byteValue = (byte) source; // 4
short shortValue = (short) 65_535; // -1
char charValue = (char) -1; // mã char 65535
int lowerBits = (int) Long.MAX_VALUE; // -1
```

**Không dùng cast để kiểm tra miền giá trị.** Nếu cần từ chối mọi `long` không chứa vừa `int`, sử dụng `Math.toIntExact(longValue)`: method này ném `ArithmeticException` khi ngoài miền `int`.

```java
long valid = 123;
int exact = Math.toIntExact(valid); // 123

// Math.toIntExact(Long.MAX_VALUE) ném ArithmeticException
```

`Math.toIntExact` không có biến thể tương ứng cho mọi cặp kiểu nhỏ hơn: muốn từ chối khi thu hẹp sang `byte`/`short`/`char`, hãy kiểm tra phạm vi rõ ràng trước khi cast.

## 5. Narrowing từ số thực sang số nguyên: cắt phần lẻ, chặn biên

Đối với `float`/`double` → `int` hoặc `long`, Java dùng phép chuyển đổi được xác định theo các bước:

1. Nếu toán hạng là `NaN`, kết quả số nguyên là `0`.
2. Nếu giá trị hữu hạn nằm trong khoảng biểu diễn, **loại bỏ phần lẻ theo hướng về 0** (*truncate toward zero*), không làm tròn đến số nguyên gần nhất.
3. Nếu giá trị quá lớn hoặc quá nhỏ, kết quả **bị chặn ở biên** tương ứng (`MIN_VALUE` hoặc `MAX_VALUE`).
4. `+Infinity` và `-Infinity` lần lượt chuyển thành biên dương và biên âm.

Ví dụ:

```java
int positive = (int) 12.99;          // 12
int negative = (int) -12.99;         // -12
int nan = (int) Double.NaN;         // 0
int positiveInf = (int) Double.POSITIVE_INFINITY; // 2147483647
int negativeInf = (int) Double.NEGATIVE_INFINITY; // -2147483648
long huge = (long) 1e100;           // Long.MAX_VALUE
```

**Truncation không giống `Math.floor`**: `(int)-12.99` bằng `-12`, còn `Math.floor(-12.99)` bằng `-13.0`.

### Đích nhỏ hơn `int`: có bước cắt bit tiếp theo

Với `float`/`double` → `byte`, `short` hoặc `char`, Java **chuyển số thực sang `int` trước**, rồi narrowing tiếp từ `int` sang kiểu nguyên nhỏ:

```java
byte a = (byte) 257.8;          // 1: 257 -> byte
byte b = (byte) Double.NaN;     // 0
char c = (char) -1.9;           // 65535: -1 -> char
byte saturatedThenNarrowed = (byte) 1e100; // -1: int MAX -> 8 bit thấp
```

Vì vậy “chặn ở biên” khi số thực vượt miền `int` **không đồng nghĩa** khi ép tiếp xuống `byte` thì nó sẽ bị chặn ở 127 hay -128. Việc cắt bit vẫn xảy ra sau bước chuyển sang `int`.

Nếu cần làm tròn số thực theo một chính sách xác định, việc cast chỉ là một lựa chọn rất cụ thể. Chẳng hạn `Math.round` có quy tắc riêng và `BigDecimal` có các chế độ làm tròn khác; không thay thế lẫn nhau một cách máy móc.

## 6. Narrowing giữa `double` và `float`

`double` → `float` cần cast trong ngữ cảnh gán:

```java
double d = 1.25;
float f = (float) d;   // 1.25f, biểu diễn chính xác ở ví dụ này
```

Trong quá trình thu hẹp, một giá trị hữu hạn có thể:

- **Bị làm tròn** vì độ chính xác 24 bit của `float` thấp hơn 53 bit của `double`.
- Trở thành `Float.POSITIVE_INFINITY` hoặc `Float.NEGATIVE_INFINITY` nếu độ lớn vượt giá trị `float` hữu hạn tối đa.
- Trở thành `+0.0f` hoặc `-0.0f` (hay số *subnormal*) nếu độ lớn quá nhỏ.
- Giữ `NaN` hoặc vô cực theo bản chất giá trị nguồn.

```java
double large = 1e100;
float infinity = (float) large; // Infinity

double tiny = 1e-100;
float underflow = (float) tiny; // +0.0f
```

Widening ngược lại `float` → `double` là tự động và giữ chính xác giá trị `float` hiện có, **không thể khôi phục** những chữ số đã mất khi tạo `float`.

Ví dụ `double widenedBack = (double) ((float) 0.1);` không bằng literal `double` `0.1`: giá trị ban đầu đã được làm tròn ở bước chuyển xuống `float` rồi mới được mở rộng trở lại.

## 7. Ngoại lệ: gán biểu thức hằng `int` vào `byte`, `short` và `char`

Mặc dù `int` → `byte`/`short`/`char` là narrowing, Java cho phép **narrowing conversion trong ngữ cảnh gán** với biểu thức hằng tại thời điểm biên dịch thỏa điều kiện.

```java
byte a = 100;      // hợp lệ: int literal 100 nằm trong byte
short b = 30_000;  // hợp lệ: int literal nằm trong short
char c = 65;       // hợp lệ: int literal nằm trong char

final int LIMIT = 120; // constant variable: initializer là constant expression
byte value = LIMIT;    // hợp lệ vì giá trị vừa byte

// byte invalid = 128;    // lỗi: vượt byte
// short invalid2 = 40000; // lỗi: vượt short
// char invalid3 = -1;    // lỗi: char không âm
```

**Giá trị có vẻ nhỏ tại runtime chưa đủ**; với biến thường có kiểu `int`, compiler không tự narrowing:

```java
int count = 100;
// byte no = count; // lỗi: count là biến int thông thường
byte yes = (byte) count;
```

Trường hợp hằng là quy tắc ngôn ngữ áp dụng theo ngữ cảnh cụ thể; nó **không thay thế** cast ở các tình huống nói chung. `long` literal như `100L` cũng không tự gán thành `byte` chỉ vì giá trị 100 vừa phạm vi.

## 8. Phép toán số học có thể làm đổi kiểu trước khi gán

Java áp dụng **binary numeric promotion** với các toán tử số học thông thường. `byte`, `short` và `char` thường được nâng lên `int` trong phép cộng, trừ, nhân. Nếu có `long` và không có toán hạng số thực, biểu thức được tính bằng `long`; nếu có `float` hoặc `double` thì quy tắc nâng kiểu tương ứng áp dụng.

```java
byte left = 10;
byte right = 20;
// byte sum = left + right; // lỗi: left + right có kiểu int
int sum = left + right;   // 30
byte smallSum = (byte) (left + right); // 30, nhưng có thể mất dữ liệu ở giá trị khác
```

Hệ quả nguy hiểm: cast **sau khi** phép toán đã tràn thì không khôi phục được kết quả toán học:

```java
int quantity = 100_000;
long wrong = (long) (quantity * quantity); // int tràn -> 1410065408L
long correct = (long) quantity * quantity; // nhân kiểu long -> 10000000000L
```

Dù `wrong` có kiểu `long`, phép nhân bên trong dấu ngoặc vẫn là `int`. Cast một toán hạng **trước phép nhân** làm thay đổi kiểu tính toán, vì toán hạng `long` buộc toán hạng `int` còn lại được nâng lên `long`.

Một trường hợp khác với `float`:

```java
long veryLarge = 9_007_199_254_740_993L;
double rounded = veryLarge;      // làm tròn
long convertedBack = (long) rounded; // 9007199254740992L
```

Giá trị đã mất khi widening không thể lấy lại bằng narrowing ngược.

### Compound assignment có thể narrowing ngầm

`+=`, `-=`, `*=` có ngữ nghĩa tương đương về kiểu với phép toán rồi chuyển kết quả trở về kiểu biến bên trái (với lưu ý vế trái chỉ được đánh giá một lần):

```java
byte b = 127;
b += 1;     // hợp lệ, nhưng b thành -128 do thu hẹp sau phép cộng
// b = b + 1; // lỗi: b + 1 có kiểu int, không tự gán về byte
```

Dạng `b++` cũng cập nhật giá trị về kiểu của biến và có thể tràn; việc thấy cú pháp ngắn không có nghĩa được bảo đảm không mất dữ liệu.

## 9. Boxing, unboxing và chuyển đổi primitive: đừng đánh đồng

Kiểu wrapper như `Integer`, `Long` và `Double` là **kiểu tham chiếu**, khác các kiểu primitive `int`, `long` và `double`. Java có boxing/unboxing ở một số ngữ cảnh, nhưng không phải mọi cặp wrapper đều tự chuyển cho nhau.

```java
Integer boxed = 42;
long widenedAfterUnboxing = boxed; // Integer -> int (unbox) -> long
Long boxedLong = 42L;              // long -> Long (boxing)

// Long invalid = boxed;          // không thể tự đổi Integer -> Long qua unbox/widen/box
Long explicit = boxed.longValue();  // lấy long rồi boxing
```

Unboxing `null` có thể ném `NullPointerException`:

```java
Integer missing = null;
// long n = missing; // biên dịch được, nhưng ném NullPointerException khi chạy
```

Các vấn đề như chuyển chuỗi `"42"` bằng `Integer.parseInt`, lưu tiền dưới dạng `BigDecimal` hoặc biểu diễn số nguyên không giới hạn bằng `BigInteger` là những cơ chế khác, không phải quy tắc widening/narrowing primitive.

## 10. Chương trình Java 17+ chạy được và đầu ra được kiểm chứng

Tạo tệp **`PrimitiveConversionsOverviewDemo.java`**:

```java
public class PrimitiveConversionsOverviewDemo {
    public static void main(String[] args) {
        byte b = -10;
        long widened = b;
        System.out.println("widenByteToLong=" + widened);

        char letter = 'A';
        int charCode = letter;
        System.out.println("widenCharToInt=" + charCode);

        int intBeyondFloatPrecision = 16_777_217;
        float roundedFloat = intBeyondFloatPrecision;
        System.out.println("floatRoundedToInt=" + (int) roundedFloat);

        long longBeyondDoublePrecision = 9_007_199_254_740_993L;
        double roundedDouble = longBeyondDoublePrecision;
        System.out.println("doubleRoundedToLong=" + (long) roundedDouble);

        System.out.println("narrowIntToByte=" + (byte) 257);
        System.out.println("narrowNegativeToChar=" + (int) (char) -1);
        System.out.println("floatToIntTrunc=" + (int) 9.99);
        System.out.println("negativeFloatToIntTrunc=" + (int) -9.99);
        System.out.println("positiveInfinityToInt=" +
                (int) Double.POSITIVE_INFINITY);
        System.out.println("nanToInt=" + (int) Double.NaN);
        System.out.println("longToInt=" + (int) Long.MAX_VALUE);
        System.out.println("doubleToLongClamped=" + (long) 1e100);

        byte compound = 127;
        compound += 1;
        System.out.println("compoundByte=" + compound);

        int quantity = 100_000;
        long earlyWide = (long) quantity * quantity;
        long lateWide = (long) (quantity * quantity);
        System.out.println("earlyWide=" + earlyWide);
        System.out.println("lateWide=" + lateWide);

        byte constantByte = 127;
        System.out.println("constByte=" + constantByte);

        long roundTrip = (long) roundedDouble;
        System.out.println("roundTripLoss=" +
                (roundTrip == longBeyondDoublePrecision));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac PrimitiveConversionsOverviewDemo.java
java PrimitiveConversionsOverviewDemo
```

Đầu ra dự kiến:

```text
widenByteToLong=-10
widenCharToInt=65
floatRoundedToInt=16777216
doubleRoundedToLong=9007199254740992
narrowIntToByte=1
narrowNegativeToChar=65535
floatToIntTrunc=9
negativeFloatToIntTrunc=-9
positiveInfinityToInt=2147483647
nanToInt=0
longToInt=-1
doubleToLongClamped=9223372036854775807
compoundByte=-128
earlyWide=10000000000
lateWide=1410065408
constByte=127
roundTripLoss=false
```

Đặc biệt chú ý `earlyWide` khác `lateWide`: vị trí cast làm thay đổi kiểu **khi thực hiện phép nhân**. Hai dòng về số thực minh họa việc widening có thể làm tròn số nguyên lớn; phép cast ngược chỉ đọc giá trị đã làm tròn.

## 11. Chọn cách chuyển đổi theo yêu cầu dữ liệu

| Nhu cầu | Cách làm phù hợp | Cần lưu ý |
| --- | --- | --- |
| Đổi `int` sang `long` | `long n = intValue;` | Giá trị được giữ chính xác |
| Đổi `long` sang `int` mà không cho mất dữ liệu | `Math.toIntExact(longValue)` | Ném `ArithmeticException` nếu ngoài miền |
| Đổi `int` sang `byte` và chấp nhận bit thấp | `(byte) intValue` | Có thể ra số âm do bù hai |
| Đổi `int` sang `byte` nhưng phải nằm trong -128..127 | Kiểm tra `Byte.MIN_VALUE <= n && n <= Byte.MAX_VALUE` trước khi cast | Tự xử lý khi ngoài miền |
| Xử lý `double` sang `int` | `(int) doubleValue` nếu đúng chính sách cắt về 0 | `NaN` thành 0; vô cực/ngoài miền bị chặn |
| Lưu số nguyên `long` cực lớn chính xác | Giữ `long` hoặc dùng `BigInteger` | Chuyển qua `double` có thể mất đơn vị |
| Tính tích hai `int` có thể vượt 32 bit | `(long) a * b` | Cast xảy ra trước phép nhân |
| Muốn phép tính tràn phải báo lỗi | `Math.addExact`, `subtractExact`, `multiplyExact` | Phải chọn overload và bảo vệ ngay bước tính |

### Checklist tránh lỗi chuyển kiểu

1. Xác định **kiểu nguồn và kiểu đích**; tra đường widening để biết có cần cast không.
2. Kiểm tra **độ chính xác**, đặc biệt `int/long` sang `float/double`; widening chưa chắc chính xác tuyệt đối.
3. Với narrowing nguyên → nguyên, xem **bit bị cắt**; với số thực → nguyên, xem quy tắc **cắt phần lẻ, `NaN` và chặn biên**.
4. Phân biệt **hằng biểu thức** với biến thường khi gán vào `byte`/`short`/`char`.
5. Nếu có phép toán trung gian, xác định **kiểu được dùng khi tính**, rồi mới xét kiểu biến đích; cast phải đúng vị trí.
6. Nếu không được phép mất dữ liệu, tự kiểm tra miền giá trị hoặc dùng API kiểm tra chính xác thay vì cast mù quáng.

**Kết luận:** *Widening* chủ yếu là sự cho phép chuyển kiểu tự động theo hệ thống kiểu Java; *narrowing* thường phải được yêu cầu tường minh vì có nguy cơ mất thông tin. Mọi lựa chọn chuyển kiểu nên dựa trên **miền giá trị, độ chính xác và mục đích phép tính**, không chỉ dựa vào việc dòng code có biên dịch được hay không.
# Kiểm tra overflow trước và sau chuyển kiểu trong Java

Khi xử lý dữ liệu số, một phép tính có thể gây mất dữ liệu ở **hai thời điểm khác nhau**: ngay lúc thực hiện phép cộng/nhân trong kiểu hiện tại, hoặc lúc chuyển kết quả sang kiểu có miền giá trị nhỏ hơn. Nếu chỉ kiểm tra sau khi dữ liệu đã bị mất, chương trình có thể kết luận sai rằng giá trị vẫn hợp lệ. Đây là một lỗi quan trọng khi kiểm thử và chẩn đoán chương trình Java.

Bài này hướng dẫn xác định **kiểu của từng phép tính**, phân biệt chuyển kiểu mở rộng và thu hẹp, phát hiện overflow đúng thời điểm bằng `Math.addExact`, `Math.multiplyExact`, `Math.toIntExact`, và sử dụng `BigInteger`/`BigDecimal` khi cần. Các ví dụ tập trung vào Java 17+, bao gồm những phản ví dụ thường làm bài test vượt biên cho kết luận sai.

## 1. Ba câu hỏi phải kiểm tra riêng

Giả sử một API nhận số lượng và đơn giá, tính tổng rồi lưu vào trường số nguyên. Cần làm rõ:

1. **Đầu vào có nằm trong miền hợp lệ không?** Ví dụ số lượng không âm và đơn giá không vượt giới hạn hợp đồng.
2. **Mọi phép tính trung gian có biểu diễn được trong kiểu đang dùng không?** Hai số `int` hợp lệ chưa chắc tích hoặc tổng `int` cũng hợp lệ.
3. **Kết quả cuối có vừa kiểu đích và giữ đúng độ chính xác không?** Một kết quả `long` hợp lệ có thể không vừa `int`; một `BigDecimal` có thể có phần thập phân không thể chuyển sang số nguyên mà không mất dữ liệu.

Ba câu hỏi độc lập với nhau. Việc kiểm tra điều kiện nghiệp vụ trên đầu vào không bảo đảm phép tính an toàn; việc kết quả nằm trong miền kiểu đích sau phép ép kiểu cũng **không chứng minh** dữ liệu ban đầu không bị tràn.

### Các miền kiểu số nguyên thường gặp

| Kiểu | Miền biểu diễn | Ghi chú |
| --- | --- | --- |
| `byte` | -128 đến 127 | Chuyển từ `int` sang `byte` có thể cắt bit |
| `short` | -32.768 đến 32.767 | Chuyển từ `int` sang `short` có thể cắt bit |
| `char` | 0 đến 65.535 | Không dấu; chuyển từ số nguyên lớn/âm có thể cắt bit |
| `int` | -2.147.483.648 đến 2.147.483.647 | Phép cộng/nhân `int` có thể overflow |
| `long` | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | Rộng hơn `int`, nhưng không vô hạn |
| `BigInteger` | Độ lớn thay đổi | Không bị giới hạn ở 32/64 bit; vẫn chịu giới hạn tài nguyên |

Java dùng số nguyên có dấu có độ rộng cố định cho `byte`, `short`, `int`, `long`. Phép cộng và nhân nguyên thông thường vượt miền sẽ cho kết quả theo các bit thấp của phép tính; đối với `int` và `long`, có thể hiểu như số học modulo \(2^{32}\) hoặc \(2^{64}\) rồi diễn giải theo số có dấu. Các phép `+`, `-`, `*` trên nguyên thủy **không tự ném** `ArithmeticException` khi overflow.

## 2. Overflow xảy ra **trước** khi chuyển sang kiểu rộng hơn

Trong Java, kiểu của phép toán được quyết định từ **toán hạng**, không từ kiểu biến nhận kết quả:

```java
int max = Integer.MAX_VALUE; // 2147483647
int one = 1;

long tooLate = max + one;       // -2147483648
long alsoTooLate = (long) (max + one); // -2147483648
long inTime = (long) max + one; // 2147483648
```

Hai biểu thức đầu cộng dưới dạng `int`, overflow đã xảy ra rồi mới chuyển kết quả sai sang `long`. Đặt `(long)` trên **một toán hạng trước phép cộng** khiến phép toán được thực hiện ở miền `long`, nên ví dụ này giữ tổng chính xác.

Sơ đồ xử lý:

```text
Sai:
(int) MAX_VALUE + (int) 1  → cộng int → overflow → ép sang long
Đúng:
(long) MAX_VALUE + (int) 1 → cộng long → 2147483648
```

Đây cũng là lý do không nên viết phép kiểm tra như:

```java
long total = (long) (left + right);
if (total > Integer.MAX_VALUE) {
    // Không thể phát hiện mọi overflow int đã xảy ra.
}
```

Nếu `left + right` đã thành giá trị âm do overflow, điều kiện `total > Integer.MAX_VALUE` có thể `false` dù tổng toán học thực sự vượt cực đại.

### Phép nhân và biểu thức tổng hợp

```java
int quantity = 50_000;
int unitPrice = 50_000;

long wrong = quantity * unitPrice;        // -1794967296
long right = (long) quantity * unitPrice; // 2500000000
```

Ngay cả khi tổng được tích lũy bằng `long`, phần tử đầu vào của tổng có thể đã sai:

```java
long total = 0L;
total += quantity * unitPrice;          // Nhân int trước, rồi cộng long: sai.
total += (long) quantity * unitPrice;   // Phép nhân thứ hai chính xác trong long.
```

Đoạn này minh họa thứ tự đánh giá; nó không phải cách tính tổng đúng vì `total` đã chứa kết quả sai từ dòng đầu. Trong chương trình thật, chỉ sử dụng biểu thức có phép nâng kiểu sớm. Cần phân tích **từng phép cộng/nhân**, đặc biệt trong lambda, mapper và collector.

### `byte` và `short` cũng cần chú ý

Phép toán `byte + byte` hay `short + short` được **nâng kiểu lên `int`** trước khi cộng; tuy nhiên khi ép kết quả trở lại kiểu nhỏ, nó có thể mất dữ liệu:

```java
byte a = 120;
byte b = 20;
int safeInt = a + b;     // 140
byte wrapped = (byte) (a + b); // -116
```

Ở đây không có overflow của phép cộng `int`; lỗi xảy ra ở bước **narrowing conversion** từ `int` về `byte`. Đây là lý do cần phân biệt overflow của phép tính với mất dữ liệu khi chuyển kiểu.

## 3. Kiểm tra overflow **ngay tại phép tính**

Khi hợp đồng yêu cầu lỗi phải được phát hiện ở từng phép toán nguyên, dùng các API **exact** trong `java.lang.Math`:

```java
int checkedAdd = Math.addExact(a, b);
int checkedSub = Math.subtractExact(a, b);
int checkedMul = Math.multiplyExact(a, b);

long checkedLong = Math.addExact(longA, longB);
```

Các biến ở trên là biến minh họa cần khai báo trong ngữ cảnh ứng dụng. `Math.addExact`, `subtractExact`, `multiplyExact` ném `ArithmeticException` khi kết quả vượt miền của kiểu tham số/kết quả tương ứng.

Ví dụ:

```java
try {
    int sum = Math.addExact(Integer.MAX_VALUE, 1);
    System.out.println(sum);
} catch (ArithmeticException ex) {
    System.out.println("Overflow during int addition");
}
```

Output:

```text
Overflow during int addition
```

Phương thức `Math.addExact(int, int)` kiểm tra phép cộng `int` khi nó diễn ra. Nếu đã viết `int bad = a + b;` rồi sau đó mới gọi `Math.addExact(bad, 0)`, phép kiểm tra **không** thể biết một phép tính trước đó đã overflow.

### Khi có thể nâng kiểu rồi chỉ kiểm tra tổng cuối

Một hợp đồng khác là “phép tính cuối cùng phải vừa `int`”, dù giá trị trung gian theo thứ tự thực hiện có thể vượt `int`. Khi tổng của một mảng `int[]` được thực hiện trong `long`, có thể kiểm tra bằng:

```java
int[] values = {Integer.MAX_VALUE, 1, -1};
long exactSum = Arrays.stream(values).asLongStream().sum();
int result = Math.toIntExact(exactSum); // 2147483647
```

Đoạn trên cần `import java.util.Arrays;` và đặt trong phương thức. `Math.toIntExact` kiểm tra việc **thu hẹp kết quả cuối**. Nếu dùng `Math.addExact` để cộng từ trái sang phải trong `int`, phép cộng `Integer.MAX_VALUE + 1` sẽ ném ngoại lệ trước khi cộng `-1`.

Với `parallel stream`, nhóm các phép cộng có thể khác nhau; các phép kiểm tra overflow **từng bước** có thể gặp hoặc không gặp lỗi tùy các tổng trung gian, dù tổng cuối theo toán học vẫn như nhau. Nếu hợp đồng chỉ kiểm tra tổng cuối, hãy cộng trong miền đủ rộng (`long` khi có thể chứng minh đủ, hoặc `BigInteger`) trước khi chuyển kiểu.

## 4. Overflow và mất dữ liệu xảy ra **khi ép sang kiểu nhỏ**

Chuyển `long` sang `int` bằng cast không phải phép kiểm tra. Nó giữ các bit thấp của giá trị nguồn và có thể đổi cả dấu:

```java
long beyondInt = 2_147_483_648L;

int unsafe = (int) beyondInt; // -2147483648
```

Nếu muốn từ chối trường hợp ngoài miền, dùng:

```java
int checked = Math.toIntExact(beyondInt);
// Ném ArithmeticException.
```

Với trường hợp hợp lệ:

```java
int checked = Math.toIntExact(42L); // 42
```

`Math.toIntExact` kiểm tra **long → int**. Nó không cung cấp trực tiếp phiên bản `int → short` hoặc `int → byte`; cần kiểm tra biên rồi mới cast:

```java
static byte toByteExact(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new ArithmeticException("outside byte range: " + value);
    }
    return (byte) value;
}
```

Đây là phương thức minh họa phải nằm trong một class. Với `short` thay bằng `Short.MIN_VALUE`/`Short.MAX_VALUE`. Với `char`, miền từ 0 đến `Character.MAX_VALUE` và không mang dấu. Không dùng `(byte)`, `(short)`, `(char)` như phép kiểm tra phạm vi.

### Bẫy kiểm tra **sau khi** cast

```java
long original = 2_147_483_648L;
int narrowed = (int) original;

// Luôn true, nên không phát hiện original đã nằm ngoài int:
boolean nowFitsInt = narrowed >= Integer.MIN_VALUE
        && narrowed <= Integer.MAX_VALUE;
```

Sau khi cast, `narrowed` **đương nhiên** là một `int`; so sánh nó với `Integer.MIN_VALUE` và `Integer.MAX_VALUE` không xác thực được giá trị ban đầu. Phải kiểm tra `original` **trước** khi ép hoặc dùng `Math.toIntExact(original)`.

Có thể kiểm tra round trip khi nguồn **chưa bị tràn**:

```java
long original = 2_147_483_648L;
int narrowed = (int) original;
boolean exact = (long) narrowed == original; // false
```

Mẫu round trip này có tác dụng cho phép chuyển `long → int`, nhưng `Math.toIntExact` làm mục đích kiểm tra rõ ràng hơn. **Nếu bản thân `original` được tạo từ một phép cộng `int` đã overflow**, round trip cũng không khôi phục được tổng toán học đã mất.

## 5. Chuyển đổi `BigInteger`/`BigDecimal`: kiểm tra cả miền lẫn phần thập phân

`BigInteger` có thể vượt giới hạn `long`. Các phương thức chuyển kiểu nguyên thông thường có thể làm mất các bit cao:

```java
BigInteger large = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);

long wrapped = large.longValue(); // Long.MIN_VALUE
```

Khi cần giữ nguyên toàn bộ giá trị số, dùng:

```java
long checked = large.longValueExact();
// Ném ArithmeticException vì large vượt miền long.
```

Các API chính xác gồm `BigInteger.intValueExact()`, `longValueExact()`, `shortValueExact()`, `byteValueExact()`. Không dùng `longValue()` rồi kiểm tra miền của biến `long` mới tạo; lúc đó phần lớn giá trị có thể đã mất.

Với `BigDecimal`, có **hai dạng mất dữ liệu** khi chuyển sang kiểu nguyên:

1. Giá trị vượt miền của kiểu đích.
2. Giá trị có phần thập phân khác 0 và phép chuyển sẽ cắt bỏ phần lẻ.

Ví dụ:

```java
BigDecimal decimal = new BigDecimal("12.5");

int truncated = decimal.intValue(); // 12, phần .5 bị bỏ.
int exact = decimal.intValueExact(); // ArithmeticException.
```

`BigDecimal.intValueExact()`/`longValueExact()` từ chối cả kết quả ngoài miền và kết quả không phải số nguyên. Nếu muốn làm tròn trước khi chuyển, **quy tắc làm tròn phải được xác định trước**:

```java
BigDecimal rounded = new BigDecimal("12.5")
        .setScale(0, RoundingMode.HALF_UP);
int value = rounded.intValueExact(); // 13
```

Ví dụ làm tròn cần import `java.math.RoundingMode`. `HALF_UP` chỉ là chính sách ví dụ; với phép tính tài chính, kết quả có thể đòi hỏi `HALF_EVEN` hoặc không cho phép làm tròn. Phân biệt rõ “giá trị vừa kiểu đích” với “chuyển đổi chính xác không mất phần thập phân”.

## 6. Chuyển số thực `double` sang số nguyên không giống overflow kiểu `int`

Một cast từ `double` sang `int`/`long` có hành vi khác hoàn toàn so với cast từ `long` sang `int`. Trong Java, chuyển narrowing từ `double` sang số nguyên trước hết làm tròn về 0; đối với `NaN` kết quả là 0; khi độ lớn vượt miền đích, kết quả **bão hòa ở giới hạn** của kiểu đích.

```java
(int) 12.9;                     // 12: bỏ phần lẻ.
(int) Double.NaN;               // 0.
(int) Double.POSITIVE_INFINITY; // Integer.MAX_VALUE.
(int) Double.NEGATIVE_INFINITY; // Integer.MIN_VALUE.
(long) Double.POSITIVE_INFINITY;// Long.MAX_VALUE.
```

Vì vậy, Java không tự ném lỗi khi cast giá trị `double` quá lớn sang `int`. Nếu hợp đồng chỉ cho phép số hữu hạn, trong phạm vi và không có phần lẻ, hãy kiểm tra **trước khi cast**:

```java
static int doubleToIntExact(double value) {
    if (!Double.isFinite(value)
            || value < Integer.MIN_VALUE
            || value > Integer.MAX_VALUE
            || value != Math.rint(value)) {
        throw new IllegalArgumentException("not an exact int: " + value);
    }
    return (int) value;
}
```

Đây là phương thức minh họa cần đặt trong class. `Math.rint(value)` trả số nguyên dạng `double` gần nhất, nhưng điều kiện `value != Math.rint(value)` trong đoạn này dùng để xác nhận **không có phần lẻ**. Nó không tự đảm bảo giá trị `double` đến từ nguồn thập phân ban đầu hoàn toàn chính xác.

Chuyển ngược từ `long` sang `double` cũng có thể mất độ chính xác mà không ném lỗi. Ví dụ `2^53 + 1` không thể biểu diễn chính xác dưới dạng `double`:

```java
long original = 9_007_199_254_740_993L;
double approximate = original; // Làm tròn thành 9007199254740992.0.
```

**Không dùng `(long) approximate == original` như kiểm chứng tổng quát** cho `long → double`: khi cast `double` lớn ngược lại về `long` có cơ chế bão hòa và giá trị khác có thể cho kết quả đánh lừa. Nếu hợp đồng đòi số nguyên chính xác, giữ ở `long`/`BigInteger`, hoặc dùng mô hình decimal phù hợp trước khi đi qua `double`.

### Tình huống JSON/JavaScript

Số nguyên `long` ở Java có thể vượt miền integer an toàn của JavaScript `Number` (`2^53 - 1`). Nếu truyền `long` lớn dưới dạng JSON number rồi đọc bằng JavaScript, độ chính xác có thể đã mất **trước khi Java nhận dữ liệu trả lại**. Khi API yêu cầu truyền số nguyên 64 bit chính xác qua client JavaScript, cần thiết kế schema, ví dụ biểu diễn dưới dạng chuỗi thập phân và parse/validate phù hợp ở hai đầu. Thử nghiệm `long` ở backend không đủ để khẳng định round trip JSON an toàn.

## 7. Phân biệt kiểm tra **đầu vào**, **từng phép tính** và **đầu ra**

Cùng một bài toán có thể có ba hợp đồng hợp lý nhưng hành vi rất khác nhau.

### Hợp đồng A: kiểm tra đầu vào, tính trong miền đã chứng minh đủ rộng

Nếu mỗi phần tử là `int` và đang cộng tất cả phần tử của một mảng `int[]` theo `long`, tổng toán học của một mảng như vậy nằm trong miền `long`. Dùng:

```java
long sum = Arrays.stream(values).asLongStream().sum();
```

Với một `IntStream` có thể sinh hơn số phần tử tối đa của một mảng, không tự động suy ra `long` luôn đủ. Cần biết giới hạn số phần tử và độ lớn từng phần tử trong hợp đồng.

### Hợp đồng B: ném lỗi nếu **bất kỳ phép tính trung gian nào** tràn

Dùng vòng lặp tuần tự với `Math.addExact`/`multiplyExact` trong kiểu đã chọn. Ví dụ:

```java
int total = 0;
for (int value : values) {
    total = Math.addExact(total, value);
}
```

Nếu tổng trung gian vượt `int`, ném lỗi tại thời điểm đó. Cách này phù hợp khi chính hợp đồng yêu cầu mọi bước đều nằm trong kiểu tích lũy.

### Hợp đồng C: tính tổng toán học chính xác, chỉ kiểm tra kiểu đầu ra

Tích lũy bằng `long` nếu đủ rộng, hoặc `BigInteger` nếu không thể chứng minh `long` đủ. Sau đó thu hẹp:

```java
BigInteger total = numbers.stream()
        .map(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

int result = total.intValueExact();
```

Mảnh mã này giả định `numbers` là `Stream<Long>`; nó không phải chương trình độc lập. Nhờ `BigInteger`, không có overflow trung gian ở độ rộng 32/64 bit. `intValueExact()` chỉ từ chối khi **tổng cuối** vượt miền `int`.

**Quan trọng:** `Math.toIntExact` đặt ở cuối không giúp sửa những phép toán `int` hoặc `long` đã overflow trước đó. Nó kiểm tra kết quả nó thực sự nhận, chứ không suy ra kết quả toán học từng tồn tại.

## 8. Chương trình Java 17+ hoàn chỉnh để quan sát

Lưu thành tệp **`OverflowCastDemo.java`**. Chương trình chỉ ghi kết quả xác định, bắt ngoại lệ trong các ca kiểm tra để không phụ thuộc nguyên văn thông báo của JDK:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.Arrays;

public class OverflowCastDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        int one = 1;
        long late = (long) (max + one);
        long early = (long) max + one;
        System.out.println("late widen = " + late);
        System.out.println("early widen = " + early);

        try {
            Math.addExact(max, one);
            System.out.println("checked add = valid");
        } catch (ArithmeticException ex) {
            System.out.println("checked add = overflow");
        }

        long beyondInt = (long) max + one;
        System.out.println("narrow cast = " + (int) beyondInt);
        try {
            Math.toIntExact(beyondInt);
            System.out.println("toIntExact = valid");
        } catch (ArithmeticException ex) {
            System.out.println("toIntExact = overflow");
        }

        int left = 50_000;
        int right = 50_000;
        System.out.println("late multiply = " + (long) (left * right));
        System.out.println("early multiply = " + ((long) left * right));

        int[] values = {Integer.MAX_VALUE, 1};
        System.out.println("int sum = " + Arrays.stream(values).sum());
        System.out.println("long sum = "
                + Arrays.stream(values).asLongStream().sum());

        BigInteger beyondLong =
                BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
        System.out.println("BigInteger longValue = " + beyondLong.longValue());
        try {
            beyondLong.longValueExact();
            System.out.println("BigInteger exact = valid");
        } catch (ArithmeticException ex) {
            System.out.println("BigInteger exact = overflow");
        }

        BigDecimal fractional = new BigDecimal("12.5");
        System.out.println("BigDecimal intValue = " + fractional.intValue());
        try {
            fractional.intValueExact();
            System.out.println("BigDecimal exact = valid");
        } catch (ArithmeticException ex) {
            System.out.println("BigDecimal exact = fractional");
        }

        System.out.println("NaN cast = " + (int) Double.NaN);
        System.out.println("infinity cast = "
                + (int) Double.POSITIVE_INFINITY);
    }
}
```

Biên dịch/chạy tại thư mục chứa tệp:

```bash
javac -encoding UTF-8 OverflowCastDemo.java
java OverflowCastDemo
```

Stdout:

```text
late widen = -2147483648
early widen = 2147483648
checked add = overflow
narrow cast = -2147483648
toIntExact = overflow
late multiply = -1794967296
early multiply = 2500000000
int sum = -2147483648
long sum = 2147483648
BigInteger longValue = -9223372036854775808
BigInteger exact = overflow
BigDecimal intValue = 12
BigDecimal exact = fractional
NaN cast = 0
infinity cast = 2147483647
```

Những cặp kết quả cần đối chiếu:

- `late widen` khác `early widen`: phép cộng đã tràn trước cast ở trường hợp đầu.
- `narrow cast` khác `toIntExact`: cast làm mất bit cao, còn exact conversion từ chối.
- `late multiply` khác `early multiply`: kiểu toán hạng quyết định phép nhân.
- `int sum` khác `long sum`: loại bộ tích lũy quyết định an toàn tổng.
- `BigInteger.longValue` khác `longValueExact`: một bên có thể cắt bit, bên kia kiểm tra.
- `BigDecimal.intValue` khác `intValueExact`: một bên có thể bỏ phần lẻ, bên kia từ chối.
- Cast `NaN`/vô cực sang `int` không phát sinh ngoại lệ.

## 9. Kiểm thử biên theo từng thời điểm thất bại

Để phát hiện lỗi thật thay vì chỉ kiểm tra “kết quả có vẻ hợp lý”, cần thiết kế ca kiểm thử đúng điểm dữ liệu có thể mất.

| Tình huống | Biểu thức/giá trị | Kết quả cần khẳng định |
| --- | --- | --- |
| Cộng tại biên trên `int` | `Integer.MAX_VALUE + 1` | `+` wrap; `Math.addExact` ném |
| Cộng tại biên dưới `int` | `Integer.MIN_VALUE - 1` | `-` wrap; `Math.subtractExact` ném |
| Nhân vượt `int` | `50_000 * 50_000` | `int` sai; nâng toán hạng thành `long` trước nhân |
| Nâng kiểu quá muộn | `(long) (max + 1)` | Kết quả âm đã bị tràn |
| Nâng kiểu đúng lúc | `(long) max + 1` | 2.147.483.648 |
| Thu hẹp ở biên trên | `(int) 2_147_483_648L` | Giá trị âm; `Math.toIntExact` ném |
| Thu hẹp hợp lệ | `Math.toIntExact(2_147_483_647L)` | Trả `Integer.MAX_VALUE` |
| Thu hẹp biên dưới | `Math.toIntExact(-2_147_483_649L)` | Ném |
| `BigInteger` vượt `long` | `Long.MAX_VALUE + 1` theo `BigInteger` | `longValueExact()` ném |
| Decimal có phần lẻ | `new BigDecimal("12.5")` | `intValue()` cắt; `intValueExact()` ném |
| `double` không hữu hạn | `NaN`, `+Infinity` | Cast có quy tắc đặc biệt, API chặt phải từ chối trước |
| Số nguyên lớn sang `double` | `9_007_199_254_740_993L` | Có thể mất độ chính xác |

### Một helper kiểm tra chuyển `int` sang `byte`

```java
static byte toByteExact(int input) {
    if (input < Byte.MIN_VALUE || input > Byte.MAX_VALUE) {
        throw new ArithmeticException("byte range exceeded");
    }
    return (byte) input;
}
```

Kiểm tra `127` thành công; `128`, `-129` bị từ chối. Nếu cast trước rồi mới kiểm tra `byte`, điều kiện về miền `byte` luôn đúng vì biến đã có kiểu `byte`.

### Một helper kiểm tra nhân và thu hẹp có chủ đích

```java
static int multiplyThenNarrow(int a, int b) {
    long product = (long) a * b;
    return Math.toIntExact(product);
}
```

Phương thức này tính sản phẩm hai `int` trong `long`, sau đó chỉ trả về `int` nếu sản phẩm cuối vừa kiểu. Với hai đối số `int`, tích toán học luôn nằm trong `long`, nên đây là lựa chọn phù hợp khi **chỉ cần kiểm tra kết quả cuối của phép nhân**. Nó không khác `Math.multiplyExact(a, b)` về việc chấp nhận hay từ chối khi chỉ có một phép nhân `int * int`, nhưng mô tả rõ ý tưởng “mở rộng rồi thu hẹp”.

Hai helper trên là **mã minh họa**, đặt trong một class để biên dịch.

## 10. Chẩn đoán lỗi đã xảy ra trong hệ thống

Nếu gặp số âm bất thường, tổng giảm khi thêm phần tử dương, hoặc chuyển kiểu ra giá trị lạ, nên quan sát tại **mỗi ranh giới số học**:

1. **Ghi nhận kiểu thực của toán hạng:** `int`, `long`, `BigInteger`, `BigDecimal`, `double`? Biểu thức trong lambda trả kiểu gì?
2. **Xác định phép tính mất dữ liệu đầu tiên:** trước cast hay tại cast? Xét cả phép nhân, cộng, trừ, dịch bit và tổng hợp.
3. **Tái hiện bằng giá trị ở biên:** `MAX_VALUE`, `MIN_VALUE`, `MAX_VALUE + 1` bằng kiểu rộng hơn, giá trị âm, giá trị có phần thập phân.
4. **Thay thế bằng phép kiểm tra chính xác ở đúng điểm:** `Math.addExact`, `Math.multiplyExact`, `Math.toIntExact`, `BigInteger.longValueExact`, `BigDecimal.intValueExact`.
5. **Xác định lại hợp đồng:** muốn lỗi khi trung gian tràn, hay chỉ khi kết quả cuối không vừa kiểu? Có cho phép làm tròn/cắt phần lẻ hay không?
6. **Kiểm tra các tầng lưu trữ/truyền tải:** kiểu cột SQL, JSON number qua JavaScript, parse từ chuỗi, API client. Một giá trị có thể đã mất chính xác trước khi vào phương thức đang debug.

Ví dụ, khi debug một mapping DTO có câu lệnh `(int) order.getTotalCents()`, hãy tìm kiểu `getTotalCents()` và miền giá trị thực tế. Nếu trả `long`, đổi sang `Math.toIntExact` sẽ làm lỗi lộ ra ngay tại ranh giới thay vì đưa một giá trị âm vào bộ phận phía sau. Nhưng nếu `getTotalCents()` đã tính bằng phép nhân `int * int` bị tràn, trước tiên phải sửa phép nhân ở nơi tạo giá trị.

**Log hữu ích** cần có giá trị đầu vào (trong giới hạn bảo mật), kiểu và đơn vị, tên phép tính, cùng tên trường đích; tránh chỉ ghi “invalid number” không đủ ngữ cảnh. Với luồng quan trọng, hãy kiểm thử kết quả số học chính xác so với `BigInteger` hoặc `BigDecimal` làm oracle, thay vì dùng chính phép tính nguyên thủy có thể tràn làm expected value.

## 11. Các lỗi thường gặp

- **“Gán sang `long` thì sẽ an toàn”**: sai nếu toán hạng của phép cộng/nhân vẫn đều là `int`.
- **“Cast sang `int` sẽ tự cảnh báo”**: sai; cast từ `long` sang `int` có thể cắt bit.
- **“Sau cast, giá trị vẫn trong miền `int` nên không overflow”**: điều hiển nhiên về kiểu của biến không chứng minh miền của giá trị trước cast.
- **“`Math.toIntExact` ở cuối đủ phát hiện mọi phép cộng sai”**: nó chỉ kiểm tra đối số `long` nhận được; không truy được overflow trước đó.
- **“`BigInteger.longValue()` giống `longValueExact()`”**: không; phương thức không có `Exact` có thể mất các bit cao.
- **“`BigDecimal.intValue()` luôn là chuyển đổi hợp lệ”**: nó có thể bỏ phần thập phân và mất giá trị ngoài miền.
- **“`(int) Double.NaN` phải ném exception”**: cast trả 0 theo quy tắc Java.
- **“Mọi `long` chuyển sang `double` đều chính xác”**: sai với các số lớn không biểu diễn được trong binary64.
- **“Kiểm thử vài số nhỏ là đủ”**: các lỗi chỉ lộ ở `MAX_VALUE`, `MIN_VALUE`, giá trị ngoài biên và phép tính trung gian.
- **“Dữ liệu sai có thể sửa bằng cast thêm một lần nữa”**: khi phép toán trước đã quấn vòng hoặc bị làm tròn, cast không phục hồi thông tin đã mất.

## 12. Quy tắc thực hành

Khi thiết kế hoặc kiểm thử phép tính số nguyên, hãy xác định miền tổng toán học **trước khi viết biểu thức**. Nếu kiểu nguyên thủy đủ, dùng kiểu đó và kiểm tra các phép tính nguy cơ tràn bằng `Math.*Exact` theo hợp đồng. Nếu kiểu hiện tại quá hẹp, nâng toán hạng **trước phép tính**. Nếu phải chuyển về kiểu nhỏ, dùng exact conversion hoặc kiểm tra giới hạn **trước cast**. Nếu tổng cuối vượt `long`, dùng `BigInteger`; nếu giá trị có phần thập phân, xác định rõ được làm tròn hay phải giữ chính xác trước khi chuyển sang số nguyên.

Một phép kiểm tra được đặt đúng thời điểm giữ cho lỗi xuất hiện ở nguồn gây ra. Một phép kiểm tra quá muộn chỉ kiểm tra **giá trị đã bị biến đổi**, không thể chứng minh kết quả ban đầu còn đúng.

### Tài liệu Java chính thức

- [JLS §5.1 — Primitive conversions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1)
- [JLS §15.18 — Additive operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.18)
- [`Math` — `addExact`, `multiplyExact`, `toIntExact`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [`BigInteger` — exact conversion](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html)
- [`BigDecimal` — exact conversion](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
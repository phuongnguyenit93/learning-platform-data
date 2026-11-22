# nextDown và các giá trị số thực liền kề trong Java 8

## 1. Khi “nhỏ hơn một chút” không có nghĩa trừ một epsilon bất kỳ

Trong tính toán số thực, một câu hỏi tưởng đơn giản là: **“Số `double` lớn nhất nhưng vẫn nhỏ hơn 1.0 là số nào?”** Nếu tự viết `1.0 - 0.000001`, ta chỉ tìm được một số nhỏ hơn 1.0, không chứng minh đó là **giá trị biểu diễn gần 1.0 nhất**. Trừ một lượng quá nhỏ còn có thể không làm thay đổi giá trị do làm tròn dấu chấm động.

Java cung cấp:

```java
double previous = Math.nextDown(1.0d);
// 0.9999999999999999

float previousFloat = Math.nextDown(1.0f);
// 0.99999994
```

`Math.nextDown(x)` trả về **giá trị dấu chấm động liền kề với x theo hướng âm vô cực** (*negative infinity*), xét tập các giá trị mà **kiểu đầu vào** biểu diễn được. Nó không phải một phép trừ theo bước cố định, không tự chuyển `float` thành `double` rồi trả kết quả `double`, và không phải công cụ làm tròn tiền tệ.

Bài học **“nextDown và các giá trị số thực liền kề”** thuộc nhóm **Số học**, module **Java 8**, bao gồm: cách biểu diễn số dấu chấm động, hai overload của `nextDown`, `nextUp`/`nextAfter`/`ulp`, tính bất đối xứng tại lũy thừa của hai, giá trị subnormal, hai số 0 có dấu, NaN/vô cực, kiểm tra ranh giới khoảng số, vấn đề so sánh/tính chính xác, những lỗi hay gặp và bài tập. **Bảy chương trình Java độc lập** trong bài đã được biên dịch với `javac --release 8` và chạy đối chiếu stdout. Tất cả API đều còn hữu ích trên JDK hiện đại, không dựa trên API nội bộ hoặc cách làm đã legacy.

**Ý chính:** `nextDown(x)` thực hiện **một bước trong lưới giá trị `float` hoặc `double` có thể biểu diễn**, đi về phía số nhỏ hơn. Kích thước bước thay đổi theo độ lớn của x, và các trường hợp đặc biệt phải được xử lý bằng ngữ nghĩa IEEE 754 của Java.

## 2. Hai overload của Math.nextDown

Java 8 có hai phương thức cùng tên:

```java
public static double nextDown(double d)
public static float  nextDown(float f)
```

Ví dụ:

```java
double d = Math.nextDown(1.0);  // double
float  f = Math.nextDown(1.0f); // float
```

Điểm quan trọng là **hậu tố literal `f`**:

- `1.0` là literal kiểu `double`; lời gọi nhận/trả `double`.
- `1.0f` là literal kiểu `float`; lời gọi nhận/trả `float`.
- Nếu ép `float` sang `double` rồi gọi `nextDown`, bạn đang bước trên **lưới double**, không phải trên lưới float.
- Không thể lấy một bước `nextDown(double)` rồi ép về float và tự cho rằng đó là `nextDown(float)`. Số double liền trước có thể làm tròn về đúng giá trị float ban đầu.

Sự khác nhau xuất phát từ **độ chính xác biểu diễn**:

| Kiểu | Độ rộng | Significand chính xác | Ví dụ giá trị liền dưới 1 |
| --- | --- | --- | --- |
| `float` | 32 bit | 24 bit độ chính xác nhị phân (kể cả bit ẩn của số normal) | `0.99999994` |
| `double` | 64 bit | 53 bit độ chính xác nhị phân (kể cả bit ẩn của số normal) | `0.9999999999999999` |

Với số bình thường (*normal*) cùng bậc độ lớn, `double` có các bước nhỏ hơn `float` rất nhiều.

### Mô hình tập số có thể biểu diễn

IEEE 754 binary32/binary64 chỉ biểu diễn **một tập hữu hạn các giá trị hữu hạn** và các giá trị đặc biệt. Trong khoảng giữa hai giá trị kề nhau không có một giá trị khác **thuộc chính kiểu đó**, dù trên trục số thực toán học vẫn có vô số số.

Hình dung:

```text
... ---- previous ---- x ---- next ---- ...
         ^             ^       ^
      nextDown(x)       x    nextUp(x)
```

Các khoảng cách trong sơ đồ không phải lúc nào cũng bằng nhau. Đặc biệt tại ranh giới giữa các bậc nhị phân, bước sang trái và sang phải có thể khác độ dài.

## 3. Hợp đồng chính xác của nextDown

Theo Java SE 8 API, `Math.nextDown(double d)` và `Math.nextDown(float f)` trả **giá trị biểu diễn liền kề theo hướng âm vô cực**. Ngữ nghĩa tương đương với:

```java
Math.nextAfter(d, Double.NEGATIVE_INFINITY);
Math.nextAfter(f, Float.NEGATIVE_INFINITY);
```

Tuy nhiên, các phương thức riêng `nextDown` được thiết kế để diễn đạt rõ hướng đi và có thể được hiện thực tối ưu hơn lời gọi `nextAfter` tương đương.

Các trường hợp đặc biệt:

| Đầu vào `double x` | `Math.nextDown(x)` |
| --- | --- |
| `1.0` | `0.9999999999999999` |
| `0.0` | `-Double.MIN_VALUE` |
| `-0.0` | `-Double.MIN_VALUE` |
| `Double.MIN_VALUE` | `+0.0` |
| `-Double.MIN_VALUE` | `-2.0 * Double.MIN_VALUE` |
| `Double.MIN_NORMAL` | Số subnormal dương lớn nhất |
| `Double.POSITIVE_INFINITY` | `Double.MAX_VALUE` |
| `Double.NEGATIVE_INFINITY` | `Double.NEGATIVE_INFINITY` (không còn số nhỏ hơn) |
| `-Double.MAX_VALUE` | `Double.NEGATIVE_INFINITY` |
| `Double.NaN` | `NaN` |

Bảng trên được trình bày theo ngữ nghĩa số học và các biểu diễn đặc biệt của Java. Hai số 0 có dấu sẽ được phân tích riêng vì cách so sánh `==` và cách biểu diễn bit cho kết quả khác nhau.

**Không cộng/trừ epsilon tùy chọn.** Muốn “giá trị `double` ngay dưới 1.0”, `nextDown(1.0d)` đúng nghĩa hơn `1.0 - 1e-12` hay `1.0 - Double.MIN_VALUE` (lượng cuối quá nhỏ và phép trừ có thể làm tròn về 1.0).

## 4. Ví dụ Java 8 số 1 — một bước dưới và trên 1.0

Tệp **`NextDownBasicsDemo.java`** in kết quả thập phân, dạng thập lục phân của số thực nhị phân và độ dài các bước cạnh 1.0. Đồng thời nó xác nhận hai giá trị kề nhau qua raw bits đối với **riêng dãy số dương gần 1.0**.

```java
public class NextDownBasicsDemo {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        double one = 1.0;
        double down = Math.nextDown(one);
        double up = Math.nextUp(one);

        check(down < one && up > one, "ordering");
        check(Math.nextUp(down) == one, "adjacent below");
        check(Math.nextDown(up) == one, "adjacent above");

        check(Double.doubleToRawLongBits(one)
              - Double.doubleToRawLongBits(down) == 1L,
              "one raw representation step below");
        check(Double.doubleToRawLongBits(up)
              - Double.doubleToRawLongBits(one) == 1L,
              "one raw representation step above");

        System.out.println("down1=" + down);
        System.out.println("up1=" + up);
        System.out.println("hexDown=" + Double.toHexString(down));
        System.out.println("hexOne=" + Double.toHexString(one));
        System.out.println("hexUp=" + Double.toHexString(up));
        System.out.println("ulpOne=" + Math.ulp(one));
        System.out.println("deltaBelow=" + (one - down));
        System.out.println("deltaAbove=" + (up - one));
        System.out.println("adjacentRawBits=true");
        System.out.println("PASS");
    }
}
```

Biên dịch/chạy trên JDK 8:

```bash
javac -encoding UTF-8 NextDownBasicsDemo.java
java NextDownBasicsDemo
```

Trên JDK hiện đại, có thể bắt buộc mức API Java 8:

```bash
javac --release 8 -encoding UTF-8 NextDownBasicsDemo.java
java NextDownBasicsDemo
```

**Stdout đã kiểm chứng:**

```text
down1=0.9999999999999999
up1=1.0000000000000002
hexDown=0x1.fffffffffffffp-1
hexOne=0x1.0p0
hexUp=0x1.0000000000001p0
ulpOne=2.220446049250313E-16
deltaBelow=1.1102230246251565E-16
deltaAbove=2.220446049250313E-16
adjacentRawBits=true
PASS
```

**Giải thích:**

1. Số liền dưới 1.0 là `0.9999999999999999`, số liền trên là `1.0000000000000002`.
2. `Double.toHexString` hiển thị dạng nhị phân-base-16: `1.0` ở một ranh giới exponent, giá trị dưới nó có significand gần 2 và exponent nhỏ hơn một.
3. `Math.ulp(1.0)` trả độ dài một ULP của 1.0 theo định nghĩa API, ở đây bằng khoảng bước **phía trên** 1.0.
4. `1.0 - nextDown(1.0)` chỉ bằng **một nửa** `Math.ulp(1.0)` vì 1.0 nằm tại biên giữa hai binade.
5. Kiểm raw-bit chênh 1 chỉ được dùng cho số dương normal gần 1.0 trong ví dụ, **không** phải công thức thay nextDown cho mọi dấu, số 0, vô cực hay NaN.
6. `Math.nextUp(Math.nextDown(1.0)) == 1.0` và ngược lại là invariant đúng ở vị trí hữu hạn này.

## 5. ULP và vì sao khoảng cách số thực không cố định

`ULP` là *unit in the last place*. Trong Java, `Math.ulp(x)` trả một độ lớn bước dương theo định nghĩa của API đối với `x` (các giá trị NaN/vô cực có trường hợp riêng). Một hiểu nhầm phổ biến là:

> “Cứ lấy `x - Math.ulp(x)` sẽ luôn ra `Math.nextDown(x)`.”

**Không đúng ở mọi x.** Ngay tại `x = 1.0`, ta vừa đo được:

```text
Math.ulp(1.0)                    = 2.220446049250313E-16
1.0 - Math.nextDown(1.0)         = 1.1102230246251565E-16
Math.nextUp(1.0) - 1.0           = 2.220446049250313E-16
```

Bước sang trái bằng **nửa** bước sang phải. Lý do: các lũy thừa chính xác của 2 thường là ranh giới giữa các khoảng exponent của kiểu nhị phân. Ngược lại, ở những vùng khác của cùng một binade, khoảng cách giữa các số normal liền kề thường giống nhau.

### Khoảng cách thay đổi theo độ lớn

Gần các giá trị lớn, số biểu diễn cách nhau nhiều hơn trên trục số thực; gần 0, có các giá trị rất nhỏ thuộc vùng subnormal.

```text
Gần 1.0:       bước cỡ 10^-16 cho double
Gần 10^16:     bước cỡ đơn vị hoặc nhiều đơn vị
Gần 0:         có subnormal, bước Double.MIN_VALUE
```

Các dòng trên chỉ là **minh họa cấp độ**, không phải bảng ULP chính xác cho mọi số. Kích thước từng bước phụ thuộc exponent và chế độ biểu diễn normal/subnormal.

Vì vậy:

- Không chọn một epsilon tuyệt đối duy nhất để so sánh mọi giá trị từ rất nhỏ đến rất lớn.
- Khi cần đúng **một giá trị kề**, dùng `nextDown`/`nextUp`.
- Khi cần thước đo độ phân giải cục bộ, có thể dùng `Math.ulp` nhưng phải hiểu bất đối xứng quanh lũy thừa của hai.
- Khi cần tính toán decimal chính xác, chọn `BigDecimal` với biểu diễn từ chuỗi và quy tắc làm tròn rõ ràng.

## 6. Signed zero: +0.0 và -0.0 có hai bit pattern, nhưng so sánh == bằng nhau

Java `double` và `float` có **hai số 0 có dấu** theo IEEE 754:

```java
double plusZero = +0.0d;
double minusZero = -0.0d;

System.out.println(plusZero == minusZero); // true
System.out.println(Double.compare(minusZero, plusZero)); // -1
```

Dù `==` coi chúng bằng nhau về giá trị số, raw bits khác nhau và `Double.compare(-0.0,+0.0)` phân biệt theo thứ tự tổng quát mà lớp Double cung cấp.

### nextDown(0.0) có trả -0.0 không?

**Không.** Theo Java SE 8 `Math.nextDown`:

```text
Math.nextDown(+0.0d) -> -Double.MIN_VALUE
Math.nextDown(-0.0d) -> -Double.MIN_VALUE
```

Vì `-Double.MIN_VALUE` là **số âm hữu hạn nhỏ nhất về độ lớn** trong double, tức số âm khác 0 gần 0 nhất.

Nếu muốn một dấu 0 âm từ 0 dương, việc thay dấu hoặc dùng `Math.copySign(0.0,-1.0)` có ngữ nghĩa khác, **không phải** cùng operation nextDown. Ngoài ra, `Math.nextAfter(+0.0,-0.0)` trả `-0.0` vì hai toán hạng so sánh bằng nhau và nextAfter trả **direction** trong trường hợp đặc biệt đó. Sẽ có ví dụ riêng.

## 7. Subnormal: vùng giữa 0 và số normal dương nhỏ nhất

Các tên dễ gây nhầm:

- `Double.MIN_VALUE` là **số dương double khác 0 nhỏ nhất**, một số **subnormal**, xấp xỉ `4.9E-324`.
- `Double.MIN_NORMAL` là **số double normal dương nhỏ nhất**, xấp xỉ `2.2250738585072014E-308`.
- `Double.MAX_VALUE` là số **hữu hạn dương lớn nhất**, không phải vô cực.
- `Double.NEGATIVE_INFINITY` và `Double.POSITIVE_INFINITY` là những giá trị đặc biệt vượt ngoài tập số hữu hạn.

Đặc biệt:

```text
Math.nextDown(Double.MIN_VALUE)    -> +0.0
Math.nextUp(-Double.MIN_VALUE)     -> -0.0
Math.nextDown(Double.MIN_NORMAL)   -> subnormal dương lớn nhất
Math.nextDown(-Double.MIN_VALUE)   -> -2 * Double.MIN_VALUE
```

**Đừng suy rằng MIN_VALUE là giá trị âm nhỏ nhất** vì trong một số kiểu khác (như Integer.MIN_VALUE) tên MIN_VALUE có nghĩa giá trị nhỏ nhất theo thứ tự số. Với `Double.MIN_VALUE` và `Float.MIN_VALUE`, đó lại là số **dương khác 0 nhỏ nhất**.

### Tại ranh giới normal/subnormal

`Double.toHexString(Math.nextDown(Double.MIN_NORMAL))` cho:

```text
0x0.fffffffffffffp-1022
```

Đây là giá trị subnormal dương lớn nhất. Ngược lại, `Math.nextUp` của giá trị này trở về `Double.MIN_NORMAL`. Các giá trị liền kề quanh ranh giới này được thiết kế theo chuẩn số dấu chấm động.

## 8. Ví dụ Java 8 số 2 — hai số 0 có dấu và subnormal

Tệp **`SignedZeroSubnormalDemo.java`** kiểm raw bits để phân biệt +0.0 và -0.0, đồng thời dùng toHexString xác minh điểm cuối của vùng subnormal.

```java
public class SignedZeroSubnormalDemo {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        double downPlusZero = Math.nextDown(+0.0);
        double downMinusZero = Math.nextDown(-0.0);
        double downMinPositive =
            Math.nextDown(Double.MIN_VALUE);
        double upMinNegative =
            Math.nextUp(-Double.MIN_VALUE);
        double belowMinNormal =
            Math.nextDown(Double.MIN_NORMAL);

        check(downPlusZero == -Double.MIN_VALUE,
              "positive zero");
        check(downMinusZero == -Double.MIN_VALUE,
              "negative zero");
        check(Double.doubleToRawLongBits(downMinPositive)
              == Double.doubleToRawLongBits(+0.0),
              "positive zero result");
        check(Double.doubleToRawLongBits(upMinNegative)
              == Double.doubleToRawLongBits(-0.0),
              "negative zero result");
        check(Double.toHexString(belowMinNormal)
              .equals("0x0.fffffffffffffp-1022"),
              "last subnormal");
        check(-0.0 == +0.0,
              "== compares zeros equal");
        check(Double.doubleToRawLongBits(-0.0)
              != Double.doubleToRawLongBits(+0.0),
              "different signed zero representations");

        System.out.println("downPositiveZero=" + downPlusZero);
        System.out.println("downNegativeZero=" + downMinusZero);
        System.out.println("downSmallestPositive="
            + downMinPositive);
        System.out.println("upSmallestNegative="
            + upMinNegative);
        System.out.println("bothZeroCompareEqual=true");
        System.out.println("signedZeroDistinctBits=true");
        System.out.println("downMinNormalHex="
            + Double.toHexString(belowMinNormal));
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 SignedZeroSubnormalDemo.java
java SignedZeroSubnormalDemo
```

**Stdout đã kiểm chứng:**

```text
downPositiveZero=-4.9E-324
downNegativeZero=-4.9E-324
downSmallestPositive=0.0
upSmallestNegative=-0.0
bothZeroCompareEqual=true
signedZeroDistinctBits=true
downMinNormalHex=0x0.fffffffffffffp-1022
PASS
```

**Lý giải:**

1. Bước từ 0 về phía số nhỏ hơn đi đến `-Double.MIN_VALUE`, không dừng ở -0.0.
2. Bước từ dương subnormal nhỏ nhất đi xuống cho `+0.0`.
3. Bước từ âm subnormal gần 0 nhất đi lên cho `-0.0`.
4. So sánh `-0.0 == +0.0` cho true; so sánh raw bits cho thấy hai biểu diễn khác nhau.
5. Số ngay dưới `Double.MIN_NORMAL` là số subnormal lớn nhất, được thể hiện bằng dạng hex.
6. Không tự làm mất dấu zero khi yêu cầu kiểm tra bit chính xác, serialization nhị phân hoặc numerical algorithm có phụ thuộc dấu.

## 9. float và double: cùng hàm, khác lưới giá trị

`float` có độ chính xác thấp hơn và vùng exponent hẹp hơn `double`. Vì thế:

```java
float f = Math.nextDown(1.0f);
double d = Math.nextDown(1.0d);
```

cho hai con số khác nhau:

```text
float  -> 0.99999994
double -> 0.9999999999999999
```

Một bẫy phổ biến:

```java
float x = 1.0f;
float wrongIdea = (float) Math.nextDown((double) x);
```

Số `double` ngay dưới 1.0 quá gần 1.0 so với độ phân giải float; ép trở lại float có thể làm tròn thành **chính 1.0f**, trong khi `Math.nextDown(1.0f)` thực sự giảm xuống 0.99999994f.

**Quy tắc:** khi thuật toán cần tìm phần tử liền trước của kiểu `float`, hãy gọi overload `float`; khi dùng `double`, gọi overload `double`. Không lạm dụng cast giữa hai kiểu nếu ý nghĩa “liền kề” phải chính xác.

## 10. Ví dụ Java 8 số 3 — so sánh độ phân giải float/double

Tệp **`FloatAndDoubleDemo.java`** đối chiếu hai overload, ULP và điểm gần 0 trong float.

```java
public class FloatAndDoubleDemo {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        float below = Math.nextDown(1.0f);
        float above = Math.nextUp(1.0f);
        double belowDouble = Math.nextDown(1.0d);
        float belowZero = Math.nextDown(0.0f);

        check(below < 1.0f && above > 1.0f,
              "float neighbors");
        check(Math.nextUp(below) == 1.0f,
              "float adjacent");
        check(Math.nextDown(above) == 1.0f,
              "float adjacent reverse");
        check(belowDouble < 1.0d,
              "double neighbor");
        check(belowZero == -Float.MIN_VALUE,
              "float zero");
        check(Float.isNaN(Math.nextDown(Float.NaN)),
              "float NaN");

        System.out.println("floatBelowOne=" + below);
        System.out.println("floatAboveOne=" + above);
        System.out.println("floatUlpOne=" + Math.ulp(1.0f));
        System.out.println("floatMinusBelow="
            + (1.0f - below));
        System.out.println("doubleBelowOne=" + belowDouble);
        System.out.println("floatBelowZero=" + belowZero);
        System.out.println("floatNaN=true");
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 FloatAndDoubleDemo.java
java FloatAndDoubleDemo
```

**Stdout đã kiểm chứng:**

```text
floatBelowOne=0.99999994
floatAboveOne=1.0000001
floatUlpOne=1.1920929E-7
floatMinusBelow=5.9604645E-8
doubleBelowOne=0.9999999999999999
floatBelowZero=-1.4E-45
floatNaN=true
PASS
```

Ở 1.0f, bước xuống cũng bằng **nửa** ULP của 1.0f, tương tự tình huống double. Nhưng các bước float lớn hơn rất nhiều. `Float.MIN_VALUE` là số float subnormal dương nhỏ nhất, còn `Double.MIN_VALUE` là số double subnormal dương nhỏ nhất: chúng khác nhau về độ lớn và kiểu.

### Không dùng float để giữ phần tiền có sai số bằng 0

Số thực dấu chấm động dùng nhị phân, nên nhiều phân số thập phân như 0.1 không có biểu diễn hữu hạn chính xác. Chọn `float` chỉ vì tiết kiệm bộ nhớ mà không xem xét sai số/biên độ là rủi ro. Với nghiệp vụ yêu cầu decimal chính xác, ưu tiên số nguyên trong đơn vị nhỏ nhất có kiểm tra tràn số, hoặc `BigDecimal` theo domain.

## 11. NaN và infinities: nextDown không luôn trả số hữu hạn nhỏ hơn

Tưởng tượng một đoạn code:

```java
double previous = Math.nextDown(value);
if (previous < value) {
    // Đã bước được về phía nhỏ hơn.
}
```

Với phần lớn số hữu hạn, check có thể đúng. Nhưng:

- Nếu `value=Double.NaN`, kết quả là NaN. Các toán tử so sánh có thứ tự như `<` và `>` với NaN đều false.
- Nếu `value=Double.NEGATIVE_INFINITY`, kết quả vẫn là âm vô cực. Không có giá trị double nhỏ hơn nó.
- Nếu `value=Double.POSITIVE_INFINITY`, bước xuống đưa đến `Double.MAX_VALUE`, số hữu hạn dương lớn nhất.
- Nếu `value=-Double.MAX_VALUE`, bước xuống đưa đến `Double.NEGATIVE_INFINITY`. Kết quả không còn hữu hạn.

Do đó một thuật toán đòi “giá trị hữu hạn liền dưới” phải **xác nhận điều kiện đầu vào** và các trường hợp biên. Không tự giả định `nextDown(x)` luôn hữu hạn khi x hữu hạn.

### Kiểm tra giá trị đặc biệt đúng cách

Java 8 cung cấp:

```java
Double.isNaN(x);
Double.isInfinite(x);
Double.isFinite(x);

Float.isNaN(f);
Float.isInfinite(f);
Float.isFinite(f);
```

Đừng kiểm NaN bằng `x == Double.NaN`: biểu thức đó luôn false. Hãy dùng `Double.isNaN(x)`. Đừng dùng `Double.isFinite` nếu bài toán của bạn thực sự muốn cho phép vô cực như một sentinel; khi đó cần một contract biên rõ ràng riêng.

## 12. Ví dụ Java 8 số 4 — NaN, ±Infinity và giới hạn hữu hạn

Tệp **`SpecialValuesDemo.java`** thử những trường hợp không thể suy ra chỉ bằng “trừ một chút”.

```java
public class SpecialValuesDemo {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        double downPositiveInfinity =
            Math.nextDown(Double.POSITIVE_INFINITY);
        double downNegativeInfinity =
            Math.nextDown(Double.NEGATIVE_INFINITY);
        double downNegativeMax =
            Math.nextDown(-Double.MAX_VALUE);
        double upPositiveMax =
            Math.nextUp(Double.MAX_VALUE);

        boolean nanStaysNaN =
            Double.isNaN(Math.nextDown(Double.NaN));
        boolean finiteMax =
            Double.isFinite(downPositiveInfinity);

        check(downPositiveInfinity == Double.MAX_VALUE,
              "+infinity");
        check(downNegativeInfinity == Double.NEGATIVE_INFINITY,
              "-infinity");
        check(downNegativeMax == Double.NEGATIVE_INFINITY,
              "-max");
        check(upPositiveMax == Double.POSITIVE_INFINITY,
              "+max");
        check(nanStaysNaN && finiteMax,
              "special cases");

        System.out.println("nextDownPositiveInf="
            + downPositiveInfinity);
        System.out.println("nextDownNegativeInf="
            + downNegativeInfinity);
        System.out.println("nextDownNegMax="
            + downNegativeMax);
        System.out.println("nextUpPositiveMax="
            + upPositiveMax);
        System.out.println("nanStaysNaN=" + nanStaysNaN);
        System.out.println("finiteCheckMax=" + finiteMax);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 SpecialValuesDemo.java
java SpecialValuesDemo
```

**Stdout đã kiểm chứng:**

```text
nextDownPositiveInf=1.7976931348623157E308
nextDownNegativeInf=-Infinity
nextDownNegMax=-Infinity
nextUpPositiveMax=Infinity
nanStaysNaN=true
finiteCheckMax=true
PASS
```

**Bài học:** ở biên dương, bước từ +∞ đi xuống là số dương hữu hạn lớn nhất; ở biên âm, `nextDown(-Double.MAX_VALUE)` đã đi tới -∞. Với input -∞, bước xuống không tiến thêm. Với NaN, kết quả vẫn là NaN. Đặc biệt, **một hàm nextDown không phải bộ lọc bảo đảm kết quả hữu hạn**.

## 13. nextDown, nextUp và nextAfter khác nhau ra sao?

Java SE 8 hỗ trợ ba API liên quan:

| API | Ý nghĩa |
| --- | --- |
| `Math.nextDown(x)` | Giá trị liền kề theo hướng -∞ |
| `Math.nextUp(x)` | Giá trị liền kề theo hướng +∞ |
| `Math.nextAfter(start, direction)` | Giá trị liền kề từ start theo hướng direction, hoặc direction khi hai toán hạng so sánh bằng nhau |

Đối với giá trị thông thường:

```java
Math.nextDown(x) ==
    Math.nextAfter(x, Double.NEGATIVE_INFINITY);
```

Trong hợp đồng API, chúng tương đương về ngữ nghĩa khi gọi đúng overload. `nextAfter` linh hoạt hơn khi hướng là một giá trị tùy ý, không chỉ ±∞.

### nextAfter và hai số 0 có dấu

Một khác biệt dễ bỏ sót là:

```text
Math.nextDown(+0.0)          -> -Double.MIN_VALUE
Math.nextAfter(+0.0, -0.0)   -> -0.0
```

Vì `+0.0` và `-0.0` **so sánh bằng nhau** theo các toán tử dấu chấm động, `nextAfter(start,direction)` có trường hợp trả lại `direction` khi hai đối số so sánh bằng nhau. Đây là **khác nhau về yêu cầu đầu vào**: hướng cố định -∞ không giống hướng chỉ đến -0.0.

Một mối quan hệ khác:

```text
Math.nextAfter(-0.0, +0.0)   -> +0.0
Math.nextDown(-Double.MIN_VALUE) -> -2 * Double.MIN_VALUE
```

Nếu bạn cần phân biệt raw sign bit của zero, hãy dùng `Double.doubleToRawLongBits`/`Double.compare` theo yêu cầu. Không dựa vào toán tử `==` để phân biệt hai zero.

## 14. Ví dụ Java 8 số 5 — nextAfter và dấu của zero

Tệp **`NextAfterDirectionDemo.java`** so sánh nextDown với nextAfter theo hướng âm vô cực, đồng thời kiểm các trường hợp direction bằng ±0.0.

```java
public class NextAfterDirectionDemo {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        double one = 1.0;
        boolean equivalent =
            Math.nextDown(one)
            == Math.nextAfter(
                one, Double.NEGATIVE_INFINITY);

        long minusZeroBits =
            Double.doubleToRawLongBits(-0.0);
        long plusZeroBits =
            Double.doubleToRawLongBits(+0.0);

        boolean towardsMinusZero =
            Double.doubleToRawLongBits(
                Math.nextAfter(+0.0, -0.0))
            == minusZeroBits;
        boolean towardsPlusZero =
            Double.doubleToRawLongBits(
                Math.nextAfter(-0.0, +0.0))
            == plusZeroBits;

        boolean downZeroIsNegativeSubnormal =
            Math.nextDown(+0.0)
            == -Double.MIN_VALUE;
        boolean adjacentBelowNegMin =
            Math.nextDown(-Double.MIN_VALUE)
            == -2.0 * Double.MIN_VALUE;
        boolean sameStartDirection =
            Math.nextAfter(1.0, 1.0) == 1.0;

        check(equivalent, "nextDown versus nextAfter");
        check(towardsMinusZero && towardsPlusZero,
              "signed zero direction");
        check(downZeroIsNegativeSubnormal,
              "zero nextDown");
        check(adjacentBelowNegMin,
              "negative subnormal step");
        check(sameStartDirection,
              "nextAfter equal returns direction");

        System.out.println("downEqualsNextAfter="
            + equivalent);
        System.out.println(
            "nextAfterPosZeroToNegZeroIsNegZero="
            + towardsMinusZero);
        System.out.println(
            "nextAfterNegZeroToPosZeroIsPosZero="
            + towardsPlusZero);
        System.out.println("downOfPosZeroIsNegMin="
            + downZeroIsNegativeSubnormal);
        System.out.println("downOfNegMinIsTwiceNegMin="
            + adjacentBelowNegMin);
        System.out.println("equalDirectionReturnsSame="
            + sameStartDirection);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 NextAfterDirectionDemo.java
java NextAfterDirectionDemo
```

**Stdout đã kiểm chứng:**

```text
downEqualsNextAfter=true
nextAfterPosZeroToNegZeroIsNegZero=true
nextAfterNegZeroToPosZeroIsPosZero=true
downOfPosZeroIsNegMin=true
downOfNegMinIsTwiceNegMin=true
equalDirectionReturnsSame=true
PASS
```

**Diễn giải:** nextDown(1.0) tương đương bước nextAfter(1.0, -∞). Nhưng khi direction là zero có dấu, nextAfter trả đúng zero ở phía đích mà không bước sang subnormal. Về phía số âm, nextDown(-Double.MIN_VALUE) lại đi xa 0 hơn thành -2 lần số subnormal nhỏ nhất.

## 15. Vì sao không tự thao tác bit để thay nextDown?

Kiểu double dùng biểu diễn 64 bit, và cách sắp thứ tự bit đối với số dương normal có thể gợi ý “chỉ giảm raw bits đi 1”. Nhưng cách đó **không đúng tổng quát**:

- Với số dương, bước xuống có thể ứng với raw bits giảm.
- Với số âm, quan hệ giữa raw bits và thứ tự số học có chiều khác; raw-bit manipulation tùy tiện dễ sai.
- Với ±0.0, bit sign gây ra điểm chuyển đặc biệt.
- Với NaN, nhiều payload bit khác nhau không tạo ra một thứ tự số học thông thường.
- Với ±Infinity hoặc ranh giới normal/subnormal, phép tăng/giảm bit thiếu guard có thể sinh giá trị không mong muốn.
- Với kiểu float, cấu trúc bit khác và phải dùng `Float.floatToRawIntBits` nếu cần debug, không thể dùng trực tiếp logic double.

**Giải pháp:** dùng `Math.nextDown`/`Math.nextUp` cho thuật toán số; dùng `Double.doubleToRawLongBits` chỉ khi cần kiểm tra biểu diễn, serialization nhị phân hoặc bit-level debugging.

### Dạng hex để đọc chính xác

`Double.toHexString(x)` mô tả giá trị dấu chấm động dưới dạng hex exponent, tránh phải đoán từ chuỗi thập phân ngắn:

```text
Math.nextDown(1.0) = 0x1.fffffffffffffp-1
1.0                = 0x1.0p0
Math.nextUp(1.0)   = 0x1.0000000000001p0
```

Đây là ba giá trị kề nhau trong double. Biểu diễn hex hữu ích cho test chính xác, nhưng không phải định dạng mà người dùng thông thường cần xem trên giao diện.

## 16. Dùng nextDown để xác định biên trên *exclusive* khi thật sự cần

Một ứng dụng kỹ thuật của nextDown là tìm giá trị `double` hữu hạn lớn nhất dưới một ngưỡng `high` **đã được biểu diễn chính xác dưới dạng double**.

Ví dụ khoảng:

```text
[0.0, 1.0)
```

có nghĩa các giá trị cho phép gồm 0.0 và những số nhỏ hơn 1.0, **không gồm 1.0**. Trong lưới double, giá trị lớn nhất vẫn thỏa `x < 1.0` là:

```java
double high = 1.0;
double last = Math.nextDown(high);
// 0.9999999999999999
```

Nếu bạn có một bộ dữ liệu chỉ chứa **double hữu hạn** và cần hiển thị “giá trị double cuối cùng dưới 1”, nextDown là thao tác thích hợp.

Tuy nhiên, trong code nghiệp vụ:

```java
boolean allowed = x < high;
```

thường **rõ nghĩa và an toàn hơn** so với biến đổi mọi biên exclusive sang inclusive rồi so sánh `x <= Math.nextDown(high)`, vì còn NaN, ±0.0, infinity, tập input không phải double, các kiểu hỗn hợp và những ràng buộc nghiệp vụ khác. Dùng toán tử `<` để diễn đạt khoảng nửa mở nếu đó chính là ý định.

### Khi nào không được tự ý dùng nextDown?

- Nếu `high = Double.NaN`, nextDown(high) vẫn NaN, không có một upper bound hợp lệ theo thứ tự số thực.
- Nếu `high = Double.NEGATIVE_INFINITY`, nextDown(high) vẫn -∞, không tạo ra số hữu hạn nhỏ hơn upper bound.
- Nếu `high` thuộc một domain decimal khác, `nextDown` của bản double gần nhất không thể tạo ra “bước decimal nhỏ nhất” một cách tổng quát.
- Nếu dữ liệu gồm `BigDecimal`, giới hạn nên theo `BigDecimal.compareTo` và quy tắc scale/precision của domain.
- Nếu dùng `float` thì upper bound liền dưới phải được tìm bằng overload float, không phải double.
- Nếu bài toán chấp nhận ±∞ làm sentinel, phải định nghĩa rõ semantics; không áp mẫu finite-only một cách máy móc.

## 17. Ví dụ Java 8 số 6 — khoảng nửa mở và điểm ngay dưới biên

Tệp **`ExclusiveUpperBoundDemo.java`** dùng biểu thức khoảng `[low, high)`, chủ động chỉ chấp nhận input và bounds hữu hạn. Đây là **chính sách ví dụ**, không phải ràng buộc bắt buộc của Math.nextDown.

```java
public class ExclusiveUpperBoundDemo {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static boolean inHalfOpenRange(
            double x, double low, double high) {
        return Double.isFinite(x)
            && Double.isFinite(low)
            && Double.isFinite(high)
            && low < high
            && low <= x && x < high;
    }

    public static void main(String[] args) {
        double high = 1.0d;
        double lastBelowHigh = Math.nextDown(high);

        boolean lastIsInside =
            inHalfOpenRange(lastBelowHigh, 0.0, high);
        boolean highExcluded =
            !inHalfOpenRange(high, 0.0, high);
        boolean nanExcluded =
            !inHalfOpenRange(Double.NaN, 0.0, high);
        boolean nextUpReachesHigh =
            Math.nextUp(lastBelowHigh) == high;
        boolean unsupportedBound =
            !inHalfOpenRange(
                Double.NEGATIVE_INFINITY,
                Double.NEGATIVE_INFINITY, 1.0);

        double sum = 0.1 + 0.2;
        boolean roundedSumAboveLiteral =
            sum > 0.3;

        check(lastIsInside && highExcluded && nanExcluded,
              "half-open interval");
        check(nextUpReachesHigh && unsupportedBound,
              "adjacency and invalid data");
        check(roundedSumAboveLiteral, "decimal rounding");

        System.out.println("lastBelowHigh="
            + lastBelowHigh);
        System.out.println("lastIsInside=" + lastIsInside);
        System.out.println("highExcluded=" + highExcluded);
        System.out.println("nanExcluded=" + nanExcluded);
        System.out.println("nextUpReachesHigh="
            + nextUpReachesHigh);
        System.out.println("nonFiniteRejected="
            + unsupportedBound);
        System.out.println("sumOfPointOneAndPointTwo=" + sum);
        System.out.println("sumAboveLiteralPointThree="
            + roundedSumAboveLiteral);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 ExclusiveUpperBoundDemo.java
java ExclusiveUpperBoundDemo
```

**Stdout đã kiểm chứng:**

```text
lastBelowHigh=0.9999999999999999
lastIsInside=true
highExcluded=true
nanExcluded=true
nextUpReachesHigh=true
nonFiniteRejected=true
sumOfPointOneAndPointTwo=0.30000000000000004
sumAboveLiteralPointThree=true
PASS
```

**Giải thích:**

- `lastBelowHigh` là giá trị double lớn nhất nhỏ hơn 1.0.
- Hàm `inHalfOpenRange` định nghĩa khoảng **không gồm cận trên**, trả true cho last và false cho high.
- NaN bị loại chủ động bằng `Double.isFinite`.
- Với phạm vi bài toán ví dụ, mọi bound cũng phải hữu hạn, và `low < high`.
- `Math.nextUp(lastBelowHigh) == high` chứng minh last là láng giềng trực tiếp của high.
- `0.1 + 0.2` cho `0.30000000000000004`, cho thấy không thể coi mọi phép tính decimal trên double là chính xác. Sự chênh lệch đó **không tự chứng minh nextDown là phương pháp sửa mọi sai số decimal**.

## 18. nextDown không phải chiến lược sửa sai số số thực

Có thể gặp tình huống:

```java
double sum = 0.1 + 0.2;
// 0.30000000000000004
```

Lấy `Math.nextDown(sum)` đúng một lần tạo ra giá trị double được in là `0.3`. Điều đó dễ dẫn đến hiểu nhầm:

> “Nếu phép tính double có sai số, chỉ cần nextDown kết quả là sẽ đúng.”

**Đây là lời khuyên sai.** Vì:

1. Lỗi làm tròn có thể hướng **lên hoặc xuống**; nextDown luôn đi về -∞.
2. Mức sai có thể lớn hơn **một ULP**, hoặc tích lũy qua nhiều phép tính.
3. Nếu giá trị ban đầu đã đúng, nextDown sẽ làm nó nhỏ hơn.
4. 0.3 kiểu double vẫn không phải số thập phân 0.3 chính xác về mặt toán học.
5. Quy tắc tiền tệ/đo lường có thể yêu cầu round-to-nearest, HALF_EVEN, HALF_UP hoặc số chữ số thập phân cụ thể, không liên quan “láng giềng double”.
6. Cận biên NaN, infinity và subnormal làm cách “bước một lần” càng không phù hợp làm cơ chế sửa lỗi chung.

Khi làm kế toán/định giá/định lượng thập phân, nên mô hình hóa **từ đầu** bằng `BigDecimal` hoặc số nguyên theo đơn vị nhỏ nhất, và có chính sách làm tròn ở đúng bước nghiệp vụ. Khi dùng số thực trong simulation, tính sai số bằng phương pháp phân tích phù hợp, không che lỗi với nextDown.

## 19. Ví dụ Java 8 số 7 — kết quả double và decimal chính xác

Tệp **`DecimalPrecisionDemo.java`** so sánh phép cộng nhị phân với phép cộng BigDecimal từ các chuỗi decimal. Đây là ví dụ minh họa **khác biệt hai mô hình**, không đề xuất nextDown để làm tròn tiền.

```java
import java.math.BigDecimal;

public class DecimalPrecisionDemo {
    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        double sum = 0.1d + 0.2d;
        double steppedDown = Math.nextDown(sum);

        BigDecimal exactSum =
            new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        BigDecimal decimalRepresentation =
            BigDecimal.valueOf(sum);

        boolean nextDownHitsLiteral =
            steppedDown == 0.3d;
        boolean exactDecimal =
            exactSum.compareTo(
                new BigDecimal("0.3")) == 0;
        boolean roundedDoubleDiffers =
            decimalRepresentation.compareTo(exactSum) > 0;

        check(nextDownHitsLiteral,
              "adjacent representable value");
        check(exactDecimal && roundedDoubleDiffers,
              "decimal distinction");

        System.out.println("doubleSum=" + sum);
        System.out.println("downDoubleSum=" + steppedDown);
        System.out.println("decimalSum=" + exactSum);
        System.out.println("decimalOfDoubleSum="
            + decimalRepresentation);
        System.out.println("downHitsDoublePointThree="
            + nextDownHitsLiteral);
        System.out.println("exactDecimalIsPointThree="
            + exactDecimal);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 DecimalPrecisionDemo.java
java DecimalPrecisionDemo
```

**Stdout đã kiểm chứng:**

```text
doubleSum=0.30000000000000004
downDoubleSum=0.3
decimalSum=0.3
decimalOfDoubleSum=0.30000000000000004
downHitsDoublePointThree=true
exactDecimalIsPointThree=true
PASS
```

**Phân tích:** kết quả cộng double được in `0.30000000000000004`; nextDown cho một giá trị double liền trước, được in là `0.3`; BigDecimal cộng hai decimal literal dưới dạng chuỗi cho **decimal 0.3 chính xác theo scale**. `BigDecimal.valueOf(sum)` dùng biểu diễn thập phân của double đầu vào để tạo BigDecimal, nên khác BigDecimal cộng trực tiếp từ chuỗi.

**Lưu ý khác:** để biểu diễn chính xác *giá trị nhị phân* của double 0.1, `new BigDecimal(0.1)` có thể cho một số thập phân dài hơn rất nhiều; `BigDecimal.valueOf(0.1)` lại dựa trên biểu diễn dạng String của double. Hãy phân biệt nguồn giá trị decimal nghiệp vụ với một số đã đi qua phép tính nhị phân.

## 20. Bước liền kề và thứ tự số học

Đối với các số double hữu hạn không NaN nằm ngoài một vài vị trí đặc biệt, một số tính chất quan trọng:

```text
Math.nextDown(x) < x
Math.nextUp(x) > x
Math.nextUp(Math.nextDown(x)) == x
Math.nextDown(Math.nextUp(x)) == x
```

**Không sao chép các tính chất này thành luật toàn cục thiếu guard.**

- Ở `x = Double.NEGATIVE_INFINITY`, `nextDown(x) == x`.
- Ở `x = Double.POSITIVE_INFINITY`, `nextUp(x) == x`.
- Ở NaN, phép so sánh thứ tự bằng `<` hoặc `>` không đúng như với số hữu hạn.
- Gần số 0 có dấu, các phép toán theo **giá trị số** và kiểm tra **raw bit identity** có thể khác ngữ nghĩa.
- Nếu ép kết quả sang float hoặc một kiểu nguyên, quan hệ láng giềng của double có thể bị mất.

### Nguy cơ vòng lặp không dừng

Đoạn sau là thiết kế rủi ro:

```java
// Pseudocode: KHÔNG CHẠY để tránh vòng lặp dài/vô hạn.
while (true) {
    x = Math.nextDown(x);
}
```

Số bước có thể cực lớn và ở `-Infinity` bước tiếp theo vẫn là `-Infinity`. Nếu bạn cần duyệt một số lượng hữu hạn giá trị kề, hãy dùng **bộ đếm số bước rõ ràng** và xác định điều kiện kết thúc:

```java
// Snippet minh họa, không phải chương trình standalone.
for (int i = 0; i < 5; i++) {
    if (!Double.isFinite(x)) break;
    double down = Math.nextDown(x);
    if (down == x) break;
    x = down;
}
```

Nếu hàm của bạn yêu cầu x luôn hữu hạn, kết quả `down` cũng phải được kiểm trước khi sử dụng ở bước tiếp theo; `Math.nextDown(-Double.MAX_VALUE)` sẽ cho -∞.

### Vấn đề NaN khi dùng toán tử so sánh

`Double.NaN < 1.0`, `Double.NaN > 1.0` và `Double.NaN == 1.0` đều false. Những phương thức như `Double.compare` dùng một thứ tự tổng quát cho mục tiêu sorting, có quy tắc riêng với NaN và signed zero. Vì vậy kết quả sắp xếp theo Double.compare không phải “trục số học thông thường” đối với mọi special value.

Nếu ứng dụng cấm NaN và infinity, **validate đầu vào**, không mong nextDown tự lọc chúng.

## 21. Những công cụ liên quan và khi nào dùng

| Công cụ Java 8 | Chức năng | Khi dùng |
| --- | --- | --- |
| `Math.nextDown(double/float)` | Một giá trị biểu diễn liền trước theo -∞ | Tìm predecessor trong lưới số thực |
| `Math.nextUp(double/float)` | Một giá trị biểu diễn liền sau theo +∞ | Tìm successor |
| `Math.nextAfter(start,direction)` | Bước một giá trị theo hướng bất kỳ | Thuật toán cần target/direction động |
| `Math.ulp(x)` | Độ dài ULP theo API | Phân tích độ phân giải và sai số cục bộ |
| `Math.scalb(x,k)` | Nhân với lũy thừa 2 và làm tròn đúng theo API | Thao tác exponent/scaling nhị phân |
| `Double.toHexString(x)` | Biểu diễn chính xác dạng hex | Gỡ lỗi bit/giá trị dấu chấm động |
| `Double.doubleToRawLongBits(x)` | Lấy raw 64-bit representation | Phân biệt signed zero, debug bit |
| `Float.floatToRawIntBits(f)` | Lấy raw 32-bit representation | Phân biệt bit của float |
| `Double.isFinite/isNaN/isInfinite` | Kiểm loại giá trị | Input validation |
| `Double.compare(a,b)` | Thứ tự tổng quát theo Double | Comparator/sorting (bao gồm NaN/signed zero) |
| `Math.copySign(magnitude,sign)` | Sao chép dấu | Điều khiển dấu, kể cả ±0 theo contract |
| `BigDecimal.compareTo` | So sánh giá trị thập phân | Domain decimal chính xác |
| `StrictMath.nextDown/nextUp` | Phiên bản StrictMath cho láng giềng | Khi API/hợp đồng số học dùng StrictMath |

Các API này **không thay thế trực tiếp** lẫn nhau. Đặc biệt, `ulp` là **độ dài bước**, `nextDown` là **giá trị đầu ra**; nhầm chúng sẽ cho thuật toán sai tại ranh giới exponent.

## 22. Ví dụ sai và cách sửa

### Sai lầm A: trừ Double.MIN_VALUE để “giảm một bước”

```java
// Sai ý nghĩa predecessor tổng quát.
double predecessor = 1.0 - Double.MIN_VALUE;
```

Vì `Double.MIN_VALUE` quá nhỏ so với ULP quanh 1.0, phép trừ được làm tròn về **chính 1.0**.

**Sửa:**

```java
double predecessor = Math.nextDown(1.0);
```

### Sai lầm B: trừ Math.ulp(x) ở mọi giá trị

```java
// Không tương đương nextDown(x) ở mọi x.
double predecessor = x - Math.ulp(x);
```

Ở 1.0, bước sang trái chỉ bằng nửa ULP theo định nghĩa Math.ulp(1.0).

**Sửa:** dùng `Math.nextDown(x)` nếu yêu cầu đúng predecessor.

### Sai lầm C: cast overload double về float

```java
float previous = (float) Math.nextDown((double) 1.0f);
```

Giá trị double predecessor gần 1.0 quá mức mà float có thể phân biệt; cast có thể làm tròn thành 1.0f.

**Sửa:**

```java
float previous = Math.nextDown(1.0f);
```

### Sai lầm D: nghĩ nextDown(0.0) là -0.0

```java
double result = Math.nextDown(0.0);
// -Double.MIN_VALUE, không phải -0.0
```

**Sửa hiểu biết:** nếu yêu cầu signed zero, dùng `-0.0`, `Math.copySign` hoặc `nextAfter(+0.0,-0.0)` theo đúng ý định. Đừng gọi nextDown cho mục tiêu chỉ đổi dấu 0.

### Sai lầm E: nextDown như cách sửa 0.1 + 0.2

```java
// Sai nếu coi là quy tắc xử lý decimal tổng quát.
double corrected = Math.nextDown(a + b);
```

Nó chỉ bước một giá trị về -∞, không áp một quy tắc làm tròn decimal hợp lệ.

**Sửa:** chọn decimal representation và rounding theo domain; hoặc phân tích sai số số thực đúng phương pháp khoa học/kỹ thuật.

### Sai lầm F: dùng Math.nextDown cho tiền với giới hạn số lẻ

Một giá tiền nhỏ hơn 100 đồng thường có bước nhỏ nhất **1 đồng** hoặc **0,01 đơn vị tiền**, không phải một ULP double quanh 100. `nextDown(100.0)` tạo giá trị biểu diễn nhị phân rất sát 100, không phải 99.99 hay 99 đồng.

**Sửa:** dùng `BigDecimal` hoặc integer minor units theo quy tắc nghiệp vụ.

## 23. Khi cần kiểm đúng bit, không chỉ kiểm chuỗi in ra

`Double.toString` chọn biểu diễn thập phân có thể round-trip tới cùng double. Điều này hữu ích nhưng không có nghĩa số decimal được in ra là **giá trị thập phân toán học chính xác của bit pattern**.

Ví dụ `Math.nextDown(1.0)` hiển thị `0.9999999999999999`; biểu diễn hex cho phép xác định vị trí binary chính xác. Nếu cần so sánh bit:

```java
long bits = Double.doubleToRawLongBits(value);
```

Nhưng nếu chỉ cần **điều kiện số học**, dùng `<`/`<=` hoặc `Double.compare` phù hợp với domain. Không lạm dụng raw bits để chứng minh inequality, vì NaN và signed zeros có ngữ nghĩa riêng.

### Kiểm thử số thực cần chú ý gì?

- So sánh exact `==` hợp lý khi kiểm một giá trị IEEE được đặc tả chính xác, như `Math.nextDown(1.0d)` với literal đã biết hoặc raw bits cho signed zero.
- Với phép tính liên quan sai số xấp xỉ, nên dùng tolerance/relative error/ULP budget được xác định từ thuật toán, không tự động dùng `==`.
- Với NaN, dùng `Double.isNaN`.
- Với infinity, dùng `Double.isInfinite` hoặc so với hằng infinity khi phù hợp.
- Với signed zero, dùng raw bits hoặc `Double.compare` tùy mục tiêu.
- Với float, kiểm test theo **float grid**, tránh so với giá trị double tưởng cùng độ phân giải.
- Với subnormal, có thể dùng `Double.toHexString` để in chính xác kết quả.

## 24. Ma trận kiểm thử dành cho nextDown

| Trường hợp | Kỳ vọng |
| --- | --- |
| `nextDown(1.0d)` | `0.9999999999999999` |
| `nextUp(1.0d)` | `1.0000000000000002` |
| `nextUp(nextDown(1.0d))` | `1.0` |
| `nextDown(nextUp(1.0d))` | `1.0` |
| `Math.ulp(1.0)` | `2.220446049250313E-16` |
| `1.0 - nextDown(1.0)` | `1.1102230246251565E-16` |
| `Math.nextDown(1.0f)` | `0.99999994` |
| `Math.nextUp(1.0f)` | `1.0000001` |
| `Math.ulp(1.0f)` | `1.1920929E-7` |
| `nextDown(+0.0d)` | `-Double.MIN_VALUE` |
| `nextDown(-0.0d)` | `-Double.MIN_VALUE` |
| `nextDown(Double.MIN_VALUE)` | `+0.0` (kiểm raw bits) |
| `nextUp(-Double.MIN_VALUE)` | `-0.0` (kiểm raw bits) |
| `nextDown(Double.MIN_NORMAL)` | Subnormal dương lớn nhất |
| `nextDown(-Double.MIN_VALUE)` | `-2.0 * Double.MIN_VALUE` |
| `nextDown(Double.POSITIVE_INFINITY)` | `Double.MAX_VALUE` |
| `nextDown(Double.NEGATIVE_INFINITY)` | `Double.NEGATIVE_INFINITY` |
| `nextDown(-Double.MAX_VALUE)` | `Double.NEGATIVE_INFINITY` |
| `nextDown(Double.NaN)` | `NaN` |
| `nextAfter(+0.0,-0.0)` | `-0.0` |
| `nextAfter(-0.0,+0.0)` | `+0.0` |
| `nextAfter(1.0,1.0)` | `1.0` |
| `Math.nextDown(1.0d) == Math.nextAfter(1.0d,-∞)` | true |
| `Double.isFinite(nextDown(+∞))` | true |
| `Double.isFinite(nextDown(-Double.MAX_VALUE))` | false |
| `Math.nextDown(0.0f)` | `-Float.MIN_VALUE` |
| `Double.compare(-0.0,+0.0) < 0` | true |
| `-0.0 == +0.0` | true |
| `Math.nextDown(0.1+0.2) == 0.3d` | true trong test cụ thể, không phải giải pháp decimal |
| `BigDecimal("0.1")+BigDecimal("0.2")` | Decimal 0.3 chính xác |

Một test đúng cần kiểm **ngữ nghĩa** chứ không dựa vào việc một giá trị “in giống 0.3” là cùng một số thực toán học. Khi test signed zero, so sánh raw bits; khi test NaN, dùng isNaN; khi test upper bound, xác định rõ liệu có cho phép infinity hay không.

## 25. Bảng lỗi thường gặp và phương án sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ nextDown = x - epsilon cố định | Sai bước tùy exponent | Dùng Math.nextDown |
| Nghĩ x - Double.MIN_VALUE luôn giảm x | Phép trừ có thể làm tròn về x | Dùng nextDown |
| Nghĩ x - Math.ulp(x) luôn là predecessor | Sai tại ranh giới lũy thừa 2 | Dùng nextDown |
| Dùng literal 1.0 thay vì 1.0f | Gọi overload double | Chọn đúng kiểu |
| Cast double predecessor về float | Có thể trở về float ban đầu | Gọi nextDown(float) |
| Tưởng -0.0 là nextDown(+0.0) | Sai special case | -Double.MIN_VALUE |
| Quên phân biệt ±0 bit pattern | Sai test/serialization | Raw bits hoặc Double.compare |
| Cho rằng Double.MIN_VALUE âm | Hiểu nhầm tên hằng | Đó là subnormal dương nhỏ nhất |
| Cho rằng Double.MIN_NORMAL=MIN_VALUE | Sai vùng subnormal | Phân biệt hai hằng |
| Cho rằng nextDown(-∞) tiến thêm | Có thể lặp vô hạn | Guard -∞ |
| Cho rằng nextDown(+∞) vẫn +∞ | Sai kết quả | Double.MAX_VALUE |
| Cho rằng nextDown(-MAX_VALUE) hữu hạn | Sai kết quả | -Infinity |
| Bỏ qua NaN | So sánh có thể luôn false | isNaN/validate |
| Đọc `ulp(x)` như số phần tử | Sai định nghĩa | ULP là khoảng cách |
| Áp nextDown để sửa 0.1+0.2 | Không tổng quát, có thể làm sai | BigDecimal/rounding phù hợp |
| Dùng nextDown cho bước đơn vị tiền | Bước IEEE không phải đơn vị tiền | Integer minor units/BigDecimal |
| Dùng bit decrement cho mọi double | Sai dấu/zero/NaN | Math.nextDown |
| Dùng `nextAfter(+0,-0)` như nextDown(0) | Hành vi khác | Hiểu direction equal case |
| Dùng nextDown để biến exclusive thành inclusive vô điều kiện | Biên đặc biệt và domain khác | Giữ toán tử < khi phù hợp |
| Dùng String.format để nghĩ thay đổi underlying number | Chỉ đổi biểu diễn text | Định nghĩa rounding thực |
| Không giữ count khi duyệt nextDown lặp | Thời gian cực dài/không dừng | Giới hạn bước, guard |
| Lấy output khi không kiểm hữu hạn | Infinite/NaN lan vào pipeline | Double.isFinite theo policy |

## 26. Bài tập thực hành có đáp án

### Bài 1 — số ngay dưới 1

**Đề:** Giá trị `double` lớn nhất nhỏ hơn `1.0d` là gì? Phương thức nào tìm chính xác?

**Đáp án:** `Math.nextDown(1.0d)`, bằng `0.9999999999999999`.

### Bài 2 — đổi kiểu

**Đề:** `Math.nextDown(1.0f)` và `Math.nextDown(1.0d)` có kết quả giống nhau không?

**Đáp án:** không. Float predecessor là `0.99999994`; double predecessor là `0.9999999999999999`. Hai kiểu có lưới biểu diễn khác nhau.

### Bài 3 — subtract MIN_VALUE

**Đề:** `double y = 1.0 - Double.MIN_VALUE;` có chắc là số double ngay dưới 1.0 không?

**Đáp án:** không. Lượng bị trừ quá nhỏ so với ULP quanh 1.0 nên phép trừ được làm tròn về 1.0.

### Bài 4 — ULP

**Đề:** `Math.ulp(1.0d)` có bằng `1.0 - Math.nextDown(1.0)` không?

**Đáp án:** không. Giá trị ULP ở 1.0 là khoảng bước bên phải, gấp đôi khoảng bước ngay dưới 1.0 vì đây là lũy thừa của 2.

### Bài 5 — số 0

**Đề:** `Math.nextDown(+0.0)` trả -0.0 hay một số âm khác 0?

**Đáp án:** `-Double.MIN_VALUE`, tức số double âm khác 0 gần 0 nhất.

### Bài 6 — min positive

**Đề:** `Math.nextDown(Double.MIN_VALUE)` trả gì?

**Đáp án:** `+0.0`. Đây là bước từ positive subnormal nhỏ nhất về zero.

### Bài 7 — ngược chiều ở vùng âm

**Đề:** `Math.nextUp(-Double.MIN_VALUE)` trả gì? Cách kiểm dấu chính xác?

**Đáp án:** `-0.0`. Dùng `Double.doubleToRawLongBits` để phân biệt -0.0 với +0.0.

### Bài 8 — vô cực dương

**Đề:** `Math.nextDown(Double.POSITIVE_INFINITY)` có kết quả hữu hạn không?

**Đáp án:** có, bằng `Double.MAX_VALUE`.

### Bài 9 — vô cực âm

**Đề:** `Math.nextDown(Double.NEGATIVE_INFINITY)` có giảm được thêm một bước không?

**Đáp án:** không. Trả lại `Double.NEGATIVE_INFINITY`.

### Bài 10 — NaN

**Đề:** `Math.nextDown(Double.NaN) == Double.NaN` đúng hay sai?

**Đáp án:** sai vì mọi toán tử equality của NaN với NaN trả false. Dùng `Double.isNaN(Math.nextDown(Double.NaN))` để kiểm kết quả là NaN.

### Bài 11 — nextAfter signed zero

**Đề:** `Math.nextAfter(+0.0,-0.0)` có giống `Math.nextDown(+0.0)` không?

**Đáp án:** không. nextAfter trả -0.0 khi start và direction so sánh bằng nhau; nextDown trả -Double.MIN_VALUE.

### Bài 12 — khoảng nửa mở

**Đề:** Khoảng double hữu hạn `[0,1)` có giá trị lớn nhất là gì?

**Đáp án:** `Math.nextDown(1.0d)`. Nhưng nếu chỉ cần membership, điều kiện `0.0 <= x && x < 1.0` cùng validation theo domain rõ nghĩa hơn.

### Bài 13 — tiền

**Đề:** Muốn tìm số tiền ngay dưới 100 với bước tối thiểu 0.01, có dùng `Math.nextDown(100.0)` không?

**Đáp án:** không. Bước đồng tiền là decimal 0.01; dùng `BigDecimal("100.00").subtract(BigDecimal("0.01"))` hoặc minor units.

### Bài 14 — số thập phân

**Đề:** `Math.nextDown(0.1 + 0.2)` in `0.3`. Có nên dùng nextDown sau mọi phép cộng không?

**Đáp án:** không. Sai số có thể ở các hướng/mức khác nhau. Chọn decimal arithmetic/rounding theo yêu cầu.

### Bài 15 — vòng lặp nextDown

**Đề:** Bắt đầu `x=-Double.MAX_VALUE`, liên tục gọi `x=Math.nextDown(x)` đến khi không còn giảm. Sẽ gặp gì?

**Đáp án:** bước đầu tới `-Infinity`, các bước sau vẫn -Infinity. Cần điều kiện dừng và xác định handling giá trị không hữu hạn.

### Bài 16 — raw bits

**Đề:** Có thể luôn tính predecessor bằng `Double.longBitsToDouble(Double.doubleToRawLongBits(x)-1)` không?

**Đáp án:** không. Raw bits không ánh xạ thứ tự số học đơn giản cho cả dấu, zero, NaN và infinities. Dùng Math.nextDown.

## 27. Câu hỏi tự kiểm tra

**1. nextDown đi theo hướng nào?** — Hướng âm vô cực.

**2. nextUp đi theo hướng nào?** — Hướng dương vô cực.

**3. Hai overload của nextDown nhận kiểu gì?** — `double` và `float`.

**4. nextDown trả số thực toán học bất kỳ hay số biểu diễn được?** — Giá trị liền kề biểu diễn được theo kiểu đầu vào.

**5. nextDown(1.0d) bằng bao nhiêu?** — `0.9999999999999999`.

**6. nextDown(1.0f) bằng bao nhiêu?** — `0.99999994`.

**7. nextDown(+0.0d) trả -0.0 đúng không?** — Không; trả -Double.MIN_VALUE.

**8. Double.MIN_VALUE có phải số âm không?** — Không; đó là số dương subnormal nhỏ nhất.

**9. Double.MIN_NORMAL khác gì?** — Là số normal dương nhỏ nhất.

**10. nextDown(+Infinity) trả gì?** — Double.MAX_VALUE.

**11. nextDown(-Infinity) trả gì?** — -Infinity.

**12. nextDown(NaN) trả gì?** — NaN.

**13. Có nên kiểm NaN bằng == không?** — Không, dùng Double.isNaN.

**14. ULP và nextDown có cùng kiểu kết quả không?** — Cả hai có thể trả double nhưng ULP là độ dài bước, nextDown là tọa độ giá trị liền kề.

**15. Vì sao bước hai phía của 1.0 không đối xứng?** — 1.0 là ranh giới binade/lũy thừa của 2.

**16. nextAfter(start,direction) có thể trả lại direction không?** — Có khi cả hai so sánh bằng nhau, đáng chú ý ở signed zero.

**17. Khi cần khoảng [a,b) nên ưu tiên phép kiểm gì?** — `a <= x && x < b` với validation theo domain.

**18. nextDown có phải công cụ round tiền tệ?** — Không.

**19. Cách hiển thị bit-value double chính xác?** — Double.toHexString hoặc raw bits khi cần.

**20. Kết quả nextDown(-Double.MAX_VALUE) có hữu hạn không?** — Không; là -Infinity.

**21. nextUp(nextDown(x)) có luôn == x kể cả NaN và vô cực?** — Không nên áp dụng như luật toàn cục; phải xử lý special cases.

**22. Có nên bước lặp nextDown để duyệt hàng tỷ giá trị?** — Không nếu không giới hạn rõ tài nguyên và điều kiện dừng.

**23. Vì sao BigDecimal("0.1") phù hợp decimal hơn double 0.1?** — Chuỗi decimal không trải qua sai số biểu diễn nhị phân trước khi tạo BigDecimal.

**24. Mục tiêu cốt lõi của nextDown là gì?** — Tìm một **láng giềng trong kiểu IEEE** chứ không sửa sai số tùy ý.

## Tài liệu chính thức

- [Java SE 8 — Math](https://docs.oracle.com/javase/8/docs/api/java/lang/Math.html): `nextDown`, `nextUp`, `nextAfter`, `ulp`, `scalb`, `copySign`.
- [Java SE 26 — Math](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html): các API số học tiếp tục còn hỗ trợ trên Java mới.
- [Java SE 8 — Double](https://docs.oracle.com/javase/8/docs/api/java/lang/Double.html): `MIN_VALUE`, `MIN_NORMAL`, `MAX_VALUE`, `isFinite`, `isNaN`, `toHexString`, raw bits.
- [Java SE 8 — Float](https://docs.oracle.com/javase/8/docs/api/java/lang/Float.html): binary32, các hằng và công cụ kiểm giá trị đặc biệt.
- [Java SE 8 — StrictMath](https://docs.oracle.com/javase/8/docs/api/java/lang/StrictMath.html): các phép số học với ngữ nghĩa được đặc tả.
- [Java SE 8 — BigDecimal](https://docs.oracle.com/javase/8/docs/api/java/math/BigDecimal.html): decimal arithmetic, compareTo và rounding theo ngữ cảnh.
- [Java Language Specification — Floating-Point Types](https://docs.oracle.com/javase/specs/jls/se8/html/jls-4.html#jls-4.2.3): kiểu float/double và các giá trị biểu diễn.
- [Java Language Specification — Numerical Comparison Operators](https://docs.oracle.com/javase/specs/jls/se8/html/jls-15.html#jls-15.20.1): ngữ nghĩa so sánh số, NaN và các giá trị đặc biệt.

**Ghi nhớ cuối:** `Math.nextDown` trả **số `float`/`double` liền kề với đầu vào theo -∞**, không phải trừ một epsilon tùy ý. Ở 1.0, bước xuống nhỏ hơn bước lên vì ranh giới lũy thừa 2; ở 0.0, bước xuống là `-MIN_VALUE`, không phải -0.0; ở +∞ trả MAX_VALUE, ở -∞ giữ nguyên, ở NaN trả NaN. Để xử lý biên số hữu hạn, dùng `nextDown` khi thật sự cần predecessor, nhưng giữ toán tử `<` và validation cho khoảng nửa mở. Không dùng nextDown để sửa mọi sai số decimal hoặc làm tròn tiền tệ: chọn đúng mô hình số học và quy tắc làm tròn theo nghiệp vụ.
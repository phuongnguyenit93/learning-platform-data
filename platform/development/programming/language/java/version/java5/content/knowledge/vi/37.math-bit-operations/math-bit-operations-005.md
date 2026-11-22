# Math.ulp, signum và giới hạn độ chính xác

## 1. Hai công cụ trả lời hai câu hỏi khác nhau

Khi làm việc với `float` và `double`, có hai câu hỏi thường gặp:

- Ở độ lớn hiện tại, các số mà máy biểu diễn được cách nhau bao xa?
- Giá trị đang mang dấu âm, dương hay bằng 0?

`Math.ulp(x)` giúp trả lời câu hỏi thứ nhất. ULP là viết tắt của **unit in the last place**, có thể hiểu là đơn vị ở vị trí có nghĩa cuối cùng của biểu diễn dấu phẩy động.

`Math.signum(x)` trả thông tin dấu theo quy tắc của số dấu phẩy động.

Cả hai đều có overload cho `float` và `double`:

```java
double step = Math.ulp(1.0);
double direction = Math.signum(-12.5);

float floatStep = Math.ulp(1.0f);
float floatDirection = Math.signum(-12.5f);
```

`Math` thuộc `java.lang`, không cần import. Các API này vẫn áp dụng trong Java hiện đại; ví dụ đầy đủ trong bài dùng Java 17+.

ULP không sửa sai số, còn signum không tăng độ chính xác. Chúng giúp quan sát và xử lý những giới hạn đã có trong kiểu số.

## 2. Vì sao khoảng cách giữa các double không cố định?

`double` có 53 bit có nghĩa ở miền số chuẩn, còn `float` có 24 bit. Số bit này có hạn, nên khi phần số mũ tăng, khoảng cách giữa các giá trị biểu diễn được cũng tăng.

Trong một khoảng của các số `double` dương chuẩn:

```text
2^e ≤ x < 2^(e+1)

ULP(x) = 2^(e - 52)
```

Ví dụ:

| Vùng giá trị double | Bước ULP |
| --- | --- |
| [0.5, 1) | 2⁻⁵³ |
| [1, 2) | 2⁻⁵² |
| [2, 4) | 2⁻⁵¹ |
| [2⁵², 2⁵³) | 1 |
| [2⁵³, 2⁵⁴) | 2 |

Có nhiều chữ số ở phần nguyên không có nghĩa máy còn đủ vị trí để giữ mọi phần lẻ hoặc mọi số nguyên kế tiếp.

Tại x = 2⁵³, hai giá trị biểu diễn được kế tiếp về phía lớn hơn là:

```text
9007199254740992
9007199254740994
```

Số nguyên 9007199254740993 nằm chính giữa. Khi cộng 1 vào 2⁵³ bằng phép cộng `double`, kết quả làm tròn về 2⁵³ theo quy tắc chọn gần nhất, hòa thì chẵn. Do đó có thể xảy ra:

```java
double x = 0x1.0p53; // 2^53.
System.out.println(x + 1.0 == x); // true.
System.out.println(x + 2.0 > x);  // true.
```

Ký hiệu `0x1.0p53` là literal dấu phẩy động hệ 16 của Java; phần p53 cho biết nhân với 2⁵³.

Với `float`, hiện tượng tương tự xuất hiện sớm hơn tại 2²⁴. Đây là lý do không dùng biến dấu phẩy động để đếm số nguyên tăng dần khi có thể vượt miền giữ chính xác số nguyên.

Các hằng và đặc điểm của kiểu `double` được mô tả tại [Double API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html).

## 3. Hiểu chính xác Math.ulp

Với giá trị hữu hạn thông thường, `Math.ulp(x)` là khoảng cách dương từ x đến giá trị cùng dấu có độ lớn kế tiếp. Vì vậy:

```text
ulp(-x) = ulp(x)
```

Với x dương chưa ở giá trị hữu hạn cực đại, có thể quan sát khoảng cách đó qua `Math.nextUp(x) - x`. Với x âm, hướng tăng độ lớn là về phía âm hơn, không phải luôn là `nextUp`.

### Hai phía của một lũy thừa 2 có thể có bước khác nhau

Tại 1.0:

```text
Math.ulp(1.0)            = 2^-52
Math.nextUp(1.0) - 1.0   = 2^-52
1.0 - Math.nextDown(1.0) = 2^-53
```

Khoảng ngay dưới 1 thuộc vùng số mũ thấp hơn nên bước bằng một nửa. Vì vậy không nên mô tả ULP là “khoảng cách đến bất kỳ số gần nhất nào ở cả hai phía”.

Tương tự, `Math.ulp(-1.0)` bằng 2⁻⁵² nhưng `Math.nextUp(-1.0) - (-1.0)` bằng 2⁻⁵³, vì `nextUp` ở đây đi về phía 0.

### ULP không phải epsilon cố định

`Math.ulp(1.0)` gần 2.220446049250313 × 10⁻¹⁶. Giá trị đó thường xuất hiện khi nói về độ chính xác quanh số 1, nhưng không phải khoảng cách chung của mọi `double`.

Dùng cố định giá trị đó để đánh giá một số ở độ lớn 10¹⁶ có thể quá chặt; dùng nó cho một đại lượng rất nhỏ có thể lại quá rộng. Cần xét độ lớn và đơn vị của bài toán.

### Các trường hợp đặc biệt

| x | Math.ulp(x) |
| --- | --- |
| +0.0 hoặc -0.0 | `Double.MIN_VALUE` |
| Số dưới chuẩn khác 0 | `Double.MIN_VALUE` |
| `Double.MIN_NORMAL` | `Double.MIN_VALUE` |
| ±`Double.MAX_VALUE` | 2⁹⁷¹ |
| ±Infinity | +Infinity |
| NaN | NaN |

`Double.MIN_VALUE` là số dương khác 0 nhỏ nhất, không phải số âm nhỏ nhất. Các số dưới chuẩn (subnormal) có bước cố định 2⁻¹⁰⁷⁴; chúng giúp tiến dần về 0, nhưng độ chính xác tương đối giảm khi số tiến sát 0.

Ở giá trị cực đại, `nextUp(Double.MAX_VALUE)` là Infinity, nhưng ULP của `Double.MAX_VALUE` vẫn hữu hạn. Đây là một trường hợp được quy định riêng.

Overload `float` có quy tắc tương tự, dùng `Float.MIN_VALUE` và ULP tại ±`Float.MAX_VALUE` bằng 2¹⁰⁴. Xem hợp đồng tại [Math.ulp API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#ulp(double)).

## 4. ULP nói về khả năng biểu diễn, không đo toàn bộ sai số

Biết `Math.ulp(result)` không cho biết result thực tế sai bao nhiêu so với đáp án toán học. Một thuật toán có thể trả về kết quả sai hàng triệu ULP do công thức không ổn định hoặc dữ liệu đầu vào đã sai.

Cần phân biệt:

- **Bước biểu diễn:** khoảng cách cục bộ của kiểu số, quan sát bằng ULP.
- **Sai số làm tròn một phép toán:** phần chênh lệch do đưa một kết quả chính xác về một giá trị biểu diễn được.
- **Sai số thuật toán:** ảnh hưởng của nhiều bước, mất thông tin, thứ tự phép tính và dữ liệu đầu vào.
- **Sai số được ứng dụng chấp nhận:** quy tắc do yêu cầu thực tế quyết định.

Với một phép làm tròn gần nhất thông thường, sai lệch nằm trong khoảng tới điểm biểu diễn lân cận; thường được nói đến bằng nửa ULP. Nhưng không thể lấy nhận định đó rồi kết luận cả một chuỗi phép tính luôn sai không quá nửa `Math.ulp(result)`.

Ví dụ:

```java
double a = 0.1 + 0.2;
double b = 0.3;
```

Trong biểu diễn `double`, a là 0.30000000000000004 còn b in là 0.3. Hai giá trị này cách nhau đúng một ULP tại b. Đó là một ví dụ cụ thể có thể kiểm chứng, không phải quy tắc rằng mọi phép cộng thập phân sai đúng một ULP.

Cũng không dùng ULP để suy ra rằng x đã giữ chính xác đầu vào. Một giá trị đo ngoài đời, một chuỗi đã parse hoặc một số được đổi từ kiểu khác có thể có sai số riêng trước khi phép tính bắt đầu.

## 5. Math.signum giữ thông tin dấu theo quy tắc dấu phẩy động

Với số khác 0, khác NaN:

```text
x > 0 →  1.0
x < 0 → -1.0
```

Hai trường hợp 0 và NaN cần xét riêng:

| Đầu vào | Math.signum |
| --- | --- |
| 12.5 | 1.0 |
| -12.5 | -1.0 |
| +0.0 | +0.0 |
| -0.0 | -0.0 |
| +Infinity | 1.0 |
| -Infinity | -1.0 |
| NaN | NaN |

`signum` không trả `int`; kiểu trả về là cùng kiểu dấu phẩy động của overload được chọn.

Số 0 âm và số 0 dương bằng nhau dưới toán tử `==`. Vì vậy `Math.signum(-0.0) == -1.0` là false; kết quả là -0.0, không phải -1.0. Nếu cần phân biệt dấu của 0, dùng biểu diễn bit hoặc API có hợp đồng phù hợp với việc giữ dấu.

`signum` cũng không phải phép so sánh toàn phần cho mọi giá trị: NaN không được tự phân vào nhóm âm, 0 hay dương. Nếu chương trình cần xử lý dữ liệu hữu hạn, kiểm tra `Double.isFinite(x)` trước; nếu chấp nhận vô cùng nhưng cần loại NaN, kiểm tra `Double.isNaN(x)`.

Định nghĩa từng trường hợp có tại [Math.signum API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#signum(double)).

### Không tự thay bằng x / abs(x)

Công thức `x / Math.abs(x)` trông giống signum khi x khác 0 và hữu hạn, nhưng:

```text
0.0 / abs(0.0)           → 0.0 / 0.0       → NaN
Infinity / abs(Infinity) → Infinity / Infinity → NaN
```

Trong khi `Math.signum(0.0)` trả 0.0 và `Math.signum(Infinity)` trả 1.0.

Với số nguyên, dùng `Integer.signum(int)` hoặc `Long.signum(long)` nếu cần kết quả int -1, 0, 1. Không cần đổi sang float/double để tìm dấu của số nguyên.

## 6. Giới hạn độ chính xác có thể làm mất cả dấu của một thay đổi

Xét biểu thức dưới đây tại x = 2⁵³:

```java
double change = (x + 1.0) - x;
double direction = Math.signum(change);
```

`change` bằng 0.0 do bước cộng đã làm mất số gia 1; `direction` bằng 0.0. Hàm signum đang trả đúng dấu của kết quả máy đã tính, nhưng không thể khôi phục dấu dương của thay đổi toán học ban đầu.

Tương tự, một phép nhân hai số dương rất nhỏ có thể hụt xuống 0.0. Gọi signum sau đó chỉ thấy 0, không thấy một số dương nhỏ hơn miền biểu diễn.

Đây là mối liên hệ thực tế giữa hai API:

1. ULP cho biết độ phân giải cục bộ.
2. Một thay đổi quá nhỏ có thể bị làm tròn mất khi cộng vào giá trị lớn.
3. Signum chỉ quan sát giá trị sau làm tròn.
4. Muốn quyết định đúng, phải chọn kiểu số hoặc công thức phù hợp từ trước.

Không thể “chữa” việc mất độ chính xác bằng cách gọi signum sau cùng.

## 7. Chương trình hoàn chỉnh

Lưu thành `UlpSignumDemo.java`. Chương trình dùng chuỗi hệ 16 cho một số bước ULP để thể hiện rõ lũy thừa của 2, tránh nhầm với số chữ số thập phân đang in.

```java
public class UlpSignumDemo {
    private static void hex(String label, double value) {
        System.out.println(label + "=" + Double.toHexString(value));
    }

    public static void main(String[] args) {
        hex("ulp1", Math.ulp(1.0));
        hex("ulp2", Math.ulp(2.0));
        hex("ulpHalf", Math.ulp(0.5));
        System.out.println("floatUlp1=" + Float.toHexString(Math.ulp(1.0f)));
        hex("gapAbove1", Math.nextUp(1.0) - 1.0);
        hex("gapBelow1", 1.0 - Math.nextDown(1.0));
        hex("gapAboveNegative1", Math.nextUp(-1.0) - (-1.0));
        System.out.println("ulpSymmetric=" + (Math.ulp(-1.0) == Math.ulp(1.0)));

        System.out.println("ulpZeroIsMin="
                + (Math.ulp(0.0) == Double.MIN_VALUE));
        System.out.println("ulpMinNormalIsMin="
                + (Math.ulp(Double.MIN_NORMAL) == Double.MIN_VALUE));
        hex("ulpMax", Math.ulp(Double.MAX_VALUE));
        System.out.println("nextUpMaxInfinite="
                + Double.isInfinite(Math.nextUp(Double.MAX_VALUE)));
        System.out.println("ulpInfinity=" + Math.ulp(Double.POSITIVE_INFINITY));
        System.out.println("ulpNaN=" + Double.isNaN(Math.ulp(Double.NaN)));

        double big = 0x1.0p53;
        System.out.println("bigPlus1Unchanged=" + (big + 1.0 == big));
        System.out.println("bigPlus2Increased=" + (big + 2.0 > big));
        System.out.println("ulpBig=" + Math.ulp(big));
        System.out.println("lostChangeSign=" + Math.signum((big + 1.0) - big));

        float bigFloat = 0x1.0p24f;
        System.out.println("floatPlus1Unchanged=" + (bigFloat + 1.0f == bigFloat));

        double oneUlp = Math.ulp(1.0);
        System.out.println("halfUlpAt1Lost=" + (1.0 + oneUlp / 2.0 == 1.0));
        System.out.println("oneUlpAt1Moves="
                + (1.0 + oneUlp == Math.nextUp(1.0)));

        double sum = 0.1 + 0.2;
        double expected = 0.3;
        System.out.println("decimalSum=" + sum);
        System.out.println("decimalSumOneUlpAway="
                + (Math.abs(sum - expected) == Math.ulp(expected)));

        System.out.println("signPositive=" + Math.signum(12.5));
        System.out.println("signNegative=" + Math.signum(-12.5));
        System.out.println("signPositiveZero=" + Math.signum(0.0));
        System.out.println("signNegativeZero=" + Math.signum(-0.0));
        System.out.println("negativeZeroBits="
                + Long.toHexString(Double.doubleToRawLongBits(Math.signum(-0.0))));
        System.out.println("signPositiveInfinity="
                + Math.signum(Double.POSITIVE_INFINITY));
        System.out.println("signNegativeInfinity="
                + Math.signum(Double.NEGATIVE_INFINITY));
        System.out.println("signNaN=" + Double.isNaN(Math.signum(Double.NaN)));

        double zero = 0.0;
        double infinity = Double.POSITIVE_INFINITY;
        System.out.println("naiveZeroNaN=" + Double.isNaN(zero / Math.abs(zero)));
        System.out.println("naiveInfinityNaN="
                + Double.isNaN(infinity / Math.abs(infinity)));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 UlpSignumDemo.java
java UlpSignumDemo
```

Stdout:

```text
ulp1=0x1.0p-52
ulp2=0x1.0p-51
ulpHalf=0x1.0p-53
floatUlp1=0x1.0p-23
gapAbove1=0x1.0p-52
gapBelow1=0x1.0p-53
gapAboveNegative1=0x1.0p-53
ulpSymmetric=true
ulpZeroIsMin=true
ulpMinNormalIsMin=true
ulpMax=0x1.0p971
nextUpMaxInfinite=true
ulpInfinity=Infinity
ulpNaN=true
bigPlus1Unchanged=true
bigPlus2Increased=true
ulpBig=2.0
lostChangeSign=0.0
floatPlus1Unchanged=true
halfUlpAt1Lost=true
oneUlpAt1Moves=true
decimalSum=0.30000000000000004
decimalSumOneUlpAway=true
signPositive=1.0
signNegative=-1.0
signPositiveZero=0.0
signNegativeZero=-0.0
negativeZeroBits=8000000000000000
signPositiveInfinity=1.0
signNegativeInfinity=-1.0
signNaN=true
naiveZeroNaN=true
naiveInfinityNaN=true
```

Hai dòng `gapAbove1` và `gapBelow1` minh họa bước biểu diễn thay đổi ở lũy thừa của 2. `ulpMax` cùng `nextUpMaxInfinite` minh họa trường hợp cực đại không thể suy ra ULP bằng một phép trừ trực tiếp với số kế tiếp.

`halfUlpAt1Lost=true` cho thấy phép cộng tại điểm giữa chọn 1.0 trong trường hợp này. Không nên tổng quát thành “mọi lần cộng nửa ULP đều không làm thay đổi số”: cách phá hòa phụ thuộc bit cuối của ứng viên.

`negativeZeroBits` có bit dấu bằng 1; chuỗi hệ 16 là 8000000000000000. Nó giúp kiểm tra việc giữ âm 0 mà phép so sánh số thông thường không phân biệt được.

## 8. Dùng ULP cho kiểm thử một cách có giới hạn

Khi kiểm thử một hàm số, có thể đặt một điều kiện cục bộ như:

```java
double tolerance = 4.0 * Math.ulp(expected);
boolean close = Double.isFinite(actual)
        && Double.isFinite(expected)
        && Math.abs(actual - expected) <= tolerance;
```

Đây là một tiêu chí đã chọn: chấp nhận độ lệch không quá bốn lần bước ULP tại `expected`. Nó không tự chứng minh thuật toán chính xác và không phải phép đếm chính xác số lần gọi `nextUp` giữa hai giá trị, nhất là khi đi qua ranh giới đổi bước.

Cần xác định hợp đồng trước khi chọn cách so sánh:

| Nhu cầu | Hướng đánh giá |
| --- | --- |
| Kiểm tra hàm có giới hạn sai số theo ULP | Dùng tiêu chí theo đặc tả hàm và giá trị tham chiếu đủ chính xác |
| Đo đại lượng có đơn vị cố định | Xét dung sai tuyệt đối theo đơn vị đó |
| So sánh dữ liệu thay đổi nhiều bậc độ lớn | Có thể cần dung sai tương đối kết hợp tuyệt đối |
| Kiểm tra đúng số nguyên hoặc số thập phân theo hợp đồng | Chọn kiểu và quy tắc chính xác tương ứng |
| Xử lý NaN/Infinity | Quy định riêng, không để lọt qua nhánh so sánh thông thường |

Ở gần 0, dung sai chỉ dựa trên ULP tại expected = 0 có thể quá nhỏ cho một thuật toán có sai số triệt tiêu. Ngược lại, dung sai tương đối thuần túy cũng gặp vấn đề vì mốc tham chiếu tiến về 0.

Giá trị tham chiếu là một `double` cũng đã được làm tròn. Khi yêu cầu đánh giá sai số toán học nghiêm ngặt, phải tính đến điều đó, thay vì xem mọi literal `double` là đáp án thực chính xác.

## 9. Những lỗi cần tránh

- Coi ULP là “sai số của x” thay vì độ phân giải cục bộ.
- Dùng `Math.ulp(1.0)` như một epsilon phù hợp cho toàn miền.
- Quên sự bất đối xứng hai phía của lũy thừa 2.
- Coi `Double.MIN_VALUE` là số âm nhỏ nhất.
- Dùng `Math.ulp(x) == Math.nextUp(x) - x` cho mọi x, kể cả âm và cực đại.
- Dùng vòng lặp `double i++` để đếm ở độ lớn mà số gia 1 đã không còn làm i thay đổi.
- Tính signum bằng x/abs(x) rồi bỏ qua 0 và vô cùng.
- Coi NaN là số 0 vì các điều kiện `x > 0` và `x < 0` đều false.
- Trông chờ signum khôi phục thay đổi đã mất do làm tròn hoặc hụt số.
- Tăng số chữ số in ra rồi cho rằng phép tính đã chính xác hơn.

Nếu cần số nguyên chính xác trong miền phù hợp, dùng `int` hoặc `long` và kiểm soát tràn; lớn hơn có thể cần `BigInteger`. Nếu cần giá trị thập phân với quy tắc làm tròn tường minh, cân nhắc `BigDecimal`. Đổi một kết quả `double` đã mất thông tin sang kiểu lớn hơn không khôi phục dữ liệu ban đầu.

## 10. Thực hành

1. Dự đoán `Math.ulp(4.0)`, `Math.ulp(8.0)` và `Math.ulp(-8.0)`; kiểm chứng bằng `Double.toHexString`.
2. So sánh bước ngay trên và ngay dưới 2.0. Vì sao chúng khác nhau dù đều gần 2?
3. Tại 2⁵⁴, ULP bằng bao nhiêu? Cộng 1, 2 và 4 lần lượt có làm giá trị thay đổi không? Giải thích trường hợp hòa.
4. Kiểm tra `Math.signum(Double.MIN_VALUE / 2.0)`. Vì sao kết quả không phải 1.0 dù biểu thức toán học ban đầu dương?
5. Viết hàm phân loại đầu vào thành NaN, âm vô cùng, dương vô cùng, số 0 và số hữu hạn khác 0; với số 0, tùy yêu cầu mà giữ hoặc bỏ phân biệt dấu.
6. Đặt hai bộ kiểm thử: một quanh 1.0 và một quanh 2⁵³. Chứng minh rằng một dung sai tuyệt đối rất nhỏ cố định không mô tả cùng mức “gần nhau theo biểu diễn” ở cả hai vùng.

Gợi ý: ULP tại 4 là 2⁻⁵⁰, tại ±8 là 2⁻⁴⁹. Tại 2⁵⁴, bước bằng 4; cộng 1 và cộng 2 đều làm tròn về chính giá trị đó, còn cộng 4 chuyển đến số biểu diễn kế tiếp. `Double.MIN_VALUE / 2.0` làm tròn về 0.0, nên signum trả 0.0.

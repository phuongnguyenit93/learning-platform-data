# NaN, vô cực và số 0 có dấu trong phép tính số thực — Java 17+

`float` và `double` trong Java biểu diễn số thực nhị phân theo IEEE 754. Ngoài các số hữu hạn thông thường, chúng có ba nhóm giá trị đặc biệt:

- **`NaN` (*Not a Number*)**: giá trị báo kết quả số học không xác định, chẳng hạn `0.0 / 0.0`.
- **Vô cực (`Infinity` và `-Infinity`)**: có thể xuất hiện khi số thực khác 0 chia cho số không hoặc khi kết quả quá lớn.
- **Số 0 có dấu (*signed zero*)**: có `+0.0` và `-0.0`. Hai giá trị bằng nhau khi dùng toán tử `==`, nhưng **bit dấu khác nhau** và có thể tạo kết quả khác nhau ở một số phép toán.

~~~java
double positive = 1.0 / 0.0;  // Infinity.
double negative = 1.0 / -0.0; // -Infinity.
double undefined = 0.0 / 0.0; // NaN.
~~~

**Không áp dụng quy tắc chia số nguyên cho 0 cho số thực.** `int` chia cho 0 ném `ArithmeticException` khi chạy; `double`/`float` chia cho số không tuân theo quy tắc IEEE 754.

## 1. Bảng kết quả tiêu biểu

| Biểu thức Java | Kết quả | Nguyên nhân |
| --- | --- | --- |
| `1.0 / 0.0` | `Infinity` | Số dương chia cho dương không |
| `1.0 / -0.0` | `-Infinity` | Số dương chia cho âm không |
| `0.0 / 0.0` | `NaN` | Dạng không xác định |
| `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` | `NaN` | Vô cực trừ vô cực |
| `Double.POSITIVE_INFINITY * 0.0` | `NaN` | Vô cực nhân không |
| `Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY` | `NaN` | Vô cực chia vô cực |
| `Double.MAX_VALUE * 2.0` | `Infinity` | Overflow số thực |
| `Double.MIN_VALUE / 2.0` | `0.0` | Underflow về dương không |
| `-Double.MIN_VALUE / 2.0` | `-0.0` | Underflow về âm không |

**Cẩn thận với tên `Double.MIN_VALUE`:** đây là **số `double` dương nhỏ nhất lớn hơn 0**, không phải số âm nhỏ nhất. Muốn có một giá trị hữu hạn âm có độ lớn rất lớn, có thể dùng `-Double.MAX_VALUE`.

## 2. Ví dụ Java 17+ chạy độc lập

Tạo tệp UTF-8 **`FloatingSpecialValuesDemo.java`**:

~~~java
public class FloatingSpecialValuesDemo {
    public static void main(String[] args) {
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = 1.0 / -0.0;
        double nan = 0.0 / 0.0;

        System.out.println("positiveInfinity=" + positiveInfinity);
        System.out.println("negativeInfinity=" + negativeInfinity);
        System.out.println("zeroOverZeroIsNaN="
                + Double.isNaN(nan));

        System.out.println("infinityMinusInfinityIsNaN="
                + Double.isNaN(Double.POSITIVE_INFINITY
                        - Double.POSITIVE_INFINITY));
        System.out.println("infinityTimesZeroIsNaN="
                + Double.isNaN(Double.POSITIVE_INFINITY * 0.0));
        System.out.println("infinityOverInfinityIsNaN="
                + Double.isNaN(Double.POSITIVE_INFINITY
                        / Double.POSITIVE_INFINITY));

        System.out.println("nanEqualsSelf=" + (nan == nan));
        System.out.println("nanNotEqualsSelf=" + (nan != nan));
        System.out.println("nanLessThanZero=" + (nan < 0.0));
        System.out.println("nanCompareSelf="
                + Double.compare(nan, nan));
        System.out.println("nanWrapperEquals="
                + Double.valueOf(nan).equals(Double.valueOf(nan)));

        System.out.println("finite42=" + Double.isFinite(42.0));
        System.out.println("finiteInfinity="
                + Double.isFinite(positiveInfinity));
        System.out.println("maxOverflow="
                + (Double.MAX_VALUE * 2.0));
        System.out.println("minUnderflow="
                + (Double.MIN_VALUE / 2.0));
        System.out.println("negativeMinUnderflow="
                + (-Double.MIN_VALUE / 2.0));

        double positiveZero = 0.0;
        double negativeZero = -0.0;
        System.out.println("zerosEqual="
                + (positiveZero == negativeZero));
        System.out.println("zeroWrapperEquals="
                + Double.valueOf(positiveZero)
                        .equals(Double.valueOf(negativeZero)));
        System.out.println("zeroCompare="
                + Double.compare(positiveZero, negativeZero));
        System.out.println("positiveZeroBits="
                + Long.toHexString(
                        Double.doubleToRawLongBits(positiveZero)));
        System.out.println("negativeZeroBits="
                + Long.toHexString(
                        Double.doubleToRawLongBits(negativeZero)));

        System.out.println("reciprocalPositiveZero="
                + (1.0 / positiveZero));
        System.out.println("reciprocalNegativeZero="
                + (1.0 / negativeZero));
        System.out.println("minZero="
                + Math.min(negativeZero, positiveZero));
        System.out.println("maxZero="
                + Math.max(negativeZero, positiveZero));
        System.out.println("copiedNegativeSign="
                + Math.copySign(5.0, negativeZero));
        System.out.println("nanMinIsNaN="
                + Double.isNaN(Math.min(nan, 3.0)));
        System.out.println("negativeZeroRemainder="
                + (negativeZero % 3.0));

        float floatNegativeInfinity = 1.0f / -0.0f;
        System.out.println("floatNegativeInfinity="
                + floatNegativeInfinity);
        System.out.println("parsedNaN="
                + Double.isNaN(Double.parseDouble("NaN")));

        double sum = 0.1 + 0.2;
        System.out.println("sum=" + sum);
        System.out.println("exactDecimalEquality="
                + (sum == 0.3));
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa tệp. Yêu cầu **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 FloatingSpecialValuesDemo.java
java FloatingSpecialValuesDemo
~~~

**Expected output chính xác** của riêng lệnh `java FloatingSpecialValuesDemo`:

~~~text
positiveInfinity=Infinity
negativeInfinity=-Infinity
zeroOverZeroIsNaN=true
infinityMinusInfinityIsNaN=true
infinityTimesZeroIsNaN=true
infinityOverInfinityIsNaN=true
nanEqualsSelf=false
nanNotEqualsSelf=true
nanLessThanZero=false
nanCompareSelf=0
nanWrapperEquals=true
finite42=true
finiteInfinity=false
maxOverflow=Infinity
minUnderflow=0.0
negativeMinUnderflow=-0.0
zerosEqual=true
zeroWrapperEquals=false
zeroCompare=1
positiveZeroBits=0
negativeZeroBits=8000000000000000
reciprocalPositiveZero=Infinity
reciprocalNegativeZero=-Infinity
minZero=-0.0
maxZero=0.0
copiedNegativeSign=-5.0
nanMinIsNaN=true
negativeZeroRemainder=-0.0
floatNegativeInfinity=-Infinity
parsedNaN=true
sum=0.30000000000000004
exactDecimalEquality=false
~~~

`java -version` và `javac -version` in thông tin JDK tùy máy, không thuộc phần expected output của chương trình.

## 3. `NaN`: kiểm tra và so sánh

`NaN` không phải `null`, số 0 hay chuỗi báo lỗi. Đây là **giá trị số thực đặc biệt** có thể được truyền tiếp qua nhiều phép tính.

~~~java
double value = 0.0 / 0.0;
System.out.println(value == Double.NaN); // false.
System.out.println(value != value);      // true.
System.out.println(Double.isNaN(value)); // true.
~~~

Với primitive `double` hoặc `float`, các phép `==`, `<`, `<=`, `>`, `>=` có toán hạng NaN cho `false`; phép `!=` cho `true`. Do đó **không kiểm tra NaN bằng `value == Double.NaN`**. Dùng `Double.isNaN(value)` hoặc `Float.isNaN(value)`.

### Phân biệt primitive `==`, `Double.equals` và `Double.compare`

~~~java
double nan = Double.NaN;
System.out.println(nan == nan); // false.
System.out.println(Double.compare(nan, nan)); // 0.
System.out.println(Double.valueOf(nan)
        .equals(Double.valueOf(nan))); // true.
~~~

| Phép so sánh | Hai giá trị NaN | Hai giá trị `+0.0` và `-0.0` |
| --- | --- | --- |
| Primitive `==` | `false` | `true` |
| Wrapper `Double.equals` | `true` | `false` |
| `Double.compare(a,b)` | Trả 0 khi cả hai NaN | Phân biệt dấu, `compare(+0.0,-0.0) > 0` |

`Double.equals` và `Double.compare` được thiết kế để có quy tắc bình đẳng/thứ tự thích hợp cho wrapper và collection. Chúng **không giống hoàn toàn** ngữ nghĩa so sánh số thực primitive bằng `==`.

### NaN lan truyền và parsing

~~~java
double nan = Double.NaN;
System.out.println(Double.isNaN(nan + 2.0)); // true.
System.out.println(Double.isNaN(nan * 0.0)); // true.
System.out.println(Double.isNaN(Double.parseDouble("NaN"))); // true.
~~~

Một chuỗi `"NaN"` có thể được `Double.parseDouble` chấp nhận. **Parsing thành công không đồng nghĩa giá trị hợp lệ theo nghiệp vụ**, nhất là khi ứng dụng chỉ muốn số hữu hạn.

## 4. Vô cực và cách nhận biết giá trị hữu hạn

Ngoài `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`, phép tính quá lớn có thể cho vô cực:

~~~java
double overflow = Double.MAX_VALUE * 2.0; // Infinity.
double reciprocal = 1.0 / -0.0;          // -Infinity.
~~~

Một số phép toán với vô cực vẫn cho vô cực, ví dụ `Infinity + 3.0`. Nhưng `Infinity + (-Infinity)`, `Infinity * 0.0` hay `Infinity / Infinity` cho NaN.

Nếu cần xác nhận số thực hữu hạn:

~~~java
double input = Double.parseDouble("12.5");
if (!Double.isFinite(input)) {
    throw new IllegalArgumentException("Expected a finite number");
}
~~~

- `Double.isNaN(x)`: giá trị NaN?
- `Double.isInfinite(x)`: giá trị vô cực dương hoặc âm?
- `Double.isFinite(x)`: giá trị không phải NaN và không phải vô cực?
- `Float` cũng có những phương thức tương ứng với `float`.

`Double.isFinite(-0.0)` trả **`true`**. Zero có bit dấu vẫn là số **hữu hạn**.

## 5. Hai số không `+0.0` và `-0.0` khác nhau ở đâu?

Cả `+0.0` và `-0.0` đều là zero theo phép `==`:

~~~java
double plus = 0.0;
double minus = -0.0;

System.out.println(plus == minus); // true.
System.out.println(1.0 / plus);    // Infinity.
System.out.println(1.0 / minus);   // -Infinity.
~~~

Tuy nhiên, với IEEE 754 chúng có **bit dấu khác nhau**. `Double.doubleToRawLongBits` giúp xem mẫu bit:

| Biểu thức | Mẫu bit 64-bit (hexadecimal) |
| --- | --- |
| `Double.doubleToRawLongBits(+0.0)` | `0x0000000000000000` |
| `Double.doubleToRawLongBits(-0.0)` | `0x8000000000000000` |

Demo in `positiveZeroBits=0` và `negativeZeroBits=8000000000000000` vì `Long.toHexString` bỏ các chữ số 0 ở đầu.

Ngoài phép nghịch đảo, dấu zero có thể quan trọng trong `Math.min`, `Math.max`, `Math.copySign`, phép chia và phần dư số thực:

~~~java
System.out.println(Math.min(-0.0, 0.0));    // -0.0.
System.out.println(Math.max(-0.0, 0.0));    //  0.0.
System.out.println(Math.copySign(5.0, -0.0)); // -5.0.
System.out.println(-0.0 % 3.0);            // -0.0.
~~~

**Không dùng `x == 0.0` để phân biệt dấu của zero**. Tùy nhu cầu, dùng `Math.copySign` hoặc kiểm tra bit. `float` cũng có `+0.0f` và `-0.0f` nhưng có biểu diễn 32-bit.

## 6. Overflow/underflow không giống sai số làm tròn thông thường

**Overflow số thực** có thể sinh `Infinity` khi độ lớn vượt miền hữu hạn. **Underflow** xảy ra với giá trị quá gần 0, có thể thành subnormal hoặc được làm tròn về **zero có dấu**:

~~~java
System.out.println(Double.MAX_VALUE * 2.0); // Infinity.
System.out.println(Double.MIN_VALUE / 2.0); // 0.0.
System.out.println(-Double.MIN_VALUE / 2.0); // -0.0.
~~~

`Double.MIN_VALUE` là số **dương nhỏ nhất khác 0**, không phải giá trị âm lớn nhất về độ lớn. Các phép này không tự ném `ArithmeticException` như chia nguyên cho 0.

Ngay cả số **hữu hạn** vẫn có thể chỉ là xấp xỉ: `0.1 + 0.2` với `double` cho `0.30000000000000004`. `Double.isFinite` kiểm tra NaN/vô cực, **không** chứng minh giá trị thập phân chính xác. Bài tiếp theo tập trung binary32/binary64, ULP, sai số tích lũy, dung sai và mô hình decimal exact.


## 7. Lỗi thường gặp

| Hiểu nhầm | Thực tế trong Java 17+ |
| --- | --- |
| “`0.0 / 0.0` ném `ArithmeticException`.” | Kết quả là `NaN` |
| “`1.0 / 0.0` giống `1 / 0`.” | `double` cho `Infinity`; `int` chia 0 ném ngoại lệ |
| “`NaN == NaN` luôn đúng.” | Với primitive `double`: `false` |
| “`x == Double.NaN` kiểm tra được NaN.” | Sai; dùng `Double.isNaN(x)` |
| “`Double.equals` và primitive `==` hoàn toàn giống nhau.” | Khác với NaN và ±0.0 |
| “`+0.0` và `-0.0` không khác biệt nào.” | Chúng khác bit dấu và có thể khác kết quả phép toán |
| “`Double.MIN_VALUE` là giá trị âm nhỏ nhất.” | Đây là số dương nhỏ nhất lớn hơn 0 |
| “`parseDouble` thành công thì luôn được số hữu hạn.” | Chuỗi `"NaN"` và `"Infinity"` cũng có thể hợp lệ |
| “Số hữu hạn nghĩa là số chính xác thập phân.” | Không; `0.1 + 0.2` là phản ví dụ |

## 8. Bài tập tự kiểm tra

1. `1.0 / 0.0`, `1.0 / -0.0`, `0.0 / 0.0` lần lượt là gì?  
   *Đáp án:* `Infinity`, `-Infinity`, `NaN`.
2. Tại sao `Double.NaN == Double.NaN` cho false?  
   *Đáp án:* Toán tử primitive `==` tuân theo quy tắc NaN; kiểm tra NaN bằng `Double.isNaN`.
3. `0.0 == -0.0` cho gì và `1.0 / -0.0` cho gì?  
   *Đáp án:* `true` và `-Infinity`.
4. Hai wrapper `Double.valueOf(0.0)` và `Double.valueOf(-0.0)` có `equals` nhau không?  
   *Đáp án:* Không; `Double.equals` phân biệt bit dấu của zero.
5. `Double.MIN_VALUE / 2.0` có thể tạo gì?  
   *Đáp án:* `0.0` do underflow.
6. Cần từ chối cả NaN lẫn Infinity trong đầu vào số thực thì dùng gì?  
   *Đáp án:* `Double.isFinite(value)`.
7. `Double.isFinite(0.1 + 0.2)` trả true, vậy `0.1 + 0.2 == 0.3` có chắc true?  
   *Đáp án:* Không; trong `double`, kết quả là `0.30000000000000004`.

## Checklist

- [ ] Biết `NaN`, `Infinity` và `-Infinity` là **giá trị số thực đặc biệt**, không phải `null`.
- [ ] Dùng `Double.isNaN`, `Double.isInfinite`, `Double.isFinite` thay vì đoán từ `==`.
- [ ] Phân biệt phép `==` primitive với `Double.equals` và `Double.compare`.
- [ ] Hiểu `+0.0` và `-0.0` bằng nhau theo `==` nhưng khác bit dấu.
- [ ] Biết overflow có thể ra vô cực, underflow có thể ra zero có dấu.
- [ ] Phân biệt phép chia cho 0 của số nguyên và số thực.
- [ ] Không đồng nhất **hữu hạn** với **chính xác thập phân**.

**Kết luận:** `float`/`double` có những quy tắc quan trọng dành riêng cho **NaN, vô cực và hai giá trị zero có dấu**. Đọc đúng các giá trị này bằng API kiểm tra chuyên dụng, nắm sự khác nhau giữa các phép so sánh, và kiểm tra độ chính xác độc lập với tính hữu hạn.

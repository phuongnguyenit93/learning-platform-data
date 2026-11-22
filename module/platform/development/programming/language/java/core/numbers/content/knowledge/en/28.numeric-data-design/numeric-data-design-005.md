# Kiểm tra đầu vào trước chuyển đổi có thể mất dữ liệu trong Java

## 1. Vấn đề: chuyển đổi thành công vẫn có thể tạo ra dữ liệu sai

Trong Java, một phép chuyển đổi số có thể biên dịch và chạy thành công nhưng **không bảo toàn giá trị đầu vào**. Ví dụ:

~~~java
int truncated = (int) 12.9;          // 12: mất phần lẻ
int overflowed = (int) 2147483648L; // -2147483648: mất các bit cao
int invalid = (int) Double.NaN;      // 0: đầu vào không phải số
~~~

Nếu chỉ kiểm tra kết quả sau khi ép kiểu, thông tin cần để phát hiện lỗi đã biến mất. Đây là lý do phải kiểm tra đầu vào **trước** những phép chuyển đổi có khả năng cắt phần lẻ, tràn miền, underflow hoặc làm tròn.

Trước một phép chuyển đổi, cần trả lời: miền giá trị hợp lệ là gì, kiểu đích có biểu diễn được giá trị đó không, có bắt buộc giữ nguyên độ chính xác không, và nếu không giữ được thì **từ chối** hay **làm tròn theo chính sách rõ ràng**?

Bài học tập trung vào dữ liệu số của Java Core: `int`, `long`, `float`, `double`, `BigInteger`, `BigDecimal` và chuỗi số. Mục tiêu là giữ dữ liệu đúng theo hợp đồng ứng dụng, không đơn thuần tránh exception.

## 2. Phân loại những mất mát thường gặp

| Chuyển đổi | Điều gì có thể xảy ra? | Ví dụ | Cách phòng ngừa |
| --- | --- | --- | --- |
| `long → int` | Mất bit cao, đổi dấu | `2147483648L → -2147483648` | `Math.toIntExact` |
| `double → int` | Cắt về 0 phần thập phân | `12.9 → 12` | Kiểm tra số nguyên rồi mới ép |
| `double → int` | NaN thành 0, quá miền bị bão hòa ở cực trị | `NaN → 0` | `Double.isFinite`, kiểm tra biên |
| `int → float` | Mất chữ số có nghĩa | `16777217 → 16777216` | Kiểm tra biểu diễn chính xác |
| `long → double` | Làm tròn số nguyên lớn | `9007199254740993 → 9007199254740992` | Giữ `long` hoặc dùng kiểu chính xác |
| `double → float` | Giảm độ chính xác, có thể vô cực/zero | `0.1d → float` | Kiểm tra hữu hạn và round-trip |
| `BigDecimal → int/long` | Mất phần thập phân hoặc tràn miền | `12.75.intValue() → 12` | `intValueExact`, `longValueExact` |
| `BigDecimal → double` | Xấp xỉ nhị phân, overflow/underflow | `0.1`, `1E+400` | Giữ `BigDecimal` nếu phải chính xác |
| Chuỗi → số | Cú pháp sai hoặc giá trị ngoài miền nghiệp vụ | `"NaN"`, `"-5"`, `"1e100"` | Parse và validate nhiều lớp |

Cần phân biệt **phạm vi (range)**, **độ chính xác (precision)** và **quy tắc làm tròn (rounding)**. Một giá trị nằm trong phạm vi của kiểu đích vẫn có thể không được biểu diễn chính xác. Ngược lại, số `12.000` có ba chữ số sau dấu thập phân nhưng có thể chuyển thành số nguyên 12 **không mất giá trị**.

## 3. Từ long sang int: dùng Math.toIntExact

`int` là số nguyên có dấu 32 bit, từ `-2147483648` đến `2147483647`; `long` là số nguyên có dấu 64 bit.

~~~java
long source = 2_147_483_648L;
int wrong = (int) source; // -2147483648: vẫn chạy được
~~~

Java không ném exception khi ép hẹp kiểu nguyên thủy từ long sang int. Để bảo đảm chính xác:

~~~java
int safe = Math.toIntExact(source);
// ArithmeticException vì source vượt Integer.MAX_VALUE
~~~

`Math.toIntExact(long)` trả int nếu giữ nguyên được giá trị số, nếu không ném `ArithmeticException`.

Kiểm tra thủ công hợp lệ khi cần một thông báo lỗi cụ thể:

~~~java
static int toIntChecked(long value) {
    if (value < Integer.MIN_VALUE || value > Integer.MAX_VALUE) {
        throw new IllegalArgumentException("Ngoài phạm vi int");
    }
    return (int) value;
}
~~~

Đoạn trên là **mảnh phương thức**; đặt trong một lớp Java để chạy. Việc ép ở dòng cuối chỉ diễn ra sau khi kiểm tra đủ hai biên.

**Chú ý:** `Math.toIntExact` không sửa được một phép tính đã tràn từ trước. Nếu `int a + int b` đã overflow, chuyển tổng sai ấy sang long cũng không khôi phục được giá trị ban đầu.

## 4. Từ double sang int: hữu hạn, trong miền và không có phần lẻ

Với phép ép `(int) doubleValue`, Java cắt phần lẻ **về phía 0**. Vì vậy `12.9 → 12`, `-12.9 → -12`. Ngoài ra:

- `Double.NaN` bị chuyển thành 0.
- Giá trị quá lớn hoặc `Double.POSITIVE_INFINITY` bị bão hòa về `Integer.MAX_VALUE`; quá nhỏ hoặc âm vô cực về `Integer.MIN_VALUE`.
- `-0.0` trở thành số nguyên 0, không giữ dấu của zero.

Nếu yêu cầu là một **giá trị số nguyên chính xác**, hãy kiểm tra trước:

~~~java
static int doubleToIntChecked(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Không phải số hữu hạn");
    }
    if (value < Integer.MIN_VALUE || value > Integer.MAX_VALUE) {
        throw new IllegalArgumentException("Ngoài phạm vi int");
    }
    if (value != Math.rint(value)) {
        throw new IllegalArgumentException("Có phần lẻ");
    }
    return (int) value;
}
~~~

`Math.rint(value)` được dùng để phát hiện giá trị có là số nguyên hay không; đoạn code **không dùng kết quả rint để âm thầm làm tròn**. Hàm này chấp nhận `-0.0` như giá trị số 0. Nếu bài toán cần bảo toàn dấu âm zero theo bit, không thể lưu đủ thông tin đó trong int; phải cấm hoặc ghi riêng.

Nếu nguồn là số thập phân người dùng nhập, **đừng parse qua double trước** rồi mới kiểm tra tính nguyên, vì giá trị lớn hoặc nhiều chữ số đã có thể bị làm tròn. Dùng `BigDecimal` từ chuỗi và `intValueExact()` khi muốn giữ giá trị thập phân chính xác.

## 5. Vì sao số nguyên chuyển sang float/double vẫn có thể mất độ chính xác?

Dù `float` hoặc `double` có thể chứa các giá trị rất lớn, chúng có số bit dành cho **chữ số có nghĩa** hữu hạn.

- `float` theo IEEE 754 binary32 có 24 bit độ chính xác nhị phân. Mọi số nguyên trong khoảng `[-2^24, 2^24]` được biểu diễn chính xác, nhưng không phải mọi số ngoài khoảng.
- `double` theo IEEE 754 binary64 có 53 bit độ chính xác nhị phân. Mọi số nguyên trong khoảng `[-2^53, 2^53]` được biểu diễn chính xác, nhưng không phải mọi số ngoài khoảng.

Ví dụ có thể chạy trong một phương thức:

~~~java
int number = 16_777_217;
float asFloat = (float) number;

System.out.println((int) asFloat); // 16777216
// Mất 1 so với number=16777217.
~~~

Với long:

~~~java
long number = 9_007_199_254_740_993L;
double asDouble = (double) number;

System.out.println((long) asDouble); // 9007199254740992
// Mất 1 so với long ban đầu.
~~~

Một **cái bẫy khi kiểm tra lại**:

~~~java
long original = 9_007_199_254_740_993L;
double converted = (double) original;
boolean looksEqual = converted == original; // Có thể true!
~~~

Trong phép so sánh `double == long`, Java **chuyển cả toán hạng long sang double**. Vì cả hai phía có thể bị làm tròn như nhau, `looksEqual` có thể true dù số nguyên gốc đã mất độ chính xác. Tương tự khi so `float` và `int`.

Nếu mục tiêu là bảo đảm mọi giá trị trong một miền đều giữ nguyên, thiết kế miền vào khoảng đủ chính xác. Nếu cần xác minh một `long` cụ thể ngoài miền đó, có thể so sánh thông qua biểu diễn chính xác của giá trị double thực tế:

~~~java
static boolean exactlyRepresentableAsDouble(long value) {
    double asDouble = (double) value;
    return java.math.BigDecimal.valueOf(value)
            .compareTo(new java.math.BigDecimal(asDouble)) == 0;
}
~~~

Trong phương thức này, `new BigDecimal(asDouble)` được dùng **có chủ đích** để tái tạo chính xác giá trị nhị phân đã được biểu diễn trong `double`; không nhầm với `BigDecimal.valueOf(double)`, vốn dùng chuỗi thập phân chuẩn của double. Có thể dùng `BigInteger` để kiểm tra giá trị nguyên theo một thiết kế tương đương.

## 6. Từ double sang float: phép chuyển hẹp có thể làm tròn

Một số `double` hữu hạn có thể không biểu diễn được đúng ở `float`; một số lớn thành vô cực hoặc số rất nhỏ khác 0 thành 0.

Để yêu cầu **không mất thêm giá trị so với double hiện tại**:

~~~java
static float doubleToFloatChecked(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Không hữu hạn");
    }
    float result = (float) value;
    if (!Float.isFinite(result) || (double) result != value) {
        throw new IllegalArgumentException("Mất độ chính xác khi ép float");
    }
    return result;
}
~~~

Mỗi giá trị float hữu hạn khi chuyển lên double đều được biểu diễn chính xác. Vì thế, so giá trị float sau ép và chuyển ngược với double trước ép giúp kiểm tra **mất mát mới tại bước chuyển**. Không thể dùng phép thử này để khôi phục giá trị thập phân gốc đã bị làm tròn trước đó khi parse hoặc tính bằng double.

Đây là phép kiểm tra giá trị số. Nếu phải bảo toàn cả chi tiết biểu diễn như dấu của zero, cần kiểm tra/ghi nhận bit dấu riêng.

## 7. BigDecimal: các phép chuyển exact

Đối với giá trị chính xác theo thập phân, `BigDecimal` cung cấp hai nhóm API chuyển đổi:

| Phương thức | Chính sách |
| --- | --- |
| `intValue()`, `longValue()` | Có thể cắt phần lẻ và/hoặc bỏ bit cao |
| `intValueExact()`, `longValueExact()` | Ném `ArithmeticException` nếu phần lẻ khác 0 hoặc vượt phạm vi |
| `toBigInteger()` | Cắt phần lẻ theo hướng 0 |
| `toBigIntegerExact()` | Ném `ArithmeticException` nếu có phần lẻ khác 0 |

Ví dụ:

~~~java
BigDecimal a = new BigDecimal("12.000");
BigDecimal b = new BigDecimal("12.001");

System.out.println(a.intValueExact()); // 12
// b.intValueExact();                   // ArithmeticException
~~~

`12.000` vẫn là số nguyên về giá trị; `BigDecimal.scale() == 3` không có nghĩa phép chuyển sang int chắc chắn mất dữ liệu. Kiểm tra exact theo **giá trị**, thay vì mặc định cấm mọi scale dương.

Với `BigDecimal.doubleValue()`, bạn không có bảo đảm exact tương tự. `0.1` thập phân không được biểu diễn chính xác bằng binary64; giá trị quá lớn như `1E+400` có thể thành vô cực. Nếu cần giữ tiền hoặc dữ liệu decimal chính xác, tiếp tục tính bằng `BigDecimal` và đừng đi vòng qua double.

`BigDecimal` không tự động kiểm tra miền nghiệp vụ. Giá trị có thể chuyển exact sang long nhưng vẫn vi phạm quy tắc “số tiền không âm” hoặc “tối đa 1.000 đơn vị”. Cần kiểm tra cả **ý nghĩa** lẫn **khả năng biểu diễn**.

## 8. Quy trình kiểm tra đầu vào chuỗi số

Khi dữ liệu đến từ JSON, biểu mẫu, CSV hoặc request HTTP, nên giữ **chuỗi gốc** nếu cần kiểm soát định dạng và chưa chắc kiểu số đích. Một quy trình có thể gồm:

1. **Sự hiện diện và độ dài:** null, trống, chuỗi quá dài.
2. **Cú pháp cho phép:** dấu âm, dấu cộng, khoảng trắng, dấu chấm thập phân, số mũ, dấu phân cách hàng nghìn, ký tự đặc biệt.
3. **Parse bằng kiểu đủ chính xác:** ví dụ `BigDecimal(String)` cho số thập phân; `BigInteger(String)` cho số nguyên rất lớn.
4. **Miền nghiệp vụ:** số không âm, khoảng cho phép, đơn vị đo, số lượng nguyên, precision/scale.
5. **Khả năng biểu diễn ở kiểu đích:** exact method, giới hạn min/max và kiểm tra mất chính xác nếu cần.
6. **Chính sách khi không exact:** từ chối hoặc làm tròn theo `RoundingMode` được quy định.
7. **Chỉ lưu/sử dụng kết quả đã qua validation.**

Không được coi “parse thành công” là “dữ liệu hợp lệ”. Chẳng hạn `Double.parseDouble("NaN")` và `Double.parseDouble("Infinity")` có thể tạo giá trị đặc biệt, nên khi chỉ chấp nhận số hữu hạn vẫn phải kiểm tra `Double.isFinite`.

`new BigDecimal("1E+3")` có thể parse thành 1000, nhưng nếu định dạng đầu vào không cho phép số mũ, vẫn phải từ chối ở **tầng cú pháp**. Tương tự, `"-0.00"` có giá trị số bằng 0 trong `BigDecimal`; nếu hợp đồng cấm ký tự dấu trừ ở đầu chuỗi dù giá trị bằng 0, phải kiểm tra chuỗi trước khi parse.

## 9. Ví dụ nghiệp vụ: đổi tiền thập phân sang đơn vị nhỏ nhất

Giả sử đầu vào là **số tiền dạng chuỗi**, lưu thành `long` biểu thị cents. Quy tắc:

- Giá trị phải không âm.
- Chỉ chấp nhận giá trị có thể chuyển chính xác sang số nguyên cents. `12.340` được phép vì chữ số cuối bị loại là 0.
- Số cents phải nằm trong phạm vi `long`.
- Dữ liệu sai cú pháp, âm, quá chính xác hoặc quá lớn bị từ chối.

Triển khai:

~~~java
static long toCents(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Thiếu số tiền");
    }
    BigDecimal amount = new BigDecimal(raw.strip());
    if (amount.signum() < 0) {
        throw new IllegalArgumentException("Số tiền âm");
    }
    return amount.movePointRight(2).longValueExact();
}
~~~

`movePointRight(2)` nhân giá trị decimal lên 100 mà không làm tròn; `longValueExact()` yêu cầu giá trị sau nhân 100 là số nguyên và còn nằm trong miền long. Như vậy chuyển `12.34 → 1234`, `12.340 → 1234`; từ chối `12.345` vì tương ứng 1234.5 cents.

Đặc tả trên kiểm tra **giá trị được giữ nguyên**. Nếu quy tắc bắt buộc biểu diễn đầu vào có **tối đa hai ký tự chữ số sau dấu chấm**, thì ngay cả `12.340` cũng phải bị loại bằng kiểm tra cú pháp/scale bổ sung. Hai quy tắc này khác nhau.

Đây là ví dụ kỹ thuật, không khẳng định mọi loại tiền tệ có đơn vị nhỏ nhất bằng 1/100; đơn vị và chính sách làm tròn phải lấy từ nghiệp vụ.

## 10. Chương trình Java 17 hoàn chỉnh và kết quả chính xác

Tạo file `CheckedConversionDemo.java`:

~~~java
import java.math.BigDecimal;

public class CheckedConversionDemo {
    static long toCents(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("Missing amount");
        }
        BigDecimal amount = new BigDecimal(raw.strip());
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        return amount.movePointRight(2).longValueExact();
    }

    static void showCents(String raw) {
        try {
            System.out.println(raw + " -> " + toCents(raw) + " cents");
        } catch (IllegalArgumentException | ArithmeticException ex) {
            System.out.println(raw + " -> REJECTED");
        }
    }

    static int toIntChecked(double value) {
        if (!Double.isFinite(value)
                || value < Integer.MIN_VALUE
                || value > Integer.MAX_VALUE
                || value != Math.rint(value)) {
            throw new IllegalArgumentException("Not exact int");
        }
        return (int) value;
    }

    public static void main(String[] args) {
        showCents("12.34");
        showCents("12.340");
        showCents("12.345");
        showCents("-1.00");
        showCents("92233720368547758.08");

        System.out.println("long 42 -> " + Math.toIntExact(42L));
        try {
            Math.toIntExact(2_147_483_648L);
        } catch (ArithmeticException ex) {
            System.out.println("int overflow -> REJECTED");
        }

        System.out.println("unsafe 42.9 -> " + (int) 42.9);
        System.out.println("checked 42.0 -> " + toIntChecked(42.0));
        try {
            toIntChecked(42.9);
        } catch (IllegalArgumentException ex) {
            System.out.println("fraction -> REJECTED");
        }
        System.out.println("NaN finite -> " + Double.isFinite(Double.NaN));
        System.out.println("NaN cast -> " + (int) Double.NaN);
        System.out.println("exact decimal int -> "
                + new BigDecimal("12.000").intValueExact());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac CheckedConversionDemo.java
java CheckedConversionDemo
~~~

Kết quả:

~~~text
12.34 -> 1234 cents
12.340 -> 1234 cents
12.345 -> REJECTED
-1.00 -> REJECTED
92233720368547758.08 -> REJECTED
long 42 -> 42
int overflow -> REJECTED
unsafe 42.9 -> 42
checked 42.0 -> 42
fraction -> REJECTED
NaN finite -> false
NaN cast -> 0
exact decimal int -> 12
~~~

Diễn giải những điểm then chốt:

- `12.345 × 100 = 1234.5`, không thể đổi thành long chính xác.
- `92233720368547758.08 × 100 = 9223372036854775808`, lớn hơn `Long.MAX_VALUE` đúng một đơn vị.
- `Math.toIntExact(2_147_483_648L)` từ chối thay vì âm thầm trở thành số âm.
- `42.9` bị ép thẳng thành 42; `toIntChecked(42.9)` từ chối vì phần lẻ.
- `Double.NaN` không phải số hữu hạn, nhưng phép ép thẳng sang int lại cho 0.
- `new BigDecimal("12.000").intValueExact()` thành công vì các chữ số thập phân đều bằng 0.

## 11. Khi làm tròn được phép: nói rõ thời điểm và chế độ

“Không mất dữ liệu” và “làm tròn có kiểm soát” là **hai hợp đồng khác nhau**.

Khi phải giữ chính xác hai chữ số sau dấu thập phân hoặc từ chối:

~~~java
BigDecimal value = new BigDecimal("12.345");
BigDecimal exact = value.setScale(
        2, java.math.RoundingMode.UNNECESSARY);
// ArithmeticException: cần làm tròn, không được phép.
~~~

Khi chính sách cho phép làm tròn:

~~~java
BigDecimal value = new BigDecimal("12.345");
BigDecimal rounded = value.setScale(
        2, java.math.RoundingMode.HALF_EVEN);
// 12.34: trường hợp đúng nửa bước, chữ số cuối giữ là 4 (chẵn).
~~~

Đây là **các mảnh minh họa** bên trong lớp có import `BigDecimal`. Chọn `HALF_UP`, `HALF_EVEN`, `UP`, `DOWN` hoặc mode khác theo quy tắc thực tế, không dựa vào tên gọi.

`setScale(2, UNNECESSARY)` vẫn cho phép `12.340` thành `12.34`, vì việc bỏ số 0 cuối không đổi giá trị số. Nếu cần giữ hoặc kiểm tra **định dạng nguyên gốc** thì phải lưu/validate chuỗi trước khi chuẩn hóa.

Không tự làm tròn sau từng phép tính trung gian. Hai cách “làm tròn từng hạng tử rồi cộng” và “cộng chính xác rồi làm tròn” có thể cho kết quả khác nhau. Đặc tả phải nêu rõ **thời điểm** làm tròn.

## 12. Mất dữ liệu trước chuyển đổi: tràn phép tính và chia số nguyên

Đôi khi kiểu đích đủ rộng, nhưng phép tính **đã bị sai trước khi gán**:

~~~java
int a = 2_000_000_000;
int b = 2_000_000_000;

long wrong = a + b;       // phép cộng int đã tràn trước
long correct = (long) a + b; // 4000000000
~~~

`long wrong` không chứa tổng toán học chính xác vì hai toán hạng đã cộng trong miền int. Nếu kết quả bắt buộc ở miền int và không được overflow, dùng `Math.addExact(a, b)`, `Math.multiplyExact`, `Math.subtractExact` hoặc API phù hợp.

Tương tự:

~~~java
int numerator = 5;
int denominator = 2;

double wrong = numerator / denominator;          // 2.0
double approximate = (double) numerator / denominator; // 2.5
~~~

Biểu thức `numerator / denominator` thực hiện chia nguyên trước, nên khi gán sang double đã mất phần lẻ. Nếu muốn tính thập phân **chính xác** hoặc làm tròn theo quy tắc rõ ràng, dùng `BigDecimal.divide(..., scale, roundingMode)`; nếu đầu vào và đầu ra cho phép xấp xỉ, chuyển sang double trước khi chia có thể phù hợp.

Kiểm tra `Math.toIntExact` **sau** một phép tính int bị tràn hoặc chuyển sang `BigDecimal` **sau** phép chia nguyên không thể tự khôi phục giá trị đã mất.

## 13. Kiểm tra miền giá trị và định dạng: không được đánh đồng

Đầu vào `"12.000"` có scale 3 nhưng giá trị là số nguyên 12. Do đó:

- Muốn bảo đảm giá trị chuyển sang int không thay đổi: dùng `intValueExact()`.
- Muốn bảo đảm giá trị tiền đổi thành cents không mất phần lẻ: dùng `movePointRight(2).longValueExact()`.
- Muốn quy định **chuỗi có tối đa hai chữ số sau dấu thập phân**: kiểm tra cấu trúc chuỗi đầu vào hoặc scale theo cú pháp được phép.
- Muốn giới hạn miền như `0 <= amount <= 1000`: so sánh `BigDecimal.compareTo` với các biên.
- Muốn giới hạn số chữ số có nghĩa: xác định cách xử lý precision, dấu 0 cuối và biểu diễn khoa học, sau đó kiểm tra riêng.

`BigDecimal.scale()` không đồng nghĩa số chữ số có nghĩa. Ví dụ `new BigDecimal("12.000")` có scale 3 và precision 5. Một chuỗi dùng số mũ có thể tạo `BigDecimal` có scale âm, nên không suy ra quy tắc lexical của input từ mỗi con số scale.

Đặc biệt, `new BigDecimal("-0.00").signum() == 0`; nếu chuỗi đầu vào có dấu trừ là bất hợp lệ **ngay cả khi bằng 0**, validation phải xét chuỗi gốc trước khi chuyển thành BigDecimal.

## 14. Lỗi thường gặp

**1. Ép rồi mới so biên.** Sau `(int) longValue`, bit cao đã biến mất. Hãy kiểm tra trên `long` hoặc dùng `Math.toIntExact`.

**2. Dùng `BigDecimal.intValue()` khi yêu cầu exact.** Nó có thể cắt phần lẻ hoặc tràn; dùng `intValueExact()`.

**3. Giả định parse thành công là hợp lệ.** `Double.parseDouble("NaN")` có thể trả NaN; một `BigDecimal` âm vẫn parse thành công dù nghiệp vụ cấm giá trị âm.

**4. Dùng `value == Double.NaN` để kiểm tra NaN.** Theo quy tắc IEEE 754, NaN không bằng chính nó. Dùng `Double.isNaN`; nếu muốn cả NaN và vô cực bị loại, dùng `Double.isFinite`.

**5. Cho rằng số được biểu diễn bằng double/float thì phải chính xác.** Các số nguyên rất lớn và decimal như `0.1` có thể bị làm tròn. Miền giá trị rộng không đồng nghĩa precision vô hạn.

**6. Chuyển lại rồi so bằng `==` mà không xét quy tắc promotion.** `doubleValue == longValue` có thể chuyển cả hai về double, che khuất mất dữ liệu.

**7. Tạo `new BigDecimal(0.1)` rồi mong nó mang giá trị thập phân 0.1 chính xác.** Literal `0.1` đã là double xấp xỉ. Với input thập phân chính xác, dùng `new BigDecimal("0.1")`; khi nhận double sẵn có, phải hiểu giới hạn thông tin nguồn.

**8. Làm tròn mặc định không có chính sách.** `HALF_UP` hay `DOWN` đều là quyết định nghiệp vụ. Nếu yêu cầu không được mất giá trị, dùng exact hoặc `RoundingMode.UNNECESSARY`.

**9. Nhầm quy tắc giá trị với quy tắc biểu diễn.** `12.340` có thể đổi exact sang 1234 cents nhưng không đáp ứng chính sách chuỗi tối đa hai chữ số sau dấu chấm.

**10. Chỉ kiểm tra kết quả cuối mà bỏ phép tính trung gian.** Overflow của phép cộng int hoặc phần lẻ đã bị chia nguyên cắt không thể được khôi phục nhờ kiểu đích rộng hơn.

**11. Tự động thay lỗi parse bằng 0.** Dữ liệu thiếu hoặc sai không nhất thiết có ý nghĩa số học bằng 0. Chỉ áp dụng giá trị mặc định nếu hợp đồng quy định rõ.

**12. Bỏ qua test ở biên.** Giá trị nằm đúng cực trị, vượt cực trị một đơn vị, gần 0, phần lẻ rất nhỏ, NaN, vô cực và dạng khoa học đều có thể phát hiện lỗi mà ví dụ số bình thường không bộc lộ.

## 15. Bài tập và đáp án

### Bài 1: Tìm dữ liệu mất ở đâu

~~~java
long original = 2_147_483_648L;
System.out.println((int) original);

double fraction = -12.9;
System.out.println((int) fraction);

BigDecimal price = new BigDecimal("8.010");
System.out.println(price.movePointRight(2).longValueExact());
~~~

Kết quả khi đặt trong chương trình có import BigDecimal:

~~~text
-2147483648
-12
801
~~~

Hai trường hợp đầu mất dữ liệu: long → int vượt miền và double → int cắt phần lẻ. Trường hợp cuối bảo toàn giá trị: `8.010 × 100 = 801.0`, có thể chuyển exact thành long.

### Bài 2: Chọn đầu vào hợp lệ cho toCents

| Chuỗi | Kết quả theo `toCents` ở mục 9 | Giải thích |
| --- | --- | --- |
| `"0"` | `0` | Giá trị zero hợp lệ |
| `"9.9"` | `990` | Chuyển chính xác |
| `"9.999"` | Từ chối | `999.9` cents còn phần lẻ |
| `"9.990"` | `999` | Bỏ số 0 cuối không đổi giá trị |
| `"-0.00"` | `0` | BigDecimal biểu diễn zero, `signum == 0` |
| `"-0.01"` | Từ chối | Vi phạm điều kiện không âm |
| `"abc"` | Từ chối | Không parse được |

Nếu API cấm ký tự `-` ở đầu, kể cả số 0, phải bổ sung kiểm tra chuỗi đầu vào.

### Bài 3: Vì sao so sánh có thể sai?

~~~java
long original = 9_007_199_254_740_993L;
double narrowed = (double) original;
boolean same = narrowed == original;
~~~

`same` có thể true vì `original` được đưa sang double ngay trong phép so sánh. Nó **không** chứng minh chuyển đổi không mất dữ liệu. Hãy giữ miền đầu vào trong `[-2^53, 2^53]` khi muốn một bảo đảm đơn giản cho mọi số nguyên, hoặc kiểm tra bằng biểu diễn chính xác của từng giá trị.

### Bài 4: Thiết kế kiểm tra nhiệt độ

API nhận chuỗi nhiệt độ Celsius trong `[-100.00,100.00]`, lưu thành `int` số phần trăm độ. Thiết kế hợp lý: kiểm tra định dạng, parse `BigDecimal`, so sánh miền với hai giá trị biên, gọi `movePointRight(2).intValueExact()`, trả lỗi nếu không thể chuyển chính xác. Nếu chính sách giới hạn chữ số **trong chuỗi**, thêm một kiểm tra lexical trước đó.

### Bài 5: Chọn API phù hợp

- `long → int` không cho phép tràn: `Math.toIntExact`.
- `BigDecimal → long` không được mất phần lẻ: `longValueExact()`.
- `BigDecimal → BigInteger` không được cắt lẻ: `toBigIntegerExact()`.
- Kiểm tra `double` hữu hạn: `Double.isFinite`.
- Thu gọn scale nhưng cấm làm tròn thay đổi giá trị: `setScale(target, RoundingMode.UNNECESSARY)`.
- Tính số nguyên mà cấm overflow: các phương thức `Math.*Exact`.

## 16. Checklist trước khi chấp nhận chuyển đổi

1. Dữ liệu gốc còn được giữ đủ chính xác để kiểm tra không?
2. Đã xác thực cú pháp, miền, đơn vị và chính sách về dấu, số 0, chữ số và exponent chưa?
3. Đã kiểm tra phạm vi kiểu đích và khả năng biểu diễn chính xác chưa?
4. Nếu nguồn là dấu phẩy động, đã loại NaN/vô cực và xét phần lẻ, underflow, overflow chưa?
5. Nếu dùng BigDecimal, đã chọn `*ValueExact` hoặc chính sách `RoundingMode` rõ ràng chưa?
6. Các phép toán trước khi chuyển đổi có thể đã mất dữ liệu hay không?
7. Bài kiểm thử có đủ giá trị biên, ngay ngoài biên, số không hợp lệ và các trường hợp làm tròn không?

**Ghi nhớ:** Hãy kiểm tra **trước khi dữ liệu bị biến đổi**. Một kết quả mang kiểu `int`, `long`, `float` hay `double` hợp lệ không chứng minh nó bằng giá trị nguồn. Dùng các API exact, kiểm tra hữu hạn/range/precision, rồi mới chuyển; nếu chủ động làm tròn, hãy ghi rõ chính sách và thời điểm.

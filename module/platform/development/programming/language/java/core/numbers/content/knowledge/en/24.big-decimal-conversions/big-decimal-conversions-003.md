# BigDecimal.toEngineeringString(): số mũ theo bội của 3

## 1. Ký pháp kỹ thuật là gì?

Khi một con số quá lớn hoặc quá nhỏ, người ta thường viết theo ký pháp khoa học (*scientific notation*):

~~~text
12 300 000 = 1.23 × 10^7
0.000000123 = 1.23 × 10^-7
~~~

Trong **ký pháp kỹ thuật** (*engineering notation*), số mũ của 10 được chọn là **bội số nguyên của 3**:

~~~text
12 300 000 = 12.3 × 10^6
0.000000123 = 123 × 10^-9
~~~

Điều này có ích khi đọc số theo nhóm ba bậc độ lớn: nghìn (`10^3`), triệu (`10^6`), tỷ (`10^9`), milli (`10^-3`), micro (`10^-6`), nano (`10^-9`). Java hỗ trợ việc chuyển đối tượng `BigDecimal` thành chuỗi theo dạng này bằng:

~~~java
String text = number.toEngineeringString();
~~~

`toEngineeringString()` trả về một `String` biểu diễn **cùng giá trị toán học**. Phương thức không làm tròn, không giới hạn precision, không thay đổi đơn vị đo, không thay đổi đối tượng `BigDecimal` ban đầu.

Ví dụ:

~~~java
BigDecimal x = new BigDecimal("1E+4");
System.out.println(x.toString());            // 1E+4
System.out.println(x.toEngineeringString()); // 10E+3
System.out.println(x.toPlainString());       // 10000
~~~

Cả ba chuỗi biểu diễn giá trị 10.000. Điểm khác nhau là cách đặt dấu thập phân và số mũ.

## 2. Quy tắc "số mũ là bội số của 3"

Trong chuỗi kiểu `ME+n`, dấu `E` chỉ lũy thừa thập phân:

~~~text
M E n = M × 10^n

1E+4 = 1 × 10^4 = 10000
10E+3 = 10 × 10^3 = 10000
100E-9 = 100 × 10^-9 = 0.0000001
~~~

Với số **khác 0** được viết ở dạng có `E`:

- Ký pháp khoa học chuẩn hóa thường đặt một chữ số khác 0 trước dấu chấm, tương ứng `1 ≤ |M| < 10`.
- Ký pháp kỹ thuật đặt từ một đến ba chữ số trước dấu chấm, tương ứng `1 ≤ |M| < 1000`; số mũ `n` chia hết cho 3.
- Dấu của số được giữ ở phần định trị: `-10E+3` bằng `-10000`.
- Số mũ có thể âm: `-3`, `-6`, `-9` cũng là bội của 3.

| Giá trị | Dạng khoa học | Dạng kỹ thuật | Vì sao |
|---|---|---|---|
| 10.000 | `1E+4` | `10E+3` | Giảm số mũ 4 xuống 3 và tăng định trị gấp 10 |
| 100.000 | `1E+5` | `100E+3` | Giảm số mũ 5 xuống 3 và tăng định trị gấp 100 |
| 1.000.000 | `1E+6` | `1E+6` | Số mũ 6 đã chia hết cho 3 |
| 0,0000001 | `1E-7` | `100E-9` | Số mũ -9 chia hết cho 3 |
| 0,00000001 | `1E-8` | `10E-9` | Số mũ -9 chia hết cho 3 |
| 0,000000001 | `1E-9` | `1E-9` | Số mũ -9 đã phù hợp |

Nếu dịch dấu thập phân trong định trị sang phải `r` chữ số thì phải giảm số mũ đi `r` để **giữ nguyên giá trị**:

~~~text
M × 10^e = (M × 10^r) × 10^(e-r)

1.23 × 10^-7 = 123 × 10^-9
1.2345 × 10^8 = 123.45 × 10^6
~~~

Cách chuyển đổi hoàn toàn không yêu cầu tính toán bằng số chấm động `double`.

**Quan trọng:** "Số mũ là bội của 3" chỉ áp dụng **khi Java quyết định xuất chuỗi có ký hiệu `E`**. `toEngineeringString()` không bắt buộc in `E` đối với mọi đối tượng.

## 3. So sánh toString(), toEngineeringString(), toPlainString()

Đây là ba cách xuất chuỗi khác nhau của `BigDecimal`:

| Phương thức | Cách biểu diễn | Có thể có `E`? | Mục tiêu |
|---|---|---|---|
| `toString()` | Biểu diễn chuẩn (*canonical*), có thể là khoa học hoặc dạng thường | Có | Chuyển số thành chuỗi chuẩn, giữ cặp giá trị–scale khi parse lại |
| `toEngineeringString()` | Nếu dùng `E` thì số mũ là bội của 3 | Có | Trình bày theo nhóm ba bậc thập phân |
| `toPlainString()` | Dạng thập phân thường, không in số mũ | Không | Chuỗi số thường, không có `E` |

So sánh giá trị trả về thực tế:

| Constructor | `toString()` | `toEngineeringString()` | `toPlainString()` |
|---|---|---|---|
| `new BigDecimal("1E+4")` | `1E+4` | `10E+3` | `10000` |
| `new BigDecimal("1E+5")` | `1E+5` | `100E+3` | `100000` |
| `new BigDecimal("1E+6")` | `1E+6` | `1E+6` | `1000000` |
| `new BigDecimal("1E-7")` | `1E-7` | `100E-9` | `0.0000001` |
| `new BigDecimal("1E-8")` | `1E-8` | `10E-9` | `0.00000001` |
| `new BigDecimal("1E-9")` | `1E-9` | `1E-9` | `0.000000001` |
| `new BigDecimal("0.000000123")` | `1.23E-7` | `123E-9` | `0.000000123` |
| `new BigDecimal("12345.00")` | `12345.00` | `12345.00` | `12345.00` |
| `new BigDecimal("1000")` | `1000` | `1000` | `1000` |
| `new BigDecimal("0E+7")` | `0E+7` | `0.00E+9` | `0` |

Với `new BigDecimal("1000")`, tất cả ba phương thức đều in `1000`. Phương thức kỹ thuật **không tự động ép số 1000 sang `1E+3`**. Tương tự, `new BigDecimal("123456789").toEngineeringString()` vẫn trả `"123456789"` dù giá trị khá lớn.

Đây là điểm dễ sai khi viết các chương trình yêu cầu "mọi số phải được in có số mũ kỹ thuật". Nếu hợp đồng yêu cầu **luôn có `E`**, phải dùng bộ định dạng có cấu hình riêng, bao gồm quy tắc precision, rounding và locale. Chỉ `toEngineeringString()` không bảo đảm hình thức đó.

## 4. Vì sao Java đôi khi in dạng thập phân thường?

Một `BigDecimal` gồm hai thành phần: giá trị nguyên chưa chia tỷ lệ (`unscaledValue`) và `scale`:

~~~text
giá trị = unscaledValue × 10^(-scale)
~~~

`scale()` có thể dương, bằng 0 hoặc âm. `precision()` là số chữ số của phần nguyên chưa chia tỷ lệ, không tính dấu. Ví dụ:

| Đối tượng | `precision()` | `scale()` | Giá trị |
|---|---:|---:|---|
| `new BigDecimal("123.4500")` | 7 | 4 | 123.4500 |
| `new BigDecimal("1000")` | 4 | 0 | 1000 |
| `new BigDecimal("1E+3")` | 1 | -3 | 1000 |
| `new BigDecimal("0.0000001")` | 1 | 7 | 0.0000001 |

Với số khác 0, số mũ điều chỉnh (*adjusted exponent*) là:

~~~text
adjustedExponent = precision() - scale() - 1
~~~

Đối với `toString()` và `toEngineeringString()`, nếu `scale >= 0` và `adjustedExponent >= -6` thì Java dùng dạng thập phân thường. Khi điều kiện đó không đúng, chuỗi thường dùng ký pháp `E`; `toEngineeringString()` điều chỉnh để số mũ của `E` là bội của 3. Quy tắc cụ thể cho số 0 có các ngoại lệ biểu diễn vì số 0 không có định trị chuẩn hóa duy nhất.

Ví dụ ranh giới:

~~~java
BigDecimal a = new BigDecimal("0.000001");  // precision=1, scale=6
BigDecimal b = new BigDecimal("0.0000001"); // precision=1, scale=7

System.out.println(a.toEngineeringString()); // 0.000001
System.out.println(b.toEngineeringString()); // 100E-9
~~~

Số thứ nhất có adjusted exponent `-6` nên vẫn in bình thường; số thứ hai có adjusted exponent `-7` nên dùng ký pháp số mũ. Do đó, không thể suy luận đơn giản rằng "số nào nhỏ hơn 1 đều có `E`".

## 5. Chương trình Java 17+ có thể chạy độc lập

Tạo tệp `EngineeringStringDemo.java` với nội dung:

~~~java
import java.math.BigDecimal;

public class EngineeringStringDemo {
    public static void main(String[] args) {
        String[] inputs = {
            "1E+4", "1E+5", "1E+6",
            "1E-7", "1E-8", "1E-9",
            "0.000000123", "12345.00", "1000", "0E+7"
        };

        for (String input : inputs) {
            BigDecimal number = new BigDecimal(input);
            System.out.println(
                    input
                    + " | sci=" + number.toString()
                    + " | eng=" + number.toEngineeringString()
                    + " | plain=" + number.toPlainString());
        }

        BigDecimal original = new BigDecimal("1E+4");
        BigDecimal fromEngineering =
                new BigDecimal(original.toEngineeringString());
        BigDecimal fromCanonical =
                new BigDecimal(original.toString());

        System.out.println("original scale=" + original.scale());
        System.out.println("engineering scale=" + fromEngineering.scale());
        System.out.println("same numeric value="
                + (original.compareTo(fromEngineering) == 0));
        System.out.println("same representation="
                + original.equals(fromEngineering));
        System.out.println("canonical preserves representation="
                + original.equals(fromCanonical));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac EngineeringStringDemo.java
java EngineeringStringDemo
~~~

Kết quả chuẩn:

~~~text
1E+4 | sci=1E+4 | eng=10E+3 | plain=10000
1E+5 | sci=1E+5 | eng=100E+3 | plain=100000
1E+6 | sci=1E+6 | eng=1E+6 | plain=1000000
1E-7 | sci=1E-7 | eng=100E-9 | plain=0.0000001
1E-8 | sci=1E-8 | eng=10E-9 | plain=0.00000001
1E-9 | sci=1E-9 | eng=1E-9 | plain=0.000000001
0.000000123 | sci=1.23E-7 | eng=123E-9 | plain=0.000000123
12345.00 | sci=12345.00 | eng=12345.00 | plain=12345.00
1000 | sci=1000 | eng=1000 | plain=1000
0E+7 | sci=0E+7 | eng=0.00E+9 | plain=0
original scale=-4
engineering scale=-3
same numeric value=true
same representation=false
canonical preserves representation=true
~~~

Tên nhãn `sci` trong ví dụ chỉ giúp đối chiếu với `toString()`; phương thức này không bắt buộc luôn trả ký pháp khoa học. Các dòng `1000` và `12345.00` cho thấy kết quả có thể là số thập phân thường.

Các dòng cuối kiểm tra tính chất quan trọng khi **parse ngược** một chuỗi engineering notation thành `BigDecimal`: cùng giá trị số chưa chắc cùng `scale`.

## 6. Parse chuỗi engineering: giữ giá trị, có thể đổi scale

Constructor `new BigDecimal(String)` chấp nhận ký pháp `E`, ví dụ:

~~~java
BigDecimal parsed = new BigDecimal("10E+3");
System.out.println(parsed.toPlainString()); // 10000
~~~

Tuy nhiên, nếu sau đó parse chuỗi từ `toEngineeringString()`, hai đối tượng trước và sau **có thể khác scale**:

~~~java
BigDecimal before = new BigDecimal("1E+4");  // 1 × 10^4
String text = before.toEngineeringString();  // "10E+3"
BigDecimal after = new BigDecimal(text);      // 10 × 10^3

System.out.println(before.scale());          // -4
System.out.println(after.scale());           // -3
System.out.println(before.compareTo(after)); // 0
System.out.println(before.equals(after));    // false
~~~

Vì sao? `BigDecimal` tính giá trị theo công thức `unscaledValue × 10^(-scale)`:

| Đối tượng | Unscaled value | Scale | Giá trị |
|---|---:|---:|---:|
| `before`, được tạo từ `"1E+4"` | 1 | -4 | 10000 |
| `after`, được tạo từ `"10E+3"` | 10 | -3 | 10000 |

`compareTo() == 0` biểu thị giá trị toán học bằng nhau. `equals()` yêu cầu giá trị **và scale** bằng nhau; vì vậy trả `false` ở đây. Đây là hành vi của `BigDecimal`, không phải lỗi của `toEngineeringString()`.

| Chuỗi xuất rồi tạo lại bằng `new BigDecimal(text)` | Giữ nguyên giá trị toán học? | Luôn giữ nguyên scale? |
|---|---|---|
| `x.toString()` | Có | **Có**: biểu diễn chuẩn của `BigDecimal` |
| `x.toEngineeringString()` | Có | **Không nhất thiết** |
| `x.toPlainString()` | Có | **Không nhất thiết**, nhất là khi scale âm |

Với `toPlainString()`, ví dụ `new BigDecimal("1E+4")` xuất ra `"10000"`. Parse lại thành `new BigDecimal("10000")` có scale 0, khác scale -4 ban đầu.

**Quy tắc thực tế:** nếu chỉ cần giá trị số, có thể so sánh bằng `compareTo(other) == 0`. Nếu serializing/deserializing phải bảo toàn cả biểu diễn (`scale`, một phần của ngữ nghĩa `equals()`), dùng `toString()` và `new BigDecimal(String)`. Không nên dùng `toEngineeringString()` làm định dạng round trip chính xác về scale trong hợp đồng dữ liệu.

## 7. Số 0 là trường hợp đặc biệt

Số khác 0 có thể chuẩn hóa định trị trong khoảng từ 1 đến dưới 1000, nhưng số 0 thì không: mọi biểu thức `0 × 10^n` vẫn là 0. Bởi vậy Java còn dùng các số 0 sau dấu thập phân để thể hiện scale.

~~~java
BigDecimal zero = new BigDecimal("0E+7");
System.out.println(zero.toString());            // 0E+7
System.out.println(zero.toEngineeringString()); // 0.00E+9
System.out.println(zero.toPlainString());       // 0
~~~

`0.00E+9` vẫn bằng 0; số mũ 9 là bội của 3. Không thể suy ra số mũ này từ "độ lớn" của số 0; nó phụ thuộc biểu diễn của đối tượng. Parse `"0.00E+9"` còn có thể giữ lại scale -7 của `"0E+7"`, bởi hai chữ số 0 thập phân nằm trong định trị.

Ví dụ khác:

~~~java
System.out.println(new BigDecimal("0E-7").toEngineeringString());
// 0.0E-6
~~~

Đối với số 0, không áp dụng máy móc quy tắc định trị `1 ≤ |M| < 1000`. Khi xây dựng thuật toán riêng chuyển đổi dạng engineering, cần xử lý zero riêng và không tự đưa ra kết luận về precision hoặc scale chỉ từ độ lớn bằng 0.

## 8. Trường hợp số 0 cuối và stripTrailingZeros()

Các `BigDecimal` sau cùng giá trị 1000 nhưng có biểu diễn khác nhau:

~~~java
BigDecimal first = new BigDecimal("1E+3");
BigDecimal second = new BigDecimal("1000");
BigDecimal third = new BigDecimal("1000.00");

System.out.println(first.toEngineeringString());  // 1E+3
System.out.println(second.toEngineeringString()); // 1000
System.out.println(third.toEngineeringString());  // 1000.00
~~~

`first` có scale -3, `second` có scale 0, `third` có scale 2. Các số 0 ở cuối chuỗi đầu vào có thể ảnh hưởng precision và scale, dù giá trị toán học không đổi.

`stripTrailingZeros()` trả về một `BigDecimal` mới, bỏ các số 0 không cần thiết khỏi unscaled value; trong trường hợp này scale thay đổi:

~~~java
BigDecimal count = new BigDecimal("1000");
BigDecimal stripped = count.stripTrailingZeros();

System.out.println(count.toEngineeringString());    // 1000
System.out.println(stripped.toEngineeringString()); // 1E+3
System.out.println(stripped.scale());               // -3
~~~

Vì thế `stripTrailingZeros()` **không chỉ đổi cách hiển thị**, mà còn thay đổi biểu diễn của đối tượng kết quả. Nếu dùng trước khi serialize, bạn có thể vô tình thay đổi kết quả của `equals()` hoặc các xử lý phụ thuộc scale.

Không dùng `stripTrailingZeros()` một cách máy móc để ép mọi số thành dạng có `E`: với các số không có số 0 cuối như `123456789`, phương thức không tạo ra số mũ.

## 9. Engineering notation không có tác dụng rounding

`toEngineeringString()` không làm tròn. Nếu số có nhiều chữ số có nghĩa, chuỗi engineering vẫn biểu diễn toàn bộ giá trị:

~~~java
BigDecimal x = new BigDecimal("1.23456789012345E+7");
System.out.println(x.toEngineeringString());
// 12.3456789012345E+6
~~~

Nếu bài toán cần giới hạn số chữ số có nghĩa, phải làm tròn riêng trước khi chuyển thành chuỗi:

~~~java
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal x = new BigDecimal("1.23456789E+7");
BigDecimal rounded = x.round(new MathContext(4, RoundingMode.HALF_UP));

System.out.println(rounded.toEngineeringString()); // 12.35E+6
~~~

`round(MathContext)` xác định precision và chế độ làm tròn; `toEngineeringString()` chỉ xác định dạng biểu diễn. Tương tự, `setScale(2, RoundingMode.HALF_UP)` nhằm làm tròn đến hai chữ số sau dấu thập phân, không nhằm đặt số mũ thành bội của 3.

Một phương thức khác dễ nhầm là `scaleByPowerOfTen(n)`:

~~~java
BigDecimal a = new BigDecimal("123");
BigDecimal b = a.scaleByPowerOfTen(3); // giá trị 123000
~~~

`scaleByPowerOfTen(3)` **thực sự thay đổi giá trị** bằng cách nhân `10^3`. Nó không phải công cụ đổi cách viết số 123 sang engineering notation mà giữ nguyên giá trị.

## 10. Ví dụ ứng dụng và lựa chọn API

Giả sử một cảm biến ghi dòng điện bằng ampere:

~~~java
BigDecimal currentAmpere = new BigDecimal("0.000000123");
String engineering = currentAmpere.toEngineeringString();

System.out.println(engineering + " A"); // 123E-9 A
~~~

`123E-9 A` và `0.000000123 A` cùng giá trị. Nếu muốn đầu ra là `123 nA`, ứng dụng phải tự chọn **tiền tố đơn vị** và xử lý quy đổi theo hợp đồng kỹ thuật; `toEngineeringString()` không thêm `n`, `μ`, `m`, `k` hoặc `M`.

Những trường hợp sử dụng phù hợp gồm báo cáo điện/điện tử, biểu diễn đại lượng vật lý trải dài nhiều bậc độ lớn, dữ liệu đo lường và các bảng kỹ thuật quen đọc theo bội của 1000.

| Nhu cầu | Phương thức / hướng xử lý |
|---|---|
| Chuỗi chuẩn có thể parse lại và bảo toàn scale | `toString()` |
| Chuỗi không chứa ký pháp `E` | `toPlainString()` |
| Khi in số mũ, muốn số mũ là bội số 3 | `toEngineeringString()` |
| Luôn bắt buộc số mũ engineering, kể cả số nguyên thông thường | Bộ định dạng riêng với quy tắc rõ ràng |
| Giới hạn số chữ số có nghĩa | `round(MathContext)` trước khi xuất chuỗi |
| Đặt số chữ số thập phân cố định | `setScale(scale, mode)` đúng theo nghiệp vụ |
| Đổi đơn vị, thêm tiền tố SI | Logic xử lý đơn vị riêng, sau khi xác định giá trị và bậc SI |

Trong API, JSON, CSV và lưu trữ, hãy phân biệt ba điều: (1) client có chấp nhận chuỗi số mũ hay không, (2) có cần bảo toàn `scale` hay không, và (3) có cần tuân theo locale hay đơn vị của người dùng hay không. `toEngineeringString()` dùng cú pháp số Java (dấu chấm và `E`), nhưng điều đó không đồng nghĩa mọi giao thức ngoài hệ thống đều chấp nhận dạng này.

## 11. Những lỗi thường gặp

| Nhận định sai | Thực tế | Cách tránh |
|---|---|---|
| "Gọi engineering là lúc nào cũng có E" | `new BigDecimal("1000")` vẫn trả `1000` | Kiểm tra nhu cầu có bắt buộc số mũ hay không |
| "Dùng engineering sẽ làm tròn" | Phương thức chỉ tạo chuỗi | Làm tròn riêng bằng context hoặc scale |
| "`10E+3` là 10 nghìn khác `1E+4`" | Cùng giá trị 10000 | Kiểm tra định trị × `10^số_mũ` |
| "Số mũ âm không theo bội ba" | `-3`, `-6`, `-9` là bội ba | Xét cả mũ âm |
| "Chuỗi engineering parse lại luôn equals bản gốc" | Có thể đổi `scale` | Dùng `toString()` nếu cần round trip biểu diễn |
| "Số 0 tuân theo chuẩn định trị của số khác 0" | `0.00E+9` là kết quả hợp lệ | Xử lý zero riêng |
| "`stripTrailingZeros` chỉ đổi chuỗi" | Trả đối tượng có thể đổi scale | Kiểm tra tác động đến equals / định dạng |
| "Engineering có sẵn đơn vị kilo/micro" | Chỉ có số mũ, không có đơn vị | Viết logic quy đổi đơn vị riêng |
| "`toPlainString` parse lại luôn giữ scale" | Scale âm mất đi | Chọn `toString` khi cần bảo toàn scale |
| "Thấy E+6 thì biết BigDecimal đã dùng double" | Chuỗi `E` là ký pháp thập phân, không hàm ý kiểu `double` | Tách việc biểu diễn chuỗi khỏi kiểu dữ liệu |

## 12. Bài tập tự kiểm tra

**Bài 1.** `new BigDecimal("1E+8").toEngineeringString()` là gì?

**Đáp án:** `100E+6`, vì `1 × 10^8 = 100 × 10^6`. Số mũ 6 chia hết cho 3.

**Bài 2.** Vì sao `new BigDecimal("1E-7").toEngineeringString()` là `100E-9` chứ không phải `1E-6`?

**Đáp án:** `1E-6` lớn gấp mười lần `1E-7`. Phải tăng định trị thành `100` và giảm mũ xuống `-9` để giữ nguyên giá trị.

**Bài 3.** Vì sao hai số cùng bằng 1000 mà `new BigDecimal("1000").toEngineeringString()` là `1000`, còn `new BigDecimal("1E+3").toEngineeringString()` là `1E+3`?

**Đáp án:** `BigDecimal` giữ scale khác nhau (0 so với -3). Quy tắc in số mũ xét biểu diễn, không chỉ độ lớn của giá trị.

**Bài 4.** Parse `"10E+3"` rồi so với `new BigDecimal("1E+4")` bằng `equals()` có nhận `true` không?

**Đáp án:** Không. Hai số có cùng giá trị nhưng scale -3 và -4. `compareTo() == 0` nhận `true`.

**Bài 5.** Khi cần luôn in engineering notation với `E` cho số `123456789`, có chỉ gọi `toEngineeringString()` được không?

**Đáp án:** Không. Với đối tượng có scale 0 ấy, Java chọn dạng thường. Cần một công cụ format bắt buộc, xác định rõ precision/rounding và hình thức đầu ra.

**Bài 6.** Mô tả kết quả `new BigDecimal("0E+7").toEngineeringString()`.

**Đáp án:** `0.00E+9`. Giá trị vẫn là 0, số mũ 9 là bội của 3; các chữ số 0 trong định trị hỗ trợ biểu đạt scale của số 0.

---

**Ghi nhớ:** `toEngineeringString()` là phép **chuyển sang chuỗi**; nếu chuỗi dùng ký hiệu `E`, số mũ sẽ là bội của 3. Giá trị số không đổi, nhưng parse ngược từ chuỗi có thể tạo `BigDecimal` với scale khác. Chọn `toString()` cho round trip bảo toàn scale, `toPlainString()` để không in `E`, và `toEngineeringString()` để trình bày theo ký pháp kỹ thuật khi phù hợp.

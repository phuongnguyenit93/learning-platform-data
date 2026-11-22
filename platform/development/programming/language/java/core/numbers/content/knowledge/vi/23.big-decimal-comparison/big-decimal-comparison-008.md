# Kiểm tra số 0 bằng signum() hoặc compareTo() trong Java BigDecimal

## 1. Mục tiêu: kiểm tra giá trị số, không nhầm với cách biểu diễn

Khi làm việc với `java.math.BigDecimal`, ta thường cần xác định một số có bằng 0 hay không: số dư tài khoản có hết không, kết quả phép trừ đã về 0 chưa, một lượng thay đổi có âm/dương/không đổi không, hoặc có nên thực hiện phép chia cho một mẫu số hay không.

Hai cách diễn đạt trực tiếp, chính xác là:

~~~java
value.signum() == 0
value.compareTo(BigDecimal.ZERO) == 0
~~~

Cả hai đều kiểm tra **giá trị số bằng 0**, bất kể đối tượng `BigDecimal` đang có scale nào. Đây là điều khác với `value.equals(BigDecimal.ZERO)`: `equals` còn kiểm tra **scale**, vì vậy có thể trả về `false` dù giá trị số đúng bằng 0.

Bài học tập trung vào cách chọn giữa `signum()` và `compareTo(BigDecimal.ZERO)`, phân biệt `equals`, xử lý số 0 có nhiều dạng thập phân, và các trường hợp thực tế có thể gây lỗi.

## 2. Cách 1: BigDecimal.signum()

`public int signum()` trả về **dấu của giá trị số**:

| `value.signum()` | Giá trị của `value` | Có bằng 0? |
| ---: | --- | --- |
| `-1` | Nhỏ hơn 0 | Không |
| `0` | Bằng 0 | **Có** |
| `1` | Lớn hơn 0 | Không |

Vì thế:

~~~java
boolean isZero = value.signum() == 0;
boolean isNegative = value.signum() < 0;
boolean isPositive = value.signum() > 0;
~~~

Ở đây, `value` là một `BigDecimal` đã được khai báo và không phải `null`. Không có phép làm tròn, đổi sang `double`, hay thay đổi scale. `signum()` trả kết quả đúng `-1`, `0`, hoặc `1`.

Các ví dụ:

| Giá trị được tạo | `signum()` | Giải thích |
| --- | ---: | --- |
| `new BigDecimal("0")` | `0` | Số 0 |
| `new BigDecimal("0.000")` | `0` | Nhiều chữ số 0 vẫn là 0 |
| `new BigDecimal("-0.00")` | `0` | Không có giá trị số âm 0 riêng biệt trong BigDecimal |
| `new BigDecimal("0.0000000001")` | `1` | Rất nhỏ nhưng vẫn lớn hơn 0 |
| `new BigDecimal("-0.0000000001")` | `-1` | Rất nhỏ nhưng vẫn âm |
| `new BigDecimal("100.0")` | `1` | Dương |

Ưu điểm của `signum()`: diễn đạt ngắn gọn câu hỏi “giá trị đang âm, dương hay bằng 0?” và không cần tạo hay truyền một đối tượng mốc để so sánh.

## 3. Cách 2: BigDecimal.compareTo(BigDecimal.ZERO)

`compareTo(BigDecimal other)` so sánh **giá trị số** của hai `BigDecimal`. Khi `other` là `BigDecimal.ZERO`, ý nghĩa của kết quả là:

~~~java
boolean isZero = value.compareTo(BigDecimal.ZERO) == 0;
boolean isNegative = value.compareTo(BigDecimal.ZERO) < 0;
boolean isPositive = value.compareTo(BigDecimal.ZERO) > 0;
~~~

`BigDecimal.ZERO` là hằng số số 0 có sẵn trong thư viện, vì vậy không cần lặp lại `new BigDecimal("0")` mỗi lần kiểm tra. Nếu kết quả `compareTo` là âm, giá trị đứng trước nhỏ hơn số 0; nếu là 0, hai số bằng nhau về mặt số học; nếu là dương, giá trị đứng trước lớn hơn số 0.

Với mọi `BigDecimal value` không null:

~~~java
(value.signum() == 0)
        == (value.compareTo(BigDecimal.ZERO) == 0)
~~~

Hai biểu thức có cùng kết quả boolean. Tương tự, `value.signum() < 0` tương đương `value.compareTo(BigDecimal.ZERO) < 0`, và `> 0` cũng tương đương.

**Đừng so kết quả `compareTo` bằng `1` hoặc `-1` để biểu thị lớn hơn/nhỏ hơn.** Theo hợp đồng `Comparable`, chỉ cần kiểm tra kết quả **dương** hoặc **âm**. Riêng `signum()` có hợp đồng trả đúng ba giá trị `-1`, `0`, `1`, nhưng dùng `< 0` và `> 0` vẫn dễ đọc và nhất quán.

## 4. Vì sao equals(BigDecimal.ZERO) có thể trả false?

`BigDecimal` lưu số thông qua một giá trị nguyên không có scale (`unscaledValue`) và một `scale`. Giá trị toán học tương ứng là `unscaledValue × 10^(-scale)`.

Ví dụ:

| Chuỗi tạo BigDecimal | Giá trị số | `scale()` | `signum()` | `compareTo(ZERO) == 0` | `equals(ZERO)` |
| --- | ---: | ---: | ---: | --- | --- |
| `"0"` | 0 | 0 | 0 | `true` | `true` |
| `"0.0"` | 0 | 1 | 0 | `true` | `false` |
| `"0.00"` | 0 | 2 | 0 | `true` | `false` |
| `"-0.00"` | 0 | 2 | 0 | `true` | `false` |
| `"0E+3"` | 0 | -3 | 0 | `true` | `false` |

Các số trên **đều bằng 0 về mặt số học**. Nhưng `BigDecimal.ZERO` có scale 0; với `equals`, số 0 có scale 1, 2 hoặc -3 khác biểu diễn của số 0 có scale 0.

Do đó, đoạn sau dễ tạo lỗi nghiệp vụ:

~~~java
BigDecimal amount = new BigDecimal("0.00");

System.out.println(amount.equals(BigDecimal.ZERO));    // false
System.out.println(amount.signum() == 0);               // true
System.out.println(amount.compareTo(BigDecimal.ZERO) == 0); // true
~~~

Khi yêu cầu là “**số tiền này có bằng 0 hay không?**”, sử dụng `signum()` hoặc `compareTo`. Chỉ dùng `equals` nếu yêu cầu thực sự bao gồm cả sự giống nhau về **scale**, chẳng hạn kiểm tra một dạng biểu diễn thập phân cố định.

Cũng không dùng `value == BigDecimal.ZERO`: toán tử `==` giữa hai tham chiếu đối tượng kiểm tra **có phải cùng đối tượng** chứ không kiểm tra giá trị số.

## 5. Ví dụ Java 17+ đầy đủ, chạy được

Lưu chương trình sau thành `BigDecimalZeroDemo.java`.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalZeroDemo {
    private static void describe(String input) {
        BigDecimal value = new BigDecimal(input);

        int comparisonSign =
                Integer.signum(value.compareTo(BigDecimal.ZERO));

        System.out.printf(
                "%s: signum=%d, compareToZeroSign=%d, equalsZero=%s%n",
                input,
                value.signum(),
                comparisonSign,
                value.equals(BigDecimal.ZERO));
    }

    public static void main(String[] args) {
        for (String input : new String[]{
                "0", "0.00", "-0.00", "0.0001", "-0.0001"}) {
            describe(input);
        }

        BigDecimal tiny = new BigDecimal("0.004");
        BigDecimal rounded = tiny.setScale(2, RoundingMode.DOWN);

        System.out.println("tiny is zero = " + (tiny.signum() == 0));
        System.out.println("rounded = " + rounded.toPlainString());
        System.out.println("rounded is zero = " + (rounded.signum() == 0));

        BigDecimal sum = new BigDecimal("0.1")
                .add(new BigDecimal("-0.10"));

        System.out.println("sum = " + sum.toPlainString());
        System.out.println("sum compared to zero = "
                + sum.compareTo(BigDecimal.ZERO));
    }
}
~~~

Mở terminal trong thư mục chứa file, dùng JDK 17 trở lên:

~~~bash
javac BigDecimalZeroDemo.java
java BigDecimalZeroDemo
~~~

Kết quả chuẩn:

~~~text
0: signum=0, compareToZeroSign=0, equalsZero=true
0.00: signum=0, compareToZeroSign=0, equalsZero=false
-0.00: signum=0, compareToZeroSign=0, equalsZero=false
0.0001: signum=1, compareToZeroSign=1, equalsZero=false
-0.0001: signum=-1, compareToZeroSign=-1, equalsZero=false
tiny is zero = false
rounded = 0.00
rounded is zero = true
sum = 0.00
sum compared to zero = 0
~~~

Các điểm cần chú ý:

1. `Integer.signum(value.compareTo(BigDecimal.ZERO))` biến kết quả so sánh thành `-1`, `0`, hoặc `1` để tiện in minh họa; khi chỉ cần kiểm tra bằng 0, hãy viết trực tiếp `compareTo(...) == 0`.
2. `"0.00"` và `"-0.00"` đều có `signum() == 0`, nhưng `equals(BigDecimal.ZERO)` là `false` vì scale bằng 2 thay vì 0.
3. `0.0001` không phải là 0 dù rất gần 0. Kiểm tra đúng giá trị số không sử dụng sai số ngầm định.
4. Khi làm tròn `0.004` bằng `RoundingMode.DOWN` về hai chữ số sau dấu thập phân, kết quả là `0.00`. **Giá trị gốc khác 0; giá trị sau làm tròn bằng 0.**
5. Phép cộng `0.1 + (-0.10)` cho số 0 có scale 2 (`0.00`). `compareTo(BigDecimal.ZERO)` nhận diện giá trị bằng 0 chính xác, không phụ thuộc scale.

## 6. Kiểm tra số 0 trước và sau phép tính

Điểm dễ bị bỏ sót: thời điểm kiểm tra có thể thay đổi ý nghĩa.

### Kiểm tra mẫu số khác 0 trước phép chia

Nếu mẫu số là `new BigDecimal("0.000")`, `equals(BigDecimal.ZERO)` là false dù phép chia cho mẫu số đó vẫn là chia cho số 0. Kiểm tra theo giá trị số:

~~~java
static BigDecimal safeDivide(BigDecimal numerator,
                             BigDecimal denominator) {
    if (denominator.signum() == 0) {
        throw new IllegalArgumentException("Mẫu số phải khác 0");
    }
    return numerator.divide(
            denominator, 6, java.math.RoundingMode.HALF_EVEN);
}
~~~

Đây là **mảnh phương thức** đặt bên trong một lớp Java có import `BigDecimal`; giả định hai đối số không null. Scale 6 và `HALF_EVEN` chỉ minh họa một chính sách tính toán, phải thay theo yêu cầu cụ thể. Dùng `compareTo(BigDecimal.ZERO) == 0` trong điều kiện `if` cũng cho cùng hành vi.

### Kiểm tra kết quả phép trừ

~~~java
BigDecimal debit = new BigDecimal("10.00");
BigDecimal credit = new BigDecimal("10.0");
BigDecimal balance = debit.subtract(credit);

boolean fullyOffset = balance.signum() == 0; // true
~~~

Hai đầu vào có scale khác nhau nhưng kết quả bằng 0 về số học. Không cần `setScale(0)` hay `stripTrailingZeros()` để kiểm tra.

### Kiểm tra giá trị đã làm tròn

~~~java
BigDecimal original = new BigDecimal("-0.004");
BigDecimal displayed = original.setScale(2, RoundingMode.DOWN);

boolean rawZero = original.signum() == 0;        // false
boolean displayedZero = displayed.signum() == 0; // true
~~~

Cần phân biệt hai câu hỏi:

- “**Dữ liệu thật sự bằng 0?**” → kiểm tra `original`.
- “**Kết quả sau quy tắc làm tròn có bằng 0?**” → kiểm tra `displayed`.

Đừng làm tròn tùy ý để biến số nhỏ thành 0 trước khi kiểm tra, vì điều đó có thể làm mất sự khác biệt cần thiết cho nghiệp vụ.

## 7. Số 0 âm: BigDecimal không giữ dấu âm riêng cho zero

Nhiều người từng gặp `-0.0` với `double` và `float` theo chuẩn IEEE 754. Một giá trị `double` có thể mang bit dấu âm dù bằng zero khi so sánh số học. `BigDecimal` vận hành khác: số 0 có giá trị nguyên không có scale bằng 0, và `signum()` trả **0** cho cả chuỗi nhập `"0.00"` và `"-0.00"`.

~~~java
BigDecimal minusZero = new BigDecimal("-0.00");

System.out.println(minusZero.signum());       // 0
System.out.println(minusZero.toPlainString()); // 0.00
~~~

Không có cách xác định người dùng **đã gõ dấu trừ** chỉ từ dấu của đối tượng `BigDecimal` sau khi parse. Nếu việc lưu dấu âm của chuỗi gốc là một yêu cầu (ví dụ biểu mẫu cần bảo toàn chính xác nội dung nhập), phải lưu chuỗi gốc hoặc thông tin dấu như một trường riêng **trước khi chuyển đổi**.

`BigDecimal` cũng không có `NaN` hoặc vô cực như `double`. Không cần thêm trường hợp `NaN` vào quy tắc `signum() == 0`; nếu dữ liệu không phải số thập phân hợp lệ, quá trình khởi tạo từ chuỗi sẽ báo lỗi thay vì tạo `NaN`.

## 8. Giá trị cực nhỏ và “gần bằng 0” là hai yêu cầu khác nhau

`BigDecimal` có thể biểu diễn số thập phân rất nhỏ với độ chính xác cao. Ví dụ:

~~~java
BigDecimal x = new BigDecimal("0.000000000000000000000000000001");
System.out.println(x.signum() == 0); // false
~~~

Số này khác 0, nên cả hai phương pháp kiểm tra chính xác đều trả false:

~~~java
x.signum() == 0                        // false
x.compareTo(BigDecimal.ZERO) == 0      // false
~~~

Nếu bài toán thật sự yêu cầu chấp nhận **sai số cho phép** (`tolerance`), cần đặc tả một khoảng rõ ràng, chẳng hạn `-0.001 <= x <= 0.001`. Khi `tolerance` đã được xác minh **không âm**:

~~~java
BigDecimal tolerance = new BigDecimal("0.001");
BigDecimal measurement = new BigDecimal("-0.0005");

boolean nearZero =
        measurement.abs().compareTo(tolerance) <= 0;
// true: trị tuyệt đối của -0.0005 không vượt 0.001
~~~

Đây là phép kiểm tra **gần 0**, không phải **bằng 0**. Nó phụ thuộc vào đơn vị đo, độ phân giải cảm biến, quy tắc thống kê hoặc hợp đồng nghiệp vụ. Không mặc định áp dụng một epsilon tùy tiện trong các phép tính BigDecimal, đặc biệt khi xử lý tiền hoặc số dư.

Nếu `tolerance = 0`, biểu thức `abs().compareTo(tolerance) <= 0` tương đương kiểm tra bằng 0. Nếu `tolerance` âm, khoảng được định nghĩa không hợp lệ và phải từ chối hoặc xử lý theo quy tắc ứng dụng.

## 9. Chọn signum hay compareTo?

Cả hai đúng khi kiểm tra BigDecimal bằng 0, nhưng mức độ diễn đạt hơi khác:

| Mục đích | Cách viết | Gợi ý |
| --- | --- | --- |
| Chỉ kiểm tra bằng 0 | `x.signum() == 0` | Ngắn, thể hiện trực tiếp phép kiểm tra dấu |
| Kiểm tra dương, âm, bằng 0 | `x.signum() > 0`, `< 0`, `== 0` | Phù hợp khi phân nhánh theo dấu |
| Kiểm tra bằng 0 trong các biểu thức so sánh | `x.compareTo(BigDecimal.ZERO) == 0` | Đồng nhất với các so sánh ngưỡng `compareTo` khác |
| So với một ngưỡng khác 0 | `x.compareTo(threshold) >= 0` | Đây là điểm mạnh tổng quát của `compareTo` |
| So sánh giá trị và scale của đối tượng | `x.equals(other)` | Dùng khi biểu diễn là một phần của điều kiện |

Một cách viết phân nhánh dễ hiểu:

~~~java
int sign = amount.signum();

if (sign < 0) {
    System.out.println("Âm");
} else if (sign == 0) {
    System.out.println("Bằng 0");
} else {
    System.out.println("Dương");
}
~~~

Đây là mảnh code giả định `amount` đã được khởi tạo với `BigDecimal` không null. Nó tránh gọi nhiều lần khi ta cần dùng cùng kết quả dấu.

Về hiệu năng, không nên giả định một lựa chọn luôn nhanh hơn đáng kể trong mọi phiên bản JDK và mọi dạng số. Hãy chọn cách diễn đạt phản ánh chính xác ý định và chỉ tối ưu dựa trên phép đo phù hợp khi cần.

## 10. Null, đối tượng bất biến và những lỗi dễ mắc

**1. Đối tượng null.** `null` không phải giá trị số 0. Nếu `value == null`, cả `value.signum()` và `value.compareTo(BigDecimal.ZERO)` đều gây `NullPointerException`. Hãy kiểm tra đầu vào hoặc sử dụng `Objects.requireNonNull(value)` theo hợp đồng API. Không mặc định biến null thành zero khi chưa được quy định.

**2. Dùng equals để kiểm tra số 0.** `new BigDecimal("0.00").equals(BigDecimal.ZERO)` là false do scale khác. Chuyển sang `signum() == 0` hoặc `compareTo(ZERO) == 0` khi so giá trị số.

**3. Dùng toán tử == với BigDecimal.** `value == BigDecimal.ZERO` là so tham chiếu đối tượng, không so giá trị. Một đối tượng `BigDecimal` mới biểu diễn số 0 sẽ không được nhận diện đáng tin theo cách này.

**4. Cắt xuống int rồi kiểm tra.** `new BigDecimal("0.5").intValue() == 0` là true nhưng giá trị gốc không phải 0. `intValue()` có thể bỏ phần thập phân hoặc gây mất thông tin; không dùng để kiểm tra zero.

**5. Chuyển sang double.** Không cần `value.doubleValue() == 0.0`. Những số `BigDecimal` có độ lớn cực nhỏ có thể **underflow thành 0.0** khi chuyển sang `double`, dù giá trị gốc khác 0. Kiểm tra trực tiếp bằng `signum`/`compareTo`.

**6. Làm tròn trước khi kiểm tra mà không chủ đích.** `0.004` làm tròn về scale 2 với `DOWN` thành `0.00`; phải xác định yêu cầu nói về số gốc hay số sau làm tròn.

**7. Tưởng số 0 âm có `signum() == -1`.** `BigDecimal("-0.00")` có `signum() == 0`. Không thể suy ra dấu trừ từ dữ liệu đã parse.

**8. Chuẩn hóa để giải quyết một phép kiểm tra đơn giản.** `value.stripTrailingZeros().equals(BigDecimal.ZERO)` có thể nhận diện số 0, nhưng tạo ra bước xử lý biểu diễn không cần thiết. Khi chỉ hỏi giá trị bằng 0, dùng `signum() == 0` cho rõ nghĩa.

**9. Nhầm điều kiện bằng 0 với “số đủ nhỏ”.** `0.0001` vẫn khác 0. Nếu cần ngưỡng gần 0, đưa ngưỡng thành dữ liệu nghiệp vụ và so `abs()` với ngưỡng rõ ràng.

## 11. Bài luyện tập có đáp án

Với từng giá trị dưới đây, dự đoán `signum()`, `compareTo(BigDecimal.ZERO) == 0` và `equals(BigDecimal.ZERO)`:

| Giá trị | signum | compareTo zero == 0 | equals ZERO |
| --- | ---: | --- | --- |
| `new BigDecimal("0")` | 0 | true | true |
| `new BigDecimal("0.000")` | 0 | true | false |
| `new BigDecimal("-0.000")` | 0 | true | false |
| `new BigDecimal("0.00000001")` | 1 | false | false |
| `new BigDecimal("-0.00000001")` | -1 | false | false |
| `new BigDecimal("10").subtract(new BigDecimal("10.00"))` | 0 | true | false |

Bài tập ứng dụng:

1. Viết `boolean isZero(BigDecimal amount)` trả true cho `0`, `0.000`, `-0.00`, nhưng false cho `0.000001`. Nêu rõ hành vi khi `amount == null`.
2. Viết điều kiện chỉ cho phép chia khi `denominator.signum() != 0`. Thử với mẫu số `"0.000"` và `"-0.00"`.
3. Tính `new BigDecimal("0.009").setScale(2, RoundingMode.DOWN)`. Giá trị ban đầu có bằng 0 không? Giá trị kết quả có bằng 0 không?
4. Viết kiểm tra “gần 0” với `tolerance = 0.01`, phân biệt rõ với kiểm tra bằng 0 chính xác.

Một cách triển khai bài 1 khi null không hợp lệ:

~~~java
static boolean isZero(BigDecimal amount) {
    return java.util.Objects.requireNonNull(amount, "amount").signum() == 0;
}
~~~

Đây là **mảnh phương thức** cần đặt trong một lớp Java, có import `java.math.BigDecimal`. Với bài 3, `0.009` sử dụng `DOWN` ở scale 2 trở thành `0.00`, nên giá trị gốc không bằng 0, còn giá trị sau làm tròn bằng 0.

**Ghi nhớ:** Với `BigDecimal`, `value.signum() == 0` và `value.compareTo(BigDecimal.ZERO) == 0` đều xác định **bằng 0 theo giá trị số**. `equals(BigDecimal.ZERO)` kiểm tra thêm scale và có thể sai mục đích. Luôn xác định giá trị cần so sánh là số gốc hay số sau biến đổi/làm tròn, và phân biệt rõ bằng 0 chính xác với gần 0 theo ngưỡng.

# Chia hai int trước khi chuyển sang double: vì sao mất phần thập phân?

## 1. Lỗi điển hình

Trong Java, đoạn code sau **không cho ra 3.5**:

~~~java
int numerator = 7;
int denominator = 2;
double ratio = numerator / denominator;

System.out.println(ratio); // 3.0
~~~

Dù biến đích có kiểu `double`, phép chia `numerator / denominator` được Java thực hiện **trước**, trên **hai toán hạng `int`**, nên dùng **phép chia nguyên** và cho kết quả `3`. Sau đó `3` mới được chuyển thành `3.0` khi gán cho `ratio`. Phần `0.5` đã bị bỏ và phép chuyển đổi về sau không thể khôi phục.

Cách sửa đúng theo mục tiêu tính tỷ số thực:

~~~java
double ratio = (double) numerator / denominator; // 3.5
~~~

Dòng trên chuyển **một toán hạng** sang `double` **trước phép chia**. Phép `/` khi đó áp dụng **binary numeric promotion** và tính phép chia dấu phẩy động, cho kết quả `3.5`.

Bài này tập trung vào thứ tự đánh giá biểu thức, quy tắc ép kiểu, các lỗi xảy ra khi tính trung bình/phần trăm/tiến độ, chia số âm, chia cho 0, các trường hợp overflow, và khi nào `double` vẫn không đủ chính xác.

## 2. Kiểu toán hạng quyết định kiểu phép chia

Trong Java, dấu `/` áp dụng cho các kiểu số primitive; trước khi tính, Java thực hiện các quy tắc **binary numeric promotion**. Nói đơn giản:

- Nếu một toán hạng là `double`, phép toán dùng `double`.
- Nếu không có `double` nhưng có `float`, dùng `float`.
- Nếu không có `double`/`float` nhưng có `long`, dùng `long`.
- Còn lại, các kiểu số nguyên nhỏ như `byte`, `short`, `char` được nâng thành `int` và phép toán dùng `int`.

**Điểm quyết định là kiểu của biểu thức ngay tại toán tử `/`**, không phải kiểu của biến được gán kết quả sau đó.

| Biểu thức | Kiểu phép chia | Kết quả | Giải thích |
|---|---|---|---|
| `7 / 2` | `int` | `3` | Bỏ phần thập phân |
| `7L / 2` | `long` | `3L` | Có `long` nhưng vẫn là chia nguyên |
| `7.0 / 2` | `double` | `3.5` | Literal `7.0` là double |
| `7 / 2.0` | `double` | `3.5` | Literal `2.0` là double |
| `7f / 2` | `float` | `3.5f` | Literal có hậu tố `f` |
| `(double) 7 / 2` | `double` | `3.5` | Ép toán hạng trước khi chia |
| `(double) (7 / 2)` | `int` rồi ép `double` | `3.0` | Ép **kết quả đã bị cắt phần dư** |
| `7 / (double) 2` | `double` | `3.5` | Ép toán hạng bên phải trước |
| `7 / 2 * 1.0` | `int` ở phép chia đầu | `3.0` | Phần lẻ mất trước khi nhân |
| `7 * 1.0 / 2` | `double` ở phép chia | `3.5` | Chuyển sang double từ phép nhân đầu |

`int` và `long` khác độ rộng số nguyên; tăng độ rộng sang `long` **không tự tạo kết quả thập phân**. `float` và `double` cho phép biểu diễn phân số nhưng là số dấu phẩy động nhị phân với độ chính xác hữu hạn.

### Vì sao kiểu đích không ảnh hưởng ngược lại?

Xét:

~~~java
double result = 7 / 2;
~~~

Phân tích theo thứ tự:

1. Java suy ra literal `7` và `2` đều là `int`.
2. Phép `/` được tính là phép chia `int`: `7 / 2 == 3`.
3. Gán cho biến `double` kích hoạt widening primitive conversion: `3` thành `3.0`.

Không có bước nào xem `result` rồi “quay lại” thực hiện phép chia bằng double. Tương tự:

~~~java
double result = 7 / 2;           // 3.0
double result2 = (double) (7 / 2); // 3.0
double result3 = (double) 7 / 2;   // 3.5
~~~

Với ba biểu thức này, Java có thể gán kết quả cho `double` ở cả ba trường hợp; nhưng chỉ biểu thức thứ ba dùng chia dấu phẩy động ngay từ đầu.

## 3. Vị trí dấu ngoặc và ép kiểu làm thay đổi kết quả

So sánh hai cách đặt dấu ngoặc:

~~~java
int a = 7;
int b = 2;

double wrong = (double) (a / b);  // 3.0
double right = ((double) a) / b;  // 3.5
~~~

Ở `wrong`, ngoặc tròn `(a / b)` buộc thực hiện phép chia nguyên trước. Ở `right`, ngoặc `((double) a)` chỉ bao toán hạng `a`, khiến `a` thành `double` khi dấu `/` được đánh giá.

Có thể ép **một trong hai toán hạng**:

~~~java
double x = (double) a / b; // 3.5
double y = a / (double) b; // 3.5
double z = a / 2.0;        // 3.5
~~~

Trường hợp số chia đến từ biến, ép kiểu rõ ràng trên `a` hoặc `b` dễ đọc và tránh vô tình thay đổi công thức khi giá trị literal không còn cố định.

### Toán tử cùng ưu tiên được đánh giá từ trái sang phải

Nhân và chia có cùng mức ưu tiên, kết hợp từ trái sang phải:

~~~java
double lost = 7 / 2 * 100.0; // 300.0
double good = 7 * 100.0 / 2; // 350.0
~~~

Ở `lost`, Java đã thực hiện `7 / 2 == 3` rồi mới nhân `100.0`. Việc xuất hiện `double` ở **phía sau** không cứu phần thập phân đã mất. Trong `good`, phép nhân `7 * 100.0` sinh double trước, nên phép chia tiếp theo cũng dùng double.

Điều tương tự xuất hiện trong code thực tế:

~~~java
int completed = 3;
int total = 8;

double incorrectPercent = 100.0 * (completed / total); // 0.0
double correctPercent = 100.0 * completed / total;     // 37.5
~~~

Cách có ngoặc đầu tiên tính `3 / 8 == 0`, rồi nhân 100; cách đúng nhân với `100.0` trước, cho tỷ lệ thực `37.5%`.

Để dễ review, còn có thể biểu đạt trực tiếp:

~~~java
double fraction = (double) completed / total;
double percent = fraction * 100.0;
~~~

Với dữ liệu quan trọng, cần quyết định tiếp có chấp nhận độ chính xác của `double` hay dùng số thập phân chính xác như `BigDecimal`.

## 4. Chương trình Java 17+ chạy độc lập

Lưu file tên **`IntegerDivisionDemo.java`**:

~~~java
public class IntegerDivisionDemo {
    public static void main(String[] args) {
        int numerator = 7;
        int denominator = 2;

        double wrong = (double) (numerator / denominator);
        double correct = (double) numerator / denominator;

        System.out.println("wrong = " + wrong);
        System.out.println("correct = " + correct);
        System.out.println("right operand cast = "
                + numerator / (double) denominator);
        System.out.println("literal double = " + numerator / 2.0);

        System.out.println("-7 / 2 = " + (-numerator / denominator));
        System.out.println("-7 % 2 = " + (-numerator % denominator));
        System.out.println("floorDiv(-7, 2) = "
                + Math.floorDiv(-numerator, denominator));
        System.out.println("floorMod(-7, 2) = "
                + Math.floorMod(-numerator, denominator));

        int completed = 3;
        int total = 8;
        System.out.println("wrong percent = "
                + 100.0 * (completed / total));
        System.out.println("correct percent = "
                + 100.0 * completed / total);

        int zero = 0;
        try {
            int ignored = numerator / zero;
            System.out.println(ignored);
        } catch (ArithmeticException expected) {
            System.out.println(
                    "integer divide by zero: ArithmeticException");
        }

        System.out.println("double divide by zero = " + numerator / 0.0);
        System.out.println("double zero by zero = " + 0.0 / 0.0);
        System.out.println("MAX/MIN edge = "
                + (Integer.MIN_VALUE / -1));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac IntegerDivisionDemo.java
java IntegerDivisionDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
wrong = 3.0
correct = 3.5
right operand cast = 3.5
literal double = 3.5
-7 / 2 = -3
-7 % 2 = -1
floorDiv(-7, 2) = -4
floorMod(-7, 2) = 1
wrong percent = 0.0
correct percent = 37.5
integer divide by zero: ArithmeticException
double divide by zero = Infinity
double zero by zero = NaN
MAX/MIN edge = -2147483648
~~~

Ví dụ vừa chỉ ra thứ tự ép kiểu, vừa phân biệt phép chia nguyên âm và chia số thực cho 0. Kết quả `Integer.MIN_VALUE / -1` là một ngoại lệ overflow của phép chia nguyên có quy tắc riêng trong Java; phần 7 giải thích chi tiết.

## 5. Chia nguyên không làm tròn xuống âm vô cực

Khi hai toán hạng `int` hoặc `long`, phép chia dùng thương nguyên **bỏ phần lẻ theo hướng về 0** (truncate toward zero), không phải luôn dùng `Math.floor`.

~~~java
System.out.println(7 / 2);    // 3
System.out.println(-7 / 2);   // -3
System.out.println(7 / -2);   // -3
System.out.println(-7 / -2);  // 3
~~~

Theo số thực:

- `7 / 2 = 3.5`, bỏ phần lẻ được `3`.
- `-7 / 2 = -3.5`, bỏ phần lẻ về 0 được `-3`. Nếu làm tròn xuống âm vô cực thì là `-4`.

Java cung cấp `Math.floorDiv` khi yêu cầu phép chia **làm tròn xuống âm vô cực**:

~~~java
int truncated = -7 / 2;               // -3
int floored = Math.floorDiv(-7, 2);   // -4
~~~

Nếu cần phần dư tương ứng với thương floor, dùng `Math.floorMod`. Phân biệt:

~~~java
System.out.println(-7 % 2);            // -1
System.out.println(Math.floorMod(-7, 2)); // 1
~~~

`/` và `%` của `int` tuân theo quy tắc Java: ngoại trừ trường hợp overflow `MIN_VALUE / -1`, phép chia thương `q = a / b` và dư `r = a % b` thỏa `a == b * q + r` trong số học nguyên theo hợp đồng, với `|r| < |b|` và phần dư có cùng dấu với số bị chia hoặc bằng 0. Với `floorDiv`/`floorMod`, chọn cặp đó cùng nhau khi nghiệp vụ đòi phân hoạch theo hướng âm vô cực.

**Đừng dùng `(int) ((double) a / b)` để tự triển khai `floorDiv`.** Ép kiểu từ double về int cũng cắt phần lẻ về 0 (và có quy tắc riêng khi overflow/NaN). Nếu cần phép chia nguyên có floor semantics, gọi API phù hợp.

## 6. Lỗi thực tế trong trung bình, phần trăm và các công thức

### 6.1. Tính điểm trung bình

~~~java
int totalScore = 17;
int subjects = 4;

double wrongAverage = totalScore / subjects;          // 4.0
double correctAverage = (double) totalScore / subjects; // 4.25
~~~

Việc gán cho `double` không tự làm biểu thức `totalScore / subjects` trở thành phép chia double. Nếu chỉ muốn phần nguyên, có thể dùng `int quotient = totalScore / subjects` một cách có chủ đích và đặt tên biến thể hiện ý nghĩa.

### 6.2. Tính tỷ lệ hoàn thành

~~~java
int done = 3;
int planned = 8;

double wrongRatio = done / planned;            // 0.0
double correctRatio = (double) done / planned; // 0.375
double correctPercent = correctRatio * 100;   // 37.5
~~~

Sai lầm nghiêm trọng khi chỉ có một phần công việc hoàn tất: tỷ lệ đúng khác 0 nhưng phép chia nguyên cho 0, khiến hiển thị **0%**. Với điều kiện `planned == 0`, cần xác định quy tắc ứng dụng: trả trạng thái “chưa có kế hoạch”, báo lỗi, hoặc một giá trị quy ước được tài liệu hóa; không tự chia cho 0.

### 6.3. Trung bình cộng của hai int lớn

Ép đúng kiểu ở phép chia vẫn **chưa đủ** nếu phép cộng ở trước đã overflow:

~~~java
int a = Integer.MAX_VALUE;
int b = Integer.MAX_VALUE;

double wrong = (a + b) / 2.0;        // -1.0: a+b overflow trước
double right = ((double) a + b) / 2.0; // 2.147483647E9
~~~

Trong `wrong`, `a + b` là phép cộng `int`, overflow từ `4294967294` (toán học) xuống `-2` theo wraparound 32 bit; `-2 / 2.0` bằng `-1.0`. Biến đích double hoặc divisor 2.0 không sửa được phép cộng đã overflow.

Một cách khác là nâng lên `long` **trước khi cộng**:

~~~java
double exactSumThenDivide =
        ((long) a + b) / 2.0; // 2.147483647E9
~~~

Với hai giá trị kiểu `int`, tổng luôn nằm trong miền `long`, nên tổng không overflow long; phép chia `2.0` sau đó là double. Nhưng nếu ngay từ đầu hai toán hạng đã là long gần cực trị, ngay cả phép cộng long cũng có thể overflow; khi đó cần thiết kế phù hợp hơn, chẳng hạn kiểm soát overflow hoặc dùng `BigInteger`.

### 6.4. Phân trang và làm tròn số trang

Với `itemCount = 10` và `pageSize = 3`, số trang cần là **4**, không phải 3.

~~~java
int itemCount = 10;
int pageSize = 3;

int wrongPages = itemCount / pageSize; // 3
int correctPages = itemCount / pageSize
        + (itemCount % pageSize == 0 ? 0 : 1); // 4
~~~

Công thức trên đúng khi `itemCount >= 0`, `pageSize > 0`. Nó tránh việc chuyển sang double và tránh overflow của công thức thường gặp `(itemCount + pageSize - 1) / pageSize` khi `itemCount + pageSize - 1` vượt giới hạn int. Nếu chỉ cần số lượng trang nguyên, không có lý do bắt buộc phải dùng double; hãy chọn phép chia nguyên cùng chính sách làm tròn lên thích hợp.

Tương tự, khi tính “bao nhiêu bucket đủ chứa n phần tử”, điều quan trọng không chỉ là sửa sang double mà là xác định **kết quả mong muốn có phải số nguyên làm tròn lên hay không**.

## 7. Chia cho 0: int và double có hợp đồng khác nhau

Với số nguyên:

~~~java
int denominator = 0;
// int invalid = 1 / denominator; // ném ArithmeticException khi thực thi
~~~

Phép chia nguyên cho 0 gây `ArithmeticException`. Một biểu thức hằng `1 / 0` cũng không nên đưa vào code như một giá trị hợp lệ; đừng dựa vào việc IDE/compiler phát hiện hay không trong mọi ngữ cảnh để thay thế kiểm tra input.

Khi có toán hạng `double` hoặc `float`, Java tuân theo quy tắc dấu phẩy động IEEE 754 đối với chia cho 0:

~~~java
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(-1.0 / 0.0); // -Infinity
System.out.println(0.0 / 0.0);  // NaN
~~~

Đây là các giá trị dấu phẩy động đặc biệt, **không giống lỗi chia nguyên**. Chính sách nghiệp vụ có thể yêu cầu từ chối divisor 0 trong cả hai trường hợp. Nếu biểu thức thành `Infinity` hoặc `NaN` rồi lan qua các bước sau, báo cáo/tính toán có thể bị hỏng mà không có exception.

**Luôn quyết định đầu vào 0 có hợp lệ không.** Ví dụ hàm tỷ lệ chỉ có ý nghĩa với tổng lớn hơn 0:

~~~java
static double completionRatio(int completed, int total) {
    if (total <= 0) {
        throw new IllegalArgumentException("total must be positive");
    }
    return (double) completed / total;
}
~~~

Đây là **phương thức minh họa**, đặt trong class, không phải chương trình có `main` độc lập. Nếu `completed` có thể âm hoặc lớn hơn `total` thì domain cũng cần quy định có từ chối hay không; việc ép kiểu không thay thế validation.

## 8. Một toán hạng double có thể gây sai số nhị phân

Chuyển toán hạng sang `double` sửa lỗi chia nguyên, nhưng **không biến mọi phân số thành số thập phân chính xác tuyệt đối**.

~~~java
double oneThird = (double) 1 / 3;
System.out.println(oneThird); // 0.3333333333333333
~~~

Số thực 1/3 có khai triển vô hạn, còn double chỉ có số bit độ chính xác hữu hạn nên kết quả là xấp xỉ. Tương tự, các số thập phân như 0.1 và 0.2 thường không có biểu diễn nhị phân chính xác.

Với số nguyên `int`, mọi giá trị riêng lẻ chuyển sang `double` đều biểu diễn chính xác vì double có 53 bit precision nhị phân và int chỉ có 32 bit. Nhưng kết quả **phép chia** giữa chúng vẫn có thể không biểu diễn chính xác bằng double.

Với `long`, không phải mọi số nguyên đều biểu diễn chính xác bằng double. Ví dụ:

~~~java
long large = 9_007_199_254_740_993L;  // 2^53 + 1
double converted = (double) large;
// converted là số double gần nhất, không giữ đúng từng đơn vị của large.
~~~

Nếu yêu cầu so sánh/đối soát số nguyên lớn theo giá trị chính xác, đừng chuyển sang double rồi coi mọi số là phân biệt. Dùng `long` khi kết quả thuộc phạm vi long và phép toán không overflow, hoặc `BigInteger` cho số nguyên vượt phạm vi. Với tỷ số yêu cầu độ chính xác thập phân hay quy tắc làm tròn xác định, cân nhắc `BigDecimal`.

### Khi cần BigDecimal

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal numerator = BigDecimal.valueOf(7);
BigDecimal denominator = BigDecimal.valueOf(2);
BigDecimal exact = numerator.divide(denominator);

System.out.println(exact); // 3.5

BigDecimal oneThird = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3), 4, RoundingMode.HALF_UP);
System.out.println(oneThird); // 0.3333
~~~

Đoạn này nằm trong một phương thức, giả định import đã khai báo. `BigDecimal.divide(divisor)` không truyền rounding mode chỉ thành công khi thương có biểu diễn thập phân hữu hạn; với `1/3` phải chỉ định scale/rounding hoặc MathContext phù hợp. Chọn số chữ số làm tròn dựa trên yêu cầu thực, không mặc định luôn 4.

**Tránh** khởi tạo tiền bằng `new BigDecimal(0.1)` vì giá trị đầu vào `double` đã gần đúng nhị phân. Đối với dữ liệu tiền tệ, ưu tiên parse chuỗi thập phân, đơn vị nguyên nhỏ nhất, hoặc phép tính BigDecimal được thiết kế ngay từ đầu.

## 9. Ép kiểu trước hoặc sau còn ảnh hưởng overflow và precision

Quy tắc tổng quát: **mọi phép toán xảy ra trước cast giữ ngữ nghĩa của kiểu đang áp dụng**, kể cả overflow, chia nguyên và sai số float.

| Biểu thức | Điều gì xảy ra trước | Hậu quả |
|---|---|---|
| `(double) (a / b)` | Chia int | Phần lẻ mất |
| `(double) a / b` | Cast a sang double | Có phần lẻ nếu thương cần |
| `(double) (a + b) / 2` | Cộng int | Có thể overflow trước cast |
| `((double) a + b) / 2` | Cast a sang double trước cộng | Tránh overflow int tại phép cộng đó, nhưng dùng số thực |
| `(long) (a * b)` | Nhân int | Có thể overflow trước cast |
| `(long) a * b` | Cast a sang long trước nhân | Nhân long, nhưng vẫn có giới hạn long |
| `(float) a / b` | Chia float | Có phần lẻ nhưng precision thấp hơn double |
| `a / (long) b` | Chia long | Vẫn cắt phần thập phân |

Ví dụ cụ thể lỗi nhân trước khi ép:

~~~java
int a = 50_000;
int b = 50_000;

long wrong = (long) (a * b);  // -1794967296 vì int overflow
long right = (long) a * b;    // 2500000000
~~~

Phần này mở rộng nguyên tắc từ phép chia sang phép nhân để tránh cùng dạng sai lầm: **cast đúng kiểu nhưng quá muộn**. Trong Java, nếu phép toán phải chính xác và có thể vượt kiểu hiện tại, hãy nâng kiểu hoặc dùng phép kiểm tra overflow **trước phép toán**.

## 10. Chọn cách tính theo ý nghĩa nghiệp vụ

Tùy mục tiêu, không phải lúc nào cũng nên chuyển sang double:

| Mục tiêu | Ví dụ giải pháp | Lý do |
|---|---|---|
| Lấy thương nguyên và bỏ phần lẻ hướng về 0 | `int q = a / b;` | Đúng khi chỉ cần số lần chia trọn |
| Tính tỷ lệ thực gần đúng | `double r = (double) a / b;` | Tránh chia nguyên |
| Tính tỷ lệ phần trăm gần đúng | `100.0 * a / b` | Chuyển sang double trước phép chia |
| Làm tròn chia nguyên xuống âm vô cực | `Math.floorDiv(a, b)` | Đúng với số âm |
| Tính số trang cho số lượng không âm | `a / b + (a % b != 0 ? 1 : 0)` | Đếm số nhóm nguyên và làm tròn lên |
| Tính tiền chính xác theo scale/mode | `BigDecimal.divide(..., scale, mode)` | Quy tắc thập phân rõ ràng |
| Tính số nguyên lớn chính xác | `BigInteger` và phép chia của nó | Tránh mất độ chính xác khi convert double |

Các biểu thức có `a / b` yêu cầu `b != 0`; công thức đếm trang giả định `a >= 0, b > 0`. Nếu nghiệp vụ xác định trước điều kiện này, kiểm tra input ở biên dễ hiểu và an toàn hơn xử lý ngoại lệ trong nhiều tầng.

## 11. Cách kiểm thử để bắt lỗi từ lần review đầu

Không chỉ kiểm thử trường hợp chia hết, vì `6 / 2` cho kết quả `3.0` dù viết sai `double result = 6 / 2`. Một bộ test nên có:

1. **Có phần lẻ:** `7/2 → 3.5`, `1/2 → 0.5`, `3/8 → 0.375` khi yêu cầu double.
2. **Chia hết:** `8/2 → 4.0`; bảo đảm sửa cast không làm sai trường hợp đơn giản.
3. **Số âm:** `-7/2 == -3` khi dùng chia int; với double là `-3.5`; với `Math.floorDiv` là -4.
4. **Bằng 0:** `0/5 == 0`; divisor 0 được từ chối theo policy.
5. **Biên int:** `Integer.MAX_VALUE`, `Integer.MIN_VALUE`, và cộng/nhân trước chia để phát hiện overflow sớm.
6. **Lỗi thứ tự toán tử:** `100.0 * (3/8) == 0.0` và `100.0 * 3/8 == 37.5`.
7. **Độ chính xác thực:** các tỷ số khó biểu diễn (1/3) cần so sánh với tolerance phù hợp hoặc với kỳ vọng thập phân theo domain; không dùng `==` bừa bãi giữa hai công thức floating được tính theo đường khác nhau.
8. **Điểm đến của kết quả:** nếu gọi hàm trả `double` mà phần thân trả `a/b` với hai int, chữ ký hàm vẫn không ngăn lỗi. Test phải kiểm chứng kết quả số học.

Ví dụ assertion thuần Java trong một phương thức:

~~~java
int a = 7;
int b = 2;
double actual = (double) a / b;

if (Double.compare(actual, 3.5) != 0) {
    throw new AssertionError("Expected 3.5");
}
~~~

Ở đây `3.5` biểu diễn chính xác trong nhị phân nên so sánh trực tiếp đáng tin cho ca đơn lẻ. Với `1/3` hoặc chuỗi phép toán số thực dài, cần chọn cách kiểm tra dung sai hoặc reference chính xác phù hợp yêu cầu.

### Tự hỏi khi review một biểu thức chia

- Hai toán hạng tại dấu `/` hiện có kiểu gì?
- Có cần **phần lẻ** hay chỉ cần **thương nguyên**?
- Cast nằm trước phép chia hay bao **toàn bộ kết quả đã tính**?
- Các phép cộng/nhân trước đó có thể overflow?
- Divisor có thể bằng 0 không?
- Nếu dùng double, độ chính xác xấp xỉ có đủ?
- Với số âm, mong muốn truncate hay floor?
- Nếu kết quả cần biểu diễn tiền tệ, có quy tắc scale và rounding chưa?

## 12. Các lỗi phổ biến và cách sửa nhanh

**Sai:** `double avg = sum / count;` khi `sum`, `count` đều int và cần kết quả có phần lẻ.

**Đúng:** `double avg = (double) sum / count;` khi count khác 0.

**Sai:** `double avg = (double) (sum / count);` vì cast quá muộn.

**Đúng:** `double avg = sum / (double) count;` hoặc cast tử số trước.

**Sai:** `double pct = (done / total) * 100.0;` vì ngoặc ép chia nguyên trước.

**Đúng:** `double pct = ((double) done / total) * 100.0;` với total khác 0.

**Sai:** `double avg = (a + b) / 2.0;` nếu `a+b` có thể overflow int.

**Đúng:** `double avg = ((double) a + b) / 2.0;` khi phù hợp semantics double, hoặc nâng lên long trước cộng nếu phạm vi cho phép.

**Sai:** `double r = (long) a / b;` và cho rằng phép chia sẽ có phần lẻ.

**Đúng:** `double r = (double) a / b;` vì long vẫn là số nguyên.

**Sai:** dùng `Math.floorDiv` chỉ để “lấy số có dấu thập phân”.

**Đúng:** `Math.floorDiv` dành cho **thương nguyên làm tròn xuống**, còn để giữ phần lẻ phải có kiểu số thực tại phép chia.

## 13. Bài tập

**Bài 1.** Dự đoán:

~~~java
System.out.println(5 / 2);
System.out.println((double) (5 / 2));
System.out.println((double) 5 / 2);
System.out.println(5 / 2.0);
~~~

**Bài 2.** Với `a = -5` và `b = 2`, so sánh `a / b`, `(double) a / b`, `Math.floorDiv(a,b)`, `a % b` và `Math.floorMod(a,b)`.

**Bài 3.** Sửa đoạn code:

~~~java
static double percentage(int success, int total) {
    return success / total * 100;
}
~~~

Yêu cầu trả tỷ lệ `37.5` khi success=3 và total=8; từ chối total=0.

**Bài 4.** Vì sao `double x = (Integer.MAX_VALUE + Integer.MAX_VALUE) / 2.0;` không ra giá trị trung bình mong muốn? Hãy sửa mà không cộng hai int trước.

**Bài 5.** Nếu số lượng trang cần dùng phép làm tròn lên nguyên cho `items = 10, pageSize = 3`, tại sao chỉ ép sang double chưa hoàn thành yêu cầu? Hãy chọn cách tính số trang trả int.

**Đáp án tham khảo:**

1. `2`, `2.0`, `2.5`, `2.5`.
2. `-2`, `-2.5`, `-3`, `-1`, `1`.
3. Kiểm tra `total != 0` (hoặc `total > 0` theo domain), sau đó `return (double) success / total * 100.0;`.
4. Phép cộng int overflow trước khi chia. Dùng `((double) Integer.MAX_VALUE + Integer.MAX_VALUE) / 2.0` hoặc cộng long trước.
5. Số trang phải nguyên làm tròn lên; với items không âm và pageSize dương, dùng `items / pageSize + (items % pageSize == 0 ? 0 : 1)` cho kết quả 4.

## 14. Tài liệu chuẩn Java SE 17

- Java Language Specification, ``15.17.2 Division Operator /`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2
- Java Language Specification, ``5.6 Numeric Contexts` (binary numeric promotion): https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6
- Java Language Specification, ``5.1.2 Widening Primitive Conversion`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.2
- Java SE 17, `Math.floorDiv`/`floorMod`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html
- Java SE 17, `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html

**Ghi nhớ:** `double result = a / b;` với hai `int` là **chia nguyên rồi mới chuyển sang double**. Muốn giữ phần lẻ, hãy đặt `(double)` trước **ít nhất một toán hạng của phép chia** và đảm bảo không có phép toán int trước đó đã làm mất thông tin hoặc overflow.
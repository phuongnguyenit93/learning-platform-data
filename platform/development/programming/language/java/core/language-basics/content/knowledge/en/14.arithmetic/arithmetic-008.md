# Sai số nhị phân khi tính với `float` hoặc `double` — Java 17+

## 1. Hiện tượng: vì sao 0.1 + 0.2 không bằng đúng 0.3?

Trong Java, `float` và `double` lưu trữ số thực theo định dạng **dấu phẩy động nhị phân IEEE 754**. Nhiều phân số thập phân hữu hạn — như `0.1`, `0.2` và `0.3` — **không thể biểu diễn chính xác bằng một số bit nhị phân hữu hạn**.

~~~java
double a = 0.1;
double b = 0.2;
double sum = a + b;

System.out.println(sum);         // 0.30000000000000004
System.out.println(sum == 0.3);  // false
~~~

Kết quả **không phải bug của Java**. Các giá trị đầu vào đã được làm tròn tới số nhị phân biểu diễn được; phép cộng cũng tuân theo quy tắc làm tròn của dấu phẩy động. Vì vậy kết quả biểu diễn của `0.1 + 0.2` khác một chút so với biểu diễn của literal `0.3`.

Ba điều cần nắm:

1. **Số toán học** `0.1` khác với **giá trị nhị phân gần nhất** được lưu trong `double`.
2. `double` có **nhiều độ chính xác hơn `float`**, nhưng vẫn không biểu diễn chính xác mọi phân số thập phân.
3. Sai số có thể **lan truyền, tích lũy hoặc bị khuếch đại** qua các phép toán. Nếu cần tính decimal chính xác theo nghiệp vụ, nên chọn mô hình dữ liệu phù hợp thay vì chỉ tăng số chữ số hiển thị.

## 2. Vì sao có sai số? Mô hình nhị phân hữu hạn

Một phân số có biểu diễn hữu hạn trong cơ số 2 khi mẫu số sau khi rút gọn chỉ có thừa số nguyên tố **2**. Ví dụ:

| Phân số toán học | Trong hệ nhị phân | Có biểu diễn hữu hạn cơ số 2? |
|---|---|---|
| `1/2 = 0.5` | `0.1₂` | Có |
| `1/4 = 0.25` | `0.01₂` | Có |
| `3/8 = 0.375` | `0.011₂` | Có |
| `1/10 = 0.1` | Chuỗi bit lặp vô hạn | Không |
| `1/5 = 0.2` | Chuỗi bit lặp vô hạn | Không |
| `3/10 = 0.3` | Chuỗi bit lặp vô hạn | Không |

Chẳng hạn, `0.1` trong cơ số 2 phải dùng các bit lặp vô hạn. `float` và `double` có số bit hữu hạn nên lưu **giá trị xấp xỉ gần nhất** theo quy tắc làm tròn áp dụng.

~~~mermaid
flowchart TD
    A["Literal thập phân: 0.1"] --> B["Chuyển sang giá trị nhị phân biểu diễn được gần nhất"]
    B --> C["Lưu vào float hoặc double hữu hạn bit"]
    C --> D["Thực hiện phép tính dấu phẩy động"]
    D --> E["Làm tròn kết quả theo định dạng"]
    E --> F["In số thập phân đủ để round-trip"]
~~~

**Lưu ý:** dòng in `0.1` không có nghĩa máy lưu **chính xác** số thập phân 0.1. Java dùng chuyển đổi chuỗi sao cho có thể đọc lại thành cùng giá trị `double`/`float`, nên chuỗi biểu diễn có thể ngắn hơn khai triển thập phân chính xác của giá trị nhị phân bên trong.

## 3. `float` và `double`: số bit và độ chính xác

| Đặc điểm | `float` | `double` |
|---|---|---|
| Định dạng | IEEE 754 binary32 | IEEE 754 binary64 |
| Tổng số bit | 32 | 64 |
| Bit phần mũ | 8 | 11 |
| Độ chính xác significand | 24 bit, gồm bit ẩn với số chuẩn hóa | 53 bit, gồm bit ẩn với số chuẩn hóa |
| Số chữ số thập phân chính xác xấp xỉ | 6–9 chữ số có nghĩa | 15–17 chữ số có nghĩa |
| Literal thông dụng | `0.1f` | `0.1`, `0.1d` |
| Hằng mô tả bit | `Float.SIZE` | `Double.SIZE` |
| Phù hợp | Dữ liệu cho phép sai số lớn hơn/tiết kiệm lưu trữ | Tính toán dấu phẩy động thông dụng cần độ chính xác cao hơn |

`double` **không** nghĩa là “độ chính xác tuyệt đối”, và `float` cũng không phải luôn sai: cả hai có miền ứng dụng khi dung sai được xác định.

~~~java
float f = 0.1f;
double d = 0.1;

System.out.println((double) f); // 0.10000000149011612
System.out.println(d);          // 0.1
~~~

Khi đổi `float` sang `double`, bạn **mở rộng khả năng biểu diễn nhưng không khôi phục** giá trị thập phân 0.1 vốn đã được làm tròn thành giá trị `float`. Chuỗi của `double d` in là 0.1 nhưng giá trị nhị phân lưu trong `d` cũng chỉ xấp xỉ 0.1.

## 4. Literal, phép tính và kiểu biểu thức ảnh hưởng sai số

~~~java
var a = 0.1;     // Suy luận double
var b = 0.1f;    // Suy luận float
var c = 0.1d;    // double tường minh

System.out.println(a + 0.2); // 0.30000000000000004
~~~

Trong biểu thức số học hỗn hợp, Java áp dụng *binary numeric promotion*. Ví dụ:

~~~java
float f = 0.1f;
double d = 0.2;
double mixed = f + d; // float được mở rộng sang double rồi cộng
~~~

`mixed` có kiểu `double`, nhưng toán hạng `f` **vẫn mang sai số từng có khi được lưu dưới dạng float**. Không được suy rằng “kiểu kết quả là double” nên cả hai đầu vào bỗng có 53 bit độ chính xác từ đầu.

Với số nguyên lớn, conversion sang floating-point cũng có thể mất chi tiết:

~~~java
double exactLimit = 9_007_199_254_740_992d; // 2^53
System.out.println(exactLimit + 1.0 == exactLimit); // true
~~~

Ở cỡ `2^53`, `double` không còn phân biệt được mọi cặp số nguyên liên tiếp; phép cộng 1 được làm tròn trở lại cùng giá trị.

## 5. ULP và độ phân giải phụ thuộc độ lớn

**ULP** (*unit in the last place*) biểu thị khoảng cách giữa các giá trị dấu phẩy động lân cận ở một vùng nhất định. Khi độ lớn của số tăng, khoảng cách biểu diễn thường tăng tương ứng.

~~~java
System.out.println(Math.ulp(1.0));          // 2.220446049250313E-16
System.out.println(Math.ulp(16_777_216f));  // 2.0
~~~

`Math.ulp(1.0)` mô tả bước `double` tại 1.0. Với `float`, quanh giá trị `2^24 = 16_777_216`, bước là 2, nên cộng 1 có thể không làm giá trị thay đổi:

~~~java
float x = 16_777_216f;
System.out.println(x + 1f == x); // true
~~~

**Không có một epsilon cố định bảo đảm đủ tốt cho mọi phạm vi số.** Với giá trị rất lớn, chênh lệch tuyệt đối hợp lệ có thể lớn; với giá trị rất gần 0, so sánh chỉ theo sai số tương đối có thể không phù hợp.

`Float.MIN_VALUE`/`Double.MIN_VALUE` còn là giá trị **dương nhỏ nhất khác 0**, không phải số âm nhỏ nhất. Muốn giới hạn độ lớn hữu hạn hãy xem `MAX_VALUE`; muốn xét âm thì có thể dùng `-MAX_VALUE`.

## 6. `==`: so đúng giá trị nhị phân, không so độ gần

~~~java
double calculated = 0.1 + 0.2;
double expected = 0.3;

System.out.println(calculated == expected); // false
System.out.println(calculated - expected);  // 5.551115123125783E-17
~~~

Toán tử `==` so **giá trị dấu phẩy động theo quy tắc ngôn ngữ**, không có “dung sai ngầm” dành cho sai số tính toán.

Nhưng **không** được tuyên bố rằng mọi phép so `==` trên số thực đều sai:

- So với một **hằng đặc biệt có ý nghĩa chính xác** (ví dụ `value == 0.0` khi thật sự muốn đúng zero) có thể là một yêu cầu hợp lệ, nhưng cần xem cách dữ liệu được tạo ra.
- So tính đồng nhất của **giá trị biểu diễn** đôi khi là chủ ý của thuật toán.
- Nếu cần **“gần bằng nhau” về mặt đo lường hoặc nghiệp vụ**, phải định nghĩa ngưỡng sai số phù hợp thay vì `==`.

**Đừng lấy một ngưỡng tùy tiện như `1e-9` rồi cho rằng mọi miền số đều đúng.** Ngưỡng phải phản ánh đơn vị, độ lớn, sai số đầu vào và yêu cầu của hệ thống.

## 7. So sánh xấp xỉ: dung sai tuyệt đối và tương đối

Một hàm minh họa cho bài toán cần so **gần bằng nhau**:

~~~java
static boolean nearlyEqual(
        double a, double b, double absTol, double relTol) {
    if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
            || absTol < 0 || relTol < 0) {
        throw new IllegalArgumentException("invalid tolerance");
    }
    if (a == b) {
        return true; // Bao gồm +0.0/-0.0 và hai infinity cùng dấu
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false; // NaN hoặc hai giá trị hữu hạn/vô cực không bằng nhau
    }
    double diff = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return diff <= absTol || diff <= relTol * scale;
}
~~~

Ví dụ:

~~~java
System.out.println(nearlyEqual(0.1 + 0.2, 0.3, 1e-12, 1e-12)); // true
System.out.println(nearlyEqual(1.0, 1.1, 1e-12, 1e-12));       // false
~~~

**Hiểu giới hạn của hàm mẫu:** phép trừ `a-b` và phép nhân `relTol*scale` cũng là số học `double`, có thể overflow/underflow ở các cực trị; hàm này phù hợp để minh họa, không phải thư viện số học tổng quát. Với giá trị Infinity, chính sách trả `true` khi cùng Infinity ở dòng `a == b` là **lựa chọn có chủ đích**, có thể đổi thành false nếu nghiệp vụ chỉ cho phép so dữ liệu hữu hạn.

Với các phép so độ chính xác nghiêm ngặt (khoa học, mô phỏng, thống kê), nên xác định rõ *error budget* và chọn thuật toán so sánh phù hợp — đôi khi dùng ULP, sai số tương đối, sai số tuyệt đối, hoặc kết hợp.

## 8. Sai số tích lũy qua vòng lặp

Một phép cộng riêng lẻ có sai số nhỏ; nhiều lần cộng có thể tích lũy sai số:

~~~java
double total = 0.0;
for (int i = 0; i < 10; i++) {
    total += 0.1;
}
System.out.println(total); // 0.9999999999999999
System.out.println(0.1 * 10); // 1.0
~~~

Hai phép toán khác nhau về đường làm tròn:

- **Cộng 10 lần:** mỗi lần cộng có thể làm tròn giá trị tạm.
- **Nhân một lần:** dùng một phép nhân dấu phẩy động, nên chỉ có trình tự làm tròn khác.

Không được suy rằng phép nhân luôn chính xác hơn phép cộng cho mọi tập dữ liệu; đây là ví dụ về **thuật toán và thứ tự tính** ảnh hưởng sai số.

Với tổng lớn hoặc nhiều số có độ lớn khác nhau, hãy xem xét **thuật toán cộng có bù** (*compensated summation*, như Kahan) hoặc các hàm/thư viện số phù hợp, rồi kiểm thử trên dữ liệu đại diện.

## 9. Phép cộng floating-point không hoàn toàn có tính kết hợp

Trong số học toán học: `(a+b)+c = a+(b+c)`. Với `double` hữu hạn, quy tắc làm tròn sau từng bước có thể khiến hai cách nhóm trả kết quả khác nhau:

~~~java
double left = (1.0e16 + -1.0e16) + 1.0;
double right = 1.0e16 + (-1.0e16 + 1.0);

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
~~~

Lý do:

1. Vế `left` triệt tiêu hai số lớn thành 0 trước, rồi cộng 1.
2. Vế `right` cộng 1 vào `-1e16`; giá trị 1 quá nhỏ so với khoảng cách các số double quanh `1e16` nên bị làm tròn mất, rồi cộng `1e16` thành 0.

**Đừng tùy ý thay đổi thứ tự cộng** khi refactor một thuật toán số thực với giả định phép cộng hoàn toàn có tính kết hợp. Thứ tự, dấu ngoặc và thuật toán cộng đều có thể ảnh hưởng kết quả.

## 10. Triệt tiêu chữ số có nghĩa (*catastrophic cancellation*)

Một kiểu sai số khác xuất hiện khi **trừ hai số gần nhau nhưng rất lớn**:

~~~java
double a = 1.0e16 + 1.0;
double b = 1.0e16;

System.out.println(a - b); // 0.0
~~~

Về toán học, nếu `a` thực sự là `10^16 + 1` và `b` là `10^16`, hiệu sẽ là 1. Nhưng **khi `a` được tính và lưu trong double**, giá trị cộng 1 đã bị làm tròn mất, nên `a` và `b` có cùng biểu diễn, trừ ra 0.

Tình huống này thường quan trọng khi tính độ chênh của các đại lượng rất lớn, gần nhau. **Không thể khôi phục chữ số đã mất chỉ bằng cách ép `double` sang kiểu khác sau đó.** Cần cân nhắc thay đổi công thức, chuẩn hóa giá trị, dùng độ chính xác cao hơn từ **đầu vào**, hoặc mô hình số khác.

## 11. Kiểm tra kết quả số thực đặc biệt trước khi so sánh

`double` còn có `NaN`, `Infinity`, `-Infinity` và hai dạng zero có dấu. Chúng có thể xuất hiện do chia cho 0 hoặc phép toán vượt miền hữu hạn:

~~~java
System.out.println(Double.isNaN(0.0 / 0.0));    // true
System.out.println(Double.isFinite(1.0 / 0.0)); // false
System.out.println(0.0 == -0.0);                // true
~~~

`Double.isFinite` **không kiểm tra độ chính xác**: `0.1 + 0.2` vẫn hữu hạn nhưng xấp xỉ. Khi kiểm tra giá trị đầu vào, cần phân biệt dữ liệu bất hợp lệ với sai số cho phép. Bài trước đã trình bày đầy đủ quy tắc NaN, so sánh wrapper, dấu zero và underflow.

## 12. Định dạng hiển thị không sửa giá trị đã tính

~~~java
double sum = 0.1 + 0.2;

System.out.println(sum); // 0.30000000000000004
System.out.printf(java.util.Locale.ROOT, "%.2f%n", sum); // 0.30
~~~

`printf("%.2f")` hoặc `String.format` chỉ **làm tròn biểu diễn văn bản** theo định dạng đã chọn. Biến `sum` vẫn chứa giá trị `double` ban đầu.

Các nhầm lẫn cần tránh:

- Hiển thị `0.30` **không** có nghĩa số được lưu chính xác bằng 0.30 toán học.
- Gọi `Math.round(...)` không thay thế một mô hình tính tiền theo số thập phân.
- Ép `float` thành `double` **sau khi** sai số xuất hiện không khôi phục dữ liệu đã mất.

Hãy phân biệt **số được lưu**, **quy tắc tính toán** và **cách định dạng đầu ra**.

## 13. Từ sai số binary floating-point đến mô hình decimal exact

Khi nghiệp vụ cần `0.1 + 0.2` thành **0.3 đúng thập phân**, giữ nguồn thập phân chính xác ngay từ đầu:

~~~java
java.math.BigDecimal a = new java.math.BigDecimal("0.1");
java.math.BigDecimal b = new java.math.BigDecimal("0.2");
System.out.println(a.add(b)); // 0.3.
~~~

Nguồn tạo đối tượng quyết định giá trị đầu vào:

| Cách tạo | Ý nghĩa |
| --- | --- |
| `new BigDecimal("0.1")` | Lưu số thập phân đúng 0.1 |
| `BigDecimal.valueOf(0.1)` | Dựa vào dạng thập phân của `Double.toString(0.1)` |
| `new BigDecimal(0.1)` | Lưu **chính xác giá trị nhị phân xấp xỉ** đang ở `double` |

~~~java
System.out.println(
        new java.math.BigDecimal("0.1")
                .compareTo(new java.math.BigDecimal(0.1)) == 0); // false.
~~~

`BigDecimal` cũng không khiến mọi phép chia tự kết thúc. `1/3` có khai triển thập phân vô hạn, nên cần chỉ định scale/rounding hoặc `MathContext`:

~~~java
java.math.BigDecimal third = java.math.BigDecimal.ONE.divide(
        new java.math.BigDecimal("3"), 2,
        java.math.RoundingMode.HALF_UP);
System.out.println(third); // 0.33.
~~~

`BigDecimal.equals` xét **giá trị và scale**: `new BigDecimal("1.00").equals(new BigDecimal("1.0"))` trả false; `compareTo` của cặp đó trả 0. Phần ranh giới này đủ để hiểu **vì sao không thể phục hồi decimal chính xác từ một `double` đã sai số**; bài `Math.*Exact`/`BigDecimal` cuối chương đi sâu về scale, precision, làm tròn, phép chia và chuyển đổi exact.

`BigDecimal` không mặc định tốt hơn `double` trong mọi ứng dụng. Tính toán khoa học chấp nhận sai số có thể ưu tiên `double` và thuật toán ổn định. Hãy chọn theo miền, độ chính xác, đơn vị và chính sách làm tròn.


## 14. Quy trình chọn kiểu số theo bài toán

| Nhu cầu | Lựa chọn thường phù hợp | Điểm phải kiểm tra |
|---|---|---|
| Bộ đếm nguyên trong miền 32 bit | `int` | Tràn số nguyên |
| Bộ đếm lớn hơn 32 bit | `long` | Vẫn có giới hạn 64 bit |
| Đo đạc khoa học, phép tính chấp nhận sai số | `double` | Dung sai, NaN, Infinity, thuật toán |
| Dữ liệu float cho API/phần cứng yêu cầu binary32 | `float` | Độ chính xác ~24 bit significand |
| Tiền lưu bằng đơn vị nhỏ nhất cố định | `long` khi miền đủ | Đơn vị, quy đổi và overflow |
| Giá trị thập phân phải chính xác | `BigDecimal` | Tạo từ text, scale, rounding |
| Tổng rất nhiều số thực | `double` + thuật toán phù hợp | Sai số tích lũy và thứ tự tính |
| Kiểm tra gần bằng nhau | Dung sai theo nghiệp vụ | Sai số tuyệt đối/tương đối, cực trị |

**Không có “kiểu đúng cho mọi số thực”.** Quy tắc thiết kế là xác định **miền giá trị, độ chính xác yêu cầu, đơn vị đo, dung sai và quy tắc làm tròn**, rồi mới chọn kiểu và thuật toán.

## 15. Ví dụ Java 17 chạy độc lập

Tạo file chính xác **`BinaryFloatingPointErrorDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public final class BinaryFloatingPointErrorDemo {
    private BinaryFloatingPointErrorDemo() {}

    static boolean nearlyEqual(
            double a, double b, double absTol, double relTol) {
        if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
                || absTol < 0 || relTol < 0) {
            throw new IllegalArgumentException("invalid tolerance");
        }
        if (a == b) {
            return true;
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        double difference = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return difference <= absTol || difference <= relTol * scale;
    }

    public static void main(String[] args) {
        double sum = 0.1 + 0.2;
        System.out.println("double sum=" + sum);
        System.out.println("sum == 0.3=" + (sum == 0.3));
        System.out.println("difference=" + (sum - 0.3));
        System.out.println("hex 0.1=" + Double.toHexString(0.1));

        float floatApprox = 0.1f;
        System.out.println("float 0.1 as double=" + (double) floatApprox);
        System.out.println("double literal printed=" + 0.1);
        System.out.println("float ulp at 2^24=" + Math.ulp(16_777_216f));
        System.out.println("float loses one="
                + (16_777_216f + 1f == 16_777_216f));
        double limit = 9_007_199_254_740_992d;
        System.out.println("double loses one=" + (limit + 1 == limit));

        double total = 0.0;
        for (int i = 0; i < 10; i++) {
            total += 0.1;
        }
        System.out.println("sum ten times=" + total);
        System.out.println("multiply ten=" + (0.1 * 10));

        double left = (1.0e16 + -1.0e16) + 1.0;
        double right = 1.0e16 + (-1.0e16 + 1.0);
        System.out.println("group left=" + left);
        System.out.println("group right=" + right);
        System.out.println("cancellation=" + ((1.0e16 + 1.0) - 1.0e16));

        System.out.println("near 0.3="
                + nearlyEqual(sum, 0.3, 1e-12, 1e-12));
        System.out.println("far from 1.1="
                + nearlyEqual(1.0, 1.1, 1e-12, 1e-12));
        System.out.println("NaN equals itself=" + (Double.NaN == Double.NaN));
        System.out.println("is NaN=" + Double.isNaN(0.0 / 0.0));
        System.out.println("infinite finite=" + Double.isFinite(1.0 / 0.0));
        System.out.println("signed zero ==" + (0.0 == -0.0));
        System.out.println("signed zero compare="
                + (Double.compare(0.0, -0.0) == 0));

        System.out.println("formatted="
                + String.format(Locale.ROOT, "%.2f", sum));

        BigDecimal decimal = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimal exact=" + decimal);
        System.out.println("valueOf decimal="
                + BigDecimal.valueOf(0.1).add(BigDecimal.valueOf(0.2)));
        System.out.println("double constructor exact decimal="
                + (new BigDecimal(0.1)
                        .compareTo(new BigDecimal("0.1")) == 0));
        System.out.println("decimal division="
                + new BigDecimal("1").divide(
                        new BigDecimal("3"), 2, RoundingMode.HALF_UP));
        BigDecimal scaleA = new BigDecimal("1.00");
        BigDecimal scaleB = new BigDecimal("1.0");
        System.out.println("BigDecimal equals=" + scaleA.equals(scaleB));
        System.out.println("BigDecimal compare="
                + (scaleA.compareTo(scaleB) == 0));
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal đang ở thư mục chứa tệp. Không cần Maven, Gradle hoặc thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 BinaryFloatingPointErrorDemo.java
java -cp . BinaryFloatingPointErrorDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\BinaryFloatingPointErrorDemo.java
java -cp . BinaryFloatingPointErrorDemo
~~~

**Exact expected output:**

~~~text
double sum=0.30000000000000004
sum == 0.3=false
difference=5.551115123125783E-17
hex 0.1=0x1.999999999999ap-4
float 0.1 as double=0.10000000149011612
double literal printed=0.1
float ulp at 2^24=2.0
float loses one=true
double loses one=true
sum ten times=0.9999999999999999
multiply ten=1.0
group left=1.0
group right=0.0
cancellation=0.0
near 0.3=true
far from 1.1=false
NaN equals itself=false
is NaN=true
infinite finite=false
signed zero ==true
signed zero compare=false
formatted=0.30
decimal exact=0.3
valueOf decimal=0.3
double constructor exact decimal=false
decimal division=0.33
BigDecimal equals=false
BigDecimal compare=true
~~~

### Đọc kết quả theo từng nhóm

1. `double sum` và `difference` cho thấy sai lệch nhỏ nhưng có thể quan sát được; `Double.toHexString` biểu diễn giá trị lưu trong dạng hex floating-point.
2. `float 0.1 as double` cho thấy nâng một giá trị float sang double **không phục hồi** số thập phân ban đầu.
3. `float ulp at 2^24` và `double loses one` minh họa độ phân giải giảm theo độ lớn số.
4. Tổng cộng 0.1 mười lần khác với nhân 0.1 một lần; thứ tự và số lần làm tròn ảnh hưởng kết quả.
5. `group left/right` và `cancellation` minh họa không kết hợp hoàn toàn và mất chữ số có nghĩa.
6. `nearlyEqual` chỉ trả true cho hai số gần nhau theo dung sai minh họa; nó **không phải so sánh chính xác toán học**.
7. `NaN`, Infinity và signed zero có những quy tắc đặc biệt cần xử lý tường minh.
8. `formatted=0.30` chỉ là chuỗi hiển thị; `BigDecimal` từ chuỗi mới thực hiện phép cộng thập phân chính xác trong ví dụ.
9. Hai kết quả cuối nhắc rằng `BigDecimal.equals` phân biệt scale, còn `compareTo` so giá trị số.

## 16. Lỗi thường gặp và cách khắc phục

| Ngộ nhận / lỗi | Vấn đề | Cách xử lý |
|---|---|---|
| `0.1 + 0.2 == 0.3` phải true | Các số decimal không biểu diễn chính xác trong binary64 | Dùng dung sai nếu bài toán cho phép, hoặc decimal exact |
| Đổi `float` sang `double` là hết sai số | Giá trị float đã làm tròn | Chọn độ chính xác phù hợp **từ đầu** |
| In `0.1` nghĩa là lưu đúng thập phân 0.1 | `toString` dùng chuỗi round-trip | Phân biệt chuỗi hiển thị với giá trị nhị phân |
| `double` lưu được mọi số nguyên lớn | Quá 2^53 không phân biệt mọi số nguyên kề nhau | Dùng `long`/`BigInteger` theo miền |
| Một `epsilon` phù hợp mọi bài toán | Sai số phụ thuộc đơn vị và độ lớn | Xác định absolute/relative tolerance |
| Cộng 0.1 nhiều lần luôn bằng nhân một lần | Các bước làm tròn khác nhau | Kiểm thử thuật toán tổng và độ chính xác |
| Có thể đổi nhóm phép cộng số thực tùy ý | Floating-point không kết hợp hoàn toàn | Giữ thứ tự/nghiệp vụ của thuật toán |
| `(1e16 + 1) - 1e16` luôn là 1 | Mất 1 khi cộng số quá lớn | Chọn thuật toán/kiểu khác từ trước |
| NaN so bằng `==` với chính nó | `NaN == NaN` là false | Dùng `Double.isNaN` |
| Formatter `%.2f` sửa sai số tính toán | Chỉ đổi biểu diễn text | Quy định kiểu dữ liệu và rounding thực |
| `new BigDecimal(0.1)` cho decimal 0.1 | Constructor đọc chính xác giá trị double xấp xỉ | `new BigDecimal("0.1")` hoặc `valueOf` |
| `BigDecimal.divide(1/3)` luôn tự chạy | Decimal vô hạn cần quy tắc rounding | Dùng scale/MathContext phù hợp |
| `BigDecimal("1.00").equals(BigDecimal("1.0"))` | `equals` xét cả scale | `compareTo == 0` nếu muốn so giá trị |

## 17. Bài tập và đáp án

### Bài A — quan sát sai số cơ bản

~~~java
double a = 0.1 + 0.2;
System.out.println(a);
System.out.println(a == 0.3);
~~~

**Đáp án:**

~~~text
0.30000000000000004
false
~~~

### Bài B — `float` không chính xác hơn khi cast

~~~java
float value = 0.1f;
double promoted = value;
System.out.println(promoted);
~~~

**Đáp án:** `0.10000000149011612`. Chuyển sang double giữ nguyên giá trị xấp xỉ đang có trong float.

### Bài C — số nguyên lớn

~~~java
double x = 9_007_199_254_740_992d;
System.out.println(x + 1.0 == x);
~~~

**Đáp án:** `true`. Tại `2^53`, binary64 không biểu diễn được mọi số nguyên kề nhau.

### Bài D — dùng thập phân exact

~~~java
java.math.BigDecimal a = new java.math.BigDecimal("0.1");
java.math.BigDecimal b = new java.math.BigDecimal("0.2");
System.out.println(a.add(b));
~~~

**Đáp án:** `0.3`.

### Bài E — tại sao `BigDecimal` chia cần rounding?

~~~java
// new BigDecimal("1").divide(new BigDecimal("3"))
~~~

**Đáp án:** `1/3` là thập phân vô hạn; không thể biểu diễn thành số thập phân hữu hạn chính xác. Chỉ định scale và `RoundingMode`, hoặc `MathContext`, theo yêu cầu nghiệp vụ.

### Bài F — dấu ngoặc số thực

~~~java
System.out.println((1e16 + -1e16) + 1.0);
System.out.println(1e16 + (-1e16 + 1.0));
~~~

**Đáp án:**

~~~text
1.0
0.0
~~~

Sự khác biệt đến từ việc làm tròn ở các bước trung gian.

## 18. Checklist và kết luận

- [ ] Hiểu `float`/`double` biểu diễn **nhị phân hữu hạn**, không phải số thập phân tùy ý.
- [ ] Biết `0.1` và `0.2` không có biểu diễn nhị phân hữu hạn chính xác.
- [ ] Phân biệt binary32 (float) và binary64 (double), độ chính xác hữu hạn.
- [ ] Biết literal `0.1f` là float, `0.1` là double.
- [ ] Hiểu chuyển từ float sang double **không phục hồi** sai số đã phát sinh.
- [ ] Hiểu ý nghĩa ULP và việc số lớn có bước biểu diễn lớn hơn.
- [ ] Không so số đo/tính gần bằng bằng `==` nếu yêu cầu có dung sai.
- [ ] Biết chọn dung sai tuyệt đối/tương đối theo miền và đơn vị nghiệp vụ.
- [ ] Nhận diện sai số tích lũy và kết quả phụ thuộc thứ tự cộng.
- [ ] Nhận diện catastrophic cancellation khi trừ số gần nhau.
- [ ] Xử lý NaN/Infinity/signed zero rõ ràng khi cần.
- [ ] Biết định dạng số chỉ tác động **chuỗi hiển thị**.
- [ ] Biết tạo `BigDecimal` từ String khi cần decimal chính xác.
- [ ] Biết `BigDecimal.divide` cần rounding khi thương không kết thúc.
- [ ] Phân biệt `BigDecimal.equals` với `compareTo` về scale.
- [ ] Biên dịch và chạy `BinaryFloatingPointErrorDemo.java` trên JDK 17+, đối chiếu exact expected output.

**Kết luận:** Sai số của `float`/`double` là hệ quả tự nhiên của biểu diễn dấu phẩy động nhị phân hữu hạn, không phải Java tính toán ngẫu nhiên. Hãy chọn kiểu dữ liệu theo **mức chính xác và miền giá trị**, tránh so gần bằng bằng `==` một cách máy móc, cân nhắc tác động của thứ tự phép tính, và dùng `BigDecimal`/số nguyên theo đơn vị cố định nếu nghiệp vụ đòi hỏi số thập phân chính xác.
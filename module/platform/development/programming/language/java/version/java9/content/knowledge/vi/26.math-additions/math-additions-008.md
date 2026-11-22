# Đối chiếu kết quả Math với hợp đồng StrictMath khi cần

`Math` và `StrictMath` đều cung cấp các hàm toán học cho số primitive trong Java. Điểm khác biệt quan trọng nằm ở **hợp đồng về tính tái lập kết quả**: nhiều hàm trong `Math` cho phép implementation tận dụng thư viện toán học hoặc chỉ thị phần cứng của nền tảng, trong khi các hàm tương ứng của `StrictMath` được định nghĩa để cho kết quả tái lập nhất quán giữa các implementation Java.

Vì vậy, lựa chọn không phải là hàm nào “đúng” và hàm nào “sai”. Hãy dùng `Math` cho tính toán thông thường khi hợp đồng của nó đáp ứng yêu cầu; chọn `StrictMath` khi cần kết quả của các hàm toán học được tái lập bit-for-bit trên các implementation Java tuân thủ cùng đặc tả.

## Mục tiêu

- Phân biệt mục đích và hợp đồng của `Math` với `StrictMath`.
- Hiểu accuracy, ULP, semi-monotonicity và strict reproducibility.
- Biết khi nào dùng `Math`, khi nào cần `StrictMath`.
- Hiểu vì sao hai API có thể trả cùng kết quả trên một runtime nhưng không được giả định luôn giống nhau trên mọi implementation.
- Phân biệt tính tái lập của hàm thư viện với quy tắc đánh giá biểu thức dấu phẩy động của ngôn ngữ.
- Thiết kế kiểm thử số học phù hợp với yêu cầu chính xác của ứng dụng.

## 1. Hai API có mục tiêu gì?

`Math` là API tổng quát cho các phép toán số học và các hàm toán học như `sin`, `cos`, `sqrt`, `log`, `exp`, `pow`, `hypot` và nhiều hàm khác. `StrictMath` cung cấp các hàm tương ứng với hợp đồng tái lập kết quả nghiêm ngặt hơn.

| Tiêu chí | `Math` | `StrictMath` |
| --- | --- | --- |
| Mục tiêu | Tính toán toán học tổng quát, cho phép implementation tối ưu | Tính tái lập kết quả của các hàm được đặc tả |
| Tính bit-for-bit giữa các implementation | Không được bảo đảm cho mọi hàm mà đặc tả cho phép sai khác | Các hàm có hợp đồng strict reproducibility cho cùng kết quả trên các implementation Java tuân thủ đặc tả |
| Cách triển khai | Có thể tận dụng thư viện toán học hoặc tối ưu đặc thù nền tảng | Dựa trên các thuật toán được quy định để bảo đảm kết quả tái lập; đặc tả lịch sử mô tả nền tảng thuật toán fdlibm |
| Khi chọn | Khi yêu cầu độ chính xác theo hợp đồng của `Math` là đủ | Khi kết quả số học của hàm cần nhất quán giữa các nền tảng Java |

Không phải mọi lời gọi `Math` và `StrictMath` đều tạo ra kết quả khác nhau. Nhiều implementation của `Math` có thể gọi trực tiếp hàm tương ứng trong `StrictMath`, hoặc dùng thuật toán cho ra cùng bit kết quả. Điều cần phân biệt là **hợp đồng được bảo đảm**, không phải quan sát ở một lần chạy.

## 2. Tính chính xác của Math: ULP và semi-monotonicity

### 2.1. ULP là gì?

ULP (*unit in the last place*) đo khoảng cách giữa các giá trị floating-point liền kề quanh một kết quả. Đây là cách mô tả sai số làm tròn phù hợp với biểu diễn dấu phẩy động.

Ví dụ, một hàm toán học có thể không trả về giá trị thực chính xác vì kết quả thực không biểu diễn được bằng `double`. Đặc tả có thể cho phép kết quả sai khác một số ULP nhất định. Mức sai số cho phép phải được đọc trong hợp đồng của phương thức cụ thể.

Đối với nhiều hàm dấu phẩy động của `Math`, tài liệu API quy định chất lượng kết quả bằng các giới hạn ULP và yêu cầu semi-monotonicity. Không nên suy diễn một giới hạn chung cho mọi overload hoặc mọi phương thức; hãy kiểm tra tài liệu của chính hàm đang dùng.

### 2.2. Semi-monotonicity

Một hàm semi-monotonic không đảo chiều thứ tự một cách tùy tiện khi các đầu vào tăng theo miền mà đặc tả xét. Nói đơn giản, nếu đầu vào tăng, kết quả xấp xỉ không được tạo ra một bước giảm trái với quan hệ đơn điệu mà hàm toán học yêu cầu.

Accuracy và semi-monotonicity là ràng buộc chất lượng kết quả. Chúng không đồng nghĩa với việc mọi implementation phải trả cùng một chuỗi bit.

### 2.3. Kết quả gần đúng vẫn có thể đúng hợp đồng

Hai implementation có thể trả hai giá trị `double` khác nhau ở bit cuối nhưng cả hai vẫn đáp ứng giới hạn sai số của `Math`. Nếu ứng dụng cần so sánh kết quả gần đúng, hãy xác định tolerance theo miền dữ liệu và yêu cầu nghiệp vụ, thay vì mặc định dùng `==`.

~~~java
double actual = Math.sin(1.0);
double expected = 0.8414709848078965;
double tolerance = 1.0e-15;

boolean closeEnough = Math.abs(actual - expected) <= tolerance;
~~~

Tolerance trong ví dụ chỉ là minh họa. Giá trị thực tế phải được lựa chọn dựa trên dải đầu vào, sai số tích lũy và tiêu chí chấp nhận của ứng dụng.

## 3. Hợp đồng tái lập của StrictMath

`StrictMath` định nghĩa các thuật toán cho những hàm toán học của nó nhằm bảo đảm kết quả tái lập giữa các implementation Java. Các thuật toán được thiết kế dựa trên fdlibm (*Freely Distributable Math Library*) và các yêu cầu được ghi trong đặc tả API.

Điều đó có nghĩa là cùng một đầu vào và cùng một phương thức `StrictMath`, các implementation Java tuân thủ hợp đồng sẽ trả về cùng kết quả floating-point theo đặc tả, thay vì tự chọn thuật toán nền tảng có thể tạo ra bit cuối khác nhau.

### 3.1. Tái lập không có nghĩa là chính xác tuyệt đối trong số thực

`StrictMath.sin(1.0)` vẫn trả về một giá trị `double` hữu hạn biểu diễn xấp xỉ của sin(1). Nó không thể biến biểu diễn nhị phân hữu hạn thành một biểu diễn chính xác cho mọi số thực.

Strict reproducibility trả lời câu hỏi: *các implementation có cho cùng kết quả được quy định hay không?* Nó không trả lời rằng kết quả là giá trị toán học chính xác tuyệt đối.

### 3.2. Phạm vi của bảo đảm

StrictMath chỉ giúp tái lập kết quả của các hàm có hợp đồng tương ứng. Nó không tự bảo đảm toàn bộ chương trình có kết quả giống nhau nếu chương trình còn phụ thuộc vào:

- Dữ liệu đầu vào hoặc thứ tự dữ liệu khác nhau.
- Phép cộng dồn song song có thứ tự thực hiện khác nhau.
- Thuật toán ứng dụng, quy tắc làm tròn hoặc chuyển đổi kiểu khác nhau.
- Locale, định dạng số, serialization hoặc cách ghi dữ liệu.
- Các thư viện khác có hợp đồng số học riêng.

Nếu cần tính tái lập toàn bộ pipeline số học, phải xác định và kiểm thử tất cả các nguồn sai khác, không chỉ thay `Math` bằng `StrictMath`.

## 4. Khi nào nên dùng Math?

Dùng `Math` khi ứng dụng cần các phép toán tổng quát và chấp nhận hợp đồng sai số của phương thức. Đây thường là lựa chọn mặc định cho mã ứng dụng thông thường.

Các tình huống phù hợp gồm:

- Tính toán hình học, đồ họa hoặc mô phỏng khi sai số trong giới hạn cho phép.
- Xử lý số liệu mà kết quả được so sánh bằng tolerance.
- Các ứng dụng không yêu cầu kết quả bit-for-bit giống nhau giữa các implementation Java.
- Khi implementation nền tảng có thể tối ưu hàm toán học và hiệu năng đã được đo kiểm.

Không nên tự thay tất cả lời gọi `Math` bằng `StrictMath` chỉ vì tên có chữ “Strict”. Hãy xác định yêu cầu tái lập trước, rồi chọn API phù hợp.

## 5. Khi nào nên dùng StrictMath?

Dùng `StrictMath` khi cùng một phép toán cần trả về kết quả tái lập giữa các implementation Java tuân thủ đặc tả.

Các tình huống có thể cần lựa chọn này:

- Tính toán phải cho kết quả hàm toán học ổn định giữa nhiều nền tảng Java.
- Tạo dữ liệu tham chiếu hoặc fixture số học dùng chung giữa các môi trường.
- Kiểm thử cần so sánh bit kết quả của một hàm được đặc tả strict reproducibility.
- Mô phỏng hoặc thuật toán cần tái lập kết quả của các phép toán transcendental để hỗ trợ điều tra và đối chiếu.

Trước khi chọn, hãy kiểm tra xem phần mềm có thật sự yêu cầu cùng bit kết quả hay chỉ cần sai số trong một khoảng. Nếu tolerance là đủ, `Math` thường đơn giản và linh hoạt hơn.

## 6. Math và StrictMath không phải lúc nào cũng khác kết quả

Ví dụ sau gọi cả hai hàm sin với cùng đầu vào:

~~~java
double angle = 1.0;
double mathValue = Math.sin(angle);
double strictValue = StrictMath.sin(angle);

boolean sameBits = Double.doubleToLongBits(mathValue)
    == Double.doubleToLongBits(strictValue);
~~~

`sameBits` có thể là `true` trên một runtime cụ thể. Điều đó chỉ cho biết hai lời gọi đã cho cùng bit trong lần chạy đó. Nó không nâng hợp đồng của `Math.sin()` thành bảo đảm bit-for-bit giữa mọi implementation.

Không viết test yêu cầu `Math.sin(x)` luôn bằng bit với `StrictMath.sin(x)` trên mọi JVM. Nếu ứng dụng cần hợp đồng tái lập, hãy gọi `StrictMath` ngay trong phần logic cần bảo đảm đó.

## 7. Phân biệt StrictMath với strict floating-point evaluation

Java còn có quy tắc về cách các biểu thức dấu phẩy động được đánh giá. Từ Java 17, các biểu thức floating-point dùng ngữ nghĩa strict mặc định trên mọi nền tảng. Điều này liên quan đến việc đánh giá phép toán trong ngôn ngữ và biểu diễn trung gian.

Quy tắc đó **không thay thế `StrictMath`**. Một biểu thức như `a * b + c` và một lời gọi như `Math.sin(x)` là hai vấn đề khác nhau:

- Ngữ nghĩa strict của biểu thức điều chỉnh cách thực hiện phép toán dấu phẩy động cơ bản.
- Lựa chọn `Math` hay `StrictMath` quyết định hợp đồng của hàm toán học thư viện được gọi.

Vì vậy, trên Java 17 trở lên, việc mọi biểu thức đã strict không đồng nghĩa mọi hàm `Math` đều có kết quả bit-for-bit giống `StrictMath` giữa các implementation.

## 8. Cách kiểm thử và so sánh kết quả

### 8.1. Khi chỉ cần độ gần đúng

Với `Math`, kiểm tra kết quả bằng tolerance được xác định cho bài toán. Tránh dùng `==` cho hai kết quả floating-point gần đúng nếu miền dữ liệu cho phép sai số.

~~~java
double actual = Math.cos(0.7);
double expected = 0.7648421872844885;

if (Math.abs(actual - expected) > 1.0e-15) {
    throw new AssertionError("Result outside accepted tolerance");
}
~~~

Tolerance không nên chọn tùy tiện quá lớn để test luôn qua, hoặc quá nhỏ khiến test phụ thuộc vào sai khác hợp lệ của implementation.

### 8.2. Khi cần tái lập bit

Chọn `StrictMath` trong logic tạo kết quả cần tái lập. Nếu kiểm thử bit pattern, dùng `Double.doubleToLongBits()` hoặc `Float.floatToIntBits()` để chuyển kết quả sang dạng bit có thể so sánh.

~~~java
double value = StrictMath.sin(1.0);
long bits = Double.doubleToLongBits(value);
System.out.println(Long.toHexString(bits));
~~~

Không dùng bit pattern của `Math` làm golden value đa nền tảng cho một hàm mà hợp đồng cho phép implementation trả kết quả khác ở bit cuối.

### 8.3. Đừng nhầm kiểm thử cùng runtime với kiểm thử đa nền tảng

Chạy test trên một JVM chỉ xác nhận hành vi của implementation đó. Nếu yêu cầu là tái lập giữa nhiều nền tảng, test nên được chạy trên các implementation hoặc môi trường mục tiêu có liên quan. Quan trọng hơn, mã cần dùng đúng API có hợp đồng mong muốn; test không thể biến một bảo đảm không tồn tại thành bảo đảm của API.

## 9. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ dưới đây hiển thị kết quả từ `Math` và `StrictMath`, đồng thời cho thấy phép so sánh bit trên runtime đang chạy. `Math.sin()` và `StrictMath.sin()` có thể giống nhau trên một implementation; dòng `same sine bits` không phải cam kết chung cho mọi implementation.

**Tệp:** `MathStrictMathDemo.java`

~~~java
import java.util.Locale;

public class MathStrictMathDemo {
    public static void main(String[] args) {
        double angle = 1.0;

        double mathSin = Math.sin(angle);
        double strictSin = StrictMath.sin(angle);
        double strictSqrt = StrictMath.sqrt(2.0);

        System.out.printf(Locale.ROOT, "Math.sin(1.0) = %.17g%n", mathSin);
        System.out.printf(Locale.ROOT, "StrictMath.sin(1.0) = %.17g%n", strictSin);
        System.out.printf(Locale.ROOT, "StrictMath.sqrt(2.0) = %.17g%n", strictSqrt);
        System.out.println("Math.addExact(20, 22) = " + Math.addExact(20, 22));

        boolean sameBits = Double.doubleToLongBits(mathSin)
            == Double.doubleToLongBits(strictSin);
        System.out.println("same sine bits on this runtime = " + sameBits);
    }
}
~~~

Biên dịch và chạy với JDK 9 trở lên:

~~~text
javac --release 9 MathStrictMathDemo.java
java MathStrictMathDemo
~~~

Output trên runtime dùng để kiểm thử ví dụ:

~~~text
Math.sin(1.0) = 0.84147098480789650
StrictMath.sin(1.0) = 0.84147098480789650
StrictMath.sqrt(2.0) = 1.4142135623730951
Math.addExact(20, 22) = 42
same sine bits on this runtime = true
~~~

Dòng kết quả `Math.sin(1.0)` và `same sine bits` mô tả runtime hiện tại. Implementation khác có thể trả về bit cuối khác cho `Math.sin()` trong giới hạn hợp đồng của nó. Giá trị `StrictMath.sin(1.0)` và `StrictMath.sqrt(2.0)` được cung cấp theo hợp đồng tái lập của `StrictMath`.

## 10. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Nghĩ `Math` và `StrictMath` luôn trả kết quả khác nhau | Nhiều implementation cho cùng kết quả | So sánh hợp đồng, không dựa vào việc kết quả phải khác |
| Nghĩ chúng luôn giống nhau vì test trên máy hiện tại cho kết quả giống | Một runtime không chứng minh bảo đảm đa implementation | Dùng `StrictMath` khi cần strict reproducibility |
| Dùng `==` cho kết quả `Math` gần đúng | Các sai khác hợp lệ ở bit cuối có thể làm so sánh thất bại | Dùng tolerance phù hợp nếu bài toán cho phép sai số |
| Dùng `StrictMath` nhưng nghĩ kết quả là số thực chính xác tuyệt đối | Strict reproducibility không loại bỏ sai số biểu diễn floating-point | Phân biệt kết quả tái lập và kết quả chính xác toán học |
| Thay tất cả `Math` bằng `StrictMath` | Có thể thêm ràng buộc không cần thiết và làm mã khó diễn đạt yêu cầu | Chọn theo yêu cầu tái lập thực tế và đo hiệu năng |
| Nghĩ Java 17 strict floating-point làm `Math` giống `StrictMath` | Strict evaluation của biểu thức và hợp đồng hàm thư viện là hai lớp khác nhau | Chọn `StrictMath` cho hàm cần kết quả tái lập |
| Nghĩ dùng `StrictMath` là toàn bộ chương trình đã deterministic | Các nguồn khác như thứ tự dữ liệu, thuật toán song song và định dạng vẫn có thể khác | Xác định toàn bộ pipeline cần tái lập |

## 11. Quy tắc thực hành

1. Dùng `Math` làm lựa chọn mặc định khi hợp đồng độ chính xác của phương thức đáp ứng yêu cầu.
2. Dùng `StrictMath` cho hàm toán học khi cần kết quả tái lập giữa các implementation Java.
3. Đọc tài liệu của từng phương thức để hiểu giới hạn ULP, monotonicity và các trường hợp đặc biệt.
4. Không giả định `Math` và `StrictMath` luôn khác hoặc luôn giống bit-for-bit.
5. Dùng tolerance cho phép so sánh gần đúng; dùng `StrictMath` khi yêu cầu là tái lập kết quả của hàm.
6. Phân biệt strict floating-point evaluation của biểu thức với strict reproducibility của hàm thư viện.
7. Đừng cho rằng thay `Math` bằng `StrictMath` sẽ làm toàn bộ chương trình deterministic.
8. Benchmark trên workload thực tế nếu hiệu năng là tiêu chí lựa chọn; không suy đoán rằng một API luôn nhanh hơn API còn lại.

## 12. Tự kiểm tra

- Khác biệt cốt lõi giữa `Math` và `StrictMath` là gì? `Math` cho phép implementation tối ưu trong giới hạn hợp đồng; `StrictMath` cung cấp hợp đồng tái lập kết quả cho các hàm được đặc tả.
- `Math.sin(x)` có thể khác `StrictMath.sin(x)` ở bit cuối không? Có thể, nếu khác biệt vẫn nằm trong hợp đồng của `Math`.
- Nếu hai API cho cùng kết quả trên JVM hiện tại, có thể kết luận mọi JVM đều giống nhau không? Không.
- Strict reproducibility có nghĩa kết quả chính xác tuyệt đối trong số thực không? Không, nó bảo đảm tính tái lập của kết quả floating-point được đặc tả.
- Khi nào nên chọn `StrictMath`? Khi kết quả của hàm toán học cần tái lập giữa các implementation Java.
- Khi nào nên chọn `Math`? Khi độ chính xác theo hợp đồng `Math` là đủ và không cần bit-for-bit reproducibility.
- Java 17 strict floating-point evaluation có loại bỏ nhu cầu `StrictMath` không? Không; hai cơ chế giải quyết hai vấn đề khác nhau.

Điểm cốt lõi: **chọn `Math` theo yêu cầu tính toán thông thường; chọn `StrictMath` khi hợp đồng tái lập kết quả của hàm toán học là yêu cầu thực sự.** Đừng suy luận từ một lần chạy rằng hai API luôn giống hoặc luôn khác nhau.
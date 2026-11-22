# Thứ tự cộng ảnh hưởng tổng dấu phẩy động trong Java

## 1. Vấn đề và mục tiêu

Trong toán học, phép cộng số thực có tính kết hợp: \((a+b)+c=a+(b+c)\). Với kiểu `double` hoặc `float` trong Java, **thay đổi thứ tự cộng có thể làm thay đổi kết quả được lưu**. Nguyên nhân là máy tính lưu số dấu phẩy động bằng một số bit hữu hạn và phải làm tròn các kết quả trung gian không biểu diễn chính xác được.

Đặc tính này quan trọng khi tổng hợp hàng triệu bản ghi, tính điểm số, thống kê, xử lý nhiều giá trị có độ lớn chênh lệch, thay đổi thứ tự phần tử hoặc gộp kết quả từ nhiều tác vụ song song.

Sau bài học, người đọc có thể giải thích nguồn gốc của sai số, tự tái hiện kết quả phụ thuộc thứ tự bằng Java 17, phân biệt những chiến lược cải thiện độ chính xác và quyết định khi nào cần dùng `BigDecimal` thay vì `double`.

## 2. Giới hạn của biểu diễn dấu phẩy động

Java sử dụng định dạng dấu phẩy động nhị phân tương ứng IEEE 754 cho `float` (32 bit) và `double` (64 bit). `float` có khoảng 24 bit chính xác significand, còn `double` có 53 bit (xấp xỉ 15–17 chữ số thập phân có nghĩa).

Các giá trị như `0.1`, `0.2` không có biểu diễn nhị phân hữu hạn chính xác. Khi tạo một `double` bằng literal `0.1`, máy lưu giá trị nhị phân gần nhất. Mỗi phép cộng có thể tiếp tục sinh kết quả nằm giữa các giá trị biểu diễn được, nên phải làm tròn.

**Khoảng cách giữa hai số biểu diễn liên tiếp thay đổi theo độ lớn của số.** Khi tổng đang rất lớn, thêm một số nhỏ có thể không làm thay đổi tổng. `Math.ulp(x)` cung cấp kích thước một bước (*unit in the last place*) tại `x`.

### Ví dụ Java 17: một số hạng nhỏ bị mất

Lưu thành `FloatingUlpDemo.java`:

~~~java
public class FloatingUlpDemo {
    public static void main(String[] args) {
        double large = 1.0e16;

        System.out.println("ulp = " + Math.ulp(large));
        System.out.println("unchanged = " + (large + 1.0 == large));
        System.out.println("add before cancel = "
                + ((large + 1.0) - large));
        System.out.println("cancel before add = "
                + ((large - large) + 1.0));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac FloatingUlpDemo.java
java FloatingUlpDemo
~~~

Đầu ra:

~~~text
ulp = 2.0
unchanged = true
add before cancel = 0.0
cancel before add = 1.0
~~~

Cả `large` và `1.0` đều có thể biểu diễn trong `double`. Nhưng quanh `1.0e16`, bước biểu diễn là `2.0`. Khi cộng `1.0`, kết quả đúng nằm ở điểm giữa hai giá trị biểu diễn được; phép làm tròn đưa kết quả về `large`. Vì vậy đóng góp `1.0` không còn để phép trừ phía sau khôi phục.

## 3. Không kết hợp: cách đặt ngoặc và thứ tự làm thay đổi tổng

Khi ký hiệu `fl` là thao tác làm tròn về kiểu dấu phẩy động, hai biểu thức

\[
\mathrm{fl}(\mathrm{fl}(a+b)+c)
\quad\text{và}\quad
\mathrm{fl}(a+\mathrm{fl}(b+c))
\]

có các bước trung gian khác nhau. Chúng không nhất thiết cho cùng kết quả.

### Ví dụ Java 17: cùng ba số, hai tổng

Lưu thành `FloatingAssociativityDemo.java`:

~~~java
public class FloatingAssociativityDemo {
    public static void main(String[] args) {
        double a = 1.0e16;
        double b = -1.0e16;
        double c = 1.0;

        double left = (a + b) + c;
        double right = a + (b + c);

        System.out.println("left = " + left);
        System.out.println("right = " + right);
        System.out.println("same = " + (left == right));
    }
}
~~~

~~~bash
javac FloatingAssociativityDemo.java
java FloatingAssociativityDemo
~~~

Đầu ra:

~~~text
left = 1.0
right = 0.0
same = false
~~~

Tổng toán học là `1`. Vế trái hủy hai số lớn trước rồi cộng `1`. Vế phải cộng `1` với số lớn âm trước, khiến đóng góp nhỏ bị làm tròn mất. Khi đổi **thứ tự phần tử** từ `[1e16, 1, -1e16]` sang `[1e16, -1e16, 1]` trong một vòng cộng trái sang phải, kết quả cũng có thể thay đổi từ `0.0` sang `1.0`.

**Hệ quả:** không thể áp dụng tùy tiện phép biến đổi đại số của cộng số thực cho `double` rồi kỳ vọng kết quả từng bit luôn giống nhau. Java đánh giá biểu thức với những phép toán trung gian cụ thể; mỗi bước có thể mất thông tin.

## 4. Sai số tích lũy khi cộng nhiều lần

Ngay cả khi không có số rất lớn, việc lặp phép cộng có thể tạo sai số khác so với một phép nhân tương ứng. Ví dụ `0.1` là số nhị phân gần đúng; mười phép cộng có cách làm tròn khác với phép nhân `10 * 0.1`.

Lưu thành `RepeatedFloatingSumDemo.java`:

~~~java
public class RepeatedFloatingSumDemo {
    public static void main(String[] args) {
        double sum = 0.0;
        for (int i = 0; i < 10; i++) {
            sum += 0.1;
        }
        double product = 10 * 0.1;

        System.out.println("repeated = " + sum);
        System.out.println("product = " + product);
        System.out.println("equal = " + (sum == product));
    }
}
~~~

~~~bash
javac RepeatedFloatingSumDemo.java
java RepeatedFloatingSumDemo
~~~

Đầu ra:

~~~text
repeated = 0.9999999999999999
product = 1.0
equal = false
~~~

`println(double)` hiển thị chuỗi decimal ngắn cho phép chuyển lại về cùng `double`, không hiển thị đầy đủ mọi bit nhị phân. Việc `println(0.1)` in `0.1` **không có nghĩa 0.1 được lưu chính xác**.

Lỗi làm tròn không nhất thiết chỉ tăng dần: có lần sai số cùng chiều, có lần bù trừ nhau. Kết quả phụ thuộc độ lớn, dấu và thứ tự của các số được cộng.

## 5. Mất số nhỏ và cancellation

Có hai hiện tượng cần tách bạch:

1. **Swamping (số nhỏ bị nuốt):** một số hạng rất nhỏ so với tổng hiện tại có thể nhỏ hơn độ phân giải của `double` tại đó, khiến phép cộng không thay đổi kết quả.
2. **Cancellation (triệt tiêu):** hai giá trị gần đối nhau cho tổng nhỏ. Những lỗi có sẵn ở các số hạng hoặc phép tính trung gian có thể lớn tương đối so với kết quả nhỏ.

Nếu chỉ cộng các số dương, đưa các số nhỏ lên trước thường có thể giảm việc mất đóng góp nhỏ. Với dữ liệu gồm cả số âm/dương, **không có một thứ tự sắp xếp luôn tối ưu**, vì vị trí các cặp triệt tiêu cũng thay đổi.

Sai số phải được đánh giá trong bối cảnh mục tiêu. Tổng `0.0` thay vì `1.0` là lỗi rất lớn nếu tổng đúng là 1, dù từng số hạng ban đầu có độ lớn `1e16`.

## 6. Cộng bù Kahan

**Kahan summation** thêm biến `correction` để ước lượng phần đóng góp bị bỏ khi cộng. Phần bù đó được đưa vào phép cộng tiếp theo nhằm giảm sai số tích lũy trong nhiều trường hợp.

Cơ chế:

~~~text
sum = 0
correction = 0
for each x:
    adjusted = x - correction
    next = sum + adjusted
    correction = (next - sum) - adjusted
    sum = next
return sum
~~~

Đây là pseudocode, không phải chương trình Java hoàn chỉnh. Các bước vẫn thực hiện bằng `double`, nên **Kahan không bảo đảm đúng tuyệt đối với mọi input**.

### Ví dụ Java 17: Kahan cải thiện tổng lặp

Lưu thành `KahanSummationDemo.java`:

~~~java
public class KahanSummationDemo {
    static double naive(int count, double value) {
        double sum = 0.0;
        for (int i = 0; i < count; i++) {
            sum += value;
        }
        return sum;
    }

    static double kahan(int count, double value) {
        double sum = 0.0;
        double correction = 0.0;
        for (int i = 0; i < count; i++) {
            double adjusted = value - correction;
            double next = sum + adjusted;
            correction = (next - sum) - adjusted;
            sum = next;
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println("naive = " + naive(10, 0.1));
        System.out.println("kahan = " + kahan(10, 0.1));
    }
}
~~~

~~~bash
javac KahanSummationDemo.java
java KahanSummationDemo
~~~

Đầu ra:

~~~text
naive = 0.9999999999999999
kahan = 1.0
~~~

Bộ số này minh họa lợi ích của phép cộng bù. Tuy nhiên, kết quả `1.0` không chứng minh thuật toán đã khôi phục mọi giá trị decimal đầu vào; `0.1` vốn được biểu diễn gần đúng khi chuyển thành `double`.

## 7. Neumaier: cải thiện khi có số lớn và số nhỏ xen kẽ

**Neumaier summation** là một biến thể cộng bù. Nó theo dõi độ lớn tương đối của tổng tạm và số mới để tính phần bù. Với `[1e16, 1, -1e16]`, cả phép cộng thường lẫn Kahan cơ bản có thể cho `0.0`, nhưng Neumaier có thể giữ lại `1.0`.

### Ví dụ Java 17: ba kết quả khác nhau

Lưu thành `CompensatedSummationDemo.java`:

~~~java
public class CompensatedSummationDemo {
    static double naive(double[] values) {
        double sum = 0.0;
        for (double x : values) {
            sum += x;
        }
        return sum;
    }

    static double kahan(double[] values) {
        double sum = 0.0;
        double correction = 0.0;
        for (double x : values) {
            double adjusted = x - correction;
            double next = sum + adjusted;
            correction = (next - sum) - adjusted;
            sum = next;
        }
        return sum;
    }

    static double neumaier(double[] values) {
        double sum = 0.0;
        double correction = 0.0;
        for (double x : values) {
            double next = sum + x;
            if (Math.abs(sum) >= Math.abs(x)) {
                correction += (sum - next) + x;
            } else {
                correction += (x - next) + sum;
            }
            sum = next;
        }
        return sum + correction;
    }

    public static void main(String[] args) {
        double[] data = {1.0e16, 1.0, -1.0e16};

        System.out.println("naive = " + naive(data));
        System.out.println("kahan = " + kahan(data));
        System.out.println("neumaier = " + neumaier(data));
    }
}
~~~

~~~bash
javac CompensatedSummationDemo.java
java CompensatedSummationDemo
~~~

Đầu ra:

~~~text
naive = 0.0
kahan = 0.0
neumaier = 1.0
~~~

Neumaier có thể giữ phần nhỏ trong biến bù trong tình huống mà Kahan cơ bản vẫn đánh mất nó. Dù vậy, cả hai không thể bảo đảm tổng toán học chính xác trong mọi trường hợp, đặc biệt với `NaN`, `Infinity`, overflow, underflow hoặc dữ liệu đã mang sai số từ trước. Thuật toán phải được thử với đặc điểm dữ liệu thực tế.

## 8. Pairwise summation và chia khối

**Pairwise summation** thay chuỗi cộng dài từ trái sang phải bằng cây phép cộng: chia mảng thành hai nửa, cộng mỗi nửa, sau đó cộng hai kết quả. Trong nhiều bài toán tổng các số không âm, phương pháp này giảm số bước cộng liên tiếp trên một nhánh và có thể giảm lỗi tích lũy.

Pseudocode:

~~~text
pairwise(values):
    if empty: return 0
    if only one value: return value
    split into left and right halves
    return pairwise(left) + pairwise(right)
~~~

Mỗi phép cộng trong cây vẫn làm tròn. **Pairwise không tốt hơn mọi thứ tự** trên mọi bộ số âm/dương, vì việc chia nhóm có thể di chuyển vị trí cancellation. Nếu hệ thống cần kết quả tái lập từng bit, phải cố định **cây cộng, kích thước khối và thứ tự các phần tử**, chứ không chỉ ghi “dùng pairwise”.

## 9. Stream, reduce và tổng song song

Trong Java, tính tổng với Stream có nhiều cách và không nhất thiết dùng cùng thứ tự:

- Vòng `for` trên mảng có trình tự xác định cộng theo thứ tự vòng lặp.
- `Arrays.stream(values).reduce(0.0, Double::sum)` giảm các giá trị bằng cộng. Hợp đồng giảm song song thường giả định phép kết hợp là associative; cộng `double` không có tính kết hợp về mặt số học máy, nên các cây gộp có thể cho kết quả khác.
- `DoubleStream.sum()` theo API Java sử dụng một thuật toán cộng có bù, giúp cải thiện nhiều tình huống nhưng không loại bỏ ảnh hưởng của thứ tự hoặc giới hạn độ chính xác.
- `Collectors.summingDouble(...)` cũng có thể chịu ảnh hưởng từ thứ tự và độ lớn các giá trị.

### Ví dụ Java 17: cùng dữ liệu, các API khác nhau

Lưu thành `FloatingStreamDemo.java`:

~~~java
import java.util.Arrays;

public class FloatingStreamDemo {
    public static void main(String[] args) {
        double[] data = {1.0e16, 1.0, -1.0e16};

        double reduce = Arrays.stream(data)
                .reduce(0.0, Double::sum);
        double specialized = Arrays.stream(data).sum();
        double parallel = Arrays.stream(data).parallel()
                .reduce(0.0, Double::sum);

        System.out.println("reduce = " + reduce);
        System.out.println("sum finite = " + Double.isFinite(specialized));
        System.out.println("parallel finite = " + Double.isFinite(parallel));
    }
}
~~~

~~~bash
javac FloatingStreamDemo.java
java FloatingStreamDemo
~~~

Đầu ra:

~~~text
reduce = 0.0
sum finite = true
parallel finite = true
~~~

Hai phép kiểm tra `isFinite` tránh giả định một tổng cụ thể cho thuật toán và cách phân hoạch có thể khác nhau. Dữ liệu trong ví dụ đều hữu hạn, không gây overflow. Không suy diễn rằng tổng cụ thể của `parallel().reduce(...)` luôn giống tổng vòng lặp trên mọi hệ thống hay mọi kích thước đầu vào.

Khi tính song song mà cần kết quả ổn định, cố định phân hoạch và phương thức gộp hoặc dùng bộ tích lũy đáp ứng yêu cầu độ chính xác. Độ ổn định phải được xác minh bằng kiểm thử thực tế.

## 10. BigDecimal khi cần phép cộng decimal chính xác

Nếu bài toán cần tính chính xác **giá trị thập phân đầu vào**, ví dụ tiền, `BigDecimal` là giải pháp thường phù hợp. Tạo BigDecimal từ chuỗi decimal và dùng `add(...)` không truyền `MathContext` để cộng chính xác các giá trị decimal đã lưu.

### Ví dụ Java 17: tổng không phụ thuộc thứ tự với phép cộng decimal chính xác

Lưu thành `BigDecimalOrderDemo.java`:

~~~java
import java.math.BigDecimal;

public class BigDecimalOrderDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("10000000000000000");
        BigDecimal b = BigDecimal.ONE;
        BigDecimal c = new BigDecimal("-10000000000000000");

        BigDecimal first = a.add(b).add(c);
        BigDecimal second = a.add(c).add(b);

        System.out.println("first = " + first.toPlainString());
        System.out.println("second = " + second.toPlainString());
        System.out.println("same value = "
                + (first.compareTo(second) == 0));
    }
}
~~~

~~~bash
javac BigDecimalOrderDemo.java
java BigDecimalOrderDemo
~~~

Đầu ra:

~~~text
first = 1
second = 1
same value = true
~~~

Phải hiểu phạm vi của kết luận:

- `new BigDecimal("0.1")` giữ đúng giá trị thập phân 0.1. `new BigDecimal(0.1)` giữ chính xác **giá trị nhị phân gần đúng của kiểu double**, không phải số decimal 0.1 lý tưởng.
- `BigDecimal.valueOf(double)` dùng biểu diễn chuỗi chuẩn của double nhưng không phục hồi những thông tin đã mất khi làm phép tính double trước đó.
- Nếu dùng `add(other, MathContext)` với precision giới hạn, **mỗi lần cộng có thể làm tròn**, khiến tổng BigDecimal cũng có thể phụ thuộc cách nhóm.
- BigDecimal dùng nhiều chi phí hơn double trong nhiều bài toán. Không tự động chuyển mọi thống kê dấu phẩy động sang BigDecimal khi dung sai và hiệu năng cho phép dùng double.

Với tiền tệ, cần xác định thời điểm làm tròn theo nghiệp vụ. **Làm tròn từng dòng rồi cộng có thể khác cộng chính xác trước rồi làm tròn tổng.**

## 11. Đo sai số và đặt kiểm thử đúng

Sai số tuyệt đối so với tham chiếu chính xác hơn:

\[
E_{\mathrm{abs}} = |S_{\mathrm{computed}}-S_{\mathrm{reference}}|.
\]

Sai số tương đối bằng sai số tuyệt đối chia cho \(|S_{\mathrm{reference}}|\), nhưng không phù hợp khi tổng tham chiếu bằng hoặc rất gần 0. Các bộ dữ liệu có cancellation thường cần đánh giá cả sai số tuyệt đối và các tiêu chuẩn gắn với nghiệp vụ.

Một công thức dung sai gần đúng thường gặp:

\[
|a-b| \le \epsilon_{\mathrm{abs}}+
\epsilon_{\mathrm{rel}}\max(|a|,|b|).
\]

Không chọn `1e-9` làm ngưỡng mặc định cho mọi trường hợp: dung sai phải phụ thuộc độ lớn dữ liệu, số phép tính và mục tiêu. Kiểm tra `NaN`, vô cực, tràn số, underflow và zero có dấu theo hợp đồng bài toán nếu đầu vào có thể chứa chúng.

Một kế hoạch thử nghiệm hữu ích là chạy cùng bộ số ở thứ tự gốc, đảo ngược, sắp xếp theo độ lớn và chia khối; so sánh với giá trị tham chiếu chính xác hơn. Bao gồm cả dữ liệu `[1e16, 1, -1e16]`, nhiều số nhỏ lặp lại và nhiều số âm/dương gần triệt tiêu.

## 12. Khi nào chọn cách tính nào?

| Yêu cầu | Cách tiếp cận | Giới hạn |
| --- | --- | --- |
| Tổng double đơn giản, chấp nhận dung sai | Vòng lặp cộng theo thứ tự cố định | Có thể tích lũy sai số |
| Nhiều phép cộng double | Kahan, pairwise hoặc phương pháp cộng bù khác | Không bảo đảm đúng tuyệt đối |
| Số lớn/nhỏ âm/dương xen kẽ | Neumaier hoặc bộ tích lũy phù hợp | Kiểm thử cancellation và ngoại lệ |
| Tính toán song song | Cố định cách chia và cây gộp nếu cần tái lập | Thay đổi phân hoạch có thể đổi tổng |
| Giá trị tiền/decimal phải chính xác | BigDecimal từ nguồn decimal, cộng chính xác trước làm tròn | Tăng chi phí xử lý và bộ nhớ |
| Cần tổng đúng bất kể thứ tự | Thuật toán tích lũy chính xác phù hợp hợp đồng | Cần giải pháp và kiểm chứng chuyên biệt |

Không có một cách cộng nào tốt nhất cho mọi bộ số. Kết quả phải phù hợp sai số cho phép, độ trễ, khả năng tái lập và đặc điểm dữ liệu.

## 13. Lỗi thường gặp

1. **Cho rằng `double` cộng có tính kết hợp hoàn toàn:** mỗi phép cộng trung gian có thể làm tròn.
2. **Nghĩ tổng luôn giống nhau khi chỉ đổi thứ tự phần tử:** các số nhỏ có thể bị mất ở vị trí khác.
3. **Dùng `parallel().reduce` và mong từng bit giống vòng lặp tuần tự:** cây gộp có thể khác.
4. **Tưởng `DoubleStream.sum()` cho kết quả số thực chính xác:** thuật toán có bù vẫn chịu giới hạn nhị phân.
5. **Sắp xếp mọi số nhỏ trước rồi coi như đã giải quyết hoàn toàn:** có số âm/dương và cancellation làm kết quả phức tạp.
6. **Tin Kahan luôn đủ:** bộ `[1e16, 1, -1e16]` có thể cần kỹ thuật bù mạnh hơn.
7. **Tưởng `println(0.1)` chứng minh double lưu chính xác 0.1:** chuỗi hiển thị là biểu diễn decimal phù hợp, không phải bit lưu trữ.
8. **Chuyển một double đã sai số sang BigDecimal để mong phục hồi dữ liệu:** thông tin đã mất không tự quay lại.
9. **Để MathContext làm tròn giữa các lần cộng BigDecimal mà không xét thứ tự:** phép cộng sau làm tròn cũng có thể không kết hợp.
10. **Bỏ qua NaN, Infinity, overflow hoặc dữ liệu rất chênh lệch:** chúng có thể phá những giả định của phép tính gần đúng.
11. **So sánh số gần đúng bằng `==` trong mọi kiểm thử:** chỉ hợp lý nếu yêu cầu phải bằng chính xác theo giá trị double.
12. **Dùng sai số tương đối khi tổng đúng bằng 0:** phép chia theo công thức tương đối không xác định.

## 14. Bài tập và đáp án

**Câu 1.** Vì sao `(1e16 + (-1e16)) + 1` khác `1e16 + ((-1e16) + 1)` khi tính bằng double?

**Đáp án:** Biểu thức đầu triệt tiêu hai số lớn trước, trả `1.0`. Biểu thức sau làm mất đóng góp `1` ở phép cộng với số lớn âm, trả `0.0`.

**Câu 2.** Vì sao cộng `0.1` mười lần không nhất thiết bằng `0.1 * 10`?

**Đáp án:** `0.1` là giá trị nhị phân gần đúng; mười phép cộng làm tròn khác với phép nhân.

**Câu 3.** Kahan có luôn khôi phục số nhỏ đã mất trong bộ `[1e16, 1, -1e16]` không?

**Đáp án:** Không. Kahan cơ bản có thể trả `0.0`; ví dụ Neumaier trả `1.0`.

**Câu 4.** Khi nào nên dùng BigDecimal?

**Đáp án:** Khi cần tổng chính xác theo giá trị decimal của đầu vào (như tiền), xây dựng các đối tượng từ dữ liệu decimal chính xác và không làm tròn mỗi phép cộng nếu mục tiêu là tổng chính xác.

**Câu 5.** Có nên dùng sai số tương đối khi tổng tham chiếu là `0`?

**Đáp án:** Không, vì chia cho 0 không xác định; dùng sai số tuyệt đối hoặc tiêu chuẩn khác từ nghiệp vụ.

## 15. Ghi nhớ

- **Thứ tự cộng có thể thay đổi kết quả float/double** vì các phép tính trung gian phải làm tròn.
- Số hạng nhỏ dễ bị mất khi cộng vào tổng lớn; các số lớn đối nhau có thể gây cancellation và làm lộ sai số.
- Kahan, Neumaier, pairwise cải thiện nhiều trường hợp, nhưng không biến double thành số học thực vô hạn chính xác.
- Stream song song có thể dùng cây cộng khác; xác định thuật toán và trình tự gộp khi cần kết quả tái lập.
- Khi cần tổng decimal chính xác, dùng BigDecimal từ nguồn decimal và quản lý thời điểm làm tròn.

Tài liệu tham khảo: Java SE 17 API `Double`, `Math.ulp`, `DoubleStream.sum`, `Collectors.summingDouble`, `BigDecimal` và IEEE 754.
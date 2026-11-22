# Sắp xếp thứ tự phép tính để giảm mất thông tin trong Java

Với `float` và `double`, hai biểu thức **tương đương trong toán học số thực** có thể cho kết quả khác nhau trên Java. Nguyên nhân là số dấu phẩy động chỉ có hữu hạn bit phần trị và số mũ; sau mỗi phép toán, kết quả có thể bị làm tròn, làm mất những đóng góp quá nhỏ, hoặc trở thành vô cực/zero vì tràn và underflow.

Ví dụ điển hình:

```java
double large = 1e16;

double lost = (large + 1.0) - large; // 0.0
double kept = (large - large) + 1.0; // 1.0
```

Trong toán học, cả hai đều bằng 1. Nhưng phép `large + 1.0` làm tròn về `large`: giá trị 1 bị mất trước khi thực hiện phép trừ. Khi triệt tiêu hai số lớn trước, giá trị 1 được giữ nguyên.

**Điểm cốt lõi:** thứ tự tính toán là một phần của thiết kế thuật toán số. Ta có thể giảm mất thông tin bằng cách cộng/ghép nhóm phù hợp, tránh trừ các giá trị gần bằng nhau, dùng công thức ổn định hơn và kiểm soát độ lớn của phép toán trung gian. Tuy nhiên, **không có một cách đảo thứ tự luôn tốt cho mọi dữ liệu**. Cần xét miền đầu vào và đo sai số.

Bài học thuộc mục **Sai số và ổn định** trong module **Java core – numbers**. Trọng tâm là cách áp dụng và giới hạn của những kỹ thuật trên trong Java 17+.

## 1. Vì sao thứ tự có thể thay đổi kết quả?

`float` và `double` sử dụng dấu phẩy động nhị phân IEEE 754:

| Kiểu | Bit phần trị chính xác (kể cả bit ẩn) | Khoảng số nguyên liên tiếp được biểu diễn chính xác |
| --- | ---: | --- |
| `float` | 24 | Từ `-2^24` đến `2^24` |
| `double` | 53 | Từ `-2^53` đến `2^53` |

Khi một kết quả chính xác nằm giữa hai số biểu diễn được, máy phải làm tròn. Ở nhiều phép toán cơ bản, Java áp dụng làm tròn tới giá trị gần nhất và khi bằng khoảng cách thì chọn giá trị có bit cuối chẵn (*round to nearest, ties to even*).

Khoảng cách giữa các giá trị `double` liên tiếp thay đổi theo độ lớn. Chẳng hạn:

```java
double x = 1e16;
System.out.println(Math.ulp(x));   // 2.0
System.out.println(x + 1.0 == x);  // true
System.out.println(x + 2.0 == x);  // false
```

`Math.ulp(x)` (*unit in the last place*) cho biết bước độ phân giải tại `x`. Quanh `1e16`, số 1 nhỏ hơn một bước giữa hai giá trị biểu diễn lân cận.

### Phép cộng không có tính kết hợp như số thực lý tưởng

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double first = (a + b) + c;  // 1.0
double second = a + (b + c); // 0.0
```

Phép `a+b` triệt tiêu thành 0 rồi cộng 1 không mất thông tin; nhưng `b+c` bị làm tròn thành `b` trước. Do đó `(a+b)+c` không nhất thiết bằng `a+(b+c)` trong số học dấu phẩy động.

Phép nhân cũng có thể không kết hợp khi xuất hiện rounding, overflow hoặc underflow. Việc thay đổi dấu ngoặc có thể làm kết quả tốt hơn **hoặc** xấu đi.

### Java 17 always-strict không sửa được tính không kết hợp

Từ Java 17, Java có ngữ nghĩa *always-strict* cho biểu thức dấu phẩy động. Điều này quy định cách đánh giá chặt chẽ hơn, nhưng **không tăng vô hạn độ chính xác** và không biến `+`, `*` thành các phép kết hợp chính xác như số thực toán học. Đừng dùng `strictfp` để kỳ vọng mất sai số tự biến mất.

## 2. Khi tổng lớn nuốt mất số hạng nhỏ

Giả sử có dữ liệu:

```java
double[] values = {1e16, 1.0, 1.0, -1e16};
```

Tổng toán học là **2**. Nhưng nếu cộng tuần tự từ trái sang phải:

```java
double sum = 0.0;
for (double value : values) {
    sum += value;
}
System.out.println(sum); // 0.0
```

Diễn biến:

```text
0                  ban đầu
1e16               cộng số rất lớn
1e16               cộng 1.0 nhưng bị làm tròn mất
1e16               cộng 1.0 lần nữa vẫn mất
0                  cộng -1e16 và triệt tiêu
```

Hai số 1 không thể xuất hiện lại ở bước cuối vì thông tin đã bị mất tại hai phép cộng trung gian.

### Ghép nhóm theo ý nghĩa số học

Trong ví dụ này, nếu phép toán được phép đổi thứ tự, ta có thể nhóm hai số lớn để triệt tiêu và hai số nhỏ để cộng:

```java
double better = (values[0] + values[3])
              + (values[1] + values[2]);
System.out.println(better); // 2.0
```

Hoặc cộng hai số nhỏ trước:

```java
double smallFirst = 1.0 + 1.0 + 1e16 - 1e16;
System.out.println(smallFirst); // 2.0
```

Đây là hai ví dụ **cải thiện được kết quả của đúng bộ dữ liệu này**, không phải quy tắc “mọi phép cộng đều phải sắp xếp tăng theo trị tuyệt đối”. Với số hạng cả âm và dương, sự triệt tiêu có thể làm một cách sắp xếp khác tốt hơn. Nếu dữ liệu biểu diễn chuỗi trạng thái phụ thuộc thời gian, đôi khi thứ tự không thể tự ý đổi.

## 3. Ba chiến lược cộng nhiều số

| Phương pháp | Cách làm | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| Cộng tuần tự (*naive summation*) | Lặp `sum += x` | Ít chi phí, dễ hiểu | Các số hạng nhỏ có thể bị mất |
| Cộng từng cặp (*pairwise summation*) | Tính tổng theo cây cân bằng | Thường giảm số bước làm tròn trên mỗi đường tính | Kết quả vẫn phụ thuộc cách chia nhóm |
| Cộng bù (*compensated summation*) | Giữ một phần sai số làm tròn trong biến bổ sung | Có thể bảo toàn những đóng góp nhỏ tốt hơn | Không luôn chính xác, phức tạp hơn |

### 3.1. Pairwise summation

Thay vì cộng một chuỗi dài từ trái sang phải, thuật toán pairwise phân đôi dãy, tính tổng từng nửa, sau đó cộng tổng hai nửa. Điều này giúp giảm chiều sâu cộng của mỗi phần tử từ mức tuyến tính về mức logarit trong cây cân bằng.

```text
x0 + x1 + x2 + x3 + x4 + x5 + x6 + x7

Cộng cặp:     s01    s23    s45    s67
Cộng nhóm:        s0123        s4567
Cộng cuối:               total
```

Pairwise thường hữu ích với dãy dài và có thể phối hợp song song. Tuy nhiên, hai cách chia nhóm có thể cho kết quả khác nhau; không được hứa mọi cây pairwise đều giảm sai số với mọi bộ dữ liệu có triệt tiêu mạnh.

### 3.2. Kahan summation

Thuật toán Kahan lưu `sum` và một biến `compensation` để bù sai số đã phát sinh trong phép cộng:

```java
static double kahanSum(double[] values) {
    double sum = 0.0;
    double compensation = 0.0;

    for (double value : values) {
        double corrected = value - compensation;
        double next = sum + corrected;
        compensation = (next - sum) - corrected;
        sum = next;
    }

    return sum;
}
```

Đây là phương thức cần đặt trong một class. Với `{1e16, 1, 1, -1e16}`, Kahan có thể khôi phục tổng **2.0** do lưu lại phần 1 bị làm tròn mất ở bước đầu và bù ở bước sau.

**Kahan không phải phép cộng chính xác tuyệt đối.** Trong một số dãy triệt tiêu bất lợi, chẳng hạn `{1e16, 1.0, -1e16}`, Kahan chuẩn vẫn có thể không trả 1.0. Khi cần chính xác hoặc độ ổn định cao hơn, cân nhắc Neumaier summation, thuật toán tổng bù nâng cao, số học đa độ chính xác hoặc một cách biểu diễn dữ liệu khác.

### 3.3. Cách chọn

Dùng phép cộng tuần tự khi dữ liệu nhỏ hoặc yêu cầu sai số cho phép. Với số đo lớn, số lượng phần tử lớn và sai số tổng đáng kể, thử pairwise/Kahan cùng bộ dữ liệu kiểm thử. Nếu phép tính là **số nguyên bắt buộc chính xác**, nên dùng `long`, `Math.addExact` hoặc `BigInteger` đúng miền; nếu là tiền cần thập phân chính xác, cân nhắc `BigDecimal`. Không biến vấn đề chính xác tuyệt đối thành bài toán “mẹo cộng double”.

## 4. Triệt tiêu số gần bằng nhau: catastrophic cancellation

Khi trừ hai số gần bằng nhau, kết quả nhỏ có thể chứa **rất ít chữ số có nghĩa đáng tin**, dù mỗi toán hạng nhìn riêng có nhiều chữ số.

Xét công thức:

```text
sqrt(1 + x) - 1
```

với `x = 1e-16`:

```java
double x = 1e-16;
double naive = Math.sqrt(1.0 + x) - 1.0;
System.out.println(naive); // 0.0
```

`1.0 + 1e-16` bị làm tròn thành `1.0`; sau đó căn bậc hai và trừ 1 cho zero. Đầu vào `x` đã bị mất trong khi giá trị toán học của biểu thức vẫn dương gần `5e-17`.

### 4.1. Biến đổi bằng liên hợp

Trong miền biểu thức xác định và mẫu số khác 0:

```text
sqrt(1 + x) - 1
= [sqrt(1 + x) - 1] * [sqrt(1 + x) + 1]
  / [sqrt(1 + x) + 1]
= x / [sqrt(1 + x) + 1]
```

Cách viết ổn định hơn quanh `x=0`:

```java
double x = 1e-16;
double stable = x / (Math.sqrt(1.0 + x) + 1.0);
System.out.println(stable); // 5.0E-17
```

Tử số giữ trực tiếp `x`, nên dù `1.0+x` được làm tròn thành 1.0, phép chia vẫn bảo toàn đóng góp nhỏ.

Điều này minh họa nguyên tắc: **tránh tính hiệu của hai đại lượng gần bằng nhau nếu có công thức tương đương ổn định hơn**. Tuy nhiên phải xét miền xác định: căn yêu cầu `1+x >= 0` trong số thực; với `x=-1` mẫu số vẫn là 1, còn khi các giá trị cực lớn hoặc đặc biệt như Infinity/NaN, cách đánh giá cần được kiểm tra riêng.

### 4.2. Không thể sửa phép tính sau khi dữ liệu đã bị làm tròn mất

Nếu hai giá trị toán học khác nhau đã được lưu thành **cùng một giá trị `double`**, phép trừ giữa chúng chỉ thấy hai giá trị lưu được. Ép kiểu sau phép trừ hoặc đảo hai toán hạng không khôi phục thông tin ban đầu.

Giải pháp phải xuất hiện **trước bước mất thông tin**: đổi công thức, giữ số hạng nhỏ riêng, sử dụng kiểu chính xác hơn hoặc làm việc trực tiếp với dữ liệu gốc.

## 5. Chọn Math.log1p và Math.expm1 khi x gần 0

Thư viện Java cung cấp hàm tránh mất thông tin trong hai biểu thức rất thường gặp.

### Math.log1p(x): log tự nhiên của 1+x

```java
double x = 1e-16;
double naive = Math.log(1.0 + x); // 0.0
double stable = Math.log1p(x);    // Số dương gần 1e-16
```

Khi `x` rất nhỏ, phép `1.0+x` có thể làm tròn về 1, khiến `Math.log(1.0)` bằng 0. `Math.log1p` được thiết kế cho `ln(1+x)` và giữ độ chính xác tốt hơn ở vùng đó.

### Math.expm1(x): exp(x)-1

```java
double x = 1e-16;
double naive = Math.exp(x) - 1.0; // 0.0
double stable = Math.expm1(x);    // Số dương gần 1e-16
```

Trong phép tính trực tiếp, `exp(x)` có thể làm tròn về 1 rồi phép trừ làm mất kết quả. `Math.expm1` tránh kiểu triệt tiêu này.

Hai hàm có ích trong xác suất, thống kê, mô hình tăng trưởng và một số công thức tài chính; nhưng chỉ thay thế khi **ý nghĩa toán học cần tính đúng là `ln(1+x)` hoặc `exp(x)-1`**.

## 6. Đổi nhóm nhân/chia để tránh overflow và underflow trung gian

Một biểu thức có kết quả toán học trong miền `double` vẫn có thể thất bại nếu **kết quả trung gian** vượt miền.

### 6.1. Tràn thành Infinity quá sớm

```java
double x = Double.MAX_VALUE;

double overflowFirst = (x * 2.0) / 2.0; // Infinity
double scaleFirst = x * (2.0 / 2.0);    // Double.MAX_VALUE
```

Trong toán học cả hai bằng `x`. Nhưng phép `x*2` ở vế đầu tràn thành vô cực; chia vô cực cho 2 không đưa nó về hữu hạn. Phép tính ở vế sau tạo tỷ lệ 1 trước nên không tràn.

### 6.2. Underflow về zero quá sớm

```java
double tiny = 1e-300;

double underflowFirst = (tiny * tiny) / tiny; // 0.0
double ratioFirst = tiny * (tiny / tiny);     // 1.0E-300
```

`tiny*tiny` có độ lớn `1e-600`, quá nhỏ để lưu trong `double`; giá trị bị làm tròn thành 0. Tính tỷ lệ `tiny/tiny=1` trước tránh vấn đề cho bộ dữ liệu này.

**Chú ý:** không phải cứ “chia trước” là tốt. Với mẫu số có thể bằng zero, rất nhỏ, rất lớn hoặc chứa NaN/Infinity, đổi thứ tự có thể gây lỗi mới. Cần xác minh miền xác định, dấu, giới hạn và chính sách sai số.

### 6.3. Math.hypot tránh bình phương rồi mới lấy căn

Độ dài của vector 2D:

```text
sqrt(x² + y²)
```

Nếu tính trực tiếp:

```java
double x = 1e200;
double y = 1e200;
double naive = Math.sqrt(x * x + y * y); // Infinity
```

Vì `x*x` đã vượt miền hữu hạn của `double`, kết quả là vô cực, dù độ dài thực khoảng `1.414e200` vẫn hữu hạn.

`Math.hypot(x, y)` dùng cách tính ổn định hơn cho căn tổng bình phương, tránh overflow/underflow trung gian không cần thiết:

```java
double better = Math.hypot(1e200, 1e200);
System.out.println(Double.isFinite(better)); // true
```

`Math.hypot` không bảo đảm mọi đầu vào có kết quả hữu hạn: nếu **độ dài toán học** vượt miền biểu diễn, kết quả vẫn có thể vô cực.

## 7. Math.fma: giảm một lần làm tròn ở tích cộng

`Math.fma(a, b, c)` tính `a*b+c` bằng phép *fused multiply-add*, với một lần làm tròn ở cuối. Trong khi đó, biểu thức `a*b+c` có thể làm tròn sau nhân và làm tròn tiếp sau cộng.

```java
double u = Math.ulp(1.0);
double a = 1.0 + u;
double b = 1.0 - u;

double separate = a * b - 1.0;     // 0.0
double fused = Math.fma(a, b, -1.0); // Một số âm rất nhỏ.
```

Tích chính xác là `(1+u)(1-u)=1-u²`. Phép nhân riêng làm tròn về 1, rồi trừ 1 thành 0. FMA giữ giá trị trước khi làm tròn cuối và có thể cho kết quả âm khác 0.

FMA hữu ích ở một số thuật toán vector, đa thức và cộng dồn tích, nhưng **không có nghĩa mọi phép tính đều chính xác tuyệt đối**. Vì nó cho kết quả khác nhân/cộng tách rời, không tự ý thay nếu hệ thống cần tính tương thích bit-for-bit.

## 8. Tính toán có thứ tự khác vẫn phải đúng về kiểu và miền

Thứ tự phép toán không chỉ là vấn đề số thực; một phép tính nguyên có thể **tràn trước khi chuyển sang `double`**:

```java
int count = 1_500_000_000;

double wrong = count * 3;          // Tích int tràn trước khi gán.
double floating = (double) count * 3; // Nhân double, không tràn int.
long exact = (long) count * 3;     // 4_500_000_000L, nguyên chính xác.
```

Nếu cần kết quả **số nguyên chính xác**, phương án `long` phù hợp hơn khi nó đủ miền, hoặc có thể dùng `Math.multiplyExact`/`BigInteger` khi cần kiểm tra. Chuyển sang `double` giúp tránh tràn ở ví dụ này nhưng có thể đánh mất các đơn vị nhỏ của những số nguyên lớn hơn `2^53`.

Cũng cần xét các phép chia: `int/int` bỏ phần lẻ trước khi gán vào `double`; ép sang `double` ở **một toán hạng trước phép chia** nếu muốn tính tỷ lệ gần đúng.

## 9. Đo sai số thay vì đánh giá kết quả bằng mắt

Một cách sắp xếp chỉ nên được gọi là “tốt hơn” khi có **giá trị tham chiếu** hoặc tiêu chí sai số.

Hai thước đo phổ biến:

```text
sai_số_tuyệt_đối = |kết_quả - tham_chiếu|
sai_số_tương_đối = sai_số_tuyệt_đối / |tham_chiếu|
```

Sai số tương đối không dùng trực tiếp khi tham chiếu bằng 0. Khi kết quả thật gần 0, cần ngưỡng tuyệt đối có đơn vị, phân tích độ nhạy hoặc quy tắc miền rõ ràng.

Ví dụ tổng của `{1e16,1,1,-1e16}` có tham chiếu toán học chính xác bằng 2. Phép cộng tuần tự cho 0 nên sai số tuyệt đối bằng 2; ghép nhóm và Kahan cho 2 nên sai số bằng 0 **đối với chính dữ liệu này**.

Phân biệt:

- **Điều kiện bài toán** (*conditioning*): đầu vào thay đổi rất ít có thể làm kết quả toán học thay đổi tương đối nhiều; đặc biệt với hiệu hai số gần bằng nhau.
- **Độ ổn định thuật toán** (*numerical stability*): thuật toán có khuếch đại sai số không cần thiết do thứ tự phép toán và biểu diễn trung gian không?

Một thuật toán ổn định hơn không thể tự loại bỏ sai số vốn đã có trong dữ liệu đo. Cần biết độ chính xác nguồn và sai số được chấp nhận trước khi thay đổi công thức.

### Checklist đánh giá một phép biến đổi

1. Xác định ý nghĩa dữ liệu: số đo gần đúng, tổng nguyên chính xác, tiền tệ hay chỉ số?
2. Đọc kiểu của **từng biểu thức con**: phép nào đã tràn hoặc làm tròn trước khi gán?
3. Xem có cộng nhiều số rất nhỏ vào tổng lớn hay không; có thể thay bằng ghép nhóm, pairwise hoặc compensated summation?
4. Xem có trừ hai giá trị gần bằng nhau hay không; có công thức tương đương tránh triệt tiêu?
5. Với nhân chia, kiểm tra overflow/underflow trung gian và miền mẫu số.
6. Dùng `Math.log1p`, `Math.expm1`, `Math.hypot`, `Math.fma` khi đúng mục đích và điều kiện áp dụng.
7. Dùng test có kết quả chuẩn và đánh giá sai số tuyệt đối/tương đối có đơn vị.
8. Thử các trường hợp số dương/âm, triệt tiêu mạnh, zero, số rất lớn/rất nhỏ, NaN và Infinity.
9. Kiểm soát thứ tự tính toán trong tác vụ song song nếu cần tái lập kết quả bit-for-bit.
10. Không giả định một phép đổi dấu ngoặc hợp lý trên dữ liệu mẫu luôn tốt trên mọi miền.

## 10. Chương trình Java 17+ hoàn chỉnh

Tạo file **`CalculationOrderDemo.java`**:

```java
public class CalculationOrderDemo {
    static double naiveSum(double[] values) {
        double sum = 0.0;
        for (double value : values) {
            sum += value;
        }
        return sum;
    }

    static double kahanSum(double[] values) {
        double sum = 0.0;
        double compensation = 0.0;
        for (double value : values) {
            double corrected = value - compensation;
            double next = sum + corrected;
            compensation = (next - sum) - corrected;
            sum = next;
        }
        return sum;
    }

    public static void main(String[] args) {
        double large = 1e16;

        System.out.println("lost=" + ((large + 1.0) - large));
        System.out.println("kept=" + ((large - large) + 1.0));
        System.out.println("ulp=" + Math.ulp(large));

        double[] values = {1e16, 1.0, 1.0, -1e16};
        System.out.println("naive-sum=" + naiveSum(values));
        System.out.println("grouped-sum=" +
                ((values[0] + values[3]) + (values[1] + values[2])));
        System.out.println("kahan-sum=" + kahanSum(values));

        double max = Double.MAX_VALUE;
        System.out.println("overflow-first=" +
                Double.isInfinite((max * 2.0) / 2.0));
        System.out.println("scale-first=" +
                (max * (2.0 / 2.0) == max));

        double tiny = 1e-300;
        System.out.println("underflow-first=" +
                ((tiny * tiny) / tiny));
        System.out.println("ratio-first=" +
                (tiny * (tiny / tiny)));

        double x = 1e-16;
        System.out.println("root-naive=" +
                (Math.sqrt(1.0 + x) - 1.0));
        System.out.println("root-stable=" +
                (x / (Math.sqrt(1.0 + x) + 1.0)));
        System.out.println("log-naive=" + Math.log(1.0 + x));
        System.out.println("log1p-positive=" + (Math.log1p(x) > 0.0));
        System.out.println("expm1-positive=" + (Math.expm1(x) > 0.0));

        double huge = 1e200;
        double naiveHypot = Math.sqrt(huge * huge + huge * huge);
        System.out.println("hypot-naive-infinite=" +
                Double.isInfinite(naiveHypot));
        System.out.println("hypot-stable-finite=" +
                Double.isFinite(Math.hypot(huge, huge)));

        double ulp = Math.ulp(1.0);
        double a = 1.0 + ulp;
        double b = 1.0 - ulp;
        System.out.println("fma-separate-zero=" +
                (a * b - 1.0 == 0.0));
        System.out.println("fma-negative=" +
                (Math.fma(a, b, -1.0) < 0.0));
    }
}
```

Biên dịch và chạy:

```bash
javac CalculationOrderDemo.java
java CalculationOrderDemo
```

Stdout:

```text
lost=0.0
kept=1.0
ulp=2.0
naive-sum=0.0
grouped-sum=2.0
kahan-sum=2.0
overflow-first=true
scale-first=true
underflow-first=0.0
ratio-first=1.0E-300
root-naive=0.0
root-stable=5.0E-17
log-naive=0.0
log1p-positive=true
expm1-positive=true
hypot-naive-infinite=true
hypot-stable-finite=true
fma-separate-zero=true
fma-negative=true
```

**Cách đọc kết quả:** `lost`/`kept` và ba cách cộng cho thấy dữ liệu nhỏ có thể bị mất hoặc được giữ; `overflow-first`/`underflow-first` cho thấy giá trị trung gian quyết định kết quả; `root-stable`, `log1p-positive` và `expm1-positive` cho thấy công thức/hàm ổn định hơn gần 0; `Math.hypot` tránh overflow của bình phương; hai dòng FMA cho thấy giảm một lần làm tròn có thể làm kết quả khác nhân/trừ riêng.

## 11. Những sai lầm thường gặp

| Nhầm lẫn | Tác hại | Cách xử lý |
| --- | --- | --- |
| Coi `(a+b)+c` luôn bằng `a+(b+c)` | Mất số hạng nhỏ hoặc khác kết quả | Phân tích ULP và thử dữ liệu biên |
| Cộng tất cả số nhỏ sau khi tổng đã rất lớn | Đóng góp nhỏ có thể bị nuốt | Thử ghép nhóm, pairwise, Kahan |
| Khẳng định luôn phải cộng theo trị tuyệt đối tăng dần | Không đúng cho mọi dãy có dấu; có thể đổi semantics | Chỉ đổi thứ tự khi miền cho phép, đo sai số |
| Coi Kahan luôn exact | Có trường hợp triệt tiêu mà Kahan vẫn sai | Kiểm thử, cân nhắc Neumaier/độ chính xác cao |
| Lấy hiệu hai số gần bằng nhau mà không xét sai số | Mất nhiều chữ số có nghĩa | Dùng công thức tránh triệt tiêu, chẳng hạn liên hợp |
| Tính `log(1+x)` hoặc `exp(x)-1` khi x quá nhỏ | Kết quả có thể về zero | Dùng `log1p` và `expm1` đúng mục đích |
| Tính `sqrt(x*x+y*y)` với x,y lớn | Bình phương có thể vô cực | Dùng `Math.hypot` |
| Nghĩ chia trước luôn an toàn | Có thể chia cho 0 hoặc sai ở miền khác | Chứng minh điều kiện và kiểm thử |
| Nghĩ `Math.fma` và `a*b+c` phải luôn cùng bit | Khác số lần làm tròn | Chọn theo thuật toán, xem tính tương thích |
| Ép kiểu sau phép nhân nguyên đã tràn | Giá trị đã mất trước khi cast | Nâng kiểu trước, dùng checked arithmetic |
| Dùng `double` cho số lượng/tiền phải chính xác | Không bảo đảm giữ mọi đơn vị | Dùng kiểu nguyên hoặc thập phân chính xác |
| Chỉ nhìn vài dòng output có vẻ hợp lý | Không thấy ca gần giới hạn và triệt tiêu | Có kết quả tham chiếu và chỉ tiêu sai số |

## 12. Bài tập tự luyện

**Bài 1 – Thứ tự và ULP.** Tính `Math.ulp(1e16)`; dự đoán `(1e16+1)-1e16` và `(1e16-1e16)+1`. Vì sao hai đáp án khác nhau?

**Bài 2 – Tổng bốn số.** Với `{1e16, 1.0, 1.0, -1e16}`, tính tổng toán học, tổng tuần tự, tổng ghép nhóm và tổng Kahan. Hoán vị dữ liệu và quan sát thay đổi.

**Bài 3 – Phản ví dụ cho Kahan.** Thử `{1e16, 1.0, -1e16}`. Có thể chỉ dùng Kahan mà bảo đảm tổng chính xác 1.0 không? Hãy giải thích.

**Bài 4 – Triệt tiêu gần zero.** Chứng minh bằng liên hợp `sqrt(1+x)-1 = x/(sqrt(1+x)+1)`. Kiểm thử `x=1e-16`; nêu miền xác định.

**Bài 5 – Hàm thư viện ổn định.** Dùng `Math.log1p` và `Math.expm1` để tính những biểu thức tương đương với `log(1+x)` và `exp(x)-1` khi x gần 0. So sai số với kết quả độ chính xác cao.

**Bài 6 – Overflow/underflow trung gian.** Giải thích sự khác biệt của `(Double.MAX_VALUE*2)/2` và `Double.MAX_VALUE*(2/2)` với các literal kiểu double. Làm tương tự cho `1e-300` nhân/chia.

**Bài 7 – Độ dài vector.** So `Math.sqrt(x*x+y*y)` với `Math.hypot(x,y)` khi `x=y=1e200` và khi `x,y` rất nhỏ. Kết quả toán học có nằm trong miền double không?

**Bài 8 – FMA và tái lập kết quả.** Viết test cho `Math.fma(a,b,-1)` với `a=1+ulp(1)`, `b=1-ulp(1)`. Vì sao dùng FMA có thể thay đổi kết quả bitwise?

**Bài 9 – Thiết kế thực tế.** Một hệ thống tổng hợp hàng triệu phép đo trên các worker song song cần kết quả ổn định và lặp lại. Bạn sẽ cố định cây reduction, chọn thuật toán tổng nào, xử lý NaN/Infinity ra sao và đo sai số như thế nào?

## 13. Ghi nhớ

- Phép cộng và nhân dấu phẩy động **không kết hợp tổng quát**; thay đổi thứ tự có thể ảnh hưởng kết quả.
- Số hạng quá nhỏ so với tổng đang có có thể bị làm tròn mất; ghép nhóm, pairwise hoặc Kahan có thể cải thiện nhưng không bảo đảm đúng tuyệt đối.
- Trừ hai số gần bằng nhau có thể mất chữ số có nghĩa; ưu tiên biến đổi công thức để tránh triệt tiêu khi có thể.
- `Math.log1p`, `Math.expm1`, `Math.hypot` giúp giải quyết các dạng mất thông tin trung gian thường gặp.
- Nhân/chia theo thứ tự không phù hợp có thể overflow thành Infinity hoặc underflow về zero trước khi kết quả cuối được tính.
- `Math.fma` khác biểu thức nhân cộng riêng vì chỉ làm tròn một lần.
- Chọn kiểu đủ chính xác cho miền dữ liệu; **không có mẹo đổi thứ tự nào thay thế được `BigInteger`, `BigDecimal` hoặc checked arithmetic khi nghiệp vụ yêu cầu chính xác**.
- Mọi tối ưu độ ổn định nên có **kết quả chuẩn, kiểm thử biên và tiêu chí sai số**.

**Kết luận:** thay đổi thứ tự phép tính có thể giảm mất thông tin trong Java, nhưng chỉ khi đã hiểu nguyên nhân sai số và miền dữ liệu. Hãy chọn một công thức/thuật toán ổn định hơn dựa trên kiểm chứng, thay vì chỉ đổi dấu ngoặc theo thói quen.

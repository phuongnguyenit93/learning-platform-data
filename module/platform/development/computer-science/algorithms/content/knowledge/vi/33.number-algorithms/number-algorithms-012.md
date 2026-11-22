# Kiểm tra phần dư, độ nhạy và kết quả có vẻ hội tụ sai

> **Chủ đề:** Computer Science Algorithms → **Thuật toán số**.  
> **Mục tiêu:** Không kết luận một nghiệm số đã đúng chỉ vì phần dư nhỏ hoặc bước lặp bằng không. Bài học phân biệt **sai số nghiệm**, **phần dư**, **sai số lùi**, **độ điều kiện**; giải thích hội tụ giả do nghiệm bội, phép tính mất chữ số, số học dấu phẩy động, phương trình gián đoạn, sai nhánh, hệ tuyến tính kém điều kiện. Thực hành với các phép chẩn đoán, bisection giữ khoảng, Newton có bảo vệ, kiểm thử độc lập và **bốn chương trình Java 17 chạy được**.

## 1. Đừng chỉ nhìn chữ “CONVERGED”

Xét phương trình một biến `f(x)=0` và kết quả máy tính trả `xHat`. Một log như:

```text
iteration=100
residual=1.0e-9
step=0.0
status=CONVERGED
```

**Chưa đủ** để khẳng định xHat gần một nghiệm mà bài toán cần. Nó có thể có phần dư nhỏ chỉ vì hệ số của f rất nhỏ; bước bằng0 chỉ vì double không thể biểu diễn bước bé hơn; hoặc giá trị f(xHat) bị làm tròn thành0 do mất chữ số.

Trước khi công nhận nghiệm cần trả lời:

1. Có **nghiệm nào** trong miền đang xét, và máy có chọn **đúng nhánh** không?
2. Residual được tính **ổn định** và đúng đơn vị không?
3. Bài toán có **nhạy** đến mức một residual bé vẫn tương ứng error lớn không?
4. Bước lặp đang tiến gần nghiệm hay chỉ **stagnate** vì floating-point?
5. Có **bất biến hoặc định lý** nào chặn sai số nghiệm không?
6. Nếu không kết luận được, API có trả `STAGNATED`, `NONFINITE`, `MAX_ITER` thay vì “success” không?

Bài tập trung vào **kiểm nghiệm hậu điều kiện** của thuật toán số. Nó không đánh đồng “chương trình không báo exception” với “nghiệm chính xác”.

### 1.1. Các ký hiệu

- x* — nghiệm toán học đích của `f(x*)=0`.
- x̂ — nghiệm gần đúng (*approximate solution*) máy trả.
- `r=f(x̂)` — phần dư toán học; `rHat` — phần dư tính thực tế bằng floating-point.
- `e=x̂−x*` — sai số nghiệm (*forward error*).
- `tolX` — ngưỡng sai số ở biến x; `tolF` — ngưỡng độ lớn của f; chúng có thể **khác đơn vị**.
- Với `Ax=b`, x*, x̂ là vectơ; `r=b−Ax̂` và dùng một chuẩn phù hợp.

Trong thực tế x* thường **không biết**, nên không thể tính `|e|` trực tiếp. Cần **chặn sai số**, nghiệm oracle, hoặc đánh giá độ điều kiện để hiểu độ tin cậy.

## 2. Forward error, residual, backward error

### 2.1. Sai số tiến — chất lượng biến cần tìm

Với một nghiệm vô hướng:

`eAbs=|x̂−x*|`.

Nếu x* khác0:

`eRel=|x̂−x*|/|x*|`.

Nếu x*=0, mẫu số của eRel bằng0 và **sai số tương đối theo định nghĩa này không tồn tại**. Khi nghiệm gần0, ngưỡng tuyệt đối và scaleX phải được cân nhắc.

### 2.2. Residual — độ thỏa phương trình

`residual=|f(x̂)|`.

Nó đo mức độ x̂ thỏa **phương trình**, không trực tiếp đo khoảng cách đến nghiệm. Đơn vị của residual là đơn vị đầu ra f, không bắt buộc giống đơn vị của x.

Nếu f được nhân với 10^9, **tập nghiệm không đổi**, nhưng residual nhân với 10^9. Do đó dùng `tolF=1e-10` tuyệt đối cho mọi phương trình mà không xét scale là không ổn.

### 2.3. Backward error — nhiễu bài toán

Một cách hiểu đơn giản: x̂ là nghiệm đúng của một bài toán đầu vào bị nhiễu nhỏ cỡ nào?

Với `f(x)=0`, đặt:

`δ=−f(x̂)`.

Khi đó x̂ giải đúng phương trình nhiễu:

`f(x)+δ=0`.

Với hệ tuyến tính `Ax=b`, phần dư r=b−Ax̂ cho:

`Ax̂=b−r`.

Như vậy x̂ là nghiệm chính xác của hệ có vế phải đã thay thành b−r. **Bài toán bị nhiễu ít** không đảm bảo nghiệm cũng đổi ít nếu hệ **kém điều kiện**.

### 2.4. Thước đo không hoán đổi được

| Thước đo | Câu hỏi | Hạn chế |
|---|---|---|
| Forward error | x̂ cách x* bao xa? | x* thường chưa biết |
| Relative forward error | Error so với quy mô x*? | Không định nghĩa khi x*=0 |
| Residual | f(x̂) gần0 tới đâu? | Có thể nhỏ dù error lớn |
| Backward error | Bài toán phải nhiễu bao nhiêu để x̂ là nghiệm đúng? | Không trực tiếp nói error khi bài toán nhạy |
| Error bound | Có chứng minh được giới hạn error không? | Cần giả thiết, ví dụ bracket/đạo hàm |

## 3. Độ nhạy của nghiệm là thuộc tính bài toán

Nếu f khả vi gần nghiệm đơn x*, `f'(x*)≠0`, tuyến tính hóa cho:

`f(x̂)≈f'(x*)·(x̂−x*)`.

Do đó:

`|x̂−x*|≈|f(x̂)|/|f'(x*)|`.

Đạo hàm càng nhỏ, cùng residual càng dễ tương ứng error lớn. Đạo hàm rất lớn thì residual lớn không tự chứng minh error x lớn.

### 3.1. Chặn error từ derivative lower bound

Giả sử f liên tục trên đoạn nối x̂ và một nghiệm x*, khả vi trong đoạn trong. Nếu biết:

`|f'(x)|≥m>0`

cho **mọi x trên đoạn đó**, định lý giá trị trung bình cho:

`|x̂−x*| ≤ |f(x̂)|/m`.

Đây là chặn có **giả thiết rõ ràng**. Nếu chỉ kiểm `|f'(x̂)|` tại đúng một điểm, chưa chắc đó là chặn dưới hợp lệ trên cả đoạn. Với nghiệm bội, f' có thể bằng0 ngay tại nghiệm nên không có m>0 cho đoạn chứa nó.

### 3.2. Ví dụ hàm rất phẳng

`f(x)=10^-15·(x−1,000,000)`.

Nghiệm đúng x*=1,000,000. Tại x̂=0:

`|f(0)|=10^-9`,

nhưng `|0−1,000,000|=1,000,000`.

Một hệ thống chỉ kiểm `|f(x̂)|≤10^-8` sẽ nhận nghiệm **sai rất xa**. Chặn đạo hàm m=10^-15 cũng chỉ cho `e≤10^6`, đúng là không đảm bảo độ chính xác x.

### 3.3. Ví dụ hàm rất dốc

`g(x)=10^12·(x−1)`.

Tại x̂≈1+10^-9, error theo x khoảng10^-9, residual khoảng10^3. Một `tolF=10^-8` sẽ từ chối dù sai số x có thể hợp yêu cầu ứng dụng.

### 3.4. Điều kiện số và scale

Độ điều kiện là tính chất của **ánh xạ từ dữ liệu đến nghiệm**. Độ ổn định của **thuật toán** là câu hỏi khác: nó có làm tăng sai số bất thường so với mức nhạy vốn có của bài toán không? Không thể kết luận “thuật toán sai” chỉ từ error lớn trong một bài toán cực nhạy; nhưng cũng không thể dùng conditioning để biện minh cho việc bỏ kiểm hậu điều kiện.

## 4. Nghiệm bội khiến phần dư giảm nhanh hơn error

Với:

`f(x)=(x−1)²`,

nghiệm x*=1 có bội2 và `f'(1)=0`.

Nếu x̂=1.001, ta có:

`|x̂−x*|≈10^-3`,

`|f(x̂)|≈10^-6`.

Residual nhỏ hơn error **ba bậc**. Nếu đặt `tolF=10^-5` và yêu cầu error x<10^-5, phép kiểm residual-only sẽ **báo nhầm**.

Tổng quát gần nghiệm bội m:

`f(x)≈c(x−x*)^m`

⇒ `|x−x*|≈(|f(x)|/|c|)^(1/m)`.

Không dùng giả thiết tuyến tính gần nghiệm khi f' bằng0.

### 4.1. Nghiệm bội chẵn không nhất thiết đổi dấu

Trên [0,2], `f(x)=(x−1)²` có f(0)=f(2)=1>0 nhưng vẫn có nghiệm1. Một bisection chuẩn có điều kiện **đổi dấu** sẽ từ chối khoảng này; đó **không phải chứng minh vô nghiệm**.

### 4.2. Newton gần nghiệm bội

Với f=(x−1)², từ x≠1:

`xNew=x−(x−1)²/[2(x−1)]=(x+1)/2`.

Sai số chỉ giảm một nửa mỗi vòng, tức hội tụ tuyến tính thay vì bậc hai. Nếu solver giả định cứ Newton là “gấp đôi chữ số đúng” thì sẽ đặt điều kiện dừng/chi phí sai.

### 4.3. Nhiều nghiệm và sai nhánh

`f(x)=(x−2)(x−5)` có hai nghiệm. Một ứng dụng cần x trong [4,6] không được nhận x≈2 dù residual bằng0. Hậu điều kiện phải kiểm **nhánh hoặc miền vật lý**, không chỉ giá trị f.

## 5. Hệ tuyến tính: residual nhỏ và error lớn cùng tồn tại

Cho:

`A=diag(1,10^-12)`,

`b=(1,10^-12)`.

Nghiệm đúng `x*=(1,1)`.

Đặt nghiệm thử `x̂=(1,1000)`:

`Ax̂=(1,10^-9)`,

`r=b−Ax̂=(0,−9.99·10^-10)`.

Theo chuẩn vô cực `||v||∞=max_i |v_i|`:

`||r||∞=9.99·10^-10`,

nhưng:

`||x̂−x*||∞=999`.

Đây là một ví dụ rõ về **false confidence** từ residual-only.

### 5.1. Số điều kiện của ma trận

Chuẩn ma trận vô cực:

`||A||∞=max_i Σ_j |a_ij|`.

Với A khả nghịch:

`κ∞(A)=||A||∞·||A^-1||∞`.

Trong ví dụ, `||A||∞=1` và `A^-1=diag(1,10^12)`, nên:

`κ∞(A)=10^12`.

Nói cách khác, bài toán có thể khuếch đại nhiễu dữ liệu đáng kể theo một phương.

### 5.2. Bound error từ residual

Do `Ax*=b`, `r=b−Ax̂`:

`A(x*−x̂)=r`,

nên:

`||x*−x̂||≤||A^-1||·||r||`.

Khi b≠0, x*≠0:

`||x*−x̂||/||x*|| ≤ κ(A)·||r||/||b||`.

Trong ví dụ, vế phải là:

`10^12·(9.99·10^-10)/1=999`.

Chặn error **không nhỏ**, phù hợp với kết quả sai999.

### 5.3. Backward residual đã chuẩn hóa

Một thước đo normwise backward error:

`η=||r||/(||A||·||x̂||+||b||)`,

nếu mẫu khác0. Tại x̂=(1,1000):

`η=9.99·10^-10/(1000+1)≈9.980·10^-13`.

η nhỏ nhưng error lớn999: **backward accuracy** và **forward accuracy** không giống nhau khi κ lớn. Không nói đơn giản “κ·η là luôn chặn forward error” nếu chưa chỉ rõ điều kiện và cách chuẩn hóa; bound ở mục5.2 dùng relative residual `||r||/||b||`.

### 5.4. Khi kiểm Ax≈b

Một quy trình tốt:

1. Tính `r=b−Ax̂` đủ ổn định; nếu cần, đánh giá residual ở precision cao hơn phép giải.
2. Lưu `||r||`, relative residual khi b≠0 và normwise backward eta.
3. Ước lượng hoặc chặn κ(A), kiểm rank/khả nghịch.
4. Kiểm ràng buộc nghiệm (không âm, tổng1, thuộc miền...).
5. Nếu κ lớn, tăng precision hoặc dùng phương pháp ổn định hơn; không hứa sai số nghiệm chỉ từ residual.

Với least squares, normal equations `AᵀA` có thể làm điều kiện xấu đi theo bình phương κ₂(A) khi A đầy đủ hạng cột; QR/SVD là lựa chọn đáng xem xét.

## 6. Java 17 — chẩn đoán residual và conditioning

Chương trình này có nghiệm tham chiếu **biết trước** để so forward error trong demo. Khi giải bài thực tế chưa có nghiệm chuẩn, forward error phải được **chặn/ước lượng**, không tự tính từ một nghiệm không tồn tại trong code.

Lưu **ResidualConditionNumberDemo.java**:

```java
import java.util.Locale;

public class ResidualConditionNumberDemo {
    public static void main(String[] args) {
        double exactRoot = 1_000_000.0;
        double approximation = 0.0;
        double residual = Math.abs(1e-15
                * (approximation - exactRoot));
        double forwardError = Math.abs(approximation - exactRoot);

        System.out.printf(Locale.ROOT,
                "flat |r|=%.3e, |error|=%.1f%n",
                residual, forwardError);
        System.out.println("flat residual pass: "
                + (residual <= 1e-8));
        System.out.println("flat root error pass: "
                + (forwardError <= 1e-8));

        double x1 = 1.0, x2 = 1000.0;
        double b1 = 1.0, b2 = 1e-12;
        double r1 = b1 - x1;
        double r2 = b2 - 1e-12 * x2;
        double rInf = Math.max(Math.abs(r1), Math.abs(r2));
        double eInf = Math.max(Math.abs(x1 - 1.0),
                               Math.abs(x2 - 1.0));

        double aInf = 1.0;
        double inverseInf = 1e12;
        double kappa = aInf * inverseInf;
        double xInf = Math.max(Math.abs(x1), Math.abs(x2));
        double bInf = Math.max(Math.abs(b1), Math.abs(b2));
        double eta = rInf / (aInf * xInf + bInf);
        double forwardBound = kappa * rInf / bInf;

        System.out.printf(Locale.ROOT,
                "linear residual infinity=%.3e%n", rInf);
        System.out.printf(Locale.ROOT,
                "linear forward error infinity=%.1f%n", eInf);
        System.out.printf(Locale.ROOT,
                "linear kappa infinity=%.3e%n", kappa);
        System.out.printf(Locale.ROOT,
                "linear backward eta=%.3e%n", eta);
        System.out.printf(Locale.ROOT,
                "linear forward bound=%.3e%n", forwardBound);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ResidualConditionNumberDemo.java
java ResidualConditionNumberDemo
```

Stdout:

```text
flat |r|=1.000e-09, |error|=1000000.0
flat residual pass: true
flat root error pass: false
linear residual infinity=9.990e-10
linear forward error infinity=999.0
linear kappa infinity=1.000e+12
linear backward eta=9.980e-13
linear forward bound=9.990e+02
```

**Đọc kết quả:** Cùng một số `r` nhỏ có thể không cho biết error x. Chỉ khi thêm conditioning, chặn error hoặc nghiệm oracle, thông tin chất lượng mới đủ.

## 7. Phần dư tính bằng máy cũng có thể sai

Cùng một đa thức:

`p(x)=(x−1)²=x²−2x+1`.

Toán học nói hai dạng tương đương. Nhưng với double `x=1.0+1e-8`:

- Dạng khai triển `x*x−2*x+1` có thể tính ra **0.0**.
- Dạng nhân tử `(x−1)*(x−1)` tính được khoảng **10^-16**.

Đây là **catastrophic cancellation**: phép trừ các số gần nhau làm mất chữ số có nghĩa; kết quả nhỏ có thể bị xóa hoàn toàn bởi làm tròn trong các số hạng cỡ1.

### 7.1. Vì sao fHat(x)==0 không phải chứng chỉ f(x)==0?

Một phép đánh giá floating có thể trả0 do triệt tiêu dù giá trị đa thức tại **số double x đang lưu** khác0. Nếu điều kiện dừng chỉ `f(x)==0.0`, nó sẽ báo thành công giả. Kiểm residual cần **công thức ổn định**, thậm chí một cách tính độc lập hoặc precision cao hơn khi cần.

### 7.2. Horner có đủ không?

Horner giảm số phép nhân của đa thức, thường hữu ích. Nhưng gần nghiệm bội, chính Horner vẫn có thể bị triệt tiêu. Nếu biểu thức dạng tích nhân tử đã biết và ổn định gần nghiệm, có thể ưu tiên dạng tích để kiểm residual.

### 7.3. Chú ý dữ liệu gốc

`1.0+1e-8` đã được làm tròn thành một số double. Dạng nhân tử chỉ bảo toàn residual **tốt hơn tại giá trị double ấy**; nó không khôi phục phần sai số của dữ liệu thập phân nếu thông tin đó đã mất trước khi tính.

## 8. Hàm sơ cấp ổn định: expm1 và log1p

Với x rất nhỏ:

`exp(x)−1` và `log(1+x)` dễ làm mất chữ số khi exp(x) hoặc1+x bị làm tròn quá gần1.

Java có:

- `Math.expm1(x)`: tính `exp(x)−1` ổn định hơn quanh x≈0.
- `Math.log1p(x)`: tính `log(1+x)` ổn định hơn quanh x≈0.

Với x=10^-12, tính theo biểu thức ngây thơ có thể cho:

`Math.exp(x)-1 ≈ 1.000089×10^-12`,

`Math.log(1+x) ≈ 1.000089×10^-12`.

Trong khi phiên bản chuyên dụng cho gần0 cho khoảng:

`Math.expm1(x) ≈ 1.000000×10^-12`,

`Math.log1p(x) ≈ 1.000000×10^-12`.

Một solver dùng f bị đánh giá sai có thể tạo **bước Newton sai** vì công thức `x−f/f'` phụ thuộc trực tiếp chất lượng f.

## 9. Java 17 — kiểm residual theo hai biểu thức độc lập

Lưu **StableResidualEvaluationDemo.java**:

```java
import java.util.Locale;

public class StableResidualEvaluationDemo {
    static double expanded(double x) {
        return x * x - 2.0 * x + 1.0;
    }
    static double factored(double x) {
        double d = x - 1.0;
        return d * d;
    }

    public static void main(String[] args) {
        double x = 1.0 + 1e-8;
        double a = expanded(x);
        double b = factored(x);

        System.out.printf(Locale.ROOT,
                "expanded p(x)=%.6e%n", a);
        System.out.printf(Locale.ROOT,
                "factored p(x)=%.6e%n", b);
        System.out.println("expanded reports zero: " + (a == 0.0));
        System.out.println("factored is positive: " + (b > 0.0));

        double delta = 1e-12;
        System.out.printf(Locale.ROOT,
                "exp(delta)-1=%.6e%n", Math.exp(delta) - 1.0);
        System.out.printf(Locale.ROOT,
                "expm1(delta)=%.6e%n", Math.expm1(delta));
        System.out.printf(Locale.ROOT,
                "log(1+delta)=%.6e%n", Math.log(1.0 + delta));
        System.out.printf(Locale.ROOT,
                "log1p(delta)=%.6e%n", Math.log1p(delta));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 StableResidualEvaluationDemo.java
java StableResidualEvaluationDemo
```

Stdout:

```text
expanded p(x)=0.000000e+00
factored p(x)=1.000000e-16
expanded reports zero: true
factored is positive: true
exp(delta)-1=1.000089e-12
expm1(delta)=1.000000e-12
log(1+delta)=1.000089e-12
log1p(delta)=1.000000e-12
```

**Ý nghĩa:** Nếu một oracle chỉ dùng chính biểu thức khai triển, nó có thể tái hiện cùng lỗi và không phát hiện hội tụ giả. Dùng hai biểu thức có cấu trúc số học khác nhau giúp chẩn đoán vấn đề.

## 10. Dừng do floating-point stagnation

`double` là định dạng hữu hạn. Tại1:

`Math.ulp(1.0)=2.220446049250313e-16`.

Vì thế:

`1.0+1e-20==1.0`

là true. Bước thực khác0 nhưng máy không biểu diễn được giá trị mới.

Nếu solver viết:

```text
if (newX == oldX) return CONVERGED
```

thì có thể gọi một số chưa phải nghiệm là “đã hội tụ”. Trạng thái đúng thường là `STAGNATED` nếu chưa đạt chặn sai số hợp lệ.

### 10.1. ULP là gì?

**ULP** (*unit in the last place*) mô tả khoảng cách giữa các giá trị floating có thể biểu diễn gần x. Khi x lớn hơn, khoảng cách thường lớn hơn.

`Double.MIN_VALUE` **không phải epsilon máy tại1**; nó là số subnormal dương nhỏ nhất. Dùng `Math.ulp(x)` hoặc `Math.nextUp(x)` khi muốn xem giới hạn độ phân giải gần x.

### 10.2. Khi bước bằng0 mà residual vẫn khác0

Ví dụ cần giải x−2=0, nhưng x=1 được cập nhật bằng một bước chỉ10^-20. Double trả lại x=1, residual vẫn bằng1. Kiểm `step==0` sẽ gắn success sai. Phải kiểm **residual và step** cùng nhau, và phân biệt thiếu tiến triển với đáp ứng mục tiêu.

### 10.3. Dừng đúng không chỉ là tolerance

Một thuật toán còn phải biết khi nào trả:

- `NONFINITE`: NaN/Infinity, miền hàm sai.
- `SAME_SIGN`: không có bracket đổi dấu, không suy vô nghiệm.
- `STAGNATED`: máy không còn giá trị mới.
- `MAX_ITER`: hết số vòng cho phép.
- `WRONG_BRANCH`: x ngoài miền ứng dụng.
- `BRACKET_WIDTH`: có chặn độ rộng đạt ngưỡng, với giả thiết đúng.
- `HEURISTIC_CONVERGED`: step và residual đạt tiêu chí, **chưa được chứng nhận sai số x**.

## 11. Tại sao bracket có giá trị hơn residual-only?

Nếu f **liên tục** trên [a,b] và `f(a),f(b)` trái dấu, định lý giá trị trung gian bảo đảm ít nhất một nghiệm bên trong. Chia đôi đoạn và giữ nửa có đổi dấu, ta luôn duy trì bracket có nghiệm **trong số học thực**.

Với midpoint m và một nghiệm x* trong [a,b]:

`|m−x*|≤(b−a)/2`.

Đây là **chặn sai số theo x** dựa vào bracket, không cần suy từ residual của một hàm có thể rất phẳng.

### 11.1. Số bước chia đôi

Độ rộng ban đầu L0. Sau k lần chia đôi lý tưởng:

`L_k=L0/2^k`.

Muốn sai số midpoint ≤ε:

`L_k/2≤ε`

⇒ `k≥ceil(log2(L0/(2ε)))` khi L0>2ε.

Ví dụ f(x)=x²−3 trên [1,2], chọn ε=10^-13. Sau **43 vòng** bisection double demo đạt nửa độ rộng≤10^-13.

### 11.2. Bracket phải thỏa tính liên tục

Phản ví dụ:

`f(x)=1/(x−1)` trên [0,2].

f(0)=-1, f(2)=1, trái dấu nhưng **không có nghiệm** vì f không xác định tại1. Midpoint1 cho Infinity. Thuật toán đúng trả `NONFINITE`, không coi đây là root.

### 11.3. SAME_SIGN không có nghĩa vô nghiệm

f(x)=(x−1)² trên [0,2] có nghiệm1 nhưng hai đầu cùng dương. Bisection chuẩn từ chối vì thiếu **chứng nhận đổi dấu**; nó không được xuất một phán quyết không có nghiệm.

### 11.4. Midpoint kề nhau

Khi a và b là hai double kế tiếp nhau, `a+(b−a)/2` có thể làm tròn thành chính a hoặc b. Nếu bracket chưa đạt tolerance, phải trả `STAGNATED` hoặc chuyển precision; không lặp vô hạn.

### 11.5. Lưu ý về chứng nhận trong máy

Giới hạn midpoint từ bracket là **một định lý toán học** nếu f liên tục và dấu endpoint đúng. Nếu đánh giá f bằng double bị sai dấu, “bracket” lưu trên máy có thể không còn chứa nghiệm. Để chứng nhận nghiêm ngặt cần đánh giá dấu có sai số được khống chế, ví dụ interval arithmetic hướng làm tròn.

## 12. Java 17 — bisection với nhiều trạng thái dừng

Lưu **ResidualBracketValidationDemo.java**:

```java
import java.util.Locale;
import java.util.function.DoubleUnaryOperator;

public class ResidualBracketValidationDemo {
    enum Status {
        BRACKET_WIDTH, FLOATING_ZERO, SAME_SIGN,
        NONFINITE, STAGNATED, MAX_ITER
    }

    record Result(Status status, double x, double a, double b,
                  int iterations, double residual) {
        double halfWidth() {
            return (b - a) / 2.0;
        }
    }

    static Result solve(DoubleUnaryOperator f, double a, double b,
                        double tolerance, int maxIter) {
        if (!Double.isFinite(a) || !Double.isFinite(b)
                || !(a < b) || !Double.isFinite(b - a)
                || !Double.isFinite(tolerance) || tolerance <= 0
                || maxIter <= 0) {
            throw new IllegalArgumentException("Invalid parameters");
        }

        double fa = f.applyAsDouble(a);
        double fb = f.applyAsDouble(b);
        if (!Double.isFinite(fa) || !Double.isFinite(fb)) {
            return new Result(Status.NONFINITE, Double.NaN,
                              a, b, 0, Double.NaN);
        }
        if (fa == 0.0) {
            return new Result(Status.FLOATING_ZERO, a, a, a, 0, 0);
        }
        if (fb == 0.0) {
            return new Result(Status.FLOATING_ZERO, b, b, b, 0, 0);
        }
        if ((fa > 0) == (fb > 0)) {
            return new Result(Status.SAME_SIGN, Double.NaN,
                              a, b, 0, Double.NaN);
        }

        for (int i = 1; i <= maxIter; i++) {
            double mid = a + (b - a) / 2.0;
            if (mid == a || mid == b) {
                return new Result(Status.STAGNATED, mid,
                                  a, b, i, Math.abs(f.applyAsDouble(mid)));
            }
            double fm = f.applyAsDouble(mid);
            if (!Double.isFinite(fm)) {
                return new Result(Status.NONFINITE, mid,
                                  a, b, i, Double.NaN);
            }
            if (fm == 0.0) {
                return new Result(Status.FLOATING_ZERO, mid,
                                  mid, mid, i, 0.0);
            }
            if ((fa > 0) == (fm > 0)) {
                a = mid;
                fa = fm;
            } else {
                b = mid;
                fb = fm;
            }

            if ((b - a) / 2.0 <= tolerance) {
                double root = a + (b - a) / 2.0;
                return new Result(Status.BRACKET_WIDTH, root,
                        a, b, i, Math.abs(f.applyAsDouble(root)));
            }
        }
        double root = a + (b - a) / 2.0;
        return new Result(Status.MAX_ITER, root,
                a, b, maxIter, Math.abs(f.applyAsDouble(root)));
    }

    public static void main(String[] args) {
        DoubleUnaryOperator square = x -> x * x - 3.0;
        Result good = solve(square, 1.0, 2.0, 1e-13, 200);
        System.out.printf(Locale.ROOT,
                "sqrt3 estimate=%.12f%n", good.x());
        System.out.println("sqrt3 status=" + good.status());
        System.out.println("sqrt3 iterations=" + good.iterations());
        System.out.println("sqrt3 halfWidth pass="
                + (good.halfWidth() <= 1e-13));
        System.out.println("sqrt3 residual pass="
                + (good.residual() <= 1e-11));

        Result jump = solve(x -> 1.0 / (x - 1.0),
                            0.0, 2.0, 1e-13, 200);
        System.out.println("discontinuity status=" + jump.status());

        Result even = solve(x -> (x - 1.0) * (x - 1.0),
                            0.0, 2.0, 1e-13, 200);
        System.out.println("even root bracket status=" + even.status());

        double next = Math.nextUp(1.0);
        double halfUlp = Math.ulp(1.0) / 2.0;
        Result tiny = solve(x -> (x - 1.0) - halfUlp,
                            1.0, next, 1e-20, 200);
        System.out.println("adjacent doubles status=" + tiny.status());

        Result budget = solve(square, 1.0, 2.0, 1e-13, 2);
        System.out.println("short budget status=" + budget.status());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ResidualBracketValidationDemo.java
java ResidualBracketValidationDemo
```

Stdout:

```text
sqrt3 estimate=1.732050807569
sqrt3 status=BRACKET_WIDTH
sqrt3 iterations=43
sqrt3 halfWidth pass=true
sqrt3 residual pass=true
discontinuity status=NONFINITE
even root bracket status=SAME_SIGN
adjacent doubles status=STAGNATED
short budget status=MAX_ITER
```

**Chú ý:** `FLOATING_ZERO` chỉ bảo đảm phép **đánh giá double** bằng0, không phải chứng minh f toán học bằng0. `BRACKET_WIDTH` có ý nghĩa chặn error dưới **giả thiết f liên tục và dấu bracket đáng tin**.

## 13. Newton có thể lặp mãi mà không đi đến nghiệm

Newton cập nhật:

`xNew=x−f(x)/f'(x)`.

Gần nghiệm đơn đủ trơn với seed tốt, tốc độ rất nhanh. Nhưng:

- Nếu f'=0, không thể chia.
- Nếu f' gần0, bước có thể rất lớn và ra ngoài miền.
- Nếu phương trình có nhiều nghiệm, seed có thể đưa tới sai nhánh.
- Nếu làm tròn khiến xNew==x, chưa có chứng minh đúng nghiệm.
- Nếu xuất hiện chu kỳ, số vòng tăng mà error không giảm.

### 13.1. Chu kỳ 0↔1

Xét:

`f(x)=x³−2x+2`, `f'(x)=3x²−2`.

Từ x0=0:

`f(0)=2`, f'(0)=-2 ⇒ x1=1.

Từ x1=1:

`f(1)=1`, f'(1)=1 ⇒ x2=0.

Dãy đi `0→1→0→1...`. Nếu chỉ kiểm maxIter rồi gắn nhãn `CONVERGED`, đó là báo cáo sai.

### 13.2. Safeguard bằng bracket

Nếu có bracket [a,b] đổi dấu hợp lệ, một biến thể an toàn:

1. Tính fx, kiểm hữu hạn.
2. Dùng dấu fx để **cập nhật bracket**.
3. Tính bước Newton nếu đạo hàm hữu hạn và khác0.
4. Nếu bước ra ngoài bracket, không hữu hạn hoặc không đổi x, chọn **midpoint**.
5. Nếu không còn ứng viên double khác hai đầu, trả `STAGNATED`.
6. Thành công thực dụng chỉ khi **cả residual và step** đạt ngưỡng hợp lý.
7. Nếu width bracket đủ nhỏ, có thể trả `BRACKET_WIDTH` với điều kiện bảo toàn nghiệm như bisection.

Dùng `residualOK && stepOK` an toàn hơn `residualOK || stepOK` cho một kiểm tra heuristic, nhưng **vẫn không tự chứng minh** forward error nhỏ khi f kém điều kiện.

### 13.3. Ngưỡng phải phù hợp thang đo

Một kiểm tra bước minh họa cho x không thứ nguyên:

`stepLimit=absXTol+relXTol·max(1,|x|)`.

Đây không phải quy tắc bắt buộc cho mọi đại lượng có đơn vị. Tol của f phải được thiết kế riêng theo **đơn vị f** và độ lớn residual tham chiếu.

## 14. Java 17 — Newton dao động và Newton có bảo vệ

Chương trình sau so hai thuật toán: Newton thuần từ x0=0 của f=x³−2x+2 tạo chu kỳ; safeguarded Newton tìm nghiệm thực của x³−x−1 trong [0,2] và buộc một lần fallback đầu tiên vì bước Newton x0=0 đưa tới -1, ra ngoài bracket.

Lưu **GuardedNewtonDiagnosticsDemo.java**:

```java
import java.util.Locale;
import java.util.function.DoubleUnaryOperator;

public class GuardedNewtonDiagnosticsDemo {
    enum Status {
        HEURISTIC_CONVERGED, FLOATING_ZERO, BRACKET_WIDTH,
        STAGNATED, MAX_ITER, NONFINITE
    }

    record Result(Status status, double x, double residual,
                  int iterations, int fallbacks) {}

    static Result solve(DoubleUnaryOperator f,
                        DoubleUnaryOperator derivative,
                        double a, double b, double x,
                        double absXTol, double relXTol, double fTol,
                        int maxIter) {
        if (!Double.isFinite(a) || !Double.isFinite(b)
                || !(a < b) || !Double.isFinite(b - a)
                || !Double.isFinite(x) || x < a || x > b
                || !Double.isFinite(absXTol) || absXTol <= 0
                || !Double.isFinite(relXTol) || relXTol < 0
                || !Double.isFinite(fTol) || fTol < 0
                || maxIter <= 0) {
            throw new IllegalArgumentException("Invalid parameters");
        }

        double fa = f.applyAsDouble(a);
        double fb = f.applyAsDouble(b);
        if (!Double.isFinite(fa) || !Double.isFinite(fb)
                || fa == 0.0 || fb == 0.0
                || ((fa > 0) == (fb > 0))) {
            throw new IllegalArgumentException("Need sign bracket");
        }

        int fallbacks = 0;
        for (int i = 1; i <= maxIter; i++) {
            double fx = f.applyAsDouble(x);
            if (!Double.isFinite(fx)) {
                return new Result(Status.NONFINITE, x, Double.NaN,
                                  i, fallbacks);
            }
            if (fx == 0.0) {
                return new Result(Status.FLOATING_ZERO, x, 0.0,
                                  i, fallbacks);
            }

            if ((fa > 0) == (fx > 0)) {
                a = x;
                fa = fx;
            } else {
                b = x;
                fb = fx;
            }

            double df = derivative.applyAsDouble(x);
            double candidate = Double.NaN;
            if (Double.isFinite(df) && df != 0.0) {
                candidate = x - fx / df;
            }
            if (!Double.isFinite(candidate)
                    || candidate <= a || candidate >= b
                    || candidate == x) {
                candidate = a + (b - a) / 2.0;
                fallbacks++;
            }
            if (candidate == a || candidate == b || candidate == x) {
                return new Result(Status.STAGNATED, x, Math.abs(fx),
                                  i, fallbacks);
            }

            double step = Math.abs(candidate - x);
            x = candidate;
            double newF = f.applyAsDouble(x);
            if (!Double.isFinite(newF)) {
                return new Result(Status.NONFINITE, x, Double.NaN,
                                  i, fallbacks);
            }

            double stepLimit = absXTol
                    + relXTol * Math.max(1.0, Math.abs(x));
            if (Math.abs(newF) <= fTol && step <= stepLimit) {
                return new Result(Status.HEURISTIC_CONVERGED, x,
                        Math.abs(newF), i, fallbacks);
            }
            if ((b - a) / 2.0 <= stepLimit) {
                double mid = a + (b - a) / 2.0;
                return new Result(Status.BRACKET_WIDTH, mid,
                        Math.abs(f.applyAsDouble(mid)), i, fallbacks);
            }
        }
        return new Result(Status.MAX_ITER, x,
                Math.abs(f.applyAsDouble(x)), maxIter, fallbacks);
    }

    public static void main(String[] args) {
        DoubleUnaryOperator badF = x -> x*x*x - 2.0*x + 2.0;
        DoubleUnaryOperator badDf = x -> 3.0*x*x - 2.0;
        double x0 = 0.0;
        double x1 = x0 - badF.applyAsDouble(x0)
                              / badDf.applyAsDouble(x0);
        double x2 = x1 - badF.applyAsDouble(x1)
                              / badDf.applyAsDouble(x1);
        System.out.printf(Locale.ROOT,
                "naive cycle: %.1f -> %.1f -> %.1f%n",
                x0, x1, x2);

        DoubleUnaryOperator f = x -> x*x*x - x - 1.0;
        DoubleUnaryOperator df = x -> 3.0*x*x - 1.0;
        Result result = solve(f, df, 0.0, 2.0, 0.0,
                              1e-12, 1e-12, 1e-12, 100);

        System.out.printf(Locale.ROOT,
                "guarded root=%.12f%n", result.x());
        System.out.println("guarded status=" + result.status());
        System.out.println("guarded iterations=" + result.iterations());
        System.out.println("guarded fallbacks=" + result.fallbacks());
        System.out.println("guarded residual pass="
                + (result.residual() <= 1e-12));

        double stopped = 1.0 + 1e-20;
        System.out.println("floating step stopped="
                + (stopped == 1.0));
        System.out.println("nonzero residual at 1 for x-2="
                + (Math.abs(1.0 - 2.0) == 1.0));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 GuardedNewtonDiagnosticsDemo.java
java GuardedNewtonDiagnosticsDemo
```

Stdout:

```text
naive cycle: 0.0 -> 1.0 -> 0.0
guarded root=1.324717957245
guarded status=HEURISTIC_CONVERGED
guarded iterations=7
guarded fallbacks=1
guarded residual pass=true
floating step stopped=true
nonzero residual at 1 for x-2=true
```

**Quan trọng:** `HEURISTIC_CONVERGED` báo tiêu chí thực dụng; không có nghĩa đã chứng nhận nghiệm đúng 12 chữ số. Với các seed khác, solver có thể trả `BRACKET_WIDTH`, `FLOATING_ZERO` hoặc `STAGNATED` khi gần nghiệm. **STAGNATED không phải PASS** trừ khi có một phép kiểm error độc lập thỏa yêu cầu.

## 15. Secant, lặp điểm bất động và hệ giải lặp

### 15.1. Secant

Secant không cần đạo hàm phân tích:

`x(k+1)=x_k−f(x_k)(x_k−x(k−1))/(f(x_k)−f(x(k−1)))`.

Nếu mẫu nhỏ do hai giá trị f gần nhau, bước có thể vô hạn/lớn. Phải kiểm hữu hạn, miền hợp lệ, residual và tiến triển. Secant không bảo toàn bracket nếu không bổ sung safeguard.

### 15.2. Fixed point

Với `x_new=g(x_old)`, bước nhỏ chỉ là bằng chứng về error nếu **có giả thiết đặc biệt**. Ví dụ, nếu g co trên một đoạn bất biến I với hằng số `q<1`, thì trong số học thực:

`|x_n−x*|≤q/(1−q)·|x_n−x(n−1)|`.

Nếu q≥1, I không bất biến, hoặc bước bằng0 do làm tròn, không được dùng bound này để chứng nhận error.

### 15.3. Jacobi/Gauss–Seidel và hệ tuyến tính

Các phương pháp giải lặp Ax=b có thể có iterate changes nhỏ nhưng residual chưa đạt; hoặc residual nhỏ ở hệ kém điều kiện mà error vẫn lớn. Ngoài chuẩn bước, phải đo `||b−Ax̂||`, điều kiện và mục tiêu tiền xử lý (*preconditioning*) theo bài toán.

### 15.4. Iterative refinement

Có thể giải thêm một hệ `AΔx=r` để hiệu chỉnh x̂. Hiệu quả phụ thuộc κ(A), quality của phép giải và residual, thường tính residual ở precision cao hơn. **Không** khẳng định refinement luôn cứu được một hệ gần suy biến.

## 16. Cách chọn điều kiện dừng đúng thang đo

Một cấu trúc phổ biến là:

`stepOK: |xNew−xOld|≤absXTol+relXTol·scaleX`;

`residualOK: |fHat(xNew)|≤absFTol+relFTol·scaleF`.

Các scale phải có ý nghĩa:

- `scaleX` có đơn vị của x; trong ví dụ không thứ nguyên thường `max(1,|x|)`.
- `scaleF` có đơn vị của f; có thể lấy quy mô từ dữ liệu đầu vào, nghiệm dự kiến hoặc chuẩn của hệ.
- Nếu nghiệm gần0, cần `absXTol` vì relative-only trở nên vô nghĩa.
- Nếu f được nhân hệ số, `fTol` cần điều chỉnh tương ứng khi muốn quy tắc bất biến theo scale.
- Nếu mô hình đo đạc có noise, tăng số vòng không tự tạo thêm độ chính xác dữ liệu.

**Điều kiện OR là nguy hiểm:** `stepOK || residualOK` chấp nhận false convergence nếu chỉ một đại lượng đánh lừa. Dùng AND phù hợp hơn cho **heuristic**; nhưng nếu f rất phẳng, cả step và residual nhỏ vẫn chưa chắc error x nhỏ, nên phải kiểm conditioning/interval khi cần.

## 17. Cây quyết định chẩn đoán một kết quả đáng ngờ

```text
Có nghiệm đích/miền hợp lệ chưa?
  Không -> xác định nhánh, kiểm domain trước
  Có   -> xHat nằm trong miền không?
             Không -> WRONG_BRANCH
             Có   -> fHat(xHat) hữu hạn không?
                        Không -> NONFINITE
                        Có   -> residual có ổn định/được scale đúng không?
                                   Không -> UNRELIABLE_RESIDUAL
                                   Có   -> có bound error được chứng minh?
                                              Có và bound<=tolX -> CERTIFIED
                                              Không -> kiểm condition, step, residual
                                                        Cả hai đạt -> HEURISTIC
                                                        Step không đổi -> STAGNATED
                                                        Quá budget -> MAX_ITER
```

Đây là cấu trúc **chẩn đoán**, không phải một chương trình giải tổng quát. Tùy thuật toán, `SAME_SIGN`, `DIVERGED`, `INVALID_DOMAIN` cũng cần trạng thái riêng.

### 17.1. Status trả về nên có dữ liệu gì?

`Result {estimate, status, residual, step, iterations, bracket, errorBound, conditionEstimate, evaluations}`.

Không cần mọi trường trong mọi thuật toán, nhưng người dùng nên biết **nguyên nhân** dừng. Một số `double` không kèm status không phân biệt thành công với hết ngân sách.

### 17.2. Phân biệt chứng nhận và kiểm thử

Kiểm thử 5.000 case có nghiệm chuẩn giúp bắt lỗi triển khai, **không chứng minh** phương pháp luôn hội tụ trên tất cả input. Với f gián đoạn hoặc dữ liệu đối kháng, giả thiết toán học có thể không tồn tại.

## 18. Oracle độc lập và phép kiểm biến hình

### 18.1. Phương trình có nghiệm biết trước

Sinh:

`f(x)=s(x−r)` với s khác0.

Nghiệm đúng là r. Dùng bracket `[r−3,r+2]`, kiểm solver giữ bracket chứa r và midpoint gần r trong giới hạn halfWidth. Sinh cả s dương, âm và nhiều độ lớn.

### 18.2. Căn bình phương

Sinh A>0, f(x)=x²−A. Oracle double là `Math.sqrt(A)`. Nếu dùng bracket `[0,high]` với high lớn hơn √A và f liên tục, bisection phải thu hẹp tới nghiệm dương.

### 18.3. Hàm mũ và log

Sinh `T=exp(r)`, giải `exp(x)−T=0`, so nghiệm với `log(T)`. Gần T≈1 nên dùng `expm1/log1p` nếu muốn giảm cancellation.

### 18.4. Kiểm solver Newton

Chọn f=x³−x−1 với nghiệm thực ≈1.324717957244746. Dùng nhiều seed trong [0,2] nhưng **không bắt mọi seed phải trả cùng một trạng thái**. Một vài seed có thể `STAGNATED` sát nghiệm vì giới hạn double; vẫn phải gắn nhãn đúng, kiểm x và residual theo oracle độc lập để chẩn đoán. Không biến `STAGNATED` thành `HEURISTIC_CONVERGED`.

### 18.5. Kiểm biến đổi scale

Nhân f với c≠0 không làm đổi nghiệm. Nếu đổi c làm kết luận từ residual-only đảo ngược, cần xem lại việc chọn tolF. Với phương trình tuyến tính, kiểm scale từng hàng và normwise backward error.

### 18.6. Kiểm hai cách tính residual

Với p(x)=(x−1)², so:

- `(x−1)*(x−1)`;
- `x*x−2*x+1`.

Nếu hai kết quả lệch tương đối lớn, cảnh báo cancellation. Có thể bổ sung BigDecimal/interval với dữ liệu đầu vào được bảo toàn chính xác.

## 19. Bảng trường hợp biên

| Tình huống | Diễn giải cần đúng |
|---|---|
| f=10^-15(x−10^6), x̂=0 | Residual nhỏ, error rất lớn |
| f=10^12(x−1), x̂≈1+10^-9 | Residual lớn, error có thể nhỏ |
| f=(x−1)² gần1 | Residual bậc hai, error bậc một |
| f=(x−1)² trên [0,2] | SAME_SIGN nhưng tồn tại nghiệm |
| f=(x−2)(x−5) | Hai nghiệm, phải chọn đúng nhánh |
| p=x²−2x+1 gần1 | Dạng khai triển có thể trả0 giả |
| exp(x)−1, log(1+x) với x rất nhỏ | Dùng expm1/log1p |
| A=diag(1,10^-12), x̂=(1,1000) | Residual≈10^-9, error999 |
| κ(A)≈10^12 | Backward error nhỏ không đủ xác nhận forward error |
| 1+1e-20 trong double | Không đổi dù có bước toán học |
| Hai double kề nhau có root thực ở giữa | STAGNATED, không tự chứng nhận |
| f=1/(x−1) trên [0,2] | Đổi dấu nhưng gián đoạn, không có root |
| f=x²−3 trên [1,2] | Bisection có bound theo bracket |
| Newton x³−2x+2 seed0 | Chu kỳ 0↔1 |
| Newton đạo hàm0 | Không chia; fallback |
| f/df trả NaN/Infinity | NONFINITE hoặc invalid-domain |
| maxIter rất nhỏ | MAX_ITER |
| Nghiệm gần0 | Không dùng relative-only |
| Noise của dữ liệu lớn | Residual cực nhỏ không tăng độ chính xác vật lý |

## 20. Những lỗi dễ gây hội tụ giả

### Lỗi 1 — Chỉ nhìn residual nhỏ

Hàm phẳng có thể cho residual10^-9 khi error x=10^6.

### Lỗi 2 — Chỉ nhìn bước nhỏ

Bước có thể nhỏ vì làm tròn hoặc bị clamp.

### Lỗi 3 — Dùng residualOK OR stepOK

Một trong hai phép kiểm sai vẫn khiến status thành công.

### Lỗi 4 — Gọi fHat(x)==0 là root toán học

Kết quả floating có thể bằng0 do cancellation.

### Lỗi 5 — Không kiểm nghiệm bội

Residual giảm nhanh hơn error; derivative tại nghiệm có thể bằng0.

### Lỗi 6 — Không kiểm đúng nhánh

Nghiệm khác vẫn cho residual0 nhưng có thể ngoài miền yêu cầu.

### Lỗi 7 — Dùng ngưỡng fTol tuyệt đối cho mọi scale

Nhân f với hệ số không đổi nghiệm nhưng làm đổi residual.

### Lỗi 8 — Dùng derivative tại một điểm làm chặn toàn đoạn

Bound error cần giả thiết `|f'|≥m>0` trên đoạn liên quan.

### Lỗi 9 — Không kiểm độ điều kiện κ(A)

Hệ κ lớn có thể có residual nhỏ và nghiệm sai lớn.

### Lỗi 10 — Coi backward η nhỏ là forward error nhỏ

Hai khái niệm khác nhau khi input nhạy.

### Lỗi 11 — Bình phương κ bằng normal equations mà không cân nhắc

Least squares kém điều kiện nên xem xét QR/SVD.

### Lỗi 12 — Đánh giá r=b−Ax bằng precision không đủ

Sai số residual cũng cần kiểm khi các thành phần lớn triệt tiêu.

### Lỗi 13 — Chỉ dùng đúng một cách tính f trong test

Một oracle dùng chung công thức cancellation có thể bỏ lọt lỗi.

### Lỗi 14 — Cho rằng Horner sửa mọi triệt tiêu

Không đúng gần nghiệm bội và dữ liệu gần suy biến.

### Lỗi 15 — Không dùng expm1/log1p khi thích hợp

Có thể mất chữ số có nghĩa gần0.

### Lỗi 16 — Quên kiểm NaN/Infinity

Các phép so với NaN thường cho false, làm bỏ qua kiểm dừng.

### Lỗi 17 — Xem Double.MIN_VALUE là epsilon tại1

Sai; dùng `Math.ulp(1.0)` để hiểu bước biểu diễn.

### Lỗi 18 — Vẫn lặp khi newX==oldX

Nếu chưa đạt bound, phải STAGNATED thay vì lặp vô hạn.

### Lỗi 19 — Kết luận đổi dấu luôn có nghiệm

Thiếu giả thiết liên tục, ví dụ 1/(x−1).

### Lỗi 20 — Kết luận không đổi dấu là vô nghiệm

Nghiệm bội chẵn có thể không đổi dấu.

### Lỗi 21 — Quên xét f(a)==0 hoặc f(b)==0

Nghiệm có thể nằm ở đầu mút theo phép đánh giá.

### Lỗi 22 — Midpoint `(a+b)/2` có thể overflow

Với b-a hữu hạn, dùng `a+(b-a)/2`; input cực trị cần guard riêng.

### Lỗi 23 — Nhân f(a)*f(b) để kiểm đổi dấu

Có thể overflow/underflow; so dấu sau khi kiểm hữu hạn.

### Lỗi 24 — Chia Newton cho derivative0

Phải fallback hoặc báo lỗi.

### Lỗi 25 — Bỏ qua chu kỳ Newton

f=x³−2x+2, seed0 tạo 0→1→0.

### Lỗi 26 — Hết maxIter nhưng vẫn trả CONVERGED

Trạng thái phải là MAX_ITER nếu chưa đạt tiêu chí phù hợp.

### Lỗi 27 — Chia relative error cho x*=0

Định nghĩa không hợp lệ, cần absolute tolerance.

### Lỗi 28 — Chọn aTol nhỏ hơn khả năng biểu diễn double

Có thể stagnate ở precision hiện tại.

### Lỗi 29 — Không tách noise dữ liệu và error thuật toán

Không thể dùng nhiều vòng hơn để tạo thông tin chính xác hơn dữ liệu.

### Lỗi 30 — In nhiều chữ số rồi coi là error bound

Format output khác với chứng minh sai số.

### Lỗi 31 — Không trả status

Một số x không cho biết solver đã chứng nhận, heuristic hay thất bại.

### Lỗi 32 — Không kiểm bước Newton có nằm trong miền

Bước ngoài miền có thể sang nghiệm khác hoặc làm f không xác định.

### Lỗi 33 — Nhầm test ngẫu nhiên với chứng minh tất cả input

Test chỉ xác nhận các case đã chạy và bất biến triển khai.

### Lỗi 34 — Chuyển dữ liệu đã mất bit sang BigDecimal rồi nghĩ đã phục hồi

Phải lưu dữ liệu gốc đúng precision từ đầu.

### Lỗi 35 — Không kiểm ổn định của residual tính lại

Có thể đánh giá sai ở cả bước giải lẫn bước hậu kiểm.

### Lỗi 36 — Quên giới hạn tài nguyên và xử lý lỗi rõ

Cần maxIterations/evaluations/time/precision và thông điệp chính xác.

## 21. Bài tập có đáp án

### Bài 1 — Sai số tiến

x*=100, x̂=100.01, forward error?

**Đáp án:** 0.01.

### Bài 2 — Sai số tương đối

Cùng bài1, relative error?

**Đáp án:** 0.01/100=10^-4.

### Bài 3 — Nghiệm0

Relative error `|x̂−x*|/|x*|` có nghĩa khi x*=0 không?

**Đáp án:** Không; chia0.

### Bài 4 — Hàm phẳng

`f=10^-15(x−10^6)`, x̂=0, residual?

**Đáp án:** 10^-9.

### Bài 5 — Error hàm phẳng

Cùng bài4, error x?

**Đáp án:** 10^6.

### Bài 6 — Hệ số scale

Nhân f với10^9 có đổi nghiệm không?

**Đáp án:** Không (với hệ số khác0), nhưng residual nhân10^9.

### Bài 7 — Chặn đạo hàm

|f'|≥2 trên đoạn chứa x̂,x*, residual≤10^-6, error≤?

**Đáp án:** 5×10^-7.

### Bài 8 — Nghiệm bội

f=(x−1)², x̂=1.001, residual xấp xỉ?

**Đáp án:** 10^-6.

### Bài 9 — Error nghiệm bội

Cùng bài8, error x?

**Đáp án:** 10^-3.

### Bài 10 — Derivative nghiệm bội

f'(1) của (x−1)²?

**Đáp án:** 0.

### Bài 11 — Bracket nghiệm bội

f=(x−1)² có đổi dấu trên [0,2] không?

**Đáp án:** Không, dù tồn tại nghiệm1.

### Bài 12 — Số điều kiện ma trận

A=diag(1,10^-12), κ∞?

**Đáp án:** 10^12.

### Bài 13 — Residual hệ

A ở bài12, x̂=(1,1000), b=(1,10^-12), ||r||∞?

**Đáp án:** 9.99×10^-10.

### Bài 14 — Error hệ

Nghiệm đúng (1,1), x̂=(1,1000), error infinity?

**Đáp án:** 999.

### Bài 15 — Backward eta

`||r||=9.99e-10, ||A||=1, ||x̂||=1000, ||b||=1`, eta?

**Đáp án:** khoảng9.980×10^-13.

### Bài 16 — Backward accuracy đủ chưa?

η≈10^-12, κ≈10^12 có bảo đảm forward error nhỏ?

**Đáp án:** Không.

### Bài 17 — Cancellation

p=(x−1)² nên đánh giá gần x=1 theo dạng nào?

**Đáp án:** dạng nhân tử có thể ổn định hơn x²−2x+1.

### Bài 18 — exp gần0

Dùng hàm nào cho exp(x)−1 gần0?

**Đáp án:** `Math.expm1(x)`.

### Bài 19 — log gần0

Dùng hàm nào cho log(1+x) gần0?

**Đáp án:** `Math.log1p(x)`.

### Bài 20 — ULP

`Math.ulp(1.0)` khoảng bao nhiêu?

**Đáp án:** 2.220446049250313×10^-16.

### Bài 21 — Stagnation

`1.0+1e-20==1.0` là true hay false trong double?

**Đáp án:** true, không chứng minh đã đạt nghiệm.

### Bài 22 — IVT

Đổi dấu có đảm bảo nghiệm nếu hàm không liên tục không?

**Đáp án:** Không.

### Bài 23 — Đổi dấu qua gián đoạn

`1/(x−1)` có nghiệm trong [0,2] không?

**Đáp án:** Không, dù endpoint trái dấu.

### Bài 24 — Bracket bound

Khoảng dài 2×10^-5, midpoint error bound?

**Đáp án:** 10^-5 tới một nghiệm được giữ trong bracket.

### Bài 25 — Newton cycle

f=x³−2x+2, seed0, hai bước tiếp?

**Đáp án:** 1 rồi0.

### Bài 26 — Derivative0

Newton có thể chia f/f' khi f'=0 không?

**Đáp án:** Không; cần fallback/return failure.

### Bài 27 — AND/OR

Tại sao dùng `residualOK || stepOK` nguy hiểm?

**Đáp án:** chỉ một phép kiểm lỏng có thể báo success giả.

### Bài 28 — MAX_ITER

Hết số vòng mà không đạt bound, trả status gì?

**Đáp án:** MAX_ITER.

### Bài 29 — Sai nhánh

f=(x−2)(x−5), miền cần [4,6]; nhận x≈2 vì residual0?

**Đáp án:** Không; phải chọn nghiệm5.

### Bài 30 — Độ chính xác mô hình

Dữ liệu chỉ đáng tin tới0.01, residual10^-15 có tăng độ chính xác vật lý?

**Đáp án:** Không.

### Bài 31 — Precision

BigDecimal nhận một double đã sai có khôi phục dữ liệu ban đầu không?

**Đáp án:** Không, cần đầu vào chính xác từ đầu.

### Bài 32 — Kết quả STAGNATED gần nghiệm

Có nên tự đổi status STAGNATED thành CONVERGED vì x gần oracle trong một test không?

**Đáp án:** Không; test chỉ xác nhận sai số trên case đó, status vẫn phản ánh lý do dừng của solver.

## 22. Checklist chẩn đoán

1. Đã xác định nghiệm/nhánh ứng dụng cần?
2. Đã kiểm miền xác định?
3. Đã phân biệt forward error, residual, backward error?
4. Nếu nghiệm gần0, đã chọn absolute tolerance?
5. Residual có được scale đúng đơn vị không?
6. Đã đánh giá f bằng công thức ổn định chưa?
7. Đã kiểm cancellation/underflow/overflow?
8. Đã thử residual bằng biểu thức độc lập?
9. Có xem đạo hàm/độ nhạy gần nghiệm?
10. Bound |f|/m có giả thiết |f'|≥m trên cả đoạn?
11. Có kiểm nghiệm bội với derivative0?
12. Có kiểm đúng nhánh khi đa nghiệm?
13. Có chặn `step` và `residual` **đồng thời**?
14. Có phân biệt heuristic và chứng nhận toán học?
15. Có kiểm `Math.ulp(x)` khi tolerance rất nhỏ?
16. Nếu newX==oldX, có báo STAGNATED khi chưa đủ bound?
17. Có kiểm NaN/Infinity?
18. Có giới hạn maxIter, số lần gọi f và thời gian?
19. Bisection có kiểm liên tục/đổi dấu?
20. SAME_SIGN có được hiểu chỉ là không có bracket?
21. Bisection có kiểm f tại midpoint hữu hạn?
22. Khi midpoint kề endpoint, có dừng rõ ràng?
23. Có lưu bracket và halfWidth?
24. Newton có chặn bước ngoài miền và derivative0?
25. Có kiểm chu kỳ 0→1→0?
26. Với hệ Ax=b, có tính `||r||` và backward eta?
27. Có ước lượng κ(A) để hiểu error?
28. Có tránh hứa forward accuracy chỉ từ residual nhỏ?
29. Có xem lại precision dùng để tính residual hệ?
30. Có so với oracle nghiệm biết trước?
31. Có thử nghiệm đa thức khai triển vs nhân tử?
32. Có thử expm1/log1p gần0?
33. Có thử sign bracket ở hàm gián đoạn?
34. Có thử ngưỡng quá chặt, maxIter nhỏ và double liền kề?
35. Có báo status và lý do không hội tụ?
36. Có xem giới hạn noise dữ liệu/mô hình trước khi hứa chữ số?

**Kết luận:** Một kết quả số “có vẻ hội tụ” chỉ đáng tin khi **nhánh nghiệm hợp lệ, residual được tính ổn định và đúng scale, độ nhạy được kiểm tra, trạng thái dừng được hiểu đúng**, và — nếu ứng dụng đòi hỏi — có **chặn sai số nghiệm**. Residual nhỏ, backward error nhỏ, hoặc `xNew==xOld` **đều chưa đủ** để kết luận forward error nhỏ. Bracket với giả thiết liên tục/dấu đúng cho chặn theo độ rộng; các thuật toán nhanh như Newton phải có bảo vệ và status trung thực; với hệ kém điều kiện, luôn báo giới hạn chất lượng thay vì chỉ báo một con số đẹp.

# Phương pháp lặp và kiểm tra hội tụ

## 1. Phương pháp lặp trong thuật toán số

Khi không có công thức đóng thuận tiện hoặc nghiệm không thể biểu diễn chính xác bằng số máy, ta tính dãy x0,x1,x2,... từ một quy tắc cập nhật. Các ví dụ gồm giải phương trình f(x)=0, tìm điểm bất động x=g(x), căn bậc hai, và các phương pháp lặp cho hệ tuyến tính.

Phải phân biệt ba việc: **thiết kế phép cập nhật**, **chứng minh/đặt giả thiết hội tụ**, và **quyết định khi nào dừng để có kết quả đủ tin cậy**. Một vòng lặp kết thúc vì x mới bằng x cũ trong double chưa chứng minh đã tìm đúng nghiệm.

Ví dụ x_new=x+1e-15 tại x=1e12 có thể cho x_new==x do làm tròn, dù phương trình x=x+1e-15 vô nghiệm trong số thực. Đây là **stagnation** (đình trệ số), không phải hội tụ thật.

Bài học so sánh ba kỹ thuật: **chia đôi** có bracket và cận sai số, **Newton** nhanh cục bộ nhưng có rủi ro đạo hàm, và **điểm bất động co** có cận sai số hậu nghiệm.

## 2. Hội tụ, residual và sai số nghiệm

Dãy (x_k) hội tụ về x* nếu với mọi epsilon>0 có chỉ số K sao cho mọi k>=K đều có |x_k-x*|<epsilon. Trong chương trình, x* thường không biết để đo trực tiếp.

| Đại lượng | Công thức | Ý nghĩa |
|---|---|---|
| Forward error | |x_k-x*| | Sai số nghiệm thực sự |
| Residual tìm nghiệm | |f(x_k)| | Mức vi phạm f(x)=0 |
| Residual điểm bất động | |g(x_k)-x_k| | Mức vi phạm x=g(x) |
| Step difference | |x_k-x_(k-1)| | Độ thay đổi giữa hai vòng |
| Error bound | B_k với |x_k-x*|<=B_k | Chứng chỉ sai số nếu được chứng minh |

Residual nhỏ **không tự động** suy ra forward error nhỏ. Ví dụ f(x)=1e-12*(x-100) có nghiệm x*=100. Tại x=0, |f(0)|=1e-10 nhỏ nhưng forward error bằng 100. Muốn suy ra sai số từ residual cần thông tin về điều kiện bài toán, ví dụ |f'(t)|>=m>0 và phù hợp các giả thiết trên khoảng từ x đến x* thì |x-x*|<=|f(x)|/m.

Step nhỏ cũng chưa đủ: phép lặp có thể đứng yên do precision double hoặc có hệ số damping rất nhỏ nên tiến triển quá chậm. Hãy ưu tiên một **bound có chứng minh**, dùng residual/step để chẩn đoán và ghi rõ tiêu chí dừng đã đạt.

### 2.1. Ngưỡng tuyệt đối và tương đối

Một kiểm tra step thực tiễn: |x_new-x_old| <= absTol+relTol*max(1,|x_new|). Đây chỉ là ngưỡng **độ thay đổi**, chưa phải cận nghiệm. Hệ số 1 ngầm chọn thang chuẩn; bài có đơn vị thực tế nên dùng một scale phù hợp. Đặt tolX cho sai số của x và tolF cho residual f(x), không mặc định chúng có cùng đơn vị.

## 3. Bisection: hội tụ bằng đoạn kẹp nghiệm

Giả sử f liên tục trên [a,b], f(a) và f(b) khác dấu. Theo định lý giá trị trung gian, tồn tại ít nhất một nghiệm x* trong [a,b]. Tính m=a+(b-a)/2:

1. Nếu f(m)=0, trả m.
2. Nếu f(a) và f(m) cùng dấu, thay a=m.
3. Nếu ngược dấu, thay b=m.

Cặp đầu mút luôn kẹp ít nhất một nghiệm. Sau mỗi bước, độ rộng đoạn giảm một nửa. Nếu lấy trung điểm m cuối, **|m-x*| <= (b-a)/2** đối với một nghiệm được kẹp, dưới giả thiết liên tục và đánh giá dấu đáng tin.

### 3.1. Ví dụ tìm căn bậc hai của 2

Đặt f(x)=x*x-2; bracket [1,2] vì f(1)=-1, f(2)=2. Những vòng đầu:

| Vòng | Đoạn trước | m | f(m) | Đoạn sau |
|---:|---|---:|---:|---|
| 1 | [1,2] | 1.5 | +0.25 | [1,1.5] |
| 2 | [1,1.5] | 1.25 | -0.4375 | [1.25,1.5] |
| 3 | [1.25,1.5] | 1.375 | -0.109375 | [1.375,1.5] |
| 4 | [1.375,1.5] | 1.4375 | +0.06640625 | [1.375,1.4375] |

Với độ rộng ban đầu W0 và ngưỡng nửa độ rộng eps, khoảng ceil(log2(W0/(2eps))) bước thu hẹp là đủ nếu chưa chạm nghiệm sớm và floating-point còn biểu diễn được midpoint mới.

### 3.2. Kiểm tra bracket đúng

Nên kiểm riêng f(a),f(b) là hữu hạn, xử lý nghiệm tại đầu mút, rồi so dấu. Không nhân f(a)*f(b) trên double để xét dấu: có thể overflow/underflow. Hai đầu cùng dấu trả trạng thái NO_BRACKET, **không kết luận phương trình vô nghiệm trên mọi nơi**.

Nếu m làm tròn thành một đầu mút và chưa đạt tol, trả STAGNATED; lặp tiếp sẽ không làm đoạn nhỏ hơn. Nếu f không liên tục, việc đổi dấu có thể đến từ điểm gián đoạn, không chứng minh có nghiệm.

## 4. Newton–Raphson: tiếp tuyến và hội tụ cục bộ

Với f khả vi, x_new=x-f(x)/f'(x). Từ f=x²−2, đạo hàm f'=2x, suy ra x_new=(x+2/x)/2. Từ x0=1:

```text
x0=1
x1=1.5
x2=1.4166666666666667
x3=1.4142156862745099
x4=1.4142135623746899
x5=1.4142135623730951
```

Nếu f đủ trơn, nghiệm đơn f'(x*) khác 0 và x0 đủ gần, Newton thường hội tụ bậc hai: gần nghiệm, sai số bước sau tỷ lệ bình phương sai số bước trước. Đó là bảo đảm **cục bộ**, không phải hội tụ từ mọi x0.

Với x0=0 và f=x²−2, f'(0)=0 nên không chia được. Với hàm khác, đạo hàm rất nhỏ có thể dẫn đến bước nhảy lớn; các phép toán có thể cho NaN/Infinity hoặc rời miền nghiệm. Dùng giới hạn vòng, kiểm hữu hạn/đạo hàm và cân nhắc damping hoặc Newton–bisection hybrid.

Hàm Java mẫu dừng khi |f(x)|<=tolF, nên trạng thái CONVERGED cho Newton có nghĩa **residual đạt ngưỡng**, không tự cấp cận forward error. Trường errorBound được để NaN.

## 5. Phép lặp điểm bất động

Từ x=g(x), chạy x_(k+1)=g(x_k). Không phải mọi g đều hội tụ. Ví dụ g(x)=2-x, từ x0 khác 1 sẽ luân phiên x0 và 2-x0, mặc dù điểm bất động x*=1 tồn tại.

### 5.1. Định lý ánh xạ co

Nếu I là đoạn đóng, g(I) nằm trong I, và có q trong [0,1) sao cho mọi x,y trong I thỏa |g(x)-g(y)|<=q*|x-y|, thì tồn tại duy nhất điểm bất động x* trong I và phép lặp hội tụ về x* từ mọi x0 trong I (định lý Banach).

Nếu g khả vi, điều kiện đủ thường dùng là sup trên I của |g'(x)|<=q<1. Khi đó e_(k+1)<=q*e_k; hơn nữa có cận **hậu nghiệm**:

**|x_k-x*| <= q/(1-q)*|x_k-x_(k-1)|**, k>=1.

Đây là trường hợp **step nhỏ dẫn đến cận sai số** nhờ định lý đã chứng minh, khác với chỉ kiểm step một cách tùy tiện.

### 5.2. Lặp x=cos(x)

Chọn g(x)=cos(x), miền I=[0,1]. Cos đưa I vào [cos(1),1], nằm trong I. |g'(x)|=sin(x)<=sin(1)≈0.84147. Chọn q=0.85 là cận trên hợp lệ và <1. Từ x0=1, lặp x_new=cos(x_old) và dừng khi q/(1-q)*|x_new-x_old|<=1e-10. Nghiệm khoảng 0.7390851332151607.

Không được dùng bound co trên nếu khởi tạo x0 ngoài I mà chưa chứng minh một miền khác. Hàm mẫu từ chối x0 ngoài [0,1].

### 5.3. Chu kỳ và stagnation

Với g(x)=-x, x0=1, ta có 1,-1,1,-1,..., là chu kỳ hai, không hội tụ. So x_(k+1) với x_(k-1) có thể phát hiện chu kỳ hai chính xác trên máy; không phát hiện được không có nghĩa là không tồn tại chu kỳ khác.

## 6. Chọn tiêu chí dừng và mã trạng thái

**CONVERGED** phải kèm diễn giải: bisection đạt bound nửa bracket; Newton đạt residual; fixed point cos đạt contraction bound. Không đánh đồng ba điều kiện thành một mức đảm bảo forward error.

**NO_BRACKET:** hai đầu không chứng minh có nghiệm kẹp. **ZERO_DERIVATIVE:** Newton không thể chia an toàn. **NONFINITE:** có NaN/Infinity. **STAGNATED:** bước mới không thay đổi vì độ phân giải hoặc tiến triển bị mất, trong khi chưa đạt mục tiêu. **CYCLE:** phát hiện một chu kỳ. **MAX_ITERATIONS:** hết ngân sách vòng khi chưa đạt điều kiện.

Double gần 1 có độ chính xác tương đối khoảng 2.22e-16, nhưng khoảng cách hai số biểu diễn tăng theo độ lớn |x|. Ngưỡng quá nhỏ có thể khiến thuật toán không tiến triển. Kiểm Double.isFinite trước các quyết định dừng; với NaN các so sánh lớn/nhỏ thông thường đều cho false.

## 7. Lựa chọn phương pháp

| Cách | Điều kiện then chốt | Đảm bảo | Hạn chế |
|---|---|---|---|
| Chia đôi | f liên tục, bracket trái dấu | Giữ nghiệm, bound nửa đoạn; O(log(W/eps)) | Cần bracket, co tuyến tính |
| Newton | f trơn, nghiệm đơn, x0 đủ gần | Bậc hai cục bộ | Đạo hàm 0, có thể phân kỳ |
| Secant | Hai điểm và mẫu sai phân khác 0 | Thường siêu tuyến tính cục bộ, không cần f' | Có thể bất ổn khi f gần bằng nhau |
| Fixed point | g đưa I vào I, co q<1 | Hội tụ trên I, bound hậu nghiệm | Khó chọn và chứng minh g |
| Hybrid | Bracket + bước Newton có bảo vệ | Kết hợp nhanh và an toàn | Phức tạp hơn |

Đối với hệ tuyến tính, các phương pháp Jacobi/Gauss–Seidel cũng là phép lặp. Điều kiện hội tụ thường liên quan bán kính phổ ma trận lặp <1; chéo trội nghiêm ngặt là một điều kiện đủ phổ biến. Tính điều kiện của ma trận ảnh hưởng mối liên hệ residual ||Ax-b|| với sai số nghiệm.

## 8. Độ phức tạp và chi phí

Bisection dùng O(log(W0/eps)) lần đánh giá f, bộ nhớ O(1). Fixed point co hệ số q cần số bước tỉ lệ log(eps)/log(q) khi sai số giảm theo q^k; nếu q gần 1, tiến rất chậm. Newton gần nghiệm đơn hội tụ bậc hai nhưng mỗi bước cần f và f' (trong nhiều chiều có thể phải giải hệ Jacobian). Số vòng ít không có nghĩa thời gian CPU ít nếu mỗi bước đắt.

## 9. Quy trình triển khai an toàn

1. Xác định f(x)=0 hoặc x=g(x), miền nghiệm và đơn vị/thang dữ liệu.
2. Chọn điều kiện hội tụ có thể chứng minh: bracket, đạo hàm hoặc co.
3. Chọn khởi tạo/đoạn đúng; từ chối những tiền điều kiện không thỏa.
4. Mỗi vòng tính hàm và bước cập nhật, kiểm giá trị hữu hạn, đạo hàm/mẫu khác 0.
5. Đo residual, step và bound (nếu chứng minh được).
6. Kiểm tolX và tolF có ý nghĩa đúng đơn vị; bổ sung relative scale khi cần.
7. Có maxIterations, phát hiện stagnation và chu kỳ chẩn đoán.
8. Trả trạng thái và số vòng, không gán nhãn thành công cho một lối thoát lỗi.
9. Dùng nghiệm tham chiếu hoặc phương pháp độc lập để kiểm thử các ca nhỏ và biên.

## 10. Những phản ví dụ phải hiểu

- Newton x0=0 với f=x²−2: đạo hàm bằng 0.
- Chia đôi f=x²−2 trên [2,3]: không có bracket, dù nghiệm tồn tại ở khoảng khác.
- g(x)=-x từ x0=1: chu kỳ hai.
- f(x)=1e-12*(x-100) ở x=0: residual=1e-10, forward error=100.
- g(x)=x+1e-15 với x=1e12: x_new có thể bằng x trong double dù không có điểm bất động thực.

Mỗi phản ví dụ cho thấy tại sao kiểm tra hội tụ không thể chỉ là một biểu thức if duy nhất không có giả thiết toán học.

## 11. Java 17+ hoàn chỉnh và kiểm thử

Chương trình có ba phương pháp lặp, trả record gồm x, số bước, residual, errorBound và status. Với Newton, errorBound=NaN là chủ ý vì chưa có chứng minh bound nghiệm tổng quát. Mã runnable trong một tệp UTF-8 tên **IterativeConvergenceDemo.java**.

```java
import java.util.Locale;
import java.util.Random;
import java.util.function.DoubleUnaryOperator;

public final class IterativeConvergenceDemo {
    private IterativeConvergenceDemo() {}

    enum Status {
        CONVERGED, NO_BRACKET, ZERO_DERIVATIVE,
        STAGNATED, CYCLE, NONFINITE, MAX_ITERATIONS
    }

    record Result(double x, int iterations, double residual,
                  double errorBound, Status status) {}

    static void requireTolerance(double tol, int maxIterations) {
        if (!Double.isFinite(tol) || tol <= 0
                || maxIterations < 1) {
            throw new IllegalArgumentException(
                "positive finite tolerance and positive maxIterations"
            );
        }
    }

    // Bisection: requires continuous f and sign-changing bracket.
    static Result bisection(
            DoubleUnaryOperator f,
            double lo, double hi, double tolX,
            int maxIterations) {
        requireTolerance(tolX, maxIterations);
        if (!Double.isFinite(lo) || !Double.isFinite(hi)
                || !(lo < hi)) {
            throw new IllegalArgumentException("invalid interval");
        }

        double flo = f.applyAsDouble(lo);
        double fhi = f.applyAsDouble(hi);
        if (!Double.isFinite(flo) || !Double.isFinite(fhi)) {
            return new Result(Double.NaN, 0, Double.NaN,
                Double.NaN, Status.NONFINITE);
        }
        if (flo == 0) {
            return new Result(lo, 0, 0, 0, Status.CONVERGED);
        }
        if (fhi == 0) {
            return new Result(hi, 0, 0, 0, Status.CONVERGED);
        }
        if (Math.signum(flo) == Math.signum(fhi)) {
            return new Result(Double.NaN, 0, Double.NaN,
                Double.NaN, Status.NO_BRACKET);
        }

        for (int k = 0; k <= maxIterations; k++) {
            double mid = lo + 0.5 * (hi - lo);
            double fm = f.applyAsDouble(mid);
            double bound = 0.5 * (hi - lo);

            if (!Double.isFinite(mid)
                    || !Double.isFinite(fm)
                    || !Double.isFinite(bound)) {
                return new Result(mid, k, Double.NaN,
                    Double.NaN, Status.NONFINITE);
            }
            if (fm == 0 || bound <= tolX) {
                return new Result(mid, k, Math.abs(fm),
                    bound, Status.CONVERGED);
            }
            if (k == maxIterations) {
                return new Result(mid, k, Math.abs(fm),
                    bound, Status.MAX_ITERATIONS);
            }
            if (mid == lo || mid == hi) {
                return new Result(mid, k, Math.abs(fm),
                    bound, Status.STAGNATED);
            }

            if (Math.signum(fm) == Math.signum(flo)) {
                lo = mid;
                flo = fm;
            } else {
                hi = mid;
            }
        }
        throw new AssertionError("unreachable");
    }

    // CONVERGED here means residual meets tolF, not forward error.
    static Result newton(
            DoubleUnaryOperator f,
            DoubleUnaryOperator derivative,
            double x0, double tolF, int maxIterations) {
        requireTolerance(tolF, maxIterations);
        if (!Double.isFinite(x0)) {
            throw new IllegalArgumentException("nonfinite x0");
        }

        double x = x0;
        for (int k = 0; k <= maxIterations; k++) {
            double fx = f.applyAsDouble(x);
            if (!Double.isFinite(fx)) {
                return new Result(x, k, Double.NaN,
                    Double.NaN, Status.NONFINITE);
            }
            if (Math.abs(fx) <= tolF) {
                return new Result(x, k, Math.abs(fx),
                    Double.NaN, Status.CONVERGED);
            }
            if (k == maxIterations) {
                return new Result(x, k, Math.abs(fx),
                    Double.NaN, Status.MAX_ITERATIONS);
            }

            double dfx = derivative.applyAsDouble(x);
            if (!Double.isFinite(dfx)) {
                return new Result(x, k, Math.abs(fx),
                    Double.NaN, Status.NONFINITE);
            }
            if (dfx == 0) {
                return new Result(x, k, Math.abs(fx),
                    Double.NaN, Status.ZERO_DERIVATIVE);
            }

            double next = x - fx / dfx;
            if (!Double.isFinite(next)) {
                return new Result(x, k, Math.abs(fx),
                    Double.NaN, Status.NONFINITE);
            }
            if (next == x) {
                return new Result(x, k, Math.abs(fx),
                    Double.NaN, Status.STAGNATED);
            }
            x = next;
        }
        throw new AssertionError("unreachable");
    }

    // cos is a contraction with q=0.85 on [0,1].
    static Result fixedPointCos(
            double x0, double tolError, int maxIterations) {
        requireTolerance(tolError, maxIterations);
        if (!Double.isFinite(x0) || x0 < 0 || x0 > 1) {
            throw new IllegalArgumentException(
                "x0 must be in [0,1]"
            );
        }

        final double q = 0.85;
        double x = x0;

        for (int k = 1; k <= maxIterations; k++) {
            double next = Math.cos(x);
            if (!Double.isFinite(next)
                    || next < 0 || next > 1) {
                return new Result(x, k, Double.NaN,
                    Double.NaN, Status.NONFINITE);
            }

            double step = Math.abs(next - x);
            double bound = q / (1 - q) * step;
            double residual = Math.abs(Math.cos(next) - next);

            if (bound <= tolError) {
                return new Result(next, k, residual,
                    bound, Status.CONVERGED);
            }
            if (next == x) {
                return new Result(x, k, residual,
                    bound, Status.STAGNATED);
            }
            x = next;
        }
        return new Result(x, maxIterations,
            Math.abs(Math.cos(x) - x),
            Double.NaN, Status.MAX_ITERATIONS);
    }

    // Diagnostic for exact two-step periodicity in double.
    static Status detectTwoCycle(
            DoubleUnaryOperator update,
            double initial, int maxIterations) {
        if (!Double.isFinite(initial) || maxIterations < 2) {
            throw new IllegalArgumentException("invalid cycle test");
        }
        double previous = Double.NaN, x = initial;
        for (int k = 1; k <= maxIterations; k++) {
            double next = update.applyAsDouble(x);
            if (!Double.isFinite(next)) return Status.NONFINITE;
            if (next == x) return Status.CONVERGED;
            if (k >= 2 && next == previous) return Status.CYCLE;
            previous = x;
            x = next;
        }
        return Status.MAX_ITERATIONS;
    }

    private static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    public static void main(String[] args) {
        DoubleUnaryOperator f = x -> x * x - 2;
        DoubleUnaryOperator df = x -> 2 * x;

        Result bis = bisection(f, 1, 2, 1e-12, 200);
        Result newt = newton(f, df, 1, 1e-14, 100);
        Result fixed = fixedPointCos(1, 1e-10, 1000);

        System.out.printf(Locale.ROOT,
            "Bisection sqrt2: x=%.12f, iter=%d, boundOK=%s%n",
            bis.x(), bis.iterations(),
            bis.status() == Status.CONVERGED
                && bis.errorBound() <= 1e-12
        );
        System.out.printf(Locale.ROOT,
            "Newton sqrt2: x=%.12f, iter=%d, residualOK=%s%n",
            newt.x(), newt.iterations(),
            newt.status() == Status.CONVERGED
                && newt.residual() <= 1e-14
        );
        System.out.printf(Locale.ROOT,
            "Fixed cos: x=%.10f, iter=%d, boundOK=%s%n",
            fixed.x(), fixed.iterations(),
            fixed.status() == Status.CONVERGED
                && fixed.errorBound() <= 1e-10
        );

        System.out.println("No bracket: " +
            bisection(f, 2, 3, 1e-12, 100).status());
        System.out.println("Newton x0=0: " +
            newton(f, df, 0, 1e-14, 100).status());
        System.out.println("Two-cycle x->-x: " +
            detectTwoCycle(x -> -x, 1, 10));

        double referenceCos = 0.7390851332151607;
        check(Math.abs(bis.x() - Math.sqrt(2)) <= 1e-12,
            "bisection sample inaccurate");
        check(Math.abs(newt.x() - Math.sqrt(2)) <= 1e-12,
            "Newton sample inaccurate");
        check(Math.abs(fixed.x() - referenceCos)
                <= fixed.errorBound() + 1e-14,
            "fixed-point posterior bound invalid");

        Random random = new Random(439L);
        for (int t = 0; t < 1_200; t++) {
            double target = 1 + 99 * random.nextDouble();
            DoubleUnaryOperator ft = x -> x * x - target;

            Result rb = bisection(
                ft, 0, target + 1, 1e-10, 200);
            check(rb.status() == Status.CONVERGED
                && rb.errorBound() <= 1e-10
                && Math.abs(rb.x() - Math.sqrt(target))
                    <= 1.1e-10,
                "bisection trial=" + t);

            Result rn = newton(ft, df, 1, 1e-11, 100);
            check(rn.status() == Status.CONVERGED
                && rn.residual() <= 1e-11
                && Math.abs(rn.x() - Math.sqrt(target))
                    < 1e-8,
                "Newton trial=" + t);
        }

        for (int t = 0; t < 600; t++) {
            double start = random.nextDouble();
            Result r = fixedPointCos(start, 1e-10, 1000);
            check(r.status() == Status.CONVERGED
                && Math.abs(r.x() - referenceCos)
                    <= r.errorBound() + 1e-14,
                "fixed-point trial=" + t);
        }

        System.out.println("Random bisection: 1200 PASS");
        System.out.println("Random Newton: 1200 PASS");
        System.out.println("Random fixed-point: 600 PASS");
    }
}
```

### 11.1. Biên dịch

```bash
javac -encoding UTF-8 IterativeConvergenceDemo.java
java IterativeConvergenceDemo
```

**Đầu ra xác định:**

```text
Bisection sqrt2: x=1.414213562372, iter=39, boundOK=true
Newton sqrt2: x=1.414213562373, iter=5, residualOK=true
Fixed cos: x=0.7390851332, iter=62, boundOK=true
No bracket: NO_BRACKET
Newton x0=0: ZERO_DERIVATIVE
Two-cycle x->-x: CYCLE
Random bisection: 1200 PASS
Random Newton: 1200 PASS
Random fixed-point: 600 PASS
```

### 11.2. Đọc kết quả

- Bisection CONVERGED với boundOK=true: đã chứng minh ít nhất một nghiệm được kẹp và nửa độ rộng <=tolX, dưới các giả thiết liên tục/đánh giá dấu tin cậy.
- Newton CONVERGED với residualOK=true: |f(x)|<=tolF. Không tự suy ra |x-x*|<=tolF cho mọi hàm.
- Fixed cos boundOK=true: điều kiện co trên [0,1] chứng minh sai số nghiệm <=q/(1-q)*step.
- NO_BRACKET, ZERO_DERIVATIVE, STAGNATED, CYCLE, NONFINITE, MAX_ITERATIONS đều là trạng thái cần xử lý, không phải nghiệm được bảo đảm.

### 11.3. Kiểm thử ngẫu nhiên

Seed `Random(439L)` giúp tái hiện. 1.200 giá trị target trong [1,100) dùng f(x)=x²−target, đối chiếu bisection và Newton với Math.sqrt(target); 600 khởi đầu trong [0,1] dùng contraction bound của cos và nghiệm tham chiếu. Các test thực nghiệm không thay thế định lý hội tụ, nhưng giúp bắt lỗi cập nhật, điều kiện dừng và kiểu dữ liệu.

## 12. Những sai lầm thường gặp

| Lỗi | Vấn đề | Sửa đúng |
|---|---|---|
| Chỉ nhìn step nhỏ | Có thể stagnation | Cần residual và bound nếu có |
| Residual nhỏ => nghiệm gần | Bài kém điều kiện | Bound đạo hàm/Jacobian hoặc bracket |
| Chung epsilon cho f và x | Khác đơn vị | Dùng tolF, tolX đúng thang |
| f(a)*f(b)<0 bằng double | Tích tràn/underflow | Kiểm dấu riêng từng đầu |
| Quên f liên tục trong bisection | Đổi dấu do gián đoạn | Xác nhận giả thiết |
| Không giữ bracket trong bisection | Mất chứng chỉ | Giữ nửa hai dấu khác nhau |
| Newton chia f'=0 | Lỗi phép chia | Trạng thái ZERO_DERIVATIVE |
| Newton từ x0 bất kỳ được tin hội tụ | Chỉ bảo đảm cục bộ | Chọn vùng khởi đầu/safeguard |
| Fixed point nào cũng được coi co | Có thể chu kỳ/phân kỳ | Chứng minh g(I) subset I và q<1 |
| Dùng q=1 trong q/(1-q) | Mẫu bằng 0 | q phải <1 |
| Bỏ kiểm x0 thuộc miền I | Bound Banach không áp dụng | Ràng buộc đầu vào |
| Quên Double.isFinite | NaN/Infinity làm hỏng quyết định | Kiểm mọi giá trị quan trọng |
| Khi next==x thì CONVERGED | Có thể kẹt vì roundoff | Trạng thái STAGNATED |
| Không có maxIterations | Lặp vô hạn | Ngân sách vòng bắt buộc |
| Yêu cầu tol dưới precision máy | Không tiến triển | Tol hợp lý hoặc số học cao hơn |
| Chỉ kiểm sqrt2 một lần | Không bắt lỗi biên | Test nhiều target, x0, trạng thái lỗi |

## 13. Bài tập có đáp án

**Bài 1.** Thuật toán lặp cần ba thành phần? *Đáp án:* quy tắc cập nhật, điều kiện hội tụ, tiêu chí kiểm tra/dừng.

**Bài 2.** Residual khác forward error thế nào? *Đáp án:* residual là |f(x)|, forward error là |x-x*|.

**Bài 3.** next==x trong double đã đủ chứng minh không sai? *Đáp án:* không, có thể stagnation.

**Bài 4.** f=1e-12*(x-100), tại x=0 residual/error? *Đáp án:* 1e-10 / 100.

**Bài 5.** Bisection cần gì ở f và hai đầu? *Đáp án:* liên tục, giá trị hữu hạn và hai dấu trái nhau (hoặc đầu mút là nghiệm).

**Bài 6.** f=x²−2 trên [1,2], midpoint đầu? *Đáp án:* 1.5.

**Bài 7.** f(1.5)=0.25 thì giữ nửa nào? *Đáp án:* [1,1.5].

**Bài 8.** Đoạn có độ rộng 0.002 thì bound midpoint? *Đáp án:* 0.001.

**Bài 9.** Cần thêm bao nhiêu bước khi giảm tolX một nửa? *Đáp án:* thường thêm một lần chia đôi.

**Bài 10.** Công thức Newton? *Đáp án:* x_new=x−f(x)/f'(x).

**Bài 11.** Newton sqrt2 từ x0=1 cho x1? *Đáp án:* 1.5.

**Bài 12.** Newton từ x0=0 cho f=x²−2? *Đáp án:* f'(0)=0, không chia được.

**Bài 13.** Newton có hội tụ bậc hai toàn cục không? *Đáp án:* không, đó là tính chất cục bộ.

**Bài 14.** Cải thiện độ bền Newton bằng gì? *Đáp án:* damping/line search hoặc hybrid bisection.

**Bài 15.** Điều kiện co? *Đáp án:* g(I) trong I và |g(x)-g(y)|<=q|x-y| với q<1.

**Bài 16.** Vì sao cos co trên [0,1]? *Đáp án:* |g'|<=sin(1)<0.85 và g(I) trong I.

**Bài 17.** Với q=.85, step=1e-12, cận hậu nghiệm? *Đáp án:* khoảng 5.667e-12.

**Bài 18.** g(x)=-x từ x0=1 tạo dãy gì? *Đáp án:* 1,-1,1,-1,...

**Bài 19.** tolX và tolF cùng 1e-12 có tương đương? *Đáp án:* không, hai đại lượng khác thang/đơn vị.

**Bài 20.** Vì sao cần Double.isFinite? *Đáp án:* tránh NaN/Infinity lọt vào quyết định dừng.

**Bài 21.** NO_BRACKET nghĩa là vô nghiệm? *Đáp án:* không, chỉ không có chứng chỉ bracket bằng hai dấu.

**Bài 22.** Newton residual đạt tol và errorBound=NaN? *Đáp án:* đạt tiêu chí residual nhưng chưa có cận forward error.

**Bài 23.** Nghiệm x=cos(x) khoảng bao nhiêu? *Đáp án:* 0.7390851332151607.

**Bài 24.** Vì sao cần oracle/tham chiếu độc lập? *Đáp án:* phát hiện lỗi trong cài đặt và tránh kiểm bằng cùng một vòng lặp sai.

**Bài 25.** Hội tụ bậc hai có nghĩa gì? *Đáp án:* gần nghiệm, sai số bước sau tỷ lệ bình phương sai số cũ.

## 14. Checklist

1. Nêu đúng phương trình f(x)=0 hoặc x=g(x), miền và thang dữ liệu.
2. Phân biệt forward error, residual, step và bound có chứng minh.
3. Bisection: kiểm liên tục, bracket, nghiệm ở đầu, dấu và tiến triển.
4. Newton: kiểm f', số hữu hạn, x0 phù hợp, giới hạn bước/vòng.
5. Fixed point: chứng minh g(I) trong I, q<1, x0 thuộc I.
6. Có tolX, tolF phù hợp đơn vị; không dừng chỉ bằng next==x.
7. Có maxIterations, phát hiện stagnation/chu kỳ/nonfinite.
8. Trả trạng thái với ý nghĩa rõ và kiểm thử độc lập.

## Kết luận

**Dãy lặp thay đổi ít không đồng nghĩa nghiệm chính xác.** Bisection cho bound từ đoạn kẹp; Newton nhanh cục bộ nhưng phải xử lý đạo hàm và các thất bại; fixed point co cho bound hậu nghiệm. Một thuật toán số đáng tin phải nêu rõ giả thiết hội tụ, tiêu chí dừng, số vòng và trạng thái.

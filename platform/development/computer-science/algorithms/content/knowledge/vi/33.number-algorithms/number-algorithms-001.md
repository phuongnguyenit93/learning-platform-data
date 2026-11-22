# Chọn nghiệm gần đúng, độ chính xác và tiêu chí dừng

> **Chủ đề:** Computer Science Algorithms → **Thuật toán số**.  
> **Trọng tâm:** Cách chọn đúng nghiệm hoặc nhánh nghiệm cho bài toán số, xác định ý nghĩa của nghiệm gần đúng, đánh giá **sai số của nghiệm** và **phần dư phương trình**, kiểm soát độ nhạy (*conditioning*), chọn **sai số tuyệt đối/tương đối**, đặt điều kiện dừng đáng tin và phát hiện hội tụ giả. Các phương pháp minh họa gồm **chia đôi (*bisection*)**, **Newton–Raphson có bảo vệ**, **secant**, và **lặp điểm bất động**. Có bốn chương trình **Java 17** độc lập, ví dụ stdout, phép kiểm độc lập và bộ bài tập có lời giải.

## 1. Nghiệm đúng, nghiệm gần đúng và mục tiêu thực tế

Trong bài toán một biến, ta thường cần giải:

`f(x)=0`.

Một **nghiệm toán học chính xác** x* thỏa `f(x*)=0` trong số học thực. Trong máy tính, ta thường chỉ lưu được một giá trị hữu hạn x̂ (*x-hat*) gần x*. Ví dụ:

`f(x)=x²−2`.

Nghiệm dương chính xác là `x*=√2`, một số vô tỉ không thể lưu đúng bằng `double`. Máy trả một x̂ như `1.414213562373...`.

Tuy nhiên câu hỏi “x̂ có tốt không?” chưa đủ cụ thể. Phải biết:

1. **Cần nghiệm nào?** Nghiệm dương, âm, gần một giá trị ban đầu, trong khoảng cho trước, hay nghiệm thỏa điều kiện vật lý?
2. **Cần độ chính xác ở biến x hay ở giá trị f(x)?** Đây là hai mục tiêu khác nhau.
3. **Sai số đo bằng đơn vị gì?** Mét, giây, độ, tỷ lệ hay đại lượng không thứ nguyên?
4. **Có thể chứng minh được sai số không, hay chỉ đánh giá bằng heuristic?**
5. **Khi nào phải dừng mà không được nói “đã hội tụ”?** Hết vòng, đạo hàm bằng0, NaN, stagnation, không có bracket hợp lệ.

Bài phân biệt ba kết quả quan trọng:

- **Đã có chứng nhận sai số:** ví dụ nghiệm nằm trong một đoạn có đổi dấu và độ rộng đã nhỏ.
- **Đạt tiêu chí dừng thực dụng:** ví dụ Newton có bước nhỏ và phần dư nhỏ, nhưng chưa có chứng nhận chính xác tuyệt đối.
- **Chưa kết luận:** thuật toán mất tiến triển, quá ngân sách hoặc gặp dữ liệu số học bất thường.

### 1.1. Phương trình và hệ phương trình

Với `f:ℝ→ℝ`, nghiệm là điểm trên trục số. Với hệ `F(x)=0`, `x∈ℝ^n`, ta thay `|f(x)|` bằng một chuẩn của vectơ phần dư `||F(x)||`; ma trận Jacobi thay cho đạo hàm. Nhiều nguyên lý về **độ nhạy, sai số, điều kiện dừng và bảo vệ** tương tự, nhưng bài này xây dựng cẩn thận cho **một biến** trước.

### 1.2. Nghiệm gần đúng không nhất thiết là nghiệm đúng khi làm tròn

Trong `double`, ngay cả khi `f(x̂)` được tính ra **đúng 0.0**, điều đó vẫn chỉ nói phép đánh giá **số thực dấu phẩy động** tại x̂ cho kết quả 0.0. Nó không tự là một chứng minh `f(x̂)=0` theo số học thực: có thể có sai số làm tròn hoặc triệt tiêu số.

## 2. Chọn đúng nghiệm khi phương trình có nhiều nghiệm

Xét:

`f(x)=(x−1)(x−3)`.

Phương trình có **hai nghiệm thực**: 1 và3. Một chương trình không thể biết bạn muốn nghiệm nào nếu đề chỉ nói “tìm nghiệm”.

Ta có thể chỉ định:

- Nghiệm thuộc khoảng `(0,1.5)` ⇒ chọn nghiệm1.
- Nghiệm thuộc khoảng `(2.2,4)` ⇒ chọn nghiệm3.
- Nghiệm gần giá trị tham chiếu `x_ref=2.8` ⇒ ứng viên3 thường thích hợp hơn, **nếu tiêu chí của bài thực sự là gần tham chiếu**.
- Nghiệm không âm, không vượt công suất/giới hạn vận hành, thỏa điều kiện phụ.

### 2.1. Khoảng có đổi dấu giúp chọn nhánh

Với f **liên tục**, nếu `f(a)·f(b)<0` thì theo định lý giá trị trung gian tồn tại **ít nhất một nghiệm** trong `(a,b)`.

Trong code không nên tính tích hai `double` chỉ để kiểm trái dấu; tích có thể underflow/overflow. Thay vào đó so **dấu** của `f(a),f(b)` sau khi kiểm hữu hạn.

Với f ở trên:

- `[0,1.5]`: f(0)=3>0, f(1.5)=-0.75<0 ⇒ có nghiệm, cụ thể là1.
- `[2.2,4]`: f(2.2)<0, f(4)=3>0 ⇒ có nghiệm, cụ thể là3.
- `[0,4]`: f(0)=3 và f(4)=3, **không có đổi dấu** dù chứa **hai nghiệm**.

**Không đổi dấu không có nghĩa là không có nghiệm.** Có thể có số nghiệm chẵn, nghiệm bội chẵn hoặc nghiệm ở giữa nhưng hàm không đổi dấu.

### 2.2. Khi nào khoảng chỉ có một nghiệm?

Đổi dấu bảo đảm **tồn tại**, chưa tự bảo đảm **duy nhất**. Nếu f liên tục và **đơn điệu nghiêm ngặt** trên [a,b], cùng với đổi dấu, nghiệm trong khoảng là **duy nhất**.

Ví dụ f(x)=x²−2 trên [1,2] có đạo hàm `f'(x)=2x>0` ⇒ đơn điệu tăng; có đúng một nghiệm ở khoảng này.

Nếu f dao động, khoảng đổi dấu có thể chứa nhiều nghiệm. Thuật toán chia đôi hội tụ về **một** nghiệm trong khoảng, nhưng không đủ thông tin để gán đó là “nghiệm số 1” theo thứ tự mong muốn nếu chưa xác định nhánh.

### 2.3. Quy tắc lựa chọn nghiệm trong ứng dụng

Khi có nhiều nghiệm x1,x2,...:

1. Lọc theo **miền xác định**: không tính căn số âm, log không dương, chia cho0.
2. Lọc theo ràng buộc bài toán: áp suất/thời gian không âm, góc trong một chu kỳ quy định, nghiệm thuộc miền vận hành.
3. Chọn nhánh theo bracket, nghiệm trước đó của một mô hình liên tục, hoặc mục tiêu phụ đã công bố.
4. Nếu hai nghiệm đều phù hợp và gần như bằng nhau theo sai số hiện có, **tăng độ chính xác trước khi xếp hạng**.
5. Không lấy nghiệm có `|f(x)|` nhỏ nhất rồi tự coi đó là nhánh đúng: nhiều nghiệm đều có f gần0.

### 2.4. Một số bẫy khi chọn nghiệm

- `f(x)=x²`: nghiệm0 có **bội chẵn**, hai đầu -1 và1 đều có f=1 ⇒ bisection yêu cầu đổi dấu sẽ **từ chối bracket**, dù nghiệm tồn tại.
- `f(x)=sin(x)`: có vô số nghiệm `kπ`; phải xác định khoảng hoặc nhánh k.
- `f(x)=(x−1)²`: gần x=1, đạo hàm rất nhỏ; có thể có `|f(x)|` nhỏ nhưng x vẫn còn sai số tương đối đáng kể.
- Newton với hai seed khác nhau có thể về hai nghiệm khác nhau, hoặc dao động; **seed là lựa chọn thuật toán**, không là chứng minh chọn đúng nhánh.

## 3. Ba khái niệm chất lượng khác nhau

Đặt nghiệm đúng x*, nghiệm gần đúng x̂.

### 3.1. Sai số tuyệt đối của nghiệm (*forward error*)

`e_abs = |x̂−x*|`.

Đơn vị giống đơn vị của x. Nếu x đo bằng mét thì e_abs cũng là mét.

Ví dụ x*=1000, x̂=1000.001 ⇒ sai số tuyệt đối0.001.

Vấn đề: trong thực hành, x* chưa biết; vì thế **không thể trực tiếp tính e_abs**. Ta cần chặn trên, ước lượng hoặc oracle kiểm thử.

### 3.2. Sai số tương đối của nghiệm

Với x*≠0:

`e_rel=|x̂−x*|/|x*|`.

Ví dụ x*=1000, x̂=1000.001 ⇒ e_rel=10^-6.

**Khi x*=0**, công thức trên **không xác định**. Không chia cho0 hoặc thay bằng kết quả `Infinity` rồi gọi đó là mức chính xác. Khi nghiệm có thể gần0, cần dùng **ngưỡng tuyệt đối** kết hợp **ngưỡng tương đối theo scale**.

### 3.3. Phần dư của phương trình (*residual*)

`r = f(x̂)`; độ lớn phần dư `|r|=|f(x̂)|`.

Nó đo xem x̂ thỏa **phương trình** tốt tới mức nào, không tự đo **khoảng cách tới nghiệm**.

Ví dụ x̂=1.4 cho f(x)=x²−2:

`f(1.4)=1.96−2=−0.04`; residual=0.04.

Nhưng cùng residual0.04 trong một phương trình khác có thể tương ứng sai số x lớn hơn hoặc nhỏ hơn rất nhiều, tùy **độ dốc của hàm**.

### 3.4. Sai số lùi (*backward error*)

Một cách hiểu: x̂ là nghiệm đúng của một **bài toán đã bị nhiễu** bao nhiêu? Với bài toán `f(x)=0`, ta có thể xem x̂ là nghiệm chính xác của `f(x)+δ=0` với `δ=−f(x̂)`. Khi đó |δ| bằng residual.

Điều này hữu ích vì residual dễ tính, nhưng bài toán bị nhiễu theo cách nào và đơn vị/chuẩn của δ cần được xác định; **sai số lùi nhỏ không đồng nghĩa sai số nghiệm nhỏ** khi bài toán kém điều kiện.

## 4. Độ nhạy và tại sao residual nhỏ chưa đủ

Giả sử f khả vi và có nghiệm x*, với `f'(x*)≠0`. Tuyến tính hóa:

`f(x̂)≈f'(x*)·(x̂−x*)`.

Suy ra, khi x̂ đủ gần:

`|x̂−x*|≈|f(x̂)|/|f'(x*)|`.

Nếu đạo hàm rất nhỏ, cùng residual sẽ tương ứng **sai số nghiệm lớn**.

### 4.1. Ví dụ hàm “phẳng”

Xét:

`f_flat(x)=10^-12·(x−1000)`.

Nghiệm chính xác x*=1000. Chọn x̂=0:

`|f_flat(0)|=10^-9`.

Nếu tiêu chí dừng chỉ là `|f(x)|≤10^-8`, thuật toán sẽ nói “đạt” ngay tại0 — trong khi:

`|x̂−x*|=1000`.

**Residual rất nhỏ nhưng nghiệm hoàn toàn sai theo yêu cầu sai số x.** Lý do: `f'(x)=10^-12`.

### 4.2. Ví dụ hàm “dốc”

Xét:

`f_steep(x)=10^12·(x−1)`.

Nghiệm x*=1. Tại `x̂≈1+10^-9`, sai số nghiệm khoảng10^-9, nhưng residual khoảng10^3. Nếu chỉ yêu cầu residual<10^-8, thuật toán có thể chạy không cần thiết vì f được nhân một hệ số rất lớn.

### 4.3. Chặn sai số từ đạo hàm (*a posteriori bound*)

Giả sử f liên tục trên [a,b], khả vi trong khoảng trong, **có một nghiệm x*** và ta biết:

`|f'(x)|≥m>0`

với mọi x nằm trên đoạn nối x̂ và x*. Theo định lý giá trị trung bình:

`|f(x̂)−f(x*)| = |f'(ξ)|·|x̂−x*|`

với một ξ giữa x̂ và x*. Vì f(x*)=0:

`|x̂−x*|≤|f(x̂)|/m`.

Đây là **chặn trên có điều kiện**, mạnh hơn heuristic khi m được chứng minh, chẳng hạn f đơn điệu và đạo hàm được chặn dưới.

Với f(x)=x²−2 trên [1,2]:

`f'(x)=2x≥2`.

Nên, nếu x̂ và nghiệm dương đều thuộc [1,2]:

`|x̂−√2|≤|x̂²−2|/2`.

Trái lại, với hàm phẳng m=10^-12, residual10^-9 chỉ cho chặn1000, hoàn toàn không đủ.

### 4.4. Nghiệm bội và độ điều kiện kém

Với `f(x)=(x−1)²`, nghiệm x*=1 nhưng `f'(1)=0`.

Tại x̂=1.001:

`|f(x̂)|≈10^-6` trong khi `|x̂−1|=10^-3`.

Residual nhỏ hơn sai số nghiệm **ba bậc độ lớn**. Giới hạn m>0 không thể áp dụng trên khoảng chứa nghiệm vì đạo hàm bằng0 tại1.

### 4.5. Đánh giá hàm số cũng có thể sai số

Nếu `f(x)` được tính bằng double, giá trị `f̂(x)` khác f(x) toán học do làm tròn. Một chặn sai số nghiêm túc cần tính đến **sai số đánh giá hàm**. Ví dụ phép trừ hai số gần bằng nhau làm triệt tiêu chữ số có nghĩa (*catastrophic cancellation*). Không được gọi một bất đẳng thức toán học là **chứng chỉ máy tuyệt đối** nếu chưa kiểm tính đúng của dấu và phép đánh giá f.

## 5. Độ chính xác tuyệt đối, tương đối và hỗn hợp

Một tiêu chí phổ biến cho bước của x:

`|x_new−x_old|≤aTol + rTol·scaleX`,

trong đó:

- `aTol` là **ngưỡng tuyệt đối**, có cùng đơn vị với x.
- `rTol` là **ngưỡng tương đối**, không có đơn vị.
- `scaleX` đại diện thang đo phù hợp, chẳng hạn `max(xScale,|x_new|)` với `xScale>0` do bài toán quy định.

### 5.1. Vì sao không chỉ dùng relative?

Nếu nghiệm gần0, `rTol·|x|` có thể quá nhỏ, thậm chí bằng0, làm điều kiện dừng vô lý. Ngược lại, dùng `max(1,|x|)` là một **quy ước thang đo** dễ triển khai cho bài toán không thứ nguyên, chứ không phải luôn phù hợp với đại lượng có đơn vị và cỡ10^-12.

### 5.2. Vì sao không chỉ dùng absolute?

Nếu nghiệm cỡ10^12, aTol=10^-8 có thể nhỏ hơn nhiều so với độ phân giải double ở thang đó. Nếu nghiệm cỡ10^-12, aTol=10^-8 lại quá lỏng.

Chọn tolerance dựa trên **mục đích ứng dụng**, không chỉ trên số chữ số thập phân muốn in.

### 5.3. Cách chọn fTol

`fTol` nên dựa trên đơn vị của **f**, độ lớn dữ liệu và sai số mô hình. Một điều kiện như:

`|f(x)|≤fTol_abs + fTol_rel·scaleF`

cần `scaleF` có ý nghĩa vật lý/thuật toán.

Nếu nhân toàn bộ phương trình f bằng10^12, tập nghiệm **không đổi** nhưng residual đổi10^12 lần. Vì thế dùng một fTol tuyệt đối giống nhau cho mọi hàm có thể dẫn đến kết luận vô nghĩa.

### 5.4. Số chữ số khi in không phải sai số

In `1.414213562373` với 12 chữ số sau dấu chấm **không chứng minh** nghiệm đúng tới12 chữ số; thông tin quan trọng là **chặn sai số** hoặc tiêu chí kiểm đã dùng. Ngược lại, một nghiệm đã đạt sai số10^-13 có thể bị hiển thị ít chữ số vì định dạng `%.3f`.

## 6. Chia đôi (*bisection*): phương pháp có khoảng bao nghiệm

Giả sử f liên tục trên [a,b] và `f(a),f(b)` trái dấu. Theo định lý giá trị trung gian, tồn tại **ít nhất một nghiệm** trong khoảng.

Mỗi vòng:

1. Tính midpoint `m=a+(b−a)/2`.
2. Nếu f(m) được tính ra0, có thể trả `ZERO_RESIDUAL` theo đánh giá floating.
3. Nếu dấu f(m) giống f(a), đặt `a=m`; nếu không đặt `b=m`.
4. Khoảng mới vẫn có đổi dấu, nên tiếp tục chứa ít nhất một nghiệm.
5. Nếu khoảng đủ hẹp, trả midpoint kèm một **chặn sai số theo độ rộng**.

### 6.1. Chặn sai số theo khoảng

Với một nghiệm x* nằm trong [a,b], midpoint m=(a+b)/2:

`|m−x*|≤(b−a)/2`.

Đây là điểm mạnh của bisection: **không cần biết đạo hàm hay residual nhỏ cỡ nào** để có chặn sai số theo x, miễn bảo toàn được giả thiết bracket.

Khi [a,b] chứa nhiều nghiệm, bất đẳng thức bảo đảm midpoint gần **một nghiệm nào đó trong bracket**, không tự xác định nghiệm đã được đánh số từ trước.

### 6.2. Số bước dự kiến

Độ dài bracket sau k lần chia:

`L_k=(b0−a0)/2^k`

trong số học thực.

Muốn chặn sai số midpoint `≤ε`, cần:

`L_k/2≤ε`

⇒ `k≥ceil(log2((b0−a0)/(2ε)))`, nếu biểu thức bên trong>1. Đây là ước tính toán học; double có thể **ngừng chia tiến** trước k đó vì không còn giá trị biểu diễn nằm giữa hai đầu.

### 6.3. Không tính midpoint bằng `(a+b)/2` một cách vô điều kiện

Nếu a và b cùng dương và rất lớn, tổng a+b có thể overflow thành Infinity dù mỗi đầu hữu hạn.

Với bracket có b−a hữu hạn, thường dùng:

`a + (b−a)/2`.

Nếu b−a có thể overflow (ví dụ a≈−1e308, b≈1e308), cần chọn phép lấy midpoint được thiết kế an toàn hơn và xét giới hạn precision. Code demo bên dưới **từ chối bracket có độ rộng không hữu hạn** để hợp đồng đầu vào rõ ràng.

### 6.4. `mid==a` hoặc `mid==b`

Khi hai đầu rất gần, có thể không còn một số double nằm giữa chúng. Khi ấy midpoint bị làm tròn về một đầu, và vòng lặp không tiến. Phải trả trạng thái **STAGNATED** (hoặc chứng nhận dựa vào khoảng đã biết nếu đủ), không lặp vô hạn.

### 6.5. Nghiệm bội chẵn

Với f(x)=(x−1)² trên [0,2], f(0)=1 và f(2)=1, không có dấu trái nhau. **Bisection chuẩn sẽ không nhận bracket này**, mặc dù x=1 là nghiệm.

Có thể tìm nghiệm bội chẵn bằng phân tích đạo hàm, cực tiểu của |f|, hoặc thuật toán khác; nhưng nghiệm của bài tối ưu |f| có thể chỉ là cực tiểu dương **không phải nghiệm thật**, nên vẫn phải kiểm.

## 7. Java 17 — bisection với chứng nhận độ rộng bracket

Chương trình độc lập sau thể hiện ba trạng thái phân biệt:

- `BRACKET_CERTIFIED`: bracket vẫn đổi dấu, nửa độ rộng đã nhỏ hơn ngưỡng xTol.
- `ZERO_RESIDUAL`: f tại điểm được đánh giá bằng0.0; đây **không là chứng chỉ số học thực** nếu phép đánh giá f bằng double.
- `STAGNATED`/`MAX_ITERATIONS`: chưa đạt chặn mong muốn trong budget, không báo hội tụ giả.

Tất cả đầu vào phải hữu hạn, a<b, b−a hữu hạn, tolerance hợp lệ. Không suy “không có nghiệm” từ thất bại đổi dấu.

Lưu file **BracketBisectionDemo.java**:

```java
import java.util.Locale;
import java.util.function.DoubleUnaryOperator;

public class BracketBisectionDemo {
    enum Status {
        BRACKET_CERTIFIED, ZERO_RESIDUAL, STAGNATED, MAX_ITERATIONS
    }

    record Result(Status status, double x, double lo, double hi,
                  double residual, int iterations) {
        double halfWidth() {
            return (hi - lo) / 2.0;
        }
    }

    static Result solve(DoubleUnaryOperator f, double a, double b,
                        double absTol, double relTol, int maxIter) {
        if (!Double.isFinite(a) || !Double.isFinite(b)
                || !(a < b) || !Double.isFinite(b - a)
                || !Double.isFinite(absTol) || absTol <= 0
                || !Double.isFinite(relTol) || relTol < 0
                || maxIter <= 0) {
            throw new IllegalArgumentException("Invalid parameters");
        }

        double fa = f.applyAsDouble(a);
        double fb = f.applyAsDouble(b);
        if (!Double.isFinite(fa) || !Double.isFinite(fb)) {
            throw new IllegalArgumentException("Nonfinite endpoint value");
        }
        if (fa == 0.0) {
            return new Result(Status.ZERO_RESIDUAL, a, a, a, 0.0, 0);
        }
        if (fb == 0.0) {
            return new Result(Status.ZERO_RESIDUAL, b, b, b, 0.0, 0);
        }
        if ((fa > 0) == (fb > 0)) {
            throw new IllegalArgumentException("No sign-change bracket");
        }

        for (int i = 1; i <= maxIter; i++) {
            double m = a + (b - a) / 2.0;
            if (m == a || m == b) {
                return new Result(Status.STAGNATED, m, a, b,
                                  Math.abs(f.applyAsDouble(m)), i);
            }

            double fm = f.applyAsDouble(m);
            if (!Double.isFinite(fm)) {
                throw new IllegalArgumentException("Nonfinite f(mid)");
            }
            if (fm == 0.0) {
                return new Result(Status.ZERO_RESIDUAL, m, m, m, 0, i);
            }

            if ((fa > 0) == (fm > 0)) {
                a = m;
                fa = fm;
            } else {
                b = m;
                fb = fm;
            }

            double half = (b - a) / 2.0;
            double xTol = absTol + relTol
                    * Math.max(Math.abs(a), Math.abs(b));
            if (half <= xTol) {
                double estimate = a + (b - a) / 2.0;
                double residual = Math.abs(f.applyAsDouble(estimate));
                return new Result(Status.BRACKET_CERTIFIED, estimate,
                                  a, b, residual, i);
            }
        }

        double estimate = a + (b - a) / 2.0;
        return new Result(Status.MAX_ITERATIONS, estimate, a, b,
                Math.abs(f.applyAsDouble(estimate)), maxIter);
    }

    public static void main(String[] args) {
        DoubleUnaryOperator squareRootTwo = x -> x * x - 2.0;
        Result root = solve(squareRootTwo, 1.0, 2.0,
                            1e-13, 0.0, 200);

        System.out.printf(Locale.ROOT,
                "sqrt2 x=%.12f%n", root.x());
        System.out.println("sqrt2 status=" + root.status());
        System.out.println("sqrt2 iterations=" + root.iterations());
        System.out.println("sqrt2 halfWidth <= 1e-13: "
                + (root.halfWidth() <= 1e-13));
        System.out.println("sqrt2 residual <= 1e-11: "
                + (root.residual() <= 1e-11));

        DoubleUnaryOperator twoRoots =
                x -> (x - 1.0) * (x - 3.0);
        Result left = solve(twoRoots, 0.0, 1.5,
                            1e-12, 0.0, 200);
        Result right = solve(twoRoots, 2.2, 4.0,
                             1e-12, 0.0, 200);
        System.out.printf(Locale.ROOT,
                "left root=%.8f%n", left.x());
        System.out.printf(Locale.ROOT,
                "right root=%.8f%n", right.x());

        boolean rejected = false;
        try {
            solve(twoRoots, 0.0, 4.0, 1e-12, 0.0, 200);
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("[0,4] no sign bracket: " + rejected);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BracketBisectionDemo.java
java BracketBisectionDemo
```

Stdout dự kiến:

```text
sqrt2 x=1.414213562373
sqrt2 status=BRACKET_CERTIFIED
sqrt2 iterations=43
sqrt2 halfWidth <= 1e-13: true
sqrt2 residual <= 1e-11: true
left root=1.00000000
right root=3.00000000
[0,4] no sign bracket: true
```

### 7.1. Đừng hiểu `BRACKET_CERTIFIED` vượt mức giả thiết

Độ rộng cho **chặn sai số toán học** nếu f liên tục, bracket có dấu đúng và các cập nhật vẫn giữ nghiệm bên trong. Khi chạy bằng double, việc đánh giá dấu phải đáng tin; một f quá nhạy với làm tròn có thể làm mất chứng nhận tuyệt đối. Muốn chứng chỉ máy chắc chắn cần **interval arithmetic với làm tròn có hướng** hoặc robust evaluation thích hợp.

### 7.2. Vì sao kết quả đổi dấu không đảm bảo duy nhất?

Cùng một bracket có thể chứa ba nghiệm. Bisection vẫn tìm được **một nghiệm**, nhưng không đảm bảo đó là nghiệm mong muốn theo số thứ tự nếu bài chưa quy định. Phải thêm kiểm đơn điệu hoặc phân tách các khoảng nghiệm.

### 7.3. Vì sao residual và halfWidth cùng được in?

Residual kiểm phương trình; halfWidth kiểm **độ bất định về x** từ bracket. Chúng không đo cùng một điều. Ở đầu ra trên, kết luận mạnh về x đến từ **bracket**, không chỉ từ residual.

## 8. Newton–Raphson: hội tụ nhanh nhưng có thể sai nhánh

Newton áp dụng khai triển tuyến tính tại x_k:

`f(x)≈f(x_k)+f'(x_k)(x−x_k)`.

Giải phương trình tiếp tuyến bằng0:

`x(k+1)=x_k−f(x_k)/f'(x_k)`.

Nếu f trơn, nghiệm đơn `f'(x*)≠0` và seed đủ gần x*, Newton thường có **hội tụ bậc hai**:

`|e(k+1)|≈C·|e(k)|²`.

Điều này rất nhanh khi đã vào vùng hội tụ, nhưng **không** bảo đảm với mọi seed.

### 8.1. Ví dụ căn hai

Cho `f(x)=x²−2`, `f'(x)=2x`:

`x(k+1)=x_k−(x_k²−2)/(2x_k)`

`= (x_k+2/x_k)/2`.

Bắt đầu x0=1:

- x1=1.5.
- x2=1.4166666666666667.
- x3≈1.4142156862745099.
- x4≈1.4142135623746899.
- x5≈1.4142135623730951.

Các chữ số đúng tăng rất nhanh.

### 8.2. Khi đạo hàm bằng0 hoặc quá nhỏ

Nếu `f'(x_k)=0`, không thể dùng phép chia Newton. Nếu đạo hàm rất nhỏ, bước có thể **rất lớn**, vượt miền xác định hoặc bay khỏi nhánh nghiệm mong muốn.

Có thể:

- Dùng bracket để giữ nghiệm trong miền cho phép.
- Nếu bước Newton ra ngoài bracket hoặc không hữu hạn, thay bằng **midpoint**.
- Dừng với trạng thái lỗi/stagnation nếu không còn giá trị double mới.
- Không dựa vào một ngưỡng `|f'|<EPS` bất biến về đơn vị cho mọi bài toán.

### 8.3. Ví dụ Newton dao động

Với `f(x)=x³−2x+2`, `f'(x)=3x²−2`:

- x0=0 ⇒ x1=1.
- x1=1 ⇒ x2=0.

Newton **lặp chu kỳ 0↔1** thay vì tiến tới nghiệm thực âm. Một điều kiện dừng chỉ đếm số vòng hoặc chỉ nhìn x thay đổi cũng không giải quyết bản chất này; cần đánh giá tiến triển và/hoặc giữ bracket hợp lệ.

### 8.4. Khi nghiệm bội

Với `f(x)=(x−1)²`, Newton từ x≠1 cho:

`x_new = x−(x−1)²/[2(x−1)] = (x+1)/2`.

Sai số giảm **một nửa mỗi vòng**, chỉ hội tụ tuyến tính thay vì bậc hai. Vì `f'(1)=0`, bảo đảm bậc hai của nghiệm đơn không áp dụng.

## 9. Kết hợp Newton với bracket và tiêu chí dừng

Một cách thực dụng là **safeguarded Newton**:

1. Có bracket [a,b] với dấu hai đầu trái nhau.
2. Chọn x trong bracket; tính f(x).
3. Cập nhật đầu bracket bằng dấu f(x), giữ bracket chứa nghiệm.
4. Tạo bước Newton `x−f(x)/f'(x)`.
5. Nếu đạo hàm0, ứng viên không hữu hạn hoặc ứng viên ra ngoài bracket, chuyển sang midpoint.
6. Đánh giá tiêu chí dừng x **và** f, hoặc chặn bracket.
7. Có maxIter và nhãn trạng thái khi không tiến triển.

### 9.1. Không lẫn hai loại hội tụ

- `BRACKET_CERTIFIED`: dựa trên bracket đủ hẹp, có chặn sai số về x dưới giả thiết dấu đúng.
- `HEURISTIC_CONVERGED`: bước nhỏ **và** residual nhỏ, có ích nhưng không tự là chứng chỉ sai số x.
- `ZERO_RESIDUAL`: đánh giá f bằng0.0 trong double; không tự là chứng minh nghiệm chính xác theo số thực.
- `STAGNATED`: cập nhật không thay đổi được số double hoặc bước không còn nằm trong bracket.
- `MAX_ITERATIONS`: ngân sách đã hết.

### 9.2. Vì sao cần kiểm cả bước và residual?

Nếu chỉ residual, ví dụ hàm phẳng có thể dừng ở x sai rất xa.

Nếu chỉ bước, thuật toán có thể dừng vì:

- đạo hàm quá nhỏ dẫn tới xử lý sai,
- step bị rounding thành0,
- bị clamp/cắt bước liên tục,
- đang dao động nhỏ quanh một điểm không phải nghiệm.

Dùng **hai điều kiện** giúp tránh nhiều lỗi phổ biến, dù vẫn không thay thế được chặn sai số hoặc phân tích điều kiện.

### 9.3. Quy tắc chọn xTol

Trong demo dùng:

`xTol = 10^-12 + 10^-12·max(1,|x|)`.

Đây là lựa chọn **minh họa cho x không thứ nguyên**, không phải quy chuẩn chung. Nếu x có đơn vị và thang đo khác, phải thiết kế aTol/rTol/scaleX theo bài toán.

## 10. Java 17 — safeguarded Newton, fallback và kiểm dừng

Chương trình dưới giải căn hai dương trên [0,2], **chọn x0=0** khiến f'(0)=0 nên bắt buộc sử dụng **một lần bisection fallback**. Sau đó Newton hội tụ nhanh; trạng thái cuối là **HEURISTIC_CONVERGED**, không bị gọi nhầm là chứng nhận toán học tuyệt đối.

Lưu **SafeguardedNewtonDemo.java**:

```java
import java.util.Locale;
import java.util.function.DoubleUnaryOperator;

public class SafeguardedNewtonDemo {
    enum Status {
        HEURISTIC_CONVERGED, BRACKET_CERTIFIED, ZERO_RESIDUAL,
        STAGNATED, MAX_ITERATIONS
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
                || (fa != 0.0 && fb != 0.0
                    && ((fa > 0) == (fb > 0)))) {
            throw new IllegalArgumentException("No valid bracket");
        }

        int fallbacks = 0;
        for (int i = 1; i <= maxIter; i++) {
            double fx = f.applyAsDouble(x);
            if (!Double.isFinite(fx)) {
                throw new IllegalArgumentException("Nonfinite f(x)");
            }
            if (fx == 0.0) {
                return new Result(Status.ZERO_RESIDUAL, x, 0.0,
                                  i, fallbacks);
            }

            if ((fx > 0) == (fa > 0)) {
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
            if (candidate == x || candidate == a || candidate == b) {
                return new Result(Status.STAGNATED, x, Math.abs(fx),
                                  i, fallbacks);
            }

            double step = Math.abs(candidate - x);
            x = candidate;
            double newFx = f.applyAsDouble(x);
            if (!Double.isFinite(newFx)) {
                throw new IllegalArgumentException("Nonfinite f(new x)");
            }

            double xTol = absXTol
                    + relXTol * Math.max(1.0, Math.abs(x));
            if (Math.abs(newFx) <= fTol && step <= xTol) {
                return new Result(Status.HEURISTIC_CONVERGED, x,
                        Math.abs(newFx), i, fallbacks);
            }
            if ((b - a) / 2.0 <= xTol) {
                double mid = a + (b - a) / 2.0;
                return new Result(Status.BRACKET_CERTIFIED, mid,
                        Math.abs(f.applyAsDouble(mid)), i, fallbacks);
            }
        }
        return new Result(Status.MAX_ITERATIONS, x,
                Math.abs(f.applyAsDouble(x)), maxIter, fallbacks);
    }

    public static void main(String[] args) {
        DoubleUnaryOperator f = x -> x * x - 2.0;
        DoubleUnaryOperator df = x -> 2.0 * x;

        Result r = solve(f, df, 0.0, 2.0, 0.0,
                         1e-12, 1e-12, 1e-12, 100);
        System.out.printf(Locale.ROOT,
                "safeguarded root=%.12f%n", r.x());
        System.out.println("status=" + r.status());
        System.out.println("iterations=" + r.iterations());
        System.out.println("fallbacks=" + r.fallbacks());
        System.out.println("residual <= 1e-12: "
                + (r.residual() <= 1e-12));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SafeguardedNewtonDemo.java
java SafeguardedNewtonDemo
```

Stdout dự kiến:

```text
safeguarded root=1.414213562373
status=HEURISTIC_CONVERGED
iterations=6
fallbacks=1
residual <= 1e-12: true
```

### 10.1. Vì sao fallback hoạt động?

Ban đầu x0=0 nên `df=0`; không được chia. Midpoint [0,2] là1 nên một bước an toàn đưa x vào vùng đạo hàm khác0. Các bước Newton sau đó lần lượt tiến gần √2.

### 10.2. Giới hạn của demo

Trường hợp `HEURISTIC_CONVERGED` là tiêu chí thực dụng: bước và residual nhỏ. Để khẳng định sai số x có một giới hạn chặt, cần chứng minh thêm từ bracket/đạo hàm hoặc số học interval. Nếu một lần tính f bị làm tròn sai dấu, bracket có thể không còn chứng minh toán học nguyên vẹn.

Một solver sản xuất còn nên:

- Theo dõi monotonic progress hoặc **guarded bracket** cẩn thận.
- Kiểm endpoint f(a)=0 hoặc f(b)=0 ngay từ đầu (demo sử dụng dữ liệu không phải nghiệm endpoint).
- Gắn giới hạn thời gian và ngân sách hàm, tránh đánh giá f quá tốn kém.
- Lưu bracket/error estimate khi trả kết quả thay vì chỉ x.
- Sử dụng tiêu chí đạo hàm theo scale thay vì ngưỡng tuyệt đối tùy ý.

## 11. Secant, regula falsi và Brent–Dekker

Không phải lúc nào có thể tính f'(x). Khi ấy **secant** dùng hai điểm liên tiếp:

`x(k+1)=x_k − f(x_k)·(x_k−x(k−1)) / [f(x_k)−f(x(k−1))]`.

Nó xấp xỉ đạo hàm bằng độ dốc dây cung.

### 11.1. Ưu và nhược điểm secant

- Không cần tính đạo hàm phân tích.
- Nghiệm đơn, seed tốt có thể hội tụ **siêu tuyến tính**, bậc khoảng φ=(1+√5)/2≈1.618.
- Không có bảo đảm tự giữ nghiệm trong một bracket.
- Nếu `f(x_k)≈f(x(k−1))`, mẫu nhỏ có thể tạo bước rất lớn hoặc vô hạn.
- Có thể dao động, chia0, gặp vùng ngoài miền xác định.

Phải kiểm mẫu, tính hữu hạn của ứng viên, bước x và residual; đặt budget.

### 11.2. Regula falsi và bảo toàn dấu

**False position/regula falsi** dùng giao của dây cung với trục x, nhưng luôn cập nhật một đầu bracket theo dấu để bảo toàn tồn tại nghiệm.

Đổi lại, một đầu có thể **đứng yên rất lâu**, khiến độ rộng bracket giảm chậm dù residual tại điểm mới có vẻ tốt. Những biến thể Illinois/Pegasus cải thiện hiện tượng đó.

### 11.3. Brent–Dekker

Một phương pháp thực tế thường dùng là **Brent–Dekker**, kết hợp bisection an toàn với các bước nội suy (secant hoặc inverse quadratic interpolation) khi phù hợp. Mục tiêu là tận dụng hội tụ nhanh nhưng vẫn bảo vệ bracket.

Không nhầm Brent–Dekker tìm nghiệm một biến với **Brent cycle detection** trong Pollard rho: hai thuật toán khác mục đích.

### 11.4. Lựa chọn phương pháp

| Điều kiện bài toán | Phương pháp hợp lý |
|---|---|
| Biết bracket đổi dấu, cần chặn sai số x rõ | Bisection/Brent–Dekker |
| Có đạo hàm, seed gần nghiệm đơn, muốn nhanh | Newton |
| Có bracket và đạo hàm nhưng phải chống bước xấu | Safeguarded Newton |
| Không có đạo hàm, hai seed phù hợp | Secant có bảo vệ |
| Có ánh xạ co trên một khoảng bất biến | Lặp điểm bất động với chặn sai số |
| Có nghiệm bội chẵn không đổi dấu | Không áp bisection chuẩn một cách mù quáng |
| Có nhiều nghiệm cần chọn đúng nhánh | Cô lập root/bracket theo điều kiện ứng dụng trước |

## 12. Lặp điểm bất động (*fixed-point iteration*)

Chuyển phương trình về:

`x=g(x)`.

Bắt đầu x0, sinh:

`x(k+1)=g(x_k)`.

Một dạng giải `x²=2` với x>0:

`g(x)=(x+2/x)/2`.

Đây cũng là phép cập nhật Newton cho √2.

### 12.1. Điều kiện co và duy nhất

Giả sử g ánh xạ đoạn đóng I=[a,b] vào chính nó, và tồn tại `0≤q<1` sao cho:

`|g(x)−g(y)|≤q·|x−y|`

với mọi x,y∈I. Khi đó theo định lý điểm bất động Banach:

- Có **một** điểm bất động x* duy nhất trong I.
- Lặp từ mọi x0∈I hội tụ tới x*.
- Có thể chặn sai số bằng khoảng cách giữa các lần lặp.

Điều kiện `g(I)⊆I` rất quan trọng. Không thể chỉ thấy `|g'(x*)|<1` tại đúng nghiệm rồi kết luận mọi seed trong toàn ℝ đều hội tụ.

### 12.2. Chặn sai số hậu nghiệm từ bước

Trong số học thực và dưới giả thiết co q:

`|x*−x_n| ≤ [q/(1−q)]·|x_n−x(n−1)|`.

Đây là chặn sai số của **nghiệm** suy ra từ bước lặp, **nhưng chỉ vì đã có giả thiết co được chứng minh**, không phải vì mọi bước nhỏ đều tốt.

Có thể dừng khi:

`q/(1−q)·|x_n−x(n−1)| ≤ xTol`.

### 12.3. Ví dụ chứng minh q=1/2

Với:

`g(x)=(x+2/x)/2`, I=[1,2],

ta có:

`g'(x)=1/2−1/x²`.

Với x∈[1,2], `g'(x)` nằm trong [-1/2,1/4], nên:

`|g'(x)|≤1/2`.

Đồng thời `g(I)⊆[√2,1.5]⊂[1,2]`. Vì vậy g là ánh xạ co với q=1/2, có nghiệm duy nhất trong I.

Chặn hậu nghiệm đơn giản thành:

`|x*−x_n|≤|x_n−x(n−1)|`.

### 12.4. Lưu ý đặc biệt với double

Chặn trên là định lý trong **số học thực**. Trên double, có thể xảy ra:

`next == current`

chỉ vì **làm tròn**, dù sai số toán học chưa được chứng minh bằng0. Không được đánh giá bound0 và gọi đó là chứng nhận tuyệt đối. Khi stagnation, nên trả trạng thái riêng hoặc dùng đánh giá interval/precision cao hơn.

## 13. Java 17 — điểm bất động với bound và phát hiện stagnation

Trong ví dụ, với ngưỡng `2e-12`, chặn lý thuyết từ bước đã nhỏ sau 5 vòng; với ngưỡng rất chặt `1e-14`, double ngừng thay đổi ở vòng6 và chương trình trả **STAGNATED**, thay vì in chặn bằng0 như thể đã chứng minh nghiệm chính xác.

Lưu **FixedPointErrorEstimateDemo.java**:

```java
import java.util.Locale;
import java.util.function.DoubleUnaryOperator;

public class FixedPointErrorEstimateDemo {
    enum Status { BOUND_ESTIMATE, STAGNATED, ESCAPED, MAX_ITERATIONS }

    record Result(Status status, double x, double estimatedBound,
                  int iterations) {}

    static Result solve(DoubleUnaryOperator g,
                        double initial, double lo, double hi,
                        double q, double tolerance, int maxIter) {
        if (!(lo < hi) || initial < lo || initial > hi
                || q < 0.0 || q >= 1.0
                || !Double.isFinite(q)
                || tolerance <= 0.0 || !Double.isFinite(tolerance)
                || maxIter <= 0) {
            throw new IllegalArgumentException("Invalid inputs");
        }

        double x = initial;
        double lastBound = Double.POSITIVE_INFINITY;
        for (int i = 1; i <= maxIter; i++) {
            double next = g.applyAsDouble(x);
            if (!Double.isFinite(next) || next < lo || next > hi) {
                return new Result(Status.ESCAPED, x, lastBound, i);
            }
            if (next == x) {
                // Không nhận sai số bằng0 chỉ vì double stagnation.
                return new Result(Status.STAGNATED, x, lastBound, i);
            }

            double step = Math.abs(next - x);
            double bound = q / (1.0 - q) * step;
            x = next;
            lastBound = bound;
            if (bound <= tolerance) {
                return new Result(Status.BOUND_ESTIMATE, x, bound, i);
            }
        }

        return new Result(Status.MAX_ITERATIONS, x,
                          lastBound, maxIter);
    }

    public static void main(String[] args) {
        DoubleUnaryOperator g = x -> (x + 2.0 / x) / 2.0;

        Result ok = solve(g, 1.0, 1.0, 2.0,
                          0.5, 2e-12, 100);
        System.out.printf(Locale.ROOT,
                "fixed point=%.12f%n", ok.x());
        System.out.printf(Locale.ROOT,
                "estimated bound=%.3e%n", ok.estimatedBound());
        System.out.println("iterations=" + ok.iterations());
        System.out.println("status=" + ok.status());

        Result strict = solve(g, 1.0, 1.0, 2.0,
                              0.5, 1e-14, 100);
        System.out.println("strict status=" + strict.status());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FixedPointErrorEstimateDemo.java
java FixedPointErrorEstimateDemo
```

Stdout dự kiến:

```text
fixed point=1.414213562373
estimated bound=1.595e-12
iterations=5
status=BOUND_ESTIMATE
strict status=STAGNATED
```

### 13.1. `BOUND_ESTIMATE` có phải chứng chỉ số học máy tuyệt đối?

Không. Công thức bound là kết quả toán học **khi g và các phép lặp chính xác**. Với double, đây là **ước lượng dựa trên lý thuyết co**, có thể bị làm tròn; nếu cần chứng nhận thật sự, phải kiểm cả lỗi đánh giá g bằng interval hoặc phương pháp số học được chứng nhận.

### 13.2. Lỗi thường gặp: chọn g không co

Cùng một phương trình có thể biến đổi thành nhiều dạng x=g(x). Một dạng g có |g'|<1 gần nghiệm sẽ ổn định, trong khi dạng khác có |g'|>1 làm lặp phân kỳ. Vì vậy **chọn phép lặp** là một quyết định thiết kế, không thể lấy một phép biến đổi đại số bất kỳ rồi mặc định hội tụ.

### 13.3. Khi nào bound từ bước là có ý nghĩa?

Chỉ khi có đủ dữ kiện: đoạn I bất biến, Lipschitz q<1 và thuật toán ở trong I. Nếu không biết q, chỉ xét bước nhỏ là **heuristic**, có nguy cơ hội tụ giả.

## 14. Số dấu phẩy động, epsilon máy và ULP

Java `double` dùng IEEE 754 binary64: khoảng 15–17 chữ số thập phân có nghĩa tùy bối cảnh. Các số double không phân bố đều trên trục thực; khoảng cách giữa các số biểu diễn gần x được gọi là **ULP** (*unit in the last place*).

Tại x=1:

`Math.ulp(1.0)=2.220446049250313e−16`.

Một bước `1e−20` quá nhỏ so với ULP này:

`1.0 + 1e−20 == 1.0` ⇒ true.

Đây là **stagnation do làm tròn**, không có nghĩa sai số nghiệm bằng0.

### 14.1. Vì sao số chữ số “đúng” không tăng mãi?

Độ chính xác của double hữu hạn. Khi x gần một nghiệm không thể biểu diễn chính xác như √2, nhiều phép cập nhật cuối cùng cho lại chính x vì giá trị toán học mới nằm giữa hai số double kề nhau.

Nếu tiêu chí dừng quá chặt so với ULP tại thang của nghiệm, solver có thể không đạt yêu cầu dù đang rất gần nghiệm.

### 14.2. `Double.MIN_VALUE` khác epsilon máy

`Double.MIN_VALUE` là số double dương **nhỏ nhất dạng subnormal**, không phải sai số tương đối phổ biến của phép làm tròn tại x≈1.

Để hiểu khoảng cách hai số double gần x, dùng `Math.ulp(x)` hoặc `Math.nextUp(x)` khi cần. Đừng dùng `Double.MIN_VALUE` làm tolerance chung vì nó quá nhỏ cho hầu hết phép tính.

### 14.3. Overflow, underflow, NaN

Một solver phải kiểm:

- `Double.isFinite(x)`, `Double.isFinite(fx)` và derivative khi thích hợp.
- Bước Newton có thể thành `Infinity` khi chia số rất nhỏ.
- Giá trị f có thể overflow hoặc underflow dẫn đến residual có vẻ vô nghĩa.
- `NaN` so sánh `<`, `>`, `==` theo cách dễ làm bỏ lọt nhánh, nên cần validate trước.

### 14.4. Stagnation khác hội tụ

Nếu `x_new==x_old`, một trong các khả năng:

- Đã đạt số double gần nghiệm tốt nhất có thể.
- Bước quá nhỏ do làm tròn.
- Hàm/đạo hàm tính sai.
- Thuật toán đang kẹt ở điểm **không phải nghiệm**.

Phải xem residual, bracket, giới hạn độ chính xác và loại trạng thái, không chỉ một phép so bằng.

## 15. Java 17 — residual nhỏ nhưng nghiệm sai, và stagnation

Chương trình sau cố ý dùng hai phương trình có cùng dạng nghiệm tuyến tính nhưng hệ số tỉ lệ rất khác. Nó chứng minh không nên dùng **chỉ một fTol tuyệt đối** để xác định độ chính xác nghiệm.

Lưu **ResidualConditioningDemo.java**:

```java
import java.util.Locale;

public class ResidualConditioningDemo {
    public static void main(String[] args) {
        // Nghiệm đúng f_flat(x)=0 là x*=1000.
        double flatApprox = 0.0;
        double flatResidual = Math.abs(1e-12
                * (flatApprox - 1000.0));
        double flatError = Math.abs(flatApprox - 1000.0);

        System.out.printf(Locale.ROOT,
                "flat residual=%.3e, true error=%.1f%n",
                flatResidual, flatError);
        System.out.println("flat residual <= 1e-8: "
                + (flatResidual <= 1e-8));
        System.out.println("flat error <= 1e-8: "
                + (flatError <= 1e-8));

        // Nghiệm đúng f_steep(x)=0 là x*=1.
        double steepApprox = 1.0 + 1e-9;
        double steepResidual = Math.abs(1e12
                * (steepApprox - 1.0));
        double steepError = Math.abs(steepApprox - 1.0);
        System.out.printf(Locale.ROOT,
                "steep residual=%.3e, true error=%.3e%n",
                steepResidual, steepError);

        System.out.printf(Locale.ROOT,
                "ulp(1.0)=%.3e%n", Math.ulp(1.0));
        System.out.println("1.0+1e-20==1.0: "
                + ((1.0 + 1e-20) == 1.0));

        double left = Math.pow(-1.0 - 1.0, 2);
        double right = Math.pow(3.0 - 1.0, 2);
        System.out.println("even root, same endpoint sign: "
                + (left > 0 && right > 0));

        double exactZeroRoot = 0.0;
        System.out.println("relative error at zero defined: "
                + (exactZeroRoot != 0.0));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ResidualConditioningDemo.java
java ResidualConditioningDemo
```

Stdout dự kiến:

```text
flat residual=1.000e-09, true error=1000.0
flat residual <= 1e-8: true
flat error <= 1e-8: false
steep residual=1.000e+03, true error=1.000e-09
ulp(1.0)=2.220e-16
1.0+1e-20==1.0: true
even root, same endpoint sign: true
relative error at zero defined: false
```

**Ý nghĩa:** Residual nhỏ có thể đi kèm sai số nghiệm lớn; residual lớn có thể đi kèm sai số nghiệm nhỏ; không đổi dấu bracket không chứng minh không có nghiệm; và số double có giới hạn bước biểu diễn.

## 16. Mô hình hội tụ và tốc độ hội tụ

Đặt `e_k=|x_k−x*|`.

### 16.1. Hội tụ tuyến tính

Nếu gần nghiệm:

`e(k+1)≈C·e_k`, với 0<C<1,

thì sai số giảm theo hệ số cố định, ví dụ mỗi vòng chia2. Bisection giảm **độ dài bracket** chính xác một nửa trong số học thực; Newton gần nghiệm bội thường chỉ tuyến tính.

### 16.2. Hội tụ siêu tuyến tính và bậc hai

- **Secant** trên nghiệm đơn với điều kiện trơn và seed đủ gần: bậc xấp xỉ1.618.
- **Newton** trên nghiệm đơn, đủ trơn, seed đủ gần: bậc hai, `e(k+1)≈C e_k²`.

Không so số vòng lặp thuần túy mà quên chi phí đánh giá f, f' và các phép số lớn. Một vòng Newton có thể tốn hơn bisection, và phương pháp nhanh trong một ví dụ có thể không bền vững trên dữ liệu khác.

### 16.3. Bước nhỏ không chứng minh hội tụ đúng

Nếu x_k gần điểm mà đạo hàm nhỏ, một phương pháp có thể tạo bước nhỏ nhưng residual không đạt ngưỡng phù hợp, hoặc f được nhân hệ số khiến residual đánh lừa. **Hội tụ của dãy số** tới một giới hạn cũng chưa chắc giới hạn ấy là nghiệm của phương trình.

### 16.4. Chọn thuật toán theo bảo đảm thay vì chỉ tốc độ

Nếu ưu tiên có **bằng chứng interval**, dùng phương pháp giữ bracket. Nếu ưu tiên tốc độ và có derivative/seed tốt, dùng Newton với safeguard. Nếu biết ánh xạ co, có thể suy chặn sai số từ bước. Nếu không có bất kỳ bảo đảm nào, phải báo kết quả dưới dạng **ước lượng/heuristic** rõ ràng.

## 17. Thiết kế tiêu chí dừng theo trạng thái

Một API solver tốt không chỉ trả `double x`. Nên trả một cấu trúc:

`Result { x, status, iterations, residual, step, bracket?, errorEstimate?, evaluations }`.

Ví dụ trạng thái:

| Status | Khi nào dùng? | Có thể gọi “đã giải”? |
|---|---|---|
| `BRACKET_CERTIFIED` | Bracket hợp lệ và sai số theo độ rộng đạt tol | Có, **theo giả thiết bảo đảm bracket** |
| `BOUND_ESTIMATE` | Chặn hậu nghiệm từ ánh xạ co đạt tol | Có, theo giả thiết co/số học |
| `HEURISTIC_CONVERGED` | Bước x nhỏ và residual nhỏ | Đạt tiêu chí thực dụng, **không tự là chứng chỉ** |
| `ZERO_RESIDUAL` | f(x) trả0.0 trong floating | Chỉ bảo đảm phép đánh giá đang dùng cho0 |
| `STAGNATED` | Không còn cập nhật double mới | Chưa chắc đạt mục tiêu |
| `MAX_ITERATIONS` | Hết vòng được phép | Chưa kết luận |
| `INVALID_BRACKET` | Không có dấu hai đầu trái nhau | Không suy “không có nghiệm” |
| `NONFINITE` | NaN/Infinity/miền xác định sai | Lỗi số học/input |
| `DIVERGED` hoặc `ESCAPED` | Không còn nằm trong miền cho phép | Không đạt |

### 17.1. Thiết kế vòng lặp dừng an toàn

```text
validate inputs and domain
initialize bracket / initial guesses
for k=1..maxIterations:
    calculate candidate with finite checks
    if invariant broken: try a safe fallback or return failure
    evaluate residual and candidate step
    if certified interval / proven error bound holds:
        return CERTIFIED with bound
    if practical step AND properly scaled residual hold:
        return HEURISTIC_CONVERGED
    if candidate == current in floating:
        return STAGNATED
return MAX_ITERATIONS
```

Thứ tự kiểm tra có thể điều chỉnh cho phương pháp cụ thể, nhưng **không** được bỏ qua tính đúng của invariant để đạt một nhãn `CONVERGED` cho đẹp.

### 17.2. Sai số và ngân sách là hai trục khác nhau

`maxIterations=100` chỉ là **giới hạn tài nguyên**, không phải mức chính xác. Hết vòng phải trả `MAX_ITERATIONS`, không được gắn trạng thái thành công chỉ vì đã chạy đủ100.

Một hệ thống còn có thể giới hạn:

- Tổng số lần đánh giá hàm/đạo hàm.
- Thời gian thực thi.
- Số lần fallback.
- Kích thước đầu vào, memory, precision.

### 17.3. Không che tình huống overflow

Nếu f(x) ra NaN/Infinity, solver phải trả lỗi hoặc sử dụng biến đổi toán học hợp lệ để tránh overflow. Không so NaN với fTol rồi đi tiếp một cách ngầm định; mọi so sánh với NaN đều có thể làm sai điều kiện điều khiển.

## 18. Chọn độ chính xác theo ứng dụng

### 18.1. Ví dụ thời điểm chạm ngưỡng

Giả sử x là **thời gian giây**, cần đáp án sai dưới1 millisecond:

`aTol=0.001 s`.

Nếu thời gian vận hành hàng triệu giây, thêm rTol nhỏ có thể hợp lý tùy yêu cầu, nhưng không nên vô tình cho rTol nới lỏng sai số vượt ngưỡng1ms của nghiệp vụ.

### 18.2. Ví dụ tỷ lệ không thứ nguyên

Nếu x là xác suất trong [0,1], `aTol=1e-8` đã có ý nghĩa rõ; rTol có thể không thêm nhiều vì |x|≤1. Nếu nghiệm gần0, relative-only sẽ thất bại.

### 18.3. Ví dụ nghiệm có đơn vị rất lớn

Nếu x đo bằng khoảng cách địa lý cỡ10^9 mét, `aTol=1e-12 m` có thể vượt mức đáng tin của double và cả mô hình đo. Cần xem **độ chính xác dữ liệu** trước khi áp tol siêu nhỏ.

### 18.4. Ví dụ số liệu có nhiễu

Một mô hình f đến từ đo đạc với sai số đầu vào có thể chỉ cho phép xác định nghiệm tới0.01. Solver trả `residual≈1e-15` không làm thông tin vật lý tốt hơn; đó là **độ chính xác thuật toán** khác với **độ chính xác mô hình/dữ liệu**.

### 18.5. Chọn nghiệm theo x_ref dưới bất định

Nếu có hai nghiệm được cô lập bởi bracket I1,I2, muốn chọn nghiệm gần x_ref, có thể chặn khoảng cách nhỏ nhất/lớn nhất từ x_ref tới từng bracket. Nếu các khoảng đánh giá **chồng lấn**, chưa chắc biết nghiệm nào gần hơn; nên tiếp tục thu hẹp bracket hoặc báo không phân định được thay vì chọn chỉ từ midpoint làm tròn.

## 19. Kiểm thử độc lập và xác minh hậu điều kiện

Không chỉ nhìn stdout đẹp của một vài ví dụ. Cần các phép kiểm độc lập:

### 19.1. Oracle có nghiệm biết trước

Sinh phương trình tuyến tính:

`f(x)=s·(x−r)` với `s≠0`.

Nghiệm **biết chính xác trong số học lý tưởng** là r. Chọn bracket `[r−1,r+2]`; bisection phải giữ nghiệm trong bracket và chặn sai số cuối không quá nửa độ rộng.

Thử cả s>0 và s<0 để bắt lỗi cập nhật dấu.

### 19.2. Oracle căn bậc hai

Cho `f(x)=x²−A`, với A>0 và bracket [0,b] đủ rộng. So x̂ với `Math.sqrt(A)` **như oracle số thực dấu phẩy động**, đồng thời kiểm bracket chứa nghiệm và residual có giá trị hữu hạn.

Nhớ rằng `Math.sqrt` cũng tính bằng double, không phải chứng chỉ toán học tuyệt đối. Đối với giá trị A nhỏ có thể có underflow và vấn đề thang đo.

### 19.3. Oracle hàm mũ

Cho `f(x)=exp(x)−T` với T>0, nghiệm x*=ln(T). Dùng bracket có dấu, so với `Math.log(T)`, đồng thời kiểm invariant về dấu sau mỗi bước. Các phép exp/log gần biên có giới hạn số học riêng nên chọn dữ liệu vừa phải trong bộ test.

### 19.4. Phương pháp đối chiếu độc lập

- So bisection với Newton có safeguard trên cùng một nghiệm đơn.
- So f(x̂) với phần dư đánh giá lại theo cách ít mất độ chính xác nếu có.
- Nếu cần chứng chỉ, dùng interval arithmetic hoặc kiểm f dấu có làm tròn hướng đúng.
- Với fixed point, kiểm I bất biến, q<1, và phát hiện stagnation trước khi nói bound0.
- Với hàm có nhiều nghiệm, thử **các bracket khác nhau** để bảo đảm chọn đúng nhánh.

### 19.5. Những bất biến không được phá

Trong bisection:

- `a≤b`, b−a hữu hạn.
- f(a),f(b) vẫn trái dấu nếu không gặp nghiệm đánh giá được0.
- Độ rộng mới **không tăng**, thông thường giảm một nửa theo số học thực.
- Trước khi trả `BRACKET_CERTIFIED`, `halfWidth≤xTol`.

Trong Newton có bảo vệ:

- Candidate luôn nằm trong bracket hoặc fallback có giải thích.
- Không chia cho derivative0.
- Không cập nhật bằng NaN/Infinity.
- Không gọi `HEURISTIC_CONVERGED` nếu một trong hai kiểm step/residual thất bại.

## 20. Các tình huống biên cần kiểm

| Trường hợp | Kết quả mong đợi |
|---|---|
| f(a)=0 | Trả ZERO_RESIDUAL tại endpoint (theo đánh giá f) |
| f(b)=0 | Tương tự |
| f(a),f(b) trái dấu, liên tục | Có ít nhất một nghiệm trong bracket |
| f(a),f(b) cùng dấu, có hai nghiệm | Bisection chuẩn từ chối bracket, không kết luận vô nghiệm |
| Nghiệm bội chẵn | Có thể không đổi dấu |
| Nghiệm gần0 | Dùng aTol, không relative-only |
| Nghiệm cỡ10^12 | Xét ULP/thang đo khi đặt aTol |
| f được nhân hệ số10^12 | Root không đổi, residual thay đổi mạnh |
| f' rất nhỏ | Residual không chặn tốt sai số nghiệm |
| f'=0 | Không chia Newton; fallback hoặc báo lỗi |
| Newton bước ra ngoài bracket | Bisection fallback |
| Newton seed0 trong f=x²−2 | Đạo hàm0, cần fallback |
| Newton f=x³−2x+2, seed0 | Có chu kỳ 0↔1 nếu không bảo vệ |
| f/f' trả NaN hoặc Infinity | Dừng/báo lỗi số học |
| Bracket hết độ phân giải double | STAGNATED hoặc trả chứng nhận đã đạt |
| maxIter quá ít | MAX_ITERATIONS, không phải CONVERGED |
| fixed point q≥1 | Không áp chặn co |
| fixed point I không bất biến | Không áp định lý co trên I |
| step==0 do rounding | Không gọi bound0 tuyệt đối |
| f(x)=x²−2 | Dùng bracket [1,2] cho nghiệm dương |
| f(x)=(x−1)(x−3) | Bracket riêng từng nghiệm |
| f(x)=(x−1)² | Không đổi dấu dù có nghiệm |
| In 12 chữ số | Không suy ra sai số nhỏ hơn10^-12 |

## 21. Những lỗi thường gặp và cách tránh

### Lỗi 1 — Không xác định nghiệm cần chọn

Một phương trình có thể có nhiều nghiệm; chọn bracket hoặc ràng buộc nhánh trước.

### Lỗi 2 — Coi bracket đổi dấu là bảo đảm duy nhất

Đổi dấu với f liên tục bảo đảm ít nhất **một** nghiệm. Muốn duy nhất, thêm điều kiện đơn điệu hoặc cô lập từng nghiệm.

### Lỗi 3 — Coi bracket không đổi dấu là vô nghiệm

Hai nghiệm hoặc nghiệm bội chẵn có thể khiến hai đầu cùng dấu.

### Lỗi 4 — Dừng chỉ vì residual nhỏ

Hàm phẳng có thể cho residual nhỏ nhưng error x rất lớn.

### Lỗi 5 — Dừng chỉ vì bước nhỏ

Bước có thể nhỏ do stagnation, clamp hoặc hội tụ tới điểm không phải nghiệm.

### Lỗi 6 — Dùng fTol tuyệt đối giống nhau cho mọi phương trình

Nhân f với hệ số làm residual đổi mà nghiệm không đổi; cần scaleF thích hợp.

### Lỗi 7 — Nhầm forward error với residual

`|x̂−x*|` đo sai số biến; `|f(x̂)|` đo phần dư của phương trình.

### Lỗi 8 — Gọi residual là chứng chỉ root error mà không có điều kiện

Muốn chặn từ residual cần derivative lower bound hoặc định lý khác.

### Lỗi 9 — Chia sai số tương đối cho nghiệm0

Relative error không xác định khi x*=0. Dùng tolerance hỗn hợp theo scale.

### Lỗi 10 — Chọn aTol nhỏ hơn khả năng phân giải double

Có thể khiến solver stagnated. Xét `Math.ulp(x)` và scale.

### Lỗi 11 — Dùng Double.MIN_VALUE như epsilon máy

Đó là số subnormal nhỏ nhất, không phải ULP tại x≈1.

### Lỗi 12 — Không chặn maxIterations

Vòng lặp có thể chạy vô hạn khi không hội tụ hoặc không còn tiến triển.

### Lỗi 13 — Hết vòng mà vẫn in CONVERGED

Trả MAX_ITERATIONS/Inconclusive theo hợp đồng API.

### Lỗi 14 — Không kiểm NaN/Infinity

Các phép so với NaN có thể bỏ qua logic dừng. Validate trước mỗi bước.

### Lỗi 15 — Tính midpoint `(a+b)/2` gây overflow

Dùng cách tính có guard cho chiều rộng và miền đầu vào.

### Lỗi 16 — `mid==a` hoặc `mid==b` nhưng tiếp tục chia đôi

Đã mất tiến triển số học; phải dừng hay nâng precision.

### Lỗi 17 — Nhân f(a)*f(b) để kiểm đổi dấu

Có thể overflow/underflow. So dấu trực tiếp.

### Lỗi 18 — Không đảm bảo f liên tục trong bracket

Đổi dấu qua **điểm gián đoạn** không chứng minh có nghiệm. Ví dụ `f(x)=1/x` trên [-1,1] có dấu khác nhau nhưng không có nghiệm; còn không xác định tại0.

### Lỗi 19 — Không kiểm miền xác định

Log, sqrt, phân thức có miền hợp lệ. Không cho Newton ra khỏi miền rồi coi NaN là hội tụ.

### Lỗi 20 — Newton chia cho derivative0

Phải fallback hoặc báo không dùng được bước này.

### Lỗi 21 — Newton bước quá lớn, ra ngoài bracket

Bước tiếp tuyến không tự bảo đảm giữ nghiệm. Safeguard bằng bracket/trust region/line search.

### Lỗi 22 — Newton dao động mà không phát hiện

Ví dụ 0↔1 cho f=x³−2x+2. Theo dõi residual, bước, chu kỳ hoặc giữ bracket.

### Lỗi 23 — Hứa hội tụ bậc hai cho nghiệm bội

Với f=(x−1)², Newton chỉ tuyến tính từ seed hợp lệ.

### Lỗi 24 — Secant chia mẫu gần0

`f(x_k)−f(x(k−1))` nhỏ gây bước cực lớn. Có guard và fallback.

### Lỗi 25 — Dùng fixed-point bound khi q≥1

Công thức q/(1−q) chỉ có ý nghĩa trong giả thiết co q<1.

### Lỗi 26 — Quên g(I) nằm trong I

Không thể áp định lý co trên một đoạn nếu g thoát ra khỏi đoạn đó.

### Lỗi 27 — Khi double stagnation thì gán error bound=0

`x_new==x_old` có thể do làm tròn; không suy đã giải chính xác.

### Lỗi 28 — Nhầm độ chính xác mô hình với độ chính xác thuật toán

Dữ liệu đo nhiễu1% không tự trở nên chính xác 10^-12 nhờ lặp nhiều hơn.

### Lỗi 29 — Đếm iteration thay cho đo chất lượng

10 bước Newton không luôn tốt hơn 40 bước bisection; phải xem residual, root error bound, tài nguyên và nhánh đúng.

### Lỗi 30 — Chỉ kiểm một ví dụ căn hai

Cần test seed khác, hàm phẳng/dốc, nghiệm0, nghiệm bội, nhiều nghiệm, discontinuity và stagnation.

### Lỗi 31 — In nhiều chữ số rồi gọi là chính xác

Định dạng output khác với bằng chứng sai số.

### Lỗi 32 — Không trả trạng thái lỗi cụ thể

Nếu chỉ trả một x, người gọi không phân biệt thành công, hết budget hay NaN.

### Lỗi 33 — Chọn nghiệm theo residual thấp nhất mà bỏ ràng buộc

Hai nghiệm đều residual0; lựa chọn cần tiêu chí nhánh vật lý hoặc tham chiếu.

### Lỗi 34 — Không tính đến sai số khi so khoảng cách giữa các nghiệm

Nếu hai ứng viên gần x_ref với mức chênh nhỏ hơn sai số hiện có, chưa thể quyết định ổn định.

### Lỗi 35 — Áp dụng chặn sai số derivative khi f' qua0

Chặn |f'|≥m>0 phải đúng trên **toàn đoạn liên quan**, không chỉ tại một điểm.

### Lỗi 36 — Gọi `ZERO_RESIDUAL` trong double là nghiệm thực chứng nhận

f̂(x) có thể bằng0 do làm tròn hoặc cancellation; nếu đòi chứng nhận tuyệt đối cần phương pháp số học thích hợp.

## 22. Bài tập thực hành có đáp án

### Bài 1 — Forward error

x*=1000, x̂=1000.001. Sai số tuyệt đối?

**Đáp án:** 0.001.

### Bài 2 — Relative error

Với số ở bài1, sai số tương đối?

**Đáp án:** 0.001/1000=10^-6.

### Bài 3 — Nghiệm0

Có thể tính `|x̂−x*|/|x*|` khi x*=0 không?

**Đáp án:** không; mẫu0. Dùng aTol/tolerance hỗn hợp.

### Bài 4 — Residual

f(x)=x²−2, x̂=1.4, tính f(x̂).

**Đáp án:** -0.04, residual0.04.

### Bài 5 — Chọn nhánh

f=(x−1)(x−3), nghiệm trong [0,1.5]?

**Đáp án:** 1.

### Bài 6 — Chọn nhánh khác

Cùng f, nghiệm trong [2.2,4]?

**Đáp án:** 3.

### Bài 7 — Hai đầu cùng dấu

Tại sao [0,4] không phải sign bracket cho f ở bài5?

**Đáp án:** f(0)=3, f(4)=3; có hai nghiệm giữa nhưng hai đầu cùng dấu.

### Bài 8 — Bội chẵn

f=(x−1)², hai đầu0 và2 đổi dấu không?

**Đáp án:** không; f(0)=f(2)=1 dù nghiệm1 tồn tại.

### Bài 9 — IVT

Điều kiện cơ bản nào để đổi dấu bảo đảm tồn tại nghiệm?

**Đáp án:** f **liên tục** trên bracket và hai đầu trái dấu.

### Bài 10 — Nghiệm duy nhất

Có thể bảo đảm duy nhất thêm bằng điều kiện nào?

**Đáp án:** f đơn điệu nghiêm ngặt trên bracket.

### Bài 11 — Bisection bound

Braket [1,2] còn độ rộng0.001. Sai số midpoint tối đa theo bracket?

**Đáp án:** 0.0005.

### Bài 12 — Nửa khoảng

Sau k bước bisection lý tưởng từ độ rộng L0, độ rộng còn?

**Đáp án:** L0/2^k.

### Bài 13 — Residual và đạo hàm

Nếu `|f(x̂)|≤10^-6`, `|f'|≥2` trên đoạn thích hợp, chặn error?

**Đáp án:** ≤5·10^-7.

### Bài 14 — Hàm phẳng

f=10^-12(x−1000), x̂=0, residual?

**Đáp án:** 10^-9, nhưng sai số nghiệm1000.

### Bài 15 — Hàm dốc

f=10^12(x−1), x̂≈1+10^-9, residual?

**Đáp án:** khoảng10^3.

### Bài 16 — Cập nhật Newton

f=x²−2, x0=1, x1?

**Đáp án:** 1.5.

### Bài 17 — Newton bước tiếp

Từ x1=1.5, cập nhật Newton cho căn2?

**Đáp án:** 1.4166666666666667.

### Bài 18 — Đạo hàm0

Tại x0=0, f=x²−2 có f'(0)=?

**Đáp án:** 0; không được chia Newton, cần fallback.

### Bài 19 — Newton dao động

f=x³−2x+2, seed0 cho hai x tiếp theo?

**Đáp án:** x1=1,x2=0, chu kỳ.

### Bài 20 — Nghiệm bội

Newton cho f=(x−1)² từ x≠1 có công thức?

**Đáp án:** x_new=(x+1)/2, hội tụ tuyến tính.

### Bài 21 — Secant

Secant cần đạo hàm phân tích không?

**Đáp án:** không, ước lượng đạo hàm bằng hai f values.

### Bài 22 — Secant denominator

Nếu f(x_k)=f(x(k−1)), điều gì nguy hiểm?

**Đáp án:** mẫu0 trong công thức; phải fallback/đổi cặp.

### Bài 23 — Fixed point

Điều kiện Lipschitz q để là ánh xạ co?

**Đáp án:** 0≤q<1 trên một đoạn I bất biến.

### Bài 24 — Bound q=1/2

Nếu |x_n−x(n−1)|=10^-5, bound hậu nghiệm?

**Đáp án:** ≤[0.5/(1−0.5)]10^-5=10^-5 trong số học thực.

### Bài 25 — Stagnation

`1.0+1e-20==1.0` trong double có true không?

**Đáp án:** true, vì bước quá nhỏ so với ULP tại1.

### Bài 26 — ULP

`Math.ulp(1.0)` khoảng bao nhiêu?

**Đáp án:** 2.220446049250313e-16.

### Bài 27 — Relative-only

Vì sao relative-only không ổn khi nghiệm gần0?

**Đáp án:** ngưỡng quá nhỏ hoặc đúng0; cần aTol và scale.

### Bài 28 — maxIter

Đã hết maxIter nhưng chưa đạt tol; status nào?

**Đáp án:** MAX_ITERATIONS, không phải CONVERGED.

### Bài 29 — Sai nhánh

Newton trả một nghiệm có residual≈0 nhưng ngoài miền vật lý cho phép. Có hợp lệ không?

**Đáp án:** không cho bài toán ứng dụng; phải kiểm ràng buộc nhánh.

### Bài 30 — Đánh giá chính xác

Tại sao in 12 chữ số không chứng minh đạt sai số10^-12?

**Đáp án:** format chỉ hiển thị số đã làm tròn; cần chặn sai số/điều kiện dừng riêng.

### Bài 31 — Khi nào `|f(x)|/m` là chặn error?

**Đáp án:** khi có nghiệm và |f'|≥m>0 trên toàn đoạn giữa x và nghiệm, với giả thiết khả vi thích hợp.

### Bài 32 — Không liên tục

f(x)=1/x trên [-1,1] có đổi dấu. Có nghiệm không?

**Đáp án:** không; f không xác định/không liên tục tại0, nên IVT không áp dụng.

### Bài 33 — Precision và dữ liệu

Nếu dữ liệu đo chỉ chính xác0.01, chạy Newton tới residual10^-15 có nâng độ chính xác dữ liệu không?

**Đáp án:** không; đó là giới hạn của mô hình/đo đạc.

### Bài 34 — Kết quả bằng0 trong double

f̂(x)=0.0 có nhất thiết nghĩa f(x)=0 toán học?

**Đáp án:** không; có thể do rounding/cancellation.

### Bài 35 — Chọn phương pháp

Có bracket đổi dấu và cần sai số x xác minh; ưu tiên phương pháp nào?

**Đáp án:** bisection hoặc Brent–Dekker với bracket bảo toàn và sai số theo độ rộng.

## 23. Checklist thực hành

1. Đã xác định **phương trình cần giải**, miền xác định và đơn vị?
2. Đã biết cần **nghiệm nào** khi có nhiều nghiệm?
3. Có cô lập nghiệm theo bracket hoặc điều kiện vật lý?
4. Có kiểm f liên tục nếu dùng định lý giá trị trung gian?
5. Có thêm điều kiện duy nhất nếu cần đúng một nhánh?
6. Đã phân biệt forward error, relative error và residual?
7. Có xử lý nghiệm0 mà không chia relative error cho0?
8. Tolerance có đơn vị và thang đo phù hợp?
9. Có xem độ chính xác dữ liệu/mô hình trước khi chọn tol?
10. Có hiểu residual nhỏ không tự suy error nhỏ?
11. Nếu dùng chặn residual/m, đã chứng minh m>0?
12. Có kiểm nghiệm bội hoặc đạo hàm gần0?
13. Bisection có giữ hai đầu dấu trái nhau sau mỗi bước?
14. Có kiểm f endpoint=0 một cách rõ ràng?
15. Có tránh nhân f(a)*f(b) gây overflow/underflow?
16. Midpoint có tránh overflow và kiểm stagnation?
17. Có dừng trên **nửa độ rộng bracket**, không nhầm độ rộng?
18. Có kiểm số vòng tối đa và trạng thái lỗi?
19. Newton có kiểm derivative0 và NaN/Infinity?
20. Newton bước ra ngoài bracket có fallback?
21. Secant có kiểm mẫu `f_k−f_(k−1)`?
22. Có tránh báo hội tụ dựa chỉ step nhỏ?
23. Có tránh báo hội tụ dựa chỉ residual nhỏ?
24. Fixed point có I bất biến và q<1?
25. Bound từ fixed point có nêu giả thiết số học thực?
26. Nếu `x_new==x_old`, có trả STAGNATED khi chưa chứng nhận?
27. Có kiểm ULP ở scale của nghiệm?
28. Có trả x, residual, iterations, status và error estimate?
29. Có kiểm đúng nhánh sau khi thuật toán kết thúc?
30. Có kiểm các input NaN, Infinity, miền xác định sai?
31. Có so với oracle nghiệm biết trước (linear/quadratic)?
32. Có thử hàm phẳng và hàm dốc để phát hiện residual-only?
33. Có thử nhiều nghiệm, nghiệm bội, nghiệm0?
34. Có thử Newton dao động và derivative0?
35. Có test maxIter ít, tolerance quá chặt, bracket không đổi dấu?
36. Có phân biệt `HEURISTIC_CONVERGED` và chứng nhận bracket?
37. Nếu cần bảo đảm tuyệt đối, có dùng interval/robust evaluation?
38. Có benchmark số lần đánh giá f/df thay vì chỉ đếm iterations?

**Kết luận:** “Tìm nghiệm gần đúng” không chỉ là lặp đến khi một số nhỏ. Phải **chọn đúng nhánh nghiệm**, xác định **sai số cần kiểm soát** (x hay f), hiểu **độ nhạy** của phương trình và dùng tiêu chí dừng **có ý nghĩa theo thang đo**. Bisection cung cấp chặn sai số từ bracket; Newton/secant cho tốc độ cao nhưng cần safeguard; fixed point cho chặn hậu nghiệm khi chứng minh ánh xạ co. Residual nhỏ, step nhỏ, hoặc `f(x)==0.0` trong floating **đều không tự động là chứng chỉ nghiệm toán học chính xác**. Luôn trả trạng thái hội tụ, chặn sai số hoặc lý do dừng rõ ràng.

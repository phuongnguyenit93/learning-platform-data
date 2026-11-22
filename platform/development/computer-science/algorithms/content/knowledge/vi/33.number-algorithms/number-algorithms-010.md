# Hạ gradient cho bài toán tối ưu khả vi

**Hạ gradient (gradient descent)** là kỹ thuật giải bài toán tối ưu khả vi bằng cách lặp lại phép cập nhật các biến theo **hướng ngược gradient** của hàm mục tiêu. Đối với hàm đủ trơn, bước đi nhỏ theo hướng này làm giảm giá trị hàm; tuy nhiên muốn có bảo đảm hội tụ phải xét **độ lớn bước, tính trơn, tính lồi và điều kiện dừng**. Trong lập trình Java, việc kiểm tra gradient, xử lý số thực không hữu hạn và xác minh kết quả bằng nghiệm giải tích cũng quan trọng như chính vòng lặp tối ưu.

Bài thuộc nhóm **Thuật toán số** của Computer Science Algorithms. Nội dung trình bày bài toán tối ưu nhiều biến, đạo hàm riêng và gradient, descent lemma và điều kiện learning rate, bước cố định và **Armijo backtracking**, hội tụ trong bài lồi/lồi mạnh/không lồi, hồi quy ridge, kiểm tra gradient bằng sai phân hữu hạn, quy tắc dừng, mã **Java 17+** tự chạy cùng phép kiểm thử độc lập, tình huống sai và bài tập có lời giải.

## 1. Mô hình bài toán và gradient

Cho một hàm thực:

`f: R^d → R`.

Mục tiêu tối ưu không ràng buộc là tìm:

`x* ∈ argmin_(x∈R^d) f(x)`.

Vectơ biến `x=(x₁,…,x_d)` có d tọa độ; `f(x)` là một số thực. Nếu f khả vi, gradient tại x là vectơ đạo hàm riêng:

`∇f(x)=[∂f/∂x₁,…,∂f/∂x_d]ᵀ`.

Với một hướng v có chuẩn Euclid bằng 1, đạo hàm theo hướng:

`D_v f(x)=∇f(x)ᵀv`.

Theo Cauchy–Schwarz, hướng làm đạo hàm theo hướng nhỏ nhất là:

`v=−∇f(x)/||∇f(x)||₂`,

khi gradient khác 0. Vì thế **−gradient** là hướng giảm dốc nhất **cục bộ theo chuẩn Euclid**. Kết luận này không nói rằng đi một bước dài tùy ý theo hướng đó sẽ luôn làm f giảm.

**Ví dụ một biến.** Cho `f(x)=(x−3)²`. Ta có `f'(x)=2(x−3)`. Tại x=0, f'(0)=−6 nên một bước theo `−f'(0)` sẽ tăng x, tiến về nghiệm tối ưu x*=3.

**Ví dụ hai biến.** Cho:

`f(x,y)=(x−3)²+2(y+2)²`.

Gradient:

`∇f(x,y)=[2(x−3),4(y+2)]ᵀ`.

Điểm tối ưu toàn cục là (3,−2) với f*=0. Hai biến có độ cong khác nhau, nên một bước học an toàn cần tính đến hướng cong hơn.

### Định nghĩa hai thuật ngữ

- **Điểm dừng (stationary point):** `∇f(x)=0`. Trong bài không lồi, điểm dừng có thể là cực tiểu, cực đại hoặc yên ngựa.
- **Nghiệm tối ưu toàn cục:** điểm x* sao cho `f(x*)≤f(x)` với mọi x thuộc miền. Không được đồng nhất hai khái niệm.

## 2. Công thức hạ gradient và ý nghĩa learning rate

Tại vòng thứ k:

`g_k=∇f(x_k)`,

`x_(k+1)=x_k−η_k g_k`,

với `η_k>0` là **learning rate / step size**. Dấu **trừ** là quan trọng; viết dấu cộng sẽ thành gradient ascent, tức đi theo hướng tăng f ở lân cận.

Một lần cập nhật yêu cầu:

1. Tính gradient tại **x hiện tại**.
2. Chọn learning rate.
3. Tính toàn bộ tọa độ của x mới **đồng thời** từ x cũ.
4. Đánh giá tiêu chí dừng hoặc tiếp tục.

**Không được cập nhật x[0] rồi dùng x[0] mới để tính gradient cho x[1]** nếu công thức đang yêu cầu một gradient đồng bộ tại x_k. Hãy tính gradient vào mảng riêng trước khi thay x.

### Ví dụ tính tay với η=0.25

Tại (0,0), gradient là (−6,8). Do đó:

`(x₁,y₁)=(0,0)−0.25(−6,8)=(1.5,−2)`.

Giá trị mục tiêu giảm từ:

`f(0,0)=9+8=17`

xuống:

`f(1.5,−2)=2.25`.

Các bước tiếp theo:

| Bước k | x_k | y_k | f(x_k,y_k) |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 17 |
| 1 | 1.5 | −2 | 2.25 |
| 2 | 2.25 | −2 | 0.5625 |
| 3 | 2.625 | −2 | 0.140625 |
| 4 | 2.8125 | −2 | 0.03515625 |
| 5 | 2.90625 | −2 | 0.0087890625 |

Từ bước 1, y=−2 giữ nguyên. Tọa độ x thỏa `x_(k+1)=0.5x_k+1.5`, nên:

`x_k=3−3·(1/2)^k`.

Dãy tiến gần 3 nhưng không chạm đúng 3 sau hữu hạn bước trong trường hợp đang xét.

### Bước quá lớn có thể làm tăng loss

Nếu từ (0,0) dùng `η=1`:

`(x₁,y₁)=(6,−8)`,

`f(6,−8)=9+72=81>17`.

Hướng vẫn là −gradient, nhưng bước quá xa vượt qua điểm tối ưu. Vì vậy **hướng đúng không thay thế được lựa chọn độ dài bước phù hợp**.

## 3. Cách tính gradient đúng

Gradient là đạo hàm của **hàm mục tiêu cụ thể**, không phải chính giá trị f(x), cũng không phải một đạo hàm tùy ý.

Các quy tắc cần nhớ:

- `d(x²)/dx=2x`.
- `d((x−a)²)/dx=2(x−a)`.
- `d((1/2)(x−a)²)/dx=x−a`.
- `d(exp x)/dx=exp x`.
- `d(log x)/dx=1/x`, x>0.
- `d(sin x)/dx=cos x`.
- `d[g(h(x))]/dx=g'(h(x))h'(x)` (quy tắc chuỗi).
- `∇(f₁+f₂)=∇f₁+∇f₂`.
- `∇[(1/2)||Ax−b||₂²]=Aᵀ(Ax−b)`.

**Ví dụ đạo hàm hàm hợp:**

`f(x,y)=(x²+3y−4)²`.

Đặt `u=x²+3y−4`, ta có:

`∂f/∂x=2u·2x=4x(x²+3y−4)`,

`∂f/∂y=2u·3=6(x²+3y−4)`.

Bỏ hệ số từ quy tắc chuỗi sẽ khiến thuật toán tối ưu **một hướng sai**. Trên bài toán dữ liệu lớn, lỗi gradient có thể rất khó nhận ra nếu chỉ nhìn loss cuối cùng; vì thế cần kiểm tra bằng sai phân hữu hạn trước khi chạy tối ưu.

## 4. Tính trơn L-smooth và điều kiện bảo đảm giảm hàm

Giả sử gradient của f **L-Lipschitz** trong miền liên quan:

`||∇f(u)−∇f(v)||₂≤L||u−v||₂`,

với `L>0`. Khi đó f được gọi là **L-smooth**. Ta có bất đẳng thức **descent lemma**:

`f(y)≤f(x)+∇f(x)ᵀ(y−x)+(L/2)||y−x||₂²`.

Đặt `g=∇f(x)` và `y=x−ηg`. Thế vào:

`f(x−ηg)≤f(x)−η(1−Lη/2)||g||₂²`.

Đây là cơ sở toán học của việc chọn learning rate.

- Với `0<η<2/L`, hệ số trước `||g||²` dương; nếu g≠0, f **giảm nghiêm ngặt** theo mô hình số thực chính xác.
- Với `0<η≤1/L`, ta có:

`f(x−ηg)≤f(x)−(η/2)||g||₂²`.

Bước `η=1/L` thường là lựa chọn đơn giản có bảo đảm. Tuy nhiên **f khả vi không tự động có một hằng số L hữu hạn áp dụng toàn R^d**. Khi miền lớn, độ cong biến thiên hoặc không biết L, nên dùng một chiến lược dò bước phù hợp.

### Trường hợp bậc hai

Với:

`f(x,y)=(x−3)²+2(y+2)²`,

Hessian `H=diag(2,4)`, nên L=4. Vì vậy `0<η<0.5` là miền an toàn theo descent lemma. Bước 0.25 thỏa, bước 1 không thỏa.

### Cận bước cho hàm bậc hai một biến

Xét:

`f(x)=(λ/2)(x−x*)²` với λ>0.

Ta có:

`x_new−x*=(1−ηλ)(x−x*)`.

Đặt `e_k=x_k−x*`:

`e_(k+1)=(1−ηλ)e_k`.

Dãy hội tụ nếu `|1−ηλ|<1`, tương đương `0<η<2/λ`. Khi η quá lớn, sai số có thể đổi dấu và tăng dần, dẫn đến phân kỳ.

## 5. Lồi, lồi mạnh và không lồi

**Hàm lồi** thỏa:

`f(tx+(1−t)y)≤tf(x)+(1−t)f(y)`,

với mọi x,y và t∈[0,1]. Nếu f khả vi và lồi trên toàn miền không ràng buộc, một điểm `∇f(x)=0` là tối ưu toàn cục.

**Hàm μ-strongly convex** với μ>0 thỏa:

`f(y)≥f(x)+∇f(x)ᵀ(y−x)+(μ/2)||y−x||₂²`.

Nếu bài toán lồi mạnh có nghiệm tối ưu, nghiệm đó duy nhất. Với f vừa μ-strongly convex vừa L-smooth, gradient descent bước `1/L` hội tụ **tuyến tính** theo gap giá trị hàm, có dạng:

`f(x_k)−f*≤(1−μ/L)^k(f(x₀)−f*)`.

Tỉ số `κ=L/μ` được gọi là **condition number**. Nếu κ lớn, tốc độ có thể chậm do các hướng có độ cong khác nhau. Chuẩn hóa biến hoặc preconditioning có thể cải thiện điều kiện tối ưu.

**Hàm không lồi** có thể có nhiều điểm dừng không tối ưu. Ví dụ:

`f(x,y)=x²−y²`.

Gradient `[2x,−2y]` bằng 0 tại (0,0), nhưng f(0,1)=−1<0=f(0,0). Vậy (0,0) là **điểm yên ngựa**. Thuật toán kiểm tra gradient nhỏ sẽ dừng tại đó và hoàn toàn **không chứng minh điểm ấy là cực tiểu**.

Phải phân biệt:

- **Giảm f qua mỗi bước:** tính chất có thể chứng minh bằng L-smooth hoặc Armijo.
- **Tiến tới điểm dừng:** có thể có với giả thiết phù hợp về độ trơn, cận dưới và learning rate.
- **Tối ưu toàn cục:** cần cấu trúc mạnh hơn, chẳng hạn tính lồi và điều kiện tối ưu.

## 6. Chọn learning rate và điều chỉnh thang biến

Learning rate η có thể:

- **Quá nhỏ:** mỗi lượt tiến rất ít, tốc độ chậm, dễ hết giới hạn vòng.
- **Phù hợp:** giảm ổn định.
- **Quá lớn:** vượt nghiệm, tăng f, dao động hoặc phân kỳ.
- **Âm:** thay hướng hạ thành hướng tăng, không hợp hợp đồng thuật toán.

Khi các biến có thang đo quá khác nhau, gradient ở từng chiều rất chênh lệch. Ví dụ một biến đo bằng mét, biến khác đo micromet: cùng η có thể nhỏ với một chiều nhưng quá lớn với chiều kia. Các biện pháp:

1. Chuẩn hóa đặc trưng trước hồi quy.
2. Scale/đổi biến sao cho các trục có độ cong tương tự.
3. Nếu bài có cấu trúc phù hợp, dùng **preconditioned gradient** thay vì bước vô hướng cho mọi chiều.
4. Dùng **backtracking line search** để giảm bớt việc đoán một η cố định.

Đừng thay η chỉ để làm loss đầu tiên giảm nếu việc đo gradient hay scale dữ liệu còn sai.

## 7. Armijo backtracking: dò bước bảo đảm giảm

Một cách chọn η thích nghi là **Armijo line search**. Cho `g=∇f(x)`, hai tham số:

`c∈(0,1)` và `β∈(0,1)`.

Bắt đầu với `η=η₀`, thử:

`candidate=x−ηg`.

Chỉ nhận điểm mới khi:

`f(candidate)≤f(x)−cη||g||₂²`.

Nếu không, cập nhật `η←βη` rồi thử lại.

Giả mã:

~~~text
BACKTRACKING_GRADIENT_DESCENT(f, gradient, x):
    g = gradient(x)
    if norm(g) <= tolerance: return x

    step = initialStep
    while step >= minStep:
        candidate = x - step * g
        if candidate is finite and candidate != x:
            if f(candidate) is finite and
                    f(candidate) <= f(x) - c*step*norm(g)^2:
                accept candidate
                return candidate
        step = step * beta

    report LINE_SEARCH_FAILED
~~~

**Tại sao hợp lý?** Khi g≠0, đạo hàm theo hướng `−g` bằng `−||g||²<0`. Với f khả vi trong lân cận và c∈(0,1), những bước đủ nhỏ sẽ thỏa Armijo trong số học lý tưởng. Tuy nhiên trên máy tính, candidate có thể trùng x vì độ phân giải double hoặc f mới bị làm tròn bằng f cũ. Cài đặt Java yêu cầu **candidate thực sự thay đổi** và f mới **nhỏ hơn f cũ** để không nhận một bước giả.

### Ví dụ Armijo hai biến

Với f(x,y) ở mục 2, tại (0,0):

- Thử η=1: candidate=(6,−8), f=81, **từ chối**.
- Thu nhỏ η=0.5: candidate=(3,−4), f=8, **nhận**.

Tại (3,−4), gradient=(0,−8):

- η=1: candidate=(3,4), f=72, từ chối.
- η=0.5: candidate=(3,0), f=8, không giảm, từ chối.
- η=0.25: candidate=(3,−2), f=0, nhận.

Sau **hai bước được nhận**, đã ở đúng nghiệm với gradient 0.

### Khi line search thất bại

Nếu đặt `minStep=1`, bước η=1 không đạt Armijo và không được thử η=0.5. Thuật toán phải trả `LINE_SEARCH_FAILED`, giữ điểm cũ, chứ không âm thầm cập nhật bằng bước không bảo đảm.

Armijo không tự đảm bảo tối ưu toàn cục của hàm không lồi, và việc thử nhiều η có chi phí đánh giá f cao hơn một bước cố định.

## 8. Tiêu chí dừng và ý nghĩa trạng thái

Một chương trình số học phải phân biệt **đã đạt điều kiện** và **không thể hoặc không nên tiếp tục**.

**GRADIENT_SMALL:** `||∇f(x)||₂≤ε_g`. Đây là kiểm tra một điều kiện dừng, **không** tự bảo đảm minimum trong bài không lồi hoặc tại saddle.

**MAX_ITERATIONS:** đã hết giới hạn vòng khi gradient còn lớn hơn ngưỡng. Chương trình vẫn trả điểm tốt nhất có thể theo thuật toán đã chạy, nhưng không được gọi là hội tụ đạt yêu cầu.

**LINE_SEARCH_FAILED:** với giới hạn `minStep`, không tìm được bước thỏa điều kiện; hoặc cập nhật bị giới hạn bởi số thực hữu hạn. Trả về điểm trước khi thất bại.

### Tại sao không chỉ kiểm tra |f_new−f_old|?

Nếu η cực nhỏ, f thay đổi rất ít dù gradient còn lớn. Vì vậy dừng do thay đổi loss nhỏ **không phải** bằng chứng đã gần nghiệm. Có thể phối hợp với gradient norm và kiểm tra bước, nhưng luôn cần diễn giải theo điều kiện của bài.

### Tại sao không chỉ dựa vào f nhỏ?

Thêm một hằng số C vào f không đổi gradient hay vị trí cực tiểu, nhưng thay đổi mọi giá trị f. Một f nhỏ về trị số không có nghĩa gần tối ưu nếu không biết f*.

### Khác với thuật toán chia đôi nghiệm

Chia đôi khoảng theo dấu giữ một **bracket chứa nghiệm** và có thể bảo đảm sai số vị trí bằng nửa độ rộng. Gradient descent thông thường **không duy trì một bracket**. Để suy ra khoảng cách tới nghiệm từ gradient hoặc giá trị f, cần giả thiết bổ sung như lồi mạnh.

## 9. Ví dụ thực tế: hồi quy tuyến tính ridge

Giả sử ta muốn khớp mô hình:

`ŷ_i=w t_i+b`

từ n cặp dữ liệu `(t_i,y_i)`.

Hàm mục tiêu:

`J(w,b)= (1/(2n)) Σ_i (w t_i+b−y_i)² + (λ/2)w²`,

với `λ≥0`. Đặt residual `e_i=w t_i+b−y_i`.

Gradient:

`∂J/∂w = (1/n)Σ_i e_i t_i + λw`,

`∂J/∂b = (1/n)Σ_i e_i`.

**Quan trọng:** regularization chỉ áp lên w, không áp lên b. Việc cộng nhầm λb trong gradient của b sẽ làm chương trình tối ưu **một bài toán khác**.

### Ví dụ có nghiệm giải tích độc lập

Lấy:

~~~text
t = [-2, -1, 0, 1, 2]
y = [-3, -1, 1, 3, 5]
lambda = 0.2
~~~

Các mẫu nằm trên đường `y=2t+1`. Vì trung bình t=0 và trung bình t²=2:

`∂J/∂w=(2+0.2)w−4=2.2w−4`,

`∂J/∂b=b−1`.

Nghiệm tối ưu:

`w*=4/2.2=20/11≈1.818181818`,

`b*=1`.

Giá trị hàm mục tiêu ở nghiệm:

`J(w*,b*)=4/11≈0.3636363636`.

Gradient descent với η=0.4 và tolerance gradient `10^(−10)` sẽ hội tụ tới các hệ số này. Đây là **đối chiếu độc lập**, vì công thức nghiệm lấy từ việc giải hệ đạo hàm bằng 0, không lấy từ vòng cập nhật gradient.

### Vì sao nghiệm slope không bằng 2?

Nếu λ=0 và mô hình khớp hoàn hảo, w=2. Khi λ=0.2, regularization kéo w về gần 0 để giảm độ lớn tham số, đánh đổi một phần sai số khớp dữ liệu. Vì thế giá trị loss tối ưu **không bằng 0**.

## 10. Batch, mini-batch và stochastic gradient

**Batch GD:** mỗi lần cập nhật dùng gradient tính từ **toàn bộ dữ liệu**. Trong ridge, vòng lặp lấy trung bình residual và các tích residual×t trên tất cả n mẫu.

**Stochastic GD (SGD):** mỗi bước dùng một mẫu hoặc một ước lượng gradient ngẫu nhiên. Có thể rẻ hơn mỗi bước nhưng tạo nhiễu, cần giả thiết về sampling và thường dùng lịch learning rate khác.

**Mini-batch GD:** dùng một nhóm mẫu để cân bằng chi phí tính và độ nhiễu.

Mã Java bên dưới là **batch gradient descent**, không phải SGD. Không được gọi một thuật toán là “stochastic” chỉ vì có mảng mẫu hoặc có `Random` trong bộ kiểm thử.

## 11. Kiểm tra gradient bằng sai phân hữu hạn

Nếu một gradient được viết bằng đạo hàm tay hoặc backpropagation, nên kiểm tra độc lập bằng **central finite difference**:

`∂f/∂x_i ≈ [f(x+h e_i)−f(x−h e_i)]/(2h)`,

trong đó e_i là vectơ đơn vị thứ i.

Với double và hàm đủ trơn có thang vừa phải, lựa chọn thử:

`h=10^(−6)·max(1,|x_i|)`.

Sau đó đối chiếu:

`|g_i−g_numeric| ≤ 10^(−5)·max(1,|g_i|)`.

**Không chọn h càng nhỏ càng tốt:** phép trừ hai giá trị gần nhau gây sai số làm tròn, nhất là khi f có giá trị lớn so với chênh lệch.

Finite difference dùng làm **oracle QA**, không dùng làm gradient chính mỗi vòng vì cần tới 2d phép đánh giá f cho một gradient d chiều. Với hàm không khả vi, miền có biên hoặc dữ liệu nhiễu, phép kiểm còn phải được điều chỉnh phù hợp.

## 12. Các lưu ý số thực và API

- Tất cả tọa độ ban đầu phải hữu hạn; không tiếp tục tính với NaN/Infinity.
- Giá trị objective tại điểm đang xét và gradient phải hữu hạn.
- Tổng bình phương gradient `Σg_i²` có thể overflow ngay cả khi từng g_i hữu hạn; demo kiểm tra kết quả này.
- Candidate sau cập nhật có thể chứa Infinity, hoặc **bằng hệt x** do double không còn đủ độ phân giải. Trong trường hợp đó, không nhận bước giả.
- Các thành phần gradient phải được tính từ **cùng một x**. Mã dùng mảng gradient riêng và nạp NaN trước mỗi lần tính để bắt trường hợp cài đặt hàm gradient quên gán một phần tử.
- Hàm mục tiêu và gradient phải dùng **cùng quy ước** như hệ số 1/2, việc lấy trung bình n mẫu, cách regularize b.
- Kết quả trả vectơ được **sao chép phòng thủ**, tránh để mã ngoài vô tình sửa kết quả đã ghi.

Đây là cài đặt giáo dục với dữ liệu có độ lớn vừa phải. Để tối ưu số cực lớn hoặc điều kiện rất xấu, có thể cần tính norm ổn định hơn, phân phối thang dữ liệu và phương pháp preconditioning.

## 13. Java 17+: tối ưu nhiều biến, bước cố định và Armijo

Lưu thành **`GradientDescentDemo.java`**, không cần thư viện ngoài JDK. Lớp gồm:

- `Objective`: giao diện hàm khả vi nhiều chiều.
- `Settings`: learning rate, gradient tolerance, max iterations, lựa chọn Armijo, shrink, hệ số Armijo và bước tối thiểu.
- `Result`: tọa độ, loss, số bước, trạng thái và bước cuối.
- `DiagonalQuadratic`: bài toán lồi mạnh với Hessian chéo, có nghiệm giải tích.
- `RidgeObjective`: hồi quy tuyến tính ridge hai biến.
- `checkGradient`: sai phân trung tâm độc lập.
- `randomCheck`: 200 bài bậc hai, 100 bài ridge, 150 bài Armijo và 300 lần so gradient.

### Chương trình hoàn chỉnh

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;
import java.util.Random;

public class GradientDescentDemo {
    interface Objective {
        int dimension();
        double value(double[] x);
        void gradient(double[] x, double[] out);
    }

    enum Stop {
        GRADIENT_SMALL, MAX_ITERATIONS, LINE_SEARCH_FAILED
    }

    record Settings(double rate, double tolerance,
            int maxIterations, boolean backtracking,
            double shrink, double armijo, double minStep) {
        Settings {
            if (!Double.isFinite(rate) || rate <= 0.0
                    || !Double.isFinite(tolerance)
                    || tolerance < 0.0 || maxIterations < 1
                    || !Double.isFinite(shrink)
                    || !(shrink > 0 && shrink < 1)
                    || !Double.isFinite(armijo)
                    || !(armijo > 0 && armijo < 1)
                    || !Double.isFinite(minStep)
                    || !(minStep > 0 && minStep <= rate)) {
                throw new IllegalArgumentException("Bad settings");
            }
        }
    }

    record Result(double[] point, double value,
            int iterations, Stop stop, double lastStep) {
        Result { point = point.clone(); }

        @Override
        public double[] point() { return point.clone(); }
    }

    static void dimension(double[] x, int expected) {
        if (x == null || x.length != expected)
            throw new IllegalArgumentException("Wrong dimension");
    }

    static double finiteValue(Objective obj, double[] x) {
        double v = obj.value(x);
        if (!Double.isFinite(v))
            throw new IllegalArgumentException("Nonfinite value");
        return v;
    }

    static double normSquared(double[] g) {
        double sum = 0.0;
        for (double v : g) {
            if (!Double.isFinite(v))
                throw new IllegalArgumentException("Nonfinite gradient");
            sum += v * v;
        }
        if (!Double.isFinite(sum))
            throw new IllegalArgumentException("Norm overflow");
        return sum;
    }

    static Result minimize(
            Objective obj, double[] initial, Settings settings) {
        Objects.requireNonNull(obj, "obj");
        Objects.requireNonNull(settings, "settings");
        if (obj.dimension() <= 0)
            throw new IllegalArgumentException("No variables");
        dimension(initial, obj.dimension());

        double[] x = initial.clone();
        for (double v : x) {
            if (!Double.isFinite(v))
                throw new IllegalArgumentException("Nonfinite input");
        }
        double value = finiteValue(obj, x);
        double[] g = new double[x.length];
        int updates = 0;
        double lastStep = 0.0;

        while (true) {
            Arrays.fill(g, Double.NaN);
            obj.gradient(x, g);
            double norm2 = normSquared(g);

            // Check gradient at the CURRENT point.
            if (Math.sqrt(norm2) <= settings.tolerance())
                return new Result(x, value, updates,
                        Stop.GRADIENT_SMALL, lastStep);

            if (updates >= settings.maxIterations())
                return new Result(x, value, updates,
                        Stop.MAX_ITERATIONS, lastStep);

            double step = settings.rate();
            double[] candidate = new double[x.length];
            double nextValue = Double.NaN;
            boolean accepted = false;

            while (step >= settings.minStep()) {
                boolean moved = false;
                boolean valid = true;
                for (int i = 0; i < x.length; i++) {
                    candidate[i] = x[i] - step * g[i];
                    if (!Double.isFinite(candidate[i])) valid = false;
                    if (candidate[i] != x[i]) moved = true;
                }

                if (valid && moved) {
                    nextValue = obj.value(candidate);
                    if (Double.isFinite(nextValue)) {
                        if (!settings.backtracking()) {
                            accepted = true;
                        } else {
                            double bound = value
                                    - settings.armijo()
                                    * step * norm2;
                            if (nextValue < value
                                    && nextValue <= bound)
                                accepted = true;
                        }
                    }
                }

                if (accepted || !settings.backtracking()) break;
                step *= settings.shrink();
            }

            if (!accepted)
                return new Result(x, value, updates,
                        Stop.LINE_SEARCH_FAILED, lastStep);

            x = candidate;
            value = nextValue;
            lastStep = step;
            updates++;
        }
    }

    static final class DiagonalQuadratic implements Objective {
        final double[] curvature, center;

        DiagonalQuadratic(double[] curvature, double[] center) {
            Objects.requireNonNull(curvature);
            Objects.requireNonNull(center);
            if (curvature.length == 0
                    || curvature.length != center.length)
                throw new IllegalArgumentException("Bad quadratic");
            this.curvature = curvature.clone();
            this.center = center.clone();
            for (int i = 0; i < curvature.length; i++) {
                if (!Double.isFinite(curvature[i])
                        || curvature[i] <= 0
                        || !Double.isFinite(center[i]))
                    throw new IllegalArgumentException(
                            "Need positive finite curvature");
            }
        }

        public int dimension() { return center.length; }

        public double value(double[] x) {
            dimension(x, dimension());
            double result = 0;
            for (int i = 0; i < x.length; i++) {
                double delta = x[i] - center[i];
                result += .5 * curvature[i] * delta * delta;
            }
            return result;
        }

        public void gradient(double[] x, double[] out) {
            dimension(x, dimension());
            dimension(out, dimension());
            for (int i = 0; i < x.length; i++)
                out[i] = curvature[i] * (x[i] - center[i]);
        }
    }

    static final class RidgeObjective implements Objective {
        final double[] t, y;
        final double lambda;

        RidgeObjective(double[] t, double[] y, double lambda) {
            Objects.requireNonNull(t);
            Objects.requireNonNull(y);
            if (t.length == 0 || t.length != y.length
                    || !Double.isFinite(lambda) || lambda < 0)
                throw new IllegalArgumentException("Bad ridge data");
            this.t = t.clone();
            this.y = y.clone();
            this.lambda = lambda;
            for (int i = 0; i < t.length; i++) {
                if (!Double.isFinite(t[i]) || !Double.isFinite(y[i]))
                    throw new IllegalArgumentException("Nonfinite data");
            }
        }

        public int dimension() { return 2; }

        public double value(double[] x) {
            dimension(x, 2);
            double loss = 0;
            for (int i = 0; i < t.length; i++) {
                double error = x[0] * t[i] + x[1] - y[i];
                loss += error * error;
            }
            return loss / (2.0 * t.length)
                    + .5 * lambda * x[0] * x[0];
        }

        public void gradient(double[] x, double[] out) {
            dimension(x, 2);
            dimension(out, 2);
            double gw = 0, gb = 0;
            for (int i = 0; i < t.length; i++) {
                double error = x[0] * t[i] + x[1] - y[i];
                gw += error * t[i];
                gb += error;
            }
            out[0] = gw / t.length + lambda * x[0];
            out[1] = gb / t.length;
        }
    }

    static void checkGradient(Objective obj, double[] x) {
        double[] g = new double[x.length];
        obj.gradient(x, g);
        normSquared(g);

        for (int i = 0; i < x.length; i++) {
            double h = 1e-6 * Math.max(1, Math.abs(x[i]));
            double[] plus = x.clone();
            double[] minus = x.clone();
            plus[i] += h;
            minus[i] -= h;
            double numeric = (finiteValue(obj, plus)
                    - finiteValue(obj, minus)) / (2 * h);
            if (!Double.isFinite(numeric)
                    || Math.abs(numeric - g[i])
                    > 1e-5 * Math.max(1, Math.abs(g[i]))) {
                throw new AssertionError("Incorrect gradient");
            }
        }
    }

    static Settings fixed(double rate, double tol, int steps) {
        return new Settings(rate, tol, steps,
                false, .5, 1e-4, 1e-12);
    }

    static Settings armijo(double rate, double tol,
            int steps, double minStep) {
        return new Settings(rate, tol, steps,
                true, .5, 1e-4, minStep);
    }

    static void show(String name, Result r) {
        double[] x = r.point();
        if (x.length != 2)
            throw new IllegalArgumentException("Display needs 2D");
        System.out.printf(Locale.ROOT,
                "%s x=[%.6f, %.6f] f=%.9f steps=%d stop=%s%n",
                name, x[0], x[1], r.value(),
                r.iterations(), r.stop());
    }

    static void randomCheck() {
        Random random = new Random(2026L);
        int gradientChecks = 0;

        // 200 random diagonal strongly convex quadratics.
        for (int test = 0; test < 200; test++) {
            int d = 1 + random.nextInt(6);
            double[] c = new double[d];
            double[] center = new double[d];
            double[] initial = new double[d];
            double L = 0;
            for (int i = 0; i < d; i++) {
                c[i] = 1 + random.nextInt(6);
                center[i] = random.nextInt(11) - 5;
                initial[i] = random.nextInt(21) - 10;
                L = Math.max(L, c[i]);
            }
            DiagonalQuadratic f = new DiagonalQuadratic(c, center);
            checkGradient(f, initial);
            gradientChecks++;
            Result r = minimize(f, initial, fixed(1.0/L, 1e-9, 500));
            if (r.stop() != Stop.GRADIENT_SMALL
                    || f.value(r.point()) > 1e-13)
                throw new AssertionError("Bad quadratic optimum");
            double[] got = r.point();
            for (int i = 0; i < d; i++) {
                if (Math.abs(got[i] - center[i]) > 1e-8)
                    throw new AssertionError("Wrong quadratic center");
            }
        }
        System.out.println("quadraticRandom=PASS (200 cases)");

        // 100 synthetic ridge datasets with analytic coefficients.
        double[] t = {-2, -1, 0, 1, 2};
        for (int test = 0; test < 100; test++) {
            double trueW = random.nextInt(9) - 4;
            double trueB = random.nextInt(9) - 4;
            double[] y = new double[5];
            for (int i = 0; i < 5; i++)
                y[i] = trueW * t[i] + trueB;
            RidgeObjective f = new RidgeObjective(t, y, .2);
            checkGradient(f, new double[]{.7, -1.3});
            gradientChecks++;
            Result r = minimize(f, new double[]{0, 0},
                    fixed(.4, 1e-9, 300));
            double[] got = r.point();
            double optimalW = 2.0 * trueW / 2.2;
            if (r.stop() != Stop.GRADIENT_SMALL
                    || Math.abs(got[0] - optimalW) > 1e-8
                    || Math.abs(got[1] - trueB) > 1e-8)
                throw new AssertionError("Wrong ridge optimum");
        }
        System.out.println("ridgeRandom=PASS (100 cases)");

        // 150 Armijo tests against known quadratic minimizers.
        for (int test = 0; test < 150; test++) {
            int d = 1 + random.nextInt(6);
            double[] c = new double[d];
            double[] center = new double[d];
            double[] initial = new double[d];
            for (int i = 0; i < d; i++) {
                c[i] = 1 + random.nextInt(6);
                center[i] = random.nextInt(11) - 5;
                initial[i] = random.nextInt(21) - 10;
            }
            DiagonalQuadratic f = new DiagonalQuadratic(c, center);
            Result r = minimize(f, initial,
                    armijo(1.0, 1e-8, 500, 1e-12));
            if (r.stop() != Stop.GRADIENT_SMALL)
                throw new AssertionError("Armijo did not converge");
            double[] got = r.point();
            for (int i = 0; i < d; i++) {
                if (Math.abs(got[i] - center[i]) > 1e-7)
                    throw new AssertionError("Wrong Armijo solution");
            }
        }
        System.out.println("armijoRandom=PASS (150 cases)");
        System.out.println("gradientCheck=PASS ("
                + gradientChecks + " points)");
    }

    public static void main(String[] args) {
        DiagonalQuadratic quadratic = new DiagonalQuadratic(
                new double[]{2, 4}, new double[]{3, -2});

        show("fixedFive", minimize(quadratic,
                new double[]{0, 0}, fixed(.25, 0, 5)));
        show("backtracking", minimize(quadratic,
                new double[]{0, 0},
                armijo(1.0, 1e-10, 100, 1e-12)));

        RidgeObjective ridge = new RidgeObjective(
                new double[]{-2, -1, 0, 1, 2},
                new double[]{-3, -1, 1, 3, 5}, .2);
        Result learned = minimize(ridge,
                new double[]{0, 0}, fixed(.4, 1e-10, 300));
        show("ridge", learned);
        double[] coeffs = learned.point();
        System.out.println("ridgeMatchesAnalytic="
                + (Math.abs(coeffs[0] - 20.0/11.0) < 1e-8
                && Math.abs(coeffs[1] - 1) < 1e-8));

        Result large = minimize(quadratic,
                new double[]{0, 0}, fixed(1, 0, 1));
        show("tooLarge", large);
        System.out.println("tooLargeIncreased="
                + (large.value()
                > quadratic.value(new double[]{0, 0})));

        Result failure = minimize(quadratic,
                new double[]{0, 0}, armijo(1, 0, 100, 1));
        System.out.println("lineSearchFailure=" + failure.stop()
                + " xUnchanged=" + Arrays.equals(
                    failure.point(), new double[]{0, 0}));

        Objective saddle = new Objective() {
            public int dimension() { return 2; }
            public double value(double[] x) {
                return x[0]*x[0] - x[1]*x[1];
            }
            public void gradient(double[] x, double[] g) {
                g[0] = 2*x[0];
                g[1] = -2*x[1];
            }
        };
        Result stationary = minimize(saddle,
                new double[]{0, 0}, fixed(.25, 1e-10, 5));
        boolean isMinimum = saddle.value(new double[]{0, 1})
                >= saddle.value(new double[]{0, 0});
        System.out.println("saddleStop=" + stationary.stop()
                + " isMinimum=" + isMinimum);

        try {
            minimize(quadratic, new double[0],
                    fixed(.25, 1e-8, 20));
            throw new AssertionError("Expected bad dimension");
        } catch (IllegalArgumentException expected) {
            System.out.println("emptyVector=rejected");
        }

        randomCheck();
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 GradientDescentDemo.java
java GradientDescentDemo
~~~

**Đầu ra dự kiến:**

~~~text
fixedFive x=[2.906250, -2.000000] f=0.008789063 steps=5 stop=MAX_ITERATIONS
backtracking x=[3.000000, -2.000000] f=0.000000000 steps=2 stop=GRADIENT_SMALL
ridge x=[1.818182, 1.000000] f=0.363636364 steps=46 stop=GRADIENT_SMALL
ridgeMatchesAnalytic=true
tooLarge x=[6.000000, -8.000000] f=81.000000000 steps=1 stop=MAX_ITERATIONS
tooLargeIncreased=true
lineSearchFailure=LINE_SEARCH_FAILED xUnchanged=true
saddleStop=GRADIENT_SMALL isMinimum=false
emptyVector=rejected
quadraticRandom=PASS (200 cases)
ridgeRandom=PASS (100 cases)
armijoRandom=PASS (150 cases)
gradientCheck=PASS (300 points)
~~~

### Phân tích các dòng đầu ra

**fixedFive:** năm lượt η=0.25 cho (2.90625,−2), f=0.0087890625; đã hết số vòng nhưng gradient còn khác 0 nên `MAX_ITERATIONS` là chính xác.

**backtracking:** bước thử η=1 tăng f nên bị từ chối; Armijo giảm η còn 0.5, rồi ở lượt sau còn 0.25, đến đúng (3,−2) sau hai lần cập nhật; gradient bằng 0.

**ridge:** tối ưu loss gồm bình phương sai số và regularization, xấp xỉ nghiệm giải tích w=20/11, b=1. Tolerance gradient đạt sau 46 lượt theo ví dụ này. Giá trị f tối ưu khác 0 vì còn chi phí regularization.

**tooLarge:** η=1 từ (0,0) cho (6,−8), làm f tăng từ 17 lên 81. Nhánh bước cố định không tự thực hiện kiểm tra Armijo, nhằm minh họa rằng learning rate không phù hợp có thể làm mất tính giảm hàm.

**lineSearchFailure:** giới hạn minStep=1 ngăn bước 0.5 sau khi bước 1 bị từ chối; thuật toán báo `LINE_SEARCH_FAILED` và giữ nguyên điểm cũ.

**saddleStop:** gradient ở (0,0) của f=x²−y² bằng 0, nên thuật toán đạt `GRADIENT_SMALL`. Nhưng f(0,1)<f(0,0), vì vậy đó **không phải cực tiểu**.

**emptyVector:** bài toán hai biến từ chối vectơ khởi tạo có chiều dài bằng 0.

**quadraticRandom:** trên 200 hàm bậc hai chéo có độ cong dương, kết quả được so với **nghiệm giải tích là vectơ center**, không lấy từ thuật toán cần kiểm chứng.

**ridgeRandom:** trên 100 bộ dữ liệu tuyến tính đối xứng quanh t=0, nghiệm ridge giải tích là `w=2w_true/2.2`, `b=b_true`. Thuật toán phải đưa ra các hệ số tương ứng.

**armijoRandom:** 150 hàm bậc hai kiểm tra backtracking với các tâm, độ cong và điểm đầu khác nhau; yêu cầu nghiệm về gần tâm.

**gradientCheck:** tổng 300 lần đối chiếu gradient giải tích của quadratic và ridge bằng central finite difference, với ngưỡng sai số phù hợp cho dữ liệu thử.

Các test cung cấp bằng chứng thực nghiệm **trong miền đã thử**, không chứng minh gradient descent luôn hội tụ trên mọi hàm khả vi hoặc luôn tìm nghiệm toàn cục khi f không lồi.

## 14. Vì sao thuật toán đúng trong phạm vi giả thiết?

**Bước cố định.** Nếu f L-smooth, chọn η∈(0,2/L) và g≠0 thì descent lemma bảo đảm f giảm theo số học chính xác. Nếu η≤1/L, lượng giảm có cận dưới `(η/2)||g||²`. Mã cố ý cho phép bước cố định lớn hơn miền này để người học quan sát trường hợp phân kỳ; API không tự chứng nhận mọi η.

**Armijo.** Nhánh backtracking chỉ nhận một candidate hữu hạn, khác điểm cũ, thỏa f mới < f cũ và `f_new≤f_old−cη||g||²`. Mỗi bước được chấp nhận thực sự giảm f trong số học máy. Nếu không có bước hợp lệ trong miền `η≥minStep`, mã trả thất bại và không làm đổi điểm hiện tại.

**Trạng thái dừng.** Mỗi vòng tính lại gradient của **x hiện tại**. Nếu chuẩn gradient nhỏ thì trả `GRADIENT_SMALL`; nếu hết lượt thì `MAX_ITERATIONS`; nếu không có bước hợp lệ thì `LINE_SEARCH_FAILED`. Thứ tự kiểm tra gradient trước giới hạn vòng giúp trường hợp vừa chạm nghiệm ở bước cuối được nhận diện đúng.

**Tối ưu toàn cục.** Với f lồi khả vi, gradient bằng 0 là điều kiện đủ cho tối ưu toàn cục. Với f không lồi, cùng điều kiện chỉ là stationary và không chứng nhận cực tiểu.

## 15. Mở rộng: dữ liệu lớn, ràng buộc và không khả vi

**Dữ liệu lớn:** nếu mỗi gradient phải duyệt hàng triệu mẫu, batch GD có thể đắt. Mini-batch và SGD dùng ước lượng gradient với chi phí thấp hơn mỗi lượt nhưng độ nhiễu lớn hơn. Lịch giảm learning rate, kỹ thuật đánh giá trên tập validation và các giả thiết thống kê trở nên quan trọng.

**Ràng buộc:** nếu x phải thuộc tập C, bước `x−η∇f(x)` có thể rời C. Với tập lồi đóng và phép chiếu khả thi, **projected gradient descent** dùng:

`x_new=Π_C(x−η∇f(x))`.

Đây là thuật toán có điều kiện dừng và bảo đảm riêng, không phải cứ chạy mã không ràng buộc rồi bỏ qua tính hợp lệ của x.

**Hàm không khả vi:** với `f(x)=|x|` tại x=0, đạo hàm cổ điển không tồn tại. Có thể dùng subgradient hoặc proximal methods tùy cấu trúc, nhưng không được áp dụng công thức gradient cổ điển tại mọi điểm mà không có quy ước.

**Hàm không có cực tiểu hữu hạn:** `f(x)=−x` có thể giảm vô hạn khi x→+∞. Không có learning rate nào biến một bài toán không có minimizer thành bài có nghiệm; phải xác định mô hình trước khi chọn thuật toán.

**Độ cong kém điều kiện:** nếu Hessian có trị riêng chênh lệch lớn, một bước η đủ an toàn cho hướng dốc lại quá nhỏ cho hướng phẳng. Có thể dùng chuẩn hóa, preconditioning, conjugate gradient trên các hệ thích hợp hoặc thuật toán bậc hai.

## 16. So sánh với các phương pháp liên quan

| Phương pháp | Cơ chế | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| Gradient descent bước cố định | `x←x−η∇f(x)` | Đơn giản, ít phép đánh giá f | Phải chọn η |
| Armijo backtracking | Thử η và giảm tới khi f đủ giảm | Bước thích nghi, không nhất thiết biết L | Tốn nhiều lần tính f |
| SGD / mini-batch | Gradient từ một phần dữ liệu | Thích hợp dữ liệu lớn | Nhiễu, cần lịch bước |
| Momentum / Nesterov | Kết hợp trạng thái vận tốc | Có thể tăng tốc một số bài toán | Cần thêm tham số |
| Newton | Dùng Hessian để hiệu chỉnh bước | Có thể hội tụ nhanh gần nghiệm tốt | Hessian đắt/không xác định dương |
| Projected gradient | Cập nhật và chiếu vào tập khả thi | Xử lý một số ràng buộc | Phụ thuộc phép chiếu và tính lồi |
| Coordinate descent | Chọn một số tọa độ mỗi lượt | Có ích với hàm phân tách | Có thể chậm khi tương quan mạnh |

Không có thuật toán thắng mọi bài toán. Cần xét điều kiện lồi/trơn, số chiều, cách tính gradient, chi phí đánh giá f, giới hạn bộ nhớ và độ chính xác mong muốn.

## 17. Sai lầm phổ biến

1. Viết dấu cộng thay dấu trừ khi muốn tối thiểu hóa.
2. Dùng giá trị f(x) thay cho gradient.
3. Bỏ một thành phần đạo hàm riêng hoặc quy tắc chuỗi.
4. Tính gradient bằng tham số đã cập nhật một phần, không đồng bộ.
5. Dùng quá lớn learning rate và kỳ vọng f luôn giảm.
6. Dùng quá nhỏ learning rate rồi kết luận đã hội tụ vì f đổi ít.
7. Nhầm khả vi với lồi.
8. Nhầm gradient=0 với tối ưu toàn cục trên hàm không lồi.
9. Không kiểm tra saddle khi diễn giải GRADIENT_SMALL.
10. Dùng lý thuyết L-smooth khi không có điều kiện đó.
11. Áp công thức hội tụ của hàm lồi mạnh cho mọi hàm.
12. Không chuẩn hóa biến có thang quá khác nhau.
13. Không kiểm tra gradient bằng finite difference.
14. Chọn h quá bé làm sai phân bị sai số làm tròn.
15. Bỏ chia số mẫu n trong mean squared error.
16. Regularize nhầm intercept khi loss chỉ phạt slope.
17. Không tính gradient từ cùng một objective với value(x).
18. Không kiểm tra giá trị NaN/Infinity trong f và g.
19. Để chuẩn gradient bình phương overflow mà không phát hiện.
20. Không kiểm tra candidate trùng x do số thực hữu hạn.
21. Chấp nhận bước Armijo khi f tăng vì đảo dấu bất đẳng thức.
22. Chọn shrink≥1 nên không thực sự giảm bước thử.
23. Đặt minStep quá lớn khiến không có bước nào được phép nhận.
24. Không có giới hạn vòng hoặc nhầm hết vòng với hội tụ.
25. Tuyên bố cực tiểu chỉ vì giá trị f nhỏ trên một thang đo tùy ý.
26. Gọi batch GD là SGD dù mỗi lượt dùng toàn bộ mẫu.
27. Dùng thuật toán không ràng buộc trên bài có ràng buộc.
28. Gọi gradient tại điểm không khả vi mà không xác định subgradient.
29. Không test trên hàm có nghiệm giải tích trước dữ liệu phức tạp.
30. Không thử trường hợp bước quá lớn làm loss tăng.
31. Không thử lỗi line search hoặc giới hạn precision.
32. Không so gradient giải tích với một phương pháp độc lập.
33. Dùng một mảng điểm đầu vào và sửa trực tiếp ngoài ý muốn.
34. Dùng kết quả gradient nhỏ như chứng nhận không còn nghiệm tốt hơn.
35. Coi phép thử ngẫu nhiên là bằng chứng đầy đủ cho hội tụ toán học.

## 18. Bài tập có lời giải

**Bài 1.** Với `f(x)=(x−3)²`, gradient là gì? **Đáp án:** `2(x−3)`.

**Bài 2.** Tại x=0, η=0.25, bước mới? **Đáp án:** `x=1.5`.

**Bài 3.** Với `f(x,y)=(x−3)²+2(y+2)²`, gradient? **Đáp án:** `[2(x−3),4(y+2)]`.

**Bài 4.** Gradient tại (0,0) của bài 3? **Đáp án:** `(−6,8)`.

**Bài 5.** Bước η=0.25 từ (0,0) cho điểm gì? **Đáp án:** (1.5,−2).

**Bài 6.** f giảm từ giá trị nào xuống giá trị nào ở bước 5? **Đáp án:** 17 xuống 2.25.

**Bài 7.** Sau năm bước η=0.25 từ (0,0), điểm? **Đáp án:** (2.90625,−2).

**Bài 8.** Giá trị f tại điểm bài 7? **Đáp án:** 0.0087890625.

**Bài 9.** Bước η=1 từ (0,0) ra sao? **Đáp án:** tới (6,−8), f tăng lên 81.

**Bài 10.** Hướng giảm dốc nhất theo chuẩn Euclid khi g≠0? **Đáp án:** `−g/||g||₂` nếu yêu cầu hướng đơn vị.

**Bài 11.** Descent lemma cho bước gradient có dạng nào? **Đáp án:** `f(x−ηg)≤f(x)−η(1−Lη/2)||g||²`.

**Bài 12.** Với L=4, miền bước có bảo đảm giảm khi g≠0? **Đáp án:** `0<η<0.5`.

**Bài 13.** Chọn η=1/L với L=4? **Đáp án:** 0.25.

**Bài 14.** Với Hessian diag(2,4), μ và L? **Đáp án:** μ=2, L=4.

**Bài 15.** Condition number bằng gì? **Đáp án:** κ=L/μ=2.

**Bài 16.** Hàm lồi khả vi có gradient=0 tại x, kết luận? **Đáp án:** x là tối ưu toàn cục trên miền không ràng buộc.

**Bài 17.** Hàm x²−y² tại (0,0) có minimum không? **Đáp án:** không; đây là saddle vì f(0,1)<f(0,0).

**Bài 18.** Điều kiện Armijo? **Đáp án:** `f(x−ηg)≤f(x)−cη||g||²`.

**Bài 19.** Với β=0.5, bước η=1 thất bại thì thử bước nào? **Đáp án:** 0.5.

**Bài 20.** Bước backtracking đầu từ (0,0) trên quadratic tới đâu? **Đáp án:** (3,−4) với η=0.5.

**Bài 21.** Lượt kế từ (3,−4) được η=0.25 tới đâu? **Đáp án:** (3,−2).

**Bài 22.** Khi không có bước ≥minStep thỏa Armijo, trạng thái? **Đáp án:** LINE_SEARCH_FAILED.

**Bài 23.** Khi chuẩn gradient≤tolerance, trạng thái? **Đáp án:** GRADIENT_SMALL.

**Bài 24.** Khi hết lượt nhưng gradient chưa đủ nhỏ, trạng thái? **Đáp án:** MAX_ITERATIONS.

**Bài 25.** Tại sao f thay đổi nhỏ chưa đủ chứng minh hội tụ? **Đáp án:** learning rate quá nhỏ hoặc sai số làm tròn cũng làm thay đổi rất ít.

**Bài 26.** Gradient ridge theo w? **Đáp án:** `(1/n)Σeᵢtᵢ+λw`.

**Bài 27.** Gradient ridge theo b khi không regularize bias? **Đáp án:** `(1/n)Σeᵢ`.

**Bài 28.** Với t=[−2,−1,0,1,2], y=2t+1 và λ=0.2, nghiệm ridge? **Đáp án:** w=20/11, b=1.

**Bài 29.** Giá trị J tối ưu của bài 28? **Đáp án:** 4/11.

**Bài 30.** Công thức sai phân trung tâm kiểm tra thành phần gradient thứ i? **Đáp án:** `[f(x+h eᵢ)−f(x−h eᵢ)]/(2h)`.

**Bài 31.** Đạo hàm theo x của `(x²+3y−4)²`? **Đáp án:** `4x(x²+3y−4)`.

**Bài 32.** Đạo hàm theo y của cùng hàm? **Đáp án:** `6(x²+3y−4)`.

**Bài 33.** SGD khác batch GD ở đâu? **Đáp án:** SGD dùng một mẫu/ước lượng ngẫu nhiên, batch dùng toàn bộ dữ liệu.

**Bài 34.** Khi x phải thuộc tập khả thi C, biến thể nào thường dùng? **Đáp án:** projected gradient với phép chiếu `Π_C` nếu phù hợp.

**Bài 35.** Với f(x)=|x| tại 0, có thể dùng gradient cổ điển không? **Đáp án:** không, vì đạo hàm không tồn tại tại 0; cần phương pháp không trơn.

## 19. Checklist triển khai

1. Đã xác định chính xác f(x) và miền hợp lệ của biến chưa?
2. f có khả vi tại các điểm thuật toán sẽ duyệt không?
3. Gradient từng thành phần có đúng đạo hàm riêng, quy tắc chuỗi và dấu không?
4. Value(x) và gradient(x) có mô tả cùng một hàm mục tiêu không?
5. Đã kiểm tra gradient bằng sai phân hữu hạn tại các điểm đại diện chưa?
6. Đã phân biệt tối ưu không ràng buộc với bài có ràng buộc chưa?
7. Learning rate có dương, hữu hạn và phù hợp với độ cong không?
8. Nếu dùng bước cố định, có giả thiết L-smooth và cận bước hoặc bằng chứng kiểm thử phù hợp không?
9. Nếu dùng Armijo, có c∈(0,1), β∈(0,1), minStep và cách báo thất bại không?
10. Có đánh giá gradient từ cùng một điểm x, trước khi cập nhật mọi tọa độ không?
11. Có từ chối NaN/Infinity trong tham số, gradient và objective không?
12. Có phát hiện bước không thay đổi x do độ phân giải double không?
13. Có báo GRADIENT_SMALL, MAX_ITERATIONS, LINE_SEARCH_FAILED tách biệt không?
14. Có hiểu gradient nhỏ không chứng nhận tối ưu toàn cục khi f không lồi không?
15. Có chuẩn hóa dữ liệu/biến nếu condition number quá lớn không?
16. Với ridge, đã chia n, đặt hệ số 1/2 và regularize đúng tham số chưa?
17. Đã phân biệt batch, mini-batch và SGD chưa?
18. Có kiểm tra trên bài bậc hai và ridge với nghiệm giải tích không?
19. Có thử learning rate quá lớn khiến f tăng không?
20. Có thử line search thất bại và trạng thái không cập nhật x không?
21. Có kiểm tra mảng đầu vào không bị sửa bất ngờ không?
22. Có viết rõ điều kiện hội tụ giả định, thay vì khẳng định mọi hàm khả vi luôn hội tụ không?

**Ghi nhớ:** hạ gradient có công thức ngắn gọn `x←x−η∇f(x)` nhưng độ tin cậy dựa trên **gradient đúng, bước học phù hợp, tính trơn/lồi và tiêu chí dừng trung thực**. Bước cố định nhỏ theo L-smooth bảo đảm giảm, còn **Armijo backtracking** dò bước khi không biết trước độ cong. Với hàm không lồi, chuẩn gradient nhỏ chỉ xác nhận **stationary theo ngưỡng**, không chứng nhận cực tiểu toàn cục. Khi áp dụng vào Java, hãy kiểm soát giá trị không hữu hạn, cập nhật đồng bộ, kiểm tra bằng nghiệm giải tích và phân biệt trạng thái thành công/thất bại.

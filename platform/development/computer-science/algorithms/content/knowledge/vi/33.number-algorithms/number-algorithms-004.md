# Newton cho phương trình phi tuyến

**Phương pháp Newton (Newton–Raphson)** là thuật toán lặp tìm **nghiệm gần đúng** của phương trình **`f(x)=0`** bằng cách thay đồ thị của hàm tại giá trị hiện tại bằng **tiếp tuyến**. Nếu `xₖ` là xấp xỉ hiện tại và đạo hàm `f'(xₖ)` khác 0, bước tiếp theo được tính bởi:

**`xₖ₊₁=xₖ−f(xₖ)/f'(xₖ)`**.

Khi f đủ trơn, nghiệm cần tìm là **nghiệm đơn** và điểm bắt đầu đủ gần nghiệm, Newton có **hội tụ bậc hai cục bộ**: sai số mới có bậc bằng **bình phương** sai số cũ. Đó là nguyên nhân Newton thường tìm được nhiều chữ số chính xác chỉ sau vài vòng. Nhưng công thức ngắn không đồng nghĩa phương pháp luôn an toàn: đạo hàm bằng 0, bước nhảy khỏi miền hợp lệ, lặp chu kỳ, nghiệm bội và các ngưỡng dừng không phù hợp có thể cho kết quả sai hoặc không hội tụ.

Bài thuộc nhóm **Thuật toán số** của **Computer Science Algorithms**, với chủ đề **Newton cho phương trình phi tuyến**. Ta sẽ đi từ phương trình tiếp tuyến, khai triển Taylor và chứng minh hội tụ, theo dõi cách tìm √2, phân tích sai số **residual so với sai số nghiệm**, khảo sát những phản ví dụ Newton không an toàn, rồi xây **Newton có kẹp đoạn, dự phòng chia đôi (safeguarded Newton)**. Mã Java 17+ tự chạy minh họa cả Newton thuần, Newton có safeguard, xử lý lỗi và một bộ test so với **bisection độc lập**. Bài cũng giới thiệu đạo hàm sai phân, secant, damping và Newton cho hệ phương trình.

**Hợp đồng ví dụ:** tìm nghiệm thực một biến bằng kiểu `double`; `f` và `df` do người dùng cung cấp phải nhất quán và không có tác dụng phụ; các điểm được đánh giá phải thuộc miền của hàm. Solver thuần cần điểm khởi tạo `x₀`, còn solver có safeguard cần đoạn **[a,b] có f liên tục và hai đầu trái dấu**, trừ trường hợp một đầu bằng nghiệm. Chương trình không hứa sai số vị trí ≤10⁻¹² chỉ vì phần dư nhỏ hơn 10⁻¹².

## 1. Phương trình phi tuyến và bài toán tìm nghiệm

Cho hàm `f:D⊆ℝ→ℝ`. Ta cần tìm giá trị `α∈D` sao cho **`f(α)=0`**. Một số ví dụ:

| Hàm f(x) | Nghiệm cần tìm |
|---|---|
| `x²−2` | ±√2 |
| `x³−2` | ∛2 |
| `cos(x)−x` | khoảng 0,739085133215 |
| `e^(−x)−x` | khoảng 0,567143290410 |
| `x³−2x+2` | nghiệm thực gần −1,769292354239 |

Không phải lúc nào ta cũng có công thức đóng dễ tính, đặc biệt với các phương trình lượng giác, hàm mũ hoặc mô hình vật lý. Khi ấy ta **xấp xỉ nghiệm theo từng bước**. Do số thực trên máy thường được biểu diễn bởi `double`, kết quả trả về mang độ chính xác hữu hạn; phải xác định ý nghĩa của “đủ gần”.

### Nghiệm thật, xấp xỉ và phần dư

Với nghiệm thật α và xấp xỉ x:

- **Sai số nghiệm**: `|x−α|`, thường không tính trực tiếp được nếu α chưa biết.
- **Phần dư (residual)**: `|f(x)|`, tính được tại x.
- **Bước lặp**: `|xₖ₊₁−xₖ|`.
- **Độ rộng bracket**: `b−a` nếu có chứng nhận nghiệm α nằm trong [a,b].

Bốn đại lượng **không tương đương**. Hàm có đạo hàm rất nhỏ gần nghiệm có thể tạo residual cực nhỏ trong khi x vẫn cách nghiệm đáng kể. Một bước rất nhỏ có thể do kẹt số học dấu phẩy động chứ không phải vì đã chính xác.

### Nghiệm đơn và nghiệm bội

Nghiệm α là **nghiệm đơn** nếu `f(α)=0` và `f'(α)≠0`. Ví dụ nghiệm √2 của f=x²−2 là nghiệm đơn.

Nếu `f'(α)=0`, α có thể là **nghiệm bội**: f(x)=(x−1)² có nghiệm bội 2 tại x=1; f(x)=x³ có nghiệm bội 3 tại x=0. Newton chuẩn thường hội tụ chậm hơn ở các nghiệm ấy. Không được phát biểu bậc hai cho mọi nghiệm mà bỏ qua điều kiện đạo hàm tại nghiệm khác 0.

## 2. Suy ra Newton từ tiếp tuyến

Giả sử f khả vi tại xₖ. Trong một vùng nhỏ quanh xₖ:

**`f(x)≈f(xₖ)+f'(xₖ)(x−xₖ)`**.

Đây là phương trình **đường tiếp tuyến** của đồ thị y=f(x) tại điểm `(xₖ,f(xₖ))`. Ta tìm nơi tiếp tuyến chạm trục hoành y=0 bằng cách giải:

**`0=f(xₖ)+f'(xₖ)(xₖ₊₁−xₖ)`**.

Nếu `f'(xₖ)≠0`, chuyển vế:

**`xₖ₊₁=xₖ−f(xₖ)/f'(xₖ)`**.

Bước `Δₖ=−f(xₖ)/f'(xₖ)` là **điều chỉnh theo tuyến tính hóa**. Một vòng lặp cần đánh giá hàm, đạo hàm, chia và trừ. Nếu f(xₖ) đã đủ gần 0 theo tiêu chí, trả kết quả trước khi tính đạo hàm; một nghiệm bội có thể có f'=0 nhưng vẫn là nghiệm hợp lệ.

### Ba lỗi dấu phổ biến

1. Viết `xₖ₊₁=xₖ+f(xₖ)/f'(xₖ)` thay vì **dấu trừ**.
2. Quên mẫu số và viết `xₖ₊₁=xₖ−f(xₖ)`.
3. Tính sai đạo hàm, chẳng hạn với `f(x)=cos(x)−x` thì **`f'(x)=−sin(x)−1`**, không phải `sin(x)−1`.

Trong Java, `Math.sin` và `Math.cos` dùng **radian**, không phải độ. Đạo hàm phải tính theo cùng đơn vị của f.

## 3. Ví dụ chi tiết: Newton tìm √2

Đặt:

**`f(x)=x²−2`** và **`f'(x)=2x`**.

Newton cho:

**`xₖ₊₁=xₖ−(xₖ²−2)/(2xₖ)=(xₖ+2/xₖ)/2`**, khi xₖ≠0.

Chọn `x₀=1,5`, ta có:

~~~text
k  x_k              f(x_k)
0  1.500000000000   0.250000000000
1  1.416666666667   0.006944444444
2  1.414215686275   0.000006007305
3  1.414213562375   0.000000000005
4  1.414213562373   0.000000000000  (rounded for display)
~~~

Nghiệm dương thật `√2≈1,4142135623730951`. Chỉ vài vòng làm sai số giảm mạnh. Ở bước đầu, tiếp tuyến tại x=1,5 có độ dốc 3 và giá trị hàm 0,25, nên giao trục hoành:

**`x₁=1,5−0,25/3=1,416666666...`**.

Tính tiếp tại x₁, ta được x₂≈1,414215686..., rồi tiến gần nghiệm rất nhanh.

**Cảnh báo về dòng 0,000000000000:** đây là do in tới **12 chữ số sau dấu thập phân**; không khẳng định `f(x)=0` chính xác trong toán học. Khi dùng `double`, biểu diễn √2 chính xác vô hạn là không thể.

### Điểm bắt đầu x₀=0 thì sao?

Với f=x²−2, tại x=0 có f(0)=−2 nhưng f'(0)=0. Công thức phải chia cho 0 và không xác định được bước Newton. Không thể kết luận “phương trình vô nghiệm”; cần **đổi điểm bắt đầu** hoặc dùng một phương pháp có khoảng kẹp, chẳng hạn [1,2].

## 4. Vì sao Newton hội tụ bậc hai khi ở gần nghiệm đơn?

Giả sử α là nghiệm đơn, f có đạo hàm bậc hai liên tục gần α, và x₀ đủ gần α. Đặt **`eₖ=xₖ−α`**.

Khai triển Taylor với phần dư tại α:

**`0=f(α)=f(xₖ)+f'(xₖ)(α−xₖ)+(1/2)f''(ξₖ)(α−xₖ)²`**,

trong đó ξₖ nằm giữa xₖ và α. Biến đổi và thay công thức Newton:

**`eₖ₊₁=[f''(ξₖ)/(2f'(xₖ))]eₖ²`**.

Vì f'(α) khác 0 và f'' liên tục, trong một lân cận đủ nhỏ tỷ số ở vế phải bị chặn bởi một hằng số C hữu hạn. Do đó:

**`|eₖ₊₁|≤C|eₖ|²`**.

Đây là **hội tụ bậc hai cục bộ** (*local quadratic convergence*). Nếu sai số đã nhỏ khoảng 10⁻³ và C ở cỡ 1, bước tiếp theo có thể đạt 10⁻⁶, rồi 10⁻¹². Không thể suy từ đây rằng Newton sẽ hội tụ từ **mọi** x₀, hoặc rằng một bước lặp luôn nhân đôi số chữ số đúng bất kể f.

### Các điều kiện không thể bỏ

- **f(α)=0**: có nghiệm cần tìm.
- **f'(α)≠0**: nghiệm đơn, không mất mẫu số gần nghiệm.
- **f đủ trơn**: chẳng hạn thuộc C² trong một lân cận.
- **x₀ đủ gần α**: phép tuyến tính hóa thực sự có ích.
- Các phép tính đủ chính xác để quan sát quá trình; ở giới hạn `double`, sai số làm tròn cuối cùng chi phối.

**Bậc hai không phải thời gian O(n²)**. Bậc hội tụ nói về mối liên hệ giữa **sai số qua các bước**, không phải Big-O theo kích thước mảng đầu vào.

## 5. Nghiệm bội: Newton có thể chỉ hội tụ tuyến tính

Với:

**`f(x)=(x−1)²`**, `f'(x)=2(x−1)`.

Khi x≠1:

**`xₖ₊₁=xₖ−(xₖ−1)²/[2(xₖ−1)]=(xₖ+1)/2`**.

Do đó `eₖ₊₁=eₖ/2`: sai số **giảm một nửa**, không phải bình phương.

Nếu bắt đầu x₀=3:

~~~text
3 -> 2 -> 1.5 -> 1.25 -> 1.125 -> 1.0625 -> ...
~~~

Tương tự, với f(x)=x³, f'(x)=3x² và x≠0, ta có:

**`xₖ₊₁=(2/3)xₖ`**.

Sai số vị trí chỉ giảm theo 2/3, nhưng residual `|f(xₖ)|=|xₖ|³` rất nhỏ khi x nhỏ. Chẳng hạn:

**`x=0,0001 ⇒ |f(x)|=10⁻¹²`**, dù nghiệm thật là 0 và sai số vị trí vẫn 10⁻⁴.

Với residual tolerance 10⁻¹², một solver có thể dừng tại x còn cách nghiệm **khoảng mười nghìn lần lớn hơn ngưỡng nếu ngưỡng ấy được diễn giải sai là sai số vị trí**. Bản Java cố ý minh họa bằng dòng `Flat cubic residual-only`.

### Newton điều chỉnh cho nghiệm bội

Nếu biết chính xác nghiệm có bội m, một biến thể là:

**`xₖ₊₁=xₖ−m·f(xₖ)/f'(xₖ)`**.

Trong điều kiện thích hợp, phép điều chỉnh này giúp khôi phục hội tụ nhanh hơn. Không chọn m tùy tiện nếu chưa biết số bội, vì sửa hệ số bước có thể làm thuật toán bất ổn.

## 6. Newton thuần có thể thất bại thế nào?

### Đạo hàm bằng 0

Với `f(x)=x³−1`, f'(x)=3x². Bắt đầu x₀=0 thì f(0)=−1≠0, nhưng f'(0)=0. Bước Newton yêu cầu chia cho 0. Phải **báo lỗi hoặc chọn lại bước/điểm**, không thay mẫu số bằng một epsilon không có cơ sở.

Nếu f(x₀)=0 và f'(x₀)=0, ta đã ở **một nghiệm** và nên trả trước khi chia.

### Chu kỳ x₀=0→1→0

Xét:

**`f(x)=x³−2x+2`**, **`f'(x)=3x²−2`**.

Bắt đầu x₀=0:

- f(0)=2, f'(0)=−2 ⇒ **x₁=1**.
- f(1)=1, f'(1)=1 ⇒ **x₂=0**.

Do đó Newton thuần lặp **0→1→0→1→...** dù phương trình có nghiệm thực gần **−1,769292354239**. Một bracket hợp lệ là [−2,0] vì f(−2)=−2<0 và f(0)=2>0.

### Rời miền xác định

Với `f(x)=ln(x)−1`, miền cần x>0. Từ x₀ quá lớn, bước Newton có thể đưa x xuống giá trị âm; lượt đánh giá `ln(x)` sau đó không xác định. Đó là lý do bộ giải cần kiểm miền hợp lệ, NaN/Infinity và có thể dùng giảm bước hoặc bracket.

### Có nhiều nghiệm

`f(x)=x²−1` có hai nghiệm −1 và 1. Newton từ hai vùng ban đầu khác nhau có thể tới hai nghiệm khác nhau. Nếu đề yêu cầu một nghiệm trong khoảng cụ thể, phải **đưa khoảng/mục tiêu vào thuật toán**, không cho rằng Newton tự tìm “nghiệm quan trọng nhất”.

### Stagnation do số học

Khi `|f/f'|` nhỏ hơn độ phân giải của double tại x, tính `x−f/f'` có thể ra **đúng x** sau làm tròn, dù |f(x)| vẫn lớn. Không coi “x_new==x” là nghiệm; hãy báo tình trạng đứng yên và thay phương pháp/tăng độ chính xác.

## 7. Chọn tiêu chí dừng có nghĩa

Một solver thực dụng nên phân biệt **đạt ngưỡng**, **không thể tiếp tục**, và **hết vòng**:

- `fTolerance>0`: ngưỡng phần dư tuyệt đối |f(x)|.
- `xTolerance>0`: ngưỡng vị trí hoặc độ rộng bracket theo một quy tắc được mô tả.
- `maxIterations`: số bước tối đa.
- Ngưỡng bảo vệ khi `|f'(x)|` quá nhỏ, phụ thuộc thang đo hàm.
- Kiểm số hữu hạn `Double.isFinite` cho các đại lượng tính được.

### Residual không bất biến theo scale

Hai phương trình `f(x)=0` và `g(x)=10⁻²⁰f(x)=0` có **cùng nghiệm**, nhưng |g(x)| luôn nhỏ hơn |f(x)| theo hệ số 10⁻²⁰. Chọn một `fTolerance=10⁻¹²` cho cả hai có thể làm phương trình g chấp nhận một x rất xa nghiệm. Ví dụ f(x)=x−100, g(x)=10⁻²⁰(x−100), tại x=0 có |g(0)|=10⁻¹⁸≤10⁻¹², trong khi nghiệm thật là 100.

Muốn biết sai số vị trí, cần thêm thông tin, chẳng hạn:
- Cận dưới **`|f'(x)|≥m>0`** trên một đoạn thích hợp; khi có nghiệm duy nhất α và các điều kiện cần cho định lý giá trị trung bình, có thể suy `|x−α|≤|f(x)|/m`.
- Một **bracket chứa nghiệm** đủ hẹp.
- Thang đo chức năng hoặc tiêu chí tương đối được thiết kế cho ứng dụng.

### Bước lặp nhỏ không đủ

`|x_next−x|` nhỏ có thể do gần nghiệm, đạo hàm rất lớn, hoặc bị làm tròn. Nếu residual vẫn lớn, không nên in “thành công” chỉ vì x hầu như không đổi.

### Dừng do bracket hẹp

Nếu f liên tục trên [a,b] với f(a),f(b) trái dấu, ít nhất một nghiệm nằm trong đoạn. Nếu width=b−a≤w, **trung điểm** m cách **ít nhất một nghiệm** trong đoạn không quá w/2. Đây là thông tin về vị trí mạnh hơn residual-only.

Bản Java dùng:

**`b−a≤xTolerance·(1+max(|a|,|b|))`**.

Đây là tiêu chí pha tuyệt đối và tương đối. Với |a|,|b| lớn, không được diễn giải nó thành bảo đảm sai số tuyệt đối đúng bằng xTolerance; độ rộng được chấp nhận đã nhân hệ số scale.

## 8. Kẹp đoạn nghiệm: định lý giá trị trung gian

Nếu f **liên tục** trên [a,b] và hai giá trị f(a),f(b) khác dấu, tồn tại ít nhất một nghiệm α∈(a,b). Nếu một đầu có giá trị f=0, chính đầu đó là nghiệm và có thể trả ngay.

Trong code, kiểm dấu an toàn bằng:

~~~text
sameSign(u,v):
    return (u > 0 and v > 0) or (u < 0 and v < 0)
~~~

Không tính `f(a)*f(b)` rồi so với 0 nếu hai giá trị lớn: phép nhân double có thể tràn/underflow, tạo Infinity hoặc 0 sai. Kiểm dấu trực tiếp không cần nhân.

### Hai đầu cùng dấu có nhất thiết vô nghiệm không?

**Không.** Hàm `f(x)=x²−1` trên [−2,2] có f(−2)=3, f(2)=3, nhưng có hai nghiệm ±1 ở trong. Điều kiện đổi dấu là **điều kiện đủ**, không phải điều kiện cần. Một bộ giải chỉ nhận bracket trái dấu có quyền **từ chối đoạn**, nhưng không được kết luận phương trình toàn cục vô nghiệm.

### Vì sao cần f liên tục?

Nếu f có một **điểm gián đoạn** (ví dụ 1/(x−1)) trong khoảng, hai đầu có thể trái dấu dù không có nghiệm. Định lý giá trị trung gian chỉ áp dụng khi f liên tục trên toàn đoạn. Đừng coi kết quả chia đôi trên một điểm cực bất liên tục là nghiệm chỉ vì bracket ngày càng nhỏ.

## 9. Chia đôi (bisection): bộ giải dự phòng

Với bracket [a,b] có f trái dấu:

1. Lấy midpoint `m=a+(b−a)/2`.
2. Nếu f(m)=0, trả m.
3. Nếu f(a) và f(m) cùng dấu, thay a=m.
4. Ngược lại, thay b=m.
5. Tiếp tục đến khi bracket đủ nhỏ.

Mỗi vòng bisection có thể giảm độ rộng đoạn xuống **một nửa** trong số học lý tưởng, bảo toàn tồn tại nghiệm. Nếu bắt đầu với độ rộng L và muốn width≤ε, cần khoảng:

**`⌈log₂(L/ε)⌉`** vòng trong mô hình số học chính xác.

Độ hội tụ của bisection không nhanh bậc hai như Newton gần nghiệm đơn, nhưng **ổn định hơn** khi có bracket hợp lệ.

Dùng midpoint `a+(b−a)/2` thay vì `(a+b)/2` để tránh cộng a+b tràn khi hai đầu rất lớn nhưng hiệu vẫn hữu hạn. Nếu `b−a` đã không hữu hạn, phải từ chối hoặc chọn biểu diễn số khác; code mẫu kiểm điều này.

## 10. Newton có kẹp đoạn và fallback chia đôi

Một cách kết hợp hai phương pháp là **safeguarded Newton**. Ta luôn giữ [lo,hi] có nghiệm dựa trên đổi dấu. Mỗi vòng:

1. Tính f(x) tại điểm đang khảo sát x.
2. Nếu |f(x)|≤fTol, trả x với lý do **RESIDUAL**.
3. Nếu bracket hẹp, trả midpoint với lý do **WIDTH**.
4. Nếu hết maxIterations, báo lỗi.
5. Dùng dấu f(x) để thay lo=x hoặc hi=x, **giữ đổi dấu**.
6. Lấy midpoint của bracket mới làm ứng viên dự phòng.
7. Nếu đạo hàm hữu hạn và đủ lớn, thử `trial=x−f(x)/f'(x)`.
8. Chỉ nhận trial nếu hữu hạn, nằm nghiêm ngặt trong bracket mới và có `|f(trial)|≤0,8|f(x)|`; ngược lại dùng midpoint.
9. Xét tiếp tại x mới.

### Điều kiện giảm 20% là gì?

Đây là một **safeguard được chọn cho ví dụ**, không phải định nghĩa Newton chuẩn hoặc hằng số tối ưu cho mọi bài. Nó buộc bước Newton được chấp nhận phải cải thiện residual rõ rệt, giúp tránh chấp nhận những bước gần như đứng yên. Đổi lại, mỗi lần xét trial có thể phải **đánh giá f thêm một lần**. Có thể dùng line search, trust region hoặc các quy tắc chấp nhận khác trong solver sản xuất.

### Bất biến quan trọng

Nếu f liên tục và bracket đang có hai đầu trái dấu, sau khi lấy x nằm trong bracket và cập nhật đầu có cùng dấu f(x), bracket còn lại vẫn chứa ít nhất một nghiệm. Bước Newton đề xuất **không được phép phá đoạn này**; nó chỉ là một **điểm khảo sát** tiếp theo nếu nằm đúng bên trong và đủ hữu ích. Nếu không, midpoint chia đôi là một điểm khảo sát hợp lệ.

### Có thể bảo đảm hội tụ tuyệt đối không?

Safeguarded Newton giảm nhiều rủi ro của Newton thuần và có đường dự phòng khi bước Newton không an toàn. Tuy nhiên chương trình vẫn có giới hạn vòng, số học double, yêu cầu liên tục và đánh giá f hữu hạn, cùng rủi ro dừng quá sớm do residual tolerance. Không nên gọi bất cứ solver nào “bảo đảm nghiệm chính xác” mà không ghi rõ giả thiết và tiêu chí.

## 11. Pseudocode hai phiên bản

### Newton thuần

~~~text
plainNewton(f, df, x0):
    x = x0
    for k = 0..maxIterations:
        fx = f(x)
        if fx is not finite: fail
        if abs(fx) <= fTolerance: return x
        if k == maxIterations: fail

        slope = df(x)
        if not finite or too small: fail

        next = x - fx/slope
        if next is not finite or next == x: fail
        x = next
~~~

### Newton có bracket

~~~text
safeNewton(f, df, a, b, x0):
    check endpoints finite, a<b, positive tolerances
    fa = f(a), fb = f(b)
    if fa == 0: return a, ENDPOINT
    if fb == 0: return b, ENDPOINT
    require opposite endpoint signs

    x = x0 if strictly inside (a,b), else midpoint(a,b)

    for k = 0..maxIterations:
        fx = f(x); require finite
        if abs(fx) <= fTolerance: return x, RESIDUAL
        if width(a,b) sufficiently small:
            return midpoint(a,b), WIDTH
        if k == maxIterations: fail

        if sign(fx) == sign(fa):
            a = x; fa = fx
        else:
            b = x; fb = fx

        next = midpoint(a,b)
        slope = df(x)
        if slope finite and abs(slope) large enough:
            trial = x-fx/slope
            if trial is finite and strictly inside (a,b):
                ft = f(trial)
                if ft finite and abs(ft) <= 0.8*abs(fx):
                    next = trial
        x = next
~~~

## 12. Java 17+ đầy đủ: hai solver, bisection oracle và kiểm thử

Chương trình dưới đây là **một tệp Java chạy độc lập**, không dùng thư viện ngoài JDK:

- `DoubleUnaryOperator` chứa f và f' dưới dạng lambda.
- `plainNewton` theo công thức Newton thuần, báo lỗi đạo hàm nhỏ, giá trị không hữu hạn, bước đứng và quá số vòng.
- `safeguardedNewton` giữ bracket và có chia đôi dự phòng; `SolveResult` lưu nghiệm xấp xỉ, residual, vòng lặp, **lý do dừng** và hai đầu bracket ở thời điểm trả.
- `bisectionOracle` **không dùng đạo hàm**, là chuẩn kiểm thử độc lập.
- `traceSqrt2` in 5 trạng thái.
- `randomizedChecks` sinh 1200 hàm bậc ba có đạo hàm dương và nghiệm biết trước, so kết quả solver với nghiệm thật và bisection.

**Lưu ý về ngưỡng:** `DERIVATIVE_TOL=1e−14` là ví dụ tuyệt đối cho bài học, không phải ngưỡng phù hợp với mọi thang đo. Với ứng dụng vật lý hay tài chính, cần chọn ngưỡng theo đơn vị f và x. `fTolerance=1e−12` có thể vẫn cho vị trí kém chính xác khi f phẳng, như ví dụ f=x³.

Lưu thành **`NewtonNonlinearDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Random;
import java.util.function.DoubleUnaryOperator;

public final class NewtonNonlinearDemo {
    private static final double DERIVATIVE_TOL = 1e-14;

    private record SolveResult(
            double root,
            double residual,
            int iterations,
            String reason,
            double left,
            double right) {}

    private static double finite(double value, String label) {
        if (!Double.isFinite(value)) {
            throw new ArithmeticException(
                    "Non-finite " + label);
        }
        return value;
    }

    private static boolean sameSign(double a, double b) {
        return (a > 0 && b > 0) || (a < 0 && b < 0);
    }

    static double plainNewton(
            DoubleUnaryOperator f,
            DoubleUnaryOperator df,
            double initial,
            double fTol,
            int maxIterations) {

        if (f == null || df == null
                || !Double.isFinite(initial)
                || !Double.isFinite(fTol)
                || fTol <= 0
                || maxIterations < 0) {
            throw new IllegalArgumentException(
                    "Invalid plain Newton parameters");
        }

        double x = initial;
        for (int k = 0; k <= maxIterations; k++) {
            double fx = finite(f.applyAsDouble(x), "f(x)");
            if (Math.abs(fx) <= fTol) {
                return x;
            }
            if (k == maxIterations) {
                break;
            }

            double derivative = finite(
                    df.applyAsDouble(x), "f'(x)");
            if (Math.abs(derivative) <= DERIVATIVE_TOL) {
                throw new ArithmeticException(
                        "Derivative too small");
            }

            double next = finite(
                    x - fx / derivative, "Newton iterate");
            if (next == x) {
                throw new ArithmeticException(
                        "Iteration stagnated");
            }
            x = next;
        }
        throw new IllegalStateException(
                "Plain Newton reached iteration limit");
    }

    static SolveResult safeguardedNewton(
            DoubleUnaryOperator f,
            DoubleUnaryOperator df,
            double left,
            double right,
            double initial,
            double fTol,
            double xTol,
            int maxIterations) {

        if (f == null || df == null
                || !Double.isFinite(left)
                || !Double.isFinite(right)
                || !Double.isFinite(initial)
                || !(left < right)
                || !Double.isFinite(right - left)
                || !Double.isFinite(fTol) || fTol <= 0
                || !Double.isFinite(xTol) || xTol <= 0
                || maxIterations < 1) {
            throw new IllegalArgumentException(
                    "Invalid safeguarded Newton parameters");
        }

        double lo = left;
        double hi = right;
        double fLo = finite(f.applyAsDouble(lo), "f(left)");
        double fHi = finite(f.applyAsDouble(hi), "f(right)");

        if (fLo == 0.0) {
            return new SolveResult(
                    lo, 0.0, 0, "ENDPOINT", lo, hi);
        }
        if (fHi == 0.0) {
            return new SolveResult(
                    hi, 0.0, 0, "ENDPOINT", lo, hi);
        }
        if (sameSign(fLo, fHi)) {
            throw new IllegalArgumentException(
                    "Endpoint signs do not bracket a root");
        }

        double x = (initial > lo && initial < hi)
                ? initial : lo + (hi - lo) / 2.0;

        for (int k = 0; k <= maxIterations; k++) {
            double fx = finite(f.applyAsDouble(x), "f(x)");
            if (Math.abs(fx) <= fTol) {
                return new SolveResult(
                        x, Math.abs(fx), k, "RESIDUAL", lo, hi);
            }

            double width = hi - lo;
            double scale = 1.0 + Math.max(
                    Math.abs(lo), Math.abs(hi));
            if (width <= xTol * scale) {
                double mid = lo + width / 2.0;
                double fMid = finite(
                        f.applyAsDouble(mid), "f(mid)");
                return new SolveResult(
                        mid, Math.abs(fMid),
                        k, "WIDTH", lo, hi);
            }

            if (k == maxIterations) {
                throw new IllegalStateException(
                        "Safeguarded Newton iteration limit");
            }

            // Update the bracket without multiplying fLo*fx.
            if (sameSign(fLo, fx)) {
                lo = x;
                fLo = fx;
            } else {
                hi = x;
                fHi = fx;
            }

            // Bisection fallback is always available.
            double next = lo + (hi - lo) / 2.0;
            double derivative = df.applyAsDouble(x);

            if (Double.isFinite(derivative)
                    && Math.abs(derivative) > DERIVATIVE_TOL) {
                double trial = x - fx / derivative;
                if (Double.isFinite(trial)
                        && trial > lo && trial < hi) {
                    double fTrial = f.applyAsDouble(trial);
                    if (Double.isFinite(fTrial)
                            && Math.abs(fTrial)
                               <= 0.8 * Math.abs(fx)) {
                        next = trial;
                    }
                }
            }

            x = next;
        }
        throw new AssertionError("Unreachable");
    }

    // Independent reference solver: bisection only.
    static double bisectionOracle(
            DoubleUnaryOperator f,
            double left,
            double right,
            int steps) {

        double lo = left;
        double hi = right;
        double fLo = finite(f.applyAsDouble(lo), "f(left)");

        if (fLo == 0.0) {
            return lo;
        }
        double fHi = finite(f.applyAsDouble(hi), "f(right)");
        if (fHi == 0.0) {
            return hi;
        }
        if (sameSign(fLo, fHi)) {
            throw new IllegalArgumentException(
                    "Bisection requires opposite signs");
        }

        for (int i = 0; i < steps; i++) {
            double mid = lo + (hi - lo) / 2.0;
            if (mid == lo || mid == hi) {
                return mid;
            }

            double fm = finite(f.applyAsDouble(mid), "f(mid)");
            if (fm == 0.0) {
                return mid;
            }
            if (sameSign(fLo, fm)) {
                lo = mid;
                fLo = fm;
            } else {
                hi = mid;
            }
        }
        return lo + (hi - lo) / 2.0;
    }

    private static void printRoot(
            String label, SolveResult result) {
        System.out.printf(
                Locale.ROOT, "%s: %.12f%n",
                label, result.root());
    }

    private static void traceSqrt2() {
        System.out.println("Newton trace sqrt(2):");
        double x = 1.5;

        for (int k = 0; k <= 4; k++) {
            double fx = x * x - 2.0;
            System.out.printf(Locale.ROOT,
                    "k=%d x=%.12f f(x)=%.12f%n",
                    k, x, fx);

            if (k < 4) {
                x = x - fx / (2.0 * x);
            }
        }
    }

    private static void checkExpectedFailures() {
        boolean zeroDerivative = false;
        try {
            plainNewton(
                    x -> x * x * x - 1.0,
                    x -> 3.0 * x * x,
                    0.0, 1e-12, 50);
        } catch (ArithmeticException expected) {
            zeroDerivative = true;
        }
        if (!zeroDerivative) {
            throw new AssertionError(
                    "Missing derivative-zero guard");
        }
        System.out.println("Zero derivative: rejected");

        boolean invalidBracket = false;
        try {
            safeguardedNewton(
                    x -> x * x + 1.0,
                    x -> 2.0 * x,
                    -1.0, 1.0, 0.0,
                    1e-12, 1e-12, 50);
        } catch (IllegalArgumentException expected) {
            invalidBracket = true;
        }
        if (!invalidBracket) {
            throw new AssertionError(
                    "Missing opposite-sign guard");
        }
        System.out.println("Invalid bracket: rejected");
    }

    private static void randomizedChecks() {
        Random rng = new Random(4362026L);

        for (int i = 0; i < 1200; i++) {
            final double target =
                    -4.0 + 8.0 * rng.nextDouble();
            final double slope =
                    0.25 + 4.0 * rng.nextDouble();
            final double constant =
                    target * target * target
                    + slope * target;

            // Unique known root target; derivative > 0.
            DoubleUnaryOperator f =
                    x -> x * x * x + slope * x - constant;
            DoubleUnaryOperator df =
                    x -> 3.0 * x * x + slope;
            double start = -6.0 + 12.0 * rng.nextDouble();

            SolveResult got = safeguardedNewton(
                    f, df, -6.0, 6.0, start,
                    1e-12, 1e-12, 100);
            double oracle =
                    bisectionOracle(f, -6.0, 6.0, 120);

            if (Math.abs(got.root() - target) > 1e-8
                    || Math.abs(got.root() - oracle) > 1e-8) {
                throw new AssertionError(
                        "Random cubic mismatch at " + i);
            }
        }

        System.out.println(
                "Random monotone cubics: 1200 PASS");
    }

    public static void main(String[] args) {
        traceSqrt2();

        double plain = plainNewton(
                x -> x * x - 2.0,
                x -> 2.0 * x,
                1.5, 1e-12, 50);
        System.out.printf(Locale.ROOT,
                "Plain Newton sqrt(2): %.12f%n", plain);

        printRoot("Safeguarded sqrt(2)",
                safeguardedNewton(
                        x -> x * x - 2.0,
                        x -> 2.0 * x,
                        1.0, 2.0, 1.5,
                        1e-12, 1e-12, 100));

        printRoot("Safeguarded cbrt(2)",
                safeguardedNewton(
                        x -> x * x * x - 2.0,
                        x -> 3.0 * x * x,
                        1.0, 2.0, 1.0,
                        1e-12, 1e-12, 100));

        printRoot("Safeguarded cos(x)-x",
                safeguardedNewton(
                        x -> Math.cos(x) - x,
                        x -> -Math.sin(x) - 1.0,
                        0.0, 1.0, 0.5,
                        1e-12, 1e-12, 100));

        printRoot("Safeguarded exp(-x)-x",
                safeguardedNewton(
                        x -> Math.exp(-x) - x,
                        x -> -Math.exp(-x) - 1.0,
                        0.0, 1.0, 0.6,
                        1e-12, 1e-12, 100));

        printRoot("Oscillating cubic safeguarded",
                safeguardedNewton(
                        x -> x * x * x - 2.0 * x + 2.0,
                        x -> 3.0 * x * x - 2.0,
                        -2.0, 0.0, -1.5,
                        1e-12, 1e-12, 100));

        printRoot("Flat cubic residual-only",
                safeguardedNewton(
                        x -> x * x * x,
                        x -> 3.0 * x * x,
                        -1.0, 1.0, 0.7,
                        1e-12, 1e-12, 100));

        printRoot("Endpoint root",
                safeguardedNewton(
                        x -> x - 3.0,
                        x -> 1.0,
                        3.0, 5.0, 4.0,
                        1e-12, 1e-12, 100));

        checkExpectedFailures();
        randomizedChecks();
    }
}
~~~

Biên dịch và chạy bằng **Java 17 trở lên**:

~~~bash
javac -encoding UTF-8 NewtonNonlinearDemo.java
java NewtonNonlinearDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
Newton trace sqrt(2):
k=0 x=1.500000000000 f(x)=0.250000000000
k=1 x=1.416666666667 f(x)=0.006944444444
k=2 x=1.414215686275 f(x)=0.000006007305
k=3 x=1.414213562375 f(x)=0.000000000005
k=4 x=1.414213562373 f(x)=0.000000000000
Plain Newton sqrt(2): 1.414213562373
Safeguarded sqrt(2): 1.414213562373
Safeguarded cbrt(2): 1.259921049895
Safeguarded cos(x)-x: 0.739085133215
Safeguarded exp(-x)-x: 0.567143290410
Oscillating cubic safeguarded: -1.769292354239
Flat cubic residual-only: 0.000093560028
Endpoint root: 3.000000000000
Zero derivative: rejected
Invalid bracket: rejected
Random monotone cubics: 1200 PASS
~~~

### Đọc kỹ kết quả

**Năm dòng trace** thể hiện Newton giảm residual của f=x²−2 cực nhanh gần √2. Dòng in f(x)=0 đến 12 chữ số sau dấu thập phân **không** có nghĩa đã biểu diễn nghiệm chính xác vô hạn.

**Safeguarded sqrt(2)** và **cbrt(2)** đều dùng [1,2]. Với cos(x)−x dùng [0,1], vì f(0)=1>0 và f(1)=cos(1)−1<0. Với e⁻ˣ−x dùng [0,1], f(0)=1>0, f(1)=e⁻¹−1<0. Cả hai hàm sau có đạo hàm âm trên đoạn nên nghiệm duy nhất.

**Oscillating cubic safeguarded** cho nghiệm âm khoảng −1,769292354239 nhờ bracket [−2,0]. Nếu chạy Newton thuần từ x₀=0, thuật toán lặp 0↔1 và không tiến tới nghiệm này.

**Flat cubic residual-only** trả 0,000093560028 cho f=x³, nghiệm thật 0. Giá trị này cách nghiệm gần 10⁻⁴ dù residual đã xuống dưới 10⁻¹². Đây là một **phản ví dụ hữu ích cho việc nhầm residual với sai số nghiệm**.

**Endpoint root** trả chính xác đầu trái 3 khi f(x)=x−3, không yêu cầu hai đầu có dấu trái nhau trong trường hợp endpoint đã là nghiệm.

**Zero derivative** minh họa hàm f=x³−1 tại x₀=0: đạo hàm bằng 0 nhưng chưa phải nghiệm, nên Newton thuần báo lỗi. **Invalid bracket** minh họa x²+1 luôn dương trên [−1,1], không đạt điều kiện dấu.

**Random monotone cubics** chỉ in PASS sau 1200 phương trình test: mỗi phương trình có nghiệm thật `r` đã biết và có f'(x)>0 trên ℝ, nên nghiệm duy nhất; bộ giải bisection độc lập dùng cùng f nhưng không sử dụng đạo hàm Newton.

## 13. Kiểm thử theo tính chất thay vì chỉ chạy √2

Kiểm thử Newton phải gồm cả **nghiệm đẹp**, **nghiệm khó** và **trường hợp phải từ chối**.

### Sinh hàm có nghiệm biết trước

Chọn ngẫu nhiên `r∈[−4,4]` và `c∈[0,25;4,25]`, tạo:

**`f(x)=x³+cx−(r³+cr)`**.

Khi ấy f(r)=0; đạo hàm `f'(x)=3x²+c>0` mọi x, nên **r là nghiệm thực duy nhất**. Chọn bracket [−6,6] và x₀ ngẫu nhiên trong đoạn. So nghiệm trả từ safeguarded Newton với:

- **r biết trước**, không được suy bằng Newton.
- Nghiệm từ **bisection oracle**, không dùng đạo hàm.

Sai khác ≤10⁻⁸ là ngưỡng kiểm thử phù hợp ở miền số này; nó **khác** fTolerance nội bộ. Test cũng nên hoán đổi nhiều điểm bắt đầu để phát hiện vùng hội tụ và bước fallback.

Trong một phép kiểm tra mô hình độc lập, **6.500 trường hợp bậc ba đơn điệu** đã khớp nghiệm biết trước và bisection độc lập, không có sai khác vượt ngưỡng 10⁻⁸. Kèm các ca √2, ∛2, cos(x)−x, e⁻ˣ−x, chu kỳ và nghiệm phẳng, điều đó hỗ trợ kiểm tra triển khai nhưng **không thay thế chứng minh toán học**.

### Những trường hợp phải kiểm riêng

| Đầu vào | Kết quả mong đợi |
|---|---|
| f(x₀)=0 | Trả nghiệm trước khi kiểm f' |
| f'(x₀)=0, f(x₀)≠0, Newton thuần | Báo lỗi |
| Hàm không đổi dấu giữa hai đầu | Không nhận là bracket hợp lệ |
| Một đầu đúng nghiệm | Trả ENDPOINT |
| f/df null | Từ chối |
| a≥b hoặc có NaN/Infinity | Từ chối |
| fTolerance/xTolerance không dương | Từ chối |
| Newton candidate ra ngoài bracket | Dùng midpoint |
| Newton candidate không giảm đủ residual | Dùng midpoint |
| Số vòng vượt maxIterations | Báo không hội tụ |
| Bước mới bằng đúng x do làm tròn | Newton thuần báo stagnation |
| Nghiệm bội, f rất phẳng | Không nhầm residual nhỏ với vị trí chính xác |

Không được xem một kết quả chỉ có residual nhỏ là đã xác minh vị trí; nên bổ sung bracket, oracle độc lập, hoặc cận sai số theo đạo hàm.

## 14. Có thể làm gì khi không có đạo hàm giải tích?

### Sai phân tiến

**`f'(x)≈[f(x+h)−f(x)]/h`**.

Với hàm đủ trơn, sai số cắt cụt thường bậc O(h). Chọn h quá lớn khiến đạo hàm thiếu chính xác, h quá nhỏ khiến phép trừ hai số gần nhau **mất chữ số có nghĩa**.

### Sai phân trung tâm

**`f'(x)≈[f(x+h)−f(x−h)]/(2h)`**.

Khi f đủ trơn, sai số cắt cụt thường O(h²), nhưng cần **hai lần đánh giá f** và bảo đảm x±h đều thuộc miền xác định. Không chọn h nhỏ tới mức x+h==x trong double.

### Tự động vi phân (automatic differentiation)

AD áp quy tắc đạo hàm qua chuỗi phép toán của chương trình để tính đạo hàm theo máy mà không dùng sai phân. Với mô hình dài, AD hữu ích, nhưng không có nghĩa mọi lambda Java tùy ý đều tự có đạo hàm miễn phí.

### Phương pháp secant

Khi không có f', có thể thay đạo hàm bằng độ dốc dây cung qua hai điểm:

**`xₖ₊₁=xₖ−f(xₖ)(xₖ−xₖ₋₁)/[f(xₖ)−f(xₖ₋₁)]`**.

Đây là **secant method**, không phải Newton với đạo hàm chính xác. Khi thuận lợi, bậc hội tụ siêu tuyến tính khoảng 1,618; nhưng mẫu số vẫn có thể rất nhỏ, phương pháp cũng không tự bảo đảm bracket.

## 15. Newton giảm bước và mở rộng nhiều biến

### Damped Newton

Khi bước Newton nguyên vẹn quá mạnh, dùng:

**`xₖ₊₁=xₖ+λₖΔₖ`**, trong đó `Δₖ=−f(xₖ)/f'(xₖ)`, **`0<λₖ≤1`**.

Có thể thử λ=1, sau đó giảm λ theo backtracking cho tới khi bước nằm trong miền và đáp ứng điều kiện giảm residual phù hợp. Kỹ thuật này có thể giúp khi f có miền hẹp hoặc mô hình tuyến tính kém tin cậy ở xa nghiệm. Nó **không tự tạo bảo đảm hội tụ toàn cục** nếu không có thêm điều kiện.

**Trust region** giới hạn độ dài bước trong vùng được coi là tin cậy đối với mô hình địa phương; các phương pháp tối ưu số và giải hệ phi tuyến dùng ý tưởng này rất nhiều.

### Newton cho hệ phương trình

Với vector biến `x∈ℝᵈ` và hệ `F(x)=0`, đạo hàm scalar được thay bằng **ma trận Jacobi** `J_F(x)`. Tại vòng k, giải:

**`J_F(xₖ)Δₖ=−F(xₖ)`**, rồi cập nhật **`xₖ₊₁=xₖ+Δₖ`**.

Không cần tính ma trận nghịch đảo tường minh; thường giải hệ bằng LU/QR hoặc thuật toán tuyến tính phù hợp. Nếu J tại nghiệm suy biến/gần suy biến, bậc hội tụ và ổn định số học có thể kém.

Ví dụ:

**`F₁(x,y)=x²+y²−5`**,  
**`F₂(x,y)=x−y−1`**,

có Jacobian:

~~~text
[ 2x  2y ]
[  1  -1 ]
~~~

Hai nghiệm thật là **(2,1)** và **(−1,−2)**. Phiên bản Newton hệ có thể hội tụ tới nghiệm nào phụ thuộc điểm bắt đầu. **Mã Java trong bài chỉ giải một biến**, không tự giải hệ đa chiều.

## 16. Phân tích chi phí

Gọi K là số vòng lặp:

- Newton thuần đánh giá f, f' mỗi vòng và thực hiện O(1) phép toán double ⇒ **O(K)** nếu đánh giá f/df O(1), bộ nhớ O(1).
- Safeguarded Newton đôi khi phải đánh giá f tại trial và dùng midpoint, nhưng vẫn O(K) nếu mỗi f/df O(1), bộ nhớ O(1).
- Nếu f là mô phỏng chi phí C_f và f' chi phí C_df, tổng thời gian gần **O(K(C_f+C_df))**, cộng những lần thử hàm bổ sung.
- Bisection thuần có thể cần khoảng **O(log((b−a)/ε))** vòng để thu hẹp bracket về ε, khi có số học đủ chính xác.
- Hội tụ bậc hai **cục bộ** không tự cho giới hạn K toàn cục từ x₀ tùy ý.

Các thư viện số học công nghiệp có thể dùng **Brent** khi có bracket và không cần đạo hàm. Brent kết hợp nội suy với bảo toàn bracket; không phải chính xác thuật toán safeguarded Newton với đạo hàm và ngưỡng 0,8 trong ví dụ.

## 17. Lỗi thường gặp

1. Quên dấu trừ trong công thức Newton.
2. Tính sai đạo hàm hoặc dùng sai đơn vị radian/degree.
3. Không kiểm nghiệm trước khi tính f', làm lỗi tại nghiệm bội.
4. Chia cho f'=0 khi f chưa bằng 0.
5. Không xử lý f' gần 0, gây bước nhảy quá lớn.
6. Tin rằng Newton hội tụ với mọi điểm x₀.
7. Lẫn lộn bậc hội tụ hai và Big-O của thời gian chương trình.
8. Áp định lý bậc hai cho nghiệm bội f'(α)=0.
9. Dùng residual nhỏ như chứng nhận vị trí gần nghiệm.
10. Không xét scale/đơn vị của fTolerance.
11. Dùng fTolerance=0 và chờ đúng f(x)==0 trong double.
12. Chỉ kiểm |x_new−x| mà không xét f(x).
13. Không đặt maxIterations.
14. Không phát hiện NaN/Infinity.
15. Không kiểm x_new nằm trong miền f.
16. Không phát hiện x_new==x do làm tròn.
17. Chạy x₀=0 cho f=x²−2 rồi kết luận phương trình không có nghiệm.
18. Bỏ qua phản ví dụ chu kỳ 0↔1.
19. Dùng hai đầu cùng dấu rồi tuyên bố không có nghiệm bên trong.
20. Áp định lý giá trị trung gian cho hàm gián đoạn.
21. Nhân f(a)*f(b) để kiểm dấu, gây tràn hoặc underflow.
22. Không trả nghiệm khi một endpoint có f=0.
23. Cập nhật sai endpoint của bracket, làm mất nghiệm.
24. Cho Newton trial ra ngoài bracket dù solver đã cam kết kẹp đoạn.
25. Clip trial thành endpoint rồi kẹt ở biên.
26. Dùng midpoint (a+b)/2 không xét overflow.
27. Cho rằng stopReason=WIDTH đồng nghĩa residual cực nhỏ.
28. Cho rằng stopReason=RESIDUAL đồng nghĩa sai số vị trí cực nhỏ.
29. Không tách absolute/relative tolerance.
30. Dùng đạo hàm sai phân với h quá nhỏ, x+h==x.
31. Dùng đạo hàm sai phân trung tâm ở ngoài miền x>0.
32. Lẫn lộn secant với Newton có đạo hàm.
33. Tính nghịch đảo Jacobian tường minh khi không cần.
34. Không kiểm Jacobian suy biến ở bài hệ nhiều biến.
35. So kết quả với chính một bản Newton tương tự thay vì oracle độc lập.
36. Chỉ test √2, không test 0/derivative nhỏ/flat root.
37. Không thử nhiều x₀ cho cùng f.
38. Không kiểm pure function khi solver gọi f nhiều lần.
39. Không giới hạn chi phí f khi hàm tốn tài nguyên.
40. Không nêu rõ lý do dừng trong API, khiến người dùng hiểu nhầm độ tin cậy.

## 18. Bài tập luyện tập

**Bài 1 — Tìm √5.** Với f=x²−5, f'=2x và x₀=2, tính bốn bước Newton bằng tay rồi so với Math.sqrt(5).

**Bài 2 — Căn bậc ba.** Dùng f=x³−7; xác định bracket [1,2] có đúng đổi dấu không, rồi chọn [1,3] và tính nghiệm ∛7.

**Bài 3 — Chu kỳ.** Chứng minh Newton từ x₀=0 cho f=x³−2x+2 lặp 0,1,0,1. Dùng bracket [−2,0] để tìm nghiệm âm.

**Bài 4 — Nghiệm bội.** Chứng minh f=(x−1)² cho e_next=e/2, rồi thử Newton điều chỉnh với m=2.

**Bài 5 — Residual và vị trí.** Cho g(x)=10⁻²⁰(x−100) và fTolerance=10⁻¹². Giải thích tại sao x₀=0 có thể được chấp nhận sai về vị trí, đề xuất cách chuẩn hóa.

**Bài 6 — Sai phân.** So đạo hàm giải tích và sai phân trung tâm của f(x)=sin x−x/2 tại x=1 với h=10⁻²,10⁻⁴,10⁻⁸,10⁻¹².

**Bài 7 — Bisection.** Tính số lần chia đôi cần cho bracket ban đầu [0,1] để width≤10⁻¹⁰ khi giải cos x−x=0.

**Bài 8 — Safeguard tùy chỉnh.** Thay ngưỡng giảm residual 20% bằng backtracking λ hoặc một trust-region 1D và thử nhiều điểm x₀.

**Bài 9 — Test sinh nghiệm.** Sinh 5000 phương trình f=x³+cx−(r³+cr), c>0, so solver với r và bisection.

**Bài 10 — Newton hệ.** Lập Jacobian của F₁=x²+y²−5, F₂=x−y−1; thử một bước từ (1,1), đối chiếu các nghiệm (2,1), (−1,−2).

## 19. Checklist trước khi sử dụng

- Đã xác định rõ f(x)=0, **miền xác định** và nghiệm muốn tìm?
- Đạo hàm f' đúng công thức và đúng đơn vị?
- Đã có x₀ đủ hợp lý hoặc bracket [a,b] có đổi dấu của hàm liên tục?
- Đã phân biệt nghiệm đơn và nghiệm bội?
- Có kiểm f(x) trước khi chia cho f'?
- Có bảo vệ đạo hàm bằng 0/gần 0?
- Có phát hiện NaN, Infinity và bước bị đứng?
- Có giới hạn số vòng lặp?
- Có báo **lý do dừng** chứ không chỉ một số?
- Có phân biệt residual, bước nhỏ và độ rộng bracket?
- Có lựa chọn fTolerance/xTolerance theo thang của bài?
- Nếu dùng safeguarded Newton, có giữ bracket đổi dấu?
- Nếu trial không hợp lệ hoặc không cải thiện, có fallback midpoint?
- Có kiểm endpoint là nghiệm trước khi yêu cầu đổi dấu?
- Có đối chiếu bằng một thuật toán **không dùng đạo hàm**?
- Có thử các ca nghiệm bội, chu kỳ, miền hẹp và dữ liệu xấu?
- Nếu giải hệ, có dùng Jacobian và bộ giải hệ tuyến tính thích hợp?
- Có tính cả chi phí f/df thật và số lần gọi thêm?

**Kết luận:** Newton dùng tiếp tuyến để biến bài toán phi tuyến thành một bước hiệu chỉnh `x_next=x−f(x)/f'(x)`. Với nghiệm đơn, hàm đủ trơn và x₀ đủ gần, thuật toán có thể đạt **hội tụ bậc hai cục bộ**. Nhưng công thức không tự bảo vệ trước đạo hàm nhỏ, chu kỳ, phân kỳ, hàm phẳng hoặc ngưỡng dừng thiếu ý nghĩa. Khi có thể tìm một đoạn đổi dấu, kết hợp **Newton và chia đôi** sẽ giữ thêm thông tin về vị trí nghiệm, đồng thời tận dụng những bước Newton nhanh ở vùng thuận lợi. Một lời giải tốt phải nêu rõ **giả thiết, chất lượng xấp xỉ, điều kiện dừng và kiểm thử độc lập**, không chỉ in ra một số có nhiều chữ số thập phân.
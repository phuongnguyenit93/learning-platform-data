# Tích phân số bằng quy tắc hình thang và Simpson

**Tích phân xác định** của một hàm trên đoạn [a,b] mô tả diện tích có dấu, lượng tích lũy hoặc tổng liên tục của một đại lượng biến thiên. Trong nhiều bài toán **Thuật toán số** thuộc Computer Science Algorithms, ta biết cách **đánh giá hàm f(x)** nhưng không có nguyên hàm đơn giản, hoặc dữ liệu chỉ cung cấp các mẫu đo tại những vị trí x nhất định. Khi ấy, **tích phân số (numerical integration, quadrature)** giúp ước lượng tích phân bằng một tổng hữu hạn có thể tính trên máy.

Bài **“Tích phân số bằng quy tắc hình thang và Simpson”** giới thiệu hai phương pháp nền tảng:

- **Quy tắc hình thang (trapezoidal rule):** xấp xỉ đồ thị bằng các đoạn thẳng, có sai số toàn cục thường ở bậc **O(h²)** khi hàm đủ trơn.
- **Quy tắc Simpson 1/3:** xấp xỉ bằng các cung parabol trên từng **hai khoảng con**, đạt sai số toàn cục thường ở bậc **O(h⁴)** khi có đạo hàm bậc bốn thích hợp.

Bài còn giải thích **Simpson ghép**, điều kiện **số khoảng con phải chẵn**, công thức sai số và giả thiết về độ trơn, cách tinh chỉnh bước, **Simpson thích nghi (adaptive Simpson)**, hạn chế khi hàm gián đoạn/dao động mạnh, ổn định số thực, cùng chương trình Java 17+ đầy đủ. Chương trình có các phép kiểm thử với tích phân giải tích, so đúng đa thức bậc thấp, kiểm tra tốc độ hội tụ và xử lý đầu vào không hợp lệ.

## 1. Phát biểu bài toán

Cho một hàm số thực f có thể đánh giá tại các điểm trong một khoảng, và hai cận tích phân a,b. Cần tính gần đúng:

~~~text
I = integral_a^b f(x) dx.
~~~

Tích phân có tính **định hướng**:

~~~text
integral_b^a f(x) dx = -integral_a^b f(x) dx.
integral_a^a f(x) dx = 0.
~~~

Các công thức dưới đây đầu tiên giả định **a<b**, f đủ trơn và các nút lấy mẫu được phân bố **đều**. Chương trình cho phép b<a bằng cách hoán đổi hai cận, tính tích phân trên đoạn tăng rồi đổi dấu kết quả. Nếu a=b, trả 0 với các tham số điều khiển hợp lệ.

Cần phân biệt hai tình huống:

1. **f được cho bằng công thức / callback:** có thể đánh giá ở x bất kỳ trong miền, thuận tiện cho tăng số khoảng chia và Simpson thích nghi.
2. **f chỉ được cho ở vài điểm đo cố định:** chỉ áp dụng được các quy tắc dựa trên những điểm thực sự có; không thể tự giả định biết f ở trung điểm hoặc nút mới nếu chưa đo hay nội suy hợp lệ.

Trong bài Java, f là **DoubleUnaryOperator**, nghĩa là có thể gọi f.applyAsDouble(x) để đánh giá tại bất kỳ nút nào cần thiết.

## 2. Tích phân Riemann và ý tưởng lấy mẫu

Chia đoạn [a,b] thành n khoảng con có độ dài bằng nhau:

~~~text
h = (b-a)/n.
x_i = a+i*h, i=0,1,...,n.

a=x_0 < x_1 < ... < x_n=b.
~~~

Một tổng Riemann lấy mẫu và nhân giá trị f tại một điểm trong mỗi khoảng con với chiều rộng h. Các quy tắc có chất lượng cao hơn sẽ dùng nhiều điểm/nhiều trọng số để tận dụng hình dạng cục bộ của đồ thị.

Hình thang xem f gần như **tuyến tính** giữa hai nút. Simpson dùng **đa thức nội suy bậc hai** qua ba nút liên tiếp. Cả hai đều là phương pháp **Newton–Cotes đóng**, nghĩa là dùng cả các điểm đầu mút của những khoảng đang xấp xỉ.

Độ chính xác chịu ảnh hưởng đồng thời của **độ dài bước h**, độ trơn của f và sai số tính toán kiểu double. Không có quy tắc phổ quát “càng tăng n thì luôn chính xác hơn” cho mọi dữ liệu thực tế vì cuối cùng việc làm tròn và lỗi lấy mẫu có thể chi phối.

## 3. Quy tắc hình thang trên một khoảng

Trên [u,v], thay đường cong y=f(x) bằng đoạn thẳng nối (u,f(u)) và (v,f(v)). Diện tích có dấu của hình thang tương ứng:

~~~text
T(u,v) = (v-u) * [f(u)+f(v)] / 2.
~~~

Ví dụ với f(x)=x² trên [0,1], dùng một hình thang:

~~~text
T(0,1) = 1 * (0²+1²)/2 = 1/2.
I = integral_0^1 x² dx = 1/3.
~~~

Sai số này khá lớn vì f(x)=x² không phải đường thẳng. Nếu chia nhỏ đoạn thành nhiều khoảng, từng đoạn tuyến tính bám đồ thị tốt hơn.

Với mọi hàm **affine** f(x)=mx+c, quy tắc hình thang cho kết quả **chính xác trong số học lý tưởng** ở bất kỳ khoảng nào, vì chính đồ thị là một đoạn thẳng. Đây là đặc tính nên kiểm tra khi viết mã.

## 4. Quy tắc hình thang ghép (composite trapezoid)

Tổng các hình thang trên n khoảng con [x_i,x_{i+1}]:

~~~text
T_n = (h/2) * [
    f(x_0) + 2*f(x_1) + 2*f(x_2) + ...
           + 2*f(x_(n-1)) + f(x_n)
].

Tương đương:

T_n = h * [(f(a)+f(b))/2
           + sum_(i=1)^(n-1) f(x_i)].
~~~

**Trọng số:** hai đầu mút có hệ số 1 trong công thức h/2, còn các nút trong có hệ số 2. Nguyên nhân là mỗi nút trong là đầu mút chung của **hai hình thang kề nhau**.

Chi phí tính nếu đánh giá hàm là O(1) gồm **n+1 lần đánh giá f**, n khoảng con, tổng O(n) thời gian và O(1) bộ nhớ phụ khi cộng trực tiếp. Nếu f rất đắt, chính số lần gọi hàm có thể là chi phí chủ đạo.

Không yêu cầu n chẵn: **bất kỳ số nguyên n≥1** đều hợp lệ với công thức hình thang ghép.

## 5. Công thức Simpson 1/3 trên hai khoảng con

Lấy ba nút cách đều:

~~~text
x_0=u, x_1=u+h, x_2=u+2h=v.
~~~

Nội suy f bằng một parabol qua ba nút này và tích phân đa thức nội suy. Kết quả:

~~~text
S(u,v) = (h/3) * [f(x_0)+4*f(x_1)+f(x_2)].

Vì v-u=2h, cũng có:
S(u,v) = (v-u)/6 *
         [f(u)+4*f((u+v)/2)+f(v)].
~~~

Hệ số **1–4–1** khác hình thang 1–1. Nút giữa đóng góp nhiều hơn để mô phỏng độ cong của đồ thị.

Simpson 1/3 dùng **hai khoảng con bằng nhau** mỗi lần. Vì vậy khi ghép nhiều đoạn với cùng bước h, số khoảng chia **n phải là số chẵn và ít nhất bằng 2**. Nếu n lẻ, không thể chỉ áp công thức Simpson 1/3 ghép như thường lệ mà không thay đổi phương pháp ở một đoạn cuối.

## 6. Vì sao Simpson chính xác đến đa thức bậc ba?

Simpson được suy ra từ nội suy bậc hai nên hiển nhiên tích phân **đúng với đa thức bậc 0,1,2** trong số học chính xác. Một tính chất mạnh hơn: do các điểm đối xứng quanh trung điểm, sai số của thành phần **bậc ba lẻ quanh trung điểm** cũng triệt tiêu.

Do đó Simpson 1/3 **chính xác cho mọi đa thức có bậc không quá ba**:

~~~text
f(x)=c0+c1*x+c2*x²+c3*x³.
~~~

Tính chính xác ở đây có nghĩa là công thức tích phân của đa thức bằng đúng nguyên hàm trong **số học thực chính xác**. Trên máy dùng double, vẫn có một sai lệch làm tròn rất nhỏ, vì vậy kiểm thử sử dụng **dung sai**, không kiểm tra bằng == tuyệt đối.

Đa thức bậc bốn **không còn được bảo đảm chính xác**: sai số có dấu và độ lớn dự đoán được từ đạo hàm bậc bốn. Ví dụ cụ thể xuất hiện ở phần sau.

## 7. Quy tắc Simpson ghép: điều kiện n chẵn

Với n=2m khoảng con bằng nhau, n chẵn, x_i=a+i h và h=(b−a)/n:

~~~text
S_n = (h/3) * [
    f(x_0)
  + 4*f(x_1) + 2*f(x_2)
  + 4*f(x_3) + 2*f(x_4)
  + ...
  + 4*f(x_(n-1))
  + f(x_n)
].
~~~

Trọng số:

- **i=0 hoặc i=n:** hệ số 1.
- **i lẻ và 0<i<n:** hệ số 4.
- **i chẵn và 0<i<n:** hệ số 2.

Lý do: mỗi cặp hai khoảng dùng ba nút và hệ số 1–4–1; khi hai khối Simpson liền nhau, nút biên chung nhận 1+1=2, còn trung điểm mỗi khối nhận hệ số 4.

Không được nhầm số **n khoảng con** với số **n+1 điểm mẫu**. Một Simpson ghép n=2 lấy mẫu 3 điểm; n=4 lấy mẫu 5 điểm. Mã Java từ chối n=3 thay vì âm thầm tính bằng một công thức trọng số không hoàn chỉnh.

## 8. Ví dụ x² trên [0,1], n=2

Đặt f(x)=x², a=0,b=1, n=2:

~~~text
h = 1/2.
Nút: x0=0, x1=0.5, x2=1.

Giá trị:
f(x0)=0.
f(x1)=0.25.
f(x2)=1.
~~~

Hình thang ghép:

~~~text
T_2=(h/2)[f(x0)+2*f(x1)+f(x2)]
   =(0.5/2)[0+2*0.25+1]
   =0.25*1.5
   =0.375 = 3/8.
~~~

Simpson ghép:

~~~text
S_2=(h/3)[f(x0)+4*f(x1)+f(x2)]
   =(0.5/3)[0+4*0.25+1]
   =1/3.
~~~

Giá trị chính xác:

~~~text
I = integral_0^1 x² dx
  = [x³/3]_0^1
  = 1/3.
~~~

Vì f là đa thức bậc 2, Simpson trúng giá trị đúng (tới sai số double), trong khi hình thang **lớn hơn** tích phân thật một lượng 3/8−1/3=1/24≈0,0416667.

## 9. Ví dụ x⁴: Simpson không phải luôn chính xác

Chọn f(x)=x⁴ trên [0,1]. Nguyên hàm x⁵/5 cho:

~~~text
I = integral_0^1 x⁴ dx = 1/5 = 0.2.
~~~

Với n=2:

~~~text
h=0.5.
f(0)=0.
f(0.5)=0.0625=1/16.
f(1)=1.

S_2=(h/3)[0+4*(1/16)+1]
   =1/6*(1/4+1)
   =5/24
   =0.208333333333...
~~~

Sai số:

~~~text
S_2−I = 5/24−1/5 = 1/120.
~~~

Tăng n lên 4, h=1/4 thì:

~~~text
S_4 = 0.200520833333...
S_4−I = 1/1920.
~~~

Sai số giảm **16 lần** khi h giảm 2 lần, đúng với tốc độ hội tụ bậc bốn cho hàm trơn này. Đối chiếu hình thang với x²: khi tăng n gấp đôi, sai số giảm **4 lần** vì hội tụ bậc hai.

## 10. Sai số hình thang: O(h²)

Giả sử f có đạo hàm cấp hai liên tục trên [a,b], a<b, và n≥1, h=(b−a)/n. Công thức sai số toàn cục của hình thang ghép có dạng:

~~~text
I−T_n = −(b−a)*h²/12 * f''(ξ)
với một ξ trong (a,b).
~~~

Do đó nếu |f''(x)|≤M2 trên [a,b], có cận:

~~~text
|I−T_n| <= (b−a)*h²*M2/12.
~~~

Khi n tăng gấp đôi, h giảm nửa, thành phần sai số xấp xỉ giảm **4 lần** nếu thành phần bậc hai chi phối và chưa bị sai số floating-point lấn át.

Dấu cũng có ý nghĩa: với f''>0 (hàm lồi, như x²), hình thang nằm **phía trên** đồ thị nên T_n>I; công thức I−T_n âm. Với f''<0 (hàm lõm, như sin x trên [0,π]), hình thang thường **đánh giá thấp** tích phân.

Nếu f không có f'' bị chặn (như sqrt(x) tại 0), không được áp dụng cận trên một cách máy móc.

## 11. Sai số Simpson: O(h⁴)

Với f đủ trơn, cụ thể có đạo hàm cấp bốn liên tục trên [a,b], n là số chẵn và h=(b−a)/n, sai số Simpson ghép:

~~~text
I−S_n = −(b−a)*h⁴/180 * f''''(ξ)
với một ξ trong (a,b).
~~~

Nếu |f''''(x)|≤M4:

~~~text
|I−S_n| <= (b−a)*h⁴*M4/180.
~~~

Đây là cận sai số bậc bốn, **không** có nghĩa Simpson chính xác bốn chữ số thập phân. Bậc hội tụ 4 nói về tốc độ sai số giảm khi h→0 **dưới các giả thiết trơn**.

Với f(x)=x⁴, f''''(x)=24 và [a,b]=[0,1]. Thay h=1/2 vào cận (thực tế ở đây là đúng bằng) nhận:

~~~text
I−S_2 = −(1)*(1/2)^4*24/180
      = −1/120.
~~~

Đúng với ví dụ. Khi h=1/4, sai số I−S_4=−1/1920.

## 12. So sánh tốc độ hội tụ khi chia nhỏ bước

Khi tăng n thành 2n:

~~~text
h_new = h_old/2.

Nếu sai số trội C*h²:
    |error_new| ≈ |error_old|/4.

Nếu sai số trội D*h⁴:
    |error_new| ≈ |error_old|/16.
~~~

Ví dụ kiểm thử:

| Hàm và thuật toán | Bước | Kết quả kỳ vọng về sai số |
| --- | --- | --- |
| x², hình thang ghép | n=16→32 | Sai số giảm xấp xỉ 4 lần |
| x⁴, Simpson ghép | n=8→16 | Sai số giảm xấp xỉ 16 lần |
| Đa thức bậc ≤1, hình thang | Mọi n hợp lệ | Chính xác đến làm tròn |
| Đa thức bậc ≤3, Simpson | Mọi n chẵn hợp lệ | Chính xác đến làm tròn |

Để đo tốc độ bằng số, tính **tỉ lệ sai số** |E_n/E_2n| với E_n=I−approximation_n khi biết I chính xác. Nếu sai số đã quá nhỏ (gần độ chính xác máy), tỉ lệ có thể nhiễu hoặc chia gần 0; tránh kết luận bậc hội tụ từ những giá trị đó.

Với hàm có góc nhọn, gián đoạn hoặc dao động nhanh bị lấy mẫu thưa, tỉ lệ 4/16 không còn được bảo đảm.

## 13. Chọn số khoảng n từ cận đạo hàm

Giả sử cần sai số tuyệt đối không vượt ε và biết cận M2 của |f''|. Từ:

~~~text
|I−T_n| <= (b−a)*h²*M2/12,
h=(b−a)/n.
~~~

Suy ra điều kiện đủ:

~~~text
n >= sqrt(((b−a)^3*M2)/(12*ε)).
~~~

Với Simpson, nếu biết cận M4 của |f''''|:

~~~text
|I−S_n| <= (b−a)*h⁴*M4/180.
~~~

Điều kiện đủ là:

~~~text
n >= (((b−a)^5*M4)/(180*ε))^(1/4).
~~~

**Nhớ làm tròn n lên và với Simpson phải làm n chẵn**, đồng thời n≥2. Những cận này là bảo đảm toán học khi giả thiết trơn/cận đạo hàm đúng, **không** trực tiếp bao trùm sai số làm tròn trên máy.

Nếu M2 hoặc M4 không biết, việc chọn n có thể dựa trên thực nghiệm tinh chỉnh và **ước lượng sai số a posteriori** (so kết quả ở hai mức lưới), nhưng đó là dự đoán có điều kiện, không phải chứng nhận tuyệt đối.

## 14. Simpson thích nghi (adaptive Simpson) dùng để làm gì?

Khi f thay đổi mạnh tại một vùng hẹp và tương đối phẳng ở những vùng khác, chia đều toàn bộ [a,b] có thể lãng phí phép đánh giá hàm. **Adaptive Simpson** tự chia nhỏ hơn ở nơi hai mức xấp xỉ chưa khớp, giữ lưới thưa ở nơi đủ ổn.

Ở một đoạn [l,r], gọi:

~~~text
S  = Simpson(l,r) bằng ba điểm l,mid,r.

L = Simpson(l,mid) bằng l, (l+mid)/2, mid.
R = Simpson(mid,r) bằng mid, (mid+r)/2, r.

S2 = L+R.
delta = S2−S.
~~~

Ta dùng sự khác biệt giữa hai mức để ước lượng sai số. Nếu chưa đạt mức chấp nhận thì đệ quy trên hai nửa, mỗi nửa được chia một phần **ngân sách dung sai**.

Lưu ý phương pháp này cần **gọi f ở các trung điểm mới**. Với dữ liệu thực nghiệm chỉ có các mẫu cố định, không thể áp dụng đúng nguyên bản nếu không đo thêm.

## 15. Vì sao dùng delta/15 trong adaptive Simpson?

Giả sử hàm đủ trơn và phần sai số chính của Simpson tỷ lệ với **h⁴** khi chia đôi bước. Gọi I là tích phân thật:

~~~text
S  ≈ I + C*h⁴.
S2 ≈ I + C*(h/2)^4
   = I + C*h⁴/16.
~~~

Suy ra:

~~~text
S2−S ≈ −15*C*h⁴/16.

I−S2 ≈ (S2−S)/15
      = delta/15.
~~~

Do đó hai công thức phổ biến:

~~~text
Ước lượng sai số |I−S2| ≈ |delta|/15.

Giá trị hiệu chỉnh:
S_corrected = S2 + delta/15.
~~~

Adaptive Simpson thường **chấp nhận** đoạn nếu |delta|≤15·tol_local, sau đó trả S_corrected. Nếu không, chia đôi và tiếp tục.

**Đây là ước lượng dựa trên mô hình sai số**, không phải chứng minh độc lập cho mọi hàm. Một hàm gián đoạn, nhiễu, dao động dưới độ phân giải lưới hoặc có tính kỳ dị có thể đánh lừa ước lượng. Không mô tả tol_local như bảo đảm sai số tuyệt đối nghiêm ngặt trong mọi điều kiện.

## 16. Ngân sách dung sai và giới hạn đệ quy

Nếu đoạn hiện tại có ngân sách tol_local, sau khi chia đôi ta thường cấp:

~~~text
tol_left = tol_local/2.
tol_right = tol_local/2.
~~~

Trong mô hình sai số phù hợp, tổng ngân sách của hai nhánh bằng ngân sách ban đầu. Mã chỉ dừng một nhánh khi:

~~~text
abs(S2−S) <= 15*tol_local.
~~~

và trả giá trị đã hiệu chỉnh S2+(S2−S)/15.

Nhưng không thể đệ quy vô hạn: do giới hạn biểu diễn double, có lúc trung điểm **trùng với một đầu mút** và đoạn không thể chia tiếp. Mã Java:

- Yêu cầu tolerance **hữu hạn và >0**.
- Yêu cầu maxDepth trong **[0,30]**.
- Kiểm tra các trung điểm mới nằm **nghiêm ngặt giữa** hai đầu mút.
- Nếu chưa đạt điều kiện và hết độ sâu, ném **IllegalStateException** thay vì âm thầm trả một kết quả chưa đạt ước lượng.
- Nếu hàm trả NaN/Infinity, ném **ArithmeticException**.

Giới hạn 30 không phải công thức toán học; đó là lựa chọn **bảo vệ chương trình** khỏi đệ quy quá mức. Khi đổi giới hạn cần đánh giá chi phí, độ chính xác số thực và bài toán thực tế.

## 17. Hai chiều tích phân và khoảng độ dài bằng 0

Công thức chia lưới thuận thường viết cho a<b. Tuy nhiên tích phân xác định có quy tắc đổi hướng:

~~~text
integral_b^a f(x) dx
    = −integral_a^b f(x) dx.
~~~

Code xử lý nếu a>b bằng cách đổi chỗ hai cận và lưu sign=−1; cuối cùng nhân sign vào kết quả. Đối với sin(x):

~~~text
integral_0^pi sin(x) dx = 2.
integral_pi^0 sin(x) dx = −2.
~~~

Hai dòng này được in trong stdout kiểm thử adaptive Simpson.

Với a=b, tích phân bằng 0, không nên tạo h=0 rồi cố so sánh n nút trùng nhau. Chương trình trả 0 sau khi kiểm tra các tham số của lời gọi là hợp lệ.

Nếu a hoặc b là NaN, Infinity, hoặc hiệu b−a tràn Infinity, đoạn không được xem là hữu hạn hợp lệ; code từ chối với IllegalArgumentException.

## 18. Số thực double, cộng Kahan và các nút trùng

Ngay cả khi công thức toán học đúng, tính số có hạn chế:

- **Làm tròn:** mỗi f(x), phép nhân trọng số và tổng được biểu diễn bằng double.
- **Mất chữ số vì cộng dồn:** khi cộng nhiều số có độ lớn khác nhau, các số nhỏ có thể mất trong tổng.
- **Hủy số (cancellation):** nếu tích phân thật gần 0 nhưng các vùng dương/âm lớn triệt tiêu, sai số tương đối có thể lớn.
- **Phân giải nút:** với a rất lớn và h quá nhỏ, a+i·h có thể trùng a+(i−1)·h sau làm tròn; lấy mẫu nhiều lần tại cùng một x không cải thiện xấp xỉ như mong đợi.
- **Lấy mẫu bỏ sót cấu trúc:** hàm dao động nhanh có thể bằng 0 tại tất cả nút dù tích phân thật không bằng 0.

Trong mã composite, ta dùng một **KahanSum** để giảm lỗi tích lũy khi cộng trọng số. Đây là một cải thiện về độ ổn định, **không** bảo đảm không có sai số floating-point.

Mã còn kiểm tra **nút sau phải lớn hơn nút trước**. Khi hai nút trùng do giới hạn độ chính xác double, ném IllegalArgumentException thay vì tiếp tục báo con số có vẻ chính xác. Tổng và giá trị f(x) phải hữu hạn; nếu phép nhân trọng số hay phép cộng tạo NaN/Infinity, báo ArithmeticException.

## 19. Hàm gián đoạn và singularity: không hứa hẹn O(h⁴)

Các công thức sai số ở trên giả định đạo hàm bậc hai/bốn đủ trơn và bị chặn. Những ví dụ cần chú ý:

1. **f(x)=sqrt(x) trên [0,1]:** f liên tục nhưng các đạo hàm cao gần 0 không bị chặn. Không được dùng công thức M4 hữu hạn trên toàn đoạn để suy diễn bậc hội tụ Simpson.
2. **f(x)=|x|:** có góc gấp tại 0, không khả vi tại đó. Nếu chia tại 0 và áp dụng từng nửa, mỗi nửa là tuyến tính, có thể tính chính xác.
3. **Hàm bậc thang:** có điểm nhảy. Một lưới chia đều hoặc adaptive Simpson có thể lấy mẫu bỏ qua điểm nhảy; khi biết vị trí gián đoạn, nên **chia tích phân tại đó**.
4. **f(x)=1/sqrt(x) gần x=0:** tích phân có thể hội tụ theo nghĩa tích phân suy rộng nhưng f(0)=Infinity, không thể dùng Newton–Cotes đóng trực tiếp tại cận. Cần đổi biến, trừ singularity hoặc dùng thuật toán tích phân suy rộng.
5. **Hàm có cực trong đoạn:** có thể tích phân không tồn tại hoặc phải hiểu theo principal value; không được để thuật toán trả một con số rồi mặc định đó là giá trị thông thường.

Học cách nhận diện **đặc tính của hàm** quan trọng hơn tăng n một cách mù quáng.

## 20. Hàm dao động nhanh và vấn đề aliasing

Xét f(x)=sin(ωx) với tần số ω cao. Nếu mỗi bước h quá lớn, các nút có thể rơi vào những pha giống nhau và không phát hiện đủ các dao động.

Ví dụ chọn khoảng [0,2π] và f(x)=cos(8x). Nếu dùng n=8 và x_i=i·2π/8, thì:

~~~text
f(x_i)=cos(8*i*2π/8)
      =cos(2πi)
      =1 ở mọi nút.
~~~

Cả hình thang lẫn Simpson trên đúng các nút này có thể trả xấp xỉ **2π**, trong khi:

~~~text
integral_0^(2π) cos(8x) dx = 0.
~~~

Đây là một phản ví dụ về **lấy mẫu bỏ sót dao động**, không phải lỗi triển khai trọng số. Simpson với n=8 vẫn thỏa yêu cầu số đoạn chẵn, nhưng kết quả có thể sai lớn.

Adaptive Simpson cũng có thể bị lừa nếu các điểm đánh giá của nó tình cờ đều tương đương theo pha; chênh lệch S2−S nhỏ không chứng minh được kết quả đúng. Khi biết tần số hoặc có cấu trúc dao động, chọn độ phân giải phù hợp, chia các chu kỳ, hoặc dùng **quadrature chuyên cho hàm dao động**.

## 21. Số lần gọi f và chi phí tính toán

Trapezoid ghép và Simpson ghép với n khoảng con dùng **n+1 nút**, vì chương trình đánh giá mỗi nút x_i đúng một lần trong vòng lặp.

~~~text
T_trapezoid = O(n*C_f), nếu C_f là chi phí gọi f.
T_Simpson   = O(n*C_f), n chẵn.
Bộ nhớ phụ: O(1) cho phép cộng luồng.
~~~

Adaptive Simpson tái sử dụng giá trị f ở các đầu/cuối/trung điểm đã tính khi chia nhánh. Mỗi lần chia một đoạn đã có ba giá trị, nó cần đánh giá **hai trung điểm quý (quarter points) mới**, chứ không đánh giá lại toàn bộ các nút. Do đó chi phí xấp xỉ tỷ lệ với **số đoạn đã chia và số lần đánh giá f**, trong khi stack đệ quy sâu tối đa maxDepth.

Không có cận O(log(1/tol)) đơn giản cho mọi f: nếu f rất khó, thuật toán có thể tạo nhiều đoạn hoặc bị chặn bởi depth/budget. Việc giảm tolerance quá thấp có thể tăng chi phí rất mạnh mà không đạt độ chính xác tương ứng do làm tròn.

Nếu chỉ cần xấp xỉ nhanh với f trơn, Simpson ghép thường hiệu quả. Nếu độ cong không đồng đều, adaptive Simpson đáng cân nhắc.

## 22. Java 17+: ba hàm tích phân và kiểm thử độc lập

Lưu mã dưới đây thành tệp **NumericalQuadratureLesson.java**. Các API:

- **trapezoid(f,a,b,panels):** hình thang ghép; panels≥1.
- **simpson(f,a,b,panels):** Simpson 1/3 ghép; panels≥2 và **phải chẵn**.
- **adaptiveSimpson(f,a,b,tolerance,maxDepth):** chia thích nghi, dùng sai khác S2−S, Richardson /15, tol chia đôi, giới hạn depth và nút lấy mẫu.
- **validateCommon:** kiểm tra hàm không null, cận hữu hạn, hiệu cận không overflow.
- **sample/finite:** từ chối kết quả NaN và Infinity.
- **KahanSum:** giảm sai số cộng nhiều trọng số trong hai công thức ghép.
- **verify:** đối chiếu đa thức có nguyên hàm chính xác, sin có nguyên hàm −cos/ω, exp có nguyên hàm exp, tốc độ hội tụ 4/16, và các input/độ sâu không hợp lệ.

**Quy ước:** khi cận a>b, đổi cận và đổi dấu. Khi a=b, trả 0 nếu tham số đúng. Độ dài khoảng được yêu cầu biểu diễn hữu hạn. `MAX_PANELS=2_000_000` là giới hạn bảo vệ tài nguyên của demo, không phải ràng buộc toán học của các quy tắc.

Mã cho phép callback f bằng lambda Java hoặc method reference như Math::sin; riêng callback phải xác định trên các nút mà thuật toán cần đánh giá.

~~~java
import java.util.*;
import java.util.function.DoubleUnaryOperator;

public final class NumericalQuadratureLesson {
    private static final int MAX_PANELS = 2_000_000;

    private NumericalQuadratureLesson() {}

    private static void validateCommon(DoubleUnaryOperator f,
                                       double a, double b) {
        if (f == null || !Double.isFinite(a) || !Double.isFinite(b)) {
            throw new IllegalArgumentException(
                    "function and endpoints must be valid");
        }
        if (!Double.isFinite(b - a)) {
            throw new IllegalArgumentException("interval width overflow");
        }
    }

    private static double sample(DoubleUnaryOperator f, double x) {
        double value = f.applyAsDouble(x);
        if (!Double.isFinite(value)) {
            throw new ArithmeticException(
                    "integrand is nonfinite at x=" + x);
        }
        return value;
    }

    private static double finite(double result) {
        if (!Double.isFinite(result)) {
            throw new ArithmeticException("nonfinite quadrature result");
        }
        return result;
    }

    private static final class KahanSum {
        private double sum;
        private double correction;
        void add(double value) {
            double y = value - correction;
            double next = sum + y;
            correction = (next - sum) - y;
            sum = next;
        }
        double value() { return sum; }
    }

    private static double composite(DoubleUnaryOperator f,
                                    double a, double b,
                                    int panels, boolean useSimpson) {
        validateCommon(f, a, b);
        if (panels < 1 || panels > MAX_PANELS
                || (useSimpson && (panels & 1) != 0)) {
            throw new IllegalArgumentException("invalid panel count");
        }
        if (a == b) return 0.0;
        double sign = 1.0;
        if (b < a) {
            double temp = a;
            a = b;
            b = temp;
            sign = -1.0;
        }
        double h = (b - a) / panels;
        if (!(h > 0.0) || !Double.isFinite(h)) {
            throw new IllegalArgumentException(
                    "panel width cannot be represented");
        }

        KahanSum accumulator = new KahanSum();
        double lastX = Double.NEGATIVE_INFINITY;
        for (int i = 0; i <= panels; i++) {
            double x = (i == 0) ? a : (i == panels ? b : a + i * h);
            if (i > 0 && !(x > lastX)) {
                throw new IllegalArgumentException(
                        "adjacent sample nodes collapse");
            }
            lastX = x;
            double weight = (i == 0 || i == panels)
                    ? 1.0
                    : (useSimpson ? ((i & 1) == 1 ? 4.0 : 2.0) : 2.0);
            accumulator.add(finite(weight * sample(f, x)));
        }
        double scale = useSimpson ? h / 3.0 : h / 2.0;
        return finite(sign * scale * finite(accumulator.value()));
    }

    public static double trapezoid(DoubleUnaryOperator f, double a,
                                   double b, int panels) {
        return composite(f, a, b, panels, false);
    }

    public static double simpson(DoubleUnaryOperator f, double a,
                                 double b, int panels) {
        return composite(f, a, b, panels, true);
    }

    private static double simpsonSegment(double a, double b,
                                         double fa, double fm, double fb) {
        return finite((b - a) / 6.0 * finite(fa + 4.0 * fm + fb));
    }

    private static double adapt(DoubleUnaryOperator f,
                                double a, double b,
                                double fa, double fm, double fb,
                                double whole, double tolerance,
                                int depthLeft) {
        double middle = a + (b - a) / 2.0;
        double lm = a + (middle - a) / 2.0;
        double rm = middle + (b - middle) / 2.0;
        if (!(a < lm && lm < middle && middle < rm && rm < b)) {
            throw new IllegalStateException(
                    "floating-point interval cannot be subdivided");
        }

        double flm = sample(f, lm);
        double frm = sample(f, rm);
        double left = simpsonSegment(a, middle, fa, flm, fm);
        double right = simpsonSegment(middle, b, fm, frm, fb);
        double combined = finite(left + right);
        double delta = finite(combined - whole);

        if (Math.abs(delta) <= 15.0 * tolerance) {
            return finite(combined + delta / 15.0);
        }
        if (depthLeft == 0) {
            throw new IllegalStateException(
                    "tolerance not met within depth limit");
        }
        return finite(adapt(f, a, middle, fa, flm, fm, left,
                            tolerance / 2.0, depthLeft - 1)
                    + adapt(f, middle, b, fm, frm, fb, right,
                            tolerance / 2.0, depthLeft - 1));
    }

    public static double adaptiveSimpson(DoubleUnaryOperator f,
                                         double a, double b,
                                         double tolerance, int maxDepth) {
        validateCommon(f, a, b);
        if (!(tolerance > 0.0) || !Double.isFinite(tolerance)
                || maxDepth < 0 || maxDepth > 30) {
            throw new IllegalArgumentException(
                    "tolerance must be positive and depth in [0,30]");
        }
        if (a == b) return 0.0;
        double sign = 1.0;
        if (b < a) {
            double temp = a;
            a = b;
            b = temp;
            sign = -1.0;
        }
        double mid = a + (b - a) / 2.0;
        if (!(a < mid && mid < b)) {
            throw new IllegalArgumentException(
                    "interval cannot be bisected");
        }
        double fa = sample(f, a);
        double fm = sample(f, mid);
        double fb = sample(f, b);
        double whole = simpsonSegment(a, b, fa, fm, fb);
        return finite(sign * adapt(f, a, b, fa, fm, fb,
                                   whole, tolerance, maxDepth));
    }

    private static void close(String label, double actual,
                              double expected, double tolerance) {
        if (!Double.isFinite(actual) ||
                Math.abs(actual - expected) > tolerance) {
            throw new AssertionError(label
                    + ": actual=" + actual + " expected=" + expected);
        }
    }

    private static void invalid(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("invalid input unexpectedly accepted");
    }

    private static void arithmeticError(Runnable operation) {
        try {
            operation.run();
        } catch (ArithmeticException expected) {
            return;
        }
        throw new AssertionError("nonfinite input not rejected");
    }

    private static void depthError(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalStateException expected) {
            return;
        }
        throw new AssertionError("unmet tolerance was silently accepted");
    }

    public static void verify() {
        int cubicCases = 0, affineCases = 0;
        double[][] intervals = {{-2, -1}, {-1, 1}, {0, 1},
                                {0, 2}, {-2, 2}};
        int[] panelCounts = {2, 4, 8, 16};
        for (int c0 = -2; c0 <= 2; c0++)
        for (int c1 = -2; c1 <= 2; c1++)
        for (int c2 = -2; c2 <= 2; c2++)
        for (int c3 = -2; c3 <= 2; c3++) {
            final double[] c = {c0, c1, c2, c3};
            DoubleUnaryOperator polynomial = x ->
                    ((c[3] * x + c[2]) * x + c[1]) * x + c[0];
            for (double[] interval : intervals) {
                double a = interval[0], b = interval[1];
                double exact = 0.0;
                for (int degree = 0; degree <= 3; degree++) {
                    exact += c[degree] *
                            (Math.pow(b, degree + 1)
                             - Math.pow(a, degree + 1)) / (degree + 1);
                }
                for (int panels : panelCounts) {
                    close("cubic Simpson", simpson(polynomial, a, b, panels),
                          exact, 1e-10);
                    cubicCases++;
                    if (c2 == 0 && c3 == 0) {
                        close("affine trapezoid",
                              trapezoid(polynomial, a, b, panels),
                              exact, 1e-10);
                        affineCases++;
                    }
                }
            }
        }

        Random random = new Random(4402026L);
        int analyticCases = 0;
        for (int trial = 0; trial < 1200; trial++) {
            double a = -1.0 + 2.0 * random.nextDouble();
            double b = a + 0.25 + 1.75 * random.nextDouble();
            final int frequency = 1 + random.nextInt(5);
            DoubleUnaryOperator f = x -> Math.sin(frequency * x);
            double exact = (Math.cos(frequency * a)
                           - Math.cos(frequency * b)) / frequency;
            int panels = 64 + 2 * random.nextInt(50);
            close("sine trapezoid", trapezoid(f, a, b, panels),
                  exact, 0.01);
            close("sine Simpson", simpson(f, a, b, panels),
                  exact, 2e-5);
            close("sine adaptive",
                  adaptiveSimpson(f, a, b, 1e-10, 25),
                  exact, 1e-8);
            analyticCases++;
        }

        DoubleUnaryOperator square = x -> x * x;
        DoubleUnaryOperator quartic = x -> x * x * x * x;
        double exactSquare = 1.0 / 3.0;
        double exactQuartic = 1.0 / 5.0;
        double trapRatio = (trapezoid(square, 0, 1, 16) - exactSquare)
                / (trapezoid(square, 0, 1, 32) - exactSquare);
        double simpsonRatio = (simpson(quartic, 0, 1, 8) - exactQuartic)
                / (simpson(quartic, 0, 1, 16) - exactQuartic);
        close("trapezoid refinement rate", trapRatio, 4.0, 1e-8);
        close("Simpson refinement rate", simpsonRatio, 16.0, 1e-6);

        close("adaptive exp",
              adaptiveSimpson(Math::exp, 0, 1, 1e-12, 30),
              Math.E - 1, 1e-11);
        close("adaptive sine", adaptiveSimpson(Math::sin, 0, Math.PI,
                                               1e-12, 30), 2.0, 1e-11);
        close("reversed integral",
              adaptiveSimpson(Math::sin, Math.PI, 0,
                              1e-12, 30), -2.0, 1e-11);
        close("zero width", simpson(Math::sin, 1, 1, 2), 0.0, 0.0);

        invalid(() -> trapezoid(null, 0, 1, 2));
        invalid(() -> simpson(x -> x, 0, 1, 3));
        invalid(() -> simpson(x -> x, 0, 1, 0));
        invalid(() -> trapezoid(x -> x, Double.NaN, 1, 2));
        invalid(() -> simpson(x -> x, 0, Double.POSITIVE_INFINITY, 2));
        invalid(() -> trapezoid(x -> x, 0, 1, MAX_PANELS + 1));
        invalid(() -> adaptiveSimpson(x -> x, 0, 1, 0, 20));
        invalid(() -> adaptiveSimpson(x -> x, 0, 1, 1e-6, 31));
        arithmeticError(() -> simpson(x -> Double.NaN, 0, 1, 2));
        arithmeticError(() -> adaptiveSimpson(
                x -> Double.POSITIVE_INFINITY, 0, 1, 1e-6, 20));
        depthError(() -> adaptiveSimpson(Math::exp, 0, 1, 1e-25, 0));

        System.out.println("Cubic Simpson exactness cases: "
                           + cubicCases + " PASS");
        System.out.println("Affine trapezoid exactness cases: "
                           + affineCases + " PASS");
        System.out.println("Seeded analytic sine cases: "
                           + analyticCases + " PASS");
        System.out.println("Refinement rates and adaptive smooth cases: PASS");
        System.out.println("Invalid, nonfinite and depth-limit cases: PASS");
    }

    public static void main(String[] args) {
        DoubleUnaryOperator square = x -> x * x;
        DoubleUnaryOperator quartic = x -> x * x * x * x;
        System.out.printf(Locale.ROOT,
                "Trapezoid x^2 [0,1], n=2: %.12f%n",
                trapezoid(square, 0, 1, 2));
        System.out.printf(Locale.ROOT,
                "Simpson x^2 [0,1], n=2: %.12f%n",
                simpson(square, 0, 1, 2));
        System.out.printf(Locale.ROOT,
                "Simpson x^4 [0,1], n=2: %.12f%n",
                simpson(quartic, 0, 1, 2));
        System.out.printf(Locale.ROOT,
                "Adaptive sin [0,pi]: %.12f%n",
                adaptiveSimpson(Math::sin, 0, Math.PI, 1e-12, 30));
        System.out.printf(Locale.ROOT,
                "Reversed adaptive sin [pi,0]: %.12f%n",
                adaptiveSimpson(Math::sin, Math.PI, 0, 1e-12, 30));
        verify();
    }
~~~

Biên dịch/chạy với JDK 17 hoặc mới hơn:

~~~bash
javac NumericalQuadratureLesson.java
java NumericalQuadratureLesson
~~~

**Stdout chính xác đã được quan sát trong lần kiểm thử Java:**

~~~text
Trapezoid x^2 [0,1], n=2: 0.375000000000
Simpson x^2 [0,1], n=2: 0.333333333333
Simpson x^4 [0,1], n=2: 0.208333333333
Adaptive sin [0,pi]: 2.000000000000
Reversed adaptive sin [pi,0]: -2.000000000000
Cubic Simpson exactness cases: 12500 PASS
Affine trapezoid exactness cases: 500 PASS
Seeded analytic sine cases: 1200 PASS
Refinement rates and adaptive smooth cases: PASS
Invalid, nonfinite and depth-limit cases: PASS
~~~

Các giá trị được in bằng **Locale.ROOT** và 12 chữ số sau dấu thập phân để kết quả không phụ thuộc locale của máy. Dòng PASS chỉ được in sau khi những kiểm tra tương ứng đã hoàn tất; nếu phát hiện sai lệch, chương trình ném AssertionError.

## 23. Kiểm thử 12.500 trường hợp Simpson đa thức bậc ≤3

Mã xét mọi đa thức bậc không quá ba có hệ số nguyên:

~~~text
f(x)=c0+c1*x+c2*x²+c3*x³.

Mỗi ck thuộc {-2,-1,0,1,2}.
Số bộ hệ số = 5^4 = 625.
~~~

Với mỗi đa thức, thử **5 đoạn**:

~~~text
[-2,-1], [-1,1], [0,1], [0,2], [-2,2].
~~~

Và **4 cách chia chẵn**:

~~~text
n in {2,4,8,16}.
~~~

Tổng:

~~~text
625 * 5 * 4 = 12500 lần kiểm tra Simpson.
~~~

Oracle không dùng Simpson: tính nguyên hàm đa thức

~~~text
F(x)=c0*x+(c1/2)*x²+(c2/3)*x³+(c3/4)*x⁴,
I=F(b)-F(a).
~~~

Mã so kết quả Simpson với I trong dung sai **1e−10** để cho phép sai số làm tròn double. Đây là bộ kiểm thử mạnh vì Simpson phải đúng cho mọi đa thức bậc ≤3, không chỉ vài hàm mẫu riêng lẻ.

## 24. Kiểm thử 500 trường hợp hình thang với hàm affine

Trong cùng bộ đa thức, nếu c2=c3=0, ta có f(x)=c0+c1x, một hàm affine. Hình thang phải tích phân chính xác tới sai số làm tròn.

Với c0,c1 mỗi hệ số có 5 lựa chọn, có 25 hàm affine. Kết hợp 5 khoảng và 4 số khoảng chia:

~~~text
25 * 5 * 4 = 500 lần kiểm tra hình thang.
~~~

Oracle vẫn là tích phân qua nguyên hàm, không dựa vào kết quả Simpson để tạo kỳ vọng. Nếu công thức hình thang thiếu hệ số 1/2 ở hai đầu mút hoặc đếm trùng nút, kiểm thử này có thể phát hiện.

## 25. Kiểm thử 1.200 khoảng sin và Simpson thích nghi

Đối với f(x)=sin(ωx), nguyên hàm là −cos(ωx)/ω khi ω≠0. Tích phân chính xác:

~~~text
I = [cos(ωa)-cos(ωb)]/ω.
~~~

Mã dùng Random(4402026L) để sinh **1.200** bộ: a và b là số thực có độ dài khoảng dương, ω là số nguyên từ 1 tới 5; n chẵn trong khoảng 64..162 theo bước 2.

Mỗi bộ được so với giá trị giải tích bằng ba phương pháp:

- Hình thang ghép, dung sai tuyệt đối 0,01 cho miền thử đã định.
- Simpson ghép, dung sai tuyệt đối 2e−5.
- Adaptive Simpson với tol 1e−10, đối chiếu giá trị thật trong dung sai 1e−8.

Dung sai ở đây là **ngưỡng kiểm thử cụ thể** cho miền dữ liệu được tạo, không phải bảo đảm tổng quát của mỗi phương pháp với mọi ω hay mọi đoạn.

Ngoài ra có test adaptive sin trên [0,π] và [π,0], tích phân exp trên [0,1] bằng e−1, và các so sánh tỷ lệ hội tụ gần 4 và 16 cho x²/x⁴. Các kết quả đã qua kiểm thử Java.

## 26. Lưu ý về sai số tuyệt đối và tương đối

**Sai số tuyệt đối:**

~~~text
E_abs = |approximation - I|.
~~~

**Sai số tương đối:** thường là |approximation−I|/|I| khi I≠0. Khi I≈0, sai số tương đối trở nên rất lớn hoặc vô nghĩa, kể cả khi sai số tuyệt đối nhỏ.

Trong adaptive Simpson, code nhận một **tolerance tuyệt đối**. Nếu bài toán có tích phân lớn về biên độ, có thể dùng tiêu chí kết hợp absolute + relative, ví dụ:

~~~text
tol_effective = max(absTol, relTol*abs(estimate)).
~~~

Nhưng vì estimate có thể triệt tiêu sai hoặc bị lấy mẫu hụt, đây cũng chỉ là **chiến lược kiểm soát** chứ không thay thế một cận sai số toán học.

Nếu tích phân cần được cộng/trừ để tính xác suất, năng lượng hay tiền tệ, hãy kiểm tra **đơn vị đo và độ lớn đầu vào**. Một sai số tuyệt đối 1e−6 có thể chấp nhận được ở đơn vị mét nhưng không phù hợp ở một bài toán nhạy cảm khác.

## 27. Lỗi lập trình và hiểu sai phương pháp

1. **Dùng n lẻ với Simpson 1/3 ghép** dù công thức yêu cầu n chẵn.
2. **Nhầm n đoạn với n điểm**, dẫn tới thiếu đầu mút b.
3. **Gán trọng số Simpson 1–2–4–2–...** không đúng mẫu 1–4–2–4–...–1.
4. **Quên hệ số h/3** trong Simpson hoặc h/2 trong hình thang dạng trọng số 1–2–...–1.
5. **Nhân h hai lần** khi cộng các khối Simpson đã có hệ số chiều rộng.
6. **Áp công thức xấp xỉ đúng cho f trơn lên hàm gián đoạn**, rồi khẳng định O(h⁴).
7. **Cho rằng Simpson chính xác với mọi đa thức**, dù chỉ chính xác tới bậc ba.
8. **Không xử lý cận đảo**, nên dấu của kết quả sai.
9. **Chia cho b−a khi a=b** rồi gặp 0 hoặc NaN ngoài ý muốn.
10. **Cho hàm trả NaN/Infinity mà vẫn chấp nhận**, làm hỏng tổng.
11. **Tăng n vô hạn khi kết quả không cải thiện**, mất thời gian do lỗi làm tròn.
12. **Không nhận ra các nút trùng nhau** khi h quá nhỏ so với độ lớn a.
13. **So double bằng == để xác nhận tích phân**, bỏ qua sai số tròn hợp lệ.
14. **Nhầm độ chính xác h⁴ với bốn chữ số thập phân**.
15. **Dùng /15 adaptive Simpson như một cận sai số chắc chắn cho mọi hàm**, dù nó là ước lượng.
16. **Không chia tol ở hai nửa**, khiến tổng ngân sách sai số không như dự định.
17. **Trả kết quả khi hết độ sâu dù chưa thỏa tiêu chí**, gây số liệu sai có vẻ đáng tin.
18. **Lấy mẫu bỏ sót đỉnh/dao động**, đặc biệt với hàm tuần hoàn tần số cao.
19. **Sử dụng Simpson closed trên hàm có cực tại đầu mút**, dù f(a)=Infinity.
20. **Không kiểm tra dấu sai số theo độ lồi/lõm**, dễ đảo công thức I−T.
21. **Quên Kahan không chữa được sai mô hình**, chỉ giảm một phần lỗi cộng.
22. **Tin rằng so hai lưới luôn chứng minh đúng**, dù hai lưới có thể cùng aliasing.
23. **Áp n chẵn của Simpson cho hình thang**, hạn chế input không cần thiết.
24. **Không giới hạn chi phí lời gọi f**, đặc biệt khi f rất đắt hoặc có side effect.
25. **Dùng callback thay đổi theo lần gọi**, khiến các ước lượng trên cùng nút không còn nhất quán.
26. **Quên kiểm tra double overflow ở b−a**, dù a và b riêng lẻ đều hữu hạn.
27. **Nhầm Simpson 1/3 với Simpson 3/8:** phương pháp 3/8 dựa trên ba khoảng con, công thức khác và không được cài trong demo này.

## 28. Bài tập thực hành

**Bài 1 — Hình thang:** tính T_2 cho f(x)=x² trên [0,1], so với 1/3 và giải thích sai số 1/24.

**Bài 2 — Simpson:** tính S_2 cho cùng bài, tự giải thích vì sao giá trị bằng 1/3.

**Bài 3 — Bậc bốn:** tính S_2 cho f(x)=x⁴, so với 1/5, xác nhận sai số 1/120; tính S_4 rồi kiểm tra tỷ lệ lỗi 16.

**Bài 4 — Trọng số:** với n=6, viết toàn bộ chuỗi trọng số hình thang và Simpson; giải thích nút nào được đếm hai lần qua các khối ghép.

**Bài 5 — Sai số có dấu:** với f(x)=x² và a<b, dùng f''=2 để giải thích vì sao hình thang đánh giá cao hơn giá trị thật.

**Bài 6 — Chọn n:** cho [a,b]=[0,1], M2=8 và ε=10^−4, tính n tối thiểu đủ cho cận hình thang; làm tương tự với M4=24 và Simpson, nhớ làm tròn n chẵn.

**Bài 7 — Đa thức chính xác:** giải thích vì sao Simpson đúng cho mọi đa thức bậc ba và hình thang đúng cho mọi affine; thử hệ số âm và các đoạn không đối xứng.

**Bài 8 — Adaptive:** viết bảng S, S2, delta, delta/15 trên [0,1] với f(x)=x⁴; nhận xét vì sao hiệu chỉnh Richardson có ích.

**Bài 9 — Hàm có góc nhọn:** với f(x)=|x| trên [−1,1], so kết quả khi chia tích phân tại 0 và khi không chia.

**Bài 10 — Alias sin/cos:** tính giá trị f tại các nút x_i=2πi/8 cho cos(8x); vì sao các nút không phản ánh tích phân thật?

**Bài 11 — Chi phí:** đo số lần đánh giá f của trapezoid, Simpson và adaptive trên các hàm có độ cong thay đổi không đều.

**Bài 12 — Dung sai:** thử tol=1e−4,1e−8,1e−12 cho adaptive Simpson của exp(x) trên [0,1]; so số lần gọi f và sai số thật so với e−1.

**Bài 13 — Phi tuyến khó:** thử sqrt(x) tại 0 và 1/sqrt(x) tại 0; phát hiện vì sao một hàm còn hữu hạn nhưng không có đạo hàm bị chặn, còn hàm kia không thể đánh giá ở cận.

**Bài 14 — Bảo toàn dấu:** kiểm tra tổng hợp với f(x)=x, f(x)=sin x, các cận đổi hướng và cận trùng.

**Bài 15 — Bộ kiểm thử:** tái tạo 12.500 bộ đa thức Simpson và 500 bộ affine hình thang từ các tập hệ số/khoảng/n, dùng nguyên hàm làm oracle.

## 29. Bảng lựa chọn nhanh và kết luận

| Nhu cầu | Quy tắc phù hợp | Lưu ý |
| --- | --- | --- |
| Hàm đơn giản/gần tuyến tính, độ chính xác vừa phải | Hình thang ghép | n≥1, O(n), error thường O(h²) |
| Hàm trơn, muốn chính xác cao với ít mẫu | Simpson 1/3 ghép | n chẵn, error thường O(h⁴) |
| Độ cong tập trung ở một vài vùng | Adaptive Simpson | Ước lượng /15, giới hạn depth, không bảo đảm cho mọi f |
| Hàm gián đoạn có điểm nhảy biết trước | Chia tích phân tại điểm nhảy | Không áp cận đạo hàm trơn xuyên qua điểm nhảy |
| Hàm dao động rất nhanh | Phân tích tần số / quadrature chuyên dụng | Tránh aliasing trên lưới thưa |
| Hàm có singularity tại đầu mút | Đổi biến / tách singularity / quadrature phù hợp | Tránh closed rule đánh giá tại điểm vô hạn |
| Chỉ có các mẫu đo cố định | Hình thang hoặc Simpson nếu lưới phù hợp | Không tự giả định biết hàm ở nút chưa được đo |

**Tư tưởng cốt lõi:** hình thang thay đường cong bằng đoạn thẳng; Simpson thay bằng các cung parabol và cần **số khoảng con chẵn**. Đối với hàm đủ trơn, sai số toàn cục thường giảm theo h² hoặc h⁴. Khi chưa biết độ phân giải cần thiết, adaptive Simpson giúp tinh chỉnh vùng khó bằng phép so hai mức và hiệu chỉnh /15, nhưng vẫn phải kiểm soát giới hạn đệ quy và hiểu các giả thiết của ước lượng. Trong Java, cần thêm kiểm tra đầu vào, giá trị f hữu hạn, các nút double không bị trùng, và bộ kiểm thử so với nguyên hàm độc lập để đưa công thức toán học thành một phép tính số đáng tin.

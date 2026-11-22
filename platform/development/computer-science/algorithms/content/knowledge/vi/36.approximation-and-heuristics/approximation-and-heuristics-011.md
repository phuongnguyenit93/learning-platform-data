# Đối chiếu nghiệm với cận để đánh giá chất lượng

**Chủ đề:** Computer Science Algorithms · Xấp xỉ và kinh nghiệm

## 1. Vấn đề: “nghiệm tốt” có nghĩa là tốt đến đâu?

Với bài toán tối ưu khó, ta thường tìm được một nghiệm khả thi rất nhanh nhờ tham lam, tìm kiếm cục bộ hoặc solver bị giới hạn thời gian. Nhưng nhìn riêng **giá trị của nghiệm** không đủ để kết luận chất lượng:

- Giá trị 100 có thể là tối ưu nếu không có nghiệm nào vượt 100.
- Giá trị 100 có thể rất kém nếu tồn tại nghiệm giá trị 1.000.
- Heuristic tốt nhất trong 1.000 lần chạy chưa chắc gần nghiệm tối ưu.

Để đánh giá có căn cứ, cần đối chiếu **nghiệm khả thi** với một **cận toán học hợp lệ** của nghiệm tối ưu, ký hiệu OPT. Hai hướng tối ưu hóa có **chiều bất đẳng thức ngược nhau**:

- **Tối đa hóa:** nghiệm khả thi cung cấp **cận dưới** L; một nới lỏng hoặc chứng minh độc lập cung cấp **cận trên** U.
- **Tối thiểu hóa:** nghiệm khả thi cung cấp **cận trên** U; một nới lỏng hoặc chứng minh độc lập cung cấp **cận dưới** L.

Cả hai cùng có khuôn:

\[
\boxed{L\le OPT\le U}.
\]

Nhưng **L và U lấy từ đâu** và **giá trị nào là một nghiệm khả thi** tùy thuộc bài tối đa hóa hay tối thiểu hóa.

Bài học này đi từ bản chất cận đến cách xây **chứng nhận chất lượng (quality certificate)**, tính **khoảng tối ưu (optimality gap)**, suy ra **tỷ lệ xấp xỉ được chứng nhận**, xử lý nghiệm nguyên, đánh giá thuật toán anytime và những cạm bẫy khiến một báo cáo chất lượng sai. Hai ví dụ được dùng xuyên suốt:

1. **0/1 Knapsack** — bài **tối đa hóa**, với cận trên từ ba lô phân số.
2. **Minimum Vertex Cover** — bài **tối thiểu hóa**, với cận dưới từ matching.

Có một chương trình **Java 17 hoàn chỉnh** cho cả hai chiều cận và các trường hợp biên.

## 2. Phát biểu toán học trước khi đo chất lượng

Gọi F là tập những phương án **khả thi**, f(x) là hàm mục tiêu và OPT là giá trị tốt nhất có thể.

Nếu tối đa hóa:

\[
OPT=\max_{x\in F}f(x).
\]

Với bất kỳ x khả thi nào:

\[
f(x)\le OPT.
\]

Nếu tối thiểu hóa:

\[
OPT=\min_{x\in F}f(x).
\]

Với bất kỳ x khả thi nào:

\[
OPT\le f(x).
\]

Điều này giải thích vì sao **nghiệm khả thi** và **cận do toán học cung cấp** đóng vai trò khác nhau.

| Bài toán | Từ một nghiệm khả thi x | Cần tìm thêm | Khoảng chứng nhận |
|---|---|---|---|
| **Tối đa hóa** | L=f(x), cận dưới | U≥OPT, cận trên | L≤OPT≤U |
| **Tối thiểu hóa** | U=f(x), cận trên | L≤OPT, cận dưới | L≤OPT≤U |

Khi cận khép kín:

\[
\boxed{L=U\Rightarrow OPT=L=U},
\]

ta có thể **chứng minh tối ưu** mà không nhất thiết duyệt vét cạn mọi phương án.

### 2.1. Tính khả thi là điều kiện bắt buộc

Không thể dùng một phương án vi phạm ràng buộc làm chứng nhận tối ưu. Ví dụ trong ba lô, nếu W=10 mà chọn vật tổng trọng lượng 11 thì dù tổng giá trị cao, đó **không phải cận dưới** của OPT.

Trước khi báo cáo nghiệm nên kiểm:
- Index/định danh thuộc tập đầu vào.
- Không chọn trùng những vật chỉ được chọn một lần.
- Thỏa ngân sách, sức chứa, phân công, khả năng kết nối và ràng buộc cụ thể.
- Giá trị mục tiêu được tính lại từ dữ liệu, không tin một con số tự khai.
- Phiên bản dữ liệu của nghiệm và cận **trùng nhau**.

Chỉ sau đó mới dùng f(x) làm cận theo chiều thích hợp.

### 2.2. Cận hợp lệ không đồng nghĩa cận chặt

Với bài tối đa hóa có L=60, U=1.000, khoảng L≤OPT≤U hoàn toàn có thể đúng nhưng **quá rộng** để nói nghiệm gần tối ưu.

Một cận U tốt nên càng **nhỏ** càng tốt mà vẫn U≥OPT. Một cận L tốt nên càng **lớn** càng tốt mà vẫn L≤OPT. Đối với minimization cũng vậy: muốn **nâng L** và **hạ U**.

Không được đánh đổi độ chặt bằng cách phá tính đúng. Cận trên sai ước lượng U<OPT nguy hiểm hơn cận trên đúng nhưng lỏng: nó có thể cấp một “chứng chỉ tối ưu giả”.

## 3. Absolute gap, relative gap và tỷ lệ chứng nhận

Giả sử biết khoảng **L≤OPT≤U**.

### 3.1. Khoảng cách cộng: absolute certificate gap

\[
\boxed{G_{\rm abs}=U-L\ge0}.
\]

Với tối đa hóa, nếu nghiệm hiện tại có giá trị L thì:

\[
0\le OPT-L\le U-L.
\]

Với tối thiểu hóa, nếu nghiệm hiện tại có giá trị U thì:

\[
0\le U-OPT\le U-L.
\]

Do đó G_abs là **cận trên của sai số cộng**, không phải nhất thiết **sai số thực**.

Nếu một solver trả nghiệm 160 và cận trên 240 cho bài tối đa hóa, ta chỉ kết luận **sai số thực không quá 80**. Có thể OPT=160, 200, 220 hoặc 240, nếu không có thêm chứng cứ.

### 3.2. Bài tối đa hóa: tỷ lệ nghiệm trên cận trên

Với mục tiêu không âm, U>0 và nghiệm giá trị L≥0:

\[
L\le OPT\le U
\Rightarrow
\frac{L}{OPT}\ge\frac{L}{U}.
\]

Vậy **L/U** là một **cận dưới được chứng nhận** của tỷ lệ chất lượng nghiệm hiện tại so với OPT.

Mặt khác:

\[
\frac{OPT-L}{OPT}
=1-\frac{L}{OPT}
\le 1-\frac LU
=\frac{U-L}{U}.
\]

Vì vậy **(U−L)/U** là một cận trên của tỷ lệ mất mát so với tối ưu, nếu OPT>0.

Không nên viết “độ lệch thực là (U−L)/U”: đây là **độ lệch tối đa được chứng nhận**, có thể lớn hơn độ lệch thực nhiều lần.

### 3.3. Bài tối thiểu hóa: tỷ lệ nghiệm trên cận dưới

Với mục tiêu không âm và L>0, nghiệm hiện tại có giá trị U:

\[
L\le OPT\le U
\Rightarrow
\frac{U}{OPT}\le\frac{U}{L}.
\]

Do đó **U/L** là **cận trên của tỷ lệ nghiệm/OPT**.

Và:

\[
\frac{U-OPT}{OPT}
=\frac{U}{OPT}-1
\le\frac{U}{L}-1
=\frac{U-L}{L}.
\]

Đây là **cận trên của phần trăm vượt tối ưu**, nếu OPT>0.

### 3.4. Vì sao không dùng cùng một tỷ lệ cho mọi hướng?

Giả sử hai khoảng đều L=10, U=20:
- Với **maximization**, một nghiệm giá trị 10 có tỷ lệ được chứng nhận **ít nhất 1/2** so với OPT.
- Với **minimization**, một nghiệm giá trị 20 có tỷ lệ được chứng nhận **không quá 2** lần OPT.

Việc đưa L/U vào công thức đánh giá minimization và kết luận “ít nhất 50%” thường không đúng với khái niệm approximation ratio của minimization.

### 3.5. Những trường hợp mục tiêu bằng 0 hoặc âm

Nếu U=0 ở tối đa hóa với mục tiêu không âm thì OPT=0 và nghiệm giá trị 0 là tối ưu, nhưng tỷ lệ **0/0 không định nghĩa**. Không cần tạo tỷ lệ giả 100%.

Nếu L=0 ở tối thiểu hóa và có nghiệm giá trị U>0, tỷ lệ U/L **không xác định**; khi ấy dùng **additive gap** U−L hoặc tìm cận dưới dương mạnh hơn.

Với giá trị mục tiêu **âm** hoặc không có một mốc 0 tự nhiên, tỷ lệ nhân có thể mất ý nghĩa: cộng cùng một hằng số vào toàn bộ giá trị mục tiêu không đổi thứ tự tối ưu nhưng làm thay đổi tỷ lệ. Cần quy ước metric theo bài toán, ưu tiên chứng nhận **sai số cộng**, cận phù hợp hoặc dịch mục tiêu có giải thích.

## 4. Cận tiên nghiệm và cận hậu nghiệm

Hai kiểu chứng nhận thường bị trộn lẫn.

**A priori guarantee (bảo đảm tiên nghiệm):** một định lý của thuật toán áp dụng cho **mọi đầu vào thuộc miền đã nêu**. Ví dụ thuật toán lấy cả hai đầu mút của một maximal matching làm vertex cover cho tỷ lệ không quá 2 lần OPT.

**A posteriori certificate (chứng nhận hậu nghiệm):** dựa trên **nghiệm và cận của instance hiện tại**. Ví dụ một phương án ba lô cụ thể có giá trị 15 trong khi cận trên nguyên chứng minh là 16, vậy tỷ lệ chất lượng ≥15/16, dù thuật toán sinh phương án có thể chỉ là một heuristic.

| Nguồn đảm bảo | Câu hỏi nó trả lời | Giới hạn |
|---|---|---|
| Định lý approximation toàn cục | Thuật toán này kém OPT nhiều nhất bao nhiêu trong mọi instance? | Có thể bi quan với instance cụ thể |
| Cận L/U cho instance | Phương án đang có kém OPT nhiều nhất bao nhiêu ở đầu vào này? | Chỉ mạnh nếu cận U/L đủ chặt |
| Oracle exact nhỏ | Kết quả có thật sự tối ưu trên các ca kiểm thử nhỏ không? | Không chứng minh tất cả input lớn |
| Benchmark thực nghiệm | Trung bình và tail latency/chất lượng ra sao trong phân phối thử? | Không thay thế bảo đảm xấu nhất |
| Solver chứng minh OPTIMAL | Đã đóng toàn bộ khoảng tối ưu chưa? | Tốn tài nguyên và phụ thuộc chứng nhận đúng |

Một heuristic không có định lý xấp xỉ toàn cục **vẫn có thể báo chất lượng đáng tin** trên một instance, nếu đi kèm cận toán học hợp lệ cho instance đó.

## 5. Bài tối đa hóa: 0/1 Knapsack

Có n vật, vật i có:
- Trọng lượng nguyên dương w[i].
- Giá trị nguyên không âm v[i].

Sức chứa nguyên W≥0. Mỗi vật lấy 0 hoặc 1 lần:

\[
\max\sum_i v_i x_i,\quad
\sum_i w_i x_i\le W,\quad
x_i\in\{0,1\}.
\]

Một phương án gồm danh sách index đã chọn. Ta phải tính đúng tổng trọng lượng và giá trị của nó; phương án rỗng luôn hợp lệ với giá trị 0.

### 5.1. Ví dụ cho cận trên phân số không nguyên

Chọn W=10 và ba vật:

| Index | Trọng lượng w | Giá trị v | Mật độ v/w |
|---:|---:|---:|---:|
| 0 | 4 | 7 | 7/4 = 1,75 |
| 1 | 5 | 8 | 8/5 = 1,60 |
| 2 | 6 | 9 | 9/6 = 1,50 |

Một heuristic tham lam theo v/w giảm dần sẽ lấy:
- Vật 0: trọng lượng 4, giá trị 7.
- Vật 1: thêm trọng lượng 5, giá trị 8.
- Tổng trọng lượng 9 và giá trị **15**.
- Vật 2 trọng lượng 6 không vừa sức chứa còn 1.

Vậy phương án **[0,1]** là khả thi, cung cấp:

\[
\boxed{L=15}.
\]

Nhưng chọn vật 0 và 2 có tổng trọng lượng 4+6=10, giá trị 7+9=**16**. Nghiệm [0,2] tốt hơn heuristic.

### 5.2. Cận trên từ bài ba lô phân số

Giảm ràng buộc x_i∈{0,1} thành x_i∈[0,1], tức cho phép lấy **một phần vật**. Không gian nghiệm phân số chứa mọi nghiệm nguyên khả thi, nên:

\[
OPT_{\rm integer}\le OPT_{\rm fractional}.
\]

Với bài fractional knapsack, sắp theo mật độ v/w giảm dần là tối ưu:
- Lấy toàn bộ vật 0 và 1: giá trị 7+8=15, trọng lượng 9.
- Còn 1 đơn vị sức chứa.
- Lấy 1/6 của vật 2: thêm 9×(1/6)=3/2.

Cận trên:

\[
\boxed{U_{\rm fractional}=15+\frac32=\frac{33}{2}=16,5}.
\]

Do đó:

\[
15\le OPT_{\rm integer}\le16,5.
\]

### 5.3. Làm chặt cận khi mục tiêu tối ưu là số nguyên

Vì mọi giá trị vật là nguyên nên tổng giá trị của mọi nghiệm cũng **nguyên**. Nếu OPT≤33/2 thì:

\[
OPT\le\left\lfloor\frac{33}{2}\right\rfloor=16.
\]

Vậy có chứng nhận chặt hơn:

\[
\boxed{15\le OPT\le16}.
\]

Khoảng sai số cộng lớn nhất:

\[
G_{\rm abs}=16-15=1.
\]

Tỷ lệ chất lượng được chứng nhận cho nghiệm hiện tại:

\[
\boxed{\frac{15}{OPT}\ge\frac{15}{16}=93,75\%}.
\]

Nếu chưa dùng tính nguyên của mục tiêu, tỷ lệ từ cận phân số chỉ là:

\[
\frac{15}{33/2}=\frac{10}{11}\approx90,91\%.
\]

**Làm tròn cận nguyên có chứng minh** nâng mức bảo đảm lên 93,75% mà không phải chạy lại heuristic.

### 5.4. Khi có nghiệm giá trị 16

Nghiệm [0,2] có giá trị **16** và trọng lượng 10≤W. Ta đã có:
- Nghiệm khả thi giá trị 16 ⇒ OPT≥16.
- Cận trên nguyên U=16 ⇒ OPT≤16.

Do đó:

\[
\boxed{OPT=16}.
\]

Một lời giải tìm được từ DP, nhánh và cận hoặc một heuristic bất kỳ đều có thể trở thành **nghiệm được chứng minh tối ưu** khi giá trị của nó đóng đúng cận trên hợp lệ. Không nhất thiết phải biết thuật toán sinh ra lời giải có tên “exact” hay không; quan trọng là **chứng nhận L=U**.

### 5.5. Sai số thực và sai số được chứng nhận có thể khác nhau

Giả sử mới biết:
- Nghiệm hiện tại L=15.
- Cận trên U=16.

Ta có thể báo sai số tối đa 1, nhưng chưa thể khẳng định sai số thực đúng bằng 1 nếu chưa thấy nghiệm 16 hoặc một chứng nhận khác cho OPT.

Sau khi tìm được nghiệm 16, L tăng thành 16 và chứng nhận đóng lại. Đây chính là ý nghĩa của việc **cập nhật cận dưới** trong các solver anytime cho bài maximization.

## 6. Xây cận trên bằng relaxation: vì sao phải đúng hướng?

Một **relaxation** nới lỏng bớt ràng buộc, tạo tập khả thi lớn hơn hoặc bằng tập gốc.

Với bài **tối đa hóa**, cực đại trên tập lớn hơn không thể nhỏ hơn cực đại trên tập nhỏ:

\[
\max_{x\in F}f(x)
\le\max_{x\in R}f(x)
\quad (F\subseteq R).
\]

Nên optimum của relaxation là **upper bound** của optimum gốc.

Với bài **tối thiểu hóa**, cực tiểu trên tập lớn hơn không thể lớn hơn cực tiểu trên tập nhỏ:

\[
\min_{x\in R}f(x)
\le\min_{x\in F}f(x).
\]

Nên optimum của relaxation là **lower bound** cho bài minimization.

Quy tắc nhớ:

| Phép nới lỏng | Bài tối đa hóa | Bài tối thiểu hóa |
|---|---|---|
| Tập khả thi được mở rộng | Optimum có thể tăng | Optimum có thể giảm |
| Giá trị relaxation cung cấp | **Cận trên U** | **Cận dưới L** |

Nếu dùng một giá trị từ relaxation mà không chứng minh giải đúng optimum relaxation hoặc chỉ lấy một nghiệm bất kỳ của relaxation, có thể không thu được đúng loại cận. Ví dụ **một nghiệm khả thi của bài fractional maximization** thường chỉ là cận dưới của optimum fractional, **không tự động là cận trên của optimum integer**; cần tính hoặc chặn trên *optimum fractional* thật sự.

### 6.1. Tính cận trên ba lô chính xác

Một cài đặt dùng double để tính 16,5 rồi làm tròn xuống vì “chắc gần 16” có thể mất tính đúng nếu có lỗi floating-point. Cách an toàn trên trọng lượng/giá trị nguyên:
- So mật độ bằng **nhân chéo BigInteger**, không so hai phép chia double.
- Tính phần cuối dưới dạng phân số **tử/mẫu BigInteger**.
- Rút gọn bằng gcd để biểu diễn đẹp.
- Tính floor của cận hữu tỉ **sau khi đã có chứng minh OPT nguyên**, không phải tùy tiện làm tròn một số thực.

Với các giá trị dương, Fraction(99,6) được chuẩn hóa thành **33/2**. Floor(33/2)=16.

### 6.2. Lọc vật không thể chọn

Nếu w[i]>W, vật ấy không thể thuộc bất kỳ lời giải 0/1 hợp lệ. Có thể loại nó khỏi bài tối ưu nguyên trước khi lập relaxation. Fractional knapsack của **tập vật còn lại** vẫn là một nới lỏng hợp lệ của bài 0/1 đã lọc.

Nếu để vật w>W tham gia bài phân số, cận trên có thể vẫn hợp lệ nhưng thường lỏng hơn; nếu lọc sai một vật có thể chọn thì cận trên có thể **không còn hợp lệ**.

### 6.3. Một đối chiếu số học để phân biệt cận

Dưới cận 15≤OPT≤33/2:
- Cận trên phân số **16,5** không phải một phương án 0/1 có thể chọn.
- Giá trị nghiệm 15 là một **lower bound**.
- **Không** được so trực tiếp 15/16,5 rồi gọi “độ chính xác thực của heuristic”.
- Có thể chứng nhận 15/16,5=10/11 là **tỷ lệ tối thiểu**.
- Vì OPT nguyên, làm chặt thành U=16, được tỷ lệ tối thiểu **15/16**.

Những thuật ngữ này cần xuất hiện minh bạch trên báo cáo.

## 7. Bài tối thiểu hóa: Minimum Vertex Cover

Cho đồ thị vô hướng G=(V,E). Một **vertex cover** là tập đỉnh C sao cho mỗi cạnh (u,v) có ít nhất một trong hai đầu mút nằm trong C. Mục tiêu:

\[
\min |C|.
\]

Ở đây một cover hợp lệ có kích thước k là **cận trên U=k** của optimum, không phải cận dưới.

### 7.1. Matching tạo cận dưới thế nào?

Một **matching** M là tập cạnh đôi một không chung đỉnh. Với m=|M| cạnh rời nhau, bất kỳ vertex cover nào cũng phải chọn **ít nhất một đỉnh trên mỗi cạnh matching**.

Vì các cạnh matching rời nhau, một đỉnh không thể đồng thời bao phủ hai cạnh thuộc M. Do đó:

\[
\boxed{|M|\le OPT_{\rm VC}}.
\]

Matching cung cấp một **lower bound L=|M|** cho bài minimization.

Không cần matching phải là maximum matching để cận dưới đúng; bất kỳ matching nào cũng được. Tuy nhiên matching có nhiều cạnh hơn cho cận dưới mạnh hơn.

### 7.2. Dùng maximal matching tạo nghiệm 2-approximation

Một **maximal matching** là matching không thể thêm cạnh mới nào mà vẫn giữ tính rời đỉnh.

Có thể tạo bằng greedy:
1. Ban đầu mọi đỉnh chưa được ghép.
2. Duyệt từng cạnh (u,v).
3. Nếu cả u và v chưa ghép, chọn cạnh đó vào matching và đánh dấu u,v đã ghép.
4. Kết thúc, lấy **cả hai đầu mút** của mọi cạnh matching để làm vertex cover C.

**Vì sao C là vertex cover?** Nếu có cạnh (a,b) mà cả hai đầu mút không nằm trong C, thì cả a,b đều chưa được ghép. Ta có thể thêm (a,b) vào matching, trái với tính maximal. Vậy không tồn tại cạnh nào chưa được cover.

Vì matching có m cạnh rời nhau, C có đúng 2m đỉnh:

\[
|C|=2m.
\]

Với cận dưới m≤OPT:

\[
\boxed{|C|\le2OPT}.
\]

Đây là một **2-approximation** cho Minimum Vertex Cover, đồng thời là một cặp nghiệm/cận có thể kiểm tra được:

\[
m\le OPT\le2m.
\]

Lưu ý **maximal** không đồng nghĩa **maximum** matching. Chứng minh 2-approximation chỉ cần maximal matching, không cần giải maximum matching.

## 8. Ví dụ minimization: đồ thị hình sao

Xét đồ thị có 5 đỉnh V={0,1,2,3,4} và bốn cạnh:

~~~text
(0,1), (0,2), (0,3), (0,4)
~~~

Đỉnh 0 là tâm; các đỉnh 1,2,3,4 là lá.

Greedy maximal matching theo thứ tự cạnh chọn (0,1). Các cạnh còn lại đều chạm đỉnh 0 đã ghép, nên không thể chọn thêm. Ta có:

\[
m=1.
\]

**Cận dưới từ matching:**

\[
\boxed{L=1}.
\]

Thuật toán lấy hai đầu mút của matching tạo cover:

~~~text
C = {0,1}
size(C) = 2
~~~

Mọi cạnh đều có đầu mút 0, nên C khả thi. Nó cung cấp:

\[
\boxed{U=2}.
\]

Cặp cận:

\[
1\le OPT\le2.
\]

Cận tỷ lệ cho nghiệm hiện tại:

\[
\boxed{\frac{U}{OPT}\le\frac{U}{L}=2}.
\]

### 8.1. Cải thiện nghiệm mà không sửa cận dưới

Một heuristic đơn giản phát hiện đỉnh 0 bao phủ toàn bộ các cạnh và trả:

~~~text
C' = {0}
size(C') = 1
~~~

Đây là cover hợp lệ, nên cận trên mới U=1. Cận dưới matching vẫn L=1. Ta có:

\[
\boxed{1\le OPT\le1\Rightarrow OPT=1}.
\]

Nghiệm {0} được **chứng minh tối ưu** bằng việc đóng cận, dù chưa phải chạy thuật toán vét cạn toàn bộ \(2^5\) tập đỉnh.

### 8.2. Vì sao tỉ lệ 2 của thuật toán không phải tỉ lệ thực của mọi lần chạy?

Ví dụ hình sao, kết quả matching-cover có kích thước 2 còn optimum là 1, nên tỷ lệ thực bằng 2 — đạt trường hợp xấu nhất của bảo đảm.

Nhưng trên đồ thị khác, matching-cover có thể trùng optimum hoặc đạt tỷ lệ thấp hơn 2. Định lý \(|C|\le2OPT\) chỉ là **cận xấu nhất**, không khẳng định mọi output có chất lượng đúng 2×OPT.

Nếu có một lower bound tốt hơn từ cấu trúc riêng của đồ thị hoặc giải relaxation chặt hơn, tỷ lệ theo instance cũng có thể được làm chặt.

## 9. Chứng chỉ chất lượng phải mang những gì?

Một báo cáo tốt không chỉ ghi “98% optimal”. Với mỗi lần giải bài tối ưu cần:
- **Phiên bản input:** định danh, hash hoặc phiên bản dữ liệu; tránh cận cũ so với nghiệm mới.
- **Loại bài toán:** minimize hay maximize.
- **Cách tính giá trị mục tiêu** và đơn vị.
- **Nghiệm cụ thể:** danh sách vật/đỉnh/cạnh/lịch trình và checker tính khả thi.
- **L và U:** giá trị chính xác, nguồn gốc và điều kiện áp dụng.
- **Loại cận:** relaxation, matching, dual feasibility, exact subtree bound, hay một định lý xấp xỉ.
- **Absolute gap** và tỷ lệ chứng nhận khi phép chia hợp lệ.
- **Trạng thái:** OPTIMAL, GUARANTEED, PARTIAL, UNKNOWN hoặc HEURISTIC_ONLY; định nghĩa nhất quán trong hệ thống.
- **Ngân sách:** giới hạn thời gian, RAM, số nút, epsilon hoặc số lượt thử.
- **Ngày/phiên bản thuật toán:** đặc biệt khi kết quả phục vụ kiểm toán.

Không có cận hợp lệ thì có thể báo **nghiệm khả thi và benchmark**, nhưng **không** được báo một khoảng tối ưu chắc chắn chỉ từ trực giác.

### 9.1. Cận đóng và chứng minh tối ưu

Nếu L=U với cùng bài toán và cùng bộ dữ liệu, một nghiệm khả thi đạt cận thích hợp là optimal.

Ví dụ:
- Maximization: có nghiệm 16 và chứng minh OPT≤16.
- Minimization: có cover 1 và matching chứng minh OPT≥1.

Điều này không đồng nghĩa mọi tình huống công bố L≈U theo số thực dấu phẩy động đều chứng minh tối ưu: phải xét **sai số số học, rounding và tolerance**.

### 9.2. Khi cận không đóng

Nếu maximization có L=15,U=16, chỉ chắc nghiệm cách OPT không quá 1; nếu minimization có L=1,U=2, chỉ chắc nghiệm cách OPT không quá 1.

Hai khoảng nhìn giống nhau nhưng:
- Maximization: tỷ lệ chất lượng ≥15/16.
- Minimization: tỷ lệ hao phí ≤2/1=2.

Báo một phần trăm “gap” duy nhất mà không ghi **công thức và hướng tối ưu hóa** rất dễ gây hiểu nhầm.

## 10. Cận cho bài toán nguyên: floor và ceil

Khi tối ưu f(x) luôn là số nguyên:

- Với **maximization**, nếu U là cận trên hữu tỉ thì:
  
  \[
  OPT\le\lfloor U\rfloor.
  \]

- Với **minimization**, nếu L là cận dưới hữu tỉ thì:
  
  \[
  OPT\ge\lceil L\rceil.
  \]

Đây là **làm chặt hợp lệ** dựa trên tính nguyên của OPT.

Ví dụ:
- Knapsack có upper bound 33/2 ⇒ OPT≤16.
- Một bài min có lower bound 7/2 ⇒ OPT≥4, **nếu** giá trị mục tiêu mọi nghiệm đều nguyên.

Nếu mục tiêu là số thực, việc tự lấy floor/ceil có thể làm mất tính đúng.

### 10.1. Không được làm tròn theo hướng sai

- Maximization: lấy **ceil(U)** vẫn là cận trên nhưng lỏng hơn; lấy **floor(U)** chỉ đúng nếu OPT nguyên.
- Minimization: lấy **floor(L)** vẫn là cận dưới nhưng lỏng hơn; lấy **ceil(L)** chỉ đúng nếu OPT nguyên.
- Maximization mà lấy **ceil(L)** đối với lower bound từ một nghiệm có mục tiêu không nguyên có thể tạo lower bound sai.
- Minimization mà lấy **floor(U)** đối với một nghiệm mục tiêu không nguyên có thể tạo upper bound sai.

Với floating-point, hướng làm tròn phải được quản lý để không vô tình chứng nhận một bất đẳng thức sai. Số học phân số BigInteger giúp tránh vấn đề này trên dữ liệu nguyên.

## 11. Lựa chọn cận khi không thể giải optimum

### 11.1. Relaxation

Nới lỏng ràng buộc của bài gốc để có một bài dễ hơn:
- Maximization: optimum relaxation cung cấp cận trên.
- Minimization: optimum relaxation cung cấp cận dưới.

Ví dụ fractional knapsack, LP relaxation, bài toán bỏ một số ràng buộc khó. Chất lượng cận phụ thuộc mức độ gần của relaxation với bài toán nguyên.

### 11.2. Bất đẳng thức tổ hợp

Không cần giải relaxation:
- Vertex Cover: kích thước matching là lower bound.
- Với nhiều bài scheduling: tổng thời lượng chia cho số máy có thể là một lower bound, sau khi xét đúng mô hình máy/ràng buộc.
- Với các bài đường đi: một đường đi cụ thể là upper bound cho bài tìm đường đi ngắn nhất; một heuristic admissible hoặc bài toán nới lỏng có thể cung cấp lower bound.

Không nên áp dụng một công thức bound quen thuộc nếu bài thực tế có ràng buộc khác, chẳng hạn cạnh âm, lịch trình có thứ tự bắt buộc hoặc máy chạy tốc độ khác nhau.

### 11.3. Dual bound

Với bài toán tuyến tính có đối ngẫu, **nghiệm đối ngẫu khả thi** có thể cung cấp cận theo hướng do **weak duality** quy định:
- Trong dạng LP minimization chuẩn, nghiệm dual maximization khả thi cho cận dưới.
- Trong dạng LP maximization chuẩn, nghiệm dual minimization khả thi cho cận trên.

Để dùng cận dual làm certificate, phải kiểm cả **dual feasibility**; một vector dual bất kỳ chưa chắc cấp cận đúng.

### 11.4. Bound trên cây tìm kiếm

Trong branch-and-bound:
- Giữ incumbent khả thi toàn cục.
- Mỗi nút chưa xử lý có một upper bound (max) hoặc lower bound (min).
- Gộp cận từ mọi nhánh còn mở để thu cận toàn cục hợp lệ.
- Chỉ loại nhánh nếu cận của nhánh chứng minh nó không thể cải thiện incumbent.

Một cận chỉ tính cho nhánh đang xét **không tự động** là cận toàn cục nếu còn nhánh mở khác.

## 12. Đánh giá anytime, timeout và stopping rule

Một thuật toán anytime cung cấp nghiệm hiện tại trước khi kết thúc, sau đó có thể cải thiện khi có thêm thời gian.

### 12.1. Cập nhật cận an toàn

Đối với **maximization**:
- Incumbent L chỉ **tăng** khi tìm được nghiệm khả thi tốt hơn.
- Upper bound toàn cục U có thể **giảm** khi chứng minh loại bớt khả năng.
- Luôn giữ L≤U; nếu L=U, chứng nhận optimum.

Đối với **minimization**:
- Incumbent U chỉ **giảm** khi tìm được nghiệm khả thi tốt hơn.
- Lower bound toàn cục L có thể **tăng** theo quá trình chứng minh.
- Luôn giữ L≤U.

Nếu một phần mềm báo **bound bị đảo** (L>U) thì ít nhất một thành phần của chứng nhận, số học hoặc phiên bản dữ liệu đang sai. Không được âm thầm hoán đổi hai số để che lỗi.

### 12.2. Dừng theo chất lượng, không nhất thiết theo optimum

Một hệ thống có thể dừng khi:
- G_abs≤ngưỡng sai số cộng.
- Maximization: L/U≥alpha, với U>0.
- Minimization: U/L≤rho, với L>0.
- Có chứng nhận L=U.
- Hết deadline, trả PARTIAL và khoảng cận hiện có.

Cần phân biệt **đạt mục tiêu chất lượng** với **đã chứng minh tối ưu**. Ví dụ L/U≥0,99 không suy ra L=OPT; nó chỉ cho biết nghiệm đạt ít nhất 99% OPT dưới những giả thiết ratio.

### 12.3. Khi bound bị lỏng

Một nghiệm có thể thực sự tối ưu nhưng cận chưa chặt. Ví dụ một solver tìm được optimum 16 nhưng chỉ chứng minh U=17; nó chưa có **certificate tối ưu** từ cặp L/U, dù một oracle bên ngoài có thể biết đó là optimum.

Không nên kết luận thuật toán “chất lượng thấp” chỉ vì **certified gap lớn**: gap có thể lớn do bound lỏng, không nhất thiết do nghiệm kém.

Có hai hướng cải thiện khác nhau:
1. **Cải thiện nghiệm (incumbent):** nâng L trong bài max, hạ U trong bài min.
2. **Cải thiện chứng minh (bound):** hạ U trong bài max, nâng L trong bài min.

Một heuristic giỏi chủ yếu giúp hướng thứ nhất; các kỹ thuật relaxations, cuts và branching có thể giúp hướng thứ hai.

## 13. Bộ kiểm chứng độc lập trên dữ liệu nhỏ

Để tin bộ đánh giá, cần kiểm định **cả nghiệm và cận** bằng một oracle đơn giản trên instance nhỏ.

### 13.1. Kiểm thử Knapsack

Sinh n≤10 vật, trọng lượng dương, giá trị không âm, sức chứa nhỏ:
1. Liệt kê tất cả 2ⁿ tập con để tìm OPT thật.
2. Sinh phương án tham lam theo mật độ và kiểm tra khả thi.
3. Tính fractional upper U bằng phân số.
4. Kiểm tra \(f(\text{greedy})\le OPT\le U\).
5. Vì OPT nguyên, kiểm tra \(OPT\le\lfloor U\rfloor\).
6. Chạy DP chính xác và so giá trị với oracle.
7. Kiểm tra danh sách vật của DP khả thi, tổng trọng lượng/giá trị đúng.
8. Nếu nghiệm hiện tại bằng floor(U), công nhận chứng nhận tối ưu.

Đặc biệt thử W=0, vật quá nặng, vật có giá trị 0, mật độ bằng nhau, một vật, nhiều vật và tổng giá trị gần giới hạn long.

### 13.2. Kiểm thử Vertex Cover

Sinh đồ thị vô hướng đơn n≤9:
1. Liệt kê tất cả 2ⁿ tập đỉnh để tìm cover nhỏ nhất OPT.
2. Duyệt cạnh tạo maximal matching M.
3. Lấy hai đầu mút của các cạnh M làm cover C.
4. Kiểm tra **mọi cạnh đều được cover**.
5. Kiểm tra \(|M|\le OPT\le|C|=2|M|\).
6. Nếu cover mới có size=|M|, chứng nhận optimum ngay.

Thử đồ thị rỗng, một cạnh, hình sao, chu trình, clique nhỏ, đồ thị nhiều thành phần và đỉnh cô lập. Với đồ thị rỗng, L=U=0 là optimum nhưng **ratio U/L=0/0 không xác định**.

### 13.3. Test có phản ví dụ

Một hệ thống kiểm định tốt nên cố ý cho:
- Một candidate **vi phạm sức chứa**.
- Một cover bỏ sót cạnh.
- Một **upper bound nhỏ hơn candidate lower** trong bài max.
- Một **lower bound lớn hơn candidate upper** trong bài min.
- Một fractional bound bị **làm tròn sai hướng**.
- Một certificate dùng dữ liệu cũ.

Checker phải từ chối, không tự “sửa cho hợp lý”.

## 14. Java 17 hoàn chỉnh: nghiệm, cận và chứng nhận

Lưu tệp **BoundQualityDemo.java**. Mã gồm:
- Bài Knapsack tối đa hóa: tham lam theo mật độ, fractional upper chính xác bằng BigInteger Fraction, exact DP và truy vết, kiểm tra phương án.
- Bài Minimum Vertex Cover tối thiểu hóa: matching lower bound, cover từ maximal matching, kiểm tra cover và oracle vét cạn cho n nhỏ.
- Công thức absolute gap, ratio và điều kiện chứng nhận optimum.
- Kiểm tra đầu vào/đầu ra hỏng để tránh một báo cáo cận sai.
- Ví dụ có **cận phân số 33/2**, làm chặt thành **cận nguyên 16**, sau đó đóng cận với nghiệm 16.

Hợp đồng chương trình:
- Knapsack: trọng lượng int dương, giá trị long không âm, W≥0; tổng giá trị các vật phải vừa long để dùng DP long.
- Graph: đồ thị vô hướng không chứa self-loop, các đỉnh 0..V−1; cạnh trùng nếu có vẫn không làm mất tính đúng của maximal matching.
- Các giới hạn demo cho exact DP/brute chỉ để tránh cấp phát hoặc duyệt quá lớn, không thay đổi định nghĩa toán học.
- BigInteger cho mọi phép nhân chéo mật độ và phân số cận.
- Không dùng double để **chứng minh** cận.

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class BoundQualityDemo {
    private BoundQualityDemo() {
    }

    private static final int MAX_KNAPSACK_W = 10_000;
    private static final long MAX_DP_CELLS = 500_000;
    private static final int MAX_COVER_BRUTE_VERTICES = 18;

    public record Item(int weight, long value) {
    }

    public record Plan(long value, int weight, List<Integer> indices) {
        public Plan {
            indices = List.copyOf(indices);
        }
    }

    // Tử/mẫu chính xác; toàn bộ upper bound trong demo không âm.
    public record Fraction(
            BigInteger numerator, BigInteger denominator) {
        public Fraction {
            Objects.requireNonNull(numerator, "numerator");
            Objects.requireNonNull(denominator, "denominator");
            if (denominator.signum() == 0) {
                throw new IllegalArgumentException(
                        "Denominator cannot be zero");
            }
            if (denominator.signum() < 0) {
                numerator = numerator.negate();
                denominator = denominator.negate();
            }
            BigInteger gcd = numerator.gcd(denominator);
            numerator = numerator.divide(gcd);
            denominator = denominator.divide(gcd);
        }

        public static Fraction whole(long x) {
            return new Fraction(
                    BigInteger.valueOf(x), BigInteger.ONE);
        }

        // Chỉ được áp dụng cho một upper bound của mục tiêu nguyên.
        public BigInteger floorNonnegative() {
            if (numerator.signum() < 0) {
                throw new IllegalArgumentException(
                        "Negative bound outside demo contract");
            }
            return numerator.divide(denominator);
        }

        @Override
        public String toString() {
            return denominator.equals(BigInteger.ONE)
                    ? numerator.toString()
                    : numerator + "/" + denominator;
        }
    }

    private static void validateItems(Item[] items, int capacity) {
        Objects.requireNonNull(items, "items");
        if (capacity < 0) {
            throw new IllegalArgumentException(
                    "Capacity must be nonnegative");
        }
        long totalValue = 0;
        for (Item item : items) {
            Objects.requireNonNull(item, "item");
            if (item.weight() <= 0 || item.value() < 0) {
                throw new IllegalArgumentException(
                        "Weight positive and value nonnegative required");
            }
            totalValue = Math.addExact(totalValue, item.value());
        }
    }

    private static List<Integer> densityOrder(
            Item[] items, int capacity) {
        List<Integer> order = new ArrayList<>();
        for (int i = 0; i < items.length; i++) {
            // Bỏ vật không thể chọn ngay cả khi đứng một mình.
            if (items[i].weight() <= capacity) {
                order.add(i);
            }
        }

        order.sort((i, j) -> {
            Item a = items[i], b = items[j];
            BigInteger left = BigInteger.valueOf(a.value())
                    .multiply(BigInteger.valueOf(b.weight()));
            BigInteger right = BigInteger.valueOf(b.value())
                    .multiply(BigInteger.valueOf(a.weight()));
            int cmp = right.compareTo(left);
            return cmp != 0 ? cmp : Integer.compare(i, j);
        });
        return order;
    }

    // Một heuristic khả thi; bản thân thuật toán này không có
    // bảo đảm tỷ lệ xấu nhất với 0/1 Knapsack.
    public static Plan densityGreedy(Item[] items, int capacity) {
        validateItems(items, capacity);
        List<Integer> indices = new ArrayList<>();
        int used = 0;
        long value = 0;

        for (int index : densityOrder(items, capacity)) {
            Item item = items[index];
            if (item.weight() <= capacity - used) {
                used += item.weight();
                value = Math.addExact(value, item.value());
                indices.add(index);
            }
        }
        Collections.sort(indices);
        return new Plan(value, used, indices);
    }

    // Relaxation 0<=x_i<=1: upper bound của 0/1 Knapsack.
    public static Fraction fractionalUpper(
            Item[] items, int capacity) {
        validateItems(items, capacity);
        int remaining = capacity;
        BigInteger whole = BigInteger.ZERO;

        for (int index : densityOrder(items, capacity)) {
            Item item = items[index];
            if (item.weight() <= remaining) {
                whole = whole.add(
                        BigInteger.valueOf(item.value()));
                remaining -= item.weight();
            } else {
                BigInteger w = BigInteger.valueOf(item.weight());
                BigInteger numerator = whole.multiply(w)
                        .add(BigInteger.valueOf(item.value())
                                .multiply(BigInteger.valueOf(
                                        remaining)));
                return new Fraction(numerator, w);
            }
        }
        return new Fraction(whole, BigInteger.ONE);
    }

    public static boolean feasibleKnapsack(
            Item[] items, int capacity, Plan plan) {
        validateItems(items, capacity);
        Objects.requireNonNull(plan, "plan");

        long totalWeight = 0;
        long totalValue = 0;
        Set<Integer> seen = new HashSet<>();

        for (Integer index : plan.indices()) {
            if (index == null || index < 0
                    || index >= items.length || !seen.add(index)) {
                return false;
            }
            Item item = items[index];
            totalWeight += item.weight();
            totalValue = Math.addExact(totalValue, item.value());
        }
        return totalWeight <= capacity
                && totalWeight == plan.weight()
                && totalValue == plan.value();
    }

    // Exact DP, giữ bảng để truy vết. Chỉ chạy khi RAM đủ.
    public static Plan exactKnapsack(
            Item[] items, int capacity) {
        validateItems(items, capacity);
        int n = items.length;
        long cells = ((long) n + 1) * ((long) capacity + 1);
        if (capacity > MAX_KNAPSACK_W || cells > MAX_DP_CELLS) {
            throw new IllegalArgumentException(
                    "Exact DP demo budget exceeded");
        }

        long[][] dp = new long[n + 1][capacity + 1];
        boolean[][] take = new boolean[n + 1][capacity + 1];

        for (int i = 1; i <= n; i++) {
            Item item = items[i - 1];
            for (int c = 0; c <= capacity; c++) {
                long best = dp[i - 1][c];
                if (item.weight() <= c) {
                    long candidate = Math.addExact(
                            dp[i - 1][c - item.weight()],
                            item.value());
                    if (candidate > best) {
                        best = candidate;
                        take[i][c] = true;
                    }
                }
                dp[i][c] = best;
            }
        }

        List<Integer> indices = new ArrayList<>();
        int remaining = capacity;
        for (int i = n; i >= 1; i--) {
            if (take[i][remaining]) {
                indices.add(i - 1);
                remaining -= items[i - 1].weight();
            }
        }
        Collections.reverse(indices);
        return new Plan(
                dp[n][capacity],
                capacity - remaining,
                indices);
    }

    // Cần caller cung cấp một upper đã được chứng minh đúng.
    // Từ chối ít nhất những certificate mâu thuẫn L>U.
    public static BigInteger certifiedMaxGap(
            long feasibleValue, Fraction upper) {
        Objects.requireNonNull(upper, "upper");
        if (feasibleValue < 0) {
            throw new IllegalArgumentException(
                    "Negative objective outside demo contract");
        }

        BigInteger roundedUpper = upper.floorNonnegative();
        BigInteger lower = BigInteger.valueOf(feasibleValue);
        if (roundedUpper.compareTo(lower) < 0) {
            throw new IllegalArgumentException(
                    "Inconsistent lower and upper bounds");
        }
        return roundedUpper.subtract(lower);
    }

    public record Edge(int u, int v) {
    }

    public record CoverResult(
            List<Integer> vertices, int matchingSize) {
        public CoverResult {
            vertices = List.copyOf(vertices);
        }
    }

    private static void validateGraph(
            int vertexCount, List<Edge> edges) {
        Objects.requireNonNull(edges, "edges");
        if (vertexCount < 0) {
            throw new IllegalArgumentException(
                    "Vertex count must be nonnegative");
        }
        for (Edge e : edges) {
            Objects.requireNonNull(e, "edge");
            if (e.u() < 0 || e.u() >= vertexCount
                    || e.v() < 0 || e.v() >= vertexCount
                    || e.u() == e.v()) {
                throw new IllegalArgumentException(
                        "Invalid edge or self-loop");
            }
        }
    }

    // Matching được tạo bằng greedy, maximal theo thứ tự cạnh.
    // Các đầu mút của matching tạo một vertex cover hợp lệ.
    public static CoverResult matchingCover(
            int vertexCount, List<Edge> edges) {
        validateGraph(vertexCount, edges);
        boolean[] matched = new boolean[vertexCount];
        int matchingSize = 0;

        for (Edge e : edges) {
            if (!matched[e.u()] && !matched[e.v()]) {
                matched[e.u()] = true;
                matched[e.v()] = true;
                matchingSize++;
            }
        }

        List<Integer> cover = new ArrayList<>();
        for (int v = 0; v < vertexCount; v++) {
            if (matched[v]) {
                cover.add(v);
            }
        }
        return new CoverResult(cover, matchingSize);
    }

    public static boolean feasibleCover(
            int vertexCount, List<Edge> edges,
            List<Integer> selected) {
        validateGraph(vertexCount, edges);
        Objects.requireNonNull(selected, "selected");
        boolean[] inCover = new boolean[vertexCount];

        for (Integer vertex : selected) {
            if (vertex == null || vertex < 0
                    || vertex >= vertexCount
                    || inCover[vertex]) {
                return false;
            }
            inCover[vertex] = true;
        }

        for (Edge e : edges) {
            if (!inCover[e.u()] && !inCover[e.v()]) {
                return false;
            }
        }
        return true;
    }

    // Brute oracle cho đồ thị rất nhỏ; không dùng để tạo matching.
    public static int bruteMinCover(
            int vertexCount, List<Edge> edges) {
        validateGraph(vertexCount, edges);
        if (vertexCount > MAX_COVER_BRUTE_VERTICES) {
            throw new IllegalArgumentException(
                    "Graph too large for brute demo");
        }

        int best = vertexCount + 1;
        long limit = 1L << vertexCount;
        for (long mask = 0; mask < limit; mask++) {
            int count = Long.bitCount(mask);
            if (count >= best) {
                continue;
            }

            boolean valid = true;
            for (Edge e : edges) {
                boolean a = (mask & (1L << e.u())) != 0;
                boolean b = (mask & (1L << e.v())) != 0;
                if (!a && !b) {
                    valid = false;
                    break;
                }
            }

            if (valid) {
                best = count;
            }
        }
        return best;
    }

    private static void require(
            boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Item[] items = {
            new Item(4, 7),
            new Item(5, 8),
            new Item(6, 9)
        };
        int capacity = 10;

        Plan greedy = densityGreedy(items, capacity);
        Fraction upper = fractionalUpper(items, capacity);
        BigInteger integerUpper = upper.floorNonnegative();
        BigInteger gap = certifiedMaxGap(
                greedy.value(), upper);
        Plan exact = exactKnapsack(items, capacity);

        require(feasibleKnapsack(items, capacity, greedy),
                "Greedy solution infeasible");
        require(feasibleKnapsack(items, capacity, exact),
                "Exact solution infeasible");

        System.out.println("Knapsack greedy items: "
                + greedy.indices());
        System.out.println("Knapsack greedy value: "
                + greedy.value());
        System.out.println("Knapsack candidate feasible: "
                + feasibleKnapsack(items, capacity, greedy));
        System.out.println("Knapsack fractional upper: "
                + upper);
        System.out.println("Knapsack integer upper: "
                + integerUpper);
        System.out.println("Knapsack certificate gap: "
                + gap);
        System.out.println("Knapsack certified ratio: "
                + new Fraction(
                    BigInteger.valueOf(greedy.value()),
                    integerUpper));
        System.out.println("Knapsack greedy certified optimal: "
                + (gap.signum() == 0));
        System.out.println("Knapsack exact DP items: "
                + exact.indices());
        System.out.println("Knapsack exact DP value: "
                + exact.value());
        System.out.println("Knapsack exact certified optimal: "
                + (certifiedMaxGap(
                    exact.value(), upper).signum() == 0));

        List<Edge> star = List.of(
                new Edge(0, 1),
                new Edge(0, 2),
                new Edge(0, 3),
                new Edge(0, 4));

        CoverResult approximation = matchingCover(5, star);
        int lower = approximation.matchingSize();
        int candidateUpper = approximation.vertices().size();
        List<Integer> improved = List.of(0);

        require(feasibleCover(
                5, star, approximation.vertices()),
                "Matching cover infeasible");
        require(feasibleCover(5, star, improved),
                "Improved cover infeasible");

        System.out.println("Vertex matching edges: " + lower);
        System.out.println("Vertex matching cover: "
                + approximation.vertices());
        System.out.println("Vertex candidate feasible: "
                + feasibleCover(
                    5, star, approximation.vertices()));
        System.out.println("Vertex candidate upper: "
                + candidateUpper);
        System.out.println("Vertex certificate ratio: "
                + candidateUpper + "/" + lower);
        System.out.println("Vertex improved cover: "
                + improved);
        System.out.println("Vertex improved feasible: "
                + feasibleCover(5, star, improved));
        System.out.println("Vertex improved certified optimal: "
                + (improved.size() == lower));
        System.out.println("Vertex brute optimum: "
                + bruteMinCover(5, star));

        CoverResult empty = matchingCover(0, List.of());
        System.out.println("Empty vertex graph lower: "
                + empty.matchingSize());
        System.out.println("Empty vertex graph cover size: "
                + empty.vertices().size());

        System.out.println("Zero capacity knapsack upper: "
                + fractionalUpper(items, 0));

        try {
            certifiedMaxGap(15, Fraction.whole(14));
            System.out.println("Reject bad bound: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject bad bound: true");
        }

        try {
            matchingCover(3, List.of(new Edge(1, 1)));
            System.out.println("Reject self loop: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject self loop: true");
        }

        System.out.println("Reject invalid candidate: "
                + !feasibleCover(
                    5, star, List.of(0, 0)));
    }
}
~~~

### 14.1. Biên dịch và chạy

Dùng JDK 17 hoặc mới hơn. Lưu đúng tên **BoundQualityDemo.java**, sau đó:

~~~bash
javac -encoding UTF-8 BoundQualityDemo.java
java BoundQualityDemo
~~~

**Stdout dự kiến:**

~~~text
Knapsack greedy items: [0, 1]
Knapsack greedy value: 15
Knapsack candidate feasible: true
Knapsack fractional upper: 33/2
Knapsack integer upper: 16
Knapsack certificate gap: 1
Knapsack certified ratio: 15/16
Knapsack greedy certified optimal: false
Knapsack exact DP items: [0, 2]
Knapsack exact DP value: 16
Knapsack exact certified optimal: true
Vertex matching edges: 1
Vertex matching cover: [0, 1]
Vertex candidate feasible: true
Vertex candidate upper: 2
Vertex certificate ratio: 2/1
Vertex improved cover: [0]
Vertex improved feasible: true
Vertex improved certified optimal: true
Vertex brute optimum: 1
Empty vertex graph lower: 0
Empty vertex graph cover size: 0
Zero capacity knapsack upper: 0
Reject bad bound: true
Reject self loop: true
Reject invalid candidate: true
~~~

### 14.2. Vì sao chương trình báo các kết quả đó?

**Knapsack greedy [0,1], value=15:** các vật đã sắp theo mật độ 7/4, 8/5, 9/6. Hai vật đầu chiếm trọng lượng 9 và giá trị 15, còn 1 đơn vị sức chứa.

**Fractional upper 33/2:** có thể lấy một phần 1/6 vật cuối trong relaxation, cộng giá trị 3/2 vào 15. Fraction chuẩn hóa 99/6 thành 33/2.

**Integer upper 16:** vì optimum 0/1 là nguyên, floor(33/2)=16.

**Certificate gap 1:** cận trên 16 trừ nghiệm hiện tại 15.

**Certified ratio 15/16:** dù heuristic không có bảo đảm xấu nhất đủ mạnh riêng, với cận trên của **instance này** nó được chứng nhận đạt tối thiểu 93,75% OPT.

**Exact DP [0,2], value=16:** lấy vật trọng lượng 4 và 6, đạt sức chứa 10 và giá trị 7+9=16. Cùng cận trên nguyên 16, chứng minh OPT=16.

**Vertex matching edges=1:** hình sao chỉ chọn được một cạnh matching; đó là cận dưới 1 của optimum cover.

**Matching cover [0,1], candidate upper=2:** lấy hai đầu mút cạnh (0,1) có tập cover hai đỉnh; mọi cạnh đều chạm đỉnh 0. Tỷ lệ được chứng nhận **2/1=2**.

**Improved cover [0]:** tập một đỉnh 0 bao phủ mọi cạnh. Vì lower bound vẫn 1, ta có **L=U=1**, chứng minh tối ưu.

**Empty graph:** không có cạnh nên matching=0 và cover rỗng là hợp lệ, optimum=0. Không chia 0/0 để tạo tỷ lệ.

**Zero capacity Knapsack upper 0:** mọi trọng lượng đều dương, W=0 nên không vật nào khả thi; fractional upper sau khi lọc cũng bằng 0.

**Reject bad bound:** đưa upper=14 khi đã có nghiệm khả thi giá trị 15 tạo mâu thuẫn L>U, nên certifiedMaxGap ném IllegalArgumentException. Nhưng lưu ý checker **không thể chứng minh mọi upper bound được cung cấp là đúng**: nó chỉ bắt một lớp lỗi tự mâu thuẫn. Cần chứng minh nguồn cận riêng biệt.

**Reject self loop:** bản demo chỉ nhận cạnh nối hai đỉnh phân biệt. Self-loop đòi xử lý riêng trong vertex cover và matching; cấm nó để giữ chính xác chứng minh đang dùng.

**Reject invalid candidate:** danh sách [0,0] chọn cùng một đỉnh hai lần, không được chấp nhận làm một tập đỉnh hợp lệ.

### 14.3. Độ phức tạp

| Phần | Thời gian | Bộ nhớ phụ | Vai trò |
|---|---|---|---|
| densityOrder | O(n log n) phép so | O(n) | Thứ tự mật độ |
| densityGreedy | O(n log n) phép so | O(n) | Nghiệm khả thi, không cận tỷ lệ chung |
| fractionalUpper | O(n log n) phép so | O(n) | Cận trên chính xác |
| exactKnapsack | O(nW) | O(nW) | Giải exact, có truy vết |
| feasibleKnapsack | O(n) + số index | O(n) | Kiểm chứng nghiệm |
| matchingCover | O(V+E) | O(V) | Nghiệm 2-approx, lower matching |
| feasibleCover | O(V+E) | O(V) | Kiểm chứng cover |
| bruteMinCover | O(2^V(V+E)) theo triển khai kiểm đếm/thử | O(1) ngoài dữ liệu | Oracle nhỏ |

Những cận này đếm thao tác số học trong mô hình đơn vị. BigInteger comparator, nhân chéo và gcd có chi phí phụ thuộc số bit. Trọng lượng, sức chứa là int; giá trị vật là long, code kiểm tra tổng giá trị vừa long trước khi dùng DP.

## 15. Quy trình ra quyết định dựa trên certificate

Một quy trình ổn định:

1. **Xác định hướng mục tiêu** và miền dữ liệu; không lấy công thức ratio của bài max dùng cho min.
2. **Tạo nghiệm khả thi** nhanh, xác minh lại toàn bộ ràng buộc.
3. **Tạo bound toán học hợp lệ**: từ relaxation, matching, dual, hoặc một kỹ thuật thích hợp.
4. **Kiểm tra hướng bound:** max cần U≥OPT; min cần L≤OPT.
5. **Chuẩn hóa số học**: phân số, BigInteger, floor/ceil hợp lệ cho mục tiêu nguyên.
6. **Tính certificate**: L,U, gap cộng, ratio nếu mẫu số>0.
7. **So với SLA chất lượng**: ratio đạt ngưỡng chưa? gap có đủ nhỏ không?
8. **Nếu chưa đạt**, dùng thêm tài nguyên cho nghiệm tốt hơn hoặc cận chặt hơn.
9. **Nếu hết deadline**, trả trạng thái PARTIAL cùng certificate đã có, không tự gắn OPTIMAL.
10. **Nếu L=U**, trả OPTIMAL và giữ cách tái kiểm chứng cho người dùng/hệ thống.

Quy trình này tách **tìm nghiệm** khỏi **đánh giá/chứng nhận nghiệm**. Vì thế có thể thay heuristic mà vẫn dùng cùng bộ kiểm chứng tính khả thi và bound, hoặc giữ nguyên heuristic nhưng nâng chất lượng báo cáo bằng cận mạnh hơn.

## 16. Sai lầm phổ biến

1. **Nhầm cận trên với cận dưới giữa maximization và minimization.**
2. **Dùng phương án không khả thi làm certificate**, khiến L/U sai từ gốc.
3. **Tin giá trị mục tiêu mà solver tự trả** nhưng không tính lại từ lời giải cụ thể.
4. **Nhầm absolute gap với sai số thực**, trong khi gap thường chỉ là cận trên của sai số.
5. **Báo phần trăm tối ưu thực tế** từ L/U hoặc U/L dù chưa biết OPT.
6. **Dùng cùng công thức ratio cho cả hai chiều tối ưu.**
7. **Chia cho 0** ở trường hợp OPT hoặc bound bằng 0.
8. **Dùng ratio nhân khi mục tiêu có thể âm** mà không xác định lại metric.
9. **Lấy một nghiệm bất kỳ của relaxation max làm upper bound** mà không chứng minh nó là optimum hoặc có upper hợp lệ.
10. **Dùng dữ liệu phiên bản khác nhau** để tính nghiệm và cận.
11. **Làm tròn fractional upper của bài max không nguyên mục tiêu xuống tùy ý**.
12. **Làm tròn lower của bài min sai hướng**, có thể biến nó thành cận không đúng.
13. **So mật độ bằng double** gây lỗi thứ tự ở những phân số rất gần nhau.
14. **Nhân chéo bằng long nhưng không kiểm overflow**, làm sai mật độ.
15. **Dùng Fraction bị chia cho mẫu âm hoặc mẫu 0** mà không chuẩn hóa.
16. **Không lọc vật quá sức chứa**, hoặc lọc sai các vật có thể chọn.
17. **Lấy fractional optimum làm nghiệm 0/1 hợp lệ**, dù có vật chỉ được chọn một phần.
18. **Gọi heuristic tham lam là exact** vì chạy nhanh và thấy nghiệm có vẻ đẹp.
19. **Gắn nhãn OPTIMAL khi solver bị timeout** dù vẫn còn gap.
20. **Coi bound lỏng là chứng cứ nghiệm kém**, trong khi nghiệm có thể đã tối ưu.
21. **Coi matching bất kỳ là maximum matching**, dù chỉ cần maximal để tạo cover hai đầu mút.
22. **Gán cận dưới cover bằng kích thước tập cover**, sai chiều của minimization.
23. **Gọi cặp đầu mút của matching là cover hợp lệ mà không kiểm maximal matching**, bỏ điều kiện cần.
24. **Quên chứng minh mọi cạnh được cover**, chỉ kiểm kích thước tập đỉnh.
25. **Coi ratio 2 của matching cover là chất lượng thực trong mọi instance**, nhầm bảo đảm tệ nhất với thực tế.
26. **Dùng cận của một nhánh DFS làm cận toàn cục** dù có nhánh khác chưa xét.
27. **Cắt nhánh theo upper/lower không hợp lệ** trong branch-and-bound, loại mất optimum.
28. **Bỏ yếu tố số học chính xác** khi chứng nhận L=U.
29. **Dùng một vài benchmark để tuyên bố bảo đảm toàn cục**.
30. **Không kiểm thử bằng oracle vét cạn trên các instance nhỏ**.
31. **Không trả lời giải cụ thể kèm index/đỉnh**, khiến người khác không thể kiểm lại tính khả thi.
32. **Quên kích thước bộ nhớ và bit complexity** khi thêm bước chứng nhận.
33. **Không định nghĩa rõ tiêu chí dừng** theo gap/ratio/budget.
34. **Không xử lý bài toán không có nghiệm khả thi**, trong đó không thể dùng trực tiếp công thức giả định F không rỗng.
35. **Không phân biệt kết quả xác suất với cận tất định** nếu bound được sinh bằng thuật toán ngẫu nhiên.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Với bài tối đa hóa, một nghiệm khả thi giá trị 15 cung cấp loại cận nào?

**Đáp án:** Cận dưới L=15, vì OPT≥15.

**Câu 2.** Với bài tối thiểu hóa, một nghiệm khả thi giá trị 2 cung cấp loại cận nào?

**Đáp án:** Cận trên U=2, vì OPT≤2.

**Câu 3.** Absolute certificate gap có công thức gì?

**Đáp án:** U−L, không âm khi cận đúng.

**Câu 4.** Tại sao gap không nhất thiết là sai số thực?

**Đáp án:** Vì OPT chưa biết nằm đâu trong khoảng [L,U]; sai số thực có thể nhỏ hơn U−L.

**Câu 5.** Với maximization, ratio nào là bảo đảm trên instance khi U>0?

**Đáp án:** L/OPT≥L/U.

**Câu 6.** Với minimization, ratio nào là bảo đảm khi L>0?

**Đáp án:** U/OPT≤U/L.

**Câu 7.** Vì sao fractional knapsack tạo upper bound cho 0/1 Knapsack?

**Đáp án:** Vì cho phép lấy một phần vật làm tập khả thi rộng hơn, nên optimum fractional không thể thấp hơn optimum 0/1.

**Câu 8.** Với W=10, ba vật (4,7),(5,8),(6,9), heuristic chọn gì?

**Đáp án:** Vật 0 và 1, trọng lượng 9 và giá trị 15.

**Câu 9.** Fractional upper trong ví dụ ấy bằng bao nhiêu?

**Đáp án:** 33/2=16,5.

**Câu 10.** Vì sao được hạ upper 16,5 xuống 16?

**Đáp án:** Vì optimum 0/1 là số nguyên, nên OPT≤floor(16,5)=16.

**Câu 11.** Nếu có nghiệm giá trị 16 và upper đã chứng minh là 16, kết luận gì?

**Đáp án:** OPT=16; nghiệm được chứng minh tối ưu.

**Câu 12.** Matching kích thước m cung cấp loại cận nào cho Minimum Vertex Cover?

**Đáp án:** Cận dưới m≤OPT, vì mỗi cạnh matching phải được cover bởi một đỉnh riêng.

**Câu 13.** Tại sao lấy hai đầu mút của maximal matching tạo cover?

**Đáp án:** Nếu tồn tại cạnh có cả hai đầu mút không được chọn thì cạnh ấy có thể thêm vào matching, trái tính maximal.

**Câu 14.** Trong đồ thị hình sao, lower và upper ban đầu bằng bao nhiêu?

**Đáp án:** Lower=1 từ matching; upper=2 từ hai đầu mút của cạnh matching.

**Câu 15.** Khi cải thiện cover thành {0}, chứng nhận thế nào?

**Đáp án:** Upper=1, lower vẫn 1, vậy OPT=1.

**Câu 16.** Nếu minimization có L=0 và U>0, tỷ lệ U/L có hợp lệ không?

**Đáp án:** Không; mẫu bằng 0, phải dùng gap cộng hoặc tìm cận dưới dương.

**Câu 17.** Một bound từ relaxation có thể sai khi nào?

**Đáp án:** Khi giải relaxation sai, dùng một nghiệm không tối ưu sai chiều cận, bỏ ràng buộc/đối tượng sai hoặc làm tròn không hợp lệ.

**Câu 18.** Vì sao một heuristic không có định lý vẫn có thể được chứng nhận tốt trên một instance?

**Đáp án:** Vì có thể so nghiệm khả thi của heuristic với một cận toán học hợp lệ độc lập của riêng instance đó.

**Câu 19.** Dùng cận của một nhánh còn mở làm upper bound toàn cục của bài max có đủ không?

**Đáp án:** Không; phải xét tất cả nhánh còn có khả năng chứa optimum và gộp cận hợp lệ.

**Câu 20.** Chọn dừng khi ratio đạt 99% có đồng nghĩa OPTIMAL không?

**Đáp án:** Không; đó chỉ là bảo đảm chất lượng, trừ khi hai cận đã đóng hoặc có một chứng minh tối ưu khác.

**Câu 21.** Tại sao cần dùng BigInteger trong so mật độ và cận phân số?

**Đáp án:** Để tránh overflow/tổn thất chính xác khi chứng minh upper bound, nhất là khi tích v_i w_j vượt long.

**Câu 22.** Một bộ kiểm thử nào kiểm chứng cả nghiệm và cận tốt nhất?

**Đáp án:** Với instance nhỏ, dùng oracle vét cạn tìm OPT, kiểm tra nghiệm khả thi và xác nhận L≤OPT≤U; thêm phản ví dụ chủ động cho bound sai.

**Tóm tắt:** Để đánh giá một nghiệm tối ưu hóa khi chưa biết OPT, hãy tạo **chứng nhận L≤OPT≤U** từ phương án khả thi và cận toán học hợp lệ. Với bài **max**, nghiệm là L, relaxation thường cung cấp U, ratio được chứng nhận **L/U**. Với bài **min**, nghiệm là U, lower bound từ relaxation/matching là L, ratio được chứng nhận **U/L**. **Gap U−L là cận sai số, không nhất thiết là sai số thực**. Với mục tiêu nguyên, floor upper cho max và ceil lower cho min có thể làm chặt chứng nhận. **L=U chứng minh tối ưu**; nếu chưa đóng cận, báo trung thực mức chất lượng, điều kiện của cận và ngân sách còn lại.

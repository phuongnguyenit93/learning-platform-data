# Lựa chọn giữa chính xác, xấp xỉ và kinh nghiệm khi tài nguyên hạn chế

**Chủ đề:** Computer Science Algorithms · Độ khó bài toán

## 1. Bài toán ra quyết định, không chỉ bài toán lập trình

Khi giải một bài tối ưu hóa, cách hỏi “có thuật toán nào tìm được đáp án?” vẫn chưa đủ. Trong môi trường có hạn mức **thời gian, RAM, năng lượng, chi phí hạ tầng hoặc thời hạn phản hồi**, cần chọn giữa ba chiến lược:

1. **Chính xác (exact):** tìm một lời giải tối ưu và có lập luận/chứng nhận rằng không tồn tại lời giải tốt hơn.
2. **Xấp xỉ có bảo đảm (approximation):** tìm một lời giải hợp lệ kèm cận chất lượng đã chứng minh so với tối ưu.
3. **Kinh nghiệm/heuristic:** dùng một quy tắc có khả năng cho nghiệm tốt trong thực tế, nhưng thường **không có bảo đảm chất lượng xấu nhất**.

Ngoài ba nhóm, **thuật toán anytime** có thể trả một nghiệm hợp lệ sớm, rồi cải thiện khi có thêm tài nguyên. Nếu chưa chạy hết, phải ghi rõ trạng thái **PARTIAL**; một nghiệm tốt không tự trở thành nghiệm đã chứng minh tối ưu.

Không nên gộp các thuật ngữ sau:
- **Đúng/khả thi:** lời giải tuân thủ tất cả ràng buộc.
- **Tối ưu:** lời giải khả thi có giá trị mục tiêu tốt nhất có thể.
- **Xấp xỉ:** lời giải khả thi có cận so với OPT được chứng minh theo mô hình bài toán.
- **Heuristic:** có quy tắc tạo lời giải, có thể hiệu quả, nhưng không có cận tổng quát được bảo đảm.
- **Ngẫu nhiên hóa:** dùng lựa chọn ngẫu nhiên; có thể xuất hiện ở cả phương pháp chính xác, xấp xỉ hoặc heuristic.
- **Deadline:** giới hạn thực tế của một lần chạy, không phải tự thân là chứng minh chất lượng.

Ví dụ xuyên suốt là **ba lô 0/1 (0/1 Knapsack)**: chọn các vật có trọng lượng và giá trị không âm sao cho tổng trọng lượng không vượt W, tổng giá trị tối đa. Bài này giúp thấy rõ khi nào nên dùng **DP chính xác O(nW)**, **heuristic tham lam theo mật độ**, **xấp xỉ 1/2 có chứng minh**, hoặc **tìm kiếm chính xác bị giới hạn số nút**.

## 2. Định nghĩa mục tiêu trước khi chọn thuật toán

Với một bài tối đa hóa, gọi F là tập lời giải khả thi, f(x) là giá trị mục tiêu và:

\[
OPT=\max_{x\in F}f(x).
\]

Với một bài tối thiểu hóa:

\[
OPT=\min_{x\in F}f(x).
\]

Phân biệt rõ:

| Loại lời giải | Bài tối đa hóa | Bài tối thiểu hóa |
|---|---|---|
| Chính xác | f(x)=OPT | f(x)=OPT |
| Xấp xỉ nhân \(\alpha\) | f(x)≥\(\alpha OPT\), 0<\(\alpha\)≤1 | f(x)≤\(\rho OPT\), \(\rho\)≥1 |
| Heuristic chưa có cận | f(x) có thể cách OPT rất xa | f(x) có thể lớn hơn OPT rất nhiều |

Trong bài tối đa hóa, một phương án khả thi có giá trị L là **cận dưới** của OPT:

\[
L\le OPT.
\]

Một cận trên U được chứng minh hợp lệ phải thỏa:

\[
OPT\le U.
\]

Vậy:

\[
\boxed{L\le OPT\le U}.
\]

Nếu L=U (so sánh **chính xác**), phương án đạt L được **chứng minh tối ưu**. Nếu 0<L≤U, tỷ lệ L/U là một **cận tỷ lệ chất lượng theo instance**: do OPT≤U, ta có L/OPT≥L/U. Nếu L=0 hoặc U=0, phải xem xét riêng trường hợp tối ưu bằng 0 và không chia cho 0.

**Cực kỳ quan trọng:** cận trên U cần có **chứng minh**, không thể tự gán bằng giá trị tìm được lớn nhất rồi tuyên bố “đã tìm được optimality gap”.

### 2.1. Khả thi trước, tối ưu sau

Một heuristic có thể trả giá trị mục tiêu rất lớn nhưng **vi phạm sức chứa**, lịch trình hoặc điều kiện pháp lý. Đó không phải một nghiệm hợp lệ. Trong bài ba lô, một phương án có tổng trọng lượng >W **không được dùng làm cận dưới L**, dù tổng giá trị cao.

Một quy trình sản xuất an toàn:
1. Xác thực đầu vào và hợp đồng bài toán.
2. Sinh phương án ứng viên.
3. Kiểm tra độc lập **tính khả thi** của ứng viên.
4. Chỉ ghi nhận ứng viên khả thi làm incumbent.
5. Nếu cần, tính hoặc cập nhật cận chất lượng.
6. Gắn nhãn rõ **OPTIMAL / APPROX_GUARANTEED / HEURISTIC / PARTIAL / UNKNOWN**.

Không được gắn nhãn OPTIMAL chỉ vì thuật toán đã hết thời gian hoặc kết quả trông hợp lý.

## 3. Ba chiến lược và lời hứa thật sự của mỗi chiến lược

### 3.1. Exact: câu trả lời tối ưu và chứng nhận

Một thuật toán chính xác có thể dựa trên:
- Quy hoạch động và các bất biến trạng thái.
- Chia để trị có chứng minh.
- Tìm kiếm toàn bộ không gian khả thi.
- Nhánh và cận với **cận hợp lệ**, cắt nhánh an toàn.
- Solver tối ưu hóa nguyên/constraint programming trả trạng thái tối ưu khi hoàn tất chứng minh.

Ví dụ 0/1 Knapsack DP theo sức chứa có thể tìm optimum trong O(nW) thời gian. Nhưng W là **giá trị số**, không phải độ dài bit mã hóa W; đó là một thuật toán **giả đa thức**. Khi W rất lớn, exact DP có thể vượt giới hạn RAM dù n nhỏ.

Exact không đồng nghĩa với “luôn nhanh”: nhiều bài NP-hard có cận trường hợp xấu nhất hàm mũ đối với các thuật toán exact thông dụng.

### 3.2. Approximation: đổi độ chính xác lấy tài nguyên, có định lý đi kèm

Một thuật toán \(\alpha\)-approximation cho bài tối đa hóa phải:
1. Trả nghiệm khả thi trên mọi đầu vào trong miền đã công bố.
2. Bảo đảm giá trị ít nhất \(\alpha OPT\).
3. Có phân tích thời gian, bộ nhớ và giả thiết.

Chất lượng cam kết \(\alpha=1/2\) **không có nghĩa** mọi instance đều chỉ đạt 50% tối ưu. Có instance giải pháp xấp xỉ đạt đúng OPT; đảm bảo 1/2 chỉ là **cận tệ nhất đã chứng minh**.

Một **FPTAS** mạnh hơn: cho tham số sai số \(\epsilon\in(0,1)\), tìm nghiệm ít nhất \((1-\epsilon)OPT\) cho tối đa hóa, với thời gian đa thức theo **kích thước biểu diễn đầu vào và 1/\(\epsilon\)**. Không phải bài NP-hard nào cũng có FPTAS.

### 3.3. Heuristic: hành vi thực nghiệm, chưa có cận tổng quát

Heuristic có thể rất hữu ích:
- Tham lam theo tỷ lệ lợi ích/chi phí.
- Local search đổi một vài quyết định.
- Random restart hoặc simulated annealing.
- Tìm kiếm chùm (beam search) hoặc cách xếp hạng miền thử.

Nhưng nếu chưa chứng minh cận, đừng gọi nó là “thuật toán xấp xỉ 90%” chỉ vì trung bình bộ benchmark đạt 90% phương án tốt nhất đã biết. Một tập thử hữu hạn không cung cấp cận xấu nhất cho mọi đầu vào.

Một heuristic **vẫn có thể kết hợp với cận trên** để báo khoảng nghiệm cụ thể: ví dụ trả một phương án hợp lệ có L=160, đồng thời chứng minh OPT≤240. Khi đó có chứng nhận **L/OPT≥2/3 trên riêng instance ấy**, dù thuật toán sinh ứng viên ban đầu chỉ là heuristic.

## 4. Các câu hỏi cần chốt trước khi chọn

1. **Bắt buộc tối ưu hay chấp nhận kém tối ưu?** Nếu sai khác nhỏ là không thể chấp nhận, cần exact hoặc một quá trình chỉ xuất kết quả sau khi chứng minh.
2. **Bắt buộc có đáp án đúng hạn hay có thể trả UNKNOWN?** Một timeout trả phương án khả thi khác với một timeout không trả gì.
3. **Giới hạn tài nguyên nào cứng?** RAM, CPU, thời gian phản hồi, số lượt API, năng lượng hay chi phí?
4. **Đầu vào có cấu trúc đặc biệt?** W nhỏ, số vật n nhỏ, giá trị nguyên bị chặn, đồ thị thưa, dữ liệu có tính lồi?
5. **Yêu cầu bảo đảm nào?** Tối ưu, \((1-\epsilon)\)-approximation, bound theo từng instance, hoặc chỉ một nghiệm hợp lệ?
6. **Chi phí đánh giá một nghiệm là bao nhiêu?** Một heuristic có ít bước nhưng mỗi bước gọi solver/ML model đắt có thể chậm hơn DP.
7. **Phân phối đầu vào có thay đổi không?** Heuristic tốt trong benchmark cũ có thể suy giảm khi dữ liệu thật đổi dạng.
8. **Có đối thủ tạo input không?** Một thuật toán dễ bị kích hoạt worst-case có thể không phù hợp với đầu vào không tin cậy.

Các câu trả lời này quyết định **hợp đồng sản phẩm**, không chỉ công thức Big-O.

## 5. Ví dụ 0/1 Knapsack và một bẫy tham lam

Có n vật, vật i có trọng lượng nguyên dương w[i] và giá trị nguyên không âm v[i]. Mỗi vật có thể lấy **tối đa một lần**, tổng trọng lượng không vượt W.

\[
\max\sum_i v_i x_i
\quad\text{với}\quad
\sum_i w_i x_i\le W,\;
x_i\in\{0,1\}.
\]

Ví dụ kinh điển:

~~~text
W = 50
index:   0    1    2
weight: 10   20   30
value:  60  100  120
density:6    5    4
~~~

**Tham lam theo mật độ** v/w chọn vật 0 trước, rồi vật 1: tổng trọng lượng 30, giá trị **160**. Vật 2 còn 30 đơn vị nên không thêm được vì sức chứa chỉ còn 20.

**Tối ưu** là chọn vật 1 và 2: trọng lượng 20+30=50, giá trị **220**.

Vậy:
- Heuristic tham lam: **160**.
- Exact DP: **220**.
- Cận trên từ nới lỏng ba lô phân số: **240**, vì lấy vật 0,1 và 20/30 vật 2 được 60+100+80=240.
- Khi chưa biết nghiệm 220, ta vẫn có chứng nhận **160≤OPT≤240**.

### 5.1. Tham lam thuần túy có thể rất tệ

Cho W=1000 và hai vật:
- Vật 0: w=1, v=2, mật độ 2.
- Vật 1: w=1000, v=1000, mật độ 1.

Tham lam theo mật độ lấy vật 0 trước; phần trống còn 999 không đủ cho vật 1. Nó trả **2**, trong khi optimum là **1000**.

Tỷ lệ heuristic/OPT là 2/1000=0,002, dù không có lỗi mã. Khi W tăng, có thể làm tỷ lệ ấy tiến sát 0. Đây là **phản ví dụ toán học** bác bỏ việc tự gán cận chất lượng không có chứng minh cho tham lam thuần túy.

Sửa nhẹ bằng **chọn tốt hơn giữa một prefix tham lam và vật đơn lẻ tốt nhất** tạo được thuật toán xấp xỉ có bảo đảm **1/2** trong hợp đồng trọng lượng dương, giá trị không âm.

## 6. Exact DP: đúng tuyệt đối nhưng phụ thuộc W

Đặt:

\[
dp[i][c]=\text{giá trị tối ưu dùng i vật đầu tiên, tổng trọng lượng}\le c.
\]

Khởi tạo dp[0][c]=0. Với vật i−1 có trọng lượng w và giá trị v:

\[
dp[i][c]=\max(
dp[i-1][c],
dp[i-1][c-w]+v
)
\]

nếu c≥w; còn c<w chỉ giữ dp[i−1][c].

**Chứng minh:** mọi lời giải trên i vật hoặc không chứa vật i, hoặc có chứa vật i. Hai trường hợp là đầy đủ và loại trừ nhau. Trạng thái không lấy dùng i−1 vật và c; trạng thái lấy dùng i−1 vật với sức chứa c−w, cộng v. Lấy max cho đúng optimum sau i vật.

Độ phức tạp:
- Thời gian **O(nW)**.
- Bộ nhớ **O(nW)** nếu lưu cả bảng và thông tin truy vết để trả danh sách vật.
- Có thể nén bộ nhớ **O(W)** nếu chỉ cần giá trị tối ưu, duyệt c **giảm dần** để không dùng vật lặp.

### 6.1. Vì sao đây là giả đa thức?

Nếu W được biểu diễn nhị phân bằng b bit thì W có thể xấp xỉ \(2^b\). Do đó O(nW) có thể là O(n2ᵇ) theo độ dài biểu diễn b.

W=1.000.000 chỉ cần 20 bit, nhưng bảng DP theo dung lượng vẫn có khoảng một triệu cột. Việc xuất hiện phép nhân nW không biến thuật toán thành đa thức theo **số bit của đầu vào**.

### 6.2. Truy vết phương án, không chỉ giá trị

Một lời giải tối ưu thực tế phải trả những **vật được chọn**, không phải chỉ số điểm tối ưu. Code Java dùng bảng hai chiều và mảng take[i][c] để truy vết. Nếu tại trạng thái (i,c) lấy vật i−1 thì:
- Ghi index i−1.
- Giảm c đi w[i−1].
- Tiếp tục với i−1.

Phương án sau truy vết phải có tổng trọng lượng ≤W, và tổng giá trị đúng dp[n][W]. Kiểm tra tính khả thi là một bước độc lập.

### 6.3. Giới hạn bộ nhớ demo

Để không vô tình cấp phát hàng trăm triệu ô, Java demo chỉ cho:
- W≤100.000.
- (n+1)(W+1)≤2.000.000 ô.

Đây là **hạn mức minh họa**, không phải ràng buộc toán học. Nếu vượt hạn mức, hàm exact DP từ chối trước khi cấp phát thay vì làm ứng dụng mất RAM. Với W rất lớn và n nhỏ, có thể chọn thuật toán exact kiểu meet-in-the-middle hoặc tìm kiếm, không nhất thiết dùng DP theo W.

## 7. Thuật toán xấp xỉ 1/2 bằng prefix và vật tốt nhất

Đối với 0/1 Knapsack có w[i]>0, v[i]≥0 và W≥0:

1. **Bỏ các vật có w[i]>W** vì chúng không thể tham gia bất kỳ nghiệm khả thi nào.
2. Sắp vật còn lại theo **mật độ v[i]/w[i] giảm dần**. Khi so hai mật độ, dùng nhân chéo bằng số nguyên lớn, tránh double và overflow.
3. Lấy **prefix liên tiếp** trong thứ tự này cho tới khi gặp vật đầu tiên không thể nhét vừa phần trống. **Dừng tại đó** cho riêng phương án prefix.
4. Đồng thời tìm **vật đơn lẻ có giá trị lớn nhất** trong số vật hợp lệ.
5. Trả phương án có giá trị lớn hơn giữa **prefix** và **vật tốt nhất**.

Khác biệt quan trọng: heuristic tham lam thuần túy có thể **bỏ qua vật không vừa rồi xét vật tiếp theo**, còn thuật toán chứng minh 1/2 dùng **prefix trước vật đầu tiên không vừa**. Đừng thay đổi quy tắc rồi bê nguyên chứng minh nếu chưa phân tích lại.

### 7.1. Chứng minh hệ số 1/2

Xét bài toán **ba lô phân số (fractional knapsack)**: cho phép lấy một phần vật. Sắp theo mật độ giảm dần rồi điền đầy từ trái sang phải là tối ưu cho bản phân số.

Nếu mọi vật hợp lệ đều vừa, prefix lấy hết nên đã tối ưu 0/1.

Nếu có vật đầu tiên k không vừa sau prefix P, lời giải phân số tối ưu gồm:
- Toàn bộ các vật trong prefix, tổng giá trị P.
- Một phần của vật k, với giá trị không vượt **v[k]**.

Gọi F là optimum phân số, ta có:

\[
OPT_{\rm 0/1}\le F\le P+v[k].
\]

Do k là vật hợp lệ riêng lẻ (đã lọc w[k]≤W), giá trị vật tốt nhất S thỏa S≥v[k]. Thuật toán trả:

\[
ALG=\max(P,S).
\]

Vậy:

\[
2ALG\ge P+S\ge P+v[k]\ge OPT_{\rm 0/1}.
\]

Suy ra:

\[
\boxed{ALG\ge \frac12 OPT}.
\]

Đây là bảo đảm **cho mọi đầu vào thỏa giả thiết**, không dựa vào dữ liệu huấn luyện, random seed hay benchmark. Cần xử lý trường hợp OPT=0 riêng nếu muốn phát biểu tỷ lệ ALG/OPT.

### 7.2. Trường hợp phản ví dụ được cứu

Với W=1000, vật nhỏ (1,2) và vật lớn (1000,1000):
- Prefix lấy vật nhỏ, P=2.
- Vật đơn lẻ tốt nhất S=1000.
- Thuật toán xấp xỉ chọn vật lớn, trả **1000**, cũng là optimum.

Trong ví dụ W=50:
- Prefix có P=160.
- Vật tốt nhất S=120.
- Thuật toán trả 160, chưa tối ưu 220 nhưng được bảo đảm ít nhất 110.

**Không nhầm 1/2-guarantee với cận thực tế của instance:** sau khi biết một cận trên U=240, có thể chứng minh 160/OPT≥160/240=2/3 trên riêng instance W=50.

### 7.3. Độ phức tạp

- Lọc vật khả thi: O(n).
- Sắp theo mật độ: O(n log n) phép so mật độ.
- Quét prefix và tìm singleton: O(n).
- Bộ nhớ phụ: O(n) chỉ số được sắp.

Với giá trị long, phép so chéo v_i w_j dùng BigInteger để **không overflow**. Nếu dùng double tỷ lệ v/w, các giá trị gần nhau có thể bị sắp sai do làm tròn, khiến giả thiết của chứng minh không còn khớp thực thi.

## 8. Chứng nhận cận trên từ ba lô phân số

Nới lỏng điều kiện x_i∈{0,1} thành:

\[
0\le x_i\le1.
\]

Không gian nghiệm lớn hơn nên:

\[
OPT_{\rm integer}\le OPT_{\rm fractional}=U.
\]

Với bài ba lô phân số có trọng lượng dương, sắp vật theo v/w giảm dần và lấy lần lượt:
- Nếu vật vừa, lấy nguyên.
- Với vật đầu tiên không vừa, lấy tỷ lệ \(\text{remaining}/w\) rồi dừng.

Trong ví dụ W=50:
- Lấy (10,60), còn 40.
- Lấy (20,100), còn 20.
- Lấy 20/30 vật (30,120), thêm giá trị 80.
- F=U=240.

Khi thuật toán tìm một nghiệm 160, bản báo cáo có thể ghi:

\[
\boxed{160\le OPT\le240}.
\]

Và, vì 160/240=2/3:

\[
ALG/OPT\ge2/3.
\]

Nếu sau đó tìm nghiệm 220 nhưng chưa chứng minh tối ưu, vẫn có 220≤OPT≤240; cận chất lượng theo instance trở thành **11/12**. Nếu tìm kiếm exact hoàn tất, có thể nâng chứng nhận lên **220=OPT**.

### 8.1. Tại sao cận phải tính chính xác?

Nếu F=160+120×20/30, biểu diễn bằng double có thể làm sai một bit khi so U và L. Để cấp chứng nhận nghiêm ngặt:
- Dùng số hữu tỉ **BigInteger tử/mẫu**.
- Chuẩn hóa mẫu dương, rút gọn gcd.
- Cộng phần nguyên và phần phân số bằng số học chính xác.
- So cận bằng nhân chéo, không round xuống làm mất tính “upper”.

Mã Java chứa record Fraction và biểu diễn chính xác. Trong ví dụ, Fraction(7200,30) rút thành **240**, còn W=1000 trong phản ví dụ cho cận trên **1001**.

### 8.2. Tại sao lọc vật quá nặng không làm sai cận?

Vật có w[i]>W **không khả thi ngay cả khi đứng riêng**. Lọc chúng không thay đổi optimum nguyên. Ta có thể xây bài toán phân số **chỉ trên những vật còn khả thi nguyên**, vẫn là một nới lỏng của bài toán nguyên sau lọc. Kết quả fractional này là cận trên hợp lệ và thường chặt hơn so với để các vật quá nặng tham gia phân số.

## 9. Anytime: có nghiệm sớm, cải thiện nếu còn ngân sách

Một tiến trình có deadline không nhất thiết phải hoàn thành search để tạo giá trị. Có thể bắt đầu bằng **incumbent**: phương án khả thi đã chứng minh được, ví dụ 1/2-approx ở trên.

Sau đó duyệt DFS các quyết định lấy/không lấy vật:
- Mỗi nút đại diện cho một tiền tố quyết định.
- Nhánh có tổng trọng lượng >W bị loại ngay, vì trọng lượng dương nên không thể trở nên khả thi bằng cách thêm vật.
- Ở lá khả thi, nếu tìm được giá trị tốt hơn incumbent thì cập nhật.
- Nếu duyệt hết cây, đã kiểm tra toàn bộ tập con khả thi: đáp án **OPTIMAL**.
- Nếu dừng trước khi duyệt hết, báo **PARTIAL**, kèm nghiệm khả thi tốt nhất đã có và cận trên toàn cục đã chứng minh.

Để có demo **tái lập**, chương trình giới hạn **số nút DFS** thay vì dùng thời gian đồng hồ. Trong hệ thống thật, giới hạn số nút chỉ là một proxy: một nút có thể tốn thời gian khác nhau; hard deadline cần đo thời gian và xử lý huỷ/timeout cẩn thận.

### 9.1. Vì sao PARTIAL không được gắn nhãn OPTIMAL?

Một DFS đã thấy nghiệm 160 sau năm nút **chưa xét hết** những tập con còn lại. Trên ví dụ W=50, tập {vật 1, vật 2} có giá trị 220 nằm ở nhánh khác.

Vì vậy sau khi tiêu hết budget, phải trả:

~~~text
Budget 5: best=160, status=PARTIAL, nodes=5, upper=240
~~~

Chỉ khi đã duyệt hết (kể cả các nhánh có thể loại an toàn) mới đổi trạng thái:

~~~text
Budget 50: best=220, status=OPTIMAL, nodes=15, upper=220
~~~

Ở đây budget=50 là **số nút tối đa cho phép**, nhưng cây thực tế của n=3 vật có 15 nút; chương trình dừng sau 15 nút và xác nhận complete.

### 9.2. Cận dưới luôn là phương án khả thi

Incumbent khởi tạo bằng 1/2-approx có một tập chỉ số vật cụ thể. Khi DFS thấy nghiệm mới, nó chỉ thay thế incumbent sau khi đã kiểm tra tổng trọng lượng≤W.

Nhờ đó, kể cả khi dừng sớm:
- Có thể trả danh sách vật **hợp lệ**.
- Giá trị L không giảm theo thời gian chạy.
- Cận trên U từ fractional relaxation vẫn hợp lệ.
- Hệ số 1/2 của incumbent đầu cũng vẫn được bảo toàn hoặc cải thiện.

Nếu không có vật khả thi, nghiệm rỗng giá trị 0 luôn có sẵn với bài có giá trị không âm và cho phép không chọn vật.

### 9.3. Có phải branch-and-bound?

Bản demo là **budgeted exhaustive DFS**, có loại nhánh vượt sức chứa và incumbent, nhưng **không có cận nút để cắt mọi nhánh không còn khả năng cải thiện**. Nó không nên được quảng cáo là một solver branch-and-bound tối ưu hiệu năng.

Một branch-and-bound đầy đủ có thể tính cận trên riêng cho từng nút rồi cắt nếu \(UB(node)\le L\). Việc cắt chỉ đúng khi UB(node) thực sự là **cận trên hợp lệ** của toàn bộ nghiệm mở rộng từ nút ấy. Cận sai có thể làm bỏ qua nghiệm tối ưu mà không báo lỗi.

Mã dùng một cận fractional **toàn cục** khi chưa complete. Nó có thể lỏng, nhưng vẫn có giá trị chứng nhận; khi complete, cận trên được thay bằng chính giá trị optimum đã chứng minh.

## 10. Xấp xỉ tinh chỉnh bằng tham số epsilon và FPTAS

Giải pháp 1/2-guarantee nhanh và đơn giản nhưng có thể chưa đạt chất lượng cần thiết. Đối với **0/1 Knapsack tối đa hóa** với trọng lượng dương và giá trị không âm, tồn tại **FPTAS** cho phép chọn epsilon.

Bảo đảm:

\[
ALG\ge(1-\epsilon)OPT
\]

với thời gian đa thức theo **kích thước đầu vào và 1/\(\epsilon\)**.

Một ý tưởng kinh điển dùng **co giãn giá trị**:
1. Loại vật quá nặng không thể chọn riêng.
2. Nếu không có vật có giá trị dương khả thi, trả nghiệm rỗng giá trị 0.
3. Gọi m là số vật còn lại và \(V_{\max}\) là giá trị lớn nhất của một vật khả thi.
4. Chọn \(K=\epsilon V_{\max}/m\) (với m>0).
5. Thay giá trị v_i bằng \(v'_i=\lfloor v_i/K\rfloor\).
6. DP theo **giá trị đã co giãn**, lưu trọng lượng nhỏ nhất để đạt mỗi mức giá trị.
7. Chọn mức giá trị co giãn cao nhất có trọng lượng≤W, truy vết vật.

Vì mỗi vật mất ít hơn K khi làm tròn, tổng mất <mK=epsilon Vmax≤epsilon OPT. Vì thế:

\[
ALG\ge OPT-\epsilon OPT=(1-\epsilon)OPT.
\]

Hơn nữa:

\[
\sum_i v'_i\le mV_{\max}/K=m^2/\epsilon.
\]

Một DP đơn giản theo giá trị co giãn có thể đạt cỡ O(m³/\(\epsilon\)) phép cập nhật, cùng chi phí mã hóa/so số nguyên phù hợp. Đây là giải thích ý tưởng FPTAS, **không phải mã FPTAS đã triển khai trong demo**.

### 10.1. PTAS khác FPTAS

- **PTAS:** với epsilon cố định, thời gian đa thức theo kích thước đầu vào; bậc đa thức có thể phụ thuộc mạnh vào 1/epsilon.
- **FPTAS:** thời gian đa thức **đồng thời** theo kích thước đầu vào và 1/epsilon.

Không được gọi một heuristic “gần 100% trong benchmark” là FPTAS nếu chưa có chứng minh cả tỷ lệ xấp xỉ và cận thời gian.

### 10.2. Chọn epsilon theo tài nguyên

Epsilon càng nhỏ thì bảo đảm chất lượng càng sát OPT, nhưng trạng thái/thời gian của FPTAS thường lớn hơn.

Ví dụ:
- epsilon=0,2 bảo đảm ≥0,8 OPT.
- epsilon=0,1 bảo đảm ≥0,9 OPT.
- epsilon=0,01 bảo đảm ≥0,99 OPT.

Nếu ngân sách RAM không đủ cho epsilon quá nhỏ, cần chọn epsilon phù hợp, dùng một thuật toán khác hoặc ghi rõ không đáp ứng được hợp đồng. Đừng tự hạ độ chính xác mà không báo cho người dùng.

## 11. Không phải bài toán nào cũng có tỷ lệ xấp xỉ giống nhau

Chất lượng 1/2 ở mục 7 là **định lý riêng cho 0/1 Knapsack với cách xây thuật toán và giả thiết đã nêu**. Không thể bê tỷ lệ đó sang mọi bài tối ưu hóa NP-hard.

Ví dụ:
- **TSP có bất đẳng thức tam giác:** có thể khai thác tính chất metric để xây các thuật toán xấp xỉ có bảo đảm; với TSP tổng quát không thỏa tam giác, không thể khẳng định cùng cận.
- **Set Cover:** một greedy theo số phần tử mới được bao phủ trên một đơn vị chi phí có thể phân tích bằng hệ số log, không phải mặc nhiên là 1/2.
- **Maximum Coverage:** greedy chọn tập mang lại lợi ích biên lớn nhất với số lượt k cố định có bảo đảm gần 1−1/e dưới các giả thiết chuẩn.
- **Tối ưu hóa có ràng buộc đặc biệt:** một cận có thể phụ thuộc tính lồi, đơn điệu, submodularity, metric hoặc điều kiện xếp lịch.

Khi thay bài toán, phải bắt đầu từ **định nghĩa nghiệm khả thi, mục tiêu và giả thiết**, rồi mới lựa chọn thuật toán. Tính chất “heuristic thường tốt” trên một miền khác không tạo ra cận lý thuyết mới.

## 12. Lập kế hoạch tài nguyên đúng cách

### 12.1. RAM trước khi CPU

Một DP có O(nW) thời gian và bộ nhớ đôi khi dừng do không thể cấp phát mảng, không phải do thiếu CPU. Ước lượng:
- Số trạng thái thật sự.
- Kích thước mỗi trạng thái.
- Bảng truy vết, mảng phụ và overhead cấu trúc Java.
- Peak memory khi chạy song song nhiều yêu cầu.
- Bộ nhớ JVM và giới hạn container.

Nếu chỉ cần **giá trị tối ưu**, DP một chiều giảm bộ nhớ xuống O(W). Nếu phải trả **danh sách vật**, cần cơ chế truy vết; bản Java demo giữ bảng O(nW) để minh bạch và giới hạn số ô.

### 12.2. Deadline cứng và đo lường

Không nên dùng mỗi *average runtime*. Phải quan tâm p95/p99/tail latency, warm-up JIT, GC, tải đồng thời và trường hợp đầu vào xấu nhất.

- Với deadline cứng, nên có thuật toán trả nghiệm khả thi **trước**, sau đó cải thiện.
- Đối với tiến trình exact, cần phân biệt **đã chứng minh OPTIMAL** và **đã dừng vì timeout**.
- Nếu một bước không thể ngắt ngay, giới hạn số nút chưa chắc giới hạn thời gian thật.
- Nếu cần kiểm toán, lưu cả lower/upper bounds, thời điểm, tham số epsilon/budget và trạng thái chứng minh.

### 12.3. Độ lớn số và tràn số

Nếu giá trị đầu vào là long:
- Tổng nhiều giá trị có thể vượt long.
- Tích chéo v_i w_j dùng để so mật độ có thể vượt long.
- Upper bound fractional có thể là số hữu tỉ không nguyên.
- Không được tính bằng double rồi làm tròn xuống cận trên; làm thế có thể làm **U<OPT** và gây chứng nhận sai.

Mã dùng BigInteger để so mật độ và tính cận trên phân số; nó cũng xác nhận tổng giá trị toàn bộ vật **vừa long** cho phần mô tả nghiệm. Nếu không vừa, ném ArithmeticException rõ ràng; một hệ thống lớn có thể thay luôn trường giá trị nghiệm bằng BigInteger.

### 12.4. Mốc kiểm tra chất lượng

Một baseline hợp lý:
- **Feasibility:** phương án chọn không lặp index, tổng trọng lượng≤W, tổng giá trị đúng số liệu.
- **Exact oracle (bài nhỏ):** kết quả DP và DFS vét cạn bằng nhau.
- **Approximation guarantee:** \(2ALG\ge OPT\) với thuật toán 1/2.
- **Upper-bound soundness:** \(OPT\le U\), kiểm thử bằng vét cạn trên n nhỏ.
- **Anytime safety:** best không giảm khi ngân sách tăng, PARTIAL không bị gọi OPTIMAL, OPTIMAL chỉ khi cây đã duyệt xong.
- **Stress/resource:** kiểm tra giới hạn RAM và số nút, số nguyên cực trị, trường hợp tất cả vật quá nặng.

## 13. Bảng lựa chọn thực tế

| Tình huống | Hướng ưu tiên | Cần ghi rõ |
|---|---|---|
| W nhỏ, n vừa, bắt buộc tối ưu | Exact DP theo W | O(nW), RAM và trạng thái |
| n rất nhỏ, W khổng lồ | Vét cạn/meet-in-the-middle exact | Hàm mũ theo n, giới hạn n |
| Cần phản hồi rất nhanh và có bảo đảm | Thuật toán xấp xỉ chứng minh được | Tỷ lệ, giả thiết, độ phức tạp |
| Chấp nhận 1−epsilon OPT và có đủ RAM | FPTAS khi bài toán hỗ trợ | epsilon, bảo đảm và tài nguyên |
| Không có thuật toán xấp xỉ tốt phù hợp | Heuristic + feasibility checker | Không quảng cáo cận chưa chứng minh |
| Deadline cứng, có thể tiếp tục cải thiện | Anytime: nghiệm sớm + bounded search | PARTIAL/OPTIMAL, L/U, deadline |
| Cần kiểm toán lời giải | Cận trên hợp lệ và certificate | Cách tính bound, không làm tròn sai |
| Heuristic hiệu quả trên dữ liệu thực | Benchmark nhiều lớp đầu vào | p95/p99, worst-case, regression |
| Bài có đầu vào đối kháng | Ưu tiên bảo đảm hoặc kiểm soát xấu nhất | Không dựa duy nhất trung bình |
| Tài nguyên thiếu và không thể thỏa chất lượng | Trả giới hạn/UNKNOWN có cấu trúc | Không tự khẳng định kết quả tối ưu |

## 14. Chương trình Java 17 tự chạy

Lưu tệp **ResourceTradeoffDemo.java**. Code minh họa:
- **densityGreedy:** heuristic tham lam theo tỷ lệ, có thể rất tệ.
- **halfApprox:** phương án xấp xỉ có bảo đảm **ít nhất 1/2 OPT**, trả danh sách vật.
- **fractionalUpper:** cận trên chính xác bằng phân số BigInteger.
- **exactDp:** DP theo sức chứa, trả nghiệm tối ưu và danh sách vật, chỉ trong budget RAM demo.
- **budgetedSearch:** DFS không gian tập con, có incumbent khả thi từ halfApprox, giới hạn **số nút**, trả PARTIAL hoặc OPTIMAL với cận trên hợp lệ.
- **validPlan:** kiểm tra độc lập index, tổng trọng lượng và tổng giá trị.

Hợp đồng:
- Mọi trọng lượng là số nguyên **dương**.
- Mọi giá trị là long **không âm**.
- Sức chứa không âm.
- Tổng tất cả giá trị phải vừa long (hệ thống lớn có thể mở rộng sang BigInteger).
- Mảng vật phải hợp lệ và không chứa null.
- DP có giới hạn số ô; exhaustive demo có giới hạn n≤20.

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;

public final class ResourceTradeoffDemo {
    private ResourceTradeoffDemo() {
    }

    private static final int MAX_CAPACITY = 100_000;
    private static final long MAX_DP_CELLS = 2_000_000;
    private static final int MAX_SEARCH_ITEMS = 20;

    public record Item(int weight, long value) {
    }

    public record Plan(
            long value, long weight, List<Integer> indices) {
        public Plan {
            if (value < 0 || weight < 0) {
                throw new IllegalArgumentException(
                        "Negative plan value or weight");
            }
            indices = List.copyOf(indices);
        }
    }

    public record Fraction(
            BigInteger numerator, BigInteger denominator) {
        public Fraction {
            Objects.requireNonNull(numerator, "numerator");
            Objects.requireNonNull(denominator, "denominator");
            if (denominator.signum() == 0) {
                throw new IllegalArgumentException(
                        "Zero denominator");
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

        @Override
        public String toString() {
            return denominator.equals(BigInteger.ONE)
                    ? numerator.toString()
                    : numerator + "/" + denominator;
        }
    }

    public record SearchResult(
            Plan best, boolean optimal,
            long visitedNodes, Fraction upperBound) {
    }

    private static void validate(Item[] items, int capacity) {
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
                        "Weight must be positive; value nonnegative");
            }
            // Demo chỉ hỗ trợ tổng giá trị vừa trong long.
            totalValue = Math.addExact(totalValue, item.value());
        }
    }

    // Thứ tự mật độ giảm dần, so tỉ lệ bằng phép nhân chéo.
    private static List<Integer> densityOrder(
            Item[] items, int capacity) {
        List<Integer> order = new ArrayList<>();
        for (int i = 0; i < items.length; i++) {
            // Vật quá nặng không khả thi dù đứng một mình.
            if (items[i].weight() <= capacity) {
                order.add(i);
            }
        }

        order.sort((i, j) -> {
            Item x = items[i];
            Item y = items[j];
            BigInteger left = BigInteger.valueOf(x.value())
                    .multiply(BigInteger.valueOf(y.weight()));
            BigInteger right = BigInteger.valueOf(y.value())
                    .multiply(BigInteger.valueOf(x.weight()));
            int cmp = right.compareTo(left);
            return cmp != 0 ? cmp : Integer.compare(i, j);
        });
        return order;
    }

    private static Plan emptyPlan() {
        return new Plan(0, 0, List.of());
    }

    // HEURISTIC: bỏ qua vật không vừa rồi xét vật tiếp theo.
    // Không có tỷ lệ bảo đảm tổng quát cho quy tắc này.
    public static Plan densityGreedy(
            Item[] items, int capacity) {
        validate(items, capacity);
        long value = 0;
        long weight = 0;
        List<Integer> selected = new ArrayList<>();

        for (int index : densityOrder(items, capacity)) {
            Item item = items[index];
            if (weight + item.weight() <= capacity) {
                weight += item.weight();
                value = Math.addExact(value, item.value());
                selected.add(index);
            }
        }
        Collections.sort(selected);
        return new Plan(value, weight, selected);
    }

    // PROVED APPROXIMATION: max(prefix, best singleton).
    // Trả >= OPT/2 với weight>0 và value>=0.
    public static Plan halfApprox(
            Item[] items, int capacity) {
        validate(items, capacity);

        int bestSingle = -1;
        for (int i = 0; i < items.length; i++) {
            if (items[i].weight() <= capacity
                    && (bestSingle < 0
                    || items[i].value()
                    > items[bestSingle].value())) {
                bestSingle = i;
            }
        }

        long prefixValue = 0;
        long prefixWeight = 0;
        List<Integer> selected = new ArrayList<>();

        for (int index : densityOrder(items, capacity)) {
            Item item = items[index];

            // DỪNG ở vật đầu tiên không vừa prefix.
            if (prefixWeight + item.weight() > capacity) {
                break;
            }

            prefixWeight += item.weight();
            prefixValue = Math.addExact(
                    prefixValue, item.value());
            selected.add(index);
        }

        if (bestSingle >= 0
                && items[bestSingle].value() > prefixValue) {
            return new Plan(
                    items[bestSingle].value(),
                    items[bestSingle].weight(),
                    List.of(bestSingle));
        }

        Collections.sort(selected);
        return new Plan(prefixValue, prefixWeight, selected);
    }

    // Chứng nhận upper bound: optimum của fractional relaxation.
    // Không làm tròn xuống và không dùng double.
    public static Fraction fractionalUpper(
            Item[] items, int capacity) {
        validate(items, capacity);
        BigInteger whole = BigInteger.ZERO;
        int remaining = capacity;

        for (int index : densityOrder(items, capacity)) {
            Item item = items[index];
            if (item.weight() <= remaining) {
                whole = whole.add(
                        BigInteger.valueOf(item.value()));
                remaining -= item.weight();
            } else {
                // F = whole + value * remaining / weight.
                BigInteger numerator = whole.multiply(
                        BigInteger.valueOf(item.weight()))
                        .add(BigInteger.valueOf(item.value())
                                .multiply(BigInteger.valueOf(
                                        remaining)));
                return new Fraction(
                        numerator,
                        BigInteger.valueOf(item.weight()));
            }
        }

        return new Fraction(whole, BigInteger.ONE);
    }

    // EXACT DP: O(nW) time AND memory because we reconstruct items.
    public static Plan exactDp(
            Item[] items, int capacity) {
        validate(items, capacity);
        int n = items.length;

        long cells = ((long) n + 1) * ((long) capacity + 1);
        if (capacity > MAX_CAPACITY || cells > MAX_DP_CELLS) {
            throw new IllegalArgumentException(
                    "DP budget exceeded in demo");
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
        long weight = 0;

        for (int i = n; i >= 1; i--) {
            if (take[i][remaining]) {
                indices.add(i - 1);
                int w = items[i - 1].weight();
                weight += w;
                remaining -= w;
            }
        }
        Collections.reverse(indices);
        return new Plan(dp[n][capacity], weight, indices);
    }

    // Verify feasibility AND exact value of the recorded indices.
    public static boolean validPlan(
            Item[] items, int capacity, Plan plan) {
        validate(items, capacity);
        Objects.requireNonNull(plan, "plan");

        long weight = 0;
        long value = 0;
        HashSet<Integer> seen = new HashSet<>();

        for (Integer index : plan.indices()) {
            if (index == null
                    || index < 0 || index >= items.length
                    || !seen.add(index)) {
                return false;
            }
            Item item = items[index];
            weight += item.weight();
            value = Math.addExact(value, item.value());
        }

        return weight <= capacity
                && weight == plan.weight()
                && value == plan.value();
    }

    private static final class SearchState {
        Plan best;
        long visited;

        SearchState(Plan initial) {
            best = initial;
        }
    }

    // DFS với ngân sách node; true iff entire subtree explored.
    private static boolean explore(
            Item[] items, int index,
            long usedWeight, long value,
            int capacity, long nodeBudget,
            boolean[] chosen, SearchState state) {
        if (state.visited >= nodeBudget) {
            return false;
        }
        state.visited++;

        if (usedWeight > capacity) {
            // Trọng lượng dương nên thêm vật không cứu được.
            return true;
        }

        if (index == items.length) {
            if (value > state.best.value()) {
                List<Integer> ids = new ArrayList<>();
                for (int i = 0; i < chosen.length; i++) {
                    if (chosen[i]) {
                        ids.add(i);
                    }
                }
                state.best = new Plan(value, usedWeight, ids);
            }
            return true;
        }

        chosen[index] = false;
        boolean left = explore(
                items, index + 1, usedWeight, value,
                capacity, nodeBudget, chosen, state);

        chosen[index] = true;
        Item item = items[index];
        boolean right = explore(
                items, index + 1,
                Math.addExact(usedWeight, item.weight()),
                Math.addExact(value, item.value()),
                capacity, nodeBudget, chosen, state);

        chosen[index] = false;
        return left && right;
    }

    public static SearchResult budgetedSearch(
            Item[] items, int capacity, long nodeBudget) {
        validate(items, capacity);

        if (nodeBudget <= 0) {
            throw new IllegalArgumentException(
                    "Node budget must be positive");
        }
        if (items.length > MAX_SEARCH_ITEMS) {
            throw new IllegalArgumentException(
                    "Too many items for exhaustive demo");
        }

        SearchState state = new SearchState(
                halfApprox(items, capacity));
        boolean[] chosen = new boolean[items.length];
        boolean complete = explore(
                items, 0, 0, 0,
                capacity, nodeBudget, chosen, state);

        Fraction upper = complete
                ? Fraction.whole(state.best.value())
                : fractionalUpper(items, capacity);

        return new SearchResult(
                state.best, complete, state.visited, upper);
    }

    private static void showBudget(
            String label, SearchResult result) {
        System.out.println(label + ": best="
                + result.best().value()
                + ", status="
                + (result.optimal() ? "OPTIMAL" : "PARTIAL")
                + ", nodes=" + result.visitedNodes()
                + ", upper=" + result.upperBound());
    }

    public static void main(String[] args) {
        Item[] classic = {
            new Item(10, 60),
            new Item(20, 100),
            new Item(30, 120)
        };
        int capacity = 50;

        Plan exact = exactDp(classic, capacity);
        Plan greedy = densityGreedy(classic, capacity);
        Plan approx = halfApprox(classic, capacity);

        System.out.println("Classic exact value: "
                + exact.value());
        System.out.println("Classic exact indices: "
                + exact.indices());
        System.out.println("Classic greedy value: "
                + greedy.value());
        System.out.println("Classic greedy indices: "
                + greedy.indices());
        System.out.println("Classic half value: "
                + approx.value());
        System.out.println("Classic fractional upper: "
                + fractionalUpper(classic, capacity));
        System.out.println("Classic plans feasible: "
                + (validPlan(classic, capacity, exact)
                && validPlan(classic, capacity, greedy)
                && validPlan(classic, capacity, approx)));

        showBudget("Budget 5",
                budgetedSearch(classic, capacity, 5));
        showBudget("Budget 50",
                budgetedSearch(classic, capacity, 50));

        Item[] greedyTrap = {
            new Item(1, 2),
            new Item(1000, 1000)
        };
        System.out.println("Trap greedy value: "
                + densityGreedy(greedyTrap, 1000).value());
        System.out.println("Trap half value: "
                + halfApprox(greedyTrap, 1000).value());
        System.out.println("Trap exact value: "
                + exactDp(greedyTrap, 1000).value());
        System.out.println("Trap upper bound: "
                + fractionalUpper(greedyTrap, 1000));

        System.out.println("Zero capacity exact: "
                + exactDp(classic, 0).value());
        System.out.println("Empty items exact: "
                + exactDp(new Item[0], 0).value());
        System.out.println("Empty items approx: "
                + halfApprox(new Item[0], 0).value());

        try {
            exactDp(classic, 100_001);
            System.out.println("Reject oversized DP: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject oversized DP: true");
        }

        try {
            densityGreedy(
                new Item[]{new Item(0, 5)}, 10);
            System.out.println("Reject zero weight: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject zero weight: true");
        }

        try {
            budgetedSearch(classic, 50, 0);
            System.out.println("Reject zero node budget: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject zero node budget: true");
        }
    }
}
~~~

### 14.1. Biên dịch và chạy

Yêu cầu **JDK 17+**, không cần thư viện ngoài:

~~~bash
javac -encoding UTF-8 ResourceTradeoffDemo.java
java ResourceTradeoffDemo
~~~

**Stdout dự kiến:**

~~~text
Classic exact value: 220
Classic exact indices: [1, 2]
Classic greedy value: 160
Classic greedy indices: [0, 1]
Classic half value: 160
Classic fractional upper: 240
Classic plans feasible: true
Budget 5: best=160, status=PARTIAL, nodes=5, upper=240
Budget 50: best=220, status=OPTIMAL, nodes=15, upper=220
Trap greedy value: 2
Trap half value: 1000
Trap exact value: 1000
Trap upper bound: 1001
Zero capacity exact: 0
Empty items exact: 0
Empty items approx: 0
Reject oversized DP: true
Reject zero weight: true
Reject zero node budget: true
~~~

### 14.2. Giải thích kết quả ví dụ

**Classic exact value 220:** DP chọn vật có index 1 và 2, tổng trọng lượng 50, tổng giá trị 220. Hàm trả danh sách [1,2], không chỉ giá trị.

**Classic greedy value 160:** tham lam chọn vật index 0 và 1 do mật độ 6 và 5 cao hơn 4. Khi đã lấy trọng lượng 30, vật index 2 có trọng lượng 30 không vừa 20 còn lại.

**Classic half value 160:** prefix là [0,1] giá trị 160; vật đơn lẻ tốt nhất index 2 giá trị 120. Thuật toán xấp xỉ 1/2 chọn prefix.

**Classic fractional upper 240:** nới lỏng thành cho lấy một phần vật cuối: 160+120×20/30=240. Đây là **cận trên của optimum nguyên**, không phải phương án 0/1 khả thi.

**Budget 5:** DFS mới ghé năm nút trong cây quyết định, chưa duyệt mọi nhánh; incumbent từ halfApprox vẫn có giá trị 160. Trả PARTIAL và cận trên 240, không mạo nhận tối ưu.

**Budget 50:** n=3 tạo cây đầy đủ 2^(3+1)−1=15 nút trong trường hợp này, đã xét hết và tìm giá trị 220. Trạng thái OPTIMAL, cận trên được cập nhật thành 220 chính xác.

**Trap greedy value 2:** vật nhỏ mật độ 2 cao hơn mật độ 1 của vật lớn, khiến tham lam thuần túy chọn phương án tệ. Thuật toán xấp xỉ chọn vật đơn lẻ tốt nhất giá trị 1000 và đạt đúng optimum. Fractional relaxation có cận 1001, không phải 1000, vì được phép lấy 999/1000 của vật lớn sau vật nhỏ.

**Hạn mức demo:** W>100.000 hoặc bảng quá 2.000.000 ô bị từ chối để không làm máy hết RAM. Search với nodeBudget≤0 bị từ chối; việc nhập vật trọng lượng 0 cũng bị từ chối theo hợp đồng, thay vì gây sai lệch thuật toán chia mật độ.

### 14.3. Độ phức tạp các hàm Java

| Hàm | Thời gian | Bộ nhớ thêm | Bảo đảm |
|---|---|---|---|
| densityGreedy | O(n log n) phép so | O(n) | Nghiệm khả thi, **không cận tổng quát** |
| halfApprox | O(n log n) phép so | O(n) | Nghiệm khả thi, ≥1/2 OPT |
| fractionalUpper | O(n log n) phép so | O(n) | **Upper bound** hợp lệ, không phải nghiệm nguyên |
| exactDp | O(nW) | O(nW) | OPTIMAL nếu chạy xong |
| budgetedSearch | O(min(B,2ⁿ)) nút + thời gian khởi tạo cận | O(n) stack + sắp index | PARTIAL hoặc OPTIMAL, nghiệm khả thi và upper bound |

Với budgetedSearch, B là số nút tối đa; việc dựng incumbent và cận fractional tốn thêm O(n log n) phép so. Duyệt DFS thô có worst-case O(2ⁿ), và cận O(min(B,2ⁿ)) ở đây ẩn hằng số do số nút của cây tối đa cỡ 2^(n+1). Việc sao chép danh sách index khi tìm nghiệm mới cũng tốn O(n) ở những lần cải thiện; không nên coi mọi lần ghi incumbent là O(1) nếu phân tích toàn bộ chi phí chính xác.

Mọi công thức trên đếm **số thao tác số học**. Với BigInteger, chi phí nhân chéo và rút gcd phụ thuộc số bit. Mảng DP lưu long và demo giới hạn tổng giá trị không tràn long.

## 15. Kiểm thử có phương pháp

### 15.1. Oracle nhỏ để kiểm tra tối ưu

Với n nhỏ (ví dụ 0..10), liệt kê mọi tập con 2ⁿ:
1. Tính tổng trọng lượng và tổng giá trị bằng số học chính xác.
2. Chỉ xét tập có tổng trọng lượng≤W.
3. Lấy giá trị lớn nhất làm oracle OPT.
4. So kết quả exactDp với oracle.
5. Kiểm tra các index của phương án exactDp không trùng, tổng trọng lượng không vượt W và giá trị khớp.

Nếu exact DP trả giá trị khác oracle trên một input hợp lệ, đây là lỗi cần sửa, không phải sai số được phép.

### 15.2. Kiểm tra chứng minh 1/2

Với mỗi input nhỏ:
- Tính exact OPT bằng oracle vét cạn.
- Tính ALG từ halfApprox.
- Kiểm tra \(2ALG\ge OPT\).
- Kiểm tra phương án halfApprox **khả thi**.

Không cần biết lời giải chính xác trong triển khai production, nhưng oracle nhỏ đặc biệt hữu ích để bắt lỗi comparator, lựa chọn singleton hoặc xử lý vật quá nặng.

### 15.3. Kiểm tra fractional upper

Với mỗi instance nhỏ:
- Tính U bằng fractionalUpper dưới dạng phân số BigInteger.
- So bằng nhân chéo: \(U_{\rm numerator}\ge OPT\times U_{\rm denominator}\).
- Không chuyển U sang double rồi round xuống để so.
- Thử W=0, mảng rỗng, vật quá nặng, nhiều giá trị 0, trọng lượng bằng nhau, mật độ bằng nhau.

Nếu U<OPT, lỗi có thể nằm ở so mật độ, phép chia phân số hoặc lọc vật.

### 15.4. Kiểm tra anytime và budget

Với một instance cố định:
- Khi B nhỏ, phương án phải khả thi.
- Tăng B, giá trị incumbent không được giảm.
- Nếu complete=false, nhãn phải là PARTIAL.
- Nếu complete=true, best phải bằng oracle OPT.
- Khi complete=true, upperBound phải bằng best chính xác.
- Khi PARTIAL, upperBound phải ≥oracle OPT.
- Với B=0, chương trình phải từ chối vì không có lượt duyệt nào; không âm thầm đặt “đã tìm kiếm đầy đủ”.
- Với n vượt giới hạn demo, từ chối rõ ràng thay vì vô tình chạy cây hàm mũ rất lớn.

Kiểm thử toàn bộ các quan hệ này mạnh hơn việc chỉ xem stdout của một input đẹp.

### 15.5. Stress, tính ổn định và chất lượng thật

Bổ sung benchmark:
- Số vật n tăng, W giữ nhỏ.
- W tăng, n giữ nhỏ.
- Các vật nhiều giá trị/trọng lượng trùng nhau.
- Một vật cực tốt nhưng bị greedy chọn muộn.
- Toàn bộ vật quá nặng.
- Toàn bộ vật có giá trị 0.
- Các giá trị lớn sát Long.MAX_VALUE và tình huống tổng giá trị vượt long.
- Nhiều request song song trong cùng giới hạn RAM.

Ghi **thời gian wall-clock, peak memory, p95/p99** và kiểm tra các đường từ chối hợp lệ. Không dùng các phép đo runtime để thay chứng minh cận xấp xỉ.

## 16. Các lỗi thường gặp

1. **Gọi heuristic là approximation mà không có chứng minh tỷ lệ xấu nhất.**
2. **Gọi một nghiệm tốt nhất đã thấy là OPTIMAL** dù chưa chứng minh không còn nghiệm tốt hơn.
3. **Dùng một nghiệm vi phạm ràng buộc làm cận dưới** của tối ưu.
4. **Tự đặt cận trên U bằng giá trị ước lượng** mà không chứng minh U≥OPT.
5. **Đọc sai hướng cận**: với tối đa hóa, incumbent khả thi là lower bound; fractional relaxation là upper bound.
6. **Dùng tỷ lệ U/L thay cho L/U** khi giải thích bảo đảm tối đa hóa.
7. **Chia cho 0 trong gap ratio** khi OPT hoặc upper bound bằng 0.
8. **Cho rằng greedy theo mật độ ba lô 0/1 luôn tối ưu**, nhầm với fractional knapsack.
9. **Bỏ vật quá nặng sai cách** rồi vẫn dùng vật ấy làm singleton khả thi.
10. **Bỏ qua vật đầu tiên không vừa nhưng tiếp tục prefix** rồi dùng nguyên chứng minh 1/2 mà không kiểm tra lại.
11. **Không lấy best singleton** trong thuật toán xấp xỉ, dẫn đến tỷ lệ có thể tiến sát 0.
12. **Dùng double để so v/w với số lớn**, tạo tie/đổi thứ tự không chính xác.
13. **Nhân chéo long có overflow** rồi tin kết quả comparator.
14. **Tính fractional upper bound bằng round xuống**, có thể làm cận trên không còn hợp lệ.
15. **Coi fractional optimum là nghiệm 0/1 khả thi**, dù nó có thể lấy một phần vật.
16. **Dùng DP O(nW) mà không xét mã hóa nhị phân của W**, gọi sai thành đa thức theo bit.
17. **Chỉ đo CPU mà quên RAM O(nW)** của bảng truy vết.
18. **Nén DP còn O(W) nhưng không giữ thông tin truy vết**, rồi vẫn hứa trả được tập vật chính xác.
19. **Duyệt DP c tăng cho 0/1 Knapsack**, khiến vật bị dùng nhiều lần.
20. **Coi timeout là nghiệm tối ưu**, không phân biệt PARTIAL và OPTIMAL.
21. **Không khởi tạo incumbent hợp lệ trước khi bị timeout**, có thể không có đáp án trả ra.
22. **Dùng số nút duyệt như một hard deadline thời gian**, dù chi phí mỗi nút không hằng.
23. **Cắt nhánh bởi một upper bound không hợp lệ**, làm exact solver bỏ mất nghiệm tối ưu.
24. **Không giữ danh sách vật khi trả giá trị mục tiêu**, không thể kiểm chứng tính khả thi.
25. **Không xử lý các vật có giá trị 0 hoặc W=0**, sinh chia cho 0 hay đáp án sai.
26. **Không kiểm tra số nguyên tràn khi cộng giá trị**, khiến cận và nghiệm sai.
27. **Nhầm FPTAS với PTAS**, bỏ phụ thuộc đa thức theo 1/epsilon.
28. **Tự gọi heuristic có “bảo đảm 99%” vì benchmark trung bình cao**, thiếu chứng minh.
29. **Chọn epsilon quá nhỏ nhưng không dự trù trạng thái và RAM**, dẫn tới runtime thất bại.
30. **Chỉ benchmark dữ liệu ngẫu nhiên, bỏ đối kháng và trường hợp biên**.
31. **Không lưu trạng thái proof/upper bound của solver**, khó giải thích kết quả cho người dùng.
32. **Không ghi phiên bản đầu vào, tham số và thời hạn**, khiến kết quả không tái lập được.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Khi nào một thuật toán được gọi là exact?

**Đáp án:** Khi nó tìm và chứng minh một nghiệm có giá trị đúng OPT trong miền đầu vào/hợp đồng đã nêu.

**Câu 2.** Khác biệt chính giữa approximation và heuristic?

**Đáp án:** Approximation có cận chất lượng xấu nhất được chứng minh; heuristic nói chung không.

**Câu 3.** Với bài tối đa hóa, nghiệm khả thi giá trị L là cận gì?

**Đáp án:** Cận dưới, L≤OPT.

**Câu 4.** Với tối đa hóa và fractional relaxation, optimum fractional F có thể dùng làm gì?

**Đáp án:** Cận trên U=F≥OPT nguyên.

**Câu 5.** Nếu L=160,U=240, có thể chứng minh tỷ lệ chất lượng nào?

**Đáp án:** L/OPT≥L/U=2/3 khi OPT>0.

**Câu 6.** Trong ví dụ ba lô W=50, greedy và OPT bằng bao nhiêu?

**Đáp án:** Greedy 160 (vật 0,1), OPT 220 (vật 1,2).

**Câu 7.** Vì sao greedy thuần có thể kém tối ưu rất nhiều?

**Đáp án:** Vật nhỏ mật độ cao có thể chặn một vật lớn giá trị vượt trội; ví dụ W=1000 trả 2 thay vì 1000.

**Câu 8.** Thuật toán chọn max(prefix,best singleton) bảo đảm gì?

**Đáp án:** Đạt ít nhất 1/2 OPT với trọng lượng dương, giá trị không âm và vật quá nặng đã lọc.

**Câu 9.** Bước nào quan trọng trong chứng minh 1/2?

**Đáp án:** Fractional optimum không vượt prefix P cộng giá trị vật đầu tiên không vừa, và best singleton có giá trị ít nhất giá trị vật ấy.

**Câu 10.** Tại sao cần so mật độ bằng BigInteger?

**Đáp án:** Tránh sai số double và overflow khi nhân chéo các giá trị long.

**Câu 11.** DP 0/1 Knapsack theo W có thời gian và bộ nhớ bao nhiêu?

**Đáp án:** O(nW) thời gian; O(nW) nếu giữ bảng để truy vết, có thể O(W) nếu chỉ cần giá trị.

**Câu 12.** Vì sao O(nW) được gọi là giả đa thức?

**Đáp án:** Vì W là giá trị số học; số bit biểu diễn W chỉ cỡ log W.

**Câu 13.** Anytime PARTIAL khác OPTIMAL thế nào?

**Đáp án:** PARTIAL chưa kiểm tra hết không gian cần thiết, OPTIMAL đã có chứng minh không còn nghiệm tốt hơn.

**Câu 14.** Kết quả Budget 5 và Budget 50 trong ví dụ?

**Đáp án:** Budget 5: best160, PARTIAL, upper240; Budget 50: best220, OPTIMAL, upper220.

**Câu 15.** FPTAS bảo đảm điều gì?

**Đáp án:** Chất lượng 1−epsilon đối với bài tối đa hóa phù hợp, thời gian đa thức theo kích thước input và 1/epsilon.

**Câu 16.** Có nên gọi một thuật toán chạy rất nhanh nhưng không chứng minh cận là FPTAS?

**Đáp án:** Không; tốc độ thực nghiệm không thay thế chứng minh chất lượng xấp xỉ.

**Câu 17.** Vì sao số nút duyệt không phải giới hạn thời gian cứng?

**Đáp án:** Mỗi nút có thể dùng thời gian khác nhau do phép tính, bộ nhớ, GC và môi trường chạy.

**Câu 18.** Làm sao bảo đảm một incumbent vẫn hợp lệ khi bị ngắt?

**Đáp án:** Khởi tạo từ nghiệm đã kiểm chứng và chỉ cập nhật bằng nghiệm mới đã xác minh toàn bộ ràng buộc.

**Câu 19.** Khi U=OPT và có nghiệm khả thi L=U, ta kết luận gì?

**Đáp án:** Nghiệm ấy là OPTIMAL, vì L≤OPT≤U=L.

**Câu 20.** Với W=0 và trọng lượng vật đều dương, đáp án đúng là gì?

**Đáp án:** Nghiệm rỗng có tổng trọng lượng 0 và tổng giá trị 0.

**Ghi nhớ:** Khi tài nguyên hạn chế, câu hỏi quan trọng không phải “exact, approximate hay heuristic cái nào tốt nhất nói chung?”, mà là **hợp đồng chất lượng, thời hạn và ngân sách tài nguyên cụ thể**. Hãy ưu tiên tính khả thi, dùng **exact** khi có thể chứng minh tối ưu trong hạn mức, dùng **approximation** khi cần cận chất lượng, và dùng **heuristic** khi chấp nhận rủi ro chất lượng nhưng vẫn kiểm tra nghiệm. Với anytime, luôn báo rõ **PARTIAL/OPTIMAL, lower/upper bounds**, không để một deadline biến nghiệm chưa chứng minh thành “tối ưu”.

# Thuật toán đa thức, giả đa thức và hàm mũ

**Chủ đề:** Computer Science Algorithms · Độ khó bài toán

## 1. Vì sao cần phân biệt ba kiểu thời gian chạy?

Khi đánh giá thuật toán, ta thường nghe:

- “Thuật toán chạy trong thời gian **đa thức**.”
- “Quy hoạch động có độ phức tạp **O(nW)**, vậy chắc cũng là đa thức?”
- “Vét cạn có **O(2ⁿ)**, nên là **hàm mũ**.”

Những câu này chỉ có ý nghĩa khi xác định đúng **kích thước đầu vào**. Trong lý thuyết độ phức tạp, kích thước đầu vào là **số ký hiệu hoặc số bit dùng để biểu diễn toàn bộ dữ liệu**, không phải giá trị số học của một tham số bất kỳ.

Ví dụ sức chứa ba lô W=1.000.000:
- Giá trị số học W bằng một triệu.
- Biểu diễn nhị phân W cần **20 bit**.
- Một thuật toán có vòng lặp từ 0 tới W phải thực hiện khoảng một triệu bước theo W, dù bản thân W chỉ cần 20 bit trong dữ liệu vào.

Nếu đặt b là số bit của W, thì W có thể ở quy mô \(2^b\). Do đó **O(nW)** có thể trở thành **O(n2ᵇ)** theo b. Nó đa thức theo *giá trị W*, nhưng không nhất thiết đa thức theo *số bit mã hóa W*. Đây là sự khác biệt cốt lõi giữa **đa thức** và **giả đa thức**.

Bài này trình bày định nghĩa, cách xác định kích thước đầu vào, ví dụ **0/1 Knapsack**, **Subset Sum**, **vét cạn 2ⁿ**, liên hệ với **NP-hard yếu/mạnh**, lựa chọn thuật toán theo ràng buộc và chương trình **Java 17 có thể chạy độc lập**.

## 2. Kích thước đầu vào theo bit

Giả sử đầu vào chứa n vật, mỗi vật có trọng lượng w[i] và giá trị v[i], cùng sức chứa W.

Nếu các số nguyên dương được mã hóa **nhị phân**, số bit để biểu diễn một số x≥1 là:

\[
\operatorname{bits}(x)=\lfloor\log_2x\rfloor+1.
\]

Ví dụ:

| Giá trị x | Số bit nhị phân |
|---:|---:|
| 1 | 1 |
| 7 | 3 |
| 15 | 4 |
| 16 | 5 |
| 1.000.000 | 20 |
| 1.000.000.000 | 30 |
| 1.073.741.824 = 2³⁰ | 31 |

Khi có n vật, tổng chiều dài đầu vào L còn chứa biểu diễn của **n trọng lượng, n giá trị, W** và phần mã hóa cấu trúc. Không được viết L=log W cho mọi bài mà bỏ qua các vật. Nhưng khi phân tích sự phụ thuộc vào **một tham số số học**, số bit của tham số đó chỉ tăng như log của trị số.

### 2.1. Nhị phân và đơn phân (unary)

- Nhị phân biểu diễn W bằng O(log(W+1)) bit.
- Đơn phân biểu diễn W bằng W dấu gạch/ký tự giống nhau nên cần Θ(W) ký hiệu.

Nếu một thuật toán mất O(nW), nó có thể là đa thức khi dữ liệu số được mã hóa **đơn phân**, vì độ dài đầu vào đã lớn tới W. Nhưng với dữ liệu thường được mã hóa nhị phân, O(nW) có thể là hàm mũ theo độ dài biểu diễn của W.

Đây là lý do **giả đa thức** không đồng nghĩa với “đa thức nhưng hơi chậm” hay “gần đa thức”: thuật ngữ mô tả chính xác **tham số đo kích thước**.

### 2.2. Nhận diện bằng thí nghiệm tăng độ lớn

Giữ số vật n cố định, nhân đôi sức chứa W:
- Thuật toán O(nW) có khoảng **gấp đôi** số trạng thái theo W.
- Nhưng số bit biểu diễn W chỉ tăng khoảng **một bit**.
- Nếu W nhân lên 2^k, số bước theo W có thể nhân lên 2^k, dù phần mô tả nhị phân của W chỉ dài thêm k bit.

Một thay đổi nhỏ về **chiều dài biểu diễn** vẫn có thể làm chi phí tăng rất lớn.

## 3. Thời gian đa thức (polynomial time)

Một thuật toán được gọi là chạy trong **thời gian đa thức** nếu thời gian bị chặn bởi:

\[
\boxed{T(L)=O(L^c)}
\]

với một **hằng số c** không phụ thuộc L, và L là **độ dài đầu vào** theo mô hình mã hóa đã chọn.

Ví dụ thường gặp:
- Duyệt một mảng n phần tử: O(n).
- Dùng hai vòng lặp lồng nhau trên n phần tử: O(n²).
- Sắp xếp so sánh bằng thuật toán bảo đảm O(n log n) phép so sánh.
- BFS/DFS: O(V+E) thao tác trên biểu diễn đồ thị chuẩn, nếu thao tác trên đỉnh/cạnh được xem là đơn vị.

Những cận này là đa thức theo **số phần tử biểu diễn**, nếu các phép toán cơ bản có chi phí phù hợp. Đối với số nguyên nhiều bit, một phép nhân, chia, so sánh hoặc cộng có **chi phí bit** riêng; không được âm thầm coi thao tác trên số khổng lồ luôn O(1) nếu đang phân tích nghiêm ngặt theo bit.

### 3.1. Ví dụ tuyến tính bằng Java

Tìm vị trí đầu tiên của một giá trị trong mảng:

~~~text
Input: [4, 1, 7, 1]
Find 7 -> index 2
Find 9 -> index -1
~~~

Chương trình chỉ duyệt tối đa n phần tử và so sánh giá trị. Với phần tử int cố định, thời gian **O(n)** và bộ nhớ phụ **O(1)**. Số bước không tăng theo trị số của phần tử: mảng [1,2,3] và mảng [1,1000000000,3] đều chỉ cần xét tối đa 3 vị trí.

### 3.2. Đa thức không có nghĩa luôn nhanh

O(n⁸) vẫn là đa thức theo n nhưng có thể không dùng được trong thực tế. Ngược lại, thuật toán hàm mũ O(2ⁿ) đôi khi nhanh khi n≤20.

Vì vậy có **hai câu hỏi khác nhau**:
1. Loại độ phức tạp của thuật toán là gì theo kích thước đầu vào?
2. Với giới hạn n,W cụ thể và hằng số cài đặt, phương pháp nào thực sự chạy đủ nhanh?

Phân loại đa thức/giả đa thức/hàm mũ giải đáp câu thứ nhất; lựa chọn thuật toán thực tế cần cả câu thứ hai.

## 4. Thời gian hàm mũ (exponential time)

Thuật toán hàm mũ thường có độ phức tạp kiểu:

\[
\boxed{O(c^n)},\qquad c>1,
\]

với n là số quyết định/phần tử có thể tăng theo chiều dài đầu vào.

Ví dụ liệt kê tất cả các tập con của n vật:
- Mỗi vật có hai lựa chọn: **lấy** hoặc **không lấy**.
- Có đúng **2ⁿ** tập con.
- Nếu một quá trình DFS giữ sẵn tổng trọng lượng/tổng giá trị hiện tại, có thể cập nhật một nhánh với O(1) thao tác.
- Số nút trong cây nhị phân đầy đủ là 2^(n+1)−1, nên thời gian **Θ(2ⁿ)** nếu phải duyệt mọi tập con.

Bộ nhớ stack khi duyệt DFS từng nhánh là **O(n)**; không nhất thiết phải lưu toàn bộ 2ⁿ tập con.

### 4.1. Những con số minh họa

| Số vật n | Số tập con 2ⁿ |
|---:|---:|
| 10 | 1.024 |
| 20 | 1.048.576 |
| 30 | 1.073.741.824 |
| 40 | 1.099.511.627.776 |

Với n=20, hơn một triệu tập con có thể vẫn khả thi tùy phép tính trong mỗi nhánh. Với n=40, hơn một nghìn tỷ tập con thường quá lớn. Đó là lý do một thuật toán hàm mũ có thể rất tốt cho n nhỏ nhưng bùng nổ khi n tăng.

### 4.2. Cận hàm mũ và đầu vào thực

Cận O(2ⁿ) mô tả một thuật toán/đường chạy, không nói mọi đầu vào có độ khó thực tế như nhau. **Branch and bound**, **memoization** hoặc các điều kiện tỉa nhánh có thể cải thiện rất nhiều trường hợp nhưng không tự làm biến mất cận xấu nhất nếu chưa có chứng minh mạnh hơn.

**Meet-in-the-middle** có thể giảm những bài liệt kê tập con từ O(2ⁿ) xuống khoảng O(2^(n/2)) về số tổ hợp nửa mảng, đánh đổi bộ nhớ và thao tác ghép. Dù 2^(n/2) nhỏ hơn nhiều 2ⁿ, nó vẫn là **hàm mũ theo n**.

## 5. Thời gian giả đa thức (pseudo-polynomial time)

Thuật toán **giả đa thức** có thời gian là đa thức theo một số **giá trị số học trong đầu vào** và phần kích thước cấu trúc, nhưng không nhất thiết đa thức theo **số bit mã hóa** các giá trị đó.

Ví dụ:

\[
T(n,W)=O(nW).
\]

Nếu W được biểu diễn bằng b bit thì W có thể cỡ 2ᵇ, và T có thể cỡ O(n2ᵇ). Đây là thuật toán giả đa thức theo sức chứa W.

Những dấu hiệu điển hình:
- Có bảng DP với trục là **tổng trọng lượng, tổng tiền, tổng giá trị, tổng mục tiêu**.
- Vòng lặp chạy từ 0 tới một giá trị lớn S/W/B, không phải từ 0 tới **số chữ số** của giá trị đó.
- Nếu số đó nhân đôi thì trạng thái/chi phí gần như nhân đôi, dù chuỗi nhị phân chỉ thêm khoảng một bit.

**Giả đa thức không phải luôn là hàm mũ theo n.** Thuật toán O(nW) có thể cực nhanh khi W nhỏ, dù n lớn, và cực chậm khi W lớn dù n chỉ vài vật.

### 5.1. So sánh phụ thuộc vào n và W

| Thuật toán | Chi phí điển hình | Phụ thuộc chính |
|---|---|---|
| Duyệt mảng | O(n) | Số phần tử n |
| Vét cạn mọi tập con | O(2ⁿ) | Số vật n |
| 0/1 Knapsack DP theo sức chứa | O(nW) | n và **giá trị W** |
| Subset Sum DP theo tổng đích | O(nS) | n và **giá trị S** |
| Duyệt tất cả tổ hợp k phần tử | O(C(n,k)) lần sinh kết quả | Số kết quả có thể hàm mũ |
| Meet-in-the-middle subset sum | O(2^(n/2)) hoặc thêm log tùy triển khai | n, không phải tổng đích S |

Khi W rất nhỏ và n lớn, DP theo W có thể thắng liệt kê tập con. Khi W cực lớn và n rất nhỏ, brute force có thể thắng DP theo W. Không thể nhìn riêng một ký hiệu O mà không thay số giới hạn thực tế.

## 6. Bài toán ba lô 0/1 (0/1 Knapsack)

Có n vật. Vật i có trọng lượng nguyên dương w[i] và giá trị nguyên không âm v[i]. Mỗi vật chỉ được lấy **0 hoặc 1 lần**. Ba lô có sức chứa W≥0. Cần tối đa:

\[
\max\sum_{i=1}^n v_i x_i
\]

dưới ràng buộc:

\[
\sum_{i=1}^n w_i x_i\le W,
\qquad x_i\in\{0,1\}.
\]

Chọn không lấy vật nào là hợp lệ, cho giá trị 0.

Bài này khác **fractional knapsack**, nơi có thể lấy một phần vật và chiến lược tham lam theo v_i/w_i giải được. Với **0/1 Knapsack**, tham lam theo tỷ lệ không bảo đảm tối ưu.

### 6.1. Ví dụ nhỏ

~~~text
weight = [2, 3, 4, 5]
value  = [3, 4, 5, 8]
~~~

Với W=7, lấy vật có w=2,v=3 và vật w=5,v=8 được tổng trọng lượng 7 và giá trị **11**. Đây là giá trị tối ưu.

Với W=9, lấy vật w=4,v=5 cùng vật w=5,v=8 cho giá trị **13**.

Với W=10, lấy vật w=2,v=3, w=3,v=4, w=5,v=8 cho giá trị **15**.

| W | Lựa chọn tối ưu ví dụ | Giá trị |
|---:|---|---:|
| 0 | Không lấy vật | 0 |
| 5 | Vật trọng lượng 5 | 8 |
| 7 | Vật trọng lượng 2 và 5 | 11 |
| 9 | Vật trọng lượng 4 và 5 | 13 |
| 10 | Vật trọng lượng 2, 3 và 5 | 15 |

Hai hướng thuật toán sẽ tìm cùng một optimum nhưng có bản chất độ phức tạp khác nhau: **DFS liệt kê 2ⁿ** và **quy hoạch động O(nW)**.

## 7. Giải 0/1 Knapsack bằng liệt kê — hàm mũ

Với mỗi vật i, thử hai lựa chọn:
1. Không lấy vật i.
2. Lấy vật i (nếu sau cùng tổng trọng lượng vẫn không vượt W).

Một oracle đơn giản, dễ chứng minh, **không tỉa nhánh**:
- DFS i từ 0 tới n.
- Mang theo tổng trọng lượng và tổng giá trị hiện tại.
- Khi i=n, tăng bộ đếm **leaves**. Nếu tổng trọng lượng ≤W, cập nhật best.
- Vì mỗi vật có đúng hai nhánh, đã xét tất cả 2ⁿ tập con.

Độ phức tạp:

\[
\boxed{\Theta(2^n)\text{ thời gian},\quad O(n)\text{ stack}}.
\]

Nếu n=4, số lá là **16** với mọi sức chứa W, kể cả W=0. Vì oracle không tỉa nhánh, nó vẫn duyệt các lựa chọn vượt sức chứa rồi loại ở lá. Đây là cách triển khai dễ kiểm tra chính xác bộ đếm, không phải lựa chọn tối ưu hiệu năng.

Nếu cài brute force bằng cách **tái tính tổng n vật** cho từng mặt nạ bit, cận có thể thành O(n2ⁿ). Việc tích lũy tổng khi DFS giải thích vì sao chương trình mẫu có thể dùng O(2ⁿ) thay vì O(n2ⁿ) phép toán cập nhật.

### 7.1. Giới hạn thực tế

Với n≤20, có nhiều nhất 1.048.576 lá; brute force đủ dùng làm oracle cho test nhỏ. Với n=40 có hơn một nghìn tỷ lá; không phù hợp để kiểm chứng đơn giản.

Trong Java demo, nhánh brute force được giới hạn **n≤20**. Đây là **giới hạn vận hành** để tránh chạy quá lâu, không phải định nghĩa toán học của vét cạn.

## 8. Giải 0/1 Knapsack bằng DP theo sức chứa — giả đa thức

Định nghĩa:

\[
dp_i[c]=\text{giá trị lớn nhất có thể chọn từ i vật đầu tiên, trọng lượng}\le c.
\]

Với vật i trọng lượng w, giá trị v:

\[
dp_i[c]=
\begin{cases}
dp_{i-1}[c],& c<w,\\
\max(dp_{i-1}[c],dp_{i-1}[c-w]+v),&c\ge w.
\end{cases}
\]

Đây là hai lựa chọn **không lấy/lấy đúng một lần** vật i. Bài toán con chỉ dùng i−1 vật, nên vật hiện tại không bị chọn lặp lại.

Khởi tạo:

\[
dp_0[c]=0
\]

cho mọi c≥0 (không có vật). Đáp án là dp_n[W].

### 8.1. Nén bộ nhớ từ O(nW) xuống O(W)

Thay vì giữ tất cả hàng theo i, dùng một mảng dp[c]. Với từng vật:
- Duyệt c từ **W xuống w**.
- Cập nhật dp[c]=max(dp[c],dp[c−w]+v).

**Phải duyệt c giảm dần.** Vì dp[c−w] chưa được cập nhật cho vật hiện tại, nó vẫn là kết quả của i−1 vật. Nếu duyệt tăng, ta có thể dùng vật i nhiều lần, vô tình chuyển thành **unbounded knapsack**.

Phản ví dụ chỉ có một vật:
- w=2, v=3, W=4.
- 0/1 Knapsack đúng phải trả **3** vì vật chỉ lấy một lần.
- Nếu duyệt tăng và dùng dp[2]=3 mới cập nhật cho dp[4], có thể tạo giá trị **6** (lấy cùng vật hai lần), sai ràng buộc 0/1.

### 8.2. Chứng minh đúng theo bất biến

Trước khi xử lý vật i, dp[c] là giá trị tốt nhất từ các vật 1..i−1 trong sức chứa c. Tại c≥w_i, hai trường hợp:
- Không lấy vật i: dùng dp[c] cũ.
- Có lấy vật i: dùng kết quả từ i−1 vật với sức chứa c−w_i, cộng v_i.

Vì duyệt c giảm, dp[c−w_i] vẫn là kết quả cũ. Lấy max hai trường hợp sẽ đúng cho i vật. Sau n lượt, dp[W] là tối ưu.

### 8.3. Độ phức tạp chính xác

Với n vật và W là một **giá trị số nguyên**, có tối đa n×(W+1) cập nhật; mỗi cập nhật là phép so và cộng:

\[
\boxed{O(nW)\text{ thời gian},\quad O(W)\text{ bộ nhớ}}.
\]

Cận trên này là **giả đa thức**, không phải đa thức tổng quát theo số bit. Nếu W có b bit, W có thể lớn cỡ 2ᵇ, nên số trạng thái tăng theo **hàm mũ của b**.

Mã minh họa cấp phát mảng **W+1** trạng thái, kiểm tra W≤1.000.000 để không vô tình cấp phát quá lớn. **Giới hạn tài nguyên của demo không thay đổi bản chất thuật toán**; W lớn hơn có thể đòi một phương pháp khác, không có nghĩa bài toán vô nghiệm.

### 8.4. Khi W rất lớn nhưng tổng trọng lượng nhỏ

Nếu W≥∑w[i], với mọi giá trị không âm, có thể lấy tất cả các vật; giá trị tối ưu là ∑v[i]. Đây là một tối ưu hóa đặc biệt. Nói chung, có thể thay W bằng min(W,∑w[i]) khi xây DP theo trọng lượng.

Nhưng điều đó **không biến phương pháp thành đa thức tổng quát theo bit**, vì tổng trọng lượng cũng có thể là một giá trị nguyên khổng lồ. Cần phân biệt giảm trạng thái nhờ đặc điểm dữ liệu với một chứng minh đa thức cho mọi đầu vào.

## 9. Subset Sum — một ví dụ giả đa thức khác

Cho n số nguyên **không âm** a[0..n−1] và tổng đích S≥0. Hỏi có thể chọn một **tập con** có tổng đúng S hay không?

Đặt:

\[
reachable_i[s]=
\text{có thể tạo tổng s từ i phần tử đầu tiên?}
\]

Khởi tạo reachable[0]=true vì tập rỗng có tổng 0.

Với giá trị x:

\[
reachable_{\text{new}}[s]
=reachable_{\text{old}}[s]
\lor
(s\ge x\land reachable_{\text{old}}[s-x]).
\]

Cũng như 0/1 Knapsack, nén vào một chiều và duyệt s **từ S xuống x**, để mỗi phần tử chỉ được lấy một lần.

~~~text
numbers = [3, 4, 5]
target 9  -> true: 4 + 5
target 2  -> false
target 12 -> true: 3 + 4 + 5
target 0  -> true: tập rỗng
~~~

Độ phức tạp:

\[
\boxed{O(nS)\text{ thời gian},\quad O(S)\text{ bộ nhớ}}.
\]

Đây là **giả đa thức** theo giá trị S. Nếu S được mã hóa nhị phân với b bit, S có thể cỡ 2ᵇ.

### 9.1. Vì sao phải giới hạn đầu vào không âm?

Nếu có số âm, trạng thái tổng có thể âm và không nằm trong chỉ số 0..S; thuật toán boolean[S+1] không còn biểu diễn đủ mọi tổng trung gian. Muốn xử lý số âm phải dùng khoảng tổng âm/dương có offset, tập hash các tổng có thể đạt, hoặc một chiến lược khác.

Mã Java **từ chối số âm**, không âm thầm bỏ qua. Các số 0 vẫn hợp lệ: chúng không tạo tổng mới, nhưng không làm sai tính đúng.

### 9.2. Bitset và tối ưu hiệu năng

Dùng bitset, phép dịch và OR có thể cập nhật nhiều trạng thái trong một từ máy, tăng hiệu năng khi S vừa phải. Tuy nhiên số bit trạng thái vẫn tỷ lệ với S, nên đây vẫn là cách tiếp cận **giả đa thức** theo giá trị tổng S, không tự trở thành đa thức theo số bit biểu diễn S.

## 10. So sánh n, W, S và chiều dài đầu vào

Ví dụ W=1.000.000 được mã hóa trong **20 bit**. Nếu dùng DP trực tiếp với W+1 trạng thái, bộ nhớ vẫn tỷ lệ khoảng một triệu phần tử, không phải 20 phần tử.

Khi W tăng theo \(W=2^b\), thì:

\[
O(nW)=O(n2^b).
\]

Vì vậy dù biểu thức nW trông như “nhân hai tham số” và là đa thức theo **trị số của W**, nó có thể là hàm mũ theo **b là số bit**.

Ngược lại với vét cạn theo số vật:
- Nếu n=20, cần 2²⁰≈1.048.576 tập con.
- Nếu W=10⁹, DP sức chứa phải xét tới khoảng một tỷ trạng thái trên mỗi vật (nếu không có đặc điểm giúp giảm sức chứa).
- Trong trường hợp ấy, brute force theo n có thể thực tế hơn, mặc dù có cận **hàm mũ theo n**.

Không tồn tại quy tắc “đa thức luôn nhanh hơn giả đa thức, giả đa thức luôn nhanh hơn hàm mũ” cho mọi **giới hạn đầu vào thực tế**. Khái niệm độ phức tạp nói về **cách tăng trưởng tiệm cận**, còn việc chọn thuật toán phải xét các tham số cụ thể.

### 10.1. Một bảng quyết định

| Dạng ràng buộc | Hướng suy nghĩ |
|---|---|
| n rất nhỏ, W cực lớn | Liệt kê tập con, meet-in-the-middle hoặc branch and bound |
| W vừa phải, n lớn hơn | DP theo sức chứa O(nW) |
| Tổng giá trị V nhỏ dù W lớn | DP theo giá trị (lưu trọng lượng nhỏ nhất) O(nV) |
| Cần chính xác, n vừa và W vừa | DP 0/1 theo trọng lượng |
| Chỉ cần xấp xỉ tốt có chứng minh | Xem FPTAS cho 0/1 Knapsack |
| S nhỏ trong Subset Sum | DP theo tổng S, có thể tối ưu bằng bitset |
| Cả n và các giá trị số đều rất lớn | Cần tận dụng cấu trúc, xấp xỉ hoặc các kỹ thuật nâng cao; không hy vọng vét cạn/DP thô luôn đủ |

## 11. DP theo tổng giá trị: đổi một tham số giả đa thức lấy tham số khác

Ngoài cách dùng sức chứa W làm trục trạng thái, 0/1 Knapsack có thể dùng **tổng giá trị** làm trục.

Đặt \(V=\sum_i v_i\), và:

\[
minWeight_i[v]=
\text{trọng lượng nhỏ nhất để đạt tổng giá trị đúng v từ i vật đầu}.
\]

Các trạng thái không đạt được có giá trị +∞.

Chuyển với vật có trọng lượng w, giá trị value:
- Không lấy: giữ minWeight[v].
- Lấy: minWeight[v+value] = min(minWeight[v+value], minWeight[v]+w), duyệt v giảm để không lấy vật lặp.

Sau khi xử lý tất cả vật, lấy v lớn nhất thỏa minWeight[v]≤W.

Chi phí theo tổng giá trị:

\[
O(nV)\text{ thời gian},\quad O(V)\text{ bộ nhớ}.
\]

Đây vẫn là **giả đa thức** nếu giá trị các vật mã hóa nhị phân có thể rất lớn. Tuy nhiên nó giúp khi W lớn còn tổng giá trị V nhỏ. Đừng gọi đây là thuật toán đa thức tổng quát chỉ vì đã bỏ W khỏi công thức.

Khi dùng giá trị long trong code thực tế, phải cẩn thận \(\sum_i v_i\) có thể vượt long, chưa kể V quá lớn để cấp phát mảng. Phần DP giá trị ở đây là mô hình thuật toán, không nằm trong demo Java để tránh triển khai bảng khổng lồ ngoài phạm vi bài.

## 12. NP-hard yếu, NP-hard mạnh và ý nghĩa của giả đa thức

Các bài như **0/1 Knapsack** (phiên bản quyết định thích hợp) và **Subset Sum** là ví dụ kinh điển của bài **NP-complete yếu (weakly NP-complete)**. Phiên bản tối ưu hóa ba lô là **NP-hard**.

Chữ **yếu** không có nghĩa “luôn dễ”. Nó chỉ phản ánh vai trò của **giá trị số học** trong độ khó: một số bài có thuật toán giả đa thức nên trở nên đa thức khi các giá trị số được giới hạn đủ nhỏ hoặc mã hóa đơn phân.

**Strongly NP-hard** mô tả những bài vẫn NP-hard ngay cả khi các giá trị số học quan trọng bị giới hạn bởi đa thức của kích thước cấu trúc (theo cách mã hóa thích hợp). Ví dụ kinh điển là **3-Partition**.

Với các giả thiết chuẩn, nếu một bài strongly NP-hard có thuật toán **giả đa thức tổng quát** thì trên các instance số học bị chặn đa thức thuật toán ấy trở thành đa thức, kéo theo P=NP. Vì vậy, **trừ khi P=NP**, không kỳ vọng thuật toán giả đa thức tổng quát cho những bài strongly NP-hard đó.

### 12.1. Không suy ngược sai

- Có thuật toán giả đa thức **không đồng nghĩa P=NP**. DP O(nW) của 0/1 Knapsack không chứng minh Knapsack có thuật toán đa thức theo bit.
- Có thuật toán giả đa thức không có nghĩa bài toán “dễ” khi W hoặc S rất lớn.
- Không có thuật toán giả đa thức **đã biết** không tự động chứng minh strongly NP-hard.
- Phân loại NP-hard là thuộc tính **bài toán**, còn O(nW), O(2ⁿ) là thuộc tính của **thuật toán cụ thể**.
- Nếu **P=NP** được chứng minh trong tương lai, nhiều kết luận có điều kiện ở đây phải diễn giải lại. Hiện chưa có chứng minh P=NP hoặc P≠NP.

## 13. FPTAS: từ giả đa thức sang xấp xỉ được bảo đảm

Với **bài 0/1 Knapsack tối đa hóa, giá trị không âm**, có một **FPTAS** (Fully Polynomial-Time Approximation Scheme): với mọi độ chính xác \(0<\epsilon<1\), thuật toán trả lời giải hợp lệ có giá trị ít nhất:

\[
\boxed{(1-\epsilon)\,OPT}
\]

và thời gian **đa thức theo kích thước đầu vào cùng 1/epsilon**, thay vì phụ thuộc trực tiếp vào W khổng lồ.

Một ý tưởng là **co giãn giá trị**:
1. Bỏ những vật tự nó nặng hơn W (chúng không thể có mặt trong lời giải khả thi).
2. Nếu không có vật có giá trị dương khả thi, đáp án 0 là hiển nhiên.
3. Đặt \(V_{\max}\) là giá trị lớn nhất của một vật khả thi và \(K=\epsilon V_{\max}/n\).
4. Thay \(v_i\) bằng \(v'_i=\lfloor v_i/K\rfloor\).
5. Chạy DP theo **tổng giá trị đã co giãn**, lưu trọng lượng nhỏ nhất.
6. Khôi phục các vật của phương án tốt nhất nằm trong W.

Với giá trị có thể co giãn như trên:

\[
\sum_i v'_i\le nV_{\max}/K=n^2/\epsilon.
\]

Vậy bảng theo giá trị co giãn có thể được xử lý trong cỡ O(n³/epsilon) phép toán ở bản DP đơn giản. Do mỗi giá trị làm tròn xuống mất ít hơn K, lời giải tối ưu mất tối đa nK=epsilon Vmax≤epsilon OPT. Vì vậy giá trị khôi phục ≥(1−epsilon)OPT.

**Điều kiện:** phải chọn K hợp lệ, lọc vật không khả thi, xử lý OPT=0 và tính toán phép chia/làm tròn cẩn thận. Đây là **phác thảo thuật toán và chứng minh xấp xỉ**, không phải lời hứa rằng lấy nguyên mã DP theo trọng lượng sẽ tự trở thành FPTAS.

### 13.1. PTAS khác FPTAS

**PTAS:** với epsilon cố định, thời gian đa thức theo kích thước đầu vào, nhưng số mũ của đa thức có thể phụ thuộc 1/epsilon.

**FPTAS:** thời gian đa thức đồng thời theo **kích thước đầu vào và 1/epsilon**. FPTAS là bảo đảm mạnh hơn PTAS.

Không nên gọi một thuật toán “rất nhanh trong thử nghiệm” là FPTAS nếu chưa có **chứng minh chất lượng xấp xỉ và thời gian**.

## 14. Java 17 chạy độc lập: ba kiểu phức tạp

Lưu tệp **ComplexityClassesDemo.java**. Chương trình có:
1. **firstIndexOf:** tìm tuyến tính O(n), ví dụ đa thức.
2. **knapsackDp:** 0/1 Knapsack bằng DP theo W, O(nW) và O(W) bộ nhớ, giả đa thức.
3. **knapsackBrute:** duyệt đầy đủ 2ⁿ tập con, Θ(2ⁿ), dùng làm oracle cho n nhỏ.
4. **subsetSum:** DP theo tổng S, O(nS), giả đa thức.
5. Phân loại điều kiện đầu vào, giới hạn tài nguyên demo và kiểm tra tràn tổng giá trị bằng Math.addExact.

**Lưu ý:** các vật có trọng lượng **dương** và giá trị **không âm**; số cho Subset Sum **không âm**. Nơi nào bài toán khác cho phép giá trị âm, trọng lượng 0 hay tổng âm cần một mô hình/trạng thái khác hoặc chứng minh xử lý riêng. Code không âm thầm thay đổi hợp đồng để làm test “có vẻ chạy”.

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class ComplexityClassesDemo {
    private ComplexityClassesDemo() {
    }

    // Giới hạn an toàn về bộ nhớ cho chương trình MINH HỌA.
    // Không phải giới hạn toán học của DP.
    private static final int MAX_DP_TARGET = 1_000_000;
    private static final int MAX_BRUTE_ITEMS = 20;

    public record DpResult(long bestValue, long transitions) {
    }

    public record BruteResult(long bestValue, long leaves) {
    }

    // POLYNOMIAL: O(n) theo số phần tử.
    public static int firstIndexOf(int[] a, int target) {
        Objects.requireNonNull(a, "array");
        for (int i = 0; i < a.length; i++) {
            if (a[i] == target) {
                return i;
            }
        }
        return -1;
    }

    private static void checkItems(
            int[] weights, long[] values) {
        Objects.requireNonNull(weights, "weights");
        Objects.requireNonNull(values, "values");
        if (weights.length != values.length) {
            throw new IllegalArgumentException(
                    "Different item array lengths");
        }
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                        "Weights must be positive; values nonnegative");
            }
        }
    }

    private static void checkNonnegativeCapacity(int capacity) {
        if (capacity < 0) {
            throw new IllegalArgumentException(
                    "Capacity must be nonnegative");
        }
    }

    // PSEUDO-POLYNOMIAL: O(nW) time, O(W) space.
    // 0/1, nên capacity bắt buộc duyệt GIẢM.
    public static DpResult knapsackDp(
            int[] weights, long[] values, int capacity) {
        checkItems(weights, values);
        checkNonnegativeCapacity(capacity);
        if (capacity > MAX_DP_TARGET) {
            throw new IllegalArgumentException(
                    "Capacity exceeds the demo memory limit");
        }

        long[] dp = new long[capacity + 1];
        long transitions = 0;

        for (int i = 0; i < weights.length; i++) {
            int weight = weights[i];
            long value = values[i];

            for (int c = capacity; c >= weight; c--) {
                long withItem = Math.addExact(
                        dp[c - weight], value);
                dp[c] = Math.max(dp[c], withItem);
                transitions++;
            }
        }

        return new DpResult(dp[capacity], transitions);
    }

    private static final class SearchState {
        long bestValue;
        long leaves;
    }

    // EXPONENTIAL: duyệt TOÀN BỘ 2^n lá, không tỉa nhánh.
    private static void enumerate(
            int index, long usedWeight, long totalValue,
            int[] weights, long[] values,
            int capacity, SearchState result) {
        if (index == weights.length) {
            result.leaves++;
            if (usedWeight <= capacity) {
                result.bestValue =
                        Math.max(result.bestValue, totalValue);
            }
            return;
        }

        // Không lấy vật hiện tại.
        enumerate(index + 1, usedWeight, totalValue,
                weights, values, capacity, result);

        // Lấy vật hiện tại.
        enumerate(index + 1,
                Math.addExact(usedWeight, weights[index]),
                Math.addExact(totalValue, values[index]),
                weights, values, capacity, result);
    }

    public static BruteResult knapsackBrute(
            int[] weights, long[] values, int capacity) {
        checkItems(weights, values);
        checkNonnegativeCapacity(capacity);

        if (weights.length > MAX_BRUTE_ITEMS) {
            throw new IllegalArgumentException(
                    "Too many items for exhaustive demo");
        }

        SearchState state = new SearchState();
        enumerate(0, 0, 0, weights, values, capacity, state);
        return new BruteResult(state.bestValue, state.leaves);
    }

    // PSEUDO-POLYNOMIAL: O(nS) time, O(S) space.
    // numbers không âm, mỗi phần tử chỉ dùng một lần.
    public static boolean subsetSum(int[] numbers, int target) {
        Objects.requireNonNull(numbers, "numbers");
        if (target < 0 || target > MAX_DP_TARGET) {
            throw new IllegalArgumentException(
                    "Target out of supported demo range");
        }

        for (int number : numbers) {
            if (number < 0) {
                throw new IllegalArgumentException(
                        "Subset Sum numbers must be nonnegative");
            }
        }

        boolean[] can = new boolean[target + 1];
        can[0] = true;

        for (int x : numbers) {
            if (x > target) {
                continue;
            }
            for (int s = target; s >= x; s--) {
                if (can[s - x]) {
                    can[s] = true;
                }
            }
        }
        return can[target];
    }

    public static void main(String[] args) {
        int[] lookup = {4, 1, 7, 1};
        System.out.println("Linear search target 7: "
                + firstIndexOf(lookup, 7));
        System.out.println("Linear search target 9: "
                + firstIndexOf(lookup, 9));

        int[] weights = {2, 3, 4, 5};
        long[] values = {3, 4, 5, 8};

        DpResult dp7 = knapsackDp(weights, values, 7);
        BruteResult brute7 =
                knapsackBrute(weights, values, 7);

        System.out.println("Knapsack DP W=7: "
                + dp7.bestValue());
        System.out.println("Knapsack brute W=7: "
                + brute7.bestValue());
        System.out.println("DP transitions W=7: "
                + dp7.transitions());
        System.out.println("Brute leaves n=4: "
                + brute7.leaves());
        System.out.println("Knapsack DP W=9: "
                + knapsackDp(weights, values, 9).bestValue());
        System.out.println("Knapsack DP W=10: "
                + knapsackDp(weights, values, 10).bestValue());
        System.out.println("Knapsack DP W=0: "
                + knapsackDp(weights, values, 0).bestValue());
        System.out.println("Empty knapsack: "
                + knapsackDp(
                    new int[0], new long[0], 7).bestValue());

        int[] numbers = {3, 4, 5};
        System.out.println("Subset sum target 9: "
                + subsetSum(numbers, 9));
        System.out.println("Subset sum target 2: "
                + subsetSum(numbers, 2));
        System.out.println("Subset sum target 12: "
                + subsetSum(numbers, 12));
        System.out.println("Subset sum target 0: "
                + subsetSum(numbers, 0));
        System.out.println("Empty subset target 0: "
                + subsetSum(new int[0], 0));

        int w = 1_000_000;
        System.out.println("Binary bits for W=1000000: "
                + Integer.toBinaryString(w).length());

        try {
            knapsackDp(new int[]{-2}, new long[]{4}, 5);
            System.out.println("Reject negative weight: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject negative weight: true");
        }

        try {
            knapsackDp(weights, values, 1_000_001);
            System.out.println("Reject oversized capacity: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject oversized capacity: true");
        }

        try {
            subsetSum(new int[]{3, -1}, 2);
            System.out.println(
                    "Reject negative subset element: false");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "Reject negative subset element: true");
        }

        int[] manyWeights = new int[21];
        Arrays.fill(manyWeights, 1);
        try {
            knapsackBrute(manyWeights, new long[21], 10);
            System.out.println(
                    "Reject too many brute items: false");
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "Reject too many brute items: true");
        }
    }
}
~~~

### 14.1. Cách biên dịch và chạy

Với **JDK 17 hoặc mới hơn**, lưu đúng tên tệp và chạy:

~~~bash
javac -encoding UTF-8 ComplexityClassesDemo.java
java ComplexityClassesDemo
~~~

**Stdout dự kiến:**

~~~text
Linear search target 7: 2
Linear search target 9: -1
Knapsack DP W=7: 11
Knapsack brute W=7: 11
DP transitions W=7: 18
Brute leaves n=4: 16
Knapsack DP W=9: 13
Knapsack DP W=10: 15
Knapsack DP W=0: 0
Empty knapsack: 0
Subset sum target 9: true
Subset sum target 2: false
Subset sum target 12: true
Subset sum target 0: true
Empty subset target 0: true
Binary bits for W=1000000: 20
Reject negative weight: true
Reject oversized capacity: true
Reject negative subset element: true
Reject too many brute items: true
~~~

### 14.2. Tại sao các kết quả là như vậy?

**firstIndexOf:** duyệt tối đa n phần tử. [4,1,7,1] có 7 ở chỉ số 2 khi đếm từ 0, còn 9 không xuất hiện nên trả −1.

**knapsackDp:** với W=7, giá trị tối ưu là 11. Bộ đếm transitions tính **số lần thực sự duyệt vòng cập nhật trạng thái**, không phải toàn bộ n×(W+1) vị trí tiềm năng:
- Vật w=2: cập nhật c=7..2, có 6 lần.
- Vật w=3: c=7..3, có 5 lần.
- Vật w=4: c=7..4, có 4 lần.
- Vật w=5: c=7..5, có 3 lần.
- Tổng: 6+5+4+3=**18**.

**knapsackBrute:** với n=4, có 2⁴=**16** lá. Vì code không tỉa, đếm đủ cả 16 lá kể cả những tập con không khả thi; kết quả tối ưu vẫn 11.

**knapsackDp W=9 và W=10:** lần lượt cho giá trị 13 và 15 theo các tổ hợp ở mục 6. Dù tăng W làm số trạng thái tăng, **số vật n không đổi**, nên brute force vẫn có đúng 16 lá.

**subsetSum:** với [3,4,5], tổng 9 đạt được bằng 4+5; tổng 2 không thể tạo; tổng 12 đạt bởi 3+4+5; tổng 0 luôn đạt bởi tập rỗng, ngay cả khi mảng không có phần tử.

**Binary bits:** 1.000.000 nằm giữa \(2^{19}\) và \(2^{20}\), nên cần đúng **20 bit**. Đây là ví dụ trực tiếp giải thích vì sao một triệu trạng thái DP không tương đương 20 bit đầu vào.

**MAX_DP_TARGET=1.000.000:** chỉ là hàng rào để demo tránh cấp phát bảng quá lớn. Nếu W=1.000.001, code từ chối thay vì thử cấp phát; về mặt lý thuyết DP theo W vẫn được định nghĩa.

**Math.addExact:** đảm bảo không trả một giá trị long bị tràn âm thầm khi cộng giá trị vật. Nếu bài toán có tổng giá trị vượt long, cần chuyển sang BigInteger hoặc chọn một giới hạn giá trị phù hợp. Khả năng phát sinh ArithmeticException là giới hạn biểu diễn, không phải chứng minh một bài toán đã trở nên NP-hard hơn.

### 14.3. Tính runnable và phạm vi minh họa

Mã không yêu cầu thư viện ngoài và dùng các API Java 17 sẵn có. Một class public duy nhất trùng tên file. Các record dùng cú pháp Java 17. Brute force chỉ gọi với n=4 trong ví dụ chính; ca n=21 được **từ chối trước khi liệt kê**, tránh chạy khoảng hai triệu lá ngoài nhu cầu test.

Đầu vào được quy ước rõ: trọng lượng dương, giá trị không âm, sức chứa không âm, Subset Sum chỉ có số không âm. Nếu thay đổi bài toán, trước tiên phải đổi hợp đồng và chứng minh các trạng thái DP vẫn biểu diễn đầy đủ trường hợp.

## 15. Kiểm thử bằng oracle độc lập

### 15.1. Đối chiếu Knapsack

Với n nhỏ (ví dụ n từ 0 tới 10) và W nhỏ:
1. Sinh trọng lượng nguyên dương, giá trị không âm.
2. Tính DP theo sức chứa.
3. Liệt kê đủ mọi tập con bằng DFS **không dùng DP**.
4. So giá trị tối ưu của hai phương pháp.
5. Kiểm tra bộ đếm leaves đúng \(2^n\).

Nếu DP trả lớn hơn vét cạn, rất có thể đã lấy cùng vật nhiều lần (duyệt dung lượng tăng). Nếu DP trả thấp hơn, có thể thiếu một chuyển trạng thái hoặc bỏ qua vật hợp lệ.

### 15.2. Đối chiếu Subset Sum

Với mảng số không âm ngắn, tạo oracle duyệt mọi mặt nạ nhị phân, cộng các phần tử được chọn và kiểm tra có tổng bằng S. So với boolean DP.

Các ca cần có:
- Mảng rỗng, S=0 và S>0.
- Nhiều số 0.
- Phần tử bằng S.
- Phần tử lớn hơn S.
- Nhiều số lặp.
- Tổng tất cả phần tử nhỏ hơn S.
- S không thể biểu diễn, dù gần một tổng khả thi.
- Đầu vào chứa số âm: API phải từ chối.

### 15.3. Phân biệt kiểm thử với chứng minh

Kiểm thử ngẫu nhiên giúp bắt lỗi cài đặt, nhưng phân loại O(nW) là **giả đa thức** đến từ việc phân tích số bit biểu diễn W, không phải từ tốc độ đo trên 100 bộ dữ liệu. Tương tự, bộ đếm brute force n=4 có 16 lá minh họa cây quyết định nhưng không thay chứng minh số lá tổng quát 2ⁿ.

## 16. Các hiểu lầm hay gặp

1. **Gọi O(nW) là đa thức theo đầu vào mà không xét mã hóa W.** Với W nhị phân, số bit chỉ cỡ log W.
2. **Lấy trị số W làm độ dài đầu vào**, dù W=1.000.000 chỉ có 20 bit.
3. **Cho rằng giả đa thức tức gần đa thức**, một mô tả không chính xác về độ dài biểu diễn.
4. **Cho rằng O(2ⁿ) luôn chậm hơn O(nW)** trên mọi bộ dữ liệu, không thay giá trị n,W cụ thể.
5. **Cho rằng O(nW) luôn hàm mũ theo n**, trong khi W có thể là một hằng số nhỏ.
6. **Gộp thời gian kỳ vọng với worst-case**, nhất là ở randomized/backtracking có pruning.
7. **Quên rằng số phép toán trên BigInteger nhiều bit không luôn O(1)**.
8. **Dùng vòng DP c tăng dần cho 0/1 Knapsack**, lấy một vật nhiều lần.
9. **Quên khởi tạo dp[c]=0** để biểu diễn phương án chọn rỗng.
10. **Không kiểm tra trọng lượng âm/0** trong một hợp đồng chỉ cho trọng lượng dương.
11. **Không kiểm tra capacity âm**, rồi tạo mảng hoặc chỉ số không hợp lệ.
12. **Cho rằng Subset Sum DP 0..S hỗ trợ số âm**, dù thiếu trạng thái âm.
13. **Tính tổng giá trị long bị overflow mà không phát hiện**, khiến đáp án sai.
14. **Không xét memory O(W)** dù thời gian DP có vẻ phù hợp.
15. **Coi một giới hạn RAM demo là bản chất NP-hard của bài toán**.
16. **Cho rằng bài strongly NP-hard có pseudo-poly algorithm thông thường mà không có hệ quả gì**, bỏ qua điều kiện P≠NP.
17. **Cho rằng bài có pseudo-poly algorithm chắc chắn thuộc P**.
18. **Nhầm NP-hard của bài toán với độ phức tạp của một cài đặt cụ thể**.
19. **Đồng nhất tối ưu ba lô 0/1 với bài fractional knapsack**, áp dụng tham lam không đúng.
20. **Nhầm DP theo tổng giá trị O(nV) là đa thức theo bit**, dù V cũng là giá trị số học.
21. **Quên phân biệt PTAS và FPTAS** theo sự phụ thuộc vào 1/epsilon.
22. **Tự khẳng định có FPTAS chỉ vì một heuristic chạy nhanh**, không chứng minh tỷ lệ tối ưu.
23. **Nhầm cận O(n2ᵇ) với O(n b²)** khi W có b bit.
24. **Duyệt mặt nạ bit với n quá lớn**, khiến 2ⁿ tràn kiểu số hoặc số lượt bùng nổ.
25. **Đánh giá độ phức tạp chỉ bằng một test runtime nhỏ** và suy rộng vô điều kiện.
26. **Coi số lượng trạng thái nW là tổng số bit đầu vào**, sai về cách đo độ phức tạp.
27. **Không kiểm thử mảng rỗng, W=0, S=0 và phần tử lặp**.
28. **Không kiểm chứng DP với vét cạn trên n nhỏ**, bỏ cơ hội phát hiện lỗi hồi quy.
29. **Tối ưu bằng cách cắt ngắn W nhưng không chứng minh điều kiện**, có thể bỏ trạng thái cần thiết.
30. **Bỏ qua encoding của trọng lượng, giá trị, n và W** khi phát biểu một thuật toán có chạy đa thức hay không.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Độ dài đầu vào cho một số nguyên dương W biểu diễn nhị phân là gì?

**Đáp án:** \(\lfloor\log_2W\rfloor+1\) bit.

**Câu 2.** Vì sao O(nW) không nhất thiết là đa thức theo input bit-length?

**Đáp án:** Vì W có thể cỡ 2ᵇ khi chỉ có b bit, nên nW có thể cỡ n2ᵇ.

**Câu 3.** Ví dụ một thuật toán đa thức đơn giản?

**Đáp án:** Tìm tuyến tính trong mảng int có O(n) thời gian.

**Câu 4.** Liệt kê mọi tập con của n phần tử có bao nhiêu kết quả?

**Đáp án:** Đúng 2ⁿ tập con, vì mỗi phần tử có hai lựa chọn độc lập.

**Câu 5.** O(2ⁿ) có luôn chậm hơn O(nW) không?

**Đáp án:** Không cho mọi giới hạn thực tế; n nhỏ và W lớn có thể khiến vét cạn nhanh hơn DP theo W.

**Câu 6.** Độ phức tạp của DP theo sức chứa cho 0/1 Knapsack?

**Đáp án:** O(nW) thời gian và O(W) bộ nhớ, tức giả đa thức theo trị số W.

**Câu 7.** Tại sao cập nhật DP 0/1 từ W xuống w?

**Đáp án:** Để dp[c−w] vẫn là trạng thái từ những vật trước, tránh chọn vật hiện tại nhiều lần.

**Câu 8.** Cho vật duy nhất w=2,v=3,W=4, tối ưu 0/1 là bao nhiêu?

**Đáp án:** 3, không phải 6.

**Câu 9.** Với weight=[2,3,4,5], value=[3,4,5,8], W=7, tối ưu bao nhiêu?

**Đáp án:** 11, từ vật có trọng lượng 2 và 5.

**Câu 10.** Với bốn vật, DFS không tỉa duyệt bao nhiêu lá?

**Đáp án:** 2⁴=16 lá.

**Câu 11.** Subset Sum DP theo tổng S có độ phức tạp nào?

**Đáp án:** O(nS) thời gian và O(S) bộ nhớ, giả đa thức theo S.

**Câu 12.** Subset Sum [3,4,5] với S=9 có đáp án gì?

**Đáp án:** Có, vì 4+5=9.

**Câu 13.** Với S=0, có luôn tồn tại tập con hợp lệ không?

**Đáp án:** Có nếu cho phép tập rỗng, như hợp đồng trong bài.

**Câu 14.** Đâu là một ví dụ strongly NP-hard nổi tiếng?

**Đáp án:** 3-Partition.

**Câu 15.** Tại sao strongly NP-hard và pseudo-polynomial algorithm thường không cùng tồn tại nếu P≠NP?

**Đáp án:** Vì trên các đầu vào có giá trị số bị chặn đa thức, pseudo-poly sẽ biến thành thuật toán đa thức cho một lớp vẫn NP-hard.

**Câu 16.** FPTAS đảm bảo điều gì cho bài tối ưu hóa phù hợp?

**Đáp án:** Chất lượng xấp xỉ theo epsilon và thời gian đa thức theo cả kích thước đầu vào lẫn 1/epsilon.

**Câu 17.** Có thể gọi DP theo tổng giá trị O(nV) là đa thức tổng quát theo bit không?

**Đáp án:** Không; V là giá trị số và có thể lớn theo hàm mũ của số bit biểu diễn.

**Câu 18.** Vì sao vừa cần chứng minh vừa cần thử với brute force?

**Đáp án:** Chứng minh cho biết tính đúng và lớp độ phức tạp; oracle vét cạn trên n nhỏ giúp bắt lỗi triển khai thực tế.

**Ghi nhớ:** **Đa thức** đo theo **độ dài biểu diễn đầu vào**; **giả đa thức** đo theo **giá trị các số trong đầu vào**; **hàm mũ** như O(2ⁿ) tăng theo số quyết định/phần tử. DP Knapsack O(nW) không phải một thuật toán đa thức theo bit cho mọi W nhị phân. Chọn phương pháp bằng cách đối chiếu **n, W, S, bộ nhớ, yêu cầu chính xác và độ khó bài toán**, không chỉ nhìn một công thức Big-O.

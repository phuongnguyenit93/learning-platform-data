# Bài toán con chồng lặp và cấu trúc con tối ưu

## 1. Hai tính chất nền tảng của quy hoạch động

**Quy hoạch động (dynamic programming, DP)** giải bài toán lớn bằng cách xác định những **trạng thái bài toán con**, biểu diễn mối quan hệ giữa chúng, rồi **lưu lại kết quả** để không giải đi giải lại cùng một trạng thái. Hai khái niệm thường đi cùng DP là:

1. **Bài toán con chồng lặp (overlapping subproblems):** nhiều nhánh tính toán cùng cần kết quả của **một trạng thái con giống hệt nhau**. Nếu không lưu kết quả, trạng thái đó bị tính lặp.
2. **Cấu trúc con tối ưu (optimal substructure):** đối với bài toán tối ưu hóa, có thể xây dựng giá trị/lời giải tối ưu của trạng thái lớn từ **giá trị/lời giải tối ưu** của những trạng thái nhỏ hơn, theo một phép chuyển đã được chứng minh đúng.

Hai tính chất **khác vai trò**:
- Chồng lặp là lý do việc **ghi nhớ/tái sử dụng kết quả** có lợi về thời gian.
- Cấu trúc con tối ưu giải thích vì sao có thể **lập truy hồi tối ưu** từ những bài toán con thay vì phải duyệt mọi lời giải toàn cục.
- Chỉ có “nhiều bài toán con” chưa chứng minh chồng lặp. Chỉ có “cấu trúc con tối ưu” chưa suy ra một **quy tắc tham lam** nào là đúng.

DP cũng được dùng cho bài toán **đếm** và **quyết định**, không chỉ tối ưu hóa. Khi đó điều cốt lõi là tồn tại **truy hồi đúng và các trạng thái dùng lại được**; không nhất thiết gọi đó là cấu trúc con “tối ưu”. Fibonacci là ví dụ kinh điển của **chồng lặp và ghi nhớ**, nhưng không phải bản thân một bài toán tối ưu hóa.

## 2. Trạng thái: “cùng bài toán con” nghĩa là gì?

Một **trạng thái DP** phải mô tả đầy đủ những thông tin quyết định đáp án phần còn lại. Hai lời gọi là **cùng trạng thái** khi mọi thông tin có thể ảnh hưởng tới các phương án hợp lệ và kết quả của chúng đều giống nhau.

Ví dụ:
- Fibonacci: trạng thái là số n; hai lần gọi F(5) thực sự hỏi cùng một giá trị.
- 0/1 knapsack: trạng thái có thể là **(i, c)**, tức được dùng các món trong tiền tố i món đầu và còn sức chứa c. Hai tình huống có cùng c nhưng khác i **không** nhất thiết là cùng bài toán con.
- Longest common subsequence (LCS): trạng thái **(i, j)** cho độ dài LCS của hai tiền tố/suffix có ranh giới i và j. Cùng i nhưng khác j chưa đủ để xác định đáp án.

Trạng thái quá ít thông tin sẽ khiến ta **trộn nhầm** những bài toán con khác nhau; cache khi đó trả đáp án cho sai ngữ cảnh. Trạng thái thừa thông tin vẫn có thể đúng nhưng làm phình số trạng thái, khó chứng minh và tốn bộ nhớ.

Hãy đặt hai câu hỏi:
- Nếu biết chỉ các tham số trạng thái này, có quyết định đúng mọi bước tiếp theo không?
- Khi gặp lại bộ tham số đó ở một nhánh tính toán khác, có chắc tập lựa chọn còn lại và kết quả tối ưu/đếm được **giống hệt** không?

Nếu một câu trả lời là không, cần thiết kế lại trạng thái trước khi viết công thức DP.

## 3. Chồng lặp qua cây đệ quy Fibonacci

Dãy Fibonacci có:

\[
F(0)=0,\quad F(1)=1,\quad F(n)=F(n-1)+F(n-2)\quad(n\ge2).
\]

Một hàm đệ quy trực tiếp gọi F(n−1) và F(n−2), rồi mỗi lời gọi lại tạo thêm hai nhánh. Với F(5), cây lời gọi có dạng:

~~~text
F(5)
├─ F(4)
│  ├─ F(3)
│  │  ├─ F(2)
│  │  └─ F(1)
│  └─ F(2)
└─ F(3)
   ├─ F(2)
   └─ F(1)
~~~

Trong cây đã lược bớt lá này, F(3) xuất hiện hai lần và F(2) xuất hiện nhiều lần. Chúng là **trạng thái giống hệt nhau** chứ không chỉ có kích thước giống nhau.

**Cây lời gọi** có thể chứa rất nhiều nút lặp, còn **đồ thị phụ thuộc trạng thái** chỉ có các đỉnh F(0), F(1), ..., F(n): tổng cộng n+1 trạng thái. Với n=10:
- Đệ quy thuần tính F(10)=55 với **177 lần gọi** khi đếm cả lời gọi cơ sở.
- Memoization vẫn trả F(10)=55, nhưng chỉ có **11 trạng thái duy nhất**, mỗi trạng thái tính mới tối đa một lần; số lần đi vào hàm trong ví dụ Java dưới đây là **19** do một số lời gọi trả về ngay từ cache.

Độ phức tạp:
- Đệ quy thuần: \(\Theta(\varphi^n)\) thời gian, với \(\varphi=(1+\sqrt 5)/2\), và O(n) stack. Đây là bậc tăng trưởng của số lời gọi trong công thức chuẩn.
- Memoization: **O(n)** thời gian, O(n) cache và O(n) stack.
- Tabulation: **O(n)** thời gian, O(n) mảng; chỉ giữ hai số trước còn cho O(1) bộ nhớ phụ trợ nếu không cần truy vết dãy.

**Lưu ý:** F(n) là công thức xác định giá trị, không yêu cầu tìm nghiệm “tốt nhất”. Ví dụ này chứng minh lợi ích của việc **loại tính toán lặp**, chứ không tự chứng minh cấu trúc con tối ưu cho một bài toán tối ưu hóa.

## 4. Chồng lặp khác với chia để trị thông thường

Nhiều thuật toán chia để trị cũng có cây đệ quy, nhưng các phần tử của cây không nhất thiết là các trạng thái lặp lại.

**Merge sort** trên một mảng phân tách đoạn [l, r) thành hai đoạn không giao nhau, rồi sắp từng đoạn và trộn. Mỗi **đoạn vị trí cụ thể** xuất hiện một lần trong cây đệ quy chuẩn; hai đoạn có cùng số phần tử nhưng khác vị trí **không phải cùng trạng thái**. Nếu cache theo độ dài đoạn, kết quả sắp của đoạn này không thể dùng cho đoạn khác chỉ vì cả hai dài 5.

**Fibonacci đệ quy** lại gọi đúng cùng F(k) từ nhiều nhánh khác nhau, nên cache theo k là hợp lệ.

| Thuật toán/vấn đề | Có phân rã thành bài toán con? | Có cùng trạng thái bị yêu cầu lặp lại? | Vai trò lưu cache |
|---|---|---|---|
| Fibonacci đệ quy thuần | Có | Có rất nhiều | Từ thời gian mũ xuống tuyến tính |
| Merge sort trên các đoạn vị trí khác nhau | Có | Thường không trong cây chuẩn | Memoization các đoạn thường không giúp |
| 0/1 knapsack theo (i,c) | Có | Có thể có nhiều đường đến cùng (i,c) | Cache tránh khám phá lại trạng thái |
| LCS theo (i,j) | Có | Nhiều nhánh có thể gặp lại (i,j) | DP giảm từ tìm kiếm lặp xuống O(mn) |
| Binary search | Có, thường chỉ đi một nhánh | Không có lời gọi con lặp trong một lượt chuẩn | Memoization thường không có ích |

**Không suy luận từ hình dạng cây:** có hai lời gọi cùng kích thước không có nghĩa dữ liệu/ngữ cảnh giống nhau. Cần so **khóa trạng thái**.

## 5. Cấu trúc con tối ưu: điều cần chứng minh

Với một bài toán **tối ưu hóa**, nói có cấu trúc con tối ưu khi giá trị tối ưu của một trạng thái có thể được xác định bằng những giá trị tối ưu của các trạng thái nhỏ hơn, sau khi đã phân loại đầy đủ các lựa chọn hợp lệ ở bước hiện tại.

Một công thức điển hình:

\[
OPT(s)=\operatorname{best}_{a\in Actions(s)}
\bigl(cost(s,a)+OPT(next(s,a))\bigr),
\]

với best là min hoặc max tùy mục tiêu. Công thức chỉ hợp lệ nếu:
1. **Bao phủ lựa chọn:** mọi lời giải khả thi thuộc ít nhất một trường hợp a được xét.
2. **Phần còn lại được mô tả đầy đủ:** next(s,a) chứa tất cả thông tin ảnh hưởng tới các lựa chọn tiếp theo.
3. **Thay thế tối ưu hợp lệ:** nếu một lời giải toàn cục chọn a nhưng dùng lời giải con chưa tối ưu, ta có thể thay phần còn lại bằng lời giải con tối ưu **mà không phá các ràng buộc khác**.
4. **Cơ sở đúng và truy hồi kết thúc:** mỗi bước dựa vào trạng thái nhỏ hơn hoặc một thứ tự phụ thuộc không có chu trình.

Phần 3 là cốt lõi của **lập luận cắt–dán (cut-and-paste)**: giả sử nghiệm toàn cục tối ưu có một nghiệm con không tối ưu; thay nghiệm con bằng nghiệm tốt hơn sẽ cải thiện nghiệm toàn cục, mâu thuẫn với tối ưu — **nhưng chỉ được phép thay** nếu các tương tác với phần ngoài đã được mã hóa trong trạng thái.

Vì vậy, “cấu trúc con tối ưu” không nên phát biểu mơ hồ cho mọi cách chọn trạng thái. Cùng một bài toán có thể **không** có truy hồi đúng với trạng thái quá nghèo thông tin, nhưng có truy hồi đúng sau khi đưa đủ điều kiện vào trạng thái.

### Không đồng nghĩa với tham lam

Cấu trúc con tối ưu cho phép ta so sánh các phương án bằng công thức min/max. Nó **không** bảo đảm rằng lựa chọn có lợi nhất ngay lập tức sẽ dẫn tới tối ưu. Bài 0/1 knapsack ở mục tiếp theo có cấu trúc con tối ưu và dùng DP, nhưng chọn món theo tỷ lệ giá trị/khối lượng giảm dần **không luôn tối ưu**.

Muốn dùng greedy cần chứng minh một **lựa chọn cụ thể có thể cố định** trong một nghiệm tối ưu. DP thường giữ lại **nhiều lựa chọn tại mỗi trạng thái** và dùng truy hồi để so giá trị của chúng.

## 6. Ví dụ tối ưu hóa: 0/1 Knapsack

### 6.1. Đề bài và trạng thái

Có n món; món thứ i có khối lượng \(w_i>0\) và giá trị \(v_i\ge0\). Mỗi món chỉ được chọn **0 hoặc 1 lần**. Ba lô chứa tối đa W đơn vị khối lượng. Mục tiêu tối đa tổng giá trị.

Chọn trạng thái:

\[
DP[i][c]=\text{giá trị tối đa khi chỉ xét i món đầu, sức chứa c}.
\]

Miền: \(0\le i\le n\), \(0\le c\le W\). Quyết định thứ i chỉ cần biết những món trước nó và dung lượng còn lại; không cần lưu nguyên tập món đã chọn vì mỗi món được xét đúng một lần theo chỉ số i.

### 6.2. Công thức và cơ sở

Không có món hoặc sức chứa bằng 0 (do mọi \(w_i>0\)) thì giá trị tối đa bằng 0:

\[
DP[0][c]=0,\qquad DP[i][0]=0.
\]

Với món i (đánh số từ 1 trong công thức), có đúng hai nhóm lời giải:
- **Không lấy** món i: giá trị tốt nhất là \(DP[i-1][c]\).
- **Lấy** món i (chỉ khi \(w_i\le c\)): giá trị tốt nhất là \(v_i+DP[i-1][c-w_i]\).

Do đó:

\[
DP[i][c]=
\begin{cases}
DP[i-1][c], & w_i>c,\\
\max\bigl(DP[i-1][c],\, v_i+DP[i-1][c-w_i]\bigr),& w_i\le c.
\end{cases}
\]

### 6.3. Vì sao có cấu trúc con tối ưu?

Xét nghiệm tối ưu cho DP[i][c].
- Nếu không lấy món i, nghiệm đó chỉ dùng i−1 món đầu. Nếu phần này không tối ưu cho DP[i−1][c], có thể thay bằng phần tối ưu và tăng giá trị toàn cục — mâu thuẫn.
- Nếu có lấy món i, bỏ món đó đi ta còn một tập từ i−1 món đầu, trọng lượng không quá c−w_i. Nếu tập còn lại không tối ưu cho DP[i−1][c−w_i], có thể thay nó bằng tập tốt hơn rồi thêm lại món i, vẫn hợp lệ vì sức chứa còn đủ. Mâu thuẫn.

Hai trường hợp bao phủ mọi nghiệm; lấy max cho giá trị tối ưu. **Điểm then chốt:** phần còn lại của bài toán đã được xác định đầy đủ bằng (i−1, dung lượng mới).

### 6.4. Vì sao các bài toán con có thể chồng lặp?

Một nhánh truy hồi chọn “lấy” hoặc “không lấy” từng món. Các chuỗi lựa chọn khác nhau có thể dẫn tới cùng cặp **(i,c)**, nhất là khi có nhiều món cùng trọng lượng hoặc nhiều cách đạt một tổng khối lượng. Nếu đệ quy không nhớ kết quả, ta tính lại trạng thái (i,c) dù câu hỏi tối ưu của trạng thái đó không đổi.

Có tối đa \((n+1)(W+1)\) trạng thái, mỗi trạng thái dùng O(1) phép chuyển. Với mảng DP hai chiều, thời gian **O(nW)** và bộ nhớ **O(nW)**; nếu chỉ cần giá trị tối ưu, có thể dùng mảng một chiều O(W) bộ nhớ.

**Quan trọng về độ phức tạp:** O(nW) là **giả đa thức (pseudo-polynomial)** nếu W được biểu diễn bằng số nhị phân: độ dài biểu diễn W chỉ là O(log W), nên O(nW) không phải thời gian đa thức theo **số bit của đầu vào** khi W có thể rất lớn.

### 6.5. Bảng ví dụ

Cho các món đánh số 0..3:

| Chỉ số | Khối lượng | Giá trị |
|---|---:|---:|
| 0 | 2 | 3 |
| 1 | 3 | 4 |
| 2 | 4 | 5 |
| 3 | 5 | 8 |

Dung lượng W=8. Kết quả tối ưu là **12**, đạt được khi chọn món **1 và 3** (khối lượng 3+5=8, giá trị 4+8=12).

Nếu sắp theo mật độ giá trị trên khối lượng rồi tham lam lấy nguyên món, không có chứng minh đúng cho 0/1 knapsack. Ví dụ kinh điển dung lượng 50, các món (10,60), (20,100), (30,120): tham lam mật độ lấy hai món đầu cho 160, còn chọn hai món sau cho 220. DP đúng vì nó xét cả hai trường hợp lấy/bỏ ở mỗi trạng thái.

### 6.6. Tối ưu bộ nhớ phải giữ đúng hướng cập nhật

Với công thức 0/1 knapsack, bảng hai chiều dùng **hàng i−1** để tính hàng i. Nếu nén còn một mảng DP[c], phải duyệt c **giảm dần** từ W xuống w_i để giá trị DP[c−w_i] vẫn thuộc trạng thái trước khi xét món i. Duyệt tăng dần có thể vô tình tái sử dụng chính món i nhiều lần, biến bài toán thành **unbounded knapsack**.

Không thực hiện tối ưu bộ nhớ trước khi hiểu rõ phụ thuộc của các trạng thái. Nếu cần truy vết các món đã chọn, bảng đầy đủ hoặc dữ liệu quyết định riêng thường dễ triển khai đúng hơn.

## 7. Ví dụ tối ưu hóa thứ hai: Longest Common Subsequence

Cho hai chuỗi A dài m và B dài n. **Longest common subsequence (LCS)** là dãy ký tự chung dài nhất không cần liên tiếp nhưng phải giữ thứ tự. LCS khác **longest common substring**, vốn đòi hỏi ký tự liên tiếp.

Chọn:

\[
DP[i][j]=\text{độ dài LCS của A[0..i) và B[0..j)}.
\]

Cơ sở: nếu một tiền tố rỗng, LCS có độ dài 0.

\[
DP[0][j]=DP[i][0]=0.
\]

Với \(i,j>0\):
- Nếu \(A[i-1]=B[j-1]\), có một LCS tối ưu kết thúc bằng ký tự chung đó; bỏ ký tự cuối đi cho bài toán hai tiền tố ngắn hơn:

\[
DP[i][j]=1+DP[i-1][j-1].
\]

- Nếu hai ký tự cuối khác nhau, một LCS chung không thể dùng **cả hai** ký tự cuối làm cùng một bước khớp. Ít nhất một trong hai ký tự cuối không được dùng, nên:

\[
DP[i][j]=\max(DP[i-1][j],DP[i][j-1]).
\]

**Chồng lặp:** khi ký tự cuối khác nhau, hai nhánh truy hồi lại tách tiếp, và nhiều đường đi có thể chạm tới cùng trạng thái (i,j). Memoization hoặc bảng hai chiều chỉ tính mỗi cặp chỉ số một lần.

**Cấu trúc con tối ưu:** công thức bao phủ các trường hợp tương ứng với lựa chọn dùng/bỏ ký tự cuối, và phần đuôi của LCS tối ưu phải có độ dài tối ưu trong trạng thái còn lại; nếu không, có thể thay bằng subsequence dài hơn mà vẫn giữ thứ tự hợp lệ.

Số trạng thái là \((m+1)(n+1)\), mỗi trạng thái tính O(1), nên thời gian O(mn), bộ nhớ O(mn) nếu lưu toàn bảng. Chỉ lấy độ dài có thể giảm bộ nhớ xuống O(min(m,n)) bằng hai hàng hoặc một hàng cẩn thận. Nếu cần **khôi phục chuỗi LCS cụ thể**, phải giữ đủ thông tin truy vết hoặc dùng chiến lược chia để trị thích hợp.

Ví dụ A="ABCDGH", B="AEDFHR" có một LCS là "ADH", độ dài 3. Lời giải LCS có thể **không duy nhất**; công thức DP xác định độ dài tối ưu, còn truy vết cần quy tắc khi có nhiều lựa chọn đạt cùng độ dài.

## 8. Memoization và tabulation: cùng trạng thái, hai lịch tính

### 8.1. Top-down memoization

Viết truy hồi giống định nghĩa toán học và tạo cache theo trạng thái:
1. Nếu trạng thái đã tính, trả về cache.
2. Nếu là trạng thái cơ sở, trả đáp án cơ sở.
3. Tính từ các trạng thái con, lưu kết quả, rồi trả kết quả.

Với Fibonacci, cache theo n. Với knapsack, cache theo (i,c). Với LCS, cache theo (i,j). Nếu một trạng thái có **giá trị hợp lệ bằng 0**, không dùng 0 để biểu thị “chưa tính” trừ khi có mảng boolean riêng; nếu không, các trạng thái có đáp án 0 sẽ bị tính lặp.

Ưu điểm: code sát công thức, chỉ tính các trạng thái thực sự được yêu cầu. Hạn chế: lời gọi sâu có thể gây StackOverflowError; recursion và cache tra cứu cũng có overhead.

### 8.2. Bottom-up tabulation

Dựng một bảng và tính theo thứ tự để **mọi trạng thái phụ thuộc đã có kết quả** trước khi dùng:
- Fibonacci: F(0), F(1), F(2), ..., F(n).
- Knapsack: i từ 1 tới n, với mỗi i tính mọi dung lượng c.
- LCS: i từ 1 tới m và j từ 1 tới n; mỗi ô dựa vào ô trên, trái và chéo trên trái.

Ưu điểm: không cần call stack đệ quy; dễ tối ưu bộ nhớ theo lớp phụ thuộc và tái lập các phép tính. Hạn chế: có thể tính nhiều trạng thái không thực sự cần; dễ sai nếu duyệt sai thứ tự.

**Đồ thị phụ thuộc:** mỗi trạng thái là một đỉnh, có cạnh từ trạng thái s tới các trạng thái con mà s cần. Nếu đồ thị không có chu trình, có thể tính bottom-up theo **thứ tự topo ngược với chiều phụ thuộc** (các tiền nhiệm cần thiết được tính trước). Top-down memoization và bottom-up tabulation đều tính trên cùng đồ thị trạng thái, chỉ khác **thứ tự thực hiện và cách giữ kết quả**.

Nếu công thức phụ thuộc theo vòng mà không có quy tắc xử lý vòng, memoization đệ quy đơn thuần có thể chạy vô hạn. Khi đó phải xem lại mô hình trạng thái hoặc dùng thuật toán giải quan hệ tuần hoàn thích hợp; không được giả định mọi công thức có trạng thái đều tự tạo DP khả thi.

## 9. Ví dụ Java 17+ chạy độc lập

Chương trình có ba ví dụ để phân biệt rõ:
1. Fibonacci: **chồng lặp** và lợi ích memoization; cả hai cách cho cùng giá trị, nhưng số lần gọi khác nhau.
2. 0/1 knapsack: **cấu trúc con tối ưu** với hai trường hợp lấy/bỏ món; bảng bottom-up và truy vết chỉ số món được chọn.
3. LCS: **cấu trúc con tối ưu và chồng lặp** trên cặp tiền tố (i,j).

Lưu thành tệp **DpPropertiesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class DpPropertiesDemo {
    private DpPropertiesDemo() {
    }

    private static long fibNaive(int n, long[] calls) {
        calls[0]++;
        if (n <= 1) {
            return n;
        }
        return fibNaive(n - 1, calls) + fibNaive(n - 2, calls);
    }

    private static long fibMemo(int n, long[] memo, long[] calls) {
        calls[0]++;
        if (memo[n] != -1L) {
            return memo[n];
        }
        if (n <= 1) {
            memo[n] = n;
            return n;
        }
        memo[n] = fibMemo(n - 1, memo, calls)
                + fibMemo(n - 2, memo, calls);
        return memo[n];
    }

    record KnapsackResult(long bestValue, List<Integer> chosenIndices) {
    }

    private static KnapsackResult knapsack(
            int[] weights, int[] values, int capacity) {
        if (weights == null || values == null
                || weights.length != values.length || capacity < 0) {
            throw new IllegalArgumentException("Invalid knapsack data");
        }

        int n = weights.length;
        for (int i = 0; i < n; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
        }

        long[][] dp = new long[n + 1][capacity + 1];
        for (int i = 1; i <= n; i++) {
            for (int c = 0; c <= capacity; c++) {
                long skip = dp[i - 1][c];
                long best = skip;

                if (weights[i - 1] <= c) {
                    long take = Math.addExact(
                            dp[i - 1][c - weights[i - 1]],
                            (long) values[i - 1]);
                    best = Math.max(best, take);
                }
                dp[i][c] = best;
            }
        }

        List<Integer> chosen = new ArrayList<>();
        int c = capacity;
        for (int i = n; i >= 1; i--) {
            if (dp[i][c] != dp[i - 1][c]) {
                chosen.add(i - 1);
                c -= weights[i - 1];
            }
        }
        Collections.reverse(chosen);
        return new KnapsackResult(dp[n][capacity], chosen);
    }

    private static int lcsLength(String a, String b) {
        if (a == null || b == null) {
            throw new IllegalArgumentException("Null string");
        }

        int[][] dp = new int[a.length() + 1][b.length() + 1];
        for (int i = 1; i <= a.length(); i++) {
            for (int j = 1; j <= b.length(); j++) {
                if (a.charAt(i - 1) == b.charAt(j - 1)) {
                    dp[i][j] = 1 + dp[i - 1][j - 1];
                } else {
                    dp[i][j] = Math.max(dp[i - 1][j],
                            dp[i][j - 1]);
                }
            }
        }
        return dp[a.length()][b.length()];
    }

    public static void main(String[] args) {
        int n = 10; // F(n) còn vừa kiểu long khi 0 <= n <= 92.
        long[] naiveCalls = {0L};
        long naive = fibNaive(n, naiveCalls);

        long[] memo = new long[n + 1];
        Arrays.fill(memo, -1L);
        long[] memoCalls = {0L};
        long cached = fibMemo(n, memo, memoCalls);

        System.out.println("Fibonacci naive n=10: "
                + naive + ", calls=" + naiveCalls[0]);
        System.out.println("Fibonacci memo n=10: "
                + cached + ", calls=" + memoCalls[0]);

        KnapsackResult best = knapsack(
                new int[] {2, 3, 4, 5},
                new int[] {3, 4, 5, 8},
                8);
        System.out.println("Knapsack maximum: " + best.bestValue());
        System.out.println("Knapsack picks (0-based): "
                + best.chosenIndices());

        System.out.println("LCS length: "
                + lcsLength("ABCDGH", "AEDFHR"));
        System.out.println("Knapsack empty: "
                + knapsack(new int[] {}, new int[] {}, 8).bestValue());
        System.out.println("LCS with empty: "
                + lcsLength("", "ABC"));
    }
}
~~~

Biên dịch và chạy với **JDK 17** hoặc mới hơn:

~~~bash
javac DpPropertiesDemo.java
java DpPropertiesDemo
~~~

**Stdout chính xác:**

~~~text
Fibonacci naive n=10: 55, calls=177
Fibonacci memo n=10: 55, calls=19
Knapsack maximum: 12
Knapsack picks (0-based): [1, 3]
LCS length: 3
Knapsack empty: 0
LCS with empty: 0
~~~

**Diễn giải và giới hạn mã:**
- **Fibonacci:** mỗi lời gọi hàm tăng counter một lần. Ở memoization, một trạng thái có thể được gọi lại nhưng cache ngăn tính lại. Mảng memo khởi tạo bằng −1 vì mọi giá trị F(n) trong phạm vi ví dụ đều không âm; nếu dùng cache cho bài toán có đáp án −1 hợp lệ, phải dùng cơ chế đánh dấu đã tính riêng.
- **Số Fibonacci tràn kiểu:** long Java chỉ biểu diễn F(n) chính xác đến n=92. Với n lớn hơn, dùng BigInteger hoặc cơ chế kiểm tra tràn. Hai hàm đệ quy trên chỉ minh họa với n=10; khi tái sử dụng phải kiểm tra n không âm và giới hạn kiểu số.
- **Knapsack:** Math.addExact làm lỗi tràn long được báo rõ thay vì âm thầm tạo đáp án sai. Bộ nhớ bảng là O(nW); giá trị 0 hợp lệ và không bị nhầm với “chưa tính” vì đây là **bottom-up**. Khi truy vết, nếu dp[i][c]==dp[i−1][c], bản triển khai chọn **bỏ** món i; vì vậy kết quả có một quy tắc tie rõ ràng.
- **LCS:** ví dụ dùng chữ cái ASCII. Hàm charAt hoạt động theo đơn vị **UTF-16 char**, không tự xử lý ký tự ghép hoặc grapheme Unicode phức tạp; nếu cần LCS theo code point hoặc grapheme, phải chuyển đổi cách tách chuỗi cho đúng định nghĩa bài toán.
- **Trường hợp rỗng:** không có món cho kết quả knapsack 0; LCS với chuỗi rỗng cho 0. Mẫu còn hạn chế ở số trạng thái vừa bộ nhớ, không tối ưu cho W hoặc chuỗi cực lớn.

## 10. Khi nào nên dùng DP, và phân tích đúng chi phí

Một quy trình đánh giá DP:

**Bước 1 — Xác định kết quả của một trạng thái.** Viết định nghĩa có ý nghĩa nghiệp vụ: DP[i][c] là tối đa từ i món đầu với dung lượng c, không chỉ “dp có hai chiều”.

**Bước 2 — Chọn thông tin đủ để ra quyết định.** Các phương án tương lai và ràng buộc phải chỉ phụ thuộc trạng thái đó. Nếu còn phụ thuộc vào lịch sử chưa được lưu, trạng thái không đủ.

**Bước 3 — Tách tất cả lựa chọn hợp lệ.** Lấy/bỏ, khớp/không khớp, chọn bước tiếp theo... Không bỏ sót và không thêm lựa chọn không khả thi.

**Bước 4 — Chứng minh phép chuyển.** Với tối ưu hóa, chứng minh cấu trúc con tối ưu: một nghiệm con không tối ưu có thể bị thay bằng nghiệm tốt hơn mà không làm hỏng nghiệm toàn cục. Với bài toán đếm, chứng minh các trường hợp không bị đếm trùng và bao phủ đủ.

**Bước 5 — Xác định cơ sở và thứ tự phụ thuộc.** Bảng phải tính những trạng thái nhỏ hơn trước; memo phải có điều kiện dừng và không bị phụ thuộc vòng.

**Bước 6 — Đếm trạng thái và số chuyển.** Nếu có S trạng thái và mỗi trạng thái xét nhiều nhất A chuyển, thời gian thường là O(S·A) cộng chi phí tạo dữ liệu/truy vết; bộ nhớ theo kích thước cache hoặc bảng. Không được chỉ nói O(n) chỉ vì có n dòng nếu mỗi dòng phải duyệt W dung lượng.

**Bước 7 — Chọn top-down hay bottom-up.** Nếu chỉ dùng ít trạng thái và công thức rẽ nhánh thưa, memoization có thể tiết kiệm. Nếu gần như tất cả trạng thái đều cần, tabulation thường rõ ràng và tránh stack sâu.

**Bước 8 — Tối ưu sau khi đã đúng.** Nén bảng chỉ khi đã hiểu phụ thuộc; chọn đúng chiều duyệt khi dùng một hàng. Nếu cần xây dựng **nghiệm cụ thể**, giữ đủ thông tin để truy vết, không chỉ trả giá trị tối ưu.

### So sánh theo ví dụ

| Bài toán | Trạng thái | Chồng lặp | Truy hồi/đích | Thời gian DP điển hình |
|---|---|---|---|---|
| Fibonacci | n | Có, nhiều lời gọi cùng F(k) | Cộng hai giá trị trước, không tối ưu hóa | O(n) |
| 0/1 knapsack | (i,c) | Các nhánh có thể gặp lại trạng thái | Max của lấy và bỏ món | O(nW) |
| LCS | (i,j) | Các nhánh có thể gặp lại cặp chỉ số | Max của hai cách bỏ ký tự hoặc nối ký tự khớp | O(mn) |
| Đếm đường đi lưới chỉ đi xuống/phải | (r,c) | Các đường có thể đến cùng ô | Tổng số cách đến từ trên và trái | O(RC) |
| Merge sort chuẩn trên đoạn vị trí | (l,r) | Thường không gặp lại cùng đoạn | Chia đôi, sắp hai nửa, trộn | O(n log n), không cần memo |

Đếm đường đi trên lưới là ví dụ DP **không tối ưu hóa**. Nếu không có vật cản, có thể đặt ways[r][c] bằng tổng số đường đi tới ô trên và ô trái (xử lý mép bảng và điều kiện khởi tạo). Việc cộng các đường đi khác nhau chỉ đúng khi hai nhóm đường có **bước cuối khác nhau**, giúp tránh đếm trùng. Nếu có vật cản, cách chuyển phải loại ô bị chặn.

## 11. Những lỗi phổ biến

1. **Thấy đệ quy là gọi DP:** đệ quy chỉ là cách điều khiển luồng; nếu không cache và không có bảng, việc tính lặp vẫn xảy ra.
2. **Nhầm hai lời gọi cùng kích thước là một trạng thái:** hai đoạn mảng khác vị trí không có cùng dữ liệu; cache theo kích thước sẽ sai.
3. **Lược bỏ ràng buộc khỏi trạng thái:** ví dụ bài đi qua các đỉnh **không được lặp**, đáp án từ đỉnh v còn phụ thuộc những đỉnh đã thăm. Chỉ lưu trạng thái v có thể trộn nhầm các tập lựa chọn khác nhau. Một thiết kế đúng có thể cần (v, visitedSet), nhưng số trạng thái có thể tăng theo hàm mũ.
4. **Chỉ nói cấu trúc con tối ưu mà không chứng minh phép thay:** phải giải thích tại sao nghiệm con tốt hơn có thể thay vào nghiệm lớn mà vẫn khả thi.
5. **Nhầm cấu trúc con tối ưu với quyền chọn tham lam:** 0/1 knapsack có DP đúng nhưng tham lam theo mật độ thất bại.
6. **Dùng 0 làm dấu chưa tính khi 0 là đáp án hợp lệ:** làm tính lại trạng thái, thậm chí xử lý sai trong các biến thể có logic đặc biệt. Dùng visited/seen riêng hoặc sentinel nằm ngoài miền giá trị.
7. **Bỏ điều kiện dừng:** memoized recursion có thể đệ quy vô hạn hoặc truy cập mảng âm.
8. **Tính bảng sai thứ tự:** dùng một trạng thái chưa được tính hoặc dùng giá trị của vòng xét món hiện tại thay vì vòng trước.
9. **Nén knapsack 0/1 nhưng duyệt sức chứa tăng:** có thể dùng một món nhiều lần, làm đổi bài toán.
10. **Không kiểm tra overflow:** Fibonacci lớn vượt long; số cách đi có thể vượt miền int/long; tối ưu hóa giá trị cộng có thể tràn.
11. **Chỉ đếm trạng thái, quên số chuyển:** có O(n²) trạng thái nhưng mỗi trạng thái xét O(n) lựa chọn sẽ tạo O(n³) thời gian.
12. **Nhầm giả đa thức với đa thức theo kích thước input:** O(nW) của knapsack không phải O(poly(n, log W)) khi W rất lớn.
13. **Quên truy vết:** nếu đề yêu cầu danh sách món/chuỗi LCS, chỉ tính độ dài/giá trị chưa hoàn thành đầu ra.
14. **Cho rằng có overlap là đủ để DP đúng:** cache chỉ giúp tính nhanh **công thức đang dùng**; công thức sai dù lưu đúng cũng tạo kết quả sai.
15. **Không phân biệt min/max/đếm:** tối ưu dùng phép max hoặc min; đếm dùng cộng nhưng phải chứng minh các trường hợp rời nhau.

## 12. Kiểm thử và phản ví dụ

Nên kiểm tra:
- **Trạng thái cơ sở:** F(0)=0, F(1)=1; knapsack 0 món/0 sức chứa; LCS với chuỗi rỗng.
- **Giá trị nhỏ đã biết:** F(10)=55, ba lô ví dụ có tối ưu 12, LCS("ABCDGH","AEDFHR")=3.
- **Một món không vừa túi:** knapsack không lấy món, giá trị 0.
- **Hai món cùng khối lượng:** tránh dùng một món hai lần khi nén bảng.
- **Nhiều lời giải đồng tối ưu:** kiểm tra giá trị và tính khả thi của lời giải truy vết, không khăng khăng phải chọn cùng một tập chỉ số.
- **Chuỗi có nhiều ký tự trùng:** LCS không phải chỉ là giao tập ký tự; thứ tự của chuỗi là ràng buộc.
- **Nhánh đệ quy trùng:** đếm số trạng thái thực sự tính mới và số lần gọi cache hit để xác nhận memoization có lợi.
- **Đối chiếu brute force với n nhỏ:** liệt kê mọi tập con món hàng (2^n), kiểm tra tổng khối lượng ≤ W và lấy giá trị cao nhất; đối chiếu bảng DP. Với LCS nhỏ, liệt kê subsequence của một chuỗi và kiểm tra có là subsequence của chuỗi kia không.

Đừng coi kết quả trùng nhau ở vài bộ test là **chứng minh** DP đúng. Kiểm thử giúp phát hiện lỗi lập trình; chứng minh tính đúng cần dựa trên **định nghĩa trạng thái, đầy đủ lựa chọn và phép thay thế tối ưu**.

### Phản ví dụ của trạng thái thiếu thông tin

Xét bài **đường đi đơn** (không lặp đỉnh) trên đồ thị. Khi đang ở đỉnh v, nếu trong lịch sử đã thăm đỉnh u thì không thể chọn u ở bước tiếp theo; nếu chưa thăm thì có thể. Vì vậy hai lượt đến cùng v nhưng có tập đỉnh đã thăm khác nhau **không phải cùng trạng thái** của bài toán. Cache chỉ theo v có thể cho lời giải dùng lại đỉnh bị cấm, dù số lượng đỉnh được lưu trong cache rất ít.

Điều này không chứng minh “bài toán không dùng được DP”; nó chứng minh **trạng thái chỉ chứa v không đủ**. Nếu dùng (v, visitedSet), công thức có thể hợp lệ nhưng có thể cần tới O(V·2^V) trạng thái. Đây là đánh đổi giữa **đúng đắn của trạng thái** và **số lượng trạng thái**.

## 13. Bài tập tự kiểm tra

**Câu 1.** F(8) có cấu trúc con chồng lặp không? Nếu có thì overlap là gì?

**Đáp án:** Có. Trong cây đệ quy thuần, cùng một F(k) có thể được gọi từ nhiều nhánh. Cache theo đúng k cho phép tính mỗi F(k) tối đa một lần. Fibonacci không phải một bài toán tối ưu hóa nên chỉ riêng ví dụ này không minh họa định nghĩa cấu trúc con **tối ưu**.

**Câu 2.** Vì sao hai lời gọi merge sort trên hai đoạn có cùng độ dài 4 không được tự coi là một trạng thái?

**Đáp án:** Chúng chứa các vị trí và phần tử khác nhau; đáp án sắp xếp của hai đoạn có thể khác nhau. Kích thước giống nhau chưa phải dữ liệu/ngữ cảnh giống nhau.

**Câu 3.** Trong 0/1 knapsack, tại sao không thể lấy giá trị của trạng thái DP[i][c-w_i] khi đang chọn món i?

**Đáp án:** Vì DP[i][...] có thể đã dùng món i; cộng thêm món i sẽ dùng món ấy **hai lần**. Phải dùng trạng thái DP[i−1][c−w_i], chỉ xét các món trước.

**Câu 4.** Cấu trúc con tối ưu có chứng minh chọn món có mật độ cao nhất là đúng trong 0/1 knapsack không?

**Đáp án:** Không. Nó cho phép lập max giữa lấy và bỏ món; chưa chứng minh cố định lựa chọn nào là an toàn. Phản ví dụ dung lượng 50 cho thấy chọn theo mật độ có thể cho 160 thay vì 220.

**Câu 5.** Khi nào memoization thường tránh tính nhiều trạng thái hơn tabulation?

**Đáp án:** Khi truy vấn đầu chỉ dẫn tới một phần nhỏ đồ thị trạng thái và nhiều trạng thái khác không được đụng tới. Memoization chỉ tính trạng thái được gọi, còn tabulation thường điền toàn bộ bảng đã thiết kế.

**Câu 6.** Vì sao kết quả LCS của hai chuỗi có thể không duy nhất dù giá trị DP xác định?

**Đáp án:** Nhiều subsequence khác nhau có thể cùng độ dài tối đa. Công thức DP xác định **độ dài**; việc chọn một subsequence để truy vết có thể cần quy tắc tie-break.

**Câu 7.** Vì sao không dùng trạng thái chỉ là đỉnh v cho một bài tìm đường đi đơn?

**Đáp án:** Những đỉnh còn được đi phụ thuộc tập đỉnh đã thăm. Hai lần đến cùng v nhưng khác visitedSet có tập lựa chọn khác nhau; gộp chúng bằng cache[v] là sai.

**Câu 8.** Nếu một công thức truy hồi có trạng thái lặp nhưng không bao quát một lựa chọn hợp lệ, memoization có sửa được không?

**Đáp án:** Không. Cache chỉ ghi nhớ kết quả của công thức; phải sửa định nghĩa trạng thái và công thức để bao phủ đúng mọi phương án.

**Ghi nhớ:** **Chồng lặp** trả lời “kết quả trạng thái nào đang bị tính đi tính lại?”, còn **cấu trúc con tối ưu** trả lời “vì sao lời giải tối ưu của trạng thái lớn có thể dựng từ những lời giải tối ưu của trạng thái nhỏ?”. Định nghĩa **đủ trạng thái**, chứng minh **công thức đúng**, rồi mới chọn **memoization/tabulation** và tối ưu thời gian, bộ nhớ.

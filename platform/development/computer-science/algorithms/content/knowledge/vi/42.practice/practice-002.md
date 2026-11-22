# Từ vét cạn đến tiền xử lý, tham lam hoặc quy hoạch động

Vét cạn (*brute force*) thường là cách giải đầu tiên dễ nghĩ ra: liệt kê các khả năng, kiểm tra điều kiện và chọn kết quả tốt nhất. Nó có ưu điểm là bám sát định nghĩa bài toán, dễ kiểm tra và có thể dùng làm **oracle** cho dữ liệu nhỏ. Nhưng khi số khả năng tăng theo \(2^n\), \(n!\), hoặc mỗi truy vấn lại quét toàn bộ dữ liệu, cách làm đó có thể vượt giới hạn thời gian.

Để tối ưu, trước tiên phải tìm xem chương trình đang **làm lại công việc nào**, dữ liệu có cấu trúc gì, và yêu cầu tối ưu có tính chất nào. Ba hướng quan trọng:

- **Tiền xử lý** (*preprocessing*): tính trước thông tin được dùng lại nhiều lần, ví dụ prefix sum, bảng tần suất, dữ liệu đã sắp xếp, chỉ mục hoặc coordinate compression.
- **Tham lam** (*greedy*): chọn một phương án cục bộ ở mỗi bước khi có thể chứng minh rằng lựa chọn đó nằm trong ít nhất một lời giải tối ưu.
- **Quy hoạch động** (*dynamic programming, DP*): mô tả các trạng thái con, tận dụng bài toán con chồng lặp và xây đáp án bằng một recurrence chính xác.

Ba hướng này khai thác những cấu trúc khác nhau. Tiền xử lý giảm chi phí truy vấn lặp lại; greedy loại bỏ các lựa chọn không cần thiết nhờ một quy tắc có chứng minh; DP lưu kết quả các trạng thái con để tránh tính lại. Có bài toán kết hợp nhiều hướng, chẳng hạn sort rồi greedy, hoặc sort và binary search rồi DP.

Bài học thuộc nhóm **Thực hành tổng hợp**. Ta dùng ba ví dụ xuyên suốt:

1. **Prefix sum** tăng tốc nhiều truy vấn tổng đoạn.
2. **Interval scheduling** chọn số lượng khoảng không giao nhau lớn nhất bằng greedy.
3. **0/1 knapsack** tối đa hóa giá trị trong giới hạn sức chứa bằng DP.

Cuối bài có chương trình Java 17+ hoàn chỉnh, cài cả ba cách và đối chiếu với các oracle vét cạn/ngây thơ trên input nhỏ. Mục tiêu là biết **khi nào có thể tối ưu, cần chứng minh điều gì và kiểm thử ra sao**.

## 1. Phát biểu đúng bài toán trước khi tối ưu

Hãy xác định rõ:

- **Input:** dữ liệu gì và kích thước lớn nhất?
- **Output:** một giá trị, một tập phần tử, một thứ tự hay một lời giải cụ thể?
- **Ràng buộc:** có số âm, phần tử trùng, dữ liệu thay đổi, trọng số hay giới hạn sức chứa?
- **Mục tiêu:** tìm một lời giải hợp lệ hay phải tối ưu số lượng/tổng giá trị/chi phí?
- **Quy ước:** đoạn đóng hay nửa mở, hai khoảng chạm biên có tương thích không, một món được dùng một hay nhiều lần?
- **Ngân sách:** thời gian, RAM, độ lớn số học và độ sâu stack.

Một thay đổi nhỏ trong đề có thể làm thay đổi thuật toán phù hợp:

- Chọn **nhiều nhất số khoảng không giao nhau** khác với tối đa **tổng trọng số của khoảng**.
- Balo 0/1 (mỗi món lấy tối đa một lần) khác với balo không giới hạn.
- Prefix sum phù hợp với mảng tĩnh; cập nhật điểm liên tục có thể cần Fenwick Tree.
- BFS tìm đường ít cạnh nhất khác với Dijkstra tìm đường có tổng trọng số nhỏ nhất.

Một thuật toán nhanh cho bài toán được hiểu sai vẫn là lời giải sai. Vì vậy cần viết rõ hợp đồng và điều kiện biên trước khi tối ưu.

## 2. Vét cạn là baseline và oracle

Vét cạn liệt kê các phương án theo định nghĩa, kiểm tra từng phương án và chọn kết quả phù hợp.

| Bài toán | Vét cạn | Chi phí điển hình |
|---|---|---:|
| Tìm cặp có tổng X | Xét mọi cặp i<j | O(n²) |
| Tìm bộ ba có tổng X | Xét mọi bộ ba | O(n³) |
| Chọn tập con tối ưu | Thử mọi bitmask | O(2ⁿ) |
| Thử mọi thứ tự | Liệt kê hoán vị | O(n!) |
| Chọn tập khoảng không giao | Thử mọi tập con | O(2ⁿ) hoặc hơn nếu kiểm chậm |
| q truy vấn tổng đoạn | Quét từng phần tử mỗi lần | O(qn) |

Brute force hữu ích vì nó dễ xây dựng, bám sát đề và thường dễ chứng minh. Nó cũng là một **oracle độc lập** để kiểm tra thuật toán nhanh trên dữ liệu nhỏ.

Không cần bỏ brute force trong mọi trường hợp. Với n nhỏ, lời giải vét cạn có thể đủ nhanh và ít lỗi hơn. Ngưỡng phù hợp tùy số test, chi phí mỗi nhánh, ngôn ngữ và giới hạn thời gian; không có một con số chung cho mọi bài.

Phân biệt hai vai trò:

- **Brute force production:** chạy trên input thật; có thể quá chậm.
- **Brute force oracle:** chạy trên input nhỏ, có kiểm soát để đối chiếu lời giải tối ưu.

## 3. Đọc độ phức tạp để tìm nút thắt

Nếu q truy vấn, mỗi truy vấn quét n phần tử thì tổng thời gian có bậc:

\[
O(qn).
\]

Nếu q và n đều lớn, cần tìm thông tin dùng lại. Nhưng nếu q=1, xây một cấu trúc tiền xử lý O(n) có thể không đem lại lợi ích.

Một số dấu hiệu:

- Hai vòng lặp lồng nhau: thường O(n²).
- Ba vòng lặp: thường O(n³).
- Thử mọi tập con: O(2ⁿ).
- Thử mọi hoán vị: O(n!).
- Sort rồi quét: thường O(n log n).
- Một vòng lặp nhưng mỗi bước quét phần còn lại: vẫn có thể O(n²).
- DP có n trạng thái, mỗi trạng thái thử C lựa chọn: thường O(nC).

| Dạng input | Hướng thường cân nhắc |
|---|---|
| n rất nhỏ | Brute force, bitmask, backtracking |
| Nhiều truy vấn trên dữ liệu tĩnh | Preprocessing/index |
| Cần chọn theo thứ tự có cấu trúc | Sort + greedy/sweep |
| Có state con lặp lại | DP hoặc memoization |
| Miền giá trị nhỏ | Frequency/counting/bitset |
| Miền lớn nhưng ít giá trị phân biệt | Hashing/coordinate compression |

Bảng chỉ gợi ý. Hãy tính tổng số phép toán, bộ nhớ và các hằng số đáng kể thay vì suy luận từ n đơn lẻ.

## 4. Quy trình chuyển từ brute force sang lời giải tốt hơn

**Bước 1 — viết baseline đúng.** Cài hoặc mô tả cách vét cạn để làm rõ điều kiện hợp lệ và đáp án.

**Bước 2 — tìm phần lặp.** Một truy vấn có quét lại cùng dữ liệu không? Nhiều lời gọi có giải cùng một state không? Nhiều phương án có thể bị loại bằng một lập luận chung không?

**Bước 3 — nhận diện cấu trúc.**

- Dữ liệu tĩnh, nhiều truy vấn → preprocessing.
- Có quy tắc chọn cục bộ và chứng minh được → greedy.
- Có overlapping subproblems và recurrence → DP.
- Nếu không phù hợp, cân nhắc cấu trúc dữ liệu, divide and conquer, graph algorithm, branch and bound hoặc hướng khác.

**Bước 4 — chứng minh.** Nêu rõ vì sao bảng tiền xử lý đủ thông tin, vì sao greedy không mất tối ưu, hoặc vì sao recurrence DP bao phủ mọi lựa chọn.

**Bước 5 — phân tích thời gian và bộ nhớ.** Tính cả sort, xây bảng, số trạng thái, số truy vấn, truy vết và overflow.

**Bước 6 — differential testing.** Sinh input nhỏ, chạy cả brute force và lời giải nhanh, so kết quả.

**Bước 7 — đo trên dữ liệu đại diện.** Chỉ sau khi đúng mới benchmark để biết có cần tối ưu thêm không.

## 5. Hướng thứ nhất: tiền xử lý

Tiền xử lý phù hợp khi một tập dữ liệu tương đối ổn định được dùng trong nhiều truy vấn. Thay vì tính lại từ đầu, ta xây một cấu trúc bổ trợ một lần.

Ví dụ:

- Prefix sum cho tổng đoạn.
- Prefix frequency cho số lần xuất hiện.
- Sort một bản sao để binary search.
- Hash map cho tra cứu theo khóa.
- Coordinate compression cho miền giá trị lớn nhưng số giá trị phân biệt ít.
- Sparse table cho min/max trên mảng tĩnh.
- Sweep line để gom nhiều truy vấn vào một lần quét.

### 5.1. Prefix sum

Cho mảng:

\[
a[0],a[1],\ldots,a[n-1].
\]

Định nghĩa:

\[
prefix[0]=0,\qquad
prefix[i+1]=prefix[i]+a[i].
\]

Tổng đoạn đóng [l,r]:

\[
\boxed{\sum_{i=l}^{r}a[i]=prefix[r+1]-prefix[l]}
\]

với \(0\le l\le r<n\).

Ví dụ:

~~~text
a      = [4, -2, 7, 1, 3]
prefix = [0,  4, 2, 9,10,13]
~~~

Tổng đoạn [1,3]:

\[
prefix[4]-prefix[1]=10-4=\boxed{6}.
\]

Tổng toàn mảng là prefix[5]−prefix[0]=13.

Brute force tính một đoạn O(n); prefix sum trả lời O(1) sau O(n) tiền xử lý. Với q truy vấn:

| Cách làm | Tổng thời gian |
|---|---:|
| Quét mỗi đoạn | O(qn) |
| Xây prefix rồi truy vấn | O(n+q) |

Nếu mảng thay đổi, prefix cũ không còn đúng. Cập nhật một phần tử có thể làm nhiều prefix phía sau thay đổi; khi cần cập nhật xen truy vấn, cân nhắc Fenwick Tree hoặc segment tree.

### 5.2. Prefix frequency

Nếu cần hỏi “đoạn [l,r] có bao nhiêu phần tử bằng x?”, với x cố định có thể xây:

\[
count_x[i+1]=count_x[i]+[a[i]=x].
\]

Trả lời:

\[
count_x[r+1]-count_x[l].
\]

Nếu x có rất nhiều giá trị khác nhau và miền lớn, không nên tạo bảng cho mọi x một cách máy móc; có thể dùng map lưu vị trí hoặc cấu trúc phù hợp.

### 5.3. Sort và binary search

Nếu có nhiều truy vấn “x có xuất hiện không?”:

- Quét mỗi lần: O(qn).
- Sort một bản sao: O(n log n).
- Mỗi truy vấn binary search: O(log n).

Tổng:

\[
O(n\log n+q\log n).
\]

Nếu chỉ có một truy vấn, sort có thể đắt hơn quét. Hãy tính số lần dùng lại để đánh giá preprocessing có được khấu hao hay không.

### 5.4. Coordinate compression

Khi giá trị rất lớn hoặc âm nhưng chỉ có k giá trị phân biệt:

1. Lấy bản sao các giá trị.
2. Sort.
3. Loại trùng.
4. Gán mỗi giá trị một rank từ 0 đến k−1.

Ví dụ:

~~~text
values = [1000000000, -7, 1000000000, 42]
unique = [-7, 42, 1000000000]
rank   = [2, 0, 2, 1]
~~~

Compression giữ thứ tự tương đối:

\[
x<y\iff rank(x)<rank(y).
\]

Nhưng rank **không giữ khoảng cách số học**. Không được thay giá trị bằng rank trong công thức cần tổng, hiệu hoặc khoảng cách thực.

## 6. Khi nào preprocessing đáng giá?

Nếu q truy vấn brute force O(n), còn tiền xử lý tốn O(P) và mỗi truy vấn sau đó O(log n):

\[
T_{\text{naive}}=O(qn)
\]

\[
T_{\text{prepared}}=O(P+q\log n).
\]

Tiền xử lý thường có lợi khi q đủ lớn và chi phí xây hợp lý. Cần hỏi:

- Dữ liệu có thay đổi giữa các truy vấn không?
- Bảng bổ trợ tốn bao nhiêu RAM?
- Các truy vấn có thực sự dùng được bảng đó?
- Có thể xử lý offline bằng sort/sweep không?
- Có cần trả lời ngay khi nhận truy vấn hay được phép biết trước tất cả?

**Online** nghĩa là trả lời khi truy vấn đến, chưa biết truy vấn tương lai. **Offline** cho phép đọc toàn bộ truy vấn, sắp xếp và xử lý theo thứ tự thuận lợi rồi khôi phục thứ tự kết quả. Một thuật toán offline nhanh không phù hợp nếu ứng dụng cần phản hồi tức thời.

## 7. Hướng thứ hai: tham lam (greedy)

Greedy xây lời giải từng bước. Mỗi bước chọn một phương án theo quy tắc cục bộ, rồi tiếp tục với phần còn lại.

Các quy tắc có thể là chọn khoảng kết thúc sớm nhất, cạnh nhẹ nhất theo một invariant, hoặc lựa chọn nhỏ nhất còn giữ được điều kiện tối ưu. **Greedy không đồng nghĩa với “chọn cái trông có vẻ tốt nhất”.** Phải chứng minh lựa chọn ấy luôn có thể xuất hiện trong ít nhất một lời giải tối ưu.

Hai tính chất thường cần:

1. **Greedy-choice property:** tồn tại một lời giải tối ưu chứa lựa chọn greedy.
2. **Optimal substructure:** sau khi cố định lựa chọn, phần còn lại là bài toán con cùng dạng.

Có optimal substructure chưa chắc greedy được; có thể vẫn phải cân nhắc nhiều lựa chọn bằng DP.

## 8. Ví dụ greedy: interval scheduling

Cho các khoảng nửa mở:

\[
[start,end),\qquad start<end.
\]

Hai khoảng [a,b) và [c,d) không giao nhau nếu:

\[
b\le c\quad\text{hoặc}\quad d\le a.
\]

Mục tiêu là chọn **số lượng khoảng lớn nhất** sao cho không có hai khoảng nào giao nhau.

Vét cạn thử mọi tập con n khoảng, rồi kiểm từng cặp khoảng. Chi phí có thể lên tới O(2ⁿ n²).

### Quy tắc greedy

1. Sort theo thời điểm kết thúc tăng dần; nếu hòa, sort start tăng dần.
2. Chọn khoảng đầu tiên.
3. Với mỗi khoảng tiếp theo, nếu start ≥ end của khoảng cuối đã chọn thì chọn.
4. Tiếp tục đến hết.

Ví dụ:

~~~text
[1,3), [2,5), [4,7), [6,9), [8,10), [9,11)
~~~

Greedy chọn:

~~~text
[1,3), [4,7), [8,10)
~~~

Số lượng là 3. Hai khoảng [1,3) và [3,5) tương thích vì chúng chỉ chạm biên theo quy ước nửa mở.

### Chứng minh bằng exchange argument

Gọi g là khoảng kết thúc sớm nhất trong toàn bộ input. Xét một lời giải tối ưu O và sắp các khoảng trong O theo thời điểm kết thúc. Gọi x là khoảng đầu tiên của O.

Do g kết thúc không muộn hơn x:

\[
end(g)\le end(x).
\]

Mọi khoảng y tiếp theo trong O bắt đầu tại hoặc sau end(x), vì các khoảng trong O không giao nhau. Do đó:

\[
start(y)\ge end(x)\ge end(g).
\]

Thay x bằng g không làm g giao với bất kỳ khoảng nào còn lại. Số khoảng được chọn giữ nguyên, nên ta thu được một lời giải tối ưu bắt đầu bằng g.

Sau khi chọn g, chỉ còn xét các khoảng bắt đầu tại hoặc sau end(g). Phần còn lại là một bài toán interval scheduling nhỏ hơn. Lặp lại lập luận bằng quy nạp, ta chứng minh greedy luôn cho số khoảng tối đa.

### Độ phức tạp

- Sort n khoảng: O(n log n).
- Quét một lần: O(n).
- Bản sao và output: O(n) bộ nhớ trong cài đặt minh họa.

Tổng thời gian:

\[
\boxed{O(n\log n).}
\]

## 9. Khi greedy thất bại

Xét đổi tiền với mệnh giá:

\[
\{1,3,4\}
\]

và cần tạo tổng 6 bằng ít đồng nhất.

Greedy lấy đồng lớn nhất trước:

~~~text
4 + 1 + 1 = 6
~~~

cần 3 đồng. Nhưng tối ưu là:

~~~text
3 + 3 = 6
~~~

chỉ cần 2 đồng.

Vậy quy tắc “lấy đồng lớn nhất” không đúng cho mọi hệ mệnh giá. Với mệnh giá tùy ý, DP có thể giải tổng quát hơn:

\[
dp[x]=1+\min_{c\le x}dp[x-c].
\]

Trước khi dùng greedy, hãy xác định quy tắc cục bộ, tìm phản ví dụ nhỏ và chứng minh exchange/cut/stays-ahead. Cũng phải kiểm tra tie-break và định nghĩa biên.

Một biến thể quan trọng: interval scheduling tối đa **số khoảng** dùng earliest finish; tối đa **tổng trọng số khoảng** thường cần weighted interval scheduling DP.

## 10. Hướng thứ ba: quy hoạch động

DP phù hợp khi bài toán có:

1. Các trạng thái con có thể mô tả được.
2. Nhiều lời gọi vét cạn giải lại cùng trạng thái.
3. Đáp án lớn được xây từ đáp án các trạng thái con bằng recurrence.

Hai kiểu triển khai:

- **Top-down memoization:** đệ quy tự nhiên, lưu kết quả mỗi state.
- **Bottom-up tabulation:** tính trạng thái theo thứ tự sao cho mọi phụ thuộc đã có.

### Sáu bước thiết kế DP

1. **State:** định nghĩa trạng thái và ý nghĩa chính xác.
2. **Recurrence:** liệt kê các lựa chọn và quan hệ chuyển.
3. **Base case:** trạng thái nhỏ nhất có giá trị gì?
4. **Order:** tính theo thứ tự nào để state phụ thuộc sẵn sàng?
5. **Answer:** kết quả nằm ở state nào?
6. **Memory:** có thể nén chiều hay cần giữ thông tin truy vết?

State phải chứa đủ thông tin để phần còn lại của bài toán được xác định. State quá ít gây recurrence sai; state quá nhiều làm tăng thời gian và bộ nhớ.

## 11. Ví dụ DP: balo 0/1

Có n món đồ. Món i có trọng lượng \(w_i>0\), giá trị \(v_i\ge0\). Balo có sức chứa tối đa C. Mỗi món được lấy **không quá một lần**. Tìm tổng giá trị lớn nhất với tổng trọng lượng không vượt C.

Vét cạn thử mọi tập con, có \(2^n\) tập.

### State và recurrence

Đặt:

\[
dp[i][c]
\]

là giá trị lớn nhất khi xét i món đầu và sức chứa tối đa c.

Với món i:

- Không lấy: \(dp[i-1][c]\).
- Lấy nếu \(w_i\le c\): \(dp[i-1][c-w_i]+v_i\).

Do đó:

\[
dp[i][c]=
\begin{cases}
dp[i-1][c], & w_i>c,\\
\max(dp[i-1][c],dp[i-1][c-w_i]+v_i),&w_i\le c.
\end{cases}
\]

Base case:

\[
dp[0][c]=0.
\]

Đáp án:

\[
\boxed{dp[n][C].}
\]

Ví dụ:

| Món | Trọng lượng | Giá trị |
|---:|---:|---:|
| 1 | 2 | 3 |
| 2 | 3 | 4 |
| 3 | 4 | 5 |
| 4 | 5 | 8 |

Với C=7, chọn món 1 và 4, tổng trọng lượng 7, tổng giá trị:

\[
3+8=\boxed{11}.
\]

### Nén còn một chiều

Recurrence chỉ dùng hàng i−1. Ta có thể dùng một mảng:

~~~text
for each item (weight, value):
    for c from capacity down to weight:
        dp[c] = max(dp[c], dp[c-weight] + value)
~~~

**Duyệt c giảm dần** là điều bắt buộc cho cách nén 0/1. Khi xử lý món hiện tại, dp[c−weight] vẫn thuộc kết quả trước món ấy, nên món không thể được dùng lần thứ hai.

Nếu duyệt c tăng, dp[c−weight] có thể đã chứa tác động của chính món hiện tại; recurrence trở thành một dạng **unbounded knapsack**, cho phép lấy lại món.

Độ phức tạp:

\[
\boxed{O(nC)\text{ thời gian},\quad O(C)\text{ bộ nhớ}.}
\]

O(nC) là **pseudo-polynomial** vì phụ thuộc giá trị số C, không chỉ số bit biểu diễn C. Nếu C rất lớn, mảng dp có thể quá lớn; cần sparse DP, meet-in-the-middle hoặc hướng khác tùy dữ liệu.

Nếu cần in tập món được chọn, chỉ lưu giá trị tối ưu cuối cùng có thể không đủ; cần lưu quyết định, predecessor hoặc dùng chiến lược truy vết.

## 12. So sánh ba hướng

| Tiêu chí | Preprocessing | Greedy | DP |
|---|---|---|---|
| Khai thác | Thông tin dùng lại | Lựa chọn cục bộ có chứng minh | Trạng thái con, recurrence |
| Tình huống | Nhiều truy vấn tĩnh | Có thứ tự/invariant lựa chọn | Overlapping subproblems |
| Chứng minh | Công thức/chỉ mục đúng | Exchange hoặc lập luận tương đương | Quy nạp trên state |
| Ví dụ | Prefix sum O(n+q) | Interval O(n log n) | Knapsack O(nC) |
| Rủi ro | Dữ liệu đổi làm bảng cũ sai | Greedy choice không đúng | State/recurrence/order sai |

Có thể kết hợp:

- Sort khoảng rồi greedy chọn earliest finish.
- Sort theo end, binary search predecessor rồi DP cho weighted interval scheduling.
- Prefix sum tăng tốc bước tính chi phí trong DP.
- Coordinate compression giúp Fenwick Tree/segment tree làm việc trên chỉ số gọn.

Tên kỹ thuật không quan trọng bằng **cấu trúc chứng minh** của toàn bộ thuật toán.

## 13. Những bài gần nhau nhưng cần hướng khác

**Interval scheduling không trọng số:** tối đa số khoảng; greedy earliest finish.

**Weighted interval scheduling:** tối đa tổng trọng số; sort theo end, tìm p(i) là khoảng cuối cùng tương thích bằng binary search, rồi:

\[
OPT(i)=\max(OPT(i-1),weight_i+OPT(p(i))).
\]

**Coin change:** greedy chỉ đúng với một số hệ mệnh giá; DP xử lý mệnh giá tùy ý.

**Range sum:** một truy vấn có thể quét; nhiều truy vấn tĩnh dùng prefix; cập nhật điểm xen truy vấn dùng Fenwick; cập nhật đoạn phức tạp có thể dùng segment tree.

Một cấu trúc mạnh hơn không tự động là lựa chọn tốt hơn. Hãy chọn mức phức tạp nhỏ nhất đáp ứng đầy đủ hợp đồng.

## 14. Chứng minh đúng theo từng hướng

### Preprocessing

Chứng minh thông tin được tính trước có quan hệ chính xác với câu trả lời. Với prefix sum:

\[
prefix[r+1]-prefix[l]
=\sum_{i=0}^{r}a[i]-\sum_{i=0}^{l-1}a[i]
=\sum_{i=l}^{r}a[i].
\]

Các phần trước l triệt tiêu, còn đúng đoạn cần hỏi.

### Greedy

Chứng minh lựa chọn cục bộ có thể xuất hiện trong một lời giải tối ưu, sau đó phần còn lại là bài toán con cùng dạng. Interval scheduling dùng exchange argument thay khoảng đầu bằng khoảng kết thúc sớm nhất.

### DP

Chứng minh recurrence xét đủ và chỉ những lựa chọn hợp lệ. Với 0/1 knapsack, mọi lời giải hoặc không lấy món i, hoặc lấy món i; hai trường hợp bao phủ mọi tập con. Quy nạp theo số món chứng minh dp đúng.

Nhiều test vượt qua không thay thế được chứng minh tổng quát.

## 15. Brute force làm oracle: differential testing

Một quy trình kiểm thử hiệu quả:

1. Viết thuật toán đơn giản, dễ tin.
2. Viết thuật toán tối ưu.
3. Sinh input nhỏ có kiểm soát.
4. Chạy cả hai trên cùng input.
5. So kết quả; nếu khác, giữ input nhỏ nhất gây lỗi.

| Thuật toán nhanh | Oracle |
|---|---|
| Prefix sum | Cộng trực tiếp từng đoạn |
| Greedy interval | Thử mọi tập con khoảng |
| 0/1 knapsack DP | Thử mọi tập con món |

Input nhỏ đặc biệt hữu ích cho các trường hợp biên: mảng một phần tử, số âm, tổng 0, khoảng chạm biên, khoảng trùng, sức chứa 0, món nặng hơn balo, và nhiều lời giải tối ưu cùng giá trị.

Random testing nên đi cùng test cố định và test stress. Dùng seed cố định để tái lập; khi tìm được mismatch, thu nhỏ input và lưu thành regression test.

## 16. Java 17+: chương trình hoàn chỉnh

Lưu chương trình dưới tên **FromBruteForceToOptimizedStrategiesDemo.java**. Chương trình cài:

- Prefix sum và range sum trên đoạn đóng.
- Greedy interval scheduling trên khoảng nửa mở [start,end).
- 0/1 knapsack DP một chiều, duyệt sức chứa giảm dần.
- Oracle brute force cho interval scheduling và knapsack.
- Oracle quét trực tiếp cho prefix sum.
- Differential tests dùng seed cố định.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Random;
import java.util.StringJoiner;

public class FromBruteForceToOptimizedStrategiesDemo {

    // ---------- PREPROCESSING: PREFIX SUM ----------

    static long[] prefixSums(long[] values) {
        if (values == null) {
            throw new IllegalArgumentException(
                "values must not be null"
            );
        }

        long[] prefix = new long[values.length + 1];
        for (int i = 0; i < values.length; i++) {
            prefix[i + 1] = Math.addExact(
                prefix[i], values[i]
            );
        }
        return prefix;
    }

    // Inclusive range [left, right].
    static long rangeSum(
        long[] prefix, int left, int right
    ) {
        if (prefix == null || prefix.length == 0) {
            throw new IllegalArgumentException(
                "invalid prefix array"
            );
        }
        int n = prefix.length - 1;
        if (left < 0 || left > right || right >= n) {
            throw new IllegalArgumentException(
                "invalid inclusive range"
            );
        }
        return Math.subtractExact(
            prefix[right + 1], prefix[left]
        );
    }

    static long bruteRangeSum(
        long[] values, int left, int right
    ) {
        long total = 0L;
        for (int i = left; i <= right; i++) {
            total = Math.addExact(total, values[i]);
        }
        return total;
    }

    // ---------- GREEDY: INTERVAL SCHEDULING ----------

    // Nonempty half-open interval [start, end).
    record Interval(int start, int end) {
        Interval {
            if (start >= end) {
                throw new IllegalArgumentException(
                    "interval must satisfy start < end"
                );
            }
        }
    }

    static List<Interval> greedyIntervals(
        Interval[] input
    ) {
        if (input == null) {
            throw new IllegalArgumentException(
                "intervals must not be null"
            );
        }

        Interval[] sorted = input.clone();
        for (Interval interval : sorted) {
            if (interval == null) {
                throw new IllegalArgumentException(
                    "null interval"
                );
            }
        }

        Arrays.sort(
            sorted,
            Comparator.comparingInt(Interval::end)
                .thenComparingInt(Interval::start)
        );

        List<Interval> chosen = new ArrayList<>();
        boolean hasChosen = false;
        int lastEnd = 0;

        for (Interval interval : sorted) {
            if (!hasChosen || interval.start() >= lastEnd) {
                chosen.add(interval);
                lastEnd = interval.end();
                hasChosen = true;
            }
        }
        return List.copyOf(chosen);
    }

    // Exact oracle for small n: enumerate all subsets and
    // check every selected interval pair for overlap.
    static int bruteIntervalCount(Interval[] intervals) {
        if (intervals == null) {
            throw new IllegalArgumentException(
                "intervals must not be null"
            );
        }
        int n = intervals.length;
        if (n > 20) {
            throw new IllegalArgumentException(
                "brute oracle is limited to 20 intervals"
            );
        }

        for (Interval interval : intervals) {
            if (interval == null) {
                throw new IllegalArgumentException(
                    "null interval"
                );
            }
        }

        int best = 0;
        int limit = 1 << n;

        for (int mask = 0; mask < limit; mask++) {
            int count = Integer.bitCount(mask);
            if (count <= best) {
                continue;
            }

            boolean compatible = true;
            for (int i = 0; i < n && compatible; i++) {
                if ((mask & (1 << i)) == 0) {
                    continue;
                }
                for (int j = i + 1; j < n; j++) {
                    if ((mask & (1 << j)) == 0) {
                        continue;
                    }

                    Interval a = intervals[i];
                    Interval b = intervals[j];
                    boolean disjoint =
                        a.end() <= b.start()
                        || b.end() <= a.start();

                    if (!disjoint) {
                        compatible = false;
                        break;
                    }
                }
            }

            if (compatible) {
                best = count;
            }
        }
        return best;
    }

    static String formatIntervals(List<Interval> intervals) {
        StringJoiner joiner = new StringJoiner(", ", "[", "]");
        for (Interval interval : intervals) {
            joiner.add(
                "[" + interval.start() + ","
                + interval.end() + ")"
            );
        }
        return joiner.toString();
    }

    // ---------- DYNAMIC PROGRAMMING: 0/1 KNAPSACK ----------

    static void validateKnapsack(
        int[] weights, int[] values, int capacity
    ) {
        if (weights == null || values == null
                || weights.length != values.length) {
            throw new IllegalArgumentException(
                "weights and values must have equal lengths"
            );
        }
        if (capacity < 0) {
            throw new IllegalArgumentException(
                "capacity must be >= 0"
            );
        }
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                    "weight must be positive and value nonnegative"
                );
            }
        }
    }

    // Descending capacity prevents reusing the current item.
    static long knapsack01(
        int[] weights, int[] values, int capacity
    ) {
        validateKnapsack(weights, values, capacity);
        long[] dp = new long[capacity + 1];

        for (int i = 0; i < weights.length; i++) {
            int weight = weights[i];
            int value = values[i];

            for (int c = capacity; c >= weight; c--) {
                long take = Math.addExact(
                    dp[c - weight], (long) value
                );
                dp[c] = Math.max(dp[c], take);
            }
        }
        return dp[capacity];
    }

    // Exact oracle for small n: enumerate every subset.
    static long bruteKnapsack(
        int[] weights, int[] values, int capacity
    ) {
        validateKnapsack(weights, values, capacity);
        int n = weights.length;
        if (n > 20) {
            throw new IllegalArgumentException(
                "brute oracle is limited to 20 items"
            );
        }

        long best = 0L;
        int limit = 1 << n;

        for (int mask = 0; mask < limit; mask++) {
            long totalWeight = 0L;
            long totalValue = 0L;

            for (int i = 0; i < n; i++) {
                if ((mask & (1 << i)) != 0) {
                    totalWeight += weights[i];
                    totalValue = Math.addExact(
                        totalValue, values[i]
                    );
                }
            }

            if (totalWeight <= capacity) {
                best = Math.max(best, totalValue);
            }
        }
        return best;
    }

    // ---------- DIFFERENTIAL TESTING ----------

    static void verifyPrefixSums(Random random) {
        int arrays = 300;
        int queriesPerArray = 20;

        for (int test = 0; test < arrays; test++) {
            int n = 1 + random.nextInt(40);
            long[] values = new long[n];

            for (int i = 0; i < n; i++) {
                values[i] = random.nextInt(41) - 20;
            }

            long[] prefix = prefixSums(values);

            for (int q = 0; q < queriesPerArray; q++) {
                int left = random.nextInt(n);
                int right = random.nextInt(n);
                if (left > right) {
                    int temp = left;
                    left = right;
                    right = temp;
                }

                long fast = rangeSum(prefix, left, right);
                long slow = bruteRangeSum(
                    values, left, right
                );

                if (fast != slow) {
                    throw new AssertionError(
                        "prefix mismatch at test " + test
                    );
                }
            }
        }

        System.out.println(
            "Prefix-sum checks: PASS ("
            + arrays + " arrays x "
            + queriesPerArray + " queries)"
        );
    }

    static void verifyIntervals(Random random) {
        int cases = 250;

        for (int test = 0; test < cases; test++) {
            int n = random.nextInt(13);
            Interval[] intervals = new Interval[n];

            for (int i = 0; i < n; i++) {
                int start = random.nextInt(20);
                int end = start + 1 + random.nextInt(7);
                intervals[i] = new Interval(start, end);
            }

            int greedy = greedyIntervals(intervals).size();
            int brute = bruteIntervalCount(intervals);

            if (greedy != brute) {
                throw new AssertionError(
                    "interval mismatch at test " + test
                    + ": greedy=" + greedy
                    + ", brute=" + brute
                );
            }
        }

        System.out.println(
            "Interval scheduling checks: PASS ("
            + cases + " cases)"
        );
    }

    static void verifyKnapsack(Random random) {
        int cases = 250;

        for (int test = 0; test < cases; test++) {
            int n = random.nextInt(17);
            int capacity = random.nextInt(31);
            int[] weights = new int[n];
            int[] values = new int[n];

            for (int i = 0; i < n; i++) {
                weights[i] = 1 + random.nextInt(12);
                values[i] = random.nextInt(31);
            }

            long fast = knapsack01(
                weights, values, capacity
            );
            long brute = bruteKnapsack(
                weights, values, capacity
            );

            if (fast != brute) {
                throw new AssertionError(
                    "knapsack mismatch at test " + test
                    + ": dp=" + fast + ", brute=" + brute
                );
            }
        }

        System.out.println(
            "Knapsack checks: PASS (" + cases + " cases)"
        );
    }

    public static void main(String[] args) {
        long[] values = {4, -2, 7, 1, 3};
        long[] prefix = prefixSums(values);

        System.out.println(
            "Prefix sums: " + Arrays.toString(prefix)
        );
        System.out.println(
            "Range sum [1,3]: " + rangeSum(prefix, 1, 3)
        );
        System.out.println(
            "Range sum [0,4]: " + rangeSum(prefix, 0, 4)
        );

        Interval[] intervals = {
            new Interval(1, 3),
            new Interval(2, 5),
            new Interval(4, 7),
            new Interval(6, 9),
            new Interval(8, 10),
            new Interval(9, 11)
        };
        List<Interval> chosen = greedyIntervals(intervals);

        System.out.println(
            "Greedy intervals: " + formatIntervals(chosen)
        );
        System.out.println(
            "Maximum compatible count: "
            + bruteIntervalCount(intervals)
        );

        int[] weights = {2, 3, 4, 5};
        int[] itemValues = {3, 4, 5, 8};
        int capacity = 7;

        System.out.println(
            "0/1 knapsack optimum: "
            + knapsack01(weights, itemValues, capacity)
        );
        System.out.println(
            "Brute-force knapsack optimum: "
            + bruteKnapsack(weights, itemValues, capacity)
        );

        Random random = new Random(551L);
        verifyPrefixSums(random);
        verifyIntervals(random);
        verifyKnapsack(random);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 FromBruteForceToOptimizedStrategiesDemo.java
java FromBruteForceToOptimizedStrategiesDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
Prefix sums: [0, 4, 2, 9, 10, 13]
Range sum [1,3]: 6
Range sum [0,4]: 13
Greedy intervals: [[1,3), [4,7), [8,10)]
Maximum compatible count: 3
0/1 knapsack optimum: 11
Brute-force knapsack optimum: 11
Prefix-sum checks: PASS (300 arrays x 20 queries)
Interval scheduling checks: PASS (250 cases)
Knapsack checks: PASS (250 cases)
~~~

## 17. Phân tích chương trình và giới hạn

### Prefix sum

`prefixSums` duyệt mảng một lần, dùng `Math.addExact` để báo overflow của long. `rangeSum` lấy hiệu hai prefix bằng `Math.subtractExact`.

- Xây prefix: O(n) thời gian, O(n) bộ nhớ.
- Mỗi truy vấn: O(1).
- q truy vấn: O(n+q).

Oracle `bruteRangeSum` cộng trực tiếp từng phần tử, không dùng prefix.

### Interval scheduling

`greedyIntervals` copy mảng, sort theo end rồi start, và chọn khoảng tiếp theo nếu start≥lastEnd.

Oracle `bruteIntervalCount` duyệt mọi mask và kiểm từng cặp khoảng. Oracle chỉ nhận n≤20 vì mục tiêu là test nhỏ.

- Greedy: O(n log n) thời gian, O(n) bộ nhớ cho bản sao/output.
- Oracle: O(2ⁿ n²) trường hợp xấu.

### 0/1 knapsack

`knapsack01` dùng một mảng dp, duyệt sức chứa từ lớn xuống nhỏ để mỗi món chỉ được dùng một lần.

Oracle `bruteKnapsack` thử mọi mask, tính tổng trọng lượng và giá trị.

- DP: O(nC) thời gian, O(C) bộ nhớ.
- Oracle: O(2ⁿ n).

Mã yêu cầu trọng lượng dương, giá trị không âm và sức chứa không âm. Nếu capacity rất lớn, mảng `long[capacity+1]` có thể quá lớn dù n nhỏ; đó là giới hạn của DP theo capacity.

### Overflow và truy vết

Các tổng prefix và giá trị DP dùng long. `Math.addExact`/`subtractExact` giúp phát hiện overflow. Nếu tổng thật vượt long, cần `BigInteger` hoặc biểu diễn khác.

Nếu đề yêu cầu in ra tập món được chọn, giá trị dp cuối cùng chưa đủ; cần lưu quyết định hoặc khôi phục qua bảng/trạng thái predecessor.

## 18. Differential testing và trường hợp biên

Chương trình dùng seed `551L`:

| Nhóm | Số lượng | Oracle |
|---|---:|---|
| Prefix sum | 300 mảng × 20 truy vấn = 6.000 | Quét trực tiếp |
| Interval scheduling | 250 trường hợp, n≤12 | Thử mọi tập con |
| 0/1 knapsack | 250 trường hợp, n≤16 | Thử mọi tập con |

Các nhóm kiểm tra những đặc trưng khác nhau:

- Prefix sum: giá trị âm, tổng 0, đoạn một phần tử, đoạn toàn mảng.
- Greedy: khoảng chồng lấn, chạm biên, cùng end, trùng nhau và input rỗng.
- Knapsack: capacity 0, không món nào vừa, nhiều món cùng giá trị, nhiều tập con cùng đạt optimum.

Random test cần đi cùng test cố định và stress test. Khi tìm được mismatch, thu nhỏ input và lưu lại thành regression test.

### Các trường hợp cần bổ sung theo đề thực tế

- Giá trị rất lớn gây overflow.
- n=0 hoặc n=1 nếu hợp đồng cho phép.
- Nhiều phần tử trùng hoặc tất cả giá trị âm.
- Các khoảng cùng start/end.
- Khoảng chỉ chạm biên.
- Sức chứa vừa đúng một món hoặc tổng trọng lượng.
- Nhiều lời giải tối ưu cùng giá trị.
- Capacity lớn đến mức O(nC) không còn phù hợp.
- Dữ liệu thay đổi giữa các truy vấn tiền xử lý.

## 19. Mở rộng và biến thể

**Prefix sum 2D:** dùng nguyên tắc bao hàm–loại trừ để trả tổng hình chữ nhật O(1) sau O(rows·cols) tiền xử lý.

**Weighted interval scheduling:** sort theo end, tìm p(i) là khoảng cuối cùng tương thích bằng binary search, rồi:

\[
OPT(i)=\max(OPT(i-1),w_i+OPT(p(i))).
\]

Đây là DP, không dùng greedy earliest-finish đơn giản.

**DP bitset:** subset sum có thể dùng dịch bit để cập nhật nhiều trạng thái trong một thao tác word/bitset.

**Meet-in-the-middle:** khi n vài chục nhưng 2ⁿ quá lớn, chia input thành hai nửa, liệt kê tập con từng nửa rồi sort/tìm kết hợp; đổi lại cần bộ nhớ đáng kể.

**Bottom-up DP:** nếu có thứ tự phụ thuộc, có thể tính trạng thái trực tiếp thay vì mô phỏng đệ quy. Phải chứng minh thứ tự đó hợp lệ.

## 20. Những lỗi thường gặp

1. Tối ưu trước khi hiểu đúng output.
2. Không có baseline để so sánh.
3. Nhầm tổng số lời gọi với độ phức tạp thực tế.
4. Dùng prefix sum sau khi dữ liệu đã thay đổi.
5. Quên prefix[0]=0.
6. Nhầm đoạn đóng với đoạn nửa mở.
7. Dùng int khi tổng có thể vượt giới hạn.
8. Không kiểm tra chỉ số truy vấn.
9. Sort input gốc dù caller cần giữ thứ tự.
10. Dùng coordinate compression cho công thức cần khoảng cách số học.
11. Cho rằng preprocessing luôn có lợi.
12. Nhầm online với offline.
13. Dùng greedy chỉ vì lựa chọn có vẻ hợp lý.
14. Dùng earliest start thay earliest finish cho interval scheduling.
15. Không định nghĩa khoảng chạm biên có tương thích không.
16. Quên sort trước khi greedy.
17. Không xử lý tie-break rõ ràng.
18. Dùng greedy không trọng số cho bài có trọng số.
19. Cho rằng coin greedy luôn đúng.
20. Không chứng minh greedy-choice property.
21. State DP thiếu thông tin.
22. Recurrence bỏ sót lựa chọn hợp lệ.
23. Base case sai.
24. Tính state trước các phụ thuộc.
25. Duyệt sức chứa tăng trong 0/1 knapsack.
26. Dùng 0/1 DP cho unbounded knapsack hoặc ngược lại.
27. Dùng int cho tổng giá trị tối ưu.
28. Không nhận ra O(nC) là pseudo-polynomial.
29. Nén DP nhưng không lưu đủ thông tin để truy vết.
30. Chạy brute force oracle trên input quá lớn.
31. Hai phiên bản kiểm thử dùng chung một hàm sai.
32. Chỉ random test, không có case biên.
33. Không cố định seed.
34. Không thu nhỏ input khi random test fail.
35. Chỉ kiểm giá trị tối ưu, không kiểm tập lựa chọn dựng ra.
36. Bỏ qua phần tử âm/trùng dù đề cho phép.
37. Quên bộ nhớ của preprocessing và DP.
38. Tuyên bố HashMap lookup O(1) tuyệt đối.
39. Cho rằng mọi bài có overlapping subproblems đều cần DP.
40. Cho rằng mọi bài có optimal substructure đều greedy.
41. Nhầm tìm lời giải hợp lệ với tìm lời giải tối ưu.
42. Benchmark trên một input duy nhất.
43. Tối ưu vi mô trước khi giảm bậc độ phức tạp.
44. Không phân tích RAM của bảng DP.
45. Không cập nhật regression test sau khi sửa lỗi.

## 21. Câu hỏi và bài tập tự luyện

**Bài 1.** Vét cạn có vai trò gì ngoài việc tạo lời giải chậm?

*Đáp án:* Là baseline, đặc tả dễ hiểu và oracle độc lập cho input nhỏ.

**Bài 2.** q truy vấn, mỗi truy vấn quét n phần tử, tổng thời gian?

*Đáp án:* O(qn) trong trường hợp xấu.

**Bài 3.** Prefix sum được định nghĩa thế nào?

*Đáp án:* prefix[0]=0 và prefix[i+1]=prefix[i]+a[i].

**Bài 4.** Tổng đoạn đóng [l,r] lấy từ prefix?

*Đáp án:* prefix[r+1]−prefix[l].

**Bài 5.** Xây prefix sum mất bao lâu?

*Đáp án:* O(n) thời gian và O(n) bộ nhớ.

**Bài 6.** Vì sao prefix sum tĩnh không phù hợp với cập nhật điểm xen truy vấn?

*Đáp án:* Một cập nhật có thể làm nhiều prefix phía sau thay đổi.

**Bài 7.** Coordinate compression giữ tính chất gì?

*Đáp án:* Thứ tự tương đối giữa các giá trị phân biệt.

**Bài 8.** Compression có giữ khoảng cách số học không?

*Đáp án:* Không; rank chỉ biểu diễn thứ tự.

**Bài 9.** Preprocessing có luôn đáng giá không?

*Đáp án:* Không; phải so chi phí xây với số truy vấn và chi phí sau xử lý.

**Bài 10.** Greedy cần tính chất cốt lõi nào?

*Đáp án:* Greedy-choice property và optimal substructure.

**Bài 11.** Interval scheduling tối đa số khoảng dùng quy tắc nào?

*Đáp án:* Chọn khoảng kết thúc sớm nhất còn tương thích.

**Bài 12.** Vì sao [1,3) và [3,5) tương thích?

*Đáp án:* Đoạn nửa mở không chứa điểm cuối; end trước bằng start sau.

**Bài 13.** Exchange argument chứng minh điều gì?

*Đáp án:* Có thể thay lựa chọn đầu của một lời giải tối ưu bằng lựa chọn greedy mà vẫn giữ tối ưu.

**Bài 14.** Interval scheduling greedy tốn bao nhiêu?

*Đáp án:* O(n log n) do sort, cộng O(n) quét.

**Bài 15.** Coin {1,3,4}, amount 6: greedy lớn nhất trước cho kết quả gì?

*Đáp án:* 4+1+1, cần 3 đồng.

**Bài 16.** Lời giải tốt hơn cho ví dụ coin change là gì?

*Đáp án:* 3+3, chỉ cần 2 đồng.

**Bài 17.** DP phù hợp khi nào?

*Đáp án:* Khi có bài toán con chồng lặp và đáp án được xây từ các state con.

**Bài 18.** Sáu bước thiết kế DP?

*Đáp án:* State, recurrence, base case, thứ tự tính, answer, phân tích/tối ưu bộ nhớ.

**Bài 19.** dp[i][c] trong 0/1 knapsack biểu diễn gì?

*Đáp án:* Giá trị lớn nhất khi xét i món đầu và sức chứa tối đa c.

**Bài 20.** Recurrence 0/1 knapsack có hai lựa chọn nào?

*Đáp án:* Không lấy món i hoặc lấy món i nếu đủ sức chứa.

**Bài 21.** Vì sao 1D 0/1 knapsack duyệt c giảm?

*Đáp án:* Để dp[c−weight] vẫn thuộc trạng thái trước món hiện tại, ngăn dùng lại món.

**Bài 22.** Duyệt c tăng thường biến recurrence thành bài gì?

*Đáp án:* Unbounded knapsack.

**Bài 23.** Với weights [2,3,4,5], values [3,4,5,8], capacity 7, optimum?

*Đáp án:* 11, chọn món trọng lượng 2 và 5.

**Bài 24.** Độ phức tạp 0/1 knapsack một chiều?

*Đáp án:* O(nC) thời gian, O(C) bộ nhớ.

**Bài 25.** Vì sao O(nC) gọi là pseudo-polynomial?

*Đáp án:* Phụ thuộc giá trị số C, không chỉ số bit biểu diễn C.

**Bài 26.** Interval scheduling có trọng số có dùng greedy earliest finish không?

*Đáp án:* Không đảm bảo; thường dùng weighted interval scheduling DP.

**Bài 27.** Oracle interval scheduling kiểm gì?

*Đáp án:* Duyệt mọi tập con và kiểm từng cặp khoảng có giao không.

**Bài 28.** Oracle knapsack kiểm gì?

*Đáp án:* Duyệt mọi tập món, tính trọng lượng/giá trị và chọn giá trị lớn nhất hợp lệ.

**Bài 29.** Differential testing là gì?

*Đáp án:* Chạy hai cách giải độc lập trên cùng input rồi so kết quả.

**Bài 30.** Vì sao dùng seed cố định?

*Đáp án:* Để tái lập chính xác trường hợp lỗi.

**Bài 31.** Nếu random test tìm mismatch, bước tiếp theo?

*Đáp án:* Thu nhỏ input và lưu thành regression test.

**Bài 32.** Có thể kết hợp preprocessing và greedy không?

*Đáp án:* Có; sort khoảng theo end trước khi greedy.

**Bài 33.** Có thể kết hợp preprocessing và DP không?

*Đáp án:* Có; sort theo end và binary search predecessor trước weighted interval DP.

**Bài 34.** Khi nào giá trị tối ưu chưa đủ hoàn thành yêu cầu?

*Đáp án:* Khi đề còn yêu cầu dựng tập phần tử/lộ trình; phải lưu hoặc khôi phục quyết định.

**Bài 35.** Vì sao phân biệt lời giải hợp lệ và lời giải tối ưu?

*Đáp án:* Tối ưu cần chứng minh không có phương án tốt hơn.

**Bài 36.** Khi nào không nên DP theo capacity?

*Đáp án:* Khi capacity quá lớn làm O(nC) hoặc O(C) vượt ngân sách.

**Tổng kết:** Chuyển từ vét cạn sang lời giải tốt hơn bắt đầu bằng việc giữ baseline đúng, xác định bottleneck và nhận diện cấu trúc bài toán. **Preprocessing** phù hợp khi thông tin tĩnh được dùng lại qua nhiều truy vấn; **greedy** phù hợp khi có lựa chọn cục bộ được chứng minh bằng exchange hoặc lập luận tương đương; **DP** phù hợp khi trạng thái con chồng lặp và recurrence bao phủ mọi lựa chọn. Ba ví dụ cho ba cơ chế: prefix sum đưa truy vấn tổng đoạn từ O(n) xuống O(1), interval scheduling đưa vét cạn tập con xuống O(n log n), và 0/1 knapsack dùng DP O(nC) thay O(2ⁿ). Chương trình Java 17 đối chiếu các thuật toán với oracle độc lập trên 6.000 truy vấn prefix, 250 bộ khoảng và 250 bộ balo. Không chọn greedy chỉ theo trực giác, không dùng preprocessing trên dữ liệu đã thay đổi và không quên chiều duyệt DP; mỗi tối ưu cần đúng hợp đồng, chứng minh, phân tích tài nguyên và kiểm thử độc lập.

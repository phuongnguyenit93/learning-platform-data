# Phân tích số trạng thái cùng chi phí mỗi chuyển

Trong **quy hoạch động (Dynamic Programming – DP)**, ta thường nghe một câu tóm tắt: “độ phức tạp bằng số trạng thái nhân với số phép chuyển”. Câu này rất hữu ích, nhưng chỉ đúng khi xác định chính xác **một trạng thái là gì**, **một trạng thái được tính bao nhiêu lần**, **có bao nhiêu phương án chuyển cần xét** và **mỗi phương án tốn bao nhiêu công việc**.

Một bảng DP có n trạng thái không tự động đồng nghĩa O(n) thời gian. Nếu để tính một ô phải duyệt thêm n ô cũ, tổng có thể là O(n²). Ngược lại, dùng tổng tiền tố hoặc cửa sổ cộng dồn có thể biến một phép chuyển phải cộng K giá trị thành phép cập nhật O(1), dù **tập trạng thái giữ nguyên**.

Bài học thuộc nhóm **Quy hoạch động** trong Computer Science Algorithms. Ta sẽ xây dựng cách phân tích có thể áp dụng cho DP một chiều, nhiều chiều, interval DP, bitmask DP và cả memoization, rồi kiểm chứng bằng hai ví dụ Java 17+: **đếm cách đi tối đa K bước** và **ba lô 0/1**.

## 1. Ba câu hỏi trước khi ghi Big-O

Khi đọc một lời giải DP, hãy hỏi theo thứ tự:

1. **Trạng thái biểu diễn điều gì?** Ví dụ dp[i] là số cách đến vị trí i; dp[i][c] là giá trị tối ưu dùng i món với sức chứa c.
2. **Có bao nhiêu trạng thái được tính?** Không nên chỉ đếm biến trong tên dp; cần nhân kích thước các miền chỉ số hoặc đếm số bộ trạng thái **có thể tiếp cận**.
3. **Tính một trạng thái tốn bao nhiêu?** Một phép cộng hằng số, hay vòng lặp qua K ứng viên, hay còn gọi hàm kiểm tra O(log n)?

Đồng thời, cần xác định thứ tự phụ thuộc: trạng thái nào đã có kết quả trước khi được dùng để tính trạng thái hiện tại? Một công thức chuyển hợp lệ nhưng duyệt sai thứ tự có thể tạo thuật toán sai.

Mô hình phân tích hữu ích là:

~~~text
T = chi phí khởi tạo + tổng công việc tính các trạng thái + chi phí xuất kết quả

T = O(P) + O(sum_{s trong states} [số chuyển được xét tại s ×
                                chi phí xử lý mỗi chuyển])
            + O(R)

Nếu có S trạng thái, tối đa D ứng viên mỗi trạng thái,
mỗi ứng viên xử lý tối đa C thao tác:
T = O(P + S × D × C + R).
~~~

Ký hiệu P ở đây là **chi phí tiền xử lý**, R là **chi phí dựng/khôi phục đáp án**. Chúng có thể quan trọng nếu phải sắp xếp, sinh danh sách cạnh, nén tọa độ hoặc truy ngược các lựa chọn.

Đây là **cận trên**, không bắt buộc là cận chặt. Nếu ít trạng thái có D ứng viên hoặc vòng lặp có giới hạn biến đổi theo s, nên tính tổng thực tế thay vì nhân hai cực đại rồi kết luận luôn đạt đến.

## 2. Số trạng thái: tích các chiều hay số lượng tiếp cận?

Một số dạng thường gặp:

| Ký hiệu DP | Ý nghĩa tham số | Số trạng thái tối đa |
| --- | --- | --- |
| dp[i], i = 0..n | Tiền tố hoặc vị trí | n + 1 |
| dp[i][j] | Hai chỉ số độc lập trong khoảng 0..n, 0..m | (n + 1)(m + 1) |
| dp[i][capacity] | i món đầu, sức chứa c = 0..W | (n + 1)(W + 1) |
| dp[l][r], 0 ≤ l < r ≤ n | Đoạn nửa mở không rỗng | n(n + 1)/2 |
| dp[mask][last] | Tập đã chọn và đỉnh cuối | Tối đa n × 2^n |
| dp[position][tight][sum] | DP chữ số có ràng buộc | Tích số vị trí, hai giá trị tight và số khả năng sum |

Không phải mọi bộ chỉ số trong tích Descartes đều nhất thiết **hợp lệ hoặc đạt được**. Ví dụ interval DP chỉ dùng l < r nên không phải mọi ô trong ma trận n × n. Với top-down memoization, số trạng thái **thực tế được truy cập** có thể thấp hơn tổng kích thước lý thuyết.

Ngược lại, một hiện thực bottom-up có thể vẫn khởi tạo hoặc duyệt toàn bộ bảng kể cả các ô không hữu ích. Khi tính chi phí phải dựa vào **chính các vòng lặp và cấu trúc dữ liệu được thực thi**, không tự giả định các trạng thái vô ích được bỏ qua.

Nếu trạng thái chứa các tham số như vị trí, mask và số dư, cần xác nhận một bộ tham số xác định **đủ thông tin** cho bài toán con. Nếu thiếu thông tin làm hai tình huống khác nhau bị gộp vào cùng một khóa memo, phân tích nhanh đến đâu cũng không cứu được tính đúng đắn.

## 3. Chi phí mỗi trạng thái: phân biệt số chuyển và chi phí một chuyển

Ví dụ có S trạng thái và mỗi trạng thái xét D ứng viên:

- Nếu mỗi ứng viên chỉ đọc một ô DP, cộng hoặc so sánh hằng số lần, thời gian O(SD).
- Nếu xử lý một ứng viên cần duyệt thêm M phần tử, thời gian có thể O(SDM).
- Nếu mỗi ứng viên đòi tìm nhị phân O(log n), thời gian có thể O(SD log n).
- Nếu mỗi trạng thái có số ứng viên khác nhau D(s), cách biểu diễn chặt hơn là O(P + Σ_s D(s) × C(s) + R).

**Bẫy đếm trùng:** khi định nghĩa “một chuyển” đã bao gồm cả vòng lặp tìm ứng viên, không được tiếp tục nhân thêm vòng lặp đó lần nữa. Hãy xác định rõ một đơn vị đếm là **một cạnh chuyển** hay **toàn bộ thủ tục tính trạng thái**.

**Bẫy phụ thuộc dữ liệu:** các phép tra HashMap thường O(1) trung bình nhưng không có nghĩa chi phí một chuyển được bảo đảm O(1) cho mọi trường hợp xấu nhất. Nếu mỗi chuyển thực hiện thao tác trên heap hoặc cây có kích thước n, chi phí có thể là O(log n). Nếu tạo/copy danh sách dài theo mỗi trạng thái, việc “gán đáp án” không còn là O(1).

**Không mặc định số chuyển bằng số trạng thái.** Một trạng thái có thể có n phương án chọn điểm chia, hoặc chỉ một lựa chọn từ hai trạng thái đã có; sự khác biệt này quyết định O(n³) hay O(n²) trong nhiều DP theo đoạn.

## 4. Ví dụ 1: đếm số cách đi đến bậc n với bước dài tối đa K

Cho vị trí từ 0 tới n; mỗi lượt đi được **1, 2, ..., K** vị trí với K ≥ 1. Hỏi có bao nhiêu dãy bước có thứ tự đi từ 0 đến đúng n? Hai cách khác thứ tự bước được coi là hai cách đi khác nhau. Kết quả lấy modulo **1.000.000.007**, vì số cách có thể rất lớn.

Đặt dp[i] = số dãy bước đến đúng vị trí i, tính theo modulo. Điều kiện cơ sở:

~~~text
dp[0] = 1   (có đúng một dãy bước rỗng để đứng tại 0)

dp[i] = dp[i-1] + dp[i-2] + ... + dp[i-K]
        chỉ lấy các chỉ số không âm, với i = 1..n.
~~~

**Vì sao công thức đúng?** Dãy bước cuối cùng đến i có một bước dài j nằm trong [1,K] và j ≤ i; trước bước cuối đó là một dãy hợp lệ đến i−j. Các nhóm dãy theo bước cuối j không giao nhau và phủ hết phương án. Vì vậy tổng số cách là tổng các dp[i−j].

Nếu n = 0, trả 1 theo định nghĩa dãy bước rỗng. Nếu K = 1, chỉ có một dãy toàn bước 1. Nếu K ≥ n và n ≥ 1, mọi cách phân tách n thành các số dương đều hợp lệ, số cách là 2^(n−1) trước khi lấy modulo.

## 5. Đếm trạng thái và vòng chuyển của cách làm trực tiếp

Chúng ta có **n + 1 trạng thái**, từ dp[0] tới dp[n]. Để tính dp[i], cần xét **min(i,K)** giá trị từ dp[max(0,i−K)] tới dp[i−1].

Tổng số lần cộng thực tế là:

~~~text
Số phép cộng = sum_{i=1..n} min(i, K).

Nếu K <= n:
  = (1 + 2 + ... + K) + (n-K) × K
  = K(K+1)/2 + (n-K)K.

Nếu K > n:
  = 1 + 2 + ... + n
  = n(n+1)/2.
~~~

Do đó thời gian của hiện thực trực tiếp là **O(n × min(n,K))**, thường được viết gọn thành cận trên **O(nK)**. Khi K rất lớn so với n, O(nK) không phải cận chặt: vòng trong không thể xét hơn i vị trí.

Bộ nhớ phụ của ví dụ trực tiếp là **O(n)** cho mảng dp; không có ngăn xếp đệ quy. Các phép cộng được lấy modulo sau mỗi lần cộng để tránh làm biến tích lũy tăng theo số cách thật.

Với n = 7, K = 3:

~~~text
dp[0..7] = [1, 1, 2, 4, 7, 13, 24, 44].

dp[3] = dp[2] + dp[1] + dp[0] = 2 + 1 + 1 = 4.
dp[4] = dp[3] + dp[2] + dp[1] = 4 + 2 + 1 = 7.
dp[7] = dp[6] + dp[5] + dp[4] = 24 + 13 + 7 = 44.
~~~

Một đáp án nho nhỏ có thể được tính bằng đệ quy thuần, nhưng nếu không memoization, cùng các bài toán con được gọi lặp lại rất nhiều lần; phân tích “n trạng thái” **không áp dụng** cho đệ quy thuần không nhớ kết quả.

## 6. Giảm chi phí chuyển bằng cửa sổ tổng: O(n) thời gian

Thay vì cộng lại K ô trước mỗi dp[i], duy trì một biến **window** là tổng các giá trị dp đang nằm trong cửa sổ cần dùng. Trước khi tính dp[i], giữ bất biến:

~~~text
window = sum(dp[j]), với max(0, i-K) <= j < i,
         tất cả tính modulo MOD.
~~~

Khởi tạo cho i=1: window = dp[0] = 1.

Tại mỗi i:

1. Gán **dp[i] = window**, vì đó chính là tổng mà công thức chuyển yêu cầu.
2. Thêm dp[i] vào window để chuẩn bị tính dp[i+1].
3. Nếu i−K ≥ 0, bỏ dp[i−K] khỏi window: phần tử này không còn thuộc cửa sổ của i+1.
4. Chuẩn hóa phép cộng/trừ modulo về miền [0, MOD−1].

Cụ thể:

~~~text
dp[0] = 1
window = 1
for i from 1 to n:
    dp[i] = window
    window = (window + dp[i]) mod MOD
    if i-K >= 0:
        window = (window - dp[i-K] + MOD) mod MOD
~~~

**Chứng minh bất biến:** trước bước i, window là tổng đúng các dp[j] có j từ max(0,i−K) tới i−1. Sau khi thêm dp[i], tập giá trị thành đoạn cũ cộng i. Nếu i−K ≥ 0, loại đúng dp[i−K] — phần tử thấp nhất rời khỏi cửa sổ khi tăng i lên i+1. Vì vậy window mới là tổng từ max(0,i+1−K) tới i, đúng cho bước kế. Cơ sở i=1 đã đúng, nên theo quy nạp mọi dp[i] đúng.

**Độ phức tạp:** vẫn có n+1 trạng thái, nhưng xử lý mỗi i chỉ còn O(1) phép toán, tổng **O(n)** thời gian. Mảng dp trong Java vẫn dài n+1, nên **O(n)** bộ nhớ phụ. Nếu chỉ cần giá trị cuối, có thể lưu vòng các giá trị gần nhất và giảm bộ nhớ xuống O(min(n,K)) với cách lập chỉ số thích hợp; đó là một cải tiến **khác** cần chứng minh riêng.

Điểm mấu chốt: **không cần giảm số trạng thái để giảm thời gian**. Ta đã thay đổi cách tính một chuyển từ “quét lại các phương án” thành “dùng kết quả tổng hợp đang được duy trì”.

## 7. So sánh trước và sau tối ưu phép chuyển

| Tiêu chí | DP cộng trực tiếp | DP dùng cửa sổ tổng |
| --- | --- | --- |
| Trạng thái | dp[0..n] | dp[0..n] |
| Số trạng thái | n+1 | n+1 |
| Các ứng viên của dp[i] | min(i,K) | Đã được tổng hợp trong window |
| Công việc trên mỗi i | O(min(i,K)) | O(1) |
| Tổng thời gian | O(n min(n,K)) | O(n) |
| Bộ nhớ hiện thực minh họa | O(n) | O(n) |
| Điều kiện đúng | K≥1, bước dương, cộng modulo | Cùng điều kiện; thêm bất biến cửa sổ |

Đây là mô hình của nhiều tối ưu DP: dùng **prefix sum, sliding window, deque đơn điệu, cấu trúc cây hoặc convex hull trick** để giảm số ứng viên được xét lại. Tuy nhiên, mỗi kỹ thuật có tiền điều kiện riêng, ví dụ phép tổng có thể thêm/bớt bằng phép cộng/trừ, deque tối ưu cần quan hệ đơn điệu thích hợp, CHT cần dạng hàm tuyến tính tương ứng. Không được gắn một kỹ thuật vào mọi công thức chuyển chỉ vì cùng chứa chữ “min” hoặc “max”.

## 8. Ví dụ 2: ba lô 0/1 và một chuyển O(1) cho mỗi trạng thái

Cho n món, món i có trọng lượng w_i > 0 và giá trị v_i ≥ 0. Ba lô có sức chứa nguyên W ≥ 0; mỗi món được chọn **không quá một lần**. Mục tiêu là tối đa tổng giá trị với tổng trọng lượng không vượt W.

Đặt F(i,c) = giá trị tối ưu khi chỉ được dùng **i món đầu tiên** với sức chứa c.

Cơ sở F(0,c)=0. Với món i (đánh số 1..n):

~~~text
F(i,c) = F(i-1,c)                              nếu w_i > c.

F(i,c) = max(F(i-1,c), F(i-1,c-w_i) + v_i)       nếu w_i <= c.
~~~

Có **(n+1)(W+1) trạng thái** trong bảng hai chiều đầy đủ. Mỗi trạng thái xét tối đa **hai lựa chọn**, mỗi lựa chọn đọc ô cũ và cộng/so sánh O(1). Do đó:

- Thời gian bảng đầy đủ: **O(nW)** cho n,W đủ lớn; viết chính xác hơn O(n(W+1)).
- Bộ nhớ bảng hai chiều: O(nW).
- Nếu chỉ cần giá trị tối ưu chứ không cần truy vết danh sách món, ta có thể nén còn **một mảng dp[0..W]**, tức **O(W)** bộ nhớ, trong khi tổng số trạng thái logic vẫn là n(W+1).

**Bẫy quan trọng về bộ nhớ:** việc hiện thực chỉ có một mảng W+1 ô **không** có nghĩa thuật toán chỉ tính W+1 trạng thái trong toàn bộ quá trình. Mỗi lần xử lý một món, các ô mang một lớp i mới; có n lượt, nên thời gian vẫn O(nW).

## 9. Vì sao ba lô 0/1 phải duyệt sức chứa giảm dần?

Bản nén một chiều dùng:

~~~text
dp[c] = giá trị tối ưu với sức chứa c sau khi đã xét các món trước.

Với mỗi món (w,v):
    cho c đi từ W xuống w:
        dp[c] = max(dp[c], dp[c-w] + v).
~~~

**Duyệt giảm dần** bảo đảm khi tính dp[c] cho món hiện tại, dp[c−w] vẫn là trạng thái của **lớp i−1**, tức chưa sử dụng món đó. Nhờ vậy mỗi món được chọn nhiều nhất một lần.

Nếu duyệt c **tăng dần**, dp[c−w] có thể vừa được cập nhật bằng chính món hiện tại, dẫn đến việc chọn lại món đó nhiều lần. Khi ấy công thức trở nên giống **unbounded knapsack**, không còn đúng cho 0/1.

Phản ví dụ ngắn:

~~~text
Chỉ có một món: w=2, v=4; W=4.

Duyệt c tăng từ 2 tới 4:
  dp[2] = 4.
  dp[4] = dp[2] + 4 = 8  (chọn cùng món hai lần: SAI cho 0/1).

Duyệt c giảm từ 4 xuống 2:
  dp[4] vẫn bằng 0 khi xử lý c=4.
  dp[2] = 4.
Đáp án 0/1 cho W=4 chỉ là 4.
~~~

Ví dụ dữ liệu gồm (w,v) = (2,4), (3,5), (4,10), W=6, chọn món trọng lượng 2 và 4 cho tổng giá trị **14**, tốt hơn mọi lựa chọn còn lại. Chương trình Java phía dưới trả đúng 14.

Điều kiện w_i > 0 giúp phân tích rõ ràng; chương trình từ chối w_i = 0 hoặc âm. Có thể định nghĩa bài toán riêng cho món trọng lượng 0, nhưng khi đó cần xử lý rõ ràng việc chọn một lần và tác động đến vòng cập nhật.

## 10. Giảm bộ nhớ khác với giảm thời gian

Xem hai phép tối ưu vừa gặp:

- **Đếm bước có cửa sổ tổng:** giữ nguyên số trạng thái, giảm công việc tính **mỗi trạng thái** từ O(K) xuống O(1), nên giảm **thời gian** từ O(nK) xuống O(n) trong trường hợp K≤n; với mảng đầy đủ bộ nhớ vẫn O(n).
- **Ba lô nén một chiều:** giữ nguyên số lớp trạng thái logic và mỗi chuyển vẫn O(1), nhưng chỉ giữ một lớp tại một thời điểm, nên giảm **bộ nhớ** từ O(nW) xuống O(W); **thời gian không đổi**.

Một cải tiến chỉ thật sự có ích nếu biết nó tối ưu đại lượng nào. Việc bỏ lưu một bảng để tiết kiệm RAM đôi khi làm mất khả năng **truy ngược lời giải**, hoặc buộc phải tính lại trạng thái gây thêm thời gian.

Các hình thức nén bảng thường dựa vào **phụ thuộc chỉ tới một vài lớp trước**. Nếu công thức mới cần giá trị ở nhiều lớp xa hơn, không thể tùy tiện ghi đè một lớp mà không giữ đủ thông tin.

## 11. Đếm đúng các chuyển trong những mẫu DP thường gặp

| Bài toán / định nghĩa trạng thái | Số trạng thái S | Số chuyển ứng viên mỗi trạng thái | Thời gian thường gặp |
| --- | --- | --- | --- |
| Fibonacci có memo | O(n) | O(1) | O(n) |
| LCS độ dài của hai chuỗi n,m | O(nm) | O(1), nhìn hai/ba ô | O(nm) |
| Đếm bước với tối đa K | O(n) | O(min(n,K)) trực tiếp | O(n min(n,K)) |
| Đếm bước với cửa sổ | O(n) | O(1) sau duy trì tổng | O(n) |
| Ba lô 0/1 | O(nW) | Tối đa 2 phép chọn O(1) | O(nW) |
| Coin change đếm/số xu tối ưu, m loại xu | O(A) trạng thái tổng tiền A | O(m) phương án mỗi mức A trong hiện thực xét mọi xu | O(Am) |
| Đường đi trên lưới R×C | O(RC) | Thường 2–4 ô lân cận | O(RC) |
| Matrix-chain multiplication | O(n²) đoạn liên tiếp | O(n) điểm tách | O(n³) |
| Bitmask TSP với n đỉnh | O(n2^n) trạng thái (mask,last) | O(n) đỉnh tiếp theo | O(n²2^n) |

**Điều kiện của bảng:** chi phí một chuyển được giả định O(1) trừ khi ghi rõ khác. Với LCS, ô phụ thuộc vào ký tự và một số ô đã tính. Với matrix-chain, mỗi đoạn [l,r] xét mọi điểm tách k giữa l và r nên số ứng viên phụ thuộc độ dài đoạn; lấy O(n) làm cận trên cho ra O(n³).

Với bitmask TSP, không phải mọi (mask,last) đều hợp lệ, nhưng cận trên O(n2^n) vẫn đúng và mô tả được bản chất hàm mũ. Nếu dùng bảng kích thước n2^n, chi phí khởi tạo bảng cũng phải tính vào tổng.

**Một mẹo quan trọng:** khi đưa ra S×D, hãy chỉ ra **điểm nào trong code thực hiện D lần lặp**. Nếu không tìm thấy vòng lặp tương ứng nhưng vẫn viết O(SD), rất có thể đang đếm thừa hoặc chưa hiểu đúng phép chuyển.

## 12. Khi nào số trạng thái không đúng bằng kích thước mảng DP?

Trong **top-down memoization**, chỉ các lời gọi thực sự đạt tới mới được lưu. Ví dụ bài toán có trạng thái (vị trí, tổng hiện tại), về lý thuyết ta có thể cho một cận trên lớn, nhưng các giá trị tổng không thể đạt đến sẽ không bao giờ xuất hiện trong map.

Trong **bottom-up**, tác giả thường tạo bảng hình chữ nhật và chạy vòng for toàn miền. Khi đó phần lớn ô có thể được duyệt kể cả nếu một số trạng thái không có đường đi hợp lệ. Chi phí thời gian có thể theo kích thước bảng dù số trạng thái “có ích” ít hơn.

Bài toán trên đồ thị với memo đếm đường đi cũng phải xét **chu kỳ**. Không thể chỉ thấy có map rồi khẳng định mỗi trạng thái tính đúng một lần: nếu quan hệ phụ thuộc có chu trình mà không có thứ tự topo/điều kiện dừng phù hợp, chương trình có thể đệ quy vòng. Quy hoạch động chuẩn cần đồ thị phụ thuộc không chu trình hoặc một cấu trúc giải thích cách xử lý chu trình.

Mỗi state cần được **khởi tạo, nhận diện và lưu đúng một kết quả** cho một bộ tham số. Nếu hàm tạo khóa/copy dữ liệu tốn O(n), phần overhead đó cũng phải được tính, không tự động coi truy cập memo luôn O(1).

## 13. Bộ nhớ phụ, chi phí khởi tạo và phục hồi kết quả

Độ phức tạp thời gian và bộ nhớ thường có câu chuyện khác nhau:

- **Bảng 2D:** O(nW) ô là O(nW) bộ nhớ nếu giữ tất cả.
- **Rolling array:** chỉ giữ một hoặc vài lớp cần thiết, bộ nhớ có thể giảm xuống O(W).
- **Top-down:** map chứa số trạng thái đã thăm và **call stack** có độ sâu bằng chuỗi phụ thuộc dài nhất; quên stack có thể gây thiếu bộ nhớ hoặc StackOverflowError.
- **Giữ dấu vết quyết định:** nếu bài toán cần in các món đã chọn, đường đi hay chuỗi thao tác, có thể cần thêm parent/choice table hoặc tính lại một phần trạng thái.
- **Khởi tạo bảng:** tạo một mảng lớn, đặt giá trị sentinel hoặc điền vô cực tốn thời gian tỉ lệ số ô được khởi tạo.
- **Bản sao và đối tượng:** map entry, key object, boxed integer, danh sách tạm và iterator có overhead thực tế ngoài phần giá trị số nguyên.

Ví dụ, zeroOneKnapsack trong mã dùng long[W+1] để chứa giá trị tối ưu, O(W) ô dữ liệu. Mỗi long có 8 byte dữ liệu số, chưa tính overhead và căn chỉnh JVM. Nếu W cực lớn, thuật toán có thể hết bộ nhớ dù n rất nhỏ.

**Lưu ý:** khi tính bộ nhớ *phụ*, thường không tính dữ liệu đầu vào đã có; khi lên ngân sách heap thực tế phải tính **cả đầu vào lẫn bảng DP**.

## 14. Độ phức tạp giả đa thức và độ lớn của giá trị số

Với ba lô 0/1, cách giải O(nW) **không được xem là đa thức theo số bit biểu diễn W** trong ý nghĩa lý thuyết phức tạp đầu vào tổng quát. W là **giá trị số**, còn chỉ cần khoảng log₂(W+1) bit để ghi nó.

Ví dụ hai bài toán cùng có n=100 nhưng W=100 và W=1.000.000.000 có độ dài biểu diễn W chỉ chênh một vài chục bit, trong khi bảng DP theo sức chứa khác nhau mười triệu lần về số ô. Vì vậy thuật toán này được gọi là **giả đa thức (pseudo-polynomial)**.

Tương tự, nếu một DP dùng trục trạng thái bằng tổng giá trị, số tiền hoặc tọa độ có miền rất lớn, phải hỏi miền đó là một giá trị số lớn hay một kích thước input thực sự. Không viết “O(nW) là nhanh vì có hai vòng for” mà bỏ qua việc W có thể vượt khả năng cấp phát.

Các hướng xử lý tùy bài toán: dùng một thuật toán khác, chuyển trạng thái theo giá trị nếu tổng giá trị nhỏ, lưu trạng thái thưa bằng map, xấp xỉ có bảo đảm khi được phép, hoặc ràng buộc W phù hợp với dữ liệu. Không có cách tối ưu chung cho mọi biến thể.

## 15. Java 17+: hai ví dụ về số trạng thái và chi phí chuyển

Chương trình dưới đây có ba hàm chính:

1. **waysSlow(n,K):** đếm cách đi bằng DP một chiều, mỗi trạng thái duyệt trực tiếp các bước từ 1 tới K; thời gian O(n min(n,K)), bộ nhớ O(n).
2. **waysFast(n,K):** cùng công thức và tập trạng thái, nhưng dùng sliding window theo modulo; thời gian O(n), bộ nhớ của hiện thực này O(n).
3. **zeroOneKnapsack(weight,value,W):** bài toán 0/1 với trọng lượng dương, giá trị không âm; mỗi món duyệt sức chứa giảm dần, dùng long[] nhằm chứa tổng giá trị lớn hơn int; thời gian O(n(W+1)), bộ nhớ O(W+1).

Các hàm từ chối n âm, K không dương, capacity âm, mảng null, chiều dài weight/value khác nhau, hoặc trọng lượng/giá trị vi phạm hợp đồng. Với W hoặc n quá lớn, việc cấp phát mảng vẫn có thể thất bại do giới hạn heap; bài mẫu không định nghĩa một ngưỡng RAM sản xuất.

Lưu đầy đủ mã vào **DpStateTransitionCosts.java**:

~~~java
import java.util.Arrays;

public final class DpStateTransitionCosts {
    private static final int MOD = 1_000_000_007;

    private DpStateTransitionCosts() {
    }

    private static void checkJumps(int n, int maxJump) {
        if (n < 0 || maxJump <= 0) {
            throw new IllegalArgumentException("n >= 0 and maxJump > 0 required");
        }
    }

    public static int waysSlow(int n, int maxJump) {
        checkJumps(n, maxJump);
        int[] dp = new int[n + 1];
        dp[0] = 1;
        for (int i = 1; i <= n; i++) {
            long sum = 0L;
            int earliest = Math.max(0, i - maxJump);
            for (int j = earliest; j < i; j++) {
                sum += dp[j];
                if (sum >= MOD) {
                    sum -= MOD;
                }
            }
            dp[i] = (int) sum;
        }
        return dp[n];
    }

    public static int waysFast(int n, int maxJump) {
        checkJumps(n, maxJump);
        int[] dp = new int[n + 1];
        dp[0] = 1;
        long window = 1L;

        for (int i = 1; i <= n; i++) {
            dp[i] = (int) window;
            window = (window + dp[i]) % MOD;
            if (i - maxJump >= 0) {
                window = (window - dp[i - maxJump] + MOD) % MOD;
            }
        }
        return dp[n];
    }

    public static long zeroOneKnapsack(
            int[] weight, int[] value, int capacity) {
        if (weight == null || value == null
                || weight.length != value.length || capacity < 0) {
            throw new IllegalArgumentException("invalid knapsack input");
        }
        for (int i = 0; i < weight.length; i++) {
            if (weight[i] <= 0 || value[i] < 0) {
                throw new IllegalArgumentException("weight > 0 and value >= 0");
            }
        }

        long[] dp = new long[capacity + 1];
        for (int item = 0; item < weight.length; item++) {
            int w = weight[item];
            int v = value[item];
            for (int c = capacity; c >= w; c--) {
                dp[c] = Math.max(dp[c], dp[c - w] + v);
            }
        }
        return dp[capacity];
    }

    private static long bruteKnapsack(
            int[] weight, int[] value, int capacity) {
        long best = 0L;
        int subsets = 1 << weight.length;
        for (int mask = 0; mask < subsets; mask++) {
            int used = 0;
            long earned = 0L;
            for (int i = 0; i < weight.length; i++) {
                if ((mask & (1 << i)) != 0) {
                    used += weight[i];
                    earned += value[i];
                }
            }
            if (used <= capacity) {
                best = Math.max(best, earned);
            }
        }
        return best;
    }

    private static long bruteWays(int remaining, int maxJump) {
        if (remaining == 0) {
            return 1L;
        }
        long result = 0L;
        for (int jump = 1; jump <= maxJump && jump <= remaining; jump++) {
            result += bruteWays(remaining - jump, maxJump);
        }
        return result;
    }

    private static void verify() {
        int checkedJumps = 0;
        for (int n = 0; n <= 40; n++) {
            for (int k = 1; k <= 15; k++) {
                int slow = waysSlow(n, k);
                int fast = waysFast(n, k);
                if (slow != fast) {
                    throw new AssertionError("ways mismatch: n=" + n + " k=" + k);
                }
                if (n <= 12 && k <= 4
                        && slow != bruteWays(n, k) % MOD) {
                    throw new AssertionError("ways brute mismatch");
                }
                checkedJumps++;
            }
        }

        int[] weights = {1, 2, 3};
        int[] values = {0, 1, 2};
        int checkedKnapsack = 0;
        for (int n = 0; n <= 4; n++) {
            int combinations = 1;
            for (int i = 0; i < n; i++) {
                combinations *= 9;
            }
            for (int code = 0; code < combinations; code++) {
                int rest = code;
                int[] w = new int[n];
                int[] v = new int[n];
                for (int i = 0; i < n; i++) {
                    int choice = rest % 9;
                    rest /= 9;
                    w[i] = weights[choice / 3];
                    v[i] = values[choice % 3];
                }
                for (int capacity = 0; capacity <= 6; capacity++) {
                    if (zeroOneKnapsack(w, v, capacity)
                            != bruteKnapsack(w, v, capacity)) {
                        throw new AssertionError(
                                "knapsack mismatch: " + Arrays.toString(w)
                                + ", " + Arrays.toString(v)
                                + ", capacity=" + capacity);
                    }
                    checkedKnapsack++;
                }
            }
        }

        long largeValue = zeroOneKnapsack(
                new int[] {1, 1, 1},
                new int[] {Integer.MAX_VALUE, Integer.MAX_VALUE,
                        Integer.MAX_VALUE}, 3);
        if (largeValue != 3L * Integer.MAX_VALUE) {
            throw new AssertionError("long-value knapsack failed");
        }

        System.out.println("Verified " + checkedJumps + " jump pairs: PASS");
        System.out.println("Verified " + checkedKnapsack + " knapsack cases: PASS");
        System.out.println("Large-value knapsack: PASS");
    }

    public static void main(String[] args) {
        System.out.println("waysSlow(7,3) = " + waysSlow(7, 3));
        System.out.println("waysFast(7,3) = " + waysFast(7, 3));
        System.out.println("waysFast(0,3) = " + waysFast(0, 3));
        System.out.println("waysFast(7,1) = " + waysFast(7, 1));
        System.out.println("waysFast(7,20) = " + waysFast(7, 20));
        System.out.println("knapsack(C=6) = " + zeroOneKnapsack(
                new int[] {2, 3, 4}, new int[] {4, 5, 10}, 6));
        System.out.println("knapsack(C=0) = " + zeroOneKnapsack(
                new int[] {2, 3, 4}, new int[] {4, 5, 10}, 0));
        verify();
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac DpStateTransitionCosts.java
java DpStateTransitionCosts
~~~

Kết quả stdout chính xác:

~~~text
waysSlow(7,3) = 44
waysFast(7,3) = 44
waysFast(0,3) = 1
waysFast(7,1) = 1
waysFast(7,20) = 64
knapsack(C=6) = 14
knapsack(C=0) = 0
Verified 615 jump pairs: PASS
Verified 51667 knapsack cases: PASS
Large-value knapsack: PASS
~~~

Chương trình dùng modulo cố định 1.000.000.007 cho bài đếm bước, và kết quả số nguyên long không modulo cho ba lô. Vì vậy không được so sánh trực tiếp hai cách tính dưới các kiểu dữ liệu khác nhau mà quên modulo.

## 16. Giải thích bộ kiểm thử độc lập của chương trình

**Đếm bước:** với n = 0..40 và K = 1..15, có 41 × 15 = **615 cặp**. Chương trình so sánh waysSlow và waysFast trên từng cặp. Riêng n ≤ 12 và K ≤ 4, nó còn so với **đệ quy vét cạn** không ghi nhớ kết quả. Đệ quy vét cạn này chỉ chạy trên trường hợp nhỏ và không được tính vào độ phức tạp của hai hàm sản xuất.

**Ba lô:** mỗi món được lấy trong 9 cấu hình (w thuộc {1,2,3}, v thuộc {0,1,2}). Với n từ 0 tới 4:

~~~text
Số dãy món = 9^0 + 9^1 + 9^2 + 9^3 + 9^4
           = 1 + 9 + 81 + 729 + 6561
           = 7381.

Mỗi dãy thử 7 sức chứa W=0..6.
Số ca đối chiếu = 7381 × 7 = 51667.
~~~

Mỗi ca được so với oracle duyệt tất cả **2^n tập con**, kiểm tra tổng trọng lượng và tổng giá trị theo đúng hợp đồng chọn tối đa một lần. Đó là kiểm thử độc lập với công thức DP. Ngoài ra, mẫu thử ba giá trị Integer.MAX_VALUE với mỗi trọng lượng bằng 1 kiểm tra việc dùng long để chứa tổng giá trị có thể vượt int.

Dòng PASS chỉ mô tả các ca đã đối chiếu. Việc tin một thuật toán đúng trên mọi dữ liệu còn dựa trên **chứng minh trạng thái, base case, phụ thuộc và công thức chuyển**; kiểm thử không thay thế chứng minh.

## 17. Các lỗi phổ biến khi tính độ phức tạp DP

1. **Đếm mỗi kích thước mảng mà bỏ qua vòng trong:** n ô dp nhưng mỗi ô quét K ứng viên thì không phải O(n).
2. **Đếm mọi tổ hợp trạng thái mà không xét tính hợp lệ:** interval DP với l<r không dùng toàn bộ cặp l,r.
3. **Lấy S×D là kết quả chính xác tuyệt đối:** khi số chuyển biến đổi theo trạng thái, cần tổng Σ_s D(s) để có cận chặt hơn.
4. **Bỏ qua chi phí xử lý chuyển:** gọi hàm tính tổng O(n) bên trong vòng K ứng viên làm mỗi trạng thái thành O(nK).
5. **Bỏ qua khởi tạo:** tạo bảng O(nW) cũng tốn O(nW) thời gian/không gian dù chỉ tính một phần trạng thái.
6. **Gộp trạng thái thiếu tham số:** memo sai khóa có thể làm thuật toán sai, dù nhìn có ít state hơn.
7. **Tin có memo là chắc chắn hữu hạn:** quan hệ chuyển có chu trình cần xử lý riêng.
8. **Nhầm số ô đang lưu với tổng số trạng thái tính:** rolling array O(W) không giảm tổng n(W+1) trạng thái logic.
9. **Duyệt ba lô 0/1 tăng dần:** vô tình dùng một món nhiều lần.
10. **Cộng lại cả cửa sổ sau khi đã duy trì tổng:** làm mất lợi ích O(1) mỗi trạng thái.
11. **Trừ modulo ra số âm:** phải chuẩn hóa window vào [0,MOD−1].
12. **Quên độ sâu stack:** top-down có thể tiêu thụ O(n) stack hoặc bị StackOverflowError nếu chuỗi phụ thuộc dài.
13. **Bỏ qua tính giả đa thức:** W lớn không trở nên nhỏ chỉ vì được lưu trong một biến int.
14. **Không đếm chi phí xây dựng/khôi phục:** tiền xử lý, copy mảng, sorting, parent pointers cũng là công việc.
15. **Nhầm chứng minh Big-O với chứng minh đúng:** một công thức chuyển chạy O(1) vẫn có thể sai nếu dùng trạng thái chưa tính hoặc ghi đè giá trị cần dùng.

## 18. Quy trình phân tích một lời giải DP mới

Hãy dùng một checklist lặp lại được:

1. **Đặc tả đầu vào/đầu ra:** xác định biến lớn nhất, ràng buộc số học và có cần khôi phục phương án hay không.
2. **Nêu trạng thái bằng câu tiếng Việt:** dp[i][j] biểu diễn chính xác điều gì; giá trị ở biên rỗng và trạng thái không thể đạt là gì?
3. **Liệt kê miền hợp lệ:** từng chiều có bao nhiêu lựa chọn; có điều kiện ràng buộc làm giảm miền hay không?
4. **Chốt base cases:** mô tả các trạng thái khởi tạo và chi phí khởi tạo.
5. **Viết công thức chuyển có tham số:** những trạng thái phụ thuộc nào, bao nhiêu ứng viên, chi phí cho mỗi ứng viên?
6. **Chỉ ra thứ tự duyệt:** bottom-up cần trạng thái nguồn đã có; top-down cần memoization/điều kiện dừng hợp lệ.
7. **Đếm tổng công việc:** chi phí dựng dữ liệu + tổng công việc trên các trạng thái + khôi phục.
8. **Đếm bộ nhớ:** số ô lưu cùng lúc, buffer, map overhead, stack và dấu vết lựa chọn.
9. **Tìm cách tối ưu đúng chỗ:** giảm số trạng thái, giảm ứng viên, giảm giá mỗi ứng viên, hoặc nén bộ nhớ là những mục tiêu khác nhau.
10. **Đối chiếu với oracle nhỏ:** vét cạn các n nhỏ, bao gồm đầu vào rỗng, biên, giá trị trùng, trường hợp tối ưu và số học lớn.

Khi kết luận, nên viết **O(S × D × C)** kèm lời giải thích S, D và C thay vì một biểu thức Big-O không thể gắn với bất cứ vòng lặp cụ thể nào.

## 19. Bài tập tự luyện

**Bài 1 — Đếm bước:** với n=8, K=2, lập bảng dp từ 0..8. Đếm tổng số ứng viên được cộng ở bản trực tiếp và so với số lần cập nhật window của bản tối ưu. Viết chứng minh bất biến window.

**Bài 2 — Đổi K:** với n=20, so sánh K=2 và K=100. Tính Σ min(i,K) để thấy vì sao cận O(nK) có thể rất lỏng khi K>n.

**Bài 3 — Ba lô 0/1:** với ba món (w,v) = (1,3), (2,5), (3,6), W=4, hãy dựng bảng F(i,c). Sau đó nén về một chiều, ghi rõ thứ tự duyệt c và số ô bộ nhớ dùng cùng lúc.

**Bài 4 — Truy ngược lời giải:** phiên bản ba lô một chiều chỉ trả giá trị. Đề xuất cách lưu quyết định hoặc tái tính một số lớp để tìm tập món đã chọn, rồi phân tích thời gian và bộ nhớ bổ sung.

**Bài 5 — Interval DP:** bài toán nhân chuỗi ma trận có n ma trận. Định nghĩa dp[l][r] và giải thích vì sao có O(n²) đoạn nhưng mỗi đoạn xét tới O(n) điểm tách. Hãy phân tích tổng thời gian O(n³) và không gian O(n²).

**Bài 6 — Top-down:** với trạng thái dp[position][sum], tạo ví dụ có nhiều trạng thái không đạt được; so sánh việc lưu bằng HashMap chỉ cho trạng thái được thăm với mảng hai chiều duyệt hết. Đừng quên chi phí map và stack.

**Kết luận:** khi phân tích DP, **số trạng thái chỉ là một nửa câu chuyện**. Phải biết mỗi trạng thái được tính một lần hay nhiều lần, phải xét bao nhiêu phương án, và mỗi phương án tốn bao nhiêu công việc. Tối ưu cửa sổ tổng có thể giảm **thời gian tính mỗi trạng thái**, còn rolling array có thể giảm **bộ nhớ của những lớp trạng thái**. Biết tách các đại lượng này giúp giải thích đúng độ phức tạp và chọn cải tiến thực sự có giá trị.

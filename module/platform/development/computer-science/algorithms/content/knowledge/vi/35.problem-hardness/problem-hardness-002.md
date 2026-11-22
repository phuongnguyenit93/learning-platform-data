# Đầu vào theo số bit và giới hạn của cách đếm theo giá trị

Khi phân tích **độ khó bài toán**, cần phân biệt hai đại lượng dễ bị nhầm: **giá trị số được ghi trong đầu vào** và **số bit cần dùng để biểu diễn giá trị ấy**. Một số nguyên dương rất lớn có thể được viết bằng tương đối ít bit; ngược lại, một thuật toán “đếm từ 1 tới số nguyên đó” có thể mất số bước **lũy thừa theo độ dài đầu vào**.

Ví dụ, số \(N=2^{40}=1\,099\,511\,627\,776\) có biểu diễn nhị phân dài **41 bit** (một bit 1 và 40 bit 0). Nhưng vòng lặp thực hiện N bước cần hơn **một nghìn tỷ lượt**, không thể được gọi là chạy đa thức theo chỉ **41 bit input**. Tương tự, bài toán Subset Sum có một cách giải **quy hoạch động theo tổng đích S** chạy \(O(nS)\); đó là thuật toán **giả đa thức** (*pseudo-polynomial*) chứ không phải đa thức theo kích thước mã hóa nhị phân nếu S có thể rất lớn.

Bài học đi từ độ dài mã hóa số nguyên, mô hình tính toán theo bit và theo word, sự khác biệt giữa đa thức và giả đa thức, các ví dụ đếm theo miền giá trị, tới Subset Sum, chứng minh trạng thái DP, thuật toán **meet-in-the-middle** dựa trên số lượng phần tử, giới hạn bộ nhớ/tràn số và việc phân biệt **NP-đầy đủ yếu** với **NP-khó mạnh**. Có chương trình **Java 17+ độc lập** gồm hai phương pháp giải, một oracle vét cạn, các bộ kiểm tự động và kết quả đầu ra có thể tái lập.

## 1. “Kích thước đầu vào” thực sự là gì?

Trong nhiều bài học nhập môn, ta viết thời gian là \(O(n)\), \(O(n\log n)\) hoặc \(O(n^2)\). Nhưng chữ n cần có **ý nghĩa rõ ràng**:

- Nếu input là một mảng gồm n phần tử, n liên hệ trực tiếp với **số phần tử cần đọc**.
- Nếu input chỉ là **một số nguyên N**, n không nhất thiết là N; kích thước biểu diễn của số N theo nhị phân chỉ khoảng \(\log_2 N\) bit.
- Nếu input gồm cả n số \(a_i\) và một ngưỡng S, kích thước mã hóa phụ thuộc **số lượng** các số và **độ dài bit** của từng số, không chỉ phụ thuộc n hoặc S riêng lẻ.

Một thuật toán được gọi là **đa thức theo kích thước input** khi thời gian được chặn bởi \(O(L^c)\) với một hằng số c, trong đó L là **độ dài mã hóa** (tính theo bit, hoặc ký tự trên một bảng chữ cái cố định) của toàn bộ input.

Nếu bài toán đầu vào chỉ là số N viết ở hệ nhị phân, với N≥1:

\[
\boxed{b(N)=\lfloor\log_2 N\rfloor+1.}
\]

Với N=0, có thể quy ước biểu diễn bằng **1 bit** là chữ số 0.

Ví dụ:

| Số thập phân N | Biểu diễn nhị phân | Số bit |
|---:|---|---:|
| 0 | 0 | 1 |
| 1 | 1 | 1 |
| 2 | 10 | 2 |
| 3 | 11 | 2 |
| 7 | 111 | 3 |
| 8 | 1000 | 4 |
| 15 | 1111 | 4 |
| 16 | 10000 | 5 |
| 1.000 | 1111101000 | 10 |
| 1.000.000 | 11110100001001000000 | 20 |
| \(2^{40}\) | 1 và 40 bit 0 | 41 |

Mỗi khi nhân N với 2, ta thường chỉ cần **thêm một bit**. Vì vậy mức tăng của **giá trị số** và mức tăng của **độ dài biểu diễn** rất khác nhau.

### Một dãy số được mã hóa như thế nào?

Giả sử input là n số nguyên không âm \(a_1,\ldots,a_n\), và thêm một số S. Nếu dùng nhị phân, tổng số bit của các giá trị về bậc là:

\[
L=\Theta\!\left(n+\sum_{i=1}^{n}\log_2(a_i+1)+\log_2(S+1)\right)
\]

khi tính cả chi phí tách các số hoặc mã hóa độ dài theo một quy ước hợp lý. Biểu thức này thể hiện ý tưởng quan trọng: **viết một số lớn không đòi hỏi số ký tự tỉ lệ với chính giá trị của nó**.

Cách đếm bit chính xác phụ thuộc định dạng, dấu âm, phần mô tả n và dấu phân cách. Nhưng các khác biệt thông thường ấy không biến một vòng lặp \(\Theta(S)\) thành đa thức theo \(\Theta(\log S)\).

## 2. Mã hóa nhị phân và mã hóa đơn phân

Một số nguyên N có thể được biểu diễn theo nhiều cách.

**Nhị phân (*binary encoding*):**

~~~text
N = 13
binary = 1101
4 bits
~~~

**Đơn phân (*unary encoding*):** dùng N ký hiệu để biểu diễn N:

~~~text
N = 13
unary = 1111111111111
13 symbols
~~~

Với N lớn:

\[
\boxed{L_{\text{binary}}=\Theta(\log(N+1))}
\]

trong khi:

\[
\boxed{L_{\text{unary}}=\Theta(N)}.
\]

Nếu một thuật toán đếm từ 1 đến N trong \(\Theta(N)\) bước:

- Khi N được cung cấp bằng **đơn phân**, \(\Theta(N)\) là tuyến tính theo độ dài biểu diễn.
- Khi N được cung cấp bằng **nhị phân**, \(\Theta(N)=2^{\Theta(L)}\), tức là **hàm mũ** theo số bit ở những đầu vào đại diện.

Điều này giải thích vì sao khi nghiên cứu tính đa thức của thuật toán số, ta luôn phải xác định **cách mã hóa đầu vào**. Trong các bài toán số nguyên thông thường, nhị phân hoặc thập phân với cơ số cố định là giả định tự nhiên; thập phân cũng chỉ cần \(\Theta(\log N)\) chữ số nên khác nhị phân chủ yếu ở hằng số.

## 3. Ví dụ đầu vào ngắn nhưng vòng lặp rất dài

Xét chương trình:

~~~java
static long countToN(long n) {
    long result = 0;
    for (long i = 0; i < n; i++) {
        result++;
    }
    return result;
}
~~~

Nếu bỏ qua giới hạn miền long của máy và coi đây là ví dụ thuật toán, thời gian là:

\[
T(N)=\Theta(N).
\]

Nhưng số bit b của N chỉ \(\Theta(\log N)\), nên trong trường hợp N gần \(2^b\):

\[
\boxed{T(N)=\Theta(2^b)}.
\]

**Một vòng lặp tuyến tính theo giá trị N không nhất thiết là đa thức theo độ dài input.**

Ngược lại, nếu mục tiêu là tính \(2^N\) dưới dạng kết quả **đã nén** như một biểu thức, chỉ đọc N là một việc nhỏ; nhưng nếu mục tiêu là **in ra toàn bộ số \(2^N\) ở dạng nhị phân**, output có N+1 bit. Khi đó riêng việc **xuất kết quả** đã cần \(\Omega(N)\) bước. Vì vậy đánh giá thuật toán phải ghi rõ **dạng input và dạng output**; không được bỏ qua kích thước đầu ra.

### Lũy thừa nhanh khác gì?

Đối với phép tính \(a^N\bmod m\), thuật toán **bình phương và nhân** xử lý các bit của N:

~~~text
result = 1
base = a mod m

while N > 0:
    if lowBit(N) == 1:
        result = result * base mod m
    base = base * base mod m
    N = floor(N/2)
~~~

Vòng lặp có **O(log N)** lần nhân mô-đun, tức O(b) phép nhân theo số bit của số mũ. Điều này tốt hơn nhân a với chính nó N lần.

Tuy nhiên, nếu m không vừa một word máy, mỗi phép nhân mô-đun không còn là O(1) trong mô hình bit; phải tính thêm chi phí nhân/chia số nguyên nhiều bit. Điểm cần học là **giảm số bước từ phụ thuộc giá trị N xuống phụ thuộc số bit của N**, đồng thời nêu rõ mô hình chi phí cho phép toán số học.

## 4. Mô hình word-RAM và độ phức tạp theo bit

Trong lập trình thi đấu, người ta thường giả sử:

- Một số nguyên nằm gọn trong **word** (ví dụ int hoặc long).
- Cộng, so sánh, truy cập ô mảng và phép toán word cơ bản tốn O(1).
- Một mảng n phần tử tốn O(n) word.

Đây là **mô hình word-RAM**, thích hợp nếu dữ liệu bị chặn bởi miền kiểu số máy.

Trong **mô hình bit** (*bit complexity*), nếu số nguyên cần b bit:

- Đọc/ghi toàn bộ số tốn \(\Omega(b)\) bit.
- Phép cộng hai số b bit có thể cần O(b) thao tác bit.
- Phép nhân cổ điển cần O(b²) thao tác bit; có thuật toán nhân nhanh hơn.
- So sánh và lưu trữ cũng phụ thuộc độ dài bit.

Khi phân tích độ khó theo lý thuyết, không nên giả vờ một số nguyên có **một triệu bit** vẫn cộng/nhân trong O(1) chỉ vì trong Java có `BigInteger`.

### Phân biệt hai nguồn chi phí

Có hai câu hỏi:

1. **Thuật toán thực hiện bao nhiêu phép toán số học?**
2. **Mỗi phép toán thao tác trên các số dài bao nhiêu bit?**

Một thuật toán chạy O(n) phép nhân trên số nguyên có thể có **bit complexity** lớn hơn O(n), nếu các số trung gian dài nhiều bit.

Tuy vậy, trong bài này, mối nguy lớn nhất của **cách đếm theo giá trị** không chỉ là từng phép toán đắt, mà là **số bước tính đã phụ thuộc trực tiếp S hoặc U**, tức có thể tăng theo \(2^{\text{số bit}}\).

## 5. Thế nào là thuật toán giả đa thức?

Một thuật toán được gọi là **giả đa thức** (*pseudo-polynomial time*) khi số bước được chặn bằng đa thức theo **số lượng phần tử** và **giá trị số của các tham số đầu vào**, nhưng không nhất thiết là đa thức theo **độ dài biểu diễn nhị phân** của các tham số ấy.

Ví dụ:

\[
\boxed{T(n,S)=O(nS)}.
\]

Đây là đa thức theo hai đại lượng **n và S**. Nhưng nếu S có b bit, S có thể gần \(2^b\), cho nên:

\[
O(nS)=O(n2^b).
\]

Trong trường hợp xấu theo b, thời gian có thể là **hàm mũ theo số bit của S**.

### Thuật toán giả đa thức không phải thuật toán mũ theo n

Cần phân biệt rõ hai hướng tăng input:

- Cố định S nhỏ, tăng n: O(nS) có thể rất tốt.
- Cố định n nhỏ, tăng số bit b của S: O(nS) có thể trở nên không thực tế.
- Cố định cả n lẫn bit-size, không có nghịch lý: đây là các tham số hữu hạn.

Một thuật toán có thể là **giả đa thức**, chạy rất nhanh trên phần lớn test thực tế, và vẫn **không chứng minh bài toán nằm trong P** theo mã hóa nhị phân.

### Không được dùng nhãn “đa thức” thiếu biến

Viết “thuật toán DP O(nS) là đa thức” là thiếu điều kiện. Cách nói chính xác:

> Thuật toán là đa thức theo n và giá trị S, nhưng **giả đa thức** theo kích thước mã hóa nhị phân khi S là một phần của input và không bị chặn đa thức bởi độ dài input.

Tương tự, `O(C)` theo **giá trị sức chứa C** không đồng nghĩa `O(b)` theo **b bit** lưu C.

## 6. Một ví dụ kinh điển: Counting Sort theo miền giá trị

Giả sử cần sắp n số nguyên thuộc \([0,U]\).

**Counting Sort** tạo mảng đếm độ dài U+1 rồi:

1. Đếm số lần xuất hiện của mỗi giá trị.
2. Duyệt mảng đếm để xây kết quả.
3. Có thể thực hiện bản ổn định khi cần giữ thứ tự tương đối của phần tử bằng cách dùng tích lũy và đặt từ phải sang trái.

Chi phí:

\[
\boxed{O(n+U)\text{ thời gian},\quad O(n+U)\text{ bộ nhớ ở bản ổn định điển hình}.}
\]

Nếu U chỉ bằng 1000, Counting Sort có thể rất hiệu quả dù n lớn.

Nhưng nếu input chứa một số lớn tới \(U=10^{12}\), U được viết với khoảng **40 bit**, trong khi mảng đếm dài gần **một nghìn tỷ phần tử** là không khả thi.

### Lỗi tư duy thường gặp

“Counting Sort O(n+U) nên là sắp xếp tuyến tính” chỉ đúng khi **U không quá lớn so với n hoặc giới hạn tài nguyên**. Nếu U là tham số số nguyên không bị chặn, thời gian/bộ nhớ theo U có thể là hàm mũ theo số bit mô tả U.

### Hướng thay thế

- Nếu cần sắp xếp các số nguyên bất kỳ trong kiểu long: dùng **comparison sort** O(n log n), không phụ thuộc vào độ lớn tuyệt đối của các số trong phân tích word-RAM.
- Nếu số lượng **giá trị phân biệt d** nhỏ: có thể dùng `Map`/cấu trúc đếm thưa rồi sắp d khóa, không tạo mảng độ dài U.
- Nếu chỉ muốn kiểm tra số một lần xuất hiện hay không: `HashSet` không cần quét mọi giá trị từ 0 tới U.

Đây là một ví dụ của **lựa chọn cấu trúc dữ liệu theo tính thưa và miền giá trị**.

## 7. Các dạng “đếm theo giá trị” khác

| Phương pháp | Tham số giá trị | Độ phức tạp điển hình | Điều cần nhớ |
|---|---|---|---|
| Counting Sort | miền giá trị U | O(n+U) | O(U) bộ nhớ/đếm có thể rất lớn |
| Sàng Eratosthenes đến N | giới hạn N | O(N log log N) | N chỉ cần O(log N) bit để nhập |
| Subset Sum DP theo tổng | tổng đích S | O(nS) | giả đa thức nếu S mã hóa nhị phân |
| 0/1 Knapsack DP theo sức chứa | sức chứa W | O(nW) | W có thể vượt khả năng cấp phát |
| Coin Change DP theo số tiền | số tiền A | O(mA) với m loại tiền ở mô hình thường | giá trị A quyết định số trạng thái |
| BFS trên không gian trạng thái [0..U] | U | O(U + E) cho đồ thị trạng thái hữu hạn tương ứng | cần xét có thực sự phải duyệt tất cả trạng thái hay không |
| Lũy thừa bằng nhân lặp N lần | số mũ N | O(N) phép nhân | bình phương nhanh giảm số lượt xuống O(log N) |

**Không phải mọi bài có thời gian O(N) theo giá trị đều “không thể cải tiến”.** Một số bài có thuật toán phụ thuộc bit-length, một số có kỹ thuật phân khối/meet-in-the-middle, và một số bài liệt kê có output vốn đã lớn. Phải phân tích **mục tiêu output** và **cấu trúc bài toán**, không chỉ đọc cận O trên giấy.

## 8. Subset Sum: bài toán minh họa cho giả đa thức

**Bài toán quyết định Subset Sum**:

Cho n số nguyên **không âm** \(w_0,w_1,\ldots,w_{n-1}\) và một tổng đích S không âm. Hỏi có tồn tại một **tập con chỉ số** I sao cho:

\[
\boxed{\sum_{i\in I}w_i=S?}
\]

Mỗi vị trí được chọn **tối đa một lần**. Đây là phiên bản **0/1**, không phải bài cho dùng một trọng số lặp vô hạn lần.

Ví dụ:

~~~text
weights = [3,34,4,12,5,2]
target  = 9
~~~

Có lời giải vì:

\[
4+5=9.
\]

Ngược lại, với cùng dãy và đích 30, ta không có lời giải:

- Nếu chọn 34, tổng đã vượt 30.
- Nếu không chọn 34, tổng tối đa từ các phần tử còn lại chỉ \(3+4+12+5+2=26\).

Do đó:

~~~text
target 9  -> true
target 30 -> false
~~~

### Phương pháp vét cạn

Mỗi phần tử có hai lựa chọn **chọn/không chọn**, tạo \(2^n\) tập con. Thử tất cả các tập con cần thời gian hàm mũ theo n trong trường hợp tổng quát.

Nếu n=6, có 64 tập con; còn n=60 có \(2^{60}\) tập con, nên vét cạn trực tiếp không thích hợp.

Nhưng nếu các số và S nhỏ, có cách tiếp cận khác tận dụng **miền giá trị của tổng**.

## 9. Subset Sum DP theo tổng S

Xây một mảng boolean:

\[
dp[s]=\text{“có thể đạt đúng tổng s từ những phần tử đã xử lý”}.
\]

Ban đầu chưa chọn phần tử nào:

\[
dp[0]=true,\qquad dp[s>0]=false.
\]

Khi xử lý một trọng số \(w\), tổng s đạt được nếu:

- Không lấy phần tử hiện tại và trước đó đã đạt s; hoặc
- Lấy phần tử hiện tại một lần, nên trước đó phải đạt \(s-w\).

Công thức:

\[
\boxed{
dp_{\text{mới}}[s]
=dp_{\text{cũ}}[s]\lor
(s\ge w\ \land\ dp_{\text{cũ}}[s-w]).
}
\]

Chỉ cần quan tâm s từ 0 tới S, vì các trọng số đều **không âm**: một tổng trung gian lớn hơn S không thể giảm về S bằng cách cộng thêm trọng số không âm.

### Tối ưu xuống một chiều

Ta không cần giữ hai mảng `old` và `new`, có thể cập nhật tại chỗ nhưng phải duyệt **s từ lớn xuống nhỏ**:

~~~text
dp[0] = true

for each weight w:
    for s = S down to w:
        dp[s] = dp[s] OR dp[s-w]

return dp[S]
~~~

Vì \(s-w\le s\), khi duyệt **giảm dần**, `dp[s-w]` chưa bị phần tử w hiện tại sử dụng để cập nhật lần thứ hai ở cùng lượt. Mỗi vị trí nguồn do đó chỉ được chọn tối đa một lần.

### Vì sao duyệt tăng dần là sai cho 0/1?

Giả sử chỉ có một trọng số w=3, đích S=6.

Nếu duyệt s tăng:

- Ở s=3, `dp[3]=true` nhờ `dp[0]`.
- Đến s=6, nếu tiếp tục đọc `dp[3]` **vừa được cập nhật từ cùng trọng số**, ta đặt `dp[6]=true`.

Điều đó tương đương dùng số 3 **hai lần**, trái với phiên bản Subset Sum 0/1.

**Quy tắc nhớ:**

- **0/1** sử dụng từng phần tử tối đa một lần: thường duyệt s **giảm dần**.
- **Unbounded** cho phép dùng một loại trọng số nhiều lần: có thể dùng phép duyệt **tăng dần** với định nghĩa trạng thái thích hợp.

Không nên học thuộc quy tắc một cách mơ hồ; phải xác định chính xác giá trị `dp[s-w]` thuộc **lượt trước** hay đã được cập nhật trong **lượt hiện tại**.

## 10. Chạy tay DP trên một ví dụ

Với:

~~~text
weights = [3,34,4,12,5,2]
target = 9
~~~

Liệt kê các tổng ≤9 có thể đạt sau mỗi lượt:

| Đã xét phần tử | Các tổng đạt được ≤9 |
|---|---|
| Chưa xét gì | {0} |
| Thêm 3 | {0,3} |
| Thêm 34 | {0,3} |
| Thêm 4 | {0,3,4,7} |
| Thêm 12 | {0,3,4,7} |
| Thêm 5 | {0,3,4,5,7,8,9} |
| Thêm 2 | {0,2,3,4,5,6,7,8,9} |

Khi xử lý 5, tổng 9 xuất hiện do **4+5**, vì trước đó `dp[4]=true`.

Trường hợp đích 30, tổng các trọng số không vượt 30 là 26, nên mọi trạng thái đích 30 đều false.

### Bất biến chứng minh tính đúng

Sau khi xử lý i phần tử đầu tiên:

> Với mọi s từ 0 tới S, `dp[s]` bằng true **nếu và chỉ nếu** tồn tại một tập con của i vị trí đầu tiên có tổng đúng s.

**Cơ sở:** i=0, chỉ tập rỗng cho tổng 0.

**Bước quy nạp:** xét phần tử \(w_i\). Mọi tập con của i+1 vị trí hoặc **không chứa** i, khi ấy tổng s đã đạt từ i vị trí cũ; hoặc **có chứa** i, khi ấy phần còn lại phải có tổng s−w_i từ i vị trí cũ. Công thức OR xét đủ và chỉ những khả năng đó.

Khi duyệt ngược tại chỗ, mọi trạng thái dùng làm nguồn vẫn phản ánh i vị trí cũ; vì thế cập nhật tương đương với công thức hai mảng. Sau n lượt, `dp[S]` trả đúng đáp án.

## 11. Độ phức tạp của Subset Sum DP

Với n trọng số và đích S:

- Mảng boolean có **S+1 ô**.
- Mỗi trọng số xét tối đa S+1 trạng thái.
- Thời gian trong mô hình word-RAM là:

\[
\boxed{O(nS)}.
\]

- Bộ nhớ phụ:

\[
\boxed{O(S)}.
\]

Đây là một cải thiện rất lớn so với \(O(2^n)\) khi S nhỏ. Nhưng nếu S có b bit, S có thể gần \(2^b\); lúc ấy cả thời gian và bộ nhớ có thể trở nên quá lớn **chỉ với một tham số b tương đối nhỏ**.

Ví dụ:

~~~text
S = 1_000
bit length ≈ 10
dp boolean length = 1_001  -> nhỏ

S = 1_000_000
bit length ≈ 20
dp boolean length = 1_000_001  -> có thể xử lý

S = 1_000_000_000_000
bit length ≈ 40
dp boolean length ≈ 1 nghìn tỷ -> không thực tế
~~~

Lưu ý: trong Java `boolean[]` có chi phí cấp phát, giới hạn kích thước mảng và cách bố trí bộ nhớ theo JVM; không nên lấy số ô nhân một byte như một cam kết chính xác cho mọi máy.

### Kích thước số học có thể phá việc cấp phát

Không nên viết ngay:

~~~java
boolean[] dp = new boolean[target + 1];
~~~

khi `target` không được kiểm tra. Nếu target= `Integer.MAX_VALUE`, phép cộng `target+1` **tràn int**. Nếu target chỉ vài trăm triệu, mảng cũng có thể gây `OutOfMemoryError`.

Code trong bài đặt **giới hạn tài nguyên rõ ràng** trước khi cấp phát. Đây không phải giới hạn toán học của Subset Sum DP; nó là giới hạn minh họa nhằm ngăn chạy vô tình trên input mà phương pháp theo tổng không phù hợp.

## 12. Giải pháp thay thế: meet-in-the-middle

Khi **n nhỏ hoặc vừa** nhưng các giá trị rất lớn, ta có thể dùng **meet-in-the-middle (MITM)** cho Subset Sum:

1. Chia n trọng số thành hai nửa.
2. Liệt kê tổng của mọi tập con nửa trái, có khoảng \(2^{\lfloor n/2\rfloor}\) tổng.
3. Liệt kê tổng của mọi tập con nửa phải, có khoảng \(2^{\lceil n/2\rceil}\) tổng.
4. Sort các tổng nửa phải.
5. Với mỗi tổng trái x không lớn hơn S, tìm nhị phân tổng phải đúng bằng **S−x**.

Nếu tìm thấy x+y=S, có một tập con đạt đích; nếu không, không có.

### Vì sao MITM đúng?

Mọi tập con của toàn bộ n vị trí có thể tách **duy nhất** thành:

- Một tập con các vị trí của nửa trái.
- Một tập con các vị trí của nửa phải.

Tổng của tập con toàn bộ là **tổng trái + tổng phải**. MITM liệt kê đầy đủ mọi tổng có thể của từng nửa rồi kiểm tồn tại cặp có tổng S. Không bỏ sót tập con nào.

### Độ phức tạp

Đặt \(m=\lceil n/2\rceil\).

- Số tổng mỗi nửa: \(O(2^m)\).
- Dùng công thức sinh tổng từ một bit thấp nhất để tạo các tổng: O(\(2^m\)) phép cộng, ngoài chi phí lưu trữ.
- Sort nửa phải: O(\(2^m m\)).
- Mỗi tổng trái tìm nhị phân: O(m), tổng O(\(2^m m\)).

Vì vậy:

\[
\boxed{\text{Thời gian }O(n2^{n/2}),\quad
\text{bộ nhớ }O(2^{n/2}).}
\]

Ở đây ký hiệu \(2^{n/2}\) bỏ qua chênh lệch làm tròn khi n lẻ.

MITM **không phải thuật toán đa thức theo n**; nó vẫn là hàm mũ theo n, nhưng giảm từ \(2^n\) còn khoảng \(2^{n/2}\), và đặc biệt **không tạo mảng dài S**.

### Khi nào MITM phù hợp?

- n≈30–40, giá trị/trọng số hoặc tổng đích có thể rất lớn.
- Bộ nhớ đủ giữ các tổng của một nửa.
- Có thể liệt kê mọi tập con của **mỗi nửa**, nhưng không thể duyệt cả \(2^n\) tập con.

Mã Java giới hạn n≤36 để tránh vô tình tạo mảng khổng lồ; đó là **chính sách tài nguyên ví dụ**. Với n=36, mỗi nửa có tối đa \(2^{18}=262\,144\) tổng, phù hợp hơn nhiều so với \(2^{36}\) tập con của toàn bộ dãy.

## 13. Cùng một input, hai hướng độ phức tạp khác nhau

Cho:

~~~text
weights = [1_000_000_000_039,
           1_000_000_000_061,
           11, 13, 29]

target = 1_000_000_000_050
~~~

Tổng đích có khoảng **40 bit**, trong khi n chỉ là 5.

Với Subset Sum theo giá trị, muốn tạo `dp[0..target]` thì cần hơn **một nghìn tỷ trạng thái** — hoàn toàn không phù hợp.

Với MITM:

- Nửa trái có 2 phần tử: tối đa \(2^2=4\) tổng.
- Nửa phải có 3 phần tử: tối đa \(2^3=8\) tổng.
- Tìm một cặp: \(1\,000\,000\,000\,039+11=1\,000\,000\,000\,050\).

Do đó kết quả là **true**, dù target rất lớn.

Nếu đổi target thành \(1\,000\,000\,000\,051\), không có tổ hợp nào trong năm trọng số trên đạt đúng đích, nên kết quả **false**.

### Lựa chọn theo miền tham số

| Điều kiện | Thuật toán thường phù hợp |
|---|---|
| n lớn, tổng đích S nhỏ | DP theo tổng O(nS) |
| n nhỏ, S rất lớn | MITM O(n2^(n/2)) |
| n rất nhỏ | Vét cạn tập con trực tiếp O(2^n) dễ viết |
| n lớn, S cũng rất lớn | Cần xem cấu trúc đặc biệt, phương pháp xấp xỉ, branch-and-bound hoặc chấp nhận độ khó cao |
| Cần nghiệm gần đúng thay vì quyết định exact | Có thể cân nhắc các lược đồ xấp xỉ phù hợp |
| Trọng số âm | DP không âm trong bài không áp dụng trực tiếp; cần biến đổi/trạng thái khác |

**Không được khẳng định MITM tốt hơn DP trong mọi trường hợp.** Nếu n=200 và S=1000, DP O(nS) rất nhẹ, còn \(2^{100}\) tổng của mỗi nửa là không khả thi.

## 14. Vì sao Subset Sum là ví dụ nổi bật trong độ phức tạp?

Bài toán quyết định **Subset Sum** với các số nguyên dương được mã hóa bằng nhị phân là một bài toán **NP-đầy đủ**. Tuy nhiên nó có thuật toán DP theo tổng giá trị **giả đa thức**.

Không có mâu thuẫn nào ở đây:

- “NP-đầy đủ” trong phân loại chuẩn xét đầu vào với cách mã hóa **ngắn gọn**, như nhị phân.
- “DP O(nS)” cho phép thời gian phụ thuộc trực tiếp **giá trị S**, trong khi S có thể tăng hàm mũ theo số bit được cung cấp.
- Vì vậy DP không phải bằng chứng cho thuật toán đa thức theo **độ dài bit input**.

Subset Sum thường được gọi là **NP-đầy đủ yếu** (*weakly NP-complete*) vì có thuật toán giả đa thức phù hợp. Thuật ngữ “yếu” **không** có nghĩa “bài dễ trong mọi trường hợp”; nó phân biệt với các bài toán mà ngay cả khi những số xuất hiện bị chặn đủ nhỏ theo kích thước input, tính NP-khó vẫn tồn tại theo nghĩa **mạnh**.

### So với NP-khó mạnh

Một ví dụ kinh điển của **NP-đầy đủ mạnh** (*strongly NP-complete*) là **3-Partition** với những ràng buộc số học đặc thù. Nói rất ngắn, độ khó của nó vẫn còn khi các giá trị số được chặn đa thức theo kích thước mô tả tương ứng.

Nếu một bài toán quyết định NP-đầy đủ mạnh có thuật toán giả đa thức theo nghĩa thông thường, ta có thể thu được thuật toán đa thức trên những instance bị chặn số học ấy; điều này sẽ dẫn tới **P=NP**. Vì vậy, với giả định **P≠NP**, không trông đợi một thuật toán giả đa thức giải exact mọi instance của bài toán NP-đầy đủ mạnh.

**Lưu ý:** Đây là phân biệt về **độ khó trong lý thuyết tính toán**, không phải quy tắc kết luận một bài thực tế chỉ bằng việc nhìn thấy số lớn hay nhỏ. Muốn áp dụng, phải xét đúng định nghĩa bài toán, cách mã hóa và các phép giảm đa thức liên quan.

## 15. Bitset DP và các tối ưu không đổi bản chất giả đa thức

Trong Subset Sum, một cách tối ưu phổ biến dùng **bitset**. Bit thứ s bằng 1 khi đạt được tổng s:

~~~text
reachable bitset starts with bit 0 = 1

for each weight w:
    reachable |= (reachable << w)
~~~

Phép dịch trái w bit chuyển mọi tổng cũ s thành s+w. Phép OR giữ cả trường hợp “không lấy” và “lấy” trọng số hiện tại.

Nếu bitset được biểu diễn bằng các **word máy** dài W bit, mỗi lượt có thể xử lý nhiều trạng thái bằng một thao tác word. Cận thô trong mô hình word-RAM là:

\[
O(n\lceil S/W\rceil)
\]

phép toán word thích hợp, cộng các chi phí dịch/OR và quản lý biên theo triển khai.

Đây thường là tối ưu lớn so với mảng boolean khi S vừa phải. Nhưng cần nhớ:

\[
\boxed{\text{Bitset vẫn cần }\Theta(S)\text{ bit nhớ}.}
\]

Nếu S≈\(10^{12}\), bitset vẫn không giải quyết được vấn đề **miền giá trị quá lớn**. Nó giảm **hằng số/tốc độ xử lý theo word**, không biến thuật toán thành đa thức theo \(\log S\).

### Những hướng cải thiện khác

- **Sparse set of reachable sums:** lưu những tổng thật sự xuất hiện thay vì mọi s từ 0..S; có thể hữu ích nếu tổng đạt được thưa, nhưng trường hợp xấu số tổng phân biệt vẫn tăng rất lớn.
- **Meet-in-the-middle:** đổi phụ thuộc S thành phụ thuộc hàm mũ của n/2.
- **Branch-and-bound:** cắt các nhánh không thể đạt đích bằng cận trên/dưới; có thể rất tốt trên dữ liệu cụ thể, nhưng không bảo đảm đa thức mọi instance.
- **Approximation:** nếu yêu cầu tối ưu có thể chấp nhận sai số, có thể lượng tử hóa giá trị hoặc dùng lược đồ xấp xỉ trong một số bài như Knapsack. Không được gọi một phép xấp xỉ là solver exact khi bài cần quyết định chính xác bằng hoặc không bằng S.

## 16. Độ dài số nguyên và tràn kiểu số trong Java

Java có các kiểu cơ bản:

- `int`: 32 bit có dấu.
- `long`: 64 bit có dấu.
- `BigInteger`: số nguyên độ dài tùy ý, giới hạn thực tế bởi bộ nhớ và thời gian.

Một `long` không âm tối đa có giá trị:

\[
2^{63}-1.
\]

Nó chiếm **64 bit trong biểu diễn two's complement có dấu**, nhưng số bit **cần để viết trị tuyệt đối không âm** \(2^{63}-1\) là 63. Hai khái niệm “bề rộng kiểu dữ liệu” và “bit-length của giá trị” **không giống nhau**.

### Đếm bit với BigInteger

Với số nguyên không âm N:

~~~java
int bitLength = BigInteger.valueOf(N).bitLength();
~~~

Ví dụ `1_000_000_000_000L` cần **40 bit** để viết dạng nhị phân không dấu. Với giá trị 0, `BigInteger.ZERO.bitLength()` trả 0 theo API BigInteger; nếu cần “số chữ số của biểu diễn 0” theo quy ước học thuật, dùng **1**, không trộn hai quy ước.

### Không được cộng rồi mới kiểm tràn

Nếu có hai `long` dương x,y, biểu thức `x+y` có thể tràn sang âm trước khi so với S. Có thể dùng:

~~~java
long sum = Math.addExact(x, y);
~~~

để nhận `ArithmeticException` thay vì kết quả wrap-around sai. Với miền số vượt long, dùng `BigInteger` và phân tích chi phí thao tác theo bit.

Trong ví dụ MITM, chương trình dùng `Math.addExact` khi tạo các tổng tập con. Nếu một tổ hợp vượt long, chương trình **từ chối tính tiếp** thay vì im lặng trả đáp án có thể sai. Đây là giới hạn đã công bố của bản dùng long; để hỗ trợ các tổng tùy ý, cần bản **BigInteger**.

## 17. Java 17+: DP theo giá trị, MITM và oracle vét cạn

Chương trình **BitLengthAndPseudoPolynomialDemo.java** sau minh họa hai phương pháp giải **Subset Sum không âm** với cùng hợp đồng:

- Trọng số `long[]` không âm; mỗi **vị trí được chọn tối đa một lần**.
- Tổng đích không âm. Tập con rỗng cho tổng 0, nên target=0 luôn true.
- `subsetSumByValue`: `target` kiểu int để cấp phát mảng chỉ số tổng; từ chối target>2.000.000 theo **ngân sách RAM minh họa**. Trọng số lớn hơn target có thể bỏ qua vì tất cả trọng số không âm.
- `subsetSumMeetInMiddle`: `target` kiểu long; hỗ trợ n≤36 trong demo; không tạo mảng theo target; dùng `Math.addExact` khi sinh các tổng của mỗi nửa.
- `bruteOracle`: kiểm thử một số nhỏ phần tử bằng cây chọn/bỏ, không sử dụng DP hay MITM.
- Có ví dụ target nhỏ, target 40-bit, trường hợp không tồn tại, chặn cấp phát, từ chối trọng số âm và **400 bộ test có seed cố định**.

**Đây là chương trình độc lập trên Java 17 trở lên:**

~~~java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;

public class BitLengthAndPseudoPolynomialDemo {
    static final int DP_TARGET_LIMIT = 2_000_000;
    static final int MITM_ITEM_LIMIT = 36;

    static void validateWeights(long[] weights) {
        Objects.requireNonNull(weights, "weights");
        for (long w : weights) {
            if (w < 0) {
                throw new IllegalArgumentException(
                    "weights must be nonnegative"
                );
            }
        }
    }

    // 0/1 Subset Sum by numeric target S.
    // O(n*S) time, O(S) memory. Not polynomial in bit-length of S.
    static boolean subsetSumByValue(long[] weights, int target) {
        validateWeights(weights);
        if (target < 0) {
            throw new IllegalArgumentException(
                "target must be nonnegative"
            );
        }
        if (target > DP_TARGET_LIMIT) {
            throw new IllegalArgumentException(
                "target exceeds demo memory budget (2000000)"
            );
        }

        boolean[] reachable = new boolean[target + 1];
        reachable[0] = true;

        for (long weight : weights) {
            if (weight > target) {
                continue;
            }

            int w = (int) weight;
            // Descending order: each input position used at most once.
            for (int sum = target; sum >= w; sum--) {
                if (reachable[sum - w]) {
                    reachable[sum] = true;
                }
            }
        }
        return reachable[target];
    }

    // Subset sums of a range [from,to) of at most 18 positions.
    // DP over masks reuses sums of smaller masks.
    static long[] enumerateSums(
        long[] weights, int from, int to
    ) {
        int len = to - from;
        int count = 1 << len;
        long[] sums = new long[count];

        for (int mask = 1; mask < count; mask++) {
            int bit = Integer.numberOfTrailingZeros(mask);
            int priorMask = mask & (mask - 1);
            sums[mask] = Math.addExact(
                sums[priorMask], weights[from + bit]
            );
        }
        return sums;
    }

    // No array indexed by target value.
    // O(n*2^(n/2)) time, O(2^(n/2)) memory for n<=36.
    static boolean subsetSumMeetInMiddle(
        long[] weights, long target
    ) {
        validateWeights(weights);
        if (target < 0) {
            throw new IllegalArgumentException(
                "target must be nonnegative"
            );
        }
        if (weights.length > MITM_ITEM_LIMIT) {
            throw new IllegalArgumentException(
                "too many elements for meet-in-middle demo (max 36)"
            );
        }

        int mid = weights.length / 2;
        long[] left = enumerateSums(weights, 0, mid);
        long[] right = enumerateSums(
            weights, mid, weights.length
        );
        Arrays.sort(right);

        for (long leftSum : left) {
            if (leftSum > target) {
                continue; // Remaining sums are nonnegative.
            }
            long requiredRight = target - leftSum;
            if (Arrays.binarySearch(right, requiredRight) >= 0) {
                return true;
            }
        }
        return false;
    }

    // Independent exponential oracle, only for tiny instances.
    // "remaining" never becomes negative because weights >= 0.
    static boolean bruteOracle(
        long[] weights, int index, long remaining
    ) {
        if (remaining == 0) {
            return true;
        }
        if (index == weights.length) {
            return false;
        }

        // Choose current position, if it cannot exceed remaining.
        if (weights[index] <= remaining
                && bruteOracle(
                    weights, index + 1,
                    remaining - weights[index]
                )) {
            return true;
        }
        // Or skip current position.
        return bruteOracle(weights, index + 1, remaining);
    }

    static void crossCheckRandomCases() {
        Random rng = new Random(2026L);
        int cases = 400;

        for (int t = 0; t < cases; t++) {
            int n = rng.nextInt(15); // n in [0,14].
            long[] weights = new long[n];
            for (int i = 0; i < n; i++) {
                weights[i] = rng.nextInt(31);
            }
            int target = rng.nextInt(151);

            boolean dp = subsetSumByValue(weights, target);
            boolean mitm = subsetSumMeetInMiddle(
                weights, target
            );
            boolean brute = bruteOracle(
                weights, 0, target
            );

            if (dp != mitm || dp != brute) {
                throw new AssertionError(
                    "Mismatch on test " + t
                    + ": weights=" + Arrays.toString(weights)
                    + ", target=" + target
                );
            }
        }

        System.out.println(
            "Cross-check DP/MITM/brute: PASS (400 cases)"
        );
    }

    public static void main(String[] args) {
        long[] small = {3, 34, 4, 12, 5, 2};
        long[] large = {
            1_000_000_000_039L,
            1_000_000_000_061L,
            11L, 13L, 29L
        };
        long hugeTarget = 1_000_000_000_050L;

        System.out.println(
            "Binary bits for 1000000000000: "
            + BigInteger.valueOf(
                1_000_000_000_000L
            ).bitLength()
        );
        System.out.println(
            "Small weights: " + Arrays.toString(small)
        );
        System.out.println(
            "DP target 9: " + subsetSumByValue(small, 9)
        );
        System.out.println(
            "DP target 30: " + subsetSumByValue(small, 30)
        );
        System.out.println(
            "DP target 0: " + subsetSumByValue(small, 0)
        );
        System.out.println(
            "MITM target 9: " + subsetSumMeetInMiddle(small, 9)
        );
        System.out.println(
            "MITM target 30: " + subsetSumMeetInMiddle(small, 30)
        );
        System.out.println(
            "Large target bit length: "
            + BigInteger.valueOf(hugeTarget).bitLength()
        );
        System.out.println(
            "MITM large target: "
            + subsetSumMeetInMiddle(large, hugeTarget)
        );
        System.out.println(
            "MITM nearby target: "
            + subsetSumMeetInMiddle(
                large, 1_000_000_000_051L
            )
        );

        try {
            subsetSumByValue(small, 5_000_000);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                "DP memory guard: " + ex.getMessage()
            );
        }

        try {
            subsetSumMeetInMiddle(new long[] {5, -1}, 4);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                "Negative weight rejected: " + ex.getMessage()
            );
        }

        crossCheckRandomCases();
    }
}
~~~

Lưu mã thành **BitLengthAndPseudoPolynomialDemo.java** rồi biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BitLengthAndPseudoPolynomialDemo.java
java BitLengthAndPseudoPolynomialDemo
~~~

**Stdout theo bộ input và seed cố định:**

~~~text
Binary bits for 1000000000000: 40
Small weights: [3, 34, 4, 12, 5, 2]
DP target 9: true
DP target 30: false
DP target 0: true
MITM target 9: true
MITM target 30: false
Large target bit length: 40
MITM large target: true
MITM nearby target: false
DP memory guard: target exceeds demo memory budget (2000000)
Negative weight rejected: weights must be nonnegative
Cross-check DP/MITM/brute: PASS (400 cases)
~~~

### Ý nghĩa của hai dòng kết quả lớn

Số 1.000.000.000.000 được viết trong **40 bit** dạng nhị phân. Trong khi đó, ví dụ MITM giải được Subset Sum với target 1.000.000.000.050 bằng cách liệt kê tối đa 4+8 tổng của hai nửa, thay vì cấp phát mảng 1.000.000.000.051 ô.

Kết quả `true` đến từ \(1\,000\,000\,000\,039+11\). Target gần bên cạnh 1.000.000.000.051 không thể tạo bởi bất kỳ tập con nào của năm trọng số mẫu.

### Ranh giới demo là chủ động

- DP **không** khẳng định target>2.000.000 luôn không giải được. Nó báo lỗi ngân sách bộ nhớ vì **cách triển khai theo giá trị** không thích hợp cho đầu vào đó.
- MITM **không** khẳng định n>36 là bài vô nghiệm. Nó từ chối vì số tập con cần lưu tăng nhanh theo n.
- Nếu một tổng tập con vượt long, `Math.addExact` báo lỗi số học. Đây không phải câu trả lời false cho Subset Sum.
- Mã không hỗ trợ trọng số âm trong cả hai phương pháp; điều kiện không âm là giả thiết trong các chứng minh cắt bỏ tổng >target.

## 18. Vì sao mã Java dùng hai loại target?

`subsetSumByValue` dùng `int target` vì nó cần mảng `reachable[target+1]`. Trong Java, độ dài mảng là số nguyên thuộc miền int và còn bị giới hạn bởi RAM, nên ngay cả target là 1 tỷ cũng rất không thực tế trong bài này.

`subsetSumMeetInMiddle` dùng `long target` vì nó **không đánh chỉ số mảng theo target**. Các mảng của MITM được đánh chỉ số theo **mask tập con của một nửa**, có độ dài \(2^{n/2}\) dưới giới hạn demo. Target lớn chỉ ảnh hưởng giá trị cộng/trừ và so sánh của `long`, không quyết định trực tiếp số ô được cấp phát.

Tuy nhiên, điều này không đồng nghĩa MITM có độ phức tạp số học độc lập với độ dài bit của mọi input. Trong mô hình word-RAM, các phép cộng/so sánh long tính như O(1); nếu dùng `BigInteger` cho các giá trị hàng nghìn bit, mỗi phép toán vẫn có chi phí theo bit. Điểm mấu chốt là MITM **tránh phụ thuộc tuyến tính vào giá trị số của target**.

## 19. Kiểm thử và xác minh độc lập

Mã có oracle `bruteOracle`:

- Tại mỗi vị trí i, thử **lấy** nếu trọng số không vượt tổng còn lại.
- Nếu không tìm được, thử **bỏ** vị trí ấy.
- Khi tổng còn lại bằng 0, trả true.
- Khi hết vị trí mà tổng còn lại chưa bằng 0, trả false.

Với trọng số không âm, cách dùng **remaining** không âm là chính xác: nếu một trọng số đã lớn hơn phần còn thiếu, lấy nó không thể giúp đạt đích.

Oracle này không dùng mảng `dp[s]`, không sinh hai nửa, không binary search, nên là một cơ chế kiểm thử **độc lập** với hai solver chính. Nó có thời gian trường hợp xấu \(O(2^n)\), do đó **chỉ dùng trên n nhỏ**.

### Những test cần có

| Input | Target | Kết quả |
|---|---:|---|
| [] | 0 | true, chọn tập rỗng |
| [] | 1 | false |
| [0] | 0 | true |
| [0] | 1 | false |
| [0,1,0] | 1 | true |
| [2,4,8] | 6 | true |
| [2,4,8] | 7 | false |
| [2,2,2] | 4 | true, chọn hai vị trí |
| [2,2,2] | 8 | false |
| [3,34,4,12,5,2] | 9 | true |
| [3,34,4,12,5,2] | 30 | false |
| [1.000.000.000.039, 11] | 1.000.000.000.050 | true bằng MITM |

Đặc biệt nên kiểm **các số 0**. Khi trọng số w=0, cập nhật giảm dần trong DP không làm xuất hiện tổng mới, vì `reachable[s] |= reachable[s]`. Một phần tử 0 không tạo khả năng đạt tổng dương nếu trước đó chưa có.

### Tại sao không chỉ kiểm vài ví dụ đẹp?

Một lỗi duyệt tăng dần cho 0/1 có thể không lộ với các bộ dữ liệu đã có nhiều phần tử giống nhau, nhưng sẽ lộ ngay với `weights=[3]`, target=6: đúng phải false.

Một lỗi cấp phát `target+1` không kiểm có thể chỉ xuất hiện khi target rất lớn. Một lỗi ép `long` xuống `int` có thể làm các trọng số vượt 2³¹ trở thành số âm, dù một số ví dụ nhỏ đều đúng.

Trong chương trình:

- 400 bộ n∈[0,14], trọng số trong [0,30], target trong [0,150] được sinh từ `Random(2026L)`.
- Mỗi bộ kiểm `DP == MITM == bruteOracle`.
- Các thông báo lỗi chứa số test, dãy trọng số và target để có thể tái hiện.

**Lưu ý:** việc ba thuật toán đồng ý trên những bộ test nhỏ là bằng chứng thực nghiệm; tính đúng tổng quát dựa vào các bất biến DP và lập luận phân tách tập con của MITM.

## 20. Các tình huống biên và tính thực dụng

### A. Mục tiêu S=0

Với trọng số không âm, tập con rỗng cho tổng 0, nên đáp án **true** bất kể dãy có rỗng hay không. Nếu bài yêu cầu **tập con không rỗng**, đây là một bài toán có hợp đồng khác; không được giữ nguyên quy tắc trả true cho dãy rỗng.

### B. Nhiều phần tử bằng nhau

Subset Sum chọn **chỉ số**, không đòi các giá trị khác nhau. Với [2,2,2], target=4 đạt được bằng cách chọn **hai vị trí** chứa số 2. Một vị trí không được dùng hai lần.

### C. Trọng số 0

Phần tử 0 có thể được chọn hoặc không mà không đổi tổng. Với bài toán **quyết định tồn tại**, nó không thay đổi các tổng đạt được; với bài toán **đếm số tập con**, nó có thể làm số cách tăng gấp đôi, nên không được áp dụng y nguyên logic đếm.

### D. Trọng số âm

Nếu có trọng số âm, việc bỏ qua tổng trung gian >S **không còn đúng**, vì về sau một số âm có thể kéo tổng về S. Cần mô hình và giới hạn khác: offset của miền tổng, hash set các tổng khả thi, MITM tổng quát có xét dấu, v.v.

Cả hai solver trong Java **chủ động từ chối âm**, làm rõ hợp đồng và tránh kết quả sai do áp dụng chứng minh không phù hợp.

### E. Tổng trọng số có thể tràn long

Ngay cả khi từng trọng số là long dương hợp lệ, tổng của nhiều số có thể lớn hơn Long.MAX_VALUE. Trong bản MITM, tạo một tổng tập con dùng `Math.addExact` để báo lỗi nếu tràn.

Nếu cần hỗ trợ mọi input với giá trị vượt long, phải thiết kế dùng `BigInteger` và tính lại chi phí số học. Không nên cắt giá trị sang int, lấy modulo hay cho phép wrap-around để “đỡ tốn bộ nhớ”; những thay đổi đó có thể biến bài toán thành một bài khác.

### F. Tổng các trọng số nhỏ hơn S

Với trọng số không âm, nếu \(\sum_i w_i<S\), câu trả lời chắc chắn false. Có thể kiểm trước để tối ưu, nhưng **phải tính tổng an toàn**, ví dụ dùng phép cộng có kiểm tràn hoặc so sánh qua tổng bị chặn ở S.

### G. Kích thước đầu ra

Nếu bài yêu cầu **liệt kê tất cả tập con** có tổng S, có thể tồn tại nhiều kết quả hàm mũ. Ngay cả khi **quyết định tồn tại** giải nhanh trên vài lớp input, liệt kê mọi lời giải có thêm chi phí tối thiểu theo tổng kích thước output.

Không được so thời gian của bài **quyết định** với bài **liệt kê** như thể chúng có cùng lượng thông tin phải xuất.

## 21. Các sai lầm phổ biến khi đánh giá độ khó

1. **Đồng nhất số nguyên N với kích thước input**, trong khi N có thể chỉ cần O(log N) bit.
2. **Kết luận O(N) là tuyến tính theo input** khi input chỉ chứa N dạng nhị phân.
3. **Không nói rõ cách mã hóa binary/unary**, làm phát biểu “đa thức” trở nên không kiểm chứng được.
4. **Bỏ qua độ dài bit của các trọng số và target** trong bài số học.
5. **Gọi O(nS) là polynomial-time theo input nhị phân** mà không có giả định về cận S.
6. **Cho rằng pseudo-polynomial nghĩa là thuật toán xấp xỉ**, trong khi DP Subset Sum cho đáp án exact trên miền hỗ trợ.
7. **Cho rằng pseudo-polynomial luôn chậm**, dù với S nhỏ DP có thể hiệu quả hơn mọi phương án mũ theo n.
8. **Cho rằng pseudo-polynomial luôn nhanh**, bỏ qua trường hợp S≈2^b.
9. **Lấy số bit của một kiểu long cố định làm lý do mọi số học O(1) trên số tùy ý**, quên BigInteger/bit complexity.
10. **Duyệt DP từ nhỏ lên lớn trong bài 0/1**, vô tình dùng cùng phần tử nhiều lần.
11. **Dùng DP đánh chỉ số tổng với trọng số âm**, khiến chứng minh và chỉ số bị sai.
12. **Tạo mảng target+1 mà không kiểm tràn int**, có thể thành kích thước âm.
13. **Chỉ xét thời gian O(nS) mà bỏ qua bộ nhớ O(S)**, dẫn đến lỗi RAM trước khi hoàn thành.
14. **Cho rằng bitset loại bỏ sự phụ thuộc vào S**, trong khi vẫn cần Θ(S) bit.
15. **Sử dụng Counting Sort trên miền tới 10¹²** dù n chỉ vài phần tử.
16. **Xem số lần lặp đến N là số chữ số của N**, nhầm giá trị với mã hóa.
17. **Chọn meet-in-the-middle khi n cực lớn**, tạo mảng 2^(n/2) không thể cấp phát.
18. **Cho rằng MITM là polynomial-time theo n**, dù chi phí vẫn mũ theo n/2.
19. **Không kiểm tràn khi sinh tổng tập con**, cho kết quả true/false sai do wrap-around.
20. **Ép `long` xuống `int` chỉ để dùng làm chỉ số mảng**, làm sai giá trị lớn.
21. **Nhầm thuật toán exact với thuật toán approximation**, nhất là khi làm tròn/scale trọng số.
22. **Cho rằng Subset Sum có DP nghĩa là không thể NP-đầy đủ**, bỏ qua pseudo-polynomial.
23. **Gọi NP-đầy đủ yếu là “dễ”**, dù vẫn có instance khó khi các giá trị có nhiều bit.
24. **Cho rằng bài NP-khó mạnh chắc chắn không có thuật toán nào tốt trên instance đặc biệt**, trong khi lớp input hạn chế có thể có giải pháp chuyên biệt.
25. **Không xét output size**, rồi tuyên bố thuật toán liệt kê hàng tỷ kết quả có thể chạy đa thức theo input ngắn.
26. **Dùng cùng một ký hiệu n cho số phần tử lẫn giá trị số**, làm lập luận độ phức tạp mơ hồ.
27. **Không chỉ rõ word-RAM hay bit model** khi nhân số nguyên lớn.
28. **Chọn ngưỡng bộ nhớ cứng rồi gọi input vượt ngưỡng là vô nghiệm**, thay vì báo phương pháp không hỗ trợ.
29. **Dùng oracle vét cạn cho n lớn**, làm bộ test không thể kết thúc.
30. **Chỉ test input đạt đích**, không thử input không thể đạt, phần tử 0 và các trọng số lớn hơn S.
31. **Bỏ qua trường hợp tập con rỗng**, trả false sai khi S=0 trong hợp đồng hiện tại.
32. **Nhầm số cách với tồn tại cách**, dùng boolean DP để trả số lượng lời giải.
33. **Không phân biệt phạm vi miền giá trị U với số giá trị phân biệt d**, bỏ qua giải pháp sparse.
34. **Sử dụng mô hình một word cố định để bàn về tính phức tạp tiệm cận của số tùy ý**, không nêu chi phí đọc và xử lý nhiều bit.

## 22. Câu hỏi tự luyện

**Bài 1.** Số N=8 cần bao nhiêu bit trong biểu diễn nhị phân?

*Đáp án:* **4 bit**, vì 8=1000₂.

**Bài 2.** Một số nguyên dương N có b bit thì N nằm trong khoảng nào?

*Đáp án:* \(2^{b-1}\le N\le2^b-1\).

**Bài 3.** Một vòng lặp chạy N lần có phải O(b) theo b bit biểu diễn N không?

*Đáp án:* Không; nó là Θ(N), có thể là \(\Theta(2^b)\).

**Bài 4.** Sự khác biệt độ dài giữa biểu diễn unary và binary của N?

*Đáp án:* Unary Θ(N), binary Θ(log(N+1)).

**Bài 5.** Vì sao Counting Sort trên U=10¹² có thể không khả thi?

*Đáp án:* Cần miền đếm kích thước Θ(U) dù U chỉ cần khoảng 40 bit để mô tả.

**Bài 6.** Subset Sum quyết định hỏi điều gì?

*Đáp án:* Có tồn tại tập con chỉ số sao cho tổng các trọng số bằng đúng S hay không.

**Bài 7.** Với [3,34,4,12,5,2], target=9 có lời giải không?

*Đáp án:* **Có**, chọn 4 và 5.

**Bài 8.** Cùng dãy trên, target=30 có lời giải không?

*Đáp án:* **Không**, vì không chọn 34 thì tổng tối đa chỉ 26.

**Bài 9.** DP theo tổng S chạy trong bao nhiêu thời gian/bộ nhớ?

*Đáp án:* O(nS) thời gian và O(S) bộ nhớ, theo mô hình word-RAM.

**Bài 10.** Vì sao gọi DP này là giả đa thức?

*Đáp án:* Vì S có thể có b bit nhưng giá trị S gần 2^b, nên O(nS) không nhất thiết đa thức theo b.

**Bài 11.** Tại sao DP 0/1 phải duyệt s giảm dần?

*Đáp án:* Để không dùng trạng thái vừa được tạo từ chính trọng số hiện tại, tránh chọn cùng phần tử hai lần.

**Bài 12.** Với chỉ một phần tử trọng số 3, target=6, đáp án 0/1 là gì?

*Đáp án:* **False**, không được dùng vị trí 3 hai lần.

**Bài 13.** Khi nào MITM hợp lý hơn DP theo tổng?

*Đáp án:* Khi n nhỏ/vừa nhưng target và trọng số rất lớn.

**Bài 14.** Meet-in-the-middle Subset Sum có chi phí tiệm cận nào?

*Đáp án:* O(n2^(n/2)) thời gian và O(2^(n/2)) bộ nhớ.

**Bài 15.** Vì sao MITM không phụ thuộc tuyến tính vào target?

*Đáp án:* Nó liệt kê tập con theo **số phần tử ở mỗi nửa**, rồi tìm cặp tổng bù, không tạo mảng theo s từ 0 đến S.

**Bài 16.** Với n=36, mỗi nửa có tối đa bao nhiêu tập con?

*Đáp án:* \(2^{18}=262\,144\).

**Bài 17.** Một target 40 bit có thể là cỡ bao nhiêu?

*Đáp án:* Trong khoảng \(2^{39}\) tới \(2^{40}-1\), tức cỡ hàng trăm tỷ đến hơn một nghìn tỷ.

**Bài 18.** Dùng `long` có bảo đảm cộng tổng mọi tập con không tràn không?

*Đáp án:* Không. Tổng nhiều `long` dương có thể vượt Long.MAX_VALUE; cần kiểm tràn hoặc dùng BigInteger.

**Bài 19.** Subset Sum là NP-đầy đủ nhưng có DP giả đa thức, có mâu thuẫn không?

*Đáp án:* Không. NP-đầy đủ xét mã hóa nhị phân; O(nS) có thể mũ theo số bit của S.

**Bài 20.** Khi nào thuật toán được gọi là polynomial-time theo input?

*Đáp án:* Khi thời gian bị chặn bởi một đa thức của **độ dài mã hóa toàn bộ input** theo mô hình tính toán đã nêu.

**Bài 21.** Bitset DP có làm bài toán trở thành đa thức theo log S không?

*Đáp án:* Không; nó vẫn cần Θ(S) bit trạng thái.

**Bài 22.** Nếu n=200, S=1000, nên ưu tiên DP hay MITM?

*Đáp án:* **DP** O(nS) dễ khả thi hơn, còn 2^100 tổng mỗi nửa của MITM là quá lớn.

**Bài 23.** Nếu trọng số âm, có thể bỏ qua mọi tổng trung gian >S không?

*Đáp án:* Không; trọng số âm về sau có thể đưa tổng về S.

**Bài 24.** Nếu input yêu cầu liệt kê tất cả nghiệm, chỉ phân tích thời gian giải bài quyết định đã đủ chưa?

*Đáp án:* Chưa; phải tính cả **kích thước output** có thể là hàm mũ.

**Bài 25.** Nếu code giới hạn target≤2.000.000 rồi báo lỗi khi target lớn hơn, có nghĩa target lớn vô nghiệm không?

*Đáp án:* Không; chỉ có nghĩa phương pháp **DP theo giá trị trong demo** vượt giới hạn tài nguyên.

**Bài 26.** Dùng mô hình word-RAM hay bit complexity có thể làm thay đổi phần nào trong phân tích?

*Đáp án:* Chi phí cho phép cộng, nhân, so sánh và lưu trữ số nhiều bit; phải nêu giả định về kích thước word và độ dài số trung gian.

**Tổng kết:** Độ khó của thuật toán số phải được đánh giá theo **độ dài mã hóa đầu vào**, không chỉ theo giá trị các tham số. Một số nguyên N có thể chỉ cần \(\Theta(\log N)\) bit, nên việc lặp \(\Theta(N)\) bước có thể là **hàm mũ theo số bit**. Các thuật toán như Counting Sort O(n+U), Subset Sum DP O(nS) và Knapsack DP O(nW) rất hữu ích khi miền giá trị nhỏ, nhưng trở thành **giả đa thức** hoặc khó dùng khi tham số số học lớn. Trong Subset Sum không âm, DP theo tổng có O(nS) thời gian/O(S) nhớ; meet-in-the-middle thay phụ thuộc S bằng \(O(n2^{n/2})\) thời gian/\(O(2^{n/2})\) nhớ, phù hợp khi n nhỏ và target lớn. Java 17 minh họa hai solver, oracle vét cạn, ngưỡng tài nguyên, kiểm soát tràn số và kiểm thử nhiều trường hợp; lựa chọn phương pháp phải dựa trên **n, bit-length của các giá trị, ngân sách bộ nhớ và dạng kết quả yêu cầu**, không chỉ nhìn vào ký hiệu O mà quên ý nghĩa của tham số.

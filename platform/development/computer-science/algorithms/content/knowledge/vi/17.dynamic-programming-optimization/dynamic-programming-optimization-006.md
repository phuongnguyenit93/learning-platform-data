# Chia để trị tối ưu khi vị trí tối ưu có tính đơn điệu

**Divide and Conquer DP Optimization** (tối ưu quy hoạch động bằng chia để trị) là kỹ thuật tăng tốc việc tính một lớp DP khi mỗi trạng thái phải thử nhiều **vị trí tách hoặc chuyển tiếp**. Ý tưởng không phải giải hai bài toán độc lập như chia để trị truyền thống, mà là **chia đôi đoạn các trạng thái cần tính**, tìm điểm chuyển tốt nhất ở cột giữa rồi thu hẹp miền thử cho các cột bên trái và bên phải.

Kỹ thuật này chỉ đúng khi các **vị trí chuyển tiếp tối ưu có tính đơn điệu** theo chỉ số cột. Đó là một mệnh đề cần có **chứng minh hoặc giả thiết bảo đảm**. Một công thức có dạng `min` không tự làm vị trí tối ưu trở nên đơn điệu.

Bài học thuộc nhóm **Tối ưu quy hoạch động** trong Computer Science Algorithms. Nội dung đi từ một công thức DP chậm nhưng chắc chắn đúng, chứng minh điều kiện đơn điệu bằng bất đẳng thức Monge, triển khai O(Kn log n), đến phản ví dụ khi bỏ giả thiết và chương trình Java 17 có kiểm thử vét cạn.

## 1. Bài toán minh họa: chia một dãy thành đúng K đoạn

Cho dãy **n số nguyên không âm**:

\[
a_1,a_2,\ldots,a_n,\qquad a_i\ge 0,
\]

và số nguyên K, `1 ≤ K ≤ n`. Cần chia toàn bộ dãy thành **đúng K đoạn liên tiếp không rỗng**, mỗi phần tử nằm trong đúng một đoạn, không đổi thứ tự.

Chi phí của đoạn \([l,r]\) là:

\[
C(l,r)=\left(\sum_{t=l}^{r}a_t\right)^2.
\]

Mục tiêu là tối thiểu **tổng chi phí bình phương tổng của K đoạn**.

Ví dụ với `a=[2,1,3,2,1,2]`:

~~~text
K=1: [2,1,3,2,1,2]
     Tổng đoạn = 11, chi phí = 11² = 121

K=2: [2,1,3] | [2,1,2]
     Tổng các đoạn = 6, 5; chi phí = 36+25 = 61

K=3: [2,1] | [3] | [2,1,2]
     Tổng các đoạn = 3, 3, 5; chi phí = 9+9+25 = 43
~~~

Đây là **phân hoạch thành các đoạn**, không phải chọn K tập phần tử tùy ý. Không được hoán đổi thứ tự, không được bỏ phần tử, không được tạo nhóm rỗng. Dữ liệu được giả định **không âm** không phải để công thức DP thường đúng — DP thường vẫn có thể xử lý số âm — mà để chứng minh **điều kiện tối ưu chia để trị**.

### Các trường hợp hợp lệ

- `n≥1`, `1≤K≤n`.
- Mỗi phần tử `a[i]≥0` và các giá trị đủ nhỏ để tổng bình phương có thể được tính chính xác trong kiểu số đang dùng.
- Mọi đoạn phải có ít nhất một phần tử.
- Chi phí cần được tính nhanh, nhờ **tổng tiền tố**.

Nếu `K>n`, không thể tạo K đoạn không rỗng; đó là **input không hợp lệ** trong hợp đồng này. Nếu `K=1`, không có vị trí tách; nếu `K=n`, mỗi phần tử là một đoạn riêng.

## 2. Trạng thái DP và công thức chuyển chuẩn

Định nghĩa:

\[
dp[g][j]=\text{chi phí nhỏ nhất để chia j phần tử đầu thành đúng g đoạn không rỗng.}
\]

Ở đây `g` là **số đoạn**, còn `j` là **độ dài tiền tố đã xét**.

Trạng thái hợp lệ:
- `dp[0][0]=0`: không có phần tử, không có đoạn, chi phí 0.
- `dp[g][j]` với `1≤g≤j≤n`: có thể chia j phần tử thành g đoạn không rỗng.
- `dp[0][j>0]` **không hợp lệ**, vì không thể chia j phần tử dương thành 0 đoạn.
- `dp[g][j<g]` **không hợp lệ**, vì mỗi đoạn cần ít nhất một phần tử.

**Không được coi các ô không hợp lệ là giá trị 0** khi đưa vào phép tối ưu; 0 có thể tạo một phương án giả và làm kết quả quá nhỏ.

### Chọn vị trí tách k của đoạn cuối

Giả sử đoạn cuối của một nghiệm ở trạng thái `dp[g][j]` bắt đầu tại phần tử thứ `k+1`:

~~~text
a1 ... ak | a(k+1) ... aj
 g-1 đoạn |  đoạn thứ g
~~~

Phần bên trái phải đủ `g−1` phần tử để tạo `g−1` đoạn; phần cuối phải không rỗng. Do đó:

\[
g-1\le k<j.
\]

Công thức DP:

\[
\boxed{
dp[g][j]=\min_{g-1\le k<j}
\left(dp[g-1][k]+C(k+1,j)\right).
}
\]

Mỗi lựa chọn k gồm hai phần:
1. `dp[g-1][k]`: giải tối ưu **k phần tử đầu thành g−1 đoạn**.
2. `C(k+1,j)`: chi phí **đoạn cuối** từ k+1 đến j.

Cần đọc hàng `g−1` đã tính xong, **không đọc hàng g chưa hoàn tất**. Với bài chia đúng g đoạn, việc thay `dp[g-1][k]` bằng `dp[g][k]` làm mất ý nghĩa số đoạn và có thể sinh ra công thức sai.

### Trường hợp riêng g=1

Chỉ có một đoạn phủ toàn bộ tiền tố, nên:

\[
dp[1][j]=C(1,j).
\]

Điều này cũng xuất phát từ công thức trên, vì chỉ có **k=0** với trạng thái cơ sở `dp[0][0]=0`. **Không được thử k>0 khi g=1**: đó là những trạng thái `dp[0][k>0]` không hợp lệ.

Bản Java ở dưới tính trực tiếp hàng g=1 bằng tổng tiền tố. Các hàng g≥2 mới dùng chia để trị. Cách này vừa rõ ràng vừa tránh nhầm ô mặc định 0 trong mảng Java với trạng thái hợp lệ.

## 3. Tiền xử lý để tính chi phí đoạn trong O(1)

Định nghĩa tổng tiền tố:

\[
P[0]=0,\qquad P[j]=\sum_{t=1}^{j}a_t.
\]

Tổng các phần tử từ k+1 đến j là `P[j]-P[k]`, nên:

\[
C(k+1,j)=(P[j]-P[k])^2.
\]

Sau khi tạo P trong O(n), mỗi ứng viên k có thể được đánh giá trong **O(1) phép toán số học cố định**:

~~~text
candidate = previous[k] + (P[j] - P[k])²
~~~

Nếu mỗi lần tính C lại quét qua cả đoạn, thời gian của cả DP có thể lớn hơn các cận O(Kn²) và O(Kn log n) thường được nêu. Do vậy, khi áp dụng bất kỳ tối ưu DP nào, phải kiểm tra **thời gian đánh giá hàm chi phí**.

### DP thường: chuẩn để đối chiếu

~~~text
dp[1][j] = (P[j] - P[0])², j từ 1 đến n

for g = 2 .. K:
    for j = g .. n:
        dp[g][j] = +INF
        for k = g-1 .. j-1:
            dp[g][j] = min(
                dp[g][j],
                dp[g-1][k] + (P[j] - P[k])²
            )

answer = dp[K][n]
~~~

Có O(Kn) trạng thái hợp lệ; mỗi trạng thái có thể thử O(n) điểm tách, nên **O(Kn²)** thời gian. Nếu chỉ cần giá trị, có thể giữ hai mảng `previous[]` và `current[]` với O(n) bộ nhớ. Nếu cần khôi phục mọi biên tách, thường cần lưu thêm quyết định theo giai đoạn.

Đây là lời giải **không cần giả thiết về tính đơn điệu** và là **oracle** quan trọng để kiểm thử phiên bản tăng tốc.

## 4. Vị trí tối ưu và quy tắc phá hòa

Đặt:

\[
F_g(k,j)=dp[g-1][k]+C(k+1,j).
\]

Ở mỗi trạng thái hợp lệ, có thể có nhiều k cho cùng chi phí nhỏ nhất. Ta định nghĩa **vị trí tối ưu**:

\[
opt[g][j]=\min\{\,k\mid g-1\le k<j,\ F_g(k,j)=dp[g][j]\,\}.
\]

Tức là **chọn k nhỏ nhất khi có nhiều nghiệm cùng tối ưu**.

Ví dụ nếu k=2 và k=3 cùng cho giá trị 45 thì ghi `opt=2`. Quy tắc phá hòa được giữ nhất quán trong chứng minh, trong cả DP chậm và trong thuật toán chia để trị.

**Điều kiện chính để tối ưu:**

\[
\boxed{opt[g][j]\le opt[g][j+1]}
\]

với mọi j hợp lệ **trong cùng một hàng g**. Khi j tăng, vị trí k tối ưu có thể giữ nguyên hoặc dịch sang phải, nhưng **không lùi về bên trái**.

Các mệnh đề sau **không tương đương** với điều kiện ấy:
- Chi phí tối ưu `dp[g][j]` tăng theo j.
- Vị trí tối ưu tăng khi **g** tăng.
- C là hàm có tính lồi theo một biến nhưng không chứng minh được điều kiện liên quan.
- Trên vài test, các k quan sát được tình cờ không giảm.

**Một điều kiện đủ cần được chứng minh** hoặc một giả thiết đề bài cho trước; nếu chưa có, không được tự giới hạn miền thử k.

## 5. Tính một hàng bằng divide and conquer

Giả sử hàng `previous[j]=dp[g−1][j]` đã được tính đúng. Ta đang tính `current[j]=dp[g][j]` cho mọi `j=g..n`.

Tại một lời gọi:

~~~text
solveRow(left, right, optL, optR)
~~~

ta biết các vị trí tối ưu của những cột j trong **[left,right]** đều nằm trong **[optL,optR]**.

1. Đặt `mid=(left+right)/2`.
2. Duyệt k từ `max(g−1,optL)` tới `min(mid−1,optR)`, tìm giá trị tốt nhất tại cột mid.
3. Ghi `current[mid]` và vị trí `bestK` đạt min; hòa thì giữ k nhỏ nhất.
4. Do tính đơn điệu, các cột **trái** của mid có vị trí tối ưu **≤bestK**. Đệ quy trái với miền `[optL,bestK]`.
5. Các cột **phải** của mid có vị trí tối ưu **≥bestK**. Đệ quy phải với miền `[bestK,optR]`.

Giả mã:

~~~text
solveRow(left, right, optL, optR):
    if left > right:
        return

    mid  = (left + right) // 2
    from = max(g - 1, optL)
    to   = min(mid - 1, optR)

    bestCost = +INF
    bestK = -1

    for k from from to to:
        candidate = previous[k] + C(k + 1, mid)
        if candidate < bestCost:
            bestCost = candidate
            bestK = k

    current[mid] = bestCost
    choice[g][mid] = bestK

    solveRow(left, mid - 1, optL, bestK)
    solveRow(mid + 1, right, bestK, optR)
~~~

Lời gọi gốc cho mỗi hàng g≥2 là:

~~~text
solveRow(g, n, g - 1, n - 1)
~~~

**Điểm quan trọng về chỉ số:** `mid` là **cột j**, còn `bestK` là **vị trí tách k**, không được lấy `mid` thay cho bestK để cập nhật cận con. Cận trên của k phải là `mid−1`, vì k=mid sẽ tạo nhóm cuối rỗng. Cận dưới phải ≥g−1, để phần trước có đủ vật/phần tử cho g−1 đoạn không rỗng.

### Bất biến bảo đảm tính đúng

Với mỗi lời gọi `solveRow(left,right,optL,optR)`:

> Vị trí tối ưu nhỏ nhất của từng cột trong [left,right] nằm trong [optL,optR].

Lời gọi đầu tiên đúng vì miền k bao trùm tất cả lựa chọn hợp lệ. Khi xử lý mid, ta duyệt toàn bộ miền đã được bảo đảm chứa nghiệm nên tìm đúng bestK. Tính đơn điệu cho thấy:
- Với cột j<mid, opt[g][j]≤bestK.
- Với cột j>mid, opt[g][j]≥bestK.

Vì vậy hai lời gọi con vẫn giữ bất biến. Cuối cùng mỗi cột được tính đúng một lần; thuật toán trả **cùng giá trị** như vòng lặp duyệt mọi k, miễn tính đơn điệu thực sự đúng.

### Khác chia để trị thông thường ở đâu?

Trong nhiều thuật toán chia để trị, giải bài toán trái và phải rồi **gộp hai kết quả**. Ở đây, mỗi cột là một bài toán DP đã có công thức chuyển; ta chia đôi **tập chỉ số các cột cần tính** để tận dụng thông tin bestK của cột giữa, không phải phân tách dãy dữ liệu gốc thành hai bài toán độc lập.

Mọi ứng viên đều đọc từ **previous** của hàng đã xong; cột `current[mid]` không phụ thuộc cột khác trong cùng hàng. Nếu công thức đọc `dp[g][k]` cùng hàng, lời gọi đệ quy trên cột giữa có thể đọc trạng thái chưa được tính. Không được áp dụng nguyên khuôn code này mà thiếu phân tích phụ thuộc.

## 6. Phân tích thời gian O(Kn log n)

Mỗi hàng có tối đa n cột hợp lệ. Cây đệ quy chia đôi đoạn cột có độ sâu **O(log n)**.

Ở mỗi mức cây, các khoảng ứng viên k của những nút cùng độ sâu chỉ chồng nhau ở một số ít **biên bestK**; tổng độ dài các khoảng ứng viên được duyệt trên một mức là **O(n)**. Do đó một hàng cần **O(n log n)** lần đánh giá `F_g(k,j)`. Với K hàng:

\[
\boxed{O(Kn\log n)}
\]

khi một ứng viên được tính trong O(1) nhờ prefix sums.

| Phương án | Thời gian | Bộ nhớ giá trị | Bộ nhớ để truy vết |
| --- | --- | --- | --- |
| DP chuẩn thử hết k | O(Kn²) | O(n) dùng hai hàng | Có thể O(Kn) |
| D&C tối ưu từng hàng | O(Kn log n) | O(n) dùng hai hàng, stack O(log n) | O(Kn) nếu lưu mọi choice |

**Không được bỏ K:** O(n log n) là cận cho **một hàng**, không phải toàn bộ K hàng. Nếu cost mất O(T) cho một ứng viên, thời gian tương ứng còn mang thừa số T trong phân tích thông thường.

Bản Java sẽ giữ bảng `choice[g][j]` để in danh sách các ranh giới chia, nên bộ nhớ thực của API ấy là **O(Kn)** chứ không chỉ O(n).

Một số lớp chi phí có thuật toán đặc thù nhanh hơn D&C; O(Kn log n) không mặc nhiên là cận tốt nhất của mọi bài. Nhưng để dùng chính tối ưu D&C này, điều kiện đơn điệu và cận chỉ số phải đúng.

## 7. Điều kiện đủ: bất đẳng thức Monge

Giả sử phép chuyển của một hàng có dạng:

\[
F_g(k,j)=dp[g-1][k]+C(k,j).
\]

Với k là điểm tách và j là vị trí cột, một điều kiện **đủ** phổ biến cho tính đơn điệu của argmin là **Monge**:

\[
C(k_1,j_1)+C(k_2,j_2)
\le C(k_1,j_2)+C(k_2,j_1),
\]

với `k1<k2<j1<j2` trong miền hợp lệ.

Hạng `dp[g−1][k]` chỉ phụ thuộc vào hàng k, nên khi xét hai vế có hai hàng k1,k2, các hạng ấy **triệt tiêu**. Vì vậy F cũng có tính Monge nếu C có tính chất này.

### Vì sao Monge giúp argmin không lùi?

Xét hai cột j1<j2 trong cùng hàng g. Gọi k1 là **argmin nhỏ nhất** tại j1, k2 là **argmin nhỏ nhất** tại j2.

Giả sử trái lại **k2<k1**. Vì k1<j1 và k2<k1, cả hai lựa chọn đều hợp lệ ở **cả hai cột**.

Từ định nghĩa tối ưu:

\[
F(k_1,j_1)\le F(k_2,j_1),\qquad
F(k_2,j_2)\le F(k_1,j_2).
\]

Cộng hai bất đẳng thức này:

\[
F(k_1,j_1)+F(k_2,j_2)
\le F(k_2,j_1)+F(k_1,j_2).
\]

Nhưng tính Monge với `k2<k1`, `j1<j2` cho chiều ngược lại:

\[
F(k_2,j_1)+F(k_1,j_2)
\le F(k_2,j_2)+F(k_1,j_1).
\]

Kết hợp hai chiều buộc mọi bất đẳng thức thành **dấu bằng**. Đặc biệt, `F(k1,j1)=F(k2,j1)`, mà `k2<k1`. Điều này mâu thuẫn với việc k1 là **argmin nhỏ nhất** ở j1.

Vậy `k2<k1` không thể xảy ra; **argmin nhỏ nhất không giảm theo j**.

Đây là một **chứng minh tổng quát** của điều kiện cắt miền trong D&C, không phải suy đoán từ một vài ví dụ. Monge là điều kiện đủ, **không phải điều kiện cần trong mọi bài**: có thể có các truy hồi mà opt đơn điệu do lý do khác.

## 8. Chứng minh bài mẫu thỏa Monge khi các số không âm

Trong bài chia dãy thành K đoạn:

\[
C(k,j)=(P[j]-P[k])^2.
\]

Lấy `k1<k2<j1<j2` và đặt:

\[
A=P[k_2]-P[k_1],\quad
B=P[j_1]-P[k_2],\quad
D=P[j_2]-P[j_1].
\]

Vì mọi `a[i]≥0`, tổng tiền tố P **không giảm**, suy ra **A,B,D≥0**.

Khi ấy:

\[
\begin{aligned}
C(k_1,j_1)&=(A+B)^2,\\
C(k_2,j_2)&=(B+D)^2,\\
C(k_1,j_2)&=(A+B+D)^2,\\
C(k_2,j_1)&=B^2.
\end{aligned}
\]

Xét chênh lệch giữa vế phải và vế trái của bất đẳng thức Monge:

\[
\begin{aligned}
& C(k_1,j_2)+C(k_2,j_1)
 -C(k_1,j_1)-C(k_2,j_2)\\
&=(A+B+D)^2+B^2-(A+B)^2-(B+D)^2\\
&=\boxed{2AD}\ge0.
\end{aligned}
\]

Do đó C thỏa Monge. Từ phần 7, nếu luôn chọn **k nhỏ nhất khi hòa**, `opt[g][j]` không giảm theo j. Đây chính là bằng chứng bài mẫu **được phép dùng** D&C tối ưu.

**Vì sao dấu bằng quan trọng?** Khi A=0 hoặc D=0, bất đẳng thức Monge có thể thành dấu bằng, nhiều k có thể tối ưu cùng chi phí. Quy ước chọn k nhỏ nhất được dùng xuyên suốt trong chứng minh, ví dụ bảng và Java.

Không được kết luận “mọi hàm chi phí bình phương đều Monge”: phép chứng minh dựa trực tiếp vào **P không giảm**. Với dữ liệu âm, A hoặc D có thể âm, tích AD không nhất thiết ≥0.

## 9. Mô phỏng bảng DP và điểm tách tối ưu

Với dãy:

~~~text
a = [2, 1, 3, 2, 1, 2]
P = [0, 2, 3, 6, 8, 9, 11]
~~~

Bảng `dp[g][j]` (ô không hợp lệ ký hiệu —):

| g \ j | 1 | 2 | 3 | 4 | 5 | 6 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4 | 9 | 36 | 64 | 81 | 121 |
| 2 | — | 5 | 18 | 34 | 45 | 61 |
| 3 | — | — | 14 | 22 | 27 | **43** |

Bảng vị trí tách **k nhỏ nhất** của từng trạng thái:

| g \ j | 1 | 2 | 3 | 4 | 5 | 6 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 | — | 1 | 2 | 2 | 2 | 3 |
| 3 | — | — | 2 | 3 | 3 | 3 |

Có thể quan sát opt ở hàng g=2 là `1,2,2,2,3`, ở g=3 là `2,3,3,3`; chúng **không giảm**, phù hợp với chứng minh Monge.

### Tính thủ công dp[2][5]

Với 5 phần tử đầu `[2,1,3,2,1]`, k có thể bằng 1..4:

| k | Nhóm bên trái | Nhóm bên phải | Tổng chi phí |
| ---: | --- | --- | ---: |
| 1 | [2] | [1,3,2,1] | \(2^2+7^2=53\) |
| 2 | [2,1] | [3,2,1] | \(3^2+6^2=45\) |
| 3 | [2,1,3] | [2,1] | \(6^2+3^2=45\) |
| 4 | [2,1,3,2] | [1] | \(8^2+1^2=65\) |

Hai vị trí k=2 và k=3 đều cho giá trị nhỏ nhất 45. Theo chính sách phá hòa, chọn **k=2**, nên `opt[2][5]=2`.

### Khôi phục chia đúng K=3

Từ `dp[3][6]=43`:
- `opt[3][6]=3`, nhóm thứ ba là `[2,1,2]`, chi phí 25.
- Bài toán con là `dp[2][3]=18`, có `opt[2][3]=2`; nhóm thứ hai là `[3]`, chi phí 9.
- Nhóm đầu tiên là `[2,1]`, chi phí 9.

Kết quả:

~~~text
cuts = [2, 3]  (cắt sau phần tử thứ 2 và thứ 3, đếm từ 1)
[2,1] | [3] | [2,1,2]
9     + 9   + 25 = 43
~~~

Dãy Java dùng chỉ số mảng 0-based; nhưng `cut=2` là **số phần tử ở tiền tố**, tức cắt **giữa a[1] và a[2]**, không phải cắt sau a[2] theo chỉ số Java.

Với cùng dãy, K=2 đạt **61** với cut=[3], còn K=6 đạt **23** với mọi phần tử một đoạn, cuts=[1,2,3,4,5].

## 10. Phản ví dụ khi áp dụng cho số âm

Điều kiện không âm không phải một chi tiết trang trí. Nếu đầu vào chứa số âm, tổng tiền tố có thể giảm và tính Monge của bình phương tổng đoạn có thể **không còn**.

Xét:

~~~text
a = [-1, -2, -2, 2]
P = [0, -1, -3, -5, -3]
K = 2
~~~

Tính bằng DP thường:
- Hàng g=1 tại j=1..4 lần lượt là `1,9,25,9`.
- Với `g=2, j=3`: k=1 có chi phí `1+(-4)^2=17`, k=2 có `9+(-2)^2=13`. Tối ưu **k=2**, giá trị 13.
- Với `g=2, j=4`: k=1 có `1+(-2)^2=5`, k=2 có `9+0^2=9`, k=3 có `25+2^2=29`. Tối ưu **k=1**, giá trị 5.

Do đó:

\[
opt[2][3]=2>1=opt[2][4].
\]

Vị trí tối ưu **đi lùi**.

Trong D&C, tính cột giữa j=3 trước và nhận bestK=2 sẽ buộc các cột phía phải chỉ được thử k≥2. Khi tính j=4, thuật toán loại mất **k=1** là nghiệm thực sự tốt nhất; có thể trả **9 thay vì 5**.

Phản ví dụ chứng minh không được dùng D&C tùy tiện với bài này khi có số âm. **DP chuẩn vẫn đúng** về công thức lấy min trên tất cả k; phần sai chỉ là phép **cắt bớt miền k** khi không có giả thiết đơn điệu.

Thiếu Monge không mặc nhiên đồng nghĩa mọi đầu vào có số âm đều sai; có thể một số đầu vào âm vẫn có opt không giảm. Nhưng muốn bảo đảm đúng **cho cả lớp đầu vào**, phải có chứng minh phù hợp, không thể dựa trên vài test.

## 11. Java 17: DP chuẩn và D&C có khôi phục nghiệm

Chương trình độc lập bên dưới:
1. Chỉ nhận dãy số **không âm**, K trong [1,n].
2. Dùng prefix sums để tính `(sum đoạn)^2` trong O(1).
3. Tính riêng hàng `g=1` theo `dp[1][j]=C(1,j)`, tránh đọc `dp[0][k>0]` không hợp lệ.
4. Tính những hàng g≥2 bằng D&C trên cột; lưu `choice[g][j]`.
5. Khôi phục **K−1 biên cắt**.
6. Có lời giải chậm thử mọi k để kiểm tra giá trị, và hàm tính lại chi phí của phương án khôi phục.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class DivideConquerDpOptimizationDemo {
    record Plan(long minCost, List<Integer> cutAfter) {}

    static void validate(int[] a, int groups) {
        if (a == null || a.length == 0
                || groups < 1 || groups > a.length) {
            throw new IllegalArgumentException("Invalid n or groups");
        }
        for (int value : a) {
            if (value < 0) {
                throw new IllegalArgumentException(
                        "Nonnegative values required");
            }
        }
    }

    static long[] prefixSums(int[] a) {
        long[] prefix = new long[a.length + 1];
        for (int i = 0; i < a.length; i++) {
            prefix[i + 1] = Math.addExact(prefix[i], a[i]);
        }
        return prefix;
    }

    // Chi phí đoạn Java nửa mở [from, to).
    static long segmentCost(long[] prefix, int from, int to) {
        long sum = Math.subtractExact(prefix[to], prefix[from]);
        return Math.multiplyExact(sum, sum);
    }

    // DP chuẩn O(K*n*n), không tối ưu theo vị trí tách.
    static long solveSlow(int[] a, int groups) {
        validate(a, groups);
        int n = a.length;
        long[] prefix = prefixSums(a);
        long[] previous = new long[n + 1];

        // g=1: chỉ k=0 hợp lệ, không được đọc dp[0][k>0].
        for (int j = 1; j <= n; j++) {
            previous[j] = segmentCost(prefix, 0, j);
        }

        for (int g = 2; g <= groups; g++) {
            long[] current = new long[n + 1];
            for (int j = g; j <= n; j++) {
                boolean found = false;
                long best = 0;
                for (int k = g - 1; k < j; k++) {
                    long candidate = Math.addExact(
                            previous[k], segmentCost(prefix, k, j));
                    if (!found || candidate < best) {
                        found = true;
                        best = candidate;
                    }
                }
                current[j] = best;
            }
            previous = current;
        }
        return previous[n];
    }

    // Tính một hàng g trên cột [left,right].
    // Vị trí k tối ưu nằm trong [optL,optR].
    static void computeRow(
            int g, int left, int right, int optL, int optR,
            long[] prefix, long[] previous, long[] current,
            int[] choice) {
        if (left > right) {
            return;
        }

        int mid = left + (right - left) / 2;
        int from = Math.max(g - 1, optL);
        int to = Math.min(mid - 1, optR);

        boolean found = false;
        long best = 0;
        int bestK = -1;

        for (int k = from; k <= to; k++) {
            long candidate = Math.addExact(
                    previous[k], segmentCost(prefix, k, mid));
            // K tăng; nếu hòa, giữ k nhỏ nhất.
            if (!found || candidate < best) {
                found = true;
                best = candidate;
                bestK = k;
            }
        }
        if (!found) {
            throw new IllegalStateException("Empty candidate range");
        }

        current[mid] = best;
        choice[mid] = bestK;
        computeRow(g, left, mid - 1, optL, bestK,
                prefix, previous, current, choice);
        computeRow(g, mid + 1, right, bestK, optR,
                prefix, previous, current, choice);
    }

    // O(K*n*log n) thời gian, O(K*n) bộ nhớ kể cả choice.
    static Plan solveFast(int[] a, int groups) {
        validate(a, groups);
        int n = a.length;
        long[] prefix = prefixSums(a);
        long[] previous = new long[n + 1];
        int[][] choice = new int[groups + 1][n + 1];

        for (int[] row : choice) {
            Arrays.fill(row, -1);
        }

        // Hàng g=1 có đáp án duy nhất: cả tiền tố là một đoạn.
        for (int j = 1; j <= n; j++) {
            previous[j] = segmentCost(prefix, 0, j);
            choice[1][j] = 0;
        }

        for (int g = 2; g <= groups; g++) {
            long[] current = new long[n + 1];
            computeRow(g, g, n, g - 1, n - 1,
                    prefix, previous, current, choice[g]);
            previous = current;
        }

        List<Integer> reversed = new ArrayList<>();
        int j = n;
        for (int g = groups; g > 1; g--) {
            int k = choice[g][j];
            reversed.add(k);
            j = k;
        }
        Collections.reverse(reversed);
        return new Plan(previous[n], reversed);
    }

    static long costOfPlan(int[] a, List<Integer> cuts) {
        long[] prefix = prefixSums(a);
        long total = 0;
        int previousCut = 0;

        for (int k : cuts) {
            if (k <= previousCut || k >= a.length) {
                throw new AssertionError("Invalid cut " + k);
            }
            total = Math.addExact(
                    total, segmentCost(prefix, previousCut, k));
            previousCut = k;
        }
        return Math.addExact(
                total, segmentCost(prefix, previousCut, a.length));
    }

    // Vét cạn n=1..6, giá trị 0/1/2, mọi K=1..n.
    static int verifySmall() {
        int checked = 0;
        for (int n = 1; n <= 6; n++) {
            int patterns = 1;
            for (int i = 0; i < n; i++) {
                patterns *= 3;
            }
            for (int code = 0; code < patterns; code++) {
                int remaining = code;
                int[] a = new int[n];
                for (int i = 0; i < n; i++) {
                    a[i] = remaining % 3;
                    remaining /= 3;
                }
                for (int g = 1; g <= n; g++) {
                    long expected = solveSlow(a, g);
                    Plan fast = solveFast(a, g);
                    if (fast.minCost() != expected
                            || fast.cutAfter().size() != g - 1
                            || costOfPlan(a, fast.cutAfter())
                                    != expected) {
                        throw new AssertionError(
                                "a=" + Arrays.toString(a)
                                + ", K=" + g
                                + ", expected=" + expected
                                + ", result=" + fast);
                    }
                    checked++;
                }
            }
        }
        return checked;
    }

    public static void main(String[] args) {
        int[] a = {2, 1, 3, 2, 1, 2};
        for (int g : new int[]{1, 2, 3, 6}) {
            Plan result = solveFast(a, g);
            System.out.println("groups=" + g
                    + " cost=" + result.minCost()
                    + " cuts=" + result.cutAfter());
        }

        Plan tie = solveFast(new int[]{0, 0, 0}, 2);
        System.out.println("tie=" + tie.minCost()
                + " cuts=" + tie.cutAfter());
        System.out.println("verified=" + verifySmall());
    }
}
~~~

Lưu thành tệp **DivideConquerDpOptimizationDemo.java** và chạy với **JDK 17 trở lên**:

~~~bash
javac DivideConquerDpOptimizationDemo.java
java DivideConquerDpOptimizationDemo
~~~

**Đầu ra chính xác:**

~~~text
groups=1 cost=121 cuts=[]
groups=2 cost=61 cuts=[3]
groups=3 cost=43 cuts=[2, 3]
groups=6 cost=23 cuts=[1, 2, 3, 4, 5]
tie=0 cuts=[1]
verified=6015
~~~

### Vì sao chương trình không đọc nhầm trạng thái không hợp lệ?

Ở hàng g=1, công thức duy nhất hợp lệ dùng `dp[0][0]`, nên code **tính trực tiếp** `previous[j]=segmentCost(prefix,0,j)` cho mọi j≥1. Không bao giờ thử `dp[0][k>0]` mặc định bằng 0.

Khi g≥2, k chạy từ **g−1** trở đi. Những `previous[k]` ấy nằm trong miền hợp lệ của hàng g−1, nên có giá trị đúng. Các ô `previous[j<g−1]` có thể vẫn bằng 0 mặc định của Java nhưng **không được đọc**. Đây là cách cài tối ưu đơn giản mà vẫn bảo toàn chính xác ý nghĩa trạng thái.

### Khôi phục biên chia

`choice[g][j]` lưu số phần tử k của tiền tố nằm ở phía trái nhóm cuối. Từ `(g=K,j=n)`, lấy k, lưu nó làm một biên chia, rồi chuyển về `(g−1,j=k)`. Sau khi gặp g=1, đảo thứ tự các biên đã ghi. Mỗi k nằm giữa 1 và n−1 trong một phương án hợp lệ, và các biên tăng nghiêm ngặt.

`costOfPlan` không dùng kết quả DP để tính giá trị; nó tính lại bình phương tổng từng đoạn từ chính các biên, giúp phát hiện lỗi khi tái dựng nghiệm.

### Kiểm thử 6.015 trường hợp

Với mỗi n từ 1 đến 6, chương trình sinh **mọi \(3^n\) dãy** trên các giá trị {0,1,2} và thử mọi `K=1..n`.

\[
\sum_{n=1}^{6}n3^n
=3+18+81+324+1215+4374
=\boxed{6015}.
\]

Trong mỗi ca, nghiệm D&C được đối chiếu với **DP chuẩn thử hết k**, kiểm tra có đúng K−1 biên và kiểm tra tổng chi phí của các đoạn do biên xác định. Bộ thử bao gồm các dãy toàn số 0 (nhiều điểm tách đồng tối ưu), dãy một phần tử, K=1, K=n và những phân bố không âm khác nhau.

Kiểm thử là bằng chứng mạnh về **bản cài trên miền đã thử**, nhưng **không thay thế chứng minh Monge và bất biến chia để trị** cho lớp đầu vào không âm tổng quát.

### Giới hạn số học

Chi phí dùng `long`; `Math.addExact`, `Math.subtractExact` và `Math.multiplyExact` báo lỗi khi vượt miền `long`. Với kích thước lớn hoặc chi phí vượt 64 bit, cần dùng `BigInteger` hoặc một chiến lược số học thích hợp.

Bản minh họa **có thể ném lỗi ngay khi một ứng viên vượt long**, dù một điểm tách khác có chi phí vẫn biểu diễn được. Vì vậy nếu đề cho miền số rộng, phải đảm bảo **mọi phép tính ứng viên** nằm trong long hoặc chuyển toàn bộ phép tính sang kiểu đủ lớn; không được âm thầm bỏ qua ứng viên tràn.

### Bộ nhớ của lời giải

Bản `solveFast` lưu `choice` kích thước (K+1)×(n+1) để trả danh sách cắt, nên cần O(Kn) ô. Nếu chỉ cần chi phí min, có thể bỏ toàn bộ bảng choice và giữ hai hàng DP cùng stack O(log n), tức O(n) bộ nhớ phụ theo cách biểu diễn này.

## 12. Cần tránh áp dụng trong những trường hợp nào?

### 12.1. Không có chứng minh tính đơn điệu

Nếu C là hàm bất kỳ, công thức:

\[
dp[g][j]=\min_{k<j}(dp[g-1][k]+C(k,j))
\]

**không tự bảo đảm** opt[g][j] không giảm. Không được lấy kết quả trên vài test làm bằng chứng. Khi thiếu tính chất này, hãy giữ DP thường hoặc nghiên cứu một tối ưu khác có giả thiết phù hợp.

### 12.2. Có số âm trong bài chi phí bình phương tổng đoạn

Với số âm, P có thể giảm. Chênh lệch Monge `2AD` có thể âm; phản ví dụ phần 10 cho thấy opt thật sự đi lùi. Chương trình Java **từ chối dữ liệu âm** để tránh tuyên bố sai phạm vi bảo đảm.

### 12.3. Có ràng buộc thêm lên độ dài đoạn

Nếu một đoạn phải dài **ít nhất L và nhiều nhất R**, miền k trở thành:

\[
j-R\le k\le j-L
\]

kết hợp với `k≥g−1` và các điều kiện khác. Cách cắt miền và chứng minh đơn điệu có thể cần được xét lại. Không được giữ nguyên `g−1≤k<j` nếu điều đó tạo đoạn không hợp lệ.

### 12.4. Công thức phụ thuộc cùng hàng

Nếu `dp[g][j]` cần `dp[g][k]` với k<j, cách chia cột giữa-trái-phải không bảo đảm `dp[g][k]` đã được tính. Trước hết phải xác lập thứ tự phụ thuộc hoặc thay đổi mô hình; không nên bê nguyên mã computeRow sang.

### 12.5. Bài toán tối đa hóa

Chứng minh Monge trên dùng **argmin**. Nếu bài là **argmax**, một điều kiện đủ có thể là **anti-Monge** (chiều bất đẳng thức ngược) hoặc một lập luận khác. Thay min thành max nhưng giữ nguyên chứng minh có thể sai.

### 12.6. Chi phí không tính trong O(1)

Nếu `C(k,j)` mất nhiều hơn O(1) để tính, tổng thời gian không còn đơn giản là O(Kn log n). Dùng prefix sums, tiền xử lý theo đoạn hoặc cấu trúc phù hợp để làm rõ độ phức tạp mỗi ứng viên.

### 12.7. Nhầm kỹ thuật với tối ưu khác

**Knuth optimization** thường áp dụng cho một dạng DP đoạn `dp[i][j]` và quan hệ vị trí tối ưu kiểu `opt[i][j−1]≤opt[i][j]≤opt[i+1][j]`, với giả thiết riêng. **Convex Hull Trick** khai thác dạng tuyến tính/đường thẳng trong chuyển; **SMAWK** dùng tính chất ma trận đơn điệu tổng quát. Những kỹ thuật này không thể thay thế qua lại chỉ vì đều được gọi là “tối ưu DP”.

Một bài toán có Monge đôi khi có thể giải bằng tối ưu khác tốt hơn O(Kn log n). Điều đó không làm D&C sai; chỉ cho thấy cần so sánh các lựa chọn phù hợp với kích thước input và cấu trúc cost.

## 13. Các lỗi thường gặp khi triển khai

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Bỏ điều kiện opt không giảm | Có thể bỏ k thực sự tối ưu | Chứng minh Monge hoặc chứng minh riêng |
| Coi `dp[0][k>0]=0` là hợp lệ | Bỏ mất các phần tử đầu ở g=1 | Hàng g=1 chỉ có k=0; tính trực tiếp |
| Dùng k từ 0 cho mọi g | Tạo g−1 nhóm rỗng hoặc đọc ô sai | k≥g−1 |
| Cho k=j | Nhóm cuối rỗng | k≤j−1 |
| Nhầm mid với bestK | Thu hẹp sai miền vị trí chuyển | Con trái dùng bestK làm cận trên |
| Không cắt `to` theo mid−1 | Nhận nhóm rỗng hoặc đọc sai | `to=min(optR,mid−1)` |
| Ghi kết quả vào previous khi chưa xong hàng g | Trộn trạng thái g và g−1 | Tách previous/current |
| Dùng quy tắc hòa tùy ý | Lựa chọn opt ghi có thể không theo chứng minh | Giữ k nhỏ nhất |
| Quên xét chi phí cost | Đánh giá sai Big-O | Prefix sums để C là O(1) |
| Truy vết biên như chỉ số Java của phần tử trái | Lệch một vị trí | k là số phần tử tiền tố, không phải chỉ số a[k−1] |
| Chỉ lưu hai hàng nhưng muốn in biên | Thiếu dữ liệu truy vết | Lưu choice hoặc tái dựng hợp lệ |
| Cho dữ liệu âm vào ví dụ có điều kiện không âm | Tính đơn điệu có thể hỏng | Kiểm tra input hoặc dùng DP chuẩn |
| Cộng/bình phương tràn số | Chi phí âm hoặc sai | Kiểm tra phép toán, dùng kiểu đủ lớn |
| Nói O(n log n) cho toàn bộ K hàng | Thiếu hệ số K | O(Kn log n) khi cost O(1) |

**Lỗi đặc biệt khó thấy:** chương trình vẫn chạy và cho một số hợp lý dù đã bỏ k tối ưu do cận đệ quy sai. Vì vậy nên so kết quả với DP chậm trên n nhỏ và có ca phản ví dụ để bảo đảm chương trình từ chối phạm vi không được chứng minh.

## 14. Quy trình áp dụng vào một bài DP mới

1. **Định nghĩa rõ dp:** một trạng thái biểu diễn bài toán con nào, có bao nhiêu nhóm/giai đoạn, và đâu là trạng thái không hợp lệ?
2. **Viết công thức chuẩn:** k có miền nào, một ứng viên được tính từ hàng nào, có dùng các cột cùng hàng không?
3. **Viết bản DP chậm đúng trước**, làm chuẩn cho kiểm thử, không cố tối ưu khi mô hình chưa ổn.
4. **Tiền xử lý C** nếu có thể, chẳng hạn prefix sums hay bảng cost, để một ứng viên có giá xác định.
5. **Định nghĩa opt và chính sách phá hòa**; xác định rõ cần đơn điệu theo chiều j trong cùng một hàng g.
6. **Chứng minh hoặc kiểm tra định lý đủ**, ví dụ Monge hoặc quadrangle inequality trong phạm vi dữ liệu.
7. **Chỉ khi có điều kiện đúng**, cài D&C tính mid và thu hẹp `[optL,optR]` bằng bestK.
8. **Kiểm thử chéo** giá trị của D&C với DP thường, nhất là mảng toàn 0, K=1, K=n, giá trị trùng, nhiều nghiệm hòa.
9. **Kiểm tra khôi phục nghiệm**: đủ K−1 biên, mỗi đoạn không rỗng, tổng chi phí tính lại khớp min.
10. **Phân tích thời gian và bộ nhớ thật** của API, gồm choice, stack, prefix sums, cost và tràn số.
11. **Công bố đúng giả thiết** về dữ liệu không âm, cấu trúc cost và giá trị K; nếu đề khác, không nói bảo đảm tổng quát.

## 15. Bài tập tự luyện và đáp án

**Bài 1 — trạng thái.** Cho dãy n phần tử và K đoạn không rỗng, chi phí đoạn bằng bình phương tổng. Hãy viết `dp[g][j]` và miền k.

*Đáp án:* `dp[g][j]` là chi phí nhỏ nhất chia j phần tử đầu thành g đoạn. Với g≥2, k từ g−1 đến j−1; `dp[g][j]=min_k(dp[g−1][k]+(P[j]−P[k])²)`. Riêng g=1, `dp[1][j]=(P[j])²`.

**Bài 2 — điểm tách hòa.** Với `a=[2,1,3,2,1]` và g=2, tính `dp[2][5]`.

*Đáp án:* Bốn ứng viên k=1,2,3,4 có chi phí 53,45,45,65. Giá trị min=45; nếu chọn argmin nhỏ nhất thì `opt[2][5]=2`.

**Bài 3 — tính đơn điệu.** Nếu `opt[g][mid]=7`, cận vị trí k có thể truyền cho các cột bên trái và bên phải như thế nào?

*Đáp án:* Cột trái chỉ cần k≤7, nên `[optL,7]`; cột phải chỉ cần k≥7, nên `[7,optR]`. Cả hai phải giao cận hợp lệ của trạng thái; lập luận chỉ đúng nếu opt không giảm.

**Bài 4 — chứng minh Monge.** Với `C(k,j)=(P[j]−P[k])²`, hãy chứng minh chênh lệch hai vế là 2AD.

*Đáp án:* Dùng A=P[k2]−P[k1], B=P[j1]−P[k2], D=P[j2]−P[j1]. Chênh lệch bằng `(A+B+D)²+B²−(A+B)²−(B+D)²=2AD≥0` khi a không âm.

**Bài 5 — phản ví dụ âm.** Dãy `[-1,-2,-2,2]`, g=2. Vì sao D&C có thể trả 9 thay vì 5 ở j=4?

*Đáp án:* Ở j=3, opt=2; ở j=4, opt thực sự =1, nên vị trí tối ưu đi lùi. D&C tính mid j=3 trước rồi giới hạn các cột phải chỉ xét k≥2, bỏ mất k=1 có chi phí 5; khi đó nhận 9.

**Bài 6 — độ phức tạp.** Vì sao DP chậm O(Kn²), còn D&C O(Kn log n)?

*Đáp án:* DP chậm có O(Kn) trạng thái, mỗi trạng thái thử O(n) k. Với D&C, mỗi hàng chia cột thành cây sâu O(log n), mỗi mức quét tổng O(n) ứng viên; nhân K hàng.

**Bài 7 — trường hợp toàn 0.** Với `a=[0,0,0]`, K=2, đáp án và cut là gì?

*Đáp án:* Mọi cách chia hai đoạn đều có chi phí 0; với quy tắc k nhỏ nhất, chọn cut=[1].

**Bài 8 — truy vết K=3.** Với `a=[2,1,3,2,1,2]`, `choice[3][6]=3` và `choice[2][3]=2`. Hãy viết các nhóm và chi phí.

*Đáp án:* cuts=[2,3]; các nhóm [2,1], [3], [2,1,2]; chi phí 9+9+25=43.

**Bài 9 — trạng thái không hợp lệ.** Tại sao không được dùng `previous[k]=0` cho mọi k ở hàng `g=0`?

*Đáp án:* Với g=0 chỉ `dp[0][0]=0` hợp lệ. Nếu cho k>0 có giá 0, lời giải sẽ giả vờ bỏ qua tiền tố k phần tử mà không trả chi phí, tạo kết quả sai. Hàng g=1 phải tính trực tiếp với k=0.

**Bài 10 — biến thể max.** Nếu chuyển thành `max_k`, có thể dùng ngay chứng minh Monge và cùng code không?

*Đáp án:* Không. Cần chứng minh tính đơn điệu cho **argmax** hoặc dùng điều kiện như anti-Monge đúng chiều, đồng thời thay cách chọn ứng viên và xử lý hòa.

## Kết luận

**Divide and Conquer DP Optimization** dựa trên một tính chất rất cụ thể: **điểm chuyển tối ưu của các cột trong cùng một hàng không giảm theo chỉ số cột**. Khi tính xong một cột giữa, ta dùng vị trí tối ưu bestK để loại bớt nhiều ứng viên ở các cột trái/phải mà không làm mất lời giải tối ưu.

Với bài chia dãy không âm thành K đoạn liên tiếp, chi phí bình phương tổng đoạn thỏa **Monge** vì chênh lệch hai vế là \(2AD\ge0\). Do đó tối ưu D&C tính đúng giá trị của DP chuẩn và giảm cận thời gian từ **O(Kn²)** xuống **O(Kn log n)** khi một ứng viên tính được O(1).

Không dùng kỹ thuật này chỉ vì tên bài có “quy hoạch động” hoặc công thức có “min”. **Chứng minh đơn điệu, cận k, trạng thái cơ sở, thứ tự đọc hàng và quy tắc hòa** là những phần bắt buộc của một lời giải đúng.

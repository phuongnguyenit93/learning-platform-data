# Thuật toán Floyd–Warshall và thứ tự vòng lặp

## 1. Bài toán: đường đi ngắn nhất giữa mọi cặp đỉnh

Cho một **đồ thị có trọng số** `G=(V,E)` với `n` đỉnh đánh số `0,1,\ldots,n-1`. Mỗi cạnh có trọng số (chi phí) `w`. Ta muốn biết chi phí đường đi ngắn nhất từ **mọi đỉnh nguồn `i`** tới **mọi đỉnh đích `j`**.

Bài toán này được gọi là **All-Pairs Shortest Paths (APSP)**. Nếu phải trả lời rất nhiều truy vấn `(i,j)` trên cùng một đồ thị có số đỉnh vừa phải, thuật toán **Floyd–Warshall** là một lựa chọn cơ bản, dễ triển khai:

- Giải đồng thời đường đi ngắn nhất cho **mọi cặp đỉnh**.
- Chấp nhận **cạnh có trọng số âm**, không đòi hỏi mọi trọng số không âm như Dijkstra.
- Có công thức quy hoạch động cực ngắn và thời gian **`O(n^3)`**.
- Dùng một ma trận khoảng cách **`O(n^2)`** bộ nhớ, có thể thêm ma trận truy vết.
- Phát hiện chu trình âm nhờ phần tử đường chéo và chỉ ra cặp nguồn–đích có khoảng cách **không bị chặn dưới (`-\infty`)**.

**Điểm mấu chốt của bài học:** thứ tự ba vòng lặp **không thể đảo tùy ý**. Với công thức Floyd–Warshall chuẩn tính tại chỗ, **đỉnh trung gian `k` phải được đưa vào theo từng giai đoạn ở vòng ngoài**. Hai vòng trong theo `i` và `j` có thể hoán đổi cho nhau; chuyển `k` vào vòng trong có thể làm kết quả sai dù code vẫn biên dịch và có vẻ hợp lý.

Bài này giải thích **vì sao**, cung cấp **phản ví dụ nhỏ có thể tính bằng tay**, chứng minh tính đúng, mô tả xử lý chu trình âm và chương trình Java 17 đầy đủ kèm kết quả chạy mẫu.

## 2. Khái niệm và hợp đồng dữ liệu

### 2.1. Đường đi, đường đi bộ và chi phí

Một **walk** từ `i` tới `j` là một dãy đỉnh:

\[
i=v_0\to v_1\to\cdots\to v_t=j,
\]

trong đó mỗi bước có một cạnh hợp lệ. Walk được phép lặp đỉnh/cạnh; **simple path** không lặp đỉnh (trừ quy ước đặc biệt của chu trình). Tổng chi phí là tổng trọng số các cạnh đã đi qua.

Bài toán đường đi ngắn nhất tìm **chi phí nhỏ nhất** trong các walk từ `i` tới `j`. Khi không có chu trình âm nào có thể được sử dụng trên tuyến từ `i` tới `j`, chi phí tối thiểu là một số hữu hạn nếu `j` tới được từ `i`.

Nếu tồn tại một chu trình có tổng trọng số âm mà từ `i` có thể đi tới nó, rồi từ đó đi tiếp tới `j`, ta có thể đi vòng chu trình đó **tùy ý nhiều lần** để giảm tổng chi phí vô hạn. Khi ấy không tồn tại “đường đi ngắn nhất” theo nghĩa chi phí nhỏ nhất hữu hạn; ta ký hiệu:

\[
dist(i,j)=-\infty.
\]

**Không tới được** và **`-\infty`** là hai trạng thái khác nhau:

- **`+\infty` / INF / UNREACHABLE:** không có walk nào từ `i` tới `j`.
- **Số hữu hạn:** có walk và có giá trị tối thiểu đạt được.
- **`-\infty`:** có các walk từ `i` tới `j` với chi phí giảm không giới hạn do có thể đi qua chu trình âm.

### 2.2. Đồ thị có hướng và vô hướng

Floyd–Warshall áp dụng cho **đồ thị có hướng** và **vô hướng**. Với đồ thị có hướng, cạnh `u\to v` không tự tạo cạnh `v\to u`. Với cạnh vô hướng `\{u,v\}` trọng số `w`, ta đưa cả hai cung `u\to v` và `v\to u` vào ma trận khoảng cách ban đầu.

**Lưu ý về trọng số âm vô hướng:** nếu một cạnh vô hướng có trọng số âm và walk được phép đi qua cạnh đó nhiều lần, đi `u\to v\to u` tạo một walk đóng có tổng chi phí `2w<0`. Vì vậy thành phần liên thông chứa cạnh âm có thể tạo các cặp `-\infty`. Điều này khác với một số bài toán giới hạn **simple path**, nơi không được quay qua cạnh rồi trở lại. Không được coi Floyd–Warshall với chu trình âm là lời giải cho bài **simple path nhỏ nhất trong mọi đồ thị âm** mà không xem xét định nghĩa.

### 2.3. Cạnh song song, khuyên và đường rỗng

- Nếu có nhiều cạnh `u\to v`, chỉ cần giữ **trọng số nhỏ nhất** của chúng trong ma trận khởi tạo. Hai cạnh song song có cùng đầu–cuối không làm mất tính đúng khi lấy min.
- Với mỗi đỉnh `i`, walk rỗng từ `i` tới chính nó có chi phí **0**, vì vậy khởi tạo `dist[i][i]=0`.
- Nếu có **khuyên âm** `i\to i` trọng số `-3`, giữ min giữa `0` và `-3`; khuyên ấy là một chu trình âm và sẽ được phát hiện.
- Nếu có khuyên dương, đường rỗng chi phí `0` vẫn tốt hơn.
- Nếu hoàn toàn không có đường từ `i` tới `j`, giữ trạng thái **unreachable**, tuyệt đối không xem nó là một đường có chi phí `0`.

## 3. Quy hoạch động theo tập các đỉnh trung gian

Để hiểu lý do `k` đứng ở ngoài, cần đặt đúng ý nghĩa của trạng thái DP, thay vì chỉ học thuộc ba vòng `for`.

Đặt `D^{(k)}[i][j]` là chi phí tối thiểu của một walk từ `i` tới `j` mà **các đỉnh trung gian** thuộc tập `\{0,1,\ldots,k\}`. Hai đầu `i` và `j` **không bị giới hạn** bởi tập này.

Trước khi cho phép bất kỳ đỉnh trung gian nào, đặt:

\[
D^{(-1)}[i][j]=
\begin{cases}
0,&i=j,\\
\min\limits_{(i,j,w)\in E}w,&\text{nếu có cạnh trực tiếp},\\
+\infty,&\text{nếu không có cạnh trực tiếp}.
\end{cases}
\]

Khi `i=j` và có khuyên âm, lấy min giữa `0` và trọng số khuyên. Khi không có chu trình âm có thể liên quan đến cặp đang xét, các phép lấy min trong quy hoạch động biểu diễn giá trị nhỏ nhất hữu hạn.

### 3.1. Hai khả năng của một đường đi tối ưu

Khi bắt đầu cho phép **đỉnh `k`** làm trung gian, một đường đi tối ưu từ `i` tới `j` có hai khả năng:

1. **Không đi qua `k` làm trung gian**: chi phí tốt nhất vẫn là `D^{(k-1)}[i][j]`.
2. **Có đi qua `k` làm trung gian**: tách đường ở `k` thành đoạn `i\rightsquigarrow k` và đoạn `k\rightsquigarrow j`. Mỗi đoạn chỉ cần dùng các đỉnh trung gian trước đó `0,\ldots,k-1`, nên chi phí tốt nhất được ứng viên:

\[
D^{(k-1)}[i][k]+D^{(k-1)}[k][j].
\]

Suy ra công thức **Floyd–Warshall**:

\[
\boxed{
D^{(k)}[i][j]
=
\min\left(
D^{(k-1)}[i][j],
D^{(k-1)}[i][k]+D^{(k-1)}[k][j]
\right).
}
\]

Ta thực hiện các giai đoạn `k=0,1,\ldots,n-1`. Cuối cùng mọi đỉnh đều được phép làm trung gian, nên `D^{(n-1)}` là ma trận đường đi ngắn nhất khi khoảng cách hữu hạn và bài toán không bị ảnh hưởng bởi chu trình âm.

### 3.2. Vì sao được tách thành hai đoạn?

Với đồ thị không chứa chu trình âm trên các đường đi đang xét, có một đường đi tối ưu không cần lặp đỉnh, ngoại trừ các chu trình trọng số `0` có thể bỏ đi mà không tăng chi phí. Nếu đường đi tối ưu có `k` làm trung gian, ta có thể chọn một đường đi tối ưu không cần lặp `k` rồi tách **một lần duy nhất** tại `k`.

Đây là lý do công thức dựa trên “có/không dùng trung gian `k`” là hợp lệ. Nếu có chu trình âm đi qua `k`, bài toán walk ngắn nhất có thể không có minimum hữu hạn; cần **phân loại `-\infty` riêng** sau khi chạy thuật toán, thay vì coi mọi số trong ma trận là câu trả lời hữu hạn đúng.

### 3.3. Từ trạng thái nhiều lớp tới một ma trận

Công thức tham chiếu cả hai giá trị của **giai đoạn `k-1`**. Nếu lưu đủ ma trận cho mọi `k`, ta cần khoảng **`O(n^3)` bộ nhớ**. Floyd–Warshall chuẩn cập nhật **tại chỗ trên một ma trận `dist[][]`**, vẫn chạy đúng trong trường hợp không có chu trình âm nhờ bất biến giai đoạn.

Mã chuẩn:

```text
dist[i][i] = 0
dist[u][v] = min(dist[u][v], weight(u,v))
dist[i][j] = INF nếu không có đường trực tiếp và i != j

for k = 0 .. n-1:
    for i = 0 .. n-1:
        for j = 0 .. n-1:
            if dist[i][k] != INF and dist[k][j] != INF:
                dist[i][j] = min(
                    dist[i][j],
                    dist[i][k] + dist[k][j]
                )
```

Khi vòng `k` kết thúc, `dist[i][j]` đã tích hợp lựa chọn đi qua tất cả trung gian trong `\{0,\ldots,k\}`, và không cần lưu lại riêng `D^{(k-1)}`.

## 4. Tại sao vòng k phải ở ngoài?

**Bất biến cốt lõi:**

> Trước lượt `k`, `dist[i][j]` chứa đáp án tốt nhất chỉ dùng các đỉnh trung gian có chỉ số nhỏ hơn `k`. Sau lượt `k`, nó chứa đáp án tốt nhất khi cho phép thêm `k`.

Nếu đặt `k` làm vòng trong và thay đổi nhiều ô theo `i` hoặc `j`, một ô có thể được tính **trước khi** một đoạn đường tốt hơn cần cho nó được phát hiện. Sau đó chương trình không quay lại ô cũ, nên đường đi nhiều trung gian có thể bị bỏ sót.

### 4.1. Thứ tự đúng

Hai dạng chuẩn:

```java
for (int k = 0; k < n; k++) {
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) {
            relax(i, k, j);
        }
    }
}
```

Và:

```java
for (int k = 0; k < n; k++) {
    for (int j = 0; j < n; j++) {
        for (int i = 0; i < n; i++) {
            relax(i, k, j);
        }
    }
}
```

Cả hai đều thực hiện **từng giai đoạn theo `k`**. Khi không có chu trình âm, việc đổi thứ tự hai vòng trong `i` và `j` không làm sai bất biến DP.

### 4.2. Thứ tự sai thường thấy

```java
// SAI nếu chạy đúng một lượt như một thuật toán APSP tổng quát:
for (int i = 0; i < n; i++) {
    for (int j = 0; j < n; j++) {
        for (int k = 0; k < n; k++) {
            relax(i, k, j);
        }
    }
}
```

Nó lần lượt “chốt” các cặp `(i,j)` quá sớm. Không có bảo đảm rằng `dist[i][k]` và `dist[k][j]` tại thời điểm đó đã cho phép đủ những trung gian cần thiết.

**Quan trọng:** không khẳng định “mọi thuật toán có `k` ở vòng trong đều vô dụng”. Có thể thiết kế thuật toán lặp đến điểm cố định, hoặc thuật toán khác với chứng minh khác. Phát biểu chính xác là **ba vòng lặp chuẩn Floyd–Warshall cập nhật tại chỗ một lượt `O(n^3)` yêu cầu thứ tự giai đoạn `k` ở ngoài**; không được tùy tiện hoán vị các vòng và vẫn dùng chứng minh cũ.

## 5. Phản ví dụ nhỏ: i–j–k trả sai

Xét đồ thị **có hướng**, không có chu trình, có đúng bốn đỉnh:

```text
0 --(1)--> 3 --(1)--> 2 --(1)--> 1

Các cạnh:
0 -> 3, trọng số 1
3 -> 2, trọng số 1
2 -> 1, trọng số 1

Không có cạnh trực tiếp 0 -> 1 hoặc 0 -> 2.
```

Đáp án đúng:

\[
dist(0,1)=1+1+1=3.
\]

Các đỉnh trung gian của đường tốt nhất là `3` và `2`.

### 5.1. Khi k ở ngoài

- Ở giai đoạn `k=2`, ta nhận ra `3\to1` có chi phí `2` từ `3\to2\to1`.
- Ở giai đoạn `k=3`, ta nhận ra `0\to1` có chi phí `3` từ `0\to3\to1`.
- Cuối cùng `dist[0][1]=3`.

Bất biến giai đoạn được giữ, vì chương trình luôn cho phép các trung gian `0,1,2,3` theo thứ tự mở rộng.

### 5.2. Khi chạy i–j–k

Ở `i=0, j=1`, vòng `k` chạy ngay, nhưng:

- `dist[0][2]=INF` vì chưa xử lý cặp `(0,2)`.
- `dist[3][1]=INF` vì chưa xử lý các cặp liên quan `(3,1)`.
- Không có `k` nào giúp giảm `dist[0][1]`; nó vẫn là **INF**.

Sau đó tới `i=0,j=2`, code có thể tìm được `dist[0][2]=2` qua `3`. Nhưng ô `dist[0][1]` **đã qua lượt xử lý**, không được xét lại. Đến cuối vòng lặp, nó vẫn là **INF**, sai với đáp án `3`.

Bảng:

| Cách chạy | `dist(0,1)` |
|---|---|
| Floyd–Warshall `k–i–j` | **3** |
| Floyd–Warshall `k–j–i` | **3** |
| Một lượt cập nhật `i–j–k` | **INF — sai** |

Đây là phản ví dụ chỉ có **trọng số dương và là DAG**, nên lỗi **không** xuất phát từ cạnh âm hoặc chu trình âm. Nó hoàn toàn do **thứ tự quy hoạch động**.

### 5.3. Vì sao có dữ liệu mà thứ tự sai vẫn qua?

Trên nhiều đồ thị đơn giản, đường tối ưu chỉ cần một trung gian hoặc đã được tìm trước khi một ô được xử lý. Khi ấy các vòng lặp đảo sai vẫn có thể tình cờ cho kết quả trùng với cách đúng. Một bộ kiểm thử chỉ gồm tam giác, đồ thị đầy đủ hoặc đường chỉ hai cạnh có thể bỏ sót lỗi.

Muốn kiểm tra thứ tự vòng lặp, phải dùng ca mà đường tốt nhất **phụ thuộc vào một ô được cải thiện muộn**, chẳng hạn phản ví dụ `0\to3\to2\to1`.

## 6. Vì sao cập nhật tại chỗ vẫn hợp lệ khi k ở ngoài?

Một lo ngại hợp lý: công thức `D^{(k)}` dùng giá trị của `D^{(k-1)}`, nhưng code lại ghi trực tiếp lên `dist[][]` trong lúc xử lý cùng giai đoạn `k`. Vậy tại sao không bị dùng “giá trị vừa cập nhật của cùng tầng”?

Trong đồ thị **không có chu trình âm**, sau các giai đoạn trước `k`, ta có:

\[
dist[k][k]=0.
\]

Khi xử lý `k`, các ô `dist[i][k]` và `dist[k][j]` không được cải thiện bằng cách **chèn thêm trung gian `k`** vào chính một đoạn đã kết thúc hoặc bắt đầu ở `k`, vì:

\[
\min(dist[i][k],dist[i][k]+dist[k][k])
=dist[i][k]
\]

và tương tự cho `dist[k][j]`. Ở đây `dist[k][k]=0` khi không có chu trình âm.

Do đó các giá trị **hàng `k` và cột `k`** dùng làm nguồn cho các phép relax không thay đổi trong giai đoạn `k`. Mỗi ô `dist[i][j]` nhận đúng ứng viên `dist[i][k]+dist[k][j]` của giai đoạn trước, nên việc cập nhật tại chỗ tương đương dùng hai ma trận trước/sau trong trường hợp bài toán có đáp án hữu hạn.

Nếu có **chu trình âm**, `dist[k][k]` có thể âm. Lập luận “hàng/cột `k` không đổi” không còn đúng; các số hữu hạn đang tính có thể tiếp tục giảm tùy thứ tự xử lý. Tuy nhiên, thuật toán Floyd–Warshall với phép relax chuẩn vẫn dùng được để **phát hiện chu trình âm** và xác định các cặp `-\infty`, chứ không phải để trả một “khoảng cách hữu hạn” ở những cặp bị ảnh hưởng.

**Không lấy nguyên giá trị số `dist[i][j]` sau ba vòng làm kết quả ngắn nhất** cho cặp có thể đi qua chu trình âm. Phải đánh dấu riêng trạng thái `-\infty`.

## 7. Khoảng cách INF: không được cộng một giá trị “không tới được”

Nếu dùng mảng kiểu số nguyên có sentinel `INF`, đừng viết:

```java
// Nguy hiểm khi một đoạn chưa tới được, hoặc phép cộng tràn:
dist[i][j] = Math.min(
    dist[i][j],
    dist[i][k] + dist[k][j]
);
```

Nếu một trong hai đoạn là `INF` thì ứng viên đi qua `k` **không phải một walk hợp lệ**. Mọi phép tính trên sentinel lúc đó chỉ là thao tác số học giả.

Cần kiểm tra trước:

```java
if (dist[i][k] != INF && dist[k][j] != INF) {
    // Sau khi chắc chắn hai đoạn tồn tại mới cộng.
}
```

### 7.1. Vấn đề tràn số

Ngay cả khi hai giá trị đều hữu hạn, phép cộng `long+long` vẫn có thể vượt `Long.MAX_VALUE` hoặc nhỏ hơn `Long.MIN_VALUE`. Nếu dùng `INF=Long.MAX_VALUE/4`, ta phải bảo đảm **mọi tổng đường đi hữu hạn cần xét** có trị tuyệt đối nằm trong phạm vi cho phép và không vượt sentinel; nếu không, một đường hợp lệ nhưng rất đắt có thể bị nhầm thành không tới được.

Cách an toàn với giới hạn cạnh/trọng số lớn:

- Dùng `Math.addExact` và báo lỗi khi tổng vượt phạm vi kiểu số, nếu bài toán chỉ cho phép kết quả trong `long`.
- Hoặc dùng **`BigInteger`** cho chi phí và dùng **`null` biểu diễn unreachable**, như chương trình hoàn chỉnh trong bài này.

Khi dùng `BigInteger`, tổng lớn hơn `Long.MAX_VALUE` vẫn được biểu diễn chính xác. `null` đại diện **không tồn tại đường**, nên ta không cộng sentinel giả. Đổi lại phép tính số lớn tốn thời gian và bộ nhớ hơn `long`.

### 7.2. Không nhầm INF với -INF

- `null` trong ma trận chi phí của ví dụ Java = **INF, không tới được**.
- `negativeInfinite[i][j]==true` = **-INF, có thể giảm chi phí không giới hạn**.
- `BigInteger.ZERO` = một chi phí hữu hạn thực sự bằng **0**.

Ba trạng thái này cần được xử lý riêng trong API và kết quả hiển thị.

## 8. Cạnh âm và chu trình âm

Floyd–Warshall chấp nhận cạnh có trọng số âm, ví dụ:

```text
0 -> 1  (4)
1 -> 2  (-2)
2 -> 3  (3)
```

Đường `0\to1\to2\to3` có tổng `4-2+3=5`. Nếu không có chu trình âm trên một tuyến từ `0` tới `3`, khoảng cách `5` hoàn toàn hợp lệ.

Cạnh âm **không đồng nghĩa** với chu trình âm. Một DAG có thể có nhiều cạnh âm mà không có chu trình nào.

### 8.1. Phát hiện chu trình âm qua đường chéo

Sau khi chạy Floyd–Warshall, nếu tồn tại `k` với:

\[
dist[k][k]<0,
\]

đồ thị có một **walk đóng trọng số âm**, tức có **chu trình âm**.

Vì sao? Ban đầu `dist[k][k]=0` (walk rỗng). Nếu cuối cùng nhỏ hơn `0`, phải tồn tại một walk từ `k` về `k` với tổng âm. Mọi walk đóng có tổng âm chứa ít nhất một chu trình âm.

Ngược lại, nếu có chu trình âm, trong quá trình xử lý các đỉnh của chu trình, Floyd–Warshall sẽ ghi nhận một giá trị đường chéo âm tại một đỉnh trên chu trình. Vì vậy:

\[
\boxed{\text{Có chu trình âm}
\iff \exists k:\ dist[k][k]<0.}
\]

**Không cần mọi `dist[k][k]` đều âm**. Chỉ một đường chéo âm đã đủ chứng minh chu trình âm tồn tại đâu đó trong đồ thị.

### 8.2. Không phải tất cả cặp đều -INF

Xét đồ thị:

```text
4 -> 0 -> 1 -> 2 -> 3
          ^    |
          |    |
          +----+
Cạnh và trọng số:
4 -> 0 :  5
0 -> 1 :  2
1 -> 2 :  1
2 -> 1 : -3
2 -> 3 :  2

Chu trình 1 -> 2 -> 1 có tổng 1 + (-3) = -2.
```

- Từ `0` tới `3`: đi tới chu trình âm, lặp bao nhiêu lần tùy ý, rồi đi `2\to3` ⇒ **`-\infty`**.
- Từ `4` tới `3`: qua `4\to0` rồi vào chu trình âm ⇒ **`-\infty`**.
- Từ `4` tới `0`: đi cạnh trực tiếp chi phí `5`; chu trình âm phía sau **không cho phép quay về `0`** ⇒ khoảng cách **hữu hạn 5**.
- Từ `3` tới `0`: không có đường ⇒ **INF**.
- Từ `0` tới chính `0`: walk rỗng chi phí `0`; không có đường quay lại `0` qua chu trình âm ⇒ **hữu hạn 0**.
- Từ `1` tới chính `1`: có chu trình âm lặp lại ⇒ **`-\infty`**.

Không được đánh dấu **toàn bộ ma trận** là `-\infty` chỉ vì phát hiện một chu trình âm.

### 8.3. Điều kiện chính xác cho một cặp -INF

Sau khi tính các đường đi đủ để biết **tính tới được** và các đỉnh thuộc vùng chu trình âm, đánh dấu:

\[
negativeInfinite[i][j]
\iff
\exists k:
\begin{cases}
dist[k][k]<0,\\
i\rightsquigarrow k,\\
k\rightsquigarrow j.
\end{cases}
\]

Trong ma trận, `i\rightsquigarrow k` biểu diễn `dist[i][k]` khác INF, và `k\rightsquigarrow j` biểu diễn `dist[k][j]` khác INF.

Khi điều kiện thỏa, ta có thể đi từ `i` đến `k`, lặp một walk đóng âm xuất phát/kết thúc tại `k` tùy ý, rồi tới `j`. Chi phí giảm không giới hạn.

Nếu một cặp **không** có bất kỳ chu trình âm nào trên tuyến nối như vậy, chi phí đường đi ngắn nhất của nó vẫn có thể hữu hạn hoặc là INF tùy tính tới được.

### 8.4. Vì sao không truy vết đường ở cặp -INF?

Với `-\infty`, không có một walk **hữu hạn duy nhất** đạt giá trị `-\infty`. Mọi walk hữu hạn đi được vẫn có một tổng số nguyên cụ thể; ta luôn có thể giảm thêm chi phí bằng cách lặp chu trình âm. Vì vậy một mảng `next[][]` không thể biểu diễn một “đường đi ngắn nhất hữu hạn” cho cặp bị ảnh hưởng.

API tốt nên trả trạng thái **`NEGATIVE_INFINITY`** thay vì cố dựng `List<Integer>`. Với cặp INF cũng không thể dựng đường vì không có đường nào.

## 9. Truy vết đường đi bằng ma trận next

Nếu chỉ cần giá trị khoảng cách, `dist[][]` là đủ. Nếu cần in **một đường đi ngắn nhất cụ thể** cho các cặp có chi phí hữu hạn, dùng thêm:

```text
next[i][j] = đỉnh kế tiếp ngay sau i
             trên một đường đi đang được chọn từ i tới j.
```

Khởi tạo:

- `next[i][i]=i` cho walk rỗng.
- Nếu có cạnh trực tiếp tốt nhất `i\to j` với `i\ne j` thì `next[i][j]=j`.
- Nếu không có đường trực tiếp thì `next[i][j]=-1`.

Khi phép relax qua `k` tạo chi phí **nhỏ hơn nghiêm ngặt**:

```java
dist[i][j] = via;
next[i][j] = next[i][k];
```

Lý do: nếu đường tốt hơn là `i\rightsquigarrow k\rightsquigarrow j`, bước đầu tiên chính là bước đầu tiên của đường `i\rightsquigarrow k`.

Không cập nhật `next` khi ứng viên **bằng** chi phí hiện tại trong ví dụ này. Đó là chính sách phá hòa nhằm tránh thay đường một cách không cần thiết; nhiều đường ngắn nhất khác nhau đều có thể đúng.

### 9.1. Khôi phục đường

Đối với `i,j` có khoảng cách hữu hạn:

```text
path = [i]
while i != j:
    i = next[i][j]
    thêm i vào path
```

Ví dụ nếu:

```text
next[0][3] = 1
next[1][3] = 2
next[2][3] = 3
```

thì trả `[0,1,2,3]`.

### 9.2. Những điều cần bảo vệ khi truy vết

1. **UNREACHABLE:** `dist[i][j]==null`, không có đường.
2. **-INF:** `negativeInfinite[i][j]==true`, không có đáp án hữu hạn, không truy vết.
3. **Chỉ số không hợp lệ:** kiểm tra `0\le i,j<n`.
4. **Vòng lặp bất thường trong `next`:** giới hạn số bước truy vết; nếu vượt số đỉnh cho một cặp hữu hạn thì báo lỗi cài đặt/trạng thái thay vì chạy vô hạn.
5. **Cạnh song song:** chỉ lấy cạnh trực tiếp có trọng số nhỏ nhất khi khởi tạo.
6. **Nhiều đường tối ưu:** đường được trả phụ thuộc thứ tự cập nhật và quy tắc hòa, không nhất thiết duy nhất.
7. **Tính đúng của đường:** tổng trọng số các cạnh trên đường phải khớp `dist[i][j]`. Nếu có cạnh song song, mỗi cặp đỉnh liên tiếp phải khớp **một cạnh thật** với trọng số đã dùng trong việc chọn đường.

## 10. Java 17+ hoàn chỉnh: đúng vòng k, phản ví dụ đảo vòng và chu trình âm

Đoạn mã dưới đây là **một chương trình chạy độc lập**, không phải pseudocode. Nó có:

- `floydWarshall`: triển khai chuẩn với `k` ngoài cùng, `BigInteger` cho khoảng cách, `null` cho không tới được, `next[][]` để truy vết, và `negativeInfinite[][]` đánh dấu các cặp bị chu trình âm ảnh hưởng.
- `wrongIJk`: phiên bản **cố ý sai** (chạy `i–j–k` đúng một lượt) **chỉ dùng minh họa phản ví dụ**. Không dùng để giải APSP thực tế.
- Kiểm tra **cạnh song song, khuyên âm, đồ thị rỗng, giá trị vượt `long`**.
- Truy vấn kết quả theo ba trạng thái: **số hữu hạn kèm đường**, **UNREACHABLE**, **-INF**.

Mảng khoảng cách `BigInteger[][]` tránh phải giả định mọi tổng nhỏ hơn một sentinel `INF`. Đổi lại, chi phí phép cộng/so sánh `BigInteger` phụ thuộc độ lớn các số; `O(n^3)` dưới đây là số **phép relax**, không phải chặn chi phí bit chính xác cho đầu vào số tùy ý lớn.

**Tên tệp:** `FloydWarshallLoopOrderDemo.java`.

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public final class FloydWarshallLoopOrderDemo {
    private FloydWarshallLoopOrderDemo() {
    }

    public record Edge(int from, int to, long weight) {
    }

    public static final class AllPairs {
        private final BigInteger[][] dist;
        private final int[][] next;
        private final boolean[][] negativeInfinite;
        private final boolean hasNegativeCycle;

        private AllPairs(
                BigInteger[][] dist, int[][] next,
                boolean[][] negativeInfinite,
                boolean hasNegativeCycle) {
            this.dist = dist;
            this.next = next;
            this.negativeInfinite = negativeInfinite;
            this.hasNegativeCycle = hasNegativeCycle;
        }

        public int size() {
            return dist.length;
        }

        public boolean hasNegativeCycle() {
            return hasNegativeCycle;
        }

        private void checkVertex(int u) {
            if (u < 0 || u >= dist.length) {
                throw new IllegalArgumentException(
                    "vertex outside 0..n-1"
                );
            }
        }

        public String distanceText(int from, int to) {
            checkVertex(from);
            checkVertex(to);
            if (negativeInfinite[from][to]) {
                return "-INF";
            }
            if (dist[from][to] == null) {
                return "INF";
            }
            return dist[from][to].toString();
        }

        public String rowText(int from) {
            checkVertex(from);
            List<String> cells = new ArrayList<>();
            for (int to = 0; to < size(); to++) {
                cells.add(distanceText(from, to));
            }
            return cells.toString();
        }

        public String describe(int from, int to) {
            checkVertex(from);
            checkVertex(to);

            if (negativeInfinite[from][to]) {
                return "-INF (reachable negative cycle)";
            }
            if (dist[from][to] == null) {
                return "UNREACHABLE";
            }

            List<Integer> path = new ArrayList<>();
            path.add(from);
            int current = from;

            while (current != to) {
                current = next[current][to];
                if (current < 0 || path.size() > size() + 1) {
                    throw new IllegalStateException(
                        "invalid next matrix"
                    );
                }
                path.add(current);
            }
            return "distance=" + dist[from][to]
                + " path=" + path;
        }
    }

    private static void validate(int n, List<Edge> edges) {
        Objects.requireNonNull(edges, "edges");
        if (n < 0) {
            throw new IllegalArgumentException(
                "number of vertices must be nonnegative"
            );
        }
        for (Edge e : edges) {
            Objects.requireNonNull(e, "edge");
            if (e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n) {
                throw new IllegalArgumentException(
                    "edge endpoint outside 0..n-1"
                );
            }
        }
    }

    // null = không tới được; giữ cạnh trực tiếp nhỏ nhất.
    private static BigInteger[][] initialDistances(
            int n, List<Edge> edges) {
        validate(n, edges);
        BigInteger[][] dist = new BigInteger[n][n];

        for (int i = 0; i < n; i++) {
            dist[i][i] = BigInteger.ZERO;
        }
        for (Edge e : edges) {
            BigInteger weight =
                BigInteger.valueOf(e.weight());
            BigInteger old = dist[e.from()][e.to()];
            if (old == null || weight.compareTo(old) < 0) {
                dist[e.from()][e.to()] = weight;
            }
        }
        return dist;
    }

    public static AllPairs floydWarshall(
            int n, List<Edge> edges) {
        BigInteger[][] dist = initialDistances(n, edges);
        int[][] next = new int[n][n];

        for (int i = 0; i < n; i++) {
            Arrays.fill(next[i], -1);
            for (int j = 0; j < n; j++) {
                if (dist[i][j] != null) {
                    next[i][j] = (i == j) ? i : j;
                }
            }
        }

        // THỨ TỰ ĐÚNG: giai đoạn k là vòng ngoài.
        for (int k = 0; k < n; k++) {
            for (int i = 0; i < n; i++) {
                if (dist[i][k] == null) {
                    continue;
                }
                for (int j = 0; j < n; j++) {
                    if (dist[k][j] == null) {
                        continue;
                    }

                    BigInteger via =
                        dist[i][k].add(dist[k][j]);
                    if (dist[i][j] == null
                            || via.compareTo(dist[i][j]) < 0) {
                        dist[i][j] = via;
                        next[i][j] = next[i][k];
                    }
                }
            }
        }

        boolean[] negativeVertex = new boolean[n];
        boolean hasNegativeCycle = false;
        for (int k = 0; k < n; k++) {
            if (dist[k][k] != null
                    && dist[k][k].signum() < 0) {
                negativeVertex[k] = true;
                hasNegativeCycle = true;
            }
        }

        boolean[][] negativeInfinite = new boolean[n][n];

        for (int k = 0; k < n; k++) {
            if (!negativeVertex[k]) {
                continue;
            }
            for (int i = 0; i < n; i++) {
                if (dist[i][k] == null) {
                    continue;
                }
                for (int j = 0; j < n; j++) {
                    if (dist[k][j] != null) {
                        negativeInfinite[i][j] = true;
                    }
                }
            }
        }

        return new AllPairs(
            dist, next, negativeInfinite, hasNegativeCycle
        );
    }

    // CỐ Ý SAI với đồ thị tổng quát: chỉ dùng làm phản ví dụ.
    public static BigInteger[][] wrongIJk(
            int n, List<Edge> edges) {
        BigInteger[][] dist = initialDistances(n, edges);

        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                for (int k = 0; k < n; k++) {
                    if (dist[i][k] == null
                            || dist[k][j] == null) {
                        continue;
                    }
                    BigInteger via =
                        dist[i][k].add(dist[k][j]);
                    if (dist[i][j] == null
                            || via.compareTo(dist[i][j]) < 0) {
                        dist[i][j] = via;
                    }
                }
            }
        }
        return dist;
    }

    private static String rawText(BigInteger value) {
        return value == null ? "INF" : value.toString();
    }

    public static void main(String[] args) {
        List<Edge> dag = List.of(
            new Edge(0, 1, 9),  // Cạnh song song kém hơn.
            new Edge(0, 1, 4),
            new Edge(0, 2, 11),
            new Edge(0, 3, 20),
            new Edge(1, 2, -2),
            new Edge(1, 3, 10),
            new Edge(2, 3, 3)
        );

        AllPairs a = floydWarshall(4, dag);
        System.out.println("DAG negative cycle: "
            + a.hasNegativeCycle());
        System.out.println("DAG row 0: " + a.rowText(0));
        System.out.println("DAG 0->3: " + a.describe(0, 3));
        System.out.println("DAG 3->0: " + a.describe(3, 0));
        System.out.println("DAG 2->2: " + a.describe(2, 2));

        List<Edge> negative = List.of(
            new Edge(0, 1, 2),
            new Edge(1, 2, 1),
            new Edge(2, 1, -3),
            new Edge(2, 3, 2),
            new Edge(4, 0, 5)
        );

        AllPairs b = floydWarshall(5, negative);
        System.out.println("Negative graph cycle: "
            + b.hasNegativeCycle());
        System.out.println("Negative 0->3: "
            + b.describe(0, 3));
        System.out.println("Negative 4->3: "
            + b.describe(4, 3));
        System.out.println("Negative 4->0: "
            + b.describe(4, 0));
        System.out.println("Negative 3->0: "
            + b.describe(3, 0));
        System.out.println("Negative 0->0: "
            + b.describe(0, 0));
        System.out.println("Negative 1->1: "
            + b.describe(1, 1));

        List<Edge> orderCounterexample = List.of(
            new Edge(0, 3, 1),
            new Edge(3, 2, 1),
            new Edge(2, 1, 1)
        );

        AllPairs correct = floydWarshall(
            4, orderCounterexample
        );
        BigInteger[][] wrong = wrongIJk(
            4, orderCounterexample
        );
        System.out.println("Correct k-i-j 0->1: "
            + correct.distanceText(0, 1));
        System.out.println("Wrong i-j-k 0->1: "
            + rawText(wrong[0][1]));
        System.out.println("Wrong order equals correct: "
            + rawText(wrong[0][1]).equals(
                correct.distanceText(0, 1)
            ));

        AllPairs loop = floydWarshall(
            1, List.of(new Edge(0, 0, -1))
        );
        System.out.println("Negative self-loop 0->0: "
            + loop.describe(0, 0));

        AllPairs large = floydWarshall(
            3, List.of(
                new Edge(0, 1, Long.MAX_VALUE),
                new Edge(1, 2, Long.MAX_VALUE)
            )
        );
        System.out.println("BigInteger 0->2: "
            + large.describe(0, 2));

        AllPairs empty = floydWarshall(0, List.of());
        System.out.println("Empty vertices: "
            + empty.size());

        boolean rejected = false;
        try {
            floydWarshall(
                2, List.of(new Edge(0, 2, 1))
            );
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Invalid edge rejected: "
            + rejected);
    }
}
```

Lưu tệp nguồn UTF-8 rồi biên dịch và chạy với **JDK 17 hoặc mới hơn**:

```bash
javac -encoding UTF-8 FloydWarshallLoopOrderDemo.java
java FloydWarshallLoopOrderDemo
```

**Đầu ra chuẩn:**

```text
DAG negative cycle: false
DAG row 0: [0, 4, 2, 5]
DAG 0->3: distance=5 path=[0, 1, 2, 3]
DAG 3->0: UNREACHABLE
DAG 2->2: distance=0 path=[2]
Negative graph cycle: true
Negative 0->3: -INF (reachable negative cycle)
Negative 4->3: -INF (reachable negative cycle)
Negative 4->0: distance=5 path=[4, 0]
Negative 3->0: UNREACHABLE
Negative 0->0: distance=0 path=[0]
Negative 1->1: -INF (reachable negative cycle)
Correct k-i-j 0->1: 3
Wrong i-j-k 0->1: INF
Wrong order equals correct: false
Negative self-loop 0->0: -INF (reachable negative cycle)
BigInteger 0->2: distance=18446744073709551614 path=[0, 1, 2]
Empty vertices: 0
Invalid edge rejected: true
```

### 10.1. Ý nghĩa kết quả nhóm DAG

- `DAG row 0` là các chi phí ngắn nhất từ `0`: `[0,4,2,5]`.
- Cạnh `1\to2` có trọng số âm `-2`, nhưng không có chu trình âm vì đồ thị không chứa chu trình nào.
- `0\to3` tốt nhất đi qua `0\to1\to2\to3`, tổng `4+(-2)+3=5`, không phải cạnh trực tiếp trọng số `20`.
- `3\to0` không đi được theo hướng cạnh, nên trạng thái **UNREACHABLE**.
- `2\to2` dùng walk rỗng chi phí `0` và trả đường `[2]`.

### 10.2. Ý nghĩa kết quả nhóm chu trình âm

- Chu trình `1\to2\to1` có trọng số `-2`, làm `0\to3` và `4\to3` không bị chặn dưới.
- `4\to0` vẫn hữu hạn `5` vì không thể đi chu trình âm rồi quay về `0`.
- `3\to0` **không tới được** chứ không phải `-\infty`.
- `0\to0` vẫn hữu hạn bằng `0`; nhưng `1\to1` có thể lặp chu trình âm nên là `-\infty`.

### 10.3. Ý nghĩa phản ví dụ thứ tự vòng

`wrongIJk` không phải “Floyd–Warshall thay cách viết vẫn đúng”. Nó cố ý đặt `i,j` ngoài `k` và chỉ relax mỗi bộ ba đúng một lần. Đồ thị `0\to3\to2\to1` buộc chương trình phải tái sử dụng một kết quả trung gian được tìm ra muộn. Với `i–j–k`, ô `(0,1)` đã được duyệt qua và không cập nhật lại, nên ra **INF** dù có đường chi phí **3**.

### 10.4. Vì sao dùng BigInteger thay vì INF lớn?

Chi phí đường `0\to1\to2` ở ví dụ cuối là:

\[
2\cdot Long.MAX\_VALUE
=18446744073709551614.
\]

Số này vượt phạm vi `long` có dấu nhưng hoàn toàn hợp lệ là tổng của hai cạnh trọng số `long`. Dùng `BigInteger` và `null` tránh cả **tràn** và **nhầm đường rất đắt với sentinel INF**.

Với bài thi có bảo đảm tổng luôn nằm trong `long` và giới hạn rõ ràng, có thể thay bằng `long[][]` để chạy nhanh hơn; nhưng phải chọn cận sentinel và kiểm tra phép cộng phù hợp với đặc tả.

## 11. Chứng minh tính đúng của Floyd–Warshall (không chu trình âm)

Ta chứng minh bằng quy nạp theo tập trung gian được cho phép.

### 11.1. Cơ sở

Trước giai đoạn `k=0`, không có đỉnh trung gian nào được phép. Một walk từ `i` tới `j` không có trung gian chỉ có thể là:

- Walk rỗng chi phí `0` nếu `i=j`; hoặc
- Một cạnh trực tiếp `i\to j`; hoặc
- Không tồn tại, tương ứng INF.

Ma trận khởi tạo giữ chính xác min của những khả năng đó (tính cả các cạnh song song và khuyên).

### 11.2. Bước quy nạp

Giả sử trước giai đoạn `k`, `dist[i][j]` đúng bằng chi phí ngắn nhất khi chỉ dùng trung gian trong tập `\{0,\ldots,k-1\}`.

Một đường ngắn nhất khi được thêm `k`:

- Hoặc không có `k` làm trung gian, đã được `dist[i][j]` của giai đoạn trước bao phủ.
- Hoặc có `k` làm trung gian. Trong đồ thị không có chu trình âm, có thể chọn một đường ngắn nhất không cần lặp `k`. Tách ở `k`, hai đoạn tốt nhất có các trung gian trước `k`, nên ứng viên bằng `dist[i][k]+dist[k][j]`.

Lấy min đúng theo công thức cho đáp án ở giai đoạn `k`. Trong cập nhật tại chỗ, vì `dist[k][k]=0`, các ô hỗ trợ hàng/cột `k` không đổi trong giai đoạn, nên mọi relax đều dùng nguồn phù hợp với giả thiết quy nạp.

Sau giai đoạn `n-1`, mọi đỉnh được phép làm trung gian. Vì vậy ma trận chứa chi phí ngắn nhất của mọi cặp tới được; những cặp không tới được vẫn là INF.

### 11.3. Chứng minh truy vết

Ở thời điểm khởi tạo, nếu `i\ne j` và có cạnh trực tiếp tối ưu `i\to j`, đỉnh kế là `j` nên `next[i][j]=j` đúng.

Khi tìm thấy đường tốt hơn qua `k`, đoạn đầu của đường mới là một đường tốt nhất từ `i` tới `k`; do đó bước tiếp theo của đường `i\to j` chính là `next[i][k]`. Cập nhật `next[i][j]=next[i][k]` giữ đúng ý nghĩa “bước đầu của một đường có chi phí `dist[i][j]`”.

Với cặp có **khoảng cách hữu hạn** và không bị chu trình âm ảnh hưởng, việc lặp bước kế tiếp dựng một đường đạt tổng chi phí đúng bằng `dist[i][j]`. Do không thể có một chu trình **âm** cần lặp để cải thiện vô hạn, và ví dụ chỉ cập nhật khi chi phí giảm nghiêm ngặt, một đường đi ngắn nhất đơn có thể được truy vết trong tối đa `n-1` cạnh khi `i\ne j`. Mã có kiểm tra bảo vệ phòng sai sót của ma trận.

### 11.4. Phạm vi chứng minh khi có chu trình âm

Nếu một cặp nguồn–đích có thể đi qua chu trình âm, “giá trị ngắn nhất hữu hạn” không tồn tại. Trong khi đó, sau phép relax ba vòng, các phần tử đường chéo âm và ma trận tính tới được vẫn cho phép đánh dấu những cặp **`-\infty`** như mục 8.3.

Đây không phải là khẳng định rằng giá trị số cuối cùng của `dist[i][j]` chính là `-\infty`. Nó chỉ là một số **đại diện trong quá trình relax**, và API phải kiểm tra `negativeInfinite[][]` trước khi trả chi phí hoặc truy vết.

## 12. Độ phức tạp thời gian và bộ nhớ

Với `n=|V|`, `m=|E|`:

- Xây ma trận `n\times n`: **`O(n^2+m)`**.
- Ba vòng `k,i,j`: có **`O(n^3)`** bộ ba, mỗi bộ ba thực hiện một phép kiểm tra và có thể cộng/so sánh chi phí.
- Đánh dấu cặp bị ảnh hưởng bởi chu trình âm: thêm tối đa **`O(n^3)`** kiểm tra.
- Kiểm tra một cặp `i,j` là INF/hữu hạn/-INF: **`O(1)`** sau khi tiền xử lý.
- Truy vết một đường hữu hạn: **`O(\ell)`** với `\ell` là số cạnh trên đường, không quá `n-1` nếu chọn đường đơn.
- Bộ nhớ ma trận `dist,next,negativeInfinite`: **`O(n^2)`**.

Tổng:

\[
\boxed{\text{Thời gian }O(n^3+m),\qquad
\text{bộ nhớ }O(n^2).}
\]

Đó là độ phức tạp theo **số phép toán ma trận**. Với `BigInteger`, mỗi phép cộng/so sánh số có chi phí theo độ dài bit của giá trị; với trọng số nhỏ gọn cố định, ta thường coi đây là chi phí hằng trong phân tích thuật toán tiêu chuẩn.

### Khi nào nên dùng Floyd–Warshall?

- **Nên dùng:** số đỉnh vừa phải, nhiều truy vấn mọi cặp, trọng số có thể âm, đồ thị có thể dày, muốn mã DP rõ ràng.
- **Cân nhắc thuật toán khác:** `n` rất lớn và đồ thị thưa, chỉ cần một nguồn, hoặc cần xử lý nhiều lần thêm/xóa cạnh động.
- **Dijkstra:** từ một nguồn, hiệu quả với trọng số **không âm**; không áp dụng trực tiếp cho đồ thị có cạnh âm tùy ý.
- **Bellman–Ford:** từ một nguồn, xử lý được cạnh âm và phát hiện chu trình âm có thể tới từ nguồn; chạy `O(nm)` trên cách cài phổ biến.
- **Johnson:** giải APSP trên đồ thị thưa bằng phép đổi trọng số và chạy Dijkstra; cần xử lý chu trình âm theo hợp đồng thuật toán.
- **BFS:** nếu mọi cạnh có trọng số như nhau (đặc biệt trọng số `1`), có thể tìm khoảng cách ít cạnh hơn; thường đơn giản và nhanh hơn Floyd cho một nguồn.

Không nên chọn Floyd–Warshall nếu chỉ cần trả một đường từ `s` tới `t` trong một đồ thị rất lớn, thưa, trọng số không âm; một thuật toán một nguồn phù hợp sẽ tiết kiệm đáng kể.

## 13. Kiểm thử đối chứng độc lập với Bellman–Ford

Vì đảo vòng lặp sai có thể qua nhiều ví dụ, nên kiểm thử thuật toán bằng một **oracle có cấu trúc khác**, không chỉ so hai phiên bản Floyd.

### 13.1. Oracle cho đồ thị nhỏ

Với mỗi nguồn `s`:

1. Chạy **Bellman–Ford** từ `s`, thư giãn tất cả cạnh trong tối đa `n-1` lượt.
2. Nếu còn một cạnh `u\to v` có thể relax khi `u` tới được, đánh dấu `v` là có thể bị ảnh hưởng bởi chu trình âm.
3. Từ các đỉnh mới bị ảnh hưởng, duyệt theo hướng cạnh để đánh dấu **mọi đỉnh tới được từ vùng chu trình âm**. Các cặp `(s,t)` được đánh dấu có trạng thái `-\infty`.
4. Các đỉnh chưa bị ảnh hưởng: nếu vẫn không tới được thì INF; nếu tới được thì khoảng cách Bellman–Ford sau `n-1` lượt là kết quả hữu hạn.
5. So **toàn bộ `n^2` trạng thái** với Floyd–Warshall: phân biệt chính xác **INF, -INF và số hữu hạn**.

Để oracle thật sự độc lập, Bellman–Ford không dùng công thức trung gian `k` của Floyd và không dùng chính ma trận `dist[][]` do Floyd tạo.

### 13.2. Kiểm tra đường trả về

Với một cặp có khoảng cách hữu hạn:

- `path[0]==source` và phần tử cuối bằng `target`.
- Mỗi cặp đỉnh liên tiếp trên đường phải có cạnh thật theo đúng hướng.
- Nếu có nhiều cạnh song song, chọn đúng trọng số của cạnh đã dùng hoặc kiểm tra rằng có một lựa chọn cạnh hợp lệ tạo tổng bằng khoảng cách được báo.
- Tổng trọng số dọc đường bằng khoảng cách Floyd báo; không phải chỉ kiểm tra có đủ đỉnh.
- Với `i=j` và không có chu trình âm ảnh hưởng: đường `[i]` có chi phí `0`.

Với cặp `-\infty`, **không đòi hỏi path hữu hạn**. Với cặp INF, **không đòi hỏi path** vì đường không tồn tại.

### 13.3. Các ca biên quan trọng

```text
n=0: đồ thị rỗng
n=1: không cạnh, khoảng cách 0->0 = 0
n=1: khuyên âm 0->0 = -1, trạng thái -INF
n=2: có một chiều 0->1 nhưng không có 1->0
n=4: 0->3->2->1, phản ví dụ i-j-k
Cạnh song song với trọng số khác nhau
Cạnh âm trong DAG nhưng không có chu trình âm
Chu trình âm mà chỉ vài cặp nguồn–đích bị ảnh hưởng
Hai vùng không liên thông, mỗi vùng có/không có chu trình âm
Đường ngắn nhất đi qua nhiều đỉnh trung gian
Đồ thị dày, đồ thị thưa và đỉnh cô lập
Tổng đường đi lớn hơn Long.MAX_VALUE
Cạnh có trọng số Long.MIN_VALUE (BigInteger tránh lỗi cộng)
Nhiều đường bằng nhau (kiểm tra tie-break truy vết)
```

### 13.4. Sinh test ngẫu nhiên có seed

Sinh `n` nhỏ, thêm cạnh có hướng với trọng số trong `[-10,10]`, cho phép cả **khuyên** và **cạnh song song**. So Floyd–Warshall với Bellman–Ford từ mọi nguồn.

Cần có đủ ba loại ca:

- **DAG**: các cạnh chỉ đi từ chỉ số nhỏ sang lớn, có cạnh âm nhưng không thể có chu trình.
- **Đồ thị có hướng tùy ý**: có thể xuất hiện chu trình âm.
- **Đồ thị nhiều thành phần**: có những cặp INF và những cặp hữu hạn/-INF.

Nếu sai khác, lưu seed, danh sách cạnh, source/target và trạng thái đầu tiên không khớp. Sau đó xóa bớt cạnh, giảm số đỉnh và đơn giản hóa trọng số để tạo **phản ví dụ ngắn**.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Đảo vòng thành `i–j–k` hoặc `j–i–k` | Không giữ giai đoạn trung gian, có thể bỏ đường tốt hơn | Đặt `k` ngoài cùng; chỉ hoán đổi `i`/`j` bên trong |
| Ghi nhận “cả ba vòng O(n³) nên hoán đổi như nhau” | Nhầm độ phức tạp với tính đúng | Chứng minh bất biến theo `k` |
| Không khởi tạo `dist[i][i]=0` | Sai đường rỗng và phát hiện chu trình âm | Đường chéo khởi tạo `0`, lấy min với khuyên |
| Gán cạnh song song sau đè lên cạnh tốt hơn | Tăng giả khoảng cách | Khởi tạo min trọng số các cạnh `u\to v` |
| Tự gán cạnh ngược cho đồ thị có hướng | Tạo đường không tồn tại | Chỉ gán `dist[u][v]` đúng chiều |
| Không kiểm tra INF trước khi cộng | Sinh đường giả, sai do sentinel | Bỏ relax nếu một đoạn không tới được |
| Chọn INF quá nhỏ | Nhầm đường hợp lệ rất đắt thành unreachable | Dùng giới hạn đủ lớn có chứng minh hoặc `BigInteger` + `null` |
| Để `long` tràn khi cộng | Khoảng cách âm/dương giả | `Math.addExact` hoặc số nguyên lớn |
| Coi cạnh âm đồng nghĩa chu trình âm | Từ chối sai DAG có cạnh âm | Kiểm tra đường chéo sau Floyd |
| Thấy chu trình âm là đặt cả ma trận -INF | Đánh dấu sai những cặp không thể đi qua chu trình | Kiểm tra `i\rightsquigarrow k\rightsquigarrow j` cho từng cặp |
| Cố truy vết `next` cho cặp -INF | Không có đường ngắn nhất hữu hạn, có thể lặp vô hạn | Trả trạng thái riêng |
| Coi INF và -INF như nhau | Nhầm không tới được với chi phí giảm vô hạn | Dùng enum/trạng thái tách biệt |
| Cập nhật `next[i][j]` theo `next[k][j]` | Bước đầu sai khi `i\ne k` | Dùng `next[i][k]` |
| Không xác minh đường truy vết | Có thể trả dãy đỉnh không khớp khoảng cách | Kiểm tra cạnh/hướng và tổng trọng số |
| Không giới hạn truy vết | Ma trận `next` lỗi có thể gây loop | Giới hạn bước, báo lỗi rõ |
| So đường đi giống hệt khi có hòa | Hai đường ngắn nhất hợp lệ có thể khác | So chi phí và tính hợp lệ, chốt tie-break nếu cần |
| Dùng Floyd trên đồ thị vô hướng có cạnh âm và vẫn đòi đáp án hữu hạn | Walk có thể lặp cạnh âm qua lại, chi phí -INF | Kiểm tra chu trình âm và đúng định nghĩa bài |
| Chỉ so `dist[n-1][n-1]` trong test | Bỏ sót lỗi ở các cặp khác | So toàn bộ ma trận trạng thái |
| Không thử phản ví dụ đảo vòng | Thứ tự sai có thể vẫn đúng trên ca đơn giản | Giữ ca `0\to3\to2\to1` làm regression test |
| Lưu từng ma trận `D^k` không cần thiết | Tốn `O(n³)` bộ nhớ | Cập nhật tại chỗ với `k` ở ngoài |
| Tính mọi cặp khi chỉ cần một nguồn | Lãng phí trên đồ thị lớn | Chọn Dijkstra/Bellman–Ford thích hợp |

## 15. Bài tập tự luyện và đáp án

**Bài 1 — Khởi tạo.** Với hai đỉnh `0,1` chỉ có cạnh `0\to1` trọng số `7`, ma trận ban đầu là gì?

*Đáp án:* `[[0,7],[INF,0]]`, vì đường `1\to0` không tồn tại.

**Bài 2 — Cạnh song song.** Nếu có hai cạnh `0\to1` trọng số `9` và `4`, giá trị khởi tạo `dist[0][1]` bằng bao nhiêu?

*Đáp án:* `4`, không phụ thuộc thứ tự hai cạnh trong danh sách input.

**Bài 3 — Trung gian.** Đồ thị có `0\to1` trọng số `5`, `1\to2` trọng số `-2`, `0\to2` trọng số `10`. Sau khi cho phép `k=1` làm trung gian, `dist[0][2]` là bao nhiêu?

*Đáp án:* `min(10,5-2)=3`.

**Bài 4 — Đảo vòng.** Với chuỗi `0\to3\to2\to1`, mỗi cạnh trọng số `1`, vì sao `i–j–k` có thể trả INF cho `(0,1)`?

*Đáp án:* ô `(0,1)` được xét trước khi `(0,2)` có khoảng cách `2` hoặc `(3,1)` có khoảng cách `2`; sau đó không được xét lại. `k–i–j` trả `3`.

**Bài 5 — Hai vòng trong.** Vì sao `k–j–i` vẫn là một thứ tự hợp lệ cho Floyd–Warshall chuẩn?

*Đáp án:* mọi phép relax của cùng một `k` vẫn nằm trong giai đoạn `k`. Khi không có chu trình âm, hàng/cột `k` dùng làm nguồn không đổi trong giai đoạn; chỉ thứ tự cập nhật các cặp `(i,j)` bị hoán đổi.

**Bài 6 — Chu trình âm.** Có cạnh `0\to1` trọng số `2`, `1\to2` trọng số `1` và `2\to1` trọng số `-3`. `dist(0,2)` là hữu hạn hay `-\infty`?

*Đáp án:* `-\infty`. Chu trình `1\to2\to1` có tổng `-2`, có thể đi từ `0` vào và tới `2` sau khi lặp tùy ý.

**Bài 7 — Cặp không bị ảnh hưởng.** Trong ví dụ phần 8, vì sao `dist(4,0)=5` chứ không phải `-\infty`?

*Đáp án:* từ `4` đi được tới chu trình âm, nhưng từ chu trình ấy **không quay về `0`**. Điều kiện tới chu trình rồi đi từ chu trình tới đích `0` không thỏa.

**Bài 8 — Không tới được.** Nếu `dist[3][0]=INF`, có nên trả `-\infty` chỉ vì ở vùng khác đồ thị có chu trình âm không?

*Đáp án:* không. Không có walk từ `3` tới `0`, nên kết quả là **INF**, không phải `-\infty`.

**Bài 9 — Cạnh âm nhưng không chu trình.** Một DAG có cạnh âm có bắt buộc phải báo chu trình âm không?

*Đáp án:* không; DAG không có chu trình nào. Floyd xử lý cạnh âm bình thường.

**Bài 10 — Truy vết.** Khi tìm được đường tốt hơn `i\rightsquigarrow k\rightsquigarrow j`, tại sao phải dùng `next[i][j]=next[i][k]`?

*Đáp án:* bước đầu từ `i` trên đường mới là bước đầu của đoạn `i\rightsquigarrow k`, không phải bước từ `k` tới `j`.

**Bài 11 — Số học.** Nếu hai cạnh liên tiếp đều có trọng số `Long.MAX_VALUE`, tổng chi phí phải biểu diễn là gì?

*Đáp án:* `18446744073709551614`, vượt `long` có dấu. `BigInteger` có thể lưu chính xác; cộng `long` thông thường sẽ tràn.

**Bài 12 — Tự kiểm thử.** Sinh đồ thị có hướng tối đa `8` đỉnh, trọng số từ `-10` tới `10`, có thể chứa khuyên/cạnh song song. Hãy dùng Bellman–Ford từ từng nguồn làm oracle cho Floyd.

*Đáp án mong đợi:* mọi cặp phải khớp đúng trạng thái **INF / hữu hạn / -INF**. Với cặp hữu hạn, kiểm tra đường trả về theo đúng hướng và tổng chi phí.

**Bài 13 — Giới hạn bộ nhớ.** Nếu lưu toàn bộ `D^{(k)}` cho `k=-1,\ldots,n-1` thay vì cập nhật tại chỗ, độ phức tạp bộ nhớ tăng từ bao nhiêu lên bao nhiêu?

*Đáp án:* từ `O(n^2)` lên `O(n^3)`.

**Bài 14 — Đúng phạm vi.** Có thể dùng bảng khoảng cách Floyd sau ba vòng để trả một con số “ngắn nhất” cho cặp đi qua chu trình âm không?

*Đáp án:* không; cặp đó có infimum `-\infty`, không có minimum hữu hạn. Phải đánh dấu `negativeInfinite[i][j]` và trả trạng thái riêng.

## 16. Checklist khi viết Floyd–Warshall trong bài thi

Trước khi tin vào kết quả, hãy kiểm tra tuần tự:

1. Đồ thị là **có hướng hay vô hướng**? Có tạo cạnh ngược đúng khi cần?
2. `dist[i][i]` đã được khởi tạo bằng `0` chưa? Có khuyên âm cần lấy min không?
3. Cạnh song song có được lấy **min trọng số** không?
4. Có trạng thái riêng cho **không tới được** không?
5. Có bảo vệ phép cộng khỏi **INF và overflow** không?
6. **`k` đã ở vòng ngoài cùng chưa?** Hai vòng trong `i,j` có thể đổi, nhưng không kéo `k` vào trong một cách tùy tiện.
7. Có chứng minh bất biến “cho phép trung gian `0..k`” không?
8. Có cạnh âm? Có kiểm tra `dist[k][k]<0` sau ba vòng không?
9. Khi có chu trình âm, có đánh dấu **đúng cặp** `i\rightsquigarrow k\rightsquigarrow j` là `-\infty` không?
10. Có phân biệt **INF, số hữu hạn và -INF** trong kết quả/API không?
11. Khi cần in đường, đã dùng và kiểm tra `next[][]`, tránh truy vết cặp INF/-INF chưa?
12. Đã thử **phản ví dụ đảo vòng** `0\to3\to2\to1` chưa?
13. Đã đối chứng mọi cặp trên đồ thị nhỏ với một oracle **khác cấu trúc** như Bellman–Ford chưa?
14. Độ phức tạp **`O(n^3)`** có phù hợp với `n` và số truy vấn của đề bài không?

## Ghi nhớ

Floyd–Warshall là một DP theo **tập các đỉnh trung gian được phép sử dụng**:

\[
\boxed{
dist[i][j]\gets
\min\bigl(dist[i][j],dist[i][k]+dist[k][j]\bigr)
\quad\text{với }k\text{ là vòng ngoài}.
}
\]

- **`k–i–j` hoặc `k–j–i`** giữ bất biến quy hoạch động; **`i–j–k`** một lượt có thể sai ngay trên DAG `0\to3\to2\to1` với trọng số dương.
- Có cạnh âm **vẫn chạy được**; có chu trình âm thì phải phân loại những cặp bị ảnh hưởng là **`-\infty`**.
- `dist[k][k]<0` phát hiện chu trình âm; một cặp `(i,j)` là `-\infty` khi có thể đi từ `i` tới chu trình rồi tới `j`.
- **UNREACHABLE** khác **-INF**; không được cộng sentinel INF hoặc để phép cộng tràn.
- Có thể dùng `next[][]` truy vết một đường ngắn nhất **hữu hạn**; không truy vết cặp không tới được hoặc bị chu trình âm làm không bị chặn dưới.
- Thời gian chuẩn **`O(n^3)`**, bộ nhớ **`O(n^2)`**.

**Thứ tự vòng lặp ở Floyd–Warshall không phải chuyện cú pháp. Nó biểu diễn thứ tự mở rộng không gian trạng thái DP. Hiểu bất biến theo `k` sẽ giúp triển khai đúng, phát hiện lỗi đảo vòng và giải thích được vì sao thuật toán tìm đủ mọi đường đi ngắn nhất.**

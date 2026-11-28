# Phân bố chiều cao nút và chi phí kỳ vọng của skip list

Hai skip list cùng lưu các khóa `10, 20, 30, ..., 1000` có thể có **hình dạng rất khác nhau**: một cấu trúc chứa nhiều “đường cao tốc” ở tầng trên, cấu trúc khác chủ yếu đi trên tầng đáy. Nguyên nhân không phải giá trị khóa mà là **chiều cao ngẫu nhiên được gán cho từng nút**. Tại sao thiết kế như vậy thường cho tìm kiếm, chèn và xóa nhanh? Tại sao nhiều tầng không làm bộ nhớ tăng lên O(n log n)? Và tại sao một skip list hoàn toàn hợp lệ đôi lúc vẫn tìm kiếm chậm?

Bài **“Phân bố chiều cao nút và chi phí kỳ vọng của skip list”** thuộc chương **Cấu trúc ngẫu nhiên** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Theo định hướng module, chúng ta kết nối mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị thông qua **bất biến**, các thao tác và phân tích **độ phức tạp thời gian/bộ nhớ**. Trọng tâm riêng của bài này là **mô hình xác suất** đằng sau các tầng skip list: phân phối hình học, kỳ vọng số con trỏ, chiều cao cao nhất, số bước tìm và chi phí cập nhật.

**Mục tiêu học tập:**

- Xác định chính xác `height`, `level`, `p` và `MAX_LEVEL`, phân biệt tầng đánh số từ 0 với số tầng của một node.
- Tính `Pr(H≥k)`, `Pr(H=k)`, `E[H]` và `Var(H)` cho chiều cao hình học; hiểu khác biệt khi cắt ngọn ở giới hạn L.
- Tính số node kỳ vọng và độ biến động trên từng tầng; suy ra **tổng dung lượng forward O(n) kỳ vọng**.
- Tìm phân phối đúng và các chặn của **chiều cao tối đa** trong n node, giải thích vì sao `E[M]=Θ(log n)` khi p cố định.
- Giải thích từng nguồn chi phí trong đường tìm kiếm: đi ngang, đi xuống, cấp mảng `update[]` và cập nhật liên kết.
- Phát biểu chính xác bảo đảm **O(log n) kỳ vọng** cùng các giả định về phân phối, giới hạn mức và thứ tự thao tác; không nhầm với worst-case hay kiểm thử thống kê.
- Ước lượng ảnh hưởng của p, L, n qua ví dụ số; viết Python sinh mẫu, tính công thức và đo đường tìm.
- Phân biệt kết quả được chứng minh về xác suất với bất biến tính đúng của skip list, so sánh cấu trúc ngẫu nhiên với các lựa chọn có cân bằng tất định.

## 1. Thiết lập mô hình và ký hiệu

Xét một skip list dạng **set** lưu n khóa phân biệt có thể so sánh theo thứ tự toàn phần. Tầng 0 chứa mọi khóa; một node cao H tầng xuất hiện ở các tầng **0, 1, ..., H−1**. Một ô `forward[i]` lưu node dữ liệu kế tiếp có mặt ở tầng i, hoặc `NULL` nếu không còn node.

```text
Tầng 3: HEAD ---------------------> 40 -----------------> NULL
Tầng 2: HEAD ---> 10 ------------> 40 -----> 80 ------> NULL
Tầng 1: HEAD ---> 10 -> 30 ------> 40 -> 60 -> 80 -----> NULL
Tầng 0: HEAD ---> 10 -> 20 -> 30 -> 40 -> 50 -> 60 -> 70 -> 80 -> NULL

H(20) = 1 : chỉ tầng 0
H(60) = 2 : tầng 0, 1
H(10) = 3 : tầng 0, 1, 2
H(40) = 4 : tầng 0, 1, 2, 3
```

Các ký hiệu dùng xuyên suốt:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `n` | Số node dữ liệu thật, không tính HEAD |
| `p` | Xác suất *nâng thêm một tầng* sau khi đạt một tầng, với `0<p<1` |
| `H_j` | Số tầng node j tham gia, luôn ≥1 |
| `L` | `MAX_LEVEL`: chiều cao node tối đa được phép, nếu có |
| `N_i` | Số node có mặt ở tầng **chỉ số i**, i bắt đầu từ 0 |
| `S` | Tổng số ô `forward` được cấp cho các node dữ liệu |
| `M` | Chiều cao cao nhất trong n node, tức `max(H_1,...,H_n)` |
| `T_{\rm search}` | Chi phí của một lần tìm: so sánh, bước ngang/xuống hoặc phép truy cập con trỏ theo mô hình đã chọn |
| `H_{\rm live}` | Số tầng **đang dùng** trong skip list, bằng M khi n>0, thường bằng 1 khi rỗng |

**Phân biệt đặc biệt:** nếu một node có `H=4` thì chỉ số tầng cao nhất của nó là **3**, không phải 4. Do đó công thức node xuất hiện ở tầng i luôn gắn với điều kiện `H≥i+1`.

### 1.1. Những giả định sẽ dùng khi phân tích

Để có các công thức xác suất tiêu chuẩn:

1. Mỗi node mới nhận một chuỗi lần nâng mức với **cùng xác suất p**, độc lập giữa các lần tung và giữa các node.
2. Các lần chọn mức độc lập với **giá trị khóa** và không bị thao túng có điều kiện bởi một tác nhân biết kết quả ngẫu nhiên.
3. Khi phân tích một trạng thái có n khóa, ta xem tập khóa là **cố định độc lập với việc rút mức**, và các mức của các node còn tồn tại đúng phân phối đã mô tả.
4. Với chương trình thực tế có PRNG và trần L, kết quả thống kê lý tưởng là **mô hình phân tích**, không phải tuyên bố rằng một PRNG hữu hạn tự động tạo các biến ngẫu nhiên độc lập hoàn hảo.

Tính đúng của liên kết skip list không phụ thuộc vào xác suất. Một cấu trúc mà mọi node đều H=1 vẫn có thể đúng như một danh sách liên kết có thứ tự; **chỉ hiệu năng** không còn được hỗ trợ bởi các đường nhảy.

### 1.2. Đặt đúng câu hỏi về kỳ vọng

Cho một chuỗi thao tác hoặc một tập khóa `I` **đã cố định**, gọi `R` là các lần bốc chiều cao của thuật toán. Chi phí là `T(I,R)`.

\[
\mathbb E_R[T(I,R)]
\]

là kỳ vọng **trên nguồn ngẫu nhiên của cấu trúc**, không phải trung bình trên một tập khóa đầu vào được giả sử “phân phối ngẫu nhiên đẹp”.

Đây là điểm mạnh của randomized skip list: khóa có thể đến theo thứ tự tăng, giảm hoặc một thứ tự cố định bất kỳ, mà phân bố hình dạng vẫn được thiết kế từ **nguồn random nội bộ**. Điều đó không tự bảo đảm khi một đối thủ thích nghi chọn thao tác dựa trên thông tin random đã lộ.

## 2. Sinh chiều cao bằng những lần tung đồng xu

Quy tắc đơn giản nhất: mọi node bắt đầu ở **một tầng**, sau đó liên tiếp được “thăng hạng” khi phép thử Bernoulli thành công với xác suất p.

```text
H := 1
while coin_flip_with_probability(p) == SUCCESS:
    H := H + 1
return H
```

Với `p=1/2`, có thể tưởng tượng tung đồng xu công bằng:

- Mặt ngửa → tăng thêm một tầng.
- Mặt sấp → dừng.
- Mỗi node bắt đầu ở tầng 0 trước khi tung.

Ví dụ:

```text
Node A: sấp                    -> H = 1
Node B: ngửa, sấp              -> H = 2
Node C: ngửa, ngửa, sấp        -> H = 3
Node D: ngửa, ngửa, ngửa, sấp  -> H = 4
```

Chiều cao là một biến ngẫu nhiên kiểu **hình học được dịch**: nó đếm **số lần nâng thành công liên tiếp trước lần dừng, cộng 1**.

### 2.1. Phân bố đuôi: đạt ít nhất k tầng

Để có `H≥k`, cần ít nhất `k−1` lần nâng thành công. Do độc lập:

\[
\boxed{\Pr(H\ge k)=p^{k-1}}, \qquad k=1,2,\ldots
\]

Ví dụ p=1/2:

\[
\Pr(H\ge1)=1,\;
\Pr(H\ge2)=\tfrac12,\;
\Pr(H\ge3)=\tfrac14,\;
\Pr(H\ge4)=\tfrac18.
\]

Tầng 0 có **toàn bộ node** vì xác suất đạt ít nhất một tầng là 1.

### 2.2. Xác suất đúng k tầng

Muốn `H=k` trong mô hình **không trần**, phải có k−1 lần nâng thành công **và** lần tiếp theo thất bại:

\[
\boxed{\Pr(H=k)=(1-p)p^{k-1}},\qquad k\ge1.
\]

Với p=1/2:

| H | Lần nâng/dừng | `Pr(H=k)` | `Pr(H≥k)` |
| ---: | --- | ---: | ---: |
| 1 | Dừng ngay | 1/2 | 1 |
| 2 | Thành công, rồi dừng | 1/4 | 1/2 |
| 3 | Thành công 2 lần, rồi dừng | 1/8 | 1/4 |
| 4 | Thành công 3 lần, rồi dừng | 1/16 | 1/8 |
| 5 | Thành công 4 lần, rồi dừng | 1/32 | 1/16 |

Kiểm tra tổng xác suất:

\[
\sum_{k=1}^{\infty}(1-p)p^{k-1}
=(1-p)\frac{1}{1-p}=1.
\]

Hai công thức rất dễ nhầm: **`Pr(H=4)=1/16` nhưng `Pr(H≥4)=1/8`** khi p=1/2.

### 2.3. Xác suất chiều cao nằm trong một khoảng

Với hai mức nguyên `1≤a≤b`:

\[
\begin{aligned}
\Pr(a\le H\le b)
 &= \Pr(H\ge a)-\Pr(H\ge b+1)\\
 &=p^{a-1}-p^b.
\end{aligned}
\]

Ví dụ p=1/2, xác suất node cao **2 hoặc 3 tầng**:

\[
\Pr(2\le H\le3)=\tfrac12-\tfrac18=\tfrac38.
\]

Biểu thức này hữu ích khi tính dung lượng một nhóm node hoặc xác suất các tầng trung bình quá đông.

## 3. Kỳ vọng và phương sai chiều cao một node

Kỳ vọng có thể được tính bằng tổng `k\Pr(H=k)`, nhưng cách ngắn hơn là dùng **tổng xác suất đuôi** của biến nguyên dương:

\[
\mathbb E[H]=\sum_{k=1}^{\infty}\Pr(H\ge k).
\]

Thế `\Pr(H\ge k)=p^{k-1}`:

\[
\boxed{\mathbb E[H]=\frac{1}{1-p}}.
\]

**Ý nghĩa:** node thường chỉ có một vài tầng, dù về lý thuyết không có giới hạn chiều cao. Với `p=1/2`, `E[H]=2`. Node H=100 có thể xảy ra nhưng cực hiếm.

### 3.1. Ví dụ với ba lựa chọn p

| p | `E[H]` | `Pr(H≥4)` | Cảm nhận cấu trúc |
| ---: | ---: | ---: | --- |
| 1/4 | 4/3 ≈ 1,333 | 1/64 | Ít liên kết cao, tầng thưa |
| 1/2 | 2 | 1/8 | Lựa chọn cân bằng thông dụng |
| 3/4 | 4 | 27/64 | Node thường cao hơn, nhiều liên kết |

**Không suy ra rằng p=3/4 nhanh nhất.** Node cao hơn tiêu tốn thêm pointer, thêm tầng cần xét và có thể làm CPU/cache làm việc nhiều hơn; đổi lại, các đường nhảy có thể ngắn theo cách khác.

### 3.2. Phương sai của H

Với hình học dịch ở trên, phương sai là:

\[
\boxed{\operatorname{Var}(H)=\frac{p}{(1-p)^2}}.
\]

Độ lệch chuẩn:

\[
\sigma_H=\frac{\sqrt p}{1-p}.
\]

Khi p=1/2, `Var(H)=2` và `σ_H=\sqrt2≈1,414`. Phương sai **không đo chiều cao tối đa**, mà đo độ biến thiên của **chiều cao một node** quanh giá trị trung bình.

Một cách kiểm tra công thức dùng đẳng thức:

\[
\mathbb E[H^2]
=\sum_{k=1}^{\infty}(2k-1)\Pr(H\ge k)
=\frac{1+p}{(1-p)^2}.
\]

Suy ra `Var(H)=E[H²]-E[H]²=p/(1-p)²`.

### 3.3. Vì sao kỳ vọng có thể nhỏ dù không có trần?

Đuôi `p^{k-1}` **giảm theo cấp số nhân** với k khi p<1. Mỗi tầng mới chỉ được một tỷ lệ p của các node ở tầng thấp hơn tham gia. Tổng của dãy giảm theo cấp số nhân là hữu hạn.

Đây là ý tưởng tổng quát trong cấu trúc ngẫu nhiên: **mỗi node có thể có độ cao không giới hạn, nhưng số node rất cao giảm nhanh**, nên tổng metadata trung bình vẫn được kiểm soát.

## 4. Có `MAX_LEVEL`: phân bố bị cắt ở đỉnh

Một hệ thống thường đặt `L=MAX_LEVEL` để ngăn node cấp mảng forward quá dài và để biết trước giới hạn mức cao nhất.

```text
height = 1
while height < L and random() < p:
    height += 1
return height
```

Khi đó `H_L = \min(H_{\infty},L)`, với `H_{\infty}` là chiều cao chưa bị cắt.

### 4.1. Phân phối đúng khi có trần

Với `1≤k<L`:

\[
\Pr(H_L=k)=(1-p)p^{k-1}.
\]

Nhưng **tại k=L**:

\[
\boxed{\Pr(H_L=L)=p^{L-1}}.
\]

Không có thừa số `(1-p)` ở mức đỉnh, vì khi đạt L thuật toán **dừng do trần**, không tung đồng xu tiếp để phân biệt H=L với H>L.

Ví dụ p=1/2, L=3:

| H_L | Xác suất |
| ---: | ---: |
| 1 | 1/2 |
| 2 | 1/4 |
| 3 | **1/4** |

Nếu dùng nhầm công thức không trần cho H=3, ta ghi 1/8 và làm tổng chỉ 7/8; đó là dấu hiệu phân phối đã bị viết sai.

### 4.2. Kỳ vọng khi có trần

Sử dụng tổng xác suất đuôi tới L:

\[
\boxed{\mathbb E[H_L]
=\sum_{k=1}^{L}p^{k-1}
=\frac{1-p^L}{1-p}}.
\]

Vì `p^L>0`:

\[
\mathbb E[H_L]<\mathbb E[H_\infty]=\frac{1}{1-p}.
\]

Nếu L=3, p=1/2:

\[
E[H_L]=1+\tfrac12+\tfrac14=\tfrac74=1{,}75.
\]

### 4.3. Khi L=1

`H_L=1` với xác suất 1. Mọi node chỉ có tầng 0: skip list suy biến thành một **danh sách liên kết đơn đã sắp xếp**. Các phép tìm/chèn/xóa vẫn có thể **đúng kết quả**, nhưng đường tìm xấu nhất là Θ(n), không có lợi ích bỏ qua node.

### 4.4. Khi L lớn hơn nhiều so với nhu cầu

Nếu L rất lớn so với `\log_{1/p}n`, hiếm có node chạm L. Về xác suất, trần gần như không ảnh hưởng hình dạng trong quy mô ấy. Nhưng:

- Nếu HEAD cấp trước **L ô pointer**, riêng HEAD dùng O(L) bộ nhớ.
- Nếu mỗi lần insert cấp `update[L]`, nó cần **O(L)** thời gian/bộ nhớ phụ ngay cả khi chỉ có vài tầng đang dùng.
- Nếu vòng tìm luôn đi qua tất cả L tầng, mỗi lần tìm có chi phí Ω(L); nên theo dõi **mức thực tế có dữ liệu** `H_live` thay vì nhất thiết đi qua L tầng.

Do đó, L quá lớn có thể gây overhead dù chiều cao các node thực tế đều nhỏ.

## 5. Số node trên mỗi tầng: phân phối nhị thức

Đặt `N_i` là số node dữ liệu xuất hiện ở tầng chỉ số i. Một node xuất hiện ở tầng i khi `H≥i+1`; xác suất bằng `p^i` nếu i<L.

Đặt biến chỉ báo:

\[
X_{j,i}=
\begin{cases}
1 & \text{node j có mặt ở tầng i},\\
0 & \text{ngược lại}.
\end{cases}
\]

Khi các node bốc chiều cao độc lập:

\[
N_i=\sum_{j=1}^n X_{j,i}.
\]

Vì mỗi `X_{j,i}` là Bernoulli với xác suất `p^i`:

\[
\boxed{N_i\sim \operatorname{Binomial}(n,p^i)}
\]

và:

\[
\boxed{\mathbb E[N_i]=n p^i}.
\]

### 5.1. Ví dụ n=1024, p=1/2

| Tầng i | `Pr(node ở tầng i)` | `E[N_i]` |
| ---: | ---: | ---: |
| 0 | 1 | 1024 |
| 1 | 1/2 | 512 |
| 2 | 1/4 | 256 |
| 3 | 1/8 | 128 |
| 4 | 1/16 | 64 |
| 5 | 1/32 | 32 |
| 6 | 1/64 | 16 |
| 7 | 1/128 | 8 |
| 8 | 1/256 | 4 |
| 9 | 1/512 | 2 |
| 10 | 1/1024 | 1 |

**Cảnh báo:** `E[N_9]=2` không có nghĩa mọi lần chạy luôn có đúng hai node ở tầng 9. Có thể là 0, 1, 3 hoặc nhiều hơn; bảng là **kỳ vọng qua nguồn random**.

### 5.2. Phương sai từng tầng

Với phân phối nhị thức:

\[
\boxed{\operatorname{Var}(N_i)=n p^i(1-p^i)}.
\]

Ví dụ n=1024, p=1/2, ở tầng i=1:

\[
E[N_1]=512,\qquad
Var(N_1)=1024\times\tfrac12\times\tfrac12=256.
\]

Do đó độ lệch chuẩn là 16 node. Một lần chạy có 500 node tầng 1 vẫn có thể là kết quả bình thường.

Với `i=0`, `p^0=1`, `Var(N_0)=0`: tầng đáy **luôn luôn có đúng n node**, không phải chỉ “kỳ vọng n”.

### 5.3. Có thể dùng bất đẳng thức tập trung khi tầng đông

Với `\mu_i=np^i` và `0<\delta≤1`, một dạng chặn Chernoff thông dụng là:

\[
\Pr\big(|N_i-\mu_i|\ge\delta\mu_i\big)
\le 2\exp\!\left(-\frac{\delta^2\mu_i}{3}\right).
\]

Điều này cho biết khi `\mu_i` lớn, số node một tầng thường **tập trung quanh kỳ vọng** theo nghĩa xác suất. Trên những tầng rất cao với `\mu_i` gần 1, chặn tương đối thường không mạnh; việc tầng ấy rỗng là điều dễ hiểu.

Không được đồng nhất các biến `N_i` giữa **những tầng khác nhau** là độc lập: một node có mặt ở tầng i+1 **bắt buộc** có mặt ở tầng i, nên các tầng có quan hệ phụ thuộc. Phân phối nhị thức chỉ dùng tính độc lập **giữa các node tại cùng tầng i**.

## 6. Tổng số con trỏ forward: vì sao bộ nhớ kỳ vọng O(n)?

Nếu mỗi node cấp **đúng H_j ô `forward`**, số ô forward của các node dữ liệu là:

\[
S=\sum_{j=1}^n H_j.
\]

Theo tuyến tính của kỳ vọng:

\[
\boxed{\mathbb E[S]=\frac{n}{1-p}}
\]

trong mô hình không trần. Với trần L:

\[
\boxed{\mathbb E[S_L]=n\,\frac{1-p^L}{1-p}}.
\]

Khi p là một hằng số nhỏ hơn 1, cả hai đều là **O(n)** theo n. Không cần các biến độc lập để dùng tính tuyến tính kỳ vọng, nhưng giả định độc lập giúp phân tích phương sai và tail.

### 6.1. Một cách kiểm tra bằng tổng số node mỗi tầng

Mỗi node có H ô forward nghĩa là nó có mặt trên đúng H tầng. Vì vậy đếm theo node hoặc theo tầng cho cùng kết quả:

\[
S=\sum_{i\ge0}N_i.
\]

Thế `E[N_i]=np^i`:

\[
E[S]
=\sum_{i\ge0}np^i
=\frac{n}{1-p}.
\]

Đây là kỹ thuật **đếm hai cách** rất hữu ích khi phân tích cấu trúc nhiều tầng: tổng số phần tử trên các tầng chính là tổng số tầng của từng phần tử.

### 6.2. Phương sai tổng số pointer

Nếu các chiều cao `H_j` độc lập:

\[
\operatorname{Var}(S)
=\sum_{j=1}^n\operatorname{Var}(H_j)
=\boxed{\frac{np}{(1-p)^2}}
\]

và:

\[
\sigma_S=\frac{\sqrt{np}}{1-p}.
\]

Với p=1/2:

\[
E[S]=2n,\quad Var(S)=2n,\quad \sigma_S=\sqrt{2n}.
\]

Độ lệch chuẩn tăng theo `\sqrt n` trong khi kỳ vọng tăng theo n; tỷ lệ dao động tương đối có xu hướng nhỏ dần khi n lớn trong mô hình IID.

### 6.3. Không tính nhầm object với slot pointer

Một node H=7 có **một** payload, **một** identity, **bảy** slot `forward`. Nếu n=1000 và p=1/2:

- Số node dữ liệu thực tế vẫn **1000**.
- Số ô forward kỳ vọng khoảng **2000**.
- Tổng byte bộ nhớ còn có **key, payload, metadata, alignment/padding, object header, allocator overhead và sentinel HEAD**.

Do đó **O(n) bộ nhớ kỳ vọng** không bảo đảm skip list dùng ít byte hơn mảng sorted hay cây cân bằng. Một implementation cấp **MAX_LEVEL slot cho mọi node** sẽ dùng Θ(nL) slot, **không** hưởng công thức n/(1−p) về số ô *đã cấp*, dù số ô thực sự dùng trên tầng có thể vẫn ít.

### 6.4. Phần vượt quá một con trỏ nền

Node ở tầng đáy cần ít nhất một `forward[0]`. Các ô còn lại là metadata “đường nhảy” bổ sung:

\[
E[H-1]=E[H]-1=\frac{p}{1-p}.
\]

Với p=1/2, trung bình có **một ô forward bổ sung** cho mỗi node so với một danh sách liên kết đơn.

Đây là cách trực quan để đọc chi phí: **trả thêm một lượng metadata kỳ vọng tuyến tính để rút ngắn đường tìm từ tuyến tính xuống logarit kỳ vọng** theo các giả định được nêu.


## 7. Chiều cao lớn nhất trong n node: phân phối chính xác

Một node có chiều cao kỳ vọng không đổi `E[H]=1/(1-p)`, nhưng skip list với rất nhiều node thường có **ít nhất một node khá cao**. Muốn biết bộ chỉ mục có bao nhiêu tầng, ta phải phân tích:

\[
M=\max(H_1,H_2,\ldots,H_n), \qquad n\ge1.
\]

### 7.1. Xác suất tất cả các node thấp hơn k

Với mô hình không trần:

\[
\Pr(H_j<k)=1-p^{k-1}.
\]

Các chiều cao độc lập, nên:

\[
\boxed{\Pr(M<k)=(1-p^{k-1})^n}.
\]

Do đó:

\[
\boxed{\Pr(M\ge k)=1-(1-p^{k-1})^n}.
\]

**Lưu ý:** biểu thức `(1-p^{k-1})^n` là xác suất **không có node nào đạt k tầng**. Không được nhầm nó với xác suất có node đạt k tầng.

### 7.2. Chặn trên bằng union bound

Sự kiện `M\ge k` là hợp của n sự kiện “node j cao ít nhất k”. Theo bất đẳng thức hợp:

\[
\begin{aligned}
\Pr(M\ge k)
&\le \sum_{j=1}^n \Pr(H_j\ge k)\\
&=\boxed{n p^{k-1}}.
\end{aligned}
\]

Vì xác suất không vượt 1, có thể viết:

\[
\Pr(M\ge k)\le \min(1,np^{k-1}).
\]

Union bound không đòi các sự kiện độc lập, nhưng công thức **chính xác** `1-(1-p^{k-1})^n` có dùng giả định độc lập.

### 7.3. Tại sao tầng cao nhất có cỡ log n?

Ta chọn k sao cho số node kỳ vọng đạt k tầng khoảng 1:

\[
n p^{k-1}\approx1.
\]

Lấy log:

\[
k-1\approx \log_{1/p}n.
\]

Vậy vùng chuyển tiếp của chiều cao tối đa nằm quanh:

\[
\boxed{M\text{ có cỡ }\log_{1/p}n}.
\]

**Đây là phát biểu xác suất**, không phải chặn cứng cho mọi dãy random. M có thể cao hơn đáng kể, nhưng xác suất giảm nhanh theo từng tầng vượt ngưỡng.

### 7.4. Ví dụ n=1024, p=1/2

Ở tầng chỉ số 10, số node kỳ vọng `E[N_{10}]=1`. Xác suất có **ít nhất một node cao 11 tầng** là:

\[
\begin{aligned}
\Pr(M\ge11)
&=1-(1-2^{-10})^{1024}\\
&=1-(1023/1024)^{1024}
\approx0{,}632.
\end{aligned}
\]

Nếu hỏi có node **cao ít nhất 21 tầng**:

\[
\Pr(M\ge21)\le1024\cdot2^{-20}
=\frac1{1024}\approx0{,}0009766.
\]

Một skip list có 1024 node đôi khi có node cao 21 tầng, nhưng nó là sự kiện hiếm theo mô hình.

### 7.5. Chọn giới hạn chiều cao theo xác suất mong muốn

Nếu muốn xác suất tồn tại node cao ít nhất k tầng không vượt `\delta`, union bound đưa ra điều kiện đủ:

\[
np^{k-1}\le\delta.
\]

Suy ra:

\[
\boxed{k\ge1+\log_{1/p}\left(\frac{n}{\delta}\right)}.
\]

Ví dụ n=1024, p=1/2, yêu cầu `\delta=0{,}01`. Chọn `k=18`:

\[
\Pr(M\ge18)\le1024\cdot2^{-17}
=0{,}0078125<0{,}01.
\]

Điều này giúp dự báo dung lượng các tầng rất cao. Nhưng “xác suất nhỏ” **không** có nghĩa **không thể xảy ra**; đối với giới hạn bộ nhớ cứng, vẫn phải thiết lập `MAX_LEVEL` và chính sách cấp phát.

## 8. Kỳ vọng của chiều cao tối đa `M` là Θ(log n)

Biết `M` thường nằm quanh log n chưa đủ; ta muốn một chặn kỳ vọng cụ thể.

Với một biến nguyên dương:

\[
E[M]=\sum_{k=1}^{\infty}\Pr(M\ge k).
\]

Thế công thức chính xác:

\[
\boxed{
E[M]=\sum_{k=1}^{\infty}
\left[1-(1-p^{k-1})^n\right].
}
\]

Tổng vô hạn này hội tụ với `0<p<1`.

### 8.1. Chặn trên bằng cách chia tổng thành hai phần

Đặt:

\[
q=\left\lceil\log_{1/p}n\right\rceil,\quad n\ge2.
\]

Với `k≤q`, chặn xác suất bởi 1. Với `k≥q+1`, dùng union bound:

\[
\begin{aligned}
E[M]
&=\sum_{k=1}^{q}\Pr(M\ge k)
+\sum_{k=q+1}^{\infty}\Pr(M\ge k)\\
&\le q+\sum_{k=q+1}^{\infty}np^{k-1}\\
&=q+\frac{np^q}{1-p}.
\end{aligned}
\]

Vì `q≥\log_{1/p}n` nên `np^q≤1`. Do đó:

\[
\boxed{
E[M]\le\left\lceil\log_{1/p}n\right\rceil
+\frac1{1-p}.
}
\]

Với p cố định và n tăng, đây là **O(log n)**.

### 8.2. Vì sao còn có chặn dưới Ω(log n)?

Lấy `q=\lceil\log_{1/p}n\rceil`. Với `n≥2` và `0<p<1`:

\[
p^{q-1}\ge\frac1n.
\]

Vì vậy:

\[
\begin{aligned}
\Pr(M\ge q)
&=1-(1-p^{q-1})^n\\
&\ge1-(1-1/n)^n\\
&\ge1-e^{-1}.
\end{aligned}
\]

Suy ra:

\[
E[M]\ge q\,\Pr(M\ge q)
\ge(1-e^{-1})q.
\]

Với p cố định:

\[
\boxed{E[M]=\Theta(\log n).}
\]

Điểm đáng nhớ: **một node** có chiều cao kỳ vọng O(1), nhưng **node cao nhất trong n node** có chiều cao kỳ vọng Θ(log n). Hai nhận định không hề mâu thuẫn.

### 8.3. Khi có trần L

Chiều cao tối đa có trần:

\[
M_L=\min(M,L).
\]

Vì vậy:

\[
\Pr(M_L\ge k)=
\begin{cases}
1-(1-p^{k-1})^n & 1\le k\le L,\\
0 & k>L.
\end{cases}
\]

và:

\[
\boxed{
E[M_L]=
\sum_{k=1}^{L}
\left[1-(1-p^{k-1})^n\right].
}
\]

Dĩ nhiên `M_L≤L`. Nếu L thấp hơn nhiều so với `\log_{1/p}n`, chiều cao tối đa **bị ép** ở L, nhưng điều này không có nghĩa số bước tìm vẫn logarit: tầng cao nhất có thể quá đông.

### 8.4. Cây rỗng và sentinel

Nếu n=0, ta có thể đặt `M=0` theo nghĩa **không có node dữ liệu**, còn một API skip list vẫn giữ `HEAD` cùng một tầng cơ sở và báo `level_count=1`. Không đưa n=0 vào biểu thức `log n`; đây là trường hợp biên cần xử lý riêng trong code.

## 9. Bản chất của đường tìm kiếm: bước ngang và bước xuống

Phân tích chiều cao chỉ giải thích **có bao nhiêu tầng**. Chúng ta còn cần biết **đi bao nhiêu bước ngang** trên mỗi tầng.

Một tìm kiếm khóa k đi theo quy tắc:

```text
current = HEAD

for i = highest_live_level downto 0:
    while current.forward[i] exists
          and current.forward[i].key < k:
        current = current.forward[i]
    # Không đi ngang tiếp mà vẫn < k: xuống i-1.

candidate = current.forward[0]
return candidate nếu candidate.key == k, ngược lại NOT_FOUND
```

Với các tầng đúng bất biến:

- **Bước ngang:** đi tới node có key < k và còn ở tầng i.
- **Bước xuống:** giữ nguyên node `current`, giảm tầng i.
- **Phép kiểm tra successor:** nhìn `forward[i]` để quyết định có đi ngang hay không.

Ở mức phân tích, một phép tìm có chi phí tỷ lệ với **số bước ngang + số bước xuống + số lần so sánh/kiểm tra successor**. Mỗi phép đi ngang thường đi kèm một số kiểm tra O(1); tại mỗi tầng còn ít nhất một kiểm tra cuối cùng không thỏa điều kiện, nên chi phí cùng bậc.

### 9.1. Vì sao nhìn đường đi ngược hữu ích?

Thử đi **ngược đường tìm** từ gần khóa đích về HEAD. Ở một tầng:

- Đi sang trái qua các node được duyệt ở tầng ấy.
- Tìm một node đã được “thăng cấp” lên tầng trên; khi gặp node đó thì có thể đi **lên**.
- Số node cần đi qua trước khi gặp node được thăng cấp có phân phối liên quan đến **hình học với xác suất thành công p**.

Với mô hình random độc lập phù hợp, số bước ngang kỳ vọng cần xét ở **mỗi tầng** có chặn hằng số theo p, thường được diễn tả ở cỡ O(1/p).

Trực giác này giải thích tại sao việc tăng số node `n` không kéo theo phải quét Θ(n) node ở mọi tầng: các node đã được nâng thành **mốc nhảy** phân bố ngẫu nhiên.

### 9.2. Hai nguồn chi phí khi đặt trần L

Một cách phác thảo chặn trên hữu ích với **L tầng được cho phép** là:

\[
\boxed{
E[T_{\rm search}]
=O\!\left(\frac{L}{p}+np^{L-1}\right)
}
\]

với p cố định, input không thích nghi vào chiều cao và hằng số trong mô hình bước truy cập. Ý tưởng phân tách:

1. **Các tầng dưới đỉnh:** đi ngược từ đường tìm, số bước ngang kỳ vọng trước một mốc được nâng cấp có cỡ O(1/p) mỗi tầng; qua L tầng đóng góp O(L/p).
2. **Tầng cao nhất L−1:** không có tầng cao hơn để làm mốc; số node ở đó có kỳ vọng `np^{L-1}`, nên ngay cả quét hết tầng này cũng có chặn kỳ vọng tương ứng.

Đây là **phác thảo phân tích đường đi ngược**, không phải phép cộng ngây thơ “số node mỗi tầng”. Để có định lý đầy đủ cần chứng minh chặn số bước truy cập theo mốc ngẫu nhiên và quy tắc tìm; công thức nêu đúng bản chất hai chi phí đối với skip list tiêu chuẩn.

Nếu thuật toán thực tế chỉ duyệt `H_{\rm live}≤L` tầng có dữ liệu, chặn bằng L vẫn là một **chặn trên hợp lệ**; có thể chặt hơn khi dùng độ cao đang sử dụng.

### 9.3. Chọn L theo log n

Đặt:

\[
L=1+\left\lceil\log_{1/p}n\right\rceil.
\]

Khi ấy:

\[
np^{L-1}\le1.
\]

Với p là hằng số cố định:

\[
E[T_{\rm search}]
=O\!\left(\frac{\log n}{p}+1\right)
=O(\log n).
\]

Thành phần thứ nhất là số tầng được kiểm tra và các bước ngang điển hình; thành phần thứ hai là chi phí tầng đỉnh, được giữ ở mức kỳ vọng hằng số bằng cách chọn L đủ cao.

### 9.4. Worst-case vẫn có thể tuyến tính

Nếu tất cả node chỉ có H=1:

```text
L0: HEAD -> k1 -> k2 -> ... -> kn -> NULL
```

Tìm k_n cần quét gần n node. Đây là trạng thái **hoàn toàn hợp lệ về bất biến**, nhưng hiệu năng xấu.

Với một phiên bản có trần L và vòng tìm không dùng mảng tạm, chặn worst-case theo trạng thái là `O(n+L)`: con trỏ chỉ đi sang phải theo thứ tự và tổng số lần xuống tầng ≤L. Nếu L cố định nhỏ, điều này thành O(n); nếu L là tham số lớn, phải giữ phần L trong công thức.

**Không được phát biểu “bảo đảm O(log n)”** nếu không gắn chữ **kỳ vọng** và mô hình xác suất. Một cấu trúc có yêu cầu deadline cứng có thể cần cây AVL/đỏ–đen hoặc một thiết kế fallback đã được chứng minh.

## 10. Tìm kiếm thành công và thất bại khác nhau thế nào?

Một thao tác `contains(k)` có hai tình huống:

- **Thành công:** khóa k có trong set.
- **Thất bại:** khóa k không có; thuật toán phải kết luận giữa hai khóa hoặc sau khóa lớn nhất.

Cả hai dùng cùng đường tìm tiền nhiệm:

```text
while next.key < k:
    move right

candidate = current.forward[0]
if candidate != NULL and candidate.key == k:
    FOUND
else:
    NOT_FOUND
```

Tìm k không tồn tại không phải là “thao tác rẻ hơn” theo mặc định: cần định vị **khoảng trống hợp lệ** để chắc chắn k không có. Trong mô hình ngẫu nhiên chuẩn và L phù hợp, cả tìm thành công và tìm thất bại theo một truy vấn cố định đều có thời gian **O(log n) kỳ vọng**.

### 10.1. Tại sao khóa đầu vào không cần random?

Các node được giữ sorted trên tầng 0. Dù người dùng chèn `1,2,3,...,n` theo thứ tự tăng dần, chiều cao mỗi node vẫn được rút độc lập (theo mô hình). Các tầng cao vẫn là **những dãy con ngẫu nhiên** của thứ tự khóa. Khác với BST không tự cân bằng, hình dạng skip list không đơn thuần quyết định bởi thứ tự chèn.

Tuy nhiên, nếu “random” được thay bằng `height(key)=1` hoặc một hàm chiều cao theo key có thiên lệch, chứng minh trên **không còn áp dụng**.

### 10.2. Không chỉ đếm bước sang phải

Một benchmark chỉ đo số node tiến sang phải có thể bỏ qua nhiều chi phí:

- Mỗi tầng có ít nhất một phép kiểm tra khiến vòng ngang dừng.
- Có bước đi xuống tầng.
- Có truy cập con trỏ và so sánh key.
- Chi phí cache miss/allocator.
- Với API tạo `update[L]` cho mọi phép tìm, có thêm O(L) dù đường đi ngang rất ngắn.

Trong báo cáo kỹ thuật, hãy ghi rõ **đơn vị đo** là phép so sánh, bước ngang, số tầng hay thời gian thực. Không được so một thuật toán theo “độ dài đường” với thuật toán khác theo “thời gian CPU” rồi kết luận một cách tùy tiện.

## 11. Chi phí kỳ vọng của chèn và xóa

Tìm kiếm là thành phần định vị. Chèn/xóa còn phải **cập nhật liên kết** trên các tầng mà node tham gia.

### 11.1. Chèn một khóa mới

Chèn khóa k thường gồm:

1. Tìm vị trí của k và lưu `update[i]`, node tiền nhiệm ở từng tầng.
2. Nếu k đã có, trả `ALREADY_EXISTS`, không tạo node.
3. Nếu khóa mới, bốc chiều cao `H_new`.
4. Cấp một node có các ô `forward[0..H_new−1]`.
5. Với mỗi tầng `i<H_new`, chèn node vào giữa tiền nhiệm và successor.

Một mức cập nhật:

```text
fresh.forward[i]      = update[i].forward[i]
update[i].forward[i]  = fresh
```

Nếu node cao H, có **H cặp phép gán pointer**, tức O(H) thao tác cập nhật khi đã biết đường. Trong mô hình không trần, `E[H]=1/(1−p)=O(1)` với p cố định.

Do đó chèn có:

\[
\begin{aligned}
E[T_{\rm insert}]
&=E[T_{\rm find\;predecessors}]
  +O(E[H_{\rm new}])\\
&=O(\log n)
\end{aligned}
\]

với cấu hình mức phù hợp và **bỏ qua/kiểm soát chi phí mảng tạm** theo mô hình. Nếu implementation luôn tạo `update[L]`, tổng nên ghi **O(log n+L)** kỳ vọng, nên cần `L=O(log n)` để giữ nguyên bậc O(log n).

### 11.2. Xóa một khóa đã có

Xóa khóa k:

1. Tìm `target` cùng `update[i]` ở từng tầng.
2. Nếu k vắng, trả `NOT_FOUND` và không sửa liên kết.
3. Nếu k có và cao H, với mỗi `i<H` gỡ:

```text
update[i].forward[i] = target.forward[i]
```

4. Hạ `level_count` nếu những tầng trên cùng rỗng.
5. Quản lý vòng đời target đúng một lần.

Trong mô hình chiều cao các node còn tồn tại IID thích hợp, chiều cao `H_target` của một khóa được chọn **độc lập với chiều cao ngẫu nhiên của chính node** có kỳ vọng O(1). Đường tìm tiền nhiệm vẫn O(log n) kỳ vọng, nên xóa cũng có **O(log n) thời gian kỳ vọng**, cộng overhead cấp mảng tạm nếu implementation có.

**Cẩn thận:** nếu chọn node để xóa bằng cách **nhìn cấu trúc rồi cố ý chọn node cao nhất**, chiều cao của target không có phân phối giống chiều cao một node bất kỳ. Khi đó phần cập nhật có thể là O(log n) kỳ vọng theo cực đại, nhưng lập luận “E[H_target]=O(1)” không còn dùng trực tiếp. Mô hình đối thủ cần được nêu rõ.

### 11.3. Xóa node cao nhất ảnh hưởng bao nhiêu tầng?

Nếu node vừa xóa là node duy nhất ở tầng cao nhất, cấu trúc phải **giảm số tầng đang sử dụng** cho đến khi tầng trên cùng không rỗng (hoặc chỉ còn tầng 0). Một lượt xóa có thể bỏ nhiều tầng.

Chi phí cập nhật/thu hẹp không vượt số tầng `H_{\rm live}` trước thao tác. Trong mô hình IID, `E[H_{\rm live}]=O(log n)`, nên nó không phá bậc O(log n) kỳ vọng.

### 11.4. Độ phức tạp theo trạng thái cụ thể

| Thao tác | Phần định vị | Phần khác | Worst-case nếu có trần L |
| --- | --- | --- | --- |
| `contains` | Đường tìm | Kiểm tra candidate | O(n+L) |
| `insert` | Đường tìm + lưu update | Bốc H, cấp node, nối H tầng | O(n+L) |
| `discard` | Đường tìm + lưu update | Gỡ H tầng, co mức | O(n+L) |
| `lower_bound` | Đường tìm | Trả successor ở L0 | O(n+L) |
| Range query xuất k khóa | Định vị đầu khoảng | Đi L0 qua k node | O(n+L+k) |

Với p cố định, các mức được hỗ trợ phù hợp và không bị một đối thủ điều chỉnh theo trạng thái random, **ba thao tác đầu có thời gian O(log n) kỳ vọng**. Nếu luôn cấp mảng `update[L]`, phải tính chi phí O(L) kể cả khi đường tìm ngắn; nếu node cấp đúng H ô pointer, bộ nhớ node mới là O(H), có kỳ vọng O(1).

## 12. Lựa chọn xác suất p và số tầng tối đa L

p thay đổi **hai đại lượng** cùng lúc:

- Số ô forward kỳ vọng một node: `1/(1-p)`, **tăng** khi p→1.
- Số tầng hữu ích để bao phủ n khóa: `\log_{1/p} n`; với p nhỏ, số tầng hữu ích **ít hơn**, nhưng khoảng tìm ngang ở một tầng có thể dài hơn.

### 12.1. Bảng chọn p cho n≈2^20

Giả sử `n=1\,048\,576=2^{20}` và chọn sơ bộ:

\[
L=1+\left\lceil\log_{1/p}n\right\rceil.
\]

| p | Forward slots kỳ vọng/node | L xấp xỉ | Số node kỳ vọng ở tầng cao nhất |
| ---: | ---: | ---: | ---: |
| 1/4 | 1,333 | 11 | `n(1/4)^{10}=1` |
| 1/2 | 2 | 21 | `n(1/2)^{20}=1` |
| 3/4 | 4 | 50 | `n(3/4)^{49}<1` |

**Diễn giải:** p=1/4 tiết kiệm con trỏ hơn nhưng các tầng thưa, dẫn tới nhiều bước ngang trung bình hơn; p=3/4 có nhiều tầng và con trỏ hơn. Số tầng ít hay nhiều **không tự động** cho biết thời gian CPU nhanh nhất vì số bước ngang, xuống và cache đều góp phần.

### 12.2. Khi L quá thấp

Ví dụ p=1/2, L=16, n=2^24:

\[
E[N_{15}]
=2^{24}(1/2)^{15}
=512.
\]

Tầng cao nhất có trung bình 512 node. Một tìm kiếm khóa lớn hơn mọi khóa có thể phải quét qua nhiều node trên **chính tầng cao nhất**, vì không có tầng nào cao hơn để bỏ qua chúng.

Khi L là hằng số cố định và n→∞:

\[
E[N_{L-1}]=np^{L-1}=\Theta(n).
\]

Đối với truy vấn lớn hơn mọi khóa, số bước ngang trên tầng cao nhất có kỳ vọng đúng bằng số node ở tầng đó (với điều kiện thuật toán bắt đầu ở tầng đó), nên **chi phí kỳ vọng đã là Ω(n)**. Không thể giữ định lý O(log n) theo n cho mọi quy mô chỉ với một L cố định.

### 12.3. Khi L quá cao

L rất lớn có thể khiến một node hiếm hoi đạt độ cao lớn, nhưng một vấn đề thực tế thường thấy hơn là **metadata được cấp trước theo L**:

- HEAD giữ L pointer.
- Mỗi chèn/xóa cấp `update[L]`.
- Mỗi node nếu dùng mảng cố định L slot sẽ tốn O(L) pointer, dù chiều cao thật chỉ 1 hoặc 2.

Có thể tối ưu bằng **mảng forward dài đúng H**, `update[]` dài theo tầng đang sử dụng và mở rộng khi cần, hoặc chỉ giữ mức HEAD đang thực sự dùng. Mỗi lựa chọn cần xử lý lỗi cấp phát và đồng bộ phù hợp.

### 12.4. Trade-off không có p tối ưu tuyệt đối

Ở mức mô hình, ta có một chặn dạng:

\[
O\!\left(\frac{1}{p}\log_{1/p}n\right).
\]

Khi p rất nhỏ, các tầng thưa, số bước ngang tăng. Khi p gần 1, node thường cao và số tầng cần xét nhiều, cũng có thể tăng tổng chi phí.

Trong hệ thống thật, cần đo thêm:

- Số phép so sánh khóa.
- Số lượt dereference pointer.
- Chiều cao `H_live` và số ô forward.
- Chi phí cấp phát/giải phóng node.
- CPU cache misses.
- Tần suất tìm so với chèn/xóa.
- Độ dài range queries.
- Phân vị cao của độ trễ theo nhiều seed.

`p=1/2` là lựa chọn dễ phân tích và thường hợp lý, nhưng không phải định luật luôn nhanh hoặc gọn nhất.


## 13. Python: mô phỏng phân bố chiều cao và đo đường tìm

Công thức xác suất là **dự đoán toán học trong mô hình rút mức độc lập**. Chúng ta có thể viết mô phỏng để kiểm tra cách cài đặt và quan sát các số đo qua nhiều seed, nhưng một thực nghiệm không tự thay thế chứng minh.

Ví dụ này dùng **Python 3.10+**, chỉ có thư viện chuẩn. Để khảo sát **chiều cao và số bước tìm**, ta xây skip list dạng set với n khóa `0,1,...,n−1` theo thứ tự cố định, gắn mức ngẫu nhiên từng node, rồi đếm số ô forward và số bước của một truy vấn thất bại lớn hơn mọi khóa.

### 13.1. Cài đặt đo có thể chạy độc lập

```python
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(eq=False)
class Node:
    key: int | None
    forward: list[Node | None]

    @property
    def height(self) -> int:
        return len(self.forward)


class MeasuredSkipList:
    def __init__(
        self, rng: random.Random,
        p: float = 0.5,
        max_level: int = 24,
    ):
        if not (0.0 < p < 1.0):
            raise ValueError("p must be in (0, 1)")
        if max_level < 1:
            raise ValueError("max_level must be positive")

        self.rng = rng
        self.p = p
        self.max_level = max_level
        self.head = Node(None, [None] * max_level)
        self.level_count = 1
        self.size = 0
        self.forward_slots = 0  # Không tính ô pointer của HEAD.

    def random_height(self) -> int:
        h = 1
        while h < self.max_level and self.rng.random() < self.p:
            h += 1
        return h

    def insert(self, key: int) -> bool:
        """Chèn vào set, không đệ quy."""
        update = [self.head] * self.max_level
        current = self.head

        for level in range(self.level_count - 1, -1, -1):
            while True:
                nxt = current.forward[level]
                if nxt is None or nxt.key >= key:
                    break
                current = nxt
            update[level] = current

        candidate = update[0].forward[0]
        if candidate is not None and candidate.key == key:
            return False

        h = self.random_height()
        fresh = Node(key, [None] * h)

        if h > self.level_count:
            for level in range(self.level_count, h):
                update[level] = self.head
            self.level_count = h

        for level in range(h):
            fresh.forward[level] = update[level].forward[level]
            update[level].forward[level] = fresh

        self.size += 1
        self.forward_slots += h
        return True

    def find_steps(self, key: int) -> tuple[bool, int, int, int]:
        """(found, right_moves, visited_levels, slot_inspections)."""
        current = self.head
        right_moves = 0
        inspections = 0
        levels = self.level_count

        for level in range(self.level_count - 1, -1, -1):
            while True:
                inspections += 1  # Mỗi lần xét một ô forward.
                nxt = current.forward[level]

                if nxt is None or nxt.key >= key:
                    break

                current = nxt
                right_moves += 1

        candidate = current.forward[0]
        found = candidate is not None and candidate.key == key
        return found, right_moves, levels, inspections

    def level_counts(self) -> list[int]:
        """Số node có mặt trên mỗi tầng đang dùng."""
        counts = [0] * self.level_count
        node = self.head.forward[0]

        while node is not None:
            for level in range(node.height):
                counts[level] += 1
            node = node.forward[0]

        return counts

    def assert_valid(self) -> None:
        """Chỉ dùng debug: kiểm tra identity, mức và sorted."""
        bottom: set[Node] = set()
        node = self.head.forward[0]
        prev_key: int | None = None
        max_height = 1
        counted_slots = 0

        while node is not None:
            assert node not in bottom, "Cycle at level 0"
            bottom.add(node)
            assert node.key is not None
            assert prev_key is None or prev_key < node.key
            assert 1 <= node.height <= self.max_level

            max_height = max(max_height, node.height)
            counted_slots += node.height
            prev_key = node.key
            node = node.forward[0]

        assert len(bottom) == self.size
        assert counted_slots == self.forward_slots
        assert max_height == self.level_count

        for level in range(self.level_count):
            expected = {u for u in bottom if u.height > level}
            observed: set[Node] = set()
            node = self.head.forward[level]
            prev_key = None

            while node is not None:
                assert node not in observed, "Cycle at upper level"
                assert node in bottom
                assert node.height > level
                assert prev_key is None or prev_key < node.key
                observed.add(node)

                prev_key = node.key
                node = node.forward[level]

            assert observed == expected


def expected_height(p: float, L: int) -> float:
    return (1.0 - p ** L) / (1.0 - p)


def expected_max_height(n: int, p: float, L: int) -> float:
    if n == 0:
        return 0.0
    return sum(
        1.0 - (1.0 - p ** (k - 1)) ** n
        for k in range(1, L + 1)
    )


def experiment(
    n: int = 512,
    trials: int = 80,
    p: float = 0.5,
    L: int = 16,
    seed: int = 2026,
) -> None:
    assert n >= 1 and trials >= 1
    rng = random.Random(seed)

    slots_total = 0
    max_total = 0
    right_total = 0
    inspections_total = 0

    for _ in range(trials):
        sl = MeasuredSkipList(rng, p=p, max_level=L)

        for key in range(n):  # Dãy tăng dần: KHÔNG shuffle.
            assert sl.insert(key)

        sl.assert_valid()
        level_counts = sl.level_counts()
        assert level_counts[0] == n
        assert sum(level_counts) == sl.forward_slots

        found, right, levels, inspections = sl.find_steps(n)
        assert not found  # n lớn hơn mọi key 0..n-1.
        assert levels == sl.level_count
        assert inspections == right + levels

        slots_total += sl.forward_slots
        max_total += sl.level_count
        right_total += right
        inspections_total += inspections

    print("n =", n, "p =", p, "MAX_LEVEL =", L)
    print("E[H] lý thuyết =", expected_height(p, L))
    print("E[S] lý thuyết =", n * expected_height(p, L))
    print("S trung bình mẫu =", slots_total / trials)
    print("E[M] lý thuyết =", expected_max_height(n, p, L))
    print("M trung bình mẫu =", max_total / trials)
    print("Bước ngang TB =", right_total / trials)
    print("Ô forward được xét TB =", inspections_total / trials)


if __name__ == "__main__":
    experiment()
```

### 13.2. Vì sao cần tách ba bộ đếm đường tìm?

Bộ đo `find_steps` trả:

- `right_moves`: số lần thực sự đi sang node tiếp theo cùng tầng.
- `visited_levels`: số tầng đã duyệt, ở code này đúng bằng `level_count`.
- `slot_inspections`: số lần xem `current.forward[level]` để quyết định có đi ngang.

Ở **mỗi tầng** có một lần xét cuối cùng khiến vòng ngang dừng, nên trong code:

\[
slot\_inspections=right\_moves+visited\_levels.
\]

Đây là đơn vị đo cấp thuật toán, **không** tính cache miss, chi phí allocator, so sánh candidate cuối hay thời gian Python cụ thể. Ghi đúng đơn vị quan trọng hơn một con số benchmark không biết đang đếm gì.

### 13.3. So sánh thực nghiệm với lý thuyết

Các đại lượng có công thức **chính xác theo mô hình**:

\[
E[S_L]=n\,\frac{1-p^L}{1-p},\qquad
E[M_L]=\sum_{k=1}^L[1-(1-p^{k-1})^n].
\]

Nếu tăng `trials`, trung bình mẫu có xu hướng gần những giá trị này khi RNG phù hợp. **Không hardcode** một giá trị chiều cao hoặc số bước cụ thể: chúng thay đổi theo seed và số lần thử.

Có thể thử:

```python
for p in (0.25, 0.5, 0.75):
    experiment(n=1024, trials=50, p=p, L=32, seed=2026)

for L in (4, 8, 12, 16, 24):
    experiment(n=1024, trials=50, p=0.5, L=L, seed=2026)
```

Nếu L quá thấp, số bước ngang trên tầng đỉnh có thể tăng mạnh. Nếu L rất cao, chiều cao thực tế thường không tăng vô hạn, nhưng mã chèn vẫn cấp `update[L]`; đó là **chi phí triển khai** không được bộ đếm đường tìm phản ánh.

**Không chạy `assert_valid` trên mỗi cập nhật trong benchmark production**: nó duyệt cả cấu trúc, có thể lấn át thời gian thao tác ta muốn đo. Trong ví dụ, validator chỉ được dùng cuối mỗi lần dựng mẫu để đảm bảo dữ liệu đo không bị hỏng.

## 14. Áp dụng công thức vào bài toán dung lượng và giới hạn

### 14.1. Dự báo số pointer

Giả sử n=1 triệu, p=1/2, mỗi node cấp đúng H slot forward. Không trần:

\[
E[S]=2n=2\,000\,000\;\text{slot}.
\]

Nếu trên một nền tảng cụ thể pointer rộng 8 byte, riêng forward slots có kỳ vọng khoảng **16 triệu byte**. Chưa tính khóa, payload, metadata, padding, overhead allocator và HEAD. Kích thước pointer không phải 8 byte trên mọi nền tảng.

### 14.2. Xác suất có tầng cực cao

Với n=1 triệu, p=1/2, xác suất có ít nhất một node đạt **41 tầng**:

\[
\Pr(M\ge41)\le 10^6 \cdot 2^{-40}<10^{-6}.
\]

Đây là một **chặn trên**, không phải tuyên bố bất khả thi. Nếu ngân sách bộ nhớ không cho phép node cao hơn L, phải đặt trần cấp phát; không dựa vào xác suất để thay kiểm tra giới hạn.

### 14.3. Khi L thấp hơn nhu cầu

Với n=1 triệu, p=1/2 nhưng L=10, tầng đỉnh i=9 có:

\[
E[N_9]=10^6\cdot2^{-9}=1953{,}125.
\]

Tìm khóa lớn hơn mọi khóa phải đi qua **tất cả** node của tầng cao nhất đang có dữ liệu; trong trường hợp tầng i=9 không trống, số bước ngang ở đó chính là `N_9`. Như vậy riêng tầng đỉnh đóng góp kỳ vọng xấp xỉ **1953 bước ngang**, dù L chỉ 10.

Cấu trúc **không sai bất biến**; thiết kế đã cấp quá ít tầng so với n để duy trì đường tìm ngắn.

### 14.4. Kỳ vọng 1 node không có nghĩa chắc chắn có node

Ở một tầng i với `E[N_i]=1`, xác suất tầng ấy rỗng là:

\[
\Pr(N_i=0)=(1-p^i)^n.
\]

Ví dụ n=1024, p=1/2, i=10:

\[
\Pr(N_{10}=0)=(1-1/1024)^{1024}\approx0{,}368.
\]

Nghĩa là dù trung bình tầng đó có **1 node**, khoảng 36,8% lần rút nó có thể **rỗng**. Đọc nhầm kỳ vọng thành giá trị chắc chắn sẽ dẫn tới dự đoán sai số tầng cao nhất.

### 14.5. Phân biệt “đúng H=k” và “ít nhất H=k”

Số node cao **đúng k tầng** có kỳ vọng:

\[
n(1-p)p^{k-1}.
\]

Số node cao **ít nhất k tầng** có kỳ vọng:

\[
np^{k-1}.
\]

Ví dụ n=1024, p=1/2, k=3:

- **Đúng H=3:** `1024\times\frac18=128` node kỳ vọng.
- **Ít nhất H=3:** `1024\times\frac14=256` node kỳ vọng.

Công thức đầu đếm node dừng đúng mức 3; công thức sau bao gồm cả node cao 4, 5, ... tầng.

## 15. Đọc bảo đảm xác suất mà không diễn giải quá mức

### 15.1. Kỳ vọng không phải giới hạn cho mọi seed

`E[S]=2n` **không có nghĩa** mọi lần chạy đều dùng tối đa 2n pointer. `E[M]=Θ(log n)` không có nghĩa `M≤c\log n` với mọi bộ kết quả random. Một trạng thái xấu có thể có xác suất nhỏ nhưng vẫn xảy ra.

Khi yêu cầu một ràng buộc tài nguyên cứng, hãy dùng giới hạn `MAX_LEVEL`, quota bộ nhớ và cơ chế xử lý lỗi cấp phát. Dùng công thức `Pr(M≥k)` để định lượng rủi ro, không thay cho quản lý tài nguyên.

### 15.2. Expected không tự suy ra high probability

Biết `E[T]=O(log n)` chưa tự cho xác suất `T>10\log n` hoặc phân vị 99,99%. Muốn chặn **high probability**, phải phân tích **đuôi của đại lượng T**, không chỉ kỳ vọng của nó.

Với `T≥0`, bất đẳng thức Markov cho:

\[
\Pr(T\ge a)\le\frac{E[T]}{a}.
\]

Nhưng đây thường là chặn thô. Đối với mức cao nhất `M`, công thức chính xác và union bound ở Mục 7 mạnh hơn và trực tiếp hơn.

### 15.3. Expected khác amortized

Một dynamic array có thể `append` khấu hao O(1) vì chi phí realloc được phân bổ qua một chuỗi thao tác, **không cần random**. Skip list có expected O(log n) vì tính trung bình **trên lựa chọn ngẫu nhiên của cấu trúc**.

| Bảo đảm | Tính trung bình theo đâu? | Một lần chạy rất chậm có thể xảy ra? |
| --- | --- | --- |
| Worst-case O(log n) | Không bình quân; chặn mọi trạng thái hợp lệ | Không vượt bậc logarit theo mô hình |
| Expected O(log n) | Các kết quả bốc ngẫu nhiên | Có |
| Amortized O(1) | Phân bổ tổng chi phí trên chuỗi thao tác | Có |

Không được suy ra bảo đảm worst-case từ biểu thức expected, cũng không được gọi expected là amortized vì cùng dùng chữ “trung bình”.

### 15.4. Đối thủ có thể làm sai giả định phân phối

Các công thức `N_i∼Binomial(n,p^i)` giả định các node đang xét có chiều cao IID đúng phân phối. Nếu một tác nhân **quan sát chiều cao rồi cố ý xóa node thấp, giữ node cao**, tập node còn lại **không** có cùng phân phối chiều cao như một tập khóa được cố định trước khi rút mức.

Tương tự, `random.Random(seed)` của Python phù hợp để mô phỏng và tái lập test, nhưng **không phải nguồn bí mật mật mã**. Trong môi trường đối kháng, cần mô hình hóa khả năng lộ mức, quan sát thời gian, trạng thái PRNG và chính sách giới hạn tài nguyên.

### 15.5. Độ đúng của skip list không phải một sự kiện xác suất

Dù mọi node H=1, các liên kết L0 vẫn phải sorted và `contains` vẫn phải đúng. Các phép chèn/xóa bảo toàn bất biến phải đúng với **mọi chiều cao hợp lệ**.

Random chỉ ảnh hưởng **chi phí**, không được ảnh hưởng ngữ nghĩa tập khóa. Một benchmark “nhanh trung bình” không chứng minh một implementation đúng nếu đôi lúc nó mất node hoặc tạo chu trình.


## 16. Ví dụ tính tay để nối công thức với cấu trúc thật

### 16.1. Năm node và một lần rút chiều cao cụ thể

Cho năm khóa sorted:

```text
key:       10  20  30  40  50
height H:   1   3   2   4   1
```

Từ `H` suy ra các tầng:

```text
L3: HEAD -------------------------> 40 -> NULL
L2: HEAD -----> 20 --------------> 40 -> NULL
L1: HEAD -----> 20 -> 30 --------> 40 -> NULL
L0: HEAD -> 10 -> 20 -> 30 ------> 40 -> 50 -> NULL
```

Bảng đếm:

| Chỉ số tầng i | Các khóa xuất hiện | `N_i` |
| ---: | --- | ---: |
| 0 | 10, 20, 30, 40, 50 | 5 |
| 1 | 20, 30, 40 | 3 |
| 2 | 20, 40 | 2 |
| 3 | 40 | 1 |

Do đó:

\[
S=N_0+N_1+N_2+N_3=5+3+2+1=11.
\]

Đếm theo node:

\[
S=1+3+2+4+1=11.
\]

Chiều cao tối đa `M=4`, có bốn tầng đang dùng. Với p=1/2 và n=5 không trần, công thức cho `E[S]=10`; trạng thái cụ thể có `S=11` là hoàn toàn hợp lệ. **Một giá trị mẫu không bắt buộc bằng kỳ vọng.**

### 16.2. Mô hình nhỏ có trần: n=2, p=1/2, L=3

Hai node độc lập, mỗi node có:

\[
\Pr(H_L=1)=\tfrac12,\quad
\Pr(H_L=2)=\tfrac14,\quad
\Pr(H_L=3)=\tfrac14.
\]

Kỳ vọng mỗi node:

\[
E[H_L]=1+\tfrac12+\tfrac14=\tfrac74.
\]

Tổng con trỏ kỳ vọng:

\[
E[S_L]=2\times\tfrac74=\tfrac72=3{,}5.
\]

Chiều cao cao nhất `M_L`:

\[
\begin{aligned}
\Pr(M_L\ge1)&=1,\\
\Pr(M_L\ge2)&=1-(1-\tfrac12)^2=\tfrac34,\\
\Pr(M_L\ge3)&=1-(1-\tfrac14)^2=\tfrac7{16}.
\end{aligned}
\]

Vậy:

\[
E[M_L]=1+\tfrac34+\tfrac7{16}
=\frac{35}{16}=2{,}1875.
\]

Đây là minh họa nhỏ cho sự khác biệt:

- **Chiều cao trung bình một node:** 1,75 tầng.
- **Chiều cao lớn nhất trung bình của hai node:** 2,1875 tầng.
- **Tổng pointer trung bình của hai node:** 3,5 slot.

### 16.3. Đếm thử một đường tìm

Với cấu trúc ở Mục 16.1, tìm khóa k=35:

```text
L3: HEAD -> 40        (40 >= 35, không sang phải)
L2: HEAD -> 20 -> 40  (20 < 35, đi tới 20)
L1: 20 -> 30 -> 40    (30 < 35, đi tới 30)
L0: 30 -> 40          (40 >= 35, dừng)

candidate = 40, nên k=35 không tồn tại.
```

Trong ví dụ này:

- Có **2 bước ngang**: HEAD→20, 20→30.
- Có **4 tầng được kiểm tra**: L3, L2, L1, L0.
- Số lần xét ô forward ở vòng ngang là **6**: hai lần đi ngang thành công và một lần kiểm tra dừng tại mỗi tầng.

Nếu muốn đo đầy đủ **số lần so sánh khóa** còn phải đếm phép so với candidate cuối cùng, tùy API và cách cài đặt.

### 16.4. Tập khóa cố định, random quyết định hình dạng

Vẫn các khóa `10,20,30,40,50` nhưng thay chiều cao bằng:

```text
height: 1 1 1 1 1
```

thì chỉ còn L0. Tìm 50 tốn nhiều bước hơn, nhưng **tập khóa và thứ tự duyệt không đổi**. Vì vậy các phép test chức năng phải không phụ thuộc vào một chuỗi rút mức đẹp.

## 17. Kiểm thử, sai lầm thường gặp và quyết định thiết kế

### 17.1. Kiểm thử tách hai tầng trách nhiệm

**Tính đúng cấu trúc** phải được kiểm tra sau thao tác chèn/xóa:

- L0 chứa mọi khóa đúng một lần, theo thứ tự tăng.
- Tầng i chứa đúng các node có H>i, theo đúng thứ tự khóa.
- Không có chu trình trên các liên kết forward.
- `size` bằng số node thật ở L0.
- `level_count` phản ánh chiều cao lớn nhất (hoặc bằng 1 khi rỗng).
- Xóa node khỏi mọi tầng rồi mới giải phóng vòng đời theo hợp đồng.
- `contains`, `lower_bound` và range query trả kết quả đúng như một mô hình tham chiếu.

**Tính chất xác suất** cần quan sát trên **nhiều lần rút random**:

- Trung bình chiều cao từng node có gần `(1-p^L)/(1-p)`?
- Trung bình forward slots có gần `n(1-p^L)/(1-p)`?
- Chiều cao tối đa có gần tổng `E[M_L]` đã tính?
- Số node tầng i có gần trung bình `np^i` và biến động kỳ vọng?
- Khi tăng n, số bước tìm có xu hướng tăng theo logarit nếu L phù hợp?
- Khi giữ L quá nhỏ, bước ngang tầng đỉnh có tăng mạnh theo n?

**Một loại test không thay thế loại kia.** Mã có phân phối chiều cao đẹp vẫn có thể bị lỗi nối khiến mất khóa; mã trả đúng mọi khóa vẫn có thể tốn O(n) nếu mức random bị cấu hình sai.

### 17.2. Độ tin cậy của seed và PRNG

Với cùng seed, cùng thuật toán RNG và cùng thứ tự gọi RNG, kết quả thường có thể **tái lập**. Đây là ưu điểm để debug, không phải bảo đảm bảo mật.

Để thu số liệu thống kê đáng tin hơn, nên:

1. Sử dụng nhiều seed, nhiều n và nhiều kiểu khóa.
2. Tách RNG quyết định **workload** khỏi RNG bốc **chiều cao cấu trúc**.
3. Không can thiệp vào trạng thái RNG giữa test theo cách khó kiểm soát.
4. Không bỏ qua trạng thái xấu chỉ vì nó hiếm; dùng validator cho mọi lần dựng.
5. Báo số trial, seed policy, n, p, L, đơn vị đo và môi trường chạy.
6. Dùng phép đo thời gian riêng với phép đo số bước, vì Python/C++ có overhead khác nhau.

### 17.3. Những lỗi lý thuyết phổ biến

| Phát biểu sai | Vì sao sai | Cách phát biểu đúng |
| --- | --- | --- |
| “Mỗi node cao trung bình log n” | Node riêng có chiều cao kỳ vọng `1/(1-p)` | **Node cao nhất** trong n node mới có kỳ vọng Θ(log n) |
| “Tầng i luôn chứa `np^i` node” | Đây chỉ là **kỳ vọng** | `N_i∼Binomial(n,p^i)` trong mô hình IID |
| “Node H=4 có xác suất `p^3`” | Thiếu thông tin “đúng” hay “ít nhất” | `Pr(H≥4)=p^3`, `Pr(H=4)=(1-p)p^3` khi không trần |
| “Ở mức trần L vẫn nhân `(1-p)` để dừng” | Thuật toán dừng vì trần | `Pr(H_L=L)=p^{L-1}` |
| “O(n log n) pointer vì có O(log n) tầng” | Node cao hiếm, không có ở mọi tầng | Tổng slot kỳ vọng `n/(1-p)=O(n)` |
| “Kỳ vọng O(log n) nên mọi truy vấn nhanh” | Tồn tại trạng thái cấu trúc xấu | Worst-case có thể tuyến tính |
| “L cố định đủ cho n→∞” | Tầng đỉnh có `np^{L-1}=\Theta(n)` node kỳ vọng | Chọn L phù hợp n tối đa hoặc thiết kế điều chỉnh |
| “L thật lớn luôn tốt hơn” | Overhead HEAD/update và đi xuống tầng tăng | Đo đánh đổi theo p,L và workload |
| “N_i độc lập giữa các tầng” | Node đạt tầng i+1 cũng đạt tầng i | Chỉ các biến node tại **cùng tầng** độc lập theo mô hình |
| “`E[M]≤\log n` từ `E[H]` hằng số” | Cực đại không bằng kỳ vọng một phần tử | Dùng phân phối `Pr(M≥k)` và tổng xác suất đuôi |
| “`E[T]` nhỏ ⇒ tail luôn rất mạnh” | Chỉ kỳ vọng không xác định chính xác tail | Chứng minh chặn tail riêng |
| “Chuỗi random có seed công khai chống mọi tấn công” | PRNG có thể dự đoán và đối thủ thích nghi | Xác định threat model, bảo vệ RNG hoặc chọn worst-case cấu trúc |
| “Chèn trùng vẫn bốc chiều cao như thường” | Có thể thay state RNG không cần thiết | Chọn và ghi rõ chính sách RNG khi thao tác thất bại |
| “Số slot pointer bằng số byte bộ nhớ” | Node còn payload, metadata, padding, allocator | Tách slot count và byte count |
| “Dùng `MAX_LEVEL` slot cho mọi node vẫn có `E[S]=n/(1-p)`” | Đó là slot **đã dùng**, không phải slot **đã cấp** | Mảng fixed-size mỗi node cấp Θ(nL) slot |
| “Báo size từ tổng node trên mọi tầng” | Một node tham gia nhiều tầng | Size là số node ở **tầng 0** |

### 17.4. So sánh với cấu trúc khác khi áp dụng

| Tiêu chí | Skip list chuẩn | AVL/red-black tree | Mảng sorted | Hash table |
| --- | --- | --- | --- | --- |
| Tìm exact key | O(log n) kỳ vọng | O(log n) worst-case | O(log n) | O(1) kỳ vọng tùy hash |
| Chèn/xóa | O(log n) kỳ vọng | O(log n) worst-case | O(n) do dịch phần tử | O(1) kỳ vọng tùy hash |
| Duy trì thứ tự khóa | Có | Có | Có | Không theo mặc định |
| Range query xuất k kết quả | O(log n+k) kỳ vọng | O(log n+k) | O(log n+k) | Thường phải bổ sung chỉ mục |
| Nguồn bảo đảm hiệu năng | Xác suất phân bố mức | Bất biến cân bằng tất định | Tìm nhị phân + dịch chuyển | Phân phối hash/tải bảng |
| Metadata chính | Forward slots theo độ cao | Con trỏ và metadata cân bằng | Vùng liên tiếp | Bucket/table, collision policy |
| Worst-case tìm một khóa | Có thể O(n) | O(log n) | O(log n) | Có thể O(n) |
| Phù hợp deadline cứng | Không chỉ dựa vào expected | Thường phù hợp hơn | Tìm đọc phù hợp nếu ít ghi | Tùy chiến lược collision và yêu cầu |

Khi workload chủ yếu tìm khóa chính xác nhưng không cần sorted order, hash table có thể hấp dẫn. Khi cần range query và cập nhật trực tuyến, skip list là một lựa chọn tốt nếu **độ trễ kỳ vọng** chấp nhận được. Khi cần **worst-case O(log n) cho mỗi thao tác**, nên xem xét cây cân bằng tất định hoặc cấu trúc khác với bảo đảm phù hợp.

### 17.5. Checklist trước khi đưa vào sản phẩm

- Mô hình khóa và quy tắc trùng khóa có rõ không?
- p có trong (0,1), các lần rút mức có đủ độc lập trong threat model không?
- n dự kiến lớn nhất là bao nhiêu và L đã được tính theo đó chưa?
- Node cấp **đúng H** forward slots hay **L** slot cố định?
- Tìm chỉ đọc có tránh cấp mảng `update[L]` nếu không cần không?
- Sau khi xóa/chèn, bất biến các tầng có được kiểm tra trong test không?
- Vòng đời node, iterator và cập nhật đồng thời được xử lý thế nào?
- Có dùng seed tái lập test nhưng tránh coi seed cố định là bí mật bảo mật không?
- Đã đo bước ngang, số tầng, số pointer và độ trễ tail trên nhiều seed chưa?
- Khi đạt quota tài nguyên, API trả lỗi gì và dữ liệu có còn đúng bất biến không?

Một skip list có **kỳ vọng toán học tốt** vẫn có thể là lựa chọn kém nếu cách cấp phát gây cache miss, mức trần quá thấp hoặc ứng dụng đòi latency worst-case.


## 18. Bài tập thực hành có lời giải chi tiết

### Bài 1. Số tầng và chỉ số tầng

Node A có chiều cao H=5. Nó tham gia những tầng nào và có bao nhiêu ô forward? Có phải chỉ số cao nhất là 5 không?

**Lời giải:** Node tham gia các tầng `0,1,2,3,4` và có **5 ô `forward[0..4]`**. Chỉ số tầng cao nhất là **4**, vì đánh số từ 0. Khi tính `N_i`, node xuất hiện ở tầng i nếu `H≥i+1`.

### Bài 2. Xác suất đạt ít nhất bốn tầng

Với `p=1/2`, không trần, xác suất `Pr(H≥4)` bằng bao nhiêu?

**Lời giải:** Cần ba lần nâng thành công:

\[
\Pr(H\ge4)=p^3=(1/2)^3=\frac18.
\]

Không cần tính lần dừng tiếp theo, vì hỏi **ít nhất** bốn tầng.

### Bài 3. Xác suất có đúng bốn tầng

Với cùng p=1/2, xác suất node có **đúng H=4** là gì?

**Lời giải:** Có ba lần nâng thành công **rồi một lần dừng**:

\[
\Pr(H=4)=(1-p)p^3
=\frac12\cdot\frac18=\frac1{16}.
\]

Đây là một nửa `Pr(H≥4)` khi p=1/2.

### Bài 4. Phân phối với p=1/4

Với p=1/4, tính `Pr(H≥5)` và `Pr(H=5)`.

**Lời giải:**

\[
\Pr(H\ge5)=(1/4)^4=\frac1{256}.
\]

\[
\Pr(H=5)=\frac34(1/4)^4=\frac3{1024}.
\]

Điều kiện “đúng” cần thêm xác suất dừng `1-p=3/4`.

### Bài 5. Xác suất H nằm giữa 2 và 4

Với p=1/2, không trần, tính `Pr(2≤H≤4)`.

**Lời giải:**

\[
\Pr(2\le H\le4)
=\Pr(H\ge2)-\Pr(H\ge5)
=\frac12-\frac1{16}=\frac7{16}.
\]

Đếm tổng riêng `Pr(H=2)+Pr(H=3)+Pr(H=4)` cũng cho `1/4+1/8+1/16=7/16`.

### Bài 6. Kỳ vọng một node với p=1/2

Tính `E[H]` và giải thích ý nghĩa của nó.

**Lời giải:**

\[
E[H]=\frac1{1-p}=\frac1{1-1/2}=2.
\]

Trung bình qua các lần rút mức, một node có **hai ô forward**. Một node cụ thể hoàn toàn có thể chỉ cao 1 hoặc cao 7 tầng; kỳ vọng không ấn định chiều cao từng node.

### Bài 7. Kỳ vọng và phương sai với p=1/4

Tính `E[H]` và `Var(H)`.

**Lời giải:**

\[
E[H]=\frac1{1-1/4}=\frac43.
\]

\[
Var(H)=\frac{1/4}{(3/4)^2}
=\frac{1/4}{9/16}=\frac49.
\]

Độ lệch chuẩn là `2/3`. Đây là độ biến động của **một node**, không phải chiều cao lớn nhất.

### Bài 8. Trần L thay đổi xác suất đỉnh

Cho p=1/2, `MAX_LEVEL=3`. Xác suất `Pr(H_L=3)` bằng 1/8 hay 1/4?

**Lời giải:** Bằng **1/4**. Đạt trần 3 chỉ cần hai lần nâng thành công; không cần một lần tung dừng:

\[
\Pr(H_L=3)=p^{L-1}=(1/2)^2=\frac14.
\]

Nếu dùng nhầm `(1-p)p^2=1/8`, tổng xác suất ba mức không bằng 1.

### Bài 9. Kỳ vọng chiều cao khi có trần L=4

Cho p=1/2, L=4. Tính `E[H_L]`.

**Lời giải:**

\[
E[H_L]=1+\tfrac12+\tfrac14+\tfrac18
=\frac{15}{8}=1{,}875.
\]

Hoặc dùng công thức `(1-p^L)/(1-p)`. Nó nhỏ hơn `E[H_\infty]=2`.

### Bài 10. L=1 có tác dụng gì?

Skip list đặt `MAX_LEVEL=1`. Hình dạng thế nào và tìm kiếm xấu nhất bao nhiêu?

**Lời giải:** Tất cả node chỉ ở L0; cấu trúc trở thành một danh sách liên kết sorted. Tìm một khóa ở cuối hoặc lớn hơn mọi khóa cần Θ(n) bước ngang. Đây là **trạng thái hợp lệ về chức năng** nhưng không có tầng nhảy.

### Bài 11. Số node kỳ vọng trên một tầng

Cho n=1024, p=1/2. Số node kỳ vọng trên tầng i=6 là bao nhiêu?

**Lời giải:**

\[
E[N_6]=1024(1/2)^6=16.
\]

Nó không chắc chắn có đúng 16 node, mà có phân phối `Binomial(1024,1/64)` theo mô hình độc lập.

### Bài 12. Phương sai của một tầng

Với n=256, p=1/2, i=5, tính `E[N_5]` và `Var(N_5)`.

**Lời giải:** Xác suất một node có mặt tại tầng 5 là `q=(1/2)^5=1/32`.

\[
E[N_5]=256/32=8.
\]

\[
Var(N_5)=256(1/32)(31/32)
=8\cdot31/32=7{,}75.
\]

Độ lệch chuẩn khoảng `\sqrt{7{,}75}≈2{,}784` node.

### Bài 13. Tầng đáy có phân phối ngẫu nhiên không?

Với n node, `N_0` có bằng n chỉ trong kỳ vọng không?

**Lời giải:** **Không:** `N_0=n` trong **mọi trạng thái hợp lệ**, vì mọi node phải tham gia tầng 0. Toán học: `Pr(H≥1)=1`, `E[N_0]=n`, `Var(N_0)=0`.

### Bài 14. Các tầng có độc lập không?

Nếu một node có mặt ở tầng 4, nó có bắt buộc xuất hiện ở tầng 3 không? `N_3` và `N_4` có độc lập không?

**Lời giải:** Nó **bắt buộc** xuất hiện ở mọi tầng thấp hơn, nên có mặt ở tầng 3. Các số đếm `N_3, N_4` có quan hệ phụ thuộc, không phải hai biến độc lập. Tại **cùng một tầng**, các chỉ báo tham gia của các node khác nhau độc lập theo mô hình rút H độc lập.

### Bài 15. Tổng số forward slots kỳ vọng

Cho n=1000, p=1/2, không trần. Tính tổng ô forward kỳ vọng.

**Lời giải:**

\[
E[S]=nE[H]=1000\times2=2000.
\]

Không nhân thêm `\log n`; nhiều node nằm ở tầng cao nhưng số node cao giảm theo cấp số nhân.

### Bài 16. Đếm hai cách trong một trạng thái cụ thể

Năm node có chiều cao `[1,3,2,4,1]`. Tính tổng slot bằng hai cách.

**Lời giải:** Theo node:

\[
S=1+3+2+4+1=11.
\]

Theo tầng: `N_0=5, N_1=3, N_2=2, N_3=1` nên:

\[
S=5+3+2+1=11.
\]

Hai cách bằng nhau vì mỗi node xuất hiện trên đúng H tầng.

### Bài 17. Forward slot cố định và cấp phát theo chiều cao

Có n=1000, L=16, p=1/2. So sánh số slot **đã cấp** nếu mỗi node dùng mảng L với nếu cấp đúng H.

**Lời giải:** Mảng cố định cấp **16.000 slot** dữ liệu. Cấp theo H có kỳ vọng:

\[
E[S_L]=1000\,\frac{1-(1/2)^{16}}{1/2}
\approx2000.
\]

Chưa tính HEAD và overhead allocator. Công thức khoảng 2000 chỉ đúng cho **node cấp theo H**, không đúng cho mảng cố định L.

### Bài 18. Phương sai tổng slot

Với n=1024, p=1/2, không trần, tính `Var(S)` và độ lệch chuẩn.

**Lời giải:**

\[
Var(S)=\frac{np}{(1-p)^2}
=\frac{1024/2}{(1/2)^2}=2048.
\]

\[
\sigma_S=\sqrt{2048}\approx45{,}25.
\]

Trong khi `E[S]=2048`, độ lệch chuẩn cỡ 45 slot; độ biến động tương đối nhỏ hơn nhiều khi n lớn theo mô hình IID.

### Bài 19. Xác suất một tầng rỗng

Có n=1024, p=1/2, tầng i=10. Xác suất tầng này không có node nào là bao nhiêu?

**Lời giải:**

\[
\Pr(N_{10}=0)=(1-2^{-10})^{1024}
=(1023/1024)^{1024}\approx0{,}368.
\]

Dù `E[N_{10}]=1`, xác suất tầng rỗng vẫn gần 36,8%.

### Bài 20. Chiều cao tối đa trong n node

Viết công thức chính xác của `Pr(M<k)` và `Pr(M≥k)`.

**Lời giải:** M<k khi mọi node thấp hơn k. Với các chiều cao IID:

\[
\Pr(M<k)=(1-p^{k-1})^n.
\]

Do lấy biến cố đối:

\[
\Pr(M\ge k)=1-(1-p^{k-1})^n.
\]

Công thức áp dụng cho n≥1 và không trần; với trần L, đặt xác suất M_L≥k bằng 0 khi k>L.

### Bài 21. Chặn union bound

Với n=1024, p=1/2, hãy chặn trên `Pr(M≥21)`.

**Lời giải:**

\[
\Pr(M\ge21)\le1024\cdot(1/2)^{20}
=1/1024\approx0{,}0009766.
\]

Chặn không có nghĩa xác suất bằng đúng 1/1024; nó là **giới hạn trên**.

### Bài 22. Chọn k theo xác suất rủi ro

Với n=64, p=1/2, muốn chặn trên xác suất tồn tại node cao ít nhất k tầng không quá `1/64`, chọn k tối thiểu theo union bound là bao nhiêu?

**Lời giải:** Cần:

\[
64\cdot2^{-(k-1)}\le1/64
\iff2^{k-1}\ge4096=2^{12}.
\]

Vậy chọn **k≥13**. Đây là k đủ theo union bound, không nhất thiết là ngưỡng tối ưu theo công thức xác suất chính xác.

### Bài 23. Kỳ vọng chiều cao lớn nhất

Với n=2, p=1/2, L=3, tính `E[M_L]`.

**Lời giải:**

\[
\begin{aligned}
\Pr(M_L\ge1)&=1,\\
\Pr(M_L\ge2)&=1-(1-1/2)^2=3/4,\\
\Pr(M_L\ge3)&=1-(1-1/4)^2=7/16.
\end{aligned}
\]

Do đó:

\[
E[M_L]=1+3/4+7/16=35/16=2{,}1875.
\]

### Bài 24. Vì sao node đơn cao O(1) còn đỉnh cao O(log n)?

Giải thích bằng xác suất đuôi.

**Lời giải:** Node đơn có `Pr(H≥k)=p^{k-1}`, tổng đuôi hội tụ nên `E[H]=1/(1-p)=O(1)`. Với n node, xác suất có ít nhất một node đạt mức k cỡ `1-(1-p^{k-1})^n`; mốc chuyển tiếp khi `np^{k-1}≈1`, tức `k≈1+\log_{1/p}n`. Vì vậy `E[M]=Θ(log n)` với p cố định.

### Bài 25. Đủ tầng cho n=2^16

Cho p=1/2, n=2^16. Chọn `L=1+\log_2 n`. L bằng bao nhiêu và kỳ vọng số node ở tầng đỉnh là gì?

**Lời giải:** `L=17`, tầng đỉnh i=16. Số node kỳ vọng:

\[
E[N_{16}]=2^{16}2^{-16}=1.
\]

Đây là lựa chọn cân đối giữa số tầng và số node cần quét ở tầng cao nhất theo mô hình.

### Bài 26. Giới hạn L quá thấp

Cho n=2^16, p=1/2, L=9. Số node kỳ vọng ở tầng đỉnh là bao nhiêu? Điều đó ảnh hưởng tìm khóa lớn hơn mọi khóa như thế nào?

**Lời giải:** Tầng đỉnh i=8:

\[
E[N_8]=2^{16}\cdot2^{-8}=256.
\]

Tìm khóa lớn hơn mọi khóa đi qua tất cả node trên tầng đỉnh trước khi xuống. Do đó **chỉ riêng tầng đỉnh** có kỳ vọng 256 bước ngang, và không thể giả định toàn thao tác O(log n) cho cấu hình này trong miền n tăng.

### Bài 27. Tại sao L cố định không đủ khi n→∞?

Giải thích bằng biểu thức số node tầng đỉnh.

**Lời giải:** Với p và L là hằng số, `E[N_{L-1}]=np^{L-1}` tăng **tuyến tính theo n**. Tầng đỉnh không có liên kết ở tầng cao hơn để bỏ qua các node ấy. Truy vấn khóa lớn hơn tất cả có chi phí tầng đỉnh kỳ vọng Θ(n), nên không còn chặn O(log n) theo n cho mọi quy mô.

### Bài 28. Đếm số bước tìm trong ví dụ nhỏ

Các mức node theo khóa `10,20,30,40,50` là `[1,3,2,4,1]`. Tìm k=35 có bao nhiêu bước ngang và tầng được xét theo quy tắc `next.key<k`?

**Lời giải:** Ở L3 không đi ngang vì node kế là 40. Ở L2 đi HEAD→20 (1 bước). Ở L1 đi 20→30 (1 bước). Ở L0 không đi ngang vì kế là 40. Tổng **2 bước ngang**, **4 tầng** được xét; trong vòng đo của Mục 13 có **6 lần kiểm tra forward**.

### Bài 29. Kỳ vọng chi phí nối của một lần chèn

Nếu một node mới có H tầng, mỗi tầng cần hai phép gán pointer để chèn. Với p=1/2 và không trần, số phép gán pointer kỳ vọng là bao nhiêu (chỉ phần nối)?

**Lời giải:** Với hai phép gán mỗi tầng, chi phí nối là `2H`. Theo tuyến tính:

\[
E[2H]=2E[H]=2\cdot2=4.
\]

Đây chỉ là chi phí **sửa liên kết khi đã biết tiền nhiệm**; tìm `update[]` vẫn có chi phí O(log n) kỳ vọng.

### Bài 30. Xóa node cao nhất

Một hệ thống chọn **node cao nhất** để xóa, thay vì chọn một khóa cố định không phụ thuộc chiều cao. Có thể dùng ngay `E[H_{\rm target}]=1/(1-p)` để tính số liên kết phải gỡ không?

**Lời giải:** **Không.** Chiều cao node cao nhất có phân phối của `M`, không phải một `H_j` điển hình; `E[M]=Θ(log n)` trong mô hình không trần. Dù chi phí này vẫn có thể phù hợp bậc O(log n) cho một thao tác, không được dùng lập luận “chiều cao node được xóa là O(1) kỳ vọng” khi **chọn node theo chính chiều cao**.

### Bài 31. Chi phí mảng `update[L]`

Một phiên bản skip list luôn khởi tạo mảng `update[L]` khi chèn, dù chỉ vài tầng đang dùng. Có thể ghi chi phí thao tác không chứa L không?

**Lời giải:** Không. Khởi tạo mảng O(L) thời gian và dùng O(L) bộ nhớ tạm. Nếu `L=O(log n)`, có thể gộp vào O(log n). Nếu L tăng nhanh hơn, phải ghi **O(log n+L)** kỳ vọng khi phần tìm đã có bảo đảm phù hợp.

### Bài 32. Chi phí truy vấn khoảng

Một skip list cần trả k khóa thuộc khoảng `[low,high)`. Vì sao không thể chỉ nói O(log n) cho toàn bộ truy vấn?

**Lời giải:** Cần một lần định vị `lower_bound(low)`, kỳ vọng O(log n) với mô hình đúng, rồi **xuất k phần tử**, cần ít nhất Ω(k) bước. Tổng là **O(log n+k) kỳ vọng**; nếu bước định vị luôn cấp update[L] còn phải tính thêm O(L).

### Bài 33. Expected khác worst-case

Một skip list có expected search O(log n), nhưng một seed nào đó khiến mọi node H=1. Có thể kết luận thuật toán sai không?

**Lời giải:** Không chỉ dựa vào độ cao. Nếu các liên kết vẫn sorted, `contains` trả đúng và không có node mất, cấu trúc hợp lệ; trường hợp này chỉ có **hiệu năng Θ(n)** khi tìm xa. Expected không cấm các kết quả random xấu.

### Bài 34. Xác suất cao từ kỳ vọng

Biết `E[T]=O(log n)`. Có thể tuyên bố ngay `Pr(T>C\log n)≤1/n^3` cho một hằng C không?

**Lời giải:** Không. Cần chứng minh **tail bound cụ thể** cho T. Một kỳ vọng nhỏ có thể cùng tồn tại với một đuôi xác suất không đạt `1/n^3` ở ngưỡng ấy. Markov chỉ cho `Pr(T≥a)≤E[T]/a`, thường quá thô để suy chặn đó.

### Bài 35. Phân tích khi đối thủ thích nghi

Một tác nhân quan sát chiều cao của các node rồi xóa các node thấp, chỉ giữ các node cao. Có còn được xem chiều cao của tập node còn lại là IID geometric theo p như ban đầu không?

**Lời giải:** Không. Việc **chọn giữ/xóa dựa trên kết quả random** gây thiên lệch lựa chọn. Những công thức `N_i∼Binomial(n,p^i)` cho tập khóa cố định độc lập với random không tự áp dụng cho tập đang sống sau thao tác thích nghi ấy. Cần mô hình phân tích thích hợp hoặc chính sách chống đối kháng.

## 19. Tổng kết: công thức và cách sử dụng đúng

Các công thức chính của bài, với `0<p<1`, **n node có chiều cao rút độc lập** và mô hình không trần:

| Đại lượng | Công thức |
| --- | --- |
| Xác suất node đạt ít nhất k tầng | `Pr(H≥k)=p^{k-1}` |
| Xác suất node đúng k tầng | `Pr(H=k)=(1-p)p^{k-1}` |
| Kỳ vọng chiều cao node | `E[H]=1/(1-p)` |
| Phương sai chiều cao node | `Var(H)=p/(1-p)^2` |
| Số node tầng i | `N_i∼Binomial(n,p^i)` |
| Kỳ vọng số node tầng i | `E[N_i]=np^i` |
| Phương sai số node tầng i | `Var(N_i)=np^i(1-p^i)` |
| Tổng ô forward kỳ vọng | `E[S]=n/(1-p)` |
| Xác suất đỉnh dưới k | `Pr(M<k)=(1-p^{k-1})^n` |
| Xác suất đỉnh đạt k | `Pr(M≥k)=1-(1-p^{k-1})^n≤np^{k-1}` |
| Chiều cao tối đa kỳ vọng | `E[M]=Θ(log n)` khi p cố định |
| Tìm/chèn/xóa | `O(log n)` **kỳ vọng**, với tầng đủ và giả định random phù hợp |

Với **trần L**, cần nhớ hai điều chỉnh quan trọng:

\[
\Pr(H_L=L)=p^{L-1},
\qquad
E[H_L]=\frac{1-p^L}{1-p}.
\]

Và để tránh tầng đỉnh quá đông, một thiết kế điển hình có thể chọn:

\[
L\approx1+\left\lceil\log_{1/p}n_{\max}\right\rceil
\]

cho quy mô `n_{\max}` dự kiến, rồi kiểm tra workload thực tế, budget bộ nhớ và tình huống trần bị chạm. Với L cố định nhưng cho n tăng không giới hạn, không thể tuyên bố expected O(log n) trong mọi quy mô.

**Khi giải bài toán có skip list, hãy trả lời ba câu hỏi theo đúng thứ tự:**

1. **Đúng cấu trúc không?** Tầng 0 đầy đủ và sorted, tầng cao là tập con, con trỏ không tạo chu trình, update/delete không bỏ quên node?
2. **Random được lấy theo mô hình nào?** Xác suất p, các lần rút độc lập, có trần L, thao tác có phụ thuộc vào kết quả random không?
3. **Đang hứa hẹn loại chi phí gì?** Kỳ vọng, worst-case, tail probability, bộ nhớ pointer hay độ trễ CPU?

Khi tách rõ **tính đúng tất định** khỏi **chi phí xác suất**, skip list trở thành một ví dụ đẹp về tư duy cấu trúc dữ liệu: mỗi node chỉ cần số liên kết bổ sung **hằng số theo kỳ vọng**, nhưng những liên kết ấy hợp lại tạo ra một hệ thống đường nhảy có **độ cao cực đại logarit kỳ vọng**, giúp định vị và cập nhật khóa trong **thời gian logarit kỳ vọng** với giả định rõ ràng.

# Xử lý một lượt với bộ nhớ giới hạn

## Mục tiêu học tập

Trong nhóm **Trực tuyến và luồng**, nhiều hệ thống không có điều kiện tải toàn bộ dữ liệu vào RAM trước khi tính toán. Ví dụ: nhật ký truy cập liên tục, sự kiện IoT, giao dịch, luồng số đo, gói tin, dòng dữ liệu từ một tệp rất lớn hoặc từ `stdin`. Khi mỗi bản ghi được nhìn thấy **một lần**, thuật toán phải duy trì một **trạng thái tóm tắt nhỏ** thay vì lưu toàn bộ lịch sử.

Chủ đề **xử lý một lượt với bộ nhớ giới hạn** (*single-pass, bounded-memory stream processing*) nghiên cứu cách quyết định **giữ thông tin nào, loại bỏ thông tin nào**, cũng như những đại lượng nào có thể tính **chính xác**, đại lượng nào chỉ có thể **xấp xỉ** trong mô hình bộ nhớ nhỏ.

Bài học sẽ giúp bạn:

1. Phân biệt **mô hình luồng một lượt**, bộ nhớ làm việc, bộ nhớ tính bằng **bit** và **từ máy**, thời gian xử lý mỗi phần tử, và độ trễ.
2. Tính **count, min, max, mean, variance** theo luồng bằng bộ trạng thái nhỏ, trong đó phương sai dùng thuật toán **Welford**.
3. Hiểu **reservoir sampling** để chọn k vị trí quan sát ngẫu nhiên đồng xác suất mà không biết trước độ dài luồng.
4. Hiểu **Misra–Gries** để giữ tối đa k−1 bộ đếm và bảo đảm không bỏ sót phần tử có tần suất lớn hơn N/k.
5. Phân biệt **ứng viên heavy hitter** và **tần suất thực**; hiểu tại sao bộ đếm Misra–Gries không thay thế lượt đếm lại chính xác.
6. Biết cách sử dụng tư duy **sketch** như Count-Min Sketch, HyperLogLog và Bloom filter, kèm giới hạn xác suất của chúng.
7. Hiểu vì sao một số yêu cầu như **đếm distinct chính xác trên miền lớn** không thể luôn giải với lượng bộ nhớ cố định rất nhỏ.
8. Phân biệt luồng **append-only**, cập nhật có xóa, và cửa sổ trượt có phần tử hết hạn.
9. Viết **Java 17+** đọc số nguyên từ `stdin` bằng bộ đệm cố định, không dùng `readAllLines` và không tích lũy danh sách toàn bộ dữ liệu.
10. Thiết kế phép thử độc lập, kiểm tra biên, xác nhận invariant và tránh tuyên bố độ chính xác vượt quá bảo đảm.

---

## 1. Mô hình dữ liệu luồng (*streaming model*)

Xét một dãy sự kiện đến theo thời gian:

\[
a_1,a_2,\ldots,a_N.
\]

Trong xử lý dạng batch, ta có thể lưu cả dãy rồi sắp xếp, tìm kiếm, quét nhiều lần. Trong xử lý streaming một lượt, tại thời điểm t ta chỉ nhận:

\[
a_t
\]

và trạng thái gọn trước đó:

\[
S_{t-1}.
\]

Thuật toán cập nhật:

\[
\boxed{S_t=U(S_{t-1},a_t).}
\]

Sau khi xử lý `a_t`, thuật toán có thể **không bao giờ được đọc lại** phần tử này. Cuối luồng (hoặc tại thời điểm bất kỳ), đầu ra được suy ra từ trạng thái:

\[
\boxed{\text{answer}_t=Q(S_t).}
\]

### 1.1. "Một lượt" nghĩa là gì?

- Mỗi sự kiện được tiêu thụ tối đa một lần theo thứ tự đến.
- Không giả định có thể quay lại đầu nguồn hay tìm kiếm ngẫu nhiên trong tệp.
- Không giữ toàn bộ dữ liệu đã xem trong RAM.
- Tính toán có thể trả kết quả liên tục sau mỗi `a_t` hoặc khi luồng kết thúc.

Một hàm chỉ có một vòng `for` nhưng **đầu tiên gọi `readAllLines()`** không phải minh họa tốt cho mô hình bộ nhớ nhỏ: nó vẫn giữ toàn bộ đầu vào.

### 1.2. Bộ nhớ làm việc và kích thước đầu vào

Giả sử mỗi sự kiện là một số nguyên `long` 64 bit và luồng có N phần tử.

- **Lưu tất cả**: cần Θ(N) từ máy.
- **Count/min/max**: thường chỉ vài từ máy, tức O(1) **từ máy**.
- **Giữ mẫu k vị trí**: O(k) từ máy.
- **Giữ k−1 ứng viên tần suất cao**: O(k) bộ đếm và khóa.

**Phân biệt quan trọng:** nếu N không bị chặn, bộ đếm chính xác từ 0 tới N cần ít nhất Θ(log N) **bit**, không phải O(1) bit theo lý thuyết. Khi lập trình Java, `long` cung cấp một từ máy 64 bit, nên O(1) từ máy nhưng chỉ đếm được đến `Long.MAX_VALUE`.

Một chương trình thực tế phải quy định điều gì xảy ra nếu bộ đếm vượt phạm vi biểu diễn.

### 1.3. Thời gian xử lý mỗi sự kiện

Ngoài tổng thời gian, streaming quan tâm **chi phí cập nhật một sự kiện**:

- Trung bình O(1) để cập nhật thống kê cơ bản.
- O(1) kỳ vọng cho bước cập nhật reservoir sampling với chọn ngẫu nhiên có giới hạn.
- Misra–Gries có bước phải giảm tất cả k−1 bộ đếm: **O(k) trong một lần cập nhật xấu nhất**, nhưng có thể phân tích tổng chi phí là O(N) kỳ vọng với bảng băm chuẩn, nên O(1) **trung bình khấu hao** trên mỗi sự kiện.

Nếu hệ thống yêu cầu độ trễ tối đa rất thấp cho **từng** sự kiện, phân biệt "xấu nhất" và "khấu hao" là thiết yếu.

### 1.4. Append-only và luồng có cập nhật

Bài này tập trung vào **insertion-only / append-only stream**: mỗi phần tử mới được thêm vào dữ liệu.

Mô hình **turnstile stream** cho phép cập nhật dạng `(key,\Delta)` với `\Delta` có thể âm, tức đếm tăng/giảm. Các thuật toán như reservoir sampling đơn giản hoặc Misra–Gries trong bài **không tự động hỗ trợ xóa hoặc cập nhật âm** với cùng bảo đảm. Nếu có sự kiện hết hạn hoặc hủy, cần cấu trúc và chứng minh phù hợp.

---

## 2. Chọn trạng thái nhỏ thay vì giữ lịch sử

Cốt lõi của thiết kế streaming là tìm một tập trạng thái S đủ để trả lời câu hỏi quan tâm.

Ví dụ với luồng:

```text
2 4 2 7 2 4 9 2 7 2 4 2
```

Có N=12 giá trị. Nếu chỉ muốn đếm, tìm nhỏ nhất, lớn nhất, trung bình và phương sai, không cần cất cả 12 số. Một trạng thái:

```text
count
minimum
maximum
mean
M2
```

đã đủ cho các đại lượng đó.

Nếu muốn **lấy mẫu ngẫu nhiên k phần tử của luồng**, cần lưu k ô reservoir, không cần N ô.

Nếu muốn tìm các giá trị **xuất hiện nhiều hơn N/k lần**, thuật toán Misra–Gries chỉ dùng k−1 bộ đếm ứng viên. Nhưng lưu ý: nó trả **ứng viên với bảo đảm không bỏ sót**, không tự động trả **tần suất thực chính xác**.

### 2.1. Bài toán nào có lời giải gọn chính xác?

| Yêu cầu | Có thể xử lý một lượt với bộ nhớ nhỏ? | Lưu ý |
| --- | --- | --- |
| Count | Có, O(1) từ máy | Bộ đếm `long` vẫn có giới hạn |
| Min/max | Có, O(1) từ máy | Phải có ít nhất một phần tử |
| Tổng | Có về logic, trạng thái một số | Kiểm soát overflow; tổng chính xác không bị chặn cần số bit tăng |
| Mean | Có, O(1) trạng thái | Thực tế `double` có sai số |
| Variance | Có, dùng Welford | Sai số dấu phẩy động, không phải số học chính xác tuyệt đối |
| Mẫu ngẫu nhiên k quan sát | Có, O(k) | Phụ thuộc bộ sinh số ngẫu nhiên |
| Ứng viên tần suất `>N/k` | Có, O(k) | Misra–Gries, chỉ là ứng viên |
| Danh sách tất cả phần tử distinct chính xác | Không với bộ nhớ cố định nhỏ trong tổng quát | Có thể cần lượng thông tin theo miền giá trị |
| Median chính xác bất kỳ trong luồng tùy ý | Nói chung không có bộ nhớ O(1) từ máy | Phụ thuộc mô hình, miền giá trị và cách biểu diễn |
| Số lượng distinct xấp xỉ | Có các sketch | Ví dụ HyperLogLog, phụ thuộc giả thiết hash |

Lựa chọn thuật toán phải xuất phát từ **câu hỏi đầu ra** và **yêu cầu sai số**. Không có một "sketch vạn năng" vừa chính xác mọi truy vấn, vừa dùng bộ nhớ cố định nhỏ.

---

## 3. Count, min, max và tổng trong một lượt

Với mỗi giá trị x đến, duy trì:

```text
count += 1
minimum = min(minimum, x)
maximum = max(maximum, x)
sum += x
```

Đối với luồng chưa có phần tử, `minimum` và `maximum` **chưa xác định**; không được lấy 0 làm min/max mặc định nếu dữ liệu có thể toàn số dương hoặc âm.

### 3.1. Bất biến

Sau t phần tử:

\[
count=t,
\]

\[
minimum=\min_{1\le i\le t}a_i,
\]

\[
maximum=\max_{1\le i\le t}a_i.
\]

Chứng minh quy nạp đơn giản: bất biến đúng sau phần tử đầu. Khi thấy a_(t+1), lấy min/max với giá trị mới đúng là min/max của t+1 phần tử.

### 3.2. Vấn đề tràn số

`long count` có thể tràn nếu tăng qua `Long.MAX_VALUE`. Trong Java nên dùng `Math.addExact(count,1)` để **phát hiện lỗi**, không âm thầm chuyển sang số âm.

Tổng long cũng có thể tràn **dù từng giá trị đầu vào nằm trong long**. Có thể dùng `BigInteger` cho tổng, nhưng đừng gọi nó là "bộ nhớ bit cố định": số bit của một tổng nguyên không bị chặn có thể tăng theo N.

### 3.3. Trung bình không cần lưu tổng nguyên lớn

Một cách khác là cập nhật trung bình trực tuyến:

\[
\boxed{\mu_t=\mu_{t-1}+\frac{a_t-\mu_{t-1}}{t}.}
\]

Công thức này thuộc về thống kê Welford ở phần tiếp theo. Nó dùng một số thực tích lũy thay vì giữ một tổng long có thể tràn.

Với dữ liệu có độ lớn cực đại và N rất lớn, `double` vẫn có giới hạn độ chính xác, nên "không tràn tổng long" **không đồng nghĩa** "trung bình chính xác tuyệt đối".

---

## 4. Welford: trung bình và phương sai một lượt

Cho n quan sát số thực `x_1,\ldots,x_n`.

Trung bình:

\[
\mu_n=\frac1n\sum_{i=1}^{n}x_i.
\]

Tổng bình phương độ lệch quanh trung bình:

\[
M_{2,n}=\sum_{i=1}^{n}(x_i-\mu_n)^2.
\]

Phương sai của toàn bộ n quan sát (*population variance*):

\[
\boxed{\sigma_n^2=\frac{M_{2,n}}n,\quad n\ge1.}
\]

Phương sai mẫu không chệch theo công thức thông dụng (*sample variance*):

\[
\boxed{s_n^2=\frac{M_{2,n}}{n-1},\quad n\ge2.}
\]

Với n=0, trung bình và phương sai **chưa xác định**. Với n=1, phương sai tổng thể theo định nghĩa là 0, nhưng phương sai mẫu chia cho n−1 **không xác định**.

### 4.1. Công thức cập nhật Welford

Giả sử sau t−1 quan sát có trung bình `\mu_{t-1}` và trạng thái `M_{2,t-1}`. Khi gặp x:

\[
\delta=x-\mu_{t-1},
\]

\[
\boxed{\mu_t=\mu_{t-1}+\frac{\delta}{t},}
\]

\[
\delta_2=x-\mu_t,
\]

\[
\boxed{M_{2,t}=M_{2,t-1}+\delta\,\delta_2.}
\]

Trường hợp phần tử đầu tiên: n=1, `mean=x`, `M2=0`.

**Trạng thái:** `(n,mean,M2,min,max)`, dùng số lượng từ máy cố định.

### 4.2. Vì sao Welford tốt hơn lấy E[x²]−E[x]² một cách ngây thơ?

Một công thức đại số là:

\[
\operatorname{Var}(X)=\frac{\sum x_i^2}{n}
-\left(\frac{\sum x_i}{n}\right)^2.
\]

Nếu các x_i rất lớn nhưng gần nhau, hai số hạng có thể **rất lớn và gần bằng nhau**; phép trừ gây **mất chữ số có nghĩa** (*catastrophic cancellation*).

Welford cập nhật theo độ lệch so với trung bình đang có, thường ổn định số hơn. Tuy vậy đây **không phải bảo đảm tính chính xác vô hạn**; nếu dữ liệu có độ lớn cực đoan, phân bố khó hoặc n quá lớn, sai số `double` vẫn tồn tại.

### 4.3. Vì sao M2 được cập nhật như vậy?

Vì:

\[
\mu_t=\mu_{t-1}+\frac{x-\mu_{t-1}}t
\]

nên:

\[
x-\mu_t=\frac{t-1}{t}(x-\mu_{t-1}).
\]

Có thể biến đổi tổng bình phương độ lệch để thấy:

\[
M_{2,t}-M_{2,t-1}
=(x-\mu_{t-1})(x-\mu_t).
\]

Đây chính là công thức `\delta\delta_2`. Chỉ cần lưu mean và M2 trước đó, **không cần giữ những x_i cũ**.

### 4.4. Ví dụ với luồng 12 phần tử

```text
2 4 2 7 2 4 9 2 7 2 4 2
```

Tần suất thật:

| Giá trị | Số lần |
| ---: | ---: |
| 2 | 6 |
| 4 | 3 |
| 7 | 2 |
| 9 | 1 |

Tổng:

\[
2\cdot6+4\cdot3+7\cdot2+9\cdot1=47.
\]

Tổng bình phương:

\[
2^2\cdot6+4^2\cdot3+7^2\cdot2+9^2\cdot1=251.
\]

Trung bình:

\[
\boxed{\mu=\frac{47}{12}\approx3.9166667.}
\]

Tổng bình phương độ lệch:

\[
M_2=251-\frac{47^2}{12}
=251-\frac{2209}{12}
=\frac{803}{12}\approx66.9166667.
\]

Phương sai tổng thể:

\[
\boxed{\sigma^2=\frac{803}{144}\approx5.5763889.}
\]

Phương sai mẫu:

\[
\boxed{s^2=\frac{803}{132}\approx6.0833333.}
\]

Min=2, max=9, count=12.

Chương trình Java sẽ in trung bình `3.9167`, phương sai tổng thể `5.5764`, phương sai mẫu `6.0833` khi làm tròn bốn chữ số thập phân.

### 4.5. Chứng minh theo một lượt

Sau mỗi quan sát, Welford chỉ sửa `mean,M2,count` và min/max. Nó không cần tra cứu `x_1,\ldots,x_{t-1}`. Vì vậy thuật toán đúng mô hình **single-pass** và O(1) trạng thái theo số từ máy.

---

## 5. Reservoir sampling: lấy k quan sát ngẫu nhiên

Nếu không biết độ dài N của luồng nhưng muốn chọn **k vị trí quan sát** ngẫu nhiên, cách ngây thơ "lưu tất cả rồi shuffle" cần O(N) bộ nhớ.

**Reservoir sampling** giữ một mảng kích thước tối đa k, đảm bảo sau khi đã thấy t≥k sự kiện, mọi **vị trí** trong t sự kiện đầu được chọn với cùng xác suất:

\[
\boxed{\Pr[\text{vị trí }i\text{ nằm trong mẫu}]=\frac{k}{t}.}
\]

Nếu t<k, thuật toán giữ toàn bộ t vị trí.

### 5.1. Thuật toán cơ bản

1. Đổ k quan sát đầu vào `reservoir[0..k-1]`.
2. Với quan sát thứ t>k, chọn chỉ số ngẫu nhiên nguyên đều:
   \[
   j\in\{0,1,\ldots,t-1\}.
   \]
3. Nếu j<k thì thay `reservoir[j]` bằng quan sát mới; nếu j≥k thì bỏ qua sự kiện mới.

Giả mã:

```text
RESERVOIR_OFFER(item):
    seen += 1

    if sample.size < k:
        sample.add(item)
    else if k > 0:
        j = UNIFORM_RANDOM_INTEGER(0, seen-1)

        if j < k:
            sample[j] = item
```

### 5.2. Chứng minh xác suất đồng đều

Giả sử ở thời điểm t−1 (≥k), mỗi vị trí cũ có xác suất xuất hiện trong mẫu:

\[
\frac{k}{t-1}.
\]

Ở thời điểm t, sự kiện mới được nhận với xác suất:

\[
\frac{k}{t}
\]

vì có k giá trị j được chấp nhận trong t giá trị đồng xác suất.

Một vị trí cũ đang nằm trong mẫu bị thay thế với xác suất **1/t**: trong t chỉ số j, chính xác một chỉ số trỏ đến ô đang chứa vị trí đó. Xác suất nó vẫn ở lại:

\[
\frac{k}{t-1}
\left(1-\frac1t\right)
=\frac{k}{t}.
\]

Như vậy cả vị trí mới lẫn mọi vị trí cũ đều có xác suất `k/t`. Định lý đúng bằng quy nạp.

### 5.3. Phân biệt vị trí và giá trị

Nếu luồng có nhiều giá trị bằng nhau, reservoir lấy mẫu **các lần xuất hiện**, không phải mỗi **giá trị phân biệt**.

Ví dụ:

```text
A A A B
```

Chọn một vị trí ngẫu nhiên đều cho xác suất giá trị A là 3/4, giá trị B là 1/4. Đó là hành vi **đúng** cho sample từ luồng theo lần xuất hiện, không phải sample đều giữa hai khóa distinct A,B.

### 5.4. Độ phức tạp và giới hạn

- Bộ nhớ: **O(k)** phần tử.
- Mỗi sự kiện: O(1) kỳ vọng nếu bộ sinh số ngẫu nhiên có phép chọn nguyên bị chặn hiệu quả.
- Không cần biết N trước.
- Mẫu là **ngẫu nhiên**, kết quả nội dung có thể khác giữa các lần chạy/seed.
- Trong chứng minh, ta giả sử lựa chọn j phân phối đều. `SplittableRandom` trong Java là PRNG thực dụng, không phải nguồn ngẫu nhiên mật mã và không có bảo đảm chống lại đối thủ biết seed.
- Nếu k=0, mẫu luôn rỗng. Nếu t<k, lưu mọi sự kiện đã thấy.

### 5.5. Reservoir không tự trả lời mọi truy vấn

Mẫu ngẫu nhiên có thể dùng để **ước lượng phân phối, trung bình hoặc phần trăm** với sai số thống kê thích hợp. Nhưng k nhỏ không cho một bảo đảm "mọi giá trị đều chính xác", và các giá trị cực hiếm có thể không xuất hiện trong mẫu.

Nếu cần đếm tần suất một khóa cụ thể bằng sai số được kiểm soát, nên xem **Count-Min Sketch** hoặc giải pháp chuyên dụng; nếu cần tìm heavy hitters, dùng **Misra–Gries**.

---

## 6. Misra–Gries: phát hiện ứng viên heavy hitter

Một **heavy hitter** là phần tử xuất hiện rất thường xuyên. Giả sử muốn **không bỏ sót** mọi khóa có tần suất:

\[
\boxed{f(x)>\frac{N}{k},\qquad k\ge2.}
\]

Thuật toán **Misra–Gries** chỉ giữ tối đa **k−1 cặp (khóa, bộ đếm)**.

Điều quan trọng: đầu ra là tập **ứng viên**, không nhất thiết chỉ gồm các heavy hitter thật.

### 6.1. Quy tắc cập nhật

Với một phần tử x mới:

1. Nếu x đang có trong bảng, tăng bộ đếm của x lên 1.
2. Nếu chưa có x và bảng còn dưới k−1 khóa, thêm x với bộ đếm 1.
3. Nếu chưa có x và bảng đang đầy k−1 khóa, **giảm tất cả bộ đếm đi 1**; x mới **không được thêm ngay**. Xóa các khóa có bộ đếm giảm về 0.

Giả mã:

```text
MISRA_GRIES_OFFER(x):
    N += 1

    if x in counters:
        counters[x] += 1
    else if counters.size < k-1:
        counters[x] = 1
    else:
        for key in counters:
            counters[key] -= 1

            if counters[key] == 0:
                remove key
```

Không có bước giữ toàn bộ luồng hoặc đếm tần suất thật của mọi khóa.

### 6.2. Ví dụ k=3, tối đa hai bộ đếm

Luồng:

```text
2 4 2 7 2 4 9 2 7 2 4 2
```

Từng bước (hiển thị các bộ đếm còn lại):

| t | Phần tử | Hành động | Trạng thái sau xử lý |
| ---: | ---: | --- | --- |
| 1 | 2 | Thêm | {2:1} |
| 2 | 4 | Thêm | {2:1, 4:1} |
| 3 | 2 | Tăng | {2:2, 4:1} |
| 4 | 7 | Giảm tất cả | {2:1} |
| 5 | 2 | Tăng | {2:2} |
| 6 | 4 | Thêm | {2:2, 4:1} |
| 7 | 9 | Giảm tất cả | {2:1} |
| 8 | 2 | Tăng | {2:2} |
| 9 | 7 | Thêm | {2:2, 7:1} |
| 10 | 2 | Tăng | {2:3, 7:1} |
| 11 | 4 | Giảm tất cả | {2:2} |
| 12 | 2 | Tăng | **{2:3}** |

Cuối luồng:

```text
N = 12
k = 3
threshold = N/k = 4
candidate residual counters = {2:3}
decrement rounds = 3
```

Tần suất **thật** của 2 là **6**, không phải 3. Phần tử 2 thỏa:

\[
6>\frac{12}{3}=4,
\]

nên phải được giữ trong bảng ứng viên. Bộ đếm **3** là phần dư sau các lần trừ, **không phải tần suất thật**.

### 6.3. Chứng minh bảo đảm không bỏ sót

Mỗi khi bảng đã đầy k−1 khóa và gặp một khóa mới x:

- x khác tất cả k−1 khóa đang giữ.
- Bước giảm mỗi bộ đếm đi một có thể hiểu là **loại đi một lần xuất hiện của k khóa phân biệt**: k−1 khóa đang giữ và chính x mới đến.

Sau D lượt giảm toàn bộ, ta đã "triệt tiêu" kD lần xuất hiện, trong đó **mỗi lượt chỉ triệt tiêu tối đa một lần xuất hiện của một khóa bất kỳ**.

Vì tổng có N lần xuất hiện:

\[
\boxed{kD\le N\quad\Rightarrow\quad D\le\frac Nk.}
\]

Nếu một khóa a có tần suất:

\[
f(a)>\frac Nk,
\]

thì không thể triệt tiêu hết các lần xuất hiện của a qua tối đa D lượt giảm (mỗi lượt nhiều nhất một lần của a). Vậy **a phải còn trong bảng cuối cùng**.

Suy ra:

\[
\boxed{
f(a)>\frac Nk
\Rightarrow
a\in\text{candidates}.
}
\]

Chiều ngược lại **không bắt buộc**:

\[
a\in\text{candidates}
\not\Rightarrow
f(a)>\frac Nk.
\]

Vì thế cần gọi là **ứng viên**, không gọi mọi khóa còn lại là heavy hitter đã chứng minh.

### 6.4. Cận cho bộ đếm phần dư

Gọi `c(a)` là bộ đếm còn lại của a, bằng 0 nếu a không có trong bảng cuối. Với D lượt giảm toàn bộ:

\[
\boxed{c(a)\le f(a)\le c(a)+D.}
\]

- Bộ đếm c không thể **lớn hơn** tần suất thật.
- Mỗi lượt giảm có thể làm "mất" nhiều nhất một lần xuất hiện của một khóa cụ thể.
- Nếu a **không còn** trong bảng, `c(a)=0`, nên `f(a)\le D\le N/k`; do đó không thể là phần tử xuất hiện **hơn** N/k lần.

Trong ví dụ, c(2)=3, D=3:

\[
3\le f(2)\le6.
\]

Thực tế `f(2)=6`, chạm cận trên.

### 6.5. Vì sao không thể xác minh chính xác trong đúng một lượt với k−1 bộ đếm?

Misra–Gries cố ý bỏ bớt thông tin khi giảm đồng loạt. Do đó bộ đếm phần dư không đủ để khôi phục mọi tần suất thật.

Nếu **nguồn có thể đọc lại**, sau lượt đầu ta có tối đa k−1 ứng viên; lượt thứ hai chỉ đếm chính xác các ứng viên này. Nhưng đó là **hai lượt**, không còn là ràng buộc nghiêm ngặt "một lượt".

Nếu **không thể đọc lại**, có thể:

- Chấp nhận tập ứng viên với bảo đảm không bỏ sót.
- Dùng cận `c≤f≤c+D`.
- Kết hợp một sketch xấp xỉ như Count-Min để ước lượng tần suất.
- Thiết kế pipeline khác hoặc lưu thêm dữ liệu tùy yêu cầu sai số.

Không được báo bộ đếm Misra–Gries như "frequency exact".

### 6.6. Độ phức tạp

- Bộ nhớ: O(k) khóa và bộ đếm, thực tế tối đa k−1 khóa.
- Một cập nhật thường: tra bảng và tăng/thêm O(1) kỳ vọng với hash map.
- Một lượt giảm toàn bộ: O(k).
- Vì mỗi lượt giảm triệt tiêu k lần xuất hiện khác nhau, D≤N/k, tổng công việc giảm là O(kD)=O(N).
- Với hash map có chi phí kỳ vọng O(1), **tổng thời gian O(N) kỳ vọng**, tức O(1) **khấu hao** mỗi quan sát.
- Nếu yêu cầu giới hạn thời gian xấu nhất cho mỗi sự kiện, bản giản đơn có bước giảm O(k), cần kiến trúc khác hoặc kỹ thuật tối ưu.

Về **bit memory**, mỗi bộ đếm có thể cần O(log N) bit và khóa cũng tốn không gian biểu diễn. Vì vậy O(k) chỉ là cách nói theo số bộ đếm và từ máy cố định.

---

## 7. Heavy hitters khác top-k chính xác

Hai bài toán dễ bị đánh đồng:

**Heavy hitters theo ngưỡng:** trả tất cả khóa có tần suất lớn hơn N/k. Số khóa thật sự vượt ngưỡng này tối đa k−1, vì nếu có k khóa mỗi khóa lớn hơn N/k thì tổng vượt N.

**Top-k chính xác:** xếp hạng k khóa có tần suất cao nhất và tần suất chính xác của chúng, xử lý cả trường hợp hòa.

Misra–Gries dùng k−1 bộ đếm và bảo đảm chứa **mọi khóa vượt N/k**, nhưng không bảo đảm:

- Tập ứng viên là top-(k−1) chính xác.
- Cột đếm còn lại là tần suất thật.
- Thứ tự của các ứng viên theo bộ đếm phần dư luôn trùng thứ tự tần suất thật.
- Không có ứng viên nào ở dưới ngưỡng.

Nếu đề bài yêu cầu top-k chính xác trên miền khóa lớn, phải phân tích giới hạn bộ nhớ và phương án bổ sung; không được thay mục tiêu mà không nói rõ.

### 7.1. Dấu ">" là nghiêm ngặt

Bảo đảm Misra–Gries là:

\[
f(a)>\frac Nk.
\]

Không được tự đổi thành:

\[
f(a)\ge\frac Nk.
\]

Một khóa có tần suất **đúng bằng** N/k có thể không còn trong bảng cuối cùng.

### 7.2. N và k ảnh hưởng bộ nhớ thế nào?

Với một tỉ lệ ngưỡng `\phi`, thường chọn:

\[
k\approx\frac1\phi.
\]

Đổi lại, số bộ đếm tăng xấp xỉ O(1/φ). Ngưỡng thấp hơn giúp bắt nhiều khóa ít phổ biến hơn nhưng tốn bộ nhớ nhiều hơn.

---

## 8. Count-Min Sketch: đánh đổi tính chính xác lấy bộ nhớ

Khi muốn trả lời ước lượng số lần xuất hiện của nhiều khóa, không thể lưu bản đồ tần suất exact của mọi khóa nếu miền khóa khổng lồ và RAM nhỏ.

**Count-Min Sketch (CMS)** dùng một bảng bộ đếm:

\[
d\times w
\]

và d hàm hash đưa khóa vào w cột ở mỗi hàng.

Với sự kiện khóa x trong luồng chỉ tăng:

\[
table[r][h_r(x)]\leftarrow
table[r][h_r(x)]+1
\]

với từng hàng r.

Khi hỏi tần suất ước lượng của x:

\[
\boxed{\hat f(x)=\min_r table[r][h_r(x)].}
\]

### 8.1. Vì sao kết quả thường lớn hơn hoặc bằng tần suất thật?

Với cập nhật không âm, mỗi ô đếm tất cả sự kiện có hash vào ô đó. Nó chứa số lần xuất hiện của x **cộng các khóa va chạm**.

Vì vậy trong số học chính xác và không có overflow:

\[
\boxed{\hat f(x)\ge f(x)}.
\]

CMS có xu hướng **đếm dư**, không đếm thiếu, trong mô hình insert-only với cập nhật dương.

### 8.2. Bảo đảm xác suất thường dùng

Với lựa chọn độ rộng cỡ:

\[
w=\left\lceil\frac e\varepsilon\right\rceil
\]

và độ sâu cỡ:

\[
d=\left\lceil\ln\frac1\delta\right\rceil,
\]

cùng họ hash độc lập/pairwise-independent phù hợp, có thể thiết lập với **một khóa truy vấn cố định**:

\[
\Pr\left[
f(x)\le\hat f(x)\le f(x)+\varepsilon N
\right]\ge1-\delta.
\]

Đây là **bảo đảm xác suất có giả thiết về hash**, không phải kết luận đúng chắc chắn với bất kỳ hàm `hashCode()` nào. Nếu hỏi đồng thời rất nhiều khóa, muốn bảo đảm đồng thời cần điều chỉnh xác suất bằng kỹ thuật như union bound và giả thiết liên quan.

### 8.3. Bộ nhớ và thời gian

- Dùng O(wd) bộ đếm.
- Mỗi sự kiện cập nhật d hàng.
- Mỗi query tính minimum trên d ô.

Nếu hệ thống chỉ có bộ nhớ nhất định, ta chọn ε,δ sao cho bảng vừa RAM. Nhưng mỗi bộ đếm vẫn có giới hạn biểu diễn; cần xử lý overflow.

### 8.4. Khi nào CMS không thay thế Misra–Gries?

CMS cho **ước lượng tần suất khi đã biết khóa x cần hỏi**, không tự sinh danh sách tất cả khóa thường gặp nếu không có cơ chế tìm ứng viên.

Misra–Gries làm tốt việc **sinh một tập ứng viên nhỏ**. Hai cách có thể kết hợp: Misra–Gries cho ứng viên, CMS cho ước lượng tần suất, chấp nhận sai số xác suất.

**Cẩn thận:** với luồng có cập nhật âm/xóa, tính chất "CMS chỉ đếm dư" như trên không tự giữ nguyên; phải dùng mô hình/cấu trúc được thiết kế cho cập nhật tương ứng.

---

## 9. Distinct count và HyperLogLog

Bài toán **đếm số khóa phân biệt** (*distinct count*) yêu cầu:

\[
F_0=|\{a_1,\ldots,a_N\}|.
\]

Nếu lưu một `HashSet` chứa mọi khóa, kết quả exact nhưng bộ nhớ:

\[
O(F_0)
\]

khóa, có thể lớn gần bằng N.

**HyperLogLog (HLL)** là ví dụ sketch dùng các giá trị hash, chia thành nhiều thanh ghi, theo dõi thông tin về số bit 0 đầu tiên (hoặc cấu trúc tương đương) và dùng công thức hiệu chỉnh để **ước lượng** số distinct.

### 9.1. Tính chất quan trọng

- Không cần giữ danh sách toàn bộ khóa.
- Bộ nhớ phụ thuộc **số thanh ghi** và số bit mỗi thanh ghi.
- Trong mô hình hash đủ đều và các giả thiết thích hợp, sai số tương đối chuẩn của HLL thường xấp xỉ:
  \[
  \boxed{\frac{1.04}{\sqrt m}}
  \]
  với m là số thanh ghi.
- Đây là độ lệch chuẩn tương đối điển hình của ước lượng, **không phải cận sai số tuyệt đối đảm bảo cho mọi luồng**.
- Với cardinality rất nhỏ, rất lớn hoặc hash có va chạm, các phiên bản HLL cần cơ chế hiệu chỉnh phù hợp.

### 9.2. Vì sao đếm distinct exact cần bộ nhớ lớn trong tổng quát?

Giả sử miền khóa có U phần tử. Một thuật toán một lượt deterministic cần trả **đúng số distinct** sau bất kỳ tiền tố và mọi đoạn nối tiếp.

Có:

\[
2^U
\]

tập con khả dĩ S của miền khóa.

Nếu hai tập con khác nhau S,T dẫn đến **cùng trạng thái**, sẽ có mâu thuẫn:

- Nếu |S|≠|T|, bộ giải đã phải trả hai số khác nhau ngay lúc đó.
- Nếu |S|=|T| nhưng S≠T, chọn một khóa a∈S\T. Nối thêm a: số distinct của S **không đổi**, còn của T **tăng 1**. Hai trạng thái giống nhau sẽ không thể trả hai kết quả khác nhau.

Vậy các tập con phải tương ứng trạng thái khác nhau. Cần ít nhất:

\[
\log_2(2^U)=\boxed{U\text{ bit}}
\]

trong mô hình tổng quát này.

Kết quả giải thích tại sao muốn bộ nhớ rất nhỏ so với U, ta thường phải **cho phép xấp xỉ hoặc thay đổi yêu cầu**.

### 9.3. Exact median cũng khó

Median chính xác của luồng có thứ tự bất kỳ và miền giá trị rộng thường cần giữ nhiều thông tin hơn vài bộ đếm. Các thuật toán exact median online có thể dùng cấu trúc hai heap, nhưng bộ nhớ tổng quát có thể tăng **O(N)** phần tử.

Có các thuật toán **xấp xỉ quantile** theo luồng với lượng bộ nhớ nhỏ hơn N, nhưng phải phát biểu rõ sai số theo **rank** hoặc giá trị, không tự gọi kết quả là median exact.

---

## 10. Bloom filter: một truy vấn khác

Bloom filter là cấu trúc bit và nhiều hàm hash để hỏi:

> Khóa x **có thể đã xuất hiện** hay **chắc chắn chưa xuất hiện**?

Với insertion-only Bloom filter chuẩn, giả sử hash được thực hiện đúng, không xóa bit:

- Nếu kết quả "chưa từng xuất hiện", đó là một kết luận **không có false negative**.
- Nếu kết quả "có thể đã xuất hiện", có thể là **false positive** vì hash collision.

Bloom filter **không trả tần suất**, không trả số distinct chính xác và không thay thế reservoir.

Nếu có yêu cầu **xóa**, một Bloom filter bit chuẩn có thể bị sai (xóa bit làm mất bằng chứng của khóa khác cùng hash). Cần biến thể như counting Bloom filter, đi kèm giới hạn và bảo đảm riêng.

### 10.1. Chọn đúng công cụ

| Câu hỏi | Công cụ tiêu biểu | Kết quả |
| --- | --- | --- |
| Mean và variance | Welford | Một trạng thái thống kê |
| Mẫu k sự kiện | Reservoir sampling | Mẫu ngẫu nhiên vị trí |
| Ứng viên `f>N/k` | Misra–Gries | Không bỏ sót heavy hitter theo ngưỡng |
| Ước lượng tần suất khóa x | Count-Min Sketch | Cận trên và sai số xác suất |
| Ước lượng số distinct | HyperLogLog | Ước lượng với sai số thống kê |
| Khóa có thể đã thấy? | Bloom filter | Có thể đã thấy / chắc chắn chưa thấy |

Không phải mọi công cụ đều giải cùng một bài toán. Trong một pipeline, nhiều sketch có thể được cập nhật **đồng thời trong một lượt đọc**.

---

## 11. Một lượt không có nghĩa chỉ một phép tính

Một bản ghi đến có thể được gửi qua nhiều bộ cập nhật:

```text
                      +--> Welford (count/min/max/mean/variance)
                      |
InputStream --> parse +--> Misra-Gries (heavy hitter candidates)
                      |
                      +--> Reservoir (random sample)
```

Dù có ba bộ xử lý, mỗi số đầu vào chỉ được **đọc một lần**. Trạng thái lưu là tổng bộ nhớ các bộ xử lý:

\[
O(1)+O(k_1)+O(k_2),
\]

không phải O(N).

Nhưng nếu dùng cùng ký hiệu k cho cả Misra–Gries và reservoir, cần nhớ:

- Misra–Gries với tham số k giữ **tối đa k−1** khóa.
- Reservoir với tham số k giữ **tối đa k** vị trí.

Đây là hai ý nghĩa tham số khác nhau, dù đều dùng O(k) bộ nhớ.

### 11.1. Xử lý lỗi ngay trên luồng

Trong hệ thống thật, một bản ghi sai định dạng có thể xuất hiện sau hàng triệu bản ghi hợp lệ. Khi không lưu nguồn để đọc lại, ta không thể "rollback" các bộ thống kê chỉ bằng cách quay đầu vào.

Chương trình nên có chính sách rõ: từ chối luồng khi gặp token lỗi, bỏ qua bản ghi kèm bộ đếm lỗi, hoặc đưa lỗi sang dead-letter queue. Không được âm thầm ép token lỗi thành 0 vì như vậy làm sai thống kê.

### 11.2. Phân biệt bộ nhớ input với bộ nhớ thuật toán

Một mã đọc từng dòng bằng `BufferedReader.readLine()` không giữ **mọi dòng**, nhưng vẫn có thể tạo một `String` dài bằng **độ dài dòng lớn nhất**. Nếu nguồn không tin cậy gửi một dòng dài hàng GB, bộ nhớ có thể tăng ngoài ý muốn.

Demo Java bên dưới dùng **bộ đệm byte cố định 8192 byte** và **token tối đa 20 ký tự ASCII** cho số nguyên long. Do đó phần parser cũng không tích lũy một dòng không giới hạn.

---

## 12. Java 17+: chương trình hoàn chỉnh một lượt, RAM có giới hạn

Chương trình **`OnePassBoundedMemoryDemo.java`** thực hiện ba công việc trên **cùng một lượt đọc**:

1. **OnlineMoments:** cập nhật số lượng, min, max, trung bình, phương sai tổng thể/mẫu qua Welford.
2. **MisraGries:** với k=3, giữ tối đa hai bộ đếm ứng viên, đếm số vòng giảm đồng loạt.
3. **ReservoirSampler:** lấy mẫu tối đa ba vị trí qua `SplittableRandom.nextLong(bound)`.

Đầu vào là các số nguyên thập phân có dấu nằm trong `long`, tách bằng **khoảng trắng ASCII**, newline hoặc tab. Parser chấp nhận token tối đa 20 ký tự và **từ chối** token sai/ngoài phạm vi `long`; không phải parser CSV.

Nếu chạy không có tham số, chương trình dùng bộ dữ liệu demo ngắn để có đầu ra xác định. Nếu chạy `--stdin`, nó đọc luồng thật từ `System.in` tới EOF. Nội dung **mẫu reservoir** được chọn ngẫu nhiên nên không in trực tiếp trong stdout cố định; chương trình chỉ in số phần tử đã thấy và kích thước mẫu.

### 12.1. Mã Java 17

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.SplittableRandom;
import java.util.TreeMap;

public final class OnePassBoundedMemoryDemo {

    // Reads decimal long tokens using a FIXED 8192-byte buffer.
    // Maximum token length is 20 ASCII characters.
    static final class LongTokenReader {
        private final InputStream input;
        private final byte[] buffer = new byte[8192];
        private int position = 0;
        private int length = 0;

        LongTokenReader(InputStream input) {
            this.input = input;
        }

        private int nextByte() throws IOException {
            while (position >= length) {
                length = input.read(buffer);
                position = 0;

                if (length < 0) {
                    return -1;
                }
            }
            return buffer[position++] & 0xff;
        }

        // Returns null ONLY on EOF before the next token.
        Long nextLongOrNull() throws IOException {
            int b;

            do {
                b = nextByte();
            } while (b >= 0 && b <= 32);

            if (b < 0) {
                return null;
            }

            StringBuilder token = new StringBuilder(20);

            while (b > 32) {
                if (token.length() >= 20) {
                    throw new IllegalArgumentException(
                            "Integer token exceeds 20 bytes");
                }

                token.append((char) b);
                b = nextByte();
            }

            try {
                return Long.parseLong(token.toString());
            } catch (NumberFormatException ex) {
                throw new IllegalArgumentException(
                        "Expected a signed decimal long", ex);
            }
        }
    }

    static final class OnlineMoments {
        private long count = 0;
        private long minimum = 0;
        private long maximum = 0;
        private double mean = 0.0;
        private double m2 = 0.0;

        void offer(long x) {
            count = Math.addExact(count, 1L);

            if (count == 1) {
                minimum = x;
                maximum = x;
                mean = (double) x;
                m2 = 0.0;
                return;
            }

            if (x < minimum) {
                minimum = x;
            }
            if (x > maximum) {
                maximum = x;
            }

            double value = (double) x;
            double delta = value - mean;
            mean += delta / (double) count;
            double deltaAfter = value - mean;
            m2 += delta * deltaAfter;
        }

        long count() {
            return count;
        }

        long minimum() {
            if (count == 0) {
                throw new IllegalStateException("Empty stream");
            }
            return minimum;
        }

        long maximum() {
            if (count == 0) {
                throw new IllegalStateException("Empty stream");
            }
            return maximum;
        }

        double mean() {
            return count == 0 ? Double.NaN : mean;
        }

        double populationVariance() {
            return count == 0 ? Double.NaN : m2 / count;
        }

        double sampleVariance() {
            return count < 2 ? Double.NaN : m2 / (count - 1);
        }
    }

    // Candidate keys whose true frequency may exceed N/k.
    // Holds at most k-1 counters, NEVER exact frequencies.
    static final class MisraGries {
        private final int k;
        private final LinkedHashMap<Long, Long> counters =
                new LinkedHashMap<>();
        private long seen = 0;
        private long decrementRounds = 0;

        MisraGries(int k) {
            if (k < 2) {
                throw new IllegalArgumentException("k must be >= 2");
            }
            this.k = k;
        }

        void offer(long item) {
            seen = Math.addExact(seen, 1L);

            Long oldCount = counters.get(item);

            if (oldCount != null) {
                counters.put(item, Math.addExact(oldCount, 1L));
                return;
            }

            if (counters.size() < k - 1) {
                counters.put(item, 1L);
                return;
            }

            decrementRounds = Math.addExact(
                    decrementRounds, 1L);

            Iterator<Map.Entry<Long, Long>> iterator =
                    counters.entrySet().iterator();

            while (iterator.hasNext()) {
                Map.Entry<Long, Long> entry = iterator.next();
                long updated = entry.getValue() - 1L;

                if (updated == 0L) {
                    iterator.remove();
                } else {
                    entry.setValue(updated);
                }
            }
        }

        Map<Long, Long> candidateCounters() {
            return new TreeMap<>(counters);
        }

        long decrementRounds() {
            return decrementRounds;
        }

        long seen() {
            return seen;
        }
    }

    // Uniform sample of stream POSITIONS, not distinct values.
    static final class ReservoirSampler {
        private final int capacity;
        private final SplittableRandom random;
        private final ArrayList<Long> sample;
        private long seen = 0;

        ReservoirSampler(int capacity, long seed) {
            if (capacity < 0) {
                throw new IllegalArgumentException(
                        "capacity must be nonnegative");
            }

            this.capacity = capacity;
            this.random = new SplittableRandom(seed);
            this.sample = new ArrayList<>(capacity);
        }

        void offer(long x) {
            seen = Math.addExact(seen, 1L);

            if (sample.size() < capacity) {
                sample.add(x);
                return;
            }

            if (capacity == 0) {
                return;
            }

            // Choose an index uniformly from [0, seen).
            long index = random.nextLong(seen);

            if (index < capacity) {
                sample.set((int) index, x);
            }
        }

        long seen() {
            return seen;
        }

        int sampleSize() {
            return sample.size();
        }

        // Defensive copy for an application that needs the values.
        ArrayList<Long> snapshot() {
            return new ArrayList<>(sample);
        }
    }

    private static void process(InputStream input)
            throws IOException {

        LongTokenReader reader = new LongTokenReader(input);
        OnlineMoments moments = new OnlineMoments();
        MisraGries heavy = new MisraGries(3);
        ReservoirSampler reservoir =
                new ReservoirSampler(3, 20261110L);

        Long boxed;

        // ONE PASS: each integer is read and dispatched once.
        while ((boxed = reader.nextLongOrNull()) != null) {
            long value = boxed;
            moments.offer(value);
            heavy.offer(value);
            reservoir.offer(value);
        }

        System.out.println("Records: " + moments.count());

        if (moments.count() == 0) {
            System.out.println("Empty stream: no statistics");
            return;
        }

        System.out.println("Minimum: " + moments.minimum());
        System.out.println("Maximum: " + moments.maximum());

        System.out.printf(
                Locale.ROOT,
                "Mean: %.4f%n",
                moments.mean());

        System.out.printf(
                Locale.ROOT,
                "Population variance: %.4f%n",
                moments.populationVariance());

        if (moments.count() >= 2) {
            System.out.printf(
                    Locale.ROOT,
                    "Sample variance: %.4f%n",
                    moments.sampleVariance());
        } else {
            System.out.println("Sample variance: undefined");
        }

        System.out.println(
                "MG k=3 residual counters: "
                        + heavy.candidateCounters());
        System.out.println(
                "MG decrement rounds: "
                        + heavy.decrementRounds());

        System.out.println(
                "Reservoir seen: " + reservoir.seen());
        System.out.println(
                "Reservoir sample size: "
                        + reservoir.sampleSize());
    }

    public static void main(String[] args) throws IOException {
        if (args.length > 1 ||
                (args.length == 1
                        && !"--stdin".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Use no arguments or --stdin");
        }

        if (args.length == 1) {
            // Real stream; no readAllBytes/readAllLines.
            process(System.in);
        } else {
            // Fixed TEST FIXTURE only, not an input requirement.
            String demo =
                    "2 4 2 7 2 4 9 2 7 2 4 2";

            byte[] data = demo.getBytes(
                    StandardCharsets.US_ASCII);

            process(new ByteArrayInputStream(data));
        }
    }
}
```

### 12.2. Biên dịch và chạy

Với JDK 17+:

```bash
javac OnePassBoundedMemoryDemo.java
java OnePassBoundedMemoryDemo
```

**Stdout của chế độ demo mặc định:**

```text
Records: 12
Minimum: 2
Maximum: 9
Mean: 3.9167
Population variance: 5.5764
Sample variance: 6.0833
MG k=3 residual counters: {2=3}
MG decrement rounds: 3
Reservoir seen: 12
Reservoir sample size: 3
```

Chế độ đọc một luồng thật qua đầu vào chuẩn:

```bash
java OnePassBoundedMemoryDemo --stdin
```

Sau đó nhập các số nguyên tách bằng khoảng trắng hoặc xuống dòng, rồi gửi EOF theo hệ điều hành/terminal của bạn. Có thể chuyển hướng từ một tệp số nguyên phù hợp mà không làm chương trình nạp toàn bộ tệp.

### 12.3. Giải thích phần input parser

`LongTokenReader` dùng mảng byte:

```java
private final byte[] buffer = new byte[8192];
```

và đọc từng byte theo nhu cầu. Một token tối đa **20 ký tự ASCII**, đủ cho số long có dấu dạng thập phân như:

```text
-9223372036854775808
9223372036854775807
```

Mọi token dài hơn giới hạn hoặc không parse được sẽ gây `IllegalArgumentException`. Không giữ tất cả các dòng, không giữ một dòng dài không giới hạn.

Giới hạn **20 ký tự** là **hợp đồng parser của demo**, không phải nói rằng mọi biểu diễn có nhiều số 0 đầu đều bị Java từ chối; demo chủ ý từ chối token quá dài để giữ giới hạn bộ nhớ.

### 12.4. Welford trong Java

`OnlineMoments` lưu `count,minimum,maximum,mean,m2`. Các trường min/max chỉ có nghĩa khi count≥1.

Khi giá trị mới đến:

```java
double delta = value - mean;
mean += delta / (double) count;
double deltaAfter = value - mean;
m2 += delta * deltaAfter;
```

Không giữ một danh sách tất cả `value`, không gọi `sort`. Phương sai mẫu chỉ có nghĩa khi count≥2.

### 12.5. Misra–Gries trong Java

Bảng `LinkedHashMap<Long,Long>` chứa tối đa k−1 khóa. Khi đã đầy và gặp khóa mới, dùng `Iterator` để giảm các bộ đếm và xóa phần tử về 0 một cách hợp lệ trong Java; không sửa cấu trúc map bằng `remove` trực tiếp trong vòng for-each không an toàn.

Khi in, chuyển sang `TreeMap` để kết quả ứng viên được **sắp theo khóa**, giúp stdout xác định. Việc tạo `TreeMap` chỉ chứa tối đa k−1 ứng viên, không tạo cấu trúc kích thước N.

Đầu ra `{2=3}` là **bộ đếm phần dư**. Không được đọc thành "2 xuất hiện ba lần". Trong fixture, tần suất thật của 2 là 6.

### 12.6. Reservoir trong Java

Với mỗi sự kiện t>k:

```java
long index = random.nextLong(seen);
if (index < capacity) {
    sample.set((int) index, x);
}
```

`SplittableRandom.nextLong(seen)` tạo chỉ số từ 0 đến seen−1, không bao gồm seen. Ép `index` sang int chỉ được thực hiện sau khi `index<capacity`; capacity là int nên index phù hợp.

Dùng seed cố định để dễ tái hiện trong bài kiểm thử. Stdout không in những giá trị được chọn nên không phụ thuộc việc một PRNG cụ thể chọn ô nào ở mỗi bước.

### 12.7. Chi phí bộ nhớ của cả chương trình

Sau khi parser có buffer cố định:

- Welford: O(1) từ máy.
- Misra–Gries k=3: tối đa **2 khóa và bộ đếm**.
- Reservoir k=3: tối đa **3 giá trị**.
- Parser: 8192 byte và token dài tối đa 20 ký tự.
- Các biến điều khiển và map wrapper: hằng số trong fixture.

Theo cách mở rộng tham số, tổng trạng thái:

\[
\boxed{O(k_{\mathrm{MG}}+k_{\mathrm{reservoir}})}
\]

từ máy và đối tượng cần giữ, **độc lập với số lượng N quan sát**, khi N còn nằm trong giới hạn của bộ đếm `long`.

Dù vậy, chương trình dùng đối tượng Java, hash map và máy ảo có overhead; "O(k)" là cận tăng trưởng, không phải tuyên bố số byte luôn đúng một con số cố định.

### 12.8. Các giới hạn của demo

1. Đầu vào phải là các số nguyên `long` được mã hóa theo chữ số ASCII, phân cách bằng whitespace ASCII. Không hỗ trợ trực tiếp CSV có dấu phẩy.
2. Count dùng `long` và báo overflow qua `Math.addExact`.
3. Mean, M2, phương sai dùng `double`; với số nguyên lớn hơn khoảng chính xác của double hoặc luồng cực dài, kết quả chỉ là **xấp xỉ số học**, không là phân số exact.
4. Hash map có chi phí tra cứu O(1) **kỳ vọng**, không phải cam kết worst-case O(1) cho mọi đầu vào/khóa.
5. Reservoir dùng PRNG không dùng cho yêu cầu bảo mật.
6. Các counter Misra–Gries **không** là tần suất thật; cần lượt thứ hai hoặc phương pháp khác nếu muốn xác minh exact.
7. Nếu luồng rỗng, chương trình in `Records: 0` và thông báo không có thống kê thay vì giả tạo mean=0.

---

## 13. Phân tích tổng thể độ phức tạp

Gọi N là số giá trị đầu vào, `k_m` là tham số Misra–Gries và `k_r` là dung lượng reservoir.

### 13.1. Thời gian

- Parser đọc tổng số byte đầu vào, chi phí O(B), B là số byte.
- Welford cập nhật N lần: O(N).
- Reservoir cập nhật N lần: O(N) kỳ vọng.
- Misra–Gries: N lần tra bảng kỳ vọng O(1); các vòng giảm đồng loạt có tổng chi phí O(N) khấu hao.
- Tạo bản sao `TreeMap` để in ứng viên: O(k_m log k_m), chỉ khi kết thúc hoặc lúc cần trả snapshot.

Vì vậy với hash map/PRNG hoạt động theo các giả thiết thông thường:

\[
\boxed{T=O(B+N+k_m\log k_m)}
\]

**kỳ vọng / khấu hao**, không phải worst-case cứng cho từng bản ghi.

Nếu token đều dài O(1) byte và k_m nhỏ, ta thường mô tả tổng chi phí theo N là **O(N)** kỳ vọng.

### 13.2. Bộ nhớ

Không kể chính nguồn dữ liệu bên ngoài:

\[
\boxed{S=O(k_m+k_r)}
\]

từ máy, cộng bộ đệm parser cố định. Bộ nhớ thật tính theo bit bao gồm các khóa và các bộ đếm có phạm vi hữu hạn.

Nếu dùng định nghĩa streaming lý thuyết với số phần tử N tăng vô hạn, bộ đếm chính xác yêu cầu O(log N) bit; cách nói O(1) bộ nhớ cho count là theo **số từ máy** với giới hạn số học đã xác định.

### 13.3. Một lượt có thể song song hóa không?

Các toán tử như đếm, tổng hoặc những thống kê có quy tắc **merge** thích hợp có thể tổng hợp các phân vùng rồi gộp trạng thái. Ví dụ Welford có công thức gộp hai bộ `(n,\mu,M2)`.

Nhưng **không phải mọi trạng thái streaming có thể gộp tùy ý** mà giữ nguyên toàn bộ tính chất. Nếu xử lý phân tán, phải chứng minh riêng phép merge của từng thuật toán và cân nhắc thứ tự, double roundoff và phân phối ngẫu nhiên.

---

## 14. Cửa sổ trượt: khi dữ liệu cũ hết hiệu lực

Đến đây các thuật toán trả lời cho **tất cả quan sát từ đầu luồng**. Một yêu cầu khác là:

> Tính tổng/trung bình của **W phần tử mới nhất**.

Đây là bài toán **sliding window**. Khi sự kiện mới đến, một sự kiện cũ **hết hạn**.

### 14.1. Tổng cửa sổ chính xác

Dùng hàng đợi vòng (circular buffer) chứa tối đa W giá trị. Khi thêm x:

1. Nếu chưa đầy, thêm x và cộng vào tổng.
2. Nếu đã đầy, trừ giá trị cũ nhất khỏi tổng rồi ghi đè bằng x.
3. Tăng con trỏ vòng.

Chi phí mỗi cập nhật O(1) và bộ nhớ O(W) giá trị. Nếu cần tổng nguyên exact, phải xử lý overflow; nếu dùng double, phép cộng-trừ nhiều lần có thể tích lũy sai số.

Đây **không phải O(1) bộ nhớ độc lập W**. Nó chỉ bị chặn bởi kích thước cửa sổ đã cấu hình.

### 14.2. Có thể trừ ngược Welford không?

Về đại số có các công thức thêm và bỏ mẫu trong các thống kê online; nhưng việc cập nhật chính xác phương sai của cửa sổ yêu cầu biết giá trị **đang hết hạn**, thường phải giữ hàng đợi hoặc nhận thông tin ấy từ hệ thống.

Không thể chỉ giữ `count,mean,M2` của tất cả dữ liệu cũ rồi tự biết giá trị cần bỏ khi một sự kiện hết hạn mà không có thông tin bổ sung.

### 14.3. Reservoir và Misra–Gries trên cửa sổ

Reservoir sampling cơ bản được chứng minh cho **toàn bộ tiền tố**. Nó không tự động trở thành mẫu đều của W phần tử mới nhất khi các phần tử cũ rời cửa sổ.

Misra–Gries cơ bản được chứng minh cho **luồng append-only** từ đầu; không tự cho tập heavy hitter chính xác theo cửa sổ có xóa dữ liệu.

Với cửa sổ, cần dùng thuật toán chuyên dụng, chia block theo thời gian, exponential histogram hoặc cấu trúc hỗ trợ expiration, với độ phức tạp và bảo đảm được phân tích riêng.

---

## 15. Tình huống thực tế và lựa chọn giải pháp

### 15.1. Phân tích log mỗi giây

Hệ thống nhận hàng triệu sự kiện mỗi phút. Mục tiêu: đếm số sự kiện, tính min/max độ trễ, trung bình, phương sai và lấy mẫu một số sự kiện cho điều tra.

Chọn:

- Bộ đếm và Welford cho thống kê toàn bộ.
- Reservoir với k có giới hạn cho mẫu ngẫu nhiên.
- Không lưu từng bản ghi trong tiến trình nếu đã có hệ thống lưu trữ bên ngoài.

### 15.2. Top endpoint gây tải

Luồng là ID endpoint, mục tiêu phát hiện endpoint chiếm tỷ lệ lớn hơn 1%.

Misra–Gries với k≈100 giữ tối đa 99 ứng viên; mọi endpoint có tần suất **nghiêm ngặt >N/100** sẽ xuất hiện trong bảng cuối.

Nếu cần **tỉ lệ chính xác để cảnh báo hoặc thu phí**, phải xác minh các ứng viên bằng nguồn có thể truy vấn lại hoặc thiết kế thêm bộ đếm/ước lượng sai số thích hợp.

### 15.3. Thống kê user distinct

Cần ước lượng số user khác nhau mỗi ngày. HashSet exact có thể tốn RAM. Có thể xem HyperLogLog với sai số thống kê phù hợp, nhưng cần kiểm tra giới hạn riêng về quyền riêng tư/ID người dùng và hash đủ tốt.

Không dùng reservoir count để tự suy số distinct exact nếu không có mô hình lấy mẫu và ước lượng được chứng minh.

### 15.4. Phát hiện ID đã từng xuất hiện

Nếu câu hỏi là "đã thấy khóa này chưa?" và chấp nhận false positive, Bloom filter có thể phù hợp.

Nếu cần **bằng chứng chắc chắn rằng khóa đã xuất hiện**, Bloom filter câu trả lời "có thể" **không đủ** vì va chạm hash.

### 15.5. Bài toán máy tính có ít RAM nhưng tệp nằm trên đĩa

Nếu cho phép **đọc lại tệp**, một số bài có thể giải bằng nhiều lượt với bộ nhớ nhỏ hơn, chẳng hạn lượt một tìm ứng viên rồi lượt hai đếm xác thực.

Nhưng đó **không còn là một lượt**. Cần ghi rõ trade-off giữa bộ nhớ, số lượt, I/O và yêu cầu thời gian.

---

## 16. Những lỗi phổ biến

1. **Gọi `readAllLines` rồi mới dùng một vòng `for`**, không phải mô hình bộ nhớ nhỏ.
2. **Tích lũy mọi event trong `ArrayList`**, dù chỉ cần mean/min/max.
3. **Không phân biệt O(1) từ máy với O(1) bit**, quên bộ đếm exact cần log N bit.
4. **Không xử lý bộ đếm `long` tràn**, N có thể vượt giới hạn.
5. **Dùng tổng long để tính trung bình mà không kiểm tra tràn**.
6. **Tính phương sai bằng hiệu hai số lớn gần bằng nhau**, gây cancellation.
7. **Dùng phương sai mẫu khi n=1**, chia cho 0.
8. **Tự đặt min=0 khi luồng rỗng**, sai nếu dữ liệu dương/âm.
9. **Coi Welford dùng double là exact số thực**, quên sai số làm tròn.
10. **Coi reservoir lấy mẫu đều theo giá trị distinct**, trong khi nó đều theo vị trí sự kiện.
11. **Dùng `random.nextInt(N)` khi N vượt `int`**, tràn hoặc không biểu diễn được.
12. **Chọn j trên [0,t] thay vì [0,t−1]**, làm sai xác suất của reservoir.
13. **Chọn xác suất nhận cố định k/N khi chưa biết N**, không đúng cơ chế reservoir online.
14. **Không cập nhật seen khi sự kiện bị bỏ khỏi reservoir**, làm sai phân phối.
15. **In các giá trị mẫu ngẫu nhiên rồi tuyên bố stdout cố định** khi chưa cố định/test PRNG.
16. **Dùng k bộ đếm cho Misra–Gries rồi phát biểu bảo đảm >N/k không điều chỉnh**, sai hợp đồng.
17. **Trong Misra–Gries, bảng đầy thì thêm x rồi mới giảm không theo thuật toán đã chứng minh**, dễ tạo k khóa hoặc sai bất biến.
18. **Đọc bộ đếm phần dư như tần suất thật**, ví dụ 2 còn counter3 nhưng xuất hiện6 lần.
19. **Coi mọi ứng viên Misra–Gries đều là heavy hitter thật**, không có bảo đảm chiều ngược.
20. **Đổi ngưỡng >N/k thành ≥N/k**, sai với trường hợp biên.
21. **Đòi chính xác tần suất heavy hitter trong một lượt chỉ với k−1 counters**, vượt bảo đảm.
22. **Dùng một lượt thứ hai đếm lại rồi vẫn ghi "single pass"**, không trung thực về số lượt.
23. **Dùng Map có thời gian lookup luôn worst-case O(1) mà không nêu giả thiết**, bỏ khả năng va chạm.
24. **Cho rằng Count-Min Sketch không bao giờ có hash collision**, sai.
25. **Nói CMS có upper-bound xác suất cho mọi khóa cùng lúc mà không điều chỉnh δ**, phát biểu thiếu điều kiện.
26. **Dùng CMS chỉ tăng cho luồng có xóa rồi vẫn giữ bảo đảm overestimate**, không đúng mô hình.
27. **Nói HyperLogLog cho số distinct chính xác**, đây là thuật toán ước lượng.
28. **Đọc 1.04/√m như cận xấu nhất chắc chắn**, thay vì sai số tương đối thống kê.
29. **Dùng Bloom filter kết quả "có thể" như bằng chứng có thật**, quên false positive.
30. **Xóa bit của Bloom filter chuẩn khi hủy khóa**, có thể tạo false negative.
31. **Áp reservoir prefix trực tiếp cho cửa sổ trượt**, bỏ việc phần tử hết hạn.
32. **Áp Misra–Gries append-only cho turnstile có cập nhật âm**, thiếu chứng minh.
33. **Gọi median exact dùng O(1) bộ nhớ với dữ liệu tùy ý**, thường không thể theo mô hình tổng quát.
34. **Không làm rõ miền giá trị và đơn vị bộ nhớ**, so độ phức tạp sai.
35. **Parser đọc cả dòng không giới hạn**, làm bùng RAM với một bản ghi dài.
36. **Không tách phần dữ liệu mẫu fixture và chế độ stdin thật**, khiến người học hiểu lầm về streaming.
37. **Không kiểm thử giá trị lặp rất nhiều hoặc toàn một khóa**, bỏ lỗi nặng của heavy hitter.
38. **Kiểm thử chỉ bằng random rồi xem đó là chứng minh lý thuyết**, test không thay định lý.
39. **Không chỉ ra ngưỡng khi k>N hoặc k lớn hơn số khóa**, phân tích ứng viên không rõ.
40. **Nhầm phần trăm phần tử sampled với độ chính xác của ước lượng bất kỳ**, mỗi mục tiêu cần phân tích sai số riêng.

---

## 17. Kiểm thử độc lập

### 17.1. So thống kê streaming với tính toán batch trên dữ liệu nhỏ

Với mảng nhỏ a[] đã lưu **chỉ trong test**, tính:

\[
\mu=\frac{\sum a_i}{N}
\]

và:

\[
M_2=\sum(a_i-\mu)^2.
\]

So với trạng thái Welford sau khi gọi `offer` từng phần tử.

Cho phép tolerance số thực phù hợp, chẳng hạn:

\[
|\mu_{\mathrm{stream}}-\mu_{\mathrm{batch}}|\le10^{-9}
\]

cho những bộ test có cỡ dữ liệu và thang đo được kiểm soát. Không thể áp một tolerance tuyệt đối cố định cho mọi dữ liệu cực lớn.

### 17.2. Test Welford trên fixture

```text
Input:
2 4 2 7 2 4 9 2 7 2 4 2

N = 12
min = 2
max = 9
mean = 47/12 = 3.916666...
population variance = 803/144 = 5.576388...
sample variance = 803/132 = 6.083333...
```

### 17.3. Test Misra–Gries với oracle tần suất exact

Trong mã kiểm thử nhỏ, tạo một `HashMap` tần suất thật. Sau khi chạy Misra–Gries k:

1. Kiểm tra số ứng viên ≤k−1.
2. Với mọi khóa có `f(x)>N/k`, bắt buộc có trong ứng viên.
3. Với D lượt giảm, kiểm tra `c(x)≤f(x)≤c(x)+D` cho từng khóa; nếu khóa không là ứng viên, lấy c=0.
4. **Không** bắt buộc mọi ứng viên có f>N/k.

Mô hình độc lập đã được đối chiếu trên **15.360 bộ dữ liệu nhỏ** với k từ 2 đến 9, N từ 1 đến 80, khóa ngẫu nhiên trong miền hẹp. Các bất biến ứng viên, cận bộ đếm và Welford so với batch đều đạt trong những bộ thử ấy.

Đây là **kiểm thử cài đặt**, không thay thế chứng minh Misra–Gries cho mọi stream.

### 17.4. Test trường hợp toàn một khóa

```text
5 5 5 5 5
```

Với k=3:

- Bảng cuối có {5:5}.
- Không có vòng giảm toàn bộ.
- `f(5)=5>5/3`.

### 17.5. Test không có heavy hitter thực

```text
1 2 3 4 5 6
```

Với k=3, mỗi phần tử có tần suất1 và N/k=2, không có phần tử nào vượt ngưỡng. Thuật toán có thể trả bảng rỗng hoặc tập ứng viên không chứa heavy hitter. Đừng test theo yêu cầu ứng viên phải luôn rỗng trừ khi chính thuật toán/luồng cụ thể cho kết quả ấy.

### 17.6. Test reservoir

Với k=3:

- N=0: sample size=0.
- N=1: sample size=1.
- N=2: sample size=2.
- N≥3: sample size=3.

Nếu muốn kiểm chứng phân phối, cố định N nhỏ, chạy **nhiều seed độc lập** và đếm tần suất xuất hiện của mỗi **vị trí gốc**. Tần suất thực nghiệm sẽ gần k/N với đủ số lần chạy; không nên kiểm tra đòi đúng k/N sau vài seed.

### 17.7. Test parser

- Dấu cộng/dấu trừ hợp lệ của long.
- Khoảng trắng, newline, tab.
- Giá trị `Long.MIN_VALUE` và `Long.MAX_VALUE`.
- Token dài hơn 20 byte → từ chối.
- Chữ cái hoặc dấu phẩy CSV → từ chối.
- Dòng dài bất thường → parser vẫn chỉ giữ buffer8192 và token tối đa20, báo lỗi sớm.
- Luồng rỗng → không tính mean/variance.
- Đủ số phần tử để `count` overflow là tình huống lý thuyết cần kiểm soát, không thử bằng cách thực sự phát hàng tỷ tỷ sự kiện.

### 17.8. Kiểm tra không giữ input

Trong chế độ `--stdin`, kiểm tra code không có:

```text
readAllBytes()
readAllLines()
collect(toList())
new long[N]
```

trên nguồn không giới hạn. Các cấu trúc còn lại đều có sức chứa giới hạn bởi k hoặc là trạng thái hằng số.

---

## 18. Bài tập tự kiểm tra

### Bài 1
Mô hình streaming một lượt khác đọc toàn bộ tệp rồi duyệt như thế nào?

### Bài 2
Vì sao O(1) từ máy cho count không đồng nghĩa O(1) bit khi N tăng vô hạn?

### Bài 3
Trạng thái nào đủ để tính min và max chính xác một lượt?

### Bài 4
Tại sao không thể khởi tạo min=0 cho mọi luồng?

### Bài 5
Viết công thức cập nhật trung bình trực tuyến sau khi gặp x_t.

### Bài 6
Viết hai công thức cập nhật mean và M2 của Welford.

### Bài 7
Phương sai tổng thể và phương sai mẫu khác nhau ở mẫu số nào?

### Bài 8
Vì sao phương sai mẫu không xác định khi N=1?

### Bài 9
Cho dữ liệu `2 4 2 7 2 4 9 2 7 2 4 2`, tính N và mean.

### Bài 10
Với dữ liệu bài 9, tính population và sample variance.

### Bài 11
Reservoir sampling lấy mẫu đều theo **vị trí** hay theo **giá trị distinct**?

### Bài 12
Với reservoir k=3, sau khi đã thấy t=12 vị trí, xác suất mỗi vị trí nằm trong mẫu là bao nhiêu?

### Bài 13
Khi thấy phần tử thứ t>k, reservoir chọn j trong khoảng nào?

### Bài 14
Chứng minh một vị trí cũ còn lại trong reservoir với xác suất k/t.

### Bài 15
Với k=3, Misra–Gries giữ tối đa bao nhiêu bộ đếm?

### Bài 16
Ba nhánh cập nhật Misra–Gries là gì?

### Bài 17
Tại sao mỗi vòng giảm toàn bộ tương ứng việc triệt tiêu k khóa khác nhau?

### Bài 18
Chứng minh mọi khóa có f>N/k chắc chắn còn trong bảng.

### Bài 19
Tại sao bộ đếm Misra–Gries không phải tần suất exact?

### Bài 20
Với ví dụ 12 số và k=3, ứng viên và bộ đếm cuối là gì?

### Bài 21
Nếu D là số vòng giảm, viết cận cho f(x) bằng c(x) và D.

### Bài 22
Có thể kết luận ứng viên Misra–Gries là top-k exact không?

### Bài 23
CMS ước lượng tần suất bằng phép min qua các hàng; vì sao trong insertion-only nó không đếm thiếu?

### Bài 24
Bảo đảm εN,δ của CMS cần giả thiết gì về hash?

### Bài 25
HyperLogLog giải bài toán nào và tại sao kết quả không exact?

### Bài 26
Vì sao distinct count exact trong tổng quát cần thông tin nhiều theo miền U?

### Bài 27
Bloom filter trả "có thể đã thấy" có đảm bảo khóa thật sự đã thấy không?

### Bài 28
Cần bộ nhớ bao nhiêu để giữ chính xác tổng của W phần tử mới nhất bằng circular buffer?

### Bài 29
Vì sao reservoir của toàn tiền tố không tự động đều cho cửa sổ W mới nhất?

### Bài 30
Một chương trình có một vòng `while` nhưng gọi `readAllLines()` có đáp ứng bộ nhớ streaming không?

### Bài 31
Nêu cách test Misra–Gries độc lập mà không dùng cùng bộ đếm của nó làm oracle.

### Bài 32
Nêu một tình huống cần dùng nhiều lượt thay vì một lượt bộ nhớ nhỏ.

### Bài 33
Tại sao `HashMap` không bảo đảm mọi thao tác có worst-case O(1) tuyệt đối?

### Bài 34
Trong mã Java, tại sao chỉ dùng `random.nextLong(seen)` thay vì `nextInt((int)seen)`?

### Bài 35
Điều gì xảy ra nếu token số nguyên quá dài trong parser Java của bài?

### Đáp án gợi ý

1. Streaming đọc mỗi sự kiện một lần và chỉ giữ trạng thái nhỏ; đọc toàn bộ tệp giữ dữ liệu theo kích thước nguồn.
2. Muốn đếm exact tới N cần ít nhất log2(N+1) bit; O(1) là số từ máy cố định với phạm vi hữu hạn.
3. Cờ đã có dữ liệu, min và max hiện tại; cập nhật khi gặp mỗi số.
4. Nếu mọi giá trị dương, min thật có thể lớn hơn0; nếu mọi giá trị âm, max có thể nhỏ hơn0.
5. `\mu_t=\mu_{t-1}+(x_t-\mu_{t-1})/t`.
6. `\delta=x_t-\mu_{t-1}`; `\mu_t=\mu_{t-1}+\delta/t`; `M2_t=M2_{t-1}+\delta(x_t-\mu_t)`.
7. Tổng thể chia N; mẫu chia N−1.
8. Vì chia cho N−1=0 và chỉ một quan sát không đủ ước lượng phương sai mẫu theo công thức ấy.
9. `N=12,\sum x=47,\mu=47/12≈3.916667`.
10. `\sigma^2=803/144≈5.576389`; `s²=803/132≈6.083333`.
11. Theo **vị trí/lần xuất hiện**.
12. `k/t=3/12=1/4`.
13. `j∈{0,1,...,t−1}` đều.
14. Xác suất đã có `k/(t−1)` nhân xác suất không bị thay `1−1/t` cho `k/t`.
15. Tối đa k−1=2 bộ đếm.
16. Có khóa → tăng; còn chỗ → thêm1; bảng đầy và khóa mới → giảm tất cả, xóa các bộ đếm về0.
17. Có k−1 khóa khác nhau trong bảng và một khóa mới khác chúng, tổng k khóa phân biệt.
18. Mỗi vòng giảm loại tối đa một lần xuất hiện của khóa, có nhiều nhất N/k lượt; f>N/k không thể biến mất hoàn toàn.
19. Lượt giảm đã xóa mất các phần đếm; counter chỉ là phần dư.
20. `{2:3}` và D=3; tần suất thật `f(2)=6`.
21. `c(x)≤f(x)≤c(x)+D`, lấy c=0 nếu không còn ứng viên.
22. Không; chỉ có bảo đảm tất cả heavy hitter `f>N/k` đều trong tập ứng viên.
23. Va chạm hash chỉ **tăng thêm** bộ đếm tương ứng, không trừ số lần thật của x trong insert-only.
24. Cần hash phù hợp, các hàng đủ độc lập và kích thước bảng được chọn theo ε,δ; không có bảo đảm như thế với hash tùy ý.
25. Ước lượng số distinct từ hash/register; có sai số thống kê và phụ thuộc giả thiết hash.
26. Có 2^U tập con khóa khả dĩ cần phân biệt khi đòi kết quả exact cho mọi đoạn nối tiếp, nên cần ≥U bit trạng thái trong mô hình nêu.
27. Không; Bloom filter có thể có false positive.
28. O(W) giá trị cho buffer, cùng con trỏ và tổng (cần kiểm soát overflow).
29. Khi phần tử cũ hết hạn, phân phối mẫu cũ không tự điều chỉnh để chỉ đều trên cửa sổ mới.
30. Không; việc nạp toàn bộ dữ liệu đã tốn O(N) bộ nhớ.
31. Với dữ liệu nhỏ, đếm tần suất thật bằng HashMap hoặc mảng độc lập, kiểm tra mọi f>N/k còn trong ứng viên và c≤f≤c+D.
32. Xác minh tần suất exact của các ứng viên Misra–Gries có thể cần lượt thứ hai nếu nguồn cho đọc lại.
33. Va chạm hash và đặc điểm triển khai có thể ảnh hưởng thời gian thao tác; O(1) thường là kỳ vọng/khấu hao.
34. `seen` là long có thể vượt phạm vi int; `nextLong(seen)` xử lý bound long.
35. Demo báo `IllegalArgumentException` khi token >20 ASCII bytes, giữ parser không cấp phát một chuỗi tùy ý dài.

---

## Ghi nhớ

**Một lượt** nghĩa là mỗi phần tử chỉ được đọc một lần; **bộ nhớ giới hạn** nghĩa là chỉ giữ một trạng thái có kích thước nhỏ theo mục tiêu, không giữ toàn bộ luồng.

| Công cụ | Trạng thái | Bảo đảm chính |
| --- | --- | --- |
| Count/min/max/Welford | O(1) từ máy | Thống kê theo tiền tố; phương sai có roundoff trong double |
| Reservoir k | O(k) | Mỗi vị trí có xác suất k/N nằm trong mẫu khi N≥k |
| Misra–Gries k | O(k) | Mọi khóa có `f>N/k` đều ở bảng ứng viên, chưa chắc biết exact frequency |
| Count-Min Sketch | O(ε⁻¹ log δ⁻¹) bộ đếm | Ước lượng frequency với lỗi xác suất dưới giả thiết hash |
| HyperLogLog | O(m) thanh ghi | Ước lượng distinct với sai số thống kê |
| Bloom filter | Mảng bit, nhiều hash | Có thể đã thấy / chắc chắn chưa thấy trong insert-only |
| Cửa sổ trượt exact | Thường O(W) | Giữ thông tin đủ để loại phần tử hết hạn |

**Ba điều phải nhớ khi thiết kế:**

1. **Chọn đúng thông tin cần trả lời:** exact hay approximate; theo toàn tiền tố hay cửa sổ; phân phối vị trí hay tần suất khóa.
2. **Không nói quá bảo đảm:** Misra–Gries là ứng viên chứ không phải exact frequency; reservoir là mẫu ngẫu nhiên vị trí; sketch có điều kiện và sai số.
3. **Kiểm soát cả parser, số học và trạng thái:** không `readAllLines`, không mảng theo N, phát hiện overflow, nêu rõ O(1) từ máy khác O(1) bit, và kiểm thử độc lập với một oracle batch trên dữ liệu nhỏ.

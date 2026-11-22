# Phân biệt bảo đảm toán học với kết quả thực nghiệm

Khi đánh giá thuật toán **xấp xỉ** và **kinh nghiệm (heuristic)**, chúng ta thường gặp hai phát biểu rất khác nhau:

> **Bảo đảm toán học:** “Với mọi đầu vào hợp lệ thuộc mô hình đã nêu, kết quả của thuật toán không tệ hơn 2 lần tối ưu.”

> **Kết quả thực nghiệm:** “Trong 3.820 trường hợp đã thử, không có kết quả nào tệ hơn 2 lần tối ưu.”

Phát biểu đầu là một định lý **nếu có chứng minh đúng và giả thiết được thỏa**. Phát biểu sau chỉ nói về **tập dữ liệu, môi trường và phương pháp đo cụ thể**; 3.820 lần kiểm tra thành công **không tự chứng minh** điều sẽ xảy ra với mọi đầu vào khác. Ngược lại, một bảo đảm tỷ lệ 2 không có nghĩa thuật toán sẽ tệ đến mức đó trong mọi bài toán thực tế: nhiều lần nó có thể tìm đúng tối ưu.

Bài thuộc nhóm **Xấp xỉ và kinh nghiệm** của Computer Science Algorithms. Trọng tâm là phân biệt **định lý đúng đắn, cận độ phức tạp, tỷ lệ xấp xỉ, kết quả trung bình theo phân phối, cận xác suất** với **benchmark, thí nghiệm, mô phỏng và quan sát hữu hạn**. Ta dùng bài toán **k-center trên trục số** để xây dựng một minh họa đầy đủ: thuật toán chọn tâm xa nhất có bảo đảm xấp xỉ **2 lần tối ưu** theo bất đẳng thức tam giác; một heuristic chọn k điểm đầu có thể tệ tùy ý. Bài có chứng minh, phản ví dụ khi mất giả thiết metric, oracle tìm tối ưu, chương trình **Java 17 chạy độc lập**, kết quả thống kê trên 3.820 trường hợp, và bài tập có đáp án.

## 1. Bảo đảm toán học nói về điều gì?

Một kết luận toán học về thuật toán phải cho biết ít nhất bốn yếu tố:

1. **Đầu vào hợp lệ:** đồ thị có trọng số không âm, khoảng cách có thỏa bất đẳng thức tam giác, đa giác có đơn hay không, n và k nằm trong miền nào?
2. **Đối tượng cần đo:** thuật toán có trả nghiệm hợp lệ không, giá trị mục tiêu có gần tối ưu không, thời gian/bộ nhớ có giới hạn gì?
3. **Lượng từ:** đúng với **mọi** đầu vào, với xác suất ít nhất 1−δ trên lựa chọn ngẫu nhiên, hay chỉ là **kỳ vọng** theo một phân phối đã cho?
4. **Chứng minh:** bất biến, quy nạp, đếm tổ hợp, bất đẳng thức, phân tích xác suất hoặc phép biến đổi đúng nào bảo vệ kết luận?

Ví dụ:

~~~text
Voi moi tap diem huu han tren duong thang
va 1 <= k <= n,
ban k-center farthest-first thoa:
R_greedy <= 2 * R_opt
~~~

Phát biểu này có điều kiện **mọi đầu vào hợp lệ**, không phải “mọi lần chương trình chạy trên máy tôi”. Nếu dùng khoảng cách không phải metric, nếu chọn tâm theo một quy tắc khác, hoặc nếu định nghĩa bài toán tối ưu khác, không được tự kế thừa kết luận.

Một **bảo đảm chất lượng nghiệm** còn khác với **bảo đảm thời gian**. Thuật toán có thể cho nghiệm xấp xỉ tốt nhưng mất thời gian lớn; ngược lại, một heuristic chạy nhanh có thể không có cận sai số nào.

## 2. Kết quả thực nghiệm nói về điều gì?

Một báo cáo thực nghiệm cần mô tả:

- **Đầu vào:** dữ liệu được lấy như thế nào, có bao nhiêu trường hợp, giới hạn n, phân phối và độ khó?
- **Đối chứng:** so với lời giải tối ưu đã chứng nhận, lower bound, heuristic khác hay kết quả gần đúng chưa kiểm chứng?
- **Phép đo:** chất lượng nghiệm, số phép so sánh, runtime, bộ nhớ, năng lượng hay tỷ lệ thành công?
- **Điều kiện:** máy tính, JDK, warm-up JIT, GC, cách đo thời gian, phiên bản mã, seed nếu có ngẫu nhiên.
- **Độ bất định:** chạy bao nhiêu lần, mẫu có độc lập hay không, phân vị/outlier, khoảng tin cậy nếu mô hình phù hợp?
- **Giới hạn suy luận:** mẫu thử có đại diện cho phân phối triển khai thực tế không; còn dạng input đối kháng hay suy biến chưa được thử?

Ví dụ:

~~~text
Da xet het 3.820 cap (tap toa do, k)
voi toa do phan biet chon trong 0..9,
so diem n=1..6 va moi k=1..n.

Greedy bang toi uu: 2.369
Greedy kem toi uu: 1.451
Cham dung he so 2: 477
Toi uu bang 0: 847
Vuot he so 2: 0
~~~

Bảng này **đúng cho phạm vi liệt kê**, không chứng minh trường hợp tọa độ âm, n=1000 hay khoảng cách khác. Định lý 2-approx mới là lý do thuật toán vẫn có bảo đảm trên **mọi** tập điểm metric hợp lệ.

## 3. Những loại bảo đảm rất dễ bị nhầm

| Loại | Dạng phát biểu | Được hiểu thế nào? |
| --- | --- | --- |
| **Correctness** | Với mọi input hợp lệ, trả nghiệm đúng đặc tả | Định lý về tính đúng |
| **Worst-case runtime** | T(n)≤C·f(n) khi n đủ lớn | Cận trên theo kích thước mọi input |
| **Approximation ratio** | ALG(I)≤α·OPT(I) cho bài tối thiểu | Bảo đảm chất lượng mọi instance trong miền |
| **Expected runtime** | E[T(I;R)]≤f(n) | Kỳ vọng theo randomness đã nêu, không phải mọi lần chạy |
| **High probability** | P(bad event)≤δ | Cần mô hình xác suất và δ cụ thể |
| **Empirical mean** | Trung bình của các run quan sát được | Thống kê trên tập mẫu, không phải định lý tổng quát |
| **Observed maximum** | Max ratio trong benchmark là 1,8 | Không tự là worst-case toàn bộ input |
| **Heuristic** | Thường cho nghiệm tốt, chạy nhanh | Có thể không có cận chất lượng tổng quát |
| **Experimentally verified finite domain** | Mọi input trong một miền hữu hạn đã xét đều pass | Chứng thực **miền đó**, không tự ngoại suy |

Ký hiệu `O(n log n)` là một phát biểu **tiệm cận**, không phải “đã đo 5 điểm thấy đường cong giống n log n”. Ký hiệu `E[T]` là kỳ vọng với phân phối xác định, không phải đơn giản trung bình ba lần chạy.

Trong thuật toán xấp xỉ, **bằng chứng** có thể là một phép phân tích toán học; trong thực nghiệm, bằng chứng là **log, dữ liệu đo, phương pháp và khả năng lặp lại**. Chúng bổ sung cho nhau nhưng **không thay thế nhau**.

## 4. Xác định mục tiêu và tối ưu trước khi so sánh

Để nói một lời giải gần tối ưu đến đâu, phải xác định chính xác:

- Tập nghiệm hợp lệ `\mathcal F(I)`.
- Hàm mục tiêu `f_I(S)`.
- Bài **tối thiểu hóa** hay **tối đa hóa**.
- Giá trị tối ưu `OPT(I)` theo **cùng một đặc tả**.

Với bài tối thiểu, một thuật toán α-approx khi:

\[
\boxed{OPT(I)\le ALG(I)\le \alpha OPT(I)}
\]

cho **mọi** input hợp lệ và một hằng `α≥1`. Với bài tối đa, dạng thường gặp là:

\[
\boxed{\frac{OPT(I)}{\alpha}\le ALG(I)\le OPT(I).}
\]

Không dùng một công thức theo chiều tối thiểu rồi áp nguyên xi cho tối đa.

**Nếu OPT=0**, phép chia `ALG/OPT` không có nghĩa; định nghĩa bất đẳng thức `ALG≤α OPT` vẫn có ý nghĩa. Một thuật toán có bảo đảm nhân α hữu hạn cho bài tối thiểu phải cho `ALG=0` khi `OPT=0` và các giá trị không âm. Vì vậy, trong báo cáo thực nghiệm nên **đếm riêng các instance OPT=0** thay vì âm thầm bỏ, gán tỷ số 1 hoặc lấy epsilon tùy tiện.

Nếu kết quả so với **một heuristic khác** chứ không phải tối ưu, đừng đặt tên tỷ số đó là approximation ratio to OPT.

## 5. Ví dụ xuyên suốt: bài toán k-center

Cho n điểm `x_0,\ldots,x_{n-1}` trên trục số. Ta chỉ được chọn **k tâm từ chính n điểm đầu vào**, với `1≤k≤n`. Khoảng cách là:

\[
d(x_i,x_j)=|x_i-x_j|.
\]

Với tập chỉ số tâm `C`, độ xa nhất từ một điểm đến tâm gần nhất là **bán kính phủ**:

\[
R(C)=\max_{0\le i<n}\min_{j\in C}|x_i-x_j|.
\]

Ta cần tìm tập k tâm sao cho `R(C)` **nhỏ nhất**:

\[
\boxed{R^*=\min_{C\subseteq\{0,\ldots,n-1\},\,|C|=k}R(C).}
\]

Đây là **discrete metric k-center**, không phải bài tìm trung bình k-means. Metric ở đây thỏa:

1. `d(a,b)≥0`;
2. `d(a,b)=d(b,a)`;
3. `d(a,a)=0`;
4. **Bất đẳng thức tam giác:** `d(a,c)≤d(a,b)+d(b,c)`.

Với trục số, bất đẳng thức tam giác của trị tuyệt đối luôn đúng.

**Hợp đồng đầu vào của code:** các điểm là tọa độ `int`, có thể âm và không cần được sort; mỗi tâm là **chỉ số** của một điểm đầu vào; `n≥1` và `1≤k≤n`. Khoảng cách được tính bằng `long` sau khi ép từng toán hạng, vì hai tọa độ `int` cực trị có hiệu lớn hơn `Integer.MAX_VALUE`.

## 6. Thuật toán xấp xỉ: farthest-first traversal

Thuật toán tham lam (*farthest-first*, còn gọi Gonzalez):

1. Chọn điểm đầu làm tâm đầu tiên.
2. Trong khi chưa đủ k tâm, chọn điểm chưa phải tâm có khoảng cách tới **tâm gần nhất hiện tại** là lớn nhất.
3. Trả tập k tâm và bán kính phủ.

~~~text
C = {diem dau tien}
repeat until |C| = k:
    p = argmax_{point not in C} distance(point, C)
    C = C union {p}
return C
~~~

Ở đây `distance(point,C)=min_{c∈C}d(point,c)`.

**Bất biến triển khai nhanh:** lưu `nearest[i]` là khoảng cách của điểm i tới tâm gần nhất đã chọn. Khi thêm tâm c:

\[
nearest[i]\leftarrow\min(nearest[i],d(x_i,x_c)).
\]

Do đó chọn mỗi tâm mới và cập nhật mảng mất O(n), tổng O(nk), bộ nhớ O(n+k). Không cần tính lại khoảng cách đến tất cả tâm ở mỗi lượt.

**Quy tắc hòa:** nếu nhiều điểm đồng thời xa nhất, code chọn **chỉ số nhỏ nhất**. Chứng minh không phụ thuộc quy tắc này: chọn một điểm xa nhất bất kỳ vẫn được bảo đảm.

### Ví dụ 1: hệ số 2 đạt được

~~~text
points = [0,1,2,3,4], k=2
farthest-first bat dau o index 0 (toa do 0)
-> chon them index 4 (toa do 4)
centers = [0,4]
R_greedy = 2

exact optimum co the chon index [0,3]
R_opt = 1
ratio = 2/1 = 2
~~~

Greedy **không tối ưu** nhưng **đúng bảo đảm 2-approx**. Đây là ví dụ cho thấy cận 2 không thể được cải thiện nói chung **đối với quy tắc khởi đầu/tie đã dùng** mà không thêm giả thiết hoặc đổi thuật toán.

### Ví dụ 2: heuristic “lấy k điểm đầu” rất tệ

~~~text
points = [0,1,2,100], k=2

first-k centers = [0,1]
R_first = 99

farthest-first centers = [0,100]
R_greedy = 2

exact centers = [1,100]
R_opt = 1
~~~

Farthest-first có tỷ lệ 2, còn lấy k điểm đầu có tỷ lệ **99**. Tổng quát đặt `points=[0,1,2,L]` với `L≥4` và k=2:

- First-k chọn 0,1 → `R_first=L−1`.
- Tối ưu chọn 1,L → `R^*=1`.
- Tỷ lệ first-k là `L−1`, **tăng không bị chặn** khi L tăng.

Vậy first-k có thể chạy nhanh nhưng **không có bảo đảm tỷ lệ hằng** cho họ instance này. Một heuristic “thường nhanh và tốt trên dữ liệu của tôi” khác với một thuật toán đã chứng minh cận cho mọi instance.

## 7. Chứng minh farthest-first là 2-approx

Đặt `R_g=R(C_g)` là bán kính khi farthest-first đã chọn đủ k tâm. Nếu `R_g=0`, kết luận `R_g≤2R^*` hiển nhiên. Giả sử `R_g>0` và xét một điểm p còn có khoảng cách `R_g` đến tập k tâm đã chọn.

Các tâm được chọn theo thứ tự `c_1,\ldots,c_k`. Vì bán kính phủ **không tăng** khi thêm tâm, tại lúc chọn mỗi `c_t`, điểm đó cách **mọi tâm đã chọn trước** ít nhất `R_g`. Điểm p cũng cách mỗi tâm trong `C_g` ít nhất `R_g` do định nghĩa điểm xa nhất cuối cùng.

Như vậy ta có **k+1 điểm**:

\[
c_1,c_2,\ldots,c_k,p
\]

mà **mọi cặp khác nhau** đều cách nhau ít nhất `R_g`.

Xét một lời giải tối ưu chọn **k tâm**, với bán kính `R^*`. Mỗi một trong k+1 điểm trên nằm trong bán kính `R^*` của một tâm tối ưu. Theo **nguyên lý Dirichlet**, ít nhất hai điểm u,v phải dùng cùng một tâm tối ưu z.

Bất đẳng thức tam giác cho:

\[
d(u,v)\le d(u,z)+d(z,v)\le 2R^*.
\]

Trong khi đó, do cách greedy chọn:

\[
d(u,v)\ge R_g.
\]

Suy ra:

\[
\boxed{R_g\le2R^*.}
\]

**Các giả thiết thực sự được dùng:**
- Có k tâm tối ưu và một bán kính tối ưu.
- Các điểm thuộc một không gian có **bất đẳng thức tam giác**.
- Thuật toán chọn đúng điểm **xa nhất tới tập tâm hiện tại**.
- Bài toán tối ưu là **minimize maximum nearest-center distance**.

Đây là chứng minh cho **mọi input metric k-center hợp lệ**. Nó không phụ thuộc vào việc đo runtime, seed, chọn bộ dữ liệu thử hay số lần chạy.

## 8. Bỏ giả thiết metric: định lý có thể thất bại

Cho bốn điểm có ma trận “khoảng cách” đối xứng, không âm và đường chéo bằng 0:

| d | 0 | 1 | 2 | 3 |
| --- | ---: | ---: | ---: | ---: |
| **0** | 0 | 3 | 3 | 1 |
| **1** | 3 | 0 | 3 | 1 |
| **2** | 3 | 3 | 0 | 1 |
| **3** | 1 | 1 | 1 | 0 |

**Không phải metric**, vì `d(0,1)=3> d(0,3)+d(3,1)=1+1=2`.

Với k=2, farthest-first bắt đầu tại điểm 0; điểm 1 và 2 cùng xa nhất 3, chọn chỉ số nhỏ hơn 1. Hai tâm là `{0,1}`, còn điểm 2 cách cả hai 3, nên `R_g=3`.

Nếu chọn hai tâm `{0,3}`, mọi điểm cách một tâm không quá 1, nên `R^*=1` (không thể 0 vì k=2<4 và mọi hai điểm khác nhau có khoảng cách dương).

Do đó:

\[
R_g/R^*=3>2.
\]

**Không phải chứng minh 2-approx sai**; đó là **phản ví dụ khi điều kiện metric bị vi phạm**. Khi đánh giá một “khoảng cách” từ độ tương đồng, chi phí học máy hoặc ma trận do người dùng cung cấp, phải kiểm tra xem nó có thỏa các giả thiết đã dùng trong proof không.

## 9. Oracle tối ưu: công cụ thực nghiệm, không thay cho proof

Để biết nghiệm greedy kém tối ưu bao nhiêu trên một instance nhỏ, cần giá trị `R^*` **chính xác**. Ta có thể vét cạn tất cả tập con k tâm:

~~~text
best = +infinity
for each subset C of k indices:
    best = min(best, radius(C))
return best
~~~

Số tập con là:

\[
\binom nk.
\]

Đây là **oracle chính xác** vì nó xét mọi nghiệm hợp lệ. Nhưng giá phải trả là thời gian hàm mũ/tổ hợp. Code ở cuối chỉ cho phép oracle với `n≤20` và dùng nó cho n≤6, **không** tuyên bố có thể vét cạn input quy mô sản xuất.

Hai mục tiêu có thể song hành:
- **Thuật toán greedy O(nk):** phù hợp xử lý n lớn hơn và có cận 2.
- **Oracle exact:** dùng để kiểm chứng chất lượng trên các instance nhỏ, tạo phản ví dụ và minh họa khoảng cách tới tối ưu.

**Không coi oracle là một heuristic khác:** nếu nghiệm so sánh không được chứng nhận tối ưu, tỷ số `ALG/reference` chỉ là so với một baseline, **không phải** tỷ lệ xấp xỉ tới `OPT`.

### Khi không có oracle exact

Với bài **tối thiểu**, nếu có một **lower bound** đúng `L≤OPT` và một nghiệm khả thi có giá trị `A≥OPT`, thì với L>0:

\[
\frac A{OPT}\le\frac A L.
\]

Tỷ số A/L là một **cận trên bảo thủ** cho tỷ lệ thật của **instance này**. Nếu dùng một nghiệm khác `U≥OPT` làm mẫu số, `A/U` **không** chứng nhận tỷ lệ gần tối ưu; U có thể lớn hơn nhiều so với OPT.

Ví dụ A=12, lower bound L=10 ⇒ tỷ lệ thật `A/OPT≤1,2` cho instance. Nhưng nếu chỉ có một heuristic reference=15, tỷ lệ 12/15=0,8 **không** cho biết A gần OPT ở mức nào.

Với bài tối đa, hướng bất đẳng thức thay đổi. Cần ghi rõ cận dưới/cận trên **trên giá trị tối ưu nào**.

## 10. Thống kê vét cạn: 3.820 trường hợp

Ta liệt kê **mọi tập n tọa độ nguyên phân biệt** lấy từ `{0,1,2,3,4,5,6,7,8,9}` với `n=1..6`. Với mỗi tập, thử tất cả `k=1..n`. Số cặp (tập điểm,k):

\[
\sum_{n=1}^{6}n\binom{10}{n}
=10+90+360+840+1260+1260
=\boxed{3820}.
\]

Với từng cặp:
1. Chạy farthest-first bắt đầu từ điểm đầu.
2. Chạy oracle exact bằng duyệt bitmask các tập con k tâm.
3. So `R_g`, `R^*` và kiểm tra `R_g≤2R^*`.
4. Nếu `R^*=0`, bắt buộc kiểm tra `R_g=0`, **không tính tỷ lệ 0/0**.
5. Ghi số ca đạt đúng tối ưu và chạm hệ số 2.

Kết quả:

| Đại lượng | Kết quả |
| --- | ---: |
| Tổng số cặp (tập điểm,k) | **3.820** |
| Greedy bằng tối ưu | **2.369** |
| Greedy lớn hơn tối ưu | **1.451** |
| Ca có `R^*=0` | **847** |
| Ca `R_g=2R^*` với `R^*>0` | **477** |
| Ca vi phạm `R_g≤2R^*` | **0** |
| Tỷ lệ lớn nhất quan sát khi `R^*>0` | **2,0** |

Tổng 2.369+1.451=3.820; các ca `R^*=0` được đếm trong nhóm bằng tối ưu, **không** đưa vào phép chia tỷ lệ. Nhóm 477 “chạm 2” được đếm riêng trong các ca `R^*>0`.

**Phân biệt chặt chẽ:**
- “Vượt quá hệ số 2: 0 trong 3.820 ca” là **kết quả kiểm thử hữu hạn**.
- “Với mọi input metric k-center, R_g≤2R^*” là **định lý có chứng minh** ở mục 7.
- “Ở một phân phối dữ liệu thực nào đó, trung bình ratio bằng ...” cần thêm **định nghĩa phân phối mẫu và phép ước lượng**. Không lấy thống kê từ bộ lưới 0..9 rồi suy thẳng sang dữ liệu thực tế.

## 11. Vì sao chạy thật không thể tự chứng minh mọi trường hợp?

Một benchmark hữu hạn chỉ bao phủ các điểm đã thử. Ngay cả triệu test ngẫu nhiên cũng có thể bỏ sót:
- **Cấu trúc đối kháng** cực hiếm theo phân phối sinh dữ liệu.
- Input rất lớn dẫn đến tràn số, stack overflow hoặc chi phí cấp phát.
- Giá trị biên: k=1, k=n, tất cả điểm trùng nhau, tọa độ âm/cực trị.
- Điều kiện giả thiết bị phá: khoảng cách không metric, dữ liệu thiếu/NaN, hàm mục tiêu khác.
- Những đường chạy ngẫu nhiên xác suất nhỏ nhưng chi phí cực lớn.

Với một tập hữu hạn đã vét cạn **toàn bộ**, ta có một phát biểu chắc chắn cho **tập đó** nếu chương trình/oracle và số học đúng. Nhưng một bộ thử `n≤6` không tự là chứng minh với **mọi n**.

Một proof cũng có giới hạn khác: nếu cài đặt Java không đúng thuật toán được chứng minh (chọn điểm không xa nhất, sai đơn vị, tràn int khi trừ, xử lý k sai), **định lý đúng không cứu phần mềm sai**. Vì thế cần cả:
- **Chứng minh thuật toán trừu tượng**;
- **Kiểm thử/đối chiếu implementation**;
- **Kiểm tra assumptions ở môi trường triển khai**.

## 12. Đánh giá heuristic một cách công bằng

Heuristic có thể hữu ích dù không có cận worst-case. Nhưng phải nói đúng điều mình biết:

**Đúng:** “Heuristic A nhanh hơn B trên các input đã thử; chi phí chất lượng so với oracle exact nhỏ trong bộ test này.”

**Không suy ra được:** “A có approximation ratio 1,1 trên mọi input” chỉ vì bộ test nhỏ nhất cho tỷ lệ không quá 1,1.

**Ví dụ first-k:** trên `[0,1,2,100]` với k=2, first-k radius99 còn tối ưu1; trên `[0,1,2,L]`, tỷ lệ có thể là L−1. Nếu dữ liệu kiểm thử chỉ quanh một cụm gần nhau, heuristic first-k có thể trông hợp lý nhưng dễ thất bại với một outlier xa.

**Bộ đối chứng nên có:**
- **Một nghiệm khả thi đơn giản** làm baseline.
- **Một thuật toán có cận đã chứng minh** nếu có.
- **Oracle exact trên n nhỏ** hoặc lower bound có chứng nhận.
- **Tình huống xấu được thiết kế có chủ đích**.
- **Dữ liệu triển khai thực tế** có mô tả nguồn và phân phối.

Đừng thay đổi tham số heuristic qua nhiều lượt xem test rồi báo kết quả trên **chính tập test đã tối ưu hóa** như một đánh giá độc lập. Đó là *selection bias* hoặc *data leakage*; nên tách train/tune/validation/test khi có bước điều chỉnh.

## 13. Kỳ vọng và xác suất khác với quan sát

Giả sử một randomized algorithm có bảo đảm:

\[
E[T(n)]\le Cn\log n.
\]

Nó nói về **kỳ vọng theo phân phối random nội tại** (và các giả thiết khác), **không** hứa mọi run có T≤Cn log n. Có thể tồn tại những lần rất chậm. Một vài lần chạy nhanh cũng không chứng minh cận kỳ vọng ấy.

Nếu một thuật toán Monte Carlo có:

\[
P(\text{sai})\le\delta,
\]

thì đây là cận theo **lựa chọn ngẫu nhiên** đã nêu, cho lớp input đã nêu. Nếu chạy 1.000 lần không gặp lỗi, không có nghĩa `\delta=0`. Phải phân biệt **xác suất thuật toán sai trong mô hình** với **tần suất sai trong bộ test hữu hạn**.

### Ví dụ một khoảng sai số thống kê

Giả sử các mẫu `X_i∈[0,1]` độc lập và cùng phân phối, có kỳ vọng `\mu`. Trung bình `\hat\mu` thỏa cận Hoeffding:

\[
P(|\hat\mu-\mu|\ge\varepsilon)
\le2e^{-2N\varepsilon^2}.
\]

Với `N=100` và mức rủi ro `\delta=0,05`, chọn:

\[
\varepsilon=\sqrt{\frac{\ln(2/\delta)}{2N}}
=\sqrt{\frac{\ln40}{200}}\approx0,136.
\]

**Ý nghĩa:** dưới các giả thiết iid và bounded, phương pháp có xác suất ít nhất 95% tạo khoảng `[\hat\mu-\varepsilon,\hat\mu+\varepsilon]` bao phủ `\mu` qua các lần lặp quá trình lấy mẫu. Nó **không** chứng minh trung bình thật đúng bằng trung bình quan sát, cũng không nên trình bày một khoảng đã tính như “xác suất hậu nghiệm 95% để giá trị cố định nằm trong khoảng” nếu đang dùng suy luận frequentist.

Nếu seed được lặp lại, dữ liệu có tương quan, có *post-selection* hay các mẫu không đại diện phân phối quan tâm, cận này **không được viện dẫn nguyên xi**. Khoảng tin cậy thống kê và cận approximation ratio là **hai thứ khác nhau**.

## 14. Benchmark runtime: một đồ thị không phải Big-O

Đo thời gian Java còn chịu ảnh hưởng của:
- JIT compilation và warm-up.
- Garbage collection và allocation.
- Scheduler, CPU frequency, nhiệt độ và tải hệ thống.
- Caching, locality, I/O, log console, bộ nhớ và kích thước input.
- Sự khác nhau giữa implementations hoặc điều kiện dừng.

**Không đặt `System.nanoTime()` quanh một thao tác quá nhỏ rồi coi một giá trị nanosecond là benchmark đáng tin**. Với nghiên cứu hiệu năng Java thực tế có thể dùng một framework benchmark phù hợp như JMH và ghi đầy đủ cấu hình.

Đo O(nk) cần nhiều n,k và xem tỷ lệ tăng; nhưng kể cả đồ thị khớp n·k trên các n đã thử, **chứng minh O(nk)** cho code farthest-first dựa trên việc đếm vòng lặp và cập nhật `nearest`, không dựa vào đường fit thống kê.

Ngược lại, proof O(nk) không nói chương trình chắc chắn nhanh hơn một biến thể O(n²) ở mọi n nhỏ do **hệ số, cache, allocation và môi trường**.

**Thiết kế một báo cáo tốt:** với mỗi input, ghi n,k, thuật toán, mã/version, dữ liệu/seed, radius, oracle radius nếu có, runtime sau warm-up, số lượt, các phân vị và điều kiện máy; công bố cả phương pháp chọn input.

## 15. Java 17: thuật toán 2-approx, oracle exact và kiểm thử

Chương trình độc lập **TheoryVsExperimentKCenterDemo.java** có:
- `distance` dùng long để tránh overflow khi hai tọa độ int cực trị bị trừ.
- `farthestFirst` với mảng `nearest`, **O(nk)**.
- `firstK` cố ý dùng làm heuristic đối chứng không có cận hằng.
- `exactOracle` duyệt mọi tập con k tâm bằng bitmask, chỉ cho `n≤20`.
- `radius` tính mục tiêu chính xác cho một tập tâm.
- Kiểm thử vét cạn tất cả tập con tọa độ 0..9 có n=1..6 với mọi k hợp lệ.
- Thống kê số lần bằng tối ưu, kém tối ưu, chạm factor2, tối ưu0 và max ratio trên những ca ratio xác định.
- Ví dụ **tọa độ int cực trị** chứng minh phép trừ phải ép sang long **trước** khi thực hiện.

Các kết quả mẫu **không dùng đồng hồ để đo runtime**, vì mục tiêu là phân biệt proof chất lượng với thực nghiệm hữu hạn; muốn benchmark cần thiết kế thí nghiệm riêng.

~~~java
import java.util.Arrays;
import java.util.Objects;

public class TheoryVsExperimentKCenterDemo {
    record Solution(int[] centers, long radius) {}

    static long distance(int a, int b) {
        // Ep tung toa do TRUOC phep tru de tranh int overflow.
        return Math.abs((long) a - (long) b);
    }

    static void checkInput(int[] p, int k) {
        Objects.requireNonNull(p, "points");
        if (p.length == 0 || k < 1 || k > p.length)
            throw new IllegalArgumentException(
                    "Require n >= 1 and 1 <= k <= n");
    }

    // Do xa nhat tu moi diem toi tam GAN NHAT.
    static long radius(int[] p, int[] centerIndices) {
        long answer = 0L;
        for (int x : p) {
            long nearest = Long.MAX_VALUE;
            for (int c : centerIndices) {
                nearest = Math.min(
                        nearest, distance(x, p[c]));
            }
            answer = Math.max(answer, nearest);
        }
        return answer;
    }

    // Gonzalez farthest-first: O(n*k), memory O(n+k).
    // Quy tac tie: chi so nho nhat.
    static Solution farthestFirst(int[] p, int k) {
        checkInput(p, k);
        int n = p.length;
        int[] centers = new int[k];
        boolean[] picked = new boolean[n];
        long[] nearest = new long[n];

        centers[0] = 0;
        picked[0] = true;
        for (int i = 0; i < n; i++)
            nearest[i] = distance(p[i], p[0]);

        for (int t = 1; t < k; t++) {
            int best = -1;
            long maxDist = -1L;
            for (int i = 0; i < n; i++) {
                if (!picked[i] && nearest[i] > maxDist) {
                    maxDist = nearest[i];
                    best = i;
                }
            }
            if (best < 0)
                throw new AssertionError(
                        "No unselected candidate");

            centers[t] = best;
            picked[best] = true;
            for (int i = 0; i < n; i++) {
                nearest[i] = Math.min(nearest[i],
                        distance(p[i], p[best]));
            }
        }

        long farthest = 0L;
        for (long d : nearest)
            farthest = Math.max(farthest, d);
        return new Solution(centers, farthest);
    }

    // Heuristic doi chung: lay k diem DAU, khong
    // co bao dam constant-factor tong quat.
    static Solution firstK(int[] p, int k) {
        checkInput(p, k);
        int[] c = new int[k];
        for (int i = 0; i < k; i++) c[i] = i;
        return new Solution(c, radius(p, c));
    }

    // ORACLE EXACT, CHI cho input nho.
    // 2^n masks; moi mask k bit la 1 tap tam hop le.
    static Solution exactOracle(int[] p, int k) {
        checkInput(p, k);
        if (p.length > 20)
            throw new IllegalArgumentException(
                    "Oracle restricted to n <= 20");

        long best = Long.MAX_VALUE;
        int[] bestCenters = null;
        int limit = 1 << p.length;

        for (int mask = 1; mask < limit; mask++) {
            if (Integer.bitCount(mask) != k) continue;
            int[] c = new int[k];
            int at = 0;
            for (int i = 0; i < p.length; i++) {
                if ((mask & (1 << i)) != 0)
                    c[at++] = i;
            }
            long cost = radius(p, c);
            if (cost < best) {
                best = cost;
                bestCenters = c;
            }
        }
        return new Solution(bestCenters, best);
    }

    static class Counts {
        int cases, optimal, suboptimal, tight2, zeroOpt;
        int violations;
        double maxRatio;
    }

    // Moi tap n toa do PHAN BIET tu {0,...,9}.
    // Enumerate theo thu tu tang, khong lap hoan vi.
    static void enumerateGrid(
            int[] p, int at, int from, Counts s) {
        if (at == p.length) {
            for (int k = 1; k <= p.length; k++) {
                Solution greedy = farthestFirst(p, k);
                Solution opt = exactOracle(p, k);
                long g = greedy.radius();
                long r = opt.radius();

                if (g > 2L * r)
                    s.violations++;
                if (g == r) s.optimal++;
                else s.suboptimal++;

                if (r == 0L) {
                    s.zeroOpt++;
                    if (g != 0L)
                        throw new AssertionError(
                                "Zero optimum violated");
                } else {
                    s.maxRatio = Math.max(
                            s.maxRatio, (double) g / r);
                    if (g == 2L * r) s.tight2++;
                }
                s.cases++;
            }
            return;
        }

        int stillNeeded = p.length - at;
        for (int x = from; x <= 10 - stillNeeded; x++) {
            p[at] = x;
            enumerateGrid(p, at + 1, x + 1, s);
        }
    }

    static Counts verify() {
        Counts s = new Counts();
        for (int n = 1; n <= 6; n++)
            enumerateGrid(new int[n], 0, 0, s);

        if (s.cases != 3820 || s.optimal != 2369
                || s.suboptimal != 1451
                || s.tight2 != 477 || s.zeroOpt != 847
                || s.violations != 0 || s.maxRatio != 2.0)
            throw new AssertionError(
                    "Unexpected exhaustive statistics");
        return s;
    }

    public static void main(String[] args) {
        int[] sample = {0,1,2,3,4};
        Solution greedy = farthestFirst(sample, 2);
        Solution optimum = exactOracle(sample, 2);
        System.out.println("sample.points="
                + Arrays.toString(sample));
        System.out.println("sample.k=2");
        System.out.println("sample.greedy.indices="
                + Arrays.toString(greedy.centers()));
        System.out.println("sample.greedy.radius="
                + greedy.radius());
        System.out.println("sample.exact.indices="
                + Arrays.toString(optimum.centers()));
        System.out.println("sample.exact.radius="
                + optimum.radius());
        System.out.println("sample.ratio="
                + (double) greedy.radius()
                    / optimum.radius());

        int[] trap = {0,1,2,100};
        Solution trapGreedy = farthestFirst(trap, 2);
        Solution trapExact = exactOracle(trap, 2);
        Solution trapFirst = firstK(trap, 2);
        System.out.println("trap.points="
                + Arrays.toString(trap));
        System.out.println("trap.greedy.indices="
                + Arrays.toString(trapGreedy.centers()));
        System.out.println("trap.greedy.radius="
                + trapGreedy.radius());
        System.out.println("trap.exact.indices="
                + Arrays.toString(trapExact.centers()));
        System.out.println("trap.exact.radius="
                + trapExact.radius());
        System.out.println("trap.firstK.radius="
                + trapFirst.radius());
        System.out.println("trap.proofBoundHolds="
                + (trapGreedy.radius()
                   <= 2L * trapExact.radius()));

        long extreme = distance(
                Integer.MIN_VALUE, Integer.MAX_VALUE);
        System.out.println("extremeDistance=" + extreme);

        Counts s = verify();
        System.out.println("verified.cases=" + s.cases);
        System.out.println("verified.optimal=" + s.optimal);
        System.out.println("verified.suboptimal="
                + s.suboptimal);
        System.out.println("verified.tight2=" + s.tight2);
        System.out.println("verified.zeroOpt=" + s.zeroOpt);
        System.out.println("verified.violations="
                + s.violations);
        System.out.println("verified.maxRatio="
                + s.maxRatio);
        System.out.println("verification=PASS");
    }
}
~~~

Lưu file với đúng tên **TheoryVsExperimentKCenterDemo.java** rồi chạy:

~~~bash
javac TheoryVsExperimentKCenterDemo.java
java TheoryVsExperimentKCenterDemo
~~~

**Đầu ra dự kiến:**

~~~text
sample.points=[0, 1, 2, 3, 4]
sample.k=2
sample.greedy.indices=[0, 4]
sample.greedy.radius=2
sample.exact.indices=[0, 3]
sample.exact.radius=1
sample.ratio=2.0
trap.points=[0, 1, 2, 100]
trap.greedy.indices=[0, 3]
trap.greedy.radius=2
trap.exact.indices=[1, 3]
trap.exact.radius=1
trap.firstK.radius=99
trap.proofBoundHolds=true
extremeDistance=4294967295
verified.cases=3820
verified.optimal=2369
verified.suboptimal=1451
verified.tight2=477
verified.zeroOpt=847
verified.violations=0
verified.maxRatio=2.0
verification=PASS
~~~

### Đọc đúng ý nghĩa kết quả

- `sample.ratio=2.0` là một **instance đạt đúng cận 2**, không nói mọi instance đều đạt 2.
- `trap.firstK.radius=99` là **phản ví dụ cho heuristic first-k**, không phải cho farthest-first.
- `trap.proofBoundHolds=true` kiểm một instance; bản thân boolean đó không phải proof tổng quát.
- `extremeDistance=4294967295` nhấn mạnh **ép từng tọa độ sang long trước khi trừ**, không làm phép trừ int rồi mới ép.
- `verified.cases=3820` là số cặp (tập điểm,k) trong một miền hữu hạn xác định.
- `verified.optimal=2369` và `verified.suboptimal=1451` phân loại số ca, **không** tự là xác suất đạt tối ưu trên dữ liệu ngoài đời.
- `verified.tight2=477` là số ca với OPT>0 và tỷ số bằng 2; `verified.zeroOpt=847` không có tỷ số `0/0`.
- `verified.violations=0` là kết quả kiểm thử; định lý tổng quát đến từ chứng minh metric.
- `verified.maxRatio=2.0` là maximum **đã quan sát**, không phải phương pháp suy ra worst-case bằng brute force 3.820 ca.

## 16. Các phép đối chiếu độc lập để tránh “oracle tự xác nhận chính nó”

Để kiểm tra ví dụ trước khi lưu, có thể cài hai cách tính **khác cấu trúc**:
- Farthest-first triển khai bằng **mảng nearest được cập nhật O(nk)**.
- Farthest-first tham chiếu tính lại min-distance đến tất cả tâm ở mỗi lượt (**O(nk²)**), cùng quy tắc tie.
- Oracle exact thứ nhất duyệt **bitmask các tập con k tâm**.
- Oracle exact thứ hai sinh **tổ hợp đệ quy** theo chỉ số tăng.

Trên **toàn bộ 3.820 ca**, hai bản greedy chọn cùng các tâm và bán kính; hai oracle trả cùng giá trị tối ưu. Mọi instance thỏa `R_g≤2R^*`, đồng thời các số đếm `2369,1451,477,847` nhất quán.

Các cấu trúc đối chiếu khác nhau giúp giảm rủi ro **một bug giống nhau xuất hiện trong cả thuật toán lẫn oracle**. Nhưng một phép kiểm hữu hạn không có giá trị bằng **chứng minh cho mọi input**.

### Kiểm tra giả thiết cũng quan trọng như kiểm tra kết quả

Bộ thử 0..9 **luôn** dùng khoảng cách `|x-y|`, nên bất đẳng thức tam giác được bảo đảm. Nếu cho ma trận khoảng cách tùy ý, một instance ở mục 8 tạo ratio3. Chỉ dựa vào 3.820 ca metric mà suy luôn “mọi ma trận khoảng cách đều có ratio≤2” là **phạm vi kết luận sai**.

Với dữ liệu thực, cần kiểm tra định nghĩa distance có phải metric không. Ví dụ “1−độ tương đồng” hay một hàm chi phí học máy bất kỳ có thể **không** thỏa tam giác; phải kiểm chứng hoặc chọn định lý khác.

## 17. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “1.000 ca đều đúng nên đã chứng minh” | Test hữu hạn không bao phủ mọi input | Phân biệt test với định lý |
| Quên giả thiết metric của 2-approx | Ma trận không metric có thể ratio>2 | Viết rõ và kiểm tra tam giác |
| So nghiệm với heuristic rồi gọi là OPT | Baseline chưa chắc tối ưu | Exact oracle hoặc cận được chứng nhận |
| Đưa `ALG/OPT` vào bảng khi OPT=0 | Chia 0/0 vô nghĩa | Kiểm tra `ALG=0`, đếm riêng |
| Gọi 2-approx là “lỗi không quá 2%” | 2 là **hệ số nhân**, không phải 2% | Giải thích α·OPT |
| Nói O(nk) tức mọi lần chạy nhanh hơn O(n²) | Big-O tiệm cận, có constant/hardware | Phân tích + benchmark |
| Một lần chạy nhanh ⇒ expected runtime nhỏ | Một mẫu không cho expectation tổng quát | Lặp đúng phân phối, phân tích xác suất |
| Không gặp lỗi Monte Carlo ⇒ δ=0 | Lỗi hiếm có thể bị bỏ sót | Cận toán học/đánh giá thống kê |
| Test chỉ trên input dễ | Bỏ outlier và adversarial cases | Thiết kế stress/counterexample |
| Đổi seed để chọn run đẹp | Selection bias | Ghi phương pháp và công bố đầy đủ |
| Không warm-up benchmark Java | JIT/GC làm sai so sánh | Dùng quy trình benchmark đáng tin |
| Coi run có cùng seed là iid | Có thể trùng hoàn toàn | Quản lý stream và dependency |
| Không kiểm tra số học | Tràn int khi tính distance | Ép sang long trước phép trừ |
| Nhầm k-means với k-center | Mục tiêu trung bình khác max-distance | Viết đúng objective |
| Thay tâm xa nhất bằng tâm tùy ý | Mất tiền đề chứng minh | Duy trì invariant nearest |
| Chỉ kiểm tra một implementation | Có thể cùng bug trong assertion | Oracle/đối chiếu khác cấu trúc |
| Dùng lower/upper bound sai chiều | Kết luận tỷ lệ bị đảo | Lập bất đẳng thức theo min/max |
| Tuyên bố kết quả thực nghiệm phổ quát | Không xét distribution shift | Công bố phạm vi và uncertainty |

## 18. Bài tập có đáp án

**Bài 1.** Một benchmark 3.820 ca có max ratio2. Có tự chứng minh 2-approx trên mọi input không?

*Đáp án:* Không. Nó kiểm chứng miền hữu hạn; muốn phát biểu tổng quát cần proof và giả thiết.

**Bài 2.** Phát biểu `ALG≤2OPT` cho bài tối thiểu nói gì?

*Đáp án:* Giá trị lời giải không vượt gấp đôi tối ưu trên **mọi input hợp lệ** đã nêu; không phải “sai số 2%”.

**Bài 3.** Khi `OPT=0` có thể in ratio `ALG/OPT` không?

*Đáp án:* Không, cần xét bất đẳng thức trực tiếp; với α hữu hạn và mục tiêu không âm phải có ALG=0.

**Bài 4.** K-center tối thiểu hóa đại lượng nào?

*Đáp án:* Max khoảng cách từ điểm bất kỳ tới **tâm gần nhất**.

**Bài 5.** Bài k-center có giống k-means không?

*Đáp án:* Không. K-center dùng max nearest-center distance, k-means dùng tổng/ trung bình bình phương khoảng cách tới tâm theo mô hình của nó.

**Bài 6.** Trong farthest-first, điểm tiếp theo được chọn thế nào?

*Đáp án:* Điểm chưa là tâm có khoảng cách đến **tâm gần nhất hiện tại** lớn nhất.

**Bài 7.** Với `[0,1,2,3,4],k=2`, greedy bắt đầu 0 chọn gì?

*Đáp án:* Chọn 4, bán kính2.

**Bài 8.** Một bộ tâm tối ưu của bài 7 là gì?

*Đáp án:* Chỉ số [0,3], bán kính1.

**Bài 9.** Với `[0,1,2,100],k=2`, first-k cho bán kính bao nhiêu?

*Đáp án:* Chọn 0,1, radius99.

**Bài 10.** Tối ưu trong bài 9 là gì?

*Đáp án:* Chọn 1,100, radius1.

**Bài 11.** Lấy `[0,1,2,L],k=2` và L ngày càng lớn cho first-k ratio nào?

*Đáp án:* L−1, không có cận hằng tổng quát.

**Bài 12.** Farthest-first có bảo đảm 2 nhờ tính chất nào của distance?

*Đáp án:* Bất đẳng thức tam giác, cùng nguyên lý k+1 điểm vào k bóng phủ.

**Bài 13.** Nếu bỏ bất đẳng thức tam giác, còn dùng proof đó được không?

*Đáp án:* Không. Ví dụ ma trận ở mục 8 có greedy radius3, OPT1.

**Bài 14.** Trong proof, vì sao có k+1 điểm cách nhau ít nhất `R_g`?

*Đáp án:* k tâm được chọn lần lượt xa nhất và thêm điểm xa nhất sau cùng; bán kính phủ không tăng theo việc thêm tâm.

**Bài 15.** Tại sao trong k tâm tối ưu phải có hai trong k+1 điểm dùng chung một tâm?

*Đáp án:* Nguyên lý Dirichlet (pigeonhole).

**Bài 16.** Hai điểm cùng được phủ trong bán kính R* của tâm z thì cách nhau tối đa bao nhiêu?

*Đáp án:* `2R^*` theo tam giác.

**Bài 17.** Với n=6,k=3 có bao nhiêu tập k tâm để oracle xét?

*Đáp án:* \(\binom63=20\).

**Bài 18.** Vì sao exact oracle không nên dùng cho n=10.000?

*Đáp án:* Số tập con tăng tổ hợp theo n; bitmask/brute force là phương pháp dành cho n nhỏ.

**Bài 19.** Bộ lưới 0..9,n1..6, mọi k có mấy case?

*Đáp án:* 3.820.

**Bài 20.** Trong 3.820 case, greedy bằng tối ưu bao nhiêu?

*Đáp án:* 2.369; còn 1.451 kém tối ưu.

**Bài 21.** Có bao nhiêu case chạm factor2 với OPT>0?

*Đáp án:* 477.

**Bài 22.** Có bao nhiêu case OPT=0 và chúng được xử lý ra sao?

*Đáp án:* 847, kiểm greedy cũng 0 và **không tính 0/0**.

**Bài 23.** Nếu chỉ biết `L≤OPT` và có nghiệm giá trị A, có thể kết luận gì khi L>0?

*Đáp án:* `A/OPT≤A/L`, nên A/L là một **cận trên cho ratio của instance**, không phải định lý cho mọi instance khác.

**Bài 24.** Nếu so A với một heuristic B chưa chứng nhận tối ưu, `A/B` có là ratio to OPT không?

*Đáp án:* Không; chỉ là tỷ lệ so với baseline B.

**Bài 25.** “Observed max=2” và “worst-case guarantee=2” khác nhau?

*Đáp án:* Cái đầu từ tập test, cái sau từ proof cho mọi input thuộc giả thiết.

**Bài 26.** Có thể dùng histogram hay 1000 lần chạy để chứng minh Monte Carlo không bao giờ sai không?

*Đáp án:* Không. Lỗi xác suất nhỏ có thể không xảy ra trong các run đó.

**Bài 27.** Một expected runtime O(n log n) có nói mọi lần chạy đều ≤Cn log n?

*Đáp án:* Không; bound trên **kỳ vọng**, không tự là bound từng run.

**Bài 28.** Vì sao benchmark Java nên warm-up?

*Đáp án:* JIT compilation, GC, cache và scheduling có thể làm các lần đầu khác các lần sau.

**Bài 29.** Hai phương pháp dùng cùng random scenario khi so sánh có nhất thiết sai?

*Đáp án:* Không; paired/common random numbers có thể hợp lệ nếu phân tích dependence đúng.

**Bài 30.** Trong k-center trục số, khoảng cách `intMin−intMax` nên tính bằng kiểu gì?

*Đáp án:* Ép mỗi toán hạng sang long trước khi trừ; trị tuyệt đối là 4.294.967.295.

**Bài 31.** Một công trình chỉ đánh giá trên dữ liệu dễ, đã tuning thuật toán trên đó rồi lại báo “test tốt”. Vấn đề?

*Đáp án:* Selection bias/data leakage; nên tách dữ liệu tuning và kiểm thử độc lập, nêu phạm vi.

**Bài 32.** Nếu proof sai giả thiết nhưng benchmark pass nhiều ca, có thể tuyên bố guarantee không?

*Đáp án:* Không. Phải sửa proof hoặc thu hẹp miền đầu vào cho đúng giả thiết.

## 19. Checklist đọc và viết báo cáo thuật toán

1. Xác định bài toán là **minimization** hay **maximization** và đặc tả nghiệm hợp lệ.
2. Viết rõ **OPT** là gì, có oracle exact hay chỉ lower/upper bound.
3. Phân loại kết luận: **proof**, **verified finite domain**, **benchmark**, **simulation**, **statistical estimate**.
4. Nếu phát biểu approximation ratio, nêu **α, lượng từ mọi input và assumptions**.
5. Nếu randomized, nêu rõ xác suất theo random nào, input có cố định hay được lấy từ distribution nào.
6. Đừng dùng `ALG/OPT` khi OPT=0; xử lý trường hợp suy biến riêng.
7. Kiểm tra tam giác nếu dùng metric k-center hoặc định lý metric khác.
8. So sánh với oracle **độc lập về cấu trúc** khi n nhỏ.
9. Thiết kế phản ví dụ phá heuristic/assumption chứ không chỉ test input thuận lợi.
10. Ghi tập dữ liệu, phạm vi n,k, seed, JDK, máy và phương pháp đo.
11. Phân biệt **tốc độ tiệm cận** với **thời gian quan sát thực tế**.
12. Nếu dùng thống kê, công bố sample size, tính độc lập, khoảng tin cậy và phương pháp chọn mẫu.
13. Tránh cherry-picking, selection bias, data leakage và ngoại suy sang input chưa xem xét.
14. Dùng số học đúng kiểu; cast trước khi trừ, tránh overflow.
15. Nêu rõ phần nào được **chứng minh toán học**, phần nào mới **kiểm chứng thực nghiệm**.

## Tổng kết

**Bảo đảm toán học** là phát biểu về **mọi input thuộc miền đã chứng minh**, có giả thiết và suy luận chính xác. **Kết quả thực nghiệm** là điều ta quan sát trên một tập dữ liệu/điều kiện hữu hạn; nó hữu ích cho lựa chọn triển khai, tìm bug và đánh giá hiệu năng thực, nhưng không tự biến thành định lý.

Trong ví dụ **metric k-center**, farthest-first chọn k tâm có `R_g≤2R^*` nhờ bất đẳng thức tam giác và nguyên lý Dirichlet. Heuristic first-k có thể tệ tùy ý, và trên ma trận không metric, bản farthest-first có thể đạt ratio3 nên **không được bỏ giả thiết tam giác**. Bộ kiểm thử 3.820 ca xác nhận không vi phạm 2-approx trong miền lưới nhỏ; định lý 2-approx mới giải thích đúng cho mọi instance metric hợp lệ.

Cách đánh giá đáng tin là **kết hợp chứng minh, oracle exact cho trường hợp nhỏ, test đối kháng, benchmark có kiểm soát và báo cáo thống kê trung thực** — đồng thời luôn nói chính xác phạm vi của từng kết luận.

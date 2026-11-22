# Nghiệm khả thi, giá trị tối ưu và hệ số xấp xỉ

**Thuật toán xấp xỉ (approximation algorithm)** giải một bài toán tối ưu bằng cách tạo ra một **nghiệm khả thi** có chất lượng được so sánh với **giá trị tối ưu** theo một **bảo đảm toán học**. Với nhiều bài toán tối ưu tổ hợp khó, chẳng hạn Minimum Vertex Cover hoặc Maximum Coverage, một nghiệm tối ưu chính xác có thể cần thời gian rất lớn khi số biến tăng. Thuật toán xấp xỉ thường hy sinh một phần chất lượng để đạt thời gian đa thức **đồng thời chứng minh được mức sai lệch tệ nhất**.

Bài học thuộc nhóm **Xấp xỉ và kinh nghiệm** của Computer Science Algorithms, tập trung vào ba khái niệm cốt lõi: **nghiệm khả thi (feasible solution)**, **giá trị tối ưu (OPT)** và **hệ số xấp xỉ (approximation ratio/factor)**. Ta phân biệt bài **MIN** và **MAX**, cách xử lý OPT=0 hoặc giá trị âm, cận dưới/cận trên cho OPT, hai ví dụ có chứng minh là **2-approximation cho Minimum Vertex Cover không trọng số** và **greedy (1−1/e)-approximation cho Maximum Coverage**, đồng thời làm rõ giới hạn của heuristic, kiểm thử thực nghiệm, thuật toán ngẫu nhiên, PTAS/FPTAS, cùng chương trình Java 17+ có oracle vét cạn cho những trường hợp nhỏ.

## 1. Một bài toán tối ưu gồm những gì?

Một bài toán tối ưu cần chỉ rõ:

1. **Đầu vào I:** dữ liệu của một trường hợp cụ thể, chẳng hạn đồ thị G=(V,E) hoặc họ tập hợp.
2. **Miền nghiệm ứng viên S(I):** những đối tượng có thể được lựa chọn, ví dụ tập đỉnh, tập tập con, lịch công việc.
3. **Ràng buộc khả thi:** điều kiện quyết định ứng viên có phải một **nghiệm hợp lệ** hay không.
4. **Hàm mục tiêu c_I(s):** giá trị số của nghiệm s; bài MIN muốn nhỏ nhất, bài MAX muốn lớn nhất.
5. **Tiêu chí đầu ra:** cần nghiệm tối ưu tuyệt đối hay chấp nhận xấp xỉ có chứng minh?

Với bài **tối thiểu hóa**, đặt:

`OPT(I)=min_{s∈F(I)} c_I(s)`.

Với bài **tối đa hóa**, đặt:

`OPT(I)=max_{s∈F(I)} c_I(s)`.

Ở đây `F(I)⊆S(I)` là tập **nghiệm khả thi**. Các công thức giả định F(I) không rỗng và giá trị tối ưu tồn tại. Nếu đầu vào **vô nghiệm**, phải báo trạng thái vô nghiệm, không thể gán bừa một giá trị OPT hữu hạn rồi tính tỉ lệ.

### Ba đối tượng khác nhau

- **Nghiệm khả thi:** một đối tượng s thực sự thỏa mọi ràng buộc.
- **Giá trị của nghiệm:** số `ALG=c_I(s)` do thuật toán tạo ra.
- **Giá trị tối ưu:** số `OPT` tốt nhất có thể trong **tất cả** nghiệm khả thi.

Nhiều bài trả **cả nghiệm và giá trị**. Chỉ in một số nhỏ hơn OPT của bài MIN nhưng không xây dựng được nghiệm thỏa ràng buộc **không** phải một thuật toán xấp xỉ đúng.

### Một ví dụ nhỏ

Minimum Vertex Cover yêu cầu chọn các đỉnh sao cho **mọi cạnh** có ít nhất một đầu mút được chọn. Giá trị mục tiêu là **số đỉnh đã chọn**.

Đồ thị ngôi sao có tâm 0 và các cạnh (0,1),(0,2),(0,3),(0,4),(0,5):

- Tập `{0}`: khả thi, giá trị 1, và là tối ưu.
- Tập `{0,1}`: khả thi, giá trị 2, không tối ưu nhưng chỉ gấp đôi OPT.
- Tập `{1}`: **không khả thi**, vì các cạnh (0,2),… chưa được che.
- Tập rỗng: không khả thi nếu đồ thị còn cạnh.

Do đó **khả thi** là điều kiện đầu tiên, **xấp xỉ tốt** là điều kiện tiếp theo.

## 2. Quy ước tỉ lệ xấp xỉ cho bài MIN

Xét một bài MIN có chi phí **không âm** và nghiệm khả thi s do thuật toán trả ra, với:

`ALG=c_I(s)`.

Theo định nghĩa tối ưu:

`ALG≥OPT`.

Một thuật toán có **hệ số xấp xỉ ρ≥1** nếu với **mọi đầu vào hợp lệ I** thuộc phạm vi chứng minh:

`ALG(I)≤ρ·OPT(I)`.

Kết hợp:

`OPT(I)≤ALG(I)≤ρ·OPT(I)`.

Nếu OPT>0, ta có thể viết:

`ALG/OPT≤ρ`.

### Diễn giải

- ρ=1: thuật toán trả nghiệm tối ưu, xét theo mục tiêu.
- ρ=2: chi phí nghiệm không lớn hơn 2 lần tối ưu.
- ρ=1.5: chi phí nghiệm không lớn hơn 1.5 lần tối ưu.
- ρ lớn: bảo đảm yếu hơn.

**ρ là cận trên cho tỉ lệ tệ nhất**, không có nghĩa mọi input đều đạt đúng ρ.

Ví dụ một thuật toán 2-approx có thể trả đúng tối ưu trên nhiều đầu vào, nhưng vẫn được gọi là 2-approx vì bảo đảm tổng quát chỉ là ALG≤2OPT.

### Cẩn thận khi OPT=0

Nếu OPT=0, biểu thức `ALG/OPT` **không xác định**. Bất đẳng thức:

`ALG≤ρ·OPT`

vẫn có nghĩa: nó yêu cầu ALG=0 khi chi phí không âm. Trong ví dụ đồ thị **không có cạnh**, tập đỉnh rỗng là nghiệm khả thi và có giá trị tối ưu 0. Một chương trình đúng nên in **ratio=undefined** thay vì in 0/0 hoặc NaN rồi coi đó là chứng nhận.

### Cẩn thận khi hàm mục tiêu âm

Các tỉ lệ thường dùng giả định **chi phí không âm** và OPT dương khi thực hiện phép chia. Với các mục tiêu âm, nhân bất đẳng thức với ρ có thể tạo kết quả vô lý: nếu OPT=−10 và ALG=−9 ở bài MIN, thì ALG≤2OPT nghĩa là −9≤−20, không thể đúng dù nghiệm rất gần tối ưu. Khi mục tiêu có thể âm, phải **định nghĩa lại thước đo** hoặc một chuẩn xấp xỉ thích hợp; không áp công thức ρ thông thường một cách máy móc.

## 3. Quy ước hệ số cho bài MAX

Với một bài MAX có giá trị nghiệm **không âm**:

`ALG≤OPT`.

Có hai cách viết tương đương khi các giá trị dương:

**Cách 1: hệ số hiệu quả α với 0<α≤1**

`ALG≥α·OPT`.

Ví dụ **α=0.8** nghĩa là giá trị đạt được **ít nhất 80%** tối ưu.

**Cách 2: hệ số xấp xỉ ρ≥1**

`OPT≤ρ·ALG`,

hoặc:

`ALG≥OPT/ρ`.

Hai cách liên hệ bằng `ρ=1/α`. Ví dụ α=0.8 tương ứng ρ=1.25.

Đừng so trực tiếp “ρ=2 tốt hơn α=0.8” vì đây là **hai thang biểu diễn khác nhau**. Trên cùng cách viết, ρ càng gần 1 càng tốt; α càng gần 1 càng tốt.

### Bảng so sánh MIN/MAX

| Nội dung | Bài MIN | Bài MAX |
| --- | --- | --- |
| Mục tiêu | Chi phí càng nhỏ càng tốt | Giá trị càng lớn càng tốt |
| Quan hệ của nghiệm khả thi | `ALG≥OPT` | `ALG≤OPT` |
| Bảo đảm thường dùng | `ALG≤ρ·OPT`, ρ≥1 | `ALG≥α·OPT`, 0<α≤1 |
| Cách dùng cùng ρ≥1 | `ALG≤ρ·OPT` | `ALG≥OPT/ρ` |
| Kết quả tối ưu | `ALG=OPT` | `ALG=OPT` |
| OPT=0 | Không chia ALG/OPT | Không chia ALG/OPT |
| Nghiệm không khả thi | Không có ý nghĩa bảo đảm | Không có ý nghĩa bảo đảm |

Với Maximum Coverage, bài học dùng chủ yếu **α≈0.632**, tương đương một hệ số ρ≈1.582 khi muốn viết theo cách ρ≥1.

## 4. Hệ số xấp xỉ phải là một bảo đảm, không phải quan sát

Giả sử trên 20 đồ thị thử nghiệm, thuật toán tìm Vertex Cover luôn có:

`ALG/OPT≤1.3`.

Điều đó **không chứng minh** thuật toán là 1.3-approx trên mọi đồ thị. Có thể tồn tại một đồ thị chưa được thử với tỉ số 1.8 hoặc lớn hơn. Muốn tuyên bố hệ số xấp xỉ tệ nhất, cần một **chứng minh cho mọi đầu vào trong lớp được xét**.

Ngược lại, nếu thuật toán được chứng minh 2-approx thì một lần chạy ra nghiệm đúng tối ưu không làm thay đổi bảo đảm 2-approx đã biết.

### Các mức bảo đảm thường gặp

- **Worst-case approximation:** bất đẳng thức áp dụng cho mọi input thuộc phạm vi định lý, với thuật toán xác định.
- **Expected approximation:** với thuật toán ngẫu nhiên, một bất đẳng thức chỉ đúng **theo kỳ vọng** đối với lựa chọn ngẫu nhiên nội bộ.
- **High-probability approximation:** bất đẳng thức đúng với xác suất ít nhất 1−δ.
- **Average-case/empirical performance:** mô tả hiệu suất trên một phân bố input hoặc tập benchmark cụ thể, không tự suy ra worst case.

**Không được tráo đổi** “kỳ vọng đạt αOPT” thành “mọi lần chạy đạt αOPT”.

## 5. Cận dưới và cận trên giúp chứng nhận nghiệm

Ta thường **không biết OPT** trên đầu vào lớn. Làm thế nào chứng minh chất lượng nghiệm mà không cần giải bài tối ưu chính xác?

### Bài MIN: dùng cận dưới L

Nếu có một cận dưới:

`L≤OPT`,

và thuật toán tạo nghiệm khả thi có giá trị ALG, đồng thời chứng minh:

`ALG≤ρ·L`,

thì suy ra:

`ALG≤ρ·L≤ρ·OPT`.

Đây là một **chứng nhận xấp xỉ** dựa vào cận dưới dễ tính. Cận dưới L có thể đến từ nghiệm thư giãn của bài toán, một ghép cặp, một phân hoạch hoặc một lập luận tổ hợp.

**Lưu ý về độ tốt của cận:** L quá nhỏ vẫn có thể đúng nhưng không giúp chứng minh hệ số mạnh.

### Bài MAX: dùng cận trên U

Nếu có:

`OPT≤U`,

và một nghiệm khả thi thỏa:

`ALG≥α·U`,

thì:

`ALG≥α·U≥α·OPT`.

Cận trên U có thể đến từ bài toán thư giãn, giới hạn tổng tài nguyên hoặc công thức cấu trúc. Một cận trên quá lỏng có thể không giúp chứng nhận hệ số tốt.

### Lower bound khác feasible upper bound

Trong bài MIN, mỗi nghiệm **khả thi** cho một **cận trên** của OPT, không phải cận dưới: `OPT≤ALG`. Muốn chứng minh “gần tối ưu”, cần thêm một **cận dưới độc lập** cho OPT.

Trong bài MAX, mỗi nghiệm khả thi cho một **cận dưới** ALG≤OPT; muốn chứng minh gần tối ưu cần biết một **cận trên** đủ chặt.

Không nhầm hai hướng này.

## 6. Ví dụ 1: Minimum Vertex Cover không trọng số

Cho đồ thị vô hướng đơn `G=(V,E)`. Một **vertex cover** là tập `C⊆V` sao cho với mọi cạnh `(u,v)∈E`:

`u∈C` hoặc `v∈C`.

Bài toán **Minimum Vertex Cover** yêu cầu tìm C có kích thước nhỏ nhất:

`OPT=min |C|`.

Phiên bản tổng quát trên đồ thị không trọng số là một bài toán NP-hard, nên thuật toán tối ưu chính xác bằng vét cạn thường không phù hợp khi n lớn. Nhưng có một thuật toán đơn giản bảo đảm **2-approximation**.

### Ý tưởng: chọn cả hai đầu mút của một ghép cặp cực đại

**Matching (ghép cặp)** là tập các cạnh không có chung đỉnh.

**Maximal matching (ghép cặp cực đại theo bao hàm)** là matching không thể thêm một cạnh nào nữa mà vẫn giữ tính matching.

**Maximum matching** là matching có **số cạnh lớn nhất**. Hai khái niệm này khác nhau. Thuật toán 2-approx **chỉ cần maximal matching**, dễ tạo bằng một lần quét cạnh.

### Thuật toán

Bắt đầu:

`C=∅, M=∅`.

Duyệt các cạnh `(u,v)` theo thứ tự đầu vào:

1. Nếu **cả u và v đều chưa được chọn**, thêm cạnh (u,v) vào M và thêm **cả hai đầu mút** u,v vào C.
2. Nếu ít nhất một đầu mút đã được chọn, bỏ qua cạnh.
3. Kết thúc, trả tập C.

Giả mã:

~~~text
APPROX_VERTEX_COVER(G):
    selected[v] = false for every vertex v
    matching = 0
    for each edge (u,v) of G:
        if not selected[u] and not selected[v]:
            selected[u] = true
            selected[v] = true
            matching = matching + 1
    return all v with selected[v] == true
~~~

Vì một cạnh được thêm khi cả hai đầu chưa thuộc matching, các cạnh trong M không giao nhau. Vì đã duyệt mọi cạnh, không còn cạnh có cả hai đầu không thuộc M; do đó M maximal và C là một vertex cover.

### Chứng minh hệ số 2

Gọi M là matching do thuật toán chọn.

**Mọi vertex cover đều phải chọn ít nhất một đầu mút của mỗi cạnh trong M.** Do các cạnh của M không chia sẻ đỉnh, cần ít nhất `|M|` đỉnh khác nhau:

`OPT≥|M|`.

Thuật toán chọn cả hai đầu mút của mỗi cạnh trong M nên:

`ALG=|C|=2|M|`.

Suy ra:

`ALG=2|M|≤2·OPT`.

Cộng với chứng minh C che mọi cạnh, thuật toán là **2-approximation cho Minimum Vertex Cover không trọng số**.

**Cốt lõi của chứng minh:** vừa có **nghiệm khả thi C**, vừa có **cận dưới |M| đối với OPT**. Chỉ so kích thước C với một giá trị phỏng đoán chưa đủ.

### Độ phức tạp

Với danh sách n đỉnh và m cạnh:

- Duyệt cạnh và đánh dấu đỉnh: **O(m)**.
- Trích danh sách đỉnh được chọn: **O(n)**.
- Tổng: **O(n+m)** thời gian; **O(n)** bộ nhớ phụ cho mảng selected, chưa tính dữ liệu đồ thị.

Không cần giải bài matching tối đa. Dùng một matching **bất kỳ chưa maximal** rồi trả hai đầu mút của nó có thể **không che hết cạnh còn lại**.

## 7. Các trường hợp cụ thể của Vertex Cover

### Đường đi bốn đỉnh

Đồ thị có các cạnh:

`(0,1),(1,2),(2,3)`.

Thuật toán quét theo thứ tự:

- Chọn (0,1), thêm 0 và 1.
- Bỏ (1,2), vì 1 đã chọn.
- Chọn (2,3), thêm 2 và 3.

Kết quả `C={0,1,2,3}`, kích thước ALG=4.

Nhưng `{1,2}` đã che mọi cạnh, nên `OPT=2`. Tỉ lệ thực tế:

`ALG/OPT=4/2=2`.

Ví dụ này cho thấy hệ số 2 **có thể đạt sát biên**, không chỉ là một cận lỏng vô nghĩa.

### Tam giác

Các cạnh (0,1),(1,2),(0,2).

Thuật toán chọn (0,1) rồi bỏ các cạnh còn lại, trả C={0,1}, ALG=2. Tối ưu cũng cần 2 đỉnh, nên OPT=2 và tỉ số 1.

### Ngôi sao

Có tâm 0, năm lá và cạnh (0,i), i=1..5.

Thuật toán chọn (0,1), trả {0,1}, ALG=2. Chọn riêng {0} đã che mọi cạnh, nên OPT=1, tỉ số 2.

### Đồ thị không có cạnh

C=∅, ALG=OPT=0. Công thức bất đẳng thức **ALG≤2OPT** đúng, nhưng `ALG/OPT=0/0` **không xác định**. Phần mềm phải phân biệt “tỉ số không xác định” với “bảo đảm sai”.

## 8. Không mở rộng bảo đảm 2 cho bài có trọng số

**Weighted Vertex Cover** cho mỗi đỉnh v một chi phí không âm `w_v` và muốn tối thiểu:

`Σ_(v∈C) w_v`.

Phương pháp “lấy cả hai đầu mút của matching” **không tự động** có hệ số 2 cho bài này.

Phản ví dụ: đồ thị chỉ có một cạnh (0,1), với:

`w_0=100, w_1=1`.

Chọn cả 0 và 1 có chi phí **101**, trong khi chọn {1} đủ che cạnh với chi phí **1**. Tỉ số 101, không hề ≤2.

Weighted Vertex Cover cũng có thuật toán 2-approx theo những hướng khác (ví dụ primal-dual/LP rounding), nhưng cần chứng minh khác. **Một chứng minh cho bài không trọng số không được chuyển sang bài có trọng số chỉ bằng cách sửa hàm tính chi phí.**

## 9. Ví dụ 2: Maximum Coverage

Cho một tập vũ trụ hữu hạn `U` và một họ n tập con:

`S₀,S₁,…,S_(n−1)⊆U`.

Được phép chọn **tối đa k tập con**. Mục tiêu là bao phủ nhiều phần tử của U nhất:

`OPT=max_{T⊆{0,…,n−1}, |T|≤k} |⋃_(i∈T) Sᵢ|`.

Nghiệm khả thi là một danh sách chỉ số tập **không lặp**, có độ dài không vượt k. Giá trị là **số phần tử phân biệt** trong hợp các tập được chọn.

### Vì sao đây là bài MAX?

Khác Vertex Cover, ta **không bắt buộc** che toàn bộ U. Với giới hạn k, có thể không đủ tập để che hết. Nghiệm tốt là nghiệm có **giá trị phủ càng lớn càng tốt**, nhưng không vượt OPT.

### Thuật toán tham lam

Bắt đầu với tập đã phủ `A₀=∅`.

Ở mỗi lượt i:

1. Xét mỗi tập chưa chọn `S_j`.
2. Tính **số phần tử mới được phủ**:

`gain(j)=|S_j \ A_i|`.

3. Chọn tập có gain lớn nhất; nếu hòa, dùng quy tắc chọn chỉ số nhỏ nhất để tái hiện.
4. Thêm tập đó và cập nhật hợp đã phủ.
5. Dừng khi đã chọn k tập hoặc không còn tập nào tạo phần tử mới.

Giả mã:

~~~text
GREEDY_MAX_COVERAGE(sets, k):
    chosen = empty list
    covered = empty set
    repeat at most k times:
        best = unchosen set with largest
               |set \ covered|
        if no positive marginal gain:
            stop
        chosen.add(best)
        covered = covered union best
    return chosen, |covered|
~~~

**Phải dùng marginal gain** — số phần tử mới sau khi trừ những phần tử đã phủ. Chọn “tập có kích thước lớn nhất ban đầu” ở mọi lượt mà không tính phần chồng lấn là một thuật toán khác và có thể chọn nhiều tập gần như giống hệt nhau.

## 10. Chứng minh bảo đảm 1−1/e cho Maximum Coverage

Đặt:

- `O=OPT` là số phần tử tối đa có thể phủ bằng ≤k tập;
- `g_i` là số phần tử đã được greedy phủ sau i lượt, `g₀=0`;
- k≥1.

Gọi `T*` là một lời giải tối ưu có không quá k tập. Tính chất của phép hợp tập hợp bảo đảm: tổng số **phần tử mới** nếu lần lượt thêm các tập của T* vào vùng đang phủ không nhỏ hơn `O−g_i`, còn tổng các marginal gain tính **so với cùng tập đang phủ ban đầu** thì lớn hơn hoặc bằng số phần tử chưa phủ của nghiệm tối ưu. Do đó trong các tập của T* tồn tại ít nhất một tập có:

`gain≥(O−g_i)/k`.

Greedy chọn tập có gain lớn nhất trong các tập chưa chọn, nên mức tăng tại lượt sau thỏa:

`g_(i+1)−g_i≥(O−g_i)/k`.

Chuyển vế:

`O−g_(i+1)≤(1−1/k)(O−g_i)`.

Lặp lại:

`O−g_k≤(1−1/k)^k O`,

tức:

`g_k≥[1−(1−1/k)^k]·OPT`.

Vì:

`(1−1/k)^k≤1/e`,

ta có:

`ALG≥(1−1/e)·OPT≈0.63212·OPT`.

Vậy thuật toán tham lam có **bảo đảm ít nhất khoảng 63.2%** số phần tử của nghiệm tối ưu, với mọi đầu vào thuộc mô hình maximum coverage **không trọng số** được xét.

Nếu greedy dừng sớm vì mọi tập còn lại có gain=0, thì không có tập nào thêm được phần tử mới, kể cả các tập của nghiệm tối ưu. Khi ấy giá trị hiện tại đã bằng OPT và bất đẳng thức vẫn đúng.

### Bảo đảm mạnh hơn cho k nhỏ

Bất đẳng thức chi tiết:

`α_k=1−(1−1/k)^k`

thường mạnh hơn 1−1/e. Ví dụ:

- k=1: `α₁=1`; greedy chọn tập lớn nhất, là tối ưu.
- k=2: `α₂=1−(1/2)²=3/4=0.75`.
- k=3: `α₃=1−(2/3)³=19/27≈0.7037`.
- Khi k lớn, α_k giảm dần về `1−1/e≈0.6321`.

Đừng gán nhầm 0.632 là hệ số ρ≥1 của bài MIN. Ở đây đó là **tỉ lệ bảo đảm α của bài MAX**.

## 11. Maximum Coverage: một phản ví dụ greedy không tối ưu

Cho vũ trụ:

`U={0,1,2,3,4,5}`.

Ba tập:

- `S₀={0,1,2,3}`.
- `S₁={0,1,4}`.
- `S₂={2,3,5}`.

Ngân sách `k=2`.

Greedy lượt đầu chọn S₀ vì nó có **4 phần tử**, lớn nhất. Khi đó:

- Thêm S₁ tạo được **1** phần tử mới: 4.
- Thêm S₂ tạo được **1** phần tử mới: 5.

Theo quy tắc hòa chọn chỉ số nhỏ nhất, greedy lấy S₁. Kết quả:

`S₀∪S₁={0,1,2,3,4}`,

`ALG=5`.

Nhưng chọn S₁ và S₂ thì:

`S₁∪S₂={0,1,2,3,4,5}`,

`OPT=6`.

Vì vậy:

`ALG/OPT=5/6≈0.8333`.

Bài MAX dùng tỉ lệ α thực tế khoảng 0.8333, vẫn **lớn hơn bảo đảm α₂=0.75**. Greedy không tối ưu ở đây nhưng hoàn toàn phù hợp với định lý.

### Khi mục tiêu đã bằng 0

Nếu k=0 hoặc mọi tập đều rỗng, cả ALG và OPT có thể bằng 0. **Không in “100% của OPT” từ phép tính 0/0.** Hãy báo ratio không xác định và xác nhận bất đẳng thức bảo đảm bằng số nguyên.

## 12. Cấu trúc bài toán và giới hạn của định lý Maximum Coverage

Định lý trên dựa vào tính:

- **Đơn điệu:** thêm một tập không làm giảm số phần tử phủ.
- **Submodular / lợi ích biên giảm dần:** nếu đã phủ nhiều hơn, cùng một tập mới không thể đóng góp thêm nhiều phần tử hơn trước.
- **Ràng buộc chọn tối đa k tập**, mọi tập có chi phí đơn vị.
- **Giá trị là số phần tử phân biệt**, không phải tổng số lần xuất hiện của phần tử.

Có thể mở rộng định lý cho nhiều hàm submodular đơn điệu không âm dưới ràng buộc cardinality, nhưng không phải **mọi bài MAX** đều có bảo đảm 1−1/e. Nếu các tập có chi phí khác nhau, phần tử có trọng số, ràng buộc nhóm hoặc hàm mục tiêu không submodular, phải thiết kế và chứng minh thuật toán thích hợp.

### So với Set Cover

**Maximum Coverage:** chọn ≤k tập, phủ được **càng nhiều** phần tử càng tốt; thường có bảo đảm greedy 1−1/e.

**Set Cover:** cần phủ **toàn bộ** U, tối thiểu hóa **số tập** hoặc tổng chi phí; greedy có cận dạng số điều hòa/ log theo các giả thiết phù hợp, **không phải** cùng một định lý.

Chỉ vì hai bài đều dùng phép hợp tập hợp không có nghĩa các hệ số xấp xỉ giống nhau.

## 13. Cách kiểm tra tính khả thi trong mã

### Vertex Cover

Với kết quả C, duyệt **mọi cạnh** (u,v). Nếu không có u∈C và v∈C, nghiệm **không khả thi**; khi đó không cần tính tiếp tỉ lệ xấp xỉ.

Cần kiểm tra đỉnh thuộc [0,n), và nếu biểu diễn kết quả bằng mảng chỉ số thì không ghi lặp một đỉnh. Một thuật toán trả danh sách đỉnh quá nhỏ nhưng bỏ sót cạnh không phải “xấp xỉ tốt”.

### Maximum Coverage

Với danh sách chỉ số tập đã chọn:

- Mọi chỉ số trong [0,n).
- Không trùng chỉ số.
- Số tập chọn ≤k.
- Tính số phần tử **phân biệt** của hợp các tập, không cộng kích thước từng tập vì có phần tử chồng lấn.

Trong Java, khi |U|≤20, có thể biểu diễn mỗi tập con bằng một **bitmask int**: bit j bật nếu phần tử j thuộc tập.

- Hợp: `covered |= mask`.
- Phần chưa phủ: `mask & ~covered`.
- Số phần tử: `Integer.bitCount(mask)`.

Biểu diễn này chỉ dành cho vũ trụ nhỏ để mã có thể kiểm thử bằng vét cạn. Với dữ liệu lớn, cần `BitSet`, các cấu trúc tập hợp hoặc danh sách phần tử phù hợp. Không dùng bitmask int 32-bit cho một vũ trụ 100.000 phần tử.

## 14. Độ phức tạp của thuật toán xấp xỉ và oracle

### Vertex Cover 2-approx

- Tạo maximal matching bằng quét một lần: **O(n+m)**.
- Bộ nhớ phụ: O(n).
- Không cần dùng exponential search cho thuật toán xấp xỉ.

### Minimum Vertex Cover tối ưu bằng vét cạn

Với n đỉnh, xét mọi tập con của V:

`2^n` khả năng.

Với mỗi khả năng, kiểm tra có che mọi cạnh và đếm số đỉnh. Chi phí đơn giản:

`O(2^n(n+m))` hoặc tốt hơn một chút nếu có cắt tỉa.

Vì vậy trong Java, oracle được **giới hạn n≤16** để kiểm thử trên đồ thị nhỏ; không dùng oracle này thay thuật toán xấp xỉ trên input lớn.

### Maximum Coverage greedy

Giả sử có s tập, vũ trụ u phần tử, được chọn tối đa k tập.

Nếu dùng bitmask int với u≤20, quét tất cả s tập để tìm marginal gain mất O(s) mỗi lượt, nên tổng khoảng:

`O(k·s)` phép toán bit.

Trong mô hình tổng quát, mỗi phép hợp/đếm có thể mất O(u/w) từ máy bit hoặc thời gian tương ứng với cấu trúc dữ liệu; không bỏ qua chi phí đọc tập con khi phân tích input lớn.

### Maximum Coverage tối ưu bằng vét cạn

Duyệt mọi tập con của s tập, chỉ giữ nhóm có kích thước ≤k, và tính hợp phủ. Cận đơn giản:

`O(2^s·s)` phép toán bit khi u nhỏ.

Oracle Java giới hạn **s≤16**. Chương trình kiểm thử ngẫu nhiên dùng s≤9 nên cách giải chính xác này đủ nhanh để làm chuẩn đối chiếu.

## 15. Có thể biết OPT bằng cách nào?

Trong lớp học, nhiều ví dụ nhỏ có OPT dễ tính bằng tay. Trong dữ liệu thực:

- **Vét cạn/backtracking/branch-and-bound:** có thể tính OPT cho input nhỏ hoặc vừa.
- **Integer Linear Programming (ILP):** mô hình ràng buộc và tối ưu; trình giải có thể tìm nghiệm tối ưu hoặc chứng minh cận.
- **LP relaxation:** bỏ một số ràng buộc nguyên; bài MIN cho cận dưới, bài MAX cho cận trên, nếu thư giãn giữ nguyên tính tương thích với mục tiêu.
- **Dual bound / tổ hợp:** trong Vertex Cover, số cạnh của bất kỳ matching là cận dưới cho số đỉnh tối ưu.
- **Benchmark có đáp án được chứng minh:** dùng để đo chất lượng thực nghiệm, nhưng phải biết đáp án đã được chứng nhận là tối ưu.

Nếu không biết OPT, một báo cáo như “ALG=10” **chưa đủ để tính hệ số**. Có thể báo hai đại lượng:

- Giá trị nghiệm khả thi ALG.
- Một cận chứng nhận L hoặc U.

Khi đó tính được **khoảng chênh có thể chứng nhận**, ví dụ MIN `ALG/L` nếu L>0; nhưng nếu chỉ biết một cận yếu, đây có thể là upper bound thô chứ không phải tỉ số thực tế.

### Integrality gap

Khi dùng LP relaxation, nghiệm LP có thể tốt hơn nghiệm nguyên. **Integrality gap** mô tả chênh lệch giữa OPT nguyên và OPT của bài LP thư giãn (theo quy ước MIN/MAX và miền chi phí phù hợp). Đây là một trở ngại tự nhiên đối với các chứng minh chỉ dựa trên một LP cụ thể.

Ví dụ Minimum Vertex Cover không trọng số có thư giãn LP quen thuộc:

`min Σ_v x_v`

với:

`x_u+x_v≥1` cho mỗi cạnh (u,v),

`0≤x_v≤1`.

Một cách làm tròn là chọn mọi v có `x_v≥1/2`, tạo vertex cover và có hệ số tối đa 2 so với nghiệm LP. Đây là **một chứng minh 2-approx khác** với chứng minh dùng maximal matching trong mã Java.

Lưu ý: **không** vì tìm được nghiệm LP thấp mà tự coi nghiệm phân số là vertex cover nguyên khả thi; phải có bước làm tròn hợp lệ.

## 16. Xấp xỉ theo tỉ lệ và xấp xỉ cộng

Có hai cách đo khoảng cách tới OPT:

### Multiplicative approximation

Bài MIN:

`ALG≤ρ·OPT`.

Bài MAX:

`ALG≥α·OPT`.

Kiểu này nhạy với độ lớn OPT, và cần xử lý riêng OPT=0/giá trị âm.

### Additive approximation

Bài MIN:

`ALG≤OPT+Δ`.

Bài MAX:

`ALG≥OPT−Δ`.

Khoảng sai số cộng Δ có cùng đơn vị với hàm mục tiêu. Đôi khi đây là thước đo phù hợp hơn, đặc biệt khi OPT có thể bằng 0 hoặc mục tiêu có giá trị âm.

**Hai loại không tương đương nếu thiếu giả thiết.** Ví dụ ALG=OPT+5 là sai số cộng 5; với OPT=1000, tỉ số gần 1.005, nhưng với OPT=1, tỉ số là 6.

### Cộng hằng số có thể làm “đẹp” tỉ lệ mà không cải thiện nghiệm

Trong bài MAX có OPT=10, ALG=8, tỉ số là 0.8. Nếu đổi thang mục tiêu thành:

`c'(s)=c(s)+100`,

thứ tự các nghiệm không thay đổi, nhưng tỉ số thành:

`108/110≈0.9818`.

Chất lượng nghiệm **không được cải thiện**. Vì thế các định lý multiplicative approximation gắn với **hàm mục tiêu và chuẩn hóa cụ thể**, không phải với mọi phép đổi thang tùy ý.

## 17. PTAS, FPTAS và heuristic khác gì nhau?

**Thuật toán xấp xỉ hệ số cố định:** ví dụ 2-approx cho Minimum Vertex Cover không trọng số, hoặc 1−1/e cho Maximum Coverage. Bảo đảm có giá trị cho mọi kích thước đầu vào thuộc phạm vi áp dụng.

**PTAS (Polynomial-Time Approximation Scheme):** với mỗi ε>0 cố định, tạo nghiệm gần tối ưu theo hệ số (ví dụ MIN 1+ε) và thời gian đa thức theo kích thước input n, nhưng **bậc đa thức có thể phụ thuộc vào 1/ε**.

**FPTAS (Fully Polynomial-Time Approximation Scheme):** thời gian đa thức **đồng thời theo n và 1/ε**, dưới mô hình mã hóa input và các giả thiết chuẩn. Đây là yêu cầu mạnh hơn PTAS.

**Heuristic:** một phương pháp thực dụng thường cho kết quả tốt trên dữ liệu quan tâm, nhưng **không có chứng minh cận xấp xỉ tệ nhất** (hoặc chưa có chứng minh). Một heuristic có thể vượt thuật toán 2-approx trên nhiều benchmark; nhưng nếu không có bảo đảm, không được tự gọi “1.2-approx”.

**Metaheuristic** như simulated annealing, genetic algorithm hoặc local search cũng cần phân biệt **chất lượng thực nghiệm** với **cận lý thuyết**. Một vòng local search có thể dừng tại cực tiểu cục bộ nhưng chưa phải tối ưu toàn cục.

### Không phải bài NP-hard nào cũng có PTAS

Việc tồn tại PTAS/FPTAS phụ thuộc từng bài và các giả thiết độ phức tạp. Đừng suy từ “có thuật toán 2-approx” sang “có thể tinh chỉnh để đạt (1+ε)-approx cho ε bất kỳ”. Đây là hai loại bảo đảm khác nhau.

## 18. Thuật toán xấp xỉ ngẫu nhiên

Một thuật toán dùng `Random` có thể có bảo đảm:

- **Theo kỳ vọng:** ví dụ trong bài MIN, `E[ALG]≤ρOPT`, với kỳ vọng tính trên các lựa chọn ngẫu nhiên nội bộ, khi input cố định.
- **Với xác suất cao:** `P(ALG≤ρOPT)≥1−δ`.
- **Đúng với mọi lần chạy:** một số thuật toán dùng ngẫu nhiên để tăng tốc nhưng mỗi nghiệm được trả vẫn thỏa bảo đảm cứng.

Đừng nói “expected ρ-approx” nghĩa là mọi seed đều đạt ρ. Nếu thuật toán có khả năng sinh nghiệm **không khả thi**, phải quy định và chứng minh cách xử lý: sửa, từ chối, thử lại hoặc bảo đảm feasibility theo xác suất tương ứng.

Chạy vài trăm seed rồi thấy tỉ số tốt **không chứng minh kỳ vọng hay bound xác suất**. Thí nghiệm giúp phát hiện bug và ước lượng hiệu suất trong phạm vi dữ liệu, nhưng định lý cần lập luận xác suất.

## 19. Java 17+: hai thuật toán có chứng minh và oracle độc lập

Chương trình **`ApproximationGuaranteesDemo.java`** minh họa cả bài MIN và MAX:

- `Graph` là đồ thị vô hướng đơn **không có self-loop**; có thể có danh sách cạnh rỗng.
- `approxVertexCover` quét cạnh và chọn cả hai đầu của một maximal matching.
- `isVertexCover` kiểm tra **từng cạnh** được che, đồng thời từ chối chỉ số trùng/không hợp lệ.
- `exactVertexCover` duyệt toàn bộ 2^n tập đỉnh với n≤16 làm oracle.
- `CoverageInstance` biểu diễn tập con U bằng bitmask int, giới hạn 1≤|U|≤20.
- `greedyMaxCoverage` chọn tập có **marginal gain** lớn nhất, hòa thì lấy chỉ số nhỏ nhất.
- `exactMaxCoverage` duyệt mọi nhóm ≤k tập với số lượng tập s≤16 làm oracle.
- `verifyCoverage` xác nhận tập được chọn đúng phạm vi, không trùng và số phần tử phủ khớp.
- `coverageFactor(k)` tính `1−(1−1/k)^k` cho k≥1.
- `randomChecks` kiểm 500 đồ thị và 500 bài maximum coverage bằng so sánh với oracle vét cạn.

Dùng oracle vét cạn **chỉ để kiểm thử**; thuật toán xấp xỉ không cần oracle để tính nghiệm trên input thật.

### Chương trình đầy đủ

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Random;

public class ApproximationGuaranteesDemo {
    record Edge(int u, int v) {}

    record Graph(int vertexCount, List<Edge> edges) {
        Graph {
            if (vertexCount < 0 || edges == null) {
                throw new IllegalArgumentException("Invalid graph");
            }
            edges = List.copyOf(edges);
            for (Edge edge : edges) {
                if (edge.u() < 0 || edge.v() < 0
                        || edge.u() >= vertexCount
                        || edge.v() >= vertexCount
                        || edge.u() == edge.v()) {
                    throw new IllegalArgumentException(
                            "Expected loop-free valid edges");
                }
            }
        }
    }

    record CoverResult(int[] vertices, int matchingSize) {
        CoverResult { vertices = vertices.clone(); }

        @Override
        public int[] vertices() { return vertices.clone(); }
    }

    static CoverResult approxVertexCover(Graph graph) {
        boolean[] chosen = new boolean[graph.vertexCount()];
        int matchingSize = 0;

        // Maximal matching: use an edge only when BOTH
        // endpoints are not incident to an earlier match.
        for (Edge edge : graph.edges()) {
            int u = edge.u(), v = edge.v();
            if (!chosen[u] && !chosen[v]) {
                chosen[u] = true;
                chosen[v] = true;
                matchingSize++;
            }
        }

        int[] selected = new int[2 * matchingSize];
        int index = 0;
        for (int v = 0; v < chosen.length; v++) {
            if (chosen[v]) selected[index++] = v;
        }
        return new CoverResult(selected, matchingSize);
    }

    static boolean isVertexCover(Graph graph, int[] vertices) {
        boolean[] chosen = new boolean[graph.vertexCount()];
        for (int v : vertices) {
            if (v < 0 || v >= chosen.length || chosen[v])
                return false;
            chosen[v] = true;
        }
        for (Edge edge : graph.edges()) {
            if (!chosen[edge.u()] && !chosen[edge.v()])
                return false;
        }
        return true;
    }

    static int exactVertexCover(Graph graph) {
        int n = graph.vertexCount();
        if (n > 16) {
            throw new IllegalArgumentException(
                    "Exponential oracle supports n <= 16");
        }
        int optimum = n;
        for (int mask = 0; mask < (1 << n); mask++) {
            int count = Integer.bitCount(mask);
            if (count >= optimum) continue;

            boolean feasible = true;
            for (Edge edge : graph.edges()) {
                if ((mask & (1 << edge.u())) == 0
                        && (mask & (1 << edge.v())) == 0) {
                    feasible = false;
                    break;
                }
            }
            if (feasible) optimum = count;
        }
        return optimum;
    }

    static void showCover(String label, Graph graph) {
        CoverResult solution = approxVertexCover(graph);
        if (!isVertexCover(graph, solution.vertices())) {
            throw new AssertionError("Vertex cover infeasible");
        }

        int optimum = exactVertexCover(graph);
        int size = solution.vertices().length;
        boolean bound = size <= 2 * optimum
                && size == 2 * solution.matchingSize();

        if (!bound) {
            throw new AssertionError("2-approximation violated");
        }

        String ratio = optimum == 0
                ? "undefined"
                : String.format(Locale.ROOT,
                        "%.3f", (double) size / optimum);

        System.out.printf(Locale.ROOT,
                "%s cover=%s matching=%d optimum=%d"
                + " ratio=%s bound2=%s%n",
                label, Arrays.toString(solution.vertices()),
                solution.matchingSize(), optimum, ratio, bound);
    }

    record CoverageInstance(int universeSize, int[] masks,
            int budget) {
        CoverageInstance {
            if (masks == null
                    || universeSize < 1 || universeSize > 20
                    || budget < 0 || budget > masks.length) {
                throw new IllegalArgumentException(
                        "Invalid coverage instance");
            }
            masks = masks.clone();
            int limit = 1 << universeSize;
            for (int mask : masks) {
                if (mask < 0 || mask >= limit)
                    throw new IllegalArgumentException(
                            "Mask exceeds the universe");
            }
        }

        @Override
        public int[] masks() { return masks.clone(); }
    }

    record CoverageResult(int[] selected, int coveredCount) {
        CoverageResult { selected = selected.clone(); }

        @Override
        public int[] selected() { return selected.clone(); }
    }

    static CoverageResult greedyMaxCoverage(
            CoverageInstance instance) {
        int[] masks = instance.masks();
        boolean[] used = new boolean[masks.length];
        int[] chosen = new int[instance.budget()];
        int count = 0;
        int union = 0;

        for (int step = 0; step < instance.budget(); step++) {
            int best = -1;
            int gain = 0;

            for (int j = 0; j < masks.length; j++) {
                if (used[j]) continue;
                int newElements =
                        Integer.bitCount(masks[j] & ~union);
                if (newElements > gain) {
                    gain = newElements;
                    best = j;
                }
            }

            // Nothing else increases the covered union.
            if (best == -1) break;

            used[best] = true;
            chosen[count++] = best;
            union |= masks[best];
        }

        return new CoverageResult(
                Arrays.copyOf(chosen, count),
                Integer.bitCount(union));
    }

    static int exactMaxCoverage(CoverageInstance instance) {
        int[] masks = instance.masks();
        if (masks.length > 16) {
            throw new IllegalArgumentException(
                    "Exponential oracle supports <=16 sets");
        }
        int optimum = 0;
        for (int subset = 0; subset < (1 << masks.length);
                subset++) {
            if (Integer.bitCount(subset) > instance.budget())
                continue;
            int union = 0;
            for (int i = 0; i < masks.length; i++) {
                if ((subset & (1 << i)) != 0)
                    union |= masks[i];
            }
            optimum = Math.max(
                    optimum, Integer.bitCount(union));
        }
        return optimum;
    }

    static boolean verifyCoverage(
            CoverageInstance instance, CoverageResult result) {
        int[] masks = instance.masks();
        int[] indices = result.selected();
        if (indices.length > instance.budget()) return false;

        boolean[] used = new boolean[masks.length];
        int union = 0;
        for (int index : indices) {
            if (index < 0 || index >= masks.length || used[index])
                return false;
            used[index] = true;
            union |= masks[index];
        }
        return Integer.bitCount(union) == result.coveredCount();
    }

    static double coverageFactor(int k) {
        if (k <= 0) return 0.0;
        return 1.0 - Math.pow(1.0 - 1.0 / k, k);
    }

    static boolean coverageGuarantee(
            CoverageInstance instance,
            CoverageResult result, int optimum) {
        if (instance.budget() == 0)
            return optimum == 0 && result.coveredCount() == 0;
        return result.coveredCount() + 1e-9
                >= coverageFactor(instance.budget()) * optimum;
    }

    static void showCoverage(
            String label, CoverageInstance instance) {
        CoverageResult greedy = greedyMaxCoverage(instance);
        if (!verifyCoverage(instance, greedy)) {
            throw new AssertionError("Infeasible coverage result");
        }

        int optimum = exactMaxCoverage(instance);
        if (greedy.coveredCount() > optimum
                || !coverageGuarantee(instance, greedy, optimum)) {
            throw new AssertionError(
                    "Coverage approximation bound failed");
        }

        String ratio = optimum == 0 ? "undefined"
                : String.format(Locale.ROOT,
                        "%.3f",
                        (double) greedy.coveredCount() / optimum);

        System.out.printf(Locale.ROOT,
                "%s chosen=%s covered=%d optimum=%d"
                + " fraction=%s guarantee=%s%n",
                label, Arrays.toString(greedy.selected()),
                greedy.coveredCount(), optimum, ratio, true);
    }

    static void randomChecks() {
        Random random = new Random(4702026L);

        for (int test = 0; test < 500; test++) {
            int n = 1 + random.nextInt(10);
            List<Edge> edges = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = u + 1; v < n; v++) {
                    if (random.nextDouble() < 0.30)
                        edges.add(new Edge(u, v));
                }
            }

            Graph graph = new Graph(n, edges);
            CoverResult approx = approxVertexCover(graph);
            int opt = exactVertexCover(graph);
            if (!isVertexCover(graph, approx.vertices())
                    || approx.vertices().length > 2 * opt
                    || approx.vertices().length
                            != 2 * approx.matchingSize()) {
                throw new AssertionError(
                        "Failed randomized Vertex Cover test");
            }
        }
        System.out.println("graphRandom=PASS (500 cases)");

        for (int test = 0; test < 500; test++) {
            int universe = 1 + random.nextInt(12);
            int count = 1 + random.nextInt(9);
            int[] masks = new int[count];
            for (int i = 0; i < count; i++)
                masks[i] = random.nextInt(1 << universe);

            int budget = random.nextInt(
                    Math.min(count, 4) + 1);
            CoverageInstance instance =
                    new CoverageInstance(universe, masks, budget);
            CoverageResult approx = greedyMaxCoverage(instance);
            int opt = exactMaxCoverage(instance);

            if (!verifyCoverage(instance, approx)
                    || approx.coveredCount() > opt
                    || !coverageGuarantee(instance, approx, opt)) {
                throw new AssertionError(
                        "Failed randomized Coverage test");
            }
        }
        System.out.println("coverageRandom=PASS (500 cases)");
    }

    public static void main(String[] args) {
        Graph path = new Graph(4, List.of(
                new Edge(0, 1),
                new Edge(1, 2),
                new Edge(2, 3)));
        Graph triangle = new Graph(3, List.of(
                new Edge(0, 1),
                new Edge(1, 2),
                new Edge(0, 2)));
        Graph star = new Graph(6, List.of(
                new Edge(0, 1), new Edge(0, 2),
                new Edge(0, 3), new Edge(0, 4),
                new Edge(0, 5)));
        Graph empty = new Graph(5, List.of());

        showCover("path", path);
        showCover("triangle", triangle);
        showCover("star", star);
        showCover("empty", empty);

        // Intentional weighted counterexample:
        // the unweighted 2-approximation does NOT apply.
        int selectedBothWeight = 100 + 1;
        int optimalWeight = 1;
        System.out.println(
                "weightedCounterexample greedyCost="
                + selectedBothWeight + " optimum=" + optimalWeight
                + " bound2=" + (selectedBothWeight <= 2*optimalWeight));

        // 3 sets on 6 elements; k=2.
        // S0={0,1,2,3}, S1={0,1,4}, S2={2,3,5}.
        CoverageInstance gap =
                new CoverageInstance(6,
                        new int[]{15, 19, 44}, 2);
        showCoverage("coverageGap", gap);

        CoverageInstance full =
                new CoverageInstance(6,
                        new int[]{7, 24, 32}, 3);
        showCoverage("coverageFull", full);

        CoverageInstance zero =
                new CoverageInstance(6,
                        new int[]{15, 19, 44}, 0);
        showCoverage("zeroBudget", zero);

        try {
            new Graph(2, List.of(new Edge(0, 0)));
            throw new AssertionError("Expected self-loop rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("selfLoop=rejected");
        }

        try {
            new CoverageInstance(3, new int[]{8}, 1);
            throw new AssertionError("Expected invalid mask rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidMask=rejected");
        }

        randomChecks();
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 ApproximationGuaranteesDemo.java
java ApproximationGuaranteesDemo
~~~

**Đầu ra dự kiến chính xác:**

~~~text
path cover=[0, 1, 2, 3] matching=2 optimum=2 ratio=2.000 bound2=true
triangle cover=[0, 1] matching=1 optimum=2 ratio=1.000 bound2=true
star cover=[0, 1] matching=1 optimum=1 ratio=2.000 bound2=true
empty cover=[] matching=0 optimum=0 ratio=undefined bound2=true
weightedCounterexample greedyCost=101 optimum=1 bound2=false
coverageGap chosen=[0, 1] covered=5 optimum=6 fraction=0.833 guarantee=true
coverageFull chosen=[0, 1, 2] covered=6 optimum=6 fraction=1.000 guarantee=true
zeroBudget chosen=[] covered=0 optimum=0 fraction=undefined guarantee=true
selfLoop=rejected
invalidMask=rejected
graphRandom=PASS (500 cases)
coverageRandom=PASS (500 cases)
~~~

### Giải thích kết quả

**path:** matching có hai cạnh không giao nhau; chọn cả bốn đầu mút cho ALG=4, trong khi oracle vét cạn tìm OPT=2. Tỉ số thực tế 2.000, chạm đúng cận 2-approx.

**triangle:** thuật toán chọn hai đầu mút của cạnh đầu tiên; đây cũng là một vertex cover tối ưu kích thước 2, tỉ số 1.000.

**star:** một cạnh matching dẫn tới chọn tâm và một lá; nghiệm tối ưu chỉ cần tâm. Thuật toán đạt đúng tỉ số 2.

**empty:** đồ thị không có cạnh có nghiệm rỗng với chi phí 0. Bất đẳng thức ALG≤2OPT đúng, nhưng tỉ số 0/0 không được định nghĩa.

**weightedCounterexample:** chỉ một cạnh có trọng số hai đỉnh là 100 và 1. Chọn cả hai tốn 101, nghiệm tối ưu chỉ tốn 1. Đây là lý do **không chuyển chứng minh unweighted** sang weighted.

**coverageGap:** greedy chọn S₀ rồi S₁, phủ 5 trong 6 phần tử, trong khi oracle chọn S₁ và S₂ phủ đủ 6. Tỉ lệ 5/6≈0.833, vượt bảo đảm α₂=0.75.

**coverageFull:** với k=3, ba tập không chồng lấn phủ trọn vũ trụ sáu phần tử. ALG=OPT=6.

**zeroBudget:** không được chọn tập nào, do đó ALG=OPT=0; tỉ số thực nghiệm không xác định nhưng ràng buộc và bảo đảm đều hợp lệ.

**selfLoop:** đồ thị được mô hình như đồ thị đơn không có self-loop; constructor từ chối đầu vào có cạnh (0,0), tránh áp chứng minh matching cho tình huống không nằm trong mô hình.

**invalidMask:** vũ trụ kích thước 3 chỉ cho phép bit 0,1,2; mask 8 sử dụng bit thứ 3 nên bị từ chối.

**graphRandom:** 500 đồ thị có tối đa 10 đỉnh, đủ nhỏ để tính **OPT chính xác** bằng toàn bộ 2^n tập đỉnh. Mỗi lần đều xác nhận vertex cover khả thi và `|C|≤2OPT`.

**coverageRandom:** 500 trường hợp có vũ trụ ≤12 phần tử, ≤9 tập và k≤4. Oracle duyệt toàn bộ tổ hợp tập được chọn (bao gồm tập rỗng); mọi lần đều kiểm tra tính khả thi, ALG≤OPT và `ALG≥α_k OPT`.

**Giới hạn:** các kiểm thử có seed và số trường hợp hữu hạn chỉ chứng minh mã làm đúng trên dữ liệu thử. **Chứng minh hệ số tệ nhất** đến từ các lập luận matching và marginal gain ở trên, không đến từ việc 500 test đều PASS.

## 20. Phân tích đúng sai của thuật toán và oracle

### 20.1. Tính khả thi Vertex Cover

Mỗi cạnh được quét:

- Nếu cả hai đầu chưa chọn, cả hai lập tức được đưa vào C.
- Nếu có đầu đã chọn, cạnh ấy đã được che.

Vì vậy sau khi duyệt hết, mọi cạnh đều được che. Bất biến này bảo đảm kết quả **khả thi cho mọi đồ thị vô hướng đơn**.

### 20.2. Chứng minh xấp xỉ Vertex Cover

Mỗi lần chọn một cạnh matching mới, các đầu mút chưa thuộc những cạnh matching trước, nên cạnh mới không chia sẻ đầu mút với M. OPT phải chứa ít nhất một đỉnh của từng cạnh trong M, suy ra `OPT≥|M|`. Thuật toán chọn chính xác 2|M| đỉnh, nên `ALG≤2OPT`.

### 20.3. Tính khả thi Maximum Coverage

Mỗi lượt greedy chọn một chỉ số chưa dùng, giới hạn tối đa k lượt. Dữ liệu dùng bitmask hợp lệ thuộc vũ trụ nên union không có bit ngoài miền. Hàm `verifyCoverage` tính lại hợp các tập đã chọn và đối chiếu số phần tử phủ được báo.

### 20.4. Chứng minh xấp xỉ Maximum Coverage

Do một nghiệm tối ưu dùng không quá k tập, trong bước greedy thứ i phải tồn tại một tập trong nghiệm tối ưu với marginal gain ít nhất `(OPT−g_i)/k`, trừ trường hợp đã đạt OPT. Greedy chọn gain lớn nhất, do đó phần thiếu tối ưu bị nhân nhiều nhất với `1−1/k` sau mỗi lượt. Sau k lượt có `ALG≥[1−(1−1/k)^k]OPT`.

### 20.5. Oracle vét cạn độc lập

Hai oracle không sử dụng công thức chọn của thuật toán xấp xỉ:

- `exactVertexCover` thử từng mask của các đỉnh và chấp nhận nếu **mọi cạnh** được che.
- `exactMaxCoverage` thử từng mask của các tập có số lượng được chọn ≤k và tính trực tiếp số phần tử trong union.

Nhờ vậy chúng có thể phát hiện lỗi chọn cạnh, lỗi marginal gain, lỗi tính objective và lỗi mất tính khả thi, thay vì chỉ so thuật toán với chính nó.

## 21. So sánh hệ số với chất lượng thực tế

Một thuật toán 2-approx không nhất thiết tệ hơn một heuristic không có bảo đảm khi chạy trên một vài bộ dữ liệu. Trên benchmark, có thể thấy:

| Đầu vào | OPT | Thuật toán 2-approx | Tỉ số thực tế |
| --- | ---: | ---: | ---: |
| Đường đi 4 đỉnh | 2 | 4 | 2.0 |
| Tam giác | 2 | 2 | 1.0 |
| Sao 6 đỉnh | 1 | 2 | 2.0 |

Nhìn vào cột tỉ số thực tế có ích để **đo chất lượng trên tập dữ liệu**, nhưng bảo đảm 2-approx độc lập với bảng này.

Nếu một heuristic khác trả 2 trên đường đi bốn đỉnh, tức đạt OPT, nó tốt hơn trong trường hợp ấy. Nhưng nếu chưa chứng minh bound cho mọi đồ thị, không được gọi heuristic đó là một thuật toán 1-approx tổng quát.

### Những phép đo đáng ghi lại

- Feasibility rate: tỉ lệ đầu ra thỏa ràng buộc (lý tưởng là 100% với thuật toán approximation chuẩn).
- Giá trị ALG và nghiệm cụ thể.
- OPT nếu tính được, hoặc cận L/U chứng nhận.
- Tỉ số thực tế với OPT>0.
- Thời gian và bộ nhớ.
- Kích thước và cấu trúc dữ liệu (n,m,k,độ thưa, sự chồng lấn các tập).
- Seed nếu thuật toán dùng ngẫu nhiên.
- Các trường hợp input đạt gần cận xấu nhất.

Không được **bỏ những input khó ra khỏi bảng kết quả** sau khi nhìn thấy tỉ số. Cách làm ấy tạo thiên lệch đánh giá.

## 22. Những lỗi suy luận thường gặp

1. Tính hệ số xấp xỉ cho một nghiệm **không khả thi**.
2. Chỉ đưa ra giá trị số mà không thể tái tạo nghiệm.
3. Nhầm “đã tìm một nghiệm” với “đã tìm tối ưu”.
4. Nhầm MIN với MAX khi đặt chiều bất đẳng thức.
5. Dùng `ALG≤ρOPT` của MIN cho MAX mà không đổi cách đo.
6. Dùng α<1 của MAX rồi gọi là hệ số ρ≥1.
7. Cho rằng ρ nhỏ hơn 1 luôn tốt cho bài MIN.
8. Cho rằng α lớn hơn 1 luôn tốt cho bài MAX.
9. Chia ALG/OPT khi OPT=0.
10. Áp định nghĩa hệ số thông thường cho hàm có giá trị âm mà không quy ước.
11. Cộng hằng số vào objective để làm đẹp tỉ số.
12. Dùng một nghiệm khả thi của bài MIN làm **cận dưới** OPT.
13. Dùng một nghiệm khả thi của bài MAX làm **cận trên** OPT.
14. Tuyên bố có chứng nhận 2-approx nhưng không chỉ ra cận dưới/cận trên chứng minh.
15. Nhầm một matching cực đại với matching có kích thước lớn nhất.
16. Lấy đầu mút của một matching chưa maximal rồi bỏ sót cạnh.
17. Chuyển 2-approx Vertex Cover không trọng số sang bài weighted mà không có chứng minh.
18. Quên kiểm tra đồ thị có self-loop khi chứng minh chỉ dành cho đồ thị đơn.
19. Cho rằng chọn cả hai đầu mút của mọi cạnh là 2-approx (có thể chọn rất nhiều đỉnh so với OPT).
20. Đếm số phần tử phủ bằng tổng độ lớn các tập, quên loại phần chồng lấn.
21. Chọn tập maximum coverage chỉ theo **kích thước gốc**, không cập nhật marginal gain.
22. Chọn quá k tập rồi vẫn báo đó là nghiệm khả thi.
23. Chọn lặp chỉ số tập dù bài chỉ cho chọn mỗi tập một lần.
24. Cho rằng greedy maximum coverage luôn tìm OPT.
25. Nhầm bài Maximum Coverage với Minimum Set Cover.
26. Áp α=1−1/e cho hàm mục tiêu không đơn điệu hoặc không submodular.
27. Áp định lý với ràng buộc chi phí khác nhau mà không điều chỉnh thuật toán.
28. Dùng oracle vét cạn trên n lớn rồi kết luận thuật toán xấp xỉ chậm theo hàm mũ.
29. Dùng test ngẫu nhiên 500 lần làm chứng minh hệ số tệ nhất.
30. Chỉ test các input dễ rồi tuyên bố tỉ số thực nghiệm là cận tổng quát.
31. Nhầm expected approximation với bảo đảm đúng trên **mọi lần chạy**.
32. Trộn lẫn cận cộng và cận nhân.
33. Cho rằng có một thuật toán 2-approx thì chắc chắn tồn tại PTAS.
34. Cho rằng một heuristic cho kết quả tốt trên benchmark là thuật toán xấp xỉ có chứng minh.
35. Không chứng minh tính khả thi trước khi chứng minh hệ số.
36. Quên kiểm tra OPT tồn tại hay đầu vào bị vô nghiệm.
37. Quên rằng LP optimum của bài thư giãn chưa chắc là nghiệm nguyên khả thi.
38. Không đặt rõ giả thiết đồ thị không trọng số hoặc phần tử có trọng số.
39. Không báo quy tắc hòa khi muốn output cố định giữa nhiều lần chạy.
40. Coi “bound2=true” của một ví dụ là bằng chứng định lý, thay vì dùng chứng minh tổ hợp.

## 23. Bài tập có lời giải

**Bài 1.** Nghiệm khả thi là gì? **Đáp án:** nghiệm thỏa **mọi ràng buộc** của đầu vào.

**Bài 2.** Với bài MIN, giá trị nghiệm khả thi có quan hệ gì với OPT? **Đáp án:** `ALG≥OPT`.

**Bài 3.** Với bài MAX, quan hệ tương ứng? **Đáp án:** `ALG≤OPT`.

**Bài 4.** Bảo đảm 2-approx của MIN là bất đẳng thức nào? **Đáp án:** `ALG≤2OPT`.

**Bài 5.** Với MAX có α=0.8, ý nghĩa? **Đáp án:** `ALG≥0.8OPT`, ít nhất 80% giá trị tối ưu.

**Bài 6.** α=0.8 của MAX tương ứng ρ≥1 bằng bao nhiêu? **Đáp án:** `ρ=1/0.8=1.25`.

**Bài 7.** Nếu ALG=12, OPT=8 ở bài MIN, tỉ số thực tế? **Đáp án:** 1.5.

**Bài 8.** Nếu ALG=8, OPT=10 ở bài MAX, fraction thực tế? **Đáp án:** 0.8.

**Bài 9.** OPT=0, ALG=0 thì ALG/OPT bằng bao nhiêu? **Đáp án:** không xác định; xét bất đẳng thức bảo đảm thay vì chia 0/0.

**Bài 10.** Vì sao kết quả không khả thi có objective rất tốt vẫn vô nghĩa? **Đáp án:** OPT chỉ so trên **tập nghiệm khả thi**.

**Bài 11.** Với MIN, cận nào L≤OPT giúp chứng minh ρ-approx? **Đáp án:** nếu ALG≤ρL, suy ra ALG≤ρOPT.

**Bài 12.** Với MAX, cận nào U≥OPT giúp chứng minh α-approx? **Đáp án:** nếu ALG≥αU, suy ra ALG≥αOPT.

**Bài 13.** Trong Vertex Cover, tập C phải có tính chất gì? **Đáp án:** mọi cạnh có ít nhất một đầu mút thuộc C.

**Bài 14.** Một matching là gì? **Đáp án:** tập cạnh không chia sẻ đỉnh.

**Bài 15.** Maximal matching có phải maximum matching không? **Đáp án:** không; maximal chỉ là không thêm được cạnh nào.

**Bài 16.** Vì sao số cạnh matching là cận dưới cho OPT Vertex Cover? **Đáp án:** mỗi cạnh matching cần một đỉnh che riêng biệt vì các cạnh không chia sẻ đầu mút.

**Bài 17.** Vì sao thuật toán maximal matching chọn 2|M| đỉnh? **Đáp án:** chọn cả hai đầu mút của mỗi cạnh và các cạnh M không giao nhau.

**Bài 18.** Từ `OPT≥|M|` và `ALG=2|M|` suy ra gì? **Đáp án:** `ALG≤2OPT`.

**Bài 19.** Với đường đi 4 đỉnh có ba cạnh liên tiếp, nghiệm greedy trên thứ tự bài? **Đáp án:** {0,1,2,3}; OPT=2; tỉ số 2.

**Bài 20.** Với tam giác, greedy chọn 0,1 có tối ưu không? **Đáp án:** có, OPT=2 và ALG=2.

**Bài 21.** Với sao năm lá, greedy chọn tâm và một lá có giá trị bao nhiêu? **Đáp án:** 2, trong khi OPT=1.

**Bài 22.** Với Vertex Cover trọng số 100 và 1 trên một cạnh, chọn cả hai có tỉ số? **Đáp án:** 101/1=101; không là 2-approx.

**Bài 23.** Maximum Coverage chọn nhiều nhất k tập hay đúng k tập? **Đáp án:** **nhiều nhất k** tập trong mô hình bài, có thể dừng sớm nếu thêm tập không tăng phủ.

**Bài 24.** Marginal gain của S so với vùng A là gì? **Đáp án:** `|S \ A|`.

**Bài 25.** Vì sao không dùng kích thước gốc |S| thay marginal gain? **Đáp án:** các phần tử đã được phủ không tạo thêm giá trị.

**Bài 26.** Với U={0,…,5}, các tập S₀,S₁,S₂ trong ví dụ, k=2, greedy phủ bao nhiêu? **Đáp án:** 5.

**Bài 27.** Với ví dụ ấy, OPT bằng bao nhiêu? **Đáp án:** 6 nhờ S₁ và S₂.

**Bài 28.** Fraction của greedy trong bài 27? **Đáp án:** 5/6≈0.8333.

**Bài 29.** Bảo đảm α_k của max coverage greedy? **Đáp án:** `1−(1−1/k)^k` với k≥1.

**Bài 30.** Với k=2, α_k bằng bao nhiêu? **Đáp án:** 3/4.

**Bài 31.** Khi k tăng lớn, α_k tiến tới giới hạn nào? **Đáp án:** `1−1/e≈0.63212`.

**Bài 32.** Với MAX, α=1−1/e tương đương ρ khoảng bao nhiêu? **Đáp án:** `1/(1−1/e)≈1.582`.

**Bài 33.** Vì sao có thể dùng bitmask int với vũ trụ 6 phần tử? **Đáp án:** mỗi phần tử tương ứng một bit; OR là phép hợp và bitCount là số phần tử phân biệt.

**Bài 34.** Khi có k=0, một lời giải max coverage khả thi được chọn bao nhiêu tập? **Đáp án:** 0 tập, có giá trị phủ 0.

**Bài 35.** Vét cạn Vertex Cover có bao nhiêu lựa chọn tập đỉnh với n đỉnh? **Đáp án:** 2^n.

**Bài 36.** Vét cạn Maximum Coverage xét tối đa bao nhiêu tập con của s tập? **Đáp án:** 2^s, rồi loại những tập con có kích thước >k.

**Bài 37.** PTAS và FPTAS khác nhau ở yêu cầu nào? **Đáp án:** PTAS đa thức theo n với ε cố định; FPTAS đa thức đồng thời theo n và 1/ε.

**Bài 38.** Thấy 100 input có tỉ số 1.1 có chứng minh 1.1-approx không? **Đáp án:** không; cận tệ nhất cần chứng minh mọi input trong phạm vi.

**Bài 39.** Thuật toán có bảo đảm kỳ vọng `E[ALG]≤2OPT` của MIN có chắc mọi lần chạy ≤2OPT không? **Đáp án:** không, kỳ vọng và bảo đảm theo từng lần là hai tính chất khác nhau.

**Bài 40.** Trong báo cáo benchmark, nên ghi những gì để đánh giá xấp xỉ? **Đáp án:** nghiệm và feasibility, ALG, OPT/cận chứng nhận, tỉ số khi hợp lệ, quy mô đầu vào, thời gian, bộ nhớ và seed nếu có ngẫu nhiên.

## 24. Checklist áp dụng thực tế

1. Đã xác định đúng đầu vào, miền nghiệm ứng viên và **tất cả ràng buộc** chưa?
2. Hàm mục tiêu có thuộc bài MIN hay MAX?
3. Thuật toán có tạo **nghiệm khả thi** chứ không chỉ một con số không?
4. Có tính giá trị ALG từ đúng nghiệm đã tạo không?
5. Đã xác định OPT là giá trị tốt nhất trên **toàn bộ nghiệm khả thi** chưa?
6. OPT có thể bằng 0 hoặc âm không; đã quy ước thước đo thích hợp?
7. Đối với MIN, hệ số có dạng `ALG≤ρOPT` với ρ≥1?
8. Đối với MAX, hệ số có dạng `ALG≥αOPT` với α≤1, hoặc dùng đúng ρ=1/α?
9. Có phân biệt hệ số được **chứng minh cho mọi input** và tỉ số chỉ quan sát trên benchmark?
10. Có một **cận dưới** cho OPT của MIN hoặc một **cận trên** cho OPT của MAX đủ để chứng minh không?
11. Nếu dùng matching cho Vertex Cover, matching tạo được có **maximal** không?
12. Tập đỉnh trả ra có che được mọi cạnh không?
13. Có tránh áp cận 2 của bài không trọng số cho weighted Vertex Cover không?
14. Nếu giải Maximum Coverage, có tính gain là **số phần tử mới** không?
15. Danh sách tập chọn có không lặp và không quá k tập không?
16. Có biết và kiểm tra giả thiết **monotone/submodular/cardinality constraint** của bảo đảm 1−1/e không?
17. Có phân biệt Maximum Coverage với Minimum Set Cover không?
18. Nếu dữ liệu lớn, có tránh dùng brute force và bitmask quá khả năng biểu diễn không?
19. Nếu cần xác minh thuật toán, có oracle exact trên input nhỏ **độc lập với logic chọn greedy** không?
20. Có test trường hợp OPT=0, đồ thị rỗng, hoán đổi thứ tự cạnh và bài gần cận xấu nhất không?
21. Đã ghi thời gian, bộ nhớ, giá trị nghiệm và seed khi đo chất lượng thực tế chưa?
22. Có phân biệt bảo đảm worst case với expectation/high probability nếu thuật toán ngẫu nhiên không?
23. Nếu dùng LP relaxation, có biết cận LP nằm phía nào của OPT và cách làm tròn nghiệm phân số?
24. Nếu dùng PTAS/FPTAS, có ghi rõ tham số ε và độ phức tạp theo n, 1/ε?
25. Nếu chỉ có heuristic, có báo trung thực **chưa có bảo đảm hệ số xấp xỉ** không?
26. Nếu vấn đề thay đổi hàm mục tiêu hoặc thêm trọng số, có chứng minh lại hệ số thay vì sao chép kết luận cũ không?

**Ghi nhớ:** một thuật toán xấp xỉ đáng tin phải có **(1) nghiệm khả thi**, **(2) giá trị mục tiêu ALG đúng**, và **(3) một chứng minh so sánh với OPT**. Với MIN, tìm **cận dưới** để chứng minh `ALG≤ρOPT`; với MAX, tìm **cận trên** hoặc phân tích marginal gain để chứng minh `ALG≥αOPT`. Ví dụ Vertex Cover không trọng số dùng maximal matching cho **ρ=2**, còn Maximum Coverage dùng greedy marginal gain cho **α≥1−1/e**. Một tỉ số quan sát được trên vài input chỉ là **kết quả thực nghiệm**, không thay thế chứng minh độ bảo đảm tệ nhất.

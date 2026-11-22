# Thuật toán Hungarian

**Hungarian algorithm (thuật toán Hungary / Kuhn–Munkres)** giải **bài toán phân công có trọng số**: mỗi người, máy hoặc tác vụ ở một phía phải được ghép với **đúng một** đối tượng phía còn lại, không đối tượng nào bị dùng quá một lần, sao cho **tổng chi phí nhỏ nhất** hoặc **tổng lợi ích lớn nhất**.

Trong nhóm **Ghép cặp và phân công**, đây là kỹ thuật quan trọng khi phải tối ưu **tổng trọng số của ghép cặp hai phía**, khác với chỉ hỏi **có bao nhiêu cặp** như matching không trọng số.

Một bài toán mẫu:

- Có n nhân viên và m công việc.
- Chi phí giao nhân viên i làm công việc j là **cost[i][j]**.
- Mỗi nhân viên phải nhận **đúng một công việc**.
- Mỗi công việc được giao cho **tối đa một nhân viên**.
- Cần **minimize tổng cost**.
- Trong phiên bản ma trận chữ nhật được dùng ở bài, **n ≤ m**, tức là có đủ số công việc về mặt đếm; một số cặp nhân viên–công việc vẫn có thể **bị cấm**, làm bài toán vô nghiệm.

Nếu n=m và mọi cặp đều hợp lệ, đây là **bài toán phân công hình vuông**. Nếu n<m, một số công việc được phép **không dùng**.

Thuật toán Hungarian giúp tối ưu toàn cục, không phải chọn ô rẻ nhất lần lượt cho từng hàng. Phiên bản trình bày dưới đây dùng **thế năng (potentials)** và **đường tăng (augmenting paths)**, cài đặt **O(n²m)** khi n≤m, với ma trận chi phí được lưu sẵn; riêng n=m là **O(n³)**. Chương trình Java 17+ dùng **BigInteger** cho các phép tính để xử lý chính xác chi phí âm, Long.MIN_VALUE và tổng chi phí vượt long, đồng thời hỗ trợ các cặp **bị cấm**.

## 1. Mô hình ghép cặp hai phía có trọng số

Cho hai tập không giao nhau:

- **L**: n đỉnh bên trái, ví dụ nhân viên.
- **R**: m đỉnh bên phải, ví dụ công việc.

Một cạnh hợp lệ (i,j) biểu thị rằng i có thể được phân công tới j, với chi phí cᵢⱼ. Một **matching** là tập cạnh mà không có hai cạnh nào dùng chung đỉnh trái hoặc chung đỉnh phải.

Một **full matching phía trái** là matching có đúng n cạnh: **mọi đỉnh trái được ghép**, mỗi đỉnh phải dùng tối đa một lần.

Ta cần chọn n cặp sao cho:

**min Σ cᵢⱼ trên các cặp (i,j) được chọn.**

Dùng biến nhị phân xᵢⱼ:

~~~text
Minimize   sum_i sum_j  c[i][j] * x[i][j]

subject to:
    sum_j x[i][j] = 1        cho moi hang i
    sum_i x[i][j] <= 1       cho moi cot j
    x[i][j] in {0,1}
    x[i][j] = 0 neu cap (i,j) bi cam
~~~

Nếu n=m và mọi hàng được ghép, số cạnh bằng m nên mỗi cột cũng sẽ được dùng đúng một lần.

### Các từ dễ nhầm

- **Maximum cardinality matching:** nhiều cặp nhất, chưa xét chi phí.
- **Minimum-cost full assignment:** mọi hàng phải có cặp, tổng chi phí nhỏ nhất.
- **Maximum-weight assignment:** mọi hàng có cặp, tổng lợi ích lớn nhất.
- **Minimum-cost maximum matching:** nếu không ghép hết được các hàng, ưu tiên số cặp tối đa rồi trong số đó tối thiểu hóa chi phí; đây **không tự động** là hợp đồng trả kết quả của code Hungarian trong bài.

Chương trình tại đây trả **IMPOSSIBLE** khi không có cách ghép **toàn bộ các hàng**, thay vì âm thầm trả một matching nhỏ hơn.

## 2. Ví dụ ma trận 3×3 cổ điển

Xét ma trận chi phí:

| Nhân viên | Việc 1 | Việc 2 | Việc 3 |
| --- | ---: | ---: | ---: |
| A | 4 | 1 | 3 |
| B | 2 | 0 | 5 |
| C | 3 | 2 | 2 |

Ta chọn mỗi hàng đúng một cột, các cột không trùng nhau. Một phương án:

- A → việc 2: chi phí **1**.
- B → việc 1: chi phí **2**.
- C → việc 3: chi phí **2**.

Tổng **1+2+2=5**.

Một phương án khác là A→1, B→2, C→3, tổng **4+0+2=6**, kém hơn.

Kết quả Hungarian cho ví dụ này là:

~~~text
Square min: cost=5, jobs=[2, 1, 3]
~~~

Ở đây **jobs[i]** là số thứ tự công việc **1-based** giao cho nhân viên thứ i+1. Mảng **[2,1,3]** không phải thứ tự thực hiện công việc theo thời gian; nó là **ánh xạ phân công** theo từng hàng.

### Tại sao không chỉ chọn minimum từng hàng?

Nhân viên A rẻ nhất ở việc 2; B cũng rẻ nhất ở việc 2. Không thể gán cả hai vào cùng một việc. Thuật toán phải giải quyết sự cạnh tranh trên cột, có thể **đổi lại quyết định trước đó** để giảm tổng chi phí.

## 3. Greedy theo hàng có thể sai rất nặng

Ma trận:

~~~text
          Job 1   Job 2
Worker 1     1       2
Worker 2     1     100
~~~

Nếu xét từng hàng và chọn việc rẻ nhất đang còn trống:

1. Worker 1 chọn Job 1 chi phí 1.
2. Worker 2 chỉ còn Job 2 chi phí 100.

Tổng **101**.

Phương án tối ưu:

1. Worker 1 chọn Job 2 chi phí 2.
2. Worker 2 chọn Job 1 chi phí 1.

Tổng **3**.

Đây là khác biệt bản chất của phân công toàn cục: một lựa chọn tốt cho hàng hiện tại có thể lấy mất lựa chọn **đặc biệt quan trọng** của hàng sau.

**Không có chứng minh greedy tổng quát** cho việc “mỗi hàng lấy ô rẻ nhất chưa dùng”. Hungarian khắc phục bằng cách mở rộng và tái bố trí matching qua các đường tăng.

## 4. Góc nhìn toán học: matching tối ưu và đối ngẫu

Với bài minimization, ta xét hai nhóm **thế năng**:

- uᵢ gắn với hàng i.
- vⱼ gắn với cột j.

Một nghiệm đối ngẫu khả thi cho bài n≤m thỏa:

**uᵢ + vⱼ ≤ cᵢⱼ** trên mọi cặp **được phép**,

và có thể lấy **vⱼ≤0** cho các cột chỉ bị ràng buộc “dùng tối đa một lần”. uᵢ là biến tự do về dấu.

Khi các ràng buộc đối ngẫu thỏa, biểu thức:

**Σuᵢ + Σvⱼ**

là một **cận dưới** cho chi phí của bất kỳ full assignment nào.

### Chứng minh cận dưới

Với một assignment hợp lệ, ta có cᵢ,assigned(i) ≥ uᵢ+v_assigned(i). Cộng theo i:

**total ≥ Σuᵢ + Σ(vⱼ của các cột được dùng).**

Các cột không dùng có vⱼ≤0, nên tổng v của cột được dùng **ít nhất bằng** tổng v trên mọi cột. Suy ra:

**total ≥ Σuᵢ + Σvⱼ**.

Nếu tìm được assignment cùng một nghiệm thế năng có giá trị bằng cận dưới này, assignment ấy **tối ưu**.

### Reduced cost và cạnh chặt

Đặt **reducedCost(i,j)=cᵢⱼ−uᵢ−vⱼ**.

Một cặp có reducedCost = 0 gọi là **cạnh chặt (tight edge)**. Hungarian điều chỉnh thế năng để xuất hiện thêm cạnh chặt, rồi tăng số hàng được ghép bằng đường tăng.

Với chi phí có thể âm, việc khởi tạo mọi thế năng bằng 0 **chưa chắc đã là nghiệm đối ngẫu khả thi toàn cục**. Phiên bản Hungarian theo đường tăng ngắn nhất được trình bày ở đây tự điều chỉnh thế năng trong quá trình đưa lần lượt các hàng vào matching; không nên tuyên bố mọi ràng buộc đối ngẫu đã thỏa ngay từ thời điểm khởi tạo.

## 5. Đường tăng (augmenting path) thay đổi ghép cặp như thế nào?

Giả sử đã ghép một số hàng vào các cột. Với hàng mới i:

- Nếu có cột trống mà ta có thể nối trực tiếp qua một cạnh phù hợp, ghép i vào cột đó.
- Nếu cột mong muốn đã có hàng khác, ta có thể **đổi hàng đang ghép** sang một cột khác, nhường cột cũ cho i.
- Chuỗi đổi qua lại giữa **cạnh chưa thuộc matching** và **cạnh thuộc matching** gọi là một **đường tăng**.

Ví dụ 2×2 ở trên:

~~~text
Truoc:
Worker 1 -> Job 1 (cost 1)
Worker 2 chua co viec

Duong tang:
Worker 2 -> Job 1 -> Worker 1 -> Job 2

Sau khi lat cac canh tren duong tang:
Worker 2 -> Job 1 (cost 1)
Worker 1 -> Job 2 (cost 2)
Tong = 3
~~~

Số cặp tăng từ 1 lên 2, dù phải thay đổi lựa chọn đã ghép của Worker 1.

Trong Hungarian có trọng số, ta không chọn đường tăng một cách tùy tiện: **thế năng và giá trị slack** hướng dẫn tìm đường tăng có chi phí điều chỉnh tối ưu.

## 6. Hai cách mô tả Hungarian phổ biến

Có hai phong cách giải thích hay gặp:

1. **Giảm hàng/cột và phủ số 0:** trên ma trận vuông, trừ minimum của từng hàng/cột, chọn các số 0 sao cho không trùng cột; nếu chưa đủ, điều chỉnh ma trận qua các đường phủ.
2. **Thế năng + đường tăng:** duy trì matching từng bước, dùng reduced cost và slack để tìm cột tự do, sau đó thay đổi matching.

Hai cách phản ánh cùng nguyên lý tối ưu đối ngẫu và xây dựng matching trên những cạnh chặt.

Bài này dùng **cách thế năng**, thuận tiện hơn để viết chương trình rõ ràng cho:

- Ma trận n×m với **n≤m**.
- Chi phí âm.
- Cặp bị cấm.
- Minimize hoặc maximize nhờ biến đổi dấu.
- Số nguyên lớn không sợ overflow.

### Khi nào cách giảm hàng/cột dễ hiểu hơn?

Nếu chỉ minh họa **ma trận vuông nhỏ không có cặp cấm**, việc lấy minimum từng hàng, từng cột và khoanh các số 0 là một hình ảnh trực quan tốt. Tuy nhiên, khi cài đặt với cặp không tồn tại hoặc số học rất lớn, phải cẩn thận với sentinel INF và phép cộng/trừ. Cách potentials có thể bỏ qua **các cặp cấm** trực tiếp.

## 7. Mảng p, way, minv và used

Phiên bản Hungarian sử dụng các chỉ số **1-based** nội bộ và thêm **cột giả 0** để thống nhất thao tác tìm đường tăng.

Ký hiệu:

| Dữ liệu | Ý nghĩa |
| --- | --- |
| **u[i]** | Thế năng hàng i |
| **v[j]** | Thế năng cột j |
| **p[j]** | Hàng hiện đang được ghép vào cột j, hoặc 0 nếu cột j trống |
| **p[0]** | Hàng mới đang muốn đưa vào matching |
| **way[j]** | Cột trước đó trong đường tăng để truy vết |
| **minv[j]** | Slack tốt nhất đã biết để tiếp cận cột j từ tập hàng đang xét |
| **used[j]** | Cột j đã được đưa vào cây tìm đường tăng chưa |
| **j0** | Cột hiện tại của quá trình mở rộng |
| **j1** | Cột mới có slack tối thiểu sẽ được chọn tiếp |

Mỗi lần thêm một hàng i:

1. Đặt **p[0]=i**.
2. Khởi tạo lại minv và used cho lượt thêm hàng này.
3. Bắt đầu ở **j0=0**.
4. Tại mỗi bước, hàng **i0=p[j0]** là hàng cần mở rộng các lựa chọn cột.
5. Với mỗi cột j chưa used và cặp i0–j hợp lệ, tính:

   **cur = c[i0][j]−u[i0]−v[j]**.

6. Nếu cur tốt hơn slack hiện tại, cập nhật **minv[j]** và **way[j]=j0**.
7. Chọn cột j1 có minv nhỏ nhất, đặt **delta=minv[j1]**, cập nhật thế năng để giảm các slack.
8. Nếu p[j1]≠0, cột ấy đã bị chiếm; tiếp tục mở rộng từ hàng đang ghép.
9. Nếu p[j1]=0, đã tới **cột trống**; lần theo way để **lật đường tăng**, đưa hàng i vào matching.

Sau n lượt, nếu mỗi lượt đều tìm được cột trống, ta có một full assignment có n cặp.

### Vì sao p[0] quan trọng?

Cột 0 là **điểm bắt đầu giả** của đường tăng; nó không phải một công việc thật và **không bao giờ xuất hiện trong kết quả**. p[0] được gán hàng mới cần ghép, còn v[0] được dùng trong công thức cập nhật thế năng của thuật toán.

## 8. Cập nhật slack và thế năng chính xác

Trong một lần tìm đường tăng, ta chọn:

**delta = min(minv[j])** trên các cột chưa used có slack đã biết.

Sau đó:

- Với mọi cột j đã used: **u[p[j]] += delta**, **v[j] -= delta**.
- Với mọi cột j chưa used nhưng có minv: **minv[j] -= delta**.

Điều chỉnh này biến ít nhất một slack nhỏ nhất thành 0, giúp đưa thêm một cột vào vùng có thể mở rộng mà không bỏ qua phương án tối ưu của matching hiện tại.

**Dấu của delta có thể âm trong giai đoạn đầu** khi dữ liệu gốc có chi phí âm. Đó không phải dấu hiệu lỗi: reduced costs và thế năng được điều chỉnh bởi phép toán chính xác.

Nếu dùng long, phép cộng/trừ thế năng phải không tràn. Mã Java dùng **BigInteger**, còn ô bị cấm dùng **null**, không dùng một số cực lớn làm chi phí thay thế.

### Lật đường tăng bằng way[]

Khi j0 chỉ tới một cột tự do, thực hiện:

~~~text
repeat:
    j1 = way[j0]
    p[j0] = p[j1]
    j0 = j1
until j0 == 0
~~~

Công thức này đi ngược theo các cột trước đó, chuyển hàng đang ghép ở cột j1 sang cột j0, cuối cùng đưa hàng mới p[0] vào cột thích hợp.

Sau đó matching tăng số cặp đúng **1**. Mỗi hàng chỉ được ghép với một cột và mỗi cột giữ nhiều nhất một hàng.

## 9. Quy trình đầy đủ: Hungarian cho n≤m

Pseudocode, với cặp bị cấm được bỏ qua:

~~~text
HungarianMin(cost[n][m]):
    require n <= m
    u[0..n] = 0
    v[0..m] = 0
    p[0..m] = 0
    way[0..m] = 0

    for i = 1 .. n:
        p[0] = i
        minv[1..m] = UNSET
        used[0..m] = false
        j0 = 0

        do:
            used[j0] = true
            i0 = p[j0]
            delta = UNSET
            j1 = NONE

            for j = 1 .. m:
                if used[j]:
                    continue
                if cost[i0][j] duoc phep:
                    cur = cost[i0][j] - u[i0] - v[j]
                    if minv[j] UNSET or cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0

                if minv[j] SET and
                   (delta UNSET or minv[j] < delta):
                    delta = minv[j]
                    j1 = j

            if j1 == NONE:
                return IMPOSSIBLE

            for j = 0 .. m:
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else if minv[j] SET:
                    minv[j] -= delta

            j0 = j1
        while p[j0] != 0

        repeat:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
        until j0 == 0

    return assignment described by p[1..m]
~~~

Mã giả dùng chỉ số hàng/cột 1-based. Trong Java, ma trận input là 0-based, vì thế phép đọc từ p[j] cần trừ 1 khi truy cập hàng.

## 10. Chi phí O(n²m): không phải duyệt n! phương án

Với n hàng và m cột, n≤m:

- Có **n lần tăng matching**, mỗi lần thêm một hàng.
- Ở lần thêm hàng thứ i, có nhiều nhất **i−1 cột đang bị chiếm**, nên hành trình tìm cột trống xét tối đa **O(i)** bước mở rộng.
- Mỗi bước quét tối đa **m cột** để cập nhật slack và tìm delta.
- Tổng qua các hàng: **O(m Σᵢ₌₁ⁿ i) = O(n²m)**.

Nếu n=m=k, ta có **O(k³)**.

Bộ nhớ phụ của thuật toán:

- u: O(n).
- v, p, way, minv, used: O(m).
- Kết quả phân công: O(n).

Tức **O(n+m) bộ nhớ phụ**, **ngoài ma trận chi phí O(nm)**.

Vì code dùng BigInteger, cần phân biệt:

- **O(n²m)** là số thao tác cộng/trừ/so sánh ở mô hình phép toán số học cơ bản.
- Thời gian thực của BigInteger phụ thuộc độ dài bit.
- Lưu thêm ma trận BigInteger chuyển đổi từ Long[][] cũng tốn O(nm) tham chiếu và đối tượng; nhiều bộ dữ liệu lớn có thể cần phiên bản dùng primitive long với cận overflow được chứng minh.

### So với vét cạn

Nếu mọi cặp đều hợp lệ, số assignment khi n≤m là:

**m·(m−1)·...·(m−n+1) = m!/(m−n)!**.

Duyệt tất cả assignment là thuật toán mũ/giai thừa, chỉ thích hợp làm **oracle trên dữ liệu rất nhỏ**. Hungarian giảm thời gian xuống đa thức.

## 11. Ma trận chữ nhật: nhân viên ít hơn công việc

Ví dụ n=3, m=4:

| Worker | Job 1 | Job 2 | Job 3 | Job 4 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 7 | 3 | 6 | 9 |
| 2 | 9 | 8 | 4 | 5 |
| 3 | 6 | 5 | 3 | 7 |

Một assignment tối ưu:

- Worker 1 → Job 2, cost 3.
- Worker 2 → Job 4, cost 5.
- Worker 3 → Job 3, cost 3.

Tổng **11**; Job 1 không dùng.

~~~text
Rectangular min: cost=11, jobs=[2, 4, 3]
~~~

Không cần bắt buộc sử dụng **mọi cột**. Điều kiện “mỗi cột tối đa một hàng” cho phép thừa việc.

### Nếu n>m?

Không thể ghép **mọi hàng với các cột phân biệt** nếu số hàng vượt số cột. Code trong bài **từ chối n>m** để không đưa ra câu trả lời mang ý nghĩa sai.

Các hướng sửa bài toán:

- Nếu muốn **mọi công việc** được giao và thừa nhân viên, **chuyển vị ma trận**: xem công việc là phía nhỏ cần ghép hết, sau đó ánh xạ kết quả ngược lại.
- Nếu cho phép nhân viên không được giao việc, thêm **cột giả (dummy jobs)** với chi phí/penalty được định nghĩa rõ. Mỗi cột giả cũng chỉ nhận một hàng. Số cột phải đủ ghép mọi hàng.
- Nếu cần **maximum cardinality matching** trên graph thưa, chọn thuật toán phù hợp như **Hopcroft–Karp** trước khi tối ưu trọng số.
- Nếu có yêu cầu vừa tối đa số cặp vừa tối thiểu chi phí, phải mô hình hóa mục tiêu **từ điển** (lexicographic) chính xác; min-cost max-flow là một lựa chọn khác.

**Không được tự ý thêm dummy cost 0** nếu việc bỏ một nhân viên thực sự phải chịu phạt hoặc bị cấm.

## 12. Các ô bị cấm: vì sao không nên dùng INF ngẫu nhiên?

Trong một bài phân công thực tế, có thể có những cặp nhân viên–việc **không hợp lệ**. Ví dụ không đủ chứng chỉ, máy không hỗ trợ tác vụ hoặc lịch bị xung đột.

Ta cần phân biệt:

- Ô có chi phí hợp lệ, dù rất lớn.
- Ô **không có cạnh** trong graph hai phía.

Mã dùng **Long[][]**, với:

- Giá trị Long hợp lệ: một cặp có thể ghép.
- Giá trị **null**: cặp bị cấm.

Khi tính Hungarian, ta **bỏ qua cặp null**, không gán cho nó chi phí 10⁹ hay Long.MAX_VALUE.

### Vì sao không dùng một INF hữu hạn?

Nếu chi phí hợp lệ rất lớn, một INF tự chọn có thể **rẻ hơn một cạnh hợp lệ**, khiến thuật toán chọn cặp bị cấm. Nếu tính reduced cost bằng cách trừ thế năng trên INF=Long.MAX_VALUE, phép toán có thể **tràn số**.

Với null, không có cạnh để relax, nên không có nguy cơ đó.

### Full matching có thể không tồn tại dù m≥n

Ví dụ:

~~~text
Worker 1: Job 1 duoc phep, Job 2 bi cam
Worker 2: Job 1 duoc phep, Job 2 bi cam
~~~

Hai nhân viên chỉ có **cùng một** công việc hợp lệ. Số công việc m=2 vẫn đủ về mặt đếm, nhưng không có cách ghép cả hai hàng. Kết quả phải là **IMPOSSIBLE**.

**Điều kiện Hall:** Trong graph hai phía, tồn tại matching phủ toàn bộ n đỉnh trái khi và chỉ khi **với mọi tập con S của phía trái, tập hàng xóm N(S) có ít nhất |S| đỉnh phải**.

Ở ví dụ trên, S={Worker 1, Worker 2} chỉ có N(S)={Job 1}, nên |N(S)|=1<2. Không có full assignment.

### Dấu hiệu vô nghiệm trong mã Hungarian

Nếu trong một lượt tìm đường tăng **không còn bất cứ cột chưa used nào có slack hữu hạn**, j1 vẫn bằng −1. Không thể mở rộng cây tìm đường tăng để tới cột tự do; code trả **IMPOSSIBLE**.

Đó là một kết luận về **khả năng ghép đủ các hàng**, không phải “chi phí tối ưu bằng vô cực” để cộng số tùy ý.

## 13. Tối đa hóa tổng lợi ích bằng đổi dấu

Nếu **benefit[i][j]** là lợi ích và cần **maximize tổng lợi ích**, chuyển thành min-cost:

**transformedCost[i][j] = −benefit[i][j]**.

Đối với mọi matching có cùng số cặp n:

**min Σ(−benefit) ⇔ max Σ benefit**.

Các ô bị cấm vẫn bị cấm, không tự động chuyển thành số.

### Vì sao không lấy bù theo một số M?

Một cách khác là **M−benefit**, nhưng phải chọn M và kiểm tra tràn số. Đổi dấu trực tiếp đơn giản hơn khi dùng **BigInteger**.

Nếu benefit là Long.MIN_VALUE, phép **−Long.MIN_VALUE trong long** bị tràn, vì trị dương tương ứng vượt Long.MAX_VALUE. Code chuyển sang BigInteger rồi mới gọi **negate()**, tránh lỗi.

Sau khi Hungarian chọn matching tốt nhất trên chi phí đã đổi dấu, chương trình **cộng lại các giá trị gốc** để in tổng benefit thật, không in tổng âm.

### Ví dụ maximize

Ma trận 3×3 cổ điển:

~~~text
Benefit:
4 1 3
2 0 5
3 2 2
~~~

Tối đa hóa cho một assignment:

- Hàng 1 → cột 1: 4.
- Hàng 2 → cột 3: 5.
- Hàng 3 → cột 2: 2.

Tổng **11**.

~~~text
Square max: cost=11, jobs=[1, 3, 2]
~~~

Trong output, từ **cost** là nhãn tổng đại lượng đầu vào chung cho cả MIN và MAX; ở chế độ MAX nó chính là **tổng benefit cần tối đa hóa**.

## 14. Chương trình Java 17+ hoàn chỉnh

Chương trình dưới đây:

- Nhận **Long[][] cost** với n hàng, m cột, **n≤m**.
- Mỗi ô null nghĩa là cặp bị cấm.
- Hỗ trợ **Objective.MIN** và **Objective.MAX**.
- Dùng **BigInteger** để cộng/trừ, lưu potentials và slack mà không tràn.
- Trả **Result(feasible, total, jobByWorker)**.
- Với assignment hợp lệ, **jobByWorker[i]** là cột công việc **1-based** của hàng i+1.
- Khi không tồn tại full matching, trả **IMPOSSIBLE**, không đưa ra partial assignment.
- Với **0 hàng**, trả assignment rỗng và tổng 0; nếu có hàng thì số cột phải **≥ số hàng**.
- Giữ tie-break xác định bằng thứ tự quét cột tăng dần và chỉ cập nhật khi **nhỏ hơn thật sự**.

**Tên tệp chính xác:** HungarianAssignmentDemo.java

~~~java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;

public class HungarianAssignmentDemo {

    enum Objective {
        MIN, MAX
    }

    record Result(boolean feasible, BigInteger total,
                  int[] jobByWorker) {

        String describe() {
            if (!feasible) {
                return "IMPOSSIBLE";
            }
            return "cost=" + total
                    + ", jobs=" + Arrays.toString(jobByWorker);
        }
    }

    static Result solve(Long[][] input, Objective objective) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(objective, "objective");

        int n = input.length;

        // No workers: the empty assignment is feasible.
        if (n == 0) {
            return new Result(true, BigInteger.ZERO, new int[0]);
        }

        Objects.requireNonNull(input[0], "row 1");
        int m = input[0].length;

        if (m < n) {
            throw new IllegalArgumentException(
                    "Need at least n distinct jobs (n <= m)");
        }

        // Convert to exact integer costs; null means forbidden.
        BigInteger[][] cost = new BigInteger[n][m];
        for (int i = 0; i < n; i++) {
            Objects.requireNonNull(input[i], "row " + (i + 1));

            if (input[i].length != m) {
                throw new IllegalArgumentException(
                        "Cost matrix must be rectangular");
            }

            for (int j = 0; j < m; j++) {
                Long value = input[i][j];
                if (value != null) {
                    BigInteger x = BigInteger.valueOf(value);
                    cost[i][j] = objective == Objective.MAX
                            ? x.negate() : x;
                }
            }
        }

        // Hungarian algorithm: 1-based rows/columns plus column 0.
        BigInteger[] u = new BigInteger[n + 1];
        BigInteger[] v = new BigInteger[m + 1];
        Arrays.fill(u, BigInteger.ZERO);
        Arrays.fill(v, BigInteger.ZERO);

        int[] p = new int[m + 1];
        int[] way = new int[m + 1];

        for (int i = 1; i <= n; i++) {
            p[0] = i;

            // null slack means no allowed route to this column yet.
            BigInteger[] minv = new BigInteger[m + 1];
            boolean[] used = new boolean[m + 1];
            int j0 = 0;

            do {
                used[j0] = true;
                int i0 = p[j0];

                BigInteger delta = null;
                int j1 = -1;

                for (int j = 1; j <= m; j++) {
                    if (used[j]) {
                        continue;
                    }

                    BigInteger cij = cost[i0 - 1][j - 1];

                    if (cij != null) {
                        BigInteger reduced = cij
                                .subtract(u[i0])
                                .subtract(v[j]);

                        if (minv[j] == null
                                || reduced.compareTo(minv[j]) < 0) {
                            minv[j] = reduced;
                            way[j] = j0;
                        }
                    }

                    if (minv[j] != null
                            && (delta == null
                            || minv[j].compareTo(delta) < 0)) {
                        delta = minv[j];
                        j1 = j;
                    }
                }

                // Hall condition fails: no full row assignment.
                if (j1 == -1) {
                    return new Result(false, null, new int[0]);
                }

                for (int j = 0; j <= m; j++) {
                    if (used[j]) {
                        u[p[j]] = u[p[j]].add(delta);
                        v[j] = v[j].subtract(delta);
                    } else if (j > 0 && minv[j] != null) {
                        minv[j] = minv[j].subtract(delta);
                    }
                }

                j0 = j1;
            } while (p[j0] != 0);

            // Augment along the recorded alternating path.
            do {
                int j1 = way[j0];
                p[j0] = p[j1];
                j0 = j1;
            } while (j0 != 0);
        }

        int[] jobByWorker = new int[n];
        BigInteger originalTotal = BigInteger.ZERO;

        for (int j = 1; j <= m; j++) {
            if (p[j] != 0) {
                int row = p[j] - 1;
                jobByWorker[row] = j;  // 1-based job number
                originalTotal = originalTotal.add(
                        BigInteger.valueOf(input[row][j - 1]));
            }
        }

        return new Result(true, originalTotal, jobByWorker);
    }

    static void show(String label, Objective objective,
                     Long[][] cost) {
        Result result = solve(cost, objective);
        System.out.println(label + ": " + result.describe());
    }

    public static void main(String[] args) {

        Long[][] square = {
            {4L, 1L, 3L},
            {2L, 0L, 5L},
            {3L, 2L, 2L}
        };
        Long[][] rectangular = {
            {7L, 3L, 6L, 9L},
            {9L, 8L, 4L, 5L},
            {6L, 5L, 3L, 7L}
        };

        show("Square min", Objective.MIN, square);
        show("Rectangular min", Objective.MIN, rectangular);

        show("Negative min", Objective.MIN, new Long[][] {
            {-5L, 0L, 4L},
            {3L, -1L, 2L},
            {2L, 1L, -3L}
        });

        show("Forbidden feasible", Objective.MIN,
                new Long[][] {
                    {1L, null, 5L},
                    {null, 2L, 3L}
                });

        show("Forbidden impossible", Objective.MIN,
                new Long[][] {
                    {1L, null},
                    {2L, null}
                });

        show("All equal", Objective.MIN, new Long[][] {
            {0L, 0L, 0L},
            {0L, 0L, 0L}
        });

        show("One row", Objective.MIN, new Long[][] {
            {10L, -7L, 4L}
        });

        show("Reassignment chain", Objective.MIN,
                new Long[][] {
                    {1L, 2L},
                    {1L, null}
                });

        show("Square max", Objective.MAX, square);
        show("Rectangular max", Objective.MAX, rectangular);

        show("Extreme min", Objective.MIN, new Long[][] {
            {Long.MIN_VALUE, 5L},
            {7L, Long.MIN_VALUE}
        });

        show("Extreme max", Objective.MAX, new Long[][] {
            {Long.MAX_VALUE, 0L},
            {0L, Long.MAX_VALUE}
        });

        show("Empty", Objective.MIN, new Long[][] {});
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 HungarianAssignmentDemo.java
java HungarianAssignmentDemo
~~~

**Đầu ra chương trình:**

~~~text
Square min: cost=5, jobs=[2, 1, 3]
Rectangular min: cost=11, jobs=[2, 4, 3]
Negative min: cost=-9, jobs=[1, 2, 3]
Forbidden feasible: cost=3, jobs=[1, 2]
Forbidden impossible: IMPOSSIBLE
All equal: cost=0, jobs=[1, 2]
One row: cost=-7, jobs=[2]
Reassignment chain: cost=3, jobs=[2, 1]
Square max: cost=11, jobs=[1, 3, 2]
Rectangular max: cost=23, jobs=[4, 1, 2]
Extreme min: cost=-18446744073709551616, jobs=[1, 2]
Extreme max: cost=18446744073709551614, jobs=[1, 2]
Empty: cost=0, jobs=[]
~~~

### Các điểm triển khai đáng chú ý

**Long[][] thay vì long[][]:** biểu diễn được cặp bị cấm bằng null mà không dùng INF số học. Khi dữ liệu lớn và mọi ô đều hợp lệ, **long[][]** tiết kiệm RAM hơn, nhưng cần một overload hoặc preprocessing phù hợp.

**Đổi dấu trên BigInteger:** chế độ MAX xử lý được cả Long.MIN_VALUE, vì phép negate của BigInteger không tràn.

**minv[j]==null:** nghĩa là chưa có đường/cặp hợp lệ nào giúp tiếp cận cột j trong lượt tăng hiện tại. Khi không còn cột có slack hợp lệ, trả IMPOSSIBLE thay vì dựng matching giả.

**Cột giả 0:** p[0]=i khởi tạo hàng mới. Nó không được phép xuất hiện trong jobByWorker.

**Không dùng phép trừ để so sánh chi phí long:** các phép cộng/trừ thế năng dùng BigInteger. Nếu viết comparator trên long, cũng không nên lấy hiệu hai trọng số vì tràn số.

**Mảng jobByWorker dùng 1-based job IDs:** tiện đối chiếu với các bảng công việc đánh số từ 1. Mảng Java vẫn dùng chỉ số hàng 0-based; vì vậy worker thứ 1 được đọc ở jobByWorker[0].

**Kết quả không duy nhất:** nếu có nhiều assignment tối ưu (ví dụ mọi chi phí đều 0), thứ tự quét cột trong bản cài này chọn một kết quả xác định. Bản cài khác có thể trả matching tối ưu khác, nên QA cần ưu tiên **tổng cost và tính hợp lệ của assignment**, không luôn bắt buộc cùng một dãy jobs.

## 15. Phân tích kỹ ví dụ có cặp bị cấm

Xét:

~~~text
          Job1   Job2   Job3
Worker1     1    X       5
Worker2     X     2      3

X = forbidden
~~~

Có full assignment:

- Worker1→Job1, chi phí 1.
- Worker2→Job2, chi phí 2.

Tổng 3.

Dù một số cạnh thiếu, thuật toán vẫn hoạt động vì còn đường tăng tới cột tự do qua các cặp hợp lệ.

Ngược lại:

~~~text
          Job1   Job2
Worker1     1    X
Worker2     2    X
~~~

Chỉ Job1 có thể dùng, trong khi hai hàng đều bắt buộc nhận việc. Không có full matching.

### Thất bại của cách thay X bằng BIG_M

Giả sử thay X bằng một số lớn nhưng hữu hạn. Hungarian thông thường sẽ vẫn cố gán cả hai hàng; nó có thể “chọn” một ô X vì không có lựa chọn khác, rồi trả một tổng cost lớn.

Nếu chương trình không kiểm tra xem assignment chọn ô bị cấm hay không, kết quả **sai bản chất**. Việc dùng null và kiểm tra đường tăng đảm bảo kết quả IMPOSSIBLE đúng.

### Nếu đề yêu cầu ghép nhiều nhất có thể

Khi không có full matching, muốn tìm **số cặp tối đa**, bài toán mục tiêu đã đổi. Có thể dùng **Hopcroft–Karp** để tìm maximum cardinality matching. Nếu cần tối thiểu hóa chi phí trong tập maximum cardinality matching, cần tối ưu thêm (chẳng hạn min-cost max-flow), không coi kết quả IMPOSSIBLE của solver full-assignment là toàn bộ câu trả lời.

## 16. Từ Hungarian tới bài phân công có ràng buộc khác

Hungarian chuẩn phù hợp khi mỗi hàng cần đúng một cột, mỗi cột nhận tối đa một hàng và tổng chi phí là tổng các ô được chọn.

Nếu đề có các ràng buộc khác, cần xem có thể chuyển về assignment chuẩn hay không.

### Mỗi công việc có nhiều suất

Giả sử Job A nhận tối đa 3 nhân viên. Có thể tạo **ba bản sao cột A** nếu số suất nhỏ và các suất có chi phí tương đương, rồi chạy Hungarian với các cột mới.

Tuy nhiên, cách nhân bản có thể làm ma trận rộng hơn nhiều; nếu capacity lớn, min-cost flow trên mạng hai phía thường phù hợp hơn.

### Nhân viên có thể không được giao việc

Có thể thêm **dummy jobs** đủ nhiều để mỗi hàng vẫn có một cột. Cost giao cho dummy phải thể hiện đúng mô hình:

- 0 nếu bỏ trống miễn phí.
- Một mức penalty cụ thể nếu không giao việc bị phạt.
- Cấm dummy cho một số nhân viên nếu họ bắt buộc có việc thật.

Không tự động sử dụng dummy cost 0 khi người dùng/đề chưa cho phép bỏ việc.

### Phân công có tiền xử lý điều kiện hợp lệ

Dùng null ở những ô không đạt điều kiện, ví dụ kỹ năng, deadline hoặc khả năng tương thích.

Nếu điều kiện phụ thuộc **đồng thời vào nhiều cặp đã chọn** (ví dụ hai nhân viên không được làm cùng một nhóm), nó không còn là assignment độc lập theo ô và Hungarian chuẩn không tự giải ràng buộc tương tác ấy.

### Cần tối ưu đa mục tiêu

Nếu muốn ưu tiên **số cặp trước, chi phí sau**, hoặc cân bằng tải, cần định nghĩa thứ tự ưu tiên rõ. Trộn mọi thứ thành một cost bằng hằng M chỉ an toàn khi đã chứng minh cận để mục tiêu ưu tiên cao không bị mục tiêu thấp đảo ngược.

## 17. Độ phức tạp so với các thuật toán matching khác

| Bài toán | Công cụ thường dùng | Nhận xét |
| --- | --- | --- |
| Hai phía, chỉ tối đa **số cặp** | DFS augmenting / Hopcroft–Karp | Không tối ưu trọng số |
| Hai phía, **chi phí** cho mỗi cặp, cần phủ mọi hàng | Hungarian | O(n²m) với n≤m, O(n³) nếu vuông |
| Ghép đôi có chi phí, cung/cột có capacity tùy ý | Min-cost flow | Mô hình linh hoạt hơn, có thể tốn nhiều thao tác hơn |
| Ghép cặp trên graph **không hai phía** | Blossom và biến thể | Hungarian dạng assignment không áp dụng trực tiếp |
| Cần cân bằng/tối ưu nhiều ràng buộc logic phức tạp | ILP/CP-SAT hoặc mô hình đặc thù | Không còn là assignment chuẩn |
| Duyệt vét cạn mọi gán | DFS/backtracking | Chỉ cho n,m rất nhỏ hoặc có cấu trúc cắt tỉa đặc biệt |

**Đừng nhầm Hungarian với Kuhn DFS matching không trọng số.** Hai thuật toán cùng có thể được nhắc cạnh nhau khi học ghép cặp hai phía, nhưng mục tiêu và xử lý trọng số khác nhau.

**Đừng nhầm Hungarian với thuật toán đường đi ngắn nhất trong graph tổng quát.** Phiên bản potentials sử dụng ý tưởng đường tăng có chi phí, nhưng nó giải cấu trúc assignment hai phía rất cụ thể.

### Vì sao Hungarian thường phù hợp ma trận dày?

Bản cài O(n²m) quét nhiều cột trong mỗi lượt, nên hợp với bài mà dữ liệu đã có ma trận chi phí **n×m**, phần lớn cặp hợp lệ, n,m vừa phải.

Nếu số cạnh hợp lệ rất ít so với n·m, một mô hình ghép cặp có trọng số bằng **min-cost flow trên adjacency list** có thể sử dụng bộ nhớ tốt hơn vì không cần giữ toàn bộ ma trận. Hungarian vẫn chạy đúng với null nhưng chưa chắc hiệu quả bộ nhớ khi m quá lớn.

## 18. Bộ kiểm thử độc lập bằng vét cạn

Để QA Hungarian, không nên chỉ so đầu ra với một bản Hungarian thứ hai vì hai bản có thể cùng mắc lỗi cập nhật thế năng hoặc index.

Với n≤5, m≤7, có thể dùng **DFS liệt kê assignment** làm oracle:

1. Chọn một cột hợp lệ cho hàng đầu tiên.
2. Đánh dấu cột đã dùng.
3. Với hàng tiếp theo, thử mọi cột chưa dùng có cost không phải null.
4. Khi đã ghép hết n hàng, tính tổng.
5. Với MIN lấy tổng nhỏ nhất; với MAX lấy tổng lớn nhất.
6. Nếu không có cách ghép đủ n hàng, oracle trả IMPOSSIBLE.

Thuật toán tham chiếu này **không dùng thế năng, minv hoặc đường tăng** nên độc lập về mặt cơ chế.

### Kiểm tra cả kết quả matching

Với mỗi kết quả Hungarian feasible:

- Có **đúng n số** trong jobByWorker.
- Mỗi job nằm trong 1..m.
- Không có hai worker chọn cùng job.
- Không chọn ô null.
- Tổng cost của các cặp chọn phải **đúng bằng trường total**.
- Trường total phải bằng minimum/maximum do oracle vét cạn tìm ra.

Với kết quả infeasible, oracle phải xác nhận không có full assignment.

### Ca biên quan trọng

| Ca | Điều cần kiểm tra |
| --- | --- |
| n=0 | Assignment rỗng, cost 0 |
| n=1, nhiều cột | Chọn một cột tốt nhất |
| n=m, mọi ô hợp lệ | Perfect matching trọng số tối ưu |
| n<m | Ghép tất cả hàng, để một số cột trống |
| Ô bị cấm bằng null | Không được chọn cặp bị cấm |
| Không tồn tại full matching | IMPOSSIBLE |
| Nhiều chi phí bằng nhau | Có thể có nhiều matching tối ưu |
| Mọi chi phí âm | Không dùng giả định nonnegative |
| Mục tiêu MAX | Đổi dấu đúng, in tổng gốc |
| Long.MIN_VALUE trong chế độ MAX | Không overflow khi negate |
| Tổng cost vượt long | BigInteger in chính xác |
| Một hàng chỉ có một job hợp lệ | Cần bảo toàn lựa chọn bắt buộc |
| Các hàng cạnh tranh một cột | Có thể phải đổi lại matching cũ |
| m<n | Input không đáp ứng hợp đồng solver |

**Kết luận QA:** Một dãy jobs khác với oracle có thể vẫn đúng nếu có nhiều assignment tối ưu. Chỉ coi là sai khi mapping không hợp lệ hoặc tổng cost không đạt optimum.

## 19. Chứng minh ý tưởng Hungarian đúng

Một chứng minh đầy đủ Hungarian thường dựa trên **đối ngẫu tuyến tính** và **complementary slackness**. Có thể nắm phần cốt lõi theo ba bất biến.

### Bất biến 1: matching luôn hợp lệ

Mảng p[j] giữ tối đa một hàng trên mỗi cột. Khi có đường tăng kết thúc ở cột trống, việc lật cạnh dọc đường chỉ **chuyển mỗi hàng sang một cột khác**, không tạo hai hàng ở cùng cột.

Sau khi thêm hàng i, số cặp tăng đúng 1. Sau n lượt thành công, tất cả n hàng được ghép.

### Bất biến 2: slack định hướng việc điều chỉnh thế năng

Khi tìm cách ghép hàng mới, minv[j] ghi **chi phí điều chỉnh nhỏ nhất đang biết** để tiếp cận cột chưa xét từ vùng hàng/cột đang mở rộng.

Chọn delta nhỏ nhất và cập nhật thế năng tạo thêm cơ hội đi theo một cạnh chặt mà không đánh mất tính tối ưu của matching bộ phận. Các phép cập nhật được thiết kế tương ứng với bước ngắn nhất trong graph xen kẽ.

Nếu không có cột khả dụng mới ở cuối quá trình mở rộng, không có đường tăng phủ thêm một hàng: chính là tình huống full matching không tồn tại.

### Bất biến 3: matching cuối đạt cận đối ngẫu

Sau khi ghép xong toàn bộ hàng, các thế năng đã điều chỉnh cung cấp cận dưới đối ngẫu cho bài minimization; những cạnh được chọn là **cạnh chặt** tương ứng (reduced cost bằng 0), với điều kiện slack/potentials được cập nhật đúng.

Theo complementary slackness, tổng chi phí assignment bằng giá trị của chứng chỉ đối ngẫu, nên không assignment hợp lệ nào có chi phí nhỏ hơn.

Đối với mục tiêu MAX, vì code chạy Hungarian MIN trên **−benefit** rồi đổi lại tổng gốc, tính tối ưu MAX theo ngay từ tính tối ưu MIN.

### Điều chứng minh cần giả định

- Cost là giá trị số học hữu hạn cho từng cặp hợp lệ.
- Mỗi hàng phải có đúng một cột, cột không trùng.
- Không có ràng buộc tương tác khác giữa các lựa chọn cặp.
- Phép toán potentials, reduced cost và so sánh **chính xác**.
- Cặp bị cấm thật sự được bỏ qua, không được đưa vào matching.

Nếu thay công thức cập nhật delta hoặc bỏ qua trạng thái used/way, không còn giữ được các bất biến trên.

## 20. Những lỗi triển khai phổ biến

1. **Áp dụng greedy lấy ô nhỏ nhất từng hàng** rồi cho rằng tối ưu tổng thể.
2. **Cho hai hàng dùng chung một cột** khi có cùng mức chi phí rẻ nhất.
3. **Chọn matching nhiều cặp nhất rồi gọi đó là minimum-cost assignment** mà không tối ưu cost.
4. **Coi n≤m là đủ bảo đảm full matching**, dù có cặp cấm khiến vi phạm điều kiện Hall.
5. **Thay ô bị cấm bằng 10⁹**, làm thuật toán chọn ô không hợp lệ nếu mọi lựa chọn khác rất đắt hoặc không có lựa chọn.
6. **Không phát hiện IMPOSSIBLE**, trả một matching giả qua ô bị cấm.
7. **Không xử lý n>m theo hợp đồng đầu vào**, khiến mảng/đường tăng sai.
8. **Thêm dummy cost 0 tùy ý**, vô tình cho phép bỏ hàng mà bài cấm.
9. **Nhầm cột giả 0 với công việc thật** và trả job 0.
10. **Quên p[0]=i** trước khi tăng matching cho hàng mới.
11. **Không reset minv và used cho mỗi hàng**, dùng lại slack cũ.
12. **Cập nhật way[j] nhưng không cập nhật minv[j] đúng nhánh**, khiến đường tăng truy vết sai.
13. **Lấy delta trên cột đã used**, thay vì những cột chưa used có slack.
14. **Dùng số INF như một chi phí hợp lệ**, dẫn đến chọn cạnh cấm.
15. **Cập nhật thế năng u,v sai dấu**, làm reduced costs và tổng tối ưu sai.
16. **Quên trừ delta khỏi minv của cột chưa used**, khiến giá trị slack lỗi thời.
17. **Lật đường tăng từ trái sang phải sai thứ tự**, tạo hai hàng một cột hoặc bỏ hàng cũ.
18. **Chỉ thay p[j0] một lần, không đi theo way[] tới cột 0**, khiến matching không tăng đúng.
19. **Dùng index 0-based lẫn 1-based** khi truy cập input hoặc p/way.
20. **Dùng −Long.MIN_VALUE trong long**, overflow ở biến thể maximize.
21. **Cộng nhiều giá trị long vượt miền**, in tổng sai dù các cạnh riêng hợp lệ.
22. **So sánh bằng phép trừ hai long**, có thể tràn và đảo thứ tự.
23. **In tổng đã đổi dấu trong MAX** thay vì tổng benefit gốc.
24. **So chính xác danh sách jobs với oracle** trong trường hợp có nhiều matching tối ưu, kết luận sai là WA.
25. **Dùng Hungarian khi đề chỉ hỏi maximum cardinality trên graph thưa**, không tận dụng matching không trọng số.
26. **Không phân biệt chi phí giao một cặp với các ràng buộc tương tác**, dùng assignment chuẩn cho bài khác.
27. **Cho rằng Hungarian dùng được cho graph không hai phía tổng quát**, trong khi matching general graph có lý thuyết khác.
28. **Coi null là cost 0**, dẫn đến cho phép các cặp bị cấm.
29. **Không xác minh rectangular rows cùng độ dài**, truy cập ra ngoài ma trận.
30. **Đánh giá độ phức tạp như n!** cho Hungarian, nhầm với vét cạn.
31. **Tuyên bố mọi potentials ban đầu đều đối ngẫu khả thi khi cost âm**, không đúng với khởi tạo zero đơn giản.
32. **Không tính bộ nhớ của ma trận BigInteger chuyển đổi**, đánh giá thiếu chi phí object trên Java.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Hungarian giải bài toán gì?  
**Đáp án:** Ghép mọi hàng với một cột khác nhau sao cho tổng cost nhỏ nhất (hoặc tổng benefit lớn nhất sau biến đổi), trong mô hình assignment hai phía.

**Câu 2.** Tại sao greedy chọn ô rẻ nhất từng hàng có thể sai?  
**Đáp án:** Một hàng có thể chiếm cột mà hàng khác rất cần, khiến tổng cost tăng mạnh; cần xét khả năng đổi cặp bằng đường tăng.

**Câu 3.** Cách viết điều kiện của full row assignment?  
**Đáp án:** Mỗi hàng có đúng một cột; mỗi cột có tối đa một hàng; chỉ chọn cặp hợp lệ.

**Câu 4.** Nếu n<m, có bắt buộc dùng hết m cột không?  
**Đáp án:** Không. Ghép đủ n hàng, các cột còn lại không dùng.

**Câu 5.** Nếu n>m, chương trình này xử lý ra sao?  
**Đáp án:** Từ chối input; không thể ghép tất cả n hàng vào m cột phân biệt.

**Câu 6.** Nếu hai hàng đều chỉ có thể ghép cột 1, có full matching không?  
**Đáp án:** Không, vi phạm điều kiện Hall.

**Câu 7.** Tại sao ô bị cấm nên dùng null thay cho INF?  
**Đáp án:** Không có nguy cơ chọn ô cấm và không tràn khi cập nhật thế năng.

**Câu 8.** Mảng p[j] có ý nghĩa gì?  
**Đáp án:** Hàng đang được ghép vào cột j, hoặc 0 nếu cột trống.

**Câu 9.** Mảng way[j] dùng để làm gì?  
**Đáp án:** Truy vết các cột của đường tăng để lật matching.

**Câu 10.** Delta được chọn như thế nào?  
**Đáp án:** Min của các slack minv[j] đã biết trên cột chưa used.

**Câu 11.** Độ phức tạp Hungarian hình vuông n×n?  
**Đáp án:** O(n³) thao tác số học theo phiên bản potentials ở đây.

**Câu 12.** Độ phức tạp ma trận n×m với n≤m?  
**Đáp án:** O(n²m), bộ nhớ phụ O(n+m) ngoài ma trận cost O(nm).

**Câu 13.** Chuyển bài maximize sang minimize thế nào?  
**Đáp án:** Dùng transformedCost=−benefit; sau đó in tổng benefit gốc.

**Câu 14.** Vì sao BigInteger cần thiết trong demo cực trị?  
**Đáp án:** Phép negate Long.MIN_VALUE và tổng của nhiều số long có thể vượt miền long.

**Câu 15.** Hungarian tự trả minimum-cost maximum matching khi có forbidden khiến full matching bất khả thi không?  
**Đáp án:** Không. Code trả IMPOSSIBLE; bài minimum-cost maximum matching cần mô hình mục tiêu khác.

**Câu 16.** Nếu hai matching có cùng tổng tối ưu, thuật toán nào đúng?  
**Đáp án:** Cả hai nếu đều có n cặp hợp lệ, không dùng lại cột và cùng giá trị tối ưu.

**Câu 17.** Khi nào min-cost flow có thể phù hợp hơn Hungarian?  
**Đáp án:** Khi có capacity nhiều suất, cần tối ưu số cặp khi không thể phủ hết hàng, hoặc graph cạnh hợp lệ rất thưa và muốn biểu diễn bằng adjacency list.

**Câu 18.** Có thể dùng Hungarian khi các cặp tương tác theo quy tắc “hai nhân viên này không cùng nhóm” không?  
**Đáp án:** Không trực tiếp, vì đó là ràng buộc phụ giữa các lựa chọn cặp, ngoài assignment chuẩn.

## 22. Tổng kết và checklist áp dụng

**Thuật toán Hungarian** là lựa chọn mạnh khi cần **phân công có trọng số** trên graph hai phía, mỗi hàng đúng một cột và không cột nào bị dùng hai lần.

Trước khi cài:

1. Xác định mục tiêu **MIN hay MAX**, không nhầm tổng trọng số với số lượng cặp.
2. Xác định có cần ghép **mọi hàng** không; code này yêu cầu **n≤m** và phủ toàn bộ n hàng.
3. Đọc rõ các **cặp bị cấm**, biểu diễn bằng null hoặc cấu trúc cạnh thực, không gán INF bừa.
4. Hiểu **p[j]**, **way[j]**, **minv[j]**, **used[j]**, u,v và cột giả 0.
5. Mỗi hàng mới: tìm đường tăng theo reduced costs, chỉnh thế năng bằng delta, rồi lật đường tăng.
6. Nếu không tìm được cột tự do qua cạnh hợp lệ, trả **IMPOSSIBLE**; không tạo assignment giả.
7. Với **MAX**, đổi dấu trên số học an toàn rồi trả **tổng giá trị gốc**.
8. Kiểm tra tổng cost bằng đúng những ô được chọn, không trùng cột.
9. Tính đến O(n²m) thời gian và O(nm) bộ nhớ ma trận; nếu input cực thưa hoặc có capacity khác thường, cân nhắc mô hình flow.
10. QA bằng **vét cạn trên ma trận nhỏ**, so cả trạng thái khả thi, mapping và giá trị optimum.

**Ý tưởng cần ghi nhớ:** Hungarian không “tham lam chọn ô rẻ nhất”. Nó **điều chỉnh thế năng để tìm các đường tăng hợp lệ**, cho phép **đổi lại các cặp ghép cũ**, nhờ đó đạt **tổng chi phí tối ưu toàn cục**.

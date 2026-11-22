# Ghép cặp cực đại theo bao hàm và ghép cặp có kích thước lớn nhất

**Ghép cặp (matching)** là tập các cạnh trong một đồ thị mà **không có hai cạnh nào chung đỉnh**. Trong các bài toán **ghép cặp và phân công**, mỗi cạnh được chọn có thể đại diện cho việc giao một người với một công việc, kết nối hai thiết bị thành một cặp, hay ghép một ứng viên với một vị trí. Hai thuật ngữ rất dễ bị dịch chung là “ghép cặp cực đại”, nhưng có ý nghĩa **hoàn toàn khác nhau**:

- **Ghép cặp cực đại theo bao hàm (maximal matching)**: không thể **thêm riêng một cạnh nào** vào tập hiện tại mà vẫn giữ tính chất matching. Đây là điều kiện **không mở rộng thêm được bằng cách bổ sung**, chưa bảo đảm số cặp lớn nhất.
- **Ghép cặp có kích thước lớn nhất (maximum-cardinality matching / maximum matching)**: có **số cạnh nhiều nhất trong mọi matching** của đồ thị. Đây là điều kiện **tối ưu toàn cục**.

**Mọi maximum matching đều maximal, nhưng một maximal matching chưa chắc maximum.** Điểm khác nhau nằm ở việc **được phép thay đổi các cặp cũ để tạo nhiều cặp mới hơn**: maximal chỉ xét thêm cạnh, còn maximum yêu cầu xét cả các phép **đổi cặp theo đường tăng (augmenting path)**.

Bài học thuộc nhóm **Ghép cặp và phân công** của Computer Science Algorithms. Ta sẽ xây dựng định nghĩa chính xác cho đồ thị tổng quát và hai phía, đưa ra phản ví dụ tham lam, chứng minh mối quan hệ giữa maximal và maximum, định lý đường tăng của Berge, cận xấp xỉ 1/2, thuật toán **Kuhn DFS** cho matching lớn nhất trên đồ thị hai phía, cách tìm **phủ đỉnh cực tiểu (minimum vertex cover)** theo định lý König, giới hạn của giải pháp này với đồ thị không hai phía, mã **Java 17+** chạy được, kiểm chứng bằng quy hoạch động vét cạn trên đồ thị nhỏ và bài tập có lời giải.

## 1. Các khái niệm nền tảng

Cho đồ thị vô hướng `G=(V,E)`. Một **matching M⊆E** là tập cạnh thỏa:

`∀e_1,e_2∈M, e_1≠e_2 ⇒ endpoints(e_1)∩endpoints(e_2)=∅`.

Nói cách khác, mỗi đỉnh được tham gia **nhiều nhất một cạnh** của M.

- Một đỉnh **đã ghép (matched)** nếu là đầu mút của một cạnh trong M.
- Một đỉnh **chưa ghép / tự do (unmatched/free)** nếu không thuộc cạnh nào của M.
- **Kích thước matching** là `|M|`: số **cạnh/cặp** được chọn, không phải số đỉnh đã ghép.
- Vì mỗi cạnh ghép dùng hai đỉnh khác nhau, mọi matching thỏa `|M|≤floor(|V|/2)`.

Nếu ghép được k cặp, có đúng **2k đỉnh đã ghép**. Nhầm “số người có cặp” là 2k với “số cặp” là k là lỗi rất phổ biến.

### Đồ thị hai phía và bài toán phân công

**Đồ thị hai phía (bipartite graph)** có thể chia V thành hai tập **L và R không giao nhau** sao cho mọi cạnh nối **một đỉnh ở L với một đỉnh ở R**. Ví dụ:

- L: ứng viên, R: công việc.
- Cạnh `L_i–R_j`: ứng viên i **có thể** đảm nhận công việc j.
- Mỗi ứng viên nhận nhiều nhất một việc; mỗi việc được giao cho nhiều nhất một ứng viên.

Một matching kích thước 3 biểu thị **3 lượt phân công hợp lệ**. Mục tiêu maximum matching là **phân công được nhiều nhất**, không nhất thiết tối ưu mức lương, độ ưu tiên hay lợi ích.

Với đồ thị hai phía có `n_L=|L|`, `n_R=|R|`:

`|M|≤min(n_L,n_R)`.

**Ghép cặp hoàn hảo (perfect matching)** là matching **bao phủ tất cả đỉnh** của đồ thị. Với đồ thị hai phía, điều này đòi `n_L=n_R` và `|M|=n_L=n_R`. Nếu chỉ muốn mọi đỉnh phía L có cặp, đó là **matching bão hòa L (left-perfect / L-saturating)**, có thể xảy ra khi `n_L≤n_R` mà không phải perfect toàn đồ thị.

### Phân biệt “maximal”, “maximum”, “perfect”

| Tên | Tiêu chuẩn | Bảo đảm tối ưu số cặp? |
| --- | --- | --- |
| Matching bất kỳ | Không cạnh được chọn nào chung đỉnh | Không |
| **Maximal matching** | Không còn cạnh có **hai đầu đều tự do** để thêm | **Không** |
| **Maximum matching** | Số cặp bằng **giá trị lớn nhất toàn cục** | **Có** |
| **Perfect matching** | **Mọi đỉnh** đều có cặp | Có; đạt giới hạn `|V|/2` |
| Matching bão hòa L | Tất cả đỉnh bên L có cặp | Có; đạt giới hạn `n_L` |

Perfect ⇒ maximum ⇒ maximal. Chiều đảo nói chung **sai**. Maximum có thể không perfect nếu các đỉnh không tương thích hoặc số đỉnh lẻ. Maximal có thể nhỏ hơn maximum rất nhiều theo tỉ lệ, dù không thể thêm một cạnh nào ngay lập tức.

## 2. Ví dụ nhỏ nhất phân biệt maximal và maximum

Xét **đường bốn đỉnh (P4)**:

~~~text
0 -- 1 -- 2 -- 3
~~~

Các cạnh là `(0,1),(1,2),(2,3)`.

Giả sử thuật toán tham lam chọn **cạnh giữa (1,2)** trước:

`M = {(1,2)}`.

Đỉnh 1 và 2 đã có cặp; 0 và 3 còn tự do. Nhưng **không có cạnh (0,3)**. Cả cạnh (0,1) và (2,3) đều đụng một đỉnh đã ghép nên không thể **thêm riêng** vào M.

Vì thế M là **maximal**, kích thước **1**.

Tuy nhiên, matching khác:

`M* = {(0,1),(2,3)}`

có kích thước **2** và không có hai cạnh chung đỉnh. Vì |V|=4 nên không thể có quá 2 cạnh ghép; M* là **maximum**, đồng thời là **perfect**.

**Kết luận:** “không thể thêm cạnh vào M” **không đồng nghĩa** “không thể đạt thêm cặp bằng cách thay đổi M”.

### Đường tăng sửa lời giải như thế nào?

Theo M={(1,2)}, dãy đỉnh:

~~~text
0 -- 1 == 2 -- 3
     M: (1,2)

(0,1) chưa ghép
(1,2) đã ghép
(2,3) chưa ghép
~~~

là một **đường tăng** từ hai đỉnh tự do 0 và 3, có các cạnh **chưa ghép – đã ghép – chưa ghép** xen kẽ. Ta **đảo trạng thái** của ba cạnh:

- Bỏ cạnh đã ghép (1,2).
- Nhận hai cạnh chưa ghép (0,1) và (2,3).

Số cặp tăng từ 1 lên 2. Đây là phép cải thiện mà greedy maximal đơn thuần không thử.

## 3. Định nghĩa maximal theo bao hàm

Matching M **maximal theo bao hàm** nếu không tồn tại matching M' khác với:

`M ⊊ M'`.

Vì các cạnh của M đang chiếm hai đầu mút của mình, ta có tiêu chí rất dễ kiểm tra:

> M là **maximal** khi và chỉ khi **mọi cạnh của G có ít nhất một đầu mút đã ghép trong M**.

**Chứng minh chiều thuận:** nếu tồn tại cạnh e=(u,v) mà cả u,v đều tự do, có thể thêm e vào M. Khi đó `M∪{e}` vẫn là matching và chứa M thực sự; trái maximal.

**Chứng minh chiều đảo:** nếu mọi cạnh đều chạm ít nhất một đỉnh đã ghép, không có cạnh e∉M nào đồng thời có hai đầu tự do để thêm vào mà không phá matching. Do đó không có siêu tập matching đúng của M; M maximal.

**Đây chỉ là kiểm tra khả năng thêm cạnh.** Một đường tăng có thể dùng cạnh mới, **bỏ bớt cạnh đã ghép**, rồi lại nhận những cạnh khác; vì thế maximal không loại trừ đường tăng dài hơn một cạnh.

### Cách nhận diện nhanh

- Nếu có **hai đỉnh tự do nối nhau bằng một cạnh**, matching **chưa maximal**.
- Nếu không có cạnh nào nối hai đỉnh tự do, matching **đã maximal**, dù vẫn có thể còn đường tăng dài 3, 5, 7... cạnh.
- Nếu **không còn đỉnh tự do**, matching perfect; chắc chắn maximal và maximum.
- Nếu còn đỉnh tự do nhưng chúng không có cạnh nối nhau, cần **kiểm tra đường tăng** mới biết maximum hay chưa.

## 4. Thuật toán tham lam tìm maximal matching

Duyệt **mỗi cạnh một lần** theo thứ tự đầu vào. Khi gặp cạnh (u,v), chỉ nhận nếu **cả u và v đều đang tự do**.

~~~text
GREEDY_MAXIMAL_MATCHING(V, E):
    mate[v] <- NONE for all vertices
    M <- empty

    FOR EACH edge (u,v) IN input order:
        IF mate[u] == NONE AND mate[v] == NONE:
            mate[u] <- v
            mate[v] <- u
            ADD (u,v) TO M

    RETURN M
~~~

**Tại sao kết quả là matching?** Mỗi cạnh được nhận khi hai đầu đều chưa ghép, rồi hai đầu bị đánh dấu đã ghép; vì thế hai cạnh được nhận không thể chung đỉnh.

**Tại sao maximal?** Xét một cạnh e không được nhận khi nó được quét. Khi ấy có ít nhất một đầu e đã được ghép; về sau greedy **không bao giờ gỡ** cạnh đã nhận nên đầu đó vẫn được ghép. Vì mọi cạnh đều đã được xét một lần, không có cạnh nào với hai đầu tự do ở cuối thuật toán.

**Độ phức tạp:** nếu có danh sách E cạnh, đánh dấu mate độ dài V tốn O(V), quét cạnh tốn O(E). Tổng **O(V+E)** thời gian và O(V) bộ nhớ phụ, ngoài input và danh sách kết quả.

**Điểm yếu:** đáp án phụ thuộc **thứ tự cạnh**. Với P4, nếu xét (1,2) đầu tiên, greedy lấy 1 cặp; nếu xét (0,1) rồi (2,3), greedy lấy 2 cặp. Cả hai đều maximal, chỉ đáp án sau là maximum.

### Không nên tự gọi greedy maximal là maximum

Một chương trình chỉ dùng mảng `used[v]`, chọn các cạnh không xung đột rồi dừng có thể rất nhanh, nhưng **chưa chứng minh kích thước tối ưu**. Nếu đề yêu cầu “tối đa số cặp”, greedy đơn thuần là **xấp xỉ**, không phải thuật toán đúng hoàn toàn.

## 5. Cận xấp xỉ 1/2 của maximal matching

Gọi M là **bất kỳ maximal matching** và M* là một **maximum matching** của cùng đồ thị (không trọng số, tối đa số cặp).

Vì M maximal, **mọi cạnh** e∈M* có **ít nhất một đầu mút** thuộc một cạnh của M. Nếu cả hai đầu của e đều tự do trong M, có thể thêm e vào M, mâu thuẫn maximal.

Ta “gán” mỗi cạnh của M* cho một cạnh của M mà nó chạm. Một cạnh của M có đúng **hai đầu mút**. Vì các cạnh của M* đôi một không chung đỉnh, mỗi đầu mút của một cạnh thuộc M có thể thuộc **tối đa một cạnh** của M*. Vậy một cạnh M có thể “chịu trách nhiệm” cho **tối đa hai cạnh** của M*.

Suy ra:

`|M*| ≤ 2|M|`,

hay:

`|M| ≥ |M*|/2`.

**Mọi maximal matching là nghiệm xấp xỉ ít nhất 1/2 kích thước tối ưu.**

### Cận 1/2 là chặt

Đường P4 ở mục 2 có maximal M kích thước 1 và maximum M* kích thước 2. Do đó:

`|M|/|M*| = 1/2`.

Không thể bảo đảm một tỉ lệ cao hơn 1/2 cho **mọi** maximal matching chỉ từ tính maximal.

**Đây là cận cho số cặp, không phải tổng trọng số.** Nếu mỗi cạnh có lợi ích riêng, một matching maximal theo bao hàm có thể có tổng lợi ích **rất kém** so với maximum-weight matching. Không được đem chứng minh 1/2 theo **số cạnh** áp vào giá trị trọng số một cách máy móc.

## 6. Đường xen kẽ và đường tăng

Cho matching hiện tại M:

- Một cạnh thuộc M gọi là **cạnh đã ghép (matched edge)**.
- Một cạnh không thuộc M gọi là **cạnh chưa ghép (unmatched edge)**.
- Một **đường xen kẽ (alternating path)** dùng lần lượt cạnh **chưa ghép**, **đã ghép**, **chưa ghép**, ... hoặc theo chiều xen kẽ tương ứng.
- **Đường tăng (augmenting path)** là đường xen kẽ **bắt đầu và kết thúc tại hai đỉnh tự do**, nên cạnh đầu và cạnh cuối đều **chưa ghép**.

Đường tăng đơn có số cạnh **lẻ**: 1,3,5,... và có **nhiều hơn một cạnh chưa ghép** so với cạnh đã ghép.

### Đảo cạnh trên đường tăng

Với đường tăng P, đặt:

`M' = M △ E(P)`,

trong đó △ là **hiệu đối xứng**: bỏ các cạnh của M nằm trên P, thêm các cạnh của P chưa nằm trong M.

Vì các cạnh trên P xen kẽ và hai đầu tự do, sau phép đảo mỗi đỉnh trên P vẫn nằm trong nhiều nhất một cạnh của matching. Ngoài P, M không đổi.

Do P có **k+1** cạnh chưa ghép và **k** cạnh đã ghép:

`|M'| = |M| − k + (k+1) = |M|+1`.

Vậy mọi đường tăng đều chứng minh matching hiện tại **chưa maximum**.

### Phân biệt đường tăng với một cạnh có hai đầu tự do

Một cạnh duy nhất giữa hai đỉnh tự do cũng là một đường tăng **dài 1**. Maximal matching **không có đường tăng dài 1**.

Nhưng maximal vẫn có thể còn đường tăng dài 3 hoặc 5 như các ví dụ. **Maximum matching không có đường tăng ở bất kỳ độ dài nào**.

## 7. Định lý Berge: tiêu chuẩn đúng của maximum matching

**Định lý Berge (Berge's Lemma):**

> Một matching M trong đồ thị vô hướng là **maximum-cardinality** khi và chỉ khi **không tồn tại đường tăng đối với M**.

### Chiều dễ: có đường tăng thì chưa maximum

Mục 6 cho phép đảo các cạnh dọc đường tăng để tạo matching mới có `|M|+1` cạnh. Vậy M không thể lớn nhất.

### Chiều ngược: nếu chưa maximum thì tồn tại đường tăng

Giả sử M chưa maximum, tức tồn tại matching M* có `|M*|>|M|`.

Xét đồ thị con chỉ gồm các cạnh nằm trong **đúng một** trong hai matching: `M△M*`.

Tại mỗi đỉnh, mỗi matching dùng không quá một cạnh, nên bậc trong đồ thị con này tối đa **2**. Các thành phần liên thông của đồ thị con là:

- Đường xen kẽ giữa cạnh của M và cạnh của M*;
- Chu trình xen kẽ **độ dài chẵn**;
- Hoặc đỉnh/cạnh đơn giản như trường hợp suy biến.

Trên một chu trình xen kẽ chẵn, số cạnh thuộc M và M* bằng nhau. Trên đường xen kẽ, hai số lượng có thể bằng nhau hoặc lệch **đúng 1**.

Vì `|M*|>|M|`, phải tồn tại **ít nhất một thành phần đường** có **nhiều hơn một cạnh M*** so với cạnh M. Đường đó bắt đầu và kết thúc bằng cạnh của M*, vì vậy hai đầu của nó **không được M ghép**. Nó chính là **đường tăng theo M**.

Suy ra nếu M chưa maximum, chắc chắn tồn tại đường tăng. Phản đảo: không có đường tăng ⇒ M maximum.

### Hệ quả thực hành

Một thuật toán hoàn chỉnh có thể:

1. Bắt đầu từ matching rỗng hoặc matching maximal tham lam.
2. Tìm một đường tăng theo matching hiện tại.
3. Đảo cạnh trên đường; số cặp tăng 1.
4. Lặp cho đến khi không còn đường tăng.

**Phần khó nằm ở bước tìm đường tăng.** Trên đồ thị **hai phía**, có thể dùng DFS tăng luồng Kuhn hoặc Hopcroft–Karp. Với **đồ thị tổng quát có chu trình lẻ**, cần thuật toán chuyên biệt như **Edmonds' blossom** để tìm đường tăng đúng và hiệu quả; không được coi DFS Kuhn hai phía là lời giải tổng quát cho mọi đồ thị.

## 8. Phản ví dụ phân công hai phía có đường tăng dài 5

Cho ba ứng viên `L0,L1,L2` và ba công việc `R0,R1,R2`. Các cạnh tương thích, theo thứ tự input:

~~~text
L0 -- R0
L0 -- R1
L1 -- R0
L2 -- R1
L2 -- R2
~~~

### Greedy maximal theo thứ tự cạnh

- Chọn `L0–R0`.
- Bỏ `L0–R1` vì L0 đã ghép.
- Bỏ `L1–R0` vì R0 đã ghép.
- Chọn `L2–R1`.
- Bỏ `L2–R2` vì L2 đã ghép.

Kết quả:

`M_greedy={(L0,R0),(L2,R1)}`, `|M_greedy|=2`.

L1 và R2 còn tự do nhưng **không có cạnh L1–R2**, nên matching là **maximal**.

### Đổi cặp để đạt 3

Đường tăng:

~~~text
L1 -- R0 == L0 -- R1 == L2 -- R2

-- : cạnh chưa ghép
== : cạnh đang ghép
~~~

Lần lượt là:

`L1–R0` chưa ghép, `R0–L0` đã ghép, `L0–R1` chưa ghép, `R1–L2` đã ghép, `L2–R2` chưa ghép.

Đảo dọc đường tăng cho:

`M*={(L1,R0),(L0,R1),(L2,R2)}`,

có **3 cặp**, bao phủ mọi đỉnh. Vì `min(|L|,|R|)=3`, kết quả là **maximum và perfect**.

**Bài học:** để tăng số cặp, có thể phải **đổi việc** của cả hai ứng viên đang có cặp, không chỉ gán một ứng viên chưa có việc vào một công việc còn trống ngay bên cạnh.

## 9. Thuật toán Kuhn DFS cho maximum matching hai phía

Với đồ thị hai phía `G=(L∪R,E)`, ta lưu:

- `adj[u]`: danh sách đỉnh phía R có cạnh nối từ u∈L.
- `pairR[v]`: đỉnh phía L hiện đang ghép với v∈R; `-1` nếu R_v tự do.

Lần lượt xét từng đỉnh `u∈L`:

1. Nếu có công việc v tự do mà u có thể nhận, ghép u–v.
2. Nếu v đã ghép với một ứng viên `owner=pairR[v]`, thử **dời owner sang một công việc khác** bằng đệ quy.
3. Nếu dời được owner, trả v cho u; số cặp tăng thêm một.
4. Dùng mảng `seenR` riêng cho **mỗi lần tìm đường tăng**, để không duyệt vô hạn cùng một đỉnh R.

### Giả mã

~~~text
FUNCTION AUGMENT(u, seenR):
    FOR v IN adj[u]:
        IF seenR[v]:
            CONTINUE
        seenR[v] = true

        IF pairR[v] = NONE OR AUGMENT(pairR[v], seenR):
            pairR[v] = u
            RETURN true
    RETURN false

FUNCTION KUHN_MAXIMUM_BIPARTITE_MATCHING():
    pairR[v] = NONE for each right vertex v
    count = 0

    FOR each u in L:
        seenR[v] = false for all v in R
        IF AUGMENT(u, seenR):
            count = count + 1

    RETURN count, pairR
~~~

Mỗi lời gọi thành công của `AUGMENT(u)` tìm ra và **đảo một đường tăng**, dù code không xây dãy đường tường minh. Khi `pairR[v]` đang có owner, lời gọi đệ quy tìm vị trí khác cho owner; nếu được, cặp cũ bị thay thế có kiểm soát.

### Vì sao phương pháp tìm được matching lớn nhất?

Khi xử lý lần lượt từng ứng viên phía L, ta duy trì matching **lớn nhất trên tập các ứng viên L đã xét**. Giả sử đã tối ưu cho tập L trước đó và thêm ứng viên u:

- Mọi matching trên tập mới nhiều hơn tối đa **1 cạnh** so với tối ưu trước, vì chỉ thêm một đỉnh bên L.
- Nếu có matching tăng được, theo định lý Berge sẽ có **đường tăng**. Do matching trước đã tối ưu trên tập L cũ, đường tăng phải xuất phát từ ứng viên mới u (không có đường tăng bắt đầu ở một ứng viên cũ chưa ghép nếu không đã cải thiện được trước).
- `AUGMENT(u)` duyệt các khả năng hoán đổi công việc dọc đường xen kẽ bằng DFS; nếu tồn tại đường tăng từ u, DFS tìm được.

Do đó sau khi duyệt tất cả đỉnh L, matching là maximum của toàn đồ thị hai phía.

**Lưu ý:** phải **reset seenR trước mỗi ứng viên u mới**. Một công việc không dùng được trong lượt u1 có thể trở thành hữu ích sau những phép đổi cặp ở lượt u2. Nếu giữ một visited chung cho mọi lượt, có thể bỏ lỡ đường tăng và trả kết quả dưới tối ưu.

### Độ phức tạp Kuhn

Gọi `n_L=|L|`, `n_R=|R|`, m=|E| (đếm cung tương thích trong danh sách kề).

Một lần tìm augment có thể xem tới O(m) cạnh; thực hiện tối đa `n_L` lượt. Vì vậy chặn thời gian:

`O(n_L·m + n_L·n_R)`

cho cài đặt reset mảng seenR toàn bộ mỗi lượt, thường viết **O(n_L·m)** khi m đủ lớn, hoặc **O(n_L·(m+n_R))** để kể cả đồ thị thưa/rỗng.

Bộ nhớ: **O(n_L+n_R+m)** gồm danh sách kề, hai mảng ghép, visited và stack đệ quy. Với dữ liệu lớn, **Hopcroft–Karp** tìm nhiều đường tăng ngắn nhất theo từng giai đoạn và đạt **O(m·sqrt(n_L+n_R))** thời gian tiêu chuẩn.

**Giới hạn stack Java:** DFS Kuhn đệ quy có thể sâu O(n_L) nếu chuỗi đổi cặp dài. Khi dữ liệu rất lớn, dùng giải pháp lặp hoặc Hopcroft–Karp phù hợp môi trường để tránh `StackOverflowError`.

## 10. Min vertex cover và định lý König — chứng chỉ tối ưu

Một **phủ đỉnh (vertex cover)** là tập đỉnh C sao cho **mỗi cạnh của đồ thị có ít nhất một đầu thuộc C**.

- **Minimum vertex cover**: phủ đỉnh có **ít đỉnh nhất**.
- **Maximal matching**: tập cạnh không còn mở rộng theo bao hàm.
- Hai khái niệm “cover” và “matching” là hai đối tượng khác nhau.

Vì các cạnh của matching không chia sẻ đỉnh, **mọi vertex cover** phải lấy ít nhất một đầu mút của **mỗi cạnh trong matching**. Vì vậy:

`|M| ≤ |C|`

đối với mọi matching M và vertex cover C.

### Định lý König cho đồ thị hai phía

Trên **đồ thị hai phía**:

`maximum matching size = minimum vertex cover size`.

Đây là một mối liên hệ sâu hơn cận dưới đơn giản. Sau khi Kuhn tìm được matching maximum, ta có thể xây luôn **một minimum vertex cover**:

1. Bắt đầu từ **tất cả đỉnh L chưa ghép**, đi tìm các đỉnh đạt được bằng **đường xen kẽ**.
2. Từ đỉnh L, chỉ đi qua **cạnh chưa ghép** sang R.
3. Từ đỉnh R đã ghép, đi qua **cạnh đang ghép** về đỉnh L sở hữu R.
4. Gọi `Z_L`, `Z_R` lần lượt là các đỉnh L/R đã tới.
5. Tạo:

`C = (L ∖ Z_L) ∪ Z_R`.

Với matching maximum không tồn tại đường tăng tới đỉnh R tự do, nên C là vertex cover và:

`|C|=|M|`.

Theo cận dưới `|M|≤minimumCoverSize`, dấu bằng chứng minh cả matching và cover đều tối ưu.

### Ví dụ Hall có cover hỗn hợp

Có `L0,L1,L2` và `R0,R1`, với cạnh:

~~~text
L0 -- R0
L1 -- R0
L2 -- R1
~~~

Matching lớn nhất có **2 cặp**: L0–R0 và L2–R1; L1 chưa có cặp. Bắt đầu đường xen kẽ từ L1:

- L1 đi qua cạnh chưa ghép tới R0.
- R0 đang ghép với L0, nên đi theo cạnh ghép về L0.
- L0 không đi tiếp được sang công việc khác.

Khi đó `Z_L={L1,L0}`, `Z_R={R0}`. Phủ đỉnh:

`C=(L∖Z_L)∪Z_R={L2,R0}`

có kích thước 2 và che **tất cả ba cạnh**. Vì matching cũng có kích thước 2 nên chúng xác nhận nhau theo König.

### Cảnh báo: König không áp dụng cho mọi đồ thị tổng quát

Xét **tam giác** ba đỉnh với ba cạnh:

~~~text
0 -- 1
 \  /
  2
~~~

Maximum matching có **1 cạnh**, vì mọi hai cạnh đều chung đỉnh. Nhưng minimum vertex cover cần **2 đỉnh** mới che được cả ba cạnh, nên:

`maximumMatching=1 ≠ minimumVertexCover=2`.

Đừng dùng công thức König hoặc cách dựng `(L∖Z_L)∪Z_R` cho đồ thị **không hai phía**. Với đồ thị tổng quát, bài toán matching lớn nhất vẫn giải đa thức bằng họ thuật toán **blossom**, còn minimum vertex cover là bài toán khó hơn nhiều (NP-hard tổng quát).

## 11. Định lý Hall: khi nào ghép được mọi đỉnh một phía?

Định lý Hall (*Marriage Theorem*) mô tả **khả năng bão hòa toàn bộ L** trong đồ thị hai phía.

Với mọi tập con `U⊆L`, ký hiệu `N(U)` là tập các đỉnh R có ít nhất một cạnh nối với một đỉnh thuộc U.

Tồn tại matching ghép được **tất cả đỉnh L** khi và chỉ khi:

`∀U⊆L: |N(U)|≥|U|`.

**Ý nghĩa:** không có nhóm ứng viên nào phải tranh giành **ít công việc tương thích hơn số ứng viên** trong nhóm đó.

### Ví dụ vi phạm Hall

Ở ví dụ L0,L1,L2 và R0,R1 vừa nêu, chọn `U={L0,L1}`:

`N(U)={R0}`,

nên `|N(U)|=1<2=|U|`. Hai ứng viên L0,L1 cùng chỉ nhận được công việc R0, vì thế không thể ghép cả hai cùng lúc. Mặc dù greedy có thể đạt maximum size 2, matching ấy không bão hòa L, cũng không perfect.

**Không đủ chỉ kiểm tra từng đỉnh L có ít nhất một hàng xóm.** Mỗi ứng viên có một lựa chọn riêng chưa bảo đảm chúng có đủ **lựa chọn khác nhau** cho mọi nhóm.

Nếu `|L|=|R|` và thỏa Hall cho mọi U⊆L, tồn tại perfect matching. Nếu `|L|<|R|`, Hall bảo đảm phủ L, nhưng **không phải perfect** của toàn bộ đồ thị vì vẫn còn đỉnh R tự do.

## 12. Matching tổng quát, hai phía, có trọng số: chọn đúng bài toán

### 12.1. Đồ thị không hai phía

Định lý Berge, khái niệm maximal và maximum vẫn đúng trên mọi đồ thị vô hướng. Thuật toán greedy maximal cũng áp dụng được cho đồ thị bất kỳ.

Nhưng **Kuhn DFS ở trên dựa vào cấu trúc L–R**. Với đồ thị có **chu trình lẻ**, các đường xen kẽ có thể tạo cấu hình **blossom** cần co cụm/giải nở mới tìm đúng đường tăng. Đừng cố chia mọi đồ thị thành L và R khi không tồn tại phép chia ấy.

Để tìm **maximum matching trong đồ thị tổng quát**, dùng thuật toán Edmonds' blossom hoặc thư viện đáng tin cho general matching, thay vì code Kuhn hai phía.

### 12.2. Matching có trọng số

Nếu mỗi cạnh có “điểm phù hợp”, lương hay chi phí khác nhau, cần hỏi rõ:

- **Maximum-cardinality matching:** tối đa số cặp; bỏ qua trọng số.
- **Maximum-weight matching:** tối đa tổng trọng số cạnh đã chọn; có thể ưu tiên ít cặp hơn nếu không yêu cầu số cặp lớn nhất trước.
- **Minimum-cost perfect assignment:** gán hết các công việc/ứng viên theo điều kiện, tối thiểu tổng chi phí; có thể dùng **Hungarian algorithm** trong mô hình thích hợp.
- **Lexicographic objective:** tối đa số cặp trước, rồi trong các matching cùng số cặp thì tối đa tổng điểm; phải mô hình rõ **hai tiêu chí**.

Không thể dùng greedy maximal hoặc Kuhn cardinality và tuyên bố đã tối ưu **tổng điểm**. Cận 1/2 nêu ở mục 5 chỉ về **số cạnh**, không phải giá trị của matching có trọng số.

### 12.3. B-matching và phân công nhiều việc

Nếu một người được làm **nhiều nhất b việc** hoặc một công việc cần **nhiều người**, đây không còn là matching chuẩn với “mỗi đỉnh tối đa một cạnh”. Có thể cần **b-matching** hoặc **max flow** với dung lượng trên các đỉnh/cung phù hợp.

Với matching hai phía đơn vị, có thể dựng mạng luồng:

~~~text
source -> mỗi L_i    capacity 1
L_i -> R_j          capacity 1 nếu tương thích
mỗi R_j -> sink     capacity 1
~~~

Một đơn vị luồng nguyên ứng với một cặp ghép. Nhờ tính nguyên của max flow khi dung lượng nguyên, **max flow = maximum bipartite matching cardinality**.

**Khi mô hình hóa năng lực >1**, phải nêu chính xác giới hạn phía L/R và điều kiện cho cạnh; không tự nhân bản đỉnh mà không xử lý khả năng trùng/tài nguyên riêng.

## 13. Java 17+ — greedy maximal, Kuhn maximum và minimum vertex cover

Chương trình sau có một đầu vào **đồ thị hai phía**, với `leftCount=L`, `rightCount=R` và từng cạnh input `{leftIndex,rightIndex}`:

- `greedyMaximal` quét cạnh input theo thứ tự, chỉ nhận khi hai đầu tự do.
- `kuhnMaximum` tìm đường tăng bằng DFS trên các đỉnh R, có mảng visited R **mới cho mỗi đỉnh L**.
- `minimumVertexCover` tạo tập `(L∖Z_L)∪Z_R` bằng BFS đường xen kẽ từ tất cả đỉnh L chưa ghép, dựa vào maximum matching.
- `verifyMatching` kiểm tra mọi cặp đều là cạnh có thật, không dùng một đỉnh hai lần và hai mảng ghép khớp nhau.
- `verifyMaximal` kiểm tra greedy không còn cạnh nối hai đỉnh tự do.
- `verifyCover` kiểm tra mọi cạnh có ít nhất một đầu trong cover và `|cover|=|maximumMatching|`.
- `bruteMaximum` dùng **DP trên bitmask R** để tính kích thước maximum matching theo một cách **độc lập**, chỉ dành cho đồ thị nhỏ.
- `crossCheck` sinh **300 đồ thị hai phía ngẫu nhiên**, gồm đầu vào rỗng, đỉnh cô lập và cạnh trùng, rồi so với DP và cận xấp xỉ 1/2.

**Quy ước đầu vào:** đồ thị hai phía có thể có L hoặc R bằng 0; một cạnh phải có cả hai ID trong phạm vi. Các cạnh trùng được phép trong input nhưng **không giúp tạo thêm cặp** vì mỗi đỉnh chỉ ghép một lần. Matching của **đồ thị rỗng cả hai phía** được coi là **perfect theo quy ước rỗng** (mọi đỉnh — không có đỉnh nào — đã được ghép).

Tạo tệp **`MatchingMaximalVsMaximumDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class MatchingMaximalVsMaximumDemo {
    record Pair(int left, int right) {}

    static final class BipartiteGraph {
        final int leftCount;
        final int rightCount;
        final List<List<Integer>> adjacency = new ArrayList<>();
        final List<Pair> edges = new ArrayList<>();

        BipartiteGraph(int leftCount, int rightCount, int[][] tuples) {
            Objects.requireNonNull(tuples, "tuples");
            if (leftCount < 0 || rightCount < 0) {
                throw new IllegalArgumentException("Negative size");
            }
            this.leftCount = leftCount;
            this.rightCount = rightCount;

            for (int u = 0; u < leftCount; u++) {
                adjacency.add(new ArrayList<>());
            }
            for (int[] tuple : tuples) {
                if (tuple == null || tuple.length != 2) {
                    throw new IllegalArgumentException("Expected {L,R}");
                }
                int u = tuple[0], v = tuple[1];
                if (u < 0 || u >= leftCount ||
                        v < 0 || v >= rightCount) {
                    throw new IllegalArgumentException("Invalid endpoint");
                }
                edges.add(new Pair(u, v));
                adjacency.get(u).add(v);
            }
        }
    }

    record Matching(int[] leftMate, int[] rightMate, int size) {
        List<String> edges() {
            List<String> result = new ArrayList<>();
            for (int u = 0; u < leftMate.length; u++) {
                if (leftMate[u] != -1) {
                    result.add("L" + u + "-R" + leftMate[u]);
                }
            }
            return List.copyOf(result);
        }

        boolean perfect(int leftCount, int rightCount) {
            return leftCount == rightCount && size == leftCount;
        }
    }

    record Cover(boolean[] left, boolean[] right) {
        List<String> vertices() {
            List<String> result = new ArrayList<>();
            for (int u = 0; u < left.length; u++) {
                if (left[u]) {
                    result.add("L" + u);
                }
            }
            for (int v = 0; v < right.length; v++) {
                if (right[v]) {
                    result.add("R" + v);
                }
            }
            return List.copyOf(result);
        }
    }

    static Matching greedyMaximal(BipartiteGraph g) {
        int[] lm = new int[g.leftCount];
        int[] rm = new int[g.rightCount];
        Arrays.fill(lm, -1);
        Arrays.fill(rm, -1);
        int size = 0;

        for (Pair edge : g.edges) {
            int u = edge.left(), v = edge.right();
            if (lm[u] == -1 && rm[v] == -1) {
                lm[u] = v;
                rm[v] = u;
                size++;
            }
        }
        return new Matching(lm, rm, size);
    }

    private static boolean augment(
            int u, BipartiteGraph g, int[] rightMate,
            boolean[] seenRight) {
        for (int v : g.adjacency.get(u)) {
            if (seenRight[v]) {
                continue;
            }
            seenRight[v] = true;

            if (rightMate[v] == -1 ||
                    augment(rightMate[v], g, rightMate, seenRight)) {
                rightMate[v] = u;
                return true;
            }
        }
        return false;
    }

    static Matching kuhnMaximum(BipartiteGraph g) {
        int[] rightMate = new int[g.rightCount];
        Arrays.fill(rightMate, -1);
        int size = 0;

        for (int u = 0; u < g.leftCount; u++) {
            boolean[] seenRight = new boolean[g.rightCount];
            if (augment(u, g, rightMate, seenRight)) {
                size++;
            }
        }

        int[] leftMate = new int[g.leftCount];
        Arrays.fill(leftMate, -1);
        for (int v = 0; v < g.rightCount; v++) {
            int u = rightMate[v];
            if (u != -1) {
                leftMate[u] = v;
            }
        }
        return new Matching(leftMate, rightMate, size);
    }

    // König: (L outside alternating reachability) union
    // (R inside alternating reachability).
    static Cover minimumVertexCover(
            BipartiteGraph g, Matching maximum) {
        boolean[] reachedL = new boolean[g.leftCount];
        boolean[] reachedR = new boolean[g.rightCount];
        ArrayDeque<Integer> queue = new ArrayDeque<>();

        for (int u = 0; u < g.leftCount; u++) {
            if (maximum.leftMate()[u] == -1) {
                reachedL[u] = true;
                queue.addLast(u);
            }
        }

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();

            for (int v : g.adjacency.get(u)) {
                // Move L->R only through UNMATCHED edges.
                if (maximum.leftMate()[u] == v || reachedR[v]) {
                    continue;
                }
                reachedR[v] = true;

                // Move R->L only through MATCHED edge.
                int owner = maximum.rightMate()[v];
                if (owner != -1 && !reachedL[owner]) {
                    reachedL[owner] = true;
                    queue.addLast(owner);
                }
            }
        }

        boolean[] coverL = new boolean[g.leftCount];
        boolean[] coverR = new boolean[g.rightCount];
        for (int u = 0; u < g.leftCount; u++) {
            coverL[u] = !reachedL[u];
        }
        System.arraycopy(reachedR, 0, coverR, 0, g.rightCount);
        return new Cover(coverL, coverR);
    }

    static void verifyMatching(
            BipartiteGraph g, Matching m) {
        if (m.leftMate().length != g.leftCount ||
                m.rightMate().length != g.rightCount) {
            throw new AssertionError("Wrong mate array sizes");
        }

        int countL = 0, countR = 0;
        for (int u = 0; u < g.leftCount; u++) {
            int v = m.leftMate()[u];
            if (v == -1) continue;
            if (v < 0 || v >= g.rightCount ||
                    m.rightMate()[v] != u ||
                    !g.adjacency.get(u).contains(v)) {
                throw new AssertionError("Invalid matched edge");
            }
            countL++;
        }
        for (int v = 0; v < g.rightCount; v++) {
            int u = m.rightMate()[v];
            if (u == -1) continue;
            if (u < 0 || u >= g.leftCount ||
                    m.leftMate()[u] != v) {
                throw new AssertionError("Inconsistent matching");
            }
            countR++;
        }
        if (countL != countR || countL != m.size()) {
            throw new AssertionError("Matching size mismatch");
        }
    }

    static void verifyMaximal(BipartiteGraph g, Matching m) {
        for (Pair edge : g.edges) {
            if (m.leftMate()[edge.left()] == -1 &&
                    m.rightMate()[edge.right()] == -1) {
                throw new AssertionError(
                        "Free-free edge: matching is not maximal");
            }
        }
    }

    static void verifyCover(
            BipartiteGraph g, Matching maximum, Cover cover) {
        if (cover.left().length != g.leftCount ||
                cover.right().length != g.rightCount) {
            throw new AssertionError("Invalid cover arrays");
        }
        for (Pair edge : g.edges) {
            if (!cover.left()[edge.left()] &&
                    !cover.right()[edge.right()]) {
                throw new AssertionError("Uncovered edge");
            }
        }
        if (cover.vertices().size() != maximum.size()) {
            throw new AssertionError("König equality failed");
        }
    }

    // Independent oracle: DP on right-side used-vertex bitmask.
    // Runs only on SMALL graphs, rightCount <= 10.
    private static int bruteDfs(
            BipartiteGraph g, int left, int mask, int[][] memo) {
        if (left == g.leftCount) {
            return 0;
        }
        if (memo[left][mask] != -1) {
            return memo[left][mask];
        }

        // Leave this left vertex unmatched.
        int best = bruteDfs(g, left + 1, mask, memo);
        // Or choose any still unused right vertex it can connect to.
        for (int v : g.adjacency.get(left)) {
            if ((mask & (1 << v)) == 0) {
                best = Math.max(best, 1 + bruteDfs(
                        g, left + 1, mask | (1 << v), memo));
            }
        }
        return memo[left][mask] = best;
    }

    static int bruteMaximum(BipartiteGraph g) {
        if (g.rightCount > 10) {
            throw new IllegalArgumentException(
                    "Bitmask oracle only for rightCount<=10");
        }
        int[][] memo = new int[g.leftCount + 1][1 << g.rightCount];
        for (int[] row : memo) {
            Arrays.fill(row, -1);
        }
        return bruteDfs(g, 0, 0, memo);
    }

    static void verify(
            BipartiteGraph g, Matching greedy,
            Matching maximum, Cover cover) {
        verifyMatching(g, greedy);
        verifyMatching(g, maximum);
        verifyMaximal(g, greedy);
        verifyMaximal(g, maximum);
        verifyCover(g, maximum, cover);

        if (maximum.size() != bruteMaximum(g) ||
                greedy.size() > maximum.size() ||
                2 * greedy.size() < maximum.size()) {
            throw new AssertionError(
                    "Maximum/half-approximation mismatch");
        }
    }

    static void show(String name, BipartiteGraph g) {
        Matching greedy = greedyMaximal(g);
        Matching maximum = kuhnMaximum(g);
        Cover cover = minimumVertexCover(g, maximum);
        verify(g, greedy, maximum, cover);

        System.out.println(name
                + " greedySize=" + greedy.size()
                + " greedyEdges=" + greedy.edges()
                + " maximumSize=" + maximum.size()
                + " maximumEdges=" + maximum.edges()
                + " minVertexCover=" + cover.vertices()
                + " perfect=" + maximum.perfect(
                        g.leftCount, g.rightCount));
    }

    static void crossCheck() {
        Random random = new Random(2026L);
        for (int test = 0; test < 300; test++) {
            int left = random.nextInt(7);
            int right = random.nextInt(7);
            int m = left == 0 || right == 0 ? 0 :
                    random.nextInt(2 * left * right + 1);
            int[][] edges = new int[m][2];

            for (int i = 0; i < m; i++) {
                edges[i][0] = random.nextInt(left);
                edges[i][1] = random.nextInt(right);
            }

            BipartiteGraph g = new BipartiteGraph(
                    left, right, edges);
            Matching greedy = greedyMaximal(g);
            Matching maximum = kuhnMaximum(g);
            Cover cover = minimumVertexCover(g, maximum);
            verify(g, greedy, maximum, cover);
        }
        System.out.println("crossCheck=PASS (300 bipartite graphs)");
    }

    public static void main(String[] args) {
        show("trap", new BipartiteGraph(3, 3, new int[][]{
            {0,0}, {0,1}, {1,0}, {2,1}, {2,2}
        }));

        show("path4", new BipartiteGraph(2, 2, new int[][]{
            {1,0}, {0,0}, {1,1}
        }));

        show("hall", new BipartiteGraph(3, 2, new int[][]{
            {0,0}, {1,0}, {2,1}
        }));

        show("star", new BipartiteGraph(3, 3, new int[][]{
            {0,0}, {1,0}, {2,0}
        }));

        show("ties", new BipartiteGraph(2, 2, new int[][]{
            {0,0}, {0,1}, {1,0}, {1,1}
        }));

        show("parallel", new BipartiteGraph(2, 2, new int[][]{
            {0,0}, {0,0}, {1,1}
        }));

        show("isolated", new BipartiteGraph(3, 3, new int[][]{
            {0,0}, {2,1}
        }));

        show("empty", new BipartiteGraph(
                0, 0, new int[0][2]));

        show("leftEmpty", new BipartiteGraph(
                0, 3, new int[0][2]));

        try {
            new BipartiteGraph(2, 2, new int[][]{{0,2}});
            throw new AssertionError("Expected validation failure");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidEndpoint=rejected");
        }

        crossCheck();
    }
}
~~~

### Biên dịch và chạy

Yêu cầu **JDK 17 trở lên**:

~~~bash
javac MatchingMaximalVsMaximumDemo.java
java MatchingMaximalVsMaximumDemo
~~~

**Đầu ra xác định:** các cạnh được in theo thứ tự ID ứng viên phía L tăng dần; thuật toán Kuhn xử lý danh sách kề theo thứ tự input.

~~~text
trap greedySize=2 greedyEdges=[L0-R0, L2-R1] maximumSize=3 maximumEdges=[L0-R1, L1-R0, L2-R2] minVertexCover=[L0, L1, L2] perfect=true
path4 greedySize=1 greedyEdges=[L1-R0] maximumSize=2 maximumEdges=[L0-R0, L1-R1] minVertexCover=[L0, L1] perfect=true
hall greedySize=2 greedyEdges=[L0-R0, L2-R1] maximumSize=2 maximumEdges=[L0-R0, L2-R1] minVertexCover=[L2, R0] perfect=false
star greedySize=1 greedyEdges=[L0-R0] maximumSize=1 maximumEdges=[L0-R0] minVertexCover=[R0] perfect=false
ties greedySize=2 greedyEdges=[L0-R0, L1-R1] maximumSize=2 maximumEdges=[L0-R1, L1-R0] minVertexCover=[L0, L1] perfect=true
parallel greedySize=2 greedyEdges=[L0-R0, L1-R1] maximumSize=2 maximumEdges=[L0-R0, L1-R1] minVertexCover=[L0, L1] perfect=true
isolated greedySize=2 greedyEdges=[L0-R0, L2-R1] maximumSize=2 maximumEdges=[L0-R0, L2-R1] minVertexCover=[L0, L2] perfect=false
empty greedySize=0 greedyEdges=[] maximumSize=0 maximumEdges=[] minVertexCover=[] perfect=true
leftEmpty greedySize=0 greedyEdges=[] maximumSize=0 maximumEdges=[] minVertexCover=[] perfect=false
invalidEndpoint=rejected
crossCheck=PASS (300 bipartite graphs)
~~~

### Giải thích từng nhóm kiểm thử

**trap:** greedy tạo 2 cặp dù maximum có 3 cặp. Phép đổi cặp diễn ra qua một đường tăng dài 5 cạnh như mục 8; đây là trường hợp phân biệt quan trọng nhất.

**path4:** nếu greedy nhận cạnh giữa trước, nó dừng ở kích thước 1. Kuhn tìm được hai cặp để phủ cả bốn đỉnh.

**hall:** hai ứng viên L0 và L1 tranh một vị trí R0. Matching tốt nhất chỉ có 2 cặp; công thức König dựng min vertex cover `{L2,R0}` cũng kích thước 2.

**star:** ba ứng viên chỉ có chung một công việc R0. Matching lớn nhất là 1, phủ đỉnh cực tiểu chỉ cần `{R0}`. Không phải mọi matching maximum đều perfect.

**ties:** có nhiều matching maximum khác nhau; greedy chọn `{L0–R0,L1–R1}`, Kuhn có thể đổi thành `{L0–R1,L1–R0}`. Cùng có kích thước 2, đều tối ưu.

**parallel:** cạnh trùng `L0–R0` được ghi hai lần nhưng không tạo thêm quyền ghép L0 hoặc R0; matching lớn nhất vẫn có 2 cặp.

**isolated:** L1 và R2 không có hàng xóm. Ghép được 2 cặp, không thể perfect.

**empty:** không có đỉnh, matching rỗng đạt mọi đỉnh theo nghĩa logic, vì vậy `perfect=true` theo quy ước. **leftEmpty:** L rỗng và R có ba đỉnh, matching rỗng không perfect vì ba đỉnh R còn tự do.

**invalidEndpoint:** ID R2 nằm ngoài khoảng 0..1 nên constructor báo lỗi rõ, tránh âm thầm làm sai dữ liệu.

**crossCheck:** 300 đồ thị hai phía nhỏ, có thể có cạnh trùng và đỉnh cô lập. Mỗi đồ thị được kiểm tra bằng DP bitmask độc lập để lấy kích thước tối ưu, bằng kiểm tra mỗi cạnh có hai đầu tự do để xác nhận maximal, bằng phủ đỉnh theo König, và bằng bất đẳng thức `2·|greedy|≥|maximum|`. Nếu sai, chương trình ném `AssertionError`; chỉ khi tất cả đúng mới in PASS.

### Khi nào không dùng trực tiếp code minh họa?

Đây là **Kuhn cho đồ thị hai phía**. Một đồ thị không hai phía không thể nạp trung thực vào hai bộ L/R mà vẫn giữ mọi cạnh; cần thuật toán general matching như blossom.

Với đồ thị lớn nhiều cạnh, Kuhn O(n_L·m) có thể chậm; cân nhắc **Hopcroft–Karp** O(m√(n_L+n_R)) hoặc max flow nếu còn ràng buộc dung lượng. Nếu đề muốn **maximum-weight matching**, code chỉ trả **maximum cardinality**, không tối ưu tổng điểm.

Hàm `bruteMaximum` có độ phức tạp theo bitmask và chỉ dành cho n_R≤10; không chạy làm lời giải chính cho input lớn.

## 14. Độ phức tạp và so sánh lựa chọn thuật toán

| Bài toán | Cách tiếp cận | Thời gian thường dùng |
| --- | --- | --- |
| Tìm **một maximal matching** | Greedy quét cạnh | **O(V+E)** |
| Kiểm tra matching đã maximal chưa | Kiểm tra mỗi cạnh có đầu mút matched | **O(V+E)** |
| Maximum matching **hai phía** (cơ bản) | Kuhn DFS đường tăng | **O(n_L·(E+n_R))** |
| Maximum matching **hai phía** (lớn) | Hopcroft–Karp | **O(E√V)** |
| Maximum matching **hai phía** bằng flow | Mạng capacity 1, max flow | Tùy thuật toán flow |
| Maximum matching **đồ thị tổng quát** | Edmonds' blossom / biến thể | Đa thức; phụ thuộc triển khai |
| Chứng minh tối ưu với một cover hai phía | König + BFS alternating | **O(V+E)** sau maximum |
| Vét cạn độc lập cho bài nhỏ | DP bitmask phía R | **O(n_L·2^n_R·(n_R+1))** chặn rộng |

**Không xem “maximum matching” là cùng nghĩa với “maximal matching” chỉ vì tiếng Việt đều có thể viết “cực đại”.** Nên gắn nhãn rõ:

- **Cực đại theo bao hàm** = maximal.
- **Lớn nhất về số cặp** = maximum-cardinality.

Với matching có trọng số, cũng cần tách “lớn nhất theo số cặp” khỏi “lớn nhất theo tổng trọng số”.

## 15. Các lỗi thường gặp

1. **Dịch maximal và maximum cùng là “cực đại” rồi kết luận chúng giống nhau.**
2. **Dùng greedy chọn cạnh không xung đột để giải maximum cardinality** mà không kiểm tra đường tăng.
3. **Đếm số đỉnh matched thay vì số cạnh matching**, dẫn đến kết quả gấp đôi.
4. **Ghép một đỉnh vào hai cạnh**, phá định nghĩa matching.
5. **Đánh giá maximal bằng kích thước gần `|V|/2`**, trong khi tiêu chí thật là không thể bổ sung cạnh.
6. **Cho rằng nhiều đỉnh tự do luôn có thể thêm một cặp**, nhưng có thể không có cạnh nối hai đỉnh tự do.
7. **Cho rằng không còn cạnh thêm được thì không còn đường tăng**, bị phản ví dụ P4 bác bỏ.
8. **Không đảo cạnh đã ghép khi đi đường tăng**, khiến trùng đỉnh hoặc không tăng kích thước.
9. **Dùng đường có hai cạnh chưa ghép liên tiếp làm đường tăng**, trong khi phải xen kẽ.
10. **Quên hai đầu đường tăng phải là đỉnh tự do**, không bảo đảm tăng thêm một cặp.
11. **Nhầm số cặp tăng với số cạnh trên đường tăng**, trong khi đảo một đường tăng luôn tăng đúng 1.
12. **Giữ visited R chung cho mọi lượt Kuhn**, có thể bỏ lỡ đường cải thiện sau.
13. **Chặn mọi đỉnh R đã matched mà không thử dời owner**, biến Kuhn thành greedy đơn thuần.
14. **Không kiểm tra quyền ghép (cạnh thật)** khi phục dựng pairL từ pairR.
15. **Chỉ kiểm tra mảng pairL mà không kiểm tra pairR tương ứng**, có thể gán trùng công việc.
16. **Dùng một DFS Kuhn của đồ thị hai phía cho đồ thị chứa chu trình lẻ**, thiếu blossom.
17. **Áp dụng định lý König cho tam giác**, sai vì đồ thị không hai phía.
18. **Xây min vertex cover từ matching chưa maximum**, công thức alternating có thể không cho cover nhỏ nhất.
19. **Duyệt từ L qua cả cạnh matched và unmatched khi dựng Z**, phá quy tắc đường xen kẽ.
20. **Quên xuất phát từ mọi L còn tự do** khi dựng cover.
21. **Nhầm min vertex cover là matching**, mặc dù cover là tập **đỉnh**, matching là tập **cạnh**.
22. **Suy ra perfect chỉ vì matching có số cặp bằng |L| khi |R|>|L|**, trong khi còn đỉnh R tự do.
23. **Suy ra mọi L có ít nhất một hàng xóm thì Hall thỏa**, quên kiểm tra các tập con U.
24. **Không xử lý cạnh input trùng** và cho rằng chúng tạo nhiều vị trí làm việc độc lập.
25. **Không kiểm tra ID biên** khi các mảng có thể rỗng.
26. **Dùng DP vét cạn bitmask n_R lớn** như lời giải production, gây nổ bộ nhớ/thời gian.
27. **Tuyên bố 1/2 approximation theo tổng trọng số** dù chứng minh chỉ theo số cặp.
28. **Tự cho rằng greedy maximal luôn nhỏ đúng bằng một nửa tối ưu**, trong thực tế có thể bằng maximum.
29. **So hai tập cạnh của các maximum matching và kết luận một thuật toán sai vì chọn cạnh khác**, trong khi matching tối ưu có thể không duy nhất.
30. **Bỏ qua yêu cầu phân công có hạn mức >1 hoặc chi phí**, vốn cần b-matching/min-cost flow hoặc mô hình khác.
31. **Gọi perfect matching là maximum bất kỳ**, nhưng maximum có thể còn đỉnh tự do.
32. **Áp dụng công thức số đỉnh đã ghép =2|M| khi có mô hình một đỉnh được nhiều cặp**, vượt ngoài matching chuẩn.

## 16. Bài tập có lời giải

**Bài 1.** Matching là tập cạnh như thế nào? **Đáp án:** không có hai cạnh nào chia sẻ một đầu mút.

**Bài 2.** Ghép 4 cặp nghĩa là bao nhiêu đỉnh được ghép? **Đáp án:** 8 đỉnh, mỗi cặp dùng 2 đỉnh.

**Bài 3.** “Maximal” theo bao hàm nghĩa là gì? **Đáp án:** không thể **thêm riêng một cạnh** nào vào matching mà vẫn giữ không xung đột.

**Bài 4.** “Maximum-cardinality” nghĩa là gì? **Đáp án:** số cạnh trong matching đạt giá trị lớn nhất trên toàn bộ matching của đồ thị.

**Bài 5.** Mọi maximum có maximal không? **Đáp án:** có; nếu thêm được một cạnh, matching chưa đạt số cạnh lớn nhất.

**Bài 6.** Mọi maximal có maximum không? **Đáp án:** không. P4 có maximal gồm cạnh giữa kích thước 1 nhưng maximum kích thước 2.

**Bài 7.** Trên P4, vì sao `{(1,2)}` là maximal? **Đáp án:** hai đỉnh tự do 0 và 3 không có cạnh nối; các cạnh còn lại chạm đỉnh đã ghép.

**Bài 8.** Trên P4, matching maximum là gì? **Đáp án:** `{(0,1),(2,3)}`, kích thước 2, perfect.

**Bài 9.** Đường tăng theo matching `{(1,2)}` trên P4 là dãy nào? **Đáp án:** `0–1–2–3`, các cạnh chưa ghép–đã ghép–chưa ghép.

**Bài 10.** Đảo cạnh trên đường tăng thay đổi kích thước bao nhiêu? **Đáp án:** tăng đúng 1 cạnh/cặp.

**Bài 11.** Matching maximum có đường tăng không? **Đáp án:** không, theo định lý Berge.

**Bài 12.** Matching maximal có thể có đường tăng dài 5 không? **Đáp án:** có, ví dụ `L1–R0–L0–R1–L2–R2` theo matching tham lam ở mục 8.

**Bài 13.** Trong ví dụ ba ứng viên ba công việc, greedy có mấy cặp? **Đáp án:** 2, gồm L0–R0 và L2–R1.

**Bài 14.** Matching maximum của cùng ví dụ có mấy cặp? **Đáp án:** 3, gồm L0–R1, L1–R0, L2–R2.

**Bài 15.** Vì sao greedy maximal bảo đảm ít nhất nửa số cặp tối ưu? **Đáp án:** mỗi cạnh của maximum chạm một cạnh trong maximal; mỗi cạnh maximal có hai đầu nên gánh tối đa hai cạnh maximum.

**Bài 16.** Cận 1/2 có chặt không? **Đáp án:** có, đường P4 đạt đúng tỉ lệ 1/2.

**Bài 17.** Cận 1/2 có tự động đúng cho tổng lợi ích của matching có trọng số không? **Đáp án:** không, cần thuật toán/định lý riêng.

**Bài 18.** Kuhn DFS được trình bày cho loại đồ thị nào? **Đáp án:** đồ thị **hai phía**, với một phía L và phía kia R.

**Bài 19.** Khi một việc v đã ghép với ứng viên khác, Kuhn có bỏ luôn v không? **Đáp án:** không; thử dời ứng viên chủ cũ theo một đường xen kẽ trước khi quyết định thất bại.

**Bài 20.** Vì sao seenRight phải reset mỗi lần tìm augment? **Đáp án:** trạng thái ghép thay đổi sau mỗi lần cải thiện, nên khả năng đổi cặp ở lượt mới khác lượt trước.

**Bài 21.** Định lý König phát biểu gì trên đồ thị hai phía? **Đáp án:** kích thước maximum matching bằng kích thước minimum vertex cover.

**Bài 22.** Với `Z_L,Z_R` tìm được bằng alternating BFS từ L chưa ghép, công thức phủ đỉnh? **Đáp án:** `(L∖Z_L)∪Z_R`.

**Bài 23.** Ở ví dụ Hall `L0,L1→R0; L2→R1`, phủ đỉnh nhỏ nhất là gì? **Đáp án:** một đáp án `{R0,L2}`, kích thước 2.

**Bài 24.** Vì sao không có matching phủ L0,L1 cùng lúc ở ví dụ Hall? **Đáp án:** `N({L0,L1})={R0}` chỉ có 1 việc cho 2 người, vi phạm Hall.

**Bài 25.** Tam giác có maximum matching và min vertex cover kích thước bao nhiêu? **Đáp án:** lần lượt 1 và 2; đây là phản ví dụ áp dụng König cho đồ thị không hai phía.

**Bài 26.** Nếu |L|=3 và |R|=5 mà matching ghép được cả 3 đỉnh L, nó có perfect không? **Đáp án:** không; còn ít nhất hai đỉnh R tự do. Nó là matching bão hòa L.

**Bài 27.** Nếu hai cạnh input cùng nối L0–R0, có thể ghép L0 với R0 hai lần không? **Đáp án:** không, matching mỗi đỉnh tham gia tối đa một cạnh.

**Bài 28.** Thời gian greedy maximal? **Đáp án:** O(V+E) với một lượt quét danh sách cạnh và mảng đánh dấu.

**Bài 29.** Thời gian Kuhn DFS cơ bản? **Đáp án:** thường viết O(n_L·E), kể cả reset visited cần O(n_L·(E+n_R)) ở trường hợp thưa.

**Bài 30.** Nếu input có hàng triệu cạnh, nên cân nhắc thuật toán nào cho maximum bipartite matching? **Đáp án:** Hopcroft–Karp O(E√V) hoặc biến thể phù hợp, thay vì Kuhn cơ bản.

**Bài 31.** Perfect matching có thể tồn tại trong đồ thị có số đỉnh lẻ không? **Đáp án:** không, vì mỗi cặp bao phủ đúng hai đỉnh.

**Bài 32.** Nếu mỗi ứng viên được nhận hai công việc, matching chuẩn có phù hợp trực tiếp không? **Đáp án:** không; cần mô hình b-matching hoặc flow với hạn mức 2.

## 17. Checklist phân biệt và triển khai

1. **Đề hỏi maximal hay maximum?** Dịch rõ “cực đại theo bao hàm” hay “số cặp lớn nhất”.
2. **Mục tiêu là số cặp hay tổng lợi ích/trọng số?** Chọn đúng bài toán tối ưu.
3. **Đồ thị có hai phía không?** Nếu không, Kuhn/Hopcroft–Karp hai phía không áp dụng trực tiếp.
4. **Mỗi đỉnh được dùng nhiều nhất một lần?** Nếu không, cần b-matching/flow.
5. **Có kiểm tra matching hợp lệ: mỗi cạnh thật, không trùng đỉnh?**
6. **Nếu chỉ cần maximal, quét cạnh và nhận khi hai đầu tự do có đủ không?** Có.
7. **Nếu cần maximum, có cách tìm đường tăng/thuật toán đúng cho loại đồ thị?**
8. **Đã thử phản ví dụ P4 với cạnh giữa được chọn đầu tiên chưa?**
9. **Trong Kuhn, có thử đổi cặp của chủ cũ khi R đã matched không?**
10. **Mảng seenR có tạo mới mỗi lần xét L không?**
11. **Khi xây pairL từ pairR, có kiểm tra tính nhất quán và kích thước?**
12. **Nếu cần certificate cho matching hai phía, có dựng min vertex cover và kiểm tra König không?**
13. **Cover có che mọi cạnh và có |cover|=|maximumMatching| không?**
14. **Đã phân biệt left-perfect, perfect, maximum và maximal chưa?**
15. **Có xét trường hợp Hall thất bại dù mỗi người có ít nhất một công việc?**
16. **Cạnh trùng, đỉnh cô lập, L/R rỗng, nhiều nghiệm tối ưu đã được xử lý chưa?**
17. **Có kiểm tra cận 2|greedy|≥|maximum| cho cardinality, không áp sang trọng số?**
18. **Có dùng DP bitmask/brute-force chỉ trên input nhỏ để kiểm chứng không?**
19. **Có đánh giá O(V+E) cho greedy và O(n_L·(E+n_R)) cho Kuhn?**
20. **Nếu cần full general matching, có chuyển sang thuật toán blossom thay vì cố dùng Kuhn không?**

**Ghi nhớ:** **maximal** chỉ có nghĩa **không thể thêm một cạnh mà không bỏ cạnh cũ**; **maximum** nghĩa **không tồn tại matching nào có nhiều cặp hơn**. Maximal không có đường tăng dài 1, nhưng có thể còn đường tăng dài 3,5,...; maximum không có **bất kỳ đường tăng** nào. Greedy nhanh và bảo đảm ≥1/2 optimum về số cặp; Kuhn giải đúng maximum **trên đồ thị hai phía** bằng cách **đổi cặp theo đường tăng**; định lý König cho một **phủ đỉnh cực tiểu** làm chứng chỉ tối ưu.

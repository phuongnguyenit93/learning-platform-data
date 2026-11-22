# Ghép cặp hai phía bằng tìm đường tăng

## Mục tiêu học tập

Trong nhóm **Ghép cặp và phân công**, bài toán **ghép cặp hai phía** (*bipartite matching*) mô hình hóa việc nối hai nhóm đối tượng, chẳng hạn **người lao động – công việc**, **sinh viên – đề tài**, **máy – nhiệm vụ**, **người đặt – suất phục vụ**. Mỗi cặp chỉ hợp lệ nếu có một cạnh thể hiện rằng hai đối tượng tương thích.

Nếu mỗi đối tượng chỉ được nhận **nhiều nhất một** đối tượng phía bên kia, ta cần một **matching**: một tập cạnh không có hai cạnh nào chung đầu mút. Bài **maximum cardinality bipartite matching** yêu cầu matching có **nhiều cạnh nhất**.

Điểm quyết định là **đường tăng** (*augmenting path*): một đường xen kẽ giữa cạnh **chưa ghép** và cạnh **đang ghép**, bắt đầu và kết thúc ở **đỉnh chưa được ghép**. Bằng cách **đảo trạng thái các cạnh trên đường ấy**, ta có thể tăng số cặp lên đúng **1**, đồng thời tái phân công một số cặp cũ thay vì phá bỏ chúng.

Sau bài này, bạn sẽ:

1. Xác định đúng **hai phía L/R**, cạnh hợp lệ, matching, đỉnh đã ghép/chưa ghép và kích thước matching.
2. Phân biệt **matching cực đại theo bao hàm** (*maximal*) với **matching có số cặp lớn nhất** (*maximum*).
3. Hiểu **đường xen kẽ**, **đường tăng** và thao tác **đảo cạnh** trên đường tăng.
4. Tìm đường tăng bằng **DFS kiểu Kuhn**, dùng mảng `ownerRight[]` và mảng `visitedRight[]`.
5. Giải thích vì sao phải **đặt lại visited cho mỗi lần tìm từ một đỉnh trái mới**, trong khi giữ matching đã cải thiện.
6. Chứng minh tính đúng bằng **định lý Berge**: một matching là maximum **khi và chỉ khi** không còn đường tăng.
7. Phân tích độ phức tạp của Kuhn **`O(L\cdot E)`** theo cận thông dụng, cùng bộ nhớ `O(L+R+E)`.
8. Biết **định lý Hall** để nhận diện khi có thể ghép hết một phía, và **định lý König** để xây một **minimum vertex cover** từ maximum matching.
9. Chạy chương trình **Java 17+** độc lập, kiểm tra đầu ra của một ví dụ phải tái phân công và ví dụ thiếu láng giềng.
10. Nhận diện khi phải chuyển sang **Hopcroft–Karp**, **max flow**, **min-cost matching** hoặc **general graph matching**.

---

## 1. Bài toán và mô hình đồ thị hai phía

### 1.1. Đồ thị hai phía là gì?

Một đồ thị vô hướng `G=(V,E)` được gọi là **hai phía** (*bipartite*) nếu tập đỉnh có thể chia thành hai tập rời nhau:

\[
V=L\cup R,\qquad L\cap R=\varnothing,
\]

và **mọi cạnh** đều nối **một đỉnh L với một đỉnh R**:

\[
E\subseteq\{\{u,v\}:u\in L,\ v\in R\}.
\]

Trong mô hình ghép cặp, chúng ta thường giữ hai tập L và R **đã được chỉ định từ đề bài**. Ví dụ:

- `L=\{L_0,L_1,L_2\}`: ba nhân viên.
- `R=\{R_0,R_1,R_2\}`: ba công việc.
- Cạnh `L_i-R_j`: nhân viên i có thể làm công việc j.

Cạnh không có ý nghĩa “bên trái làm chủ bên phải”; đó chỉ là cách biểu diễn điều kiện tương thích. Một bài có thể cho danh sách kề từ trái sang phải để tiện cài thuật toán.

### 1.2. Khi nào graph **không** phải hai phía?

Nếu đồ thị đầu vào chứa một **chu trình lẻ**, không thể chia đỉnh thành hai phía sao cho mọi cạnh đều băng qua hai phía. Ví dụ tam giác gồm ba đỉnh và ba cạnh **không** phải đồ thị hai phía.

Thuật toán Kuhn ở bài này đòi **phân hoạch hai phía hợp lệ**. Nó không phải thuật toán matching tổng quát cho mọi graph vô hướng. Với graph bất kỳ, có thể cần **Edmonds' blossom algorithm**.

Nếu đề đã cho rõ “người – công việc”, tính hai phía có sẵn. Nếu đề chỉ cho graph vô hướng chưa phân loại, có thể dùng BFS/DFS tô hai màu để kiểm tra graph hai phía trước khi chạy.

### 1.3. Matching là gì?

Một matching `M\subseteq E` là tập cạnh mà **không có hai cạnh nào cùng đi vào một đỉnh**:

\[
\forall v\in V,\quad
\deg_M(v)\le1.
\]

Ví dụ:

```text
L0 -- R1    matched
L1 -- R0    matched
L2          unmatched
```

Tập cạnh `\{L_0-R_1,L_1-R_0\}` là matching, có **kích thước 2**.

Một đỉnh **matched** nếu nó thuộc một cạnh của M; ngược lại gọi **free**, **unmatched** hoặc “chưa được ghép”. Một matching có k cạnh thì dùng đúng **k đỉnh bên trái và k đỉnh bên phải**.

### 1.4. Maximum và maximal không giống nhau

- **Maximal matching:** không thể **thêm trực tiếp một cạnh mới** vào matching hiện tại mà vẫn giữ điều kiện hai đầu chưa dùng. Nó chỉ tối đa theo **bao hàm**.
- **Maximum matching:** trong tất cả matching, có **số cạnh lớn nhất**. Nếu `M^*` là maximum, mọi matching M đều thỏa `|M|\le|M^*|`.

Mọi maximum matching đều maximal, nhưng một maximal matching **có thể nhỏ hơn** maximum matching.

Ví dụ:

```text
L0 -- R0
 |     
 +---- R1

L1 -- R0
```

Nếu chỉ chọn cạnh `L0-R0` rồi dừng khi không thể thêm một cạnh **giữa hai đỉnh đều free**, ta có maximal matching kích thước 1. Nhưng matching `\{L0-R1,L1-R0\}` có kích thước **2**, nên matching ban đầu **không maximum**.

Đường tăng cho phép **tái phân công L0** để có chỗ cho L1, đó là lý do thuật toán tốt hơn tham lam chọn cạnh trống đơn thuần.

### 1.5. Giới hạn trên hiển nhiên

Nếu `|L|=L_n` và `|R|=R_n`, mỗi cạnh matching dùng một đỉnh ở mỗi phía, nên:

\[
|M|\le\min(L_n,R_n).
\]

Nhưng đây chỉ là **cận trên**, không bảo đảm sẽ đạt được: có thể nhiều đỉnh trái chỉ nối chung một đỉnh phải, hoặc có những đỉnh không có cạnh.

---

## 2. Vì sao “chọn đối tượng chưa dùng đầu tiên” có thể thất bại?

Xét đồ thị nhỏ:

| Đỉnh trái | Những đỉnh phải có thể ghép |
| --- | --- |
| `L_0` | `R_0,R_1` |
| `L_1` | `R_0` |

Nếu xét L0 trước và tham lam lấy R0:

```text
L0 --- R0  [đã ghép]
L0 --- R1  [chưa ghép]
L1 --- R0  [không thể thêm trực tiếp]
```

L1 không còn đỉnh phải trống trong danh sách kề. Dừng tại đây cho kết quả 1 cặp là **sai**.

Nhưng ta có thể sửa hai mối ghép:

```text
Trước: L0-R0

Sau:  L0-R1
      L1-R0
```

Kết quả 2 cặp, tối ưu vì cả L và R đều có hai đỉnh.

Thao tác này chính là **tìm một đường tăng** và **đảo trạng thái các cạnh** trên đường.

---

## 3. Đường xen kẽ và đường tăng

### 3.1. Cạnh matched và unmatched

Với matching hiện tại M:

- **Cạnh matched:** cạnh thuộc M.
- **Cạnh unmatched:** cạnh tồn tại trong graph nhưng không thuộc M.

Một **đường xen kẽ** (*alternating path*) là một đường mà trạng thái matched/unmatched **xen kẽ nhau** khi đi dọc đường.

Ví dụ:

```text
L1 -- R0 -- L0 -- R1

L1-R0 : unmatched
R0-L0 : matched
L0-R1 : unmatched
```

Chuỗi cạnh ở đây có mẫu:

```text
unmatched, matched, unmatched
```

### 3.2. Đường tăng

Một **đường tăng đối với M** là một đường xen kẽ có:

1. Đỉnh đầu **chưa matched**.
2. Đỉnh cuối **chưa matched**.
3. Cạnh đầu và cạnh cuối đều **chưa thuộc M**.
4. Các đỉnh bên trong xen kẽ đi qua cạnh matched/unmatched.

Trong đồ thị hai phía, ta có thể tìm đường tăng bắt đầu từ một đỉnh **trái free** và kết thúc ở một đỉnh **phải free**.

Ví dụ trên, sau khi ghép `L0-R0`, đường:

```text
L1 -> R0 -> L0 -> R1
```

là một đường tăng.

### 3.3. Đảo cạnh trên đường tăng

Nếu P là đường tăng, ta tạo matching mới bằng **hiệu đối xứng**:

\[
M'=M\triangle E(P),
\]

nghĩa là:

- Những cạnh **chưa thuộc M** trên P trở thành **matched**.
- Những cạnh **đang thuộc M** trên P trở thành **unmatched**.
- Các cạnh ngoài P giữ nguyên.

Với đường có `2k+1` cạnh, số cạnh unmatched trên P là `k+1`, số cạnh matched là k. Sau đảo:

\[
|M'|=|M|+(k+1)-k=|M|+1.
\]

Vì mỗi đỉnh bên trong P mất đúng một cạnh matched và nhận đúng một cạnh matched khác, nó vẫn có **một** bạn ghép. Hai đầu free trở thành matched. Vì vậy `M'` vẫn là matching hợp lệ, lớn hơn đúng **1** cặp.

### 3.4. “Đường” không nhất thiết là ngắn nhất

Kuhn DFS chỉ cần tìm **một đường tăng bất kỳ**. Nó không bắt buộc tìm đường ngắn nhất theo số cạnh, đường có độ dài nhỏ nhất, hay đường có “chi phí” thấp nhất.

Sự lựa chọn đường ảnh hưởng số lần duyệt, trạng thái matching trung gian và cặp cuối cùng. **Định lý Berge** bảo đảm mọi đường tăng đều cho phép tăng cardinality đúng 1.

### 3.5. Không phải cứ đi qua matched edge là đường tăng

Một đường xen kẽ bắt đầu từ đỉnh đã matched hoặc kết thúc tại đỉnh đã matched không nhất thiết làm tăng số cặp khi đảo. Điều kiện **hai đầu đều free** là thiết yếu.

Tương tự, một vòng xen kẽ có số cạnh matched và unmatched bằng nhau; đảo vòng có thể đổi cách ghép nhưng **không tăng** kích thước matching.

---

## 4. Cách hiểu DFS từ một đỉnh trái free

Ta duy trì một mảng:

\[
ownerRight[r]=
\begin{cases}
u,&\text{nếu }R_r\text{ đang matched với }L_u,\\
-1,&\text{nếu }R_r\text{ chưa matched.}
\end{cases}
\]

Với mỗi đỉnh trái u chưa ghép, hàm DFS thử những đỉnh phải v có cạnh `L_u-R_v`.

### 4.1. Nếu Rv còn trống

Nếu `ownerRight[v]=-1`, ta có thể ghép ngay:

```text
ownerRight[v] = u
return true
```

Tìm được đường tăng dài 1 cạnh: L_u→R_v.

### 4.2. Nếu Rv đã có người ghép

Giả sử `ownerRight[v]=x`. Ta không được gán ngay `ownerRight[v]=u` và bỏ rơi x. Phải thử **chuyển x sang một đỉnh phải khác** bằng lời gọi đệ quy:

```text
if dfs(x) succeeds:
    ownerRight[v] = u
    return true
```

Nếu x có thể được ghép chỗ khác, L_u có thể “lấy lại” v mà **không làm mất cặp cũ**. Đây chính là việc đi dọc đường xen kẽ rồi đảo cạnh khi trả về từ đệ quy.

### 4.3. Nếu không tìm được cách tái phân công

Nếu Rv đã ghép với x và DFS(x) không thể tìm chỗ thay thế, thử đỉnh phải tiếp theo trong danh sách kề của u.

Nếu mọi lựa chọn đều không thành công, DFS(u) trả false. Khi đó không tồn tại đường tăng **theo cấu trúc DFS đã duyệt hết** từ đỉnh trái u trên matching hiện tại.

### 4.4. Mảng visited phải gắn với **một lượt tìm đường tăng**

Một đỉnh phải có thể xuất hiện nhiều lần trong quá trình đệ quy của **cùng** một lượt tìm. Để không quay vòng hoặc duyệt lại vô ích, ta đánh dấu `visitedRight[v]` khi đã thử v trong lượt ấy.

Nhưng khi chuyển sang một đỉnh trái gốc mới, phải **xóa visited hoặc dùng mã lượt mới**. Một đỉnh phải từng không cho đường tăng ở lượt trước vẫn có thể là một phần của đường tăng **ở lượt sau** khi matching đã thay đổi.

**Không được giữ visitedRight=true vĩnh viễn** qua mọi lượt tìm. Đây là một lỗi rất phổ biến khiến thuật toán trả matching quá nhỏ.

### 4.5. Pseudocode Kuhn đơn giản

```text
maximumBipartiteMatching(L, R, adjacency):
    ownerRight[0..R-1] = -1
    matched = 0

    for u = 0..L-1:
        visitedRight[0..R-1] = false

        if tryAugment(u, visitedRight, ownerRight):
            matched++

    return matched, ownerRight

tryAugment(u, visitedRight, ownerRight):
    for each right v in adjacency[u]:
        if visitedRight[v]:
            continue

        visitedRight[v] = true

        if ownerRight[v] == -1
           or tryAugment(ownerRight[v],
                         visitedRight, ownerRight):
            ownerRight[v] = u
            return true

    return false
```

Hàm `tryAugment` thực hiện chính việc tìm đường tăng và tái phân công. Trước mỗi lượt u, các đỉnh trái được xử lý trước đó **đã được thử**, còn matching hiện tại được giữ nguyên.

---

## 5. Mô phỏng từng lượt trên ví dụ cần tái phân công

Xét đồ thị hai phía với 6 đỉnh trái `L0..L5` và 5 đỉnh phải `R0..R4`:

| Đỉnh trái | Danh sách đỉnh phải kề |
| --- | --- |
| `L0` | `R0,R1` |
| `L1` | `R0` |
| `L2` | `R1,R2` |
| `L3` | `R2,R3` |
| `L4` | `R3,R4` |
| `L5` | `R4` |

Đây là dữ liệu chính của chương trình Java ở mục 11.

### 5.1. Xét L0

Ban đầu mọi đỉnh phải đều free. DFS(L0) thử R0 trước:

```text
Matching: { L0-R0 }
ownerRight = [0, -1, -1, -1, -1]
size = 1
```

### 5.2. Xét L1: đường tăng có 3 cạnh

L1 chỉ kề R0, nhưng R0 đang do L0 giữ. DFS(L1) thử tái phân công L0:

```text
L1 -> R0  (unmatched)
R0 -> L0  (matched hiện tại)
L0 -> R1  (unmatched, R1 đang free)
```

Đây là đường tăng. Đảo trạng thái làm:

```text
Trước: L0-R0
Sau:   L1-R0, L0-R1
```

Mảng:

```text
ownerRight = [1, 0, -1, -1, -1]
size = 2
```

**Điểm cốt lõi:** Dù R0 đã có chủ, việc tìm đường tăng cho phép **đổi chủ của R0** và giữ nguyên số người đã ghép trước đó, rồi thêm L1.

### 5.3. Xét L2

L2 kề R1 và R2:

- R1 đã có L0, có thể thử DFS tái phân công L0.
- Nhưng các lựa chọn của L0 (R0,R1) không tạo một đỉnh phải free mới trong lượt này.
- Quay lại L2, thử R2 đang free.

Kết quả:

```text
ownerRight = [1, 0, 2, -1, -1]
size = 3
```

### 5.4. Xét L3

L3 kề R2,R3. R2 đang do L2 giữ; thử tái phân công L2 không mở ra chỗ trống phù hợp trong lượt này. Sau đó L3 thử R3 free:

```text
ownerRight = [1, 0, 2, 3, -1]
size = 4
```

### 5.5. Xét L4

L4 kề R3,R4. R3 đang có L3, đường tái phân công không thành công nên dùng R4 free:

```text
ownerRight = [1, 0, 2, 3, 4]
size = 5
```

### 5.6. Xét L5

L5 chỉ kề R4, nhưng R4 đã do L4 giữ. DFS thử dịch chuyển L4, rồi L3, L2, L0 và L1 nếu cần qua chuỗi các cạnh matched/unmatched. Tất cả 5 đỉnh phải đều đang được sử dụng và **không có đỉnh phải free** nào để kết thúc đường tăng.

Lượt của L5 thất bại; matching giữ nguyên kích thước 5.

### 5.7. Matching cuối cùng

Theo thứ tự duyệt kề trong bảng:

```text
L0 - R1
L1 - R0
L2 - R2
L3 - R3
L4 - R4
L5   unmatched
```

`ownerRight[]`:

```text
[1, 0, 2, 3, 4]
```

Đối ứng theo phía trái:

```text
leftToRight = [1, 0, 2, 3, 4, -1]
```

Matching có đúng 5 cạnh. Vì chỉ có **5 đỉnh phải**, không matching nào có hơn 5 cặp. Vậy đây là maximum matching:

\[
\boxed{|M^*|=5}.
\]

### 5.8. Kết quả cuối cùng có duy nhất không?

Không nhất thiết. Nếu nhiều cạnh có thể hoán đổi theo vòng xen kẽ, có thể tồn tại nhiều maximum matching khác nhau. Một triển khai DFS có thể cho bộ ghép cuối khác tùy:

- Thứ tự xét đỉnh trái.
- Thứ tự hàng xóm trong danh sách kề.
- Quy tắc khi nhiều đường tăng đều khả thi.

Điều cần đúng là **số cặp tối đa** và tất cả các cặp hợp lệ, không nhất thiết trùng y hệt một danh sách cặp mẫu nếu input không cố định thứ tự.

---

## 6. Chứng minh vì sao đường tăng tăng đúng một cặp

Giả sử matching M và một đường tăng P:

```text
free L -- unmatched -- R
       -- matched ---- L
       -- unmatched -- R
       -- matched ---- L
       -- unmatched -- free R
```

Một đường tăng luôn có **số cạnh lẻ** `2k+1`:

- Cạnh ở vị trí 1,3,5,... là **unmatched**, tổng `k+1` cạnh.
- Cạnh ở vị trí 2,4,6,... là **matched**, tổng k cạnh.

Đảo các cạnh trên P:

- Loại k cạnh matched cũ.
- Thêm k+1 cạnh unmatched cũ.
- Giữ nguyên tất cả cạnh matching khác.

Số cạnh mới:

\[
|M'|=|M|-k+(k+1)=|M|+1.
\]

Tính hợp lệ vẫn được bảo toàn:

- Hai đỉnh free ở hai đầu đường trước đó không có cạnh matched, sau đảo mỗi đỉnh nhận 1 cạnh matched.
- Mỗi đỉnh bên trong đường trước đó có 1 cạnh matched của P, sau đảo cạnh đó bị loại và một cạnh khác của P trở thành matched.
- Đỉnh nằm ngoài P không bị đổi.

Do đó **mỗi đường tăng tạo ra matching lớn hơn đúng 1**, chứ không đơn thuần là “tìm một đường nối hai phía”.

---

## 7. Định lý Berge: không còn đường tăng ⇔ matching tối đa

### 7.1. Phát biểu

**Định lý Berge** áp dụng cho matching trong graph vô hướng nói chung:

\[
\boxed{
M\text{ là maximum matching}
\iff
\text{không có đường tăng đối với }M.
}
\]

Định lý chính là nền tảng của thuật toán dựa trên augmenting path.

### 7.2. Chiều dễ: có đường tăng thì chưa tối đa

Nếu còn đường tăng P, đảo cạnh trên P tạo `M'` với:

\[
|M'|=|M|+1.
\]

Vậy M **không thể** có kích thước lớn nhất.

### 7.3. Chiều khó: nếu M chưa tối đa thì phải có đường tăng

Giả sử tồn tại matching `M^*` có nhiều cạnh hơn M:

\[
|M^*|>|M|.
\]

Xét **hiệu đối xứng** `M\triangle M^*`: chỉ giữ những cạnh thuộc đúng một trong hai matching.

Vì ở mỗi matching, một đỉnh có bậc ≤1, trong graph hiệu đối xứng, mỗi đỉnh có bậc ≤2. Các thành phần của graph này chỉ gồm:

- Đường đi xen kẽ các cạnh của M và `M^*`.
- Chu trình chẵn xen kẽ.
- Cạnh/đường riêng lẻ như trường hợp đặc biệt.

Trên một chu trình xen kẽ, số cạnh của hai matching **bằng nhau**. Trên một đường xen kẽ có hai đầu không thuận lợi, số cạnh có thể bằng nhau hoặc hơn nhau đúng 1.

Vì `|M^*|>|M|`, phải có **ít nhất một thành phần đường** chứa nhiều cạnh của `M^*` hơn cạnh của M. Đường đó bắt đầu và kết thúc bằng cạnh của `M^*`, hai đầu đều **free đối với M**. Chính nó là **đường tăng đối với M**.

Mâu thuẫn với giả thiết “không có đường tăng”. Vậy nếu không có đường tăng thì M đã maximum.

### 7.4. Hệ quả thực hành

Một thuật toán có thể bắt đầu từ matching rỗng, rồi:

```text
while tồn tại đường tăng:
    đảo cạnh trên đường đó
```

Khi không tìm được đường tăng **từ bất kỳ đỉnh free thích hợp nào**, matching cuối cùng là maximum.

Thuật toán Kuhn sử dụng cấu trúc hai phía để tìm đường tăng hiệu quả bằng DFS.

---

## 8. Vì sao Kuhn chỉ thử từng đỉnh trái một lần?

Kuhn duyệt các đỉnh trái theo thứ tự. Khi bắt đầu xử lý `L_u`, các đỉnh trái đứng trước đã có matching **cực đại về số cặp trong graph chỉ xét các đỉnh trái đã xử lý**. Mệnh đề này có thể chứng minh bằng quy nạp.

### 8.1. Cơ sở

Trước khi xét bất kỳ đỉnh trái nào, matching rỗng là tối ưu trên một graph không có đỉnh trái.

### 8.2. Bước quy nạp

Khi thêm đỉnh trái u mới vào tập đã xét:

- Maximum matching của graph mở rộng có thể tăng **tối đa 1**, vì chỉ thêm một đỉnh trái mới có thể tham gia nhiều nhất một cặp.
- Nếu DFS(u) tìm được đường tăng, matching tăng 1 và đạt giá trị tối đa mới.
- Nếu DFS(u) không tìm được đường tăng, không thể có đường tăng bắt đầu từ u. Những đỉnh trái đã xét trước đó cũng không thể có đường tăng, vì matching trước đó là maximum trên tập cũ.

Đỉnh mới u đang free nên không thể là **đỉnh bên trong** một đường xen kẽ bắt đầu từ một đỉnh trái free cũ: để là đỉnh trái bên trong, nó phải đi đến từ một cạnh matched, nhưng u chưa matched. Do đó thêm u không tạo đường tăng mới từ các đỉnh trái free cũ. Khi không có đường tăng nào, matching giữ nguyên và vẫn maximum theo Berge.

### 8.3. Sau khi xét hết đỉnh trái

Mọi đỉnh trái đã được đưa vào quá trình xét, nên matching có kích thước lớn nhất trong toàn graph hai phía.

**Lưu ý:** lý lẽ này phụ thuộc DFS(u) thực sự tìm được một đường tăng nếu có. Nếu dùng visited sai, chỉ thử hàng xóm đầu tiên hoặc không cho tái phân công, giả thiết ấy không còn đúng.

### 8.4. Không cần xóa matching cũ trước mỗi lượt

Mỗi lượt DFS bắt đầu từ matching đã được xây ở các lượt trước và **có thể thay thế một số cặp**, nhưng không làm mất tổng số cặp hiện tại khi lượt thành công. Chỉ mảng visited (hoặc dấu lượt) được reset; **ownerRight[] phải được giữ**.

---

## 9. Thiết kế dữ liệu trong Java

### 9.1. Danh sách kề từ trái sang phải

Ta dùng:

```java
List<List<Integer>> adjacency;
```

`adjacency.get(u)` là danh sách những đỉnh phải v có cạnh `L_u-R_v`. Không cần lưu chiều ngược riêng vì trong tìm đường tăng, cạnh matched từ Rv về Lu được suy ra qua `ownerRight[v]`.

### 9.2. Mảng ownerRight

```java
int[] ownerRight = new int[rightCount];
Arrays.fill(ownerRight, -1);
```

Nếu `ownerRight[v]=u` thì v đang được ghép với u.

Khi DFS tìm được đường tái phân công, ta gán lại `ownerRight[v]=u` trong quá trình đệ quy **quay ngược**, do đó cả chuỗi cặp mới được cập nhật nhất quán.

### 9.3. Mảng visited theo dấu lượt

Cách dễ hiểu là:

```java
boolean[] visitedRight = new boolean[rightCount];
```

và tạo mảng mới cho từng đỉnh trái gốc. Nhưng nếu R rất lớn, việc fill lại toàn bộ mảng có thể tốn thời gian dù đồ thị thưa.

Bản Java mẫu dùng **timestamp/stamp**:

```java
int[] seenStamp = new int[rightCount];

for (int left = 0; left < leftCount; left++) {
    int token = left + 1;

    if (augment(left, token, seenStamp, ownerRight)) {
        matched++;
    }
}
```

Một right v đã thăm trong lượt hiện tại khi:

```java
seenStamp[v] == token
```

Do mỗi lượt có token khác nhau, không cần xóa `seenStamp[]` sau lượt. Với `leftCount` là độ dài mảng Java kiểu int hợp lệ, `left+1` nằm trong miền int cho mọi chỉ số được duyệt.

### 9.4. Dừng ở đỉnh phải free

Phần lõi:

```java
if (ownerRight[right] == -1
        || augment(ownerRight[right], token,
                   seenStamp, ownerRight)) {
    ownerRight[right] = left;
    return true;
}
```

Nếu right free, gán ngay. Nếu right đang bị chiếm, DFS kiểm tra có cách dời người giữ right hay không. Điều kiện OR ngắn mạch của Java bảo đảm **chỉ gọi đệ quy khi right đã bị chiếm**.

### 9.5. Khôi phục phía trái sau cùng

Khi đã có `ownerRight[]` cuối, dựng `leftToRight[]`:

```java
int[] partnerLeft = new int[leftCount];
Arrays.fill(partnerLeft, -1);

for (int right = 0; right < rightCount; right++) {
    int left = ownerRight[right];

    if (left != -1) {
        partnerLeft[left] = right;
    }
}
```

Dựng ở **cuối** giúp tránh lỗi cập nhật nửa chừng mảng hai phía khi DFS thay chuỗi nhiều cặp. Mỗi left có tối đa một partner do bất biến matching của DFS.

---

## 10. Định lý Hall: khi nào ghép hết phía trái?

### 10.1. Phát biểu

Đồ thị hai phía `G=(L\cup R,E)` có một matching **phủ hết L** (mỗi đỉnh trái có một bạn ghép khác nhau) **khi và chỉ khi**:

\[
\boxed{
\forall S\subseteq L,\quad
|N(S)|\ge|S|.
}
\]

Ở đây `N(S)` là **tập tất cả đỉnh phải kề với ít nhất một đỉnh trong S**.

Đây là **định lý hôn nhân Hall** (*Hall's marriage theorem*).

### 10.2. Vì sao điều kiện cần?

Nếu `|S|=4` nhưng bốn đỉnh trái trong S chỉ có **ba** hàng xóm phải khác nhau, không thể ghép cả bốn đỉnh trái với bốn đỉnh phải phân biệt. Ít nhất một đỉnh trái phải unmatched.

Điều kiện Hall yêu cầu mọi tập S đều có đủ số lượng hàng xóm để ghép từng đỉnh với một right riêng.

### 10.3. Ví dụ vi phạm Hall

Ba đỉnh trái:

```text
L0 -> R0
L1 -> R0
L2 -> R1, R2
```

Xét `S=\{L0,L1\}`. Cả hai chỉ kề R0:

\[
|S|=2,\quad |N(S)|=1.
\]

Hall không thỏa. Không thể ghép hết ba đỉnh trái. Maximum matching có **2** cặp, chẳng hạn:

```text
L0 - R0
L2 - R1
L1   unmatched
```

### 10.4. Hall không đòi |L|=|R|

Điều kiện Hall đủ để **ghép hết bên trái**. Nếu `|L|<|R|`, có thể ghép hết L và vẫn còn right unmatched. Để có **perfect matching phủ cả hai phía**, cần `|L|=|R|` và điều kiện Hall tương ứng.

Với ví dụ chính `|L|=6,|R|=5`, chỉ từ cận `|M|\le5` đã biết không thể ghép hết L; Hall cũng bị vi phạm bởi `S=L` vì `|N(S)|=5<6`.

### 10.5. Hall và thuật toán Kuhn bổ sung nhau

Hall cung cấp **điều kiện tồn tại** matching phủ hết L. Kuhn **xây matching** và cho biết cardinality thực sự.

Không cần duyệt mọi tập con `S\subseteq L` để chạy Kuhn; cách đó có thể tốn `2^{|L|}`. Thuật toán đường tăng đã khai thác cấu trúc graph để tìm lời giải hiệu quả.

---

## 11. Chương trình Java 17+ hoàn chỉnh

Chương trình dùng DFS Kuhn với dấu lượt, sau đó mở rộng thêm một chứng chỉ **minimum vertex cover** bằng định lý König (giải thích ở mục 12). Điều này giúp kiểm tra không chỉ số cặp matching mà còn một đối tượng đối ngẫu có cùng kích thước.

Lưu tệp **`BipartiteAugmentingPathDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class BipartiteAugmentingPathDemo {

    public record Matching(
            int size,
            List<Integer> leftToRight,
            List<Integer> rightToLeft,
            List<Integer> leftCover,
            List<Integer> rightCover) {
    }

    public static final class BipartiteGraph {
        private final int leftCount;
        private final int rightCount;
        private final List<List<Integer>> adj;

        public BipartiteGraph(int leftCount, int rightCount) {
            if (leftCount < 0 || rightCount < 0) {
                throw new IllegalArgumentException(
                        "negative side size");
            }

            this.leftCount = leftCount;
            this.rightCount = rightCount;
            this.adj = new ArrayList<>(leftCount);

            for (int u = 0; u < leftCount; u++) {
                adj.add(new ArrayList<>());
            }
        }

        public void addEdge(int left, int right) {
            if (left < 0 || left >= leftCount
                    || right < 0 || right >= rightCount) {
                throw new IllegalArgumentException(
                        "invalid bipartite edge");
            }

            adj.get(left).add(right);
        }

        private boolean augment(
                int left,
                int token,
                int[] seenStamp,
                int[] ownerRight) {

            for (int right : adj.get(left)) {
                if (seenStamp[right] == token) {
                    continue;
                }

                seenStamp[right] = token;

                int previousLeft = ownerRight[right];

                if (previousLeft == -1
                        || augment(previousLeft, token,
                                   seenStamp, ownerRight)) {
                    ownerRight[right] = left;
                    return true;
                }
            }

            return false;
        }

        public Matching maximumMatching() {
            int[] ownerRight = new int[rightCount];
            Arrays.fill(ownerRight, -1);

            // Timestamp avoids clearing R visited flags
            // at the start of every new left-root search.
            int[] seenStamp = new int[rightCount];

            int matched = 0;

            for (int left = 0; left < leftCount; left++) {
                int token = left + 1;

                if (augment(
                        left, token, seenStamp, ownerRight)) {
                    matched++;
                }
            }

            int[] partnerLeft = new int[leftCount];
            Arrays.fill(partnerLeft, -1);

            for (int right = 0; right < rightCount; right++) {
                if (ownerRight[right] != -1) {
                    partnerLeft[ownerRight[right]] = right;
                }
            }

            // Alternating reachability from all unmatched
            // left vertices; used for Konig's min cover.
            boolean[] reachableLeft = new boolean[leftCount];
            boolean[] reachableRight =
                    new boolean[rightCount];

            ArrayDeque<Integer> queue = new ArrayDeque<>();

            for (int left = 0; left < leftCount; left++) {
                if (partnerLeft[left] == -1) {
                    reachableLeft[left] = true;
                    queue.addLast(left);
                }
            }

            while (!queue.isEmpty()) {
                int left = queue.removeFirst();

                for (int right : adj.get(left)) {
                    // Traverse unmatched edges left -> right.
                    if (partnerLeft[left] == right
                            || reachableRight[right]) {
                        continue;
                    }

                    reachableRight[right] = true;

                    // Traverse matched edges right -> left.
                    int owner = ownerRight[right];

                    if (owner != -1 && !reachableLeft[owner]) {
                        reachableLeft[owner] = true;
                        queue.addLast(owner);
                    }
                }
            }

            List<Integer> leftCover = new ArrayList<>();
            List<Integer> rightCover = new ArrayList<>();

            for (int left = 0; left < leftCount; left++) {
                if (!reachableLeft[left]) {
                    leftCover.add(left);
                }
            }

            for (int right = 0; right < rightCount; right++) {
                if (reachableRight[right]) {
                    rightCover.add(right);
                }
            }

            List<Integer> leftPartners =
                    new ArrayList<>(leftCount);
            List<Integer> rightPartners =
                    new ArrayList<>(rightCount);

            for (int left = 0; left < leftCount; left++) {
                leftPartners.add(partnerLeft[left]);
            }

            for (int right = 0; right < rightCount; right++) {
                rightPartners.add(ownerRight[right]);
            }

            return new Matching(
                    matched,
                    List.copyOf(leftPartners),
                    List.copyOf(rightPartners),
                    List.copyOf(leftCover),
                    List.copyOf(rightCover));
        }
    }

    private static String showPairs(Matching matching) {
        List<String> pairs = new ArrayList<>();

        for (int left = 0;
                left < matching.leftToRight().size();
                left++) {

            int right = matching.leftToRight().get(left);

            if (right != -1) {
                pairs.add("L" + left + "-R" + right);
            }
        }

        return pairs.toString();
    }

    public static void main(String[] args) {
        BipartiteGraph graph = new BipartiteGraph(6, 5);

        graph.addEdge(0, 0);
        graph.addEdge(0, 1);
        graph.addEdge(1, 0);
        graph.addEdge(2, 1);
        graph.addEdge(2, 2);
        graph.addEdge(3, 2);
        graph.addEdge(3, 3);
        graph.addEdge(4, 3);
        graph.addEdge(4, 4);
        graph.addEdge(5, 4);

        Matching result = graph.maximumMatching();

        System.out.println(
                "Maximum matching size: " + result.size());
        System.out.println(
                "Left partners: " + result.leftToRight());
        System.out.println(
                "Right partners: " + result.rightToLeft());
        System.out.println(
                "Matched pairs: " + showPairs(result));
        System.out.println(
                "Minimum cover L: " + result.leftCover());
        System.out.println(
                "Minimum cover R: " + result.rightCover());
        System.out.println(
                "Matching equals cover size: "
                        + (result.size()
                        == result.leftCover().size()
                        + result.rightCover().size()));

        BipartiteGraph hall = new BipartiteGraph(3, 3);
        hall.addEdge(0, 0);
        hall.addEdge(1, 0);
        hall.addEdge(2, 1);
        hall.addEdge(2, 2);

        Matching hallResult = hall.maximumMatching();
        System.out.println(
                "Hall example matching: " + hallResult.size());
        System.out.println(
                "Hall example cover L: "
                        + hallResult.leftCover());
        System.out.println(
                "Hall example cover R: "
                        + hallResult.rightCover());

        BipartiteGraph duplicate = new BipartiteGraph(1, 1);
        duplicate.addEdge(0, 0);
        duplicate.addEdge(0, 0);
        System.out.println(
                "Duplicate-edge matching: "
                        + duplicate.maximumMatching().size());

        BipartiteGraph empty = new BipartiteGraph(0, 0);
        System.out.println(
                "Empty graph matching: "
                        + empty.maximumMatching().size());

        boolean invalidRejected = false;
        try {
            new BipartiteGraph(2, 1).addEdge(1, 2);
        } catch (IllegalArgumentException ex) {
            invalidRejected = true;
        }

        System.out.println(
                "Invalid neighbor rejected: "
                        + invalidRejected);
    }
}
```

Biên dịch và chạy trên **JDK 17 trở lên**:

```bash
javac BipartiteAugmentingPathDemo.java
java BipartiteAugmentingPathDemo
```

**Đầu ra chuẩn chính xác:**

```text
Maximum matching size: 5
Left partners: [1, 0, 2, 3, 4, -1]
Right partners: [1, 0, 2, 3, 4]
Matched pairs: [L0-R1, L1-R0, L2-R2, L3-R3, L4-R4]
Minimum cover L: []
Minimum cover R: [0, 1, 2, 3, 4]
Matching equals cover size: true
Hall example matching: 2
Hall example cover L: [2]
Hall example cover R: [0]
Duplicate-edge matching: 1
Empty graph matching: 0
Invalid neighbor rejected: true
```

### 11.1. Vì sao đầu ra đúng?

Trong graph chính, có tối đa 5 cặp vì chỉ có 5 đỉnh phải. Chương trình tìm được đúng 5 cặp hợp lệ, nên kết quả chắc chắn tối ưu.

Mảng:

```text
Left partners: [1, 0, 2, 3, 4, -1]
```

có nghĩa:

- L0 ghép R1.
- L1 ghép R0.
- L2 ghép R2.
- L3 ghép R3.
- L4 ghép R4.
- L5 chưa ghép.

Mảng bên phải:

```text
Right partners: [1, 0, 2, 3, 4]
```

phù hợp hoàn toàn với mảng phía trái, không có đỉnh nào nhận hai đối tượng.

Ví dụ Hall chỉ ghép được 2 vì L0 và L1 cùng phụ thuộc R0. Graph có cạnh song song vẫn chỉ ghép được 1 cặp khi mỗi phía chỉ có một đỉnh. Graph rỗng cho matching 0. Input đỉnh phải ngoài phạm vi bị từ chối.

### 11.2. Vì sao dùng stamp thay vì reset boolean[]?

Mỗi lần thử một đỉnh trái gốc mới, cần một trạng thái visited riêng. Đánh dấu:

```java
seenStamp[right] = token;
```

và kiểm tra:

```java
seenStamp[right] == token
```

cho phép biết một right đã xuất hiện trong đúng lượt hiện tại mà không `Arrays.fill` mỗi lần. Với mảng right rất lớn nhưng graph rất thưa, điều này tránh chi phí reset mảng kích thước R ở mỗi lượt.

### 11.3. Vì sao không duy trì cả hai mảng partner trong DFS?

Trong quá trình đệ quy, một đỉnh phải có thể được đổi chủ trước khi lời gọi ngoài cùng hoàn thành. Để giảm nguy cơ cập nhật bất nhất, thuật toán chỉ cập nhật `ownerRight[]` trong DFS, rồi sau khi các lượt augment kết thúc mới dựng `leftToRight[]`.

Đó là một thiết kế đơn giản và dễ kiểm thử. Một phiên bản khác có thể cập nhật cả hai mảng ngay khi đảo đường nếu quản lý chính xác những cặp bị thay thế.

### 11.4. Vì sao List.copyOf?

`Matching` dùng `List<Integer>` thay vì trả mảng nội bộ; các danh sách được trả bằng `List.copyOf` để người gọi không thay đổi kết quả sau khi thuật toán kết thúc. Số nguyên `-1` được dùng làm sentinel cho đỉnh chưa matched.

Một API lớn hơn có thể bổ sung tên đối tượng, id nghề nghiệp và dữ liệu giải thích, nhưng thuật toán lõi chỉ cần chỉ số 0-based của hai phía.

### 11.5. Nguy cơ tràn ngăn xếp

`augment` dùng đệ quy; với mạng rất lớn tạo chuỗi tái phân công dài, độ sâu lời gọi có thể lớn và gây `StackOverflowError` trong Java.

Bản mẫu chọn đệ quy vì dễ đối chiếu với chứng minh đường tăng. Nếu n hàng trăm nghìn và graph dạng chuỗi dài, nên cân nhắc tìm đường tăng **lặp bằng stack tường minh** hoặc dùng thuật toán khác phù hợp, thay vì chỉ tăng stack JVM mà không đánh giá rủi ro.

---

## 12. Định lý König: từ maximum matching đến minimum vertex cover

Một **vertex cover** là tập đỉnh C sao cho **mọi cạnh** của graph có ít nhất một đầu thuộc C.

Đây không phải matching: matching chọn cạnh không trùng đỉnh, còn vertex cover chọn đỉnh để **phủ mọi cạnh**.

### 12.1. Cận dưới của vertex cover

Nếu matching có k cạnh, các cạnh ấy không chung đầu mút. Để phủ cả k cạnh, bất kỳ vertex cover nào cũng phải chọn **ít nhất một đỉnh từ mỗi cạnh**, nên cần ít nhất k đỉnh:

\[
\min|C|\ge |M|.
\]

### 12.2. Phát biểu König

Với **đồ thị hai phía**:

\[
\boxed{
\text{maximum matching cardinality}
=
\text{minimum vertex cover cardinality}.
}
\]

Điều này **không đúng nguyên dạng cho mọi đồ thị vô hướng tổng quát**. Cấu trúc hai phía là điều kiện quan trọng.

### 12.3. Dựng min cover bằng đường xen kẽ

Sau khi tìm **maximum matching M**:

1. Bắt đầu từ **tất cả đỉnh trái đang unmatched**.
2. Đi theo **cạnh chưa matched từ trái sang phải**.
3. Từ một đỉnh phải matched, đi theo **cạnh matched trở lại đỉnh trái chủ của nó**.
4. Duyệt tới khi không tới được đỉnh mới.

Gọi:

- `Z_L`: các đỉnh trái reachable theo những đường xen kẽ này.
- `Z_R`: các đỉnh phải reachable.

Khi đó tập:

\[
\boxed{
C=(L\setminus Z_L)\cup Z_R
}
\]

là một **minimum vertex cover**.

### 12.4. Vì sao C phủ mọi cạnh?

Xét một cạnh u–v với u∈L và v∈R.

Nếu u **không** thuộc `Z_L`, thì u thuộc `L\setminus Z_L` nên cạnh được phủ.

Nếu u thuộc `Z_L` mà cạnh u–v **chưa matched**, quy tắc duyệt từ trái sang phải buộc v thuộc `Z_R`, nên cạnh được phủ.

Nếu u thuộc `Z_L` và cạnh u–v **đang matched**, thì trừ trường hợp khởi đầu free (không thể có cạnh matched), u chỉ có thể đạt tới từ v qua cạnh matched; vì thế v cũng thuộc `Z_R`. Cạnh được phủ.

Do đó mọi cạnh đều có đầu thuộc C.

### 12.5. Vì sao kích thước C bằng matching?

Trong maximum matching, không có đường tăng nào từ một left free tới một right free. Vì vậy **mọi right thuộc `Z_R` đều matched**.

Mỗi cạnh matched góp đúng một đỉnh vào C:

- Nếu hai đầu matched reachable thì right thuộc `Z_R` và left thuộc `Z_L`: chọn right.
- Nếu hai đầu matched không reachable thì left thuộc `L\setminus Z_L`, right không thuộc `Z_R`: chọn left.

Không thể xảy ra một cạnh matched có đúng một đầu reachable theo quy tắc duyệt: các cạnh matched được đi ngược từ R sang L, còn right matched của left reachable cũng nằm trong tập reachable. Vì vậy có một song ánh giữa các cạnh matched và các đỉnh cover được chọn, suy ra:

\[
|C|=|M|.
\]

Kết hợp cận dưới `\min|C|\ge|M|`, ta có C minimum và M maximum.

### 12.6. Min cover trong ví dụ chính

Graph chính có **6 left** và **5 right**, matching tối đa 5 cặp, còn L5 unmatched.

Từ L5 ta đi R4 (matched L4), rồi từ L4 đi R3 (matched L3), rồi tiếp tục qua R2→L2, R1→L0, R0→L1. Kết quả:

\[
Z_L=\{L0,L1,L2,L3,L4,L5\},
\]

\[
Z_R=\{R0,R1,R2,R3,R4\}.
\]

Tập cover:

\[
C=(L\setminus Z_L)\cup Z_R
=\varnothing\cup R=R.
\]

Min cover có 5 đỉnh phải — đúng bằng kích thước maximum matching 5.

### 12.7. Min cover trong ví dụ Hall

Với:

```text
L0 -> R0
L1 -> R0
L2 -> R1, R2
```

Matching mẫu là L0–R0, L2–R1; L1 free.

Duyệt xen kẽ từ L1 tới R0 rồi qua cạnh matched tới L0:

```text
Z_L = {L0,L1}
Z_R = {R0}
```

Do đó:

\[
C=(L\setminus Z_L)\cup Z_R
=\{L2,R0\}.
\]

Cover này có **2 đỉnh**, phủ mọi cạnh, trùng kích thước maximum matching 2. Đó là nguồn gốc hai dòng:

```text
Hall example cover L: [2]
Hall example cover R: [0]
```

trong stdout của Java.

### 12.8. Lưu ý điều kiện “sau khi maximum”

Công thức dùng Z để trích xuất min vertex cover phải áp dụng trên **maximum matching**. Nếu matching chưa tối đa, có thể tồn tại đường tăng từ một left free tới một right free; tập Z và kết luận cardinality bằng matching có thể không cho chứng chỉ tối ưu.

---

## 13. Độ phức tạp của DFS Kuhn

Ký hiệu:

- `L=|L|` số đỉnh trái.
- `R=|R|` số đỉnh phải.
- `E=|E|` số cạnh giữa hai phía.

### 13.1. Chi phí một DFS tìm đường tăng

Trong **một lượt gốc**, mỗi right được đánh dấu visited tối đa một lần. Khi thử right đang bị chiếm, DFS đi tới chủ left của right đó. Vì mỗi right có một chủ tối đa và right được xét một lần, tổng số đỉnh/cạnh được duyệt bị chặn bởi việc quét các danh sách kề của những left có thể đạt tới.

Một cận thông dụng:

\[
O(E)
\]

cho một lần tìm đường tăng khi E>0 và mã chỉ duyệt những left reachable qua cạnh matched. Nếu graph rỗng, việc kiểm tra một left không có hàng xóm vẫn tốn O(1).

### 13.2. Tổng cho tất cả left

Thuật toán thử tối đa L lần, mỗi lần duyệt O(E+1), nên:

\[
\boxed{
T_{\mathrm{Kuhn}}=O(L(E+1)+R)
}
\]

khi tính cả việc khởi tạo mảng, và thường ghi gọn:

\[
\boxed{O(LE)}
\]

cho graph có cạnh và xét chi phí tìm kiếm là chính.

Một cách chặn đối xứng hơn khi tự chọn phía chạy DFS là `O(\min(L,R)\cdot E)` **nếu** thuật toán được cài để duyệt các đỉnh của phía nhỏ hơn và tổ chức danh sách kề theo phía ấy.

### 13.3. Nếu reset visited bằng Arrays.fill

Nếu mỗi lần gốc tạo một `boolean[R]` hoặc fill lại R ô, có thêm O(LR) chi phí reset, dù graph thưa.

Bản Java dùng **seenStamp** nên chỉ khởi tạo mảng R một lần, rồi mỗi lượt dùng token khác nhau, tránh phí O(LR) khi mảng right lớn và ít cạnh.

### 13.4. Bộ nhớ

- Danh sách kề: `O(L+E)` (tạo L list và lưu E chỉ số right).
- Mảng ownerRight, seenStamp, reachableRight: `O(R)`.
- Mảng partnerLeft, reachableLeft, queue: `O(L)`.
- Kết quả matching và vertex cover: `O(L+R)`.
- DFS đệ quy có độ sâu tới `O(\min(L,R))` trong trường hợp xấu nhất.

Vậy tổng bộ nhớ:

\[
\boxed{O(L+R+E)}.
\]

### 13.5. Khi nào Kuhn đủ nhanh?

Kuhn tương đối dễ viết, phù hợp:

- L và R vừa phải (vài trăm đến vài nghìn tùy E).
- Graph thưa.
- Bài cần **maximum cardinality matching**, không có trọng số/cost.
- Cần nhanh một cài đặt dễ chứng minh và debug.

Nếu L và R lớn và E nhiều, `O(LE)` có thể quá chậm.

### 13.6. Hopcroft–Karp

**Hopcroft–Karp** cũng dựa trên đường tăng, nhưng dùng **BFS phân lớp** và DFS tìm **nhiều đường tăng ngắn nhất theo từng pha**, giúp giảm số pha. Cận nổi tiếng:

\[
\boxed{O(E\sqrt{L+R})}
\]

đối với bài maximum cardinality matching trên graph hai phía.

Nó phức tạp hơn Kuhn, nhưng thường thích hợp cho graph lớn. Đừng nhầm Hopcroft–Karp với một phiên bản Kuhn chỉ đổi DFS thành BFS đơn thuần; điểm đặc trưng là **nhiều đường tăng ngắn nhất trong cùng pha**.

---

## 14. Ghép cặp hai phía và bài toán max flow

Có thể quy bài bipartite matching thành một mạng luồng:

1. Tạo nguồn s và đích t.
2. Với mỗi left u, thêm cạnh `s→u` dung lượng 1.
3. Với mỗi cạnh tương thích u–v, thêm cạnh có hướng `u→v` dung lượng 1.
4. Với mỗi right v, thêm cạnh `v→t` dung lượng 1.

Mọi đường s→u→v→t gửi tối đa 1 đơn vị. Vì các cạnh s→u và v→t đều có capacity 1, không left hay right nào được ghép nhiều hơn một lần.

### 14.1. Sự tương đương

Một matching M có k cạnh tạo ra một luồng nguyên giá trị k bằng cách gửi 1 qua mỗi đường s→u→v→t tương ứng.

Ngược lại, với các capacity nguyên và max-flow nguyên, những cạnh u→v có flow 1 xác định một matching hợp lệ, vì không left/right nào có hơn một đơn vị đi qua. Vì thế:

\[
\boxed{
\text{maximum bipartite matching size}
=
\text{maximum flow value trong mạng quy đổi}.
}
\]

### 14.2. Đường tăng Kuhn chính là đường dư

Trong residual network của bài quy đổi:

- Cạnh u→v **chưa matched** còn dung lượng dư 1.
- Một cạnh matched u→v có cạnh dư **ngược v→u** dung lượng 1, cho phép hủy lựa chọn đó.
- Đường tăng s→left free→...→right free→t là một đường dư từ s tới t.

Do đó thao tác đảo matched/unmatched trong Kuhn tương đương **augment 1 đơn vị trên đường dư**.

### 14.3. Khi nào dùng max flow thay Kuhn?

Nếu mỗi người có thể làm **nhiều nhiệm vụ**, hoặc mỗi nhiệm vụ cần nhiều người, capacity có thể lớn hơn 1. Khi ấy bài có thể là **b-matching** hoặc **max flow** với dung lượng từ nguồn/đến đích lớn hơn 1.

Nếu các cặp có **chi phí/lợi nhuận** và cần tối ưu tổng chi phí ngoài số cặp, có thể cần **min-cost max-flow**, Hungarian algorithm hoặc weighted bipartite matching tùy mô hình.

Kuhn chỉ tìm **số cặp lớn nhất**, không tự bảo đảm mỗi cặp ít tốn chi phí nhất hay tổng điểm lớn nhất.

---

## 15. Các trường hợp biên cần xử lý

### 15.1. Một phía rỗng

Nếu L=0 hoặc R=0, không có cặp hợp lệ. Maximum matching = 0. Với Java mẫu, `new BipartiteGraph(0,0)` trả `Matching.size()=0` và hai tập cover đều rỗng.

Nếu L>0,R=0, tất cả left unmatched, max matching vẫn là 0; chương trình có thể tạo L danh sách kề rỗng hợp lệ.

### 15.2. Đỉnh cô lập

Một left không kề right nào sẽ không bao giờ matched. Một right không có left kề có thể vắng mặt trong mọi `adj[u]`; nó không ảnh hưởng việc tìm đường tăng.

Không được “tự tạo cạnh” để ghép đỉnh cô lập nhằm đạt `min(L,R)`.

### 15.3. Hai left chỉ kề chung một right

Ví dụ L0→R0 và L1→R0, không thể ghép cả hai cùng lúc. Tìm đường tăng từ đỉnh trái thứ hai sẽ thất bại nếu đỉnh trái thứ nhất không có nơi khác để chuyển. Đây là tình huống thiếu láng giềng trong Hall.

### 15.4. Cạnh song song trùng cặp

Nếu input vô tình liệt kê `L0-R0` hai lần, số cặp tối đa **không tăng**, vì matching là tập cặp đối tượng, mỗi đỉnh vẫn chỉ được ghép một lần. DFS đánh dấu right đã thử, nên bản Java xử lý đúng dù danh sách kề có duplicate.

Một bước tiền xử lý deduplicate các adjacency có thể tiết kiệm thời gian, nhưng không bắt buộc để có kết quả đúng.

### 15.5. Thứ tự đầu vào thay đổi

Cùng một graph nhưng liệt kê hàng xóm theo thứ tự khác có thể cho matching cuối khác. Nếu đề chỉ yêu cầu **cardinality maximum** hoặc một matching bất kỳ có cardinality ấy, mọi kết quả hợp lệ đều được chấp nhận.

Nếu đề yêu cầu **matching nhỏ nhất theo từ điển** hay ưu tiên công việc đặc biệt, cần quy tắc bổ sung và có thể một thuật toán khác.

### 15.6. Các mảng 0-based và 1-based

Nếu đề đặt tên đỉnh `1..L` và `1..R`, phải chuyển về 0-based khi truy cập mảng. Không được lẫn id đỉnh trái 3 với đỉnh phải 3 như thể chúng là **cùng một đỉnh**; hai phía có namespace khác nhau.

### 15.7. Input không phân biệt hai phía

Nếu graph vô hướng được nhập với id chung `0..n-1` mà chưa biết phân hoạch, hãy **tô hai màu** để xác định hai phía hoặc phát hiện chu trình lẻ. Không chuyển tất cả cạnh tùy ý về “từ id nhỏ sang id lớn” rồi giả sử graph hai phía; chiều id không tạo phân hoạch hợp lệ.

### 15.8. Matching đã cho một phần

Nếu bài bắt đầu từ matching M đã tồn tại, phải kiểm tra M hợp lệ, sau đó có thể tìm những đường tăng tiếp để mở rộng. Chương trình mẫu bắt đầu từ matching **rỗng** và tính mới mỗi lần gọi.

Đừng nạp ownerRight tùy tiện với hai right cùng trỏ một left: đó không phải matching, các giả thiết DFS và proof không còn bảo đảm.

### 15.9. Một bên có dung lượng >1

Bài “mỗi nhân viên nhận tối đa hai công việc” không còn là matching 1–1 cơ bản. Có thể nhân bản đỉnh trong một số trường hợp hoặc dùng b-matching/max-flow, nhưng phải chứng minh việc nhân bản giữ đúng các ràng buộc nghiệp vụ.

### 15.10. Phân công có trọng số

Nếu cạnh mang số điểm, lương hoặc chi phí, Kuhn **không** tối ưu tổng điểm/chi phí. Tập matching maximum cardinality chỉ tối ưu **số lượng cặp**, không tối ưu theo trọng số.

Một bài có thể yêu cầu ưu tiên **ghép tối đa số cặp, rồi trong số đó tối đa hóa điểm**. Đây là mục tiêu từ điển hai tầng; cần cấu trúc tối ưu trọng số phù hợp.

### 15.11. Đệ quy sâu

Một chuỗi tái phân công dài hàng trăm nghìn bước có thể vượt thread stack Java. Nếu input cực lớn, nên cân nhắc DFS lặp hoặc Hopcroft–Karp với thiết kế ngăn xếp an toàn.

### 15.12. Tính lại sau khi sửa graph

Nếu thêm hoặc xóa cạnh, matching cũ có thể không còn tối ưu hoặc không còn hợp lệ. Bản mẫu tính lại từ đầu khi gọi `maximumMatching()`; không giả định kết quả trước vẫn còn đúng.

---

## 16. Kiểm thử bằng các bất biến

### 16.1. Bất biến của matching hợp lệ

Với kết quả cuối:

1. Mỗi cặp (u,v) **phải tồn tại** trong adjacency.
2. Không đỉnh trái nào được ghép với **hai** right.
3. Không đỉnh phải nào thuộc **hai** cặp.
4. Nếu `leftToRight[u]=v` thì phải có `rightToLeft[v]=u`.
5. Nếu `rightToLeft[v]=u` thì phải có `leftToRight[u]=v`.
6. Số giá trị không phải -1 của `leftToRight` phải bằng `size`.
7. Số giá trị không phải -1 của `rightToLeft` cũng bằng `size`.
8. `size≤min(L,R)`.
9. Không còn đường tăng trong graph đối với matching cuối cùng.

Điều kiện 1–8 chứng minh matching **hợp lệ**; điều kiện 9 (hoặc một chứng chỉ min cover bằng cardinality) mới chứng minh **tối ưu**.

### 16.2. Kiểm tra min vertex cover

Nếu trả kết quả từ công thức König:

- Mọi cạnh u–v phải được phủ bởi ít nhất một trong `leftCover`, `rightCover`.
- Không có chỉ số cover ngoài phạm vi.
- `leftCover.size()+rightCover.size()==matching.size()`.

Một matching hợp lệ kích thước k cộng với một vertex cover hợp lệ kích thước k là **hai chứng chỉ đối ngẫu** đủ để khẳng định cả matching maximum lẫn cover minimum trong graph hai phía.

### 16.3. Oracle vét cạn trên graph nhỏ

Với L,R≤7, có thể dùng backtracking thử mọi cách:

```text
BRUTE(u, usedRight, current):
    if u == L:
        best = max(best, current)
        return

    // Option 1: leave u unmatched.
    BRUTE(u+1, usedRight, current)

    // Option 2: match u to an unused neighbor.
    for each v in adjacency[u]:
        if not usedRight[v]:
            usedRight[v] = true
            BRUTE(u+1, usedRight, current+1)
            usedRight[v] = false
```

Vì oracle vét cạn **không dùng đường tăng**, nó độc lập về phương pháp và có thể giúp phát hiện lỗi tái phân công của Kuhn.

Tuy nhiên backtracking là **hàm mũ** trong trường hợp xấu, chỉ dùng để test graph nhỏ.

### 16.4. Các bộ test gợi ý

| Input | Kết quả kỳ vọng |
| --- | --- |
| L=0,R=0 | 0 cặp |
| L=4,R=0 | 0 cặp |
| L=1,R=1, có cạnh | 1 cặp |
| L=1,R=1, không cạnh | 0 cặp |
| L0→R0,R1; L1→R0 | 2 cặp, cần đường tăng |
| L0→R0; L1→R0 | 1 cặp, không thể ghép cả hai |
| L0→R0, R0 (duplicate) | 1 cặp |
| Đồ thị đầy đủ `K_{3,3}` | 3 cặp |
| Ví dụ chính L=6,R=5 | 5 cặp |
| Ví dụ Hall L=3,R=3 | 2 cặp |
| Right id ngoài phạm vi | Báo lỗi input |
| Left id âm | Báo lỗi input |
| Graph nhiều đỉnh cô lập | Không ép ghép đỉnh không kề |
| Thứ tự adjacency đảo | Cardinality không đổi |
| Graph sâu cần tái phân công dài | Kết quả đúng, cân nhắc stack |

### 16.5. Sinh test ngẫu nhiên nhỏ

Với mỗi L,R từ 0 tới 6:

1. Sinh ngẫu nhiên các cạnh giữa hai phía, có thể thêm duplicate.
2. Chạy Kuhn và oracle backtracking.
3. So **kích thước** matching.
4. Kiểm tra tính hợp lệ của từng cặp.
5. Dựng cover và kiểm tra mọi cạnh được phủ.
6. Xác nhận `|cover|=|matching|`.

Nếu matching và cover cùng hợp lệ có kích thước bằng nhau, đó là bằng chứng tối ưu rất mạnh cho mỗi test.

### 16.6. Kiểm tra hành vi qua từng augment

Trên graph nhỏ, sau mỗi DFS trả true:

- Matching size tăng đúng 1.
- Không left/right nào matched hai lần.
- Những cặp bị đổi đều thuộc một đường xen kẽ phù hợp.
- Không cần so ownerRight của các lần trung gian với một thuật toán khác; thứ tự đường tăng có thể khác.

Sau DFS false, matching **không đổi**. Nếu code trả false nhưng mảng ownerRight đã bị thay đổi, đó thường là lỗi cập nhật ngay trước khi kiểm tra liệu việc tái phân công cũ có thành công hay không.

---

## 17. Những lỗi thường gặp

1. **Nhầm maximal với maximum**, tưởng rằng không thể thêm trực tiếp một cạnh free–free nghĩa là đã tối ưu.
2. **Không cho tái phân công** một right đã matched, nên mất những đường tăng dài hơn 1 cạnh.
3. **Ghi đè ownerRight** khi right đang bị chiếm mà chưa tìm được đường dời chủ cũ, có thể làm mất cặp hoặc tạo trạng thái sai.
4. **Không reset visited cho mỗi đỉnh trái gốc mới**, khiến bỏ qua đỉnh phải có thể giúp augment ở lượt sau.
5. **Reset matching ownerRight ở mỗi lượt**, khiến chỉ giữ cặp của lượt cuối và không tích lũy kết quả.
6. **Không có visited trong DFS**, có thể lặp qua chuỗi tái phân công và gây đệ quy vòng hoặc lặp vô hạn.
7. **Đánh dấu visited khi trả về thay vì khi bắt đầu thử right**, khiến cùng right bị xét nhiều lần trong một lượt.
8. **Chỉ tìm một đường tăng duy nhất cho toàn bài**, không lặp cho các left khác.
9. **Cho rằng một đường xen kẽ bất kỳ luôn tăng size**, trong khi hai đầu phải free và số cạnh phải phù hợp.
10. **Sai chiều ý nghĩa ownerRight[v]**, dùng nó như id right cho đỉnh trái.
11. **Không phân biệt namespace hai phía**, tưởng L1 và R1 là cùng một đối tượng.
12. **Nhầm cardinality maximum với chi phí minimum**, dùng Kuhn cho bài weighted assignment.
13. **Không kiểm tra graph hai phía** nếu input là graph vô hướng tổng quát.
14. **Chấp nhận cạnh nối hai đỉnh cùng phía** trong mô hình input đang yêu cầu L–R.
15. **Quên xử lý một phía rỗng**, cố truy cập index 0 trên mảng length 0.
16. **Quên đỉnh cô lập**, tự thêm cạnh ảo để đạt min(L,R).
17. **Tưởng cạnh song song tăng số cặp**, dù matching vẫn dùng một đỉnh mỗi phía tối đa một lần.
18. **Đảo trạng thái cạnh trên đường tăng nhưng không cập nhật cả chuỗi**, khiến mảng hai phía mất nhất quán.
19. **Đặt visited toàn graph vĩnh viễn** như BFS đồ thị tĩnh, dù matching thay đổi qua mỗi lượt.
20. **Dùng visitedLeft và visitedRight không nhất quán**, làm bỏ sót đường tăng.
21. **Không lưu id bên phải hợp lệ trong adjacency**, gây ArrayIndexOutOfBoundsException ở DFS.
22. **Tin kết quả matching hợp lệ là tối ưu** mà không chứng minh không còn đường tăng.
23. **Áp dụng König cho graph không hai phía**, tạo cover với kết luận kích thước không được bảo đảm.
24. **Trích xuất min cover khi matching chưa maximum**, suy ra cover sai hoặc không tối ưu.
25. **Duyệt matched edge theo hướng L→R trong BFS cover** rồi lại duyệt nhầm unmatched edge theo R→L, phá cấu trúc đường xen kẽ.
26. **Giữ visitedRight từ lượt augment khi dựng cover**, thay vì tạo trạng thái reachable mới từ tất cả left free.
27. **Coi một matching có size=|L| là perfect bất kể |R|**, trong khi perfect phủ **mọi đỉnh cả hai phía** và cần |L|=|R|.
28. **Tưởng Hall chỉ cần kiểm tra từng đỉnh trái riêng lẻ**, trong khi điều kiện phải xét mọi tập con S.
29. **Suy rằng thiếu điều kiện Hall ở một tập S là bằng chứng graph không có bất kỳ cặp nào**, dù vẫn có matching một phần.
30. **Phân tích độ phức tạp DFS Kuhn là O(E) cho toàn bài**, bỏ qua tối đa L lượt.
31. **Bỏ qua O(LR) khởi tạo visited** khi fill/reset mảng R ở mỗi lần tìm trên graph rất thưa.
32. **Không xét giới hạn stack** khi augment đệ quy có chuỗi matched dài.
33. **Ép matching cuối phải giống một thứ tự cặp duy nhất** dù graph có nhiều nghiệm.
34. **Tái sử dụng mảng partnerLeft chưa cập nhật** trong đệ quy và ra quyết định dựa trên dữ liệu cũ.
35. **Tự chuyển graph sang cấu trúc có hướng từ trái sang phải nhưng quên thao tác matched R→L** cần thiết để tìm đường tăng.
36. **Lẫn bài b-matching capacity>1 với matching 1–1**, khiến kết quả không đáp ứng yêu cầu nghiệp vụ.

---

## 18. Bài tập tự kiểm tra

### Bài 1 — Định nghĩa matching

Cho hai phía `L=\{L0,L1,L2\}`, `R=\{R0,R1\}`. Tập `\{L0-R0,L1-R0\}` có phải matching không? Vì sao?

### Bài 2 — Maximal hay maximum?

Graph có L0→R0,R1 và L1→R0. Matching `\{L0-R0\}` là maximal hay maximum? Hãy nêu matching tốt hơn.

### Bài 3 — Đường tăng

Với matching `\{L0-R0\}`, liệt kê các đỉnh và trạng thái cạnh trên đường tăng bắt đầu từ L1 trong graph của Bài 2.

### Bài 4 — Đảo cạnh

Một đường tăng có 7 cạnh, gồm bao nhiêu cạnh matched và unmatched? Kích thước matching tăng bao nhiêu sau đảo?

### Bài 5 — Gán ownerRight

Nếu `ownerRight[3]=2` thì ý nghĩa là gì? Nếu `ownerRight[4]=-1` thì sao?

### Bài 6 — DFS trên right đã có chủ

Nếu right v đang do left x giữ, có được gán v cho left u ngay không? Hàm Kuhn phải thử điều gì trước?

### Bài 7 — Visited

Vì sao phải reset `visitedRight[]` cho mỗi đỉnh trái gốc mới? Khi dùng stamp, điều kiện một right đã visited là gì?

### Bài 8 — Mô phỏng hai lượt

Với `L0→R0,R1`, `L1→R0`, xét L0 trước L1. Viết ownerRight sau khi xử lý cả hai.

### Bài 9 — Ví dụ sáu trái, năm phải

Với danh sách ở mục 5, maximum matching có bao nhiêu cặp? Đỉnh trái nào unmatched theo thứ tự DFS Java?

### Bài 10 — Cận kích thước

Nếu `|L|=8` và `|R|=5`, maximum matching có thể lớn hơn 5 không? Điều kiện nào khiến cận 5 đạt được?

### Bài 11 — Định lý Berge

Phát biểu đầy đủ điều kiện cần và đủ để một matching là maximum. Vì sao chỉ là maximal chưa đủ?

### Bài 12 — Hiệu đối xứng

Vì sao nếu matching `M^*` lớn hơn M thì `M\triangle M^*` bắt buộc chứa một đường tăng đối với M?

### Bài 13 — Hall

Graph có `L0→R0`, `L1→R0` và `L2→R1,R2`. Chọn S nào vi phạm Hall và maximum matching có thể đạt mấy cặp?

### Bài 14 — Hall khi hai phía khác kích thước

Nếu `|L|=3,|R|=5` và Hall thỏa đối với mọi S⊆L, kết luận ghép hết phía nào? Có nhất thiết ghép hết 5 right không?

### Bài 15 — König

Phát biểu mối quan hệ giữa kích thước maximum matching và minimum vertex cover trong graph hai phía.

### Bài 16 — Dựng min cover

Sau khi có maximum matching, định nghĩa `Z_L,Z_R` bằng những đường xen kẽ từ các left free. Công thức xây min vertex cover là gì?

### Bài 17 — Min cover ví dụ chính

Với 6 left và 5 right ở mục 5, min cover có thể là tập nào? Kích thước bao nhiêu?

### Bài 18 — Min cover ví dụ Hall

Với matching L0–R0, L2–R1 trên ví dụ Hall, tính các tập reachable và min cover.

### Bài 19 — Độ phức tạp

Giải thích tại sao DFS Kuhn có cận thường dùng `O(LE)` và bộ nhớ `O(L+R+E)`. Nếu mỗi lượt fill lại R ô visited thì phát sinh thêm chi phí gì?

### Bài 20 — Hopcroft–Karp

Hopcroft–Karp khác Kuhn ở điểm chính nào? Nêu cận tổng quát của Hopcroft–Karp.

### Bài 21 — Quy về max flow

Hãy mô tả cách tạo nguồn s, đích t và các cạnh dung lượng 1 để bài maximum bipartite matching thành bài max flow.

### Bài 22 — Cạnh song song

Nếu `L0-R0` xuất hiện hai lần trong danh sách cạnh, matching có thể dùng cả hai để tăng cardinality thêm 2 không?

### Bài 23 — Vertex cover và optimality

Nếu bạn có matching hợp lệ gồm 6 cặp và vertex cover hợp lệ gồm 6 đỉnh trên cùng graph hai phía, có thể kết luận gì về hai kết quả?

### Bài 24 — Graph có chu trình lẻ

Nếu graph gốc là tam giác và đề không chỉ rõ hai phía, có thể áp dụng Kuhn như mô tả bài này không? Cần giải pháp gì?

### Bài 25 — Phân công có chi phí

Mỗi nhân viên làm tối đa một công việc, nhưng cặp i,j có chi phí riêng và đề yêu cầu **số cặp tối đa, sau đó chi phí thấp nhất**. Kuhn thuần có giải đủ không?

### Bài 26 — Kiểm thử bằng oracle

Với L,R≤6, hãy xây oracle vét cạn maximum matching độc lập và dùng nó so với Kuhn như thế nào?

### Đáp án gợi ý

1. Không. Hai cạnh cùng sử dụng R0, vi phạm ràng buộc một đỉnh xuất hiện tối đa trong một cạnh matched.
2. Matching `\{L0-R0\}` là **maximal** nhưng không maximum; `\{L0-R1,L1-R0\}` có 2 cặp.
3. `L1→R0→L0→R1`; các cạnh lần lượt unmatched, matched, unmatched. Hai đầu L1 và R1 đều free.
4. Có 4 cạnh unmatched và 3 cạnh matched, sau đảo số cặp tăng đúng 1.
5. R3 đang ghép với L2. R4 chưa ghép.
6. Không được ghi đè mù. Phải thử DFS tái phân công left x sang một right khác trước; nếu thành công mới gán v cho u.
7. Matching có thể thay đổi giữa các lượt; right cần được xét lại cho gốc mới. Với stamp, `seenStamp[v]==token` nghĩa v đã visited trong lượt token.
8. Cuối cùng `ownerRight=[1,0]`: R0 ghép L1, R1 ghép L0.
9. Có 5 cặp; L5 unmatched theo thứ tự đã nêu.
10. Không, tối đa 5. Đạt được nếu có một matching phủ toàn bộ 5 right; không phải cứ có 8 left là đạt.
11. Berge: M maximum khi và chỉ khi không tồn tại đường tăng. Maximal chỉ cấm thêm cạnh free–free trực tiếp, vẫn có thể tồn tại đường tăng dài hơn.
12. Hiệu đối xứng tách thành đường/chu trình xen kẽ; vì `|M^*|>|M|`, ít nhất một đường có nhiều cạnh `M^*` hơn M, tạo đường tăng đối với M.
13. `S=\{L0,L1\}`, `N(S)=\{R0\}`, nên 1<2. Maximum matching có kích thước 2.
14. Ghép hết 3 left; không thể buộc ghép cả 5 right chỉ bằng 3 cặp.
15. Định lý König: kích thước maximum matching bằng kích thước minimum vertex cover trong graph hai phía.
16. `C=(L\setminus Z_L)\cup Z_R`, trong đó từ left free đi theo unmatched edge L→R và matched edge R→L.
17. Có thể lấy tất cả 5 đỉnh phải; mọi cạnh đều nối tới R và min cover size=5 vì matching đã có 5 cặp.
18. `Z_L=\{L0,L1\}`, `Z_R=\{R0\}`. Cover `\{L2,R0\}`, size=2.
19. Tối đa L lượt; mỗi DFS xét O(E) cạnh trong trường hợp xấu nhất, tổng O(LE) khi E>0; bộ nhớ adjacency+mảng O(L+R+E). Reset boolean R ô mỗi lượt thêm O(LR).
20. Hopcroft–Karp dùng BFS tạo lớp và nhiều đường tăng ngắn nhất theo pha; thời gian `O(E\sqrt{L+R})`.
21. Thêm s→u cho mọi left, u→v cho mọi cạnh tương thích, v→t cho mọi right; tất cả có capacity 1. Max flow nguyên tương ứng cardinality maximum.
22. Không. Cùng một left và một right chỉ xuất hiện tối đa một lần trong matching, nên duplicate không tăng số cặp.
23. Cả matching và vertex cover đều tối ưu. Mọi cover phải có ít nhất size matching, mọi matching không thể lớn hơn size cover; hai cận gặp nhau ở 6.
24. Không vì tam giác không hai phía. Cần thuật toán matching tổng quát như Edmonds' blossom, hoặc kiểm tra bipartite và từ chối đầu vào nếu bài bắt buộc hai phía.
25. Không. Kuhn tối ưu số cặp, không tối ưu chi phí giữa các maximum matching. Cần weighted assignment/min-cost max-flow hoặc mô hình tương đương.
26. Duyệt từng left: có thể bỏ unmatched hoặc ghép với một right kề chưa dùng; thử mọi lựa chọn, lấy số cặp lớn nhất. So cardinality, tính hợp lệ mảng cặp, và min vertex cover với Kuhn trên graph nhỏ ngẫu nhiên.

---

## Ghi nhớ

**Maximum bipartite matching** chọn nhiều cạnh nhất sao cho **mỗi đỉnh hai phía thuộc tối đa một cặp**. Cách tham lam chỉ lấy cạnh trống có thể dừng ở matching **maximal nhưng chưa maximum**. **Đường tăng** bắt đầu ở một left free, đi xen kẽ cạnh **unmatched → matched → unmatched ...** và kết thúc ở right free. **Đảo cạnh** trên đường tăng luôn làm số cặp tăng đúng **1**.

Thuật toán **Kuhn DFS** lưu `ownerRight[v]` là left đang ghép với right v; nếu v bị chiếm, thử **tái phân công chủ cũ** trước khi nhận v cho left mới. Mỗi lượt gốc phải có **visited riêng**; có thể dùng `seenStamp[]` để tránh xóa mảng nhiều lần. Sau khi xử lý mọi left, matching là maximum theo định lý **Berge**. Cận thường dùng `O(LE)` thời gian và `O(L+R+E)` bộ nhớ. **Hall** đặc tả điều kiện ghép hết phía trái, còn **König** cho chứng chỉ đối ngẫu **maximum matching size = minimum vertex cover size**. Với mạng lớn, cân nhắc **Hopcroft–Karp**; với capacity hoặc chi phí khác nhau, cần mô hình luồng hay phân công trọng số phù hợp.

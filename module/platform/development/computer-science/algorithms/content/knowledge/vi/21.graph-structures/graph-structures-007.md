# Giá trị low-link trong xác định điểm khớp và cạnh cầu

## 1. Hai loại phần tử quan trọng của cấu trúc đồ thị

Trong **đồ thị vô hướng**, có những đỉnh và cạnh đóng vai trò kết nối đặc biệt. Khi loại chúng khỏi đồ thị, các thành phần có thể bị tách rời:

- **Điểm khớp (articulation point, cut vertex)** là một **đỉnh** mà khi xóa đỉnh đó cùng tất cả cạnh kề, **số thành phần liên thông tăng**.
- **Cạnh cầu (bridge, cut edge)** là một **cạnh cụ thể** mà khi xóa riêng cạnh ấy, **số thành phần liên thông tăng**.

Ví dụ một đường thẳng:

~~~text
0 -- 1 -- 2 -- 3
~~~

Đỉnh 1 và 2 là điểm khớp: xóa đỉnh 1 chia phần còn lại thành {0} và {2,3}; tương tự với đỉnh 2. Cả ba cạnh đều là cầu: xóa bất kỳ cạnh nào sẽ tách đường thành hai thành phần.

Ngược lại, trên chu trình:

~~~text
0 -- 1
|    |
3 -- 2
~~~

Không đỉnh nào là điểm khớp và không cạnh nào là cầu. Khi xóa một cạnh của chu trình vẫn còn đường đi vòng thay thế; khi xóa một đỉnh, ba đỉnh còn lại vẫn kết nối qua một đường.

**Giá trị low-link** kết hợp với thời điểm duyệt DFS cho phép tìm **toàn bộ điểm khớp và cạnh cầu chỉ trong O(V+E)**, thay vì phải xóa từng đỉnh/cạnh rồi kiểm tra liên thông lại nhiều lần.

Trong bài này:
- V là số đỉnh, E là số **cạnh vô hướng có ID riêng**.
- Đỉnh đánh số từ **0 tới V−1**.
- Đồ thị có thể **không liên thông**.
- Có thể tồn tại **cạnh song song** giữa hai đỉnh và **self-loop** (cạnh nối một đỉnh với chính nó).
- Ta tìm điểm khớp/cạnh cầu theo **định nghĩa liên thông của đồ thị vô hướng**, không áp dụng trực tiếp công thức này cho đồ thị có hướng.

## 2. Vì sao DFS giúp nhận ra vị trí dễ đứt kết nối?

**Duyệt theo chiều sâu (depth-first search, DFS)** chọn một đỉnh gốc, đi sâu theo những đỉnh chưa thăm rồi quay lui. Các lần phát hiện đỉnh tạo một **cây DFS** trong từng thành phần liên thông; nếu đồ thị không liên thông, tổng các cây tạo thành **rừng DFS**.

Hai dạng cạnh có vai trò chính:
1. **Cạnh cây (tree edge)**: lần đầu đưa đỉnh v chưa thăm vào DFS từ u; u là cha của v.
2. **Cạnh ngược (back edge)**: cạnh từ một đỉnh trong quá trình DFS nối về một **tổ tiên đã phát hiện trước** trong cây DFS.

Với đồ thị vô hướng, khi xét theo các đỉnh DFS và bỏ đúng cạnh cây đi về cha, những cạnh còn lại tới đỉnh đã thăm có thể được xử lý bằng thời gian phát hiện của đỉnh đó. Trong đồ thị vô hướng, DFS không có cạnh chéo giữa hai nhánh hoàn toàn riêng biệt theo cách phân loại chuẩn; cạnh nối tới một đỉnh đã thăm sẽ nằm trong quan hệ tổ tiên–hậu duệ (self-loop là một trường hợp đặc biệt không ảnh hưởng cận).

Một cạnh ngược từ **cây con của v** tới một tổ tiên của u có nghĩa: ngay cả khi đường cây từ u xuống v bị xóa, cây con v vẫn có **đường thay thế** để quay về phần phía trên u.

Nếu cây con v **không có bất kỳ đường nối thay thế** nào đi lên u hay tổ tiên, cạnh cây (u,v) sẽ là **cầu**.

Nếu cây con v **không thể lên một tổ tiên nằm thật sự phía trên u**, khi xóa đỉnh u thì cây con v bị tách khỏi phía chứa cha của u, vì vậy u có thể là **điểm khớp**.

Để diễn đạt các câu hỏi này trong O(1) sau khi DFS một nhánh, ta dùng **tin** và **low**.

## 3. Hai giá trị tin[u] và low[u]

### 3.1. Thời điểm phát hiện tin[u]

Mỗi khi DFS lần đầu tới một đỉnh u, tăng bộ đếm thời gian và lưu:

\[
tin[u]=\text{thời điểm u được phát hiện trong DFS}.
\]

Có thể bắt đầu đếm từ 0. Với một lần duyệt đầy đủ rừng DFS, các giá trị tin khác nhau cho các đỉnh khác nhau.

**tin không phải khoảng cách ngắn nhất.** Nó chỉ phản ánh **thứ tự DFS**; thay thứ tự các cạnh trong danh sách kề có thể làm giá trị tin thay đổi, nhưng tập điểm khớp/cạnh cầu không thay đổi.

### 3.2. Định nghĩa low[u]

Giá trị:

\[
low[u]=\text{tin nhỏ nhất của đỉnh có thể tới từ u}
\]

khi đường đi được phép:
1. Đi xuống **0 hoặc nhiều cạnh cây DFS** trong cây con gốc u;
2. Rồi sử dụng **tối đa một cạnh ngược** từ một đỉnh trong cây con đó tới tổ tiên (hoặc chính đỉnh được phát hiện) của nó.

Nói đơn giản: **cây con của u có thể “leo ngược” về thời điểm DFS sớm nhất nào mà không cần đi theo cạnh cây nối u với cha của nó?**

Bản thân u luôn là một điểm có thể đạt từ u bằng đường đi rỗng, nên ban đầu:

\[
low[u]=tin[u].
\]

Khi duyệt DFS, low[u] được hạ xuống nếu phát hiện đường ngược tới một tổ tiên sớm hơn, hoặc nếu một cây con có thể trở về tổ tiên sớm hơn.

### 3.3. Công thức cập nhật

Khi vừa vào u:

\[
tin[u]=low[u]=timer,\qquad timer\leftarrow timer+1.
\]

Xét mỗi cạnh vô hướng có ID e từ u tới v:

- Nếu e chính là **cạnh cây đã đưa DFS từ cha xuống u**, bỏ qua đúng cạnh e ở chiều đi ngược; đây không phải một đường thay thế.
- Nếu v **đã được thăm** qua một cạnh khác, cập nhật:

\[
\boxed{low[u]=\min(low[u],tin[v]).}
\]

- Nếu v **chưa được thăm**, (u,v) là cạnh cây. DFS(v) xong, cập nhật:

\[
\boxed{low[u]=\min(low[u],low[v]).}
\]

**Phải phân biệt hai dòng:**
- Với **đỉnh đã thăm** qua cạnh không phải cạnh cha, dùng **tin[v]**, không dùng low[v] tùy tiện.
- Với **đỉnh con mới** vừa DFS xong, dùng **low[v]** để truyền khả năng quay lên của cả cây con về cho u.

Không làm low[u] nhỏ đi bằng cách đi qua **chính cạnh cây tới cha rồi quay lại**: điều đó sẽ khiến mọi cạnh cây tưởng như đều có đường thay thế và làm mất các cầu.

### 3.4. Bất biến của low

Sau khi DFS(u) kết thúc, low[u] là giá trị nhỏ nhất trong:
- tin[u];
- tin của những đỉnh đã thăm nối với u hoặc những đỉnh trong cây con u bằng cạnh ngược thích hợp;
- low của tất cả cây con DFS trực tiếp của u.

Bất biến này cho phép phát biểu điều kiện điểm khớp/cầu bằng **một phép so sánh** giữa low[v] và tin[u] tại mỗi cạnh cây (u,v).

## 4. Cạnh cầu: điều kiện low[v] > tin[u]

Xét cạnh cây từ u xuống **con DFS v**. Cạnh (u,v) là **cầu** khi và chỉ khi:

\[
\boxed{low[v]>tin[u].}
\]

**Vì sao dùng dấu lớn hơn nghiêm ngặt?**

- Nếu low[v]>tin[u], không có cạnh ngược nào từ cây con v quay tới **u hoặc một tổ tiên của u**. Đường kết nối duy nhất giữa cây con v và phần còn lại của thành phần liên thông là cạnh cây (u,v). Xóa cạnh này làm hai phần bị tách → **cầu**.
- Nếu low[v]≤tin[u], cây con v có đường ngược về **u hoặc một tổ tiên của u** bằng một cạnh khác. Tồn tại đường thay thế tránh cạnh cây (u,v), nên xóa cạnh ấy **không** tăng số thành phần → **không phải cầu**.

**Ví dụ low[v]==tin[u]:** cạnh cây 6--7 có một **cạnh song song thứ hai** nối chính 6 với 7. Khi DFS đi từ 6 sang 7 theo cạnh thứ nhất, cạnh song song còn lại tạo đường quay về 6. Khi đó low[7]=tin[6]; điều kiện **>** là sai, nên cả hai cạnh 6--7 đều **không phải cầu**.

Nếu dùng **>=** để kiểm tra cầu, cạnh có đường thay thế quay tới chính u sẽ bị báo nhầm là cầu.

**Chú ý:** phép so sánh cầu chỉ áp dụng cho **cạnh cây DFS (u,v)**, sau khi dfs(v) đã tính xong low[v]. Một cạnh ngược bản thân nó không thể là cầu vì nó tham gia chu trình cùng đường cây nối hai đầu.

## 5. Điểm khớp: điều kiện khác giữa đỉnh gốc và đỉnh thường

### 5.1. Đỉnh không phải gốc DFS

Với một đỉnh u **có cha trong cây DFS**, u là điểm khớp khi tồn tại **ít nhất một con DFS v** thỏa:

\[
\boxed{low[v]\ge tin[u].}
\]

Lý do: sau khi bỏ đỉnh u, cây con v không có đường ngược tới **bất kỳ tổ tiên nào thật sự ở phía trên u**. Nó có thể quay tới u khi low[v]==tin[u], nhưng **u đã bị xóa**, nên đường ấy không cứu được kết nối.

Khi u không phải gốc, phía chứa cha của u vẫn có đỉnh bên ngoài cây con v. Vì vậy cây con v bị tách khỏi phía chứa cha nếu low[v]≥tin[u], làm tăng số thành phần liên thông.

Ngược lại, nếu **mọi con** đều có low[v]<tin[u], mỗi cây con đều có đường thay thế tới một tổ tiên của u. Sau khi bỏ u, các cây con vẫn nối được tới phía cha và vì thế không tách thành phần này.

**Phân biệt so sánh:**

| Kết luận | Điều kiện trên cạnh cây (u,v) |
|---|---|
| Cạnh (u,v) là cầu | **low[v] > tin[u]** |
| u là điểm khớp nếu u không phải gốc | **low[v] >= tin[u]** |

Chỉ khác đúng một dấu bằng, nhưng ý nghĩa khác: **xóa cạnh** vẫn giữ u nên đường ngược về u là đủ; **xóa đỉnh u** thì đường ngược về chính u không còn giá trị.

### 5.2. Đỉnh gốc DFS

Gốc r **không có cha và không có tổ tiên nằm phía trên r**, nên điều kiện low[child]≥tin[r] không thể dùng để đánh dấu điểm khớp theo cùng cách. Đối với gốc, điều kiện đúng là:

\[
\boxed{r\ \text{là điểm khớp}\iff
\text{r có ít nhất hai con trực tiếp trong cây DFS}.}
\]

Vì sao? Trong đồ thị vô hướng, khi DFS đã đi hết một nhánh con của gốc, không tồn tại cạnh từ cây con ấy sang một cây con khác chưa được thăm. Nếu có cạnh đó, DFS của nhánh thứ nhất đã phát hiện nhánh thứ hai, và nhánh thứ hai **không còn là con trực tiếp** của gốc.

Vì vậy, hai cây con trực tiếp khác nhau của gốc chỉ nối được qua gốc. Xóa gốc sẽ tách chúng.

Nếu gốc có **0 con** (đỉnh cô lập) hoặc **1 con** trong cây DFS, xóa gốc **không làm tăng** số thành phần liên thông. Ví dụ gốc của một chu trình có thể chỉ có một con DFS dù bậc của nó là hai hoặc nhiều hơn.

**Đếm con DFS, không đếm số hàng xóm/cạnh kề.** Đỉnh gốc có ba cạnh kề chưa chắc có ba con DFS, vì các hàng xóm có thể được phát hiện bên trong cùng một nhánh con.

### 5.3. Điểm khớp không đồng nghĩa có cạnh cầu kề

Một đỉnh có thể là điểm khớp ngay cả khi **không có cạnh cầu kề**. Ví dụ hai chu trình chia sẻ duy nhất một đỉnh u: xóa u tách hai phần, nhưng mọi cạnh của cả hai chu trình vẫn nằm trên một chu trình nên không là cầu.

Ngược lại, một đầu mút của một cạnh cầu có thể **không** là điểm khớp, như đồ thị chỉ có hai đỉnh 0--1: cạnh đó là cầu, nhưng xóa một đầu còn một đỉnh, không làm **tăng** số thành phần.

Vì vậy không được suy ra tập điểm khớp chỉ bằng cách lấy mọi đầu mút của các cầu, hay ngược lại.

## 6. Đồ thị không liên thông và định nghĩa số thành phần

Nếu đồ thị ban đầu có C thành phần liên thông:
- Xóa một đỉnh u, rồi tính số thành phần mới C'. u là điểm khớp **khi C'>C**.
- Xóa một cạnh e, rồi tính C'. e là cầu **khi C'>C**.

Đây là định nghĩa toàn cục, không yêu cầu đồ thị ban đầu phải liên thông.

**Cách chạy low-link:** duyệt tất cả đỉnh:

~~~text
for u = 0 .. V-1:
    if tin[u] == -1:
        dfs(u, parentEdgeId=-1)
~~~

Mỗi thành phần có gốc riêng, nên cần áp dụng quy tắc **số con DFS của gốc** cho từng gốc của rừng DFS.

**Đỉnh cô lập không phải điểm khớp.** Nếu xóa một đỉnh cô lập, số thành phần của đồ thị thực ra giảm một, không tăng.

**Đồ thị rỗng:** không có điểm khớp hay cạnh cầu. **Đồ thị một đỉnh:** không có điểm khớp. **Self-loop:** xóa nó không làm tăng số thành phần; không phải cầu.

## 7. Điểm rất dễ sai: đồ thị có cạnh song song

### 7.1. Vì sao chỉ bỏ qua “đỉnh cha” không đủ?

Nhiều ví dụ đơn giản dùng:

~~~java
if (v == parent) {
    continue;
}
~~~

Đoạn này **chỉ an toàn khi đồ thị đơn** không có cạnh song song. Nếu giữa u và cha p có **hai cạnh phân biệt**, khi u quay về p:
- Cạnh thứ nhất là **cạnh cây** đã dùng để đến u, cần bỏ qua.
- Cạnh thứ hai là **cạnh khác thật**, tạo một đường thay thế; nó phải được xử lý như một back edge để hạ low[u] về tin[p].

Nếu bỏ **mọi cạnh có v==parent**, ta bỏ luôn cạnh thứ hai, khiến low[u] quá cao và báo sai rằng cạnh p--u là cầu.

### 7.2. Dùng ID cạnh thay vì chỉ ID đỉnh cha

Đối với mỗi cạnh vô hướng đầu vào, gán một **edgeId duy nhất**. Trong danh sách kề, lưu hai cung:
- (u→v, edgeId)
- (v→u, **cùng edgeId**)

Khi DFS từ p qua cạnh e để vào u, truyền **parentEdgeId=e**. Tại u, bỏ qua **chính edgeId đó**, không bỏ tất cả các cung đi tới p:

~~~java
if (edge.id() == parentEdgeId) {
    continue;       // Bỏ đúng cạnh cây đi về cha
}
~~~

Một cạnh song song có edgeId khác, nên vẫn được xem xét và hạ low đúng. Đây là cách cài đặt **đúng cho đồ thị vô hướng có đa cạnh**.

**Ví dụ hai đỉnh có hai cạnh:**

~~~text
0 == 1     (hai cạnh song song 0--1)
~~~

DFS(0) đi theo cạnh ID=0 tới 1. Tại 1, bỏ cung có ID=0, nhưng vẫn thấy cung ID=1 tới đỉnh 0 đã thăm, nên low[1]=tin[0]. Vì low[1] không lớn hơn tin[0], cạnh ID=0 không là cầu. Cạnh ID=1 cũng không là cầu. Bỏ một cạnh vẫn còn cạnh kia nối hai đỉnh.

### 7.3. Self-loop và cạnh trùng trong input

Một self-loop u--u có hai đầu giống nhau. Trong cài đặt vô hướng ở đây, nó được đưa vào danh sách kề hai lần với cùng ID; khi DFS gặp nó, u đã được thăm và phép min(low[u],tin[u]) không đổi. Self-loop không thể là cầu.

**Cạnh trùng trong input không nhất thiết là lỗi dữ liệu:** có thể chúng biểu diễn hai **cạnh song song độc lập**. Nếu bài toán quy định đồ thị đơn, có thể khử trùng cạnh trước; nếu cho phép multigraph, khử trùng làm thay đổi bài toán và có thể tạo cầu giả. Phải xác định đúng hợp đồng của đồ thị.

## 8. Ví dụ tổng hợp: chu trình, cầu, đa cạnh, self-loop, đỉnh cô lập

Xét đồ thị vô hướng có **10 đỉnh** (0..9) và các cạnh được nhập theo thứ tự:

~~~text
(0,1), (1,2), (2,0),       // Chu trình 0-1-2-0
(1,3),                     // Cầu nối cụm trái và cụm giữa
(3,4), (4,5), (5,3),       // Chu trình 3-4-5-3
(3,6),                     // Cầu tới cụm phải
(6,7), (6,7),              // HAI cạnh song song
(7,8),                     // Cầu tới đỉnh lá 8
(5,5)                      // Self-loop tại 5
// Đỉnh 9 cô lập
~~~

Các đỉnh 0,1,2 tạo một chu trình; 3,4,5 tạo chu trình thứ hai. Hai cụm nối qua cạnh 1--3. Bên phải là 3--6, hai cạnh song song 6==7 rồi cạnh 7--8. Đỉnh 9 không kề ai.

Dùng DFS bắt đầu từ đỉnh nhỏ nhất chưa thăm, với danh sách kề giữ **thứ tự cạnh nhập**; thời điểm tăng từ 0. Cây DFS biểu diễn khái quát:

~~~text
0
└── 1
    ├── 2      (có cạnh ngược 2--0)
    └── 3
        ├── 4
        │   └── 5   (có cạnh ngược 5--3, self-loop 5--5)
        └── 6
            └── 7   (có cạnh song song thứ hai 7--6)
                └── 8

9 (gốc của thành phần cô lập)
~~~

### 8.1. Bảng tin và low

Với **đúng thứ tự duyệt trên**, kết quả:

| Đỉnh u | tin[u] | low[u] | Lý do low |
|---:|---:|---:|---|
| 0 | 0 | 0 | Gốc của thành phần lớn |
| 1 | 1 | 0 | Cây con 2 quay được về 0 |
| 2 | 2 | 0 | Back edge 2--0 |
| 3 | 3 | 3 | Không có đường từ cụm 3..8 về 0/1 |
| 4 | 4 | 3 | Cây con 5 quay về 3 |
| 5 | 5 | 3 | Back edge 5--3 |
| 6 | 6 | 6 | Cây con 7 có cạnh song song quay tới 6 |
| 7 | 7 | 6 | Cạnh song song thứ hai 7--6 |
| 8 | 8 | 8 | Lá, không có đường ngược |
| 9 | 9 | 9 | Gốc cô lập |

Tóm tắt:

~~~text
tin = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
low = [0, 0, 0, 3, 3, 3, 6, 6, 8, 9]
~~~

**Lưu ý:** nếu thay thứ tự danh sách kề, các con số tin và có thể cả low theo số thứ tự DFS sẽ thay đổi. Tập điểm khớp và cầu vẫn phải như nhau.

### 8.2. Kiểm tra các cạnh cầu

Xét các cạnh cây tiêu biểu:
- **1--3:** low[3]=3 > tin[1]=1 → **cầu**.
- **3--6:** low[6]=6 > tin[3]=3 → **cầu**.
- **7--8:** low[8]=8 > tin[7]=7 → **cầu**.
- **6--7:** low[7]=6 == tin[6]=6 → **không phải cầu**, vì có một cạnh song song thay thế.
- **0--1:** low[1]=0 == tin[0]=0 → không là cầu do chu trình 0-1-2-0.
- **3--4:** low[4]=3 == tin[3]=3 → không là cầu do chu trình 3-4-5-3.

Tập **cạnh cầu** (ghi theo hai đầu tăng dần):

~~~text
[1-3, 3-6, 7-8]
~~~

### 8.3. Kiểm tra các điểm khớp

- **u=1:** có con v=3 với low[3]=3≥tin[1]=1 → **điểm khớp**. Xóa 1 tách nhóm 0,2 khỏi nhóm 3..8.
- **u=3:** có con v=6 với low[6]=6≥tin[3]=3; ngoài ra cây con 4 cũng chỉ quay về 3 → **điểm khớp**.
- **u=6:** con v=7 có low[7]=6==tin[6]=6. **6 vẫn là điểm khớp** dù cạnh 6--7 **không là cầu**. Xóa 6 cắt hẳn nhóm {7,8} khỏi nhóm {0..5}.
- **u=7:** con v=8 có low[8]=8≥tin[7]=7 → **điểm khớp**.
- **u=0:** gốc DFS chỉ có **một** con trực tiếp (đỉnh 1), nên không là điểm khớp, mặc dù 0 có hai hàng xóm 1 và 2.
- **u=9:** gốc cô lập, không có con DFS nên không là điểm khớp.

Tập **điểm khớp**:

~~~text
[1, 3, 6, 7]
~~~

**Bài học từ ví dụ:** so sánh low[7]==tin[6] đánh dấu **điểm khớp ở 6** nhưng **không đánh dấu cầu ở cạnh 6--7**. Đây là ví dụ ngắn gọn nhất để nhớ dấu **>=** và **>**.

## 9. Java 17+ hoàn chỉnh, hỗ trợ đa cạnh và nhiều thành phần

Chương trình dưới đây:
- Đọc đầu vào bằng mảng cạnh, gán **ID bằng vị trí cạnh trong mảng**.
- Xây danh sách kề vô hướng với hai cung chung edgeId.
- Chạy DFS từ mọi đỉnh chưa thăm để xử lý **đồ thị không liên thông**.
- Tính tin[u] và low[u], đánh dấu điểm khớp và ghi cầu.
- Áp dụng **quy tắc riêng cho gốc DFS**.
- Trả tập điểm khớp theo thứ tự tăng và các cầu được chuẩn hóa hai đầu tăng rồi **sắp xếp** để đầu ra ổn định.
- Minh họa trường hợp có chu trình, ngôi sao, cạnh song song, cạnh đơn, self-loop, đồ thị rỗng.

Lưu thành **LowLinkArticulationBridgeDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public final class LowLinkArticulationBridgeDemo {
    private LowLinkArticulationBridgeDemo() {
    }

    record Edge(int to, int id) {
    }

    record Bridge(int a, int b) {
    }

    public record Result(
            List<Integer> articulationPoints,
            List<String> bridges,
            int[] tin,
            int[] low) {
    }

    private static final class Solver {
        private final List<List<Edge>> graph;
        private final int[] tin;
        private final int[] low;
        private final boolean[] isCut;
        private final List<Bridge> bridgeList = new ArrayList<>();
        private int timer = 0;

        Solver(int n, int[][] edges) {
            if (n < 0 || edges == null) {
                throw new IllegalArgumentException("Invalid graph");
            }

            graph = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                graph.add(new ArrayList<>());
            }

            for (int id = 0; id < edges.length; id++) {
                int[] edge = edges[id];
                if (edge == null || edge.length != 2) {
                    throw new IllegalArgumentException("Invalid edge");
                }

                int u = edge[0];
                int v = edge[1];
                if (u < 0 || u >= n || v < 0 || v >= n) {
                    throw new IllegalArgumentException(
                            "Vertex out of range");
                }

                // Hai cung của cùng một cạnh vô hướng cùng ID.
                graph.get(u).add(new Edge(v, id));
                graph.get(v).add(new Edge(u, id));
            }

            tin = new int[n];
            low = new int[n];
            isCut = new boolean[n];
            Arrays.fill(tin, -1);
        }

        private void dfs(int u, int parentEdgeId) {
            tin[u] = low[u] = timer++;
            int childCount = 0;

            for (Edge edge : graph.get(u)) {
                int v = edge.to();

                // Bỏ duy nhất cạnh cây tới cha, KHÔNG bỏ
                // mọi cạnh song song có cùng đỉnh cha.
                if (edge.id() == parentEdgeId) {
                    continue;
                }

                if (tin[v] != -1) {
                    // Cạnh tới đỉnh đã thấy: dùng tin[v].
                    low[u] = Math.min(low[u], tin[v]);
                } else {
                    // Cạnh cây: DFS xuống một con mới.
                    childCount++;
                    dfs(v, edge.id());

                    low[u] = Math.min(low[u], low[v]);

                    // Quy tắc điểm khớp cho u không phải gốc.
                    if (parentEdgeId != -1
                            && low[v] >= tin[u]) {
                        isCut[u] = true;
                    }

                    // Quy tắc cạnh cầu: dấu > NGHIÊM NGẶT.
                    if (low[v] > tin[u]) {
                        bridgeList.add(new Bridge(
                                Math.min(u, v),
                                Math.max(u, v)));
                    }
                }
            }

            // Gốc DFS: chỉ khớp khi có hơn một con DFS.
            if (parentEdgeId == -1 && childCount > 1) {
                isCut[u] = true;
            }
        }

        Result run() {
            for (int u = 0; u < graph.size(); u++) {
                if (tin[u] == -1) {
                    dfs(u, -1);
                }
            }

            List<Integer> points = new ArrayList<>();
            for (int u = 0; u < isCut.length; u++) {
                if (isCut[u]) {
                    points.add(u);
                }
            }

            bridgeList.sort(
                    Comparator.comparingInt(Bridge::a)
                            .thenComparingInt(Bridge::b));

            List<String> bridges = new ArrayList<>();
            for (Bridge bridge : bridgeList) {
                bridges.add(bridge.a() + "-" + bridge.b());
            }

            return new Result(
                    List.copyOf(points),
                    List.copyOf(bridges),
                    tin.clone(),
                    low.clone());
        }
    }

    public static Result analyze(int vertexCount, int[][] edges) {
        return new Solver(vertexCount, edges).run();
    }

    private static void show(String label, Result result) {
        System.out.println(label
                + ": articulation=" + result.articulationPoints()
                + ", bridges=" + result.bridges());
    }

    public static void main(String[] args) {
        int[][] mainEdges = {
                {0, 1}, {1, 2}, {2, 0},
                {1, 3},
                {3, 4}, {4, 5}, {5, 3},
                {3, 6},
                {6, 7}, {6, 7},
                {7, 8},
                {5, 5}
        };

        Result main = analyze(10, mainEdges);
        System.out.println("Main articulation: "
                + main.articulationPoints());
        System.out.println("Main bridges: " + main.bridges());
        System.out.println("Main tin: "
                + Arrays.toString(main.tin()));
        System.out.println("Main low: "
                + Arrays.toString(main.low()));

        show("Star", analyze(4, new int[][] {
                {0, 1}, {0, 2}, {0, 3}
        }));

        show("Cycle", analyze(4, new int[][] {
                {0, 1}, {1, 2}, {2, 3}, {3, 0}
        }));

        show("Parallel edges", analyze(2, new int[][] {
                {0, 1}, {0, 1}
        }));

        show("Single edge", analyze(2, new int[][] {
                {0, 1}
        }));

        show("Only self-loop", analyze(1, new int[][] {
                {0, 0}
        }));

        show("Empty graph", analyze(0, new int[][] {}));
    }
}
~~~

### 9.1. Biên dịch và chạy

Sử dụng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 LowLinkArticulationBridgeDemo.java
java LowLinkArticulationBridgeDemo
~~~

**Stdout dự kiến chính xác với thứ tự cạnh trong mã:**

~~~text
Main articulation: [1, 3, 6, 7]
Main bridges: [1-3, 3-6, 7-8]
Main tin: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
Main low: [0, 0, 0, 3, 3, 3, 6, 6, 8, 9]
Star: articulation=[0], bridges=[0-1, 0-2, 0-3]
Cycle: articulation=[], bridges=[]
Parallel edges: articulation=[], bridges=[]
Single edge: articulation=[], bridges=[0-1]
Only self-loop: articulation=[], bridges=[]
Empty graph: articulation=[], bridges=[]
~~~

### 9.2. Giải thích từng trường hợp in ra

**Main:** có hai chu trình giúp bảo vệ các cạnh bên trong, ba cầu [1-3,3-6,7-8], bốn điểm khớp [1,3,6,7]; hai cạnh 6--7 song song nên không là cầu; đỉnh 9 cô lập.

**Star:** các cạnh 0--1, 0--2, 0--3 tạo ba nhánh trực tiếp từ gốc 0. Xóa 0 làm ba lá rời nhau; 0 là điểm khớp. Mỗi cạnh đều là cầu.

**Cycle:** bốn cạnh khép thành chu trình nên xóa một cạnh hoặc một đỉnh vẫn không tách phần còn lại thành nhiều thành phần; không có cầu/khớp.

**Parallel edges:** hai cạnh độc lập cùng nối 0 với 1. Xóa một cạnh vẫn có cạnh còn lại, nên không có cầu; không có điểm khớp.

**Single edge:** cạnh 0--1 là cầu, nhưng xóa một trong hai đỉnh chỉ còn một đỉnh và số thành phần không tăng, nên không có điểm khớp.

**Only self-loop:** cạnh 0--0 không nối hai đỉnh khác nhau; xóa nó không ảnh hưởng số thành phần. Một đỉnh đơn lẻ cũng không là điểm khớp.

**Empty graph:** không có đỉnh hay cạnh, nên cả hai tập rỗng.

### 9.3. Những lựa chọn kỹ thuật trong Java

- **ID cạnh độc lập** là phần quan trọng nhất để xử lý cạnh song song đúng. Hai cung của cùng cạnh vô hướng có chung ID; hai cạnh song song có **ID khác nhau**.
- Đặt tin[u]=low[u]=timer++ khi vừa khám phá u, với sentinel tin=-1 cho đỉnh chưa thăm. Không dùng low=-1 làm dấu chưa thăm.
- Dùng **tin[v]** cho cạnh gặp đỉnh đã thăm; dùng **low[v]** sau khi đi sâu nhánh con DFS.
- Chỉ đánh dấu điểm khớp cho **đỉnh không phải gốc** trong vòng cập nhật từ con. Sau khi duyệt hết các con, mới áp dụng điều kiện gốc **childCount>1**.
- Các cầu được chuẩn hóa với Math.min/Math.max hai đầu rồi sắp xếp, để chiều đi DFS không ảnh hưởng cách in.
- Không thay đổi mảng cạnh đầu vào. Bảng kết quả sao chép tin/low bằng clone(); tuy nhiên **mảng nằm trong record vẫn có thể bị sửa qua tham chiếu getter** nếu người gọi cố ý sửa. Nếu API sản xuất cần bất biến sâu, nên trả bản sao phòng vệ mỗi lần truy cập.
- Hàm từ chối n âm, mảng cạnh null, cạnh sai độ dài hoặc ID đỉnh ngoài [0,n). Cạnh song song và self-loop **được phép**.
- DFS bằng đệ quy có thể dùng stack sâu O(V). Với đồ thị rất sâu (đường thẳng dài), Java có thể bị StackOverflowError; khi cần chạy trên V lớn, nên chuyển sang **DFS lặp có stack khung trạng thái** và duy trì chính xác thời điểm cập nhật low sau khi xử lý con.

## 10. Chứng minh tính đúng của thuật toán low-link

### 10.1. Tính đúng của low sau DFS(u)

Xét cây DFS từ u. Khi vừa vào u, chỉ biết đường đi rỗng, nên low[u]=tin[u].

Với mỗi cạnh không phải cạnh cây tới cha:
- Nếu nối tới một đỉnh đã phát hiện, tin[v] là một ứng viên thời điểm tổ tiên đạt được bằng một cạnh ngược thích hợp. Cập nhật min với tin[v] không bỏ qua một đường ngược ngắn hơn.
- Nếu nối tới đỉnh chưa phát hiện v, DFS(v) duyệt trọn cây con v trước khi trả. Theo giả thuyết quy nạp, low[v] chứa thời điểm sớm nhất mà cây con v có thể quay tới. Kết hợp đường cây u→v với đường ấy cho một cách đi hợp lệ từ cây con u, nên cập nhật min với low[v].

Không còn cạnh nào thuộc danh sách kề của u hay cây con u chưa xét sau khi dfs(u) kết thúc. Vì vậy low[u] là thời điểm sớm nhất đạt được theo định nghĩa. Lập luận này áp dụng cho mỗi cây trong rừng DFS và vẫn đúng khi có cạnh song song vì chỉ bỏ qua **chính cạnh cây tới cha**.

### 10.2. Tính đúng của phát hiện cầu

Xét cạnh cây e=(u,v). Nếu low[v]>tin[u], mọi đường từ cây con v ra ngoài bằng cạnh khác sẽ đòi một cạnh ngược tới u hoặc tổ tiên của u, kéo low[v] xuống không quá tin[u]; không có đường như thế, nên e là kết nối duy nhất và xóa e tách thành phần.

Ngược lại, nếu low[v]≤tin[u], có đường đi từ cây con v qua một cạnh khác về u hoặc tổ tiên, kết hợp với đường cây tạo đường thay thế tránh e. Xóa e không ngắt kết nối giữa hai phía. Mọi cạnh không phải cạnh cây nằm trên một chu trình với các cạnh cây, vì vậy không thể là cầu.

Do đó điều kiện **low[v]>tin[u]** phát hiện đúng và đủ mọi cầu.

### 10.3. Tính đúng của điểm khớp không phải gốc

Với u có cha, nếu có một con v thỏa low[v]≥tin[u], cây con v không có đường tới tổ tiên của u **mà tránh u**. Sau khi xóa u, cây con v bị tách khỏi ít nhất phần chứa cha của u, nên số thành phần tăng và u là điểm khớp.

Nếu mọi con v đều có low[v]<tin[u], mỗi cây con có đường thay thế lên một tổ tiên của u. Khi xóa u, các cây con vẫn kết nối với phần tổ tiên qua những đường thay thế này; không có phần nào bị cô lập bởi việc xóa u. Vậy u không là điểm khớp.

### 10.4. Tính đúng của điểm khớp gốc

Gốc r không có phía chứa cha, nên không dùng điều kiện của đỉnh thường. Nếu gốc có từ hai con DFS, các cây con này không có cạnh nối với nhau trong đồ thị vô hướng mà bỏ qua r; nếu có, DFS của con đầu tiên đã tới con kia. Xóa r khiến chúng nằm ở các thành phần khác nhau.

Nếu gốc có không quá một con DFS, xóa r không thể tách thành phần ban đầu thành hai phần còn đỉnh. Rõ ràng một gốc cô lập cũng không phải điểm khớp. Vì vậy **số con DFS trực tiếp >1** là điều kiện đúng.

### 10.5. Không bỏ sót thành phần liên thông

Vòng ngoài chạy DFS từ mọi đỉnh có tin=-1; mỗi lần như vậy xử lý hết một thành phần liên thông. Vì vậy mọi đỉnh và cạnh của đồ thị đều được xét. Các điều kiện cầu/khớp chỉ liên quan đến kết nối trong thành phần của chính cạnh/đỉnh, và việc tăng số thành phần sau khi xóa được phản ánh đúng trên toàn đồ thị.

**Kết luận:** thuật toán trả đúng tập điểm khớp và cạnh cầu của đồ thị vô hướng theo định nghĩa tăng số thành phần liên thông.

## 11. Phân tích độ phức tạp

Với V đỉnh và E cạnh vô hướng:
- Tạo danh sách kề: O(V+E) thời gian và bộ nhớ. Mỗi cạnh vô hướng tạo **hai cung** trong danh sách kề; với self-loop, hai cung đều ở cùng danh sách.
- Mỗi đỉnh được DFS **một lần**, vì tin[u] được gán khi phát hiện lần đầu.
- Mỗi cung của danh sách kề được duyệt tối đa một lần ở một lời gọi DFS tương ứng. Tổng số cung là 2E.
- Mỗi phép cập nhật tin/low, so sánh điểm khớp và cầu là O(1).

Vì vậy phần **xác định cấu trúc** mất:

\[
\boxed{O(V+E)\ \text{thời gian},\quad O(V+E)\ \text{bộ nhớ tổng}.}
\]

Riêng bộ nhớ bổ sung cho tin, low, isCut, timer và stack đệ quy là O(V). Danh sách điểm khớp chứa tối đa V đỉnh, cầu tối đa E cạnh.

**Chi tiết về phiên bản Java:** mã **sắp xếp danh sách các cầu trước khi in**. Nếu có B cầu, bước sắp xếp thêm O(B log B) thời gian. Do đó toàn bộ hàm Java như viết có chi phí:

\[
O(V+E+B\log B),
\]

trong đó B≤E. Đây là chi phí **định dạng đầu ra có thứ tự**, không phải chi phí cốt lõi của Tarjan low-link. Nếu không cần danh sách cầu được sắp thứ tự, có thể giữ thứ tự tìm thấy để duy trì O(V+E) cho toàn bộ phần phát hiện và thu thập.

Bộ nhớ DFS đệ quy tệ nhất O(V) khi cây DFS là đường dài. Trên đồ thị lớn, giới hạn stack có thể quan trọng hơn bộ nhớ lưu mảng.

## 12. Kiểm tra chậm bằng xóa từng đỉnh/cạnh: bộ tham chiếu đáng tin

Khi tự viết low-link, cách xác minh độc lập hữu ích nhất là **brute force số thành phần liên thông** cho đầu vào nhỏ.

Đầu tiên, tính:

\[
C_0=\text{số thành phần liên thông của đồ thị gốc}.
\]

Với mỗi đỉnh u:
1. Tạm bỏ u và tất cả cạnh có đầu mút là u.
2. Dùng BFS/DFS thường để đếm số thành phần của những đỉnh còn lại, gọi là C_u.
3. Nếu C_u>C_0, u là điểm khớp.

Với mỗi **cạnh theo ID e**:
1. Tạm bỏ **chính cạnh ID e** (không bỏ các cạnh song song khác có cùng đầu mút).
2. Đếm thành phần C_e.
3. Nếu C_e>C_0, e là cầu.

Giả mã:

~~~text
base = countComponents(G)

for vertex u:
    if countComponents(G without vertex u) > base:
        articulation.add(u)

for edgeId e:
    if countComponents(G without edgeId e) > base:
        bridges.add(e)
~~~

Trong đồ thị có đa cạnh, phải xóa **theo ID cạnh**, không phải xóa toàn bộ cặp đầu mút. Nếu xóa cả hai cạnh 6--7 cùng lúc, ta sẽ làm kết nối đứt rồi kết luận sai mỗi cạnh riêng lẻ là cầu.

Cách brute force chạy nhiều BFS/DFS nên có thời gian khoảng **O((V+E)(V+E))** trong cách cài đặt đơn giản xây/duyệt đồ thị lại mỗi lần; không phù hợp dữ liệu lớn nhưng rất tốt để **kiểm thử**.

### Đối chiếu các bộ mẫu

| Bộ đồ thị | Điểm khớp | Cạnh cầu |
|---|---|---|
| Đồ thị chính V=10 | [1,3,6,7] | [1-3,3-6,7-8] |
| Hình sao 0--{1,2,3} | [0] | [0-1,0-2,0-3] |
| Chu trình 0--1--2--3--0 | [] | [] |
| Hai cạnh song song 0==1 | [] | [] |
| Một cạnh đơn 0--1 | [] | [0-1] |
| Một đỉnh với self-loop | [] | [] |
| Đồ thị rỗng | [] | [] |

Kết quả low-link ở mục 9 khớp kết quả kiểm tra xóa đỉnh/cạnh trên tất cả các trường hợp này.

### Tự kiểm thử ngẫu nhiên trên n nhỏ

Với V≤7 chẳng hạn, sinh ngẫu nhiên các cạnh, có thể gồm:
- Nhiều thành phần liên thông.
- Self-loop và cạnh song song.
- Cây, chu trình, đồ thị gần đầy đủ.

Chạy low-link và brute force trên từng đồ thị, sau đó so **tập đỉnh** và **ID cạnh** được báo (hoặc hai đầu cầu đã chuẩn hóa, khi biết chắc không có nhiều cầu trùng đầu mút). Kiểm tra thêm:
- Mỗi cầu xuất ra có thật trong input.
- Mỗi điểm khớp nằm trong [0,V).
- Thay thứ tự cạnh nhập **không thay đổi tập điểm khớp/cầu**, dù tin và low có thể thay đổi.

Bộ tham chiếu giúp phát hiện lỗi dấu > / >=, cách xử lý gốc và lỗi bỏ qua cạnh song song mà không cần đoán từ một vài trace.

## 13. Những sai lầm thường gặp

1. **Đồng nhất tin[u] và low[u].** tin là thời điểm phát hiện; low còn tổng hợp các đường quay ngược từ cả cây con.
2. **Tính low[u] bằng min tin của mọi đỉnh kề một cách tùy tiện.** Phải phân biệt cạnh cây, cạnh đã thăm và bỏ đúng cạnh cây tới cha.
3. **Dùng low[v] thay tin[v] khi gặp v đã thăm.** Công thức chuẩn trên cạnh ngược dùng **tin[v]**, còn low[v] truyền lên sau DFS của một con mới.
4. **Không cập nhật low[u] sau khi DFS(v).** Mất thông tin về back edge từ các hậu duệ, có thể báo cầu giả.
5. **Bỏ qua toàn bộ cạnh tới đỉnh cha bằng v==parent trong multigraph.** Mất cạnh song song tạo đường thay thế, báo cầu sai.
6. **Dùng dấu >= để phát hiện cầu.** Khi low[v]==tin[u] vẫn có đường thay thế quay về u, nên cạnh không là cầu.
7. **Dùng dấu > thay vì >= cho điểm khớp thường.** Bỏ sót trường hợp low[v]==tin[u] nhưng xóa u vẫn tách cây con.
8. **Áp dụng công thức điểm khớp thường cho gốc.** Gốc một con DFS có thể bị đánh dấu sai.
9. **Đếm bậc của gốc thay vì số con trực tiếp của cây DFS.** Gốc trong chu trình có nhiều hàng xóm nhưng chỉ một con DFS.
10. **Chỉ chạy DFS từ đỉnh 0.** Bỏ sót thành phần khác và các cầu/khớp nằm ngoài thành phần của 0.
11. **Coi đỉnh cô lập là điểm khớp.** Xóa đỉnh cô lập làm số thành phần giảm, không tăng.
12. **Coi mọi đầu mút của cầu đều là điểm khớp.** Một cạnh đơn có cầu nhưng hai đầu không phải điểm khớp theo định nghĩa.
13. **Coi mọi cạnh kề điểm khớp đều là cầu.** Hai chu trình gặp nhau ở một đỉnh có điểm khớp nhưng không có cầu bên trong chu trình.
14. **Dùng DFS low-link này cho đồ thị có hướng.** Khái niệm strong articulation/strong bridge hoặc SCC yêu cầu thuật toán/định nghĩa khác.
15. **Trộn low-link của điểm khớp/cầu với low-link trong Tarjan SCC.** SCC đồ thị có hướng cần điều kiện và stack thành phần riêng; cùng tên low không có nghĩa cùng công thức.
16. **Quên rằng cạnh song song là các cạnh độc lập.** Xóa một cạnh không được vô tình xóa những cạnh trùng đầu mút còn lại.
17. **Đếm self-loop là cầu.** Self-loop không bao giờ giúp nối hai đỉnh khác nhau.
18. **Không xác định rõ thứ tự kề khi so tin/low với stdout.** Thay thứ tự xét cạnh làm thời điểm DFS thay đổi.
19. **Lưu kết quả vào biến toàn cục rồi gọi lại mà không reset.** tin/low/cầu từ đồ thị cũ sẽ trộn với dữ liệu mới.
20. **Dùng dấu chưa thăm sai.** Mặc định int[] bằng 0; nếu timer bắt đầu 0 mà lại kiểm tra tin==0 để biết chưa thăm, sẽ không phân biệt được đỉnh đầu tiên.
21. **Đọc các phần tử của mảng kết quả như bất biến sâu.** record Java không tự khóa nội dung của int[].
22. **Không tính chi phí sắp xếp đầu ra.** Phần phát hiện O(V+E), nhưng sort B cầu mất O(B log B).
23. **Bỏ qua giới hạn ngăn xếp đệ quy.** Đường đi dài có thể gây StackOverflowError trong Java.
24. **Nhầm điểm khớp với đỉnh có nhiều cạnh kề.** Bậc lớn không chứng minh việc xóa đỉnh làm tăng số thành phần.

## 14. Tình huống áp dụng và mở rộng

**Phân tích độ tin cậy của mạng:** đỉnh cầu nối thiết bị hoặc cạnh cầu nối đường truyền có thể là điểm hỏng đơn lẻ làm mạng mất kết nối. Điểm khớp tương ứng thiết bị trọng yếu; cạnh cầu tương ứng liên kết trọng yếu.

**Bản đồ/đường giao thông:** nếu mô hình vô hướng không trọng số, cầu là đoạn đường mà bỏ nó làm hai nhóm khu vực không còn đường thay thế; điểm khớp là giao lộ mà xóa nó làm mạng tách.

**Thiết kế hạ tầng dự phòng:** muốn loại bỏ cầu, cần tạo đường thay thế cho những liên kết hiện chỉ nằm trên một đường độc đạo. Nhưng việc một đồ thị **không có cầu** chưa đảm bảo không có điểm khớp: hai chu trình có thể chỉ gặp nhau ở một đỉnh.

**Phân rã 2-edge-connected:** nếu bỏ tất cả cầu, các thành phần còn lại là các khối không bị chia cắt chỉ bằng một cạnh. Có thể co các khối thành đỉnh để tạo cấu trúc dạng cây cầu ở mỗi thành phần liên thông ban đầu. Đây là ứng dụng tiếp theo của danh sách cầu.

**Phân rã khối hai đỉnh liên thông:** các điểm khớp có thể dùng để xây **block-cut tree** biểu diễn quan hệ giữa khối hai đỉnh liên thông và điểm khớp. Muốn liệt kê các khối phải bổ sung cơ chế lưu cạnh/stack thành phần; chỉ biết mảng tin, low và cờ điểm khớp **chưa tự trả danh sách tất cả khối**.

**Đồ thị có hướng:** một đỉnh/cạnh mà xóa đi làm tăng số thành phần liên thông mạnh có định nghĩa khác. Không chuyển trực tiếp điều kiện \(\mathrm{low}[v]>\mathrm{tin}[u]\) sang directed graph.

## 15. Bài tập tự kiểm tra

**Câu 1.** tin[u] và low[u] lần lượt đo điều gì?

**Đáp án:** tin[u] là thời điểm DFS lần đầu phát hiện u. low[u] là thời điểm sớm nhất mà cây con u có thể vươn tới bằng các cạnh cây đi xuống rồi tối đa một cạnh ngược thích hợp, không dùng cạnh cây nối u với cha để làm đường thay thế.

**Câu 2.** Điều kiện để cạnh cây (u,v) là cầu?

**Đáp án:** **low[v]>tin[u]**, dấu lớn hơn nghiêm ngặt. Khi bằng nhau còn có đường thay thế quay về u, nên cạnh không là cầu.

**Câu 3.** Điều kiện để đỉnh u không phải gốc là điểm khớp?

**Đáp án:** Tồn tại con DFS v sao cho **low[v]>=tin[u]**. Khi xóa u, cây con v không thể tới tổ tiên thật sự của u mà tránh u.

**Câu 4.** Điều kiện cho gốc DFS có gì khác?

**Đáp án:** Gốc là điểm khớp **khi và chỉ khi nó có ít nhất hai con trực tiếp trong cây DFS**. Không dùng công thức của đỉnh có cha và không đếm số hàng xóm làm số con.

**Câu 5.** Vì sao hai cạnh song song 0--1 không phải cầu?

**Đáp án:** Xóa một cạnh vẫn có cạnh kia nối hai đỉnh; low của con quay được về cha qua cạnh ID khác. Nếu code bỏ hết những cạnh v==parent sẽ sai.

**Câu 6.** Trong ví dụ chính, vì sao 6 là điểm khớp nhưng cạnh 6--7 không là cầu?

**Đáp án:** low[7]=tin[6]=6. Điều kiện điểm khớp của đỉnh thường dùng **>=** nên 6 khớp; điều kiện cầu dùng **>**, sai khi bằng, vì có cạnh song song nối 6 với 7.

**Câu 7.** Một đỉnh cô lập có phải điểm khớp không?

**Đáp án:** Không. Xóa nó không làm tăng số thành phần; thường số thành phần giảm một.

**Câu 8.** Trong ví dụ V=10, tập điểm khớp và cạnh cầu là gì?

**Đáp án:** Điểm khớp **[1,3,6,7]**; cạnh cầu **[1-3,3-6,7-8]**. Đỉnh 9 cô lập và self-loop 5--5 không tạo cầu/khớp.

**Câu 9.** Tại sao phải chạy DFS từ mọi đỉnh chưa thăm?

**Đáp án:** Vì đồ thị có thể có nhiều thành phần liên thông; mỗi thành phần cần một gốc DFS riêng để xác định cầu/khớp của toàn bộ đồ thị.

**Câu 10.** Vì sao một đỉnh có bậc lớn chưa chắc là điểm khớp?

**Đáp án:** Các hàng xóm có thể còn liên thông qua chu trình; xóa đỉnh đó vẫn không tăng số thành phần.

**Câu 11.** Độ phức tạp phát hiện low-link là bao nhiêu?

**Đáp án:** O(V+E) thời gian và O(V+E) bộ nhớ nếu tính cả danh sách kề; riêng mảng và stack O(V). Nếu muốn sắp B cạnh cầu để in, cần thêm O(B log B) thời gian.

**Câu 12.** Khi kiểm thử low-link trên graph nhỏ, cách độc lập nào dễ tin cậy?

**Đáp án:** Đếm số thành phần liên thông gốc, rồi **xóa từng đỉnh hoặc đúng từng cạnh theo ID** và đếm lại. Điểm/cạnh làm số thành phần **tăng** là điểm khớp/cầu.

**Ghi nhớ:** Với DFS trên **đồ thị vô hướng**, thời điểm **tin** và giá trị **low-link** trả lời liệu một cây con có đường quay về tổ tiên hay không. **Cầu:** low[child] **>** tin[parent]. **Điểm khớp thường:** low[child] **>=** tin[parent]. **Gốc DFS:** cần **hơn một con trực tiếp**. Trên multigraph, nhất thiết bỏ qua **ID của đúng cạnh cây tới cha**, không bỏ mọi cạnh tới cùng đỉnh cha.

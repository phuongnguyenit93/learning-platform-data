# Thuật toán Prim với các cách chọn cạnh

**Prim** là thuật toán tham lam tìm **cây khung nhỏ nhất** (*minimum spanning tree – MST*) của **đồ thị vô hướng, có trọng số, liên thông**. Thay vì xét tất cả cây có thể tạo, Prim bắt đầu từ một đỉnh, duy trì tập S gồm các đỉnh đã nằm trong cây, rồi liên tục chọn **cạnh nhẹ nhất nối từ S ra một đỉnh chưa thuộc S**. Mỗi lần chọn, cây tăng thêm đúng một đỉnh và một cạnh. Khi S chứa tất cả V đỉnh, kết quả có V−1 cạnh, liên thông và tổng trọng số nhỏ nhất.

Có nhiều cách thực hiện đúng cùng quy tắc chọn cạnh này:

1. **Quét ma trận/khóa đỉnh**: tìm ứng viên nhỏ nhất bằng một vòng quét các đỉnh, đơn giản, thích hợp với đồ thị dày.
2. **Prim lazy với hàng đợi ưu tiên chứa cạnh**: đưa các cạnh ứng viên vào min-heap; khi lấy ra phải **bỏ cạnh cũ** nếu đầu đích đã nằm trong cây.
3. **Prim eager với khóa tốt nhất của từng đỉnh**: với mỗi v chưa chọn, duy trì trọng số nhỏ nhất của cạnh nối v tới tập S và một đỉnh cha tương ứng; dùng indexed min-heap hoặc min-heap thường với bản ghi cũ (*lazy decrease-key*).

Ba cách đều dựa trên **tính chất đường cắt** (*cut property*) và đều đúng nếu xử lý trạng thái, chiều cạnh, điều kiện chọn, cùng trường hợp hòa trọng số một cách nhất quán. Chúng có **chi phí thời gian/bộ nhớ khác nhau**, nhưng không làm đổi định nghĩa MST.

Bài học trình bày chứng minh tính đúng, mô phỏng chọn cạnh, xử lý đồ thị không liên thông thành **rừng khung nhỏ nhất** (*minimum spanning forest – MSF*), so sánh ba cách chọn cạnh và một chương trình **Java 17+** hoàn chỉnh. Ví dụ có cạnh âm, cạnh song song, self-loop và đỉnh cô lập để làm rõ điểm dễ sai.

## 1. Cây khung và tổng trọng số

Cho đồ thị vô hướng có trọng số \(G=(V,E,w)\). Một **cây khung** là tập cạnh:

- Chứa tất cả các đỉnh V.
- Liên thông: từ mỗi đỉnh tới được mọi đỉnh khác.
- Không có chu trình.
- Có đúng \(V-1\) cạnh nếu \(V\ge1\).

**MST** là cây khung có tổng trọng số cạnh nhỏ nhất:

\[
w(T)=\sum_{e\in T}w(e),\qquad
T_{\min}\in\arg\min_{\text{cây khung }T} w(T).
\]

MST tối ưu **tổng trọng số của cả cây**, không nhất thiết làm cho đường đi từ một gốc tới từng đỉnh ngắn nhất. Đừng nhầm MST với **shortest-path tree** của Dijkstra hoặc Bellman–Ford.

Nếu graph **không liên thông**, không tồn tại một cây khung của **toàn đồ thị**. Ta có thể thay mục tiêu bằng **rừng khung nhỏ nhất** (*MSF*): với mỗi thành phần liên thông, chọn MST của thành phần đó; hợp các cây là MSF.

Cạnh có trọng số **âm** hoàn toàn được phép trong MST. Prim chỉ so sánh trọng số cạnh cắt, không yêu cầu trọng số không âm. Điều kiện “không có cạnh âm” của **Dijkstra** không được chuyển sang Prim.

### Đồ thị được xét phải vô hướng

Nếu có cạnh \(\{u,v\}\), đi từ u sang v hoặc ngược lại đều được. Một danh sách kề thực tế thường lưu **hai cung** để biểu diễn cùng **một cạnh vô hướng**: u→v và v→u. Điều này không biến bài toán thành MST có hướng.

Bài toán chọn cây có hướng gốc và cung đi vào mỗi đỉnh (minimum arborescence) là một bài **khác**; không thể chạy nguyên Prim rồi khẳng định đáp án tối ưu cho graph có hướng.

## 2. Tính chất đường cắt: cơ sở để chọn cạnh tham lam

Một **đường cắt** (*cut*) chia tập đỉnh thành hai phần S và \(V\setminus S\). Một cạnh **băng qua đường cắt** khi có đúng một đầu mút ở S, đầu còn lại ở ngoài S.

Khi Prim đang xây cây, S chính là tập các đỉnh **đã được chọn**. Ứng viên hợp lệ phải:

\[
u\in S,\quad v\notin S,\quad e=\{u,v\}\in E.
\]

Prim chọn:

\[
e^*\in\arg\min\{w(e):e\text{ băng qua }(S,V\setminus S)\}.
\]

**Không phải chọn cạnh nhẹ nhất toàn đồ thị** và cũng không phải chọn cạnh nhẹ nhất kề đỉnh vừa thêm. Cạnh phải đi từ **bất kỳ đỉnh đã chọn nào** ra ngoài tập S.

### Chứng minh bằng phép đổi cạnh (exchange argument)

Giả sử A là tập cạnh Prim đã chọn, A nằm trong ít nhất một MST T. Xét cạnh e có trọng số nhỏ nhất qua đường cắt S–bên ngoài, với S chứa các đỉnh hiện có của cây A.

- Nếu \(e\in T\), thêm e vẫn tương thích với MST T.
- Nếu \(e\notin T\), thêm e vào T tạo đúng một chu trình.
- Vì e băng qua đường cắt S–\(V\setminus S\), chu trình phải có ít nhất một cạnh khác f cũng băng qua đường cắt.
- Do e là cạnh nhẹ nhất qua đường cắt, \(w(e)\le w(f)\).
- Thay f bằng e được cây khung \(T'=T-f+e\) có \(w(T')\le w(T)\). Vì T là MST, T' cũng là MST.
- Chọn f không thuộc A (những cạnh trong A nối bên trong S), nên T' vẫn chứa A và chứa thêm e.

Vậy sau mỗi bước Prim, **tập cạnh đã chọn vẫn có thể mở rộng thành một MST**. Khi đủ V−1 cạnh, chính tập cạnh ấy là một MST.

Lập luận vẫn đúng nếu có **trọng số âm hoặc nhiều cạnh bằng nhau**. Nếu hai cạnh cùng nhẹ nhất qua đường cắt, cả hai đều có thể là lựa chọn an toàn; đồ thị có thể có **nhiều MST khác nhau nhưng cùng tổng trọng số tối ưu**.

### Vì sao không chọn cạnh nội bộ?

Nếu cả hai đầu u,v đã ở S, cạnh u–v **không thêm đỉnh mới**. Thêm nó vào cây đang liên thông trên S sẽ tạo chu trình. Dù cạnh rất nhẹ hoặc âm, nó **không phải ứng viên cắt hợp lệ** tại thời điểm ấy.

Vì vậy tiêu chí “đang có cạnh trọng số nhỏ nhất trong heap” mới chỉ là **một nửa**: trước khi thêm phải kiểm tra cạnh đó **thực sự nối tập đã chọn với một đỉnh chưa chọn**.

## 3. Ví dụ xuyên suốt: ba thành phần và trọng số đặc biệt

Xét graph vô hướng có **9 đỉnh** `0..8`. Các cạnh theo thứ tự đầu vào:

| Cạnh | Trọng số | Ghi chú |
|---|---:|---|
| 0–1 | 4 | Liên kết đầu tiên từ 0 |
| 0–2 | 3 | Nhẹ hơn 0–1 |
| 1–2 | 1 | Cạnh rất nhẹ giữa 1 và 2 |
| 1–3 | 2 | Mở rộng sang 3 |
| 2–3 | 4 | Cạnh thay thế |
| 2–4 | 5 | Cạnh thay thế |
| 3–4 | 2 | Mở rộng sang 4 |
| 3–5 | 3 | Một ứng viên để đến 5 |
| 4–5 | 3 | Hòa trọng số cho đường tới 5 |
| 6–7 | **−2** | Thành phần thứ hai, cạnh âm |
| 1–1 | **−20** | **Self-loop:** không thể thuộc cây |
| 0–2 | 6 | **Cạnh song song:** kém hơn cạnh 0–2 trọng số 3 |
| Đỉnh 8 | — | Cô lập |

Đồ thị có ba **thành phần liên thông**:

~~~text
Thành phần A: {0,1,2,3,4,5}
Thành phần B: {6,7}
Thành phần C: {8}
~~~

Không có **một MST toàn graph 9 đỉnh**, vì không có cạnh nối A với B và C. Nhưng có **MSF**, gồm một MST của A, cạnh 6–7, và cây đơn đỉnh 8.

### Mô phỏng Prim từ đỉnh 0

Ban đầu \(S=\{0\}\), tập cạnh được chọn rỗng.

| Bước | S trước khi chọn | Cạnh nhẹ nhất **qua đường cắt** | S sau khi chọn | Tổng phần A |
|---:|---|---|---|---:|
| 1 | {0} | 0–2 (3) | {0,2} | 3 |
| 2 | {0,2} | 1–2 (1) | {0,1,2} | 4 |
| 3 | {0,1,2} | 1–3 (2) | {0,1,2,3} | 6 |
| 4 | {0,1,2,3} | 3–4 (2) | {0,1,2,3,4} | 8 |
| 5 | {0,1,2,3,4} | 3–5 (3) | {0,1,2,3,4,5} | **11** |

Tổng MST của thành phần A là \(3+1+2+2+3=11\).

Tại bước 2, cạnh 1–2 (1) được xét **dù đỉnh mới nhất là 2**. Prim nhìn mọi cạnh qua S: cạnh từ 0 hoặc 2 ra ngoài đều là ứng viên.

Sau khi chọn 1–2, cạnh này trở thành **cạnh nội bộ của S**. Nó không được chọn lại dù vẫn có trọng số 1. Ở bước 5, 3–5 và 4–5 cùng có trọng số 3; ví dụ chọn **3–5** theo quy tắc ưu tiên đã công bố, nhưng chọn 4–5 cũng có thể cho một MST hợp lệ cùng tổng.

Thành phần B có đúng một cạnh 6–7 trọng số −2. Thành phần C chỉ có đỉnh 8, nên không cần cạnh. Tổng MSF:

\[
\boxed{11+(-2)+0=9},
\]

số cạnh được chọn là \(5+1+0=6=9-3\), đúng bằng **V − số thành phần**.

**Self-loop 1–1 trọng số −20 không được chọn** dù rất âm, vì nó không nối hai đỉnh phân biệt và tạo chu trình độ dài 1. Cạnh song song 0–2 trọng số 6 cũng không giúp cải thiện MST.

## 4. Bất biến của Prim

Trong một thành phần liên thông đang xử lý, duy trì:

1. **S** chứa chính các đỉnh đã được đưa vào cây.
2. Tập cạnh A đã chọn tạo thành **một cây** trên S: không chu trình, liên thông và có \(|S|-1\) cạnh khi S không rỗng.
3. A là một **tập cạnh an toàn**: tồn tại ít nhất một MST của thành phần đang xét chứa toàn bộ A.
4. Ứng viên tiếp theo được xét từ các cạnh **băng qua đường cắt** S–các đỉnh chưa chọn.
5. Khi không còn cạnh băng qua đường cắt, ta đã hoàn thành **toàn bộ thành phần liên thông** chứa gốc đó.

**Cơ sở:** bắt đầu bằng một đỉnh gốc, A rỗng. Một đỉnh là cây hợp lệ và A nằm trong mọi MST của thành phần.

**Bước quy nạp:** chọn cạnh nhẹ nhất qua đường cắt, nối một đỉnh mới vào S. Không thể tạo chu trình vì đỉnh mới chưa thuộc S. Tính chất đường cắt bảo toàn tính an toàn của A.

**Kết thúc:** nếu thành phần liên thông có k đỉnh, sau k−1 bước S chứa cả k đỉnh, A có k−1 cạnh. Vì A an toàn và đã là cây khung của thành phần, A là MST.

**Không liên thông:** khi hết cạnh cắt nhưng vẫn còn đỉnh khác chưa chọn, thuật toán **không được giả định toàn graph đã có MST**; nó có thể bắt đầu một cây mới và trả về **MSF**.

## 5. Cách thứ nhất: Prim quét khóa đỉnh trong ma trận

Với ma trận trọng số `weight[u][v]`, ta có thể duy trì:

~~~text
inTree[v] = đã thuộc S?
key[v] = trọng số nhẹ nhất đã biết để nối v từ S
parent[v] = đầu mút trong S của cạnh có trọng số key[v]
~~~

Khởi động một thành phần bằng gốc r; đánh dấu r đã thuộc S và cập nhật khóa cho các neighbor chưa chọn. Sau đó lặp:

1. **Quét tất cả đỉnh chưa vào cây**, chọn v có `key[v]` nhỏ nhất.
2. Thêm cạnh `parent[v]–v`, đưa v vào S.
3. Quét hàng `weight[v][*]`; nếu cạnh v–u nhẹ hơn `key[u]` đang có, cập nhật `key[u]` và `parent[u]=v`.
4. Nếu không còn đỉnh chưa chọn nào có khóa hữu hạn, thành phần hiện tại đã xong; nếu làm MSF thì chuyển sang gốc chưa chọn khác.

**Điểm quan trọng:** `key[v]` là **trọng số của một cạnh nối v vào S**, không phải tổng đường đi từ gốc tới v. Tính tổng đường đi thay vì trọng số một cạnh sẽ biến bài toán sang ý nghĩa khác, làm sai Prim.

### Đỉnh có cạnh trọng số rất lớn

Trong cài đặt đơn giản, nhiều người khởi tạo `key[v]=INF`. Nếu `INF` là một số hữu hạn như `Long.MAX_VALUE`, một cạnh có trọng số đúng bằng giá trị đó có thể bị nhầm là “không có cạnh”. Ví dụ Java phía dưới dùng **`Long[][]` với `null` nghĩa là không có cạnh** và mảng `Long[] best` với `null` nghĩa là chưa tìm được cạnh nối, nên không nhầm các giá trị trọng số hợp lệ với sentinel.

### Độ phức tạp

Xây ma trận từ danh sách cạnh tốn O(V²+E) thời gian để cấp phát/điền và O(V²) bộ nhớ. Mỗi lần chọn đỉnh bằng cách quét V đỉnh, tối đa V lần; mỗi lần chọn có thể quét cả hàng ma trận V ô. Tổng thời gian của phần Prim là:

\[
\boxed{O(V^2)}.
\]

Cách này dễ hiểu, không cần priority queue và phù hợp khi graph **dày** (\(E\) gần \(V^2\)) hoặc khi ma trận kề đã có sẵn. Với graph thưa rất lớn, bộ nhớ O(V²) có thể không phù hợp.

## 6. Cách thứ hai: Prim lazy – min-heap chứa cạnh

Thay vì giữ một khóa tốt nhất cho từng đỉnh, **lazy Prim** đưa **các cạnh ứng viên** vào một min-heap theo trọng số.

Mã giả cho một thành phần:

~~~text
mark root as inTree
push every edge (root, v, weight) with v not inTree

while heap not empty:
    edge = heap.popMin()

    if edge.to already inTree:
        continue      // stale edge, no new vertex

    add edge.from -- edge.to to result
    mark edge.to as inTree

    for every edge (edge.to, next):
        if next not inTree:
            heap.push(edge.to, next, weight)
~~~

Mọi cạnh được đưa vào heap đều có **đầu from đã thuộc S tại thời điểm thêm**, còn đầu to ở ngoài S lúc ấy. Về sau to có thể đã thuộc S qua một đường khác, làm bản ghi trở thành **stale** (*lỗi thời*); phải kiểm tra lại khi pop.

### Tại sao phải bỏ bản ghi cũ?

Từ đỉnh 0 có thể đưa vào heap cạnh 0–1(4) và 0–2(3). Sau khi chọn 0–2(3), ta khám phá thêm 1–2(1). Khi 1–2(1) được chọn, đỉnh 1 đã vào cây; bản ghi 0–1(4) còn trong heap nhưng bây giờ **cả hai đầu đã ở S**. Nếu vẫn thêm 0–1(4), ta tạo chu trình 0–2–1–0 và không còn MST.

Do đó trong bản lazy, **popMin không đồng nghĩa cạnh được chọn**. Điều kiện chọn là: cạnh pop ra thật sự đưa một **đỉnh mới** vào cây.

### Hệ quả về độ phức tạp

Mỗi cạnh vô hướng được xem từ hai đầu qua danh sách kề, nhưng với cách chỉ push tới đỉnh chưa chọn, mỗi cạnh được push tối đa một lần ở thời điểm một đầu mới vào S. Với graph nhiều cạnh song song, số bản ghi trong heap có thể đạt O(E).

Thời gian:

\[
O((V+E)\log(E+1))
\]

là một cận dễ hiểu khi dùng binary heap, cộng chi phí xây adjacency list. Với graph đơn \(E\le O(V^2)\), thường viết **O(E log V)** cho phần có cạnh khi E không quá nhỏ. Bộ nhớ phụ cho heap là **O(E)**, ngoài visited O(V) và graph O(V+E).

Lazy Prim thường dễ triển khai, nhưng có thể dùng **nhiều bộ nhớ hơn** eager Prim nếu có vô số ứng viên lỗi thời trong heap.

## 7. Cách thứ ba: Prim eager – khóa nhỏ nhất của mỗi đỉnh

**Eager Prim** nhìn bài toán từ phía **đỉnh chưa chọn**:

\[
key[v]=\min\{w(u,v): u\in S,\{u,v\}\in E\}.
\]

Khi thêm một đỉnh u vào S, ta kiểm tra các neighbor v ở ngoài S và **cải thiện khóa** nếu cạnh u–v nhẹ hơn.

Mã giả:

~~~text
for each v:
    best[v] = undefined
    parent[v] = -1

mark root inTree
relax every edge from root

while exists outside vertex with defined best:
    v = outside vertex with minimum best[v]
    add (parent[v], v, best[v]) to result
    mark v inTree

    for each neighbor x of v:
        if not inTree[x] and weight(v,x) < best[x]:
            best[x] = weight(v,x)
            parent[x] = v
~~~

Khác với lazy chứa nhiều **cạnh** tới cùng một đỉnh v, eager về mặt logic chỉ cần **một ứng viên tốt nhất cho v**.

### Hai kiểu priority queue

**Indexed min-heap có decrease-key:** mỗi đỉnh chưa chọn có tối đa một entry. Khi khóa giảm, cập nhật vị trí của v trong heap. Với binary heap có index-map, thời gian thường **O((V+E)log V)** và heap O(V), đồ thị O(V+E).

**PriorityQueue Java thông thường:** không có thao tác decrease-key theo chỉ số. Ta có thể **đẩy bản ghi khóa mới** mỗi khi tìm được một cạnh tốt hơn; bản ghi cũ được bỏ khi pop nếu không còn khớp với `best[v]`/parent. Đây là cách **eager theo khóa** nhưng **lazy trong việc loại heap entry**.

Mã Java dưới đây dùng cách thứ hai để giữ mã đơn giản. Bảng `best[v]` chỉ giữ **một cạnh tốt nhất về mặt logic**, nhưng hàng đợi có thể chứa O(E) bản ghi, nên **không được tuyên bố O(V) bộ nhớ heap cho chính phiên bản này**. Chi phí heap trong bản này gần dạng O(E log(E+1)); muốn heap thật sự O(V), cần indexed heap hoặc cấu trúc decrease-key thích hợp.

### Khác biệt “chọn cạnh” giữa lazy và eager

- **Lazy:** chọn **bản ghi cạnh nhẹ nhất** đang hợp lệ qua đường cắt.
- **Eager:** chọn **đỉnh chưa vào cây có khóa tốt nhất**, tương ứng cạnh nhẹ nhất hiện nối đỉnh đó với S.
- Cả hai giải cùng phép tối thiểu hóa trên tập cạnh cắt, vì:
  \[
  \min_{e\text{ qua cắt}}w(e)
  =\min_{v\notin S,\;key[v]\text{ đã có}}key[v].
  \]
- Nếu có nhiều cạnh bằng trọng số, **quy tắc tie-break** có thể khiến hai cài đặt chọn những cạnh khác nhau nhưng vẫn cùng tổng MST tối ưu.

## 8. Quy tắc hòa trọng số và kết quả có nhiều MST

Khi nhiều cạnh băng qua đường cắt cùng có trọng số thấp nhất, tính chất đường cắt nói rằng **mọi lựa chọn nhẹ nhất đều an toàn**. Vì thế Prim không nhất thiết trả **một danh sách cạnh duy nhất** nếu graph có trọng số bằng nhau.

Để bài kiểm tra và stdout tái lập, có thể quy định thứ tự phụ:

- Với **lazy cạnh**, so sánh theo `(weight, min(u,v), max(u,v), edgeId)`.
- Với **eager khóa đỉnh**, so sánh theo `(key, vertexId)`, và khi v nhận hai cạnh có cùng trọng số thì ưu tiên parent có ID nhỏ hơn, sau đó edgeId.
- Với **quét ma trận**, khi khóa bằng nhau chọn vertex ID nhỏ hơn; khi cập nhật khóa bằng nhau ưu tiên parent ID nhỏ hơn.

Các quy tắc phụ này **không phải điều kiện để MST đúng**; chúng chỉ tạo đầu ra ổn định.

Trong ví dụ, cạnh **3–5(3)** và **4–5(3)** có cùng trọng số. Ta dùng quy tắc ưu tiên parent nhỏ hơn để chọn **3–5(3)**. Nếu một cách cài đặt chọn 4–5(3), kết quả vẫn có thể hoàn toàn đúng. Khi so sánh các cài đặt MST trên graph có cạnh hòa, nên kiểm **tổng trọng số**, **số cạnh**, **liên thông**, **không chu trình**, và tính khả thi, thay vì luôn yêu cầu danh sách cạnh giống nhau từng phần tử.

## 9. Graph không liên thông: MST khác MSF

Trong đồ thị có nhiều thành phần, ở một thời điểm heap/khóa của thành phần hiện tại không còn cạnh nối ra ngoài. Đây không phải lỗi thuật toán; nó chỉ nói **thành phần liên thông đang duyệt đã hoàn tất**.

Nếu đặc tả yêu cầu **MST của toàn bộ graph** và graph không liên thông, phải báo **không tồn tại**. Nếu đặc tả cho phép **MSF**, lặp qua mọi đỉnh chưa chọn và dùng nó làm **gốc của cây tiếp theo**.

Với V đỉnh và c thành phần liên thông, MSF có:

\[
\boxed{V-c\text{ cạnh}}
\]

và gồm đúng c cây. Một đỉnh cô lập đóng góp **một cây đơn đỉnh, không có cạnh**, không phải bị quên khỏi kết quả.

Mã Java trong bài trả về **MSF**, kèm **`components`**, nên người gọi có thể phân biệt:

- `components==1` với `V>=1`: có MST của toàn graph.
- `components>1`: graph không liên thông; kết quả là MSF.
- `V==0`: rừng rỗng, `components=0`, tổng trọng số 0 theo quy ước của demo.

### Có cần chạy Prim từ đỉnh 0?

Không. Trong một thành phần liên thông, Prim có thể bắt đầu từ **bất kỳ đỉnh nào**; tất cả lần chạy đúng đều trả tổng trọng số MST tối ưu. **Danh sách cạnh cụ thể** có thể khác khi có nhiều MST. Mã dùng thứ tự gốc tăng `0..V-1` để kết quả tái lập, không phải vì đỉnh 0 đặc biệt về mặt toán học.

## 10. Java 17+: ba cách chọn cạnh trong cùng một chương trình

Chương trình minh họa ba bộ giải:

- **`primLazy`**: adjacency list + min-heap các cạnh; kiểm tra `inTree[to]` trước khi chọn.
- **`primEager`**: adjacency list + bảng `best[v]` và parent + heap bản ghi cập nhật; bỏ entry lỗi thời.
- **`primDense`**: ma trận trọng số tối thiểu giữa mỗi cặp đỉnh; quét toàn bộ đỉnh để chọn khóa nhỏ nhất, rồi quét hàng ma trận để cập nhật.

Cả ba đều trả **MSF** để xử lý đồ thị không liên thông thống nhất. Cạnh kết quả được chuẩn hóa hai đầu `u<v` khi in, nhưng thuật toán vẫn biết **đầu trong S** và **đầu mới** khi chọn.

**Đầu vào:**

- `InputEdge(u,v,weight)` là **cạnh vô hướng**. Graph builder tự thêm hai cung vào danh sách kề, trừ self-loop.
- Cho phép **trọng số âm**, **cạnh song song**, **cạnh bằng trọng số** và **đỉnh cô lập**.
- **Bỏ self-loop** vì nó không thể thuộc cây.
- Dùng `Math.addExact` khi cộng tổng trọng số để không im lặng trả kết quả tràn `long`.
- Dùng `Long` nullable cho khóa chưa tồn tại và cạnh ma trận chưa có, tránh sentinel đụng với một trọng số hợp lệ.
- Không dùng phép trừ trọng số để làm comparator vì hiệu của hai `long` có thể overflow; dùng `Comparator.comparingLong`.

Lưu tệp **PrimEdgeSelectionDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class PrimEdgeSelectionDemo {
    record InputEdge(int u, int v, long weight) {}
    record Arc(int to, long weight, int id) {}
    record Candidate(int from, int to, long weight, int id) {}
    record KeyEntry(int vertex, long weight, int parent, int id) {}

    record TreeEdge(int u, int v, long weight) {
        @Override
        public String toString() {
            return u + "-" + v + "(" + weight + ")";
        }
    }

    record Forest(long totalWeight, int components, List<TreeEdge> edges) {}

    static TreeEdge edge(int u, int v, long weight) {
        return new TreeEdge(Math.min(u, v), Math.max(u, v), weight);
    }

    static void validate(int vertices, List<InputEdge> edges) {
        Objects.requireNonNull(edges, "edges");
        if (vertices < 0) {
            throw new IllegalArgumentException("negative vertex count");
        }
        for (InputEdge e : edges) {
            if (e == null || e.u() < 0 || e.u() >= vertices
                    || e.v() < 0 || e.v() >= vertices) {
                throw new IllegalArgumentException("invalid edge endpoint");
            }
        }
    }

    static List<List<Arc>> adjacency(int n, List<InputEdge> edges) {
        validate(n, edges);
        List<List<Arc>> graph = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            graph.add(new ArrayList<>());
        }
        for (int i = 0; i < edges.size(); i++) {
            InputEdge e = edges.get(i);
            if (e.u() == e.v()) {
                continue; // A self-loop cannot belong to a spanning tree.
            }
            graph.get(e.u()).add(new Arc(e.v(), e.weight(), i));
            graph.get(e.v()).add(new Arc(e.u(), e.weight(), i));
        }
        return graph;
    }

    static final Comparator<Candidate> EDGE_ORDER =
        Comparator.comparingLong(Candidate::weight)
                  .thenComparingInt(c -> Math.min(c.from(), c.to()))
                  .thenComparingInt(c -> Math.max(c.from(), c.to()))
                  .thenComparingInt(Candidate::id);

    // Lazy Prim: heap stores edges, possibly obsolete edges.
    static Forest primLazy(int n, List<InputEdge> edges) {
        List<List<Arc>> graph = adjacency(n, edges);
        boolean[] inTree = new boolean[n];
        List<TreeEdge> chosen = new ArrayList<>();
        long total = 0L;
        int components = 0;

        PriorityQueue<Candidate> pq =
            new PriorityQueue<>(EDGE_ORDER);

        for (int root = 0; root < n; root++) {
            if (inTree[root]) {
                continue;
            }
            components++;
            inTree[root] = true;
            for (Arc a : graph.get(root)) {
                if (!inTree[a.to()]) {
                    pq.add(new Candidate(root, a.to(),
                        a.weight(), a.id()));
                }
            }

            while (!pq.isEmpty()) {
                Candidate c = pq.poll();
                if (inTree[c.to()]) {
                    continue; // Edge is no longer crossing the cut.
                }
                chosen.add(edge(c.from(), c.to(), c.weight()));
                total = Math.addExact(total, c.weight());
                inTree[c.to()] = true;

                for (Arc a : graph.get(c.to())) {
                    if (!inTree[a.to()]) {
                        pq.add(new Candidate(c.to(), a.to(),
                            a.weight(), a.id()));
                    }
                }
            }
        }
        return new Forest(total, components, List.copyOf(chosen));
    }

    static final Comparator<KeyEntry> KEY_ORDER =
        Comparator.comparingLong(KeyEntry::weight)
                  .thenComparingInt(KeyEntry::vertex)
                  .thenComparingInt(KeyEntry::parent)
                  .thenComparingInt(KeyEntry::id);

    // Eager logical keys, but a normal Java heap with stale entries.
    static Forest primEager(int n, List<InputEdge> edges) {
        List<List<Arc>> graph = adjacency(n, edges);
        boolean[] inTree = new boolean[n];
        Long[] best = new Long[n];
        int[] parent = new int[n];
        int[] edgeId = new int[n];
        Arrays.fill(parent, -1);
        Arrays.fill(edgeId, -1);

        List<TreeEdge> chosen = new ArrayList<>();
        long total = 0L;
        int components = 0;
        PriorityQueue<KeyEntry> pq =
            new PriorityQueue<>(KEY_ORDER);

        for (int root = 0; root < n; root++) {
            if (inTree[root]) {
                continue;
            }
            components++;
            inTree[root] = true;
            relax(root, graph, inTree, best, parent, edgeId, pq);

            while (!pq.isEmpty()) {
                KeyEntry entry = pq.poll();
                int v = entry.vertex();
                if (inTree[v] || best[v] == null
                        || entry.weight() != best[v]
                        || entry.parent() != parent[v]
                        || entry.id() != edgeId[v]) {
                    continue; // Stale key entry.
                }
                chosen.add(edge(parent[v], v, best[v]));
                total = Math.addExact(total, best[v]);
                inTree[v] = true;
                relax(v, graph, inTree, best, parent, edgeId, pq);
            }
        }
        return new Forest(total, components, List.copyOf(chosen));
    }

    private static void relax(
        int u, List<List<Arc>> graph, boolean[] inTree,
        Long[] best, int[] parent, int[] edgeId,
        PriorityQueue<KeyEntry> pq
    ) {
        for (Arc a : graph.get(u)) {
            int v = a.to();
            if (inTree[v]) {
                continue;
            }
            boolean improve = best[v] == null
                || a.weight() < best[v]
                || (a.weight() == best[v]
                    && (u < parent[v]
                        || (u == parent[v] && a.id() < edgeId[v])));
            if (improve) {
                best[v] = a.weight();
                parent[v] = u;
                edgeId[v] = a.id();
                pq.add(new KeyEntry(v, a.weight(), u, a.id()));
            }
        }
    }

    // Dense Prim: scan all vertices for the minimum key.
    static Forest primDense(int n, List<InputEdge> edges) {
        validate(n, edges);
        Long[][] weight = new Long[n][n];
        for (InputEdge e : edges) {
            if (e.u() == e.v()) {
                continue;
            }
            Long old = weight[e.u()][e.v()];
            if (old == null || e.weight() < old) {
                weight[e.u()][e.v()] = e.weight();
                weight[e.v()][e.u()] = e.weight();
            }
        }

        boolean[] inTree = new boolean[n];
        Long[] key = new Long[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);
        List<TreeEdge> chosen = new ArrayList<>();
        long total = 0L;
        int components = 0;

        for (int root = 0; root < n; root++) {
            if (inTree[root]) {
                continue;
            }
            components++;
            inTree[root] = true;
            updateRow(root, weight, inTree, key, parent);

            while (true) {
                int v = -1;
                for (int u = 0; u < n; u++) {
                    if (!inTree[u] && key[u] != null
                            && (v == -1 || key[u] < key[v]
                                || (key[u].equals(key[v]) && u < v))) {
                        v = u;
                    }
                }
                if (v == -1) {
                    break;
                }
                chosen.add(edge(parent[v], v, key[v]));
                total = Math.addExact(total, key[v]);
                inTree[v] = true;
                updateRow(v, weight, inTree, key, parent);
            }
        }
        return new Forest(total, components, List.copyOf(chosen));
    }

    private static void updateRow(
        int u, Long[][] weight, boolean[] inTree,
        Long[] key, int[] parent
    ) {
        for (int v = 0; v < weight.length; v++) {
            Long w = weight[u][v];
            if (inTree[v] || w == null) {
                continue;
            }
            if (key[v] == null || w < key[v]
                    || (w.equals(key[v]) && u < parent[v])) {
                key[v] = w;
                parent[v] = u;
            }
        }
    }

    public static void main(String[] args) {
        List<InputEdge> edges = List.of(
            new InputEdge(0, 1, 4),
            new InputEdge(0, 2, 3),
            new InputEdge(1, 2, 1),
            new InputEdge(1, 3, 2),
            new InputEdge(2, 3, 4),
            new InputEdge(2, 4, 5),
            new InputEdge(3, 4, 2),
            new InputEdge(3, 5, 3),
            new InputEdge(4, 5, 3),
            new InputEdge(6, 7, -2),
            new InputEdge(1, 1, -20), // ignored self-loop
            new InputEdge(0, 2, 6)    // worse parallel edge
        );

        Forest lazy = primLazy(9, edges);
        Forest eager = primEager(9, edges);
        Forest dense = primDense(9, edges);
        System.out.println("Lazy weight: " + lazy.totalWeight());
        System.out.println("Lazy components: " + lazy.components());
        System.out.println("Lazy edges: " + lazy.edges());
        System.out.println("Eager weight: " + eager.totalWeight());
        System.out.println("Eager components: " + eager.components());
        System.out.println("Eager edges: " + eager.edges());
        System.out.println("Dense weight: " + dense.totalWeight());
        System.out.println("Dense components: " + dense.components());
        System.out.println("Dense edges: " + dense.edges());

        List<InputEdge> connected = edges.subList(0, 9);
        System.out.println("Connected MST weight: "
            + primLazy(6, connected).totalWeight());
        System.out.println("Empty graph components: "
            + primEager(0, List.of()).components());
        System.out.println("Only isolated vertices: "
            + primDense(3, List.of()).components());

        try {
            primLazy(2, List.of(new InputEdge(0, 2, 1)));
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid edge rejected: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy với **JDK 17 trở lên**:

~~~bash
javac PrimEdgeSelectionDemo.java
java PrimEdgeSelectionDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
Lazy weight: 9
Lazy components: 3
Lazy edges: [0-2(3), 1-2(1), 1-3(2), 3-4(2), 3-5(3), 6-7(-2)]
Eager weight: 9
Eager components: 3
Eager edges: [0-2(3), 1-2(1), 1-3(2), 3-4(2), 3-5(3), 6-7(-2)]
Dense weight: 9
Dense components: 3
Dense edges: [0-2(3), 1-2(1), 1-3(2), 3-4(2), 3-5(3), 6-7(-2)]
Connected MST weight: 11
Empty graph components: 0
Only isolated vertices: 3
Invalid edge rejected: invalid edge endpoint
~~~

### Cách đọc kết quả

Mỗi cách thêm một đỉnh mới qua cạnh cắt nhẹ nhất. Cả ba dùng cùng đồ thị mẫu và quy tắc tie ổn định, nên ở đây trả **cùng sáu cạnh**, tổng 9. Đây chỉ là tính chất của ví dụ và tie-break đã chọn; trên graph khác, hai MST hợp lệ có thể khác cạnh nhưng vẫn cùng tổng.

**Vì sao total không bị self-loop âm chi phối?** Cạnh 1–1 (−20) không đưa một đỉnh mới vào S nên builder bỏ qua. Một thuật toán cứ lấy cạnh nhẹ nhất toàn graph sẽ chọn sai self-loop này.

**Vì sao 0–2(6) không được chọn?** 0–2(3) nối cùng cặp đỉnh với trọng số nhỏ hơn, nên cạnh 6 không bao giờ có ích để tạo MST tối ưu. Bản lazy/eager vẫn đọc được cạnh song song; bản dense giữ trọng số nhỏ nhất theo cặp khi xây ma trận.

**Vì sao có 3 components nhưng chỉ 6 edges?** Thành phần đầu có 6 đỉnh và 5 cạnh cây, thành phần 6–7 có 2 đỉnh và 1 cạnh, đỉnh 8 cô lập có 0 cạnh. Tổng cạnh đúng bằng \(V-c=9-3=6\).

### Hai điểm an toàn trong code

**Không dùng sentinel số nguyên cho cạnh chưa có.** `Long[] best` và `Long[][] weight` phân biệt `null` với một trọng số thật, kể cả `Long.MAX_VALUE`. Tổng cạnh chọn dùng `Math.addExact`, do đó một tổng vượt phạm vi long gây lỗi rõ ràng thay vì im lặng quay vòng dấu.

**Không dùng heap entry cũ để gắn nhầm cha.** Bản eager lưu cùng lúc `best[v]`, `parent[v]`, `edgeId[v]`. Khi pop, nó so sánh các trường của entry với trạng thái hiện tại; entry cũ bị bỏ. Nếu chỉ so sánh trọng số mà không xử lý tie/parent, kết quả có thể khó dự đoán và dễ mất tính nhất quán của bản ghi khi có cạnh bằng nhau.

## 11. Chứng minh ba cách chọn đều tối ưu

Bản chất của Prim không phụ thuộc heap hay ma trận. Với mỗi cách, chứng minh hai điều:

**Tính hợp lệ:** trước khi thêm cạnh, một đầu của cạnh đã nằm trong S và đầu còn lại chưa nằm trong S. Thêm cạnh đó không thể tạo chu trình; sau k lần chọn, cây có k+1 đỉnh và k cạnh. Mỗi thành phần được hoàn tất khi không còn cạnh cắt.

**Tính tối ưu:** cạnh chọn có trọng số **nhỏ nhất trên toàn bộ đường cắt**. Theo tính chất đường cắt, cạnh đó là an toàn, giữ khả năng mở rộng thành MST. Khi không còn đỉnh trong thành phần chưa chọn, cây kết quả là MST của thành phần ấy.

Ta cần chứng minh cụ thể rằng mỗi cấu trúc lựa chọn thật sự trả đúng min qua cắt.

### 11.1. Quét ma trận/khóa

Với mọi v ngoài S, `key[v]` luôn bằng trọng số nhỏ nhất đã thấy của các cạnh từ **một đỉnh trong S** tới v (và parent chỉ đúng đầu u trong S của cạnh đó).

Tất cả cạnh cắt đều có một đầu trong S, nên khi S vừa mở rộng, quét hàng của đỉnh mới u sẽ xét hết các cạnh cắt mới xuất hiện. Mỗi lần quét toàn bộ v ngoài S để lấy min key chính là lấy min của **mọi cạnh cắt**.

### 11.2. Lazy edge heap

Khi một đỉnh u mới vào S, mọi cạnh u–v có v chưa ở S được đưa vào heap. Vì mỗi đầu u được xử lý lúc vào S, mỗi cạnh cắt hiện thời hoặc đã có entry phù hợp trong heap, hoặc vừa được thêm khi đầu bên trong S gia nhập.

Heap có thể chứa thêm **entry lỗi thời**, nhưng vòng pop bỏ những entry có đích đã ở S. Entry đầu tiên còn hợp lệ có trọng số nhỏ nhất trong những ứng viên cắt thật sự, nên là cạnh an toàn.

### 11.3. Eager key heap

Với mỗi v chưa vào S, `best[v]` là min trọng số của một cạnh nối v tới S. Khi S mở rộng qua đỉnh u, relax mọi cạnh u–v để duy trì bất biến.

Priority queue trả một entry có `best[v]` nhỏ nhất trong các ứng viên hiện thời sau khi bỏ stale records. Đó là min cạnh cắt toàn cục. Parent được lưu từ một đỉnh đã ở S, nên cạnh chọn thật sự nối một đỉnh mới vào cây.

**Nếu hai cạnh cùng trọng số:** chọn một trong những min vẫn an toàn. Bản mã có tie-break để thuận tiện đối chiếu, không thay đổi lập luận toán học.

## 12. Phân tích độ phức tạp theo cách chọn cạnh

Ký hiệu V là số đỉnh, E là số cạnh vô hướng gốc, tính cả cạnh song song trong dữ liệu đầu vào.

| Cách thực hiện | Thời gian | Bộ nhớ phụ ngoài đầu vào | Phù hợp |
|---|---|---|---|
| Ma trận + quét min key | **O(V²+E)** gồm xây ma trận | **O(V²)** | Graph dày, V vừa phải |
| Lazy edge min-heap | **O((V+E)log(E+1))** | **O(V+E)** gồm adjacency và heap O(E) | Graph thưa, dễ code |
| Eager key + indexed binary heap | **O((V+E)log V)** khi V≥2 | **O(V+E)** gồm graph, heap O(V) | Muốn quản lý một entry mỗi đỉnh |
| Eager key + Java PriorityQueue push bản ghi mới | **O((V+E)log(E+1))** | **O(V+E)**, heap có thể O(E) | Dễ code, không có decrease-key |

Với **đồ thị đơn**, \(E=O(V^2)\), nên nhiều sách viết heap Prim dưới dạng **O(E log V)** trong trường hợp connected graph có E≥V−1. Nếu có rất nhiều **cạnh song song**, E có thể lớn hơn \(V^2\); viết **log(E+1)** phản ánh đúng kích thước heap lazy hơn. Khi E=0 và V lớn, các thành phần đơn đỉnh vẫn cần vòng lặp qua V đỉnh, nên luôn giữ thêm chi phí **O(V)**.

**MST/MSF đầu ra** có tối đa \(V-c\) cạnh, cần O(V) chỗ lưu kết quả. Với bản ma trận, bộ nhớ O(V²) thường là yếu tố quyết định. Với hai bản danh sách kề, cả graph và heap có thể O(V+E).

### Có thể cải thiện cách chọn cạnh mà vẫn là Prim không?

Có. Có thể chọn cấu trúc dữ liệu nhanh hơn hoặc điều chỉnh cách tìm min qua cut:

- **Quét tuyến tính** với ma trận: không cần heap, O(V²).
- **Binary heap** với indexed decrease-key: O((V+E)log V).
- **Fibonacci heap** (mô hình lý thuyết): O(E+V log V) cho Prim với decrease-key amortized thích hợp.
- Các cấu trúc heap khác có ưu/nhược về hằng số, bộ nhớ và độ phức tạp triển khai.

Điều không thay đổi là **nguyên tắc chọn cạnh nhẹ nhất băng qua đường cắt**, chứ không phải tên cấu trúc dữ liệu. Chọn cách nào cần cân nhắc V, E, số cạnh trùng, bộ nhớ và yêu cầu đầu ra.

## 13. So sánh Prim với Kruskal và các thuật toán khác

**Prim:** duy trì một cây đang lớn dần theo đỉnh từ gốc, mỗi lần lấy cạnh nhẹ nhất **qua đường cắt tập S**. Trên graph không liên thông, cần khởi động lại cho từng thành phần để tạo MSF.

**Kruskal:** sắp các cạnh toàn graph theo trọng số tăng dần, xét từng cạnh và chọn nếu nó nối **hai thành phần DSU khác nhau**. Kruskal có thể chọn một cạnh ở bất kỳ thành phần nào trước, không phụ thuộc gốc. Dùng DSU giúp tránh chu trình.

Cả hai có thể tạo MST/MSF tối ưu nhưng **thứ tự chọn cạnh khác nhau**; nếu trọng số hòa nhau, danh sách cạnh kết quả có thể khác nhau.

**Dijkstra:** cũng dùng `key` và priority queue, nhưng `dist[v]` là **tổng trọng số đường đi từ nguồn**. Trong Prim, `key[v]` chỉ là **trọng số một cạnh nối v vào cây**. Nhầm hai phép cập nhật:

~~~text
Prim:     key[v] = min(key[v], weight(u,v))
Dijkstra: dist[v] = min(dist[v], dist[u] + weight(u,v))
~~~

sẽ làm sai mục tiêu. Dijkstra thông thường cần trọng số không âm; Prim **không cần**.

**Borůvka:** cũng là thuật toán MST dựa trên cạnh nhẹ nhất qua các đường cắt, nhưng mỗi pha có thể chọn cạnh nhẹ nhất đi ra **mỗi thành phần**, rồi hợp nhất nhiều thành phần cùng lúc. Không được nhầm một bước của Prim đang có một tập S với việc Borůvka cùng lúc mở rộng nhiều thành phần.

## 14. Trường hợp biên và kiểm tra dữ liệu

| Trường hợp | Xử lý đúng |
|---|---|
| V=0 | Theo demo: forest rỗng, `components=0`, total=0 |
| V=1, không cạnh | Một cây một đỉnh, `components=1`, total=0 |
| Nhiều đỉnh cô lập | Mỗi đỉnh là một cây của MSF |
| Một cạnh âm u–v | Có thể được chọn; Prim không cần trọng số không âm |
| Self-loop âm | Không thuộc MST/MSF vì tạo chu trình, không thêm đỉnh |
| Hai cạnh song song khác trọng số | Cạnh nhẹ hơn là ứng viên tốt hơn; có thể giữ hai cạnh hoặc gộp min nếu không cần ID |
| Hai cạnh cùng trọng số | Có thể có nhiều MST; tie-break chỉ để kết quả ổn định |
| Graph có chu trình | Hoàn toàn bình thường; chỉ cây kết quả không được có chu trình |
| Graph không liên thông | Không có một MST toàn graph; trả MSF hoặc báo không thể tạo MST theo yêu cầu |
| Graph có hướng | Không chạy trực tiếp Prim MST vô hướng; bài cây có hướng có thuật toán khác |
| Cạnh có trọng số `Long.MAX_VALUE` | Không nên dùng chính số này làm INF sentinel cho cạnh chưa tồn tại |
| Tổng trọng số vượt `long` | Báo overflow hoặc dùng số học lớn hơn; không tin kết quả tràn |
| Trọng số bằng nhau và parent khác nhau | Phải thống nhất cách chọn tie nếu muốn stdout ổn định |
| Nguồn khác 0 | Vẫn tìm MST tối ưu trên thành phần; các cạnh cụ thể có thể khác |
| Dữ liệu cạnh chỉ số ngoài `0..V-1` | Từ chối hoặc ánh xạ nhãn trước khi tạo graph |

### Trọng số cực âm không phải là “chu trình âm” theo nghĩa đường đi ngắn nhất

Trong MST, một cạnh âm vẫn có thể được chọn hoàn toàn hợp lệ. Ví dụ cạnh 6–7 trọng số -2 xuất hiện trong MSF và làm tổng nhỏ đi. Không cần chạy Bellman–Ford để kiểm tra chu trình âm cho Prim.

Bài toán shortest paths với chu trình âm là vấn đề khác: việc đi lặp quanh chu trình có thể làm tổng đường đi giảm vô hạn. Cây khung **không có chu trình**, nên tình huống “lặp chu trình âm vô hạn” không xảy ra trong tập phương án cây khung.

## 15. Lỗi thường gặp khi chọn cạnh trong Prim

1. Chọn **cạnh nhẹ nhất toàn graph** mà không xét có băng qua đường cắt S hay không.
2. Chỉ xem cạnh kề **đỉnh mới nhất**, bỏ cạnh tốt hơn đi ra từ một đỉnh S cũ.
3. Với lazy heap, pop một cạnh có cả hai đầu đã trong S rồi **vẫn thêm**, tạo chu trình.
4. Với eager, lưu `key[v]` bằng **tổng đường từ gốc tới v**, nhầm với Dijkstra.
5. Với eager, cập nhật key nhưng **không cập nhật parent** tương ứng.
6. Dùng parent của bản ghi heap **đã stale** sau khi key giảm, dẫn tới cạnh kết quả không khớp trọng số.
7. Giả định Java `PriorityQueue` tự có `decreaseKey(v)` và chỉ lưu một entry dù code thực tế push nhiều entry.
8. Đặt `INF=Long.MAX_VALUE` rồi không xử lý trường hợp cạnh có đúng trọng số đó.
9. So sánh trọng số bằng `(int)(a.weight-b.weight)`, có thể overflow.
10. Bỏ kiểm tra overflow ở tổng các cạnh, nhất là khi có trọng số âm/dương lớn.
11. Cho rằng Prim không chấp nhận cạnh âm vì nhớ điều kiện của Dijkstra.
12. Chọn self-loop cực nhẹ làm cạnh MST, dù nó **không mở rộng tập đỉnh**.
13. Không xét đỉnh cô lập, rồi báo số thành phần nhỏ hơn thực tế.
14. Cố trả một **MST toàn graph** dù graph không liên thông mà không thông báo đã chuyển sang MSF.
15. Dùng adjacency list vô hướng mà chỉ thêm cạnh `u→v`, làm mất chiều ngược của cạnh.
16. Chạy Prim trực tiếp cho đồ thị có hướng và gọi kết quả là minimum arborescence.
17. Không nhất quán tie-break khi test yêu cầu thứ tự cạnh xác định.
18. Gán `visited[v]=true` **ngay khi chỉ nhìn thấy cạnh vào heap**, làm chặn một cạnh tốt hơn trước khi v thật sự được chọn.
19. Trong lazy, để ứng viên có from không còn thuộc S do quản lý trạng thái sai; phải chỉ push từ đỉnh đã vào cây.
20. Quên cập nhật các khóa của neighbor sau khi thêm một đỉnh mới.
21. Dùng một key cũ của thành phần đã hoàn thành khi bắt đầu một thành phần mới mà không có bất biến bảo đảm sạch dữ liệu.
22. Tính O(V²) cho heap version mà không xét số thao tác heap, hoặc gán heap O(V) cho bản Java push duplicate.
23. Cho rằng MST đảm bảo **đường đi ngắn nhất từ gốc**, nhầm MST với shortest-path tree.
24. Kiểm tra chỉ tổng trọng số mà không xác minh tập cạnh kết quả **không chu trình và đủ thành phần**, có thể chấp nhận một kết quả tình cờ cùng tổng nhưng sai cấu trúc.
25. Sắp cạnh theo `int` cast khi trọng số `long`, mất độ chính xác thứ tự.
26. Dùng số lượng cạnh đúng V−1 làm bằng chứng duy nhất của MST mà không kiểm tra **liên thông, không chu trình và tối ưu**.

## 16. Kiểm thử và đối chiếu bằng oracle

Với graph nhỏ, có thể dùng **Kruskal + DSU** làm oracle độc lập:

1. Sắp các cạnh gốc theo trọng số tăng dần.
2. Bỏ self-loop.
3. Chọn cạnh nếu hai đầu thuộc **hai thành phần DSU khác nhau**, hợp nhất chúng.
4. Tổng trọng số Kruskal phải bằng tổng Prim nếu cùng graph vô hướng và cùng quy ước MSF.

Khi có nhiều MST do hòa trọng số, **không ép danh sách cạnh giống nhau**. Kiểm thêm:

- Mọi cạnh được chọn phải tồn tại trong đầu vào với đúng trọng số.
- Mỗi cạnh được chọn nối hai đỉnh khác nhau.
- Không có chu trình trong kết quả (có thể kiểm tra bằng DSU).
- Trong mỗi thành phần graph gốc, tất cả đỉnh liên thông nhờ cạnh kết quả.
- Số cạnh bằng \(V-c\), với c là số thành phần graph gốc.
- Tổng trọng số khớp oracle Kruskal, kể cả cạnh âm.
- Trên dữ liệu đúng như ví dụ, ba cách in cùng cạnh/tổng theo quy tắc tie đã công bố.

Các bài đặc biệt cần test: graph không cạnh, chỉ một đỉnh, tất cả trọng số bằng nhau, cạnh âm, self-loop âm, hai cạnh song song, đỉnh cô lập, chu trình nhiều cạnh, các thành phần có kích thước khác nhau, trọng số vượt miền số nguyên 32-bit và tổng có nguy cơ vượt 64-bit.

### Một phản ví dụ hữu ích để thử code lazy

Graph tam giác:

~~~text
0 --(2)-- 1
|         /
(1)     (1)
|      /
2 ----
~~~

Nếu Prim bắt đầu ở 0, chọn 0–2(1), rồi 2–1(1). Trong heap vẫn có cạnh 0–1(2) từ lúc xử lý đỉnh 0. Thuật toán **phải bỏ cạnh 0–1(2)** khi pop vì 1 đã thuộc S; nếu không, nó trả 3 cạnh cho graph 3 đỉnh và tạo chu trình.

## 17. Bài tập tự kiểm tra

**Bài 1 — Định nghĩa ứng viên.** Khi S={0,2} và các cạnh `0–1(4)`, `2–1(1)`, `0–2(3)`, cạnh nào hợp lệ để Prim chọn tiếp và vì sao?

*Đáp án:* **2–1(1)**. Nó băng qua cắt S–bên ngoài và nhẹ hơn 0–1(4). Cạnh 0–2(3) nằm hoàn toàn trong S, không phải ứng viên mở rộng.

**Bài 2 — Cạnh âm.** Có thể chọn cạnh 6–7 trọng số -2 vào MST thành phần {6,7} không?

*Đáp án:* **Có**. Cạnh âm hợp lệ trong MST, và đó là cạnh duy nhất nối hai đỉnh của thành phần này.

**Bài 3 — Self-loop âm.** Vì sao không chọn self-loop 1–1 trọng số -20?

*Đáp án:* Vì không thêm đỉnh mới, và chính nó là chu trình độ dài 1. Tập cạnh của một cây khung không thể chứa self-loop.

**Bài 4 — MSF.** Graph ví dụ có V=9 và 3 thành phần. MSF phải có bao nhiêu cạnh?

*Đáp án:* **\(9-3=6\)** cạnh, gồm 5 cạnh ở thành phần A, 1 cạnh ở B và 0 cạnh ở đỉnh cô lập 8.

**Bài 5 — Tổng trọng số.** Năm cạnh của MST thành phần A có trọng số 3,1,2,2,3. Tổng là bao nhiêu? Thêm cạnh 6–7(-2) được gì?

*Đáp án:* Thành phần A có tổng **11**, toàn MSF có tổng **9**.

**Bài 6 — Hòa trọng số.** Hai cạnh 3–5 và 4–5 đều nặng 3. Prim có buộc chọn cùng một cạnh trong mọi lần chạy không?

*Đáp án:* **Không.** Nếu đều là cạnh nhỏ nhất qua cắt tại thời điểm phù hợp, chọn một trong hai vẫn có thể tạo MST tối ưu. Tie-break quyết định đầu ra cụ thể.

**Bài 7 — Lazy heap.** Vì sao một cạnh pop ra từ heap cần được kiểm tra đích `inTree[to]` lần nữa?

*Đáp án:* Vì trong thời gian cạnh chờ heap, đỉnh đích có thể đã vào cây qua cạnh nhẹ hơn. Cạnh cũ trở thành nội bộ và thêm nó sẽ tạo chu trình.

**Bài 8 — Eager key.** Trong Prim, `key[v]` biểu diễn tổng đường đi từ gốc tới v hay trọng số cạnh nhẹ nhất nối v vào S?

*Đáp án:* **Trọng số một cạnh nhẹ nhất từ S tới v**. Không cộng thêm key[u] khi relax; cộng như Dijkstra sẽ làm sai bài.

**Bài 9 — Ba cấu trúc.** Nếu graph dày với V vừa phải, cách nào dễ cài và thường đáng cân nhắc?

*Đáp án:* **Quét ma trận** O(V²) có thể hợp lý và đơn giản. Với graph thưa, ưu tiên adjacency list và heap.

**Bài 10 — PriorityQueue Java.** Nếu eager cập nhật key bằng cách push một `KeyEntry` mới vào `PriorityQueue` mà không xóa entry cũ, heap có chắc O(V) không?

*Đáp án:* **Không.** Có thể có nhiều bản ghi cùng đỉnh, tổng O(E) bản ghi. Muốn heap O(V), cần indexed decrease-key hoặc cấu trúc tương đương.

**Bài 11 — Tie và tính đúng.** Nếu lazy và dense chọn các bộ cạnh khác nhau trên graph có nhiều trọng số bằng nhau, tiêu chí nào là chính để xác minh cả hai đúng?

*Đáp án:* Kiểm tính hợp lệ của cây/rừng, số cạnh \(V-c\), không chu trình, nối đúng các thành phần và **tổng trọng số tối ưu**. Danh sách cạnh không nhất thiết giống nhau.

**Bài 12 — Tính chất đường cắt.** Vì sao cạnh nhẹ nhất từ S sang bên ngoài là an toàn?

*Đáp án:* Dùng phép đổi cạnh: trong một MST bất kỳ đang chứa các cạnh đã chọn, nếu cạnh nhẹ nhất e chưa có, thêm e tạo chu trình; thay một cạnh f khác qua cắt bằng e không làm tổng tăng, vẫn thu MST chứa e.

**Bài 13 — So với Kruskal.** Prim và Kruskal chọn cạnh theo cùng thứ tự toàn graph không?

*Đáp án:* **Không.** Prim chỉ chọn cạnh nhẹ nhất qua đường cắt **cây đang tăng**, Kruskal xét cạnh toàn graph theo thứ tự trọng số và dùng DSU để tránh chu trình.

**Bài 14 — Vô hướng/hướng.** Có thể thêm cạnh vào adjacency list một chiều rồi coi kết quả Prim là MST vô hướng không?

*Đáp án:* **Không** nếu đồ thị đầu vào thực sự vô hướng mà thiếu chiều ngược. MST vô hướng cần biểu diễn cạnh nối cả hai đầu. Bài cây khung có hướng có định nghĩa và thuật toán khác.

**Bài 15 — Đồ thị rỗng.** Theo chính sách ví dụ Java, graph 0 đỉnh có mấy thành phần và tổng trọng số bao nhiêu?

*Đáp án:* **0 thành phần**, tổng **0**, không có cạnh.

**Bài 16 — Nhiều đỉnh cô lập.** Graph 3 đỉnh không có cạnh có bao nhiêu thành phần và cạnh trong MSF?

*Đáp án:* **3 cây một đỉnh**, 0 cạnh, tổng 0.

**Tổng kết:** Prim xây MST bằng cách mở rộng một tập đỉnh S, **mỗi lần chọn cạnh có trọng số nhỏ nhất băng qua đường cắt S–bên ngoài**. Chọn cạnh bằng **quét ma trận**, **min-heap cạnh lazy**, hoặc **khóa đỉnh eager** đều đúng nếu duy trì bất biến này. Cạnh cũ trong heap phải bị bỏ khi không còn nối tới đỉnh mới; khóa Prim là **trọng số một cạnh**, không phải khoảng cách từ gốc như Dijkstra. Cạnh âm được phép, self-loop bị loại, hòa trọng số có thể tạo nhiều MST; với graph không liên thông, lặp từ các gốc chưa chọn để có **MSF** và công bố rõ rằng không tồn tại một MST chung cho toàn graph.
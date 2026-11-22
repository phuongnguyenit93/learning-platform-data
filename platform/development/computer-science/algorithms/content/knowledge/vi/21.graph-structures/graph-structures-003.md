# Phát hiện trường hợp không có thứ tự tô-pô

## 1. Thứ tự tô-pô là gì và khi nào bài toán không có đáp án?

Cho đồ thị **có hướng** G=(V,E). Một **thứ tự tô-pô (topological ordering)** là một hoán vị của **toàn bộ các đỉnh** sao cho với **mọi cạnh có hướng u→v**, đỉnh u xuất hiện **trước** đỉnh v trong hoán vị ấy.

Ta có thể hiểu cạnh u→v là một **ràng buộc ưu tiên**: phải hoàn thành u trước khi được thực hiện v. Một đỉnh có thể có nhiều điều kiện tiên quyết; tất cả phải được đặt trước đỉnh đó.

Ví dụ các công việc:

~~~text
A -> C
B -> C
C -> D

Mot thu tu hop le: A, B, C, D
Mot thu tu hop le: B, A, C, D
Thu tu khong hop le: A, C, B, D
~~~

Ở ví dụ trên, A và B không bắt buộc phải so trước/sau nhau. Nhưng C phải đứng sau **cả A và B**, còn D phải đứng sau C.

**Câu hỏi chính của bài:** khi nào không tồn tại **bất kỳ** hoán vị nào thỏa tất cả các cạnh? Đáp án cốt lõi là:

> Đồ thị có hướng có thứ tự tô-pô **khi và chỉ khi** nó **không chứa chu trình có hướng** (directed cycle). Một đồ thị có hướng không chu trình được gọi là **DAG** (Directed Acyclic Graph).

Ví dụ không thể sắp thứ tự:

~~~text
A -> B
B -> C
C -> A
~~~

Nếu A phải trước B, B phải trước C và C phải trước A thì không có cách xếp tuyến tính nào đáp ứng cùng lúc. Bất kỳ thay đổi vị trí nào cũng vi phạm ít nhất một cạnh.

Ứng dụng: lịch học với môn tiên quyết, lập lịch công việc, dependency của thư viện, build system, workflow, thứ tự chạy các bước xử lý dữ liệu và nhiều bài kiểm tra phụ thuộc. Khi có chu trình, đôi khi vấn đề thực tế là **dữ liệu phụ thuộc mâu thuẫn** chứ không phải thuật toán sắp xếp sai.

**Phạm vi:** bài nói về **đồ thị có hướng**. Đồ thị vô hướng không có nghĩa thứ tự topo theo định nghĩa này trừ khi ta đã định hướng các cạnh thành ràng buộc đi trước/đi sau. Hai đỉnh nối bởi cạnh vô hướng không tự cho biết ai phải đứng trước.

## 2. Định lý nền tảng: tồn tại thứ tự topo khi và chỉ khi DAG

### Chiều 1: Có chu trình thì không thể có thứ tự topo

Giả sử có chu trình:

~~~text
v0 -> v1 -> v2 -> ... -> vk -> v0
~~~

Trong một thứ tự topo hợp lệ phải có:

~~~text
position(v0) < position(v1)
position(v1) < position(v2)
...
position(vk) < position(v0)
~~~

Theo tính bắc cầu, các bất đẳng thức dẫn tới position(v0) < position(v0), vô lý. Vì thế **chỉ cần có một chu trình có hướng ở bất kỳ thành phần nào** là không thể sắp tất cả đỉnh theo topo.

**Self-loop** u→u cũng là một chu trình độ dài một cạnh. Nó yêu cầu position(u)<position(u), nên làm bài toán không có đáp án ngay lập tức.

### Chiều 2: Không có chu trình thì luôn dựng được thứ tự topo

Một DAG hữu hạn, không rỗng luôn có ít nhất một đỉnh **bậc vào bằng 0**: đỉnh không có cạnh nào đi vào nó từ các đỉnh của DAG.

Lý do: nếu mọi đỉnh đều có ít nhất một cạnh đi vào, chọn một đỉnh và liên tục đi ngược theo một cạnh đi vào. Đồ thị có hữu hạn đỉnh nên ta sẽ lặp lại một đỉnh, tạo thành chu trình có hướng, mâu thuẫn với DAG.

Vì thế ta có thể:

1. Chọn một đỉnh có indegree=0 và đặt đầu thứ tự.
2. Xóa đỉnh ấy cùng các cạnh đi ra khỏi nó.
3. Lặp lại trên đồ thị còn lại.

Xóa đỉnh và cạnh không thể tạo thêm chu trình, nên phần còn lại vẫn là DAG; nếu còn đỉnh, lại có đỉnh indegree=0. Quá trình cuối cùng lấy ra **mọi đỉnh** và tạo một thứ tự topo.

Đây chính là nền tảng của **thuật toán Kahn**, đồng thời chứng minh rằng không có chu trình thì chắc chắn tồn tại thứ tự topo.

**Kết luận:** việc phát hiện “không có thứ tự topo” tương đương với **phát hiện chu trình có hướng**, nhưng ta có nhiều cách thực hiện: Kahn cho biết thiếu thứ tự thông qua số đỉnh đã xử lý, còn DFS ba màu có thể cho ra một chu trình làm bằng chứng.

## 3. Kahn: kiểm tra topo bằng bậc vào và hàng đợi

**Indegree[v]** là số cạnh có hướng đi **vào** v từ các đỉnh hiện còn trong đồ thị. Nếu có **hai cạnh song song** u→v, cả hai đều góp một đơn vị vào indegree[v]; phải giảm đúng hai lần khi xử lý u.

Thuật toán Kahn:

~~~text
topologicalSort(n, edges):
    indegree[v] = 0 for every vertex v

    for each edge (u, v):
        indegree[v]++

    queue = FIFO
    for v from 0 to n-1:
        if indegree[v] == 0:
            queue.addLast(v)

    order = []

    while queue is not empty:
        u = queue.removeFirst()
        order.add(u)

        for v in outgoingNeighbors[u]:
            indegree[v]--
            if indegree[v] == 0:
                queue.addLast(v)

    if order.size() == n:
        return "EXISTS", order
    else:
        return "NO TOPOLOGICAL ORDER", order as partial result
~~~

Bản triển khai thực tế thường dùng **danh sách kề** (adjacency list) để truy cập các cạnh đi ra từ u.

### Tại sao phải tính bậc vào chứ không phải bậc ra?

Thứ tự topo yêu cầu mọi **tiền nhiệm** của v phải được lấy ra trước v. Khi indegree[v] trong đồ thị còn lại bằng 0, không có công việc chưa xử lý nào còn yêu cầu đứng trước v; do đó v có thể an toàn đi tiếp.

Outdegree=0 là đặc tính của đỉnh không cần làm gì sau nó, phù hợp nếu muốn xây thứ tự từ cuối về đầu bằng một thuật toán khác. Nhưng **Kahn chuẩn** lấy đỉnh indegree=0 và thêm vào kết quả **từ đầu đến cuối**.

### Tại sao giảm bậc vào khi lấy đỉnh khỏi queue?

Khi u đã được đặt vào thứ tự, ràng buộc u→v được xem như đã đáp ứng, do đó cạnh ấy được xóa khỏi bài toán còn lại. Mỗi cạnh u→v tương ứng với một lần giảm indegree[v]. Khi tất cả cạnh đi vào v từ các đỉnh chưa xử lý đã biến mất, indegree[v] trở về 0 và v được đưa vào queue.

Đỉnh đã nằm trong queue chỉ được thêm đúng lúc indegree chuyển từ số dương sang 0, nên mỗi đỉnh được enqueue tối đa một lần nếu khởi tạo và cập nhật đúng.

### Điều kiện phát hiện thất bại

**Nếu hàng đợi rỗng mà order vẫn chưa có đủ n đỉnh**, vẫn còn những đỉnh chưa được xử lý, nhưng không có đỉnh nào có bậc vào 0. Theo định lý ở trên, phần đồ thị còn lại chứa một chu trình có hướng. Bởi vậy không tồn tại thứ tự topo của toàn bộ đồ thị ban đầu.

Điểm kiểm tra đúng là **order.size()==n**, không phải chỉ “đã lấy ra một đỉnh” hoặc “hàng đợi đang rỗng”. Hàng đợi luôn rỗng khi kết thúc, kể cả trong trường hợp thành công; kết quả được quyết định bởi **số đỉnh đã lấy ra**.

## 4. Mô phỏng Kahn trên một DAG có nhiều nguồn ban đầu

Cho đồ thị có hướng 7 đỉnh 0..6 và các cạnh:

~~~text
0 -> 1
0 -> 2
1 -> 3
2 -> 3
3 -> 4
5 -> 6
~~~

Đỉnh 0 và 5 đều có indegree=0; đỉnh 6 không liên hệ với chuỗi 0→...→4 ngoài cạnh đi từ 5. Danh sách kề theo thứ tự cạnh nhập:

~~~text
0: [1,2]
1: [3]
2: [3]
3: [4]
4: []
5: [6]
6: []
~~~

Indegree ban đầu:

~~~text
vertex:   0 1 2 3 4 5 6
indegree: 0 1 1 2 1 0 1
queue:    [0,5]
~~~

Mô phỏng:

| Lượt | Lấy u | Cập nhật indegree | Queue sau lượt | Order |
| --- | --- | --- | --- | --- |
| 1 | 0 | 1:1→0, 2:1→0 | [5,1,2] | [0] |
| 2 | 5 | 6:1→0 | [1,2,6] | [0,5] |
| 3 | 1 | 3:2→1 | [2,6] | [0,5,1] |
| 4 | 2 | 3:1→0 | [6,3] | [0,5,1,2] |
| 5 | 6 | Không có cạnh đi ra | [3] | [0,5,1,2,6] |
| 6 | 3 | 4:1→0 | [4] | [0,5,1,2,6,3] |
| 7 | 4 | Không có cạnh đi ra | [] | [0,5,1,2,6,3,4] |

Đã lấy ra 7/7 đỉnh nên **tồn tại thứ tự topo**. Một kết quả là:

~~~text
[0, 5, 1, 2, 6, 3, 4]
~~~

Kiểm từng cạnh:

- 0 đứng trước 1 và 2.
- Cả 1,2 đứng trước 3.
- 3 đứng trước 4.
- 5 đứng trước 6.

Tất cả đều thỏa. Có thể còn nhiều thứ tự khác, ví dụ đổi chỗ 0 và 5, hoặc thay đổi cách ưu tiên các đỉnh indegree=0. **Không có thứ tự topo duy nhất** không đồng nghĩa “không có thứ tự topo”; miễn là có một hoán vị hợp lệ thì kết quả là **có**.

### Cách hiểu queue và tính tất định

Nếu đưa các đỉnh indegree=0 vào FIFO theo thứ tự id tăng dần, và duyệt láng giềng theo đúng thứ tự danh sách, thuật toán Kahn trả một thứ tự **tất định với biểu diễn input đó**.

Nếu thay FIFO bằng priority queue lấy đỉnh id nhỏ nhất, ta thường có **thứ tự topo nhỏ nhất theo thứ tự từ điển** khi id biểu diễn thứ tự mong muốn; độ phức tạp tăng thêm logarithmic. Cả hai đều đúng cho bài kiểm tra có/không. Không cần áp dụng priority queue nếu đề chỉ hỏi tồn tại.

## 5. Kahn dừng sớm khi có chu trình có hướng

Xét đồ thị có hướng 5 đỉnh:

~~~text
0 -> 1
1 -> 2
2 -> 1
2 -> 3
3 -> 4
~~~

Ở đây 1→2→1 là chu trình hai cạnh. Cạnh 2→3→4 là một “đuôi” đi ra từ chu trình.

Indegree ban đầu:

~~~text
vertex:   0 1 2 3 4
indegree: 0 2 1 1 1
queue:    [0]
~~~

Kahn lấy đỉnh 0 và xóa cạnh 0→1. Khi ấy:

~~~text
processed order = [0]

indegree con lai:
1: 1      (canh 2 -> 1)
2: 1      (canh 1 -> 2)
3: 1      (canh 2 -> 3)
4: 1      (canh 3 -> 4)

queue = []
~~~

Không còn đỉnh indegree=0. Kahn dừng với **1/5 đỉnh được xử lý**, suy ra **không có thứ tự topo** cho cả đồ thị.

Để chứng minh bằng một nhân chứng cụ thể, chỉ cần chỉ ra:

~~~text
1 -> 2 -> 1
~~~

Chu trình tạo mâu thuẫn “1 phải trước 2” và “2 phải trước 1”. Không cần vẽ hết mọi đường đi của đồ thị.

### Tại sao chỉ cần một chu trình?

Thứ tự topo phải thỏa **mọi** cạnh trên toàn đồ thị. Một chu trình ở một thành phần bất kỳ tạo ra ràng buộc không thể thỏa, nên dù phần đồ thị khác hoàn toàn là DAG, **toàn đồ thị vẫn không có thứ tự topo**.

Ví dụ hai nhóm đỉnh rời nhau: nhóm A là DAG, nhóm B có chu trình. Kahn có thể xử lý hết nhóm A nhưng sẽ kẹt ở B; tổng order vẫn ngắn hơn n. Điều kiện kiểm tra phải áp dụng cho **toàn bộ số đỉnh**, không chỉ những đỉnh reachable từ đỉnh 0.

## 6. Những đỉnh chưa được xử lý không nhất thiết đều nằm trên chu trình

Một lỗi rất thường gặp khi báo cáo nguyên nhân là phát biểu: “mọi đỉnh còn lại sau Kahn đều thuộc chu trình”. Điều này **không đúng**.

Trong ví dụ:

~~~text
1 -> 2 -> 1
     |
     v
     3 -> 4
~~~

Kahn không xử lý được các đỉnh 1,2,3,4. Nhưng:

- **1 và 2** thực sự thuộc chu trình 1→2→1.
- **3 và 4** chỉ nằm **sau** chu trình theo hướng cạnh. Chúng bị giữ lại vì chưa thể bỏ các cạnh đi vào từ những đỉnh còn kẹt.
- Không có đường từ 3 hoặc 4 quay lại 1 hoặc 2 trong đồ thị ví dụ, nên 3,4 không thuộc chu trình này.

Vì vậy, một danh sách **unprocessed/residual** là tập các đỉnh Kahn chưa lấy ra, **không phải tập chính xác những đỉnh nằm trên chu trình**. Tập residual có thể gồm cả những đỉnh phụ thuộc **xuôi** từ một chu trình và có thể có nhiều chu trình.

### Giải thích bằng bậc vào còn lại

Khi queue rỗng mà còn residual, mọi đỉnh residual có indegree dương tính **trong đồ thị residual**. Nếu lần theo những cạnh đi vào này trong một tập hữu hạn, ta phải lặp một đỉnh và tìm được chu trình. Nhưng lập luận này chỉ đảm bảo **tồn tại ít nhất một chu trình trong residual**, không nói mọi đỉnh residual đều nằm trong chu trình.

Muốn xác định chính xác **những đỉnh thuộc một hoặc nhiều chu trình**, có thể tìm **thành phần liên thông mạnh (SCC)**. Một SCC có ít nhất hai đỉnh luôn chứa chu trình, còn SCC một đỉnh chỉ chứa chu trình nếu có self-loop. Nếu chỉ cần biết có tồn tại thứ tự topo hay không, Kahn là đủ; không nhất thiết phải tính SCC.

### Kết quả Kahn khi thất bại có dùng được không?

Danh sách partial order do Kahn tạo ra vẫn có thể hữu ích để quan sát công việc đã đủ điều kiện chạy. Nhưng đó **không phải một thứ tự topo của toàn bộ đồ thị**; không được trả nó như nghiệm hoàn chỉnh. Trong mã Java, API trả cả cờ exists và partial order để phân biệt.

Nếu muốn có một giải thích trực quan “vì sao không làm được”, nên bổ sung một chu trình cụ thể thay vì chỉ in residual.

## 7. DFS ba màu: phát hiện chu trình trực tiếp

Một cách khác là **Depth-First Search (DFS)** với ba trạng thái màu cho mỗi đỉnh:

| Màu | Ý nghĩa |
| --- | --- |
| WHITE = 0 | Chưa bắt đầu duyệt đỉnh này |
| GRAY = 1 | Đang nằm trên stack đệ quy DFS hiện tại, chưa xử lý xong |
| BLACK = 2 | Đã duyệt xong mọi cạnh đi ra của đỉnh |

Khi vào dfs(u), đặt color[u]=GRAY. Duyệt từng cạnh u→v:

1. Nếu v WHITE, gọi dfs(v) và ghi parent[v]=u.
2. Nếu v GRAY, có một cạnh đi **ngược tới tổ tiên đang mở** trên stack hiện tại: đó là một **back edge**, và tồn tại chu trình có hướng.
3. Nếu v BLACK, v đã xử lý xong. Chỉ thấy một cạnh tới BLACK **không** chứng minh có chu trình, nên không được báo lỗi.
4. Nếu không thấy chu trình trong mọi nhánh, đặt color[u]=BLACK rồi trả về.

~~~text
dfs(u):
    color[u] = GRAY

    for v in outgoing[u]:
        if color[v] == WHITE:
            parent[v] = u
            if dfs(v) detects cycle:
                return true
        else if color[v] == GRAY:
            return true

    color[u] = BLACK
    return false

for every vertex u:
    if color[u] == WHITE and dfs(u) detects cycle:
        return NO TOPOLOGICAL ORDER

return HAS TOPOLOGICAL ORDER
~~~

**Vòng ngoài duyệt mọi đỉnh bắt buộc** vì đồ thị có thể có nhiều thành phần, hoặc có một chu trình ở thành phần không reachable từ đỉnh đầu tiên.

### Vì sao cạnh tới GRAY là chu trình?

Nếu v đang GRAY khi dfs(u) duyệt cạnh u→v, v là một đỉnh đang nằm trên **đường đệ quy hiện tại**, và nó là tổ tiên của u (hoặc chính u nếu self-loop). Các cạnh cây DFS cung cấp một đường **v→...→u**, rồi cạnh u→v khép lại thành chu trình có hướng.

Nếu v là BLACK, nó không còn nằm trên stack hiện tại. Cạnh u→v có thể là cạnh tiến hoặc cạnh chéo trong cấu trúc DFS; nó không tự tạo chu trình.

### Tại sao không dùng visited Boolean một màu?

Nếu chỉ có visited[v]=true cho cả “đã vào nhưng chưa ra” và “đã duyệt xong”, không thể phân biệt:

- v là tổ tiên vẫn đang trên stack → cạnh u→v báo chu trình.
- v là đỉnh đã xử lý xong ở nhánh khác → cạnh u→v hoàn toàn bình thường.

Ví dụ DAG hình thoi 0→1, 0→2, 1→3, 2→3. DFS qua 1 sẽ thăm 3, rồi quay lại; sau đó qua 2 lại gặp 3 đã visited. Nếu cứ “gặp visited là cycle” thì sẽ báo **chu trình giả** dù đồ thị là DAG.

Hai mảng visited và inStack tương đương với color ba trạng thái; color thường gọn và dễ diễn giải.

## 8. Dựng một chu trình cụ thể bằng DFS và parent

Kahn kết luận được “không có thứ tự topo” rất đơn giản, nhưng không cho ngay một chu trình làm bằng chứng. Khi cần báo cáo lỗi dependency, ta có thể dùng **DFS ba màu** để dựng **cycle witness**.

Khi đang ở u và tìm thấy cạnh u→v với color[v]=GRAY:

1. Có đường cây DFS từ v tới u, với các parent.
2. Bắt đầu tại u, đi ngược parent cho tới khi gặp v.
3. Đảo thứ tự để có đường v→...→u.
4. Thêm v lần nữa ở cuối để biểu diễn cạnh u→v khép chu trình.

Ví dụ chu trình 1→2→1:

~~~text
Khi dfs(2) gap canh 2 -> 1:
color[1] = GRAY

parent[2] = 1
duong truy nguoc: [2,1]
dao thu tu:       [1,2]
them dinh dau:    [1,2,1]
~~~

Ta thường in **đỉnh đầu lặp lại ở cuối** để người đọc thấy chu trình đóng. Đối với self-loop u→u, witness là [u,u] – có hai lần xuất hiện của cùng một đỉnh để biểu diễn **một cạnh quay về chính nó**.

**Quan trọng:** mảng parent ở đây là **cha trong cây DFS**, không phải mảng parent của BFS đường đi ngắn nhất. Hai mảng có thể cùng tên nhưng được tạo trong hai thuật toán khác nhau, phục vụ mục đích khác nhau.

### Tính hợp lệ của witness

Nếu kết quả là [c0,c1,...,ck] với c0=ck, cần xác minh:

- Mọi cặp liên tiếp (ci,ci+1) là một **cạnh có hướng** thực sự trong E.
- Các đỉnh bên trong không bị lặp đối với một chu trình đơn do kỹ thuật back edge này tạo ra.
- k≥1 (self-loop được phép).
- Không nhầm hướng cạnh khi lần theo parent.

Trong đồ thị lớn, có thể chỉ cần tìm **một** witness, không cần liệt kê tất cả chu trình: số chu trình có thể cực lớn, khiến yêu cầu liệt kê tất cả vượt xa chi phí O(V+E) của kiểm tra tồn tại.

## 9. So sánh Kahn và DFS ba màu

Cả hai đều xác định đúng liệu đồ thị có thứ tự topo hay không trong **O(V+E)** thời gian khi dùng danh sách kề. Sự khác biệt chủ yếu nằm ở cách giải thích kết quả và tài nguyên.

| Tiêu chí | Kahn – indegree + queue | DFS ba màu |
| --- | --- | --- |
| Cơ chế | Liên tục lấy đỉnh không còn tiền nhiệm | Phát hiện cạnh quay lại tổ tiên trên stack |
| Kết quả khi DAG | Sinh trực tiếp một thứ tự topo | Có thể tạo topo bằng cách đảo thứ tự hoàn tất DFS |
| Kết quả khi có chu trình | order.size() nhỏ hơn V | Gặp cạnh tới GRAY |
| Dữ liệu làm bằng chứng | Residual chứa ít nhất một chu trình | Có thể dựng chính chu trình qua parent |
| Bộ nhớ phụ | O(V) indegree, queue, order | O(V) color, parent, stack |
| Chiều sâu ngăn xếp | Vòng lặp, không đệ quy | Đệ quy có thể sâu O(V) |
| Thứ tự lựa chọn | Phụ thuộc thứ tự zero-indegree, queue | Phụ thuộc thứ tự DFS |
| Nhiều thành phần | Seed mọi đỉnh indegree=0 | Vòng ngoài qua mọi đỉnh chưa thăm |

Nếu cần **lịch thực hiện các công việc**, Kahn rất tự nhiên. Nếu cần **chỉ ra quan hệ phụ thuộc vòng**, DFS ba màu với parent thuận tiện. Có thể kết hợp: chạy Kahn để xây lịch; nếu thất bại, chạy DFS để cung cấp chu trình cụ thể.

### DFS có thể tạo topo trong DAG

Nếu DFS không phát hiện chu trình, ghi một đỉnh vào danh sách **sau khi đã duyệt xong tất cả cạnh đi ra của nó**. Đảo danh sách thời điểm hoàn tất (reverse postorder) sẽ cho một thứ tự topo. Nhưng nếu DFS phát hiện chu trình, danh sách hoàn tất không thể trở thành topo hợp lệ dù có đảo.

**Không được** chỉ chạy DFS từ đỉnh 0 rồi kết luận toàn đồ thị không chu trình, vì chu trình có thể nằm ở thành phần không đi tới từ 0.

## 10. Java 17 – chương trình đầy đủ kiểm tra topo và dựng chu trình

Mã sau cung cấp:

1. **directedGraph:** dựng danh sách kề đúng hướng từ các cạnh (u,v) có nghĩa u→v, kiểm tra miền chỉ số.
2. **topologicalSortKahn:** trả cờ exists, thứ tự đã xử lý và các đỉnh unprocessed khi thất bại.
3. **findDirectedCycle:** DFS ba màu và parent để trả **một chu trình cụ thể**, hoặc danh sách rỗng nếu DAG.
4. Một hàm main chạy DAG, đồ thị có chu trình, self-loop, cạnh song song, đồ thị rỗng và lỗi cạnh ngoài miền.

**Quy ước output:** Nếu exists=false, trường order là **partial order**, không phải một topo của toàn đồ thị. Trường unprocessed là các đỉnh chưa được Kahn xử lý, **không khẳng định mọi đỉnh ấy thuộc chu trình**. Cycle witness do DFS trả về có cùng đỉnh đầu/cuối.

Lưu toàn bộ mã trong tệp **TopologicalFailureDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class TopologicalFailureDemo {

    record TopoResult(
            boolean exists,
            List<Integer> order,
            List<Integer> unprocessed) {}

    // Moi canh int[]{u,v} co nghia u -> v.
    static List<List<Integer>> directedGraph(int n, int[][] edges) {
        if (n < 0) {
            throw new IllegalArgumentException(
                    "n must be nonnegative");
        }
        Objects.requireNonNull(edges, "edges");

        List<List<Integer>> graph = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            graph.add(new ArrayList<>());
        }

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException("invalid edge");
            }
            int u = edge[0];
            int v = edge[1];
            if (u < 0 || u >= n || v < 0 || v >= n) {
                throw new IllegalArgumentException(
                        "vertex out of range");
            }
            graph.get(u).add(v);
        }
        return graph;
    }

    static TopoResult topologicalSortKahn(
            List<List<Integer>> graph) {
        Objects.requireNonNull(graph, "graph");
        int n = graph.size();
        int[] indegree = new int[n];

        for (List<Integer> outgoing : graph) {
            for (int v : outgoing) {
                indegree[v]++;
            }
        }

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (int v = 0; v < n; v++) {
            if (indegree[v] == 0) {
                queue.addLast(v);
            }
        }

        List<Integer> order = new ArrayList<>();
        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            order.add(u);

            for (int v : graph.get(u)) {
                indegree[v]--;
                if (indegree[v] == 0) {
                    queue.addLast(v);
                }
            }
        }

        List<Integer> unprocessed = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            if (indegree[v] > 0) {
                unprocessed.add(v);
            }
        }

        return new TopoResult(
                order.size() == n,
                List.copyOf(order),
                List.copyOf(unprocessed));
    }

    // Tra ve mot chu trinh gom cac dinh, lap lai dinh dau.
    static List<Integer> findDirectedCycle(
            List<List<Integer>> graph) {
        Objects.requireNonNull(graph, "graph");
        int n = graph.size();
        byte[] color = new byte[n];  // 0=WHITE,1=GRAY,2=BLACK
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        List<Integer> cycle = new ArrayList<>();
        for (int start = 0; start < n; start++) {
            if (color[start] == 0 &&
                    dfsCycle(start, graph, color, parent, cycle)) {
                break;
            }
        }
        return List.copyOf(cycle);
    }

    private static boolean dfsCycle(
            int u,
            List<List<Integer>> graph,
            byte[] color,
            int[] parent,
            List<Integer> cycle) {

        color[u] = 1; // GRAY: dang tren recursion stack.
        for (int v : graph.get(u)) {
            if (color[v] == 0) {
                parent[v] = u;
                if (dfsCycle(v, graph, color, parent, cycle)) {
                    return true;
                }
            } else if (color[v] == 1) {
                // v la to tien GRAY. Duong v->...->u + u->v.
                List<Integer> reversed = new ArrayList<>();
                for (int at = u; at != v; at = parent[at]) {
                    reversed.add(at);
                }
                reversed.add(v);
                Collections.reverse(reversed);
                reversed.add(v);
                cycle.addAll(reversed);
                return true;
            }
        }
        color[u] = 2; // BLACK: da xu ly xong.
        return false;
    }

    public static void main(String[] args) {
        List<List<Integer>> dag = directedGraph(7,
                new int[][]{
                        {0, 1}, {0, 2}, {1, 3},
                        {2, 3}, {3, 4}, {5, 6}
                });
        TopoResult d = topologicalSortKahn(dag);
        System.out.println("DAG exists = " + d.exists());
        System.out.println("DAG order = " + d.order());
        System.out.println("DAG unprocessed = " + d.unprocessed());
        System.out.println("DAG cycle witness = " +
                findDirectedCycle(dag));

        List<List<Integer>> cyclic = directedGraph(5,
                new int[][]{
                        {0, 1}, {1, 2}, {2, 1},
                        {2, 3}, {3, 4}
                });
        TopoResult c = topologicalSortKahn(cyclic);
        System.out.println("Cycle exists = " + c.exists());
        System.out.println("Cycle processed prefix = " + c.order());
        System.out.println("Cycle unprocessed = " + c.unprocessed());
        System.out.println("Cycle witness = " +
                findDirectedCycle(cyclic));

        List<List<Integer>> selfLoop = directedGraph(2,
                new int[][]{{0, 0}, {0, 1}});
        System.out.println("Self-loop exists = " +
                topologicalSortKahn(selfLoop).exists());
        System.out.println("Self-loop witness = " +
                findDirectedCycle(selfLoop));

        List<List<Integer>> parallel = directedGraph(3,
                new int[][]{{0, 1}, {0, 1}, {1, 2}});
        TopoResult p = topologicalSortKahn(parallel);
        System.out.println("Parallel edges exists = " + p.exists());
        System.out.println("Parallel edges order = " + p.order());

        TopoResult empty = topologicalSortKahn(
                directedGraph(0, new int[0][2]));
        System.out.println("Empty DAG exists = " + empty.exists());
        System.out.println("Empty order = " + empty.order());

        try {
            directedGraph(2, new int[][]{{0, 2}});
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid edge: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac TopologicalFailureDemo.java
java TopologicalFailureDemo
~~~

**Stdout chính xác** với các cạnh được thêm đúng thứ tự trong mã:

~~~text
DAG exists = true
DAG order = [0, 5, 1, 2, 6, 3, 4]
DAG unprocessed = []
DAG cycle witness = []
Cycle exists = false
Cycle processed prefix = [0]
Cycle unprocessed = [1, 2, 3, 4]
Cycle witness = [1, 2, 1]
Self-loop exists = false
Self-loop witness = [0, 0]
Parallel edges exists = true
Parallel edges order = [0, 1, 2]
Empty DAG exists = true
Empty order = []
Invalid edge: vertex out of range
~~~

### Giải thích các hàm Java

**directedGraph:** chỉ thêm cạnh một chiều u→v, không thêm v→u. Mỗi cạnh phải có đúng hai đầu nằm trong [0,n). Cạnh trùng vẫn được giữ; self-loop cũng được giữ để phát hiện chu trình thật.

**topologicalSortKahn:** mỗi cạnh đi vào v làm indegree[v] tăng một. Khởi tạo queue theo đỉnh id tăng dần; khi lấy u, giảm bậc vào **cho từng cạnh** trong graph.get(u). Đỉnh v chỉ được enqueue khi indegree[v] vừa về 0. Vì vậy cạnh song song u→v được trừ từng lần chứ không gộp sai.

Nếu lấy được n đỉnh, exists=true và order là topo hợp lệ. Nếu chưa đủ, exists=false, order chỉ là prefix đã xử lý; unprocessed chứa các đỉnh còn indegree dương sau khi loại hết đỉnh xử lý được. Không có chuyện trả partial prefix như một lịch trình đã giải xong mọi dependency.

**findDirectedCycle:** dùng color ba trạng thái, duyệt mọi nguồn DFS chưa thăm. Khi cạnh u→v gặp v màu GRAY, đường parent từ u quay về tổ tiên v cùng cạnh u→v tạo witness. Code đảo các đỉnh parent để in chu trình đúng hướng, ví dụ [1,2,1]. Nếu v==u (self-loop), witness là [u,u]. Nếu DAG, không có cạnh tới GRAY và kết quả là [].

**Kết quả Java là ví dụ có thể chạy độc lập**, không phải từng hàm giả mã riêng lẻ phải ghép từ nhiều ví dụ. Vì tìm chu trình dùng đệ quy, đồ thị có đường rất dài có thể gây StackOverflowError trong Java; khi đó nên dùng DFS lặp với stack frame hoặc Kahn nếu chỉ cần kết luận có/không.

### Hợp đồng và những giới hạn của mã

- Input dùng **chỉ số đỉnh 0..n-1**. Với tên công việc như "build-api", "run-tests", cần lập map tên→id trước khi gọi, rồi ánh xạ kết quả id về tên.
- Hai hàm phân tích nhận danh sách kề đã tồn tại, giả định các chỉ số đỉnh là hợp lệ. Builder kiểm tra dữ liệu cạnh nên ví dụ đáp ứng giả định; API thư viện công khai nên xác thực graph bên ngoài trước khi phân tích.
- Nếu người gọi sửa danh sách kề giữa lần kiểm tra Kahn và lần tìm chu trình, hai kết quả có thể thuộc **hai phiên bản đồ thị khác nhau**. Phải giữ graph ổn định giữa các thao tác muốn so sánh.
- DFS tìm witness **có thể dừng ngay khi phát hiện chu trình**, vì chỉ cần một nhân chứng để phủ nhận thứ tự topo. Những color còn GRAY trên đường đệ quy khi trả true không ảnh hưởng kết quả vì thuật toán dừng; không dùng mảng color ấy như kết quả phân loại hoàn tất của toàn graph.
- Đồ thị rỗng n=0 là DAG theo định nghĩa và có đúng một thứ tự topo là danh sách rỗng. Đây là trường hợp khác với “không có thứ tự topo”.
- Khi có số cạnh cực lớn, các int indegree có giới hạn biểu diễn; với dữ liệu thông thường n,m trong giới hạn bộ nhớ Java thì phù hợp, còn khi xây đồ thị siêu lớn cần xét nguy cơ tràn số/thiếu bộ nhớ.

## 11. Chứng minh Kahn phát hiện đúng trường hợp không có thứ tự topo

### Bất biến bậc vào

Sau mỗi lượt, gọi R là tập đỉnh **chưa được lấy ra**. Mảng indegree[v] với v∈R bằng số cạnh đi vào v **từ các đỉnh cũng ở R**.

- Ban đầu R=V, indegree được tính từ mọi cạnh nên bất biến đúng.
- Khi lấy u khỏi R, các cạnh đi ra từ u tới những v còn ở R bị loại. Mỗi cạnh như thế làm indegree[v] giảm một. Những cạnh giữa các đỉnh còn lại không đổi.
- Vì vậy sau khi xử lý u, indegree vẫn biểu diễn đúng số tiền nhiệm chưa hoàn tất.

Một đỉnh được enqueue khi indegree bằng 0, tức không có tiền nhiệm chưa xử lý. Đặt nó vào thứ tự không thể vi phạm cạnh từ một đỉnh chưa xử lý tới nó.

### Nếu Kahn lấy đủ n đỉnh

Xét bất kỳ cạnh u→v. Khi v được lấy ra, u đã phải được lấy ra trước đó; nếu u còn ở R, cạnh u→v sẽ khiến indegree[v]>0 và v không thể vào queue. Do đó u đứng trước v, và order thỏa **mọi cạnh**. Order chứa đủ n đỉnh nên là một thứ tự topo.

### Nếu Kahn dừng khi order chưa đủ n

Queue rỗng, nhưng R không rỗng. Do bất biến, **mọi đỉnh trong R có indegree dương trong đồ thị con do R tạo ra**. Theo lập luận lấy liên tiếp các cạnh đi vào trên đồ thị hữu hạn, phải có chu trình có hướng nằm trong R. Theo định lý phần 2, graph có chu trình thì không thể có topo. Vậy exists=false là đúng.

### Nếu graph là DAG

DAG hữu hạn không rỗng luôn có một đỉnh indegree=0. Mỗi lần Kahn xóa một đỉnh, phần còn lại vẫn DAG, nên nếu còn đỉnh thì queue sẽ có ít nhất một đỉnh đủ điều kiện. Thuật toán không thể dừng sớm; cuối cùng lấy đủ n đỉnh và exists=true.

**Độ đầy đủ:** Kahn không báo thất bại trên DAG, và không báo thành công trên graph có chu trình. Đây là hai vế cần thiết để dùng order.size()!=n làm phép kiểm tra không tồn tại topo.

## 12. Chứng minh DFS ba màu phát hiện đúng chu trình

Giữ bất biến: color[u]=GRAY đúng khi u **đang nằm trên đường gọi đệ quy DFS hiện tại**, còn color[u]=BLACK khi đã xét xong mọi cạnh đi ra và rời khỏi stack.

**Có back edge u→v đến GRAY:** v là tổ tiên của u trên đường DFS, nên có đường có hướng từ v qua các cạnh cây DFS đến u. Thêm cạnh u→v tạo một chu trình. Vì vậy cứ phát hiện một cạnh tới GRAY, kết luận graph có chu trình là đúng.

**Có chu trình thì DFS nhất định gặp back edge:** giả sử có một chu trình. Lấy đỉnh đầu tiên của chu trình được DFS phát hiện trong lần duyệt các đỉnh của chu trình. Từ đỉnh đó, đường các cạnh tiếp theo dọc theo chu trình đưa ta tới những đỉnh WHITE mới trước khi hoàn tất nhánh, hoặc tới một đỉnh GRAY đã nằm trên stack. Cuối cùng cạnh khép chu trình sẽ đi tới đỉnh đang GRAY (có thể là đỉnh đã khởi đầu), làm DFS báo chu trình.

Có thể diễn giải bằng lập luận phản chứng: nếu DFS kết thúc và không có cạnh đến GRAY, thứ tự **ngược thời điểm hoàn tất** của DFS là một thứ tự topo. Nhưng đồ thị có chu trình không thể có topo, nên giả thiết không gặp back edge là sai.

**Chu trình witness:** parent được gán khi đi từ u sang một v WHITE, nên mỗi parent[v]→v là cạnh trong đồ thị. Khi gặp u→v với v GRAY, đường parent từ v tới u là một đường trong cây DFS; nối cạnh u→v cho ra danh sách cạnh có hướng thực, khép vòng. Vì thế witness là một bằng chứng có thể tự kiểm tra độc lập.

## 13. Độ phức tạp và khả năng mở rộng

Với V đỉnh, E cạnh và danh sách kề:

| Phương pháp | Thời gian | Bộ nhớ phụ | Ghi chú |
| --- | --- | --- | --- |
| Kahn | O(V+E) | O(V) | indegree, queue, order |
| DFS ba màu | O(V+E) | O(V) | color, parent, recursion stack và witness |
| Kahn rồi DFS nếu thất bại | O(V+E) | O(V) | Hằng số có thể tăng, nhưng vẫn cùng bậc |
| Kiểm tra mọi cạnh của thứ tự đề xuất | O(V+E) | O(V) | Tạo position[v], quét các cạnh |

**Vì sao O(V+E)?** Tạo/khởi tạo mảng tốn O(V); tính indegree duyệt mọi cạnh O(E). Kahn lấy mỗi đỉnh tối đa một lần và duyệt mỗi cạnh đi ra đúng một lượt khi lấy đỉnh tương ứng. DFS cũng thăm mỗi đỉnh tối đa một lần và duyệt mỗi cạnh tối đa một lần trong nhánh kiểm tra chu trình.

Khi E=0, mọi đỉnh có indegree=0, nên Kahn xử lý tất cả V đỉnh trong O(V), tạo ra một hoán vị tùy ý. Khi đồ thị có chu trình, Kahn có thể dừng trước khi duyệt tất cả E cạnh đi ra từ residual; đó là lợi ích thực tế, nhưng cận trên vẫn O(V+E).

**Chi phí lưu graph** là O(V+E) với adjacency list. Bộ nhớ phụ không tính cấu trúc lưu graph nhưng có thêm mảng indegree/queue hoặc color/parent O(V). Nếu chỉ dùng ma trận kề, quét hàng có thể tốn O(V²).

### Vấn đề đệ quy sâu

DFS ba màu dạng đệ quy có chiều sâu tới O(V), nên Java có thể gặp StackOverflowError trên DAG dạng chuỗi rất dài (dù không có chu trình). Nếu cần ổn định cho hàng triệu đỉnh, Kahn dạng vòng lặp thường an toàn hơn về stack. Nếu cần chu trình witness mà muốn tránh đệ quy, có thể dùng stack frame tường minh lưu đỉnh và vị trí cạnh kế tiếp, cùng trạng thái WHITE/GRAY/BLACK.

### Có tìm được mọi chu trình không?

Hai thuật toán ở đây chỉ phục vụ bài **kiểm tra tồn tại** và, nếu cần, trả **một** witness. Liệt kê mọi chu trình có thể có số lượng rất lớn (đặc biệt trong đồ thị dày), và không thể bảo đảm O(V+E) cho lượng đầu ra như vậy.

Nếu người dùng cần “những công việc nào tham gia vòng phụ thuộc”, SCC là công cụ bổ sung. Nhưng kết quả SCC không thay thế ý nghĩa của order topo; đây là hai truy vấn khác nhau trên đồ thị.

## 14. Các ca biên và sai lầm dễ gây false positive/false negative

| Trường hợp | Kết quả đúng | Lỗi thường mắc |
| --- | --- | --- |
| Đồ thị rỗng V=0 | Có thứ tự topo rỗng | Tưởng không có đáp án |
| V>0, E=0 | Có thứ tự topo: mọi hoán vị đều hợp lệ | Quên seed tất cả indegree=0 |
| Một self-loop u→u | Không có thứ tự topo | Bỏ qua cạnh tự nối |
| Hai cạnh song song u→v | Không tự tạo chu trình | Cộng indegree hai lần nhưng giảm một lần |
| Chu trình ở thành phần tách rời | Toàn đồ thị không có topo | DFS chỉ từ một đỉnh nguồn |
| DAG hình thoi 0→1,0→2,1→3,2→3 | Có topo | DFS Boolean coi gặp visited là chu trình |
| Một chu trình kèm đuôi đi ra | Không có topo | Tưởng mọi residual đều nằm trên chu trình |
| Có nhiều đỉnh indegree=0 | Có thể có nhiều topo | Tưởng không duy nhất là thất bại |
| Graph vô hướng | Phải định hướng cạnh theo bài toán | Tự chạy topo trên cạnh hai chiều |
| Input có đỉnh cô lập | Đỉnh cô lập phải xuất hiện trong order | Chỉ khởi tạo những đỉnh xuất hiện trong edge list |
| Đỉnh đầu/cạnh có id ngoài [0,n) | Dữ liệu không hợp lệ | IndexOutOfBounds hoặc kết quả sai |
| Cạnh chiều u→v bị nhập ngược | Thứ tự có thể sai theo dependency thực | Định nghĩa rõ ý nghĩa edge |
| Dùng bậc ra trong Kahn chuẩn | Chọn sai đầu thứ tự | Dùng bậc vào của phần còn lại |
| Đánh dấu DFS BLACK quá sớm | Bỏ lỡ back edge | Chỉ BLACK sau khi duyệt hết children |
| Trả partial order dù exists=false | Công bố lịch không thỏa mọi phụ thuộc | Trả cờ thất bại rõ ràng |

### Cạnh song song không nhất thiết là chu trình

Xét V={0,1,2} với các cạnh:

~~~text
0 -> 1
0 -> 1   (canh thu hai)
1 -> 2
~~~

Indegree ban đầu của 1 bằng 2. Sau khi Kahn lấy 0, phải duyệt **hai mục 1** trong adjacency[0], giảm bậc vào của 1 lần lượt 2→1→0. Khi đó 1 được enqueue đúng một lần, rồi 2; thứ tự topo là [0,1,2].

Nếu dùng Set để gộp hai cạnh song song thành một cạnh, cũng có thể đúng **nếu tính indegree từ chính graph đã được gộp**. Sai xảy ra khi graph và indegree **không nhất quán**: đếm hai cạnh nhưng chỉ xóa một.

### Self-loop là chu trình một cạnh

Với một đỉnh 0 và cạnh 0→0, indegree[0]=1 nên không có đỉnh nguồn của Kahn. DFS từ 0 sẽ gặp cạnh 0→0 trong khi color[0]=GRAY, trả witness [0,0]. Không nên từ chối self-loop như dữ liệu lỗi nếu mục tiêu chính là **phát hiện phụ thuộc vòng**: nó chính là trường hợp quan trọng cần phát hiện.

### Cạnh có hướng khác với cạnh vô hướng

Một cạnh vô hướng (u,v) thường được lưu bằng **hai cung** u→v và v→u. Nếu mang nguyên biểu diễn ấy đi kiểm tra topo, sẽ có chu trình hai cung u→v→u dù đồ thị vô hướng ban đầu chỉ có một cạnh. Kết luận này không phản ánh một bài toán thứ tự trước/sau hợp lệ, vì graph đã được diễn giải lại thành **hai ràng buộc trái ngược**. Cần xác định hướng theo đề thực tế trước khi dùng topo.

## 15. Kiểm tra và kiểm thử kết quả một cách độc lập

### Xác minh một thứ tự topo được trả về

Nếu kết quả exists=true và order được trả, hãy kiểm tra:

1. order có **đúng V phần tử**.
2. Mỗi id thuộc [0,V) xuất hiện **chính xác một lần**.
3. Tạo position[v]=vị trí của v trong order.
4. Với **mọi cạnh u→v**, kiểm position[u]<position[v].

Nếu tất cả đúng, order là một thứ tự topo hợp lệ. Cách kiểm này tốn O(V+E) và không phụ thuộc vào thuật toán đã dùng để tạo order; rất phù hợp làm **oracle kiểm thử**.

Nếu exists=false, một witness chu trình phải có đỉnh đầu bằng đỉnh cuối và từng cạnh liên tiếp tồn tại trong graph. Nếu có witness thật, ta đã có **chứng cứ độc lập** rằng không thể có topo.

### Kiểm thử bằng liệt kê hoán vị cho V nhỏ

Với V≤8, có thể liệt kê tất cả V! hoán vị các đỉnh, kiểm từng hoán vị theo position[u]<position[v]. Nếu ít nhất một hoán vị thỏa, graph là DAG; nếu không có hoán vị nào thỏa, graph có chu trình. Đối chiếu Boolean này với Kahn và DFS ba màu.

Dùng brute force như vậy **chỉ để kiểm tra cỡ nhỏ**, không dùng cho graph lớn vì V! tăng cực nhanh.

### Kiểm thử theo đồ thị ngẫu nhiên

Một bài kiểm thử mạnh có thể:

- Sinh một hoán vị ngẫu nhiên P của các đỉnh.
- Chỉ thêm các cạnh từ vị trí **sớm** tới vị trí **muộn** trong P. Khi ấy graph chắc chắn là DAG; cả Kahn và DFS phải báo có topo và chứng thực order.
- Chọn một chuỗi đỉnh khác nhau trong graph mới, thêm các cạnh tạo thành chu trình, ví dụ a→b→c→a. Khi ấy graph chắc chắn có chu trình; Kahn phải báo thất bại và DFS phải trả witness hợp lệ.
- Thêm self-loop để kiểm tra chu trình độ dài 1.
- Thêm cạnh song song trên một DAG nhưng không đổi hướng và không thêm cạnh ngược; kết quả vẫn DAG.

Không nên tạo cycle test bằng cách thêm cạnh tùy ý rồi **giả định** chắc chắn đã tạo được chu trình: phải xác minh đường đóng cụ thể hoặc so với một oracle khác.

### Bộ ca tham khảo

| Input | Kahn exists | Kahn order/witness đáng chú ý |
| --- | --- | --- |
| DAG 7 đỉnh của ví dụ | true | [0,5,1,2,6,3,4] |
| 5 đỉnh với 1→2→1 | false | partial [0], witness [1,2,1] |
| Self-loop 0→0 và cạnh 0→1 | false | witness [0,0] |
| Parallel 0→1 hai lần, 1→2 | true | [0,1,2] |
| Đồ thị rỗng V=0 | true | [] |
| V=4, cạnh 0→1 và 2→3 | true | [0,2,1,3] với FIFO theo id |
| V=1, không có cạnh | true | [0] |
| V=1, cạnh 0→0 | false | [0,0] |
| DAG hình thoi 0→1,0→2,1→3,2→3 | true | Có nhiều topo hợp lệ |
| Chu trình chỉ ở thành phần không chứa 0 | false | Phải duyệt mọi đỉnh để phát hiện |
| Cạnh 0→2 khi n=2 | Lỗi input | Từ chối do id ngoài miền |

### Tính chất cần kiểm bằng assert

- exists bằng (order.size()==V).
- Nếu exists, unprocessed phải rỗng.
- Nếu không exists, unprocessed không rỗng và mọi phần tử có indegree còn lại dương.
- Nếu không exists, findDirectedCycle phải trả witness không rỗng trong graph không đổi.
- Nếu exists, findDirectedCycle phải trả danh sách rỗng.
- Nếu exists và V>0, order chứa cả các đỉnh cô lập.
- Với mỗi cạnh u→v của một DAG, indexOf(u)<indexOf(v) trong order.
- Kahn và DFS phải cùng kết luận DAG/cyclic trên mọi graph hợp lệ.
- Nếu hoán đổi thứ tự adjacency hoặc thứ tự seed queue, cờ exists **không thay đổi**.
- Gỡ đúng một cạnh trong chu trình **có thể** làm graph thành DAG nếu không còn chu trình khác, nhưng không được mặc định rằng xóa một cạnh tùy ý luôn đủ.

## 16. Bài tập thực hành

1. Với graph 0→1, 1→2, 2→0, hãy chứng minh bằng bất đẳng thức vị trí rằng không thể có thứ tự topo. Chạy tay Kahn và nêu ngay bước dừng.
2. Với DAG 7 đỉnh trong bài, điền bảng indegree, queue và order sau từng lượt. Kiểm tra mọi cạnh trong kết quả [0,5,1,2,6,3,4].
3. Thêm cạnh 4→0 vào DAG ví dụ. Xác định có tạo chu trình hay không; nếu có, tìm một chu trình rõ ràng và mô phỏng Kahn dừng ở đâu.
4. Với graph 0→1,1→2,2→1,2→3,3→4, giải thích vì sao residual=[1,2,3,4] nhưng **không phải cả bốn đỉnh đều thuộc chu trình**.
5. Cho V=4 và các cạnh 0→1, 2→3. Dùng FIFO seed theo id tăng dần để tự tính order. Thử sắp lại queue và liệt kê thêm hai thứ tự hợp lệ.
6. Mô phỏng DFS ba màu trên DAG hình thoi 0→1,0→2,1→3,2→3. Vì sao gặp đỉnh 3 màu BLACK từ nhánh thứ hai **không** cho phép báo chu trình?
7. Cho self-loop 5→5 trong graph 6 đỉnh. Mô tả kết quả indegree, Kahn và DFS witness; vì sao [5,5] là một chu trình hợp lệ?
8. Cho graph có hai cạnh song song 0→1 và một cạnh 1→2. Tính indegree từng đỉnh; mô phỏng từng lần giảm bậc vào để không enqueue 1 sai thời điểm.
9. Viết hàm verifyTopo(order,edges,n) chạy O(V+E), trả false nếu order thiếu/đúp đỉnh hoặc có bất kỳ cạnh u→v với position[u]≥position[v].
10. Mở rộng chương trình Java để trả **tên công việc** thay vì id. Đầu vào chứa danh sách tên và dependency, báo lỗi khi dependency tham chiếu tên không có trong dữ liệu.
11. Dùng priority queue trong Kahn để trả thứ tự topo nhỏ nhất theo thứ tự từ điển của id. So sánh kết quả với FIFO trên một DAG có nhiều nguồn.
12. Viết DFS ba màu **không đệ quy** bằng stack frame giữ chỉ số cạnh đang xét. Bảo đảm GRAY chỉ nghĩa là đang nằm trên stack và BLACK khi toàn bộ cạnh đã xử lý.
13. Viết bộ test ngẫu nhiên sinh DAG từ một hoán vị P, chạy Kahn, rồi thêm chu trình ba đỉnh và xác minh cờ false cùng witness hợp lệ.
14. Dùng brute force mọi hoán vị với V≤8 để kiểm tra kết quả Kahn, bao gồm E=0, self-loop, cạnh song song và chu trình ở thành phần tách biệt.
15. Với một dependency graph có SCC {A,B,C} và đuôi C→D→E, phân biệt những đỉnh thuộc chu trình với những đỉnh chỉ **bị chặn** sau chu trình; giải thích cách SCC hỗ trợ chẩn đoán.
16. Nếu graph thay đổi theo thời gian (thêm/bớt dependency), phân tích vì sao kết quả topo/cycle cũ có thể mất hiệu lực và đề xuất cách kiểm tra lại hoặc duy trì topo động theo yêu cầu hệ thống.

## 17. Checklist áp dụng và kết luận

Khi gặp yêu cầu “kiểm tra thứ tự thực hiện”, “phát hiện phụ thuộc vòng” hay “có cách xếp các công việc không”, hãy kiểm tra lần lượt:

- **Mô hình đúng chưa?** Đỉnh đại diện đúng đối tượng; cạnh u→v nghĩa là u bắt buộc **trước** v; đồ thị có hướng.
- **Đã tính đủ mọi đỉnh?** Đỉnh cô lập và các thành phần không reachable từ đỉnh 0 cũng phải tham gia.
- **Dùng phương pháp nào?** Chọn Kahn nếu cần topo và cờ thành công; chọn DFS ba màu nếu cần phát hiện và dựng một witness chu trình.
- **Điều kiện quyết định?** Kahn: đã lấy đủ n đỉnh thì có topo; thiếu đỉnh thì không. DFS: có cạnh tới đỉnh GRAY thì có chu trình.
- **Khi thất bại báo thế nào?** Không trả partial order như nghiệm hoàn chỉnh; có thể báo số đỉnh chưa xử lý và một chu trình cụ thể.
- **Đã xử lý ca biên?** Đồ thị rỗng, self-loop, cạnh song song, các thành phần tách biệt và lỗi id ngoài miền.
- **Đã chứng minh và kiểm tra?** Khi exists=true, xác minh position[u]<position[v] cho mọi cạnh; khi exists=false, xác minh witness là một chu trình có hướng thực tế.

**Kết luận cốt lõi:** thứ tự tô-pô tồn tại **khi và chỉ khi đồ thị có hướng là DAG**. Thuật toán **Kahn** phát hiện không tồn tại khi hàng đợi hết nhưng chưa xử lý đủ đỉnh; **DFS ba màu** phát hiện không tồn tại khi một cạnh dẫn về đỉnh GRAY đang nằm trên stack, đồng thời có thể dựng chu trình chứng minh. Đừng nhầm “nhiều thứ tự topo” với “không có thứ tự topo”, và đừng nhầm “đỉnh còn dư sau Kahn” với “đỉnh chắc chắn nằm trong chu trình”.

# BFS nhiều nguồn

## 1. BFS nhiều nguồn giải bài toán gì?

**BFS nhiều nguồn (multi-source breadth-first search)** là thuật toán duyệt theo chiều rộng xuất phát **đồng thời từ nhiều đỉnh nguồn**. Nó đặc biệt hữu ích khi cần tìm **khoảng cách ngắn nhất từ mỗi đỉnh tới một nguồn gần nhất**, với giả thiết các cạnh đều có cùng chi phí một bước.

Ví dụ:
- Trên bản đồ ô vuông, có nhiều trạm cứu hộ: mỗi ô cách **trạm gần nhất** bao nhiêu bước?
- Trong một mạng xã hội, ai cách **bất kỳ tài khoản khởi đầu nào** ít bước kết nối nhất?
- Lửa/chất lỏng lan từ **nhiều vị trí ban đầu**: thời điểm sớm nhất từng vị trí được tiếp cận là bao nhiêu?
- Trên đồ thị, cần gán mỗi đỉnh cho **một nguồn gần nhất** và truy vết đường đi.
- Trong mê cung có nhiều cửa thoát, từ mỗi ô đi tới cửa thoát gần nhất mất bao nhiêu bước? Cần chú ý chiều cạnh nếu là đồ thị có hướng.

Ý tưởng mấu chốt: **đưa tất cả nguồn vào hàng đợi với khoảng cách 0 trước khi bắt đầu lấy phần tử ra xử lý**. Sau đó BFS lan tỏa từng lớp khoảng cách:

~~~text
Lớp 0: tất cả các nguồn ban đầu
Lớp 1: các đỉnh cách một nguồn đúng 1 cạnh
Lớp 2: các đỉnh cách một nguồn đúng 2 cạnh
...
~~~

BFS không ưu tiên nguồn này chạy hết rồi mới chạy nguồn kia. Tất cả nguồn là các điểm xuất phát ngang hàng; hàng đợi FIFO bảo đảm đỉnh có khoảng cách nhỏ hơn được xử lý trước.

**Kết quả quan trọng nhất:** với mọi đỉnh v, khoảng cách trả về là số cạnh **ít nhất** trên một đường đi từ **bất kỳ nguồn nào** tới v. Các trường hợp hòa giữa nhiều nguồn có cùng khoảng cách cần được xử lý riêng nếu bài yêu cầu một quy tắc chọn nguồn cụ thể.

## 2. Đặc tả toán học và phạm vi áp dụng

Cho đồ thị \(G=(V,E)\) với N đỉnh, được đánh số 0..N−1. Tập nguồn \(S\subseteq V\). Giả sử:
- Mỗi cạnh có chi phí bằng **1 bước** (đồ thị không trọng số hoặc trọng số đồng nhất).
- Ta cần khoảng cách theo **chiều đi từ nguồn tới đỉnh đích**.
- Đồ thị có thể **không liên thông**; một đỉnh có thể không được nguồn nào tiếp cận.
- Tập nguồn có thể chứa một hoặc nhiều đỉnh; đầu vào danh sách nguồn có thể có giá trị **lặp** và sẽ được khử trùng.

Ký hiệu \(\delta(s,v)\) là số cạnh ít nhất trên đường đi từ s tới v; nếu không có đường đi thì \(\delta(s,v)=+\infty\). Giá trị cần tính là:

\[
\boxed{dist[v]=\min_{s\in S}\delta(s,v)}.
\]

Nếu S rỗng, không có đường đi xuất phát từ nguồn nào: mọi dist[v] được coi là vô cùng. Trong mảng Java, ví dụ này dùng **−1** để biểu diễn “không thể tới” thay cho vô cùng.

Định nghĩa các thông tin tùy chọn:
- **dist[v]:** khoảng cách ngắn nhất tới một nguồn.
- **origin[v]:** một đỉnh nguồn đạt khoảng cách đó; nếu không thể tới, là −1.
- **parent[v]:** đỉnh liền trước v trên **một đường đi ngắn nhất từ origin[v] tới v**; đối với nguồn hoặc đỉnh không thể tới là −1.
- **maxDistance:** khoảng cách lớn nhất trong các đỉnh đã tới được; nếu không tới được đỉnh nào, là −1.
- **unreachableCount:** số đỉnh có dist[v]=−1.

Lưu ý thuật ngữ “gần nguồn nhất” trong đồ thị **có hướng**: BFS theo cạnh u→v giải \(\min_{s\in S}\delta(s,v)\). Nếu bài hỏi từ v **đi đến** nguồn gần nhất, tức \(\min_{s\in S}\delta(v,s)\), phải BFS trên **đồ thị đảo chiều cạnh**, không phải tự động chạy cùng chiều.

BFS theo hàng đợi thường **không đúng** khi cạnh có trọng số khác nhau. Khi đó xem xét **Dijkstra nhiều nguồn** cho trọng số không âm, hoặc **0–1 BFS** nếu trọng số chỉ thuộc {0,1}.

## 3. Vì sao phải khởi tạo đồng thời toàn bộ nguồn?

Một BFS đơn nguồn bình thường:
1. Đặt dist[source]=0.
2. Đưa source vào queue.
3. Lấy đỉnh đầu queue và xét các đỉnh kề chưa thăm.

BFS nhiều nguồn chỉ thay bước khởi tạo:

~~~text
for each vertex v:
    dist[v] = -1
    origin[v] = -1
    parent[v] = -1

queue = empty FIFO

for each source s:
    if dist[s] == -1:             // Bỏ trùng nguồn
        dist[s] = 0
        origin[s] = s
        queue.pushBack(s)

while queue not empty:
    u = queue.popFront()
    for each neighbor v of u:
        if dist[v] != -1:
            continue             // Đã được phát hiện
        dist[v] = dist[u] + 1
        origin[v] = origin[u]
        parent[v] = u
        queue.pushBack(v)
~~~

**Các nguồn phải được thêm hết vào queue trước vòng while.** Nếu chạy BFS từ nguồn A đến khi queue hết, rồi thử nguồn B mà dùng lại mảng visited/dist, các đỉnh đã được A thăm sẽ không được cập nhật dù thực tế gần B hơn. Đó không phải BFS nhiều nguồn đúng.

Ví dụ trên đường thẳng:

~~~text
0 -- 1 -- 2 -- 3 -- 4 -- 5 -- 6

Nguồn S = {0, 6}
Khoảng cách đúng: [0, 1, 2, 3, 2, 1, 0]
~~~

Nếu chạy nguồn 0 hết trước và không cho nguồn 6 sửa khoảng cách, ta có thể nhận [0,1,2,3,4,5,6], **sai** ở các đỉnh 4,5,6. Khởi tạo cả 0 và 6 từ đầu sẽ khiến hai làn sóng gặp nhau ở giữa, đúng khoảng cách nhỏ nhất tới nguồn nào cũng được.

### Đánh dấu khi phát hiện, không đợi tới lúc lấy ra

Đặt dist[v] và origin[v] **ngay trước khi enqueue(v)**. Đó là thời điểm v được **phát hiện lần đầu** bằng một đường đi ngắn nhất. Nhờ vậy:
- Mỗi đỉnh được enqueue **tối đa một lần**.
- Không có nhiều bản sao của cùng đỉnh trong queue.
- Cây parent không bị ghi đè bởi một đường đi dài hơn hoặc một lựa chọn hòa xuất hiện sau.

Nếu chỉ đánh dấu visited khi dequeue, nhiều đỉnh kề có thể enqueue cùng một v trước khi nó được lấy ra. Thuật toán có thể trở nên tốn thời gian/bộ nhớ và parent/origin khó nhất quán nếu thiếu cơ chế lọc bổ sung.

## 4. Phân biệt BFS một nguồn, chạy K lần, và BFS nhiều nguồn

Giả sử có K nguồn và đồ thị có N đỉnh, M cạnh.

| Phương pháp | Kết quả tự nhiên | Thời gian |
|---|---|---|
| BFS từ một nguồn s | Khoảng cách từ s tới mọi đỉnh | O(N+M) |
| Chạy BFS riêng cho từng nguồn | Ma trận khoảng cách từ từng nguồn, có thể lấy min sau | O(K(N+M)) |
| BFS nhiều nguồn một lượt | Khoảng cách tới **nguồn gần nhất** | **O(N+M+K)** |

Nếu mục tiêu chỉ là \(\min_{s\in S}\delta(s,v)\) cho mọi v, chạy K lần thường là lãng phí. Multi-source BFS giải cùng mục tiêu bằng **một** hàng đợi.

Ngược lại, nếu cần **khoảng cách từ từng nguồn riêng lẻ** tới mỗi đỉnh, multi-source BFS chỉ giữ khoảng cách nhỏ nhất nên **không đủ thông tin**. Khi đó có thể cần K lần BFS hoặc một phương pháp chuyên biệt.

**Một BFS nhiều nguồn không tính mọi cặp khoảng cách.** Không nên xem dist[v] là bảng dist[s][v] đầy đủ hoặc origin[v] là danh sách mọi nguồn tối ưu.

## 5. Diễn giải theo lớp sóng

Ngay sau khởi tạo, queue chứa tất cả nguồn có dist=0.

Mỗi lần lấy một đỉnh u với dist[u]=d:
- Các đỉnh kề chưa được phát hiện nhận dist=d+1.
- Chúng được đưa vào **cuối queue**, phía sau những đỉnh đang chờ có khoảng cách ≤d+1.
- Khi bắt đầu xử lý đỉnh ở lớp d+1, tất cả đỉnh lớp d đã được lấy ra trước đó.

Ta có thể hình dung nhiều **mặt sóng cùng lan** từ các nguồn. Một đỉnh được sóng nào chạm đến đầu tiên sẽ nhận khoảng cách và origin từ sóng ấy.

Trường hợp có nhiều nguồn với cùng khoảng cách ngắn nhất:
- **dist[v] không phụ thuộc thứ tự xét nguồn/cạnh**.
- **origin[v] và parent[v] có thể phụ thuộc thứ tự** nếu nhiều lựa chọn hòa.
- Chương trình chỉ lưu **một** nguồn và **một** đường đi ngắn nhất, không liệt kê mọi lựa chọn hòa.

Điều này rất quan trọng khi bài hỏi “khoảng cách tới trạm gần nhất” so với “ID trạm gần nhất nhỏ nhất”. Hai yêu cầu không hoàn toàn giống nhau khi có nhiều trạm cùng khoảng cách.

## 6. Ví dụ đồ thị có hai nguồn, đường đi hòa và đỉnh cô lập

Xét đồ thị **vô hướng** có 9 đỉnh 0..8. Các cạnh được đưa vào danh sách kề theo thứ tự:

~~~text
(0,1), (1,2), (2,3),
(0,4), (4,5), (5,3),
(3,6), (2,7), (5,7), (4,7)
~~~

Đỉnh **8** không có cạnh nào; nó là một thành phần cô lập. Đặt hai nguồn:

~~~text
S = [0, 3]
queue ban đầu = [0, 3]
dist[0] = dist[3] = 0
~~~

Các nguồn không cần liên thông trực tiếp. Đỉnh 7 có nhiều đường đi độ dài 2:
- Từ nguồn 0: **0 → 4 → 7**.
- Từ nguồn 3: **3 → 2 → 7** hoặc **3 → 5 → 7**.

Vì vậy, dist[7]=2 bất kể nguồn nào được gán. Ví dụ dùng thứ tự nguồn [0,3] và thứ tự cạnh đã liệt kê; đỉnh 7 sẽ được phát hiện lần đầu từ nhánh của nguồn 0.

### Trace hàng đợi theo từng lượt dequeue

| Lượt | Lấy ra | Các đỉnh mới phát hiện (theo thứ tự) | Ghi chú |
|---:|---:|---|---|
| Khởi tạo | — | 0, 3 | Hai nguồn đều có dist 0 |
| 1 | 0 | 1, 4 | dist=1, origin=0 |
| 2 | 3 | 2, 5, 6 | dist=1, origin=3 |
| 3 | 1 | Không | 2 đã được phát hiện từ nguồn 3 |
| 4 | 4 | 7 | dist=2, origin=0, parent=4 |
| 5 | 2 | Không | 7 đã được phát hiện |
| 6 | 5 | Không | 7 đã được phát hiện |
| 7 | 6 | Không | Không có đỉnh mới |
| 8 | 7 | Không | Không có đỉnh mới |

**Thứ tự dequeue:** [0,3,1,4,2,5,6,7]. Đỉnh 8 không được đưa vào queue.

### Kết quả từng đỉnh

| v | dist[v] | origin[v] | parent[v] | Diễn giải |
|---:|---:|---:|---:|---|
| 0 | 0 | 0 | −1 | Nguồn ban đầu |
| 1 | 1 | 0 | 0 | 0→1 |
| 2 | 1 | 3 | 3 | 3→2 |
| 3 | 0 | 3 | −1 | Nguồn ban đầu |
| 4 | 1 | 0 | 0 | 0→4 |
| 5 | 1 | 3 | 3 | 3→5 |
| 6 | 1 | 3 | 3 | 3→6 |
| 7 | 2 | 0 | 4 | 0→4→7 |
| 8 | −1 | −1 | −1 | Không thể tới |

Với thứ tự [0,3]:

~~~text
dist   = [0, 1, 1, 0, 1, 1, 1, 2, -1]
origin = [0, 0, 3, 3, 0, 3, 3, 0, -1]
parent = [-1, 0, 3, -1, 0, 3, 3, 4, -1]
~~~

Khoảng cách lớn nhất trong những đỉnh **tới được** là 2. Có **1 đỉnh không tới được**, là đỉnh 8.

### Đảo thứ tự hai nguồn sẽ ra sao?

Nếu đưa **3 trước 0** vào queue (giữ nguyên các cạnh và thứ tự kề):
- Các khoảng cách vẫn y hệt.
- Đỉnh 7 sẽ được nhánh của nguồn 3 phát hiện trước, qua **3→2→7**.
- Khi đó origin[7]=3, parent[7]=2.

Cả hai cách đều đúng nếu đề chỉ yêu cầu một nguồn gần nhất. Nếu đề quy định **phải trả nguồn có ID nhỏ nhất trong mọi nguồn gần nhất**, không thể dựa ngẫu nhiên vào thứ tự nhập; phải thiết kế thêm tie-break được chứng minh đúng (ví dụ tổ chức lớp và cập nhật gán nguồn phù hợp).

## 7. Chứng minh tính đúng của BFS nhiều nguồn

### 7.1. Mọi khoảng cách được gán là chiều dài một đường đi thật

Mỗi nguồn s được gán dist[s]=0, tương ứng đường đi rỗng từ s tới s. Mỗi đỉnh v mới được phát hiện từ cạnh (u,v) nhận dist[v]=dist[u]+1 và origin[v]=origin[u]. Nếu parent[u] đã mô tả đường đi từ một nguồn tới u dài dist[u], nối cạnh (u,v) tạo đường đi tới v dài dist[v].

Bằng quy nạp theo lần phát hiện, với mọi đỉnh đã được gán, ta **có một đường đi thật** từ origin[v] tới v dài đúng dist[v]. Do đó dist[v] **không thể nhỏ hơn khoảng cách ngắn nhất**.

### 7.2. Không có đường đi ngắn hơn đường mà BFS tìm được

Tại thời điểm khởi tạo, queue chứa **toàn bộ** các nguồn ở lớp 0. Với queue FIFO và mỗi cạnh có chi phí 1, sau khi một đỉnh lớp d được xử lý, đỉnh mới được phát hiện nằm ở lớp d+1 và được thêm vào cuối hàng đợi.

Vì thế các đỉnh được dequeue theo **thứ tự khoảng cách không giảm**. Giả sử có đỉnh v được gán dist[v]=d nhưng thực tế có đường đi từ một nguồn nào đó tới v với độ dài \(\ell<d\). Trên đường ấy, đỉnh ngay trước v phải có khoảng cách không quá \(\ell-1<d-1\); BFS xử lý đỉnh này trước những đỉnh lớp d−1 dẫn tới lần phát hiện v, nên v đã phải được phát hiện với khoảng cách không quá \(\ell\). Mâu thuẫn.

Cách phát biểu chặt hơn bằng quy nạp theo lớp: tất cả đỉnh có khoảng cách ngắn nhất d đều được phát hiện từ các đỉnh có khoảng cách d−1 trước khi thuật toán bắt đầu xử lý các đường dài hơn. Vì mọi nguồn đều ở lớp 0, lập luận áp dụng cho **giá trị min trên tất cả nguồn** chứ không chỉ một nguồn.

Kết hợp hai chiều, với mọi v tới được:

\[
\boxed{dist[v]=\min_{s\in S}\delta(s,v).}
\]

### 7.3. Khi nào trả −1 là đúng?

Nếu v không bao giờ được phát hiện, không thể tồn tại đường đi từ một nguồn tới v: giả sử tồn tại một đường, bắt đầu từ nguồn có dist=0; lần lượt từng đỉnh của đường sẽ được duyệt và đỉnh kế tiếp được phát hiện, cuối cùng v phải được phát hiện. Mâu thuẫn.

Do đó dist[v]=−1 **đúng nghĩa không có đường đi từ bất kỳ nguồn nào tới v** theo hướng cạnh đang xét.

### 7.4. Tính đúng của parent và origin

Đỉnh v khác nguồn chỉ được phát hiện qua một cạnh u→v với dist[v]=dist[u]+1. Gán parent[v]=u và origin[v]=origin[u] đảm bảo đi lùi theo parent:
- Khoảng cách giảm đúng 1 ở mỗi bước.
- Cuối cùng tới một đỉnh nguồn có dist=0, parent=−1.
- Chuỗi đảo ngược là một đường đi ngắn nhất từ một nguồn tới v.

Tuy nhiên, parent/origin mô tả **một** đường ngắn nhất, không nhất thiết tất cả đường hay một nguồn duy nhất có thể đạt khoảng cách đó.

## 8. Khôi phục đường đi ngắn nhất về nguồn

Với result gồm dist, origin và parent, muốn lấy đường đi tới đỉnh target:
1. Nếu target nằm ngoài miền hợp lệ, báo lỗi.
2. Nếu dist[target]==−1, trả danh sách rỗng để biểu thị **không có đường từ nguồn nào tới target**.
3. Từ target đi lùi qua parent cho tới −1, ghi các đỉnh.
4. Đảo danh sách để có đường từ nguồn đến target.

Giả mã:

~~~text
pathTo(target):
    if dist[target] == -1:
        return []

    reversedPath = []
    at = target

    while at != -1:
        reversedPath.add(at)
        at = parent[at]

    reverse(reversedPath)
    return reversedPath
~~~

Với dữ liệu trên:
- target=7, nguồn [0,3] → [0,4,7].
- target=8 → [], vì không có đường.
- target=0 → [0], là đường đi độ dài 0.

Đừng trả chỉ parent[7]=4 rồi xem đó là **toàn bộ đường đi**: phải theo tiếp parent[4]=0. Và đừng nhầm origin[7]=0 với parent[7]=4; một bên là **nguồn gốc**, một bên là **đỉnh ngay trước**.

Chi phí khôi phục một đường đi dài d cạnh là O(d+1), với bộ nhớ O(d+1) cho danh sách kết quả.

## 9. BFS nhiều nguồn trên lưới có chướng ngại vật

Lưới R×C cũng có thể xem là một đồ thị:
- Mỗi ô đi được là một đỉnh.
- Có cạnh nối hai ô kề nếu được phép đi giữa chúng.
- Với **4 hướng** (lên, xuống, trái, phải), mỗi bước có chi phí 1.
- Các ô '#': tường, không đi qua.
- Các ô 'S': **nguồn**, đều phải có dist=0.
- Các ô '.': đi được.

Ví dụ lưới 3×5:

~~~text
S..#.
.#..S
...#.
~~~

Có nguồn tại (0,0) và (1,4). Chạy BFS nhiều nguồn 4 hướng, với dấu −1 cho tường/ô không tới được, thu được:

~~~text
[0, 1, 2, -1, 1]
[1, -1, 2, 1, 0]
[2, 3, 3, -1, 1]
~~~

Giải thích:
- Ô (0,2) cách nguồn (0,0) hai bước qua (0,1).
- Ô (1,3) cách nguồn (1,4) một bước.
- Ô (2,2) cách nguồn (0,0) ba bước, chẳng hạn (0,0)→(1,0)→(2,0)→(2,1)→(2,2) thực ra **bốn** bước; đường ngắn hơn là (0,0)→(0,1)→(0,2)→(1,2)→(2,2), cũng **bốn** bước. Vậy cần kiểm tra nguồn khác: từ (1,4)→(1,3)→(1,2)→(2,2), **ba** bước, nên dist[2][2]=3.
- Tường có dist=−1 vì không phải đỉnh đi được, không được enqueue.

**Cần phân biệt:** khi dùng chung sentinel −1 cho tường và ô đi được nhưng không tới được, phải dựa thêm vào **ký tự gốc của ô** để phân biệt hai lý do. Nếu bài yêu cầu báo số ô đi được không tới được, chỉ đếm các ô '.'/'S' có dist=−1, không đếm tường.

Nếu đề cho **8 hướng**, cạnh của lưới khác đi và khoảng cách có thể giảm; không dùng nhầm kết quả BFS 4 hướng cho đề 8 hướng. Nếu mỗi ô có thời gian di chuyển không bằng nhau, phải đổi sang thuật toán đường đi ngắn nhất có trọng số thích hợp.

## 10. Java 17+ độc lập: đồ thị và lưới

Chương trình dưới đây gồm hai API:
- **solveUndirected(vertexCount, edges, sources):** BFS nhiều nguồn trên đồ thị vô hướng; trả khoảng cách, nguồn được gán, parent, khoảng cách lớn nhất tới được và số đỉnh không tới được.
- **gridDistances(grid):** BFS nhiều nguồn trên lưới ký tự với tường '#', nguồn 'S', đường đi '.', chỉ dùng **4 hướng**.

Hàm **pathTo** dựng một đường đi từ nguồn được gán tới đỉnh đích. Mã giữ **thứ tự cạnh nhập** trong danh sách kề để ví dụ về tie có đầu ra xác định; nếu thay thứ tự cạnh, đường đi hoặc nguồn của đỉnh hòa có thể thay đổi.

Lưu thành **MultiSourceBfsDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class MultiSourceBfsDemo {
    private MultiSourceBfsDemo() {
    }

    public record Result(
            int[] distance,
            int[] origin,
            int[] parent,
            int maxDistance,
            int unreachableCount) {
    }

    public static Result solveUndirected(
            int vertexCount, int[][] edges, int[] sources) {
        if (vertexCount < 0 || edges == null || sources == null) {
            throw new IllegalArgumentException("Invalid graph input");
        }

        List<List<Integer>> graph = new ArrayList<>();
        for (int v = 0; v < vertexCount; v++) {
            graph.add(new ArrayList<>());
        }

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException("Invalid edge");
            }
            int u = edge[0];
            int v = edge[1];
            if (u < 0 || v < 0 || u >= vertexCount
                    || v >= vertexCount) {
                throw new IllegalArgumentException("Vertex out of range");
            }
            graph.get(u).add(v);
            graph.get(v).add(u);
        }

        int[] distance = new int[vertexCount];
        int[] origin = new int[vertexCount];
        int[] parent = new int[vertexCount];

        Arrays.fill(distance, -1);
        Arrays.fill(origin, -1);
        Arrays.fill(parent, -1);

        ArrayDeque<Integer> queue = new ArrayDeque<>();

        // Khởi tạo TẤT CẢ nguồn trước khi xử lý queue.
        for (int s : sources) {
            if (s < 0 || s >= vertexCount) {
                throw new IllegalArgumentException("Source out of range");
            }
            if (distance[s] != -1) {
                continue; // Trùng nguồn: không enqueue lần hai.
            }
            distance[s] = 0;
            origin[s] = s;
            queue.addLast(s);
        }

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();

            for (int v : graph.get(u)) {
                if (distance[v] != -1) {
                    continue;
                }

                // Ghi khi phát hiện, không chờ tới khi dequeue.
                distance[v] = distance[u] + 1;
                origin[v] = origin[u];
                parent[v] = u;
                queue.addLast(v);
            }
        }

        int maxDistance = -1;
        int unreachableCount = 0;

        for (int d : distance) {
            if (d == -1) {
                unreachableCount++;
            } else {
                maxDistance = Math.max(maxDistance, d);
            }
        }

        return new Result(
                distance, origin, parent, maxDistance, unreachableCount);
    }

    public static List<Integer> pathTo(Result result, int target) {
        if (result == null || target < 0
                || target >= result.distance().length) {
            throw new IllegalArgumentException("Invalid target");
        }
        if (result.distance()[target] == -1) {
            return List.of();
        }

        List<Integer> reversed = new ArrayList<>();
        for (int at = target; at != -1; at = result.parent()[at]) {
            reversed.add(at);
        }

        Collections.reverse(reversed);
        return List.copyOf(reversed);
    }

    public static int[][] gridDistances(String[] grid) {
        if (grid == null) {
            throw new IllegalArgumentException("Null grid");
        }

        int rows = grid.length;
        if (rows == 0) {
            return new int[0][0];
        }
        if (grid[0] == null) {
            throw new IllegalArgumentException("Null row");
        }

        int cols = grid[0].length();
        int[][] dist = new int[rows][cols];
        ArrayDeque<int[]> queue = new ArrayDeque<>();

        for (int r = 0; r < rows; r++) {
            if (grid[r] == null || grid[r].length() != cols) {
                throw new IllegalArgumentException("Nonrectangular grid");
            }
            Arrays.fill(dist[r], -1);

            for (int c = 0; c < cols; c++) {
                char cell = grid[r].charAt(c);
                if (cell != 'S' && cell != '.' && cell != '#') {
                    throw new IllegalArgumentException("Unknown cell");
                }
                if (cell == 'S') {
                    dist[r][c] = 0;
                    queue.addLast(new int[] {r, c});
                }
            }
        }

        int[] dr = {-1, 1, 0, 0};
        int[] dc = {0, 0, -1, 1};

        while (!queue.isEmpty()) {
            int[] cell = queue.removeFirst();
            int r = cell[0];
            int c = cell[1];

            for (int k = 0; k < 4; k++) {
                int nr = r + dr[k];
                int nc = c + dc[k];

                if (nr < 0 || nr >= rows || nc < 0 || nc >= cols) {
                    continue;
                }
                if (grid[nr].charAt(nc) == '#'
                        || dist[nr][nc] != -1) {
                    continue;
                }

                dist[nr][nc] = dist[r][c] + 1;
                queue.addLast(new int[] {nr, nc});
            }
        }

        return dist;
    }

    public static void main(String[] args) {
        int[][] edges = {
                {0, 1}, {1, 2}, {2, 3},
                {0, 4}, {4, 5}, {5, 3},
                {3, 6}, {2, 7}, {5, 7}, {4, 7}
        };

        Result first = solveUndirected(9, edges, new int[] {0, 3});
        System.out.println("Sources: [0, 3]");
        System.out.println("Distance: "
                + Arrays.toString(first.distance()));
        System.out.println("Origin: "
                + Arrays.toString(first.origin()));
        System.out.println("Parent: "
                + Arrays.toString(first.parent()));
        System.out.println("Max distance: " + first.maxDistance());
        System.out.println("Unreachable: " + first.unreachableCount());
        System.out.println("Path to 7: " + pathTo(first, 7));
        System.out.println("Path to 8: " + pathTo(first, 8));

        Result reversed = solveUndirected(
                9, edges, new int[] {3, 0});
        System.out.println("Reverse sources origin[7]: "
                + reversed.origin()[7]);
        System.out.println("Reverse sources path to 7: "
                + pathTo(reversed, 7));

        Result duplicate = solveUndirected(
                9, edges, new int[] {0, 0, 3});
        System.out.println("Duplicate sources same distances: "
                + Arrays.equals(first.distance(),
                                duplicate.distance()));

        Result noSources = solveUndirected(
                3, new int[][] {{0, 1}}, new int[] {});
        System.out.println("No sources: "
                + Arrays.toString(noSources.distance()));

        Result empty = solveUndirected(
                0, new int[][] {}, new int[] {});
        System.out.println("Empty graph: "
                + Arrays.toString(empty.distance()));

        System.out.println("Grid distances:");
        int[][] gridDist = gridDistances(
                new String[] {"S..#.", ".#..S", "...#."});
        for (int[] row : gridDist) {
            System.out.println(Arrays.toString(row));
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 MultiSourceBfsDemo.java
java MultiSourceBfsDemo
~~~

**Stdout của chương trình:**

~~~text
Sources: [0, 3]
Distance: [0, 1, 1, 0, 1, 1, 1, 2, -1]
Origin: [0, 0, 3, 3, 0, 3, 3, 0, -1]
Parent: [-1, 0, 3, -1, 0, 3, 3, 4, -1]
Max distance: 2
Unreachable: 1
Path to 7: [0, 4, 7]
Path to 8: []
Reverse sources origin[7]: 3
Reverse sources path to 7: [3, 2, 7]
Duplicate sources same distances: true
No sources: [-1, -1, -1]
Empty graph: []
Grid distances:
[0, 1, 2, -1, 1]
[1, -1, 2, 1, 0]
[2, 3, 3, -1, 1]
~~~

### Giải thích triển khai

**1. Mảng ba vai trò tách biệt.** distance trả số bước; origin ghi **một nguồn gần nhất**; parent ghi **một đỉnh tiền nhiệm** trên đường đi ngắn nhất. Với đỉnh 7, origin=0 nhưng parent=4.

**2. Ghi −1 ban đầu.** Đây là dấu **chưa được phát hiện/không tới được**, khác với khoảng cách 0 của nguồn. Nếu khởi tạo mọi khoảng cách bằng 0 sẽ không phân biệt được nguồn với những đỉnh chưa duyệt.

**3. Kiểm tra trùng nguồn.** Nếu sources=[0,0,3], nguồn 0 chỉ enqueue một lần. Giá trị dist không đổi so với [0,3].

**4. Thứ tự kề giữ nguyên thứ tự cạnh.** Chương trình thêm u→v và v→u mỗi khi đọc một cạnh. Do đó ví dụ trên là đồ thị **vô hướng**. Với đồ thị có hướng, chỉ thêm cạnh u→v; cần hiểu lại ý nghĩa khoảng cách theo chiều nguồn tới đích.

**5. Khôi phục đường đi.** pathTo theo parent về tới −1, đảo kết quả. Khi đỉnh không thể tới, nó trả List.of() tức []; khi target tự là nguồn, nó trả danh sách một đỉnh.

**6. Lưới nhiều nguồn.** Hàm gridDistances đưa **mọi ô S** vào queue với giá trị 0 trước khi bắt đầu mở rộng, kiểm tra biên và bỏ tường. Hàm không gán owner hoặc parent cho lưới vì ví dụ chỉ yêu cầu khoảng cách; có thể bổ sung hai mảng tương ứng nếu cần đường đi.

**7. Bảo toàn đầu vào.** Danh sách kề được xây mới; các mảng edges, sources và grid không bị sửa.

**8. Mảng trong record vẫn có thể bị sửa.** Java record làm các trường tham chiếu thành final, nhưng **không tự biến phần tử mảng thành bất biến**. Trong ứng dụng sản xuất, nếu muốn bảo vệ Result khỏi sửa ngoài ý muốn, dùng các bản sao phòng vệ hoặc đối tượng chỉ đọc. Mã giáo dục ở đây chỉ đọc các mảng sau khi nhận kết quả.

**9. Xử lý biên.** Hàm từ chối ID đỉnh/nguồn ngoài miền, cạnh sai định dạng, dữ liệu null hay lưới không chữ nhật. Đồ thị 0 đỉnh với nguồn rỗng trả mảng rỗng; 3 đỉnh nhưng không có nguồn thì cả ba dist đều −1.

## 11. Độ phức tạp thời gian và bộ nhớ

Với đồ thị N đỉnh, M cạnh và danh sách có K nguồn:
- Khởi tạo danh sách kề: **O(N+M)** thời gian và O(N+M) bộ nhớ.
- Khởi tạo dist/origin/parent: **O(N)**.
- Xử lý danh sách K nguồn: **O(K)**; nguồn trùng được bỏ, không cần enqueue lại.
- Mỗi đỉnh được enqueue/dequeue tối đa một lần; mỗi cạnh trong danh sách kề được kiểm tra một lần theo mỗi hướng đối với đồ thị vô hướng: tổng **O(N+M)**.
- Tổng thời gian **O(N+M+K)**; bộ nhớ **O(N+M)** nếu tính cả danh sách kề, hay O(N) bộ nhớ bổ sung nếu đã có danh sách kề đầu vào.

Duyệt tìm maxDistance và unreachableCount tốn thêm O(N), không làm thay đổi bậc.

Với lưới R×C:
- Có tối đa RC ô/đỉnh.
- Mỗi ô được xử lý nhiều nhất một lần và kiểm tra tối đa bốn hướng.
- Tổng thời gian **O(RC)**, bộ nhớ O(RC) cho bảng dist và queue trong trường hợp xấu nhất.

**So với chạy BFS K lần:** O(K(N+M)) có thể chậm hơn nhiều nếu K lớn. Multi-source BFS chỉ cần một lượt duyệt, nhưng đổi lại nó chỉ trả **min distance tới tập nguồn**, không phải khoảng cách riêng của từng nguồn.

## 12. Đọc kết quả như thời gian lan truyền

Trong bài toán lan truyền đồng thời với **mỗi bước mất đúng một đơn vị thời gian**:
- Thời điểm đỉnh/ô v bị ảnh hưởng lần đầu chính là dist[v].
- Những nguồn ban đầu có thời điểm 0.
- Một vùng không thể tới được bất kỳ nguồn nào có dist=−1 và **không bị lan truyền tới**.

Nếu bài hỏi “mất bao lâu để lan tới **mọi đỉnh cần đạt**?”:
- Trước hết kiểm tra **tất cả đỉnh bắt buộc** có dist≥0 hay không.
- Nếu có đỉnh bắt buộc không thể tới được, cần trả **không thể hoàn tất** (thường −1 theo hợp đồng đề), thay vì đơn giản lấy max của những đỉnh đã tới.
- Nếu mọi đỉnh bắt buộc đều tới được, thời gian là \(\max_v dist[v]\) trên những đỉnh bắt buộc đó.

Ví dụ 9 đỉnh bên trên có maxDistance=2 nhưng đỉnh 8 không thể tới. Nếu yêu cầu lan tới **cả 9 đỉnh**, câu trả lời **không thể hoàn tất**, không phải thời gian 2. Nếu chỉ yêu cầu lan tới thành phần chứa các nguồn, 2 có thể là thời gian tối đa phù hợp.

Nếu có **nguồn rỗng** và vẫn có đỉnh bắt buộc cần lan tới, thời gian hoàn tất không tồn tại. Nếu không có đỉnh nào bắt buộc, phải theo quy ước đề để xác định thời gian 0 hay trạng thái rỗng.

## 13. Quan hệ với siêu nguồn (super-source)

Có một cách nhìn khác rất hữu ích về mặt chứng minh: thêm **đỉnh ảo T** nối tới mỗi nguồn s.

Nếu mọi cạnh mới T→s đều có trọng số **1**, BFS đơn nguồn từ T trả:

\[
dist_T(v)=1+\min_{s\in S}\delta(s,v)
\]

với các đỉnh tới được; vì vậy có thể **trừ 1** để trở lại khoảng cách nhiều nguồn mong muốn. Tuy nhiên, không được trừ 1 cho sentinel của đỉnh không tới được.

Nếu nối T→s bằng cạnh có trọng số **0**, khoảng cách từ T bằng đúng khoảng cách nhiều nguồn, nhưng đồ thị lúc này có cạnh 0 và 1; BFS FIFO thông thường **không còn được bảo đảm đúng** trên đồ thị có trọng số không đồng nhất. Cần 0–1 BFS hoặc thuật toán đường đi ngắn nhất phù hợp.

Khởi tạo tất cả nguồn với dist=0 và enqueue ngay từ đầu chính là cách **mô phỏng tác dụng của siêu nguồn 0 chi phí mà không phải thêm các cạnh ảo**. Đây là trực giác giải thích vì sao chỉ thay khâu khởi tạo từ BFS đơn nguồn là đủ.

## 14. Cận chế độ nâng cao và biến thể

### 14.1. Nguồn nào gần nhất khi có hòa?

origin[v] trong ví dụ là một nguồn được phát hiện **đầu tiên** trong những nguồn đạt min. Nó không tự mang nghĩa “ID nhỏ nhất” hay “nguồn ưu tiên cao nhất” nếu thứ tự queue/cạnh không được thiết kế cho điều đó.

Nếu đề yêu cầu:
- **Một nguồn bất kỳ gần nhất:** lưu origin như BFS chuẩn là đủ.
- **Nguồn gần nhất với tie-break theo ưu tiên:** cần quy tắc nhất quán (chẳng hạn sắp nguồn theo ưu tiên và có chứng minh thứ tự lớp đáp ứng tie-break, hoặc xử lý các kết quả cùng khoảng cách ở một bước riêng).
- **Tất cả nguồn cùng gần nhất:** một mảng origin đơn không đủ; phải lưu nhiều nguồn hoặc dùng phương pháp bổ sung, chi phí có thể lớn theo số cặp đỉnh–nguồn cần xuất.

Không được thay dist[v] bằng “khoảng cách tới nguồn đã được chọn sẵn” nếu nguồn được chọn không phải gần nhất; nếu yêu cầu cả tie-break và khoảng cách thì phải giữ **khoảng cách tối thiểu** làm tiêu chí ưu tiên chính.

### 14.2. Đồ thị có hướng: đảo cạnh khi cần

Ví dụ có cạnh A→B và nguồn là B:
- “Đi **từ B đến A**” là không thể nếu không có cạnh B→A.
- “Đi **từ A đến B**” dài một cạnh.

Vì vậy, với mục tiêu “mỗi đỉnh cần mấy bước **để đi tới** một nguồn”, ta phải chạy multi-source BFS từ các nguồn trên **đồ thị đảo** (mỗi cạnh u→v được thay bằng v→u). Khoảng cách trong đồ thị đảo từ s tới v bằng khoảng cách từ v tới s trong đồ thị gốc.

### 14.3. Cạnh có trọng số

Nếu các cạnh có trọng số **không âm** nhưng khác nhau, có thể dùng **Dijkstra nhiều nguồn**: gán dist[s]=0 cho mọi nguồn, đưa tất cả nguồn vào hàng đợi ưu tiên với khóa 0, sau đó relax các cạnh theo trọng số. Không dùng visited lúc enqueue như BFS nếu có thể tìm đường ngắn hơn sau đó; Dijkstra phải xử lý cập nhật khoảng cách đúng với heap.

Nếu trọng số chỉ thuộc {0,1}, dùng **0–1 BFS** với deque: cạnh 0 có thể đưa vào đầu, cạnh 1 đưa vào cuối theo quy tắc relax. Với trọng số âm, Dijkstra không áp dụng tổng quát; phải xét phương pháp phù hợp và vấn đề chu trình âm.

### 14.4. BFS động khi thêm/bớt nguồn

BFS nhiều nguồn cơ bản giả sử tập nguồn và đồ thị **cố định trong một lần chạy**. Khi thêm nguồn mới, có thể có nhiều khoảng cách giảm; khi xóa nguồn, các đỉnh từng phụ thuộc vào nguồn đó có thể phải được gán lại. Không thể chỉ xóa nguồn khỏi queue rồi coi bảng dist cũ còn đúng.

Trong các bài cập nhật ít và kích thước vừa phải, tính lại BFS từ đầu thường đơn giản và đáng tin hơn so với tự viết thuật toán động không được chứng minh.

## 15. Những lỗi rất hay gặp

1. **Chạy BFS từ nguồn A xong rồi thêm nguồn B vào queue cũ có visited.** Khoảng cách đã “chốt” theo A có thể sai đối với nguồn B; phải đưa toàn bộ nguồn vào từ đầu.
2. **Chỉ đặt dist của nguồn đầu tiên bằng 0.** Các nguồn khác sẽ bị xem như đỉnh bình thường, làm sai kết quả.
3. **Khởi tạo dist bằng 0 cho mọi đỉnh.** Không phân biệt được nguồn với đỉnh chưa tới; dùng sentinel −1 hoặc một mảng visited riêng.
4. **Dùng stack thay queue FIFO.** Chuyển sang DFS không còn bảo đảm khoảng cách lần đầu được phát hiện là ngắn nhất.
5. **Đánh dấu khi dequeue thay vì enqueue mà không kiểm soát bản sao.** Dễ enqueue trùng và làm sai parent/origin khi ghi đè.
6. **Tưởng mỗi nguồn cần chạy một BFS riêng.** Đúng nếu cần kết quả **riêng cho từng nguồn**, nhưng không tối ưu nếu chỉ cần min distance.
7. **Ghi đè dist khi gặp một đường hòa mà không có chính sách tie.** Khoảng cách đúng có thể còn, nhưng parent/origin trở nên không nhất quán nếu không cập nhật cùng nhau.
8. **Nhầm parent với origin.** Parent là đỉnh ngay trước, origin là nguồn đầu đường; phải theo parent nhiều bước mới tới nguồn.
9. **Quên đỉnh không liên thông.** Không phải mọi đỉnh đều được gán; kết quả −1 là thông tin quan trọng.
10. **Lấy maxDistance rồi tuyên bố lan tới toàn đồ thị.** Nếu còn đỉnh bắt buộc unreachable thì không thể hoàn tất.
11. **Không lọc nguồn trùng.** Có thể enqueue một đỉnh nhiều lần và khiến số đo/hàng đợi sai.
12. **Không kiểm tra ID nguồn và cạnh hợp lệ.** Có thể truy cập ngoài mảng hoặc trả kết quả không có nghĩa.
13. **Nhầm đồ thị vô hướng với có hướng.** Không tự thêm cạnh ngược nếu đề quy định cạnh một chiều.
14. **Duyệt theo chiều đi ngược với câu hỏi.** Nếu hỏi từ v tới nguồn trên đồ thị có hướng, phải dùng cạnh đảo.
15. **Dùng BFS cho đường đi có trọng số bất kỳ.** Khi chi phí cạnh không đồng nhất, số cạnh ít nhất không chắc là tổng trọng số nhỏ nhất.
16. **Xem lần phát hiện đầu là nguồn ID nhỏ nhất mà không chứng minh tie-break.** Nó phụ thuộc thứ tự nguồn/cạnh theo cách tổ chức queue.
17. **Cho rằng origin lưu mọi nguồn gần nhất.** Nó chỉ lưu một nguồn; bài liệt kê các nguồn đồng hạng cần thêm dữ liệu.
18. **Sai hướng di chuyển trong grid.** 4 hướng khác 8 hướng; đi chéo khi đề cấm sẽ làm khoảng cách nhỏ hơn sai.
19. **Đếm tường vào số ô unreachable.** Tường không phải ô hợp lệ cần tới; cần phân biệt loại ô.
20. **Nhầm nguồn rỗng với tập nguồn gồm một đỉnh có ID 0.** Danh sách rỗng không sinh bất kỳ khoảng cách 0 nào.
21. **Không sao chép dữ liệu nếu kết quả bị sửa ngoài ý muốn.** Record chứa mảng không bất biến sâu; cần phòng vệ nếu API yêu cầu bất biến.
22. **Không định nghĩa rõ dist cho n=0.** Đồ thị rỗng có mảng kết quả rỗng, không nên tự truy cập phần tử 0.
23. **Quên xử lý self-loop/cạnh lặp.** Với kiểm tra distance[v]!=−1, chúng không phá tính đúng nhưng có thể làm tăng số lần xét cạnh.
24. **So sánh tốc độ mà quên chi phí dựng danh sách kề.** O(N+M) gồm cả xây đồ thị nếu đầu vào dạng danh sách cạnh.

## 16. Bộ kiểm thử có hệ thống

Một triển khai BFS nhiều nguồn nên được thử trên nhiều dạng đồ thị:
- **Một nguồn:** kết quả phải trùng BFS đơn nguồn thông thường.
- **Hai nguồn ở hai đầu đường thẳng:** các lớp sóng gặp nhau ở giữa; với n=7 và nguồn 0,6, kết quả [0,1,2,3,2,1,0].
- **Nguồn ở cạnh nhau:** cả hai vẫn có dist=0, không tự tăng thành 1.
- **Nguồn lặp:** [0,0,3] cho cùng khoảng cách như [0,3].
- **Nguồn đảo thứ tự:** dist không đổi; origin/parent ở đỉnh hòa có thể đổi.
- **Nguồn rỗng:** tất cả đỉnh có dist=−1.
- **Đồ thị rỗng:** mảng kết quả rỗng, không truy cập đỉnh không tồn tại.
- **Đỉnh cô lập:** nếu không phải nguồn, nó không thể tới và có dist=−1; nếu chính nó là nguồn, dist của nó bằng 0.
- **Nhiều thành phần liên thông:** mỗi thành phần có nguồn được lan truyền độc lập, thành phần không nguồn có dist=−1.
- **Đồ thị có cạnh lặp/self-loop:** không enqueue vô hạn nhờ đánh dấu khi phát hiện.
- **Lưới có tường:** không đi xuyên qua '#'; ô gần theo tọa độ có thể cách xa theo đường đi.
- **Lưới tất cả tường và không có nguồn:** không có ô đi được cần lan tới; chính sách báo cáo phụ thuộc bài.
- **Đồ thị có hướng:** đối chiếu hai mục tiêu từ nguồn tới v và từ v tới nguồn để không nhầm chiều.

### Kiểm chứng bằng nhiều BFS đơn nguồn khi đồ thị nhỏ

Với n nhỏ, tạo oracle đơn giản:
1. Chạy BFS riêng từ từng nguồn s.
2. Với mỗi đỉnh v, lấy **minimum** các khoảng cách hữu hạn \(\delta(s,v)\).
3. So sánh với dist[v] từ multi-source BFS.

Nếu không nguồn nào tới v, kết quả oracle là −1. Cách kiểm thử này **đắt hơn khi K lớn**, nhưng rất hữu ích để phát hiện lỗi khởi tạo nguồn, xử lý cạnh có hướng và các trường hợp hòa.

Kiểm tra riêng các đường đi từ parent:
- Đường đi phải bắt đầu ở origin[v] và kết thúc ở v.
- Các đỉnh liên tiếp phải có cạnh hợp lệ theo **đúng chiều**.
- Số cạnh bằng dist[v].
- Nếu v không thể tới, origin[v]=parent[v]=−1.

Các bất biến đó giúp xác nhận cả **chất lượng đường đi**, không chỉ giá trị khoảng cách.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** BFS nhiều nguồn khác BFS đơn nguồn ở bước quan trọng nào?

**Đáp án:** Khởi tạo tất cả nguồn với dist=0 và enqueue **toàn bộ** trước khi xử lý queue. Vòng duyệt hàng đợi sau đó giống BFS đơn nguồn.

**Câu 2.** Tại sao không chạy hết BFS từ nguồn thứ nhất rồi mới đưa nguồn thứ hai vào?

**Đáp án:** Vì các đỉnh đã đánh dấu có thể có đường ngắn hơn từ nguồn thứ hai nhưng không được cập nhật. Khởi tạo đồng thời bảo đảm mọi nguồn cùng tham gia từ lớp 0.

**Câu 3.** Với chuỗi 0--1--2--3--4--5--6 và nguồn {0,6}, dist[5] là bao nhiêu?

**Đáp án:** 1, vì có cạnh 6--5. Giá trị toàn dãy là [0,1,2,3,2,1,0].

**Câu 4.** Với hai nguồn 0 và 3 trong ví dụ 9 đỉnh, dist[7] và origin[7] là gì?

**Đáp án:** dist[7]=2 luôn đúng. Nếu khởi tạo nguồn theo [0,3] và thứ tự kề như đề, origin[7]=0. Đảo nguồn thành [3,0] có thể làm origin[7]=3 mà dist vẫn bằng 2.

**Câu 5.** Tại sao parent[7] không nhất thiết bằng origin[7]?

**Đáp án:** Parent là đỉnh ngay trước 7 trên đường đi ngắn nhất, còn origin là nguồn đầu đường; nếu đường đi có nhiều cạnh thì hai giá trị khác nhau, ví dụ parent[7]=4, origin[7]=0.

**Câu 6.** Một đồ thị có maxDistance=2 nhưng còn đỉnh cần đạt không tới được. Thời gian lan tới toàn bộ là 2 hay không thể?

**Đáp án:** Không thể hoàn tất. MaxDistance=2 chỉ nói về những đỉnh **đã tới được**, không chứng minh đã lan tới mọi đỉnh bắt buộc.

**Câu 7.** Độ phức tạp BFS nhiều nguồn là gì?

**Đáp án:** O(N+M+K) thời gian với N đỉnh, M cạnh và K phần tử trong danh sách nguồn; bộ nhớ O(N+M) nếu xây danh sách kề, hoặc O(N) bổ sung khi danh sách kề đã có.

**Câu 8.** Nếu các cạnh có trọng số dương khác nhau, multi-source BFS FIFO có còn đúng không?

**Đáp án:** Không nói chung. Dùng Dijkstra nhiều nguồn nếu trọng số không âm; nếu chỉ 0 hoặc 1, có thể dùng 0–1 BFS.

**Câu 9.** Trong đồ thị có hướng, muốn mỗi đỉnh v biết đường ngắn nhất **đến** bất kỳ nguồn nào thì làm thế nào?

**Đáp án:** Đảo chiều các cạnh rồi chạy multi-source BFS xuất phát từ các nguồn, vì đường s→v trong đồ thị đảo tương ứng đường v→s trong đồ thị gốc.

**Câu 10.** Tại sao phải kiểm tra visited/dist ngay khi enqueue?

**Đáp án:** Nhờ vậy mỗi đỉnh chỉ được đưa vào queue một lần, không bị gán lại bởi đường đi dài hơn; BFS theo lớp bảo đảm lần phát hiện đầu có khoảng cách ngắn nhất.

**Câu 11.** Một BFS nhiều nguồn có trả khoảng cách từ **từng nguồn riêng lẻ** không?

**Đáp án:** Không. Nó trả min qua mọi nguồn. Để biết khoảng cách riêng từng nguồn, thường phải chạy BFS từng nguồn hoặc dùng phương pháp khác phù hợp.

**Câu 12.** Nếu một ô grid có dist=−1, chắc chắn nó là ô không thể tới được không?

**Đáp án:** Chưa chắc theo ý nghĩa “ô đi được”: trong ví dụ cùng sentinel −1 được dùng cho tường '#'. Phải xem ký tự gốc để phân biệt **tường** và **ô đi được nhưng unreachable**.

**Ghi nhớ:** BFS nhiều nguồn là **một BFS với nhiều đỉnh khởi tạo ở lớp 0**. Hàng đợi FIFO lan tỏa đồng thời, nên dist[v] bằng **số cạnh ít nhất từ một nguồn bất kỳ** đến v. Khởi tạo mọi nguồn trước, đánh dấu khi enqueue, dùng parent/origin khi cần truy vết và cẩn thận với **hòa nguồn, thành phần không tới được, chiều cạnh và trọng số**.

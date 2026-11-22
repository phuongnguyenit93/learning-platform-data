# Khởi tạo trạng thái và duyệt mọi thành phần

Khi học **duyệt đồ thị**, người mới thường viết một hàm `BFS(start)` hoặc `DFS(start)` rồi tin rằng đã “duyệt cả đồ thị”. Điều đó chỉ đúng nếu từ đỉnh `start` có thể đi tới mọi đỉnh cần xét. Trong **đồ thị vô hướng không liên thông**, một lần duyệt chỉ thăm được **một thành phần liên thông**. Những đỉnh ở thành phần khác, kể cả **đỉnh cô lập**, vẫn chưa được xử lý.

Lời giải tổng quát cần hai tầng:

1. **Khởi tạo một bộ trạng thái thống nhất** cho tất cả `n` đỉnh, chẳng hạn `visited` hoặc `componentId=-1`.
2. **Lặp qua tất cả các đỉnh**; khi gặp đỉnh chưa thăm, bắt đầu BFS/DFS từ đỉnh ấy để thăm trọn thành phần mới.

Điểm học tập không chỉ là thêm một vòng `for`: ta cần hiểu **khi nào đánh dấu đã thăm**, làm thế nào giữ state nhất quán, vì sao mỗi đỉnh thuộc đúng một thành phần, cách quản lý `parent`, `distance`, và đặc biệt **không được đánh đồng thành phần liên thông vô hướng với các khái niệm trên đồ thị có hướng**.

Bài học thuộc nhóm **Duyệt đồ thị**. Nội dung dùng Java 17+ và một đồ thị mẫu có thành phần lớn, thành phần nhỏ, khuyên tự thân (*self-loop*), cạnh song song và đỉnh cô lập. Cuối bài có chương trình chạy độc lập, kiểm tra đúng đắn bằng **Disjoint Set Union (DSU)** và **Floyd–Warshall** trên toàn bộ 1.100 đồ thị vô hướng đơn với tối đa năm đỉnh.

## 1. Thành phần liên thông là gì?

Xét đồ thị vô hướng `G=(V,E)`, với `V={0,1,...,n−1}`. Hai đỉnh `u` và `v` được gọi là **liên thông** nếu tồn tại một đường đi từ `u` đến `v`.

Một **thành phần liên thông (connected component)** là một tập đỉnh cực đại sao cho mọi cặp đỉnh trong tập có đường đi nối với nhau. Từ “cực đại” nghĩa là không thể thêm một đỉnh ngoài tập vào mà vẫn giữ được tính chất liên thông.

Trong đồ thị vô hướng, quan hệ “có đường đi nối” có ba tính chất:

- **Phản xạ:** từ `u` tới chính `u` có đường đi độ dài 0.
- **Đối xứng:** có đường từ `u` tới `v` thì đảo chiều đường đi được đường từ `v` tới `u`.
- **Bắc cầu:** có đường `u→v` và `v→w` thì ghép thành đường `u→w`.

Vì vậy các thành phần tạo thành một **phân hoạch của tập đỉnh**: mỗi đỉnh nằm trong **đúng một** thành phần, các thành phần khác nhau **không giao nhau**, hợp của chúng là toàn bộ `V`.

### Ví dụ đồ thị không liên thông

Giả sử `n=11`, các cạnh vô hướng là:

```text
(0,1), (0,2), (1,3), (2,3)
(4,5), (5,6)
(7,7)                    // khuyên tự thân tại 7
(8,9)
(0,1)                    // cạnh song song, lặp lại
                           // đỉnh 10 không có cạnh
```

Nếu bỏ qua cạnh trùng khi xét khái niệm liên thông, năm thành phần là:

```text
C0 = {0,1,2,3}
C1 = {4,5,6}
C2 = {7}
C3 = {8,9}
C4 = {10}
```

**Có 5 thành phần**, không phải 4. Cả `7` và `10` đều tạo thành phần có một đỉnh: khuyên `(7,7)` không kết nối `7` với đỉnh khác, còn đỉnh `10` cô lập hoàn toàn.

Một lần `BFS(0)` hoặc `DFS(0)` chỉ thăm `{0,1,2,3}`. Muốn biết tất cả thành phần cần tiếp tục kiểm tra các đỉnh khác sau khi lần duyệt này kết thúc.

### Cạnh lặp và self-loop không làm nhân đôi đỉnh

Danh sách kề có thể chứa nhiều bản sao của một cạnh, hoặc một đỉnh có cạnh tới chính nó. BFS/DFS phải dùng trạng thái đã thăm để tránh đưa cùng đỉnh vào hàng đợi/stack nhiều lần. Chương trình mẫu giữ nguyên cạnh song song và self-loop trong danh sách kề để chứng minh thuật toán vẫn đúng.

## 2. Định nghĩa dữ liệu và trạng thái trước khi duyệt

Ta quy ước các đỉnh được đánh số từ `0` đến `n−1`. Đồ thị dùng **danh sách kề (adjacency list)**:

```text
adj[u] = danh sách những đỉnh v có cạnh u--v
```

Với cạnh vô hướng `(u,v)` và `u!=v`, thêm:

```text
adj[u].add(v)
adj[v].add(u)
```

Với self-loop `(u,u)`, có thể thêm một mục `u` vào `adj[u]`. Một số biểu diễn đa đồ thị lưu self-loop hai lần; điều đó **không làm thay đổi kết quả duyệt**, miễn logic visited đúng.

### Các mảng trạng thái quan trọng

| Trạng thái | Ý nghĩa | Giá trị khởi tạo |
| --- | --- | --- |
| `visited[v]` | Đỉnh `v` đã được phát hiện chưa? | `false` cho mọi v |
| `componentId[v]` | Chỉ số thành phần chứa `v` | `−1`: chưa thăm |
| `parent[v]` | Cha của `v` trong cây BFS/DFS | `−1`: không có cha |
| `depth[v]` | Số cạnh trên đường từ gốc duyệt tới `v` trong **cây duyệt** | `−1`: chưa biết |
| `components` | Danh sách những nhóm đã tìm được | Danh sách rỗng |
| `queue/stack` | Các đỉnh đang chờ xử lý | Rỗng trước mỗi lần duyệt |

Không nhất thiết phải giữ **cả `visited[]` và `componentId[]`**. Nếu `componentId[v]==−1` được dùng thống nhất làm dấu “chưa phát hiện”, nó có thể thay hoàn toàn `visited[]`.

Ví dụ Java:

```java
int[] componentId = new int[n];
int[] parent = new int[n];
int[] depth = new int[n];

Arrays.fill(componentId, -1);
Arrays.fill(parent, -1);
Arrays.fill(depth, -1);
```

Bắt buộc khởi tạo `componentId` về `−1` nếu giá trị này là sentinel. Mảng `int[]` Java mặc định chứa toàn số 0; nếu kiểm tra `componentId[v] == 0` để nhận biết “chưa thăm”, ta sẽ nhầm với **thành phần mang ID 0**.

Với `n=0`, các mảng rỗng và số thành phần là **0**. Với `n>0` nhưng không có cạnh nào, có **`n` thành phần** gồm một đỉnh mỗi thành phần.

### Giữ gì trên mỗi lần duyệt?

Một lời giải chỉ cần **số thành phần** có thể dùng `visited[]` và một biến `count`. Nếu đề cần in thành phần, ta lưu `componentId[]` hoặc danh sách `components`. Nếu cần dựng đường từ gốc tới một đỉnh, lưu `parent[]`. Nếu cần **khoảng cách ngắn nhất theo số cạnh** từ gốc trong đồ thị không trọng số, dùng **BFS** và `depth[]`; DFS depth **không phải** khoảng cách ngắn nhất.

Đó là nguyên tắc thiết kế: chỉ giữ những trường trạng thái phục vụ mục tiêu, nhưng mọi trường được giữ phải có **nghĩa xác định**.

## 3. Vòng lặp ngoài: chìa khóa để duyệt mọi thành phần

Khuôn giải tổng quát:

```text
khởi tạo visited[v] = false cho mọi v
components = []

for root = 0 .. n-1:
    nếu root đã visited:
        continue

    bắt đầu một nhóm mới
    duyệt BFS hoặc DFS từ root
    mỗi đỉnh vừa phát hiện được gán vào nhóm mới
    kết thúc một lần duyệt -> hoàn thành một thành phần
```

**Bất biến sau mỗi lần BFS/DFS từ một root chưa thăm:** Tất cả những đỉnh thuộc thành phần liên thông của `root` đã được phát hiện và gán cùng một `componentId`. Không có đỉnh từ thành phần khác bị gán nhầm, vì không có cạnh vô hướng nối giữa hai thành phần khác nhau.

**Sau vòng ngoài:** Nếu đỉnh `v` chưa từng thuộc một thành phần đã xử lý, đến lượt `root=v` nó sẽ bắt đầu một lần duyệt mới; vì vậy không đỉnh nào bị bỏ sót.

### Tại sao kiểm tra root phải nằm ngoài BFS/DFS?

Một lỗi rất phổ biến:

```text
BFS(0)
in kết quả
```

Cách này chỉ đúng khi đề **cam kết đồ thị liên thông** hoặc chỉ hỏi những đỉnh có thể đến từ 0. Nếu đề yêu cầu “duyệt tất cả”, “đếm số nhóm liên thông”, “tìm mọi thành phần”, phải có vòng lặp qua tất cả đỉnh.

### Tại sao không khởi tạo visited trong mỗi lần duyệt?

Sai:

```text
for root = 0 .. n-1:
    visited = tất cả false
    BFS(root)
```

Ở cách này, mọi lần duyệt lại quên những gì đã xử lý; cùng một thành phần bị tính lặp rất nhiều lần. Đúng là **khởi tạo một lần trước vòng ngoài** và chỉ reset khi bắt đầu giải một đồ thị/input hoàn toàn mới.

### Cần tạo queue/stack riêng cho từng root không?

Có thể tạo `ArrayDeque` mới mỗi lần gặp root chưa thăm, hoặc dùng lại một deque đã rỗng sau lần trước. Dù chọn cách nào, **bắt đầu một thành phần mới không được mang theo phần tử chờ xử lý của thành phần cũ**. Mã mẫu tạo queue/stack mới trong mỗi lượt để diễn giải rõ ràng.

## 4. BFS từng thành phần: đánh dấu lúc đưa vào hàng đợi

**Breadth-First Search (BFS)** dùng hàng đợi FIFO. Khi phát hiện đỉnh mới, đánh dấu visited **ngay lúc enqueue**. Khi lấy ra khỏi hàng đợi, xử lý các đỉnh kề.

Pseudocode cho đồ thị vô hướng:

```text
componentId[0..n-1] = -1
parent[0..n-1] = -1
depth[0..n-1] = -1
components = []

for root = 0..n-1:
    if componentId[root] != -1:
        continue

    cid = components.size
    order = []
    queue = new FIFO

    componentId[root] = cid
    parent[root] = -1
    depth[root] = 0
    queue.pushBack(root)

    while queue not empty:
        u = queue.popFront()
        order.append(u)

        for v in adj[u]:
            if componentId[v] != -1:
                continue

            componentId[v] = cid
            parent[v] = u
            depth[v] = depth[u] + 1
            queue.pushBack(v)

    components.append(order)
```

### Vì sao visited phải được đặt khi enqueue?

Giả sử có tam giác hoặc chu trình `0–1–3–2–0`. Nếu chỉ đánh dấu lúc **dequeue**, cùng một đỉnh có thể được nhiều hàng xóm đưa vào queue trước khi nó được lấy ra. Với cạnh song song, việc đưa lặp càng dễ xảy ra.

Đánh dấu **tại thời điểm phát hiện** bảo đảm:

- Mỗi đỉnh được enqueue **nhiều nhất một lần**;
- `parent[v]` và `depth[v]` được quyết định đúng lúc tìm thấy đường đầu tiên trong BFS;
- Không cần xử lý nhiều bản sao của cùng một đỉnh trong queue;
- Độ phức tạp duyệt giữ được `O(n+m)` với danh sách kề.

### Khoảng cách BFS

Trong **đồ thị vô hướng không trọng số**, khi bắt đầu từ `root`:

```text
depth[root] = 0
depth[v] = số cạnh ít nhất từ root đến v
```

BFS thăm theo từng lớp khoảng cách 0, 1, 2, ... vì queue FIFO. Khi `v` được phát hiện lần đầu từ `u`, `depth[v]=depth[u]+1` là khoảng cách nhỏ nhất có thể.

**Một chi tiết quan trọng:** `depth[]` ở ví dụ lưu **khoảng cách từ gốc của từng thành phần**, không phải từ một gốc chung của toàn đồ thị. Mọi thành phần mới có gốc và `depth[root]=0` riêng. Không thể so sánh `depth` giữa hai thành phần như khoảng cách giữa các đỉnh: **không tồn tại đường đi** nối chúng.

Nếu đồ thị có trọng số dương/không âm và mục tiêu là tổng trọng số ngắn nhất, BFS thường **không đúng**; cần dùng thuật toán như Dijkstra (trọng số không âm) hoặc thuật toán khác phù hợp. BFS chỉ tối ưu **số cạnh** khi mỗi cạnh coi có cùng chi phí.

## 5. DFS toàn đồ thị: hiểu stack và thứ tự phát hiện

**Depth-First Search (DFS)** đi sâu theo một nhánh trước khi quay về. Có thể viết đệ quy:

```text
dfs(u,cid):
    visited[u] = true
    componentId[u] = cid
    for v in adj[u]:
        if not visited[v]:
            parent[v] = u
            dfs(v,cid)

for root = 0..n-1:
    if not visited[root]:
        bắt đầu thành phần mới
        dfs(root,componentId mới)
```

Nhưng với đồ thị rất lớn như một đường dài hàng trăm nghìn đỉnh, DFS đệ quy Java có thể gây **`StackOverflowError`**. Phiên bản **DFS lặp (iterative DFS)** dùng `ArrayDeque` quản lý stack trên heap, tránh phụ thuộc độ sâu call stack Java.

### Hai kiểu DFS lặp không hoàn toàn giống nhau về thứ tự

**Kiểu A — Stack các đỉnh:** Khi gặp `u`, đẩy các hàng xóm chưa thăm vào stack và đánh dấu visited ngay. Kiểu này vẫn thăm toàn thành phần, nhưng thứ tự phát hiện có thể khác DFS đệ quy vì **nhiều anh em được đánh dấu cùng lúc**.

**Kiểu B — Stack các frame có vị trí hàng xóm tiếp theo:** Mỗi frame lưu `(vertex, nextNeighborIndex)`. Chỉ khám phá **một hàng xóm chưa thăm** rồi đẩy frame con lên stack; khi frame con kết thúc mới tiếp tục hàng xóm tiếp theo của frame cha. Cách này mô phỏng đúng thứ tự phát hiện của DFS đệ quy khi danh sách kề được duyệt theo cùng thứ tự.

Chương trình Java dùng **kiểu B**, vì dễ diễn giải cây DFS và lưu `parent/depth` nhất quán:

```text
DFS iterative from root:
    đánh dấu root, depth[root]=0
    stack.push(Frame(root,nextIndex=0))

    while stack not empty:
        f = stack.peek()
        nếu f đã xét hết hàng xóm:
            stack.pop()
            continue

        v = hàng xóm tiếp theo của f.vertex
        tăng f.nextIndex

        nếu v đã thăm:
            continue

        componentId[v] = cid
        parent[v] = f.vertex
        depth[v] = depth[f.vertex] + 1
        ghi nhận v vào thứ tự phát hiện
        stack.push(Frame(v,0))
```

**DFS depth không phải khoảng cách ngắn nhất.** Với đồ thị `0–1, 0–2, 1–3, 2–3`, nếu duyệt hàng xóm tăng dần:

- BFS từ 0 phát hiện 2 trực tiếp, `depth_BFS[2]=1`.
- DFS có thể đi `0→1→3→2`, nên `depth_DFS[2]=3`.

Cả hai đều duyệt **đúng cùng tập đỉnh**. Sự khác biệt về `parent/depth` không phải lỗi; đó là hai cây duyệt khác nhau.

## 6. Ví dụ đầy đủ: một đồ thị, năm thành phần

Dùng danh sách cạnh ở mục 1 và yêu cầu **sắp danh sách kề tăng dần** để thứ tự duyệt xác định. Một cạnh song song `(0,1)` khiến 1 xuất hiện hai lần trong `adj[0]`, nhưng kiểm tra visited vẫn chỉ nhận một lần.

### BFS qua tất cả đỉnh

```text
Component 0: [0, 1, 2, 3]
Component 1: [4, 5, 6]
Component 2: [7]
Component 3: [8, 9]
Component 4: [10]
```

Mảng `componentId`:

```text
vertex:        0  1  2  3  4  5  6  7  8  9 10
componentId:   0  0  0  0  1  1  1  2  3  3  4
parent BFS:   -1  0  0  1 -1  4  5 -1 -1  8 -1
depth BFS:     0  1  1  2  0  1  2  0  0  1  0
```

Khi một đỉnh có `parent[v]=-1` nhưng `componentId[v]!=-1`, nó là **gốc cây BFS của thành phần**. Trong mẫu này, các gốc là `0,4,7,8,10`.

Để tìm đường đi trong cây BFS từ gốc thành phần tới đỉnh `v`, theo `parent[v]` ngược tới `−1` rồi đảo lại. Với `v=3`: `3→1→0` khi đi ngược, nên đường từ gốc là `0→1→3` có 2 cạnh.

### DFS lặp mô phỏng đệ quy

Thứ tự phát hiện trong mỗi thành phần:

```text
[0, 1, 3, 2]
[4, 5, 6]
[7]
[8, 9]
[10]
```

Mảng componentId của DFS vẫn giống BFS vì **thành phần liên thông là thuộc tính của đồ thị, không phụ thuộc thuật toán/thứ tự duyệt**. Nhưng parent/depth của DFS khác:

```text
parent DFS:   -1  0  3  1 -1  4  5 -1 -1  8 -1
depth DFS:     0  1  3  2  0  1  2  0  0  1  0
```

Nút 2 có độ sâu DFS bằng 3 nhưng khoảng cách ngắn nhất từ 0 chỉ là 1. Do đó không sử dụng chiều sâu cây DFS làm khoảng cách ngắn nhất theo số cạnh.

### Kích thước thành phần

Các kích thước là `[4,3,1,2,1]`; tổng `4+3+1+2+1=11=n`. Đây là một **bất biến kiểm tra nhanh**: mỗi đỉnh được tính đúng một lần nên tổng kích thước mọi thành phần phải bằng số đỉnh.

Nếu một chương trình trả tổng kích thước khác `n`, thường đã bỏ sót đỉnh cô lập, đếm trùng một đỉnh do visited sai, hoặc khởi tạo/reset state không nhất quán.

## 7. Chứng minh thuật toán duyệt mọi thành phần là đúng

### Mệnh đề 1 — BFS/DFS không bỏ sót đỉnh có thể tới gốc

Giả sử đỉnh `v` nằm trong cùng thành phần với gốc `root`. Có đường đi:

```text
root = v0 -- v1 -- v2 -- ... -- vk = v
```

Khi xử lý `v0`, thuật toán xem mọi hàng xóm và phát hiện `v1` nếu chưa được phát hiện. Theo quy nạp trên chiều dài đường đi, mỗi `vi` được phát hiện và rồi xử lý; do đó `v` được phát hiện.

BFS dùng queue, DFS dùng stack, nhưng cả hai đều **xét mọi cạnh kề của đỉnh đã phát hiện** trước khi kết thúc lượt duyệt.

### Mệnh đề 2 — Một lần duyệt không lạc sang thành phần khác

Mọi bước phát hiện mới đều đi qua một cạnh `(u,v)` từ một đỉnh `u` đã thuộc thành phần của `root`. Khi đó `v` cũng có đường từ `root` qua `u` rồi tới `v`. Vì vậy `v` không thể thuộc thành phần liên thông khác.

Đồ thị có self-loop hoặc cạnh song song không làm lập luận sai: chúng vẫn chỉ nối các đỉnh đang có đường đi, và visited ngăn việc phát hiện lặp.

### Mệnh đề 3 — Vòng ngoài tạo mỗi thành phần đúng một lần

Sau khi lượt duyệt từ `root` kết thúc, theo mệnh đề 1 và 2, **toàn bộ** thành phần của gốc đã đánh dấu. Khi vòng ngoài gặp một đỉnh của thành phần đó, nó đã visited nên bị bỏ qua. Nếu một đỉnh chưa visited được gặp, nó **không thuộc** bất kỳ thành phần đã xử lý nào, nên bắt đầu một thành phần mới.

Vì vòng ngoài xét mọi đỉnh `0..n−1`, cuối cùng không đỉnh nào chưa thăm. Các nhóm tạo thành phân hoạch chính xác của đồ thị.

### Mệnh đề 4 — BFS cho khoảng cách ít cạnh nhất

BFS xử lý đỉnh theo các lớp độ sâu không giảm vì queue FIFO. Nếu `v` được phát hiện lần đầu qua `u` ở lớp `d`, một đường tới `v` ngắn hơn `d+1` sẽ phải có đỉnh trước đó ở lớp nhỏ hơn đã được xử lý trước, mâu thuẫn với việc `v` chưa phát hiện. Do đó `depth[v]=depth[u]+1` đúng bằng độ dài đường đi ngắn nhất từ gốc của thành phần.

Lập luận này **không áp dụng cho DFS depth**, vì DFS ưu tiên đi sâu thay vì theo lớp.

### Kết thúc

Mỗi đỉnh chuyển từ chưa thăm sang đã thăm **nhiều nhất một lần**. Mỗi đỉnh đã thăm được đưa vào queue hoặc stack **một lần** trong các triển khai mẫu; mọi lượt duyệt xét hữu hạn phần tử trong danh sách kề. Vòng ngoài có đúng `n` lần xét gốc. Thuật toán dừng.

## 8. Đồ thị có hướng: đừng gọi forest là thành phần mạnh/yếu

Với **đồ thị có hướng**, quan hệ “có đường đi từ `u` tới `v`” **không nhất thiết đối xứng**. Chạy:

```text
for root = 0 .. n-1:
    nếu root chưa thăm:
        BFS/DFS theo cạnh có hướng từ root
```

vẫn là một cách **phát hiện toàn bộ đỉnh** và dựng **rừng tìm kiếm theo thứ tự gốc**, nhưng các nhóm trong rừng này **không nhất thiết là** thành phần liên thông yếu hoặc mạnh.

### Thành phần liên thông yếu (*weakly connected component*)

Bỏ hướng của mọi cạnh rồi xét liên thông theo định nghĩa vô hướng. Có thể:

1. Từ các cạnh có hướng `u→v`, dựng danh sách kề của đồ thị vô hướng bằng cách thêm cả hai chiều;
2. Chạy vòng ngoài BFS/DFS như bài này.

Kết quả là các **thành phần liên thông yếu**. Không nên gọi nhầm là thành phần mạnh.

### Thành phần liên thông mạnh (*strongly connected component – SCC*)

Hai đỉnh `u,v` cùng một SCC khi:

```text
u có đường có hướng tới v
VÀ
v có đường có hướng tới u
```

Để phân rã thành SCC, dùng thuật toán chuyên biệt như **Kosaraju** hoặc **Tarjan**, không chỉ chạy vòng ngoài BFS/DFS theo hướng cạnh gốc.

### Phản ví dụ chỉ có ba đỉnh

Các cạnh có hướng:

```text
0 -> 1
2 -> 1
```

Nếu quét root tăng dần và đi theo cạnh có hướng, các nhóm của rừng BFS là:

```text
[0,1]
[2]
```

Nhưng bỏ hướng cạnh, tất cả `0,1,2` nối với nhau qua đỉnh 1, nên chỉ có **một thành phần yếu `{0,1,2}`**. Các SCC thực tế là **`{0}`, `{1}`, `{2}`**, vì không có chu trình hướng nối ngược hai đỉnh khác nhau.

**Cảnh báo:** Thứ tự quét gốc có thể thay đổi cách gom nhóm của rừng duyệt có hướng, nên không thể dùng số nhóm đó thay cho số SCC hay số thành phần yếu.

Một đồ thị có hướng mà mọi cạnh đều được thêm hai chiều đối xứng có thể được coi như vô hướng để phân thành phần; nhưng đó là một **giả định riêng của input**, không phải đặc tính chung của đồ thị có hướng.

## 9. Độ phức tạp và biểu diễn đồ thị

Cho `n=|V|` và `m=|E|` (với đồ thị vô hướng có thể lưu mỗi cạnh hai lần trong danh sách kề):

- **BFS/DFS toàn đồ thị bằng adjacency list:** `O(n+m)` thời gian, vì mỗi đỉnh phát hiện tối đa một lần và mỗi mục cạnh được xét hữu hạn lần.
- **Trạng thái visited/componentId/parent/depth:** `O(n)` bộ nhớ.
- **Queue/stack:** nhiều nhất `O(n)` đỉnh/frame.
- **Danh sách các thành phần:** `O(n)` phần tử đỉnh được lưu, ngoài cấu trúc danh sách kề.
- **Adjacency list:** `O(n+m)` bộ nhớ khi tính các mục cạnh được lưu.
- **Adjacency matrix:** `O(n²)` bộ nhớ; nếu mỗi lần xử lý một đỉnh đều quét `n` cột, duyệt toàn đồ thị `O(n²)` thời gian kể cả khi đồ thị rất thưa.

Mã Java mẫu **sắp danh sách kề để có thứ tự phát hiện xác định**, nên bước dựng/sắp ban đầu có chi phí bổ sung:

```text
O(n + m) để tạo danh sách kề,
O(sum_v degree(v) * log(max(1,degree(v)))) để sort,
sau đó O(n + m) để duyệt.
```

Có thể viết cận đơn giản là **`O(n+m log m)`** khi `m>1`, nhưng trong môi trường thực tế thứ tự đầu vào có thể được giữ nguyên nếu đề không yêu cầu thứ tự duyệt cụ thể. BFS/DFS **không cần sort** để đúng về tập đỉnh/thành phần, chỉ cần sort khi muốn kiểm soát thứ tự thăm hoặc in kết quả.

### Cạnh song song và self-loop

Trong đa đồ thị, `m` đếm cả các cạnh song song. Thời gian `O(n+m)` vẫn đúng theo **số mục cạnh được duyệt**. Cạnh trùng làm tăng chi phí đọc cạnh nhưng không tăng số đỉnh phát hiện vì mỗi đỉnh chỉ được đánh dấu một lần.

Một đỉnh có self-loop vẫn là một đỉnh; self-loop không tạo đường đến đỉnh khác. **Không nên biến mỗi self-loop thành một thành phần mới**, vì thành phần được xác định bởi **đỉnh**, không phải cạnh.

### Khi đồ thị quá lớn

Dùng **DFS lặp** để tránh phụ thuộc call stack Java. Dùng `ArrayDeque<Integer>` cho BFS thay vì `LinkedList` khi chỉ cần queue, tránh cấp phát nút liên kết riêng. Nếu cần lưu hàng triệu cạnh, chú ý overhead của `ArrayList<Integer>` và boxing `Integer`; cấu trúc mảng `head/to/next` hoặc CSR (*compressed sparse row*) có thể tiết kiệm bộ nhớ hơn.

Nếu input là một tập đỉnh lớn được gán nhãn chuỗi, cần ánh xạ nhãn sang chỉ số 0..n−1 trước; đừng giả định các nhãn số bất kỳ là chỉ số mảng liên tiếp.

## 10. Chọn cấu trúc và biến thể phù hợp với mục tiêu

| Mục tiêu | Thông tin trạng thái cốt lõi | Cách làm |
| --- | --- | --- |
| Chỉ hỏi đồ thị vô hướng có liên thông không | visited + một lượt BFS/DFS | Từ một đỉnh bất kỳ nếu `n>0`, xem có thăm đủ `n` đỉnh không |
| Đếm số thành phần | visited, count | Vòng ngoài, mỗi root chưa thăm tăng count |
| Liệt kê đỉnh theo thành phần | componentId + components | Mỗi lượt duyệt ghi một nhóm mới |
| Tìm kích thước thành phần | componentId hoặc nhóm và size | Đếm số đỉnh phát hiện trong từng lượt |
| Kiểm tra hai đỉnh có liên thông | componentId | So sánh ID sau khi phân rã (đồ thị vô hướng) |
| Đường ngắn nhất theo **số cạnh** từ gốc | BFS distance + parent | Mỗi thành phần có gốc riêng khi duyệt toàn bộ |
| Duyệt sâu, kiểm tra chu trình, phân loại cạnh | DFS + visited + trạng thái bổ sung | Quy tắc phát hiện chu trình khác nhau giữa đồ thị vô hướng/có hướng |
| Nhiều thao tác thêm cạnh, truy vấn liên thông | DSU/Union-Find | Hữu ích cho đồ thị vô hướng **chỉ thêm cạnh**; không tự hỗ trợ xóa cạnh |
| Tìm thành phần yếu của đồ thị có hướng | Bỏ hướng rồi BFS/DFS | Mỗi cạnh `u→v` cho phép đi cả hai chiều |
| Tìm thành phần mạnh của đồ thị có hướng | Kosaraju/Tarjan | Đòi tính reachability hai chiều trong cùng SCC |

### DSU và BFS/DFS khác nhau thế nào?

DSU (*Disjoint Set Union*, *Union-Find*) xây quan hệ liên thông bằng các phép `union(u,v)` với mọi cạnh vô hướng. Sau đó hai đỉnh liên thông nếu `find(u)==find(v)`.

**Ưu điểm:** DSU thường rất gọn cho truy vấn liên thông sau các phép **thêm cạnh** và cho phép dùng như một **oracle độc lập** để kiểm tra BFS/DFS.

**Hạn chế:** DSU không cho sẵn thứ tự duyệt, cây cha BFS, hay khoảng cách ngắn nhất. Với đồ thị có hướng, DSU trên cạnh `u→v` sẽ cho liên thông **yếu** nếu bỏ hướng, không cho SCC.

Bài học Java dùng DSU để đối chiếu **phân hoạch** thành phần; kiểm tra khoảng cách BFS bằng thuật toán khác, chứ không dùng DSU để suy đoán khoảng cách.

## 11. Java 17+ — BFS/DFS mọi thành phần và kiểm thử

Chương trình **GraphComponentsDemo.java** có:

1. Hàm tạo đồ thị vô hướng/có hướng từ danh sách cạnh `int[][]`, xác thực `n` và đầu mút, cho phép self-loop/cạnh song song.
2. Hàm `bfsAll`: duyệt vòng ngoài mọi root, gán `componentOf/parent/depth`, ghi nhóm theo thứ tự lấy khỏi queue.
3. Hàm `dfsAll`: dùng stack frame có chỉ số hàng xóm tiếp theo để mô phỏng DFS đệ quy, không dùng recursion.
4. Một ví dụ **11 đỉnh, 5 thành phần**, in chính xác thứ tự, parent và depth.
5. Phản ví dụ **đồ thị có hướng** để phân biệt rừng duyệt và thành phần yếu.
6. Bộ kiểm thử độc lập **`verifyAllSmallGraphs`**: duyệt mọi đồ thị vô hướng đơn với `n=0..5`, so phân hoạch BFS/DFS với DSU; kiểm tra depth BFS qua Floyd–Warshall; xác minh parent là cạnh hợp lệ và depth của con bằng cha + 1.
7. Kiểm tra thêm đồ thị mẫu có self-loop và cạnh song song.

### Toàn bộ mã nguồn: GraphComponentsDemo.java

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class GraphComponentsDemo {
    record Graph(int n, List<List<Integer>> adjacent) {}

    record Walk(int[] componentOf, int[] parent, int[] depth,
                List<List<Integer>> components) {}

    // directed=false: cạnh hai chiều; directed=true: giữ hướng.
    // Không sửa danh sách cạnh của caller.
    static Graph fromEdges(int n, int[][] edges, boolean directed) {
        if (n < 0 || edges == null) {
            throw new IllegalArgumentException("bad graph size/edges");
        }

        List<List<Integer>> a = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            a.add(new ArrayList<>());
        }

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException("edge needs u,v");
            }
            int u = edge[0], v = edge[1];
            if (u < 0 || v < 0 || u >= n || v >= n) {
                throw new IllegalArgumentException(
                    "edge endpoint outside [0,n)");
            }

            a.get(u).add(v);
            if (!directed && u != v) {
                a.get(v).add(u);
            }
        }

        // Cố định thứ tự kề để output BFS/DFS xác định.
        for (int u = 0; u < n; u++) {
            Collections.sort(a.get(u));
            a.set(u, List.copyOf(a.get(u)));
        }
        return new Graph(n, List.copyOf(a));
    }

    static Walk bfsAll(Graph g) {
        int n = g.n();
        int[] id = new int[n];
        int[] parent = new int[n];
        int[] depth = new int[n];
        Arrays.fill(id, -1);
        Arrays.fill(parent, -1);
        Arrays.fill(depth, -1);

        List<List<Integer>> components = new ArrayList<>();

        for (int root = 0; root < n; root++) {
            if (id[root] != -1) {
                continue;
            }

            int cid = components.size();
            List<Integer> order = new ArrayList<>();
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            id[root] = cid;
            depth[root] = 0;
            queue.addLast(root);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                order.add(u);

                for (int v : g.adjacent().get(u)) {
                    if (id[v] != -1) {
                        continue;
                    }
                    // Đánh dấu ngay lúc enqueue.
                    id[v] = cid;
                    parent[v] = u;
                    depth[v] = depth[u] + 1;
                    queue.addLast(v);
                }
            }
            components.add(List.copyOf(order));
        }

        return new Walk(id, parent, depth, List.copyOf(components));
    }

    static final class Frame {
        final int vertex;
        int nextNeighbor;

        Frame(int vertex) {
            this.vertex = vertex;
        }
    }

    // Stack frame mô phỏng đúng thứ tự khám phá DFS đệ quy.
    static Walk dfsAll(Graph g) {
        int n = g.n();
        int[] id = new int[n];
        int[] parent = new int[n];
        int[] depth = new int[n];
        Arrays.fill(id, -1);
        Arrays.fill(parent, -1);
        Arrays.fill(depth, -1);

        List<List<Integer>> components = new ArrayList<>();

        for (int root = 0; root < n; root++) {
            if (id[root] != -1) {
                continue;
            }

            int cid = components.size();
            List<Integer> order = new ArrayList<>();
            ArrayDeque<Frame> stack = new ArrayDeque<>();
            id[root] = cid;
            depth[root] = 0;
            order.add(root);
            stack.push(new Frame(root));

            while (!stack.isEmpty()) {
                Frame top = stack.peek();
                List<Integer> neighbors =
                    g.adjacent().get(top.vertex);

                if (top.nextNeighbor == neighbors.size()) {
                    stack.pop();
                    continue;
                }

                int v = neighbors.get(top.nextNeighbor++);
                if (id[v] != -1) {
                    continue;
                }

                id[v] = cid;
                parent[v] = top.vertex;
                depth[v] = depth[top.vertex] + 1;
                order.add(v);
                stack.push(new Frame(v));
            }

            components.add(List.copyOf(order));
        }

        return new Walk(id, parent, depth, List.copyOf(components));
    }

    static final class DSU {
        private final int[] leader;

        DSU(int n) {
            leader = new int[n];
            for (int i = 0; i < n; i++) {
                leader[i] = i;
            }
        }

        int find(int x) {
            while (leader[x] != x) {
                leader[x] = leader[leader[x]];
                x = leader[x];
            }
            return x;
        }

        void unite(int a, int b) {
            int ra = find(a), rb = find(b);
            if (ra != rb) {
                leader[ra] = rb;
            }
        }
    }

    // Oracle độc lập cho khoảng cách trong đồ thị nhỏ.
    // Self-loop không được ghi đè khoảng cách d[i][i] = 0.
    static int[][] floydShortest(Graph g) {
        int n = g.n();
        int inf = 1_000_000;
        int[][] d = new int[n][n];

        for (int i = 0; i < n; i++) {
            Arrays.fill(d[i], inf);
            d[i][i] = 0;
            for (int v : g.adjacent().get(i)) {
                d[i][v] = Math.min(d[i][v], 1);
            }
        }

        for (int k = 0; k < n; k++) {
            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) {
                    d[i][j] = Math.min(
                        d[i][j], d[i][k] + d[k][j]);
                }
            }
        }
        return d;
    }

    // Dùng cho đồ thị vô hướng: so với DSU và Floyd,
    // kiểm tra cây cha của cả BFS và DFS.
    static void verifyUndirected(Graph g, int[][] edges) {
        Walk bfs = bfsAll(g);
        Walk dfs = dfsAll(g);
        int n = g.n();

        DSU dsu = new DSU(n);
        for (int[] edge : edges) {
            dsu.unite(edge[0], edge[1]);
        }
        int[][] shortest = floydShortest(g);

        if (bfs.components().size() != dfs.components().size()) {
            throw new AssertionError("different component count");
        }

        for (int v = 0; v < n; v++) {
            int rootBfs =
                bfs.components().get(bfs.componentOf()[v]).get(0);
            int rootDfs =
                dfs.components().get(dfs.componentOf()[v]).get(0);

            // Trong BFS, depth là đường đi ít cạnh nhất từ root.
            if (bfs.depth()[v] != shortest[rootBfs][v]) {
                throw new AssertionError("BFS shortest path");
            }

            for (Walk walk : new Walk[]{bfs, dfs}) {
                int root = walk == bfs ? rootBfs : rootDfs;
                int p = walk.parent()[v];

                if (v == root) {
                    if (p != -1 || walk.depth()[v] != 0) {
                        throw new AssertionError("root metadata");
                    }
                } else {
                    if (p < 0
                            || !g.adjacent().get(p).contains(v)
                            || walk.componentOf()[p]
                               != walk.componentOf()[v]
                            || walk.depth()[v]
                               != walk.depth()[p] + 1) {
                        throw new AssertionError("tree parent/depth");
                    }
                }
            }

            for (int u = 0; u < n; u++) {
                boolean expected = dsu.find(u) == dsu.find(v);
                boolean sameBfs = bfs.componentOf()[u]
                                  == bfs.componentOf()[v];
                boolean sameDfs = dfs.componentOf()[u]
                                  == dfs.componentOf()[v];

                if (sameBfs != expected || sameDfs != expected) {
                    throw new AssertionError("wrong partition");
                }
            }
        }
    }

    // Tất cả đồ thị vô hướng đơn n=0..5:
    // 1+1+2+8+64+1024 = 1100 đồ thị.
    static int verifyAllSmallGraphs() {
        int checked = 0;

        for (int n = 0; n <= 5; n++) {
            List<int[]> possible = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = u + 1; v < n; v++) {
                    possible.add(new int[]{u, v});
                }
            }

            int graphs = 1 << possible.size();
            for (int bits = 0; bits < graphs; bits++) {
                List<int[]> chosen = new ArrayList<>();
                for (int e = 0; e < possible.size(); e++) {
                    if ((bits & (1 << e)) != 0) {
                        chosen.add(possible.get(e));
                    }
                }
                int[][] edges =
                    chosen.toArray(new int[0][]);
                Graph g = fromEdges(n, edges, false);
                verifyUndirected(g, edges);
                checked++;
            }
        }
        return checked;
    }

    public static void main(String[] args) {
        int[][] edges = {
            {0,1}, {0,2}, {1,3}, {2,3},
            {4,5}, {5,6}, {7,7}, {8,9}, {0,1}
        };
        Graph g = fromEdges(11, edges, false);
        Walk bfs = bfsAll(g);
        Walk dfs = dfsAll(g);

        List<Integer> sizes = new ArrayList<>();
        for (List<Integer> group : bfs.components()) {
            sizes.add(group.size());
        }

        System.out.println("BFS components: "
                           + bfs.components());
        System.out.println("Component sizes: " + sizes);
        System.out.println("BFS componentId: "
                           + Arrays.toString(bfs.componentOf()));
        System.out.println("BFS parent: "
                           + Arrays.toString(bfs.parent()));
        System.out.println("BFS depth: "
                           + Arrays.toString(bfs.depth()));

        System.out.println("DFS components: "
                           + dfs.components());
        System.out.println("DFS parent: "
                           + Arrays.toString(dfs.parent()));
        System.out.println("DFS depth: "
                           + Arrays.toString(dfs.depth()));

        int[][] directedEdges = {{0,1}, {2,1}};
        Graph directed = fromEdges(3, directedEdges, true);
        Graph undirectedView =
            fromEdges(3, directedEdges, false);

        System.out.println("Directed search forest: "
                           + bfsAll(directed).components());
        System.out.println("Weak components: "
                           + bfsAll(undirectedView).components());

        verifyUndirected(g, edges);
        System.out.println("Exhaustive undirected graphs n<=5: "
                           + verifyAllSmallGraphs() + " OK");
    }
}
```

### Biên dịch và chạy

Lưu đúng tên **GraphComponentsDemo.java**, rồi chạy bằng **JDK 17 hoặc mới hơn**:

```bash
javac -encoding UTF-8 GraphComponentsDemo.java
java GraphComponentsDemo
```

**Stdout dự kiến** (thứ tự xác định vì danh sách kề đã được sắp tăng):

```text
BFS components: [[0, 1, 2, 3], [4, 5, 6], [7], [8, 9], [10]]
Component sizes: [4, 3, 1, 2, 1]
BFS componentId: [0, 0, 0, 0, 1, 1, 1, 2, 3, 3, 4]
BFS parent: [-1, 0, 0, 1, -1, 4, 5, -1, -1, 8, -1]
BFS depth: [0, 1, 1, 2, 0, 1, 2, 0, 0, 1, 0]
DFS components: [[0, 1, 3, 2], [4, 5, 6], [7], [8, 9], [10]]
DFS parent: [-1, 0, 3, 1, -1, 4, 5, -1, -1, 8, -1]
DFS depth: [0, 1, 3, 2, 0, 1, 2, 0, 0, 1, 0]
Directed search forest: [[0, 1], [2]]
Weak components: [[0, 1, 2]]
Exhaustive undirected graphs n<=5: 1100 OK
```

### Vì sao các con số khớp?

- **BFS components** gồm đúng năm nhóm, kể cả `[7]` có self-loop và `[10]` cô lập.
- **Component sizes** cộng lại bằng `11`.
- **BFS parent/depth** cho thấy đường từ 0 tới 2 dài một cạnh, đường từ 0 tới 3 dài hai cạnh.
- **DFS components** có cùng tập đỉnh trong từng nhóm, nhưng thứ tự riêng của nhóm đầu là `[0,1,3,2]`. DFS depth của 2 bằng 3 do cây DFS đi qua 0→1→3→2.
- **Directed search forest** chỉ là kết quả của thuật toán “quét mọi root theo thứ tự rồi đi theo cạnh hướng”. Hai nhóm `[0,1]` và `[2]` không phải phân hoạch thành phần yếu/mạnh của đồ thị có hướng.
- **Weak components** thu được khi bỏ chiều cạnh, nên cả ba đỉnh thuộc cùng nhóm.
- **Exhaustive 1100**: tất cả đồ thị vô hướng đơn với 0..5 đỉnh. Mỗi đồ thị được kiểm tra bằng hai thuật toán duyệt và DSU, cùng đối chiếu **khoảng cách BFS với Floyd–Warshall**. Đồ thị mẫu có self-loop/cạnh song song được kiểm thêm riêng vì các đồ thị “đơn” trong tập exhaustive không chứa hai dạng cạnh đó.

### Những chi tiết triển khai cần chú ý

**Không sửa đầu vào:** Hàm `fromEdges` chỉ đọc `int[][] edges`; nó tạo các danh sách kề mới và sắp xếp các danh sách đó. Không sort hoặc thay phần tử trong mảng cạnh của caller.

**Vòng ngoài dùng chung state:** Mảng `componentOf[]` được khởi tạo về `−1` **một lần** trước khi duyệt toàn đồ thị. Sau khi kết thúc một thành phần, các giá trị đã gán được giữ nguyên cho lần duyệt tiếp.

**BFS visited on enqueue:** `id[v]=cid` được gán trước `queue.addLast(v)`. Điều này tránh xếp hàng lặp do chu trình hoặc cạnh song song.

**DFS iterative với frame:** `Frame.nextNeighbor` nhớ vị trí kề sẽ xét tiếp khi nhánh con hoàn tất. Vì vậy thứ tự khám phá trùng quy tắc DFS đệ quy khi các hàng xóm được sắp tăng, nhưng không dùng đệ quy Java.

**Bộ kiểm thử độc lập:** DSU không dùng BFS/DFS; Floyd–Warshall cũng không dùng thứ tự queue của BFS. Nếu cả BFS và DFS đều có cùng lỗi phân nhóm, việc so với DSU vẫn có khả năng phát hiện. Nếu cả hai tính sai chiều sâu, kiểm tra Floyd và cạnh cha giúp phát hiện.

**Giới hạn của kiểm thử:** Tập exhaustive 1100 đồ thị nhỏ không thay thế chứng minh cho mọi `n,m`; trên hệ thống thực cần thêm test ngẫu nhiên lớn, đồ thị dạng đường dài, rất nhiều cạnh song song và đầu vào quá lớn so với bộ nhớ.

## 12. Cách xử lý các tình huống biên

### Đồ thị rỗng

`n=0`, danh sách cạnh rỗng. Vòng ngoài không chạy, danh sách `components` rỗng, số thành phần **0**. Không được tự tạo một thành phần rỗng rồi in count=1.

### Không có cạnh nhưng có đỉnh

`n=4`, `edges=[]`. Kết quả:

```text
[[0], [1], [2], [3]]
```

Tất cả đỉnh đều cô lập, mỗi đỉnh là một thành phần.

### Đồ thị liên thông

`n=4`, cạnh `(0,1),(1,2),(2,3)`. Bắt đầu từ root 0 sẽ thăm hết bốn đỉnh, nên các root 1,2,3 bị bỏ qua. Có **1 thành phần**.

### Đỉnh có self-loop

`n=2`, chỉ cạnh `(0,0)`. Hai thành phần là `[0]` và `[1]`. Self-loop ở 0 không tạo liên kết tới 1, cũng không khiến BFS/DFS bị lặp vô hạn vì 0 đã visited.

### Cạnh song song

`n=2`, hai cạnh `(0,1),(0,1)`. Chỉ có **1 thành phần `{0,1}`**, không phải 2. Khi duyệt adjacency list, hàng xóm 1 có thể xuất hiện hai lần, nhưng `componentOf[1]` đã được gán ngay trong lần phát hiện đầu.

### Đỉnh không thuộc miền

`n=3`, cạnh `(0,3)` là dữ liệu không hợp lệ vì chỉ số hợp lệ là 0,1,2. Code ném `IllegalArgumentException`; không im lặng bỏ cạnh nếu không có hợp đồng cho phép.

### Hai nguồn truy vấn khác nhau

Nếu cần đường ngắn nhất từ một nguồn `s` duy nhất, chạy BFS từ `s` rồi giữ các đỉnh không tới được với `distance=-1` hoặc `INF`. Khi chạy BFS **mọi thành phần**, mỗi thành phần lại có một **root riêng** và depth reset về 0 tại root mới. Không dùng `depth` của forest để trả “khoảng cách từ s” tới các đỉnh ở thành phần khác.

### Giao diện có nhãn đỉnh dạng chuỗi

Các nhãn như `"Hà Nội"`, `"Đà Nẵng"` không trực tiếp là chỉ số mảng. Có thể dùng `Map<String,Integer>` để ánh xạ từng nhãn tới một số 0..n−1, xây graph trên chỉ số rồi ánh xạ kết quả ngược để in. Cẩn thận chọn thứ tự duyệt root theo yêu cầu đề: theo thứ tự nhập, theo tên, hoặc theo ID đã gán.

## 13. Lỗi phổ biến cần tránh

**1. Chỉ gọi `BFS(0)` và coi là duyệt xong.** Đồ thị có thể không liên thông; phải có vòng ngoài trên mọi đỉnh khi mục tiêu là mọi thành phần.

**2. Reset visited trong mỗi lượt root.** Cùng một thành phần sẽ bị duyệt và đếm lặp. Khởi tạo một lần cho mỗi bài toán/đồ thị.

**3. Quên khởi tạo `componentId[]=-1`.** Mảng Java mặc định 0, trùng ID thành phần đầu tiên. Dùng sentinel không xung đột với ID hợp lệ.

**4. Đánh dấu visited quá muộn trong BFS.** Nếu chỉ đánh dấu khi dequeue, các hàng xóm khác có thể enqueue cùng đỉnh nhiều lần. Đánh dấu lúc **enqueue**.

**5. Bỏ sót đỉnh cô lập.** Chỉ duyệt qua danh sách cạnh rồi tạo trạng thái cho các đầu mút sẽ bỏ các đỉnh không có cạnh. Phải lấy `n` từ đề và tạo đủ `0..n−1`.

**6. Quên chiều ngược của cạnh vô hướng.** Với cạnh `(u,v)`, phải cho phép đi từ u tới v và từ v tới u. Nếu chỉ thêm một chiều, phân hoạch liên thông có thể sai.

**7. Nhầm DFS depth với đường đi ngắn nhất.** DFS ưu tiên đi sâu, khoảng cách cây DFS không nhất thiết nhỏ nhất; dùng BFS cho đồ thị không trọng số.

**8. Dùng recursive DFS cho đường đi cực dài mà không xét stack.** Có thể gây `StackOverflowError` trên Java. Bản iterative với `ArrayDeque` an toàn hơn về call stack.

**9. Dùng queue FIFO nhưng gọi là DFS, hoặc stack LIFO nhưng gọi là BFS.** Hai cách có thứ tự khám phá và ý nghĩa depth khác nhau.

**10. Quên xử lý cạnh trùng và self-loop qua visited.** Mỗi đỉnh chỉ nên được phát hiện một lần dù adjacency chứa nhiều mục giống nhau.

**11. So sánh thứ tự in hai thuật toán rồi cho rằng phân hoạch sai.** BFS và DFS có thể in thứ tự khác nhau, nhưng các tập đỉnh thành phần vẫn phải giống nhau. Khi test, hãy so **quan hệ cùng thành phần**, không nhất thiết so thứ tự traversal.

**12. Gọi các nhóm BFS của đồ thị có hướng là SCC.** Reachability có hướng không đối xứng; dùng Tarjan/Kosaraju cho SCC, bỏ hướng cạnh nếu cần weak components.

**13. Nhầm forest BFS với một BFS từ nguồn cố định.** Depth của mỗi root mới là 0; các thành phần khác nhau không có khoảng cách hữu hạn giữa các đỉnh.

**14. Dùng `Integer` boxing và cấp phát danh sách lớn mà không ước lượng RAM.** Với đồ thị cực lớn, cần biểu diễn kề tiết kiệm bộ nhớ hơn.

**15. Không xác thực chỉ số đầu mút.** Cạnh `(u,v)` với u/v ngoài `0..n−1` phải được phát hiện trước khi thêm vào danh sách kề.

**16. Không xác định liệu input là đồ thị đơn hay đa đồ thị.** Cạnh song song làm số mục adjacency tăng; không tự suy ra số cạnh từ tổng bậc mà không biết cách lưu self-loop.

**17. Tưởng sort adjacency là điều kiện bắt buộc của BFS/DFS.** Sort chỉ ảnh hưởng **thứ tự** thăm, không phải tính đúng của tập đỉnh. Với bài không yêu cầu thứ tự, có thể giữ nguyên thứ tự input.

**18. Dùng DSU để lấy khoảng cách.** DSU chỉ lưu nhóm liên thông, không cho đường đi ngắn nhất; để tìm khoảng cách theo số cạnh dùng BFS.

## 14. Bài tập tự luyện

**Bài 1 — Đồ thị không cạnh.** Với `n=6` và `E=∅`, có bao nhiêu thành phần? Viết `componentId` và `depth` nếu root được quét tăng từ 0.

**Bài 2 — Năm nhóm.** Dùng đồ thị 11 đỉnh ở mục 1, tự chạy BFS từng nhóm. Vì sao `[7]` và `[10]` là hai thành phần riêng, dù một đỉnh có self-loop và một đỉnh cô lập?

**Bài 3 — Tầng BFS.** Với cạnh `(0,1),(0,2),(1,3),(2,3)`, tính `parent` và `depth` của BFS từ 0. Vì sao `depth[3]=2`?

**Bài 4 — Cây DFS.** Với cùng đồ thị nhưng danh sách kề tăng dần, viết thứ tự khám phá DFS đệ quy từ 0. Vì sao `depth_DFS[2]=3` vẫn là kết quả đúng của DFS, dù có cạnh trực tiếp `0–2`?

**Bài 5 — Visited at enqueue.** Tạo đồ thị tam giác, mô phỏng BFS đánh dấu chỉ khi dequeue. So sánh số lần đỉnh có thể xuất hiện trong queue với cách đánh dấu ngay lúc enqueue.

**Bài 6 — Cạnh song song.** Tạo `n=3`, cạnh `(0,1)` xuất hiện ba lần, đỉnh 2 cô lập. Hãy dự đoán danh sách kề và số thành phần; bổ sung kiểm tra visited để mỗi đỉnh chỉ được enqueue một lần.

**Bài 7 — Đồ thị có hướng.** Với cạnh `0→1,2→1`, chạy vòng ngoài BFS trên cạnh hướng. Sau đó bỏ hướng và chạy lại. Chỉ ra vì sao kết quả forest không phải phân hoạch SCC.

**Bài 8 — Kiểm tra bằng DSU.** Với 5 đỉnh và các cạnh `(0,1),(1,2),(3,4)`, union mọi cạnh rồi so kết quả với BFS/DFS. DSU có thể đưa ra khoảng cách ngắn nhất giữa 0 và 2 không?

**Bài 9 — Gốc của từng nhóm.** Khi root được xét tăng dần và mỗi thành phần được duyệt hoàn toàn, chứng minh gốc của mỗi thành phần là **đỉnh có ID nhỏ nhất trong thành phần đó**.

**Bài 10 — Đồ thị lớn dạng đường.** Tạo `n=100000`, cạnh `(i,i+1)` cho mọi `i=0..n−2`. So sánh giới hạn call stack của DFS đệ quy và stack frame lặp trong Java.

**Bài 11 — Truy vấn nhiều cặp.** Sau một lần phân nhóm, muốn trả lời 100000 câu hỏi “u và v có liên thông không?”, nên dùng lại `componentId[]` thế nào? Nếu có thao tác thêm cạnh xen giữa các câu hỏi, khi nào DSU thích hợp hơn?

**Bài 12 — Kiểm thử exhaustive.** Liệt kê tất cả đồ thị vô hướng đơn với `n≤4`; đối chiếu BFS, DFS, DSU. Vì sao số đồ thị n=4 là `2^6=64`? Mở rộng kiểm thử tới n=5.

## 15. Checklist trước khi nộp

1. **Biết rõ loại đồ thị:** Vô hướng hay có hướng? Nếu có hướng, mục tiêu là forest duyệt, weak components hay SCC?
2. **Có đủ n đỉnh:** Kể cả đỉnh cô lập không xuất hiện trong cạnh?
3. **Đã khởi tạo đúng:** `visited=false` hoặc `componentId=-1` một lần trước toàn bộ vòng root?
4. **Vòng ngoài đầy đủ:** Đã xét root từ 0 đến n−1 và chỉ bắt đầu duyệt khi chưa thăm?
5. **Phát hiện ngay:** BFS đánh dấu visited lúc enqueue, DFS đánh dấu lúc push/đi sâu?
6. **State nhất quán:** Parent, depth, componentId của mọi đỉnh được gán đúng khi lần đầu phát hiện?
7. **Cạnh xây đúng:** Đồ thị vô hướng có đủ hai chiều, self-loop và cạnh song song không làm lặp đỉnh?
8. **Kết quả nhóm đúng:** Các nhóm không giao nhau, hợp mọi nhóm bằng toàn bộ tập đỉnh, tổng size bằng n?
9. **Đúng nghĩa khoảng cách:** BFS depth là số cạnh ngắn nhất từ root của **chính thành phần**; DFS depth không nhất thiết ngắn nhất?
10. **Tài nguyên hợp lý:** `O(n+m)` thời gian duyệt với danh sách kề, `O(n+m)` tổng bộ nhớ; tránh recursive DFS quá sâu?
11. **Thứ tự in có quy định không:** Nếu cần tăng dần, đã sắp danh sách kề và quét root tăng chưa?
12. **Đã test:** `n=0`, không cạnh, một thành phần, nhiều thành phần, self-loop, cạnh trùng, đỉnh cô lập và ví dụ có hướng?
13. **Đã kiểm chứng độc lập:** Khi cần, so phân hoạch với DSU và kiểm tra khoảng cách BFS với một oracle khác?

**Tiêu chí hoàn thành:** Bạn có thể khởi tạo đúng trạng thái duyệt, viết **vòng ngoài qua mọi đỉnh**, triển khai BFS/DFS để nhận đủ các thành phần của **đồ thị vô hướng** mà không bỏ đỉnh cô lập hoặc đếm trùng, phân biệt parent/depth của BFS và DFS, hiểu ranh giới của đồ thị có hướng, và kiểm chứng chương trình Java 17+ bằng một phương pháp độc lập.

# DFS đệ quy và DFS dùng ngăn xếp

## Mục tiêu học tập

**Duyệt theo chiều sâu (Depth-First Search, DFS)** là thuật toán duyệt đồ thị bằng cách khám phá sâu một nhánh trước rồi **quay lui** khi nhánh ấy không còn đỉnh mới. Có hai cách triển khai thông dụng: dùng **ngăn xếp lời gọi của đệ quy** và dùng **ngăn xếp tường minh (explicit stack)**. Cả hai đều có thể duyệt đúng tập đỉnh có thể tới; tuy nhiên không phải mọi cách viết DFS dùng stack đều cho **cùng thứ tự vào/ra, cùng cây cha hoặc cùng thời điểm hoàn tất** với DFS đệ quy.

Sau bài học, bạn có thể:

1. Viết DFS đệ quy trên danh sách kề và xác định `visited`, `parent`, `preorder`, `postorder`.
2. Duyệt một nguồn hoặc tạo **rừng DFS** cho cả đồ thị, kể cả đỉnh cô lập và đồ thị có hướng.
3. Viết DFS dùng **stack chỉ chứa đỉnh**, hiểu đánh dấu **khi push** so với **khi pop**.
4. Nhận ra vì sao đảo thứ tự push hàng xóm chưa bảo đảm giống DFS đệ quy.
5. Dùng **stack chứa frame (đỉnh, hàng xóm kế tiếp)** để mô phỏng chính xác trình tự đệ quy.
6. Chứng minh tính đúng, tính dừng và giới hạn `O(V+E)` thời gian khi dùng danh sách kề.
7. Ứng dụng DFS vào truy vết đường đi, phát hiện chu trình có hướng bằng ba màu, thứ tự topo của DAG và các thành phần.
8. Chạy chương trình **Java 17+** hoàn chỉnh với kết quả kiểm chứng được.

---

## 1. Bài toán duyệt đồ thị

Cho đồ thị `G=(V,E)`, với V là tập các đỉnh và E là tập các cạnh. Trong ví dụ, đánh số các đỉnh từ `0` đến `n−1` và biểu diễn đồ thị có hướng bằng **danh sách kề**:

```text
graph[v] = danh sách các đỉnh u có cạnh v -> u.
```

Nếu là đồ thị vô hướng, mỗi cạnh `{u,v}` cần được thêm vào **cả hai danh sách kề**, trừ khi cấu trúc nhập dữ liệu đã thực hiện việc đó.

Hãy xét đồ thị:

```text
0: [1, 2]
1: [2, 3]
2: [4]
3: [4]
4: [1]
5: [6]
6: []
```

Có bảy đỉnh. Từ 0 có thể tới `0,1,2,3,4` nhưng không tới 5 hoặc 6. Cạnh `4→1` tạo chu trình `1→2→4→1`. Phần `5→6` tạo một cây khám phá khác nếu muốn duyệt toàn bộ đồ thị.

### 1.1. Mục tiêu của DFS là gì?

DFS có thể được dùng cho nhiều yêu cầu khác nhau:

- **Reachability:** từ đỉnh s đi tới những đỉnh nào?
- **Duyệt toàn đồ thị:** liệt kê mọi đỉnh, không bỏ các phần không tới được từ s.
- **Cây DFS:** ghi cạnh dùng để khám phá một đỉnh lần đầu.
- **Preorder:** ghi đỉnh ngay lúc được bước vào/khám phá.
- **Postorder:** ghi đỉnh khi đã xét hết các hàng xóm cần thiết và quay về cha.
- **Chu trình:** phát hiện cạnh quay lại tổ tiên **đang hoạt động** trong DFS có hướng.
- **Thuật toán đồ thị khác:** thứ tự topo, Tarjan/Kosaraju, cầu và đỉnh khớp trên mô hình phù hợp.

Không phải mọi ứng dụng chỉ cần “đi qua mọi đỉnh”. Nếu cần chính xác **thời điểm hoàn tất**, cách cài DFS phải giữ đúng ngữ nghĩa **đi sâu, quay lui, tiếp tục duyệt hàng xóm còn lại**.

### 1.2. DFS và BFS

| Khía cạnh | DFS | BFS |
| --- | --- | --- |
| Chiến lược | Đi sâu một nhánh, quay lui | Duyệt theo các lớp khoảng cách |
| Cấu trúc | Call stack hoặc explicit stack | Queue |
| Đường đi tìm được | Một đường đi có thật, không nhất thiết ngắn nhất | Ít cạnh nhất trên đồ thị không trọng số |
| Độ phức tạp với danh sách kề | `O(V+E)` | `O(V+E)` |
| Ứng dụng tiêu biểu | Chu trình, topo, SCC, cây DFS | Độ dài đường ít cạnh nhất, lớp khoảng cách |

Ví dụ cạnh `0→1`, `1→2`, `2→3`, `0→3`: DFS xét 1 trước có thể tới 3 theo **ba cạnh**, trong khi BFS tìm được đường `0→3` chỉ **một cạnh**. Đừng dùng parent của DFS như chứng chỉ đường đi ngắn nhất.

---

## 2. visited, parent và thứ tự vào/ra

### 2.1. visited[]

`visited[v]` cho biết v đã được đánh dấu theo chính sách duyệt đã chọn. Với **đệ quy**, ta đánh dấu ngay khi **bước vào lời gọi DFS(v)**. Điều đó chặn việc gọi lại một đỉnh trên chu trình:

```text
DFS(v):
    visited[v] = true
    for u trong graph[v]:
        if !visited[u]:
            DFS(u)
```

Nếu đợi duyệt xong hàng xóm mới đánh dấu, chu trình `1→2→4→1` có thể gây đệ quy vô hạn.

### 2.2. parent[]

`parent[u]=v` nghĩa là lần đầu u được khám phá qua cạnh `v→u`. Với gốc của một cây DFS, đặt `parent[root]=-1`.

Parent không nhất thiết là **một đỉnh duy nhất có cạnh đi vào u**: đồ thị có thể có nhiều cạnh đi vào. Nó chỉ là một cạnh cây được chọn theo **thứ tự và thời điểm khám phá** của thuật toán. Đổi thứ tự hàng xóm hoặc thời điểm đánh dấu có thể đổi parent.

### 2.3. Preorder và postorder

Trong DFS đệ quy chuẩn:

```text
DFS(v):
    visited[v] = true
    preorder.add(v)               // enter

    for u trong graph[v]:
        if !visited[u]:
            parent[u] = v
            DFS(u)

    postorder.add(v)              // exit
```

- `preorder` ghi **lần đầu bước vào** một đỉnh.
- `postorder` ghi khi **hoàn tất toàn bộ hàng xóm** của đỉnh.

Với đồ thị ở mục 1 và vòng duyệt tất cả gốc theo thứ tự tăng:

```text
Roots:      [0, 5]
Preorder:   [0, 1, 2, 4, 3, 5, 6]
Postorder:  [4, 2, 3, 1, 0, 6, 5]
Parent:     [-1, 0, 1, 1, 2, -1, 5]
```

Chú ý chu trình ở 1–2–4 **không gây lặp vô hạn**, vì khi xét cạnh `4→1`, 1 đã được đánh dấu.

### 2.4. Thứ tự không duy nhất nếu không cố định danh sách kề

Hai danh sách `graph[0]=[1,2]` và `graph[0]=[2,1]` chứa cùng tập hàng xóm nhưng tạo **thứ tự vào đỉnh khác**. Do đó nếu yêu cầu đúng một chuỗi đầu ra, đề hoặc chương trình phải quy định rõ thứ tự xét các hàng xóm, chẳng hạn tăng dần theo id.

Thứ tự phụ thuộc cả vào:
- Danh sách kề được sắp hay giữ nguyên thứ tự nhập.
- Dùng DFS đệ quy hay stack đỉnh.
- Đánh dấu khi push hay khi pop.
- Cách xử lý các đỉnh đã được xếp chờ nhưng chưa thực sự xử lý.

---

## 3. DFS đệ quy

DFS đệ quy là cách viết sát định nghĩa nhất: khi gặp đỉnh u chưa được duyệt trong danh sách kề của v, ta **gọi DFS(u) ngay** và chỉ quay về xét hàng xóm kế tiếp của v sau khi nhánh u hoàn tất.

### 3.1. Giả mã một nguồn

```text
recursiveDFS(v):
    visited[v] = true
    preorder.append(v)

    for u theo thứ tự trong graph[v]:
        if !visited[u]:
            parent[u] = v
            recursiveDFS(u)

    postorder.append(v)
```

Muốn chỉ xét những đỉnh đi tới được từ s:

```text
visited = all false
parent = all -1
recursiveDFS(s)
```

Với đồ thị có V đỉnh, s phải nằm trong `[0,V)`.

### 3.2. Rừng DFS cho toàn đồ thị

Muốn không bỏ đỉnh chưa tới được từ s:

```text
for v = 0..V-1:
    if !visited[v]:
        roots.add(v)
        recursiveDFS(v)
```

Mỗi lời gọi từ một gốc mới tạo một **cây** trong **rừng DFS (DFS forest)**.

**Đồ thị vô hướng:** số gốc/cây của một rừng DFS toàn đồ thị bằng số **thành phần liên thông**.

**Đồ thị có hướng:** số cây theo vòng ngoài **không mặc định** bằng số SCC hay số thành phần liên thông yếu; có thể đổi khi thay thứ tự gốc. Muốn SCC, dùng thuật toán như Tarjan/Kosaraju; muốn liên thông yếu, xét đồ thị sau khi bỏ hướng cạnh.

### 3.3. Cây DFS của ví dụ

Từ thứ tự ở mục 2, các cạnh cây là:

```text
0
└── 1
    ├── 2
    │   └── 4
    └── 3

5
└── 6
```

Các cạnh `0→2`, `3→4` và `4→1` có thật trong đồ thị nhưng không phải cạnh cây theo lần duyệt này.

### 3.4. Bất biến đệ quy

Trong khi `recursiveDFS(v)` đang chạy:

1. v được đánh dấu đúng một lần khi bước vào.
2. Các lời gọi đang hoạt động tạo một đường cây từ gốc đến v.
3. Mọi hàng xóm trước vị trí đang xét đã được kiểm tra; nếu cần đi sâu vào một hàng xóm chưa visited thì **nhánh ấy đã hoàn tất** trước khi duyệt hàng xóm kế tiếp.
4. Sau khi kết thúc vòng lặp, mọi cạnh đi ra từ v đã được kiểm tra; mới lúc đó ghi postorder.
5. Khi quay về lời gọi cha, chương trình tiếp tục ở **đúng vị trí sau hàng xóm vừa xử lý**.

Chính điểm thứ năm quyết định cách mô phỏng bằng stack tường minh.

---

## 4. Tại sao cần DFS dùng ngăn xếp tường minh?

Trong Java, mỗi lời gọi đệ quy chiếm một **khung trên call stack**. Với đường một chiều rất sâu:

```text
0 -> 1 -> 2 -> ... -> 200000
```

số khung lời gọi có thể tăng theo V. Kích thước stack mỗi thread hữu hạn; chương trình có thể gặp `StackOverflowError` dù thuật toán logic đúng và đồ thị không có chu trình.

Dùng `ArrayDeque` trên heap để tự quản lý công việc có thể tránh **giới hạn call stack của DFS đệ quy**, nhưng không loại bỏ nhu cầu bộ nhớ. Một stack tường minh cũng có thể cần `O(V)` phần tử và vẫn có thể làm heap cạn.

### 4.1. Hai lựa chọn stack khác nhau

**Stack chỉ chứa đỉnh:**

```text
stack: [vertex, vertex, ...]
```

Thuận tiện nếu chỉ cần thăm các đỉnh reachable, lưu cây theo chính sách push, hoặc làm một công việc tại mỗi đỉnh.

**Stack chứa frame:**

```text
stack: [Frame(vertex, nextNeighbor), ...]
```

Cần khi muốn mô phỏng **trạng thái lời gọi đang tạm dừng**, giữ chính xác preorder, postorder, parent theo cùng thứ tự kề như đệ quy.

Việc đánh đồng hai cấu trúc này là một trong những nguyên nhân phổ biến khiến kết quả duyệt khác mong đợi.

---

## 5. DFS dùng stack chỉ chứa đỉnh, đánh dấu khi push

### 5.1. Giả mã

```text
vertexStackDFS(s):
    stack.push(s)
    visited[s] = true

    while !stack.empty():
        v = stack.pop()
        popOrder.append(v)

        for u theo thứ tự ngược của graph[v]:
            if !visited[u]:
                visited[u] = true
                parent[u] = v
                stack.push(u)
```

Ta duyệt hàng xóm **ngược** để phần tử hàng xóm đầu trong `graph[v]` nằm **trên cùng stack**, được pop trước những hàng xóm khác của v:

```text
graph[v] = [a, b, c]
push(c), push(b), push(a)
=> pop(a) trước b và c
```

Tuy nhiên đây chỉ là **đảo thứ tự cho các hàng xóm cùng một lượt**, chưa tái hiện chính xác cách đệ quy đi sâu rồi quay lại.

### 5.2. Bất biến của mark-on-push

- Một đỉnh được đánh dấu **lúc đưa vào stack**, không phải lúc lấy ra.
- Nếu `visited[u]` đã true, u đã được lên lịch hoặc đã xử lý, nên không push lần thứ hai.
- Một đỉnh được pop đúng một lần, một danh sách kề được quét tối đa một lần.
- Parent của u được xác định khi push u lần đầu.

**Nên gọi danh sách in tại pop là `popOrder` hoặc `processingOrder`.** Trong biến thể này, một đỉnh có thể đã được đánh dấu rất lâu trước khi được pop, nên `popOrder` không phải chính xác “thứ tự đánh dấu visited”.

### 5.3. Phản ví dụ quyết định

Dùng lại đồ thị:

```text
0: [1,2]
1: [2,3]
2: [4]
3: [4]
4: [1]
5: [6]
6: []
```

**Đệ quy** từ 0 xử lý:

```text
0 -> 1 -> 2 -> 4 -> quay lui -> 3
preorder từ 0: [0,1,2,4,3]
```

**Stack đỉnh mark-on-push, đảo thứ tự đẩy**:

```text
Pop 0, push 2 rồi 1.
Visited đã gồm 0,1,2; stack top trước = [1,2].

Pop 1: 2 đã visited nên bỏ qua 2;
       push 3; stack = [3,2].
Pop 3: push 4; stack = [4,2].
Pop 4: cạnh tới 1 đã visited.
Pop 2: cạnh tới 4 đã visited.
```

Thứ tự pop từ 0:

```text
[0,1,3,4,2]
```

Khác preorder đệ quy:

```text
[0,1,2,4,3]
```

Kết quả parent khác nhau:

```text
Đệ quy:      parent[2] = 1, parent[4] = 2.
Stack đỉnh:  parent[2] = 0, parent[4] = 3.
```

**Cả hai vẫn đến được đúng tập đỉnh** từ 0, nhưng lịch khám phá và cây được sinh khác nhau. Nếu bài chỉ kiểm tra reachability, điều đó thường không ảnh hưởng. Nếu bài cần **đúng cây DFS, thời điểm vào/ra hoặc phân loại cạnh** theo đệ quy, phải dùng phiên bản frame.

### 5.4. Đánh dấu khi pop là gì?

Một cách viết khác đẩy nguồn vào stack nhưng **chưa đánh dấu ngay**:

```text
stack.push(s)

while !stack.empty():
    v = stack.pop()
    if visited[v]:
        continue

    visited[v] = true
    process(v)

    for u theo thứ tự ngược trong graph[v]:
        if !visited[u]:
            stack.push(u)
```

Ở đây một đỉnh **có thể bị push nhiều lần** trước khi được pop lần đầu (vì các nguồn khác nhau chưa thấy nó visited). Phải có `if visited[v] continue` sau pop để không mở rộng lại.

Nếu có nhiều cạnh tới cùng u, số mục stack đang chờ có thể lớn hơn V. Tuy nhiên, nếu mỗi đỉnh chỉ được **mở rộng một lần** và mỗi cạnh của đỉnh mở rộng chỉ được xét một lần, tổng số push được chặn bởi `O(V+E)`. Thời gian vẫn `O(V+E)` nhưng **bộ nhớ stack có thể đạt `O(V+E)`**, không còn chặn `O(V)` như mark-on-push.

**Lưu ý parent:** nếu muốn parent tương ứng với lần khám phá thực sự trong phiên bản mark-on-pop, không nên gán cha tùy tiện ngay khi một bản sao được push: u có thể đã được đưa vào stack từ nhiều cạnh trước khi lần đầu được xử lý. Cần lưu cha cùng mục stack hoặc gán parent theo chính sách được chứng minh nhất quán.

---

## 6. Mô phỏng chính xác đệ quy: stack chứa frame

Trong lời gọi `DFS(v)`, khi đi sâu sang hàng xóm u, runtime giữ lại v cùng thông tin “đã duyệt tới hàng xóm nào”. Khi `DFS(u)` trả về, nó tiếp tục từ vị trí tiếp theo trong `graph[v]`.

Một phần tử stack chỉ chứa v không đủ lưu **vị trí tiếp tục** ấy. Ta dùng:

```text
Frame {
    vertex        // Đỉnh có lời gọi đang hoạt động
    nextNeighbor  // Chỉ số hàng xóm sẽ xét tiếp
}
```

### 6.1. Giả mã dùng frame

```text
frameDFS(s):
    visited[s] = true
    preorder.append(s)
    stack.push(Frame(s, nextNeighbor=0))

    while !stack.empty():
        f = stack.peek()

        if f.nextNeighbor == graph[f.vertex].length:
            postorder.append(f.vertex)
            stack.pop()
            continue

        u = graph[f.vertex][f.nextNeighbor]
        f.nextNeighbor++

        if !visited[u]:
            visited[u] = true
            parent[u] = f.vertex
            preorder.append(u)
            stack.push(Frame(u, nextNeighbor=0))
```

Trong mô phỏng này:

- `peek()` lấy frame trên đỉnh **mà chưa xóa**.
- Nếu còn hàng xóm, ta xét đúng **một** hàng xóm mỗi bước.
- Nếu hàng xóm chưa thăm, push frame con ngay; frame cha vẫn nằm dưới, **chờ**.
- Nếu hết hàng xóm, ghi `postorder` rồi pop frame — tương đương câu lệnh `return` của DFS đệ quy.

### 6.2. Bất biến của stack frame

Ở mỗi thời điểm:

1. Các frame từ đáy lên trên cùng tương ứng với **các lời gọi đệ quy đang hoạt động** theo thứ tự cha–con.
2. Mỗi frame đã ghi preorder và đánh dấu vertex **ngay khi được push**.
3. `nextNeighbor` chính là hàng xóm kế tiếp mà lời gọi tương ứng phải xét.
4. Frame cha **không** được duyệt tiếp khi frame con còn tồn tại ở trên.
5. Khi frame bị pop, toàn bộ danh sách kề của nó đã xét xong và postorder được ghi.

Do đó với **cùng thứ tự kề**, frame DFS cho đúng cùng **preorder, postorder và parent** như đệ quy.

### 6.3. Vết hoạt động ngắn

Với `graph[0]=[1,2]`:

```text
push Frame(0,0) -> preorder 0
Frame 0 xét 1, nextNeighbor trở thành 1
push Frame(1,0) -> preorder 1

Trong lúc Frame 1 còn hoạt động,
Frame 0 KHÔNG xét 2.

Chỉ khi nhánh của Frame 1 hoàn tất,
Frame 0 mới xét tiếp hàng xóm số 2.
```

Điểm này là khác biệt cốt lõi với việc pop 0 và **push tất cả hàng xóm ngay lập tức**.

### 6.4. Cần frame khi nào?

Nếu bạn cần:

- Thứ tự hoàn tất chính xác.
- Mảng `tin/tout` của DFS.
- Cấu trúc cây DFS tương đương đệ quy.
- Phát hiện cạnh tới một tổ tiên **đang hoạt động**.
- Sắp xếp topo dựa trên postorder.
- Chuyển thuật toán dùng recursion sâu sang vòng lặp mà không thay ngữ nghĩa.

thì stack frame là lựa chọn rõ ràng. Nếu chỉ cần thăm mọi đỉnh một lần và phát một giá trị ở mỗi đỉnh, stack đỉnh mark-on-push có thể đơn giản hơn.

---

## 7. Java 17+: ba cách triển khai chạy được

Lưu chương trình dưới tên **`DfsRecursiveAndStackDemo.java`**. Chương trình thực hiện:

- DFS **đệ quy** trên toàn đồ thị.
- DFS dùng **stack đỉnh mark-on-push**; in thứ tự pop.
- DFS dùng **stack frame**, mô phỏng chính xác đệ quy.
- Phát hiện chu trình có hướng bằng **ba màu WHITE/GRAY/BLACK**.
- Kiểm tra đồ thị có hướng, đồ thị DAG và đồ thị rỗng.
- Giữ nguyên dữ liệu danh sách kề.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.List;
import java.util.Objects;

public class DfsRecursiveAndStackDemo {

    public record DfsResult(
            List<Integer> roots,
            List<Integer> preorder,
            List<Integer> postorder,
            int[] parent) {
    }

    public record StackResult(
            List<Integer> roots,
            List<Integer> popOrder,
            int[] parent) {
    }

    private static final class Frame {
        final int vertex;
        int nextNeighbor;

        Frame(int vertex) {
            this.vertex = vertex;
            this.nextNeighbor = 0;
        }
    }

    private static void validate(int[][] graph) {
        Objects.requireNonNull(graph, "graph");

        int n = graph.length;
        for (int v = 0; v < n; v++) {
            if (graph[v] == null) {
                throw new IllegalArgumentException(
                        "null adjacency list at " + v);
            }

            for (int u : graph[v]) {
                if (u < 0 || u >= n) {
                    throw new IllegalArgumentException(
                            "invalid neighbor " + u + " of " + v);
                }
            }
        }
    }

    private static void recursiveVisit(
            int[][] graph,
            int v,
            boolean[] visited,
            int[] parent,
            List<Integer> preorder,
            List<Integer> postorder) {

        visited[v] = true;
        preorder.add(v);

        for (int u : graph[v]) {
            if (!visited[u]) {
                parent[u] = v;
                recursiveVisit(graph, u, visited, parent,
                        preorder, postorder);
            }
        }

        postorder.add(v);
    }

    public static DfsResult recursiveForest(int[][] graph) {
        validate(graph);
        int n = graph.length;

        boolean[] visited = new boolean[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        List<Integer> roots = new ArrayList<>();
        List<Integer> preorder = new ArrayList<>();
        List<Integer> postorder = new ArrayList<>();

        for (int root = 0; root < n; root++) {
            if (!visited[root]) {
                roots.add(root);
                recursiveVisit(graph, root, visited, parent,
                        preorder, postorder);
            }
        }

        return new DfsResult(roots, preorder, postorder, parent);
    }

    // Vertex-only stack, mark when pushing, print when popping.
    public static StackResult vertexStackForest(int[][] graph) {
        validate(graph);
        int n = graph.length;

        boolean[] visited = new boolean[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        List<Integer> roots = new ArrayList<>();
        List<Integer> popOrder = new ArrayList<>();
        Deque<Integer> stack = new ArrayDeque<>();

        for (int root = 0; root < n; root++) {
            if (visited[root]) {
                continue;
            }

            roots.add(root);
            visited[root] = true;
            stack.push(root);

            while (!stack.isEmpty()) {
                int v = stack.pop();
                popOrder.add(v);

                // Reverse the push order, not necessarily
                // the same traversal as recursive DFS.
                for (int i = graph[v].length - 1; i >= 0; i--) {
                    int u = graph[v][i];

                    if (!visited[u]) {
                        visited[u] = true;
                        parent[u] = v;
                        stack.push(u);
                    }
                }
            }
        }

        return new StackResult(roots, popOrder, parent);
    }

    // Exact simulation of recursive enter/exit events.
    public static DfsResult frameStackForest(int[][] graph) {
        validate(graph);
        int n = graph.length;

        boolean[] visited = new boolean[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        List<Integer> roots = new ArrayList<>();
        List<Integer> preorder = new ArrayList<>();
        List<Integer> postorder = new ArrayList<>();
        Deque<Frame> stack = new ArrayDeque<>();

        for (int root = 0; root < n; root++) {
            if (visited[root]) {
                continue;
            }

            roots.add(root);
            visited[root] = true;
            preorder.add(root);
            stack.push(new Frame(root));

            while (!stack.isEmpty()) {
                Frame top = stack.peek();
                int v = top.vertex;

                if (top.nextNeighbor == graph[v].length) {
                    postorder.add(v);
                    stack.pop();
                    continue;
                }

                int u = graph[v][top.nextNeighbor];
                top.nextNeighbor++;

                if (!visited[u]) {
                    visited[u] = true;
                    parent[u] = v;
                    preorder.add(u);
                    stack.push(new Frame(u));
                }
            }
        }

        return new DfsResult(roots, preorder, postorder, parent);
    }

    // 0=WHITE, 1=GRAY (active), 2=BLACK (finished).
    private static boolean cycleVisit(
            int[][] graph, int v, int[] color) {

        color[v] = 1;

        for (int u : graph[v]) {
            if (color[u] == 1) {
                return true;
            }

            if (color[u] == 0 && cycleVisit(graph, u, color)) {
                return true;
            }
        }

        color[v] = 2;
        return false;
    }

    public static boolean hasDirectedCycle(int[][] graph) {
        validate(graph);

        int[] color = new int[graph.length];

        for (int v = 0; v < graph.length; v++) {
            if (color[v] == 0 && cycleVisit(graph, v, color)) {
                return true;
            }
        }

        return false;
    }

    public static void main(String[] args) {
        int[][] graph = {
                {1, 2},
                {2, 3},
                {4},
                {4},
                {1},
                {6},
                {}
        };

        DfsResult recursive = recursiveForest(graph);
        StackResult vertices = vertexStackForest(graph);
        DfsResult frames = frameStackForest(graph);

        System.out.println(
                "Recursive roots: " + recursive.roots());
        System.out.println(
                "Recursive preorder: " + recursive.preorder());
        System.out.println(
                "Recursive postorder: " + recursive.postorder());
        System.out.println(
                "Recursive parents: "
                        + Arrays.toString(recursive.parent()));

        System.out.println(
                "Vertex stack roots: " + vertices.roots());
        System.out.println(
                "Vertex stack pop order: " + vertices.popOrder());
        System.out.println(
                "Vertex stack parents: "
                        + Arrays.toString(vertices.parent()));

        System.out.println(
                "Frame stack preorder: " + frames.preorder());
        System.out.println(
                "Frame stack postorder: " + frames.postorder());
        System.out.println(
                "Frame stack parents: "
                        + Arrays.toString(frames.parent()));

        boolean matches =
                recursive.preorder().equals(frames.preorder())
                && recursive.postorder().equals(frames.postorder())
                && Arrays.equals(
                        recursive.parent(), frames.parent());

        System.out.println(
                "Frame matches recursive: " + matches);
        System.out.println(
                "Directed cycle exists: "
                        + hasDirectedCycle(graph));

        int[][] dag = {
                {1, 2},
                {3},
                {3},
                {}
        };

        System.out.println(
                "DAG cycle exists: " + hasDirectedCycle(dag));
        System.out.println(
                "Empty graph roots: "
                        + recursiveForest(new int[0][]).roots());
    }
}
```

Biên dịch/chạy trên **JDK 17 trở lên**:

```bash
javac DfsRecursiveAndStackDemo.java
java DfsRecursiveAndStackDemo
```

**Kết quả stdout chính xác** với các danh sách kề trong chương trình:

```text
Recursive roots: [0, 5]
Recursive preorder: [0, 1, 2, 4, 3, 5, 6]
Recursive postorder: [4, 2, 3, 1, 0, 6, 5]
Recursive parents: [-1, 0, 1, 1, 2, -1, 5]
Vertex stack roots: [0, 5]
Vertex stack pop order: [0, 1, 3, 4, 2, 5, 6]
Vertex stack parents: [-1, 0, 0, 1, 3, -1, 5]
Frame stack preorder: [0, 1, 2, 4, 3, 5, 6]
Frame stack postorder: [4, 2, 3, 1, 0, 6, 5]
Frame stack parents: [-1, 0, 1, 1, 2, -1, 5]
Frame matches recursive: true
Directed cycle exists: true
DAG cycle exists: false
Empty graph roots: []
```

### 7.1. Giải thích chi tiết kết quả

**Đệ quy:** 0→1→2→4, kiểm tra `4→1` đã visited rồi quay về 2 và 1, tiếp tục hàng xóm 3; cuối cùng xét 2 của 0 (đã visited). Sau cây gốc 0, vòng ngoài bắt đầu 5 và khám phá 6. Vì vậy `roots=[0,5]`.

**Stack đỉnh:** pop 0, đưa 2 và 1 vào stack và đánh dấu cả hai. Khi pop 1, 2 đã visited, nên nhánh tiếp theo đi qua 3 rồi 4; 2 chỉ được pop về sau. Parent cũng khác vì 2 được khám phá từ 0 thay vì từ 1.

**Stack frame:** sau khi đẩy Frame(1), Frame(0) chưa xử lý hàng xóm 2. Frame(1) đi sâu vào 2 và 4 trước khi quay lại 1 để xét 3. Vì vậy preorder, postorder và parent khớp hoàn toàn phiên bản đệ quy.

**Chu trình:** tại đường `1→2→4`, cạnh `4→1` trỏ tới đỉnh GRAY nên hàm phát hiện chu trình trả true. Trong DAG đối chiếu không có cạnh đến đỉnh đang GRAY, nên trả false.

### 7.2. Vì sao code cần validate?

Với `int[][]`, một danh sách kề có thể là null hoặc chứa chỉ số u ngoài `[0,n)`. Khi ấy `visited[u]` sẽ đọc sai hoặc ném lỗi. `validate` chặn từ đầu; self-loop và cạnh lặp vẫn được phép và không phá các thuật toán duyệt.

Với đồ thị vô hướng, phải tự thêm cả `u→v` và `v→u` vào ma trận danh sách kề; chương trình không tự suy diễn rằng input đối xứng.

### 7.3. Lưu ý về record và tính bất biến

`DfsResult`, `StackResult` là `record` Java 17. Chúng đóng gói kết quả nhưng **không tự tạo bản sao sâu** của `List` hay `int[]`. Trong ví dụ, mỗi lần gọi sinh mảng/danh sách riêng và không sửa sau đó, nên kết quả chính xác. Nếu xây thư viện công cộng cần trả dữ liệu bất biến, có thể dùng `List.copyOf` và sao chép mảng ở ranh giới API.

### 7.4. Giới hạn thực tế của ví dụ

Cả ba phương thức duyệt và hàm phát hiện chu trình ở ví dụ đều dùng danh sách kề trong RAM. Bản `recursiveForest` và `hasDirectedCycle` dùng recursion nên vẫn có nguy cơ `StackOverflowError` trên đồ thị rất sâu. `frameStackForest` không dùng đệ quy cho phần duyệt, nhưng vẫn dùng heap để chứa các frame.

Không có giới hạn n cố định về mặt lý thuyết trong thuật toán `O(V+E)`; thực tế còn phụ thuộc bộ nhớ cho danh sách kề, visited, parent, output và stack.

---

## 8. Chứng minh tính đúng

### 8.1. Mọi đỉnh được khám phá từ một nguồn đều tới được

Dùng quy nạp theo lần đánh dấu:

- Nguồn s tự tới được từ s qua đường độ dài 0.
- Mỗi đỉnh u khác s chỉ được khám phá từ một đỉnh v đã khám phá qua **cạnh có thật `v→u`**. Nếu s tới được v thì nối cạnh `v→u` tạo đường từ s tới u.

Vì vậy mọi đỉnh được khám phá trong một lượt từ s thật sự **có đường đi từ s**.

### 8.2. Mọi đỉnh tới được đều được khám phá

Giả sử có đỉnh t tới được từ s nhưng chưa visited sau khi thuật toán kết thúc. Trên một đường đi từ s tới t, xét cạnh đầu tiên `v→u` có v đã thăm còn u chưa thăm.

Khi xử lý v, thuật toán phải xét mọi cạnh trong `graph[v]`. Khi gặp u chưa visited, nó sẽ push/call DFS(u). Mâu thuẫn.

Do đó mọi đỉnh tới được từ s đều được khám phá. Nếu lặp thêm các gốc chưa visited theo vòng ngoài, **mọi đỉnh toàn đồ thị** được đánh dấu.

### 8.3. Vì sao không đi vô hạn trên chu trình?

- Đệ quy: đánh dấu ngay trước khi duyệt hàng xóm, không gọi lại đỉnh đã visited.
- Stack đỉnh mark-on-push: mỗi đỉnh push tối đa một lần.
- Stack frame: mỗi đỉnh được tạo frame tối đa một lần; con trỏ hàng xóm của frame tăng từng bước và cuối cùng frame bị pop.

Vì có hữu hạn đỉnh/cạnh, các thuật toán đều dừng.

### 8.4. Tính đúng của cây parent

Mỗi đỉnh không phải gốc nhận parent lúc **được đánh dấu lần đầu** từ một cạnh thật. Cha đã được khám phá trước con, nên chuỗi cha không thể tạo vòng và cuối cùng dẫn về một gốc. Vì mỗi đỉnh chỉ đánh dấu lần đầu một lần, nó có một cha duy nhất.

Các phương pháp DFS khác nhau có thể chọn các cạnh cây khác nhau. **Tính đúng của rừng khám phá** không có nghĩa mọi phiên bản phải có cùng mảng parent.

### 8.5. Bằng nhau giữa đệ quy và stack frame

Xét mỗi lời gọi đệ quy như một frame `(v,nextNeighbor)`:

- Bước gọi DFS(v) ↔ push Frame(v,0), đánh dấu và ghi preorder.
- Bước xét cạnh kế tiếp ↔ đọc `graph[v][nextNeighbor]` rồi tăng `nextNeighbor`.
- Bước gọi DFS(u) ↔ push frame u trong khi frame v vẫn chờ dưới.
- Lệnh return ↔ ghi postorder rồi pop frame v.

Vì từng thao tác có một sự kiện tương ứng và cùng cập nhật `visited/parent`, phiên bản frame **mô phỏng chính xác** thứ tự vào/ra của recursion.

---

## 9. Thời gian O(V+E) và bộ nhớ

Giả sử dùng danh sách kề, các thao tác truy cập `visited`, `push/pop` và thêm vào danh sách kết quả có chi phí `O(1)` khấu hao.

- Mỗi đỉnh được **khám phá/mở rộng** tối đa một lần: tổng `O(V)`.
- Khi mở rộng đỉnh v, ta duyệt hết `graph[v]` đúng một lần.
- Tổng số mục kề trong đồ thị có hướng là E; trong vô hướng nếu lưu hai chiều là `2E`.

Vậy:

\[
\boxed{T(V,E)=O(V+E)}.
\]

| Cài đặt | Stack tối đa | visited và parent | Bộ nhớ phụ tổng quát |
| --- | --- | --- | --- |
| DFS đệ quy | `O(V)` call frames | `O(V)` | `O(V)` |
| Stack đỉnh mark-on-push | `O(V)` phần tử | `O(V)` | `O(V)` |
| Stack đỉnh mark-on-pop | Có thể `O(V+E)` mục đang chờ | `O(V)` | `O(V+E)` |
| Stack frame | `O(V)` frame | `O(V)` | `O(V)` |

Các kết quả preorder/postorder/roots chứa tối đa V đỉnh, mỗi danh sách `O(V)`. Bộ nhớ biểu diễn đồ thị danh sách kề là `O(V+E)` và được tính **riêng** khi nói bộ nhớ phụ thuật toán.

### 9.1. Vì sao danh sách kề quan trọng?

Nếu dùng **ma trận kề `V×V`** và mỗi lần mở rộng v phải quét tất cả V cột để tìm hàng xóm, tổng thời gian duyệt thường là `O(V²)`, kể cả đồ thị thưa.

Khi học độ phức tạp DFS, không chỉ nhớ công thức `O(V+E)` mà phải nêu **giả thiết về biểu diễn đồ thị**.

### 9.2. Đệ quy và stack khác nhau ở giới hạn runtime

Hai cách đều có thể dùng `O(V)` bộ nhớ, nhưng bản đệ quy có thể đụng giới hạn **thread call stack** trước khi heap cạn. Stack tường minh giảm rủi ro `StackOverflowError` do DFS, nhưng không bảo đảm heap đủ cho đồ thị khổng lồ.

---

## 10. Phát hiện chu trình có hướng bằng ba màu

Duyệt đồ thị có hướng đôi khi cần biết một cạnh có quay về đỉnh **đang hoạt động** trong cùng nhánh DFS hay không. Boolean visited không phân biệt được “đã khám phá nhưng chưa xong” với “đã khám phá và hoàn tất”.

Dùng ba trạng thái:

| Màu | Ý nghĩa |
| --- | --- |
| WHITE (0) | Chưa khám phá |
| GRAY (1) | Đã khám phá, chưa hoàn tất, đang nằm trên đường DFS hoạt động |
| BLACK (2) | Đã hoàn tất mọi hàng xóm |

Giả mã:

```text
dfsCycle(v):
    color[v] = GRAY

    for u trong graph[v]:
        if color[u] == GRAY:
            return true
        if color[u] == WHITE and dfsCycle(u):
            return true

    color[v] = BLACK
    return false
```

Một cạnh `v→u` tới **GRAY** tạo chu trình: u đang là tổ tiên hoạt động của v, nên tồn tại đường cây `u⇢v`; thêm cạnh `v→u` tạo vòng.

### 10.1. Cạnh tới BLACK không nhất thiết tạo chu trình

Xét DAG:

```text
0: [1,2]
1: [3]
2: [3]
3: []
```

Sau khi hoàn tất `0→1→3`, đỉnh 3 đã BLACK. Khi duyệt nhánh 2 rồi xét `2→3`, cạnh tới BLACK này **không tạo chu trình**.

Vì vậy `if (visited[u]) cycle=true` là **sai** trên đồ thị có hướng. Chỉ cạnh tới đỉnh còn đang GRAY mới là back edge chỉ báo chu trình của DFS.

### 10.2. Phát hiện chu trình lặp không đệ quy

Có thể dùng stack frame ở mục 6 và duy trì màu:

- Push frame mới → đặt vertex thành GRAY.
- Từ frame đang hoạt động, gặp neighbor GRAY → có chu trình.
- Gặp WHITE → tạo frame con.
- Khi pop frame sau khi xét xong tất cả hàng xóm → đổi thành BLACK.

Một stack đỉnh mark-on-push đơn giản **không phân biệt** đã khám phá với đã hoàn tất, nên không được coi mọi visited là GRAY.

### 10.3. Đồ thị vô hướng khác

Trên **đồ thị vô hướng đơn**, DFS có thể phát hiện chu trình khi gặp neighbor đã visited mà neighbor **khác parent[v]**. Cạnh đến parent chính là chiều ngược của cạnh cây đã đi qua.

Với **đa đồ thị có cạnh song song**, hai cạnh nối u và v có thể tạo chu trình hai cạnh; nếu bỏ qua **tất cả** cạnh về parent, bạn có thể bỏ sót. Muốn chính xác, nên lưu **id cạnh** và chỉ bỏ qua đúng cạnh được dùng để đi vào v. Self-loop cũng là một chu trình theo quy ước thông thường.

Không dùng trực tiếp quy tắc parent dành cho vô hướng để phát hiện chu trình có hướng.

---

## 11. Dùng DFS để khôi phục đường đi

Nếu cần một đường đi từ s đến t, thực hiện DFS **bắt đầu ở s** và lưu parent khi khám phá đỉnh mới.

Nếu t không được thăm, không có đường đi từ s theo hướng cạnh đã cho. Nếu t có visited, truy ngược:

```text
path = []
current = t

while current != -1:
    path.add(current)
    if current == s:
        break
    current = parent[current]

if current != s:
    return "không có đường từ s đến t"

reverse(path)
return path
```

Các cạnh `parent[u]→u` có thật nên chuỗi sau khi đảo là một đường đi hợp lệ.

**Cạm bẫy của forest:** nếu dùng kết quả **duyệt toàn đồ thị**, t có thể đã visited do nằm trong một cây gốc khác s. Chỉ `visited[t]==true` chưa đủ chứng minh t tới được từ s. Phải kiểm tra chuỗi parent có dẫn về s hoặc chạy riêng DFS từ s.

### 11.1. DFS không cho đường đi ngắn nhất

Trên đồ thị không trọng số, DFS parent có thể đi theo một đường dài hơn đường tốt nhất. Nếu mục tiêu là **ít cạnh nhất**, dùng BFS. Nếu đồ thị có trọng số không âm và cần tổng trọng số nhỏ nhất, cân nhắc Dijkstra; đây là một bài toán khác với chỉ duyệt reachable.

---

## 12. Postorder và thứ tự topo của DAG

Trên **đồ thị có hướng không chu trình (DAG)**, lấy **đảo ngược postorder** của DFS chuẩn cho một thứ tự topo hợp lệ.

Với DAG:

```text
0: [1,2]
1: [3]
2: [3]
3: []
```

Nếu duyệt theo thứ tự ghi:

```text
Preorder:  [0,1,3,2]
Postorder: [3,1,2,0]
Đảo postorder: [0,2,1,3]
```

Thứ tự `[0,2,1,3]` hợp lệ vì trên mỗi cạnh `u→v`, u xuất hiện **trước** v.

### 12.1. Vì sao đảo postorder đúng?

Trong DFS chuẩn trên DAG, nếu đang xét cạnh `u→v`:
- Nếu v WHITE, ta hoàn tất nhánh v trước khi hoàn tất u.
- Nếu v BLACK, v đã hoàn tất trước u.
- Không thể có v GRAY, vì cạnh tới GRAY sẽ tạo chu trình.

Vậy thời điểm hoàn tất của u luôn **sau** v. Đảo thứ tự hoàn tất đưa u trước v.

**Không dùng phương pháp này khi đồ thị có chu trình**: topo order không tồn tại. Cũng không được dùng “đảo thứ tự pop stack đỉnh mark-on-push” thay postorder chuẩn, vì lịch xử lý ấy không có cùng ngữ nghĩa hoàn tất.

---

## 13. Thời điểm vào/ra và quan hệ tổ tiên

Một số thuật toán DFS lưu:

- `tin[v]`: thời điểm khám phá v.
- `tout[v]`: thời điểm hoàn tất v.

Ví dụ:

```text
timer = 0
DFS(v):
    visited[v] = true
    tin[v] = ++timer

    for u trong graph[v]:
        if !visited[u]:
            parent[u] = v
            DFS(u)

    tout[v] = ++timer
```

Với đệ quy chuẩn, u là **tổ tiên nghiêm ngặt** của v trong cây DFS nếu và chỉ nếu:

\[
tin[u]<tin[v]<tout[v]<tout[u].
\]

Đối với tổ tiên không nghiêm ngặt (cho phép u=v), điều kiện cần sửa dấu tương ứng.

Stack frame tái hiện chính xác thời điểm **push frame = enter** và **pop frame = exit**, nên giữ được tính chất ấy. Stack đỉnh mark-on-push không tự tái hiện chuỗi frame đang hoạt động vì có thể push nhiều hàng xóm trước khi xử lý nhánh đầu tiên.

### 13.1. Phân loại cạnh trong DFS có hướng

Nếu có đầy đủ trạng thái ba màu và cây DFS chuẩn:

- **Tree edge:** cạnh dùng để khám phá một đỉnh WHITE lần đầu.
- **Back edge:** cạnh tới đỉnh GRAY là tổ tiên đang hoạt động.
- **Forward edge:** cạnh không phải cạnh cây, tới một hậu duệ đã hoàn tất.
- **Cross edge:** cạnh tới đỉnh đã hoàn tất không có quan hệ tổ tiên–hậu duệ như trên.

Không phân loại các cạnh này bằng một thứ tự `popOrder` được sinh từ một stack đỉnh đơn giản mà chưa chứng minh sự tương ứng với **thời điểm vào/ra của DFS chuẩn**.

---

## 14. Các trường hợp biên

| Trường hợp | Kết quả hoặc lưu ý |
| --- | --- |
| Đồ thị rỗng | Duyệt **forest** trả danh sách rỗng; duyệt từ nguồn phải từ chối nguồn |
| Một đỉnh không cạnh | Preorder và postorder đều `[0]` |
| Self-loop `0→0` | Duyệt một lần; directed cycle=true |
| Hai cạnh cùng hướng `0→1` | Không khám phá 1 hai lần |
| Cạnh vào một đỉnh từ nhiều nguồn | Parent phụ thuộc cách đánh dấu/lịch duyệt |
| Đồ thị không liên thông | Cần vòng duyệt các gốc để thăm tất cả |
| Đồ thị có hướng `1→0` | Từ 0 chưa chắc tới được 1 |
| Đỉnh có neighbor ngoài `[0,n)` | Báo input không hợp lệ |
| Danh sách kề null | Báo input không hợp lệ |
| Đường sâu rất dài | Bản đệ quy có nguy cơ `StackOverflowError` |
| Đổi thứ tự hàng xóm | Preorder, parent và postorder có thể đổi |
| Đồ thị vô hướng đa cạnh | Phát hiện chu trình cần phân biệt từng cạnh |

Với mảng `int[][]`, có thể có self-loop và các neighbor bị lặp. Ba phiên bản duyệt vẫn không bị vòng lặp vô hạn vì đánh dấu đúng thời điểm; riêng những thuật toán phân loại cạnh/chu trình có thể cần chính sách xử lý đa cạnh chi tiết.

---

## 15. Kiểm thử tính đúng

### 15.1. Thuộc tính của forest

Với một đồ thị có V đỉnh hợp lệ, một kết quả duyệt **toàn bộ đồ thị** phải có:

1. Đúng V phần tử trong preorder hoặc popOrder.
2. Mỗi id đỉnh từ 0 tới V−1 xuất hiện **đúng một lần**.
3. Mọi gốc có `parent[root]=-1`.
4. Mỗi đỉnh không phải gốc có parent hợp lệ, và tồn tại cạnh thật `parent[v]→v`.
5. Chuỗi parent dẫn về một gốc, không tạo chu trình.
6. Với đệ quy và stack frame, postorder cũng chứa đúng V đỉnh, mỗi đỉnh một lần.
7. Với cùng thứ tự hàng xóm, đệ quy và frame phải có **cùng roots, preorder, postorder, parent**.

### 15.2. Kiểm thử đối chiếu

Với n nhỏ (0 tới 10), sinh nhiều đồ thị có hướng ngẫu nhiên, có thể có self-loop, nhiều cạnh cùng đích, đồ thị rỗng và cạnh hội tụ:

1. Chạy `recursiveForest`.
2. Chạy `frameStackForest`.
3. So sánh chính xác tất cả danh sách `roots/preorder/postorder` và mảng parent.
4. Chạy `vertexStackForest`; chỉ kiểm tra tính bao phủ đỉnh và parent hợp lệ, **không đòi thứ tự giống đệ quy**.
5. So kết quả phát hiện chu trình có hướng với một thuật toán độc lập như **Kahn** (xóa dần đỉnh indegree bằng 0): Kahn không thể loại hết đỉnh nếu có chu trình.

Những kiểm thử này giúp phát hiện lỗi tăng `nextNeighbor` hoặc lỗi cập nhật visited trước/sau push.

### 15.3. Kiểm thử thứ tự đầu ra

Không nên hard-code preorder cho một đồ thị nếu **không cố định thứ tự danh sách kề**. Nếu một chương trình xử lý neighbor theo thứ tự nhập, input thay thứ tự các cạnh có thể dẫn đến preorder khác mà vẫn đúng.

Trong chương trình Java của bài, danh sách kề có thứ tự cố định theo mảng được khai báo, vì vậy stdout đã trình bày là **xác định**.

---

## 16. Những lỗi thường gặp

1. Quên `visited[]` hoặc đánh dấu quá muộn, khiến chu trình tạo vòng gọi vô hạn.
2. Không gọi DFS từ những đỉnh chưa visited khi mục tiêu là duyệt **toàn đồ thị**.
3. Dùng stack đỉnh mark-on-push rồi đòi preorder/parent giống recursion trong mọi đồ thị.
4. Quên **đảo thứ tự push** khi muốn ưu tiên hàng xóm đầu tiên được pop trước ở một nút.
5. Tưởng đảo thứ tự push đã đủ mô phỏng đệ quy, bỏ qua trường hợp đỉnh được đánh dấu trước khi nhánh đầu xử lý.
6. Gọi `popOrder` là thứ tự “khám phá lúc visited” dù đã mark ngay khi push.
7. Mark-on-pop nhưng không kiểm tra visited sau pop, làm mở rộng một đỉnh nhiều lần.
8. Gán parent khi push các bản sao mark-on-pop mà không xác định chính sách chọn bản sao hiệu lực.
9. Stack frame không lưu `nextNeighbor`, khiến mỗi lần quay lại frame cha phải duyệt từ đầu.
10. Tăng `nextNeighbor` sai vị trí, làm bỏ sót hoặc xét lặp hàng xóm.
11. Quên ghi postorder **lúc frame hoàn tất**, không phải lúc vừa pop một đỉnh trong stack đơn giản.
12. Dùng `visited` boolean để phát hiện chu trình có hướng, nhầm BLACK với GRAY.
13. Dùng quy tắc neighbor khác parent của đồ thị vô hướng trên đồ thị có hướng.
14. Quên rằng đa cạnh vô hướng cần nhận diện **id cạnh** để phát hiện chu trình chính xác.
15. Trả parent path như đường đi **ngắn nhất** dù DFS không có bảo đảm đó.
16. Dùng visited của forest làm bằng chứng reachable từ một nguồn s bất kỳ.
17. Quên từ chối neighbor ngoài khoảng hoặc danh sách kề null.
18. Dùng đệ quy trên chuỗi cực dài mà không cân nhắc giới hạn call stack.
19. Nghĩ stack tường minh không thể hết bộ nhớ, dù nó vẫn tốn `O(V)` hoặc hơn.
20. Gọi kết quả đảo popOrder là topo order mà không có chứng minh postorder chuẩn và tính DAG.
21. Nhầm số cây DFS trong đồ thị có hướng với số SCC hoặc thành phần liên thông yếu.
22. Nói `O(V+E)` mà quên rằng quét từng hàng của ma trận kề thường tốn `O(V²)`.

---

## 17. Bài tập tự kiểm tra

**Bài 1 — Vết đệ quy.** Với đồ thị ở mục 1, hãy tự tính roots, preorder, postorder và parent của DFS đệ quy khi duyệt gốc tăng dần.

**Bài 2 — Stack đỉnh.** Từ cùng đồ thị, dùng stack LIFO mark-on-push và push neighbor theo thứ tự ngược. Thứ tự pop toàn đồ thị là gì? Vì sao khác recursion?

**Bài 3 — Frame.** Để mô phỏng `DFS(v)` chính xác cần lưu gì trong frame? Khi nào phải ghi postorder?

**Bài 4 — Chu trình.** Với cạnh `1→2,2→4,4→1`, đỉnh nào đang GRAY khi xét cạnh `4→1`? Vì sao đây là chu trình?

**Bài 5 — DAG.** Cho `0→1,0→2,1→3,2→3`. Tính postorder đệ quy và đảo nó để lấy một topo order.

**Bài 6 — Rừng DFS.** Với đồ thị vô hướng gồm `0–1,1–2,3–4` và đỉnh 5 cô lập, có mấy cây DFS? Nếu các cạnh có hướng, kết luận này còn tự đúng không?

**Bài 7 — Độ phức tạp.** Chứng minh DFS dùng danh sách kề có thời gian `O(V+E)`. Nếu đổi sang ma trận kề và quét mọi cột của mỗi đỉnh thì sao?

**Bài 8 — Parent.** Với `parent=[-1,0,1,1,2,-1,5]`, khôi phục đường cây từ 0 đến 4. Có thể dùng forest này để nói 0 tới được 6 không?

**Bài 9 — Stack overflow.** Với một đồ thị có một đường dài 200.000 đỉnh, bạn chọn recursion hay stack frame nếu cần postorder chuẩn? Vì sao?

**Bài 10 — Mark-on-pop.** Vì sao một đỉnh có thể bị push nhiều lần? Làm cách nào để mỗi đỉnh chỉ được mở rộng một lần?

**Bài 11 — Cạnh trùng.** Trong đồ thị vô hướng có hai cạnh khác nhau nối cùng u và v, vì sao kiểm tra neighbor khác parent có thể bỏ sót chu trình hai cạnh?

**Bài 12 — Directed cycle.** Nếu gặp cạnh tới một đỉnh BLACK, có được kết luận chu trình không? Hãy nêu ví dụ.

**Bài 13 — Truy vết.** Một DFS từ nguồn s có parent cho đỉnh t. Các điều kiện nào cần kiểm tra trước khi tuyên bố tìm được đường s→t?

**Bài 14 — DFS frame.** Sau khi đọc một neighbor u ở `graph[v][nextNeighbor]`, tại sao phải tăng con trỏ của frame v **trước khi push frame u**?

**Bài 15 — Biên.** Một đồ thị có 0 đỉnh được truyền vào hàm duyệt forest. Hàm nên trả gì? Nếu được yêu cầu duyệt từ s=0, phải xử lý ra sao?

### Đáp án gợi ý

1. Roots `[0,5]`; preorder `[0,1,2,4,3,5,6]`; postorder `[4,2,3,1,0,6,5]`; parent `[-1,0,1,1,2,-1,5]`.
2. Pop order `[0,1,3,4,2,5,6]`. Đỉnh 2 đã được mark khi push từ 0, khiến 1 không đi sâu vào 2 như recursion.
3. Lưu `vertex` và `nextNeighbor`. Ghi postorder và pop chỉ sau khi đã xét hết hàng xóm của frame ấy.
4. Đỉnh 1 đang GRAY, trên chuỗi lời gọi hoạt động `1→2→4`; cạnh `4→1` khép một chu trình.
5. Postorder `[3,1,2,0]`, đảo `[0,2,1,3]` là topo order hợp lệ.
6. Ba cây: `{0,1,2}`, `{3,4}`, `{5}`. Với đồ thị có hướng, số cây DFS phụ thuộc thứ tự gốc, không mặc định bằng số thành phần liên thông yếu hoặc SCC.
7. Mỗi đỉnh mở rộng một lần, mỗi mục kề xét một lần → `O(V+E)`. Với ma trận quét đủ V cột, `O(V²)`.
8. Truy ngược 4→2→1→0, đảo thành `0→1→2→4`. Không thể kết luận 0 tới được 6 từ việc 6 visited vì 6 nằm trong cây gốc 5.
9. Chọn stack frame để tránh call stack sâu và vẫn giữ đúng postorder/parent như recursion.
10. Trước lần pop đầu, nhiều cạnh khác nhau có thể push cùng đỉnh chưa visited. Sau pop, kiểm tra và đánh dấu; mọi bản sao về sau bị bỏ.
11. Khi gặp cạnh thứ hai tới parent, so theo id đỉnh vẫn thấy parent và bỏ qua, dù đó là cạnh khác với cạnh đã đi; cần id cạnh.
12. Không. Trong DAG `0→1→3` và `0→2→3`, khi duyệt qua 2 cạnh `2→3` có thể tới BLACK mà không hình thành chu trình.
13. Cần dùng parent/visited của lượt DFS **từ đúng nguồn s**, hoặc truy vết chứng minh chuỗi parent của t dẫn về s; mọi cạnh cha–con phải tồn tại.
14. Vì sau khi con hoàn tất, frame v phải tiếp tục **hàng xóm kế tiếp**, không xử lý lại u và không đẩy con lần nữa.
15. Forest trả danh sách/mảng rỗng. Duyệt từ nguồn 0 phải từ chối vì 0 không thuộc tập đỉnh.

---

## Ghi nhớ

DFS có thời gian `O(V+E)` trên danh sách kề và bộ nhớ phụ `O(V)` đối với phiên bản đệ quy, stack đỉnh **mark-on-push** và stack frame. **Đệ quy** ngắn và biểu đạt chính xác tiến trình đi sâu rồi quay lui, nhưng có thể gây `StackOverflowError` trên một đường rất dài. **Stack chỉ chứa đỉnh** là cách lặp tiện lợi để duyệt reachable; nếu đánh dấu khi push, kể cả **đảo thứ tự push** vẫn không bảo đảm cùng preorder/parent với đệ quy. **Stack frame** lưu `(vertex,nextNeighbor)`, chỉ pop khi hết hàng xóm, vì vậy tái hiện đúng **preorder, postorder, parent và thời điểm enter/exit** của đệ quy. Luôn phân biệt duyệt **một nguồn** với **rừng toàn đồ thị**, đồ thị có hướng/vô hướng, và yêu cầu thật sự của bài toán: thăm đủ đỉnh, truy vết, phát hiện chu trình hay xử lý postorder.

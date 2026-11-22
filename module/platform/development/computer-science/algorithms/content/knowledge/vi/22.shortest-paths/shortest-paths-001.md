# Phép nới lỏng cạnh và điều kiện duy trì khoảng cách

> **Chủ đề:** Computer Science Algorithms → Đường đi ngắn nhất (*Shortest Paths*).  
> **Mục tiêu:** Hiểu chính xác phép **nới lỏng cạnh** (*edge relaxation*), bất biến “khoảng cách đang lưu có một đường đi làm chứng”, điều kiện duy trì/cải thiện `dist`, quan hệ bất đẳng thức tam giác, trạng thái chưa tới được, truy vết `parent`, điểm dừng và điều kiện đúng của BFS, Dijkstra, Bellman–Ford, DAG shortest path và 0-1 BFS. Có sáu chương trình Java 17+ độc lập với lệnh chạy và stdout, cùng kiểm thử, phản ví dụ và bài tập.

## 1. Đường đi ngắn nhất là đại lượng nào?

Cho đồ thị có hướng `G=(V,E)`; mỗi cạnh `(u,v)` có trọng số `w(u,v)` (âm, bằng 0 hoặc dương tùy bài toán). Một **đường đi** từ nguồn `s` đến đỉnh `v` là dãy đỉnh bắt đầu ở s, kết thúc ở v, các cặp liên tiếp đều là cạnh hợp lệ. Tổng trọng số là tổng trọng số các cạnh trên đường đi.

Ta ký hiệu:

`δ(s,v) = trọng số nhỏ nhất của một đường đi từ s tới v`.

Một số quy ước quan trọng:

- `δ(s,s)=0` nếu không có **chu trình âm tới được từ s rồi quay lại s**; đường đi rỗng dài 0 luôn là ứng viên.
- Nếu **không có đường đi** từ s đến v: `δ(s,v)=+∞` theo quy ước toán học.
- Nếu từ s có thể tới một chu trình có **tổng trọng số âm**, và từ chu trình đó có thể tiếp tục tới v, thì có thể đi vòng chu trình âm tùy nhiều lần trước khi tới v. Khi ấy không tồn tại khoảng cách ngắn nhất hữu hạn: infimum là `−∞`.
- Đường có trọng số bằng nhau có thể không duy nhất. Một thuật toán có thể trả **bất kỳ** đường đi ngắn nhất nào nếu đề không yêu cầu quy tắc phá hòa.

### 1.1. Tại sao dùng ký hiệu `dist` thay vì gọi ngay là khoảng cách thật?

Thuật toán thường lưu `dist[v]`: **giá trị tốt nhất đã biết cho tới thời điểm hiện tại**, không phải lúc nào cũng bằng `δ(s,v)`.

Ví dụ nguồn `S` có cạnh trực tiếp đến A trọng số 10, nhưng còn đường `S→B→A` với tổng trọng số `3+4=7`.

Ngay sau khi thấy cạnh `S→A`, ta có thể gán `dist[A]=10`. Đây là **một đường khả thi** từ S tới A, nhưng chưa phải đường ngắn nhất. Khi khám phá `S→B→A`, ta thay bằng 7.

Cần phân biệt:

- **Giá trị ứng viên:** `candidate=dist[u]+w(u,v)`.
- **Giá trị tốt nhất đang lưu:** `dist[v]`.
- **Khoảng cách ngắn nhất thật:** `δ(s,v)`.

Trong giai đoạn chưa hoàn tất, thường:

`dist[v] >= δ(s,v)`

với những đỉnh có khoảng cách ngắn nhất hữu hạn và `dist[v]` là độ dài một **walk** (hành trình có thể lặp đỉnh) đã thực sự được tìm thấy. Vì đường ngắn nhất không thể dài hơn một hành trình hợp lệ, `dist` là một **cận trên có nhân chứng**, không phải một cận dưới.

### 1.2. Cạnh có hướng và vô hướng

Với cạnh có hướng `u→v`, phép nới lỏng này chỉ giúp đi **từ u sang v**. Không được tự động nới lỏng ngược `v→u` nếu đồ thị không cho cạnh đó.

Với cạnh vô hướng `{u,v}` trọng số w, biểu diễn bằng **hai hướng** `u→v` và `v→u` khi chạy thuật toán trên danh sách cạnh có hướng.

**Cảnh báo đặc biệt:** một cạnh vô hướng trọng số âm tạo thành một vòng đi-về có tổng âm `2w`. Nếu cho phép lặp cạnh, bài shortest-walk sẽ có chu trình âm; không được áp dụng Dijkstra.

## 2. Phép nới lỏng cạnh — công thức nền tảng

Cho một cạnh có hướng `(u,v)` trọng số `w`. Nếu đã biết một đường đi từ s tới u dài `dist[u]`, ta có thể nối thêm `(u,v)` để được một đường đi từ s tới v với độ dài:

`candidate = dist[u] + w`.

Nếu `candidate` **nhỏ hơn** giá trị tốt nhất hiện có ở v, ta cập nhật:

`dist[v] = candidate`.

Đồng thời, nếu cần khôi phục đường đi:

`parent[v] = u`.

Pseudocode:

```text
relax(u, v, w):
    if u chưa tới được:
        return false

    candidate = dist[u] + w  // cộng có kiểm tra tràn số

    if v chưa tới được OR candidate < dist[v]:
        dist[v] = candidate
        parent[v] = u
        đánh dấu v đã tới được
        return true

    return false
```

**Phép nới lỏng chỉ có tác dụng khi tìm được đường đi tốt hơn.** Cạnh đã được xét trước vẫn có thể trở nên hữu ích sau khi `dist[u]` giảm. Vì vậy, số lần xét cạnh và thứ tự xét cạnh tùy thuộc thuật toán.

### 2.1. “Nới lỏng” không có nghĩa là tăng khoảng cách

Từ *relaxation* có thể gây nhầm. Trong thuật toán tìm đường đi ngắn nhất, phép nới lỏng làm **giảm** giá trị `dist[v]` khi có một đường tốt hơn, hoặc giữ nguyên. Không có bước nới lỏng chuẩn nào tăng một khoảng cách hữu hạn đã lưu.

Bất biến sau mỗi thao tác:

`dist_new[v] <= dist_old[v]`

nếu xem trạng thái chưa tới được là `+∞`. Các đỉnh khác không đổi.

### 2.2. Không nới lỏng từ đỉnh chưa tới được

Nếu `dist[u]=+∞` theo toán học, biểu thức `+∞ + w` không phải một đường đi được phát hiện từ s tới v. Trong mã số nguyên, dùng giá trị sentinel `INF` rồi cộng w có thể gây tràn hoặc tạo ra một ứng viên **giả**.

Vì thế **kiểm tra u đã tới được** trước. Trong các chương trình Java dưới đây, ta dùng `boolean[] reachable` riêng, tránh việc một số `long` đặc biệt bị nhầm với `+∞`.

### 2.3. Khi bằng nhau, thường không cập nhật

Nếu `candidate == dist[v]`, ta đã có một đường đi cùng độ dài. Khi chỉ cần **một** đường ngắn nhất, quy tắc:

`candidate < dist[v]`

giữ `parent[v]` cũ, làm kết quả ổn định theo thứ tự xét cạnh.

Nếu dùng `<=` và luôn cập nhật parent khi hòa, trên đồ thị có **cạnh trọng số 0** có thể tạo chu trình trong quan hệ parent. Nếu cần liệt kê **mọi** đường ngắn nhất, phải thiết kế cấu trúc riêng, ví dụ các cạnh thỏa `dist[u]+w=dist[v]`, và chú ý chu trình trọng số 0 có thể khiến số **walk** ngắn nhất không hữu hạn.

### 2.4. Relaxation không tự quyết định thứ tự thăm

Một hàm `relax` không phải một thuật toán hoàn chỉnh. Bài shortest path cần chính sách:

- **Cạnh nào được nới lỏng khi nào?**
- **Có cần nới lỏng lặp lại không?**
- **Khi nào một `dist[v]` được khẳng định đã tối ưu?**
- **Khi nào được kết luận không có đường hoặc có chu trình âm?**

BFS, Dijkstra, Bellman–Ford, DAG shortest path và 0-1 BFS khác nhau chủ yếu ở **lịch xét cạnh / trạng thái** và điều kiện đảm bảo kết quả.

## 3. Bất biến quan trọng: mỗi `dist` hữu hạn có nhân chứng

Đặt `reachable[s]=true`, `dist[s]=0`, các đỉnh khác `reachable=false`.

**Bất biến A — tính khả thi:** nếu `reachable[v]=true`, tồn tại một **walk từ s tới v** có tổng trọng số bằng `dist[v]`.

**Chứng minh quy nạp:**

1. Ban đầu s có đường rỗng trọng số 0; các đỉnh khác chưa gán nên bất biến đúng.
2. Giả sử `dist[u]` là độ dài một walk từ s tới u.
3. Khi nới lỏng `u→v` bằng `dist[u]+w(u,v)`, nối thêm cạnh `(u,v)` tạo walk thực sự từ s tới v với trọng số đúng bằng ứng viên.
4. Nếu ứng viên tốt hơn thì cập nhật. Vì vậy giá trị mới ở v vẫn có một walk làm chứng.

Nếu không có chu trình âm ảnh hưởng tới v, mọi walk hợp lệ không thể có trọng số nhỏ hơn khoảng cách ngắn nhất `δ(s,v)`. Vậy với mọi đỉnh reachable có khoảng cách hữu hạn:

`dist[v] >= δ(s,v)`.

Nếu thuật toán chỉ cắt nhánh/đánh dấu theo đúng điều kiện, invariant này không phụ thuộc việc các cạnh đã xét theo thứ tự tốt hay chưa.

### 3.1. Đường đi thực sự và mảng `parent`

Khi cập nhật `parent[v]=u` cùng với `dist[v]`, ta ghi lại cách ứng viên được tạo. Tuy nhiên, trong thuật toán cho phép **cải thiện lại** các đỉnh, việc một tiền nhiệm `parent[u]` thay đổi sau đó có thể khiến tổng trọng số của **chuỗi parent hiện tại** không còn khớp tạm thời với `dist[v]`.

Vì thế nên phân biệt:

- **Bất biến khoảng cách có nhân chứng:** giá trị `dist[v]` từng được tạo từ một walk hợp lệ; đúng sau từng relax.
- **Tính hợp lệ của cây parent cuối cùng:** thường được bảo đảm sau khi thuật toán hoàn tất đúng và không có chu trình âm ảnh hưởng. Trong lúc còn chạy, không nên sử dụng parent hiện tại như một chứng chỉ độc lập cho mọi đỉnh mà chưa kiểm tra.

Với Dijkstra trọng số không âm và quy tắc chỉ cập nhật khi **nhỏ hơn nghiêm ngặt**, các parent cuối cùng mô tả đường đi ngắn nhất. Với Bellman–Ford có chu trình âm tới được, không được mặc nhiên dùng parent để dựng một “đường ngắn nhất”, vì khoảng cách hữu hạn có thể không tồn tại.

### 3.2. Giá trị chưa tới được không giống khoảng cách bằng 0

`reachable[v]=false` nghĩa là thuật toán **chưa tìm ra** walk từ s tới v. Sau khi thuật toán kết thúc và đã xét đầy đủ, đó mới là kết luận **không tồn tại đường đi**.

Trái lại `reachable[v]=true`, `dist[v]=0` hoàn toàn có thể hợp lệ, ví dụ nguồn, cạnh trọng số 0, hoặc tổng đường đi gồm các cạnh dương/âm triệt tiêu nhau.

Không dùng `0` làm sentinel “chưa tới được” nếu 0 có thể là khoảng cách thật.

## 4. Ví dụ từng phép nới lỏng

Ta có các cạnh xét **theo thứ tự cố ý chọn** sau, nguồn đỉnh 0:

| Lượt | Cạnh | Kết quả |
|---:|---|---|
| 1 | `0→1 (10)` | `dist[1]: ∞→10` |
| 2 | `0→2 (3)` | `dist[2]: ∞→3` |
| 3 | `2→1 (4)` | `dist[1]: 10→7` |
| 4 | `1→3 (2)` | `dist[3]: ∞→9` |
| 5 | `2→3 (9)` | Ứng viên `3+9=12`, **không** hơn 9 |
| 6 | `3→4 (1)` | `dist[4]: ∞→10` |
| 7 | `0→4 (50)` | Ứng viên 50, không hơn 10 |
| 8 | `1→3 (2)` | Bằng 9; giữ parent cũ |
| 9 | `5→2 (−100)` | Đỉnh 5 chưa tới được; **bỏ qua** |

Kết quả:

`dist=[0,7,3,9,10,∞]`.

`parent=[-1,2,0,1,3,-1]`.

Đường đi từ 0 tới 4 lần theo parent là:

`0→2→1→3→4`,

trọng số `3+4+2+1=10`.

Đỉnh 5 chưa được phát hiện; cạnh `5→2` có trọng số rất âm cũng **không** làm giảm khoảng cách từ nguồn 0 nếu không có đường nào từ 0 tới 5.

Đây là minh họa **thao tác**, chưa phải chứng minh rằng một lần xét các cạnh theo thứ tự bất kỳ đủ để tính ngắn nhất trên **mọi** đồ thị. Ở ví dụ này, thứ tự xét may mắn lan truyền được các cải thiện cần thiết.

## 5. Java 17 — chương trình quan sát từng lần relax

Lưu thành **EdgeRelaxationTraceDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class EdgeRelaxationTraceDemo {
    record Edge(int from, int to, long weight) {}

    static boolean relax(Edge e, long[] dist,
                         boolean[] reachable, int[] parent) {
        int u = e.from();
        int v = e.to();

        if (!reachable[u]) {
            return false;
        }

        long candidate = Math.addExact(dist[u], e.weight());

        if (!reachable[v] || candidate < dist[v]) {
            reachable[v] = true;
            dist[v] = candidate;
            parent[v] = u;
            return true;
        }

        return false;
    }

    static List<String> showDistances(long[] dist, boolean[] reachable) {
        List<String> result = new ArrayList<>();

        for (int i = 0; i < dist.length; i++) {
            result.add(reachable[i] ? Long.toString(dist[i]) : "INF");
        }

        return result;
    }

    public static void main(String[] args) {
        int n = 6;
        long[] dist = new long[n];
        boolean[] reachable = new boolean[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        reachable[0] = true;
        dist[0] = 0L;

        Edge[] sequence = {
            new Edge(0, 1, 10),
            new Edge(0, 2, 3),
            new Edge(2, 1, 4),
            new Edge(1, 3, 2),
            new Edge(2, 3, 9),
            new Edge(3, 4, 1),
            new Edge(0, 4, 50),
            new Edge(1, 3, 2),
            new Edge(5, 2, -100)
        };

        for (Edge e : sequence) {
            boolean changed = relax(e, dist, reachable, parent);
            System.out.println(e.from() + "->" + e.to()
                    + " (" + e.weight() + "): " + changed);
        }

        System.out.println("Distances: "
                + showDistances(dist, reachable));
        System.out.println("Parents: "
                + Arrays.toString(parent));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 EdgeRelaxationTraceDemo.java
java EdgeRelaxationTraceDemo
```

Stdout:

```text
0->1 (10): true
0->2 (3): true
2->1 (4): true
1->3 (2): true
2->3 (9): false
3->4 (1): true
0->4 (50): false
1->3 (2): false
5->2 (-100): false
Distances: [0, 7, 3, 9, 10, INF]
Parents: [-1, 2, 0, 1, 3, -1]
```

### 5.1. Những chi tiết có tính đúng cao

- Dùng `boolean[] reachable`: số 0 hay số âm vẫn có thể là khoảng cách hợp lệ.
- Dùng `Math.addExact`: nếu tổng vượt giới hạn `long`, chương trình ném `ArithmeticException` thay vì âm thầm tràn.
- `parent[v]` chỉ đổi khi ứng viên **nhỏ hơn**.
- Khi `reachable[u]==false`, **không cộng** trọng số vào dist[u], vì dist[u] mặc định bằng 0 trong mảng Java nhưng **không mang ý nghĩa đường từ nguồn**.
- Đoạn code là **bộ mô phỏng các lần relax được chỉ định**, không tự dò mọi cạnh cho tới hội tụ; muốn giải đồ thị tổng quát phải dùng lịch thuật toán thích hợp.

## 6. Điều kiện tối ưu sau khi hội tụ: bất đẳng thức tam giác

Với một đồ thị không có chu trình âm tới được từ s làm vô hạn dưới khoảng cách đang xét, khoảng cách ngắn nhất thật thỏa với mọi cạnh `(u,v)`:

`δ(s,v) <= δ(s,u) + w(u,v)`,

nếu u tới được. Đây là **bất đẳng thức tam giác trên cạnh** (*edge triangle inequality*): đi tới u theo đường ngắn nhất rồi đi qua `(u,v)` là một phương án tới v; đường ngắn nhất tới v không thể đắt hơn phương án ấy.

Tại một thời điểm, một cạnh **còn nới lỏng được** nếu:

`reachable[u] && (!reachable[v] || dist[v] > dist[u] + w)`.

Khi **không còn cạnh nào nới lỏng được**, `dist` thỏa các điều kiện:

`dist[v] <= dist[u] + w(u,v)` cho mọi cạnh có u tới được.

Kết hợp với bất biến có nhân chứng và nguồn `dist[s]=0`, có thể chứng minh `dist=δ` tại các đỉnh tới được, **nếu** không có chu trình âm tới được và các trạng thái/giá trị đã duy trì hợp lệ.

### 6.1. Chứng minh bằng một đường đi tối ưu

Chọn đỉnh v tới được và một đường đi ngắn nhất:

`P: s=v0→v1→...→vk=v`.

Vì không còn cạnh nào có thể cải thiện:

`dist[v1] <= dist[v0]+w(v0,v1)`.

Tiếp tục dọc đường:

`dist[vk] <= dist[s] + Σ cạnh trên P = δ(s,v)`.

Mặt khác, bất biến mỗi `dist[v]` có một walk từ s tới v cho biết:

`dist[v] >= δ(s,v)`.

Do đó:

`dist[v] = δ(s,v)`.

Với đỉnh hoàn toàn không tới được, không có phép relax nào có thể tạo walk giả từ nguồn; khi đã duyệt đầy đủ, `reachable=false` tương ứng `+∞`.

### 6.2. Vì sao trạng thái “hội tụ” không đủ khi có chu trình âm?

Giả sử chu trình tới được có tổng trọng số âm. Nếu mọi cạnh trên chu trình đều thỏa:

`dist[next] <= dist[current]+w`,

cộng các bất đẳng thức quanh chu trình sẽ suy ra:

`0 <= tổng trọng số chu trình`.

Điều này mâu thuẫn khi tổng là số âm. Bởi vậy không thể có một nghiệm khoảng cách hữu hạn thỏa tất cả bất đẳng thức cạnh trên chu trình âm tới được.

Trong trường hợp đó Bellman–Ford phát hiện một cạnh vẫn cải thiện sau `|V|−1` lượt quét toàn bộ cạnh (với số học chính xác và triển khai đúng), báo **chu trình âm tới được**. Không được coi các dist khi ấy là khoảng cách ngắn nhất hữu hạn của mọi đỉnh.

## 7. BFS: phép gán khoảng cách khi cạnh đều giá 1

Nếu mọi cạnh có cùng trọng số 1, BFS theo **FIFO queue** là một cơ chế nới lỏng đặc biệt:

`dist[v] = dist[u] + 1` khi v được phát hiện **lần đầu**.

Tại sao chỉ cần lần đầu? Vì BFS mở rộng theo lớp:

- Nguồn có khoảng cách 0.
- Mọi đỉnh cách 1 cạnh được phát hiện trước những đỉnh cách 2 cạnh.
- Tương tự, toàn bộ lớp d xuất hiện trước lớp d+1.

Khi `v` lần đầu được enqueue từ `u` ở lớp d, không thể tồn tại đường ít cạnh hơn tới v chưa được khám phá. Vì vậy **không cần cập nhật v thêm lần nữa**.

### 7.1. Bất biến queue

Đánh dấu v đã thăm **ngay khi enqueue**, không đợi dequeue. Khi đó:

- Mỗi đỉnh được thêm vào queue tối đa một lần.
- `dist[v]` sau lần đầu gán là khoảng cách ngắn nhất tính bằng **số cạnh**.
- `parent[v]=u` ở lúc phát hiện ghi nhận một đường ngắn nhất.

Nếu chỉ cần số bước, không cần tính `parent`. Nếu cần in đường, giữ `parent` và đi ngược từ đích.

### 7.2. Tại sao BFS không dùng được cho trọng số 2 hoặc −1?

BFS mặc định tối ưu **số cạnh**, không tối ưu tổng trọng số khác nhau. Một đường hai cạnh phí 100 mỗi cạnh có thể đắt hơn đường năm cạnh phí 1 mỗi cạnh.

Khi có trọng số khác nhau, không được giữ chính sách “khóa đỉnh mãi sau lần phát hiện đầu”. Ta có thể cần **nới lỏng lại** cùng đỉnh nếu xuất hiện đường có tổng phí tốt hơn, theo thuật toán phù hợp.

## 8. Java 17 — BFS với `dist=-1` biểu diễn chưa phát hiện

Lưu thành **BfsUnitDistanceDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class BfsUnitDistanceDemo {
    record Result(int[] dist, int[] parent) {}

    static Result bfs(List<List<Integer>> graph, int source) {
        int n = graph.size();
        if (source < 0 || source >= n) {
            throw new IllegalArgumentException("Invalid source");
        }

        int[] dist = new int[n];
        int[] parent = new int[n];
        Arrays.fill(dist, -1);
        Arrays.fill(parent, -1);

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        dist[source] = 0;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();

            for (int v : graph.get(u)) {
                if (dist[v] == -1) {
                    dist[v] = dist[u] + 1;
                    parent[v] = u;
                    queue.addLast(v);
                }
            }
        }

        return new Result(dist, parent);
    }

    static List<Integer> pathTo(int target, int[] dist, int[] parent) {
        if (dist[target] == -1) {
            return List.of();
        }

        List<Integer> path = new ArrayList<>();
        for (int v = target; v != -1; v = parent[v]) {
            path.add(v);
        }
        Collections.reverse(path);
        return path;
    }

    public static void main(String[] args) {
        List<List<Integer>> graph = List.of(
            List.of(1, 2),  // 0
            List.of(3),     // 1
            List.of(1, 3),  // 2
            List.of(4),     // 3
            List.of(),      // 4
            List.of()       // 5, không thể tới từ 0
        );

        Result r = bfs(graph, 0);
        System.out.println("Distances: "
                + Arrays.toString(r.dist()));
        System.out.println("Path to 4: "
                + pathTo(4, r.dist(), r.parent()));
        System.out.println("Unreachable 5: " + r.dist()[5]);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BfsUnitDistanceDemo.java
java BfsUnitDistanceDemo
```

Stdout:

```text
Distances: [0, 1, 1, 2, 3, -1]
Path to 4: [0, 1, 3, 4]
Unreachable 5: -1
```

**Chi phí:** `O(V+E)` thời gian, `O(V)` bộ nhớ phụ cho `dist`, `parent` và queue, chưa tính danh sách kề đầu vào.

Đây là một trường hợp mạnh hơn việc “cứ relax mãi đến khi ổn định”: hàng đợi theo lớp đảm bảo dist **đúng ngay khi được phát hiện**.

## 9. Dijkstra: chọn đỉnh có khoảng cách tạm thời nhỏ nhất

Dijkstra dùng cho cạnh có trọng số **không âm**. Nó duy trì các ước lượng `dist`; lần lượt **chốt** (*finalize/settle*) đỉnh chưa chốt có dist nhỏ nhất, rồi nới lỏng các cạnh đi ra của đỉnh đó.

### 9.1. Bất biến hai lớp

Đặt tập `S` gồm các đỉnh đã chốt.

- Với mọi `u∈S`, `dist[u]=δ(s,u)` (đã được chứng minh ngắn nhất).
- Với các đỉnh chưa chốt nhưng đã phát hiện, `dist[v]` là độ dài một đường từ s tới v tìm được trong quá trình mở rộng; nó chưa chắc tối ưu.

**Chứng minh chốt an toàn:** giả sử u có khoảng cách tạm thời nhỏ nhất trong các đỉnh chưa chốt. Nếu có một đường ngắn hơn tới u, xét đỉnh đầu tiên của đường đó nằm ngoài S và đỉnh ngay trước nó thuộc S. Khi chốt đỉnh trước, nới lỏng cạnh đi ra đã cung cấp một ước lượng không lớn hơn tiền tố của đường ngắn đó. Vì mọi trọng số không âm, phần còn lại không thể làm đường ngắn hơn tiền tố. Điều này mâu thuẫn với u là đỉnh chưa chốt nhỏ nhất.

Điều kiện **không âm** là then chốt. Với cạnh âm, một đỉnh đã chốt có thể được cải thiện qua một đường đi khám phá muộn, phá chứng minh.

### 9.2. PriorityQueue và entry cũ

Trong Java, `PriorityQueue` không có thao tác giảm khóa (*decrease-key*) trực tiếp cho một phần tử đang nằm trong heap. Cách phổ biến:

1. Khi `dist[v]` giảm, **thêm một entry mới** `(newDist,v)` vào queue.
2. Khi pop `(d,u)`, nếu `d != dist[u]`, đó là **entry cũ** (*stale*); bỏ qua.
3. Nếu u đã chốt, bỏ qua entry lặp.
4. Ngược lại chốt u và nới lỏng các cạnh đi ra.

Không được chốt mọi entry ngay lần được thêm queue: chỉ chốt khi **lấy ra với khóa nhỏ nhất hiện thời**.

### 9.3. Ví dụ đường đi tối ưu qua nhiều bước cải thiện

Các cạnh của đồ thị có hướng:

```text
S(0) -> A(1) : 4
S(0) -> B(2) : 2
S(0) -> D(4) : 20
B(2) -> A(1) : 1
A(1) -> C(3) : 3
B(2) -> C(3) : 7
B(2) -> D(4) : 10
C(3) -> D(4) : 1
```

Ban đầu A có giá trị 4 qua cạnh trực tiếp từ S. Khi xử lý B với dist 2, relax `B→A (1)` tạo ứng viên `2+1=3`, giảm A xuống 3. Khi xử lý A, C giảm thành 6; từ C, D giảm thành 7.

Kết quả:

`dist[S,A,B,C,D] = [0,3,2,6,7]`.

Một đường tối ưu tới D:

`S→B→A→C→D`, trọng số `2+1+3+1=7`.

## 10. Java 17 — Dijkstra có kiểm tra entry cũ và parent

Lưu thành **DijkstraRelaxationDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class DijkstraRelaxationDemo {
    record Edge(int to, long weight) {}
    record State(int vertex, long distance) {}

    static final String[] NAMES = {"S", "A", "B", "C", "D"};

    static final class Result {
        long[] dist;
        boolean[] reached;
        int[] parent;
        List<String> settledOrder = new ArrayList<>();
        int updates;
        int staleSkipped;

        Result(int n) {
            dist = new long[n];
            reached = new boolean[n];
            parent = new int[n];
            Arrays.fill(parent, -1);
        }
    }

    static List<List<Edge>> newGraph(int n) {
        List<List<Edge>> graph = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            graph.add(new ArrayList<>());
        }
        return graph;
    }

    static void addEdge(List<List<Edge>> graph,
                        int from, int to, long weight) {
        if (weight < 0) {
            throw new IllegalArgumentException(
                    "Dijkstra requires nonnegative weights");
        }
        graph.get(from).add(new Edge(to, weight));
    }

    static Result dijkstra(List<List<Edge>> graph, int source) {
        int n = graph.size();
        if (source < 0 || source >= n) {
            throw new IllegalArgumentException("Invalid source");
        }

        Result result = new Result(n);
        boolean[] settled = new boolean[n];

        PriorityQueue<State> pq = new PriorityQueue<>(
                Comparator.comparingLong(State::distance)
                        .thenComparingInt(State::vertex));

        result.reached[source] = true;
        result.dist[source] = 0L;
        pq.add(new State(source, 0L));

        while (!pq.isEmpty()) {
            State state = pq.remove();
            int u = state.vertex();

            if (settled[u] || state.distance() != result.dist[u]) {
                result.staleSkipped++;
                continue;
            }

            settled[u] = true;
            result.settledOrder.add(NAMES[u]);

            for (Edge edge : graph.get(u)) {
                int v = edge.to();
                long candidate = Math.addExact(
                        result.dist[u], edge.weight());

                if (!result.reached[v] || candidate < result.dist[v]) {
                    result.reached[v] = true;
                    result.dist[v] = candidate;
                    result.parent[v] = u;
                    result.updates++;
                    pq.add(new State(v, candidate));
                }
            }
        }

        return result;
    }

    static String showPath(int target, Result result) {
        if (!result.reached[target]) {
            return "unreachable";
        }

        List<String> names = new ArrayList<>();
        for (int v = target; v != -1; v = result.parent[v]) {
            names.add(NAMES[v]);
        }
        Collections.reverse(names);
        return String.join(" -> ", names);
    }

    public static void main(String[] args) {
        List<List<Edge>> graph = newGraph(5);

        addEdge(graph, 0, 1, 4);
        addEdge(graph, 0, 2, 2);
        addEdge(graph, 0, 4, 20);
        addEdge(graph, 2, 1, 1);
        addEdge(graph, 1, 3, 3);
        addEdge(graph, 2, 3, 7);
        addEdge(graph, 2, 4, 10);
        addEdge(graph, 3, 4, 1);

        Result r = dijkstra(graph, 0);
        System.out.println("Distances [S,A,B,C,D]: "
                + Arrays.toString(r.dist));
        System.out.println("Settled order: " + r.settledOrder);
        System.out.println("Path to D: " + showPath(4, r));
        System.out.println("Improving relaxations: " + r.updates);
        System.out.println("Stale entries skipped: " + r.staleSkipped);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 DijkstraRelaxationDemo.java
java DijkstraRelaxationDemo
```

Stdout:

```text
Distances [S,A,B,C,D]: [0, 3, 2, 6, 7]
Settled order: [S, B, A, C, D]
Path to D: S -> B -> A -> C -> D
Improving relaxations: 8
Stale entries skipped: 4
```

### 10.1. Diễn giải kết quả

- A từng có dist 4 rồi giảm còn 3; C từng có 9 rồi giảm thành 6; D từng có 20 và 12 rồi giảm thành 7.
- Queue chứa các entry cũ của A, C và D. `staleSkipped=4` cho dữ liệu này, phản ánh cơ chế heap không decrease-key.
- Mỗi khi nới lỏng **cải thiện thật**, `parent` được cập nhật cùng `dist`.
- `NAMES` là bảng tên minh họa cho đồ thị năm đỉnh cố định. Nếu chuyển thành thư viện xử lý đồ thị tùy ý, không để một danh sách tên năm phần tử áp cho đồ thị số đỉnh khác.

### 10.2. Trọng số bằng 0 có dùng Dijkstra được không?

**Có.** Điều kiện là `w>=0`, không phải `w>0`.

Với cạnh 0, hai đỉnh có thể có khoảng cách bằng nhau. Comparator và quy tắc cập nhật strict `<` tránh cập nhật parent vô ích khi hòa; Dijkstra vẫn chốt an toàn vì trọng số không âm.

### 10.3. Không được dùng Dijkstra khi có cạnh âm tùy ý

Một phản ví dụ kinh điển:

```text
S -> A: 2
S -> B: 5
B -> A: -10
```

Đường `S→B→A` có tổng `5−10=−5`, nhỏ hơn đường trực tiếp `S→A` có trọng số 2.

Nếu Dijkstra chốt A ở khoảng cách 2 trước B, nó sẽ **không** còn xem xét cải thiện qua cạnh âm về A theo bất biến chốt. Phải dùng Bellman–Ford, DAG shortest path nếu đồ thị không chu trình, hoặc kỹ thuật chuyên biệt có chứng minh.

**Không** chữa bằng cách “vẫn cho weight âm và để priority queue tự xử lý”, vì điều kiện chứng minh Dijkstra đã bị phá.

## 11. Bellman–Ford: lặp relax để lan truyền qua cạnh âm

Bellman–Ford cho phép cạnh trọng số âm và phát hiện **chu trình âm tới được từ nguồn**.

Ý tưởng:

1. `dist[s]=0`, các đỉnh khác chưa tới được.
2. Lặp tối đa `|V|−1` lượt; mỗi lượt quét **toàn bộ cạnh**, nới lỏng nếu tốt hơn.
3. Có thể dừng sớm nếu một lượt **không có cập nhật**.
4. Sau các lượt, quét thêm toàn bộ cạnh: nếu vẫn có thể cải thiện từ một đỉnh tới được, có **chu trình âm tới được**.

### 11.1. Vì sao cần tới `|V|−1` lượt?

Nếu không có chu trình âm ảnh hưởng tới nguồn, một đường đi ngắn nhất đơn giản có nhiều nhất `|V|−1` cạnh: nếu chứa chu trình với tổng không âm, có thể bỏ chu trình mà không làm trọng số tăng.

Xét một đường ngắn nhất có k cạnh. Dù quét cạnh theo thứ tự bất lợi, sau **mỗi lượt quét toàn bộ cạnh** ta có thể đảm bảo thông tin đường tối ưu lan thêm ít nhất một cạnh dọc đường đó. Vì `k<=|V|−1`, sau đủ `|V|−1` lượt các đường ngắn nhất đơn giản đều được xét đủ.

Một số cạnh có thể được nới lỏng nhiều bước **ngay trong cùng lượt** nếu thứ tự thuận lợi; đó là lý do vòng lặp có thể dừng sớm.

### 11.2. Cạnh âm không đồng nghĩa chu trình âm

Một cạnh `u→v` có weight -2 hoàn toàn có thể xuất hiện trong một đồ thị **không có chu trình âm**. Khi ấy đường ngắn nhất vẫn xác định.

Ví dụ:

```text
0 -> 1: 4
1 -> 2: -2
2 -> 3: 3
3 -> 4: 1
0 -> 2: 7
```

Đường ngắn nhất từ 0 tới 4 là `0→1→2→3→4` trọng số:

`4−2+3+1 = 6`.

Bellman–Ford xử lý được cạnh âm mà không cần sửa công thức relax.

### 11.3. Phát hiện chu trình âm phải xét khả năng tới được

Nếu một chu trình âm nằm trong **thành phần không thể tới từ s**, nó không ảnh hưởng đường đi ngắn nhất xuất phát từ s. Kiểm tra vòng extra pass phải chỉ xét cạnh có **đầu u tới được**.

Nếu có chu trình âm tới được, không có khoảng cách hữu hạn cho những đỉnh có thể tới **sau** chu trình ấy. Việc Bellman–Ford báo `negativeCycle=true` không có nghĩa mọi đỉnh của đồ thị đều có khoảng cách `−∞`: những đỉnh không bị ảnh hưởng vẫn có thể có khoảng cách hữu hạn.

### 11.4. Tại sao cạnh cập nhật sau `|V|−1` lượt chứng minh được chu trình âm?

Nếu mọi đường tối ưu hữu hạn có thể chọn là đường đơn với tối đa `|V|−1` cạnh, sau các lượt Bellman–Ford toàn bộ các giá trị sẽ đúng và không còn cạnh cải thiện. Nếu vẫn có cạnh cải thiện từ phần reachable, tồn tại một walk tốt hơn khi đi qua số cạnh nhiều hơn, đòi hỏi tận dụng chu trình giảm tổng trọng số; đó là một chu trình âm reachable.

Điều này giả sử đồ thị hữu hạn và không có **tràn số**, sai số hay lược bỏ cạnh.

## 12. Java 17 — Bellman–Ford với cạnh âm và phát hiện chu trình

Lưu thành **BellmanFordRelaxationDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class BellmanFordRelaxationDemo {
    record Edge(int from, int to, long weight) {}

    record Result(long[] dist, boolean[] reached, int[] parent,
                  List<Integer> improvements, boolean negativeCycle) {}

    static Result solve(int n, Edge[] edges, int source) {
        if (n <= 0 || source < 0 || source >= n) {
            throw new IllegalArgumentException("Invalid graph/source");
        }

        long[] dist = new long[n];
        boolean[] reached = new boolean[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        reached[source] = true;
        dist[source] = 0L;

        List<Integer> improvements = new ArrayList<>();

        for (int pass = 1; pass <= n - 1; pass++) {
            int changes = 0;

            for (Edge e : edges) {
                int u = e.from();
                int v = e.to();

                if (!reached[u]) {
                    continue;
                }

                long candidate = Math.addExact(dist[u], e.weight());

                if (!reached[v] || candidate < dist[v]) {
                    dist[v] = candidate;
                    reached[v] = true;
                    parent[v] = u;
                    changes++;
                }
            }

            improvements.add(changes);
            if (changes == 0) {
                break;
            }
        }

        boolean negativeCycle = false;

        for (Edge e : edges) {
            if (!reached[e.from()]) {
                continue;
            }

            long candidate = Math.addExact(
                    dist[e.from()], e.weight());

            if (!reached[e.to()] || candidate < dist[e.to()]) {
                negativeCycle = true;
                break;
            }
        }

        return new Result(dist, reached, parent,
                List.copyOf(improvements), negativeCycle);
    }

    static String showDistances(Result r) {
        List<String> values = new ArrayList<>();
        for (int v = 0; v < r.dist().length; v++) {
            values.add(r.reached()[v]
                    ? Long.toString(r.dist()[v]) : "INF");
        }
        return values.toString();
    }

    static List<Integer> pathTo(Result r, int target) {
        if (r.negativeCycle() || !r.reached()[target]) {
            return List.of();
        }

        List<Integer> path = new ArrayList<>();
        for (int at = target; at != -1; at = r.parent()[at]) {
            path.add(at);
        }
        Collections.reverse(path);
        return path;
    }

    public static void main(String[] args) {
        // Thứ tự cạnh bất lợi, cần tới bốn lượt lan truyền.
        Edge[] normal = {
            new Edge(3, 4, 1),
            new Edge(2, 3, 3),
            new Edge(1, 2, -2),
            new Edge(0, 1, 4),
            new Edge(0, 2, 7)
        };

        Result good = solve(5, normal, 0);
        System.out.println("Pass improvements: "
                + good.improvements());
        System.out.println("Distances: " + showDistances(good));
        System.out.println("Path to 4: " + pathTo(good, 4));
        System.out.println("Reachable negative cycle: "
                + good.negativeCycle());

        Edge[] reachableCycle = {
            new Edge(0, 1, 1),
            new Edge(1, 2, -3),
            new Edge(2, 1, 1)
        };
        System.out.println("Reachable cycle detected: "
                + solve(3, reachableCycle, 0).negativeCycle());

        Edge[] unreachableCycle = {
            new Edge(0, 1, 2),
            new Edge(3, 4, -5),
            new Edge(4, 3, 4)
        };
        System.out.println("Unreachable cycle detected: "
                + solve(5, unreachableCycle, 0).negativeCycle());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BellmanFordRelaxationDemo.java
java BellmanFordRelaxationDemo
```

Stdout:

```text
Pass improvements: [2, 2, 2, 1]
Distances: [0, 4, 2, 5, 6]
Path to 4: [0, 1, 2, 3, 4]
Reachable negative cycle: false
Reachable cycle detected: true
Unreachable cycle detected: false
```

### 12.1. Vì sao số lần cải thiện là `[2,2,2,1]`?

Lượt đầu cạnh từ 0 nằm **cuối danh sách**, nên chỉ gán được đỉnh 1 và đỉnh 2 (lần lượt 4 và 7). Lượt hai, cạnh `2→3` tạo 10 trước khi `1→2` giảm đỉnh 2 từ 7 xuống 2. Lượt ba, cải thiện được 4 rồi 3; lượt bốn cập nhật đỉnh 4 xuống 6.

Ví dụ cho thấy **một lượt quét cạnh không luôn đủ**, và thứ tự cạnh có thể ảnh hưởng số lượt cập nhật trung gian, nhưng không đổi đáp án khi thuật toán hoàn tất đúng.

### 12.2. Tính đúng về `pathTo` và chu trình âm

Hàm `pathTo` mẫu chỉ trả đường khi **không có bất kỳ chu trình âm reachable nào**. Đây là chính sách bảo thủ: một đồ thị có chu trình âm reachable vẫn có thể có những đỉnh **không bị ảnh hưởng** với đường ngắn nhất hữu hạn, nhưng demo không phân loại chi tiết những đỉnh đó.

Với bài tổng quát, cần xác định tập đỉnh bị ảnh hưởng bằng cách đánh dấu các đỉnh có thể cải thiện sau `n−1` lượt và lan truyền khả năng tới được từ chúng. **Không** dùng parent của một đỉnh bị ảnh hưởng để khôi phục một đường “ngắn nhất”.

### 12.3. Chi phí Bellman–Ford

- Mỗi lượt quét `E` cạnh.
- Tối đa `V−1` lượt, cộng một lượt kiểm chu trình âm.
- Thời gian `O(VE)`.
- Bộ nhớ phụ `O(V)` cho dist, reached, parent và danh sách số lần cải thiện.

Với n rất lớn và nhiều cạnh, Bellman–Ford có thể chậm hơn Dijkstra; đổi lại nó hỗ trợ cạnh âm và cung cấp khả năng nhận diện chu trình âm reachable.

## 13. Đường đi ngắn nhất trên DAG: relax đúng thứ tự topo

**DAG** (*directed acyclic graph*) là đồ thị có hướng **không có chu trình**. Trên DAG, có thể tính đường đi ngắn nhất từ s bằng cách duyệt các đỉnh theo **thứ tự topo** và nới lỏng toàn bộ cạnh đi ra của từng đỉnh.

Điểm quan trọng: trên DAG, cách này đúng **kể cả khi một số cạnh có trọng số âm**, vì không có chu trình để lặp nhằm giảm đường đi vô hạn.

### 13.1. Vì sao chỉ một lượt theo topo đủ?

Trong một thứ tự topo, với mọi cạnh `u→v`, u xuất hiện trước v. Do đó khi đến lượt xét v, tất cả **tiền nhiệm** có thể cung cấp một đường tốt hơn tới v đã được xét và đã nới lỏng cạnh sang v.

Bằng quy nạp theo thứ tự topo, khi xử lý v, `dist[v]` đã bằng đường ngắn nhất từ s tới v. Sau đó relax các cạnh đi ra của v là đủ; không cần quay lại v lần nữa.

Điều này khác với Bellman–Ford, nơi thứ tự cạnh bất kỳ có thể phải quét nhiều lượt để đẩy một cải thiện đi xa.

### 13.2. Thứ tự topo không phải thứ tự theo ID trong mọi đồ thị

Một input DAG có thể có cạnh từ đỉnh ID lớn đến ID nhỏ. Không được mặc định duyệt `0,1,2,...` là topo nếu chưa kiểm tra.

Có thể tạo thứ tự bằng thuật toán Kahn:

1. Đếm indegree của mỗi đỉnh.
2. Đưa các đỉnh có indegree 0 vào queue.
3. Lấy một đỉnh, đưa vào thứ tự; giảm indegree các đỉnh nhận cạnh từ nó.
4. Đỉnh nào vừa về 0 thì enqueue.
5. Nếu không lấy đủ V đỉnh, đồ thị **có chu trình**, không được chạy DAG shortest path.

### 13.3. Ví dụ

Đồ thị sáu đỉnh:

```text
0→1 (+2), 0→2 (+4)
1→2 (−3), 1→3 (+3)
2→3 (+2), 2→4 (+5)
3→4 (−1), 3→5 (+6)
4→5 (+2)
```

Thứ tự topo `[0,1,2,3,4,5]` hợp lệ. Từ 0:

`dist = [0,2,-1,1,0,2]`.

Đường tới 5:

`0→1→2→3→4→5`

có tổng trọng số:

`2−3+2−1+2=2`.

## 14. Java 17 — relax theo topo trên DAG có cạnh âm

Lưu thành **DagShortestPathRelaxationDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class DagShortestPathRelaxationDemo {
    record Edge(int from, int to, long weight) {}
    record Result(long[] dist, boolean[] reached,
                  int[] parent, List<Integer> topo) {}

    static Result shortestPath(int n, Edge[] edges, int source) {
        if (n <= 0 || source < 0 || source >= n) {
            throw new IllegalArgumentException("Invalid graph/source");
        }

        List<List<Edge>> outgoing = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            outgoing.add(new ArrayList<>());
        }

        int[] indegree = new int[n];
        for (Edge edge : edges) {
            outgoing.get(edge.from()).add(edge);
            indegree[edge.to()]++;
        }

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (int v = 0; v < n; v++) {
            if (indegree[v] == 0) {
                queue.addLast(v);
            }
        }

        List<Integer> topo = new ArrayList<>();
        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            topo.add(u);

            for (Edge edge : outgoing.get(u)) {
                int v = edge.to();
                indegree[v]--;
                if (indegree[v] == 0) {
                    queue.addLast(v);
                }
            }
        }

        if (topo.size() != n) {
            throw new IllegalArgumentException("Graph is not a DAG");
        }

        long[] dist = new long[n];
        boolean[] reached = new boolean[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        reached[source] = true;
        dist[source] = 0L;

        for (int u : topo) {
            if (!reached[u]) {
                continue;
            }

            for (Edge edge : outgoing.get(u)) {
                int v = edge.to();
                long candidate = Math.addExact(
                        dist[u], edge.weight());

                if (!reached[v] || candidate < dist[v]) {
                    reached[v] = true;
                    dist[v] = candidate;
                    parent[v] = u;
                }
            }
        }

        return new Result(dist, reached, parent, List.copyOf(topo));
    }

    static List<Integer> pathTo(Result result, int target) {
        if (!result.reached()[target]) {
            return List.of();
        }

        List<Integer> path = new ArrayList<>();
        for (int v = target; v != -1; v = result.parent()[v]) {
            path.add(v);
        }
        Collections.reverse(path);
        return path;
    }

    public static void main(String[] args) {
        Edge[] edges = {
            new Edge(0, 1, 2),
            new Edge(0, 2, 4),
            new Edge(1, 2, -3),
            new Edge(1, 3, 3),
            new Edge(2, 3, 2),
            new Edge(2, 4, 5),
            new Edge(3, 4, -1),
            new Edge(3, 5, 6),
            new Edge(4, 5, 2)
        };

        Result r = shortestPath(6, edges, 0);
        System.out.println("Topo: " + r.topo());
        System.out.println("Distances: " + Arrays.toString(r.dist()));
        System.out.println("Path to 5: " + pathTo(r, 5));

        Edge[] cycle = {
            new Edge(0, 1, 1),
            new Edge(1, 2, 1),
            new Edge(2, 0, -3)
        };

        boolean rejected = false;
        try {
            shortestPath(3, cycle, 0);
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("Cycle rejected: " + rejected);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 DagShortestPathRelaxationDemo.java
java DagShortestPathRelaxationDemo
```

Stdout:

```text
Topo: [0, 1, 2, 3, 4, 5]
Distances: [0, 2, -1, 1, 0, 2]
Path to 5: [0, 1, 2, 3, 4, 5]
Cycle rejected: true
```

### 14.1. Vì sao topo của ví dụ là thứ tự đã in?

Indegree ban đầu của đỉnh 0 bằng 0, các đỉnh khác đều có cạnh đi vào từ một đỉnh trước đó. Khi loại 0, đỉnh 1 trở thành indegree 0; tiếp theo 2,3,4,5. Vì queue chứa các đỉnh mới indegree 0 theo thứ tự phát hiện, kết quả là `[0,1,2,3,4,5]`.

Mã **không tin** input là DAG: nếu Kahn không sắp được hết V đỉnh thì ném ngoại lệ.

### 14.2. Chi phí

Tính indegree, topo rồi nới lỏng mỗi cạnh đúng một lần:

- Thời gian **`O(V+E)`**.
- Bộ nhớ phụ **`O(V+E)`** cho adjacency, indegree, queue, topo, dist và parent.

Thật sự cho phép trọng số âm vì **không có chu trình**. Đây là một lý do nên nhận diện cấu trúc đặc biệt của đồ thị trước khi chọn Bellman–Ford chỉ vì thấy weight âm.

## 15. 0-1 BFS: khi trọng số chỉ có 0 và 1

**0-1 BFS** xử lý đồ thị có trọng số mỗi cạnh thuộc `{0,1}` bằng một **deque**:

- Khi `dist[v]` giảm qua cạnh trọng số 0, đưa v vào **đầu deque**.
- Khi `dist[v]` giảm qua cạnh trọng số 1, đưa v vào **cuối deque**.
- Nếu có entry cũ trong deque, bỏ qua khi thấy khoảng cách snapshot khác `dist[v]`.

Đây là trường hợp đặc biệt có thể xem như Dijkstra với cấu trúc queue tối ưu cho hai giá trị trọng số, thay vì dùng heap tổng quát.

### 15.1. Bất biến của deque

Khi lấy một entry có khoảng cách d ở đầu deque:

- Cạnh chi phí 0 tạo ứng viên cũng là d, nên state mới cần được xét sớm.
- Cạnh chi phí 1 tạo ứng viên d+1, nên state mới vào cuối.
- Các giá trị khoảng cách đang chờ được giữ theo các mức liền kề phù hợp cơ chế xử lý.

Mỗi lần cải thiện `dist[v]`, ta **phải có thể xử lý lại v**. Không dùng một `visited[v]=true` vĩnh viễn ngay lúc v được đưa vào queue lần đầu, như BFS trọng số đơn vị.

### 15.2. Phản ví dụ “đã tới rồi không sửa nữa”

Đồ thị:

```text
0→1 (1)
0→2 (0)
2→1 (0)
2→3 (1)
1→3 (1)
```

Nếu duyệt cạnh `0→1 (1)` trước, ban đầu có `dist[1]=1`. Nhưng qua `0→2→1` ta có `0+0=0`, tốt hơn. Một thuật toán khóa đỉnh 1 ở lần gặp đầu sẽ giữ khoảng cách sai.

Kết quả đúng:

`dist[0,1,2,3] = [0,0,0,1]`.

### 15.3. Java 17 — 0-1 BFS với deque và relax thật

Lưu thành **ZeroOneBfsRelaxationDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class ZeroOneBfsRelaxationDemo {
    record Edge(int to, int weight) {}
    record Entry(int vertex, long distance) {}
    record Result(long[] dist, boolean[] reached, int[] parent) {}

    static List<List<Edge>> newGraph(int n) {
        List<List<Edge>> graph = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            graph.add(new ArrayList<>());
        }
        return graph;
    }

    static void add(List<List<Edge>> graph, int u, int v, int weight) {
        if (weight != 0 && weight != 1) {
            throw new IllegalArgumentException("Only 0/1 weights");
        }
        graph.get(u).add(new Edge(v, weight));
    }

    static Result solve(List<List<Edge>> graph, int source) {
        int n = graph.size();
        if (source < 0 || source >= n) {
            throw new IllegalArgumentException("Invalid source");
        }

        long[] dist = new long[n];
        boolean[] reached = new boolean[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        ArrayDeque<Entry> deque = new ArrayDeque<>();
        reached[source] = true;
        deque.addFirst(new Entry(source, 0L));

        while (!deque.isEmpty()) {
            Entry entry = deque.removeFirst();
            int u = entry.vertex();

            if (entry.distance() != dist[u]) {
                continue; // Entry cũ đã bị một cải thiện khác thay thế.
            }

            for (Edge edge : graph.get(u)) {
                int v = edge.to();
                long candidate = Math.addExact(
                        dist[u], (long) edge.weight());

                if (!reached[v] || candidate < dist[v]) {
                    reached[v] = true;
                    dist[v] = candidate;
                    parent[v] = u;

                    Entry next = new Entry(v, candidate);
                    if (edge.weight() == 0) {
                        deque.addFirst(next);
                    } else {
                        deque.addLast(next);
                    }
                }
            }
        }

        return new Result(dist, reached, parent);
    }

    static List<Integer> pathTo(Result r, int target) {
        if (!r.reached()[target]) {
            return List.of();
        }

        List<Integer> path = new ArrayList<>();
        for (int u = target; u != -1; u = r.parent()[u]) {
            path.add(u);
        }
        Collections.reverse(path);
        return path;
    }

    public static void main(String[] args) {
        List<List<Edge>> graph = newGraph(4);
        add(graph, 0, 1, 1);
        add(graph, 0, 2, 0);
        add(graph, 2, 1, 0);
        add(graph, 2, 3, 1);
        add(graph, 1, 3, 1);

        Result result = solve(graph, 0);
        System.out.println("Distances: "
                + Arrays.toString(result.dist()));
        System.out.println("Path to 3: "
                + pathTo(result, 3));

        List<List<Edge>> freeEdge = newGraph(2);
        add(freeEdge, 0, 1, 0);
        System.out.println("Zero-cost edge: "
                + solve(freeEdge, 0).dist()[1]);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ZeroOneBfsRelaxationDemo.java
java ZeroOneBfsRelaxationDemo
```

Stdout:

```text
Distances: [0, 0, 0, 1]
Path to 3: [0, 2, 3]
Zero-cost edge: 0
```

**Chi phí:** với 0-1 BFS chuẩn, `O(V+E)` thời gian trong mô hình thao tác queue hằng số, bộ nhớ `O(V+E)` theo cách lưu các entry snapshot lặp trong deque (trên đồ thị hữu hạn), cùng `O(V)` mảng khoảng cách/parent.

**Không áp dụng trực tiếp** quy tắc đưa đầu/cuối deque khi trọng số có thể là 2, 5 hay số âm. Với trọng số không âm bất kỳ, dùng Dijkstra; với cạnh âm có chu trình, cân nhắc Bellman–Ford; với DAG, topo một lượt.

## 16. So sánh điều kiện duy trì khoảng cách giữa các thuật toán

| Thuật toán | Trọng số được phép | Chính sách chọn trạng thái | Khi nào dist được coi là tối ưu? | Thời gian chuẩn |
|---|---|---|---|---|
| BFS | Mọi cạnh phí 1 | Queue FIFO theo lớp | Khi lần đầu enqueue | `O(V+E)` |
| 0-1 BFS | Chỉ 0/1 | Deque, phí 0 vào đầu | Khi các nới lỏng trước nó được xử lý theo thứ tự khoảng cách; không khóa lúc đầu thấy | `O(V+E)` |
| Dijkstra | Không âm | Min-priority queue | Khi pop tối thiểu và chốt u | `O((V+E)log V)` với heap nhị phân, tùy biểu diễn |
| Bellman–Ford | Có thể âm | Quét toàn bộ cạnh nhiều lượt | Sau tối đa V−1 lượt nếu không có chu trình âm reachable | `O(VE)` |
| DAG shortest path | Có thể âm, đồ thị DAG | Theo thứ tự topo | Khi xử lý đỉnh theo topo | `O(V+E)` |

**Tất cả** cùng sử dụng nguyên tắc ứng viên `dist[u]+w`. Không phải tất cả đều có cùng **quyền chốt dist**. Đây là lý do quan trọng nhất phải chọn thuật toán theo đặc điểm cạnh và cấu trúc đồ thị.

### 16.1. Quy tắc ưu tiên các điều kiện bài

1. **Đồ thị là DAG** và cần single-source shortest paths? Topological DP xử lý cả cạnh âm.
2. **Mọi cạnh giá 1**? BFS đơn giản và nhanh.
3. **Trọng số chỉ 0/1**? 0-1 BFS.
4. **Trọng số không âm tổng quát**? Dijkstra.
5. **Có cạnh âm và có thể có chu trình**? Bellman–Ford hoặc thuật toán được chứng minh phù hợp.
6. **Có chu trình âm tới được**? Khoảng cách hữu hạn không tồn tại cho các đỉnh chịu ảnh hưởng, cần báo/đánh dấu riêng.

Một nhãn thuật toán không thay thế điều kiện chứng minh. Ví dụ dùng Dijkstra “vì đồ thị thưa” nhưng trọng số âm thì vẫn sai.

## 17. Phân biệt điều kiện cập nhật, điều kiện chốt và điều kiện dừng

Ba câu hỏi khác nhau thường bị trộn lẫn:

### 17.1. Điều kiện cập nhật (*relaxation*)

`candidate < dist[v]`.

Nó chỉ phát biểu “vừa tìm được một walk rẻ hơn tới v”. Một giá trị cập nhật vẫn có thể tiếp tục giảm.

### 17.2. Điều kiện chốt (*finalization*)

Dijkstra chốt u khi u được **lấy khỏi min-heap với khóa tốt nhất hiện thời** và mọi cạnh không âm.

BFS không trọng số chốt độ dài ngay lúc **phát hiện** theo từng lớp.

Bellman–Ford **không chốt từng đỉnh theo thứ tự tăng dist**; nó tiếp tục quét cạnh cho tới khi chắc chắn đường ngắn nhất có đủ bước hoặc phát hiện chu trình âm.

DAG duyệt theo topo, nhờ mọi tiền nhiệm đều đã được xử lý trước.

### 17.3. Điều kiện dừng (*termination*)

- BFS có thể dừng khi pop đích nếu chỉ cần khoảng cách từ một nguồn tới một đích.
- Dijkstra có thể dừng khi **chốt đích** nếu chỉ cần một đích, không phải khi đích được enqueue lần đầu.
- Bellman–Ford có thể dừng sớm khi một lượt quét **không có cập nhật**; nếu cần phát hiện chu trình âm reachable, kiểm tra đúng chính sách để không bỏ sót.
- DAG shortest path cần xử lý đúng thứ tự topo (có thể bỏ qua đỉnh chưa tới được).
- Với 0-1 BFS có entry cũ, cần cẩn thận điều kiện dừng và tính chất deque; không dừng chỉ vì **lần đầu thấy đích**.

**Không được lấy “đã có đường tới đích” làm điều kiện kết luận đường ngắn nhất** khi thuật toán còn có thể cải thiện.

## 18. Số học an toàn: INF, tràn số và số thực

### 18.1. Vì sao sentinel `INF` có thể gây lỗi?

Cách thường gặp:

```java
long INF = Long.MAX_VALUE;
long[] dist = new long[n];
Arrays.fill(dist, INF);
dist[source] = 0L;
```

Nếu viết:

```text
candidate = dist[u] + weight
```

mà `dist[u]==INF`, cộng với số dương có thể tràn xuống âm, tạo ứng viên “rất tốt” giả.

**Cách an toàn:** kiểm tra `dist[u]!=INF` trước; dùng `Math.addExact` hoặc kiểm tra chặn trước phép cộng. Các chương trình ở trên dùng **`reachable[]` tách biệt**, tránh nhầm khoảng cách số nguyên hợp lệ với sentinel.

### 18.2. Kể cả hai số hữu hạn vẫn có thể tràn

Nếu `dist[u]=Long.MAX_VALUE−5` và cạnh có trọng số 10, tổng vượt `long`. Java mặc định với số nguyên **tràn vòng**, có thể biến thành số âm lớn, khiến một cạnh dương tạo “đường rẻ nhất” giả.

`Math.addExact` ném `ArithmeticException`; nếu đề đảm bảo tổng nằm trong miền `long`, ngoại lệ không xảy ra. Nếu cần hỗ trợ tổng lớn hơn, thiết kế với `BigInteger` và cân nhắc chi phí bộ nhớ/thời gian.

### 18.3. Trọng số âm

Trọng số âm tự nó **không phải** lỗi số học và Bellman–Ford xử lý được. Nhưng nếu có chu trình âm reachable, giá trị tối ưu không hữu hạn ở những đỉnh bị ảnh hưởng; một số vòng relax có thể tiếp tục giảm cho tới khi kiểu số tràn nếu không dừng theo thuật toán.

### 18.4. Số thực và so sánh

Khi trọng số là `double`, cộng dồn có thể gây sai số:

`candidate < dist[v]`

vẫn có thể dùng trong nhiều ứng dụng nếu thiết kế độ chính xác phù hợp, nhưng không được tùy tiện sửa thành `candidate+epsilon<dist[v]` khi cần chứng minh đường tối ưu tuyệt đối: epsilon có thể **bỏ mất cải thiện thật**.

Nếu đề dùng trọng số nguyên, ưu tiên dùng `long`/`BigInteger` đủ miền để có so sánh chính xác. Nếu dùng `double`, cần chính sách xử lý NaN, ±Infinity và so sánh số thực có chủ đích.

### 18.5. Về trọng số rất lớn và nhiều cạnh

Đường đơn có tối đa `V−1` cạnh. Nếu trọng số mỗi cạnh có độ lớn tối đa B, tổng có thể cần cỡ `O(VB)` về biên trị tuyệt đối. Phải kiểm tra **tổng đường** chứ không chỉ từng weight có vừa `int` hay không.

Dùng `int` cho dist trong đồ thị lớn có thể sai dù từng cạnh chỉ tốn vài triệu. Dùng `long` là một cải thiện nhưng vẫn hữu hạn.

## 19. Truy vết `parent`, nhiều đường hòa và chu trình

### 19.1. Khi nào cập nhật parent?

Với mỗi cập nhật khoảng cách:

```text
if candidate < dist[v]:
    dist[v] = candidate
    parent[v] = u
```

Khoảng cách và parent phải cập nhật **đồng bộ**. Nếu chỉ cập nhật dist nhưng quên parent, đường in ra có thể không đạt đúng giá trị đã báo.

### 19.2. Cách dựng đường sau khi thuật toán kết thúc

Nếu đích t đã tới được và **không bị chu trình âm ảnh hưởng**:

1. Đặt `current=t`.
2. Ghi current vào danh sách.
3. Thay current bằng `parent[current]` cho tới nguồn hoặc sentinel.
4. Đảo danh sách để có nguồn → đích.
5. Kiểm tra mọi cạnh trên đường có thật và tổng trọng số đúng bằng dist[t].

Trong mã demo, nguồn có parent = −1 và đường xây kết thúc ở đó. Trong một thư viện tổng quát, nên có bộ bảo vệ số bước `<=V` và báo lỗi nếu gặp chu trình parent bất thường.

### 19.3. Nhiều đường ngắn nhất

Nếu hai đường đều có tổng bằng 7, strict relaxation `<` chỉ ghi nhận **đường được phát hiện trước** ở cùng độ dài; thuật toán không cần lưu mọi parent.

Nếu đề yêu cầu:

- **Đếm số đường ngắn nhất:** thường phải xử lý các cạnh “tight” và xét chu trình 0, đặc biệt trong đồ thị có trọng số 0.
- **Lấy đường từ điển nhỏ nhất:** cần quy tắc lựa chọn đường rõ ràng, không tự mặc định parent đầu tiên theo thứ tự input là tối ưu từ điển.
- **Liệt kê tất cả đường ngắn nhất đơn giản:** là bài khác, có thể có số lượng nghiệm rất lớn.
- **Đếm số walk ngắn nhất:** có thể vô hạn nếu một chu trình tổng trọng số 0 nằm trên các walk ngắn nhất và được phép lặp.

### 19.4. Multi-source shortest paths

Nếu có tập nguồn `S0`, ta có thể đặt `dist[s]=0` cho **tất cả nguồn** rồi chạy BFS (mọi cạnh 1), Dijkstra (cạnh không âm) hoặc phương pháp phù hợp.

Bất biến khi ấy là: `dist[v]` tương ứng độ dài một đường từ **một nguồn thuộc S0** tới v. Truy vết có thể kết thúc tại **bất kỳ nguồn nào**, không nhất thiết nguồn được liệt kê đầu tiên.

Với Dijkstra, mọi nguồn được đưa vào heap với khóa 0. Với Bellman–Ford, có thể dùng một **siêu nguồn** nối tới từng nguồn bằng cạnh trọng số 0.

## 20. Đồ thị được sinh ngầm và cấu trúc trạng thái

Phép relax không phụ thuộc dữ liệu có được lưu dưới dạng edge list hay sinh trực tiếp.

Ví dụ trong lưới có ô tốn chi phí khi **đi vào**, ta có trạng thái `u=(r,c)` và với mỗi hướng hợp lệ sinh `v=(nr,nc)`, trọng số cạnh `w(u,v)=cost[nr][nc]`. Sau đó áp:

`candidate=dist[r][c]+cost[nr][nc]`.

Nhưng nếu ô có chìa khóa, hướng quay hoặc thời gian chẵn/lẻ quyết định chuyển tiếp hợp lệ, trạng thái cần bao gồm chúng, ví dụ `(r,c,mask)` hoặc `(r,c,parity)`. Dùng `dist[r][c]` cho hai trạng thái có lựa chọn tương lai khác nhau có thể **gộp nhầm đỉnh** và làm sai đường tối ưu.

Với lưới R×C và k chìa khóa, trạng thái `(r,c,mask)` có thể có tới `R*C*2^k` cấu hình. Bài có cạnh sinh ngầm không có nghĩa số trạng thái nhỏ.

## 21. Các sai lầm thường gặp

### Lỗi 1 — Nới lỏng từ INF

Cộng `INF + weight` có thể tràn hoặc tạo ứng viên giả. **Sửa:** kiểm tra khả năng tới được trước khi cộng.

### Lỗi 2 — Dùng dấu `>` ngược hướng

Bài đường đi ngắn nhất cập nhật khi `candidate < dist[v]`, không phải `candidate > dist[v]` (đó là dạng tối đa hóa, ví dụ longest path trên DAG).

### Lỗi 3 — Không cập nhật parent theo dist

Nếu dist của v cải thiện qua u, `parent[v]` cũng cần thành u nếu muốn khôi phục đường tương ứng.

### Lỗi 4 — Dùng `<=` và tạo chu trình parent ở cạnh 0

Nếu cứ đổi parent khi hòa, hai đỉnh với các cạnh phí 0 có thể trở thành cha của nhau. **Sửa:** strict `<` khi chỉ cần một đường.

### Lỗi 5 — Xem giá trị đầu tiên là tối ưu

Dijkstra không chốt khi enqueue; Bellman–Ford có thể giảm một đỉnh sau nhiều lượt. Đừng dừng ở lần đầu tìm được đích nếu chính sách thuật toán chưa đảm bảo tối ưu.

### Lỗi 6 — Dùng BFS cho trọng số khác nhau

BFS tìm ít cạnh nhất, không nhất thiết min tổng trọng số. **Sửa:** xác định loại weight trước.

### Lỗi 7 — Dùng Dijkstra cho cạnh âm

Không âm là điều kiện thiết yếu cho lập luận chốt đỉnh. Với cạnh âm có thể phải dùng Bellman–Ford hoặc topo nếu DAG.

### Lỗi 8 — Nhầm cạnh âm với chu trình âm

Một cạnh âm không đủ chứng minh không có đường ngắn nhất. Điều kiện phá tối ưu hữu hạn là **chu trình âm reachable có thể dẫn tới đỉnh đang xét**.

### Lỗi 9 — Phát hiện chu trình âm không tới được rồi kết luận sai

Một chu trình âm ở thành phần không thể tới từ nguồn không ảnh hưởng shortest paths từ nguồn. Bellman–Ford phải kiểm tra cạnh chỉ từ u đã tới được.

### Lỗi 10 — Bellman–Ford chỉ quét cạnh một lần

Cải thiện có thể cần lan truyền ngược theo thứ tự cạnh, phải lặp tới `V−1` lượt hoặc dừng khi không còn cập nhật.

### Lỗi 11 — Bỏ qua lượt kiểm tra chu trình âm

Sau `V−1` lượt, nếu còn cạnh có thể relax, có thể tồn tại chu trình âm reachable. Nếu đề yêu cầu phát hiện, cần lượt kiểm tra này.

### Lỗi 12 — Sai thứ tự topo

Không duyệt đỉnh theo ID tăng nếu ID không phải topo. Dùng Kahn/DFS topo, xác nhận đồ thị không có chu trình.

### Lỗi 13 — 0-1 BFS khóa visited khi enqueue lần đầu

Một cạnh phí 0 có thể cải thiện đỉnh đã phát hiện trước với phí 1. Cần nới lỏng khi có ứng viên nhỏ hơn.

### Lỗi 14 — Cho phép trọng số 2 ở 0-1 BFS

Deque quy tắc đầu/cuối chỉ được chứng minh cho weight 0 hoặc 1. Với trọng số bất kỳ không âm, Dijkstra tổng quát phù hợp hơn.

### Lỗi 15 — Không bỏ entry cũ trong heap/deque

Nếu một đỉnh có nhiều entry với dist khác nhau, mở rộng cả entry đã lỗi thời gây thừa việc; và nếu chốt sai, có thể phá tính đúng. Kiểm tra khóa entry với `dist[vertex]`.

### Lỗi 16 — Tràn khi cộng trọng số

`long` vẫn có thể tràn. Dùng `Math.addExact` hoặc kiểm tra phạm vi, với input lớn có thể dùng số nguyên độ chính xác tùy ý.

### Lỗi 17 — Dùng giá trị 0 để biểu diễn chưa tới

Trọng số bằng 0 và đường có tổng 0 hoàn toàn hợp lệ. Dùng `reachable[]` hoặc sentinel riêng đã được xử lý đúng.

### Lỗi 18 — Quên cạnh ngược cho đồ thị vô hướng

Nếu bài định nghĩa đường hai chiều nhưng bạn chỉ thêm `u→v`, kết quả có thể báo vô nghiệm chiều ngược. Thêm cả hai hướng khi mô hình thực sự vô hướng.

### Lỗi 19 — Gộp nhầm trạng thái khác nhau

Đường tới cùng tọa độ nhưng tập chìa khóa khác nhau có thể có tương lai khác. Dùng state đầy đủ để đánh dấu và lưu dist.

### Lỗi 20 — Không kiểm tra parent cuối

Nếu parent không trỏ về nguồn hoặc tổng weight của parent path không khớp dist, có lỗi đồng bộ trạng thái, đặc biệt khi có cạnh âm/chu trình.

### Lỗi 21 — Đánh đồng “không relax được” với “đã chạy đúng”

Điều kiện hội tụ chỉ là chứng chỉ mạnh nếu dist có nhân chứng hợp lệ, nguồn đặt 0 và không có chu trình âm reachable. Một mảng dist ngẫu nhiên thỏa vài bất đẳng thức chưa là lời giải đúng.

### Lỗi 22 — Đo độ phức tạp chỉ theo số đỉnh

BFS/Dijkstra/Bellman–Ford còn phụ thuộc số cạnh, cấu trúc adjacency và số lần relax. Với đồ thị sinh ngầm, tính cả chi phí **sinh neighbors**.

## 22. Kiểm thử và oracle độc lập

### 22.1. Các điều kiện QA cho một kết quả shortest-path

Với mỗi v có `reachable[v]=true` và kết quả xác định:

1. Có một walk hợp lệ từ s tới v có tổng bằng dist[v].
2. Nếu dùng parent, chuỗi parent phải về tới nguồn và mọi cạnh nằm trong đồ thị.
3. Tổng trọng số trên parent path phải bằng dist[v].
4. Với mọi cạnh `u→v` reachable và không có chu trình âm ảnh hưởng, bất đẳng thức:

   `dist[v] <= dist[u] + w(u,v)`

   phải thỏa.
5. Đỉnh unreachable phải được báo đúng, không dùng dist mặc định 0 làm kết quả.
6. Khi thuật toán tuyên bố “hoàn tất”, cần đúng điều kiện trọng số/cấu trúc mà thuật toán yêu cầu.

Nếu chỉ kiểm tra `dist` mà không kiểm tra parent, có thể bỏ sót lỗi truy vết. Nếu chỉ kiểm tra parent mà không kiểm tra optimum, có thể in một đường hợp lệ nhưng chưa ngắn nhất.

### 22.2. So sánh thuật toán trên miền giao nhau

- Trọng số **toàn không âm**: đối chiếu Dijkstra với Bellman–Ford; nếu đều có đường đi, khoảng cách phải bằng nhau.
- Trọng số **chỉ 0/1**: đối chiếu 0-1 BFS với Dijkstra.
- DAG có trọng số **âm hoặc dương**: đối chiếu topo shortest path với Bellman–Ford.
- Mọi cạnh **giá 1**: đối chiếu BFS với Dijkstra/Bellman–Ford.
- Đồ thị rất nhỏ: có thể xây ma trận và dùng **Floyd–Warshall** làm oracle tất cả cặp; cần kiểm tra chu trình âm nếu có.

### 22.3. Test biên có giá trị phân loại lỗi

| Trường hợp | Kỳ vọng |
|---|---|
| Một đỉnh, không cạnh, nguồn chính nó | dist[source]=0 |
| Một đỉnh khác hoàn toàn không tới được | `INF` hoặc trạng thái unreachable |
| Cạnh phí 0 từ nguồn | Đỉnh đích có thể có dist 0 |
| Hai đường cùng phí | Cùng optimum; parent có thể tùy thứ tự duyệt |
| Cạnh âm, đồ thị DAG | Topo/Bellman–Ford đúng; Dijkstra không được dùng không điều kiện |
| Chu trình âm tới được | Bellman–Ford báo chu trình |
| Chu trình âm không tới được | Không làm hỏng shortest paths từ nguồn |
| Thứ tự cạnh Bellman–Ford bị đảo | Cần nhiều lượt; kết quả cuối không đổi |
| Một cạnh tạo ứng viên lớn hơn | Không cập nhật dist/parent |
| Một cạnh tạo ứng viên bằng | Với strict `<`, không đổi parent |
| Nhiều cập nhật tới cùng đỉnh | Chỉ lưu ứng viên tốt nhất |
| Tích lũy vượt miền `long` | Phải xử lý/trả lỗi, không chấp nhận wraparound |
| Đồ thị vô hướng | Mô hình đúng hai cạnh hướng mỗi cạnh vô hướng |
| Đồ thị trạng thái có chìa khóa | Dist/visited theo state đầy đủ |
| Đồ thị có trọng số 0/1 | 0-1 BFS hoặc Dijkstra đúng |
| Đồ thị có trọng số 2 | Không dùng 0-1 BFS nguyên xi |

### 22.4. Kiểm tra hội tụ trực tiếp

Sau Bellman–Ford thành công, duyệt mọi cạnh reachable và xác nhận không còn cạnh cải thiện. Nếu còn, đó có thể là chu trình âm reachable hoặc một lỗi cài đặt/quá ít lượt.

Sau Dijkstra thành công với trọng số không âm, cũng có thể kiểm điều kiện tam giác trên toàn bộ các cạnh reachable.

Khi thử input ngẫu nhiên nhỏ, hãy so **từng đỉnh**, không chỉ một đích mẫu. Có thể tạo graph với một đỉnh hoàn toàn rời để kiểm tra sentinel.

## 23. Bài tập tự luyện kèm đáp án

### Bài 1 — Relax đơn giản

`dist[u]=7`, cạnh `u→v` trọng số 4, `dist[v]=15`. Có cập nhật không?

**Đáp án:** có. Ứng viên `7+4=11 <15`, nên `dist[v]=11` và `parent[v]=u`.

### Bài 2 — Không cập nhật khi bằng

`dist[u]=3`, `w(u,v)=5`, `dist[v]=8`. Với phép relax strict `<`, có đổi parent[v] không?

**Đáp án:** không. Ứng viên 8 bằng dist[v], đường hiện tại đã đạt cùng giá trị.

### Bài 3 — Đỉnh chưa tới được

`reachable[u]=false`, dù cạnh `u→v` trọng số `−1000`, có được dùng nó để giảm dist[v] không?

**Đáp án:** không. Chưa có đường từ nguồn tới u, nên không có walk hợp lệ nguồn→u→v để làm chứng.

### Bài 4 — Khoảng cách tạm thời có thể lớn hơn thật

Từ s tới A có cạnh trực tiếp 10 và đường s→B→A có phí `3+4=7`. Sau khi mới xét cạnh trực tiếp, dist[A] là bao nhiêu? Sau khi xét đủ đường qua B?

**Đáp án:** đầu tiên 10, sau đó giảm thành 7.

### Bài 5 — Bất đẳng thức tam giác

Nếu các dist đã tối ưu, có cạnh `u→v` trọng số 6, `δ(s,u)=4`, thì `δ(s,v)` bị chặn trên bởi số nào qua cạnh đó?

**Đáp án:** `δ(s,v) <= 4+6=10`. Có thể có đường khác còn ngắn hơn.

### Bài 6 — Phản ví dụ Dijkstra

`S→A=2`, `S→B=5`, `B→A=−10`. Đường ngắn nhất tới A là bao nhiêu?

**Đáp án:** `−5` qua S→B→A, không phải 2. Dijkstra không được dùng cho trọng số âm tổng quát.

### Bài 7 — Bellman–Ford số lượt

Đồ thị có V đỉnh, không có chu trình âm reachable. Cần tối đa bao nhiêu lượt quét E cạnh để có các dist đúng?

**Đáp án:** `V−1` lượt, cộng một lượt kiểm chu trình âm nếu bài cần phát hiện.

### Bài 8 — Chu trình âm

Có chu trình reachable `1→2` trọng số −3, `2→1` trọng số 1. Tổng chu trình?

**Đáp án:** `−3+1=−2`. Có thể lặp để giảm không giới hạn tổng phí tới các đỉnh đi được sau chu trình; cần phát hiện ảnh hưởng.

### Bài 9 — Chu trình âm không reachable

Nguồn s nằm trong thành phần khác; một chu trình âm tồn tại nhưng s không tới được chu trình. Bellman–Ford từ s có cần báo chu trình âm reachable không?

**Đáp án:** không. Chu trình không ảnh hưởng khoảng cách từ s.

### Bài 10 — DAG có cạnh âm

DAG có cạnh âm và không có chu trình. Có thể dùng thuật toán nào chạy `O(V+E)`?

**Đáp án:** xử lý đỉnh theo thứ tự topo, nới lỏng các cạnh đi ra một lần.

### Bài 11 — 0-1 BFS

Khi nới lỏng thành công cạnh trọng số 0 trong 0-1 BFS, đưa đỉnh vào đâu?

**Đáp án:** vào **đầu deque**. Cạnh trọng số 1 thì vào cuối.

### Bài 12 — BFS và số cạnh

Mọi cạnh trọng số 1, một đường từ nguồn tới v gồm 5 cạnh. `dist[v]` tính theo BFS bằng bao nhiêu nếu đó là đường ngắn nhất?

**Đáp án:** 5, không phải 6 (6 là số đỉnh của đường).

### Bài 13 — Entry heap lỗi thời

Dijkstra đã từng enqueue `(A,10)` rồi cải thiện `dist[A]=7` và enqueue `(A,7)`. Khi pop entry `(A,10)` nên làm gì?

**Đáp án:** bỏ qua vì khóa entry 10 khác `dist[A]=7`; không chốt hoặc nới lỏng dựa trên entry cũ.

### Bài 14 — Truy vết

Nếu `parent[4]=3`, `parent[3]=1`, `parent[1]=2`, `parent[2]=0`, `parent[0]=-1`, đường từ 0 tới 4 là gì?

**Đáp án:** `[0,2,1,3,4]` sau khi đi ngược parent từ 4 và đảo.

### Bài 15 — Cộng tràn

`dist[u]=Long.MAX_VALUE−3`, `w=10`. Nếu dùng phép cộng `long` thường, có thể gặp gì?

**Đáp án:** tràn xuống số âm, gây cập nhật sai. Dùng `Math.addExact`, kiểm tra biên hoặc `BigInteger`.

### Bài 16 — Dừng sớm

Dijkstra đã **enqueue** đích ở dist 20, queue vẫn còn các đỉnh khác. Có chắc dist đích tối ưu chưa?

**Đáp án:** chưa. Chỉ khi đích được **pop và chốt** theo quy tắc min-heap với trọng số không âm, ta mới có bảo đảm.

### Bài 17 — Mảng dist và mask

Trong lưới có cửa cần chìa khóa, hai lần đến cùng ô với hai tập chìa khác nhau có gộp vào một dist[r][c] không?

**Đáp án:** không nói chung. State cần `(r,c,mask)` vì các chuyển tiếp tương lai khác nhau.

### Bài 18 — Đếm nhiều đường ngắn nhất

Đồ thị có chu trình trọng số 0 trên một đường đạt optimum. Có thể có bao nhiêu **walk** cùng chi phí ngắn nhất?

**Đáp án:** có thể **vô hạn** nếu được lặp chu trình 0 tùy nhiều lần. Đếm đường đơn là bài khác và cần mô hình rõ.

### Bài 19 — Kiểm chứng hội tụ

Sau một thuật toán, tìm thấy cạnh `u→v` có `dist[u]=8`, `w=−2`, `dist[v]=9` và u reachable. Hệ dist hiện tại đã tối ưu chưa?

**Đáp án:** chưa, vì ứng viên `8−2=6 <9`, cạnh còn nới lỏng được.

### Bài 20 — Nhiều nguồn

Nếu có ba nguồn đều khởi tạo dist 0, dist[v] đang biểu diễn điều gì?

**Đáp án:** khoảng cách ngắn nhất **từ một trong ba nguồn** tới v (với thuật toán/trọng số thích hợp), tương đương nguồn ảo nối tới ba nguồn bằng cạnh phí 0.

## 24. Checklist trước khi nộp giải thuật đường đi ngắn nhất

1. **Đỉnh và cạnh được định nghĩa đúng?** Có hướng/vô hướng, một chiều/hai chiều?
2. **Trọng số thuộc loại nào?** Tất cả 1, 0/1, không âm, âm, hay DAG?
3. **Có chu trình âm reachable không?** Nếu có, đỉnh chịu ảnh hưởng không có shortest distance hữu hạn.
4. **`dist[source]` đã khởi tạo 0?** Các đỉnh khác là unreachable/INF?
5. **Mọi relax đều kiểm tra `reachable[u]` trước khi cộng?**
6. **Điều kiện cập nhật là strict `<` khi chỉ cần một đường?**
7. **Khi dist cải thiện, parent có cập nhật cùng?**
8. **Phép cộng `dist[u]+w` có bảo vệ tràn số?**
9. **Đã chọn thuật toán theo loại cạnh?** BFS, 0-1 BFS, Dijkstra, Bellman–Ford hay DAG?
10. **Với Dijkstra, chỉ chốt khi pop min hợp lệ?** Không chốt khi enqueue.
11. **Với Dijkstra, đã bỏ entry heap cũ?**
12. **Với Bellman–Ford, quét đủ tối đa V−1 lượt?**
13. **Nếu cần phát hiện negative cycle, đã kiểm tra extra pass từ đỉnh reachable?**
14. **Với DAG, thứ tự topo có thực sự hợp lệ và kiểm tra chu trình?**
15. **Với 0-1 BFS, relax có thể cập nhật lại một đỉnh?** Cạnh 0 vào đầu, 1 vào cuối?
16. **Nếu dùng `visited`, nó có đúng nghĩa cho thuật toán không?** Không khóa quá sớm với cạnh không đồng trọng số.
17. **Mọi đường truy vết có thật, tổng weight bằng dist, và kết thúc ở nguồn?**
18. **Đỉnh unreachable được báo rõ, không nhầm với khoảng cách 0?**
19. **Nếu có nhiều nguồn hoặc state mở rộng, mọi dist/visited có chỉ số đủ thông tin?**
20. **Đã thử phản ví dụ cạnh âm, trọng số 0, equal paths, queue stale, unreachable và overflow?**
21. **Sau khi hoàn tất không có cạnh reachable nào còn relax được nếu không có chu trình âm?**
22. **Đã đối chiếu với một oracle độc lập trên đồ thị nhỏ?** Dijkstra so Bellman–Ford/Floyd–Warshall; 0-1 BFS so Dijkstra; DAG so Bellman–Ford.
23. **Có đo đúng chi phí V/E, heap/deque và sinh hàng xóm ngầm không?**
24. **Đề có yêu cầu đường từ điển nhỏ nhất hoặc tất cả đường cùng tối ưu không?** Khi ấy strict parent và tie-break mặc định có thể chưa đủ.

**Ghi nhớ:** phép nới lỏng cạnh `u→v` đề xuất một đường mới tới v bằng `dist[u]+w`; chỉ cập nhật khi v chưa tới được hoặc ứng viên **nhỏ hơn** dist[v]. Mỗi cập nhật phải có **walk hợp lệ làm chứng**, nên dist hữu hạn là một **cận trên cho khoảng cách thật**, không phải một ước đoán tùy ý. Khi không còn cạnh cải thiện và không có chu trình âm tới được, các bất đẳng thức tam giác cùng bất biến nhân chứng chứng minh khoảng cách đã đúng. Sự khác nhau giữa BFS, Dijkstra, Bellman–Ford, DAG shortest path và 0-1 BFS nằm ở **lịch xử lý các cạnh** và **thời điểm được phép chốt khoảng cách**.

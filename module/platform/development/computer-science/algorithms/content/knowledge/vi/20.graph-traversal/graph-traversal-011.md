# Phát hiện chu trình trong đồ thị có hướng

**Chu trình có hướng** (*directed cycle*) là một đường đi theo đúng chiều các cạnh, kết thúc ở chính đỉnh xuất phát. Phát hiện chu trình giúp kiểm tra hệ thống công việc phụ thuộc nhau, thứ tự học môn tiên quyết, các bước build/phân tích chương trình và điều kiện tồn tại của **sắp xếp topo**.

Có hai kỹ thuật cơ bản, đều chạy **O(V+E)** khi dùng danh sách kề:

- **DFS ba màu (WHITE, GRAY, BLACK):** cạnh đi tới đỉnh GRAY đang nằm trong stack DFS chứng minh có chu trình. Với mảng parent, có thể **dựng một chu trình cụ thể**.
- **Kahn (loại đỉnh có indegree bằng 0):** nếu không lấy ra được đủ V đỉnh thì đồ thị có chu trình; ngược lại thứ tự lấy ra là một **thứ tự topo**.

Bài học thuộc nhóm **Duyệt đồ thị**. Nội dung giải thích điều kiện đúng, bất biến, phương pháp dựng chứng cứ, đồ thị không liên thông, self-loop, cạnh song song, chứng minh, chương trình Java 17 độc lập, kiểm thử vét cạn và lỗi thực hành.

## 1. Định nghĩa và phân biệt với đồ thị vô hướng

Đồ thị có hướng \(G=(V,E)\) có các cạnh \(u\to v\). Cạnh này chỉ cho phép đi từ u sang v, **không tự động** cho phép đi từ v về u.

Một **chu trình có hướng đơn** gồm các cạnh:

\[
v_0\to v_1\to\cdots\to v_{k-1}\to v_0,\quad k\ge1,
\]

trong đó các đỉnh \(v_0,\ldots,v_{k-1}\) khác nhau. Khi in chu trình, ta lặp đỉnh đầu ở cuối để biểu diễn cạnh đóng vòng: `[v0, v1, ..., v0]`.

Ví dụ:

~~~text
0 → 1 → 2
↑       |
└───────┘

Đường có hướng khép kín: 0→1→2→0
Danh sách chứng cứ: [0, 1, 2, 0]
~~~

Các trường hợp cần nhớ:

| Đồ thị | Chu trình? | Giải thích |
| --- | --- | --- |
| Một đỉnh 0, không cạnh | Không | Không có cạnh để đi |
| Chỉ `0→1` | Không | Không có đường quay về 0 |
| `0→1, 1→0` | Có | Chu trình hai cạnh [0,1,0] |
| `0→0` | Có | Self-loop là chu trình một cạnh [0,0] |
| Hai cạnh `0→1` cùng chiều | Không | Cạnh song song không tạo đường quay lại |
| `0→1, 1→2, 2→0` | Có | Chu trình dài ba cạnh |
| `0→1,0→2,1→3,2→3` | Không | Hai nhánh hội tụ tại 3 vẫn là DAG |

**Self-loop** là một chu trình hợp lệ. Hai cạnh song song **cùng chiều** chỉ tăng số cạnh, không tự tạo chu trình. Nếu hai đỉnh có cạnh **hai chiều**, đó là chu trình hai cạnh.

### DAG và sắp xếp topo

Đồ thị có hướng **không có chu trình** được gọi là DAG (*Directed Acyclic Graph*). Một thứ tự topo là một danh sách chứa **mỗi đỉnh đúng một lần**, sao cho với mọi cạnh \(u\to v\), u xuất hiện **trước** v.

Tính chất nền tảng:

\[
\boxed{\text{Đồ thị có hướng hữu hạn là DAG}
\iff \text{tồn tại thứ tự topo đầy đủ}.}
\]

Nếu có chu trình \(v_0\to v_1\to\cdots\to v_0\), các điều kiện thứ tự đòi \(v_0\) trước \(v_1\), ... và cuối cùng trước chính \(v_0\), điều bất khả thi.

**Đồ thị không cần liên thông.** Một thành phần có thể không có vòng, thành phần khác lại có chu trình. Muốn kết luận cho toàn đồ thị, phải duyệt mọi đỉnh, không chỉ các đỉnh tới được từ 0.

## 2. Biểu diễn dữ liệu và hướng cạnh

Với n đỉnh đánh số `0..n-1`, danh sách kề:

~~~text
adj[u] = các đỉnh v sao cho có cạnh u→v
~~~

Ví dụ DAG hình thoi:

~~~text
0 → 1 → 3
 \      ↑
  → 2 ─┘

adj[0] = [1,2]
adj[1] = [3]
adj[2] = [3]
adj[3] = []
~~~

Nếu có n đỉnh, m cạnh, xây danh sách kề cần **O(n+m)** thời gian và bộ nhớ. Một cạnh `u→v` chỉ được thêm vào `adj[u]`, **không thêm vào adj[v]** trừ khi dữ liệu thực sự có cạnh ngược.

**Bậc vào** `indegree[v]` là **số cạnh đi vào v**, không phải số đỉnh nguồn phân biệt. Hai cạnh song song `0→1` làm `indegree[1]=2`. Kahn phải trừ cả hai lần khi xử lý 0.

Chương trình minh họa chấp nhận self-loop và cạnh song song, nhưng yêu cầu n không âm, mỗi cạnh có hai đầu mút hợp lệ trong `0..n-1`, và không sửa danh sách kề giữa chừng.

## 3. Tại sao chỉ có visited boolean là chưa đủ?

Một cách làm sai thường thấy: “trong DFS, gặp cạnh tới **bất kỳ đỉnh đã visited** nào là có chu trình”.

Phản ví dụ chính là DAG hình thoi:

~~~text
0→1→3
↓   ↑
2───┘
~~~

Giả sử DFS từ 0 đi qua 1 rồi 3 và hoàn tất nhánh này. Sau đó DFS quay về 0, đi qua 2 và gặp cạnh `2→3`. Đỉnh 3 đã được thăm, nhưng **không còn nằm trên nhánh đang xét**; cạnh này không tạo vòng.

Cần phân biệt **đang duyệt** với **đã duyệt xong**. DFS ba màu biểu diễn bằng:

| Màu | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| **WHITE** | 0 | Chưa bắt đầu duyệt |
| **GRAY** | 1 | Đang nằm trên ngăn xếp lời gọi DFS |
| **BLACK** | 2 | Đã duyệt xong tất cả cạnh đi ra |

Khi `dfs(u)` bắt đầu, đặt `color[u]=GRAY`. Sau khi thăm hết cạnh đi ra mà không phát hiện vòng, đặt `color[u]=BLACK`.

Khi xét cạnh **u→v**:
- **WHITE:** v chưa thăm, gán `parent[v]=u` rồi đệ quy vào v.
- **GRAY:** v là một **tổ tiên đang hoạt động** của u trong cây DFS; cạnh này là **back edge**, chứng minh có chu trình.
- **BLACK:** v đã hoàn tất; cạnh này **không phải chứng cứ chu trình**, tiếp tục duyệt.

Nếu không muốn dùng màu, có thể dùng hai mảng `visited[]` và `onStack[]`. Chỉ `onStack[v]==true` tương ứng với gặp GRAY, không phải `visited[v]==true` nói chung.

### Bất biến GRAY

Trong một lời gọi DFS đệ quy, những đỉnh còn GRAY tạo thành chuỗi các đỉnh **tổ tiên đến đỉnh hiện tại** theo các cạnh cây. Nếu gặp cạnh \(u\to v\) mà v GRAY, đã có đường theo các cạnh cây:

\[
v\to\cdots\to u.
\]

Thêm cạnh \(u\to v\) khép thành chu trình. Đỉnh BLACK có thể từng nằm trên đường DFS nhưng đã kết thúc; nó không còn là tổ tiên hoạt động.

### Duyệt đủ các thành phần

Phải có vòng ngoài:

~~~text
for start = 0 .. n-1:
    if color[start] == WHITE:
        dfs(start)
~~~

Nếu chỉ gọi `dfs(0)`, chu trình ở một thành phần tách biệt có thể bị bỏ sót. Mỗi đỉnh chuyển từ WHITE sang GRAY một lần nên tổng thời gian vẫn tuyến tính theo đỉnh và cạnh.

## 4. Dựng một chu trình khi gặp cạnh tới GRAY

Một bài chỉ hỏi true/false có thể dừng ngay khi phát hiện back edge. Nếu cần **in một chu trình** làm chứng cứ, hãy lưu mảng **parent**.

Giả sử đang ở u và gặp cạnh `u→v` với v GRAY. Vì v là tổ tiên của u, mảng parent ghi đường theo các cạnh cây từ v xuống u. Làm như sau:

1. Bắt đầu `x=u`, thêm x vào danh sách `reversed`.
2. Khi `x!=v`, đặt `x=parent[x]`, tiếp tục thêm x. Danh sách thu được là `[u,...,v]`, đi ngược chiều các cạnh cây.
3. **Đảo** danh sách thành `[v,...,u]`.
4. Thêm v lần nữa ở cuối. Danh sách cuối `[v,...,u,v]` là chu trình theo **chiều cạnh thực tế**.

Ví dụ:

~~~text
0 → 1 → 2 → 0
        |
        ↓
        3
~~~

Khi duyệt từ 0: `parent[1]=0`, `parent[2]=1`; tới 2 thì gặp cạnh tới 0 GRAY.

~~~text
u=2, v=0
Chuỗi parent ngược: [2,1,0]
Đảo:               [0,1,2]
Đóng vòng:          [0,1,2,0]
~~~

Đỉnh 3 có thể nằm trong đồ thị nhưng **không thuộc chu trình** này.

Với cạnh tự khép `u→u`, danh sách ngược chỉ chứa `[u]`, sau khi thêm v=u thành `[u,u]`.

**Không dùng parent chain cho cạnh tới BLACK.** Khi v BLACK, nó không còn chắc là tổ tiên; lần theo parent từ u có thể không gặp v hoặc cho đường sai chiều.

### Giả mã DFS ba màu

~~~text
color[] = WHITE; parent[] = -1

visit(u):
    color[u] = GRAY
    for v in adj[u]:
        if color[v] == WHITE:
            parent[v] = u
            if visit(v) found a cycle: return true
        else if color[v] == GRAY:
            reconstruct [v,...,u,v] using parent
            return true
    color[u] = BLACK
    return false

for start in 0 .. n-1:
    if color[start] == WHITE and visit(start):
        return reconstructed cycle

return no cycle
~~~

Khi tìm thấy vòng, có thể return ngay mà không chuyển tất cả những đỉnh còn GRAY về BLACK, vì bài toán đã kết thúc. Nếu muốn dùng màu để tiếp tục xử lý sau khi tìm được vòng, phải thiết kế lại cách dọn trạng thái.

### Độ phức tạp

Với danh sách kề, mỗi đỉnh được bắt đầu duyệt tối đa một lần, mỗi cạnh xét tối đa một lần:

\[
\boxed{O(V+E)\ \text{thời gian};\quad O(V)\ \text{bộ nhớ phụ}.}
\]

Bộ nhớ phụ gồm màu, parent, stack đệ quy và chu trình trả về. Đồ thị lưu bằng danh sách kề chiếm O(V+E) riêng.

**Giới hạn đệ quy Java:** trên một đường rất dài, DFS đệ quy có thể gây `StackOverflowError`. Có thể chuyển sang **stack tường minh** gồm khung `(đỉnh, chỉ số cạnh tiếp theo)`, giữ GRAY cho tới khi khung kết thúc và chỉ sau đó đổi BLACK. Đừng đánh BLACK ngay khi vừa đưa đỉnh lên stack.

## 5. Kahn: loại đỉnh bậc vào 0 và kiểm tra topo

Một cách phát hiện chu trình **khác với DFS** là thuật toán Kahn:

1. Tính `indegree[v]` cho mọi v bằng cách duyệt toàn bộ cạnh u→v.
2. Đưa tất cả đỉnh có `indegree==0` vào hàng đợi.
3. Lấy u ra, ghi vào `order`.
4. Với **mỗi cạnh** u→v, giảm `indegree[v]`. Nếu vừa về 0, đưa v vào queue.
5. Lặp đến khi queue rỗng; kiểm tra số đỉnh đã lấy.

Kết luận:

\[
\boxed{\text{hasCycle}=(|order|<V).}
\]

Nếu `order.size()==V`, đây là DAG và `order` là một thứ tự topo đầy đủ.

### Mô phỏng DAG hình thoi

Với `0→1,0→2,1→3,2→3`:

~~~text
indegree = [0,1,1,2]
queue ban đầu = [0]

Lấy 0: order=[0], các đỉnh 1,2 về indegree 0
Lấy 1: order=[0,1], indegree[3] từ 2 xuống 1
Lấy 2: order=[0,1,2], indegree[3] từ 1 xuống 0
Lấy 3: order=[0,1,2,3]
~~~

Lấy đủ bốn đỉnh, nên không có chu trình; `[0,1,2,3]` là một topo hợp lệ. Có thể tồn tại nhiều thứ tự topo khác, chẳng hạn hoán đổi 1 và 2.

### Mô phỏng có chu trình

Với `0→1,1→2,2→0,2→3`:

~~~text
indegree = [1,1,1,1]
queue ban đầu = []
order = []
~~~

Không lấy được đỉnh nào: chỉ **0/4 đỉnh** được xóa. Chu trình là `0→1→2→0`, nhưng đỉnh 3 cũng còn lại vì phụ thuộc vào 2.

**Không kết luận mọi đỉnh còn lại sau Kahn đều nằm trên chu trình.** Một đỉnh không thuộc vòng nhưng có đường đến từ vòng có thể vẫn có indegree dương và không bị lấy ra.

Cũng không đúng khi nói “cứ có vòng thì queue ban đầu rỗng”. Với `0→1,1→2,2→1`, Kahn vẫn lấy đỉnh 0 trước rồi mới kẹt ở vòng 1↔2, tức lấy **1/3 đỉnh**.

### Xử lý cạnh song song

Nếu có hai cạnh `0→1` cùng chiều, `indegree[1]=2`. Khi lấy 0, duyệt cả hai phần tử `adj[0]=[1,1]`, trừ hai lần, rồi đưa 1 vào queue **đúng một lần** khi indegree đi từ 1 xuống 0. Đồ thị này **không có chu trình**.

Nếu đếm indegree bằng số cạnh nhưng lại khử trùng các cạnh lúc giảm, có thể báo chu trình sai. Phải giữ một cách tính nhất quán theo đúng số cạnh.

### Độ phức tạp Kahn

Tính indegree O(V+E). Mỗi đỉnh được thêm/xóa khỏi queue tối đa một lần, mỗi cạnh được dùng để giảm indegree một lần, nên **O(V+E)** thời gian, O(V) bộ nhớ phụ cho indegree, queue, order.

**Chọn Kahn khi** cần thứ tự thực hiện công việc/topo nếu không có chu trình, hoặc muốn tránh stack đệ quy. **Chọn DFS ba màu khi** cần in ra chính một vòng phụ thuộc để người dùng biết phải sửa những cạnh nào.

## 6. Chứng minh tính đúng của hai cách

### DFS: gặp GRAY thì thật sự có chu trình

Nếu DFS thấy cạnh \(u\to v\) tới một đỉnh GRAY, v đang là tổ tiên hoạt động của u. Các cạnh cây dẫn từ v xuống u cùng chiều. Kết hợp cạnh u→v tạo đường khép kín có hướng, nên báo chu trình là đúng.

Ngược lại, nếu đồ thị chứa một chu trình có hướng, trong lần DFS thăm các đỉnh thuộc chu trình sẽ có một cạnh trở về đỉnh vẫn đang GRAY; đây là tính chất chuẩn **đồ thị có hướng không có back edge trong DFS khi và chỉ khi nó là DAG**. Vòng ngoài duyệt mọi đỉnh chưa thăm nên không bỏ sót thành phần nào.

### Kahn: DAG luôn có đỉnh bậc vào 0

Một DAG hữu hạn không rỗng luôn tồn tại đỉnh indegree 0. Nếu mọi đỉnh đều có cạnh đi vào, ta có thể đi ngược theo một cạnh đi vào liên tục; vì tập đỉnh hữu hạn, sẽ lặp một đỉnh và tạo chu trình, mâu thuẫn DAG. Loại một đỉnh indegree 0 khỏi DAG cùng các cạnh đi ra vẫn cho DAG, nên Kahn có thể loại hết.

Nếu có chu trình, không thể xóa **đỉnh đầu tiên trên chu trình**: trước khi xóa nó, cạnh từ đỉnh trước đó trên vòng vẫn còn, nên indegree của nó không thể bằng 0. Do đó ít nhất các đỉnh vòng tồn tại đến cuối; Kahn không thể lấy đủ V đỉnh.

Kết hợp:

\[
\boxed{\text{Có chu trình}
\iff \text{DFS gặp cạnh tới GRAY}
\iff \text{Kahn lấy ra ít hơn V đỉnh}.}
\]

Lập luận và mã áp dụng cho **đồ thị có hướng**, không phải quy tắc bỏ qua cạnh parent của đồ thị vô hướng.

## 7. Chương trình Java 17 chạy độc lập

Chương trình sau cài:
- Xây đồ thị có hướng 0-based, kiểm tra n và cạnh.
- DFS ba màu trả một chu trình khép kín dưới dạng `List<Integer>`, hoặc danh sách rỗng nếu không có.
- Kahn trả `hasCycle` và `order`; `order` chỉ là topo đầy đủ nếu hasCycle=false.
- Hai bộ kiểm tra chứng cứ chu trình và thứ tự topo.
- Một **oracle độc lập** tính bao đóng đường đi bằng Warshall; chỉ dùng trên đồ thị nhỏ.
- Vét cạn mọi đồ thị có hướng đơn n=0..4 để đối chiếu với oracle.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class DirectedCycleDetectionDemo {
    static final int WHITE = 0;
    static final int GRAY = 1;
    static final int BLACK = 2;

    record KahnResult(boolean hasCycle, List<Integer> order) {}

    static List<List<Integer>> graph(int n, int[][] edges) {
        if (n < 0 || edges == null) {
            throw new IllegalArgumentException("Invalid graph");
        }
        List<List<Integer>> g = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            g.add(new ArrayList<>());
        }
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2
                    || edge[0] < 0 || edge[0] >= n
                    || edge[1] < 0 || edge[1] >= n) {
                throw new IllegalArgumentException("Invalid edge");
            }
            g.get(edge[0]).add(edge[1]);
        }
        return g;
    }

    static List<Integer> findCycleDFS(List<List<Integer>> g) {
        int n = g.size();
        int[] color = new int[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);
        List<Integer> cycle = new ArrayList<>();

        for (int u = 0; u < n; u++) {
            if (color[u] == WHITE
                    && dfs(u, g, color, parent, cycle)) {
                return List.copyOf(cycle);
            }
        }
        return List.of();
    }

    static boolean dfs(
            int u, List<List<Integer>> g, int[] color,
            int[] parent, List<Integer> cycle) {
        color[u] = GRAY;

        for (int v : g.get(u)) {
            if (color[v] == WHITE) {
                parent[v] = u;
                if (dfs(v, g, color, parent, cycle)) {
                    return true;
                }
            } else if (color[v] == GRAY) {
                // Canh u->v dong mot chu trinh.
                List<Integer> reversed = new ArrayList<>();
                int x = u;
                reversed.add(x);
                while (x != v) {
                    x = parent[x];
                    reversed.add(x);
                }
                Collections.reverse(reversed);
                reversed.add(v);
                cycle.addAll(reversed);
                return true;
            }
        }

        color[u] = BLACK;
        return false;
    }

    static KahnResult kahn(List<List<Integer>> g) {
        int n = g.size();
        int[] indegree = new int[n];
        for (int u = 0; u < n; u++) {
            for (int v : g.get(u)) {
                indegree[v]++;
            }
        }

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (int u = 0; u < n; u++) {
            if (indegree[u] == 0) {
                queue.addLast(u);
            }
        }

        List<Integer> order = new ArrayList<>();
        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            order.add(u);
            for (int v : g.get(u)) {
                indegree[v]--;
                if (indegree[v] == 0) {
                    queue.addLast(v);
                }
            }
        }
        return new KahnResult(
                order.size() < n, List.copyOf(order));
    }

    static String showCycle(List<Integer> cycle) {
        return cycle.isEmpty() ? "none" : cycle.toString();
    }

    // Oracle: bao dong kha dat, khong dung DFS mau/Kahn.
    static boolean hasCycleClosure(List<List<Integer>> g) {
        int n = g.size();
        boolean[][] reach = new boolean[n][n];
        for (int u = 0; u < n; u++) {
            for (int v : g.get(u)) {
                reach[u][v] = true;
            }
        }
        for (int k = 0; k < n; k++) {
            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) {
                    if (reach[i][k] && reach[k][j]) {
                        reach[i][j] = true;
                    }
                }
            }
        }
        for (int u = 0; u < n; u++) {
            if (reach[u][u]) return true;
        }
        return false;
    }

    static boolean validCycle(
            List<List<Integer>> g, List<Integer> cycle) {
        int n = g.size();
        if (cycle.size() < 2
                || !cycle.get(0).equals(
                        cycle.get(cycle.size() - 1))) {
            return false;
        }

        boolean[] seen = new boolean[n];
        for (int i = 0; i + 1 < cycle.size(); i++) {
            int u = cycle.get(i);
            int v = cycle.get(i + 1);
            if (u < 0 || u >= n || v < 0 || v >= n
                    || seen[u] || !g.get(u).contains(v)) {
                return false;
            }
            seen[u] = true;
        }
        return true;
    }

    static boolean validTopo(
            List<List<Integer>> g, List<Integer> order) {
        int n = g.size();
        if (order.size() != n) return false;
        int[] pos = new int[n];
        Arrays.fill(pos, -1);
        for (int i = 0; i < n; i++) {
            int v = order.get(i);
            if (v < 0 || v >= n || pos[v] != -1) {
                return false;
            }
            pos[v] = i;
        }
        for (int u = 0; u < n; u++) {
            for (int v : g.get(u)) {
                if (pos[u] >= pos[v]) {
                    return false;
                }
            }
        }
        return true;
    }

    static int verifySmallGraphs() {
        int checked = 0;
        for (int n = 0; n <= 4; n++) {
            int total = 1 << (n * n);
            for (int mask = 0; mask < total; mask++) {
                List<List<Integer>> g = new ArrayList<>();
                for (int u = 0; u < n; u++) {
                    g.add(new ArrayList<>());
                }
                for (int u = 0; u < n; u++) {
                    for (int v = 0; v < n; v++) {
                        if ((mask & (1 << (u * n + v))) != 0) {
                            g.get(u).add(v);
                        }
                    }
                }

                boolean expected = hasCycleClosure(g);
                List<Integer> cycle = findCycleDFS(g);
                KahnResult k = kahn(g);
                boolean dfsHasCycle = !cycle.isEmpty();

                if (dfsHasCycle != expected
                        || k.hasCycle() != expected
                        || (dfsHasCycle && !validCycle(g, cycle))
                        || (!expected && !validTopo(g, k.order()))) {
                    throw new AssertionError(
                            "Mismatch n=" + n + " mask=" + mask);
                }
                checked++;
            }
        }
        return checked;
    }

    public static void main(String[] args) {
        List<List<Integer>> dag = graph(4, new int[][]{
            {0, 1}, {0, 2}, {1, 3}, {2, 3}
        });
        KahnResult dk = kahn(dag);
        System.out.println(
                "dagDFS=" + showCycle(findCycleDFS(dag)));
        System.out.println(
                "dagKahn=" + dk.hasCycle()
                + " topo=" + dk.order());

        List<List<Integer>> cyclic = graph(4, new int[][]{
            {0, 1}, {1, 2}, {2, 0}, {2, 3}
        });
        KahnResult ck = kahn(cyclic);
        System.out.println(
                "cycleDFS=" + showCycle(findCycleDFS(cyclic)));
        System.out.println(
                "cycleKahn=" + ck.hasCycle()
                + " removed=" + ck.order().size()
                + "/" + cyclic.size());

        List<List<Integer>> self = graph(2, new int[][]{
            {0, 0}, {0, 1}
        });
        System.out.println(
                "selfLoopDFS=" + showCycle(findCycleDFS(self)));

        List<List<Integer>> parallel = graph(2, new int[][]{
            {0, 1}, {0, 1}
        });
        System.out.println(
                "parallelOnlyDFS="
                + showCycle(findCycleDFS(parallel)));

        List<List<Integer>> disconnected = graph(5, new int[][]{
            {0, 1}, {2, 3}, {3, 2}
        });
        System.out.println(
                "disconnectedDFS="
                + showCycle(findCycleDFS(disconnected)));

        List<List<Integer>> empty = graph(0, new int[0][0]);
        KahnResult ek = kahn(empty);
        System.out.println(
                "emptyKahn=" + ek.hasCycle()
                + " topo=" + ek.order());

        System.out.println("checked=" + verifySmallGraphs());
    }
}
~~~

Lưu tệp **DirectedCycleDetectionDemo.java**, chạy trên **JDK 17 trở lên**:

~~~bash
javac DirectedCycleDetectionDemo.java
java DirectedCycleDetectionDemo
~~~

**Đầu ra dự kiến chính xác:**

~~~text
dagDFS=none
dagKahn=false topo=[0, 1, 2, 3]
cycleDFS=[0, 1, 2, 0]
cycleKahn=true removed=0/4
selfLoopDFS=[0, 0]
parallelOnlyDFS=none
disconnectedDFS=[2, 3, 2]
emptyKahn=false topo=[]
checked=66067
~~~

### Ý nghĩa kết quả và các giới hạn

- `dagDFS=none`: DFS không thấy cạnh tới GRAY. Kahn trả `false` và topo gồm đầy đủ bốn đỉnh.
- `cycleDFS=[0,1,2,0]`: đây là danh sách khép kín; phải kiểm tra mọi cạnh 0→1, 1→2, 2→0 thật sự tồn tại.
- `cycleKahn=true removed=0/4`: không có đỉnh indegree 0 ban đầu; kết luận có chu trình, nhưng **không tự dựng đường khép kín**.
- `selfLoopDFS=[0,0]`: self-loop là một chu trình.
- `parallelOnlyDFS=none`: hai cạnh cùng chiều không tạo chu trình; Kahn vẫn đếm/trừ hai cạnh nếu gọi.
- `disconnectedDFS=[2,3,2]`: dù 0→1 không dẫn tới 2, vòng ngoài DFS vẫn kiểm tra thành phần còn lại.
- `emptyKahn=false topo=[]`: đồ thị rỗng không có vòng; thứ tự topo rỗng hợp lệ.
- `checked=66067`: số đồ thị vét cạn qua oracle, không phải số đỉnh hay số lần gọi DFS trên riêng một đồ thị.

`findCycleDFS` trả **một chu trình bất kỳ theo thứ tự duyệt**, không bảo đảm chu trình ngắn nhất hoặc duy nhất. Nếu đề yêu cầu thứ tự xác định, cần quy định thứ tự đỉnh bắt đầu và thứ tự danh sách kề; chương trình dùng 0..n−1 và thứ tự chèn cạnh.

**Lưu ý tràn stack:** chương trình dùng DFS đệ quy để dễ thấy màu GRAY; trên đường rất sâu có thể gây `StackOverflowError`. Khi cần xử lý đồ thị cực lớn, dùng stack tường minh (hoặc dùng Kahn nếu chỉ cần boolean/topo). Không được bỏ GRAY quá sớm khi chuyển DFS sang dạng lặp.

## 8. Kiểm thử độc lập trên 66.067 đồ thị

Oracle trong chương trình dùng **bao đóng khả đạt**: khởi tạo `reach[u][v]=true` khi có **cạnh thực** u→v, sau đó dùng các đỉnh trung gian k để tìm những đường có hướng có độ dài dương. Đặc biệt, **không đặt sẵn `reach[u][u]=true`** lúc khởi tạo, vì điều đó sẽ làm mọi đỉnh trông như có chu trình.

Sau khi tính bao đóng, có chu trình khi tồn tại u với `reach[u][u]=true`: có một đường đi theo cạnh quay về u.

Với n đỉnh, mỗi cặp có thứ tự `(u,v)` có hoặc không có cạnh, kể cả u=v, nên có \(2^{n^2}\) đồ thị đơn có hướng. Vét cạn n từ 0 đến 4:

| n | Số đồ thị |
| ---: | ---: |
| 0 | 1 |
| 1 | 2 |
| 2 | 16 |
| 3 | 512 |
| 4 | 65.536 |
| **Tổng** | **66.067** |

Với mỗi đồ thị, mã đối chiếu:
1. Boolean phát hiện chu trình của DFS với oracle.
2. Boolean phát hiện của Kahn với oracle.
3. Nếu DFS trả chu trình, **mọi cạnh nối liên tiếp phải có trong danh sách kề đúng chiều**, danh sách phải khép kín và không lặp đỉnh nội bộ.
4. Nếu oracle xác định DAG, Kahn phải trả một thứ tự topo **chứa mỗi đỉnh đúng một lần** và đảm bảo với mọi cạnh u→v, vị trí u nhỏ hơn vị trí v.

Bộ vét cạn này bao gồm đồ thị n=0, self-loop, vòng hai cạnh, vòng dài hơn và đồ thị không liên thông. Nó xét mỗi cặp u→v tối đa một lần, nên **không chứa cạnh song song**; ví dụ `parallel` trong `main` minh họa riêng trường hợp ấy.

Oracle có **O(n³) thời gian và O(n²) bộ nhớ trên một đồ thị**, nên chỉ dùng để kiểm thử đồ thị nhỏ. Hai thuật toán chính có **O(V+E)** thời gian nhờ danh sách kề.

**Kiểm thử không thay chứng minh:** vét cạn n≤4 xác thực cài đặt trên một tập hữu hạn; tính đúng tổng quát đến từ bất biến GRAY của DFS và tính chất indegree 0 của DAG.

## 9. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gặp `visited[v]` là báo chu trình | Dương tính giả ở DAG hình thoi | Chỉ báo khi v **GRAY** |
| Chỉ chạy DFS từ đỉnh 0 | Bỏ sót vòng ở thành phần khác | Duyệt mọi đỉnh WHITE |
| Bỏ cạnh tới parent như đồ thị vô hướng | Bỏ sót chu trình 0→1→0 | Không bỏ cạnh có hướng thật |
| Không xử lý self-loop | Bỏ sót chu trình [u,u] | GRAY khi đang ở u |
| Nhầm hai cạnh 0→1 song song với vòng hai chiều | Báo sai | Cần đường thực từ 1 về 0 |
| Đếm indegree theo số cạnh nhưng trừ theo số đỉnh khác nhau | Kahn kẹt sai | Duyệt/trừ từng cạnh |
| So số cạnh đã xóa với V | Kết luận sai | So số **đỉnh** đã lấy |
| Coi order một phần là topo đầy đủ | Có thể còn vòng | Chỉ topo khi order.size()==V |
| Cho rằng mọi đỉnh còn lại sau Kahn thuộc vòng | Nhầm đỉnh phụ thuộc vào vòng | DFS dựng vòng hoặc tìm SCC |
| Gặp cạnh tới BLACK rồi lần parent để dựng vòng | Có thể không quay về tổ tiên | Chỉ dựng khi v GRAY |
| Không đảo chuỗi parent | Các cặp kế tiếp sai chiều | Đảo [u,...,v], thêm v |
| Tự thêm cạnh ngược vào adjacency | Chuyển thành bài toán khác | Giữ đúng chiều input |
| Dùng DFS đệ quy cho đường quá sâu | Có thể tràn stack | Stack DFS tự quản hoặc Kahn |
| Coi phát hiện vòng thường là phát hiện chu trình âm | Sai mục tiêu | Với trọng số cần thuật toán riêng |
| Không xác minh chứng cứ chu trình | Có thể trả danh sách sai | Kiểm tra từng cạnh đúng chiều |

### Phân biệt mục tiêu nâng cao

Nếu đề chỉ hỏi **có vòng hay không**, DFS/Kahn đủ. Nếu cần **sắp topo**, Kahn trả order khi DAG. Nếu cần **một vòng thật sự**, DFS với parent tiện hơn. Nếu cần **những nhóm đỉnh phụ thuộc vòng tròn**, nên tìm **thành phần liên thông mạnh (SCC)** bằng Tarjan hoặc Kosaraju; một SCC nhiều hơn một đỉnh có chu trình, còn SCC một đỉnh chỉ có chu trình khi có self-loop.

Nếu đồ thị có trọng số, việc có **chu trình bất kỳ** khác với việc có **chu trình âm** hay **chu trình ngắn nhất**. Những bài toán đó cần thuật toán và giả thiết riêng.

## 10. Bài tập tự luyện có đáp án

**Bài 1.** Đồ thị chỉ có `0→1, 1→2`. Có chu trình không?

*Đáp án:* Không. Chưa có đường quay về đỉnh xuất phát.

**Bài 2.** Đồ thị có `0→1,1→0`. Khi DFS từ 0 đến 1 rồi xét `1→0`, màu của 0 là gì?

*Đáp án:* 0 đang GRAY. Cạnh 1→0 đóng chu trình `[0,1,0]`.

**Bài 3.** Đồ thị một đỉnh có self-loop `0→0`. Chu trình nào được in?

*Đáp án:* `[0,0]`, một chu trình một cạnh.

**Bài 4.** Với `0→1,0→2,1→3,2→3`, DFS có thể gặp 3 đã BLACK khi xét `2→3` không? Có vòng không?

*Đáp án:* Có thể gặp BLACK, nhưng **không có chu trình**. Một topo hợp lệ là [0,1,2,3].

**Bài 5.** Kahn của DAG hình thoi có indegree ban đầu là gì và loại đỉnh theo thứ tự nào nếu queue ưu tiên thứ tự thêm 0..3?

*Đáp án:* Indegree `[0,1,1,2]`, thứ tự `[0,1,2,3]`.

**Bài 6.** Kahn với `0→1,1→2,2→1` lấy được bao nhiêu đỉnh?

*Đáp án:* Lấy được một đỉnh 0, rồi còn vòng 1↔2 và dừng. Có chu trình.

**Bài 7.** Đồ thị `0→1,1→2,2→0,2→3`: những đỉnh nào nằm trên chu trình và những đỉnh nào còn lại sau Kahn?

*Đáp án:* Chu trình gồm 0,1,2. Kahn không lấy được đỉnh nào nên cả 0,1,2,3 đều còn; đỉnh 3 không thuộc chu trình.

**Bài 8.** Hai cạnh song song cùng chiều `0→1` có phải một chu trình không? Kahn cần trừ indegree như thế nào?

*Đáp án:* Không. Indegree[1]=2; khi xử lý đỉnh 0, trừ hai lần để còn 0.

**Bài 9.** Có `0→1` và một thành phần khác gồm `2→3,3→2`. Nếu chỉ duyệt từ 0, có phát hiện vòng không?

*Đáp án:* Không. Phải duyệt thêm các đỉnh WHITE, khi đó tìm được `[2,3,2]`.

**Bài 10.** Tại sao cạnh u→v tới GRAY chứng minh có vòng, còn cạnh tới BLACK thì không?

*Đáp án:* GRAY biểu diễn tổ tiên đang trên stack, có đường cây v→...→u; thêm u→v khép vòng. BLACK đã kết thúc, không đảm bảo có đường cây theo chiều ấy.

**Bài 11.** Với n đỉnh m cạnh, độ phức tạp của DFS và Kahn là bao nhiêu?

*Đáp án:* Cả hai O(n+m) thời gian, O(n) bộ nhớ phụ ngoài danh sách kề.

**Bài 12.** Nếu muốn phát hiện **mọi nhóm đỉnh có phụ thuộc vòng tròn**, liệu in một chu trình bằng DFS đã đủ chưa?

*Đáp án:* Chưa. Một vòng chỉ là một chứng cứ; phân tích SCC bằng Tarjan/Kosaraju giúp xác định các nhóm mạnh liên thông có vòng.

## Tổng kết

- **Chu trình có hướng** phải đi theo đúng chiều cạnh. Self-loop là chu trình; cạnh song song cùng chiều tự nó không tạo vòng.
- **DFS ba màu:** WHITE chưa thăm, GRAY đang trên stack, BLACK đã hoàn tất. Cạnh tới **GRAY** phát hiện vòng; dùng parent để dựng `[v,...,u,v]`.
- **Kahn:** liên tục xóa đỉnh có bậc vào 0; nếu không xóa được đủ V đỉnh thì đồ thị có chu trình. Nếu xóa đủ, order là topo.
- **Không chỉ duyệt một thành phần**, không áp dụng quy tắc bỏ qua parent của đồ thị vô hướng, không coi đỉnh còn lại sau Kahn đều nằm trên vòng.
- **Thời gian O(V+E), bộ nhớ phụ O(V)** cho cả hai cách dùng danh sách kề.
- **Đối chiếu bằng oracle và xác minh từng cạnh trong chứng cứ** giúp phát hiện lỗi cài đặt; bất biến DFS và định lý DAG có đỉnh bậc vào 0 bảo đảm tính đúng tổng quát.

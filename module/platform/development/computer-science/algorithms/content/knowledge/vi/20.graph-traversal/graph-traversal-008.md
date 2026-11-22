# Khoảng cách theo số cạnh trên đồ thị không trọng số

**Khoảng cách theo số cạnh trên đồ thị không trọng số** là số **cạnh ít nhất** cần đi qua để tới một đỉnh đích từ một đỉnh xuất phát. Thuật toán chuẩn để tìm khoảng cách này là **BFS — Breadth-First Search (duyệt theo chiều rộng)**. BFS thăm các đỉnh theo **từng lớp khoảng cách**: trước hết đỉnh xuất phát, sau đó các đỉnh cách một cạnh, rồi hai cạnh, ba cạnh, ... Vì mỗi cạnh đều có cùng chi phí **một bước**, lần đầu tiên BFS phát hiện một đỉnh chính là lúc đã biết **độ dài đường đi ngắn nhất** từ nguồn đến đỉnh đó.

Bài học thuộc chủ đề **Duyệt đồ thị (Graph Traversal)**. Nội dung giải thích mô hình hóa đồ thị có hướng/vô hướng, định nghĩa độ dài đường đi, hàng đợi FIFO, công thức `dist[v]=dist[u]+1`, bất biến và chứng minh tính đúng đắn, phục dựng đường đi, xử lý đỉnh không thể tới, BFS nhiều nguồn, độ phức tạp O(V+E), cách chuyển từ bài toán lưới sang đồ thị và những khác biệt với DFS, Dijkstra, 0-1 BFS. Chương trình **Java 17+** có thể biên dịch/chạy độc lập, in đầu ra chính xác và kiểm thử với thuật toán tham chiếu.

## 1. Hiểu chính xác “khoảng cách theo số cạnh”

Một **đồ thị** có tập đỉnh `V` và tập cạnh `E`. Với đồ thị vô hướng, cạnh `(u,v)` cho phép đi cả `u→v` và `v→u`. Với đồ thị có hướng, cung `u→v` chỉ cho phép đi theo chiều mũi tên, trừ khi có thêm cung ngược lại.

Một **đường đi (path)** từ `s` đến `t` có dạng:

~~~text
s = v0 -> v1 -> v2 -> ... -> vk = t
~~~

trong đó mỗi bước `v_(i-1) -> v_i` là một cạnh/cung hợp lệ. **Độ dài theo số cạnh** của đường đi là **k**, không phải k+1. Nếu một đường đi có 5 đỉnh liên tiếp thì nó có 4 cạnh.

Khoảng cách ngắn nhất theo số cạnh, ký hiệu `dist(s,t)`, là:

~~~text
dist(s,t) = min(k) trên mọi đường đi s -> t dùng k cạnh
~~~

Nếu **không có đường đi** hợp lệ từ s đến t, khoảng cách theo lý thuyết được xem là **vô cùng**; khi cài đặt, thường lưu **-1** để chỉ “không thể tới”.

### Những trường hợp biên quan trọng

- `dist(s,s)=0`: từ một đỉnh tới chính nó không cần qua cạnh nào, kể cả khi đồ thị có chu trình.
- Nếu có cạnh trực tiếp `s→t` thì `dist(s,t)=1`, miễn s khác t và có đường đi hợp lệ.
- Nếu đường ngắn nhất đi qua `s→a→b→t`, khoảng cách là **3**, dù dãy gồm 4 đỉnh.
- Với đồ thị **có hướng**, `dist(s,t)` có thể khác `dist(t,s)` hoặc một chiều không tồn tại.
- Với đồ thị **vô hướng**, khoảng cách giữa hai đỉnh liên thông là đối xứng: `dist(s,t)=dist(t,s)`.
- Nếu có nhiều đường đi ngắn nhất cùng độ dài, BFS vẫn tính đúng **một giá trị khoảng cách**, còn đường đi được phục dựng phụ thuộc thứ tự duyệt hàng xóm.

“Không trọng số” ở đây hiểu là mọi cạnh được tính **một đơn vị độ dài**, không phải các cạnh có chi phí bằng **0**. Nếu một cạnh có trọng số 0, đi qua cạnh đó có thể không làm tăng khoảng cách chi phí, và BFS thường **không còn đúng** cho mục tiêu tổng trọng số nhỏ nhất.

## 2. Vì sao duyệt theo chiều rộng giải được bài toán?

BFS sử dụng một **hàng đợi FIFO (First In, First Out)**:

1. Đưa nguồn `s` vào hàng đợi; đặt `dist[s]=0`.
2. Lấy đỉnh `u` ở đầu hàng đợi ra.
3. Xét mọi hàng xóm có thể đi tới `v` của u.
4. Nếu v **chưa được phát hiện**, đặt `dist[v]=dist[u]+1` và đưa v vào cuối hàng đợi.
5. Lặp cho tới khi hàng đợi rỗng.

FIFO giữ các đỉnh theo **lớp (level)**:

~~~text
L0: tất cả đỉnh có dist = 0       -> chỉ có nguồn s
L1: tất cả đỉnh có dist = 1       -> hàng xóm trực tiếp
L2: tất cả đỉnh có dist = 2       -> tới từ một đỉnh L1
L3: tất cả đỉnh có dist = 3       -> tới từ một đỉnh L2
...
~~~

Khi một đỉnh ở lớp k được lấy khỏi hàng đợi, mọi đỉnh ở lớp nhỏ hơn k đã được xử lý, và những đỉnh chưa biết khoảng cách được phát hiện từ đó sẽ có khoảng cách k+1.

**Điểm không được nhầm:** BFS không nhất thiết duyệt các đỉnh trong cùng lớp theo một thứ tự cố định, và không nhất thiết chọn cùng một **đường đi cụ thể** nếu danh sách kề đổi thứ tự. Nó bảo đảm **độ dài ngắn nhất** vì lớp khoảng cách tăng dần, không vì sắp xếp đỉnh theo số ID.

### Trạng thái cần lưu

Với `n` đỉnh đánh số `0..n-1`:

- `distance[v]`: độ dài đường đi ngắn nhất từ nguồn s đến v, ban đầu -1.
- `parent[v]`: đỉnh đứng ngay trước v trên **một đường đi ngắn nhất** được BFS phát hiện, ban đầu -1.
- `queue`: hàng đợi các đỉnh đã phát hiện nhưng chưa xử lý hết cạnh đi ra.

Chỉ cần một mảng `distance` để biết đỉnh **đã thăm**: `distance[v]!=-1`. Không cần mảng `visited` riêng nếu -1 không trùng một khoảng cách hợp lệ. Độ dài đường đi không âm nên -1 là sentinel an toàn.

## 3. Ví dụ duyệt tay đồ thị vô hướng

Xét đồ thị gồm **7 đỉnh** với các cạnh:

~~~text
(0,1), (0,2), (1,3), (2,3), (3,4), (2,5)

        0
      /   \
     1     2 ---- 5
      \   /
        3 ---- 4

     6 (đỉnh cô lập)
~~~

Nguồn `s=0`. Các danh sách kề xét theo **thứ tự thêm cạnh** như trên:

~~~text
adj[0] = [1,2]
adj[1] = [0,3]
adj[2] = [0,3,5]
adj[3] = [1,2,4]
adj[4] = [3]
adj[5] = [2]
adj[6] = []
~~~

Ban đầu:

~~~text
distance = [0,-1,-1,-1,-1,-1,-1]
parent   = [-1,-1,-1,-1,-1,-1,-1]
queue    = [0]
~~~

Quá trình phát hiện các đỉnh mới:

| Bước | Đỉnh lấy khỏi đầu queue | Đỉnh mới được phát hiện (distance) | Queue sau bước |
| ---: | ---: | --- | --- |
| 1 | 0 | 1 (1), 2 (1) | [1,2] |
| 2 | 1 | 3 (2) | [2,3] |
| 3 | 2 | 5 (2); 3 đã phát hiện nên bỏ qua | [3,5] |
| 4 | 3 | 4 (3) | [5,4] |
| 5 | 5 | Không có đỉnh mới | [4] |
| 6 | 4 | Không có đỉnh mới | [] |

Đỉnh 6 không nằm trong thành phần liên thông chứa 0, nên không được phát hiện.

Kết quả:

~~~text
distance = [0,1,1,2,3,2,-1]
parent   = [-1,0,0,1,3,2,-1]
~~~

Từ đó:

- `dist(0,4)=3`, với một đường đi ngắn nhất là `0→1→3→4`.
- `dist(0,5)=2`, với đường đi ngắn nhất `0→2→5`.
- `dist(0,6)=-1` theo quy ước cài đặt: **không thể tới**.
- `dist(0,0)=0`; đường đi được phục dựng là `[0]`, không phải danh sách rỗng.
- Đỉnh 3 có **hai** đường đi ngắn nhất độ dài 2: `0→1→3` và `0→2→3`. Vì danh sách kề đưa 1 vào queue trước 2, `parent[3]=1` trong lần chạy này.

Đồ thị không có quy tắc bắt buộc chọn đường đi `0→1→3` thay vì `0→2→3`. Nếu cần **đường đi từ điển nhỏ nhất** theo một định nghĩa cụ thể, phải mô tả và xử lý thêm yêu cầu về thứ tự; BFS cơ bản chỉ bảo đảm độ dài.

## 4. Giả mã BFS một nguồn

~~~text
ALGORITHM BFS_SHORTEST_EDGE_DISTANCE(graph, source)
    REQUIRE graph has n vertices indexed 0..n-1
    REQUIRE 0 <= source < n
    REQUIRE every edge contributes exactly one step

    distance[0..n-1] <- -1
    parent[0..n-1] <- -1

    queue <- empty FIFO queue
    distance[source] <- 0
    ENQUEUE(queue, source)

    WHILE queue is not empty DO
        u <- DEQUEUE_FRONT(queue)

        FOR EACH edge u -> v IN adjacency[u] DO
            IF distance[v] = -1 THEN
                distance[v] <- distance[u] + 1
                parent[v] <- u
                ENQUEUE_BACK(queue, v)
            END IF
        END FOR
    END WHILE

    RETURN distance, parent
END ALGORITHM
~~~

**Đánh dấu ngay khi ENQUEUE, không đợi lúc DEQUEUE.** Khi nhìn thấy v lần đầu, đặt khoảng cách và cha ngay rồi mới đưa vào queue. Những cạnh khác đi tới v sẽ không thêm v lần nữa, nên **mỗi đỉnh vào queue tối đa một lần**. Nếu chỉ đánh dấu khi lấy ra, v có thể được đưa vào queue rất nhiều lần qua các cạnh khác nhau, làm tốn bộ nhớ/thời gian và dễ ghi đè parent không nhất quán.

**Chỉ số parent của nguồn:** `parent[source]=-1` vì nguồn không có đỉnh đứng trước. Các đỉnh không tới được cũng có `parent=-1`, nhưng phân biệt bằng `distance`: nguồn có khoảng cách 0, đỉnh không tới có khoảng cách -1.

**Đồ thị vô hướng:** khi xây danh sách kề, mỗi cạnh `(u,v)` phải được thêm cả `u→v` và `v→u`. Nếu chỉ thêm một chiều thì chương trình đã giải một **đồ thị có hướng khác** với đề.

**Đồ thị có hướng:** chỉ thêm cạnh theo chiều được cho. BFS không tự đi ngược cung.

## 5. Chứng minh BFS trả khoảng cách ngắn nhất

Không nên chỉ nói “BFS dùng queue nên đúng”. Cần hiểu **tại sao lần đầu phát hiện là ngắn nhất**.

### 5.1. Mọi khoảng cách được gán đều xuất phát từ đường đi thật

**Cơ sở:** `distance[source]=0` ứng với đường đi rỗng dài 0 cạnh.

**Bước quy nạp:** nếu một đỉnh u đã có đường đi từ s dài `distance[u]`, và BFS phát hiện v qua cạnh `u→v`, thì nối thêm cạnh ấy tạo một đường đi từ s tới v dài `distance[u]+1`. Do vậy, khoảng cách được gán cho v luôn là độ dài **một đường đi hợp lệ**, không phải con số đoán.

Vì thế `distance[v]` lúc đầu không thể **nhỏ hơn** khoảng cách ngắn nhất thật.

### 5.2. FIFO tạo thứ tự lớp không giảm

Khi BFS đang lấy các đỉnh khỏi queue theo FIFO, khoảng cách của đỉnh được lấy ra là một dãy **không giảm**. Từ một đỉnh ở lớp k, các đỉnh mới phát hiện có lớp k+1 và được thêm vào **cuối** queue. Do đó đỉnh ở lớp lớn hơn không thể vượt lên trước những đỉnh đã chờ ở lớp nhỏ hơn.

Nói cách khác, sau khi xử lý hết các đỉnh có khoảng cách k-1, BFS mới hoàn tất phát hiện/xử lý những lớp xa hơn theo cấu trúc hàng đợi.

### 5.3. Không thể có đường đi ngắn hơn

Giả sử BFS phát hiện v lần đầu và gán `distance[v]=d` qua đỉnh u có khoảng cách d-1. Nếu thực sự có đường đi từ s đến v dài `k<d`, xét đỉnh đứng ngay trước v trên đường đi ngắn ấy, gọi là x. Khi đó có một đường đi đến x dài k-1. Theo lập luận lớp BFS, x phải được xử lý **trước** mọi đỉnh ở lớp d-1. Khi xử lý cạnh `x→v`, BFS lẽ ra đã phát hiện v với khoảng cách không quá k — mâu thuẫn với việc v lần đầu được phát hiện ở khoảng cách d.

Vì vậy giá trị lần đầu gán là **khoảng cách tối thiểu**.

### 5.4. Mọi đỉnh có thể tới đều được phát hiện

Cho một đường đi bất kỳ `s=v0→v1→...→vk=t`. Nguồn v0 được đưa vào queue. Khi một đỉnh vi trên đường đi được xử lý, BFS xét cạnh `vi→v_(i+1)`, nên đỉnh kế tiếp sẽ được phát hiện nếu chưa có, hoặc đã được phát hiện từ trước. Quy nạp theo các cạnh trên đường đi cho thấy t cuối cùng được phát hiện.

Do đó, sau khi queue rỗng:

- `distance[v]>=0` **khi và chỉ khi** v có thể tới từ s;
- nếu tới được, `distance[v]` đúng bằng số cạnh của đường đi ngắn nhất;
- `parent` tạo ra **một cây BFS** trên các đỉnh có thể tới, mỗi cạnh parent giảm khoảng cách đúng 1.

### 5.5. Vì sao thuật toán kết thúc?

Mỗi đỉnh chỉ được đưa vào queue **một lần** do đánh dấu khi enqueue. Mỗi lần lấy khỏi queue, chương trình duyệt danh sách kề hữu hạn. Vì có n đỉnh và m cạnh, quá trình kết thúc sau hữu hạn bước.

## 6. Phục dựng một đường đi ngắn nhất

Khi BFS phát hiện v từ u lần đầu, lưu `parent[v]=u`. Với đích t có `distance[t]>=0`:

1. Bắt đầu từ t.
2. Lặp `t=parent[t]` cho tới -1, ghi các đỉnh đã đi qua.
3. Đảo ngược dãy để được đường đi từ nguồn s tới đích ban đầu.

~~~text
ALGORITHM RECONSTRUCT(parent, distance, target)
    IF distance[target] == -1 THEN
        RETURN []  // Không thể tới.
    END IF

    reversed <- []
    cur <- target
    WHILE cur != -1 DO
        APPEND cur TO reversed
        cur <- parent[cur]
    END WHILE
    REVERSE(reversed)
    RETURN reversed
END ALGORITHM
~~~

**Ví dụ:** với `parent[4]=3`, `parent[3]=1`, `parent[1]=0` và `parent[0]=-1`, ta thu thứ tự ngược `[4,3,1,0]`; đảo lại được `[0,1,3,4]`, dài đúng **3 cạnh**.

Nếu s=t, kết quả là danh sách chỉ chứa s; **số cạnh bằng 0**. Nếu t không thể tới, trả danh sách rỗng trong ví dụ cài đặt. Không nên nhầm danh sách rỗng với đường đi từ s tới chính s: trường hợp s=t có **một đỉnh**.

### Có nhiều đường đi ngắn nhất

BFS có thể giữ một `parent` bất kỳ từ lần khám phá đầu tiên. Nếu đỉnh v có nhiều cha tiềm năng ở lớp trước, `distance[v]` vẫn giữ nguyên; không được ghi đè `distance[v]` thành giá trị lớn hơn theo một nhánh khác.

Nếu muốn **đếm số đường đi ngắn nhất**, cần thêm mảng `ways[v]`. Với đồ thị không có nhiều cạnh song song hoặc khi đã xác định rõ cách đếm đường đi theo cạnh:

~~~text
ways[source] = 1

Khi v được phát hiện lần đầu từ u:
    distance[v] = distance[u] + 1
    ways[v] = ways[u]

Khi xét cạnh u -> v mà distance[v] == distance[u] + 1:
    ways[v] += ways[u]
~~~

Nếu dùng cấu trúc kiểm tra theo thứ tự, hãy nhớ phân biệt nhánh **phát hiện mới** với nhánh **đã có khoảng cách bằng lớp kế** để tránh cộng hai lần trong cùng một lần xét cạnh. Với đồ thị có **cạnh song song**, việc đếm “đường đi theo dãy đỉnh” hay “đường đi theo các cạnh riêng biệt” là hai bài toán khác nhau. Tổng số đường đi ngắn nhất có thể rất lớn, nên thường cần `long`, `BigInteger` hoặc modulo theo đề.

## 7. BFS nhiều nguồn (multi-source BFS)

Đôi khi không có một đỉnh bắt đầu duy nhất. Ví dụ: tìm số bước ít nhất từ **bất kỳ trạm cứu hộ nào** tới mỗi vị trí, hoặc từ **bất kỳ cổng nào** tới mỗi phòng.

Cho tập nguồn `S={s1,s2,...,sk}`. Cần tính:

`distance[v] = min(dist(s_i,v))` với mọi nguồn s_i thuộc S.

Cách làm: **đưa tất cả nguồn hợp lệ vào queue với khoảng cách 0** ngay từ đầu, rồi thực hiện BFS bình thường:

~~~text
distance[v] <- -1 for all v
queue <- empty

FOR EACH source s IN sources DO
    IF distance[s] == -1 THEN
        distance[s] <- 0
        ENQUEUE(queue, s)
    END IF
END FOR

WHILE queue not empty DO
    u <- DEQUEUE(queue)
    FOR EACH edge u -> v DO
        IF distance[v] == -1 THEN
            distance[v] <- distance[u] + 1
            ENQUEUE(queue, v)
        END IF
    END FOR
END WHILE
~~~

**Chú ý nguồn trùng:** nếu danh sách nguồn có một đỉnh lặp, chỉ đưa nó vào queue một lần. Nếu tập nguồn rỗng, theo quy ước không có nguồn nào để đi từ đó, tất cả đỉnh có khoảng cách -1.

Trên đồ thị 7 đỉnh ở mục 3, chọn hai nguồn `{1,3}`. Khoảng cách theo số cạnh đến **nguồn gần nhất** là:

~~~text
[1, 0, 1, 0, 1, 2, -1]
~~~

Đỉnh 6 vẫn không thể tới, còn đỉnh 2 cách đỉnh 3 một cạnh. Các nguồn có khoảng cách 0 và cả hai cùng mở rộng theo lớp.

**Sai lầm:** chạy BFS riêng từ từng nguồn rồi cộng khoảng cách không giải bài **nguồn gần nhất**. Có thể lấy min của nhiều kết quả, nhưng làm k lần sẽ tốn `O(k(V+E))`, trong khi multi-source BFS chỉ cần **O(V+E+k)** để khởi tạo k nguồn và duyệt đồ thị một lần.

Có thể hình dung thêm một **siêu nguồn** có cạnh chi phí **0** tới mọi nguồn thật, rồi chạy mô hình thích hợp; nhưng nếu thêm những cạnh ấy và đếm tất cả như 1 bước thì kết quả sẽ lệch 1. Cách khởi tạo tất cả nguồn ở khoảng cách 0 đơn giản và chính xác hơn.

## 8. Java 17+ — BFS, phục dựng đường đi và nhiều nguồn

Chương trình sau dùng `ArrayDeque<Integer>` cho FIFO thay vì `ArrayList.remove(0)`, vì việc xóa đầu một ArrayList phải dời nhiều phần tử. Đồ thị lưu bằng danh sách kề `List<List<Integer>>`.

Nó cung cấp:

- `buildGraph(n,edges,directed)` để xây đồ thị có hướng hoặc vô hướng và kiểm tra chỉ số.
- `bfs(graph,source)` trả `distance`, `parent`.
- `BfsResult.pathTo(target)` phục dựng một đường đi ngắn nhất, trả `[]` khi không thể tới.
- `multiSourceDistances(graph,sources)` tìm khoảng cách tới nguồn gần nhất.
- `referenceDistances` dùng **n-1 lượt nới lỏng cạnh** để đối chiếu độc lập trên đồ thị nhỏ; hàm này không thay thế BFS về hiệu năng.
- `randomCrossCheck` tạo 200 đồ thị ngẫu nhiên nhỏ (có hướng hoặc vô hướng, có thể có khuyên và cạnh song song), kiểm tra khoảng cách và cấu trúc đường đi.

Tạo tệp **`UnweightedEdgeDistanceDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class UnweightedEdgeDistanceDemo {
    record BfsResult(int source, int[] distance, int[] parent) {
        List<Integer> pathTo(int target) {
            if (target < 0 || target >= distance.length) {
                throw new IllegalArgumentException("Invalid target");
            }
            if (distance[target] == -1) {
                return List.of();
            }

            List<Integer> reversed = new ArrayList<>();
            for (int cur = target; cur != -1; cur = parent[cur]) {
                reversed.add(cur);
            }
            Collections.reverse(reversed);
            return List.copyOf(reversed);
        }
    }

    public static List<List<Integer>> buildGraph(
            int n, int[][] edges, boolean directed) {
        Objects.requireNonNull(edges, "edges");
        if (n < 0) {
            throw new IllegalArgumentException("Negative vertex count");
        }

        List<List<Integer>> graph = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            graph.add(new ArrayList<>());
        }

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException("Invalid edge");
            }
            int from = edge[0];
            int to = edge[1];
            if (from < 0 || from >= n || to < 0 || to >= n) {
                throw new IllegalArgumentException("Invalid endpoint");
            }

            graph.get(from).add(to);
            if (!directed) {
                graph.get(to).add(from);
            }
        }
        return graph;
    }

    public static BfsResult bfs(
            List<List<Integer>> graph, int source) {
        Objects.requireNonNull(graph, "graph");
        int n = graph.size();
        if (source < 0 || source >= n) {
            throw new IllegalArgumentException("Invalid source");
        }

        int[] distance = new int[n];
        int[] parent = new int[n];
        Arrays.fill(distance, -1);
        Arrays.fill(parent, -1);

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        distance[source] = 0;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();

            for (int v : graph.get(u)) {
                if (distance[v] != -1) {
                    continue;
                }
                distance[v] = distance[u] + 1;
                parent[v] = u;
                queue.addLast(v);
            }
        }

        return new BfsResult(source, distance, parent);
    }

    public static int[] multiSourceDistances(
            List<List<Integer>> graph, int[] sources) {
        Objects.requireNonNull(graph, "graph");
        Objects.requireNonNull(sources, "sources");
        int n = graph.size();
        int[] distance = new int[n];
        Arrays.fill(distance, -1);

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (int source : sources) {
            if (source < 0 || source >= n) {
                throw new IllegalArgumentException("Invalid source");
            }
            if (distance[source] == -1) {
                distance[source] = 0;
                queue.addLast(source);
            }
        }

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (int v : graph.get(u)) {
                if (distance[v] == -1) {
                    distance[v] = distance[u] + 1;
                    queue.addLast(v);
                }
            }
        }
        return distance;
    }

    // Tham chiếu độc lập cho unit test:
    // với n đỉnh, một đường ngắn nhất có thể chọn là đường đơn
    // nên dùng tối đa n-1 cạnh.
    private static int[] referenceDistances(
            List<List<Integer>> graph, int source) {
        int n = graph.size();
        int inf = 1_000_000_000;
        int[] current = new int[n];
        Arrays.fill(current, inf);
        current[source] = 0;

        for (int round = 0; round < n - 1; round++) {
            int[] next = current.clone();
            for (int u = 0; u < n; u++) {
                if (current[u] == inf) {
                    continue;
                }
                for (int v : graph.get(u)) {
                    next[v] = Math.min(next[v], current[u] + 1);
                }
            }
            current = next;
        }

        for (int i = 0; i < n; i++) {
            if (current[i] == inf) {
                current[i] = -1;
            }
        }
        return current;
    }

    private static void checkPaths(
            List<List<Integer>> graph, BfsResult result) {
        int n = graph.size();
        int source = result.source();

        for (int target = 0; target < n; target++) {
            List<Integer> path = result.pathTo(target);
            int distance = result.distance()[target];

            if (distance == -1) {
                if (!path.isEmpty()) {
                    throw new AssertionError("Unreachable path exists");
                }
                continue;
            }
            if (path.size() != distance + 1 ||
                    path.get(0) != source ||
                    path.get(path.size() - 1) != target) {
                throw new AssertionError("Wrong path endpoints/length");
            }

            for (int i = 1; i < path.size(); i++) {
                int from = path.get(i - 1);
                int to = path.get(i);
                if (!graph.get(from).contains(to)) {
                    throw new AssertionError("Non-edge in path");
                }
            }
        }
    }

    private static void randomCrossCheck() {
        Random random = new Random(2026L);

        for (int test = 0; test < 200; test++) {
            int n = 1 + random.nextInt(9);
            boolean directed = random.nextBoolean();
            int m = random.nextInt(2 * n * n + 1);
            int[][] edges = new int[m][2];

            for (int e = 0; e < m; e++) {
                edges[e][0] = random.nextInt(n);
                edges[e][1] = random.nextInt(n);
            }

            List<List<Integer>> graph =
                    buildGraph(n, edges, directed);
            int source = random.nextInt(n);
            BfsResult found = bfs(graph, source);
            int[] expected = referenceDistances(graph, source);

            if (!Arrays.equals(found.distance(), expected)) {
                throw new AssertionError(
                        "Distance mismatch at test " + test);
            }
            checkPaths(graph, found);
        }
        System.out.println("randomCrossCheck=PASS (200 graphs)");
    }

    public static void main(String[] args) {
        int[][] undirectedEdges = {
            {0,1}, {0,2}, {1,3},
            {2,3}, {3,4}, {2,5}
        };
        List<List<Integer>> undirected =
                buildGraph(7, undirectedEdges, false);

        BfsResult fromZero = bfs(undirected, 0);
        System.out.println("undirectedDist=" +
                Arrays.toString(fromZero.distance()));
        System.out.println("pathTo4=" + fromZero.pathTo(4));
        System.out.println("pathTo5=" + fromZero.pathTo(5));
        System.out.println("pathTo6=" + fromZero.pathTo(6));
        System.out.println("pathTo0=" + fromZero.pathTo(0));

        System.out.println("multiSource=" +
                Arrays.toString(multiSourceDistances(
                        undirected, new int[]{1,3})));

        int[][] directedEdges = {
            {0,1}, {1,2}, {2,4},
            {0,3}, {3,4}, {4,5}
        };
        List<List<Integer>> directed =
                buildGraph(6, directedEdges, true);
        BfsResult directedBfs = bfs(directed, 0);
        System.out.println("directedDist=" +
                Arrays.toString(directedBfs.distance()));
        System.out.println("directedPath4=" +
                directedBfs.pathTo(4));
        System.out.println("reverseReach=" +
                bfs(directed, 4).distance()[0]);

        List<List<Integer>> single =
                buildGraph(1, new int[0][2], false);
        System.out.println("singleDist=" +
                Arrays.toString(bfs(single, 0).distance()));

        int[][] duplicateAndLoop = {
            {0,0}, {0,1}, {0,1}
        };
        System.out.println("selfLoopDist=" +
                Arrays.toString(bfs(buildGraph(2,
                        duplicateAndLoop, false), 0).distance()));

        System.out.println("emptyGraphSize=" +
                buildGraph(0, new int[0][2], false).size());

        randomCrossCheck();
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac UnweightedEdgeDistanceDemo.java
java UnweightedEdgeDistanceDemo
~~~

**Đầu ra xác định:**

~~~text
undirectedDist=[0, 1, 1, 2, 3, 2, -1]
pathTo4=[0, 1, 3, 4]
pathTo5=[0, 2, 5]
pathTo6=[]
pathTo0=[0]
multiSource=[1, 0, 1, 0, 1, 2, -1]
directedDist=[0, 1, 2, 1, 2, 3]
directedPath4=[0, 3, 4]
reverseReach=-1
singleDist=[0]
selfLoopDist=[0, 1]
emptyGraphSize=0
randomCrossCheck=PASS (200 graphs)
~~~

### Đọc kết quả từ chương trình

**Đồ thị vô hướng:** nguồn 0 có khoảng cách `[0,1,1,2,3,2,-1]`. Đỉnh 4 cách 3 cạnh, đỉnh 5 cách 2 cạnh. Đỉnh 6 cô lập nên không thể tới từ 0. Danh sách `pathTo0=[0]` có **một đỉnh và không cạnh**.

**Nhiều nguồn:** đưa đỉnh 1 và 3 vào queue cùng khoảng cách 0, kết quả `[1,0,1,0,1,2,-1]`. Khoảng cách của đỉnh 5 là 2 vì nó có đường ngắn nhất đến nguồn 3 là `5–2–3`.

**Đồ thị có hướng:** từ 0 có thể tới 4 qua `0→3→4` trong 2 cạnh. Nhưng từ 4 không có đường quay về 0 theo các cung đã khai báo, nên `reverseReach=-1`.

**Khuyên và cạnh song song:** đồ thị hai đỉnh có khuyên `0→0` và hai cạnh lặp `0–1`, khoảng cách từ 0 vẫn là `[0,1]`. Bởi vì BFS đánh dấu khi enqueue, các cạnh lặp không đưa đỉnh 1 vào queue nhiều lần.

**Đồ thị rỗng:** `buildGraph(0,...)` tạo được danh sách kề rỗng; nhưng không có đỉnh nguồn hợp lệ để gọi `bfs`. Vì vậy ví dụ chỉ in kích thước 0, không cố BFS từ 0 trên đồ thị rỗng.

**Kiểm thử 200 đồ thị:** với mỗi đồ thị nhỏ, chương trình so sánh khoảng cách BFS với phép nới lỏng cạnh theo từng vòng, rồi kiểm tra rằng mỗi đường `pathTo` dùng toàn các cạnh có thật và có số cạnh đúng bằng khoảng cách. Nếu bất kỳ kiểm tra nào sai, chương trình ném `AssertionError` trước khi in PASS.

## 9. Vì sao cách tham chiếu bằng n-1 vòng nới lỏng đúng?

Trong đồ thị mà mỗi cạnh có chi phí **1 dương**, một đường đi ngắn nhất có thể chọn là **đường đi đơn**, không lặp đỉnh. Nếu có đoạn lặp thành chu trình, bỏ chu trình sẽ giảm số cạnh, nên đường đi lặp không thể là ngắn nhất.

Một đường đi đơn trên n đỉnh dùng tối đa **n-1 cạnh**. Nếu đặt `d_0[source]=0`, các đỉnh khác vô cùng và cập nhật đồng thời:

~~~text
d_next[v] = min(
    d_previous[v],
    d_previous[u] + 1 for every edge u -> v
)
~~~

thì sau k vòng, `d_k[v]` là độ dài nhỏ nhất trong tất cả đường đi từ nguồn đến v dùng **không quá k cạnh**. Vậy n-1 vòng đủ tìm đường ngắn nhất tới mọi đỉnh có thể tới.

Phương pháp tham chiếu trên phục vụ **kiểm tra kết quả**. Nếu mỗi vòng quét tất cả n đỉnh và m cạnh, thời gian có thể là **O(n(n+m))**, chậm hơn BFS O(n+m), nhưng với đồ thị nhỏ nó là một oracle thuận tiện có cách xử lý khác.

**Lưu ý:** một chương trình BFS đúng vẫn cần chứng minh độ dài lớp và đánh dấu khi phát hiện. Hai thuật toán cùng in một kết quả trên vài đồ thị chưa phải là chứng minh tính đúng tổng quát.

## 10. Độ phức tạp và cấu trúc lưu trữ

Gọi `V` là số đỉnh, `E` là số cạnh/cung. Với danh sách kề:

- Khởi tạo `distance` và `parent`: **O(V)**.
- Mỗi đỉnh được thêm queue và lấy ra **nhiều nhất một lần**: O(V).
- Mỗi cạnh có hướng được xét trong danh sách kề một lần; mỗi cạnh vô hướng xuất hiện hai lần, nhưng hằng số 2 không đổi bậc: **O(E)**.
- Tổng thời gian BFS: **O(V+E)**.
- Bộ nhớ queue, distance, parent: **O(V)** bổ sung.
- Danh sách kề của đồ thị: **O(V+E)** bộ nhớ.

**Không nhầm số cạnh của đường đi với số cạnh toàn đồ thị.** Một đường đi dài k cạnh, nhưng BFS có thể cần duyệt gần như mọi đỉnh/cạnh có thể tới để tính khoảng cách cho **tất cả** các đỉnh.

**Dừng sớm khi chỉ hỏi một đích:** nếu chỉ cần khoảng cách hoặc một đường đi từ s đến t, có thể dừng **ngay khi t được phát hiện lần đầu** sau khi gán `distance[t]` và `parent[t]` (hoặc khi lấy t ra khỏi queue). Tính đúng vẫn giữ nhờ định lý khám phá lần đầu. Nhưng các khoảng cách của những đỉnh khác **chưa được duyệt hết** không còn là kết quả BFS đầy đủ.

**Dừng sớm không giúp bài đếm nhiều đường ngắn nhất theo cách ngây thơ:** nếu phải đếm mọi đường đi ngắn nhất tới đích, cần xử lý đủ các cạnh từ lớp trước đích để cộng tất cả đóng góp; dừng ngay ở lần đầu gặp đích có thể bỏ sót những đường khác cùng độ dài.

### Danh sách kề so với ma trận kề

Nếu biểu diễn bằng **ma trận kề V×V**, mỗi lần lấy một đỉnh u khỏi queue phải duyệt mọi cột v để tìm hàng xóm, nên tổng thời gian thường **O(V²)**, bộ nhớ ma trận **O(V²)**. Điều này có thể phù hợp với đồ thị rất dày hoặc khi đề đã cho ma trận, nhưng với đồ thị thưa, danh sách kề thường tiết kiệm hơn.

Nếu đồ thị có `V=10^5` đỉnh và `E≈V` cạnh, ma trận kề V² là không thực tế, trong khi danh sách kề có thể vừa bộ nhớ. Cần chọn cấu trúc từ kích thước đầu vào, không chỉ từ thuật toán.

## 11. BFS so với DFS, Dijkstra và 0-1 BFS

### DFS không bảo đảm khoảng cách ở lần gặp đầu

DFS (Depth-First Search) đi sâu theo một nhánh trước khi quay lại. Nó thích hợp để kiểm tra liên thông, duyệt thành phần, phát hiện chu trình theo điều kiện, hoặc khám phá cấu trúc, nhưng **DFS thông thường không bảo đảm lần đầu tới một đỉnh là đường ngắn nhất**.

Xét đồ thị **có hướng**:

~~~text
0 -> 1 -> 2 -> 3
 \-------------> 3
~~~

Nếu DFS xét đỉnh 1 trước đỉnh 3 và đánh dấu mỗi đỉnh khi gặp, nó có thể lần đầu gán cho 3 độ dài **3** theo đường `0→1→2→3`. Nhưng có cạnh trực tiếp `0→3`, nên khoảng cách thật là **1**. BFS phát hiện đỉnh 3 từ lớp 0 và gán ngay 1.

**Không có nghĩa DFS tuyệt đối không thể dùng để tìm đường đi ngắn nhất.** Một cách vét cạn bằng DFS xét mọi đường đơn hoặc cập nhật/relax khoảng cách khi tìm đường ngắn hơn vẫn có thể trả đáp án đúng, nhưng không có đặc tính tuyến tính đơn giản của BFS.

### Khi nào dùng thuật toán nào?

| Loại cạnh/mục tiêu | Thuật toán thường phù hợp | Lý do |
| --- | --- | --- |
| Mỗi cạnh tính đúng 1 bước | **BFS** | Duyệt theo lớp số cạnh, O(V+E). |
| Mỗi cạnh có trọng số dương hoặc không âm | **Dijkstra** (khi cần tổng trọng số) | Hàng đợi ưu tiên theo tổng chi phí tạm thời, không theo số cạnh. |
| Trọng số chỉ thuộc {0,1} | **0-1 BFS** | Dùng deque, cạnh 0 thêm đầu và cạnh 1 thêm cuối, thường O(V+E). |
| Có cạnh âm, không có chu trình âm ảnh hưởng bài toán | **Bellman–Ford** hoặc thuật toán phù hợp | Dijkstra không bảo đảm khi có trọng số âm. |
| Chỉ cần xét tồn tại đường đi | **BFS hoặc DFS** | Không nhất thiết cần độ dài ngắn nhất. |
| Cạnh không trọng số nhưng nhiều nguồn | **Multi-source BFS** | Khởi tạo mọi nguồn ở lớp 0, một lần duyệt. |

**Bài toán “ít cạnh nhất” và “chi phí nhỏ nhất” khác nhau:** nếu các cạnh có trọng số, đường đi dùng ít cạnh có thể đắt hơn đường đi dùng nhiều cạnh. Nếu đề hỏi **ít cạnh nhất bất kể trọng số**, BFS theo số cạnh vẫn giải mục tiêu đó, với điều kiện mọi cạnh chỉ được đếm là một bước; còn nếu hỏi **tổng trọng số nhỏ nhất**, phải dùng thuật toán thích hợp cho trọng số.

### Phản ví dụ về trọng số

~~~text
s -> t          weight = 100
s -> a -> t     weights = 1 and 1
~~~

Theo **số cạnh**, đường `s→t` dài 1 nên tốt hơn đường qua a dài 2. Theo **tổng chi phí**, đường qua a tốn 2 nên tốt hơn cạnh trực tiếp tốn 100. Cùng một đồ thị, hai hàm mục tiêu khác nhau sẽ có hai đáp án khác nhau.

## 12. Từ lưới và mê cung sang đồ thị không trọng số

BFS rất phổ biến với bàn cờ, mê cung, bản đồ ô vuông:

- Mỗi **ô đi được** là một đỉnh.
- Hai ô có cạnh nối nếu được phép đi trực tiếp từ ô này sang ô kia bằng **một bước**.
- Nếu chỉ cho phép đi lên, xuống, trái, phải, một ô có tối đa 4 hàng xóm.
- Nếu ô là tường, không đưa ô đó vào tập đi được hoặc không sinh cạnh từ/đến ô tường.

Giả sử có R hàng, C cột, ô `(r,c)` được ánh xạ thành ID `r*C+c`. Các hướng di chuyển bốn phía:

~~~text
dr = [-1, 1, 0, 0]
dc = [0, 0, -1, 1]

For each direction k:
    nr = r + dr[k]
    nc = c + dc[k]
    accept if inside grid and not blocked[nr][nc]
~~~

Sau đó dùng BFS từ ô xuất phát. `distance[r][c]` là **số bước di chuyển ít nhất** đến ô ấy, vì mỗi bước đi tới ô kề là **một cạnh**.

**Ví dụ:**

~~~text
S . . #
# # . .
. . . T
~~~

Với luật đi bốn hướng, phải kiểm tra đường đi thực tế; việc trông thấy T “gần” S theo khoảng cách hình học không bảo đảm đi tới được nếu có tường. BFS tự tìm số bước ít nhất quanh các ô chặn.

### Các bẫy mô hình hóa trên lưới

- Nếu được đi **chéo**, phải thêm cạnh theo các hướng ấy; nếu không, BFS bốn hướng sẽ trả khoảng cách của một bài toán khác.
- Nếu mỗi ô có **chi phí di chuyển khác nhau**, BFS tính **số bước**, không phải tổng chi phí.
- Nếu ô bắt đầu hoặc ô đích bị chặn, cần quy định trả “không tới được” hoặc lỗi đầu vào theo đề.
- Nếu có **cổng dịch chuyển** từ ô A sang B dùng đúng một thao tác, thêm một cạnh A→B; nếu dịch chuyển miễn phí, đó là cạnh trọng số 0 và bài toán tổng chi phí có thể cần 0-1 BFS.
- Nếu trạng thái di chuyển phụ thuộc số chìa khóa nhặt được, cổng đã mở hay hướng đang quay, **đỉnh trạng thái không chỉ là (r,c)**. Cần dùng `(r,c,mask)` hoặc thông tin tương đương để phân biệt khả năng tiếp tục.

Với R×C ô và số hướng cố định, BFS có thể chạy trong **O(RC)** thời gian và bộ nhớ nếu mỗi ô/trạng thái hợp lệ được xét một số lần hằng định.

## 13. Các trường hợp đặc biệt cần xử lý

### 13.1. Đồ thị không liên thông

BFS từ s chỉ thăm **thành phần liên thông chứa s** trong đồ thị vô hướng, hoặc những đỉnh **có thể tới theo hướng cung** từ s trong đồ thị có hướng. Các đỉnh khác giữ `distance=-1`. Không tự chuyển -1 thành 0: 0 chỉ dành cho nguồn và những đỉnh được coi là nguồn trong multi-source BFS.

Nếu muốn duyệt **mọi thành phần**, có thể khởi tạo BFS mới tại mỗi đỉnh chưa được thăm. Nhưng như vậy không còn là **một mảng khoảng cách từ nguồn ban đầu duy nhất**; phải phân biệt mục tiêu tính thành phần với mục tiêu shortest path.

### 13.2. Đồ thị có khuyên hoặc nhiều cạnh trùng

**Khuyên (self-loop)** `u→u` không cải thiện khoảng cách vì `distance[u]` đã biết, nên BFS bỏ qua. **Cạnh song song** dẫn đến cùng hàng xóm nhiều lần, nhưng vì đánh dấu khi enqueue, một đỉnh vẫn chỉ được thêm queue một lần. Khoảng cách ngắn nhất **không thay đổi**.

Nếu chuyển sang bài **đếm số đường đi**, cạnh song song có thể làm số “đường theo cạnh” khác số “dãy đỉnh” như đã nói; cần định nghĩa thống nhất.

### 13.3. Đồ thị một đỉnh và đồ thị rỗng

Với `V=1`, nếu nguồn là đỉnh duy nhất 0, mảng khoảng cách là `[0]` ngay cả khi không có cạnh.

Với `V=0`, không tồn tại **chỉ số nguồn hợp lệ**. Hàm tạo đồ thị của ví dụ có thể trả danh sách kề rỗng, nhưng `bfs(graph,0)` sẽ ném lỗi đầu vào. Nếu bài cho phép “đồ thị rỗng”, hãy quyết định rõ API muốn trả mảng rỗng hay từ chối truy vấn nguồn; đừng vô tình đọc `distance[0]` khi mảng rỗng.

### 13.4. Nhiều cạnh, thứ tự duyệt khác nhau

Thứ tự liệt kê hàng xóm có thể làm thay đổi `parent` và đường đi được chọn trong trường hợp hòa. Nó **không được** làm thay đổi `distance`. Nếu một thay đổi thứ tự làm đổi khoảng cách, thường có lỗi dùng queue, đánh dấu hoặc cập nhật sai.

### 13.5. Đích được phát hiện sớm

Nếu chỉ hỏi khoảng cách từ s đến t, ngay khi `distance[t]` được gán lần đầu, giá trị đã tối ưu. Có thể kết thúc sớm để tiết kiệm thời gian. Nhưng nếu vẫn trả toàn bộ mảng khoảng cách như thể BFS đã hoàn tất, sẽ có các ô -1 của những đỉnh có thể tới nhưng chưa được duyệt; phải nói rõ kết quả khi dừng sớm **chỉ có giá trị cho đích được hỏi**.

### 13.6. Số đỉnh lớn

Trong một đồ thị có V đỉnh, đường đi ngắn nhất không lặp đỉnh nên có nhiều nhất V-1 cạnh. `int` đủ lưu khoảng cách khi V nằm trong phạm vi một mảng Java bình thường, nhưng bộ nhớ cho adjacency bằng danh sách các đối tượng Java có thể lớn. Với dữ liệu rất lớn có thể dùng mảng `head/to/next` hoặc CSR để tiết kiệm đối tượng; thuật toán BFS và tính đúng không thay đổi.

## 14. Sai lầm phổ biến

1. **Dùng DFS đánh dấu một lần để tìm đường ngắn nhất** trên đồ thị tổng quát; lần gặp đầu của DFS không bảo đảm ít cạnh nhất.
2. **Dùng stack LIFO thay queue FIFO**, phá thứ tự lớp khoảng cách.
3. **Đánh dấu visited khi lấy khỏi queue** rồi đẩy trùng nhiều lần, dễ tăng chi phí và rối parent.
4. **Gán `distance[v]` lại khi gặp cạnh khác**, dù v đã được phát hiện bằng đường ngắn nhất.
5. **Khởi tạo mọi khoảng cách bằng 0** làm không phân biệt nguồn với đỉnh chưa tới.
6. **Quên đặt `distance[source]=0`** trước khi enqueue.
7. **Nhầm độ dài đường đi là số đỉnh** thay vì số cạnh.
8. **Ghi khoảng cách của đỉnh v bằng `distance[u]`** thay vì `distance[u]+1`.
9. **Xem đồ thị có hướng là vô hướng**, tự thêm cạnh ngược không tồn tại.
10. **Quên thêm chiều ngược** khi đề là đồ thị vô hướng.
11. **Dừng quá sớm khi vẫn cần khoảng cách đến mọi đỉnh**, khiến kết quả còn -1 sai.
12. **Trả danh sách rỗng cho đường đi nguồn→chính nó**, nhầm với đỉnh không thể tới.
13. **Phục dựng từ parent nhưng không đảo ngược**, làm đường đi đi từ đích ngược về nguồn.
14. **Không kiểm tra `distance[target]==-1` trước phục dựng**, dẫn đến coi đỉnh unreachable như một đường đi.
15. **Dùng mảng visited toàn cục không reset** khi chạy BFS cho một nguồn mới.
16. **Dùng `ArrayList.remove(0)` làm queue** trên dữ liệu lớn, tốn chi phí dời phần tử.
17. **Nghĩ BFS luôn giải được mọi bài shortest path có trọng số**, kể cả cạnh 0 hoặc 100.
18. **Nhầm 0-1 BFS với BFS thường** khi có cạnh trọng số 0.
19. **Tính khoảng cách trên lưới nhưng quên ô cấm hoặc hướng di chuyển**, giải sai mô hình.
20. **Chạy BFS riêng từ mọi nguồn trong bài tìm nguồn gần nhất** mà bỏ qua multi-source BFS một lượt.
21. **Cho rằng `parent` luôn duy nhất**; nhiều đường ngắn nhất có thể tồn tại.
22. **Nhầm số đường đi ngắn nhất với một đường đã phục dựng**, vì chỉ lưu parent không đếm tất cả đường.
23. **Quên kiểm tra chỉ số đỉnh hợp lệ** khi xây danh sách kề.
24. **Phân tích thời gian BFS là O(V²) cho mọi kiểu lưu trữ**, bỏ qua lợi ích O(V+E) của danh sách kề.
25. **Dùng khoảng cách Manhattan làm kết quả mê cung có tường**, trong khi đường cần vòng tránh chướng ngại.
26. **Thêm siêu nguồn bằng cạnh một bước rồi không trừ điều chỉnh** trong bài khoảng cách tới nguồn gần nhất, làm kết quả lệch.
27. **Không xét trường hợp nguồn trùng đích**, vì đáp án phải là 0 ngay lập tức.
28. **Nhầm trọng số ghi trên cạnh với yêu cầu ít cạnh nhất**; thuật toán phải giải đúng hàm mục tiêu thực tế.

## 15. Bài tập tự luyện có lời giải

**Bài 1.** Đường `0→2→5→7` có bao nhiêu cạnh? **Đáp án:** 3 cạnh, dù có 4 đỉnh.

**Bài 2.** `dist(s,s)` bằng bao nhiêu nếu s hợp lệ? **Đáp án:** 0, vì có đường đi rỗng không đi qua cạnh nào.

**Bài 3.** Một đỉnh t không thể tới từ s thì nên lưu gì? **Đáp án:** quy ước `distance[t]=-1`; theo lý thuyết khoảng cách vô cùng/không xác định hữu hạn.

**Bài 4.** Đồ thị vô hướng có cạnh `(0,1),(1,2),(0,2)`. Khoảng cách từ 0 tới 2 là bao nhiêu? **Đáp án:** 1 nhờ cạnh trực tiếp `0–2`, không phải 2 qua đỉnh 1.

**Bài 5.** Đồ thị có hướng có cung `0→1`, không có cung `1→0`. Từ 1 tới 0 có đi được không? **Đáp án:** không, nếu không còn cung/đường khác dẫn về 0.

**Bài 6.** Vì sao BFS cần FIFO? **Đáp án:** để phát hiện/xử lý theo các lớp khoảng cách không giảm, bảo đảm lần gặp đầu là đường ngắn nhất.

**Bài 7.** Ở ví dụ 7 đỉnh, từ nguồn 0, `distance[4]` bằng bao nhiêu? **Đáp án:** 3; một đường đi là `0→1→3→4`.

**Bài 8.** Trong cùng ví dụ, tại sao `parent[3]` có thể là 1 hoặc 2? **Đáp án:** cả hai ở khoảng cách 1 từ nguồn và đều kề 3; đường tới 3 qua mỗi đỉnh đều dài 2 cạnh.

**Bài 9.** Nếu `parent[4]=3, parent[3]=1, parent[1]=0`, phục dựng đường đi từ 0 đến 4 thế nào? **Đáp án:** lần ngược từ 4 có `[4,3,1,0]` rồi đảo thành `[0,1,3,4]`.

**Bài 10.** Có hai nguồn 1 và 3 trong đồ thị ví dụ; khoảng cách của đỉnh 5 tới nguồn gần nhất là bao nhiêu? **Đáp án:** 2 qua `5–2–3`.

**Bài 11.** Multi-source BFS khởi tạo mỗi nguồn với khoảng cách bao nhiêu? **Đáp án:** 0, đồng thời đưa tất cả vào queue ở lớp 0.

**Bài 12.** Với cùng đồ thị, nếu danh sách nguồn rỗng thì mảng khoảng cách là gì? **Đáp án:** tất cả -1 theo quy ước không có nguồn để đi từ đó.

**Bài 13.** Tại sao DFS thăm 3 trước qua `0→1→2→3` có thể sai nếu tồn tại `0→3`? **Đáp án:** DFS gặp 3 ở độ dài 3 trước, còn đường ngắn nhất chỉ 1 cạnh; BFS không mắc lỗi này.

**Bài 14.** Một cạnh trực tiếp s→t có chi phí 100, đường s→a→t có chi phí 1+1. Nếu hỏi **ít cạnh nhất**, chọn gì? **Đáp án:** cạnh trực tiếp, dài 1 cạnh. Nếu hỏi **tổng chi phí nhỏ nhất**, chọn đường qua a với chi phí 2.

**Bài 15.** Đồ thị có khuyên `0→0`, khuyên ấy có làm khoảng cách từ 0 tới 0 bằng 1 không? **Đáp án:** không, khoảng cách vẫn 0 nhờ đường đi rỗng.

**Bài 16.** Nếu chỉ cần khoảng cách tới một đích t, có thể dừng BFS lúc nào? **Đáp án:** ngay khi t được khám phá lần đầu sau khi gán khoảng cách, hoặc khi t được lấy khỏi queue; không được coi các khoảng cách chưa duyệt là hoàn chỉnh.

**Bài 17.** Với danh sách kề có V đỉnh và E cạnh, độ phức tạp BFS là gì? **Đáp án:** O(V+E) thời gian, O(V) bộ nhớ phụ cho queue và mảng trạng thái.

**Bài 18.** Trên lưới R×C, nếu chỉ được đi 4 hướng và có tường, BFS giải bài toán nào? **Đáp án:** số bước di chuyển tối thiểu từ ô nguồn đến mỗi ô có thể tới theo đúng 4 hướng và tường đã cho.

**Bài 19.** Nếu một ô vừa là nguồn vừa là đích và không bị chặn, đường đi có số cạnh bao nhiêu? **Đáp án:** 0.

**Bài 20.** Vì sao `distance[v]` không cần cập nhật lần hai khi tìm thêm một đường tới v? **Đáp án:** BFS khám phá v lần đầu bằng đường ít cạnh nhất nhờ thứ tự lớp; mọi lần phát hiện sau không thể có đường ngắn hơn.

**Bài 21.** Nếu muốn đếm **tất cả** đường đi ngắn nhất, chỉ lưu `parent[v]` có đủ không? **Đáp án:** không. Parent chỉ ghi một đường; cần thêm số cách và cộng đóng góp từ mọi cạnh thuộc lớp đường ngắn nhất.

**Bài 22.** Nếu trọng số cạnh chỉ là 0 và 1, nên dùng thuật toán gì để tìm tổng trọng số nhỏ nhất? **Đáp án:** 0-1 BFS hoặc thuật toán shortest path phù hợp, không áp dụng trực tiếp `dist[v]=dist[u]+1` cho mọi cạnh.

## 16. Checklist triển khai BFS khoảng cách theo số cạnh

1. **Đồ thị có hướng hay vô hướng?** Xây đúng các cạnh được phép đi.
2. **Mục tiêu là ít cạnh nhất hay tổng trọng số nhỏ nhất?** BFS chỉ giải trực tiếp trường hợp mỗi bước tính một đơn vị.
3. **Đỉnh đánh số đúng phạm vi không?** Kiểm tra source, target và mọi đầu mút cạnh.
4. **Đã khởi tạo tất cả `distance=-1`, `parent=-1` chưa?** Nguồn phải có khoảng cách 0.
5. **Hàng đợi có FIFO không?** Dùng `ArrayDeque` hoặc queue phù hợp.
6. **Đã đánh dấu ngay khi enqueue chưa?** Một đỉnh được thêm queue tối đa một lần.
7. **Khi duyệt cạnh `u→v` mới phát hiện, có gán `distance[v]=distance[u]+1` không?**
8. **Có lưu `parent[v]=u` nếu cần phục dựng đường đi?** Có đảo ngược chuỗi parent sau khi lần ngược?
9. **Có phân biệt không thể tới (-1), nguồn→nguồn (0) và các khoảng cách dương không?**
10. **Nếu nhiều nguồn, có khởi tạo mọi nguồn ở khoảng cách 0 trong cùng một BFS không?**
11. **Nếu chỉ cần một đích và dừng sớm, có tránh trình bày mảng khoảng cách còn thiếu như kết quả toàn đồ thị không?**
12. **Trên lưới, có xét chính xác tường, biên, hướng di chuyển, trọng số và các trạng thái phụ không?**
13. **Đã kiểm tra cạnh trùng, khuyên, đồ thị không liên thông, một đỉnh và đồ thị rỗng chưa?**
14. **Đã kiểm tra với ví dụ có nhiều đường ngắn nhất và đồ thị có hướng một chiều chưa?**
15. **Đã chứng minh bất biến lớp và đánh giá O(V+E) khi dùng danh sách kề chưa?**

**Ghi nhớ:** trong đồ thị không trọng số, BFS tìm khoảng cách ngắn nhất theo **số cạnh** nhờ queue FIFO và quy tắc **đánh dấu ngay khi khám phá**. Giá trị `distance[v]` là số bước tối thiểu, `parent[v]` giúp phục dựng một đường đi ngắn nhất, và -1 biểu thị đỉnh không thể tới. Khi mô hình có trọng số khác nhau, hướng di chuyển đặc biệt hoặc trạng thái bổ sung, phải xác định lại bài toán và chọn phương pháp thích hợp thay vì áp dụng BFS một cách máy móc.

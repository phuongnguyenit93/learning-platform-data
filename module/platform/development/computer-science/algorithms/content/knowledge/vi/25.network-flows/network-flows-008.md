# Khôi phục lát cắt từ mạng dư sau khi tìm luồng cực đại

> **Chủ đề:** Computer Science Algorithms → **Luồng mạng** (*Network Flow*).  
> **Đề bài trọng tâm:** Sau khi tìm được một **luồng cực đại** từ nguồn s tới đích t, hãy dùng **mạng dư** (*residual network*) để khôi phục một **lát cắt s–t có dung lượng nhỏ nhất** (*minimum s–t cut*): xác định hai phía đỉnh, các cạnh gốc đi qua lát cắt, tổng dung lượng, và chứng minh vì sao kết quả đúng.  
> **Ngôn ngữ minh họa:** Java 17+, có lệnh `javac/java`, stdout, trường hợp biên và kiểm thử độc lập.

## 1. Kết quả cuối cùng cần lấy ra là gì?

Đầu vào là một mạng luồng có hướng `G=(V,E)`. Mỗi cạnh gốc e=(u,v) có **dung lượng** `c(e)≥0`. Cho nguồn s và đích t **khác nhau**. Giả sử thuật toán max-flow (Ford–Fulkerson, Edmonds–Karp hoặc Dinic) đã chạy xong và cung cấp **mạng dư cuối cùng**.

Đầu ra của bài toán khôi phục min-cut gồm:

1. **Tập S:** tất cả đỉnh **còn đi tới được từ s trong mạng dư cuối** bằng những cung có **dung lượng dư >0**.
2. **Tập T:** `V \ S`. Vì luồng đã cực đại, t **không** tới được từ s trong mạng dư, nên `s∈S`, `t∈T`.
3. **Các cạnh cắt gốc:** tất cả **cạnh gốc có hướng** `(u→v)` thỏa `u∈S` và `v∈T`.
4. **Dung lượng lát cắt:**

   `c(S,T)=Σ_(e gốc: u∈S, v∈T) c(e)`.

5. **Chứng nhận tối ưu:** nếu luồng đã cực đại, `c(S,T)=|f|`, trong đó `|f|` là giá trị luồng cực đại.

Điểm then chốt: **không** chọn ngẫu nhiên những cạnh dư bằng 0 rồi gọi đó là lát cắt. Đầu tiên phải **phân chia đỉnh theo tính tới được trong mạng dư**, sau đó mới lấy **các cạnh ban đầu đi từ S sang T**.

### 1.1. Ví dụ nhanh

Giả sử sau max-flow, s có thể tới các đỉnh 0 và 2 trong mạng dư, nhưng không thể tới 1,3,4,5:

`S={0,2}`, `T={1,3,4,5}`.

Nếu các cạnh gốc đi từ S sang T là `0→1 (8)`, `0→1 (2)` và `2→4 (9)` thì:

`c(S,T)=8+2+9=19`.

Cạnh `0→1` xuất hiện **hai lần** với hai ID khác nhau; cả hai đều phải tính. Nếu luồng cực đại cũng bằng 19, đó là chứng nhận lát cắt nhỏ nhất.

## 2. Phân biệt luồng, dung lượng và dung lượng dư

Với một **cạnh gốc có hướng** `(u,v)`, ký hiệu:

- `c(u,v)`: dung lượng tối đa được phép truyền, **không âm**.
- `f(u,v)`: lượng luồng trên cạnh gốc, thoả `0≤f(u,v)≤c(u,v)`.
- `r_forward(u,v)=c(u,v)−f(u,v)`: **dung lượng dư xuôi** trên cạnh đó.
- `r_backward(v,u)=f(u,v)`: **dung lượng dư ngược** cho phép hủy bớt luồng đã gửi trước.

Một cạnh gốc thông thường tạo **hai cung trong mạng dư**:

```text
Cạnh gốc u --c--> v

Cung dư xuôi:  u --(c-f)--> v
Cung dư ngược: v --(f)----> u
```

Chỉ những cung dư có **residual capacity >0** mới được phép đi qua khi tìm đường tăng luồng và khi khôi phục S.

**Quan trọng:** cung dư ngược **không phải** một cạnh gốc bổ sung với dung lượng mới. Nó là thao tác đảo một phần luồng đã đi trên cạnh tương ứng.

### 2.1. Vì sao cần cung ngược?

Một đường tăng trước đó có thể dùng cạnh `u→v`. Về sau, ta phát hiện muốn đi theo tuyến khác thì phải giảm bớt f trên cạnh ấy. Cung dư `v→u` có dung lượng f cho phép gửi luồng “ngược” để **hủy** phần luồng cũ và chuyển sang đường mới.

Không duy trì cung ngược sẽ khiến thuật toán dựa trên đường tăng có thể **dừng sai** dù còn khả năng cải thiện luồng.

### 2.2. Hai cạnh gốc ngược chiều là hai đối tượng khác nhau

Nếu đầu vào có **hai cạnh gốc** `u→v` và `v→u`, mỗi cạnh gốc có **cặp cung dư riêng**. Không được trộn lẫn cung dư ngược của cạnh thứ nhất với cung dư xuôi gốc của cạnh thứ hai.

Trong biểu diễn bằng adjacency list, nên tạo **hai đối tượng Edge** cho mỗi cạnh gốc và lưu chỉ số `reverseIndex` trỏ chính xác tới cung đảo tương ứng.

### 2.3. Đối với cạnh song song

Nếu có hai cạnh gốc `u→v` với dung lượng lần lượt 8 và 2, ta có thể:

- Giữ **hai ID và hai cặp cung dư**, để in từng cạnh cắt chính xác.
- Hoặc gộp dung lượng thành 10 **chỉ khi đề không yêu cầu truy xuất ID cạnh** và mô hình cho phép tổng hợp.

Trong chương trình minh họa, **giữ nguyên ID cạnh gốc**, vì bài này yêu cầu **khôi phục chính xác danh sách cạnh cắt**.

## 3. Luồng hợp lệ và giá trị luồng

Luồng hợp lệ thỏa ba loại ràng buộc:

1. **Giới hạn dung lượng:** `0≤f(e)≤c(e)` với mọi cạnh gốc e.
2. **Bảo toàn luồng:** với mọi đỉnh `v∉{s,t}`, tổng luồng đi vào v bằng tổng luồng đi ra v.
3. **Giá trị:** `|f|` bằng tổng luồng rời s trừ tổng luồng vào s, đồng thời bằng tổng luồng vào t trừ tổng luồng rời t.

Trong ví dụ không có cạnh quay về s hoặc rời t, ta thường tính `|f|` đơn giản là tổng f trên các cạnh gốc đi ra s.

### 3.1. Giá trị lát cắt

Một **lát cắt s–t** là một phân hoạch `(S,T)` sao cho:

`S∪T=V`, `S∩T=∅`, `s∈S`, `t∈T`.

Dung lượng của lát cắt **có hướng** là:

`c(S,T)=Σ_(u∈S,v∈T) c(u,v)`.

**Chỉ cộng cạnh gốc đi từ S sang T.** Cạnh gốc đi từ T về S **không** cộng vào dung lượng cắt. Cạnh có hai đầu cùng phía cũng không cộng. Self-loop không cắt qua phân hoạch nào.

Với hai cạnh song song, cộng cả hai dung lượng; với cạnh có dung lượng 0, cộng 0 (nó có thể nằm trong danh sách cạnh qua cut về mặt cấu trúc).

### 3.2. Giới hạn trên từ mọi lát cắt

Theo bảo toàn luồng, với mọi lát cắt `(S,T)`:

`|f| = f(S,T) − f(T,S)`,

trong đó `f(S,T)` là tổng luồng trên các cạnh gốc từ S sang T, `f(T,S)` là tổng luồng gốc theo hướng ngược lại.

Vì `f(S,T)≤c(S,T)` và `f(T,S)≥0`, suy ra:

`|f| ≤ c(S,T)`.

Vậy **mọi lát cắt** đều cho một **cận trên** của giá trị luồng hợp lệ. Nếu ta tìm được một lát cắt có dung lượng **bằng** giá trị luồng, đã chứng minh cả luồng cực đại lẫn lát cắt nhỏ nhất.

## 4. Thuật toán khôi phục lát cắt từ mạng dư

Giả sử đã chạy max-flow đúng cho s,t và giữ được đồ thị dư cuối cùng.

### 4.1. Pseudocode

```text
recoverMinCut(residualGraph, originalEdges, s, t):
    visited[v] = false với mọi đỉnh v
    queue = FIFO queue
    visited[s] = true
    enqueue(s)

    while queue không rỗng:
        u = dequeue()
        for mỗi CUNG DƯ u->v có residual > 0:
            if !visited[v]:
                visited[v] = true
                enqueue(v)

    S = {v | visited[v] == true}
    T = {v | visited[v] == false}

    if visited[t]:
        báo: chưa thể xác nhận max-flow đã hoàn tất

    cutEdges = []
    capacity = 0
    for mỗi CẠNH GỐC e=(u,v,c):
        if visited[u] && !visited[v]:
            cutEdges.add(e)
            capacity += c   // cộng an toàn, tránh tràn số

    return S, T, cutEdges, capacity
```

### 4.2. Tại sao `visited` đánh dấu khi enqueue?

Nếu nhiều cung dư đi tới cùng v, đánh dấu ngay khi enqueue để v vào queue **tối đa một lần**; tránh enqueue trùng lặp làm chậm hoặc tốn bộ nhớ.

Thuật toán chỉ cần xét **khả năng tới được**, không tối ưu số cạnh hay tổng trọng số trên mạng dư. Dùng BFS hoặc DFS đều đúng nếu chỉ đi qua cung `residual>0`.

### 4.3. Phân biệt hai lần duyệt

- **Duyệt 1:** duyệt **các cung dư** có residual>0 để tìm `S`.
- **Duyệt 2:** duyệt **các cạnh gốc** và kiểm `inS[u] && !inS[v]` để xác định cạnh cắt và cộng **dung lượng gốc**.

Không thay lần duyệt 2 bằng “in mọi cung dư đang có residual0”. Nhiều cạnh bão hòa nằm **nội bộ S hoặc nội bộ T**, và chúng không thuộc lát cắt đã khôi phục.

### 4.4. Độ phức tạp của riêng bước khôi phục

Cho V đỉnh, E cạnh gốc; mạng dư có tối đa khoảng `2E` cung nếu biểu diễn mỗi cạnh gốc bằng cặp cung xuôi/ngược:

- BFS/DFS: `O(V+E)`.
- Quét các cạnh gốc để lấy cut edges: `O(E)`.
- Tổng thời gian sau khi max-flow đã chạy: **`O(V+E)`**.
- Bộ nhớ phụ: `O(V)` cho visited và queue; lưu danh sách cạnh cắt có thể thêm `O(E)`.

Đây là **chi phí khôi phục min-cut**, không phải chi phí chạy max-flow. Ví dụ Dinic tổng quát có cận worst-case `O(V²E)` trước đó.

## 5. Chứng minh lát cắt tìm được là nhỏ nhất

Đặt `S` là tập các đỉnh **tới được từ s** trong mạng dư cuối cùng; `T=V\S`.

### 5.1. Nguồn và đích nằm khác phía

Hiển nhiên `s∈S` vì đường dài 0 đi từ s tới s.

Khi luồng đã cực đại, **không còn đường tăng luồng** từ s tới t trong mạng dư (định lý đường tăng của Ford–Fulkerson). Vì vậy `t∉S` và `t∈T`. `(S,T)` thực sự là một lát cắt s–t.

Nếu chạy BFS dư mà **vẫn thấy t**, ta chưa thể khẳng định luồng cực đại; có thể còn đường tăng hoặc dữ liệu residual bị cập nhật sai.

### 5.2. Mọi cạnh gốc đi S→T đều bão hòa

Xét cạnh gốc e=(u→v) với `u∈S`, `v∈T`.

Nếu `c(e)-f(e)>0`, ta có một **cung dư xuôi** từ u sang v với residual>0. Vì u tới được từ s, suy ra v cũng tới được từ s, mâu thuẫn v∈T.

Do đó:

`c(e)−f(e)=0` ⇒ **`f(e)=c(e)`**.

Tức mọi cạnh gốc đi qua lát cắt **từ S sang T đã bão hòa**. Điều này đúng cả khi c(e)=0, vì f(e)=0.

### 5.3. Không có luồng dương trên cạnh gốc đi T→S

Xét cạnh gốc e=(u→v) với `u∈T`, `v∈S`.

Nếu `f(e)>0`, trong mạng dư tồn tại cung **ngược** `v→u` có dung lượng dư f(e)>0. Vì v∈S, suy ra u cũng tới được từ s; mâu thuẫn u∈T.

Do đó:

`f(e)=0`

với mọi cạnh gốc đi từ T về S.

### 5.4. Suy ra đẳng thức max-flow min-cut

Từ bảo toàn luồng:

`|f| = f(S,T)−f(T,S)`.

Vì mọi cạnh S→T bão hòa, `f(S,T)=c(S,T)`; vì mọi cạnh T→S có f=0:

`|f| = c(S,T)−0 = c(S,T)`.

Mặt khác, mọi luồng hợp lệ ≤ dung lượng **mọi** cut. Vậy luồng f đạt cận trên của một cut và cut này đạt cận dưới của mọi cut:

**`maxFlow(s,t) = minCutCapacity(s,t)`**.

Kết luận: chính lát cắt `(S,T)` thu được từ **tính tới được trong mạng dư** là một **min-cut**, không chỉ là một cut bất kỳ.

### 5.5. Chứng nhận dễ kiểm chứng

Để kiểm chứng kết quả độc lập, chỉ cần:

- f hợp lệ: không vượt dung lượng và bảo toàn tại các đỉnh trung gian.
- S chứa s, không chứa t.
- Mọi cạnh gốc S→T bão hòa.
- Mọi cạnh gốc T→S có luồng 0.
- Tổng capacity của S→T bằng giá trị f.

Những điều kiện trên là một **chứng chỉ tối ưu** mà không cần tin vào hành vi nội bộ của thuật toán đã tạo f.

## 6. Ví dụ có cạnh song song, self-loop và cạnh ngược chiều

Xét mạng **có hướng** 6 đỉnh, `s=0`, `t=5`. Mỗi cạnh là một dòng input có ID.

| ID | Cạnh gốc | Capacity | Ý nghĩa |
|---:|---|---:|---|
| 0 | 0→1 | 8 | Cạnh song song số 1 |
| 1 | 0→1 | 2 | Cạnh song song số 2 |
| 2 | 0→2 | 10 | Đường sang nhánh 2 |
| 3 | 1→2 | 2 | Cạnh hướng **T→S** theo min-cut cuối |
| 4 | 1→3 | 4 | Nhánh giữa |
| 5 | 1→4 | 8 | Nhánh giữa |
| 6 | 2→4 | 9 | Cạnh qua cut |
| 7 | 4→3 | 6 | Chuyển nhánh |
| 8 | 3→5 | 10 | Đi vào đích |
| 9 | 4→5 | 10 | Đi vào đích |
| 10 | 2→2 | 7 | Self-loop, không giúp truyền luồng s–t |
| 11 | 3→4 | 0 | Cạnh gốc dung lượng 0 |

Một max-flow hợp lệ có giá trị **19**, ví dụ các luồng trên cạnh gốc ID 0..9 lần lượt:

`[8,2,9,0,4,6,9,5,9,10]`.

Kiểm bảo toàn:

- Tại đỉnh 1: vào 8+2=10; ra 0+4+6=10.
- Tại đỉnh 2: vào 9+0=9; ra 9.
- Tại đỉnh 3: vào 4+5=9; ra 9.
- Tại đỉnh 4: vào 6+9=15; ra 5+10=15.
- Đích 5 nhận 9+10=19.

Cạnh 0→2 vẫn còn dung lượng dư xuôi `10−9=1`, nên s còn tới được đỉnh 2. Nhưng các cạnh `0→1` (cả ID 0 và 1) và `2→4` đều bão hòa, nên không thể thoát từ `{0,2}` sang các đỉnh còn lại qua cung dư dương.

### 6.1. Phân hoạch sau BFS trên mạng dư

`S={0,2}`.

`T={1,3,4,5}`.

Các cạnh gốc **S→T**:

```text
ID 0: 0→1, capacity 8,  flow 8, residual xuôi 0
ID 1: 0→1, capacity 2,  flow 2, residual xuôi 0
ID 6: 2→4, capacity 9,  flow 9, residual xuôi 0
```

Dung lượng cắt:

`8+2+9 = 19`.

Cạnh gốc **1→2** có capacity 2 và nằm theo hướng **T→S**; nó **không** được tính vào c(S,T). Ở max-flow minh họa, f(1→2)=0, đúng điều kiện chứng nhận. Self-loop 2→2 nằm hoàn toàn trong S; cạnh 3→4 dung lượng 0 nằm trong T; cả hai không góp dung lượng cut.

### 6.2. Đối chiếu với giá trị max-flow

Thuật toán tìm max-flow cho `|f|=19`. Cut được khôi phục có capacity 19:

`|f| = c(S,T) = 19`.

Bởi vì không luồng nào lớn hơn dung lượng một cut, đây là min-cut và 19 là max-flow. Có thể kiểm tra bằng vét cạn các phân hoạch s–t: với ví dụ này có **đúng một min-cut**, phía nguồn là `{0,2}`.

## 7. Java 17 — Dinic + khôi phục S/T và danh sách cạnh gốc qua cut

Đây là chương trình **độc lập**. Nó:

- Dùng Dinic tìm max-flow trong một mạng có hướng.
- Lưu đúng từng **cạnh gốc và ID**, kể cả cạnh song song.
- Định nghĩa hai cung dư có `reverseIndex` riêng cho mỗi cạnh gốc.
- Với self-loop, **giữ trong danh sách input gốc nhưng không thêm cung vào mạng dư**, vì vòng tự thân không giúp s–t flow/cut.
- Sau max-flow, BFS trên các cung dư `residual>0` để lấy S.
- Duyệt cạnh gốc S→T để cộng **capacity gốc**, kiểm tất cả bão hòa, đồng thời kiểm tổng luồng trên cạnh gốc T→S bằng 0.
- Không nhập nhằng giữa cung dư ngược và cạnh gốc ngược chiều.

Lưu thành **ResidualMinCutDinicDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ResidualMinCutDinicDemo {
    static final class Arc {
        final int to;
        final int reverseIndex;
        long residual;

        Arc(int to, int reverseIndex, long residual) {
            this.to = to;
            this.reverseIndex = reverseIndex;
            this.residual = residual;
        }
    }

    record Original(int id, int from, int to,
                    long capacity, Arc forward) {}

    record Cut(List<Integer> sourceSide, List<Integer> sinkSide,
               List<Original> crossing, long capacity,
               long reverseCrossingFlow, boolean[] inS) {}

    static final class Network {
        final int n;
        final List<List<Arc>> graph;
        final List<Original> originals;

        Network(int n) {
            if (n < 1) {
                throw new IllegalArgumentException("Need at least one vertex");
            }
            this.n = n;
            graph = new ArrayList<>();
            originals = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                graph.add(new ArrayList<>());
            }
        }

        void add(int from, int to, long capacity) {
            if (from < 0 || from >= n || to < 0 || to >= n
                    || capacity < 0) {
                throw new IllegalArgumentException("Invalid edge");
            }

            int id = originals.size();
            if (from == to) {
                // Self-loop không giúp truyền luồng s-t hoặc tạo cut.
                originals.add(new Original(id, from, to, capacity, null));
                return;
            }

            // Hai chỉ số rev độc lập, kể cả khi input có cạnh song song.
            Arc forward = new Arc(to, graph.get(to).size(), capacity);
            Arc backward = new Arc(from, graph.get(from).size(), 0L);
            graph.get(from).add(forward);
            graph.get(to).add(backward);
            originals.add(new Original(id, from, to, capacity, forward));
        }

        int[] buildLevels(int source) {
            int[] level = new int[n];
            Arrays.fill(level, -1);
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            level[source] = 0;
            queue.addLast(source);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Arc edge : graph.get(u)) {
                    if (edge.residual > 0 && level[edge.to] == -1) {
                        level[edge.to] = level[u] + 1;
                        queue.addLast(edge.to);
                    }
                }
            }
            return level;
        }

        long send(int u, int sink, long allowed,
                  int[] level, int[] next) {
            if (u == sink) {
                return allowed;
            }
            List<Arc> outgoing = graph.get(u);

            while (next[u] < outgoing.size()) {
                Arc edge = outgoing.get(next[u]);
                if (edge.residual > 0
                        && level[edge.to] == level[u] + 1) {
                    long pushed = send(edge.to, sink,
                            Math.min(allowed, edge.residual), level, next);
                    if (pushed > 0) {
                        edge.residual -= pushed;
                        Arc reverse = graph.get(edge.to)
                                .get(edge.reverseIndex);
                        reverse.residual = Math.addExact(
                                reverse.residual, pushed);
                        return pushed;
                    }
                }
                next[u]++;
            }
            return 0L;
        }

        long maxFlow(int source, int sink) {
            if (source < 0 || source >= n || sink < 0 || sink >= n
                    || source == sink) {
                throw new IllegalArgumentException(
                        "Need two distinct valid terminals");
            }

            long result = 0L;
            while (true) {
                int[] level = buildLevels(source);
                if (level[sink] == -1) {
                    break;
                }

                int[] next = new int[n];
                while (true) {
                    long pushed = send(source, sink, Long.MAX_VALUE,
                            level, next);
                    if (pushed == 0L) {
                        break;
                    }
                    result = Math.addExact(result, pushed);
                }
            }
            return result;
        }

        boolean[] residualReachable(int source) {
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            seen[source] = true;
            queue.addLast(source);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Arc edge : graph.get(u)) {
                    if (edge.residual > 0 && !seen[edge.to]) {
                        seen[edge.to] = true;
                        queue.addLast(edge.to);
                    }
                }
            }
            return seen;
        }

        Cut recoverCut(int source, int sink) {
            boolean[] inS = residualReachable(source);
            if (inS[sink]) {
                throw new IllegalStateException(
                        "Sink still reachable: max-flow not certified");
            }

            List<Integer> sourceSide = new ArrayList<>();
            List<Integer> sinkSide = new ArrayList<>();
            for (int v = 0; v < n; v++) {
                if (inS[v]) {
                    sourceSide.add(v);
                } else {
                    sinkSide.add(v);
                }
            }

            List<Original> crossing = new ArrayList<>();
            long cutCapacity = 0L;
            long reverseFlow = 0L;

            for (Original edge : originals) {
                if (edge.from() == edge.to()) {
                    continue; // Không cắt qua phân hoạch.
                }

                long flow = Math.subtractExact(
                        edge.capacity(), edge.forward().residual);

                if (inS[edge.from()] && !inS[edge.to()]) {
                    crossing.add(edge);
                    cutCapacity = Math.addExact(
                            cutCapacity, edge.capacity());

                    if (edge.forward().residual != 0L) {
                        throw new IllegalStateException(
                                "A cut edge has positive forward residual");
                    }
                } else if (!inS[edge.from()] && inS[edge.to()]) {
                    reverseFlow = Math.addExact(reverseFlow, flow);
                }
            }

            if (reverseFlow != 0L) {
                throw new IllegalStateException(
                        "Positive original flow from T to S");
            }

            return new Cut(List.copyOf(sourceSide), List.copyOf(sinkSide),
                    List.copyOf(crossing), cutCapacity, reverseFlow, inS);
        }
    }

    static void sample(Network net) {
        net.add(0, 1, 8);   // ID 0
        net.add(0, 1, 2);   // ID 1, cạnh song song
        net.add(0, 2, 10);  // ID 2
        net.add(1, 2, 2);   // ID 3, hướng T->S của cut sau cùng
        net.add(1, 3, 4);   // ID 4
        net.add(1, 4, 8);   // ID 5
        net.add(2, 4, 9);   // ID 6
        net.add(4, 3, 6);   // ID 7
        net.add(3, 5, 10);  // ID 8
        net.add(4, 5, 10);  // ID 9
        net.add(2, 2, 7);   // ID 10, self-loop
        net.add(3, 4, 0);   // ID 11, capacity zero
    }

    public static void main(String[] args) {
        Network net = new Network(6);
        sample(net);

        long value = net.maxFlow(0, 5);
        Cut cut = net.recoverCut(0, 5);

        System.out.println("Max flow: " + value);
        System.out.println("S (reachable): " + cut.sourceSide());
        System.out.println("T (unreachable): " + cut.sinkSide());

        for (Original edge : cut.crossing()) {
            long edgeFlow = edge.capacity()
                    - edge.forward().residual;
            System.out.println("Cut edge #" + edge.id()
                    + " " + edge.from() + "->" + edge.to()
                    + " cap=" + edge.capacity()
                    + " flow=" + edgeFlow
                    + " residual=" + edge.forward().residual);
        }

        System.out.println("Cut capacity: " + cut.capacity());
        System.out.println("Reverse-crossing flow: "
                + cut.reverseCrossingFlow());
        System.out.println("Sink reachable after max flow: "
                + cut.inS()[5]);

        Network unreachable = new Network(4);
        unreachable.add(0, 1, 5);
        unreachable.add(1, 2, 0);
        unreachable.add(2, 3, 7);
        long noFlow = unreachable.maxFlow(0, 3);
        Cut noPathCut = unreachable.recoverCut(0, 3);
        System.out.println("No-path flow: " + noFlow);
        System.out.println("No-path S: " + noPathCut.sourceSide());
        System.out.println("No-path cut capacity: "
                + noPathCut.capacity());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ResidualMinCutDinicDemo.java
java ResidualMinCutDinicDemo
```

Stdout:

```text
Max flow: 19
S (reachable): [0, 2]
T (unreachable): [1, 3, 4, 5]
Cut edge #0 0->1 cap=8 flow=8 residual=0
Cut edge #1 0->1 cap=2 flow=2 residual=0
Cut edge #6 2->4 cap=9 flow=9 residual=0
Cut capacity: 19
Reverse-crossing flow: 0
Sink reachable after max flow: false
No-path flow: 0
No-path S: [0, 1]
No-path cut capacity: 0
```

### 7.1. Cấu trúc `reverseIndex` phải chính xác

Giả sử một cung xuôi f được thêm vào adjacency[u] và cung ngược b vào adjacency[v]. Cung f cần lưu chỉ số b **trong adjacency[v]**; cung b cần lưu chỉ số f **trong adjacency[u]**.

Khi augment `pushed`, cập nhật:

```text
f.residual -= pushed
b.residual += pushed
```

Nếu có cạnh song song hoặc hai cạnh gốc ngược chiều, **không** tìm cung đảo chỉ bằng cặp `(to,from)` vì có thể có nhiều cung cùng hai đầu. Dùng cặp chỉ số/bản tham chiếu được tạo khi thêm cạnh.

### 7.2. Tại sao self-loop được xử lý riêng?

Vòng `(u,u)` không giúp truyền s→t và cũng **không thể vượt qua một cut** vì u không thể thuộc cả S và T. Bỏ nó khỏi mạng dư không thay đổi giá trị max-flow/min-cut. Chương trình vẫn giữ bản ghi gốc để bảo toàn ID đầu vào.

Nếu muốn thật sự lưu self-loop trong residual graph, phải cài chính xác chỉ số đảo **ngay trong cùng adjacency[u]**; nhiều đoạn code thêm cung kiểu thông thường khi `from==to` bị trỏ `reverseIndex` sai.

### 7.3. Tại sao cut capacity tính từ danh sách cạnh gốc?

Sau max-flow, những cung dư S→T có residual 0. Nếu cộng chúng, ta sẽ thu 0 chứ **không phải** dung lượng min-cut.

Ta phải lấy **capacity gốc** của mỗi cạnh S→T. Mạng dư dùng để tìm **phân hoạch**, không dùng residual như trọng số cut.

### 7.4. Có cần gọi `maxFlow` trước không?

**Có.** `recoverCut` chỉ cung cấp chứng nhận min-cut đúng sau khi luồng đã cực đại. Code kiểm điều kiện t không reachable; tuy nhiên muốn tin kết quả toán học, mạng dư vẫn phải được duy trì đúng từ **một luồng hợp lệ** và mọi bước cập nhật phải theo luật residual.

### 7.5. Độ phức tạp Dinic

Với mạng luồng tổng quát, Dinic có cận worst-case **`O(V²E)`**; bộ nhớ residual/adjacency **`O(V+E)`**. Hàm `send` dùng đệ quy có thể tràn ngăn xếp Java với đường rất dài; khi V cực lớn, cân nhắc DFS dạng stack tường minh.

Bước **`recoverCut` riêng** chỉ có `O(V+E)` thời gian sau khi max-flow xong.

## 8. Cạnh dư ngược có thể quyết định tìm đúng max-flow

Một lỗi cơ bản là chỉ tăng dọc cạnh xuôi, không cho phép đi ngược trên cạnh đã có luồng. Xét mạng nhỏ 6 đỉnh:

```text
s=0, t=5

0→1:1
0→2:1
1→3:1
1→4:1
2→3:1
3→5:1
4→5:1
```

Nếu đường tăng đầu tiên là:

`0→1→3→5`, đẩy 1 đơn vị.

Sau đó đường xuôi tự nhiên `0→2→3→5` bị chặn vì `3→5` đã đầy. Nếu không có cung dư ngược, một thuật toán sai có thể kết luận luồng tối đa chỉ bằng 1.

Nhưng mạng dư có **cung ngược `3→1` dung lượng 1** từ luồng trên `1→3`. Vì vậy có đường tăng thứ hai:

`0→2→3→1→4→5`.

Bước `3→1` **hủy** luồng cũ trên cạnh `1→3`; cuối cùng luồng được bố trí:

```text
0→1→4→5 : 1
0→2→3→5 : 1
```

Giá trị max-flow thành **2**. Sau đó s không còn cung dư đi ra với residual>0, nên `S={0}` và cut capacity bằng `1+1=2`.

**Bài học:** cung ngược không phải lỗi cần xóa; nó là cơ chế đảm bảo một đường tăng đã chọn trước **không khóa cứng** nghiệm tối ưu.

## 9. Java 17 — Edmonds–Karp và in đường tăng có cung dư ngược

Chương trình thứ hai độc lập với Dinic, dùng BFS để tìm **đường tăng ngắn nhất theo số cung** trên residual graph.

Lưu thành **ResidualReverseAugmentDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ResidualReverseAugmentDemo {
    static final class Arc {
        final int from, to, reverseIndex;
        final boolean originalDirection;
        long residual;

        Arc(int from, int to, int reverseIndex,
            long residual, boolean originalDirection) {
            this.from = from;
            this.to = to;
            this.reverseIndex = reverseIndex;
            this.residual = residual;
            this.originalDirection = originalDirection;
        }
    }

    record Original(int from, int to, long capacity) {}

    static final class Network {
        final int n;
        final List<List<Arc>> graph;
        final List<Original> originalEdges;

        Network(int n) {
            this.n = n;
            graph = new ArrayList<>();
            originalEdges = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                graph.add(new ArrayList<>());
            }
        }

        Arc add(int u, int v, long capacity) {
            if (capacity < 0 || u < 0 || u >= n
                    || v < 0 || v >= n || u == v) {
                throw new IllegalArgumentException(
                        "This demo uses non-loop directed edges");
            }

            Arc forward = new Arc(u, v, graph.get(v).size(),
                    capacity, true);
            Arc backward = new Arc(v, u, graph.get(u).size(),
                    0L, false);
            graph.get(u).add(forward);
            graph.get(v).add(backward);
            originalEdges.add(new Original(u, v, capacity));
            return forward;
        }

        long maxFlowWithTrace(int source, int sink) {
            if (source == sink) {
                throw new IllegalArgumentException("s must differ from t");
            }

            long total = 0L;
            int count = 0;

            while (true) {
                int[] parent = new int[n];
                java.util.Arrays.fill(parent, -1);
                Arc[] via = new Arc[n];

                ArrayDeque<Integer> queue = new ArrayDeque<>();
                parent[source] = source;
                queue.addLast(source);

                while (!queue.isEmpty() && parent[sink] == -1) {
                    int u = queue.removeFirst();
                    for (Arc arc : graph.get(u)) {
                        int v = arc.to;
                        if (arc.residual > 0 && parent[v] == -1) {
                            parent[v] = u;
                            via[v] = arc;
                            queue.addLast(v);
                            if (v == sink) {
                                break;
                            }
                        }
                    }
                }

                if (parent[sink] == -1) {
                    break;
                }

                long delta = Long.MAX_VALUE;
                List<String> steps = new ArrayList<>();

                for (int v = sink; v != source; v = parent[v]) {
                    Arc arc = via[v];
                    delta = Math.min(delta, arc.residual);
                    steps.add(arc.from + "->" + arc.to
                            + (arc.originalDirection
                                ? "" : "(reverse)"));
                }
                Collections.reverse(steps);

                for (int v = sink; v != source; v = parent[v]) {
                    Arc arc = via[v];
                    arc.residual -= delta;
                    Arc reverse = graph.get(arc.to)
                            .get(arc.reverseIndex);
                    reverse.residual = Math.addExact(
                            reverse.residual, delta);
                }

                count++;
                total = Math.addExact(total, delta);
                System.out.println("Augment #" + count + ": "
                        + String.join(", ", steps)
                        + " | delta=" + delta);
            }

            return total;
        }

        boolean[] reachable(int source) {
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> q = new ArrayDeque<>();
            seen[source] = true;
            q.addLast(source);
            while (!q.isEmpty()) {
                int u = q.removeFirst();
                for (Arc e : graph.get(u)) {
                    if (e.residual > 0 && !seen[e.to]) {
                        seen[e.to] = true;
                        q.addLast(e.to);
                    }
                }
            }
            return seen;
        }

        List<Integer> sourceSide(boolean[] seen) {
            List<Integer> answer = new ArrayList<>();
            for (int v = 0; v < n; v++) {
                if (seen[v]) {
                    answer.add(v);
                }
            }
            return answer;
        }

        long cutCapacity(boolean[] seen) {
            long capacity = 0L;
            for (Original e : originalEdges) {
                if (seen[e.from()] && !seen[e.to()]) {
                    capacity = Math.addExact(capacity, e.capacity());
                }
            }
            return capacity;
        }
    }

    public static void main(String[] args) {
        Network net = new Network(6);
        net.add(0, 1, 1);
        net.add(0, 2, 1);
        Arc oldRoute = net.add(1, 3, 1);
        net.add(1, 4, 1);
        net.add(2, 3, 1);
        net.add(3, 5, 1);
        net.add(4, 5, 1);

        long flow = net.maxFlowWithTrace(0, 5);
        boolean[] seen = net.reachable(0);

        System.out.println("Max flow: " + flow);
        System.out.println("Final flow on 1->3: "
                + (1L - oldRoute.residual));
        System.out.println("Residual S: " + net.sourceSide(seen));
        System.out.println("Cut capacity: " + net.cutCapacity(seen));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ResidualReverseAugmentDemo.java
java ResidualReverseAugmentDemo
```

Stdout:

```text
Augment #1: 0->1, 1->3, 3->5 | delta=1
Augment #2: 0->2, 2->3, 3->1(reverse), 1->4, 4->5 | delta=1
Max flow: 2
Final flow on 1->3: 0
Residual S: [0]
Cut capacity: 2
```

### 9.1. Vì sao `Final flow on 1->3: 0`?

Ban đầu đường tăng thứ nhất đẩy 1 trên 1→3. Đường tăng thứ hai sử dụng **cung dư ngược** 3→1, làm giảm luồng trên cạnh gốc 1→3 từ 1 xuống **0**. Luồng mới chuyển qua cạnh 1→4 để đến t. Nếu mã in flow trên cạnh 1→3 vẫn là 1, phần cập nhật reverse residual đã bị sai.

### 9.2. Edmonds–Karp có đảm bảo kết thúc không?

Có. Edmonds–Karp chọn đường tăng bằng **BFS trên residual graph** và có độ phức tạp worst-case `O(VE²)` với E là số cạnh gốc (bỏ qua hằng số do cặp cung dư). Nó kết thúc với max-flow cho dung lượng không âm; trình tự đường tăng có thể khác nếu đổi thứ tự adjacency, nhưng **giá trị max-flow và capacity min-cut không đổi**.

### 9.3. Không được xóa các cung dư ngược “để đồ thị nhìn gọn”

Nếu xóa chúng trước khi tính S, ta đang duyệt trên một đồ thị **không còn là residual graph đúng**. S có thể khác và chứng minh min-cut không áp dụng. Chỉ được bỏ cung có **residual=0**, bất kể là xuôi hay ngược; cung ngược residual>0 vẫn phải giữ.

## 10. Có thể có nhiều lát cắt nhỏ nhất không?

**Có.** Thuật toán BFS từ s trong mạng dư sau max-flow trả **một** min-cut, chứ không nhất thiết liệt kê toàn bộ min-cut.

Ví dụ hình thoi:

```text
s=0
0→1:1
0→2:1
1→3:1
2→3:1
t=3
```

Max-flow bằng 2. Có **bốn** phân hoạch min-cut cùng capacity 2:

- `S={0}`.
- `S={0,1}`.
- `S={0,2}`.
- `S={0,1,2}`.

Với một max-flow bão hòa cả bốn cạnh, BFS dư từ s chỉ tới `S={0}`. Đó là **một cut hợp lệ và tối ưu**, nhưng không phải cut duy nhất.

### 10.1. S nhỏ nhất theo bao hàm

Một tính chất sâu hơn: sau khi có max-flow, đặt:

`S_min = {v : s còn tới được v trong residual graph}`.

Trong **mọi min-cut** `(A,V\A)`, đều có `S_min ⊆ A`. Nói cách khác, S_min là **phía nguồn nhỏ nhất theo quan hệ bao hàm** trong số các min-cut.

Lý do: nếu cut A tối ưu, **không có cung dư dương đi từ A sang V\A**. Bắt đầu ở s∈A, mọi đường trong residual phải ở lại A. Vì vậy mọi đỉnh reachable từ s thuộc A.

### 10.2. S lớn nhất theo bao hàm

Đặt:

`R_t = {v : trong residual graph có đường từ v tới t}`.

Tính R_t bằng BFS/DFS **từ t trên đồ thị dư đảo chiều** (chỉ các cung dư dương).

Với mọi min-cut, `R_t` phải thuộc **phía T**, vì nếu một đỉnh thuộc S có đường dư tới t∈T thì sẽ tồn tại cung dư đi qua cut. Suy ra:

`S_max = V \ R_t`

là **phía nguồn lớn nhất theo bao hàm** của các min-cut. Nó cũng là một min-cut vì không có cung dư dương từ S_max sang R_t.

### 10.3. Kiểm tính duy nhất của phân hoạch min-cut

Nếu:

`S_min == S_max`

thì mọi min-cut có cùng phía nguồn ⇒ phân hoạch min-cut **duy nhất**. Nếu hai tập khác nhau thì tồn tại ít nhất hai min-cut.

**Lưu ý:** phân hoạch min-cut duy nhất không đồng nghĩa luồng cực đại duy nhất. Có thể có nhiều cách phân phối luồng đạt cùng giá trị; không được suy ra uniqueness của flow từ uniqueness của cut.

## 11. Oracle độc lập: duyệt mọi phân hoạch s–t khi V nhỏ

Để kiểm tra max-flow/min-cut trên mạng rất nhỏ, có thể **vét cạn tất cả tập S** thỏa `s∈S`, `t∉S`.

Với V đỉnh, có `2^(V−2)` phân hoạch như vậy (nếu s,t khác nhau). Mỗi phân hoạch tính:

`sum capacity(e)` với mọi cạnh **gốc** từ S sang ngoài S.

Giữ capacity nhỏ nhất và đếm số tập S đạt capacity đó. Cách này **không chạy max-flow và không dùng mạng dư**, nên rất hữu ích làm **oracle độc lập**.

Trên ví dụ sáu đỉnh phần 6, brute-force cho:

- Minimum cut capacity: **19**.
- Số phân hoạch min-cut: **1**.
- Phía nguồn duy nhất: **`[0,2]`**.

Trên hình thoi, brute-force cho capacity 2, **4 min-cut**.

### 11.1. Java 17 — liệt kê min-cut bằng bitmask

Lưu thành **MinCutBruteForceOracleDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;

public class MinCutBruteForceOracleDemo {
    record Edge(int from, int to, long capacity) {}
    record Answer(long capacity, List<List<Integer>> sourceSides) {}

    static Answer enumerate(int n, Edge[] edges, int source, int sink) {
        if (n < 2 || n > 18 || source < 0 || source >= n
                || sink < 0 || sink >= n || source == sink) {
            throw new IllegalArgumentException(
                    "Only 2<=n<=18 and distinct valid s,t");
        }

        for (Edge e : edges) {
            if (e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n
                    || e.capacity() < 0) {
                throw new IllegalArgumentException("Invalid edge");
            }
        }

        boolean found = false;
        long best = 0L;
        List<List<Integer>> winners = new ArrayList<>();
        int limit = 1 << n;

        for (int mask = 0; mask < limit; mask++) {
            if ((mask & (1 << source)) == 0
                    || (mask & (1 << sink)) != 0) {
                continue;
            }

            long capacity = 0L;
            for (Edge e : edges) {
                boolean fromInS = (mask & (1 << e.from())) != 0;
                boolean toInS = (mask & (1 << e.to())) != 0;

                if (fromInS && !toInS) {
                    capacity = Math.addExact(
                            capacity, e.capacity());
                }
            }

            if (!found || capacity < best) {
                best = capacity;
                winners.clear();
                found = true;
            }

            if (capacity == best) {
                List<Integer> side = new ArrayList<>();
                for (int v = 0; v < n; v++) {
                    if ((mask & (1 << v)) != 0) {
                        side.add(v);
                    }
                }
                winners.add(List.copyOf(side));
            }
        }

        return new Answer(best, List.copyOf(winners));
    }

    static Edge[] sample() {
        return new Edge[]{
            new Edge(0, 1, 8),  new Edge(0, 1, 2),
            new Edge(0, 2, 10), new Edge(1, 2, 2),
            new Edge(1, 3, 4),  new Edge(1, 4, 8),
            new Edge(2, 4, 9),  new Edge(4, 3, 6),
            new Edge(3, 5, 10), new Edge(4, 5, 10),
            new Edge(2, 2, 7),  new Edge(3, 4, 0)
        };
    }

    public static void main(String[] args) {
        Answer a = enumerate(6, sample(), 0, 5);
        System.out.println("Sample min-cut capacity: " + a.capacity());
        System.out.println("Sample min-cut count: "
                + a.sourceSides().size());
        System.out.println("Sample min-cut source sets: "
                + a.sourceSides());

        Edge[] diamond = {
            new Edge(0, 1, 1), new Edge(0, 2, 1),
            new Edge(1, 3, 1), new Edge(2, 3, 1)
        };
        Answer b = enumerate(4, diamond, 0, 3);
        System.out.println("Diamond capacity: " + b.capacity());
        System.out.println("Diamond min-cut count: "
                + b.sourceSides().size());
        System.out.println("Diamond min-cut source sets: "
                + b.sourceSides());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MinCutBruteForceOracleDemo.java
java MinCutBruteForceOracleDemo
```

Stdout:

```text
Sample min-cut capacity: 19
Sample min-cut count: 1
Sample min-cut source sets: [[0, 2]]
Diamond capacity: 2
Diamond min-cut count: 4
Diamond min-cut source sets: [[0], [0, 1], [0, 2], [0, 1, 2]]
```

### 11.2. Độ phức tạp của brute force

Có `2^(V−2)` phân hoạch hợp lệ; mỗi phân hoạch quét E cạnh gốc, nên thời gian `O(2^V E)`. Code còn lưu **tất cả tập S tối ưu**, tốn thêm bộ nhớ theo số nghiệm `O(numberOfMinCuts*V)`.

Giới hạn n<=18 để demo không vô tình thử lượng quá lớn. Với V lớn, dùng max-flow + reachability `O(V+E)` sau khi có luồng, **không** liệt kê mọi cut bằng bitmask.

## 12. Sự khác biệt giữa cut và residual cut

Một lỗi thuật ngữ dễ gặp:

- **Một cut** là **phân hoạch đỉnh** `(S,T)`.
- **Các cạnh qua cut** là các cạnh **gốc S→T**.
- **Dung lượng cut** là tổng capacity **gốc** trên những cạnh đó.
- **Tập S được khám phá trên residual graph** là cách ta **tìm một min-cut** sau max-flow, không có nghĩa cut có thể được đo bằng tổng residual.
- **Cung ngược dư** là đối tượng thuật toán; nó không tự động trở thành cạnh gốc qua cut.

Nếu cạnh gốc `(u,v)` đã bão hòa nhưng u,v **cùng thuộc S**, nó không nằm trong cut. Nếu cạnh `u→v` bão hòa và u∈S, v∈T, nó nằm trong cut. Điều kiện **phân hoạch** mới quyết định membership, còn bão hòa là **hệ quả** của cut tối ưu.

### 12.1. Có thể chỉ nhìn cạnh bão hòa để tìm min-cut?

**Không.** Rất nhiều cạnh có thể bão hòa trong luồng tối ưu mà **không** nằm trên lát cắt khôi phục được.

Thuật toán đúng bắt đầu bằng việc BFS/DFS từ s trên residual graph; sau đó lọc cạnh gốc theo vị trí hai đầu. Chọn “cạnh nào residual0” rồi cộng tất cả capacity có thể cho số lớn hơn min-cut.

### 12.2. Có thể dùng đồ thị gốc để tìm S?

**Không.** Đồ thị gốc có những cạnh đã bão hòa, vẫn tồn tại về mặt cấu trúc nhưng **không còn dung lượng dư**. BFS trên cạnh gốc sẽ đi qua những cạnh không còn cho phép tăng luồng, làm S bị mở rộng sai.

### 12.3. Có thể dùng đồ thị chỉ có cung dư xuôi?

**Không.** Cung dư ngược có thể có residual>0; bỏ chúng sẽ làm sai tính tới được. Quy tắc là xét **mọi cung dư còn dung lượng dương**: xuôi, ngược, kể cả các cung phát sinh do cạnh gốc ngược chiều.

## 13. Trường hợp biên cần xử lý rõ

| Trường hợp | Kết quả/điều kiện đúng |
|---|---|
| Không có đường có residual>0 từ s tới t ngay từ đầu | Max-flow 0; cut capacity 0, S là phần reachable từ s qua cung dư dương |
| Cạnh gốc capacity 0 | Không truyền luồng; có thể xuất hiện qua cut với đóng góp 0 |
| Hai cạnh song song S→T | **Cộng cả hai** capacity; giữ ID nếu cần in |
| Cạnh gốc T→S | **Không cộng** capacity vào c(S,T) |
| Cạnh gốc nội bộ S hoặc T | Không thuộc cut |
| Self-loop u→u | Không vượt cut, không có tác dụng cho s–t flow |
| Mạng không có cạnh | S thường chỉ có s; cut capacity 0 |
| Mọi cạnh ra s bão hòa | Thường S chỉ gồm s, nhưng phải **BFS để xác nhận**, không đoán |
| Mạng có các cạnh gốc ngược hướng | Mỗi cạnh gốc phải có **cặp cung dư riêng** |
| Có chu trình trong residual graph | BFS visited tránh lặp vô hạn |
| Luồng chưa cực đại | t vẫn có thể reachable; không gọi cut hiện tại là min-cut |
| Trọng số âm được nhập làm capacity | **Không hợp lệ** với định nghĩa max-flow chuẩn |
| Tổng capacity/flow vượt long | Dùng phép cộng checked hoặc `BigInteger`/kiểu lớn hơn |
| s==t | Bài s–t max-flow/min-cut chuẩn yêu cầu **hai terminal khác nhau** |
| Nhiều min-cut bằng nhau | BFS dư trả **một** min-cut; không mặc nhiên là duy nhất |
| Cần đếm số min-cut | Bài nâng cao, không thể chỉ lấy kích thước S; brute force chỉ dùng cho V nhỏ |
| Đồ thị vô hướng | Phải mô hình hóa dung lượng cẩn thận, thường bằng hai cạnh có hướng và tính **chỉ cạnh gốc S→T** |
| Nhiều nguồn/đích | Dùng siêu nguồn/siêu đích và kiểm ý nghĩa các cạnh nhân tạo |

### 13.1. Nguồn không tới được đích

Nếu mạng có cạnh 0→1 capacity 5, 1→2 capacity 0, 2→3 capacity 7, chọn s=0, t=3:

- Không có đường tăng s–t ngay từ đầu.
- Max-flow = 0.
- Trong residual graph, s còn tới được 1 qua cạnh capacity 5, nhưng **không thể vượt 1→2** vì residual 0.
- `S={0,1}`, `T={2,3}`, cạnh gốc qua cut là 1→2 capacity 0.
- `c(S,T)=0`.

Điều này chứng minh **không có đường s–t** không đồng nghĩa S chỉ có s.

### 13.2. Cạnh vô hướng có capacity

Nếu đề mô tả cạnh vô hướng `{u,v}` dung lượng c, một cách mô hình thông dụng là cho **hai cạnh gốc có hướng** `u→v` capacity c và `v→u` capacity c. Với một phân hoạch, chỉ **một hướng** của mỗi cặp đi S→T, nên capacity cut vẫn cộng c một lần cho mỗi cạnh vô hướng vượt cắt.

**Không** cộng cả hai chiều của một cạnh vô hướng vào capacity cut. **Không** nhầm hai cạnh gốc hai hướng này với hai cung dư xuôi/ngược từ **một cạnh gốc có hướng**.

### 13.3. Siêu nguồn và siêu đích

Nếu có nhiều nguồn/đích, có thể thêm `superSource` nối tới các nguồn và các đích nối tới `superSink` bằng các cung đủ capacity. Min-cut trên **mạng mở rộng** phải được diễn giải cẩn thận khi trả lời bài **mạng gốc**; các cạnh nhân tạo có thể ảnh hưởng phân hoạch nếu dung lượng lựa chọn không đủ lớn.

Nếu chọn “vô hạn” bằng một sentinel số nguyên, cần tránh tràn và phải bảo đảm nó thật sự lớn hơn mọi luồng hợp lệ theo giới hạn đề.

## 14. Các bất biến để kiểm chất lượng cài đặt

### 14.1. Bất biến của mỗi cặp cung dư

Với cạnh gốc e có capacity c, gọi forward residual là r_f và backward residual là r_b (cặp cung thuộc riêng e):

`r_f + r_b = c`

và:

`f(e) = r_b = c−r_f`.

Ban đầu `(r_f,r_b)=(c,0)`. Khi đẩy delta xuôi, `(r_f,r_b)` thành `(r_f−delta,r_b+delta)`. Khi dùng cung ngược, thao tác đảo lại. Tổng luôn bằng c.

Với self-loop bỏ khỏi residual, có thể coi luồng của nó được cố định bằng 0; nó không liên quan cut.

### 14.2. Bất biến luồng ở đỉnh trung gian

Sau mỗi augmentation hoàn chỉnh, tổng f vào v bằng tổng f ra v cho mọi v khác s,t. Đẩy dọc một **đường tăng** làm bảo toàn luồng ở những đỉnh trung gian, kể cả khi đường đi dùng cung dư ngược để giảm f trên cạnh gốc.

### 14.3. Điều kiện kiểm chứng cut sau khi chạy

Khi max-flow kết thúc, cần đồng thời:

1. `inS[s]==true`.
2. `inS[t]==false`.
3. Mọi đỉnh inS đều có đường dư dương từ s.
4. Không tồn tại cung dư dương có đầu ở S và cuối ở T.
5. Mọi cạnh **gốc S→T** bão hòa.
6. Mọi cạnh **gốc T→S** có flow 0.
7. `cutCapacity == maxFlowValue`.
8. Danh sách cut edges được lấy theo **cạnh gốc** có ID, không lẫn cung ngược.

Nếu chỉ so `maxFlow==cutCapacity` mà không kiểm điều kiện 1–6, code có thể tình cờ in đúng một số trên một ví dụ nhưng sai cấu trúc với input khác.

## 15. Cách kiểm thử bằng oracle và dữ liệu ngẫu nhiên

Với n nhỏ (2..8) và e nhỏ, sinh đồ thị có hướng ngẫu nhiên có:

- Capacity thuộc miền hẹp 0..6 để tạo **cạnh bão hòa** và tie.
- Cạnh song song từ u sang v.
- Cặp cạnh gốc hai chiều u→v và v→u.
- Self-loop.
- Đỉnh cô lập, nhiều thành phần.
- Nhiều cut cùng capacity.

Với mỗi đồ thị:

1. Chạy Dinic, lấy `maxFlow`.
2. BFS các cung dư dương từ s để có S.
3. Tính `cutCapacity` từ **các cạnh gốc**.
4. Dùng Edmonds–Karp độc lập tìm maxFlow thứ hai.
5. Vét cạn tất cả phân hoạch s–t để lấy minimum cut capacity.
6. Kiểm `dinicFlow == edmondsKarpFlow == bruteMinCut`.
7. Kiểm `cutCapacity == dinicFlow` và S thật sự là một trong các phân hoạch min-cut.
8. Kiểm mọi cạnh gốc S→T bão hòa; mọi cạnh gốc T→S flow0.
9. Kiểm luồng gốc trên từng cạnh nằm trong `[0,capacity]`, và bảo toàn tại đỉnh trung gian.

### 15.1. Không yêu cầu các thuật toán chọn cùng S qua mọi lúc

Với các **luồng chưa cực đại**, mạng dư khác nhau và S chưa là min-cut. Sau khi cả hai thuật toán đều cực đại, tập reachable từ s thực ra là **phía nguồn nhỏ nhất theo bao hàm trong các min-cut**, vì thế nó được quyết định bởi mạng gốc và dung lượng; kết quả S nên khớp, nếu cả hai cài đúng.

Các thuật toán vẫn có thể có **luồng cực đại khác nhau trên từng cạnh**, nên không bắt buộc so từng f(e) giữa Dinic và Edmonds–Karp. Hãy so giá trị max-flow, cut và tính hợp lệ của luồng.

## 16. Lỗi sai thường gặp và cách sửa

### Lỗi 1 — BFS trên cạnh gốc thay vì cạnh dư

Cạnh đã bão hòa vẫn tồn tại trong graph gốc. **Sửa:** BFS chỉ trên residual edges có capacity dư `>0`.

### Lỗi 2 — Lấy tất cả cạnh có residual 0

Không phải mọi cạnh bão hòa đều vượt min-cut. **Sửa:** xác định S/T trước, sau đó lọc `inS[u] && !inS[v]` trên danh sách **cạnh gốc**.

### Lỗi 3 — Cộng residual thay vì capacity gốc

Các cung dư S→T đều residual 0 sau max-flow, nên cộng chúng ra 0. **Sửa:** cộng **capacity ban đầu**.

### Lỗi 4 — Cộng cả cạnh T→S

Min-cut trên đồ thị **có hướng** chỉ cộng các cạnh gốc đi **S→T**. Hướng ngược không được cộng.

### Lỗi 5 — Bỏ cung dư ngược khỏi graph

Cung dư ngược có thể cho phép hủy luồng đã chọn và quyết định tính tới được; xóa nó làm hỏng max-flow/min-cut.

### Lỗi 6 — Nhầm cung dư ngược với cạnh gốc ngược chiều

Mỗi cạnh gốc có cặp cung dư riêng. Không thể dùng một arc đối diện bất kỳ làm reverse partner nếu có cạnh song song/hai hướng.

### Lỗi 7 — Quên cạnh song song khi tính dung lượng cut

Nếu input có hai ID cùng `(u,v)`, capacity cut phải cộng **cả hai** nếu chúng đi S→T.

### Lỗi 8 — Sử dụng dấu `>=0` khi đi residual

Phải là **`residual>0`**. Duyệt cung residual0 sẽ bước qua cạnh bị bão hòa và làm S sai.

### Lỗi 9 — Chỉ duyệt cung dư xuôi

BFS từ s phải duyệt **mọi cung dư dương**, kể cả cung ngược từ những cạnh gốc có luồng dương.

### Lỗi 10 — Không đánh dấu visited khi enqueue

Một đỉnh có nhiều incoming arcs sẽ bị enqueue lặp, gây thừa xử lý. Đánh dấu lúc đưa vào queue.

### Lỗi 11 — Tuyên bố min-cut khi t vẫn reachable

Nếu t còn reachable trên mạng dư, vẫn còn đường tăng luồng; không thể chứng minh max-flow đã đạt.

### Lỗi 12 — Đặt capacity âm

Max-flow/min-cut chuẩn yêu cầu **capacity không âm**. Trọng số âm của bài shortest path/MST không được đưa nguyên vào đây.

### Lỗi 13 — Tràn khi tính capacity hoặc flow

Tổng trên nhiều cạnh có thể vượt int/long. Dùng `long` với `Math.addExact` hoặc `BigInteger` nếu cần.

### Lỗi 14 — Xử lý self-loop sai reverseIndex

Khi `u==v`, cả hai arc nằm trong cùng adjacency; cách tạo chỉ số đảo thông thường rất dễ sai. Có thể bỏ self-loop vì nó không ảnh hưởng s–t flow/cut.

### Lỗi 15 — Lẫn tổng capacity qua cut với số cạnh qua cut

Minimum cut tối ưu **tổng dung lượng**, không nhất thiết chọn ít cạnh nhất. Nếu muốn minimum **số cạnh** với mỗi cạnh phí1, đó là bài toán/cách mô hình khác.

### Lỗi 16 — Xóa mạng dư sau khi max-flow

Nếu chỉ giữ giá trị luồng mà đã xóa adjacency dư, không còn thông tin BFS để khôi phục S. Giữ mạng dư hoặc xây lại chính xác từ flow theo từng cạnh.

### Lỗi 17 — Không bảo toàn ID cạnh gốc

Nếu đề cần danh sách cạnh cắt, việc gộp cạnh song song không lưu ánh xạ khiến không biết phải in các ID nào. Lưu `Original` riêng.

### Lỗi 18 — Coi min-cut luôn duy nhất

Hình thoi có bốn min-cut bằng capacity2. BFS dư cho một min-cut; muốn liệt kê tất cả cần bài toán khác.

### Lỗi 19 — Đếm min-cut bằng số cạnh bão hòa

Số min-cut là số **phân hoạch tối ưu**, không liên hệ trực tiếp với số cạnh bão hòa.

### Lỗi 20 — Không xử lý đồ thị s/t rời nhau

Khi không có đường tăng, max-flow 0, min-cut0. S vẫn có thể chứa những đỉnh khác s nếu có cung dư dương tới chúng.

### Lỗi 21 — Cho s=t mà không có quy ước

Bài s–t flow và min-cut chuẩn giả định hai terminal **khác nhau**. Hàm giải nên reject hoặc có hợp đồng đặc biệt rõ ràng.

### Lỗi 22 — Dùng mạng dư trung gian thay vì mạng dư cuối

Tại một thời điểm giữa quá trình max-flow, S chưa đảm bảo là phía nguồn của một min-cut. Khôi phục **sau khi thuật toán chứng minh không còn đường tăng**.

### Lỗi 23 — Coi cut edges là toàn bộ cung dư S→T

Thực tế sau max-flow, không tồn tại cung dư S→T nào có capacity dương. Cut edges phải là **cạnh gốc** S→T, vốn đã bão hòa.

### Lỗi 24 — Tính `f(S,T)` mà quên `f(T,S)`

Với đồ thị có các cạnh gốc đi ngược về S, giá trị luồng qua cut là `f(S,T)-f(T,S)`, không phải luôn chỉ `f(S,T)` ở thời điểm bất kỳ. Ở cut được khôi phục từ residual cuối, `f(T,S)=0`, nên mới suy ra đẳng thức.

## 17. Bài tập tự luyện kèm giải thích

### Bài 1 — Xác định S

Sau max-flow, mạng dư cho phép từ s=0 đi tới 1 và 3, rồi từ 3 tới 4, nhưng không tới 2 hoặc t=5. S là gì?

**Đáp án:** `S={0,1,3,4}`, `T={2,5}`. Chỉ xét cung dư capacity>0.

### Bài 2 — Cạnh gốc qua cut

Với `S={0,2}`, `T={1,3}`, có các cạnh gốc `0→1 cap5`, `1→2 cap8`, `2→3 cap4`, `0→2 cap9`. Cạnh nào thuộc cut?

**Đáp án:** `0→1 cap5` và `2→3 cap4`; dung lượng cut=9. Cạnh 1→2 là T→S; cạnh 0→2 nội bộ S.

### Bài 3 — Saturation

Một cạnh gốc e từ S sang T có capacity7. Sau max-flow, residual xuôi e bằng bao nhiêu?

**Đáp án:** 0, vì nếu residual>0 sẽ đi được từ S sang T, mâu thuẫn T unreachable.

### Bài 4 — Luồng ngược cut

Cạnh gốc T→S capacity10. Luồng trên cạnh ấy ở min-cut từ residual cuối có thể dương không?

**Đáp án:** không. Nếu flow>0, cung dư ngược S→T có residual>0, mâu thuẫn S là tập reachable đầy đủ.

### Bài 5 — Luồng bằng capacity

Max-flow=23, sau BFS dư ta tính một cut capacity23. Kết luận?

**Đáp án:** đây là min-cut; `maxFlow=minCut=23` theo định lý và chứng nhận bằng đẳng thức.

### Bài 6 — Cạnh song song

Hai cạnh gốc S→T song song capacity3 và 5. Đóng góp của chúng vào cut capacity?

**Đáp án:** 8, nếu mỗi cạnh là một dòng input. Không được chỉ lấy max hoặc một cạnh.

### Bài 7 — Cung dư ngược

Cạnh gốc u→v capacity7 đang có flow4. Residual xuôi và ngược?

**Đáp án:** xuôi `7−4=3`; ngược `4`.

### Bài 8 — Hủy flow

Cạnh gốc 1→3 đang có flow1. Nếu đường tăng dùng cung dư ngược 3→1 một đơn vị, flow còn bao nhiêu?

**Đáp án:** 0. Đó là cách thuật toán đổi lựa chọn đường đi trước đó.

### Bài 9 — Không có đường

Nếu s và t không nối bởi bất kỳ đường dư dương nào ngay ban đầu, giá trị max-flow và min-cut?

**Đáp án:** cả hai bằng 0. S có thể chứa nhiều đỉnh reachable từ s nhưng không chứa t.

### Bài 10 — Residual0

Một cung dư có capacity0, BFS khôi phục S có được đi qua không?

**Đáp án:** không. Chỉ đi qua cung `residual>0`.

### Bài 11 — Cạnh gốc T→S

S chứa 0,2, T chứa 1,3. Cạnh gốc 1→2 capacity99 có cộng vào capacity cut không?

**Đáp án:** không, vì hướng T→S. Ở cut tối ưu khôi phục từ residual cuối, flow trên cạnh này phải bằng 0.

### Bài 12 — Internal edge

Cạnh gốc 0→2 capacity100, cả hai đầu thuộc S. Có thuộc cut không?

**Đáp án:** không; dù bão hòa hay chưa, nó ở nội bộ S.

### Bài 13 — Hình thoi

Mạng 0→1,0→2,1→3,2→3 mỗi capacity1. Max-flow và số min-cut?

**Đáp án:** max-flow=2, có 4 min-cut capacity2.

### Bài 14 — S nhỏ nhất

Trong mọi min-cut của hình thoi, S có thể là {0}, {0,1}, {0,2}, {0,1,2}. BFS dư từ s sau max-flow trả tập nào?

**Đáp án:** `S_min={0}`, nhỏ nhất theo bao hàm.

### Bài 15 — S lớn nhất

Với hình thoi trên, phía nguồn lớn nhất theo bao hàm của các min-cut là gì?

**Đáp án:** `{0,1,2}`, vì chỉ t=3 có thể tới t trong residual cuối.

### Bài 16 — Độ phức tạp

Sau max-flow, BFS dư và lọc cạnh gốc có chi phí bao nhiêu?

**Đáp án:** `O(V+E)` thời gian, `O(V)` bộ nhớ phụ chưa kể lưu danh sách cạnh cắt.

### Bài 17 — Sai lầm tổng residual

Nếu bạn cộng residual của các cung S→T sau max-flow và nhận0, liệu min-cut capacity luôn là0?

**Đáp án:** không. Residual0 là **bão hòa**, capacity cũ có thể lớn. Phải cộng dung lượng gốc.

### Bài 18 — Self-loop

Cạnh gốc 2→2 capacity1000 có làm tăng capacity cut khi 2∈S không?

**Đáp án:** không, vì hai đầu cùng một đỉnh nên không vượt S→T.

### Bài 19 — Nhiều nguồn

Khi có ba nguồn, có thể chuyển thành bài s–t chuẩn bằng cách nào?

**Đáp án:** tạo siêu nguồn nối tới các nguồn với capacity phù hợp và một siêu đích nếu có nhiều sink; phải giải thích cách suy cut trở lại mạng gốc.

### Bài 20 — Certificate

Nêu hai điều kiện cạnh cần kiểm trên cut khôi phục.

**Đáp án:** mọi cạnh gốc S→T bão hòa `f=c`; mọi cạnh gốc T→S có `f=0`.

### Bài 21 — Khác biệt dòng và cut

Có phải mọi max-flow có cùng f(e) trên từng cạnh không?

**Đáp án:** không. Max-flow có thể không duy nhất về phân phối luồng, nhưng giá trị max-flow bằng min-cut capacity là bất biến.

### Bài 22 — Dữ liệu cực lớn

Tổng capacity có thể vượt `Long.MAX_VALUE`. `long` cộng unchecked có an toàn không?

**Đáp án:** không. Dùng checked addition, thuật toán số nguyên tùy ý hoặc hợp đồng giới hạn dữ liệu đầu vào; không chấp nhận overflow.

## 18. Checklist trước khi nộp bài

1. Đồ thị được coi là **có hướng** đúng theo input?
2. Capacity mỗi cạnh **không âm**?
3. Có hai terminal **s khác t**?
4. Max-flow đã hoàn tất, **không còn đường dư dương từ s tới t**?
5. Vẫn giữ đúng **mạng dư sau augmentation**, gồm cả reverse arcs?
6. Có cặp reverseIndex chính xác cho **từng cạnh gốc**?
7. Có phân biệt reverse residual với cạnh gốc ngược chiều?
8. BFS/DFS khôi phục S chỉ đi qua cung `residual>0`?
9. Có đánh dấu visited ngay khi enqueue?
10. `s∈S` và `t∉S`?
11. Phía T được tạo bằng **phần bù** V\S?
12. Cut edges được lọc từ **cạnh gốc** theo hướng S→T?
13. Có cộng tất cả cạnh song song gốc vượt cut?
14. Có bỏ cạnh gốc T→S khỏi capacity cut?
15. Có bỏ self-loop và cạnh nội bộ cùng phía khỏi tổng cut?
16. Có dùng capacity **gốc**, không dùng residual, để cộng cut?
17. Mọi cạnh gốc S→T có `flow==capacity`?
18. Mọi cạnh gốc T→S có `flow==0`?
19. `maxFlowValue==cutCapacity`?
20. Đã kiểm bảo toàn luồng tại các đỉnh giữa?
21. Đã xử lý capacity0, sink unreachable, graph rỗng cạnh và nhiều cut?
22. Có tính đúng độ phức tạp max-flow và riêng bước khôi phục?
23. Có tránh overflow khi cộng flow/cut capacity?
24. Đã đối chiếu với brute-force min-cut trên mạng nhỏ?
25. Nếu đề yêu cầu **tất cả** min-cut hoặc min-cut duy nhất, đã xử lý bài toán bổ sung thay vì chỉ trả S đầu tiên?
26. Nếu mạng có nhiều nguồn/đích hoặc cạnh vô hướng, đã mô hình hóa và ánh xạ về bài gốc?

**Ghi nhớ:** Sau khi tìm luồng cực đại, **BFS/DFS từ nguồn s trên mạng dư qua các cung có dung lượng dư `>0`**. Tập đỉnh tới được là **S**, phần còn lại là **T**. Sau đó duyệt **các cạnh gốc có hướng từ S sang T**, cộng **dung lượng ban đầu** của chúng. Những cạnh ấy đều bão hòa; các cạnh gốc T→S có luồng 0. Từ bảo toàn luồng suy ra `maxFlow=capacity(S,T)`, chứng minh lát cắt tìm được là **nhỏ nhất**. Không được lấy tất cả cạnh bão hòa, cộng residual, xóa cung dư ngược hoặc lẫn cạnh song song.

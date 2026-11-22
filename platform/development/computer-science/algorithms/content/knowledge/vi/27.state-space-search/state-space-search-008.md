# Mở lại trạng thái và điều kiện dừng của A*

> **Chủ đề:** Computer Science Algorithms → **Tìm kiếm trạng thái** (*State-Space Search*).  
> **Bài học:** Khi nào thuật toán **A\*** phải **mở lại trạng thái đã đóng** (*reopen a closed state*)? Khi nào có thể **dừng** mà vẫn bảo đảm đường đi tối ưu? Phân biệt heuristic **chấp nhận được** (*admissible*) với heuristic **nhất quán** (*consistent*), xử lý priority queue có **bản ghi cũ** (*stale entries*), và kiểm chứng bằng ví dụ Java 17.

## 1. Mô hình A* và bốn khái niệm cần tách

Cho đồ thị trạng thái có hướng `G=(V,E)`, trạng thái bắt đầu s, một trạng thái đích t, và chi phí cạnh **không âm** `c(u,v)≥0`. Ta cần tìm đường s→t có **tổng chi phí nhỏ nhất**; nếu không có đường thì báo không tìm thấy.

A* sử dụng:

- `g(v)`: **chi phí nhỏ nhất đã biết** của một đường thật sự từ s đến v. Giá trị **có thể giảm** khi có đường khác tốt hơn.
- `h(v)`: ước lượng chi phí còn lại từ v đến t; đây là tri thức heuristic, không phải độ dài đã đi.
- `f(v)=g(v)+h(v)`: độ ưu tiên trong hàng đợi `OPEN`.
- `parent(v)`: tiền nhiệm tạo đường đạt `g(v)` hiện hành, dùng dựng lời giải.

`OPEN` là hàng đợi ưu tiên lấy **f nhỏ nhất**. `CLOSED` là tập trạng thái đã được **lấy ra và mở rộng** (*expanded*) với g đang biết.

**Bốn động từ không đồng nghĩa:**

1. **Generate/discover:** mới nhìn thấy một trạng thái khi xét cạnh từ đỉnh đang mở rộng.
2. **Relax/update:** tìm được `candidate=g(u)+c(u,v)` nhỏ hơn g(v) đã lưu và cập nhật g(v), parent(v).
3. **Pop/extract-min:** lấy một entry có độ ưu tiên nhỏ nhất trong OPEN, **sau khi bỏ các entry stale**.
4. **Expand/close:** xét các cạnh xuất phát từ state vừa pop hợp lệ rồi đánh dấu trạng thái đã được xử lý ở g đó.

**Reopen** nghĩa là một đỉnh đã ở CLOSED được phát hiện đường mới rẻ hơn: `candidate < bestG[v]`; khi ấy xóa cờ CLOSED và đưa lại v vào OPEN.

**Stale entry** là bản ghi trong priority queue giữ một `g` cũ khác `bestG[v]`, hoặc một bản ghi trùng cho đỉnh đã được close ở cùng g. Entry stale **không được expand** hay dùng làm lý do dừng.

### 1.1. Vì sao không dùng `visited` đơn giản?

Trạng thái “đã được nhìn thấy” **không có nghĩa** đã tìm được đường rẻ nhất đến nó. Thậm chí với heuristic không nhất quán, trạng thái **đã pop và close** cũng có thể được tìm thấy với g tốt hơn. Gộp cả hai ý nghĩa vào một `visited` rồi từ chối mọi đường mới là một lỗi phổ biến.

### 1.2. A* khi `h=0`

Nếu h(v)=0 trên toàn bộ V thì f=g, thứ tự tìm kiếm như **Dijkstra**, với điều kiện chi phí cạnh không âm. Một trạng thái được pop hợp lệ lần đầu đã đạt g tối ưu, nên **không cần reopen**. Tuy vậy vẫn phải loại bỏ **stale PQ entries** nếu triển khai bằng cách push một entry mới thay vì decrease-key.

### 1.3. Giả thiết của bảo đảm tối ưu

Trong bài học này, các định lý áp dụng cho đồ thị trạng thái hữu hạn, chi phí cạnh **không âm**, h cố định theo trạng thái, **`h(t)=0`**, h không âm, và tìm kiếm không bị chặn tùy tiện bởi thời gian hay bộ nhớ. Cạnh cost 0 **hợp lệ**; cạnh âm không thuộc mô hình chứng minh Dijkstra/A* chuẩn ở đây.

Nếu các điều kiện đổi (weighted heuristic, trạng thái động, edge cost thay đổi, âm, tìm beam/approximate), phải chứng minh lại tính đúng theo bài toán mới.

## 2. Heuristic admissible và consistent

Đặt `d*(v,t)` là chi phí đường ngắn nhất từ v tới t, và bằng ∞ nếu không có đường.

### 2.1. Admissible — không dự đoán quá cao

Heuristic **admissible** khi:

`0 ≤ h(v) ≤ d*(v,t)` cho mọi state có đường đến t, và `h(t)=0`.

Điều này nói h là **cận dưới** cho chi phí còn lại thực sự. Nếu g(v) là chi phí một đường s→v có thật, thì `g(v)+h(v)` là cận dưới cho chi phí của lời giải hoàn thiện đường ấy đến t.

**Không** suy ra rằng h tuân theo bất đẳng thức tam giác trên từng cạnh. Vì vậy f có thể **giảm** sau một bước.

### 2.2. Consistent — nhất quán giữa hai state kề nhau

Heuristic **consistent** nếu trên **mọi cạnh có hướng** u→v:

`h(u) ≤ c(u,v) + h(v)`,

đồng thời `h(t)=0`.

Đi dọc một đường với chi phí tích lũy g, ta có:

`g(u)+h(u) ≤ g(u)+c(u,v)+h(v)`.

Vì vậy **f không giảm dọc phép mở rộng cạnh** khi xét cùng đường đi. Tính chất này giúp chứng minh: **lần pop hợp lệ đầu tiên của một trạng thái có g tối ưu**.

Với cạnh không âm và h(t)=0, **consistent ⇒ admissible**: cộng các bất đẳng thức cạnh dọc đường ngắn nhất đến t. Nhưng **admissible không kéo theo consistent**.

### 2.3. Bảng quyết định

| Điều kiện h | CLOSED khóa vĩnh viễn? | Có thể dừng ở goal pop hợp lệ? |
|---|---|---|
| h=0 | Có | Có |
| h **consistent** | Có | Có |
| h **admissible nhưng inconsistent** | **Không bảo đảm**; cần reopen | Có, **nếu reopen đúng** |
| h có thể **overestimate** | Reopen không đủ để cứu bảo đảm | Goal pop có thể **không tối ưu** |

Điều kiện “goal pop” luôn giả định `h(goal)=0` và trọng số cạnh không âm. Mọi câu khẳng định tối ưu còn dựa trên việc không cắt tỉa những state cần thiết.

## 3. Phản ví dụ đầy đủ: admissible nhưng không nhất quán

Xét bốn state `S` (start), `A`, `B`, `G` (goal):

```text
             3                2
        S --------> A --------------> G
         \          ^
          \ 1       | 1
           v        |
            B ------+
```

Các cạnh có hướng:

| Cạnh | Cost |
|---|---:|
| S→A | 3 |
| S→B | 1 |
| B→A | 1 |
| A→G | 2 |

Chi phí thật còn lại:

| v | `d*(v,G)` |
|---|---:|
| S | 4 |
| A | 2 |
| B | 3 |
| G | 0 |

Đường tối ưu là `S→B→A→G` có tổng **4**. Đường `S→A→G` có tổng **5**.

Chọn heuristic:

`h(S)=3`, `h(A)=0`, `h(B)=3`, `h(G)=0`.

Từng giá trị đều không vượt chi phí thật, nên heuristic **admissible**.

Nhưng cạnh B→A cost1 vi phạm consistency:

`h(B)=3 > c(B,A)+h(A)=1+0=1`.

Heuristic **inconsistent**.

### 3.1. Chạy A* có reopen

Ban đầu `S(g=0,h=3,f=3)`. Expand S tạo:

- `A(g=3,h=0,f=3)`.
- `B(g=1,h=3,f=4)`.

A được pop trước B vì f(A)=3 <f(B)=4. Expand A tạo G(g=5,f=5), rồi đóng A ở g=3.

B được pop tiếp. Từ B→A, chi phí mới:

`g(B)+c(B,A)=1+1=2 < g(A)=3`.

A đã closed, nhưng đường mới tốt hơn. **Reopen A**:

- `g(A)=2`.
- `parent(A)=B`.
- `closed[A]=false`.
- Thêm entry A(g=2,f=2) vào OPEN.

A pop và expand **lần thứ hai**, cập nhật G từ g5 xuống **g4**. Goal G được pop hợp lệ với f=g=4, trả `S→B→A→G`.

| Lượt expand | State | g | f | Sự kiện |
|---:|---|---:|---:|---|
| 1 | S | 0 | 3 | Generate A và B |
| 2 | A | 3 | 3 | Generate G(g5), close A |
| 3 | B | 1 | 4 | Cải thiện A từ g3 xuống g2, **reopen** |
| 4 | A | 2 | 2 | Cải thiện G từ g5 xuống g4 |
| 5 | G | 4 | 4 | Pop goal hợp lệ, dừng tối ưu |

Lưu ý **f giảm** từ f(B)=4 xuống f(A)=2 sau bước B→A. Đây chính là hành vi heuristic inconsistent cho phép.

### 3.2. Cấm reopen trả sai cost

Nếu A bị khóa vĩnh viễn sau lượt expand ở g3, B phát hiện đường tới A giá2 nhưng bị bỏ qua vì A closed. Thuật toán cuối cùng pop G(g5), trả `S→A→G`, **cost 5**.

Đây không phải lỗi ở tính **admissible**; lỗi là dùng quy tắc CLOSED chỉ an toàn khi heuristic **consistent**.

### 3.3. Thay h bằng heuristic consistent

Chọn:

`h(S)=4`, `h(A)=2`, `h(B)=3`, `h(G)=0`.

Đây là chi phí ngắn nhất còn lại thực sự. Kiểm:

- S→A: 4≤3+2.
- S→B: 4≤1+3.
- B→A: 3≤1+2.
- A→G: 2≤2+0.

Tất cả thỏa consistency. A* chạy tới cost4 **không reopen**.

### 3.4. Admissible không đồng nghĩa tối ưu nếu đóng sai

Khi cài đặt A* graph search, phát biểu “h admissible thì A* luôn tối ưu” cần gắn với **cách xử lý các trạng thái trùng**. Bản không reopen ở graph có h inconsistent **không** có cam kết đó. Bản cho phép cải thiện g và mở lại trạng thái mới giữ bảo đảm tối ưu cho graph search chuẩn.

## 4. Nguyên tắc reopen và lazy priority queue

A* nên giữ ba cấu trúc tách biệt:

- `bestG[state]`: đường tốt nhất được tìm thấy.
- `closed[state]`: trạng thái đã được expand ở lần g hiện hành.
- `OPEN`: priority queue chứa các entry `(state,gSnapshot,fSnapshot)`.

### 4.1. Pseudocode relax đúng

```text
tentative = bestG[u] + cost(u,v)

if chưa thấy v OR tentative < bestG[v]:
    bestG[v] = tentative
    parent[v] = u

    if closed[v]:
        closed[v] = false             // REOPEN.

    OPEN.push(v, tentative, tentative + h[v])
```

**Chỉ cải thiện khi nhỏ hơn nghiêm ngặt**. Với cạnh cost0 và chu trình có cost0, dùng `<=` và push lại liên tục có thể lặp vô hạn hoặc phát sinh rất nhiều bản ghi trùng không cần thiết.

### 4.2. Pseudocode pop đúng

```text
while OPEN không rỗng:
    entry = OPEN.popMinF()
    u = entry.state

    if entry.gSnapshot != bestG[u] OR closed[u]:
        continue                      // Bỏ entry stale.

    closed[u] = true
    if u == goal:
        return bestG[u], reconstruct(parent)

    for mỗi cạnh u->v:
        relax(u,v)
```

Kiểm **stale trước** kiểm goal. Nếu không, một entry goal cũ có thể được dùng như kết quả cuối sau khi goal đã có g tốt hơn.

### 4.3. Vì sao Java PriorityQueue thường có duplicate?

Trong Java, `PriorityQueue` không có một thao tác decrease-key thuận tiện theo khóa state. Khi tìm g mới rẻ hơn cho v, cách thông dụng là **push entry mới** và để entry cũ ở heap. Lúc pop phải so snapshot với bestG hiện tại.

Stale entry **không nhất thiết đồng nghĩa reopen**. Khi một state vẫn ở OPEN mà nhận g tốt hơn, entry cũ đã stale dù nó **chưa bao giờ closed**.

### 4.4. Parent phải cập nhật cùng g

Nếu `bestG[A]` đổi từ 3 sang 2 qua B, phải đổi `parent[A]` từ S sang B. Nếu chỉ cập nhật g, chương trình có thể báo cost4 nhưng in path `S→A→G` thực tế cost5.

### 4.5. Trạng thái phải là khóa đầy đủ

Khi áp dụng A* cho robot hoặc puzzle, khóa state phải gồm mọi thông tin ảnh hưởng hành động tương lai: vị trí, chìa khóa, nhiên liệu, trạng thái công tắc, lượt đi, v.v. Hai state cùng tọa độ nhưng khác chìa khóa **không được gộp** vào cùng CLOSED nếu bước đi hợp lệ khác nhau.

## 5. Dừng A* như thế nào mới đúng?

Có hai thời điểm khác nhau khi xử lý đích t:

- **Goal generated:** vừa tìm được một đường đến t và đưa t vào OPEN.
- **Goal popped:** t được lấy khỏi OPEN bằng một entry **hợp lệ**, đang có f tối thiểu.

### 5.1. Quy tắc dừng chuẩn

Với h **admissible**, h(t)=0, chi phí cạnh không âm, relax và reopen đúng khi cần, có thể **dừng ngay khi goal được pop hợp lệ**. Giá trị g(t) khi ấy là chi phí tối ưu.

Nếu h **consistent**, không cần reopen trạng thái đã closed nhưng vẫn chỉ nên dừng khi goal được pop hợp lệ, không phải ngay khi generate.

### 5.2. Phản ví dụ dừng khi generate — ngay cả h=0

Đồ thị:

```text
S → G : 10
S → X :  1
X → G :  1
```

Tất cả h=0, tức admissible và consistent.

Nếu xét cạnh S→G trước và dừng **ngay lúc nhìn thấy goal**, đáp án là **10**. Nhưng đường `S→X→G` có cost **2**.

Thuật toán đúng sau khi expand S giữ trong OPEN:

`X(g=1,f=1)` và `G(g=10,f=10)`.

X được pop trước, tìm đường mới tới G cost2. Khi entry G(g=2) được pop hợp lệ, đáp án **2**.

**Tính nhất quán không làm quy tắc goal-generation trở nên an toàn.**

### 5.3. Lập luận tối ưu tại thời điểm goal pop

Giả sử goal t được pop hợp lệ với g=C, do h(t)=0 nên f(t)=C.

Nếu còn đường tối ưu chưa được phát hiện có cost C*<C, trên đường đó phải có một trạng thái ở **frontier OPEN** đạt đường prefix tốt nhất, hoặc một trạng thái đã được cải thiện và được **reopen**. Nếu không, các relax dọc đường đã đưa goal với cost≤C* vào OPEN từ trước.

Với trạng thái frontier x và h admissible:

`f(x)=g*(x)+h(x) ≤ g*(x)+d*(x,t) = C* < C`.

Nhưng OPEN lấy f nhỏ nhất, không thể pop t có f=C trước entry x có f<C. Mâu thuẫn. Vậy **C là tối ưu**.

Trong chứng minh này, việc **reopen** bảo đảm một đỉnh từng được closed ở g quá cao không bị loại vĩnh viễn khỏi phần frontier cần thiết.

### 5.4. Điều kiện dừng theo incumbent

Thay vì chờ pop goal, có thể lưu `bestGoalCost` khi **tìm được một đường hoàn chỉnh tới goal**. Đặt:

`LB = min { bestG(x)+h(x) : x còn là entry OPEN hợp lệ }`.

Nếu **`bestGoalCost ≤ LB`**, lời giải goal hiện có đã đạt cận dưới của mọi lời giải chưa xét. Khi h admissible và xử lý reopen đầy đủ, có thể dừng và công bố **chi phí tối ưu**.

Nếu OPEN không còn entry hợp lệ, quy ước `LB=∞`.

Ví dụ ở phần 3, khi lần đầu thấy G cost5, OPEN vẫn có B với f4:

`bestGoalCost=5`, `LB=4`, nên **không được dừng**.

Lưu ý phải loại các entry stale và closed không hợp lệ trước khi tính LB. Nếu yêu cầu **liệt kê tất cả đường tối ưu** hoặc tiêu chí phụ giữa các đường cùng cost, điều kiện bằng nhau có thể chưa đủ để thu thập mọi nghiệm.

### 5.5. Dừng khi OPEN cạn

Nếu OPEN hết entry hợp lệ mà chưa từng tìm ra goal, **không có đường** từ s đến t trong đồ thị đã mô hình hóa. Trả trạng thái `NOT_FOUND`, không trả `Long.MAX_VALUE` như thể đó là chi phí thật.

### 5.6. Timeout và giới hạn bộ nhớ

Dừng khi quá N expansions, hết thời gian hoặc dùng beam width có thể trả **một nghiệm đang có**, nhưng không tự động chứng minh tối ưu. Hãy tách `FOUND_UNPROVEN` khỏi `FOUND_OPTIMAL` trong API ứng dụng.

## 6. Inadmissible: reopen vẫn không bảo đảm tối ưu

Trở lại graph bốn trạng thái, chọn:

`h(S)=0`, `h(A)=0`, `h(B)=10`, `h(G)=0`.

Chi phí thật từ B tới G bằng3, nên `h(B)=10` **ước lượng quá cao**, heuristic không admissible.

Sau expand S:

- A: `g=3,f=3`.
- B: `g=1,f=11`.

A pop trước, generate G(g5,f5). G có f5 nhỏ hơn B f11, nên **goal được pop với cost5** dù đường tối ưu qua B chỉ cost4.

Ở đây việc cài reopen hoàn chỉnh cũng **không cứu được** chứng minh tối ưu, vì bản thân h đã vi phạm lower bound.

**Weighted A\*** dùng `f_w=g+w·h` với w>1 có thể rơi vào tình huống tương tự: thứ tự goal-pop theo f_w **không chứng minh tối ưu chính xác** bằng định lý A* admissible chuẩn. Những bảo đảm xấp xỉ, nếu có, thuộc các giả thiết và phân tích riêng.

### 6.1. Heuristic từ khoảng cách hình học

Manhattan distance thường admissible và consistent cho lưới bốn hướng, mỗi bước chi phí ít nhất1. Nhưng nếu graph có cổng dịch chuyển cost0, đường tắt rất rẻ hoặc cho di chuyển nhanh hơn mô hình Manhattan, dùng nguyên khoảng cách ấy có thể **overestimate**. Không kết luận heuristic tốt chỉ vì nó quen thuộc; phải so với **cost thực tế của các chuyển trạng thái**.

## 7. Java 17 — A* cho phép reopen và bỏ stale entry

Chương trình đầu tiên bao gồm:

- `bestG`, `reached`, `closed` độc lập.
- `PriorityQueue` sắp `f`, rồi `g`, ID state, serial.
- Ghi `parent` ngay lúc relax tốt hơn.
- Cho phép **reopen** một state closed nếu g mới nhỏ hơn.
- Bỏ **stale entry** trước khi xét goal.
- Tùy chọn `allowReopen=false` **chỉ để minh họa sai lầm** trên h inconsistent.

Lưu thành **AStarReopenStatesDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.StringJoiner;

public class AStarReopenStatesDemo {
    record Edge(int to, long cost) {}
    record Item(int u, long g, long f, long sequence) {}
    record Result(boolean found, long cost, List<Integer> path,
                  int expanded, int reopened, int stale) {}

    static List<List<Edge>> makeGraph(int n) {
        List<List<Edge>> graph = new ArrayList<>();
        for (int i = 0; i < n; i++) graph.add(new ArrayList<>());
        return graph;
    }

    static void add(List<List<Edge>> graph, int u, int v, long cost) {
        if (u < 0 || u >= graph.size() || v < 0 || v >= graph.size()
                || cost < 0) {
            throw new IllegalArgumentException("Invalid edge");
        }
        graph.get(u).add(new Edge(v, cost));
    }

    static Result search(List<List<Edge>> graph, long[] h,
                         int start, int goal, boolean allowReopen) {
        int n = graph.size();
        if (n == 0 || h.length != n || start < 0 || start >= n
                || goal < 0 || goal >= n || h[goal] != 0) {
            throw new IllegalArgumentException("Invalid problem");
        }
        for (long value : h) {
            if (value < 0) throw new IllegalArgumentException("Negative h");
        }
        for (List<Edge> edges : graph) {
            for (Edge e : edges) {
                if (e.to() < 0 || e.to() >= n || e.cost() < 0) {
                    throw new IllegalArgumentException("Invalid edge");
                }
            }
        }

        PriorityQueue<Item> open = new PriorityQueue<>(
                Comparator.comparingLong(Item::f)
                        .thenComparingLong(Item::g)
                        .thenComparingInt(Item::u)
                        .thenComparingLong(Item::sequence));
        long[] bestG = new long[n];
        boolean[] reached = new boolean[n], closed = new boolean[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        long sequence = 0L;
        reached[start] = true;
        bestG[start] = 0L;
        open.add(new Item(start, 0L, h[start], sequence++));

        int expanded = 0, reopened = 0, stale = 0;

        while (!open.isEmpty()) {
            Item current = open.poll();
            int u = current.u();

            if (!reached[u] || current.g() != bestG[u] || closed[u]) {
                stale++;
                continue;
            }

            closed[u] = true;
            expanded++;

            // Kiểm goal SAU KHI pop hợp lệ.
            if (u == goal) {
                List<Integer> path = new ArrayList<>();
                for (int v = goal; v != -1; v = parent[v]) {
                    path.add(v);
                }
                Collections.reverse(path);
                return new Result(true, bestG[goal],
                        List.copyOf(path), expanded, reopened, stale);
            }

            for (Edge edge : graph.get(u)) {
                int v = edge.to();
                if (closed[v] && !allowReopen) {
                    continue; // Chế độ cố ý sai khi h inconsistent.
                }

                long candidate = Math.addExact(bestG[u], edge.cost());
                if (!reached[v] || candidate < bestG[v]) {
                    if (closed[v]) {
                        closed[v] = false;
                        reopened++;
                    }

                    reached[v] = true;
                    bestG[v] = candidate;
                    parent[v] = u;
                    long f = Math.addExact(candidate, h[v]);
                    open.add(new Item(v, candidate, f, sequence++));
                }
            }
        }

        return new Result(false, 0L, List.of(),
                expanded, reopened, stale);
    }

    static String describe(Result result, String[] names) {
        if (!result.found()) return "none expanded=" + result.expanded();
        StringJoiner path = new StringJoiner(" -> ");
        for (int u : result.path()) path.add(names[u]);
        return "cost=" + result.cost()
                + " path=" + path
                + " expanded=" + result.expanded()
                + " reopened=" + result.reopened()
                + " stale=" + result.stale();
    }

    static List<List<Edge>> example() {
        // ID 0=S, 1=A, 2=B, 3=G.
        List<List<Edge>> g = makeGraph(4);
        add(g, 0, 1, 3); // S->A
        add(g, 0, 2, 1); // S->B
        add(g, 2, 1, 1); // B->A
        add(g, 1, 3, 2); // A->G
        return g;
    }

    public static void main(String[] args) {
        List<List<Edge>> graph = example();
        String[] names = {"S", "A", "B", "G"};

        long[] inconsistent = {3, 0, 3, 0};
        long[] consistent = {4, 2, 3, 0};
        long[] dijkstra = {0, 0, 0, 0};
        long[] overestimate = {0, 0, 10, 0};

        System.out.println("Inconsistent reopen: "
                + describe(search(graph, inconsistent, 0, 3, true), names));
        System.out.println("Inconsistent no-reopen: "
                + describe(search(graph, inconsistent, 0, 3, false), names));
        System.out.println("Consistent no-reopen: "
                + describe(search(graph, consistent, 0, 3, false), names));
        System.out.println("Heuristic zero: "
                + describe(search(graph, dijkstra, 0, 3, true), names));
        System.out.println("Overestimate reopen: "
                + describe(search(graph, overestimate, 0, 3, true), names));

        List<List<Edge>> noPath = makeGraph(3);
        add(noPath, 0, 1, 2);
        System.out.println("No path: "
                + describe(search(noPath, new long[]{0, 0, 0},
                        0, 2, true), new String[]{"S", "X", "G"}));

        List<List<Edge>> single = makeGraph(1);
        System.out.println("Start equals goal: "
                + describe(search(single, new long[]{0}, 0, 0, true),
                        new String[]{"S"}));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 AStarReopenStatesDemo.java
java AStarReopenStatesDemo
```

Stdout:

```text
Inconsistent reopen: cost=4 path=S -> B -> A -> G expanded=5 reopened=1 stale=0
Inconsistent no-reopen: cost=5 path=S -> A -> G expanded=4 reopened=0 stale=0
Consistent no-reopen: cost=4 path=S -> B -> A -> G expanded=4 reopened=0 stale=0
Heuristic zero: cost=4 path=S -> B -> A -> G expanded=4 reopened=0 stale=1
Overestimate reopen: cost=5 path=S -> A -> G expanded=3 reopened=0 stale=0
No path: none expanded=2
Start equals goal: cost=0 path=S expanded=1 reopened=0 stale=0
```

### 7.1. Giải thích `expanded=5` và `reopened=1`

Có 4 state phân biệt nhưng A được mở rộng **hai lần**. Trình tự là `S,A,B,A,G`, nên expanded=5; state A được reopen **một lần**.

### 7.2. Vì sao `stale=1` khi h=0?

Khi S expand, entry A(g3) và B(g1) vào OPEN. B được pop trước và cải thiện A thành g2, push **entry A(g2)**. A(g2) được expand; entry cũ A(g3) sau đó bị pop và bỏ qua vì `entry.g != bestG[A]`, nên `stale=1`. A chưa từng closed trước khi g được cải thiện nên `reopened=0`.

### 7.3. Math.addExact để làm gì?

Khi chi phí lớn, `g+c` hoặc `g+h` tràn long có thể thành số âm, khiến heap ưu tiên sai. `Math.addExact` báo lỗi rõ thay vì âm thầm sai kết quả. Với cost có thể vượt miền long, thay bằng kiểu số lớn, ví dụ `BigInteger`. Comparator dùng `comparingLong`, không viết `a.f-b.f` rồi ép int.

### 7.4. Tại sao cần reset dữ liệu giữa các lần chạy?

`bestG`, `closed`, `reached`, `parent` và heap thuộc **một phiên tìm kiếm**. Chương trình tạo mới các mảng trong `search`; nếu tái sử dụng cờ closed từ lần chạy heuristic trước thì dễ trả sai.

### 7.5. Đừng dùng `allowReopen=false` với h chưa được chứng minh consistent

Chế độ false trong demo là **một thí nghiệm so sánh**, không phải đề xuất production. Nếu chỉ biết h admissible hoặc nghi ngờ inconsistent, bật reopen. Chỉ tối ưu bỏ reopen sau khi có chứng minh consistency của heuristic trên mọi chuyển trạng thái.

## 8. Java 17 — dừng khi goal generate hay goal pop?

Ví dụ thứ hai cố ý dùng h=0 để cho thấy lỗi dừng sớm **không phụ thuộc vào heuristic inconsistent**.

Lưu thành **AStarGoalStopDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class AStarGoalStopDemo {
    record Edge(int to, long cost) {}
    record Entry(int u, long g) {}

    static List<List<Edge>> sample() {
        List<List<Edge>> g = new ArrayList<>();
        for (int i = 0; i < 3; i++) g.add(new ArrayList<>());
        g.get(0).add(new Edge(2, 10)); // S->G đầu tiên
        g.get(0).add(new Edge(1, 1));  // S->X
        g.get(1).add(new Edge(2, 1));  // X->G
        return g;
    }

    static long wrongFirstGenerated(List<List<Edge>> g) {
        for (Edge e : g.get(0)) {
            if (e.to() == 2) return e.cost();
        }
        return -1L;
    }

    static long correctGoalPop(List<List<Edge>> g) {
        long[] dist = {0L, Long.MAX_VALUE, Long.MAX_VALUE};
        PriorityQueue<Entry> pq = new PriorityQueue<>(
                Comparator.comparingLong(Entry::g)
                        .thenComparingInt(Entry::u));
        pq.add(new Entry(0, 0L));

        while (!pq.isEmpty()) {
            Entry x = pq.poll();
            if (x.g() != dist[x.u()]) continue; // Stale.
            if (x.u() == 2) return x.g();       // Goal pop hợp lệ.

            for (Edge e : g.get(x.u())) {
                long candidate = Math.addExact(x.g(), e.cost());
                if (candidate < dist[e.to()]) {
                    dist[e.to()] = candidate;
                    pq.add(new Entry(e.to(), candidate));
                }
            }
        }
        return -1L;
    }

    static long safeIncumbentBound(List<List<Edge>> g) {
        long[] dist = {0L, Long.MAX_VALUE, Long.MAX_VALUE};
        long bestGoal = Long.MAX_VALUE;
        PriorityQueue<Entry> pq = new PriorityQueue<>(
                Comparator.comparingLong(Entry::g)
                        .thenComparingInt(Entry::u));
        pq.add(new Entry(0, 0L));

        while (!pq.isEmpty()) {
            while (!pq.isEmpty()
                    && pq.peek().g() != dist[pq.peek().u()]) {
                pq.poll(); // Bỏ stale trước khi đo min OPEN.
            }
            if (pq.isEmpty()) break;

            long lowerBound = pq.peek().g(); // h=0.
            if (bestGoal != Long.MAX_VALUE
                    && bestGoal <= lowerBound) {
                return bestGoal; // Đã chứng minh tối ưu theo cost.
            }

            Entry x = pq.poll();
            if (x.u() == 2) return x.g();
            for (Edge e : g.get(x.u())) {
                long candidate = Math.addExact(x.g(), e.cost());
                if (candidate < dist[e.to()]) {
                    dist[e.to()] = candidate;
                    pq.add(new Entry(e.to(), candidate));
                    if (e.to() == 2 && candidate < bestGoal) {
                        bestGoal = candidate;
                    }
                }
            }
        }

        return bestGoal == Long.MAX_VALUE ? -1L : bestGoal;
    }

    public static void main(String[] args) {
        List<List<Edge>> g = sample();
        System.out.println("Wrong goal generated: "
                + wrongFirstGenerated(g));
        System.out.println("Correct goal popped: "
                + correctGoalPop(g));
        System.out.println("Safe lower bound stop: "
                + safeIncumbentBound(g));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 AStarGoalStopDemo.java
java AStarGoalStopDemo
```

Stdout:

```text
Wrong goal generated: 10
Correct goal popped: 2
Safe lower bound stop: 2
```

**Giải thích:** ngay sau khi thấy goal cost10, OPEN vẫn có X(g1), nên lower bound 1 < incumbent10 và không được dừng. Sau khi mở rộng X, goal được cải thiện xuống cost2; lúc này min hợp lệ của OPEN đã bằng2, nên điều kiện `incumbent≤LB` được thỏa.

`Long.MAX_VALUE` chỉ là sentinel tiện dụng cho demo nhỏ. Nếu đường thật có chi phí đúng bằng giá trị này, cần cờ `reached` riêng hoặc kiểu số tùy ý như ở mã A* chính.

## 9. Java 17 — audit heuristic bằng khoảng cách thật trên graph đảo

Để phân biệt admissibility và consistency trên graph nhỏ, có thể tính `d*(v,goal)` **độc lập**:

1. Đảo chiều mỗi cạnh có hướng u→v thành v→u, giữ nguyên chi phí.
2. Chạy Dijkstra từ goal trên **graph đảo**.
3. Khoảng cách từ goal đến v trong graph đảo là `d*(v,goal)` của graph ban đầu.

Sau đó:

- Admissible: `h(v)≤d*(v,goal)` khi v reachable tới goal.
- Consistent: `h(u)≤c(u,v)+h(v)` với **từng cạnh gốc**.

Lưu thành **AStarHeuristicCheckDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class AStarHeuristicCheckDemo {
    record Edge(int to, long cost) {}
    record Entry(int u, long dist) {}
    record Audit(boolean admissible, boolean consistent,
                 String firstViolation) {}

    static List<List<Edge>> graph(int n) {
        List<List<Edge>> g = new ArrayList<>();
        for (int i = 0; i < n; i++) g.add(new ArrayList<>());
        return g;
    }

    static void add(List<List<Edge>> g, int u, int v, long w) {
        if (w < 0 || u < 0 || u >= g.size()
                || v < 0 || v >= g.size()) {
            throw new IllegalArgumentException("Invalid edge");
        }
        g.get(u).add(new Edge(v, w));
    }

    static long[] distanceToGoal(List<List<Edge>> g, int goal) {
        int n = g.size();
        List<List<Edge>> reversed = graph(n);
        for (int u = 0; u < n; u++) {
            for (Edge e : g.get(u)) {
                add(reversed, e.to(), u, e.cost());
            }
        }

        long[] dist = new long[n];
        Arrays.fill(dist, Long.MAX_VALUE);
        dist[goal] = 0L;

        PriorityQueue<Entry> pq = new PriorityQueue<>(
                Comparator.comparingLong(Entry::dist)
                        .thenComparingInt(Entry::u));
        pq.add(new Entry(goal, 0L));

        while (!pq.isEmpty()) {
            Entry cur = pq.poll();
            if (cur.dist() != dist[cur.u()]) continue;
            for (Edge e : reversed.get(cur.u())) {
                long candidate = Math.addExact(cur.dist(), e.cost());
                if (candidate < dist[e.to()]) {
                    dist[e.to()] = candidate;
                    pq.add(new Entry(e.to(), candidate));
                }
            }
        }
        return dist;
    }

    static Audit check(List<List<Edge>> g, long[] h, int goal) {
        if (h.length != g.size() || h[goal] != 0) {
            throw new IllegalArgumentException("Invalid heuristic");
        }

        long[] truth = distanceToGoal(g, goal);
        boolean admissible = true, consistent = true;
        String firstViolation = "none";
        String[] label = {"S", "A", "B", "G"};

        for (int u = 0; u < g.size(); u++) {
            if (h[u] < 0
                    || (truth[u] != Long.MAX_VALUE
                        && h[u] > truth[u])) {
                admissible = false;
            }

            for (Edge e : g.get(u)) {
                if (h[u] > Math.addExact(e.cost(), h[e.to()])) {
                    consistent = false;
                    if (firstViolation.equals("none")) {
                        firstViolation = label[u] + "->" + label[e.to()];
                    }
                }
            }
        }
        return new Audit(admissible, consistent, firstViolation);
    }

    static List<List<Edge>> sample() {
        List<List<Edge>> g = graph(4);
        add(g, 0, 1, 3);
        add(g, 0, 2, 1);
        add(g, 2, 1, 1);
        add(g, 1, 3, 2);
        return g;
    }

    public static void main(String[] args) {
        List<List<Edge>> g = sample();
        System.out.println("True remaining costs: "
                + Arrays.toString(distanceToGoal(g, 3)));

        Audit a = check(g, new long[]{3, 0, 3, 0}, 3);
        Audit b = check(g, new long[]{4, 2, 3, 0}, 3);
        Audit c = check(g, new long[]{0, 0, 10, 0}, 3);

        System.out.println("Inconsistent: admissible="
                + a.admissible() + ", consistent=" + a.consistent());
        System.out.println("First violation: " + a.firstViolation());
        System.out.println("Consistent: admissible="
                + b.admissible() + ", consistent=" + b.consistent());
        System.out.println("Overestimate: admissible="
                + c.admissible() + ", consistent=" + c.consistent());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 AStarHeuristicCheckDemo.java
java AStarHeuristicCheckDemo
```

Stdout:

```text
True remaining costs: [4, 2, 3, 0]
Inconsistent: admissible=true, consistent=false
First violation: B->A
Consistent: admissible=true, consistent=true
Overestimate: admissible=false, consistent=false
```

### 9.1. Tại sao đảo cạnh?

Dijkstra từ goal trên graph gốc có hướng tính các đường **đi từ goal**, trong khi ta cần chi phí **đi từ từng state tới goal**. Graph đảo là cách chuyển đúng bài toán. Nếu graph vô hướng, việc đảo thường không làm thay đổi khoảng cách, nhưng không được dựa vào điều này khi graph có hướng.

### 9.2. Consistency dễ kiểm hơn admissibility trên graph tường minh

Để kiểm consistency chỉ cần duyệt mỗi cạnh một lần và so `h(u)≤c+h(v)`. Để kiểm admissibility, cần chi phí thật `d*(u,t)` cho tất cả u, vốn tương đương giải shortest paths ngược về goal. Vì thế audit admissibility thường dùng để **thử graph nhỏ** chứ không nhất thiết dùng trong A* production.

## 10. Chứng minh vì sao h consistent không cần reopen

Giả sử h consistent và mọi chi phí cạnh không âm. Ta xét state u được pop hợp lệ **lần đầu**. Giả sử `g(u)>g*(u)`, với g* là chi phí ngắn nhất thật từ start.

Xét một đường s→u tối ưu. Trước thời điểm pop u, trên đường này phải có một trạng thái y ở biên OPEN có g bằng chi phí prefix tối ưu: lấy đỉnh đầu tiên chưa được mở rộng với g tối ưu; tiền nhiệm đã được mở rộng tối ưu và relax đúng nên đã đưa y vào OPEN.

Theo consistency, cộng dọc đoạn đường từ y tới u:

`h(y) ≤ cost(path y→u)+h(u)`.

Do đó:

`f(y)=g*(y)+h(y) ≤ g*(u)+h(u) < g(u)+h(u)=f(u)`.

Như vậy OPEN có entry y có f nhỏ hơn u, trái với việc u được pop có f nhỏ nhất. Mâu thuẫn. Vậy g(u) đã tối ưu lần đầu pop; **không cần reopen** state closed.

Nếu h chỉ admissible, ta **không** có bất đẳng thức consistency trên đoạn y→u và lập luận “first pop của u tối ưu” có thể thất bại. Vì vậy phải cho phép reopen.

### 10.1. Consistent vẫn có thể có stale PQ entry

Một state có thể nhận g tốt hơn **trước lần pop đầu**. Ví dụ h=0, S→A3, S→B1, B→A1. B được pop trước A, giảm g(A) từ3 xuống2. Bản ghi A(g3) trong PQ trở nên stale. Điều này **không phải reopen CLOSED** vì A chưa từng được expand.

### 10.2. Reopen làm độ phức tạp thay đổi

Với consistent h, mỗi state được expand tối đa một lần; heap và adjacency cho chặn thường dùng `O((V+E)log(V+E))` thời gian cho graph tường minh với các entry duplicate, bộ nhớ `O(V+E)` trong cách cài phổ biến.

Với inconsistent h và reopen, một state có thể expand nhiều lần. Không được tuyên bố “mỗi đỉnh chỉ mở rộng một lần”; trường hợp xấu có thể có rất nhiều lần reopen, thậm chí tăng theo hàm mũ ở một số họ graph.

Với graph hữu hạn, cost không âm và chỉ cập nhật khi g **giảm nghiêm ngặt**, chu trình cost0 không tự gây lặp vô hạn. Thực tế cần đo số lần expanded/reopened để đánh giá hiệu năng heuristic.

## 11. Điều kiện dừng theo mục đích sản phẩm

### 11.1. Một goal

Nếu chỉ cần **chi phí và một đường tối ưu**, goal pop hợp lệ là điều kiện đơn giản nhất. Nếu cần thoát sớm bằng `bestGoal≤minValidOpenF`, phải duy trì đúng cận dưới và không bỏ sót state cần reopen.

### 11.2. Nhiều goal

Với tập đích `G_goal`, có thể dừng ở **goal bất kỳ đầu tiên được pop hợp lệ** nếu h là cận dưới tới **goal rẻ nhất trong tập**, bằng0 ở các goal, và reopen đúng. Nếu yêu cầu một goal **cụ thể**, không được dừng khi chạm goal khác.

### 11.3. Nhiều đường cùng chi phí

Tie-break giữa các entry cùng f có thể thay đổi path in ra nhưng không làm thay đổi chi phí tối ưu dưới các tiền đề A* đúng. Nếu đề yêu cầu đường lexicographic nhỏ nhất hoặc **liệt kê mọi đường tối ưu**, có thể cần tiếp tục xử lý khi bound bằng incumbent và lưu nhiều parent. Điều kiện dừng theo cost không tự giải quyết yêu cầu phụ này.

### 11.4. Đồ thị/cost động

A* chuẩn giả định heuristic và chi phí cạnh **ổn định trong lần chạy**. Khi robot phát hiện vật cản mới, graph/cost thay đổi, một đường đã được chứng minh tối ưu cho graph cũ không còn nhất thiết tối ưu cho graph mới. Đây là bài toán **replanning**, nên dùng thuật toán thích hợp hoặc chạy lại với mô hình được cập nhật.

### 11.5. Trạng thái học được

Nếu h được cập nhật trong lúc tìm kiếm, một entry đã push với f cũ có thể không còn đúng thứ tự mới. Chỉ reopen khi g giảm **không tự động** bảo đảm A* như thể h cố định. Phải quản lý lại priority hoặc dùng thuật toán có chứng minh riêng.

## 12. Những sai lầm thường gặp

### Lỗi 1 — Nhầm admissible và consistent

Admissible là `h≤chi phí thật`. Consistent là điều kiện trên **từng cạnh**. Ví dụ B→A chứng minh một heuristic admissible vẫn inconsistent.

### Lỗi 2 — Khóa CLOSED mãi mãi

A được pop ở g3 rồi B tìm g2, nếu bỏ qua sẽ trả cost5 thay vì4. **Sửa:** reopen A khi g được cải thiện.

### Lỗi 3 — Chỉ push lại state mà quên xóa CLOSED

Entry mới A(g2) vào heap nhưng cờ closed[A] vẫn true, nên lúc pop bị bỏ qua. Cần `closed[A]=false` trước khi xử lý entry mới.

### Lỗi 4 — Update khi `candidate≤bestG`

Cạnh cost0 và cycle có thể tạo các lần push ngang giá vô ích, thậm chí lặp. Nếu chỉ cần một đường tối ưu, cập nhật khi `candidate<bestG`.

### Lỗi 5 — Không bỏ stale entries

Entry cũ còn trong PQ không phản ánh bestG mới. Kiểm gSnapshot và closed **trước** expand và trước điều kiện dừng goal.

### Lỗi 6 — Dừng ngay khi goal vừa được generate

S→G10 có thể được thấy trước S→X→G cost2 dù h consistent. **Sửa:** goal pop hoặc incumbent≤LB.

### Lỗi 7 — Overestimate h rồi vẫn cam kết optimal

Heuristic h(B)=10 trong graph mẫu làm goal cost5 được pop trước đường4. Reopen không sửa được h inadmissible.

### Lỗi 8 — Xếp hàng theo h thay vì g+h

Chỉ xét h là greedy best-first, không có bảo đảm tối ưu của A* chuẩn.

### Lỗi 9 — Không cập nhật parent

Cải thiện g(v) mà giữ predecessor cũ khiến path và chi phí không nhất quán.

### Lỗi 10 — Lẫn state với ô tọa độ

Cùng vị trí nhưng khác chìa khóa/nhiên liệu có thể dẫn tới tương lai khác nhau. State key phải chứa đủ thông tin.

### Lỗi 11 — Dùng cạnh cost âm

Chứng minh A* như Dijkstra cần cost không âm. Negative edges/cycles đòi mô hình và thuật toán khác.

### Lỗi 12 — Không bảo đảm `h(goal)=0`

Nếu h(goal) khác0, `f(goal)` không bằng g(goal), nên luật goal-pop/lower bound chuẩn phải được xem lại.

### Lỗi 13 — Overflow trong `g+c` hoặc `g+h`

Dùng `Math.addExact`, miền cost rõ ràng, hoặc BigInteger nếu cần. Overflow có thể khiến priority thành số âm.

### Lỗi 14 — Comparator dùng phép trừ

`(int)(f1-f2)` có thể overflow. Dùng `Comparator.comparingLong`.

### Lỗi 15 — So expanded với số đỉnh khác nhau

Khi reopen, một state có thể được expand nhiều lần. Ví dụ có 4 state nhưng 5 expansions.

### Lỗi 16 — Coi `stale` là `reopen`

Stale xuất hiện khi g giảm lúc state **chưa closed**. Reopen chỉ tính khi state closed nhận đường g tốt hơn.

### Lỗi 17 — Dùng min OPEN tính cả entry stale làm bound

Dùng những entry hợp lệ sau khi loại stale. Không tự coi tất cả bản ghi trong heap là frontier thật.

### Lỗi 18 — Giả định path duy nhất

Nhiều đường cost bằng nhau có thể dẫn tới parent khác nhau. Một đường tối ưu bất kỳ là hợp lệ trừ khi đề yêu cầu tie-break.

### Lỗi 19 — Dừng do timeout mà không phân biệt trạng thái bảo đảm

Nghiệm hiện có có thể chưa tối ưu. Báo `UNPROVEN` thay vì `OPTIMAL`.

### Lỗi 20 — Quên reset khi chạy lại

Lần chạy heuristic mới phải tạo bestG/closed/parent/OPEN mới, không dùng trạng thái cũ.

### Lỗi 21 — Tin heuristic “tốt trung bình”

Admissibility là yêu cầu không overestimate trên **mọi state**, không phải sai số trung bình nhỏ.

### Lỗi 22 — Kiểm consistency sai chiều cạnh

Với graph có hướng, chỉ xét cạnh thực tế u→v. Không được tự suy tồn tại v→u để áp bất đẳng thức ngược.

### Lỗi 23 — Kiểm admissibility bằng Dijkstra từ goal trên graph gốc

Muốn tính `d*(v,goal)`, chạy Dijkstra từ goal trên **graph đảo cạnh**. Chạy trên graph gốc có hướng tính chiều ngược mục tiêu.

### Lỗi 24 — Dùng weighted priority làm lower bound chính xác

`g+w·h` khi w>1 có thể lớn hơn chi phí thực còn lại; không dùng min weighted-f như min admissible-f để chứng minh optimal chính xác.

## 13. Bộ kiểm thử tối thiểu

| Tình huống | Kết quả đúng |
|---|---|
| Mẫu h admissible inconsistent `[3,0,3,0]` | Reopen ⇒ cost4, path S→B→A→G |
| Mẫu ấy, **cố ý cấm reopen** | Có thể sai: cost5 |
| Mẫu h consistent `[4,2,3,0]` | No-reopen ⇒ cost4, reopen0 |
| Mẫu h0 | Cost4; có thể xuất hiện stale A(g3) |
| Mẫu h overestimate `[0,0,10,0]` | Goal-pop có thể sai: cost5 |
| S→G10, S→X1, X→G1, h0 | Generate sai10; pop đúng2 |
| Start cũng là goal | Cost0, path chỉ chứa start |
| Goal không reachable | None |
| Cạnh cost0 và vòng cost0 | Không lặp do equal-cost relax |
| Cạnh song song | Relax chọn g tốt hơn; entry cũ stale |
| Hai lời giải bằng chi phí | Một đường tối ưu bất kỳ |
| Gần giới hạn long | Không overflow âm thầm |
| Graph có hướng | Kiểm consistency đúng chiều cạnh |

### 13.1. Oracle độc lập

Một test tự động đáng tin:

1. Sinh directed graph nhỏ có 2–7 trạng thái, cost trong `0..6`, cho phép self-loop, cạnh song song và goal không reachable.
2. Tính shortest path thật bằng **Floyd–Warshall** hoặc Dijkstra độc lập.
3. Tính khoảng cách từ từng state tới goal, rồi sinh `h(v)` ngẫu nhiên trong `[0,d*(v,t)]` nếu có đường, ngược lại h=0.
4. Chạy A* với **reopen**, so cost với oracle.
5. Chạy `h=0` và no-reopen, so với oracle.
6. Nếu heuristic do test sinh ra **consistent**, kiểm reopenCount=0.
7. Kiểm path bắt đầu s, kết thúc t và tổng chi phí cạnh đúng.
8. Chạy riêng phản ví dụ để chắc chắn phát hiện sai no-reopen.
9. Không ép hai thuật toán in cùng path nếu có nhiều nghiệm tối ưu.

Các test này xác nhận triển khai trên mẫu cụ thể; chứng minh vẫn cần để khẳng định mọi input thỏa tiền đề.

## 14. Bài tập tự luyện có đáp án

### Bài 1 — Tính f

Trạng thái x có `g(x)=7`, `h(x)=4`. `f(x)` bằng?

**Đáp án:** 11.

### Bài 2 — Admissibility

Chi phí thật từ B tới G là3, `h(B)=3`. Có admissible tại B?

**Đáp án:** có, vì h không vượt chi phí thật; phải kiểm các state khác để kết luận toàn heuristic.

### Bài 3 — Consistency

B→A cost1, h(B)=3, h(A)=0. Có consistent trên cạnh?

**Đáp án:** không, `3>1+0`.

### Bài 4 — Suy ra từ consistency

Với h(goal)=0 và edge cost không âm, consistent có suy ra admissible?

**Đáp án:** có, do cộng bất đẳng thức dọc đường ngắn nhất.

### Bài 5 — Chiều ngược

Admissible có nhất thiết consistent không?

**Đáp án:** không, mẫu S,A,B,G là phản ví dụ.

### Bài 6 — Reopen

A đã closed ở g3, B tìm g2. Bước đúng?

**Đáp án:** cập nhật g(A)=2, parent(A)=B, bỏ closed[A] và push A mới.

### Bài 7 — Cost bằng nhau

A closed ở g2, đường khác cũng tới A cost2. Có cần reopen để tìm một lời giải tối ưu?

**Đáp án:** không; dùng relax **nhỏ hơn nghiêm ngặt**.

### Bài 8 — Path tối ưu

Đường nào tốt nhất trong mẫu bốn state và cost?

**Đáp án:** S→B→A→G, `1+1+2=4`.

### Bài 9 — Cấm reopen

Nếu bỏ cải thiện A g3 thành g2, kết quả?

**Đáp án:** S→A→G cost5, không tối ưu.

### Bài 10 — h=0

A* với h=0 tương đương?

**Đáp án:** Dijkstra với nonnegative edge costs.

### Bài 11 — Stale entry

PQ có A(g3), A(g2), bestG[A]=2. Pop entry g3 làm gì?

**Đáp án:** bỏ qua, không expand.

### Bài 12 — Dừng khi generate

S→G cost10 được thấy đầu tiên nhưng S→X1,X→G1. Có nên dừng với10?

**Đáp án:** không, optimum2.

### Bài 13 — Dừng goal pop

H admissible, reopen đúng, goal pop ở cost C. C tối ưu?

**Đáp án:** có dưới tiền đề chuẩn (chi phí không âm, h(goal)=0, graph tĩnh, không cắt tỉa sai).

### Bài 14 — Lower bound

Incumbent goal9, minValidOpenF7. Có dừng?

**Đáp án:** không, vì 9>7.

### Bài 15 — Bound bằng incumbent

Incumbent9, mọi OPEN valid có f≥9. Có thể dừng về **giá trị tối ưu**?

**Đáp án:** có nếu h admissible và reopen/relax đúng.

### Bài 16 — Heuristic quá cao

B có true distance3 nhưng h(B)=10. Có admissible?

**Đáp án:** không.

### Bài 17 — Mục tiêu đã là start

Nếu s=t và h(t)=0, cost?

**Đáp án:** 0, đường chỉ chứa s.

### Bài 18 — Chu trình cost0

Vì sao chỉ relax khi g mới nhỏ hơn g cũ?

**Đáp án:** tránh push lại vô hạn những đường cùng chi phí qua vòng cost0.

### Bài 19 — Parent

G giảm g từ5 xuống4 mà parent không đổi, nguy cơ gì?

**Đáp án:** đường in ra có thể không khớp cost mới.

### Bài 20 — Consistent và stale

Heuristic consistent có thể vẫn có stale PQ entry không?

**Đáp án:** có; g có thể được cải thiện khi state còn ở OPEN.

### Bài 21 — Reopen count

Mẫu có 4 state nhưng 5 expansions. Vì sao?

**Đáp án:** A được expand hai lần sau reopen.

### Bài 22 — Audit heuristic có hướng

Tính chi phí từ mọi v tới goal bằng Dijkstra như thế nào?

**Đáp án:** đảo cạnh gốc rồi chạy từ goal.

### Bài 23 — Weighted A*

Dùng `g+2h` rồi dừng goal pop có chắc tối ưu chính xác?

**Đáp án:** không; weighted heuristic có thể overestimate và cần phân tích bảo đảm riêng.

### Bài 24 — State key

Hai trạng thái cùng vị trí nhưng khác chìa khóa có thể gộp CLOSED không?

**Đáp án:** không nếu chìa khóa ảnh hưởng bước đi/cost tương lai.

### Bài 25 — Timeout

Đã thấy một đường tới goal nhưng hết thời gian, có báo OPTIMAL không?

**Đáp án:** chỉ khi đã có chứng chỉ goal-pop hợp lệ hoặc incumbent≤lower bound; nếu không, báo chưa chứng minh tối ưu.

## 15. Checklist trước khi nộp lời giải A*

1. Chi phí cạnh có **không âm** theo tiền đề A* không?
2. State key có phân biệt đủ mọi yếu tố ảnh hưởng tương lai?
3. `h(goal)=0`, `h≥0` và có bằng chứng **admissible**?
4. Heuristic có bằng chứng **consistent** không?
5. Nếu chưa chứng minh consistent, đã hỗ trợ **reopen**?
6. Dùng `f=g+h`, không phải h?
7. Có `bestG`, `reached`, `closed` rõ ràng?
8. Relax khi `candidate<bestG`, không dùng ≤?
9. Khi cập nhật g, có cập nhật parent?
10. Nếu state closed được cải thiện, có xóa closed và push entry mới?
11. Có bỏ stale entries theo gSnapshot và trạng thái closed?
12. Goal được xét **sau pop hợp lệ**, không phải generate?
13. Nếu dùng incumbent, có đo `minValidOpenF` với h admissible?
14. Có tránh sai bảo đảm với weighted/inadmissible heuristic?
15. OPEN rỗng, goal chưa thấy có trả none?
16. Timeout hay beam search có đánh dấu chưa chứng minh tối ưu?
17. Có bảo vệ overflow trong cộng g/cost/h?
18. Comparator có dùng so long an toàn?
19. Có reset toàn bộ state giữa các lượt tìm?
20. Có kiểm path tái dựng đúng tổng g(goal)?
21. Có kiểm trường hợp goal=start, graph disconnected, cost0, parallel edges?
22. Có chạy Dijkstra/Floyd độc lập đối chiếu graph nhỏ?
23. Có dùng phản ví dụ admissible-inconsistent để kiểm reopen thật sự hoạt động?
24. Có kiểm heuristic nhất quán theo **đúng hướng** cạnh?

**Ghi nhớ:** A* chọn `f=g+h`. Nếu h **consistent**, lần đầu pop một trạng thái hợp lệ đã có g tối ưu, có thể khóa CLOSED. Nếu h **admissible nhưng inconsistent**, g của một state closed vẫn có thể giảm, nên phải **mở lại state**. Trong mọi trường hợp dùng lazy priority queue, phải **bỏ entry stale** trước khi xử lý. Không dừng khi goal **vừa được generate**; chỉ dừng ở **goal pop hợp lệ** hoặc khi có chứng chỉ `bestGoalCost≤minValidOpenF` với lower bound admissible và xử lý reopen đúng.

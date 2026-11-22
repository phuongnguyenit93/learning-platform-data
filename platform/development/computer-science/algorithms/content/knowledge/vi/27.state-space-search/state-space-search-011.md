# Tìm kiếm theo chùm (beam search) và giới hạn bảo đảm

## 1. Khái niệm và mục đích

**Beam search (tìm kiếm theo chùm)** là một thuật toán tìm kiếm **theo tầng với giới hạn số ứng viên giữ lại**. Nếu một trạng thái có nhiều hành động, cây các đường tìm kiếm có thể tăng theo hàm mũ của độ sâu. Beam search dùng một **hàm đánh giá (score)** để giữ tối đa **W ứng viên tốt nhất** ở mỗi tầng, rồi loại vĩnh viễn các ứng viên khác.

~~~text
Beam hien tai (toi da W node)
    -> sinh ung vien con
    -> tinh score
    -> sap xep cac ung vien cua TOAN BO tang
    -> giu top-W
    -> cat phan con lai
    -> chuyen sang tang tiep theo
~~~

**W** là beam width. W nhỏ tiết kiệm tài nguyên nhưng dễ loại nhánh tốt; W lớn giữ nhiều khả năng hơn nhưng cần thêm CPU và bộ nhớ. Beam search được sử dụng trong tìm kiếm trạng thái rộng, sinh chuỗi, dịch máy, nhận dạng tiếng nói và lập kế hoạch gần đúng.

**Sự đánh đổi chính:** beam search cố ý cắt nhánh. Nó nói chung **không complete** (có lời giải nhưng không chắc tìm được) và **không optimal** (tìm được nhưng không chắc tốt nhất). Dùng heuristic admissible/consistent cũng không tự xóa bỏ hai giới hạn này.

## 2. State, action, chi phí và node tìm kiếm

Một bài toán xác định có thể mô hình:

~~~text
S            tap state hop le
start        state ban dau
actions(s)   hanh dong cho phep
next(s,a)    state sau action a
cost(s,a)    chi phi cua buoc chuyen
goal(s)      dieu kien dich
score(n)     diem uu tien cua mot search node
W            beam width
Dmax         gioi han do sau
~~~

Một lời giải có dạng:

~~~text
start --a1/c1--> s1 --a2/c2--> ... --ak/ck--> goal
~~~

Tổng chi phí thực sự g=c1+...+ck. Cần phân biệt:

- **State:** cấu hình đủ thông tin để xác định những hành động tương lai.
- **Search node/path hypothesis:** một cách tới state, có parent, depth, g và score.
- **Heuristic h:** ước lượng hoặc cận dưới chi phí còn lại; không phải chi phí đã trả.
- **Score:** thước đo dùng để chọn top-W, có thể là h, g+h, log probability hoặc điểm tùy biến.

Hai node đều ở G có thể mang g=22 và g=102 vì tới G bằng những đường khác nhau. **Path-based beam** có thể giữ cả hai. **State-based beam** có thể gộp khi chứng minh một đường bị chi phối bởi đường khác trong mô hình state hiện tại.

### Thiết kế state đủ thông tin

Nếu hai người ở cùng tọa độ nhưng chỉ một người có chìa khóa mở cửa, không thể dùng vị trí làm toàn bộ state. Cần lưu (row,col,hasKey) nếu quyền vào cửa phụ thuộc khóa. Ngược lại, nếu tương lai chỉ phụ thuộc một vài trường hiện tại, không nên đưa cả lịch sử đường đi vào khóa định danh state.

Trong Java 17, record bất biến phù hợp khi cần equals/hashCode theo các trường của state. Trong ví dụ dưới, trạng thái là một nhãn String vì graph đã được khai báo rõ.

## 3. Quy trình beam search theo tầng

Giả sử tầng d đang giữ tối đa W node; mỗi node có tối đa b transition hợp lệ. Tầng tiếp theo sinh tối đa Wb candidates rồi chỉ giữ W.

~~~text
beamSearch(start,width,maxDepth):
    require width >= 1
    beam = [rootNode]

    for depth=0..maxDepth:
        if beam contains goal:
            return chosenGoalWithinBeam(beam)
        if depth==maxDepth:
            break

        candidates=[]
        for node in beam:
            for tr in legalNeighbors(node.state):
                if violatesCyclePolicy(node,tr):
                    continue
                child=Node(
                    state=tr.next,
                    g=node.g+tr.cost,
                    parent=node)
                candidates.add(child)

        if candidates empty:
            break

        sort candidates by score and tieBreak
        beam=first min(width,candidates.size) candidates

    return NO_SOLUTION
~~~

**Phải chọn top-W từ tất cả ứng viên chung của tầng**, không giữ W con riêng của từng node cha; cách thứ hai có thể duy trì tới W² node và không còn là giới hạn W toàn cục.

### Chính sách kiểm goal

Có nhiều biến thể:

1. **Sau pruning:** chỉ kiểm goal trong beam đã giữ; một goal vừa sinh có thể bị cắt trước khi được kiểm.
2. **Trước pruning:** kiểm mọi goal vừa sinh; cứu được một số lời giải nhưng vẫn không cứu được nhánh đã cắt ở tầng trước.
3. **Completed pool:** hypothesis đã hoàn tất được giữ riêng, thường trong sinh chuỗi.

Mã Java dùng **cách 1**: kiểm goal ở đầu mỗi tầng sau khi beam của tầng ấy được chọn. Nếu beam chứa nhiều goal, chọn goal có g nhỏ nhất **trong số đang giữ**. Thuật toán không tiếp tục đến tầng sâu hơn chỉ để tìm lời giải có cost thấp hơn.

### Depth limit

Dmax tính từ tầng 0. Nếu Dmax=0, chỉ kiểm start; nếu start không phải goal, không có mở rộng. Kết quả NO_SOLUTION khi beam cạn hoặc vượt Dmax **không chứng minh** graph không có lời giải.

## 4. Hàm score và heuristic

Với quy ước điểm **nhỏ hơn tốt hơn**, có thể đánh giá theo:

~~~text
h(s)            uoc luong chi phi con lai
g(n)            chi phi da di
f(n)=g(n)+h(s)  uoc luong tong chi phi
negLogP(n)      am log xac suat cua chuoi
~~~

Các mục tiêu khác nhau. Ưu tiên h thiên về trạng thái trông gần đích; ưu tiên g+h cân nhắc thêm cost đã đi; score chuỗi dùng mô hình xác suất.

**Admissible heuristic** thỏa h(s)≤chi phí tối ưu thật từ s tới goal. **Consistent heuristic** thỏa:

~~~text
h(s) <= cost(s,t) + h(t)
h(goal) = 0
~~~

trên mọi cạnh s→t.

Hai điều kiện này quan trọng trong chứng minh A* tối ưu khi quản lý frontier đúng. Nhưng beam width nhỏ vẫn có thể **cắt bỏ node thuộc đường tối ưu** mặc dù h admissible và consistent.

Ví dụ ngõ cụt có chi phí còn lại +∞; đặt h=0 vẫn là cận dưới hợp lệ vì 0≤+∞. Heuristic thấp **không cam kết** còn đường tới goal.

Trong Java, score chính là h(state) thấp hơn tốt hơn; nếu hòa, chọn g thấp hơn, tên state tăng dần và serial sinh node. G là chi phí thật để báo cáo chứ không phải khóa ưu tiên chính.

## 5. Ví dụ 1: width=1 bỏ lỡ goal

Graph có hướng, mọi cạnh cost1:

~~~text
       A --> X   ngo cut
      /
S ---+
      \
       B --> G   goal

h(S)=0
h(A)=0, h(X)=0
h(B)=1, h(G)=0
~~~

**Width1:** tầng 0 là S. Sinh A(h0), B(h1), chỉ giữ A và cắt B vĩnh viễn. Tầng 1 sinh X từ A; X là ngõ cụt. Beam trả **NO_SOLUTION**.

~~~text
Layer 0: [S]
Layer 1: [A]
Layer 2: [X]
Result : NO_SOLUTION
~~~

Tuy vậy lời giải **S→B→G, cost2** tồn tại. Đây là phản ví dụ của **completeness** trên một DAG bé không có chu trình, dù Dmax6 đã dư.

**Width2:** giữ cả A,B ở tầng 1, rồi sinh X từ A và G từ B; tầng 2 chứa [G,X] theo comparator của mã. Kết quả **S→B→G, cost2**.

Heuristic vẫn admissible/consistent: B còn cost1 nên h(B)=1 chính xác; A và X không tới được G nên cost còn lại +∞, h0 vẫn hợp lệ. Vì vậy **heuristic hợp lệ không khôi phục completeness sau pruning**.

## 6. Ví dụ 2: width=1,2,3 cho cost 102,22,3

Các cạnh và chi phí:

~~~text
S -> A : 1
S -> B : 1
S -> C : 1
A -> D : 1
B -> E : 1
C -> F : 1
D -> G : 100
E -> G : 20
F -> G : 1
~~~

Ba đường tới G:

~~~text
S -> A -> D -> G  cost 102
S -> B -> E -> G  cost 22
S -> C -> F -> G  cost 3
~~~

Heuristic:

| State | h | Chi phí còn lại tối ưu |
| --- | ---: | ---: |
| S | 0 | 3 |
| A | 0 | 101 |
| B | 1 | 21 |
| C | 2 | 2 |
| D | 0 | 100 |
| E | 1 | 20 |
| F | 1 | 1 |
| G | 0 | 0 |

Mọi h đều là cận dưới. Mọi cạnh u→v cũng thỏa h(u)≤cost(u,v)+h(v), nên **h admissible và consistent**.

**Width1:** tầng đầu chỉ giữ A (h0), cắt B,C; tiếp tục D→G, trả **cost102**.

**Width2:** tầng đầu giữ A,B và **cắt C dù C thuộc đường tối ưu**. Tiếp đó giữ D,E; tầng cuối sinh G(g102) và G(g22). Chọn goal rẻ hơn trong beam, trả **cost22**.

**Width3:** giữ A,B,C rồi D,E,F; ba path tới G có cost102,22,3. Chọn nhánh C→F, trả **cost3**. Dijkstra trên graph này xác nhận optimum=3.

| Width | Đường trả về | Cost | Chênh với optimum3 |
| ---: | --- | ---: | ---: |
| 1 | S,A,D,G | 102 | 99 |
| 2 | S,B,E,G | 22 | 19 |
| 3 | S,C,F,G | 3 | 0 |

Điểm then chốt: **width2 cắt C dù heuristic C hoàn toàn admissible/consistent**. Không thể áp dụng chứng minh tối ưu của A* chỉ vì beam dùng cùng loại heuristic.

## 7. Ví dụ 3: tăng width nhưng kết quả đắt hơn

Đừng kết luận cost(W+1)≤cost(W) từ bảng trên. Chính sách **dừng ngay ở tầng đầu tiên chứa goal** có thể khiến beam rộng hơn gặp một goal nông nhưng đắt.

~~~text
S -> A : 1
S -> B : 1
A -> X : 1
X -> G : 1
B -> G : 100

h(S)=0, h(A)=0, h(B)=1
h(X)=0, h(G)=0
~~~

**Width1:** B bị cắt ở tầng 1. Beam theo S→A→X→G, tổng **cost3** ở depth3.

**Width2:** A,B cùng được giữ. Tầng 2 có X(g2) và G(g101); solver thấy goal ở tầng đó và trả **S→B→G, cost101**, trước khi đi sâu từ X.

~~~text
W=1: S -> A -> X -> G, cost3, depth3
W=2: S -> B -> G,    cost101, depth2
~~~

Dijkstra optimum=3. Kết quả không mâu thuẫn với beam policy: nó ưu tiên một goal **ở tầng gần hơn**, không phải chi phí tối thiểu toàn cục.

Một phương pháp thí nghiệm có thể chạy nhiều W rồi lưu **incumbent** là đáp án rẻ nhất từng thấy. Chi phí incumbent khi đó không tăng theo số lần chạy, nhưng đó là tính chất của **bộ chọn qua nhiều lần chạy**, không phải của từng lần beam search.

## 8. Completeness: khi nào có thể khôi phục?

Beam search nói chung **incomplete** khi:

- Những nhánh tới goal bị cắt sớm.
- Dmax ngắn hơn mọi đường tới goal.
- Dedup hoặc cycle policy loại sai state/hypothesis.
- Goal bị sinh nhưng bị cắt trước khi được kiểm theo goal policy.

**Điều kiện đủ:** trên graph hữu hạn, nếu Dmax đủ lớn để bao phủ một đường đơn tới goal, mọi transition được sinh đầy đủ, và W đủ lớn để **không prune những đường đơn cần thiết**, tìm kiếm theo tầng có thể đạt goal nếu reachable.

Với N state hữu hạn, nếu reachable thì có đường đơn từ start tới goal dài tối đa N−1 cạnh. Dmax≥N−1 đủ về độ sâu cho reachability **nếu không prune sai**.

Nhưng số đường đơn có thể rất lớn; width cần để không prune có thể vượt giới hạn tài nguyên. **Không có một W nhỏ cố định bảo đảm completeness cho mọi đồ thị tùy ý.**

NO_SOLUTION của beam không tương đương PROVED_UNREACHABLE. Nếu cần chứng minh không có lời giải, phải có tìm kiếm đầy đủ hoặc chứng minh riêng.

## 9. Optimality và tỷ lệ xấp xỉ

Beam tìm được goal vẫn có thể trả cost lớn hơn optimum vì nhánh tối ưu đã bị cắt. Trong ví dụ phần 6, width1 trả 102 trong khi optimum3.

Thay cost D→G từ 100 thành số rất lớn M, còn nhánh S→C→F→G vẫn cost3. Width1 vẫn chọn A rồi D, trả M+2, nên:

~~~text
beamCost / optimalCost = (M+2)/3
~~~

Tỷ lệ tăng tùy ý theo M. Không có **hệ số xấp xỉ hữu hạn cố định chỉ dựa vào W** cho beam score h trong ví dụ.

### Width đủ lớn có làm tối ưu weighted cost không?

**Không nhất thiết.** Nếu giữ mọi path nhưng vẫn **dừng ở goal đầu tiên theo tầng**, thuật toán ưu tiên số bước. Ví dụ phần 7 có goal depth2 cost101 và goal depth3 cost3. Dù không prune, chính sách dừng ở depth2 vẫn trả cost101.

Nếu cần min weighted cost không âm có bảo đảm, dùng **Dijkstra** hoặc **A*** đúng điều kiện, thay vì chỉ tăng W. Nếu mọi cạnh có cùng chi phí dương, không pruning và chọn goal đầu theo tầng thì số bước nhỏ nhất tương ứng với chi phí nhỏ nhất.

## 10. So sánh các thuật toán

| Thuật toán | Frontier | Bảo đảm điển hình |
| --- | --- | --- |
| BFS | Queue, duyệt state theo depth | Complete graph hữu hạn; ít cạnh nhất |
| DFS | Stack, đi sâu | Không bảo đảm ít bước hoặc chi phí |
| Greedy best-first | Priority queue **toàn cục** theo h | Có thể quay lại node còn trong queue; không tối ưu cost |
| Dijkstra | Priority queue toàn cục theo g | Tối ưu cost nếu mọi cạnh không âm |
| A* | Priority queue toàn cục theo g+h | Tối ưu theo điều kiện heuristic, cập nhật và dừng |
| Beam search | Giữ top-W **mỗi tầng**, cắt phần còn lại | Không complete/optimal nói chung |

**Beam width1 không đồng nghĩa greedy best-first chuẩn.** Greedy best-first giữ một queue toàn cục, nên sau khi mở rộng A đến ngõ cụt, nó có thể quay lại B đã sinh. Beam width1 cắt B ngay tại tầng đầu và không phục hồi.

**Beam score g+h không tự trở thành A*.** A* cần duy trì những node chưa mở rộng cần thiết cho chứng minh lower bound. Cắt tùy ý theo W mất điều kiện ấy.

## 11. Chu trình, trùng state và đa dạng chùm

Graph có thể chứa A→B→A. Nếu mỗi tầng cứ mở rộng path mà không xử lý, beam có thể quay quanh chu trình tới Dmax.

Một số chính sách:

- **Path-cycle check:** cấm sinh state đã xuất hiện trong parent chain của **chính path**.
- **Global dominance:** với state đủ thông tin và cost không âm, bỏ những đường bị một đường khác tới cùng state chi phối.
- **Per-layer dedup:** gộp node cùng state/depth khi có cơ sở.
- **Không dedup:** giữ từng hypothesis riêng, dễ thấy hành vi nhưng tốn slot khi nhiều đường giống nhau.

Mã Java dùng path-cycle check và **không dedup giữa các path**. Vì vậy G(g22) và G(g102) cùng có thể nằm trong width2 ở tầng cuối.

Không gộp hai state cùng vị trí khi chúng khác chìa khóa, tài nguyên hoặc yếu tố ảnh hưởng tương lai. Nếu bài yêu cầu không lặp đỉnh trên đường đi, tập đỉnh đã thăm có thể ảnh hưởng hợp lệ của hành động và phải được xử lý riêng khi cân nhắc dominance.

### Diversity

Những hypothesis top-W có thể gần giống nhau, chiếm hết slot beam. Có thể dùng diversity penalty, quota theo hành động đầu tiên, giới hạn số con mỗi parent hoặc stochastic selection. Các kỹ thuật này giúp khám phá nhánh khác trên một số dữ liệu nhưng **không tạo bảo đảm đầy đủ/tối ưu chung**.

## 12. Độ phức tạp và bộ nhớ

Gọi W là beam width, b là số con tối đa/node, D là depth limit.

Mỗi tầng sinh tối đa Wb ứng viên; sort toàn bộ:

~~~text
Time per layer = O(W*b*log(W*b))
Time D layers  = O(D*W*b*log(W*b))
~~~

Cận trên giả định tính score O(1) và không kiểm đường tổ tiên.

**Frontier** chỉ O(W) node nhưng **candidates** có thể dùng O(Wb) bộ nhớ tạm. Parent chains để reconstruct có thể giữ O(WD) node tổ tiên, và log tất cả tầng cũng dùng O(WD). Vì vậy tổng bộ nhớ của một triển khai không đơn thuần là O(W).

Trong Java demo, containsOnPath quét parent chain O(D) cho mỗi candidate. Tổng thời gian có cận:

~~~text
O(D * W * b * (D + log(W*b)))
~~~

Bộ nhớ theo node/entry cho candidates, ancestor chains và trace:

~~~text
O(W*b + W*D)
~~~

Nếu state rất lớn hoặc tính score bằng model ML tốn thời gian, phải cộng thêm chi phí tương ứng. Khi Wb quá lớn, có thể stream top-W bằng một heap size W để giảm phần bộ nhớ candidates tạm, nhưng cần bảo toàn comparator và goal policy.

## 13. Java 17 – beam search và Dijkstra đối chứng

Chương trình Java 17 độc lập:

- Graph có hướng, cost cạnh không âm.
- Beam score=h(state), nhỏ hơn tốt hơn; tie-break theo g, tên state, serial.
- Parent chain để dựng đường và tránh lặp state trên cùng path.
- Chọn top-W trên **tất cả candidates của tầng**.
- Goal được kiểm trong beam đã chọn; nếu nhiều goal thì lấy g thấp nhất.
- Ghi trace từng tầng, expanded/generated/pruned.
- Dijkstra độc lập tính optimum để đối chứng.
- Thử ba graph phản ví dụ, start==goal và input không hợp lệ.

Lưu đúng tên **BeamSearchGuaranteesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;

public class BeamSearchGuaranteesDemo {

    record Arc(String to, long cost) {}

    record Node(String state, long g, Node parent, long serial) {}

    record CostEntry(String state, long g) {}

    record Result(
            boolean found, long cost, List<String> path,
            List<List<String>> layers,
            int expanded, int generated, int pruned) {}

    static final class Problem {
        final String start;
        final String goal;
        final Map<String, List<Arc>> adj = new HashMap<>();
        final Map<String, Long> heuristic = new HashMap<>();

        Problem(String start, String goal) {
            if (start == null || goal == null) {
                throw new IllegalArgumentException(
                        "terminals must be nonnull");
            }
            this.start = start;
            this.goal = goal;
        }

        Problem h(String state, long value) {
            if (state == null || value < 0) {
                throw new IllegalArgumentException(
                        "heuristic must be nonnegative");
            }
            heuristic.put(state, value);
            adj.computeIfAbsent(state,
                    ignored -> new ArrayList<>());
            return this;
        }

        Problem edge(String from, String to, long cost) {
            if (from == null || to == null) {
                throw new IllegalArgumentException(
                        "invalid endpoint");
            }
            if (cost < 0) {
                throw new IllegalArgumentException(
                        "edge cost must be nonnegative");
            }
            adj.computeIfAbsent(from,
                    ignored -> new ArrayList<>())
                    .add(new Arc(to, cost));
            adj.computeIfAbsent(to,
                    ignored -> new ArrayList<>());
            return this;
        }

        long h(String state) {
            Long result = heuristic.get(state);
            if (result == null) {
                throw new IllegalArgumentException(
                        "missing heuristic for " + state);
            }
            return result;
        }

        List<Arc> neighbors(String state) {
            return adj.getOrDefault(state, List.of());
        }
    }

    private static boolean onPath(Node node, String state) {
        for (Node p = node; p != null; p = p.parent()) {
            if (p.state().equals(state)) {
                return true;
            }
        }
        return false;
    }

    private static List<String> path(Node node) {
        List<String> reversed = new ArrayList<>();
        for (Node p = node; p != null; p = p.parent()) {
            reversed.add(p.state());
        }
        java.util.Collections.reverse(reversed);
        return List.copyOf(reversed);
    }

    private static List<String> snapshot(List<Node> beam) {
        List<String> output = new ArrayList<>();
        for (Node n : beam) {
            output.add(n.state() + "(g=" + n.g() + ")");
        }
        return List.copyOf(output);
    }

    static Result beamSearch(
            Problem graph, int width, int maxDepth) {
        if (width <= 0) {
            throw new IllegalArgumentException(
                    "width must be positive");
        }
        if (maxDepth < 0) {
            throw new IllegalArgumentException(
                    "maxDepth must be nonnegative");
        }

        graph.h(graph.start);
        long serial = 0;
        List<Node> beam = new ArrayList<>();
        beam.add(new Node(graph.start, 0, null, serial++));

        List<List<String>> layers = new ArrayList<>();
        int expanded = 0, generated = 0, pruned = 0;

        Comparator<Node> order = Comparator
                .comparingLong(
                        (Node n) -> graph.h(n.state()))
                .thenComparingLong(Node::g)
                .thenComparing(Node::state)
                .thenComparingLong(Node::serial);

        for (int depth = 0; depth <= maxDepth; depth++) {
            layers.add(snapshot(beam));

            Node chosenGoal = null;
            for (Node n : beam) {
                if (n.state().equals(graph.goal)
                        && (chosenGoal == null
                        || n.g() < chosenGoal.g())) {
                    chosenGoal = n;
                }
            }

            if (chosenGoal != null) {
                return new Result(
                        true, chosenGoal.g(), path(chosenGoal),
                        List.copyOf(layers),
                        expanded, generated, pruned);
            }

            if (depth == maxDepth) {
                break;
            }

            List<Node> candidates = new ArrayList<>();
            for (Node current : beam) {
                expanded++;
                for (Arc arc : graph.neighbors(current.state())) {
                    if (onPath(current, arc.to())) {
                        continue;
                    }
                    long nextG = Math.addExact(
                            current.g(), arc.cost());
                    candidates.add(new Node(
                            arc.to(), nextG, current, serial++));
                }
            }

            generated += candidates.size();
            if (candidates.isEmpty()) {
                break;
            }

            candidates.sort(order);
            int keep = Math.min(width, candidates.size());
            pruned += candidates.size() - keep;
            beam = new ArrayList<>(
                    candidates.subList(0, keep));
        }

        return new Result(
                false, -1L, List.of(), List.copyOf(layers),
                expanded, generated, pruned);
    }

    // Independent optimum reference with nonnegative costs.
    static long dijkstraCost(Problem graph) {
        Map<String, Long> dist = new HashMap<>();
        PriorityQueue<CostEntry> pq = new PriorityQueue<>(
                Comparator.comparingLong(CostEntry::g)
                        .thenComparing(CostEntry::state));

        dist.put(graph.start, 0L);
        pq.add(new CostEntry(graph.start, 0L));

        while (!pq.isEmpty()) {
            CostEntry item = pq.poll();
            Long best = dist.get(item.state());
            if (best == null || best.longValue() != item.g()) {
                continue;
            }
            if (item.state().equals(graph.goal)) {
                return item.g();
            }

            for (Arc arc : graph.neighbors(item.state())) {
                long nextG = Math.addExact(
                        item.g(), arc.cost());
                Long old = dist.get(arc.to());
                if (old == null || nextG < old) {
                    dist.put(arc.to(), nextG);
                    pq.add(new CostEntry(arc.to(), nextG));
                }
            }
        }

        return -1L;
    }

    static Problem deadEnd() {
        return new Problem("S", "G")
                .h("S", 0).h("A", 0).h("B", 1)
                .h("X", 0).h("G", 0)
                .edge("S", "A", 1)
                .edge("S", "B", 1)
                .edge("A", "X", 1)
                .edge("B", "G", 1);
    }

    static Problem weighted() {
        return new Problem("S", "G")
                .h("S", 0).h("A", 0).h("B", 1)
                .h("C", 2).h("D", 0).h("E", 1)
                .h("F", 1).h("G", 0)
                .edge("S", "A", 1)
                .edge("S", "B", 1)
                .edge("S", "C", 1)
                .edge("A", "D", 1)
                .edge("B", "E", 1)
                .edge("C", "F", 1)
                .edge("D", "G", 100)
                .edge("E", "G", 20)
                .edge("F", "G", 1);
    }

    static Problem nonMonotonic() {
        return new Problem("S", "G")
                .h("S", 0).h("A", 0).h("B", 1)
                .h("X", 0).h("G", 0)
                .edge("S", "A", 1)
                .edge("S", "B", 1)
                .edge("A", "X", 1)
                .edge("X", "G", 1)
                .edge("B", "G", 100);
    }

    static String show(Result r) {
        return r.found()
                ? "path " + r.path() + ", cost " + r.cost()
                : "NO_SOLUTION";
    }

    public static void main(String[] args) {
        Problem dead = deadEnd();
        System.out.println("dead-end optimum = "
                + dijkstraCost(dead));
        System.out.println("dead-end W=1: "
                + show(beamSearch(dead, 1, 6)));
        System.out.println("dead-end W=2: "
                + show(beamSearch(dead, 2, 6)));

        Problem weighted = weighted();
        System.out.println("weighted optimum = "
                + dijkstraCost(weighted));
        for (int w = 1; w <= 3; w++) {
            System.out.println("weighted W=" + w + ": "
                    + show(beamSearch(weighted, w, 6)));
        }

        Result trace = beamSearch(weighted, 2, 6);
        for (int i = 0; i < trace.layers().size(); i++) {
            System.out.println("weighted W=2 layer " + i
                    + " = " + trace.layers().get(i));
        }
        System.out.println("weighted W=2 stats = "
                + "expanded " + trace.expanded()
                + ", generated " + trace.generated()
                + ", pruned " + trace.pruned());

        Problem counter = nonMonotonic();
        System.out.println("non-monotonic optimum = "
                + dijkstraCost(counter));
        System.out.println("non-monotonic W=1: "
                + show(beamSearch(counter, 1, 6)));
        System.out.println("non-monotonic W=2: "
                + show(beamSearch(counter, 2, 6)));

        Problem single = new Problem("S", "S").h("S", 0);
        System.out.println("start-is-goal: "
                + show(beamSearch(single, 1, 0)));

        try {
            beamSearch(dead, 0, 6);
        } catch (IllegalArgumentException e) {
            System.out.println("invalid width: " + e.getMessage());
        }
        try {
            beamSearch(dead, 2, -1);
        } catch (IllegalArgumentException e) {
            System.out.println("invalid depth: " + e.getMessage());
        }
        try {
            new Problem("S", "G").edge("S", "G", -1);
        } catch (IllegalArgumentException e) {
            System.out.println("invalid cost: " + e.getMessage());
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17:

~~~bash
javac BeamSearchGuaranteesDemo.java
java BeamSearchGuaranteesDemo
~~~

**Stdout chính xác:**

~~~text
dead-end optimum = 2
dead-end W=1: NO_SOLUTION
dead-end W=2: path [S, B, G], cost 2
weighted optimum = 3
weighted W=1: path [S, A, D, G], cost 102
weighted W=2: path [S, B, E, G], cost 22
weighted W=3: path [S, C, F, G], cost 3
weighted W=2 layer 0 = [S(g=0)]
weighted W=2 layer 1 = [A(g=1), B(g=1)]
weighted W=2 layer 2 = [D(g=2), E(g=2)]
weighted W=2 layer 3 = [G(g=22), G(g=102)]
weighted W=2 stats = expanded 5, generated 7, pruned 1
non-monotonic optimum = 3
non-monotonic W=1: path [S, A, X, G], cost 3
non-monotonic W=2: path [S, B, G], cost 101
start-is-goal: path [S], cost 0
invalid width: width must be positive
invalid depth: maxDepth must be nonnegative
invalid cost: edge cost must be nonnegative
~~~

### Giải thích trace

Ở weighted width2: S sinh A,B,C, giữ A,B và prune1. Hai node này sinh D,E. Tiếp đó D,E sinh hai hypothesis cùng state G với g102 và g22. Tổng expanded=1+2+2=5, generated=3+2+2=7, pruned=1.

Code không gộp hai node G vì chúng có parent chain khác nhau. Có thể cải tiến bằng dedup/dominance nếu chứng minh hợp lệ. MaxDepth6 đủ cho các ví dụ; start đã là goal và maxDepth0 trả [S] cost0. Cost âm bị từ chối để Dijkstra oracle đúng, và Math.addExact phát hiện tràn long.

## 14. Bất biến và điều có thể chứng minh

**Độ rộng:** beam đầu có một node; sau mỗi tầng chỉ giữ min(W,candidates.size), nên kích thước không vượt W.

**Tính hợp lệ:** node đầu là start; mỗi node con nối một transition hợp lệ từ node cha; parent chain tạo một path hợp lệ. Khi found=true, state cuối là goal.

**Tổng cost:** g đầu bằng 0; mỗi con nhận g cha cộng cost cạnh bằng Math.addExact. Theo quy nạp, g khớp tổng chi phí của path.

**Top-W:** solver sort mọi candidates của tầng bằng cùng comparator h,g,state,serial và giữ W đầu tiên. Đây là top-W **trong số node được sinh từ beam tầng trước**, không phải top-W của mọi path có thể tồn tại trong graph.

**Không có bảo đảm tối ưu/tìm được:** ba phản ví dụ lần lượt bác bỏ completeness, optimality và đơn điệu chi phí theo width. Một phản ví dụ chính xác đủ để bác bỏ mỗi khẳng định phổ quát.

## 15. Beam search cho sinh chuỗi token

Một hypothesis có thể là tiền tố token. Mỗi bước sinh token mới, cộng điểm xác suất và giữ W tiền tố có score tốt nhất. Với negative log probability:

~~~text
logP(sequence) = sum log P(token_i | prefix_i)
negLogP(sequence) = -logP(sequence)
~~~

Điểm negLogP càng nhỏ thì xác suất model càng cao. Nhưng tổng logprob phụ thuộc độ dài, nên so chuỗi đã hoàn tất khác độ dài có thể cần length normalization và quy tắc dừng rõ.

Cần xác định cách xử lý **EOS (end-of-sequence)**: hypothesis kết thúc có thể chuyển vào completed pool thay vì cạnh tranh với hypothesis còn mở. Nếu bỏ quên các chuỗi đã hoàn tất, thuật toán có thể đánh mất kết quả tốt.

Ví dụ xác suất toàn chuỗi giả định:

~~~text
P("A EOS")   = 0.30
P("B C EOS") = 0.35
P("B D EOS") = 0.10
~~~

B C EOS có xác suất cao nhất trong ba chuỗi, nhưng beam width nhỏ có thể prune tiền tố B sớm khi các tiền tố khác được ưu tiên ở tầng đầu. Đây là một search error do pruning.

**Xác suất model cao không tương đương chất lượng ngôn ngữ cao.** Tăng W không bảo đảm chất lượng đầu ra theo con người, ngay cả khi nó thường cải thiện khả năng khám phá hypothesis score cao hơn.

## 16. Đo chất lượng và chọn W

Một thí nghiệm beam cần ghi rõ W, Dmax, score, tie-break, goal policy, dedup, cycle policy và budget. Nếu thay nhiều tham số đồng thời, khó biết nguyên nhân kết quả đổi.

Thước đo:

- **Success rate:** tỷ lệ tìm được goal.
- **Absolute gap:** beamCost−optimalCost trên bài có đáp án exact.
- **Relative gap:** (beamCost−optimalCost)/optimalCost nếu optimalCost>0.
- **Expanded/generated/pruned:** số node xử lý, sinh và loại.
- **Peak memory và runtime:** tính cả candidates trước pruning.
- **Diversity:** độ khác nhau giữa các hypothesis đang giữ.

Nếu optimum=0, không tính relative gap bằng cách chia cho 0; dùng absolute gap hoặc metric khác. Nếu beam trả NO_SOLUTION nhưng Dijkstra tìm được goal, ghi đó là **false negative trong ngân sách beam**, không gọi graph vô nghiệm.

Thử W=1,2,4,8,... trên cùng bộ dữ liệu và giữ các policy khác cố định. Chọn W theo chi phí CPU/RAM và tỷ lệ thành công thực nghiệm. Không tuyên bố một W nhỏ phổ quát đủ tốt cho mọi graph.

## 17. Lỗi triển khai phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Giữ W con cho từng parent | Beam có thể lên tới W² | Chọn global top-W theo tầng |
| Nhầm h với g | Báo sai tối ưu cost | Lưu cost thật riêng |
| Tưởng h admissible làm beam optimal | Cắt optimal path | Phân biệt với A* |
| Dừng goal đầu tầng rồi gọi min weighted cost | Có thể trả đường đắt | Dijkstra/A* khi cần exact |
| Beam width1 gọi greedy best-first chuẩn | Nhầm frontier | Greedy best-first dùng queue toàn cục |
| Không nói rõ goal policy | Có thể bỏ goal vừa sinh | Chỉ rõ trước/sau pruning |
| Không xử lý cycle | Lặp path vô ích | Path check/dedup |
| Dedup state thiếu khóa/tài nguyên | Mất nhánh hợp lệ | State đủ Markov |
| NO_SOLUTION bị hiểu là vô nghiệm | Sai về completeness | Báo rõ giới hạn |
| Tăng W được coi luôn giảm cost | Có phản ví dụ ngược | Đo và giữ incumbent |
| Chỉ tính bộ nhớ O(W) | Thiếu Wb candidates, WD parents | Phân tích đầy đủ |
| Quên tie-break | Kết quả không tái lập | Comparator xác định |
| Dùng cost âm với Dijkstra | Oracle sai | Ràng buộc nonnegative |
| Không kiểm overflow | g bị tràn | Math.addExact/BigInteger |
| Bỏ completed pool trong sinh chuỗi | Có thể mất output kết thúc | Xử lý EOS |
| So logprob khác độ dài tùy tiện | Length bias | Quy tắc normalization |
| Không test từng bước trong path | Đường có thể không hợp lệ | Recompute transition và cost |

## 18. Kiểm thử độc lập

Với found=true, path phải bắt đầu ở start, kết thúc tại goal; mọi cặp state kề nhau phải là transition hợp lệ; tổng cost đúng bằng Result.cost; path không dài quá Dmax và không lặp state nếu bật cycle check.

Với từng tầng, kiểm beam.size≤W, selected là top-W theo comparator, pruned=candidateCount−selectedCount. Với tie-break, dùng h rồi g rồi tên state rồi serial đúng như mã.

| Test | Width | Kết quả |
| --- | ---: | --- |
| Graph ngõ cụt | 1 | NO_SOLUTION |
| Graph ngõ cụt | 2 | S,B,G cost2 |
| Ba nhánh | 1 | cost102 |
| Ba nhánh | 2 | cost22 |
| Ba nhánh | 3 | cost3 |
| Graph non-monotonic | 1 | cost3 |
| Graph non-monotonic | 2 | cost101 |
| Start==goal, Dmax0 | 1 | [S] cost0 |
| Width0 | Bất kỳ | IllegalArgumentException |
| Dmax âm | Bất kỳ | IllegalArgumentException |
| Cost âm | Bất kỳ | IllegalArgumentException |

### Dùng oracle exact

Dijkstra trên graph có cost không âm cho optimum 2,3,3 ở ba ví dụ. Với graph nhỏ, có thể liệt kê mọi đường đơn bằng DFS để kiểm reachability và chi phí. Nếu beam tìm được goal, cost không thể nhỏ hơn optimum; nếu beam không tìm được trong khi optimum hữu hạn, đó là thất bại do hạn mức/pruning.

### Sinh graph ngẫu nhiên

Sinh DAG nhỏ V≤8, cạnh từ id nhỏ sang id lớn, cost không âm, h tùy ý. Kiểm:

1. Path của beam luôn hợp lệ và cost đúng.
2. Các tầng không vượt W.
3. Beam có thể thất bại dù Dijkstra tìm được goal.
4. W đủ lớn để không prune bất kỳ path đơn nào, Dmax≥V−1 thì tìm được goal nếu reachable.
5. Khi mọi cạnh cost1, không pruning và dừng theo tầng, goal đầu cho ít bước nhất.
6. **Không** áp đặt cost(W+1)≤cost(W) trong mọi trường hợp.

Đối với heuristic được yêu cầu admissible, so h với shortest remaining cost thật; đối với consistent, kiểm h(u)≤cost(u,v)+h(v). Bài Java dùng h để sắp thứ tự nhưng không tự chứng minh các tính chất ấy bằng API.

## 19. Bài tập

1. Định nghĩa beam width, state, node hypothesis, heuristic và goal policy.
2. Vẽ cây branching factor3 và minh họa top-W với W=2.
3. Mô phỏng width1 trên graph ngõ cụt và chỉ ra nhánh bị cắt.
4. Mô phỏng width2 cùng graph, giải thích vì sao tìm được G.
5. Tính cost102,22,3 của ba đường trong graph thứ hai.
6. Kiểm h của graph thứ hai admissible/consistent trên từng cạnh.
7. Giải thích vì sao width2 cắt đường tối ưu qua C.
8. Đổi comparator h thành g+h; thử tìm ví dụ beam vẫn suboptimal.
9. Mô phỏng graph non-monotonic để thấy W tăng và cost cũng tăng.
10. Đổi chính sách kiểm goal sang trước pruning; so với mã gốc.
11. Viết completed-goal pool và lưu incumbent tốt nhất.
12. Thêm path-cycle check cho graph chứa chu trình hai đỉnh.
13. Thêm dedup theo state/depth và chứng minh khi nào hợp lệ.
14. So width1 với greedy best-first có priority queue toàn cục.
15. Cài heap top-W để giảm bộ nhớ tạm ứng viên.
16. So beam và BFS khi tất cả cạnh cost1 và W đủ không prune.
17. Sinh 100 graph nhỏ và dùng Dijkstra làm oracle.
18. Đo success rate, cost gap và expanded khi W tăng.
19. Thiết kế beam decoder với negative logprob và token EOS.
20. Thử length normalization cho chuỗi có độ dài khác nhau.
21. Xây graph với rất nhiều nhánh có h0 nhưng đều là ngõ cụt.
22. Chứng minh bất biến path hợp lệ và g bằng tổng cost.
23. Giải thích tại sao không có tỷ lệ xấp xỉ chung khi tăng M.
24. Mô tả khi nào nên chuyển sang Dijkstra/A* thay beam.

## 20. Tổng kết

Trước khi dùng beam search hãy kiểm: state đã đủ thông tin? W, Dmax và score là gì? Đã chọn top-W từ **toàn bộ candidates của tầng**? Có nêu goal policy, tie-break, cycle/dedup và giới hạn bộ nhớ Wb/WD? Có biết NO_SOLUTION không chứng minh vô nghiệm, found=true không chứng minh tối ưu? Có kiểm đường trả về và đối chiếu với exact oracle trên bài nhỏ?

**Kết luận:** beam search giữ tối đa W ứng viên tốt nhất ở mỗi tầng để đánh đổi chất lượng lấy tài nguyên. Nó hữu ích trong không gian trạng thái lớn nhưng **không complete, không optimal và không có tỷ lệ xấp xỉ phổ quát** trong trường hợp chung. Heuristic admissible/consistent không khôi phục những nhánh đã prune. Ba ví dụ trọng tâm cho thấy beam có thể **bỏ lỡ goal**, **trả cost rất cao hơn optimum**, và **tăng W nhưng kết quả đắt hơn** do điều kiện dừng. Hãy công khai các chính sách và đo với oracle exact khi có thể.

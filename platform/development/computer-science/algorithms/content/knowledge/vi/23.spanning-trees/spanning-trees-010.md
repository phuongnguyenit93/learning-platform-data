# Thay cạnh để tìm cây khung khác tốt nhất và xử lý trọng số bằng nhau

> **Chủ đề:** Computer Science Algorithms → Cây khung.  
> **Mục tiêu:** Tìm một cây khung khác từ MST đã có bằng phép **thêm một cạnh và bỏ một cạnh trên chu trình**, phân biệt **một MST khác cùng tổng** với **cây khung có tổng trọng số lớn hơn MST nhỏ nhất một cách nghiêm ngặt**; xử lý cạnh bằng trọng số, âm, song song, self-loop, thành phần rời rạc; giải từ quét đường cây đơn giản đến **LCA + hai trọng số lớn nhất phân biệt**, cài Java 17 và kiểm tra bằng vét cạn.

## 1. Hai nghĩa khác nhau của “cây khung thứ hai”

Với đồ thị **vô hướng có trọng số** `G=(V,E)`, mỗi cạnh có **ID riêng**, giả sử G có ít nhất một đỉnh và **liên thông**. Một **cây khung** T chứa tất cả đỉnh, không có chu trình, có `n−1` cạnh. Một **cây khung nhỏ nhất** (minimum spanning tree, **MST**) tối thiểu tổng trọng số các cạnh:

`W = Σ_(e∈T) w(e)`.

Khi đã biết một MST T, cần phân biệt:

- **Cây khung khác có tổng nhỏ nhất** (*minimum different spanning tree*): tìm T' có **tập ID cạnh khác T**, sao cho tổng nhỏ nhất. **Tổng có thể bằng W**, vì nhiều MST có thể đồng tối ưu.
- **Cây khung có tổng lớn hơn W nhỏ nhất** (*strictly second-best MST*, *second distinct cost*): tìm T' sao cho `weight(T')>W` và tổng nhỏ nhất. Nếu mọi cây khung đều cùng W, **không có đáp án strict**.
- **Một MST khác:** tìm T' khác T **và** `weight(T')=W`. Nếu tồn tại, MST không duy nhất.

Nếu chỉ bảo “second MST” mà không quy định có cho phép **bằng trọng số** hay không, cần đọc kỹ đề và ví dụ. Hai bài có **đáp án khác nhau** trên đồ thị có cạnh bằng nhau.

### 1.1. Nhiều cây nhưng không có trọng số lớn hơn

Tam giác có ba cạnh đều trọng số 1. Mọi cây khung chọn đúng hai cạnh, tổng đều bằng 2. Có **3 MST khác nhau** xét theo tập cạnh, nhưng **không tồn tại** cây khung với tổng >2.

Ngược lại tam giác 1,1,2 chỉ có **một MST** gồm hai cạnh 1, tổng 2; cây khác nhẹ nhất và cây strict second-best đều có tổng 3.

### 1.2. Vấn đề cạnh song song

Hai cạnh `(0,1)` cùng trọng số 5 nhưng có **hai ID** khác nhau là hai lựa chọn riêng trong một multigraph. Nếu chọn cạnh thứ nhất trong cây, thay bằng cạnh thứ hai tạo cây **khác tập cạnh** với tổng không đổi.

Nếu đề không phân biệt cạnh song song trùng ID/đầu mút hoặc chỉ cho đồ thị đơn, cần thống nhất ngữ nghĩa đếm nghiệm trước khi kết luận MST duy nhất.

## 2. Điều kiện đồ thị liên thông và MSF

Một cây khung trên **toàn bộ G** tồn tại khi và chỉ khi G vô hướng **liên thông** (với `n>=1`). Nếu G có k thành phần liên thông, k>1, **không có MST toàn đồ thị**.

Khi ấy thuật toán Kruskal tạo **minimum spanning forest (MSF)**: một MST cho **mỗi thành phần ban đầu**, gồm `n−k` cạnh. Đỉnh cô lập tạo cây một đỉnh không cạnh.

Các công thức thay cạnh vẫn có thể áp dụng **bên trong từng cây của MSF**, để tìm một MSF khác hoặc rừng có tổng lớn hơn mức minimum nhỏ nhất, với điều kiện **giữ đủ kết nối bên trong mỗi component gốc**. Không tự nối các component bằng cạnh không có trong input.

Ví dụ n=5, các cạnh ở component `{0,1,2}` là 0—1:1, 1—2:2, 0—2:2; component `{3,4}` có **hai cạnh song song** trọng số 5. MSF có tổng `1+2+5=8`, có nhiều MSF cùng 8; mức tổng lớn hơn tiếp theo bằng **9**. Nhưng **không** thể gọi chúng là MST nối toàn bộ 5 đỉnh.

Với `n=1`, một đỉnh không cạnh có cây khung duy nhất, tổng 0, không có cây khác. Với `n=0`, bài này quy ước rừng rỗng tổng 0, components 0, không gọi là một cây MST.

## 3. Phép thêm một cạnh — bỏ một cạnh

Giả sử T là cây khung vô hướng. Giữa hai đỉnh u và v có **đúng một đường đơn** trong T, ký hiệu `P_T(u,v)`.

Chọn một cạnh `e=(u,v)` **ngoài T** và có `u!=v`. Thêm e vào T tạo **đúng một chu trình** gồm e và đường P.

Nếu bỏ **một cạnh f thuộc P**, ta thu được cây khung mới:

`T' = T + e − f`.

Tập đỉnh không đổi, số cạnh vẫn `n−1`, chu trình bị phá và liên thông được giữ nguyên.

Tổng cây mới:

`weight(T') = W + w(e) − w(f)`.

**Không được bỏ tùy ý một cạnh ngoài P:** chu trình tạo bởi e vẫn tồn tại và phần khác có thể bị ngắt. Bỏ lại e chỉ đưa về cây cũ T, không tạo nghiệm khác.

### 3.1. Cạnh self-loop không tham gia phép đổi

Với e=(u,u), “đường” từ u tới chính nó không chứa cạnh, thêm e tạo chu trình một cạnh. Không có cạnh cũ trên đường để bỏ và giữ e hợp lệ. Vì vậy **bỏ qua self-loop** dù trọng số rất âm.

### 3.2. Cạnh song song hợp lệ nếu khác ID

Nếu e ngoài T song song với f∈T, đường P giữa hai đầu e có thể chỉ gồm f. Đổi `+e−f` hợp lệ. Nếu `w(e)==w(f)`, đây là một MST khác; nếu `w(e)>w(f)`, đây là một cây nặng hơn.

## 4. Tính chất kiểm MST qua trọng số lớn nhất trên đường

Đặt:

`M(e) = max { w(f) : f ∈ P_T(u,v) }`

cho cạnh ngoài cây e=(u,v), u≠v.

Nếu T là MST, với **mọi** cạnh ngoài T:

`w(e) >= M(e)`.

**Chứng minh:** nếu `w(e)<M(e)`, bỏ một cạnh f trên P có `w(f)=M(e)`, thêm e, tổng giảm:

`W' = W + w(e) − M(e) < W`.

Điều này mâu thuẫn T là MST.

Ngược lại, nếu một cây khung T thỏa `w(e)>=M(e)` cho mọi cạnh e ngoài T không-loop, nó là MST. Đây là hệ quả của **tính chất chu trình và lập luận trao đổi cạnh** (*exchange argument*): nếu có cây nhẹ hơn T, có thể tìm một phép đổi cạnh làm tổng T giảm.

### 4.1. Khi nào MST không duy nhất?

Một MST T **không duy nhất khi và chỉ khi** tồn tại cạnh ngoài T có:

`w(e) = M(e)`.

Khi đó bỏ cạnh trên đường có trọng số bằng `M(e)` và thêm e, tổng mới bằng W, nhưng tập cạnh đổi.

Nếu mọi cạnh ngoài T đều có `w(e)>M(e)`, mọi phép thay cạnh tăng tổng; MST là **duy nhất**.

**Không được** chỉ nhìn bảng thấy hai cạnh cùng trọng số rồi kết luận có hai MST. Cạnh bằng nhau phải thực sự cho phép một phép thay hợp lệ trên chu trình.

### 4.2. Cạnh cầu và cạnh bắt buộc

Nếu một cạnh f của G là **cầu** (bỏ f làm tăng số component), mọi cây khung phải chứa f. Không có cạnh ngoài cây nào tạo chu trình chứa f để thay thế nó. Điều này đúng ngay cả khi f rất nặng.

### 4.3. Trọng số âm không gây vấn đề

MST/Kruskal/Prim **không đòi trọng số không âm** như Dijkstra. Phương trình `W+w(e)−w(f)` và so sánh trên đường đúng với trọng số âm, 0 và dương. Nhưng **không dùng 0 làm sentinel “chưa có max”** trên đường toàn cạnh âm.

## 5. Bài toán A: cây khác có tổng nhỏ nhất

Với một cạnh ngoài T cố định e, muốn tối thiểu:

`W + w(e) − w(f)`

trong các f thuộc P, cần chọn cạnh bị bỏ có trọng số **lớn nhất**:

`f_max(e) = argmax_(f∈P) w(f)`.

Vậy chi phí cây khác nhẹ nhất qua e là:

`C_different(e) = W + w(e) − M(e)`.

Duyệt **tất cả cạnh ngoài T** (không-loop), rồi lấy min C.

- Nếu có ứng viên bằng W ⇒ tồn tại MST khác cùng tổng.
- Nếu mọi ứng viên >W ⇒ T là MST duy nhất; ứng viên nhỏ nhất cũng là cây strict second-best.
- Nếu không có cạnh ngoài T hợp lệ ⇒ không có cây khác (ví dụ graph tự là một cây).

Khi có nhiều cạnh trên đường cùng đạt max, có thể bỏ **một trong số chúng**. Để chương trình in witness ổn định, chọn **ID cạnh nhỏ nhất** trong các cạnh đồng max.

## 6. Bài toán B: cây nhẹ nhất với tổng **lớn hơn nghiêm ngặt** MST

Để phép đổi cho tổng **lớn hơn W**, cần:

`W+w(e)−w(f)>W` ⇔ `w(f)<w(e)`.

Trong số các cạnh f trên đường thỏa `w(f)<w(e)`, ta muốn bỏ cạnh có trọng số **lớn nhất** để mức tăng **dương nhỏ nhất**.

Đặt:

`L(e) = max { w(f) : f∈P_T(u,v), w(f)<w(e) }`.

Nếu tập này không rỗng:

`C_strict(e) = W + w(e) − L(e) > W`.

Nếu không có f nào nhẹ hơn w(e) trên P, cạnh e **không tạo** cây strict bằng một bước đổi.

Lấy min mọi C_strict để được **trọng số strict second-best**. Với MST ban đầu bất kỳ, định lý trao đổi cơ sở của cây khung bảo đảm có thể tìm mức trọng số nhỏ nhất lớn hơn W qua **một phép đổi** nếu mức ấy tồn tại; không phải thử tất cả cây khung.

### 6.1. Hai trường hợp thuật toán phải tách

Vì w(e)>=M(e), chỉ có:

- **`w(e)>M(e)`**: mọi cạnh trên P đều nhẹ hơn e; do đó `L(e)=M(e)`. Bỏ cạnh max như thường.
- **`w(e)==M(e)`**: bỏ cạnh max làm tổng **bằng W**, không được dùng cho strict. Phải tìm **giá trị trọng số lớn nhất trên đường nhưng *nhỏ hơn* M**.

Giá trị thứ hai này là **maximum thứ hai phân biệt** (*second distinct maximum*), **không** phải cạnh có vị trí đứng thứ hai khi sắp trọng số nếu có các giá trị bằng nhau.

### 6.2. Phản ví dụ quan trọng

Đường trong MST có các trọng số `[5,5,3,1]`; cạnh ngoài e có trọng số 5.

- Bỏ một cạnh 5: `W+5−5=W` ⇒ tạo MST khác.
- Bỏ cạnh 3: `W+5−3=W+2` ⇒ ứng viên strict tốt nhất qua e.
- Nếu chỉ lưu hai cạnh lớn nhất **tính cả trùng**, ta sẽ lấy 5 và 5, không nhìn thấy 3 ⇒ **bỏ sót** cây strict.

Vì vậy LCA tối ưu cần lưu **hai giá trị trọng số lớn nhất khác nhau**, không phải hai ID cạnh nặng nhất bất kể bằng nhau.

### 6.3. Khi không tồn tại strict second

Tam giác `[1,1,1]`: mọi spanning tree có tổng 2, nên không có cây có tổng >2.

Graph chỉ gồm một cây n−1 cạnh: cũng không có strict second, nhưng còn **không có cây khác** nói chung.

Bài ra có thể yêu cầu phân biệt hai lý do “none”; hãy trả trạng thái khác nhau nếu cần.

## 7. Ví dụ năm đỉnh có cạnh bằng nhau

Đồ thị vô hướng `V={0,1,2,3,4}` và các cạnh ID như sau:

| ID | Hai đầu | w | Ghi chú |
|---|---|---:|---|
| A | 0—1 | 1 | MST ban đầu |
| B | 1—2 | 2 | MST ban đầu |
| C | 2—3 | 2 | MST ban đầu |
| D | 3—4 | 4 | MST ban đầu |
| E | 0—2 | 2 | Có thể đổi giữ tổng |
| F | 1—3 | 3 | Có thể tạo strict candidate |
| G | 0—3 | 4 | Cạnh ngoài |
| H | 2—4 | 4 | Có thể đổi giữ tổng |
| I | 0—4 | 6 | Cạnh ngoài |
| J | 1—4 | 5 | Cạnh ngoài |
| K | 2—2 | −20 | Self-loop, không được chọn |
| L | 0—1 | 1 | Song song với A, cùng w |

Kruskal tăng theo weight, phá hòa bằng vị trí input, chọn:

`T={A,B,C,D}`; `W=1+2+2+4=9`.

### 7.1. Thay cạnh E

Đường trong T nối 0 và 2:

`0 --A(1)-- 1 --B(2)-- 2`.

Cạnh E weight2:

- Bỏ **B** weight2: `9+2−2=9` ⇒ cây `{A,C,D,E}` là MST khác.
- Bỏ **A** weight1: `9+2−1=10` ⇒ cây `{B,C,D,E}` nặng hơn MST một đơn vị.

Chính **một cạnh E** có thể cho cả kết quả “different” và kết quả “strict” bằng việc bỏ hai cạnh khác nhau.

### 7.2. Thay cạnh L song song

L trọng số1, path 0→1 chỉ có A trọng số1. Đổi `+L−A` tạo **MST khác cùng tổng9**, nhưng không có cạnh nào trên đường nhẹ hơn1 để tạo strict qua L.

### 7.3. Kết quả đầy đủ

- MST ban đầu: **9**.
- Một cây khác có tổng nhỏ nhất: **9**.
- Cây nhẹ nhất có tổng **lớn hơn 9**: **10**.
- Số MST khác nhau xét theo ID cạnh: **8**.
- Số spanning tree hợp lệ trong multigraph: **175**.

Các số đếm được xác minh bằng oracle vét cạn, trong khi thuật toán thực tế chỉ cần hai phép so sánh trên đường.

## 8. Phương pháp dễ hiểu: Kruskal + tìm đường trên cây cho mỗi cạnh ngoài

Đầu tiên chạy **Kruskal + DSU** để dựng MST/MSF và đánh dấu cạnh `inTree[id]=true` nếu được chọn. Sau đó dựng adjacency **chỉ từ các cạnh đã chọn**.

Với mỗi cạnh e ngoài MST:

1. Nếu self-loop, bỏ.
2. Chạy BFS/DFS trên cây đang chứa u,v để lấy `parent` và `viaEdge`, tức **cạnh đã dùng để tới mỗi đỉnh**.
3. Lần ngược từ v tới u, xét các cạnh trên đường để tìm:
   - `maxId`: cạnh có trọng số max, phá hòa bằng ID nhỏ nhất.
   - `lessId`: cạnh có trọng số lớn nhất **nhỏ hơn w(e)**, phá hòa ID nhỏ nhất.
4. Cập nhật ứng viên:
   - `different = W+w(e)-w(maxId)`.
   - `strict = W+w(e)-w(lessId)` nếu `lessId` tồn tại.
5. Giữ **ID cạnh thêm và cạnh bỏ** nếu đề muốn in cây mới.

**Tại sao BFS dùng được dù cạnh âm?** BFS ở đây chỉ tìm **đường duy nhất trong cây**, không tối ưu trọng số đường. Với một cây không chu trình, đường hình học giữa u,v là duy nhất.

### 8.1. Tie-break rõ ràng

Khi nhiều cách đổi cùng tổng, code dưới đây ưu tiên:

- Tổng cây mới thấp hơn.
- Nếu bằng, **ID cạnh thêm** nhỏ hơn.
- Nếu vẫn bằng, **ID cạnh bỏ** nhỏ hơn.

Với cùng trọng số trên path, max/less cũng ưu tiên ID nhỏ nhất. Tie-break chỉ để kết quả ổn định; **không thay đổi giá trị tối ưu**.

### 8.2. Độ phức tạp

- Kruskal: `O(E log E + V + E α(V))`.
- Dựng adjacency của cây/rừng: `O(V)`.
- Mỗi cạnh ngoài cây quét một đường bằng BFS, worst-case `O(V)`.
- Tổng thời gian: **`O(E log E + EV)`**.
- Bộ nhớ phụ: **`O(V+E)`**.

Khi số đỉnh và cạnh vừa phải, đây là cách cài dễ chứng minh và là **oracle triển khai** cho phiên bản LCA nhanh hơn.

## 9. Java 17 — đổi cạnh có witness

Lưu thành **MstSwapWithWitnessDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class MstSwapWithWitnessDemo {
    record Edge(int u, int v, long w, String name) {}
    record Arc(int to, int edgeId) {}
    record Swap(int add, int remove, long cost) {}
    record Result(long base, int components,
                  List<String> mstNames, Swap different, Swap strict) {}

    static final class DSU {
        int[] p, size;
        int count;

        DSU(int n) {
            p = new int[n];
            size = new int[n];
            count = n;
            for (int i = 0; i < n; i++) {
                p[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            if (p[x] != x) p[x] = find(p[x]);
            return p[x];
        }

        boolean union(int a, int b) {
            a = find(a);
            b = find(b);
            if (a == b) return false;
            if (size[a] < size[b]) {
                int tmp = a;
                a = b;
                b = tmp;
            }
            p[b] = a;
            size[a] += size[b];
            count--;
            return true;
        }
    }

    static Swap better(Swap old, Swap next) {
        if (old == null || next.cost() < old.cost()
                || (next.cost() == old.cost()
                    && (next.add() < old.add()
                        || (next.add() == old.add()
                            && next.remove() < old.remove())))) {
            return next;
        }
        return old;
    }

    static Result solve(int n, Edge[] edges) {
        if (n < 0) throw new IllegalArgumentException("Negative n");
        for (Edge e : edges) {
            if (e.u() < 0 || e.u() >= n
                    || e.v() < 0 || e.v() >= n) {
                throw new IllegalArgumentException("Invalid endpoint");
            }
        }

        Integer[] ids = new Integer[edges.length];
        for (int i = 0; i < ids.length; i++) ids[i] = i;
        Arrays.sort(ids, (a, b) -> {
            int cmp = Long.compare(edges[a].w(), edges[b].w());
            return cmp != 0 ? cmp : Integer.compare(a, b);
        });

        DSU dsu = new DSU(n);
        boolean[] inTree = new boolean[edges.length];
        List<Integer> selected = new ArrayList<>();
        long total = 0L;

        for (int id : ids) {
            Edge e = edges[id];
            if (dsu.union(e.u(), e.v())) {
                inTree[id] = true;
                selected.add(id);
                total = Math.addExact(total, e.w());
            }
        }

        List<List<Arc>> tree = new ArrayList<>();
        for (int i = 0; i < n; i++) tree.add(new ArrayList<>());
        for (int id : selected) {
            Edge e = edges[id];
            tree.get(e.u()).add(new Arc(e.v(), id));
            tree.get(e.v()).add(new Arc(e.u(), id));
        }

        Swap different = null, strict = null;

        for (int enter = 0; enter < edges.length; enter++) {
            if (inTree[enter]) continue;
            Edge e = edges[enter];
            if (e.u() == e.v()) continue;

            int[] parent = new int[n];
            int[] via = new int[n];
            Arrays.fill(parent, -1);
            Arrays.fill(via, -1);

            ArrayDeque<Integer> queue = new ArrayDeque<>();
            parent[e.u()] = e.u();
            queue.addLast(e.u());

            while (!queue.isEmpty() && parent[e.v()] == -1) {
                int u = queue.removeFirst();
                for (Arc arc : tree.get(u)) {
                    int v = arc.to();
                    if (parent[v] == -1) {
                        parent[v] = u;
                        via[v] = arc.edgeId();
                        queue.addLast(v);
                    }
                }
            }

            if (parent[e.v()] == -1) {
                throw new IllegalStateException("No path in forest");
            }

            int maxId = -1, lessId = -1;
            for (int at = e.v(); at != e.u(); at = parent[at]) {
                int id = via[at];
                long weight = edges[id].w();

                if (maxId == -1 || weight > edges[maxId].w()
                        || (weight == edges[maxId].w()
                            && id < maxId)) {
                    maxId = id;
                }

                if (weight < e.w()
                        && (lessId == -1
                            || weight > edges[lessId].w()
                            || (weight == edges[lessId].w()
                                && id < lessId))) {
                    lessId = id;
                }
            }

            if (maxId == -1 || e.w() < edges[maxId].w()) {
                throw new IllegalStateException("Bad initial MST");
            }

            long delta = Math.subtractExact(e.w(), edges[maxId].w());
            long cost = Math.addExact(total, delta);
            different = better(different, new Swap(enter, maxId, cost));

            if (lessId != -1) {
                long strictDelta = Math.subtractExact(
                        e.w(), edges[lessId].w());
                long strictCost = Math.addExact(total, strictDelta);
                if (strictCost <= total) {
                    throw new IllegalStateException("Bad strict candidate");
                }
                strict = better(strict,
                        new Swap(enter, lessId, strictCost));
            }
        }

        List<String> names = new ArrayList<>();
        for (int id : selected) names.add(edges[id].name());
        return new Result(total, dsu.count, List.copyOf(names),
                different, strict);
    }

    static String show(Swap swap, Edge[] edges) {
        if (swap == null) return "none";
        return swap.cost() + " via +" + edges[swap.add()].name()
                + " -" + edges[swap.remove()].name();
    }

    static String weight(Swap swap) {
        return swap == null ? "none" : Long.toString(swap.cost());
    }

    static Edge[] sample() {
        return new Edge[]{
            new Edge(0, 1, 1, "A"),
            new Edge(1, 2, 2, "B"),
            new Edge(2, 3, 2, "C"),
            new Edge(3, 4, 4, "D"),
            new Edge(0, 2, 2, "E"),
            new Edge(1, 3, 3, "F"),
            new Edge(0, 3, 4, "G"),
            new Edge(2, 4, 4, "H"),
            new Edge(0, 4, 6, "I"),
            new Edge(1, 4, 5, "J"),
            new Edge(2, 2, -20, "K"),
            new Edge(0, 1, 1, "L")
        };
    }

    public static void main(String[] args) {
        Edge[] data = sample();
        Result r = solve(5, data);

        System.out.println("MST cost: " + r.base());
        System.out.println("MST edges: " + r.mstNames());
        System.out.println("Different: " + show(r.different(), data));
        System.out.println("Strict: " + show(r.strict(), data));
        System.out.println("Unique: "
                + (r.different() == null || r.different().cost() > r.base()));

        Edge[] allEqual = {
            new Edge(0, 1, 1, "A"),
            new Edge(1, 2, 1, "B"),
            new Edge(0, 2, 1, "C")
        };
        Result eq = solve(3, allEqual);
        System.out.println("All equal: base=" + eq.base()
                + ", different=" + weight(eq.different())
                + ", strict=" + weight(eq.strict()));

        Edge[] unique = {
            new Edge(0, 1, 1, "A"),
            new Edge(1, 2, 1, "B"),
            new Edge(0, 2, 2, "C")
        };
        Result un = solve(3, unique);
        System.out.println("Repeated weights, unique: base="
                + un.base() + ", different=" + weight(un.different())
                + ", strict=" + weight(un.strict()));

        Edge[] disconnected = {
            new Edge(0, 1, 1, "A"),
            new Edge(1, 2, 2, "B"),
            new Edge(0, 2, 2, "C"),
            new Edge(3, 4, 5, "D"),
            new Edge(3, 4, 5, "E")
        };
        Result forest = solve(5, disconnected);
        System.out.println("Disconnected: components="
                + forest.components() + ", MSF=" + forest.base()
                + ", different=" + weight(forest.different())
                + ", strict=" + weight(forest.strict()));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MstSwapWithWitnessDemo.java
java MstSwapWithWitnessDemo
```

Stdout:

```text
MST cost: 9
MST edges: [A, B, C, D]
Different: 9 via +E -B
Strict: 10 via +E -A
Unique: false
All equal: base=2, different=2, strict=none
Repeated weights, unique: base=2, different=3, strict=3
Disconnected: components=2, MSF=8, different=8, strict=9
```

### 9.1. Giải thích trạng thái và khôi phục

DSU chọn MST/MSF; `inTree[id]` phân biệt cạnh gốc đã chọn. BFS trên rừng T cho `parent[v]` và `via[v]` là **ID cạnh cây** dẫn tới v. Khi duyệt đường ngược từ đích tới nguồn, mỗi cạnh được xem đúng một lần.

`Swap(add,remove,cost)` là **witness**. Để thật sự dựng cây mới: lấy danh sách MST ban đầu, bỏ `remove`, thêm `add`, kiểm đủ `n−1` cạnh (hoặc `n−k`) và không chu trình.

### 9.2. Vì sao self-loop âm không thể giúp?

Cạnh K=(2,2,-20) được sort đầu tiên nhưng DSU `union(2,2)` trả false. Khi xét các cạnh ngoài cây, mã cũng bỏ `u==v`. Không có cách hợp lệ để “lấy -20” vào cây MST.

### 9.3. Số học an toàn

Dùng `Long.compare` khi sort, `Math.subtractExact` và `Math.addExact` khi cộng tổng hoặc thay cạnh. Nếu input cho phép tổng vượt miền `long`, cần chuyển sang `BigInteger`. Đừng dùng `(int)(w1-w2)` làm comparator vì có thể tràn.

## 10. Tối ưu truy vấn: LCA và top hai **giá trị phân biệt**

Quét lại đường cây cho từng cạnh ngoài T là `O(EV)`. Với n,m lớn, tiền xử lý **binary lifting** trên T hoặc từng cây của MSF để trả lời trong `O(log V)`:

`topTwoDistinct(u,v) = hai trọng số LỚN NHẤT KHÁC NHAU trên P_T(u,v)`.

Ví dụ đường `[7,7,5,3]` có `first=7`, `second=5`. Đường chỉ `[7,7,7]` có `first=7` và **không có second**.

### 10.1. Bảng tổ tiên

Chọn một gốc ở mỗi thành phần, lưu:

- `depth[v]`: độ sâu trong rừng.
- `up[k][v]`: tổ tiên của v sau `2^k` cạnh (root tự trỏ tới root).
- `top[k][v]`: hai giá trị lớn nhất **phân biệt** trên đoạn từ v đi lên `2^k` cạnh; tại root là tập rỗng.

Đệ quy gộp:

`up[k][v] = up[k−1][ up[k−1][v] ]`.

`top[k][v] = merge(top[k−1][v],top[k−1][up[k−1][v]])`.

Hàm merge lấy hai giá trị lớn nhất **khác nhau** trong hợp các đoạn.

### 10.2. Truy vấn LCA

1. Nếu hai đỉnh ở hai thành phần khác nhau ⇒ không có đường.
2. Nâng đỉnh sâu hơn cho tới cùng depth, đồng thời **gộp top của các đoạn đi qua**.
3. Nếu chúng đã trùng, trả top đã gom.
4. Nếu chưa, từ k lớn xuống nhỏ, khi `up[k][u]!=up[k][v]`, nâng cả hai và gộp top hai đoạn.
5. Cuối cùng gộp hai cạnh đi lên LCA.

Sau `O(log V)` bước, thu được `first`, `second`.

### 10.3. Công thức cho mỗi cạnh ngoài cây

Cho cạnh ngoài e weight w, và top của path:

- Nếu `w<first` ⇒ MST ban đầu có lỗi hoặc query sai.
- `different = W+w−first`.
- Nếu `w>first` ⇒ `strict=W+w−first`.
- Nếu `w==first && second tồn tại` ⇒ `strict=W+w−second`.
- Nếu `w==first && second không có` ⇒ không có ứng viên strict qua e.

Nếu cần in ID cạnh bị thay, có thể lưu thêm ID trong top hoặc truy ngược **một lần cuối** để xác định ID sau khi đã biết lựa chọn e tốt nhất.

### 10.4. Độ phức tạp

- Dựng MST Kruskal: `O(ElogE + V + Eα(V))`.
- Dựng bảng binary lifting: `O(VlogV)`.
- Mỗi cạnh ngoài MST query `O(logV)`, tổng `O(ElogV)`.
- Tổng **`O(ElogE + (V+E)logV)`**.
- Bộ nhớ **`O(E+VlogV)`**.

Không dùng `0` hay `Long.MIN_VALUE` làm sentinel cho max nếu trọng số có thể âm đến cực trị của `long`; dùng **cờ tồn tại**.

## 11. Java 17 — binary lifting cho second-best

Lưu thành **MstPathTopTwoLcaDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class MstPathTopTwoLcaDemo {
    record Edge(int u, int v, long w) {}
    record Arc(int to, long weight) {}
    record Result(long base, int components, Long different, Long strict) {}

    static final class DSU {
        int[] p, sz;
        int count;
        DSU(int n) {
            p = new int[n];
            sz = new int[n];
            count = n;
            for (int i = 0; i < n; i++) {
                p[i] = i;
                sz[i] = 1;
            }
        }
        int find(int x) {
            if (p[x] != x) p[x] = find(p[x]);
            return p[x];
        }
        boolean union(int a, int b) {
            a = find(a);
            b = find(b);
            if (a == b) return false;
            if (sz[a] < sz[b]) {
                int t = a; a = b; b = t;
            }
            p[b] = a;
            sz[a] += sz[b];
            count--;
            return true;
        }
    }

    static final class TopTwo {
        boolean hasFirst, hasSecond;
        long first, second;

        void add(long w) {
            if (!hasFirst) {
                hasFirst = true;
                first = w;
                return;
            }
            if (w == first || (hasSecond && w == second)) return;
            if (w > first) {
                second = first;
                hasSecond = true;
                first = w;
            } else if (!hasSecond || w > second) {
                second = w;
                hasSecond = true;
            }
        }

        void merge(TopTwo other) {
            if (other.hasFirst) add(other.first);
            if (other.hasSecond) add(other.second);
        }
    }

    static TopTwo path(int a, int b, int[] depth,
                       int[] component, int[][] up, TopTwo[][] top) {
        if (component[a] != component[b]) {
            throw new IllegalArgumentException("Different components");
        }
        TopTwo answer = new TopTwo();
        if (depth[a] < depth[b]) {
            int t = a; a = b; b = t;
        }

        int difference = depth[a] - depth[b];
        for (int k = 0; k < up.length; k++) {
            if (((difference >>> k) & 1) != 0) {
                answer.merge(top[k][a]);
                a = up[k][a];
            }
        }
        if (a == b) return answer;

        for (int k = up.length - 1; k >= 0; k--) {
            if (up[k][a] != up[k][b]) {
                answer.merge(top[k][a]);
                answer.merge(top[k][b]);
                a = up[k][a];
                b = up[k][b];
            }
        }
        answer.merge(top[0][a]);
        answer.merge(top[0][b]);
        return answer;
    }

    static Result solve(int n, Edge[] edges) {
        if (n < 0) throw new IllegalArgumentException("Negative n");
        for (Edge e : edges) {
            if (e.u() < 0 || e.u() >= n
                    || e.v() < 0 || e.v() >= n) {
                throw new IllegalArgumentException("Invalid endpoint");
            }
        }

        Integer[] sorted = new Integer[edges.length];
        for (int i = 0; i < sorted.length; i++) sorted[i] = i;
        Arrays.sort(sorted, (a, b) -> {
            int cmp = Long.compare(edges[a].w(), edges[b].w());
            return cmp != 0 ? cmp : Integer.compare(a, b);
        });

        DSU dsu = new DSU(n);
        boolean[] inTree = new boolean[edges.length];
        List<List<Arc>> tree = new ArrayList<>();
        for (int v = 0; v < n; v++) tree.add(new ArrayList<>());

        long base = 0L;
        for (int id : sorted) {
            Edge e = edges[id];
            if (dsu.union(e.u(), e.v())) {
                inTree[id] = true;
                base = Math.addExact(base, e.w());
                tree.get(e.u()).add(new Arc(e.v(), e.w()));
                tree.get(e.v()).add(new Arc(e.u(), e.w()));
            }
        }

        int levels = 1;
        while ((1L << levels) <= Math.max(1L, (long) n)) levels++;

        int[][] up = new int[levels][n];
        TopTwo[][] top = new TopTwo[levels][n];
        int[] depth = new int[n];
        int[] component = new int[n];
        Arrays.fill(component, -1);
        for (int v = 0; v < n; v++) top[0][v] = new TopTwo();

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (int root = 0; root < n; root++) {
            if (component[root] >= 0) continue;
            component[root] = root;
            up[0][root] = root;
            queue.addLast(root);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Arc arc : tree.get(u)) {
                    int v = arc.to();
                    if (component[v] >= 0) continue;
                    component[v] = root;
                    depth[v] = depth[u] + 1;
                    up[0][v] = u;
                    top[0][v].add(arc.weight());
                    queue.addLast(v);
                }
            }
        }

        for (int k = 1; k < levels; k++) {
            for (int v = 0; v < n; v++) {
                int mid = up[k - 1][v];
                up[k][v] = up[k - 1][mid];
                TopTwo t = new TopTwo();
                t.merge(top[k - 1][v]);
                t.merge(top[k - 1][mid]);
                top[k][v] = t;
            }
        }

        Long different = null, strict = null;
        for (int i = 0; i < edges.length; i++) {
            if (inTree[i]) continue;
            Edge e = edges[i];
            if (e.u() == e.v()) continue;

            TopTwo t = path(e.u(), e.v(),
                    depth, component, up, top);
            if (!t.hasFirst || e.w() < t.first) {
                throw new IllegalStateException("Not an MST");
            }

            long diff = Math.addExact(base,
                    Math.subtractExact(e.w(), t.first));
            if (different == null || diff < different) different = diff;

            Long removed = null;
            if (e.w() > t.first) {
                removed = t.first;
            } else if (t.hasSecond) {
                removed = t.second;
            }
            if (removed != null) {
                long candidate = Math.addExact(base,
                        Math.subtractExact(e.w(), removed));
                if (candidate <= base) {
                    throw new IllegalStateException("Invalid strict swap");
                }
                if (strict == null || candidate < strict) strict = candidate;
            }
        }

        return new Result(base, dsu.count, different, strict);
    }

    static String show(Long x) {
        return x == null ? "none" : x.toString();
    }

    static Edge[] sample() {
        return new Edge[]{
            new Edge(0, 1, 1), new Edge(1, 2, 2),
            new Edge(2, 3, 2), new Edge(3, 4, 4),
            new Edge(0, 2, 2), new Edge(1, 3, 3),
            new Edge(0, 3, 4), new Edge(2, 4, 4),
            new Edge(0, 4, 6), new Edge(1, 4, 5),
            new Edge(2, 2, -20), new Edge(0, 1, 1)
        };
    }

    public static void main(String[] args) {
        Result r = solve(5, sample());
        System.out.println("LCA MST cost: " + r.base());
        System.out.println("LCA components: " + r.components());
        System.out.println("Different minimum: " + show(r.different()));
        System.out.println("Strict second: " + show(r.strict()));
        System.out.println("Unique MST: "
                + (r.different() == null || r.different() > r.base()));

        Edge[] equal = {
            new Edge(0, 1, 1),
            new Edge(1, 2, 1),
            new Edge(0, 2, 1)
        };
        System.out.println("All equal strict: "
                + show(solve(3, equal).strict()));

        Edge[] onlyTree = {
            new Edge(0, 1, 3),
            new Edge(1, 2, 4)
        };
        System.out.println("Only-tree different: "
                + show(solve(3, onlyTree).different()));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MstPathTopTwoLcaDemo.java
java MstPathTopTwoLcaDemo
```

Stdout:

```text
LCA MST cost: 9
LCA components: 1
Different minimum: 9
Strict second: 10
Unique MST: false
All equal strict: none
Only-tree different: none
```

### 11.1. Vì sao `TopTwo` dùng hai cờ?

Mọi `long`, kể cả `0` và `Long.MIN_VALUE`, đều có thể là trọng số cạnh thật. Các cờ `hasFirst`, `hasSecond` cho biết một hay hai giá trị phân biệt đã tồn tại; tránh dùng **giá trị trọng số** làm sentinel.

Khi gặp trọng số bằng `first` hoặc `second`, `TopTwo.add` **bỏ qua** để không lưu hai max bằng nhau.

### 11.2. Bảo toàn thông tin trên đoạn nâng

Mỗi khi nâng ancestor từ u lên `up[k][u]`, hàm `path` cũng gộp `top[k][u]`. Nếu chỉ cập nhật `up` mà quên gộp, các cạnh trên đoạn vừa nhảy **biến mất** khỏi phép tính max và second, làm điều kiện strict sai.

### 11.3. Vùng áp dụng

Chương trình này chỉ trả **trọng số** của nghiệm khác và strict; chương trình trước còn trả **ID các cạnh đổi**. Nếu cần list cạnh strict sau LCA, lưu ID cùng trọng số hoặc tìm lại đường trong cây đúng một lần cho cặp cạnh cuối cùng.

## 12. Phát hiện MST không duy nhất theo **nhóm trọng số**

Nếu chỉ muốn kiểm MST/MSF có duy nhất không, chưa cần LCA. Có thể xử lý Kruskal bằng **các nhóm cạnh có cùng w**.

Tại thời điểm xử lý một nhóm trọng số w, DSU toàn cục chỉ được chứa liên thông do các cạnh **nhẹ hơn w**.

1. Chưa union cạnh nào của nhóm w.
2. Với mỗi e=(u,v) trong nhóm, lấy `ru=find(u)`, `rv=find(v)` bằng DSU hiện tại.
3. Nếu `ru==rv`, cạnh này không nối thêm nhóm; bỏ khỏi kiểm tra lựa chọn cùng w.
4. Nếu khác, thêm cạnh (ru,rv) vào **multigraph tạm**; giữ cạnh song song theo ID.
5. Nếu graph tạm có **chu trình** (kể cả chu trình hai cạnh song song), tồn tại nhiều cách chọn cạnh cùng trọng số để nối các nhóm ⇒ có nhiều MST/MSF.
6. Sau khi đã kiểm **toàn bộ nhóm**, mới union toàn bộ cạnh của nhóm vào DSU toàn cục; chuyển sang w kế tiếp.

**Lỗi hay gặp:** union từng cạnh của nhóm w ngay trước khi kiểm các cạnh sau. Việc này có thể làm mất bằng chứng có chu trình giữa những lựa chọn **đồng trọng số**, khiến bạn kết luận sai là unique.

Ví dụ tam giác 1,1,1: graph tạm của nhóm w=1 có chu trình ⇒ nhiều MST. Tam giác 1,1,2: nhóm w=1 tạo đường không chu trình, nhóm w=2 có hai đầu đã cùng component ⇒ MST duy nhất.

Phương pháp này trả **boolean uniqueness**, không trả trực tiếp giá trị **strict second-best**; với strict vẫn cần trọng số đường cây.

## 13. Oracle độc lập: vét cạn các rừng khung trên đồ thị nhỏ

Khi n,m nhỏ, có thể liệt kê mọi tập con cạnh để kiểm chứng ba thứ:

- `minimum`: tổng MST/MSF tối ưu.
- `minimumForests`: số rừng khung khác nhau xét theo **ID cạnh** đạt optimum.
- `strictSecond`: tổng nhỏ nhất **lớn hơn minimum**.
- `validForests`: tổng số rừng khung hợp lệ trong input.

Tính k thành phần liên thông của **đồ thị gốc** (DSU union toàn bộ cạnh). Một rừng khung đầy đủ phải có chính xác **n−k cạnh**, không có chu trình và có k component sau khi chọn.

Mọi subset đáp ứng những điều kiện này đều là một rừng khung đầy đủ, kể cả khi có đỉnh cô lập. Đếm subset theo ID nên cạnh song song là lựa chọn khác.

### 13.1. Java 17 — brute-force oracle có tie và strict second

Lưu thành **MstExchangeBruteOracleDemo.java**:

```java
public class MstExchangeBruteOracleDemo {
    record Edge(int u, int v, long w) {}
    record Result(int components, long minimum, long minCount,
                  Long strict, long validCount) {}

    static final class DSU {
        int[] p, sz;
        int count;

        DSU(int n) {
            p = new int[n];
            sz = new int[n];
            count = n;
            for (int i = 0; i < n; i++) {
                p[i] = i;
                sz[i] = 1;
            }
        }

        int find(int x) {
            if (p[x] != x) p[x] = find(p[x]);
            return p[x];
        }

        boolean union(int a, int b) {
            a = find(a);
            b = find(b);
            if (a == b) return false;
            if (sz[a] < sz[b]) {
                int t = a; a = b; b = t;
            }
            p[b] = a;
            sz[a] += sz[b];
            count--;
            return true;
        }
    }

    static Result solve(int n, Edge[] edges) {
        if (n < 0 || edges.length > 18) {
            throw new IllegalArgumentException(
                    "Small graphs: n>=0, m<=18");
        }

        DSU original = new DSU(n);
        for (Edge e : edges) {
            if (e.u() < 0 || e.u() >= n
                    || e.v() < 0 || e.v() >= n) {
                throw new IllegalArgumentException("Invalid endpoint");
            }
            original.union(e.u(), e.v());
        }

        int k = original.count;
        int need = n - k;
        int masks = 1 << edges.length;

        boolean found = false;
        long best = 0L, minCount = 0L, valid = 0L;
        Long second = null;

        for (int mask = 0; mask < masks; mask++) {
            if (Integer.bitCount(mask) != need) continue;

            DSU chosen = new DSU(n);
            boolean cycle = false;
            long total = 0L;

            for (int i = 0; i < edges.length; i++) {
                if ((mask & (1 << i)) == 0) continue;
                Edge e = edges[i];
                if (!chosen.union(e.u(), e.v())) {
                    cycle = true;
                    break;
                }
                total = Math.addExact(total, e.w());
            }

            if (cycle || chosen.count != k) continue;
            valid++;

            if (!found || total < best) {
                if (found) second = best;
                best = total;
                minCount = 1;
                found = true;
            } else if (total == best) {
                minCount++;
            } else if (second == null || total < second) {
                second = total;
            }
        }

        if (!found) {
            throw new IllegalStateException(
                    "Finite graph has a spanning forest");
        }
        return new Result(k, best, minCount, second, valid);
    }

    static String show(Long value) {
        return value == null ? "none" : value.toString();
    }

    static Edge[] sample() {
        return new Edge[]{
            new Edge(0, 1, 1), new Edge(1, 2, 2),
            new Edge(2, 3, 2), new Edge(3, 4, 4),
            new Edge(0, 2, 2), new Edge(1, 3, 3),
            new Edge(0, 3, 4), new Edge(2, 4, 4),
            new Edge(0, 4, 6), new Edge(1, 4, 5),
            new Edge(2, 2, -20), new Edge(0, 1, 1)
        };
    }

    public static void main(String[] args) {
        Result main = solve(5, sample());
        System.out.println("Brute minimum: " + main.minimum());
        System.out.println("Brute MST count: " + main.minCount());
        System.out.println("Brute strict second: " + show(main.strict()));
        System.out.println("Brute valid trees: " + main.validCount());

        Edge[] equal = {
            new Edge(0, 1, 1),
            new Edge(1, 2, 1),
            new Edge(0, 2, 1)
        };
        Result eq = solve(3, equal);
        System.out.println("Equal triangle: min=" + eq.minimum()
                + ", count=" + eq.minCount()
                + ", strict=" + show(eq.strict()));

        Edge[] unique = {
            new Edge(0, 1, 1),
            new Edge(1, 2, 1),
            new Edge(0, 2, 2)
        };
        Result un = solve(3, unique);
        System.out.println("Tie but unique: min=" + un.minimum()
                + ", count=" + un.minCount()
                + ", strict=" + show(un.strict()));

        Edge[] disconnected = {
            new Edge(0, 1, 1),
            new Edge(1, 2, 2),
            new Edge(0, 2, 2),
            new Edge(3, 4, 5),
            new Edge(3, 4, 5)
        };
        Result forest = solve(5, disconnected);
        System.out.println("Disconnected: components="
                + forest.components() + ", min=" + forest.minimum()
                + ", count=" + forest.minCount()
                + ", strict=" + show(forest.strict()));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MstExchangeBruteOracleDemo.java
java MstExchangeBruteOracleDemo
```

Stdout:

```text
Brute minimum: 9
Brute MST count: 8
Brute strict second: 10
Brute valid trees: 175
Equal triangle: min=2, count=3, strict=none
Tie but unique: min=2, count=1, strict=3
Disconnected: components=2, min=8, count=4, strict=9
```

### 13.2. Vì sao không chỉ so Kruskal với LCA?

Hai phiên bản có thể **cùng sai** nếu dùng cùng một công thức nhầm “max thứ hai” hoặc cùng bỏ sót cạnh song song. Vét cạn không dùng max path và không cần LCA, nên là một oracle **độc lập về thuật toán**.

Với input mẫu, có **8 MST cùng trọng số 9**, nhưng strict second có tổng **10**. Cứ lấy “cây thứ hai theo thứ tự weight” khi có tie sẽ vẫn nhận 9, sai nếu đề muốn strict.

### 13.3. Giới hạn vét cạn

Có `2^m` tập con cạnh. Với mỗi subset, code dựng DSU O(n) và thử tới m cạnh. Chặn trên:

`O(2^m (n + m α(n)))` thời gian, `O(n+m)` bộ nhớ phụ.

Giới hạn m<=18 là **giới hạn cho demo/kiểm thử**, không phải điều kiện tồn tại MST. Với m lớn, dùng thuật toán thay cạnh/LCA.

## 14. Chứng minh kết quả và kiểm thử witness

### 14.1. Tính đúng của một phép đổi

T là cây, thêm e ngoài T tạo một chu trình duy nhất. Bỏ f trên P loại chu trình và giữ đủ liên thông; tổng mới là W+w(e)-w(f). Vì e khác ID với cạnh T, tập cạnh mới chắc chắn khác T.

### 14.2. Tính đúng của ứng viên “different”

Với e cố định, bỏ cạnh có trọng số lớn nhất trên P làm tổng nhỏ nhất trong mọi phép đổi dùng e. Quét mọi cạnh ngoài T bao phủ các phép đổi cơ bản. Theo tính chất trao đổi cơ sở cây khung, một nghiệm khác tối ưu có thể chọn trong các cây khác **một lần đổi** từ T; vì vậy lấy min cho `different`.

### 14.3. Tính đúng của ứng viên “strict”

Một phép đổi tăng tổng iff `w(f)<w(e)`. Trong số f hợp lệ, chọn f có weight lớn nhất để giảm mức tăng dương. Quét mọi e ngoài T để lấy tăng dương nhỏ nhất. Định lý trao đổi tương ứng bảo đảm mức tăng dương nhỏ nhất của cây khung tìm được qua một phép đổi khi có cây nặng hơn MST.

Nếu mọi C_strict đều không tồn tại, không có cây với tổng lớn hơn W. Đây không đồng nghĩa không có cây khác: có thể có rất nhiều MST đồng trọng số.

### 14.4. Kiểm chứng ID cạnh thật

Với một witness `(+e,−f)`:

1. e thuộc input, **không thuộc T**.
2. f thuộc T.
3. f nằm trên đường P_T(e.u,e.v).
4. T'=T+e−f có đúng `n−1` (hoặc `n−k`) cạnh.
5. DSU trên T' xác nhận không chu trình và giữ đủ component.
6. Tổng T' bằng `W+w(e)−w(f)`.

Nếu chỉ so số cost mà bỏ kiểm witness, code có thể in đúng giá trị nhưng sai danh sách cạnh.

## 15. Nhiều tie không có nghĩa nhiều MST

Tam giác 1,1,2 có hai cạnh cùng trọng số nhỏ nhất nhưng MST **duy nhất**. Điều quyết định uniqueness là tồn tại cạnh ngoài T e sao cho:

`w(e)=maxWeight(P_T(e.u,e.v))`.

Mặt khác, toàn bộ trọng số khác nhau ⇒ MST duy nhất, nhưng điều ngược lại **không đúng**.

Nếu chỉ cần boolean unique, Kruskal nhóm bằng trọng số ở phần 12 thường phù hợp hơn dùng toàn bộ LCA. Nếu cần **cây khác thực tế** và **strict second**, vẫn nên dùng phép thay cạnh.

## 16. Những lỗi phổ biến

### Lỗi 1 — Nhầm “cây khác” với “strict second”

Một cây đổi ID nhưng tổng bằng W là đáp án hợp lệ cho **different**, không hợp lệ cho **strictly heavier**.

### Lỗi 2 — Lưu hai cạnh lớn nhất kể cả trùng trọng số

Đường `[7,7,5]`, e weight7 cần bỏ cạnh 5 để tăng 2. Hai ID cạnh weight7 không đủ dữ liệu.

### Lỗi 3 — Bỏ qua cạnh e khi `w(e)==maxPath`

e vẫn có thể cho strict candidate bằng cách bỏ cạnh **nhẹ hơn max** trên đường.

### Lỗi 4 — Chọn cạnh bỏ không nằm trên chu trình

Bỏ nhầm f khác đường có thể làm cây mất liên thông và vẫn giữ chu trình.

### Lỗi 5 — Coi self-loop âm là cạnh hữu ích

Self-loop không được chọn vào spanning tree/MSF dù có chi phí âm.

### Lỗi 6 — Gộp hai cạnh song song

Trong multigraph, cạnh có cùng hai đầu nhưng khác ID vẫn là các lựa chọn riêng, có thể tạo MST khác.

### Lỗi 7 — Dùng 0 làm sentinel max

Trên đường trọng số toàn âm, 0 không phải một max hợp lệ; dùng cờ `hasFirst/hasSecond`.

### Lỗi 8 — Dùng Long.MIN_VALUE làm sentinel không có trọng số

`Long.MIN_VALUE` có thể là **trọng số thật**. Cờ tồn tại hoặc Optional kiểu phù hợp mới an toàn.

### Lỗi 9 — Dùng phép trừ cho comparator

`w1-w2` có thể tràn. Dùng `Long.compare`.

### Lỗi 10 — Không kiểm tràn khi tính tổng cây đổi

Dùng `Math.addExact`, `Math.subtractExact` hoặc `BigInteger`, nhất là trọng số gần giới hạn kiểu máy.

### Lỗi 11 — Tính LCA trên graph gốc có chu trình

LCA và đường duy nhất chỉ có nghĩa trên **cây/rừng đã chọn**, không trực tiếp trên graph gốc.

### Lỗi 12 — Nâng tổ tiên mà không gộp top đoạn

Mỗi jump `2^k` phải cộng dữ liệu về các cạnh đi qua; nếu quên, max và max thứ hai thiếu giá trị.

### Lỗi 13 — Kết luận unique chỉ từ việc có cạnh trùng trọng số

Cạnh bằng nhau không đồng nghĩa tạo được một phép đổi `w(e)==max(path)`. Cần điều kiện đường cây hoặc xét nhóm Kruskal đúng.

### Lỗi 14 — Chọn cạnh Kruskal bằng ID trước trọng số

ID chỉ dùng tie-break khi w bằng nhau; nếu sort ID trước, có thể dựng **cây không tối ưu**.

### Lỗi 15 — Không xử lý graph rời rạc

Kruskal khi k>1 trả MSF, không phải MST toàn graph; các cạnh thay chỉ trong cùng component.

### Lỗi 16 — Chỉ kiểm số cạnh rồi gọi là cây

N−1 cạnh vẫn có thể tạo chu trình và bỏ đỉnh cô lập. Phải kiểm liên thông và không chu trình.

### Lỗi 17 — In `Long.MAX_VALUE` nếu không có strict

Đây là sentinel nội bộ nguy hiểm; dùng `null`, `OptionalLong` hoặc trạng thái `none` minh bạch.

### Lỗi 18 — Đếm số MST bằng số tie trong sort

Số MST phụ thuộc cấu trúc chu trình của các cạnh đồng trọng số sau khi co DSU, không phải số lượng tie đơn thuần.

### Lỗi 19 — Quên giữ ID cạnh ban đầu sau sort

Khi in witness `+e−f`, phải dùng **ID gốc**, không dùng vị trí mới trong mảng đã sort.

### Lỗi 20 — So list cạnh khác thứ tự rồi kết luận khác cây

Hai list với thứ tự khác nhau nhưng cùng ID tập hợp là **cùng một cây**. Chuẩn hóa bằng set ID.

## 17. Bộ kiểm thử bao phủ các ngữ nghĩa

| Tình huống | MST/MSF minimum | Different | Strict |
|---|---:|---:|---:|
| Tam giác 1,1,1 | 2 | 2 | Không có |
| Tam giác 1,1,2 | 2 | 3 | 3 |
| Graph 5 đỉnh có tie, loop, parallel | 9 | 9 | 10 |
| Graph tự là cây có hai cạnh 3,4 | 7 | Không có | Không có |
| Hai cạnh song song −3,−3 nối 2 đỉnh | −3 | −3 | Không có |
| Hai cạnh song song −3,−2 nối 2 đỉnh | −3 | −2 | −2 |
| Một đỉnh, một self-loop −100 | 0 | Không có | Không có |
| Graph 5 đỉnh, hai component mẫu | MSF 8 | MSF 8 | MSF 9 |
| n=3, không cạnh | MSF 0 | Không có | Không có |
| Cạnh cầu nặng | Cầu bắt buộc | Chỉ đổi các cạnh khác | Theo những cạnh có thể đổi |
| Các trọng số đều khác nhau | Unique MST | >W nếu có | >W nếu có |

### 17.1. Randomized tests có tính độc lập

Sinh nhiều graph n nhỏ, m nhỏ, trọng số trong `−5..5`, **cho phép lặp cặp đỉnh, self-loop và graph rời rạc**:

- Tính thành phần k từ **toàn bộ cạnh gốc**.
- Chạy Kruskal + đường cây, tính minimum, different, strict.
- Chạy Kruskal + LCA top-two phân biệt, so cost.
- Dùng brute-force tất cả subset có n−k cạnh, kiểm cấu trúc và lấy minimum, số MSF optimum, strict.
- Nếu `minCount>1`, phải có different=minimum; nếu `minCount==1` thì different=strict hoặc cùng null.
- Kiểm `strict > minimum` nếu tồn tại, không chấp nhận bằng.
- Kiểm witness thật sự tạo cây/rừng có tổng như công bố.

Thử trọng số âm và tie là **bắt buộc** để bắt lỗi sentinel/max thứ hai.

## 18. Bài tập tự luyện có đáp án

### Bài 1 — Thêm cạnh vào cây

Thêm một cạnh e ngoài cây T vô hướng, u≠v. T+e có bao nhiêu chu trình?

**Đáp án:** đúng một, gồm e và đường P_T(u,v).

### Bài 2 — Điều kiện bỏ cạnh

Sau khi thêm e, có được bỏ bất kỳ cạnh cũ nào không?

**Đáp án:** không. Phải bỏ một cạnh trên P_T(u,v) để còn cây liên thông không chu trình.

### Bài 3 — Công thức tổng

MST W=100; thêm e weight9, bỏ f weight7. Tổng mới?

**Đáp án:** `100+9−7=102`.

### Bài 4 — Cạnh ngoài bằng max

MST W=50, e weight4 và max trên đường bằng4. Có MST khác không?

**Đáp án:** có, thay e cho cạnh trên path có weight4, tổng vẫn 50.

### Bài 5 — Max trên đường

MST W=20, e weight8; path weights `[1,5,3]`. Different candidate?

**Đáp án:** `20+8−5=23`, đồng thời là strict candidate tốt nhất qua e vì e>max.

### Bài 6 — Max phân biệt thứ hai

MST W=20, e weight5, path `[5,5,3,1]`. Strict candidate?

**Đáp án:** `20+5−3=22`, không phải 20.

### Bài 7 — Toàn giá trị bằng nhau

Path `[2,2,2]`, e weight2. Có strict candidate qua e không?

**Đáp án:** không; mọi phép bỏ cạnh đều cho tổng W.

### Bài 8 — Graph tam giác toàn bằng nhau

Tam giác 1,1,1 có bao nhiêu MST? Strict second?

**Đáp án:** ba MST, tất cả bằng2, strict không tồn tại.

### Bài 9 — Tie nhưng unique

Tam giác 1,1,2 có bao nhiêu MST? Different cost?

**Đáp án:** một MST bằng2, different cost3.

### Bài 10 — Self-loop

Cạnh `(2,2,-100)` có dùng làm cạnh mới để tạo spanning tree khác được không?

**Đáp án:** không; nó là self-loop, bản thân tạo chu trình và không nối thêm đỉnh.

### Bài 11 — Cạnh song song

Hai cạnh khác ID nối 0—1 cùng weight5, đồ thị có đúng hai đỉnh. Có mấy MST?

**Đáp án:** hai MST xét theo ID cạnh, mỗi cây tổng5.

### Bài 12 — Đường toàn âm

Path có weight `[-7,-3]`, e ngoài weight−2. Different candidate thay cạnh nào?

**Đáp án:** bỏ cạnh −3 là max trên đường, mức tăng `−2−(−3)=1`. Không dùng 0 làm max.

### Bài 13 — MSF có mấy cạnh?

Graph n=9, k=3 component. MSF có bao nhiêu cạnh?

**Đáp án:** `9−3=6`.

### Bài 14 — MST khi disconnected?

Graph hai component có MST toàn graph không?

**Đáp án:** không. Chỉ có MSF là hợp các MST của từng component.

### Bài 15 — LCA nâng ancestor

`up[k][v]` đại diện tổ tiên cách v bao nhiêu cạnh?

**Đáp án:** `2^k` cạnh; phải gộp thông tin top trên đoạn đó.

### Bài 16 — Chi phí quét đường

Nếu mỗi cạnh ngoài cây duyệt BFS trên cây O(V), tổng thời gian lớn nhất phần truy vấn?

**Đáp án:** `O(EV)`.

### Bài 17 — Chi phí LCA

Tiền xử lý cây bằng binary lifting và truy vấn top-two lần lượt bao nhiêu?

**Đáp án:** `O(VlogV)` chuẩn bị, `O(logV)` mỗi truy vấn; kết hợp m cạnh ngoài cho `O(ElogV)`.

### Bài 18 — Phát hiện unique

Nếu mọi cạnh ngoài T có `w(e)>max(P_T(e.u,e.v))`, MST có duy nhất không?

**Đáp án:** có.

### Bài 19 — Dấu điều kiện strict

Candidate mới bằng W. Có đưa vào `strictSecond` không?

**Đáp án:** không. Strict phải thỏa **`candidate>W`**.

### Bài 20 — Truy vết

Witness trả `(+E,−A)`. Xây cây mới thế nào?

**Đáp án:** từ tập cạnh MST, bỏ ID A và thêm ID E; kiểm cạnh mới thuộc graph, không chu trình, nối đủ và tổng đúng.

### Bài 21 — MST khác tốt nhất

Graph có 8 MST cùng weight9 và các cây khác bắt đầu từ weight10. Different và strict bằng bao nhiêu?

**Đáp án:** different **9**, strict **10**.

### Bài 22 — Nhóm trọng số Kruskal

Khi kiểm uniqueness, tại sao chưa union cạnh của cùng nhóm weight w trước khi phân tích graph tạm?

**Đáp án:** union sớm có thể che khuất những cạnh đồng trọng số tạo lựa chọn ngang giá và làm mất bằng chứng có MST khác.

## 19. Checklist trước khi nộp bài second-best MST

1. Đồ thị **vô hướng** hay có hướng?
2. Đề hỏi **different edge set** hay **strictly larger total**?
3. Có chắc G **liên thông** nếu gọi là MST không? Nếu không, MSF.
4. Đỉnh cô lập và n=0/1 đã được xử lý đúng hợp đồng?
5. MST ban đầu đã được dựng chính xác bằng Kruskal/Prim?
6. Cạnh gốc có ID riêng, nhất là các cạnh song song?
7. Đã bỏ self-loop khỏi ứng viên đổi?
8. Đã dựng adjacency của **T**, không phải graph gốc?
9. Có tìm đường P_T(u,v) duy nhất cho mỗi cạnh ngoài T?
10. **Different:** bỏ cạnh max trên P?
11. **Strict:** bỏ cạnh max **nhỏ hơn** w(e)?
12. Nếu `w(e)==max`, có tìm **max thứ hai PHÂN BIỆT** không?
13. Khi không có second, có bỏ ứng viên strict qua e?
14. `different` có thể bằng W; `strict` bắt buộc >W?
15. Có trả `none` nếu không có cây khác hoặc không có strict?
16. Nếu in cây, có lưu cặp ID cạnh `+e,−f`?
17. Có kiểm chứng cây mới đủ cạnh, liên thông và không chu trình?
18. Có dùng tie-break ổn định khi nhiều max/candidate bằng nhau?
19. Có tránh comparator kiểu phép trừ và tràn tổng `long`?
20. Nếu graph lớn, có chuyển từ quét đường O(EV) sang LCA O(ElogV)?
21. Trong top-two, có giữ **hai giá trị phân biệt** bằng cờ tồn tại?
22. Có thử tam giác all-equal, tie-but-unique, negative, loop, parallel, tree-only và disconnected?
23. Có đối chiếu bằng vét cạn trên input nhỏ với **mức trọng số strict**, không phải cây thứ hai theo list?
24. Có trình bày rõ MST khác đồng tối ưu, strictly second-best và điều kiện uniqueness?

**Kết luận:** với MST T có tổng W, mỗi cạnh e ngoài cây tạo một chu trình khi thêm vào T. Bỏ cạnh f thuộc đường nối hai đầu e tạo cây mới có tổng `W+w(e)−w(f)`. Muốn **cây khác nhẹ nhất**, bỏ **cạnh lớn nhất** trên đường. Muốn **cây nhẹ nhất có tổng lớn hơn W**, bỏ **cạnh lớn nhất có trọng số nhỏ hơn w(e)**; khi `w(e)` bằng max trên đường, đây chính là **trọng số max thứ hai PHÂN BIỆT**. Cạnh bằng nhau có thể tạo nhiều MST nhưng strict second có thể không tồn tại. Kruskal + quét đường đơn giản; LCA + binary lifting tăng tốc nhiều truy vấn. Mọi kết luận phải tách rõ đồ thị có MST hay chỉ có MSF khi không liên thông.

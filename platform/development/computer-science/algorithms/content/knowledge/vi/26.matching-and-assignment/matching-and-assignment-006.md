# Phủ đỉnh nhỏ nhất trong đồ thị hai phía từ ghép cặp

> **Chủ đề:** Computer Science Algorithms → **Ghép cặp và phân công** (*Matching and Assignment*).  
> **Mục tiêu:** Tìm **phủ đỉnh nhỏ nhất** (*minimum vertex cover*, MVC) của một **đồ thị hai phía vô hướng** sau khi tính **ghép cặp cực đại** (*maximum bipartite matching*). Hiểu định lý **Kőnig**, thuật toán duyệt **đường luân phiên** từ các đỉnh trái chưa ghép, công thức `(L\Z_L)∪(R∩Z_R)`, chứng minh tính tối ưu, cài Java 17, kiểm thử bằng vét cạn và tránh nhầm thuật toán với bài toán đồ thị tổng quát.

## 1. Bài toán và cách diễn giải đầu ra

Cho đồ thị hai phía `G=(L∪R,E)`:

- `L` là tập đỉnh **phía trái**, thường đánh chỉ số `0..nL−1`.
- `R` là tập đỉnh **phía phải**, đánh chỉ số **riêng** `0..nR−1`.
- Mỗi cạnh nối một đỉnh bên L với một đỉnh bên R. Không có cạnh giữa hai đỉnh cùng phía.
- Đồ thị ở đây **vô hướng**. Trong code, `adj[u]` có các chỉ số v thuộc R mà đỉnh trái u nối tới.

**Phủ đỉnh** (*vertex cover*) là tập đỉnh `C⊆L∪R` sao cho **mỗi cạnh (u,v)∈E có ít nhất một đầu thuộc C**. Không bắt buộc cả hai đầu đều được chọn; chỉ cần một đầu đủ để “phủ” cạnh.

**Phủ đỉnh nhỏ nhất** (*minimum vertex cover*) là phủ đỉnh có **ít đỉnh nhất** trong tất cả phủ đỉnh hợp lệ:

`minimize |C| subject to: ∀(u,v)∈E, u∈C hoặc v∈C`.

Nếu đồ thị không có cạnh, **C=∅**, size 0, là nghiệm tối ưu.

### 1.1. Ghép cặp là gì?

**Ghép cặp** (*matching*) M là một tập cạnh **không có hai cạnh nào dùng chung một đỉnh**.

- Mỗi đỉnh ghép với **tối đa một đỉnh đối diện**.
- Đỉnh **tự do/chưa ghép** là đỉnh không chạm cạnh nào thuộc M.
- **Ghép cặp cực đại về kích thước** (*maximum matching*) có **nhiều cạnh nhất**, ký hiệu `ν(G)=|M*|`.
- Một **ghép cặp cực đại theo bao hàm** (*maximal matching*) chỉ là ghép cặp không thể thêm một cạnh mà vẫn giữ tính matching. Nó **chưa chắc** là matching có kích thước tối đa.

Phân biệt **maximum** và **maximal** là tối quan trọng, vì công thức khôi phục phủ đỉnh tối ưu phía sau **yêu cầu maximum matching**.

### 1.2. Ghép cặp khác phủ đỉnh

Ghép cặp **chọn cạnh**, sao cho các cạnh không chung đầu. Phủ đỉnh **chọn đỉnh**, sao cho mọi cạnh đều có một đầu được chọn. Hai tập khác loại đối tượng, nhưng trên đồ thị hai phía, **giá trị tối ưu bằng nhau**.

Ví dụ cạnh duy nhất `L0—R0`: matching tối đa chọn cạnh ấy, size 1; phủ đỉnh tối thiểu có thể chọn `{L0}` hoặc `{R0}`, size 1.

### 1.3. Đầu ra nên trả những gì?

Một chương trình hoàn chỉnh nên trả:

1. `matchingSize`: số cạnh trong maximum matching.
2. `pairLeft[u]`: đỉnh R được ghép với u, hoặc `-1` nếu u tự do.
3. `pairRight[v]`: đỉnh L được ghép với v, hoặc `-1` nếu v tự do.
4. `Z_L`, `Z_R`: những đỉnh tới được qua đường luân phiên xuất phát từ **tất cả đỉnh tự do ở L**.
5. `coverLeft = L\Z_L` và `coverRight = Z_R`.
6. `coverSize = |coverLeft|+|coverRight| = matchingSize`.

Trả hai danh sách `coverLeft`, `coverRight` riêng biệt giúp tránh nhầm đỉnh `L0` với `R0`, vốn có cùng chỉ số số nguyên nhưng là **hai đỉnh khác nhau**.

## 2. Định lý Kőnig: cầu nối giữa matching và vertex cover

**Định lý Kőnig** (*Kőnig's theorem*): đối với mọi đồ thị **hai phía hữu hạn**,

`|maximum matching| = |minimum vertex cover|`.

Thường ký hiệu:

`ν(G) = τ(G)`,

trong đó ν là kích thước ghép cặp lớn nhất, τ là kích thước phủ đỉnh nhỏ nhất.

Đẳng thức này **không đúng với mọi đồ thị vô hướng**. Ví dụ tam giác ba đỉnh là đồ thị **không hai phía**, maximum matching có size 1 nhưng mọi vertex cover cần ít nhất 2 đỉnh.

### 2.1. Bất đẳng thức dễ: mọi vertex cover ≥ mọi matching

Lấy **bất kỳ matching M**, gồm k cạnh không chung đỉnh. Muốn phủ k cạnh ấy, ta phải chọn **ít nhất k đỉnh**, vì một đỉnh không thể phủ **hai cạnh thuộc M** (chúng không chung đầu).

Do đó đối với mọi cover C:

`|M| ≤ |C|`.

Đặc biệt:

`ν(G) ≤ τ(G)`.

Bước này đúng trên **mọi đồ thị**, không cần giả thiết hai phía.

### 2.2. Bước khó: từ một maximum matching dựng cover size bằng matching

Trên đồ thị hai phía, ta sẽ dùng đường luân phiên từ đỉnh trái chưa ghép để dựng C thỏa:

`|C| = |M|`.

Kết hợp với bất đẳng thức trên:

`|M| ≤ τ(G) ≤ |C| = |M|`.

Vậy C là **minimum vertex cover**, đồng thời M là **maximum matching**. Phần 4–5 xây thuật toán và chứng minh từng bước.

## 3. Đường luân phiên và đường tăng

Cho matching M hiện tại.

Một **đường luân phiên** (*alternating path*) là đường trong đồ thị mà các cạnh lần lượt là:

`không thuộc M, thuộc M, không thuộc M, thuộc M, ...`.

Khi xuất phát từ một đỉnh **chưa ghép ở L**, ta đi:

1. Từ **L sang R** qua **cạnh không thuộc M**.
2. Từ **R sang L** qua **cạnh đang thuộc M** (nếu R đó đã được ghép).
3. Lặp lại cho tới khi hết đường có thể đi.

Một **đường tăng** (*augmenting path*) là đường luân phiên bắt đầu và kết thúc ở **hai đỉnh tự do** (một ở L, một ở R). Đảo trạng thái thuộc matching của mọi cạnh trên đường tăng sẽ **tăng kích thước matching thêm 1**.

### 3.1. Ví dụ cần tăng lại matching cũ

```text
L0 -- R0
 | 
 R1

L1 -- R0
```

Hai đỉnh trái L0,L1; hai đỉnh phải R0,R1; các cạnh `(L0,R0)`, `(L0,R1)`, `(L1,R0)`.

Giả sử matching tạm mới có `M={(L0,R0)}`, L1 chưa ghép:

- Từ L1 đi cạnh chưa ghép `(L1,R0)`.
- R0 đang ghép L0, nên theo cạnh ghép `(R0,L0)`.
- Từ L0 đi cạnh chưa ghép `(L0,R1)`.
- R1 chưa ghép ⇒ tìm thấy **đường tăng**.

Đảo cạnh trên đường này cho matching mới:

`M'={(L1,R0),(L0,R1)}`, size 2.

Nếu dừng ở matching size 1 rồi cố dùng định lý Kőnig để báo MVC size 1, kết quả sẽ sai. **Phải tìm maximum matching trước.**

### 3.2. Dấu hiệu matching đã tối đa

**Định lý Berge:** matching M có kích thước tối đa khi và chỉ khi **không còn đường tăng** so với M.

Trên đồ thị hai phía, đường tăng bắt đầu từ một đỉnh tự do bên L, kết thúc ở một đỉnh tự do bên R. Thuật toán Hopcroft–Karp hoặc DFS tăng ghép (*Kuhn*) khai thác tiêu chí này để tìm maximum matching.

Sau khi matching tối đa, phép duyệt luân phiên từ các đỉnh tự do ở L sẽ **không thể** tới một đỉnh tự do ở R. Đây là điều kiện quan trọng trong chứng minh |cover|=|matching|.

## 4. Thuật toán khôi phục phủ đỉnh từ maximum matching

Giả sử đã có maximum matching M, lưu:

- `pairL[u] = v` nếu `(L_u,R_v)∈M`, ngược lại `-1`.
- `pairR[v] = u` nếu `(L_u,R_v)∈M`, ngược lại `-1`.

### 4.1. Bước 1 — chọn tất cả nguồn BFS

Khởi tạo `Z_L=∅`, `Z_R=∅`.

**Đưa vào hàng đợi tất cả đỉnh L chưa ghép**, tức `pairL[u]==-1`, đánh dấu chúng vào `Z_L`.

Không chỉ chọn một đỉnh chưa ghép: các thành phần liên thông và nhánh luân phiên khác nhau có thể phát sinh từ nhiều đỉnh nguồn.

### 4.2. Bước 2 — duyệt đường luân phiên

Lặp khi queue còn đỉnh trái u:

- Với mỗi cạnh `(u,v)` từ L sang R **không thuộc M** (`pairL[u]!=v`):
  - Nếu R_v chưa vào `Z_R`, thêm v.
  - Nếu R_v đang ghép với L_x (`pairR[v]=x`), và x chưa vào `Z_L`, thêm x và enqueue x.
  - Nếu R_v **chưa ghép**, tìm thấy đường tăng ⇒ matching ban đầu **chưa maximum**, không được công bố MVC đã tối ưu.

Ta chỉ cần queue các đỉnh **bên L**; khi gặp R qua cạnh chưa ghép, tức thì theo cạnh ghép ngược về L nếu có. Tương đương có thể duyệt trên đồ thị trạng thái gồm hai loại đỉnh và cạnh luân phiên.

### 4.3. Bước 3 — dựng phủ đỉnh

Sau khi queue cạn, đặt:

`C = (L \ Z_L) ∪ (R ∩ Z_R)`.

Vì `Z_R⊆R`, cách viết ngắn gọn là:

`coverLeft = {u∈L : u∉Z_L}`,

`coverRight = {v∈R : v∈Z_R}`.

**Quy tắc nhớ:**

- Bên **L**, chọn những đỉnh **KHÔNG được duyệt tới**.
- Bên **R**, chọn những đỉnh **ĐƯỢC duyệt tới**.

Không được lấy `(L∩Z_L)∪(R\Z_R)`; đó là phép chọn ngược, thường không phải vertex cover.

### 4.4. Pseudocode

```text
minimumVertexCoverAfterMaximumMatching(adj, pairL, pairR):
    ZL[0..nL-1] = false
    ZR[0..nR-1] = false
    queue = empty

    for u in L:
        if pairL[u] == -1:
            ZL[u] = true
            queue.push(u)

    while queue not empty:
        u = queue.pop()
        for v in adj[u]:
            if pairL[u] == v:
                continue                  // Không đi L->R qua cạnh ghép.
            if ZR[v]:
                continue
            ZR[v] = true

            x = pairR[v]
            if x == -1:
                error("Matching was not maximum")
            if not ZL[x]:
                ZL[x] = true
                queue.push(x)              // R->L qua cạnh ghép.

    coverLeft  = all u such that not ZL[u]
    coverRight = all v such that ZR[v]

    assert size(coverLeft) + size(coverRight) == |M|
    assert for every edge (u,v):
        u in coverLeft OR v in coverRight

    return coverLeft, coverRight
```

### 4.5. Chi phí chỉ riêng giai đoạn khôi phục

Mỗi đỉnh trái vào queue tối đa một lần, mỗi cạnh kề trái được quét tối đa một lần. Vì vậy:

- Thời gian: `O(|L|+|R|+|E|)`.
- Bộ nhớ phụ: `O(|L|+|R|)` cho visited, queue và danh sách đáp án (không tính input).

Nếu maximum matching đã có, **không cần chạy thêm thuật toán tối ưu**: chỉ duyệt một lần mạng cạnh luân phiên.

## 5. Chứng minh phủ đỉnh khôi phục được là hợp lệ

Đặt `Z_L,Z_R` là hai tập tới được sau BFS, và:

`C=(L\Z_L)∪Z_R`.

Xét **cạnh bất kỳ** `(u,v)∈E`.

### 5.1. Nếu u không ở Z_L

Khi `u∉Z_L`, chính u thuộc `L\Z_L`, nên `u∈C`. Cạnh đã được phủ.

### 5.2. Nếu u ở Z_L và cạnh không thuộc M

Thuật toán xét cạnh **chưa ghép** từ mọi u∈Z_L, nên v được đưa vào `Z_R`. Vì `v∈Z_R⊆C`, cạnh được phủ.

### 5.3. Nếu u ở Z_L và cạnh thuộc M

Đỉnh u **đã được ghép**, nên không thể là một đỉnh gốc tự do của BFS. Do đó u chỉ được đưa vào Z_L khi đi **từ đỉnh R_v đang ghép với u** qua cạnh ghép `(v,u)`. Suy ra `v∈Z_R⊆C`.

Vậy mọi cạnh E đều có ít nhất một đầu trong C: **C là một vertex cover hợp lệ**.

### 5.4. Vì sao C không có đỉnh “thừa” so với matching?

Khi matching M đã maximum, BFS không gặp R tự do; nếu gặp sẽ có đường tăng, mâu thuẫn. Vì thế **mọi v∈Z_R đều đã được ghép**.

Mặt khác **mọi đỉnh L chưa ghép nằm trong Z_L ngay từ đầu**, nên những đỉnh trái được chọn vào `L\Z_L` cũng **đã được ghép**.

Với mỗi cạnh ghép `(u,v)∈M`:

- Nếu `u∈Z_L` thì `v∈Z_R`: chọn **v**, không chọn u.
- Nếu `u∉Z_L` thì `v∉Z_R`: vì nếu v được duyệt tới, cạnh ghép ngược v→u sẽ đưa u vào Z_L. Do đó chọn **u**, không chọn v.

**Mỗi cạnh ghép đóng góp đúng một đỉnh vào C**, không trùng nhau vì các cạnh trong matching không chung đầu. Và mọi đỉnh được chọn đều thuộc một cạnh ghép.

Suy ra:

`|C| = |M|`.

Vì |M| là cận dưới của mọi cover (phần 2.1), C vừa là cover **hợp lệ** vừa đạt cận dưới, nên **C nhỏ nhất**.

### 5.5. Định lý Kőnig được chứng minh

Từ `|M|≤τ(G)` và cover xây được `|C|=|M|`, suy ra:

`τ(G)=ν(G)`.

Đây là chứng minh **mang tính thuật toán**: không chỉ biết hai giá trị bằng nhau, ta còn lấy được **danh sách đỉnh tối ưu**.

## 6. Ví dụ xuyên suốt: phủ đỉnh chứa cả đỉnh L và R

Xét đồ thị có 7 đỉnh trái `L0..L6` và 6 đỉnh phải `R0..R5`. Danh sách kề:

| Đỉnh trái | Các đỉnh phải kề |
|---|---|
| L0 | R0, R1 |
| L1 | R0 |
| L2 | R1 |
| L3 | R2 |
| L4 | R2, R3 |
| L5 | R3, R4 |
| L6 | *(không có)* |

R5 cũng là đỉnh cô lập (không cạnh nối). Input có **tổng 8 cạnh**.

### 6.1. Một maximum matching

Có thể chọn các cặp:

```text
L0 - R0
L2 - R1
L3 - R2
L4 - R3
L5 - R4
```

Số cạnh ghép = **5**. L1 và L6 chưa ghép; R5 cũng chưa ghép.

Đây là maximum matching vì chỉ có **5 đỉnh R có cạnh**, nên không matching nào có thể có nhiều hơn 5 cạnh. Ngoài ra phần phủ đỉnh dưới đây có size 5, tạo chứng nhận tối ưu kép.

### 6.2. Khởi tạo tìm kiếm luân phiên

Các đỉnh L chưa ghép:

`L1`, `L6`.

Bắt đầu:

`Z_L={L1,L6}`, `Z_R=∅`.

L6 cô lập, không mở rộng thêm. L1 có cạnh chưa ghép L1—R0, nên đưa R0 vào Z_R. R0 đang ghép L0, nên theo cạnh ghép ngược về L0, đưa L0 vào Z_L.

Tiếp tục từ L0: cạnh L0—R1 **không thuộc matching**, nên đưa R1 vào Z_R. R1 đang ghép L2, nên đưa L2 vào Z_L. L2 chỉ có cạnh ghép tới R1, không còn cạnh chưa ghép để mở rộng.

Kết quả:

`Z_L={L0,L1,L2,L6}`.

`Z_R={R0,R1}`.

### 6.3. Xây min vertex cover

Theo công thức:

`coverLeft=L\Z_L={L3,L4,L5}`.

`coverRight=Z_R={R0,R1}`.

Vậy:

`C={L3,L4,L5,R0,R1}` và `|C|=5`.

Kiểm từng cạnh:

- L0—R0 và L0—R1 được phủ bởi R0 hoặc R1.
- L1—R0 được phủ bởi R0.
- L2—R1 được phủ bởi R1.
- L3—R2 được phủ bởi L3.
- L4—R2 và L4—R3 được phủ bởi L4.
- L5—R3 và L5—R4 được phủ bởi L5.

Không còn cạnh chưa phủ. Vì maximum matching cũng có 5 cạnh không chung đầu, không thể có cover size <5. Kết luận: **C là phủ đỉnh nhỏ nhất**.

### 6.4. Matching và vertex cover không nhất thiết duy nhất

Có thể đổi phần ghép của ba đỉnh đầu thành:

`(L1,R0), (L0,R1)`

và để L2 chưa ghép; matching vẫn size 5, nên maximum matching **không duy nhất**.

Phủ đỉnh tối thiểu cũng có thể không duy nhất. Với đồ thị trên, có **4 minimum vertex covers** khác nhau (mỗi phủ đều có size 5):

```text
1. Left=[3, 4, 5], Right=[0, 1]
2. Left=[4, 5],    Right=[0, 1, 2]
3. Left=[5],       Right=[0, 1, 2, 3]
4. Left=[],        Right=[0, 1, 2, 3, 4]
```

Thuật toán đường luân phiên trả **một** phủ tối ưu, không hứa liệt kê mọi phủ tối ưu.

### 6.5. Đỉnh cô lập được xử lý thế nào?

L6 cô lập và chưa ghép, nên nó **thuộc Z_L** nhưng **không** được chọn vào coverLeft.

R5 cô lập, không reachable từ L chưa ghép nên **không thuộc Z_R** và không chọn vào coverRight.

Đúng trực giác: đỉnh cô lập không phủ thêm cạnh nào, nên không có lý do đưa nó vào **minimum vertex cover** khi mỗi đỉnh có chi phí đơn vị dương.

## 7. Cài đặt Java 17 — Hopcroft–Karp + dựng min vertex cover

**Hopcroft–Karp** tìm maximum matching của đồ thị hai phía bằng cách:

1. BFS phân lớp từ tất cả L chưa ghép và xác định độ dài ngắn nhất của các đường tăng.
2. DFS tìm **nhiều đường tăng ngắn nhất** trong một pha và cập nhật matching.
3. Lặp tới khi không còn đường tăng.

Sau đó chạy **một BFS đường luân phiên khác** để khôi phục C theo định lý Kőnig.

### 7.1. Chương trình độc lập

Lưu thành **BipartiteMinVertexCoverHopcroftKarpDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class BipartiteMinVertexCoverHopcroftKarpDemo {
    record Result(int matchingSize, int phases,
                  int[] pairLeft, int[] pairRight,
                  List<Integer> zLeft, List<Integer> zRight,
                  List<Integer> coverLeft, List<Integer> coverRight) {
        int coverSize() {
            return coverLeft.size() + coverRight.size();
        }
    }

    static final class Solver {
        final int nLeft, nRight;
        final int[][] adj;
        final int[] pairL, pairR, dist;

        Solver(int nLeft, int nRight, int[][] adj) {
            if (nLeft < 0 || nRight < 0 || adj.length != nLeft) {
                throw new IllegalArgumentException("Invalid sizes");
            }
            this.nLeft = nLeft;
            this.nRight = nRight;
            this.adj = adj;
            for (int[] row : adj) {
                for (int v : row) {
                    if (v < 0 || v >= nRight) {
                        throw new IllegalArgumentException("Bad right index");
                    }
                }
            }
            pairL = new int[nLeft];
            pairR = new int[nRight];
            dist = new int[nLeft];
            Arrays.fill(pairL, -1);
            Arrays.fill(pairR, -1);
        }

        // Khoảng cách ngắn nhất từ một L tự do tới một R tự do
        // tính theo số lần đi từ L sang R trong đường tăng.
        int bfsLayer() {
            Arrays.fill(dist, -1);
            ArrayDeque<Integer> q = new ArrayDeque<>();
            for (int u = 0; u < nLeft; u++) {
                if (pairL[u] == -1) {
                    dist[u] = 0;
                    q.addLast(u);
                }
            }

            int shortest = Integer.MAX_VALUE;
            while (!q.isEmpty()) {
                int u = q.removeFirst();
                if (dist[u] >= shortest) {
                    continue;
                }

                for (int v : adj[u]) {
                    int mate = pairR[v];
                    if (mate == -1) {
                        shortest = Math.min(shortest, dist[u] + 1);
                    } else if (dist[mate] == -1) {
                        dist[mate] = dist[u] + 1;
                        q.addLast(mate);
                    }
                }
            }
            return shortest;
        }

        boolean dfsAugment(int u, int shortest) {
            for (int v : adj[u]) {
                int mate = pairR[v];
                boolean usable;

                if (mate == -1) {
                    usable = dist[u] + 1 == shortest;
                } else {
                    usable = dist[mate] == dist[u] + 1
                            && dfsAugment(mate, shortest);
                }

                if (usable) {
                    pairL[u] = v;
                    pairR[v] = u;
                    return true;
                }
            }

            dist[u] = -1; // Không còn đường tăng ngắn nhất từ u.
            return false;
        }

        Result solve() {
            int matchingSize = 0;
            int phases = 0;

            while (true) {
                int shortest = bfsLayer();
                if (shortest == Integer.MAX_VALUE) {
                    break;
                }

                phases++;
                for (int u = 0; u < nLeft; u++) {
                    if (pairL[u] == -1 && dfsAugment(u, shortest)) {
                        matchingSize++;
                    }
                }
            }

            // Duyệt alternating reachability từ TOÀN BỘ L chưa ghép.
            boolean[] zL = new boolean[nLeft];
            boolean[] zR = new boolean[nRight];
            ArrayDeque<Integer> q = new ArrayDeque<>();

            for (int u = 0; u < nLeft; u++) {
                if (pairL[u] == -1) {
                    zL[u] = true;
                    q.addLast(u);
                }
            }

            while (!q.isEmpty()) {
                int u = q.removeFirst();

                for (int v : adj[u]) {
                    if (pairL[u] == v || zR[v]) {
                        continue; // Chỉ đi L->R qua cạnh chưa ghép.
                    }

                    zR[v] = true;
                    int mate = pairR[v];

                    if (mate == -1) {
                        throw new IllegalStateException(
                                "Reachable free R: not maximum");
                    }
                    if (!zL[mate]) {
                        zL[mate] = true;
                        q.addLast(mate);
                    }
                }
            }

            List<Integer> reachedL = new ArrayList<>();
            List<Integer> reachedR = new ArrayList<>();
            List<Integer> coverL = new ArrayList<>();
            List<Integer> coverR = new ArrayList<>();

            for (int u = 0; u < nLeft; u++) {
                if (zL[u]) reachedL.add(u);
                else coverL.add(u);
            }
            for (int v = 0; v < nRight; v++) {
                if (zR[v]) {
                    reachedR.add(v);
                    coverR.add(v);
                }
            }

            if (coverL.size() + coverR.size() != matchingSize) {
                throw new IllegalStateException("Kőnig equality failed");
            }
            for (int u = 0; u < nLeft; u++) {
                for (int v : adj[u]) {
                    if (!coverL.contains(u) && !coverR.contains(v)) {
                        throw new IllegalStateException("Uncovered edge");
                    }
                }
            }

            return new Result(matchingSize, phases,
                    pairL.clone(), pairR.clone(),
                    List.copyOf(reachedL), List.copyOf(reachedR),
                    List.copyOf(coverL), List.copyOf(coverR));
        }
    }

    public static void main(String[] args) {
        int[][] graph = {
            {0, 1}, {0}, {1}, {2}, {2, 3}, {3, 4}, {}
        };
        Result r = new Solver(7, 6, graph).solve();

        System.out.println("Max matching size: " + r.matchingSize());
        System.out.println("Pair left: "
                + Arrays.toString(r.pairLeft()));
        System.out.println("Pair right: "
                + Arrays.toString(r.pairRight()));
        System.out.println("HK BFS phases: " + r.phases());
        System.out.println("Z_L: " + r.zLeft());
        System.out.println("Z_R: " + r.zRight());
        System.out.println("Min cover left: " + r.coverLeft());
        System.out.println("Min cover right: " + r.coverRight());
        System.out.println("Min cover size: " + r.coverSize());

        Result perfect = new Solver(
                2, 2, new int[][]{{0, 1}, {0}}).solve();
        System.out.println("Perfect-left matching: "
                + perfect.matchingSize() + ", cover size: "
                + perfect.coverSize() + ", phases: "
                + perfect.phases());

        Result empty = new Solver(
                2, 3, new int[][]{{}, {}}).solve();
        System.out.println("No-edge matching: "
                + empty.matchingSize() + ", cover size: "
                + empty.coverSize());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BipartiteMinVertexCoverHopcroftKarpDemo.java
java BipartiteMinVertexCoverHopcroftKarpDemo
```

Stdout:

```text
Max matching size: 5
Pair left: [0, -1, 1, 2, 3, 4, -1]
Pair right: [0, 2, 3, 4, 5, -1]
HK BFS phases: 1
Z_L: [0, 1, 2, 6]
Z_R: [0, 1]
Min cover left: [3, 4, 5]
Min cover right: [0, 1]
Min cover size: 5
Perfect-left matching: 2, cover size: 2, phases: 2
No-edge matching: 0, cover size: 0
```

### 7.2. Tại sao BFS phân lớp của Hopcroft–Karp khác BFS khôi phục cover?

**BFS phân lớp** trong `bfsLayer` được chạy trong **quá trình tối đa hóa matching** và tìm độ dài ngắn nhất của các **đường tăng còn tồn tại**. `dfsAugment` cập nhật matching bằng cách đi theo những lớp phù hợp.

**BFS khôi phục cover** chỉ chạy **sau khi không còn đường tăng**. Nó duyệt tất cả những đỉnh có thể tới từ các L tự do qua cạnh luân phiên, không cần tìm đích R tự do vì theo giả thiết maximum, không còn đỉnh R tự do reachable.

Hai lần BFS có mục tiêu khác nhau; không tự dùng mảng `dist` của lần tối đa hóa để suy ra `Z_L/Z_R` nếu chưa chứng minh nó lưu đúng tập reachability.

### 7.3. Vì sao `pairL` và `pairR` phải đối xứng?

Nếu `pairL[u]=v`, thì `pairR[v]` phải bằng u, và ngược lại. Khi DFS tái ghép một nhánh, cập nhật **cả hai** mảng tương ứng. Không được chỉ đổi một chiều: thuật toán dựng cover cần biết ai đang ghép với v để theo cạnh R→L.

### 7.4. Vì sao `shortest` cần thiết?

Nếu BFS chỉ biết “có một đường tăng ở đâu đó” mà DFS tự do tìm các đường tùy ý, code có thể vẫn tìm matching nhưng không còn đúng kỹ thuật phân pha của Hopcroft–Karp. `shortest` giới hạn các đường DFS ở **độ dài tăng ngắn nhất**, giúp thuật toán đạt độ phức tạp đặc trưng.

### 7.5. Kiểm kết quả trả về

Code tự xác nhận:

1. `|coverLeft|+|coverRight| == matchingSize`.
2. Mọi cạnh đầu vào có một đầu nằm trong cover tương ứng.
3. Không còn R tự do reachable từ L tự do trong BFS alternating.

Nhờ đó, nếu cài sai một trong hai giai đoạn, bài không âm thầm in danh sách “có vẻ hợp lý” mà sai.

### 7.6. Độ phức tạp Hopcroft–Karp

Đặt `V=nL+nR`, `E=|E|`.

- Hopcroft–Karp: `O(E sqrt(V))` với cách đánh giá chuẩn (cộng chi phí khởi tạo `O(V+E)`).
- BFS reconstruct: `O(V+E)`.
- Tổng: `O(V+E sqrt(V))` với V≥1, E≥1.
- Bộ nhớ: `O(V+E)` cho adjacency, cặp ghép, level, queue, reachability và kết quả.

Trong code mẫu, phép kiểm cuối dùng `List.contains` trên danh sách cover, có thể làm bước **kiểm định bổ sung** chậm hơn `O(V+E)` ở các đầu vào lớn. Khi dùng thực tế, hãy kiểm bằng `boolean[] inCoverL/inCoverR` để giữ bước kiểm định cũng `O(V+E)`; hoặc bỏ kiểm định khỏi vòng hiệu năng. Điều này **không** thay đổi độ phức tạp lõi của thuật toán Hopcroft–Karp.

## 8. Cài đặt Java 17 — Kuhn DFS đơn giản để đối chiếu

Với input không quá lớn, thuật toán **Kuhn** dùng DFS tìm đường tăng từ từng đỉnh L là lựa chọn dễ viết:

1. Ban đầu mọi R đều chưa ghép.
2. Với mỗi L_u, chạy DFS qua các R kề, sử dụng mảng `seenRight` **mới cho mỗi lần tìm**.
3. Nếu R_v tự do, ghép u-v. Nếu R_v đã ghép L_x, thử **đẩy x sang một R khác** bằng đệ quy.
4. Nếu thành công, cập nhật `pairR[v]=u`.
5. Sau khi duyệt hết L, xây `pairL` từ `pairR`.

Kuhn vẫn tìm **maximum matching**, dù thường chậm hơn Hopcroft–Karp trên đồ thị lớn.

### 8.1. Chương trình độc lập

Lưu thành **KuhnMatchingVertexCoverDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class KuhnMatchingVertexCoverDemo {
    record Result(int matchingSize, int[] pairLeft,
                  List<Integer> zLeft, List<Integer> zRight,
                  List<Integer> coverLeft, List<Integer> coverRight) {}

    static boolean augment(int u, int[][] adj,
                           int[] pairRight, boolean[] seenRight) {
        for (int v : adj[u]) {
            if (seenRight[v]) continue;
            seenRight[v] = true;

            if (pairRight[v] == -1
                    || augment(pairRight[v], adj, pairRight, seenRight)) {
                pairRight[v] = u;
                return true;
            }
        }
        return false;
    }

    static Result solve(int nLeft, int nRight, int[][] adj) {
        if (nLeft < 0 || nRight < 0 || adj.length != nLeft) {
            throw new IllegalArgumentException("Invalid sizes");
        }
        for (int[] row : adj) {
            for (int v : row) {
                if (v < 0 || v >= nRight) {
                    throw new IllegalArgumentException("Bad right ID");
                }
            }
        }

        int[] pairRight = new int[nRight];
        Arrays.fill(pairRight, -1);
        int size = 0;

        for (int u = 0; u < nLeft; u++) {
            if (augment(u, adj, pairRight, new boolean[nRight])) {
                size++;
            }
        }

        int[] pairLeft = new int[nLeft];
        Arrays.fill(pairLeft, -1);
        for (int v = 0; v < nRight; v++) {
            if (pairRight[v] != -1) {
                pairLeft[pairRight[v]] = v;
            }
        }

        boolean[] zL = new boolean[nLeft];
        boolean[] zR = new boolean[nRight];
        ArrayDeque<Integer> queue = new ArrayDeque<>();

        for (int u = 0; u < nLeft; u++) {
            if (pairLeft[u] == -1) {
                zL[u] = true;
                queue.addLast(u);
            }
        }

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (int v : adj[u]) {
                if (pairLeft[u] == v || zR[v]) continue;

                zR[v] = true;
                int mate = pairRight[v];
                if (mate == -1) {
                    throw new IllegalStateException(
                            "A free right vertex is reachable");
                }
                if (!zL[mate]) {
                    zL[mate] = true;
                    queue.addLast(mate);
                }
            }
        }

        List<Integer> reachL = new ArrayList<>();
        List<Integer> reachR = new ArrayList<>();
        List<Integer> coverL = new ArrayList<>();
        List<Integer> coverR = new ArrayList<>();

        for (int u = 0; u < nLeft; u++) {
            if (zL[u]) reachL.add(u);
            else coverL.add(u);
        }
        for (int v = 0; v < nRight; v++) {
            if (zR[v]) {
                reachR.add(v);
                coverR.add(v);
            }
        }

        if (coverL.size() + coverR.size() != size) {
            throw new IllegalStateException("Kőnig check failed");
        }

        return new Result(size, pairLeft, List.copyOf(reachL),
                List.copyOf(reachR), List.copyOf(coverL),
                List.copyOf(coverR));
    }

    public static void main(String[] args) {
        int[][] graph = {
            {0, 1}, {0}, {1}, {2}, {2, 3}, {3, 4}, {}
        };
        Result r = solve(7, 6, graph);

        System.out.println("Kuhn matching size: " + r.matchingSize());
        System.out.println("Kuhn pair left: "
                + Arrays.toString(r.pairLeft()));
        System.out.println("Kuhn Z_L: " + r.zLeft());
        System.out.println("Kuhn Z_R: " + r.zRight());
        System.out.println("Kuhn cover left: " + r.coverLeft());
        System.out.println("Kuhn cover right: " + r.coverRight());
        System.out.println("Kuhn cover size: "
                + (r.coverLeft().size() + r.coverRight().size()));

        Result moved = solve(2, 2,
                new int[][]{{0, 1}, {0}});
        System.out.println("Reassigned pair left: "
                + Arrays.toString(moved.pairLeft()));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 KuhnMatchingVertexCoverDemo.java
java KuhnMatchingVertexCoverDemo
```

Stdout:

```text
Kuhn matching size: 5
Kuhn pair left: [1, 0, -1, 2, 3, 4, -1]
Kuhn Z_L: [0, 1, 2, 6]
Kuhn Z_R: [0, 1]
Kuhn cover left: [3, 4, 5]
Kuhn cover right: [0, 1]
Kuhn cover size: 5
Reassigned pair left: [1, 0]
```

### 8.2. Tại sao hai thuật toán có thể trả matching khác nhau?

Hopcroft–Karp theo BFS ngắn nhất và Kuhn DFS theo thứ tự đỉnh/cạnh có thể tìm **hai maximum matchings khác tập cạnh**. Trong ví dụ, Hopcroft–Karp để L1 tự do, còn Kuhn để L2 tự do.

Nhưng cả hai có kích thước **5** và khôi phục được một minimum vertex cover kích thước **5**. Không so sánh hai mảng `pairLeft` theo từng phần tử rồi kết luận thuật toán sai; phải kiểm **tính hợp lệ, kích thước tối đa và cover hợp lệ**.

### 8.3. Độ phức tạp Kuhn

Nếu mỗi lần augment có thể duyệt nhiều cạnh và ta thử cho nL đỉnh trái, độ phức tạp worst-case thường viết:

`O(nL · E)` (cộng chi phí khởi tạo/đánh dấu visited).

Bộ nhớ `O(V+E)`. Đệ quy có thể sâu trên đồ thị lớn; nếu lo stack overflow, dùng DFS tường minh hoặc Hopcroft–Karp phù hợp.

**Không** quên cấp mảng `seenRight` mới cho mỗi lần thử từ một đỉnh trái; giữ một visited vĩnh viễn từ lần thử trước sẽ chặn những đường tăng hợp lệ về sau.

## 9. Oracle độc lập: vét cạn tất cả tập đỉnh khi V nhỏ

Để kiểm chứng rằng cover khôi phục thực sự nhỏ nhất, có thể dùng phương pháp **không phụ thuộc matching**:

1. Gộp các đỉnh thành dãy `[L0..L(nL−1), R0..R(nR−1)]`.
2. Duyệt mọi bitmask biểu thị một tập đỉnh C.
3. Kiểm với mọi cạnh `(u,v)`: bit của L_u hoặc bit của R_v phải bằng 1.
4. Giữ kích thước nhỏ nhất và đếm các bitmask đạt kích thước ấy.

Với `nL+nR` nhỏ, đây là một **oracle độc lập**, dùng kiểm thử Hopcroft–Karp, Kuhn và công thức König.

Có `2^(nL+nR)` tập cần xét, nên không dùng brute force cho dữ liệu lớn.

### 9.1. Java 17 — đếm và in mọi minimum vertex cover nhỏ

Lưu thành **BipartiteMinVertexCoverBruteOracleDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;

public class BipartiteMinVertexCoverBruteOracleDemo {
    record Cover(List<Integer> left, List<Integer> right) {}
    record Answer(int minimum, List<Cover> optimalCovers) {}

    static Answer enumerate(int nLeft, int nRight, int[][] adj) {
        int n = nLeft + nRight;
        if (nLeft < 0 || nRight < 0
                || n > 16 || adj.length != nLeft) {
            throw new IllegalArgumentException(
                    "Brute force: nLeft+nRight<=16");
        }

        for (int[] row : adj) {
            for (int v : row) {
                if (v < 0 || v >= nRight) {
                    throw new IllegalArgumentException("Bad right ID");
                }
            }
        }

        int best = Integer.MAX_VALUE;
        List<Cover> optimal = new ArrayList<>();

        for (int mask = 0; mask < (1 << n); mask++) {
            int count = Integer.bitCount(mask);
            if (count > best) continue;

            boolean valid = true;
            for (int u = 0; u < nLeft && valid; u++) {
                for (int v : adj[u]) {
                    boolean takeL = (mask & (1 << u)) != 0;
                    boolean takeR = (mask & (1 << (nLeft + v))) != 0;
                    if (!takeL && !takeR) {
                        valid = false;
                        break;
                    }
                }
            }
            if (!valid) continue;

            List<Integer> left = new ArrayList<>();
            List<Integer> right = new ArrayList<>();
            for (int u = 0; u < nLeft; u++) {
                if ((mask & (1 << u)) != 0) left.add(u);
            }
            for (int v = 0; v < nRight; v++) {
                if ((mask & (1 << (nLeft + v))) != 0) right.add(v);
            }

            if (count < best) {
                best = count;
                optimal.clear();
            }
            optimal.add(new Cover(
                    List.copyOf(left), List.copyOf(right)));
        }

        return new Answer(best, List.copyOf(optimal));
    }

    public static void main(String[] args) {
        int[][] sample = {
            {0, 1}, {0}, {1}, {2}, {2, 3}, {3, 4}, {}
        };
        Answer a = enumerate(7, 6, sample);

        System.out.println("Brute minimum size: " + a.minimum());
        System.out.println("Brute optimal count: "
                + a.optimalCovers().size());
        for (Cover c : a.optimalCovers()) {
            System.out.println("Cover L=" + c.left()
                    + " R=" + c.right());
        }

        Answer empty = enumerate(2, 3,
                new int[][]{{}, {}});
        System.out.println("No-edge optimum: " + empty.minimum());

        Answer triangleLikeBipartite = enumerate(2, 2,
                new int[][]{{0, 1}, {0}});
        System.out.println("Reassignment graph optimum: "
                + triangleLikeBipartite.minimum());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BipartiteMinVertexCoverBruteOracleDemo.java
java BipartiteMinVertexCoverBruteOracleDemo
```

Stdout:

```text
Brute minimum size: 5
Brute optimal count: 4
Cover L=[3, 4, 5] R=[0, 1]
Cover L=[4, 5] R=[0, 1, 2]
Cover L=[5] R=[0, 1, 2, 3]
Cover L=[] R=[0, 1, 2, 3, 4]
No-edge optimum: 0
Reassignment graph optimum: 2
```

### 9.2. Vì sao bốn phủ tối ưu đều có size 5?

Thành phần `{L0,L1,L2,R0,R1}` yêu cầu tối thiểu **hai** đỉnh cover, và lựa chọn size2 duy nhất là `{R0,R1}`.

Thành phần `{L3,L4,L5,R2,R3,R4}` là một đồ thị dạng đường, yêu cầu tối thiểu **ba** đỉnh cover. Có bốn cách chọn ba đỉnh tương ứng với bốn dòng in. Hai đỉnh cô lập L6 và R5 không được chọn trong nghiệm tối ưu.

Nhân số lựa chọn giữa các thành phần độc lập sẽ cho số nghiệm tối ưu tổng thể: `1×4=4`.

### 9.3. Độ phức tạp và giới hạn

- Mỗi bitmask phải kiểm nhiều nhất E cạnh, có `2^V` bitmask.
- Thời gian: `O(2^V (V+E))` nếu kể tạo danh sách nghiệm.
- Bộ nhớ: phụ thuộc số nghiệm được lưu, có thể tới `O(numberOfOptimalCovers·V)`.
- Đặt `V<=16` để demo kiểm thử được; **không** được coi đây là thuật toán giải tổng quát hiệu quả.

Brute force không sử dụng matching, nên việc nó trả cùng size 5 tạo kiểm chứng độc lập cho thuật toán chính.

## 10. Kiểm tra một matching và một cover đã trả

Không nên chỉ so `coverSize==matchingSize` mà bỏ kiểm các điều kiện nền tảng.

### 10.1. Kiểm matching

Với `pairL`, `pairR`:

- Nếu `pairL[u]=v>=0`, thì `(u,v)` phải là **cạnh có thật** trong input.
- `pairR[v]` phải bằng u và ngược lại.
- Không có hai đỉnh L cùng ghép một R hoặc ngược lại.
- `matchingSize` bằng số u có `pairL[u]!=-1`, đồng thời bằng số v có `pairR[v]!=-1`.
- Nếu cần chứng minh maximum, không còn đường tăng (hoặc có cover hợp lệ cùng size làm chứng chỉ theo Kőnig).

### 10.2. Kiểm cover

Dùng boolean `inCoverL[u]` và `inCoverR[v]`, rồi:

```text
for every edge (u,v) in E:
    assert inCoverL[u] || inCoverR[v]
```

Đây là điều kiện **đúng định nghĩa**. Nếu một cạnh có cả hai đầu không được chọn, danh sách đó **không phải** vertex cover, dù kích thước tình cờ bằng số cạnh matching.

### 10.3. Chứng chỉ tối ưu kép

Nếu đã xác nhận:

1. M là một matching **hợp lệ** có k cạnh.
2. C là một vertex cover **hợp lệ** có k đỉnh.

Thì không cần tin M được tính bởi thuật toán nào: vì mọi cover có size≥k, mọi matching có size≤k, nên cả M và C **đều tối ưu**.

Điều này tạo ra chứng chỉ dễ kiểm toán trong hệ thống phân công thực tế.

### 10.4. Duyệt alternating không phải kết quả BFS thường

BFS trên **toàn bộ cạnh của graph vô hướng** từ L chưa ghép sẽ lan sang quá nhiều đỉnh và không lưu chiều “cạnh ghép / cạnh chưa ghép”. Quy tắc đúng là **cạnh chưa ghép L→R, cạnh ghép R→L**. Nếu quên định hướng alternating, công thức khôi phục C có thể sai.

## 11. Mối liên hệ với bài toán independent set

Một **tập độc lập** (*independent set*) I là tập đỉnh **không có cạnh nào nối giữa hai đỉnh thuộc I**.

C và `V\C` có quan hệ:

- C là vertex cover **khi và chỉ khi** `V\C` là independent set.
- Vậy bổ sung của **minimum vertex cover** là **maximum independent set**.

Do đó trên mọi đồ thị:

`α(G) + τ(G) = |V|`,

với α là kích thước independent set lớn nhất.

Kết hợp với định lý Kőnig trên đồ thị hai phía:

`α(G) = |L| + |R| − ν(G)`.

Ví dụ phần 6 có `|L|+|R|=13`, matching size5. Vì thế maximum independent set có size:

`13−5=8`.

Một tập độc lập lớn nhất có thể lấy trực tiếp là phần bù của cover đã dựng:

`I=Z_L ∪ (R\Z_R)`.

Với ví dụ:

`I={L0,L1,L2,L6,R2,R3,R4,R5}`,

có 8 đỉnh và không có cạnh nối giữa hai đỉnh trong I.

**Không nhầm:** independent set chọn các đỉnh **không kề nhau**, trong khi vertex cover chọn các đỉnh **phủ mọi cạnh**.

## 12. Mối liên hệ với định lý Hall và matching đầy đủ

Một **matching phủ hết phía trái** (*left-perfect matching*) là matching có `nL` cạnh; đòi `nL<=nR` và mọi đỉnh L đều được ghép.

**Định lý Hall:** đồ thị hai phía có matching phủ hết L khi và chỉ khi với mọi tập con `X⊆L`,

`|N(X)| ≥ |X|`,

trong đó `N(X)` là tập các đỉnh R kề với ít nhất một đỉnh thuộc X.

### 12.1. Nếu matching phủ hết L

Không có đỉnh L tự do để làm nguồn BFS alternating, nên:

`Z_L=∅`, `Z_R=∅`.

Công thức Kőnig trả:

`C=L`, size `nL=|M|`.

Đây là một vertex cover nhỏ nhất **hợp lệ** vì mọi cạnh của bipartite graph chạm phía L; không có nghĩa C=L là **nghiệm nhỏ nhất duy nhất**. Ví dụ perfect matching hai bên có thể có cover khác cùng size, như chọn toàn phía R.

### 12.2. Nếu matching không phủ hết L

Có ít nhất một đỉnh trái tự do; alternating search giúp tìm nhóm đỉnh có cạnh bị cạnh tranh, phản ánh sự thiếu chỗ ghép. Nếu matching đã maximum, không có đường tăng dẫn tới R tự do. Các đỉnh reachable và không reachable cho công thức cover tối ưu.

Định lý Hall thường dùng chứng minh tồn tại phân công cho mọi người; Kőnig cho số **đỉnh cần chọn ít nhất để giám sát/phủ mọi quan hệ**. Chúng liên hệ sâu sắc nhưng trả lời hai câu hỏi khác nhau.

## 13. Phủ đỉnh có trọng số: không dùng trực tiếp công thức số lượng

Trong bài hiện tại, mỗi đỉnh được chọn có **chi phí 1**. Khi mỗi đỉnh u có **trọng số/chi phí khác nhau** `w(u)≥0`, mục tiêu đổi thành:

`min Σ_(v∈C) w(v)`.

Đây là **minimum-weight vertex cover**, không phải chỉ cần số đỉnh ít nhất.

Ví dụ hình sao hai phía:

```text
L0 -- R0
L0 -- R1
L0 -- R2
```

Cho `cost(L0)=10`, còn `cost(R0)=cost(R1)=cost(R2)=1`.

- Phủ đỉnh ít đỉnh nhất: `{L0}`, size 1 nhưng cost 10.
- Phủ đỉnh có tổng cost nhỏ nhất: `{R0,R1,R2}`, size 3, cost **3**.

Vậy công thức từ maximum **cardinality** matching chỉ tối ưu **số đỉnh**, không tự động tối ưu tổng cost khi trọng số khác nhau.

### 13.1. Reduction weighted bipartite vertex cover → min s–t cut

Với chi phí đỉnh không âm, dựng mạng luồng:

1. Thêm super-source s và super-sink t.
2. Với mỗi đỉnh L_u, thêm cung `s→L_u` dung lượng `w(L_u)`.
3. Với mỗi cạnh hai phía `(L_u,R_v)`, thêm cung `L_u→R_v` dung lượng **INF**.
4. Với mỗi R_v, thêm cung `R_v→t` dung lượng `w(R_v)`.

Chọn INF **lớn hơn tổng trọng số tất cả đỉnh**, không dùng giá trị vô cực giả quá nhỏ hoặc cộng bị tràn.

Với một min-cut `(S,T)`, vì không thể tối ưu khi cắt cung INF:

- Những đỉnh L thuộc **T** được tính phí `w(L)` do cắt cung s→L.
- Những đỉnh R thuộc **S** được tính phí `w(R)` do cắt cung R→t.

Các cạnh L→R vô cùng lớn ép điều kiện: nếu L thuộc S mà R thuộc T, cut quá đắt. Vì vậy tập:

`C=(L∩T) ∪ (R∩S)`

là một weighted vertex cover tối ưu.

Đây là **liên hệ qua min-cut** cho weighted bipartite vertex cover, **khác** công thức dùng alternating BFS từ matching cực đại không trọng số. Nếu cho phép chi phí âm, cần xử lý lại mô hình; reduction trên giả sử **không âm**.

## 14. Đồ thị tổng quát: vì sao không áp Kőnig bừa?

Với đồ thị ba đỉnh tạo tam giác A—B, B—C, C—A:

- Maximum matching chỉ có thể chọn **một cạnh**, size1.
- Minimum vertex cover cần **hai đỉnh** để phủ cả ba cạnh, size2.

Do đó:

`ν=1 < τ=2`.

Với **đồ thị vô hướng tổng quát**, bài minimum vertex cover là một bài toán khó tính toán (NP-hard); không thể kỳ vọng luôn lấy MVC chỉ bằng một maximum matching như trên đồ thị hai phía.

Tuy nhiên, với một **maximal matching** trong đồ thị bất kỳ, chọn **cả hai đầu mút** của mọi cạnh ghép tạo một vertex cover có size ≤2 lần optimum. Đây là **xấp xỉ 2**, không phải nghiệm tối ưu chính xác và không phải công thức Kőnig.

### 14.1. Cách nhận ra đầu vào có thực sự hai phía

Nếu input chưa cho hai nhóm L/R, có thể chạy BFS/DFS **tô hai màu**:

- Chọn màu 0 cho một đỉnh chưa thăm.
- Mỗi cạnh (u,v) yêu cầu màu(u) khác màu(v).
- Nếu phát hiện một cạnh nối hai đỉnh cùng màu ⇒ đồ thị **không hai phía**.

Graph có nhiều thành phần vẫn tô tiếp từ mọi đỉnh chưa thăm. Self-loop luôn làm graph **không hai phía** theo định nghĩa; cạnh song song giữa hai phía không cản trở tô màu.

Sau khi tách được L/R, ánh xạ ID gốc vào `0..nL−1` và `0..nR−1` để chạy matching.

### 14.2. Đồ thị hai phía không nhất thiết liên thông

Kőnig vẫn đúng với nhiều thành phần và cả đỉnh cô lập. Không cần biến thành graph liên thông. Matching cực đại của toàn graph là hợp matching cực đại từng thành phần; minimum cover toàn graph là hợp minimum cover từng thành phần.

## 15. Những trường hợp biên quan trọng

| Trường hợp | Hành vi đúng |
|---|---|
| Không có cạnh | Matching size0; cover tối ưu **rỗng** |
| Không có đỉnh L | Không có cạnh; cover rỗng |
| Không có đỉnh R | Không có cạnh; cover rỗng |
| Một cạnh L0—R0 | Matching1; cover có thể chọn L0 hoặc R0 |
| Đỉnh L cô lập | Là nguồn BFS nếu tự do; không được chọn vào cover |
| Đỉnh R cô lập | Không xuất hiện trong Z_R; không được chọn vào cover |
| Matching phủ hết L | Z_L=Z_R=∅; cover trả toàn L |
| Matching chưa maximum | Có thể gặp R tự do reachable; không công bố C tối ưu |
| Nhiều matching maximum | Pair arrays khác nhưng size giống; cover có thể giống hoặc khác |
| Nhiều MVC | Thuật toán trả **một** nghiệm tối ưu, không liệt kê tất cả |
| Cạnh trùng/parallel L–R | Không thay đổi định nghĩa cover; có thể cần deduplicate để tăng tốc |
| Chỉ số L0 và R0 | Hai đỉnh khác nhau dù cùng số 0 |
| Một đỉnh nối mọi R | Có thể cover bằng một đỉnh L |
| `nL>nR` | Matching size ≤nR; vẫn tìm cover được |
| `nR>nL` | Matching size ≤nL; vẫn tìm cover được |
| Có cạnh trong cùng phía | Input **không đúng mô hình bipartite** |
| Có trọng số đỉnh | Phải giải minimum-weight cover, không dùng cardinality cover nguyên xi |
| Cần tất cả MVC | Bài nâng cao, không thể chỉ in một Z từ một matching |
| Nhiều thành phần | Không ảnh hưởng tính đúng, phải khởi tạo mọi đỉnh tự do L |

### 15.1. Cạnh song song ảnh hưởng kết quả ra sao?

Nếu có nhiều cạnh **cùng cặp L_u—R_v**, một vertex cover phủ chúng bằng cách chọn u hoặc v — vẫn như một cạnh đơn. Các bản sao không thể tăng matching size vì chúng dùng chung hai đầu.

Có thể **khử trùng adjacency** cho bài matching/cardinality cover để giảm thời gian, miễn giữ mô hình số đỉnh đúng. Nếu đề đòi đếm **matching phân biệt ID cạnh**, các bản sao có thể làm thay đổi số nghiệm; không khử trùng trong bài đếm đó nếu ID có ý nghĩa.

### 15.2. Trường hợp `nL=0` hoặc `nR=0`

Matching size0; mọi cạnh vắng mặt nếu input hợp lệ; minimum cover rỗng. Với code, mảng adjacency phải có đúng nL dòng; mỗi ID v được kiểm `[0,nR)`.

Nếu `nR=0` nhưng adjacency có một v, đó là input sai chỉ số; phải **báo lỗi**, không im lặng bỏ.

## 16. Các lỗi triển khai thường gặp

### Lỗi 1 — Nhầm maximum với maximal matching

Chọn cạnh greedily không thể thêm nữa chỉ đảm bảo *maximal*, có thể chưa maximum. Công thức phủ đỉnh cần **maximum matching**. Hãy chạy Kuhn/Hopcroft–Karp đến khi không còn đường tăng.

### Lỗi 2 — Bắt đầu BFS từ R tự do

Công thức `(L\Z_L) ∪ Z_R` được xây bằng BFS **từ L tự do**. Nếu bắt đầu từ R tự do, phải đổi đối xứng công thức và hướng luân phiên; không thể dùng nguyên công thức trên.

### Lỗi 3 — Chỉ bắt đầu từ một đỉnh trái tự do

Nhiều vùng luân phiên không nối nhau có thể bị bỏ sót. Hãy enqueue **tất cả** L chưa ghép trước khi BFS.

### Lỗi 4 — Đi L→R qua cả cạnh đang ghép

Hướng chuẩn của alternating search là **cạnh chưa ghép L→R, cạnh ghép R→L**. Bỏ ràng buộc dễ khiến bạn duyệt sai trạng thái và suy diễn Z sai.

### Lỗi 5 — Đi R→L qua mọi cạnh

Ở R, chỉ được theo **cạnh thuộc matching** về đỉnh L đang ghép với R. Đi theo cạnh chưa ghép ngược về L làm mất cấu trúc luân phiên.

### Lỗi 6 — Lấy `(Z_L)∪(R\Z_R)` làm phủ

Đó là phép chọn ngược với công thức Kőnig đang dùng. Đúng là **`(L\Z_L)∪Z_R`**.

### Lỗi 7 — Chọn tất cả đỉnh đã BFS tới

Chọn `Z_L ∪ Z_R` thường thừa hoặc không phủ hết; bên L phải lấy **phần bù** reachability.

### Lỗi 8 — Nhầm số lượng với danh sách đỉnh

Đề hỏi **tập phủ**, không chỉ hỏi size. In mỗi `matchingSize` là thiếu đầu ra. Phải in `coverLeft` và `coverRight` khi yêu cầu.

### Lỗi 9 — Không xây lại pairLeft từ pairRight

Kuhn có thể chỉ duy trì `pairRight`; nếu muốn alternating BFS, cần biết cạnh ghép của từng L. Dựng `pairLeft` trước khi duyệt để nhận diện cạnh chưa ghép.

### Lỗi 10 — Pair arrays thiếu đối xứng

Nếu `pairL[u]=v` mà `pairR[v]!=u`, BFS R→L sai và matching không còn hợp lệ. Luôn cập nhật hoặc dựng hai mảng nhất quán.

### Lỗi 11 — Dùng visited vĩnh viễn cho mọi lượt Kuhn

Mảng `seenRight` phải được làm mới mỗi lần tìm đường tăng từ L tiếp theo, nếu không sẽ bỏ qua đường tăng hợp lệ.

### Lỗi 12 — Kết luận cover tối ưu dù R tự do reachable

R tự do reachable từ một L tự do qua alternating path tạo đường tăng. Hãy kiểm và **tiếp tục tăng matching**, thay vì dùng kết quả phủ.

### Lỗi 13 — Nhầm thứ tự các chỉ số

L0 và R0 là hai đỉnh khác phía; nếu gộp into một `boolean visited[0]` mà không offset hoặc tách mảng, sẽ đánh dấu đè.

### Lỗi 14 — Không xử lý đỉnh cô lập

Đỉnh cô lập vẫn tồn tại trong V. L cô lập là unmatched root; R cô lập không reachable, cả hai không nên có mặt trong minimum cover.

### Lỗi 15 — Tuyên bố MVC luôn duy nhất

Có thể có nhiều phủ tối ưu cùng size. Matching khác nhau cũng có thể tạo các phủ khác nhau; chỉ cần trả một phủ tối ưu khi đề không đòi liệt kê.

### Lỗi 16 — Coi graph bất kỳ đều áp được định lý Kőnig

Định lý bằng nhau áp cho **bipartite graph**. Tam giác là phản ví dụ: matching1, cover2.

### Lỗi 17 — Tối ưu nhầm số đỉnh khi có trọng số

Minimum-weight vertex cover có thể chọn **nhiều đỉnh hơn** để tổng cost thấp hơn. Dùng min-cut reduction cho bài weighted, không áp bài cardinality máy móc.

### Lỗi 18 — Không kiểm từng cạnh có được phủ

`coverSize==matchingSize` chưa đủ nếu matching hoặc cover sai. Kiểm `inCoverL[u]||inCoverR[v]` với mọi cạnh thật.

### Lỗi 19 — Lẫn vertex cover với edge cover

Vertex cover chọn **đỉnh** để chạm mọi cạnh. Edge cover chọn **cạnh** để chạm mọi đỉnh. Hai bài khác nhau và không thể thay tên mà giữ thuật toán.

### Lỗi 20 — Dùng thuật toán đồ thị có hướng không đúng

Bài này là graph hai phía **vô hướng** (quan hệ được biểu diễn L→R chỉ để lưu adjacency). Nếu cạnh thực sự có hướng và mục tiêu phủ cung theo định nghĩa khác, phải kiểm lại bài toán.

### Lỗi 21 — Truy cập v ngoài `[0,nR)`

Mỗi dòng adj[u] phải chứa chỉ số R hợp lệ, không phải ID chung của toàn graph nếu chưa ánh xạ. Kiểm validation đầu vào.

### Lỗi 22 — Không giới hạn brute force

Vét cạn `2^V` không khả thi cho V lớn. Chỉ dùng làm oracle trên V nhỏ; production dùng matching và alternating BFS.

### Lỗi 23 — Không kiểm lớp BFS trong Hopcroft–Karp

DFS của mỗi pha phải theo độ dài đường tăng ngắn nhất để giữ cận thời gian `O(E√V)`. Nếu tùy tiện đi cạnh có thể vẫn tìm nghiệm nhưng phân tích độ phức tạp khác.

### Lỗi 24 — So sánh chính xác `pairLeft` giữa hai thuật toán

Có thể tồn tại nhiều maximum matching. Kuhn và Hopcroft–Karp cho cặp khác nhau nhưng đều tối ưu. So size, tính hợp lệ và phủ tối ưu, không ép pair arrays giống từng ô.

### Lỗi 25 — Giả định greedy chọn R đầu tiên là đủ

Nếu L0 nhận R0 ngay, L1 chỉ có R0, thì L1 bị bỏ; nhưng L0 có thể chuyển sang R1 để nhường R0 cho L1. Cần đường tăng và tái ghép.

### Lỗi 26 — Tính independent set bằng cách chọn phủ chứ không lấy bù

Maximum independent set tương ứng là **`V\C`**, không phải C. Kích thước tối ưu của independent set bằng `V−matchingSize`.

## 17. Bộ kiểm thử cần có

| Input | Matching tối đa | Một phủ nhỏ nhất hợp lệ | Lưu ý |
|---|---:|---|---|
| L=∅, R bất kỳ | 0 | ∅ | Không có cạnh |
| L bất kỳ, R=∅ | 0 | ∅ | Không có cạnh |
| L0—R0 | 1 | {L0} hoặc {R0} | Nhiều nghiệm |
| `L0:{R0,R1}`, `L1:{R0}` | 2 | `{L0,L1}` hoặc `{R0,R1}` | Cần tái ghép nếu tham lam sai |
| Tam giác 1,1,2 theo **graph hai phía không có cạnh trong cùng phía** | Theo graph | Theo graph | Không dùng tam giác ba đỉnh thường |
| Đồ thị có tất cả L đều ghép | nL | Toàn bộ L | `Z_L=Z_R=∅` |
| Có L và R cô lập | Không tăng | Không chọn đỉnh cô lập | Giữ đủ số đỉnh |
| Ngôi sao một L, nhiều R | 1 | Chọn L trung tâm | Matching1 và cover1 |
| Ví dụ 7L,6R phần 6 | 5 | L3,L4,L5,R0,R1 | Z_L={0,1,2,6}, Z_R={0,1} |
| Hai cạnh song song L0—R0 | 1 | L0 hoặc R0 | Duplicate không tăng matching |
| Graph disconnected | Tổng matching các component | Hợp cover các component | Không cần nối thêm cạnh |
| Complete bipartite `K_(p,q)` | `min(p,q)` | Toàn phía nhỏ hơn | Nhiều lựa chọn nếu p=q |

### 17.1. Kiểm thử ngẫu nhiên có oracle

Quy trình đáng tin cho các đồ thị hai phía nhỏ:

1. Sinh `nL`, `nR` nhỏ, có thể bằng 0.
2. Sinh adjacency có cạnh, cạnh trùng, thành phần rời và đỉnh cô lập.
3. Chạy Hopcroft–Karp và lấy `matchingSize`, `coverLeft`, `coverRight`.
4. Chạy Kuhn độc lập để so matchingSize.
5. Dùng brute force duyệt mọi tập đỉnh để lấy `minimumCoverSize`.
6. Yêu cầu `HKmatchingSize == KuhnMatchingSize == bruteMinimumCoverSize`.
7. Xác nhận mọi cạnh có đầu trong cover; `coverSize==matchingSize`.
8. Xác nhận pair arrays đối xứng, matching không chung đầu.
9. Kiểm mọi unmatched L thuộc Z_L, mọi reached R đều matched.
10. Nếu đếm nhiều nghiệm, không buộc cover HK trùng cover đầu tiên từ brute.

**Đừng chỉ test perfect matching.** Khi mọi L đã ghép, BFS reconstruction có thể không mở rộng gì, che giấu lỗi xử lý các chuỗi alternating từ L chưa ghép.

## 18. Bài tập thực hành và đáp án

### Bài 1 — Định nghĩa

Vertex cover của đồ thị là gì?

**Đáp án:** tập đỉnh C sao cho với mọi cạnh (u,v), ít nhất một trong hai đầu u,v thuộc C.

### Bài 2 — Ghép cặp

Matching gồm ba cạnh không chung đầu. Có thể có phủ đỉnh size2 không?

**Đáp án:** không, vì ba cạnh matching rời nhau về đỉnh, mỗi cạnh đòi ít nhất một đỉnh cover riêng; cover phải có size≥3.

### Bài 3 — Kőnig

Đồ thị hai phía có maximum matching size7. Minimum vertex cover có size bao nhiêu?

**Đáp án:** 7.

### Bài 4 — Đồ thị tổng quát

Tam giác ba đỉnh có maximum matching size1. Minimum vertex cover có size1 không?

**Đáp án:** không; cần hai đỉnh. Kőnig không áp cho tam giác vì không bipartite.

### Bài 5 — Công thức

Đã biết `Z_L={L0,L2}` trên L={L0,L1,L2,L3}, `Z_R={R1}` trên R={R0,R1,R2}. Một cover theo Kőnig là gì?

**Đáp án:** `coverLeft={L1,L3}` và `coverRight={R1}`, size3, **nếu** Z lấy từ alternating BFS của một maximum matching.

### Bài 6 — Hướng cạnh luân phiên

Khi đi từ L tới R, đi cạnh thuộc matching hay không thuộc matching?

**Đáp án:** **không thuộc matching**. Khi đi từ R sang L, đi **cạnh thuộc matching**.

### Bài 7 — Nguồn BFS

Có ba đỉnh trái tự do. Dùng mấy đỉnh làm nguồn?

**Đáp án:** **cả ba**, đưa đồng thời vào queue.

### Bài 8 — R tự do reachable

Khi BFS luân phiên chạm một R chưa ghép, suy ra gì?

**Đáp án:** tồn tại đường tăng từ một L tự do tới R tự do; matching chưa maximum.

### Bài 9 — Ví dụ chính

Graph phần 6 có matching size và cover size bao nhiêu?

**Đáp án:** cả hai đều bằng **5**.

### Bài 10 — Tập Z

Với ví dụ phần 6, tập Z_L và Z_R là gì?

**Đáp án:** `Z_L={0,1,2,6}`, `Z_R={0,1}`.

### Bài 11 — Kết quả cover

Với Z phần 6, coverLeft và coverRight?

**Đáp án:** `coverLeft={3,4,5}`, `coverRight={0,1}`.

### Bài 12 — Đỉnh cô lập

L cô lập mà chưa ghép có thuộc Z_L không? Có nằm trong cover tối ưu không?

**Đáp án:** có thuộc Z_L vì là nguồn; **không** nằm trong coverLeft do phải lấy L\Z_L.

### Bài 13 — Perfect matching phía trái

Nếu matching ghép đủ mọi L, công thức trả cover nào?

**Đáp án:** `Z_L=Z_R=∅`, nên cover trả **toàn bộ L**, size nL.

### Bài 14 — Matching không duy nhất

Hai thuật toán trả matching khác cặp nhưng size bằng nhau. Có cần kết luận một thuật toán sai không?

**Đáp án:** không. Cần kiểm tính hợp lệ và giá trị maximum; matching tối đa có thể không duy nhất.

### Bài 15 — Cover không duy nhất

Ví dụ phần 6 có bao nhiêu minimum covers xét theo tập đỉnh?

**Đáp án:** **4**.

### Bài 16 — Đồ thị không cạnh

`nL=3`, `nR=4`, E=∅. Minimum cover?

**Đáp án:** tập rỗng, size0; mọi L chưa ghép đều thuộc Z_L.

### Bài 17 — Star

Một L0 nối với 100 đỉnh R. Maximum matching size và min vertex cover size?

**Đáp án:** đều bằng 1; chọn L0 làm cover.

### Bài 18 — Independent set

Đồ thị hai phía có 20 đỉnh tổng, maximum matching size6. Maximum independent set size?

**Đáp án:** `20−6=14`.

### Bài 19 — Weighted cover

Star có L0 cost10 và ba R cost1 mỗi đỉnh. Minimum-cardinality cover và minimum-weight cover có khác nhau không?

**Đáp án:** có: cardinality chọn `{L0}` size1 cost10; weighted chọn cả ba R size3 cost3.

### Bài 20 — Kuhn complexity

Một lần DFS tăng có thể quét nhiều cạnh, lặp nL lần. Chặn thời gian phổ biến?

**Đáp án:** `O(nL·E)` worst-case với cấu trúc DFS thích hợp.

### Bài 21 — Hopcroft–Karp complexity

Đồ thị hai phía V đỉnh, E cạnh. Matching Hopcroft–Karp và cover reconstruction có độ phức tạp?

**Đáp án:** matching `O(E√V)`, reconstruction `O(V+E)`.

### Bài 22 — Hai màu

BFS tô hai màu phát hiện cạnh có hai đầu cùng màu, suy ra gì?

**Đáp án:** đồ thị không bipartite (với tô màu đúng theo duyệt); không áp công thức König.

### Bài 23 — Cặp ghép nhất quán

Nếu pairL[2]=4 nhưng pairR[4]=1, matching hợp lệ không?

**Đáp án:** không; hai mảng bất nhất, không được dùng để reconstruct.

### Bài 24 — Kiểm cover

CoverSize bằng matchingSize, nhưng còn một cạnh có cả hai đầu nằm ngoài C. Có phải min vertex cover không?

**Đáp án:** không. Nó **không phải cover** vì cạnh ấy chưa được phủ, dù số lượng tình cờ bằng matching.

### Bài 25 — Hai cạnh song song

Hai bản sao cạnh L0—R0 có làm tăng matching size tối đa lên 2 không?

**Đáp án:** không; cả hai dùng chung đầu, chỉ chọn tối đa một trong matching.

### Bài 26 — Chứng chỉ tối ưu

Một matching hợp lệ có 9 cạnh và một vertex cover hợp lệ có 9 đỉnh trên cùng đồ thị. Có cần brute force để biết tối ưu không?

**Đáp án:** không. Mọi cover có ít nhất 9 đỉnh do matching; đã có cover 9 nên nó tối ưu. Tương tự matching9 là tối đa.

## 19. Checklist trước khi nộp lời giải

1. Đồ thị có thực sự **hai phía** hay đã được tô hai màu hợp lệ?
2. Có tách rõ ID của L và R không?
3. Đồ thị có **cạnh trong cùng phía** hoặc self-loop không? Nếu có, không đúng input bipartite.
4. Có xét **đỉnh cô lập** và hai phía có số lượng khác nhau?
5. Matching tính ra là **maximum**, không chỉ maximal?
6. `pairLeft`, `pairRight` có nhất quán và không chung đầu?
7. Có kiểm mọi cạnh matching thực sự tồn tại trong input?
8. Có khởi tạo BFS alternating từ **tất cả L chưa ghép**?
9. Có đi L→R chỉ qua **cạnh chưa ghép**?
10. Có đi R→L chỉ qua **cạnh ghép**?
11. Có đánh dấu visited trước khi enqueue để tránh vòng lặp?
12. Có đảm bảo không còn R tự do reachable?
13. Có tạo đúng `coverLeft=L\Z_L`?
14. Có tạo đúng `coverRight=Z_R`?
15. Có phân biệt `L0` với `R0` trong output?
16. Có kiểm **mọi cạnh** có ít nhất một đầu thuộc cover?
17. Có kiểm `coverSize==matchingSize`?
18. Có nhớ rằng output chỉ cần **một** cover tối ưu, không phải mọi cover?
19. Nếu matching phủ hết L, có xử lý Z rỗng đúng?
20. Nếu graph không có cạnh, cover có phải rỗng?
21. Có dùng boolean arrays để kiểm coverage trong O(E), tránh List.contains chậm?
22. Với đồ thị lớn, đã chọn Hopcroft–Karp thay Kuhn khi cần hiệu năng?
23. Với đồ thị nhỏ, đã đối chiếu brute force tối thiểu độc lập?
24. Nếu đỉnh có trọng số, đã chuyển sang **minimum-weight cover**, không coi cardinality cover là đủ?
25. Nếu graph không bipartite, đã dừng áp định lý Kőnig?
26. Nếu đề cần independent set, đã lấy **V\C**, không lấy C?
27. Nếu đếm nghiệm theo ID cạnh, đã xử lý duplicate theo đúng định nghĩa?
28. Có nêu rõ chi phí matching và chi phí khôi phục là hai giai đoạn khác nhau?

**Ghi nhớ:** Với đồ thị **hai phía** và một **maximum matching M**, bắt đầu từ **tất cả đỉnh L chưa ghép**. Duyệt **cạnh chưa ghép từ L sang R**, rồi **cạnh đang ghép từ R về L** để tìm `Z_L` và `Z_R`. Khi không còn đường tăng, kết quả:

`MinimumVertexCover = (L \ Z_L) ∪ Z_R`.

Tập ấy phủ mọi cạnh và có **đúng |M| đỉnh** theo định lý Kőnig; do đó nó là **phủ đỉnh nhỏ nhất**. Đừng đảo chiều công thức, đừng bắt đầu từ một L tự do duy nhất, đừng dùng matching mới maximal, và đừng áp kết quả này lên đồ thị không hai phía hoặc bài toán phủ đỉnh **có trọng số** mà không điều chỉnh.

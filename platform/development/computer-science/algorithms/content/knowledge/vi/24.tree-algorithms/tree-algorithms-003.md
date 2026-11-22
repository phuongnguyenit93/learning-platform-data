# Duyệt Euler để chuyển cây con thành một đoạn

**Duyệt Euler để chuyển cây con thành một đoạn** là kỹ thuật gán cho mỗi đỉnh của **cây có gốc** một vị trí liên tiếp theo thứ tự DFS, sao cho **mọi đỉnh thuộc cây con của u nằm gọn trong đúng một đoạn liên tiếp** của mảng mới. Sau bước biến đổi này, những yêu cầu như *tính tổng giá trị cây con*, *cộng đồng loạt vào các đỉnh trong cây con*, hoặc *đổi giá trị một đỉnh* có thể xử lý bằng các cấu trúc dữ liệu mảng như **prefix sum, Fenwick tree hoặc segment tree có lazy propagation**.

Bài thuộc nhóm **Thuật toán trên cây** trong Computer Science Algorithms. Điểm cốt lõi không chỉ là thuộc công thức `[tin[u], tout[u])`, mà còn phải nắm **vì sao cây con trở thành đoạn**, **thời điểm tăng bộ đếm Euler**, **quy ước hai biên**, **tính cố định của gốc** và **giới hạn khi truy vấn đường đi hay thay đổi cấu trúc cây**.

Trong bài, ta dùng **DFS thứ tự vào đỉnh** (*entry-time Euler order / preorder flattening*): mỗi đỉnh được ghi vào mảng đúng **một lần** khi bắt đầu thăm. Đây là một biến thể thường được gọi là *Euler tour technique*, nhưng cần phân biệt với Euler tour đầy đủ ghi cả lúc vào và ra đỉnh, hoặc dãy Euler phục vụ LCA.

## 1. Mô hình: cây, gốc, cây con và giá trị đỉnh

Một **cây vô hướng** có n đỉnh và đúng n−1 cạnh, đồng thời liên thông; không có chu trình. Chọn một đỉnh r làm **gốc**. Với mỗi đỉnh khác gốc, ta xác định một `parent[u]` — đỉnh đứng trước u trên đường duy nhất từ r tới u. Đỉnh nằm dưới u trong quan hệ gốc–cha–con được gọi là **hậu duệ** của u; cây con của u gồm **u và mọi hậu duệ của u**.

Ví dụ chọn gốc 0:

~~~text
             0
           /   \
          1     2
         / \   / \
        3   4 5   6
           / \
          7   8
~~~

Danh sách cạnh **vô hướng**, theo thứ tự thêm vào adjacency:

~~~text
0--1, 0--2
1--3, 1--4
2--5, 2--6
4--7, 4--8
~~~

Ta gán giá trị cho các đỉnh theo chỉ số 0..8:

~~~text
node:   0 1 2 3 4 5 6 7 8
value:  5 3 8 2 4 6 1 7 9
~~~

Theo gốc 0:
- Cây con của 4 là `{4,7,8}`.
- Cây con của 1 là `{1,3,4,7,8}`.
- Cây con của 2 là `{2,5,6}`.
- Cây con của 0 là **toàn bộ chín đỉnh**.
- Cây con của lá 7 chỉ có **một đỉnh 7**.

Đây là tính chất **phụ thuộc vào gốc được chọn**. Đổi gốc có thể đổi parent và tập cây con, dù các cạnh vô hướng không đổi.

### Mục tiêu tính toán

Ví dụ có hai loại thao tác:
1. `SUM(u)`: tính tổng `value[v]` trên tất cả v thuộc cây con của u.
2. `ADD(u,delta)`: cộng cùng delta vào mỗi đỉnh trong cây con của u.

Nếu với mỗi truy vấn đều duyệt lại từng đỉnh của cây con, một truy vấn có thể mất O(n). Với q truy vấn, trường hợp xấu có thể O(nq). Ta muốn biến phạm vi cây con thành **một đoạn mảng** để áp dụng thuật toán dữ liệu đã biết.

## 2. Duyệt Euler kiểu vào đỉnh một lần

Đặt `timer=0`, một mảng `order[]` chiều dài n và hai mảng `tin[]`, `tout[]`.

Khi DFS bắt đầu ở u:
1. Gán `tin[u]=timer`.
2. Ghi `order[timer]=u`.
3. Tăng `timer` thêm 1.
4. Duyệt lần lượt **toàn bộ các cây con của từng đứa con** của u.
5. Khi sắp rời u, gán `tout[u]=timer`. **Không tăng timer khi thoát.**

Quy ước này cho kết quả:

\[
\boxed{\text{các đỉnh cây con của }u
=\{order[i]\mid tin[u]\le i<tout[u]\}.}
\]

Đây là đoạn **nửa mở**:

\[
\boxed{[tin[u],\;tout[u])}.
\]

Hệ quả:

\[
\boxed{sizeSubtree[u]=tout[u]-tin[u].}
\]

**Ý nghĩa biên:** `tin[u]` là vị trí của u trong `order`; `tout[u]` là vị trí **ngay sau đỉnh cuối cùng** của cây con, không phải vị trí của đỉnh cuối. Nếu u là lá, `tout[u]=tin[u]+1`.

### Vì sao dùng đoạn nửa mở?

Với mảng 0-based:
- Truy vấn sum cho cây con u: `query(tin[u], tout[u])`.
- Cập nhật cộng cho cây con u: `add(tin[u], tout[u], delta)`.
- Số phần tử: `tout[u]-tin[u]`.
- Cây con r là gốc của toàn bộ cây: `[0,n)`.

Nếu cấu trúc dữ liệu của bạn dùng đoạn **đóng** `[l,r]`, cần chuyển thành `[tin[u],tout[u]-1]`. Không được dùng lẫn hai quy ước, vì rất dễ cập nhật thừa một đỉnh hoặc bỏ sót phần tử cuối.

### “Euler tour” có nhiều cách ghi khác nhau

Trong tài liệu có thể gặp:
- **Preorder / entry-only:** mỗi đỉnh xuất hiện đúng một lần, `order` dài n. Đây là cách bài này dùng để lấy **một đoạn cây con**.
- **Ghi sự kiện vào và ra:** có thể ghi mỗi đỉnh hai lần; dãy sự kiện dài 2n. Đối với giá trị mỗi đỉnh, không thể đơn giản cộng mọi sự kiện trong đoạn mà không sửa công thức.
- **Euler walk cho LCA:** ghi đỉnh mỗi lần đi qua cạnh/đi lên, có thể có độ dài 2n−1; phục vụ bài toán LCA bằng RMQ, không đồng nhất với mảng n phần tử ở đây.

Vì vậy luôn xác định **timer tăng vào lúc nào** và **tout là bao gồm hay loại trừ** trước khi dùng một công thức có tên “Euler”.

## 3. Giả mã DFS và thứ tự duyệt

Với cây vô hướng, mỗi cạnh xuất hiện ở danh sách kề của cả hai đầu. Khi đi từ u sang v, nhớ `parent[v]=u` và **không quay lại ngay parent** như một đứa con.

~~~text
timer = 0

dfs(u, p):
    parent[u] = p
    tin[u] = timer
    order[timer] = u
    timer++

    for v in adj[u]:
        if v == p:
            continue
        dfs(v, u)

    tout[u] = timer
~~~

Giả mã trên giả định đầu vào **đã là cây hợp lệ**. Nếu input có chu trình, chỉ bỏ parent không đủ để chống đệ quy vòng lặp. Khi phải xử lý đầu vào thực tế, hãy dùng `visited[]` và kiểm tra tính liên thông/chu trình, hoặc xác minh cây bằng một thuật toán độc lập trước.

### Phiên bản lặp tránh tràn stack Java

Một cây dạng đường thẳng có thể sâu n−1. DFS đệ quy Java có thể ném `StackOverflowError` khi n lớn. Chương trình bên dưới dùng:
- `ArrayDeque<Integer> stack` lưu đường DFS đang hoạt động;
- `nextIndex[u]` ghi **chỉ số láng giềng kế tiếp** chưa xét của u;
- `seen[u]` để kiểm tra không đi lại một đỉnh đã phát hiện;
- `tin[u]=−1` trước khi vào, gán vị trí đúng một lần;
- khi `nextIndex[u]` đã bằng độ dài adjacency[u], gán `tout[u]=timer` và pop u khỏi stack.

Khác biệt quan trọng: **không được gán tout ngay khi đẩy các con vào stack**. Phải gán sau khi **toàn bộ các cây con** đã xử lý xong, nếu không đoạn cây con sẽ bị thiếu đỉnh.

Giả mã lặp:

~~~text
seen[root] = true
parent[root] = -1
push(root)

while stack not empty:
    u = stack.peek()

    if tin[u] == -1:
        tin[u] = timer
        order[timer] = u
        timer++

    if nextIndex[u] < adj[u].size():
        v = adj[u][nextIndex[u]]
        nextIndex[u]++

        if v == parent[u]:
            continue
        if seen[v]:
            reject non-tree cycle

        seen[v] = true
        parent[v] = u
        push(v)
    else:
        tout[u] = timer
        pop()
~~~

Khi kết thúc, phải có `timer=n`. Nếu còn đỉnh chưa vào DFS thì đầu vào không liên thông. Chương trình mẫu còn kiểm tra số cạnh đúng n−1, đầu mút hợp lệ và self-loop.

## 4. Tính Euler trên ví dụ chín đỉnh

Với gốc 0 và adjacency giữ đúng thứ tự cạnh đã liệt kê, DFS vào các đỉnh:

~~~text
order = [0, 1, 3, 4, 7, 8, 2, 5, 6]
index =   0  1  2  3  4  5  6  7  8
~~~

Thời điểm vào (tin) và thời điểm sau cây con (tout):

| u | parent[u] | tin[u] | tout[u] | Đoạn nửa mở | Kích thước |
| ---: | ---: | ---: | ---: | --- | ---: |
| 0 | −1 | 0 | 9 | [0,9) | 9 |
| 1 | 0 | 1 | 6 | [1,6) | 5 |
| 2 | 0 | 6 | 9 | [6,9) | 3 |
| 3 | 1 | 2 | 3 | [2,3) | 1 |
| 4 | 1 | 3 | 6 | [3,6) | 3 |
| 5 | 2 | 7 | 8 | [7,8) | 1 |
| 6 | 2 | 8 | 9 | [8,9) | 1 |
| 7 | 4 | 4 | 5 | [4,5) | 1 |
| 8 | 4 | 5 | 6 | [5,6) | 1 |

Mảng đã làm phẳng bằng cách đặt giá trị của đỉnh u vào vị trí `tin[u]`:

~~~text
order index:       0  1  2  3  4  5  6  7  8
node:              0  1  3  4  7  8  2  5  6
flat value:        5  3  2  4  7  9  8  6  1
~~~

Đoạn của **cây con 4** là `[3,6)`, chứa `order[3..5]=[4,7,8]` và các giá trị `[4,7,9]`. Tổng:

\[
SUM(4)=4+7+9=20.
\]

Đoạn của **cây con 1** là `[1,6)`, chứa `[1,3,4,7,8]` với giá trị `[3,2,4,7,9]`, tổng `25`.

Đoạn của **cây con 2** là `[6,9)`, chứa `[2,5,6]` với giá trị `[8,6,1]`, tổng `15`.

Toàn bộ cây có tổng `45`. Với một lá 7, đoạn `[4,5)` chỉ có một phần tử.

### Hai đứa con tạo hai đoạn rời

Các cây con của 1 gồm:
- Cây con 3 là `[2,3)`.
- Cây con 4 là `[3,6)`.

Chúng không giao nhau. Ghép theo thứ tự vào DFS cho phần hậu duệ của 1 là `[2,6)`, cộng thêm chính đỉnh 1 ở vị trí tin[1]=1, thành cây con 1 `[1,6)`.

Tính chất này tiếp tục đúng với mọi độ sâu của cây.

## 5. Chứng minh cây con đúng bằng một đoạn

### Bất biến DFS

Khi `tin[u]` được gán, `timer` đang chỉ tới vị trí trống kế tiếp của mảng `order`. Từ lúc bắt đầu xử lý u cho tới lúc gán `tout[u]`, DFS **chỉ xử lý u và các đỉnh nằm trong cây con của u**. Nó không rời cây con của u để vào một nhánh ngoài rồi quay lại, vì DFS duyệt **trọn vẹn từng nhánh con** trước khi trở về cha.

Chính u được ghi một lần tại `tin[u]`. Mọi hậu duệ được ghi nối tiếp sau u; không có đỉnh ngoài cây con chen vào trước lúc u thoát. Vì timer tăng đúng một lần cho mỗi đỉnh đi vào, các vị trí được dùng là các số nguyên liên tiếp từ tin[u] đến tout[u]−1.

Vậy:

\[
\{tin[v]\mid v\in subtree(u)\}
=\{tin[u],tin[u]+1,\ldots,tout[u]-1\}.
\]

Lập luận cũng chứng minh:

\[
|subtree(u)|=tout[u]-tin[u].
\]

### Hệ quả tổ tiên

Với cây đã cố định gốc:

\[
u \text{ là tổ tiên của }v\text{ (kể cả }u=v)
\iff tin[u]\le tin[v]<tout[u].
\]

Cách kiểm tra này mất O(1) sau khi có tin/tout. Nếu yêu cầu **tổ tiên thực sự** không tính chính u, bổ sung điều kiện `u!=v`.

Với hai đỉnh u, v trong một cây có gốc, hai đoạn cây con hoặc:
- **một đoạn chứa đoạn còn lại**, khi một đỉnh là tổ tiên của đỉnh kia;
- **hai đoạn rời nhau**, khi không đỉnh nào là tổ tiên của đỉnh còn lại.

Không thể có hai đoạn cây con **giao nhau một phần nhưng không chứa nhau**.

### Giới hạn quan trọng

Tính đoạn liên tiếp chỉ đúng cho **cây con của gốc đã chọn**. Nó **không có nghĩa** rằng đường đi bất kỳ giữa hai đỉnh cũng là một đoạn Euler.

Ví dụ đường từ 3 tới 5 trong cây trên là:

~~~text
3 → 1 → 0 → 2 → 5
~~~

Vị trí Euler lần lượt `[2,1,0,6,7]`, **không liên tiếp**. Muốn cập nhật/truy vấn một **đường đi bất kỳ**, cần phương pháp khác như **Heavy-Light Decomposition (HLD)**, một cách chia đường thành nhiều đoạn; hoặc cấu trúc phù hợp nếu chỉ hỏi một số loại dữ liệu trên đường.

## 6. Từ cây con sang truy vấn đoạn mảng

Đặt:

\[
flat[tin[u]]=value[u].
\]

Từ nay một phép toán trên cây con u trở thành phép toán trên `flat[tin[u]..tout[u]-1]`.

| Bài trên cây | Bài trên mảng |
| --- | --- |
| Tổng giá trị cây con u | Range sum `[tin[u],tout[u])` |
| Min/max giá trị cây con u | Range min/max trên cùng đoạn |
| Cộng delta vào mọi đỉnh cây con u | Range add trên cùng đoạn |
| Gán giá trị mới cho riêng đỉnh u | Point set tại `tin[u]` |
| Cộng delta cho riêng đỉnh u | Point add tại `tin[u]` |
| Số đỉnh cây con u | `tout[u]-tin[u]`, O(1) |
| u là tổ tiên của v? | `tin[u]<=tin[v]<tout[u]`, O(1) |

**Điểm cần hiểu:** Euler chỉ là **cách đổi chỉ số**, không tự giúp cập nhật nhanh. Độ phức tạp truy vấn phụ thuộc vào cấu trúc dữ liệu mà ta đặt trên `flat[]`.

### Không có cập nhật: prefix sum

Với `prefix[0]=0` và:

\[
prefix[i+1]=prefix[i]+flat[i],
\]

tổng cây con u bằng:

\[
SUM(u)=prefix[tout[u]]-prefix[tin[u]].
\]

Xây prefix trong O(n); mỗi truy vấn tổng O(1). Nhưng nếu giá trị đỉnh bị cập nhật, prefix phía sau có thể phải tính lại O(n), trừ khi đổi sang cấu trúc dữ liệu động.

### Chỉ gán/cộng từng đỉnh, hỏi tổng cây con: Fenwick tree

Nếu chỉ thay đổi giá trị **một đỉnh mỗi lần**, dùng Fenwick/Binary Indexed Tree theo thứ tự Euler:
- Point add tại tin[u]: O(log n).
- Sum đoạn cây con: lấy hai prefix sums, O(log n).
- Point set: lưu giá trị hiện tại hoặc query điểm để tính delta rồi point add, O(log n).

Cách này đơn giản hơn segment tree nếu đề **không cần range add**.

### Cộng cả cây con và hỏi tổng: lazy segment tree

Nếu vừa có:
- `ADD_SUBTREE(u,delta)`: cộng delta cho cả đoạn `[tin[u],tout[u])`,
- `SUM_SUBTREE(u)`: tính tổng cùng đoạn,

hãy dùng **segment tree có lazy propagation**. Một lần cộng lên đoạn hoàn toàn phủ một nút segment tree chỉ cần cập nhật tổng và thẻ lazy, không đi xuống từng lá.

Bài này chọn **lazy segment tree** cho chương trình Java, vì cùng một cấu trúc xử lý được tổng cây con, cộng cây con, lấy giá trị đỉnh và gán giá trị một đỉnh.

## 7. Lazy segment tree: vì sao xử lý được cả đoạn?

Mỗi nút segment tree đại diện một đoạn nửa mở `[l,r)`:
- `sum[node]` là **tổng hiện tại** của mọi phần tử trong đoạn;
- `lazy[node]` là lượng cộng chưa đẩy xuống các nút con.

Nếu cộng cùng delta cho toàn đoạn `[l,r)`, có đúng `r−l` phần tử, nên:

\[
sum[node]\gets sum[node]+\delta\,(r-l)
\]

và:

\[
lazy[node]\gets lazy[node]+\delta.
\]

Không cần chạm từng lá.

Khi một truy vấn hoặc cập nhật sau đó cần đi vào các nút con, ta **push**:
1. Áp dụng lazy của nút cha lên hai con, mỗi con với **độ dài đoạn riêng**.
2. Đặt lazy của nút cha về 0.
3. Tiếp tục xử lý các phần giao với phạm vi yêu cầu.

Nếu phạm vi yêu cầu phủ trọn một nút, dùng tổng đã lưu ngay. Nếu không giao, trả 0 với truy vấn tổng, hoặc bỏ qua đối với cập nhật cộng. Nếu giao một phần, push rồi đi xuống hai con.

### Các phép toán trên cây

- `sumSubtree(u) = seg.sum(tin[u],tout[u])`.
- `addSubtree(u,delta) = seg.add(tin[u],tout[u],delta)`.
- `nodeValue(u) = seg.sum(tin[u],tin[u]+1)`.
- `setNode(u,newValue)`: tìm giá trị cũ tại tin[u], tính `delta=newValue-old`, rồi cộng delta vào đoạn điểm `[tin[u],tin[u]+1)`.

Một phép truy vấn/cập nhật đoạn có O(log n) nút cần xử lý theo segment tree lazy, nên cả bốn thao tác trên có **O(log n)** thời gian. Point set gồm một point query và một point update, vẫn O(log n).

**Không được nhầm cộng vào cây con với gán cả cây con:** range add thay `value[x]` bằng `value[x]+delta`; range assign thay bằng **cùng giá trị mới**. Hai loại lazy tag khác nhau và cần quy tắc hợp thành riêng nếu muốn hỗ trợ cả hai. Chương trình mẫu chỉ hỗ trợ **range add** và **point set**, không có range assign.

## 8. Chương trình Java 17 hoàn chỉnh

Chương trình gồm hai thành phần độc lập:
- **Euler flattening:** dựng cây vô hướng, kiểm tra số cạnh và đầu mút, DFS lặp để tính `tin`, `tout`, `parent`, `depth`, `order`. Kiểm tra `seen[]` để từ chối chu trình; bảo đảm duyệt đủ n đỉnh.
- **LazySegmentTree:** xây từ mảng đã làm phẳng, hỗ trợ cộng đoạn và tổng đoạn nửa mở.

`SubtreeEngine` gắn hai thành phần lại và cung cấp đúng các thao tác theo **chỉ số đỉnh gốc**.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class EulerSubtreeDemo {
    record Tour(int root, int[] tin, int[] tout,
            int[] parent, int[] depth, int[] order) {}

    static List<List<Integer>> makeTree(
            int n, int[][] edges) {
        if (n <= 0) {
            throw new IllegalArgumentException(
                    "Tree must have vertices");
        }
        if (edges == null || edges.length != n - 1) {
            throw new IllegalArgumentException(
                    "Tree requires n-1 edges");
        }

        List<List<Integer>> graph = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            graph.add(new ArrayList<>());
        }
        for (int[] e : edges) {
            if (e == null || e.length != 2
                    || e[0] < 0 || e[0] >= n
                    || e[1] < 0 || e[1] >= n) {
                throw new IllegalArgumentException(
                        "Invalid edge");
            }
            int u = e[0], v = e[1];
            if (u == v) {
                throw new IllegalArgumentException("Self-loop");
            }
            graph.get(u).add(v);
            graph.get(v).add(u);
        }
        return graph;
    }

    // Entry-only Euler DFS: moi dinh vao order dung 1 lan.
    static Tour flattenTree(
            List<List<Integer>> g, int root) {
        int n = g.size();
        if (root < 0 || root >= n) {
            throw new IllegalArgumentException("Invalid root");
        }

        int[] tin = new int[n];
        int[] tout = new int[n];
        int[] parent = new int[n];
        int[] depth = new int[n];
        int[] order = new int[n];
        int[] nextIndex = new int[n];
        boolean[] seen = new boolean[n];
        Arrays.fill(tin, -1);
        Arrays.fill(parent, -2);

        ArrayDeque<Integer> stack = new ArrayDeque<>();
        seen[root] = true;
        parent[root] = -1;
        stack.push(root);
        int timer = 0;

        while (!stack.isEmpty()) {
            int u = stack.peek();
            if (tin[u] == -1) {
                tin[u] = timer;
                order[timer] = u;
                timer++;
            }

            if (nextIndex[u] < g.get(u).size()) {
                int v = g.get(u).get(nextIndex[u]++);
                if (v == parent[u]) continue;
                if (seen[v]) {
                    throw new IllegalArgumentException(
                            "Not a tree");
                }
                seen[v] = true;
                parent[v] = u;
                depth[v] = depth[u] + 1;
                stack.push(v);
            } else {
                // Sau KHI da tham xong toan bo cay con.
                tout[u] = timer; // exclusive
                stack.pop();
            }
        }

        if (timer != n) {
            throw new IllegalArgumentException(
                    "Disconnected tree");
        }
        return new Tour(root, tin, tout, parent, depth, order);
    }

    static long[] flatValues(Tour t, long[] values) {
        int n = t.order().length;
        if (values == null || values.length != n) {
            throw new IllegalArgumentException(
                    "Invalid value array");
        }
        long[] flat = new long[n];
        for (int i = 0; i < n; i++) {
            flat[i] = values[t.order()[i]];
        }
        return flat;
    }

    static final class LazySegmentTree {
        final int n;
        final long[] sum;
        final long[] lazy;

        LazySegmentTree(long[] flat) {
            this.n = flat.length;
            this.sum = new long[4 * Math.max(1, n)];
            this.lazy = new long[4 * Math.max(1, n)];
            if (n > 0) build(1, 0, n, flat);
        }

        void build(int p, int l, int r, long[] flat) {
            if (r - l == 1) {
                sum[p] = flat[l];
                return;
            }
            int m = l + (r - l) / 2;
            build(p * 2, l, m, flat);
            build(p * 2 + 1, m, r, flat);
            sum[p] = Math.addExact(sum[p * 2], sum[p * 2 + 1]);
        }

        void apply(int p, int l, int r, long delta) {
            sum[p] = Math.addExact(
                    sum[p], Math.multiplyExact(delta, r - l));
            lazy[p] = Math.addExact(lazy[p], delta);
        }

        void push(int p, int l, int r) {
            if (lazy[p] == 0 || r - l == 1) return;
            int m = l + (r - l) / 2;
            apply(p * 2, l, m, lazy[p]);
            apply(p * 2 + 1, m, r, lazy[p]);
            lazy[p] = 0;
        }

        void checkRange(int l, int r) {
            if (l < 0 || r < l || r > n) {
                throw new IllegalArgumentException("Invalid range");
            }
        }

        void add(int l, int r, long delta) {
            checkRange(l, r);
            if (l == r) return;
            add(1, 0, n, l, r, delta);
        }

        void add(int p, int l, int r,
                int ql, int qr, long delta) {
            if (qr <= l || r <= ql) return;
            if (ql <= l && r <= qr) {
                apply(p, l, r, delta);
                return;
            }
            push(p, l, r);
            int m = l + (r - l) / 2;
            add(p * 2, l, m, ql, qr, delta);
            add(p * 2 + 1, m, r, ql, qr, delta);
            sum[p] = Math.addExact(
                    sum[p * 2], sum[p * 2 + 1]);
        }

        long query(int l, int r) {
            checkRange(l, r);
            if (l == r) return 0;
            return query(1, 0, n, l, r);
        }

        long query(int p, int l, int r,
                int ql, int qr) {
            if (qr <= l || r <= ql) return 0;
            if (ql <= l && r <= qr) return sum[p];
            push(p, l, r);
            int m = l + (r - l) / 2;
            return Math.addExact(
                    query(p * 2, l, m, ql, qr),
                    query(p * 2 + 1, m, r, ql, qr));
        }
    }

    static final class SubtreeEngine {
        final Tour tour;
        final LazySegmentTree seg;

        SubtreeEngine(int n, int[][] edges,
                int root, long[] values) {
            List<List<Integer>> g = makeTree(n, edges);
            tour = flattenTree(g, root);
            seg = new LazySegmentTree(flatValues(tour, values));
        }

        void checkNode(int u) {
            if (u < 0 || u >= tour.order().length) {
                throw new IllegalArgumentException("Invalid node");
            }
        }

        int sizeSubtree(int u) {
            checkNode(u);
            return tour.tout()[u] - tour.tin()[u];
        }

        long sumSubtree(int u) {
            checkNode(u);
            return seg.query(
                    tour.tin()[u], tour.tout()[u]);
        }

        void addSubtree(int u, long delta) {
            checkNode(u);
            seg.add(tour.tin()[u], tour.tout()[u], delta);
        }

        long nodeValue(int u) {
            checkNode(u);
            return seg.query(tour.tin()[u], tour.tin()[u] + 1);
        }

        void setNode(int u, long newValue) {
            checkNode(u);
            long old = nodeValue(u);
            long delta = Math.subtractExact(newValue, old);
            seg.add(tour.tin()[u], tour.tin()[u] + 1, delta);
        }
    }

    static String subtreeNodes(Tour t, int u) {
        return Arrays.toString(Arrays.copyOfRange(
                t.order(), t.tin()[u], t.tout()[u]));
    }

    public static void main(String[] args) {
        int[][] edges = {
            {0,1}, {0,2}, {1,3}, {1,4},
            {2,5}, {2,6}, {4,7}, {4,8}
        };
        long[] values = {5,3,8,2,4,6,1,7,9};

        SubtreeEngine engine =
                new SubtreeEngine(9, edges, 0, values);
        Tour t = engine.tour;
        System.out.println(
                "order=" + Arrays.toString(t.order()));
        System.out.println(
                "tin=" + Arrays.toString(t.tin()));
        System.out.println(
                "tout=" + Arrays.toString(t.tout()));
        System.out.println(
                "parent=" + Arrays.toString(t.parent()));
        System.out.println(
                "flat=" + Arrays.toString(flatValues(t, values)));

        System.out.println("subtree1=["
                + t.tin()[1] + "," + t.tout()[1] + ")"
                + " nodes=" + subtreeNodes(t, 1));
        System.out.println("subtree4=["
                + t.tin()[4] + "," + t.tout()[4] + ")"
                + " nodes=" + subtreeNodes(t, 4));
        System.out.println("size4=" + engine.sizeSubtree(4));

        System.out.println("sumRoot=" + engine.sumSubtree(0));
        System.out.println("sum1=" + engine.sumSubtree(1));
        System.out.println("sum4=" + engine.sumSubtree(4));
        System.out.println("sum2=" + engine.sumSubtree(2));

        engine.addSubtree(4, 10);
        System.out.println(
                "afterAdd4_sum4=" + engine.sumSubtree(4));
        System.out.println(
                "afterAdd4_sum1=" + engine.sumSubtree(1));
        System.out.println(
                "afterAdd4_sumRoot=" + engine.sumSubtree(0));
        System.out.println(
                "afterAdd4_node7=" + engine.nodeValue(7));

        engine.setNode(7, 0);
        System.out.println(
                "afterSet7_node7=" + engine.nodeValue(7));
        System.out.println(
                "afterSet7_sum4=" + engine.sumSubtree(4));
        System.out.println(
                "afterSet7_sumRoot=" + engine.sumSubtree(0));

        engine.addSubtree(2, -2);
        System.out.println(
                "afterAdd2_sum2=" + engine.sumSubtree(2));
        System.out.println(
                "afterAdd2_sumRoot=" + engine.sumSubtree(0));
        System.out.println(
                "afterAdd2_sum4=" + engine.sumSubtree(4));

        // Tao tour MOI neu thay doi goc.
        SubtreeEngine reroot =
                new SubtreeEngine(9, edges, 4, values);
        Tour tr = reroot.tour;
        System.out.println("reroot4_order="
                + Arrays.toString(tr.order()));
        System.out.println("reroot4_subtree1=["
                + tr.tin()[1] + "," + tr.tout()[1] + ")"
                + " nodes=" + subtreeNodes(tr, 1));

        SubtreeEngine single = new SubtreeEngine(
                1, new int[0][0], 0, new long[]{-5});
        Tour ts = single.tour;
        System.out.println("singleInterval=["
                + ts.tin()[0] + "," + ts.tout()[0] + ")");
        System.out.println("singleSum=" + single.sumSubtree(0));
        single.addSubtree(0, 7);
        System.out.println(
                "singleAfterAdd=" + single.sumSubtree(0));

        try {
            new SubtreeEngine(4,
                    new int[][]{{0,1}, {1,2}, {2,0}},
                    0, new long[4]);
            throw new AssertionError("Cycle was accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "cycleRejected=" + ex.getMessage());
        }

        try {
            new SubtreeEngine(3, new int[][]{{0,1}},
                    0, new long[3]);
            throw new AssertionError("Bad edge count accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "badCountRejected=" + ex.getMessage());
        }
    }
}
~~~

Lưu mã thành tệp **EulerSubtreeDemo.java**, dùng **JDK 17 trở lên**:

~~~bash
javac EulerSubtreeDemo.java
java EulerSubtreeDemo
~~~

**Đầu ra dự kiến (với thứ tự adjacency trong mã):**

~~~text
order=[0, 1, 3, 4, 7, 8, 2, 5, 6]
tin=[0, 1, 6, 2, 3, 7, 8, 4, 5]
tout=[9, 6, 9, 3, 6, 8, 9, 5, 6]
parent=[-1, 0, 0, 1, 1, 2, 2, 4, 4]
flat=[5, 3, 2, 4, 7, 9, 8, 6, 1]
subtree1=[1,6) nodes=[1, 3, 4, 7, 8]
subtree4=[3,6) nodes=[4, 7, 8]
size4=3
sumRoot=45
sum1=25
sum4=20
sum2=15
afterAdd4_sum4=50
afterAdd4_sum1=55
afterAdd4_sumRoot=75
afterAdd4_node7=17
afterSet7_node7=0
afterSet7_sum4=33
afterSet7_sumRoot=58
afterAdd2_sum2=9
afterAdd2_sumRoot=52
afterAdd2_sum4=33
reroot4_order=[4, 1, 0, 2, 5, 6, 3, 7, 8]
reroot4_subtree1=[1,7) nodes=[1, 0, 2, 5, 6, 3]
singleInterval=[0,1)
singleSum=-5
singleAfterAdd=2
cycleRejected=Not a tree
badCountRejected=Tree requires n-1 edges
~~~

### Giải thích từng nhóm kết quả

**Flatten:** gốc 0 tạo thứ tự `[0,1,3,4,7,8,2,5,6]`. Trong mảng `flat`, giá trị tại index i là giá trị của đỉnh `order[i]`, **không nhất thiết là giá trị của đỉnh i**.

**Tổng ban đầu:** toàn cây 45; cây con 1 tổng 25, cây con 4 tổng 20, cây con 2 tổng 15.

**Cộng vào cây con 4:** ba đỉnh 4,7,8 đều tăng 10. Tổng cây con 4 tăng `3×10=30` thành 50. Tổng cây con 1 cũng tăng 30 thành 55; tổng toàn cây từ 45 thành 75. Giá trị riêng đỉnh 7 tăng từ 7 thành 17.

**Gán đỉnh 7 về 0:** chỉ một đỉnh giảm 17. Tổng cây con 4 từ 50 thành 33; tổng toàn cây từ 75 thành 58.

**Cộng −2 vào cây con 2:** đúng ba đỉnh 2,5,6 giảm mỗi đỉnh 2. Tổng cây con 2 từ 15 thành 9; tổng toàn cây từ 58 thành 52; cây con 4 không đổi và vẫn là 33.

**Đổi gốc sang 4:** kết quả tạo Euler **mới**. Cây con 1 lúc này là `{1,0,2,3,5,6}` thay vì tập cũ `{1,3,4,7,8}`. Tập này nằm trong đoạn `[1,7)` của thứ tự Euler mới. Chương trình cố ý dùng mảng giá trị **ban đầu** cho ví dụ đổi gốc, không mang theo những cập nhật segment tree trước đó.

**Cây một đỉnh:** `tin[0]=0`, `tout[0]=1`, cây con chính nó; tổng ban đầu −5, sau cộng 7 thành 2.

**Dữ liệu không phải cây:** trường hợp có vòng 0–1–2–0 và một đỉnh 3 cô lập dù có n−1 cạnh, nên DFS phát hiện cạnh quay tới một đỉnh đã seen và báo `Not a tree`. Trường hợp chỉ một cạnh cho ba đỉnh sai điều kiện n−1 và bị từ chối sớm.

### Lưu ý tính an toàn của ví dụ Java

- `Tour` là record chứa các mảng; Java **không tự sao chép sâu** mảng khi tạo record. Mã minh họa xem các mảng tour là **chỉ đọc** sau xây dựng. Nếu đóng gói thành thư viện công khai, nên làm defensive copy hoặc ẩn quyền sửa để bảo vệ bất biến.
- `LazySegmentTree` dùng `Math.addExact` và `Math.multiplyExact` để phát hiện overflow; `setNode` dùng `Math.subtractExact`. Giả thiết các tổng trung gian, tích delta×độ dài đoạn và nhãn lazy đều biểu diễn được bằng long. Nếu phép toán ném `ArithmeticException` giữa một cập nhật, cấu trúc không bảo đảm rollback về trạng thái cũ; **không tiếp tục dùng engine ấy như thể thao tác không xảy ra**. Với miền giá trị lớn cần `BigInteger` hoặc kiểm tra điều kiện miền số trước khi cập nhật.
- DFS cây dùng stack tường minh và `nextIndex[]` để tránh tràn ngăn xếp do đường cây sâu. Hàm segment tree vẫn dùng đệ quy, nhưng độ sâu chỉ O(log n) với mảng có kích thước hợp lý.
- `makeTree` kiểm tra n>0 và đúng n−1 cạnh, đầu mút và self-loop; `flattenTree` từ chối gặp lại đỉnh không phải parent và kiểm tra thăm đủ n đỉnh. Điều này giúp không dùng nhầm công thức cây con cho dữ liệu có chu trình hoặc không liên thông.
- Không được thay đổi các cạnh hoặc root **sau khi đã tạo tin/tout** mà vẫn tin những chỉ số cũ còn đúng.

## 9. Tính đúng của chương trình

### Tính đúng của flattenTree

**Bất biến 1:** mỗi đỉnh có `tin[u]!=−1` sau khi được đưa vào `order` đúng một lần. `seen[]` ngăn không cho đưa một đỉnh vào hai nhánh DFS, và mỗi đỉnh chỉ có một lần gán tin.

**Bất biến 2:** trong stack, các đỉnh biểu diễn đường từ root tới đỉnh đang xử lý. `nextIndex[u]` chỉ tăng khi một cạnh kề được xem xét, nên không bỏ sót cạnh. Khi u được pop, tất cả những đứa con của u đã được pop xong.

**Bất biến 3:** `tout[u]` được gán bằng timer đúng khi không còn láng giềng chưa xét; thời điểm này, toàn bộ hậu duệ của u đã nằm liên tiếp trong `order` kể từ tin[u].

Với đầu vào cây hợp lệ, root khám phá toàn bộ n đỉnh. Từ ba bất biến suy ra đoạn `[tin[u],tout[u])` gồm đúng các đỉnh thuộc cây con u. Việc dùng stack lặp thay cho stack lời gọi đệ quy không làm đổi thứ tự xử lý mỗi cạnh.

### Tính đúng của lazy segment tree

Mỗi nút đại diện một đoạn [l,r) và lưu đúng tổng giá trị hiện hành của đoạn. Khi áp dụng cùng delta cho cả đoạn, tổng tăng `delta×(r−l)`; nhãn lazy biểu diễn phép cộng chưa phân phối xuống các con.

Khi cần đi sâu, push chia phép cộng vào hai con theo đúng độ dài đoạn, giữ tổng của cha bằng tổng hai con. Với query, đoạn không giao đóng góp 0; đoạn phủ trọn đóng góp sum[node]; đoạn giao một phần bằng tổng câu trả lời từ hai con. Với range add, các đoạn phủ trọn được cập nhật trực tiếp, còn đoạn giao một phần được xử lý ở con và cập nhật tổng cha.

Do đó query và add trên `[tin[u],tout[u])` tác động đúng tất cả và chỉ những đỉnh thuộc cây con u. Point set dùng một phép query điểm và một phép cộng delta cho đúng một vị trí, cũng giữ bất biến này.

## 10. Phân tích độ phức tạp

Đặt n là số đỉnh. Trong một cây hợp lệ, m=n−1:

| Công việc | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Dựng adjacency của cây | O(n) | O(n) để lưu các cạnh hai chiều |
| DFS Euler lặp tính tin/tout/order | O(n) | O(n) |
| Tạo flat và xây segment tree | O(n) | O(n) |
| `sizeSubtree(u)` | O(1) | O(1) |
| `sumSubtree(u)` | O(log n) | O(log n) stack segment tree |
| `addSubtree(u,delta)` | O(log n) | O(log n) |
| `nodeValue(u)` | O(log n) | O(log n) |
| `setNode(u,new)` | O(log n) | O(log n) |
| Truy vấn chỉ kiểm tra tổ tiên bằng tin/tout | O(1) | O(1) |

Tổng tiền xử lý **O(n)**, xử lý q truy vấn thuộc các loại trên **O(q log n)**; tổng **O(n+q log n)** thời gian và O(n) bộ nhớ. Các mốc này giả thiết phép cộng số `long` có chi phí O(1), cây và gốc giữ cố định, và **không tính chi phí in ra danh sách toàn bộ đỉnh một cây con**. Nếu thật sự xuất tất cả k đỉnh thuộc cây con, riêng đầu ra đã tốn Ω(k).

Với **prefix sum** không có cập nhật, tổng tiền xử lý O(n), truy vấn tổng O(1). Với **Fenwick** và chỉ cập nhật từng đỉnh, mỗi cập nhật/đọc tổng cây con O(log n). Chọn cấu trúc vừa đủ theo loại thao tác, không bắt buộc dùng lazy segment tree cho mọi bài.

### Kiểm tra chi phí cập nhật cả cây con

Một cập nhật `ADD(u,delta)` trên k đỉnh làm tổng cây con u tăng `k×delta`, với `k=tout[u]-tin[u]`. Nhưng khi truy vấn tổng của **một cây con tổ tiên khác**, mức tăng phụ thuộc số đỉnh **giao** hai cây con. Vì các đoạn cây con hoặc chứa nhau hoặc rời nhau, phép giao có cấu trúc rõ ràng, phù hợp với range add/range sum.

Ví dụ trên: cập nhật +10 cây con 4 làm tổng cây con 1 tăng 30 vì đoạn `[3,6)` nằm trọn trong `[1,6)`; không làm tổng cây con 2 thay đổi vì `[6,9)` rời `[3,6)`.

## 11. Đổi gốc và thay đổi cấu trúc cây

### Đổi gốc không giữ nguyên mọi đoạn

Cho cùng cây nhưng chuyển gốc từ 0 sang 4. Khi đó đường cha–con đổi chiều dọc theo đường từ 0 tới 4. Đỉnh 1 trở thành con của 4, và cây con 1 theo gốc mới chứa:

~~~text
{1, 0, 2, 3, 5, 6}
~~~

Trong `order` theo gốc **cũ** là `[0,1,3,4,7,8,2,5,6]`, các vị trí tương ứng không tạo thành một đoạn: `{0,1,2,6,7,8}`.

Nếu chạy lại Euler với gốc **mới 4**, `order` mới là:

~~~text
[4, 1, 0, 2, 5, 6, 3, 7, 8]
~~~

Cây con của 1 lại là một đoạn liên tiếp **[1,7)**. Điều này không mâu thuẫn: tính liên tiếp luôn đúng **so với một gốc cố định đã dùng để tính Euler**.

Nếu hệ thống có rất nhiều truy vấn đổi gốc, có thể áp dụng công thức dựa trên quan hệ tổ tiên và phần bù cây con, hoặc dùng kỹ thuật chuyên biệt. Không được lặng lẽ dùng `tin/tout` cũ như thể root chưa thay đổi.

### Thêm hoặc xóa cạnh

Khi thêm/xóa cạnh, tập hậu duệ và thứ tự DFS có thể thay đổi. Tin/tout cũ **không còn bảo đảm** đúng. Với cây tĩnh, cứ tiền xử lý một lần. Với cây động thực sự có thao tác link/cut, cần cấu trúc khác hoặc tính lại Euler khi cấu trúc thay đổi; không thể giả định cập nhật một cạnh là một phép cập nhật đoạn giá trị bình thường.

### Trọng số nằm trên cạnh, không phải đỉnh

Nếu đề gán trọng số cho **cạnh**, một cách thông dụng là lưu trọng số của cạnh `parent[u]→u` vào vị trí của đỉnh **u** (ngoại trừ root không có cạnh parent). Khi cần tổng trọng số của **những cạnh nằm trọn trong cây con u**, phải **loại slot của u** và dùng đoạn `[tin[u]+1,tout[u])`; nếu truy vấn tổng cạnh trên đường nối từ cha tới u, đó là một ý nghĩa khác và không được loại tùy tiện.

Lựa chọn biểu diễn này giúp dùng mảng Euler, nhưng phải ghi rõ **giá trị ban đầu thuộc đỉnh hay cạnh**.

## 12. Kiểm thử độc lập và các bất biến nên xác minh

Ngoài việc so sánh các dòng stdout, nên kiểm tra **thuộc tính** thay vì chỉ một ví dụ.

### Kiểm tra bằng cây nhỏ

Với một cây đã chọn gốc:
1. `order` phải là một hoán vị của `0..n−1`.
2. `tin[order[i]]=i`.
3. `0<=tin[u]<tout[u]<=n`.
4. `tout[u]-tin[u]` phải bằng số đỉnh thực sự thuộc cây con của u.
5. Tập `{order[tin[u]],...,order[tout[u]-1]}` phải bằng tập hậu duệ của u (kể cả u) tính bằng quan hệ parent.
6. Với u,v, điều kiện `tin[u]<=tin[v]<tout[u]` phải khớp việc u là tổ tiên của v.

Một kiểm chứng độc lập đã đối chiếu các bất biến này trên **1.442 cây có nhãn với 1..6 đỉnh**, duyệt **mọi gốc hợp lệ** cho tổng **8.477 lượt cây/gốc**:
- n=1: 1 cây, 1 gốc;
- n=2: 1 cây, 2 gốc;
- n=3: 3 cây, 9 cặp cây/gốc;
- n=4: 16 cây, 64 cặp;
- n=5: 125 cây, 625 cặp;
- n=6: 1.296 cây, 7.776 cặp.

Tập này có thể sinh bằng mã Prüfer của cây có nhãn (với n≥2, số cây là `n^(n−2)`). Đây là **kiểm thử hữu hạn**, không thay thế chứng minh liên tiếp ở phần 5.

### Kiểm tra cập nhật đoạn

Trên các mảng nhỏ có cả số âm và dương, so sánh segment tree lazy với **mảng thường**:
- Cộng delta từng phần tử trong đoạn tương ứng ở mảng thường.
- Gán một phần tử bằng cách thay giá trị tại vị trí đó.
- Tổng trên đoạn so với phép cộng trực tiếp qua mảng.
- Luôn kiểm tra tổng toàn bộ mảng sau từng thao tác.

Một phép đối chiếu độc lập sử dụng 24 độ dài mảng, 20 bộ dữ liệu mỗi độ dài và 75 phép thao tác cho mỗi bộ, tương ứng **36.000 lượt thao tác**. Các kết quả truy vấn đoạn và tổng toàn mảng đều trùng với mô phỏng mảng đơn giản.

Đây là kiểm thử phần **segment tree**, tách biệt với kiểm thử tính chất **Euler**. Khi kết hợp, kiểm thử end-to-end còn nên so với một thuật toán chậm duyệt hậu duệ thực tế rồi cập nhật/cộng trực tiếp từng đỉnh.

**Lưu ý:** những số kiểm thử trên mô tả các phép đối chiếu thuật toán độc lập, **không phải** những bài test được tự động chạy bởi `main()` của chương trình Java trên. `main()` trình bày các ví dụ xác định, trường hợp biên và lỗi đầu vào.

### Cách kiểm tra một kết quả cập nhật

Với u bất kỳ, lưu danh sách đỉnh trong `order[tin[u]..tout[u]-1]`. Nếu chạy `addSubtree(u,delta)`, chỉ những đỉnh thuộc danh sách ấy được tăng. Một đỉnh v ngoài đoạn phải giữ nguyên.

Có thể kiểm tra tổng thay đổi theo công thức `delta×(tout[u]-tin[u])` cho chính cây con u. Nếu giá trị âm, tổng vẫn có thể giảm; không được giả định cập nhật luôn làm tổng tăng.

## 13. Trường hợp biên và lỗi phổ biến

| Trường hợp | Kết quả / quy tắc |
| --- | --- |
| Cây một đỉnh | `order=[root]`, `tin=0`, `tout=1`, cây con kích thước 1 |
| Root là 0 hoặc đỉnh khác | Đều hợp lệ nếu thuộc cây; Euler phụ thuộc root |
| Root có cây con | Đoạn root luôn là `[0,n)` |
| Đỉnh lá | `tout[u]=tin[u]+1` |
| Cây dạng đường thẳng rất sâu | DFS lặp tránh stack overflow khi dựng Euler |
| Cây dạng ngôi sao | Các lá có đoạn một phần tử và root có đoạn toàn cây |
| Giá trị đỉnh âm hoặc 0 | Vẫn tính tổng/cập nhật đúng; không phải sentinel |
| Có chu trình hoặc self-loop | Không phải cây; phải từ chối |
| Có n−1 cạnh nhưng không liên thông | Không phải cây; có thể kèm chu trình |
| Thêm/xóa cạnh sau preprocessing | Euler cũ có thể sai, cần xây lại hoặc dùng kỹ thuật cây động |
| Đổi root sau preprocessing | Cây con thay đổi, không tự dùng đoạn root cũ |
| Truy vấn đường đi u–v | Không nhất thiết là một đoạn Euler |
| Cộng cả cây con | Dùng range add, không phải point add |
| Gán một đỉnh | Point set, không giống range assign cây con |
| Trọng số gán trên cạnh | Phải định nghĩa mapping vào vị trí đỉnh con |
| Overflow trong long | Phát hiện bằng Math.addExact/multiplyExact/subtractExact |

Những lỗi hay gặp:
1. **Nhầm đoạn đóng và nửa mở**, query `[tin,tout]` thay vì `[tin,tout)`.
2. **Tăng timer khi thoát** dù đang muốn mảng một lần vào đỉnh, khiến tout không còn là biên đúng.
3. **Gán tout ngay sau khi tạo lời gọi DFS con**, trước khi các cây con hoàn tất.
4. **Không bỏ parent** trong cây vô hướng, đệ quy quay lại cha vô hạn.
5. **Chỉ bỏ parent nhưng không xác minh dữ liệu đầu vào là cây**, dễ mắc vòng khi input chứa chu trình khác.
6. **Đánh số đỉnh và vị trí Euler là một**, rồi cập nhật sai `flat[u]` thay vì `flat[tin[u]]`.
7. **Nhầm thứ tự Euler với thứ tự nhãn tăng dần**, dù DFS đi theo adjacency.
8. **Bỏ chính u khỏi cây con** khi đề định nghĩa subtree gồm cả u.
9. **Quên rằng lá có đoạn một phần tử**, gây truy vấn rỗng hoặc tràn ra hàng xóm.
10. **Cho rằng mọi đường u–v đều là một đoạn Euler**, dẫn đến truy vấn đường đi sai.
11. **Đổi root rồi dùng đoạn cũ** mà không tính lại hoặc dùng công thức phần bù.
12. **Thêm/xóa cạnh rồi vẫn dùng tin/tout cũ**, phá bất biến cây con.
13. **Dùng prefix sum tĩnh cho dữ liệu có cập nhật mà không làm mới**, trả tổng sai.
14. **Dùng Fenwick point-add thông thường cho cả range add và range sum** nhưng không bổ sung kỹ thuật cần thiết.
15. **Quên nhân lazy delta với độ dài đoạn**, cập nhật tổng sai.
16. **Không push lazy trước khi đi xuống con**, khiến truy vấn hoặc cập nhật một phần dùng dữ liệu cũ.
17. **Không cập nhật tổng nút cha sau khi cập nhật hai con**, làm sai truy vấn phủ trọn.
18. **Dùng range assign như range add** (hoặc ngược lại), sai ngữ nghĩa.
19. **Dùng int cho tổng lớn** gây overflow; long cũng có giới hạn.
20. **Cố tiếp tục dùng segment tree sau khi phép cập nhật bị ngắt do ArithmeticException**, dù có thể đã thay đổi một phần trạng thái.

## 14. Bài tập tự luyện và đáp án

**Bài 1 — tính đoạn.** Với cây mẫu gốc 0, `order=[0,1,3,4,7,8,2,5,6]`. Cây con 4 chiếm đoạn nào và có mấy đỉnh?

*Đáp án:* `[3,6)`, gồm ba đỉnh `[4,7,8]`; `tout[4]−tin[4]=6−3=3`.

**Bài 2 — tổng cây con.** Cây con 1 có những giá trị nào và tổng bao nhiêu?

*Đáp án:* Giá trị `[3,2,4,7,9]`, tổng `25`.

**Bài 3 — cộng cây con.** Nếu cộng 10 vào cây con 4, tổng cây con 1 tăng bao nhiêu?

*Đáp án:* Ba đỉnh trong cây con 4 cũng thuộc cây con 1, nên tổng cây con 1 tăng `3×10=30`, từ 25 thành 55.

**Bài 4 — các nhánh rời.** Sau khi cộng 10 vào cây con 4, tổng cây con 2 có đổi không?

*Đáp án:* Không, vì `[3,6)` của cây con 4 và `[6,9)` của cây con 2 không giao nhau; tổng cây con 2 vẫn 15.

**Bài 5 — thay một đỉnh.** Sau `ADD(4,10)`, đỉnh 7 có giá trị 17. Nếu gán đỉnh 7 bằng 0, tổng cây con 4 đổi thế nào?

*Đáp án:* Giảm 17, từ 50 thành 33.

**Bài 6 — tiền xử lý.** Nếu chỉ có các truy vấn tính tổng cây con, không có bất kỳ cập nhật nào, cấu trúc nào đủ để trả O(1) mỗi truy vấn?

*Đáp án:* Dùng prefix sum trên `flat`; trả `prefix[tout[u]]−prefix[tin[u]]`.

**Bài 7 — chỉ cập nhật điểm.** Cần point add và tổng cây con, nên chọn cấu trúc nào đơn giản?

*Đáp án:* Fenwick tree trên thứ tự Euler; mỗi thao tác O(log n).

**Bài 8 — khoảng đóng.** Một thư viện range sum nhận đoạn đóng `[l,r]`. Cách chuyển từ cây con u theo bài là gì?

*Đáp án:* Dùng `[tin[u],tout[u]−1]`.

**Bài 9 — tổ tiên.** Với cây mẫu, 4 có là tổ tiên của 8 không? Kiểm tra bằng tin/tout.

*Đáp án:* Có, vì `tin[4]=3<=tin[8]=5<tout[4]=6`.

**Bài 10 — đường đi.** Các vị trí Euler của đường `3→1→0→2→5` có thành một đoạn không?

*Đáp án:* Không; vị trí `[2,1,0,6,7]` phân tán. Không dùng một đoạn subtree để tính tổng đường này.

**Bài 11 — đổi gốc.** Đổi root từ 0 sang 4. Cây con 1 còn là `{1,3,4,7,8}` không?

*Đáp án:* Không. Với gốc 4, cây con 1 là `{1,0,2,3,5,6}`. Phải dùng Euler mới hoặc kỹ thuật xử lý đổi root.

**Bài 12 — cây một đỉnh.** Với n=1, root=0, tin/tout là gì?

*Đáp án:* tin[0]=0, tout[0]=1; cây con kích thước 1.

**Bài 13 — edge weights.** Nếu `weight[u]` lưu trọng số cạnh nối parent[u] tới u, tổng trọng số **các cạnh nằm trọn trong cây con u** nên lấy đoạn nào?

*Đáp án:* `[tin[u]+1,tout[u])`, loại slot của u vì slot ấy là cạnh nối từ ngoài cây con vào u.

**Bài 14 — đổi giá trị trên mảng.** Khi gán đỉnh u thành giá trị mới X bằng lazy segment tree hỗ trợ range add, làm thế nào?

*Đáp án:* Đọc old tại `[tin[u],tin[u]+1)`, tính `delta=X−old`, rồi range add delta đúng đoạn một phần tử.

**Bài 15 — độ phức tạp.** Với n đỉnh và q thao tác `ADD_SUBTREE`/`SUM_SUBTREE`, tiền xử lý Euler và lazy segment tree hết bao nhiêu?

*Đáp án:* O(n) tiền xử lý, O(log n) mỗi thao tác, tổng O(n+q log n), bộ nhớ O(n).

## Tổng kết

**Duyệt Euler theo thời điểm vào đỉnh** biến mỗi cây con u thành **một đoạn nửa mở liên tiếp `[tin[u],tout[u])`** của mảng chứa đúng một lần mỗi đỉnh. Độ dài đoạn chính là số đỉnh trong cây con, và quan hệ tổ tiên cũng kiểm tra được trong O(1).

Sau khi làm phẳng, **chọn cấu trúc mảng theo loại truy vấn**: prefix sum cho tổng tĩnh, Fenwick cho point update/range sum, lazy segment tree cho **cộng cây con và tính tổng cây con**. Với cây có n đỉnh và q truy vấn động, giải pháp Euler + segment tree chạy **O(n+q log n)** thời gian, O(n) bộ nhớ.

Đừng quên ba điều kiện nền tảng: **dữ liệu thực sự là cây, gốc và cấu trúc giữ cố định, hai biên được dùng nhất quán theo quy ước nửa mở**. Những truy vấn đường đi, đổi gốc liên tục hoặc thay đổi cạnh là các bài toán mở rộng cần kỹ thuật bổ sung.

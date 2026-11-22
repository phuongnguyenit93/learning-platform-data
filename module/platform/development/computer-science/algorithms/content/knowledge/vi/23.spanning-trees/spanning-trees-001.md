# Cây khung nhỏ nhất, rừng khung và điều kiện liên thông

> **Chủ đề:** Computer Science Algorithms → Cây khung (*Spanning Trees*).  
> **Trọng tâm:** Hiểu **khi nào cây khung tồn tại**, phân biệt cây khung (*spanning tree*) với **cây khung nhỏ nhất** (*minimum spanning tree — MST*), rừng khung (*spanning forest*) với **rừng khung nhỏ nhất** (*minimum spanning forest — MSF*), chứng minh quy tắc cạnh an toàn, xử lý đồ thị không liên thông, và cài đúng Kruskal/Prim trên đồ thị vô hướng có trọng số. Ví dụ sử dụng **Java 17+**, gồm chương trình chạy độc lập, stdout, bài tập và đối chiếu bằng vét cạn.

## 1. Từ đồ thị vô hướng đến cây khung

Cho đồ thị vô hướng `G=(V,E)` với `n=|V|` đỉnh và `m=|E|` cạnh. Cạnh `{u,v}` có trọng số `w(u,v)`, có thể âm, bằng 0 hoặc dương nếu đề bài không giới hạn.

Một **cây** là một đồ thị vô hướng **liên thông** và **không chứa chu trình**. Với `n>=1`, ba tính chất kinh điển tương đương khi đồ thị có đúng n đỉnh:

1. Liên thông và không có chu trình.
2. Liên thông và có đúng `n−1` cạnh.
3. Không có chu trình và có đúng `n−1` cạnh.

Một **cây khung** của G là một cây `T=(V,E_T)` dùng **toàn bộ đỉnh gốc** nhưng chỉ lấy những cạnh thuộc G:

- `V(T)=V(G)`.
- `E_T ⊆ E(G)`.
- T liên thông và không có chu trình.
- Với `n>=1`, `|E_T|=n−1`.

Từ “khung” nghĩa là **không bỏ đỉnh**. Cây khung có thể bỏ nhiều cạnh của G, nhưng không được bỏ một đỉnh nào, kể cả đỉnh ít cạnh.

### 1.1. Trọng số cây và bài toán MST

Với một cây khung T, tổng trọng số:

`weight(T) = Σ_(e∈E_T) w(e)`.

**Minimum Spanning Tree — MST** là một cây khung có **tổng trọng số nhỏ nhất** trong mọi cây khung của cùng đồ thị.

Không có yêu cầu “mỗi cạnh đều nhẹ nhất” hoặc “đường đi từ một gốc tới mọi đỉnh là ngắn nhất”. Mục tiêu là **tối thiểu tổng trọng số của toàn bộ tập cạnh nối tất cả đỉnh**.

Trong mạng cáp, đường ống hoặc hệ thống kết nối hai chiều, MST mô hình hóa việc kết nối đủ các điểm với **tổng chi phí xây dựng nhỏ nhất**, nếu chi phí có thể cộng theo cạnh và không có những ràng buộc thêm.

### 1.2. Cây khung có thể không duy nhất

Một đồ thị có thể có nhiều cây khung. Ngay cả MST cũng có thể có nhiều nghiệm cùng tổng trọng số.

Ví dụ tam giác ba cạnh đều trọng số 1: chọn bất kỳ **hai cạnh** nào cũng nối cả ba đỉnh không tạo chu trình, cho tổng 2. Vì thế có **ba MST** khác nhau.

Khi đề chỉ yêu cầu **một MST**, Kruskal/Prim có thể trả bất kỳ nghiệm tối ưu nào. Khi đề yêu cầu tất cả MST, số lượng MST hoặc thứ tự từ điển của cạnh, phải thiết kế thêm cơ chế riêng.

## 2. Điều kiện tồn tại cây khung: tính liên thông là bắt buộc

Với đồ thị vô hướng có **ít nhất một đỉnh**:

> **G có cây khung khi và chỉ khi G liên thông.**

### 2.1. Chứng minh chiều cần

Nếu G có một cây khung T, thì giữa hai đỉnh bất kỳ u và v có đường đi trong T vì T liên thông. Mọi cạnh của T cũng thuộc G, nên u và v có đường đi trong G. Vì vậy **G liên thông**.

### 2.2. Chứng minh chiều đủ

Giả sử G liên thông. Có thể bắt đầu từ một đỉnh và chạy DFS/BFS, mỗi khi phát hiện một đỉnh mới thì giữ lại cạnh đã dẫn tới nó.

- Mọi đỉnh đều được phát hiện, vì G liên thông.
- Mỗi đỉnh khác nguồn có đúng **một cạnh cha** khi lần đầu phát hiện.
- Các cạnh cha không tạo chu trình, vì mỗi cạnh nối một đỉnh đã thăm với một đỉnh **chưa thăm**.
- Có đúng `n−1` cạnh cha.

Những cạnh được chọn tạo thành một cây khung. Vì tập cây khung hữu hạn với đồ thị hữu hạn, cũng tồn tại cây khung có tổng trọng số nhỏ nhất: **MST tồn tại**.

### 2.3. Trường hợp n=1

Đồ thị chỉ có **một đỉnh** và không có cạnh vẫn được coi là **liên thông**. Cây khung duy nhất là chính đỉnh đó với **0 cạnh** và tổng trọng số **0**.

Đây là trường hợp rất dễ bị xử lý sai nếu code cứng nhắc đòi “đã chọn được ít nhất một cạnh”.

### 2.4. Trường hợp n=0

Một đồ thị **không có đỉnh** có quy ước khác nhau giữa tài liệu: “đồ thị rỗng có liên thông không?” hoặc “có cây khung rỗng không?” không phải lúc nào cũng được định nghĩa giống nhau.

**Quy ước lập trình của bài học:** với `n=0`, trả rừng rỗng có tổng chi phí 0, **số thành phần 0**, và `hasSpanningTree=false` vì không có cây với ít nhất một đỉnh. Với `n>=1`, kiểm tra đúng định lý `components==1`.

Một đề thi có thể quy định khác; khi đó phải tuân thủ **hợp đồng đầu vào/đầu ra của đề**, không áp mặc định quy ước này.

### 2.5. Nếu G không liên thông?

Nếu G có `k>=2` thành phần liên thông, không thể chọn cạnh của G để nối những thành phần đó, bởi **không có cạnh nào giữa chúng**. Vì vậy **không có cây khung cho toàn bộ G**, và cũng **không có MST toàn đồ thị**.

Không nên trả một cây nhỏ trong một thành phần rồi gọi đó là MST của toàn G. Có thể trả **rừng khung nhỏ nhất (MSF)**, gồm một MST cho **mỗi thành phần**.

## 3. Rừng khung và rừng khung nhỏ nhất

Một **rừng** là đồ thị vô hướng **không có chu trình**; mỗi thành phần liên thông của nó là một cây, trong đó một đỉnh đứng riêng cũng là một cây.

Với bài học này, **rừng khung** của G được định nghĩa chặt như sau:

- Chứa **mọi đỉnh của G**.
- Dùng **chỉ các cạnh thuộc G**.
- Không có chu trình.
- **Trong mỗi thành phần liên thông ban đầu của G**, những đỉnh đó được nối với nhau bằng **một cây** của rừng.

Điều kiện cuối phân biệt rừng khung đầy đủ với một **đồ thị con không chu trình nhưng chưa nối đủ**. Chẳng hạn “không lấy cạnh nào” là đồ thị con không chu trình, nhưng **không** là rừng khung đầy đủ nếu G có cạnh nối các đỉnh cần nối.

**Rừng khung nhỏ nhất — Minimum Spanning Forest, MSF** là rừng khung có tổng trọng số nhỏ nhất. Tương đương:

> Lấy một MST độc lập cho **mỗi thành phần liên thông** của G rồi hợp các cây lại.

Nếu G liên thông, MSF chỉ có **một cây**, chính là MST. Nếu G không liên thông, MSF có từ hai cây trở lên; mỗi đỉnh cô lập tạo **một cây một đỉnh, không cạnh, trọng số 0**.

### 3.1. Công thức số cạnh

Giả sử G có n đỉnh và k thành phần liên thông. Thành phần thứ i có `n_i` đỉnh. MST của thành phần đó có `n_i−1` cạnh. Do đó mọi rừng khung đầy đủ đều có:

`Σ_i(n_i−1) = Σ_i n_i−k = n−k` cạnh.

**Công thức nền tảng:**

`edgesInSpanningForest = n − components`.

Áp dụng kể cả khi một thành phần là đỉnh cô lập (`n_i=1`, có 0 cạnh). Với n=0 và k=0 theo quy ước, công thức cũng cho 0.

### 3.2. Liên thông, số cạnh và chu trình

Trên đồ thị vô hướng bất kỳ, chỉ biết `m=n−1` **không đủ** kết luận liên thông hay là cây nếu không kiểm thêm tính chu trình/liên thông.

Ví dụ n=4, các cạnh tạo tam giác giữa ba đỉnh (3 cạnh), đỉnh thứ tư cô lập: `m=3=n−1`, nhưng G **không liên thông** và có chu trình. Đây không phải cây.

Ngược lại, nếu một đồ thị **không có chu trình** và có đúng `n−1` cạnh với `n>=1`, nó liên thông. Nếu một đồ thị **liên thông** và có `n−1` cạnh, nó không có chu trình.

### 3.3. Công thức MSF từ thành phần

Giả sử các thành phần là `C_1,...,C_k`, và `MST(C_i)` là một cây khung nhỏ nhất của đồ thị cảm sinh trên thành phần i. Khi đó:

`weight(MSF(G)) = Σ_(i=1..k) weight(MST(C_i))`.

**Chứng minh:** mỗi rừng khung phải nối đủ đỉnh **bên trong từng thành phần**, và không có cạnh liên thông giữa các thành phần khác nhau để đánh đổi trọng số. Tối ưu tổng bằng tổng các bài toán tối ưu độc lập.

Không cần “bù” cạnh nhân tạo có trọng số cực lớn để ép đồ thị thành liên thông. Thêm cạnh ngoài G thay đổi bài toán.

## 4. Ví dụ có đỉnh cô lập, cạnh âm và self-loop

Xét đồ thị vô hướng có 7 đỉnh `0..6`, các cạnh:

| Cạnh | Trọng số | Vai trò |
|---|---:|---|
| 0—1 | 4 | Thành phần thứ nhất |
| 0—2 | 3 | Thành phần thứ nhất |
| 1—2 | 1 | Thành phần thứ nhất |
| 1—3 | 2 | Thành phần thứ nhất |
| 2—3 | 5 | Thành phần thứ nhất |
| 0—3 | 8 | Thành phần thứ nhất |
| 4—5 | −2 | Thành phần thứ hai |
| 1—1 | −100 | **Self-loop**, không được đưa vào rừng |
| 2—1 | 6 | **Cạnh song song** giữa 1 và 2, nặng hơn cạnh 1—2 trọng số 1 |

Đỉnh 6 không có cạnh.

Tập đỉnh tách thành **3 thành phần liên thông**:

- `{0,1,2,3}`.
- `{4,5}`.
- `{6}`.

Không có đường từ 0 tới 5 hoặc 6; vì thế **không tồn tại cây khung toàn bộ 7 đỉnh**.

### 4.1. MSF của ví dụ

Một MSF chọn các cạnh sau:

```text
4—5  trọng số −2
1—2  trọng số  1
1—3  trọng số  2
0—2  trọng số  3
```

Tổng trọng số:

`−2 + 1 + 2 + 3 = 4`.

Có đúng `7−3=4` cạnh và đúng 3 cây:

```text
Cây 1:
0 --(3)-- 2 --(1)-- 1 --(2)-- 3

Cây 2:
4 --(-2)-- 5

Cây 3:
6   (đỉnh cô lập)
```

Cây 1 có tổng 6. Cây 2 có tổng −2. Cây 3 có tổng 0. Vì vậy MSF toàn đồ thị có tổng **4**.

### 4.2. Self-loop có trọng số âm rất nhỏ vẫn không được chọn

Cạnh `1—1` trọng số −100 không nối thêm đỉnh nào. Nó tạo một chu trình dài 1, nên **không thuộc bất kỳ cây khung/rừng khung nào**, dù trọng số rất hấp dẫn.

Đây là khác biệt giữa tối thiểu tổng trọng số **trên tập cạnh bất kỳ** và tối thiểu tổng trọng số **của rừng khung hợp lệ**.

### 4.3. Cạnh song song được phép trong mô hình multigraph

Hai cạnh cùng cặp đỉnh 1 và 2 nhưng trọng số 1 và 6 là **hai cạnh khác nhau**. Khi chọn cạnh 1—2 trọng số 1, chọn tiếp cạnh 2—1 trọng số 6 tạo chu trình độ dài 2 trong multigraph; DSU sẽ từ chối vì hai đầu đã chung thành phần.

Nếu cả hai cạnh song song có cùng trọng số nhẹ nhất, có thể tạo **nhiều MST khác nhau** do chọn cạnh nào; nếu đề chỉ xét tập cặp đỉnh mà không phân biệt ID cạnh, cách đếm nghiệm phải định nghĩa tương ứng.

## 5. Hai tính chất cốt lõi: lát cắt và chu trình

Tại sao có thể chọn cạnh theo trọng số tăng mà vẫn tối ưu? Câu trả lời nằm ở **cut property** và **cycle property**.

### 5.1. Lát cắt (*cut*)

Một lát cắt chia tập đỉnh của một thành phần thành hai nhóm không rỗng `(S,V\S)`. Một cạnh được gọi là **đi qua lát cắt** nếu một đầu thuộc S và đầu kia thuộc V\S.

Một cạnh **nhẹ nhất đi qua lát cắt** (*light edge*) có trọng số nhỏ nhất trong tất cả các cạnh vượt cắt.

**Tính chất lát cắt:** với một đồ thị vô hướng liên thông, **một cạnh nhẹ nhất của một lát cắt luôn thuộc ít nhất một MST**. Nếu một tập cạnh A đã được chọn và lát cắt **tôn trọng A** (không cạnh nào của A vượt cắt), một cạnh nhẹ nhất vượt cắt có thể được thêm vào A một cách **an toàn** trong quá trình xây MST.

**Cẩn trọng khi có cạnh hòa trọng số:** nói “mọi cạnh nhẹ nhất đều bắt buộc thuộc **mọi** MST” là sai. Chỉ có thể khẳng định cạnh nhẹ nhất là **an toàn cho ít nhất một MST phù hợp**. Nếu cạnh đó là **duy nhất nhẹ nhất** vượt cắt thì nó thuộc **mọi MST**.

### 5.2. Chứng minh bằng phép đổi cạnh (*exchange argument*)

Chọn một MST T mà ta muốn điều chỉnh để chứa cạnh nhẹ nhất `e=(u,v)` vượt cắt.

- Nếu T đã có e, xong.
- Nếu chưa có e, thêm e vào T tạo đúng **một chu trình**.
- Chu trình phải có ít nhất một cạnh khác `f` cũng vượt lát cắt, vì đi từ u thuộc S sang v ngoài S rồi quay về phải cắt qua biên nhóm.
- Vì e nhẹ nhất vượt cắt: `w(e) <= w(f)`.
- Bỏ f khỏi chu trình, giữ e, thu một cây khung T' với:

  `weight(T') = weight(T) + w(e) − w(f) <= weight(T)`.

Vì T vốn tối ưu, T' cũng tối ưu, và T' chứa e. Đó là lý do có thể chọn e mà không làm mất khả năng hoàn thành tới một MST.

### 5.3. Tính chất chu trình (*cycle property*)

Trong một chu trình, nếu một cạnh e là **duy nhất có trọng số lớn nhất**, e **không thể thuộc bất kỳ MST nào**.

Chứng minh: nếu một MST T chứa e, bỏ e làm T tách hai phần. Những cạnh khác của chu trình tạo một đường nối hai đầu e; trên đường ấy có cạnh f vượt hai phần và `w(f)<w(e)`. Thay e bằng f cho cây có tổng trọng số nhỏ hơn, mâu thuẫn tối ưu.

Nếu nhiều cạnh cùng là lớn nhất, **không** được khẳng định từng cạnh lớn nhất đều bị cấm trong tất cả MST. Có thể có nghiệm dùng cạnh này và nghiệm khác dùng cạnh kia.

### 5.4. Cạnh cầu và lát cắt duy nhất

**Cạnh cầu** (*bridge*) là cạnh mà bỏ đi khiến số thành phần liên thông tăng. Với thành phần ban đầu có ít nhất hai đỉnh, mọi cây khung của thành phần **phải chứa cạnh cầu** đó: nếu không, hai phía của cầu không có đường nối.

Điều này đúng dù cầu có trọng số lớn, nhỏ hay âm. Tối ưu MST không thể bỏ một cạnh bắt buộc để đổi lấy cạnh “rẻ hơn” vốn không tồn tại qua lát cắt.

## 6. Kruskal: sắp cạnh và hợp nhất thành phần

**Kruskal** bắt đầu từ rừng n cây đơn đỉnh. Nó xét các cạnh theo **trọng số tăng dần** và chọn cạnh nếu cạnh đó nối **hai thành phần khác nhau** của rừng đang xây.

Pseudocode:

```text
Kruskal(G):
    create DSU with n singleton components
    selected = empty
    total = 0

    sort all edges by weight ascending
    for edge (u,v,w) in sorted edges:
        if DSU.find(u) != DSU.find(v):
            DSU.union(u,v)
            selected.add(edge)
            total += w

    components = DSU.componentCount()
    return selected, total, components
```

Chỉ thêm cạnh nối hai tập khác nhau nên **không tạo chu trình**. Mỗi lần thêm cạnh, số thành phần trong DSU giảm đúng 1.

Sau khi xét hết các cạnh, DSU mô tả đúng **các thành phần liên thông của đồ thị gốc**, và rừng đã chọn nối đủ từng thành phần. Vì mỗi cạnh được chọn theo quy tắc cạnh nhẹ nhất qua một lát cắt phù hợp, rừng có trọng số tối thiểu: **MSF**.

### 6.1. DSU (Disjoint Set Union) là gì?

DSU, còn gọi là Union–Find, quản lý các nhóm đỉnh đã nối trong rừng:

- `find(x)`: tìm đại diện của nhóm chứa x.
- `union(a,b)`: nếu hai đại diện khác nhau, gộp nhóm và trả `true`; nếu cùng nhóm, trả `false`.
- `components`: số nhóm hiện tại.

Hai tối ưu kinh điển:

1. **Path compression:** khi tìm đại diện, cập nhật đường parent tới đại diện để các lần tìm sau nhanh hơn.
2. **Union by size/rank:** gắn cây DSU nhỏ dưới cây lớn để tránh độ sâu lớn.

Với cả hai kỹ thuật, chuỗi thao tác có chi phí **gần hằng số trung bình theo nghĩa amortized**, thường viết `O(α(n))` mỗi thao tác, trong đó α là hàm Ackermann ngược tăng cực chậm.

DSU **không trực tiếp lưu cạnh MST**. Vì vậy code cần giữ danh sách những cạnh union thành công để in kết quả.

### 6.2. Bất biến của Kruskal

Sau khi xét một tiền tố của danh sách cạnh đã sort:

- Những cạnh chọn được là một **rừng**.
- DSU chính xác biểu diễn liên thông trong rừng ấy.
- Tập cạnh đã chọn **có thể được mở rộng** thành một MST của mỗi thành phần gốc (tính chất cạnh an toàn).
- Nếu union thành công, `chosenEdgeCount` tăng 1 và `components` giảm 1.

Kết thúc, không còn cạnh của G nối hai thành phần DSU khác nhau. Nếu có, Kruskal đã xét nó và phải union khi hai đầu còn khác nhóm, mâu thuẫn. Vì vậy rừng bao phủ trọn vẹn mỗi thành phần gốc.

### 6.3. Kiểm tra liên thông ngay bằng Kruskal

Sau khi hoàn tất:

- `components==1` với `n>=1` ⇒ G liên thông, rừng chính là **MST** toàn đồ thị.
- `components>1` ⇒ G không liên thông, chỉ có **MSF**, không có MST toàn đồ thị.
- `n==0` ⇒ theo quy ước bài học, MSF rỗng, `components=0`, `hasSpanningTree=false`.

Ngoài ra:

`selectedEdgeCount = n − components`.

Đây là invariant kiểm thử rất hữu ích. Nếu không đúng thì code có thể đã thêm cạnh tạo chu trình, quên đỉnh cô lập, hoặc tính sai số thành phần.

## 7. Java 17 — Kruskal trả cả MSF và điều kiện liên thông

Lưu thành **KruskalMinimumSpanningForestDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;

public class KruskalMinimumSpanningForestDemo {
    record Edge(int u, int v, long weight, int inputIndex) {}

    record Result(long totalWeight, int components,
                  boolean hasSpanningTree, List<Edge> selected) {}

    static final class DSU {
        final int[] parent;
        final int[] size;
        int components;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;

            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            if (parent[x] != x) {
                parent[x] = find(parent[x]); // Path compression.
            }
            return parent[x];
        }

        boolean union(int a, int b) {
            int ra = find(a);
            int rb = find(b);

            if (ra == rb) {
                return false;
            }
            if (size[ra] < size[rb]) {
                int temp = ra;
                ra = rb;
                rb = temp;
            }

            parent[rb] = ra;
            size[ra] += size[rb];
            components--;
            return true;
        }
    }

    static Result solve(int n, Edge[] edges) {
        Objects.requireNonNull(edges, "edges");
        if (n < 0) {
            throw new IllegalArgumentException("Negative n");
        }

        for (Edge e : edges) {
            Objects.requireNonNull(e, "edge");

            if (e.u() < 0 || e.u() >= n
                    || e.v() < 0 || e.v() >= n) {
                throw new IllegalArgumentException("Endpoint out of range");
            }
        }

        Edge[] sorted = edges.clone();
        Arrays.sort(sorted, Comparator
                .comparingLong(Edge::weight)
                .thenComparingInt(Edge::inputIndex));

        DSU dsu = new DSU(n);
        List<Edge> chosen = new ArrayList<>();
        long weight = 0L;

        for (Edge e : sorted) {
            if (dsu.union(e.u(), e.v())) {
                chosen.add(e);
                weight = Math.addExact(weight, e.weight());
            }
        }

        boolean spanningTree = n >= 1 && dsu.components == 1;
        return new Result(weight, dsu.components,
                spanningTree, List.copyOf(chosen));
    }

    static Edge[] example() {
        return new Edge[]{
            new Edge(0, 1, 4, 0),
            new Edge(0, 2, 3, 1),
            new Edge(1, 2, 1, 2),
            new Edge(1, 3, 2, 3),
            new Edge(2, 3, 5, 4),
            new Edge(0, 3, 8, 5),
            new Edge(4, 5, -2, 6),
            new Edge(1, 1, -100, 7), // Loop: union false.
            new Edge(2, 1, 6, 8)     // Cạnh song song nặng hơn.
        };
    }

    static String formatEdges(List<Edge> edges) {
        StringJoiner s = new StringJoiner(", ", "[", "]");
        for (Edge e : edges) {
            s.add("(" + e.u() + "-" + e.v() + ":" + e.weight() + ")");
        }
        return s.toString();
    }

    public static void main(String[] args) {
        Result r = solve(7, example());

        System.out.println("Components: " + r.components());
        System.out.println("Has spanning tree: " + r.hasSpanningTree());
        System.out.println("MSF weight: " + r.totalWeight());
        System.out.println("Edges: " + formatEdges(r.selected()));
        System.out.println("Edges count: " + r.selected().size());

        Result singleton = solve(1, new Edge[0]);
        System.out.println("Singleton connected: "
                + singleton.hasSpanningTree());
        System.out.println("Singleton cost: "
                + singleton.totalWeight());

        Result isolated = solve(3, new Edge[0]);
        System.out.println("No-edge components: "
                + isolated.components());

        Edge[] firstComponent = Arrays.copyOf(example(), 6);
        System.out.println("Connected graph MST cost: "
                + solve(4, firstComponent).totalWeight());
    }
}
```

Chạy với Java 17 trở lên:

```bash
javac -encoding UTF-8 KruskalMinimumSpanningForestDemo.java
java KruskalMinimumSpanningForestDemo
```

Stdout:

```text
Components: 3
Has spanning tree: false
MSF weight: 4
Edges: [(4-5:-2), (1-2:1), (1-3:2), (0-2:3)]
Edges count: 4
Singleton connected: true
Singleton cost: 0
No-edge components: 3
Connected graph MST cost: 6
```

### 7.1. Vì sao self-loop âm bị bỏ qua?

Khi xét cạnh `(1,1,-100)`, `find(1)==find(1)` nên `union(1,1)` trả false. Cạnh không được thêm, dù được sort lên đầu vì trọng số âm. Rừng vẫn không có chu trình.

### 7.2. Tại sao một cạnh có hướng ngược được coi là cùng kiểu vô hướng?

Đối với DSU, `union(1,2)` và `union(2,1)` thử nối cùng hai nhóm. Cạnh `(2,1,6)` là một **cạnh song song khác** trong input, không làm xuất hiện hướng đi một chiều. Hai đầu là đối xứng trong phép nối.

### 7.3. Tính chính xác số học

`weight` là `long`, và `Math.addExact` phát hiện nếu tổng vượt miền `long` thay vì tràn im lặng. Nếu bài cho giá trị hoặc số cạnh khiến tổng thật có thể vượt `long`, cần đổi sang `BigInteger`.

Comparator dùng `comparingLong`, không dùng phép trừ `(int)(a.weight-b.weight)` vì có thể tràn và vi phạm quy tắc sắp xếp.

### 7.4. Độ phức tạp Kruskal

Gọi `V=n`, `E=m`. Với cách cài có sort toàn bộ cạnh:

- Khởi tạo DSU: `O(V)`.
- Sort: `O(E log E)`, với E=0 thao tác sort rỗng.
- Kiểm tra/hợp nhất các cạnh: `O(E α(V))` amortized; có thể coi chi phí DSU gần hằng số trong thực hành.
- Tổng: `O(V + E log E + E α(V))`.
- Bộ nhớ: `O(V+E)` cho DSU, mảng cạnh sort copy và danh sách chọn.

Với đồ thị đơn không có cạnh song song, `E<=V(V−1)/2`, thường viết `O(E log V)` cho phần sorting khi V đủ lớn. Công thức `O(E log E)` vẫn rõ ràng và phù hợp multigraph có rất nhiều cạnh song song.

## 8. Prim: mở rộng cây từ đỉnh gốc

**Prim** chọn cạnh nhẹ nhất **đi ra từ tập đỉnh đã đưa vào cây hiện tại** sang một đỉnh chưa thuộc cây.

Với đồ thị liên thông:

1. Chọn bất kỳ đỉnh gốc r.
2. Đánh dấu r thuộc cây.
3. Trong các cạnh có một đầu đã thuộc cây và một đầu chưa thuộc cây, lấy cạnh nhẹ nhất.
4. Thêm đỉnh mới cùng cạnh nối vào cây.
5. Lặp cho tới khi mọi đỉnh thuộc cây.

Mỗi cạnh được chọn là một **cạnh nhẹ nhất vượt lát cắt giữa tập đã chọn và tập chưa chọn**, nên an toàn theo cut property.

### 8.1. Prim thường được giới thiệu cho MST liên thông

Nếu chỉ chạy Prim từ đỉnh 0 trên **đồ thị không liên thông**, thuật toán **chỉ duyệt thành phần chứa 0**. Nó không thể đến các thành phần khác, và nếu cứ gọi kết quả là MST toàn đồ thị thì sai.

Để tạo **MSF** bằng Prim, thêm vòng ngoài:

```text
for root = 0 .. n-1:
    if root chưa được thăm:
        bắt đầu một cây mới từ root
        mở rộng cây bằng Prim cho tới khi heap hết
```

Vòng ngoài xử lý cả **đỉnh cô lập**: một root không có cạnh vẫn đóng góp **một cây đơn đỉnh**, tăng số thành phần lên 1 mà không thêm cạnh/trọng số.

### 8.2. Prim và Kruskal khác nhau ở trạng thái

- **Kruskal:** xét cạnh toàn cục theo thứ tự tăng; DSU duy trì nhiều cây cùng lúc và union khi an toàn.
- **Prim:** tập trung phát triển **một cây** cho tới khi hết đỉnh có thể tới; priority queue duy trì cạnh ứng viên vượt biên cây.
- Cả hai dựa trên **cut property**, không yêu cầu trọng số không âm.
- Trên đồ thị có MST không duy nhất, hai thuật toán có thể chọn **tập cạnh khác nhau**, nhưng tổng trọng số MST/MSF đều tối ưu.

### 8.3. Prim dùng priority queue dạng lazy

Thay vì cập nhật giảm khóa của từng đỉnh, ta có thể đẩy nhiều **cạnh ứng viên** vào `PriorityQueue`.

Khi pop cạnh:

- Nếu đỉnh đích **đã nằm trong cây hiện tại**, cạnh là stale/không thêm được ⇒ bỏ qua.
- Nếu đỉnh đích **chưa thuộc cây**, chọn cạnh đó, đánh dấu đích, rồi đẩy các cạnh đi ra từ đích tới đỉnh chưa thăm.

Với đồ thị vô hướng, danh sách kề có **hai cung** cho mỗi cạnh `{u,v}`; nhưng khi thêm cạnh ứng viên từ một đỉnh đã thăm, chỉ đẩy sang đỉnh **chưa thăm**, tránh đưa vòng lặp tự thân vào heap.

## 9. Java 17 — Prim nhiều thành phần, có đỉnh cô lập

Lưu thành **PrimMinimumSpanningForestDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.StringJoiner;

public class PrimMinimumSpanningForestDemo {
    record Edge(int u, int v, long weight) {}
    record Arc(int to, long weight, int inputIndex) {}
    record Candidate(int from, int to, long weight, int inputIndex) {}
    record Chosen(int from, int to, long weight) {}

    record Result(long totalWeight, int components,
                  boolean hasSpanningTree, List<Integer> roots,
                  List<Chosen> selected) {}

    static void addCandidates(
            int from, boolean[] visited,
            List<List<Arc>> graph, PriorityQueue<Candidate> heap) {
        for (Arc arc : graph.get(from)) {
            if (!visited[arc.to()]) {
                heap.add(new Candidate(from, arc.to(),
                        arc.weight(), arc.inputIndex()));
            }
        }
    }

    static Result solve(int n, Edge[] edges) {
        Objects.requireNonNull(edges, "edges");
        if (n < 0) {
            throw new IllegalArgumentException("Negative n");
        }

        List<List<Arc>> graph = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            graph.add(new ArrayList<>());
        }

        for (int i = 0; i < edges.length; i++) {
            Edge e = Objects.requireNonNull(edges[i], "edge");

            if (e.u() < 0 || e.u() >= n
                    || e.v() < 0 || e.v() >= n) {
                throw new IllegalArgumentException("Invalid endpoint");
            }

            // Self-loop không giúp nối một đỉnh mới.
            if (e.u() == e.v()) {
                continue;
            }

            // Đồ thị vô hướng: thêm cả hai chiều.
            graph.get(e.u()).add(new Arc(e.v(), e.weight(), i));
            graph.get(e.v()).add(new Arc(e.u(), e.weight(), i));
        }

        PriorityQueue<Candidate> heap = new PriorityQueue<>(
                Comparator.comparingLong(Candidate::weight)
                        .thenComparingInt(Candidate::to)
                        .thenComparingInt(Candidate::from)
                        .thenComparingInt(Candidate::inputIndex));

        boolean[] visited = new boolean[n];
        List<Integer> roots = new ArrayList<>();
        List<Chosen> chosen = new ArrayList<>();
        long totalWeight = 0L;

        for (int root = 0; root < n; root++) {
            if (visited[root]) {
                continue;
            }

            roots.add(root);
            visited[root] = true;
            addCandidates(root, visited, graph, heap);

            // Heap cạn khi đã duyệt hết thành phần của root.
            while (!heap.isEmpty()) {
                Candidate candidate = heap.remove();
                int to = candidate.to();

                if (visited[to]) {
                    continue;
                }

                visited[to] = true;
                chosen.add(new Chosen(
                        candidate.from(), to, candidate.weight()));
                totalWeight = Math.addExact(
                        totalWeight, candidate.weight());

                addCandidates(to, visited, graph, heap);
            }
        }

        int components = roots.size();
        boolean spanningTree = n >= 1 && components == 1;

        return new Result(totalWeight, components,
                spanningTree, List.copyOf(roots), List.copyOf(chosen));
    }

    static Edge[] example() {
        return new Edge[]{
            new Edge(0, 1, 4),
            new Edge(0, 2, 3),
            new Edge(1, 2, 1),
            new Edge(1, 3, 2),
            new Edge(2, 3, 5),
            new Edge(0, 3, 8),
            new Edge(4, 5, -2),
            new Edge(1, 1, -100),
            new Edge(2, 1, 6)
        };
    }

    static String show(List<Chosen> chosen) {
        StringJoiner s = new StringJoiner(", ", "[", "]");
        for (Chosen e : chosen) {
            s.add("(" + e.from() + "-" + e.to()
                    + ":" + e.weight() + ")");
        }
        return s.toString();
    }

    public static void main(String[] args) {
        Result r = solve(7, example());

        System.out.println("Prim component roots: " + r.roots());
        System.out.println("Prim components: " + r.components());
        System.out.println("Prim MSF weight: " + r.totalWeight());
        System.out.println("Prim edges: " + show(r.selected()));
        System.out.println("Has spanning tree: "
                + r.hasSpanningTree());

        Edge[] oneComponent = Arrays.copyOf(example(), 6);
        System.out.println("Connected n=4 MST weight: "
                + solve(4, oneComponent).totalWeight());
        System.out.println("No-edge roots: "
                + solve(3, new Edge[0]).roots());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PrimMinimumSpanningForestDemo.java
java PrimMinimumSpanningForestDemo
```

Stdout:

```text
Prim component roots: [0, 4, 6]
Prim components: 3
Prim MSF weight: 4
Prim edges: [(0-2:3), (2-1:1), (1-3:2), (4-5:-2)]
Has spanning tree: false
Connected n=4 MST weight: 6
No-edge roots: [0, 1, 2]
```

### 9.1. Giải thích thứ tự cạnh của Prim

Bắt đầu root 0:

1. Trong các cạnh đi ra từ 0, nhẹ nhất là `0—2` trọng số 3.
2. Khi đã có `{0,2}`, cạnh nhẹ nhất vượt cắt là `2—1` trọng số 1.
3. Khi có `{0,1,2}`, cạnh nhẹ nhất để nối 3 là `1—3` trọng số 2.
4. Heap cạn, cây đầu tiên có trọng số 6.
5. Root chưa thăm tiếp theo là 4, chọn `4—5` trọng số −2.
6. Root cuối là 6, không có cạnh nào, tạo cây một đỉnh.

Do đó có 3 root thành phần, 4 cạnh chọn và tổng chi phí 4.

Kruskal có thể chọn cùng các **cạnh vô hướng** nhưng theo thứ tự trọng số tăng toàn cục, nên thứ tự xuất list khác Prim. Không nên so sánh hai list theo thứ tự chuỗi rồi kết luận thuật toán sai.

### 9.2. Độ phức tạp Prim lazy

Khi dùng danh sách kề và heap cạnh:

- Tạo adjacency: `O(V+E)` thời gian/bộ nhớ.
- Mỗi cạnh vô hướng có hai cung trong danh sách kề; với quy tắc chỉ enqueue cạnh tới đỉnh chưa thăm, mỗi cạnh được đưa vào heap tối đa một lần khi đầu thứ nhất của nó trở thành visited, ngoại trừ loop được bỏ.
- Có thể có `O(E)` entry trong heap ⇒ thao tác heap `O(log(E+1))`.
- Tổng thời gian `O(V+E log(E+1))`.
- Bộ nhớ `O(V+E)` cho adjacency, visited, heap và tập cạnh chọn.

Với **đồ thị đơn**, vì `E<=V²`, cách viết thường gặp là `O(E log V)` (cộng khởi tạo V). Với multigraph có nhiều cạnh song song, giữ công thức `log E` rõ ràng.

Một biến thể Prim với mảng `minEdge[v]` và heap giảm khóa có thể có cách phân tích khác. Dù là biến thể nào, **không tự coi chi phí heap bằng hằng số**.

## 10. Kiểm chứng bằng vét cạn trên đồ thị nhỏ

Kruskal và Prim đều dựa vào cut property. Khi kiểm thử code, nên dùng thêm một **oracle độc lập**: vét cạn tất cả các tập cạnh nhỏ.

Với n đỉnh, m cạnh và k thành phần liên thông gốc:

1. Tính `k` từ **toàn bộ cạnh gốc**.
2. Mỗi rừng khung đầy đủ phải có chính xác `n−k` cạnh.
3. Duyệt các tập con cạnh có đúng `n−k` phần tử.
4. Với mỗi tập con, dùng DSU độc lập để kiểm tra **không chu trình**.
5. Nếu không chu trình và số thành phần sau chọn bằng k, tập con là rừng khung hợp lệ.
6. Tính tổng trọng số; giữ tổng nhỏ nhất và đếm có bao nhiêu rừng khung cùng đạt tổng đó.

Cách này có chi phí **hàm mũ theo m**, chỉ dùng làm oracle cho đồ thị **rất nhỏ**; không thay thế Kruskal/Prim cho bài thật.

### 10.1. Tại sao điều kiện `n−k` và không chu trình đủ?

Nếu chọn những cạnh từ G và tập chọn không chu trình, số thành phần của tập chọn là:

`n−selectedEdgeCount`.

Nếu số cạnh là `n−k`, rừng chọn có đúng k thành phần. Vì các cạnh chọn đều thuộc G, **một thành phần của rừng không thể chứa đỉnh từ hai thành phần khác nhau của G**. Nếu rừng có đúng k thành phần — bằng số thành phần gốc — thì mỗi thành phần gốc đã được nối trọn thành **một cây**.

Vì vậy có thể kiểm tra rừng khung đầy đủ bằng điều kiện `acyclic && selectedEdgeCount==n−k`, cùng ràng buộc cạnh được chọn thuộc G. Trong mã vẫn có kiểm tra số thành phần cuối để tăng tính rõ ràng.

### 10.2. Các cạnh bằng trọng số và nhiều MST

Xét đồ thị bốn đỉnh:

```text
0—1 : 1
1—2 : 1
0—2 : 1
1—3 : 2
2—3 : 2
```

Trong tam giác giữa 0,1,2, ta phải chọn **hai trong ba** cạnh trọng số 1: có 3 cách.

Để nối đỉnh 3, chọn một trong hai cạnh `1—3` hoặc `2—3` trọng số 2: có 2 cách.

Có chính xác:

`3×2 = 6 MST`,

mỗi MST có tổng trọng số:

`1+1+2=4`.

**Kết luận:** một thuật toán chỉ trả một trong 6 nghiệm ấy vẫn đúng nếu đề chỉ hỏi một MST. Đếm MST đòi thuật toán bổ sung, và không phải chỉ “đếm số tie trong lúc sort”.

## 11. Java 17 — oracle nhỏ và đếm số rừng khung nhỏ nhất

Lưu thành **MinimumSpanningForestBruteOracleDemo.java**:

```java
import java.util.Objects;

public class MinimumSpanningForestBruteOracleDemo {
    record Edge(int u, int v, long weight) {}

    record Analysis(int components, long minimumWeight,
                    long minimumForests, long validForests) {}

    static final class DSU {
        int[] parent;
        int[] size;
        int components;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;

            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            while (parent[x] != x) {
                parent[x] = parent[parent[x]];
                x = parent[x];
            }
            return x;
        }

        boolean union(int a, int b) {
            int x = find(a);
            int y = find(b);
            if (x == y) {
                return false;
            }
            if (size[x] < size[y]) {
                int tmp = x;
                x = y;
                y = tmp;
            }
            parent[y] = x;
            size[x] += size[y];
            components--;
            return true;
        }
    }

    static Analysis bruteForce(int n, Edge[] edges) {
        Objects.requireNonNull(edges, "edges");

        if (n < 0 || edges.length > 20) {
            throw new IllegalArgumentException(
                    "Small graphs only: n>=0, m<=20");
        }

        DSU original = new DSU(n);
        for (Edge edge : edges) {
            Objects.requireNonNull(edge, "edge");

            if (edge.u() < 0 || edge.u() >= n
                    || edge.v() < 0 || edge.v() >= n) {
                throw new IllegalArgumentException("Invalid endpoint");
            }
            original.union(edge.u(), edge.v());
        }

        int originalComponents = original.components;
        int neededEdges = n - originalComponents;

        boolean found = false;
        long best = 0L;
        long optimalCount = 0L;
        long validCount = 0L;

        long limits = 1L << edges.length;
        for (long mask = 0; mask < limits; mask++) {
            if (Long.bitCount(mask) != neededEdges) {
                continue;
            }

            DSU selected = new DSU(n);
            boolean acyclic = true;
            long total = 0L;

            for (int i = 0; i < edges.length; i++) {
                if ((mask & (1L << i)) == 0L) {
                    continue;
                }

                Edge edge = edges[i];
                if (!selected.union(edge.u(), edge.v())) {
                    acyclic = false;
                    break;
                }
                total = Math.addExact(total, edge.weight());
            }

            if (!acyclic || selected.components != originalComponents) {
                continue;
            }

            validCount++;
            if (!found || total < best) {
                found = true;
                best = total;
                optimalCount = 1L;
            } else if (total == best) {
                optimalCount++;
            }
        }

        if (!found) {
            throw new IllegalStateException(
                    "Every finite graph has a spanning forest");
        }

        return new Analysis(originalComponents, best,
                optimalCount, validCount);
    }

    public static void main(String[] args) {
        Edge[] tied = {
            new Edge(0, 1, 1),
            new Edge(1, 2, 1),
            new Edge(0, 2, 1),
            new Edge(1, 3, 2),
            new Edge(2, 3, 2)
        };
        Analysis a = bruteForce(4, tied);
        System.out.println("Equal-weight graph: components="
                + a.components() + ", optimum=" + a.minimumWeight()
                + ", min forests=" + a.minimumForests());
        System.out.println("Valid spanning trees: "
                + a.validForests());

        Edge[] stillUnique = {
            new Edge(0, 1, 1),
            new Edge(1, 2, 1),
            new Edge(0, 2, 2)
        };
        System.out.println("Repeated 1s do not force non-uniqueness: "
                + bruteForce(3, stillUnique).minimumForests());

        Edge[] disconnected = {
            new Edge(0, 1, -3),
            new Edge(2, 3, 4)
        };
        Analysis b = bruteForce(4, disconnected);
        System.out.println("Disconnected: components=" + b.components()
                + ", optimum=" + b.minimumWeight()
                + ", min forests=" + b.minimumForests());

        Analysis single = bruteForce(1, new Edge[0]);
        System.out.println("Singleton: components="
                + single.components() + ", optimum="
                + single.minimumWeight() + ", min forests="
                + single.minimumForests());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MinimumSpanningForestBruteOracleDemo.java
java MinimumSpanningForestBruteOracleDemo
```

Stdout:

```text
Equal-weight graph: components=1, optimum=4, min forests=6
Valid spanning trees: 8
Repeated 1s do not force non-uniqueness: 1
Disconnected: components=2, optimum=1, min forests=1
Singleton: components=1, optimum=0, min forests=1
```

### 11.1. Vì sao tổng số spanning tree hợp lệ là 8?

Ở đồ thị 4 đỉnh có 5 cạnh của ví dụ tied, cần chọn đúng **3 cạnh** để thành cây. Có `C(5,3)=10` tổ hợp ba cạnh.

- Chọn cả ba cạnh của tam giác 0–1–2 tạo chu trình, đồng thời không nối đỉnh 3 ⇒ không hợp lệ.
- Chọn cả ba cạnh `0—1`, `1—3`, `2—3` thì hợp lệ nhưng tổng lớn hơn optimum.
- Tổng cộng có **8 cây khung hợp lệ**; trong số này **6 cây** có tổng bằng 4.

Mã không suy luận bằng công thức cố định: nó thật sự thử mọi mask, bỏ tập có chu trình hoặc chưa nối đủ thành phần.

### 11.2. Lỗi đếm do cạnh song song

Nếu multigraph có hai cạnh song song cùng hai đầu và cùng trọng số, chương trình coi chúng là **hai lựa chọn cạnh riêng** vì chúng nằm ở hai chỉ số input khác nhau. Nếu đề định nghĩa “hai MST chọn cùng cặp đỉnh được xem là một” thì kết quả đếm phải chuẩn hóa theo ngữ nghĩa đề.

### 11.3. Độ phức tạp oracle

Với m cạnh, có `2^m` mask, mỗi mask kiểm tối đa m cạnh (DSU). Một chặn trên dễ hiểu:

- Thời gian `O(2^m·(m α(n)+n))` theo cách xây DSU mới ở mỗi mask.
- Bộ nhớ phụ `O(n+m)` ngoài input, khi chỉ giữ optimum và số lượng; mỗi lần xét một mask được xử lý tuần tự.

Giới hạn `m<=20` chỉ nhằm **không vô ý dùng brute force lên đồ thị lớn**. Nó không phải giới hạn toán học của việc tồn tại MSF.

## 12. Vì sao Kruskal và Prim tìm cùng trọng số?

Hai thuật toán dùng cùng nguyên lý cạnh an toàn nhưng duyệt khác nhau:

- Kruskal chọn cạnh nhẹ nhất **toàn cục trong những cạnh chưa xét**, miễn nó nối hai nhóm DSU khác nhau.
- Prim chọn cạnh nhẹ nhất **vượt cắt của một cây đang phát triển**.

Mỗi cạnh được chọn đều có thể chứng minh thuộc một MST phù hợp với lựa chọn trước đó. Sau khi thêm đủ `n−k` cạnh, tập chọn là MSF, nên cả hai có tổng trọng số bằng giá trị optimum duy nhất về mặt số học.

Nếu các trọng số khác nhau và MST duy nhất, hai thuật toán buộc chọn **cùng tập cạnh** (dù thứ tự khác). Nếu có nhiều MST đồng tối ưu, tập cạnh có thể khác nhau.

### 12.1. Trọng số cạnh âm có làm hỏng quy tắc không?

**Không.** Cả cut property, cycle property, Kruskal và Prim đều dựa vào thứ tự so sánh **trọng số** và cấu trúc cây, không dùng giả thiết trọng số không âm.

Ví dụ cạnh 4—5 trọng số −2 là cạnh duy nhất kết nối hai đỉnh trong thành phần `{4,5}`. Nó phải có trong MSF. Cộng trọng số âm cho tổng 4 là hoàn toàn đúng.

**Phân biệt với Dijkstra:** Dijkstra shortest path cần trọng số **không âm** để chốt đỉnh; MST không yêu cầu giả thiết ấy.

### 12.2. Có thể chọn rừng tổng trọng số âm mà không nối đủ không?

Giả sử chỉ lấy vài cạnh âm và bỏ hết những cạnh dương. Tập chọn có thể có tổng nhỏ hơn một MSF, nhưng nếu nó **không nối đủ từng thành phần ban đầu**, thì **không phải rừng khung đầy đủ**, không được dùng để so sánh.

Tối ưu cần thỏa **đủ điều kiện ràng buộc**, không chỉ tối thiểu một biểu thức tổng.

## 13. MST không phải cây đường đi ngắn nhất

Đây là hai mục tiêu khác nhau, thường bị nhầm:

- **MST:** giảm **tổng trọng số tất cả cạnh trong cây**, không có nguồn cố định.
- **Shortest Path Tree — SPT:** với một nguồn s, đường trong cây từ s đến mỗi đỉnh phải có độ dài đúng bằng **khoảng cách ngắn nhất trong G**.

Ví dụ đồ thị 4 đỉnh có:

```text
0—1:2, 0—2:2, 0—3:2
1—2:1, 2—3:1
```

Nếu cần shortest paths từ nguồn 0:

- Đường ngắn nhất từ 0 tới 1 dài 2.
- Đường ngắn nhất từ 0 tới 2 dài 2.
- Đường ngắn nhất từ 0 tới 3 dài 2.

Một SPT tự nhiên lấy ba cạnh sao tâm `0—1`, `0—2`, `0—3`, tổng trọng số **6**.

Một MST thì có thể chọn:

`1—2 (1), 2—3 (1), 0—1 (2)`,

tổng trọng số **4**. Nhưng đường từ 0 tới đỉnh 3 trong MST dài `2+1+1=4`, dài hơn đường trực tiếp 0—3 bằng 2.

Vậy MST **không** đảm bảo đường từ một nguồn tới mọi đỉnh ngắn nhất. Ngược lại, SPT không đảm bảo tổng trọng số cạnh của cây nhỏ nhất.

Không dùng Prim/Kruskal để giải bài **đường đi ngắn nhất** chỉ vì cả hai đều dùng ưu tiên trọng số. Dijkstra chọn đỉnh theo **khoảng cách tích lũy từ nguồn**; Prim chọn cạnh theo **trọng số nối qua lát cắt**.

## 14. Khi nào MST là duy nhất?

### 14.1. Các trọng số đôi một khác nhau ⇒ MST duy nhất

Nếu **mọi cạnh có trọng số khác nhau**, MST của đồ thị liên thông là duy nhất. Trực giác: tại các lát cắt, cạnh nhẹ nhất là duy nhất, và phép chọn cạnh an toàn được ép theo cấu trúc.

Cách chứng minh bằng phản chứng: giả sử có hai MST T và T' khác nhau. Chọn cạnh e nhẹ nhất trong hiệu đối xứng của hai tập cạnh; không mất tính tổng quát e thuộc T nhưng không thuộc T'. Thêm e vào T' tạo chu trình; trên chu trình có cạnh f thuộc T' mà không thuộc T. Do e được chọn nhẹ nhất trong hiệu đối xứng và trọng số đều khác nhau, `w(e)<w(f)`. Thay f bằng e làm T' nhẹ hơn, mâu thuẫn.

### 14.2. Có trọng số trùng nhau không suy ra nhiều MST

Ví dụ tam giác:

```text
0—1:1
1—2:1
0—2:2
```

Hai cạnh trọng số 1 phải được chọn để tối ưu; MST duy nhất có tổng 2, dù có **hai cạnh cùng trọng số**.

Do đó:

- **Cạnh đều khác trọng số:** điều kiện **đủ** để đảm bảo duy nhất.
- **Có cạnh cùng trọng số:** chưa thể kết luận duy nhất hay không.

### 14.3. Một tiêu chuẩn kiểm MST được chọn

Giả sử T là một MST của đồ thị vô hướng liên thông. Với mỗi cạnh e=(u,v) **không thuộc T** và không phải self-loop, giữa u và v có một đường duy nhất trong T.

Gọi `maxWeightOnTreePath(u,v)` là trọng số lớn nhất trên đường ấy.

- Vì T là MST, phải có `w(e) >= maxWeightOnTreePath(u,v)`.
- Nếu có cạnh ngoài T với `w(e) == maxWeightOnTreePath(u,v)`, có thể đổi e với một cạnh nặng nhất trên đường để tạo **MST khác** cùng tổng.
- Nếu **mọi** cạnh ngoài T có `w(e) > maxWeightOnTreePath(u,v)`, T là MST **duy nhất**.

Với đồ thị không liên thông, áp dụng tiêu chuẩn cho từng cây thành phần của MSF. Self-loop không làm thành cây thay thế. Cạnh song song được xét như các cạnh có ID riêng, nếu định nghĩa nghiệm phân biệt cạnh.

Tiêu chuẩn này rất hữu ích để **kiểm chứng** một nghiệm hoặc phân loại uniqueness, nhưng cần dữ liệu hỗ trợ truy vấn max-edge-on-path như DFS cho bài nhỏ, hoặc binary lifting/LCA cho nhiều truy vấn trên cây lớn.

## 15. Liên thông, MSF và những bài yêu cầu khác

### 15.1. Đề yêu cầu “MST” nhưng đầu vào có thể không liên thông

Cần xem hợp đồng đầu ra:

- Trả “**IMPOSSIBLE**” hoặc `-1` nếu không có cây khung toàn G.
- Trả rừng khung nhỏ nhất và số cây.
- Trả tổng trọng số nhỏ nhất có thể khi nối tối đa những đỉnh vốn có cạnh thông nhau.

Không tự thay điều kiện này bằng việc cho phép thêm một cạnh ngoài G, trừ khi đề định nghĩa chi phí bổ sung hoặc đầy đủ các cặp đỉnh.

Trong ba chương trình Java, kết quả luôn có **MSF**; trường `hasSpanningTree` cho biết có thể gọi kết quả đó là một MST cho **toàn bộ** G hay không.

### 15.2. Đề chỉ hỏi kiểm tra liên thông

Không cần tính MSF nếu không cần trọng số. Chạy BFS/DFS từ một đỉnh hoặc dùng DSU gộp mọi cạnh, kiểm `components==1` khi n>=1. Với đồ thị vô hướng, O(V+E) thời gian là đủ để kiểm tra liên thông bằng BFS/DFS.

Kruskal phải sort cạnh vì nó còn **tối ưu trọng số**; sort là thừa nếu chỉ hỏi liên thông.

### 15.3. Đề yêu cầu số cạnh tối thiểu để nối thành mạng

Nếu được phép **thêm cạnh mới giữa những thành phần**, đồ thị có k thành phần cần ít nhất `k−1` cạnh mới để thành liên thông (với n>=1), miễn thêm được các cạnh nối thích hợp.

Nhưng **chọn k−1 cạnh mới nào, chi phí bao nhiêu, và có được nối mọi cặp thành phần không** là các điều kiện bổ sung. Công thức `k−1` chỉ nói về **số lượng tối thiểu theo cấu trúc**, không phải đáp án chi phí MST trên đồ thị có sẵn.

### 15.4. Cây khung lớn nhất (*maximum spanning tree*)

Nếu mục tiêu là **tối đa** tổng trọng số, thay thứ tự xét cạnh của Kruskal bằng **giảm dần**, hoặc Prim chọn cạnh lớn nhất vượt lát cắt.

Đó là **maximum spanning tree/forest**, không phải MST. Đừng nhầm chữ “minimum” với “maximum” khi thay comparator. Tính liên thông vẫn là điều kiện tồn tại cây khung toàn đồ thị.

### 15.5. Đồ thị có hướng

Khái niệm cây khung vô hướng của bài học **không áp trực tiếp** cho đồ thị có hướng. Bài tương ứng có thể là **minimum directed spanning arborescence** với một gốc, mỗi đỉnh reachable bằng đường có hướng và có điều kiện cạnh vào.

Kruskal/Prim được trình bày ở đây là **cho đồ thị vô hướng**. Nếu chỉ bỏ hướng của các cạnh có hướng rồi chạy Kruskal, ta đã **đổi mô hình**, không giải bài arborescence gốc.

## 16. Kiểm tra một kết quả rừng khung đã chọn

Một tập cạnh được báo là MSF phải vượt qua **hai lớp** kiểm tra:

**Lớp cấu trúc:**

1. Mọi cạnh được chọn tồn tại trong input (nếu multigraph, đối chiếu ID cạnh).
2. Các đầu cạnh nằm trong tập đỉnh hợp lệ.
3. Có đủ mọi đỉnh trong rừng, kể cả đỉnh cô lập.
4. Không chứa chu trình, self-loop hoặc chu trình hai cạnh song song.
5. Số cạnh bằng `n−k`, với k là số thành phần của G gốc.
6. Số thành phần rừng bằng k, nối đúng mỗi thành phần G.

**Lớp tối ưu:**

1. Tổng trọng số được tính đúng, không overflow.
2. Với dữ liệu nhỏ, đối chiếu brute force.
3. Với dữ liệu lớn, đối chiếu Kruskal và Prim độc lập.
4. Có thể kiểm tra không tồn tại cạnh ngoài T có thể thay một cạnh nặng hơn trên đường của T; nếu có, cây chưa tối ưu.
5. Nếu đòi tính duy nhất, kiểm các cạnh ngoài có thể thay cùng trọng số.

Lớp cấu trúc **không đủ** để kết luận tối ưu: bất kỳ cây khung nào cũng không có chu trình và có n−1 cạnh, nhưng có thể nặng hơn MST.

### 16.1. Kiểm tra totalWeight của cạnh âm

Một kết quả tổng âm không có nghĩa thuật toán bị lỗi. Nếu đồ thị chứa cạnh âm, MSF có thể âm; mọi phép so phải dùng tổng có dấu đúng.

Với ví dụ 7 đỉnh, cây thứ nhất trọng số 6, cây thứ hai -2, cây thứ ba 0 ⇒ `totalWeight=4`.

### 16.2. Đồ thị có nhiều thành phần và một số cạnh thừa

Khi thêm một cạnh nối hai đỉnh **đã cùng nhóm DSU**, cạnh ấy tạo chu trình và phải bị bỏ. Điều này đúng dù cạnh là âm, dương hay có trọng số bằng cạnh đã chọn.

Ngược lại, khi một cạnh nối **hai thành phần khác nhau**, việc chọn nó có thể cần thiết để rừng khung nối trọn vẹn thành phần gốc; nếu nó là cạnh nhẹ nhất qua lát cắt phù hợp, Kruskal có cơ sở chọn an toàn.

## 17. So sánh Kruskal, Prim và BFS/DFS

| Tiêu chí | BFS/DFS | Kruskal | Prim |
|---|---|---|---|
| Bài toán chính | Liên thông, cây DFS/BFS, duyệt | MST/MSF tối ưu trọng số | MST/MSF tối ưu trọng số |
| Có quan tâm trọng số? | Không trong kiểm liên thông | Có, sort tăng | Có, chọn min qua cut |
| Cấu trúc chính | Queue/stack, visited | DSU + danh sách cạnh sort | Adjacency + visited + min-heap |
| Với đồ thị không liên thông | Tạo forest nếu chạy từ mọi nguồn | Tự cho MSF | Cần restart mỗi thành phần |
| Với đỉnh cô lập | Thành phần một đỉnh | DSU giữ thành phần | Root mới không thêm cạnh |
| Với trọng số âm | Không ảnh hưởng liên thông | Hỗ trợ | Hỗ trợ |
| Output tổng nhỏ nhất? | **Không đảm bảo** | Có | Có |
| Chi phí điển hình | `O(V+E)` | `O(V+E log E+Eα(V))` | `O(V+E log(E+1))` lazy |

**Một cây DFS/BFS** của đồ thị liên thông là một **cây khung**, nhưng thường **không** là MST nếu các cạnh có trọng số khác nhau. BFS tối ưu **số cạnh trên đường từ nguồn**, không tối ưu tổng trọng số của cả cây.

### 17.1. Chọn Kruskal hay Prim?

- Nếu input là **edge list**, cần xử lý đồ thị rời rạc và muốn code trực quan, **Kruskal + DSU** thường dễ.
- Nếu input là **adjacency list** hoặc đồ thị dày, **Prim** có thể phù hợp; nhưng cần xét biến thể heap/mảng và chi phí cạnh.
- Nếu đồ thị không liên thông và cần MSF, **Kruskal** tự hoạt động, còn **Prim** phải có vòng ngoài.
- Nếu chỉ cần kết luận liên thông, BFS/DFS/DSU **không cần sort**.

Không có khẳng định thuật toán nào nhanh hơn tuyệt đối trên mọi đồ thị, vì cấu trúc dữ liệu, mật độ cạnh, chi phí sort và heap khác nhau.

## 18. Những lỗi thường gặp

### Lỗi 1 — Báo MST khi đồ thị không liên thông

Nếu có k>1 thành phần, không tồn tại một cây khung toàn đồ thị. Kết quả Kruskal/Prim nhiều cây là **MSF**, không phải MST.

### Lỗi 2 — Bỏ đỉnh cô lập ra khỏi V

Nếu đầu vào có n=7 nhưng chỉ có cạnh trên các đỉnh 0..5, đỉnh 6 vẫn phải được tính. Số thành phần là 3 thay vì 2. MSF chứa cả cây `{6}`.

### Lỗi 3 — So nhầm số cạnh với liên thông

Chỉ biết `m=n−1` chưa chắc đồ thị là cây. Có thể có chu trình trong một thành phần và đỉnh cô lập ở thành phần khác.

### Lỗi 4 — Chọn mọi cạnh trọng số âm

Một self-loop âm hoặc cạnh âm nối hai đỉnh đã cùng thành phần tạo chu trình; không được chọn trong rừng khung. Mục tiêu là **tổng nhỏ nhất trong rừng hợp lệ**, không phải tổng các cạnh âm.

### Lỗi 5 — Không kiểm tra chu trình trong Kruskal

Chọn cạnh theo trọng số tăng mà không DSU có thể tạo chu trình, số cạnh lớn hơn `n−k` và kết quả không phải rừng.

### Lỗi 6 — Cho Prim chạy từ một gốc duy nhất rồi gọi là MSF

Nếu đồ thị rời rạc, heap cạn chỉ chứng minh đã duyệt xong **thành phần hiện tại**. Phải restart từ mỗi đỉnh chưa thăm để trả MSF toàn đồ thị.

### Lỗi 7 — Cấm trọng số âm một cách không cần thiết

Kruskal/Prim hỗ trợ cạnh âm. Không copy điều kiện `w>=0` của Dijkstra sang MST nếu đề không yêu cầu.

### Lỗi 8 — Dùng comparator trừ hai trọng số

Trả `(int)(a.weight-b.weight)` có thể tràn và làm sort sai. Dùng `Long.compare` hoặc `Comparator.comparingLong`.

### Lỗi 9 — Dùng int cho tổng lớn

Tổng nhiều cạnh có thể vượt `int` dù từng trọng số vừa `int`. Dùng `long` và kiểm tra tràn; với dữ liệu lớn hơn dùng `BigInteger`.

### Lỗi 10 — Không xử lý self-loop

Self-loop không giúp kết nối thêm đỉnh, nhưng có thể có trọng số rất nhỏ. DSU `find(u)==find(v)` tự từ chối; Prim nên bỏ loop khi dựng adjacency hoặc khi xét ứng viên.

### Lỗi 11 — Coi hai cạnh song song là một không có điều kiện

Trong multigraph, cạnh song song khác ID hoặc khác trọng số là **hai lựa chọn**. Loại nhầm cạnh có thể làm tăng tổng MST hoặc làm sai số MST nếu đề đếm nghiệm.

### Lỗi 12 — Dùng DSU kiểm kết nối sau khi chỉ xét vài cạnh

DSU của những cạnh **đã chọn** có thể chưa phản ánh số thành phần của **G gốc** khi chưa duyệt hết input. Để xác định liên thông của G, phải xét đầy đủ cạnh gốc hoặc chạy BFS/DFS trên G.

### Lỗi 13 — Nhầm rừng không chu trình bất kỳ với rừng khung đầy đủ

Không chọn cạnh nào chắc chắn không tạo chu trình nhưng thường **không** nối đủ những đỉnh vốn thuộc cùng thành phần gốc. Cần `n−k` cạnh và kết nối đúng từng thành phần.

### Lỗi 14 — Đòi tất cả MST giống nhau khi có tie

Cạnh cùng trọng số có thể tạo nhiều MST. Kruskal/Prim có thể in tập cạnh khác nhau nhưng **cùng tổng tối ưu**.

### Lỗi 15 — Kết luận nhiều MST chỉ vì có trọng số trùng

Trọng số khác nhau là **điều kiện đủ** cho tính duy nhất, không phải điều kiện cần. Tam giác 1,1,2 vẫn có một MST duy nhất.

### Lỗi 16 — Dùng MST để trả lời shortest path

MST giảm tổng cạnh trong cây. Một đường từ nguồn trên MST có thể dài hơn đường ngắn nhất trong đồ thị gốc.

### Lỗi 17 — Áp Kruskal/Prim lên đồ thị có hướng

Hai thuật toán ở đây dùng cấu trúc vô hướng. Bài minimum directed arborescence yêu cầu thuật toán khác.

### Lỗi 18 — Không tính số thành phần sau union

Nếu không giữ `components` hoặc không đọc `n−selectedCount`, khó biết rừng đã nối đủ, đặc biệt khi đầu vào không liên thông.

### Lỗi 19 — Quên cập nhật visited của Prim trước khi thêm cạnh mới

Một đỉnh được thêm vào cây phải được đánh dấu ngay khi chọn cạnh vào nó. Nếu chậm đánh dấu, có thể chọn nhiều cạnh vào cùng một đỉnh và tạo chu trình.

### Lỗi 20 — Không bỏ entry heap stale trong Prim

Heap có thể giữ cạnh đến một đỉnh đã visited; phải bỏ qua khi pop. Đừng cộng trọng số những entry cũ.

### Lỗi 21 — Không tạo adjacency hai chiều

Trong đồ thị vô hướng, nếu chỉ thêm cung `u→v` mà không thêm `v→u`, Prim có thể không nhìn thấy cạnh khi mở rộng từ phía ngược.

### Lỗi 22 — Nhầm số component khi n=0 hoặc n=1

Đồ thị một đỉnh có **một component**, có MST rỗng trọng số 0. Đồ thị 0 đỉnh được xử lý theo **quy ước bài**, không tự áp `components==1`.

### Lỗi 23 — Không phân biệt minimum và maximum

Kruskal tăng dần cho **minimum**, giảm dần cho **maximum**. Một comparator sai hướng đảo bài toán.

### Lỗi 24 — Giả định kết quả phụ thuộc thứ tự input là luôn cố định

Nếu nhiều cạnh cùng trọng số, thứ tự xét quyết định MST nào được chọn. Muốn test ổn định, phá hòa bằng chỉ số cạnh gốc hoặc một quy tắc cụ thể.

## 19. Bộ test bắt buộc cho MST và MSF

| Đồ thị | Kết quả đúng cần kiểm |
|---|---|
| Một đỉnh, không cạnh | Liên thông, MST 0 cạnh, tổng 0 |
| Ba đỉnh, không cạnh | 3 components, MSF 0 cạnh, **không có MST toàn đồ thị** |
| Hai đỉnh, một cạnh trọng số −3 | Liên thông, MST chứa cạnh âm, tổng −3 |
| Ba đỉnh tạo tam giác 1,2,3 | MST chọn 1 và 2, tổng 3 |
| Tam giác 1,1,1 | 3 MST khác nhau, cùng tổng 2 |
| Tam giác 1,1,2 | MST duy nhất, tổng 2 |
| 7 đỉnh ví dụ phần 4 | 3 components, 4 cạnh MSF, tổng 4 |
| Cạnh self-loop −100 | Không bao giờ được chọn vào rừng |
| Hai cạnh song song trọng số 1 và 6 | Cạnh 6 bị loại nếu 1 đã nối cùng hai đỉnh |
| Cạnh cầu trọng số rất lớn | Cầu vẫn bắt buộc trong mọi spanning tree của thành phần |
| Đồ thị liên thông mọi trọng số khác nhau | MST duy nhất |
| Một đồ thị có nhiều MST | Kruskal/Prim có thể khác list cạnh nhưng chi phí bằng nhau |
| n=0 | Theo quy ước: MSF rỗng, components 0, không có spanning tree |
| n=2 với cạnh 0—1=0 | MST tổng 0 dù có cạnh thật |
| Đồ thị có hai thành phần nhưng tất cả cạnh đều dương | Vẫn phải nối đủ từng thành phần; không được bỏ cạnh “đắt” nếu nó bắt buộc |

### 19.1. Kiểm thử so chéo trên đồ thị nhỏ

Một quy trình đánh giá đáng tin:

1. Sinh một đồ thị vô hướng nhỏ, có thể không liên thông.
2. Giữ cả `n` kể cả đỉnh không có cạnh.
3. Tính số thành phần gốc bằng DSU/BFS trên **toàn bộ cạnh**.
4. Chạy Kruskal để tạo MSF và tổng.
5. Chạy Prim với vòng restart để tạo MSF và tổng.
6. Dùng vét cạn nếu m nhỏ để tìm MSF tối ưu độc lập.
7. So sánh: ba tổng bằng nhau, số cây bằng số thành phần gốc, số cạnh chọn đúng `n−k`.
8. Kiểm tra mọi cạnh chọn thuộc input, không tạo chu trình.
9. Với trường hợp nhiều MST, **không** yêu cầu danh sách cạnh hoàn toàn giống nhau.
10. Thử trọng số âm, 0, trùng, self-loop và cạnh song song.

### 19.2. Một oracle cấu trúc đơn giản

Cho danh sách các cạnh đã chọn từ thuật toán:

```text
checkForest(n, allEdges, chosen):
    originalComponents = DSU union allEdges
    selectedComponents = DSU union chosen
    nếu bất kỳ union(chosenEdge) trả false:
        FAIL (chu trình)
    nếu selectedComponents != originalComponents:
        FAIL (chưa khung đủ)
    nếu chosen.size() != n-originalComponents:
        FAIL
    nếu bất kỳ chosenEdge không nằm trong allEdges:
        FAIL
    nếu sum(chosen.weight) != reportedCost:
        FAIL
    PASS về cấu trúc
```

Đây chỉ là kiểm cấu trúc. Để xác minh **minimum**, vẫn cần so optimum độc lập hoặc chứng minh bằng cut/cycle property.

## 20. Bài tập tự luyện có đáp án

### Bài 1 — Điều kiện tồn tại

Đồ thị vô hướng có 8 đỉnh và 2 thành phần liên thông. Có cây khung cho cả đồ thị không?

**Đáp án:** không. Cây khung toàn bộ tồn tại khi và chỉ khi đồ thị liên thông; hai thành phần không có cạnh nối.

### Bài 2 — Số cạnh của MSF

Đồ thị có `n=10`, `k=4` thành phần. Rừng khung đầy đủ có bao nhiêu cạnh?

**Đáp án:** `n−k=10−4=6`.

### Bài 3 — Đỉnh cô lập

Một đồ thị có 4 đỉnh nối thành một component và 1 đỉnh cô lập. Nếu có 5 đỉnh tổng cộng, MSF gồm bao nhiêu cây?

**Đáp án:** 2 cây: một trên 4 đỉnh và một cây một đỉnh cô lập.

### Bài 4 — Cây một đỉnh

Đồ thị `V={0}`, `E=∅` có MST không và trọng số là bao nhiêu?

**Đáp án:** có, cây rỗng cạnh trên một đỉnh, tổng 0.

### Bài 5 — Cạnh âm

Đồ thị hai đỉnh 0 và 1 có cạnh trọng số −7. MST có tổng bao nhiêu?

**Đáp án:** −7. Cạnh là cầu duy nhất nối hai đỉnh, phải được chọn.

### Bài 6 — Self-loop âm

Đồ thị có cạnh `2—2` trọng số −1000. Nó có thể thuộc một rừng khung không?

**Đáp án:** không, vì tự nó là một chu trình; không nối thêm đỉnh.

### Bài 7 — Tam giác

Tam giác cạnh trọng số 2,5,7 có MST tổng bao nhiêu?

**Đáp án:** chọn hai cạnh nhẹ nhất 2 và 5, tổng 7.

### Bài 8 — Đếm cạnh

Đồ thị liên thông 15 đỉnh. Mọi cây khung có bao nhiêu cạnh?

**Đáp án:** `15−1=14`.

### Bài 9 — MSF nhiều thành phần

Ba component có MST tổng lần lượt 8,−3,0. Tổng MSF là bao nhiêu?

**Đáp án:** `8−3+0=5`.

### Bài 10 — Kruskal và DSU

Nếu một cạnh nối u và v mà `find(u)==find(v)`, Kruskal có chọn cạnh ấy không?

**Đáp án:** không. Chọn nó tạo chu trình trong rừng hiện tại.

### Bài 11 — Prim không liên thông

Prim bắt đầu từ đỉnh 0 và heap cạn, nhưng còn đỉnh chưa thăm. Có kết luận đã tạo MSF toàn đồ thị chưa?

**Đáp án:** chưa. Phải restart từ một đỉnh chưa thăm và tiếp tục đến khi mọi đỉnh được xử lý.

### Bài 12 — Unique MST

Mọi cạnh có trọng số khác nhau. MST có chắc duy nhất không?

**Đáp án:** có, với đồ thị vô hướng liên thông. Nếu không liên thông, từng component có MST duy nhất và MSF cũng duy nhất về tập cạnh.

### Bài 13 — Equal weights

Một số cạnh có trọng số bằng nhau. Có chắc có nhiều MST không?

**Đáp án:** không. Tam giác trọng số 1,1,2 có một MST duy nhất.

### Bài 14 — Cut property

Một lát cắt có ba cạnh đi qua trọng số 2,4,9; cạnh trọng số 2 có thể chọn an toàn không?

**Đáp án:** có, đó là cạnh nhẹ nhất qua cut. Nếu lát cắt tôn trọng rừng đã chọn, thêm cạnh ấy là một bước MST an toàn.

### Bài 15 — Cạnh duy nhất nhẹ nhất

Nếu e là **duy nhất** nhẹ nhất đi qua một lát cắt, e có nằm trong mọi MST không?

**Đáp án:** có. Nếu MST nào bỏ e, phép đổi cạnh sẽ làm giảm tổng, mâu thuẫn tối ưu.

### Bài 16 — Cycle property

Một chu trình có trọng số các cạnh 1,3,8,5. Cạnh duy nhất trọng số 8 có thể thuộc MST không?

**Đáp án:** không. Nó là cạnh duy nhất lớn nhất trên chu trình, có thể đổi bằng cạnh nhẹ hơn để giảm tổng.

### Bài 17 — Cầu

Một cạnh cầu có trọng số rất lớn. MST có thể bỏ cầu đó vì quá đắt không?

**Đáp án:** không, nếu bỏ sẽ ngắt kết nối thành phần; mọi spanning tree đều phải chứa cầu.

### Bài 18 — MST và SPT

Đồ thị có cạnh 0—1,0—2,0—3 cùng trọng số 2 và 1—2,2—3 trọng số 1. Chi phí MST và cây shortest path gốc 0 của ví dụ là gì?

**Đáp án:** MST tổng 4; SPT dạng sao từ 0 tổng 6. Hai bài tối ưu tiêu chí khác nhau.

### Bài 19 — Kết quả Kruskal ví dụ

Với graph 7 đỉnh phần 4, Kruskal chọn bao nhiêu cạnh, gồm bao nhiêu cây, tổng trọng số bao nhiêu?

**Đáp án:** 4 cạnh, 3 cây, tổng 4.

### Bài 20 — Các nghiệm MST đồng tối ưu

Đồ thị bốn đỉnh gồm tam giác ba cạnh trọng số 1 và hai cạnh nối đỉnh thứ tư trọng số 2. Có bao nhiêu MST?

**Đáp án:** `3×2=6`, mỗi MST tổng 4.

### Bài 21 — Kiểm tra liên thông bằng số cạnh

Đồ thị có 4 đỉnh, 3 cạnh, gồm một tam giác và một đỉnh cô lập. Nó có cây khung không?

**Đáp án:** không. Dù `m=n−1`, đồ thị không liên thông và có chu trình.

### Bài 22 — Kiểu đồ thị

Một mạng đường một chiều cho phép đi từ u tới v nhưng không được ngược lại. Có dùng nguyên Kruskal/Prim cho directed arborescence không?

**Đáp án:** không. Phải dùng mô hình/thuật toán cho cây có hướng phù hợp, hoặc đề phải rõ rằng đang xét kết nối vô hướng.

## 21. Checklist trước khi nộp lời giải MST/MSF

1. **Đồ thị có vô hướng không?** Nếu có hướng, cần định nghĩa bài toán khác.
2. **Đề yêu cầu MST toàn đồ thị hay MSF cho từng thành phần?**
3. **Có đảm bảo G liên thông không?** Nếu không, đã xử lý `components>1` đúng hợp đồng?
4. **n có thể bằng 0 hoặc 1 không?** Quy ước đầu ra đã rõ?
5. **Mọi đỉnh, kể cả cô lập, đã được tính vào n và DSU/visited?**
6. **Các cạnh có thể âm/0/parallel/self-loop không?** Alg có xử lý đúng?
7. **Kruskal có sort trọng số tăng và union hai nhóm khác nhau?**
8. **Comparator có tránh tràn số không?**
9. **Prim có dùng cạnh nhẹ nhất vượt cắt, kiểm visited lúc pop không?**
10. **Nếu không liên thông, Prim có restart từ mọi root chưa visited không?**
11. **Số cạnh chọn có đúng `n−components` không?**
12. **Tập cạnh có thực sự không chu trình và nối đủ các component gốc không?**
13. **Tổng trọng số có kiểm tràn không?** Có cần BigInteger?
14. **Có trả riêng `hasSpanningTree` và `MSF cost` để tránh nhầm không?**
15. **Nếu bài đếm số MST, có xét tie và định nghĩa cạnh song song là nghiệm khác không?**
16. **Nếu bài yêu cầu MST duy nhất, có kiểm chứ không suy từ “có tie” đơn thuần không?**
17. **Nếu chỉ cần liên thông, có dùng BFS/DFS/DSU thay vì sort thừa không?**
18. **Nếu bài tìm đường ngắn nhất, đã chọn thuật toán SPT thay MST chưa?**
19. **Đã test negative weights, bridges, self-loop, isolated, duplicates và graph trống?**
20. **Đã đối chiếu Kruskal, Prim và brute force trên graph nhỏ chưa?**
21. **Đã chứng minh cạnh greedy an toàn qua cut/exchange argument?**
22. **Kết luận chính xác: nếu connected là MST, nếu disconnected là MSF?**

**Ghi nhớ:** với đồ thị vô hướng có ít nhất một đỉnh, **cây khung toàn đồ thị tồn tại khi và chỉ khi đồ thị liên thông**. Nếu đồ thị có k thành phần, một **rừng khung đầy đủ** có `n−k` cạnh và gồm **k cây**, kể cả những cây chỉ có một đỉnh cô lập. **MSF** là hợp các MST của từng thành phần; **Kruskal** tự xây MSF bằng DSU, còn **Prim** cần chạy lại ở mỗi thành phần. Tối ưu được bảo đảm bởi **cut property và exchange argument**, không phải bởi giả định trọng số không âm. Cuối cùng, MST tối thiểu **tổng cạnh trong cây**, không đồng nghĩa cây đường đi ngắn nhất từ một nguồn.

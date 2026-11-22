# Đổi gốc để tính kết quả cho mọi đỉnh (Rerooting DP trên cây)

**Đổi gốc (rerooting / rerooting dynamic programming)** là kỹ thuật **quy hoạch động trên cây** dùng để tính một đại lượng cho **mọi đỉnh khi lần lượt xem mỗi đỉnh là gốc**, nhưng **không chạy lại toàn bộ thuật toán cho từng gốc**.

Bài toán điển hình: cho cây vô hướng n đỉnh và khoảng cách theo số cạnh, cần tính với mọi đỉnh u:

**F(u) = ∑ dist(u,v)**, trong đó v chạy qua **tất cả các đỉnh**.

Nếu chạy BFS/DFS từ từng u để tính tổng khoảng cách, chi phí là **O(n²)** trên cây. Rerooting xử lý toàn bộ cây một lần để có thông tin của các nhánh con, rồi **truyền đáp án từ gốc hiện tại sang từng đỉnh con**. Với bài này, tất cả n kết quả được tính trong **O(n)** thời gian.

Kỹ thuật áp dụng rộng hơn tổng khoảng cách: **khoảng cách xa nhất từ mỗi đỉnh**, tổng khoảng cách có trọng số, DP từ cả hai phía một cạnh, tối ưu trên nhánh bất kỳ, và các bài **đổi gốc không có công thức trừ đơn giản** cần tiền tố/hậu tố khi gộp các nhánh.

Điểm cốt lõi là phân biệt:

- **DP trong cây con:** chỉ tính thông tin từ những đỉnh ở phía dưới khi cố định một gốc ban đầu.
- **Đáp án khi xét toàn cây:** mỗi đỉnh còn bị ảnh hưởng bởi **những đỉnh nằm ngoài cây con của nó**.
- **Rerooting:** truyền ảnh hưởng từ bên ngoài xuống từng nhánh để mọi đỉnh có thể được xem như gốc mà không phải tính lại từ đầu.

## 1. Cây vô hướng, gốc tạm thời và cây con

Một **cây** là đồ thị vô hướng **liên thông, không có chu trình**. Cây có n≥1 đỉnh có đúng n−1 cạnh và giữa hai đỉnh bất kỳ tồn tại **một đường đi đơn duy nhất**.

Mặc dù cây đầu vào thường **không có gốc**, ta có thể chọn một đỉnh bất kỳ làm **gốc tạm thời**, chẳng hạn đỉnh 1, để định nghĩa:

- **parent[u]:** cha của u theo gốc tạm thời.
- **children[u]:** các đỉnh con trực tiếp.
- **subtree(u):** u cùng tất cả hậu duệ của u.
- **size[u]:** số đỉnh trong subtree(u).
- **depth[u]:** số cạnh từ gốc tạm thời đến u.

Ví dụ cây bảy đỉnh:

~~~text
           1
         /   \
        2     3
       / \     \
      4   5     6
                 \
                  7

Các cạnh:
(1,2), (1,3), (2,4), (2,5), (3,6), (6,7)
~~~

Khi gốc tạm thời là 1:

- subtree(2) = {2,4,5}, nên **size[2]=3**.
- subtree(3) = {3,6,7}, nên **size[3]=3**.
- subtree(6) = {6,7}, nên **size[6]=2**.
- Các lá 4,5,7 có **size=1**.
- Gốc 1 có **size[1]=n=7**.

**Gốc tạm thời không làm đổi đường đi giữa các đỉnh.** Nó chỉ cho ta một hướng cha–con để tổ chức hai lượt tính toán. Kết quả cuối cùng ở mỗi đỉnh phải là đại lượng của **toàn cây**, không phải chỉ cây con theo gốc 1.

### Điều kiện quan trọng trước khi áp dụng

- Đầu vào phải là **cây**, hoặc mỗi thành phần được xử lý theo mô hình rừng phù hợp.
- **Không áp dụng công thức cây một cách máy móc cho đồ thị có chu trình**: một cạnh có thể không chia đồ thị thành đúng hai thành phần như trên cây.
- Nếu bài cho cạnh có trọng số, phải thay đổi phép tính khoảng cách theo trọng số cạnh.
- Nếu chỉ cần đáp án cho **một gốc duy nhất**, một DFS có thể đã đủ; lợi thế rerooting thể hiện khi cần **mọi gốc**.

## 2. Nhận ra dấu hiệu của bài rerooting

Các cách diễn đạt thường gợi ý rerooting DP:

- “Với **mỗi đỉnh u**, tính tổng khoảng cách tới **tất cả đỉnh còn lại**.”
- “Chọn một đỉnh đặt trạm sao cho tổng khoảng cách tới mọi nhà là nhỏ nhất.”
- “Với **mỗi đỉnh**, biết độ xa nhất tới một đỉnh khác.”
- “Nếu đổi gốc cây thành u, một đại lượng của cây có giá trị bao nhiêu?”
- “Mỗi đỉnh cần biết kết quả từ **mọi hướng kề**, không chỉ từ các con của gốc cố định.”
- “Trả lời n truy vấn, mỗi truy vấn hỏi một **gốc khác nhau**, trên cùng cây tĩnh.”

Một cách kiểm tra nhanh:

1. Cố định một gốc r, có tính được **đóng góp của các cây con** không?
2. Nếu di chuyển gốc từ u sang đỉnh kề v, có thể **cập nhật đáp án nhanh** từ thông tin đã biết không?
3. Nếu không cập nhật bằng một phép trừ/cộng đơn giản, có thể tính thông tin **ở phía ngoài subtree(v)** không?
4. Có thể xử lý tất cả các cạnh một số lần hằng số thay vì duyệt lại toàn cây cho từng gốc không?

Nếu trả lời được những câu hỏi này, rerooting có khả năng giảm bài toán từ O(n²) xuống O(n) trong nhiều trường hợp.

## 3. Hai lượt DFS/BFS trên cây: khung tổng quát

Nhiều bài rerooting có thể trình bày thành **hai lượt**.

**Lượt 1 — Từ lá lên gốc (postorder):**

- Cố định gốc r.
- Tính DP của mỗi đỉnh từ DP các đỉnh con.
- Thu được thông tin của subtree(u): kích thước, tổng khoảng cách trong cây con, chiều cao đi xuống, v.v.
- Sau lượt này, ta thường biết đáp án cho **gốc r** nhưng chưa biết đáp án cho mọi đỉnh.

**Lượt 2 — Từ gốc xuống lá (preorder):**

- Với mỗi cạnh cha u → con v, chuyển thông tin từ phía u sang phía v.
- Tính đáp án của v từ đáp án/thông tin tại u và phần đóng góp của subtree(v).
- Truyền tiếp cho các con của v.

Giả mã khái quát:

~~~text
root = một đỉnh bất kỳ
xác định parent, order từ root

for u in order theo thứ tự ngược:
    down[u] = gộp thông tin từ các con của u

all[root] = kết quả toàn cây tại root

for u in order theo thứ tự thuận:
    for mỗi con v của u:
        all[v] = reroot(all[u], down[v], dữ liệu của cạnh u-v)

trả all[u] cho mọi u
~~~

Ở đây **order** là một thứ tự bảo đảm cha đứng trước con (DFS preorder hoặc BFS từ gốc đều đáp ứng). Đi **ngược order** bảo đảm con đã được tính trước cha; đi **thuận order** bảo đảm cha được tính trước con. Không nhất thiết phải dùng đệ quy: có thể dựng order một lần rồi duyệt hai chiều, tránh nguy cơ stack overflow khi cây là một đường thẳng rất dài.

**Quan trọng:** Không phải mọi bài có một hàm reroot đơn giản như all[v]=f(all[u],down[v]). Với phép tổng hợp phức tạp, lượt hai có thể cần **thông tin tốt nhất từ anh em của v**, hoặc một cấu trúc gộp bỏ đi đúng một nhánh. Phần sau sẽ trình bày cả hai kiểu.

## 4. Bài toán nền tảng: tổng khoảng cách từ mọi đỉnh

Cho cây n đỉnh, mỗi cạnh có độ dài 1. Cần tính:

**answer[u] = ∑ dist(u,x)** trên tất cả đỉnh x.

Vì dist(u,u)=0, việc cộng chính u không thay đổi kết quả.

### 4.1. Lượt dưới lên: size[u] và downSum[u]

Cố định gốc r=1. Định nghĩa:

- **size[u]** = số đỉnh thuộc subtree(u), kể cả u.
- **downSum[u]** = tổng khoảng cách từ u đến mọi đỉnh trong **subtree(u)**.

Với lá u:

**size[u]=1**, **downSum[u]=0**.

Với một đỉnh u có các con v:

**size[u] = 1 + ∑ size[v]**.

**downSum[u] = ∑ (downSum[v] + size[v])**.

Tại sao phải cộng thêm size[v]? Với mỗi đỉnh x trong subtree(v):

**dist(u,x) = 1 + dist(v,x)**.

Cộng qua **size[v]** đỉnh tạo ra **size[v]** đơn vị thêm vào tổng. Vì các cây con của u rời nhau và cùng với u phủ hết subtree(u), công thức đúng.

Với cây ví dụ:

| Đỉnh u | size[u] | downSum[u] |
| ---: | ---: | ---: |
| 4 | 1 | 0 |
| 5 | 1 | 0 |
| 7 | 1 | 0 |
| 6 | 2 | 1 |
| 2 | 3 | 2 |
| 3 | 3 | 3 |
| 1 | 7 | 11 |

Kiểm tra:

- downSum[2] = (0+1) của nhánh 4 + (0+1) của nhánh 5 = **2**.
- downSum[6] = (0+1) của nhánh 7 = **1**.
- downSum[3] = downSum[6]+size[6] = 1+2 = **3**.
- downSum[1] = (2+3)+(3+3)=**11**.

Vì subtree(root) chứa tất cả n đỉnh, ta đã có:

**answer[root] = downSum[root] = 11**.

Nhưng **downSum[2]=2 không phải answer[2]**: downSum[2] bỏ qua đỉnh 1,3,6,7 ở **ngoài subtree(2)**. Đây chính là thông tin lượt thứ hai phải bù vào.

### 4.2. Lượt trên xuống: đổi gốc từ u sang con v

Xét cạnh (u,v), với v là con của u theo gốc tạm thời.

Nếu cắt cạnh này, cây chia thành đúng hai thành phần:

- Thành phần chứa **v**: có **size[v]** đỉnh.
- Thành phần chứa **u**: có **n − size[v]** đỉnh.

Khi chuyển vị trí đo khoảng cách từ u sang v:

- Đối với mỗi đỉnh x trong **subtree(v)**, khoảng cách **giảm 1**, vì v gần x hơn u đúng một cạnh.
- Đối với mỗi đỉnh x ở **ngoài subtree(v)**, khoảng cách **tăng 1**, vì đường từ v đến x phải đi qua u.

Vậy:

**answer[v] = answer[u] − size[v] + (n−size[v])**,

hay công thức nổi tiếng:

**answer[v] = answer[u] + n − 2×size[v]**.

Đây không phải một mẹo nhớ công thức: nó xuất phát trực tiếp từ **phân hoạch cây thành hai phía của một cạnh**.

### 4.3. Truy vết lượt đổi gốc

Với n=7 và answer[1]=11:

| Chuyển từ cha sang con | size[con] | Công thức | Đáp án con |
| --- | ---: | --- | ---: |
| 1 → 2 | 3 | 11+7−2×3 | **12** |
| 1 → 3 | 3 | 11+7−2×3 | **12** |
| 2 → 4 | 1 | 12+7−2×1 | **17** |
| 2 → 5 | 1 | 12+7−2×1 | **17** |
| 3 → 6 | 2 | 12+7−2×2 | **15** |
| 6 → 7 | 1 | 15+7−2×1 | **20** |

Kết quả theo thứ tự đỉnh 1..7:

~~~text
answer = [11, 12, 12, 17, 17, 15, 20]
~~~

Kiểm tra trực tiếp từ đỉnh 2:

~~~text
Đến đỉnh:       1  2  3  4  5  6  7
Khoảng cách:    1  0  2  1  1  3  4
Tổng:           1+0+2+1+1+3+4 = 12
~~~

Đỉnh 1 có tổng khoảng cách **nhỏ nhất bằng 11** trong ví dụ, nên là một vị trí tốt nhất nếu mỗi đỉnh đại diện một điểm nhu cầu như nhau và mục tiêu là **giảm tổng khoảng cách**.

## 5. Chứng minh tính đúng cho tổng khoảng cách

Một chứng minh đầy đủ có hai tầng bất biến.

### Lượt 1: bất biến cây con

**Mệnh đề:** Sau khi xử lý u theo thứ tự từ dưới lên, size[u] và downSum[u] lần lượt bằng số đỉnh và tổng khoảng cách từ u đến mọi đỉnh trong subtree(u).

- **Cơ sở:** u là lá: subtree chỉ có chính u; size=1, khoảng cách đến chính nó là 0.
- **Quy nạp:** giả sử mệnh đề đúng với mọi con v của u. Các subtree(v) rời nhau; mỗi khoảng cách từ u đến x∈subtree(v) đúng bằng 1+dist(v,x). Tổng qua các nhánh và cộng chính u suy ra hai công thức ở mục 4.1.

Do đó lượt 1 đúng, và answer[root]=downSum[root] là tổng khoảng cách từ gốc tới mọi đỉnh.

### Lượt 2: bất biến toàn cây

**Mệnh đề:** Khi xử lý đỉnh u theo thứ tự cha trước con, answer[u] đã là tổng khoảng cách từ u đến mọi đỉnh toàn cây.

- **Cơ sở:** đúng ở root theo lượt 1.
- **Quy nạp:** xét con v của u. Cạnh (u,v) chia cây thành hai thành phần kích thước size[v] và n−size[v]. Chuyển từ u sang v làm tổng khoảng cách thay đổi đúng **−size[v]+(n−size[v])**. Vì answer[u] đúng, công thức tính answer[v] cũng đúng.
- Duyệt theo thứ tự cha trước con khiến mọi đỉnh được tính từ một cha đã có đáp án đúng.

Vậy sau hai lượt, **answer[u] đúng cho mọi đỉnh u**.

Chứng minh chỉ dựa vào **đường đi duy nhất** và **tính chất cắt một cạnh tách cây thành hai thành phần**. Nếu đồ thị có chu trình, không thể đơn giản nói mọi đỉnh trong một phía sẽ gần hơn đúng 1 sau khi đổi điểm xuất phát; công thức không còn được bảo đảm.

## 6. Bài toán thứ hai: đỉnh xa nhất từ mỗi đỉnh

Đặt:

**ecc[u] = max dist(u,x)** với x chạy qua tất cả đỉnh.

Đại lượng này gọi là **độ lệch tâm (eccentricity)** của đỉnh trong đồ thị. Nếu hỏi “mỗi đỉnh cách đỉnh xa nhất bao nhiêu cạnh?”, ta cần ecc[u] cho mọi u.

Với cây ví dụ:

~~~text
Đỉnh:          1  2  3  4  5  6  7
ecc[u]:        3  4  3  5  5  4  5
~~~

Không thể lấy đơn giản **ecc[con] = ecc[cha]+n−2×size[con]**: công thức đó dành cho **tổng khoảng cách**, không phải khoảng cách lớn nhất.

Ta cần biết cả **khoảng cách xa nhất đi xuống** và **khoảng cách xa nhất đi ra ngoài cây con**.

### 6.1. down[u] — khoảng cách xa nhất trong cây con

Định nghĩa **down[u]** là số cạnh lớn nhất từ u đến một đỉnh trong subtree(u). Cho phép chọn chính u nên down[u]≥0.

Với lá: **down[u]=0**.

Với u có các con v:

**down[u] = max(0, max(1 + down[v]))**.

Mỗi nhánh con tạo một ứng viên 1+down[v]. Cơ sở 0 biểu diễn đi tới chính u.

### 6.2. up[u] — khoảng cách xa nhất ra ngoài cây con

Định nghĩa **up[u]** là khoảng cách lớn nhất từ u đến một đỉnh **không thuộc subtree(u)**. Nếu ngoài subtree(u) không có đỉnh nào (đúng ở root), đặt **up[root]=−1** làm sentinel vì mọi khoảng cách thật đều không âm.

Xét một con v của u. Từ v, muốn đi đến một đỉnh nằm ngoài subtree(v), bước đầu phải đi lên u. Sau đó có ba khả năng:

1. Dừng tại **chính u**: thêm **1** cạnh từ v.
2. Đi tiếp tới một đỉnh **ngoài subtree(u)**: tổng là **1 + up[u]**.
3. Đi vào subtree của **một anh em w≠v**: tổng là **1 + (1 + down[w])**, tức **2 + down[w]**.

Vì vậy:

**up[v] = 1 + max(0, up[u], max_{w là con của u, w≠v}(1 + down[w]))**.

Nếu không có anh em, tập max qua anh em là rỗng và ta bỏ ứng viên ấy. **0** bảo đảm có thể chọn chính u; up[root]=−1 không tạo giá trị giả lớn hơn 0.

Cuối cùng:

**ecc[u] = max(down[u], up[u])**.

Mọi đỉnh khác u hoặc ở trong subtree(u) hoặc ở ngoài; hai giá trị bao phủ đúng hai nhóm ấy.

### 6.3. Vì sao không quét tất cả anh em mỗi lần?

Nếu tại mỗi u, với **mỗi con v** lại duyệt **mọi anh em của v** để lấy nhánh cao nhất còn lại, một đỉnh bậc lớn có thể làm tổng chi phí **O(deg(u)²)**. Cây dạng sao có một đỉnh bậc n−1, vì vậy cách làm đó có thể dẫn đến **O(n²)**.

Có hai cách tối ưu:

- Lưu **nhánh cao nhất và nhánh cao thứ hai**, có xét trường hợp hòa. Khi đang xử lý con v, dùng nhánh tốt nhất **không phải v**.
- Tổng quát hơn, tạo **prefix/suffix** trên danh sách đóng góp của các nhánh, để biết giá trị gộp của tất cả nhánh **trừ nhánh v** trong O(1).

Mã Java bên dưới dùng **hai giá trị cao nhất** vì phép gộp ở đây là max.

## 7. Cẩn thận với nhánh cao nhất và nhánh cao thứ hai

Giả sử với một đỉnh u, mỗi con v có đóng góp:

**branch[v] = 1 + down[v]**.

Ta duyệt các con và giữ:

- **best1:** giá trị nhánh lớn nhất.
- **best2:** giá trị nhánh lớn nhì theo **hai ứng viên khác nhau**, có thể bằng best1.
- **bestChild:** đỉnh con đã tạo best1.

Khi tính up[v]:

- Nếu v là bestChild, đóng góp từ các anh em tốt nhất là **best2**.
- Nếu v khác bestChild, dùng **best1**.

### Xử lý hòa là bắt buộc

Ví dụ u có hai con a,b với:

~~~text
branch[a] = 5
branch[b] = 5
~~~

Khi bỏ nhánh a, nhánh b vẫn đạt **5**. Nếu code chỉ giữ **hai giá trị phân biệt** (5 và một số nhỏ hơn), hoặc xóa mọi nhánh bằng giá trị max, sẽ tính sai up[a].

Hai giá trị cần là **hai nhánh tốt nhất xét theo số lần xuất hiện**, không phải hai giá trị số học khác nhau. Quy tắc cập nhật:

~~~text
nếu value > best1:
    best2 = best1
    best1 = value
    bestChild = v
ngược lại nếu value > best2:
    best2 = value
~~~

Với trường hợp value == best1, nhánh thứ hai vẫn có thể làm best2=best1. Nếu không có nhánh anh em, best2 giữ sentinel **−1**; công thức up[v] vẫn xử lý đúng vì có ứng viên 0 tương ứng với đỉnh u.

## 8. Java 17+: tính tổng khoảng cách và khoảng cách xa nhất cho mọi đỉnh

Chương trình dưới đây thực hiện **hai phép rerooting** trên cùng một cây không trọng số:

1. **Tổng khoảng cách:** một lượt tính size và downSum, một lượt áp dụng answer[child]=answer[parent]+n−2size[child].
2. **Khoảng cách lớn nhất:** một lượt tính downHeight, một lượt tính up bằng hai nhánh tốt nhất; cuối cùng ecc=max(downHeight,up).

Để tránh StackOverflowError trên cây đường thẳng rất dài, code **không dùng DFS đệ quy**. Nó duyệt từ gốc để tạo thứ tự **cha trước con**, sau đó đi ngược mảng thứ tự cho lượt dưới lên. Các đỉnh trong dữ liệu nhập và kết quả in có nhãn **1..n**; mảng Java sử dụng **chỉ số 0..n−1**.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class RerootingTreeDpDemo {

    record Result(int[] subtreeSizes, long[] distanceSums,
                  int[] eccentricities) {}

    // vertices: 1..n; every edge is {u,v}.
    static Result solve(int n, int[][] edges) {
        Objects.requireNonNull(edges, "edges");
        if (n <= 0 || edges.length != n - 1) {
            throw new IllegalArgumentException("Expected a nonempty tree");
        }

        List<List<Integer>> graph = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            graph.add(new ArrayList<>());
        }

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException("Invalid edge");
            }
            int u = edge[0] - 1;
            int v = edge[1] - 1;
            if (u < 0 || u >= n || v < 0 || v >= n || u == v) {
                throw new IllegalArgumentException("Invalid vertex");
            }
            graph.get(u).add(v);
            graph.get(v).add(u);
        }

        // Establish parent and an order with parent before child.
        int[] parent = new int[n];
        Arrays.fill(parent, -2);           // -2 = unvisited
        int[] order = new int[n];
        parent[0] = -1;                     // vertex 1 is a temporary root
        order[0] = 0;
        int visited = 1;

        for (int head = 0; head < visited; head++) {
            int u = order[head];
            for (int v : graph.get(u)) {
                if (v == parent[u]) {
                    continue;
                }
                if (parent[v] != -2) {
                    throw new IllegalArgumentException("Cycle or duplicate edge");
                }
                parent[v] = u;
                order[visited++] = v;
            }
        }

        if (visited != n) {
            throw new IllegalArgumentException("Disconnected graph");
        }

        int[] size = new int[n];
        long[] downSum = new long[n];
        int[] downHeight = new int[n];

        // Pass 1: children are processed before their parent.
        for (int k = n - 1; k >= 0; k--) {
            int u = order[k];
            size[u] = 1;
            for (int v : graph.get(u)) {
                if (parent[v] != u) {
                    continue;
                }
                size[u] += size[v];
                downSum[u] += downSum[v] + size[v];
                downHeight[u] = Math.max(
                        downHeight[u], 1 + downHeight[v]);
            }
        }

        long[] distanceSum = new long[n];
        distanceSum[0] = downSum[0];

        int[] up = new int[n];
        Arrays.fill(up, -1);                // no outside node for root

        // Pass 2: parent is processed before its children.
        for (int k = 0; k < n; k++) {
            int u = order[k];

            int best1 = -1;
            int best2 = -1;
            int bestChild = -1;
            for (int v : graph.get(u)) {
                if (parent[v] != u) {
                    continue;
                }
                int branch = 1 + downHeight[v];
                if (branch > best1) {
                    best2 = best1;
                    best1 = branch;
                    bestChild = v;
                } else if (branch > best2) {
                    best2 = branch;
                }
            }

            for (int v : graph.get(u)) {
                if (parent[v] != u) {
                    continue;
                }

                // Moving the root over an edge.
                distanceSum[v] = distanceSum[u]
                        + (long) n - 2L * size[v];

                // Best path via parent or another sibling subtree.
                int sibling = (v == bestChild) ? best2 : best1;
                up[v] = 1 + Math.max(
                        0, Math.max(up[u], sibling));
            }
        }

        int[] eccentricity = new int[n];
        for (int i = 0; i < n; i++) {
            eccentricity[i] = Math.max(downHeight[i], up[i]);
        }

        return new Result(size, distanceSum, eccentricity);
    }

    public static void main(String[] args) {
        int[][] edges = {
                {1, 2}, {1, 3}, {2, 4},
                {2, 5}, {3, 6}, {6, 7}
        };

        Result result = solve(7, edges);
        System.out.println("Subtree sizes (root=1): "
                + Arrays.toString(result.subtreeSizes()));
        System.out.println("Distance sums: "
                + Arrays.toString(result.distanceSums()));
        System.out.println("Eccentricities: "
                + Arrays.toString(result.eccentricities()));

        int minVertex = 0;
        for (int i = 1; i < 7; i++) {
            if (result.distanceSums()[i]
                    < result.distanceSums()[minVertex]) {
                minVertex = i;
            }
        }
        System.out.println("Min total distance: vertex "
                + (minVertex + 1)
                + " (" + result.distanceSums()[minVertex] + ")");

        int minEccentricity = Integer.MAX_VALUE;
        List<Integer> centers = new ArrayList<>();
        for (int i = 0; i < 7; i++) {
            int e = result.eccentricities()[i];
            if (e < minEccentricity) {
                minEccentricity = e;
                centers.clear();
            }
            if (e == minEccentricity) {
                centers.add(i + 1);
            }
        }
        System.out.println("Min eccentricity: "
                + minEccentricity + " at vertices " + centers);

        Result single = solve(1, new int[][] {});
        System.out.println("Single vertex: sums="
                + Arrays.toString(single.distanceSums())
                + ", eccentricities="
                + Arrays.toString(single.eccentricities()));
    }
}
~~~

Lưu tệp **RerootingTreeDpDemo.java**, biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac RerootingTreeDpDemo.java
java RerootingTreeDpDemo
~~~

**Đầu ra chính xác:**

~~~text
Subtree sizes (root=1): [7, 3, 3, 1, 1, 2, 1]
Distance sums: [11, 12, 12, 17, 17, 15, 20]
Eccentricities: [3, 4, 3, 5, 5, 4, 5]
Min total distance: vertex 1 (11)
Min eccentricity: 3 at vertices [1, 3]
Single vertex: sums=[0], eccentricities=[0]
~~~

### Điểm thiết kế đáng chú ý

- **solve** kiểm tra n≥1, đúng n−1 cạnh và chỉ số đỉnh nằm trong [1,n]. Sau khi dựng các cạnh, việc duyệt với mảng parent giúp phát hiện cạnh lặp/chu trình và cây không liên thông, thay vì âm thầm dùng công thức cây trên dữ liệu sai.
- **order** được tạo bằng duyệt theo hàng đợi ngay trong mảng; mỗi đỉnh xuất hiện đúng một lần và **cha luôn đứng trước con**.
- Lượt đi **ngược order** tính size/downSum/downHeight cho từng đỉnh sau khi các con đã có kết quả.
- Lượt đi **thuận order** xử lý từng cha u rồi truyền thông tin tới con v; không gọi lại solve cho mỗi đỉnh.
- **distanceSum** dùng kiểu **long**, vì tổng khoảng cách trên cây đường thẳng có thể đạt **n(n−1)/2**, vượt int khi n đủ lớn.
- **downHeight/up/eccentricity** dùng int vì mọi khoảng cách theo số cạnh của cây n đỉnh không vượt n−1, miễn n nằm trong giới hạn mảng của Java.
- **best1,best2** giữ hai ứng viên từ **hai nhánh con khác nhau**; hai nhánh có độ cao bằng nhau vẫn được tính đúng.
- **up[root]=−1** biểu thị “không có đỉnh ngoài subtree(root)”. Các đỉnh khác dùng công thức có ứng viên 0 cho chính đỉnh cha nên không sinh kết quả âm.
- Hai mảng kết quả có ý nghĩa khác nhau: **distanceSums** tối thiểu hóa tổng khoảng cách (kiểu trung vị cây), còn **eccentricities** tối thiểu hóa khoảng cách xa nhất (kiểu tâm cây); các đỉnh tối ưu có thể khác nhau.

**Tổng chi phí:** dựng danh sách kề O(n), lượt order O(n), lượt hậu tự O(n), lượt tiền tự O(n); tổng **O(n) thời gian và O(n) bộ nhớ** cho n đỉnh cây. Đây là cải thiện so với n lần BFS/DFS, tức O(n²) trên cây.

## 9. Công thức tổng khoảng cách với cạnh có trọng số

Bây giờ cạnh (u,v) có độ dài **length(u,v)** thay vì luôn 1. Mỗi đỉnh vẫn có nhu cầu bằng 1. Định nghĩa:

**answer[u] = ∑ weightedDist(u,x)**.

Công thức lượt dưới lên:

**downSum[u] = ∑ (downSum[v] + size[v] × length(u,v))**.

Khi đổi gốc qua cạnh từ u xuống v:

- Mỗi x trong subtree(v) giảm khoảng cách **length(u,v)**.
- Mỗi x ở ngoài tăng đúng **length(u,v)**.

Do đó:

**answer[v] = answer[u] + (n − 2×size[v]) × length(u,v)**.

**size[v]** vẫn chỉ đếm số đỉnh, không phụ thuộc trọng số cạnh. Trọng số chỉ thay đổi mức tăng/giảm khoảng cách.

### Ví dụ cạnh có độ dài

~~~text
       1
      / \
    (2) (3)
    /     \
   2       3

length(1,2)=2; length(1,3)=3
~~~

Với ba đỉnh và nhu cầu ngang nhau:

- answer[1] = dist(1,2)+dist(1,3)=2+3=**5**.
- size[2]=size[3]=1.
- answer[2]=5+(3−2×1)×2=**7**; tính trực tiếp: dist(2,1)=2, dist(2,3)=5 → 7.
- answer[3]=5+(3−2×1)×3=**8**; tính trực tiếp: 3+5=8.

Công thức đúng với khoảng cách là tổng trọng số trên đường đi duy nhất; khi dùng “độ dài” theo nghĩa thông thường, giả thiết trọng số cạnh **không âm** giúp giữ ý nghĩa khoảng cách hình học.

### Nếu mỗi đỉnh có trọng số nhu cầu

Giả sử mỗi đỉnh x có trọng số **demand[x]≥0** (ví dụ số cư dân) và mục tiêu là:

**cost[u] = ∑ demand[x] × dist(u,x)**.

Lượt dưới lên lưu:

**subDemand[u] = demand[u] + ∑ subDemand[v]**,

**subCost[u] = ∑ (subCost[v] + subDemand[v] × length(u,v))**.

Gọi **totalDemand = ∑ demand[x]**. Công thức đổi gốc:

**cost[v] = cost[u] + (totalDemand − 2×subDemand[v]) × length(u,v)**.

Để hiểu, chỉ cần thay “mỗi đỉnh đóng góp 1” bằng “mỗi đỉnh đóng góp demand[x]” khi cộng phần tăng và giảm.

Ví dụ cây ba đỉnh ở trên, nếu demand=(1,2,4):

- cost[1] = 1×0 + 2×2 + 4×3 = **16**.
- totalDemand=7, subDemand[2]=2, subDemand[3]=4.
- cost[2] = 16+(7−2×2)×2=**22**.
- cost[3] = 16+(7−2×4)×3=**13**.

Nếu mỗi đỉnh là ứng viên mở cơ sở dịch vụ, tối ưu hóa **tổng khoảng cách có trọng số nhu cầu** có thể cho vị trí khác với tối ưu hóa tổng khoảng cách không trọng số. Cần dùng kiểu số đủ rộng, vì phép nhân nhu cầu × độ dài và tổng của nhiều đỉnh có thể vượt long nếu giới hạn đầu vào quá lớn.

## 10. Rerooting tổng quát: không phải phép gộp nào cũng có phép trừ

Công thức tổng khoảng cách đơn giản vì khi đổi gốc, ta có thể tách tổng đóng góp thành hai phía và xác định chính xác mức chênh lệch. Nhưng nhiều bài toán dùng phép tổng hợp như **max**, **min**, **tích**, hoặc một **cấu trúc DP nhiều trường** không có phép toán nghịch đảo đủ dùng.

Ví dụ để tính ecc[u], biết **max của mọi nhánh** chưa đủ để xác định max khi **bỏ một nhánh** nếu nhánh đó đang là lớn nhất. Cần best2 hoặc dữ liệu prefix/suffix.

### 10.1. Tư duy thông điệp theo cạnh có hướng

Với một cạnh vô hướng u—v, tưởng tượng hai thông điệp:

- **msg(u→v)**: trạng thái từ **phía u** truyền sang phía v khi cắt cạnh u—v.
- **msg(v→u)**: trạng thái từ **phía v** truyền sang phía u.

Mỗi thông điệp chỉ tổng hợp những đỉnh nằm trong thành phần ở **phía gửi** sau khi cắt cạnh. Để tính msg(u→v), đỉnh u được dùng **thông tin từ mọi hàng xóm khác v**, cộng đóng góp của chính u, rồi chuyển qua cạnh (u,v) nếu cần thay đổi tọa độ/trọng số.

Điểm này khắc phục lỗi thường gặp của rerooting: **không gửi lại thông tin của chính v cho v**. Nếu tính msg(u→v) từ tất cả hàng xóm của u mà không bỏ nhánh v, dữ liệu của subtree(v) đi vòng trở lại và bị **đếm trùng**.

### 10.2. Monoid gộp nhánh

Giả sử có một phép gộp **⊕** trên các trạng thái nhánh, thỏa:

- **Kết hợp (associative):** (a⊕b)⊕c = a⊕(b⊕c).
- Có **phần tử đơn vị e:** e⊕a = a⊕e = a.

Đây là cấu trúc thường gọi là **monoid**. Phép gộp **không nhất thiết giao hoán**; nếu thứ tự hàng xóm có ý nghĩa, phải thống nhất thứ tự ấy. Các ví dụ quen thuộc:

- Tổng số lượng: ⊕ là cộng, e=0.
- Max: ⊕ là max, e là giá trị “không có đóng góp”, thường là −∞ hoặc một sentinel được xử lý đúng.
- Min: ⊕ là min, e=+∞.
- Cặp nhiều trường: gộp theo từng quy tắc thích hợp, miễn bảo đảm tính kết hợp và trường hợp cơ sở.

Với một đỉnh u có các đóng góp nhánh **a₀,a₁,...,a_{d−1}**, muốn gửi tới hàng xóm thứ i phải biết giá trị:

**a₀ ⊕ ... ⊕ a_{i−1} ⊕ a_{i+1} ⊕ ... ⊕ a_{d−1}**.

Nếu làm bằng cách quét lại tất cả nhánh cho **mỗi i**, chi phí mỗi đỉnh là O(d²). Prefix/suffix cho phép loại đúng một nhánh trong O(1) sau O(d) tiền xử lý.

## 11. Prefix/suffix để bỏ một nhánh trong O(1)

Cho mảng đóng góp **a[0..d−1]** ở đỉnh u.

Xây các tích lũy tiền tố:

**prefix[0] = e**,

**prefix[i+1] = prefix[i] ⊕ a[i]**.

Xây các tích lũy hậu tố:

**suffix[d] = e**,

**suffix[i] = a[i] ⊕ suffix[i+1]**.

Khi muốn bỏ nhánh i:

**without[i] = prefix[i] ⊕ suffix[i+1]**.

Để tính thông điệp từ u sang hàng xóm i, gộp tiếp **trạng thái của chính u** và áp dụng **hàm chuyển qua cạnh** nếu trạng thái đo tại u khác trạng thái đo tại đầu bên kia.

Ví dụ đơn giản với phép max:

~~~text
Đóng góp của các nhánh tại u:
a = [4, 7, 7, 2]

Bỏ nhánh 0: max([7,7,2]) = 7
Bỏ nhánh 1: max([4,7,2]) = 7
Bỏ nhánh 2: max([4,7,2]) = 7
Bỏ nhánh 3: max([4,7,7]) = 7
~~~

Hai nhánh cùng đạt max=7. Prefix/suffix vẫn trả đúng **7** sau khi bỏ **một** trong hai nhánh, không nhầm với việc loại tất cả nhánh có giá trị 7.

### Giả mã rerooting trên mọi hàng xóm

~~~text
# contribution(v -> u) là thông tin phía v,
# đã quy đổi để gộp tại u.

for u theo thứ tự từ gốc xuống:
    neighbors = danh sách hàng xóm của u
    a[i] = contribution(neighbors[i] -> u)

    prefix[0] = identity
    for i = 0..d-1:
        prefix[i+1] = merge(prefix[i], a[i])

    suffix[d] = identity
    for i = d-1..0:
        suffix[i] = merge(a[i], suffix[i+1])

    answer[u] = finish(merge(base(u), prefix[d]))

    for i = 0..d-1:
        allExceptI = merge(prefix[i], suffix[i+1])
        stateAtU = merge(base(u), allExceptI)
        message(u -> neighbors[i]) =
            liftAcrossEdge(stateAtU, edge(u, neighbors[i]))
~~~

**Đây là giả mã mô tả phép gộp thông điệp**, không phải chương trình Java độc lập. Việc thực thi hai lượt phải bảo đảm thông điệp từ **các con** được tính ở lượt dưới lên và thông điệp từ **cha** tới u được truyền đúng ở lượt trên xuống. Khi soạn một hiện thực tổng quát, không thể giả định tất cả thông điệp đều đã có từ đầu.

Nếu phép gộp không giao hoán, giữ **thứ tự các phần đóng góp** nhất quán khi đặt base(u), tính answer[u] và tính thông điệp loại một nhánh. Cách chèn base(u) vào đầu mảng ở giả mã là một quy ước cụ thể, không phải hợp đồng chung cho mọi bài toán.

### Chi phí

Tại mỗi đỉnh bậc d:

- Tạo mảng đóng góp: O(d).
- Xây prefix/suffix: O(d).
- Tính d giá trị “bỏ một nhánh”: O(d).
- Xử lý trạng thái của u: O(d) hoặc tốt hơn.

Trong cây, tổng bậc bằng **2(n−1)**. Vậy tổng số bước **O(∑deg(u)) = O(n)** nếu merge/lift/finish là O(1). Bộ nhớ lưu adjacency, trạng thái, prefix/suffix lớn nhất trong quá trình xử lý là **O(n)**.

Không được kết luận O(n) cho mọi rerooting mà không kiểm tra **chi phí merge**: nếu mỗi trạng thái là một tập lớn và việc hợp nhất phải sao chép toàn bộ, tổng độ phức tạp có thể cao hơn.

## 12. Ví dụ trạng thái nhiều trường: (số đỉnh, tổng khoảng cách)

Rerooting có thể nhìn dưới dạng **tóm tắt một thành phần của cây**. Với mỗi thành phần được quan sát từ một đỉnh u, lưu cặp:

**State = (count, distanceSum)**,

trong đó count là số đỉnh của thành phần, distanceSum là tổng khoảng cách từ u đến tất cả đỉnh trong thành phần.

Hai thành phần **rời nhau** cùng đo khoảng cách tại u được gộp bằng:

**merge((c₁,s₁), (c₂,s₂)) = (c₁+c₂, s₁+s₂)**.

Trạng thái của **chính đỉnh u** là **(1,0)**. Nếu một thông điệp từ phía v được mô tả tương đối với v và cạnh (u,v) có độ dài w, khi chuyển đóng góp đó về u:

**lift((c,s),w) = (c, s + c×w)**.

Tại u, tổng hợp **(1,0)** với tất cả đóng góp đã lift từ các hàng xóm, ta thu được:

- count = n;
- distanceSum = tổng khoảng cách từ u tới toàn cây.

Thiết kế này có lợi thế là dùng lại được cấu trúc tổng quát **gộp đóng góp từ mọi phía**. Công thức answer[v]=answer[u]+n−2size[v] là một **lối tắt đại số đặc biệt** cho bài tổng khoảng cách với trọng số cạnh bằng 1; khi học rerooting mới, mẫu thông điệp thường giúp thiết kế bài phức tạp hơn.

### Cách xác định base và identity

- **base(u)=(1,0)**: chứa đúng bản thân đỉnh u.
- **identity=(0,0)**: thành phần rỗng, dùng cho gộp nhánh.
- Chuyển qua cạnh độ dài w chỉ cộng **c×w** nếu thành phần có c đỉnh; với c=0, lift(identity,w) vẫn là identity.

Sự phân biệt giữa **đơn vị của phép merge** và **đóng góp của đỉnh** là quan trọng. Nếu coi identity là (1,0), mỗi lần gộp có thể tự sinh thêm một đỉnh ảo và làm count sai.

## 13. Những bài tương tự và cách chọn kiểu DP

| Mục tiêu ở mỗi đỉnh u | Thông tin cần từ nhánh | Kỹ thuật đổi gốc phù hợp |
| --- | --- | --- |
| Tổng khoảng cách đến mọi đỉnh | size, downSum, tổng tại root | Công thức dịch gốc với n−2size |
| Tổng khoảng cách có trọng số cạnh | size, weighted downSum | Cộng (n−2size)×length cạnh |
| Tổng khoảng cách có trọng số nhu cầu ở đỉnh | subDemand, subCost, totalDemand | Cộng (totalDemand−2subDemand)×length |
| Khoảng cách xa nhất tới một đỉnh | downHeight, up, max nhánh trừ một con | Hai max lớn nhất hoặc prefix/suffix |
| Tổng đóng góp từ những nhánh không chứa một đỉnh con | Trạng thái theo từng cạnh | Prefix/suffix loại một nhánh |
| Tối ưu theo cây con nhưng cần kết quả toàn cây | DP trong cây con và thông tin ngoài cây con | Hai lượt truyền đóng góp |
| Câu hỏi dùng các phép merge khác nhau | State phù hợp với phép merge | Thiết kế merge/lift/base và chứng minh |

**Không phải mọi bài ở bảng đều có cùng công thức.** Hãy bắt đầu từ câu hỏi “nếu cắt cạnh u—v, đóng góp từ hai phía được mô tả bằng những đại lượng nào?” rồi viết công thức đúng cho đại lượng đó.

### Liên hệ với đường kính cây

Với cây không trọng số, một cách khác để tìm **ecc[u] cho mọi u** là:

1. Chọn một đỉnh bất kỳ, BFS tìm một đầu mút a của đường kính.
2. BFS từ a tìm đầu mút b của đường kính; lưu distA[u].
3. BFS từ b lưu distB[u].
4. Với cây không trọng số, **ecc[u] = max(distA[u],distB[u])**.

Cách này cũng O(n) và ngắn cho riêng bài **khoảng cách xa nhất**. Tuy nhiên, nó dựa trên tính chất đặc biệt của **đường kính cây**; rerooting down/up mang tính tổng quát hơn và dễ mở rộng sang các trạng thái cần thông tin khác. Không suy từ mẹo đầu mút đường kính rằng mọi phép gộp cây đều có thể giải bằng hai BFS.

## 14. Các bẫy thường gặp khi đổi gốc

1. **Nhầm downSum[u] với answer[u].** downSum chỉ tính trong subtree(u) theo gốc cố định, còn answer phải tính toàn cây.
2. **Không tách đúng hai phía cạnh u—v.** Khi v là con u, phía v có size[v] đỉnh, phía còn lại có n−size[v].
3. **Đảo dấu công thức tổng khoảng cách.** Di chuyển u→v làm phía subtree(v) gần hơn và phía ngoài xa hơn, nên **+n−2size[v]**, không phải **−n+2size[v]**.
4. **Dùng size[u] thay size[v].** Phần được gần hơn chính là subtree(v) khi đổi gốc qua cạnh cha–con.
5. **Tính size sai khi cây sâu.** Phải xử lý các con trước cha, tức postorder hoặc order đảo ngược.
6. **Chạy lại DFS với mỗi đỉnh dù đã có công thức dịch gốc.** Khi n lớn, dễ thành O(n²).
7. **Quên ảnh hưởng từ cha trong ecc[u].** Chỉ dùng downHeight có thể đánh giá thấp các đỉnh ở ngoài subtree(u).
8. **Lấy max của mọi anh em lại cho từng con.** Đỉnh bậc lớn có thể gây O(n²); dùng best1/best2 hoặc prefix/suffix.
9. **Không xử lý hai nhánh bằng max.** Nếu bỏ một nhánh max nhưng còn nhánh max khác, đáp án vẫn phải giữ max đó.
10. **Đưa chính nhánh v vào msg(u→v).** Dữ liệu của v bị gửi ngược lại cho v, dẫn đến đếm trùng hoặc tự phụ thuộc.
11. **Xem mọi phép gộp đều có phép trừ.** Max/min không có nghịch đảo đơn giản; cần loại nhánh bằng cấu trúc thích hợp.
12. **Dùng DFS đệ quy không kiểm soát độ sâu.** Cây chuỗi n đỉnh có độ sâu O(n), có thể gây StackOverflowError trong Java.
13. **Dùng int cho tổng khoảng cách trên cây rất dài.** Cỡ n² có thể vượt giới hạn int; dùng long hoặc rộng hơn theo ràng buộc.
14. **Quên trọng số cạnh trong cả hai lượt.** Với length=w, phải cộng w×size[v] và đổi gốc thêm w×(n−2size[v]).
15. **Nhầm trọng số nhu cầu với kích thước đỉnh.** Nếu mỗi đỉnh có nhu cầu riêng, cần subDemand thay size.
16. **Không kiểm tra đầu vào là cây.** Đồ thị có chu trình, cạnh lặp hoặc mất liên thông không tuân theo cùng công thức.
17. **Nhầm n=1 là không có đáp án.** Với cây một đỉnh, tổng khoảng cách và ecc đều bằng 0.
18. **Lẫn khoảng cách theo cạnh và theo số đỉnh.** Bài học dùng **số cạnh**; nếu đề đếm số đỉnh trên đường đi, phải chuyển quy ước.
19. **Cho rằng mọi phép gộp đều giao hoán.** Prefix/suffix chỉ yêu cầu kết hợp; với phép không giao hoán phải giữ thứ tự đúng.
20. **Không định nghĩa phần tử đơn vị và base.** Identity “rỗng” khác đóng góp “bản thân đỉnh” trong nhiều DP.
21. **Lưu tất cả prefix/suffix cho mọi đỉnh mà không tính bộ nhớ.** Có thể dùng bộ nhớ O(n) tổng hoặc cấp phát tạm theo từng đỉnh; tránh tạo cấu trúc bậc hai không cần thiết.
22. **Nhầm câu hỏi tối thiểu tổng khoảng cách với tối thiểu khoảng cách xa nhất.** Hai hàm mục tiêu khác nhau, không được dùng chung đáp án nếu chưa chứng minh.

## 15. Phân tích độ phức tạp và các trường hợp đặc biệt

### Một BFS/DFS cho từng gốc

Trên cây n đỉnh có n−1 cạnh, BFS/DFS từ một gốc mất **O(n)**. Lặp lại cho n gốc là:

**n × O(n) = O(n²)**.

Nếu n=100.000, điều này thường không khả thi.

### Hai lượt rerooting

- Dựng danh sách kề: O(n).
- Tạo parent và order: O(n).
- Lượt tính subtree DP: O(n).
- Lượt truyền đáp án: O(n).
- Tổng công việc duyệt cạnh (hai chiều): O(n).

Tổng thời gian **O(n)**, bộ nhớ **O(n)** cho adjacency, order, parent và các mảng DP. Nếu dùng đệ quy, cần tính thêm ngăn xếp O(h) với h là chiều cao cây; bản Java dùng vòng lặp và mảng order thay cho ngăn xếp đệ quy.

### Cây đường thẳng

~~~text
1 - 2 - 3 - 4 - 5
~~~

Tổng khoảng cách:

~~~text
Đỉnh:         1  2  3  4  5
Tổng dist:   10  7  6  7 10
Ecc:          4  3  2  3  4
~~~

Đỉnh giữa có tổng khoảng cách nhỏ nhất bằng 6 và eccentricity nhỏ nhất bằng 2. Với cây đường thẳng dài n, tổng khoảng cách tại một đầu là n(n−1)/2, cho thấy lý do dùng long.

### Cây dạng sao

~~~text
    2
    |
3 - 1 - 4
    |
    5
~~~

- Đỉnh 1 có tổng khoảng cách **4** và ecc **1**.
- Mỗi lá có tổng khoảng cách **1+3×2=7** và ecc **2**.

Đỉnh 1 có bậc cao, nên đây là bài kiểm thử giúp phát hiện cách lấy max anh em O(deg²) và lỗi khi các nhánh có **cùng chiều cao**.

### Cây một đỉnh

Với n=1, không có cạnh. size[1]=1, downSum[1]=answer[1]=downHeight[1]=ecc[1]=0; up[root] chỉ là sentinel. Không có lượt đổi gốc sang đỉnh con nào, kết quả vẫn hợp lệ.

### Cây không phải dạng tĩnh

Nếu có nhiều lần **thêm/xóa cạnh** và vẫn phải duy trì kết quả sau mỗi cập nhật, rerooting O(n) mỗi lần xây lại có thể không đủ. Khi đó cần đánh giá cấu trúc động như link-cut tree hoặc một thiết kế khác tùy phép toán và giới hạn. Không suy ra rằng rerooting tĩnh hỗ trợ cập nhật cạnh O(1).

## 16. Kiểm thử bằng brute force trên cây nhỏ

Tính đúng của rerooting có thể được kiểm tra tự động bằng một cách đơn giản nhưng chậm:

1. Với mỗi đỉnh u, chạy **BFS** trên cây không trọng số.
2. Từ mảng dist[v], tính **sumDist[u] = ∑dist[v]**.
3. Tính **ecc[u] = max dist[v]**.
4. So các kết quả brute force với hai mảng rerooting.

Với cây nhỏ, chi phí **O(n²)** hoàn toàn chấp nhận được để làm **oracle kiểm thử**. Khi chạy production với cây lớn, chỉ dùng rerooting O(n).

Bộ ca kiểm thử nên có:

| Ca | Điều cần xác minh |
| --- | --- |
| n=1 | Tổng và ecc đều 0; không đọc cạnh |
| Cây chỉ có 2 đỉnh | Cả hai tổng bằng 1, ecc bằng 1 |
| Đường thẳng có độ dài chẵn/lẻ | Kết quả đối xứng; tâm đúng |
| Cây sao | Nhánh cao nhất bị hòa; best2 đúng |
| Cây mất cân đối như ví dụ 7 đỉnh | Thông tin up truyền qua nhiều cấp |
| Cây ngẫu nhiên n nhỏ | Rerooting trùng kết quả BFS từng gốc |
| Cạnh lặp, vòng tự nối, đỉnh ngoài phạm vi | Trả lỗi đầu vào thay vì đáp án giả |
| Đồ thị không liên thông | Trả lỗi vì không phải một cây |
| n rất lớn, cây thành một đường thẳng | Không tràn stack nếu dùng thứ tự lặp |
| Tính sum với length và demand | So với đường đi có trọng số ở n nhỏ |

Đối với bài tổng khoảng cách, còn có một bất biến toàn cục hữu ích:

**∑_u answer[u] = 2 × ∑_{unordered pairs {u,v}} dist(u,v)**.

Mỗi cặp đỉnh không thứ tự đóng góp khoảng cách **hai lần** trong tổng của mọi gốc — một lần khi lấy u làm gốc, một lần khi lấy v làm gốc. Bất biến này hỗ trợ kiểm tra toàn cục nhưng **không thay thế** việc đối chiếu từng đỉnh.

## 17. Câu hỏi tự kiểm tra và bài tập

**Câu 1.** Với cây bảy đỉnh ở mục 1, subtree(6) có bao nhiêu đỉnh và downSum[6] bằng bao nhiêu?  
**Đáp án:** subtree(6)={6,7}, nên size[6]=2 và downSum[6]=1.

**Câu 2.** Nếu answer[1]=11, n=7, size[3]=3, thì answer[3] là bao nhiêu?  
**Đáp án:** 11+7−2×3=**12**.

**Câu 3.** Tại sao khi đổi gốc từ u sang v, các đỉnh trong subtree(v) gần hơn đúng một cạnh?  
**Đáp án:** Đường đi duy nhất từ u đến bất kỳ x trong subtree(v) đều đi qua cạnh u—v rồi mới tới x. Bắt đầu tại v loại bỏ chính cạnh ấy.

**Câu 4.** Cây hình sao n đỉnh có tâm c và n−1 lá. Tổng khoảng cách từ tâm và từ một lá lần lượt bằng bao nhiêu?  
**Đáp án:** Tâm bằng **n−1**. Lá bằng 1 tới tâm cộng 2 tới n−2 lá khác, tức **2n−3**.

**Câu 5.** Với n=5 trên đường thẳng 1—2—3—4—5, tổng khoảng cách tại đỉnh 3 bằng bao nhiêu?  
**Đáp án:** 2+1+0+1+2=**6**.

**Câu 6.** Trong bài ecc[u], tại sao chỉ giữ downHeight[u] là thiếu?  
**Đáp án:** Đỉnh xa nhất có thể nằm ngoài subtree(u), qua phía cha; cần up[u].

**Câu 7.** Nếu u có hai con a,b cùng branch=5, khi tính up[a] thì nhánh anh em tốt nhất là bao nhiêu?  
**Đáp án:** Vẫn **5** từ b, không được coi là không còn nhánh max.

**Câu 8.** Với cạnh u—v dài w và v là con u, công thức tổng khoảng cách thay đổi thế nào?  
**Đáp án:** **answer[v] = answer[u] + (n−2size[v])×w**.

**Câu 9.** Nếu mỗi đỉnh x có demand[x], trong công thức dịch gốc thay n và size[v] bằng những đại lượng nào?  
**Đáp án:** Thay n bằng **totalDemand**, thay size[v] bằng **subDemand[v]**.

**Câu 10.** Trong phép merge=max, tại sao không thể lấy tổng toàn bộ rồi “trừ đóng góp của nhánh v” như phép cộng?  
**Đáp án:** Max không có phép trừ khôi phục max của các phần tử còn lại. Phải biết nhánh lớn thứ hai hoặc dùng prefix/suffix.

**Câu 11.** Tại đỉnh có d hàng xóm, nếu tính riêng giá trị bỏ từng nhánh bằng cách quét lại d−1 nhánh, chi phí là gì?  
**Đáp án:** O(d²). Prefix/suffix xử lý mọi nhánh trong O(d) khi merge O(1).

**Câu 12.** Vì sao rerooting thường làm hai lượt thay vì chỉ từ lá lên gốc?  
**Đáp án:** Lượt dưới lên chỉ biết đóng góp từ cây con. Lượt trên xuống mang thêm thông tin ngoài cây con để tính được kết quả toàn cây tại từng đỉnh.

**Câu 13.** Nếu đề chỉ cần tổng khoảng cách từ một đỉnh duy nhất, có nhất thiết làm rerooting không?  
**Đáp án:** Không. Một BFS/DFS O(n) từ đỉnh đó là đủ trong cây không trọng số.

**Câu 14.** Nếu đồ thị có một chu trình, có dùng ngay size[v] để xác định đúng phía được gần hơn khi đổi gốc không?  
**Đáp án:** Không. Cắt một cạnh trên chu trình không chia đồ thị thành hai thành phần, nên lập luận n−2size không áp dụng trực tiếp.

### Bài tập mở rộng

1. Cài **tổng khoảng cách có trọng số cạnh** cho mọi đỉnh, trả long[] và kiểm tra bằng DFS từng gốc trên n nhỏ.
2. Mỗi đỉnh có demand[x], tính **tổng chi phí có trọng số** cho mọi vị trí đặt trạm; tìm tất cả đỉnh tối ưu.
3. Thực hiện rerooting ecc[u] bằng **prefix/suffix max** thay cho best1/best2 và so với đầu mút đường kính cây.
4. Viết một khung **message passing** với State=(count,sumDistance), merge/lift/base và kiểm tra mỗi thông điệp chỉ tính đỉnh ở **một phía cạnh**.
5. Với cây n=100.000 đường thẳng, xác minh phiên bản dùng thứ tự lặp không cần đệ quy sâu và tổng khoảng cách dùng kiểu long.

## 18. Ghi nhớ

**Rerooting DP** không phải “đặt gốc mới rồi chạy DFS lại n lần”. Đó là kỹ thuật **tái sử dụng thông tin** giữa hai gốc kề nhau:

- **Chọn một gốc tạm thời**, dựng parent và thứ tự duyệt.
- **Lượt dưới lên** tính trạng thái của từng cây con.
- **Lượt trên xuống** truyền thông tin toàn cây hoặc phần nằm ngoài cây con.
- Với tổng khoảng cách không trọng số: **answer[v] = answer[u] + n − 2×size[v]**.
- Với cạnh độ dài w và nhu cầu ở đỉnh: **cost[v] = cost[u] + (totalDemand−2×subDemand[v])×w**.
- Với khoảng cách xa nhất: **ecc[u] = max(down[u],up[u])**, và khi truyền up phải **loại đúng nhánh con hiện tại**.
- Với phép gộp không có nghịch đảo, dùng **hai nhánh tốt nhất** hoặc **prefix/suffix** để loại một đóng góp trong O(1).
- Trên cây tĩnh, khi mỗi lần gộp có chi phí O(1), hai lượt đủ để tính cho **mọi đỉnh trong O(n) thời gian, O(n) bộ nhớ**.

Điều quan trọng nhất cần hiểu là **mỗi cạnh chia cây thành hai phía**, và khi đổi gốc từ đầu này sang đầu kia, ta phải biết **đóng góp từ cả hai phía**, không được để thông tin của nhánh đang xét tự đi vòng trở lại chính nó.

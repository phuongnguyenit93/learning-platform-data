# Biểu diễn đồ thị theo danh sách kề hoặc ma trận

Đồ thị (*graph*) là mô hình gồm **tập đỉnh** (*vertices*) và **tập cạnh** (*edges*). Trong các bài toán như tìm đường, duyệt mạng lưới, phụ thuộc giữa tác vụ, quan hệ bạn bè hoặc lịch trình, thuật toán cần biết **đỉnh nào kết nối với đỉnh nào**. Hai cách lưu trữ phổ biến là **danh sách kề** (*adjacency list*) và **ma trận kề** (*adjacency matrix*).

Bài học này tập trung vào **biểu diễn đồ thị như một cấu trúc dữ liệu hỗ trợ thuật toán**: cách xây dựng, tra cứu, thêm/xóa cạnh, duyệt hàng xóm, ảnh hưởng đến BFS/DFS, chi phí bộ nhớ và cách chọn theo dữ liệu. Không có cách biểu diễn nào tối ưu cho mọi yêu cầu.

## 1. Trước tiên, thống nhất mô hình đồ thị

Ký hiệu:

- **V** (hoặc n): số lượng đỉnh. Trong ví dụ Java, các đỉnh được đánh số từ 0 đến V − 1.
- **E** (hoặc m): số lượng cạnh. Với đồ thị vô hướng đơn, cạnh {u, v} không phân biệt chiều; với đồ thị có hướng, cạnh (u, v) đi từ u sang v.
- **deg(u)**: số cạnh kề với u trong đồ thị vô hướng đơn, không có vòng tự nối. Với đồ thị có hướng, cần phân biệt **out-degree** (số cạnh đi ra) và **in-degree** (số cạnh đi vào).
- **Đồ thị thưa** (*sparse*): E tương đối nhỏ so với V², chẳng hạn một cây có E = V − 1 khi V ≥ 1.
- **Đồ thị dày** (*dense*): E gần bậc V². Đồ thị vô hướng đơn không có vòng tự nối có tối đa V(V − 1)/2 cạnh.

Những khái niệm thường ảnh hưởng trực tiếp đến việc chọn biểu diễn:

| Đặc điểm | Ý nghĩa đối với lưu trữ |
| --- | --- |
| Vô hướng | Cần biểu diễn cả hai chiều u → v và v → u để tiện duyệt, dù chúng là một cạnh logic |
| Có hướng | Chỉ lưu quan hệ từ u đến v; chiều ngược lại là một cạnh khác nếu có |
| Không trọng số | Chỉ cần biết cạnh có tồn tại hay không |
| Có trọng số | Cần thêm chi phí/độ dài/giá trị của từng cạnh |
| Đơn (*simple*) | Không có cạnh song song, thường không có vòng tự nối u → u |
| Đa đồ thị (*multigraph*) | Có thể có nhiều cạnh giữa cùng một cặp đỉnh; phải lưu từng cạnh hoặc số lượng cạnh |
| Đỉnh có nhãn | Có thể cần ánh xạ nhãn bất kỳ (chuỗi, ID) sang chỉ số 0..V − 1 |

Khi nói “danh sách kề O(V + E)” hoặc “ma trận kề O(V²)”, ta đang xét cách biểu diễn cơ bản. Kiểu chứa thực tế, chính sách trùng cạnh, số lượng đỉnh thay đổi và trọng số có thể thay đổi hệ số chi phí đáng kể.

## 2. Cùng một đồ thị để so sánh

Xét **đồ thị vô hướng đơn, không trọng số**, có 5 đỉnh {0, 1, 2, 3, 4} và 4 cạnh:

- {0, 1}
- {0, 2}
- {1, 3}
- {2, 3}

Đỉnh 4 **cô lập**: không có cạnh nào nối với 4. Đồ thị **không liên thông**, bởi từ đỉnh 0 không thể đi đến đỉnh 4.

Hình dung các mối nối:

```text
    0
   / \
  1   2     4 (cô lập)
   \ /
    3
```

Ta dùng cùng dữ liệu này để nhìn thấy điểm khác nhau giữa hai cách lưu.

## 3. Danh sách kề (adjacency list)

**Ý tưởng:** Mỗi đỉnh u có một tập hợp hoặc danh sách các đỉnh v nối trực tiếp với u. Với đỉnh được đánh số liên tiếp, có thể dùng `List<List<Integer>>`; phần tử `adj.get(u)` là danh sách hàng xóm của u.

Danh sách kề của ví dụ (theo thứ tự thêm cạnh):

```text
0 -> [1, 2]
1 -> [0, 3]
2 -> [0, 3]
3 -> [1, 2]
4 -> []
```

Cạnh {0, 1} được ghi **hai lần trong các danh sách hàng xóm**: 1 nằm trong hàng của 0, và 0 nằm trong hàng của 1. Với đồ thị vô hướng đơn không có vòng tự nối, tổng số mục kề là **2E** (ở đây là 8), không phải E. Đỉnh 4 vẫn phải có một danh sách rỗng để không bị “biến mất”.

### Tổ chức trong Java

```java
List<List<Integer>> adj = new ArrayList<>();
for (int u = 0; u < 5; u++) {
    adj.add(new ArrayList<>());
}
adj.get(0).add(1);
adj.get(1).add(0); // Cạnh vô hướng {0,1}: ghi cả hai chiều
```

Đây là **đoạn minh họa** và cần các import `java.util.*` hoặc import cụ thể; chương trình Java đầy đủ ở phần 8.

**Chi phí và đặc điểm:**

- Bộ nhớ **O(V + E)** nếu lưu một danh sách cho mỗi đỉnh và một mục cho mỗi cạnh có hướng (hoặc hai mục cho mỗi cạnh vô hướng). Với Java `List<Integer>`, chi phí đối tượng `Integer`, mảng nền và danh sách có thể lớn hơn con số mục lý thuyết.
- Duyệt tất cả hàng xóm của một đỉnh u tốn **Θ(deg(u))** với đồ thị vô hướng đơn; đồ thị có hướng dùng out-degree(u).
- Kiểm tra có cạnh u → v với `ArrayList.contains(v)` mất **O(deg(u))** trong trường hợp xấu nhất vì phải dò danh sách.
- Thêm cạnh bằng cách chỉ `add(v)` vào cuối `ArrayList` có thời gian **O(1) trung bình phân bổ** cho một chiều (giả sử không cần kiểm tra trùng và không tính tăng kích thước danh sách nền). Nếu bảo đảm **đồ thị đơn** bằng cách `contains` trước khi thêm, thao tác có thể mất **O(deg(u))**.
- Xóa một cạnh với danh sách dựa trên `ArrayList` cần tìm vị trí và dịch phần tử; trường hợp xấu nhất O(deg(u)) mỗi chiều.
- Có thể thay danh sách hàng xóm bằng `HashSet<Integer>` để kiểm tra tồn tại và thêm/xóa kỳ vọng gần O(1) mỗi thao tác, đổi lại bộ nhớ phụ lớn hơn và thứ tự duyệt không được bảo đảm. Cần phân biệt **danh sách kề như mô hình** với **kiểu chứa cụ thể của từng danh sách**.

Đồ thị thưa có rất nhiều cặp đỉnh **không nối nhau**. Danh sách kề chỉ lưu các cạnh đang tồn tại, nên thường tiết kiệm bộ nhớ và đặc biệt thuận tiện cho BFS, DFS, tìm thành phần liên thông hoặc liệt kê cạnh.

## 4. Ma trận kề (adjacency matrix)

**Ý tưởng:** Tạo bảng hai chiều kích thước **V × V**. Ô `matrix[u][v]` cho biết có cạnh u → v hay không. Với đồ thị không trọng số, dùng `boolean[][]` và quy ước `true` = có cạnh, `false` = không có cạnh.

Ma trận của đồ thị ví dụ, theo thứ tự cột 0, 1, 2, 3, 4:

```text
        v=0 1 2 3 4
u=0       0 1 1 0 0
u=1       1 0 0 1 0
u=2       1 0 0 1 0
u=3       0 1 1 0 0
u=4       0 0 0 0 0
```

Trong bảng trên, 1 đại diện cho `true` và 0 đại diện cho `false`. Đường chéo chính bằng 0 vì đồ thị ví dụ **không có vòng tự nối**. Ma trận đối xứng qua đường chéo vì đây là đồ thị **vô hướng**: `matrix[u][v] == matrix[v][u]`.

### Tổ chức trong Java

```java
boolean[][] matrix = new boolean[5][5];
matrix[0][1] = true;
matrix[1][0] = true; // Cùng cạnh vô hướng {0,1}
```

- Bộ nhớ **Θ(V²)** ô, bất kể có bao nhiêu cạnh. Ma trận 1.000 đỉnh chứa 1.000.000 ô, ngay cả khi đồ thị chỉ có vài cạnh. `boolean[][]` Java còn mang chi phí đối tượng cho từng hàng; độ lớn thực tế phụ thuộc JVM.
- Kiểm tra tồn tại cạnh u → v mất **O(1)** bằng một lần truy cập ô đã biết chỉ số.
- Thêm hoặc xóa cạnh giữa hai đỉnh đã tồn tại mất **O(1)** bằng cách gán một ô (hai ô với đồ thị vô hướng).
- Duyệt hàng xóm của u phải nhìn qua **V cột** để biết ô nào `true`, nên mất **Θ(V)** kể cả khi u chỉ có một cạnh.
- Lưu hoặc tính bậc đỉnh bằng cách quét hàng mất O(V), trừ khi duy trì thêm bộ đếm cập nhật.
- Thêm một đỉnh mới có thể đòi hỏi cấp phát lại ma trận kích thước (V + 1)² và sao chép dữ liệu, thường tốn O(V²) nếu dùng mảng hai chiều cố định.

Ma trận kề phù hợp khi đồ thị tương đối dày, số đỉnh ổn định, hoặc thuật toán cần **hỏi nhiều lần “u và v có nối trực tiếp không?”**.

## 5. Bảng so sánh độ phức tạp

Đặt n = V, m = E, d(u) = số hàng xóm của u. Bảng áp dụng cho biểu diễn đơn giản: danh sách kề dùng **`ArrayList<Integer>` cho mỗi đỉnh**, ma trận dùng `boolean[][]`, không có các chỉ mục phụ.

| Thao tác | Danh sách kề | Ma trận kề |
| --- | --- | --- |
| Lưu trữ | **O(V + E)** | **O(V²)** |
| Liệt kê hàng xóm của u | **Θ(d(u))** | **Θ(V)** |
| Kiểm tra cạnh u → v | **O(d(u))** với `contains` | **O(1)** |
| Thêm một cạnh đã biết là mới | **O(1) trung bình phân bổ** khi thêm cuối mỗi danh sách | **O(1)** |
| Thêm cạnh và từ chối cạnh trùng | **O(d(u))** để kiểm tra cạnh, rồi thêm; với vô hướng ghi cả hai chiều | **O(1)** |
| Xóa cạnh | **O(d(u))** để tìm và xóa; đồ thị vô hướng còn cập nhật đầu v | **O(1)** |
| BFS/DFS trên toàn đồ thị | **O(V + E)** | **O(V²)** nếu quét toàn bộ hàng ở mỗi đỉnh |
| Xây dựng từ danh sách cạnh, với V đỉnh | **O(V + E)** nếu cứ thêm, không kiểm tra trùng | **O(V² + E)** do khởi tạo ma trận rồi gán cạnh |

Các ghi chú để dùng bảng chính xác:

1. Với đồ thị vô hướng, mỗi cạnh cập nhật hai chiều nên có các hệ số 2, nhưng bậc Big O không đổi. Nếu cho phép tự nối u = v, phải xử lý riêng vì hai chiều trùng nhau.
2. Nếu dùng `HashSet<Integer>` cho mỗi danh sách kề, kiểm tra cạnh, thêm và xóa có thể có thời gian **kỳ vọng** gần O(1), không phải bảo đảm O(1) tuyệt đối. Đây là **đổi cấu trúc chứa hàng xóm**, không đổi nguyên lý danh sách kề.
3. Nếu mọi đỉnh đều được đánh số từ 0 đến V − 1, các thao tác truy cập danh sách theo chỉ số là O(1). Nếu đỉnh là tên chuỗi, có thể cần thêm `Map<String, Integer>` để ánh xạ.
4. Với BFS/DFS bắt đầu ở một đỉnh, chỉ các đỉnh **có thể đi tới** được duyệt. Công thức O(V + E) và O(V²) ở bảng là **cận xấu nhất cho toàn đồ thị**; với ma trận từ một đỉnh, quét tối đa V cột cho mỗi đỉnh được thăm.
5. Kích thước thực tế phụ thuộc kiểu dữ liệu. `boolean[][]` có thể sử dụng ít byte hơn trên mỗi ô so với nhiều đối tượng `Integer` trong danh sách; vì vậy không thể so sánh chính xác RAM chỉ bằng O(V + E) và O(V²).

### Ví dụ đồ thị thưa và dày

- **V = 1.000, E = 999** (một cây): danh sách kề vô hướng có 1.998 mục hàng xóm và 1.000 danh sách; ma trận có 1.000.000 ô, trong đó đa số là `false`. Danh sách kề thường thuận lợi về bộ nhớ và duyệt hàng xóm.
- **V = 1.000, E = 499.500** (đồ thị vô hướng đơn đầy đủ): có 999.000 mục hàng xóm; ma trận vẫn 1.000.000 ô. Lúc này ma trận có lợi rõ ở tra cứu cạnh O(1), và mức RAM thực tế cần đo theo cách cài đặt cụ thể.

**Không có ngưỡng phần trăm cạnh tuyệt đối** để khẳng định ma trận luôn tốt hơn danh sách: còn phụ thuộc loại truy vấn, cập nhật, số đỉnh, quy mô lớn nhất và cấu trúc thực tế trong bộ nhớ.

## 6. Hướng cạnh, trọng số, cạnh song song và vòng tự nối

### Đồ thị có hướng

Nếu có cạnh **0 → 2** nhưng không có **2 → 0**:

- Danh sách kề: chỉ thêm 2 vào hàng xóm đi ra từ 0; không thêm 0 vào hàng của 2.
- Ma trận kề: đặt `matrix[0][2] = true`, giữ `matrix[2][0] = false`.

Vì vậy ma trận **không nhất thiết đối xứng** đối với đồ thị có hướng. Nếu bài toán cần truy vấn cạnh đi **vào** một đỉnh nhanh, có thể lưu thêm danh sách kề đảo chiều hoặc quét cột của ma trận. Danh sách kề đi ra một mình không có ngay danh sách đỉnh trỏ đến u.

### Đồ thị có trọng số

Cần phân biệt **cạnh không tồn tại** và **cạnh tồn tại có trọng số bằng 0**:

- Với danh sách kề, có thể lưu đối tượng như `Edge(to, weight)` cho mỗi cạnh; hoặc `Map<Neighbor, Weight>` nếu mỗi cặp đỉnh chỉ có một trọng số. Cấu trúc vẫn lưu gần theo số cạnh.
- Với ma trận, dùng `Integer[][] weight` và quy ước `null` nghĩa là không có cạnh, hoặc dùng ma trận trọng số đi kèm ma trận `boolean[][] exists`. **Không nên coi trọng số 0 là “không có cạnh”** nếu bài toán cho phép cạnh trọng số 0.
- Nếu trọng số âm, thuật toán đường đi ngắn như Dijkstra còn có tiền điều kiện riêng; chọn cách biểu diễn không tự giải quyết vấn đề tính đúng của thuật toán.

Ví dụ về danh sách kề có trọng số (minh họa ý tưởng, chưa phải chương trình độc lập):

```java
record Edge(int to, int weight) {}
List<List<Edge>> weightedAdj = new ArrayList<>();
// Mỗi cạnh lưu cả đỉnh đích và trọng số, ví dụ new Edge(2, 7).
```

### Cạnh song song (multigraph)

Nếu có **hai cạnh khác nhau** cùng nối u đến v, ma trận `boolean[u][v]` chỉ ghi “có ít nhất một cạnh”, nên **không giữ được số cạnh hay danh tính từng cạnh**. Có thể dùng ma trận số lượng, hoặc ma trận mỗi ô chứa một danh sách cạnh/trọng số; nhưng đây không còn là ma trận boolean cơ bản. Danh sách kề có thể lưu nhiều mục kề, kèm ID cạnh để phân biệt.

### Vòng tự nối (self-loop)

Cạnh u → u tương ứng `matrix[u][u] = true`. Với đồ thị vô hướng, vòng tự nối đóng góp **2 vào bậc đỉnh** theo định nghĩa chuẩn của đồ thị vô hướng; còn một mục `u` trong danh sách hàng xóm không tự thể hiện trực quan hai lần đóng góp này. Cần chốt quy ước khi tính bậc hoặc đếm cạnh. Ví dụ Java bên dưới **chủ động cấm vòng tự nối và cạnh trùng**, để biểu diễn một đồ thị vô hướng đơn nhất quán.

## 7. Chọn cấu trúc theo thao tác chủ đạo

| Tình huống | Lựa chọn khởi đầu hợp lý | Lý do |
| --- | --- | --- |
| Mạng lưới giao thông lớn, mỗi nút chỉ nối với ít nút | Danh sách kề | Ít cạnh, thuận tiện duyệt hàng xóm, tránh cấp phát V² ô |
| BFS/DFS, thành phần liên thông trên đồ thị thưa | Danh sách kề | Duyệt các cạnh đang tồn tại với O(V + E) |
| Đồ thị dày và hỏi cạnh u–v liên tục | Ma trận kề | Truy cập trực tiếp mỗi cặp đỉnh O(1) |
| Số lượng đỉnh nhỏ/cố định, thuật toán thao tác trên mọi cặp đỉnh | Ma trận kề | Cách biểu diễn đơn giản cho quan hệ từng cặp; thích hợp các thuật toán ma trận |
| Thêm/xóa đỉnh thường xuyên hoặc không biết V trước | Danh sách kề / ánh xạ theo ID | Không cần tái cấp phát cả ma trận V × V khi tăng V |
| Đồ thị trọng số có nhiều cạnh song song cần giữ riêng | Danh sách các đối tượng cạnh | Không mất danh tính, ID hoặc trọng số của từng cạnh |
| Cần hỏi cạnh tồn tại nhanh và cũng cần duyệt cạnh nhanh | Danh sách kề với tập băm hoặc cấu trúc kết hợp | Đánh đổi thêm bộ nhớ để phù hợp hai thao tác |

**Quy trình ra quyết định:** (1) xác định có hướng, trọng số, vòng tự nối, cạnh trùng hay không; (2) ước lượng V và E; (3) xác định thao tác lặp lại nhiều nhất là **liệt kê hàng xóm** hay **tra cứu một cặp đỉnh**; (4) xét cập nhật đỉnh/cạnh và giới hạn RAM; (5) chọn cấu trúc và đo thực nghiệm nếu quy mô lớn.

## 8. Ví dụ Java 17+ hoàn chỉnh: cùng một đồ thị, hai cách biểu diễn

Chương trình sau giữ **cùng 5 đỉnh và 4 cạnh** bằng danh sách kề và ma trận kề, rồi thực hiện **BFS từ đỉnh 0**. Hai lớp không phụ thuộc thư viện ngoài JDK; thêm cạnh trùng được bỏ qua, vòng tự nối bị từ chối. Để thứ tự BFS trong ví dụ có thể dự đoán, ta thêm cạnh theo thứ tự đã nêu; danh sách kề giữ thứ tự chèn, còn ma trận duyệt các đỉnh theo chỉ số tăng dần.

Lưu thành **`GraphRepresentations.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

public class GraphRepresentations {
    static final class ListGraph {
        private final List<List<Integer>> neighbors;

        ListGraph(int vertices) {
            if (vertices < 0) {
                throw new IllegalArgumentException("vertices must be >= 0");
            }
            neighbors = new ArrayList<>(vertices);
            for (int u = 0; u < vertices; u++) {
                neighbors.add(new ArrayList<>());
            }
        }

        private void checkVertex(int v) {
            if (v < 0 || v >= neighbors.size()) {
                throw new IndexOutOfBoundsException("vertex " + v);
            }
        }

        void addUndirectedEdge(int u, int v) {
            checkVertex(u);
            checkVertex(v);
            if (u == v) {
                throw new IllegalArgumentException("self-loop is not allowed");
            }
            if (!neighbors.get(u).contains(v)) {
                neighbors.get(u).add(v);
                neighbors.get(v).add(u);
            }
        }

        boolean hasEdge(int u, int v) {
            checkVertex(u);
            checkVertex(v);
            return neighbors.get(u).contains(v);
        }

        List<Integer> bfs(int start) {
            checkVertex(start);
            boolean[] seen = new boolean[neighbors.size()];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            List<Integer> order = new ArrayList<>();
            seen[start] = true;
            queue.add(start);

            while (!queue.isEmpty()) {
                int u = queue.remove();
                order.add(u);
                for (int v : neighbors.get(u)) {
                    if (!seen[v]) {
                        seen[v] = true;
                        queue.add(v);
                    }
                }
            }
            return order;
        }

        String describe() {
            return neighbors.toString();
        }
    }

    static final class MatrixGraph {
        private final boolean[][] connected;

        MatrixGraph(int vertices) {
            if (vertices < 0) {
                throw new IllegalArgumentException("vertices must be >= 0");
            }
            connected = new boolean[vertices][vertices];
        }

        private void checkVertex(int v) {
            if (v < 0 || v >= connected.length) {
                throw new IndexOutOfBoundsException("vertex " + v);
            }
        }

        void addUndirectedEdge(int u, int v) {
            checkVertex(u);
            checkVertex(v);
            if (u == v) {
                throw new IllegalArgumentException("self-loop is not allowed");
            }
            connected[u][v] = true;
            connected[v][u] = true;
        }

        boolean hasEdge(int u, int v) {
            checkVertex(u);
            checkVertex(v);
            return connected[u][v];
        }

        List<Integer> bfs(int start) {
            checkVertex(start);
            boolean[] seen = new boolean[connected.length];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            List<Integer> order = new ArrayList<>();
            seen[start] = true;
            queue.add(start);

            while (!queue.isEmpty()) {
                int u = queue.remove();
                order.add(u);
                for (int v = 0; v < connected.length; v++) {
                    if (connected[u][v] && !seen[v]) {
                        seen[v] = true;
                        queue.add(v);
                    }
                }
            }
            return order;
        }
    }

    public static void main(String[] args) {
        int vertices = 5;
        int[][] edges = {
            {0, 1}, {0, 2}, {1, 3}, {2, 3}
        };

        ListGraph list = new ListGraph(vertices);
        MatrixGraph matrix = new MatrixGraph(vertices);
        for (int[] edge : edges) {
            list.addUndirectedEdge(edge[0], edge[1]);
            matrix.addUndirectedEdge(edge[0], edge[1]);
        }

        System.out.println("Vertices: " + vertices);
        System.out.println("Edges: " + edges.length);
        System.out.println("Adjacency list: " + list.describe());
        System.out.println("List has 0-2: " + list.hasEdge(0, 2));
        System.out.println("Matrix has 0-2: " + matrix.hasEdge(0, 2));
        System.out.println("List has 0-4: " + list.hasEdge(0, 4));
        System.out.println("BFS list from 0: " + list.bfs(0));
        System.out.println("BFS matrix from 0: " + matrix.bfs(0));
        System.out.println("Isolated vertex 4: "
                + !matrix.hasEdge(0, 4));
    }
}
```

Biên dịch và chạy:

```bash
javac GraphRepresentations.java
java GraphRepresentations
```

Stdout của chương trình:

```text
Vertices: 5
Edges: 4
Adjacency list: [[1, 2], [0, 3], [0, 3], [1, 2], []]
List has 0-2: true
Matrix has 0-2: true
List has 0-4: false
BFS list from 0: [0, 1, 2, 3]
BFS matrix from 0: [0, 1, 2, 3]
Isolated vertex 4: true
```

**Đọc kết quả:**

- Danh sách kề hiện ra ở dạng mảng các danh sách hàng xóm; hàng số 4 rỗng.
- `hasEdge(0, 2)` cho cùng kết quả `true` ở cả hai cách; `hasEdge(0, 4)` là `false`.
- BFS đánh dấu `seen` **khi đưa đỉnh vào hàng đợi**, tránh đưa cùng một đỉnh vào hàng đợi nhiều lần.
- Cả hai BFS trả về `[0, 1, 2, 3]`; không có 4 vì 4 không đi tới được từ 0. Nếu cần duyệt **toàn bộ đồ thị không liên thông**, phải khởi chạy BFS/DFS từ mỗi đỉnh chưa thăm.
- Thứ tự thăm BFS **không duy nhất**: nó phụ thuộc thứ tự xét hàng xóm. Ví dụ này được sắp để cả hai biểu diễn cho cùng thứ tự, nhưng hai cấu trúc có thể trả thứ tự BFS khác nhau mà vẫn đúng về khoảng cách theo số cạnh.
- Câu cuối kiểm tra riêng cạnh 0–4 và phù hợp với cấu trúc của ví dụ. Để xác minh **một đỉnh thật sự cô lập ở mọi đồ thị**, phải kiểm tra toàn bộ hàng xóm/cạnh liên quan đến đỉnh ấy, không chỉ một cặp đỉnh.

**Tại sao chi phí BFS khác nhau?** Ở `ListGraph.bfs`, vòng `for (int v : neighbors.get(u))` chỉ xét các hàng xóm thực sự có. Tổng cộng trên toàn đồ thị là O(V + E). Trong `MatrixGraph.bfs`, vòng `for (int v = 0; v < connected.length; v++)` luôn quét toàn bộ V cột của mỗi đỉnh được thăm; trường hợp xấu nhất O(V²). Hai cách tạo ra cùng tập đỉnh reachable nhưng làm lượng công việc khác nhau.

### Kiểm tra trường hợp biên

Với đồ thị **0 đỉnh**, cả hai constructor đều tạo cấu trúc rỗng hợp lệ; gọi `bfs(0)` hoặc `hasEdge(0, 0)` sẽ ném `IndexOutOfBoundsException` vì không có đỉnh 0. Với đồ thị **1 đỉnh**, BFS từ 0 trả `[0]` dù không có cạnh. Các lớp từ chối chỉ số âm, chỉ số ≥ V và vòng tự nối; danh sách kề bỏ qua cạnh trùng bằng bước `contains` còn ma trận gán lại `true`, nên đều không tạo nhiều cạnh song song.

### Lưu ý về độ phức tạp của chính đoạn mã

Phương thức `ListGraph.addUndirectedEdge` có bước `contains(v)` để ngăn cạnh trùng, nên một lần thêm có thể tốn O(deg(u)). Nếu thay bằng việc thêm thẳng không kiểm tra, độ phức tạp trung bình phân bổ sẽ thấp hơn nhưng phải chấp nhận/tránh cạnh trùng theo một cơ chế khác. `MatrixGraph.addUndirectedEdge` gán hai ô, nên O(1).

## 9. Sai lầm thường gặp

1. **Quên ghi chiều ngược ở đồ thị vô hướng:** Danh sách kề chỉ có v trong hàng của u hoặc ma trận chỉ ghi `matrix[u][v]` sẽ làm biểu diễn không nhất quán.
2. **Giả định ma trận luôn nhanh hơn:** Truy vấn một cạnh nhanh O(1), nhưng quét hàng xóm hoặc BFS trên đồ thị thưa có thể làm nhiều việc hơn rất nhiều.
3. **Quên đỉnh cô lập trong danh sách kề:** Nếu chỉ tạo danh sách khi đỉnh có cạnh thì sẽ làm mất số lượng đỉnh và khiến thuật toán duyệt sai.
4. **Nhầm số lượng phần tử kề với số cạnh vô hướng:** Với đồ thị vô hướng đơn không có vòng tự nối, tổng số mục kề = 2E.
5. **Không ngăn cạnh trùng:** Với `List<Integer>`, thêm nhiều lần có thể tạo nhiều mục giống nhau; thao tác tính bậc, đếm cạnh và xử lý cạnh có thể khác ý định.
6. **Coi ma trận trọng số 0 là không có cạnh:** Nếu cạnh có trọng số 0 hợp lệ, cần sentinel khác hoặc bảng tồn tại riêng.
7. **Đánh đồng danh sách kề với `LinkedList`:** “Adjacency list” mô tả mỗi đỉnh có tập hàng xóm; danh sách đó có thể lưu bằng `ArrayList`, `HashSet`, mảng hoặc cấu trúc khác.
8. **Quên thuật toán BFS/DFS chỉ từ một nguồn không thăm toàn bộ đồ thị rời rạc:** Muốn bao phủ tất cả thành phần liên thông cần vòng lặp qua các đỉnh chưa thăm.
9. **So Big O mà bỏ cấu trúc cụ thể:** “Kiểm tra cạnh trong danh sách kề là O(1)” chỉ có thể được kỳ vọng nếu dùng cấu trúc như hash set cho hàng xóm; với `ArrayList.contains` thường là O(deg(u)).
10. **Đổi cách lưu mà quên chỉnh thuật toán:** BFS dùng danh sách kề chỉ duyệt các mục của hàng xóm; dùng ma trận phải quét hàng và kiểm tra từng ô.

## 10. Tự kiểm tra

**Câu 1.** Có V = 10.000 đỉnh và E = 9.999 cạnh tạo thành một cây. Trong hai cách cơ bản, nên ưu tiên cách nào để duyệt BFS?

**Đáp án:** Danh sách kề, vì lưu O(V + E), BFS O(V + E), trong khi ma trận cần O(V²) ô và quét hàng xóm mỗi đỉnh bằng O(V).

**Câu 2.** Cần trả lời hàng triệu truy vấn “có cạnh từ u đến v không?” trên đồ thị dày và số đỉnh nhỏ, ổn định. Ma trận có lợi gì?

**Đáp án:** Kiểm tra mỗi cặp chỉ số bằng `matrix[u][v]` trong O(1); đổi lại phải dành O(V²) bộ nhớ. Với nhiều truy vấn và V đủ nhỏ, đây có thể là đánh đổi hợp lý.

**Câu 3.** Với đồ thị vô hướng có các cạnh {0,1} và {1,2}, danh sách kề cần lưu gì?

**Đáp án:** `0:[1]`, `1:[0,2]`, `2:[1]`. Tổng 4 mục hàng xóm tương ứng 2E với E=2.

**Câu 4.** Một đồ thị có hướng chỉ có cạnh (2, 3). Giá trị nào phải là `true` trong ma trận?

**Đáp án:** `matrix[2][3]`; `matrix[3][2]` phải giữ `false` nếu không có cạnh ngược.

**Câu 5.** Một đồ thị có cạnh (u, v) trọng số 0. Vì sao không nên dùng `weight[u][v] == 0` để suy ra không có cạnh?

**Đáp án:** Vì sẽ không phân biệt được cạnh tồn tại trọng số 0 với cạnh không tồn tại. Cần `exists[][]` hoặc sentinel không trùng với trọng số hợp lệ.

**Câu 6.** Vì sao hai bản BFS trong chương trình có thể có thứ tự thăm khác nhau dù đều đúng?

**Đáp án:** BFS xử lý hàng xóm theo thứ tự biểu diễn cung cấp. Danh sách kề có thể dùng thứ tự chèn, ma trận quét cột tăng dần; cả hai vẫn thăm các đỉnh reachable và xác định khoảng cách ngắn nhất theo số cạnh trong đồ thị không trọng số.

## Ghi nhớ

**Danh sách kề** ưu tiên lưu và duyệt **cạnh thực sự tồn tại**: bộ nhớ O(V + E), thuận tiện cho đồ thị thưa và BFS/DFS. **Ma trận kề** ưu tiên tra cứu **quan hệ giữa một cặp đỉnh bất kỳ**: truy cập ô O(1), đổi lại lưu O(V²) và quét hàng xóm O(V). Chọn cách biểu diễn dựa trên **V, E, loại đồ thị, thao tác chủ đạo, yêu cầu cập nhật và bộ nhớ**, đồng thời giữ đúng ngữ nghĩa cạnh, hướng và trọng số.

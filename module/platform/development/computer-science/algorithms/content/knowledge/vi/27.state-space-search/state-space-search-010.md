# Tìm kiếm hai chiều và điều kiện ghép hai phía

**Tìm kiếm hai chiều** (*bidirectional search*) là kỹ thuật đồng thời tìm từ **trạng thái bắt đầu** s về phía đích và từ **trạng thái đích** t theo chiều ngược của các phép chuyển. Hai nửa tìm kiếm có thể được **ghép** (*meet/join*) khi chúng đại diện cho một điểm nối hợp lệ. Mục đích phổ biến nhất là tìm đường đi ngắn nhất trong đồ thị trạng thái không trọng số với ít trạng thái được khám phá hơn BFS một chiều.

Điểm cốt lõi không phải chỉ là “chạy hai BFS”: phải làm rõ **điều kiện ghép hai phía**. Với bài tìm đường ngắn nhất trong một đồ thị trạng thái đầy đủ, điều kiện đơn giản nhất là **hai phía cùng tới đúng một trạng thái v**, tức `visitedFromStart[v] && visitedFromGoal[v]`. Với bài toán trạng thái có tài nguyên, ràng buộc từng nửa, hoặc kiểu **meet-in-the-middle**, hai trạng thái nửa đường còn phải **tương thích** theo các điều kiện bổ sung; ghép bừa vì trùng một vị trí có thể tạo hành trình không hợp lệ.

Bài học trình bày cơ sở, chứng minh tối ưu cho BFS hai chiều mở rộng theo **lớp**, cách xử lý **đồ thị có hướng**, khôi phục đường đi, khi nào **không** được dừng tại lần gặp đầu tiên, phức tạp, liên hệ với meet-in-the-middle và một chương trình **Java 17+ chạy độc lập** được kiểm chứng bằng BFS một chiều.

## 1. Đồ thị trạng thái và ý tưởng gặp ở giữa

Xét một bài toán có tập trạng thái S, trạng thái khởi đầu s, tập đích hoặc một đích t, và quan hệ chuyển hợp lệ:

\[
x\longrightarrow y\quad\Longleftrightarrow\quad
\text{một phép biến đổi hợp lệ đưa x thành y}.
\]

Ta coi mỗi trạng thái là một **đỉnh**; mỗi phép biến đổi là một **cạnh có hướng**. Nếu mọi phép chuyển có chi phí 1, **BFS** tìm được đường có ít bước nhất.

BFS một chiều từ s khám phá lần lượt các lớp khoảng cách:

~~~text
L0(s): trạng thái s
L1(s): các trạng thái cách s đúng 1 bước
L2(s): các trạng thái cách s đúng 2 bước
...
Ld(s): các trạng thái cách s đúng d bước
~~~

Nếu t cách s khoảng d và hệ số phân nhánh trung bình là b, cây tìm kiếm lý tưởng có thể phải khám phá khoảng:

\[
1+b+b^2+\cdots+b^d=O(b^d)
\]

trạng thái khi không có nhiều trạng thái trùng nhau.

**Tìm kiếm hai chiều** đồng thời khám phá từ t **ngược** về s. Một đường dài d có thể được chia thành đoạn đầu khoảng \(d/2\) và đoạn cuối khoảng \(d/2\); mỗi phía chỉ cần khám phá độ sâu xấp xỉ \(d/2\). Trong mô hình phân nhánh đều, chi phí trực giác có thể giảm từ \(O(b^d)\) xuống \(O(b^{d/2})\) ở mỗi phía.

Đó là **ước lượng có điều kiện**, không phải cam kết cho mọi đồ thị. Nếu nhánh ngược rất lớn, đích không biết chính xác, phép chuyển ngược không dựng được, hoặc hai phía bị mất cân bằng, tìm kiếm hai chiều có thể không có lợi.

### Một sơ đồ ngắn

~~~text
BFS xuôi từ s                   BFS ngược từ t

       s                              t
      / \                            / \
     ... ...                       ... ...
        \                           /
         \           v             /
          \-------- gặp ----------/

   s -> ... -> v         v -> ... -> t

Ghép hai nửa thành s -> ... -> v -> ... -> t
~~~

**Đoạn phía t** khi được dựng ngược phải đổi chiều lúc khôi phục. Ta không được nối thành s→...→v→...→t nếu chuỗi phía t không thật sự gồm các bước xuôi hợp lệ từ v tới t.

## 2. Điều kiện ghép cơ bản: cùng một trạng thái

Cho đồ thị có hướng G, đặt:

- \(dist_F[v]\): số bước ngắn nhất từ s tới v.
- \(dist_B[v]\): số bước ngắn nhất từ v tới t, tính bằng BFS từ t trên **đồ thị đảo cạnh** \(G^R\).
- \(parent_F[v]\): tiền nhiệm của v trên một đường s→v.
- \(parent_B[v]\): **bước kế tiếp** đi xuôi từ v về t, được ghi khi khám phá v bằng BFS trên \(G^R\).

Nếu một đỉnh v đã được khám phá ở cả hai phía, hai nửa ghép được:

\[
\boxed{length(s\leadsto v\leadsto t)=dist_F[v]+dist_B[v].}
\]

Điều kiện ghép:

\[
\boxed{dist_F[v]\ge0\ \text{và}\ dist_B[v]\ge0.}
\]

Trong BFS đồ thị không trọng số, mỗi \(dist_F,dist_B\) khi đã được gán đều là **khoảng cách ngắn nhất** tới v theo hướng tương ứng. Vì thế phép nối qua v cho một **đường đi hợp lệ** từ s tới t, và nếu v là điểm ghép tối ưu, tổng khoảng cách bằng \(dist(s,t)\).

Tuy nhiên, **“v đã xuất hiện ở cả hai phía” chưa tự đủ để khẳng định độ dài của v là nhỏ nhất trong tất cả điểm ghép**. Cần có quy tắc mở rộng và dừng bảo đảm rằng chưa bỏ qua một điểm ghép cho tổng ngắn hơn.

### Trạng thái phải được định nghĩa đầy đủ

Nếu bài toán có trạng thái `(v, keyMask, fuel, phase)`, chỉ so `v` của hai phía là **không đủ**. Hai nửa đi tới cùng vị trí nhưng khác quyền sử dụng chìa khóa, lượng tài nguyên còn lại, thời điểm hoặc pha chuyển có thể **không tương thích**.

Với BFS trạng thái đầy đủ, **trùng đúng toàn bộ trạng thái** có ý nghĩa của bài là điều kiện gặp tự nhiên, miễn là tìm kiếm ngược thật sự biểu diễn những đường từ trạng thái đó tới đích. Với biểu diễn **hai nửa khác loại**, cần một **quan hệ ghép riêng** (xem phần 11).

## 3. Đồ thị có hướng: phía đích phải dùng cạnh đảo

Nếu có cạnh hợp lệ \(u\to v\), phía xuôi được đi u→v; phía ngược bắt đầu từ t phải được phép đi **v→u trong đồ thị đảo**. Khi đó khi BFS ngược khám phá u qua v, nó biết một bước **xuôi hợp lệ** là u→v.

Đặt:

\[
G^R=(V,\{(v,u)\mid (u,v)\in E\}).
\]

BFS từ t trên \(G^R\) tính đúng:

\[
dist_{G^R}(t,v)=dist_G(v,t).
\]

Đây là lý do cần **danh sách hàng xóm đi vào** (*reverse adjacency*) khi graph có hướng.

### Phản ví dụ đảo sai chiều

Giả sử graph chỉ có:

~~~text
8 -> 0
~~~

Truy vấn s=0, t=8 **không có đường đi**. Nếu từ t=8 mà dùng lại cạnh **xuôi** 8→0 rồi coi 0 là điểm gặp, ta sẽ báo sai là có đường 0→8.

BFS ngược phải hỏi **những ai có cạnh đi vào 8**; trong graph trên không có đỉnh nào như vậy. Ngược lại, truy vấn s=8,t=0 có đường trực tiếp độ dài 1.

Đối với **đồ thị vô hướng**, mỗi cạnh u–v đi được cả hai chiều, nên adjacency phía xuôi và phía ngược tương đương. Dù vậy, code tổng quát cho **đồ thị có hướng** nên xây cả `out[u]` và `in[v]`.

### Sinh tiền nhiệm với bài toán phép biến đổi trạng thái

Nếu phép chuyển xuôi là `x -> 2*x` hoặc `x -> x+1` trong một miền trạng thái hữu hạn, phía ngược từ y phải sinh **tiền nhiệm hợp lệ**:

- Từ phép `x -> x+1`: tiền nhiệm `y-1` (nếu nằm trong miền).
- Từ phép `x -> 2*x`: tiền nhiệm `y/2` **chỉ khi y chẵn**, và phải thuộc miền.

Không phải mọi phép biến đổi có một **hàm nghịch đảo duy nhất**. Có phép không khả nghịch, có nhiều tiền nhiệm, có miền trạng thái hạn chế. Điều kiện cần cho tìm kiếm ngược là sinh **đủ các trạng thái có thể chuyển xuôi một bước vào y**, không nhất thiết có một hàm đảo.

## 4. Quy tắc dừng đúng với BFS hai chiều

Có nhiều cách triển khai. Bài này chọn một phiên bản dễ chứng minh:

1. BFS xuôi từ s và BFS ngược từ t, mỗi phía có **hàng đợi và bảng khoảng cách riêng**.
2. **Mở rộng toàn bộ một lớp** của phía xuôi.
3. Nếu có điểm gặp, xét tất cả điểm gặp được phát hiện trong lớp đó, chọn tổng `dist_F+dist_B` nhỏ nhất (hòa thì chọn ID điểm gặp nhỏ nhất), rồi dừng.
4. Nếu không có điểm gặp, **mở rộng toàn bộ một lớp** của phía ngược và kiểm tra như trên.
5. Tiếp tục luân phiên **một lớp xuôi, một lớp ngược** cho đến khi gặp, hoặc một phía cạn lớp có thể mở rộng.

Điều quan trọng là **mỗi lượt mở rộng nguyên một lớp**, không lấy tùy tiện một đỉnh từ một bên rồi dừng ngay tại sự giao đầu tiên.

### Vì sao cần mở rộng nguyên lớp?

BFS bảo đảm mọi đỉnh trong cùng một lớp có **cùng khoảng cách** từ phía đó. Có thể có nhiều điểm gặp ở một lớp; chọn **tổng khoảng cách nhỏ nhất** trong các điểm ấy để tránh quyết định theo thứ tự adjacency mà không có luận cứ.

Với lịch **luân phiên đồng đều các lớp** như trên, sau k−1 lượt đầy đủ, phía xuôi và phía ngược đã biết tất cả đỉnh tới độ sâu k−1. Nếu chưa có giao:

- Không thể có đường s→t ngắn **≤2k−2**, vì một đường dài như vậy phải chứa một vị trí nằm cách s và t lần lượt **≤k−1**.
- Khi mở rộng xuôi tới độ sâu k, mọi đường dài **2k−1** buộc có một điểm ở khoảng cách ≤k từ s và ≤k−1 tới t, nên nếu có đường dài 2k−1, hai phía sẽ gặp.
- Nếu phía xuôi chưa gặp, khi mở rộng ngược tới độ sâu k, mọi đường dài **2k** cũng buộc có một điểm ở khoảng cách ≤k từ cả hai đầu, nên sẽ gặp.

Bởi vậy, **lần gặp đầu tiên sau một lớp đầy đủ** trong lịch đồng đều này tìm được khoảng cách **ngắn nhất**. Lập luận vẫn đúng với graph có hướng vì phía ngược dùng đúng \(G^R\).

### Khi hai phía gặp tại cạnh thay vì tại đỉnh

Có thể cài một biến thể phát hiện **cạnh băng qua hai vùng đã thăm** \((u,v)\) với u thuộc phía xuôi và v thuộc phía ngược, rồi xét ứng viên:

\[
dist_F[u]+1+dist_B[v].
\]

Điều kiện này cũng hợp lệ nếu **cạnh u→v có thật**, nhưng quy tắc dừng và khôi phục phải được chứng minh tương ứng. Mã Java chọn **gặp tại cùng đỉnh đã được phát hiện ở cả hai phía**, giúp giải thích ngắn gọn hơn.

### Tối ưu bằng chọn biên nhỏ hơn

Một biến thể thực dụng mở rộng phía có **frontier nhỏ hơn** để cân bằng số trạng thái. Tuy nhiên, khi hai bên phát triển **không cùng độ sâu**, nếu chỉ trả **ứng viên giao đầu tiên** mà không giữ **cận dưới phù hợp** cho mọi đường chưa xét, kết quả ngắn nhất không tự được bảo đảm từ lập luận ở trên.

Muốn dùng lịch mở rộng tùy ý, cần thiết kế thêm:
- Biến `best` giữ độ dài ứng viên nối tốt nhất đã phát hiện.
- Một điều kiện dừng được **chứng minh** từ các khoảng cách lớp chưa xử lý và trạng thái đã chốt của hai phía.
- Cách xét điểm gặp tại đỉnh/cạnh nhất quán với điều kiện cận đó.

**Không chuyển từ lịch luân phiên lớp sang lịch “luôn chọn biên nhỏ hơn” rồi giữ nguyên lập luận dừng cũ**. Bản Java cố ý dùng lịch đều để minh họa tính đúng.

## 5. Ví dụ có hướng: nhiều điểm ghép và cạnh đánh lừa

Xét các đỉnh 0..10 và các cung sau, **theo thứ tự thêm vào**:

~~~text
0->1, 0->2
1->3, 1->4
2->4, 2->5
3->6
4->6, 4->7
5->7
6->8, 7->8
8->0
9->10
~~~

Đây là **đồ thị có hướng**, có chu trình 8→0 và một thành phần riêng 9→10.

Truy vấn tìm đường từ s=0 tới t=8:

~~~text
                 0
               /   \
              1     2
             / \   / \
            3   4     5
             \ / \   /
              6   7
               \ /
                8
                |
                v
                0    (cạnh quay về 0)
~~~

Có nhiều đường độ dài 4:

~~~text
0 -> 1 -> 3 -> 6 -> 8
0 -> 1 -> 4 -> 7 -> 8
0 -> 2 -> 4 -> 7 -> 8
0 -> 2 -> 5 -> 7 -> 8
~~~

Thuật toán tìm một đường ngắn nhất, **không cần liệt kê tất cả đường bằng nhau**.

### Hai phía phát triển như thế nào?

BFS xuôi từ 0:

~~~text
F0 = {0}
F1 = {1,2}
F2 = {3,4,5}
~~~

BFS ngược từ 8 trên các **cung đảo**:

~~~text
B0 = {8}
B1 = {6,7}
B2 = {3,4,5}
~~~

Lịch luân phiên:

| Lượt | Phía mở rộng | Trạng thái mới tới | Có giao? |
|---|---|---|---|
| 1 | F: độ sâu 0→1 | 1,2 | Chưa |
| 2 | B: độ sâu 0→1 | 6,7 | Chưa |
| 3 | F: độ sâu 1→2 | 3,4,5 | Chưa |
| 4 | B: độ sâu 1→2 | 3,4,5 | **Có** |

Mọi điểm gặp 3,4,5 đều có:

\[
dist_F[v]=2,\quad dist_B[v]=2,\quad
dist_F[v]+dist_B[v]=4.
\]

Với quy tắc tie-break **điểm gặp có ID nhỏ nhất**, chọn **v=3**. Sau đó:

~~~text
Đoạn xuôi 0 -> 1 -> 3
Đoạn về đích 3 -> 6 -> 8
Đường trả về 0 -> 1 -> 3 -> 6 -> 8
Độ dài: 4
~~~

### Truy vấn đổi chiều

- `8→0` có cạnh trực tiếp độ dài **1**.
- `0→8` có độ dài **4**.
- `0→10` **không có đường**, vì 9→10 nằm ở thành phần không thể tới từ 0.
- `9→10` có độ dài **1**, nhưng `10→9` không có đường.

Điều này chứng minh **không thể đổi vai trò hai chiều mà bỏ qua hướng cạnh**.

## 6. Khôi phục đường đi từ hai bảng cha

Muốn trả lời không chỉ độ dài mà còn **chuỗi trạng thái**, phải lưu hai bảng:

- `parentF[v]`: tiền nhiệm trên một đường ngắn nhất **s→v**.
- `parentB[v]`: trạng thái tiếp theo trên một đường ngắn nhất **v→t** của graph gốc.

Khi BFS ngược ở đỉnh u khám phá tiền nhiệm v vì graph gốc có cạnh v→u, ghi:

~~~text
parentB[v] = u
~~~

Đó là một bước **đi xuôi từ v sang u**, không phải một bước ngược. Dùng `parentB` để bước từ điểm gặp về đích là hoàn toàn hợp lệ.

Với điểm gặp `meet`:

1. Đi từ meet ngược theo `parentF` tới s, ghi các đỉnh rồi **đảo ngược** danh sách.
2. Đi từ `parentB[meet]` xuôi theo `parentB` tới t, **nối thêm** vào danh sách.
3. Bắt đầu nửa sau từ `parentB[meet]`, không bắt đầu lại từ meet để tránh **lặp điểm gặp hai lần**.

Mã giả:

~~~text
prefix = [meet, parentF[meet], parentF[parentF[meet]], ... ,s]
reverse(prefix)

suffix = []
v = parentB[meet]
while v != -1:
    suffix.add(v)
    v = parentB[v]

path = prefix + suffix
~~~

Khi s=t, đường ngắn nhất là `[s]`, độ dài 0, không cần mở rộng hai phía.

### Kiểm tra khôi phục

Với đường `[v0,v1,...,vd]` phải có:

- `v0==s`, `vd==t`.
- Mọi cặp liên tiếp `vi→v(i+1)` là **cạnh xuôi hợp lệ trong graph gốc**.
- Số cạnh `path.size()-1` đúng bằng `dist_F[meet]+dist_B[meet]`.
- Trên đồ thị không trọng số, nếu thuật toán tìm được khoảng cách ngắn nhất thì đường khôi phục phải đạt đúng khoảng cách ấy.

Không phải mọi ứng dụng cần lưu đường; nếu chỉ hỏi “có thể tới không?” hoặc “ít bước nhất?”, có thể bỏ các bảng cha để tiết kiệm bộ nhớ.

## 7. Java 17+: BFS hai chiều có hướng, điều kiện gặp và đường đi

Chương trình **BidirectionalStateSearchDemo.java** có thể biên dịch/chạy trực tiếp với JDK 17 trở lên. Nó dùng một graph có hướng và duy trì **hai adjacency list**: cung xuôi từ u và cung ngược để tìm tiền nhiệm.

Hợp đồng API:

- `DirectedGraph(int n,int[][] edges)` nhận n≥0, các cung có hướng đầu mút trong `0..n-1`. Có thể có self-loop, cạnh song song, đồ thị không liên thông.
- `shortestPath(s,t)` trả độ dài ngắn nhất tính theo **số cung**, danh sách đỉnh đường đi, điểm gặp và số đỉnh đã được **mở rộng khỏi queue** bởi mỗi phía.
- `distance==-1` cùng `path=[]` nghĩa là **không tới được**; riêng `s==t` luôn trả distance 0 và path một đỉnh.
- Nếu có nhiều đường ngắn nhất, trả một đường theo thứ tự adjacency và quy tắc **tie-break điểm gặp ID nhỏ nhất trong cùng lớp**.
- Mã mở rộng **một lớp hoàn chỉnh phía s**, rồi **một lớp hoàn chỉnh phía t**, để dùng chứng minh dừng phần 4.
- `expandedFromStart/expandedFromGoal` đếm số đỉnh bị lấy khỏi queue để mở rộng, không phải số đỉnh đã được phát hiện; chỉ là chỉ số chẩn đoán, không phải độ dài đường đi.

**Mã Java 17 hoàn chỉnh:**

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class BidirectionalStateSearchDemo {
    record Result(
        int distance,
        List<Integer> path,
        int meetingVertex,
        int expandedFromStart,
        int expandedFromGoal
    ) {
        boolean reachable() {
            return distance >= 0;
        }
    }

    static final class DirectedGraph {
        final int n;
        final List<List<Integer>> out;
        final List<List<Integer>> incoming;

        DirectedGraph(int n, int[][] edges) {
            if (n < 0) {
                throw new IllegalArgumentException("negative vertex count");
            }
            Objects.requireNonNull(edges, "edges");
            this.n = n;
            out = new ArrayList<>();
            incoming = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                out.add(new ArrayList<>());
                incoming.add(new ArrayList<>());
            }

            for (int[] e : edges) {
                if (e == null || e.length != 2
                        || e[0] < 0 || e[0] >= n
                        || e[1] < 0 || e[1] >= n) {
                    throw new IllegalArgumentException("invalid directed edge");
                }
                out.get(e[0]).add(e[1]);
                incoming.get(e[1]).add(e[0]);
            }
        }

        private void checkVertex(int v) {
            if (v < 0 || v >= n) {
                throw new IllegalArgumentException("invalid vertex");
            }
        }

        // Expand EXACTLY one full BFS layer.
        // Return the best newly discovered meeting vertex in this layer,
        // or -1 if the two visited sets have not met.
        private int expandOneLayer(
            ArrayDeque<Integer> queue,
            List<List<Integer>> adjacency,
            int[] hereDist,
            int[] otherDist,
            int[] hereParent
        ) {
            int layerSize = queue.size();
            int bestMeet = -1;
            int bestLength = Integer.MAX_VALUE;

            for (int i = 0; i < layerSize; i++) {
                int u = queue.remove();

                for (int v : adjacency.get(u)) {
                    if (hereDist[v] != -1) {
                        continue;
                    }

                    hereDist[v] = hereDist[u] + 1;
                    hereParent[v] = u;
                    queue.add(v);

                    if (otherDist[v] != -1) {
                        int length = hereDist[v] + otherDist[v];
                        if (length < bestLength
                                || (length == bestLength
                                    && (bestMeet == -1 || v < bestMeet))) {
                            bestLength = length;
                            bestMeet = v;
                        }
                    }
                }
            }
            return bestMeet;
        }

        private Result reconstruct(
            int meet, int[] forwardParent, int[] backwardParent,
            int[] forwardDist, int[] backwardDist,
            int expandedF, int expandedB
        ) {
            List<Integer> path = new ArrayList<>();

            // This half is read backward; reverse it before joining.
            for (int v = meet; v != -1; v = forwardParent[v]) {
                path.add(v);
            }
            Collections.reverse(path);

            // parentB[v] points to the NEXT original forward state v->t.
            for (int v = backwardParent[meet]; v != -1;
                    v = backwardParent[v]) {
                path.add(v);
            }

            int length = forwardDist[meet] + backwardDist[meet];
            if (path.size() != length + 1) {
                throw new IllegalStateException("invalid reconstructed path");
            }
            return new Result(
                length, List.copyOf(path), meet, expandedF, expandedB
            );
        }

        Result shortestPath(int source, int target) {
            checkVertex(source);
            checkVertex(target);

            if (source == target) {
                return new Result(
                    0, List.of(source), source, 0, 0
                );
            }

            int[] forwardDist = new int[n];
            int[] backwardDist = new int[n];
            int[] forwardParent = new int[n];
            int[] backwardParent = new int[n];
            Arrays.fill(forwardDist, -1);
            Arrays.fill(backwardDist, -1);
            Arrays.fill(forwardParent, -1);
            Arrays.fill(backwardParent, -1);

            ArrayDeque<Integer> forwardQueue = new ArrayDeque<>();
            ArrayDeque<Integer> backwardQueue = new ArrayDeque<>();
            forwardQueue.add(source);
            backwardQueue.add(target);
            forwardDist[source] = 0;
            backwardDist[target] = 0;
            int expandedF = 0;
            int expandedB = 0;

            while (!forwardQueue.isEmpty() && !backwardQueue.isEmpty()) {
                int forwardLayerSize = forwardQueue.size();
                int meet = expandOneLayer(
                    forwardQueue, out,
                    forwardDist, backwardDist, forwardParent
                );
                expandedF += forwardLayerSize;
                if (meet != -1) {
                    return reconstruct(
                        meet, forwardParent, backwardParent,
                        forwardDist, backwardDist, expandedF, expandedB
                    );
                }

                int backwardLayerSize = backwardQueue.size();
                meet = expandOneLayer(
                    backwardQueue, incoming,
                    backwardDist, forwardDist, backwardParent
                );
                expandedB += backwardLayerSize;
                if (meet != -1) {
                    return reconstruct(
                        meet, forwardParent, backwardParent,
                        forwardDist, backwardDist, expandedF, expandedB
                    );
                }
            }

            return new Result(
                -1, List.of(), -1, expandedF, expandedB
            );
        }
    }

    static void printRoute(
        DirectedGraph graph, int source, int target
    ) {
        Result r = graph.shortestPath(source, target);
        System.out.println(
            source + "->" + target
            + ": distance=" + r.distance()
            + ", path=" + r.path()
            + ", meet=" + r.meetingVertex()
            + ", expanded=" + r.expandedFromStart()
            + "/" + r.expandedFromGoal()
        );
    }

    public static void main(String[] args) {
        int[][] edges = {
            {0, 1}, {0, 2},
            {1, 3}, {1, 4},
            {2, 4}, {2, 5},
            {3, 6},
            {4, 6}, {4, 7},
            {5, 7},
            {6, 8}, {7, 8},
            {8, 0},
            {9, 10}
        };

        DirectedGraph graph = new DirectedGraph(11, edges);
        printRoute(graph, 0, 8);
        printRoute(graph, 0, 7);
        printRoute(graph, 8, 0);
        printRoute(graph, 4, 8);
        printRoute(graph, 0, 10);
        printRoute(graph, 9, 10);
        printRoute(graph, 0, 0);

        DirectedGraph empty = new DirectedGraph(0, new int[][] {});
        System.out.println("Empty graph constructed: " + empty.n);

        try {
            graph.shortestPath(0, 11);
        } catch (IllegalArgumentException e) {
            System.out.println("Invalid vertex rejected: "
                + e.getMessage());
        }

        try {
            new DirectedGraph(3, new int[][] {{0, 3}});
        } catch (IllegalArgumentException e) {
            System.out.println("Invalid edge rejected: "
                + e.getMessage());
        }
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac BidirectionalStateSearchDemo.java
java BidirectionalStateSearchDemo
~~~

**Stdout đúng với dữ liệu trên:**

~~~text
0->8: distance=4, path=[0, 1, 3, 6, 8], meet=3, expanded=3/3
0->7: distance=3, path=[0, 1, 4, 7], meet=4, expanded=3/1
8->0: distance=1, path=[8, 0], meet=0, expanded=1/0
4->8: distance=2, path=[4, 6, 8], meet=6, expanded=1/1
0->10: distance=-1, path=[], meet=-1, expanded=3/2
9->10: distance=1, path=[9, 10], meet=10, expanded=1/0
0->0: distance=0, path=[0], meet=0, expanded=0/0
Empty graph constructed: 0
Invalid vertex rejected: invalid vertex
Invalid edge rejected: invalid directed edge
~~~

### Đọc từng phần của mã

**Danh sách kề:** `out[u]` lưu các đỉnh v có cạnh xuôi u→v; `incoming[v]` lưu các tiền nhiệm u có u→v. Phía ngược không được dùng `out` nếu đồ thị có hướng.

**Bảng khoảng cách:** `forwardDist` và `backwardDist` khởi tạo -1 (chưa thăm). Nguồn s và đích t có khoảng cách 0 ở phía tương ứng.

**Mở rộng đúng một lớp:** `layerSize=queue.size()` được lấy **trước** vòng lặp. Mỗi phần tử đang có trong queue thuộc lớp hiện tại; các trạng thái mới chỉ được đẩy ra cuối và **không bị mở rộng ngay** trong lượt đó.

**Điểm ghép:** ngay khi phát hiện v mới từ một phía, nếu `otherDist[v]!=-1`, có ứng viên đường đi. Hàm xét **mọi ứng viên trong lớp**, lấy tổng khoảng cách nhỏ nhất và tie-break theo ID.

**Lưu cha:** Khi phía ngược khám phá v từ một đỉnh u qua `incoming[u]`, gán `backwardParent[v]=u`; đây là bước xuôi v→u trên graph gốc. Chính điều này cho phép nối đường mà không phải đảo hướng các cạnh.

**Lịch dừng:** vòng lặp một lớp xuôi rồi một lớp ngược, dừng khi tìm được giao sau một lớp hoàn chỉnh. Nếu một queue cạn mà chưa gặp, không có đường từ s đến t.

**Không đoán chi phí bằng expanded:** hai bộ đếm là số đỉnh bị lấy khỏi queue; chi phí thật còn phụ thuộc số cạnh quét. Chẳng hạn một đỉnh có bậc ra rất lớn có thể tốn nhiều công dù chỉ tăng `expanded` một đơn vị.

## 8. Tính đúng: điều kiện ghép và độ dài ngắn nhất

Chứng minh theo ba bước.

### Bước A — Khoảng cách ở mỗi phía đúng

BFS duyệt mọi cạnh có trọng số bằng 1 theo các lớp. Khi một đỉnh v lần đầu được khám phá từ s, `forwardDist[v]` là số cạnh ít nhất từ s tới v. Khi v được khám phá từ t trên `incoming`, `backwardDist[v]` là số cạnh ít nhất từ v tới t **trên graph gốc**.

### Bước B — Ghép cho một đường hợp lệ

Khi v đã được cả hai phía phát hiện, nửa đầu s→v theo `forwardParent` và nửa sau v→t theo `backwardParent` đều gồm các cung xuôi hợp lệ. Độ dài tổng là `forwardDist[v]+backwardDist[v]`. Hai nửa không cần dùng cùng quy tắc chọn cha, chỉ cần mỗi nửa hợp lệ và đạt khoảng cách đã lưu.

### Bước C — Dừng ở lần gặp đầu tiên sau lớp là tối ưu

Giả sử đã mở rộng k−1 lớp của mỗi phía mà chưa gặp. Nếu có đường dài không quá \(2k-2\), trên đường đó phải tồn tại điểm z cách s ≤k−1 và cách t ≤k−1; BFS đã phát hiện z ở cả hai phía, mâu thuẫn.

Sau khi mở rộng lớp k phía s, nếu có đường độ dài \(2k-1\), lấy điểm ở vị trí k tính từ s trên đường đó: cách s ≤k, cách t ≤k−1. Hai phía phải gặp. Do không có đường ngắn hơn \(2k-1\), nếu gặp ở lượt này thì khoảng cách nhỏ nhất là \(2k-1\).

Nếu chưa gặp, mở rộng lớp k phía t. Nếu có đường dài \(2k\), điểm ở vị trí k trên đường sẽ cách s và t ≤k. Hai phía gặp, và vì không có đường dài ≤\(2k-1\), độ dài ngắn nhất lúc ấy bằng \(2k\).

Đối với s=t xử lý riêng với khoảng cách 0. Vì lịch mở rộng trong code đúng là **F lớp k rồi B lớp k**, và kiểm giao sau mỗi lớp, kết quả có đường luôn ngắn nhất.

### Trường hợp hai nửa có trạng thái trùng ngoài điểm ghép

Trong bài shortest path cơ bản, nếu hai đường con được ghép tạo một **walk có lặp trạng thái**, thì walk đó không thể là đường ngắn nhất nếu tồn tại chu trình có độ dài dương (mỗi cạnh chi phí 1). Vì thuật toán chỉ dừng ở độ dài tối ưu, đường được dựng là đường ngắn nhất. Nếu bài toán có ràng buộc **đường đơn với tài nguyên tiêu thụ phụ thuộc các đỉnh đã ghé**, đó là một **bài trạng thái khác**: phải bảo toàn lịch sử/điều kiện tài nguyên, không thể chỉ dùng vị trí v.

## 9. Khi nào tìm kiếm hai chiều nhanh hơn?

Trong một **cây phân nhánh đều** với b trạng thái con ở mỗi mức và khoảng cách ngắn nhất d, BFS một phía có thể chạm tới khoảng \(b^d\) trạng thái. Tìm kiếm hai chiều cân bằng hai độ sâu xấp xỉ d/2, có thể khám phá khoảng:

\[
O(b^{d/2})+O(b^{d/2})=O(b^{d/2}).
\]

Ví dụ nếu b=4 và d=10:

- Một chiều theo mô hình cây phân nhánh: mức sâu 10 có thể có \(4^{10}=1.048.576\) trạng thái.
- Hai chiều cân bằng: mỗi phía sâu khoảng 5, mức sâu nhất mỗi phía khoảng \(4^5=1.024\) trạng thái.

Đây là **minh họa lý thuyết theo cây phân nhánh**, không phải số đỉnh phải duyệt chính xác trong mọi graph. Các trạng thái lặp, hướng cạnh, cách phân bố đường tới đích, bộ nhớ và việc phát hiện giao thay đổi mạnh hiệu quả thực tế.

### Độ phức tạp xấu nhất

Với đồ thị hữu hạn có V đỉnh, E cung, xây reverse adjacency mất **O(V+E)** thời gian và bộ nhớ. Trong một truy vấn, mỗi BFS khám phá mỗi đỉnh tối đa một lần và quét các cung liên quan tối đa một lần mỗi phía:

\[
\boxed{\text{Thời gian xấu nhất }O(V+E).}
\]

Bảng dist, parent và hai queue chiếm O(V). Cả adjacency xuôi/ngược chiếm O(V+E). Đường khôi phục có tối đa O(V) đỉnh.

Bidirectional BFS **không cải thiện cận xấu nhất** so với BFS một chiều. Lợi ích chủ yếu là **giảm vùng tìm kiếm thực tế** khi hai phía phát triển hợp lý và gặp sớm.

### Các trường hợp không lợi

- Đích không xác định chính xác, ví dụ “tới bất cứ trạng thái thỏa thuộc tính P” mà không có cách khởi tạo phía ngược hữu hạn và đúng.
- Không thể liệt kê tiền nhiệm hoặc phép sinh tiền nhiệm có chi phí rất lớn.
- Một phía có hệ số phân nhánh ngược khổng lồ; không cân bằng dù khoảng cách đã chia đôi.
- s gần t (0–1 cạnh): một BFS bình thường đã rất rẻ.
- Cần trả lời rất nhiều truy vấn chung một nguồn s: chạy **một BFS từ s** và tái sử dụng kết quả có thể tốt hơn chạy lại bidirectional search cho mỗi đích.
- Đồ thị có trọng số không đồng đều: BFS hai chiều không còn tìm tổng chi phí nhỏ nhất nếu giữ cách duyệt theo số cạnh.

## 10. Ghép ở đỉnh và ghép ở cạnh

Có hai biến thể thường gặp.

**Ghép tại đỉnh v:** khi hai phía đều đã có v, ứng viên dài:

\[
dist_F[v]+dist_B[v].
\]

Đường: s→...→v→...→t. Đây là cách code sử dụng.

**Ghép qua cạnh \((u,v)\):** khi u đã có bên xuôi và v đã có bên ngược, đồng thời **có cung xuôi u→v**, ứng viên:

\[
dist_F[u]+1+dist_B[v].
\]

Đường: s→...→u→v→...→t. Đây là phương án hợp lệ với điều kiện nối **u→v thực sự tồn tại và các nửa không xung đột ràng buộc khác**.

Đừng vô tình cộng 1 cho cách ghép ở **cùng một đỉnh**, hoặc quên cộng 1 khi ghép qua **một cạnh**. Nếu các nửa dài a,b:

~~~text
Ghép đỉnh v:  tổng = a + b
Ghép cạnh u->v: tổng = a + 1 + b
~~~

Trong tìm kiếm trạng thái tổng quát, điều kiện ghép qua cạnh còn có thể là một **phép chuyển hợp lệ** giữa hai tóm tắt trạng thái, không nhất thiết là một cung có sẵn trong graph tường minh.

## 11. Điều kiện ghép khi hai phía mang tài nguyên hoặc thông tin khác nhau

Đây là phần dễ bị bỏ qua nếu chỉ biết “hai visited set giao nhau”.

### 11.1. Cùng vị trí nhưng trạng thái chưa đầy đủ

Giả sử trạng thái thật sự là:

~~~text
(position, collectedKeys, remainingFuel)
~~~

Một nửa đường tới vị trí v với `collectedKeys=01` chưa chắc ghép được với một nửa khác cần `collectedKeys=11`; nhiên liệu còn lại cũng có thể không đủ cho đoạn sau.

Nếu định nghĩa graph trạng thái đầy đủ, hai phía phải ghép theo **trạng thái đủ thông tin**, hoặc theo một quan hệ đúng được dẫn xuất từ logic tiếp diễn. Chỉ so `position` tạo **false positive**.

### 11.2. Tổng ngân sách

Nếu bài cho phép tối đa B đơn vị tài nguyên và mỗi nửa đường có chi phí/tài nguyên cộng được, một điều kiện ghép ứng viên có thể là:

\[
samePosition\ \land\ cost_F+cost_B\le B.
\]

Nếu yêu cầu dùng **chính xác B**, thay \(\le B\) bằng \(=B\). Tuy nhiên cần chắc chắn tài nguyên không bị **đếm hai lần tại điểm gặp**, và các ràng buộc không cộng được đã được kiểm riêng.

Ví dụ: nửa trái dùng 3 năng lượng, nửa phải dùng 4, ngân sách B=6. Dù hai nửa gặp cùng vị trí, **không được ghép**, vì 3+4=7>B.

### 11.3. Ràng buộc không dùng trùng đối tượng

Trong bài duyệt đường **đơn** hoặc sử dụng các vật chỉ một lần, nếu mỗi nửa lưu tập đối tượng đã dùng:

\[
Used_F\cap Used_B=\varnothing
\]

có thể là điều kiện bắt buộc, sau khi quy định rõ cách **tính điểm gặp chung**. Nếu cả hai nửa đều đã tính chính đỉnh gặp v vào visited set, giao được phép chứa v nhưng không được chứa những đỉnh khác nếu yêu cầu đường đơn và biểu diễn hai nửa chỉ dùng những đường đơn.

Nếu không kiểm điều kiện này, hai nửa riêng lẻ hợp lệ có thể ghép thành một hành trình lặp đối tượng bị cấm.

### 11.4. Điều kiện biên giữa hai nửa

Có bài hai nửa dừng ở hai trạng thái khác nhau p,q; chúng có thể ghép nếu:

\[
Compatible(p,q)=true.
\]

Ví dụ: phải có một phép chuyển **p→q**, thời điểm/khoảng cách nối thỏa giới hạn, hoặc hai phần phân công không xung đột. Trong trường hợp ấy, **không cần** `p==q`, nhưng bắt buộc có **chứng cứ nối hợp lệ**.

**Quy tắc chung:** biểu diễn nửa trái, biểu diễn nửa phải và điều kiện ghép phải đủ để khẳng định sau khi nối có một **lời giải hoàn chỉnh hợp lệ**. Tốc độ tìm kiếm không bù được một join predicate sai.

## 12. Liên hệ với meet-in-the-middle

**Bidirectional BFS** và **meet-in-the-middle (MITM)** có trực giác chung: chia bài thành hai nửa, xử lý riêng rồi **ghép các kết quả tương thích**. Nhưng chúng không phải một thuật toán đồng nhất.

### Bidirectional BFS

- Hai phía đi từ s và t trong graph trạng thái.
- Bảo toàn **khoảng cách từ hai đầu**.
- Điểm gặp thường là **cùng một trạng thái**.
- Mục tiêu có thể là đường đi ít bước nhất.
- Dừng theo quy tắc lớp/cận để bảo đảm tối ưu.

### Meet-in-the-middle cho tổ hợp

Ví dụ bài **subset sum** với n số: chia dãy thành hai nửa, liệt kê các tổng của từng nửa (khoảng \(2^{n/2}\) mỗi bên), rồi tìm cặp tổng:

\[
sumLeft+sumRight=T.
\]

Ở đây **không có một đỉnh đồ thị** mà hai BFS cùng tới. Điều kiện ghép là **phương trình tổng**, không phải hai trạng thái bằng nhau. Nếu còn ràng buộc số phần tử, nhóm, thứ tự hoặc xung đột lựa chọn, phải đưa đủ điều kiện vào phép ghép.

Vì vậy:

- Trong shortest path: **join là giao trạng thái** hoặc một cạnh nối hợp lệ.
- Trong MITM tổ hợp: **join là quan hệ tương thích** của hai tóm tắt nửa nghiệm.
- Cả hai cần chứng minh **mọi nghiệm hợp lệ có một cách tách được xét**, và **mọi cặp ghép được đều tạo nghiệm hợp lệ**.

### Chọn cấu trúc dữ liệu để ghép

- **HashSet/HashMap**: tìm trạng thái/bổ sung chính xác bằng khóa, trung bình O(1) mỗi lookup.
- **Sắp xếp + hai con trỏ**: ghép tổng hoặc so sánh thứ tự, O(K log K) tiền xử lý và có thể O(K) quét.
- **Bảng dist/parent bằng mảng**: tốt khi trạng thái là ID nguyên trong `0..V-1`, như Java demo.
- **Trạng thái nén bitmask**: khi tập đối tượng nhỏ, có thể kiểm xung đột `maskL & maskR` hoặc kết hợp mask.
- **Chỉ mục theo khóa chung**: nhóm theo vị trí, thời điểm hoặc chữ ký của biên để không xét mọi cặp \(O(|L||R|)\).

Một phép ghép tốt phải **đúng trước khi nhanh**.

## 13. Bài toán có trọng số: không dùng BFS thường

Nếu mỗi bước có trọng số không âm nhưng khác nhau, số bước nhỏ nhất chưa chắc là tổng chi phí nhỏ nhất.

Ví dụ:

~~~text
s -> a  (100)
s -> b  (1)
b -> a  (1)
~~~

Đường ít cạnh nhất s→a có **1 cạnh nhưng chi phí 100**. Đường s→b→a có **2 cạnh nhưng chi phí 2**. BFS (một hay hai chiều) tối ưu số cạnh sẽ **không giải** bài tối thiểu tổng trọng số.

Các lựa chọn:

- Trọng số tất cả bằng 1: **BFS hai chiều** như bài.
- Trọng số chỉ 0 hoặc 1: **0–1 BFS** thích hợp; muốn làm hai chiều cần thiết kế quy tắc dừng đúng.
- Trọng số không âm: **Dijkstra**, có thể thiết kế **bidirectional Dijkstra** với hàng đợi ưu tiên của hai phía.
- Có cạnh âm: Dijkstra không đúng nói chung; cần giải pháp phù hợp với graph và điều kiện chu trình âm.

### Điều kiện dừng của bidirectional Dijkstra

Một biến thể Dijkstra hai chiều giữ:

- Khoảng cách tạm từ s và t (phía ngược dùng cạnh đảo).
- Hai tập đỉnh đã **chốt** theo Dijkstra, không chỉ đã thấy.
- Biến \(\mu\) là độ dài **ứng viên đường s→t hoàn chỉnh tốt nhất** đã được phát hiện qua điểm/cạnh nối hợp lệ.

Khi khoảng cách tối thiểu chưa xử lý của hai hàng đợi là \(minKey_F,minKey_B\), một điều kiện dừng kinh điển đúng **với bất biến cập nhật \(\mu\) đầy đủ và trọng số không âm** là:

\[
\boxed{minKey_F+minKey_B\ge \mu.}
\]

Không nên chép nguyên quy tắc “gặp đầu tiên” của BFS vào Dijkstra hai chiều. Trong Dijkstra, **lần đầu gặp** của hai tập trạng thái mới nhìn thấy không nhất thiết cho đường nhỏ nhất. Cần chứng minh cận và cập nhật ứng viên khi các vùng tìm kiếm nối nhau.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả / cách sửa |
|---|---|
| Phía t dùng cung xuôi trong graph có hướng | Trả nhầm đường t→s thành s→t; dùng reverse adjacency |
| Chỉ khởi tạo một bảng visited | Hai phía làm mất thông tin của nhau |
| Không lưu dist riêng | Không tính được tổng khoảng cách của điểm gặp |
| Dừng khi thấy một trạng thái có cùng vị trí nhưng khác tài nguyên | Ghép nghiệm không hợp lệ |
| Ghép ở cạnh nhưng không kiểm cạnh có thật | Xuất một bước chuyển không tồn tại |
| Ghép ở đỉnh nhưng cộng thêm 1 | Lệch một đơn vị |
| Ghép qua cạnh nhưng quên cộng 1 | Lệch một đơn vị |
| Đảo sai nửa đường phía t | In đường đi ngược cạnh |
| Lặp điểm gặp hai lần | Danh sách đỉnh thừa, khoảng cách không khớp |
| Không xử lý s=t | Có thể tìm vòng hoặc báo không tới được |
| Dừng ngay ở một giao tùy ý khi lịch mở rộng không cân bằng | Có nguy cơ bỏ sót ứng viên ngắn hơn |
| Không mở hết lớp hiện tại | Không xét đúng các ứng viên cùng mức của BFS |
| Đếm expanded thành dist | Số đỉnh mở rộng khác số cung đường đi |
| Coi BFS hai chiều luôn nhanh hơn một chiều | Có thể tốn thêm công sinh tiền nhiệm và bộ nhớ |
| Áp BFS với trọng số không bằng nhau | Tối ưu số bước, không tối ưu chi phí |
| Không kiểm ID trạng thái hợp lệ | Truy cập mảng ngoài miền |
| Dùng reverse adjacency cho graph vô hướng mà chỉ thêm một chiều | Bỏ sót hàng xóm hợp lệ |
| Coi visited giao nhau là đủ cho đường đơn có ràng buộc visited-mask | Có thể lặp đối tượng đã dùng |
| Quên điều kiện ngân sách hai nửa | Ghép vượt tài nguyên |
| Giữ hàng đợi cũ giữa các truy vấn | Trạng thái truy vấn trước rò sang truy vấn sau |
| Không đối chiếu đường đi với cạnh gốc | Có thể in một đường vô hướng hóa sai |
| Quên đường vô nghiệm | Cần trả path rỗng và distance=-1 theo hợp đồng |

### Nguy cơ hiệu năng và số học

Trong một graph hữu hạn ID số nguyên, `dist` không vượt số đỉnh trừ một khi có đường đi ngắn nhất đơn. Dùng `int` cho số bước thường hợp lý trong giới hạn mảng Java. Nếu trạng thái được tạo ngầm với số bước/số trạng thái vượt giới hạn số nguyên, phải chọn kiểu đếm và cấu trúc lưu phù hợp.

Với graph rất lớn có trạng thái là chuỗi, tuple hoặc đối tượng, cần hash/equality **đúng và ổn định**. Nếu hai trạng thái logic bằng nhau nhưng có hash khác do chuẩn hóa sai, phép giao hai phía có thể thất bại dù có đường đi.

## 15. Kiểm thử đúng và oracle độc lập

Với bài đường đi ít bước nhất, một **BFS một chiều chuẩn** là oracle đơn giản, độc lập với logic chia hai phía. Với mỗi truy vấn (s,t):

1. Chạy BFS thường từ s trên **các cung xuôi**, lấy `distanceReference[t]`.
2. Chạy BFS hai chiều, lấy `distanceBidirectional`.
3. Yêu cầu hai khoảng cách **bằng nhau**, kể cả khi cả hai là -1.
4. Nếu có đường, kiểm danh sách trả về bắt đầu s, kết thúc t và mỗi cặp kề là một **cung xuôi có thật**.
5. Kiểm `path.size()-1==distanceBidirectional`.
6. Thử nhiều graph **có hướng** ngẫu nhiên, bao gồm chu trình, self-loop, cạnh song song, đỉnh cô lập và thành phần một chiều.
7. Thử s=t, đích không tới được và khi t có cạnh đi về s nhưng s không tới t.
8. Đảo thứ tự các cung: khoảng cách phải giữ nguyên, dù **đường cụ thể hoặc điểm gặp** có thể đổi.

### Test dẫn tới lỗi đảo chiều

~~~text
Graph: 8 -> 0
Query: 0 -> 8
Expected: unreachable
~~~

Nếu chạy “BFS từ t” mà vẫn đi cung xuôi 8→0, chương trình có thể thấy 0 ở phía đích và kết luận sai có đường 0→8. Đây là test rất nhỏ nhưng bắt được lỗi định hướng nghiêm trọng.

### Test gặp ở lớp chẵn và lẻ

- Đường dài **3** có thể gặp khi phía xuôi đã mở đến độ sâu **2**, phía ngược đến độ sâu **1**.
- Đường dài **4** có thể gặp khi hai phía cùng mở đến độ sâu **2**.

Ví dụ code:

~~~text
0->7: distance=3, meet=4
0->8: distance=4, meet=3
~~~

Hai trường hợp này kiểm việc dừng sau **nửa vòng xuôi** hoặc sau **nửa vòng ngược** của một chu kỳ luân phiên.

## 16. Bài tập thực hành

**Bài 1 — Truy vấn cùng đỉnh.** Nếu s=t, khoảng cách ngắn nhất là bao nhiêu?

*Đáp án:* **0**, đường đi gồm đúng một trạng thái `[s]`.

**Bài 2 — Cạnh đảo.** Graph chỉ có cung 8→0. Tìm đường từ 0 tới 8 có nghiệm không?

*Đáp án:* **Không**. Chiều cạnh không cho 0→8.

**Bài 3 — Khoảng cách đối xứng?** Trên graph ví dụ, `dist(0,8)` và `dist(8,0)` có bằng nhau không?

*Đáp án:* **Không**. Lần lượt **4** và **1**, vì graph có hướng.

**Bài 4 — Vì sao phải đảo graph ở phía t?**

*Đáp án:* Để đi từ trạng thái y tới tất cả **tiền nhiệm x** có thể chuyển xuôi x→y. Nhờ vậy bảng backwardDist[v] biểu diễn đúng khoảng cách **từ v tới t**.

**Bài 5 — Ghép tại đỉnh.** Nếu distF[v]=2 và distB[v]=3, một đường qua v dài bao nhiêu cạnh?

*Đáp án:* **5**, bằng 2+3.

**Bài 6 — Ghép qua cạnh.** Nếu có cung u→v, distF[u]=2 và distB[v]=3, đoạn nối dài mấy cạnh?

*Đáp án:* **6**, bằng 2+1+3.

**Bài 7 — Dừng sớm.** Có thể mở rộng ngẫu nhiên một đỉnh ở phía s rồi một đỉnh ở phía t, trả ngay giao đầu tiên mà vẫn mặc định tối ưu không?

*Đáp án:* **Không có bảo đảm chung**. Cần mở rộng theo lớp đồng đều như bài hoặc chứng minh một điều kiện dừng khác theo các cận khoảng cách.

**Bài 8 — Đường độ dài 3.** Vì sao có thể phát hiện đường độ dài 3 sau khi F tới lớp 2 và B tới lớp 1?

*Đáp án:* Một vị trí trên đường cách s 2 bước và cách t 1 bước; hai phía đã có thể khám phá nó.

**Bài 9 — Đường độ dài 4.** Đường 0→1→3→6→8 có điểm gặp minh họa nào?

*Đáp án:* **3**, có distF=2, distB=2, tổng 4.

**Bài 10 — Tại sao parentB không đảo thêm lần nữa khi nối?**

*Đáp án:* Vì khi BFS ngược khám phá v từ u, nó lưu `parentB[v]=u`, và graph gốc có cung **v→u**. Bám parentB từ v chính là đi xuôi về t.

**Bài 11 — Không tới được.** Trên graph ví dụ, `0→10` có đường không?

*Đáp án:* **Không**, vì 9→10 nằm trong thành phần không tới được từ 0.

**Bài 12 — Số đỉnh mở rộng.** `expanded=3/3` có nghĩa đường đi có sáu cạnh không?

*Đáp án:* **Không**. Nó là số đỉnh bị lấy ra mở rộng ở mỗi phía; khoảng cách ở ví dụ 0→8 chỉ **4**.

**Bài 13 — Trạng thái phụ.** Nếu trạng thái gồm `(v,mask)`, chỉ kiểm v bằng nhau đã đủ ghép chưa?

*Đáp án:* **Chưa**. Phải bảo đảm mask và mọi ràng buộc dùng tài nguyên tương thích.

**Bài 14 — Ngân sách.** Nửa trái dùng 3 đơn vị, nửa phải dùng 4, ngân sách B=6. Hai nửa gặp cùng vị trí có ghép được không?

*Đáp án:* **Không**, vì 3+4=7>B.

**Bài 15 — MITM tổng.** Với bài subset sum, điều kiện ghép hai nửa là gì?

*Đáp án:* Tìm `sumLeft+sumRight==target`, không phải hai trạng thái bằng nhau.

**Bài 16 — Trọng số.** Có đường 1 cạnh chi phí 100 và đường 2 cạnh chi phí 2. BFS hai chiều sẽ ưu tiên đường nào?

*Đáp án:* Nó tối ưu **số cạnh**, nên có thể chọn đường 1 cạnh dù đắt hơn. Muốn tối ưu chi phí phải dùng thuật toán phù hợp như Dijkstra cho trọng số không âm.

**Bài 17 — Độ phức tạp.** Với graph hữu hạn V đỉnh E cung, cận xấu nhất của BFS hai chiều là gì?

*Đáp án:* **O(V+E)** thời gian, O(V+E) lưu graph và O(V) bộ nhớ truy vấn. Ưu thế thường nằm ở số trạng thái thực tế được duyệt.

**Bài 18 — Định nghĩa đích.** Nếu không thể xác định các trạng thái đích hoặc tiền nhiệm của chúng, bidirectional search có luôn khả thi không?

*Đáp án:* **Không**. Nó cần một cách khởi tạo phía ngược và sinh các tiền nhiệm **đầy đủ, đúng chiều**; nếu thiếu, BFS một chiều hoặc một phương pháp khác có thể phù hợp hơn.

**Tổng kết:** Tìm kiếm hai chiều chia bài từ s tới t thành **hai BFS theo hướng đúng**: từ s trên graph gốc và từ t trên graph **đảo cạnh**. Điểm gặp hợp lệ trong shortest-path cơ bản là **một trạng thái đã được cả hai phía khám phá**; ứng viên có độ dài **distF+distB**. Bản triển khai mở rộng **mỗi phía một lớp đầy đủ theo lịch F–B đồng đều**, nên lần gặp đầu tiên sau một lớp bảo đảm khoảng cách ít bước nhất, và hai bảng cha khôi phục đường s→t đúng chiều. Nếu bài toán có thêm tài nguyên, ràng buộc visited hoặc trạng thái nửa đường khác loại, phải thiết kế **điều kiện ghép tương thích**, không chỉ so vị trí. Không dùng quy tắc BFS để tối ưu trọng số tùy ý, và không dừng tại giao đầu tiên của một lịch mở rộng bất kỳ nếu chưa chứng minh cận tối ưu.
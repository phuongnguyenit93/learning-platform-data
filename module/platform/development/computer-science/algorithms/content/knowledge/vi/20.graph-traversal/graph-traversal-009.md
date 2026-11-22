# Kiểm tra tính hai phía bằng tô màu — Duyệt đồ thị

**Đồ thị hai phía (bipartite graph)** là đồ thị có thể chia tập đỉnh thành hai nhóm **A** và **B** sao cho **mọi cạnh đều nối một đỉnh thuộc A với một đỉnh thuộc B**. Không có cạnh nào nối hai đỉnh cùng nhóm. Một cách kiểm tra hiệu quả là **tô màu hai màu bằng BFS hoặc DFS**: gán cho mỗi đỉnh một trong hai màu 0 và 1, rồi yêu cầu mọi cạnh nối hai màu đối nhau.

Bài toán này thuộc chủ đề **duyệt đồ thị**. Thay vì thử tất cả cách gán hai nhóm (có thể tới 2ⁿ cách), ta lan truyền màu qua cạnh theo quy tắc:

**color[v] = 1 − color[u]** khi từ u đi tới v chưa được tô màu.

Nếu gặp một cạnh **(u,v)** có hai đầu **cùng màu**, không thể giữ toàn bộ các ràng buộc và đồ thị **không hai phía**.

Bài học tập trung vào:

- Định nghĩa đúng cho đồ thị vô hướng, kể cả **nhiều thành phần liên thông**, đỉnh cô lập, cạnh song song và khuyên tự nối.
- Cách triển khai **BFS hai màu** và biến thể **DFS**.
- Chứng minh tương đương giữa **tô được hai màu** và **không tồn tại chu trình lẻ**.
- Cách trả **hai nhóm đỉnh** khi hợp lệ hoặc **một chu trình lẻ làm chứng cứ** khi không hợp lệ.
- Code **Java 17+ chạy độc lập**, độ phức tạp, các lỗi thường gặp và bài kiểm thử với vét cạn.

## 1. Định nghĩa và mô hình đầu vào

Xét đồ thị vô hướng **G=(V,E)** gồm n đỉnh, m cạnh. Đồ thị là **hai phía** nếu tồn tại hai tập A,B thỏa:

1. **A∩B=∅**.
2. **A∪B=V**.
3. Với mọi cạnh vô hướng {u,v}∈E, có **một đầu ở A và đầu còn lại ở B**.

Hai tập có thể rỗng trong định nghĩa tổng quát. Ví dụ đồ thị **không có cạnh** là hai phía: có thể đặt tất cả đỉnh vào A, không đỉnh nào vào B. Đồ thị **rỗng n=0** cũng hai phía theo quy ước thông dụng.

Một cách tô màu tương ứng là hàm:

**color: V → {0,1}**,

với điều kiện:

**color[u] ≠ color[v]** cho mỗi cạnh {u,v}.

Các đỉnh màu 0 tạo A; các đỉnh màu 1 tạo B. Ngược lại, từ một phân hoạch A/B có thể gán màu 0/1 ngay. Do đó **“hai phía” và “tô được hai màu đúng” là hai cách nói tương đương**.

### Ví dụ cơ bản

Đường đi 1—2—3—4—5:

~~~text
1 -- 2 -- 3 -- 4 -- 5
0    1    0    1    0

A = {1,3,5}
B = {2,4}
~~~

Đây là đồ thị hai phía.

Tam giác:

~~~text
       1
      / \
     2---3

1 mang màu 0.
2 và 3 đều phải mang màu 1 vì nối với 1.
Nhưng cạnh 2--3 nối hai đỉnh cùng màu 1.
=> KHÔNG hai phía.
~~~

Điểm khác biệt không phải số đỉnh chẵn/lẻ của toàn đồ thị; yếu tố quyết định là **ràng buộc trên từng cạnh** và **các chu trình lẻ**.

## 2. Định lý quan trọng: đồ thị hai phía khi và chỉ khi không có chu trình lẻ

Với đồ thị vô hướng, ta có định lý:

**G là đồ thị hai phía ⇔ G không chứa chu trình có số cạnh lẻ.**

Quy ước: trong một đồ thị có khuyên (self-loop), khuyên {u,u} là **chu trình độ dài 1** và làm đồ thị không hai phía. Trong đồ thị đơn, chu trình lẻ nhỏ nhất có 3 cạnh (tam giác).

### Chiều thuận: hai phía ⇒ không có chu trình lẻ

Giả sử tồn tại tô màu 0/1 hợp lệ. Trên một đường đi, mỗi lần qua một cạnh màu phải **đảo**:

**0 → 1 → 0 → 1 → ...**

Nếu xuất phát từ đỉnh màu 0 và đi qua một **số cạnh lẻ**, ta kết thúc ở màu 1. Nhưng một chu trình quay lại **chính đỉnh xuất phát** nên phải có cùng màu 0. Mâu thuẫn. Vậy mọi chu trình phải có **số cạnh chẵn**.

Lập luận cũng áp dụng nếu xuất phát màu 1.

### Chiều đảo: không có chu trình lẻ ⇒ tô được hai màu

Xét một thành phần liên thông. Chọn đỉnh gốc r và dùng BFS, tô đỉnh theo **chẵn/lẻ của khoảng cách ngắn nhất từ r**:

**color[u] = dist(r,u) mod 2**.

Nếu tồn tại cạnh {u,v} nối hai đỉnh cùng màu, khoảng cách từ r đến u,v có cùng tính chẵn lẻ. Từ các đường đi trong cây BFS đến u và v, bỏ phần tiền tố chung trước **tổ tiên chung gần nhất (LCA)**, rồi nối bằng cạnh {u,v}; thu được một chu trình có **số cạnh lẻ**. Điều này trái giả thiết. Vì vậy không có cạnh cùng màu và phép tô hợp lệ.

Lập luận thực hiện độc lập cho từng thành phần liên thông.

**Hệ quả:** khi BFS/DFS phát hiện cạnh nối hai đỉnh cùng màu, ngoài việc trả false, ta có thể **dựng chu trình lẻ** từ các đường đi cha trong cây duyệt.

## 3. BFS tô màu: ý tưởng và bất biến

Dùng mảng **color[]**:

- **−1:** chưa được tô.
- **0:** phía A.
- **1:** phía B.

Ở một thành phần mới, tùy ý chọn gốc r và gán **color[r]=0**. Đưa r vào hàng đợi FIFO.

Khi lấy u khỏi queue, duyệt từng đỉnh kề v:

- Nếu **color[v]=−1**, gán **color[v]=1−color[u]** rồi đưa v vào queue.
- Nếu **color[v]=color[u]**, phát hiện mâu thuẫn, kết luận **không hai phía**.
- Nếu **color[v]≠color[u]**, cạnh này phù hợp; không cần thay đổi màu.

Pseudocode:

~~~text
color[1..n] = -1

for r = 1 .. n:
    if color[r] != -1:
        continue

    color[r] = 0
    queue.push(r)

    while queue not empty:
        u = queue.pop_front()

        for v adjacent to u:
            if color[v] == -1:
                color[v] = 1 - color[u]
                queue.push(v)
            else if color[v] == color[u]:
                return NOT_BIPARTITE

return BIPARTITE
~~~

**Vòng for bên ngoài là bắt buộc** nếu đồ thị có thể không liên thông. Chỉ BFS từ một đỉnh không bảo đảm đã xét những thành phần khác.

### Bất biến quan trọng

Sau khi một đỉnh được tô, màu của nó biểu thị **parity (chẵn/lẻ)** của đường đi trong **cây BFS** từ gốc thành phần tới đỉnh đó. Khi gặp một cạnh từ u tới v chưa thăm, ta tô v với màu ngược u, bảo đảm cạnh cây BFS hợp lệ.

Nếu cạnh không thuộc cây BFS nối hai màu đối nhau thì vẫn phù hợp. Nếu nối hai màu bằng nhau, ràng buộc không thể thỏa và có thể dựng chu trình lẻ.

### Thời điểm đánh dấu đã thăm

Đặt color[v] ngay **khi đưa v vào queue**, không phải khi lấy v khỏi queue. Một đỉnh có thể có nhiều hàng xóm cùng muốn đưa nó vào; tô ngay ngăn việc đưa trùng và bảo đảm mỗi đỉnh được thêm vào queue nhiều nhất một lần.

## 4. Vì sao phải duyệt mọi thành phần liên thông?

Cho đồ thị 7 đỉnh với các cạnh:

~~~text
1 -- 2 -- 3       4 -- 5       6       7

Thanh phan 1: {1,2,3}
Thanh phan 2: {4,5}
Thanh phan 3: {6}
Thanh phan 4: {7}
~~~

BFS từ đỉnh 1 chỉ tô 1,2,3. Nếu kết luận thành công ngay, ta chưa kiểm tra các thành phần khác; một thành phần khác hoàn toàn có thể chứa tam giác.

Giải pháp là quét r từ 1 đến n. Nếu r chưa tô:

1. Bắt đầu một BFS mới.
2. Gán r màu 0.
3. Tô mọi đỉnh trong thành phần đó.
4. Sau khi hết queue, tiếp tục tìm thành phần chưa xử lý.

Với thứ tự tăng dần trong ví dụ, một phép tô hợp lệ là:

~~~text
color[1..7] = [0,1,0,0,1,0,0]

A = [1,3,4,6,7]
B = [2,5]
~~~

Mỗi thành phần có thể **đổi đồng thời 0↔1** mà vẫn hợp lệ, vì không có cạnh nối các thành phần khác nhau. Bởi vậy, hai nhóm được trả ra **không nhất thiết duy nhất**.

### Đỉnh cô lập

Đỉnh không có hàng xóm có thể nhận màu 0 hoặc 1. Mã minh họa gán 0 khi bắt đầu thành phần mới. Một đỉnh cô lập **không làm đồ thị mất tính hai phía**.

### Lưu ý về bài toán “hai nhóm phải đều không rỗng”

Định nghĩa hai phía chuẩn cho phép nhóm rỗng. Nếu một đề yêu cầu cả A lẫn B có ít nhất một đỉnh, cần **kiểm tra thêm điều kiện đầu ra**; đừng thay đổi định nghĩa cốt lõi một cách âm thầm. Ví dụ đồ thị một đỉnh, không cạnh là bipartite nhưng không thể chia thành **hai nhóm đều không rỗng**.

## 5. Truy vết BFS trên chu trình chẵn và chu trình lẻ

### Chu trình chẵn

~~~text
1 -- 2
|    |
4 -- 3
~~~

Các cạnh: (1,2),(2,3),(3,4),(4,1).

Bắt đầu ở 1 màu 0:

- Tô 2 và 4 màu 1.
- Từ 2 tô 3 màu 0.
- Từ 4 nhìn thấy 3 màu 0, đối với màu 1 của 4, nên hợp lệ.

Kết quả:

**A={1,3}, B={2,4}**.

### Chu trình lẻ 5 cạnh

~~~text
1 -- 2 -- 3
|         |
5 -------4
~~~

Các cạnh: (1,2),(2,3),(3,4),(4,5),(5,1).

Bắt đầu từ 1:

- color[1]=0.
- color[2]=color[5]=1.
- Từ 2 tô 3 màu 0.
- Từ 5 tô 4 màu 0.
- Khi xét cạnh (3,4), cả hai cùng màu 0 ⇒ mâu thuẫn.

Đường trong cây BFS từ 3 về 1 là 3—2—1. Đường từ 1 đến 4 là 1—5—4. Thêm cạnh 4—3 tạo:

**3 → 2 → 1 → 5 → 4 → 3**,

một chu trình lẻ có **5 cạnh**.

### Đồ thị có chu trình lẻ trong thành phần về sau

~~~text
1 -- 2      3      4
                    / \
                   5---6      7
~~~

Thành phần {1,2} và các đỉnh cô lập không gây vấn đề. Nhưng tam giác {4,5,6} khiến **toàn đồ thị không bipartite**. Điều này kiểm tra trực tiếp việc quét các thành phần chưa thăm.

## 6. Chứng cứ khi không hai phía: khôi phục một chu trình lẻ

Đối với bài chỉ hỏi YES/NO, có thể dừng ngay khi thấy cạnh cùng màu. Tuy nhiên, trong bài cần **giải thích lý do hoặc in chứng cứ**, chỉ trả false đôi khi chưa đủ. Ta có thể dựng **một chu trình lẻ** từ thông tin BFS.

Khi phát hiện cạnh {u,v} nối hai đỉnh đã có cùng màu, lưu:

- **parent[x]:** cha của x trong cây BFS, gốc có parent=−1.
- **depth[x]:** số cạnh từ gốc BFS đến x.

Hai đỉnh u,v nằm trong **cùng một thành phần**, vì giữa chúng có cạnh. Các chuỗi parent đi lên sẽ gặp nhau ở một **tổ tiên chung**.

### Thuật toán dựng chu trình

1. Đặt a=u và b=v.
2. Trong khi depth[a]>depth[b], đưa a vào nhánh trái và đi a=parent[a].
3. Trong khi depth[b]>depth[a], đưa b vào nhánh phải và đi b=parent[b].
4. Trong khi a≠b, thêm cả a và b vào hai nhánh, rồi cùng đi lên.
5. Khi a=b, đó là tổ tiên chung gần nhất trong cây BFS; thêm nó đúng một lần.
6. Đảo danh sách nhánh phải và nối vào sau nhánh trái. Ta thu đường đơn **u ... LCA ... v**.
7. Nối lại **u** ở cuối để thể hiện cạnh xung đột **v→u** khép chu trình.

Vì u,v có cùng màu, depth[u] và depth[v] cùng parity. Độ dài đường đi qua cây giữa chúng là:

**depth[u] + depth[v] − 2×depth[LCA]**,

một **số chẵn**. Thêm cạnh xung đột u—v làm tổng số cạnh **lẻ**.

Đường qua LCA trong cây không lặp đỉnh; sau khi nối cạnh u—v, ta có một chu trình lẻ đơn (trừ việc lặp điểm đầu ở cuối để biểu diễn chu trình đóng).

### Self-loop

Nếu cạnh là {u,u}, chính nó mâu thuẫn với điều kiện color[u]≠color[u]. Có thể in chu trình **[u,u]**, nghĩa là đi từ u qua **một cạnh tự nối** quay lại u. Đây là chu trình lẻ có độ dài 1 trong mô hình cho phép khuyên.

### Chu trình nhận được có phải ngắn nhất?

**Không bảo đảm.** BFS dùng đường đi ngắn nhất từ một **gốc thành phần**, nhưng khi phát hiện xung đột, chu trình dựng từ hai đường parent và một cạnh không nhất thiết là **chu trình lẻ ngắn nhất toàn đồ thị**. Bài chỉ yêu cầu một chứng cứ thì thuật toán O(n+m) là đủ; bài tìm **odd girth** (độ dài chu trình lẻ ngắn nhất) là bài khác.

## 7. Java 17+: chương trình hoàn chỉnh BFS tô màu và in chu trình lẻ

Chương trình sử dụng đồ thị vô hướng với đỉnh đánh số **1..n** ở đầu vào và đầu ra. Nội bộ dùng mảng chỉ số **0..n−1**.

Hàm **check** trả một record chứa:

- **bipartite:** true/false.
- **color:** mảng màu ở chỉ số nội bộ, −1 là chưa thăm.
- **groupA/groupB:** hai nhóm đỉnh khi hợp lệ, sắp theo nhãn tăng dần.
- **oddCycle:** một chu trình lẻ theo nhãn 1..n khi không hợp lệ, đỉnh đầu được lặp lại ở cuối.

Khi không bipartite, chương trình trả hai danh sách nhóm rỗng vì phép tô lúc đó **chưa phải phân hoạch hai phía hợp lệ**. Mảng color lúc lỗi chỉ phản ánh trạng thái đã duyệt, không nên dùng để tuyên bố có hai nhóm hợp lệ.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class BipartiteColoringDemo {

    record Result(boolean bipartite, int[] color,
                  List<Integer> groupA, List<Integer> groupB,
                  List<Integer> oddCycle) {}

    // Input vertices are labeled 1..n. Graph is undirected.
    static Result check(int n, int[][] edges) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be nonnegative");
        }
        Objects.requireNonNull(edges, "edges");

        List<List<Integer>> adj = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            adj.add(new ArrayList<>());
        }

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException("Invalid edge format");
            }
            int u = edge[0] - 1;
            int v = edge[1] - 1;
            if (u < 0 || u >= n || v < 0 || v >= n) {
                throw new IllegalArgumentException("Vertex out of range");
            }

            // Store both directions of each undirected edge.
            // A self-loop only needs one adjacency entry.
            adj.get(u).add(v);
            if (u != v) {
                adj.get(v).add(u);
            }
        }

        int[] color = new int[n];
        int[] parent = new int[n];
        int[] depth = new int[n];
        int[] queue = new int[n];

        Arrays.fill(color, -1);
        Arrays.fill(parent, -1);

        // A new BFS is needed for every uncolored component.
        for (int root = 0; root < n; root++) {
            if (color[root] != -1) {
                continue;
            }

            int head = 0;
            int tail = 0;
            color[root] = 0;
            depth[root] = 0;
            queue[tail++] = root;

            while (head < tail) {
                int u = queue[head++];

                for (int v : adj.get(u)) {
                    if (color[v] == -1) {
                        color[v] = 1 - color[u];
                        parent[v] = u;
                        depth[v] = depth[u] + 1;
                        queue[tail++] = v;
                    } else if (color[v] == color[u]) {
                        return new Result(
                                false, color,
                                List.of(), List.of(),
                                buildOddCycle(u, v, parent, depth));
                    }
                }
            }
        }

        List<Integer> groupA = new ArrayList<>();
        List<Integer> groupB = new ArrayList<>();

        for (int u = 0; u < n; u++) {
            if (color[u] == 0) {
                groupA.add(u + 1);
            } else {
                groupB.add(u + 1);
            }
        }

        return new Result(
                true, color, List.copyOf(groupA),
                List.copyOf(groupB), List.of());
    }

    // Called when color[u] == color[v].
    // Returns a closed odd cycle, with the first vertex repeated.
    private static List<Integer> buildOddCycle(
            int u, int v, int[] parent, int[] depth) {

        if (u == v) {
            return List.of(u + 1, u + 1); // self-loop
        }

        List<Integer> left = new ArrayList<>();
        List<Integer> right = new ArrayList<>();
        int a = u;
        int b = v;

        while (depth[a] > depth[b]) {
            left.add(a + 1);
            a = parent[a];
        }
        while (depth[b] > depth[a]) {
            right.add(b + 1);
            b = parent[b];
        }
        while (a != b) {
            left.add(a + 1);
            right.add(b + 1);
            a = parent[a];
            b = parent[b];
        }

        // a == b is the common ancestor.
        left.add(a + 1);
        Collections.reverse(right);
        left.addAll(right);

        // Close the cycle using the conflict edge (v,u).
        left.add(u + 1);
        return List.copyOf(left);
    }

    static void show(String label, Result answer) {
        if (answer.bipartite()) {
            System.out.println(label + ": YES; A="
                    + answer.groupA() + "; B=" + answer.groupB());
        } else {
            System.out.println(label + ": NO; odd cycle="
                    + answer.oddCycle());
        }
    }

    public static void main(String[] args) {
        show("Path", check(5, new int[][] {
                {1, 2}, {2, 3}, {3, 4}, {4, 5}
        }));

        show("Triangle", check(3, new int[][] {
                {1, 2}, {2, 3}, {3, 1}
        }));

        show("Disconnected", check(7, new int[][] {
                {1, 2}, {2, 3}, {4, 5}
        }));

        show("Even cycle", check(4, new int[][] {
                {1, 2}, {2, 3}, {3, 4}, {4, 1}
        }));

        show("Odd cycle 5", check(5, new int[][] {
                {1, 2}, {2, 3}, {3, 4}, {4, 5}, {5, 1}
        }));

        show("Self loop", check(3, new int[][] {
                {1, 1}, {1, 2}
        }));

        show("Parallel edges", check(2, new int[][] {
                {1, 2}, {1, 2}
        }));

        show("Empty", check(0, new int[][] {}));
    }
}
~~~

Lưu tên tệp **BipartiteColoringDemo.java** với mã nguồn UTF-8. Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 BipartiteColoringDemo.java
java BipartiteColoringDemo
~~~

**Đầu ra chính xác** của ví dụ:

~~~text
Path: YES; A=[1, 3, 5]; B=[2, 4]
Triangle: NO; odd cycle=[2, 1, 3, 2]
Disconnected: YES; A=[1, 3, 4, 6, 7]; B=[2, 5]
Even cycle: YES; A=[1, 3]; B=[2, 4]
Odd cycle 5: NO; odd cycle=[3, 2, 1, 5, 4, 3]
Self loop: NO; odd cycle=[1, 1]
Parallel edges: YES; A=[1]; B=[2]
Empty: YES; A=[]; B=[]
~~~

**Vì sao đầu ra có tính xác định ở các ví dụ?**

- Thành phần được khởi động tại **đỉnh chưa tô có nhãn nhỏ nhất** vì vòng for root tăng dần.
- Danh sách kề giữ **thứ tự xuất hiện của cạnh trong input**.
- BFS lấy node theo FIFO; vì vậy thứ tự tạo parent và cạnh xung đột được phát hiện là xác định đối với input đã cho.
- Các nhóm A/B được in theo **nhãn đỉnh tăng dần**, không phụ thuộc thứ tự lấy ra của queue.
- Nếu đổi thứ tự cạnh đầu vào, **một chu trình lẻ khác** có thể được xuất ra; điều này hoàn toàn đúng nếu chu trình mới vẫn hợp lệ.

## 8. Phân tích từng thành phần của chương trình

### Xây danh sách kề

Mỗi cạnh vô hướng {u,v} được thêm vào:

- Danh sách kề của u với đỉnh v.
- Danh sách kề của v với đỉnh u nếu u≠v.

Điều kiện u≠v tránh lưu khuyên hai lần không cần thiết. Dù lưu hai lần cũng vẫn phát hiện được self-loop, nhưng dùng một lần giúp đơn giản.

**Cạnh song song** vẫn được thêm theo đúng số lần xuất hiện. Duyệt màu không bị sai vì kiểm tra một cạnh hợp lệ lần thứ hai chỉ thấy hai màu đối nhau. Nếu cần hiệu quả cho đồ thị có rất nhiều cạnh trùng, có thể khử trùng nhưng phải xét chi phí và hợp đồng dữ liệu.

### Mảng màu và queue

color ban đầu bằng −1; khi tô r=0 màu 0, BFS lan truyền màu đối qua cạnh. Một đỉnh chỉ được enqueue khi color còn −1, nên nó xuất hiện trong queue đúng một lần.

queue là **int[n]**, tái sử dụng cho từng thành phần, mỗi lần đặt head=tail=0. Trong một BFS đơn lẻ, số đỉnh được enqueue không vượt số đỉnh của thành phần và không vượt n; do đó không tràn kích thước queue nếu dữ liệu đầu vào hợp lệ.

### Mảng parent và depth

Được cập nhật **khi tô màu v lần đầu**, vì lúc đó u là cha của v trong cây BFS. Các đường parent đi lên tạo một cây, không có vòng vì chỉ gán parent khi đỉnh chưa thăm.

Ở gốc thành phần, parent[root]=−1 và depth[root]=0. Khi phát hiện cạnh cùng màu u—v, hai đỉnh thuộc cùng thành phần nên đường parent của chúng luôn có tổ tiên chung; thuật toán buildOddCycle có thể đi lên tới điểm gặp mà không phải vượt khỏi gốc.

### Trả kết quả

Khi gặp cạnh xung đột:

- bipartite=false.
- groupA/groupB rỗng theo hợp đồng API.
- oddCycle chứa **một chứng cứ lẻ**.

Nếu BFS tất cả thành phần mà không có xung đột:

- bipartite=true.
- Mọi đỉnh đã có màu 0 hoặc 1.
- groupA và groupB tạo đúng một phân hoạch theo hai màu.
- oddCycle rỗng.

**Một lưu ý về record:** Java record tự tạo các accessor như answer.bipartite(), answer.groupA(). Với trường int[] color, accessor trả **tham chiếu mảng**; nếu API công khai cần tính bất biến tuyệt đối, phải tạo defensive copy trong constructor/accessor. Bài demo không sửa mảng kết quả sau khi check và không dựa vào bảo đảm bất biến của array.

## 9. Chứng minh tính đúng của thuật toán BFS hai màu

### Bổ đề 1: nếu thuật toán trả YES thì đồ thị hai phía

Thuật toán chỉ trả YES sau khi đã duyệt **mọi đỉnh** của mọi thành phần. Mọi đỉnh đã được gán màu 0 hoặc 1.

Xét một cạnh {u,v} bất kỳ. Khi duyệt u:

- Nếu v chưa tô, thuật toán gán color[v]=1−color[u].
- Nếu v đã tô và cùng màu u, thuật toán sẽ trả NO ngay.
- Nếu thuật toán cuối cùng trả YES thì trường hợp cùng màu **không xảy ra** đối với bất kỳ cạnh nào.

Vì vậy mọi cạnh nối hai màu khác nhau. Hai tập các đỉnh màu 0 và màu 1 thỏa định nghĩa phân hoạch bipartite.

### Bổ đề 2: nếu thuật toán trả NO thì đồ thị không hai phía

Thuật toán chỉ trả NO khi thấy một cạnh u—v có color[u]=color[v]. Do màu được gán theo **parity của đường đi trong cây BFS**, đường đi cây giữa u và v có số cạnh chẵn. Thêm cạnh u—v tạo một chu trình có số cạnh lẻ, hoặc chính cạnh là một khuyên u=u dài 1.

Theo định lý ở mục 2, đồ thị chứa chu trình lẻ nên không thể tô hai màu hợp lệ.

### Định lý

Từ hai bổ đề:

- YES ⇒ bipartite.
- NO ⇒ không bipartite.

Thuật toán luôn kết thúc vì mỗi đỉnh chỉ được tô/enqueue tối đa một lần, mọi vòng lặp duyệt danh sách hữu hạn. Vậy nó quyết định tính hai phía **đúng cho mọi đồ thị vô hướng hữu hạn** theo hợp đồng đầu vào đã nêu.

Chứng minh không phụ thuộc vào việc tô gốc mỗi thành phần là 0 hay 1: đảo màu toàn bộ một thành phần vẫn giữ quan hệ khác màu trên mọi cạnh của thành phần ấy.

## 10. Độ phức tạp thời gian và bộ nhớ

Gọi:

- **n=|V|** số đỉnh.
- **m=|E|** số cạnh vô hướng (tính cả cạnh song song nếu được cho).

Với danh sách kề:

- Khởi tạo n danh sách: **O(n)**.
- Thêm mỗi cạnh vào một hoặc hai danh sách: **O(m)**.
- Mỗi đỉnh được enqueue/dequeue tối đa một lần: **O(n)**.
- Mỗi phần tử của danh sách kề được duyệt tối đa một lần khi xử lý đỉnh đầu; tổng khoảng **2m** với cạnh không phải khuyên: **O(m)**.
- Nếu có mâu thuẫn, dựng một chu trình lẻ đi theo parent/depth tối đa **O(n)**.

Vậy tổng thời gian:

**O(n+m)**.

Bộ nhớ:

- Danh sách kề: **O(n+m)**.
- color, parent, depth, queue: **O(n)**.
- Nhóm đỉnh hoặc chu trình làm chứng cứ: **O(n)**.

Tổng bộ nhớ:

**O(n+m)**.

### Nếu dùng ma trận kề?

Ma trận kề có n×n ô nên **O(n²)** bộ nhớ; để tìm hàng xóm của mỗi u thường phải quét cả một hàng, đưa thời gian duyệt lên **O(n²)**, kể cả đồ thị thưa.

Với input dạng danh sách cạnh và n,m lớn, danh sách kề thường là lựa chọn tốt hơn cho bài kiểm tra hai phía.

### Nếu chỉ cần true/false?

Không bắt buộc lưu parent/depth hoặc dựng chu trình. Chỉ cần color và queue/stack; vẫn O(n+m) thời gian và O(n+m) tổng bộ nhớ nếu tính cả adjacency. Nếu graph đã có sẵn, phần bộ nhớ phụ cho color và queue là **O(n)**.

## 11. Dùng DFS thay BFS có được không?

**Có.** Ta có thể thay queue FIFO bằng stack LIFO hoặc hàm đệ quy.

Logic tô màu giữ nguyên:

~~~text
color[*] = -1

for root:
    if color[root] != -1:
        continue

    color[root] = 0
    DFS(root)

DFS(u):
    for v adjacent to u:
        if color[v] == -1:
            color[v] = 1 - color[u]
            DFS(v)
        else if color[v] == color[u]:
            report conflict
~~~

Nếu dùng hàm DFS trả boolean:

~~~text
dfs(u):
    for v adjacent to u:
        if color[v] == -1:
            color[v] = 1 - color[u]
            if !dfs(v):
                return false
        else if color[v] == color[u]:
            return false
    return true
~~~

Cần kiểm tra giá trị false được truyền ngược lên các lời gọi. Cũng phải chạy DFS từ **mọi gốc thành phần chưa tô**.

**Kết quả YES/NO của BFS và DFS phải giống nhau**, vì cả hai cùng kiểm tra khả năng gán hai màu theo cạnh. Chúng có thể tạo **màu khác nhau giữa các thành phần** nếu chọn gốc khác nhau, hoặc có cây duyệt/chu trình chứng cứ khác nhau.

### Ưu/nhược của DFS đệ quy

- Code ngắn, dễ đọc khi graph nhỏ hoặc chiều sâu giới hạn.
- Độ phức tạp vẫn O(n+m).
- Tuy nhiên, đồ thị dạng đường đi có n đỉnh có thể tạo ngăn xếp lời gọi sâu O(n), dẫn đến **StackOverflowError trong Java** với n lớn.

BFS dùng queue tường minh không có nguy cơ tràn call stack do đệ quy. DFS dùng stack tường minh cũng tránh được lỗi ấy.

### Cần phân biệt hai bài toán

- **Kiểm tra bipartite:** cần tìm một cách tô 2 màu phù hợp; cả BFS và DFS đều làm được.
- **Tìm khoảng cách ngắn nhất từ nguồn trong đồ thị không trọng số:** BFS có tính chất riêng về mức khoảng cách; DFS thông thường không bảo đảm khoảng cách ngắn nhất.

Mặc dù BFS trong bài bipartite cũng tạo depth theo khoảng cách ngắn nhất từ mỗi gốc thành phần, mục tiêu ở đây là **parity và mâu thuẫn màu**, không phải xuất khoảng cách cho mọi cặp đỉnh.

## 12. Cạnh đặc biệt và ngữ nghĩa đồ thị

### Cạnh tự nối (self-loop)

Cạnh {u,u} yêu cầu **color[u]≠color[u]**, điều bất khả thi. Chỉ một self-loop đủ kết luận NO, kể cả khi mọi cạnh khác tạo đồ thị hai phía.

Trong một số bài định nghĩa “đồ thị đơn” loại self-loop ngay từ input. Nếu dữ liệu thực tế vẫn có self-loop, thuật toán nên xử lý rõ ràng thay vì silently bỏ nó vì sẽ cho kết quả sai.

### Cạnh song song

Hai cạnh cùng nối u—v với u≠v **không tạo mâu thuẫn**: nếu một cạnh hợp lệ thì cạnh còn lại đòi đúng cùng điều kiện đối màu.

Ví dụ n=2, E={{1,2},{1,2}}, kết quả YES với A={1}, B={2}. Không nên nhầm “chu trình có 2 cạnh” trong một số quy ước đa đồ thị với **chu trình lẻ**; độ dài 2 là chẵn.

### Đỉnh không có cạnh

Một đỉnh cô lập là thành phần riêng. Ta có thể gán tùy ý một trong hai màu; bài demo chọn màu 0. Khi **n=0 và không có cạnh**, mọi ràng buộc đều được thỏa vacuously, nên YES với hai nhóm rỗng.

### Đồ thị vô hướng hay có hướng?

Thuật toán trong bài học mô hình hóa **mỗi cạnh như vô hướng**. Nếu input là các **cung có hướng** nhưng câu hỏi là “có thể chia các đỉnh thành hai tập sao cho mỗi cung nối hai tập khác nhau?”, hãy **bỏ hướng** của cung khi kiểm tra điều kiện hai màu.

Nếu bài toán hỏi một tính chất riêng của đồ thị có hướng (ví dụ chu trình có hướng lẻ, đồ thị DAG, tính hai phía của đồ thị hai loại cung…), không được tự động dùng cùng định lý chu trình lẻ của **đồ thị vô hướng**.

Ví dụ cung **1→2**, **1→3**, **2→3** không tạo chu trình có hướng, nhưng khi bỏ hướng thành tam giác 1—2—3—1 nên **không thể chia các đầu cung thành hai phía đối nhau**. Không có chu trình có hướng không đủ kết luận bipartite của đồ thị nền vô hướng.

### Định dạng đánh số

Đề có thể đánh số 0..n−1 hoặc 1..n. Mã minh họa nhận nhãn **1..n**, rồi trừ 1 khi dựng graph. Nếu đề dùng 0..n−1, phải bỏ phép trừ và sửa cách in kết quả; làm nửa vời dễ tạo lỗi off-by-one.

## 13. Ứng dụng của kiểm tra hai phía

### 13.1. Chia người/vật thành hai nhóm theo quan hệ xung khắc

Mỗi đỉnh là một đối tượng, cạnh {u,v} nghĩa là **u và v phải ở hai nhóm khác nhau**.

Nếu graph bipartite, lấy chính hai lớp màu làm phân công hợp lệ. Nếu không, chu trình lẻ cung cấp một **chuỗi mâu thuẫn**: đảo nhóm qua số ràng buộc lẻ rồi quay về đối tượng ban đầu, đòi cùng đối tượng ở nhóm đối lập.

Ví dụ chia các đội vào hai ca, hoặc xếp đối tượng vào hai cụm đối lập. Phải bảo đảm ràng buộc đầu vào đúng là “khác nhóm”, không phải “cùng nhóm” hay một quan hệ có hướng phức tạp.

### 13.2. Kiểm tra tính chẵn của chu trình

Một đồ thị vô hướng **không có chu trình lẻ** chính là đồ thị hai phía. Vì vậy kiểm tra bipartite có thể xem là cách **phát hiện sự tồn tại của chu trình lẻ** trong O(n+m), không cần liệt kê tất cả chu trình.

### 13.3. Nền tảng cho ghép cặp hai phía

Nhiều thuật toán tìm **matching trên đồ thị hai phía** giả định đã có hai tập đỉnh trái và phải. Tô màu cung cấp phân hoạch này khi graph chỉ được cho ở dạng vô hướng.

Tuy nhiên, **kiểm tra bipartite** chỉ trả hai tập màu; nó **không tìm matching cực đại**. Sau khi có A/B, cần thuật toán ghép cặp riêng như augmenting paths hoặc Hopcroft–Karp tùy kích thước.

### 13.4. Đếm số cách tô màu nếu không có đỉnh bị cố định

Giả sử đồ thị vô hướng hai phía có **c thành phần liên thông**, kể cả các đỉnh cô lập. Nếu màu 0/1 là **hai nhãn phân biệt** và không có ràng buộc màu cố định, mỗi thành phần có đúng **hai cách** chọn màu cho một gốc rồi các màu còn lại được ép theo cạnh.

Vì vậy số phép tô hai màu hợp lệ là:

**2ᶜ**.

Ví dụ đường đi 1—2—3 là một thành phần: có hai phép tô, [0,1,0] và [1,0,1]. Nếu có thêm đỉnh cô lập 4, nó có thể chọn 0/1 độc lập, tổng là 2²=4 phép tô.

Với đồ thị rỗng n=0, c=0 và có đúng **một ánh xạ màu rỗng**, tương ứng 2⁰=1.

Nếu đề coi hai phép tô chỉ khác nhau vì **đổi tên hai màu trên toàn đồ thị** là cùng một phân hoạch không gắn nhãn, phép đếm phải điều chỉnh theo quy ước; không được mặc định dùng 2ᶜ cho mọi cách đếm nhóm.

## 14. Bài toán nâng cao: có ràng buộc cùng màu/khác màu

Một số đề không cho graph thuần túy, mà cho các quan hệ giữa u,v:

- **same(u,v):** u và v phải có cùng màu.
- **different(u,v):** u và v phải có màu khác nhau.

Có thể biểu diễn dưới dạng phương trình XOR:

**color[u] XOR color[v] = p**,

trong đó p=0 cho **cùng màu**, p=1 cho **khác màu**.

Nếu toàn bộ ràng buộc đều p=1, đây chính là kiểm tra đồ thị hai phía.

Nếu có cả p=0 và p=1, BFS/DFS vẫn hoạt động theo công thức tổng quát:

**color[v] = color[u] XOR p** khi v chưa tô,

và báo mâu thuẫn nếu màu đã gán không thỏa công thức. Với mỗi thành phần ràng buộc, chọn gốc màu 0 rồi lan truyền.

Một kỹ thuật khác là **DSU có parity** (disjoint set union with parity) để xử lý các ràng buộc được đưa vào dần, theo dõi quan hệ XOR giữa đỉnh và đại diện tập. DSU thường hữu ích khi cần cập nhật trực tuyến hoặc phát hiện mâu thuẫn ngay sau mỗi quan hệ được thêm.

**Lưu ý:** chỉ DSU thông thường không lưu parity thì không đủ để kiểm tra điều kiện “khác màu”; cần thêm thông tin quan hệ chẵn/lẻ.

### Khi có đỉnh bị cố định màu

Nếu một số đỉnh bắt buộc màu 0 hoặc 1, không còn quyền tự do đảo màu tùy ý từng thành phần. Ta phải lan truyền cả ràng buộc cố định; nếu các ràng buộc đặt ra hai màu mâu thuẫn trong cùng thành phần, bài toán vô nghiệm ngay cả khi graph nền hai phía.

Phần code chính chỉ giải bài chuẩn **không có đỉnh bị cố định**.

## 15. Biến thể: yêu cầu cân bằng kích thước hai nhóm

Một đồ thị có thể bipartite nhưng việc chia thành hai nhóm **kích thước bằng nhau** hoặc chênh lệch không quá 1 chưa chắc khả thi.

Mỗi thành phần liên thông hai phía có hai kích thước lớp màu, giả sử (aᵢ,bᵢ). Ta có thể:

- Giữ nguyên hướng tô của thành phần: đóng góp aᵢ vào nhóm A, bᵢ vào nhóm B.
- Đảo màu cả thành phần: đóng góp bᵢ vào A, aᵢ vào B.

Bài cân bằng nhóm có thể trở thành một **quy hoạch động theo tổng số đỉnh chọn vào A** trên các thành phần, chứ không chỉ kiểm tra bipartite.

Ví dụ một thành phần hình sao có một tâm và ba lá: hai lớp có kích thước (1,3). Graph bipartite nhưng với một thành phần duy nhất, không thể tạo hai nhóm (2,2) bằng cách tô màu hợp lệ. Ngược lại, hai thành phần có thể được đảo tương đối để cân bằng.

**Điểm phân biệt:** “có tồn tại hai màu hợp lệ” là câu hỏi khác “có hai màu hợp lệ thỏa đúng kích thước từng nhóm”. Câu thứ hai cần thêm bước tối ưu/DP theo thành phần.

## 16. Những lỗi phổ biến

1. **Chỉ BFS/DFS từ đỉnh 1**, bỏ qua các thành phần khác. Phải quét toàn bộ đỉnh chưa tô.
2. **Khởi tạo color bằng 0 thay vì −1**, khiến không phân biệt chưa thăm với màu thật.
3. **Tô v cùng màu u** khi gặp cạnh; đúng phải là **1−color[u]**.
4. **Không kiểm tra cạnh tới đỉnh đã tô**; có thể bỏ sót tam giác/chu trình lẻ.
5. **Đánh dấu v khi dequeue thay vì enqueue**, khiến v bị đưa vào queue nhiều lần và màu bị gán không nhất quán.
6. **Quên self-loop**, mặc dù {u,u} luôn khiến graph không bipartite.
7. **Coi cạnh song song là chu trình lẻ**, trong khi hai cạnh tạo chu trình độ dài 2, là chẵn.
8. **Nhầm số đỉnh của graph lẻ với không bipartite**; đường đi có 5 đỉnh vẫn bipartite.
9. **Nhầm đồ thị có chu trình với không bipartite**; chu trình 4 cạnh hợp lệ.
10. **Cho rằng đồ thị hai phía không được có đỉnh cô lập**; đỉnh cô lập được tô tùy ý.
11. **Xây adjacency một chiều cho graph vô hướng**, rồi kết luận dựa trên việc chưa thấy cạnh ngược.
12. **Không xử lý vertex index 0-based/1-based nhất quán**, dễ gây ArrayIndexOutOfBoundsException.
13. **Dùng DFS đệ quy trên đường đi rất dài**, có nguy cơ StackOverflowError.
14. **Nhầm odd cycle certificate với shortest odd cycle**; BFS phát hiện một chu trình lẻ không bảo đảm ngắn nhất.
15. **Đếm cách tô bằng 2ⁿ** thay vì dựa vào số thành phần liên thông, khi cạnh ép màu trong mỗi thành phần.
16. **Nhầm hai cách hoán đổi nhãn A/B là hai lời giải khác nhau** khi đề coi hai nhóm không có tên.
17. **Kết luận một cách tô là duy nhất**, dù mỗi thành phần có thể đảo màu.
18. **Áp dụng định lý chu trình vô hướng vào chu trình có hướng** mà không xác định rõ bài đang xét underlying graph hay đồ thị định hướng.
19. **Coi bipartite test là thuật toán matching**, trong khi nó chưa hề chọn các cặp.
20. **Đem màu tạm trong kết quả NO làm hai nhóm hợp lệ**, mặc dù có ít nhất một cạnh phá vỡ phân hoạch.
21. **Không khử trùng hay không làm rõ multigraph** khi đề có giả thiết graph đơn; code phải xử lý đúng theo hợp đồng đầu vào.
22. **Dừng khi đã tô được một số đỉnh mà chưa kiểm tra mọi cạnh**; màu trên cạnh chưa duyệt có thể mâu thuẫn.
23. **Bỏ qua ràng buộc kích thước nhóm hoặc màu cố định** nếu đề có yêu cầu bổ sung ngoài tính hai phía.
24. **Chỉ thử ví dụ đẹp, không thử graph rỗng và nhiều thành phần**, dễ bỏ qua các ca biên.

## 17. Kiểm thử với vét cạn để đối chiếu

Với graph nhỏ n≤10, có thể làm một **oracle độc lập**:

1. Duyệt mọi bitmask từ 0 đến **2ⁿ−1**.
2. Bit i biểu thị màu 0/1 của đỉnh i.
3. Với mỗi cạnh {u,v}, kiểm tra bit[u] khác bit[v].
4. Nếu có một mask thỏa tất cả cạnh, graph bipartite; nếu không, graph không bipartite.

Vét cạn tốn **O(2ⁿ×m)**, chỉ phù hợp với n nhỏ để kiểm thử; không dùng cho production n lớn.

So kết quả của BFS hai màu với oracle trên nhiều graph:

- Graph không cạnh.
- Đường đi dài và ngắn.
- Cây nhị phân, cây hình sao (mọi cây đều hai phía).
- Chu trình chẵn/chu trình lẻ.
- Hai thành phần, trong đó thành phần sau chứa chu trình lẻ.
- Graph hoàn chỉnh K₃ (không bipartite), K₄ (không bipartite).
- Graph đầy đủ hai phía K₂,₃ (bipartite).
- Graph có cạnh song song.
- Graph có self-loop.
- Graph với các cạnh nhập theo nhiều thứ tự khác nhau.
- Đỉnh cô lập và graph rỗng.

Nếu thuật toán trả YES, kiểm tra thêm:

1. Mỗi đỉnh xuất hiện **đúng một lần** trong groupA hoặc groupB.
2. Màu mỗi đỉnh là 0 hoặc 1.
3. **Mọi cạnh** nối hai màu đối nhau.
4. Không có oddCycle.

Nếu thuật toán trả NO và có chu trình chứng cứ:

1. Phần tử đầu bằng phần tử cuối.
2. Số cạnh trong danh sách là **lẻ**.
3. Mỗi cặp đỉnh liên tiếp trong chứng cứ là một cạnh thật của input.
4. Ngoài đỉnh lặp để đóng vòng, các đỉnh nội bộ không bị lặp (với self-loop chứng cứ là [u,u]).
5. Không dùng những đỉnh ngoài 1..n.

### Các trường hợp cần chú ý

| Input | Có hai phía? | Lý do |
| --- | --- | --- |
| n=0,m=0 | Có | Không có ràng buộc nào bị vi phạm |
| n=1,m=0 | Có | Một đỉnh cô lập |
| n=1, cạnh (1,1) | Không | Self-loop, chu trình lẻ độ dài 1 |
| Cạnh (1,2) xuất hiện hai lần | Có | Ràng buộc khác màu lặp lại, không mâu thuẫn |
| Đường đi n đỉnh | Có | Tô luân phiên theo đường |
| Tam giác | Không | Chu trình lẻ độ dài 3 |
| Chu trình 4 cạnh | Có | Chu trình chẵn |
| Chu trình 5 cạnh | Không | Chu trình lẻ độ dài 5 |
| Một thành phần là tam giác, các thành phần khác là cây | Không | Chỉ một thành phần lỗi cũng khiến toàn graph lỗi |
| Graph không cạnh có 100 đỉnh | Có | Mỗi đỉnh tự chọn màu |

**Kiểm thử không thay thế chứng minh.** Một test random có thể bỏ qua cấu trúc gây lỗi. Cốt lõi đúng của BFS là việc lan truyền parity theo cạnh và định lý tương đương với không có chu trình lẻ.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Đồ thị hai phía có nghĩa là gì?  
**Đáp án:** Có thể chia mọi đỉnh thành A/B sao cho mỗi cạnh nối hai nhóm khác nhau; tương đương tô 2 màu để mọi cạnh khác màu.

**Câu 2.** Tại sao khi BFS qua cạnh (u,v) với v chưa tô, phải gán color[v]=1−color[u]?  
**Đáp án:** Vì cạnh buộc hai đầu khác màu. Với hai màu 0/1, phép 1−color[u] tạo màu đối diện.

**Câu 3.** Có thể kiểm tra đồ thị không liên thông chỉ bằng BFS từ đỉnh 1 không?  
**Đáp án:** Không. Cần chạy BFS từ mọi đỉnh còn màu −1 để phát hiện mâu thuẫn ở thành phần khác.

**Câu 4.** Đồ thị có 5 đỉnh và không cạnh có bipartite không?  
**Đáp án:** Có. Không có cạnh vi phạm, mọi đỉnh có thể đặt vào một trong hai phía.

**Câu 5.** Chu trình có 6 cạnh có khiến graph không bipartite không?  
**Đáp án:** Không, bản thân một chu trình chẵn vẫn có thể tô 2 màu xen kẽ.

**Câu 6.** Vì sao tam giác không bipartite?  
**Đáp án:** Ba cạnh tạo chu trình lẻ. Tô hai đỉnh kề đỉnh gốc màu đối diện dẫn đến hai đỉnh đó cùng màu nhưng có cạnh nối nhau.

**Câu 7.** Một cạnh tự nối có thể xuất hiện trong graph bipartite không?  
**Đáp án:** Không, vì đỉnh sẽ phải khác màu với chính nó.

**Câu 8.** Nếu graph có hai cạnh song song nối 1 và 2, có cần kết luận NO không?  
**Đáp án:** Không. Cả hai cùng đòi màu 1 và 2 khác nhau, hoàn toàn có thể thỏa.

**Câu 9.** Khi nhận cạnh cùng màu u—v trong BFS, độ dài đường đi trong cây BFS giữa u và v có tính chẵn/lẻ nào?  
**Đáp án:** Chẵn, vì depth[u] và depth[v] cùng parity. Thêm cạnh u—v tạo chu trình lẻ.

**Câu 10.** Mảng parent và depth có cần nếu chỉ trả true/false không?  
**Đáp án:** Không. Chúng phục vụ khôi phục chứng cứ chu trình lẻ.

**Câu 11.** BFS tô 2 màu trên danh sách kề chạy bao lâu?  
**Đáp án:** **O(n+m)** vì mỗi đỉnh được enqueue một lần và mỗi phần tử adjacency được quét một lần.

**Câu 12.** DFS có thể thay BFS để kiểm tra bipartite không?  
**Đáp án:** Có, dùng đúng quy tắc gán màu đối và duyệt mọi thành phần. DFS đệ quy có rủi ro độ sâu ngăn xếp.

**Câu 13.** Có 4 thành phần liên thông và graph bipartite; hai màu được gắn nhãn phân biệt. Có bao nhiêu cách tô màu hợp lệ nếu không có màu cố định?  
**Đáp án:** **2⁴=16**.

**Câu 14.** Nếu một bài yêu cầu cả hai nhóm phải có cùng kích thước, kiểm tra bipartite đã đủ chưa?  
**Đáp án:** Chưa. Cần xét khả năng đảo màu từng thành phần và kiểm tra/DP theo kích thước nhóm.

**Câu 15.** Có đồ thị có hướng không có chu trình có hướng; liệu underlying undirected graph chắc chắn bipartite không?  
**Đáp án:** Không. Các cung 1→2,1→3,2→3 tạo DAG nhưng underlying graph là tam giác.

## 19. Ghi nhớ

**Kiểm tra tính hai phía bằng tô màu** là một ứng dụng trực tiếp của BFS/DFS trên đồ thị vô hướng:

- Đồ thị hai phía ⇔ có thể tô mỗi đỉnh màu 0/1 sao cho **mọi cạnh nối hai màu khác nhau**.
- Khởi tạo **color=−1**, chọn gốc mới màu 0 cho **mọi thành phần liên thông**.
- Qua cạnh tới v chưa tô, gán **color[v]=1−color[u]**.
- Gặp cạnh nối **hai đỉnh cùng màu** ⇒ không bipartite.
- Mâu thuẫn tương đương tồn tại **chu trình lẻ**; có thể dùng parent/depth để in một chu trình làm chứng.
- Một self-loop phá tính hai phía; cạnh song song giữa hai đỉnh khác nhau không tự gây mâu thuẫn.
- BFS và DFS đều đúng; trên danh sách kề có độ phức tạp **O(n+m) thời gian**.
- Nếu cần **matching, cân bằng nhóm, màu cố định hoặc ràng buộc same/different**, đây là bài toán mở rộng cần bước xử lý riêng.

Cách tư duy cần nhớ là: **mỗi cạnh mang ràng buộc “đảo màu”**. Duyệt đồ thị sẽ lan truyền những ràng buộc ấy qua các thành phần; một cạnh đòi hai màu bằng nhau chính là chứng cứ rằng không thể phân chia toàn bộ đỉnh thành hai phía hợp lệ.
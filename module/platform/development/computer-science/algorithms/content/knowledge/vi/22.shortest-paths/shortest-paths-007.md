# Phân biệt không có đường đi với không có khoảng cách hữu hạn

Khi giải **đường đi ngắn nhất trên đồ thị có trọng số**, không phải câu trả lời nào cũng là một con số hữu hạn. Có hai tình huống khác bản chất nhưng thường bị gom nhầm: **không tồn tại đường đi** từ nguồn đến đích, và **có đường đi nhưng tổng trọng số có thể giảm vô hạn** nhờ lặp một chu trình âm. Một đỉnh thứ ba có thể có **khoảng cách ngắn nhất hữu hạn**, dù giá trị đó âm hoặc rất lớn.

Với nguồn s và đích t, bài toán shortest-walk chuẩn cần phân biệt:

1. **UNREACHABLE:** không có bất kỳ hành trình nào từ s đến t; theo quy ước toán học, d(s,t)=**+∞**.
2. **FINITE(x):** có hành trình và có chi phí nhỏ nhất **hữu hạn x**, có thể âm, bằng 0 hoặc dương.
3. **NEGATIVE_INFINITY (NEG_INF):** có hành trình từ s đến t, nhưng có thể đi vòng một chu trình âm bao nhiêu lần cũng được rồi tới t, nên chi phí giảm không có cận dưới. Khi ấy d(s,t)=**−∞**, nhưng không có một hành trình hữu hạn nào đạt đúng tổng −∞.

**Định lý quan trọng nhất:** Một đích t bị NEG_INF khi và chỉ khi tồn tại chu trình âm **nguồn s tới được**, và từ chu trình âm đó **đi tiếp tới t được**. Chỉ phát hiện graph có chu trình âm ở đâu đó là chưa đủ.

Bài học thuộc nhóm **Đường đi ngắn nhất**, trình bày ý nghĩa toán học, Bellman–Ford, lan truyền ảnh hưởng theo cung, xử lý dữ liệu lớn, code Java 17+ chạy độc lập, ví dụ và kiểm thử độc lập.

## 1. Walk, path và khoảng cách ngắn nhất

Cho đồ thị có hướng G=(V,E). Mỗi cung e có trọng số w(e), có thể âm. Một **walk** từ s đến t là một dãy các đỉnh bắt đầu ở s, kết thúc ở t, giữa hai đỉnh liên tiếp có một cung đúng chiều. Walk **được phép lặp đỉnh và cung**.

Chi phí walk P bằng **tổng các trọng số của các cung được đi qua**, tính cả những lần lặp. Định nghĩa khoảng cách ngắn nhất theo mô hình này:

**d(s,t) = inf {cost(P) : P là walk từ s tới t}.**

Infimum là cận dưới lớn nhất. Nếu tập không có walk nào, ta quy ước giá trị là +∞. Nếu có thể giảm chi phí tùy ý, infimum bằng −∞, không phải một minimum hữu hạn đạt được.

**Simple path** là đường đi không lặp đỉnh. Trong một đồ thị hữu hạn, số simple path giữa hai đỉnh là hữu hạn, nên nếu có simple path thì chi phí nhỏ nhất trên các simple path vẫn **hữu hạn**, kể cả graph có chu trình âm. Trường hợp NEG_INF trong bài này giả định walk được phép lặp chu trình.

Ví dụ có cung 1→2 trọng số 2, khuyên 2→2 trọng số −5, cung 2→3 trọng số 4:

- Simple path 1→2→3 có chi phí 6.
- Walk đi qua khuyên ở 2 k lần rồi mới tới 3 có chi phí 6−5k.
- Khi k tăng, chi phí giảm vô hạn, nên theo shortest-walk d(1,3)=−∞.

Nếu đề cấm lặp đỉnh hoặc cạnh, cần giải đúng bài ràng buộc ấy; không được tự động kết luận NEG_INF chỉ từ sự tồn tại chu trình âm.

## 2. Ba trạng thái bằng ví dụ

**Ví dụ A — không tới được:**

~~~text
1 --(4)--> 2       3 --(7)--> 4

Nguon s=1.
d(1,2)=4.
d(1,3)=+INF, d(1,4)=+INF: UNREACHABLE.
~~~

Không có kết nối từ 1 đến {3,4}. Dù cung 3→4 có trọng số nào, cũng không thể tạo walk từ 1 đến 4.

**Ví dụ B — giá trị âm nhưng hữu hạn:**

~~~text
1 --(8)--> 2 --(2)--> 4
 \         ^
  \(5)     |(-9)
    v      |
     3 ----+
      \--(20)--> 4

Duong 1->3->2->4: 5-9+2=-2.
Khong co chu trinh am.
d(1,4)=-2 la FINITE(-2).
~~~

Giá trị nhỏ hơn 0 không phải là −∞.

**Ví dụ C — có đường nhưng không có minimum hữu hạn:**

~~~text
1 --(2)--> 2 --(1)--> 3 --(3)--> 4
            ^          |
            +---(-4)---+

Chu trinh 2->3->2 co tong -3.
Chi phi toi 4 sau k vong: 6-3*k.
d(1,4)=-INF.
~~~

Đỉnh 4 hoàn toàn **đạt được**; không được báo UNREACHABLE.

## 3. Chu trình âm ảnh hưởng tới đích nào?

Xét:

~~~text
1 -> 2 (2)
2 -> 3 (1)
3 -> 2 (-4)
3 -> 4 (3)

1 -> 5 (10)
5 -> 6 (-2)
6 -> 7 (1)
~~~

Chu trình 2→3→2 có tổng −3, đạt được từ nguồn 1. Tuy nhiên, từ chu trình ấy không có đường tới 5,6,7.

| Đỉnh | Kết quả từ nguồn 1 | Giải thích |
| ---: | --- | --- |
| 1 | FINITE(0) | Không quay lại được 1 từ chu trình |
| 2 | NEG_INF | Nằm trên chu trình âm |
| 3 | NEG_INF | Nằm trên chu trình âm |
| 4 | NEG_INF | Có đường từ chu trình qua 3→4 |
| 5 | FINITE(10) | Nhánh không chịu ảnh hưởng chu trình |
| 6 | FINITE(8) | Đi 1→5→6 |
| 7 | FINITE(9) | Đi 1→5→6→7 |

Nếu bổ sung cung 4→7, lúc đó 7 cũng thành NEG_INF, vì có walk từ chu trình âm tới 7.

**Quan trọng:** một chu trình âm đạt được từ nguồn **không khiến mọi đỉnh đạt được từ nguồn đều có khoảng cách −∞**. Chỉ những đích nằm **sau** một chu trình âm đạt được mới bị ảnh hưởng.

Nếu chu trình âm ở một thành phần không tới được từ nguồn, các đỉnh ở đó **UNREACHABLE**, không phải NEG_INF.

## 4. Định lý nhận diện −∞ và chứng minh

Với graph hữu hạn, d(s,t)=−∞ khi và chỉ khi tồn tại chu trình C có tổng trọng số âm thỏa:

**s có walk tới C và C có walk tới t.**

**Chiều đủ:** gọi A là chi phí đoạn s→C, B là chi phí đoạn C→t, W<0 là chi phí đi một vòng C. Lặp C k lần rồi tới t sẽ có chi phí A+kW+B. Khi k→∞, chi phí →−∞.

**Chiều cần:** nếu có walk s→t với chi phí giảm không giới hạn, các walk dài có thể tách thành một đường đi đơn và các phần khép kín được lặp/chèn vào. Nếu không có chu trình âm nào đạt được từ s rồi dẫn tới t, bỏ những phần khép kín không âm không làm chi phí tăng. Chỉ còn hữu hạn đường đi đơn nên chi phí bị chặn dưới, mâu thuẫn. Vì vậy phải có chu trình âm ảnh hưởng đến t.

Hệ quả:

- Chu trình **dương** không làm giảm mục tiêu minimization.
- Chu trình có tổng trọng số **0** có thể tạo vô hạn walk cùng chi phí, nhưng minimum vẫn hữu hạn nếu không có chu trình âm liên quan.
- Một **đỉnh hậu duệ** của chu trình âm cũng có giá trị −∞, dù bản thân đỉnh ấy không thuộc chu trình.
- Một đỉnh chỉ có đường **đi tới chu trình** nhưng không có đường **từ chu trình quay về nó** không tự động NEG_INF.

## 5. Bellman–Ford: tính các giá trị ứng viên

Bellman–Ford cho phép trọng số âm và chạy trên danh sách cung.

Khởi tạo:

**dist[s]=0**; với mọi v khác s, chưa tìm được walk nên dist[v] mang trạng thái **UNSET**.

Relax cung u→v trọng số w:

- Nếu u chưa có walk từ nguồn thì bỏ qua.
- Nếu v chưa có giá trị, có thể thiết lập dist[v]=dist[u]+w.
- Nếu v đã có giá trị, cập nhật khi dist[u]+w < dist[v].

Pseudocode:

~~~text
dist[s] = 0
dist[v != s] = UNSET

for pass = 1 .. n-1:
    changed = false
    for moi cung u->v trong E:
        if dist[u] chua co:
            continue
        cand = dist[u] + weight(u,v)
        if dist[v] chua co or cand < dist[v]:
            dist[v] = cand
            changed = true
    if not changed:
        break
~~~

**Vì sao n−1 lượt?** Bất kỳ đỉnh đạt được nào cũng có một đường đi đơn từ nguồn, gồm tối đa n−1 cung. Qua đủ n−1 lượt quét toàn bộ các cung, thông tin đạt được và chi phí của các đường đi đơn có thể lan tới mọi đỉnh đạt được, bất kể thứ tự cung trong input.

Nếu **không có chu trình âm reachable từ s**, giá trị của các đỉnh đạt được sau n−1 lượt là shortest distance hữu hạn. Nếu có chu trình âm, các số trong dist ở một số đỉnh có thể tiếp tục giảm; **không được in ngay** mà phải kiểm tra ảnh hưởng chu trình âm.

### Không cộng với INF

Nếu dist[u] chưa có walk, phép tính INF+w là vô nghĩa. Trong code, trước khi cộng phải kiểm tra dist[u] tồn tại. Việc cộng Long.MAX_VALUE với số khác có thể tràn và tạo một đường giả.

## 6. Lượt quét thêm phát hiện seed của chu trình âm

Sau n−1 lượt relax, quét toàn bộ cung **thêm một lần**. Nếu u đạt được và:

**dist[u]+w(u,v) < dist[v]**,

thì có thể tiếp tục cải thiện tới v. Điều này cho thấy ảnh hưởng của một chu trình âm reachable. Đánh dấu v là **seed**.

~~~text
negative[*] = false
queue = empty

for moi cung (u,v,w):
    if dist[u] ton tai and dist[v] ton tai:
        if dist[u]+w < dist[v]:
            if not negative[v]:
                negative[v] = true
                queue.push_back(v)
~~~

Không bắt buộc cập nhật dist ở lượt này: con số tại các đỉnh ảnh hưởng không còn là minimum hữu hạn. Ta chỉ cần các seed để nhận diện **vùng NEG_INF**.

Tại sao không chỉ gắn nhãn các đỉnh trên một chu trình? Vì từ chu trình có thể đi tiếp qua nhiều cung đến các đỉnh khác. Các đỉnh hậu duệ cũng không có minimum hữu hạn.

## 7. BFS lan truyền ảnh hưởng chu trình âm

Từ mọi seed, BFS theo **đúng chiều cung đi ra**:

~~~text
while queue not empty:
    u = queue.pop_front()
    for v in outgoing[u]:
        if not negative[v]:
            negative[v] = true
            queue.push_back(v)
~~~

Nếu chi phí tới u giảm tùy ý, nối thêm một cung u→v với trọng số hữu hạn sẽ cho walk tới v giảm tùy ý. Vì vậy v cũng NEG_INF. Lập luận lan truyền được qua một chuỗi cung.

**Không lan ngược cung đi vào.** Nếu t→u và u thuộc chu trình âm, chưa chắc có cách đi từ chu trình tới t, nên không thể chỉ vì t dẫn tới u mà gắn NEG_INF cho t.

Sau propagation:

~~~text
if dist[v] chua ton tai:
    kind[v] = UNREACHABLE
else if negative[v]:
    kind[v] = NEG_INF
else:
    kind[v] = FINITE
    value[v] = dist[v]
~~~

Phân loại dựa trên hai thông tin: **có walk tới v hay không** và **có thể giảm chi phí tới v vô hạn hay không**.

## 8. Không nên dùng một con số sentinel cho ba ý nghĩa

Một vài cách cài vội:

- Dùng −1 cho UNREACHABLE: sai nếu minimum hữu hạn thật sự là −1.
- Dùng INF=10¹⁵: sai khi minimum hữu hạn lớn hơn 10¹⁵.
- Dùng Long.MIN_VALUE cho NEG_INF: có thể nhầm với một khoảng cách hữu hạn có trị số lớn, hoặc gặp overflow.
- Cộng vào Long.MAX_VALUE cho u chưa đạt được: có thể tạo số âm giả và làm thuật toán báo chu trình âm không tồn tại.

Giải pháp chắc chắn:

1. Giữ **cờ/trạng thái đạt được** riêng với giá trị số.
2. Chỉ cộng trọng số khi nguồn cung **đã đạt được**.
3. Chọn kiểu số đủ lớn hoặc chứng minh rõ cận tổng trọng số.
4. Giữ **Kind** riêng cho UNREACHABLE, FINITE và NEG_INF.
5. Chỉ trả giá trị số cho Kind.FINITE.

Trong ví dụ Java, dùng **BigInteger** cho chi phí, và dùng **null** để biểu thị chưa có walk. Nhờ vậy hai cung trọng số Long.MAX_VALUE rồi 1 sẽ tạo một khoảng cách hữu hạn vượt kiểu long mà không bị gắn INF.

## 9. Java 17+ chạy độc lập: phân loại ba trạng thái

Chương trình nhận đồ thị **có hướng**, đỉnh đánh số 1..n, cung có trọng số kiểu long. Nó dùng BigInteger cho tổng chi phí. Với graph rỗng n=0 không có nguồn hợp lệ cho bài toán single-source, nên chương trình yêu cầu n≥1.

~~~java
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Objects;

public class ShortestDistanceStatesDemo {

    enum Kind {
        UNREACHABLE, FINITE, NEGATIVE_INFINITY
    }

    record Edge(int from, int to, long weight) {}

    record Answer(Kind[] kinds, BigInteger[] finiteValues) {
        String describe(int vertex) {
            if (vertex < 1 || vertex > kinds.length) {
                throw new IllegalArgumentException("Invalid target");
            }
            int i = vertex - 1;
            return switch (kinds[i]) {
                case UNREACHABLE -> "UNREACHABLE";
                case NEGATIVE_INFINITY -> "NEG_INF";
                case FINITE -> finiteValues[i].toString();
            };
        }
    }

    static Answer classify(int n, int source, Edge[] edges) {
        if (n <= 0 || source < 1 || source > n) {
            throw new IllegalArgumentException(
                    "Require n>=1 and source in 1..n");
        }
        Objects.requireNonNull(edges, "edges");

        List<List<Integer>> outgoing = new ArrayList<>(n);
        for (int u = 0; u < n; u++) {
            outgoing.add(new ArrayList<>());
        }
        for (Edge e : edges) {
            Objects.requireNonNull(e, "edge");
            if (e.from() < 1 || e.from() > n
                    || e.to() < 1 || e.to() > n) {
                throw new IllegalArgumentException(
                        "Endpoint outside 1..n");
            }
            outgoing.get(e.from() - 1).add(e.to() - 1);
        }

        BigInteger[] dist = new BigInteger[n];
        dist[source - 1] = BigInteger.ZERO;

        // Up to n-1 rounds of relaxations.
        for (int pass = 1; pass < n; pass++) {
            boolean changed = false;
            for (Edge e : edges) {
                int u = e.from() - 1;
                int v = e.to() - 1;
                if (dist[u] == null) {
                    continue;
                }
                BigInteger cand = dist[u].add(
                        BigInteger.valueOf(e.weight()));
                if (dist[v] == null
                        || cand.compareTo(dist[v]) < 0) {
                    dist[v] = cand;
                    changed = true;
                }
            }
            if (!changed) {
                break;
            }
        }

        // Seeds: vertices whose distance can still improve.
        boolean[] negative = new boolean[n];
        Deque<Integer> queue = new ArrayDeque<>();
        for (Edge e : edges) {
            int u = e.from() - 1;
            int v = e.to() - 1;
            if (dist[u] == null || dist[v] == null) {
                continue;
            }
            BigInteger cand = dist[u].add(
                    BigInteger.valueOf(e.weight()));
            if (cand.compareTo(dist[v]) < 0 && !negative[v]) {
                negative[v] = true;
                queue.addLast(v);
            }
        }

        // Descendants of negative-cycle influence are NEG_INF.
        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (int v : outgoing.get(u)) {
                if (!negative[v]) {
                    negative[v] = true;
                    queue.addLast(v);
                }
            }
        }

        Kind[] kind = new Kind[n];
        BigInteger[] value = new BigInteger[n];
        for (int v = 0; v < n; v++) {
            if (dist[v] == null) {
                kind[v] = Kind.UNREACHABLE;
            } else if (negative[v]) {
                kind[v] = Kind.NEGATIVE_INFINITY;
            } else {
                kind[v] = Kind.FINITE;
                value[v] = dist[v];
            }
        }
        return new Answer(kind, value);
    }

    static void show(String title, int n, int source,
                     Edge... edges) {
        Answer ans = classify(n, source, edges);
        StringBuilder text = new StringBuilder(title + ": ");
        for (int vertex = 1; vertex <= n; vertex++) {
            if (vertex > 1) {
                text.append("; ");
            }
            text.append("v").append(vertex).append("=")
                    .append(ans.describe(vertex));
        }
        System.out.println(text);
    }

    public static void main(String[] args) {
        show("Finite and unreachable", 5, 1,
                new Edge(1, 2, 3),
                new Edge(2, 3, -1),
                new Edge(1, 4, 7));

        show("Reachable negative cycle", 7, 1,
                new Edge(1, 2, 2),
                new Edge(2, 3, 1),
                new Edge(3, 2, -4),
                new Edge(3, 4, 3),
                new Edge(1, 5, 10),
                new Edge(5, 6, -2),
                new Edge(6, 7, 1));

        show("Unreachable negative cycle", 5, 1,
                new Edge(1, 2, 4),
                new Edge(2, 3, 6),
                new Edge(4, 5, -3),
                new Edge(5, 4, 1));

        show("Negative edges but finite", 4, 1,
                new Edge(1, 2, 8),
                new Edge(1, 3, 5),
                new Edge(3, 2, -9),
                new Edge(2, 4, 2),
                new Edge(3, 4, 20));

        show("Zero cycle", 3, 1,
                new Edge(1, 2, 0),
                new Edge(2, 1, 0),
                new Edge(2, 3, -2));

        show("Source affected", 2, 1,
                new Edge(1, 2, 0),
                new Edge(2, 1, -1));

        show("Single vertex", 1, 1);

        show("Negative self loop", 1, 1,
                new Edge(1, 1, -2));

        show("No edges", 3, 1);

        show("Beyond long range", 3, 1,
                new Edge(1, 2, Long.MAX_VALUE),
                new Edge(2, 3, 1));
    }
}
~~~

Lưu tên tệp **ShortestDistanceStatesDemo.java**, biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 ShortestDistanceStatesDemo.java
java ShortestDistanceStatesDemo
~~~

Đầu ra:

~~~text
Finite and unreachable: v1=0; v2=3; v3=2; v4=7; v5=UNREACHABLE
Reachable negative cycle: v1=0; v2=NEG_INF; v3=NEG_INF; v4=NEG_INF; v5=10; v6=8; v7=9
Unreachable negative cycle: v1=0; v2=4; v3=10; v4=UNREACHABLE; v5=UNREACHABLE
Negative edges but finite: v1=0; v2=-4; v3=5; v4=-2
Zero cycle: v1=0; v2=0; v3=-2
Source affected: v1=NEG_INF; v2=NEG_INF
Single vertex: v1=0
Negative self loop: v1=NEG_INF
No edges: v1=0; v2=UNREACHABLE; v3=UNREACHABLE
Beyond long range: v1=0; v2=9223372036854775807; v3=9223372036854775808
~~~

### Giải thích code

- **dist[v]==null** biểu diễn không có walk được khám phá. Sau n−1 lượt, nó cũng chính là UNREACHABLE.
- **BigInteger** tránh overflow khi tổng trọng số vượt miền long.
- **Lượt quét bổ sung** lấy các đỉnh còn có thể giảm làm seed; không dùng số tạm của những đỉnh này làm kết quả.
- **BFS theo outgoing** lan truyền ảnh hưởng tới tất cả đỉnh có thể đến từ vùng có chu trình âm.
- **Kind.FINITE** mới kèm giá trị số. UNREACHABLE và NEGATIVE_INFINITY không có một khoảng cách hữu hạn để in.

### Độ phức tạp

Tối đa n−1 lượt duyệt m cung: O(nm) phép relax. Quét seed O(m), lan truyền O(n+m), tổng **O(nm+n+m)** phép toán số học, dùng **O(n+m)** bộ nhớ. Với BigInteger, mỗi phép cộng/so sánh có thêm chi phí phụ thuộc số bit.

## 10. Chứng minh kết quả phân loại là đúng

**UNREACHABLE:** Nếu một đỉnh nhận dist khác null, nó phải được lan từ dist[source]=0 theo một chuỗi cung thật nên chắc chắn đạt được. Nếu một đỉnh đạt được, tồn tại một đường đi đơn dài tối đa n−1 cung; sau đủ lượt relax nó sẽ nhận dist. Vậy dist null khi và chỉ khi không có walk từ s.

**NEG_INF:** Một cung còn relaxable sau n−1 lượt cho thấy có ảnh hưởng của chu trình âm đạt được. Mọi seed có thể nhận chi phí giảm tùy ý; mọi hậu duệ của seed theo cung đi ra cũng vậy. Chiều ngược, nếu đỉnh t có infimum −∞, phải tồn tại một chu trình âm đạt được từ s và dẫn đến t. Những cải thiện còn lại ở lượt n nằm trong hoặc sau vùng ảnh hưởng ấy, và BFS lan truyền tới t.

**FINITE:** Nếu t đạt được nhưng không chịu ảnh hưởng chu trình âm, bỏ các vòng không âm ra khỏi một walk không làm chi phí tăng. Có một simple path tối ưu dài không quá n−1 cung; Bellman–Ford đã xử lý đủ số cạnh ấy và trả giá trị nhỏ nhất đúng.

Bởi vậy cả ba trạng thái đều được phân loại chính xác theo định nghĩa shortest walk.

## 11. So sánh với BFS, Dijkstra, DAG và Floyd–Warshall

| Loại dữ liệu | Thuật toán phù hợp | NEG_INF có thể xuất hiện? |
| --- | --- | --- |
| Đồ thị không trọng số, mỗi cạnh tính 1 | BFS | Không |
| Trọng số không âm | Dijkstra | Không |
| DAG có cả trọng số âm | Relax theo thứ tự topo | Không |
| Có cạnh âm và có thể có chu trình âm | Bellman–Ford + propagation | Có |
| Cần mọi cặp, n tương đối nhỏ | Floyd–Warshall + kiểm tra chu trình âm | Có |

**BFS:** nếu không đạt được thì unreachable, nếu đạt được thì khoảng cách số cạnh hữu hạn. Không có chu trình âm vì mỗi cạnh tính +1.

**Dijkstra:** dùng cho trọng số không âm trong cách chứng minh chuẩn. Có trọng số âm thì Dijkstra chuẩn không còn bảo đảm đúng, kể cả nếu graph không có chu trình âm.

**DAG:** không có chu trình để lặp, nên dù có cung âm, mọi đỉnh đạt được vẫn có shortest distance hữu hạn. Relax theo thứ tự tô-pô chạy O(n+m).

**Floyd–Warshall:** sau khi tính bảng d[i][j], một cặp (s,t) bị NEG_INF nếu tồn tại k thỏa đồng thời s tới k, **d[k][k]<0**, và k tới t. Một negative cycle tồn tại đâu đó trong graph **không** đủ để đánh dấu mọi cặp.

## 12. Trường hợp nguồn cũng là đích

Với s=t, luôn có walk rỗng chi phí 0. Nhưng chưa chắc d(s,s)=0.

Ví dụ:

~~~text
1 -> 2 (0)
2 -> 1 (-1)
~~~

Có thể lặp vòng 1→2→1 nhiều lần, làm chi phí s→s bằng −1,−2,−3,... nên d(1,1)=NEG_INF.

Ngược lại, nếu nguồn 1 chỉ đi tới chu trình âm 2↔3 nhưng từ đó **không có cung quay lại 1**, d(1,1)=FINITE(0), mặc dù d(1,2) và d(1,3) có thể NEG_INF.

**Điều kiện để nguồn cũng NEG_INF:** có chu trình âm s đi tới được **và chu trình đó có đường quay về s**.

## 13. Đồ thị vô hướng và cạnh âm

Nếu một cạnh vô hướng {u,v} có trọng số w<0 và shortest walk cho phép sử dụng lại cạnh, ta có thể đi **u→v→u** với tổng 2w<0, rồi lặp. Khi biểu diễn cạnh vô hướng bằng hai cung ngược nhau, nó tạo một closed directed walk âm hai bước.

Trong đồ thị vô hướng đơn, đi đi-về trên cùng cạnh không nhất thiết được gọi là một **chu trình đơn**; cách diễn đạt chính xác là một **hành trình khép kín trọng số âm**. Nó vẫn đủ tạo −∞ khi phép lặp cạnh được phép.

Nếu bài chỉ cho phép simple path hoặc cấm lặp cạnh, thao tác này không hợp lệ. Cần xét quy tắc đường đi của đề.

Đỉnh thuộc thành phần không đạt được từ nguồn vẫn UNREACHABLE, dù thành phần ấy có cạnh âm.

## 14. Kiểm thử bằng oracle độc lập

Với graph nhỏ n≤8 và trọng số nhỏ, có thể viết tham chiếu **Floyd–Warshall**:

1. Khởi tạo d[i][i]=0 và d[i][j]=trọng số nhỏ nhất của các cung i→j; cặp không có cung mang +INF.
2. Cho từng đỉnh trung gian k, cập nhật d[i][j]=min(d[i][j],d[i][k]+d[k][j]) khi các giá trị trung gian hữu hạn.
3. Với nguồn s, đích t:
   - Nếu d[s][t] là +INF → UNREACHABLE.
   - Nếu tồn tại k mà s tới k, d[k][k]<0, và k tới t → NEG_INF.
   - Các trường hợp còn lại → FINITE(d[s][t]).

So sánh toàn bộ nhãn trạng thái và giá trị hữu hạn của Bellman–Ford với oracle cho nhiều graph ngẫu nhiên có:

- Cạnh âm nhưng không chu trình.
- Negative self-loop, chu trình âm 2 hoặc nhiều đỉnh.
- Chu trình 0 và dương.
- Chu trình âm ở vùng không đạt được.
- Chu trình âm đạt được nhưng không thể dẫn tới mọi đỉnh.
- Nhiều cung song song cùng cặp đầu mút.
- Graph không có cung, chỉ một đỉnh và nguồn cũng là đích.

**Kiểm thử không thay thế chứng minh** về khả năng tiếp tục relax và lan truyền đúng chiều. Một lỗi gắn NEG_INF sai chỉ xuất hiện ở cấu trúc đồ thị đặc biệt có thể vượt qua nhiều bài thử ngẫu nhiên nếu không thiết kế ca biên.

## 15. Những lỗi thường gặp

1. **Gộp không có đường đi với có đường nhưng chi phí giảm vô hạn.**
2. **Dùng −1 làm unreachable** trong graph có khoảng cách âm hợp lệ.
3. **In dist sau n−1 lượt** mà không phát hiện và lan truyền chu trình âm.
4. **Có chu trình âm ở đâu cũng báo mọi đỉnh NEG_INF**, bất kể nguồn.
5. **Nguồn tới được chu trình âm rồi báo mọi đỉnh reachable NEG_INF**, dù có nhánh không tới được từ chu trình.
6. **Lan truyền âm ngược cung**, khiến các đỉnh trước chu trình cũng bị gắn sai.
7. **Chỉ gắn nhãn những đỉnh trên chu trình**, quên các đỉnh hậu duệ.
8. **Chỉ gắn các seed relaxable**, không BFS/DFS đi tiếp.
9. **Không kiểm tra dist[u] tồn tại** trước phép cộng.
10. **Chọn INF nhỏ hơn khoảng cách hợp lệ**, tạo kết luận UNREACHABLE giả.
11. **Overflow long**, tạo một phép cải thiện giả giống negative cycle.
12. **Cho rằng trọng số âm tức NEG_INF**, dù không có chu trình.
13. **Cho rằng chu trình 0 là chu trình âm.**
14. **Nhầm có vô hạn walk với không có minimum hữu hạn.**
15. **Không phân biệt shortest walk với simple path**, lặp chu trình trái đề.
16. **Cho rằng d(s,s) luôn bằng 0**, bỏ qua chu trình âm quay lại nguồn.
17. **Dùng Dijkstra tùy ý khi có trọng số âm**.
18. **Dùng kết quả một nguồn để trả cho một nguồn khác**.
19. **Đọc giá trị tạm của đỉnh NEG_INF như đáp án hữu hạn**.
20. **Đánh dấu mọi cặp là NEG_INF trong Floyd–Warshall chỉ vì d[k][k]<0 ở đâu đó**.
21. **Không kiểm thử nhiều cung song song và self-loop âm**.
22. **Coi −∞ là tổng của một walk hữu hạn**, thay vì infimum không đạt được.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Không có walk từ s tới t, d(s,t) được ký hiệu ra sao?  
**Đáp án:** UNREACHABLE, ký hiệu +∞ theo quy ước.

**Câu 2.** Có walk từ s tới t, nhưng chu trình âm đạt được từ s dẫn tới t. Trạng thái?  
**Đáp án:** NEG_INF, vì có thể lặp chu trình để giảm chi phí không giới hạn.

**Câu 3.** Có cạnh âm nhưng graph là DAG. Có thể có NEG_INF không?  
**Đáp án:** Không. DAG không có chu trình nên các đỉnh đạt được có minimum hữu hạn.

**Câu 4.** Chu trình âm ở thành phần không đạt được từ s ảnh hưởng thế nào?  
**Đáp án:** Không; các đỉnh ở thành phần ấy là UNREACHABLE từ s.

**Câu 5.** Chu trình âm đạt được từ s nhưng không có đường đến t, t có tự thành NEG_INF không?  
**Đáp án:** Không. Nếu t đạt được qua nhánh khác, t vẫn có thể FINITE.

**Câu 6.** Vì sao Bellman–Ford quét thêm sau n−1 lượt?  
**Đáp án:** Để tìm cung còn relaxable, làm seed của các đỉnh chịu ảnh hưởng chu trình âm.

**Câu 7.** Từ seed, lan truyền theo hướng nào?  
**Đáp án:** Theo cung đi ra, vì chỉ những đỉnh đi được từ vùng âm mới nhận ảnh hưởng.

**Câu 8.** Một chu trình trọng số 0 có làm d(s,t)=−∞ không?  
**Đáp án:** Không, lặp chu trình 0 không giảm chi phí.

**Câu 9.** Với s=t, d(s,s) có luôn bằng 0 không?  
**Đáp án:** Không; nếu có thể lặp chu trình âm rồi quay về s, d(s,s)=−∞.

**Câu 10.** Cần điều kiện gì để gắn NEG_INF cho cặp (s,t) sau Floyd–Warshall?  
**Đáp án:** Có k mà s tới k, d[k][k]<0 và k tới t.

**Câu 11.** Vì sao dùng BigInteger trong demo?  
**Đáp án:** Để không nhầm khoảng cách hữu hạn rất lớn với INF hoặc gây overflow.

**Câu 12.** Nếu shortest path bắt buộc không lặp đỉnh, có được lặp chu trình âm không?  
**Đáp án:** Không. Phải tuân theo mô hình simple path.

## 17. Tổng kết

Ba trạng thái shortest paths cần giữ độc lập:

- **UNREACHABLE:** không có walk; d=+∞.
- **FINITE(d):** có walk và một minimum hữu hạn.
- **NEG_INF:** có walk nhưng không có minimum hữu hạn; d=−∞ do ảnh hưởng chu trình âm.

Với graph có trọng số âm, **Bellman–Ford + lan truyền** là phương pháp chuẩn:

1. Khởi tạo nguồn bằng 0, đỉnh khác chưa đạt được; không cộng với sentinel INF.
2. Relax tối đa n−1 lượt.
3. Tìm các cung còn giảm ở lượt tiếp theo để lấy seed.
4. BFS/DFS lan theo **chiều cung đi ra**.
5. UNREACHABLE nếu chưa có walk; NEG_INF nếu bị đánh dấu; FINITE nếu còn lại.
6. Không nhầm một giá trị âm lớn với vô hạn âm, hoặc một giá trị lớn với unreachable.

**Câu hỏi cần tự đặt ra:** “Không có khoảng cách hữu hạn là vì **không có hành trình nào**, hay vì **có hành trình nhưng có thể làm chi phí giảm mãi**?” Trả lời được điều này mới chọn đúng thuật toán và định dạng kết quả.
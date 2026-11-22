# Dijkstra với hàng đợi ưu tiên và bản ghi đã lỗi thời

## 1. Dijkstra giải bài toán gì?

Cho đồ thị \(G=(V,E)\) với đỉnh xuất phát s và trọng số cạnh **không âm**. Bài toán **đường đi ngắn nhất một nguồn** yêu cầu tìm tổng trọng số nhỏ nhất của đường đi từ s tới từng đỉnh v. Gọi \(\delta(s,v)\) là độ dài tối ưu, hoặc \(+\infty\) nếu không có đường đi; kết quả:

\[
dist[v]=\delta(s,v).
\]

Khác **BFS không trọng số**, Dijkstra không ưu tiên ít cạnh nhất, mà ưu tiên **tổng trọng số hiện biết nhỏ nhất**. Một đường gồm nhiều cạnh rẻ có thể tốt hơn một cạnh đắt. Để chọn ứng viên có khoảng cách nhỏ nhất, ta dùng **min-priority queue** (min-heap).

Trong **Java 17**, PriorityQueue cung cấp offer và poll theo thứ tự của comparator, nhưng **không có thao tác decrease-key** trực tiếp để giảm khóa của một phần tử đã nằm trong heap. Vì vậy cài đặt quen thuộc dùng **bản ghi lười (lazy duplicate entries)**:

1. Khi tìm được đường đi tới v tốt hơn trước, cập nhật dist[v].
2. Thêm **một bản ghi mới (v, dist[v])** vào PriorityQueue, không sửa bản ghi cũ.
3. Khi lấy (u, d) ra, nếu d **khác dist[u] hiện tại**, đây là **bản ghi đã lỗi thời (stale/outdated)**: bỏ qua ngay.
4. Chỉ khi d==dist[u], duyệt các cạnh kề u để thử cải thiện khoảng cách những đỉnh khác.

Điểm quan trọng nhất của bài này: **một đỉnh có thể xuất hiện nhiều lần trong heap**, nhưng khoảng cách chính thức đang tốt nhất của nó chỉ nằm trong mảng dist. Heap lưu các ảnh chụp **tại thời điểm offer**, không tự đồng bộ bản ghi cũ khi dist thay đổi.

## 2. Hợp đồng đầu vào và kết quả

Bài sử dụng:
- Đồ thị **có hướng** với đỉnh 0..n−1, nguồn s thuộc miền đó.
- Trọng số nguyên không âm, **cho phép bằng 0**, cạnh song song và self-loop.
- Không yêu cầu đồ thị liên thông. Đỉnh không thể tới được giữ khoảng cách **INF**.
- Java dùng long cho khoảng cách và trọng số. **Long.MAX_VALUE** được dành làm INF, không phải một khoảng cách hữu hạn.
- Chương trình yêu cầu mọi phép cộng khoảng cách thực hiện được không tràn long và tạo kết quả nhỏ hơn Long.MAX_VALUE; khi vi phạm sẽ **báo lỗi số học**, không âm thầm trả sai.
- Nếu cần đồ thị vô hướng, phải thêm **hai cung ngược chiều** cho mỗi cạnh vô hướng.

Ba dữ liệu lưu:
- **distance[v]**: khoảng cách tạm thời tốt nhất đã biết từ s tới v.
- **parent[v]**: đỉnh ngay trước v trên một đường đi hiện biết tốt nhất, phục vụ truy vết.
- **PriorityQueue<State>**: nhiều bản ghi bất biến State(vertex,distance), có thể gồm cả bản ghi cũ.

**Không nhầm với visited của BFS.** Đỉnh được phát hiện lần đầu **chưa chắc** đã có khoảng cách tối ưu. Chỉ khi bản ghi hiện hành được poll nhỏ nhất từ heap, Dijkstra mới chứng minh khoảng cách của nó tối ưu nhờ điều kiện trọng số không âm.

Nếu bài chỉ cần **một đường ngắn nhất**, parent giữ một kết quả khi có hòa. Nếu cần **mọi đường ngắn nhất** hoặc đường có tiêu chí phụ như ít cạnh nhất, quy tắc lưu parent phải được mở rộng.

## 3. Thao tác relax: nguồn tạo ra bản ghi mới

Giả sử đang xử lý đỉnh u ở khoảng cách d và có cạnh u→v trọng số w≥0. Khi đó:

\[
candidate=d+w.
\]

Nếu candidate<dist[v], đường mới cải thiện khoảng cách tới v, ta thực hiện:

\[
dist[v]\gets candidate,\qquad parent[v]\gets u.
\]

Với Java PriorityQueue, **đừng quên offer bản ghi mới**:

~~~java
long candidate = Math.addExact(currentDistance, edge.weight());
if (candidate < distance[v]) {
    distance[v] = candidate;
    parent[v] = u;
    pq.offer(new State(v, candidate));
}
~~~

Dấu **< nghiêm ngặt** rất quan trọng. Nếu candidate==dist[v], ta đã có đường cùng chi phí, không cần offer thêm. Nếu dùng <=, một **chu trình cạnh 0** có thể tạo vô hạn bản ghi bằng nhau, và parent có thể bị đổi đi đổi lại hoặc tạo chu trình.

**Đánh dấu visited ngay khi offer** rồi từ chối mọi lần cập nhật v sau đó là lỗi: Dijkstra cần cho phép nhiều lần cải thiện trước khi khoảng cách được chốt.

## 4. Cách bản ghi stale xuất hiện

Xét đồ thị có hướng:

~~~text
0 -> 1 (10)
0 -> 2 (1)
2 -> 1 (1)
~~~

Nguồn s=0. Ban đầu distance[0]=0, các đỉnh khác là INF. Sau khi xử lý 0:
- Cạnh 0→1 cho candidate=10, nên distance[1]=10; offer (1,10).
- Cạnh 0→2 cho candidate=1, nên distance[2]=1; offer (2,1).

Heap lấy (2,1) trước (1,10). Từ 2 tới 1 trọng số 1, candidate=2<10. Ta **giảm distance[1] xuống 2** và offer **(1,2)**.

Lúc này heap vẫn có cả:

~~~text
(1,2)    : bản ghi hiện hành
(1,10)   : bản ghi cũ, nay đã lỗi thời
~~~

Java PriorityQueue không tự sửa (1,10) thành (1,2). Bản ghi (1,2) được lấy ra trước và xử lý. Khi sau đó (1,10) được lấy ra, kiểm tra:

~~~java
State top = pq.poll();
int u = top.vertex();
if (top.distance() != distance[u]) {
    continue;    // Stale: không xét cạnh kề từ u.
}
~~~

Vì 10!=distance[1]=2, bỏ qua bản ghi cũ. Đây là **lazy deletion**: không cần tìm/xóa bản ghi từ heap tại lúc cải thiện; cứ để nó tồn tại, tới lượt poll mới loại.

**Vì sao không sửa khóa trực tiếp?** PriorityQueue không tự tái cấu trúc heap khi field của phần tử hoặc giá trị được comparator tham chiếu thay đổi. Không nên lưu chỉ ID đỉnh rồi để comparator phụ thuộc trực tiếp vào một mảng distance[] **mutable**. Hãy dùng State **bất biến** với khóa cố định và offer bản ghi mới.

Trong biến thể có cập nhật nghiêm ngặt, mọi bản ghi stale đều có poppedDistance>distance[u] hiện hành. Vì vậy có thể kiểm tra bằng > thay vì !=; cách != trực tiếp thể hiện sự không khớp và là mẫu được dùng trong bài.

## 5. Giả mã đầy đủ

~~~text
for each vertex v:
    dist[v] = INF
    parent[v] = -1

dist[source] = 0
pq = min-heap ordered by (distance, vertexId)
pq.offer((source, 0))

while pq not empty:
    (u, poppedDistance) = pq.poll()

    if poppedDistance != dist[u]:
        continue    // Bỏ bản ghi lỗi thời, không relax.

    for each edge u -> v of weight w:
        candidate = poppedDistance + w
        if candidate < dist[v]:
            dist[v] = candidate
            parent[v] = u
            pq.offer((v, candidate))

return dist, parent
~~~

Các bất biến cần giữ:
- Khi offer(v,d), d là độ dài **một đường đi thật** từ nguồn tới v.
- distance[v] là giá trị tốt nhất đã tìm thấy, chỉ **giảm**, không tăng.
- Mọi lần relax thành công phải **offer** bản ghi mới.
- Mọi lần poll phải **kiểm tra stale trước khi duyệt kề**.
- Không có vertex nào được đánh dấu “đã chốt” **chỉ vì vừa enqueue**.
- Với trọng số không âm, mỗi đỉnh tới được chỉ có **một lượt poll hợp lệ** trong quá trình chạy hết; các bản ghi cùng đỉnh khác, nếu có, là stale.

Không dùng queue FIFO nếu cạnh có trọng số thay đổi; thứ tự FIFO chỉ đúng cho **số cạnh ít nhất** hoặc chi phí cạnh đồng nhất.

## 6. Ví dụ có nhiều bản ghi stale: đồ thị tám đỉnh

Dùng đồ thị có hướng với các đỉnh 0..7, nguồn 0. Có 14 cung theo thứ tự sau:

| Cung | Trọng số | Vai trò |
|---|---:|---|
| 0→1 | 10 | Tạo bản ghi ban đầu (1,10) |
| 0→2 | 1 | Đường rẻ tới 2 |
| 0→3 | 20 | Tạo bản ghi ban đầu (3,20) |
| 2→1 | 1 | Giảm 1 từ 10 xuống 2 |
| 2→3 | 8 | Tạm giảm 3 từ 20 xuống 9 |
| 2→5 | 15 | Tạm có 5 ở 16 |
| 1→3 | 2 | Giảm 3 từ 9 xuống 4 |
| 1→4 | 10 | Tạm có 4 ở 12 |
| 3→4 | 3 | Giảm 4 xuống 7 |
| 3→5 | 12 | Đường hòa tới 5 ở 16, không cải thiện |
| 4→5 | 2 | Giảm 5 xuống 9 |
| 4→6 | 9 | Tạm có 6 ở 16 |
| 5→6 | 1 | Giảm 6 xuống 10 |
| 4→3 | 0 | Cạnh trọng số 0, không tạo cải thiện |

Đỉnh 7 không có đường đi từ 0. Những phép cải thiện quan trọng:

~~~text
dist[1]: INF -> 10 -> 2
dist[3]: INF -> 20 -> 9 -> 4
dist[4]: INF -> 12 -> 7
dist[5]: INF -> 16 -> 9
dist[6]: INF -> 16 -> 10
~~~

### 6.1. Thứ tự lấy bản ghi khỏi heap

Min-heap sắp theo **(distance tăng, vertexId tăng khi hòa)** như Java mẫu.

| Lượt poll | Bản ghi | Khoảng cách hiện hành | Kết luận |
|---:|---|---:|---|
| 1 | (0,0) | 0 | Hợp lệ, tạo ba ứng viên |
| 2 | (2,1) | 1 | Hợp lệ, cải thiện 1, 3 và phát hiện 5 |
| 3 | (1,2) | 2 | Hợp lệ, cải thiện 3, phát hiện 4 |
| 4 | (3,4) | 4 | Hợp lệ, cải thiện 4 |
| 5 | (4,7) | 7 | Hợp lệ, cải thiện 5, phát hiện 6 |
| 6 | (3,9) | **4** | **Stale** |
| 7 | (5,9) | 9 | Hợp lệ, cải thiện 6 |
| 8 | (1,10) | **2** | **Stale** |
| 9 | (6,10) | 10 | Hợp lệ |
| 10 | (4,12) | **7** | **Stale** |
| 11 | (5,16) | **9** | **Stale** |
| 12 | (6,16) | **10** | **Stale** |
| 13 | (3,20) | **4** | **Stale** |

Sáu bản ghi lỗi thời:

~~~text
(3@9->4), (1@10->2), (4@12->7),
(5@16->9), (6@16->10), (3@20->4)
~~~

Ký hiệu (v@old→new) nghĩa là heap chứa khoảng cách old của v nhưng distance[v] đã trở thành new.

### 6.2. Đáp án ngắn nhất

~~~text
distance = [0, 2, 1, 4, 7, 9, 10, INF]
parent   = [-1, 2, 0, 1, 3, 4, 5, -1]

Đường đi tới 6:
0 -> 2 -> 1 -> 3 -> 4 -> 5 -> 6
Chi phí: 1 + 1 + 2 + 3 + 2 + 1 = 10

Đường đi tới 7: không tồn tại.
~~~

Trong phiên bản mã này:
- **13 offers**: một bản ghi nguồn + 12 lần relax thành công.
- **13 polls**: chạy cho tới khi heap rỗng, nên số poll bằng số offer.
- **6 stale pops**: sáu bản ghi cũ.
- **7 lượt pop hợp lệ**: 7 đỉnh tới được là 0..6.

**Đếm đúng bản chất:** số bản ghi lỗi thời **không phải** số đỉnh không tới được; đỉnh 3 có tới **hai** bản ghi stale, còn đỉnh 7 không được offer lần nào.

## 7. Chứng minh tính đúng khi trọng số không âm

### 7.1. Khoảng cách tạm thời luôn có chứng cứ là một đường đi

Nguồn có distance[s]=0 qua đường rỗng. Mỗi cải thiện distance[v] lấy từ distance[u] cộng trọng số cạnh u→v, vì vậy nó tương ứng với một đường đi từ s tới v đã khám phá được.

Do đó mọi distance[v] hữu hạn **không nhỏ hơn** khoảng cách tối ưu thật:

\[
distance[v]\ge \delta(s,v).
\]

Các giá trị có thể giảm khi tìm đường tốt hơn, nhưng không “bịa” ra đường đi ngắn hơn mọi đường tồn tại.

### 7.2. Khi pop hợp lệ nhỏ nhất, khoảng cách đã tối ưu

Giả sử vừa pop đỉnh u với bản ghi khớp distance[u], nhỏ nhất trong các bản ghi đang chờ, nhưng lại tồn tại đường đi thực từ s tới u có chi phí nhỏ hơn.

Xét trên đường ngắn hơn ấy **đỉnh đầu tiên chưa được chốt** tại thời điểm đang xét; gọi nó là y, còn x là đỉnh trước y đã chốt. Khi x được xử lý, cạnh x→y đã được relax. Do trọng số không âm, giá trị ứng viên của y không thể lớn hơn độ dài tiền tố của đường giả sử ngắn hơn. Suy ra phải có một bản ghi hiện hành của y với khoảng cách **nhỏ hơn** distance[u], lẽ ra được poll trước u. Mâu thuẫn với tính chất min-heap.

Vậy khi một đỉnh được pop hợp lệ:

\[
distance[u]=\delta(s,u).
\]

Với cạnh trọng số **0**, một số đỉnh có khoảng cách bằng nhau và thứ tự pop khi hòa có thể khác, nhưng không có đường qua các đỉnh chưa xử lý nào tạo **khoảng cách nhỏ hơn** một đỉnh đã chốt.

### 7.3. Bỏ qua stale là an toàn

Khi một bản ghi (u,old) stale, mảng distance[u] đã được cải thiện xuống giá trị **nhỏ hơn old**, và bản ghi mới đã được offer.

Relax mọi cạnh từ giá trị tốt hơn có thể cho ứng viên **không lớn hơn** những ứng viên tính từ old, bởi trọng số cạnh không âm. Bản ghi mới được xử lý trước bản ghi cũ hoặc đã xử lý xong. Vì vậy bỏ bản ghi old không làm mất cơ hội tìm một đường ngắn hơn.

Từ đó, sau khi heap rỗng, mọi đỉnh tới được đã được xử lý ở khoảng cách tối ưu; những đỉnh không thể tới được giữ INF. Thuật toán cho đúng toàn bộ mảng đường đi ngắn nhất.

**Giới hạn chứng minh:** các cạnh phải **không âm**. Nếu cho phép âm, một đỉnh đã poll có thể về sau được cải thiện qua đường đi chứa cạnh âm. Đó không còn là Dijkstra có bảo đảm chốt và độ phức tạp đã nêu.

## 8. Vì sao visited khi enqueue sai?

Vẫn dùng đồ thị:

~~~text
0 -> 1 (10), 0 -> 2 (1), 2 -> 1 (1)
~~~

Nếu khi xét cạnh 0→1 ta đặt visited[1]=true rồi không cho cập nhật 1 nữa, kết quả trả distance[1]=10, trong khi đường 0→2→1 có chi phí **2**.

Điều này trái với BFS không trọng số: ở BFS, lần phát hiện đầu đã đạt số bước ngắn nhất vì tất cả cung có chi phí như nhau; ở Dijkstra, lần phát hiện đầu có thể đến từ cung trọng số lớn.

Có thể dùng boolean **settled[u]** riêng, nhưng chỉ được đặt settled[u]=true **sau khi pop hợp lệ**, không phải khi offer. Trong ví dụ đang học, stale-check đủ và không bắt buộc có settled.

**Chú ý:** nếu không có stale-check nhưng luôn relax dựa trên distance[u] mới nhất, một số biến thể có thể vẫn trả khoảng cách đúng nhưng quét lại nhiều cạnh vô ích; đó không phải lý do để bỏ kiểm tra stale. Nếu vừa dùng khoảng cách cũ của bản ghi để mở rộng, lại có logic chốt/đích dừng sai, hậu quả có thể nghiêm trọng hơn hiệu năng.

## 9. Hòa khoảng cách, cạnh 0 và parent

Cạnh trọng số 0 hoàn toàn hợp lệ với Dijkstra. Khi hai đường cùng tổng trọng số, chương trình giữ **parent đầu tiên** dẫn tới giá trị tối ưu đang biết vì chỉ relax lúc candidate<distance[v].

Ví dụ đồ thị thứ hai, nguồn 0:

~~~text
0 -> 2 (1)
0 -> 1 (1)
2 -> 3 (3)
1 -> 3 (3)
0 -> 3 (7)
3 -> 4 (0)
~~~

Kết quả:

~~~text
distance = [0, 1, 1, 4, 4]
parent   = [-1, 0, 0, 1, 3]
pathTo(4) = [0, 1, 3, 4]
~~~

Cả 0→1→3 và 0→2→3 có chi phí 4. Comparator của Java ưu tiên **ID đỉnh nhỏ hơn** khi khoảng cách bằng nhau, nên (1,1) được poll trước (2,1) dù cạnh 0→2 được nhập trước. Vì vậy parent[3]=1; khi đường qua 2 cũng có candidate=4, dấu < không cập nhật.

Cạnh 3→4 trọng số 0 giữ distance[4]=4. Bản ghi (3,7) ban đầu bị bỏ thành stale sau khi distance[3] giảm xuống 4.

**Không suy ra parent là đường ít cạnh nhất hoặc nhỏ nhất theo từ điển toàn chuỗi.** Comparator chỉ quyết định cách xử lý những bản ghi có cùng khoảng cách; khi bài có thêm tiêu chí phụ, cần thiết kế mô hình so sánh toàn bộ tiêu chí và chứng minh.

Nếu thay < bằng <= ở phép relax, **chu trình 0** có thể phát sinh offer liên tục dù giá trị không đổi, và việc sửa parent khi hòa có thể gây vòng lặp khi truy vết.

## 10. Java 17+ hoàn chỉnh: lazy heap và nhật ký stale

Chương trình độc lập dưới đây:
- Nhận cạnh có hướng theo hàng {from,to,weight} trong long[][].
- Từ chối ID ngoài miền, trọng số âm hoặc đồ thị không có nguồn hợp lệ.
- Dùng **record State bất biến** và PriorityQueue ưu tiên distance tăng, rồi vertex tăng.
- Dùng **Math.addExact** và sentinel INF riêng để tránh số học tràn âm.
- Relax khi tốt hơn, ghi parent, offer bản ghi mới.
- **Bỏ stale trước khi duyệt graph.get(u)** và đếm số lượng.
- In đường đi, mảng khoảng cách, thống kê và nhật ký bản ghi stale.
- Kiểm tra cạnh 0, hòa, đỉnh không thể tới, đồ thị không cạnh và đầu vào không hợp lệ.

Lưu thành **DijkstraStaleRecordsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.StringJoiner;

public final class DijkstraStaleRecordsDemo {
    private DijkstraStaleRecordsDemo() {
    }

    private static final long INF = Long.MAX_VALUE;

    private record Edge(int to, long weight) {
    }

    private record State(int vertex, long distance) {
    }

    public record Result(
            long[] distance, int[] parent,
            long offers, long polls, long stalePops,
            long improvements, List<String> staleLog) {
    }

    public static Result shortestPaths(
            int vertexCount, long[][] edges, int source) {
        if (vertexCount <= 0 || edges == null
                || source < 0 || source >= vertexCount) {
            throw new IllegalArgumentException(
                    "Need a nonempty graph and a valid source");
        }

        List<List<Edge>> graph = new ArrayList<>();
        for (int v = 0; v < vertexCount; v++) {
            graph.add(new ArrayList<>());
        }

        for (long[] row : edges) {
            if (row == null || row.length != 3) {
                throw new IllegalArgumentException(
                        "Each edge needs from, to, weight");
            }

            long from = row[0];
            long to = row[1];
            long weight = row[2];

            if (from < 0 || from >= vertexCount
                    || to < 0 || to >= vertexCount
                    || weight < 0) {
                throw new IllegalArgumentException(
                        "Vertex out of range or negative weight");
            }

            graph.get((int) from).add(
                    new Edge((int) to, weight));
        }

        long[] distance = new long[vertexCount];
        int[] parent = new int[vertexCount];
        Arrays.fill(distance, INF);
        Arrays.fill(parent, -1);

        Comparator<State> byDistance = Comparator
                .comparingLong(State::distance)
                .thenComparingInt(State::vertex);

        PriorityQueue<State> pq = new PriorityQueue<>(byDistance);
        distance[source] = 0;
        pq.offer(new State(source, 0));

        long offers = 1;
        long polls = 0;
        long stalePops = 0;
        long improvements = 0;
        List<String> staleLog = new ArrayList<>();

        while (!pq.isEmpty()) {
            State top = pq.poll();
            polls++;

            int u = top.vertex();

            // Chỉ mở rộng từ khoảng cách hiện hành.
            if (top.distance() != distance[u]) {
                stalePops++;
                staleLog.add("(" + u + "@"
                        + top.distance() + "->"
                        + distance[u] + ")");
                continue;
            }

            for (Edge edge : graph.get(u)) {
                // Tràn long phải là lỗi, không được wrap âm.
                long candidate = Math.addExact(
                        top.distance(), edge.weight());

                if (candidate == INF) {
                    throw new ArithmeticException(
                            "Finite path conflicts with INF sentinel");
                }

                int v = edge.to();
                if (candidate < distance[v]) {
                    distance[v] = candidate;
                    parent[v] = u;

                    pq.offer(new State(v, candidate));
                    offers++;
                    improvements++;
                }
            }
        }

        return new Result(
                distance, parent, offers, polls,
                stalePops, improvements, List.copyOf(staleLog));
    }

    public static List<Integer> pathTo(Result result, int target) {
        if (result == null || target < 0
                || target >= result.distance().length) {
            throw new IllegalArgumentException("Invalid target");
        }

        if (result.distance()[target] == INF) {
            return List.of();
        }

        List<Integer> reversed = new ArrayList<>();
        for (int at = target; at != -1; at = result.parent()[at]) {
            reversed.add(at);
        }

        Collections.reverse(reversed);
        return List.copyOf(reversed);
    }

    private static String formatDistances(long[] distance) {
        StringJoiner joined = new StringJoiner(", ", "[", "]");
        for (long value : distance) {
            joined.add(value == INF ? "INF" : Long.toString(value));
        }
        return joined.toString();
    }

    public static void main(String[] args) {
        long[][] mainEdges = {
                {0, 1, 10}, {0, 2, 1}, {0, 3, 20},
                {2, 1, 1}, {2, 3, 8}, {2, 5, 15},
                {1, 3, 2}, {1, 4, 10},
                {3, 4, 3}, {3, 5, 12},
                {4, 5, 2}, {4, 6, 9},
                {5, 6, 1}, {4, 3, 0}
        };

        Result main = shortestPaths(8, mainEdges, 0);
        System.out.println("Main distances: "
                + formatDistances(main.distance()));
        System.out.println("Main parent: "
                + Arrays.toString(main.parent()));
        System.out.println("Main path to 6: " + pathTo(main, 6));
        System.out.println("Main path to 7: " + pathTo(main, 7));
        System.out.println("Main heap offers: " + main.offers());
        System.out.println("Main heap polls: " + main.polls());
        System.out.println("Main stale records: " + main.stalePops());
        System.out.println("Main improvements: " + main.improvements());
        System.out.println("Main stale log: " + main.staleLog());

        long[][] tieEdges = {
                {0, 2, 1}, {0, 1, 1},
                {2, 3, 3}, {1, 3, 3},
                {0, 3, 7}, {3, 4, 0}
        };

        Result tie = shortestPaths(5, tieEdges, 0);
        System.out.println("Tie distances: "
                + formatDistances(tie.distance()));
        System.out.println("Tie path to 4: " + pathTo(tie, 4));
        System.out.println("Tie stale records: " + tie.stalePops());

        Result zero = shortestPaths(
                1, new long[][] {{0, 0, 0}}, 0);
        System.out.println("Zero self-loop: "
                + formatDistances(zero.distance()));

        Result noEdges = shortestPaths(
                3, new long[][] {}, 2);
        System.out.println("No edges from 2: "
                + formatDistances(noEdges.distance()));

        try {
            shortestPaths(2, new long[][] {{0, 1, -1}}, 0);
            System.out.println("Negative weight: accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("Negative weight: rejected");
        }

        try {
            shortestPaths(0, new long[][] {}, 0);
            System.out.println("Empty graph: accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("Empty graph: rejected");
        }
    }
}
~~~

Biên dịch/chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 DijkstraStaleRecordsDemo.java
java DijkstraStaleRecordsDemo
~~~

**Stdout đúng theo mã và thứ tự comparator:**

~~~text
Main distances: [0, 2, 1, 4, 7, 9, 10, INF]
Main parent: [-1, 2, 0, 1, 3, 4, 5, -1]
Main path to 6: [0, 2, 1, 3, 4, 5, 6]
Main path to 7: []
Main heap offers: 13
Main heap polls: 13
Main stale records: 6
Main improvements: 12
Main stale log: [(3@9->4), (1@10->2), (4@12->7), (5@16->9), (6@16->10), (3@20->4)]
Tie distances: [0, 1, 1, 4, 4]
Tie path to 4: [0, 1, 3, 4]
Tie stale records: 1
Zero self-loop: [0]
No edges from 2: [INF, INF, 0]
Negative weight: rejected
Empty graph: rejected
~~~

### 10.1. Ý nghĩa của các bộ đếm

- **offers** đếm số lần tạo bản ghi heap, gồm bản ghi nguồn.
- **improvements** đếm các lần relax có candidate<distance[v]; vì nguồn được offer riêng nên **offers=improvements+1**.
- **polls** đếm số lần poll, gồm bản ghi hợp lệ và stale; khi chạy tới hết heap thì **polls=offers**.
- **stalePops** tăng khi poppedDistance!=distance[u]; nhánh này **không quét cạnh**.
- **staleLog** chỉ phục vụ minh họa; nếu không cần debug, bỏ nhật ký để tránh phân bổ nhiều chuỗi.

Trong ví dụ chính, polls−stalePops=13−6=**7**, đúng số đỉnh tới được từ nguồn.

### 10.2. Quy tắc comparator

Không dùng biểu thức kiểu:

~~~java
(a, b) -> (int) (a.distance() - b.distance())
~~~

vì phép trừ/ép int có thể tràn và làm comparator trả thứ tự sai. Dùng **Comparator.comparingLong(State::distance)** hoặc Long.compare. Phần thenComparingInt(State::vertex) chỉ dùng để định nghĩa thứ tự ổn định khi hòa.

Nếu bỏ tie-break theo ID, khoảng cách tối ưu vẫn phải đúng; nhưng **parent và đường in ra** có thể khác khi có nhiều đường bằng nhau.

### 10.3. INF, số lớn và overflow

Long.MAX_VALUE được dùng làm **sentinel** cho đỉnh không thể tới. Code chặn candidate==INF và dùng Math.addExact để ném lỗi nếu tràn kiểu long.

Hợp đồng số học của bản demo là: **mọi tổng candidate được tính phải nằm trong 0..Long.MAX_VALUE−1**. Nếu một ứng viên quá lớn, code có thể ném lỗi ngay cả khi còn tồn tại đường khác tốt hơn; trong trường hợp yêu cầu xử lý trọng số cực lớn, cần thiết kế phiên bản dùng BigInteger hoặc cách biểu diễn khoảng cách khác, không được im lặng biến overflow thành giá trị âm.

Không nên phép cộng INF+w trong phần relax; chỉ các đỉnh đã được đưa vào heap với distance hữu hạn mới được mở rộng.

### 10.4. Mảng trong Result và bảo toàn dữ liệu

Record Java giữ tham chiếu tới mảng; nó **không làm phần tử mảng trở thành bất biến sâu**. Mã học tập trả mảng để quan sát dễ dàng; trong API sản xuất, nếu muốn bảo vệ distance và parent, nên sao chép phòng vệ khi tạo và trả kết quả.

Mã không sửa danh sách cạnh đầu vào, mà xây danh sách kề mới. Với đồ thị vô hướng, đầu vào cần chứa **cả hai cung** cho mỗi cạnh.

## 11. Độ phức tạp của Dijkstra lazy records

Gọi V là số đỉnh, E là số **cung có hướng** trong danh sách kề.

- Xây đồ thị: **O(V+E)** thời gian và bộ nhớ.
- Mỗi lần pop hợp lệ mở rộng các cung xuất phát từ một đỉnh; nhờ trọng số không âm, mỗi đỉnh tới được được pop hợp lệ **một lần**, nên tổng số lần xét cung là **O(E)**.
- Một cung dẫn tới **tối đa một lần relax thành công** tại lần xét đó; tổng offer **không vượt E+1**.
- Mỗi thao tác offer/poll trên heap chứa tối đa O(E+1) bản ghi mất **O(log(E+2))**.
- Stale-check tốn **O(1)** cho mỗi lần pop.

Vì vậy, cận trên thời gian:

\[
\boxed{O(V+E+E\log(E+2)).}
\]

Với đồ thị đơn và V≥2, vì E=O(V²), thường thấy cách viết **O((V+E)log V)**. Với multigraph có rất nhiều cung song song, cách viết log(E+2) phản ánh đúng hơn kích thước heap.

Bộ nhớ:
- Danh sách kề O(V+E).
- Mảng distance, parent O(V).
- PriorityQueue có thể chứa **O(E)** bản ghi, vì các bản ghi cũ vẫn chờ.
- staleLog minh họa cũng có thể giữ O(E) chuỗi; bỏ nó nếu không cần.

Tổng bộ nhớ **O(V+E)**, không phải luôn O(V) nếu dùng lazy duplicates.

**Tại sao nhiều bản ghi không làm thuật toán chạy vô hạn?** Mỗi bản ghi mới tương ứng một lần giảm khoảng cách nghiêm ngặt qua một cung đang được xét, số lần xét cung bị chặn bởi E. Các chu trình trọng số 0 cũng không sinh thêm bản ghi khi candidate==distance[v] vì điều kiện relax dùng dấu <.

## 12. Dừng sớm khi chỉ hỏi một đích

Nếu chỉ cần đường ngắn nhất tới target, có thể dừng **khi poll hợp lệ** target:

~~~text
while pq not empty:
    (u,d) = pq.poll()
    if d != dist[u]:
        continue

    if u == target:
        return dist[target]      // Đã được chốt.

    relax all outgoing edges of u
~~~

**Không dừng khi vừa relax hoặc offer target.** Ví dụ 0→1(10), 0→2(1), 2→1(1) cho thấy lần phát hiện target=1 đầu tiên có chi phí 10, nhưng tối ưu thật là 2.

**Không kiểm tra target trước stale-check** vì có thể poll một bản ghi cũ của target. Nếu thuật toán cần khoảng cách tới **mọi** đỉnh, phải chạy tới hết heap; dừng tại một đích sẽ để mảng distance của những đỉnh khác chưa chắc tối ưu.

Nếu chỉ tìm một đích mà dừng sớm, đẳng thức **polls=offers** không còn bắt buộc đúng vì heap có thể vẫn còn bản ghi.

## 13. Trọng số âm, zero-one BFS và các bài liên quan

| Điều kiện | Thuật toán thường phù hợp |
|---|---|
| Mọi cạnh có trọng số bằng nhau | **BFS** |
| Trọng số chỉ 0 và 1 | **0–1 BFS** dùng deque |
| Trọng số không âm tổng quát | **Dijkstra** dùng min-heap |
| Có thể có cạnh âm | **Bellman–Ford** hoặc thuật toán được chứng minh cho cạnh âm |
| Nhiều nguồn, trọng số không âm | **Dijkstra nhiều nguồn**: offer mọi nguồn ở khoảng cách 0 |

Ví dụ có cạnh âm: 0→1(2), 0→2(5), 2→1(−4), 1→3(1). Khoảng cách ngắn nhất tới 1 là 1 qua 0→2→1; tới 3 là 2. Một Dijkstra chốt đỉnh 1 với giá trị 2 trước khi đi qua đỉnh 2 sẽ chốt sai, chứng minh không âm bị phá.

Một biến thể lazy-record không settled **có thể** tiếp tục cập nhật khi có cạnh âm, nhưng không có chứng minh Dijkstra hoặc độ phức tạp như trên; nếu có chu trình âm còn có thể không kết thúc. Vì vậy code mẫu **từ chối mọi cạnh âm**, ngay cả khi đồ thị cụ thể không có chu trình âm.

Dijkstra nhiều nguồn chỉ cần thay khởi tạo: mọi nguồn s có distance[s]=0 và được offer trước vòng while. Nếu bài hỏi từ một đỉnh **đi tới** nguồn gần nhất trên đồ thị có hướng, cần đổi hướng cạnh hoặc mô hình bài toán.

## 14. Đồ thị vô hướng, cạnh song song và đường đi chi tiết

Đồ thị có hướng chỉ có cung u→v; không thể mặc định di chuyển ngược v→u. Nếu đề là **vô hướng**, mỗi cạnh u--v trọng số w cần thêm cả:

~~~java
{u, v, w},
{v, u, w}
~~~

**Cạnh song song** có cùng u,v nhưng trọng số khác nhau được phép. Cung rẻ hơn có thể làm dist[v] giảm nhiều lần, sinh stale records. Không được tự bỏ mọi cạnh trùng đầu mút nếu chúng là cạnh độc lập, trừ khi trước đó đã chứng minh chỉ cần giữ cạnh nhỏ nhất.

**Truy vết pathTo** bằng parent[v] tạo danh sách **đỉnh** trên một đường đi ngắn nhất. Nếu có nhiều cung song song u→v, chỉ biết parent[v]=u **chưa chỉ ra cung có trọng số nào** được dùng. Khi bài yêu cầu xuất **các cạnh cụ thể và trọng số**, nên lưu parentEdgeId hoặc parentEdgeWeight mỗi khi relax thành công.

Đường đi tới v không thể tới là danh sách rỗng theo API, còn đường đi từ s tới chính s là **[s]** với tổng trọng số 0. Không dùng 0 như giá trị sentinel unreachable.

## 15. Các lỗi phổ biến

1. **Đánh dấu visited khi offer:** ngăn lần relax sau cải thiện một đỉnh.
2. **Quên stale-check:** quét lại cạnh từ các bản ghi cũ, lãng phí thời gian và dễ làm sai logic dừng/chốt.
3. **Dùng poppedDistance cũ để cập nhật khoảng cách trong khi dist[u] đã tốt hơn:** xử lý trên dữ liệu lỗi thời.
4. **Sửa field của một State đã nằm trong heap:** Java PriorityQueue không tự heapify lại sau khi khóa đổi.
5. **Comparator đọc trực tiếp mảng dist mutable** thay vì khóa cố định trong bản ghi.
6. **Không offer bản ghi mới sau relax thành công:** heap có thể không phản ánh ứng viên tốt nhất.
7. **Dùng <= cho relax:** chu trình 0 có thể tạo bản ghi vô hạn và parent không ổn định.
8. **Dùng phép trừ rồi ép int khi so long:** overflow phá thứ tự min-heap.
9. **Nhầm PriorityQueue là queue FIFO:** nó ưu tiên theo comparator, không theo thứ tự thêm.
10. **Mặc định parent là đường ít cạnh nhất giữa các đường hòa:** thuật toán chỉ tìm tổng trọng số nhỏ nhất.
11. **Không kiểm tra INF trước khi truy vết:** unreachable cần trả trạng thái rõ ràng.
12. **Cộng số lớn mà không bắt overflow:** giá trị âm giả làm sai min-heap và relax.
13. **Cho phép candidate trùng sentinel INF:** mất khả năng phân biệt hữu hạn với không tới được.
14. **Dùng Dijkstra cho trọng số âm** mà không có thuật toán/chứng minh khác.
15. **Dừng khi target mới được phát hiện**, thay vì khi poll hợp lệ.
16. **Nhầm tổng offers hoặc stalePops là số đỉnh:** một đỉnh có thể có nhiều bản ghi.
17. **Quên thêm cung chiều ngược khi đề là đồ thị vô hướng.**
18. **Không phân biệt một đường đi và tất cả đường đi ngắn nhất.**
19. **Nhầm độ phức tạp heap lazy là O(V) bộ nhớ** thay vì O(E) trong trường hợp xấu.
20. **Không reset dist, parent, heap giữa các lần chạy**, làm kết quả nhiễm phiên trước.
21. **Không kiểm thử cạnh 0, đường hòa và đỉnh unreachable** nên bỏ sót lỗi dấu so sánh.
22. **Không chú ý đặc tả số học của kiểu long** khi nhận trọng số rất lớn.
23. **Đồng nhất đồ thị không cạnh với đồ thị không đỉnh:** đồ thị còn một nguồn s nhưng không cạnh vẫn có distance[s]=0.
24. **Không đánh giá cả số bản ghi stale và số cạnh được quét:** stale-check giảm công quét kề lặp, chứ không làm biến mất thao tác poll cho bản ghi cũ.

## 16. Phương pháp kiểm thử độc lập

Với đồ thị nhỏ có trọng số không âm, có thể chạy **Bellman–Ford** như bộ tham chiếu:
1. Khởi tạo distOracle[source]=0, các đỉnh khác INF.
2. Tối đa V−1 vòng lặp, relax tất cả cung còn có đường từ nguồn.
3. So **toàn bộ khoảng cách** với Dijkstra.

Đừng chỉ so một đỉnh đích; các lỗi stale có thể ảnh hưởng một số đỉnh khác mà mẫu đơn giản chưa bộc lộ.

**Bộ test khuyến nghị:**
- Một đỉnh, không cạnh → [0].
- Self-loop trọng số 0 → [0], không vô hạn bản ghi.
- Nhiều cạnh song song trọng số khác nhau → giá trị tốt nhất.
- Đỉnh không thể tới → INF, path=[].
- Hai đường tới cùng đỉnh có trọng số hòa → distance đúng và parent theo chính sách.
- Chu trình 0 → thuật toán vẫn kết thúc nhờ relax dấu <.
- Trọng số âm → IllegalArgumentException theo hợp đồng.
- Không đỉnh nhưng truyền source=0 → đầu vào không hợp lệ.
- Trọng số quá lớn hoặc tổng vượt long/sentinel → báo lỗi số học.
- Đảo thứ tự nhập cạnh → distance không đổi; parent có thể đổi nếu các đường hòa và comparator/relax khác chính sách.

**Bất biến thống kê** với phiên bản chạy hết queue:
- offers=improvements+1.
- polls=offers.
- polls−stalePops bằng số đỉnh tới được.
- Mỗi pathTo(v) gồm các cạnh đúng chiều, chi phí cộng đúng distance[v].
- Sau khi thuật toán kết thúc, không có cung u→v nào còn relax thành công, với tổng chi phí có thể biểu diễn.

Với **cạnh song song**, nếu pathTo chỉ lưu ID đỉnh thì để kiểm tổng trọng số chính xác có thể phải giữ thêm **ID/trọng số của cạnh cha**, thay vì chọn tùy tiện một trong nhiều cung u→v.

## 17. Bài tập tự kiểm tra

**Câu 1.** Vì sao một đỉnh xuất hiện nhiều lần trong Java PriorityQueue?

**Đáp án:** Mỗi lần distance[v] giảm, thuật toán offer một State(v,newDistance) mới. State cũ không được decrease-key nên vẫn có thể nằm trong heap tới khi poll.

**Câu 2.** Khi nào phải bỏ một bản ghi heap?

**Đáp án:** Nếu poppedDistance!=distance[u] hiện tại, vì nó là ảnh chụp cũ không còn đại diện đường tốt nhất. Bỏ ngay trước khi quét cạnh kề.

**Câu 3.** Vì sao đánh dấu visited ngay khi phát hiện không đúng?

**Đáp án:** Đỉnh có thể được phát hiện qua đường trọng số cao trước, rồi được cải thiện sau. Ví dụ 0→1(10) nhưng 0→2→1 chỉ tốn 2.

**Câu 4.** Với đồ thị 8 đỉnh của bài, số offers, polls, stalePops là bao nhiêu?

**Đáp án:** Tương ứng **13, 13 và 6**, với 7 lượt poll hợp lệ cho các đỉnh 0..6; đỉnh 7 không thể tới.

**Câu 5.** Tại sao không dùng candidate<=distance[v] để offer?

**Đáp án:** Đường bằng chi phí không cải thiện kết quả; trên chu trình 0 nó có thể tạo vô hạn bản ghi bằng nhau và làm parent khó kiểm soát.

**Câu 6.** Cạnh trọng số 0 có làm Dijkstra sai không?

**Đáp án:** Không. Tất cả trọng số vẫn không âm nên chứng minh chốt đỉnh đúng; chỉ có thêm các trường hợp bằng nhau.

**Câu 7.** Vì sao comparator không được dựa trên khóa mutable?

**Đáp án:** PriorityQueue không tự điều chỉnh heap khi khóa của phần tử đang nằm trong heap thay đổi; phải dùng giá trị distance đã chụp trong State bất biến.

**Câu 8.** Có thể kết thúc khi vừa relax tới target không?

**Đáp án:** Không. Phải đợi target được **poll hợp lệ** ở khóa nhỏ nhất; đường tốt hơn có thể được phát hiện trước thời điểm đó.

**Câu 9.** Nếu có cạnh âm, dùng Dijkstra lazy không settled đã đủ bảo đảm chưa?

**Đáp án:** Chưa. Chứng minh và cận thời gian Dijkstra cần trọng số không âm. Cần chuyển sang thuật toán hỗ trợ cạnh âm như Bellman–Ford khi phù hợp.

**Câu 10.** Độ phức tạp của Dijkstra với lazy heap là gì?

**Đáp án:** **O(V+E+Elog(E+2))** thời gian, **O(V+E)** bộ nhớ khi tính cả danh sách kề và heap chứa tối đa O(E) bản ghi.

**Câu 11.** Tại sao với đồ thị có nhiều cung song song, parent[v]=u có thể chưa đủ để xuất đường đi chi tiết?

**Đáp án:** Parent chỉ nêu đỉnh trước, không biết cung nào giữa u và v đã tạo khoảng cách tốt nhất. Cần thêm parentEdge hoặc trọng số đã dùng nếu muốn in chính xác các cạnh.

**Câu 12.** Vì sao một bản ghi cũ không cần được xóa ngay lúc distance giảm?

**Đáp án:** Bản ghi mới có khóa nhỏ hơn nên được ưu tiên trước; bản ghi cũ khi poll sẽ bị stale-check loại. Cách này đơn giản và tránh thao tác tìm/xóa đắt trên Java PriorityQueue.

**Ghi nhớ:** Trong Dijkstra trọng số **không âm**, khi relax cải thiện v thì cập nhật distance[v] và **offer một State mới**. Heap có thể giữ bản ghi cũ; khi poll mà khóa không khớp distance[u], **skip trước khi duyệt kề**. Đỉnh được chốt khi **poll hợp lệ**, không phải khi enqueue. Cách làm này đúng, dễ triển khai bằng Java PriorityQueue và đổi thao tác decrease-key phức tạp thành các bản ghi stale được bỏ một cách an toàn.

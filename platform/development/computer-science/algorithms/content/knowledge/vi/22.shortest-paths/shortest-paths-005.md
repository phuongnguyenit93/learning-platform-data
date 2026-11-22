# Thuật toán Bellman–Ford

## 1. Bài toán đường đi ngắn nhất khi cạnh có thể mang trọng số âm

Cho đồ thị **có hướng** G=(V,E), mỗi cạnh u→v có trọng số w(u,v), và một đỉnh nguồn s. Ta muốn xác định **chi phí nhỏ nhất** của đường đi từ s tới mỗi đỉnh v, với chi phí bằng tổng trọng số các cạnh trên đường.

Đối với đồ thị vô hướng, có thể mô hình hóa một cạnh vô hướng {u,v} bằng hai cung u→v và v→u cùng trọng số. Nhưng một cạnh vô hướng **trọng số âm** sẽ tạo một chu trình âm gồm hai cung nếu cho phép đi qua cạnh ấy qua lại, vì vậy cần lưu ý ý nghĩa bài toán và quy định về đường đi.

Vấn đề đặc biệt: trọng số có thể là **âm**. Có nghĩa một cạnh được đi qua sẽ làm **giảm** tổng chi phí thay vì tăng. Ví dụ:

~~~text
0 -> 1 (cost 4)
0 -> 2 (cost 5)
1 -> 2 (cost -2)

Duong 0 -> 2 truc tiep: cost 5
Duong 0 -> 1 -> 2: cost 4 + (-2) = 2
~~~

Đường đi với **nhiều cạnh hơn** lại có tổng trọng số nhỏ hơn. Vì vậy BFS thông thường (tối thiểu số cạnh) không đủ. Thuật toán Dijkstra cũng không bảo đảm đúng khi tồn tại cạnh âm, vì quyết định chốt một đỉnh quá sớm có thể bỏ qua một đường cải thiện nhờ cạnh âm được xử lý về sau.

**Bellman–Ford** giải quyết đường đi ngắn nhất **đơn nguồn** với các cạnh trọng số dương, bằng 0 và âm. Thuật toán còn có khả năng phát hiện **chu trình có tổng trọng số âm tới được từ nguồn**, khi đó một số đỉnh không có khoảng cách nhỏ nhất hữu hạn.

### Ba loại kết quả phải phân biệt

Với mỗi đỉnh v, kết quả có thể thuộc một trong ba nhóm:

1. **FINITE:** có đường từ s tới v, và chi phí nhỏ nhất là một giá trị hữu hạn.
2. **UNREACHABLE:** không có đường có hướng từ s tới v; thường hiển thị là INF hoặc ∞.
3. **NEGATIVE_INFINITY:** có chu trình âm đi tới được từ s và từ chu trình ấy đi tiếp tới được v; có thể lặp chu trình âm nhiều lần để làm chi phí đường tới v thấp tùy ý, ký hiệu -INF hoặc -∞.

Đỉnh nằm **trong** chu trình âm chắc chắn thuộc trường hợp thứ ba nếu chu trình đi tới được từ nguồn; các đỉnh nằm **phía sau** chu trình theo hướng cạnh cũng vậy. Một đỉnh không nằm trên chu trình âm vẫn có thể có giá trị -∞.

**Không được nhầm INF với -INF:** INF nghĩa là hoàn toàn **không tới được**, còn -INF nghĩa là **tới được nhưng không có cận dưới hữu hạn** cho chi phí đường đi.

## 2. Phép nới lỏng cạnh (edge relaxation)

Đặt dist[v] là ước lượng chi phí tốt nhất đã biết để tới đỉnh v. Khởi tạo:

~~~text
dist[s] = 0
dist[v] = INF cho moi v khac s
parent[v] = -1 cho moi v
~~~

Với một cạnh có hướng u→v trọng số w, nếu dist[u] hữu hạn thì đường đi tới u đã biết và thêm cạnh u→v sẽ cho một cách tới v có chi phí:

~~~text
candidate = dist[u] + w
~~~

Nếu candidate nhỏ hơn dist[v] hiện tại, ta **nới lỏng (relax)** cạnh:

~~~text
if dist[u] != INF AND dist[u] + w < dist[v]:
    dist[v] = dist[u] + w
    parent[v] = u
~~~

Ý nghĩa: đã tìm được một đường từ nguồn tới v **rẻ hơn** đường đã biết trước đó, thông qua u. Khi đó parent[v] ghi nhận đỉnh đứng ngay trước v trên đường đang được chọn.

### Ví dụ một lần relax

Ban đầu ta biết:

~~~text
dist[0] = 0
dist[1] = 4
dist[2] = 5

Canh 1 -> 2 co w = -2

candidate = 4 + (-2) = 2
2 < 5, cap nhat:
dist[2] = 2
parent[2] = 1
~~~

Một lượt duyệt cạnh có thể cải thiện nhiều đỉnh. **Bellman–Ford thử relax toàn bộ cạnh nhiều lượt**, để thông tin cải thiện có cơ hội lan truyền dọc những đường đi dài.

### Không được relax từ INF

Nếu u chưa tới được, phép cộng INF+w không đại diện cho một đường đi thật. Với code dùng số nguyên và một sentinel rất lớn, cộng thêm số âm có thể tạo một số hữu hạn giả hoặc tràn số; cần kiểm tra reachable trước khi tính candidate.

Trong Java mẫu bên dưới, dùng **BigInteger và null cho đỉnh chưa tới được**, tránh việc lạm dụng một con số đặc biệt làm vô cực và tránh tràn số khi cộng trọng số nhiều lần.

## 3. Tại sao lặp tối đa V-1 lượt?

Gọi n=|V|. Nếu không có chu trình âm **tới được từ nguồn**, mọi đỉnh có một khoảng cách ngắn nhất hữu hạn đều có thể đạt khoảng cách ấy bằng một **đường đi đơn** (không lặp đỉnh).

Một đường đi đơn trên n đỉnh có tối đa n-1 cạnh. Vì vậy Bellman–Ford chỉ cần **n-1 lượt nới lỏng toàn bộ tập cạnh** để tìm đủ mọi đường đi ngắn nhất hữu hạn.

Cốt lõi lý thuyết là phiên bản **đồng bộ** của phép relax:

~~~text
D_0[s] = 0
D_0[v != s] = INF

D_k[v] = min(
    D_(k-1)[v],
    min over edges (u,v) of D_(k-1)[u] + w(u,v)
)
~~~

Khi dùng bảng riêng cho lượt trước và lượt hiện tại, D_k[v] đúng bằng chi phí nhỏ nhất trong các **walk từ s tới v có tối đa k cạnh**, nếu có. Tại k=n-1, mọi đường đi đơn được xét, nên khoảng cách ngắn nhất hữu hạn đã đạt được.

### Phiên bản in-place chạy ra sao?

Triển khai thực tế thường relax trực tiếp lên mảng dist hiện tại:

~~~text
repeat up to n-1 times:
    changed = false
    for every edge (u,v,w):
        if dist[u] finite and dist[u]+w < dist[v]:
            dist[v] = dist[u]+w
            parent[v] = u
            changed = true
~~~

Một lượt in-place đôi khi lan truyền cập nhật qua **nhiều cạnh trên cùng một đường** nếu thứ tự duyệt cạnh thuận lợi. Do vậy kết quả của từng lượt in-place **không bắt buộc giống hệt D_k của phiên bản đồng bộ**.

Tuy nhiên, phiên bản in-place vẫn bảo đảm sau k lượt ít nhất đã xét được mọi đường có tối đa k cạnh: những cải thiện có thể lan truyền sớm hơn nhưng không làm mất đường hợp lệ. Vì thế sau n-1 lượt, các khoảng cách hữu hạn cần thiết đã ổn định khi không có chu trình âm tới được.

### Vì sao phải cho tới n-1 lượt dù có ít cạnh?

Số lượt tối đa phụ thuộc số đỉnh, không phải số cạnh. Xét một chuỗi s→a→b→c→t mà các cạnh được liệt kê theo thứ tự **ngược chiều lan truyền**. Một lượt có thể chỉ đẩy được thông tin đi thêm một bước vì cạnh ở cuối đường được duyệt trước khi dist của đỉnh đầu cạnh ấy được cải thiện.

Ngược lại, nếu cạnh được liệt kê đúng thứ tự đường, một lượt có thể đủ cho toàn bộ chuỗi. Thuật toán **không được dựa vào thứ tự ngẫu nhiên của input** để giảm số lượt một cách không có kiểm chứng.

## 4. Pseudocode Bellman–Ford cơ bản

Bài toán đầu tiên: chỉ tìm khoảng cách hữu hạn trong trường hợp **không có chu trình âm tới được**.

~~~text
bellmanFord(n, edges, source):
    dist = [INF] * n
    parent = [-1] * n
    dist[source] = 0

    for pass from 1 to n-1:
        changed = false

        for edge in edges:
            u = edge.from
            v = edge.to
            w = edge.weight

            if dist[u] == INF:
                continue

            if dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                parent[v] = u
                changed = true

        if not changed:
            break

    return dist, parent
~~~

**Đầu vào:** n đỉnh đánh số 0..n-1, danh sách các cạnh **có hướng** (u,v,w), source hợp lệ.

**Đầu ra:** dist và parent, khi mỗi đỉnh có đường ngắn nhất hữu hạn hoặc unreachable; khi có chu trình âm reachable, dist ở cuối n-1 lượt chỉ là **ước lượng tạm**, không nên công bố như giá trị ngắn nhất đúng.

Một số cách viết trả false khi phát hiện **bất kỳ** chu trình âm reachable. Cách ấy hợp lệ nếu đề chỉ hỏi “toàn bộ bài có khoảng cách hữu hạn không”. Nhưng nếu muốn trả lời riêng cho từng đỉnh, phải phân biệt đỉnh hữu hạn và đỉnh bị ảnh hưởng -∞ như phần sau.

### Early stopping

Nếu một lượt duyệt mọi cạnh **không có bất kỳ relax thành công nào**, các dist đã ổn định. Lặp lại các lượt sau sẽ không tạo cập nhật mới, nên có thể dừng sớm.

Trong một đồ thị có chu trình âm reachable, việc giảm chi phí liên tục trên chu trình bảo đảm không thể ổn định thật sau khi đã tiếp cận chu trình. Vì vậy early stopping an toàn; nó không che giấu một chu trình âm reachable đã được đưa vào mô hình.

**Không được dừng chỉ vì một số cạnh không relax.** Điều kiện dừng là **toàn bộ một lượt** không có cải thiện nào.

## 5. Ví dụ có cạnh âm nhưng không có chu trình âm

Xét đồ thị **có hướng** với 6 đỉnh 0..5, nguồn 0, các cạnh theo thứ tự:

~~~text
0 -> 1  weight =  4
0 -> 2  weight =  5
1 -> 2  weight = -2
1 -> 3  weight =  6
2 -> 3  weight =  3
3 -> 4  weight =  2
2 -> 4  weight = 10

Dinh 5 co lap.
~~~

Đồ thị này không có chu trình có hướng, nên chắc chắn không có chu trình âm. Nhưng có một cạnh âm 1→2 giúp cải thiện đường đi.

### Theo dõi một lượt relax

Khởi tạo:

~~~text
dist = [0, INF, INF, INF, INF, INF]
parent = [-1, -1, -1, -1, -1, -1]
~~~

Duyệt các cạnh theo thứ tự trên:

| Cạnh | candidate | Kết quả |
| --- | ---: | --- |
| 0→1 (4) | 0+4=4 | dist[1]=4 |
| 0→2 (5) | 0+5=5 | dist[2]=5 |
| 1→2 (-2) | 4-2=2 | dist[2] cải thiện từ 5 xuống 2 |
| 1→3 (6) | 4+6=10 | dist[3]=10 |
| 2→3 (3) | 2+3=5 | dist[3] cải thiện từ 10 xuống 5 |
| 3→4 (2) | 5+2=7 | dist[4]=7 |
| 2→4 (10) | 2+10=12 | Không cải thiện dist[4]=7 |

Chỉ trong lượt đầu, nhờ duyệt cạnh theo thứ tự thuận lợi, ta đã có:

~~~text
dist   = [0, 4, 2, 5, 7, INF]
parent = [-1, 0, 1, 2, 3, -1]
~~~

Lượt thứ hai không tạo cập nhật nên chương trình có thể dừng với **passes=2 và relaxations=6** theo cách đếm trong mã Java. Số lượt này không phải hằng số của mọi biểu diễn graph; đổi thứ tự cạnh có thể thay đổi số lượt cần dùng.

Một đường ngắn nhất từ 0 đến 4:

~~~text
0 -> 1 -> 2 -> 3 -> 4
cost = 4 + (-2) + 3 + 2 = 7
~~~

Đỉnh 5 có giá trị INF vì không có đường từ 0 tới 5. Kết quả này **không bị ảnh hưởng bởi một chu trình âm nào** vì graph mẫu không có chu trình.

## 6. Chu trình âm reachable: vì sao không có giá trị nhỏ nhất hữu hạn?

Một **chu trình âm (negative-weight cycle)** là một chu trình có hướng với tổng trọng số các cạnh **nhỏ hơn 0**.

Giả sử có đường từ source s tới một chu trình âm C, và từ C có đường tới v. Nếu đi qua C thêm một lần, tổng chi phí giảm một lượng dương cố định. Ta có thể đi quanh C 1, 2, 3, ... lần trước khi rời chu trình tới v.

Vì thế chi phí đi từ s tới v có thể thấp tùy ý:

~~~text
cost(k) = cost(toCycle) + k * cycleWeight + cost(fromCycleToV)

cycleWeight < 0
k co the tang khong gioi han

lim cost(k) khi k -> +infinity = -infinity
~~~

Nói cách khác, **không tồn tại một chi phí nhỏ nhất hữu hạn** cho v; ta ký hiệu dist[v]=-INF.

### Ví dụ chu trình âm reachable

Có 7 đỉnh, nguồn 0, các cạnh:

~~~text
0 -> 1  cost +2
1 -> 2  cost +2
2 -> 3  cost +2
3 -> 1  cost -7
3 -> 4  cost +1
4 -> 5  cost +1
0 -> 6  cost +10
~~~

Chu trình:

~~~text
1 -> 2 -> 3 -> 1
total = 2 + 2 - 7 = -3
~~~

Nguồn 0 tới được chu trình qua 0→1. Từ chu trình đi tiếp tới 4 và 5 được. Do đó:

- Đỉnh 1,2,3: -INF vì nằm trên chu trình âm reachable.
- Đỉnh 4,5: -INF vì có đường đi **từ chu trình** tới chúng.
- Đỉnh 0: FINITE=0, vì không có đường từ chu trình quay về 0.
- Đỉnh 6: FINITE=10, vì có cạnh 0→6 nhưng không có đường từ chu trình tới 6.

Kết quả theo đỉnh:

~~~text
[0, -INF, -INF, -INF, -INF, -INF, 10]
~~~

Ví dụ này nhấn mạnh: **phát hiện một chu trình âm reachable không làm mọi đỉnh reachable trở thành -INF**. Chỉ những đỉnh có thể nhận ảnh hưởng từ chu trình âm mới có chi phí không bị chặn dưới.

### Chu trình âm nhưng không reachable từ nguồn

Nếu có một chu trình âm ở một thành phần **không đi tới được từ s**, nó không ảnh hưởng các đường bắt đầu từ s.

Ví dụ:

~~~text
0 -> 1 cost 3

2 -> 3 cost -2
3 -> 2 cost -1
3 -> 4 cost +2
~~~

Với s=0:

~~~text
dist[0] = 0
dist[1] = 3
dist[2] = INF
dist[3] = INF
dist[4] = INF
~~~

Có chu trình âm 2→3→2, nhưng Bellman–Ford **đơn nguồn từ 0** không xem đó là chu trình âm reachable. Muốn phát hiện chu trình âm ở bất cứ đâu trong đồ thị, cần biến thể **super-source**, được trình bày ở phần 16.

## 7. Phát hiện chu trình âm bằng lượt relax thứ n

Sau n-1 lượt relax, kiểm tra **thêm một lượt** trên các cạnh:

~~~text
for (u,v,w) in edges:
    if dist[u] != INF and dist[u] + w < dist[v]:
        negativeCycleReachable = true
~~~

Nếu vẫn còn một cải thiện đối với một đỉnh có đường đi từ source, tồn tại một **chu trình âm reachable**. Vì nếu không có chu trình âm reachable thì đã có đường đi đơn tối ưu với tối đa n-1 cạnh, không thể còn cải thiện sau n-1 lượt.

Một lưu ý: **lượt kiểm tra này có thể chỉ đọc dist sau n-1 lượt, không nhất thiết phải cập nhật dist**. Điều đó rất tiện nếu muốn giữ nguyên ước lượng tại mốc n-1 lượt để tiếp tục phân loại đỉnh affected.

Nếu cần dựng **nhân chứng chu trình**, có thể chạy một lượt relax thứ n trên bản sao dist và parent, nhớ một đỉnh vừa được cải thiện, rồi truy vết predecessor. Chi tiết ở phần 9.

### Vì sao chỉ xét cạnh có nguồn reachable?

Nếu dist[u] vẫn là INF, cạnh u→v không nằm trên bất kỳ đường đi từ s theo hiểu biết của BFS/relax, và nó không có quyền cải thiện một đỉnh reachable.

Bỏ kiểm tra nguồn reachable có thể tạo **phát hiện chu trình âm giả** khi dùng sentinel INF và số âm; với giá trị nguyên cố định còn có nguy cơ tràn. Java mẫu dùng BigInteger và null cho unreachable để tránh cả hai.

### Một cạnh còn relax không nhất thiết là cạnh thuộc chu trình

Trong ví dụ ở phần 6, sau n-1 lượt có thể còn cạnh 3→4 hoặc 4→5 cải thiện, dù các đỉnh 4,5 **không nằm trên chu trình âm**. Vì vậy:

- Một cạnh relax được là bằng chứng có **chu trình âm reachable ở nơi có thể ảnh hưởng tới nó**.
- Đích của cạnh relax được là điểm **khởi đầu đáng tin cậy để lan truyền dấu -INF**.
- Không được xem mọi đỉnh nhận cập nhật ở lượt n là **đỉnh nằm trên chu trình**.

Muốn có danh sách chính xác những đỉnh **thuộc chu trình âm**, cần phân tích sâu hơn. Để tìm tất cả đỉnh có **khoảng cách -INF**, chỉ cần bước lan truyền từ những đỉnh có thể còn cải thiện.

## 8. Đánh dấu tất cả đỉnh bị ảnh hưởng -INF

Nếu chỉ cần một cờ “đồ thị có chu trình âm reachable không”, kiểm tra lượt n đã đủ. Nhưng nếu đề hỏi khoảng cách tới **từng đỉnh**, ta phải tìm tất cả đỉnh có thể đi tới **từ chu trình âm reachable**.

Quy trình hai pha:

**Pha A – tìm hạt giống ảnh hưởng.** Sau n-1 lượt relax, quét mọi cạnh u→v:

~~~text
if dist[u] != INF and dist[u] + w < dist[v]:
    mark v as affected
    queue.add(v)
~~~

Nếu dist[v] là INF và có cạnh từ một u reachable tới v, cũng cần xem như một cập nhật, mặc dù sau n-1 lượt chuẩn trên graph hữu hạn, một v reachable như vậy thực tế đã phải được khám phá.

**Pha B – lan truyền theo hướng cạnh.** Dùng BFS/DFS từ mọi v đã đánh dấu:

~~~text
while queue not empty:
    u = queue.removeFirst()
    for each outgoing edge u -> v:
        if not affected[v]:
            affected[v] = true
            queue.add(v)
~~~

**Mọi đỉnh được đánh dấu** có giá trị ngắn nhất -INF. Những đỉnh không được đánh dấu vẫn có thể có giá trị hữu hạn hoặc không tới được.

### Giải thích tại sao lan truyền đúng

Nếu u có chi phí có thể giảm không giới hạn và tồn tại cạnh u→v có trọng số hữu hạn, thì chi phí tới v cũng có thể giảm không giới hạn bằng cách đi tới u rẻ tùy ý rồi thêm cạnh u→v. Tương tự, mọi đỉnh đi tới được từ u cũng chịu ảnh hưởng.

Ngược lại, một đỉnh không nằm trên bất kỳ đường đi nào xuất phát từ chu trình âm reachable không thể sử dụng chu trình ấy để giảm chi phí. Nếu không chịu ảnh hưởng từ chu trình âm khác, khoảng cách ngắn nhất tới nó vẫn hữu hạn khi reachable.

### Những trạng thái không thể dùng parent để dựng đường tối ưu

Với một đỉnh affected, **không có đường đi với chi phí nhỏ nhất hữu hạn**, nên yêu cầu “khôi phục một đường đi ngắn nhất” theo nghĩa chi phí tối ưu là không xác định. Một path cụ thể từ s tới nó có thể tồn tại, nhưng có thể có walk rẻ hơn bằng cách lặp chu trình âm thêm lần nữa.

Trong mã Java, hàm pathTo(v) sẽ **từ chối** nếu v bị affected, thay vì trả một đường rồi gọi đó là ngắn nhất. Với v unreachable, pathTo trả danh sách rỗng; với v hữu hạn, parent cho một đường tối ưu.

## 9. Trích xuất một chu trình âm làm bằng chứng

Đôi khi không chỉ cần phát hiện có chu trình âm mà còn phải **in một chu trình cụ thể** để giải thích dữ liệu lỗi.

Cách kinh điển dựa trên predecessor:

1. Chạy n lượt relax (hoặc n-1 lượt rồi lượt thứ n **trên bản sao dist/parent**).
2. Ghi lại đỉnh x được cập nhật **cuối cùng** ở lượt n.
3. Nếu không có cập nhật, không có chu trình âm reachable.
4. Nếu có x, lần theo parent[x] **đúng n lần** để chắc chắn đi vào một chu trình.
5. Từ đỉnh nằm trên chu trình, tiếp tục lần theo parent cho đến khi lặp lại đỉnh đầu.
6. Đảo danh sách theo hướng predecessor để in các đỉnh **đúng chiều cạnh**, lặp đỉnh đầu ở cuối.

Giả mã:

~~~text
x = lastUpdatedOnNthPass
if x == -1:
    return empty witness

repeat n times:
    x = parent[x]

cycleBackward = []
at = x
do:
    cycleBackward.add(at)
    at = parent[at]
while at != x

cycleBackward.add(x)
reverse(cycleBackward)
return cycleBackward
~~~

### Tại sao cần nhảy n lần?

Đỉnh x vừa được cải thiện có thể nằm **phía sau** chu trình, không nhất thiết thuộc chu trình. Mảng parent có thể chứa một “đuôi” dẫn ngược vào chu trình; với n đỉnh, nhảy n lần theo parent bảo đảm vào vùng có lặp đỉnh nếu có một cập nhật tại lượt n do chu trình âm reachable.

Ví dụ:

~~~text
0 -> 1 -> 2 -> 3 -> 1
               |
               -> 4 -> 5
~~~

Nếu lượt n cập nhật đỉnh 5, lần theo parent 5→4→3→2→1→3... cuối cùng sẽ nằm trong chu trình 1,2,3. Truy vết rồi đảo cho witness:

~~~text
[1,2,3,1]
~~~

Đây là một chu trình có tổng chi phí 2+2-7=-3 trong ví dụ phần 6.

**Cạnh song song:** nếu hai đỉnh có nhiều cạnh khác trọng số, một danh sách **đỉnh** có thể chưa đủ để xác minh chính xác **tổng trọng số** của chu trình. Khi cần chứng minh chi phí âm từng cạnh, lưu **chỉ số cạnh predecessor (parentEdge)** cùng parent, rồi cộng chính những cạnh đã được relax. Trong mã demo, witness hiển thị danh sách đỉnh; tất cả cạnh trong các ví dụ negative cycle đều không mơ hồ về trọng số.

## 10. Các trạng thái output và cách quản lý parent

Cần tách hai khái niệm:

- **Giá trị dist[v] tạm** sau n-1 lượt relax.
- **Trạng thái cuối** của v: UNREACHABLE, FINITE hay NEGATIVE_INFINITY.

Nếu v thuộc NEGATIVE_INFINITY, con số tạm trong dist[v] **không phải đáp án đường đi ngắn nhất**, và cũng không phải một giá trị xấp xỉ hữu hạn có ý nghĩa ổn định. Đừng in nó như “khoảng cách” đúng chỉ vì nó đang là một số nguyên.

### Hợp đồng API phù hợp

Một kết quả tính toán có thể cung cấp:

~~~text
status(v):
    UNREACHABLE       -> khong co duong di tu source
    FINITE            -> dist[v] la chi phi nho nhat
    NEGATIVE_INFINITY -> chi phi khong bi chan duoi

pathTo(v):
    UNREACHABLE       -> danh sach rong
    FINITE            -> mot duong di toi uu
    NEGATIVE_INFINITY -> bao loi: khong co path toi uu huu han
~~~

Nếu nguồn s bị ảnh hưởng bởi chu trình âm reachable đi ngược về s, status(s) cũng phải là NEGATIVE_INFINITY, chứ không cố định s luôn có khoảng cách 0 trong mọi graph. Đường độ dài 0 cho chi phí 0 vẫn tồn tại, nhưng nó **không nhỏ nhất** nếu có thể đi từ s qua chu trình âm rồi quay về s với tổng chi phí âm.

### Kiểm tra đường đi hữu hạn

Với một đỉnh v FINITE, lần ngược parent cho tới source. Mỗi parent[v]=u phải tương ứng một cạnh u→v thật sự, và tổng trọng số các cạnh trên đường bằng dist[v]. Nếu v là nguồn và có giá trị FINITE, path chỉ là [source].

Đối với dữ liệu có nhiều đường bằng chi phí, lựa chọn parent có thể phụ thuộc thứ tự duyệt cạnh; **không được giả định một đường đi ngắn nhất là duy nhất**.

Để hạn chế lỗi vòng predecessor do bug hoặc dữ liệu không nhất quán, mã Java dùng một giới hạn số bước khi dựng path và báo lỗi nếu chuỗi parent không chạm điểm kết thúc như mong đợi.

## 11. Java 17 – chương trình Bellman–Ford đầy đủ, tránh tràn số

Mã chạy độc lập dưới đây dùng:

- **Edge(from,to,weight):** cạnh có hướng, trọng số long.
- **BigInteger[] distance:** chi phí tích lũy, tránh tràn long khi đường dài hoặc trọng số rất lớn.
- **null:** biểu diễn chưa có đường từ nguồn tới đỉnh; không dùng một giá trị long tùy ý cho INF.
- **int[] parent:** dùng dựng đường đi hữu hạn và cycle witness.
- **boolean[] negativeInfinity:** đánh dấu mọi đỉnh có đường từ chu trình âm reachable tới được.
- **List<Integer> cycle:** một chu trình âm reachable có thể dùng làm bằng chứng.
- **passes, relaxations:** đếm lượt duyệt cạnh và số lần relax trong n-1 lượt để người học quan sát.

Java 17 hỗ trợ record và switch expression. Chương trình cố ý ưu tiên **tính rõ ràng và độ an toàn số học**; BigInteger có chi phí cao hơn long, và record chứa mảng Java không bất biến sâu nếu người gọi sửa mảng.

Lưu toàn bộ code trong tệp **BellmanFordDemo.java**:

~~~java
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class BellmanFordDemo {

    record Edge(int from, int to, long weight) {}

    enum Status {
        UNREACHABLE,
        FINITE,
        NEGATIVE_INFINITY
    }

    record Result(
            BigInteger[] distance,
            int[] parent,
            boolean[] negativeInfinity,
            List<Integer> cycle,
            int passes,
            long relaxations) {

        Status status(int v) {
            if (v < 0 || v >= distance.length) {
                throw new IllegalArgumentException("vertex out of range");
            }
            if (negativeInfinity[v]) {
                return Status.NEGATIVE_INFINITY;
            }
            return distance[v] == null
                    ? Status.UNREACHABLE : Status.FINITE;
        }

        String value(int v) {
            return switch (status(v)) {
                case UNREACHABLE -> "INF";
                case NEGATIVE_INFINITY -> "-INF";
                case FINITE -> distance[v].toString();
            };
        }

        List<Integer> pathTo(int target) {
            Status state = status(target);
            if (state == Status.UNREACHABLE) {
                return List.of();
            }
            if (state == Status.NEGATIVE_INFINITY) {
                throw new IllegalStateException(
                        "no finite shortest path");
            }

            List<Integer> reversed = new ArrayList<>();
            int at = target;
            for (int steps = 0;
                    at != -1 && steps <= parent.length;
                    steps++) {
                reversed.add(at);
                at = parent[at];
            }
            if (at != -1) {
                throw new IllegalStateException(
                        "invalid predecessor chain");
            }
            Collections.reverse(reversed);
            return List.copyOf(reversed);
        }
    }

    static Result solve(int n, List<Edge> edges, int source) {
        if (n <= 0) {
            throw new IllegalArgumentException(
                    "n must be positive");
        }
        if (source < 0 || source >= n) {
            throw new IllegalArgumentException(
                    "source out of range");
        }
        Objects.requireNonNull(edges, "edges");

        List<List<Integer>> adj = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            adj.add(new ArrayList<>());
        }

        for (Edge e : edges) {
            if (e == null
                    || e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n) {
                throw new IllegalArgumentException("invalid edge");
            }
            adj.get(e.from()).add(e.to());
        }

        BigInteger[] dist = new BigInteger[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);
        dist[source] = BigInteger.ZERO;

        // V-1 passes; stop if an entire pass changes nothing.
        int passes = 0;
        long relaxations = 0;
        for (int pass = 1; pass < n; pass++) {
            passes++;
            boolean changed = false;

            for (Edge e : edges) {
                int u = e.from();
                int v = e.to();
                if (dist[u] == null) {
                    continue;
                }

                BigInteger candidate = dist[u].add(
                        BigInteger.valueOf(e.weight()));
                if (dist[v] == null
                        || candidate.compareTo(dist[v]) < 0) {
                    dist[v] = candidate;
                    parent[v] = u;
                    changed = true;
                    relaxations++;
                }
            }

            if (!changed) {
                break;
            }
        }

        // Detection on the frozen values after V-1 passes.
        // Each relaxable destination seeds NEGATIVE_INFINITY.
        boolean[] affected = new boolean[n];
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (Edge e : edges) {
            int u = e.from();
            int v = e.to();
            if (dist[u] == null) {
                continue;
            }
            BigInteger candidate = dist[u].add(
                    BigInteger.valueOf(e.weight()));
            if (dist[v] == null
                    || candidate.compareTo(dist[v]) < 0) {
                if (!affected[v]) {
                    affected[v] = true;
                    queue.addLast(v);
                }
            }
        }

        // Propagate -INF through all outgoing reachable edges.
        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (int v : adj.get(u)) {
                if (!affected[v]) {
                    affected[v] = true;
                    queue.addLast(v);
                }
            }
        }

        // Separate Nth pass on copies to get one cycle witness.
        BigInteger[] probe = dist.clone();
        int[] pred = parent.clone();
        int lastUpdated = -1;

        for (Edge e : edges) {
            int u = e.from();
            int v = e.to();
            if (probe[u] == null) {
                continue;
            }
            BigInteger candidate = probe[u].add(
                    BigInteger.valueOf(e.weight()));
            if (probe[v] == null
                    || candidate.compareTo(probe[v]) < 0) {
                probe[v] = candidate;
                pred[v] = u;
                lastUpdated = v;
            }
        }

        List<Integer> witness = List.of();
        if (lastUpdated != -1) {
            int x = lastUpdated;

            // Enter a predecessor cycle.
            for (int i = 0; i < n; i++) {
                x = pred[x];
            }

            List<Integer> reversed = new ArrayList<>();
            int at = x;
            do {
                reversed.add(at);
                at = pred[at];
            } while (at != x);
            reversed.add(x);
            Collections.reverse(reversed);
            witness = List.copyOf(reversed);
        }

        return new Result(
                dist, parent, affected, witness,
                passes, relaxations);
    }

    static String show(Result result) {
        List<String> values = new ArrayList<>();
        for (int v = 0; v < result.distance().length; v++) {
            values.add(result.value(v));
        }
        return values.toString();
    }

    static List<Integer> affectedVertices(Result result) {
        List<Integer> answer = new ArrayList<>();
        for (int v = 0; v < result.negativeInfinity().length; v++) {
            if (result.negativeInfinity()[v]) {
                answer.add(v);
            }
        }
        return List.copyOf(answer);
    }

    public static void main(String[] args) {
        Result finite = solve(6, List.of(
                new Edge(0, 1, 4),
                new Edge(0, 2, 5),
                new Edge(1, 2, -2),
                new Edge(1, 3, 6),
                new Edge(2, 3, 3),
                new Edge(3, 4, 2),
                new Edge(2, 4, 10)), 0);

        System.out.println("finite distances = " + show(finite));
        System.out.println("finite parents = " +
                Arrays.toString(finite.parent()));
        System.out.println("finite path 0->4 = " +
                finite.pathTo(4));
        System.out.println("finite status 5 = " +
                finite.status(5));
        System.out.println("finite passes = " + finite.passes()
                + ", relaxations = " + finite.relaxations());

        Result negative = solve(7, List.of(
                new Edge(0, 1, 2),
                new Edge(1, 2, 2),
                new Edge(2, 3, 2),
                new Edge(3, 1, -7),
                new Edge(3, 4, 1),
                new Edge(4, 5, 1),
                new Edge(0, 6, 10)), 0);

        System.out.println("cycle states = " + show(negative));
        System.out.println("cycle affected = " +
                affectedVertices(negative));
        System.out.println("cycle witness = " + negative.cycle());
        System.out.println("safe path 0->6 = " +
                negative.pathTo(6));

        Result unreachableCycle = solve(5, List.of(
                new Edge(0, 1, 3),
                new Edge(2, 3, -2),
                new Edge(3, 2, -1),
                new Edge(3, 4, 2)), 0);

        System.out.println("unreachable cycle states = " +
                show(unreachableCycle));
        System.out.println("unreachable cycle witness = " +
                unreachableCycle.cycle());

        Result selfLoop = solve(2, List.of(
                new Edge(0, 1, 2),
                new Edge(1, 1, -1)), 0);
        System.out.println("negative self-loop states = " +
                show(selfLoop));
        System.out.println("negative self-loop witness = " +
                selfLoop.cycle());

        try {
            negative.pathTo(5);
        } catch (IllegalStateException ex) {
            System.out.println("affected path: " + ex.getMessage());
        }

        try {
            solve(2, List.of(new Edge(0, 2, 4)), 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid input: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac BellmanFordDemo.java
java BellmanFordDemo
~~~

**Stdout chính xác** với thứ tự các cạnh trong chương trình:

~~~text
finite distances = [0, 4, 2, 5, 7, INF]
finite parents = [-1, 0, 1, 2, 3, -1]
finite path 0->4 = [0, 1, 2, 3, 4]
finite status 5 = UNREACHABLE
finite passes = 2, relaxations = 6
cycle states = [0, -INF, -INF, -INF, -INF, -INF, 10]
cycle affected = [1, 2, 3, 4, 5]
cycle witness = [1, 2, 3, 1]
safe path 0->6 = [0, 6]
unreachable cycle states = [0, 3, INF, INF, INF]
unreachable cycle witness = []
negative self-loop states = [0, -INF]
negative self-loop witness = [1, 1]
affected path: no finite shortest path
invalid input: invalid edge
~~~

### Điểm cần đọc kỹ trong mã

**BigInteger thay vì INF sentinel:** Java demo dùng null cho một đỉnh chưa được reach. Chỉ khi dist[u]!=null mới tạo candidate. Cộng BigInteger với trọng số chuyển từ long không tràn số ngay cả khi tích lũy qua rất nhiều cạnh. Tuy nhiên, BigInteger có chi phí tính toán theo số bit, không phải phép cộng O(1) trong mọi mô hình.

**Duyệt cạnh có hướng:** mỗi Edge(u,v,w) chỉ cho phép u→v. Không tự động thêm cạnh ngược. Nếu mô hình dùng cạnh vô hướng không âm, phải tạo hai Edge cho mỗi cạnh; còn cạnh vô hướng trọng số âm có thể làm khái niệm walk ngắn nhất trở nên -∞ như đã giải thích.

**Lượt relax tối đa n-1:** biến passes đếm những lượt quét cạnh thực tế. Nếu một lượt không thay đổi thì dừng; vì thế passes có thể nhỏ hơn n-1. Biến relaxations đếm **lần thay đổi dist** trong n-1 lượt, không tính lượt kiểm tra negative-cycle và không tính probe để dựng witness.

**Tách detection với witness:** Pha detection đọc giá trị dist đã ổn định ở mốc n-1 lượt mà không cập nhật, sau đó lan truyền affected. Pha witness dùng bản sao probe/pred và thực hiện thêm một lượt relax để dựng một chu trình cụ thể. Vì vậy thao tác dựng witness **không làm sai** những giá trị và parent được dùng trong kết quả chính.

**Không in giá trị tạm của đỉnh affected:** show(result) kiểm tra negativeInfinity[v] trước khi in BigInteger; v bị ảnh hưởng hiển thị -INF. Với unreachable, hiển thị INF; chỉ các đỉnh FINITE mới in số nguyên.

**Hàm pathTo:** trả danh sách rỗng cho unreachable, ném IllegalStateException cho -INF, còn với đỉnh hữu hạn thì truy parent đến -1. Chương trình giới hạn số bước predecessor như một kiểm tra phòng trường hợp dữ liệu không nhất quán. Đối với một đường đi ngắn nhất hữu hạn thực sự, chuỗi parent cần dẫn về nguồn mà không tạo vòng.

**Cycle witness:** danh sách [1,2,3,1] đã được đảo để đúng chiều cạnh, và tổng trọng số vòng này bằng -3. Nếu có nhiều chu trình âm reachable, hàm trả **một** witness được tìm thấy theo thứ tự relax của input, không phải tất cả chu trình.

### Giới hạn và giao diện thực tế

- solve cần n>0, source trong [0,n) và mọi đầu cạnh nằm trong miền. Với đồ thị n=0, không tồn tại source hợp lệ cho bài toán đơn nguồn; nên từ chối thay vì tự chọn source.
- Input weights dùng long; BigInteger được dùng cho **tổng**, không có giới hạn long cho tổng đường đi. Nếu trọng số từng cạnh vượt long, cần đổi kiểu input sang BigInteger.
- Result chứa các mảng Java có thể bị code ngoài sửa dù record tự nó là một kiểu gọn; đây là ví dụ học tập, không phải API bất biến sâu hoàn chỉnh.
- Khi đồ thị có rất nhiều đỉnh và chuỗi cạnh dài, bộ nhớ dùng cho mảng và danh sách có thể lớn; chương trình không dùng thuật toán tối ưu hóa riêng cho đồ thị thưa vô cùng lớn.
- Kết quả witness là chuỗi **đỉnh**. Nếu có cạnh song song nhiều trọng số giữa cùng hai đỉnh, cần lưu parentEdge để in đúng các cạnh cụ thể của chu trình âm.

## 12. Chứng minh tính đúng khi không có chu trình âm reachable

### Bất biến trên phép relax

Mỗi lần dist[v] được gán một số hữu hạn, tồn tại **một walk có hướng từ source tới v** có tổng trọng số bằng con số ấy tại thời điểm gán. Chứng minh bằng quy nạp trên các phép relax:

- Ban đầu dist[source]=0 tương ứng walk độ dài 0.
- Nếu dist[u] tương ứng một walk tới u, ghép thêm cạnh u→v tạo walk tới v với chi phí dist[u]+w(u,v).
- Khi gán dist[v] bằng candidate, candidate là chi phí của một walk thật.

Vì vậy thuật toán **không tự tạo ra** một chi phí thấp hơn đường đi thực tế bằng phép toán không hợp lệ. Sự cải thiện luôn có một walk làm nhân chứng.

### Đảm bảo bao phủ mọi đường đi đơn

Sau k lượt duyệt mọi cạnh, mọi đường đi dài tối đa k cạnh đã có cơ hội truyền thông tin chi phí tới đích. Trong phiên bản in-place, một số đường dài hơn còn có thể được truyền ngay trong cùng lượt; điều đó chỉ giúp tiến nhanh hơn. Ta có thể dùng quy nạp theo số cạnh của đường đi để khẳng định sau n-1 lượt, mọi đường đơn đã được bao phủ.

Nếu không có chu trình âm reachable, mọi walk từ s tới v có thể loại bỏ các chu trình lặp không âm mà **không tăng** chi phí. Do đó tồn tại một đường đi đơn tối ưu, có tối đa n-1 cạnh.

Kết hợp hai lập luận: sau n-1 lượt, dist[v] không lớn hơn chi phí của đường đơn tối ưu; đồng thời nó là chi phí một walk thật, không thể nhỏ hơn giá trị tối ưu. Vì vậy dist[v] bằng khoảng cách ngắn nhất hữu hạn.

### Nếu còn relax sau n-1 lượt

Giả sử dist[u]+w<dist[v] sau n-1 lượt với u reachable. Nếu không có chu trình âm reachable, tất cả dist hữu hạn đã bằng khoảng cách tối ưu; bất đẳng thức tam giác của đường ngắn nhất yêu cầu dist[v]≤dist[u]+w cho mọi cạnh reachable, mâu thuẫn. Vậy có chu trình âm reachable.

Ngược lại, một chu trình âm reachable cho phép giảm chi phí không giới hạn tới các đỉnh trong chu trình, nên không thể đạt trạng thái toàn bộ các cạnh reachable đều thỏa điều kiện không cải thiện. Lượt kiểm tra n sẽ phát hiện ít nhất một khả năng relax.

**Ý nghĩa:** đây là tiêu chuẩn chính xác cho câu hỏi “có chu trình âm reachable từ nguồn không?”, không phải tiêu chuẩn cho câu hỏi “đồ thị có chu trình bất kỳ không?” hoặc “đồ thị có chu trình âm ở bất kỳ thành phần nào không?”.

## 13. Chứng minh việc gán -INF cho các đỉnh downstream

Cần đảm bảo cả hai chiều: không **bỏ sót** đỉnh có chi phí -∞ và không **đánh dấu nhầm** đỉnh hữu hạn.

**Chiều không bỏ sót:** có chu trình âm C tới được từ s, và đỉnh v đi tới được từ C. Có thể đi tới C, lặp chu trình để giảm chi phí tùy ý, rồi đi từ C tới v. Vì vậy v thật sự có chi phí -∞. Sau n-1 lượt, ít nhất một cạnh trong miền chịu ảnh hưởng của C còn relax được; các đích cạnh như vậy được seed, rồi BFS theo hướng cạnh sẽ đi tới mọi đỉnh ở downstream có thể bị ảnh hưởng.

**Chiều không đánh dấu nhầm:** một đỉnh được seed chỉ khi một cạnh reachable còn cải thiện sau n-1 lượt. Theo nguyên lý n-1 lượt, cải thiện này là hệ quả của đường sử dụng chu trình âm reachable, nên đỉnh seed nằm trong vùng đi tới được từ một chu trình âm reachable. Mọi đỉnh lan truyền từ seed cũng nằm trong vùng ấy. Vì thế không đỉnh không chịu ảnh hưởng nào bị đưa vào affected.

Tổng hợp: boolean negativeInfinity[v] đúng chính xác khi tồn tại chu trình âm C với s⇝C và C⇝v.

Nếu graph có nhiều chu trình âm reachable nằm ở nhiều nhánh, cần **seed tất cả đích cạnh relax được**, không chỉ một cạnh đầu tiên; như vậy mới đánh dấu đủ những vùng downstream khác nhau. Hàm Java đã quét toàn bộ edges để seed trước khi lan truyền.

**Không đồng nhất -INF với giá trị số nhỏ nhất của kiểu dữ liệu.** -INF là một phân loại toán học; trong code, boolean[] biểu diễn điều kiện, không phải Long.MIN_VALUE hoặc một BigInteger hữu hạn nào.

## 14. Độ phức tạp thời gian và bộ nhớ

Đặt V=n là số đỉnh, E=m là số cạnh có hướng.

**Bellman–Ford chuẩn:** tối đa V-1 lượt, mỗi lượt duyệt E cạnh, nên:

~~~text
Time = O(V * E)
Extra space = O(V) cho dist va parent,
              neu edges da duoc cung cap san.
~~~

Nếu tính cả dữ liệu đầu vào thì lưu danh sách cạnh O(E). Đối với đồ thị không có chu trình âm reachable và cạnh được sắp thuận lợi, early stopping có thể giảm số lượt thực tế, nhưng **không thay đổi cận trên xấu nhất** O(VE).

**Bước phát hiện và lan truyền -INF:** quét cạnh phát hiện O(E), rồi BFS/DFS trên adjacency list O(V+E). Để lan truyền cần danh sách cạnh đi ra O(V+E), có thể được dựng từ danh sách edges.

**Bước dựng witness:** một lượt relax trên bản sao O(E) và n lần lần theo predecessor O(V), cộng thời gian lấy lại chu trình O(V). Tổng vẫn là **O(VE+V+E)**, thường viết O(VE) khi V và E đủ lớn, cộng chi phí đọc input.

**Bộ nhớ của bản demo:**

- O(V) cho dist, parent, affected, probe, pred, queue và kết quả witness.
- O(V+E) cho adjacency list phục vụ propagation.
- O(E) cho danh sách cạnh đầu vào.

Do dùng **BigInteger**, mỗi phép cộng và so sánh còn tốn tài nguyên theo số bit. Phát biểu O(VE) thường giả định phép toán trọng số là O(1). Với trọng số BigInteger nhiều bit, phải tính thêm chi phí số học; đổi lại tránh tràn số và sai kết quả do sentinel.

### So sánh với Dijkstra

Dijkstra dùng priority queue thường có O((V+E) log V) thời gian trên đồ thị thưa với trọng số không âm, có thể nhanh hơn Bellman–Ford đáng kể. Nhưng với cạnh âm, Dijkstra không có bảo đảm đúng của thuật toán chuẩn.

Nếu đồ thị có chu trình âm reachable và cần phân loại đỉnh -INF, Bellman–Ford cung cấp cách xử lý tự nhiên; Dijkstra không được thiết kế cho trường hợp này.

## 15. So sánh với BFS, DAG shortest path, SPFA và Johnson

| Phương pháp | Trọng số hỗ trợ | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| BFS | Không trọng số hoặc mọi cạnh cùng chi phí | O(V+E), đơn giản | Không tối ưu tổng trọng số tùy ý |
| 0–1 BFS | Mỗi cạnh có trọng số 0 hoặc 1 | O(V+E) với deque | Không dùng cho trọng số âm/khác 0,1 |
| Dijkstra | Trọng số không âm | Hiệu quả trên đồ thị thưa | Không dùng chuẩn cho cạnh âm |
| Bellman–Ford | Dương, 0 và âm | Phát hiện negative-cycle reachable | O(VE) trường hợp xấu |
| Shortest path trên DAG | Có thể có cạnh âm | Topo + relax O(V+E) | Chỉ đúng khi graph là DAG |
| SPFA | Cạnh có thể âm | Thường cải thiện thực tế ở một số graph | Có trường hợp xấu rất chậm; cần kiểm negative cycle đúng |
| Johnson | Cạnh có thể âm nếu graph không có chu trình âm | Hữu ích cho nhiều truy vấn/all-pairs trên graph thưa | Cần Bellman–Ford tìm thế năng; không áp dụng nếu có chu trình âm |

### Cạnh âm không đồng nghĩa chắc chắn có chu trình âm

Một DAG có thể chứa rất nhiều cạnh âm mà vẫn **không có chu trình nào**, nên hoàn toàn có khoảng cách ngắn nhất hữu hạn trên mọi đỉnh reachable. Với DAG, thuật toán đường ngắn nhất theo **thứ tự tô-pô** thường nhanh hơn Bellman–Ford.

Bellman–Ford là công cụ tổng quát khi cạnh có thể âm và graph có thể chứa chu trình. Không nên dùng nó chỉ vì “graph có trọng số” nếu trọng số không âm và Dijkstra phù hợp hơn.

### SPFA và ngộ nhận về độ phức tạp

SPFA dùng queue để chỉ relax cạnh đi ra từ các đỉnh vừa được cải thiện; nhiều dữ liệu thực tế chạy nhanh. Nhưng không có bảo đảm luôn nhanh; có những graph khiến SPFA rất chậm (có thể xấu tới bậc tương đương nhiều lượt relax). Nếu dùng SPFA, thuật toán phát hiện chu trình âm phải có chứng minh cẩn thận; đếm số lần enqueue đơn giản không phải lúc nào cũng là bằng chứng đúng theo mọi biến thể implementation.

### Johnson dùng Bellman–Ford làm bước tiền xử lý

Trong Johnson all-pairs shortest paths, thêm một **super-source** nối mọi đỉnh bằng cạnh trọng số 0, chạy Bellman–Ford để lấy thế năng h[v]. Nếu có chu trình âm, việc tái trọng số đúng để dùng Dijkstra bị ngăn cản. Nếu không có chu trình âm, tái trọng số w'(u,v)=w(u,v)+h[u]-h[v] sẽ không âm; sau đó chạy Dijkstra từ nhiều nguồn.

Đây là ứng dụng khác của Bellman–Ford, không làm thay đổi quy tắc phân loại -INF của bài đơn nguồn.

## 16. Super-source và phát hiện chu trình âm ở bất cứ đâu

Bellman–Ford đơn nguồn chỉ phát hiện chu trình âm **reachable từ nguồn đã chọn**. Nếu đề chỉ hỏi “**đồ thị có tồn tại chu trình âm ở bất kỳ thành phần nào không?**” thì kết quả chạy từ một nguồn có thể bỏ sót chu trình trong thành phần khác.

Một cách giải an toàn:

1. Tạo một **siêu nguồn S** mới.
2. Thêm cạnh trọng số 0 từ S tới **mọi đỉnh gốc**.
3. Chạy Bellman–Ford trên graph mở rộng với V+1 đỉnh, nguồn S.
4. Vì mọi đỉnh gốc đều reachable từ S, bất kỳ chu trình âm nào trong graph gốc cũng trở thành reachable và sẽ được phát hiện.

Một cách tương đương nếu chỉ cần phát hiện tồn tại chu trình âm toàn graph: khởi tạo dist[v]=0 cho mọi đỉnh rồi chạy V lượt relax. Điều này tương đương cho phép một siêu nguồn có cạnh 0 đến mọi đỉnh mà không cần thực sự tạo thêm đỉnh.

**Đừng trộn hai câu hỏi:**

- Từ một source s cụ thể, đỉnh nào bị -INF? Phải chỉ seed source s; chu trình âm không reachable từ s không ảnh hưởng kết quả.
- Ở bất kỳ đâu trong graph có chu trình âm không? Dùng super-source hoặc tương đương.

### Nhiều nguồn và một số nguồn bị chu trình âm

Nếu đề có tập các nguồn, tất cả bắt đầu với chi phí ban đầu 0, có thể tạo siêu nguồn nối vào từng nguồn tương ứng. Khi đó mức -INF là những đỉnh có thể đi tới từ **ít nhất một chu trình âm reachable từ một nguồn trong tập**.

Nếu mỗi nguồn có **chi phí ban đầu khác nhau**, trọng số cạnh nối từ siêu nguồn phải phản ánh các chi phí đó; không được seed tất cả 0 nếu đề cho điểm khởi hành khác nhau. Khi có cạnh trọng số âm và nhiều nguồn, super-source giúp thống nhất mô hình nhưng phải giữ đúng ý nghĩa trọng số.

## 17. Những lỗi thường gặp trong cài đặt

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Relax từ đỉnh INF | Đường không tồn tại bị xem là hợp lệ | Kiểm tra reachable trước khi cộng |
| Dùng INF sentinel quá nhỏ | Một đường thật lớn hơn INF bị coi như unreachable | BigInteger/null, hoặc miền sentinel có chứng minh |
| Cộng long gây tràn | Sai thứ tự so sánh và kết quả | BigInteger hoặc Math.addExact kèm xử lý |
| Nhầm cạnh u→v với v→u | Tính trên graph sai hướng | Giữ đúng directed edge |
| Chỉ chạy một lượt relax | Bỏ đường dài hoặc cạnh nhập ngược | Tối đa V-1 lượt |
| Chạy V lượt rồi in số hữu hạn dù có cycle | Công bố giá trị tạm là tối ưu | Phát hiện/lan truyền -INF |
| Kiểm chu trình âm ở vùng unreachable | False positive trong bài đơn nguồn | Chỉ xét dist[u] reachable |
| Coi mọi negative edge là negative cycle | Báo lỗi trên DAG có cạnh âm | Kiểm lượt thứ V |
| Coi mọi đỉnh reachable là -INF khi có một cycle | Đánh dấu nhầm nhánh an toàn | Chỉ lan truyền từ cycle reachable |
| Chỉ đánh dấu đỉnh trực tiếp được relax ở lượt V | Thiếu đỉnh downstream xa hơn | BFS/DFS lan truyền theo hướng cạnh |
| Chỉ seed một cycle dù có nhiều cycle khác nhau | Có thể thiếu vùng -INF | Quét mọi cạnh relax được |
| In parent path khi target=-INF | Trả một đường không tối ưu | Phân loại status trước khi restore |
| Dùng parent=-1 để nói unreachable | Nhầm nguồn hữu hạn với unreachable | Dùng dist/status |
| Đổi thứ tự cạnh rồi mong số passes cố định | Test sai giả | Kiểm giá trị toán học, không giả định thứ tự |
| Chỉ dùng BigInteger mà quên kiểm unreachable | Gặp null/giá trị giả | Dùng null guard |
| Không chứng minh early stop | Dừng trước khi đường mới lan tới đích | Chỉ dừng khi cả lượt không đổi |
| Nhầm walk với đường đi đơn | Lập luận -INF sai | Chu trình âm cần được phép lặp trong walk |
| Graph vô hướng có cạnh âm mà vẫn đòi finite shortest walk | Có thể đi qua lại cạnh âm vô hạn lần | Nêu rõ mô hình hoặc điều kiện cạnh |
| DFS witness không nhảy V lần qua parent | Nhận đỉnh downstream thay chu trình | Nhảy V lần rồi mới lặp |
| Không xác thực parentEdge khi có cạnh song song | Sai tổng trọng số nhân chứng | Lưu id cạnh được relax |
| Không phân biệt global và single-source cycle | Bỏ sót cycle rời nguồn hoặc báo nhầm | Chọn super-source đúng câu hỏi |

**Lỗi kiến thức nguy hiểm nhất:** “Có cạnh âm nên Dijkstra không chạy được, vậy Bellman–Ford luôn trả một số”. Thực tế Bellman–Ford có thể phát hiện rằng **không có giá trị nhỏ nhất hữu hạn** do chu trình âm reachable. Khi ấy kết quả phải phản ánh **-INF** hoặc báo điều kiện lỗi tùy yêu cầu bài.

## 18. Kiểm thử tính chất và đối chứng độc lập

### Kiểm thử trên graph không có chu trình âm reachable

- dist[source]=0 nếu source không bị ảnh hưởng -INF.
- Mỗi đỉnh reachable hữu hạn có một đường thật từ source với tổng chi phí đúng dist[v].
- Với mọi cạnh u→v mà cả hai đỉnh có khoảng cách hữu hạn và u reachable, **dist[v] ≤ dist[u] + w(u,v)**. Nếu v affected, bất đẳng thức trên số hữu hạn không áp dụng theo cùng cách.
- Với các đỉnh có parent hợp lệ, cạnh parent[v]→v phải tồn tại, và đường khôi phục hợp lệ, đúng hướng.
- Một đỉnh không có đường từ source phải có status UNREACHABLE và không bị affected.
- Đổi thứ tự edges có thể đổi passes/parent, nhưng không đổi **kết quả trạng thái và khoảng cách ngắn nhất**.
- Một DAG có trọng số âm phải khớp với shortest path bằng topo relax độc lập.

### Kiểm thử chu trình âm reachable

- Graph có chu trình 1→2→3→1 tổng -3; tất cả đỉnh đi tới từ chu trình phải -INF.
- Những đỉnh reachable **không** đi tới từ chu trình có thể vẫn FINITE.
- Một cycle witness phải khép kín, mỗi cặp đỉnh liên tiếp là cạnh có hướng thực tế, và với các cạnh được chọn thì tổng trọng số âm.
- Với một self-loop trọng số âm reachable, witness có thể là [v,v].
- Chu trình âm trong thành phần rời nguồn **không** làm thay đổi kết quả đơn nguồn.
- Khi có hai chu trình âm reachable ở hai nhánh, cả hai vùng downstream đều phải được đánh dấu, dù witness chỉ chứa một chu trình.

### Các ca chuẩn

| Dữ liệu | Kết quả mong đợi |
| --- | --- |
| Graph 6 đỉnh của phần 5 | [0,4,2,5,7,INF] |
| Graph 7 đỉnh có cycle -3 của phần 6 | [0,-INF,-INF,-INF,-INF,-INF,10] |
| Cycle reachable 1→2→3→1 | Một witness [1,2,3,1] |
| Graph có cycle 2↔3 nhưng không tới từ 0 | [0,3,INF,INF,INF] |
| Self-loop 1→1 trọng số -1 reachable từ 0 | [0,-INF] và witness [1,1] |
| Một đỉnh s, không có cạnh | [0], không có cycle |
| Một đỉnh s, self-loop w=0 | [0], không có cycle âm |
| Một đỉnh s, self-loop w=-1 | [-INF], cycle [s,s] |
| Graph có hai cạnh song song u→v | Relax từng cạnh và chọn chi phí nhỏ nhất |
| Chỉ có các cạnh không âm | Đối chứng với Dijkstra |
| Graph là DAG có cả cạnh âm | Đối chứng với topo shortest path |
| n=0 hoặc source ngoài miền ở API demo | Từ chối đầu vào |
| Một cạnh với endpoint ngoài [0,n) | Từ chối đầu vào |
| Trọng số long rất lớn trên nhiều cạnh | Tổng không bị tràn nhờ BigInteger |

### Đối chứng Floyd–Warshall trên graph nhỏ

Với V≤8, có thể tính tất cả khoảng cách đường đi bằng Floyd–Warshall, dùng số nguyên đủ rộng hoặc BigInteger có trạng thái INF rõ ràng. Sau khi relax, một đỉnh k có distAll[k][k]<0 chứng tỏ có chu trình âm đi tới được từ k và quay lại k.

Đối với nguồn s và đích v, -INF xảy ra khi tồn tại k với:

~~~text
reachable(s,k)
AND distAll[k][k] < 0
AND reachable(k,v)
~~~

Nếu không có k như vậy và v reachable, khoảng cách hữu hạn được so với giá trị từ Bellman–Ford. Nếu không reachable, hai phương pháp phải cùng cho INF.

Đây là một oracle **độc lập về cách hiện thực** so với relax V-1 lượt và BFS đánh dấu affected; rất hữu ích để phát hiện lỗi chỉ đánh dấu một cycle hoặc bỏ sót đỉnh downstream.

### Kiểm thử ngẫu nhiên

Sinh các đồ thị nhỏ với trọng số trong [-5,5], bao gồm cả self-loop, cạnh song song và các thành phần không liên thông. Chạy Bellman–Ford từ từng nguồn rồi so kết quả ba trạng thái với oracle Floyd–Warshall. Kiểm tra riêng path hữu hạn theo tổng trọng số cạnh.

Để tránh false alarm khi có nhiều path tối ưu, không nên bắt buộc parent/path phải đúng **một** chuỗi cố định trừ khi bài quy định tie-breaking. Cần kiểm tra chiều cạnh, tổng chi phí và tính hữu hạn của kết quả.

## 19. Bài tập tự luyện

1. Với các cạnh 0→1 (4), 0→2 (5), 1→2 (-2), tính dist và parent sau từng phép relax. Giải thích vì sao đường qua 1 ngắn hơn cạnh trực tiếp.
2. Đổi thứ tự các cạnh của graph 6 đỉnh ở phần 5 theo chiều ngược. Tính số lượt cần relax; chứng minh kết quả cuối không đổi.
3. Viết Bellman–Ford với **hai mảng prev/next** theo từng lượt, chứng minh D_k biểu diễn đường đi có tối đa k cạnh và so với bản in-place.
4. Với n=5 và một chuỗi 0→1→2→3→4, hãy sắp thứ tự edges khiến thông tin đi từ 0 đến 4 chậm nhất. Vì sao cần tối đa V-1 lượt?
5. Với chu trình 1→2 (+2), 2→3 (+2), 3→1 (-7), tính tổng trọng số và giải thích chính xác vì sao chi phí tới các đỉnh downstream có thể giảm không giới hạn.
6. Bổ sung cạnh 5→0 vào graph negative-cycle của phần 6. Giải thích vì sao **nguồn 0 cũng trở thành -INF** sau khi có đường từ cycle quay về 0.
7. Tạo một graph có hai chu trình âm reachable ở hai nhánh không nối nhau. Tại sao chỉ seed một cạnh relax có thể bỏ sót vùng affected còn lại?
8. Dùng graph có chu trình âm rời nguồn, so Bellman–Ford đơn nguồn với biến thể super-source. Hai câu hỏi cho kết luận khác nhau ra sao?
9. Viết hàm pathTo chỉ nhận đỉnh có status FINITE; với UNREACHABLE trả [], với NEGATIVE_INFINITY báo lỗi rõ ràng. Kiểm thử cả ba trường hợp.
10. Mở rộng API để in **tên đỉnh** thay vì id, dùng bảng ánh xạ tên→id và danh sách ngược. Không thay đổi ngữ nghĩa hướng cạnh.
11. Bổ sung lưu parentEdge để chu trình witness vẫn xác minh được **tổng chi phí âm** khi có cạnh song song khác trọng số.
12. Dùng BigInteger trong Java để kiểm thử đường nhiều cạnh có trọng số gần Long.MAX_VALUE. So với một phiên bản dùng long không có kiểm tra overflow.
13. Với đồ thị vô hướng và một cạnh có trọng số -4, mô tả hai cung tương đương và giải thích vì sao chi phí walk ngắn nhất có thể -INF cho những đỉnh reachable từ cung đó.
14. Dùng DAG shortest path theo topo làm oracle cho Bellman–Ford trên đồ thị không chu trình có trọng số âm; phân tích O(V+E) so với O(VE).
15. Cài đặt một phép kiểm tính đúng: khi một đỉnh FINITE, path khôi phục phải có số bước hữu hạn, mọi cạnh đúng hướng và tổng trọng số bằng dist.
16. Tạo bộ test ngẫu nhiên n≤8 và so Bellman–Ford với Floyd–Warshall, bao gồm các trường hợp negative cycle chỉ ảnh hưởng một phần đồ thị.
17. Phân tích điều kiện cần để early stopping hợp lệ. Nếu một lượt không có relax, liệu lượt kế tiếp có thể có relax không? Giải thích bằng bất biến.
18. Từ một cycle witness, tìm tất cả đỉnh reachable theo cạnh đi ra bằng BFS. Tại sao muốn đánh dấu đủ -INF khi có **nhiều cycle âm không liên thông với nhau**, có thể cần nhiều hạt giống?
19. Giải thích vì sao Bellman–Ford không phải “BFS có trọng số”, dù cả hai đều có thể duyệt danh sách cạnh và cập nhật thông tin đường đi.
20. Cho một graph có các chu trình trọng số dương, bằng 0 và âm. Phân biệt tác động của từng loại đối với sự tồn tại của đường ngắn nhất hữu hạn từ nguồn.

## 20. Checklist áp dụng và kết luận

Trước khi chọn Bellman–Ford cho một bài toán:

- Xác định **đồ thị có hướng hay vô hướng**, ý nghĩa mỗi cạnh, trọng số có thể âm không.
- Xác định đề hỏi **một nguồn**, nhiều nguồn hay **chu trình âm ở bất cứ đâu**.
- Nếu có cạnh âm và graph không phải DAG, Bellman–Ford là lựa chọn chuẩn cho đường ngắn nhất đơn nguồn.
- Khởi tạo đúng source=0, các đỉnh khác unreachable; **không relax từ INF**.
- Duyệt tối đa V-1 lượt; chỉ early stop nếu **cả lượt** không có cập nhật.
- Kiểm **lượt thứ V** để phát hiện negative-cycle reachable nếu bài cần xử lý chu trình âm.
- Nếu trả lời từng đỉnh, **seed tất cả cạnh còn relax được và lan truyền -INF** theo cạnh đi ra.
- Với đỉnh FINITE, dùng parent để khôi phục một đường tối ưu; với -INF, **không** giả vờ có đường hữu hạn nhỏ nhất.
- Nếu dùng long và INF sentinel, kiểm toán **tràn số, dấu và miền trọng số**; có thể dùng BigInteger và null như mã học tập.
- Phân biệt **chu trình âm reachable** với chu trình âm không tới được, và phân biệt **chu trình âm** với cạnh âm đơn lẻ.
- Kiểm thử ca negative cycle, self-loop, disconnected, parallel edge, multiple cycles, source bị ảnh hưởng và đường tối ưu không duy nhất.

**Kết luận:** Bellman–Ford nới lỏng tất cả các cạnh tối đa V-1 lượt để tìm đường đi ngắn nhất kể cả khi có **trọng số âm**. Một lượt bổ sung phát hiện **chu trình âm đi tới được từ nguồn**; lan truyền từ các đỉnh còn cải thiện sẽ xác định chính xác những đỉnh có giá trị **-INF**. Với những đỉnh không chịu ảnh hưởng chu trình âm, thuật toán vẫn có thể trả khoảng cách hữu hạn và dựng một đường ngắn nhất. Cốt lõi là hiểu rõ phép relax, chứng minh giới hạn V-1 cạnh và **không đánh đồng** unreachable, finite và negative infinity.

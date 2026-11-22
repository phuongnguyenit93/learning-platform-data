# Thuật toán Edmonds–Karp

## 1. Bài toán luồng cực đại trong mạng có hướng

**Edmonds–Karp** là một cách cài đặt cụ thể của phương pháp **Ford–Fulkerson** để tìm **luồng cực đại (maximum flow)** trên mạng có hướng. Điểm phân biệt là Edmonds–Karp luôn chọn **đường tăng luồng ngắn nhất theo số cạnh bằng BFS trên mạng dư (residual network)**. Quy tắc BFS tạo ra bảo đảm thời gian đa thức **O(VE²)**, không phụ thuộc độ lớn số học của giá trị luồng.

Một mạng luồng G=(V,E) gồm:

- Tập đỉnh V và các **cạnh có hướng** E.
- Mỗi cạnh (u,v) có **sức chứa (capacity)** c(u,v) **không âm**.
- Một đỉnh nguồn s (source) và một đỉnh đích t (sink), **s khác t**.
- Luồng f cho biết lượng hàng/dữ liệu/nước gửi trên từng cạnh, với ràng buộc sức chứa và bảo toàn dòng.

Bài toán: tìm **lượng luồng ròng lớn nhất** từ s đến t sao cho không vi phạm bất kỳ sức chứa và điều kiện bảo toàn nào.

Ví dụ ứng dụng: số gói có thể đi qua hệ thống truyền tải, lưu lượng qua ống dẫn, tối đa số đơn hàng có thể vận chuyển qua các tuyến, hay công đoạn ghép cặp hai phía thông qua mạng luồng. Edmonds–Karp giúp trả lời “có thể chuyển tối đa bao nhiêu đơn vị từ s đến t?”, không phải “đường đi nào ngắn nhất?” hoặc “tổng chi phí vận chuyển nhỏ nhất là bao nhiêu?”.

### Mô hình một luồng khả thi

Với mỗi cạnh gốc e=(u,v) có capacity c(e), mô hình lưu luồng không âm riêng trên từng cạnh:

~~~text
0 <= f(e) <= c(e)
~~~

Với mọi đỉnh v khác s,t, tổng luồng đi vào phải bằng tổng luồng đi ra:

~~~text
SUM incoming f(e) = SUM outgoing f(e)
~~~

Giá trị luồng bằng **luồng ròng rời nguồn**:

~~~text
value(f)
  = SUM flow(s -> x) - SUM flow(x -> s)
  = SUM flow(x -> t) - SUM flow(t -> x)
~~~

Biểu thức có trừ luồng ngược về nguồn hoặc rời đích nếu mạng có các cạnh như vậy. Trong nhiều ví dụ đơn giản không có cạnh đi vào s hoặc đi ra t, nên giá trị luồng chỉ là tổng dòng rời s.

### Capacity không phải cost

Sức chứa 10 nghĩa là một cạnh chuyển được nhiều nhất 10 đơn vị luồng; nó **không** phải trọng số dài 10 hoặc chi phí 10. Thuật toán Edmonds–Karp tối ưu **lượng luồng**, không tối ưu tổng chi phí. Bài **min-cost max-flow** là bài toán khác, cần lưu cả capacity và cost rồi dùng các thuật toán riêng.

## 2. Trực giác: tăng luồng dọc đường s→t

Ban đầu cho tất cả luồng trên các cạnh bằng 0. Nếu vẫn có một đường từ s tới t mà mỗi cạnh còn khả năng chuyển thêm một lượng dương, ta có thể **tăng luồng** trên toàn đường.

Đối với đường P, lượng tối đa có thể tăng trong một lần là:

~~~text
bottleneck(P) = MIN residualCapacity(e)
                voi moi canh tren P.
~~~

Đây là **nút thắt cổ chai** của đường. Nếu một cạnh chỉ còn 3 đơn vị dư trong khi những cạnh khác còn 8 và 20, ta chỉ có thể tăng **3** đơn vị qua cả đường.

Ví dụ:

~~~text
s --(8)--> a --(3)--> b --(20)--> t
~~~

Lần đầu trên đường ấy, bottleneck=min(8,3,20)=3. Sau khi tăng 3, cạnh a→b đã hết khả năng chuyển tiếp theo chiều đó, nên ta phải tìm đường khác nếu muốn tăng thêm.

**Vấn đề quan trọng:** việc tăng luồng sớm dọc một đường đôi khi tạo lựa chọn chưa tốt cho những lần sau. Thuật toán phải có khả năng **điều chỉnh hoặc hủy một phần luồng đã gửi trên cạnh** để phân phối lại hiệu quả. Mạng dư và cạnh ngược giải quyết vấn đề này.

## 3. Mạng dư (residual graph) là gì?

Mạng dư G_f phản ánh **những thay đổi luồng còn có thể thực hiện** khi đã có luồng hiện tại f.

Với một **cạnh gốc có hướng** u→v, sức chứa c và luồng hiện tại f:

- **Cạnh dư xuôi u→v:** khả năng chuyển thêm là c-f.
- **Cạnh dư ngược v→u:** khả năng **giảm bớt luồng cũ** trên u→v là f.

Đây là một **cặp cạnh dư có liên kết** trong cấu trúc dữ liệu. Ví dụ cạnh gốc có capacity 10 đang mang flow 6:

~~~text
Original:
    u --capacity 10, flow 6--> v

Residual:
    u --remaining 4--> v
    v --remaining 6--> u
~~~

Nếu đi tiếp 2 đơn vị trên cạnh dư **xuôi**, flow gốc tăng từ 6 lên 8, dư xuôi giảm xuống 2 và dư ngược tăng lên 8.

Nếu đường tăng luồng đi theo cạnh dư **ngược** v→u với lượng 2, ta thực chất giảm flow gốc từ 6 xuống 4, dư xuôi tăng lại thành 6 và dư ngược giảm xuống 4.

### Quy tắc cập nhật residual

Với cạnh dư e=u→v đang có remaining≥delta, và cạnh đảo e.rev=v→u thuộc cùng cặp:

~~~text
e.remaining     -= delta
reverse.remaining += delta
~~~

**Hai thay đổi phải xảy ra cùng nhau**. Nếu chỉ giảm remaining xuôi mà không tăng cạnh ngược, thuật toán mất khả năng sửa luồng cũ và có thể kẹt ở lời giải chưa cực đại.

### Đừng nhầm cạnh ngược dư với cạnh gốc đi ngược

Nếu input ban đầu cũng có một cạnh **v→u** độc lập với capacity riêng, nó phải có **cặp cạnh dư riêng**. Do đó adjacency list tại v có thể chứa nhiều cung v→u:

1. Một cung ngược dư để hủy luồng trên cạnh gốc u→v.
2. Một cung xuôi dư của **cạnh gốc v→u**.
3. Các cung khác nếu input chứa cạnh song song.

Chúng có thể cùng đỉnh đầu/cuối nhưng **không cùng ý nghĩa**, không được chỉ gộp bừa nếu cần truy vết từng luồng gốc.

## 4. Cấu trúc dữ liệu residual bằng danh sách kề

Cài đặt hiệu quả lưu mỗi cạnh dư thành một đối tượng:

~~~text
Edge {
    to: đỉnh đích
    rev: chỉ số của cạnh đảo trong adj[to]
    remaining: sức chứa dư hiện tại
}
~~~

Khi thêm một cạnh gốc u→v capacity c≥0, với u!=v:

~~~text
forward = Edge(to=v,
               rev=index of reverse in adj[v],
               remaining=c)

reverse = Edge(to=u,
               rev=index of forward in adj[u],
               remaining=0)

adj[u].add(forward)
adj[v].add(reverse)
~~~

Mỗi cạnh gốc tạo **hai đối tượng residual**, nên nếu graph gốc có E cạnh, residual adjacency có O(E) cạnh đối tượng.

### Chỉ số rev giúp làm gì?

Khi BFS hoặc đường tăng luồng dùng cạnh e trong adj[u], ta biết cạnh đảo chính xác nằm tại:

~~~text
adj[e.to].get(e.rev)
~~~

Không phải tìm kiếm bằng cách quét toàn bộ danh sách kề, cũng không nhầm cạnh song song. Việc cập nhật một cặp cạnh dư theo rev vì thế tốn O(1).

### Self-loop

Một self-loop u→u **không bao giờ giúp tăng luồng ròng từ s sang t**: thêm luồng quanh chính đỉnh ấy không làm chuyển lượng giữa các đỉnh khác nhau. Trong mã Java, self-loop được **bỏ qua khi tạo residual** sau khi kiểm tra capacity và endpoint; nó không ảnh hưởng max flow hay min cut.

Nếu muốn lưu self-loop vì mục tiêu kiểm toán luồng hoặc xử lý mô hình khác, cần cài đặt cặp rev cẩn thận vì hai cạnh nằm **cùng một adjacency list**. Viết addEdge cho u==v mà không xét hai chỉ số sẽ dễ trỏ nhầm cạnh đảo.

### Capacity bằng 0

Cạnh có capacity=0 vẫn có thể hiện diện trong input và residual, nhưng BFS **không thể đi qua cạnh dư remaining=0**. Các cạnh như vậy không góp luồng. Mã mẫu chỉ hiển thị **các cạnh gốc capacity dương** trong danh sách cạnh cắt để output gọn; capacity 0 không thay đổi tổng cắt.

## 5. BFS tìm đường tăng luồng theo số cạnh

Điểm cốt lõi của Edmonds–Karp là **BFS trên residual graph**, không phải BFS trên chỉ những cạnh gốc.

BFS được phép đi qua một cạnh dư e nếu và chỉ nếu:

~~~text
e.remaining > 0
~~~

BFS bắt đầu tại s. Mỗi khi khám phá đỉnh v từ u qua cạnh dư e, lưu:

~~~text
prevVertex[v] = u
prevEdgeIndex[v] = vi tri cua e trong adj[u]
~~~

Lưu **chỉ số cạnh**, không chỉ đỉnh cha, vì input có thể chứa nhiều cạnh song song hoặc cả hai chiều giữa một cặp đỉnh.

Giả mã:

~~~text
bfsResidual(s,t):
    prevVertex = [-1] * V
    prevEdge = [-1] * V

    queue.add(s)
    prevVertex[s] = s

    while queue not empty:
        u = queue.removeFirst()
        for index i and edge e in adj[u]:
            if e.remaining <= 0:
                continue
            if prevVertex[e.to] != -1:
                continue

            prevVertex[e.to] = u
            prevEdge[e.to] = i
            queue.addLast(e.to)

            if e.to == t:
                return FOUND

    return NOT_FOUND
~~~

BFS với queue FIFO bảo đảm đường vừa tìm có **ít cạnh dư nhất**, không phải tổng capacity nhỏ nhất hay trọng số bé nhất. Mỗi lượt BFS duyệt O(V+E) đối tượng, kể cả cạnh ngược dư.

### Dựng ngược đường từ t về s

Nếu BFS tới được t, ta dùng prevVertex và prevEdgeIndex để dựng đường:

~~~text
v = t
bottleneck = +INF

while v != s:
    u = prevVertex[v]
    e = adj[u][prevEdgeIndex[v]]
    bottleneck = min(bottleneck, e.remaining)
    v = u
~~~

Sau khi có bottleneck, đi ngược đường một lần nữa để cập nhật e và e.rev. Tổng độ dài đường không vượt V-1 cạnh vì BFS đánh dấu mỗi đỉnh một lần.

**Chú ý:** BFS đang chạy trên **trạng thái dư mới nhất sau các lần augment**. Không được tính một BFS duy nhất rồi dùng đi dùng lại đường cũ mà không kiểm tra remaining.

## 6. Pseudocode đầy đủ của Edmonds–Karp

~~~text
edmondsKarp(G, source, sink):
    validate source != sink
    validate every original capacity >= 0
    build residual adjacency with paired reverse edges

    maxFlow = 0

    loop:
        run BFS on residual arcs with remaining > 0
        if sink not reached:
            break

        delta = minimum remaining on the found s->t path

        v = sink
        while v != source:
            u = prevVertex[v]
            edge = adj[u][prevEdgeIndex[v]]
            reverse = adj[v][edge.rev]

            edge.remaining -= delta
            reverse.remaining += delta

            v = u

        maxFlow += delta

    sourceSide = vertices reachable from source
                 using positive residual arcs

    minCut = original directed edges u->v
             with u in sourceSide and v outside sourceSide

    return maxFlow, minCut
~~~

Không cần đặt một cận tùy ý cho số lần lặp. Quy tắc BFS và định lý độ phức tạp bảo đảm Edmonds–Karp kết thúc sau số lần tăng luồng bị chặn bởi O(VE), khi V,E hữu hạn.

### Lượng luồng tăng bao nhiêu sau mỗi lần?

Nếu bottleneck=delta>0, thì giá trị luồng tăng đúng delta, dù đường augment có thể chứa cạnh ngược. Mọi đỉnh bên trong đường có một cạnh residual đi vào và một cạnh residual đi ra, nên tổng luồng ròng tại các đỉnh trung gian vẫn cân bằng. Ở source luồng ròng rời đi tăng delta, và tại sink luồng ròng nhận được tăng delta.

### Khi nào dừng?

Khi BFS **không còn đường s→t** chỉ qua các cạnh dư remaining>0. Đây là điều kiện tối ưu toàn cục, không phải chỉ “không còn cạnh gốc nào đủ capacity”.

Nếu chỉ tìm đường trên các cạnh gốc mà bỏ reverse arcs, thuật toán có thể dừng quá sớm với luồng chưa cực đại.

## 7. Ví dụ mạng chuẩn sáu đỉnh: max flow = 23

Xét mạng có hướng với source=0, sink=5 và các cạnh capacity:

~~~text
0 -> 1 : 16
0 -> 2 : 13
1 -> 2 : 10
2 -> 1 :  4
1 -> 3 : 12
3 -> 2 :  9
2 -> 4 : 14
4 -> 3 :  7
3 -> 5 : 20
4 -> 5 :  4
~~~

Các cạnh 1→2 và 2→1 là **hai cạnh gốc khác nhau**, không nên xóa một cạnh chỉ vì đã thấy cạnh còn lại.

Với thứ tự kề được tạo từ thứ tự input trên, Edmonds–Karp BFS tìm ba đường tăng luồng:

| Lượt | Đường tăng luồng residual | Bottleneck | Tổng luồng sau lượt |
| ---: | --- | ---: | ---: |
| 1 | 0→1→3→5 | 12 | 12 |
| 2 | 0→2→4→5 | 4 | 16 |
| 3 | 0→2→4→3→5 | 7 | 23 |

Sau lượt 1, cạnh 1→3 bão hòa. Sau lượt 2, cạnh 4→5 bão hòa. Sau lượt 3, cạnh 4→3 bão hòa. Không còn đường dư từ 0 tới 5.

**Kết quả maxFlow=23**.

### Kiểm tra lát cắt nhỏ nhất

Trên residual graph cuối cùng, BFS từ source 0 chỉ tới được các đỉnh:

~~~text
S = {0,1,2,4}
T = {3,5}
~~~

Các cạnh gốc đi **từ S sang T**:

~~~text
1 -> 3 : 12
4 -> 3 :  7
4 -> 5 :  4
~~~

Tổng sức chứa cut:

~~~text
cutCapacity = 12 + 7 + 4 = 23
~~~

Vì có luồng giá trị 23 và một cut sức chứa 23, định lý **max-flow min-cut** xác nhận **23 là tối ưu**.

Không đưa cạnh 3→2 vào cut S→T vì nó đi **từ T về S**. Định nghĩa capacity(S,T) chỉ cộng các cạnh từ S sang T, không cộng cạnh đi ngược.

### Tập đỉnh S được tính thế nào?

Sau khi ngừng tăng luồng, chạy **BFS/DFS trên mạng dư cuối** từ source, chỉ theo cạnh remaining>0. Không dùng BFS trên cạnh gốc vì cạnh bão hòa có thể tồn tại trong input nhưng **không đi được** theo residual.

Từ S ở đây ta thu được cut rõ ràng bằng các cạnh gốc. Các cạnh băng từ S sang T phải bão hòa, nếu không residual sẽ còn cung capacity dương để BFS đi tới phía T.

## 8. Ví dụ bắt buộc dùng cạnh ngược để sửa luồng cũ

Xét mạng sáu đỉnh, source=0, sink=5, mọi capacity bằng 1:

~~~text
0 -> 1
0 -> 2
1 -> 3
1 -> 4
2 -> 3
3 -> 5
4 -> 5
~~~

Với thứ tự cạnh này, BFS trước tiên tìm:

~~~text
0 -> 1 -> 3 -> 5
delta=1
~~~

Luồng này dùng hết sức chứa trên cạnh 1→3 và 3→5. Để gửi đơn vị thứ hai từ 0 qua 2, ta cần dùng 2→3 nhưng 3→5 đã bão hòa.

Mạng dư lúc này có **cạnh ngược 3→1 capacity 1** do đã đẩy luồng 1 đơn vị trên cạnh gốc 1→3. BFS tiếp theo tìm:

~~~text
0 -> 2 -> 3 -> 1 -> 4 -> 5
delta=1
~~~

Ở đoạn 3→1, thuật toán **hủy 1 đơn vị** đã chạy theo cạnh gốc 1→3, rồi chuyển lượng ấy sang 1→4→5. Luồng cuối có thể nhìn như hai đường gốc:

~~~text
0 -> 1 -> 4 -> 5
0 -> 2 -> 3 -> 5
~~~

Tổng maxFlow=2. Không hề có chuyện luồng “đi ngược thời gian”; reverse edge chỉ biểu diễn một **phép chỉnh sửa hợp lệ của lời giải luồng đang có**.

Nếu một cài đặt chỉ tìm đường trên các cạnh gốc còn dư, nó có thể dừng sau đơn vị đầu vì không tìm được đường tăng thứ hai nếu không được phép hủy phân bổ cũ. Đây là phản ví dụ quan trọng minh họa tại sao cần residual reverse arcs.

## 9. Lát cắt s–t và định lý Max-flow Min-cut

Một **s–t cut** là phép chia V thành hai tập S,T sao cho:

~~~text
source in S
sink in T
S union T = V
S intersect T = empty
~~~

Capacity của cut là tổng sức chứa **các cạnh gốc có hướng từ S tới T**:

~~~text
capacity(S,T) = SUM c(u,v)
                voi u in S va v in T.
~~~

Không cộng cạnh từ T sang S, dù input có cả hai chiều. Không cộng cạnh nội bộ trong S hoặc T. Nếu có nhiều cạnh song song từ S sang T, **cộng sức chứa từng cạnh gốc**.

### Vì sao mọi luồng ≤ sức chứa mọi cut?

Bảo toàn luồng trên các đỉnh bên trong S cho ta:

~~~text
value(flow)
  = total flow(S->T) - total flow(T->S)
  <= total flow(S->T)
  <= capacity(S,T).
~~~

Vì vậy **bất kỳ cut nào cũng là một cận trên** của giá trị luồng khả thi.

### Vì sao cut lấy từ residual khi BFS thất bại là cut tối ưu?

Đặt S là các đỉnh tới được từ s bằng đường residual có capacity dương, T=V\S. BFS dừng nghĩa là t không thuộc S.

Nếu một cạnh gốc u→v có u∈S,v∈T mà remaining xuôi >0, BFS đã có thể đi từ u sang v, mâu thuẫn v∈T. Do đó **mọi cạnh gốc từ S tới T đã bão hòa**. Tương tự, mọi luồng chạy từ T về S phải bằng 0 ở trạng thái tối ưu xét theo các cặp cạnh dư tương ứng; nếu có luồng dương trên cạnh gốc v→u (v∈T,u∈S), cung ngược residual u→v sẽ có capacity dương, mâu thuẫn.

Như vậy luồng ròng qua cut bằng đúng tổng sức chứa cut. Vì mọi luồng bị chặn trên bởi capacity của mọi cut, và luồng hiện tại chạm được cận trên này, đây là **luồng cực đại** và cut cũng là **cut nhỏ nhất**.

Đây là cách thuật toán vừa **tìm một lời giải tối ưu**, vừa cung cấp **chứng cứ tối ưu** kiểm tra được: giá trị maxFlow bằng minCutCapacity.

## 10. Tại sao Edmonds–Karp không bị phụ thuộc độ lớn capacity?

Phương pháp Ford–Fulkerson tổng quát chỉ yêu cầu chọn **một đường tăng luồng bất kỳ**. Khi capacity nguyên, mỗi lần tăng ít nhất 1 và có thể đưa ra cận theo **giá trị luồng tối đa**, tức không mạnh về thời gian nếu capacity rất lớn. Khi capacity thực vô tỉ, chọn đường tùy tiện còn có thể gây những vấn đề về khả năng kết thúc của một số chiến lược.

Edmonds–Karp thay “đường bất kỳ” bằng **đường ngắn nhất theo số cạnh residual** nhờ BFS. Quy tắc này có bất biến cấu trúc giúp giới hạn số lượt tăng luồng theo V,E, thay vì theo tổng capacity.

### Khoảng cách BFS residual không giảm

Gọi dist_f(v) là số cạnh ít nhất từ s đến v trong residual network ứng với trạng thái luồng f, hoặc +∞ nếu không tới được.

Khi tăng luồng trên một **đường BFS ngắn nhất**, các khoảng cách BFS từ s tới những đỉnh vẫn reachable trong các trạng thái kế tiếp **không giảm**. Cạnh dư mới có capacity dương chỉ có thể xuất hiện nhờ việc tăng sức chứa của **cạnh ngược trên đường augment**, nên việc dùng cạnh mới đó để tạo một đường ngắn hơn sẽ dẫn tới mâu thuẫn với tính ngắn nhất của đường vừa chọn.

Đây là tính chất đặc trưng của Edmonds–Karp, không đúng theo cùng cách nếu mỗi lượt chọn đường tùy tiện.

### Cạnh tới hạn bị bão hòa có giới hạn số lần xuất hiện

Mỗi lần augment, ít nhất một cạnh dư trên đường đạt remaining=0: **cạnh tới hạn (critical edge)** với capacity bằng bottleneck.

Đối với một hướng dư cụ thể u→v, nếu nó là cạnh tới hạn rồi sau đó lại trở thành cạnh tới hạn lần nữa, phải có một lượt augment trung gian dùng cạnh ngược v→u để hồi phục capacity cho u→v. Kết hợp quy tắc đường BFS ngắn nhất và tính chất khoảng cách không giảm, có thể chứng minh **khoảng cách tới u tăng ít nhất 2** giữa hai lần u→v là cạnh tới hạn.

Vì khoảng cách tới đỉnh reachable không vượt V-1, một hướng dư chỉ có thể tới hạn O(V) lần. Có O(E) cặp cạnh dư, nên số lần augment tối đa **O(VE)**.

Mỗi BFS duyệt O(V+E) bằng adjacency list. Tổng thời gian **O(VE²)** theo cận thông dụng cho mạng không tầm thường; chi phí cập nhật một đường O(V) không vượt cận tương ứng.

**Lưu ý:** E trong phân tích thường là số cạnh gốc; mạng dư có tối đa 2E đối tượng, vẫn cùng bậc O(E). Các capacity được so/cộng với phép toán số học hằng thời gian trong mô hình chuẩn.

## 11. Độ phức tạp và đánh đổi bộ nhớ

Với V đỉnh, E cạnh gốc:

| Thao tác | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Khởi tạo residual adjacency | O(V+E) | O(V+E) |
| Một BFS tìm augmenting path | O(V+E) | O(V) cho queue và parent |
| Dựng/cập nhật đường | O(V) | O(V) cho path |
| Số lần augment Edmonds–Karp | O(VE) | Phụ thuộc có lưu log không |
| Toàn bộ tìm max flow | O(VE²) | O(V+E) nếu không lưu log các đường |
| BFS lấy source side cuối | O(V+E) | O(V) |
| Liệt kê cut từ cạnh gốc | O(E) | O(E) tối đa cho danh sách |

Trong mã bài học, ta lưu **toàn bộ các đường tăng luồng** để giải thích kết quả. Nếu có A lượt augment và mỗi đường chứa tối đa V đỉnh, riêng log có thể chiếm **O(AV)=O(V²E)** phần tử trong trường hợp xấu. Vì vậy tổng bộ nhớ của **demo có log** là O(V+E+AV), không nên tuyên bố toàn bộ chương trình dùng O(V+E) nếu giữ trace không giới hạn.

Trong hệ thống production, có thể tắt log, hoặc chỉ ghi **số lượt**, giá trị bottleneck và kết quả cuối. Khi đó phần residual, queue và parent chiếm O(V+E).

### Chi phí khi dùng BigInteger

Mã Java dùng long cho **capacity của một cạnh** và BigInteger cho **tổng max flow**. Lý do: dù mỗi cạnh vừa trong long, nhiều cạnh song song có thể có tổng vượt Long.MAX_VALUE. BigInteger giúp tổng không overflow.

Phân tích O(VE²) ở trên giả định phép toán capacity có chi phí O(1). Nếu cần xét bit complexity của các phép cộng BigInteger trên luồng tổng rất lớn, còn có chi phí theo số bit; điều này không làm thay đổi tính đúng của thuật toán.

## 12. Java 17 – Edmonds–Karp đầy đủ bằng cạnh đảo

Chương trình độc lập sau:

1. Kiểm n≥2, id nguồn/đích, source!=sink, endpoint và capacity không âm.
2. Xây residual adjacency bằng các cặp Edge xuôi/ngược có **chỉ số rev chính xác**.
3. Bỏ self-loop gốc vì không giúp đưa luồng từ source tới sink.
4. BFS theo residual capacity dương và ghi prevVertex/prevEdgeIndex.
5. Tìm bottleneck, cập nhật xuôi/ngược, cộng tổng bằng BigInteger.
6. Tính sourceSide từ residual cuối; từ danh sách cạnh gốc xác định cut và capacity.
7. Ghi log từng augmentation để minh họa, bao gồm trường hợp đi qua reverse edge.

**Lưu toàn bộ mã trong tệp EdmondsKarpDemo.java:**

~~~java
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class EdmondsKarpDemo {

    record InputEdge(int from, int to, long capacity) {
        @Override
        public String toString() {
            return "(" + from + "->" + to + ":" + capacity + ")";
        }
    }

    // One residual arc. The opposite arc has index rev
    // inside the adjacency list of vertex 'to'.
    private static final class Edge {
        final int to;
        final int rev;
        long remaining;

        Edge(int to, int rev, long remaining) {
            this.to = to;
            this.rev = rev;
            this.remaining = remaining;
        }
    }

    record Augmentation(List<Integer> path, long delta) {}

    record Result(
            BigInteger maxFlow,
            List<Augmentation> augmentations,
            List<Integer> sourceSide,
            List<InputEdge> cutEdges,
            BigInteger minCutCapacity) {}

    private static void addEdge(
            List<List<Edge>> graph,
            int u, int v, long capacity) {

        // Self-loops cannot help an s-t flow or cut.
        if (u == v) {
            return;
        }

        Edge forward = new Edge(
                v, graph.get(v).size(), capacity);
        Edge reverse = new Edge(
                u, graph.get(u).size(), 0L);

        graph.get(u).add(forward);
        graph.get(v).add(reverse);
    }

    static Result solve(
            int n, int source, int sink,
            List<InputEdge> input) {

        if (n < 2) {
            throw new IllegalArgumentException(
                    "n must be at least 2");
        }
        if (source < 0 || source >= n
                || sink < 0 || sink >= n) {
            throw new IllegalArgumentException(
                    "terminal out of range");
        }
        if (source == sink) {
            throw new IllegalArgumentException(
                    "source and sink must differ");
        }
        Objects.requireNonNull(input, "input");

        List<List<Edge>> graph = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            graph.add(new ArrayList<>());
        }

        for (InputEdge e : input) {
            if (e == null) {
                throw new IllegalArgumentException(
                        "invalid edge");
            }
            if (e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n) {
                throw new IllegalArgumentException(
                        "vertex out of range");
            }
            if (e.capacity() < 0L) {
                throw new IllegalArgumentException(
                        "capacity must be nonnegative");
            }
            addEdge(graph, e.from(), e.to(), e.capacity());
        }

        BigInteger maxFlow = BigInteger.ZERO;
        List<Augmentation> steps = new ArrayList<>();

        for (;;) {
            int[] prevVertex = new int[n];
            int[] prevEdge = new int[n];
            Arrays.fill(prevVertex, -1);
            Arrays.fill(prevEdge, -1);

            ArrayDeque<Integer> queue = new ArrayDeque<>();
            prevVertex[source] = source;
            queue.addLast(source);

            // BFS finds a minimum-edge s->t residual path.
            while (!queue.isEmpty() && prevVertex[sink] == -1) {
                int u = queue.removeFirst();
                List<Edge> outgoing = graph.get(u);

                for (int i = 0; i < outgoing.size(); i++) {
                    Edge e = outgoing.get(i);
                    if (e.remaining <= 0
                            || prevVertex[e.to] != -1) {
                        continue;
                    }
                    prevVertex[e.to] = u;
                    prevEdge[e.to] = i;
                    queue.addLast(e.to);

                    if (e.to == sink) {
                        break;
                    }
                }
            }

            if (prevVertex[sink] == -1) {
                break;
            }

            long delta = Long.MAX_VALUE;
            List<Integer> reversed = new ArrayList<>();

            int v = sink;
            reversed.add(v);
            while (v != source) {
                int u = prevVertex[v];
                Edge e = graph.get(u).get(prevEdge[v]);
                delta = Math.min(delta, e.remaining);
                v = u;
                reversed.add(v);
            }

            Collections.reverse(reversed);
            steps.add(new Augmentation(
                    List.copyOf(reversed), delta));

            // Move delta along the chosen residual path.
            v = sink;
            while (v != source) {
                int u = prevVertex[v];
                Edge e = graph.get(u).get(prevEdge[v]);
                Edge reverse = graph.get(v).get(e.rev);

                e.remaining -= delta;
                reverse.remaining =
                        Math.addExact(reverse.remaining, delta);
                v = u;
            }

            maxFlow = maxFlow.add(BigInteger.valueOf(delta));
        }

        // Residual reachable set S; sink is not reachable.
        boolean[] reachable = new boolean[n];
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        reachable[source] = true;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (Edge e : graph.get(u)) {
                if (e.remaining > 0 && !reachable[e.to]) {
                    reachable[e.to] = true;
                    queue.addLast(e.to);
                }
            }
        }

        List<Integer> sourceSide = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            if (reachable[v]) {
                sourceSide.add(v);
            }
        }

        // Original directed edges crossing S -> T.
        // Zero-capacity edges are omitted from the printed list.
        List<InputEdge> cutEdges = new ArrayList<>();
        BigInteger minCut = BigInteger.ZERO;
        for (InputEdge e : input) {
            if (reachable[e.from()] && !reachable[e.to()]
                    && e.capacity() > 0L) {
                cutEdges.add(e);
                minCut = minCut.add(
                        BigInteger.valueOf(e.capacity()));
            }
        }

        return new Result(
                maxFlow,
                List.copyOf(steps),
                List.copyOf(sourceSide),
                List.copyOf(cutEdges),
                minCut);
    }

    public static void main(String[] args) {
        Result standard = solve(6, 0, 5, List.of(
                new InputEdge(0, 1, 16),
                new InputEdge(0, 2, 13),
                new InputEdge(1, 2, 10),
                new InputEdge(2, 1, 4),
                new InputEdge(1, 3, 12),
                new InputEdge(3, 2, 9),
                new InputEdge(2, 4, 14),
                new InputEdge(4, 3, 7),
                new InputEdge(3, 5, 20),
                new InputEdge(4, 5, 4)));

        System.out.println("standard max flow = " +
                standard.maxFlow());
        System.out.println("standard augmentations = " +
                standard.augmentations().size());
        for (int i = 0; i < standard.augmentations().size(); i++) {
            Augmentation a = standard.augmentations().get(i);
            System.out.println("augmentation " + (i + 1) + " = "
                    + a.path() + " / " + a.delta());
        }
        System.out.println("standard S = " +
                standard.sourceSide());
        System.out.println("standard min-cut edges = " +
                standard.cutEdges());
        System.out.println("standard min-cut capacity = " +
                standard.minCutCapacity());

        // The second augmenting path uses a reverse residual arc.
        Result reroute = solve(6, 0, 5, List.of(
                new InputEdge(0, 1, 1),
                new InputEdge(0, 2, 1),
                new InputEdge(1, 3, 1),
                new InputEdge(1, 4, 1),
                new InputEdge(2, 3, 1),
                new InputEdge(3, 5, 1),
                new InputEdge(4, 5, 1)));
        System.out.println("reroute max flow = " +
                reroute.maxFlow());
        System.out.println("reroute path 1 = " +
                reroute.augmentations().get(0).path());
        System.out.println("reroute path 2 = " +
                reroute.augmentations().get(1).path());

        // Parallel edges, plus a self-loop that must not matter.
        Result parallel = solve(4, 0, 3, List.of(
                new InputEdge(0, 1, 3),
                new InputEdge(0, 1, 4),
                new InputEdge(1, 3, 6),
                new InputEdge(0, 2, 2),
                new InputEdge(2, 3, 2),
                new InputEdge(0, 0, 99)));
        System.out.println("parallel + loop max flow = " +
                parallel.maxFlow());
        System.out.println("parallel + loop S = " +
                parallel.sourceSide());
        System.out.println("parallel + loop min-cut = " +
                parallel.minCutCapacity());

        Result disconnected = solve(4, 0, 3, List.of(
                new InputEdge(0, 1, 5),
                new InputEdge(2, 3, 7)));
        System.out.println("disconnected max flow = " +
                disconnected.maxFlow());
        System.out.println("disconnected S = " +
                disconnected.sourceSide());

        Result antiParallel = solve(3, 0, 2, List.of(
                new InputEdge(0, 1, 5),
                new InputEdge(1, 0, 2),
                new InputEdge(1, 2, 4),
                new InputEdge(0, 2, 1)));
        System.out.println("antiparallel max flow = " +
                antiParallel.maxFlow());

        Result zero = solve(3, 0, 2, List.of(
                new InputEdge(0, 1, 0),
                new InputEdge(1, 2, 1)));
        System.out.println("zero capacity max flow = " +
                zero.maxFlow());

        Result huge = solve(2, 0, 1, List.of(
                new InputEdge(0, 1, Long.MAX_VALUE),
                new InputEdge(0, 1, Long.MAX_VALUE)));
        System.out.println("huge parallel max flow = " +
                huge.maxFlow());

        try {
            solve(2, 0, 1, List.of(
                    new InputEdge(0, 1, -1)));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid negative: " +
                    ex.getMessage());
        }
        try {
            solve(2, 0, 0, List.of());
        } catch (IllegalArgumentException ex) {
            System.out.println("same terminals: " +
                    ex.getMessage());
        }
        try {
            solve(2, 0, 1, List.of(
                    new InputEdge(0, 2, 1)));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid endpoint: " +
                    ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac EdmondsKarpDemo.java
java EdmondsKarpDemo
~~~

**Stdout chính xác** với thứ tự duyệt cạnh được khai báo:

~~~text
standard max flow = 23
standard augmentations = 3
augmentation 1 = [0, 1, 3, 5] / 12
augmentation 2 = [0, 2, 4, 5] / 4
augmentation 3 = [0, 2, 4, 3, 5] / 7
standard S = [0, 1, 2, 4]
standard min-cut edges = [(1->3:12), (4->3:7), (4->5:4)]
standard min-cut capacity = 23
reroute max flow = 2
reroute path 1 = [0, 1, 3, 5]
reroute path 2 = [0, 2, 3, 1, 4, 5]
parallel + loop max flow = 8
parallel + loop S = [0, 1]
parallel + loop min-cut = 8
disconnected max flow = 0
disconnected S = [0, 1]
antiparallel max flow = 5
zero capacity max flow = 0
huge parallel max flow = 18446744073709551614
invalid negative: capacity must be nonnegative
same terminals: source and sink must differ
invalid endpoint: vertex out of range
~~~

### Đọc kết quả Java

- **Standard:** ba đường tăng luồng tổng 12+4+7=23. Source side và các cạnh min cut đúng như phân tích; maxFlow=minCutCapacity.
- **Reroute:** đường thứ hai đi 3→1 qua **cạnh ngược residual** của cạnh gốc 1→3. Không có cạnh gốc 3→1 trong input này, nhưng residual có cung đảo và dùng nó để điều chỉnh luồng.
- **Parallel + loop:** hai cạnh gốc 0→1 độc lập với capacity 3 và 4, tổng 7; cạnh 1→3 chỉ cho tối đa 6, nhánh 0→2→3 cho thêm 2, nên maxFlow=8. Self-loop 0→0 capacity 99 không tạo thêm luồng ròng.
- **Disconnected:** từ 0 chỉ tới được 1; không có đường dư tới 3 nên maxFlow=0. Cut S={0,1} không có cạnh gốc dương đi sang phần còn lại, nên capacity=0.
- **Antiparallel:** cạnh gốc 1→0 capacity 2 được giữ như một cạnh riêng, **không** làm sai liên kết các cạnh đảo của cạnh gốc 0→1; maxFlow=5.
- **Zero capacity:** cạnh 0→1 dư bằng 0, BFS không thể qua nó; không có đường tới sink.
- **Huge parallel:** tổng hai cạnh Long.MAX_VALUE vượt long, BigInteger trả chính xác 18446744073709551614.
- Các dữ liệu có capacity âm, source trùng sink hoặc endpoint sai bị từ chối rõ ràng trước khi giải.

### Vì sao Java demo dùng long cho từng cạnh và BigInteger cho tổng?

Các remaining của một cặp cạnh residual luôn nằm trong [0,capacity gốc của cặp đó]. Nếu mỗi capacity gốc nằm trong long không âm, reverse.remaining sau mỗi lần cộng delta không vượt capacity gốc. Math.addExact là một kiểm tra an toàn bổ sung.

Tổng maxFlow có thể lớn hơn Long.MAX_VALUE vì có nhiều cạnh song song/nhánh song song. BigInteger xử lý việc này. Nếu capacity **mỗi cạnh** còn vượt long, phải đổi InputEdge.capacity và Edge.remaining sang BigInteger cùng phép so sánh/trừ phù hợp.

**Chú ý về record:** Result dùng List.copyOf cho danh sách kết quả, nên không cho phép sửa danh sách ngoài ý muốn. Các Edge residual mutable chỉ tồn tại nội bộ solver. Mã giữ log augmentations phục vụ học tập; bản production có thể tắt logging.

## 13. Kiểm chứng luồng khả thi và kết quả min cut

Một chương trình max-flow đáng tin không chỉ in con số; cần có tiêu chí kiểm chứng độc lập.

### Ràng buộc capacity

Đối với mọi cạnh gốc e, ta phải có:

~~~text
0 <= flow(e) <= capacity(e)
~~~

Nếu cần xuất luồng trên **từng cạnh gốc**, nên lưu tham chiếu hoặc id tới cạnh dư xuôi tương ứng khi tạo graph. Khi ấy:

~~~text
flow(e) = originalCapacity(e) - forward.remaining
~~~

hoặc bằng remaining của cạnh dư ngược thuộc cùng cặp. Nếu có cạnh antiparallel gốc, công thức phải áp dụng **cho đúng cặp cạnh residual của từng cạnh gốc**, không lấy mọi cạnh có cùng endpoints cộng vào vô điều kiện.

Mã demo không in từng flow(e) để giữ stdout gọn, nhưng có thể mở rộng bằng một danh sách tham chiếu forwardEdgeForInputId.

### Bảo toàn ở đỉnh trung gian

Với mọi v khác s,t:

~~~text
SUM flow(u->v) = SUM flow(v->w)
~~~

Mỗi đường augment có một cạnh vào và một cạnh ra tại mọi đỉnh trung gian. Cạnh residual ngược giảm một luồng gốc, nên giá trị ròng vẫn thay đổi nhất quán; đây là lý do việc dùng cạnh ngược **không phá** tính bảo toàn.

### Max flow bằng min cut

Sau khi BFS không tới được t, lấy S là các đỉnh residual reachable, T=V\S. Tổng capacity các cạnh gốc S→T phải bằng giá trị maxFlow; đây là một **chứng chỉ tối ưu**. Trên ví dụ chuẩn:

~~~text
maxFlow = 23
minCutCapacity = 12 + 7 + 4 = 23
~~~

Nếu in ra maxFlow khác minCutCapacity, hãy xem lại rev pointers, cập nhật capacity hai chiều, định nghĩa cut hoặc việc cộng cạnh T→S nhầm hướng.

### Không kiểm cut bằng graph gốc

Trong graph gốc có thể tồn tại nhiều cạnh u→v dù đã bão hòa. Chỉ **residual graph cuối** mới cho biết những đỉnh source còn tới được. Nếu BFS bằng graph gốc, ta có thể đánh dấu cả sink dù không còn residual path, rồi trích một cut sai.

## 14. Những tình huống biên của mạng luồng

| Tình huống | Cách xử lý đúng |
| --- | --- |
| Không có cạnh nào | Max flow=0, residual reachable chỉ chứa source |
| Source và sink không nối | Max flow=0, min cut=0 |
| Một cạnh s→t capacity C | Max flow=C |
| Cạnh capacity 0 | BFS không đi được qua cạnh ấy |
| Cạnh capacity âm | Input sai mô hình, phải từ chối |
| Source==sink | Đặc tả luồng s–t thông thường yêu cầu hai đỉnh khác nhau; demo từ chối |
| Đồ thị có self-loop | Không tăng luồng ròng; demo bỏ qua sau xác thực |
| Nhiều cạnh song song | Lưu từng cạnh hoặc gộp có kiểm overflow và giữ nghĩa input |
| Có cạnh gốc theo cả hai hướng | Phải duy trì đúng cặp cạnh đảo của từng cạnh gốc |
| Đường augment cần reverse arc | Hợp lệ, dùng để hủy/sửa phân bổ luồng cũ |
| Sink có cạnh đi ra | Vẫn tính luồng ròng và residual bình thường |
| Source có cạnh đi vào | Vẫn dùng mô hình luồng ròng, không chỉ cộng output thô |
| Nhiều min cut tối ưu | Một S từ residual cuối cho một cut tối ưu, không nhất thiết duy nhất |
| Tổng flow vượt long | Dùng BigInteger cho maxFlow |
| Một capacity vượt long | Cần kiểu số lớn cả cho residual capacity |
| Số đỉnh rất lớn | BFS/danh sách kề phù hợp, nhưng O(VE²) có thể chậm |
| Có yêu cầu lưu mọi augmentation | Tính thêm bộ nhớ log |
| Các capacity không nguyên | Dùng kiểu số và so sánh phù hợp; tránh sai số dấu phẩy động |
| Input n<2 hoặc endpoint sai | Từ chối theo hợp đồng API |

### Khác biệt với đồ thị vô hướng

Nếu đề nói một cạnh vô hướng có capacity C, cần làm rõ mô hình: cạnh cho phép luồng ròng theo **hai chiều nhưng chịu một giới hạn chung**, hay cho phép **hai cung độc lập mỗi cung C**? Hai cách mã hóa không hoàn toàn cùng biểu diễn luồng trên từng hướng, dù một số bài max-flow đơn s–t có thể quy đổi.

Không tự thêm hai cạnh có hướng chỉ vì quen xử lý đồ thị vô hướng. Hãy đọc kỹ định nghĩa capacity và luồng ròng theo cạnh của đề.

## 15. So sánh Edmonds–Karp với các thuật toán luồng khác

| Thuật toán | Ý tưởng | Cận thời gian phổ biến |
| --- | --- | --- |
| Ford–Fulkerson tổng quát | Chọn bất kỳ đường tăng luồng residual | Có thể phụ thuộc giá trị max flow khi capacity nguyên |
| Edmonds–Karp | Luôn chọn đường tăng luồng ít cạnh nhất bằng BFS | O(VE²) |
| Dinic | BFS xây level graph, DFS đẩy blocking flow | O(V²E) tổng quát; nhanh hơn ở nhiều mạng |
| Push–Relabel | Dùng preflow và thao tác push/relabel | Nhiều biến thể có cận đa thức; phù hợp mạng lớn |
| Min-cost max-flow | Tối đa lượng luồng đồng thời xét chi phí | Bài toán khác, cần cost trên cạnh |

### Edmonds–Karp với Ford–Fulkerson

Edmonds–Karp **là một biến thể** của phương pháp Ford–Fulkerson. Không phải “cùng kết quả khác tên” đơn thuần; quy tắc BFS là cải tiến quan trọng để có bảo đảm đa thức O(VE²), ngay cả khi capacity rất lớn.

### Edmonds–Karp với Dinic

Dinic cũng sử dụng BFS trên residual graph, nhưng dùng BFS để xây **level graph**, rồi trong mỗi pha tìm một **blocking flow** qua nhiều đường hợp lệ trước khi xây level mới. Vì thế Dinic thường có hiệu năng tốt hơn trên nhiều bài với E,V lớn.

Edmonds–Karp vẫn phù hợp khi muốn cài đặt ngắn, dễ chứng minh, cần bộ ví dụ minh họa reverse edges và cut, hoặc kích thước input vừa phải.

### Không nhầm với bài tìm đường

BFS trong Edmonds–Karp chỉ chọn **đường tăng luồng** có ít cạnh residual nhất để hướng quá trình tối ưu luồng, chứ không giải bài shortest path đầu–cuối theo chi phí. Một đường có ít cạnh nhưng capacity bottleneck nhỏ có thể được chọn trước một đường dài hơn với bottleneck lớn; điều đó **không ảnh hưởng tính đúng** của Edmonds–Karp.

## 16. Mô hình hóa các bài toán bằng mạng luồng

### Nguồn và đích tổng hợp

Nếu có nhiều điểm cung cấp và nhiều điểm nhận, có thể tạo:

~~~text
superSource -> every supply node
every demand node -> superSink
~~~

Capacity các cạnh từ superSource phản ánh giới hạn cung cấp, và capacity tới superSink phản ánh giới hạn tiếp nhận. Không dùng một giá trị “vô cùng” tùy ý nhỏ hơn luồng hợp lệ; nếu cần INF, chọn cận an toàn từ dữ liệu và kiểm tràn số.

### Ghép cặp hai phía (bipartite matching)

Với một đồ thị hai phía U,W:

1. Thêm source→u capacity 1 với mọi u thuộc U.
2. Với mỗi cặp cho phép (u,w), thêm u→w capacity 1.
3. Thêm w→sink capacity 1 với mọi w thuộc W.

Một luồng nguyên tối đa tương ứng với một **ghép cặp tối đa**. Nếu mọi capacity nguyên, thuật toán tăng luồng theo delta nguyên bảo toàn tính nguyên của kết quả. Với bài matching lớn, Hopcroft–Karp là thuật toán chuyên biệt thường phù hợp hơn, nhưng mạng luồng là cách mô hình hóa rất trực quan.

### Sức chứa theo đỉnh (vertex capacity)

Edmonds–Karp mặc định capacity đặt trên **cạnh**. Nếu một trạm v chỉ có thể xử lý tối đa C_v đơn vị, ta có thể **tách đỉnh** thành v_in và v_out, thêm cạnh v_in→v_out capacity C_v, rồi nối các cạnh đến/đi với hai nửa đỉnh tương ứng.

Phải xác định cách xử lý source, sink và những đỉnh không có giới hạn theo đặc tả. Không thể chỉ gắn vertex capacity vào một cạnh bất kỳ rồi tin rằng nó đã ràng buộc mọi đường qua v.

### Phân luồng theo từng hạng mục

Nếu các loại hàng có thể tương tác hoặc có yêu cầu luồng riêng từng loại, mô hình **single-commodity max-flow** có thể không đủ. Multi-commodity flow là bài toán phức tạp hơn; không tự gom mọi loại hàng thành một dòng nếu có giới hạn riêng biệt về hàng hóa.

## 17. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| BFS trên cạnh gốc thay vì residual | Không có khả năng sửa luồng cũ | Duyệt toàn bộ residual edges |
| Quên reverse edge khi addEdge | Không thể hủy phân bổ luồng | Thêm cặp forward/reverse |
| Quên cập nhật reverse.remaining | Residual mất cân bằng | Giảm xuôi, tăng ngược cùng delta |
| rev chỉ sai khi có parallel edges | Ghi vào sai cạnh, sai luồng | Lưu chính xác chỉ số cạnh đảo |
| Dùng cùng rev cho cạnh gốc hai chiều độc lập | Gộp sai luồng hai cạnh | Mỗi InputEdge có cặp riêng |
| Quên kiểm remaining>0 trong BFS | Đi qua cạnh đã bão hòa | Chỉ duyệt cạnh dương |
| Dùng DFS tùy tiện rồi gọi Edmonds–Karp | Không còn bảo đảm O(VE²) của BFS | Dùng queue FIFO BFS |
| Chọn bottleneck theo capacity gốc | Có thể tăng vượt dư hiện tại | Lấy min remaining trên đường |
| Đánh dấu visited sau khi dequeue | Có thể lặp/ghi đè parent | Đánh dấu khi enqueue |
| Chỉ lưu prevVertex với multigraph | Không biết cạnh nào đã dùng | Lưu prevEdgeIndex |
| Không reset parent mỗi lượt | Dựng đường từ trạng thái cũ | Tạo/fill lại mỗi BFS |
| Không cập nhật đúng hướng cạnh ngược | Sai conservation | Cặp residual có chỉ số rev |
| Cộng cạnh cut cả chiều T→S | Cut capacity sai | Chỉ cộng cạnh gốc S→T |
| Tính S bằng graph gốc | Phía cut sai | BFS trên residual cuối |
| Coi self-loop là tăng s–t flow | Đếm luồng giả | Bỏ qua hoặc xử lý đúng |
| Dùng capacity âm | Residual không có nghĩa chuẩn | Từ chối input |
| Coi capacity là cost | Giải nhầm bài toán | Phân biệt max-flow và min-cost |
| Đếm tổng flow bằng long không kiểm | Overflow | BigInteger hoặc addExact |
| Lưu log vô hạn rồi nói memory O(V+E) | Ước lượng bộ nhớ thiếu | Bỏ log/đếm thêm log |
| Chỉ kiểm maxFlow mà không kiểm minCut | Khó bắt lỗi tinh vi | So maxFlow=minCutCapacity |
| Tưởng min cut duy nhất | Test cứng một tập S | Kiểm capacity và phân hoạch hợp lệ |
| Không kiểm source!=sink | Thuật toán có thể rơi vào xử lý đặc biệt vô nghĩa | Quy định và xác thực đầu vào |

**Điểm cốt lõi nhất:** capacity dương ở cạnh ngược residual **không phải** sự cho phép vận chuyển trái chiều trên một cạnh gốc có hướng. Nó là quyền **hủy bớt luồng cũ**, một phép biến đổi tương đương về bảo toàn luồng.

## 18. Kiểm thử độc lập và những bất biến quan trọng

### Bất biến qua từng lượt augmentation

- Mọi remaining của residual đều không âm.
- Với mỗi cặp forward/reverse của **một cạnh gốc**, tổng remaining hai chiều bằng capacity ban đầu của cạnh đó.
- Delta là số dương và không vượt remaining của bất kỳ cạnh dư nào trên đường chọn.
- Đường BFS không lặp đỉnh do visited/prevVertex.
- Giá trị maxFlow tăng chính xác delta.
- Flow gốc nằm trong [0,capacity] với mọi cạnh.
- Luồng bảo toàn tại tất cả đỉnh khác source,sink.

### Bất biến khi kết thúc

- Không còn đường residual capacity dương từ source tới sink.
- Source nằm trong S, sink không nằm trong S.
- Tập S tính bằng reachability residual cuối.
- Mọi cạnh gốc từ S sang T có forward remaining bằng 0.
- Mọi luồng từ T sang S phải có giá trị 0 nếu xét từng cạnh gốc.
- **maxFlow == minCutCapacity**.
- Một luồng khả thi khác không thể lớn hơn minCutCapacity, nên luồng hiện tại tối ưu.

### Đối chứng bằng brute force min cut trên đồ thị nhỏ

Với V≤8, có thể liệt kê mọi tập S chứa source nhưng không chứa sink, tức tối đa 2^(V-2) phương án. Tính capacity(S,V\S) bằng cách quét các cạnh gốc có hướng từ S ra ngoài S, rồi lấy giá trị nhỏ nhất.

Kết quả brute force **min-cut capacity** phải bằng maxFlow Edmonds–Karp. Đây là một oracle độc lập so với việc chạy BFS/augment trên residual graph.

Đối với capacity nguyên nhỏ và graph nhỏ, cũng có thể đối chứng với một cài đặt max-flow độc lập (chẳng hạn Dinic). Đừng dùng chính cùng code Edmonds–Karp đổi tên làm oracle.

### Các test cố định

| Input | Kết quả |
| --- | --- |
| Mạng chuẩn 6 đỉnh | maxFlow=23, minCut=23 |
| Mạng reroute 6 đỉnh | maxFlow=2, đường thứ hai dùng cạnh đảo 3→1 |
| Mạng có parallel edges và self-loop | maxFlow=8, minCut=8 |
| Source không tới được sink | maxFlow=0, minCut=0 |
| Đồ thị antiparallel có 3 đỉnh | maxFlow=5 |
| Cạnh duy nhất s→t capacity 0 | maxFlow=0 |
| Hai cạnh song song s→t capacity Long.MAX_VALUE | maxFlow=18446744073709551614 |
| Source trùng sink | Bị từ chối |
| Có capacity âm | Bị từ chối |
| Endpoint ngoài [0,n) | Bị từ chối |
| Không có cạnh từ source | maxFlow=0 |
| Nhiều min cuts đồng hạng | Một cut hợp lệ với capacity=maxFlow, không ép S cố định |

### Metamorphic/property tests

1. **Đổi thứ tự input edges:** có thể đổi danh sách đường augment, nhưng **maxFlow không đổi**. Một min cut có thể khác nếu có nhiều cut tối ưu.
2. **Đổi nhãn đỉnh bằng hoán vị** kèm source/sink và endpoint: giá trị maxFlow không đổi.
3. **Thêm self-loop capacity bất kỳ không âm:** maxFlow không đổi.
4. **Thêm cạnh capacity=0:** maxFlow không đổi.
5. **Chia một cạnh u→v capacity C thành hai cạnh song song C1,C2 với C1+C2=C:** maxFlow không đổi nếu không overflow và các cạnh khác giữ nguyên.
6. **Tăng capacity cạnh:** giá trị maxFlow không thể giảm.
7. **Nhân toàn bộ capacity với số nguyên dương k:** maxFlow nhân k, nếu miền số được bảo toàn.
8. **Đổi chiều tất cả cạnh và hoán đổi source/sink:** maxFlow không đổi vì mỗi luồng từ s tới t có thể đảo chiều thành luồng từ t tới s trong mạng đảo hướng.
9. **Kiểm brute force cut:** với mạng nhỏ, minCutCapacity tính từ thuật toán phải bằng min của mọi cut.
10. **Kiểm trace:** từng đường tăng luồng phải tồn tại trong residual ngay trước bước tăng, và bottleneck đúng bằng min remaining trên đường ở thời điểm đó.

### Kiểm chứng trọng số và hướng

Trên mạng có cả u→v và v→u là hai cạnh gốc riêng, không cộng capacity của chúng theo một hướng khi tính min cut. Chỉ lấy những cạnh có đầu thuộc S và đích thuộc T. Nếu có nhiều cạnh song song đúng chiều S→T, từng cạnh đóng góp capacity riêng.

## 19. Bài tập tự luyện

1. Với mạng s→a capacity 8, a→b capacity 3, b→t capacity 20, tìm bottleneck và cập nhật cả cạnh xuôi lẫn ngược sau khi tăng luồng.
2. Tự tính ba đường augment và maxFlow=23 của mạng sáu đỉnh chuẩn. Dựng residual cuối và kiểm S={0,1,2,4}.
3. Dùng mạng chuẩn để tính cut S→T, giải thích vì sao cạnh 3→2 không được cộng vào capacity cut.
4. Mô phỏng ví dụ reroute: sau lượt đầu 0→1→3→5, xác định remaining của cạnh dư 3→1; sau lượt hai giải thích cách luồng gốc 1→3 giảm.
5. Viết BFS chỉ đi qua remaining>0, lưu prevVertex và prevEdgeIndex. Tại sao không thể chỉ lưu prevVertex nếu có parallel edges?
6. Thêm cạnh gốc 1→0 với capacity 5 vào một mạng đã có cạnh 0→1. Vẽ bốn đối tượng dư của hai cạnh gốc và giải thích chỉ số rev.
7. Viết chương trình kiểm invariant forward.remaining+reverse.remaining==originalCapacity sau mỗi augmentation.
8. In luồng trên từng cạnh gốc bằng originalCapacity-forward.remaining; khi có antiparallel edges, kiểm từng cặp riêng.
9. Tạo mạng có capacity bằng 0 và self-loop lớn. Chạy thuật toán rồi giải thích vì sao maxFlow không đổi nếu bỏ các cạnh ấy.
10. Đối với V≤7, liệt kê tất cả s–t cuts và so min cut brute force với kết quả Edmonds–Karp trên 100 mạng ngẫu nhiên.
11. Sinh mạng có vài cạnh song song capacity khác nhau. Thử chia/gộp capacity hai cạnh và kiểm maxFlow không đổi.
12. Chứng minh mọi luồng khả thi ≤ capacity(S,T) của bất kỳ s–t cut bằng bảo toàn luồng trong S.
13. Chứng minh S là tập reachable trong residual cuối tạo ra cut có capacity đúng bằng giá trị luồng.
14. Giải thích vì sao chọn đường tùy tiện của Ford–Fulkerson có thể chậm hơn quy tắc BFS của Edmonds–Karp; phát biểu cận O(VE²).
15. Cài đặt một phiên bản Dinic và so maxFlow, minCut trên các mạng thưa, mạng dày và mạng nhiều cạnh song song.
16. Mô hình hóa bài bipartite matching thành mạng luồng với capacity 1, đối chiếu giá trị maxFlow với số cặp ghép.
17. Một trạm trung gian có vertex capacity 4. Tách đỉnh thành v_in,v_out và thêm cạnh v_in→v_out capacity 4. Vì sao chỉ đặt capacity trên một cạnh đi ra tùy ý không đủ?
18. Tạo nhiều sources/sinks, thêm superSource/superSink với capacity theo cung/cầu; tính luồng và nêu vai trò mỗi loại cạnh.
19. Với hai cạnh song song đều Long.MAX_VALUE, chứng minh tổng maxFlow không thể chứa trong long. Thử BigInteger và một phiên bản chỉ dùng long.
20. Tắt log augmentations trong mã Java, phân tích sự khác nhau giữa bộ nhớ O(V+E) cốt lõi và O(V+E+AV) khi lưu đầy đủ A đường tăng.
21. Tạo mạng có nhiều lát cắt nhỏ nhất bằng nhau; thử đảo thứ tự cạnh rồi xem source side tìm được có thay đổi không, nhưng maxFlow vẫn như cũ.
22. Giải thích vì sao Edmonds–Karp giải **maximum flow** chứ không giải **minimum-cost maximum flow**, dù BFS chọn đường ít cạnh.
23. Phân biệt một cạnh ngược residual do hủy luồng cũ với một cạnh gốc antiparallel; nêu cách code đánh dấu và cập nhật đúng.
24. Viết hàm validateFlow nhận danh sách flow từng cạnh, kiểm capacity, conservation và net source/sink, rồi dùng nó để kiểm kết quả solver.

## 20. Tổng kết và checklist

Trước khi áp dụng Edmonds–Karp:

- Mô hình có phải **mạng có hướng**, capacity **không âm**, source và sink phân biệt?
- Bài hỏi **max flow** hay shortest path, min cost, matching, hoặc nhu cầu nhiều loại hàng?
- Mỗi cạnh gốc đã tạo **một cặp residual xuôi/ngược** có chỉ số rev đúng chưa?
- Có xử lý rõ **parallel**, **antiparallel**, self-loop và zero capacity?
- BFS có chỉ đi qua residual edges với remaining>0, không duyệt cố định các cạnh gốc?
- Có lưu đủ prevVertex và prevEdgeIndex để dựng chính xác đường augment?
- Bottleneck có là **min remaining** trên mọi cạnh trong đường?
- Có cập nhật đồng thời **xuôi -= delta** và **ngược += delta**?
- Khi không còn residual path s→t, có trích sourceSide từ **residual cuối**?
- Min cut có chỉ cộng **các cạnh gốc hướng S→T**, không cộng chiều ngược?
- Đã kiểm **maxFlow == minCutCapacity** như một chứng chỉ tối ưu?
- Có nguy cơ overflow tổng flow, chi phí lưu log hay mạng quá lớn cho O(VE²)?
- Đã đối chứng bằng brute force min cut trên mạng nhỏ và kiểm conservation/capacity?

**Kết luận:** Edmonds–Karp là phương pháp Ford–Fulkerson chọn **đường tăng luồng ngắn nhất theo số cạnh bằng BFS trên mạng dư**. Mỗi lần tăng, thuật toán dùng bottleneck và cập nhật hai hướng của cặp residual để có thể **sửa cả các phân bổ luồng cũ**. Khi BFS không còn đến được sink, tập reachable cuối cùng tạo một **s–t min cut**, có capacity bằng giá trị max flow; đây vừa là kết quả tối ưu vừa là bằng chứng kiểm chứng được. Với danh sách kề, Edmonds–Karp có cận thời gian **O(VE²)** và bộ nhớ cốt lõi O(V+E) nếu không lưu toàn bộ trace.

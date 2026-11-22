# Thuật toán Dinic với đồ thị mức và luồng chặn

## Mục tiêu học tập

Trong nhóm **Luồng mạng**, **Dinic** (còn được viết Dinitz) là thuật toán tìm **luồng cực đại** (*maximum flow*) từ nguồn `s` đến đích `t` trên **đồ thị có hướng, có dung lượng cạnh không âm**. Điểm đặc trưng của Dinic là thay vì chỉ tăng luồng trên **một** đường bất kỳ mỗi lượt, thuật toán lặp theo **pha** (*phase*):

1. Dùng **BFS trên đồ thị dư** để xây **đồ thị mức** (*level graph*) gồm các cạnh tiến đúng một mức.
2. Trong đồ thị mức ấy, dùng **DFS và con trỏ cạnh hiện hành** (*current-arc optimization*) để đẩy một **luồng chặn** (*blocking flow*).
3. Khi không thể đẩy thêm trong đồ thị mức của pha hiện tại, làm BFS mới; nếu không còn đường dư từ s tới t thì **luồng hiện có là cực đại**.

Bài học giải thích đầy đủ mô hình luồng, tính đúng của cập nhật cạnh dư và reverse edge, các bất biến của Dinic, tại sao BFS phải làm mới theo pha, vì sao **luồng chặn chưa chắc là luồng cực đại toàn mạng**, chứng minh max-flow/min-cut, độ phức tạp tổng quát và mã **Java 17+ chạy độc lập**.

Sau bài này, bạn có thể:

- Phát biểu ràng buộc **dung lượng**, **bảo toàn luồng**, **giá trị luồng** và bài toán cực đại.
- Tạo **đồ thị dư** với cạnh thuận và cạnh ngược, hiểu ý nghĩa **hủy/đổi đường luồng**.
- Tính mảng `level[]` bằng BFS chỉ qua cạnh có dung lượng dư dương.
- Phân biệt **đường tăng luồng**, **đồ thị mức** và **luồng chặn**.
- Triển khai DFS `sendFlow` với `ptr[]` và biết tại sao con trỏ chỉ reset **mỗi pha**.
- Giải thích vì sao Dinic dừng và có tổng thời gian **`O(V^2E)`** trong trường hợp tổng quát.
- Trích xuất **min-cut** từ đồ thị dư sau khi chạy; xác nhận `maxFlow=minCutCapacity`.
- Xử lý đúng **cạnh song song**, **cạnh ngược chiều độc lập**, **self-loop**, **cạnh dung lượng 0**, **mạng không nối tới t** và số `long` lớn.
- Tránh những lỗi thường gặp với reverse edge, BFS trên graph gốc, DFS không kiểm tra mức, luồng âm, overflow và tràn ngăn xếp đệ quy.

---

## 1. Bài toán luồng cực đại là gì?

Cho mạng có hướng:

\[
G=(V,E),\quad s,t\in V,\quad s\ne t,
\]

với mỗi cạnh e=(u,v) có **dung lượng** `c(u,v)\ge0`. Dung lượng là giới hạn tối đa cho lượng hàng, dữ liệu, nước, đơn vị công việc hoặc tài nguyên đi qua cạnh trong một đơn vị thời gian.

Ta muốn đưa càng nhiều luồng càng tốt từ **nguồn s** tới **đích t**, miễn không vi phạm dung lượng và các đỉnh trung gian không tự sinh hay tiêu hao luồng.

### 1.1. Ràng buộc dung lượng

Đặt `f(u,v)` là luồng trên cạnh gốc `u→v`:

\[
0\le f(u,v)\le c(u,v).
\]

Với cạnh có dung lượng 10, luồng gửi qua cạnh ấy có thể là 0, 3, 10 nhưng không thể 11. Với cạnh dung lượng 0, cạnh vẫn có thể tồn tại trong dữ liệu nhưng không cho phép chảy theo chiều thuận ở trạng thái ban đầu.

### 1.2. Bảo toàn luồng tại đỉnh trung gian

Với mọi đỉnh `v\ne s,t`:

\[
\sum_{(u,v)\in E} f(u,v)
=
\sum_{(v,w)\in E} f(v,w).
\]

Lượng luồng đi **vào** đỉnh trung gian bằng lượng đi **ra**. Đỉnh trung gian có thể nằm trên nhiều đường và chia/gộp lượng luồng, nhưng không được tạo thêm luồng.

### 1.3. Giá trị của một luồng

Giá trị luồng là lượng ròng đi ra nguồn:

\[
|f|=\sum_{(s,v)\in E}f(s,v)
-\sum_{(u,s)\in E}f(u,s).
\]

Theo bảo toàn tại các đỉnh trung gian, nó cũng bằng lượng ròng đi vào đích. Bài toán là:

\[
\max |f|
\]

trên tất cả các phép gán f thỏa các ràng buộc trên.

### 1.4. Không nên nhầm với bài đường đi ngắn nhất

Một đường ngắn nhất tìm tổng trọng số **nhỏ nhất** từ s tới t. Max flow tìm **tổng lượng vận chuyển lớn nhất** qua **nhiều đường đồng thời**, có thể dùng nhiều đường đi, và phải tôn trọng các cạnh có dung lượng chung.

Nếu một đường s→a→t chứa cạnh nghẽn dung lượng 3, không thể gửi 10 trên đường ấy chỉ vì cạnh đầu có dung lượng 10. Luồng gửi trên một đường bị giới hạn bởi **dung lượng dư nhỏ nhất** dọc đường (*bottleneck*).

### 1.5. Mô hình dung lượng và đồ thị có hướng

Trong mạng luồng, cạnh `u→v` và `v→u` là **hai cạnh gốc độc lập** nếu input nêu cả hai. Chúng có thể có dung lượng khác nhau. Ngoài các cạnh gốc, thuật toán còn tạo **cạnh dư ngược** phục vụ thao tác hoàn tác luồng; cạnh ngược dư **không được tự động nhầm** với cạnh gốc đi chiều ngược.

---

## 2. Đồ thị dư (residual network): điều kiện để đổi quyết định

Nếu trên cạnh gốc u→v có dung lượng c và hiện gửi luồng f, ta có:

- **Dung lượng dư chiều thuận**: `c-f` — còn gửi thêm được bao nhiêu.
- **Dung lượng dư chiều ngược**: `f` — có thể **hủy** bao nhiêu luồng trước đó trên cạnh gốc.

Đó là ý nghĩa của **residual edge**.

### 2.1. Ví dụ cạnh dung lượng 8

Ban đầu:

```text
u --(8)--> v

residual u -> v = 8
residual v -> u = 0
```

Nếu gửi 5 đơn vị theo u→v:

```text
luồng trên cạnh gốc u -> v = 5

residual u -> v = 3
residual v -> u = 5
```

Nếu về sau một đường tăng luồng sử dụng cạnh dư `v→u` để hủy 2 đơn vị, thì:

```text
residual u -> v = 5
residual v -> u = 3

luồng ròng trên cạnh gốc u -> v = 3
```

**Reverse edge là khả năng sửa phân bổ trước đó**, không phải chỉ là một cạnh “tự mọc ra” làm tăng công suất vật lý.

### 2.2. Quy tắc cập nhật hai chiều

Nếu đẩy `pushed` đơn vị qua cạnh dư e:

\[
residual(e)\leftarrow residual(e)-pushed,
\]

\[
residual(reverse(e))\leftarrow
residual(reverse(e))+pushed.
\]

Hai thay đổi phải xảy ra **cùng nhau**. Nếu chỉ trừ dung lượng dư chiều thuận mà không cộng cạnh ngược, thuật toán không thể sửa những quyết định tăng luồng trước đó và có thể trả kết quả thấp hơn tối ưu.

### 2.3. Đường tăng luồng (augmenting path)

Một **đường tăng luồng** là đường từ s tới t trong đồ thị dư mà **mọi cạnh có dung lượng dư dương**.

Dung lượng tăng thêm tối đa qua đường P:

\[
b(P)=\min_{e\in P} residual(e).
\]

Ta có thể tăng giá trị luồng lên `b(P)>0` bằng cập nhật tất cả cạnh thuận/ngược dư trên đường ấy.

Ví dụ đường:

```text
s --(7)--> a --(4)--> b --(9)--> t
```

có bottleneck 4. Đẩy 4 sẽ làm cạnh a→b **bão hòa**, tức dung lượng dư về 0.

### 2.4. Vì sao đường dư có thể dùng cạnh ngược?

Giả sử đã gửi hàng theo s→a→b→t. Về sau tìm được cách tốt hơn là để a gửi qua c, còn b nhận hàng từ một nhánh khác. Cạnh dư b→a cho phép **rút lại** phần gửi a→b rồi phân bổ lại, không vi phạm bảo toàn luồng.

Nếu không có reverse edge, thuật toán “tham lam đường đi trước” có thể bị khóa bởi một cách gán sai mặc dù mạng còn khả năng vận chuyển lớn hơn.

### 2.5. Cạnh song song và cạnh đối hướng

Nếu input có hai cạnh độc lập:

```text
u -> v (capacity 3)
u -> v (capacity 5)
```

chúng có thể cùng đóng góp 8 đơn vị trong trường hợp các phía còn lại đủ dung lượng. Có thể gộp thành một cạnh dung lượng 8 nếu chỉ cần tổng flow và không cần theo dõi luồng của từng cạnh gốc.

Nếu input còn có cạnh gốc v→u dung lượng 4, **đừng** dùng reverse edge của một cạnh u→v thay cho cạnh gốc ấy. Cách an toàn là **mỗi cạnh gốc có một cặp cạnh dư thuận/ngược riêng**.

---

## 3. Từ Ford–Fulkerson đến Dinic

### 3.1. Ford–Fulkerson cơ bản

Khung lặp:

```text
flow = 0

while tìm được đường tăng luồng P trong đồ thị dư:
    delta = min residual trên P
    cập nhật mọi cạnh dư và cạnh ngược của P
    flow += delta

return flow
```

Ý tưởng đúng về mặt cấu trúc, nhưng số vòng lặp và cách chọn đường ảnh hưởng nhiều đến hiệu năng. Nếu dung lượng là số nguyên và mỗi lượt tăng ít nhất 1, ta có một cận phụ thuộc giá trị luồng cực đại; với các dung lượng thực và chọn đường tùy ý, các vấn đề hội tụ cần được phân tích cẩn thận.

### 3.2. Edmonds–Karp

Edmonds–Karp chọn **đường tăng ngắn nhất theo số cạnh** bằng BFS trên đồ thị dư. Cận tổng quát:

\[
O(VE^2).
\]

Đây là một phương pháp có thời gian đa thức không phụ thuộc trực tiếp vào tổng giá trị dung lượng trong mô hình thao tác số học phù hợp.

### 3.3. Động cơ của Dinic

Edmonds–Karp mỗi lần dùng BFS để lấy **một đường**. Dinic tận dụng nhiều hơn kết quả BFS: xây **toàn bộ phân lớp mức**, rồi gửi luồng dọc **nhiều đường ngắn nhất còn hợp lệ** cho tới khi tạo **luồng chặn** trên lớp đó.

Thay vì tính lại BFS sau mỗi đường tăng, Dinic chỉ tính BFS sau khi **không còn đường đi s→t trong đồ thị mức hiện tại**.

### 3.4. Hai tầng tham lam của Dinic

- BFS xác định **độ dài ít cạnh nhất** của đường tăng từ s tới mỗi đỉnh trong đồ thị dư.
- DFS chỉ đi trên các cạnh dư tiến **đúng một mức**, vì vậy mọi đường s→t đang dùng trong pha đều có độ dài ít cạnh nhất của pha đó.

Điểm mạnh không đến từ việc “chọn một đường có bottleneck lớn nhất”, mà từ việc **chặn toàn bộ các đường s→t của đồ thị mức** rồi mới làm lại BFS.

---

## 4. Đồ thị mức (level graph) bằng BFS

Ở đầu mỗi pha, ta chạy BFS từ nguồn s, chỉ đi qua **cạnh dư có residual > 0**.

Đặt:

\[
level[s]=0.
\]

Với các đỉnh khác, ban đầu `level[v]=-1` (chưa reachable). Nếu BFS đang ở u và thấy cạnh dư u→v dung lượng dương, với v chưa được thăm:

\[
level[v]=level[u]+1.
\]

Vì BFS duyệt theo từng lớp, `level[v]` đúng là số cạnh **ít nhất** của một đường dư từ s tới v.

### 4.1. Những cạnh nào thuộc đồ thị mức?

Một cạnh dư `u→v` được cho phép trong pha khi **cả hai điều kiện** đúng:

\[
\boxed{residual(u,v)>0}
\]

và:

\[
\boxed{level[v]=level[u]+1.}
\]

Đó là một **admissible edge** — cạnh hợp lệ để đẩy luồng trong đồ thị mức.

### 4.2. Không dùng mọi cạnh nối hai đỉnh reachable

Một cạnh từ level 3 về level 2 có thể có dung lượng dư dương, nhưng không được đi theo nó trong DFS pha hiện tại. Tương tự, cạnh nối **hai đỉnh cùng mức** không hợp lệ.

Bởi mọi bước đều tăng level lên 1, đồ thị mức **không có chu trình có hướng theo các cạnh được phép**. Điều này làm việc tìm các đường ngắn nhất và luồng chặn thuận tiện hơn.

### 4.3. Nếu level[t] = -1

Khi BFS không thể tới đích t qua bất kỳ cạnh dư dương nào, nghĩa là **không có đường tăng luồng**. Theo định lý luồng cực đại — lát cắt nhỏ nhất, luồng hiện tại là **cực đại** và thuật toán dừng.

Không được dùng BFS trên **graph gốc** sau khi đã có luồng: một cạnh gốc bão hòa có thể không còn dung lượng dư, còn cạnh ngược dư có thể trở nên quan trọng.

### 4.4. Có nên dừng BFS ngay khi thấy t?

Để triển khai rõ ràng và bảo đảm xây đủ mảng mức hữu ích cho pha, chương trình mẫu **duyệt BFS tới khi hàng đợi rỗng** rồi mới xem `level[t]`.

Một cách tối ưu BFS dừng sớm có thể đúng nếu được thiết kế cẩn thận, nhưng dừng ngay khi phát hiện t mà bỏ xây các nhánh còn lại của lớp thích hợp có thể khiến DFS không khai thác đủ đường trong cùng pha, dẫn đến sai lập luận về **luồng chặn** hoặc làm giảm hiệu năng. Bản đầy đủ đơn giản, dễ chứng minh hơn.

---

## 5. Luồng chặn (blocking flow) là gì?

Cho một **đồ thị mức cố định** của pha hiện tại. Một luồng trên các cạnh hợp lệ gọi là **blocking flow** khi **mọi đường s→t trong đồ thị mức ban đầu đều có ít nhất một cạnh trở nên bão hòa trong phần dư của pha**, hay nói tương đương:

> Sau khi đẩy xong, **không còn đường tăng luồng s→t chỉ dùng các cạnh tiến đúng một mức** của lớp hiện tại.

### 5.1. Phân biệt ba khái niệm

- **Một đường tăng:** một đường s→t có bottleneck dương, giúp tăng luồng.
- **Một luồng chặn:** kết quả nhiều lần tăng dọc cạnh hợp lệ trong **cùng một level graph**, đến khi level graph không còn đường s→t.
- **Luồng cực đại:** không còn đường tăng s→t trong **toàn bộ đồ thị dư**, kể cả đường dài hơn hoặc dùng những cạnh không hợp lệ trong lớp cũ.

**Luồng chặn của một pha chưa chắc là max flow**. Nó chỉ đóng các đường tăng có độ dài BFS hiện tại. Pha sau có thể tìm đường dài hơn.

### 5.2. Không bắt buộc bão hòa mọi cạnh

Tên “luồng chặn” **không** có nghĩa làm bão hòa toàn bộ cạnh ra khỏi s hoặc tất cả cạnh của graph. Chỉ cần mọi đường s→t hợp lệ trong đồ thị mức hiện tại **bị chặn** bởi ít nhất một cạnh bão hòa.

Có thể còn nhiều cạnh dư dương nhưng không tạo thành đường s→t tiến mức trong pha.

### 5.3. Vì sao đẩy được nhiều đường mà không gọi BFS lại?

BFS xác định một cấu trúc phân lớp. Sau mỗi phép tăng, ta chỉ thay dung lượng dư, còn **mảng level[] của pha vẫn giữ nguyên**.

DFS lại thử các đường chỉ tăng level từ s tới t. Khi không thể đẩy thêm, ta mới làm BFS khác để khai thác những đường ngắn nhất mới, thường dài hơn.

Không sửa level[] tùy tiện giữa lúc đang tìm blocking flow.

---

## 6. Current-arc optimization: con trỏ cạnh hiện hành

Nếu một đỉnh u có danh sách kề rất dài, mỗi lần DFS không nên bắt đầu thử lại từ cạnh đầu tiên khi những cạnh đó đã biết **không thể dẫn tới t trong pha hiện tại**.

Dinic thường lưu:

```text
ptr[u] = chỉ số cạnh đầu tiên chưa loại bỏ
         trong danh sách kề của u ở pha hiện tại
```

Khi DFS xét một cạnh e của u:

- Nếu `residual(e)=0` hoặc `level[to]!=level[u]+1`, bỏ cạnh, tăng `ptr[u]`.
- Nếu cạnh hợp lệ nhưng DFS xuống đỉnh kế tiếp **không đẩy được gì**, bỏ cạnh này trong pha, tăng `ptr[u]`.
- Nếu DFS **đẩy được** một lượng dương, cập nhật phần dư rồi **trả ngay**, chưa cần tăng `ptr[u]`: cạnh ấy có thể còn dư và tiếp tục đẩy ở lần DFS sau.
- Nếu một cạnh vừa bị bão hòa, ở lần thử tiếp theo nó sẽ bị bỏ do residual=0.

### 6.1. Tại sao chỉ reset ptr[] sau BFS mới?

Trong một pha, mảng level[] cố định và các cạnh được DFS dùng chỉ đi **tiến mức**. Khi một cạnh bị loại vì không còn giúp tạo đường đến t trên đồ thị mức hiện tại, các lần tăng tiếp theo không khiến cạnh ấy trở nên hữu ích trở lại theo thứ tự lớp hiện tại.

Tại pha mới, phần dư và mức có thể thay đổi, nên **phải reset `ptr[u]=0`** cho mọi u; một cạnh từng không admissible có thể trở nên admissible trong đồ thị mức mới.

### 6.2. DFS đẩy bao nhiêu?

Hàm đệ quy đi từ u tới t nhận một giới hạn `limit`:

```text
sendFlow(u,limit):
    if u == t:
        return limit

    for cạnh e bắt đầu từ ptr[u]:
        nếu e không admissible: bỏ
        pushed = sendFlow(e.to, min(limit, e.residual))
        nếu pushed > 0:
            e.residual -= pushed
            reverse(e).residual += pushed
            return pushed

    return 0
```

Lần gọi đầu ở nguồn có thể dùng `Long.MAX_VALUE` làm giới hạn, rồi phép `min` dọc đường sẽ lấy bottleneck thật.

### 6.3. Vì sao cần một vòng gọi DFS nhiều lần?

Một lần gọi `sendFlow(s,∞)` trong bản mẫu chỉ đẩy trên **một đường** rồi trả về. Muốn tạo blocking flow, ta cần:

```text
while true:
    pushed = sendFlow(s, infinity)
    if pushed == 0:
        break
    flow += pushed
```

Điều quan trọng là **không đặt lại ptr[] giữa các lượt này**, vì đó vẫn là **cùng pha**.

### 6.4. Cạm bẫy với đệ quy

Độ sâu DFS trong Dinic có thể tới `O(V)`. Mạng có đường tăng dài hàng trăm nghìn đỉnh có thể khiến Java ném `StackOverflowError` nếu dùng DFS đệ quy.

Chương trình dưới đây ưu tiên mã dễ đọc và chứng minh. Với V rất lớn và mạng có đường dài, nên dùng **DFS stack tường minh** hoặc triển khai blocking flow **lặp** thay vì tăng cỡ ngăn xếp mà không đánh giá độ ổn định.

---

## 7. Toàn bộ quy trình Dinic

Giả mã:

```text
DINIC(G, source, sink):
    dựng đồ thị dư với forward/reverse edge
    flow = 0

    while BFS_LEVEL_GRAPH(source, sink) tìm thấy sink:
        for u trong V: ptr[u] = 0

        while true:
            pushed = DFS_BLOCKING_FLOW(
                source, sink, +INF, level, ptr)
            if pushed == 0:
                break
            flow += pushed

    return flow
```

**BFS_LEVEL_GRAPH**:

```text
level[all] = -1
level[source] = 0
queue.push(source)

while queue không rỗng:
    u = queue.pop()
    for cạnh dư e từ u:
        if e.residual > 0
           and level[e.to] == -1:
            level[e.to] = level[u] + 1
            queue.push(e.to)

return level[sink] != -1
```

**DFS_BLOCKING_FLOW** chỉ đi qua cạnh thỏa:

```text
e.residual > 0
level[e.to] == level[u] + 1
```

### 7.1. Những bất biến quan trọng

1. Dung lượng dư của mọi cạnh không âm.
2. Với một cặp cạnh dư thuận/ngược của cạnh gốc dung lượng c:

\[
residualForward+residualReverse=c.
\]

3. Mỗi phép augment duy trì bảo toàn luồng ở các đỉnh trung gian và tăng luồng ròng từ s tới t một lượng `pushed`.
4. DFS chỉ dùng cạnh tiến mức, nên mỗi đường tăng trong pha là **đường ngắn nhất theo số cạnh** trong đồ thị dư tại thời điểm BFS của pha.
5. Khi một pha kết thúc, không còn đường s→t trong **level graph cũ**.
6. Khi BFS không còn tới t trên **toàn bộ đồ thị dư**, luồng là cực đại.

### 7.2. Luồng có thể đi ngược trên một cạnh gốc không?

Biến lưu residual của cạnh ngược có thể tăng, thể hiện khả năng **hủy** luồng trên cạnh gốc. Điều này không có nghĩa vi phạm ràng buộc `0≤f≤c`: tổng giá trị thuận/ngược dư cho cạnh gốc giữ nguyên c, và luồng thực tế trên cạnh gốc là `f=residualReverse` nếu cặp cạnh được tạo từ trạng thái gốc f=0.

Nếu trong input còn một cạnh gốc thật sự đi ngược chiều, nó có **cặp residual khác**; không được cộng lẫn thông tin hai cặp đó.

---

## 8. Ví dụ kinh điển: max flow bằng 23

Dùng mạng 6 đỉnh (s=0, t=5):

| Cạnh có hướng | Dung lượng |
| --- | ---: |
| `0→1` | 16 |
| `0→2` | 13 |
| `1→2` | 10 |
| `2→1` | 4 |
| `1→3` | 12 |
| `3→2` | 9 |
| `2→4` | 14 |
| `4→3` | 7 |
| `3→5` | 20 |
| `4→5` | 4 |

Đây là một mạng nhỏ nhưng có **cả hai cạnh gốc 1→2 và 2→1**, các đường cùng chia cạnh, và cần nhiều hơn một pha Dinic để đạt tối ưu.

### 8.1. Pha 1: BFS trên đồ thị dư ban đầu

Ban đầu mọi cạnh thuận có dung lượng dư bằng dung lượng gốc; các cạnh ngược dư bằng 0.

BFS từ s=0 cho:

```text
vertex: 0  1  2  3  4  5
level:  0  1  1  2  2  3
```

Các đường từ 0 tới 5 **tiến đúng một mức** có độ dài 3 cạnh:

```text
0 -> 1 -> 3 -> 5
0 -> 2 -> 4 -> 5
```

Cạnh 1→2 và 2→1 đều nối **hai đỉnh ở level 1**, nên không admissible trong pha này, dù hai cạnh có dung lượng dương.

### 8.2. Đẩy blocking flow pha 1

Theo thứ tự cạnh trong ví dụ Java ở mục 12, DFS tìm:

**Đường thứ nhất:**

```text
0 -> 1 -> 3 -> 5
capacity: 16, 12, 20
bottleneck = min(16,12,20) = 12
```

Đẩy **12**. Cạnh 1→3 bị bão hòa.

**Đường thứ hai:**

```text
0 -> 2 -> 4 -> 5
capacity: 13, 14, 4
bottleneck = 4
```

Đẩy **4**. Cạnh 4→5 bị bão hòa.

Sau hai đường, không còn đường s→t trong **đồ thị mức pha 1**. Tổng của pha:

\[
12+4=\boxed{16}.
\]

**Đây chưa phải max flow.** Mạng dư vẫn cho phép đi theo một đường dài hơn.

### 8.3. Pha 2: BFS sau khi cập nhật residual

BFS mới từ 0 (với phần dư sau pha 1) cho:

```text
vertex: 0  1  2  3  4  5
level:  0  1  1  3  2  4
```

Vì 1→3 đã bão hòa, đường đi ngắn nhất còn khả dụng tới đích dài **4 cạnh**:

```text
0 -> 2 -> 4 -> 3 -> 5
```

Bottleneck của đường ấy:

- 0→2 còn 9.
- 2→4 còn 10.
- 4→3 còn 7.
- 3→5 còn 8 (đã dùng 12 ở pha 1).

Vì vậy đẩy thêm:

\[
\min(9,10,7,8)=7.
\]

Tổng sau pha 2:

\[
16+7=\boxed{23}.
\]

Đường qua 4→3 là một cạnh **tiến mức** trong pha 2, dù nó không tạo đường s→t ngắn nhất trong pha 1.

### 8.4. Kết thúc: không còn đường tăng trong đồ thị dư

BFS sau pha 2 **không tới được đích 5**, nên dừng. Các đỉnh vẫn reachable từ nguồn qua cạnh dư dương là:

\[
S=\{0,1,2,4\},
\]

còn phía bên kia:

\[
T=\{3,5\}.
\]

Các **cạnh gốc** đi từ S sang T:

| Cạnh cắt | Dung lượng gốc |
| --- | ---: |
| `1→3` | 12 |
| `4→3` | 7 |
| `4→5` | 4 |

Tổng dung lượng của lát cắt:

\[
12+7+4=\boxed{23}.
\]

Ta đã tìm được một luồng giá trị 23 và một lát cắt dung lượng 23. Vì luồng không thể vượt qua dung lượng của bất kỳ lát cắt s–t nào, hai chứng chỉ khớp nhau:

\[
\boxed{\text{max flow}=23=\text{min cut capacity}}.
\]

### 8.5. Vì sao kết quả có thể khác thứ tự đường?

Một phiên bản Dinic có thể xét cạnh kề theo thứ tự khác, hoặc chọn các đường tăng khác nhau trong từng pha. Khi có nhiều cách phân bổ luồng, **giá trị luồng cực đại vẫn giống nhau** và luôn bằng dung lượng min-cut.

Đường tăng từng lượt và cấu trúc f(e) không nhất thiết duy nhất. Kiểm thử chỉ nên ép đúng **giá trị max flow**, tính hợp lệ của residual/cut và những chi tiết thứ tự đã được cố định trong ví dụ, chứ không áp đặt một thứ tự đường cho mọi triển khai.

---

## 9. Vì sao Dinic đúng?

### 9.1. Bất biến tính khả thi

Bắt đầu luồng bằng 0; nó thỏa mọi điều kiện dung lượng và bảo toàn.

Mỗi DFS chỉ đi trên cạnh dư có `residual>0`, và lượng đẩy không quá bottleneck. Giảm residual thuận và tăng residual ngược tương ứng với tăng hoặc hủy một phần luồng trên những cạnh gốc, nên:

- Không vi phạm các giới hạn dung lượng cạnh gốc.
- Mỗi đỉnh trung gian trên một đường tăng nhận thêm một lượng bằng lượng gửi đi tiếp.
- Giá trị luồng nguồn→đích tăng đúng `pushed`.

Do đó luồng luôn khả thi qua mọi pha.

### 9.2. Bất biến đồ thị mức

BFS tìm độ dài đường ngắn nhất theo số cạnh trong đồ thị dư hiện tại:

\[
level[v]=dist_{\text{edges,residual}}(s,v)
\]

cho mỗi v reachable. DFS chỉ qua `level[to]=level[from]+1`, nên đồ thị mức không chứa chu trình có hướng và mỗi đường s→t được DFS dùng có đúng `level[t]` cạnh của pha.

### 9.3. Tính chất của blocking flow

Với con trỏ cạnh hiện hành `ptr[]`, DFS thử các cạnh admissible cho tới khi không thể đẩy thêm. Khi `sendFlow(s,∞)` trả 0 sau những lần tăng thành công, không còn đường tăng s→t **trong đồ thị mức cố định**.

Nếu còn một đường admissible có residual dương, DFS theo quy tắc xét hết cạnh và con trỏ không thể kết luận thất bại ở nguồn; điều này mâu thuẫn. Vì vậy lượng đẩy của pha là một **blocking flow**.

### 9.4. Khoảng cách tới t tăng sau mỗi pha thành công

Một kết quả then chốt của Dinic: sau khi đã tạo blocking flow của một level graph, nếu t vẫn reachable trong đồ thị dư mới, khoảng cách theo số cạnh từ s tới t **phải tăng** so với pha trước.

Trực giác:

- Những cạnh dư có chiều tăng luồng trong pha là cạnh **tiến đúng một mức**.
- Nếu còn một đường s→t ngắn bằng trước, nó phải đi qua toàn những cạnh tiến mức của pha trước; nhưng blocking flow đã chặn tất cả đường ấy.
- Cạnh dư ngược mới có thể xuất hiện nhưng đi **lùi một mức** so với lớp của cạnh thuận vừa dùng, không tạo một đường mới ngắn bằng trước.

Vì độ dài đường đơn s→t nhiều nhất V−1, số pha BFS thành công là **O(V)**.

### 9.5. Điều kiện dừng bảo đảm tối ưu

Khi BFS không còn đường dư s→t, lấy S là tập đỉnh reachable từ s và T là phần còn lại. Khi ấy:

- Mọi cạnh gốc từ S sang T có residual thuận **0**, vì nếu còn dương thì đầu đích cũng reachable.
- Mọi cạnh gốc từ T sang S có luồng **0**: nếu nó có luồng dương, cạnh dư ngược từ S sang T sẽ dương, làm đầu đích reachable, mâu thuẫn.

Vì vậy luồng ròng qua lát cắt bằng đúng tổng dung lượng các cạnh gốc S→T:

\[
|f|
=\sum_{u\in S,v\in T}c(u,v).
\]

Mặt khác với **mọi** luồng khả thi và mọi lát cắt s–t, `|f|≤capacity(S,T)`. Do ta có một luồng và một lát cắt cùng giá trị, luồng là **cực đại**, lát cắt là **nhỏ nhất**.

Đây là cách kiểm chứng bằng **định lý max-flow/min-cut**, không phải chỉ dựa vào việc “chạy DFS hết đường”.

---

## 10. Độ phức tạp

Đặt V là số đỉnh, E là số **cạnh gốc có hướng**. Trong residual graph, mỗi cạnh gốc sinh đúng hai cạnh dư, nên số mục cạnh dư là `2E`; hệ số 2 không đổi bậc tiệm cận.

### 10.1. Chi phí BFS mỗi pha

BFS xét mỗi đỉnh tối đa một lần và duyệt các cạnh dư từ những đỉnh reachable:

\[
O(V+E).
\]

### 10.2. Chi phí tìm một blocking flow

Với **current-arc optimization**, trong một pha mỗi chỉ số `ptr[u]` chỉ tăng, nên tổng số lần một cạnh bị bỏ qua là `O(E)`.

Mỗi DFS tăng thành công thường **bão hòa ít nhất một cạnh** trên đường tìm thấy. Một pha có tối đa O(E) lần tăng hữu ích; một đường có tối đa O(V) cạnh, nên cận tổng quát cho blocking flow có thể lấy là:

\[
O(VE).
\]

Cận này là cận trên bảo thủ, nhưng đủ để suy ra thời gian tổng quát của Dinic.

### 10.3. Số pha

Sau mỗi blocking flow thành công, khoảng cách BFS từ s tới t **tăng nghiêm ngặt**, nếu t còn reachable. Khoảng cách đó không vượt V−1, nên số pha thành công:

\[
O(V).
\]

### 10.4. Tổng thời gian tổng quát

Gộp:

\[
\boxed{
T_{\text{Dinic}}=O(V^2E)
}
\]

trong trường hợp xấu nhất của đồ thị có hướng tổng quát, dưới mô hình thao tác số học hằng số.

Đây là cận **không phụ thuộc vào giá trị max flow hoặc độ lớn dung lượng** theo số vòng tăng kiểu Ford–Fulkerson đơn giản. Trong thực tế Dinic thường nhanh hơn cận xấu nhất trên nhiều mạng vừa/thưa.

### 10.5. Bộ nhớ

- Danh sách kề residual: `O(V+E)`.
- Mảng `level[]`: `O(V)`.
- Mảng `ptr[]`: `O(V)`.
- Queue BFS: `O(V)`.
- Ngăn xếp DFS đệ quy ở triển khai mẫu: tối đa `O(V)` độ sâu.

Tổng:

\[
\boxed{O(V+E)}
\]

bộ nhớ của lõi thuật toán, chưa kể danh sách cạnh gốc nếu người gọi giữ lại để in chứng chỉ cut.

### 10.6. Các mạng đặc biệt

Trên một số cấu trúc như **unit network** dùng trong ghép cặp hai phía, Dinic có cận tốt hơn, điển hình `O(E\sqrt V)` dưới những giả thiết chuyên biệt của mạng đơn vị. Không được áp dụng máy móc cận ấy cho **mọi** đồ thị chỉ vì dung lượng của các cạnh đều bằng 1.

Đối với bài ghép cặp hai phía, thuật toán **Hopcroft–Karp** có cách tư duy phân lớp và tăng luồng theo pha tương tự, nhưng được thiết kế chuyên biệt cho mạng ghép cặp.

---

## 11. Chi tiết triển khai đúng trên Java

### 11.1. Lưu cạnh dư dưới dạng cặp đối tượng

Một lựa chọn thường gặp là lưu:

```java
class Edge {
    int to;
    int revIndex;
    long residual;
}
```

và dùng `revIndex` trỏ sang cạnh ngược trong danh sách kề của đỉnh bên kia. Cách này nhanh, nhưng phải tính chỉ số rất cẩn thận, đặc biệt với **self-loop `u==v`**.

Bản minh họa dưới đây dùng một cách khác, dễ kiểm chứng hơn:

```java
class Edge {
    int to;
    long residual;
    Edge reverse;
}
```

Khi thêm một cạnh gốc, tạo **hai đối tượng** và nối tham chiếu ngược lẫn nhau:

```java
Edge f = new Edge(to, capacity);
Edge r = new Edge(from, 0);
f.reverse = r;
r.reverse = f;
graph.get(from).add(f);
graph.get(to).add(r);
```

Nhờ tham chiếu trực tiếp, **cạnh song song**, **self-loop** và **cạnh gốc đối hướng** đều có cặp reverse đúng mà không cần cộng/trừ chỉ số mảng kề bằng tay.

### 11.2. Long và overflow

Dung lượng cạnh, bottleneck và tổng luồng trong chương trình dùng `long`. Tuy nhiên tổng nhiều nguồn cấp có thể vượt `Long.MAX_VALUE` dù từng dung lượng cạnh vừa một `long`.

Mã dùng:

```java
totalFlow = Math.addExact(totalFlow, pushed);
```

để ném lỗi khi tổng không biểu diễn được, thay vì âm thầm tràn số. Cập nhật residual ngược cũng dùng `Math.addExact`.

Nếu bài toán thực sự cho tổng luồng lớn hơn 64 bit, phải cân nhắc `BigInteger` hoặc giới hạn dữ liệu rõ ràng. Bất kỳ cách nào dùng sentinel “INF” cũng phải tương thích với miền số; ở đây `Long.MAX_VALUE` chỉ là **giới hạn ban đầu cho DFS**, không phải một dung lượng cạnh giả được cộng vào tổng.

### 11.3. Nguồn bằng đích

Phần lớn phát biểu max flow giả định `s≠t`. Nếu một hàm DFS trả ngay `limit` khi `u==t` và main liên tục gọi DFS với s==t, có thể tăng giả vô hạn.

Vì vậy API mẫu **từ chối source==sink** bằng `IllegalArgumentException` thay vì cho phép một vòng lặp không hợp lệ. Nếu muốn quy ước kết quả 0 cho trường hợp này, cần xử lý sớm trước khi chạy thuật toán.

### 11.4. Gọi một lần trên cùng residual network

Một lần `maxFlow(s,t)` sẽ **thay đổi residual graph**. Hàm không phải pure function. Bản mẫu đánh dấu đối tượng đã giải để:

- Không vô tình gọi lại `maxFlow` trên residual đã thay đổi như thể graph gốc.
- Không thêm cạnh sau khi đã giải rồi tiếp tục dùng chứng chỉ cut cũ.
- Chỉ cho truy xuất **min-cut của đúng nguồn đã giải**.

Muốn giải bài toán khác, hãy tạo một đối tượng Dinic mới và nạp lại các cạnh gốc.

---

## 12. Java 17+ hoàn chỉnh: Dinic, blocking flow và min-cut

Tệp chạy độc lập: **`DinicLevelBlockingFlowDemo.java`**.

Chương trình sử dụng `ArrayList` cho residual adjacency, `ArrayDeque` cho BFS, `int[] level` và `int[] ptr`, DFS chỉ theo cạnh tăng đúng một mức, lưu tổng luồng mỗi pha để đối chiếu **[16, 7]** trong ví dụ 6 đỉnh, rồi in **tập reachable từ s** và các cạnh gốc băng qua min-cut.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class DinicLevelBlockingFlowDemo {

    public record Arc(int from, int to, long capacity) {
    }

    public static final class Dinic {
        private static final class Edge {
            final int to;
            long residual;
            Edge reverse;

            Edge(int to, long residual) {
                this.to = to;
                this.residual = residual;
            }
        }

        private final int n;
        private final List<List<Edge>> graph;
        private final int[] level;
        private final int[] ptr;
        private final List<Long> phaseFlows = new ArrayList<>();

        private boolean solved;
        private int solvedSource = -1;

        public Dinic(int n) {
            if (n < 0) {
                throw new IllegalArgumentException(
                        "negative vertex count");
            }

            this.n = n;
            this.level = new int[n];
            this.ptr = new int[n];
            this.graph = new ArrayList<>(n);

            for (int i = 0; i < n; i++) {
                graph.add(new ArrayList<>());
            }
        }

        private void checkVertex(int v) {
            if (v < 0 || v >= n) {
                throw new IllegalArgumentException(
                        "vertex out of range: " + v);
            }
        }

        public void addEdge(int from, int to, long capacity) {
            if (solved) {
                throw new IllegalStateException(
                        "network already solved");
            }

            checkVertex(from);
            checkVertex(to);

            if (capacity < 0) {
                throw new IllegalArgumentException(
                        "negative capacity");
            }

            // One reverse pair per original directed edge.
            // References also work for parallel edges, self-
            // loops and original edges in both directions.
            Edge forward = new Edge(to, capacity);
            Edge backward = new Edge(from, 0L);

            forward.reverse = backward;
            backward.reverse = forward;

            graph.get(from).add(forward);
            graph.get(to).add(backward);
        }

        private boolean buildLevels(int source, int sink) {
            Arrays.fill(level, -1);

            ArrayDeque<Integer> queue = new ArrayDeque<>();
            queue.addLast(source);
            level[source] = 0;

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();

                for (Edge e : graph.get(u)) {
                    if (e.residual > 0
                            && level[e.to] == -1) {
                        level[e.to] = level[u] + 1;
                        queue.addLast(e.to);
                    }
                }
            }

            return level[sink] != -1;
        }

        private long sendFlow(
                int u, int sink, long limit) {
            if (u == sink) {
                return limit;
            }

            List<Edge> edges = graph.get(u);

            for (; ptr[u] < edges.size(); ptr[u]++) {
                Edge e = edges.get(ptr[u]);

                if (e.residual <= 0
                        || level[e.to] != level[u] + 1) {
                    continue;
                }

                long pushed = sendFlow(
                        e.to, sink,
                        Math.min(limit, e.residual));

                if (pushed > 0) {
                    e.residual -= pushed;
                    e.reverse.residual = Math.addExact(
                            e.reverse.residual, pushed);
                    return pushed;
                }
            }

            return 0L;
        }

        public long maxFlow(int source, int sink) {
            if (solved) {
                throw new IllegalStateException(
                        "maxFlow was already called");
            }

            checkVertex(source);
            checkVertex(sink);

            if (source == sink) {
                throw new IllegalArgumentException(
                        "source and sink must differ");
            }

            long totalFlow = 0L;

            while (buildLevels(source, sink)) {
                Arrays.fill(ptr, 0);
                long phaseFlow = 0L;

                while (true) {
                    long pushed = sendFlow(
                            source, sink, Long.MAX_VALUE);

                    if (pushed == 0) {
                        break;
                    }

                    totalFlow = Math.addExact(
                            totalFlow, pushed);
                    phaseFlow = Math.addExact(
                            phaseFlow, pushed);
                }

                phaseFlows.add(phaseFlow);
            }

            solved = true;
            solvedSource = source;
            return totalFlow;
        }

        public List<Long> phaseFlows() {
            if (!solved) {
                throw new IllegalStateException(
                        "solve the network first");
            }
            return List.copyOf(phaseFlows);
        }

        // Reachable vertices in the final residual graph.
        public boolean[] minCutSourceSide(int source) {
            if (!solved || source != solvedSource) {
                throw new IllegalStateException(
                        "no completed maxFlow for this source");
            }

            boolean[] reachable = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();

            reachable[source] = true;
            queue.addLast(source);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();

                for (Edge e : graph.get(u)) {
                    if (e.residual > 0
                            && !reachable[e.to]) {
                        reachable[e.to] = true;
                        queue.addLast(e.to);
                    }
                }
            }

            return reachable;
        }
    }

    private static String sourceSideString(boolean[] side) {
        List<Integer> result = new ArrayList<>();

        for (int v = 0; v < side.length; v++) {
            if (side[v]) {
                result.add(v);
            }
        }

        return result.toString();
    }

    private static String cutEdgesString(
            List<Arc> original, boolean[] sourceSide) {

        List<String> result = new ArrayList<>();

        for (Arc e : original) {
            if (sourceSide[e.from()]
                    && !sourceSide[e.to()]) {
                result.add(
                        e.from() + "->" + e.to()
                                + "(" + e.capacity() + ")");
            }
        }

        return result.toString();
    }

    private static long cutCapacity(
            List<Arc> original, boolean[] sourceSide) {

        long result = 0;

        for (Arc e : original) {
            if (sourceSide[e.from()]
                    && !sourceSide[e.to()]) {
                result = Math.addExact(
                        result, e.capacity());
            }
        }

        return result;
    }

    public static void main(String[] args) {
        List<Arc> original = List.of(
                new Arc(0, 1, 16),
                new Arc(0, 2, 13),
                new Arc(1, 2, 10),
                new Arc(2, 1, 4),
                new Arc(1, 3, 12),
                new Arc(3, 2, 9),
                new Arc(2, 4, 14),
                new Arc(4, 3, 7),
                new Arc(3, 5, 20),
                new Arc(4, 5, 4));

        Dinic network = new Dinic(6);

        for (Arc e : original) {
            network.addEdge(
                    e.from(), e.to(), e.capacity());
        }

        long maxFlow = network.maxFlow(0, 5);
        boolean[] sourceSide =
                network.minCutSourceSide(0);
        long minCut = cutCapacity(original, sourceSide);

        System.out.println("Max flow: " + maxFlow);
        System.out.println(
                "Phase flows: " + network.phaseFlows());
        System.out.println(
                "Source side: "
                        + sourceSideString(sourceSide));
        System.out.println(
                "Min-cut edges: "
                        + cutEdgesString(original, sourceSide));
        System.out.println("Min-cut capacity: " + minCut);
        System.out.println(
                "Flow equals cut: " + (maxFlow == minCut));

        // Parallel edges are independent capacities.
        Dinic parallel = new Dinic(3);
        parallel.addEdge(0, 1, 3);
        parallel.addEdge(0, 1, 5);
        parallel.addEdge(1, 2, 7);
        System.out.println(
                "Parallel flow: " + parallel.maxFlow(0, 2));

        // A zero-capacity edge cannot carry flow.
        Dinic zero = new Dinic(2);
        zero.addEdge(0, 1, 0);
        System.out.println(
                "Zero-capacity flow: " + zero.maxFlow(0, 1));

        // Self-loop is supported and cannot help 0->1.
        Dinic loop = new Dinic(2);
        loop.addEdge(0, 0, 100);
        loop.addEdge(0, 1, 2);
        System.out.println(
                "Self-loop flow: " + loop.maxFlow(0, 1));

        // No residual path from 0 to 3.
        Dinic disconnected = new Dinic(4);
        disconnected.addEdge(0, 1, 8);
        disconnected.addEdge(2, 3, 9);
        System.out.println(
                "Disconnected flow: "
                        + disconnected.maxFlow(0, 3));

        boolean negativeRejected = false;
        try {
            new Dinic(2).addEdge(0, 1, -2);
        } catch (IllegalArgumentException ex) {
            negativeRejected = true;
        }
        System.out.println(
                "Negative capacity rejected: "
                        + negativeRejected);

        boolean sameVertexRejected = false;
        try {
            new Dinic(2).maxFlow(0, 0);
        } catch (IllegalArgumentException ex) {
            sameVertexRejected = true;
        }
        System.out.println(
                "Same source/sink rejected: "
                        + sameVertexRejected);

        boolean emptyGraphRejected = false;
        try {
            new Dinic(0).maxFlow(0, 1);
        } catch (IllegalArgumentException ex) {
            emptyGraphRejected = true;
        }
        System.out.println(
                "Empty graph query rejected: "
                        + emptyGraphRejected);
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac DinicLevelBlockingFlowDemo.java
java DinicLevelBlockingFlowDemo
```

**Đầu ra chuẩn chính xác** theo thứ tự cạnh đã khai báo và mã ở trên:

```text
Max flow: 23
Phase flows: [16, 7]
Source side: [0, 1, 2, 4]
Min-cut edges: [1->3(12), 4->3(7), 4->5(4)]
Min-cut capacity: 23
Flow equals cut: true
Parallel flow: 7
Zero-capacity flow: 0
Self-loop flow: 2
Disconnected flow: 0
Negative capacity rejected: true
Same source/sink rejected: true
Empty graph query rejected: true
```

### 12.1. Giải thích mã

**Cặp Edge có liên kết hai chiều:** Một cạnh input u→v tạo hai đối tượng Edge; mỗi Edge giữ tham chiếu `reverse` tới đối tượng kia. Khi augment, cập nhật đồng thời:

```java
e.residual -= pushed;
e.reverse.residual =
        Math.addExact(e.reverse.residual, pushed);
```

Cấu trúc này giữ đúng reverse cả khi `u==v`, khi có hai cạnh song song và khi có cạnh gốc hai hướng.

**BFS:** Duyệt chỉ cạnh `e.residual>0`, xây `level[]`. Nếu t không reachable, kết thúc toàn bộ.

**DFS:** Chỉ đi qua cạnh `level[e.to]==level[u]+1` và residual dương. `ptr[]` nhớ vị trí cạnh đang thử; reset một lần trước blocking flow của pha.

**Mỗi pha:** Lặp DFS cho tới khi trả 0. `phaseFlows` ghi tổng gửi trong pha ấy, phục vụ học thuật và đối chiếu với kết quả 16 rồi 7.

**Min-cut:** Sau khi maxFlow kết thúc, chạy BFS trên residual từ **đúng nguồn s**. Những đỉnh còn reachable thuộc phía S; tính tổng dung lượng các **cạnh gốc từ S sang T** để được chứng chỉ min-cut. Không tính dung lượng hiện tại của các cạnh dư và không cộng những cạnh gốc hướng T→S.

### 12.2. Vì sao không lưu current flow riêng cho từng cạnh?

Cặp residual thuận/ngược đã đủ để tiến hành augment và undo. Nếu muốn in luồng trên **từng cạnh gốc**, hãy lưu tham chiếu tới forward Edge của nó. Với cạnh gốc dung lượng c:

\[
f(e)=c-residualForward(e)
=residualReverse(e).
\]

Các cạnh gốc song song cần tham chiếu riêng để không nhầm luồng của chúng. Trong bài mẫu, ta chỉ cần giá trị tổng và min-cut, nên không cần một mảng flow[] gốc riêng.

### 12.3. Tại sao dùng long?

Từng capacity có thể lớn hơn `Integer.MAX_VALUE`. Mã dùng `long` cho residual, bottleneck và total; `Math.addExact` báo lỗi khi tổng vượt miền. Không dùng giá trị âm để biểu thị “vô hạn” hay “cạnh không tồn tại” vì dung lượng yêu cầu không âm.

### 12.4. Không thể sửa input sau khi giải rồi coi kết quả còn đúng

Dinic thay đổi trạng thái residual. Bản mẫu chặn gọi lại `maxFlow` và chặn `addEdge` sau khi đã giải. Nếu cần giải một bài mới hoặc đổi dung lượng, tạo **đối tượng mới** từ dữ liệu cạnh gốc.

### 12.5. Hạn chế với đường rất sâu

`sendFlow` dùng đệ quy. Độ sâu đệ quy là chiều dài một đường s→t trong đồ thị mức, có thể tới V−1. Với một đường dây rất lớn, JVM có thể ném `StackOverflowError`. Khi yêu cầu xử lý V cực lớn, thay bằng **DFS lặp với stack tường minh** và giữ cơ chế ptr, level, bottleneck, rollback đúng.

---

## 13. Từ max flow đến min cut

Một **lát cắt s–t** là phân hoạch V thành S và T sao cho:

\[
s\in S,\quad t\in T.
\]

**Dung lượng lát cắt** là tổng dung lượng gốc của những cạnh có hướng **từ S sang T**:

\[
c(S,T)=\sum_{u\in S,v\in T}c(u,v).
\]

Cạnh có hướng **T→S không được cộng** vào capacity của lát cắt S→T, dù nó có thể ảnh hưởng đến các ràng buộc luồng bên trong mạng.

### 13.1. Bất đẳng thức flow ≤ cut

Mọi đơn vị luồng ròng từ s sang t đều phải vượt qua lát cắt S→T. Do các cạnh đi xuôi cut có tổng khả năng tối đa là `c(S,T)`, với một luồng khả thi bất kỳ:

\[
|f|\le c(S,T).
\]

Đây là **cận trên** đối với giá trị luồng cực đại.

### 13.2. Chứng chỉ sau khi thuật toán kết thúc

Khi không còn đường tăng, S là tập đỉnh reachable trong residual từ s. Mọi cạnh gốc S→T đều **bão hòa** (residual thuận 0), còn mọi cạnh gốc T→S không có luồng (vì nếu có sẽ xuất hiện residual ngược từ S sang T). Vì thế:

\[
|f|=c(S,T).
\]

Ta có đồng thời:

- Một luồng **khả thi** giá trị F.
- Một lát cắt có **dung lượng F**.

Hai đối tượng này xác nhận ngay tính tối ưu: không luồng nào lớn hơn F, vì sẽ vượt cận trên của cut.

### 13.3. Không phải mọi cut đều là min cut

Nếu chọn S bất kỳ chứa nguồn và không chứa đích, nó chỉ cho một **cận trên**; có thể lớn hơn max flow. Chọn **tập đỉnh reachable từ s trên residual cuối cùng** là cách đáng tin để trích xuất **một min-cut**.

Khi có nhiều min-cut cùng dung lượng, tập S tìm được không nhất thiết là min-cut duy nhất. Giá trị **min-cut capacity** luôn bằng max flow, nhưng cách phân hoạch S/T có thể không duy nhất.

### 13.4. Cut với cạnh dung lượng 0

Một cạnh có dung lượng gốc 0 băng qua cut được tính với đóng góp 0. Việc nó có tồn tại trong input hay không không thay đổi capacity của cut, nhưng API vẫn có thể giữ cạnh 0 để bảo toàn cấu trúc input.

---

## 14. Những trường hợp biên quan trọng

### 14.1. Không có đường từ s tới t

BFS đầu tiên trả `level[t]=-1`. Luồng cực đại là 0. Tập S reachable từ s (qua cạnh dư dương) có thể chứa nhiều đỉnh khác ngoài s, nhưng t không nằm trong S. Min-cut với capacity 0 là chứng chỉ đúng.

### 14.2. Cạnh dung lượng 0

Cạnh gốc có dung lượng 0 được chấp nhận trong input nhưng residual thuận ban đầu 0, vì vậy BFS/DFS không dùng nó. Không được nhầm “cạnh 0” với cạnh có **luồng 0 nhưng dung lượng dương**: trường hợp thứ hai vẫn có thể đẩy.

### 14.3. Cạnh song song

Mỗi cạnh có thể tạo một cặp residual riêng. Ví dụ `0→1` dung lượng 3 và 5, `1→2` dung lượng 7, max flow từ 0 tới 2 là **7**; không phải 8 vì cạnh 1→2 là bottleneck.

### 14.4. Self-loop

Cạnh `u→u` không giúp tạo đường s→t có tiến mức, bởi level[u] không thể bằng level[u]+1. Nó có thể nằm trong input nhưng không góp vào luồng cực đại. Cặp Edge tham chiếu nhau vẫn đúng khi self-loop xuất hiện.

### 14.5. Cạnh gốc đối hướng

Có `u→v` và `v→u` trong input không có nghĩa chúng là một cặp forward/reverse duy nhất. **Mỗi cạnh gốc phải có reverse riêng**, bởi hai dung lượng gốc độc lập và việc hủy luồng phải gắn đúng với cạnh đã được sử dụng trước đó.

### 14.6. Source==sink

Bài max flow chuẩn yêu cầu nguồn và đích khác nhau. Nếu không, hàm DFS có thể trả bottleneck “vô hạn” ngay lập tức dù không đi qua cạnh. Chọn quy ước báo lỗi hoặc giá trị 0, nhưng phải xử lý **trước** vòng lặp. Code mẫu báo lỗi.

### 14.7. Mạng có nhiều thành phần

Đồ thị không cần liên thông theo nghĩa vô hướng. Chỉ những đường dư từ s đến t mới liên quan đến augment. Các đỉnh cô lập hoặc thành phần tách biệt không ảnh hưởng max flow; chúng có thể nằm ở phía T của cut do không reachable từ s.

### 14.8. Dung lượng âm

Dung lượng `c<0` không phù hợp định nghĩa của bài toán chuẩn. Cần từ chối thay vì cố đưa vào BFS hoặc diễn giải nó như một chiều cạnh. Nếu bài có **chi phí âm** trên cạnh nhưng **dung lượng không âm**, đó là bài **min-cost flow**, không phải max-flow dung lượng âm.

### 14.9. Dung lượng rất lớn

Không dùng `int` cho tổng khi nhiều cạnh có dung lượng tới hàng tỷ. `long` an toàn hơn, nhưng vẫn có giới hạn. Tránh dùng phép trừ trong comparator hoặc cộng vào sentinel có thể tràn; mã mẫu dùng phép cộng kiểm tra tràn.

### 14.10. Đồ thị thay đổi trong khi tính

Nếu thêm/xóa cạnh hay đổi dung lượng khi Dinic đang chạy, các bất biến residual, level và blocking flow có thể không còn đúng. Đây là thuật toán cho **một mạng tĩnh tại thời điểm chạy**; muốn giải một mạng đã đổi, thường phải tạo lại hoặc áp dụng thuật toán incremental có chứng minh riêng.

---

## 15. Vì sao không thể bỏ reverse edge?

Giả sử ban đầu có thể dùng hai nhánh:

```text
s -> a -> b -> t
s -> b
a -> t
```

Các cạnh thích hợp đều có dung lượng 1. Nếu trước đó đã gửi 1 đơn vị theo `s→a→b→t`, ta có thể muốn sửa thành hai đường:

```text
s -> a -> t
s -> b -> t
```

Nhưng cạnh b→t trong đường thứ hai đã bị chiếm bởi đường cũ. Để sửa, dùng một đường tăng trong residual gồm bước **b→a** — cạnh ngược của a→b — để **hủy** lượng cũ trên a→b, sau đó tái phân bổ.

Một graph dư chỉ giữ các cạnh thuận sẽ không thực hiện được thao tác hủy, dễ mắc kẹt ở luồng 1 dù tồn tại luồng 2.

### 15.1. Điều gì làm ví dụ này hợp lệ?

Các cạnh gốc:

```text
s -> a (1)
s -> b (1)
a -> b (1)
a -> t (1)
b -> t (1)
```

Đường đầu `s→a→b→t` gửi 1, làm bão hòa s→a, a→b, b→t. Trong residual, có đường:

```text
s -> b -> a -> t
```

với cạnh b→a là **reverse** của a→b. Đẩy 1 qua đường này:

- Tăng luồng trên s→b và a→t.
- Hủy luồng trên a→b.
- Hai đường cuối cùng tương đương s→a→t và s→b→t, tổng luồng 2.

Cách gán mới vẫn thỏa bảo toàn và dung lượng.

### 15.2. Vì sao Dinic không cần dùng ngay reverse trong pha đầu?

Trong Dinic, DFS chỉ đi cạnh tiến đúng mức. Reverse edge mới xuất hiện sau khi augment thường đi **lùi một mức** so với lớp hiện tại; nó không được dùng ngay trong cùng pha nếu không admissible. Pha sau BFS có thể phát hiện một đường khác mà reverse edge trở thành cạnh tiến mức mới.

Đừng xem reverse edge là “không dùng trong Dinic”; chúng là phần không thể thiếu của **đồ thị dư** và tính tối ưu.

---

## 16. So sánh Dinic với các thuật toán liên quan

| Thuật toán | Cách chọn đường hoặc cải thiện | Cận tổng quát thường dùng |
| --- | --- | --- |
| Ford–Fulkerson cơ bản | Bất kỳ đường tăng có dư | Phụ thuộc dữ liệu/lựa chọn đường; với dung lượng nguyên có cận theo giá trị flow |
| Edmonds–Karp | BFS lấy **một** đường ngắn nhất mỗi lượt | `O(VE²)` |
| **Dinic** | BFS mức, DFS đẩy **blocking flow** mỗi pha | **`O(V²E)`** |
| Push–relabel | Đẩy luồng dư cục bộ và thay nhãn độ cao | Nhiều biến thể/cận khác nhau |
| Hopcroft–Karp | Phân lớp và tăng theo pha trên ghép cặp hai phía | `O(E√V)` cho bài matching hai phía |

### 16.1. Khi nào Dinic thường là lựa chọn tốt?

- Nhiều bài max flow trên graph vừa đến lớn với dung lượng nguyên `long`.
- Mạng có cấu trúc phân lớp hoặc cần giải nhiều đường tăng cùng một pha.
- Bài toán quy về max flow: ghép cặp, phân công công việc, chọn dự án có phụ thuộc, cắt mạng, phân chia tài nguyên.
- Khi cần cả **max flow** lẫn một **min-cut** làm chứng chỉ.

### 16.2. Khi nào cần cân nhắc giải pháp khác?

- **Ghép cặp hai phía đơn thuần:** Hopcroft–Karp có cài đặt chuyên biệt và cận rất tốt.
- **Luồng cực tiểu chi phí:** Dinic tối đa hóa lượng, không tối ưu hóa **chi phí** cho một giá trị luồng.
- **Đồ thị cực lớn với đường sâu:** cần bản DFS lặp hoặc thư viện tối ưu để tránh StackOverflowError.
- **Nhiều lần thay đổi dung lượng và truy vấn lại:** một cấu trúc incremental hoặc tái xây mạng có thể phù hợp hơn.
- **Dung lượng thực hoặc tổng vượt 64 bit:** cần kiểu số và chứng minh ổn định phù hợp.

---

## 17. Quy trình kiểm thử đáng tin

### 17.1. Kiểm thử mẫu bằng định lý min-cut

Với mạng sáu đỉnh:

1. Chạy Dinic, thu `F=23`.
2. Từ s trên residual cuối cùng, tìm S = `\{0,1,2,4\}`.
3. Tính dung lượng các cạnh **gốc** từ S sang T: `12+7+4=23`.
4. Kiểm tra `F==cutCapacity`.
5. Kiểm tra sink không nằm trong S.
6. Nếu lưu luồng từng cạnh, kiểm tra ràng buộc 0≤f≤c và bảo toàn tại đỉnh trung gian.

**Flow==cut** là một chứng chỉ mạnh khi flow khả thi và cut đúng hướng.

### 17.2. Trường hợp cần thử

| Mạng | Kỳ vọng |
| --- | --- |
| Không có cạnh từ s tới t | Max flow 0 |
| Chỉ một cạnh s→t dung lượng 5 | Max flow 5 |
| Hai cạnh song song 3,5 từ s→t | Max flow 8 |
| `s→a(3),a→t(2)` | Max flow 2 |
| `s→a(0),a→t(5)` | Max flow 0 |
| Cạnh self-loop lớn cùng đường s→t nhỏ | Self-loop không làm tăng kết quả |
| Cạnh gốc cả hai hướng u↔v | Không nhầm cặp reverse residual |
| Mạng ví dụ 6 đỉnh | Max flow 23, min cut 23 |
| Hai thành phần không có đường s→t | Max flow 0 |
| Dung lượng rất lớn | Kết quả long chính xác hoặc lỗi overflow tường minh |
| Nguồn bằng đích | Báo lỗi theo hợp đồng code |
| Đỉnh ngoài `[0,V)` | Báo lỗi |
| Dung lượng âm | Báo lỗi |
| Đồ thị rỗng V=0 | Không có truy vấn nguồn/đích hợp lệ |

### 17.3. Oracle độc lập cho mạng nhỏ

Đối với graph nhỏ (V≤10), có thể tính **min-cut bằng vét cạn**:

1. Giữ s trong S và t ngoài S.
2. Duyệt mọi cách gán V−2 đỉnh còn lại vào S hoặc T (có `2^{V-2}` lựa chọn).
3. Với mỗi lát cắt, cộng dung lượng **các cạnh gốc có hướng S→T**.
4. Lấy capacity nhỏ nhất.
5. Đối chiếu với giá trị max flow của Dinic.

Vì định lý max-flow/min-cut, oracle vét cạn trên các cut cho ra đúng max flow. Phương pháp này **khác cách tính của Dinic** và hữu ích để tìm lỗi BFS, DFS, reverse edge, xét hướng hoặc overflow trên nhiều mạng ngẫu nhiên nhỏ.

### 17.4. Oracle theo luồng khả thi

Với mạng rất nhỏ có dung lượng nguyên bé, có thể liệt kê phân bổ f(e) trên từng cạnh gốc trong `0..c(e)`, chỉ giữ những phân bổ bảo toàn tại mọi đỉnh trung gian và lấy giá trị lớn nhất. Cách này rất tốn, nhưng độc lập về mặt tư duy và giúp kiểm tra từng cập nhật residual.

### 17.5. Kiểm thử ngẫu nhiên

Sinh mạng có:

- V từ 2 tới 8.
- Dung lượng từ 0 tới 10.
- Nhiều cạnh song song.
- Một số self-loop.
- Cạnh gốc hai hướng.
- Cạnh tới/from nguồn/đích theo nhiều cấu trúc.
- Đỉnh cô lập.

So `Dinic.maxFlow` với min-cut vét cạn và kiểm tra minCutSourceSide. Chỉ dùng số vừa phải để không khiến oracle tràn hoặc quá chậm.

---

## 18. Các lỗi thường gặp

1. **Chạy BFS trên cạnh gốc có c>0** thay vì cạnh có **residual hiện tại >0**.
2. **Không tạo reverse edge** nên không thể hủy luồng đã phân bổ sai.
3. **Tạo reverse edge nhưng cập nhật sai đối tượng**, làm residual cặp không nhất quán.
4. **Nhầm một cạnh gốc đối hướng với reverse của cạnh khác**, nhất là khi input đã có cả u→v và v→u.
5. **Không xử lý self-loop khi lưu revIndex**; dùng tham chiếu reverse trực tiếp có thể tránh lỗi này.
6. **Dùng DFS qua cạnh bất kỳ còn dư**, không yêu cầu `level[to]=level[u]+1`.
7. **Đi cạnh về mức thấp hơn** trong DFS pha, có thể phá cấu trúc blocking flow và phân tích độ phức tạp.
8. **Không đặt lại ptr[] sau BFS mới**, khiến bỏ sót cạnh admissible của pha sau.
9. **Đặt lại ptr[] sau mỗi đường tăng** trong cùng pha, gây quét cạnh lặp nhiều lần và mất tối ưu.
10. **Chỉ gọi DFS một lần cho mỗi BFS**, chưa tạo blocking flow nhưng vẫn tuyên bố đã chặn mọi đường.
11. **Tuyên bố blocking flow là max flow**, dù có thể còn đường dài hơn.
12. **Nhầm bão hòa một cạnh ra khỏi nguồn với hoàn thành blocking flow**, trong khi vẫn còn nhiều đường.
13. **Không kiểm tra residual>0**, dùng cả cạnh đã bão hòa trong BFS/DFS.
14. **Cập nhật residual thuận mà quên cộng reverse**, làm mất khả năng hoàn tác.
15. **Đẩy quá bottleneck** trên một đường, khiến residual âm.
16. **Không loại source==sink**, khiến DFS trả limit ngay lập tức mà không đi qua cạnh.
17. **Dùng int cho tổng flow lớn**, làm overflow.
18. **Cộng vào long mà không kiểm soát miền số** khi tổng có thể vượt 64 bit.
19. **Đếm cạnh gốc T→S vào min-cut capacity**, sai định nghĩa cut có hướng.
20. **Tính min-cut từ BFS ở đầu pha trước** thay vì BFS trên residual **cuối cùng** sau khi dừng.
21. **Coi mọi đỉnh không reachable là cạnh bị bão hòa**, dù đó là tính chất của cạnh **băng qua cut S→T**, không phải mọi cạnh trong T.
22. **Giữ graph gốc nhưng quên update residual sau augment**, làm lặp đi lặp lại một đường.
23. **Nhầm đường ngắn nhất theo số cạnh với đường có bottleneck lớn nhất**, hai mục tiêu khác nhau.
24. **Quên đỉnh t không reachable**, cố DFS dù BFS đã báo không có đường.
25. **Không phân biệt dung lượng 0 với không có cạnh**, dẫn tới xử lý sai input.
26. **Đặt reverse cap bằng dung lượng gốc ngay từ đầu**, khiến tạo ra khả năng hủy luồng chưa tồn tại.
27. **Tự biến graph có hướng thành vô hướng**, thay đổi lượng luồng có thể vận chuyển.
28. **Không chứng minh bảo toàn luồng** khi triển khai nhiều augmentation.
29. **Dùng DFS đệ quy trên mạng đường cực dài** mà không tính nguy cơ StackOverflowError.
30. **Sử dụng min-cut không kiểm tra đúng nguồn đã giải**, dễ lấy sai phía S.
31. **Gọi maxFlow nhiều lần trên cùng residual** rồi coi lần thứ hai là flow tổng từ đầu.
32. **Áp cận O(E√V) của một mạng đơn vị cho mọi graph Dinic**, sai điều kiện.
33. **Chỉ test mạng tuyến tính** nên không phát hiện lỗi cạnh ngược, nhiều đường song song, self-loop hoặc pha thứ hai.
34. **Kết luận tối ưu chỉ vì không còn đường trong level graph của một pha**; phải BFS lại trên toàn residual.
35. **Không kiểm tra luồng ròng vào/ra nguồn** nếu muốn audit dòng chảy trên từng cạnh gốc.
36. **Tin một thứ tự đường tăng duy nhất là đặc tả thuật toán**, trong khi kết quả có thể khác thứ tự dù cùng maxflow.

---

## 19. Bài tập tự kiểm tra

### Bài 1 — Dung lượng và bảo toàn

Một đỉnh trung gian v nhận 3 và 5 đơn vị từ hai cạnh vào. Nó có thể gửi tổng 9 đơn vị ra ngoài không? Vì sao?

### Bài 2 — Bottleneck

Đường `s→a→b→t` có dung lượng dư lần lượt `[7,4,9]`. Đẩy tối đa được bao nhiêu? Cạnh nào sẽ bão hòa sau khi đẩy mức tối đa?

### Bài 3 — Reverse edge

Cạnh gốc u→v dung lượng 8 đã gửi 5. Dung lượng dư thuận và ngược bằng bao nhiêu? Nếu hủy 2 đơn vị, chúng thay đổi ra sao?

### Bài 4 — Level graph

BFS từ s cho `level[u]=2`, `level[v]=3`. Cạnh dư u→v dung lượng 4 có admissible không? Nếu `level[v]=2` thì sao?

### Bài 5 — Cạnh ngược trong level graph

Vì sao cạnh dư mới được tạo theo chiều ngược của một cạnh từng dùng trong pha thường không admissible **ngay trong pha đó**?

### Bài 6 — Blocking flow

Một pha đã đẩy 10 đơn vị và làm mọi đường s→t trong level graph bị chặn. Có đủ cơ sở kết luận maxflow=10 chưa? Cần làm gì tiếp?

### Bài 7 — Mạng mẫu sáu đỉnh

Ở pha 1 của mạng mục 8, BFS cho dãy level nào? Hai đường tăng chính và giá trị đẩy là gì?

### Bài 8 — Pha tiếp theo

Trên mạng mẫu, vì sao pha 2 có đường `0→2→4→3→5`? Bottleneck bằng bao nhiêu và tổng flow cuối là bao nhiêu?

### Bài 9 — Min-cut

Sau khi Dinic dừng trên mạng mẫu, tập S reachable từ 0 là gì? Những cạnh gốc nào đi từ S sang T và tổng capacity là bao nhiêu?

### Bài 10 — Định lý max-flow/min-cut

Nếu có luồng khả thi giá trị 23 và một lát cắt capacity 23, giải thích tại sao luồng ấy cực đại và lát cắt ấy cực tiểu.

### Bài 11 — Current arc

Tại sao `ptr[u]` có thể được giữ giữa nhiều DFS trong cùng pha? Khi nào phải reset ptr và vì sao?

### Bài 12 — Hai cạnh song song

Có hai cạnh gốc s→a dung lượng 3 và 5, cùng cạnh a→t dung lượng 7. Max flow là bao nhiêu?

### Bài 13 — Cạnh đối hướng

Nếu input có cạnh gốc u→v dung lượng 4 và v→u dung lượng 6, chúng có được dùng chung một cặp Edge/reverse không? Giải thích.

### Bài 14 — Dung lượng 0

Mạng chỉ có một cạnh s→t dung lượng 0. BFS có tới t không? Max flow bằng bao nhiêu?

### Bài 15 — Self-loop

Một cạnh u→u dung lượng 100 có giúp tăng giá trị flow từ s tới t không? Trong level graph nó có thể thỏa `level[to]=level[u]+1` không?

### Bài 16 — Thời gian

Nêu cận tổng quát O(V²E) của Dinic từ số pha, chi phí blocking flow và BFS. Vì sao không lấy O(VE) làm cận tổng một cách máy móc?

### Bài 17 — Đếm dung lượng cut

Cho cut S,T. Có một cạnh gốc S→T dung lượng 5 và một cạnh gốc T→S dung lượng 8. Capacity của cut này tính hai cạnh như thế nào?

### Bài 18 — Không có đường

Nếu BFS ban đầu không thể tới sink dù có vài cạnh gần nguồn, kết quả max flow và min-cut capacity là gì?

### Bài 19 — Kiểm thử độc lập

Với V=6, mô tả thuật toán vét cạn tất cả cut s–t có thể kiểm tra giá trị Dinic. Có bao nhiêu lựa chọn gán các đỉnh khác s và t vào S/T?

### Bài 20 — Khác với đường ngắn nhất

Dinic tìm đường ngắn nhất theo số cạnh trong residual. Điều đó có nghĩa nó tối thiểu hóa tổng **trọng số chi phí** vận chuyển không? Nếu bài cần vừa lượng tối đa vừa chi phí thấp nhất thì cần gì?

### Bài 21 — Java long

Tại sao `Math.addExact` được dùng khi cộng totalFlow? Nó bảo đảm điều gì, và khi tổng vượt long thì API có thể xử lý ra sao?

### Bài 22 — Mạng cần reverse

Trên mạng có các cạnh `s→a`, `s→b`, `a→b`, `a→t`, `b→t` đều dung lượng 1, nếu đã đẩy trước `s→a→b→t` thì còn cách đạt flow 2 không? Chỉ ra đường dư dùng reverse.

### Bài 23 — Đồ thị có hướng

Tại sao không được tự thêm cạnh ngược với cùng dung lượng rồi gọi đó là residual reverse của cạnh gốc? Cách đúng để tạo reverse là gì?

### Bài 24 — Phân biệt BFS các pha

Điều gì chứng minh độ dài đường ngắn nhất s→t trong residual **tăng** khi chuyển từ pha Dinic đã blocking sang pha tiếp theo?

### Bài 25 — Nguồn bằng đích

Nếu s==t, vì sao một DFS có nhánh `if(u==t) return limit` không được đưa vào vòng lặp maxFlow thông thường mà không xử lý biên?

### Đáp án gợi ý

1. Không. Theo bảo toàn luồng, tổng ra bằng tổng vào =8, nếu v không phải nguồn hay đích.
2. Bottleneck 4; cạnh a→b dung lượng dư 4 bị bão hòa.
3. Sau gửi 5: dư thuận 3, dư ngược 5. Hủy 2: dư thuận 5, dư ngược 3.
4. Admissible khi dư dương và v ở mức 3. Nếu v ở mức 2, cạnh không tăng đúng một mức, nên không admissible.
5. Cạnh ngược của một cạnh tiến mức j→j+1 thường đi từ j+1 về j, không tăng mức của pha cũ.
6. Chưa. Phải BFS lại trên toàn residual; có thể còn đường s→t dài hơn.
7. Levels `[0,1,1,2,2,3]`. Đẩy 12 trên 0→1→3→5 và 4 trên 0→2→4→5; tổng pha 16.
8. Sau pha 1, các cạnh dư trên đường 0→2→4→3→5 có bottleneck 7. Đẩy thêm 7, tổng 23.
9. `S={0,1,2,4}`. Cạnh S→T: 1→3(12), 4→3(7), 4→5(4), capacity 23.
10. Bất kỳ luồng nào đều ≤capacity của mọi cut. Luồng 23 và cut 23 khớp cận trên, nên cả hai tối ưu.
11. Trong pha, cạnh không còn giúp đẩy theo level cố định có thể bỏ qua về sau; reset ptr sau BFS mới vì level và residual đã đổi.
12. Max flow 7, bị giới hạn bởi a→t.
13. Không. Mỗi cạnh gốc là một tài nguyên dung lượng riêng và phải tạo cặp residual thuận/ngược riêng; nếu gộp hai hướng sẽ nhầm luồng đã gửi với luồng được phép hủy.
14. BFS không tới sink qua cạnh dư 0; max flow 0.
15. Không. Self-loop luôn có cùng đỉnh đầu/cuối nên không thể có `level[u]=level[u]+1`.
16. O(V) pha do độ dài đường tăng tăng; mỗi pha blocking flow O(VE), BFS O(V+E), tổng O(V²E).
17. Chỉ cộng cạnh S→T dung lượng 5; cạnh T→S dung lượng 8 không thuộc capacity của cut S→T.
18. Max flow 0; tập reachable tạo cut có capacity 0 vì không có cạnh dư dương S→T.
19. Có `2^{V-2}=2^4=16` cut: giữ s∈S, t∈T, tự chọn phía cho bốn đỉnh còn lại; lấy capacity nhỏ nhất.
20. Không. Độ dài BFS chỉ đếm số cạnh của đường tăng. Muốn tối ưu chi phí với luồng tối đa, dùng thuật toán **min-cost max-flow** phù hợp, không phải Dinic thuần.
21. `Math.addExact` phát hiện tổng long overflow và ném `ArithmeticException`, tránh trả con số sai do tràn. Nếu yêu cầu tổng vượt 64 bit, cân nhắc BigInteger hoặc ràng buộc đầu vào.
22. Có. Đường dư tiếp theo `s→b→a→t` dùng b→a là reverse của a→b; cuối cùng có thể phân bổ s→a→t và s→b→t, tổng 2.
23. Cạnh gốc u→v dung lượng c sinh **forward residual c** và **reverse residual 0** ở chiều v→u, tăng reverse chỉ khi đã gửi luồng. Không tự thêm cạnh vật lý v→u dung lượng c.
24. Blocking flow đã chặn mọi đường ngắn nhất trong level graph cũ; cạnh ngược mới xuất hiện đi lùi lớp, nên đường còn lại nếu có phải dài hơn.
25. Nếu s==t, DFS trả limit mà không đi cạnh, khiến vòng tăng luồng có thể cộng “vô hạn” và lặp. API nên từ chối hoặc trả 0 trước khi chạy.

---

## Ghi nhớ

**Dinic = BFS xây đồ thị mức + DFS đẩy luồng chặn + lặp các pha.** BFS chỉ qua cạnh dư **dương**, gán `level[s]=0`. DFS chỉ qua cạnh dư có `level[to]=level[from]+1`, dùng `ptr[]` để không quét lại vô ích trong cùng pha. Một pha kết thúc khi **không còn đường tăng trong đồ thị mức cố định**, nhưng phải **BFS lại** vì có thể còn đường dài hơn. Mọi lần đẩy đều cập nhật **cặp residual thuận/ngược**, cho phép thay đổi những phân bổ trước đó. Khi BFS cuối không tới t, tập đỉnh còn reachable từ s cho **min-cut**, và:

\[
\boxed{\text{giá trị luồng cực đại}=\text{dung lượng lát cắt nhỏ nhất}.}
\]

Với graph tổng quát, cận thời gian quen thuộc là **`O(V^2E)`**, bộ nhớ lõi **`O(V+E)`**. Chương trình Java 17 minh họa dùng `long`, `ArrayDeque`, `ArrayList` và current-edge pointer để tìm max flow **23** cùng min-cut **23** trên mạng 6 đỉnh, đồng thời xử lý cạnh song song, self-loop, dung lượng 0, không có đường s→t và dữ liệu không hợp lệ.

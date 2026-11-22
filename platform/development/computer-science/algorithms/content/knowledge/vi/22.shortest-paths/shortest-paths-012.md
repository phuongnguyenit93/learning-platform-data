# Khôi phục đường đi và xử lý nhiều lời giải bằng nhau

Trong bài toán **đường đi ngắn nhất**, tìm được một con số `dist[t]` chưa chắc đã đáp ứng yêu cầu. Đề bài có thể còn muốn biết **đi qua những đỉnh nào**, có bao nhiêu cách đi tối ưu, phải in cách đi nào khi **nhiều đường có cùng tổng trọng số**, hoặc phải xử lý các cạnh trọng số 0 khiến quan hệ “cha” không rõ ràng.

Chủ đề này thuộc nhóm **Đường đi ngắn nhất**. Ta sẽ học từ cách lưu `parent[]` đơn giản trong BFS/Dijkstra đến một cách xử lý vững chắc cho đồ thị có hướng với cạnh không âm, kể cả **cạnh trọng số 0, chu trình 0, cạnh song song và nhiều đáp án bằng nhau**:

1. Tính **khoảng cách ngắn nhất** từ nguồn `s`.
2. Lập **đồ thị cạnh chặt (tight-edge graph)** gồm những cạnh `u→v` thỏa `dist[u]+w(u,v)=dist[v]`.
3. Trên đồ thị cạnh chặt, dùng BFS tìm số cạnh **ít nhất** trong những đường có tổng trọng số ngắn nhất.
4. Trong những đường đạt **đồng thời khoảng cách và số cạnh tối ưu**, chọn dãy đỉnh **nhỏ nhất theo thứ tự từ điển** bằng khoảng cách ngược từ đích và lựa chọn tham lam có chứng minh.
5. Nếu cần, **đếm số dãy đỉnh tối ưu** (theo ba điều kiện: khoảng cách nhỏ nhất, số cạnh ít nhất, rồi chọn một đại diện từ điển) modulo `1_000_000_007`.

Có chương trình **Java 17+ độc lập**, có ví dụ stdout, oracle duyệt đường đi đơn để so kết quả trên **4.114 đồ thị có hướng nhỏ / 36.929 truy vấn nguồn–đích**, và phần phân tích ranh giới của cách khôi phục bằng `parent[]`, đếm đường đi và trọng số âm.

Điểm cốt lõi: **“nhiều lời giải bằng nhau” phải đi kèm tiêu chí bằng nhau cụ thể**. Hai đường cùng tổng trọng số nhưng khác số cạnh có thể được xem là hòa theo một đề bài, nhưng không hòa theo một đề yêu cầu ưu tiên **ít cạnh nhất**. Không được tự áp quy tắc chọn một cha bất kỳ rồi khẳng định đó là lời giải nhỏ nhất từ điển.

## 1. Định nghĩa đường đi ngắn nhất và các dạng lời giải

Cho đồ thị `G=(V,E)`, một đỉnh nguồn `s` và đỉnh đích `t`. Mỗi cạnh có trọng số `w(u,v)`. Trong phần thuật toán chính và code Java, **tất cả trọng số không âm**; đồ thị có hướng, nhưng đồ thị vô hướng có thể được biểu diễn bằng cách thêm hai cạnh đối xứng.

Một **walk** từ `s` đến `t` là dãy:

```text
s = v0 -> v1 -> ... -> vk = t
```

Mỗi cặp liên tiếp phải là một cạnh có hướng trong đồ thị. Tổng trọng số:

```text
weight(v0,...,vk)
    = w(v0,v1) + w(v1,v2) + ... + w(v[k-1],vk)
```

**Đường đi đơn (simple path)** không lặp đỉnh. Một walk có thể lặp đỉnh và cạnh, trong khi thuật ngữ “path” đôi khi được tài liệu dùng rộng hơn. Khi bài toán đếm hoặc cho phép cạnh trọng số 0, phải xác định **walk hay simple path** vì kết quả có thể khác rất lớn.

Khoảng cách ngắn nhất:

```text
dist[t] = min tổng trọng số mọi walk hợp lệ từ s tới t
```

Nếu không có walk từ `s` tới `t`, coi `dist[t]=INF` theo quy ước thuật toán.

Với trọng số **không âm**, luôn tồn tại một **đường đi đơn** đạt khoảng cách ngắn nhất khi `t` reachable: nếu walk tối ưu lặp đỉnh, xóa một chu trình không âm sẽ không làm tổng trọng số tăng; nếu chu trình có trọng số 0, xóa còn giúp giảm số cạnh.

### Một đáp số, nhiều cách biểu diễn

| Yêu cầu đề bài | Cần trả gì? | Thông tin bổ sung |
| --- | --- | --- |
| Chỉ cần khoảng cách | `dist[t]` | BFS/Dijkstra/Bellman–Ford tùy trọng số |
| Cần một đường ngắn nhất | Dãy `s,...,t` | `parent[]` hoặc khôi phục từ cấu trúc cạnh tối ưu |
| Cần ít cạnh nhất nếu nhiều đường cùng trọng số | `dist[t]` rồi `hops[t]` | BFS trên đồ thị cạnh chặt |
| Cần đường nhỏ nhất từ điển với cùng `dist` và `hops` | Dãy đỉnh tối ưu theo thứ tự từ điển | Khoảng cách ngược + greedy |
| Cần số đường tối ưu theo `dist` và `hops` | Số dãy đỉnh, có thể modulo `M` | DP/BFS trên các lớp `hops` |
| Cần đếm **mọi shortest walks** | Có thể vô hạn khi có chu trình trọng số 0 | Phải kiểm định bài toán |
| Cần đường đi trọng số âm | Không dùng Dijkstra thông thường | Bellman–Ford hoặc thuật toán phù hợp |

**Điều kiện ràng buộc của bài học:** Ta định nghĩa đáp án theo ba tầng ưu tiên:

```text
1. Tổng trọng số nhỏ nhất.
2. Trong các cách đạt tổng nhỏ nhất, ít cạnh nhất.
3. Trong các cách đạt hai điều kiện trên, dãy ID đỉnh
   nhỏ nhất theo thứ tự từ điển.
```

Nếu bài gốc yêu cầu thứ tự ưu tiên khác, chẳng hạn **chỉ** nhỏ nhất từ điển trong toàn bộ shortest simple paths mà **không ưu tiên ít cạnh**, phải dùng phương pháp khác và chứng minh lại. Không gọi hai bài toán này là một.

## 2. Phương pháp cơ bản: lưu parent khi phát hiện đỉnh

Một cách khôi phục phổ biến là lưu `parent[v]`, đỉnh mà từ đó ta lần đầu hoặc cuối cùng cải thiện `dist[v]`.

### BFS trên đồ thị không trọng số

Với đồ thị không trọng số hoặc mỗi cạnh có chi phí bằng nhau, BFS cho khoảng cách ngắn nhất tính theo **số cạnh**:

```text
dist[s] = 0
parent[s] = -1
queue = [s]

while queue không rỗng:
    u = popFront()

    for v trong adj[u]:
        nếu v chưa thăm:
            dist[v] = dist[u] + 1
            parent[v] = u
            đánh dấu đã thăm NGAY lúc enqueue
            pushBack(v)
```

Khi `t` được thăm, khôi phục:

```text
path = []
cur = t

while cur != -1:
    path.append(cur)
    cur = parent[cur]

reverse(path)
```

Nhớ kiểm tra `t` reachable trước. Nếu `t` không thể tới được mà `parent[t]` vẫn bằng `−1`, việc ghép ra `[t]` và gọi đó là đường `s→t` là **sai**; phải trả “unreachable”.

### Dijkstra trên đồ thị trọng số không âm

Trong Dijkstra, mỗi lần tìm được **khoảng cách tốt hơn nghiêm ngặt**:

```text
candidate = dist[u] + w(u,v)

if candidate < dist[v]:
    dist[v] = candidate
    parent[v] = u
    push(v, dist[v]) vào priority queue
```

Sau khi Dijkstra kết thúc, `parent[]` có thể dùng để khôi phục **một** đường đạt trọng số nhỏ nhất, với điều kiện các cập nhật và giới hạn số học đều đúng. Tuy nhiên:

- Kết quả có thể thay đổi khi **thứ tự adjacency/priority queue** đổi;
- Mặc định không biết đó có phải đường **ít cạnh nhất** trong các shortest paths không;
- Không bảo đảm dãy đỉnh **nhỏ nhất theo từ điển**;
- Không tự cho biết số lời giải bằng nhau;
- Nếu tự ý cập nhật `parent[v]` khi `candidate==dist[v]`, có thể tạo **chu trình parent** khi có cạnh trọng số 0.

Do vậy `parent[]` là lựa chọn tốt cho yêu cầu “**in bất kỳ một đường ngắn nhất**”, nhưng chưa đủ cho mọi loại tie-breaking.

## 3. Lỗi khi sửa parent trên các lần hòa: chu trình trọng số 0

Xét đồ thị có hướng:

```text
3 -> 1 (0)
3 -> 2 (0)
1 -> 2 (0)
2 -> 1 (0)
1 -> 0 (1)
2 -> 0 (1)
```

Từ nguồn `3`, hai đường tới đích `0` có cùng tổng trọng số 1 và cùng số cạnh 2:

```text
3 -> 1 -> 0
3 -> 2 -> 0
```

Đường nhỏ nhất theo từ điển là `[3,1,0]`. Nhưng các cạnh `1→2` và `2→1` cũng là cạnh **chặt** vì mọi đỉnh `1,2` có `dist=0`.

Một phiên bản Dijkstra cập nhật cha khi:

```text
if candidate <= dist[v]:
    parent[v] = u
```

có thể lần lượt đặt `parent[1]=2` và `parent[2]=1`. Khi đi ngược cha từ 1 hoặc 2, thuật toán lặp **1→2→1→...**, mặc dù khoảng cách vẫn đúng. Thậm chí luật “chọn ID cha nhỏ hơn” cũng không tự giải quyết vấn đề nếu nguồn có ID lớn và các cạnh chặt tạo chu trình.

**Bài học:** Một giá trị `dist[v]` bằng nhau không có nghĩa quan hệ cha `parent[u]→parent[v]` vẫn là cây. Phải xem cấu trúc đường đi tối ưu, đặc biệt khi có cạnh trọng số 0.

### Vì sao không giải bằng cách chỉ sort adjacency?

Sort các hàng xóm giúp **đầu ra xác định hơn**, nhưng việc hàng xóm có ID nhỏ không bảo đảm dãy hoàn chỉnh từ nguồn nhỏ nhất từ điển. Hai đường có cha cuối khác nhau có thể có tiền tố rất khác nhau:

```text
s -> 1 -> 9 -> t
s -> 2 -> 3 -> t
```

Nếu cả hai cùng tổng trọng số và số cạnh, đường qua 1 nhỏ hơn từ điển, dù cha trực tiếp của t là 9 **lớn hơn** 3. So `parent[t]` bằng ID không đủ để so **toàn dãy**.

Một thuật toán chọn theo từ điển phải tính đến **phần đầu tiên khác nhau trong toàn dãy đỉnh** hoặc dùng một cấu trúc/qui tắc có chứng minh phù hợp.

## 4. Ví dụ đầy đủ: nhiều đường hòa, cạnh trùng và chu trình 0

Xét đồ thị có hướng 9 đỉnh `0..8`, nguồn `s=0`, với các cạnh:

```text
0 -> 1 (2)
0 -> 1 (2)     // hai cạnh song song giống nhau
0 -> 2 (2)
0 -> 3 (1)
1 -> 4 (2)
2 -> 4 (2)
3 -> 5 (1)
5 -> 4 (2)
4 -> 6 (1)
1 -> 6 (5)
2 -> 6 (5)
0 -> 7 (0)
7 -> 0 (0)     // chu trình tổng trọng số 0
7 -> 1 (2)
7 -> 2 (2)
7 -> 7 (0)     // self-loop trọng số 0
đỉnh 8 không có cạnh
```

Các đường tới 6:

| Dãy đỉnh | Tổng trọng số | Số cạnh |
| --- | ---: | ---: |
| `[0,1,4,6]` | 2+2+1 = **5** | **3** |
| `[0,2,4,6]` | 2+2+1 = **5** | **3** |
| `[0,3,5,4,6]` | 1+1+2+1 = **5** | 4 |
| `[0,7,1,4,6]` | 0+2+2+1 = **5** | 4 |
| `[0,7,2,4,6]` | 0+2+2+1 = **5** | 4 |
| `[0,1,6]` | 2+5 = 7 | 2 |

Đặc biệt, có vô số **walk** ngắn nhất theo trọng số 5 nếu cho phép lặp chu trình `0→7→0` bất kỳ số lần rồi đi tiếp tới 6. Nhưng các walk ấy có **nhiều cạnh hơn**, vì vậy không cạnh tranh với điều kiện thứ hai “ít cạnh nhất”.

Theo quy tắc ba tầng của bài:

```text
Tổng trọng số nhỏ nhất = 5.
Trong các cách đạt trọng số 5, số cạnh nhỏ nhất = 3.
Có hai dãy đỉnh đạt đồng thời: [0,1,4,6] và [0,2,4,6].
Đại diện nhỏ nhất từ điển = [0,1,4,6].
Số dãy đỉnh đạt khoảng cách + số cạnh tối ưu = 2.
```

Ta chủ ý đếm **dãy đỉnh khác nhau**, không đếm **cạnh có ID riêng**. Do có hai bản sao cạnh `0→1` cùng trọng số, nếu đếm dãy **cạnh** thì đường qua 1 có thể được tính thành hai lựa chọn; trong bài học này, `[0,1,4,6]` chỉ được tính **một lần**.

### Khoảng cách Dijkstra từ 0

```text
vertex:    0  1  2  3  4  5  6  7  8
dist:      0  2  2  1  4  2  5  0  INF
minHops:   0  1  1  1  2  2  3  1  -1
ways:      1  1  1  1  2  1  2  1   0
```

`ways` là số dãy đỉnh có **trọng số nhỏ nhất và số cạnh nhỏ nhất** từ 0 đến từng đỉnh, tính modulo `1_000_000_007`. Ở đỉnh 4 có hai dãy `[0,1,4]` và `[0,2,4]`. Ở đỉnh 6 có hai dãy tương ứng thêm đỉnh 6.

Đỉnh 8 không reachable: `dist[8]=INF`, `minHops[8]=-1`, `ways[8]=0`. Với `s=t=0`, đường rỗng cạnh `[0]` có trọng số 0, số cạnh 0, và chỉ có một dãy đỉnh tối ưu theo hai tiêu chí đầu dù tồn tại chu trình trọng số 0.

## 5. Bước 1: tính khoảng cách, không cập nhật cha khi hòa

Với đồ thị có hướng không âm, chạy Dijkstra từ nguồn `s`:

```text
dist[s] = 0, các đỉnh khác INF
priority queue ban đầu chứa (s,0)

while heap không rỗng:
    (u,d) = pop min
    nếu d != dist[u]: bỏ bản ghi cũ

    for edge u -> v có trọng số w >= 0:
        cand = d + w      // phải kiểm soát overflow
        nếu cand < dist[v]:
            dist[v] = cand
            push (v,cand)
```

**Không cần lưu `parent[]` ở bước này**. Dijkstra chỉ đảm bảo mảng `dist[]` đúng; bài toán tie-breaking được xử lý một cách tường minh ở các bước sau.

### Tại sao Dijkstra vẫn đúng khi có cạnh 0?

Dijkstra yêu cầu `w≥0`, **không** bắt buộc `w>0`. Khi lấy một đỉnh có khoảng cách nhỏ nhất khỏi heap, không có đường thông qua các đỉnh còn lại có thể làm khoảng cách nó nhỏ hơn vì các cạnh tiếp theo không âm.

Cạnh trọng số 0 có thể tạo nhiều đỉnh có `dist` bằng nhau hoặc chu trình 0. Dijkstra vẫn tính khoảng cách chính xác. Điểm khó nằm ở **khôi phục/đếm đường** chứ không phải khoảng cách.

### Chú ý tràn số trong Java

Sai nếu viết trực tiếp:

```java
long candidate = distance + weight;
```

Với số quá lớn, `long` có thể overflow và biến giá trị dương thành âm. Khi đó phép relax có thể nhận một “đường ngắn” giả.

Chương trình dùng:

```java
long sum = Math.addExact(distance, weight);
```

và dành `Long.MAX_VALUE` làm sentinel `INF`; nếu kết quả bằng sentinel hoặc phép cộng vượt miền `long`, chương trình báo `ArithmeticException` rõ ràng. Đây là **giới hạn dữ liệu được công bố**, không phải lời hứa hỗ trợ mọi tổng trọng số lớn tùy ý. Để hỗ trợ số lớn hơn, cần chuyển toàn bộ distance/sum/comparator sang `BigInteger` hoặc một biểu diễn chính xác khác.

Bản demo chủ ý kiểm tra **mọi phép cộng ứng viên được xét** đều nằm dưới sentinel, không lặng lẽ bỏ một cạnh lớn ngay cả khi nó không tạo đường tối ưu.

## 6. Bước 2: giữ các cạnh chặt (tight edges)

Sau khi có `dist[]`, một cạnh `u→v` trọng số `w` được gọi là **chặt** nếu:

```text
dist[u] hữu hạn
dist[v] hữu hạn
dist[u] + w(u,v) == dist[v]
```

Đặt `T` là đồ thị có cùng các đỉnh nhưng chỉ giữ các cạnh chặt. Khi bắt đầu từ nguồn `s` và đi theo các cạnh của `T`:

```text
s=v0 -> v1 -> ... -> vk=v
```

ta có:

```text
dist[v1] = dist[v0] + w(v0,v1)
dist[v2] = dist[v1] + w(v1,v2)
...
dist[v]  = dist[s] + tổng trọng số = tổng trọng số
```

vì `dist[s]=0`. Nói cách khác, **mọi walk trên T từ s đến v có tổng trọng số bằng dist[v]**. Ngược lại, nếu một đường từ s tới v đạt đúng tổng ngắn nhất, từng tiền tố của đường đó cũng phải có khoảng cách tối ưu và mỗi cạnh của nó phải chặt; nếu một tiền tố không tối ưu, ta có thể thay bằng tiền tố ngắn hơn để làm ngắn cả đường.

Do đó:

> **Đồ thị các cạnh chặt mô tả chính xác những bước có thể xuất hiện trên các shortest paths từ nguồn** (với cách hiểu về walk và tiền tố như trên).

### Vì sao đồ thị cạnh chặt có thể có chu trình?

Với một cạnh chặt `u→v`:

```text
dist[v] = dist[u] + w
```

Nếu `w>0`, khoảng cách **tăng nghiêm ngặt**. Nếu `w=0`, khoảng cách có thể **bằng nhau**.

Vì vậy nếu tất cả trọng số **dương nghiêm ngặt**, `T` là DAG theo thứ tự `dist` tăng; nhưng nếu cho cạnh 0, `T` **có thể chứa chu trình 0**.

Ví dụ:

```text
dist[0] = dist[7] = 0
0 -> 7 (0) là cạnh chặt
7 -> 0 (0) cũng là cạnh chặt
```

Đồ thị `T` có chu trình `0→7→0`. **Không thể** tùy tiện sắp topo theo `dist` nếu các khoảng cách bằng nhau, và cũng không được dùng DFS đếm mọi walk mà không tránh chu trình.

### Khử cạnh song song để đếm dãy đỉnh

Nếu có hai cạnh chặt `u→v` cùng endpoint, chúng biểu diễn **cùng bước trong dãy đỉnh**. Vì bài yêu cầu đếm **dãy đỉnh**, ta **khử trùng theo `(u,v)` trong đồ thị T**.

Code dùng `TreeSet<Integer>` cho các hàng xóm chặt, vừa **sắp tăng ID** để chọn đại diện từ điển, vừa loại các bản sao cùng endpoint.

Nếu đề yêu cầu đếm **đường theo ID cạnh**, cần giữ multiplicity và thay đổi công thức đếm; không dùng kết quả bài này cho quy ước đó một cách máy móc.

## 7. Bước 3: BFS trên T để tối ưu số cạnh và đếm

Các cạnh trong `T` giờ đều có **chi phí 1 khi đếm bước**. Ta chạy BFS từ `s` để tìm `hops[v]`: số cạnh ít nhất từ `s` đến `v` trong `T`.

```text
hops[v] = -1 cho mọi v
ways[v] = 0 cho mọi v

hops[s] = 0
ways[s] = 1
queue = [s]

while queue không rỗng:
    u = popFront()

    for v trong tight[u]:       // đã khử trùng u->v
        nếu hops[v] == -1:
            hops[v] = hops[u] + 1
            ways[v] = ways[u]
            enqueue(v)

        ngược lại nếu hops[v] == hops[u] + 1:
            ways[v] = (ways[v] + ways[u]) mod M

        các trường hợp khác:
            không dùng cạnh này để tạo đường ít cạnh nhất tới v
```

**Vì sao cập nhật `ways[v]` ở một đỉnh đã được phát hiện vẫn đúng?** BFS xử lý theo các lớp `hops=0,1,2,...`. Tất cả các đỉnh ở lớp `k−1` được lấy khỏi queue **trước** mọi đỉnh lớp `k`, nên tất cả những cạnh từ lớp `k−1` có khả năng cộng vào `ways[v]` đã được xử lý trước khi `v` được dùng để truyền số cách sang lớp tiếp theo.

Mọi đường từ `s` tới `v` có ít cạnh nhất trong `T` là đường có `hops[v]` bước. Vì tất cả cạnh trên đường thuộc `T`, tổng trọng số của nó bằng `dist[v]`. Như vậy BFS trên `T` giải đúng **mục tiêu phụ ít cạnh nhất trong các shortest-distance walks**.

### Không có chu trình trong các cạnh phục vụ phép đếm

Dù `T` có chu trình 0, các cạnh được dùng để cộng `ways` đều thỏa:

```text
hops[v] = hops[u] + 1
```

Theo các cạnh ấy, `hops` tăng nghiêm ngặt. Không thể có chu trình quay về mức hop cũ. Đây là lý do **đếm số dãy đỉnh ngắn nhất theo cả khoảng cách và số cạnh** vẫn hữu hạn và chạy được bằng BFS, kể cả có chu trình 0 trong `T`.

### Tại sao không cộng cho mọi cạnh chặt?

Nếu cộng `ways[v] += ways[u]` cho **mọi** cạnh chặt `u→v`, những cạnh ngang tầng hoặc vòng lặp 0 có thể khiến số cách bị đếm lặp, thậm chí xuất hiện vô số walk có trọng số ngắn nhất.

Chỉ cộng khi `hops[v]==hops[u]+1`. Cạnh `u→v` chặt nhưng làm đến `v` bằng nhiều hop hơn **không thuộc bất kỳ lời giải nào tối ưu cả hai tiêu chí**.

### Đếm theo modulo và ý nghĩa số 0

Với `M=1_000_000_007`, phép đếm `ways[v]` trả **số dãy đỉnh tối ưu modulo M**, không phải số nguyên chính xác nếu số cách rất lớn.

Một đỉnh reachable có thể có `ways[v]==0` do số cách chia hết cho `M`. Không dùng `ways[v]==0` làm điều kiện “unreachable”; phải kiểm tra `dist[v]==INF` hoặc `hops[v]==−1`.

Nếu cần đếm chính xác số cách và kích thước input cho phép, dùng `BigInteger` thay cho modulo; nếu dùng modulo khác, điều chỉnh toán tử cộng cho đúng.

## 8. Bước 4: khôi phục đại diện nhỏ nhất từ điển

BFS từ nguồn trên `T` cho biết số hop tối thiểu và số cách, nhưng **không tự chứng minh `parent[]` thu được là dãy đỉnh nhỏ nhất từ điển**. Để chọn một đường đại diện theo ba tiêu chí đã công bố, ta sử dụng BFS **ngược từ đích `t`** trên đồ thị cạnh chặt.

### Tính số hop ngắn nhất còn lại đến đích

Từ `T`, xây `reverseTight` bằng cách đảo mỗi cạnh chặt `u→v` thành `v→u`. Sau đó chạy BFS từ `t` trên `reverseTight`:

```text
toTarget[v] = số cạnh ít nhất trên T từ v tới t
toTarget[t] = 0
toTarget[v] = -1 nếu v không thể tới t trong T
```

Nếu `t` reachable từ `s`, ta có:

```text
toTarget[s] = hops[t]
```

vì cả hai tính số cạnh ít nhất trên những đường chặt nối s tới t.

### Chọn bước đi tham lam

Bắt đầu ở `u=s`, đã biết `toTarget[u]≥0`. Trong tất cả hàng xóm `v` của `u` thuộc `tight[u]`, chọn **ID nhỏ nhất** thỏa:

```text
toTarget[v] == toTarget[u] - 1
```

Thêm `v` vào đường đi rồi gán `u=v`. Lặp cho đến `t`.

Vì `toTarget` giảm đúng 1 mỗi bước, thuật toán chắc chắn đến `t` sau **chính xác `hops[t]` cạnh** và **không thể lặp đỉnh**. Mọi bước là cạnh chặt nên tổng trọng số bằng `dist[t]`.

### Tại sao greedy cho đường nhỏ nhất từ điển?

Giả sử hiện đã cố định một tiền tố chung kết thúc ở `u`. Những hàng xóm `v` thỏa `toTarget[v]=toTarget[u]−1` là **chính xác những lựa chọn có thể hoàn tất đường tối ưu với số hop còn lại ít nhất**.

Hai đường đi có cùng tiền tố và cùng tổng số hop sẽ được so từ điển tại **đỉnh đầu tiên khác nhau**. Vì chọn hàng xóm có ID nhỏ nhất trong các lựa chọn còn có thể hoàn thành tối ưu, tiền tố sau một bước là nhỏ nhất có thể. Lặp bằng quy nạp cho từng vị trí: dãy nhận được **nhỏ nhất từ điển** trong tất cả đường đạt `dist[t]` và `hops[t]`.

**Đừng chọn đơn thuần hàng xóm nhỏ nhất trong tight[u]**. Một hàng xóm nhỏ có thể vẫn có đường chặt tới đích nhưng cần **nhiều cạnh hơn**. Điều kiện về `toTarget` là phần giữ đúng tối ưu số cạnh.

### Mục tiêu "lexicographically smallest shortest simple path" khác

Với đồ thị:

```text
0 -> 1 (0)
1 -> 2 (0)
2 -> 3 (1)
0 -> 3 (1)
```

Hai dãy `[0,1,2,3]` và `[0,3]` có cùng tổng trọng số 1. Nếu ưu tiên **ít cạnh**, chọn `[0,3]`. Nếu chỉ ưu tiên **từ điển** giữa mọi đường ngắn nhất đơn mà không quan tâm số cạnh, `[0,1,2,3]` nhỏ hơn vì sau tiền tố 0 thì `1<3`.

Hai đầu bài khác nhau có kết quả khác nhau. Thuật toán ở đây **chủ ý** chọn **ít cạnh trước, từ điển sau**.

## 9. Chứng minh đầy đủ cho quy tắc khoảng cách – hop – từ điển

Để chắc chắn không mất nghiệm, ta tách các mệnh đề:

### Mệnh đề A — mọi đường ngắn nhất dùng cạnh chặt

Giả sử đường `P=s=v0,...,vk=t` có tổng trọng số bằng `dist[t]`. Nếu tại một tiền tố đến `vi`, tổng trọng số đi trên `P` lớn hơn `dist[vi]`, thay tiền tố bằng đường ngắn hơn tới `vi` sẽ cho một **walk** tới `t` có trọng số nhỏ hơn, mâu thuẫn với việc `P` ngắn nhất. Với trọng số không âm, nếu đường thay thế tạo chu trình thì vẫn có thể xóa chu trình không âm mà không tăng trọng số.

Suy ra tổng trọng số mỗi tiền tố bằng `dist[vi]`, nên mỗi cạnh có:

```text
dist[vi] + w(vi,vi+1) = dist[vi+1]
```

Tức là cạnh chặt.

### Mệnh đề B — mọi walk trên T từ nguồn có tổng trọng số tối ưu

Với một dãy cạnh chặt `s=v0→...→vk=t`, cộng các đẳng thức:

```text
w(vi,vi+1) = dist[vi+1] - dist[vi]
```

Hai vế triệt tiêu dạng telescoping:

```text
sum weights = dist[t] - dist[s] = dist[t].
```

Do đó walk chặt luôn đạt khoảng cách ngắn nhất.

### Mệnh đề C — BFS trên T tìm đúng số hop và số cách tối thiểu

BFS xử lý theo từng lớp `hops`, nên lần đầu phát hiện `v` cho số cạnh ít nhất để tới `v` trong `T`. Mọi đường vừa tối ưu trọng số vừa tối ưu số cạnh chính là các đường ngắn nhất theo số hop trong `T` (từ A và B).

Đếm số cách bằng cách cộng trên mọi cạnh làm `hops` tăng 1 nhận đúng số dãy đỉnh tối ưu: mỗi dãy tới `v` kết thúc qua một predecessor `u` tại lớp `hops[v]−1`; những tiền tố tới `u` được đếm một lần bởi quy nạp. Nhờ khử cạnh song song theo endpoint, một dãy đỉnh không bị nhân đôi do có hai cạnh giống nhau.

### Mệnh đề D — greedy chọn dãy nhỏ nhất từ điển

Mọi đường ít cạnh nhất từ `u` đến `t` trên T phải chọn một `v` sao cho `toTarget[v]=toTarget[u]−1`. Nếu một lựa chọn không thỏa, nó không thể là bước đầu của một đường có số hop còn lại tối thiểu.

Greedy chọn **ID nhỏ nhất** trong những lựa chọn hợp lệ. Nếu tồn tại đường tối ưu khác nhỏ hơn từ điển, tại vị trí khác đầu tiên, đường ấy phải chọn ID nhỏ hơn greedy, mâu thuẫn với việc greedy đã xét toàn bộ lựa chọn hợp lệ. Vậy đường dựng được là dãy nhỏ nhất từ điển.

### Mệnh đề E — không bị vòng lặp do cạnh 0

Trên đường được khôi phục, `toTarget` giảm đúng một sau mỗi cạnh. Không thể trở lại một đỉnh đã thăm vì như thế `toTarget` phải bằng hai số khác nhau. Do đó việc khôi phục **kết thúc sau đúng `hops[t]` bước**, ngay cả khi đồ thị T có chu trình 0.

## 10. Đếm “nhiều lời giải bằng nhau”: phải xác định đúng đối tượng đếm

Có ít nhất bốn khái niệm thường bị gộp nhầm:

1. **Nhiều đường cùng khoảng cách:** Có thể khác số cạnh và khác dãy đỉnh.
2. **Nhiều đường cùng khoảng cách và cùng số cạnh ít nhất:** Đây là tập ta đếm bằng `ways[]`.
3. **Nhiều shortest walks:** Cho phép lặp đỉnh/cạnh; với chu trình 0 có thể có **vô số** walk tối ưu.
4. **Nhiều shortest simple paths:** Chỉ đếm đường không lặp đỉnh; hữu hạn với đồ thị hữu hạn nhưng việc đếm tổng quát có thể khó khi có chu trình 0.

### Một chu trình 0 tạo vô số shortest walks khi nằm trên đường tối ưu

Nếu từ nguồn `s` tới một đỉnh `u` với chi phí `d`, tại `u` có thể đi một chu trình tổng trọng số 0 và từ `u` tới đích `t` với phần còn lại tối ưu, thì ta có thể lặp chu trình 0 bất kỳ số lần để tạo **vô số walks** tổng trọng số bằng `dist[t]`.

Không dùng DP đơn giản trên tight graph có chu trình để đếm tất cả shortest walks: phép đệ quy có thể vòng vô hạn, hoặc phép cộng theo thứ tự tùy ý tạo số cách không đúng.

**Nếu đề cần đếm mọi shortest walks**, phải xác định trước có chu trình 0 trên tuyến nguồn–đích có thể đạt tối ưu hay không. Có thể xét SCC/cycle trong phần tight graph vừa reachable từ s vừa có thể tới t; nếu có chu trình 0 như vậy, số walks tối ưu là vô hạn.

### Mục tiêu ít cạnh giải quyết vấn đề đó ra sao?

Lặp bất kỳ chu trình nào đều **tăng số cạnh**. Vì tiêu chí phụ là ít cạnh nhất, không shortest min-hop path nào lặp đỉnh. Cạnh có thể dùng để đếm chỉ đi từ lớp `hops=k` sang lớp `k+1` nên tạo một DAG theo lớp, ngay cả khi tight graph gốc không phải DAG.

Điều này giúp việc đếm **min-distance/min-hop vertex sequences** vừa xác định rõ vừa dễ triển khai bằng BFS.

### Cạnh song song: dãy đỉnh hay dãy cạnh?

Có hai bản sao cạnh `0→1` cùng trọng số 2. Với `[0,1,4,6]`:

- **Đếm dãy đỉnh:** chỉ có một `[0,1,4,6]`.
- **Đếm dãy cạnh theo ID cạnh:** có thể có hai cách chọn cạnh 0→1 khác nhau.

Code minh họa **loại trùng `u→v` trong đồ thị T** để đếm dãy đỉnh. Nếu đề bài định nghĩa các cạnh song song là **những tuyến riêng biệt**, phải giữ số lượng và thay đổi cập nhật `ways`; không được sử dụng trực tiếp đáp số của demo.

## 11. Liên hệ với BFS, Dijkstra và Bellman–Ford

### BFS khi mỗi cạnh có cùng trọng số

Trong đồ thị **không trọng số**, `dist[v]` chính là số cạnh tối thiểu. Các shortest paths đã tự động có cùng hop tối ưu; không cần tối ưu thứ hai riêng biệt. Có thể dựng đường nhỏ nhất từ điển bằng:

1. BFS từ `s` lấy `distFromS`;
2. BFS trên graph đảo từ `t` lấy `distToT`;
3. Từ `u`, chọn hàng xóm nhỏ nhất `v` sao cho:

```text
distFromS[v] = distFromS[u] + 1
distFromS[v] + distToT[v] = distFromS[t]
```

Đây là cùng tinh thần **chỉ đi qua cạnh thuộc một đường tối ưu, rồi tham lam theo thứ tự từ điển**.

### Dijkstra với trọng số không âm

Dijkstra cho `dist[]`, trong đó cạnh 0 hợp lệ. Tight graph có thể có chu trình 0, nên nếu cần đếm hoặc chọn min-hop/lex thì cách dựng tight graph rồi BFS là một lựa chọn an toàn.

**Một cách thay thế:** Có thể chạy Dijkstra tối ưu trực tiếp theo cặp `(totalWeight, hopCount)`, dùng so sánh từ điển trên hai số: ưu tiên trọng số trước, rồi hop. Khi cập nhật parent, vẫn phải thiết kế cẩn thận nếu cần **từ điển toàn bộ dãy đỉnh**; so ID cha không đủ. Cách hai giai đoạn trong bài dễ chứng minh hơn.

### Bellman–Ford khi có cạnh âm

Nếu có cạnh âm, **không chạy Dijkstra thường**. Bellman–Ford có thể tính khoảng cách hữu hạn khi không có chu trình âm ảnh hưởng tới đích. Sau khi đã có `dist[]` hữu hạn và kiểm soát đúng **negative cycles**, ta vẫn có thể nói về cạnh chặt `dist[u]+w=dist[v]` và khôi phục số hop/từ điển từ những cạnh ấy trong phạm vi các đỉnh có khoảng cách hữu hạn.

Nhưng nếu có **chu trình âm reachable từ nguồn và có đường tới đích**, có thể giảm trọng số walk đến đích vô hạn bằng cách lặp chu trình âm. Khi đó **không có một khoảng cách nhỏ nhất hữu hạn** cho truy vấn đó; đừng in một đường “ngắn nhất” giả.

Nếu chu trình âm reachable từ s nhưng **không thể đi tới t**, nó không nhất thiết làm hỏng khoảng cách ngắn nhất từ s tới t. Một cài đặt Bellman–Ford nghiêm túc phải phân biệt các đỉnh bị ảnh hưởng bởi negative cycle và các truy vấn đích không bị ảnh hưởng.

**Chương trình Java dưới đây có chủ ý chỉ hỗ trợ trọng số không âm** để tập trung vào vấn đề khôi phục và hòa; nó báo lỗi khi nhận cạnh âm, không tự dùng Bellman–Ford.

### Đồ thị vô hướng có cạnh âm

Nếu một cạnh vô hướng trọng số âm được biểu diễn bằng hai cung `u→v` và `v→u`, đi qua lại hai cung tạo **chu trình âm** trong ngữ nghĩa walk, nên bài toán shortest walk thông thường có thể không có giá trị nhỏ nhất hữu hạn. Đây là một lý do phải đọc kỹ đề cho phép **walk hay simple path**, và không chuyển nguyên cách làm vô hướng sang bài có trọng số âm.

## 12. Java 17+ — chương trình đầy đủ có oracle độc lập

Chương trình **ShortestPathTiesDemo.java** thực hiện:

- Xây đồ thị có hướng có `n` đỉnh `0..n−1`; cạnh `(from,to,weight≥0)`; cho phép self-loop và cạnh song song.
- Chạy **Dijkstra** bằng `PriorityQueue`, kiểm tra overflow trên mọi phép cộng trọng số.
- Xây tight graph bằng `dist[u]+w=dist[v]`, dùng `TreeSet` để **sắp và loại cạnh trùng theo cặp đỉnh**.
- BFS từ nguồn trên tight graph để tính **`hops[]`** và **`ways[] mod 1_000_000_007`**.
- Với đích bất kỳ, BFS ngược từ đích trên tight graph, rồi greedily chọn đỉnh kề nhỏ nhất làm giảm `toTarget[]` đúng một để tìm đường đại diện nhỏ nhất từ điển.
- Đối chiếu trên **4.114 đồ thị có hướng n=0..3**: thử mọi trạng thái **vắng cạnh / trọng số 0 / trọng số 1 / trọng số 2** cho từng cặp đỉnh khác nhau, và với từng nguồn–đích so với **brute force liệt kê mọi simple path**.
- Brute oracle xét trực tiếp tổng trọng số, số cạnh, thứ tự từ điển và số dãy đỉnh tối ưu; **không dùng Dijkstra hoặc tight graph** để quyết định kết quả.

### Thiết kế API

```text
ShortestPaths(graph, source)
    .answer(target)

Answer:
    reachable = có đường từ source đến target?
    distance  = tổng trọng số nhỏ nhất (nếu reachable)
    hops      = số cạnh ít nhất trong các đường có distance tối ưu
    ways      = số dãy đỉnh đạt distance/hops tối ưu modulo 1e9+7
    path      = dãy ID đỉnh nhỏ nhất từ điển trong số các đường đó
```

Với đích **không reachable**, code trả:

```text
reachable=false
distance=-1
hops=-1
ways=0
path=[]
```

`distance=-1` chỉ là sentinel trong **Answer** vì đồ thị không có trọng số âm; bên trong mảng Dijkstra, `INF=Long.MAX_VALUE`. Đừng so `ways==0` để biết unreachable vì modulo có thể cho 0 ngay cả khi có đường.

Để đơn giản hóa ý nghĩa các ca kiểm thử, chương trình **chỉ trả một số cách theo dãy đỉnh**. Khi graph chứa nhiều cung cùng endpoint, brute oracle cũng quy về **cạnh có trọng số nhỏ nhất cho mỗi endpoint**, vì chỉ cạnh nhẹ nhất có thể xuất hiện trên đường đi tối ưu của một dãy đỉnh cho trước.

### Mã nguồn đầy đủ — ShortestPathTiesDemo.java

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.TreeMap;
import java.util.TreeSet;

public class ShortestPathTiesDemo {
    static final long MOD = 1_000_000_007L;
    static final long INF = Long.MAX_VALUE;

    record Edge(int to, long weight) {}
    record State(int vertex, long distance) {}

    record Answer(boolean reachable, long distance,
                  int hops, long ways, List<Integer> path) {}

    record Counts(int graphs, long queries) {}

    static final class Graph {
        final int n;
        final List<List<Edge>> adj;

        Graph(int n) {
            if (n < 0) {
                throw new IllegalArgumentException("n must be nonnegative");
            }
            this.n = n;
            adj = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                adj.add(new ArrayList<>());
            }
        }

        void addEdge(int from, int to, long weight) {
            if (from < 0 || to < 0 || from >= n || to >= n
                    || weight < 0) {
                throw new IllegalArgumentException(
                    "bad endpoint or negative weight");
            }
            adj.get(from).add(new Edge(to, weight));
        }
    }

    // Các phép cộng được xem xét phải biểu diễn được và < INF.
    // Không âm thầm bỏ qua cạnh khi chi phí quá giới hạn.
    static long addCost(long a, long b) {
        if (a < 0 || b < 0 || a == INF) {
            throw new IllegalArgumentException(
                "cost must be finite nonnegative");
        }
        long sum = Math.addExact(a, b);
        if (sum == INF) {
            throw new ArithmeticException(
                "Long.MAX_VALUE is reserved for INF");
        }
        return sum;
    }

    static final class ShortestPaths {
        final Graph graph;
        final int source;
        final long[] dist;
        final int[] hops;
        final long[] ways;
        final List<List<Integer>> tight;
        final List<List<Integer>> reverseTight;

        ShortestPaths(Graph graph, int source) {
            if (graph == null
                    || source < 0 || source >= graph.n) {
                throw new IllegalArgumentException("invalid source");
            }
            this.graph = graph;
            this.source = source;
            this.dist = dijkstra();
            this.tight = new ArrayList<>(graph.n);
            this.reverseTight = new ArrayList<>(graph.n);
            buildTightGraphs();

            this.hops = new int[graph.n];
            this.ways = new long[graph.n];
            Arrays.fill(hops, -1);
            countMinimumHopPaths();
        }

        private long[] dijkstra() {
            long[] result = new long[graph.n];
            Arrays.fill(result, INF);
            result[source] = 0;

            PriorityQueue<State> queue = new PriorityQueue<>(
                Comparator.comparingLong(State::distance)
                    .thenComparingInt(State::vertex)
            );
            queue.add(new State(source, 0));

            while (!queue.isEmpty()) {
                State cur = queue.remove();
                int u = cur.vertex();
                if (cur.distance() != result[u]) {
                    continue; // Bỏ bản ghi PQ đã cũ.
                }

                for (Edge edge : graph.adj.get(u)) {
                    long cand = addCost(
                        cur.distance(), edge.weight());

                    if (cand < result[edge.to()]) {
                        result[edge.to()] = cand;
                        queue.add(new State(edge.to(), cand));
                    }
                }
            }
            return result;
        }

        private void buildTightGraphs() {
            List<TreeSet<Integer>> unique = new ArrayList<>();
            for (int u = 0; u < graph.n; u++) {
                unique.add(new TreeSet<>());
                reverseTight.add(new ArrayList<>());
            }

            for (int u = 0; u < graph.n; u++) {
                if (dist[u] == INF) {
                    continue;
                }
                for (Edge edge : graph.adj.get(u)) {
                    long cand = addCost(dist[u], edge.weight());
                    if (cand == dist[edge.to()]) {
                        // TreeSet khử trùng các cung u->v.
                        unique.get(u).add(edge.to());
                    }
                }
            }

            for (int u = 0; u < graph.n; u++) {
                tight.add(List.copyOf(unique.get(u)));
            }
            for (int u = 0; u < graph.n; u++) {
                for (int v : tight.get(u)) {
                    reverseTight.get(v).add(u);
                }
            }
        }

        // BFS trên tight graph: tối ưu số hop và đếm dãy đỉnh.
        private void countMinimumHopPaths() {
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            hops[source] = 0;
            ways[source] = 1;
            queue.addLast(source);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();

                for (int v : tight.get(u)) {
                    if (hops[v] == -1) {
                        hops[v] = hops[u] + 1;
                        ways[v] = ways[u];
                        queue.addLast(v);
                    } else if (hops[v] == hops[u] + 1) {
                        ways[v] = (ways[v] + ways[u]) % MOD;
                    }
                }
            }
        }

        Answer answer(int target) {
            if (target < 0 || target >= graph.n) {
                throw new IllegalArgumentException("invalid target");
            }
            if (dist[target] == INF) {
                return new Answer(
                    false, -1, -1, 0, List.of());
            }

            // BFS ngược để biết số hop tối thiểu còn lại tới t.
            int[] toTarget = new int[graph.n];
            Arrays.fill(toTarget, -1);
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            toTarget[target] = 0;
            queue.addLast(target);

            while (!queue.isEmpty()) {
                int v = queue.removeFirst();
                for (int u : reverseTight.get(v)) {
                    if (toTarget[u] == -1) {
                        toTarget[u] = toTarget[v] + 1;
                        queue.addLast(u);
                    }
                }
            }

            if (toTarget[source] != hops[target]) {
                throw new AssertionError(
                    "forward and reverse hops disagree");
            }

            // Greedy: chọn hàng xóm nhỏ nhất vẫn đạt số hop.
            ArrayList<Integer> path = new ArrayList<>();
            int u = source;
            path.add(u);

            while (u != target) {
                int next = -1;
                for (int v : tight.get(u)) {
                    if (toTarget[v] == toTarget[u] - 1) {
                        next = v;
                        break; // tight[u] đã sort tăng.
                    }
                }
                if (next == -1) {
                    throw new AssertionError(
                        "no tight next vertex to target");
                }
                path.add(next);
                u = next;
            }

            return new Answer(
                true, dist[target], hops[target],
                ways[target], List.copyOf(path));
        }
    }

    static String show(Answer a) {
        if (!a.reachable()) {
            return "unreachable";
        }
        return "distance=" + a.distance()
            + ", hops=" + a.hops()
            + ", ways=" + a.ways()
            + ", path=" + a.path();
    }

    static String showDistances(long[] dist) {
        ArrayList<String> text = new ArrayList<>();
        for (long value : dist) {
            text.add(value == INF ? "INF" : Long.toString(value));
        }
        return text.toString();
    }

    // Brute-force oracle cho n nhỏ.
    // Với cùng cặp (u,v), giữ cạnh nhẹ nhất để đếm DÃY ĐỈNH
    // thay vì đếm ID cạnh song song.
    static final class BruteOracle {
        final List<List<Edge>> uniqueEdges = new ArrayList<>();
        final boolean[] seen;
        final ArrayList<Integer> path = new ArrayList<>();
        final int target;

        long bestCost = INF;
        int bestHops = Integer.MAX_VALUE;
        long ways = 0;
        List<Integer> bestPath = List.of();

        BruteOracle(Graph graph, int source, int target) {
            this.target = target;
            this.seen = new boolean[graph.n];

            for (int u = 0; u < graph.n; u++) {
                TreeMap<Integer, Long> minimum =
                    new TreeMap<>();

                for (Edge edge : graph.adj.get(u)) {
                    minimum.merge(
                        edge.to(), edge.weight(),
                        (x, y) -> Math.min(x, y));
                }

                ArrayList<Edge> candidates = new ArrayList<>();
                for (Map.Entry<Integer, Long> item
                        : minimum.entrySet()) {
                    candidates.add(
                        new Edge(item.getKey(), item.getValue()));
                }
                uniqueEdges.add(List.copyOf(candidates));
            }

            seen[source] = true;
            path.add(source);
        }

        private static boolean lexSmaller(
                List<Integer> a, List<Integer> b) {
            int common = Math.min(a.size(), b.size());
            for (int i = 0; i < common; i++) {
                int x = a.get(i), y = b.get(i);
                if (x != y) {
                    return x < y;
                }
            }
            return a.size() < b.size();
        }

        private void dfs(int u, long cost) {
            if (u == target) {
                int hops = path.size() - 1;

                if (cost < bestCost
                        || (cost == bestCost
                            && hops < bestHops)) {
                    bestCost = cost;
                    bestHops = hops;
                    ways = 1;
                    bestPath = List.copyOf(path);
                } else if (cost == bestCost
                        && hops == bestHops) {
                    ways = (ways + 1) % MOD;
                    if (lexSmaller(path, bestPath)) {
                        bestPath = List.copyOf(path);
                    }
                }
                return;
            }

            for (Edge edge : uniqueEdges.get(u)) {
                int v = edge.to();
                if (seen[v]) {
                    continue; // Chỉ duyệt simple paths.
                }

                long nextCost = addCost(cost, edge.weight());
                if (nextCost > bestCost) {
                    continue;
                }

                seen[v] = true;
                path.add(v);
                dfs(v, nextCost);
                path.remove(path.size() - 1);
                seen[v] = false;
            }
        }

        Answer run() {
            dfs(path.get(0), 0);
            if (bestCost == INF) {
                return new Answer(false, -1, -1, 0, List.of());
            }
            return new Answer(
                true, bestCost, bestHops, ways, bestPath);
        }
    }

    // So hai cách độc lập: Dijkstra + tight/BFS/greedy
    // và brute-force simple paths với tiêu chí 3 tầng.
    static Counts verifyAllSmallGraphs() {
        int graphCount = 0;
        long queryCount = 0;

        for (int n = 0; n <= 3; n++) {
            ArrayList<int[]> possible = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = 0; v < n; v++) {
                    if (u != v) {
                        possible.add(new int[]{u, v});
                    }
                }
            }

            int variants = 1;
            for (int i = 0; i < possible.size(); i++) {
                variants *= 4; // absent, weight 0, 1, 2.
            }

            for (int code = 0; code < variants; code++) {
                int remaining = code;
                Graph graph = new Graph(n);

                for (int[] pair : possible) {
                    int kind = remaining % 4;
                    remaining /= 4;
                    if (kind != 0) {
                        graph.addEdge(
                            pair[0], pair[1], kind - 1L);
                    }
                }

                graphCount++;
                for (int source = 0; source < n; source++) {
                    ShortestPaths fast =
                        new ShortestPaths(graph, source);

                    for (int target = 0; target < n; target++) {
                        Answer got = fast.answer(target);
                        Answer expected =
                            new BruteOracle(
                                graph, source, target).run();

                        if (!got.equals(expected)) {
                            throw new AssertionError(
                                "shortest-path mismatch: n=" + n
                                + ", code=" + code
                                + ", s=" + source
                                + ", t=" + target
                                + ", got=" + got
                                + ", expected=" + expected);
                        }
                        queryCount++;
                    }
                }
            }
        }
        return new Counts(graphCount, queryCount);
    }

    public static void main(String[] args) {
        Graph sample = new Graph(9);
        int[][] edges = {
            {0,1,2}, {0,1,2}, {0,2,2}, {0,3,1},
            {1,4,2}, {2,4,2}, {3,5,1}, {5,4,2},
            {4,6,1}, {1,6,5}, {2,6,5},
            {0,7,0}, {7,0,0}, {7,1,2}, {7,2,2},
            {7,7,0}
        };
        for (int[] e : edges) {
            sample.addEdge(e[0], e[1], e[2]);
        }

        ShortestPaths plan = new ShortestPaths(sample, 0);
        System.out.println("Distances from 0: "
                           + showDistances(plan.dist));
        System.out.println("Minimum hops: "
                           + Arrays.toString(plan.hops));
        System.out.println("Counts mod 1000000007: "
                           + Arrays.toString(plan.ways));
        System.out.println("0 -> 6: " + show(plan.answer(6)));
        System.out.println("0 -> 4: " + show(plan.answer(4)));
        System.out.println("0 -> 8: " + show(plan.answer(8)));
        System.out.println("0 -> 0: " + show(plan.answer(0)));

        // Hai đỉnh 1 và 2 nối thành chu trình zero-cost.
        // Không cần cập nhật parent trên bằng nhau.
        Graph ties = new Graph(4);
        ties.addEdge(3, 1, 0);
        ties.addEdge(3, 2, 0);
        ties.addEdge(1, 2, 0);
        ties.addEdge(2, 1, 0);
        ties.addEdge(1, 0, 1);
        ties.addEdge(2, 0, 1);

        System.out.println(
            "Tie demo 3 -> 0: "
            + show(new ShortestPaths(ties, 3).answer(0)));

        Counts counts = verifyAllSmallGraphs();
        System.out.println(
            "Exhaustive: " + counts.graphs()
            + " graphs, " + counts.queries()
            + " source-target checks OK");
    }
}
```

### Biên dịch và chạy

Lưu đúng tên **ShortestPathTiesDemo.java**. Sử dụng **JDK 17 hoặc mới hơn** (vì mã dùng `record`):

```bash
javac -encoding UTF-8 ShortestPathTiesDemo.java
java ShortestPathTiesDemo
```

**Stdout dự kiến:**

```text
Distances from 0: [0, 2, 2, 1, 4, 2, 5, 0, INF]
Minimum hops: [0, 1, 1, 1, 2, 2, 3, 1, -1]
Counts mod 1000000007: [1, 1, 1, 1, 2, 1, 2, 1, 0]
0 -> 6: distance=5, hops=3, ways=2, path=[0, 1, 4, 6]
0 -> 4: distance=4, hops=2, ways=2, path=[0, 1, 4]
0 -> 8: unreachable
0 -> 0: distance=0, hops=0, ways=1, path=[0]
Tie demo 3 -> 0: distance=1, hops=2, ways=2, path=[3, 1, 0]
Exhaustive: 4114 graphs, 36929 source-target checks OK
```

### Giải thích kết quả của code

**Khoảng cách:** `dist[6]=5` là tổng nhỏ nhất; `dist[8]=INF` vì không có đường từ 0. Chu trình 0↔7 làm nhiều shortest walks hơn nhưng không làm thay đổi `dist[]`.

**Minimum hops:** Đường `0→3→5→4→6` có tổng trọng số 5 nhưng 4 cạnh; BFS trên đồ thị T loại nó khỏi tập mục tiêu phụ vì đã có đường 3 cạnh tới 6.

**Counts:** `ways[6]=2` và `ways[4]=2` vì có hai **dãy đỉnh** tối ưu. Hai cạnh song song `0→1` chỉ đóng góp **một** dãy đỉnh.

**Đại diện từ điển:** So `[0,1,4,6]` và `[0,2,4,6]`, vị trí đầu tiên khác nhau là 1 so với 2. Vì 1 nhỏ hơn 2, đường qua 1 được chọn.

**Nguồn trùng đích:** `0→0` theo đường 0 cạnh được biểu diễn `[0]`, có tổng trọng số 0 và số hop 0. Chu trình `0→7→0` có tổng trọng số 0 nhưng nhiều hop, nên không được đếm trong `ways[0]`.

**Tie demo:** Đồ thị con với nguồn 3 có chu trình 0 giữa 1 và 2; hai đường `[3,1,0]` và `[3,2,0]` đều có chi phí 1 và 2 hop. Kết quả `[3,1,0]` nhỏ nhất từ điển, không có vòng lặp parent.

### Con số kiểm chứng exhaustive

Với `n` đỉnh, số **cặp đỉnh có hướng khác nhau** `u≠v` là `n(n−1)`. Mỗi cặp nhận một trong bốn trạng thái:

```text
không có cạnh
có cạnh trọng số 0
có cạnh trọng số 1
có cạnh trọng số 2
```

Nên có `4^(n(n−1))` đồ thị cho n cố định (chưa xét self-loop/cạnh song song). Bảng kiểm thử:

| `n` | Số đồ thị | Số truy vấn `s,t` trên mỗi graph | Tổng truy vấn |
| ---: | ---: | ---: | ---: |
| 0 | 1 | 0 | 0 |
| 1 | 1 | 1 | 1 |
| 2 | 16 | 4 | 64 |
| 3 | 4.096 | 9 | 36.864 |
| **Tổng** | **4.114** | — | **36.929** |

Oracle độc lập **duyệt tất cả simple paths** cho mỗi cặp `s,t`; trên mỗi đường tính tổng trọng số, số cạnh, dãy từ điển và tổng số nghiệm hòa. Đây là hướng kiểm tra trực tiếp đặc tả, khác lõi Dijkstra–tight graph–BFS. Các ca có **self-loop và cạnh song song** được kiểm tra riêng trên đồ thị mẫu vì bộ exhaustive chuẩn hóa mỗi cặp đỉnh có nhiều nhất một cạnh và không chứa self-loop.

**Vì sao brute chỉ duyệt simple paths vẫn đủ?** Với trọng số không âm, bất kỳ walk tối ưu theo hai tiêu chí khoảng cách–hops mà lặp đỉnh sẽ chứa một chu trình; bỏ chu trình không làm trọng số tăng và làm giảm số cạnh. Nếu chu trình dương, còn làm giảm trọng số. Vì vậy một lời giải tối ưu theo **cả hai tiêu chí** không thể lặp đỉnh. Brute simple paths do đó là oracle đầy đủ cho hợp đồng đã chọn.

## 13. Độ phức tạp và tái sử dụng cho nhiều đích

Cho `n` đỉnh, `m` cung có hướng được lưu, tính cả các cung song song.

**Tiền xử lý từ một nguồn:**

1. Dijkstra bằng priority queue có thể có tới `O(m)` bản ghi được thêm. Cận an toàn của phiên bản không decrease-key: **`O((n+m)log(n+m))`** thời gian và `O(n+m)` bộ nhớ gồm PQ.
2. Duyệt mọi cạnh để tìm tight edges: `O(n+m)` phép xét.
3. Dùng `TreeSet` để sort và deduplicate các hàng xóm chặt: thêm tối đa `m` mục, chi phí tối đa `O(m log(n+1))` cho các tập đỉnh khác nhau; phần này có thể thay bằng sort–unique hoặc hash nếu cần.
4. BFS trên T để tìm `hops[]` và `ways[]`: `O(n+m_T)`, trong đó `m_T≤m` là số cặp đỉnh chặt đã khử trùng.
5. Tổng tiền xử lý có thể chặn gọn bằng **`O((n+m)log(n+m))`**, không tính độ rộng bit của các phép cộng số học; bộ nhớ **`O(n+m)`**.

**Mỗi truy vấn đích `t` sau khi tiền xử lý:**

- BFS ngược trên reverse tight graph để tính `toTarget[]`: `O(n+m_T)`.
- Greedy dựng đường: đi qua đúng `hops[t]` cạnh; duyệt các neighbor tại những đỉnh trên đường, tổng không vượt `O(n+m_T)`.
- Do đó trả cả đường đại diện từ điển có độ phức tạp **`O(n+m_T)`/đích** ở phiên bản đơn giản. Nếu chỉ cần khoảng cách/hops/ways, truy xuất trực tiếp mảng đã tính là **`O(1)`/đích**.

Khi có rất nhiều truy vấn đích cho **cùng nguồn**, có thể cache `toTarget[]` theo những đích được hỏi lặp lại, hoặc thiết kế cấu trúc khác để chọn lex path theo nhiều đích. Không nên tự nhận mọi truy vấn đường đại diện là `O(1)` chỉ vì Dijkstra đã chạy một lần.

**Bộ nhớ:** Graph `O(n+m)`, tight/reverse graph `O(n+m_T)`, mảng `dist/hops/ways` `O(n)`, queue/stack/PQ tương ứng; tổng `O(n+m)`.

### Khi chỉ cần một đường bất kỳ

Nếu đề chỉ yêu cầu **bất kỳ một shortest path**, không có tie-break/đếm, dùng `parent[]` từ những lần **cải thiện nghiêm ngặt** trong BFS/Dijkstra thường ngắn và nhanh hơn. Cách xây tight graph + hai BFS dành cho trường hợp có nhiều ràng buộc tie và cần một lời giải có tính chất xác định.

## 14. Tình huống biên cần xử lý

### Đồ thị rỗng `n=0`

Không có đỉnh nên **không có nguồn `s` hoặc đích `t` hợp lệ**. Constructor tạo `Graph(0)` được, nhưng không gọi `ShortestPaths(graph,0)`; chương trình ném `IllegalArgumentException` vì nguồn ngoài miền. Bộ exhaustive có một đồ thị rỗng nhưng **không có truy vấn `s,t`** ở đó.

### Nguồn bằng đích

Đường 0 cạnh `[s]` có trọng số 0 và hop 0, là đường tối ưu theo hai tiêu chí khi trọng số không âm, kể cả có chu trình 0. Số dãy đỉnh min-distance/min-hop là 1.

### Không thể tới đích

Nếu `dist[t]=INF`, không dựng đường bằng `parent[t]`. Trả rõ `reachable=false` và `path=[]`. Trong code, `distance/hops=-1` là sentinel của kết quả; `ways=0`, nhưng không sử dụng ways để suy đoán reachability.

### Nhiều cạnh cùng endpoint

Nếu cạnh `u→v` có trọng số 3 và 5, chỉ cạnh 3 có thể xuất hiện trong một đường tối ưu dùng cặp đỉnh đó. Nếu có hai bản sao cùng trọng số 3, với hợp đồng đếm **dãy đỉnh**, chúng vẫn là một bước `u,v`. Code TreeSet khử trùng cặp endpoint **sau khi kiểm tra tight**.

### Cạnh 0 và chu trình 0

Dijkstra vẫn hợp lệ. Nhưng tight graph có thể chứa chu trình; dùng BFS theo hop cho min-hop và greed theo `toTarget` giảm dần để tránh vòng lặp. Đừng đếm toàn bộ walks trên tight graph mà không xét chu trình.

### Cạnh âm

Code từ chối `weight<0`. Nếu đề thật có cạnh âm, phải đổi thuật toán khoảng cách và kiểm tra negative cycles. Không để Dijkstra chạy trên input đó rồi hi vọng kết quả may mắn đúng.

### Khoảng cách có giá trị cực lớn

`Long.MAX_VALUE` được dành làm `INF`. Nếu một phép cộng được xét cho kết quả không biểu diễn được, hoặc chạm chính `INF`, code báo ngoại lệ. Hợp đồng dữ liệu là **mọi phép cộng ứng viên được thực thi nằm trong 0..Long.MAX_VALUE−1**; không lặng lẽ cắt hoặc wrap.

### Kết quả số cách quá lớn

`ways[]` trả modulo `1_000_000_007`, không phải số đường chính xác khi số đường nhiều hơn modulo. Nếu một giá trị modulo bằng 0, vẫn có thể reachable; tin vào `dist/hops` để xét reachability.

### Từ điển theo nhãn khác ID

Nếu đỉnh là chuỗi như `"A"`, `"B"` hoặc tên địa danh, “nhỏ nhất từ điển” phải so theo **nhãn đúng yêu cầu**, không phải tự động theo số ID cấp phát. Code sort theo ID nguyên 0-based; nếu nhãn là chuỗi, cần ánh xạ và comparator phù hợp.

## 15. Lỗi phổ biến khi khôi phục và xử lý hòa

**1. Chỉ in `dist[t]` khi đề cần đường.** Một khoảng cách không chứa dãy đỉnh; cần parent hoặc phép khôi phục có chứng minh.

**2. Tự dựng `[t]` khi `t` unreachable.** Kiểm tra reachability trước rồi mới khôi phục.

**3. Cập nhật `parent[v]` khi `candidate==dist[v]` mà không quản lý chu trình 0.** Cha có thể tạo vòng lặp, khiến dựng đường không kết thúc.

**4. Chọn parent có ID nhỏ nhất và cho rằng toàn đường nhỏ nhất từ điển.** So mỗi cha cuối không phải so cả chuỗi đỉnh từ nguồn.

**5. Không nói rõ quy tắc hòa.** Chỉ cùng trọng số, cùng trọng số+hop, hay cùng ba tiêu chí? Mỗi quy tắc có tập lời giải khác nhau.

**6. Đếm mọi cạnh chặt như một đường tối ưu hop.** Cạnh chặt có thể làm số hop tăng vượt tối ưu; chỉ cộng `ways` qua cạnh từ lớp `k` sang `k+1`.

**7. Bỏ qua cạnh trọng số 0.** Dijkstra cho phép 0, nhưng tight graph có thể có chu trình; không giả định tight graph luôn DAG.

**8. Cho rằng shortest walks luôn hữu hạn.** Có chu trình trọng số 0 trên một đường tối ưu thì có thể lặp chu trình vô hạn lần.

**9. Đếm cạnh song song hai lần khi đề đếm dãy đỉnh.** Khử trùng cung chặt `u→v` nếu cùng endpoint tương ứng một dãy đỉnh.

**10. Khử trùng cạnh sai theo weight trước khi tìm tight.** Trong một cặp `u,v`, các weight khác nhau có ý nghĩa khác nhau; chỉ những cạnh thật sự chặt mới được giữ trong T.

**11. Greedy chọn hàng xóm nhỏ nhất chỉ vì nó chặt.** Hàng xóm ấy có thể cần nhiều hop hơn để tới đích; cần điều kiện `toTarget[v]=toTarget[u]−1`.

**12. Chạy BFS ngược trên graph gốc thay vì reverse tight.** Nếu tính số hop trên các cạnh không chặt, có thể tìm đường ít cạnh nhưng chi phí **không** ngắn nhất.

**13. Nhầm `hops[v]` từ nguồn với `toTarget[v]` tới đích.** Hai mảng có hướng và ý nghĩa khác nhau; greedy cần số hop **còn lại** để tới đích.

**14. Không kiểm soát overflow khi cộng dist và weight.** Một overflow có thể khiến đường chi phí dương được xem như số âm.

**15. Dùng `ways[v]==0` để kết luận unreachable.** Số cách modulo có thể bằng 0 dù tồn tại đường.

**16. Cho rằng BFS distance áp dụng cho cạnh có weight khác nhau.** BFS cho số cạnh, không cho tổng trọng số tùy ý; cần Dijkstra với trọng số không âm.

**17. Dùng Dijkstra với cạnh âm.** Phải chọn Bellman–Ford/thuật toán phù hợp và xử lý negative cycles.

**18. Không xác định walk/simple path khi đếm.** Trên graph có chu trình 0, hai cách hiểu này có thể cho tổng số cách hoàn toàn khác.

**19. So trực tiếp hai đường được in từ hai implementation rồi kết luận một cách sai.** Nếu đề cho phép bất kỳ shortest path, hai đường khác nhau cùng tối ưu đều hợp lệ; khi có tie-break, kiểm bằng **đúng tuple tiêu chí**.

**20. Không kiểm thử cạnh trùng, self-loop, đích unreachable, `s=t`.** Đây là những ca rất dễ làm lộ bug của parent, đếm hoặc khôi phục.

## 16. Bài tập tự luyện

**Bài 1 — Khôi phục bằng parent.** Cho `parent=[-1,0,0,1]` với nguồn 0. Khôi phục đường tới đỉnh 3 và nêu cách xử lý nếu đỉnh t có `dist[t]=INF`.

**Bài 2 — Hai đường cùng trọng số.** Có `0→1(1),1→3(2),0→2(2),2→3(1)`. Tìm `dist[3]` và hai đường ngắn nhất. Nếu ưu tiên dãy nhỏ nhất từ điển, chọn đường nào?

**Bài 3 — Trọng số so với hop.** Dùng ví dụ `0→1(0),1→2(0),2→3(1),0→3(1)`. Nếu chỉ tối ưu trọng số rồi từ điển, đường nào tốt? Nếu tối ưu trọng số rồi hop rồi từ điển, đường nào tốt?

**Bài 4 — Cạnh chặt.** Với `dist[0]=0,dist[1]=2,dist[2]=3`, cạnh `0→1(2),1→2(1),0→2(5)`, xác định cạnh chặt và chỉ ra vì sao cạnh 0→2 không thuộc shortest path.

**Bài 5 — Chu trình 0.** Có `0→1(0),1→0(0),1→2(1)`. Giải thích vì sao có vô hạn shortest walks tới 2 nhưng min-distance/min-hop path vẫn có hữu hạn.

**Bài 6 — Đếm dãy đỉnh.** Hai cạnh song song `0→1(2)` cùng endpoint và một cạnh `1→2(3)`. Theo quy ước đếm dãy đỉnh, có bao nhiêu cách tới 2? Nếu đếm dãy cạnh theo ID, kết quả đổi thế nào?

**Bài 7 — BFS trên tight.** Với graph 9 đỉnh ở mục 4, tự tính `hops[4]`, `hops[6]` và `ways[6]`. Giải thích tại sao đường qua `0→3→5→4→6` không được cộng vào `ways[6]`.

**Bài 8 — Greedy ngược.** Dựng `toTarget[]` cho đích 6 trên tight graph. Tại nguồn 0, những hàng xóm nào cho phép giảm `toTarget` đúng 1? Vì sao chọn 1 thay vì 2?

**Bài 9 — Parent cycle.** Dùng đồ thị nguồn 3, cạnh 1↔2 trọng số 0. Mô phỏng chính sách “ghi đè parent khi khoảng cách hòa” để tạo chu trình parent, rồi chỉ ra cách hai BFS tránh lỗi.

**Bài 10 — Tính đúng.** Chứng minh các đường dùng toàn cạnh chặt từ s có tổng bằng `dist` và mọi shortest path chỉ dùng cạnh chặt. Dùng hai mệnh đề để giải thích mục tiêu phụ min-hop.

**Bài 11 — Kiểm thử độc lập.** Với n≤3 và trọng số thuộc `{0,1,2}`, sinh mọi directed graph không có self-loop và so thuật toán tối ưu với brute simple paths cho mọi nguồn–đích.

**Bài 12 — Truy vấn nhiều đích.** Dijkstra và BFS trên tight đã tiền xử lý từ nguồn. Nếu có 100.000 truy vấn chỉ hỏi `dist/hops/ways`, độ phức tạp mỗi truy vấn là gì? Nếu phải in cả đường đại diện nhỏ nhất từ điển, thêm chi phí nào?

**Bài 13 — Đồ thị vô hướng.** Chuyển mỗi cạnh vô hướng không âm thành hai cung có hướng. Khi nào có chu trình 0? Điều đó ảnh hưởng tới việc đếm shortest walks và min-hop shortest routes ra sao?

**Bài 14 — Bellman–Ford.** Tạo graph có cạnh âm nhưng không có chu trình âm, tìm `dist` bằng Bellman–Ford. Sau đó dựng tight graph và kiểm tra việc khôi phục min-hop; nếu có chu trình âm reachable tới đích, giải thích vì sao không có optimum hữu hạn.

**Bài 15 — Thay đổi thứ tự ưu tiên.** Nếu bài yêu cầu “ít cạnh nhất trước, tổng trọng số nhỏ nhất sau”, thuật toán và kết quả có thay đổi không? Vì sao không được giữ nguyên Dijkstra theo weight rồi mới xét hop?

## 17. Checklist trước khi nộp lời giải

1. **Đề yêu cầu gì?** Chỉ khoảng cách, một đường, đường min-hop, dãy từ điển, đếm theo đỉnh hay theo cạnh?
2. **Đồ thị có hướng/vô hướng?** Có cạnh song song, self-loop hoặc nhiều cung giữa cùng cặp?
3. **Trọng số thế nào?** Unweighted, nonnegative, có âm, có chu trình âm?
4. **Khoảng cách được tính đúng?** BFS cho unweighted, Dijkstra cho nonnegative, Bellman–Ford khi có âm và cần kiểm tra negative cycle?
5. **Có overflow không?** Mọi phép cộng dist+weight có xử lý số lớn đúng, INF không đụng giá trị hợp lệ?
6. **Reachability rõ ràng?** Không dựng `[t]` giả khi t không tới được; đừng dùng modulo 0 làm sentinel.
7. **Nếu dùng parent, cập nhật khi nào?** Đã chứng minh tie-break không tạo chu trình, đặc biệt cạnh trọng số 0?
8. **Cạnh chặt đúng?** Chỉ giữ những `u→v` có `dist[u]+w=dist[v]` với dist hữu hạn?
9. **Đếm đúng đối tượng?** Dãy đỉnh hay dãy cạnh, có khử trùng cung song song khi cần?
10. **Có chu trình 0 không?** Không tùy tiện topo/đếm tất cả walks trên tight graph.
11. **Hops đúng?** BFS trên tight graph, mỗi cạnh tính một bước?
12. **Ways đúng?** Chỉ truyền qua cạnh từ lớp hop k sang k+1, modulo rõ ràng?
13. **Từ điển đúng?** Chọn smallest neighbor mà vẫn giảm `toTarget` đúng 1 trên reverse tight BFS?
14. **Nguồn = đích?** Đường `[s]` với 0 hop, một dãy tối ưu?
15. **Nhiều truy vấn?** Tái sử dụng `dist/hops/ways`; biết rõ chi phí dựng lại path cho mỗi đích?
16. **Bộ test đủ không?** Có dữ liệu không liên thông, đường hòa, đường trọng số thấp nhưng nhiều hop, chu trình 0, cạnh trùng và phép so với brute độc lập?

**Tiêu chí hoàn thành:** Bạn có thể **khôi phục một đường ngắn nhất** khi chỉ có khoảng cách, hiểu giới hạn của `parent[]` trong trường hợp hòa, và tự xây một bộ giải có quy tắc **khoảng cách nhỏ nhất → số cạnh ít nhất → dãy đỉnh nhỏ nhất từ điển**. Bộ giải vẫn chính xác với cạnh trọng số 0, chu trình 0, cạnh song song, đích unreachable và `s=t`; nếu đếm lời giải, bạn nêu rõ đếm **dãy đỉnh min-distance/min-hop modulo M**, không nhầm với số shortest walks có thể vô hạn.

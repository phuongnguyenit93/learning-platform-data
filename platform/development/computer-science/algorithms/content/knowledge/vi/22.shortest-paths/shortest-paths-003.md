# Thuật toán Dijkstra và giả thiết trọng số không âm

## Mục tiêu học tập

**Dijkstra** giải bài toán **đường đi ngắn nhất từ một nguồn** (*single-source shortest paths*) trên đồ thị có trọng số cạnh **không âm**. Thuật toán dùng kỹ thuật **nới lỏng cạnh (relaxation)** và lựa chọn **tham lam (greedy)**: liên tục lấy một đỉnh chưa chốt có khoảng cách tạm thời nhỏ nhất, xác nhận khoảng cách ấy là tối ưu, rồi thử cải thiện các đỉnh kế tiếp.

Giả thiết **`w(u,v)≥0`** là điều kiện then chốt cho **chứng minh tính đúng**, không phải chi tiết triển khai. Trọng số **0 được phép**, nhưng với trọng số **âm**, Dijkstra chốt đỉnh vĩnh viễn có thể cho kết quả sai ngay cả khi không có chu trình âm.

Sau bài học, bạn sẽ:

1. Phát biểu chính xác `dist[v]`, khoảng cách ngắn nhất, đường đi hợp lệ, đỉnh không thể tới và vai trò của `parent[v]`.
2. Giải thích quy tắc **relax `dist[v] > dist[u]+w(u,v)`** và ý nghĩa của khoảng cách tạm thời.
3. Chứng minh bất biến: **mỗi đỉnh đã chốt đều có khoảng cách đúng** khi mọi cạnh không âm.
4. Phân biệt **đỉnh đã đưa vào heap** và **đỉnh đã chốt**; xử lý các mục cũ trong `PriorityQueue`.
5. Cài đặt Java 17+ với `long`, sentinel INF, kiểm tra trọng số, khôi phục đường đi và in đầu ra chính xác.
6. Phân tích thời gian, bộ nhớ khi dùng mảng, danh sách kề, heap có hoặc không có `decrease-key`.
7. Hiểu phản ví dụ với cạnh âm, trường hợp trọng số 0, các đường cùng chi phí, đồ thị có hướng, cạnh song song, self-loop và đồ thị không liên thông.
8. Chọn đúng giữa **BFS**, **0–1 BFS**, **Dijkstra**, **Bellman–Ford** và thuật toán đường ngắn nhất trên **DAG**.
9. Xây kiểm thử bằng một oracle độc lập và tránh các lỗi phổ biến về heap, đánh dấu, hướng cạnh, overflow, và truy vết.

---

## 1. Bài toán đường đi ngắn nhất

Cho đồ thị `G=(V,E)`; mỗi cạnh `(u,v)∈E` có trọng số `w(u,v)`. Một đường đi từ nguồn `s` đến đích `t` là dãy đỉnh:

\[
s=v_0\to v_1\to\cdots\to v_k=t
\]

với mọi cạnh liên tiếp đều tồn tại. Chi phí đường đi `P` là tổng trọng số cạnh:

\[
\operatorname{cost}(P)=\sum_{i=0}^{k-1}w(v_i,v_{i+1}).
\]

**Khoảng cách ngắn nhất**:

\[
\delta(s,v)=\min_{P:s\leadsto v}\operatorname{cost}(P).
\]

Nếu không có đường từ s đến v, quy ước `\delta(s,v)=+\infty`. Đường từ s tới chính s không dùng cạnh nào có chi phí 0; trong miền trọng số không âm, `\delta(s,s)=0`.

Dijkstra nhận một nguồn s, tính `\delta(s,v)` cho **mọi đỉnh reachable từ s**; các đỉnh không reachable vẫn có khoảng cách INF. Nếu lưu `parent[]`, ta có thể truy ngược **một đường ngắn nhất thực sự**, không chỉ một con số.

### 1.1. Đồ thị có hướng và vô hướng

Trong **đồ thị có hướng**, cạnh `u→v` không tự kéo theo `v→u`. Nếu đề có đường một chiều, phải giữ nguyên hướng; việc tự thêm chiều ngược sẽ tạo ra những đường không hợp lệ.

Trong **đồ thị vô hướng**, một cạnh `{u,v}` có trọng số c thường được thêm vào danh sách kề như hai mục:

```text
u -> v (c)
v -> u (c)
```

Dijkstra áp dụng cho cả hai loại nếu **mọi trọng số cạnh được xét không âm**.

### 1.2. Không âm chứ không phải dương

Điều kiện là:

\[
\boxed{w(u,v)\ge0}
\]

chứ không phải `w(u,v)>0`. Một cạnh trọng số **0 là hợp lệ**; nó có thể biểu diễn một lần chuyển miễn phí. Không được dùng `0` làm dấu “không có cạnh” nếu bài cho phép cạnh phí 0. Với danh sách kề, chỉ lưu **những cạnh thực sự tồn tại**, nên không cần một giá trị đặc biệt cho cạnh thiếu.

### 1.3. Dijkstra không phải BFS

**BFS** tối ưu số **cạnh** của đường đi trên đồ thị không trọng số, trong khi Dijkstra tối ưu **tổng trọng số**. Ví dụ:

```text
0 -> 1 (cost 100)
0 -> 2 (cost 1)
2 -> 1 (cost 1)
```

BFS có thể tìm đường trực tiếp `0→1` một cạnh; Dijkstra tìm `0→2→1` có tổng chi phí **2**, nhỏ hơn 100. Khi mọi cạnh có cùng chi phí dương, tối ưu số cạnh và tổng chi phí là tương đương; trường hợp tổng quát thì không.

---

## 2. Ví dụ xuyên suốt: bảy đỉnh

Đồ thị có hướng gồm các cạnh:

| Cạnh | Trọng số |
| --- | ---: |
| `0→1` | 4 |
| `0→2` | 1 |
| `1→3` | 1 |
| `1→4` | 7 |
| `2→1` | 2 |
| `2→3` | 7 |
| `3→4` | 3 |
| `4→5` | **0** |

Đỉnh 6 không thể tới được từ 0.

Một đường đi trực tiếp từ 0 tới 1 có chi phí 4, nhưng đường:

```text
0 -> 2 -> 1
1 + 2 = 3
```

rẻ hơn. Muốn đến 5, một đường ngắn nhất là:

```text
0 -> 2 -> 1 -> 3 -> 4 -> 5
1 + 2 + 1 + 3 + 0 = 7
```

Kết quả đúng từ nguồn 0:

| Đỉnh v | Khoảng cách ngắn nhất | Một đường ngắn nhất |
| ---: | ---: | --- |
| 0 | 0 | `[0]` |
| 1 | 3 | `[0,2,1]` |
| 2 | 1 | `[0,2]` |
| 3 | 4 | `[0,2,1,3]` |
| 4 | 7 | `[0,2,1,3,4]` |
| 5 | 7 | `[0,2,1,3,4,5]` |
| 6 | INF | Không có đường |

Ta sẽ đối chiếu các giá trị này với một chương trình Java 17 hoàn chỉnh ở mục 9.

---

## 3. Ý tưởng greedy: khoảng cách tạm thời và đỉnh đã chốt

Dijkstra dùng hai loại thông tin:

- **`dist[v]`:** chi phí tốt nhất của một đường **đã được tìm thấy** từ s đến v, ban đầu thường là INF.
- **`settled[v]`:** đỉnh v đã được chốt với khoảng cách tối ưu hay chưa.

Khởi tạo:

\[
dist[s]=0,\qquad dist[v]=INF\quad(v\ne s).
\]

Sau đó:

1. Chọn đỉnh `u` chưa chốt với `dist[u]` nhỏ nhất.
2. **Chốt u**, tức `dist[u]=\delta(s,u)` từ thời điểm này.
3. Xét từng cạnh `u→v`; nếu đi qua u tạo đường tốt hơn, cập nhật `dist[v]`.
4. Lặp tới khi không còn đỉnh chưa chốt nào có nhãn hữu hạn.

### 3.1. Relaxation — nới lỏng cạnh

Với cạnh `u→v` có trọng số w, thử:

\[
candidate=dist[u]+w(u,v).
\]

Nếu:

\[
candidate<dist[v],
\]

thì:

\[
dist[v]\leftarrow candidate,\qquad parent[v]\leftarrow u.
\]

Ví dụ ban đầu phát hiện `0→1` có `dist[1]=4`. Khi xử lý đỉnh 2 với `dist[2]=1`, cạnh `2→1` trọng số 2 tạo:

\[
candidate=1+2=3<4.
\]

Do đó `dist[1]=3` và `parent[1]=2`.

Nếu `candidate==dist[v]`, ta có thể **giữ nguyên parent cũ** nếu chỉ cần một đường ngắn nhất. Để chọn đường ít cạnh nhất trong các đường đồng chi phí hoặc đường nhỏ nhất theo từ điển, phải thiết kế thêm tiêu chí phụ và chứng minh quy tắc cập nhật.

### 3.2. Dist hữu hạn là một cận trên của khoảng cách thật

Mỗi lần cập nhật, `dist[v]` bằng chi phí của **một đường đã được phát hiện**. Vì vậy:

\[
dist[v]\ge\delta(s,v).
\]

Đây là một **cận trên** của khoảng cách ngắn nhất thật (khi hữu hạn), không phải một ước lượng tùy ý hay cận dưới. Trong quá trình chạy, dist chỉ có thể **giảm** khi phát hiện đường mới tốt hơn, còn nhãn của đỉnh đã chốt không thay đổi nữa.

### 3.3. Tại sao đỉnh nhỏ nhất có thể chốt?

Nếu mọi cạnh có trọng số không âm, việc nối thêm các cạnh vào một đường đi không thể làm tổng chi phí **giảm**. Vì vậy, khi u đang có nhãn nhỏ nhất trong những đỉnh chưa chốt, không thể tìm một đường tới u rẻ hơn bằng cách đi qua một đỉnh chưa chốt khác với nhãn lớn hơn rồi tiếp tục qua các cạnh không âm.

Lập luận này sẽ được chứng minh bằng quy nạp trong mục 7. Nó **không còn đúng** nếu một cạnh về sau có trọng số âm.

### 3.4. Không được chốt lúc đẩy vào queue

Giả sử:

```text
0 -> 1 (4)
0 -> 2 (1)
2 -> 1 (2)
```

Nếu code vừa thấy cạnh `0→1` đã đặt `visited[1]=true` và không cho cập nhật nữa, nó trả 4 thay vì 3. Đỉnh chỉ nên được **chốt khi lấy ra hợp lệ với nhãn nhỏ nhất**, không phải lúc lần đầu đưa vào queue.

Phân biệt:

- **Discovered / queued:** đã biết một đường đến đỉnh, nhãn có thể giảm tiếp.
- **Settled / finalized:** đã chứng minh nhãn bằng khoảng cách ngắn nhất, không thay đổi nữa.

---

## 4. Dijkstra với hàng đợi ưu tiên (PriorityQueue)

Thay vì quét V đỉnh để tìm nhãn nhỏ nhất ở mỗi bước, có thể sử dụng **min-heap**. Trong Java:

```java
PriorityQueue<State> pq = new PriorityQueue<>(
        Comparator.comparingLong(State::distance));
```

Mỗi `State` chứa **đỉnh** và **giá trị khoảng cách tại thời điểm push**.

### 4.1. Vì sao cần lưu snapshot của khoảng cách?

Một cách dễ sai:

```java
PriorityQueue<Integer> pq = new PriorityQueue<>(
        (a, b) -> Long.compare(dist[a], dist[b]));
```

Nếu các đỉnh đã nằm trong queue mà `dist[]` bên ngoài thay đổi, cấu trúc heap Java **không tự sửa lại vị trí** các phần tử tương ứng. Comparator đọc một khóa mutable làm thứ tự heap có thể trở nên không phù hợp.

Giải pháp phổ biến, dễ kiểm chứng:

- Đưa vào `new State(v,newDistance)` khi `dist[v]` được cải thiện.
- Giữ các State cũ trong heap nhưng **bỏ qua khi lấy ra**.

### 4.2. Stale entry — mục đã cũ

Ví dụ queue có:

```text
(vertex=1, distance=4)    // phát hiện qua 0 -> 1
(vertex=1, distance=3)    // sau khi tìm thấy 0 -> 2 -> 1
```

Trong khi `dist[1]=3`, mục `(1,4)` là **stale**.

Quy tắc:

```java
State state = pq.poll();
int u = state.vertex();
long d = state.distance();

if (d != dist[u] || settled[u]) {
    continue;
}
settled[u] = true;
```

Đặt `settled[u]=true` **sau** điều kiện kiểm tra. Như vậy một mục lỗi thời không thể chốt đỉnh với nhãn cũ.

### 4.3. Cần decrease-key không?

Trong một số heap có hỗ trợ giảm khóa, có thể giữ đúng một khóa cho mỗi đỉnh và gọi `decreaseKey(v,newValue)`. `PriorityQueue` chuẩn của Java không có thao tác indexed decrease-key tiện lợi và hiệu quả như vậy.

Bản **lazy duplicates** chỉ cần `offer` một mục mới khi cải thiện và `continue` khi thấy mục cũ. Nó đơn giản và thường đủ nhanh cho bài đường đi ngắn nhất.

### 4.4. Trọng số bằng 0 và các khóa hòa

Một cạnh trọng số 0 có thể tạo `candidate=dist[u]` cho hàng xóm. Hàng đợi ưu tiên có thể có nhiều đỉnh cùng nhãn; không cần yêu cầu các nhãn **tăng nghiêm ngặt**, chỉ cần thứ tự **không giảm** của các mục hợp lệ được chốt.

Nếu hai State có cùng `distance`, Java PriorityQueue không hứa phải pop theo chỉ số đỉnh tăng hay theo thứ tự chèn. Điều này **không làm sai khoảng cách** trong miền không âm; nó có thể ảnh hưởng lựa chọn parent giữa nhiều đường tối ưu.

---

## 5. Vết chạy trên dữ liệu bảy đỉnh

Trước khi bắt đầu:

```text
dist   = [0, INF, INF, INF, INF, INF, INF]
parent = [-1,-1,-1,-1,-1,-1,-1]
pq     = [(0,0)]
```

Trong bảng, các mục queue được viết dạng `(đỉnh,khoảng cách)`.

### Bước 1: chốt đỉnh 0

Các cạnh `0→1` trọng số 4 và `0→2` trọng số 1:

```text
dist   = [0, 4, 1, INF, INF, INF, INF]
parent = [-1,0,0,-1,-1,-1,-1]
pq chứa (1,4) và (2,1)
```

### Bước 2: chốt đỉnh 2

Mục nhỏ nhất `(2,1)` được poll. Hai cạnh ra:

- `2→1` trọng số 2: `1+2=3<4` → `dist[1]=3`, parent[1]=2.
- `2→3` trọng số 7: `1+7=8` → `dist[3]=8`, parent[3]=2.

```text
dist = [0, 3, 1, 8, INF, INF, INF]

pq chứa:
(1,3) đang hợp lệ
(1,4) đã cũ
(3,8) đang hợp lệ
```

### Bước 3: chốt đỉnh 1

Poll mục hợp lệ `(1,3)`:

- `1→3`: `3+1=4<8` → `dist[3]=4` và parent[3]=1.
- `1→4`: `3+7=10` → `dist[4]=10` và parent[4]=1.

```text
dist = [0, 3, 1, 4, 10, INF, INF]
```

Bây giờ queue có các mục cũ và mới, trong đó `(1,4)` là stale và `(3,4)` hợp lệ. Hai mục có khóa bằng 4 có thể được poll theo thứ tự tùy heap; điều kiện stale sẽ bỏ mục 1:4 mà không ảnh hưởng kết quả.

### Bước 4: chốt đỉnh 3

Với `dist[3]=4`, cạnh `3→4` trọng số 3 tạo `candidate=7<10`. Cập nhật `dist[4]=7`, parent[4]=3. Mục cũ `(4,10)` còn trong heap nhưng về sau bị bỏ qua.

### Bước 5: chốt đỉnh 4 và 5

Đỉnh 4 có `dist[4]=7`. Cạnh `4→5` trọng số **0** tạo:

\[
candidate=7+0=7.
\]

Nên `dist[5]=7`, parent[5]=4. Đỉnh 5 sau đó được chốt với nhãn 7, không có cạnh ra cần relax.

Đỉnh 6 chưa được đưa vào heap vì không có đường tới từ 0.

### Kết quả

```text
dist   = [0, 3, 1, 4, 7, 7, INF]
parent = [-1,2,0,1,3,4,-1]
```

Đường tới 5 được khôi phục ngược:

```text
5 <- 4 <- 3 <- 1 <- 2 <- 0
```

Đảo thứ tự được:

```text
0 -> 2 -> 1 -> 3 -> 4 -> 5
cost = 1 + 2 + 1 + 3 + 0 = 7
```

**Không cộng INF với trọng số** để tạo ứng viên. Một đỉnh INF chưa có đường đi từ nguồn nên không có đoạn đường hợp lệ để nối tiếp; code chỉ relax từ một đỉnh đã được lấy ra khỏi heap với nhãn hữu hạn.

---

## 6. Giả mã chuẩn

```text
DIJKSTRA(graph, s):
    yêu cầu: 0 <= s < V
             mọi cạnh u->v có w >= 0

    dist[0..V-1] = INF
    parent[0..V-1] = -1
    settled[0..V-1] = false

    dist[s] = 0
    pq.push((distance=0, vertex=s))

    while pq không rỗng:
        (du, u) = pq.popMin()

        if du != dist[u] or settled[u]:
            continue

        settled[u] = true

        for mỗi cạnh (u,v,w):
            if settled[v]:
                continue

            candidate = dist[u] + w
            // Phép cộng phải an toàn trong miền số học.

            if candidate < dist[v]:
                dist[v] = candidate
                parent[v] = u
                pq.push((candidate,v))

    return (dist,parent)
```

Với trọng số không âm và phép cộng an toàn, mỗi đỉnh được chốt tối đa một lần. Các mục stale có thể bị pop thêm nhưng không làm mở rộng lại đỉnh đã hoàn tất.

### 6.1. Vì sao không đánh dấu visited khi relax?

Lần relax đầu tiên chỉ tìm thấy **một đường** đến v. Vẫn có thể xuất hiện đường khác rẻ hơn sau này. Do đó `settled[v]` chưa thể bật. Nếu bật quá sớm, thuật toán có thể trả giá trị lớn hơn tối ưu ngay trên đồ thị không âm.

### 6.2. Khi nào có thể dừng sớm?

Nếu chỉ cần khoảng cách đến một đỉnh t, có thể dừng **sau khi t được lấy khỏi queue bằng một mục hợp lệ và được chốt**. Không dừng khi t được push lần đầu: một đường tốt hơn có thể được phát hiện trước khi đến lượt chốt t.

Khi queue rỗng mà t không được chốt, t không tới được từ nguồn.

---

## 7. Chứng minh Dijkstra đúng khi mọi trọng số không âm

### 7.1. Bất biến A: mỗi nhãn hữu hạn là đường đi thật

Ban đầu `dist[s]=0` là đường đi rỗng từ s tới s. Các đỉnh khác INF chưa có đường đã biết.

Nếu `dist[u]` là chi phí của một đường thật tới u, cập nhật `dist[v]=dist[u]+w(u,v)` dùng cạnh thật `u→v` tạo một đường thật tới v. Do đó mọi nhãn hữu hạn đều ≥ khoảng cách thật:

\[
dist[v]\ge\delta(s,v).
\]

Điều này bảo đảm thuật toán không tự tạo ra giá trị “rẻ hơn mọi đường có thật” khi phép cộng và dữ liệu hợp lệ.

### 7.2. Bất biến B: mỗi đỉnh đã chốt là tối ưu

Đặt S là tập các đỉnh đã chốt. Mệnh đề:

\[
\forall u\in S,\quad dist[u]=\delta(s,u).
\]

**Cơ sở:** nguồn s có `dist[s]=0`, cũng là khoảng cách thật do mọi chu trình có tổng trọng số không âm. Nó được chốt trước.

**Bước quy nạp:** giả sử mọi đỉnh trong S đã đúng. Gọi u là đỉnh chưa chốt có nhãn hữu hạn nhỏ nhất, được chọn để chốt. Giả sử có một đường P từ s tới u rẻ hơn `dist[u]`:

\[
\operatorname{cost}(P)=\delta(s,u)<dist[u].
\]

Trên đường P, lấy đỉnh x **đầu tiên chưa chốt**. Gọi y là đỉnh ngay trước x, nên y đã chốt. Khi y được xử lý, thuật toán đã xét cạnh `y→x`. Vì `dist[y]` đúng và không lớn hơn chi phí tiền tố của P tới y:

\[
dist[x]\le dist[y]+w(y,x)
\le\operatorname{cost}(P_{s\to x}).
\]

Đoạn từ x tới u có tổng trọng số **không âm**, nên:

\[
\operatorname{cost}(P_{s\to x})
\le\operatorname{cost}(P)
=\delta(s,u).
\]

Kết hợp:

\[
dist[x]\le\delta(s,u)<dist[u].
\]

Nhưng x vẫn chưa chốt, mâu thuẫn với việc u là đỉnh **chưa chốt có nhãn nhỏ nhất**. Vậy không thể có P rẻ hơn; suy ra:

\[
\boxed{dist[u]=\delta(s,u).}
\]

Đó là lý do lựa chọn tham lam luôn an toàn với trọng số không âm.

### 7.3. Chỗ nào dùng giả thiết không âm?

Bước quyết định chính là:

\[
\operatorname{cost}(P_{s\to x})
\le\operatorname{cost}(P_{s\to u}).
\]

Nếu phần từ x tới u có **trọng số âm**, chi phí toàn đường tới u có thể **thấp hơn** chi phí tiền tố tới x. Khi ấy chuỗi bất đẳng thức không còn đúng; không thể kết luận chốt u là an toàn.

### 7.4. Tính dừng và unreachable

Mỗi đỉnh được chốt nhiều nhất một lần, mỗi cạnh được relax khi đỉnh đầu được chốt. Số lần cập nhật nhãn hữu hạn là hữu hạn nên có hữu hạn State được đưa vào queue.

Nếu một đỉnh reachable nhưng vẫn INF khi queue rỗng, trên một đường từ s tới nó phải có cạnh từ một đỉnh đã đạt tới sang đỉnh chưa được gán nhãn. Khi xử lý đỉnh trước, Dijkstra đã xét cạnh đó, mâu thuẫn. Vì vậy các đỉnh giữ INF đúng là không thể tới được.

---

## 8. Phản ví dụ với trọng số âm

Xét đồ thị có hướng:

```text
0 -> 1 (  2)
0 -> 2 (  5)
2 -> 1 (-10)
1 -> 3 (  1)
```

Đường rẻ nhất đến 1 là:

\[
0\to2\to1,\qquad 5-10=-5.
\]

Đường rẻ nhất đến 3 là:

\[
0\to2\to1\to3,\qquad 5-10+1=-4.
\]

Nhưng Dijkstra với quy tắc **chốt vĩnh viễn**:

1. Từ 0, có `dist[1]=2`, `dist[2]=5`.
2. Chốt 1 trước vì 2 nhỏ hơn 5; cập nhật `dist[3]=3`.
3. Có thể chốt 3 với giá trị 3, trước khi xử lý 2.
4. Khi xử lý 2, cạnh `2→1` cho ứng viên `5-10=-5`, nhưng **1 đã chốt**.
5. Nếu bỏ cập nhật tới settled, kết quả tới 1 và 3 vẫn là 2 và 3, **sai** so với −5 và −4.

Đây là đồ thị **không có chu trình âm**. Một cạnh âm đơn lẻ đã đủ phá tính đúng của Dijkstra chuẩn.

### 8.1. Vì sao một số code “Dijkstra” vẫn sửa được cạnh âm?

Nếu bỏ `settled[]` và cho phép một đỉnh bị đưa trở lại queue sau khi cải thiện, một số đồ thị cạnh âm không có chu trình âm có thể vẫn ra đáp án đúng. Nhưng đó không còn là thuật toán **chốt nhãn tham lam** được chứng minh ở mục 7; hiệu năng và tính dừng cần được phân tích theo một thuật toán label-correcting phù hợp.

Nếu có **chu trình âm reachable**, đường đi có thể giảm chi phí vô hạn bằng cách đi vòng; một thuật toán cứ cập nhật nhãn giảm mãi có thể không dừng. Không dựa vào may mắn “code vẫn ra đúng vài test” để dùng Dijkstra khi input cho phép cạnh âm.

### 8.2. Trọng số 0 không phá chứng minh

Với cạnh trọng số 0, đoạn nối thêm **không giảm** chi phí đã có; nó có thể giữ nguyên. Mệnh đề chỉ cần “không âm”, không cần “dương nghiêm ngặt”. Vì thế Dijkstra xử lý cạnh 0 và chu trình tổng phí 0 đúng, miễn code tránh cập nhật vô ích khi nhãn bằng nhau.

### 8.3. Nên dùng gì thay?

Nếu đồ thị có **cạnh âm**, cân nhắc **Bellman–Ford** để tính đường ngắn nhất từ một nguồn và phát hiện chu trình âm reachable, hoặc thuật toán **theo thứ tự topo trên DAG** nếu đồ thị không có chu trình. Không phải mọi bài có trọng số âm đều cần một thuật toán tốn `O(VE)`: cấu trúc DAG cho phép xử lý nhanh hơn.

---

## 9. Java 17+ hoàn chỉnh: PriorityQueue và truy vết

Ví dụ dùng:

- `List<List<Edge>>`: danh sách kề có hướng.
- `Edge(to,weight)`: cạnh có trọng số `long` không âm.
- `State(vertex,distance)`: mục heap **bất biến**, giúp bỏ stale.
- `Result(dist,parent)`: khoảng cách và đỉnh cha trong một đường ngắn nhất.
- `settled[]`: chỉ chốt khi poll mục hợp lệ.
- `INF=Long.MAX_VALUE/4`, cùng kiểm tra một miền trọng số an toàn để tránh overflow/sentinel.
- Đỉnh 6 unreachable và cạnh `4→5` có trọng số **0**.

Lưu tệp là **`DijkstraNonnegativeDemo.java`**.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class DijkstraNonnegativeDemo {

    private static final long INF = Long.MAX_VALUE / 4;

    public record Edge(int to, long weight) {
    }

    public record State(int vertex, long distance) {
    }

    public record Result(long[] dist, int[] parent) {
    }

    private static List<List<Edge>> createGraph(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("negative n");
        }

        List<List<Edge>> graph = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            graph.add(new ArrayList<>());
        }
        return graph;
    }

    private static void addEdge(
            List<List<Edge>> graph,
            int from, int to, long weight) {
        graph.get(from).add(new Edge(to, weight));
    }

    public static Result dijkstra(
            List<List<Edge>> graph, int source) {

        Objects.requireNonNull(graph, "graph");
        int n = graph.size();

        if (source < 0 || source >= n) {
            throw new IllegalArgumentException(
                    "source must be a graph vertex");
        }

        // Reserve INF for unreachable vertices. Bounding each
        // edge ensures that every simple-path cost and every
        // one-edge extension remain strictly below INF.
        long maxEdgeExclusive = INF / (n + 1L);

        for (int u = 0; u < n; u++) {
            List<Edge> edges =
                    Objects.requireNonNull(
                            graph.get(u), "null adjacency list");

            for (Edge e : edges) {
                if (e == null
                        || e.to() < 0 || e.to() >= n
                        || e.weight() < 0
                        || e.weight() >= maxEdgeExclusive) {
                    throw new IllegalArgumentException(
                            "invalid edge or unsupported weight");
                }
            }
        }

        long[] dist = new long[n];
        Arrays.fill(dist, INF);

        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        boolean[] settled = new boolean[n];

        PriorityQueue<State> pq = new PriorityQueue<>(
                Comparator.comparingLong(State::distance));

        dist[source] = 0;
        pq.offer(new State(source, 0));

        while (!pq.isEmpty()) {
            State entry = pq.poll();
            int u = entry.vertex();
            long du = entry.distance();

            if (du != dist[u] || settled[u]) {
                continue; // Old entry or already finalized.
            }

            settled[u] = true;

            for (Edge edge : graph.get(u)) {
                int v = edge.to();
                if (settled[v]) {
                    continue;
                }

                long candidate = du + edge.weight();

                if (candidate < dist[v]) {
                    dist[v] = candidate;
                    parent[v] = u;
                    pq.offer(new State(v, candidate));
                }
            }
        }

        return new Result(dist, parent);
    }

    public static List<Integer> pathTo(
            Result result, int source, int target) {

        Objects.requireNonNull(result, "result");

        int n = result.dist().length;
        if (source < 0 || source >= n
                || target < 0 || target >= n) {
            throw new IllegalArgumentException(
                    "source or target out of range");
        }

        if (result.dist()[target] == INF) {
            return List.of();
        }

        List<Integer> reversed = new ArrayList<>();

        for (int at = target; at != -1;
                at = result.parent()[at]) {
            reversed.add(at);
            if (at == source) {
                break;
            }
        }

        if (reversed.get(reversed.size() - 1) != source) {
            throw new IllegalStateException(
                    "parent chain does not reach source");
        }

        Collections.reverse(reversed);
        return reversed;
    }

    public static void main(String[] args) {
        List<List<Edge>> graph = createGraph(7);

        addEdge(graph, 0, 1, 4);
        addEdge(graph, 0, 2, 1);
        addEdge(graph, 1, 3, 1);
        addEdge(graph, 1, 4, 7);
        addEdge(graph, 2, 1, 2);
        addEdge(graph, 2, 3, 7);
        addEdge(graph, 3, 4, 3);
        addEdge(graph, 4, 5, 0); // Zero is a valid edge.
        // Vertex 6 is unreachable.

        int source = 0;
        Result result = dijkstra(graph, source);

        for (int v = 0; v < graph.size(); v++) {
            String distance = result.dist()[v] == INF
                    ? "INF"
                    : Long.toString(result.dist()[v]);

            System.out.println(
                    "to " + v + ": " + distance
                            + ", path " + pathTo(result, source, v));
        }

        List<List<Edge>> negative = createGraph(3);
        addEdge(negative, 0, 1, 2);
        addEdge(negative, 0, 2, 5);
        addEdge(negative, 2, 1, -10);

        boolean rejected = false;
        try {
            dijkstra(negative, 0);
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("Negative edge rejected: " + rejected);

        List<List<Edge>> singleGraph = createGraph(1);
        Result single = dijkstra(singleGraph, 0);
        System.out.println(
                "Single vertex: " + single.dist()[0]
                        + ", path " + pathTo(single, 0, 0));

        boolean emptyRejected = false;
        try {
            dijkstra(createGraph(0), 0);
        } catch (IllegalArgumentException ex) {
            emptyRejected = true;
        }
        System.out.println(
                "Empty source rejected: " + emptyRejected);
    }
}
```

Biên dịch và chạy trên **JDK 17+**:

```bash
javac DijkstraNonnegativeDemo.java
java DijkstraNonnegativeDemo
```

**Đầu ra chuẩn chính xác:**

```text
to 0: 0, path [0]
to 1: 3, path [0, 2, 1]
to 2: 1, path [0, 2]
to 3: 4, path [0, 2, 1, 3]
to 4: 7, path [0, 2, 1, 3, 4]
to 5: 7, path [0, 2, 1, 3, 4, 5]
to 6: INF, path []
Negative edge rejected: true
Single vertex: 0, path [0]
Empty source rejected: true
```

### 9.1. Vì sao code đúng với thuật toán?

- `PriorityQueue` so sánh **`State.distance` bất biến**, không so sánh `dist[]` mutable ở bên ngoài.
- Khi tìm đường rẻ hơn, code đưa **một bản State mới** vào queue; mục cũ tự bị bỏ qua nếu `du != dist[u]`.
- `settled[u]` được bật **sau** khi poll mục hợp lệ, không phải khi mới phát hiện u.
- Chỉ relax tới v chưa settled; điều này đúng do chứng minh Dijkstra với trọng số không âm.
- `parent[v]` chỉ sửa khi ứng viên **nhỏ hơn nghiêm ngặt**, giữ một chuỗi cha hợp lệ kể cả khi có chu trình trọng số 0.
- Cạnh âm bị từ chối theo hợp đồng, thay vì chạy và có thể tạo ra khoảng cách sai.

### 9.2. Tại sao dùng long và giới hạn trọng số?

Mã dùng:

```java
private static final long INF = Long.MAX_VALUE / 4;
long maxEdgeExclusive = INF / (n + 1L);
```

Mọi cạnh hợp lệ phải thỏa:

\[
0\le w<INF/(n+1).
\]

Một đường đi **đơn** có tối đa n−1 cạnh. Trong quá trình nới lỏng, việc nối thêm **một** cạnh vào một đường đi tối ưu đã chốt tạo một ứng viên không vượt giới hạn n cạnh đơn vị trọng số; vậy mọi ứng viên cần tính nằm **dưới INF**, không tràn `long` và không thể bị nhầm với sentinel.

Đây là **hạn chế số học của chương trình minh họa**, không phải đòi hỏi của lý thuyết Dijkstra. Với trọng số lớn hơn, thư viện thực tế cần kiểm tra tràn số `Math.addExact`, dùng reachability riêng thay cho một sentinel có thể trùng chi phí thật, hoặc dùng `BigInteger` khi tổng có thể vượt 64 bit.

### 9.3. Vì sao không tạo vòng vô hạn với cạnh 0?

Vì cập nhật chỉ xảy ra khi `candidate<dist[v]`, một vòng chi phí 0 chỉ tạo ứng viên **bằng** nhãn đang có, không tạo cải thiện giả. Mỗi đỉnh chỉ được settled một lần và mục stale bị bỏ.

### 9.4. Tính chất của Result

Hàm `pathTo(result,source,target)` trả:

- `[source]` nếu target chính là source.
- Một đường đi ngắn nhất nếu target reachable.
- `[]` nếu target unreachable.

Hàm kỳ vọng `source` là đúng nguồn đã dùng khi tính `result`. Record Java 17 **không sao chép sâu** các mảng; người gọi không nên sửa `result.dist()` hay `result.parent()` sau khi chạy nếu muốn truy vết đúng. Một API yêu cầu bất biến hoàn toàn nên sao chép phòng vệ.

### 9.5. Biên n=0, n=1

Với một đỉnh không cạnh, khoảng cách từ 0 đến 0 bằng 0 và đường là `[0]`. Với đồ thị có 0 đỉnh, không có nguồn hợp lệ; code **từ chối** lời gọi `dijkstra(empty,0)` thay vì cố truy cập mảng độ dài 0.

---

## 10. Phân tích thời gian và bộ nhớ

Đặt `V` là số đỉnh, `E` là số mục cạnh trong danh sách kề. Với đồ thị vô hướng lưu hai chiều, tổng số mục cạnh là `2E` theo quy ước đếm cạnh vô hướng, không làm thay đổi bậc `O(V+E)`.

### 10.1. Bản chọn min bằng quét mảng

Nếu mỗi lượt quét toàn bộ V đỉnh chưa chốt để tìm nhãn nhỏ nhất:

- Tối đa V lượt chọn min, mỗi lượt quét V đỉnh → `O(V²)`.
- Nới lỏng tổng cộng E cạnh → `O(E)`.

Vì thế:

\[
T=O(V^2+E).
\]

Với **ma trận kề**, phải kiểm tra mọi vị trí trong một hàng để tìm cạnh nên tổng thường là `O(V²)`. Cách này đơn giản và có thể cạnh tranh với heap khi V nhỏ hoặc đồ thị rất dày.

### 10.2. Binary heap có decrease-key

Nếu dùng một hàng đợi ưu tiên hỗ trợ cập nhật khóa của đỉnh hiệu quả, bậc thời gian quen thuộc là:

\[
O((V+E)\log V)
\]

với V≥2 và các phép toán heap phù hợp. Bộ nhớ heap `O(V)` ngoài danh sách kề.

### 10.3. Java PriorityQueue theo cách lazy

Mỗi cạnh được xét khi đỉnh đầu được settled, tối đa một lần trong thuật toán này; mỗi lần relax thành công push một State. Do đó tổng số State tạo ra `O(E+1)` và heap có thể chứa `O(E)` mục.

Mỗi `offer/poll` trên heap có kích thước tới `O(E+1)` mất `O(\log(E+1))`. Tổng thời gian, gồm cả validate đầu vào và duyệt danh sách:

\[
O(V+E+(E+1)\log(E+1)),
\]

thường trình bày gọn là:

\[
\boxed{O((V+E)\log(V+E)).}
\]

Với đồ thị đơn có `E≤O(V²)`, biểu thức này thường rút về `O((V+E)\log V)`. Với đa cạnh rất nhiều, `\log(E+1)` thể hiện đúng hơn chi phí heap có nhiều mục.

Bộ nhớ phụ:

- `dist[]`, `parent[]`, `settled[]`: `O(V)`.
- PriorityQueue chứa các State, có thể tới `O(E)`.
- Do đó `O(V+E)` bộ nhớ phụ, ngoài danh sách kề đầu vào.

### 10.4. Trọng số lớn

Giới hạn tiệm cận thường giả sử một phép cộng/so sánh số có chi phí hằng số. Trong Java, kiểu `long` là số nguyên 64 bit; nếu tổng trọng số có thể vượt miền biểu diễn, cần xử lý overflow. Chương trình ở trên có hợp đồng về miền cạnh để giữ các phép cộng an toàn.

---

## 11. Các trường hợp biên và tính chất cần hiểu

### 11.1. Cạnh trọng số 0

Dijkstra **đúng** với cạnh 0. Ví dụ `dist[u]=5`, cạnh `u→v` có trọng số 0 và `dist[v]=INF`: relax đưa `dist[v]=5`. Không được bỏ cạnh vì `weight==0`.

### 11.2. Cạnh song song

Có thể có hai cạnh cùng chiều `0→1` trọng số 10 và 3. Dijkstra xem cả hai và giữ khoảng cách 3. Không bắt buộc phải gộp cạnh, nhưng nếu gộp trong bài chỉ quan tâm chi phí thì nên giữ cạnh rẻ nhất, không cộng các trọng số.

### 11.3. Self-loop và chu trình trọng số 0

Self-loop `u→u` trọng số 0 không cải thiện nhãn. Chu trình có tổng trọng số 0 có thể tạo nhiều walk đồng chi phí, nhưng vì code chỉ cập nhật khi **nhỏ hơn**, không bị vòng relax vô hạn. Self-loop âm bị cấm và là một chu trình âm.

### 11.4. Nhiều đường ngắn nhất đồng hạng

Hai đường cùng tổng 7 đều tối ưu. Dijkstra chỉ bảo đảm **khoảng cách** và một đường khôi phục hợp lệ. Muốn đường ít cạnh nhất trong nhóm đồng chi phí, cần lưu thêm số cạnh hoặc thiết kế tiêu chí lexicographic. Muốn đếm mọi đường đi tối ưu, phải định nghĩa rõ đếm **walk** hay **đường đơn**: chu trình 0 có thể tạo vô số walk đồng chi phí.

### 11.5. Đồ thị không liên thông

Đỉnh không reachable từ s giữ `INF`. Đây là kết quả đúng cho bài **single-source shortest paths**; không cần khởi chạy DFS/Dijkstra mới từ mỗi đỉnh còn lại chỉ để ép mọi đỉnh có giá trị hữu hạn.

### 11.6. Cạnh âm ở vùng không tới được từ s

Về mặt toán học, một cạnh âm không thể đạt tới từ s không ảnh hưởng các đường đi từ s. Tuy nhiên chương trình mẫu **kiểm tra mọi cạnh của graph** và từ chối toàn bộ input nếu gặp cạnh âm ở bất kỳ vùng nào, nhằm làm hợp đồng ứng dụng Dijkstra rõ ràng và dễ kiểm chứng.

### 11.7. Nhiều nguồn cùng lúc

Nếu cần khoảng cách từ **nguồn gần nhất** trong tập S:

\[
dist[v]=\min_{s\in S}\delta(s,v),
\]

có thể đặt `dist[s]=0` cho mọi `s∈S` và đẩy tất cả các nguồn vào queue. Điều này tương đương thêm một siêu nguồn với cạnh trọng số 0 tới mỗi nguồn trong S. Nếu bài yêu cầu đường từ **một nguồn nhất định**, đừng thay bằng multi-source vì ngữ nghĩa khác.

### 11.8. Chỉ cần một đích

Với một đích t, có thể dừng khi t được **poll hợp lệ và finalized**. Không dừng khi t được push lần đầu, bởi về sau có thể tìm được đường rẻ hơn trước khi t được chốt.

### 11.9. Đồ thị lưới

Có thể coi mỗi ô hợp lệ là một đỉnh, các bước đi hợp lệ là cạnh. Dijkstra áp dụng nếu **chi phí mỗi bước không âm**. Tuy nhiên phải xác định rõ chi phí trả **khi rời ô** hay **khi tới ô**, có tính ô xuất phát hay không, và có cho phép đi chéo không; mỗi cách tạo một đồ thị và kết quả khác nhau.

---

## 12. Chọn thuật toán thay thế khi dữ liệu khác

| Dạng bài toán | Lựa chọn phù hợp | Ghi chú |
| --- | --- | --- |
| Cạnh không trọng số hoặc cùng chi phí 1 | **BFS** | Tìm đường ít cạnh nhất; `O(V+E)` |
| Trọng số chỉ có **0 hoặc 1** | **0–1 BFS** | Deque; `O(V+E)` |
| Trọng số **không âm tổng quát** | **Dijkstra** | Heap hoặc chọn min theo mảng |
| Có **cạnh âm**, không có chu trình âm reachable | **Bellman–Ford** | Có thể dùng để kiểm tra chu trình âm; `O(VE)` |
| Đồ thị có hướng **không chu trình (DAG)**, có thể có cạnh âm | **Topo shortest path** | `O(V+E)` |
| Nhiều cặp trên đồ thị V nhỏ | **Floyd–Warshall** | `O(V³)` hoặc lặp SSSP tùy dữ liệu |
| Nhiều nguồn, cạnh âm nhưng không có chu trình âm | **Johnson** (nâng cao) | Tái trọng số rồi chạy nhiều lần Dijkstra |

### 12.1. Bellman–Ford

Bellman–Ford thử relax tất cả các cạnh tối đa V−1 lượt. Khi không có chu trình âm ảnh hưởng tới đích, đường tối ưu có thể chọn không lặp đỉnh, nên tối đa V−1 cạnh. Một lượt kiểm tra thêm có thể phát hiện nhãn vẫn giảm do **chu trình âm reachable**.

Nếu có chu trình âm reachable từ nguồn và từ đó còn đi tới một đỉnh v, khoảng cách tới v có thể giảm vô hạn khi cho phép walk lặp vòng. Không nên trả một số hữu hạn “đường ngắn nhất” mà không nêu trạng thái ấy.

### 12.2. DAG cho phép trọng số âm

Trong DAG, thứ tự topo bảo đảm mọi tiền nhiệm được xử lý trước khi một đỉnh cần dùng kết quả của chúng. Nới lỏng mỗi cạnh một lần theo thứ tự topo cho `O(V+E)`, **kể cả có trọng số âm**, vì không có chu trình.

### 12.3. Vì sao 0–1 BFS nhanh hơn heap trong trường hợp riêng?

Khi mỗi cạnh có trọng số 0 hoặc 1, có thể dùng **deque**: relax qua cạnh 0 thì đưa đỉnh lên đầu deque; qua cạnh 1 thì đưa vào cuối. Với triển khai đúng, thời gian `O(V+E)`. Dijkstra vẫn đúng, nhưng chưa khai thác hết cấu trúc trọng số đặc biệt.

### 12.4. Nhiều đích với cùng nguồn

Một lần chạy Dijkstra từ s trả dist tới mọi v, nên nếu có nhiều câu hỏi `(s,t_1),(s,t_2),...` cùng nguồn, hãy **chạy một lần** rồi tra kết quả. Không cần chạy lại cho mỗi đích nếu graph không thay đổi.

---

## 13. Kiểm thử Dijkstra bằng thuộc tính và oracle

### 13.1. Bộ test tối thiểu

| Input | Mong đợi |
| --- | --- |
| Đồ thị bảy đỉnh ở mục 2 | `[0,3,1,4,7,7,INF]` |
| n=1, source=0, không cạnh | `dist[0]=0`, path `[0]` |
| n=0, source=0 | Báo nguồn không hợp lệ |
| n=3, không cạnh, source=0 | `[0,INF,INF]` |
| Một cạnh `0→1` trọng số 0 | `dist[1]=0` |
| Hai cạnh song song `0→1` trọng số 8 và 2 | `dist[1]=2` |
| Self-loop `0→0` trọng số 0 | `dist[0]=0`, không lặp |
| Hai đường đến v cùng chi phí | Dist đúng, parent có thể khác |
| Chỉ có cạnh `1→0`, source=0 | 1 không reachable |
| Cạnh âm `2→1` trọng số −10 | Code mẫu báo lỗi input |
| Neighbor ngoài `[0,V)` | Code mẫu báo lỗi |
| Danh sách kề null | Code mẫu báo lỗi |
| Trọng số ≥ miền an toàn của demo | Code mẫu báo lỗi |
| Nguồn âm hoặc nguồn ≥ V | Code mẫu báo lỗi |

### 13.2. Thuộc tính của dist và path

Với mọi đỉnh reachable v:

1. `dist[v]` hữu hạn và không âm.
2. `dist[source]=0`.
3. `pathTo` phải bắt đầu bằng source và kết thúc bằng v.
4. Các cặp đỉnh liên tiếp trên path phải có cạnh hợp lệ theo đúng hướng.
5. Tổng trọng số **những cạnh đã sử dụng** phải bằng `dist[v]`. Với cạnh song song, muốn đối chiếu chính xác phải biết cạnh nào được chọn hoặc tìm cạnh phù hợp với chênh lệch nhãn.
6. Với mọi cạnh `u→v` và u reachable, khoảng cách phải thỏa:

\[
dist[v]\le dist[u]+w(u,v).
\]

7. Đỉnh unreachable có dist=INF, parent=−1, và path rỗng.

Bất đẳng thức theo cạnh là **điều kiện cần** của khoảng cách ngắn nhất; để chứng minh toàn bộ kết quả tối ưu vẫn cần bất biến Dijkstra hoặc so với một oracle đáng tin.

### 13.3. Kiểm thử chéo bằng Bellman–Ford

Với n nhỏ, tạo nhiều đồ thị có hướng trọng số trong `[0,20]`, gồm cả cạnh 0, đa cạnh, chu trình và đỉnh cô lập:

1. Chạy Dijkstra từ cùng nguồn s.
2. Chạy Bellman–Ford độc lập với `n−1` lượt relax.
3. So mọi `dist[v]`; các giá trị unreachable phải thống nhất.
4. Đối với đỉnh reachable, kiểm tra parent path hợp lệ và tổng chi phí đúng.
5. Khi có nhiều đường đồng giá, không ép hai thuật toán trả cùng parent; chỉ ép khoảng cách và tính hợp lệ.

Kiểm thử ngẫu nhiên nhỏ giúp phát hiện những lỗi khó thấy: sai điều kiện stale, đánh dấu sớm, chỉ thêm một chiều cạnh vô hướng, comparator không an toàn hoặc nhầm INF với cạnh trọng số 0.

---

## 14. Những lỗi thường gặp

1. **Dùng Dijkstra trên đồ thị có cạnh âm** rồi vẫn khẳng định tối ưu.
2. **Nhầm “không âm” với “dương”** và loại mất những cạnh trọng số 0.
3. **Đánh dấu settled khi push**, khiến một đỉnh không được cập nhật bởi đường tốt hơn về sau.
4. **Không kiểm tra stale entry** khi dùng PriorityQueue với nhiều State của cùng đỉnh.
5. **Comparator đọc dist[] mutable** trong khi phần tử đã nằm trong heap, không tự cập nhật lại thứ tự.
6. **So sánh State bằng phép trừ ép kiểu int**, có thể tràn và đảo thứ tự.
7. **Cộng INF với trọng số** hoặc chọn INF nhỏ hơn một tổng hợp lệ.
8. **Dùng int cho tổng trọng số có thể hàng tỷ**, gây overflow.
9. **Dùng 0 biểu thị cạnh không tồn tại** trong khi có cạnh hợp lệ chi phí 0.
10. **Quên parent khi relax thành công**, làm giá trị đúng nhưng không truy vết được.
11. **Thay parent khi nhãn bằng nhau** trên đồ thị có chu trình 0 mà chưa phân tích khả năng tạo vòng parent.
12. **Dừng khi target được đưa vào heap lần đầu** thay vì khi target được chốt hợp lệ.
13. **Quên hướng cạnh** khi dữ liệu có đường một chiều.
14. **Quên chiều ngược** khi tự dựng danh sách kề cho đồ thị vô hướng.
15. **Coi mọi đỉnh của graph đều reachable** từ nguồn được chọn.
16. **Gọi một biến thể cho phép tái xử lý đỉnh ở cạnh âm là Dijkstra chuẩn**, không có chứng minh hoặc xử lý negative cycle.
17. **Coi parent là duy nhất** hoặc luôn là đường có ít cạnh nhất.
18. **Dùng PriorityQueue lazy nhưng báo heap chỉ O(V)** dù có thể giữ O(E) mục.
19. **Nói O((V+E)log V) cho mọi đa đồ thị** mà không xét số mục heap có thể phụ thuộc E.
20. **Không kiểm tra source, neighbor, null adjacency, trọng số và miền số học**.
21. **Bỏ qua self-loop/đa cạnh** trong test nên không phát hiện lỗi logic.
22. **Dùng BFS khi cạnh có trọng số không đồng nhất** và vẫn gọi kết quả là tổng chi phí ngắn nhất.
23. **Suy rằng chỉ cạnh âm thuộc chu trình mới nguy hiểm**, mặc dù một cạnh âm đơn lẻ có thể phá thứ tự chốt.
24. **Đếm mọi đường đi ngắn nhất như các walk** mà không xét khả năng có vô số walk do chu trình phí 0.

---

## 15. Bài tập tự kiểm tra

### Bài 1 — Relaxation

Có `dist[u]=7`, `dist[v]=15` và cạnh `u→v` trọng số 5. Sau relax, dist[v] và parent[v] thay đổi ra sao?

### Bài 2 — Đường rẻ hơn cạnh trực tiếp

Trên đồ thị `0→1:4`, `0→2:1`, `2→1:2`, tìm khoảng cách ngắn nhất tới 1. Vì sao không được chốt 1 khi mới push từ 0?

### Bài 3 — Vết bảy đỉnh

Với đồ thị ở mục 2, viết dist và parent cuối cùng; khôi phục đường tới 5.

### Bài 4 — Stale entry

Queue chứa `(vertex=1,distance=4)` và `(vertex=1,distance=3)`; `dist[1]=3`. Khi poll từng mục cần làm gì?

### Bài 5 — Cạnh 0

Nếu `dist[u]=5`, cạnh `u→v` có trọng số 0 và `dist[v]=INF`, kết quả relax là gì? Cạnh ấy có làm sai Dijkstra không?

### Bài 6 — Phản ví dụ âm

Với `0→1:2`, `0→2:5`, `2→1:−10`, `1→3:1`, khoảng cách thật tới 1 và 3 là bao nhiêu? Dijkstra chốt vĩnh viễn có thể sai tại bước nào?

### Bài 7 — Chứng minh tham lam

Chỉ ra bất đẳng thức trong chứng minh chọn đỉnh chưa chốt nhỏ nhất cần giả thiết mọi trọng số không âm.

### Bài 8 — Đường hòa

Nếu hai đường đến v đều có tổng 7, việc giữ nguyên parent khi candidate==dist[v] có phải lỗi không? Khi nào cần cơ chế phá hòa?

### Bài 9 — Độ phức tạp

Với danh sách kề và `PriorityQueue` lazy, tại sao có thể sinh `O(E)` State? Phân tích thời gian và bộ nhớ.

### Bài 10 — Chọn thuật toán

Chọn một thuật toán phù hợp cho: (a) cạnh không trọng số; (b) chỉ trọng số 0 hoặc 1; (c) trọng số không âm bất kỳ; (d) có cạnh âm; (e) DAG có cạnh âm.

### Bài 11 — Đỉnh không reachable

Một graph có nguồn 0 và chỉ các cạnh `0→1`, `1→2`. Đỉnh 3 không có đường từ 0. Dist, parent, path của 3 phải là gì?

### Bài 12 — Đồ thị một chiều

Chỉ có cạnh `1→0`, không có `0→1`. Từ nguồn 0 có tới được 1 không? Nếu chuyển thành đồ thị vô hướng, bạn đã đổi bài toán thế nào?

### Bài 13 — Dừng sớm

Khi một đường tới t có chi phí 10 được push, ta có thể dừng trả 10 chưa? Khi nào mới được dừng?

### Bài 14 — Overflow

Vì sao nên dùng long và kiểm tra tràn khi đường có nhiều cạnh lớn? Tại sao phép cộng INF+w không hợp lệ?

### Bài 15 — Multi-source

Tính khoảng cách từ nguồn gần nhất trong `{s_1,s_2,s_3}` đến mọi đỉnh với trọng số không âm. Khởi tạo queue như thế nào?

### Bài 16 — Kiểm thử

Thiết kế oracle bằng Bellman–Ford cho các đồ thị ngẫu nhiên nhỏ, có trọng số không âm và nhiều cạnh song song. Cần so những điều gì ngoài dist?

### Bài 17 — Self-loop và cạnh song song

Có self-loop `1→1` phí 0 và hai cạnh `0→1` phí 10 và 3. Dijkstra từ 0 cho dist[1] là bao nhiêu? Có vòng cập nhật không?

### Bài 18 — Đường ít cạnh nhất và ít phí nhất

Có đường `0→1` giá 100 và `0→2→1` giá 2. BFS và Dijkstra tối ưu hai mục tiêu khác nhau như thế nào?

### Bài 19 — Vì sao DAG xử lý được cạnh âm?

Giải thích vai trò của thứ tự topo và tại sao thuật toán DAG không cần giả thiết trọng số không âm.

### Bài 20 — Biên n=0

Với graph có 0 đỉnh, gọi `dijkstra(graph,0)` phải cho kết quả rỗng hay báo lỗi theo code minh họa? Vì sao?

### Đáp án gợi ý

1. `candidate=7+5=12<15`, nên đặt `dist[v]=12` và `parent[v]=u`.
2. `dist[1]=3` qua 0→2→1. Chốt lúc push sẽ khóa sai nhãn 4 trước khi thấy đường rẻ hơn.
3. `dist=[0,3,1,4,7,7,INF]`, `parent=[-1,2,0,1,3,4,-1]`. Đường tới 5: 0→2→1→3→4→5, tổng 7.
4. `(1,3)` là mục hiện hành; `(1,4)` stale vì 4 khác dist[1], phải bỏ qua.
5. `dist[v]=5`; trọng số 0 là không âm nên Dijkstra vẫn đúng.
6. `\delta(0,1)=-5`, `\delta(0,3)=-4`. Đỉnh 1 bị chốt với 2 trước khi xét cạnh âm 2→1.
7. Chi phí tiền tố tới đỉnh chưa chốt đầu tiên phải ≤ chi phí toàn đường; điều này cần phần trọng số còn lại không âm.
8. Không lỗi khi chỉ cần một đường ngắn nhất; nếu đề yêu cầu tiêu chí phụ, cần quy tắc hòa và chứng minh riêng.
9. Mỗi relax thành công push State mới, tối đa theo số cạnh. Heap có thể O(E) mục; thời gian `O((V+E)\log(V+E))`, bộ nhớ phụ `O(V+E)`.
10. (a) BFS, (b) 0–1 BFS, (c) Dijkstra, (d) Bellman–Ford (nếu muốn phát hiện chu trình âm), (e) DAG shortest paths theo thứ tự topo.
11. `dist[3]=INF`, `parent[3]=-1`, path `[]`.
12. Không. Nếu tự thêm cạnh 0→1, đã tạo thêm đường không tồn tại và đổi graph thành vô hướng.
13. Chưa; phải chờ t được poll với nhãn hiện hành và chốt, vì có thể tìm đường rẻ hơn.
14. Tổng có thể vượt int; dùng long và kiểm soát phạm vi. INF là sentinel “không có đường đã biết”, không phải một số chi phí để cộng.
15. Đặt `dist[s_i]=0`, push tất cả `(s_i,0)`; tương đương một siêu nguồn có cạnh 0 tới các s_i.
16. So mọi dist, tính reachable, tính hợp lệ của đường parent và tổng chi phí; không nhất thiết so parent khi có hòa.
17. `dist[1]=3`, self-loop phí 0 chỉ tạo ứng viên bằng nhãn nên không cập nhật vô hạn.
18. BFS tối ưu số cạnh và có thể chọn cạnh giá 100; Dijkstra tối ưu tổng phí và chọn đường qua 2 giá 2.
19. DAG không có chu trình, thứ tự topo cho phép xử lý mọi tiền nhiệm trước đỉnh cần kết quả, nên mỗi cạnh relax một lần dù trọng số âm.
20. Báo `IllegalArgumentException`: không tồn tại nguồn 0 trong một tập đỉnh rỗng.

---

## Ghi nhớ

**Dijkstra dùng tham lam để chốt đỉnh chưa chốt có khoảng cách tạm thời nhỏ nhất**. Điều đó **chỉ có bảo đảm đúng khi mọi cạnh có trọng số không âm**. Trọng số **0 vẫn hợp lệ**; cạnh **âm có thể gây sai** ngay cả khi không có chu trình âm. Nhãn hữu hạn `dist[v]` biểu diễn một đường đi thật, và sau khi chốt u thì `dist[u]=\delta(s,u)`. Với Java, dùng `PriorityQueue` chứa các `State(vertex,distance)` bất biến, **thêm State mới khi giảm nhãn** và **bỏ stale entries** khi poll. Lưu `parent[]` nếu cần khôi phục đường đi; dùng `INF` cho đỉnh không reachable và kiểm soát số học để tránh overflow. Bản heap lazy trên danh sách kề có thời gian thường `O((V+E)\log(V+E))` và bộ nhớ phụ `O(V+E)`. Khi dữ liệu có cạnh âm, hãy dùng thuật toán khác có chứng minh phù hợp như **Bellman–Ford** hoặc thuật toán đường ngắn nhất theo thứ tự topo nếu đồ thị là **DAG**.

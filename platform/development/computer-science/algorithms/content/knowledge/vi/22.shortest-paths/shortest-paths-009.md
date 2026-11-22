# Thuật toán Johnson và phép đổi trọng số

**Thuật toán Johnson** (*Johnson's algorithm*) giải bài toán **đường đi ngắn nhất giữa mọi cặp đỉnh** (*all-pairs shortest paths – APSP*) trên đồ thị có hướng, cho phép cạnh mang **trọng số âm**, miễn là đồ thị **không chứa chu trình có tổng trọng số âm**. Johnson kết hợp:

1. **Bellman–Ford** chạy một lần từ một **siêu nguồn ảo** để tính các **thế năng đỉnh** (*vertex potentials*) \(h[v]\) và phát hiện chu trình âm.
2. **Phép đổi trọng số** (*reweighting*) \(w'(u,v)=w(u,v)+h[u]-h[v]\) biến mọi cạnh thành **không âm** nhưng vẫn **giữ nguyên tập các đường đi ngắn nhất** giữa mỗi cặp nguồn–đích.
3. **Dijkstra** chạy từ từng đỉnh trên đồ thị đã đổi trọng số để thu kết quả APSP nhanh trên **đồ thị thưa**.
4. **Đổi ngược khoảng cách** bằng \(d(s,t)=d'(s,t)-h[s]+h[t]\).

Điểm cốt lõi không phải “xóa dấu âm cho đẹp”. Johnson chọn một phép biến đổi có **chứng minh bất đẳng thức và tính bất biến của đường đi**, nên có thể sử dụng Dijkstra mà không làm thay đổi lời giải tối ưu của bài toán gốc.

Bài học trình bày cơ chế, chứng minh, mô phỏng số, điều kiện áp dụng, độ phức tạp và một chương trình **Java 17+ chạy độc lập**, hỗ trợ truy vết đường đi, phát hiện chu trình âm, đỉnh không tới được, cạnh song song và self-loop.

## 1. Bài toán APSP và lý do Johnson cần thiết

Cho đồ thị có hướng \(G=(V,E)\), mỗi cạnh \(u\to v\) có trọng số \(w(u,v)\), có thể âm, bằng 0 hoặc dương. Trọng số của đường đi là **tổng trọng số trên các cạnh**. Với mọi cặp đỉnh s và t, cần xác định:

\[
d(s,t)=\min_{\text{đường đi }P:s\leadsto t}\ \sum_{e\in P}w(e).
\]

Nếu t không tới được từ s, quy ước \(d(s,t)=+\infty\). Khi s=t, **đường đi rỗng** có tổng bằng 0; nếu không có chu trình âm, giá trị ngắn nhất từ s về s là 0.

### Vì sao không chạy Dijkstra trực tiếp khi có cạnh âm?

Dijkstra dựa vào việc các đoạn đường đi thêm vào có trọng số **không âm**, nên một đỉnh có khoảng cách nhỏ nhất hiện tại có thể được xác nhận an toàn. Cạnh âm phá lập luận này.

Ví dụ:

~~~text
s --(2)--> a
|          ^
|          |
+--(5)--> b --(-4)--> a
~~~

Đường trực tiếp s→a có chi phí 2, nhưng đường s→b→a có chi phí \(5-4=1\). Một triển khai Dijkstra **chốt đỉnh a quá sớm** có thể kết luận sai. Có những biến thể priority queue tiếp tục cập nhật mà vẫn tìm được kết quả trên một số đồ thị có cạnh âm, nhưng đó **không phải** Dijkstra được bảo đảm bởi chứng minh chuẩn; không được dùng tùy ý thay cho thuật toán hỗ trợ cạnh âm.

**Bellman–Ford** giải bài một nguồn ngay cả khi có cạnh âm (và phát hiện chu trình âm tới được từ nguồn), nhưng chạy riêng Bellman–Ford từ mọi đỉnh có thể rất tốn thời gian.

**Floyd–Warshall** giải APSP trong \(O(V^3)\), phù hợp khi V không quá lớn hoặc đồ thị dày; nó cũng hỗ trợ trọng số âm nếu không có chu trình âm khi muốn khoảng cách hữu hạn.

**Johnson** đặc biệt hữu ích khi E nhỏ hơn đáng kể so với \(V^2\): trả chi phí Bellman–Ford **một lần**, sau đó tận dụng các lượt Dijkstra trên các cạnh đã trở thành không âm.

### Chu trình âm khiến bài toán thay đổi thế nào?

Một chu trình có tổng trọng số âm cho phép đi vòng lặp nhiều lần để **giảm tổng trọng số không giới hạn**. Với những cặp s,t có thể đi từ s đến chu trình âm rồi từ chu trình đến t, **không có khoảng cách ngắn nhất hữu hạn**; infimum là \(-\infty\).

Johnson theo đặc tả chuẩn **không trả một ma trận khoảng cách bình thường** nếu đồ thị chứa **bất kỳ chu trình âm nào**, kể cả ở thành phần không tới được từ một nguồn mà ta tình cờ chọn. Siêu nguồn ảo kết nối tới **mọi đỉnh**, nên Bellman–Ford sẽ phát hiện chu trình âm ở bất kỳ đâu.

Không nên gán một số lớn âm tùy ý làm “khoảng cách” cho chu trình âm; điều đó không có cùng ý nghĩa toán học với \(-\infty\).

## 2. Tư duy chính: đổi trọng số mà không đổi đường tối ưu

Johnson gán một số \(h[v]\) gọi là **thế năng** (*potential*) cho mỗi đỉnh. Với cạnh \(u\to v\), đặt:

\[
\boxed{w'(u,v)=w(u,v)+h[u]-h[v].}
\]

Thoạt nhìn, trọng số thay đổi theo **đầu và cuối cạnh**. Vì sao tổng trọng số của một đường đi vẫn so sánh được với đường khác?

Xét một đường đi \(P:s=v_0\to v_1\to\cdots\to v_k=t\). Tổng trọng số mới:

\[
\begin{aligned}
w'(P)
&=\sum_{i=0}^{k-1}\left(w(v_i,v_{i+1})+h[v_i]-h[v_{i+1}]\right)\\
&=w(P)+\underbrace{h[v_0]-h[v_1]+h[v_1]-\cdots-h[v_k]}_{\text{triệt tiêu từng cặp}}\\
&=\boxed{w(P)+h[s]-h[t].}
\end{aligned}
\]

Sự triệt tiêu này gọi là **tổng dạng telescoping**. Mọi đường đi từ cùng s đến cùng t đều được cộng **đúng một hằng số \(h[s]-h[t]\)**.

Vì thế, với hai đường đi P và Q đều từ s tới t:

\[
w(P)<w(Q)\quad\Longleftrightarrow\quad w'(P)<w'(Q).
\]

Tương tự, hai đường hòa nhau trước khi đổi trọng số vẫn hòa nhau sau khi đổi. **Thứ tự ưu tiên và tập đường đi ngắn nhất được giữ nguyên**. Đây là tính chất quan trọng nhất của reweighting.

### Khoảng cách khôi phục

Nếu \(d'(s,t)\) là khoảng cách ngắn nhất trên đồ thị đã đổi trọng số, ta có:

\[
d'(s,t)=d(s,t)+h[s]-h[t].
\]

Chuyển vế:

\[
\boxed{d(s,t)=d'(s,t)-h[s]+h[t].}
\]

Phải nhớ dấu của hai thế năng:

- Đổi cạnh: **cộng h của đỉnh xuất phát cạnh, trừ h của đỉnh đến**.
- Khôi phục khoảng cách: **trừ h của nguồn đường đi, cộng h của đích**.

Dùng nhầm \(+h[s]-h[t]\) khi **khôi phục** sẽ chuyển sai khoảng cách dù Dijkstra bên trong hoàn toàn đúng.

Nếu t **không tới được** từ s, việc đổi trọng số **không thêm/xóa cạnh nào**, nên t vẫn không tới được. Giá trị \(+\infty\) phải được giữ là “không tới được”, không thực hiện phép cộng/trừ các số h hữu hạn với một giá trị sentinel tùy ý.

## 3. Chọn thế năng h bằng Bellman–Ford

Công thức đổi cạnh chỉ dùng được với Dijkstra nếu tất cả trọng số mới đều **không âm**:

\[
w'(u,v)=w(u,v)+h[u]-h[v]\ge0.
\]

Chuyển vế:

\[
\boxed{h[v]\le h[u]+w(u,v).}
\]

Đây chính là **bất đẳng thức tam giác** thỏa bởi khoảng cách ngắn nhất từ cùng một nguồn đến mọi đỉnh của đồ thị **không có chu trình âm**.

Ta tạo một **siêu nguồn ảo** q và thêm cạnh \(q\to v\) trọng số 0 cho **mọi đỉnh v**. Chạy Bellman–Ford từ q, rồi đặt:

\[
\boxed{h[v]=d_G(q,v).}
\]

Vì q có cạnh đi tới mọi v, tất cả h[v] là hữu hạn khi không có chu trình âm. Với mọi cạnh cũ \(u\to v\), một đường từ q tới u rồi qua cạnh u→v là một phương án tới v, do đó:

\[
h[v]\le h[u]+w(u,v).
\]

Suy ra:

\[
w'(u,v)=w(u,v)+h[u]-h[v]\ge0.
\]

**Vậy hai điều được bảo đảm cùng lúc:**

1. Mọi cạnh của đồ thị mới có trọng số không âm ⇒ Dijkstra áp dụng được.
2. Mỗi đường s→t chỉ thay tổng trọng số bởi hằng số phụ thuộc s,t ⇒ đường đi tối ưu không đổi.

### Siêu nguồn là công cụ tính thế năng, không phải nguồn truy vấn

Siêu nguồn q chỉ phục vụ **Bellman–Ford tiền xử lý**. Khi chạy APSP, Johnson thực hiện Dijkstra từ **mỗi đỉnh gốc của G**, không cần chạy Dijkstra từ q và không đưa q vào ma trận kết quả V×V.

Không được nhầm việc q “tới được mọi đỉnh” với việc mọi cặp đỉnh trong đồ thị gốc đều tới được nhau. Các cạnh \(q\to v\) chỉ dùng cho tính h và sau đó bị bỏ khỏi đồ thị chạy Dijkstra.

## 4. Tối ưu cài đặt: không nhất thiết tạo đỉnh q thật

Cách mô tả trong sách thường xây \(G'=(V\cup\{q\}, E\cup\{q\to v: v\in V\})\) rồi Bellman–Ford từ q. Tuy nhiên ta có thể mô phỏng cùng kết quả mà **không tạo một đỉnh hoặc cạnh mới nào**:

~~~text
for mỗi đỉnh v:
    h[v] = 0

lặp tối đa V-1 lượt:
    for mỗi cạnh u -> v trọng số w:
        nếu h[u] + w < h[v]:
            h[v] = h[u] + w

for mỗi cạnh u -> v trọng số w:
    nếu h[u] + w < h[v]:
        báo có chu trình âm
~~~

**Vì sao tất cả h khởi tạo bằng 0 là đúng?** Với siêu nguồn q, mỗi đỉnh v có một đường q→v chi phí 0. Khởi tạo h[v]=0 tương đương đã relax tất cả các cạnh ảo q→v **ngay lúc đầu**.

Sau đó chỉ cần xét các cạnh gốc. Khi không có chu trình âm, mỗi đường ngắn nhất đơn giữa hai đỉnh của G có tối đa \(V-1\) cạnh gốc; do đó \(V-1\) lượt relax các cạnh gốc là đủ để thu đúng thế năng. Một lượt kiểm tra nữa phát hiện chu trình âm.

**Hai lựa chọn cài đặt đều đúng:**

- Tạo q thật, chạy Bellman–Ford trên \(V+1\) đỉnh và \(E+V\) cạnh.
- Không tạo q, khởi tạo mọi `h[v]=0` rồi relax các cạnh gốc tối đa \(V-1\) lượt, như mã Java trong bài.

Cách thứ hai giảm cấu trúc phụ nhưng **không thay đổi chứng minh** hay điều kiện phát hiện chu trình âm.

### Dừng sớm

Nếu một lượt quét tất cả các cạnh không còn cập nhật h, ta có thể dừng trước \(V-1\) lượt. Dừng sớm không làm thay đổi kết quả, vì mọi bất đẳng thức \(h[v]\le h[u]+w(u,v)\) đã thỏa.

Tuy nhiên sau khi kết thúc các lượt, **vẫn nên kiểm tra điều kiện chu trình âm** theo hợp đồng thuật toán. Nếu còn cạnh nào làm giảm h, không được tiếp tục sang Dijkstra.

## 5. Quy trình Johnson đầy đủ

~~~text
JOHNSON(graph G with V vertices, directed weighted edges E):
    // Step 1: potentials, equivalent to a virtual super-source
    for v in V: h[v] = 0
    repeat at most V-1 times:
        changed = false
        for edge (u, v, w) in E:
            if h[u] + w < h[v]:
                h[v] = h[u] + w
                changed = true
        if not changed: break

    // Step 2: negative-cycle check
    for edge (u, v, w) in E:
        if h[u] + w < h[v]:
            report NEGATIVE_WEIGHT_CYCLE

    // Step 3: reweight every original edge
    for edge (u, v, w) in E:
        newWeight = w + h[u] - h[v]
        assert newWeight >= 0
        add edge (u, v, newWeight) to reweighted graph

    // Step 4: Dijkstra from every original vertex
    for source s in V:
        distPrime, predecessor = DIJKSTRA(reweightedGraph, s)
        for target t in V:
            if distPrime[t] is INF:
                dist[s][t] = INF
            else:
                dist[s][t] = distPrime[t] - h[s] + h[t]
        save predecessor for path reconstruction if needed

    return dist, predecessors, h
~~~

### Các bất biến theo từng giai đoạn

**Bellman–Ford:** mỗi lượt relax giữ h là giá trị một đường đi từ siêu nguồn ảo; sau đủ lượt và kiểm tra âm, h thỏa bất đẳng thức cho mọi cạnh.

**Reweighting:** tất cả cạnh giữ nguyên điểm đầu/điểm cuối, chỉ thay trọng số, nên reachability không đổi. Mọi cạnh mới không âm.

**Dijkstra:** trên đồ thị mới, khoảng cách `distPrime` tối ưu theo tổng trọng số mới. Tiền nhiệm (*predecessor*) được lưu khi có một phép thư giãn làm giảm khoảng cách.

**Restoration:** công thức `distPrime-h[source]+h[target]` trả lại đúng giá trị tối ưu trên đồ thị gốc.

Mỗi bước có một hợp đồng riêng. Ví dụ một chương trình có thể chạy Dijkstra đúng trên trọng số mới nhưng trả ma trận sai nếu đảo dấu ở bước restoration.

## 6. Ví dụ đầy đủ: năm đỉnh, có cạnh âm nhưng không có chu trình âm

Xét các đỉnh `0..4` với các cạnh có hướng:

| Cạnh u→v | w(u,v) |
|---|---:|
| 0 → 1 | 3 |
| 0 → 2 | 8 |
| 0 → 4 | -4 |
| 1 → 3 | 1 |
| 1 → 4 | 7 |
| 2 → 1 | 4 |
| 3 → 0 | 2 |
| 3 → 2 | -5 |
| 4 → 3 | 6 |

Có **hai cạnh âm** là `0→4=-4` và `3→2=-5`. Điều này **không tự nói có chu trình âm**: tổng của một chu trình phải được tính trên **toàn bộ** các cạnh của vòng đó. Bellman–Ford với siêu nguồn ảo xác nhận đồ thị này **không chứa chu trình âm**.

### Bước 1 — Thế năng Bellman–Ford

Kết quả:

~~~text
Vertex:     0   1   2   3   4
h[v]:       0  -1  -5   0  -4
~~~

Để thấy h hợp lý:

- `h[4]=-4` có thể đạt từ cạnh ảo q→0 trọng số 0, rồi cạnh 0→4 trọng số -4.
- `h[2]=-5` có thể đạt từ q→3 (0), rồi 3→2 (-5).
- `h[1]=-1` có thể đạt từ q→3 (0), 3→2 (-5), 2→1 (+4), tổng -1.
- `h[0]=0` và `h[3]=0` do cạnh ảo trực tiếp đạt chi phí 0 và không có đường từ q tới các đỉnh này rẻ hơn 0.

Khi có nhiều đường từ q tới một đỉnh, h là **giá trị nhỏ nhất** trong tất cả chúng; không phải một h chọn theo cảm tính.

### Bước 2 — Đổi từng trọng số

Áp dụng `w' = w + h[u] - h[v]`:

| Cạnh | Trọng số gốc w | Thế năng đầu/cuối | Trọng số mới w' |
|---|---:|---|---:|
| 0→1 | 3 | 0, -1 | **4** |
| 0→2 | 8 | 0, -5 | **13** |
| 0→4 | -4 | 0, -4 | **0** |
| 1→3 | 1 | -1, 0 | **0** |
| 1→4 | 7 | -1, -4 | **10** |
| 2→1 | 4 | -5, -1 | **0** |
| 3→0 | 2 | 0, 0 | **2** |
| 3→2 | -5 | 0, -5 | **0** |
| 4→3 | 6 | -4, 0 | **2** |

Tất cả trọng số mới **không âm**, kể cả các cạnh vốn âm. Đồ thị vẫn có đúng năm đỉnh và chín cạnh gốc; chỉ trọng số đã biến đổi.

### Bước 3 — Dijkstra từ đỉnh 0

Trên đồ thị mới, có đường:

~~~text
0 --(0)--> 4 --(2)--> 3 --(0)--> 2
~~~

Tổng mới là \(d'(0,2)=0+2+0=2\). Khôi phục:

\[
d(0,2)=d'(0,2)-h[0]+h[2]=2-0-5=\boxed{-3}.
\]

Trên đồ thị **gốc**, chính đường ấy có tổng:

\[
w(0\to4\to3\to2)=-4+6-5=\boxed{-3}.
\]

Phép đổi trọng số đã làm các cạnh không âm nhưng **không đổi đường tối ưu**. Dijkstra từ 0 có thể lưu `parent[4]=0`, `parent[3]=4`, `parent[2]=3`; truy vết từ 2 về 0 cho đường `[0,4,3,2]`.

### Bước 4 — Ma trận APSP gốc

Chạy Dijkstra từ cả năm đỉnh, sau đó khôi phục, nhận:

| Nguồn \ Đích | 0 | 1 | 2 | 3 | 4 |
|---:|---:|---:|---:|---:|---:|
| **0** | 0 | 1 | -3 | 2 | -4 |
| **1** | 3 | 0 | -4 | 1 | -1 |
| **2** | 7 | 4 | 0 | 5 | 3 |
| **3** | 2 | -1 | -5 | 0 | -2 |
| **4** | 8 | 5 | 1 | 6 | 0 |

Đây là **ma trận khoảng cách của đồ thị gốc**, nên **có số âm** dù mỗi lượt Dijkstra bên trong đã chạy trên đồ thị **không âm**. Johnson **không biến các khoảng cách cuối cùng thành không âm**, mà chỉ tạo một bài toán tương đương có cạnh không âm cho Dijkstra.

Ví dụ `d(1,2)=-4` qua đường 1→3 (+1), 3→2 (-5). Khoảng cách `d(2,0)=7` qua 2→1 (+4), 1→3 (+1), 3→0 (+2).

## 7. Bất biến và chứng minh tính đúng

Có thể chứng minh Johnson qua ba bổ đề.

### Bổ đề 1 — Mọi cạnh đổi trọng số đều không âm

Bellman–Ford trả h thỏa:

\[
h[v]\le h[u]+w(u,v)\quad\forall(u,v)\in E
\]

khi không có chu trình âm.

Do đó:

\[
w'(u,v)=w(u,v)+h[u]-h[v]\ge0.
\]

Chứng minh không dựa vào việc phần lớn trọng số dương; nó áp dụng cho **mọi cạnh**, kể cả cạnh gốc âm và cạnh 0.

### Bổ đề 2 — Mọi đường đi từ s tới t đổi cùng một hằng số

Với mọi đường P từ s tới t:

\[
w'(P)=w(P)+h[s]-h[t].
\]

Với hai đường P,Q có cùng đầu mút, hiệu:

\[
w'(P)-w'(Q)=w(P)-w(Q).
\]

Mọi quan hệ \(\le\), \(<\), \(=\) về tổng trọng số giữa các đường có cùng đầu mút được giữ nguyên. Vì thế đường ngắn nhất của G cũng là đường ngắn nhất của G' đổi trọng số, và ngược lại.

**Quan trọng:** không được so sánh đường **khác cặp đầu mút** chỉ bằng trọng số mới rồi mặc nhiên suy ra thứ tự như cũ; hằng số bù phụ thuộc s và t.

### Bổ đề 3 — Dijkstra tìm đúng khoảng cách trên G'

Sau bổ đề 1, tất cả cạnh của G' có trọng số **không âm**. Khi Dijkstra được cài đúng và không có overflow, thuật toán tìm được \(d'(s,t)\) cho mọi đích t từ nguồn s. Với t không tới được, trả **INF**.

Nhờ bổ đề 2, \(d(s,t)=d'(s,t)-h[s]+h[t]\) chính là khoảng cách ngắn nhất gốc. Chạy cho mọi s cho toàn bộ ma trận APSP.

**Hệ quả về đường đi:** nếu Dijkstra lưu tiền nhiệm `parent_s[t]` của t khi thư giãn tốt hơn, việc truy vết vẫn trả một **đường tối ưu của G**. Không phải chạy lại tìm đường trên đồ thị gốc; danh sách đỉnh/cạnh của lời giải tối ưu được giữ nguyên qua reweighting.

### Vì sao chu trình âm không thể được “chữa” bằng thế năng?

Xét một chu trình đóng \(C:v_0\to v_1\to\cdots\to v_0\). Trọng số mới:

\[
w'(C)=w(C)+h[v_0]-h[v_0]=w(C).
\]

**Tổng của mọi chu trình không đổi** dưới phép đổi trọng số. Nếu tồn tại chu trình âm, nó vẫn âm trong mọi phép đổi kiểu `w+h[u]-h[v]`; không thể biến **mọi cạnh** thành không âm bằng một bộ h hữu hạn như yêu cầu Dijkstra. Đây là lý do Bellman–Ford phải kiểm tra và dừng trước khi đổi trọng số.

## 8. Truy vết đường đi trong Johnson

Nếu bài chỉ yêu cầu **ma trận khoảng cách**, không cần lưu parent cho mọi nguồn. Nhưng nếu đề còn muốn xuất một đường đi cụ thể, có thể giữ mảng `parent[source][vertex]` trong mỗi lượt Dijkstra.

Quy tắc thư giãn ở đồ thị đổi trọng số:

~~~text
if dist[u] + newWeight(u,v) < dist[v]:
    dist[v] = dist[u] + newWeight(u,v)
    parent[v] = u
~~~

Chỉ gán lại parent khi tìm được khoảng cách **tốt hơn thật sự**, không gán tùy tiện cho cạnh có đỉnh đã xử lý. Nếu nhiều đường ngắn nhất hòa nhau, thuật toán có thể trả **một** trong số đó, phụ thuộc thứ tự cạnh và quy tắc tie.

Truy vết từ đích t lên nguồn s:

~~~text
if distOriginal[s][t] là INF:
    return []                   // không tới được

path = []
v = t
while v != s:
    path.add(v)
    v = parent[s][v]
    if v không hợp lệ:
        báo lỗi cây cha

path.add(s)
reverse(path)
return path
~~~

Đường nguồn tới chính nó được biểu diễn `[source]` với tổng trọng số 0 nếu không có chu trình âm. Khi không tới được, trả danh sách rỗng `[]`.

### Cây cha được xây trên trọng số mới có dùng được cho đồ thị gốc không?

**Có**, vì tập đỉnh/cạnh **không đổi** khi reweighting. Dijkstra chỉ chọn đường khác theo số đã biến đổi; bổ đề 2 nói đường tối ưu **giữa cùng s,t** vẫn tối ưu trên graph gốc.

Điều không nên làm: dùng **dist' như là dist gốc** khi in nhãn độ dài, hoặc tính lại `parent` bằng cách so với trọng số gốc trong khi không cập nhật distance theo quy tắc nhất quán.

## 9. Java 17+: Johnson APSP, đường đi và lỗi chu trình âm

Chương trình dưới đây sử dụng **danh sách cạnh** để Bellman–Ford và **danh sách kề** để Dijkstra.

Thiết kế có chủ đích:

- Dùng `record Edge(int from,int to,long weight)` để biểu diễn **cung có hướng**; nhiều cạnh cùng cặp đỉnh được phép.
- Không tạo siêu nguồn thật; khởi tạo `h[v]=0` cho mọi v tương đương cạnh siêu nguồn trọng số 0.
- Dùng `Math.addExact`/`Math.subtractExact` để **phát hiện tràn số** thay vì để `long` tràn im lặng và làm sai cận/đường đi.
- Dùng `Long` bằng **null** để biểu thị **không tới được**, không dùng `Long.MAX_VALUE` làm sentinel gây nhầm với một khoảng cách hợp lệ rất lớn.
- Dijkstra dùng `PriorityQueue`, chấp nhận nhiều bản ghi cho cùng một đỉnh (*lazy decrease-key*) và bỏ bản ghi cũ khi pop.
- Lưu `predecessor` cho từng nguồn để khôi phục đường đi tối ưu; chỉ update khi có cải thiện nghiêm ngặt.
- Nếu Bellman–Ford còn cạnh relax được sau các lượt, ném `IllegalArgumentException` với thông báo **`negative-weight cycle`**.
- Mọi đầu vào cạnh được kiểm tra chỉ số nằm trong `0..V-1`. V=0 cho kết quả ma trận rỗng.

Lưu tệp **JohnsonReweightingDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class JohnsonReweightingDemo {
    record Edge(int from, int to, long weight) {}
    record State(int vertex, long distance) {}
    record OneSource(Long[] distance, int[] parent) {}
    record Result(long[] potential, Long[][] distance, int[][] parent) {}

    static Result johnson(int vertices, List<Edge> edges) {
        Objects.requireNonNull(edges, "edges");
        if (vertices < 0) {
            throw new IllegalArgumentException("negative vertex count");
        }
        for (Edge e : edges) {
            if (e == null || e.from() < 0 || e.from() >= vertices
                    || e.to() < 0 || e.to() >= vertices) {
                throw new IllegalArgumentException("invalid directed edge");
            }
        }

        // Bellman-Ford from a virtual super-source:
        // h[v]=0 represents its zero-weight edge to every v.
        long[] h = new long[vertices];
        for (int pass = 0; pass < vertices - 1; pass++) {
            boolean changed = false;
            for (Edge e : edges) {
                long candidate = Math.addExact(h[e.from()], e.weight());
                if (candidate < h[e.to()]) {
                    h[e.to()] = candidate;
                    changed = true;
                }
            }
            if (!changed) {
                break;
            }
        }

        // Any further relaxation proves a negative-weight cycle.
        for (Edge e : edges) {
            long candidate = Math.addExact(h[e.from()], e.weight());
            if (candidate < h[e.to()]) {
                throw new IllegalArgumentException("negative-weight cycle");
            }
        }

        // Reweight the SAME directed edges; do not add super-source.
        List<List<Edge>> nonnegative = new ArrayList<>();
        for (int v = 0; v < vertices; v++) {
            nonnegative.add(new ArrayList<>());
        }
        for (Edge e : edges) {
            long adjusted = Math.subtractExact(
                Math.addExact(e.weight(), h[e.from()]), h[e.to()]
            );
            if (adjusted < 0) {
                throw new IllegalStateException("negative reweighted edge");
            }
            nonnegative.get(e.from()).add(
                new Edge(e.from(), e.to(), adjusted)
            );
        }

        Long[][] resultDistance = new Long[vertices][vertices];
        int[][] resultParent = new int[vertices][vertices];

        for (int source = 0; source < vertices; source++) {
            OneSource out = dijkstra(nonnegative, source);
            resultParent[source] = out.parent();
            for (int target = 0; target < vertices; target++) {
                Long reweightedDistance = out.distance()[target];
                if (reweightedDistance == null) {
                    resultDistance[source][target] = null;
                    continue;
                }

                // d(s,t) = d'(s,t) - h[s] + h[t].
                long restored = Math.addExact(
                    Math.subtractExact(reweightedDistance, h[source]),
                    h[target]
                );
                resultDistance[source][target] = restored;
            }
        }
        return new Result(h.clone(), resultDistance, resultParent);
    }

    private static OneSource dijkstra(
        List<List<Edge>> graph, int source
    ) {
        int n = graph.size();
        Long[] distance = new Long[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        PriorityQueue<State> pq = new PriorityQueue<>(
            Comparator.comparingLong(State::distance)
                      .thenComparingInt(State::vertex)
        );
        distance[source] = 0L;
        pq.add(new State(source, 0L));

        while (!pq.isEmpty()) {
            State cur = pq.poll();
            int u = cur.vertex();

            // Ignore an outdated heap entry after a better route.
            if (distance[u] == null
                    || cur.distance() != distance[u]) {
                continue;
            }

            for (Edge e : graph.get(u)) {
                long candidate = Math.addExact(
                    cur.distance(), e.weight()
                );
                if (distance[e.to()] == null
                        || candidate < distance[e.to()]) {
                    distance[e.to()] = candidate;
                    parent[e.to()] = u;
                    pq.add(new State(e.to(), candidate));
                }
            }
        }
        return new OneSource(distance, parent);
    }

    static List<Integer> restorePath(
        Result result, int source, int target
    ) {
        Objects.requireNonNull(result, "result");
        int n = result.distance().length;
        if (source < 0 || source >= n
                || target < 0 || target >= n) {
            throw new IllegalArgumentException("invalid path endpoint");
        }
        if (result.distance()[source][target] == null) {
            return List.of();
        }

        List<Integer> backwards = new ArrayList<>();
        int v = target;
        for (int count = 0; count < n && v != -1; count++) {
            backwards.add(v);
            if (v == source) {
                break;
            }
            v = result.parent()[source][v];
        }

        if (backwards.isEmpty()
                || backwards.get(backwards.size() - 1) != source) {
            throw new IllegalStateException("invalid predecessor chain");
        }
        Collections.reverse(backwards);
        return List.copyOf(backwards);
    }

    private static String showDistances(Long[] row) {
        List<String> fields = new ArrayList<>();
        for (Long value : row) {
            fields.add(value == null ? "INF" : value.toString());
        }
        return fields.toString();
    }

    public static void main(String[] args) {
        List<Edge> edges = List.of(
            new Edge(0, 1, 3),
            new Edge(0, 2, 8),
            new Edge(0, 4, -4),
            new Edge(1, 3, 1),
            new Edge(1, 4, 7),
            new Edge(2, 1, 4),
            new Edge(3, 0, 2),
            new Edge(3, 2, -5),
            new Edge(4, 3, 6)
        );

        Result all = johnson(5, edges);
        System.out.println("Potentials: "
            + Arrays.toString(all.potential()));
        System.out.println("All-pairs original distances:");
        for (int source = 0; source < 5; source++) {
            System.out.println("from " + source + ": "
                + showDistances(all.distance()[source]));
        }
        System.out.println("Shortest path 0 -> 2: "
            + restorePath(all, 0, 2));
        System.out.println("Distance 0 -> 2: "
            + all.distance()[0][2]);
        System.out.println("Self path 3 -> 3: "
            + restorePath(all, 3, 3));

        Result isolated = johnson(3, List.of(new Edge(0, 1, 2)));
        System.out.println("Unreachable 0 -> 2: "
            + showDistances(new Long[] {isolated.distance()[0][2]}));
        System.out.println("Unreachable path 0 -> 2: "
            + restorePath(isolated, 0, 2));

        Result parallel = johnson(3, List.of(
            new Edge(0, 1, 5), new Edge(0, 1, 2),
            new Edge(1, 2, -1), new Edge(2, 2, 0)
        ));
        System.out.println("Parallel/self-loop 0 -> 2: "
            + parallel.distance()[0][2]);
        System.out.println("Empty graph vertices: "
            + johnson(0, List.of()).distance().length);

        try {
            johnson(3, List.of(
                new Edge(0, 1, 1),
                new Edge(1, 2, -3),
                new Edge(2, 0, 1)
            ));
        } catch (IllegalArgumentException ex) {
            System.out.println("Negative cycle rejected: "
                + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac JohnsonReweightingDemo.java
java JohnsonReweightingDemo
~~~

**Stdout chính xác với dữ liệu mẫu:**

~~~text
Potentials: [0, -1, -5, 0, -4]
All-pairs original distances:
from 0: [0, 1, -3, 2, -4]
from 1: [3, 0, -4, 1, -1]
from 2: [7, 4, 0, 5, 3]
from 3: [2, -1, -5, 0, -2]
from 4: [8, 5, 1, 6, 0]
Shortest path 0 -> 2: [0, 4, 3, 2]
Distance 0 -> 2: -3
Self path 3 -> 3: [3]
Unreachable 0 -> 2: [INF]
Unreachable path 0 -> 2: []
Parallel/self-loop 0 -> 2: 1
Empty graph vertices: 0
Negative cycle rejected: negative-weight cycle
~~~

### Đọc mã và đối chiếu với công thức

**Bellman–Ford ảo.** `new long[vertices]` tạo toàn bộ h=0. Quét mỗi cạnh để relax \(h[v]\) theo \(h[u]+w\), tối đa \(V-1\) lượt; kiểm tra lại một lượt trước khi xây đồ thị mới. Nếu phát hiện chu trình âm, **không Dijkstra**.

**Reweighting.** `Math.addExact(w,h[from])` rồi `Math.subtractExact(...,h[to])` chính là \(w+h[u]-h[v]\). Phép kiểm tra `adjusted<0` là một assertion về **tính đúng của Bellman–Ford/potential** khi không có overflow.

**Priority queue.** `State(vertex,distance)` là một bản ghi tại thời điểm thêm heap. Nếu sau đó tìm được đường tốt hơn, heap vẫn chứa bản ghi cũ, nhưng vòng `if (cur.distance()!=distance[u]) continue` bỏ nó an toàn. Thêm vào heap khi khoảng cách **nhỏ hơn nghiêm ngặt** giúp tránh lặp vô hạn do cạnh 0.

**Đường đi.** `parent[v]=u` chỉ được gán khi relax làm giảm khoảng cách. Sau Johnson, cây parent của lượt từ s mô tả các đường đi ngắn nhất về **tổng trọng số gốc**, dù parent được tìm bằng đồ thị mới.

**Không tới được.** `Long` null thể hiện INF. Cách này không nhập nhằng với một khoảng cách hữu hạn bằng `Long.MAX_VALUE`, và không thực hiện phép toán số học với INF.

**Tổng lớn.** `Math.addExact` và `Math.subtractExact` có thể ném `ArithmeticException` nếu một **bước trung gian** vượt miền `long`, kể cả khi trong vài phép sắp xếp lại toán học giá trị cuối có thể vừa miền. Đây là **lựa chọn an toàn**: không trả khoảng cách sai do overflow. Với miền số cực lớn cần biểu diễn chính xác bằng `BigInteger` hoặc xác định giới hạn trọng số trước khi dùng thuật toán.

**Kết quả record và mảng.** `record Result` không khiến các mảng `Long[][]`, `int[][]` bất biến. Demo đọc dữ liệu sau khi trả; trong thư viện công cộng nên phòng vệ bằng deep copy hoặc phương thức truy vấn chỉ đọc nếu người dùng có thể sửa các mảng.

## 10. Biến thể có cạnh âm: tại sao Dijkstra bên trong vẫn đúng?

Một thắc mắc thường gặp: “Johnson dùng Bellman–Ford chỉ một lần, sao lại giải được đường ngắn nhất từ mọi nguồn khi graph có cạnh âm?”

Lý do là Bellman–Ford **không trực tiếp tính APSP**. Nó tính một **bộ thế năng h toàn cục**, thỏa điều kiện cho **mọi cạnh gốc**, không phụ thuộc nguồn s:

\[
w(u,v)+h[u]-h[v]\ge0\quad\forall(u,v).
\]

Một khi mọi cạnh mới không âm, Dijkstra có thể chạy **từ bất kỳ s nào** trên **cùng một đồ thị G'**. Mỗi nguồn dùng lại h đã tính; không cần chạy Bellman–Ford lại.

Công thức khôi phục **thay đổi theo nguồn và đích**:

\[
d(s,t)=d'(s,t)-h[s]+h[t],
\]

nhưng **không cần tính h mới**. Đây là chỗ Johnson tiết kiệm công sức trên đồ thị thưa so với chạy Bellman–Ford từ từng nguồn.

### Nếu h không duy nhất thì sao?

Có thể tồn tại nhiều bộ thế năng khác nhau làm mọi cạnh \(w'\) không âm. Johnson chọn h từ khoảng cách siêu nguồn vì **dễ xây và chứng minh**.

Nếu cộng cùng một hằng số c vào **mọi** h[v], ta có:

\[
w+h[u]+c-(h[v]+c)=w+h[u]-h[v].
\]

Trọng số mới **không đổi**. Vì thế h tuyệt đối không nhất thiết là một giá trị có ý nghĩa độc lập; **hiệu thế năng giữa hai đầu mút** mới ảnh hưởng phép đổi cạnh.

### Nếu đồ thị không liên thông thì sao?

Siêu nguồn ảo có cạnh 0 tới mọi đỉnh, nên Bellman–Ford vẫn tính h cho tất cả thành phần. Nhưng Johnson **không bổ sung cạnh nối giữa các đỉnh gốc** khi tạo G' để chạy Dijkstra. Do đó:

- Đỉnh không tới được từ s trong G vẫn **không tới được trong G'**.
- Ma trận có thể có nhiều ô INF.
- Một chu trình âm trong bất kỳ thành phần nào vẫn bị phát hiện trước khi chạy Dijkstra.

Đồ thị có hướng chỉ có một chiều tới nhau cũng được xử lý đúng; không được tự thêm cạnh ngược.

## 11. Phân tích độ phức tạp thời gian và bộ nhớ

Gọi \(V=|V|\), \(E=|E|\). Dùng **danh sách cạnh** để Bellman–Ford và **danh sách kề** cho Dijkstra.

### Giai đoạn Bellman–Ford

Khởi tạo h mất O(V). Mỗi lượt quét E cạnh; nhiều nhất \(V-1\) lượt, rồi thêm một lượt kiểm tra. Vì vậy:

\[
T_{BF}=O(VE+V).
\]

Nếu xây siêu nguồn thật với \(V+1\) đỉnh, \(E+V\) cạnh, cận theo dạng tổng quát là \(O(V(E+V))\). Cách khởi tạo h=0 ảo có thể tránh quét V cạnh ảo trong mỗi vòng, nhưng **không thay đổi bản chất** chi phí Bellman–Ford trên các cạnh gốc.

### Giai đoạn đổi trọng số

Mỗi cạnh được đổi trọng số và đưa vào danh sách kề đúng một lần, ngoài O(V) khởi tạo các danh sách:

\[
T_{\text{reweight}}=O(V+E).
\]

### Giai đoạn V lần Dijkstra

Một lượt Dijkstra với danh sách kề và binary heap có cận thông dụng:

\[
O((V+E)\log V)
\]

(với \(V\ge2\), hiểu \(\log V\) theo cách tránh 0 ở trường hợp rất nhỏ). Heap lazy có thể chứa nhiều bản ghi cho một đỉnh, nhưng các lần thư giãn thành công bị giới hạn bởi việc xét các cạnh; cận với log V vẫn áp dụng ở bậc lớn cho đồ thị đơn/thưa, hoặc dùng \(\log(V+E)\) nếu muốn nêu kích thước heap tường minh trong multigraph có nhiều cạnh song song.

Chạy từ tất cả V đỉnh:

\[
T_{\text{Dijkstra all}}=O\big(V(V+E)\log V\big)
\]

theo cách ghi thông dụng với binary heap.

Tổng quát:

\[
\boxed{T_{\text{Johnson}}=
O\big(VE+V(V+E)\log V\big)}
\]

(kể chi phí tạo ma trận kết quả \(O(V^2)\) nếu yêu cầu lưu tất cả cặp; nó đã nằm trong phần \(V(V+E)\log V\) đối với V đủ lớn).

Nếu graph thưa với \(E=O(V)\), thời gian thường được viết gọn thành:

\[
O(V^2\log V)
\]

cho bản heap nhị phân. Nếu dùng cấu trúc heap có thao tác decrease-key tốt hơn theo mô hình lý thuyết, có thể đạt dạng \(O(VE+V^2\log V)\) với Fibonacci heap; nhưng không nên áp con số ấy cho mã `PriorityQueue` của Java vì `PriorityQueue` ở đây **không hỗ trợ decrease-key trực tiếp**.

### Bộ nhớ

- Đồ thị gốc, danh sách cạnh/kề và đồ thị đổi trọng số: **O(V+E)**.
- h, mảng Dijkstra tạm, heap và tiền nhiệm của **một nguồn**: O(V+E) trong cận thông dụng cho heap lazy.
- Nếu lưu **mọi khoảng cách**: ma trận **O(V²)**.
- Nếu lưu **mọi predecessor** để truy vết mọi cặp: thêm ma trận **O(V²)**.

Vậy bản Java có tổng bộ nhớ **O(V²+V+E)**. Khi chỉ cần tính một nguồn hoặc xuất kết quả theo từng hàng, có thể cân nhắc tránh lưu mọi predecessor, thậm chí stream từng hàng khoảng cách để giảm bộ nhớ; nhưng nếu hợp đồng yêu cầu trả toàn bộ ma trận APSP thì riêng đầu ra đã cần O(V²).

### So với thuật toán khác

| Thuật toán | Cạnh âm? | Chu trình âm | Độ phức tạp thông dụng | Khi nên cân nhắc |
|---|---|---|---|---|
| BFS từ từng nguồn | Không dùng trọng số khác nhau | Không thích hợp | O(V(V+E)) | Đồ thị không trọng số |
| Dijkstra từ từng nguồn | **Không có cạnh âm** | Không áp dụng | O(V(V+E)log V) với heap | Graph không âm |
| Bellman–Ford từ từng nguồn | Có | Phát hiện chu trình âm **tới được từng nguồn** | O(V²E) cận điển hình | Một số bài hỗ trợ âm / cần chứng cứ |
| Floyd–Warshall | Có | Có thể phát hiện từ đường chéo âm | **O(V³)**, O(V²) nhớ | V nhỏ, graph dày |
| Johnson | Có, **không có chu trình âm** | Kiểm tra toàn đồ thị nhờ siêu nguồn | **O(VE+V(V+E)log V)** | APSP trên graph thưa có cạnh âm |

Chọn thuật toán theo **mục tiêu, biểu diễn graph, V/E, dấu trọng số và nhu cầu truy vết**, không chỉ theo một nhãn “nhanh nhất” chung.

## 12. Tính đúng khi có cạnh song song, self-loop và đỉnh cô lập

### Cạnh song song

Nếu hai cạnh cùng đi từ u sang v nhưng có trọng số khác nhau, cả hai đều phải được giữ hoặc loại cạnh thừa bằng một bước tối ưu được chứng minh.

Ví dụ:

~~~text
0 -> 1 (5)
0 -> 1 (2)
1 -> 2 (-1)
~~~

Đường tốt nhất 0→1→2 dùng **cạnh 0→1 trọng số 2**, nên có tổng \(2-1=1\). Mã Java giữ cả hai cạnh trong danh sách; Dijkstra chọn được cạnh có khoảng cách tốt hơn.

Nếu đã gộp cạnh song song theo **trọng số nhỏ nhất** trước Bellman–Ford, điều đó có thể bảo toàn khoảng cách ngắn nhất giữa các đỉnh với bài toán đường đi trọng số tổng, nhưng nếu ứng dụng cần **ID cạnh**, số lượng tuyến hoặc nhiều đường đi phân biệt thì việc gộp có thể không phù hợp.

### Self-loop

Cạnh \(u\to u\) có trọng số mới:

\[
w'(u,u)=w(u,u)+h[u]-h[u]=w(u,u).
\]

- Self-loop **âm** chính là chu trình âm độ dài 1 ⇒ Johnson phải từ chối.
- Self-loop **0** không tạo lợi ích để giảm khoảng cách; không làm Dijkstra lặp vô hạn nếu chỉ cập nhật khi có khoảng cách **nhỏ hơn nghiêm ngặt**.
- Self-loop **dương** cũng không giúp tạo đường ngắn nhất từ u về u khi đường rỗng có chi phí 0.

### Đỉnh cô lập

Một đỉnh không có cạnh vào/ra vẫn được tính trong V. Bellman–Ford ảo cho h=0 ở đỉnh đó, Dijkstra từ nó chỉ tới chính nó với khoảng cách 0, các cặp khác có thể không tới được. Không được tự coi INF là 0 hoặc dùng đường rỗng cho hai đỉnh khác nhau.

### Chu trình tổng bằng 0

Chu trình có tổng 0 **được phép**. Nó không giúp giảm khoảng cách bằng cách quay lặp; Johnson vẫn có thể đổi mọi cạnh về không âm, và Dijkstra xử lý được các cạnh bằng 0. Một chu trình 0 có thể tạo nhiều đường đi cùng tổng trọng số (nếu cho phép walk lặp cạnh), nhưng ta vẫn có thể lưu một **đường đi đơn** tối ưu qua predecessor bằng cách chỉ cập nhật khi khoảng cách giảm thật.

## 13. Độ tin cậy số học và giới hạn của long

Trong bài toán đường đi có trọng số, **overflow có thể phá tính đúng** ngay cả khi công thức thuật toán chính xác.

Ví dụ phép cộng `h[u]+w` của Bellman–Ford có thể vượt miền `long`. Nếu Java để tràn im lặng, một giá trị dương lớn có thể trở thành âm và gây **báo chu trình âm giả** hoặc tạo trọng số mới âm sai.

Tương tự, `w+h[u]-h[v]` có thể có bước trung gian vượt miền biểu diễn, và `d'-h[s]+h[t]` cũng cần miền đủ rộng.

Mã minh họa chọn **`Math.addExact` và `Math.subtractExact`**. Nếu phép toán trung gian không biểu diễn được trong `long`, nó ném `ArithmeticException` thay vì lặng lẽ trả dữ liệu sai.

Điều này **không có nghĩa Java long luôn đủ**; người thiết kế phải biết giới hạn đầu vào. Nếu trọng số, số đỉnh và tổng đường đi có thể vượt 64-bit, một giải pháp dùng **`BigInteger`** hoặc kiểm soát miền giá trị theo đề bài có thể cần thiết.

### Không trộn INF với số thật

Một số cài đặt dùng `INF=Long.MAX_VALUE/4` rồi chặn kết quả ở INF để giảm rủi ro tràn. Cách này dễ code nhưng **có thể làm mất khoảng cách hữu hạn lớn hơn sentinel**, trừ khi có chứng minh giới hạn số lớn nhất của mọi đường đi hợp lệ.

Trong ví dụ Java, `Long[] distance` dùng **null** cho đỉnh chưa tới được. Đây không phải lựa chọn bắt buộc, nhưng giúp tách rõ khái niệm **không tồn tại đường** với **đường rất dài**. Khi xuất ra bảng, null được hiển thị thành chữ `INF`.

### Chu trình âm và khoảng cách âm khác nhau

- **Cạnh âm:** hoàn toàn có thể có trong graph hợp lệ cho Johnson.
- **Đường đi ngắn nhất âm:** hoàn toàn bình thường nếu graph không có chu trình âm.
- **Chu trình âm:** làm một số cặp mất nghiệm ngắn nhất hữu hạn và khiến Johnson chuẩn phải từ chối.

Không được viết điều kiện “nếu `dist<0` thì lỗi”, vì ví dụ chuẩn có khoảng cách -5 và -4 hợp lệ.

## 14. Những lỗi cài đặt thường gặp

1. **Chạy Dijkstra trực tiếp trên trọng số âm**, không có phép đổi trọng số đã chứng minh.
2. **Chạy Bellman–Ford chỉ từ một đỉnh gốc tùy ý**, khiến chu trình âm ở thành phần khác bị bỏ qua. Johnson cần siêu nguồn tới **mọi đỉnh**.
3. **Thêm các cạnh siêu nguồn vào graph chạy Dijkstra**, vô tình tạo reachability mới giữa các đỉnh gốc.
4. **Đổi sai dấu:** dùng `w-h[u]+h[v]` thay vì `w+h[u]-h[v]`.
5. **Khôi phục sai dấu:** dùng `d'+h[s]-h[t]` thay vì `d'-h[s]+h[t]`.
6. **Không kiểm tra chu trình âm** sau Bellman–Ford rồi tiếp tục chạy Dijkstra, dù h không thỏa điều kiện.
7. **Cho rằng Johnson có thể loại bỏ một chu trình âm** bằng đổi trọng số, trong khi tổng chu trình không đổi.
8. **Giả định mọi d' không âm đồng nghĩa mọi d gốc không âm**, rồi in trực tiếp dist' như kết quả.
9. **Không đánh dấu INF riêng** và cộng/trừ h vào sentinel, gây overflow hoặc tạo khoảng cách giả.
10. **Bỏ đỉnh cô lập** vì chỉ tạo danh sách kề cho đỉnh xuất hiện ở cạnh.
11. **Không giữ hướng cạnh**, vô ý thêm cung ngược.
12. **Thay đổi thứ tự cạnh hoặc gộp cạnh song song** khi bài cần khôi phục ID cạnh hoặc tất cả đường đi phân biệt.
13. **Dùng Dijkstra với min-heap nhưng không bỏ entry cũ**, làm tốn công, hoặc dùng sai tiêu chí cập nhật dẫn tới parent không nhất quán.
14. **Relax khi bằng nhau và luôn thay parent**, có thể tạo chuỗi predecessor khó truy vết trên chu trình trọng số 0.
15. **Quên xử lý đường source→source**, để parent[source]=-1 rồi coi là unreachable.
16. **Truy vết parent cho đỉnh không tới được**, đi vào chỉ số -1 hoặc vòng lặp.
17. **Đổi h theo từng nguồn mà không đồng bộ với graph'**, trong khi Johnson dùng một bộ h toàn cục.
18. **Không chứng minh mọi w'≥0**, nhất là khi tự viết heuristic potentials khác Bellman–Ford.
19. **Dùng `double` rồi làm tròn sai** trong một bài mà trọng số nguyên và kết quả cần chính xác.
20. **Dùng long tràn im lặng** trong Bellman–Ford, reweighting hoặc restoration.
21. **Gọi Johnson là O(VE) tổng cộng**, quên V lượt Dijkstra.
22. **Tuyên bố \(O(V^2\log V)\) trên mọi đồ thị**, trong khi đây là dạng đơn giản cho **graph thưa** với E=O(V).
23. **Không phân biệt chu trình âm với self-loop âm**, khiến V=1 cũng có thể lỗi mà bị bỏ qua.
24. **Dùng kết quả distance nhưng quên lưu predecessor** khi đặc tả yêu cầu xuất cả tuyến đường.
25. **Thử so sánh trọng số mới của đường có nguồn/đích khác nhau** rồi suy ra thứ tự như trên graph gốc, quên hằng số dịch khác nhau.
26. **Cho rằng record Java làm mảng bất biến**, trong khi các accessor trả mảng có thể sửa.
27. **Không dự trù O(V²) bộ nhớ của ma trận APSP**, ngay cả khi graph gốc rất thưa.

## 15. Quy trình giải một bài APSP bằng Johnson

1. Xác định **đồ thị có hướng hay vô hướng**, miền đỉnh, E, trọng số, cạnh trùng, self-loop và đỉnh cô lập.
2. Kiểm tra bài có cần **mọi cặp** hay chỉ một nguồn. Nếu chỉ một nguồn với cạnh âm, Bellman–Ford có thể đủ, không cần Johnson.
3. Xác định **điều kiện chu trình âm**: Johnson chỉ trả APSP hữu hạn khi không có bất kỳ chu trình âm nào.
4. Tạo siêu nguồn ảo có cạnh 0 tới mọi đỉnh hoặc **khởi tạo h[v]=0** rồi relax các cạnh gốc.
5. Chạy Bellman–Ford đúng số lượt và **kiểm tra relax thêm** để phát hiện chu trình âm.
6. Chỉ sau khi xác nhận hợp lệ, tính \(w'=w+h[u]-h[v]\) cho **từng cạnh đúng hướng**.
7. Kiểm tra mọi \(w'\ge0\) như một phép xác nhận bất biến.
8. Xây adjacency list cho G', không thêm q hoặc các cạnh giả nối đỉnh gốc.
9. Chạy Dijkstra từ mỗi s; dùng priority queue và điều kiện bỏ stale entry.
10. Nếu cần đường đi cụ thể, giữ `parent[s][t]` từ các lần relax.
11. Với mọi t tới được, phục hồi `d(s,t)=d'(s,t)-h[s]+h[t]`; với t không tới được, giữ INF.
12. Nếu cần đường đi, truy vết ngược parent từ target tới source rồi đảo; kiểm tra mọi cạnh có thật.
13. Kiểm tra không overflow; nếu dữ liệu quá lớn, sử dụng cách biểu diễn số phù hợp.
14. Với graph nhỏ, **đối chiếu Floyd–Warshall hoặc Bellman–Ford từng nguồn** làm oracle để kiểm chứng ma trận APSP.
15. Kiểm tra trường hợp cạnh âm không chu trình âm, đồ thị không liên thông, nhiều cạnh song song, self-loop 0/âm, nhiều đường hòa, graph rỗng.
16. Đo thời gian khi V/E lớn, chú ý E thưa/dày, số lượt Dijkstra và bộ nhớ V².

## 16. Bài tập tự kiểm tra

**Bài 1 — Công thức.** Một cạnh 2→3 có trọng số -5, thế năng h[2]=-5 và h[3]=0. Trọng số đổi là bao nhiêu?

*Đáp án:* \(w'=-5+(-5)-0=-10\) **không hợp lệ** với bộ thế năng ấy. Trong ví dụ chuẩn, cạnh có trọng số -5 là **3→2**, tức `h[3]=0`, `h[2]=-5`, nên \(w'= -5+0-(-5)=0\). Bài này nhấn mạnh **chiều cạnh và thứ tự h[u],h[v] quyết định dấu**; nếu một bộ h tạo cạnh âm, nó không phải thế năng Bellman–Ford hợp lệ cho graph chứa cạnh đó.

**Bài 2 — Đổi ngược.** Dijkstra trên graph mới cho `d'(0,2)=2`, h[0]=0, h[2]=-5. Khoảng cách gốc là gì?

*Đáp án:* \(2-h[0]+h[2]=2-0-5=\boxed{-3}\).

**Bài 3 — Đường đi.** Nếu dãy đỉnh 0→4→3→2 có trọng số gốc -4,+6,-5, tổng gốc là bao nhiêu?

*Đáp án:* **-3**. Sau đổi trọng số, các cạnh thành 0,+2,0 có tổng 2, tương ứng cộng h[0]-h[2]=5.

**Bài 4 — Siêu nguồn.** Vì sao Johnson thêm một siêu nguồn q với cạnh trọng số 0 tới mọi đỉnh?

*Đáp án:* Để mọi đỉnh đều **tới được từ q**, Bellman–Ford tính được h hữu hạn toàn graph và phát hiện **chu trình âm ở mọi thành phần**.

**Bài 5 — Không tạo q thật.** Nếu khởi tạo tất cả h[v]=0 rồi relax các cạnh gốc, điều đó tương ứng với thao tác nào của graph có q?

*Đáp án:* Tương ứng **relax sẵn toàn bộ cạnh ảo q→v trọng số 0** khi bắt đầu. Khi không có chu trình âm, tiếp tục tối đa V-1 lượt relax cạnh gốc là đủ.

**Bài 6 — Chu trình âm.** Nếu graph có vòng 0→1 trọng số 1, 1→2 trọng số -3, 2→0 trọng số 1, Johnson có trả ma trận hữu hạn không?

*Đáp án:* **Không**. Tổng chu trình \(1-3+1=-1\), âm; Bellman–Ford từ siêu nguồn phát hiện và thuật toán từ chối.

**Bài 7 — Cạnh âm.** Một graph có cạnh -4 nhưng không có chu trình âm có dùng Johnson được không?

*Đáp án:* **Có**. Cạnh âm là mục đích Johnson xử lý; chỉ **chu trình tổng âm** mới ngăn việc tính toàn bộ APSP hữu hạn theo phương pháp chuẩn.

**Bài 8 — Cạnh song song.** Với hai cạnh 0→1 có trọng số 5 và 2, cùng cạnh 1→2 trọng số -1, đường tốt nhất 0→2 có tổng bao nhiêu?

*Đáp án:* **1**, dùng cạnh 0→1 trọng số 2 và cạnh 1→2 trọng số -1.

**Bài 9 — INF.** Nếu t không tới được từ s trước reweighting, sau đổi trọng số và chạy Dijkstra có trở nên tới được không?

*Đáp án:* **Không**. Phép đổi chỉ thay số trên cạnh, không thêm cạnh mới giữa các đỉnh gốc; kết quả phải giữ **INF**.

**Bài 10 — Giữ đường tối ưu.** Vì sao hai đường P,Q cùng s,t không đổi thứ tự tổng trọng số sau reweighting?

*Đáp án:* Cả hai đều nhận đúng cùng hằng số \(h[s]-h[t]\); hiệu \(w(P)-w(Q)\) không đổi.

**Bài 11 — Chu trình.** Phép đổi trọng số có thay tổng trọng số của một chu trình không?

*Đáp án:* **Không.** Điểm đầu và cuối chu trình trùng nhau, thế năng triệt tiêu thành h[v]-h[v]=0.

**Bài 12 — Bộ nhớ.** Vì sao graph thưa nhưng trả ma trận APSP đầy đủ vẫn có thể tốn nhiều bộ nhớ?

*Đáp án:* Vì ma trận V×V có **V² ô**; nếu giữ parent cho mọi cặp, cần thêm một ma trận V×V nữa.

**Bài 13 — Chọn thuật toán.** Graph có trọng số không âm, chỉ cần đường ngắn nhất từ một nguồn; có bắt buộc chạy Johnson không?

*Đáp án:* **Không.** Dijkstra đơn nguồn là lựa chọn trực tiếp hơn. Johnson chủ yếu hữu ích cho **APSP** trên graph thưa có thể có cạnh âm.

**Bài 14 — Độ phức tạp.** Vì sao Johnson dùng heap nhị phân không chỉ mất O(VE)?

*Đáp án:* O(VE) là phần Bellman–Ford theo cận thông dụng; còn **V lượt Dijkstra**, mỗi lượt có chi phí khoảng O((V+E)log V).

**Bài 15 — Số học.** Nếu `h[u]+w` vượt miền `long`, có thể tin vào kết quả tràn của Java để tiếp tục không?

*Đáp án:* **Không.** Tràn có thể làm sai dấu và phá chứng minh. Mã dùng `Math.addExact` để báo lỗi; với miền quá lớn cần số học chính xác hơn.

**Bài 16 — Dijkstra và đường hòa.** Nếu có nhiều đường từ s tới t có cùng tổng trọng số tối ưu, Johnson có phải trả tất cả không?

*Đáp án:* **Không** nếu bài chỉ cần khoảng cách hoặc một đường. Reweighting giữ mọi đường hòa nhau; tiền nhiệm của một lượt Dijkstra thường lưu **một đường** tùy thứ tự relax/tie.

**Tổng kết:** Johnson giải **APSP trên đồ thị có hướng, có thể có cạnh âm nhưng không có chu trình âm**. Bellman–Ford từ siêu nguồn ảo tạo thế năng h thỏa \(h[v]\le h[u]+w(u,v)\). Nhờ đó phép đổi \(w'(u,v)=w(u,v)+h[u]-h[v]\) tạo các cạnh **không âm**, trong khi mọi đường s→t chỉ được cộng cùng hằng số \(h[s]-h[t]\), nên **không đổi đường ngắn nhất**. Chạy Dijkstra từ mọi nguồn trên graph mới, rồi khôi phục \(d(s,t)=d'(s,t)-h[s]+h[t]\), giữ INF cho đỉnh không tới được và từ chối graph có chu trình âm.
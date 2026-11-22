# Duyệt đồ thị song song và phối hợp trạng thái đã thăm

**Duyệt đồ thị song song** (*parallel graph traversal*) cho phép nhiều luồng xử lý các đỉnh/cạnh đồng thời, chẳng hạn để tìm các đỉnh có thể đi tới từ một nguồn hoặc tính khoảng cách ngắn nhất trên **đồ thị không trọng số**. Tuy nhiên, không thể chỉ biến vòng lặp BFS thành nhiều thread rồi hy vọng kết quả đúng: các worker có thể đồng thời khám phá **cùng một đỉnh**, cập nhật chung `visited`, tạo trùng công việc hoặc ghi đè thông tin `parent` và `distance`.

Trọng tâm của bài là **phối hợp trạng thái đã thăm** (*visited-state coordination*). Ta xây dựng một phiên bản **BFS song song đồng bộ theo tầng** (*level-synchronous parallel BFS*) bằng Java 17:

1. Duy trì `frontier` — các đỉnh **cùng khoảng cách** tới nguồn.
2. Phân chia các đỉnh frontier cho nhiều worker.
3. Dùng **compare-and-set (CAS)** trên một mảng khoảng cách nguyên tử để chỉ **một worker giành quyền khám phá mỗi đỉnh**.
4. Ghi đỉnh mới vào **danh sách riêng của worker**, tránh ghi đồng thời lên `ArrayList` chung.
5. Đợi **toàn bộ worker của tầng hiện tại hoàn tất** trước khi chuyển sang tầng tiếp theo.
6. Kiểm tra kết quả bằng **BFS tuần tự độc lập** và kiểm tính hợp lệ của quan hệ cha–con.

Thuật toán giữ nguyên **khoảng cách ngắn nhất** như BFS tuần tự, nhưng **cha của một đỉnh có thể khác nhau giữa các lần chạy** nếu có nhiều đường đi ngắn nhất. Đó là khác biệt hợp lệ do lịch chạy, không phải lỗi.

Ngoài BFS, bài phân tích cách song song hóa **DFS/duyệt đạt tới được**, điều kiện dừng của hàng đợi công việc, tính bất biến của đồ thị, tranh chấp nguyên tử, mất cân bằng tải, work/span và các tình huống có chu trình, self-loop, cạnh trùng, đỉnh cô lập. Không đồng nhất “chạy nhiều thread” với “chắc chắn nhanh hơn”, và không nhận một chương trình song song là đúng nếu chưa phân tích **tính nhất quán và đồng bộ**.

## 1. Mô hình đồ thị và phạm vi

Giả sử đồ thị:

\[
G=(V,E),\qquad |V|=n,\quad |E|=m.
\]

Các đỉnh được đánh số:

\[
0,1,\ldots,n-1.
\]

Trong mã Java, đồ thị là `int[][] graph`; `graph[u]` liệt kê những đỉnh v có **cạnh có hướng** \((u,v)\).

Ví dụ:

~~~text
graph[0] = [1, 2, 1]
graph[1] = [3, 4]
graph[2] = [4, 5]
...
~~~

Điều này cho phép **cạnh trùng** (0→1 xuất hiện hai lần) và **self-loop** (u→u). Mọi chỉ số đỉnh phải nằm trong \([0,n-1]\); các hàng adjacency không được null. Mã coi graph là **đồ thị có hướng**: cạnh u→v không tự tạo cạnh v→u.

Nếu bài toán là đồ thị **vô hướng**, cần lưu cả hai chiều cho mỗi cạnh, hoặc dùng biểu diễn phù hợp. Nếu cạnh có **trọng số**, BFS theo số cạnh **không bảo đảm đường đi có tổng trọng số nhỏ nhất**; khi ấy cần thuật toán tương ứng như Dijkstra, 0–1 BFS hoặc kỹ thuật song song khác theo giả thiết trọng số.

Bài xây BFS từ **một nguồn s**, với:

\[
0\le s<n,\quad n\ge1.
\]

Các đỉnh không thể đi tới từ s có khoảng cách \(-1\) và cha \(-1\).

## 2. Duyệt đồ thị tuần tự: baseline không thể bỏ qua

BFS (*breadth-first search*) tuần tự dùng một hàng đợi:

~~~text
distance[all] = -1
distance[source] = 0
queue.offer(source)

while queue not empty:
    u = queue.poll()
    for v in adjacency[u]:
        if distance[v] == -1:
            distance[v] = distance[u] + 1
            parent[v] = u
            queue.offer(v)
~~~

Nếu đồ thị có n đỉnh và m cạnh, BFS trên danh sách kề có thời gian:

\[
\boxed{O(n+m)}
\]

và bộ nhớ phụ O(n), không kể lưu đồ thị.

**Khoảng cách** `distance[v]` là số cạnh ít nhất trong một đường đi từ s tới v; \(-1\) nghĩa là không thể đi tới. Khi khám phá v lần đầu từ u, ta có `distance[v]=distance[u]+1`.

### Tại sao BFS đúng?

BFS xử lý đỉnh theo các **tầng khoảng cách tăng dần**:

- Tầng 0: nguồn s.
- Tầng 1: mọi đỉnh có đường đi ngắn nhất một cạnh từ s.
- Tầng 2: mọi đỉnh có đường đi ngắn nhất hai cạnh.
- Và tiếp tục.

Một đỉnh lần đầu được khám phá từ tầng d phải ở tầng d+1; nếu có đường đi ngắn hơn, nó đã được khám phá ở một tầng trước.

Chính cấu trúc **tầng** này cho phép thiết kế BFS song song mà vẫn đúng. Một cách xử lý song song **không tôn trọng tầng** không được tự nhận là BFS tính khoảng cách ngắn nhất.

## 3. Vì sao duyệt song song khó hơn duyệt tuần tự?

Trên CPU nhiều lõi, ta muốn các worker cùng xử lý nhiều đỉnh trong một frontier. Nhưng hai hoặc nhiều đỉnh khác nhau có thể có cạnh tới **cùng một đỉnh v**.

Ví dụ:

~~~text
    0
   / \
  1   2
   \ /
    3
~~~

Hai worker đồng thời xử lý 1 và 2 đều thấy cạnh tới 3. Nếu chúng dùng điều kiện thường:

~~~java
if (!visited[3]) {
    visited[3] = true;
    nextFrontier.add(3);
}
~~~

thì có thể xảy ra lịch:

~~~text
Worker A đọc visited[3] = false
Worker B đọc visited[3] = false
Worker A ghi visited[3] = true và enqueue 3
Worker B ghi visited[3] = true và enqueue 3
~~~

Đỉnh 3 bị enqueue **hai lần**. Nếu cả hai còn ghi `parent[3]`, kết quả cha có thể bị ghi đè; nếu không có đồng bộ, chương trình còn có thể chứa **data race** theo Java Memory Model.

Đây là lỗi **check-then-act không nguyên tử** (*non-atomic check-then-act*). Dùng `volatile` để thấy giá trị mới hơn **không biến cặp thao tác “đọc rồi ghi” thành một giao dịch nguyên tử**.

### Ba vấn đề cần giải đồng thời

1. **Quyền sở hữu khám phá:** chính xác một worker được “claim” v lần đầu.
2. **An toàn cấu trúc dữ liệu:** những worker đang thêm kết quả không làm hỏng danh sách/queue chung.
3. **Thứ tự giữa các tầng:** không xử lý tầng d+1 trước khi toàn bộ tầng d kết thúc nếu cần kết quả BFS ngắn nhất.

Một `ConcurrentLinkedQueue` chỉ giải quyết vấn đề đồng bộ thao tác queue, **không tự giải quyết** quyền sở hữu khám phá hay thứ tự tầng.

## 4. Trạng thái đã thăm nên biểu diễn thế nào?

Có nhiều phương án:

| Cách biểu diễn | Kiểu đồng bộ | Ưu điểm | Cảnh báo |
|---|---|---|---|
| `boolean[] visited` | Không có | Nhỏ, nhanh tuần tự | Không an toàn khi nhiều worker ghi/đọc không đồng bộ |
| `AtomicIntegerArray visited` | CAS từng ô | Có thể claim v duy nhất | Cần xác định rõ giá trị chưa/đã thăm |
| `AtomicIntegerArray distance` | CAS \(-1\to d+1\) | Vừa claim vừa đặt khoảng cách | Phải giữ ranh giới tầng |
| `ConcurrentHashMap.newKeySet()` | Thêm khóa thread-safe | Hữu ích cho ID rời rạc | Chi phí hash/boxing và bộ nhớ có thể lớn |
| `synchronized` quanh `visited` | Khóa chung | Dễ hiểu ban đầu | Khóa toàn cục có thể gây nghẽn |
| Bitset nguyên tử/bitmap phân đoạn | CAS trên word | Gọn cho đồ thị rất lớn | Cần xử lý contention và bit masks đúng |

Bài chọn một `AtomicIntegerArray distance` với quy ước:

\[
\boxed{distance[v]=-1\iff v\text{ chưa được khám phá}.}
\]

Với nguồn:

\[
distance[s]=0.
\]

Khi đang xử lý tầng d, mỗi worker thử:

~~~java
if (distance.compareAndSet(v, -1, d + 1)) {
    // Chỉ worker thành công mới được thêm v vào frontier kế tiếp.
}
~~~

**CAS** là phép so sánh và cập nhật **nguyên tử**: nếu ô distance[v] vẫn bằng -1 thì đổi nó thành d+1 và trả `true`; nếu đã khác -1 thì không ghi và trả `false`.

Vì chỉ một thao tác CAS có thể chuyển một ô \(-1\) sang giá trị không âm, **mỗi đỉnh chỉ có một worker claim thành công**.

## 5. CAS thành công và CAS thất bại

Xét cạnh đến đỉnh 3 ở ví dụ trước. Worker A và B cạnh tranh để claim:

~~~text
distance[3] = -1

Worker A: CAS(3, -1, 2) -> true
Worker B: CAS(3, -1, 2) -> false
~~~

Hoặc B thắng và A thua. Dù thứ tự nào:

\[
\boxed{distance[3]=2}
\]

và **chỉ một worker** được thêm đỉnh 3 vào frontier kế tiếp.

### Điều không được làm

Không dùng:

~~~java
if (distance.get(v) == -1) {
    distance.set(v, depth + 1);
    localNext.add(v);
}
~~~

Cặp `get` / `set` là **hai thao tác riêng**; giữa chúng worker khác có thể ghi. Hai thao tác riêng lẻ đều nguyên tử không có nghĩa **cả kiểm tra–cập nhật** được thực hiện nguyên tử.

### Claim trước, ghi parent sau

Sau CAS thành công, worker có quyền ghi:

~~~java
parent.set(v, u);
localNext.add(v);
~~~

Chỉ worker thắng CAS được ghi `parent[v]`, nên không có hai worker cùng ghi cha của một đỉnh đã được khám phá lần đầu.

Trong chương trình, `parent` cũng là `AtomicIntegerArray` để đơn giản hóa việc công bố trạng thái. **Tất cả worker của tầng phải hoàn tất** trước khi các worker tầng sau hoặc người gọi sử dụng `parent`. Nhờ hàng rào đồng bộ (Future.get), không có tình huống đọc một `distance[v]` đã claim nhưng `parent[v]` chưa được công bố trong thuật toán được mô tả.

## 6. Phân chia công việc bằng frontier

**Frontier** ở tầng d là tập các đỉnh đang chờ mở rộng và đã có:

\[
distance[u]=d.
\]

Trong bản Java, frontier được giữ trong một `List<Integer>` chỉ do thread điều phối tạo và **không thay đổi khi các worker đang dùng**.

Nếu có P worker và frontier chứa F đỉnh, số task của tầng được chọn:

\[
\boxed{T=\min(P,F).}
\]

Worker với chỉ số lane \(t\in[0,T-1]\) xử lý các vị trí:

\[
t,\ t+T,\ t+2T,\ldots
\]

trong frontier.

Ví dụ:

~~~text
frontier = [10, 11, 12, 13, 14, 15, 16]
T = 3

worker 0: [10, 13, 16]
worker 1: [11, 14]
worker 2: [12, 15]
~~~

Cách chia vòng tròn này đơn giản, không cần khóa để lấy một đỉnh frontier. Nhưng nó **chưa cân bằng số cạnh**: một đỉnh có hàng triệu hàng xóm vẫn có thể khiến một worker bận hơn hẳn các worker khác.

### Danh sách next frontier riêng từng task

Mỗi worker tạo:

~~~java
List<Integer> localNext = new ArrayList<>();
~~~

Chỉ task đó được ghi vào `localNext`. Khi CAS claim thành công một đỉnh v, task thêm v vào danh sách của mình.

Đây là cách giảm tranh chấp trên cấu trúc tập hợp chung. **Không** có nhiều worker cùng gọi `add` trên một `ArrayList` không được bảo vệ.

Sau khi toàn bộ task hoàn thành, thread điều phối ghép các danh sách riêng thành frontier kế tiếp.

## 7. Hàng rào đồng bộ giữa các tầng là thiết yếu

Một quy tắc **không thể bỏ qua**:

> Không bắt đầu mở rộng các đỉnh ở tầng d+1 cho đến khi **mọi cạnh từ toàn bộ frontier tầng d** đã được xét.

Trong Java:

~~~java
List<Future<List<Integer>>> futures =
    pool.invokeAll(tasks);

for (Future<List<Integer>> future : futures) {
    nextFrontier.addAll(future.get());
}
~~~

`invokeAll` đợi các task trong danh sách hoàn tất; `Future.get()` trả kết quả hoặc ném `ExecutionException` nếu task lỗi. Theo quy tắc đồng bộ của Future, kết quả công việc của task đã hoàn tất **có quan hệ happens-before** với hành động đọc kết quả sau `get`.

Vì vậy chỉ sau khi ghép xong mới:

~~~text
frontier = nextFrontier
depth++
~~~

### Nếu bỏ barrier, BFS có thể cho khoảng cách sai

Xét đồ thị có hai đường đi từ 0 tới 4:

~~~text
Đường ngắn: 0 -> 2 -> 4             (2 cạnh)
Đường dài: 0 -> 1 -> 3 -> 4        (3 cạnh)
~~~

Nếu worker mở rộng đường dài quá nhanh trong một hàng đợi tự do và claim 4 trước, distance[4] có thể bị ghi là 3. Khi worker xử lý đường ngắn đến 4, CAS \(-1\to2\) thất bại vì đỉnh đã visited. Kết quả **không còn là khoảng cách ngắn nhất**.

Dùng CAS **một mình** chỉ giải quyết **khám phá trùng**, không bảo đảm **độ dài đường đi ngắn nhất** trong một lịch xử lý bất kỳ.

Giữ barrier giữa các tầng bảo đảm mọi đường đi có d cạnh được xử lý **trước** đường đi có d+1 cạnh. Nhờ đó lần claim đầu luôn có khoảng cách tối ưu.

## 8. Bất biến của BFS song song đồng bộ theo tầng

Gọi \(\mathcal{F}_d\) là frontier tại đầu vòng lặp tầng d.

Ta duy trì:

1. **Tính đúng khoảng cách trước tầng d:** mọi đỉnh đã claim có khoảng cách ngắn nhất không vượt d; tất cả đỉnh trong \(\mathcal{F}_d\) có distance=d.
2. **Tính duy nhất:** không đỉnh nào được đưa vào frontier kế tiếp nhiều hơn một lần, vì CAS claim chỉ thành công một lần.
3. **Không bỏ sót cạnh:** mỗi u trong frontier được một task xử lý, mỗi cạnh đi ra khỏi u được xét một lần ở tầng hiện tại.
4. **Barrier:** toàn bộ cạnh của \(\mathcal{F}_d\) đã xét xong trước khi bắt đầu \(\mathcal{F}_{d+1}\).

### Cơ sở

Ban đầu chỉ nguồn s đã claim:

\[
\mathcal{F}_0=\{s\},\quad distance[s]=0.
\]

Khoảng cách 0 là tối ưu và mọi đỉnh còn lại có distance=-1.

### Bước quy nạp

Giả sử các bất biến đúng đầu tầng d. Với mỗi cạnh \((u,v)\) từ u ở tầng d, nếu v chưa được claim và CAS thành công, ta đặt:

\[
distance[v]=d+1.
\]

Có đường đi dài d+1 từ nguồn qua u tới v, nên khoảng cách ngắn nhất của v **không lớn hơn d+1**.

Nếu v có đường đi ngắn hơn d+1, nó đã phải được khám phá tại một tầng trước (theo giả thiết quy nạp và barrier), trái việc CAS từ -1 thành công. Vì vậy khoảng cách ngắn nhất của v **chính xác là d+1**.

CAS bảo đảm không có hai task cùng claim thành công v. Mỗi cạnh từ frontier được duyệt, nên mọi đỉnh có đường đi ngắn nhất d+1 mà chưa claim sẽ được phát hiện.

Sau khi toàn bộ task hoàn thành, danh sách kế tiếp chứa đúng các đỉnh được khám phá ở tầng d+1. Các bất biến được bảo toàn.

### Kết luận

Khi frontier rỗng, không còn đỉnh mới nào có thể đi tới từ s. Mọi đỉnh reachable đã có khoảng cách ngắn nhất và mọi đỉnh unreachable vẫn là -1.

\[
\boxed{\text{Parallel BFS distance}=
\text{Sequential BFS distance}.}
\]

Chứng minh không yêu cầu **thứ tự worker cố định**, nhưng yêu cầu graph **không bị sửa đồng thời**, CAS đúng, mỗi frontier được xử lý đầy đủ và barrier theo tầng.

## 9. Cây cha không nhất thiết xác định

Trong BFS, `parent[v]` là một đỉnh u thỏa:

\[
(u,v)\in E,\qquad distance[u]+1=distance[v].
\]

Nếu có nhiều đường đi ngắn nhất tới v, nhiều u thỏa điều kiện. Worker thắng CAS quyết định `parent[v]`.

Ví dụ:

~~~text
0 -> 1 -> 3
 \-> 2 -> 3
~~~

Cả đường 0→1→3 và 0→2→3 đều dài hai cạnh. Vì vậy:

~~~text
parent[3] = 1
~~~

hoặc:

~~~text
parent[3] = 2
~~~

đều **đúng**. Một chương trình unit test mà cố bắt `parent[3]` luôn bằng 1 sẽ bị lỗi giả do nondeterminism.

### Cái gì cần xác minh?

Thay vì so toàn bộ mảng parent với BFS tuần tự, nên kiểm:

- `distance` **khớp chính xác** với BFS tuần tự.
- `parent[source]=source`.
- Mọi đỉnh unreachable có `parent=-1`.
- Với mọi đỉnh visited khác source, `parent[v]` là **đỉnh hợp lệ**.
- Có cạnh \((parent[v],v)\).
- `distance[parent[v]]+1=distance[v]`.

Những điều kiện này đủ bảo đảm đi ngược theo parent tạo một đường đi ngắn nhất tới nguồn và không có chu trình cha, vì distance giảm một đơn vị mỗi bước.

### Muốn kết quả parent có tính quyết định?

Có thể áp đặt quy tắc chọn parent nhỏ nhất hoặc thứ tự duyệt cạnh cố định, nhưng phải thiết kế thêm cách **phá hòa an toàn**. Ví dụ, sau khi biết distance, có thể duyệt cạnh để lấy cha nhỏ nhất trong các đỉnh ở tầng d−1 hoặc dùng phép giảm nguyên tử `min` thích hợp. Đây là thêm công việc và có thể đổi thứ tự/tính năng của thuật toán; **không phải mặc định** của bản CAS claim-first.

## 10. Ví dụ có cạnh trùng, nhiều cha và đỉnh unreachable

Dùng đồ thị có hướng mười đỉnh:

~~~text
0 -> [1, 2, 1]       (cạnh 0->1 lặp)
1 -> [3, 4]
2 -> [4, 5]
3 -> [6]
4 -> [6, 7]
5 -> [7]
6 -> [8]
7 -> [8]
8 -> []
9 -> []              (đỉnh 9 không thể tới từ 0)
~~~

Từ nguồn s=0, các tầng là:

| Tầng | Các đỉnh |
|---:|---|
| 0 | {0} |
| 1 | {1,2} |
| 2 | {3,4,5} |
| 3 | {6,7} |
| 4 | {8} |
| Không reachable | {9} |

Khoảng cách:

~~~text
[0, 1, 1, 2, 2, 2, 3, 3, 4, -1]
~~~

Đỉnh 4 có thể do worker xử lý 1 hoặc 2 claim trước. Đỉnh 6 có thể nhận cha 3 hoặc 4; đỉnh 7 có thể nhận cha 4 hoặc 5; đỉnh 8 có thể nhận cha 6 hoặc 7. Dù vậy mọi đường cha hợp lệ tới 8 đều chứa **4 cạnh**.

Cạnh 0→1 xuất hiện hai lần nhưng không khiến 1 xuất hiện hai lần trong frontier. Sau CAS thành công đầu tiên, những CAS còn lại đều thấy distance[1] khác -1.

Mã Java in **mảng distance và độ dài đường cha**, không in một danh sách parent cụ thể để tránh hứa một lịch thread mà ExecutorService không bảo đảm.

## 11. Các bước triển khai có kiểm soát

**Bước 1 — kiểm input.** Graph phải có ít nhất một đỉnh; source nằm trong [0,n−1]; mỗi adjacency row khác null và mọi neighbor ID hợp lệ; worker count dương. Graph không được thay đổi trong khi BFS đang chạy.

**Bước 2 — khởi tạo trạng thái nguyên tử.**

~~~text
distance[*] = -1
parent[*] = -1
distance[source] = 0
parent[source] = source
frontier = [source]
depth = 0
~~~

**Bước 3 — lập thread pool.** Sử dụng `Executors.newFixedThreadPool` với tối đa số worker được yêu cầu (bản demo chặn bởi n).

**Bước 4 — tạo task cho frontier.** Nếu frontier có F đỉnh, tạo \(T=\min(P,F)\) callable; phân chia các vị trí vòng tròn để tránh hai task nhận cùng một vị trí frontier.

**Bước 5 — xử lý cạnh song song.** Trong mỗi task, với mọi cạnh u→v:

~~~text
if CAS(distance[v], -1, depth+1) succeeds:
    parent[v] = u
    localNext.add(v)
~~~

**Bước 6 — barrier và ghép.** Chờ mọi Future; nếu task lỗi, truyền lỗi ra cho caller thay vì âm thầm bỏ; ghép local lists bằng thread điều phối.

**Bước 7 — tăng depth.** Thay frontier bằng next, tăng depth và lặp đến khi frontier rỗng.

**Bước 8 — công bố kết quả.** Đọc các giá trị `distance` và `parent` sau barrier cuối vào `int[]` để trả ra. Các mảng kết quả này là bản chụp, không phải tham chiếu đến các cấu trúc còn đang thay đổi bởi worker.

**Bước 9 — đóng pool.** `finally` gọi `shutdownNow()` để cố dừng/cắt bỏ tác vụ còn chạy nếu thao tác thất bại. Sau luồng bình thường, mọi task đã kết thúc trước đó. Nếu có interrupt/error, hàm **không** trả một kết quả BFS dở dang như thể hoàn chỉnh.

## 12. Java 17+: chương trình BFS song song hoàn chỉnh

Lưu nguyên chương trình dưới tên **ParallelGraphTraversalDemo.java**. Nó chỉ dùng Java Standard Library và không cần framework song song bên ngoài.

Chương trình có:

- `sequentialBfs`: oracle tuần tự lấy distance chính xác.
- `parallelBfs`: BFS song song dùng `AtomicIntegerArray.compareAndSet`, frontier theo tầng, task-local list và `ExecutorService.invokeAll`.
- `BfsResult`: mảng `distance` và `parent`.
- `pathTo`: truy ngược theo parent để dựng **một** đường đi ngắn nhất.
- `checkResult`: đối chiếu distance với oracle, kiểm parent thực sự trỏ theo cạnh và độ dài tăng một.
- Kiểm **toàn bộ 512 đồ thị có hướng ba đỉnh** (bao gồm self-loop), nguồn 0.
- Kiểm **180 đồ thị ngẫu nhiên có seed 527**, mỗi đồ thị với 1, 2 và 4 worker; cho phép cạnh trùng, chu trình và nhiều đỉnh unreachable.
- Output tất định: không phụ thuộc vào worker nào thắng CAS ở các đỉnh có nhiều cha.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Random;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicIntegerArray;

public class ParallelGraphTraversalDemo {

    record BfsResult(int[] distance, int[] parent) {}

    static void validateGraph(int[][] graph, int source, int workers) {
        if (graph == null || graph.length == 0) {
            throw new IllegalArgumentException(
                "graph must contain at least one vertex"
            );
        }
        if (workers < 1) {
            throw new IllegalArgumentException(
                "workers must be >= 1"
            );
        }
        int n = graph.length;
        if (source < 0 || source >= n) {
            throw new IllegalArgumentException(
                "source index out of range"
            );
        }
        for (int u = 0; u < n; u++) {
            if (graph[u] == null) {
                throw new IllegalArgumentException(
                    "null adjacency row at " + u
                );
            }
            for (int v : graph[u]) {
                if (v < 0 || v >= n) {
                    throw new IllegalArgumentException(
                        "neighbor index out of bounds"
                    );
                }
            }
        }
    }

    // Independent sequential reference for unweighted graphs.
    static int[] sequentialBfs(int[][] graph, int source) {
        validateGraph(graph, source, 1);
        int n = graph.length;
        int[] distance = new int[n];
        Arrays.fill(distance, -1);

        int[] queue = new int[n];
        int head = 0;
        int tail = 0;

        distance[source] = 0;
        queue[tail++] = source;

        while (head < tail) {
            int u = queue[head++];
            for (int v : graph[u]) {
                if (distance[v] == -1) {
                    distance[v] = distance[u] + 1;
                    queue[tail++] = v;
                }
            }
        }
        return distance;
    }

    // Level-synchronous BFS. Atomic CAS claims each vertex once.
    static BfsResult parallelBfs(
        int[][] graph, int source, int workers
    ) throws InterruptedException, ExecutionException {

        validateGraph(graph, source, workers);
        int n = graph.length;

        AtomicIntegerArray distance = new AtomicIntegerArray(n);
        AtomicIntegerArray parent = new AtomicIntegerArray(n);
        for (int i = 0; i < n; i++) {
            distance.set(i, -1);
            parent.set(i, -1);
        }

        distance.set(source, 0);
        parent.set(source, source);

        int poolSize = Math.min(workers, n);
        ExecutorService pool =
            Executors.newFixedThreadPool(poolSize);

        try {
            List<Integer> frontier = new ArrayList<>();
            frontier.add(source);
            int depth = 0;

            while (!frontier.isEmpty()) {
                // This list is never modified while workers use it.
                final List<Integer> current = frontier;
                final int taskCount =
                    Math.min(poolSize, current.size());
                final int nextDepth = depth + 1;

                List<Callable<List<Integer>>> tasks =
                    new ArrayList<>(taskCount);

                for (int lane = 0; lane < taskCount; lane++) {
                    final int taskLane = lane;

                    tasks.add(() -> {
                        // Only this task writes to its localNext.
                        List<Integer> localNext = new ArrayList<>();

                        for (int i = taskLane;
                                i < current.size();
                                i += taskCount) {
                            int u = current.get(i);

                            for (int v : graph[u]) {
                                // Compare-and-set is ONE atomic
                                // check+write; no get-then-set race.
                                if (distance.compareAndSet(
                                        v, -1, nextDepth)) {
                                    parent.set(v, u);
                                    localNext.add(v);
                                }
                            }
                        }
                        return localNext;
                    });
                }

                // Barrier: all tasks of depth finish before next.
                List<Future<List<Integer>>> done =
                    pool.invokeAll(tasks);

                // Only coordinator writes the combined frontier.
                List<Integer> nextFrontier = new ArrayList<>();
                for (Future<List<Integer>> future : done) {
                    nextFrontier.addAll(future.get());
                }

                frontier = nextFrontier;
                depth++;
            }
        } finally {
            // In a successful run, all tasks are already finished.
            // In an interrupted/error run, no partial BFS is returned.
            pool.shutdownNow();
        }

        int[] finalDistance = new int[n];
        int[] finalParent = new int[n];
        for (int i = 0; i < n; i++) {
            finalDistance[i] = distance.get(i);
            finalParent[i] = parent.get(i);
        }

        return new BfsResult(finalDistance, finalParent);
    }

    // Reconstruct ONE valid shortest path; parent tie is not
    // deterministic if multiple shortest paths exist.
    static List<Integer> pathTo(BfsResult result, int target) {
        int[] distance = result.distance();
        int[] parent = result.parent();

        if (target < 0 || target >= distance.length) {
            throw new IllegalArgumentException(
                "target index out of range"
            );
        }
        if (distance[target] == -1) {
            return List.of();
        }

        List<Integer> reverse = new ArrayList<>();
        int v = target;

        for (int steps = 0; steps < parent.length; steps++) {
            reverse.add(v);
            if (parent[v] == v) {
                Collections.reverse(reverse);
                return reverse;
            }
            v = parent[v];
            if (v < 0 || v >= parent.length) {
                throw new AssertionError("invalid parent chain");
            }
        }
        throw new AssertionError("parent cycle detected");
    }

    // Check full distances AND validate each chosen parent edge.
    static void checkResult(
        int[][] graph, int source,
        BfsResult result, int[] expected
    ) {
        if (!Arrays.equals(result.distance(), expected)) {
            throw new AssertionError(
                "distance differs: expected="
                + Arrays.toString(expected)
                + ", actual="
                + Arrays.toString(result.distance())
            );
        }

        int[] distance = result.distance();
        int[] parent = result.parent();

        if (parent.length != graph.length
                || parent[source] != source
                || distance[source] != 0) {
            throw new AssertionError(
                "source/parent length invariant failed"
            );
        }

        for (int v = 0; v < graph.length; v++) {
            if (v == source) {
                continue;
            }
            if (distance[v] == -1) {
                if (parent[v] != -1) {
                    throw new AssertionError(
                        "unreachable vertex has parent"
                    );
                }
                continue;
            }

            int p = parent[v];
            if (p < 0 || p >= graph.length
                    || distance[p] != distance[v] - 1) {
                throw new AssertionError(
                    "parent not in preceding layer"
                );
            }

            boolean foundEdge = false;
            for (int neighbor : graph[p]) {
                if (neighbor == v) {
                    foundEdge = true;
                    break;
                }
            }
            if (!foundEdge) {
                throw new AssertionError(
                    "parent edge missing from graph"
                );
            }
            List<Integer> path = pathTo(result, v);
            if (path.size() - 1 != distance[v]
                    || path.get(0) != source
                    || path.get(path.size() - 1) != v) {
                throw new AssertionError(
                    "reconstructed shortest path invalid"
                );
            }
        }
    }

    // Every simple directed graph on 3 vertices:
    // 3*3 = 9 possible ordered edges, including self-loops.
    static void exhaustiveTinyGraphs()
            throws InterruptedException, ExecutionException {

        int checked = 0;
        for (int mask = 0; mask < (1 << 9); mask++) {
            int[][] graph = new int[3][];

            for (int u = 0; u < 3; u++) {
                int degree = 0;
                for (int v = 0; v < 3; v++) {
                    if ((mask & (1 << (u * 3 + v))) != 0) {
                        degree++;
                    }
                }

                graph[u] = new int[degree];
                int out = 0;
                for (int v = 0; v < 3; v++) {
                    if ((mask & (1 << (u * 3 + v))) != 0) {
                        graph[u][out++] = v;
                    }
                }
            }

            int[] oracle = sequentialBfs(graph, 0);
            BfsResult result = parallelBfs(graph, 0, 2);
            checkResult(graph, 0, result, oracle);
            checked++;
        }
        System.out.println(
            "Exhaustive tiny digraphs: PASS ("
            + checked + " graphs)"
        );
    }

    // Cycles, duplicates, self-loops, different sources and
    // disconnected vertices are allowed by this generator.
    static void randomGraphs()
            throws InterruptedException, ExecutionException {

        Random random = new Random(527L);
        int cases = 180;
        int[] workerCounts = {1, 2, 4};

        for (int test = 0; test < cases; test++) {
            int n = 1 + random.nextInt(35);
            int[][] graph = new int[n][];

            for (int u = 0; u < n; u++) {
                int degree = random.nextInt(n + 1);
                graph[u] = new int[degree];

                for (int i = 0; i < degree; i++) {
                    graph[u][i] = random.nextInt(n);
                }
            }

            int source = random.nextInt(n);
            int[] oracle = sequentialBfs(graph, source);

            for (int workers : workerCounts) {
                BfsResult result =
                    parallelBfs(graph, source, workers);
                checkResult(graph, source, result, oracle);
            }
        }
        System.out.println(
            "Random directed multigraphs: PASS ("
            + cases + " graphs x "
            + workerCounts.length + " worker counts)"
        );
    }

    public static void main(String[] args) throws Exception {
        int[][] graph = {
            {1, 2, 1}, // 0: duplicate edge to 1
            {3, 4},    // 1
            {4, 5},    // 2
            {6},       // 3
            {6, 7},    // 4
            {7},       // 5
            {8},       // 6
            {8},       // 7
            {},        // 8
            {}         // 9: unreachable from 0
        };

        int[] oracle = sequentialBfs(graph, 0);
        BfsResult parallel = parallelBfs(graph, 0, 4);
        checkResult(graph, 0, parallel, oracle);

        System.out.println(
            "Sequential distances: "
            + Arrays.toString(oracle)
        );
        System.out.println(
            "Parallel distances:   "
            + Arrays.toString(parallel.distance())
        );
        System.out.println(
            "Equal distances: "
            + Arrays.equals(oracle, parallel.distance())
        );
        System.out.println(
            "Path length to vertex 8: "
            + (pathTo(parallel, 8).size() - 1)
        );
        System.out.println(
            "Unreachable vertex 9: " + parallel.distance()[9]
        );

        int[][] selfLoop = {{0, 0}};
        BfsResult single = parallelBfs(selfLoop, 0, 2);
        System.out.println(
            "Self-loop graph: "
            + Arrays.toString(single.distance())
        );

        try {
            parallelBfs(graph, 0, 0);
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Invalid worker count rejected: " + e.getMessage()
            );
        }

        try {
            parallelBfs(new int[0][], 0, 2);
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Empty graph rejected: " + e.getMessage()
            );
        }

        exhaustiveTinyGraphs();
        randomGraphs();
    }
}
~~~

Biên dịch và chạy trên **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 ParallelGraphTraversalDemo.java
java ParallelGraphTraversalDemo
~~~

**Stdout dự kiến chính xác** (không phụ thuộc thứ tự thắng CAS):

~~~text
Sequential distances: [0, 1, 1, 2, 2, 2, 3, 3, 4, -1]
Parallel distances:   [0, 1, 1, 2, 2, 2, 3, 3, 4, -1]
Equal distances: true
Path length to vertex 8: 4
Unreachable vertex 9: -1
Self-loop graph: [0]
Invalid worker count rejected: workers must be >= 1
Empty graph rejected: graph must contain at least one vertex
Exhaustive tiny digraphs: PASS (512 graphs)
Random directed multigraphs: PASS (180 graphs x 3 worker counts)
~~~

Trong `main`, parent của các đỉnh như 4, 6, 7, 8 có thể thay đổi giữa các lần chạy. Tuy nhiên, `pathTo(parallel,8)` luôn đi qua **bốn cạnh** và kết thúc ở đỉnh 8. Đó là lý do stdout chỉ in **độ dài đường đi**, không in cha cụ thể.

## 13. Kiểm chứng bao phủ những trường hợp nào?

### A. Toàn bộ đồ thị có hướng nhỏ n=3

Với ba đỉnh, có:

\[
3\cdot3=9
\]

cặp đỉnh có thứ tự \((u,v)\) có thể tạo cạnh, gồm cả ba self-loop. Mỗi cặp có hai khả năng (có/không cạnh), nên số đồ thị đơn có hướng là:

\[
\boxed{2^9=512.}
\]

Mã duyệt toàn bộ 512 mask, dựng danh sách kề, chạy BFS từ nguồn 0 bằng:

- BFS tuần tự dùng hàng đợi.
- BFS song song dùng hai worker và CAS theo tầng.

Mỗi trường hợp được so chính xác mảng distance và kiểm đường cha. Không có cạnh trùng trong phần **exhaustive** này vì mỗi cặp \((u,v)\) chỉ bật hoặc tắt; cạnh trùng được thử ở ví dụ và phần ngẫu nhiên.

### B. Đồ thị ngẫu nhiên có hướng và cạnh trùng

Với hạt giống `527L`, Java `Random` sinh 180 đồ thị:

- Số đỉnh trong [1,35].
- Mỗi đỉnh có một số cạnh từ 0 đến n, điểm cuối có thể lặp.
- Source ngẫu nhiên trong các đỉnh hợp lệ.
- Cho phép tự vòng, chu trình và các thành phần không tới được.
- Chạy cùng graph với số worker **1, 2, 4**.

Tổng số lượt so BFS song song trong phần này:

\[
\boxed{180\cdot3=540.}
\]

Thứ tự scheduler không được cố định, nên chạy nhiều lần có thể tạo parent khác nhau. Nhưng **distance và các bất biến parent** phải luôn đúng.

### C. Kiểm thử lịch claim giả lập

Ngoài các test Java thực thi theo scheduler của hệ điều hành, khi đánh giá độc lập ý tưởng thuật toán có thể mô phỏng **nhiều lịch interleaving** cho các worker tại cùng tầng:

- Worker có chỉ số thấp xử lý cạnh trước.
- Worker có chỉ số cao xử lý cạnh trước.
- Worker lần lượt xử lý từng cạnh theo thứ tự trộn khác nhau.

Bất biến CAS và barrier bảo đảm kết quả **distance giống nhau**, còn parent có thể khác nhau. Kiểm thử giả lập giúp phát hiện lệ thuộc thứ tự xử lý, nhưng **không thay thế** kiểm thử thực thi đa luồng, phân tích Java Memory Model và công cụ phát hiện race.

### D. Những điều kiện đúng cần đo

Một test tốt phải kiểm:

1. Mọi distance đồng nhất với BFS tuần tự.
2. Mọi parent visited trỏ tới đỉnh có cạnh đến v.
3. Distance của parent bằng distance[v]−1.
4. Source có distance=0 và parent=source.
5. Unreachable có distance=−1 và parent=−1.
6. Reconstructed path có đúng distance[v] cạnh.
7. Cạnh trùng, self-loop không làm khám phá đỉnh hai lần.
8. Không có lỗi worker bị im lặng bỏ qua.

Không nên chỉ kiểm một ví dụ in đúng rồi kết luận chương trình an toàn đồng thời.

## 14. Phân tích thời gian theo work và span

Trong thuật toán tuần tự, BFS làm tối đa O(n+m) công việc.

Với BFS song song, có ít nhất hai thước đo:

**Work (tổng công việc):** tổng các phép xử lý của mọi worker và thread điều phối.

**Span/critical path (đường thực thi dài nhất):** thời gian tối thiểu cần dù có nhiều bộ xử lý, do phụ thuộc giữa các tầng và các thao tác bắt buộc tuần tự.

### Tổng công việc

Mỗi đỉnh reachable xuất hiện trong đúng một frontier vì CAS claim tối đa một lần. Mỗi cạnh đi ra từ đỉnh reachable được xét một lần ở tầng tương ứng. Việc validate graph duyệt n+m; snapshot kết quả duyệt n.

Do đó phần duyệt có tổng công việc:

\[
O(n+m)
\]

**chưa tính overhead điều phối task**.

Nếu P là số worker tối đa và L là số tầng khác rỗng, mỗi tầng tạo tối đa P task, nên phần tạo task/barrier có thể thêm:

\[
O(PL).
\]

Đối với bản triển khai đơn giản:

\[
\boxed{W_{\text{total}}=O(n+m+PL)}
\]

theo mô hình thao tác bảng kề/CAS hằng số, cộng các chi phí cấp phát và quản lý thread thực tế.

### Không được chia máy móc cho P

Một công thức sơ bộ thường được mong đợi là:

\[
T_P\approx\frac{n+m}{P}+\text{overhead}.
\]

Nhưng **đây không phải bảo đảm thời gian** của bản Java:

- Một tầng chỉ có một đỉnh thì \(\min(P,1)=1\) task.
- Các đỉnh có bậc rất khác nhau gây **mất cân bằng tải**.
- Các CAS trên đỉnh nóng gây tranh chấp cache.
- Barrier phải chờ worker **chậm nhất** của tầng.
- Thread điều phối ghép các danh sách local thành frontier mới, cộng dồn O(n) thao tác tuần tự trên toàn BFS.
- Thread pool, Future, boxing `Integer`, cấp phát danh sách và memory bandwidth đều tốn chi phí.

Do đó tăng số worker có thể khiến **chậm hơn** BFS tuần tự trên đồ thị nhỏ hoặc frontier hẹp. Cần đo hiệu năng thực tế, không chỉ suy ra tốc độ từ số lõi.

### Đường kính và số tầng

Đặt D là khoảng cách lớn nhất từ nguồn tới một đỉnh reachable. Số tầng có đỉnh là:

\[
L=D+1.
\]

Một đồ thị dạng đường đi dài có frontier hầu hết chỉ một đỉnh, nên L≈n và không có nhiều công việc độc lập theo đỉnh mỗi tầng. Một đồ thị rộng, có frontier lớn ở vài tầng, có thể khai thác song song tốt hơn nếu phân phối đều các cạnh.

## 15. Tối ưu chia việc theo đỉnh và theo cạnh

Bản Java phân chia **đỉnh frontier** theo lane:

~~~text
worker 0: u0, uP, u2P, ...
worker 1: u1, u(P+1), ...
~~~

Tốt khi bậc các đỉnh tương đối đồng đều.

Tuy nhiên nếu một đỉnh có một triệu cạnh và mọi đỉnh khác chỉ có hai cạnh, task sở hữu đỉnh lớn trở thành nút thắt. Các hướng tối ưu gồm:

- **Chia theo cạnh:** chia danh sách hàng xóm của đỉnh bậc lớn thành nhiều khối; mỗi worker xử lý một khối, cùng dùng CAS vào distance[v].
- **Dynamic scheduling:** chia frontier thành nhiều task nhỏ và cho worker lấy task khi rảnh.
- **Work stealing:** worker lấy công việc còn dư từ worker khác.
- **Compact CSR:** thay nhiều mảng/đối tượng nhỏ bằng hai mảng `offsets` và `neighbors` liên tục để cải thiện locality.
- **Thay boxing:** dùng mảng `int[]` hoặc bộ đệm primitive thay `List<Integer>` nếu muốn giảm phân bổ đối tượng.
- **Tối ưu theo hướng BFS:** khi frontier quá lớn, cân nhắc bottom-up BFS dùng thông tin hàng xóm chiều ngược lại để tìm một neighbor đã có trong frontier, nhưng phải có đồ thị phù hợp và phân tích đúng.

Những cải tiến này thường cần code và bằng chứng riêng. Bản học giữ mô hình **đơn giản, chính xác và dễ kiểm chứng**, không giả sử nó là triển khai BFS song song nhanh nhất.

## 16. Kích thước bộ nhớ

Mã Java lưu:

- Graph dạng adjacency `int[][]`: O(n+m) số nguyên, cộng overhead của các mảng con.
- `AtomicIntegerArray distance`: O(n).
- `AtomicIntegerArray parent`: O(n).
- Hai frontier liên tiếp và các local lists: tổng tối đa O(n) đỉnh đang lưu, do mỗi đỉnh chỉ claim một lần.
- Danh sách task/Future: O(P) mỗi tầng.
- Stack và các đối tượng hỗ trợ cho thread.

Vì thế, bỏ qua overhead object và stack chi tiết:

\[
\boxed{\text{Bộ nhớ toàn thuật toán}=O(n+m+P).}
\]

Nếu không tính graph đầu vào, bộ nhớ phụ O(n+P).

**Lưu ý:** `AtomicIntegerArray` không có nghĩa bản thân mảng này lưu một entry cho mỗi **cạnh**; nó lưu một ô cho mỗi **đỉnh**. Mức độ cạnh tranh CAS lại phụ thuộc vào số cạnh đi tới cùng một đỉnh.

### Có cần thêm boolean visited riêng không?

Không trong thiết kế này. Trạng thái:

\[
distance[v]=-1
\]

đã đóng vai trò “chưa thăm”. Một `boolean[] visited` riêng có thể tạo ra rủi ro **hai trạng thái không nhất quán** nếu worker cập nhật chúng theo thứ tự khác nhau.

Nếu cần trạng thái phức tạp hơn, hãy định nghĩa rõ một **state machine** gồm `UNSEEN`, `CLAIMED`, `PROCESSED` và quy tắc chuyển trạng thái nguyên tử. Không thêm cờ phụ mà không có hợp đồng đồng bộ.

## 17. Parallel DFS: cùng vấn đề visited nhưng khác ngữ nghĩa

DFS (*depth-first search*) tuần tự đi sâu dọc một nhánh trước khi quay lui. Nếu chỉ cần biết **những đỉnh reachable** từ s, có thể cho worker lấy công việc từ hàng đợi/stack đồng thời, dùng CAS để mỗi đỉnh chỉ được xử lý một lần.

Tuy vậy:

- Thứ tự duyệt sẽ **không còn là thứ tự DFS tuần tự xác định**.
- Cây cha có thể khác, thậm chí không còn thỏa cấu trúc thời điểm vào/ra của DFS tuần tự.
- Kết quả `discoveryTime`, `finishTime`, tô màu trắng–xám–đen và những thuật toán dựa vào thứ tự này cần một thiết kế riêng.
- Không được lấy đồ thị vừa “thăm đủ đỉnh” làm bằng chứng đã chạy đúng **Tarjan SCC, low-link, articulation points** hoặc topological DFS theo thuật toán tuần tự ban đầu.

### Một phác thảo parallel reachability

~~~text
atomic state[*] = UNSEEN
concurrent queue of work
CAS(state[source], UNSEEN, SEEN)
enqueue(source)

workers:
    obtain vertex u from queue
    for each neighbor v of u:
        if CAS(state[v], UNSEEN, SEEN):
            enqueue(v)
    announce that task u has completed
~~~

Trong kiểu không dùng barrier này, CAS đủ để bảo đảm **đỉnh được claim một lần**, nhưng **không được dùng số lần lấy công việc làm khoảng cách BFS**. Các worker có thể xử lý nhánh dài trước nhánh ngắn.

### Phát hiện kết thúc không đơn giản là “queue rỗng”

Một hàng đợi concurrent có thể rỗng **trong lúc một worker đang xử lý u** và sắp enqueue hàng xóm mới. Nếu tất cả thread thấy queue rỗng rồi dừng, nhiều đỉnh có thể bị bỏ sót.

Một thiết kế worklist đúng cần giao thức **termination detection**, ví dụ một bộ đếm số việc còn outstanding, trong đó các công việc mới phải được **đăng ký vào bộ đếm trước khi công bố vào queue**, và công việc đang chạy chỉ giảm counter sau khi đã đăng ký các việc mới của nó. Quá trình nhận việc và quyết định dừng còn phải được phối hợp để tránh race giữa “không có việc” và “sắp có việc”.

Đây là một vấn đề khác với CAS visited. Bản BFS theo tầng dùng `invokeAll/Future.get` để đơn giản hóa: kết thúc một tầng chỉ khi toàn bộ task đã hoàn tất, và toàn BFS chỉ khi frontier mới thật sự rỗng.

## 18. Trạng thái visited trong graph động và nhiều nguồn

### Đồ thị đang thay đổi

Chương trình giả định graph là **bất biến trong cả lượt BFS**. Nếu một thread khác thêm/xóa cạnh giữa khi worker đang duyệt `graph[u]`, kết quả có thể không tương ứng với bất kỳ snapshot hợp lệ nào; việc thay adjacency array cũng có thể gây lỗi cạnh tranh dữ liệu.

Để xử lý graph động, cần một trong những chiến lược:

- Chụp một **snapshot bất biến** trước khi chạy.
- Dùng cấu trúc graph concurrent có ngữ nghĩa snapshot rõ ràng.
- Chạy thuật toán gia tăng/động được thiết kế riêng và công bố ngữ nghĩa nhất quán.

Dùng CAS visited **không làm cho graph đầu vào đang bị sửa trở nên an toàn**.

### BFS nhiều nguồn

Nếu có tập nguồn \(S\), có thể khởi tạo:

\[
distance[s]=0\quad\text{cho mọi }s\in S
\]

và frontier ban đầu là tập nguồn duy nhất. Khi đó khoảng cách của v là số cạnh nhỏ nhất từ **bất kỳ nguồn nào**.

Cần xử lý nguồn trùng đúng cách và định nghĩa parent của mỗi nguồn là chính nó. Các bước CAS và barrier theo tầng vẫn áp dụng khi tất cả nguồn đều khởi tạo trước khi worker bắt đầu.

Bản Java minh họa **một nguồn**, không tự nhận đã triển khai multi-source.

### Nhiều thành phần liên thông

BFS từ s chỉ thăm các đỉnh reachable từ s. Nếu muốn quét **mọi đỉnh của graph** để tìm các thành phần liên thông, cần điều phối thêm các nguồn chưa thăm và xét riêng đồ thị vô hướng/hữu hướng.

Trong đồ thị có hướng, khái niệm **SCC** (thành phần liên thông mạnh) còn phức tạp hơn reachability từ một nguồn. Không thể tìm SCC chỉ bằng một BFS từ mỗi nguồn mà không phân tích đúng thuật toán và chi phí.

## 19. Hệ quả về thứ tự và tính tái lập

Song song hóa làm **thứ tự hoàn thành** và **quyết định worker thắng CAS** không xác định.

Những điều **bất biến** với graph tĩnh và thuật toán đã chứng minh:

- Tập đỉnh reachable.
- Mảng khoảng cách ngắn nhất.
- Số tầng reachable.
- Mỗi đỉnh chỉ được claim một lần.

Những điều **có thể khác**:

- Thứ tự các đỉnh trong frontier mới.
- Worker xử lý/claim từng đỉnh.
- Parent của đỉnh có nhiều đường ngắn nhất.
- Thời điểm từng cạnh được kiểm.

Nếu một hệ thống đòi **output giống từng byte ở mọi lần chạy**, phải phân biệt dữ liệu có ngữ nghĩa xác định (distance) với dữ liệu không xác định theo lịch chạy (parent). Có thể chuẩn hóa/sắp xếp frontier sau barrier để in, nhưng việc này **không tự làm parent trở nên xác định**, vì CAS đã chọn cha trước đó.

### Tác động lên test

Không viết:

~~~java
assertEquals(sequentialParents, parallelParents);
~~~

trong trường hợp có nhiều đường ngắn nhất, trừ khi thuật toán có quy tắc tie-break được chứng minh.

Thay bằng:

~~~text
assert distance arrays equal
assert each visited parent is a valid edge
assert parent distance = child distance - 1
~~~

Đây là cách kiểm đúng bản chất thuật toán, không ràng buộc vào lịch thread.

## 20. Java Memory Model và an toàn công bố kết quả

Phối hợp đa luồng có hai khía cạnh:

1. **Atomicity:** một thao tác cập nhật chung không bị chia nhỏ thành lịch check/set cạnh tranh.
2. **Visibility/ordering:** kết quả worker viết đã sẵn sàng khi thread khác sử dụng.

`AtomicIntegerArray.compareAndSet` giải quyết thao tác claim trên ô distance.

`AtomicIntegerArray.set` công bố parent theo quyền sở hữu claim.

`Future.get()` sau khi task kết thúc tạo điểm đồng bộ để thread điều phối đọc danh sách local và, ở cuối thuật toán, snapshot distance/parent.

Trong Java có các quan hệ happens-before do thực thi trong ExecutorService và Future đảm bảo. Điều này quan trọng hơn một giả định mơ hồ rằng “CPU tự đồng bộ cache đủ nhanh”.

### Không sửa frontier đang được nhiều worker đọc

Nếu coordinator sửa `current` khi task đang gọi `current.get(i)` hoặc `current.size()`, thiết kế có thể tạo race hoặc lỗi chỉ số. Bản Java giữ `current` bất biến trong một tầng; chỉ sau khi tất cả Future kết thúc mới tạo và gán frontier tiếp theo.

### Không dùng chung ArrayList mutable cho output

`ArrayList.add` không phải thao tác thread-safe. Nhiều worker thêm vào cùng một `ArrayList` có thể làm mất phần tử hoặc phá trạng thái nội bộ. Danh sách local cho mỗi task tránh hẳn vấn đề, rồi coordinator nối sau barrier.

Một `ConcurrentLinkedQueue` có thể là lựa chọn hợp lệ khác cho next frontier, nhưng nó thường có chi phí đồng bộ và contention; vẫn cần CAS để không enqueue trùng.

## 21. Các trường hợp biên

| Trường hợp | Hành vi đúng |
|---|---|
| Graph chỉ một đỉnh | Khoảng cách của nguồn 0 |
| Self-loop s→s | CAS thất bại vì source đã thăm; không tạo tầng mới |
| Cạnh trùng u→v | Chỉ một CAS từ -1 thành công |
| Chu trình u→v→u | Không lặp vô hạn vì cả hai được claim tối đa một lần |
| Nhiều đường ngắn nhất | Distance giống nhau; parent có thể khác |
| Đỉnh không thể tới s | Distance=-1, parent=-1 |
| Graph có hướng | Chỉ theo những cạnh được liệt kê |
| Graph vô hướng | Cần lưu hai hướng trong adjacency |
| Có đỉnh bậc ra rất lớn | Có thể mất cân bằng tải khi chia theo đỉnh |
| Frontier chỉ một đỉnh | Chỉ một task ở tầng đó |
| Workers=1 | Kết quả BFS đúng, nhưng dùng thêm overhead ExecutorService |
| Workers>n | Bản Java giới hạn poolSize ở n |
| Workers≤0 | Báo IllegalArgumentException |
| Graph rỗng n=0 | Bản Java từ chối, không có source hợp lệ |
| Neighbor ngoài [0,n−1] | Báo lỗi input |
| Adjacency row null | Báo lỗi input |
| Input graph bị sửa giữa chừng | Ngoài hợp đồng; phải có snapshot/dồng bộ riêng |
| Có trọng số cạnh không bằng nhau | Không dùng BFS để tìm weighted shortest path |
| Worker bị lỗi giữa tầng | Không trả kết quả hoàn chỉnh; Future.get truyền lỗi |
| Thread bị interrupt | Không coi kết quả một phần là BFS đã hoàn thành |
| Parent nhiều lựa chọn | Kiểm invariant, không ép bằng parent của BFS tuần tự |

## 22. So sánh chiến lược đồng bộ

| Chiến lược | Quyền claim | Output cạnh tranh | Khi nào phù hợp |
|---|---|---|---|
| Một khóa `synchronized` chung | Đúng nếu đặt toàn bộ check+set trong khóa | Cần xử lý riêng | Dễ chứng minh, nghẽn nhiều worker |
| `AtomicIntegerArray.compareAndSet` | Một winner mỗi v | Local buffers | Bộ đỉnh ID nguyên liên tục, BFS theo tầng |
| `ConcurrentHashMap.newKeySet().add(v)` | Một winner với add thành công | Local buffers hoặc queue | ID thưa, dữ liệu dạng object |
| `AtomicBoolean[]` CAS từng ô | Một winner | Local buffers | Đơn giản nhưng overhead mỗi object |
| `boolean[]` không khóa | Không bảo đảm | Dù queue thread-safe vẫn có duplicate | **Không dùng** trong concurrent traversal |
| Bitmap CAS trên word | Một winner nếu bit thao tác đúng | Local buffers | Đồ thị lớn, tối ưu RAM |
| Worklist queue không barrier | Một winner nếu có CAS | Queue concurrent | Reachability, không tự bảo đảm BFS shortest |

**Tiêu chí chọn:**

- ID các đỉnh có liên tục từ 0 đến n−1 không?
- Có cần khoảng cách ngắn nhất hay chỉ reachability?
- Cần tính một parent bất kỳ hay parent xác định?
- Frontier lớn hay nhỏ, bậc các đỉnh có lệch nhau nhiều?
- Dữ liệu có thể sửa đồng thời không?
- Mục tiêu tối ưu RAM, CPU, độ trễ hay throughput?
- Bộ nhớ cache/NUMA và chi phí CAS có ảnh hưởng đáng kể không?

Cấu trúc thread-safe không thay thế chứng minh thuật toán. Một thiết kế có mọi collection concurrent vẫn có thể cho **khoảng cách sai** nếu mất thứ tự tầng.

## 23. Những lỗi thường gặp

1. **Dùng `if (!visited[v]) visited[v]=true` với nhiều worker**, check-then-act không nguyên tử.
2. **Tin `volatile boolean` làm phép check+set nguyên tử**, trong khi volatile chỉ cung cấp quy tắc visibility/ordering.
3. **Chỉ thay queue bằng ConcurrentLinkedQueue**, quên đồng bộ visited.
4. **Thêm v vào next frontier ngay cả khi CAS thất bại**, tạo bản ghi trùng.
5. **Ghi parent trước khi claim**, nhiều worker có thể ghi đè parent.
6. **Cho parent bằng worker thắng CAS nhưng so từng byte với parent BFS tuần tự**, test sai khi có nhiều đường ngắn nhất.
7. **Bỏ barrier giữa các tầng nhưng vẫn dùng CAS first visit để đặt distance**, nhánh dài có thể claim trước nhánh ngắn.
8. **Dùng hàng đợi công việc không thứ tự nhưng gọi kết quả distance là shortest path**, sai ngữ nghĩa.
9. **Cho phép worker xử lý frontier mới khi các worker tầng cũ còn chạy**, vi phạm bất biến BFS theo tầng.
10. **Đọc parent ngay sau CAS ở thread khác mà chưa có điểm đồng bộ phù hợp**, có thể đọc trạng thái chưa hoàn chỉnh.
11. **Cho nhiều thread cùng ghi vào ArrayList**, dẫn tới mất phần tử/hỏng dữ liệu.
12. **Gọi `ArrayList` read-only nhưng đồng thời sửa nó**, tạo data race.
13. **Không gọi `Future.get`**, có thể bỏ qua lỗi worker và thiếu cạnh.
14. **Gọi `shutdownNow` trước khi task hoàn thành**, hủy BFS dở.
15. **Không đóng ExecutorService**, để rò rỉ thread sau mỗi lượt BFS.
16. **Khởi tạo distance với 0 cho mọi đỉnh**, nhầm với chưa thăm; phải có sentinel rõ.
17. **Dùng số âm -1 làm khoảng cách thật**, trong graph không trọng số khoảng cách reachable không âm.
18. **Không đánh dấu source trước khi enqueue**, self-loop/cạnh quay lại có thể claim source lần nữa.
19. **Không xét self-loop trong test**, bỏ sót vòng lặp vô hạn.
20. **Bỏ qua cạnh trùng**, test không phát hiện duplicate frontier.
21. **Cố đánh dấu visited khi pop thay vì khi enqueue mà không phân tích lại**, có thể tạo nhiều công việc trùng.
22. **Giả định graph vô hướng khi adjacency chỉ lưu u→v**, bỏ sót chiều ngược.
23. **Coi BFS theo số cạnh là Dijkstra cho mọi trọng số**, sai bài toán.
24. **Không kiểm source trong phạm vi**, lỗi chỉ số hoặc kết quả vô nghĩa.
25. **Không kiểm graph null/adjacency null**, lỗi runtime khó chẩn đoán.
26. **Không ràng buộc graph bất biến trong lượt duyệt**, đọc cấu trúc đang bị thay thế.
27. **Phân công mỗi worker số đỉnh bằng nhau rồi coi tải công bằng**, bậc đỉnh có thể chênh lệch lớn.
28. **Không tính overhead barrier cho graph đường đi**, parallel có thể chậm hơn.
29. **Cho rằng tăng worker luôn giảm thời gian**, bỏ qua contention/bộ nhớ.
30. **Nhầm tổng công việc O(n+m) với latency O((n+m)/P)**, bỏ qua critical path.
31. **Không tách quyền truy cập parent và distance**, ghi parent cạnh tranh gây đường cha sai.
32. **Coi quét graph nhiều lần khi validate là không có chi phí**, trên graph lớn cũng O(n+m).
33. **Dùng int[] queue nhỏ hơn số đỉnh reachable trong BFS tuần tự**, dễ overflow.
34. **Dùng số lượng thread bằng số cạnh/đỉnh**, dễ tiêu hao tài nguyên cực lớn.
35. **Cố duy trì thứ tự DFS tuần tự bằng queue concurrent**, hai khái niệm không tương đương.
36. **Dùng DFS parallel tự do để tạo discovery/finish times như DFS tuần tự**, sai với nhiều thuật toán đồ thị.
37. **Kết luận work queue rỗng nghĩa là mọi worker đã xong**, có thể còn task đang sinh hàng xóm.
38. **Không đăng ký công việc mới trước khi công bố enqueue trong termination detection**, tạo false termination.
39. **Thử ít trường hợp không có chu trình và khẳng định CAS không cần**, bỏ sót tranh chấp claim.
40. **Dùng phần tử `parent=-1` cho source nhưng lại truy ngược đến parent[source]**, gây lỗi dựng đường.
41. **Kiểm chỉ số v hợp lệ sau khi đã dùng v để truy cập distance**, lỗi array index.
42. **Không kiểm số tầng trong BFS**, khiến distance tăng sai theo độ sâu task/recursive call.
43. **Dùng DFS reachability để suy ra shortest distance**, sai trong graph tổng quát.
44. **Cho rằng tất cả kết quả song song phải xác định tuyệt đối**, trong khi parent có thể nhiều lựa chọn đúng.
45. **Không phân biệt safety và liveness**, chương trình có thể tránh race nhưng dừng quá sớm hoặc kẹt.
46. **Không phân biệt điều kiện đã xử lý với đã claim**, một worker khác không được tự tái xử lý v đang ở frontier sau.
47. **Dùng nguyên tử nhưng cập nhật hai trường độc lập rồi đọc ở giữa không có protocol**, có thể quan sát snapshot không nhất quán.
48. **Không có oracle BFS tuần tự độc lập**, dễ tin một implementation song song sai nhưng chạy ổn định.
49. **Thử chỉ graph có duy nhất đường đi**, không phát hiện nondeterministic parent.
50. **Đo tăng tốc khi JVM chưa warm-up và không tách chi phí tạo thread pool**, kết luận hiệu năng không đáng tin.

## 24. Câu hỏi và bài tập tự luyện

**Bài 1.** Frontier của BFS là gì?

*Đáp án:* Tập các đỉnh đã khám phá nhưng đang chờ mở rộng **ở cùng một tầng khoảng cách**.

**Bài 2.** Vì sao cần CAS cho visited hoặc distance?

*Đáp án:* Để bảo đảm **chỉ một worker** claim thành công mỗi đỉnh dù nhiều worker cùng thấy cạnh đến nó.

**Bài 3.** Vì sao `get()==-1` rồi `set` không đủ?

*Đáp án:* Hai thao tác riêng không hợp thành một phép kiểm–ghi nguyên tử; worker khác có thể chen vào.

**Bài 4.** Trong chương trình, giá trị -1 của distance có nghĩa gì?

*Đáp án:* Đỉnh **chưa được khám phá** hoặc unreachable khi thuật toán kết thúc.

**Bài 5.** Giá trị ban đầu của distance[source] là gì?

*Đáp án:* 0.

**Bài 6.** Khi xử lý tầng d, CAS thành công đặt distance[v] bằng bao nhiêu?

*Đáp án:* d+1.

**Bài 7.** Vì sao phải đợi mọi task của tầng d trước tầng d+1?

*Đáp án:* Để các đường ngắn hơn được xét trước, bảo đảm distance claim lần đầu là **ngắn nhất**.

**Bài 8.** Có thể dùng CAS mà bỏ barrier và vẫn chắc shortest path không?

*Đáp án:* Không trong thiết kế first-claim; một nhánh dài có thể claim đỉnh trước nhánh ngắn.

**Bài 9.** Vì sao nên có `localNext` cho mỗi task?

*Đáp án:* Tránh nhiều thread cùng sửa một `ArrayList` không thread-safe.

**Bài 10.** Có thể có hai CAS từ -1 tới cùng một đỉnh cùng thành công không?

*Đáp án:* Không, thao tác CAS nguyên tử và sau thành công đầu ô không còn -1.

**Bài 11.** Parent của một đỉnh có hai đường ngắn nhất có bắt buộc giống giữa các lần chạy không?

*Đáp án:* Không; phụ thuộc worker thắng CAS.

**Bài 12.** Những bất biến parent cần kiểm là gì?

*Đáp án:* Có cạnh parent→v và distance[parent]+1=distance[v], với quy ước riêng cho source/unreachable.

**Bài 13.** Với đồ thị ví dụ, distance[8] bằng bao nhiêu?

*Đáp án:* 4.

**Bài 14.** Với ví dụ đó, distance[9] bằng bao nhiêu?

*Đáp án:* -1.

**Bài 15.** Cạnh 0→1 bị lặp có làm 1 vào next frontier hai lần không?

*Đáp án:* Không, CAS chỉ thắng một lần.

**Bài 16.** Nếu đồ thị có self-loop s→s, BFS có cần enqueue s lần nữa không?

*Đáp án:* Không, source đã có distance=0.

**Bài 17.** Bộ nhớ phụ cho distance, parent và frontier có bậc nào?

*Đáp án:* O(n), cộng O(P) cho task/Future và overhead thread.

**Bài 18.** Work duyệt cạnh là bao nhiêu nếu mỗi đỉnh chỉ claim một lần?

*Đáp án:* O(n+m), chưa tính overhead tạo task/barrier.

**Bài 19.** Tại sao chi phí điều phối có thể là O(PL)?

*Đáp án:* Có tối đa P task ở mỗi trong L tầng.

**Bài 20.** Graph hình đường đi dài có lợi cho song song theo đỉnh không?

*Đáp án:* Ít; mỗi frontier thường chỉ có một đỉnh, không có nhiều công việc cùng tầng.

**Bài 21.** Khi một đỉnh có bậc rất lớn, cách chia nào có thể tốt hơn chia theo đỉnh?

*Đáp án:* Chia theo **khối cạnh** hoặc dynamic scheduling.

**Bài 22.** Dùng ConcurrentLinkedQueue có tự ngăn khám phá trùng không?

*Đáp án:* Không, queue thread-safe không thay CAS claim.

**Bài 23.** Nếu source có thể có nhiều giá trị trong multi-source BFS, cần khởi tạo thế nào?

*Đáp án:* Đặt distance=0 cho từng nguồn duy nhất trước khi mở rộng, frontier đầu gồm các nguồn.

**Bài 24.** Đồ thị có trọng số dương có dùng ngay BFS parallel để tìm min tổng trọng số được không?

*Đáp án:* Không, BFS tính ít **cạnh** nhất, không phải min tổng trọng số.

**Bài 25.** Với graph đang bị sửa đồng thời, CAS visited đã đủ an toàn chưa?

*Đáp án:* Chưa; cần snapshot/graph concurrent có ngữ nghĩa rõ ràng.

**Bài 26.** Vì sao parallel DFS không tự cung cấp thứ tự finish như DFS tuần tự?

*Đáp án:* Nhiều nhánh xử lý đồng thời phá thứ tự đệ quy sâu–quay lui của DFS tuần tự.

**Bài 27.** Vì sao queue rỗng chưa đủ phát hiện kết thúc trong worklist không barrier?

*Đáp án:* Worker có thể đang xử lý một đỉnh và sắp tạo công việc mới.

**Bài 28.** `Future.get()` giúp gì ngoài trả `localNext`?

*Đáp án:* Đồng bộ kết quả task, truyền lỗi task và hỗ trợ happens-before với thread nhận kết quả.

**Bài 29.** Trong random test, vì sao nên đổi worker count giữa 1,2,4?

*Đáp án:* Để kiểm kết quả không dựa vào một lịch/phân chia task cụ thể.

**Bài 30.** Khi nào nên đo hiệu năng thay vì kết luận từ O(n+m)?

*Đáp án:* Khi đánh giá tăng tốc thực tế, phải tính chi phí thread/barrier, contention, cân bằng tải và memory bandwidth.

**Bài 31.** Nếu muốn tìm SCC, có thể lấy mỗi node có distance≥0 rồi gọi đó là SCC của source không?

*Đáp án:* Không, reachability từ source khác với liên thông mạnh hai chiều.

**Bài 32.** Nếu test chỉ so mảng distance mà không kiểm parent, có thể bỏ sót lỗi gì?

*Đáp án:* Parent không phải cạnh hợp lệ, parent ở sai tầng hoặc chuỗi parent có vấn đề.

**Bài 33.** Lý do gì để tránh so parent chính xác với BFS tuần tự?

*Đáp án:* Nhiều đường ngắn nhất có parent hợp lệ khác nhau; song song chọn theo lịch CAS.

**Bài 34.** Kết quả nào của BFS parallel đồng bộ theo tầng là tất định trên graph tĩnh?

*Đáp án:* **Tập đỉnh reachable và khoảng cách ngắn nhất** từ source.

**Bài 35.** Một thiết kế có mọi collection thread-safe có chắc BFS đúng không?

*Đáp án:* Không; phải bảo đảm cả bất biến thuật toán như **thứ tự tầng**.

**Tổng kết:** Parallel graph traversal không chỉ là nhiều thread duyệt adjacency. Muốn BFS đúng trên đồ thị không trọng số, cần **CAS nguyên tử để claim từng đỉnh**, **task-local frontier để tránh tranh chấp cấu trúc** và **barrier giữa các tầng** để các đường ngắn hơn luôn được khám phá trước. Với bất biến này, khoảng cách song song trùng BFS tuần tự; parent có thể khác do nhiều đường đi ngắn nhất nhưng phải trỏ theo cạnh từ tầng trước. Bản Java 17 dùng `AtomicIntegerArray`, `ExecutorService.invokeAll` và `Future.get`, kiểm đúng trên 512 đồ thị có hướng ba đỉnh và 180 đồ thị ngẫu nhiên với ba số worker. Tổng công việc duyệt có bậc O(n+m) cộng overhead điều phối, nhưng latency không tự động chia cho số lõi vì độ rộng frontier, độ lệch bậc, CAS contention và đồng bộ. Khi chuyển sang parallel DFS, worklist không có barrier hoặc graph động, cần phân tích **termination detection, thứ tự duyệt và nhất quán trạng thái** riêng, không tái sử dụng kết luận shortest path của BFS một cách tùy tiện.
